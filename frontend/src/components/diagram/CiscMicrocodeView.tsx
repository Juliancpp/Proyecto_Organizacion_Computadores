import type { SimEvent } from "@/types/simulation";
import {
  getCurrentMicroEvent,
  getMicroIndex,
  getMicroTotal,
  getMicroAddress,
  getInternalBusText,
  getRecentMicroOps,
} from "@/lib/cpu-model";

export function CiscMicrocodeView({
  timeline,
  currentCycle,
}: {
  timeline: { cycle: number; events: SimEvent[] }[];
  currentCycle: number;
}) {
  const currentEvents = timeline[currentCycle]?.events ?? [];
  const microEvent = getCurrentMicroEvent(currentEvents);
  const idx = getMicroIndex(microEvent);
  const total = getMicroTotal(microEvent);
  const mar = getMicroAddress(microEvent?.action ?? "");
  const mdr = microEvent?.output;
  const recentMicroOps = getRecentMicroOps(timeline, currentCycle);

  return (
    <div className="p-3 space-y-3">
      <div className="rounded border border-border bg-card p-2">
        <div className="text-[10px] font-mono text-muted-foreground">Microcode Engine / Control Store</div>
        <div className="text-xs font-mono mt-1 text-foreground">
          {microEvent ? `uOp ${idx}/${total}: ${microEvent.action}` : "No micro-operation on this cycle"}
        </div>
        {total > 0 && (
          <div className="mt-2 h-1.5 bg-secondary rounded">
            <div className="h-1.5 bg-primary rounded" style={{ width: `${(idx / total) * 100}%` }} />
          </div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded border border-border bg-card p-2">
          <div className="text-[10px] font-mono text-muted-foreground mb-1">MAR</div>
          <div className="text-sm font-mono text-neon-amber">{mar ?? "-"}</div>
        </div>
        <div className="rounded border border-border bg-card p-2">
          <div className="text-[10px] font-mono text-muted-foreground mb-1">MDR</div>
          <div className="text-sm font-mono text-neon-cyan">{mdr !== undefined ? JSON.stringify(mdr) : "-"}</div>
        </div>
        <div className="rounded border border-border bg-card p-2">
          <div className="text-[10px] font-mono text-muted-foreground mb-1">Internal Bus</div>
          <div className="text-xs font-mono text-foreground">{getInternalBusText(microEvent)}</div>
        </div>
      </div>

      <div className="rounded border border-border bg-card p-2">
        <div className="text-[10px] font-mono text-muted-foreground mb-1">Recent micro-operations</div>
        <div className="space-y-1 max-h-44 overflow-auto">
          {recentMicroOps.length === 0 ? (
            <div className="text-xs font-mono text-muted-foreground">No micro-op history yet</div>
          ) : (
            recentMicroOps.map((m, i) => (
              <div key={`${m.cycle}-${i}`} className="text-xs font-mono text-foreground">
                C{m.cycle}: [{m.idx}/{m.total}] {m.text}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
