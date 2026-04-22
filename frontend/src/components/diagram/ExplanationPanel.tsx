import type { GuidedStep } from "@/lib/cpu-model";
import { GraduationCap } from "lucide-react";

const SIGNAL_DESCRIPTIONS: Record<string, string> = {
  RegWrite: "Escritura en registro",
  MemRead: "Lectura de memoria",
  MemWrite: "Escritura en memoria",
  ALUSrc: "Fuente ALU (inmediato)",
};

export function ExplanationPanel({ step }: { step?: GuidedStep }) {
  const activeSignals = step?.signals
    ? Object.entries(step.signals).filter(([, v]) => v === 1)
    : [];

  return (
    <div className="rounded border-2 border-primary/40 bg-primary/10 p-5 relative overflow-hidden shadow-lg">
      <div className="absolute top-0 right-0 p-4 opacity-10">
        <GraduationCap className="w-16 h-16" />
      </div>
      <div className="flex items-center gap-2 mb-3">
        <GraduationCap className="w-6 h-6 text-primary" />
        <div className="text-sm font-bold text-primary uppercase tracking-wider">Explicación del Profesor</div>
      </div>
      <p className="text-base font-medium text-foreground leading-7 mt-2">
        {step?.narration || "Haz clic en 'Siguiente Paso' para comenzar la ejecución guiada paso a paso."}
      </p>

      {/* Active signals as pills */}
      {activeSignals.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {activeSignals.map(([key]) => (
            <span
              key={key}
              className="inline-flex items-center gap-1.5 text-xs font-mono bg-neon-green/10 text-neon-green border border-neon-green/30 rounded-full px-3 py-1"
              title={SIGNAL_DESCRIPTIONS[key] || key}
            >
              <span className="w-2 h-2 rounded-full bg-neon-green animate-pulse" />
              {key}
              <span className="text-neon-green/70">— {SIGNAL_DESCRIPTIONS[key]}</span>
            </span>
          ))}
        </div>
      )}

      {step?.pathLabel && (
        <div className="mt-4 bg-background/50 p-3 rounded text-sm font-mono text-primary/90 border border-primary/20">
          <span className="text-muted-foreground mr-1">Ruta de datos:</span> {step.pathLabel}
        </div>
      )}
    </div>
  );
}
