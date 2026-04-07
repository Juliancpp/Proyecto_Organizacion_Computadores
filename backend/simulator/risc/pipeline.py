"""
RISC 5-stage pipeline simulator.

Stages:
  IF  — Instruction Fetch
  ID  — Instruction Decode / Register Read
  EX  — Execute (ALU / branch resolution)
  MEM — Memory access
  WB  — Write-Back to register file

This simulator models in-order issue with structural hazard detection.
Each cycle, all occupied stages advance one position.  When a stall or
branch flush occurs, the affected stages are invalidated.

The pipeline produces events that describe what each stage is doing on
every cycle, enabling the frontend to draw a multi-row pipeline diagram.
"""

from __future__ import annotations

import logging
from typing import Any

from simulator.core.cpu_state import CPUState
from simulator.core.events import Component, Event
from simulator.core.exceptions import ExecutionError
from simulator.parser.assembly_parser import Instruction, ParseResult

logger = logging.getLogger(__name__)

MAX_CYCLES = 10_000


# ---------------------------------------------------------------------------
# Pipeline stage names (order matters)
# ---------------------------------------------------------------------------

STAGES = ("IF", "ID", "EX", "MEM", "WB")


# ---------------------------------------------------------------------------
# Slot in the pipeline — tracks one instruction through all stages
# ---------------------------------------------------------------------------

class PipelineSlot:
    """One instruction flowing through the pipeline."""

    def __init__(self, instr: Instruction, index: int) -> None:
        self.instr = instr
        self.index = index            # position in the instruction list
        self.stage_idx: int = 0       # 0=IF, 1=ID, …
        self.computed_value: int = 0  # result buffer
        self.branch_target: int | None = None
        self.branch_taken: bool = False
        self.flushed: bool = False

    @property
    def stage(self) -> str:
        return STAGES[self.stage_idx]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def execute_risc_pipeline(
    parse_result: ParseResult,
    state: CPUState | None = None,
) -> CPUState:
    """
    Execute a RISC program in a classic 5-stage pipeline model.

    At each cycle, every occupied pipeline stage performs its work
    concurrently.  Stalls are inserted for data hazards; branches
    cause a flush of younger instructions.

    Returns the final CPUState with timeline populated.
    """
    instructions = parse_result.instructions
    labels = parse_result.labels

    if state is None:
        state = CPUState()

    if not instructions:
        return state

    pipeline: list[PipelineSlot] = []   # active pipeline slots
    fetch_pc: int = 0                    # next PC to fetch from
    done: bool = False

    while not done:
        if state.cycles >= MAX_CYCLES:
            raise ExecutionError("Maximum cycle count exceeded (pipeline)", fetch_pc)

        state.new_cycle()
        cycle_events: list[Event] = []

        # ---------------------------------------------------------------
        # Fetch new instruction FIRST (if pipeline has room and not halted)
        # so that the IF event appears on this cycle.
        # ---------------------------------------------------------------
        if not state.halted and fetch_pc < len(instructions) and len(pipeline) < len(STAGES):
            slot = PipelineSlot(instructions[fetch_pc], fetch_pc)
            pipeline.append(slot)
            fetch_pc += 1

        # ---------------------------------------------------------------
        # Process all occupied stages (all slots work concurrently).
        # ---------------------------------------------------------------

        completed_slots: list[PipelineSlot] = []
        flush_from: int | None = None

        for slot in pipeline:
            if slot.flushed:
                continue

            stage = slot.stage
            instr = slot.instr

            if stage == "IF":
                cycle_events.append(Event(
                    Component.MEMORY, f"IF: Fetch '{instr.raw.strip()}'",
                    inputs=[slot.index], output=instr.opcode,
                    meta={"pipeline_stage": "IF", "instruction_index": slot.index},
                ))

            elif stage == "ID":
                cycle_events.append(Event(
                    Component.CONTROL, f"ID: Decode {instr.opcode}",
                    inputs=instr.operands, output=f"{instr.opcode} decoded",
                    meta={"pipeline_stage": "ID"},
                ))

            elif stage == "EX":
                _pipeline_execute_stage(slot, state, labels, cycle_events)

            elif stage == "MEM":
                _pipeline_mem_stage(slot, state, cycle_events)

            elif stage == "WB":
                _pipeline_wb_stage(slot, state, cycle_events)
                completed_slots.append(slot)

                # Check for branch/jump resolution
                if slot.branch_target is not None:
                    flush_from = slot.branch_target
                if instr.opcode == "HALT":
                    state.halted = True

        # Add all events for this cycle
        for ev in cycle_events:
            state.add_event(ev)

        # ---------------------------------------------------------------
        # Advance stages
        # ---------------------------------------------------------------
        for slot in pipeline:
            if not slot.flushed and slot not in completed_slots:
                slot.stage_idx += 1

        # Remove completed slots
        pipeline = [s for s in pipeline if s not in completed_slots and not s.flushed]

        # ---------------------------------------------------------------
        # Handle branch flush
        # ---------------------------------------------------------------
        if flush_from is not None:
            for slot in pipeline:
                slot.flushed = True
            pipeline = []
            fetch_pc = flush_from
            state.add_event(Event(
                Component.CONTROL, "Pipeline FLUSH due to branch",
                inputs=[], output=f"New fetch PC = {flush_from}",
                meta={"flush": True},
            ))

        state.end_cycle()

        # Done when pipeline is drained and no more instructions to fetch
        if not pipeline and (fetch_pc >= len(instructions) or state.halted):
            done = True

    return state


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------

def _pipeline_execute_stage(
    slot: PipelineSlot,
    state: CPUState,
    labels: dict[str, int],
    events: list[Event],
) -> None:
    """EX stage: ALU operations, branch resolution."""
    instr = slot.instr
    ops = instr.operands

    if instr.opcode in ("ADD", "SUB"):
        rd, rs1, rs2 = ops
        v1 = state.read_register(rs1)
        v2 = state.read_register(rs2)
        result = (v1 + v2) if instr.opcode == "ADD" else (v1 - v2)
        slot.computed_value = result
        events.append(Event(
            Component.ALU, f"EX: {instr.opcode} R{rs1}({v1}) {'+'if instr.opcode=='ADD' else '-'} R{rs2}({v2}) = {result}",
            inputs=[v1, v2], output=result,
            meta={"pipeline_stage": "EX", "operation": instr.opcode},
        ))

    elif instr.opcode == "MOV":
        rd, imm = ops
        slot.computed_value = imm
        events.append(Event(
            Component.ALU, f"EX: MOV immediate {imm}",
            inputs=[imm], output=imm,
            meta={"pipeline_stage": "EX"},
        ))

    elif instr.opcode == "LOAD":
        rd, addr = ops
        events.append(Event(
            Component.ALU, f"EX: Compute address {addr}",
            inputs=[addr], output=addr,
            meta={"pipeline_stage": "EX"},
        ))
        slot.computed_value = addr  # pass address to MEM stage

    elif instr.opcode == "STORE":
        rs, addr = ops
        slot.computed_value = addr
        events.append(Event(
            Component.ALU, f"EX: Compute store address {addr}",
            inputs=[addr], output=addr,
            meta={"pipeline_stage": "EX"},
        ))

    elif instr.opcode in ("BEQ", "BNE"):
        rs1, rs2, label = ops
        v1 = state.read_register(rs1)
        v2 = state.read_register(rs2)
        if instr.opcode == "BEQ":
            taken = v1 == v2
        else:
            taken = v1 != v2

        if label not in labels:
            raise ExecutionError(f"Undefined label '{label}'", slot.index)

        target = labels[label] if taken else None
        slot.branch_target = target if taken else None
        slot.branch_taken = taken

        events.append(Event(
            Component.ALU, f"EX: {instr.opcode} R{rs1}({v1}) vs R{rs2}({v2}) → {'TAKEN' if taken else 'NOT TAKEN'}",
            inputs=[v1, v2], output=taken,
            meta={"pipeline_stage": "EX", "branch_taken": taken},
        ))

    elif instr.opcode == "JMP":
        label = ops[0]
        if label not in labels:
            raise ExecutionError(f"Undefined label '{label}'", slot.index)
        slot.branch_target = labels[label]
        events.append(Event(
            Component.CONTROL, f"EX: JMP → {label}",
            inputs=[label], output=labels[label],
            meta={"pipeline_stage": "EX"},
        ))

    elif instr.opcode == "HALT":
        events.append(Event(
            Component.CONTROL, "EX: HALT detected",
            inputs=[], output="HALT",
            meta={"pipeline_stage": "EX"},
        ))

    elif instr.opcode == "NOP":
        events.append(Event(
            Component.CONTROL, "EX: NOP",
            inputs=[], output="NOP",
            meta={"pipeline_stage": "EX"},
        ))


def _pipeline_mem_stage(
    slot: PipelineSlot,
    state: CPUState,
    events: list[Event],
) -> None:
    """MEM stage: memory read/write."""
    instr = slot.instr
    ops = instr.operands

    if instr.opcode == "LOAD":
        rd, addr = ops
        value = state.read_memory(addr)
        slot.computed_value = value
        events.append(Event(
            Component.MEMORY, f"MEM: Read MEM[{addr}] = {value}",
            inputs=[addr], output=value,
            meta={"pipeline_stage": "MEM", "address": addr},
        ))

    elif instr.opcode == "STORE":
        rs, addr = ops
        value = state.read_register(rs)
        state.write_memory(addr, value)
        events.append(Event(
            Component.MEMORY, f"MEM: Write MEM[{addr}] ← {value}",
            inputs=[addr, value], output=value,
            meta={"pipeline_stage": "MEM", "address": addr},
        ))

    else:
        events.append(Event(
            Component.MEMORY, f"MEM: Pass-through ({instr.opcode})",
            inputs=[], output="No memory access",
            meta={"pipeline_stage": "MEM"},
        ))


def _pipeline_wb_stage(
    slot: PipelineSlot,
    state: CPUState,
    events: list[Event],
) -> None:
    """WB stage: write result back to register file."""
    instr = slot.instr
    ops = instr.operands

    if instr.opcode in ("ADD", "SUB"):
        rd = ops[0]
        state.write_register(rd, slot.computed_value)
        events.append(Event(
            Component.REGISTERS, f"WB: R{rd} ← {slot.computed_value}",
            inputs=[slot.computed_value], output=slot.computed_value,
            meta={"pipeline_stage": "WB", "register": f"R{rd}"},
        ))

    elif instr.opcode == "MOV":
        rd = ops[0]
        state.write_register(rd, slot.computed_value)
        events.append(Event(
            Component.REGISTERS, f"WB: R{rd} ← {slot.computed_value}",
            inputs=[slot.computed_value], output=slot.computed_value,
            meta={"pipeline_stage": "WB", "register": f"R{rd}"},
        ))

    elif instr.opcode == "LOAD":
        rd = ops[0]
        state.write_register(rd, slot.computed_value)
        events.append(Event(
            Component.REGISTERS, f"WB: R{rd} ← {slot.computed_value}",
            inputs=[slot.computed_value], output=slot.computed_value,
            meta={"pipeline_stage": "WB", "register": f"R{rd}"},
        ))

    else:
        events.append(Event(
            Component.REGISTERS, f"WB: No write-back ({instr.opcode})",
            inputs=[], output="—",
            meta={"pipeline_stage": "WB"},
        ))
