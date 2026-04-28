"""
x86-64 direct execution engine.

Interprets parsed x86-64 instructions using an X86State, supporting the
instruction set needed for real programs (bubble sort, etc.):

  mov, dec, inc, cmp, jle, jl, je, jnz, jmp, jne, jg, jge,
  xor, add, sub, and, or, not, neg, push, pop, syscall, nop, hlt

Control flow uses FLAGS (ZF, SF, OF, CF) set by cmp/sub/add/inc/dec/xor.
Memory operands are resolved at runtime with full addressing support:
  [base_symbol + index_reg*scale + displacement]

The engine generates Event objects per cycle for timeline visualization.
"""

from __future__ import annotations

import logging
from typing import Any

from simulator.core.events import Component, Event
from simulator.core.exceptions import ExecutionError, InvalidInstructionError
from simulator.x86.parser import (
    MemoryOperand,
    X86Instruction,
    X86ParseResult,
    DataSymbol,
    _REG_32_TO_64,
    _GP_REGS_32,
)
from simulator.x86.state import X86State

logger = logging.getLogger(__name__)

MAX_CYCLES = 100_000


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def execute_x86(
    parse_result: X86ParseResult,
    state: X86State | None = None,
    *,
    step: bool = False,
) -> X86State:
    """
    Execute a parsed x86-64 program.

    Args:
        parse_result: Output of parse_x86().
        state:        Optional pre-existing state. A fresh one is created if None.
        step:         If True, execute only one instruction and return.

    Returns:
        The X86State after execution.
    """
    instructions = parse_result.instructions
    labels = parse_result.labels
    data_symbols = parse_result.data_symbols
    constants = parse_result.constants

    if state is None:
        state = X86State()

    # Load .data segment into memory
    if parse_result.data_segment:
        state.load_data_segment(parse_result.data_base_address, parse_result.data_segment)

    if not instructions:
        return state

    # Start at _start label if present, otherwise at instruction 0
    if "_start" in labels and state.pc == 0:
        state.pc = labels["_start"]

    while not state.halted and 0 <= state.pc < len(instructions):
        if state.cycles >= MAX_CYCLES:
            raise ExecutionError("Maximum cycle count exceeded (infinite loop?)", state.pc)

        instr = instructions[state.pc]
        _execute_instruction(state, instr, labels, data_symbols, constants)

        if step:
            break

    return state


def read_array_from_memory(
    state: X86State,
    symbol: DataSymbol,
) -> list[int]:
    """Read a dword array from memory given its DataSymbol."""
    count = symbol.size // 4
    result = []
    for i in range(count):
        addr = symbol.address + i * 4
        result.append(state.read_dword(addr))
    return result


# ---------------------------------------------------------------------------
# Instruction dispatch
# ---------------------------------------------------------------------------

def _execute_instruction(
    state: X86State,
    instr: X86Instruction,
    labels: dict[str, int],
    data_symbols: dict[str, DataSymbol],
    constants: dict[str, int],
) -> None:
    """Dispatch and execute a single x86-64 instruction."""
    opcode = instr.opcode
    ops = instr.operands

    # Record cycle with current instruction
    state.new_cycle(instr.raw)

    try:
        if opcode == "mov":
            _exec_mov(state, ops, data_symbols, constants, instr)
        elif opcode == "dec":
            _exec_dec(state, ops, data_symbols, instr)
        elif opcode == "inc":
            _exec_inc(state, ops, data_symbols, instr)
        elif opcode == "cmp":
            _exec_cmp(state, ops, data_symbols, constants, instr)
        elif opcode == "xor":
            _exec_xor(state, ops, data_symbols, instr)
        elif opcode == "add":
            _exec_add(state, ops, data_symbols, constants, instr)
        elif opcode == "sub":
            _exec_sub(state, ops, data_symbols, constants, instr)
        elif opcode in ("jle", "jl", "je", "jz", "jnz", "jne", "jg", "jge",
                         "jmp", "jb", "jbe", "ja", "jae", "jo", "jno",
                         "js", "jns", "jc", "jnc"):
            _exec_jump(state, opcode, ops, labels, instr)
            state.end_cycle()
            return  # PC already set by jump logic
        elif opcode == "syscall":
            _exec_syscall(state, instr)
            state.end_cycle()
            return
        elif opcode == "nop":
            state.add_event(Event(
                Component.CONTROL, "NOP — no operation",
                inputs=[], output="No-op",
            ))
        elif opcode == "hlt":
            state.add_event(Event(
                Component.CONTROL, "HLT — CPU halted",
                inputs=[], output="HALTED",
            ))
            state.halted = True
            state.end_cycle()
            return
        elif opcode == "ret":
            state.add_event(Event(
                Component.CONTROL, "RET — return (halting simulator)",
                inputs=[], output="HALTED",
            ))
            state.halted = True
            state.end_cycle()
            return
        else:
            raise InvalidInstructionError(
                f"Unknown x86-64 instruction '{opcode}'", instr.line_number,
            )
    except (ExecutionError, InvalidInstructionError):
        raise
    except Exception as exc:
        raise ExecutionError(
            f"Error executing '{instr.raw}': {exc}", state.pc,
        ) from exc

    # Advance PC for non-branch instructions
    state.pc += 1
    state.end_cycle()


# ---------------------------------------------------------------------------
# Address resolution
# ---------------------------------------------------------------------------

def _resolve_address(
    state: X86State,
    mem: MemoryOperand,
    data_symbols: dict[str, DataSymbol],
) -> int:
    """
    Resolve a MemoryOperand to an absolute byte address.

    Evaluates: base_addr + index_reg_value * scale + displacement
    """
    addr = 0

    # Base: symbol address or register value
    if mem.base_symbol:
        if mem.base_symbol not in data_symbols:
            raise ExecutionError(f"Undefined symbol '{mem.base_symbol}'", 0)
        addr += data_symbols[mem.base_symbol].address
    if mem.base_reg:
        addr += state.read_reg(mem.base_reg)

    # Index with scale
    if mem.index_reg:
        index_val = state.read_reg(mem.index_reg)
        addr += index_val * mem.scale

    # Displacement
    addr += mem.displacement

    return addr


def _read_operand(
    state: X86State,
    operand: Any,
    data_symbols: dict[str, DataSymbol],
    constants: dict[str, int] | None = None,
) -> int:
    """
    Read the value of an operand.

    - str (register name) → register value
    - int (immediate) → value itself
    - MemoryOperand → read dword from resolved address
    """
    if isinstance(operand, MemoryOperand):
        addr = _resolve_address(state, operand, data_symbols)
        return state.read_dword(addr)
    elif isinstance(operand, str):
        return state.read_reg(operand)
    elif isinstance(operand, int):
        return operand
    else:
        raise ExecutionError(f"Invalid operand type: {type(operand)}", state.pc)


def _write_operand(
    state: X86State,
    operand: Any,
    value: int,
    data_symbols: dict[str, DataSymbol],
) -> None:
    """
    Write a value to a destination operand.

    - str (register name) → write to register
    - MemoryOperand → write dword to resolved address
    """
    if isinstance(operand, MemoryOperand):
        addr = _resolve_address(state, operand, data_symbols)
        state.write_dword(addr, value)
    elif isinstance(operand, str):
        state.write_reg(operand, value)
    else:
        raise ExecutionError(
            f"Cannot write to operand of type {type(operand)}", state.pc,
        )


def _operand_bits(operand: Any) -> int:
    """Return the operand size in bits (32 for eax-style, 64 for rax-style)."""
    if isinstance(operand, str):
        if operand.lower() in _GP_REGS_32:
            return 32
        return 64
    if isinstance(operand, MemoryOperand):
        return 32  # dword memory access by default
    return 64


# ---------------------------------------------------------------------------
# MOV dst, src
# ---------------------------------------------------------------------------

def _exec_mov(
    state: X86State,
    ops: list[Any],
    data_symbols: dict[str, DataSymbol],
    constants: dict[str, int],
    instr: X86Instruction,
) -> None:
    if len(ops) != 2:
        raise InvalidInstructionError("MOV requires 2 operands", instr.line_number)

    dst, src = ops
    value = _read_operand(state, src, data_symbols, constants)
    _write_operand(state, dst, value, data_symbols)

    state.add_event(Event(
        Component.REGISTERS if isinstance(dst, str) else Component.MEMORY,
        f"MOV: {_fmt_operand(dst)} ← {value}",
        inputs=[_fmt_operand(src)],
        output=value,
    ))


# ---------------------------------------------------------------------------
# DEC dst
# ---------------------------------------------------------------------------

def _exec_dec(
    state: X86State,
    ops: list[Any],
    data_symbols: dict[str, DataSymbol],
    instr: X86Instruction,
) -> None:
    if len(ops) != 1:
        raise InvalidInstructionError("DEC requires 1 operand", instr.line_number)

    dst = ops[0]
    old_val = _read_operand(state, dst, data_symbols)
    bits = _operand_bits(dst)
    new_val = old_val - 1
    _write_operand(state, dst, new_val, data_symbols)
    state.update_flags_sub(old_val, 1, new_val, bits)

    state.add_event(Event(
        Component.ALU,
        f"DEC: {_fmt_operand(dst)} = {old_val} → {new_val}",
        inputs=[old_val],
        output=new_val,
        meta={"flags": dict(state.flags)},
    ))


# ---------------------------------------------------------------------------
# INC dst
# ---------------------------------------------------------------------------

def _exec_inc(
    state: X86State,
    ops: list[Any],
    data_symbols: dict[str, DataSymbol],
    instr: X86Instruction,
) -> None:
    if len(ops) != 1:
        raise InvalidInstructionError("INC requires 1 operand", instr.line_number)

    dst = ops[0]
    old_val = _read_operand(state, dst, data_symbols)
    bits = _operand_bits(dst)
    new_val = old_val + 1
    _write_operand(state, dst, new_val, data_symbols)
    state.update_flags_add(old_val, 1, new_val, bits)

    state.add_event(Event(
        Component.ALU,
        f"INC: {_fmt_operand(dst)} = {old_val} → {new_val}",
        inputs=[old_val],
        output=new_val,
        meta={"flags": dict(state.flags)},
    ))


# ---------------------------------------------------------------------------
# CMP a, b  (sets flags based on a - b, does NOT store result)
# ---------------------------------------------------------------------------

def _exec_cmp(
    state: X86State,
    ops: list[Any],
    data_symbols: dict[str, DataSymbol],
    constants: dict[str, int],
    instr: X86Instruction,
) -> None:
    if len(ops) != 2:
        raise InvalidInstructionError("CMP requires 2 operands", instr.line_number)

    a_op, b_op = ops
    a_val = _read_operand(state, a_op, data_symbols, constants)
    b_val = _read_operand(state, b_op, data_symbols, constants)
    bits = _operand_bits(a_op)
    result = a_val - b_val
    state.update_flags_sub(a_val, b_val, result, bits)

    state.add_event(Event(
        Component.ALU,
        f"CMP: {_fmt_operand(a_op)}({a_val}) - {_fmt_operand(b_op)}({b_val}) = {result}",
        inputs=[a_val, b_val],
        output=result,
        meta={"flags": dict(state.flags)},
    ))


# ---------------------------------------------------------------------------
# XOR dst, src
# ---------------------------------------------------------------------------

def _exec_xor(
    state: X86State,
    ops: list[Any],
    data_symbols: dict[str, DataSymbol],
    instr: X86Instruction,
) -> None:
    if len(ops) != 2:
        raise InvalidInstructionError("XOR requires 2 operands", instr.line_number)

    dst, src = ops
    a_val = _read_operand(state, dst, data_symbols)
    b_val = _read_operand(state, src, data_symbols)
    bits = _operand_bits(dst)
    result = a_val ^ b_val
    _write_operand(state, dst, result, data_symbols)
    state.update_flags_logic(result, bits)

    state.add_event(Event(
        Component.ALU,
        f"XOR: {_fmt_operand(dst)} = {a_val} ^ {b_val} = {result}",
        inputs=[a_val, b_val],
        output=result,
        meta={"flags": dict(state.flags)},
    ))


# ---------------------------------------------------------------------------
# ADD dst, src
# ---------------------------------------------------------------------------

def _exec_add(
    state: X86State,
    ops: list[Any],
    data_symbols: dict[str, DataSymbol],
    constants: dict[str, int],
    instr: X86Instruction,
) -> None:
    if len(ops) != 2:
        raise InvalidInstructionError("ADD requires 2 operands", instr.line_number)

    dst, src = ops
    a_val = _read_operand(state, dst, data_symbols, constants)
    b_val = _read_operand(state, src, data_symbols, constants)
    bits = _operand_bits(dst)
    result = a_val + b_val
    _write_operand(state, dst, result, data_symbols)
    state.update_flags_add(a_val, b_val, result, bits)

    state.add_event(Event(
        Component.ALU,
        f"ADD: {_fmt_operand(dst)} = {a_val} + {b_val} = {result}",
        inputs=[a_val, b_val],
        output=result,
        meta={"flags": dict(state.flags)},
    ))


# ---------------------------------------------------------------------------
# SUB dst, src
# ---------------------------------------------------------------------------

def _exec_sub(
    state: X86State,
    ops: list[Any],
    data_symbols: dict[str, DataSymbol],
    constants: dict[str, int],
    instr: X86Instruction,
) -> None:
    if len(ops) != 2:
        raise InvalidInstructionError("SUB requires 2 operands", instr.line_number)

    dst, src = ops
    a_val = _read_operand(state, dst, data_symbols, constants)
    b_val = _read_operand(state, src, data_symbols, constants)
    bits = _operand_bits(dst)
    result = a_val - b_val
    _write_operand(state, dst, result, data_symbols)
    state.update_flags_sub(a_val, b_val, result, bits)

    state.add_event(Event(
        Component.ALU,
        f"SUB: {_fmt_operand(dst)} = {a_val} - {b_val} = {result}",
        inputs=[a_val, b_val],
        output=result,
        meta={"flags": dict(state.flags)},
    ))


# ---------------------------------------------------------------------------
# Conditional and unconditional jumps
# ---------------------------------------------------------------------------

def _exec_jump(
    state: X86State,
    opcode: str,
    ops: list[Any],
    labels: dict[str, int],
    instr: X86Instruction,
) -> None:
    if len(ops) != 1:
        raise InvalidInstructionError(f"{opcode.upper()} requires 1 operand", instr.line_number)

    label = ops[0]
    if label not in labels:
        raise ExecutionError(f"Undefined label '{label}'", state.pc)

    target = labels[label]
    taken = _evaluate_condition(opcode, state.flags)

    if taken:
        state.add_event(Event(
            Component.PC,
            f"{opcode.upper()} TAKEN: PC ← {target} (label '{label}')",
            inputs=[state.pc, label],
            output=target,
            meta={"branch_taken": True, "flags": dict(state.flags)},
        ))
        state.pc = target
    else:
        state.add_event(Event(
            Component.PC,
            f"{opcode.upper()} NOT TAKEN: PC ← {state.pc + 1}",
            inputs=[state.pc, label],
            output=state.pc + 1,
            meta={"branch_taken": False, "flags": dict(state.flags)},
        ))
        state.pc += 1


def _evaluate_condition(opcode: str, flags: dict[str, bool]) -> bool:
    """Evaluate a jump condition based on FLAGS."""
    zf = flags["ZF"]
    sf = flags["SF"]
    of = flags["OF"]
    cf = flags["CF"]

    conditions: dict[str, bool] = {
        "jmp": True,                          # unconditional
        "je":  zf,                            # equal (ZF=1)
        "jz":  zf,                            # zero (ZF=1)
        "jne": not zf,                        # not equal (ZF=0)
        "jnz": not zf,                        # not zero (ZF=0)
        "jl":  sf != of,                      # less (SF≠OF)
        "jle": zf or (sf != of),              # less or equal (ZF=1 OR SF≠OF)
        "jg":  (not zf) and (sf == of),       # greater (ZF=0 AND SF=OF)
        "jge": sf == of,                      # greater or equal (SF=OF)
        "jb":  cf,                            # below (CF=1)
        "jbe": cf or zf,                      # below or equal (CF=1 OR ZF=1)
        "ja":  (not cf) and (not zf),         # above (CF=0 AND ZF=0)
        "jae": not cf,                        # above or equal (CF=0)
        "jo":  of,                            # overflow
        "jno": not of,                        # no overflow
        "js":  sf,                            # sign (negative)
        "jns": not sf,                        # no sign (positive)
        "jc":  cf,                            # carry
        "jnc": not cf,                        # no carry
    }

    if opcode not in conditions:
        raise ExecutionError(f"Unknown jump condition '{opcode}'", 0)

    return conditions[opcode]


# ---------------------------------------------------------------------------
# SYSCALL (mocked)
# ---------------------------------------------------------------------------

def _exec_syscall(
    state: X86State,
    instr: X86Instruction,
) -> None:
    """
    Mock syscall implementation.

    Only supports:
      - rax=60 (sys_exit): halt the CPU. rdi = exit code.
    """
    syscall_num = state.read_reg("rax")

    if syscall_num == 60:
        exit_code = state.read_reg("rdi")
        state.add_event(Event(
            Component.CONTROL,
            f"SYSCALL 60 (exit): code={exit_code}",
            inputs=[syscall_num, exit_code],
            output="HALTED",
            meta={"syscall": 60, "exit_code": exit_code},
        ))
        state.halted = True
    else:
        state.add_event(Event(
            Component.CONTROL,
            f"SYSCALL {syscall_num}: unimplemented (ignored)",
            inputs=[syscall_num],
            output="IGNORED",
            meta={"syscall": syscall_num},
        ))
        # Don't halt — just advance PC
        state.pc += 1


# ---------------------------------------------------------------------------
# Formatting helper
# ---------------------------------------------------------------------------

def _fmt_operand(operand: Any) -> str:
    """Format an operand for event descriptions."""
    if isinstance(operand, MemoryOperand):
        return repr(operand)
    elif isinstance(operand, str):
        return operand
    elif isinstance(operand, int):
        return str(operand)
    return str(operand)
