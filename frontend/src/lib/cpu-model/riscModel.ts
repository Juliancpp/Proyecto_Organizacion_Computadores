import type { SimEvent } from "@/types/simulation";
import type { ControlSignals } from "@/lib/cpu-model/types";

export function getRiscOpcodeFromEvents(events: SimEvent[]): string {
  const decoded = events.find((e) => e.meta?.pipeline_stage === "ID" && e.action.includes("Decode"));
  if (!decoded) return "NOP";
  const parts = decoded.action.split("Decode ");
  return (parts[1] || "NOP").trim().toUpperCase();
}

export function getRiscControlSignals(opcode: string): ControlSignals {
  switch (opcode) {
    case "ADD":
      return { RegWrite: 1, MemRead: 0, MemWrite: 0, ALUOp: "ADD", ALUSrc: 0 };
    case "SUB":
      return { RegWrite: 1, MemRead: 0, MemWrite: 0, ALUOp: "SUB", ALUSrc: 0 };
    case "LOAD":
      return { RegWrite: 1, MemRead: 1, MemWrite: 0, ALUOp: "ADDR", ALUSrc: 1 };
    case "STORE":
      return { RegWrite: 0, MemRead: 0, MemWrite: 1, ALUOp: "ADDR", ALUSrc: 1 };
    case "MOV":
      return { RegWrite: 1, MemRead: 0, MemWrite: 0, ALUOp: "PASS", ALUSrc: 1 };
    case "BEQ":
    case "BNE":
      return { RegWrite: 0, MemRead: 0, MemWrite: 0, ALUOp: "CMP", ALUSrc: 0 };
    default:
      return { RegWrite: 0, MemRead: 0, MemWrite: 0, ALUOp: "NOP", ALUSrc: 0 };
  }
}

export function getRiscRegReads(events: SimEvent[]): SimEvent[] {
  return events.filter((e) => e.component === "REGISTERS" && e.action.includes("READ"));
}

export function getRiscRegWrites(events: SimEvent[]): SimEvent[] {
  return events.filter((e) => e.component === "REGISTERS" && e.action.includes("WRITE"));
}

export function getRiscAluEvent(events: SimEvent[]): SimEvent | undefined {
  return events.find((e) => e.component === "ALU");
}

export function getRiscStageIndicator(events: SimEvent[]): string {
  const activeStage = events.find((e) => e.meta?.pipeline_stage)?.meta?.pipeline_stage;
  return activeStage ? `Stage ${activeStage}` : "Idle";
}
