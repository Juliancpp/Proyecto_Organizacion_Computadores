"""
x86-64 NASM-style assembly parser.

Parses real x86-64 assembly syntax including:
  - Sections: .data, .text
  - Directives: dd (define dword), equ (equate constant), global
  - Labels: _start:, loop:, etc.
  - x86-64 registers: rax, rbx, rcx, rdx, rsi, rdi, rsp, rbp, r8-r15,
    plus 32-bit aliases eax, ebx, ecx, edx, esi, edi
  - Complex memory addressing: [base + index*scale + displacement]
  - Instructions: mov, dec, inc, cmp, jle, jl, je, jnz, xor, syscall

Design:
  Pass 1 — Parse .data section: allocate memory for arrays/variables,
           resolve equ constants (including $ - symbol expressions).
  Pass 2 — Parse .text section: extract labels → instruction index map,
           parse each instruction into an X86Instruction.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from simulator.core.exceptions import InvalidInstructionError, ParseError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MemoryOperand:
    """
    Parsed memory reference like [array + rcx*4 + 4].

    Fields:
        base_symbol:  Name of the base symbol (e.g. "array"), or None.
        base_reg:     Base register name (e.g. "rbx"), or None.
        index_reg:    Index register name (e.g. "rcx"), or None.
        scale:        Multiplier for index_reg (1, 2, 4, 8).
        displacement: Constant offset (e.g. 4), default 0.
    """
    base_symbol: str | None = None
    base_reg: str | None = None
    index_reg: str | None = None
    scale: int = 1
    displacement: int = 0

    def __repr__(self) -> str:
        parts = []
        if self.base_symbol:
            parts.append(self.base_symbol)
        if self.base_reg:
            parts.append(self.base_reg)
        if self.index_reg:
            if self.scale != 1:
                parts.append(f"{self.index_reg}*{self.scale}")
            else:
                parts.append(self.index_reg)
        if self.displacement:
            parts.append(str(self.displacement))
        return "[" + " + ".join(parts) + "]"


@dataclass
class X86Instruction:
    """A parsed x86-64 instruction."""
    opcode: str                         # e.g. "mov", "cmp", "jle"
    operands: list[Any] = field(default_factory=list)
    raw: str = ""                       # original source line
    line_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        ops = []
        for op in self.operands:
            if isinstance(op, MemoryOperand):
                ops.append({
                    "type": "memory",
                    "base_symbol": op.base_symbol,
                    "base_reg": op.base_reg,
                    "index_reg": op.index_reg,
                    "scale": op.scale,
                    "displacement": op.displacement,
                })
            else:
                ops.append(op)
        return {
            "opcode": self.opcode,
            "operands": ops,
            "raw": self.raw,
            "line_number": self.line_number,
        }


@dataclass
class DataSymbol:
    """A symbol defined in the .data section."""
    name: str
    address: int            # byte address in memory
    size: int               # total size in bytes
    values: list[int]       # initial dword values


@dataclass
class X86ParseResult:
    """Container returned by the x86-64 parser."""
    instructions: list[X86Instruction]
    labels: dict[str, int]              # label name → instruction index
    data_symbols: dict[str, DataSymbol] # symbol name → DataSymbol
    constants: dict[str, int]           # equ name → computed value
    data_segment: bytes                 # raw bytes for .data section
    data_base_address: int              # base address of .data segment

    def to_dict(self) -> dict[str, Any]:
        return {
            "instructions": [i.to_dict() for i in self.instructions],
            "labels": self.labels,
            "data_symbols": {
                name: {
                    "address": sym.address,
                    "size": sym.size,
                    "values": sym.values,
                }
                for name, sym in self.data_symbols.items()
            },
            "constants": self.constants,
            "data_base_address": self.data_base_address,
        }


# ---------------------------------------------------------------------------
# Register sets
# ---------------------------------------------------------------------------

# 64-bit general-purpose registers
_GP_REGS_64 = frozenset({
    "rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rsp", "rbp",
    "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15",
})

# 32-bit aliases (lower 32 bits of corresponding 64-bit reg)
_GP_REGS_32 = frozenset({
    "eax", "ebx", "ecx", "edx", "esi", "edi", "esp", "ebp",
    "r8d", "r9d", "r10d", "r11d", "r12d", "r13d", "r14d", "r15d",
})

_ALL_REGS = _GP_REGS_64 | _GP_REGS_32

# Map 32-bit alias → 64-bit parent register
_REG_32_TO_64: dict[str, str] = {
    "eax": "rax", "ebx": "rbx", "ecx": "rcx", "edx": "rdx",
    "esi": "rsi", "edi": "rdi", "esp": "rsp", "ebp": "rbp",
    "r8d": "r8", "r9d": "r9", "r10d": "r10", "r11d": "r11",
    "r12d": "r12", "r13d": "r13", "r14d": "r14", "r15d": "r15",
}

# Instructions that take no operands
_ZERO_OPERAND_INSTRS = frozenset({"syscall", "ret", "nop", "hlt"})

# Jump/branch instructions (single label operand)
_JUMP_INSTRS = frozenset({
    "jmp", "je", "jne", "jz", "jnz", "jl", "jle", "jg", "jge",
    "jb", "jbe", "ja", "jae", "jo", "jno", "js", "jns",
    "jc", "jnc",
})

# Default base address for .data segment
DATA_BASE_ADDRESS = 0x1000


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_x86(source: str) -> X86ParseResult:
    """
    Parse x86-64 NASM-style assembly source code.

    Returns an X86ParseResult containing instructions, labels, data layout,
    and constants.
    """
    lines = source.splitlines()

    # Split into sections
    data_lines, text_lines = _split_sections(lines)

    # Pass 1: Parse .data section
    data_symbols, constants, data_segment = _parse_data_section(data_lines)

    # Pass 2: Parse .text section
    instructions, labels = _parse_text_section(text_lines, data_symbols, constants)

    logger.info(
        "x86-64 parse complete: %d instructions, %d labels, %d data symbols, %d constants",
        len(instructions), len(labels), len(data_symbols), len(constants),
    )

    return X86ParseResult(
        instructions=instructions,
        labels=labels,
        data_symbols=data_symbols,
        constants=constants,
        data_segment=data_segment,
        data_base_address=DATA_BASE_ADDRESS,
    )


def is_x86_syntax(source: str) -> bool:
    """
    Heuristic check: does the source look like x86-64 NASM assembly?

    Returns True if it contains section directives or x86-specific registers.
    """
    lower = source.lower()
    if "section .data" in lower or "section .text" in lower:
        return True
    if re.search(r'\b(rax|rbx|rcx|rdx|rsi|rdi|eax|ebx|ecx|edx|syscall)\b', lower):
        return True
    return False


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

def _split_sections(
    lines: list[str],
) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """
    Split source lines into .data and .text sections.

    Returns (data_lines, text_lines) as lists of (line_number, line_content).
    """
    data_lines: list[tuple[int, str]] = []
    text_lines: list[tuple[int, str]] = []
    current_section: str | None = None

    for line_num_0, raw_line in enumerate(lines):
        line = raw_line.split(";")[0].strip()  # strip comments
        if not line:
            continue

        lower = line.lower()
        if lower == "section .data":
            current_section = "data"
            continue
        elif lower == "section .text":
            current_section = "text"
            continue

        if current_section == "data":
            data_lines.append((line_num_0 + 1, line))
        elif current_section == "text":
            text_lines.append((line_num_0 + 1, line))
        # Lines before any section declaration are ignored (or could be directives)

    return data_lines, text_lines


# ---------------------------------------------------------------------------
# .data section parsing
# ---------------------------------------------------------------------------

def _parse_data_section(
    data_lines: list[tuple[int, str]],
) -> tuple[dict[str, DataSymbol], dict[str, int], bytes]:
    """
    Parse .data section lines.

    Handles:
      - ``array dd 34, 7, 23, 32, 5, 62``
      - ``n equ ($ - array) / 4``

    Returns (data_symbols, constants, data_segment_bytes).
    """
    data_symbols: dict[str, DataSymbol] = {}
    constants: dict[str, int] = {}
    data_bytes = bytearray()
    current_offset = 0  # byte offset within data segment

    for line_num, line in data_lines:
        # Try equ directive: name equ expr
        equ_match = re.match(
            r'^([A-Za-z_]\w*)\s+equ\s+(.+)$', line, re.IGNORECASE,
        )
        if equ_match:
            name = equ_match.group(1)
            expr = equ_match.group(2).strip()
            value = _evaluate_equ_expr(expr, current_offset, data_symbols, line_num)
            constants[name] = value
            continue

        # Try dd directive: name dd val1, val2, ...
        dd_match = re.match(
            r'^([A-Za-z_]\w*)\s+dd\s+(.+)$', line, re.IGNORECASE,
        )
        if dd_match:
            name = dd_match.group(1)
            values_str = dd_match.group(2)
            values = [int(v.strip()) for v in values_str.split(",")]
            size = len(values) * 4  # 4 bytes per dword

            symbol = DataSymbol(
                name=name,
                address=DATA_BASE_ADDRESS + current_offset,
                size=size,
                values=values,
            )
            data_symbols[name] = symbol

            # Write dwords to data segment (little-endian)
            for val in values:
                data_bytes.extend(val.to_bytes(4, byteorder="little", signed=True))

            current_offset += size
            continue

        # Try db directive: name db val1, val2, ...
        db_match = re.match(
            r'^([A-Za-z_]\w*)\s+db\s+(.+)$', line, re.IGNORECASE,
        )
        if db_match:
            name = db_match.group(1)
            values_str = db_match.group(2)
            values = [int(v.strip()) for v in values_str.split(",")]
            size = len(values)

            symbol = DataSymbol(
                name=name,
                address=DATA_BASE_ADDRESS + current_offset,
                size=size,
                values=values,
            )
            data_symbols[name] = symbol

            for val in values:
                data_bytes.extend(val.to_bytes(1, byteorder="little", signed=True))

            current_offset += size
            continue

        # Unknown data directive — skip or warn
        logger.warning("Ignoring unrecognized .data line %d: %s", line_num, line)

    return data_symbols, constants, bytes(data_bytes)


def _evaluate_equ_expr(
    expr: str,
    current_offset: int,
    data_symbols: dict[str, DataSymbol],
    line_num: int,
) -> int:
    """
    Evaluate an equ expression.

    Supports:
      - ``($ - array) / 4``  — count of dword elements
      - Simple integer literals
      - Arithmetic with +, -, *, /

    ``$`` represents the current byte offset (from data segment base).
    """
    # Replace $ with current offset (absolute address)
    resolved = expr.replace("$", str(DATA_BASE_ADDRESS + current_offset))

    # Replace symbol names with their addresses
    for sym_name, sym in data_symbols.items():
        resolved = re.sub(
            rf'\b{re.escape(sym_name)}\b',
            str(sym.address),
            resolved,
        )

    # Evaluate the arithmetic expression safely
    try:
        # Only allow digits, operators, parentheses, whitespace
        if not re.match(r'^[\d\s\+\-\*\/\(\)]+$', resolved):
            raise ParseError(
                f"Unsafe equ expression: '{expr}' → '{resolved}'", line_num,
            )
        value = int(eval(resolved))  # noqa: S307 — input is sanitised above
        return value
    except Exception as exc:
        raise ParseError(
            f"Cannot evaluate equ expression '{expr}': {exc}", line_num,
        ) from exc


# ---------------------------------------------------------------------------
# .text section parsing
# ---------------------------------------------------------------------------

def _parse_text_section(
    text_lines: list[tuple[int, str]],
    data_symbols: dict[str, DataSymbol],
    constants: dict[str, int],
) -> tuple[list[X86Instruction], dict[str, int]]:
    """
    Parse .text section: extract labels and instructions.

    Two-pass:
      Pass 1: identify labels → instruction index.
      Pass 2: parse each instruction line.
    """
    labels: dict[str, int] = {}
    instructions: list[X86Instruction] = []

    # --- Pass 1: Clean lines, extract labels ---
    clean_lines: list[tuple[int, str]] = []
    instruction_index = 0

    for line_num, line in text_lines:
        # Skip 'global' directive
        if line.strip().lower().startswith("global"):
            continue

        # Check for label definition
        label, remainder = _extract_label(line)
        if label is not None:
            if label in labels:
                raise ParseError(f"Duplicate label '{label}'", line_num)
            labels[label] = instruction_index
            if remainder:
                clean_lines.append((line_num, remainder))
                instruction_index += 1
        else:
            clean_lines.append((line_num, line))
            instruction_index += 1

    # --- Pass 2: Parse instructions ---
    for line_num, line in clean_lines:
        try:
            instr = _parse_x86_instruction(line, line_num, data_symbols, constants)
            instructions.append(instr)
        except (InvalidInstructionError, ParseError):
            raise
        except Exception as exc:
            raise ParseError(str(exc), line_num) from exc

    return instructions, labels


def _extract_label(line: str) -> tuple[str | None, str]:
    """
    Extract a label definition from the start of a line.

    Returns (label_name, remainder) or (None, original_line).
    """
    # Match "label_name:" at the start
    m = re.match(r'^([A-Za-z_]\w*)\s*:', line)
    if m:
        label = m.group(1)
        remainder = line[m.end():].strip()
        return label, remainder
    return None, line


def _parse_x86_instruction(
    line: str,
    line_num: int,
    data_symbols: dict[str, DataSymbol],
    constants: dict[str, int],
) -> X86Instruction:
    """Parse a single x86-64 instruction line."""
    line = line.strip()
    if not line:
        raise ParseError("Empty instruction", line_num)

    # Extract opcode (first token)
    parts = line.split(None, 1)
    opcode = parts[0].lower()
    operands_str = parts[1].strip() if len(parts) > 1 else ""

    # Zero-operand instructions
    if opcode in _ZERO_OPERAND_INSTRS:
        return X86Instruction(opcode=opcode, operands=[], raw=line, line_number=line_num)

    # Jump instructions: single label operand
    if opcode in _JUMP_INSTRS:
        label = operands_str.strip()
        if not label:
            raise InvalidInstructionError(f"{opcode} requires a label operand", line_num)
        return X86Instruction(opcode=opcode, operands=[label], raw=line, line_number=line_num)

    # Parse operands for all other instructions
    operands = _parse_operands(operands_str, line_num, data_symbols, constants)

    return X86Instruction(opcode=opcode, operands=operands, raw=line, line_number=line_num)


# ---------------------------------------------------------------------------
# Operand parsing
# ---------------------------------------------------------------------------

def _parse_operands(
    operands_str: str,
    line_num: int,
    data_symbols: dict[str, DataSymbol],
    constants: dict[str, int],
) -> list[Any]:
    """
    Parse the operand string of an x86-64 instruction.

    Splits by commas (respecting brackets), then classifies each operand as:
      - register name (str)
      - immediate integer (int)
      - MemoryOperand (complex addressing)
      - constant name resolved to int
    """
    if not operands_str:
        return []

    # Split by commas, but not inside brackets
    raw_operands = _split_operands(operands_str)
    parsed: list[Any] = []

    for raw_op in raw_operands:
        op = raw_op.strip()
        if not op:
            continue
        parsed.append(_parse_single_operand(op, line_num, data_symbols, constants))

    return parsed


def _split_operands(operands_str: str) -> list[str]:
    """
    Split operand string by commas, respecting bracket nesting.

    E.g. "[array + rcx*4 + 4], eax" → ["[array + rcx*4 + 4]", "eax"]
    """
    result: list[str] = []
    current: list[str] = []
    depth = 0

    for char in operands_str:
        if char == "[":
            depth += 1
            current.append(char)
        elif char == "]":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            result.append("".join(current).strip())
            current = []
        else:
            current.append(char)

    if current:
        result.append("".join(current).strip())

    return result


def _parse_single_operand(
    op: str,
    line_num: int,
    data_symbols: dict[str, DataSymbol],
    constants: dict[str, int],
) -> Any:
    """
    Classify and parse a single operand.

    Returns:
      - str: if it's a register name
      - int: if it's an immediate value or resolved constant
      - MemoryOperand: if it's a memory reference [...]
    """
    # Memory operand: [...]
    if op.startswith("[") and op.endswith("]"):
        return _parse_memory_operand(op[1:-1].strip(), line_num, data_symbols)

    # Register
    lower = op.lower()
    if lower in _ALL_REGS:
        return lower

    # Immediate integer
    try:
        return int(op, 0)  # supports 0x hex prefix too
    except ValueError:
        pass

    # Named constant
    if op in constants:
        return constants[op]

    # Could be a symbol name used as immediate (address)
    if op in data_symbols:
        return data_symbols[op].address

    raise InvalidInstructionError(
        f"Unrecognized operand '{op}'", line_num,
    )


def _parse_memory_operand(
    inner: str,
    line_num: int,
    data_symbols: dict[str, DataSymbol],
) -> MemoryOperand:
    """
    Parse the contents of a memory reference (inside brackets).

    Supports forms:
      - [array]
      - [array + rcx*4]
      - [array + rcx*4 + 4]
      - [rax]
      - [rax + rbx*2 + 8]
      - [rax + 8]
    """
    mem = MemoryOperand()

    # Tokenize: split by + and -, keeping the sign
    # First normalize spaces around operators
    inner = inner.strip()

    # Split into additive terms, preserving sign
    # e.g. "array + rcx*4 + 4" → [("", "array"), ("+", "rcx*4"), ("+", "4")]
    terms = _tokenize_address_expr(inner)

    for sign, term in terms:
        term = term.strip()
        if not term:
            continue

        sign_mult = 1 if sign in ("", "+") else -1

        # Check for reg*scale pattern
        scale_match = re.match(r'^(\w+)\s*\*\s*(\d+)$', term)
        if scale_match:
            reg = scale_match.group(1).lower()
            scale = int(scale_match.group(2))
            if reg in _ALL_REGS:
                mem.index_reg = reg
                mem.scale = scale * sign_mult
            else:
                raise InvalidInstructionError(
                    f"Invalid index register '{reg}' in memory operand", line_num,
                )
            continue

        # Check for scale*reg pattern (reversed)
        scale_match2 = re.match(r'^(\d+)\s*\*\s*(\w+)$', term)
        if scale_match2:
            scale = int(scale_match2.group(1))
            reg = scale_match2.group(2).lower()
            if reg in _ALL_REGS:
                mem.index_reg = reg
                mem.scale = scale * sign_mult
            else:
                raise InvalidInstructionError(
                    f"Invalid index register '{reg}' in memory operand", line_num,
                )
            continue

        # Numeric displacement
        try:
            mem.displacement += int(term, 0) * sign_mult
            continue
        except ValueError:
            pass

        # Register (base or index without scale)
        lower = term.lower()
        if lower in _ALL_REGS:
            if mem.base_reg is None and mem.base_symbol is None:
                mem.base_reg = lower
            elif mem.index_reg is None:
                mem.index_reg = lower
                mem.scale = sign_mult  # scale = 1 (or -1)
            else:
                raise InvalidInstructionError(
                    f"Too many registers in memory operand: '{inner}'", line_num,
                )
            continue

        # Symbol name
        if term in data_symbols:
            mem.base_symbol = term
            continue

        # Unknown token
        raise InvalidInstructionError(
            f"Unrecognized token '{term}' in memory operand '[{inner}]'", line_num,
        )

    return mem


def _tokenize_address_expr(expr: str) -> list[tuple[str, str]]:
    """
    Tokenize an address expression into (sign, term) pairs.

    "array + rcx*4 + 4" → [("", "array"), ("+", "rcx*4"), ("+", "4")]
    "rax - 8"           → [("", "rax"), ("-", "8")]
    """
    # Split by + and - while keeping the delimiter
    tokens = re.split(r'\s*(\+|-)\s*', expr)
    result: list[tuple[str, str]] = []

    sign = ""
    for token in tokens:
        token = token.strip()
        if token in ("+", "-"):
            sign = token
        elif token:
            result.append((sign, token))
            sign = ""

    return result
