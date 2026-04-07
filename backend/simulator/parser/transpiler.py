"""
Transpiler from a small common assembly dialect to RISC and CISC.

This enables a single-editor UX in the frontend:
  - user writes one "common" program
  - backend produces architecture-specific sources
  - simulator runs both and compares results
"""

from __future__ import annotations

import re

from simulator.core.exceptions import InvalidInstructionError, ParseError

_LABEL_DEF_RE = re.compile(r"^([A-Za-z_]\w*):$")
_REGISTER_RE = re.compile(r"^R([0-7])$", re.IGNORECASE)
_MEMORY_REF_RE = re.compile(r"^\[(\d+)\]$")
_IMMEDIATE_RE = re.compile(r"^-?\d+$")

_MEMORY_SIZE = 256


def transpile_common_to_risc_cisc(source: str) -> tuple[str, str]:
    """Return (risc_source, cisc_source) from common assembly input."""
    lines = source.strip().splitlines()
    clean_lines: list[tuple[int, str]] = []

    for idx, raw in enumerate(lines):
        line = raw.split(";")[0].strip()
        if not line:
            continue
        clean_lines.append((idx + 1, line))

    register_addrs, tmp0_addr, tmp1_addr = _allocate_runtime_addresses(clean_lines)
    risc_lines: list[str] = []
    cisc_lines: list[str] = []
    label_counter = 0

    for line_num, line in clean_lines:
        label, instruction_part = _extract_label(line)
        if label:
            risc_lines.append(f"{label}:")
            cisc_lines.append(f"{label}:")
        if not instruction_part:
            continue

        tokens = [t.strip().rstrip(",") for t in re.split(r"[,\s]+", instruction_part) if t.strip()]
        if not tokens:
            continue

        opcode = tokens[0].upper()
        ops = tokens[1:]

        risc_instr, cisc_instr, label_counter = _transpile_instruction(
            opcode,
            ops,
            line_num,
            label_counter,
            register_addrs,
            tmp0_addr,
            tmp1_addr,
        )
        risc_lines.extend(risc_instr)
        cisc_lines.extend(cisc_instr)

    return ("\n".join(risc_lines).strip(), "\n".join(cisc_lines).strip())


def _extract_label(line: str) -> tuple[str | None, str]:
    first = line.split()[0]
    m = _LABEL_DEF_RE.match(first)
    if not m:
        return None, line
    label = m.group(1)
    remainder = line[m.end():].strip()
    return label, remainder


def _reg_index(token: str, line_num: int) -> int:
    m = _REGISTER_RE.match(token)
    if not m:
        raise InvalidInstructionError(f"Expected register R0..R7, got '{token}'", line_num)
    return int(m.group(1))


def _addr_token(token: str, line_num: int) -> int:
    m_mem = _MEMORY_REF_RE.match(token)
    if m_mem:
        return int(m_mem.group(1))
    if _IMMEDIATE_RE.match(token):
        return int(token)
    raise InvalidInstructionError(f"Expected memory address, got '{token}'", line_num)


def _imm(token: str, line_num: int) -> int:
    if not _IMMEDIATE_RE.match(token):
        raise InvalidInstructionError(f"Expected immediate integer, got '{token}'", line_num)
    return int(token)


def _allocate_runtime_addresses(clean_lines: list[tuple[int, str]]) -> tuple[dict[int, int], int, int]:
    used_addrs: set[int] = set()
    for line_num, line in clean_lines:
        label, instruction_part = _extract_label(line)
        _ = label
        if not instruction_part:
            continue
        tokens = [t.strip().rstrip(",") for t in re.split(r"[,\s]+", instruction_part) if t.strip()]
        if not tokens:
            continue
        opcode = tokens[0].upper()
        ops = tokens[1:]

        if opcode in ("LOAD", "STORE") and len(ops) == 2:
            try:
                used_addrs.add(_addr_token(ops[1], line_num))
            except InvalidInstructionError:
                pass

    free_pool = [addr for addr in range(_MEMORY_SIZE - 1, -1, -1) if addr not in used_addrs]
    needed = 10  # 8 register mirrors + 2 temporaries
    if len(free_pool) < needed:
        raise ParseError("Not enough free memory addresses for transpilation runtime state", 0)

    assigned = free_pool[:needed]
    register_addrs = {idx: assigned[idx] for idx in range(8)}
    tmp0_addr = assigned[8]
    tmp1_addr = assigned[9]
    return register_addrs, tmp0_addr, tmp1_addr


def _transpile_instruction(
    opcode: str,
    ops: list[str],
    line_num: int,
    label_counter: int,
    register_addrs: dict[int, int],
    tmp0_addr: int,
    tmp1_addr: int,
) -> tuple[list[str], list[str], int]:
    def raddr(reg_idx: int) -> int:
        return register_addrs[reg_idx]

    if opcode == "MOV":
        if len(ops) != 2:
            raise InvalidInstructionError("MOV expects 2 operands", line_num)
        rd = _reg_index(ops[0], line_num)
        imm = _imm(ops[1], line_num)
        return (
            [f"MOV R{rd}, {imm}"],
            [f"MOV [{raddr(rd)}], {imm}"],
            label_counter,
        )

    if opcode == "LOAD":
        if len(ops) != 2:
            raise InvalidInstructionError("LOAD expects 2 operands", line_num)
        rd = _reg_index(ops[0], line_num)
        addr = _addr_token(ops[1], line_num)
        return (
            [f"LOAD R{rd}, {addr}"],
            [
                f"LOAD R0, [{addr}]",
                f"STORE [{raddr(rd)}], R0",
            ],
            label_counter,
        )

    if opcode == "STORE":
        if len(ops) != 2:
            raise InvalidInstructionError("STORE expects 2 operands", line_num)
        rs = _reg_index(ops[0], line_num)
        addr = _addr_token(ops[1], line_num)
        return (
            [f"STORE R{rs}, {addr}"],
            [
                f"LOAD R0, [{raddr(rs)}]",
                f"STORE [{addr}], R0",
            ],
            label_counter,
        )

    if opcode in ("ADD", "SUB"):
        if len(ops) != 3:
            raise InvalidInstructionError(f"{opcode} expects 3 operands", line_num)
        rd = _reg_index(ops[0], line_num)
        rs1 = _reg_index(ops[1], line_num)
        rs2 = _reg_index(ops[2], line_num)
        op_instr = "ADD" if opcode == "ADD" else "SUB"
        cisc_seq = [
            f"LOAD R0, [{raddr(rs1)}]",
            f"LOAD R1, [{raddr(rs2)}]",
            f"STORE [{tmp0_addr}], R0",
            f"STORE [{tmp1_addr}], R1",
            f"MOV [{raddr(rd)}], 0",
            f"ADD [{raddr(rd)}], [{tmp0_addr}]",
            f"{op_instr} [{raddr(rd)}], [{tmp1_addr}]",
        ]
        return (
            [f"{opcode} R{rd}, R{rs1}, R{rs2}"],
            cisc_seq,
            label_counter,
        )

    if opcode == "BEQ":
        if len(ops) != 3:
            raise InvalidInstructionError("BEQ expects 3 operands", line_num)
        rs1 = _reg_index(ops[0], line_num)
        rs2 = _reg_index(ops[1], line_num)
        label = ops[2]
        return (
            [f"BEQ R{rs1}, R{rs2}, {label}"],
            [f"BEQ [{raddr(rs1)}], [{raddr(rs2)}], {label}"],
            label_counter,
        )

    if opcode == "BNE":
        if len(ops) != 3:
            raise InvalidInstructionError("BNE expects 3 operands", line_num)
        rs1 = _reg_index(ops[0], line_num)
        rs2 = _reg_index(ops[1], line_num)
        label = ops[2]
        skip_label = f"__BNE_SKIP_{label_counter}"
        label_counter += 1
        return (
            [f"BNE R{rs1}, R{rs2}, {label}"],
            [
                f"BEQ [{raddr(rs1)}], [{raddr(rs2)}], {skip_label}",
                f"JMP {label}",
                f"{skip_label}:",
                "NOP",
            ],
            label_counter,
        )

    if opcode == "JMP":
        if len(ops) != 1:
            raise InvalidInstructionError("JMP expects 1 operand", line_num)
        label = ops[0]
        return ([f"JMP {label}"], [f"JMP {label}"], label_counter)

    if opcode in ("HALT", "NOP"):
        if len(ops) != 0:
            raise InvalidInstructionError(f"{opcode} expects 0 operands", line_num)
        return ([opcode], [opcode], label_counter)

    raise ParseError(f"Unsupported common opcode '{opcode}'", line_num)
