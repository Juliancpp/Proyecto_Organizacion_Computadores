"""
CPUState — the mutable state of a simulated processor.

This class is architecture-agnostic.  Both the RISC and CISC engines
operate on a CPUState instance, mutating registers, memory, and the
program counter while appending cycle-level events to the timeline.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from .events import Event

logger = logging.getLogger(__name__)

# Number of general-purpose registers (R0–R7)
NUM_REGISTERS = 8

# Default memory size (number of addressable cells)
DEFAULT_MEMORY_SIZE = 256


class CPUState:
    """
    Encapsulates the complete observable state of a simple CPU.

    Attributes:
        pc:         Program counter — index of the next instruction.
        registers:  General-purpose register file (R0–R7), indexed 0..7.
        memory:     Main memory, modelled as a dict[int, int] for sparse
                    access.  Uninitialised cells default to 0.
        cycles:     Total clock cycles elapsed so far.
        timeline:   Ordered list of cycle records, each containing a list
                    of events that occurred during that cycle.
        halted:     Flag indicating the CPU has finished execution.
    """

    def __init__(self, memory_size: int = DEFAULT_MEMORY_SIZE) -> None:
        self.pc: int = 0
        self.registers: list[int] = [0] * NUM_REGISTERS
        self.memory: dict[int, int] = {}
        self.memory_size: int = memory_size
        self.cycles: int = 0
        self.timeline: list[dict[str, Any]] = []
        self.halted: bool = False

        # Current cycle's event buffer (flushed by end_cycle)
        self._current_events: list[Event] = []

    # ------------------------------------------------------------------
    # Cycle management
    # ------------------------------------------------------------------

    def new_cycle(self) -> int:
        """
        Begin a new clock cycle.

        If there were pending events from a previous call that was never
        finalised with ``end_cycle``, they are flushed automatically so
        no data is lost.

        Returns:
            The 1-based cycle number that just started.
        """
        # Auto-flush any pending events from a prior cycle
        if self._current_events:
            self._flush_cycle()

        self.cycles += 1
        self._current_events = []
        logger.debug("Cycle %d started (PC=%d)", self.cycles, self.pc)
        return self.cycles

    def add_event(self, event: Event) -> None:
        """Record a hardware event in the current cycle."""
        self._current_events.append(event)

    def end_cycle(self) -> None:
        """Finalise the current cycle and commit its events to the timeline."""
        self._flush_cycle()

    def _flush_cycle(self) -> None:
        """Write pending events into a cycle record on the timeline."""
        if not self._current_events:
            return
        self.timeline.append({
            "cycle": self.cycles,
            "events": [e.to_dict() for e in self._current_events],
        })
        self._current_events = []

    # ------------------------------------------------------------------
    # Register helpers
    # ------------------------------------------------------------------

    def read_register(self, index: int) -> int:
        """Read a general-purpose register (0-indexed)."""
        if not 0 <= index < NUM_REGISTERS:
            raise IndexError(f"Register R{index} out of range (0–{NUM_REGISTERS - 1})")
        return self.registers[index]

    def write_register(self, index: int, value: int) -> None:
        """Write a value to a general-purpose register."""
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
        """Write a value to a memory cell."""
        if not 0 <= address < self.memory_size:
            raise IndexError(f"Memory address {address} out of range (0–{self.memory_size - 1})")
        self.memory[address] = value
        logger.debug("MEM[%d] ← %d", address, value)

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
        logger.info("CPU state reset")

    def snapshot(self) -> dict[str, Any]:
        """Return a read-only snapshot of the current CPU state."""
        return {
            "pc": self.pc,
            "registers": list(self.registers),
            "memory": dict(self.memory),
            "cycles": self.cycles,
            "halted": self.halted,
        }

    def clone(self) -> "CPUState":
        """Deep-copy the entire state (useful for step-by-step replay)."""
        return copy.deepcopy(self)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"CPUState(pc={self.pc}, cycles={self.cycles}, "
            f"regs={self.registers}, halted={self.halted})"
        )
