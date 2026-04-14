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
        strokeDasharray={isControl ? "8, 8" : "none"}
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
          initial={{ strokeDasharray: isControl ? "8, 12" : "15, 15", strokeDashoffset: 150 }}
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
           <rect x={(labelX || 0) - 45} y={(labelY || 0) - 13} width={90} height={22} fill="#111" rx={4} stroke={isControl ? "#4c1d95" : "#164e63"} strokeWidth={1} />
           <text
             x={labelX}
             y={(labelY || 0) + 4}
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
    <div className="rounded-xl border border-border bg-card p-2 sm:p-4 h-full relative overflow-hidden flex flex-col justify-start">
      <div className="text-sm font-mono text-muted-foreground uppercase mb-3 px-2 pt-2 font-bold flex justify-between items-center z-10 relative">
        <span className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
          Arquitectura Global ({activeArch.toUpperCase()})
        </span>
      </div>
      
      <div className="flex-1 w-full relative bg-black/30 rounded-lg p-1 sm:p-2 min-h-[600px] lg:min-h-[700px] flex items-center justify-center">
        {/* SVG Container designed cleanly for scaling */}
        <svg viewBox="0 0 1200 600" className="w-full h-full drop-shadow-2xl overflow-visible">
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

          {/* Paths Map (Orthogonal Strict Layout) */}

          {/* Instruction Lane (Top Row) */}
          <DataFlow 
            d="M 120 150 L 205 150" 
            isActive={isInstrMem} 
            label="Dir." labelX={165} labelY={130} 
          />
          <DataFlow 
            d="M 370 150 L 475 150" 
            isActive={isInstrMem || isReg || isControl} 
            label="Instrucción" labelX={425} labelY={130} 
          />
          
          {/* Instruction to Control unit branch */}
          <DataFlow 
            d="M 400 150 L 400 360 L 440 360" 
            isActive={isControl} 
          />
          <text x={400} y={250} fill={isControl ? "#a5f3fc" : "#666"} fontSize="13" fontFamily="monospace" textAnchor="middle" opacity={isControl ? 1 : 0.4} transform="rotate(-90 400 250)">
            Opcode
          </text>

          {/* Data Execution Lane (Middle) */}
          <DataFlow 
            d="M 620 130 L 755 130" 
            isActive={isALU} 
            label="Op 1" labelX={680} labelY={115} 
          />
          <DataFlow 
            d="M 620 170 L 755 170" 
            isActive={isALU} 
            label="Op 2" labelX={680} labelY={185} 
          />
          <DataFlow 
            d="M 880 170 L 975 170" 
            isActive={isALU || isMem} 
            label="Dir/Res" labelX={925} labelY={150} 
          />

          {/* Control Lane (Dashed Signals - Bottom & Vertical Snaps) */}
          {/* Control -> ALU */}
          <DataFlow 
            d="M 620 340 L 820 340 L 820 250" 
            isActive={isALU || isControl} 
            label="ALU Ctrl" labelX={730} labelY={320} 
            isControl={true}
          />
          {/* Control -> Memory */}
          <DataFlow 
            d="M 620 380 L 1050 380 L 1050 220" 
            isActive={isMem || isControl} 
            label="Mem Ctrl" labelX={860} labelY={360} 
            isControl={true}
          />
          {/* Control -> Registers (RegWrite) */}
          <DataFlow 
            d="M 550 320 L 550 210" 
            isActive={isReg || isControl} 
            label="RegWrite" labelX={550} labelY={260} 
            isControl={true}
          />

          {/* Writeback Loops (Top clearance) */}
          {/* DataMem -> Regs */}
          <DataFlow 
            d="M 1120 170 L 1150 170 L 1150 40 L 550 40 L 550 90" 
            isActive={step?.stage === "WB"} 
            label="Read Dato" labelX={860} labelY={25} 
          />
          {/* ALU -> Regs (Direct WB) */}
          <DataFlow 
            d="M 900 170 L 900 65 L 530 65 L 530 90" 
            isActive={step?.stage === "WB" && step?.signals?.MemRead === 0} 
            label="ALU WB" labelX={720} labelY={50} 
          />

          {/* Components Grid (Mapped perfectly to standard architecture layout) */}
          {/* LEFT ZONE */}
          <GraphNode id="PC" label="PC" x={40} y={120} width={80} height={60} isActive={isPC} />
          <GraphNode id="INSTR_MEM" label="Mem. de Inst" x={210} y={110} width={160} height={80} isActive={isInstrMem} />
          
          {/* CENTER ZONE */}
          <GraphNode id="REGISTERS" label="Registros" x={480} y={100} width={140} height={100} isActive={isReg} />
          <GraphNode id="CONTROL" label="Unidad Control" x={440} y={320} width={180} height={80} isActive={isControl} />
          
          {/* RIGHT ZONE */}
          <GraphNode id="ALU" label="ALU" x={760} y={100} width={120} height={140} isActive={isALU} />
          <GraphNode id="DATA_MEM" label="Mem. Datos" x={980} y={130} width={140} height={80} isActive={isMem} />

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
