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
from simulator.parser.transpiler import transpile_common_to_risc_cisc
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
                logger.error("Transpilation failed: %s", exc)
                return Response(
                    {
                        "error": True,
                        "message": f"Transpilation failed: {exc}",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

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
