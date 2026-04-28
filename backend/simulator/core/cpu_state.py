"""
CPUState — immutable snapshot-based processor state.

TASK 2 FIX: Enforce immutable state design.
─────────────────────────────────────────────────────────────────────────────
Each cycle produces a NEW CPUState snapshot; no in-place mutation of
committed state is allowed.

Design:
  • CPUState is the single source of truth for one point in time.
  • Mutations happen through a MutableCPUContext (a working buffer).
  • At end_cycle(), the context is frozen into an immutable CPUState
    snapshot and appended to the timeline.
  • The timeline is List[CPUState], enabling time-travel debugging and
    deterministic replay.

Benefits:
  • Time-travel debugging: step backward by indexing timeline[n].
  • Determinism: re-running from any snapshot produces identical results.
  • Aligns with event-sourcing: each state is derived from the previous.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

from .events import Event

logger = logging.getLogger(__name__)

NUM_REGISTERS = 8
DEFAULT_MEMORY_SIZE = 256


# ---------------------------------------------------------------------------
# Immutable snapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CPUSnapshot:
    """
    A frozen, immutable record of CPU state at the end of one cycle.

    frozen=True makes all fields read-only after construction, enforcing
    the immutability contract at the Python level.
    """
    cycle: int
    pc: int
    registers: tuple[int, ...]       # immutable tuple, not a list
    memory: tuple[tuple[int, int], ...]  # ((addr, val), ...) — hashable
    halted: bool
    events: tuple[dict[str, Any], ...]  # serialised events for this cycle
    # Control signals visible to the frontend
    control_signals: dict[str, Any] = field(default_factory=dict)
    current_instruction: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "pc": self.pc,
            "registers": list(self.registers),
            "memory": dict(self.memory),
            "halted": self.halted,
            "events": list(self.events),
            "control_signals": self.control_signals,
            "current_instruction": self.current_instruction,
        }


# ---------------------------------------------------------------------------
# Mutable working context (used WITHIN a single cycle, then frozen)
# ---------------------------------------------------------------------------

class CPUState:
    """
    Working CPU state used by the execution engines.

    IMMUTABILITY CONTRACT:
      • Engines mutate this object freely within a cycle.
      • Calling end_cycle() freezes the current state into a CPUSnapshot
        and appends it to self.timeline (List[CPUSnapshot]).
      • After end_cycle(), the snapshot is read-only; only the live
        working fields (pc, registers, memory, …) continue to be mutable
        for the NEXT cycle.

    The timeline is the authoritative record of execution history.
    Each entry is a CPUSnapshot — a complete, independent state image.
    """

    def __init__(self, memory_size: int = DEFAULT_MEMORY_SIZE) -> None:
        # ── Live working state (mutable, current cycle) ──
        self.pc: int = 0
        self.registers: list[int] = [0] * NUM_REGISTERS
        self.memory: dict[int, int] = {}
        self.memory_size: int = memory_size
        self.cycles: int = 0
        self.halted: bool = False
        self.current_instruction: str = ""
        self.control_signals: dict[str, Any] = {}

        # ── Program output log ──
        # Each entry: {"cycle": int, "type": "register"|"memory"|"string", "value": str}
        self.output_log: list[dict[str, Any]] = []

        # ── Pending READ inputs (pre-supplied by the API caller) ──
        # List of integer values to consume when READ instructions execute.
        self.input_queue: list[int] = []

        # ── Immutable timeline: List[CPUSnapshot] ──
        # Each entry is a frozen snapshot produced by end_cycle().
        self.timeline: list[CPUSnapshot] = []

        # ── Current cycle's event buffer (flushed by end_cycle) ──
        self._current_events: list[Event] = []

    # ------------------------------------------------------------------
    # Cycle management — produces immutable snapshots
    # ------------------------------------------------------------------

    def new_cycle(self) -> int:
        """
        Begin a new clock cycle.

        Auto-flushes any pending events from a prior unfinalised cycle
        so no data is lost.

        Returns:
            The 1-based cycle number that just started.
        """
        # Auto-flush pending events from a prior cycle
        if self._current_events:
            self._commit_snapshot()

        self.cycles += 1
        self._current_events = []
        logger.debug("Cycle %d started (PC=%d)", self.cycles, self.pc)
        return self.cycles

    def add_event(self, event: Event) -> None:
        """Record a hardware event in the current cycle's buffer."""
        self._current_events.append(event)

    def end_cycle(self) -> CPUSnapshot:
        """
        Finalise the current cycle.

        Freezes the current working state into an immutable CPUSnapshot
        and appends it to self.timeline.

        Returns:
            The newly created CPUSnapshot (read-only).
        """
        return self._commit_snapshot()

    def _commit_snapshot(self) -> CPUSnapshot:
        """
        Create an immutable CPUSnapshot from the current working state
        and append it to the timeline.

        This is the core of the immutability model: each call produces
        a new, independent, frozen object. No existing snapshot is ever
        modified.
        """
        snapshot = CPUSnapshot(
            cycle=self.cycles,
            pc=self.pc,
            # Convert mutable list → immutable tuple
            registers=tuple(self.registers),
            # Convert mutable dict → immutable tuple of pairs
            memory=tuple(sorted(self.memory.items())),
            halted=self.halted,
            events=tuple(e.to_dict() for e in self._current_events),
            control_signals=dict(self.control_signals),
            current_instruction=self.current_instruction,
        )
        self.timeline.append(snapshot)
        self._current_events = []
        logger.debug(
            "Snapshot committed: cycle=%d pc=%d halted=%s",
            snapshot.cycle, snapshot.pc, snapshot.halted,
        )
        return snapshot

    # ------------------------------------------------------------------
    # Register helpers
    # ------------------------------------------------------------------

    def read_register(self, index: int) -> int:
        """Read a general-purpose register (0-indexed)."""
        if not 0 <= index < NUM_REGISTERS:
            raise IndexError(f"Register R{index} out of range (0–{NUM_REGISTERS - 1})")
        return self.registers[index]

    def write_register(self, index: int, value: int) -> None:
        """Write a value to a general-purpose register (live working state)."""
        if not 0 <= index < NUM_REGISTERS:
            raise IndexError(f"Register R{index} out of range (0–{NUM_REGISTERS - 1})")
        self.registers[index] = value
        logger.debug("R%d ← %d", index, value)

    # ------------------------------------------------------------------
    # Memory helpers
    # ------------------------------------------------------------------

    def read_memory(self, address: int) -> int:
        """Read a memory cell (defaults to 0 if uninitialised)."""
        if not 0 <= address < self.memory_size:
            raise IndexError(f"Memory address {address} out of range (0–{self.memory_size - 1})")
        return self.memory.get(address, 0)

    def write_memory(self, address: int, value: int) -> None:
        """Write a value to a memory cell (live working state)."""
        if not 0 <= address < self.memory_size:
            raise IndexError(f"Memory address {address} out of range (0–{self.memory_size - 1})")
        self.memory[address] = value
        logger.debug("MEM[%d] ← %d", address, value)

    # ------------------------------------------------------------------
    # Time-travel helpers
    # ------------------------------------------------------------------

    def get_snapshot(self, cycle: int) -> CPUSnapshot | None:
        """
        Retrieve the immutable snapshot for a specific cycle number.

        Enables time-travel debugging: the caller can inspect any past
        state without risk of mutation.

        Returns None if the cycle has not been executed yet.
        """
        # Timeline is 0-indexed; cycle numbers are 1-based
        idx = cycle - 1
        if 0 <= idx < len(self.timeline):
            return self.timeline[idx]
        return None

    def restore_from_snapshot(self, snapshot: CPUSnapshot) -> None:
        """
        Restore the live working state from an immutable snapshot.

        Useful for re-running from a checkpoint. The snapshot itself
        is never modified.
        """
        self.pc = snapshot.pc
        self.registers = list(snapshot.registers)
        self.memory = dict(snapshot.memory)
        self.cycles = snapshot.cycle
        self.halted = snapshot.halted
        self.current_instruction = snapshot.current_instruction
        self.control_signals = dict(snapshot.control_signals)
        self._current_events = []
        logger.info("State restored from snapshot at cycle %d", snapshot.cycle)

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Restore the CPU to its initial power-on state."""
        self.pc = 0
        self.registers = [0] * NUM_REGISTERS
        self.memory.clear()
        self.cycles = 0
        self.timeline.clear()
        self._current_events.clear()
        self.halted = False
        self.current_instruction = ""
        self.control_signals = {}
        self.output_log.clear()
        self.input_queue.clear()
        logger.info("CPU state reset")

    def emit_output(self, entry_type: str, value: str, label: str = "") -> None:
        """Append a program output entry (called by PRINT/PRINT_MEM/PRINT_STR handlers)."""
        self.output_log.append({
            "cycle": self.cycles,
            "type": entry_type,
            "value": value,
            "label": label,
        })

    def consume_input(self) -> int:
        """Pop the next value from the input queue (for READ instruction)."""
        if self.input_queue:
            return self.input_queue.pop(0)
        return 0  # default when no input supplied

    def snapshot(self) -> dict[str, Any]:
        """Return a plain-dict snapshot of the current live working state."""
        return {
            "pc": self.pc,
            "registers": list(self.registers),
            "memory": dict(self.memory),
            "cycles": self.cycles,
            "halted": self.halted,
            "output_log": list(self.output_log),
        }

    def clone(self) -> "CPUState":
        """Deep-copy the entire state including timeline (for forking)."""
        return copy.deepcopy(self)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"CPUState(pc={self.pc}, cycles={self.cycles}, "
            f"regs={self.registers}, halted={self.halted}, "
            f"snapshots={len(self.timeline)})"
        )
