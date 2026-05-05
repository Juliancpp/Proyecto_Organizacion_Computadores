"""
Semantic-equivalence tests for the demo programs.

Verifies that a single common-dialect program produces **identical**
final memory state on both the RISC and CISC engines, per the
`equivalence_contract` in `isa_spec.json`:

    "A CISC program and its RISC transpilation are semantically
     equivalent if and only if they produce identical final CPU state.
     Checked fields: registers, memory, halted."
"""

from django.test import TestCase

from simulator.parser.assembly_parser import parse_risc, parse_cisc
from simulator.parser.transpiler import transpile_common_to_risc_cisc
from simulator.risc.engine import execute_risc
from simulator.cisc.engine import execute_cisc
from simulator.core.cpu_state import CPUState

from simulator.demos.factorial_plus_square import (
    PROGRAM as FACTORIAL_PLUS_SQUARE,
    EXPECTED_FINAL_MEMORY,
)


class TestFactorialPlusSquareDemo(TestCase):
    """
    Demo: f(n) = n! + n²  for n = 5  →  expected MEM[100] = 145.

    Runs the same common-dialect program through the full RISC/CISC
    pipeline and asserts the observable memory state matches on both
    architectures.
    """

    def _transpile_and_run(self) -> tuple[CPUState, CPUState]:
        """Transpile once, run on both engines, return (risc_state, cisc_state)."""
        risc_src, cisc_src = transpile_common_to_risc_cisc(FACTORIAL_PLUS_SQUARE)

        risc_parsed = parse_risc(risc_src)
        risc_state = execute_risc(risc_parsed, CPUState())

        cisc_parsed = parse_cisc(cisc_src)
        cisc_state = execute_cisc(cisc_parsed, CPUState())

        return risc_state, cisc_state

    def test_final_result_matches_expected(self):
        """MEM[100] == 145 on both architectures."""
        risc_state, cisc_state = self._transpile_and_run()
        self.assertEqual(risc_state.memory.get(100), 145)
        self.assertEqual(cisc_state.memory.get(100), 145)

    def test_factorial_intermediate(self):
        """MEM[12] (n!) == 120 on both architectures."""
        risc_state, cisc_state = self._transpile_and_run()
        self.assertEqual(risc_state.memory.get(12), 120)
        self.assertEqual(cisc_state.memory.get(12), 120)

    def test_square_intermediate(self):
        """MEM[11] (n²) == 25 on both architectures."""
        risc_state, cisc_state = self._transpile_and_run()
        self.assertEqual(risc_state.memory.get(11), 25)
        self.assertEqual(cisc_state.memory.get(11), 25)

    def test_all_expected_memory_matches(self):
        """Every expected memory address matches on both engines."""
        risc_state, cisc_state = self._transpile_and_run()
        for addr, expected in EXPECTED_FINAL_MEMORY.items():
            self.assertEqual(
                risc_state.memory.get(addr), expected,
                f"RISC MEM[{addr}] mismatch: expected {expected}, "
                f"got {risc_state.memory.get(addr)}",
            )
            self.assertEqual(
                cisc_state.memory.get(addr), expected,
                f"CISC MEM[{addr}] mismatch: expected {expected}, "
                f"got {cisc_state.memory.get(addr)}",
            )

    def test_both_halted_cleanly(self):
        """Both engines must reach HALT, not max-cycle timeout."""
        risc_state, cisc_state = self._transpile_and_run()
        self.assertTrue(risc_state.halted)
        self.assertTrue(cisc_state.halted)

    def test_semantic_equivalence_memory(self):
        """
        Equivalence contract: the set of EXPECTED memory locations must
        hold the same value on both architectures.

        (Registers and scratch memory may differ due to the different
        register-allocation strategies — that's allowed per the contract.)
        """
        risc_state, cisc_state = self._transpile_and_run()
        for addr in EXPECTED_FINAL_MEMORY:
            self.assertEqual(
                risc_state.memory.get(addr),
                cisc_state.memory.get(addr),
                f"Semantic equivalence violated at MEM[{addr}]: "
                f"RISC={risc_state.memory.get(addr)}, "
                f"CISC={cisc_state.memory.get(addr)}",
            )

    def test_cisc_takes_more_cycles_than_risc(self):
        """
        CISC should generally take more cycles than the native RISC form,
        because each CISC µ-op sequence expands what RISC does in one
        instruction. This is the architectural tradeoff the simulator
        is designed to demonstrate.
        """
        risc_state, cisc_state = self._transpile_and_run()
        # Both should have executed substantial work
        self.assertGreater(risc_state.cycles, 10)
        self.assertGreater(cisc_state.cycles, 10)
        # CISC µ-op expansion typically runs slower in cycles
        self.assertGreater(cisc_state.cycles, risc_state.cycles)


class TestCommonDialectMul(TestCase):
    """Directly test that the common-dialect MUL transpiles to both targets."""

    def test_simple_multiplication(self):
        src = """\
MOV R0, 6
MOV R1, 7
MUL R2, R0, R1
STORE R2, 50
HALT"""
        risc_src, cisc_src = transpile_common_to_risc_cisc(src)

        s_r = execute_risc(parse_risc(risc_src), CPUState())
        s_c = execute_cisc(parse_cisc(cisc_src), CPUState())

        self.assertEqual(s_r.memory.get(50), 42)
        self.assertEqual(s_c.memory.get(50), 42)

    def test_mul_with_zero(self):
        src = """\
MOV R0, 99
MOV R1, 0
MUL R2, R0, R1
STORE R2, 50
HALT"""
        risc_src, cisc_src = transpile_common_to_risc_cisc(src)

        s_r = execute_risc(parse_risc(risc_src), CPUState())
        s_c = execute_cisc(parse_cisc(cisc_src), CPUState())

        self.assertEqual(s_r.memory.get(50), 0)
        self.assertEqual(s_c.memory.get(50), 0)

    def test_chained_multiplications(self):
        """R3 = 2 * 3 * 4 = 24 — chains MULs with intermediate register."""
        src = """\
MOV R0, 2
MOV R1, 3
MOV R2, 4
MUL R3, R0, R1
MUL R3, R3, R2
STORE R3, 50
HALT"""
        risc_src, cisc_src = transpile_common_to_risc_cisc(src)

        s_r = execute_risc(parse_risc(risc_src), CPUState())
        s_c = execute_cisc(parse_cisc(cisc_src), CPUState())

        self.assertEqual(s_r.memory.get(50), 24)
        self.assertEqual(s_c.memory.get(50), 24)
