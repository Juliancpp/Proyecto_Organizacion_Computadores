"""
ISA specification loader and instruction validator.

Loads isa_spec.json and exposes helpers that the execution engines use
to validate opcodes and operand counts at parse time.  This ensures the
engines strictly follow the formal ISA definition.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

_SPEC_PATH = os.path.join(os.path.dirname(__file__), "isa_spec.json")


@lru_cache(maxsize=1)
def load_spec() -> dict[str, Any]:
    """Load and cache the ISA specification from isa_spec.json."""
    with open(_SPEC_PATH, encoding="utf-8") as f:
        return json.load(f)


def risc_opcodes() -> frozenset[str]:
    """Return the set of valid RISC opcodes from the spec."""
    spec = load_spec()
    return frozenset(spec["risc"]["instructions"].keys())


def cisc_opcodes() -> frozenset[str]:
    """Return the set of valid CISC opcodes from the spec."""
    spec = load_spec()
    return frozenset(spec["cisc"]["instructions"].keys())


def risc_cycle_cost(opcode: str) -> int:
    """Return the cycle cost for a RISC instruction (from spec)."""
    spec = load_spec()
    instr = spec["risc"]["instructions"].get(opcode)
    if instr is None:
        raise KeyError(f"Unknown RISC opcode '{opcode}'")
    return instr["cycle_cost"]


def cisc_total_cycles(opcode: str) -> int:
    """Return the total cycle cost (fetch/decode + µ-ops) for a CISC instruction."""
    spec = load_spec()
    instr = spec["cisc"]["instructions"].get(opcode)
    if instr is None:
        raise KeyError(f"Unknown CISC opcode '{opcode}'")
    return instr["total_cycles"]


def risc_operand_count(opcode: str) -> int:
    """Return the expected operand count for a RISC instruction."""
    spec = load_spec()
    instr = spec["risc"]["instructions"].get(opcode)
    if instr is None:
        raise KeyError(f"Unknown RISC opcode '{opcode}'")
    return len(instr["operands"])


def cisc_operand_count(opcode: str) -> int:
    """Return the expected operand count for a CISC instruction."""
    spec = load_spec()
    instr = spec["cisc"]["instructions"].get(opcode)
    if instr is None:
        raise KeyError(f"Unknown CISC opcode '{opcode}'")
    return len(instr["operands"])


def simulation_modes() -> dict[str, Any]:
    """Return the simulation mode definitions from the spec."""
    return load_spec()["simulation_modes"]


def equivalence_contract() -> dict[str, Any]:
    """Return the semantic equivalence contract definition."""
    return load_spec()["equivalence_contract"]
