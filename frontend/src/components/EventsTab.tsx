import { useState, useMemo } from "react";
import { useSimStore } from "@/store/simulationStore";
import type { ComponentName } from "@/types/simulation";

const COMPONENT_COLORS: Record<ComponentName, string> = {
  CONTROL: "text-neon-amber",
  PC: "text-neon-amber",
  REGISTERS: "text-neon-violet",
  ALU: "text-neon-green",
  BUS: "text-neon-cyan",
  MEMORY: "text-neon-cyan",
};

const ALL_COMPONENTS: ComponentName[] = ["CONTROL", "PC", "REGISTERS", "ALU", "BUS", "MEMORY"];

export function EventsTab() {
  const { result, currentCycle, activeArch } = useSimStore();
  const [archFilter, setArchFilter] = useState<"both" | "risc" | "cisc">("both");
  const [componentFilter, setComponentFilter] = useState<Set<ComponentName>>(new Set(ALL_COMPONENTS));

  const toggleComponent = (c: ComponentName) => {
    const next = new Set(componentFilter);
    if (next.has(c)) next.delete(c); else next.add(c);
    setComponentFilter(next);
  };

  const rows = useMemo(() => {
    if (!result) return [];
    const out: { cycle: number; arch: string; component: ComponentName; action: string; inputs: string; output: string }[] = [];

    const addArch = (archName: string, timeline: typeof result.risc.timeline | undefined) => {
      if (!timeline) return;
      timeline.forEach((tc) => {
        tc.events.forEach((ev) => {
          if (!componentFilter.has(ev.component)) return;
          out.push({
            cycle: tc.cycle,
            arch: archName,
            component: ev.component,
            action: ev.action,
            inputs: JSON.stringify(ev.inputs),
            output: JSON.stringify(ev.output),
          });
        });
      });
    };

    if (archFilter === "both" || archFilter === "risc") addArch("RISC", result.risc?.timeline);
    if (archFilter === "both" || archFilter === "cisc") addArch("CISC", result.cisc?.timeline);

    return out.sort((a, b) => a.cycle - b.cycle);
  }, [result, archFilter, componentFilter]);

  if (!result) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm font-mono">
        Run a simulation to see events
      </div>
    );
  }

  const currentTimeline = result[activeArch]?.timeline;
  const currentCycleNum = currentTimeline?.[currentCycle]?.cycle;

  return (
    <div className="h-full flex flex-col">
      {/* Filters */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border bg-card flex-wrap">
        <span className="text-[10px] font-mono text-muted-foreground">Arch:</span>
        {(["both", "risc", "cisc"] as const).map((a) => (
          <button key={a} onClick={() => setArchFilter(a)}
            className={`px-1.5 py-0.5 text-[10px] font-mono rounded uppercase ${
              archFilter === a ? "bg-primary/20 text-primary" : "text-muted-foreground hover:text-foreground"
            }`}>
            {a}
          </button>
        ))}
        <div className="h-4 w-px bg-border mx-1" />
        <span className="text-[10px] font-mono text-muted-foreground">Components:</span>
        {ALL_COMPONENTS.map((c) => (
          <button key={c} onClick={() => toggleComponent(c)}
            className={`px-1.5 py-0.5 text-[10px] font-mono rounded ${
              componentFilter.has(c)
                ? `bg-secondary ${COMPONENT_COLORS[c]}`
                : "text-muted-foreground/40"
            }`}>
            {c}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto scrollbar-thin">
        <table className="w-full text-xs font-mono">
          <thead className="sticky top-0 bg-card">
            <tr className="text-muted-foreground border-b border-border">
              <th className="text-left px-3 py-1.5 w-16">Cycle</th>
              <th className="text-left px-2 py-1.5 w-14">Arch</th>
              <th className="text-left px-2 py-1.5 w-24">Component</th>
              <th className="text-left px-2 py-1.5">Action</th>
              <th className="text-left px-2 py-1.5 w-28">Inputs</th>
              <th className="text-left px-2 py-1.5 w-20">Output</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}
                className={`border-b border-border/30 hover:bg-secondary/30 transition-colors ${
                  row.cycle === currentCycleNum ? "bg-primary/5" : ""
                }`}>
                <td className="px-3 py-1 text-muted-foreground">{row.cycle}</td>
                <td className="px-2 py-1">
                  <span className={row.arch === "RISC" ? "text-neon-cyan" : "text-neon-violet"}>
                    {row.arch}
                  </span>
                </td>
                <td className={`px-2 py-1 ${COMPONENT_COLORS[row.component]}`}>{row.component}</td>
                <td className="px-2 py-1 text-foreground max-w-xs truncate">{row.action}</td>
                <td className="px-2 py-1 text-muted-foreground truncate max-w-[7rem]">{row.inputs}</td>
                <td className="px-2 py-1 text-muted-foreground truncate max-w-[5rem]">{row.output}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
