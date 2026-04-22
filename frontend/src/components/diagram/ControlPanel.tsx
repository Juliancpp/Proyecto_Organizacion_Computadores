interface ControlPanelProps {
  isPlaying: boolean;
  canStep: boolean;
  cycle: number;
  onNextStep: () => void;
  onTogglePlay: () => void;
  onReset: () => void;
}

export function ControlPanel({ isPlaying, canStep, cycle, onNextStep, onTogglePlay, onReset }: ControlPanelProps) {
  return (
    <div className="rounded border border-border bg-card p-3 flex items-center gap-2">
      <button
        onClick={onNextStep}
        disabled={!canStep}
        className="px-3 py-1.5 rounded text-sm font-mono bg-primary/20 text-primary disabled:opacity-40 hover:bg-primary/30 transition-colors"
      >
        ▶ Siguiente Paso
      </button>
      <button onClick={onTogglePlay} className="px-3 py-1.5 rounded text-sm font-mono bg-secondary text-foreground hover:bg-secondary/80 transition-colors">
        {isPlaying ? "⏸ Pausar" : "▶ Auto"}
      </button>
      <button onClick={onReset} className="px-3 py-1.5 rounded text-sm font-mono bg-secondary text-foreground hover:bg-secondary/80 transition-colors">
        Reiniciar
      </button>
      <div className="ml-auto text-sm font-mono text-neon-amber font-semibold">Reloj: Ciclo {cycle}</div>
    </div>
  );
}
