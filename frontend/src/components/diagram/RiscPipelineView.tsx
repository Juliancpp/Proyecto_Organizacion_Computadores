import { motion } from "framer-motion";
import type { SimEvent } from "@/types/simulation";
import {
  getRiscOpcodeFromEvents,
  getRiscControlSignals,
  getRiscRegReads,
  getRiscRegWrites,
  getRiscAluEvent,
} from "@/lib/cpu-model";

const RISC_STAGES = ["IF", "ID", "EX", "MEM", "WB"] as const;
type RiscStage = (typeof RISC_STAGES)[number];

function StageCard({ stage, events }: { stage: RiscStage; events: SimEvent[] }) {
  const stageEvents = events.filter((e) => e.meta?.pipeline_stage === stage);
  const text = stageEvents[0]?.action || "idle";
  const active = stageEvents.length > 0;
  return (
    <motion.div
      layout
      className={`rounded border p-2 min-h-20 ${active ? "border-primary bg-primary/10" : "border-border bg-card"}`}
    >
      <div className="text-[10px] font-mono text-muted-foreground">{stage}</div>
      <div className="text-xs font-mono mt-1 text-foreground">{text}</div>
    </motion.div>
  );
}

function PipeReg({ name }: { name: string }) {
  return (
    <div className="rounded border border-neon-amber/40 bg-neon-amber/10 px-2 py-1 text-[10px] font-mono text-neon-amber text-center">
      {name}
    </div>
  );
}

export function RiscPipelineView({ currentEvents }: { currentEvents: SimEvent[] }) {
  const opcode = getRiscOpcodeFromEvents(currentEvents);
  const signals = getRiscControlSignals(opcode);
  const regReads = getRiscRegReads(currentEvents);
  const regWrites = getRiscRegWrites(currentEvents);
  const aluEvent = getRiscAluEvent(currentEvents);

  return (
    <div className="p-3 space-y-3">
      <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr_auto_1fr] gap-2 items-start">
        <StageCard stage="IF" events={currentEvents} />
        <PipeReg name="IF/ID" />
        <StageCard stage="ID" events={currentEvents} />
        <PipeReg name="ID/EX" />
        <StageCard stage="EX" events={currentEvents} />
        <PipeReg name="EX/MEM" />
        <StageCard stage="MEM" events={currentEvents} />
        <PipeReg name="MEM/WB" />
        <StageCard stage="WB" events={currentEvents} />
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded border border-border bg-card p-2">
          <div className="text-[10px] font-mono text-muted-foreground mb-1">Control Unit Signals ({opcode})</div>
          {Object.entries(signals).map(([k, v]) => (
            <div key={k} className="text-xs font-mono flex justify-between">
              <span>{k}</span>
              <span className={String(v) === "1" ? "text-neon-green" : "text-muted-foreground"}>{String(v)}</span>
            </div>
          ))}
        </div>

        <div className="rounded border border-border bg-card p-2">
          <div className="text-[10px] font-mono text-muted-foreground mb-1">Register File (2R / 1W)</div>
          <div className="text-xs font-mono text-neon-cyan">Read ports: {regReads.map((e) => e.action).join(" | ") || "idle"}</div>
          <div className="text-xs font-mono text-neon-violet mt-1">Write port: {regWrites.map((e) => e.action).join(" | ") || "idle"}</div>
        </div>

        <div className="rounded border border-border bg-card p-2">
          <div className="text-[10px] font-mono text-muted-foreground mb-1">ALU + ALUSrc MUX</div>
          <div className="text-xs font-mono text-foreground">Operation: {signals.ALUOp}</div>
          <div className="text-xs font-mono text-foreground">ALUSrc: {signals.ALUSrc ? "Immediate" : "Register"}</div>
          <div className="text-xs font-mono text-muted-foreground mt-1">{aluEvent?.action || "No ALU activity this cycle"}</div>
        </div>
      </div>
    </div>
  );
}
