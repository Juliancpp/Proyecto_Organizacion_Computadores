import type { GuidedStep } from "@/lib/cpu-model";

const SIGNAL_HELP: Record<string, string> = {
  RegWrite: "Permite escribir en un registro",
  MemRead: "Habilita lectura de memoria",
  MemWrite: "Habilita escritura en memoria",
  ALUSrc: "0 = registro, 1 = inmediato",
};

export function StatePanel({ step }: { step?: GuidedStep }) {
  if (!step) {
    return (
      <div className="rounded border border-border bg-card p-4 h-full flex flex-col justify-center items-center">
        <div className="text-sm font-mono text-muted-foreground">Ejecuta una simulación para ver el estado actual.</div>
      </div>
    );
  }

  return (
    <div className="rounded border border-border bg-card p-4 h-full flex flex-col justify-between">
      <div>
        <div className="text-xs font-mono text-muted-foreground uppercase mb-3 font-semibold">Estado Actual</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm font-mono">
          <span className="text-muted-foreground">Instrucción</span>
          <span className="text-foreground font-semibold">{step.instruction}</span>
          <span className="text-muted-foreground">Etapa</span>
          <span className="text-foreground font-semibold">{step.stage}</span>
          <span className="text-muted-foreground">Operación ALU</span>
          <span className="text-foreground">{step.aluOp}</span>
          <span className="text-muted-foreground">Ciclo</span>
          <span className="text-foreground">{step.cycle}</span>
        </div>
      </div>
      <div className="mt-3 pt-3 border-t border-border">
        <div className="text-xs font-mono text-muted-foreground/70 uppercase mb-2 font-semibold">Señales de control</div>
        <div className="space-y-1.5">
          {(["RegWrite", "MemRead", "MemWrite", "ALUSrc"] as const).map((sig) => (
            <div key={sig} className="flex items-center justify-between text-sm font-mono group">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${step.signals[sig] ? "bg-neon-green" : "bg-muted-foreground/30"}`} />
                <span className="text-foreground">{sig}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground/60 hidden group-hover:inline-block transition-opacity">
                  {SIGNAL_HELP[sig]}
                </span>
                <span className={`font-bold min-w-[1.5ch] text-right ${step.signals[sig] ? "text-neon-green" : "text-muted-foreground"}`}>
                  {step.signals[sig]}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
