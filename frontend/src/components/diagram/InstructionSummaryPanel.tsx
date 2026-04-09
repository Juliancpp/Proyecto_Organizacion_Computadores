import type { MicroSummary } from "@/lib/cpu-model/guidedExecution";

export function InstructionSummaryPanel({ summary }: { summary?: MicroSummary }) {
  if (!summary) return null;

  return (
    <div className="rounded border-2 border-neon-green/50 bg-neon-green/5 p-4 my-4 animate-in fade-in slide-in-from-bottom-2">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xl">✅</span>
        <h3 className="text-sm font-bold text-neon-green">Instruction Completed</h3>
      </div>
      
      <div className="grid grid-cols-2 gap-y-2 text-xs font-mono">
        <span className="text-muted-foreground">Instruction:</span>
        <span className="text-foreground font-bold">{summary.instruction}</span>
        
        <span className="text-muted-foreground">Components Used:</span>
        <span className="text-foreground">{summary.componentsUsed.join(", ")}</span>
        
        <span className="text-muted-foreground">Memory Accessed:</span>
        <span className={summary.memoryAccessed === "Yes" ? "text-neon-amber font-bold" : "text-foreground"}>
          {summary.memoryAccessed}
        </span>
        
        <span className="text-muted-foreground">Result Stored In:</span>
        <span className={summary.resultStoredIn !== "None" ? "text-neon-green font-bold" : "text-foreground"}>
          {summary.resultStoredIn}
        </span>
      </div>
    </div>
  );
}
