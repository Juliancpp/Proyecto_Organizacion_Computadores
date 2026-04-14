import type { GuidedStep } from "@/lib/cpu-model";
import { motion, AnimatePresence } from "framer-motion";

interface NodeProps {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  isActive: boolean;
}

function GraphNode({ id, x, y, width, height, label, isActive }: NodeProps) {
  return (
    <motion.g
      initial={{ opacity: 0.8 }}
      animate={{ 
        opacity: isActive ? 1 : 0.3,
        scale: isActive ? 1.05 : 1
      }}
      transition={{ duration: 0.3 }}
    >
      {/* Glow Layer */}
      {isActive && (
        <rect
          x={x} y={y} width={width} height={height} rx={10}
          fill="none" stroke="rgba(6, 182, 212, 0.4)" strokeWidth={10}
        />
      )}
      
      {/* Main Block */}
      <rect
        x={x} y={y} width={width} height={height} rx={8}
        fill={isActive ? "rgba(6, 182, 212, 0.15)" : "rgba(10, 10, 15, 0.85)"}
        stroke={isActive ? "#22d3ee" : "#333"}
        strokeWidth={isActive ? 2 : 1.5}
      />
      
      {/* Text Label */}
      <text
        x={x + width / 2}
        y={y + height / 2 + 6}
        textAnchor="middle"
        fill={isActive ? "#cffafe" : "#888"}
        fontSize="16"
        fontFamily="monospace"
        fontWeight={isActive ? "700" : "500"}
        className="pointer-events-none select-none"
      >
        {label}
      </text>
    </motion.g>
  );
}

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
  const color = isControl ? "#a855f7" : "#06b6d4"; // Purple for control signals, Cyan for data

  return (
    <g>
      {/* Background Dim Line */}
      <path 
        d={d} 
        fill="none" 
        stroke={isActive ? color : "#2dd4bf"} 
        strokeOpacity={isActive ? 0.2 : 0.1}
        strokeWidth={isActive ? 6 : 3} 
        markerEnd={`url(#arrowhead${isActive ? '-active' : '-dim'})`} 
        strokeLinejoin="round"
      />
      
      {/* Animated Flow Line */}
      {isActive && (
        <motion.path
          d={d}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinejoin="round"
          initial={{ strokeDasharray: "15, 15", strokeDashoffset: 150 }}
          animate={{ strokeDashoffset: 0 }}
          transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
        />
      )}
      
      {/* Overlay Label */}
      {label && (
         <motion.g
           initial={{ opacity: 0.2, y: 5 }}
           animate={{ opacity: isActive ? 1 : 0.4, y: 0 }}
         >
           <rect x={(labelX || 0) - 50} y={(labelY || 0) - 15} width={100} height={20} fill="#111" rx={4} />
           <text
             x={labelX}
             y={labelY}
             fill={isActive ? (isControl ? "#d8b4fe" : "#a5f3fc") : "#666"}
             fontSize="13"
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

export function CPUView({
  step,
  activeArch,
}: {
  activeArch: "risc" | "cisc";
  step?: GuidedStep;
  stepList: GuidedStep[];
}) {
  
  const isPC = step?.stage === "IF" || step?.focusComponent === "PC";
  const isControl = step?.stage === "ID" || step?.focusComponent === "CONTROL";
  const isReg = step?.stage === "WB" || step?.focusComponent === "REGISTERS" || step?.signals?.RegWrite === 1;
  const isALU = step?.stage === "EX" || step?.focusComponent === "ALU" || step?.signals?.ALUSrc === 1 || step?.aluOp !== "PASS";
  const isMem = step?.stage === "MEM" || step?.focusComponent === "MEMORY" || step?.signals?.MemRead === 1 || step?.signals?.MemWrite === 1;
  const isInstrMem = step?.stage === "IF";

  return (
    <div className="rounded-xl border border-border bg-card p-4 h-full relative overflow-hidden flex flex-col justify-start">
      <div className="text-sm font-mono text-muted-foreground uppercase mb-6 font-bold flex justify-between items-center z-10 relative">
        <span className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
          Arquitectura Global ({activeArch.toUpperCase()})
        </span>
      </div>
      
      <div className="flex-1 w-full relative bg-black/30 rounded-lg p-2 min-h-[500px]">
        {/* SVG Container designed cleanly for scaling */}
        <svg viewBox="0 0 1100 500" className="w-full h-full drop-shadow-xl overflow-visible">
          <defs>
             {/* Dim Marker */}
            <marker id="arrowhead-dim" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#333" />
            </marker>
             {/* Active Blueprint/Cyan Marker */}
            <marker id="arrowhead-active" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#06b6d4" />
            </marker>
          </defs>

          {/* Paths Map */}
          {/* PC -> InstrMem */}
          <DataFlow 
            d="M 120 140 L 220 140" 
            isActive={isInstrMem} 
            label="Dirección" labelX={170} labelY={125} 
          />
          
          {/* InstrMem -> Regs */}
          <DataFlow 
            d="M 380 140 L 460 140" 
            isActive={isControl || isInstrMem} 
            label="Instrucción" labelX={420} labelY={125} 
          />
          
          {/* InstrMem -> Control */}
          <DataFlow 
            d="M 300 180 L 300 320" 
            isActive={isControl} 
          />
          <text x={300} y={250} fill={isControl ? "#a5f3fc" : "#666"} fontSize="12" fontFamily="monospace" textAnchor="middle" opacity={isControl ? 1 : 0.4} transform="rotate(-90 300 250)">
            Opcode
          </text>
          
          {/* Control -> ALU (Signals) */}
          <DataFlow 
            d="M 380 360 L 640 360 L 640 280 L 700 280" 
            isActive={isALU || isControl} 
            label="Señales Ctrl" labelX={510} labelY={350} 
            isControl={true}
          />

          {/* Control -> Memory (Signals) */}
          <DataFlow 
            d="M 380 380 L 920 380 L 920 230" 
            isActive={isMem || isControl} 
            label="Read/Write" labelX={650} labelY={395} 
            isControl={true}
          />
          
          {/* Regs -> ALU (Top Bus/Op1) */}
          <DataFlow 
            d="M 620 120 L 660 120 L 660 200 L 700 200" 
            isActive={isALU} 
            label="Op 1" labelX={650} labelY={110} 
          />
          {/* Regs -> ALU (Bottom Bus/Op2) */}
          <DataFlow 
            d="M 620 160 L 680 160 L 680 240 L 700 240" 
            isActive={isALU} 
            label="Op 2" labelX={680} labelY={150} 
          />
          
          {/* ALU -> DataMem */}
          <DataFlow 
            d="M 820 220 L 860 220" 
            isActive={isMem || isALU} 
            label="Resul/Dir" labelX={840} labelY={205} 
          />
          
          {/* Feedback Loops (Writeback) */}
          {/* DataMem -> Regs */}
          <DataFlow 
            d="M 920 150 L 920 80 L 540 80 L 540 90" 
            isActive={step?.stage === "WB"} 
            label="Dato WB" labelX={730} labelY={70} 
          />
          {/* ALU -> Regs (Direct Writeback) */}
          <DataFlow 
            d="M 820 240 L 840 240 L 840 60 L 560 60 L 560 90" 
            isActive={step?.stage === "WB" && step?.signals?.MemRead === 0} 
            label="ALU WB" labelX={700} labelY={50} 
          />

          {/* 
            Geometry Map:
            PC: x=40, y=100
            InstrMem: x=240, y=100
            Control: x=240, y=320
            Regs: x=480, y=100
            ALU: x=720, y=160
            DataMem: x=880, y=150
          */}
          <GraphNode id="PC" label="PC" x={20} y={110} width={100} height={60} isActive={isPC} />
          
          <GraphNode id="INSTR_MEM" label="Mem. de Inst" x={220} y={100} width={160} height={80} isActive={isInstrMem} />
          
          <GraphNode id="CONTROL" label="Unidad Control" x={220} y={320} width={160} height={80} isActive={isControl} />
          
          <GraphNode id="REGISTERS" label="Registros" x={460} y={100} width={160} height={100} isActive={isReg} />
          
          <GraphNode id="ALU" label="ALU" x={700} y={170} width={120} height={140} isActive={isALU} />
          
          <GraphNode id="DATA_MEM" label="Mem. Datos" x={860} y={150} width={140} height={80} isActive={isMem} />

        </svg>
      </div>

      {/* Floating State Banner */}
      <AnimatePresence>
        {step?.pathLabel && (
          <motion.div 
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 15 }}
            className="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-full border border-primary/50 bg-background/95 px-6 py-3 font-mono text-[13px] text-primary shadow-[0_0_20px_rgba(6,182,212,0.15)] backdrop-blur-md z-20"
          >
            {step.pathLabel}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
