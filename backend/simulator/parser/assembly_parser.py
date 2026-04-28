"""
Assembly parser for both RISC and CISC instruction sets.

Design goals:
  - Architecture-agnostic tokenisation
  - First-pass label extraction (forward references work)
  - Second-pass instruction materialisation
  - Clear error messages with line numbers

Supported RISC instructions:
  LOAD  Rd, addr          — load from memory address into register
  STORE Rs, addr          — store register value into memory address
  ADD   Rd, Rs1, Rs2      — Rd = Rs1 + Rs2
  SUB   Rd, Rs1, Rs2      — Rd = Rs1 - Rs2
  MOV   Rd, imm           — Rd = immediate value
  BEQ   Rs1, Rs2, label   — branch to label if Rs1 == Rs2
  BNE   Rs1, Rs2, label   — branch to label if Rs1 != Rs2
  JMP   label             — unconditional jump

Supported CISC instructions:
  ADD   [addr1], [addr2]  — MEM[addr1] += MEM[addr2]  (decomposed into µ-ops)
  SUB   [addr1], [addr2]  — MEM[addr1] -= MEM[addr2]
  MOV   [addr], imm       — MEM[addr] = imm
  MUL   [addr1], [addr2]  — MEM[addr1] *= MEM[addr2]
  LOAD  Rd, [addr]        — Rd = MEM[addr]  (CISC variant)
  STORE [addr], Rs        — MEM[addr] = Rs  (CISC variant)
  BEQ   [addr1], [addr2], label
  JMP   label
  INC   [addr]            — MEM[addr] += 1
  DEC   [addr]            — MEM[addr] -= 1
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from simulator.core.exceptions import InvalidInstructionError, ParseError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Instruction data class — one per parsed assembly line
# ---------------------------------------------------------------------------

@dataclass
class Instruction:
    """A parsed assembly instruction (architecture-neutral representation)."""
    opcode: str                         # e.g. "ADD", "LOAD"
    operands: list[Any] = field(default_factory=list)
    raw: str = ""                       # original source line
    line_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "opcode": self.opcode,
            "operands": self.operands,
            "raw": self.raw,
            "line_number": self.line_number,
        }


# ---------------------------------------------------------------------------
# Parse result
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    """Container returned by the parser."""
    instructions: list[Instruction]
    labels: dict[str, int]              # label name → instruction index

    def to_dict(self) -> dict[str, Any]:
        return {
            "instructions": [i.to_dict() for i in self.instructions],
            "labels": self.labels,
        }


# ---------------------------------------------------------------------------
# Helper regex patterns
# ---------------------------------------------------------------------------

_REGISTER_RE = re.compile(r"^R([0-7])$", re.IGNORECASE)
_MEMORY_REF_RE = re.compile(r"^\[(\d+)\]$")       # e.g. [100]
_LABEL_DEF_RE = re.compile(r"^([A-Za-z_]\w*):$")  # e.g. LOOP:
_IMMEDIATE_RE = re.compile(r"^-?\d+$")


def _parse_register(token: str) -> int | None:
    """Return register index (0–7) or None if not a register token."""
    m = _REGISTER_RE.match(token)
    return int(m.group(1)) if m else None


def _parse_memory_ref(token: str) -> int | None:
    """Return memory address from [addr] syntax, or None."""
    m = _MEMORY_REF_RE.match(token)
    return int(m.group(1)) if m else None


def _parse_immediate(token: str) -> int | None:
    """Return integer if token is a literal number, else None."""
    m = _IMMEDIATE_RE.match(token)
    return int(m.group(0)) if m else None


# ---------------------------------------------------------------------------
# RISC parser
# ---------------------------------------------------------------------------

def parse_risc(source: str) -> ParseResult:
    """
    Parse RISC assembly source code.

    Returns a ParseResult containing the instruction list and label map.
    Raises ParseError or InvalidInstructionError on failures.
    """
    lines = source.strip().splitlines()
    labels: dict[str, int] = {}
    instructions: list[Instruction] = []

    # --- First pass: strip comments, identify labels ---
    clean_lines: list[tuple[int, str]] = []
    instruction_index = 0
    for line_num_0, raw_line in enumerate(lines):
        line = raw_line.split(";")[0].strip()  # strip comments
        if not line:
            continue

        label_match = _LABEL_DEF_RE.match(line.split()[0])
        if label_match:
            label_name = label_match.group(1)
            if label_name in labels:
                raise ParseError(f"Duplicate label '{label_name}'", line_num_0 + 1)
            labels[label_name] = instruction_index
            # The rest of the line after the label could still be an instruction
            remainder = line[label_match.end():].strip()
            if remainder:
                clean_lines.append((line_num_0 + 1, remainder))
                instruction_index += 1
        else:
            clean_lines.append((line_num_0 + 1, line))
            instruction_index += 1

    # --- Second pass: parse instructions ---
    for line_num, line in clean_lines:
        tokens = [t.strip().rstrip(",") for t in re.split(r"[,\s]+", line) if t.strip()]
        if not tokens:
            continue

        opcode = tokens[0].upper()
        operands_raw = tokens[1:]

        try:
            instruction = _parse_risc_instruction(opcode, operands_raw, line, line_num)
            instructions.append(instruction)
        except (InvalidInstructionError, ParseError):
            raise
        except Exception as exc:
            raise ParseError(str(exc), line_num) from exc

    logger.info("RISC parse complete: %d instructions, %d labels", len(instructions), len(labels))
    return ParseResult(instructions=instructions, labels=labels)


def _parse_risc_instruction(
    opcode: str,
    operands_raw: list[str],
    raw_line: str,
    line_num: int,
) -> Instruction:
    """Parse a single RISC instruction and validate its operands."""
    operands: list[Any] = []

    if opcode == "LOAD":
        # LOAD Rd, addr
        if len(operands_raw) != 2:
            raise InvalidInstructionError(f"LOAD expects 2 operands, got {len(operands_raw)}", line_num)
        rd = _parse_register(operands_raw[0])
        addr = _parse_immediate(operands_raw[1])
        if rd is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[0]}'", line_num)
        if addr is None:
            raise InvalidInstructionError(f"Invalid address '{operands_raw[1]}'", line_num)
        operands = [rd, addr]

    elif opcode == "STORE":
        # STORE Rs, addr
        if len(operands_raw) != 2:
            raise InvalidInstructionError(f"STORE expects 2 operands, got {len(operands_raw)}", line_num)
        rs = _parse_register(operands_raw[0])
        addr = _parse_immediate(operands_raw[1])
        if rs is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[0]}'", line_num)
        if addr is None:
            raise InvalidInstructionError(f"Invalid address '{operands_raw[1]}'", line_num)
        operands = [rs, addr]

    elif opcode in ("ADD", "SUB"):
        # ADD/SUB Rd, Rs1, Rs2
        if len(operands_raw) != 3:
            raise InvalidInstructionError(f"{opcode} expects 3 operands, got {len(operands_raw)}", line_num)
        rd = _parse_register(operands_raw[0])
        rs1 = _parse_register(operands_raw[1])
        rs2 = _parse_register(operands_raw[2])
        if rd is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[0]}'", line_num)
        if rs1 is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[1]}'", line_num)
        if rs2 is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[2]}'", line_num)
        operands = [rd, rs1, rs2]

    elif opcode == "MOV":
        # MOV Rd, imm
        if len(operands_raw) != 2:
            raise InvalidInstructionError(f"MOV expects 2 operands, got {len(operands_raw)}", line_num)
        rd = _parse_register(operands_raw[0])
        imm = _parse_immediate(operands_raw[1])
        if rd is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[0]}'", line_num)
        if imm is None:
            raise InvalidInstructionError(f"Invalid immediate '{operands_raw[1]}'", line_num)
        operands = [rd, imm]

    elif opcode in ("BEQ", "BNE"):
        # BEQ/BNE Rs1, Rs2, label
        if len(operands_raw) != 3:
            raise InvalidInstructionError(f"{opcode} expects 3 operands, got {len(operands_raw)}", line_num)
        rs1 = _parse_register(operands_raw[0])
        rs2 = _parse_register(operands_raw[1])
        label = operands_raw[2]
        if rs1 is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[0]}'", line_num)
        if rs2 is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[1]}'", line_num)
        operands = [rs1, rs2, label]

    elif opcode == "JMP":
        # JMP label
        if len(operands_raw) != 1:
            raise InvalidInstructionError(f"JMP expects 1 operand, got {len(operands_raw)}", line_num)
        operands = [operands_raw[0]]

    elif opcode == "HALT":
        operands = []

    elif opcode == "NOP":
        operands = []

    elif opcode == "PRINT":
        # PRINT Rx  — print register value
        if len(operands_raw) != 1:
            raise InvalidInstructionError(f"PRINT expects 1 operand, got {len(operands_raw)}", line_num)
        rd = _parse_register(operands_raw[0])
        if rd is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[0]}'", line_num)
        operands = [rd]

    elif opcode == "PRINT_MEM":
        # PRINT_MEM addr  — print memory value
        if len(operands_raw) != 1:
            raise InvalidInstructionError(f"PRINT_MEM expects 1 operand, got {len(operands_raw)}", line_num)
        addr = _parse_immediate(operands_raw[0])
        if addr is None:
            raise InvalidInstructionError(f"Invalid address '{operands_raw[0]}'", line_num)
        operands = [addr]

    elif opcode == "PRINT_STR":
        # PRINT_STR "text"  — print literal string
        # Reconstruct the string from remaining tokens (may contain spaces)
        raw_str = raw_line.split(None, 1)[1] if " " in raw_line else ""
        raw_str = raw_str.strip().strip('"').strip("'")
        operands = [raw_str]

    elif opcode == "READ":
        # READ Rx  — read integer input into register
        if len(operands_raw) != 1:
            raise InvalidInstructionError(f"READ expects 1 operand, got {len(operands_raw)}", line_num)
        rd = _parse_register(operands_raw[0])
        if rd is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[0]}'", line_num)
        operands = [rd]

    else:
        raise InvalidInstructionError(f"Unknown RISC instruction '{opcode}'", line_num)

    return Instruction(opcode=opcode, operands=operands, raw=raw_line, line_number=line_num)


# ---------------------------------------------------------------------------
# CISC parser
# ---------------------------------------------------------------------------

def parse_cisc(source: str) -> ParseResult:
    """
    Parse CISC assembly source code.

    CISC instructions typically use memory references [addr] as operands.
    Returns a ParseResult containing the instruction list and label map.
    """
    lines = source.strip().splitlines()
    labels: dict[str, int] = {}
    instructions: list[Instruction] = []

    # --- First pass: strip comments, identify labels ---
    clean_lines: list[tuple[int, str]] = []
    instruction_index = 0
    for line_num_0, raw_line in enumerate(lines):
        line = raw_line.split(";")[0].strip()
        if not line:
            continue

        label_match = _LABEL_DEF_RE.match(line.split()[0])
        if label_match:
            label_name = label_match.group(1)
            if label_name in labels:
                raise ParseError(f"Duplicate label '{label_name}'", line_num_0 + 1)
            labels[label_name] = instruction_index
            remainder = line[label_match.end():].strip()
            if remainder:
                clean_lines.append((line_num_0 + 1, remainder))
                instruction_index += 1
        else:
            clean_lines.append((line_num_0 + 1, line))
            instruction_index += 1

    # --- Second pass: parse instructions ---
    for line_num, line in clean_lines:
        try:
            instruction = _parse_cisc_line(line, line_num)
            instructions.append(instruction)
        except (InvalidInstructionError, ParseError):
            raise
        except Exception as exc:
            raise ParseError(str(exc), line_num) from exc

    logger.info("CISC parse complete: %d instructions, %d labels", len(instructions), len(labels))
    return ParseResult(instructions=instructions, labels=labels)


def _parse_cisc_line(raw_line: str, line_num: int) -> Instruction:
    """Parse a single CISC assembly line."""
    # Tokenize carefully to preserve [addr] references
    # Split by whitespace and commas, but keep [..] groups together
    tokens = re.findall(r"\[[^\]]+\]|[^\s,]+", raw_line)
    if not tokens:
        raise ParseError("Empty instruction", line_num)

    opcode = tokens[0].upper()
    operands_raw = tokens[1:]
    operands: list[Any] = []

    if opcode in ("ADD", "SUB", "MUL"):
        # ADD [addr1], [addr2]
        if len(operands_raw) != 2:
            raise InvalidInstructionError(
                f"{opcode} expects 2 operands, got {len(operands_raw)}", line_num
            )
        addr1 = _parse_memory_ref(operands_raw[0])
        addr2 = _parse_memory_ref(operands_raw[1])
        if addr1 is None:
            raise InvalidInstructionError(f"Invalid memory ref '{operands_raw[0]}'", line_num)
        if addr2 is None:
            raise InvalidInstructionError(f"Invalid memory ref '{operands_raw[1]}'", line_num)
        operands = [addr1, addr2]

    elif opcode == "MOV":
        # MOV [addr], imm
        if len(operands_raw) != 2:
            raise InvalidInstructionError(
                f"MOV expects 2 operands, got {len(operands_raw)}", line_num
            )
        addr = _parse_memory_ref(operands_raw[0])
        imm = _parse_immediate(operands_raw[1])
        if addr is None:
            raise InvalidInstructionError(f"Invalid memory ref '{operands_raw[0]}'", line_num)
        if imm is None:
            raise InvalidInstructionError(f"Invalid immediate '{operands_raw[1]}'", line_num)
        operands = [addr, imm]

    elif opcode == "LOAD":
        # LOAD Rd, [addr]
        if len(operands_raw) != 2:
            raise InvalidInstructionError(
                f"LOAD expects 2 operands, got {len(operands_raw)}", line_num
            )
        rd = _parse_register(operands_raw[0])
        addr = _parse_memory_ref(operands_raw[1])
        if rd is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[0]}'", line_num)
        if addr is None:
            raise InvalidInstructionError(f"Invalid memory ref '{operands_raw[1]}'", line_num)
        operands = [rd, addr]

    elif opcode == "STORE":
        # STORE [addr], Rs
        if len(operands_raw) != 2:
            raise InvalidInstructionError(
                f"STORE expects 2 operands, got {len(operands_raw)}", line_num
            )
        addr = _parse_memory_ref(operands_raw[0])
        rs = _parse_register(operands_raw[1])
        if addr is None:
            raise InvalidInstructionError(f"Invalid memory ref '{operands_raw[0]}'", line_num)
        if rs is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[1]}'", line_num)
        operands = [addr, rs]

    elif opcode in ("INC", "DEC"):
        # INC [addr]  /  DEC [addr]
        if len(operands_raw) != 1:
            raise InvalidInstructionError(
                f"{opcode} expects 1 operand, got {len(operands_raw)}", line_num
            )
        addr = _parse_memory_ref(operands_raw[0])
        if addr is None:
            raise InvalidInstructionError(f"Invalid memory ref '{operands_raw[0]}'", line_num)
        operands = [addr]

    elif opcode in ("BEQ", "BNE"):
        # BEQ/BNE [addr1], [addr2], label
        if len(operands_raw) != 3:
            raise InvalidInstructionError(
                f"{opcode} expects 3 operands, got {len(operands_raw)}", line_num
            )
        addr1 = _parse_memory_ref(operands_raw[0])
        addr2 = _parse_memory_ref(operands_raw[1])
        label = operands_raw[2]
        if addr1 is None:
            raise InvalidInstructionError(f"Invalid memory ref '{operands_raw[0]}'", line_num)
        if addr2 is None:
            raise InvalidInstructionError(f"Invalid memory ref '{operands_raw[1]}'", line_num)
        operands = [addr1, addr2, label]

    elif opcode == "JMP":
        # JMP label
        if len(operands_raw) != 1:
            raise InvalidInstructionError(
                f"JMP expects 1 operand, got {len(operands_raw)}", line_num
            )
        operands = [operands_raw[0]]

    elif opcode == "HALT":
        operands = []

    elif opcode == "NOP":
        operands = []

    elif opcode == "PRINT":
        # PRINT Rx  — print register value
        if len(operands_raw) != 1:
            raise InvalidInstructionError(f"PRINT expects 1 operand, got {len(operands_raw)}", line_num)
        rd = _parse_register(operands_raw[0])
        if rd is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[0]}'", line_num)
        operands = [rd]

    elif opcode == "PRINT_MEM":
        # PRINT_MEM [addr]  — print memory value
        if len(operands_raw) != 1:
            raise InvalidInstructionError(f"PRINT_MEM expects 1 operand, got {len(operands_raw)}", line_num)
        addr = _parse_memory_ref(operands_raw[0])
        if addr is None:
            # Also accept bare integer address
            addr = _parse_immediate(operands_raw[0])
        if addr is None:
            raise InvalidInstructionError(f"Invalid memory ref '{operands_raw[0]}'", line_num)
        operands = [addr]

    elif opcode == "PRINT_STR":
        # PRINT_STR "text"
        raw_str = raw_line.split(None, 1)[1] if " " in raw_line else ""
        raw_str = raw_str.strip().strip('"').strip("'")
        operands = [raw_str]

    elif opcode == "READ":
        # READ Rx  — read integer input into register
        if len(operands_raw) != 1:
            raise InvalidInstructionError(f"READ expects 1 operand, got {len(operands_raw)}", line_num)
        rd = _parse_register(operands_raw[0])
        if rd is None:
            raise InvalidInstructionError(f"Invalid register '{operands_raw[0]}'", line_num)
        operands = [rd]

    else:
        raise InvalidInstructionError(f"Unknown CISC instruction '{opcode}'", line_num)

    return Instruction(opcode=opcode, operands=operands, raw=raw_line, line_number=line_num)
