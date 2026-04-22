import type { DecisionFlow } from "@/lib/cpu-model/guidedExecution";

export function DecisionFlowPanel({ flow }: { flow: DecisionFlow[] }) {
  if (!flow || flow.length === 0) return null;

  return (
    <div className="rounded border border-border bg-card p-4 h-full flex flex-col justify-between">
      <div className="text-xs font-mono text-muted-foreground uppercase mb-2 shrink-0 font-semibold">
        Árbol de Decisión — Unidad de Control
      </div>
      <p className="text-xs text-muted-foreground/80 mb-3 leading-relaxed">
        La Unidad de Control evalúa cada señal para decidir qué componentes activar.
      </p>
      <div className="space-y-1.5 text-sm font-mono flex-grow">
        {flow.map((decision, i) => (
          <div key={i} className="flex justify-between items-center bg-black/20 p-2.5 rounded">
            <span className="text-foreground/80">{decision.question}</span>
            <span className={`font-bold text-base ${decision.answer === "SÍ" ? "text-neon-green" : "text-muted-foreground"}`}>
              {decision.answer}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
