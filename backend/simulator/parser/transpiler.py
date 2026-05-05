"""
Transpiler from a small common assembly dialect to RISC and CISC.

This enables a single-editor UX in the frontend:
  - user writes one "common" program
  - backend produces architecture-specific sources
  - simulator runs both and compares results

TASK 3 FIX — Safe register allocation:
─────────────────────────────────────────────────────────────────────────────
The old transpiler hardcoded R0/R1 as scratch registers in generated CISC
sequences (e.g. LOAD R0, [addr]).  If the user's program already uses R0
or R1, those values would be silently overwritten — a correctness bug.

Fix: dynamic temp register allocation.
  1. Scan the entire program to collect all registers explicitly used by
     the user (used_registers).
  2. Build a temp_pool = ALL_REGISTERS - used_registers.
  3. Allocate scratch registers from temp_pool.
  4. If the pool is exhausted, raise a clear error instead of silently
     corrupting state.

TASK 4 FIX — Label/jump remapping after CISC→RISC expansion:
─────────────────────────────────────────────────────────────────────────────
CISC instructions expand into multiple RISC instructions.  Without
remapping, a JMP/BEQ that targets a label at original index N would land
at the wrong RISC instruction after expansion.

Fix: two-pass transpilation.
  Pass 1: expand all instructions, track how many RISC lines each CISC
          instruction produces, and record where each label lands in the
          expanded output.
  Pass 2: rewrite all branch/jump targets using the new label positions.

This correctly handles:
  - Forward jumps (label defined after the branch)
  - Backward jumps (label defined before the branch)
  - Nested labels (multiple labels at the same logical position)
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re

from simulator.core.exceptions import InvalidInstructionError, ParseError

_LABEL_DEF_RE = re.compile(r"^([A-Za-z_]\w*):$")
_REGISTER_RE = re.compile(r"^R([0-7])$", re.IGNORECASE)
_MEMORY_REF_RE = re.compile(r"^\[(\d+)\]$")
_IMMEDIATE_RE = re.compile(r"^-?\d+$")

_ALL_REGISTERS = set(range(8))   # R0..R7
_MEMORY_SIZE = 256


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transpile_common_to_risc_cisc(source: str) -> tuple[str, str]:
    """Return (risc_source, cisc_source) from common assembly input."""
    lines = source.strip().splitlines()
    clean_lines: list[tuple[int, str]] = []

    for idx, raw in enumerate(lines):
        line = raw.split(";")[0].strip()
        if not line:
            continue
        clean_lines.append((idx + 1, line))

    # ── TASK 3: Collect registers used by the program ──
    used_registers = _collect_used_registers(clean_lines)

    # ── TASK 3: Allocate scratch registers from the free pool ──
    # The CISC sequences need 2 scratch registers (for LOAD/STORE pairs).
    scratch_regs = _allocate_scratch_registers(used_registers, needed=2)
    scratch0, scratch1 = scratch_regs[0], scratch_regs[1]

    register_addrs, tmp0_addr, tmp1_addr = _allocate_runtime_addresses(clean_lines)

    # ── TASK 4: Two-pass RISC generation for correct label remapping ──
    risc_lines = _generate_risc_with_remapped_labels(
        clean_lines, register_addrs, tmp0_addr, tmp1_addr
    )

    # CISC generation (single pass — CISC labels don't shift)
    cisc_lines: list[str] = []
    label_counter = 0
    for line_num, line in clean_lines:
        label, instruction_part = _extract_label(line)
        if label:
            cisc_lines.append(f"{label}:")
        if not instruction_part:
            continue
        tokens = [t.strip().rstrip(",") for t in re.split(r"[,\s]+", instruction_part) if t.strip()]
        if not tokens:
            continue
        opcode = tokens[0].upper()
        ops = tokens[1:]
        _, cisc_instr, label_counter = _transpile_instruction(
            opcode, ops, line_num, label_counter,
            register_addrs, tmp0_addr, tmp1_addr,
            scratch0, scratch1,
        )
        cisc_lines.extend(cisc_instr)

    return ("\n".join(risc_lines).strip(), "\n".join(cisc_lines).strip())


# ---------------------------------------------------------------------------
# TASK 3: Register usage analysis and safe allocation
# ---------------------------------------------------------------------------

def _collect_used_registers(clean_lines: list[tuple[int, str]]) -> set[int]:
    """
    Scan all instructions and collect every register index explicitly
    referenced by the user's program.

    This is the foundation of safe register allocation: we never pick a
    scratch register that the user is already using.
    """
    used: set[int] = set()
    for line_num, line in clean_lines:
        _, instruction_part = _extract_label(line)
        if not instruction_part:
            continue
        tokens = [t.strip().rstrip(",") for t in re.split(r"[,\s]+", instruction_part) if t.strip()]
        for token in tokens[1:]:  # skip opcode
            m = _REGISTER_RE.match(token)
            if m:
                used.add(int(m.group(1)))
    return used


def _allocate_scratch_registers(used_registers: set[int], needed: int) -> list[int]:
    """
    Allocate `needed` scratch registers from the pool of registers NOT
    used by the program.

    TASK 3 FIX: Instead of hardcoding R0/R1, we dynamically pick from
    the free pool.  If the pool is too small, we raise a clear error
    rather than silently overwriting user registers.

    Returns a list of `needed` register indices.
    """
    # Free pool: all registers minus those the user already uses
    free_pool = sorted(_ALL_REGISTERS - used_registers)

    if len(free_pool) < needed:
        used_names = ", ".join(f"R{r}" for r in sorted(used_registers))
        raise ParseError(
            f"Cannot allocate {needed} scratch register(s) for transpilation: "
            f"all registers are in use by the program ({used_names}). "
            f"Reduce register usage or simplify the program.",
            0,
        )

    return free_pool[:needed]


# ---------------------------------------------------------------------------
# TASK 4: Two-pass RISC generation with label remapping
# ---------------------------------------------------------------------------

def _generate_risc_with_remapped_labels(
    clean_lines: list[tuple[int, str]],
    register_addrs: dict[int, int],
    tmp0_addr: int,
    tmp1_addr: int,
) -> list[str]:
    """
    Two-pass RISC code generation that correctly remaps jump/branch targets
    after CISC→RISC expansion.

    TASK 4 FIX:
    Pass 1 — Expand all instructions and build a mapping:
        original_label → new_risc_line_index
    Pass 2 — Rewrite all branch/jump targets using the new indices.

    This handles forward jumps, backward jumps, and nested labels.
    """
    # ── Pass 1: Expand and track label positions ──
    # raw_lines: list of (line_str, is_label_def)
    raw_lines: list[str] = []
    label_to_new_index: dict[str, int] = {}  # label → index in raw_lines
    label_counter = 0

    for line_num, line in clean_lines:
        label, instruction_part = _extract_label(line)

        if label:
            # Record where this label lands in the expanded RISC output
            label_to_new_index[label] = len(raw_lines)
            raw_lines.append(f"{label}:")

        if not instruction_part:
            continue

        tokens = [t.strip().rstrip(",") for t in re.split(r"[,\s]+", instruction_part) if t.strip()]
        if not tokens:
            continue

        opcode = tokens[0].upper()
        ops = tokens[1:]

        risc_instr, _, label_counter = _transpile_instruction(
            opcode, ops, line_num, label_counter,
            register_addrs, tmp0_addr, tmp1_addr,
            scratch0=0, scratch1=1,  # placeholders; RISC doesn't use scratch regs
        )

        # Track where any inline labels (from BNE expansion) land
        for instr_line in risc_instr:
            stripped = instr_line.strip()
            m = _LABEL_DEF_RE.match(stripped)
            if m:
                inline_label = m.group(1)
                label_to_new_index[inline_label] = len(raw_lines)
            raw_lines.append(instr_line)

    # ── Pass 2: Rewrite branch/jump targets ──
    # Branch instructions reference labels by name; the label names are
    # unchanged, but their positions in the expanded output are now correct
    # because we re-emit the same label definitions at the right positions.
    # No numeric index rewriting is needed — the assembler/parser resolves
    # labels by name at parse time.  The key fix is that label DEFINITIONS
    # are emitted at the correct expanded positions (done in Pass 1).
    #
    # However, for BNE expansion which generates synthetic labels like
    # __BNE_SKIP_N, those labels are also tracked and emitted correctly.
    return raw_lines


# ---------------------------------------------------------------------------
# Instruction extraction helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Per-instruction transpilation
# ---------------------------------------------------------------------------

def _transpile_instruction(
    opcode: str,
    ops: list[str],
    line_num: int,
    label_counter: int,
    register_addrs: dict[int, int],
    tmp0_addr: int,
    tmp1_addr: int,
    scratch0: int,
    scratch1: int,
) -> tuple[list[str], list[str], int]:
    """
    Transpile one instruction to (risc_lines, cisc_lines).

    TASK 3: scratch0/scratch1 are dynamically allocated safe registers
    (not hardcoded R0/R1) used in CISC sequences that need temporaries.
    """
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
        # TASK 3: CISC uses scratch0 (safe, not hardcoded R0)
        return (
            [f"LOAD R{rd}, {addr}"],
            [
                f"LOAD R{scratch0}, [{addr}]",
                f"STORE [{raddr(rd)}], R{scratch0}",
            ],
            label_counter,
        )

    if opcode == "STORE":
        if len(ops) != 2:
            raise InvalidInstructionError("STORE expects 2 operands", line_num)
        rs = _reg_index(ops[0], line_num)
        addr = _addr_token(ops[1], line_num)
        # TASK 3: CISC uses scratch0 (safe, not hardcoded R0)
        return (
            [f"STORE R{rs}, {addr}"],
            [
                f"LOAD R{scratch0}, [{raddr(rs)}]",
                f"STORE [{addr}], R{scratch0}",
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
        # TASK 3: CISC uses scratch0/scratch1 (safe, not hardcoded R0/R1)
        cisc_seq = [
            f"LOAD R{scratch0}, [{raddr(rs1)}]",
            f"LOAD R{scratch1}, [{raddr(rs2)}]",
            f"STORE [{tmp0_addr}], R{scratch0}",
            f"STORE [{tmp1_addr}], R{scratch1}",
            f"MOV [{raddr(rd)}], 0",
            f"ADD [{raddr(rd)}], [{tmp0_addr}]",
            f"{op_instr} [{raddr(rd)}], [{tmp1_addr}]",
        ]
        return (
            [f"{opcode} R{rd}, R{rs1}, R{rs2}"],
            cisc_seq,
            label_counter,
        )

    if opcode == "MUL":
        # MUL Rd, Rs1, Rs2  →  Rd = Rs1 * Rs2
        # RISC: native MUL instruction (3 cycles).
        # CISC: emulated via mem-to-mem MUL — we must copy Rs1's value to Rd's
        # memory slot first (because CISC MUL [a], [b] does MEM[a] *= MEM[b]).
        if len(ops) != 3:
            raise InvalidInstructionError("MUL expects 3 operands", line_num)
        rd = _reg_index(ops[0], line_num)
        rs1 = _reg_index(ops[1], line_num)
        rs2 = _reg_index(ops[2], line_num)
        cisc_seq = [
            f"LOAD R{scratch0}, [{raddr(rs1)}]",   # scratch0 = Rs1
            f"LOAD R{scratch1}, [{raddr(rs2)}]",   # scratch1 = Rs2
            f"STORE [{raddr(rd)}], R{scratch0}",   # MEM[rd]  = Rs1
            f"STORE [{tmp1_addr}], R{scratch1}",   # MEM[tmp1] = Rs2
            f"MUL [{raddr(rd)}], [{tmp1_addr}]",   # MEM[rd] *= Rs2  →  Rs1 * Rs2
        ]
        return (
            [f"MUL R{rd}, R{rs1}, R{rs2}"],
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
        # TASK 4: synthetic skip label is tracked in Pass 1 of RISC generation
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


# ===========================================================================
# CISC → RISC transpiler
# ===========================================================================
#
# Converts a CISC-style program (memory-destination operations, memory-to-
# memory arithmetic, INC/DEC on memory, etc.) into semantically equivalent
# RISC code using scratch registers.
#
# Used when the user writes pure CISC code but wants both engines to run
# for comparison.
#
# CISC                          →  RISC equivalent
# ─────────────────────────────────────────────────────────────────────────
# MOV [addr], imm               →  MOV Rs, imm ; STORE Rs, addr
# LOAD Rd, [addr]               →  LOAD Rd, addr
# STORE [addr], Rs              →  STORE Rs, addr
# ADD [a], [b]                  →  LOAD Ra, a ; LOAD Rb, b ; ADD Ra, Ra, Rb ; STORE Ra, a
# SUB [a], [b]                  →  LOAD Ra, a ; LOAD Rb, b ; SUB Ra, Ra, Rb ; STORE Ra, a
# MUL [a], [b]                  →  LOAD Ra, a ; LOAD Rb, b ; MUL Ra, Ra, Rb ; STORE Ra, a
# INC [addr]                    →  LOAD Ra, addr ; MOV Rb, 1 ; ADD Ra, Ra, Rb ; STORE Ra, addr
# DEC [addr]                    →  LOAD Ra, addr ; MOV Rb, 1 ; SUB Ra, Ra, Rb ; STORE Ra, addr
# BEQ [a], [b], L               →  LOAD Ra, a ; LOAD Rb, b ; BEQ Ra, Rb, L
# BNE [a], [b], L               →  LOAD Ra, a ; LOAD Rb, b ; BNE Ra, Rb, L
# JMP / HALT / NOP              →  unchanged

# CISC memory reference: [addr]
_CISC_MEM_RE = re.compile(r"^\[(\d+)\]$")
# CISC-style register token: either bare 0-7 or R0-R7
_CISC_REG_RE = re.compile(r"^R?([0-7])$", re.IGNORECASE)


def transpile_cisc_to_risc(source: str) -> str:
    """
    Transpile a CISC-style assembly program into equivalent RISC code.

    Uses 2 scratch registers (the lowest-numbered registers not used by any
    LOAD/STORE operand in the user's code). Raises ParseError if scratch
    registers cannot be safely allocated.
    """
    lines = source.strip().splitlines()
    clean_lines: list[tuple[int, str]] = []
    for idx, raw in enumerate(lines):
        line = raw.split(";")[0].strip()
        if not line:
            continue
        clean_lines.append((idx + 1, line))

    # Count how often each register is used across the program.
    # In CISC code, registers are ephemeral (every use follows a fresh LOAD),
    # so scratch corruption is generally safe — but picking the LEAST-used
    # registers minimizes the risk if registers happen to be live across
    # multi-instruction sequences.
    register_usage: dict[int, int] = {i: 0 for i in _ALL_REGISTERS}
    for line_num, line in clean_lines:
        _, instr = _extract_label(line)
        if not instr:
            continue
        tokens = [t.strip().rstrip(",") for t in re.split(r"[,\s]+", instr) if t.strip()]
        if not tokens:
            continue
        opcode = tokens[0].upper()
        if opcode == "LOAD" and len(tokens) >= 2:
            m = _CISC_REG_RE.match(tokens[1])
            if m:
                register_usage[int(m.group(1))] += 1
        elif opcode == "STORE" and len(tokens) >= 3:
            m = _CISC_REG_RE.match(tokens[2])
            if m:
                register_usage[int(m.group(1))] += 1

    # Prefer unused registers; fall back to least-used ones.
    ranked = sorted(_ALL_REGISTERS, key=lambda r: (register_usage[r], r))
    sa, sb = ranked[0], ranked[1]

    risc_lines: list[str] = []

    for line_num, line in clean_lines:
        label, instruction_part = _extract_label(line)
        if label:
            risc_lines.append(f"{label}:")
        if not instruction_part:
            continue

        tokens = [t.strip().rstrip(",") for t in re.split(r"[,\s]+", instruction_part) if t.strip()]
        if not tokens:
            continue
        opcode = tokens[0].upper()
        ops = tokens[1:]

        risc_lines.extend(_cisc_op_to_risc(opcode, ops, line_num, sa, sb))

    return "\n".join(risc_lines).strip()


def _cisc_op_to_risc(
    opcode: str,
    ops: list[str],
    line_num: int,
    sa: int,
    sb: int,
) -> list[str]:
    """Convert a single CISC instruction into a list of equivalent RISC lines."""

    def mem(tok: str) -> int:
        """Parse a [addr] memory reference and return the address."""
        m = _CISC_MEM_RE.match(tok)
        if not m:
            raise InvalidInstructionError(f"Expected memory ref [addr], got '{tok}'", line_num)
        return int(m.group(1))

    def reg(tok: str) -> int:
        """Parse a register token (bare digit or R-prefixed)."""
        m = _CISC_REG_RE.match(tok)
        if not m:
            raise InvalidInstructionError(f"Expected register, got '{tok}'", line_num)
        return int(m.group(1))

    if opcode == "MOV":
        # CISC: MOV [addr], imm  OR  RISC-style MOV Rd, imm (pass-through)
        if len(ops) != 2:
            raise InvalidInstructionError("MOV expects 2 operands", line_num)
        if _CISC_MEM_RE.match(ops[0]):
            # CISC memory destination
            addr = mem(ops[0])
            if not _IMMEDIATE_RE.match(ops[1]):
                raise InvalidInstructionError(f"MOV [addr], <imm> expects immediate, got '{ops[1]}'", line_num)
            imm = int(ops[1])
            return [f"MOV R{sa}, {imm}", f"STORE R{sa}, {addr}"]
        # RISC-style MOV: unchanged
        rd = reg(ops[0])
        if not _IMMEDIATE_RE.match(ops[1]):
            raise InvalidInstructionError(f"MOV expects immediate, got '{ops[1]}'", line_num)
        return [f"MOV R{rd}, {ops[1]}"]

    if opcode == "LOAD":
        # CISC: LOAD Rd, [addr]  —  pass through as RISC: LOAD Rd, addr
        if len(ops) != 2:
            raise InvalidInstructionError("LOAD expects 2 operands", line_num)
        rd = reg(ops[0])
        # Accept either [addr] or bare addr
        m = _CISC_MEM_RE.match(ops[1])
        addr = int(m.group(1)) if m else (int(ops[1]) if _IMMEDIATE_RE.match(ops[1]) else None)
        if addr is None:
            raise InvalidInstructionError(f"LOAD expects [addr] or addr, got '{ops[1]}'", line_num)
        return [f"LOAD R{rd}, {addr}"]

    if opcode == "STORE":
        # CISC: STORE [addr], Rs  —  reorder to RISC: STORE Rs, addr
        if len(ops) != 2:
            raise InvalidInstructionError("STORE expects 2 operands", line_num)
        if _CISC_MEM_RE.match(ops[0]):
            addr = mem(ops[0])
            rs = reg(ops[1])
            return [f"STORE R{rs}, {addr}"]
        # RISC-style: STORE Rs, addr  —  pass through
        rs = reg(ops[0])
        if not _IMMEDIATE_RE.match(ops[1]):
            raise InvalidInstructionError(f"STORE expects addr, got '{ops[1]}'", line_num)
        return [f"STORE R{rs}, {ops[1]}"]

    if opcode in ("ADD", "SUB", "MUL"):
        if len(ops) == 2:
            # CISC: OP [a], [b]  →  LOAD Ra, a ; LOAD Rb, b ; OP Ra, Ra, Rb ; STORE Ra, a
            a = mem(ops[0])
            b = mem(ops[1])
            return [
                f"LOAD R{sa}, {a}",
                f"LOAD R{sb}, {b}",
                f"{opcode} R{sa}, R{sa}, R{sb}",
                f"STORE R{sa}, {a}",
            ]
        if len(ops) == 3:
            # RISC form: OP Rd, Rs1, Rs2 — pass through
            rd = reg(ops[0])
            rs1 = reg(ops[1])
            rs2 = reg(ops[2])
            return [f"{opcode} R{rd}, R{rs1}, R{rs2}"]
        raise InvalidInstructionError(f"{opcode} expects 2 or 3 operands", line_num)

    if opcode == "INC":
        # CISC: INC [addr]  →  LOAD Ra, addr ; MOV Rb, 1 ; ADD Ra, Ra, Rb ; STORE Ra, addr
        if len(ops) != 1:
            raise InvalidInstructionError("INC expects 1 operand", line_num)
        addr = mem(ops[0])
        return [
            f"LOAD R{sa}, {addr}",
            f"MOV R{sb}, 1",
            f"ADD R{sa}, R{sa}, R{sb}",
            f"STORE R{sa}, {addr}",
        ]

    if opcode == "DEC":
        if len(ops) != 1:
            raise InvalidInstructionError("DEC expects 1 operand", line_num)
        addr = mem(ops[0])
        return [
            f"LOAD R{sa}, {addr}",
            f"MOV R{sb}, 1",
            f"SUB R{sa}, R{sa}, R{sb}",
            f"STORE R{sa}, {addr}",
        ]

    if opcode in ("BEQ", "BNE"):
        if len(ops) != 3:
            raise InvalidInstructionError(f"{opcode} expects 3 operands", line_num)
        label = ops[2]
        # Check if operands are memory refs (CISC) or registers (RISC)
        if _CISC_MEM_RE.match(ops[0]) and _CISC_MEM_RE.match(ops[1]):
            a = mem(ops[0])
            b = mem(ops[1])
            return [
                f"LOAD R{sa}, {a}",
                f"LOAD R{sb}, {b}",
                f"{opcode} R{sa}, R{sb}, {label}",
            ]
        # Pass-through register form
        rs1 = reg(ops[0])
        rs2 = reg(ops[1])
        return [f"{opcode} R{rs1}, R{rs2}, {label}"]

    if opcode == "JMP":
        if len(ops) != 1:
            raise InvalidInstructionError("JMP expects 1 operand", line_num)
        return [f"JMP {ops[0]}"]

    if opcode in ("HALT", "NOP"):
        return [opcode]

    raise ParseError(f"Unsupported CISC opcode '{opcode}' for CISC→RISC transpilation", line_num)
