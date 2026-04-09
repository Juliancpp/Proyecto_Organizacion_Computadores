import type { SimEvent, TimelineCycle } from "@/types/simulation";
import { getCurrentMicroEvent, getInternalBusText, getMicroAddress } from "@/lib/cpu-model";
import { getRiscControlSignals } from "@/lib/cpu-model/riscModel";

export type Quiz = {
  question: string;
  options: string[];
  answer: string;
  explanation: string;
};

export type MicroSummary = {
  instruction: string;
  componentsUsed: string[];
  memoryAccessed: string;
  resultStoredIn: string;
};

export type DecisionFlow = {
  question: string;
  answer: string;
};

export type CPUStateMap = Record<string, string | number>;

export type GuidedStep = {
  cycle: number;
  instruction: string;
  stage: string;
  aluOp: string;
  signals: {
    RegWrite: 0 | 1;
    MemRead: 0 | 1;
    MemWrite: 0 | 1;
    ALUSrc: 0 | 1;
  };
  narration: string;
  focusComponent: string;
  pathLabel: string;
  rawEvent: SimEvent;
  quiz?: Quiz;
  decisionFlow: DecisionFlow[];
  beforeState: CPUStateMap;
  afterState: CPUStateMap;
  operationLabel?: string;
  microSummary?: MicroSummary;
};

const RISC_STAGE_ORDER = ["IF", "ID", "EX", "MEM", "WB"];

function inferRiscStage(event: SimEvent): string {
  if (event.meta?.pipeline_stage) return String(event.meta.pipeline_stage);
  if (event.component === "PC") return "IF";
  if (event.component === "CONTROL") return "ID";
  if (event.component === "ALU") return "EX";
  if (event.component === "MEMORY" || event.component === "BUS") return "MEM";
  if (event.component === "REGISTERS") return "WB";
  return "ID";
}

function readInstructionFromEvents(events: SimEvent[]): string {
  const fetch = events.find((e) => e.action.startsWith("IF: Fetch"));
  if (fetch) {
    const m = fetch.action.match(/'(.+)'/);
    return m?.[1] ?? fetch.action;
  }
  const decode = events.find((e) => e.action.includes("Decode"));
  return decode?.action ?? "Instruction in progress";
}

function narrationForRiscStage(stage: string, event: SimEvent, instruction: string): string {
  const op = instruction.split(" ")[0] || "Instruction";
  switch (stage) {
    case "IF":
      return `The CPU starts by looking up the next instruction from memory using the Program Counter (PC).`;
    case "ID":
      return `The Control Unit reads '${op}'. It is now decoding what this means to configure the CPU's internal paths.`;
    case "EX":
      return `The ALU is now executing the arithmetic or logical part of the '${op}' operation.`;
    case "MEM":
      return event.action.includes("Read")
        ? `The CPU is reading data from main memory.`
        : event.action.includes("Write")
        ? `The CPU is storing the computed result into main memory.`
        : `This '${op}' instruction doesn't need data memory, so it simply passes through this stage.`;
    case "WB":
      return `Finally, the result is saved back into the internal Register File to complete the operation.`;
    default:
      return "Advancing instruction through the pipeline.";
  }
}

function pathLabelForRisc(stage: string, event: SimEvent): string {
  switch (stage) {
    case "IF": return "PC -> Instruction Memory -> Pipeline";
    case "ID": return "Control Unit decodes -> Read Registers";
    case "EX": return "Registers/Immediate -> ALU";
    case "MEM": return "ALU Result -> Data Memory";
    case "WB": return "Result -> Register File";
    default: return event.action;
  }
}

function generateQuizForRiscStage(stage: string): Quiz {
  switch (stage) {
    case "IF":
      return {
        question: "What must the CPU do first to execute an instruction?",
        options: ["Fetch it from memory", "Run it in the ALU", "Store data in a register"],
        answer: "Fetch it from memory",
        explanation: "Before doing anything, the CPU needs to retrieve the instruction code from memory using the Program Counter."
      };
    case "ID":
      return {
        question: "Which component is responsible for 'understanding' the instruction?",
        options: ["ALU", "Control Unit", "Data Memory"],
        answer: "Control Unit",
        explanation: "The Control Unit decodes the opcode and activates the appropriate control signals for the datapath."
      };
    case "EX":
      return {
        question: "Where does the mathematical or logical execution happen?",
        options: ["Register File", "ALU", "Program Counter"],
        answer: "ALU",
        explanation: "The Arithmetic Logic Unit (ALU) performs all calculations (addition, logic, etc)."
      };
    case "MEM":
      return {
        question: "Does every instruction use the Data Memory?",
        options: ["Yes", "No"],
        answer: "No",
        explanation: "Only instructions like LOAD or STORE access data memory. Math instructions just pass through."
      };
    case "WB":
    default:
      return {
        question: "Where do we usually save the final computed result?",
        options: ["Main Memory", "Register File", "Control Unit"],
        answer: "Register File",
        explanation: "Results from ALU or memory reads are written back to the fast Register File (Write-Back)."
      };
  }
}

function generateDecisionFlow(signals: any): DecisionFlow[] {
  return [
    { question: "Needs to compute something (ALU)?", answer: signals.ALUSrc || signals.ALUOp !== "PASS" ? "YES" : "NO" },
    { question: "Reads from memory?", answer: signals.MemRead ? "YES" : "NO" },
    { question: "Writes to memory?", answer: signals.MemWrite ? "YES" : "NO" },
    { question: "Updates a register?", answer: signals.RegWrite ? "YES" : "NO" },
  ];
}

function toRiscSteps(timeline: TimelineCycle[]): GuidedStep[] {
  const steps: GuidedStep[] = [];
  let localState: CPUStateMap = {};
  
  for (const cycle of timeline) {
    const instruction = readInstructionFromEvents(cycle.events);
    const stageEvents = cycle.events
      .map((event) => ({ stage: inferRiscStage(event), event }))
      .filter(({ stage }) => RISC_STAGE_ORDER.includes(stage));

    const orderedEvents = stageEvents.length > 0
        ? RISC_STAGE_ORDER.flatMap((stage) => stageEvents.filter((s) => s.stage === stage).slice(0, 1))
        : cycle.events.slice(0, 1).map((event) => ({ stage: inferRiscStage(event), event }));

    for (const { stage, event } of orderedEvents) {
      const opcode = (instruction.split(" ")[0] || "NOP").toUpperCase();
      const control = getRiscControlSignals(opcode);
      
      const beforeState = { ...localState };
      let operationLabel = event.action;
      
      // Parse output to update our pseudo-local state if applicable
      if (event.component === "REGISTERS" && event.action.includes("Write")) {
         const match = event.action.match(/(R\d+).+?(\d+)/i);
         if (match) localState[match[1]] = match[2];
      }

      const isLastStage = stage === "WB";
      const microSummary = isLastStage ? {
        instruction,
        componentsUsed: control.RegWrite ? ["Register File", "ALU"] : ["ALU"],
        memoryAccessed: control.MemRead || control.MemWrite ? "Yes" : "No",
        resultStoredIn: control.RegWrite ? "Register" : control.MemWrite ? "Memory" : "None"
      } : undefined;

      steps.push({
        cycle: cycle.cycle,
        instruction,
        stage: String(stage),
        aluOp: control.ALUOp,
        signals: { RegWrite: control.RegWrite, MemRead: control.MemRead, MemWrite: control.MemWrite, ALUSrc: control.ALUSrc },
        narration: narrationForRiscStage(stage, event, instruction),
        focusComponent: event.component,
        pathLabel: pathLabelForRisc(stage, event),
        rawEvent: event,
        quiz: generateQuizForRiscStage(stage),
        decisionFlow: generateDecisionFlow(control),
        beforeState,
        afterState: { ...localState },
        operationLabel,
        microSummary
      });
    }
  }
  return steps;
}

function toCiscSteps(timeline: TimelineCycle[]): GuidedStep[] {
  const steps: GuidedStep[] = [];
  let localState: CPUStateMap = {};

  for (const cycle of timeline) {
    const micro = getCurrentMicroEvent(cycle.events);
    if (!micro) continue;
    const instruction = String(micro.meta?.instruction || "CISC instruction").toUpperCase();
    const mar = getMicroAddress(micro.action);
    const focus = micro.action.includes("READ") || micro.action.includes("WRITE") ? "MEMORY" : micro.component;
    
    // Attempt rudimentary state update
    const beforeState = { ...localState };
    if (micro.component === "REGISTERS" && micro.action.includes("WRITE")) {
       const match = micro.action.match(/(R\d+).+?(\d+)/i);
       if (match) localState[match[1]] = match[2];
    }
    
    const isLastMicro = micro.meta?.micro_op_index === micro.meta?.total_micro_ops;
    
    steps.push({
      cycle: cycle.cycle,
      instruction,
      stage: `uOp ${micro.meta?.micro_op_index ?? "?"}/${micro.meta?.total_micro_ops ?? "?"}`,
      aluOp: micro.component === "ALU" ? instruction : "N/A",
      signals: {
        RegWrite: micro.component === "REGISTERS" && micro.action.includes("WRITE") ? 1 : 0,
        MemRead: micro.action.includes("READ") ? 1 : 0,
        MemWrite: micro.action.includes("WRITE") ? 1 : 0,
        ALUSrc: micro.component === "ALU" ? 1 : 0,
      },
      narration: `Deep inside the instruction, the CISC Control Unit is executing micro-operation: ${micro.action}. Notice how one CISC instruction breaks down into many steps!`,
      focusComponent: focus,
      pathLabel: mar ? `MAR <- ${mar}, ${getInternalBusText(micro)}` : getInternalBusText(micro),
      rawEvent: micro,
      quiz: {
        question: "CISC breaks down complex instructions into:",
        options: ["Many simple micro-operations", "One gigantic hardware operation", "Software loops"],
        answer: "Many simple micro-operations",
        explanation: "To execute complex instructions, CISC processors use a 'microcode' engine that runs smaller, sequence-based internal micro-ops."
      },
      decisionFlow: generateDecisionFlow({ RegWrite: micro.component === "REGISTERS", MemRead: micro.action.includes("READ"), MemWrite: micro.action.includes("WRITE"), ALUSrc: micro.component === "ALU" }),
      beforeState,
      afterState: { ...localState },
      operationLabel: micro.action,
      microSummary: isLastMicro ? {
        instruction,
        componentsUsed: ["Micro-code ROM", "ALU", "Registers"],
        memoryAccessed: instruction.includes("LOAD") || instruction.includes("STORE") ? "Yes" : "Maybe",
        resultStoredIn: instruction.includes("STORE") ? "Memory" : "Register/Internal"
      } : undefined
    });
  }
  return steps;
}

export function buildGuidedSteps(arch: "risc" | "cisc", timeline: TimelineCycle[]): GuidedStep[] {
  return arch === "risc" ? toRiscSteps(timeline) : toCiscSteps(timeline);
}
