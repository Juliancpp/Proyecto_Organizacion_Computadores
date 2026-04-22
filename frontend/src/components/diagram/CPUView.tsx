import type { GuidedStep } from "@/lib/cpu-model";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";

/* ------------------------------------------------------------------ */
/*  Component description map                                          */
/* ------------------------------------------------------------------ */

const COMPONENT_DESCRIPTIONS: Record<string, string> = {
  PC: "Dirección de la próxima instrucción",
  INSTR_MEM: "Almacena las instrucciones del programa",
  REGISTERS: "Almacenan valores temporales rápidos",
  CONTROL: "Interpreta instrucciones y activa señales",
  ALU: "Realiza operaciones aritméticas y lógicas",
  DATA_MEM: "Almacena datos en direcciones específicas",
  MAR: "Memory Address Register — dirección activa",
  MDR: "Memory Data Register — dato en tránsito",
};

const COMPONENT_TOOLTIPS: Record<string, string> = {
  PC: "El Program Counter (PC) indica qué instrucción se ejecutará. Se incrementa o modifica en saltos.",
  INSTR_MEM: "La memoria de instrucciones contiene el programa que la CPU ejecuta secuencialmente.",
  REGISTERS: "El archivo de registros (R0–R7) almacena operandos y resultados de acceso rápido.",
  CONTROL: "La Unidad de Control decodifica el opcode y genera señales que configuran el datapath.",
  ALU: "La Unidad Aritmético-Lógica ejecuta sumas, restas y comparaciones.",
  DATA_MEM: "La memoria de datos almacena variables del programa. Se accede con LOAD y STORE.",
  MAR: "MAR recibe la dirección de memoria que se va a leer o escribir en el ciclo actual.",
  MDR: "MDR contiene el dato leído de memoria o el dato que se va a escribir.",
};

/* ------------------------------------------------------------------ */
/*  Tooltip helper — word-aware line splitting for SVG text            */
/* ------------------------------------------------------------------ */

function splitTooltipLines(text: string, maxCharsPerLine: number): string[] {
  const words = text.split(" ");
  const lines: string[] = [];
  let current = "";
  for (const w of words) {
    if (current.length + w.length + 1 > maxCharsPerLine && current.length > 0) {
      lines.push(current);
      current = w;
    } else {
      current = current ? current + " " + w : w;
    }
  }
  if (current) lines.push(current);
  return lines;
}

/* ------------------------------------------------------------------ */
/*  Graph Node                                                         */
/* ------------------------------------------------------------------ */

interface NodeProps {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  isActive: boolean;
  compact?: boolean;
}

function GraphNode({ id, x, y, width, height, label, isActive, compact }: NodeProps) {
  const [hovered, setHovered] = useState(false);
  const tooltip = COMPONENT_TOOLTIPS[id];
  const tooltipLines = tooltip ? splitTooltipLines(tooltip, 40) : [];

  const tooltipHeight = 24 + tooltipLines.length * 20;
  const tooltipWidth = 320;
  // Position tooltip above the component
  const tooltipY = y - tooltipHeight - 16;

  return (
    <motion.g
      initial={{ opacity: 0.8, scale: 1 }}
      animate={{ 
        opacity: isActive ? 1 : (hovered ? 1 : 0.3),
        scale: hovered ? 1.4 : (isActive ? 1.05 : 1)
      }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ cursor: "pointer", transformOrigin: `${x + width / 2}px ${y + height / 2}px` }}
    >
      {/* Glow Layer (stronger on hover) */}
      {(isActive || hovered) && (
        <rect
          x={x} y={y} width={width} height={height} rx={10}
          fill="none" 
          stroke={hovered ? "rgba(6, 182, 212, 0.6)" : "rgba(6, 182, 212, 0.4)"} 
          strokeWidth={hovered ? 14 : 10}
        />
      )}
      
      {/* Main Block */}
      <rect
        x={x} y={y} width={width} height={height} rx={8}
        fill={isActive || hovered ? "rgba(6, 182, 212, 0.25)" : "rgba(10, 10, 15, 0.85)"}
        stroke={isActive || hovered ? "#67e8f9" : "#333"}
        strokeWidth={isActive || hovered ? 3 : 1.5}
      />
      
      {/* Text Label (Only name, no descriptions inside) */}
      <text
        x={x + width / 2}
        y={y + height / 2 + 6}
        textAnchor="middle"
        fill={isActive || hovered ? "#ffffff" : "#aaa"}
        fontSize={compact ? "14" : "18"}
        fontFamily="monospace"
        fontWeight={isActive || hovered ? "700" : "500"}
        className="pointer-events-none select-none"
      >
        {label}
      </text>

      {/* Enhanced Tooltip on hover */}
      {hovered && tooltipLines.length > 0 && (
        <motion.g
          initial={{ opacity: 0, y: 10, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
        >
          {/* Tooltip Background */}
          <rect
            x={x + width / 2 - tooltipWidth / 2}
            y={tooltipY}
            width={tooltipWidth}
            height={tooltipHeight}
            rx={12}
            fill="#0f172a"
            stroke="#22d3ee"
            strokeWidth={2}
            filter="drop-shadow(0 8px 16px rgba(0, 0, 0, 0.8))"
          />
          {/* Tooltip Text Lines */}
          {tooltipLines.map((line, i) => (
            <text
              key={i}
              x={x + width / 2}
              y={tooltipY + 24 + i * 20}
              textAnchor="middle"
              fill="#f8fafc"
              fontSize="15"
              fontWeight="500"
              fontFamily="Inter, sans-serif"
              className="pointer-events-none select-none"
            >
              {line}
            </text>
          ))}
        </motion.g>
      )}
    </motion.g>
  );
}

/* ------------------------------------------------------------------ */
/*  Data Flow Arrow                                                    */
/* ------------------------------------------------------------------ */

function DataFlow({ 
  d, 
  isActive, 
  label, 
  labelX, 
  labelY,
  isControl = false 
}: { 
  d: string, 
  isActive: boolean, 
  label?: string, 
  labelX?: number, 
  labelY?: number,
  isControl?: boolean
}) {
  const color = isControl ? "#a855f7" : "#06b6d4";

  return (
    <g>
      <path 
        d={d} 
        fill="none" 
        stroke={isActive ? color : "#2dd4bf"} 
        strokeOpacity={isActive ? 0.2 : 0.1}
        strokeWidth={isActive ? 6 : 3} 
        strokeDasharray={isControl ? "8, 8" : "none"}
        markerEnd={`url(#arrowhead${isActive ? '-active' : '-dim'})`} 
        strokeLinejoin="round"
      />
      
      {isActive && (
        <motion.path
          d={d}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinejoin="round"
          initial={{ strokeDasharray: isControl ? "8, 12" : "15, 15", strokeDashoffset: 150 }}
          animate={{ strokeDashoffset: 0 }}
          transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
        />
      )}
      
      {label && (
         <motion.g
           initial={{ opacity: 0.2, y: 5 }}
           animate={{ opacity: isActive ? 1 : 0.4, y: 0 }}
         >
           <rect x={(labelX || 0) - 50} y={(labelY || 0) - 13} width={100} height={24} fill="#111" rx={4} stroke={isControl ? "#4c1d95" : "#164e63"} strokeWidth={1} />
           <text
             x={labelX}
             y={(labelY || 0) + 5}
             fill={isActive ? (isControl ? "#d8b4fe" : "#a5f3fc") : "#666"}
             fontSize="12"
             fontFamily="monospace"
             fontWeight="600"
             textAnchor="middle"
           >
             {label}
           </text>
         </motion.g>
      )}
    </g>
  );
}

/* ------------------------------------------------------------------ */
/*  ALU Operation Label                                                */
/* ------------------------------------------------------------------ */

function AluOperationLabel({ step, x, y }: { step?: GuidedStep; x: number; y: number }) {
  if (!step || (step.stage !== "EX" && step.focusComponent !== "ALU")) return null;
  
  const aluOp = step.aluOp;
  const opLabels: Record<string, string> = {
    ADD: "Sumando valores",
    SUB: "Restando valores",
    CMP: "Comparando valores",
    ADDR: "Calculando dirección",
    PASS: "Pasando valor",
    NOP: "",
  };
  
  const label = opLabels[aluOp] || aluOp;
  if (!label) return null;

  return (
    <motion.g
      initial={{ opacity: 0, y: 5 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <rect x={x} y={y} width={140} height={24} rx={5} fill="rgba(6, 182, 212, 0.12)" stroke="rgba(6, 182, 212, 0.4)" strokeWidth={1} />
      <text x={x + 70} y={y + 16} textAnchor="middle" fill="#67e8f9" fontSize="12" fontFamily="Inter, sans-serif" fontWeight="600">
        {label}
      </text>
    </motion.g>
  );
}

/* ------------------------------------------------------------------ */
/*  µ-Op Progress Bar (CISC sequential mode)                           */
/* ------------------------------------------------------------------ */

function MicroOpProgress({ step, x, y, width }: { step?: GuidedStep; x: number; y: number; width: number }) {
  if (!step) return null;
  
  const stageStr = step.stage;
  const match = stageStr.match(/uOp (\d+)\/(\d+)/);
  if (!match) return null;
  
  const current = parseInt(match[1]);
  const total = parseInt(match[2]);
  const pct = (current / total) * 100;

  return (
    <g>
      {/* Background bar */}
      <rect x={x} y={y} width={width} height={8} rx={4} fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.1)" strokeWidth={0.5} />
      {/* Fill */}
      <motion.rect
        x={x} y={y} height={8} rx={4}
        fill="#06b6d4"
        initial={{ width: 0 }}
        animate={{ width: (pct / 100) * width }}
        transition={{ duration: 0.4 }}
      />
      {/* Label */}
      <text x={x + width / 2} y={y + 24} textAnchor="middle" fill="#a5f3fc" fontSize="13" fontFamily="monospace" fontWeight="600">
        µ-Op {current} / {total}
      </text>
    </g>
  );
}

/* ------------------------------------------------------------------ */
/*  SVG Definitions (shared markers)                                   */
/* ------------------------------------------------------------------ */

function SvgDefs() {
  return (
    <defs>
      <marker id="arrowhead-dim" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#333" />
      </marker>
      <marker id="arrowhead-active" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#06b6d4" />
      </marker>
    </defs>
  );
}

/* ------------------------------------------------------------------ */
/*  Pipeline Diagram (RISC or CISC+Pipeline)                           */
/* ------------------------------------------------------------------ */

function PipelineDiagram({ step }: { step?: GuidedStep }) {
  const isPC = step?.stage === "IF" || step?.focusComponent === "PC";
  const isControl = step?.stage === "ID" || step?.focusComponent === "CONTROL";
  const isReg = step?.stage === "WB" || step?.focusComponent === "REGISTERS" || step?.signals?.RegWrite === 1;
  const isALU = step?.stage === "EX" || step?.focusComponent === "ALU" || step?.signals?.ALUSrc === 1 || step?.aluOp !== "PASS";
  const isMem = step?.stage === "MEM" || step?.focusComponent === "MEMORY" || step?.signals?.MemRead === 1 || step?.signals?.MemWrite === 1;
  const isInstrMem = step?.stage === "IF";

  return (
    <svg viewBox="0 0 1200 600" className="w-full h-full drop-shadow-2xl overflow-visible">
      <SvgDefs />

      {/* Instruction Lane */}
      <DataFlow d="M 120 150 L 205 150" isActive={isInstrMem} label="Dir." labelX={165} labelY={130} />
      <DataFlow d="M 370 150 L 475 150" isActive={isInstrMem || isReg || isControl} label="Instrucción" labelX={425} labelY={130} />
      
      {/* Instruction → Control */}
      <DataFlow d="M 400 150 L 400 360 L 440 360" isActive={isControl} />
      <text x={400} y={250} fill={isControl ? "#a5f3fc" : "#666"} fontSize="12" fontFamily="monospace" textAnchor="middle" opacity={isControl ? 1 : 0.4} transform="rotate(-90 400 250)">
        Opcode
      </text>

      {/* Data Execution Lane */}
      <DataFlow d="M 620 130 L 755 130" isActive={isALU} label="Op 1" labelX={680} labelY={115} />
      <DataFlow d="M 620 170 L 755 170" isActive={isALU} label="Op 2" labelX={680} labelY={185} />
      <DataFlow d="M 880 170 L 975 170" isActive={isALU || isMem} label="Dir/Res" labelX={925} labelY={150} />

      {/* Control Signals */}
      <DataFlow d="M 620 340 L 820 340 L 820 250" isActive={isALU || isControl} label="ALU Ctrl" labelX={730} labelY={320} isControl={true} />
      <DataFlow d="M 620 380 L 1050 380 L 1050 220" isActive={isMem || isControl} label="Mem Ctrl" labelX={860} labelY={360} isControl={true} />
      <DataFlow d="M 550 320 L 550 210" isActive={isReg || isControl} label="RegWrite" labelX={550} labelY={260} isControl={true} />

      {/* Writeback Loops */}
      <DataFlow d="M 1120 170 L 1150 170 L 1150 40 L 550 40 L 550 90" isActive={step?.stage === "WB"} label="Read Dato" labelX={860} labelY={25} />
      <DataFlow d="M 900 170 L 900 65 L 530 65 L 530 90" isActive={step?.stage === "WB" && step?.signals?.MemRead === 0} label="ALU WB" labelX={720} labelY={50} />

      {/* Components */}
      <GraphNode id="PC" label="PC" x={40} y={120} width={80} height={60} isActive={isPC} />
      <GraphNode id="INSTR_MEM" label="Mem. de Inst" x={210} y={110} width={160} height={80} isActive={isInstrMem} />
      <GraphNode id="REGISTERS" label="Registros" x={480} y={100} width={140} height={100} isActive={isReg} />
      <GraphNode id="CONTROL" label="Unidad Control" x={440} y={320} width={180} height={80} isActive={isControl} />
      <GraphNode id="ALU" label="ALU" x={760} y={100} width={120} height={140} isActive={isALU} />
      <GraphNode id="DATA_MEM" label="Mem. Datos" x={980} y={130} width={140} height={80} isActive={isMem} />

      <AluOperationLabel step={step} x={750} y={250} />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Sequential CISC Diagram (micro-op mode — one at a time)            */
/* ------------------------------------------------------------------ */

function SequentialCiscDiagram({ step }: { step?: GuidedStep }) {
  // In CISC sequential mode, only ONE component is active at a time
  const focus = step?.focusComponent || "";
  
  const isControl = focus === "CONTROL";
  const isALU = focus === "ALU";
  const isMem = focus === "MEMORY" || step?.rawEvent?.action?.includes("READ") || step?.rawEvent?.action?.includes("WRITE");
  const isReg = focus === "REGISTERS";
  const isPC = focus === "PC";

  // MAR/MDR values from the current event
  const rawAction = step?.rawEvent?.action ?? "";
  const marMatch = rawAction.match(/MEM\[(\d+)\]/);
  const marValue = marMatch ? marMatch[1] : "—";
  const mdrValue = step?.rawEvent?.output !== undefined ? String(step.rawEvent.output) : "—";

  // Determine active data path for sequential mode
  const memToAlu = isMem && rawAction.includes("READ");
  const aluToMem = isMem && rawAction.includes("WRITE");
  const controlToAll = isControl;

  return (
    <svg viewBox="0 0 1200 620" className="w-full h-full drop-shadow-2xl overflow-visible">
      <SvgDefs />

      {/* ── Sequential flow indicator (top bar) ── */}
      <rect x={40} y={15} width={1120} height={32} rx={6} fill="rgba(6,182,212,0.05)" stroke="rgba(6,182,212,0.15)" strokeWidth={1} />
      <text x={600} y={36} textAnchor="middle" fill="#67e8f9" fontSize="13" fontFamily="Inter, sans-serif" fontWeight="600">
        Ejecución Secuencial — Solo un componente activo por ciclo (micro-operación)
      </text>

      {/* ── µ-Op Progress Bar ── */}
      <MicroOpProgress step={step} x={350} y={55} width={500} />

      {/* ── Components (same layout but only ONE active) ── */}

      {/* PC → Instr Mem path */}
      <DataFlow d="M 120 180 L 205 180" isActive={isPC} label="Dir." labelX={165} labelY={160} />
      
      {/* Instr Mem → Control path */}
      <DataFlow d="M 370 180 L 440 180 L 440 340 L 440 360" isActive={isControl} label="Instrucción" labelX={410} labelY={260} />

      {/* Control → all (broadcast signals) */}
      <DataFlow d="M 620 360 L 820 360 L 820 280" isActive={controlToAll} label="Ctrl" labelX={730} labelY={340} isControl={true} />

      {/* Registers ↔ ALU */}
      <DataFlow d="M 620 180 L 755 180" isActive={isReg || isALU} label="Dato" labelX={685} labelY={160} />

      {/* ALU → MAR/MDR → Memory */}
      <DataFlow d="M 880 200 L 920 200 L 920 420 L 480 420" isActive={memToAlu || aluToMem} label="Bus Datos" labelX={700} labelY={400} />

      {/* Memory → Registers (writeback) */}
      <DataFlow d="M 1120 180 L 1150 180 L 1150 70 L 550 70 L 550 130" isActive={isReg && isMem} label="WB" labelX={860} labelY={55} />

      {/* ── Component Nodes ── */}
      <GraphNode id="PC" label="PC" x={40} y={150} width={80} height={60} isActive={isPC} />
      <GraphNode id="INSTR_MEM" label="Mem. de Inst" x={210} y={140} width={160} height={80} isActive={false} />
      <GraphNode id="REGISTERS" label="Registros" x={480} y={130} width={140} height={100} isActive={isReg} />
      <GraphNode id="CONTROL" label="Unidad Control" x={440} y={320} width={180} height={80} isActive={isControl} />
      <GraphNode id="ALU" label="ALU" x={760} y={130} width={120} height={140} isActive={isALU} />
      <GraphNode id="DATA_MEM" label="Mem. Datos" x={980} y={150} width={140} height={80} isActive={isMem} />

      {/* ── MAR / MDR Registers (CISC-specific) ── */}
      <GraphNode id="MAR" label="MAR" x={370} y={450} width={100} height={50} isActive={isMem} compact />
      <GraphNode id="MDR" label="MDR" x={520} y={450} width={100} height={50} isActive={isMem || isALU} compact />

      {/* MAR value */}
      <text x={420} y={520} textAnchor="middle" fill={isMem ? "#fbbf24" : "#555"} fontSize="14" fontFamily="monospace" fontWeight="700">
        {marValue}
      </text>
      {/* MDR value */}
      <text x={570} y={520} textAnchor="middle" fill={isMem || isALU ? "#67e8f9" : "#555"} fontSize="14" fontFamily="monospace" fontWeight="700">
        {mdrValue}
      </text>

      {/* MAR → Memory connection */}
      <DataFlow d="M 470 465 L 620 465 L 980 465 L 980 230" isActive={isMem} label="Dirección" labelX={780} labelY={450} />
      {/* MDR ↔ Data bus */}
      <DataFlow d="M 570 450 L 570 420" isActive={isMem || isALU} />

      {/* ALU operation label */}
      <AluOperationLabel step={step} x={750} y={280} />

      {/* ── Current action highlight ── */}
      {step && (
        <motion.g
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
        >
          <rect x={40} y={560} width={1120} height={40} rx={8} fill="rgba(6,182,212,0.08)" stroke="rgba(6,182,212,0.25)" strokeWidth={1} />
          <text x={600} y={585} textAnchor="middle" fill="#a5f3fc" fontSize="13" fontFamily="Inter, sans-serif" fontWeight="500">
            {step.rawEvent?.action || "Esperando..."}
          </text>
        </motion.g>
      )}
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Main CPUView Component                                             */
/* ------------------------------------------------------------------ */

export function CPUView({
  step,
  activeArch,
  pipelineEnabled = true,
}: {
  activeArch: "risc" | "cisc";
  step?: GuidedStep;
  stepList: GuidedStep[];
  pipelineEnabled?: boolean;
}) {
  const isCiscSequential = activeArch === "cisc" && !pipelineEnabled;

  const titleLabel = isCiscSequential 
    ? "Arquitectura CISC — Ejecución Secuencial (Micro-ops)"
    : `Arquitectura Global (${activeArch.toUpperCase()})`;

  return (
    <div className="rounded-xl border border-border bg-card p-2 sm:p-4 h-full relative overflow-hidden flex flex-col justify-start">
      <div className="text-sm font-mono text-muted-foreground uppercase mb-3 px-2 pt-2 font-bold flex justify-between items-center z-10 relative">
        <span className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isCiscSequential ? "bg-neon-amber" : "bg-primary"} animate-pulse`} />
          {titleLabel}
        </span>
        <span className="text-[11px] text-muted-foreground/60 font-normal normal-case">
          Pasa el cursor sobre un componente para más info
        </span>
      </div>
      
      <div className={`flex-1 w-full relative bg-black/30 rounded-lg p-1 sm:p-2 flex items-center justify-center ${isCiscSequential ? "min-h-[650px] lg:min-h-[750px]" : "min-h-[600px] lg:min-h-[700px]"}`}>
        {isCiscSequential ? (
          <SequentialCiscDiagram step={step} />
        ) : (
          <PipelineDiagram step={step} />
        )}
      </div>

      {/* Floating State Banner */}
      <AnimatePresence>
        {step?.pathLabel && (
          <motion.div 
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 15 }}
            className="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-full border border-primary/50 bg-background/95 px-6 py-3 font-mono text-sm text-primary shadow-[0_0_20px_rgba(6,182,212,0.15)] backdrop-blur-md z-20"
          >
            {step.pathLabel}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
