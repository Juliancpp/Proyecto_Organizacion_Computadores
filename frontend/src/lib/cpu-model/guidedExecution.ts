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
  const op = instruction.split(" ")[0] || "Instrucción";
  switch (stage) {
    case "IF":
      return `La CPU comienza buscando la siguiente instrucción en la memoria usando el Contador de Programa (PC).`;
    case "ID":
      return `La Unidad de Control lee '${op}'. Ahora decodifica qué significa para configurar las rutas internas de la CPU.`;
    case "EX":
      return `La ALU está ejecutando la parte aritmética o lógica de la operación '${op}'.`;
    case "MEM":
      return event.action.includes("Read")
        ? `La CPU está leyendo datos de la memoria principal.`
        : event.action.includes("Write")
        ? `La CPU está guardando el resultado en la memoria principal.`
        : `Esta instrucción '${op}' no usa memoria de datos, por lo que simplemente pasa por esta etapa.`;
    case "WB":
      return `Finalmente, el resultado calculado se guarda en el archivo de registros interno (Register File).`;
    default:
      return "Avanzando instrucción en el pipeline.";
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

function generateQuizForRiscStage(stage: string, quizTracker: { count: number }): Quiz | undefined {
  if (quizTracker.count >= 2) return undefined;

  let quiz: Quiz | undefined;
  switch (stage) {
    case "ID":
      quiz = {
        question: "¿Qué componente se activará ahora para decodificar?",
        options: ["ALU", "Unidad de Control", "Registros", "PC"],
        answer: "Unidad de Control",
        explanation: "La Unidad de Control lee la instrucción y activa las señales para el datapath."
      };
      break;
    case "EX":
      quiz = {
        question: "¿Dónde se ejecutan las operaciones matemáticas?",
        options: ["Registros", "ALU", "PC"],
        answer: "ALU",
        explanation: "La ALU se encarga de todos los cálculos matemáticos (sumas, restas, lógica)."
      };
      break;
    case "MEM":
      quiz = {
        question: "¿Se accederá a memoria?",
        options: ["Sí", "No"],
        answer: "Sí",
        explanation: "Las instrucciones LOAD/STORE leen o escriben memoria principal."
      };
      break;
    case "WB":
      quiz = {
        question: "¿Se escribirá en un registro?",
        options: ["Sí", "No"],
        answer: "Sí",
        explanation: "El resultado final se escribe de vuelta en un registro interno."
      };
      break;
  }
  
  if (quiz) quizTracker.count++;
  return quiz;
}

function generateDecisionFlow(signals: any): DecisionFlow[] {
  return [
    { question: "¿Calcula operaciones en ALU?", answer: signals.ALUSrc || signals.ALUOp !== "PASS" ? "SÍ" : "NO" },
    { question: "¿Lee de memoria?", answer: signals.MemRead ? "SÍ" : "NO" },
    { question: "¿Escribe en memoria?", answer: signals.MemWrite ? "SÍ" : "NO" },
    { question: "¿Modifica un registro?", answer: signals.RegWrite ? "SÍ" : "NO" },
  ];
}

function toRiscSteps(timeline: TimelineCycle[], quizTracker: { count: number }): GuidedStep[] {
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
        quiz: generateQuizForRiscStage(stage, quizTracker),
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

function toCiscSteps(timeline: TimelineCycle[], quizTracker: { count: number }): GuidedStep[] {
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
    const isFirstMicro = micro.meta?.micro_op_index === 1;
    let ciscQuiz: Quiz | undefined;
    
    if (isFirstMicro && quizTracker.count < 2) {
      ciscQuiz = {
        question: "¿En qué divide CISC las instrucciones complejas?",
        options: ["Micro-operaciones", "Bucles de software", "Hardware directo"],
        answer: "Micro-operaciones",
        explanation: "CISC usa secuencias más pequeñas llamadas micro-operaciones."
      };
      quizTracker.count++;
    } else if (isLastMicro && quizTracker.count < 2) {
      ciscQuiz = {
        question: "¿Se escribirá en un registro al finalizar?",
        options: ["Sí", "No"],
        answer: micro.component === "REGISTERS" && micro.action.includes("WRITE") ? "Sí" : "No",
        explanation: "Si la operación era aritmética o de carga, termina escribiendo su valor allí."
      };
      quizTracker.count++;
    }

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
      narration: `En lo profundo de la instrucción, la Unidad de Control CISC ejecuta la micro-operación: ${micro.action}. ¡Nota cómo una instrucción CISC se divide en muchos pasos!`,
      focusComponent: focus,
      pathLabel: mar ? `MAR <- ${mar}, ${getInternalBusText(micro)}` : getInternalBusText(micro),
      rawEvent: micro,
      quiz: ciscQuiz,
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
  const tracker = { count: 0 };
  return arch === "risc" ? toRiscSteps(timeline, tracker) : toCiscSteps(timeline, tracker);
}
