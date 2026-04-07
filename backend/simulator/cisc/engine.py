"""
CISC execution engine — micro-operation decomposition model.

In a CISC architecture, each high-level instruction is internally broken
down into a sequence of **micro-operations** (µ-ops).  Each µ-op consumes
exactly one clock cycle and generates one event.

Example decomposition:
  ADD [100], [200]  →
    µ-op 1:  READ  MEM[100] → temp1       (1 cycle)
    µ-op 2:  READ  MEM[200] → temp2       (1 cycle)
    µ-op 3:  ALU   temp1 + temp2 → result (1 cycle)
    µ-op 4:  WRITE result → MEM[100]      (1 cycle)

This means a single CISC instruction can take 3–4+ cycles depending on
its complexity, which is the key performance difference vs. RISC.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from simulator.core.cpu_state import CPUState
from simulator.core.events import Component, Event
from simulator.core.exceptions import ExecutionError, InvalidInstructionError
from simulator.parser.assembly_parser import Instruction, ParseResult

logger = logging.getLogger(__name__)

MAX_CYCLES = 10_000


# ---------------------------------------------------------------------------
# Micro-operation data class
# ---------------------------------------------------------------------------

@dataclass
class MicroOp:
    """
    Represents a single micro-operation within a CISC instruction.

    Each µ-op maps to one clock cycle and one hardware event.
    """
    component: str          # Component enum value
    action: str
    inputs: list[Any] = field(default_factory=list)
    output: Any = None
    meta: dict[str, Any] = field(default_factory=dict)

    # Callable that performs the actual state mutation (executed at cycle time)
    execute: Any = None     # Callable[[CPUState], Any] | None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def execute_cisc(
    parse_result: ParseResult,
    state: CPUState | None = None,
    *,
    step: bool = False,
) -> CPUState:
    """
    Execute a parsed CISC program to completion (or one instruction in
    step mode).

    Each instruction is first decomposed into micro-operations, then each
    µ-op is executed one-per-cycle.
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

        # Decompose into µ-ops
        micro_ops = _decompose(state, instr, labels)

        # Execute each µ-op as one cycle
        for uop in micro_ops:
            if state.cycles >= MAX_CYCLES:
                raise ExecutionError("Maximum cycle count exceeded during µ-op execution", state.pc)

            state.new_cycle()
            # Run the µ-op's side-effect (if any)
            if uop.execute is not None:
                uop.execute(state)
            # Record the event
            state.add_event(Event(
                component=uop.component,
                action=uop.action,
                inputs=uop.inputs,
                output=uop.output,
                meta={**uop.meta, "instruction": instr.opcode, "micro_op": True},
            ))
            state.end_cycle()

        # Advance PC (unless branch/jump already set it)
        if instr.opcode not in ("BEQ", "JMP"):
            state.pc += 1

        if step:
            break

    return state


# ---------------------------------------------------------------------------
# Micro-operation decomposition for each CISC instruction
# ---------------------------------------------------------------------------

def _decompose(
    state: CPUState,
    instr: Instruction,
    labels: dict[str, int],
) -> list[MicroOp]:
    """Break a single CISC instruction into a list of MicroOps."""
    opcode = instr.opcode
    ops = instr.operands

    if opcode == "ADD":
        return _decompose_alu_mem_mem(state, ops, "ADD", lambda a, b: a + b)
    elif opcode == "SUB":
        return _decompose_alu_mem_mem(state, ops, "SUB", lambda a, b: a - b)
    elif opcode == "MUL":
        return _decompose_alu_mem_mem(state, ops, "MUL", lambda a, b: a * b)
    elif opcode == "MOV":
        return _decompose_mov(state, ops)
    elif opcode == "LOAD":
        return _decompose_load(state, ops)
    elif opcode == "STORE":
        return _decompose_store(state, ops)
    elif opcode == "INC":
        return _decompose_inc_dec(state, ops, "INC", lambda v: v + 1)
    elif opcode == "DEC":
        return _decompose_inc_dec(state, ops, "DEC", lambda v: v - 1)
    elif opcode == "BEQ":
        return _decompose_beq(state, ops, labels)
    elif opcode == "JMP":
        return _decompose_jmp(state, ops, labels)
    elif opcode == "HALT":
        return _decompose_halt(state)
    elif opcode == "NOP":
        return _decompose_nop()
    else:
        raise InvalidInstructionError(f"Unknown CISC opcode '{opcode}'", instr.line_number)


# ---------------------------------------------------------------------------
# ADD [addr1], [addr2]  →  4 µ-ops
# SUB [addr1], [addr2]  →  4 µ-ops
# MUL [addr1], [addr2]  →  4 µ-ops
# ---------------------------------------------------------------------------

def _decompose_alu_mem_mem(
    state: CPUState,
    ops: list[Any],
    op_name: str,
    alu_fn: Any,
) -> list[MicroOp]:
    addr1, addr2 = ops

    # We capture values at decomposition time for event descriptions,
    # but mutations happen via the execute lambda.
    val1 = state.read_memory(addr1)
    val2 = state.read_memory(addr2)
    result = alu_fn(val1, val2)

    return [
        # µ-op 1: Read first operand from memory
        MicroOp(
            component=Component.MEMORY.value,
            action=f"READ MEM[{addr1}]",
            inputs=[addr1],
            output=val1,
            meta={"micro_op_index": 1, "total_micro_ops": 4, "address": addr1},
        ),
        # µ-op 2: Read second operand from memory
        MicroOp(
            component=Component.MEMORY.value,
            action=f"READ MEM[{addr2}]",
            inputs=[addr2],
            output=val2,
            meta={"micro_op_index": 2, "total_micro_ops": 4, "address": addr2},
        ),
        # µ-op 3: ALU operation
        MicroOp(
            component=Component.ALU.value,
            action=f"{op_name} {val1} and {val2}",
            inputs=[val1, val2],
            output=result,
            meta={"micro_op_index": 3, "total_micro_ops": 4, "operation": op_name},
        ),
        # µ-op 4: Write result back to memory
        MicroOp(
            component=Component.MEMORY.value,
            action=f"WRITE MEM[{addr1}] ← {result}",
            inputs=[addr1, result],
            output=result,
            meta={"micro_op_index": 4, "total_micro_ops": 4, "address": addr1},
            execute=lambda s, a=addr1, r=result: s.write_memory(a, r),
        ),
    ]


# ---------------------------------------------------------------------------
# MOV [addr], imm  →  2 µ-ops
# ---------------------------------------------------------------------------

def _decompose_mov(state: CPUState, ops: list[Any]) -> list[MicroOp]:
    addr, imm = ops
    return [
        # µ-op 1: Decode + prepare immediate
        MicroOp(
            component=Component.CONTROL.value,
            action=f"DECODE MOV: immediate {imm} → MEM[{addr}]",
            inputs=[imm, addr],
            output=f"MOV decoded",
            meta={"micro_op_index": 1, "total_micro_ops": 2},
        ),
        # µ-op 2: Write immediate to memory
        MicroOp(
            component=Component.MEMORY.value,
            action=f"WRITE MEM[{addr}] ← {imm}",
            inputs=[addr, imm],
            output=imm,
            meta={"micro_op_index": 2, "total_micro_ops": 2, "address": addr},
            execute=lambda s, a=addr, v=imm: s.write_memory(a, v),
        ),
    ]


# ---------------------------------------------------------------------------
# LOAD Rd, [addr]  →  3 µ-ops
# ---------------------------------------------------------------------------

def _decompose_load(state: CPUState, ops: list[Any]) -> list[MicroOp]:
    rd, addr = ops
    value = state.read_memory(addr)
    return [
        # µ-op 1: Decode
        MicroOp(
            component=Component.CONTROL.value,
            action=f"DECODE LOAD R{rd} ← MEM[{addr}]",
            inputs=[f"R{rd}", addr],
            output="LOAD decoded",
            meta={"micro_op_index": 1, "total_micro_ops": 3},
        ),
        # µ-op 2: Memory read
        MicroOp(
            component=Component.MEMORY.value,
            action=f"READ MEM[{addr}]",
            inputs=[addr],
            output=value,
            meta={"micro_op_index": 2, "total_micro_ops": 3, "address": addr},
        ),
        # µ-op 3: Register write
        MicroOp(
            component=Component.REGISTERS.value,
            action=f"WRITE R{rd} ← {value}",
            inputs=[value],
            output=value,
            meta={"micro_op_index": 3, "total_micro_ops": 3, "register": f"R{rd}"},
            execute=lambda s, r=rd, v=value: s.write_register(r, v),
        ),
    ]


# ---------------------------------------------------------------------------
# STORE [addr], Rs  →  3 µ-ops
# ---------------------------------------------------------------------------

def _decompose_store(state: CPUState, ops: list[Any]) -> list[MicroOp]:
    addr, rs = ops
    value = state.read_register(rs)
    return [
        # µ-op 1: Decode
        MicroOp(
            component=Component.CONTROL.value,
            action=f"DECODE STORE MEM[{addr}] ← R{rs}",
            inputs=[addr, f"R{rs}"],
            output="STORE decoded",
            meta={"micro_op_index": 1, "total_micro_ops": 3},
        ),
        # µ-op 2: Register read
        MicroOp(
            component=Component.REGISTERS.value,
            action=f"READ R{rs}",
            inputs=[f"R{rs}"],
            output=value,
            meta={"micro_op_index": 2, "total_micro_ops": 3, "register": f"R{rs}"},
        ),
        # µ-op 3: Memory write
        MicroOp(
            component=Component.MEMORY.value,
            action=f"WRITE MEM[{addr}] ← {value}",
            inputs=[addr, value],
            output=value,
            meta={"micro_op_index": 3, "total_micro_ops": 3, "address": addr},
            execute=lambda s, a=addr, v=value: s.write_memory(a, v),
        ),
    ]


# ---------------------------------------------------------------------------
# INC [addr]  →  3 µ-ops
# DEC [addr]  →  3 µ-ops
# ---------------------------------------------------------------------------

def _decompose_inc_dec(
    state: CPUState,
    ops: list[Any],
    op_name: str,
    fn: Any,
) -> list[MicroOp]:
    addr = ops[0]
    value = state.read_memory(addr)
    result = fn(value)

    return [
        # µ-op 1: Memory read
        MicroOp(
            component=Component.MEMORY.value,
            action=f"READ MEM[{addr}]",
            inputs=[addr],
            output=value,
            meta={"micro_op_index": 1, "total_micro_ops": 3, "address": addr},
        ),
        # µ-op 2: ALU increment/decrement
        MicroOp(
            component=Component.ALU.value,
            action=f"{op_name} {value} → {result}",
            inputs=[value],
            output=result,
            meta={"micro_op_index": 2, "total_micro_ops": 3, "operation": op_name},
        ),
        # µ-op 3: Memory write-back
        MicroOp(
            component=Component.MEMORY.value,
            action=f"WRITE MEM[{addr}] ← {result}",
            inputs=[addr, result],
            output=result,
            meta={"micro_op_index": 3, "total_micro_ops": 3, "address": addr},
            execute=lambda s, a=addr, r=result: s.write_memory(a, r),
        ),
    ]


# ---------------------------------------------------------------------------
# BEQ [addr1], [addr2], label  →  4 or 5 µ-ops (branch taken/not-taken)
# ---------------------------------------------------------------------------

def _decompose_beq(
    state: CPUState,
    ops: list[Any],
    labels: dict[str, int],
) -> list[MicroOp]:
    addr1, addr2, label = ops
    val1 = state.read_memory(addr1)
    val2 = state.read_memory(addr2)
    taken = val1 == val2

    if label not in labels:
        raise ExecutionError(f"Undefined label '{label}'", state.pc)

    target = labels[label]

    micro_ops = [
        # µ-op 1: Read first operand
        MicroOp(
            component=Component.MEMORY.value,
            action=f"READ MEM[{addr1}]",
            inputs=[addr1],
            output=val1,
            meta={"micro_op_index": 1, "total_micro_ops": 4, "address": addr1},
        ),
        # µ-op 2: Read second operand
        MicroOp(
            component=Component.MEMORY.value,
            action=f"READ MEM[{addr2}]",
            inputs=[addr2],
            output=val2,
            meta={"micro_op_index": 2, "total_micro_ops": 4, "address": addr2},
        ),
        # µ-op 3: ALU comparison
        MicroOp(
            component=Component.ALU.value,
            action=f"COMPARE {val1} == {val2} → {'EQUAL' if taken else 'NOT_EQUAL'}",
            inputs=[val1, val2],
            output=taken,
            meta={"micro_op_index": 3, "total_micro_ops": 4, "comparison": "BEQ"},
        ),
    ]

    if taken:
        # µ-op 4: PC ← target
        def _branch_taken(s: CPUState, t: int = target) -> None:
            s.pc = t

        micro_ops.append(MicroOp(
            component=Component.PC.value,
            action=f"BRANCH TAKEN: PC ← {target} (label '{label}')",
            inputs=[state.pc, label],
            output=target,
            meta={"micro_op_index": 4, "total_micro_ops": 4, "branch_taken": True},
            execute=_branch_taken,
        ))
    else:
        # µ-op 4: PC ← PC + 1 (sequential)
        def _branch_not_taken(s: CPUState) -> None:
            s.pc += 1

        micro_ops.append(MicroOp(
            component=Component.PC.value,
            action=f"BRANCH NOT TAKEN: PC ← {state.pc + 1}",
            inputs=[state.pc],
            output=state.pc + 1,
            meta={"micro_op_index": 4, "total_micro_ops": 4, "branch_taken": False},
            execute=_branch_not_taken,
        ))

    return micro_ops


# ---------------------------------------------------------------------------
# JMP label  →  2 µ-ops
# ---------------------------------------------------------------------------

def _decompose_jmp(
    state: CPUState,
    ops: list[Any],
    labels: dict[str, int],
) -> list[MicroOp]:
    label = ops[0]
    if label not in labels:
        raise ExecutionError(f"Undefined label '{label}'", state.pc)

    target = labels[label]

    def _set_pc(s: CPUState, t: int = target) -> None:
        s.pc = t

    return [
        # µ-op 1: Decode jump
        MicroOp(
            component=Component.CONTROL.value,
            action=f"DECODE JMP → {label}",
            inputs=[label],
            output=target,
            meta={"micro_op_index": 1, "total_micro_ops": 2},
        ),
        # µ-op 2: Set PC
        MicroOp(
            component=Component.PC.value,
            action=f"SET PC ← {target}",
            inputs=[state.pc],
            output=target,
            meta={"micro_op_index": 2, "total_micro_ops": 2},
            execute=_set_pc,
        ),
    ]


# ---------------------------------------------------------------------------
# HALT  →  1 µ-op
# ---------------------------------------------------------------------------

def _decompose_halt(state: CPUState) -> list[MicroOp]:
    def _halt(s: CPUState) -> None:
        s.halted = True

    return [
        MicroOp(
            component=Component.CONTROL.value,
            action="HALT — CPU stopped",
            inputs=[],
            output="HALTED",
            meta={"micro_op_index": 1, "total_micro_ops": 1, "halted": True},
            execute=_halt,
        ),
    ]


# ---------------------------------------------------------------------------
# NOP  →  1 µ-op
# ---------------------------------------------------------------------------

def _decompose_nop() -> list[MicroOp]:
    return [
        MicroOp(
            component=Component.CONTROL.value,
            action="NOP — no operation",
            inputs=[],
            output="No-op",
            meta={"micro_op_index": 1, "total_micro_ops": 1},
        ),
    ]
