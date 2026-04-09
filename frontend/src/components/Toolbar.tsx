import { Play, Pause, SkipForward, Trash2, Zap, RotateCcw } from "lucide-react";
import { useSimStore } from "@/store/simulationStore";
import { simulate } from "@/lib/api";
import { motion } from "framer-motion";

export function Toolbar() {
  const {
    code, pipeline, loading, playing, speed, result,
    setPipeline, setResult, setLoading, setError,
    setPlaying, setSpeed, stepForward, resetPlayback, setCode,
  } = useSimStore();

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await simulate({
        code,
        step: false,
        pipeline,
        transpile: true,
        risc_tcycle: 1.0,
        cisc_tcycle: 1.5,
      });
      setResult(res);
      if (res.errors) {
        const errs = Object.entries(res.errors)
          .map(([arch, message]) => `${arch.toUpperCase()}: ${message}`)
          .join(" | ");
        setError(errs || null);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const speeds = [1, 2, 4, 8];

  return (
    <div className="flex items-center gap-1 px-3 py-2 bg-card border-b border-border">
      <div className="flex items-center gap-1 mr-2">
        <span className="text-xs font-mono text-primary font-bold tracking-wider mr-2">
          RISC vs CISC Lab
        </span>
      </div>

      <ToolbarButton onClick={handleRun} disabled={loading} title="Run">
        <Play className="w-3.5 h-3.5" />
        <span>{loading ? "Running..." : "Run"}</span>
      </ToolbarButton>

      <ToolbarButton
        onClick={() => setPlaying(!playing)}
        disabled={!result}
        title={playing ? "Pause" : "Play"}
      >
        {playing ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
      </ToolbarButton>

      <ToolbarButton onClick={stepForward} disabled={!result} title="Step">
        <SkipForward className="w-3.5 h-3.5" />
      </ToolbarButton>

      <ToolbarButton
        onClick={() => {
          setCode(`MOV R0, 5\nMOV R1, 3\nADD R2, R0, R1\nSTORE R2, 100\nLOAD R3, 100\nHALT`);
          setResult(null);
        }}
        title="Clear"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </ToolbarButton>

      <div className="h-5 w-px bg-border mx-1" />

      <button
        onClick={() => setPipeline(!pipeline)}
        className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-mono transition-all ${
          pipeline
            ? "bg-primary/20 text-primary border border-primary/40"
            : "bg-secondary text-muted-foreground border border-border hover:text-foreground"
        }`}
      >
        <Zap className="w-3 h-3" />
        Pipeline {pipeline ? "ON" : "OFF"}
      </button>

      <div className="h-5 w-px bg-border mx-1" />

      <div className="flex items-center gap-0.5">
        {speeds.map((s) => (
          <button
            key={s}
            onClick={() => setSpeed(s)}
            className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition-all ${
              speed === s
                ? "bg-primary/20 text-primary"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            x{s}
          </button>
        ))}
      </div>

      <div className="h-5 w-px bg-border mx-1" />

      <ToolbarButton onClick={resetPlayback} disabled={!result} title="Reset">
        <RotateCcw className="w-3.5 h-3.5" />
      </ToolbarButton>

    </div>
  );
}

function ToolbarButton({
  children,
  onClick,
  disabled,
  title,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  title: string;
}) {
  return (
    <motion.button
      whileTap={{ scale: 0.95 }}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="flex items-center gap-1 px-2 py-1 rounded text-xs font-mono text-muted-foreground
        hover:text-foreground hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed transition-all"
    >
      {children}
    </motion.button>
  );
}
