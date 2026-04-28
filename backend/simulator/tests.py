"""
Comprehensive test suite for the RISC vs CISC CPU simulator.

Tests cover:
  - Assembly parsing (RISC and CISC)
  - RISC execution engine (all instructions, branches, loops)
  - CISC execution engine (micro-op decomposition)
  - RISC pipeline simulator
  - Metrics computation
  - API endpoints
  - Error handling
"""

import json

from django.test import TestCase, Client

from simulator.core.cpu_state import CPUState
from simulator.core.events import Event, Component
from simulator.core.exceptions import (
    ParseError,
    InvalidInstructionError,
    ExecutionError,
)
from simulator.parser.assembly_parser import parse_risc, parse_cisc
from simulator.risc.engine import execute_risc
from simulator.risc.pipeline import execute_risc_pipeline
from simulator.cisc.engine import execute_cisc
from simulator.metrics.calculator import (
    compute_metrics,
    count_executed_instructions,
    compare,
)


# =========================================================================
# CORE TESTS
# =========================================================================

class EventModelTests(TestCase):
    """Tests for the Event class and Component enum."""

    def test_event_creation(self):
        event = Event(Component.ALU, "ADD operation", inputs=[5, 10], output=15)
        self.assertEqual(event.component, Component.ALU)
        self.assertEqual(event.action, "ADD operation")
        self.assertEqual(event.inputs, [5, 10])
        self.assertEqual(event.output, 15)

    def test_event_to_dict(self):
        event = Event(Component.MEMORY, "READ", inputs=[100], output=42, meta={"addr": 100})
        d = event.to_dict()
        self.assertEqual(d["component"], "MEMORY")
        self.assertEqual(d["action"], "READ")
        self.assertEqual(d["inputs"], [100])
        self.assertEqual(d["output"], 42)
        self.assertEqual(d["meta"]["addr"], 100)

    def test_event_string_component(self):
        event = Event("ALU", "test")
        self.assertEqual(event.component, Component.ALU)

    def test_event_empty_meta_not_in_dict(self):
        event = Event(Component.PC, "increment", inputs=[0], output=1)
        d = event.to_dict()
        self.assertNotIn("meta", d)


class CPUStateTests(TestCase):
    """Tests for the CPUState class."""

    def test_initial_state(self):
        state = CPUState()
        self.assertEqual(state.pc, 0)
        self.assertEqual(state.registers, [0] * 8)
        self.assertEqual(state.cycles, 0)
        self.assertFalse(state.halted)

    def test_register_read_write(self):
        state = CPUState()
        state.write_register(3, 42)
        self.assertEqual(state.read_register(3), 42)

    def test_register_out_of_range(self):
        state = CPUState()
        with self.assertRaises(IndexError):
            state.read_register(8)

    def test_memory_read_write(self):
        state = CPUState()
        state.write_memory(100, 255)
        self.assertEqual(state.read_memory(100), 255)

    def test_memory_uninitialized_default(self):
        state = CPUState()
        self.assertEqual(state.read_memory(50), 0)

    def test_memory_out_of_range(self):
        state = CPUState()
        with self.assertRaises(IndexError):
            state.write_memory(999, 1)

    def test_cycle_management(self):
        state = CPUState()
        state.new_cycle()
        self.assertEqual(state.cycles, 1)
        state.add_event(Event(Component.ALU, "test"))
        state.end_cycle()
        self.assertEqual(len(state.timeline), 1)
        # timeline stores CPUSnapshot objects; use .cycle attribute or .to_dict()
        self.assertEqual(state.timeline[0].cycle, 1)

    def test_reset(self):
        state = CPUState()
        state.write_register(0, 100)
        state.write_memory(50, 200)
        state.new_cycle()
        state.add_event(Event(Component.ALU, "test"))
        state.end_cycle()
        state.reset()
        self.assertEqual(state.pc, 0)
        self.assertEqual(state.registers, [0] * 8)
        self.assertEqual(state.cycles, 0)
        self.assertEqual(len(state.timeline), 0)

    def test_snapshot(self):
        state = CPUState()
        state.write_register(0, 5)
        state.pc = 3
        snap = state.snapshot()
        self.assertEqual(snap["pc"], 3)
        self.assertEqual(snap["registers"][0], 5)

    def test_clone(self):
        state = CPUState()
        state.write_register(0, 99)
        cloned = state.clone()
        cloned.write_register(0, 0)
        self.assertEqual(state.read_register(0), 99)  # original unchanged


# =========================================================================
# PARSER TESTS
# =========================================================================

class RISCParserTests(TestCase):
    """Tests for the RISC assembly parser."""

    def test_parse_mov(self):
        result = parse_risc("MOV R0, 5")
        self.assertEqual(len(result.instructions), 1)
        self.assertEqual(result.instructions[0].opcode, "MOV")
        self.assertEqual(result.instructions[0].operands, [0, 5])

    def test_parse_add(self):
        result = parse_risc("ADD R2, R0, R1")
        instr = result.instructions[0]
        self.assertEqual(instr.opcode, "ADD")
        self.assertEqual(instr.operands, [2, 0, 1])

    def test_parse_load_store(self):
        result = parse_risc("LOAD R0, 100\nSTORE R1, 200")
        self.assertEqual(len(result.instructions), 2)
        self.assertEqual(result.instructions[0].operands, [0, 100])
        self.assertEqual(result.instructions[1].operands, [1, 200])

    def test_parse_labels(self):
        code = "LOOP: MOV R0, 1\nJMP LOOP"
        result = parse_risc(code)
        self.assertIn("LOOP", result.labels)
        self.assertEqual(result.labels["LOOP"], 0)

    def test_parse_beq(self):
        result = parse_risc("BEQ R0, R1, END\nEND: HALT")
        instr = result.instructions[0]
        self.assertEqual(instr.opcode, "BEQ")
        self.assertEqual(instr.operands, [0, 1, "END"])

    def test_parse_comments(self):
        result = parse_risc("; this is a comment\nMOV R0, 5 ; inline comment")
        self.assertEqual(len(result.instructions), 1)

    def test_parse_empty_lines(self):
        result = parse_risc("\n\nMOV R0, 5\n\n")
        self.assertEqual(len(result.instructions), 1)

    def test_parse_halt(self):
        result = parse_risc("HALT")
        self.assertEqual(result.instructions[0].opcode, "HALT")

    def test_invalid_instruction(self):
        with self.assertRaises(InvalidInstructionError):
            parse_risc("FOOBAR R0, R1")

    def test_invalid_register(self):
        with self.assertRaises(InvalidInstructionError):
            parse_risc("MOV R9, 5")

    def test_duplicate_label(self):
        with self.assertRaises(ParseError):
            parse_risc("LOOP: NOP\nLOOP: NOP")

    def test_case_insensitive_opcodes(self):
        result = parse_risc("mov r0, 5")
        self.assertEqual(result.instructions[0].opcode, "MOV")


class CISCParserTests(TestCase):
    """Tests for the CISC assembly parser."""

    def test_parse_add_mem(self):
        result = parse_cisc("ADD [100], [200]")
        instr = result.instructions[0]
        self.assertEqual(instr.opcode, "ADD")
        self.assertEqual(instr.operands, [100, 200])

    def test_parse_mov_imm(self):
        result = parse_cisc("MOV [100], 42")
        instr = result.instructions[0]
        self.assertEqual(instr.operands, [100, 42])

    def test_parse_inc_dec(self):
        result = parse_cisc("INC [100]\nDEC [200]")
        self.assertEqual(len(result.instructions), 2)
        self.assertEqual(result.instructions[0].opcode, "INC")
        self.assertEqual(result.instructions[1].opcode, "DEC")

    def test_parse_labels(self):
        code = "START: MOV [100], 0\nJMP START"
        result = parse_cisc(code)
        self.assertIn("START", result.labels)

    def test_invalid_memory_ref(self):
        with self.assertRaises(InvalidInstructionError):
            parse_cisc("ADD R0, [100]")  # CISC ADD expects [addr], [addr]


# =========================================================================
# RISC ENGINE TESTS
# =========================================================================

class RISCEngineTests(TestCase):
    """Tests for the RISC execution engine."""

    def test_mov_and_add(self):
        code = "MOV R0, 5\nMOV R1, 10\nADD R2, R0, R1\nHALT"
        parsed = parse_risc(code)
        state = execute_risc(parsed)
        self.assertEqual(state.registers[2], 15)
        self.assertTrue(state.halted)

    def test_sub(self):
        code = "MOV R0, 20\nMOV R1, 8\nSUB R2, R0, R1\nHALT"
        parsed = parse_risc(code)
        state = execute_risc(parsed)
        self.assertEqual(state.registers[2], 12)

    def test_load_store(self):
        code = "MOV R0, 42\nSTORE R0, 100\nLOAD R1, 100\nHALT"
        parsed = parse_risc(code)
        state = execute_risc(parsed)
        self.assertEqual(state.registers[1], 42)
        self.assertEqual(state.memory[100], 42)

    def test_cycle_counts(self):
        # MOV=1, STORE=2, LOAD=2, HALT=1 → total 6
        code = "MOV R0, 1\nSTORE R0, 50\nLOAD R1, 50\nHALT"
        parsed = parse_risc(code)
        state = execute_risc(parsed)
        self.assertEqual(state.cycles, 6)

    def test_jmp(self):
        code = "JMP END\nMOV R0, 999\nEND: HALT"
        parsed = parse_risc(code)
        state = execute_risc(parsed)
        self.assertEqual(state.registers[0], 0)  # MOV was skipped
        self.assertTrue(state.halted)

    def test_beq_taken(self):
        code = "MOV R0, 5\nMOV R1, 5\nBEQ R0, R1, DONE\nMOV R2, 999\nDONE: HALT"
        parsed = parse_risc(code)
        state = execute_risc(parsed)
        self.assertEqual(state.registers[2], 0)  # MOV R2 was skipped

    def test_beq_not_taken_misprediction(self):
        code = "MOV R0, 5\nMOV R1, 10\nBEQ R0, R1, SKIP\nMOV R2, 42\nSKIP: HALT"
        parsed = parse_risc(code)
        state = execute_risc(parsed)
        self.assertEqual(state.registers[2], 42)  # Not taken, MOV executed

    def test_loop_countdown(self):
        code = "MOV R0, 3\nMOV R1, 1\nMOV R7, 0\nLOOP: SUB R0, R0, R1\nBNE R0, R7, LOOP\nHALT"
        parsed = parse_risc(code)
        state = execute_risc(parsed)
        self.assertEqual(state.registers[0], 0)  # Counted down to 0
        self.assertTrue(state.halted)

    def test_step_mode(self):
        code = "MOV R0, 5\nMOV R1, 10\nHALT"
        parsed = parse_risc(code)

        state = execute_risc(parsed, step=True)
        self.assertEqual(state.registers[0], 5)
        self.assertEqual(state.pc, 1)

        state = execute_risc(parsed, state, step=True)
        self.assertEqual(state.registers[1], 10)
        self.assertEqual(state.pc, 2)

    def test_timeline_events_structure(self):
        code = "MOV R0, 5\nHALT"
        parsed = parse_risc(code)
        state = execute_risc(parsed)
        # timeline stores CPUSnapshot objects; use .to_dict() for dict access
        for snapshot in state.timeline:
            record = snapshot.to_dict()
            self.assertIn("cycle", record)
            self.assertIn("events", record)
            for event in record["events"]:
                self.assertIn("component", event)
                self.assertIn("action", event)

    def test_undefined_label(self):
        code = "JMP NOWHERE"
        parsed = parse_risc(code)
        with self.assertRaises(ExecutionError):
            execute_risc(parsed)

    def test_nop(self):
        code = "NOP\nHALT"
        parsed = parse_risc(code)
        state = execute_risc(parsed)
        self.assertTrue(state.halted)
        self.assertEqual(state.cycles, 2)

    def test_all_event_components(self):
        """Ensure events reference valid Component values."""
        code = "MOV R0, 5\nMOV R1, 3\nADD R2, R0, R1\nSTORE R2, 100\nLOAD R3, 100\nHALT"
        parsed = parse_risc(code)
        state = execute_risc(parsed)
        valid_components = {c.value for c in Component}
        for snapshot in state.timeline:
            for event in snapshot.events:
                self.assertIn(event["component"], valid_components)


# =========================================================================
# CISC ENGINE TESTS
# =========================================================================

class CISCEngineTests(TestCase):
    """Tests for the CISC execution engine."""

    def test_mov_and_add(self):
        code = "MOV [100], 5\nMOV [200], 10\nADD [100], [200]\nHALT"
        parsed = parse_cisc(code)
        state = execute_cisc(parsed)
        self.assertEqual(state.memory[100], 15)

    def test_sub(self):
        code = "MOV [100], 20\nMOV [200], 8\nSUB [100], [200]\nHALT"
        parsed = parse_cisc(code)
        state = execute_cisc(parsed)
        self.assertEqual(state.memory[100], 12)

    def test_mul(self):
        code = "MOV [100], 6\nMOV [200], 7\nMUL [100], [200]\nHALT"
        parsed = parse_cisc(code)
        state = execute_cisc(parsed)
        self.assertEqual(state.memory[100], 42)

    def test_inc_dec(self):
        code = "MOV [100], 10\nINC [100]\nDEC [100]\nHALT"
        parsed = parse_cisc(code)
        state = execute_cisc(parsed)
        self.assertEqual(state.memory[100], 10)

    def test_micro_op_cycle_count(self):
        # MOV=2µops, ADD=4µops, HALT=1µop → total 2+2+4+1 = 9
        code = "MOV [100], 5\nMOV [200], 10\nADD [100], [200]\nHALT"
        parsed = parse_cisc(code)
        state = execute_cisc(parsed)
        self.assertEqual(state.cycles, 9)

    def test_jmp(self):
        code = "JMP END\nMOV [100], 999\nEND: HALT"
        parsed = parse_cisc(code)
        state = execute_cisc(parsed)
        self.assertEqual(state.memory.get(100, 0), 0)

    def test_beq_cisc(self):
        code = "MOV [100], 5\nMOV [200], 5\nBEQ [100], [200], DONE\nMOV [100], 999\nDONE: HALT"
        parsed = parse_cisc(code)
        state = execute_cisc(parsed)
        self.assertEqual(state.memory[100], 5)  # MOV [100], 999 skipped

    def test_micro_op_events_have_meta(self):
        code = "ADD [100], [200]\nHALT"
        parsed = parse_cisc(code)
        state = execute_cisc(parsed)
        for snapshot in state.timeline:
            for event in snapshot.events:
                meta = event.get("meta", {})
                if meta.get("micro_op"):
                    self.assertIn("micro_op_index", meta)

    def test_step_mode_cisc(self):
        code = "MOV [100], 5\nMOV [200], 10\nHALT"
        parsed = parse_cisc(code)
        state = execute_cisc(parsed, step=True)
        self.assertEqual(state.memory[100], 5)
        self.assertEqual(state.pc, 1)
        self.assertFalse(state.halted)


# =========================================================================
# PIPELINE TESTS
# =========================================================================

class PipelineTests(TestCase):
    """Tests for the RISC 5-stage pipeline simulator."""

    def test_pipeline_basic(self):
        code = "MOV R0, 5\nMOV R1, 10\nHALT"
        parsed = parse_risc(code)
        state = execute_risc_pipeline(parsed)
        self.assertEqual(state.registers[0], 5)
        self.assertEqual(state.registers[1], 10)
        self.assertTrue(state.halted)

    def test_pipeline_has_overlapping_events(self):
        """Pipeline cycles should have events from multiple stages."""
        code = "MOV R0, 1\nMOV R1, 2\nMOV R2, 3\nHALT"
        parsed = parse_risc(code)
        state = execute_risc_pipeline(parsed)

        # After a few cycles, we should see multiple pipeline stages per cycle
        multi_stage_found = False
        for record in state.timeline:
            stages_in_cycle = set()
            for event in record["events"]:
                stage = event.get("meta", {}).get("pipeline_stage")
                if stage:
                    stages_in_cycle.add(stage)
            if len(stages_in_cycle) > 1:
                multi_stage_found = True
                break

        self.assertTrue(multi_stage_found, "Pipeline should have overlapping stages")

    def test_pipeline_instruction_count(self):
        code = "MOV R0, 5\nMOV R1, 10\nADD R2, R0, R1\nHALT"
        parsed = parse_risc(code)
        state = execute_risc_pipeline(parsed)
        ic = count_executed_instructions(state)
        self.assertEqual(ic, 4)


# =========================================================================
# METRICS TESTS
# =========================================================================

class MetricsTests(TestCase):
    """Tests for the performance metrics calculator."""

    def test_basic_metrics(self):
        state = CPUState()
        state.cycles = 10
        metrics = compute_metrics(state, instruction_count=5, t_cycle_ns=1.0)
        self.assertEqual(metrics.instruction_count, 5)
        self.assertEqual(metrics.total_cycles, 10)
        self.assertEqual(metrics.cpi, 2.0)
        self.assertEqual(metrics.cpu_time_ns, 10.0)

    def test_zero_instructions(self):
        state = CPUState()
        metrics = compute_metrics(state, instruction_count=0, t_cycle_ns=1.0)
        self.assertEqual(metrics.cpi, 0.0)
        self.assertEqual(metrics.cpu_time_ns, 0.0)

    def test_comparison(self):
        risc_state = CPUState()
        risc_state.cycles = 8
        cisc_state = CPUState()
        cisc_state.cycles = 9
        result = compare(risc_state, 5, cisc_state, 3)
        self.assertGreater(result.speedup_risc_over_cisc, 1.0)

    def test_metrics_to_dict(self):
        state = CPUState()
        state.cycles = 6
        metrics = compute_metrics(state, instruction_count=3, t_cycle_ns=1.0)
        d = metrics.to_dict()
        self.assertIn("instruction_count", d)
        self.assertIn("total_cycles", d)
        self.assertIn("cpi", d)
        self.assertIn("cpu_time_ns", d)
        self.assertIn("cpu_time_us", d)

    def test_count_executed_instructions_risc(self):
        code = "MOV R0, 5\nMOV R1, 10\nADD R2, R0, R1\nHALT"
        parsed = parse_risc(code)
        state = execute_risc(parsed)
        ic = count_executed_instructions(state)
        self.assertEqual(ic, 4)

    def test_count_executed_instructions_cisc(self):
        code = "MOV [100], 5\nADD [100], [100]\nHALT"
        parsed = parse_cisc(code)
        state = execute_cisc(parsed)
        ic = count_executed_instructions(state)
        self.assertEqual(ic, 3)


# =========================================================================
# API ENDPOINT TESTS
# =========================================================================

class APITests(TestCase):
    """Integration tests for the REST API."""

    def setUp(self):
        self.client = Client()

    def test_simulate_split_mode(self):
        response = self.client.post(
            "/api/simulate/",
            data=json.dumps({
                "risc_code": "MOV R0, 5\nMOV R1, 10\nADD R2, R0, R1\nHALT",
                "cisc_code": "MOV [100], 5\nMOV [200], 10\nADD [100], [200]\nHALT",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("risc", data)
        self.assertIn("cisc", data)
        self.assertIn("comparison", data)

        # Check structure
        self.assertIn("timeline", data["risc"])
        self.assertIn("metrics", data["risc"])
        self.assertIn("final_state", data["risc"])

    def test_simulate_risc_only(self):
        response = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({"code": "MOV R0, 5\nHALT"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("timeline", data)
        self.assertIn("metrics", data)
        self.assertEqual(data["final_state"]["registers"][0], 5)

    def test_simulate_cisc_only(self):
        response = self.client.post(
            "/api/simulate/cisc/",
            data=json.dumps({"code": "MOV [100], 42\nHALT"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["final_state"]["memory"]["100"], 42)

    def test_simulate_pipeline_mode(self):
        response = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({
                "code": "MOV R0, 5\nMOV R1, 10\nHALT",
                "pipeline": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_simulate_empty_code(self):
        response = self.client.post(
            "/api/simulate/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_simulate_invalid_instruction(self):
        response = self.client.post(
            "/api/simulate/risc/",
            data=json.dumps({"code": "INVALID R0, R1"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertIn("error", data)

    def test_simulate_with_custom_tcycle(self):
        response = self.client.post(
            "/api/simulate/",
            data=json.dumps({
                "risc_code": "MOV R0, 5\nHALT",
                "cisc_code": "MOV [100], 5\nHALT",
                "risc_tcycle": 0.5,
                "cisc_tcycle": 2.0,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["risc"]["metrics"]["t_cycle_ns"], 0.5)
        self.assertEqual(data["cisc"]["metrics"]["t_cycle_ns"], 2.0)

    def test_partial_failure_returns_successful_side(self):
        """If CISC code is invalid but RISC succeeds, return RISC result + error."""
        response = self.client.post(
            "/api/simulate/",
            data=json.dumps({
                "risc_code": "MOV R0, 5\nHALT",
                "cisc_code": "INVALID [100]",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("risc", data)
        self.assertIn("errors", data)
        self.assertIn("cisc", data["errors"])

    def test_simulate_with_transpile_common_code(self):
        response = self.client.post(
            "/api/simulate/",
            data=json.dumps({
                "code": "MOV R0, 5\nMOV R1, 10\nADD R2, R0, R1\nSTORE R2, 100\nHALT",
                "transpile": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("risc", data)
        self.assertIn("cisc", data)
        self.assertIn("comparison", data)
        self.assertEqual(data["risc"]["final_state"]["memory"]["100"], 15)
        self.assertEqual(data["cisc"]["final_state"]["memory"]["100"], 15)

    def test_transpile_requires_unified_code(self):
        response = self.client.post(
            "/api/simulate/",
            data=json.dumps({
                "risc_code": "MOV R0, 5\nHALT",
                "transpile": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)

    def test_transpile_unsupported_opcode(self):
        response = self.client.post(
            "/api/simulate/",
            data=json.dumps({
                "code": "MUL R0, R1, R2\nHALT",
                "transpile": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertIn("error", data)
