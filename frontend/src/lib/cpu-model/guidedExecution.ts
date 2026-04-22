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
  const inputs = event.inputs || [];
  const output = event.output;

  switch (stage) {
    case "IF":
      return `La CPU lee la instrucción '${instruction.trim()}' desde la memoria de instrucciones, usando el valor actual del PC como dirección. Esta es la fase de búsqueda (Fetch).`;
    case "ID": {
      const opUpper = op.toUpperCase();
      const signalExplanations: Record<string, string> = {
        ADD: "RegWrite=1 (escribirá resultado en registro), ALUSrc=0 (operandos desde registros)",
        SUB: "RegWrite=1 (escribirá resultado en registro), ALUSrc=0 (operandos desde registros)",
        LOAD: "RegWrite=1, MemRead=1 (leerá dato de memoria), ALUSrc=1 (dirección inmediata)",
        STORE: "MemWrite=1 (escribirá en memoria), ALUSrc=1 (dirección inmediata)",
        MOV: "RegWrite=1 (cargará valor inmediato en registro)",
        BEQ: "ALUOp=CMP (comparará dos registros para decidir el salto)",
        BNE: "ALUOp=CMP (comparará dos registros para decidir el salto)",
      };
      const signals = signalExplanations[opUpper] || "señales configuradas para esta operación";
      return `La Unidad de Control interpreta el opcode '${opUpper}' y genera las señales de control: ${signals}. Esto decide qué componentes se activarán en las siguientes etapas.`;
    }
    case "EX": {
      if (event.component === "ALU" && inputs.length >= 2) {
        const opSign = op.toUpperCase() === "ADD" ? "+" : op.toUpperCase() === "SUB" ? "-" : "?";
        if (op.toUpperCase() === "ADD" || op.toUpperCase() === "SUB") {
          return `La ALU calcula: ${inputs[0]} ${opSign} ${inputs[1]} = ${output}. El resultado queda listo para la siguiente etapa.`;
        }
        if (op.toUpperCase() === "BEQ" || op.toUpperCase() === "BNE") {
          const result = output ? "son iguales → salto se toma" : "son diferentes → continúa secuencial";
          return `La ALU compara los valores ${inputs[0]} y ${inputs[1]}: ${result}.`;
        }
      }
      return `La ALU procesa la operación '${op}'. Entradas: [${inputs.join(", ")}], Resultado: ${output}.`;
    }
    case "MEM":
      if (event.action.includes("Read")) {
        const addr = event.meta?.address ?? inputs[0] ?? "?";
        return `Se lee el dato de la dirección de memoria ${addr}. Valor obtenido: ${output}. Este dato viajará al archivo de registros.`;
      }
      if (event.action.includes("Write")) {
        const addr = event.meta?.address ?? inputs[0] ?? "?";
        return `Se escribe el valor ${inputs[1] ?? output} en la dirección de memoria ${addr}. El dato queda almacenado en memoria principal.`;
      }
      return `La instrucción '${op}' no requiere acceso a memoria de datos. Esta etapa actúa como paso directo (pass-through).`;
    case "WB": {
      const reg = event.meta?.register ?? "destino";
      if (event.action.includes("No write-back")) {
        return `Esta instrucción '${op}' no necesita escribir resultado en registros. La etapa Write-Back no modifica ningún registro.`;
      }
      return `El resultado ${output} se escribe en el registro ${reg}. El archivo de registros queda actualizado y listo para futuras instrucciones.`;
    }
    default:
      return "Avanzando instrucción en el pipeline.";
  }
}

function pathLabelForRisc(stage: string, event: SimEvent): string {
  switch (stage) {
    case "IF": return "PC → Mem. Instrucciones → Pipeline";
    case "ID": return "Unidad de Control decodifica → Lee Registros";
    case "EX": return "Registros/Inmediato → ALU → Resultado";
    case "MEM": return "Resultado ALU → Memoria de Datos";
    case "WB": return "Resultado → Archivo de Registros";
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

function narrationForCiscMicroOp(micro: SimEvent, instruction: string, idx: number, total: number): string {
  const component = micro.component;
  const action = micro.action;
  const inputs = micro.inputs || [];
  const output = micro.output;

  const stepLabel = `[µ-Op ${idx}/${total}]`;

  if (component === "CONTROL") {
    if (action.includes("DECODE")) {
      return `${stepLabel} La Unidad de Control CISC decodifica la instrucción '${instruction}'. A diferencia de RISC, CISC descompone esta instrucción en ${total} micro-operaciones secuenciales.`;
    }
    if (action.includes("HALT")) {
      return `${stepLabel} Se ejecuta HALT — la CPU se detiene. No hay más instrucciones.`;
    }
    return `${stepLabel} La Unidad de Control coordina la ejecución de esta micro-operación.`;
  }

  if (component === "MEMORY") {
    const addrMatch = action.match(/MEM\[(\d+)\]/);
    const addr = addrMatch ? addrMatch[1] : "?";
    if (action.includes("READ")) {
      return `${stepLabel} Se carga la dirección ${addr} en el MAR. La memoria lee el valor ${output !== undefined ? output : "?"} y lo coloca en el MDR. Dato listo para el bus interno.`;
    }
    if (action.includes("WRITE")) {
      const val = inputs[1] ?? output ?? "?";
      return `${stepLabel} El MAR apunta a la dirección ${addr}. El MDR contiene el valor ${val}. La memoria escribe el dato desde el MDR a la dirección indicada.`;
    }
  }

  if (component === "ALU") {
    if (inputs.length >= 2) {
      return `${stepLabel} La ALU ejecuta la operación: ${inputs[0]} y ${inputs[1]} → resultado = ${output}. El resultado queda disponible en el bus interno para la siguiente µ-op.`;
    }
    return `${stepLabel} La ALU procesa: ${action}. Resultado: ${output}.`;
  }

  if (component === "REGISTERS") {
    if (action.includes("WRITE")) {
      const regMatch = action.match(/R(\d+)/);
      const reg = regMatch ? `R${regMatch[1]}` : "registro";
      return `${stepLabel} El resultado ${output} se escribe en el registro ${reg}. El bus interno transfiere el dato al archivo de registros.`;
    }
    if (action.includes("READ")) {
      const regMatch = action.match(/R(\d+)/);
      const reg = regMatch ? `R${regMatch[1]}` : "registro";
      return `${stepLabel} Se lee el valor ${output} del registro ${reg} y se coloca en el bus interno para la siguiente etapa.`;
    }
  }

  if (component === "PC") {
    if (action.includes("BRANCH TAKEN")) {
      return `${stepLabel} El resultado de la comparación fue IGUAL. El PC se actualiza a la dirección del salto: ${output}.`;
    }
    if (action.includes("BRANCH NOT TAKEN")) {
      return `${stepLabel} El resultado de la comparación fue DIFERENTE. El PC avanza secuencialmente a ${output}.`;
    }
    return `${stepLabel} El PC se actualiza a ${output}.`;
  }

  return `${stepLabel} Micro-operación ejecutándose: ${action}.`;
}

function pathLabelForCiscMicroOp(micro: SimEvent): string {
  const action = micro.action;
  const addrMatch = action.match(/MEM\[(\d+)\]/);

  if (micro.component === "MEMORY" && action.includes("READ")) {
    return `MAR ← ${addrMatch?.[1] ?? "?"} → Memoria → MDR ← ${micro.output ?? "?"}`;
  }
  if (micro.component === "MEMORY" && action.includes("WRITE")) {
    return `MAR ← ${addrMatch?.[1] ?? "?"}, MDR → Memoria[MAR]`;
  }
  if (micro.component === "ALU") {
    return `Operandos → ALU → Resultado en bus interno`;
  }
  if (micro.component === "REGISTERS" && action.includes("WRITE")) {
    return `Bus interno → Registro destino`;
  }
  if (micro.component === "REGISTERS" && action.includes("READ")) {
    return `Registro → Bus interno`;
  }
  if (micro.component === "CONTROL") {
    return `Unidad de Control decodifica → Micro-código ROM`;
  }
  if (micro.component === "PC") {
    return `Control → PC actualizado`;
  }
  return getInternalBusText(micro);
}

function toCiscSteps(timeline: TimelineCycle[], quizTracker: { count: number }): GuidedStep[] {
  const steps: GuidedStep[] = [];
  let localState: CPUStateMap = {};

  for (const cycle of timeline) {
    const micro = getCurrentMicroEvent(cycle.events);
    if (!micro) continue;
    const instruction = String(micro.meta?.instruction || "CISC instruction").toUpperCase();
    const focus = micro.action.includes("READ") || micro.action.includes("WRITE") ? "MEMORY" : micro.component;
    
    const idx = micro.meta?.micro_op_index ?? 0;
    const total = micro.meta?.total_micro_ops ?? 0;
    
    // Attempt rudimentary state update
    const beforeState = { ...localState };
    if (micro.component === "REGISTERS" && micro.action.includes("WRITE")) {
       const match = micro.action.match(/(R\d+).+?(\d+)/i);
       if (match) localState[match[1]] = match[2];
    }
    
    const isLastMicro = idx === total;
    const isFirstMicro = idx === 1;
    let ciscQuiz: Quiz | undefined;
    
    if (isFirstMicro && quizTracker.count < 2) {
      ciscQuiz = {
        question: "¿En qué divide CISC las instrucciones complejas?",
        options: ["Micro-operaciones", "Bucles de software", "Hardware directo"],
        answer: "Micro-operaciones",
        explanation: "CISC descompone cada instrucción compleja en una secuencia de micro-operaciones (µ-ops). Cada µ-op usa un solo ciclo de reloj."
      };
      quizTracker.count++;
    } else if (isLastMicro && quizTracker.count < 2) {
      ciscQuiz = {
        question: "¿Se escribirá en un registro al finalizar?",
        options: ["Sí", "No"],
        answer: micro.component === "REGISTERS" && micro.action.includes("WRITE") ? "Sí" : "No",
        explanation: "Si la operación era aritmética o de carga, termina escribiendo su valor en el archivo de registros."
      };
      quizTracker.count++;
    }

    steps.push({
      cycle: cycle.cycle,
      instruction,
      stage: `uOp ${idx}/${total}`,
      aluOp: micro.component === "ALU" ? instruction : "N/A",
      signals: {
        RegWrite: micro.component === "REGISTERS" && micro.action.includes("WRITE") ? 1 : 0,
        MemRead: micro.action.includes("READ") ? 1 : 0,
        MemWrite: micro.action.includes("WRITE") && micro.component === "MEMORY" ? 1 : 0,
        ALUSrc: micro.component === "ALU" ? 1 : 0,
      },
      narration: narrationForCiscMicroOp(micro, instruction, idx, total),
      focusComponent: focus,
      pathLabel: pathLabelForCiscMicroOp(micro),
      rawEvent: micro,
      quiz: ciscQuiz,
      decisionFlow: generateDecisionFlow({ RegWrite: micro.component === "REGISTERS", MemRead: micro.action.includes("READ"), MemWrite: micro.action.includes("WRITE") && micro.component === "MEMORY", ALUSrc: micro.component === "ALU" }),
      beforeState,
      afterState: { ...localState },
      operationLabel: micro.action,
      microSummary: isLastMicro ? {
        instruction,
        componentsUsed: ["Micro-code ROM", "ALU", "Registros"],
        memoryAccessed: instruction.includes("LOAD") || instruction.includes("STORE") || instruction.includes("ADD") || instruction.includes("SUB") || instruction.includes("MUL") ? "Yes" : "Maybe",
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
