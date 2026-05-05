"""
Tests for the CISC→RISC transpiler and RISC MUL support.

Covers:
  - transpile_cisc_to_risc: each CISC pattern converts to equivalent RISC
  - RISC MUL opcode
  - End-to-end: the user's bubble-sort-style accumulator program runs on
    both engines with identical final memory state
"""

from django.test import TestCase

from simulator.parser.assembly_parser import parse_risc, parse_cisc
from simulator.parser.transpiler import transpile_cisc_to_risc
from simulator.risc.engine import execute_risc
from simulator.cisc.engine import execute_cisc
from simulator.core.cpu_state import CPUState
from simulator.core.exceptions import InvalidInstructionError


class TestCiscToRiscTranspiler(TestCase):
    """Verify each CISC instruction converts to correct RISC equivalent."""

    def test_mov_mem_imm(self):
        risc = transpile_cisc_to_risc("MOV [100], 42\nHALT")
        self.assertIn("MOV R", risc)
        self.assertIn("STORE R", risc)
        self.assertIn("100", risc)
        self.assertIn("42", risc)
        self.assertIn("HALT", risc)

    def test_load_cisc_form(self):
        risc = transpile_cisc_to_risc("LOAD 3, [100]\nHALT")
        self.assertIn("LOAD R3, 100", risc)

    def test_store_cisc_form(self):
        risc = transpile_cisc_to_risc("STORE [100], 5\nHALT")
        self.assertIn("STORE R5, 100", risc)

    def test_add_mem_mem(self):
        risc = transpile_cisc_to_risc("ADD [10], [20]\nHALT")
        lines = risc.splitlines()
        self.assertTrue(any("LOAD" in l and "10" in l for l in lines))
        self.assertTrue(any("LOAD" in l and "20" in l for l in lines))
        self.assertTrue(any("ADD" in l and "," in l for l in lines))
        self.assertTrue(any("STORE" in l and "10" in l for l in lines))

    def test_mul_mem_mem(self):
        risc = transpile_cisc_to_risc("MUL [10], [20]\nHALT")
        self.assertIn("MUL", risc)
        self.assertIn("LOAD", risc)
        self.assertIn("STORE", risc)

    def test_inc_mem(self):
        risc = transpile_cisc_to_risc("INC [50]\nHALT")
        self.assertIn("LOAD", risc)
        self.assertIn("MOV", risc)
        self.assertIn("ADD", risc)
        self.assertIn("STORE", risc)
        self.assertIn("50", risc)

    def test_dec_mem(self):
        risc = transpile_cisc_to_risc("DEC [50]\nHALT")
        self.assertIn("SUB", risc)
        self.assertIn("50", risc)

    def test_bne_mem_mem(self):
        risc = transpile_cisc_to_risc("""LOOP:
INC [10]
BNE [10], [20], LOOP
HALT""")
        self.assertIn("LOOP:", risc)
        self.assertIn("BNE", risc)

    def test_jmp_passthrough(self):
        risc = transpile_cisc_to_risc("L:\nJMP L\nHALT")
        self.assertIn("JMP L", risc)

    def test_labels_preserved(self):
        risc = transpile_cisc_to_risc("""START:
MOV [10], 5
INC [10]
JMP START
HALT""")
        self.assertIn("START:", risc)


class TestTranspiledEquivalence(TestCase):
    """
    Verify that CISC and its CISC→RISC transpilation produce the same
    observable memory state (per the equivalence_contract in isa_spec).
    """

    def _run_cisc(self, code: str) -> CPUState:
        parsed = parse_cisc(code)
        state = CPUState()
        return execute_cisc(parsed, state)

    def _run_risc(self, code: str) -> CPUState:
        parsed = parse_risc(code)
        state = CPUState()
        return execute_risc(parsed, state)

    def test_simple_mov(self):
        cisc = "MOV [100], 42\nHALT"
        risc = transpile_cisc_to_risc(cisc)
        s_c = self._run_cisc(cisc)
        s_r = self._run_risc(risc)
        self.assertEqual(s_c.memory.get(100), s_r.memory.get(100))
        self.assertEqual(s_c.memory.get(100), 42)

    def test_add_mem(self):
        cisc = """MOV [10], 5
MOV [20], 7
ADD [10], [20]
HALT"""
        risc = transpile_cisc_to_risc(cisc)
        s_c = self._run_cisc(cisc)
        s_r = self._run_risc(risc)
        self.assertEqual(s_c.memory.get(10), 12)
        self.assertEqual(s_r.memory.get(10), 12)

    def test_mul_mem(self):
        cisc = """MOV [10], 6
MOV [20], 7
MUL [10], [20]
HALT"""
        risc = transpile_cisc_to_risc(cisc)
        s_c = self._run_cisc(cisc)
        s_r = self._run_risc(risc)
        self.assertEqual(s_c.memory.get(10), 42)
        self.assertEqual(s_r.memory.get(10), 42)

    def test_inc_loop(self):
        cisc = """MOV [10], 0
MOV [20], 5
LOOP:
INC [10]
BNE [10], [20], LOOP
HALT"""
        risc = transpile_cisc_to_risc(cisc)
        s_c = self._run_cisc(cisc)
        s_r = self._run_risc(risc)
        self.assertEqual(s_c.memory.get(10), 5)
        self.assertEqual(s_r.memory.get(10), 5)

    def test_user_accumulator_program(self):
        """The user's exact CISC program — both engines must agree on MEM[200]."""
        cisc = """MOV [201], 10
MOV [202], 30
MOV [203], 5
MOV [204], 0
MOV [205], 4

MOV [10], 10
MOV [11], 20
MOV [12], 30
MOV [13], 40

MOV [200], 0

BUCLE_RISC:
LOAD 1, [10]
LOAD 2, [203]
STORE [30], 1
STORE [31], 2
MUL [30], [31]
LOAD 3, [30]
LOAD 0, [200]
STORE [32], 0
STORE [33], 3
ADD [32], [33]
LOAD 0, [32]
STORE [200], 0
LOAD 4, [201]
INC [201]
LOAD 5, [204]
INC [204]
LOAD 6, [204]
LOAD 7, [205]
STORE [34], 6
STORE [35], 7
BNE [34], [35], BUCLE_RISC
HALT"""

        risc = transpile_cisc_to_risc(cisc)
        s_c = self._run_cisc(cisc)
        s_r = self._run_risc(risc)

        # Accumulator = 4 iterations × 10 × 5 = 200
        self.assertEqual(s_c.memory.get(200), 200)
        self.assertEqual(s_r.memory.get(200), 200)


class TestRiscMul(TestCase):
    """Verify the new MUL opcode in the RISC engine."""

    def test_mul_basic(self):
        code = """MOV R0, 6
MOV R1, 7
MUL R2, R0, R1
HALT"""
        parsed = parse_risc(code)
        state = CPUState()
        state = execute_risc(parsed, state)
        self.assertEqual(state.read_register(2), 42)

    def test_mul_zero(self):
        code = """MOV R0, 0
MOV R1, 99
MUL R2, R0, R1
HALT"""
        parsed = parse_risc(code)
        state = CPUState()
        state = execute_risc(parsed, state)
        self.assertEqual(state.read_register(2), 0)

    def test_mul_cycle_cost(self):
        """MUL should take 3 cycles per the ISA spec."""
        code = """MOV R0, 3
MOV R1, 4
MUL R2, R0, R1
HALT"""
        parsed = parse_risc(code)
        state = CPUState()
        state = execute_risc(parsed, state)
        # MUL is specified as 3 cycles; ensure total is at least 5
        # (= 2 MOVs + MUL, ignoring HALT which may be 0-cycle).
        self.assertGreaterEqual(state.cycles, 5)
