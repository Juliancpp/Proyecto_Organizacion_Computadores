"""
Comprehensive academic test suite for the RISC/CISC CPU simulator.

Covers:
  1. ISA spec validation (opcodes, operand counts, cycle costs)
  2. Semantic equivalence (RISC == CISC final state)
  3. Basic arithmetic (ADD, SUB, MOV)
  4. Memory operations (LOAD, STORE)
  5. Control flow (JMP, BEQ, BNE, loops)
  6. CISC-specific (µ-op decomposition, MUL, INC, DEC)
  7. Edge cases (register conflicts, memory overwrite, pipeline vs no-pipeline)
  8. Cycle model correctness
  9. simulationMode flag
"""

import json

from django.test import TestCase, Client

from simulator.core.cpu_state import CPUState, CPUSnapshot
from simulator.core.events import Event, Component
from simulator.core.exceptions import (
    ParseError,
    InvalidInstructionError,
    ExecutionError,
)
from simulator.core.isa import (
    risc_opcodes, cisc_opcodes,
    risc_cycle_cost, cisc_total_cycles,
    risc_operand_count, cisc_operand_count,
    simulation_modes, equivalence_contract,
)
from simulator.parser.assembly_parser import parse_risc, parse_cisc
from simulator.parser.transpiler import transpile_common_to_risc_cisc
from simulator.risc.engine import execute_risc, CYCLE_COSTS
from simulator.risc.pipeline import execute_risc_pipeline
from simulator.cisc.engine import execute_cisc
from simulator.metrics.calculator import (
    compute_metrics,
    count_executed_instructions,
    compare,
)


# =========================================================================
# HELPER: run both architectures and compare final state
# =========================================================================

def _run_risc(code: str) -> CPUState:
    return execute_risc(parse_risc(code))


def _run_cisc(code: str) -> CPUState:
    return execute_cisc(parse_cisc(code))


def _final_registers(state: CPUState) -> list[int]:
    return list(state.registers)


def _final_memory(state: CPUState) -> dict[int, int]:
    return dict(state.memory)


# =========================================================================
# 1. ISA SPEC VALIDATION
# =========================================================================

class ISASpecTests(TestCase):
    """Validate that the ISA spec file is consistent with the engines."""

    def test_risc_opcodes_match_engine(self):
        """Every opcode in the spec must be handled by the RISC engine."""
        spec_ops = risc_opcodes()
        expected = {"LOAD", "STORE", "ADD", "SUB", "MOV", "BEQ", "BNE", "JMP", "NOP", "HALT"}
        self.assertEqual(spec_ops, expected)

    def test_cisc_opcodes_match_engine(self):
        """Every opcode in the spec must be handled by the CISC engine."""
        spec_ops = cisc_opcodes()
        expected = {"ADD", "SUB", "MUL", "MOV", "LOAD", "STORE", "INC", "DEC",
                    "BEQ", "BNE", "JMP", "NOP", "HALT"}
        self.assertEqual(spec_ops, expected)

    def test_risc_cycle_costs_match_engine(self):
        """Spec cycle costs must match the CYCLE_COSTS table in risc/engine.py."""
        for opcode, cost in CYCLE_COSTS.items():
            self.assertEqual(risc_cycle_cost(opcode), cost,
                             f"Cycle cost mismatch for RISC {opcode}")

    def test_cisc_total_cycles_from_spec(self):
        """Spot-check CISC total cycle counts from spec."""
        # ADD: 1 fetch + 4 µ-ops = 5
        self.assertEqual(cisc_total_cycles("ADD"), 5)
        # MOV: 1 fetch + 2 µ-ops = 3
        self.assertEqual(cisc_total_cycles("MOV"), 3)
        # HALT: 1 fetch + 1 µ-op = 2
        self.assertEqual(cisc_total_cycles("HALT"), 2)

    def test_risc_operand_counts(self):
        self.assertEqual(risc_operand_count("ADD"), 3)   # Rd, Rs1, Rs2
        self.assertEqual(risc_operand_count("MOV"), 2)   # Rd, imm
        self.assertEqual(risc_operand_count("HALT"), 0)
        self.assertEqual(risc_operand_count("BEQ"), 3)   # Rs1, Rs2, label

    def test_cisc_operand_counts(self):
        self.assertEqual(cisc_operand_count("ADD"), 2)   # [addr1], [addr2]
        self.assertEqual(cisc_operand_count("INC"), 1)   # [addr]
        self.assertEqual(cisc_operand_count("HALT"), 0)
        self.assertEqual(cisc_operand_count("BEQ"), 3)   # [a1], [a2], label

    def test_simulation_modes_defined(self):
        modes = simulation_modes()
        self.assertIn("functional", modes)
        self.assertIn("microarchitectural", modes)

    def test_equivalence_contract_fields(self):
        contract = equivalence_contract()
        self.assertIn("registers", contract["checked_fields"])
        self.assertIn("memory", contract["checked_fields"])
        self.assertIn("halted", contract["checked_fields"])

    def test_timeline_stores_snapshots_not_dicts(self):
        """timeline must contain CPUSnapshot objects, not plain dicts."""
        state = CPUState()
        state.new_cycle()
        state.add_event(Event(Component.ALU, "test"))
        state.end_cycle()
        self.assertIsInstance(state.timeline[0], CPUSnapshot)
        # Attribute access works
        self.assertEqual(state.timeline[0].cycle, 1)
        # to_dict() produces a dict
        d = state.timeline[0].to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["cycle"], 1)


# =========================================================================
# 2. SEMANTIC EQUIVALENCE (RISC == CISC)
# =========================================================================

class SemanticEquivalenceTests(TestCase):
    """
    Core academic requirement: a program and its transpiled version must
    produce identical observable state (registers + memory).

    These tests use the transpiler to generate both versions from a single
    common source, then assert final state equality.
    """

    def _assert_equivalent(self, common_code: str) -> None:
        """Transpile common_code, run both engines, assert final state matches."""
        risc_src, cisc_src = transpile_common_to_risc_cisc(common_code)
        risc_state = _run_risc(risc_src)
        cisc_state = _run_cisc(cisc_src)

        contract = equivalence_contract()
        checked = contract["checked_fields"]

        if "registers" in checked:
            self.assertEqual(
                list(risc_state.registers),
                list(cisc_state.registers),
                f"Register mismatch.\nRISC: {risc_state.registers}\nCISC: {cisc_state.registers}",
            )
        if "memory" in checked:
            self.assertEqual(
                dict(risc_state.memory),
                dict(cisc_state.memory),
                f"Memory mismatch.\nRISC: {risc_state.memory}\nCISC: {cisc_state.memory}",
            )
        if "halted" in checked:
            self.assertEqual(risc_state.halted, cisc_state.halted)

    def test_equivalence_mov_halt(self):
        self._assert_equivalent("MOV R0, 42\nHALT")

    def test_equivalence_add(self):
        self._assert_equivalent(
            "MOV R0, 10\nMOV R1, 20\nADD R2, R0, R1\nSTORE R2, 100\nHALT"
        )

    def test_equivalence_sub(self):
        self._assert_equivalent(
            "MOV R0, 50\nMOV R1, 13\nSUB R2, R0, R1\nSTORE R2, 100\nHALT"
        )

    def test_equivalence_load_store(self):
        self._assert_equivalent(
            "MOV R0, 77\nSTORE R0, 50\nLOAD R1, 50\nSTORE R1, 60\nHALT"
        )

    def test_equivalence_jmp(self):
        self._assert_equivalent(
            "JMP END\nMOV R0, 999\nEND: MOV R1, 1\nHALT"
        )

    def test_equivalence_beq_taken(self):
        self._assert_equivalent(
            "MOV R0, 5\nMOV R1, 5\nBEQ R0, R1, DONE\nMOV R2, 999\nDONE: MOV R3, 1\nHALT"
        )

    def test_equivalence_beq_not_taken(self):
        self._assert_equivalent(
            "MOV R0, 3\nMOV R1, 7\nBEQ R0, R1, SKIP\nMOV R2, 42\nSKIP: HALT"
        )

    def test_equivalence_bne_taken(self):
        self._assert_equivalent(
            "MOV R0, 1\nMOV R1, 2\nBNE R0, R1, DIFF\nMOV R2, 0\nDIFF: MOV R3, 99\nHALT"
        )

    def test_equivalence_bne_not_taken(self):
        self._assert_equivalent(
            "MOV R0, 5\nMOV R1, 5\nBNE R0, R1, DIFF\nMOV R2, 42\nDIFF: HALT"
        )

    def test_equivalence_multiple_stores(self):
        self._assert_equivalent(
            "MOV R0, 1\nMOV R1, 2\nMOV R2, 3\n"
            "STORE R0, 10\nSTORE R1, 11\nSTORE R2, 12\nHALT"
        )

    def test_equivalence_add_chain(self):
        """R0=1, R1=2, R2=R0+R1=3, R3=R2+R1=5, store R3."""
        self._assert_equivalent(
            "MOV R0, 1\nMOV R1, 2\n"
            "ADD R2, R0, R1\n"
            "ADD R3, R2, R1\n"
            "STORE R3, 100\nHALT"
        )


# =========================================================================
# 3. BASIC ARITHMETIC
# =========================================================================

class RISCArithmeticTests(TestCase):

    def test_add_positive(self):
        state = _run_risc("MOV R0, 15\nMOV R1, 27\nADD R2, R0, R1\nHALT")
        self.assertEqual(state.registers[2], 42)

    def test_add_zero(self):
        state = _run_risc("MOV R0, 0\nMOV R1, 0\nADD R2, R0, R1\nHALT")
        self.assertEqual(state.registers[2], 0)

    def test_sub_positive(self):
        state = _run_risc("MOV R0, 100\nMOV R1, 37\nSUB R2, R0, R1\nHALT")
        self.assertEqual(state.registers[2], 63)

    def test_sub_to_zero(self):
        state = _run_risc("MOV R0, 5\nMOV R1, 5\nSUB R2, R0, R1\nHALT")
        self.assertEqual(state.registers[2], 0)

    def test_sub_negative_result(self):
        state = _run_risc("MOV R0, 3\nMOV R1, 10\nSUB R2, R0, R1\nHALT")
        self.assertEqual(state.registers[2], -7)

    def test_mov_immediate(self):
        state = _run_risc("MOV R5, 255\nHALT")
        self.assertEqual(state.registers[5], 255)

    def test_mov_negative_immediate(self):
        state = _run_risc("MOV R0, -1\nHALT")
        self.assertEqual(state.registers[0], -1)

    def test_add_uses_destination_register(self):
        """ADD Rd, Rs1, Rs2 — Rd must be written, Rs1/Rs2 unchanged."""
        state = _run_risc("MOV R0, 10\nMOV R1, 20\nADD R2, R0, R1\nHALT")
        self.assertEqual(state.registers[0], 10)  # Rs1 unchanged
        self.assertEqual(state.registers[1], 20)  # Rs2 unchanged
        self.assertEqual(state.registers[2], 30)  # Rd written

    def test_add_same_source_and_dest(self):
        """ADD R0, R0, R1 — R0 is both source and destination."""
        state = _run_risc("MOV R0, 5\nMOV R1, 3\nADD R0, R0, R1\nHALT")
        self.assertEqual(state.registers[0], 8)


class CISCArithmeticTests(TestCase):

    def test_add_memory(self):
        state = _run_cisc("MOV [10], 15\nMOV [20], 27\nADD [10], [20]\nHALT")
        self.assertEqual(state.memory[10], 42)

    def test_sub_memory(self):
        state = _run_cisc("MOV [10], 100\nMOV [20], 37\nSUB [10], [20]\nHALT")
        self.assertEqual(state.memory[10], 63)

    def test_mul_memory(self):
        state = _run_cisc("MOV [10], 6\nMOV [20], 7\nMUL [10], [20]\nHALT")
        self.assertEqual(state.memory[10], 42)

    def test_inc(self):
        state = _run_cisc("MOV [10], 9\nINC [10]\nHALT")
        self.assertEqual(state.memory[10], 10)

    def test_dec(self):
        state = _run_cisc("MOV [10], 10\nDEC [10]\nHALT")
        self.assertEqual(state.memory[10], 9)

    def test_inc_dec_cancel(self):
        state = _run_cisc("MOV [10], 5\nINC [10]\nDEC [10]\nHALT")
        self.assertEqual(state.memory[10], 5)

    def test_add_does_not_modify_source(self):
        """ADD [addr1], [addr2] — addr2 must be unchanged."""
        state = _run_cisc("MOV [10], 3\nMOV [20], 7\nADD [10], [20]\nHALT")
        self.assertEqual(state.memory[20], 7)   # source unchanged
        self.assertEqual(state.memory[10], 10)  # destination updated


# =========================================================================
# 4. MEMORY OPERATIONS
# =========================================================================

class RISCMemoryTests(TestCase):

    def test_store_then_load(self):
        state = _run_risc("MOV R0, 99\nSTORE R0, 50\nLOAD R1, 50\nHALT")
        self.assertEqual(state.registers[1], 99)
        self.assertEqual(state.memory[50], 99)

    def test_load_uninitialized_is_zero(self):
        state = _run_risc("LOAD R0, 100\nHALT")
        self.assertEqual(state.registers[0], 0)

    def test_store_overwrites_memory(self):
        state = _run_risc("MOV R0, 1\nSTORE R0, 10\nMOV R0, 2\nSTORE R0, 10\nHALT")
        self.assertEqual(state.memory[10], 2)

    def test_multiple_memory_locations(self):
        state = _run_risc(
            "MOV R0, 10\nMOV R1, 20\nMOV R2, 30\n"
            "STORE R0, 0\nSTORE R1, 1\nSTORE R2, 2\nHALT"
        )
        self.assertEqual(state.memory[0], 10)
        self.assertEqual(state.memory[1], 20)
        self.assertEqual(state.memory[2], 30)

    def test_load_after_alu(self):
        """Store ALU result, then load it back."""
        state = _run_risc(
            "MOV R0, 7\nMOV R1, 8\nADD R2, R0, R1\nSTORE R2, 100\nLOAD R3, 100\nHALT"
        )
        self.assertEqual(state.registers[3], 15)

    def test_store_cycle_cost(self):
        # MOV=1, STORE=2, HALT=1 → 4
        state = _run_risc("MOV R0, 1\nSTORE R0, 50\nHALT")
        self.assertEqual(state.cycles, 4)

    def test_load_cycle_cost(self):
        # LOAD=2, HALT=1 → 3
        state = _run_risc("LOAD R0, 50\nHALT")
        self.assertEqual(state.cycles, 3)


class CISCMemoryTests(TestCase):

    def test_load_register_from_memory(self):
        state = _run_cisc("MOV [50], 77\nLOAD R0, [50]\nHALT")
        self.assertEqual(state.registers[0], 77)

    def test_store_register_to_memory(self):
        state = _run_cisc("MOV [50], 33\nLOAD R0, [50]\nSTORE [60], R0\nHALT")
        self.assertEqual(state.memory[60], 33)

    def test_mov_writes_memory(self):
        state = _run_cisc("MOV [100], 42\nHALT")
        self.assertEqual(state.memory[100], 42)

    def test_memory_overwrite(self):
        state = _run_cisc("MOV [10], 1\nMOV [10], 2\nHALT")
        self.assertEqual(state.memory[10], 2)


# =========================================================================
# 5. CONTROL FLOW
# =========================================================================

class RISCControlFlowTests(TestCase):

    def test_jmp_skips_instruction(self):
        state = _run_risc("JMP END\nMOV R0, 999\nEND: HALT")
        self.assertEqual(state.registers[0], 0)

    def test_jmp_cycle_cost(self):
        # JMP=2, HALT=1 → 3
        state = _run_risc("JMP END\nEND: HALT")
        self.assertEqual(state.cycles, 3)

    def test_beq_taken_skips(self):
        state = _run_risc(
            "MOV R0, 5\nMOV R1, 5\nBEQ R0, R1, DONE\nMOV R2, 999\nDONE: HALT"
        )
        self.assertEqual(state.registers[2], 0)

    def test_beq_not_taken_executes_next(self):
        state = _run_risc(
            "MOV R0, 3\nMOV R1, 7\nBEQ R0, R1, SKIP\nMOV R2, 42\nSKIP: HALT"
        )
        self.assertEqual(state.registers[2], 42)

    def test_beq_not_taken_misprediction_penalty(self):
        # MOV=1, MOV=1, BEQ(not taken)=2+2penalty=4, MOV=1, HALT=1 → 10
        state = _run_risc(
            "MOV R0, 3\nMOV R1, 7\nBEQ R0, R1, SKIP\nMOV R2, 42\nSKIP: HALT"
        )
        self.assertEqual(state.cycles, 10)

    def test_beq_taken_no_penalty(self):
        # MOV=1, MOV=1, BEQ(taken)=2, HALT=1 → 5
        state = _run_risc(
            "MOV R0, 5\nMOV R1, 5\nBEQ R0, R1, DONE\nDONE: HALT"
        )
        self.assertEqual(state.cycles, 5)

    def test_bne_taken(self):
        state = _run_risc(
            "MOV R0, 1\nMOV R1, 2\nBNE R0, R1, DIFF\nMOV R2, 0\nDIFF: MOV R3, 99\nHALT"
        )
        self.assertEqual(state.registers[2], 0)   # skipped
        self.assertEqual(state.registers[3], 99)

    def test_bne_not_taken(self):
        state = _run_risc(
            "MOV R0, 5\nMOV R1, 5\nBNE R0, R1, DIFF\nMOV R2, 42\nDIFF: HALT"
        )
        self.assertEqual(state.registers[2], 42)

    def test_loop_countdown(self):
        """Count R0 down from 3 to 0 using BNE."""
        state = _run_risc(
            "MOV R0, 3\nMOV R1, 1\nMOV R7, 0\n"
            "LOOP: SUB R0, R0, R1\nBNE R0, R7, LOOP\nHALT"
        )
        self.assertEqual(state.registers[0], 0)
        self.assertTrue(state.halted)

    def test_loop_accumulate(self):
        """Accumulate 1+2+3 = 6 in R2."""
        state = _run_risc(
            "MOV R0, 3\nMOV R1, 1\nMOV R2, 0\nMOV R7, 0\n"
            "LOOP: ADD R2, R2, R0\nSUB R0, R0, R1\nBNE R0, R7, LOOP\nHALT"
        )
        self.assertEqual(state.registers[2], 6)

    def test_forward_jump(self):
        state = _run_risc("JMP FORWARD\nMOV R0, 1\nFORWARD: MOV R1, 2\nHALT")
        self.assertEqual(state.registers[0], 0)
        self.assertEqual(state.registers[1], 2)

    def test_nop_does_nothing(self):
        state = _run_risc("NOP\nMOV R0, 5\nNOP\nHALT")
        self.assertEqual(state.registers[0], 5)
        self.assertEqual(state.cycles, 4)  # NOP=1, MOV=1, NOP=1, HALT=1


class CISCControlFlowTests(TestCase):

    def test_jmp_skips(self):
        state = _run_cisc("JMP END\nMOV [10], 999\nEND: HALT")
        self.assertEqual(state.memory.get(10, 0), 0)

    def test_beq_taken(self):
        state = _run_cisc(
            "MOV [10], 5\nMOV [20], 5\nBEQ [10], [20], DONE\nMOV [10], 999\nDONE: HALT"
        )
        self.assertEqual(state.memory[10], 5)

    def test_beq_not_taken(self):
        state = _run_cisc(
            "MOV [10], 3\nMOV [20], 7\nBEQ [10], [20], SKIP\nMOV [30], 42\nSKIP: HALT"
        )
        self.assertEqual(state.memory[30], 42)

    def test_bne_taken(self):
        state = _run_cisc(
            "MOV [10], 1\nMOV [20], 2\nBNE [10], [20], DIFF\nMOV [30], 0\nDIFF: MOV [40], 99\nHALT"
        )
        self.assertEqual(state.memory.get(30, 0), 0)
        self.assertEqual(state.memory[40], 99)

    def test_bne_not_taken(self):
        state = _run_cisc(
            "MOV [10], 5\nMOV [20], 5\nBNE [10], [20], DIFF\nMOV [30], 42\nDIFF: HALT"
        )
        self.assertEqual(state.memory[30], 42)

    def test_cisc_loop(self):
        """CISC countdown loop: MEM[10] from 3 to 0."""
        state = _run_cisc(
            "MOV [10], 3\nMOV [20], 0\n"
            "LOOP: DEC [10]\nBNE [10], [20], LOOP\nHALT"
        )
        self.assertEqual(state.memory[10], 0)


# =========================================================================
# 6. CISC MICRO-OP DECOMPOSITION
# =========================================================================

class CISCMicroOpTests(TestCase):

    def test_add_cycle_count(self):
        # 2×MOV(3 each) + ADD(5) + HALT(2) = 13
        state = _run_cisc("MOV [10], 5\nMOV [20], 10\nADD [10], [20]\nHALT")
        self.assertEqual(state.cycles, 13)

    def test_mov_cycle_count(self):
        # MOV=3, HALT=2 → 5
        state = _run_cisc("MOV [10], 42\nHALT")
        self.assertEqual(state.cycles, 5)

    def test_inc_cycle_count(self):
        # MOV=3, INC=4, HALT=2 → 9
        state = _run_cisc("MOV [10], 0\nINC [10]\nHALT")
        self.assertEqual(state.cycles, 9)

    def test_load_cycle_count(self):
        # MOV=3, LOAD=4, HALT=2 → 9
        state = _run_cisc("MOV [50], 7\nLOAD R0, [50]\nHALT")
        self.assertEqual(state.cycles, 9)

    def test_store_cycle_count(self):
        # MOV=3, LOAD=4, STORE=4, HALT=2 → 13
        state = _run_cisc("MOV [50], 7\nLOAD R0, [50]\nSTORE [60], R0\nHALT")
        self.assertEqual(state.cycles, 13)

    def test_mul_result(self):
        state = _run_cisc("MOV [10], 9\nMOV [20], 9\nMUL [10], [20]\nHALT")
        self.assertEqual(state.memory[10], 81)

    def test_micro_op_index_in_events(self):
        """Every CISC µ-op event must carry micro_op_index in meta."""
        state = _run_cisc("ADD [10], [20]\nHALT")
        found = False
        for snap in state.timeline:
            for ev in snap.events:
                meta = ev.get("meta", {})
                if meta.get("micro_op"):
                    self.assertIn("micro_op_index", meta)
                    found = True
        self.assertTrue(found, "No µ-op events found")

    def test_fetch_decode_event_present(self):
        """Each CISC instruction must produce a FETCH+DECODE event."""
        state = _run_cisc("MOV [10], 1\nHALT")
        fetch_found = any(
            "FETCH+DECODE" in ev.get("action", "")
            for snap in state.timeline
            for ev in snap.events
        )
        self.assertTrue(fetch_found)


# =========================================================================
# 7. CYCLE MODEL CORRECTNESS
# =========================================================================

class CycleModelTests(TestCase):
    """Verify that cycle counts match the formal ISA spec."""

    # RISC single-issue
    def test_risc_mov_1_cycle(self):
        state = _run_risc("MOV R0, 1\nHALT")
        # MOV=1, HALT=1 → 2
        self.assertEqual(state.cycles, 2)

    def test_risc_add_1_cycle(self):
        state = _run_risc("MOV R0, 1\nMOV R1, 2\nADD R2, R0, R1\nHALT")
        # 1+1+1+1 = 4
        self.assertEqual(state.cycles, 4)

    def test_risc_load_store_2_cycles_each(self):
        state = _run_risc("MOV R0, 1\nSTORE R0, 50\nLOAD R1, 50\nHALT")
        # 1+2+2+1 = 6
        self.assertEqual(state.cycles, 6)

    def test_risc_jmp_2_cycles(self):
        state = _run_risc("JMP END\nEND: HALT")
        # 2+1 = 3
        self.assertEqual(state.cycles, 3)

    def test_risc_bne_taken_2_cycles_no_penalty(self):
        # BNE taken → 2 cycles, no penalty
        state = _run_risc("MOV R0, 1\nMOV R1, 2\nBNE R0, R1, END\nEND: HALT")
        # 1+1+2+1 = 5
        self.assertEqual(state.cycles, 5)

    def test_risc_bne_not_taken_penalty(self):
        # BNE not-taken → 2 + 2 penalty = 4 cycles
        state = _run_risc("MOV R0, 5\nMOV R1, 5\nBNE R0, R1, END\nEND: HALT")
        # 1+1+4+1 = 7
        self.assertEqual(state.cycles, 7)

    def test_risc_nop_1_cycle(self):
        state = _run_risc("NOP\nHALT")
        self.assertEqual(state.cycles, 2)

    # CISC micro-op model
    def test_cisc_halt_2_cycles(self):
        state = _run_cisc("HALT")
        self.assertEqual(state.cycles, 2)

    def test_cisc_nop_2_cycles(self):
        state = _run_cisc("NOP\nHALT")
        # NOP=2, HALT=2 → 4
        self.assertEqual(state.cycles, 4)

    def test_cisc_sub_5_cycles(self):
        state = _run_cisc("MOV [10], 10\nMOV [20], 3\nSUB [10], [20]\nHALT")
        # 3+3+5+2 = 13
        self.assertEqual(state.cycles, 13)

    def test_cisc_mul_5_cycles(self):
        state = _run_cisc("MOV [10], 2\nMOV [20], 3\nMUL [10], [20]\nHALT")
        # 3+3+5+2 = 13
        self.assertEqual(state.cycles, 13)


# =========================================================================
# 8. EDGE CASES
# =========================================================================

class EdgeCaseTests(TestCase):

    def test_register_conflict_add_to_self(self):
        """ADD R0, R0, R0 doubles R0."""
        state = _run_risc("MOV R0, 7\nADD R0, R0, R0\nHALT")
        self.assertEqual(state.registers[0], 14)

    def test_register_conflict_sub_self(self):
        """SUB R0, R0, R0 always gives 0."""
        state = _run_risc("MOV R0, 99\nSUB R0, R0, R0\nHALT")
        self.assertEqual(state.registers[0], 0)

    def test_memory_overwrite_risc(self):
        state = _run_risc(
            "MOV R0, 1\nSTORE R0, 10\n"
            "MOV R0, 2\nSTORE R0, 10\nHALT"
        )
        self.assertEqual(state.memory[10], 2)

    def test_memory_overwrite_cisc(self):
        state = _run_cisc("MOV [10], 1\nMOV [10], 2\nHALT")
        self.assertEqual(state.memory[10], 2)

    def test_all_registers_independent(self):
        """Writing one register must not affect others."""
        code = "\n".join(f"MOV R{i}, {i * 10}" for i in range(8)) + "\nHALT"
        state = _run_risc(code)
        for i in range(8):
            self.assertEqual(state.registers[i], i * 10)

    def test_beq_self_always_taken(self):
        """BEQ Rx, Rx, label is always taken (register equals itself)."""
        state = _run_risc("MOV R0, 42\nBEQ R0, R0, DONE\nMOV R1, 999\nDONE: HALT")
        self.assertEqual(state.registers[1], 0)

    def test_bne_self_never_taken(self):
        """BNE Rx, Rx, label is never taken."""
        state = _run_risc("MOV R0, 42\nBNE R0, R0, SKIP\nMOV R1, 7\nSKIP: HALT")
        self.assertEqual(state.registers[1], 7)

    def test_empty_program_returns_initial_state(self):
        state = execute_risc(parse_risc("HALT"))
        self.assertTrue(state.halted)
        self.assertEqual(state.registers, [0] * 8)

    def test_timeline_length_matches_cycles(self):
        """Each cycle must produce exactly one snapshot."""
        state = _run_risc("MOV R0, 1\nMOV R1, 2\nHALT")
        self.assertEqual(len(state.timeline), state.cycles)

    def test_snapshot_is_immutable(self):
        """CPUSnapshot must be frozen (immutable)."""
        state = _run_risc("MOV R0, 5\nHALT")
        snap = state.timeline[0]
        with self.assertRaises(Exception):
            snap.cycle = 999  # type: ignore[misc]

    def test_cisc_add_source_unchanged(self):
        """ADD [a], [b] must not modify MEM[b]."""
        state = _run_cisc("MOV [10], 3\nMOV [20], 7\nADD [10], [20]\nHALT")
        self.assertEqual(state.memory[20], 7)

    def test_pipeline_vs_no_pipeline_same_result(self):
        """Pipeline and non-pipeline RISC must produce identical final registers."""
        code = "MOV R0, 5\nMOV R1, 10\nADD R2, R0, R1\nHALT"
        parsed = parse_risc(code)
        s1 = execute_risc(parsed)
        s2 = execute_risc_pipeline(parsed)
        self.assertEqual(list(s1.registers), list(s2.registers))
        self.assertEqual(dict(s1.memory), dict(s2.memory))

    def test_pipeline_load_store_same_result(self):
        code = "MOV R0, 42\nSTORE R0, 100\nLOAD R1, 100\nHALT"
        parsed = parse_risc(code)
        s1 = execute_risc(parsed)
        s2 = execute_risc_pipeline(parsed)
        self.assertEqual(s1.registers[1], s2.registers[1])
        self.assertEqual(s1.memory, s2.memory)


# =========================================================================
# 9. SIMULATION MODE FLAG
# =========================================================================

class SimulationModeTests(TestCase):

    def setUp(self):
        self.client = Client()

    def test_microarchitectural_returns_timeline(self):
        resp = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({
                "code": "MOV R0, 5\nHALT",
                "simulation_mode": "microarchitectural",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(len(data["timeline"]), 0)
        self.assertEqual(data["simulation_mode"], "microarchitectural")

    def test_functional_returns_empty_timeline(self):
        resp = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({
                "code": "MOV R0, 5\nHALT",
                "simulation_mode": "functional",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["timeline"], [])
        self.assertEqual(data["simulation_mode"], "functional")

    def test_functional_still_computes_metrics(self):
        resp = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({
                "code": "MOV R0, 5\nHALT",
                "simulation_mode": "functional",
            }),
            content_type="application/json",
        )
        data = resp.json()
        self.assertIn("metrics", data)
        self.assertGreater(data["metrics"]["total_cycles"], 0)

    def test_functional_still_returns_final_state(self):
        resp = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({
                "code": "MOV R0, 42\nHALT",
                "simulation_mode": "functional",
            }),
            content_type="application/json",
        )
        data = resp.json()
        self.assertEqual(data["final_state"]["registers"][0], 42)

    def test_default_mode_is_microarchitectural(self):
        resp = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({"code": "MOV R0, 1\nHALT"}),
            content_type="application/json",
        )
        data = resp.json()
        self.assertEqual(data["simulation_mode"], "microarchitectural")

    def test_invalid_mode_rejected(self):
        resp = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({
                "code": "MOV R0, 1\nHALT",
                "simulation_mode": "invalid_mode",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_cisc_functional_mode(self):
        resp = self.client.post(
            "/api/simulate/cisc/",
            data=json.dumps({
                "code": "MOV [10], 42\nHALT",
                "simulation_mode": "functional",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["timeline"], [])
        self.assertEqual(data["final_state"]["memory"]["10"], 42)

    def test_combined_simulation_mode(self):
        resp = self.client.post(
            "/api/simulate/",
            data=json.dumps({
                "risc_code": "MOV R0, 5\nHALT",
                "cisc_code": "MOV [10], 5\nHALT",
                "simulation_mode": "functional",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["risc"]["timeline"], [])
        self.assertEqual(data["cisc"]["timeline"], [])


# =========================================================================
# 10. METRICS
# =========================================================================

class MetricsCorrectnessTests(TestCase):

    def test_cpi_formula(self):
        """CPI = total_cycles / instruction_count."""
        state = _run_risc("MOV R0, 1\nMOV R1, 2\nADD R2, R0, R1\nHALT")
        ic = count_executed_instructions(state)
        metrics = compute_metrics(state, ic, 1.0)
        self.assertEqual(metrics.instruction_count, 4)
        self.assertEqual(metrics.total_cycles, 4)
        self.assertAlmostEqual(metrics.cpi, 1.0)

    def test_cpu_time_formula(self):
        """cpu_time_ns = total_cycles × t_cycle_ns."""
        state = _run_risc("MOV R0, 1\nHALT")
        ic = count_executed_instructions(state)
        metrics = compute_metrics(state, ic, 2.0)
        self.assertAlmostEqual(metrics.cpu_time_ns, state.cycles * 2.0)

    def test_cpu_time_us_conversion(self):
        state = _run_risc("MOV R0, 1\nHALT")
        ic = count_executed_instructions(state)
        metrics = compute_metrics(state, ic, 1.0)
        self.assertAlmostEqual(metrics.cpu_time_us, metrics.cpu_time_ns / 1000.0)

    def test_zero_instructions_cpi_is_zero(self):
        state = CPUState()
        metrics = compute_metrics(state, 0, 1.0)
        self.assertEqual(metrics.cpi, 0.0)

    def test_count_instructions_risc(self):
        state = _run_risc("MOV R0, 1\nMOV R1, 2\nADD R2, R0, R1\nHALT")
        self.assertEqual(count_executed_instructions(state), 4)

    def test_count_instructions_cisc(self):
        state = _run_cisc("MOV [10], 5\nADD [10], [10]\nHALT")
        self.assertEqual(count_executed_instructions(state), 3)

    def test_count_instructions_pipeline(self):
        parsed = parse_risc("MOV R0, 1\nMOV R1, 2\nADD R2, R0, R1\nHALT")
        state = execute_risc_pipeline(parsed)
        self.assertEqual(count_executed_instructions(state), 4)

    def test_compare_risc_faster_than_cisc(self):
        """For equivalent programs, RISC should be faster (lower cpu_time_ns)."""
        risc_state = _run_risc("MOV R0, 5\nMOV R1, 10\nADD R2, R0, R1\nHALT")
        cisc_state = _run_cisc("MOV [10], 5\nMOV [20], 10\nADD [10], [20]\nHALT")
        risc_ic = count_executed_instructions(risc_state)
        cisc_ic = count_executed_instructions(cisc_state)
        result = compare(risc_state, risc_ic, cisc_state, cisc_ic,
                         risc_t_cycle=1.0, cisc_t_cycle=1.5)
        # RISC: 4 cycles × 1.0 ns = 4 ns
        # CISC: 13 cycles × 1.5 ns = 19.5 ns
        self.assertGreater(result.speedup_risc_over_cisc, 1.0)


# =========================================================================
# 6. CISC MICRO-OP DECOMPOSITION
# =========================================================================

class CISCMicroOpTests(TestCase):

    def test_add_cycle_count(self):
        # 2×MOV(3) + ADD(5) + HALT(2) = 13
        state = _run_cisc("MOV [10], 5\nMOV [20], 10\nADD [10], [20]\nHALT")
        self.assertEqual(state.cycles, 13)

    def test_mov_cycle_count(self):
        # MOV=3, HALT=2 → 5
        state = _run_cisc("MOV [10], 42\nHALT")
        self.assertEqual(state.cycles, 5)

    def test_inc_cycle_count(self):
        # MOV=3, INC=4, HALT=2 → 9
        state = _run_cisc("MOV [10], 0\nINC [10]\nHALT")
        self.assertEqual(state.cycles, 9)

    def test_load_cycle_count(self):
        # MOV=3, LOAD=4, HALT=2 → 9
        state = _run_cisc("MOV [50], 7\nLOAD R0, [50]\nHALT")
        self.assertEqual(state.cycles, 9)

    def test_mul_result(self):
        state = _run_cisc("MOV [10], 9\nMOV [20], 9\nMUL [10], [20]\nHALT")
        self.assertEqual(state.memory[10], 81)

    def test_micro_op_index_in_events(self):
        state = _run_cisc("ADD [10], [20]\nHALT")
        found = False
        for snap in state.timeline:
            for ev in snap.events:
                if ev.get("meta", {}).get("micro_op"):
                    self.assertIn("micro_op_index", ev["meta"])
                    found = True
        self.assertTrue(found)

    def test_fetch_decode_event_present(self):
        state = _run_cisc("MOV [10], 1\nHALT")
        fetch_found = any(
            "FETCH+DECODE" in ev.get("action", "")
            for snap in state.timeline
            for ev in snap.events
        )
        self.assertTrue(fetch_found)


# =========================================================================
# 7. CYCLE MODEL CORRECTNESS
# =========================================================================

class CycleModelTests(TestCase):

    def test_risc_mov_1_cycle(self):
        state = _run_risc("MOV R0, 1\nHALT")
        self.assertEqual(state.cycles, 2)  # MOV=1, HALT=1

    def test_risc_add_1_cycle(self):
        state = _run_risc("MOV R0, 1\nMOV R1, 2\nADD R2, R0, R1\nHALT")
        self.assertEqual(state.cycles, 4)  # 1+1+1+1

    def test_risc_load_store_2_cycles_each(self):
        state = _run_risc("MOV R0, 1\nSTORE R0, 50\nLOAD R1, 50\nHALT")
        self.assertEqual(state.cycles, 6)  # 1+2+2+1

    def test_risc_jmp_2_cycles(self):
        state = _run_risc("JMP END\nEND: HALT")
        self.assertEqual(state.cycles, 3)  # 2+1

    def test_risc_bne_taken_no_penalty(self):
        # BNE taken → 2 cycles, no stall
        state = _run_risc("MOV R0, 1\nMOV R1, 2\nBNE R0, R1, END\nEND: HALT")
        self.assertEqual(state.cycles, 5)  # 1+1+2+1

    def test_risc_bne_not_taken_penalty(self):
        # BNE not-taken → 2 + 2 penalty = 4 cycles
        state = _run_risc("MOV R0, 5\nMOV R1, 5\nBNE R0, R1, END\nEND: HALT")
        self.assertEqual(state.cycles, 7)  # 1+1+4+1

    def test_cisc_halt_2_cycles(self):
        state = _run_cisc("HALT")
        self.assertEqual(state.cycles, 2)

    def test_cisc_nop_2_cycles(self):
        state = _run_cisc("NOP\nHALT")
        self.assertEqual(state.cycles, 4)  # NOP=2, HALT=2

    def test_cisc_sub_5_cycles(self):
        state = _run_cisc("MOV [10], 10\nMOV [20], 3\nSUB [10], [20]\nHALT")
        self.assertEqual(state.cycles, 13)  # 3+3+5+2


# =========================================================================
# 8. EDGE CASES
# =========================================================================

class EdgeCaseTests(TestCase):

    def test_add_register_to_itself(self):
        state = _run_risc("MOV R0, 7\nADD R0, R0, R0\nHALT")
        self.assertEqual(state.registers[0], 14)

    def test_sub_register_from_itself_is_zero(self):
        state = _run_risc("MOV R0, 99\nSUB R0, R0, R0\nHALT")
        self.assertEqual(state.registers[0], 0)

    def test_memory_overwrite_risc(self):
        state = _run_risc("MOV R0, 1\nSTORE R0, 10\nMOV R0, 2\nSTORE R0, 10\nHALT")
        self.assertEqual(state.memory[10], 2)

    def test_memory_overwrite_cisc(self):
        state = _run_cisc("MOV [10], 1\nMOV [10], 2\nHALT")
        self.assertEqual(state.memory[10], 2)

    def test_all_registers_independent(self):
        code = "\n".join(f"MOV R{i}, {i * 10}" for i in range(8)) + "\nHALT"
        state = _run_risc(code)
        for i in range(8):
            self.assertEqual(state.registers[i], i * 10)

    def test_beq_self_always_taken(self):
        state = _run_risc("MOV R0, 42\nBEQ R0, R0, DONE\nMOV R1, 999\nDONE: HALT")
        self.assertEqual(state.registers[1], 0)

    def test_bne_self_never_taken(self):
        state = _run_risc("MOV R0, 42\nBNE R0, R0, SKIP\nMOV R1, 7\nSKIP: HALT")
        self.assertEqual(state.registers[1], 7)

    def test_timeline_length_matches_cycles(self):
        state = _run_risc("MOV R0, 1\nMOV R1, 2\nHALT")
        self.assertEqual(len(state.timeline), state.cycles)

    def test_snapshot_is_immutable(self):
        state = _run_risc("MOV R0, 5\nHALT")
        snap = state.timeline[0]
        with self.assertRaises(Exception):
            snap.cycle = 999  # type: ignore[misc]

    def test_pipeline_vs_no_pipeline_same_registers(self):
        code = "MOV R0, 5\nMOV R1, 10\nADD R2, R0, R1\nHALT"
        parsed = parse_risc(code)
        s1 = execute_risc(parsed)
        s2 = execute_risc_pipeline(parsed)
        self.assertEqual(list(s1.registers), list(s2.registers))

    def test_pipeline_vs_no_pipeline_same_memory(self):
        code = "MOV R0, 42\nSTORE R0, 100\nLOAD R1, 100\nHALT"
        parsed = parse_risc(code)
        s1 = execute_risc(parsed)
        s2 = execute_risc_pipeline(parsed)
        self.assertEqual(dict(s1.memory), dict(s2.memory))


# =========================================================================
# 9. SIMULATION MODE FLAG
# =========================================================================

class SimulationModeTests(TestCase):

    def setUp(self):
        self.client = Client()

    def test_microarchitectural_returns_timeline(self):
        resp = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({"code": "MOV R0, 5\nHALT", "simulation_mode": "microarchitectural"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(len(data["timeline"]), 0)
        self.assertEqual(data["simulation_mode"], "microarchitectural")

    def test_functional_returns_empty_timeline(self):
        resp = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({"code": "MOV R0, 5\nHALT", "simulation_mode": "functional"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["timeline"], [])
        self.assertEqual(data["simulation_mode"], "functional")

    def test_functional_still_computes_metrics(self):
        resp = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({"code": "MOV R0, 5\nHALT", "simulation_mode": "functional"}),
            content_type="application/json",
        )
        data = resp.json()
        self.assertGreater(data["metrics"]["total_cycles"], 0)

    def test_functional_returns_correct_final_state(self):
        resp = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({"code": "MOV R0, 42\nHALT", "simulation_mode": "functional"}),
            content_type="application/json",
        )
        data = resp.json()
        self.assertEqual(data["final_state"]["registers"][0], 42)

    def test_default_mode_is_microarchitectural(self):
        resp = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({"code": "MOV R0, 1\nHALT"}),
            content_type="application/json",
        )
        self.assertEqual(resp.json()["simulation_mode"], "microarchitectural")

    def test_invalid_mode_rejected(self):
        resp = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({"code": "MOV R0, 1\nHALT", "simulation_mode": "bogus"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_cisc_functional_mode(self):
        resp = self.client.post(
            "/api/simulate/cisc/",
            data=json.dumps({"code": "MOV [10], 42\nHALT", "simulation_mode": "functional"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["timeline"], [])
        self.assertEqual(data["final_state"]["memory"]["10"], 42)

    def test_combined_endpoint_functional_mode(self):
        resp = self.client.post(
            "/api/simulate/",
            data=json.dumps({
                "risc_code": "MOV R0, 5\nHALT",
                "cisc_code": "MOV [10], 5\nHALT",
                "simulation_mode": "functional",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["risc"]["timeline"], [])
        self.assertEqual(data["cisc"]["timeline"], [])


# =========================================================================
# 10. METRICS
# =========================================================================

class MetricsCorrectnessTests(TestCase):

    def test_cpi_formula(self):
        state = _run_risc("MOV R0, 1\nMOV R1, 2\nADD R2, R0, R1\nHALT")
        ic = count_executed_instructions(state)
        metrics = compute_metrics(state, ic, 1.0)
        self.assertEqual(metrics.instruction_count, 4)
        self.assertEqual(metrics.total_cycles, 4)
        self.assertAlmostEqual(metrics.cpi, 1.0)

    def test_cpu_time_equals_cycles_times_tcycle(self):
        state = _run_risc("MOV R0, 1\nHALT")
        ic = count_executed_instructions(state)
        metrics = compute_metrics(state, ic, 2.0)
        self.assertAlmostEqual(metrics.cpu_time_ns, state.cycles * 2.0)

    def test_cpu_time_us_conversion(self):
        state = _run_risc("MOV R0, 1\nHALT")
        ic = count_executed_instructions(state)
        metrics = compute_metrics(state, ic, 1.0)
        self.assertAlmostEqual(metrics.cpu_time_us, metrics.cpu_time_ns / 1000.0)

    def test_zero_instructions_cpi_is_zero(self):
        metrics = compute_metrics(CPUState(), 0, 1.0)
        self.assertEqual(metrics.cpi, 0.0)

    def test_count_instructions_risc(self):
        state = _run_risc("MOV R0, 1\nMOV R1, 2\nADD R2, R0, R1\nHALT")
        self.assertEqual(count_executed_instructions(state), 4)

    def test_count_instructions_cisc(self):
        state = _run_cisc("MOV [10], 5\nADD [10], [10]\nHALT")
        self.assertEqual(count_executed_instructions(state), 3)

    def test_count_instructions_pipeline(self):
        parsed = parse_risc("MOV R0, 1\nMOV R1, 2\nADD R2, R0, R1\nHALT")
        state = execute_risc_pipeline(parsed)
        self.assertEqual(count_executed_instructions(state), 4)

    def test_risc_faster_than_cisc_wall_clock(self):
        """For equivalent programs, RISC wall-clock time < CISC (given default clock periods)."""
        risc_state = _run_risc("MOV R0, 5\nMOV R1, 10\nADD R2, R0, R1\nHALT")
        cisc_state = _run_cisc("MOV [10], 5\nMOV [20], 10\nADD [10], [20]\nHALT")
        result = compare(
            risc_state, count_executed_instructions(risc_state),
            cisc_state, count_executed_instructions(cisc_state),
            risc_t_cycle=1.0, cisc_t_cycle=1.5,
        )
        self.assertGreater(result.speedup_risc_over_cisc, 1.0)
