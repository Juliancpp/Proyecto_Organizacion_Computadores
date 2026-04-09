import type { SimEvent, TimelineCycle } from "@/types/simulation";
import type { CiscMicroRecord } from "@/lib/cpu-model/types";

export function getCurrentMicroEvent(events: SimEvent[]): SimEvent | undefined {
  return events.find((e) => e.meta?.micro_op);
}

export function getMicroIndex(event?: SimEvent): number {
  return Number(event?.meta?.micro_op_index ?? 0);
}

export function getMicroTotal(event?: SimEvent): number {
  return Number(event?.meta?.total_micro_ops ?? 0);
}

export function getMicroAddress(action: string): string | null {
  const m = action.match(/MEM\[(\d+)\]/);
  return m?.[1] ?? null;
}

export function getInternalBusText(event?: SimEvent): string {
  if (!event) return "Control transfer";
  if (event.action.includes("READ")) return "Memory -> MDR -> ALU/Register";
  if (event.action.includes("WRITE")) return "ALU/Register -> MDR -> Memory";
  return "Control transfer";
}

export function getRecentMicroOps(timeline: TimelineCycle[], currentCycle: number): CiscMicroRecord[] {
  return timeline
    .slice(Math.max(0, currentCycle - 8), currentCycle + 1)
    .flatMap((c) =>
      c.events
        .filter((e) => e.meta?.micro_op)
        .map((e) => ({ cycle: c.cycle, text: e.action, idx: e.meta?.micro_op_index, total: e.meta?.total_micro_ops }))
    );
}

export function getCiscStageIndicator(events: SimEvent[]): string {
  const uop = getCurrentMicroEvent(events);
  return uop ? `Micro-op ${uop.meta?.micro_op_index}/${uop.meta?.total_micro_ops}` : "Decode/Idle";
}
