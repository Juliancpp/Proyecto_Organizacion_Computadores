import type { GuidedStep } from "@/lib/cpu-model";

export function StatePanel({ step }: { step?: GuidedStep }) {
  if (!step) {
    return (
      <div className="rounded border border-border bg-card p-3 h-full flex flex-col justify-center items-center">
        <div className="text-xs font-mono text-muted-foreground">Run simulation to see current state.</div>
      </div>
    );
  }

  return (
    <div className="rounded border border-border bg-card p-3 h-full flex flex-col justify-between">
      <div>
        <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2 shrink-0">Current State</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono">
          <span className="text-muted-foreground">Instruction</span>
          <span className="text-foreground">{step.instruction}</span>
          <span className="text-muted-foreground">Stage</span>
          <span className="text-foreground">{step.stage}</span>
          <span className="text-muted-foreground">ALU Operation</span>
          <span className="text-foreground">{step.aluOp}</span>
          <span className="text-muted-foreground">Cycle</span>
          <span className="text-foreground">{step.cycle}</span>
        </div>
      </div>
      <div className="mt-2 pt-2 border-t border-border grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono">
        <span className="text-muted-foreground">RegWrite</span>
        <span className={step.signals.RegWrite ? "text-neon-green" : "text-muted-foreground"}>{step.signals.RegWrite}</span>
        <span className="text-muted-foreground">MemRead</span>
        <span className={step.signals.MemRead ? "text-neon-green" : "text-muted-foreground"}>{step.signals.MemRead}</span>
        <span className="text-muted-foreground">MemWrite</span>
        <span className={step.signals.MemWrite ? "text-neon-green" : "text-muted-foreground"}>{step.signals.MemWrite}</span>
        <span className="text-muted-foreground">ALUSrc</span>
        <span className={step.signals.ALUSrc ? "text-neon-green" : "text-muted-foreground"}>{step.signals.ALUSrc}</span>
      </div>
    </div>
  );
}
