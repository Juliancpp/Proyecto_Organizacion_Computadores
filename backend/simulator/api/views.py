"""
API views for the CPU simulator.

All views are thin wrappers — they validate input, call the simulation
engines, and format the output.  **No business logic lives here.**
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from simulator.api.serializers import (
    SimulationRequestSerializer,
    SingleArchRequestSerializer,
)
from simulator.core.cpu_state import CPUState
from simulator.core.exceptions import SimulatorError
from simulator.parser.assembly_parser import parse_risc, parse_cisc
from simulator.parser.transpiler import transpile_common_to_risc_cisc, transpile_cisc_to_risc
from simulator.risc.engine import execute_risc
from simulator.risc.pipeline import execute_risc_pipeline
from simulator.cisc.engine import execute_cisc, execute_cisc_pipeline
from simulator.metrics.calculator import (
    compare,
    compute_metrics,
    count_executed_instructions,
    DEFAULT_RISC_TCYCLE_NS,
    DEFAULT_CISC_TCYCLE_NS,
)
from simulator.x86.parser import parse_x86, is_x86_syntax
from simulator.x86.engine import execute_x86, read_array_from_memory

logger = logging.getLogger(__name__)


# Patterns that indicate the code is already in an architecture-specific
# syntax (not the restricted "common dialect" expected by the transpiler).
import re as _re

# CISC memory-destination MOV: "MOV [addr], ..."
_CISC_MEM_DST_RE = _re.compile(r'\bMOV\s*\[', _re.IGNORECASE)

# CISC memory-to-memory arithmetic: "ADD [..], [..]" / "MUL [..], [..]"
_CISC_MEM_ARITH_RE = _re.compile(
    r'\b(?:ADD|SUB|MUL|DIV)\s*\[[^\]]+\]\s*,\s*\[',
    _re.IGNORECASE,
)

# CISC-only instructions: INC [addr], DEC [addr]
_CISC_INC_DEC_RE = _re.compile(r'\b(?:INC|DEC)\s*\[', _re.IGNORECASE)

# Bare-digit register usage in LOAD/STORE (e.g. "LOAD 1, [10]" without R prefix)
_BARE_REG_LOAD_RE = _re.compile(r'\b(?:LOAD|STORE)\s+\d', _re.IGNORECASE)


def _is_already_arch_specific(code: str) -> bool:
    """
    Return True if the source looks like it's already in a final
    architecture's dialect (CISC or bare-register RISC) rather than the
    restricted "common dialect" accepted by the transpiler.

    The transpiler's common dialect requires:
      - MOV Rn, imm        (never MOV [addr], ...)
      - LOAD Rn, [addr]    (never LOAD n, [addr])
      - ADD Rd, Rs1, Rs2   (never ADD [a], [b])
      - No INC/DEC on memory

    When any of these architecture-specific patterns appear, transpilation
    will fail — so we skip it and run the code directly on the target
    engine instead.
    """
    if _CISC_MEM_DST_RE.search(code):
        return True
    if _CISC_MEM_ARITH_RE.search(code):
        return True
    if _CISC_INC_DEC_RE.search(code):
        return True
    if _BARE_REG_LOAD_RE.search(code):
        return True
    return False


class SimulateView(APIView):
    """
    POST /api/simulate/

    Accepts assembly code and runs it through the specified architecture engine(s).

    Supports multiple modes:
    - Unified:  ``{"code": "..."}`` — same code to both RISC and CISC engines.
    - Split:    ``{"risc_code": "...", "cisc_code": "..."}`` — architecture-specific code.
    - Targeted: ``{"code": "...", "architecture": "x86"}`` — run only specified architecture.

    The ``architecture`` field controls which engine(s) run:
    - "auto" (default): Auto-detect from code syntax; runs all matching engines.
    - "risc": Run only RISC simulation.
    - "cisc": Run only CISC simulation.
    - "x86": Run only x86-64 simulation.
    """

    def post(self, request: Request) -> Response:
        # Debug logging
        logger.debug("Incoming request data: %s", request.data)

        serializer = SimulationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("Validation error: %s", serializer.errors)
            return Response(
                {
                    "error": True,
                    "message": "Invalid request format",
                    "details": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        unified_code = data.get("code", "").strip()
        risc_code = data.get("risc_code", "").strip()
        cisc_code = data.get("cisc_code", "").strip()
        architecture = data.get("architecture", "auto")
        transpile = data.get("transpile", False)
        step_mode = data["step"]
        use_pipeline = data["pipeline"]
        risc_tcycle = data.get("risc_tcycle", DEFAULT_RISC_TCYCLE_NS)
        cisc_tcycle = data.get("cisc_tcycle", DEFAULT_CISC_TCYCLE_NS)
        simulation_mode = data.get("simulation_mode", "microarchitectural")
        input_values = data.get("input_values", [])

        logger.info(
            "Simulation request: architecture=%s, transpile=%s, code_length=%d",
            architecture, transpile, len(unified_code),
        )

        # If architecture is explicitly set, handle accordingly
        is_x86 = is_x86_syntax(unified_code) if unified_code else False

        # Skip transpile if x86 code detected (transpile is for common dialect only)
        if transpile and is_x86:
            logger.info("X86 syntax detected, disabling transpile")
            transpile = False

        # Skip transpile if code is already in architecture-specific syntax
        # (e.g. CISC-style MOV [addr], imm or bare-digit LOAD/STORE operands).
        # When the code is pure CISC, auto-generate an equivalent RISC version
        # via the CISC→RISC transpiler so both engines can run in comparison.
        if transpile and unified_code and _is_already_arch_specific(unified_code):
            logger.info("Architecture-specific (CISC) syntax detected, "
                        "auto-generating RISC via CISC→RISC transpiler")
            try:
                risc_code = transpile_cisc_to_risc(unified_code)
                cisc_code = unified_code  # CISC code runs as-is
                logger.info(
                    "CISC→RISC transpilation successful: RISC=%d chars",
                    len(risc_code),
                )
            except SimulatorError as exc:
                logger.warning(
                    "CISC→RISC transpilation failed, RISC side will fall back "
                    "to direct execution: %s", exc,
                )
                # Fall through — RISC will fail with its own error but CISC runs.
            transpile = False

        if transpile:
            if not unified_code:
                return Response(
                    {
                        "error": True,
                        "message": "Code field is required when transpile=true",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                risc_code, cisc_code = transpile_common_to_risc_cisc(unified_code)
                logger.info("Transpilation successful: RISC=%d chars, CISC=%d chars", len(risc_code), len(cisc_code))
            except SimulatorError as exc:
                # Graceful fallback: if the transpiler rejects the input,
                # fall back to running the code as-is on the target engines.
                # Each engine parser will report its own error if the syntax
                # is actually incompatible, but many valid CISC/RISC programs
                # get rejected by the transpiler because they aren't in the
                # restricted "common dialect".
                logger.warning(
                    "Transpilation failed, falling back to direct execution: %s", exc,
                )
                errors_transpile = f"Transpilation skipped: {exc}"
                transpile = False
                # Note: risc_code and cisc_code remain empty; unified_code will
                # be passed directly to each engine below.

        response_data: dict = {}
        errors: dict = {}
        any_success = False

        # Determine which architectures to run based on 'architecture' field
        run_risc = architecture in ("auto", "risc") and (risc_code or unified_code)
        run_cisc = architecture in ("auto", "cisc") and (cisc_code or unified_code)
        run_x86 = architecture in ("auto", "x86") and unified_code

        # ------ RISC simulation ------
        if run_risc:
            code_to_run = risc_code or unified_code
            try:
                risc_result = self._run_risc(code_to_run, step_mode, use_pipeline, risc_tcycle, simulation_mode, input_values)
                response_data["risc"] = risc_result
                any_success = True
                logger.info("RISC simulation successful")
            except Exception as exc:
                error_msg = str(exc)
                errors["risc"] = error_msg
                logger.warning("RISC simulation error: %s", error_msg)

        # ------ CISC simulation ------
        if run_cisc:
            code_to_run = cisc_code or unified_code
            try:
                cisc_result = self._run_cisc(code_to_run, step_mode, use_pipeline, cisc_tcycle, simulation_mode, input_values)
                response_data["cisc"] = cisc_result
                any_success = True
                logger.info("CISC simulation successful")
            except Exception as exc:
                error_msg = str(exc)
                errors["cisc"] = error_msg
                logger.warning("CISC simulation error: %s", error_msg)

        # ------ Comparison (only if both RISC and CISC succeeded) ------
        if "risc" in response_data and "cisc" in response_data:
            risc_m = response_data["risc"]["metrics"]
            cisc_m = response_data["cisc"]["metrics"]
            comparison = self._build_comparison(risc_m, cisc_m)
            response_data["comparison"] = comparison

        # ------ x86-64 simulation ------
        if run_x86:
            try:
                x86_result = self._run_x86(unified_code)
                response_data["x86"] = x86_result
                any_success = True
                logger.info("x86-64 simulation successful")
            except Exception as exc:
                error_msg = str(exc)
                errors["x86"] = error_msg
                logger.warning("x86-64 simulation error: %s", error_msg)

        if errors:
            response_data["errors"] = errors

        # Return success if any simulation succeeded
        if any_success:
            return Response(response_data, status=status.HTTP_200_OK)

        # All simulations failed - return 400 with detailed errors
        logger.error("All simulations failed: %s", errors)
        return Response(
            {
                "error": True,
                "message": "All simulations failed",
                "details": errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_risc(code: str, step: bool, pipeline: bool, tcycle: float,
                  simulation_mode: str = "microarchitectural",
                  input_values: list | None = None) -> dict:
        parsed = parse_risc(code)
        state = CPUState()
        if input_values:
            state.input_queue = list(input_values)
        if pipeline:
            state = execute_risc_pipeline(parsed, state)
        else:
            state = execute_risc(parsed, state, step=step)
        ic = count_executed_instructions(state)
        metrics = compute_metrics(state, ic, tcycle)
        timeline = [] if simulation_mode == "functional" else [s.to_dict() for s in state.timeline]
        return {
            "timeline": timeline,
            "metrics": metrics.to_dict(),
            "final_state": state.snapshot(),
            "parsed_instructions": parsed.to_dict(),
            "simulation_mode": simulation_mode,
            "output_log": state.output_log,
        }

    @staticmethod
    def _run_cisc(code: str, step: bool, pipeline: bool, tcycle: float,
                  simulation_mode: str = "microarchitectural",
                  input_values: list | None = None) -> dict:
        parsed = parse_cisc(code)
        state = CPUState()
        if input_values:
            state.input_queue = list(input_values)
        if pipeline:
            state = execute_cisc_pipeline(parsed, state)
        else:
            state = execute_cisc(parsed, state, step=step)
        ic = count_executed_instructions(state)
        metrics = compute_metrics(state, ic, tcycle)
        timeline = [] if simulation_mode == "functional" else [s.to_dict() for s in state.timeline]
        return {
            "timeline": timeline,
            "metrics": metrics.to_dict(),
            "final_state": state.snapshot(),
            "parsed_instructions": parsed.to_dict(),
            "simulation_mode": simulation_mode,
            "output_log": state.output_log,
        }

    @staticmethod
    def _run_x86(code: str) -> dict:
        parsed = parse_x86(code)
        state = execute_x86(parsed)

        # Read arrays from data symbols for output
        arrays = {}
        for name, sym in parsed.data_symbols.items():
            if sym.size >= 4:
                arrays[name] = read_array_from_memory(state, sym)

        timeline = [s.to_dict() for s in state.core_state.timeline]

        return {
            "timeline": timeline,
            "final_state": state.snapshot(),
            "parsed_instructions": parsed.to_dict(),
            "arrays": arrays,
            "constants": parsed.constants,
            "cycles": state.cycles,
            "output_log": state.output_log,
        }

    @staticmethod
    def _build_comparison(risc_metrics: dict, cisc_metrics: dict) -> dict:
        risc_time = risc_metrics["cpu_time_ns"]
        cisc_time = cisc_metrics["cpu_time_ns"]
        speedup = cisc_time / risc_time if risc_time > 0 else 0.0
        cycle_ratio = cisc_metrics["total_cycles"] / risc_metrics["total_cycles"] if risc_metrics["total_cycles"] > 0 else 0.0

        analysis_lines = [
            f"RISC: {risc_metrics['instruction_count']} instructions, "
            f"{risc_metrics['total_cycles']} cycles (CPI={risc_metrics['cpi']:.2f}).",
            f"CISC: {cisc_metrics['instruction_count']} instructions, "
            f"{cisc_metrics['total_cycles']} cycles (CPI={cisc_metrics['cpi']:.2f}).",
        ]
        if speedup > 1:
            analysis_lines.append(f"RISC is {speedup:.2f}× faster in wall-clock time.")
        elif speedup < 1:
            analysis_lines.append(f"CISC is {1/speedup:.2f}× faster in wall-clock time.")
        else:
            analysis_lines.append("Both architectures have equal performance.")

        return {
            "risc_metrics": risc_metrics,
            "cisc_metrics": cisc_metrics,
            "speedup_risc_over_cisc": round(speedup, 4),
            "cycle_ratio": round(cycle_ratio, 4),
            "analysis": " ".join(analysis_lines),
        }


class SimulateRISCView(APIView):
    """
    POST /api/simulate/risc/

    Run only the RISC simulation.
    """

    def post(self, request: Request) -> Response:
        serializer = SingleArchRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        code = data["code"]
        step_mode = data["step"]
        use_pipeline = data["pipeline"]
        risc_tcycle = data.get("risc_tcycle", DEFAULT_RISC_TCYCLE_NS)
        simulation_mode = data.get("simulation_mode", "microarchitectural")
        input_values = data.get("input_values", [])

        try:
            parsed = parse_risc(code)
            state = CPUState()
            if input_values:
                state.input_queue = list(input_values)
            if use_pipeline:
                state = execute_risc_pipeline(parsed, state)
            else:
                state = execute_risc(parsed, state, step=step_mode)

            ic = count_executed_instructions(state)
            metrics = compute_metrics(state, ic, risc_tcycle)
            timeline = [] if simulation_mode == "functional" else [s.to_dict() for s in state.timeline]

            return Response({
                "timeline": timeline,
                "metrics": metrics.to_dict(),
                "final_state": state.snapshot(),
                "parsed_instructions": parsed.to_dict(),
                "simulation_mode": simulation_mode,
                "output_log": state.output_log,
            })

        except SimulatorError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)


class SimulateCISCView(APIView):
    """
    POST /api/simulate/cisc/

    Run only the CISC simulation.
    """

    def post(self, request: Request) -> Response:
        serializer = SingleArchRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        code = data["code"]
        step_mode = data["step"]
        use_pipeline = data["pipeline"]
        cisc_tcycle = data.get("cisc_tcycle", DEFAULT_CISC_TCYCLE_NS)
        simulation_mode = data.get("simulation_mode", "microarchitectural")
        input_values = data.get("input_values", [])

        try:
            parsed = parse_cisc(code)
            state = CPUState()
            if input_values:
                state.input_queue = list(input_values)
            if use_pipeline:
                state = execute_cisc_pipeline(parsed, state)
            else:
                state = execute_cisc(parsed, state, step=step_mode)

            ic = count_executed_instructions(state)
            metrics = compute_metrics(state, ic, cisc_tcycle)
            timeline = [] if simulation_mode == "functional" else [s.to_dict() for s in state.timeline]

            return Response({
                "timeline": timeline,
                "metrics": metrics.to_dict(),
                "final_state": state.snapshot(),
                "parsed_instructions": parsed.to_dict(),
                "simulation_mode": simulation_mode,
                "output_log": state.output_log,
            })

        except SimulatorError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)


class SimulateX86View(APIView):
    """
    POST /api/simulate/x86/

    Run the x86-64 NASM-style assembly simulation.
    """

    def post(self, request: Request) -> Response:
        logger.debug("Incoming x86 request: %s", request.data)

        serializer = SingleArchRequestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("Validation error: %s", serializer.errors)
            return Response(
                {
                    "error": True,
                    "message": "Invalid request format",
                    "details": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        code = data["code"]

        try:
            logger.info("Parsing x86 code (%d chars)", len(code))
            parsed = parse_x86(code)
            logger.info("Executing x86: %d instructions", len(parsed.instructions))
            state = execute_x86(parsed)

            # Read arrays from data symbols for output
            arrays = {}
            for name, sym in parsed.data_symbols.items():
                if sym.size >= 4:
                    arrays[name] = read_array_from_memory(state, sym)

            timeline = [s.to_dict() for s in state.core_state.timeline]

            logger.info("x86 simulation complete: %d cycles, halted=%s", state.cycles, state.halted)

            return Response({
                "timeline": timeline,
                "final_state": state.snapshot(),
                "parsed_instructions": parsed.to_dict(),
                "arrays": arrays,
                "constants": parsed.constants,
                "cycles": state.cycles,
                "output_log": state.output_log,
            })

        except Exception as exc:
            logger.error("x86 simulation failed: %s", exc)
            return Response(
                {
                    "error": True,
                    "message": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
