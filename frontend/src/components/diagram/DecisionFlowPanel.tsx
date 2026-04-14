import type { DecisionFlow } from "@/lib/cpu-model/guidedExecution";

export function DecisionFlowPanel({ flow }: { flow: DecisionFlow[] }) {
  if (!flow || flow.length === 0) return null;

  return (
    <div className="rounded border border-border bg-card p-3 h-full flex flex-col justify-between">
      <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2 shrink-0">Control Unit Decision Tree</div>
      <div className="space-y-1 text-xs font-mono flex-grow">
        {flow.map((decision, i) => (
          <div key={i} className="flex justify-between items-center bg-black/20 p-1.5 rounded">
            <span className="text-muted-foreground">{decision.question}</span>
            <span className={`font-bold ${decision.answer === "YES" ? "text-neon-green" : "text-muted-foreground"}`}>
              {decision.answer}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
