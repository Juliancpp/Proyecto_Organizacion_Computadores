"""
RISC execution engine — single-issue, fixed-cycle-cost model.

Design:
  - Each instruction consumes a fixed, deterministic number of cycles.
  - Every cycle produces one or more Event objects describing hardware activity.
  - The engine operates on a shared CPUState and never touches Django.

Cycle costs:
  LOAD       → 2 cycles  (address bus + data read)
  STORE      → 2 cycles  (address bus + data write)
  ADD / SUB  → 1 cycle   (ALU)
  MOV        → 1 cycle   (register write)
  BEQ / BNE  → 2 cycles  (comparison + PC update; +2 penalty on misprediction)
  JMP        → 2 cycles  (PC reload + pipeline flush)
  NOP        → 1 cycle
  HALT       → 1 cycle
"""

from __future__ import annotations

import logging
from typing import Any

from simulator.core.cpu_state import CPUState
from simulator.core.events import Component, Event
from simulator.core.exceptions import ExecutionError, InvalidInstructionError
from simulator.parser.assembly_parser import Instruction, ParseResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cycle cost table
# ---------------------------------------------------------------------------

CYCLE_COSTS: dict[str, int] = {
    "LOAD":      2,
    "STORE":     2,
    "ADD":       1,
    "SUB":       1,
    "MOV":       1,
    "BEQ":       2,
    "BNE":       2,
    "JMP":       2,
    "NOP":       1,
    "HALT":      1,
    "PRINT":     1,
    "PRINT_MEM": 1,
    "PRINT_STR": 1,
    "READ":      1,
}

# Extra penalty cycles added when a branch is mispredicted
MISPREDICTION_PENALTY = 2

# Maximum cycles to prevent infinite-loop hang
MAX_CYCLES = 10_000


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def execute_risc(
    parse_result: ParseResult,
    state: CPUState | None = None,
    *,
    step: bool = False,
) -> CPUState:
    """
    Execute a parsed RISC program to completion (or one instruction in
    step mode).

    Args:
        parse_result:  Output of ``parse_risc()``.
        state:         Optional pre-existing CPU state to continue from.
                       A fresh state is created when *None*.
        step:          If *True*, execute only the next instruction and return.

    Returns:
        The mutated CPUState after execution.
    """
    instructions = parse_result.instructions
    labels = parse_result.labels

    if state is None:
        state = CPUState()

    if not instructions:
        return state

    while not state.halted and state.pc < len(instructions):
        if state.cycles >= MAX_CYCLES:
            raise ExecutionError("Maximum cycle count exceeded (infinite loop?)", state.pc)

        instr = instructions[state.pc]
        _execute_instruction(state, instr, instructions, labels)

        if step:
            break

    return state


# ---------------------------------------------------------------------------
# Per-instruction execution
# ---------------------------------------------------------------------------

def _execute_instruction(
    state: CPUState,
    instr: Instruction,
    instructions: list[Instruction],
    labels: dict[str, int],
) -> None:
    """Dispatch and execute a single RISC instruction, generating events."""
    opcode = instr.opcode
    ops = instr.operands

    if opcode == "LOAD":
        _exec_load(state, ops)
    elif opcode == "STORE":
        _exec_store(state, ops)
    elif opcode == "ADD":
        _exec_add(state, ops)
    elif opcode == "SUB":
        _exec_sub(state, ops)
    elif opcode == "MUL":
        _exec_mul(state, ops)
    elif opcode == "MOV":
        _exec_mov(state, ops)
    elif opcode == "BEQ":
        _exec_beq(state, ops, labels)
        return  # PC already updated by branch logic
    elif opcode == "BNE":
        _exec_bne(state, ops, labels)
        return
    elif opcode == "JMP":
        _exec_jmp(state, ops, labels)
        return
    elif opcode == "NOP":
        _exec_nop(state)
    elif opcode == "HALT":
        _exec_halt(state)
        return
    elif opcode == "PRINT":
        _exec_print(state, ops)
    elif opcode == "PRINT_MEM":
        _exec_print_mem(state, ops)
    elif opcode == "PRINT_STR":
        _exec_print_str(state, ops)
    elif opcode == "READ":
        _exec_read(state, ops)
    else:
        raise InvalidInstructionError(f"Unknown RISC opcode '{opcode}'", instr.line_number)

    # Advance PC for non-branch instructions
    state.pc += 1


# ---------------------------------------------------------------------------
# LOAD Rd, addr  →  2 cycles
# ---------------------------------------------------------------------------

def _exec_load(state: CPUState, ops: list[Any]) -> None:
    rd, addr = ops

    # Cycle 1: Address bus + memory read request
    state.new_cycle()
    state.add_event(Event(
        Component.CONTROL, "DECODE instruction LOAD",
        inputs=[f"R{rd}", addr], output="LOAD decoded",
    ))
    state.add_event(Event(
        Component.BUS, "Send address to memory bus",
        inputs=[addr], output=f"Address {addr} placed on bus",
    ))
    state.add_event(Event(
        Component.PC, "Increment PC",
        inputs=[state.pc], output=state.pc + 1,
    ))
    state.end_cycle()

    # Cycle 2: Data arrives from memory, written to register
    state.new_cycle()
    value = state.read_memory(addr)
    state.add_event(Event(
        Component.MEMORY, "READ data from memory",
        inputs=[addr], output=value,
        meta={"address": addr, "value": value},
    ))
    state.add_event(Event(
        Component.REGISTERS, f"WRITE R{rd}",
        inputs=[value], output=value,
        meta={"register": f"R{rd}"},
    ))
    state.write_register(rd, value)
    state.end_cycle()


# ---------------------------------------------------------------------------
# STORE Rs, addr  →  2 cycles
# ---------------------------------------------------------------------------

def _exec_store(state: CPUState, ops: list[Any]) -> None:
    rs, addr = ops
    value = state.read_register(rs)

    # Cycle 1: Decode + address bus
    state.new_cycle()
    state.add_event(Event(
        Component.CONTROL, "DECODE instruction STORE",
        inputs=[f"R{rs}", addr], output="STORE decoded",
    ))
    state.add_event(Event(
        Component.REGISTERS, f"READ R{rs}",
        inputs=[f"R{rs}"], output=value,
    ))
    state.add_event(Event(
        Component.BUS, "Send address to memory bus",
        inputs=[addr], output=f"Address {addr} placed on bus",
    ))
    state.end_cycle()

    # Cycle 2: Write data to memory
    state.new_cycle()
    state.add_event(Event(
        Component.BUS, "Send data to memory bus",
        inputs=[value], output=f"Data {value} sent",
    ))
    state.add_event(Event(
        Component.MEMORY, "WRITE data to memory",
        inputs=[addr, value], output=value,
        meta={"address": addr, "value": value},
    ))
    state.write_memory(addr, value)
    state.end_cycle()


# ---------------------------------------------------------------------------
# ADD Rd, Rs1, Rs2  →  1 cycle
# ---------------------------------------------------------------------------

def _exec_add(state: CPUState, ops: list[Any]) -> None:
    rd, rs1, rs2 = ops
    val1 = state.read_register(rs1)
    val2 = state.read_register(rs2)
    result = val1 + val2

    state.new_cycle()
    state.add_event(Event(
        Component.CONTROL, "DECODE instruction ADD",
        inputs=[f"R{rd}", f"R{rs1}", f"R{rs2}"], output="ADD decoded",
    ))
    state.add_event(Event(
        Component.REGISTERS, f"READ R{rs1}, R{rs2}",
        inputs=[f"R{rs1}", f"R{rs2}"], output=[val1, val2],
    ))
    state.add_event(Event(
        Component.ALU, "ADD operation",
        inputs=[val1, val2], output=result,
        meta={"operation": "ADD"},
    ))
    state.add_event(Event(
        Component.REGISTERS, f"WRITE R{rd}",
        inputs=[result], output=result,
        meta={"register": f"R{rd}"},
    ))
    state.write_register(rd, result)
    state.end_cycle()


# ---------------------------------------------------------------------------
# SUB Rd, Rs1, Rs2  →  1 cycle
# ---------------------------------------------------------------------------

def _exec_sub(state: CPUState, ops: list[Any]) -> None:
    rd, rs1, rs2 = ops
    val1 = state.read_register(rs1)
    val2 = state.read_register(rs2)
    result = val1 - val2

    state.new_cycle()
    state.add_event(Event(
        Component.CONTROL, "DECODE instruction SUB",
        inputs=[f"R{rd}", f"R{rs1}", f"R{rs2}"], output="SUB decoded",
    ))
    state.add_event(Event(
        Component.REGISTERS, f"READ R{rs1}, R{rs2}",
        inputs=[f"R{rs1}", f"R{rs2}"], output=[val1, val2],
    ))
    state.add_event(Event(
        Component.ALU, "SUB operation",
        inputs=[val1, val2], output=result,
        meta={"operation": "SUB"},
    ))
    state.add_event(Event(
        Component.REGISTERS, f"WRITE R{rd}",
        inputs=[result], output=result,
        meta={"register": f"R{rd}"},
    ))
    state.write_register(rd, result)
    state.end_cycle()


# ---------------------------------------------------------------------------
# MUL Rd, Rs1, Rs2  →  3 cycles  (multi-cycle ALU op)
# ---------------------------------------------------------------------------

def _exec_mul(state: CPUState, ops: list[Any]) -> None:
    rd, rs1, rs2 = ops
    val1 = state.read_register(rs1)
    val2 = state.read_register(rs2)
    result = val1 * val2

    # Cycle 1: decode + read operands
    state.new_cycle()
    state.add_event(Event(
        Component.CONTROL, "DECODE instruction MUL",
        inputs=[f"R{rd}", f"R{rs1}", f"R{rs2}"], output="MUL decoded",
    ))
    state.add_event(Event(
        Component.REGISTERS, f"READ R{rs1}, R{rs2}",
        inputs=[f"R{rs1}", f"R{rs2}"], output=[val1, val2],
    ))
    state.end_cycle()

    # Cycle 2: multiply (multi-cycle ALU)
    state.new_cycle()
    state.add_event(Event(
        Component.ALU, "MUL operation (multi-cycle)",
        inputs=[val1, val2], output=result,
        meta={"operation": "MUL"},
    ))
    state.end_cycle()

    # Cycle 3: writeback
    state.new_cycle()
    state.add_event(Event(
        Component.REGISTERS, f"WRITE R{rd}",
        inputs=[result], output=result,
        meta={"register": f"R{rd}"},
    ))
    state.write_register(rd, result)
    state.end_cycle()


# ---------------------------------------------------------------------------
# MOV Rd, imm  →  1 cycle
# ---------------------------------------------------------------------------

def _exec_mov(state: CPUState, ops: list[Any]) -> None:
    rd, imm = ops

    state.new_cycle()
    state.add_event(Event(
        Component.CONTROL, "DECODE instruction MOV",
        inputs=[f"R{rd}", imm], output="MOV decoded",
    ))
    state.add_event(Event(
        Component.REGISTERS, f"WRITE R{rd} ← {imm}",
        inputs=[imm], output=imm,
        meta={"register": f"R{rd}", "immediate": imm},
    ))
    state.write_register(rd, imm)
    state.end_cycle()


# ---------------------------------------------------------------------------
# BEQ Rs1, Rs2, label  →  2 cycles (+2 misprediction penalty)
# ---------------------------------------------------------------------------

def _exec_beq(state: CPUState, ops: list[Any], labels: dict[str, int]) -> None:
    rs1_idx, rs2_idx, label = ops
    val1 = state.read_register(rs1_idx)
    val2 = state.read_register(rs2_idx)

    if label not in labels:
        raise ExecutionError(f"Undefined label '{label}'", state.pc)

    taken = val1 == val2

    # Cycle 1: Decode + comparison
    state.new_cycle()
    state.add_event(Event(
        Component.CONTROL, "DECODE instruction BEQ",
        inputs=[f"R{rs1_idx}", f"R{rs2_idx}", label], output="BEQ decoded",
    ))
    state.add_event(Event(
        Component.REGISTERS, f"READ R{rs1_idx}, R{rs2_idx}",
        inputs=[f"R{rs1_idx}", f"R{rs2_idx}"], output=[val1, val2],
    ))
    state.add_event(Event(
        Component.ALU, "COMPARE (equal?)",
        inputs=[val1, val2], output=taken,
        meta={"comparison": "BEQ", "result": "EQUAL" if taken else "NOT_EQUAL"},
    ))
    state.end_cycle()

    # Cycle 2: PC update
    state.new_cycle()
    if taken:
        target = labels[label]
        state.add_event(Event(
            Component.CONTROL, f"Branch TAKEN → {label} (index {target})",
            inputs=[label], output=target,
            meta={"branch_taken": True},
        ))
        state.add_event(Event(
            Component.PC, f"SET PC ← {target}",
            inputs=[state.pc], output=target,
        ))
        state.pc = target
    else:
        state.add_event(Event(
            Component.CONTROL, "Branch NOT TAKEN — continue sequential",
            inputs=[label], output=state.pc + 1,
            meta={"branch_taken": False},
        ))
        state.add_event(Event(
            Component.PC, f"INCREMENT PC ← {state.pc + 1}",
            inputs=[state.pc], output=state.pc + 1,
        ))

        # Misprediction penalty: the simple static predictor assumes taken,
        # so a not-taken outcome incurs a flush penalty.
        state.add_event(Event(
            Component.CONTROL, "MISPREDICTION PENALTY — pipeline flush",
            inputs=[], output=f"+{MISPREDICTION_PENALTY} stall cycles",
            meta={"penalty_cycles": MISPREDICTION_PENALTY},
        ))
        state.pc += 1
    state.end_cycle()

    # Misprediction stall cycles (only when branch NOT taken)
    if not taken:
        for i in range(MISPREDICTION_PENALTY):
            state.new_cycle()
            state.add_event(Event(
                Component.CONTROL, f"Pipeline stall cycle {i + 1}/{MISPREDICTION_PENALTY}",
                inputs=[], output="STALL",
                meta={"stall": True, "reason": "branch_misprediction"},
            ))
            state.end_cycle()


# ---------------------------------------------------------------------------
# BNE Rs1, Rs2, label  →  2 cycles (+2 misprediction penalty if equal)
# ---------------------------------------------------------------------------

def _exec_bne(state: CPUState, ops: list[Any], labels: dict[str, int]) -> None:
    rs1_idx, rs2_idx, label = ops
    val1 = state.read_register(rs1_idx)
    val2 = state.read_register(rs2_idx)

    if label not in labels:
        raise ExecutionError(f"Undefined label '{label}'", state.pc)

    taken = val1 != val2

    # Cycle 1: Decode + comparison
    state.new_cycle()
    state.add_event(Event(
        Component.CONTROL, "DECODE instruction BNE",
        inputs=[f"R{rs1_idx}", f"R{rs2_idx}", label], output="BNE decoded",
    ))
    state.add_event(Event(
        Component.REGISTERS, f"READ R{rs1_idx}, R{rs2_idx}",
        inputs=[f"R{rs1_idx}", f"R{rs2_idx}"], output=[val1, val2],
    ))
    state.add_event(Event(
        Component.ALU, "COMPARE (not equal?)",
        inputs=[val1, val2], output=taken,
        meta={"comparison": "BNE", "result": "NOT_EQUAL" if taken else "EQUAL"},
    ))
    state.end_cycle()

    # Cycle 2: PC update
    state.new_cycle()
    if taken:
        target = labels[label]
        state.add_event(Event(
            Component.CONTROL, f"Branch TAKEN → {label} (index {target})",
            inputs=[label], output=target,
            meta={"branch_taken": True},
        ))
        state.add_event(Event(
            Component.PC, f"SET PC ← {target}",
            inputs=[state.pc], output=target,
        ))
        state.pc = target
    else:
        state.add_event(Event(
            Component.CONTROL, "Branch NOT TAKEN — continue sequential",
            inputs=[label], output=state.pc + 1,
            meta={"branch_taken": False},
        ))
        state.add_event(Event(
            Component.PC, f"INCREMENT PC ← {state.pc + 1}",
            inputs=[state.pc], output=state.pc + 1,
        ))
        state.add_event(Event(
            Component.CONTROL, "MISPREDICTION PENALTY — pipeline flush",
            inputs=[], output=f"+{MISPREDICTION_PENALTY} stall cycles",
            meta={"penalty_cycles": MISPREDICTION_PENALTY},
        ))
        state.pc += 1
    state.end_cycle()

    if not taken:
        for i in range(MISPREDICTION_PENALTY):
            state.new_cycle()
            state.add_event(Event(
                Component.CONTROL, f"Pipeline stall cycle {i + 1}/{MISPREDICTION_PENALTY}",
                inputs=[], output="STALL",
                meta={"stall": True, "reason": "branch_misprediction"},
            ))
            state.end_cycle()


# ---------------------------------------------------------------------------
# JMP label  →  2 cycles
# ---------------------------------------------------------------------------

def _exec_jmp(state: CPUState, ops: list[Any], labels: dict[str, int]) -> None:
    label = ops[0]
    if label not in labels:
        raise ExecutionError(f"Undefined label '{label}'", state.pc)

    target = labels[label]

    # Cycle 1: Decode + resolve target
    state.new_cycle()
    state.add_event(Event(
        Component.CONTROL, "DECODE instruction JMP",
        inputs=[label], output=f"Target index = {target}",
    ))
    state.end_cycle()

    # Cycle 2: PC reload
    state.new_cycle()
    state.add_event(Event(
        Component.PC, f"SET PC ← {target} (label '{label}')",
        inputs=[state.pc], output=target,
    ))
    state.add_event(Event(
        Component.CONTROL, "Pipeline flush (unconditional jump)",
        inputs=[], output="Flush",
    ))
    state.pc = target
    state.end_cycle()


# ---------------------------------------------------------------------------
# NOP  →  1 cycle
# ---------------------------------------------------------------------------

def _exec_nop(state: CPUState) -> None:
    state.new_cycle()
    state.add_event(Event(
        Component.CONTROL, "DECODE instruction NOP",
        inputs=[], output="NOP decoded",
    ))
    state.add_event(Event(
        Component.CONTROL, "NOP — no operation",
        inputs=[], output="No-op",
    ))
    state.end_cycle()


# ---------------------------------------------------------------------------
# HALT  →  1 cycle
# ---------------------------------------------------------------------------

def _exec_halt(state: CPUState) -> None:
    state.new_cycle()
    state.add_event(Event(
        Component.CONTROL, "DECODE instruction HALT",
        inputs=[], output="HALT decoded",
    ))
    state.add_event(Event(
        Component.CONTROL, "HALT — CPU halted",
        inputs=[], output="HALTED",
        meta={"halted": True},
    ))
    state.halted = True
    state.end_cycle()


# ---------------------------------------------------------------------------
# PRINT Rx  →  1 cycle
# ---------------------------------------------------------------------------

def _exec_print(state: CPUState, ops: list[Any]) -> None:
    rd = ops[0]
    value = state.read_register(rd)
    state.new_cycle()
    state.add_event(Event(
        Component.CONTROL, f"PRINT R{rd} = {value}",
        inputs=[f"R{rd}"], output=str(value),
        meta={"output": True, "output_type": "register"},
    ))
    state.emit_output("register", str(value), label=f"R{rd}")
    state.end_cycle()


# ---------------------------------------------------------------------------
# PRINT_MEM addr  →  1 cycle
# ---------------------------------------------------------------------------

def _exec_print_mem(state: CPUState, ops: list[Any]) -> None:
    addr = ops[0]
    value = state.read_memory(addr)
    state.new_cycle()
    state.add_event(Event(
        Component.MEMORY, f"PRINT_MEM [{addr}] = {value}",
        inputs=[addr], output=str(value),
        meta={"output": True, "output_type": "memory", "address": addr},
    ))
    state.emit_output("memory", str(value), label=f"MEM[{addr}]")
    state.end_cycle()


# ---------------------------------------------------------------------------
# PRINT_STR "text"  →  1 cycle
# ---------------------------------------------------------------------------

def _exec_print_str(state: CPUState, ops: list[Any]) -> None:
    text = ops[0]
    state.new_cycle()
    state.add_event(Event(
        Component.CONTROL, f'PRINT_STR "{text}"',
        inputs=[], output=text,
        meta={"output": True, "output_type": "string"},
    ))
    state.emit_output("string", text)
    state.end_cycle()


# ---------------------------------------------------------------------------
# READ Rx  →  1 cycle
# ---------------------------------------------------------------------------

def _exec_read(state: CPUState, ops: list[Any]) -> None:
    rd = ops[0]
    value = state.consume_input()
    state.new_cycle()
    state.add_event(Event(
        Component.REGISTERS, f"READ input → R{rd} = {value}",
        inputs=["stdin"], output=value,
        meta={"input": True, "register": f"R{rd}"},
    ))
    state.write_register(rd, value)
    state.end_cycle()
