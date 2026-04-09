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
        className="px-2 py-1 rounded text-xs font-mono bg-primary/20 text-primary disabled:opacity-40"
      >
        ▶ Next Step
      </button>
      <button onClick={onTogglePlay} className="px-2 py-1 rounded text-xs font-mono bg-secondary text-foreground">
        {isPlaying ? "⏸ Pause" : "▶ Auto"}
      </button>
      <button onClick={onReset} className="px-2 py-1 rounded text-xs font-mono bg-secondary text-foreground">
        Reset
      </button>
      <div className="ml-auto text-xs font-mono text-neon-amber">Clock: Cycle {cycle}</div>
    </div>
  );
}
