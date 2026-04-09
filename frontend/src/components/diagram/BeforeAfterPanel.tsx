import type { CPUStateMap } from "@/lib/cpu-model/guidedExecution";

interface BeforeAfterPanelProps {
  beforeState: CPUStateMap;
  afterState: CPUStateMap;
  operationLabel?: string;
}

export function BeforeAfterPanel({ beforeState, afterState, operationLabel }: BeforeAfterPanelProps) {
  // Find which keys changed to highlight them specially
  const allKeys = Array.from(new Set([...Object.keys(beforeState), ...Object.keys(afterState)]));
  if (allKeys.length === 0) return null;

  return (
    <div className="rounded border border-border bg-card p-3 my-2">
      <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">State Transition (Cause → Effect)</div>
      <div className="grid grid-cols-[1fr_auto_1fr] gap-4 items-center font-mono text-xs">
        {/* BEFORE */}
        <div className="bg-black/20 p-2 rounded min-h-[60px]">
          <div className="text-[9px] text-muted-foreground mb-1">BEFORE</div>
          {allKeys.map(k => (
            <div key={k} className="text-foreground/80">{k} = {beforeState[k] ?? "?"}</div>
          ))}
        </div>

        {/* OPERATION TRANSITION */}
        <div className="flex flex-col items-center justify-center text-primary/80">
          <span className="text-[10px] bg-primary/10 px-2 py-1 rounded-full mb-1 border border-primary/20">
            {operationLabel || "Updating"}
          </span>
          <span>→</span>
        </div>

        {/* AFTER */}
        <div className="bg-black/20 p-2 rounded min-h-[60px]">
          <div className="text-[9px] text-muted-foreground mb-1">AFTER</div>
          {allKeys.map(k => {
            const changed = beforeState[k] !== afterState[k];
            return (
              <div key={k} className={changed ? "text-neon-amber font-bold" : "text-foreground/80"}>
                {k} = {afterState[k] ?? "?"}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
