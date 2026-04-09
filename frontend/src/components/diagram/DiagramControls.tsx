interface DiagramControlsProps {
  playing: boolean;
  speed: number;
  currentCycle: number;
  totalCycles: number;
  activeArch: "risc" | "cisc";
  stageIndicator: string;
  onTogglePlay: () => void;
  onStep: () => void;
  onReset: () => void;
  onSpeedChange: (speed: number) => void;
  onCycleChange: (cycle: number) => void;
}

export function DiagramControls({
  playing,
  speed,
  currentCycle,
  totalCycles,
  activeArch,
  stageIndicator,
  onTogglePlay,
  onStep,
  onReset,
  onSpeedChange,
  onCycleChange,
}: DiagramControlsProps) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border bg-card">
      <button onClick={onTogglePlay} className="text-xs font-mono text-muted-foreground hover:text-foreground">
        {playing ? "⏸" : "▶"}
      </button>
      <button onClick={onStep} className="text-xs font-mono text-muted-foreground hover:text-foreground">⏭</button>
      <button onClick={onReset} className="text-xs font-mono text-muted-foreground hover:text-foreground">↺</button>
      <div className="flex gap-0.5 ml-2">
        {[1, 2, 4, 8].map((s) => (
          <button
            key={s}
            onClick={() => onSpeedChange(s)}
            className={`px-1 py-0.5 text-[10px] font-mono rounded ${speed === s ? "text-primary bg-primary/10" : "text-muted-foreground"}`}
          >
            x{s}
          </button>
        ))}
      </div>
      <input
        type="range"
        min={0}
        max={Math.max(0, totalCycles - 1)}
        value={currentCycle}
        onChange={(e) => onCycleChange(Number(e.target.value))}
        className="ml-2 w-32 h-1 accent-primary"
      />
      <span className="text-[10px] font-mono text-muted-foreground ml-1">
        Cycle {currentCycle > -1 ? currentCycle + 1 : 0} / {totalCycles}
      </span>
      <span className="ml-auto text-[10px] font-mono text-primary uppercase">{activeArch}</span>
      <span className="text-[10px] font-mono text-neon-amber">{stageIndicator}</span>
    </div>
  );
}
