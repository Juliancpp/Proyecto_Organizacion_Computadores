import { useEffect, useRef } from "react";
import { Terminal, Cpu, Database, Type } from "lucide-react";
import { useSimStore } from "@/store/simulationStore";
import type { OutputEntry } from "@/types/simulation";

const TYPE_ICON: Record<OutputEntry["type"], React.ReactNode> = {
  register: <Cpu className="w-3 h-3 text-blue-400 shrink-0" />,
  memory:   <Database className="w-3 h-3 text-yellow-400 shrink-0" />,
  string:   <Type className="w-3 h-3 text-green-400 shrink-0" />,
};

const TYPE_COLOR: Record<OutputEntry["type"], string> = {
  register: "text-blue-300",
  memory:   "text-yellow-300",
  string:   "text-green-300",
};

export function OutputPanel() {
  const { result, activeArch } = useSimStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  const outputLog: OutputEntry[] = result?.[activeArch]?.output_log ?? [];

  // Auto-scroll to bottom whenever new entries arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [outputLog.length]);

  return (
    <div className="h-full flex flex-col bg-[#0d0d0f]">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border bg-card shrink-0">
        <Terminal className="w-3.5 h-3.5 text-primary" />
        <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
          Program Output
        </span>
        <span className="ml-auto text-[10px] font-mono text-muted-foreground">
          {activeArch.toUpperCase()} · {outputLog.length} line{outputLog.length !== 1 ? "s" : ""}
        </span>
        {outputLog.length > 0 && (
          <button
            onClick={() => bottomRef.current?.scrollIntoView({ behavior: "smooth" })}
            className="text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
            title="Scroll to bottom"
          >
            ↓
          </button>
        )}
      </div>

      {/* Output area */}
      <div className="flex-1 overflow-y-auto font-mono text-xs p-3 space-y-0.5">
        {outputLog.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
            <Terminal className="w-8 h-8 opacity-20" />
            <p className="text-[11px]">No output yet.</p>
            <p className="text-[10px] opacity-60">
              Use <span className="text-primary">PRINT Rx</span>,{" "}
              <span className="text-primary">PRINT_MEM addr</span>, or{" "}
              <span className="text-primary">PRINT_STR "text"</span> in your program.
            </p>
          </div>
        ) : (
          outputLog.map((entry, i) => (
            <div
              key={i}
              className="flex items-start gap-2 py-0.5 border-b border-border/30 last:border-0"
            >
              {/* Cycle badge */}
              <span className="text-[10px] text-muted-foreground w-12 shrink-0 pt-px">
                #{entry.cycle}
              </span>
              {/* Type icon */}
              <span className="pt-px">{TYPE_ICON[entry.type]}</span>
              {/* Label */}
              {entry.label && (
                <span className="text-muted-foreground shrink-0">{entry.label}:</span>
              )}
              {/* Value */}
              <span className={`${TYPE_COLOR[entry.type]} break-all`}>
                {entry.value}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
