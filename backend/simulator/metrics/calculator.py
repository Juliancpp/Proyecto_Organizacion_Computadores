"""
Performance metrics calculator for CPU simulations.

Computes the standard performance equation:

  CPU Time = IC × CPI × T_cycle

Where:
  IC      = Instruction Count (number of instructions executed)
  CPI     = Cycles Per Instruction  =  Total Cycles / IC
  T_cycle = Clock period (seconds per cycle)

The module also provides comparative analysis between RISC and CISC
results, computing speedup ratios and efficiency differences.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from simulator.core.cpu_state import CPUState


# ---------------------------------------------------------------------------
# Default clock periods (nanoseconds)
#
# RISC chips typically use a faster clock because each stage does less
# work → shorter critical path → smaller T_cycle.
# ---------------------------------------------------------------------------

DEFAULT_RISC_TCYCLE_NS = 1.0   # 1 ns  → 1 GHz
DEFAULT_CISC_TCYCLE_NS = 1.5   # 1.5 ns → ~667 MHz


# ---------------------------------------------------------------------------
# Metrics result
# ---------------------------------------------------------------------------

@dataclass
class Metrics:
    """
    Computed performance metrics for one architecture.

    All time values are in nanoseconds unless otherwise noted.
    """
    instruction_count: int      # IC
    total_cycles: int           # Total clock cycles consumed
    cpi: float                  # Cycles Per Instruction
    t_cycle_ns: float           # Clock period in nanoseconds
    cpu_time_ns: float          # Total CPU time in nanoseconds
    cpu_time_us: float          # Total CPU time in microseconds (convenience)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instruction_count": self.instruction_count,
            "total_cycles": self.total_cycles,
            "cpi": round(self.cpi, 4),
            "t_cycle_ns": self.t_cycle_ns,
            "cpu_time_ns": round(self.cpu_time_ns, 4),
            "cpu_time_us": round(self.cpu_time_us, 6),
        }


# ---------------------------------------------------------------------------
# Comparative analysis
# ---------------------------------------------------------------------------

@dataclass
class ComparativeMetrics:
    """Side-by-side comparison between RISC and CISC execution."""
    risc: Metrics
    cisc: Metrics
    speedup_risc_over_cisc: float   # >1 means RISC is faster
    cycle_ratio: float              # CISC cycles / RISC cycles

    def to_dict(self) -> dict[str, Any]:
        return {
            "risc": self.risc.to_dict(),
            "cisc": self.cisc.to_dict(),
            "speedup_risc_over_cisc": round(self.speedup_risc_over_cisc, 4),
            "cycle_ratio": round(self.cycle_ratio, 4),
            "analysis": self._analysis_text(),
        }

    def _analysis_text(self) -> str:
        """Generate a human-readable comparison summary."""
        lines = []
        lines.append(
            f"RISC executed {self.risc.instruction_count} instructions in "
            f"{self.risc.total_cycles} cycles (CPI={self.risc.cpi:.2f})."
        )
        lines.append(
            f"CISC executed {self.cisc.instruction_count} instructions in "
            f"{self.cisc.total_cycles} cycles (CPI={self.cisc.cpi:.2f})."
        )
        if self.speedup_risc_over_cisc > 1:
            lines.append(
                f"RISC is {self.speedup_risc_over_cisc:.2f}× faster in wall-clock time."
            )
        elif self.speedup_risc_over_cisc < 1:
            lines.append(
                f"CISC is {1/self.speedup_risc_over_cisc:.2f}× faster in wall-clock time."
            )
        else:
            lines.append("Both architectures have equal wall-clock performance.")
        return " ".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_metrics(
    state: CPUState,
    instruction_count: int,
    t_cycle_ns: float,
) -> Metrics:
    """
    Compute performance metrics from a completed simulation.

    FIXED FORMULA (Task 1):
    ─────────────────────────────────────────────────────────────────────
    CPU Time = total_cycles × T_cycle

    Where total_cycles is taken directly from the CPUState (the ground
    truth of what the simulator actually ran), NOT recomputed as IC×CPI.

    The old formula  cpu_time_ns = IC × CPI × T_cycle  is algebraically
    equivalent to  total_cycles × T_cycle  only when CPI = total/IC, but
    it obscures the pipeline savings because it re-derives cycles from IC
    instead of using the actual simulated cycle count.

    For the CISC pipeline model:
        total_cycles_pipe ≈ Σ(µops_i) + pipeline_fill_cost
    This is already captured in state.cycles after execute_cisc_pipeline().

    CPI is still reported as a diagnostic ratio (total_cycles / IC).
    ─────────────────────────────────────────────────────────────────────

    Args:
        state:              The CPUState after execution.
        instruction_count:  Number of instructions that were executed
                            (may differ from parsed count due to branches).
        t_cycle_ns:         Clock period in nanoseconds.

    Returns:
        A Metrics instance.
    """
    total_cycles = state.cycles
    cpi = total_cycles / instruction_count if instruction_count > 0 else 0.0
    # Use total_cycles directly — this reflects actual pipeline savings
    cpu_time_ns = total_cycles * t_cycle_ns
    cpu_time_us = cpu_time_ns / 1_000.0

    return Metrics(
        instruction_count=instruction_count,
        total_cycles=total_cycles,
        cpi=cpi,
        t_cycle_ns=t_cycle_ns,
        cpu_time_ns=cpu_time_ns,
        cpu_time_us=cpu_time_us,
    )


def compare(
    risc_state: CPUState,
    risc_ic: int,
    cisc_state: CPUState,
    cisc_ic: int,
    risc_t_cycle: float = DEFAULT_RISC_TCYCLE_NS,
    cisc_t_cycle: float = DEFAULT_CISC_TCYCLE_NS,
) -> ComparativeMetrics:
    """
    Compute and compare metrics between RISC and CISC execution results.

    Returns:
        A ComparativeMetrics instance containing both individual metrics
        and cross-architecture analysis.
    """
    risc_metrics = compute_metrics(risc_state, risc_ic, risc_t_cycle)
    cisc_metrics = compute_metrics(cisc_state, cisc_ic, cisc_t_cycle)

    speedup = (
        cisc_metrics.cpu_time_ns / risc_metrics.cpu_time_ns
        if risc_metrics.cpu_time_ns > 0
        else 0.0
    )
    cycle_ratio = (
        cisc_metrics.total_cycles / risc_metrics.total_cycles
        if risc_metrics.total_cycles > 0
        else 0.0
    )

    return ComparativeMetrics(
        risc=risc_metrics,
        cisc=cisc_metrics,
        speedup_risc_over_cisc=speedup,
        cycle_ratio=cycle_ratio,
    )


def count_executed_instructions(state: CPUState) -> int:
    """
    Count the number of instructions actually executed by examining
    the timeline.

    Works for all three execution modes:
    - RISC single-issue:  events with "DECODE instruction" in action
    - RISC pipeline:      events with pipeline_stage == "IF" (each IF = 1 new instruction)
    - CISC micro-ops:     events with micro_op_index == 1 (first µ-op of instruction)

    NOTE (Task 2): timeline is now List[CPUSnapshot]; each snapshot exposes
    its events as a tuple of dicts via snapshot.events.
    """
    ic = 0
    seen_pipeline_instructions: set[int] = set()

    for snapshot in state.timeline:
        # snapshot.events is a tuple[dict, ...] (immutable, from CPUSnapshot)
        for event in snapshot.events:
            action = event.get("action", "")
            meta = event.get("meta", {})

            # RISC single-issue: "DECODE instruction XXX"
            if "DECODE instruction" in action and not meta.get("micro_op"):
                ic += 1
                break

            # RISC pipeline: IF stage = new instruction entering pipeline
            if meta.get("pipeline_stage") == "IF":
                instr_idx = meta.get("instruction_index")
                if instr_idx is not None and instr_idx not in seen_pipeline_instructions:
                    seen_pipeline_instructions.add(instr_idx)
                    ic += 1
                break

            # CISC: first µ-op of an instruction
            if meta.get("micro_op") and meta.get("micro_op_index") == 1:
                ic += 1
                break

    return ic
