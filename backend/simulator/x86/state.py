"""
x86-64 CPU state model.

Provides:
  - 16 named 64-bit general-purpose registers (rax–r15)
  - 32-bit aliases (eax, ebx, …) that read/write the lower 32 bits
  - FLAGS register with ZF, SF, OF, CF
  - Byte-addressable memory with dword (32-bit) read/write helpers
  - Integration with the core CPUState for timeline/snapshot support

Memory model:
  The x86-64 state uses a flat byte-addressable memory (bytearray).
  The .data segment is loaded at a configurable base address (default 0x1000).
  Dwords are stored in little-endian format.
"""

from __future__ import annotations

import struct
import logging
from typing import Any

from simulator.core.cpu_state import CPUState
from simulator.core.events import Event

logger = logging.getLogger(__name__)

# Default memory size: 64 KB
DEFAULT_X86_MEMORY_SIZE = 65536

# Map 32-bit alias → 64-bit parent register
_REG_32_TO_64: dict[str, str] = {
    "eax": "rax", "ebx": "rbx", "ecx": "rcx", "edx": "rdx",
    "esi": "rsi", "edi": "rdi", "esp": "rsp", "ebp": "rbp",
    "r8d": "r8", "r9d": "r9", "r10d": "r10", "r11d": "r11",
    "r12d": "r12", "r13d": "r13", "r14d": "r14", "r15d": "r15",
}

_GP_REGS_32 = frozenset(_REG_32_TO_64.keys())


class X86State:
    """
    x86-64 processor state.

    Wraps the core CPUState for timeline/event recording while providing
    x86-64-specific register and memory semantics.
    """

    def __init__(self, memory_size: int = DEFAULT_X86_MEMORY_SIZE) -> None:
        # ── x86-64 register file ──
        self.registers: dict[str, int] = {
            "rax": 0, "rbx": 0, "rcx": 0, "rdx": 0,
            "rsi": 0, "rdi": 0, "rsp": 0, "rbp": 0,
            "r8": 0, "r9": 0, "r10": 0, "r11": 0,
            "r12": 0, "r13": 0, "r14": 0, "r15": 0,
        }

        # ── FLAGS ──
        self.flags: dict[str, bool] = {
            "ZF": False,   # Zero Flag
            "SF": False,   # Sign Flag
            "OF": False,   # Overflow Flag
            "CF": False,   # Carry Flag
        }

        # ── Byte-addressable memory ──
        self.memory = bytearray(memory_size)
        self.memory_size = memory_size

        # ── Execution state ──
        self.pc: int = 0
        self.halted: bool = False
        self.cycles: int = 0

        # ── Core CPUState for timeline integration ──
        self.core_state = CPUState(memory_size=256)
        self.core_state.memory_size = 256  # keep core state small

        # ── Program output ──
        self.output_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Register access
    # ------------------------------------------------------------------

    def read_reg(self, name: str) -> int:
        """Read a register by name (supports both 64-bit and 32-bit aliases)."""
        lower = name.lower()

        # 32-bit alias
        if lower in _GP_REGS_32:
            parent = _REG_32_TO_64[lower]
            return self.registers[parent] & 0xFFFFFFFF

        # 64-bit register
        if lower in self.registers:
            return self.registers[lower]

        raise KeyError(f"Unknown register '{name}'")

    def write_reg(self, name: str, value: int) -> None:
        """
        Write a value to a register.

        For 32-bit aliases (eax, ebx, …): per x86-64 convention, writing
        a 32-bit register zero-extends the result into the full 64-bit
        parent register.
        """
        lower = name.lower()

        # 32-bit alias — zero-extend into 64-bit parent
        if lower in _GP_REGS_32:
            parent = _REG_32_TO_64[lower]
            self.registers[parent] = value & 0xFFFFFFFF
            logger.debug("%s ← %d (→ %s)", lower, value & 0xFFFFFFFF, parent)
            return

        # 64-bit register
        if lower in self.registers:
            self.registers[lower] = value
            logger.debug("%s ← %d", lower, value)
            return

        raise KeyError(f"Unknown register '{name}'")

    def get_parent_reg(self, name: str) -> str:
        """Return the 64-bit parent register name for any register alias."""
        lower = name.lower()
        if lower in _GP_REGS_32:
            return _REG_32_TO_64[lower]
        if lower in self.registers:
            return lower
        raise KeyError(f"Unknown register '{name}'")

    def is_32bit_reg(self, name: str) -> bool:
        """Check if a register name is a 32-bit alias."""
        return name.lower() in _GP_REGS_32

    # ------------------------------------------------------------------
    # Memory access (byte-addressable, little-endian)
    # ------------------------------------------------------------------

    def read_dword(self, address: int) -> int:
        """Read a 32-bit signed dword from memory at the given byte address."""
        if address < 0 or address + 4 > self.memory_size:
            raise IndexError(f"Memory read out of bounds: address {address:#x}")
        return struct.unpack_from("<i", self.memory, address)[0]

    def write_dword(self, address: int, value: int) -> None:
        """Write a 32-bit signed dword to memory at the given byte address."""
        if address < 0 or address + 4 > self.memory_size:
            raise IndexError(f"Memory write out of bounds: address {address:#x}")
        # Truncate to 32-bit signed range
        value = value & 0xFFFFFFFF
        if value >= 0x80000000:
            value -= 0x100000000
        struct.pack_into("<i", self.memory, address, value)
        logger.debug("MEM[%#x] ← %d (dword)", address, value)

    def read_qword(self, address: int) -> int:
        """Read a 64-bit value from memory."""
        if address < 0 or address + 8 > self.memory_size:
            raise IndexError(f"Memory read out of bounds: address {address:#x}")
        return struct.unpack_from("<q", self.memory, address)[0]

    def write_qword(self, address: int, value: int) -> None:
        """Write a 64-bit value to memory."""
        if address < 0 or address + 8 > self.memory_size:
            raise IndexError(f"Memory write out of bounds: address {address:#x}")
        struct.pack_into("<q", self.memory, address, value)

    def load_data_segment(self, base_address: int, data: bytes) -> None:
        """Load the .data segment into memory at the given base address."""
        end = base_address + len(data)
        if end > self.memory_size:
            raise IndexError(
                f"Data segment exceeds memory: {base_address:#x}+{len(data)} > {self.memory_size:#x}"
            )
        self.memory[base_address:end] = data
        logger.info(
            "Loaded %d bytes of .data at %#x–%#x",
            len(data), base_address, end - 1,
        )

    # ------------------------------------------------------------------
    # FLAGS helpers
    # ------------------------------------------------------------------

    def update_flags_sub(self, a: int, b: int, result: int, bits: int = 64) -> None:
        """
        Update FLAGS after a subtraction (CMP, SUB, DEC).

        For CMP a, b:  computes a - b and sets flags.
        """
        mask = (1 << bits) - 1
        sign_bit = 1 << (bits - 1)

        result_masked = result & mask

        self.flags["ZF"] = (result_masked == 0)
        self.flags["SF"] = bool(result_masked & sign_bit)

        # Overflow: sign of a differs from sign of result, AND sign of a differs from sign of b
        a_sign = bool(a & sign_bit)
        b_sign = bool(b & sign_bit)
        r_sign = bool(result_masked & sign_bit)
        self.flags["OF"] = (a_sign != b_sign) and (a_sign != r_sign)

        # Carry: unsigned borrow
        self.flags["CF"] = (a & mask) < (b & mask)

    def update_flags_add(self, a: int, b: int, result: int, bits: int = 64) -> None:
        """Update FLAGS after an addition (ADD, INC)."""
        mask = (1 << bits) - 1
        sign_bit = 1 << (bits - 1)

        result_masked = result & mask

        self.flags["ZF"] = (result_masked == 0)
        self.flags["SF"] = bool(result_masked & sign_bit)

        a_sign = bool(a & sign_bit)
        b_sign = bool(b & sign_bit)
        r_sign = bool(result_masked & sign_bit)
        self.flags["OF"] = (a_sign == b_sign) and (a_sign != r_sign)

        self.flags["CF"] = (result & mask) < (a & mask)  # unsigned carry

    def update_flags_logic(self, result: int, bits: int = 64) -> None:
        """Update FLAGS after a logical operation (XOR, AND, OR)."""
        mask = (1 << bits) - 1
        sign_bit = 1 << (bits - 1)

        result_masked = result & mask

        self.flags["ZF"] = (result_masked == 0)
        self.flags["SF"] = bool(result_masked & sign_bit)
        self.flags["OF"] = False
        self.flags["CF"] = False

    # ------------------------------------------------------------------
    # Cycle management (delegates to core_state)
    # ------------------------------------------------------------------

    def new_cycle(self, current_instruction: str = "") -> int:
        """Begin a new clock cycle. Sync PC and instruction to core_state."""
        self.cycles += 1
        self.core_state.cycles = self.cycles
        self.core_state.pc = self.pc  # SYNC PC!
        self.core_state.current_instruction = current_instruction
        return self.core_state.new_cycle()

    def add_event(self, event: Event) -> None:
        """Record an event in the current cycle."""
        self.core_state.add_event(event)

    def end_cycle(self) -> Any:
        """Finalise the current cycle."""
        return self.core_state.end_cycle()

    # ------------------------------------------------------------------
    # State inspection
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a plain-dict snapshot of the current state."""
        return {
            "pc": self.pc,
            "registers": dict(self.registers),
            "flags": dict(self.flags),
            "halted": self.halted,
            "cycles": self.cycles,
            "output_log": list(self.output_log),
        }

    def reset(self) -> None:
        """Reset to initial state."""
        for reg in self.registers:
            self.registers[reg] = 0
        for flag in self.flags:
            self.flags[flag] = False
        self.memory = bytearray(self.memory_size)
        self.pc = 0
        self.halted = False
        self.cycles = 0
        self.core_state.reset()
        self.output_log.clear()

    def __repr__(self) -> str:
        return (
            f"X86State(pc={self.pc}, cycles={self.cycles}, "
            f"halted={self.halted}, flags={self.flags})"
        )
