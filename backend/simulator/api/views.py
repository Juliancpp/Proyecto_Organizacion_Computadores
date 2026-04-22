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

logger = logging.getLogger(__name__)


class SimulateView(APIView):
    """
    POST /api/simulate/

    Accepts assembly code and runs it through both RISC and CISC engines,
    returning cycle-by-cycle timelines and performance metrics.

    Supports two modes:
    - Unified:  ``{"code": "..."}`` — same code to both engines.
    - Split:    ``{"risc_code": "...", "cisc_code": "..."}`` — architecture-
                specific code.
    """

    def post(self, request: Request) -> Response:
        serializer = SimulationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        unified_code = data.get("code", "").strip()
        risc_code = data.get("risc_code", "").strip() or unified_code
        cisc_code = data.get("cisc_code", "").strip() or unified_code
        transpile = data.get("transpile", False)
        step_mode = data["step"]
        use_pipeline = data["pipeline"]
        risc_tcycle = data.get("risc_tcycle", DEFAULT_RISC_TCYCLE_NS)
        cisc_tcycle = data.get("cisc_tcycle", DEFAULT_CISC_TCYCLE_NS)

        if transpile:
            if not unified_code:
                return Response(
                    {"error": "Invalid request", "details": {"code": ["This field is required when transpile=true."]}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                risc_code, cisc_code = transpile_common_to_risc_cisc(unified_code)
            except SimulatorError as exc:
                return Response(
                    {"error": "Transpilation failed", "details": str(exc)},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

        response_data: dict = {}
        errors: dict = {}

        # ------ RISC simulation ------
        if risc_code:
            try:
                risc_result = self._run_risc(risc_code, step_mode, use_pipeline, risc_tcycle)
                response_data["risc"] = risc_result
            except SimulatorError as exc:
                errors["risc"] = str(exc)
                logger.warning("RISC simulation error: %s", exc)

        # ------ CISC simulation ------
        if cisc_code:
            try:
                cisc_result = self._run_cisc(cisc_code, step_mode, use_pipeline, cisc_tcycle)
                response_data["cisc"] = cisc_result
            except SimulatorError as exc:
                errors["cisc"] = str(exc)
                logger.warning("CISC simulation error: %s", exc)

        # ------ Comparison (only if both succeeded) ------
        if "risc" in response_data and "cisc" in response_data:
            risc_m = response_data["risc"]["metrics"]
            cisc_m = response_data["cisc"]["metrics"]
            comparison = self._build_comparison(risc_m, cisc_m)
            response_data["comparison"] = comparison

        if errors:
            response_data["errors"] = errors

        if not response_data or (errors and "risc" not in response_data and "cisc" not in response_data):
            return Response(
                {"error": "Both simulations failed", "details": errors},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(response_data, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_risc(code: str, step: bool, pipeline: bool, tcycle: float) -> dict:
        parsed = parse_risc(code)
        state = CPUState()
        if pipeline:
            state = execute_risc_pipeline(parsed, state)
        else:
            state = execute_risc(parsed, state, step=step)
        ic = count_executed_instructions(state)
        metrics = compute_metrics(state, ic, tcycle)
        return {
            "timeline": [s.to_dict() for s in state.timeline],
            "metrics": metrics.to_dict(),
            "final_state": state.snapshot(),
            "parsed_instructions": parsed.to_dict(),
        }

    @staticmethod
    def _run_cisc(code: str, step: bool, pipeline: bool, tcycle: float) -> dict:
        parsed = parse_cisc(code)
        state = CPUState()
        if pipeline:
            state = execute_cisc_pipeline(parsed, state)
        else:
            state = execute_cisc(parsed, state, step=step)
        ic = count_executed_instructions(state)
        metrics = compute_metrics(state, ic, tcycle)
        return {
            "timeline": [s.to_dict() for s in state.timeline],
            "metrics": metrics.to_dict(),
            "final_state": state.snapshot(),
            "parsed_instructions": parsed.to_dict(),
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

        try:
            parsed = parse_risc(code)
            state = CPUState()
            if use_pipeline:
                state = execute_risc_pipeline(parsed, state)
            else:
                state = execute_risc(parsed, state, step=step_mode)

            ic = count_executed_instructions(state)
            metrics = compute_metrics(state, ic, risc_tcycle)

            return Response({
                "timeline": [s.to_dict() for s in state.timeline],
                "metrics": metrics.to_dict(),
                "final_state": state.snapshot(),
                "parsed_instructions": parsed.to_dict(),
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

        try:
            parsed = parse_cisc(code)
            state = CPUState()
            if use_pipeline:
                state = execute_cisc_pipeline(parsed, state)
            else:
                state = execute_cisc(parsed, state, step=step_mode)

            ic = count_executed_instructions(state)
            metrics = compute_metrics(state, ic, cisc_tcycle)

            return Response({
                "timeline": [s.to_dict() for s in state.timeline],
                "metrics": metrics.to_dict(),
                "final_state": state.snapshot(),
                "parsed_instructions": parsed.to_dict(),
            })

        except SimulatorError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
