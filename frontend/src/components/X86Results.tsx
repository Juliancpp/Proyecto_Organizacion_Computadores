import { useSimStore } from "@/store/simulationStore";
import type { X86Result } from "@/types/simulation";
import { Cpu, Activity, MemoryStick, Flag, PlayCircle } from "lucide-react";

export function X86Results() {
  const result = useSimStore((s) => s.result);

  if (!result?.x86) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm font-mono p-4">
        No x86 simulation results available
      </div>
    );
  }

  const x86: X86Result = result.x86;
  const finalState = x86.final_state;
  const registers = finalState.registers;
  const flags = finalState.flags;
  const arrays = x86.arrays || {};
  const timeline = x86.timeline || [];
  const instructions = x86.parsed_instructions?.instructions || [];

  return (
    <div className="h-full overflow-auto p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2 text-neon-green">
        <Cpu className="w-5 h-5" />
        <span className="text-sm font-mono font-bold">x86-64 Simulation Results</span>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <SummaryCard
          icon={<Activity className="w-4 h-4" />}
          label="Total Cycles"
          value={x86.cycles || 0}
          color="text-neon-cyan"
        />
        <SummaryCard
          icon={<PlayCircle className="w-4 h-4" />}
          label="Instructions"
          value={instructions.length}
          color="text-neon-violet"
        />
        <SummaryCard
          icon={<Flag className="w-4 h-4" />}
          label="Halted"
          value={finalState.halted ? "YES" : "NO"}
          color={finalState.halted ? "text-green-400" : "text-red-400"}
        />
        <SummaryCard
          icon={<MemoryStick className="w-4 h-4" />}
          label="Timeline Entries"
          value={timeline.length}
          color="text-neon-amber"
        />
      </div>

      {/* Data Arrays */}
      {Object.keys(arrays).length > 0 && (
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">Data Arrays (Final State)</div>
          <div className="space-y-2">
            {Object.entries(arrays).map(([name, values]: [string, any]) => (
              <div key={name} className="bg-secondary/30 rounded p-2">
                <div className="text-xs font-mono text-neon-cyan mb-1">{name}:</div>
                <div className="text-xs font-mono text-foreground font-mono">
                  [{Array.isArray(values) ? values.join(", ") : String(values)}]
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Registers */}
      <div className="bg-card border border-border rounded-lg p-3">
        <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">Registers (Final State)</div>
        <div className="grid grid-cols-4 gap-2 text-xs font-mono">
          {Object.entries(registers).map(([reg, val]: [string, any]) => (
            <div key={reg} className="bg-secondary/50 rounded p-2 flex justify-between">
              <span className="text-neon-cyan">{reg}</span>
              <span className="text-foreground">{val}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Flags */}
      <div className="bg-card border border-border rounded-lg p-3">
        <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">Flags</div>
        <div className="flex gap-4 text-xs font-mono">
          {Object.entries(flags).map(([flag, val]: [string, any]) => (
            <div key={flag} className="flex items-center gap-1">
              <span className={val ? "text-green-400" : "text-red-400"}>
                {flag}: {val ? "1" : "0"}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Timeline */}
      {timeline.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">
            Execution Timeline ({timeline.length} cycles)
          </div>
          <div className="max-h-64 overflow-auto space-y-1">
            {timeline.slice(0, 100).map((cycle: any, i: number) => (
              <div
                key={i}
                className="text-xs font-mono bg-secondary/20 rounded p-2 flex items-center gap-3"
              >
                <span className="text-neon-amber w-12">C{cycle.cycle}</span>
                <span className="text-muted-foreground w-12">PC:{cycle.pc}</span>
                <span className="text-foreground flex-1 truncate">
                  {cycle.current_instruction || `Events: ${cycle.events?.length || 0}`}
                </span>
              </div>
            ))}
            {timeline.length > 100 && (
              <div className="text-xs text-muted-foreground text-center py-2">
                ... {timeline.length - 100} more cycles
              </div>
            )}
          </div>
        </div>
      )}

      {/* Program Info */}
      <div className="bg-card border border-border rounded-lg p-3">
        <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">Parsed Instructions</div>
        <div className="space-y-1 max-h-40 overflow-auto">
          {instructions.map((instr: any, i: number) => (
            <div key={i} className="text-xs font-mono flex gap-2">
              <span className="text-muted-foreground w-6">{i}</span>
              <span className="text-neon-violet w-16">{instr.opcode}</span>
              <span className="text-foreground">{instr.raw}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SummaryCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color: string;
}) {
  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <div className={`flex items-center gap-2 ${color} mb-1`}>
        {icon}
        <span className="text-[10px] font-mono uppercase">{label}</span>
      </div>
      <div className="text-xl font-mono font-bold text-foreground">{value}</div>
    </div>
  );
}
