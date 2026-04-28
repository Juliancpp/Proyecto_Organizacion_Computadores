import { useSimStore } from "@/store/simulationStore";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, PieChart, Pie, Cell, Legend,
} from "recharts";
import { motion } from "framer-motion";
import type { ArchResult, Metrics } from "@/types/simulation";

const CHART_COLORS = ["#06b6d4", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#ec4899"];
const EMPTY_METRICS: Metrics = {
  instruction_count: 0,
  total_cycles: 0,
  cpi: 0,
  t_cycle_ns: 0,
  cpu_time_ns: 0,
  cpu_time_us: 0,
};

export function MetricsTab() {
  const { result } = useSimStore();

  if (!result) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm font-mono">
        Run a simulation to see metrics
      </div>
    );
  }

  const risc = result.risc;
  const cisc = result.cisc;
  const x86 = result.x86;

  if (!risc && !cisc && !x86) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm font-mono">
        No architecture result available
      </div>
    );
  }

  const comparison = result.comparison ?? {
    speedup_risc_over_cisc: 0,
    cycle_ratio: 0,
    analysis: "No comparison available",
  };
  const riscMetrics = risc?.metrics ?? EMPTY_METRICS;
  const ciscMetrics = cisc?.metrics ?? EMPTY_METRICS;
  const riscTimeline = risc?.timeline ?? [];
  const ciscTimeline = cisc?.timeline ?? [];
  const riscFinalState = risc?.final_state ?? { registers: [], memory: {} };
  const ciscFinalState = cisc?.final_state ?? { registers: [], memory: {} };

  const barData = [
    { name: "Cycles", RISC: riscMetrics.total_cycles, CISC: ciscMetrics.total_cycles },
    { name: "Instructions", RISC: riscMetrics.instruction_count, CISC: ciscMetrics.instruction_count },
  ];

  // Cumulative events
  const maxCycles = Math.max(riscTimeline.length, ciscTimeline.length);
  const lineData = Array.from({ length: maxCycles }, (_, i) => ({
    cycle: i + 1,
    RISC: riscTimeline.slice(0, i + 1).reduce((s, c) => s + (c.events?.length ?? 0), 0),
    CISC: ciscTimeline.slice(0, i + 1).reduce((s, c) => s + (c.events?.length ?? 0), 0),
  }));

  // Component mix
  const getComponentMix = (timeline: ArchResult["timeline"]) => {
    const counts: Record<string, number> = {};
    timeline.forEach((c) => (c.events ?? []).forEach((e) => {
      counts[e.component] = (counts[e.component] || 0) + 1;
    }));
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  };

  const riscMix = getComponentMix(riscTimeline);
  const ciscMix = getComponentMix(ciscTimeline);

  return (
    <div className="h-full overflow-auto scrollbar-thin p-4 space-y-4">
      {/* Metric Cards */}
      <div className="grid grid-cols-2 gap-3">
        <MetricGroup label="RISC" metrics={riscMetrics} color="text-neon-cyan" missing={!risc} />
        <MetricGroup label="CISC" metrics={ciscMetrics} color="text-neon-violet" missing={!cisc} />
      </div>

      {/* Comparison */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid grid-cols-3 gap-3">
        <CompCard label="Speedup (RISC/CISC)" value={comparison.speedup_risc_over_cisc.toFixed(2) + "x"} />
        <CompCard label="Cycle Ratio" value={comparison.cycle_ratio.toFixed(2)} />
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="text-[10px] font-mono text-muted-foreground uppercase mb-1">Analysis</div>
          <div className="text-xs text-foreground">{comparison.analysis}</div>
        </div>
      </motion.div>

      {/* Charts */}
      <div className="grid grid-cols-2 gap-3">
        <ChartCard title="Cycles & Instructions">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={barData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#222" />
              <XAxis dataKey="name" tick={{ fill: "#666", fontSize: 10 }} />
              <YAxis tick={{ fill: "#666", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "#111", border: "1px solid #222", fontSize: 11 }} />
              <Bar dataKey="RISC" fill="#06b6d4" radius={[4, 4, 0, 0]} />
              <Bar dataKey="CISC" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Cumulative Events">
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={lineData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#222" />
              <XAxis dataKey="cycle" tick={{ fill: "#666", fontSize: 10 }} />
              <YAxis tick={{ fill: "#666", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "#111", border: "1px solid #222", fontSize: 11 }} />
              <Line type="monotone" dataKey="RISC" stroke="#06b6d4" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="CISC" stroke="#8b5cf6" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <ChartCard title="RISC Component Mix">
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={riscMix} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={40} outerRadius={70} paddingAngle={2}>
                {riscMix.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
              </Pie>
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "#111", border: "1px solid #222", fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="CISC Component Mix">
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={ciscMix} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={40} outerRadius={70} paddingAngle={2}>
                {ciscMix.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
              </Pie>
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "#111", border: "1px solid #222", fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Register Tables */}
      <div className="grid grid-cols-2 gap-3">
        <RegisterTable label="RISC" registers={riscFinalState.registers} missing={!risc} />
        <RegisterTable label="CISC" registers={ciscFinalState.registers} missing={!cisc} />
      </div>

      {/* Memory Tables */}
      <div className="grid grid-cols-2 gap-3">
        <MemoryTable label="RISC" memory={riscFinalState.memory} missing={!risc} />
        <MemoryTable label="CISC" memory={ciscFinalState.memory} missing={!cisc} />
      </div>

      {/* x86-64 Section */}
      {x86 && (
        <>
          <div className="border-t border-border my-4" />
          <div className="text-xs font-mono font-bold uppercase tracking-wider text-neon-green mb-2">x86-64</div>
          <X86Section x86={x86} />
        </>
      )}
    </div>
  );
}

function MetricGroup({ label, metrics, color, missing }: { label: string; metrics: any; color: string; missing?: boolean }) {
  return (
    <div className="bg-card border border-border rounded-lg p-3 space-y-2">
      <div className={`text-xs font-mono font-bold uppercase tracking-wider ${color}`}>{label}</div>
      {missing && <div className="text-[10px] font-mono text-muted-foreground">No data for this architecture</div>}
      <div className="grid grid-cols-3 gap-2">
        <MiniCard label="Cycles" value={metrics.total_cycles} />
        <MiniCard label="Instructions" value={metrics.instruction_count} />
        <MiniCard label="CPI" value={metrics.cpi.toFixed(2)} />
        <MiniCard label="CPU Time (ns)" value={metrics.cpu_time_ns.toFixed(1)} />
        <MiniCard label="CPU Time (μs)" value={metrics.cpu_time_us.toFixed(4)} />
        <MiniCard label="T_cycle" value={metrics.t_cycle_ns + " ns"} />
      </div>
    </div>
  );
}

function MiniCard({ label, value }: { label: string; value: any }) {
  return (
    <div className="bg-secondary/50 rounded p-2">
      <div className="text-[9px] font-mono text-muted-foreground uppercase">{label}</div>
      <div className="text-sm font-mono text-foreground font-semibold">{value}</div>
    </div>
  );
}

function CompCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card border border-border rounded-lg p-3 text-center">
      <div className="text-[10px] font-mono text-muted-foreground uppercase mb-1">{label}</div>
      <div className="text-lg font-mono text-primary font-bold">{value}</div>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">{title}</div>
      {children}
    </div>
  );
}

function RegisterTable({ label, registers, missing }: { label: string; registers: number[]; missing?: boolean }) {
  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">{label} Registers</div>
      {missing && <div className="text-xs text-muted-foreground mb-2">No data for this architecture</div>}
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="text-muted-foreground">
            <th className="text-left py-1">Reg</th>
            <th className="text-right py-1">Value</th>
          </tr>
        </thead>
        <tbody>
          {registers.map((v, i) => (
            <tr key={i} className="border-t border-border/50">
              <td className="py-1 text-neon-cyan">R{i}</td>
              <td className="py-1 text-right text-foreground">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MemoryTable({ label, memory, missing }: { label: string; memory: Record<string, number>; missing?: boolean }) {
  const entries = Object.entries(memory).slice(0, 20);
  return (
    <div className="bg-card border border-border rounded-lg p-3">
      <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">{label} Memory</div>
      {missing && <div className="text-xs text-muted-foreground mb-2">No data for this architecture</div>}
      {entries.length === 0 ? (
        <div className="text-xs text-muted-foreground">No memory used</div>
      ) : (
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="text-muted-foreground">
              <th className="text-left py-1">Addr</th>
              <th className="text-right py-1">Value</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([addr, val]) => (
              <tr key={addr} className="border-t border-border/50">
                <td className="py-1 text-neon-amber">{addr}</td>
                <td className="py-1 text-right text-foreground">{val}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function X86Section({ x86 }: { x86: Record<string, any> }) {
  const finalState = x86.final_state || {};
  const registers = finalState.registers || {};
  const flags = finalState.flags || {};
  const arrays = x86.arrays || {};
  const timeline = x86.timeline || [];

  return (
    <div className="space-y-3">
      {/* Cycles and Status */}
      <div className="grid grid-cols-4 gap-3">
        <MiniCard label="Cycles" value={x86.cycles || 0} />
        <MiniCard label="Instructions" value={x86.parsed_instructions?.instructions?.length || 0} />
        <MiniCard label="Halted" value={finalState.halted ? "YES" : "NO"} />
        <MiniCard label="Timeline" value={`${timeline.length} entries`} />
      </div>

      {/* Arrays */}
      {Object.entries(arrays).length > 0 && (
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">Data Arrays</div>
          {Object.entries(arrays).map(([name, values]: [string, any]) => (
            <div key={name} className="mb-2">
              <div className="text-xs font-mono text-neon-cyan">{name}:</div>
              <div className="text-xs font-mono text-foreground">[{Array.isArray(values) ? values.join(", ") : String(values)}]</div>
            </div>
          ))}
        </div>
      )}

      {/* x86 Registers */}
      <div className="bg-card border border-border rounded-lg p-3">
        <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">x86-64 Registers</div>
        <div className="grid grid-cols-4 gap-2 text-xs font-mono">
          {Object.entries(registers).map(([reg, val]) => (
            <div key={reg} className="bg-secondary/50 rounded p-1">
              <span className="text-neon-cyan">{reg}</span>: <span className="text-foreground">{val as number}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Flags */}
      <div className="bg-card border border-border rounded-lg p-3">
        <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">Flags</div>
        <div className="flex gap-3 text-xs font-mono">
          {Object.entries(flags).map(([flag, val]) => (
            <span key={flag} className={val ? "text-green-400" : "text-red-400"}>
              {flag}: {val ? "1" : "0"}
            </span>
          ))}
        </div>
      </div>

      {/* Timeline Preview */}
      {timeline.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">
            Timeline (first 5 cycles)
          </div>
          <div className="space-y-1 max-h-40 overflow-auto">
            {timeline.slice(0, 5).map((cycle: any, i: number) => (
              <div key={i} className="text-xs font-mono bg-secondary/30 rounded p-1">
                <span className="text-neon-amber">C{cycle.cycle}</span>
                <span className="text-muted-foreground ml-2">PC:{cycle.pc}</span>
                <span className="text-foreground ml-2">{cycle.events?.length || 0} events</span>
              </div>
            ))}
            {timeline.length > 5 && (
              <div className="text-xs text-muted-foreground text-center">... {timeline.length - 5} more cycles</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
