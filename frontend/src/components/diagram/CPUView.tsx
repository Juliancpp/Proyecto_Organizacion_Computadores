import type { GuidedStep } from "@/lib/cpu-model";

const COMPONENT_HELP: Record<string, string> = {
  ALU: "Performs arithmetic and logic operations.",
  PC: "Points to the next instruction to fetch.",
  REGISTERS: "Register file stores CPU general-purpose registers.",
  MEMORY: "Main memory stores instructions and data.",
  CONTROL: "Control Unit generates datapath control signals.",
  BUS: "Internal bus carries values between components.",
};

function RiscCPUView({ step }: { step?: GuidedStep }) {
  const stageList = ["IF", "ID", "EX", "MEM", "WB"];
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-5 gap-2">
        {stageList.map((stage) => {
          const active = step?.stage === stage;
          return (
            <div
              key={stage}
              className={`rounded border p-2 transition-opacity ${active ? "border-primary bg-primary/15 opacity-100" : "border-border opacity-35"}`}
              title={COMPONENT_HELP[stage === "IF" ? "PC" : stage === "ID" ? "CONTROL" : stage === "EX" ? "ALU" : stage === "MEM" ? "MEMORY" : "REGISTERS"]}
            >
              <div className="text-[10px] font-mono text-muted-foreground">{stage}</div>
              <div className="text-xs font-mono text-foreground mt-1">{active ? step?.rawEvent.action : "inactive"}</div>
            </div>
          );
        })}
      </div>
      <div className="rounded border border-primary/30 bg-primary/5 p-2 text-xs font-mono text-primary">
        Data Flow: {step?.pathLabel || "No active flow"}
      </div>
      <div className="rounded border border-border bg-black/20 p-2">
        <div className="text-[10px] font-mono text-muted-foreground mb-2">RISC Datapath Graphic</div>
        <svg viewBox="0 0 760 90" className="w-full h-24">
          {stageList.map((stage, i) => {
            const x = 10 + i * 150;
            const active = step?.stage === stage;
            return (
              <g key={stage}>
                <rect x={x} y={20} width={120} height={40} rx={6} fill={active ? "#10253a" : "#111"} stroke={active ? "#06b6d4" : "#333"} />
                <text x={x + 60} y={44} textAnchor="middle" fill={active ? "#67e8f9" : "#777"} fontSize="11" fontFamily="monospace">
                  {stage}
                </text>
                {i < stageList.length - 1 && (
                  <>
                    <line x1={x + 120} y1={40} x2={x + 145} y2={40} stroke={active ? "#06b6d4" : "#444"} strokeWidth="2" />
                    <polygon points={`${x + 145},40 ${x + 138},36 ${x + 138},44`} fill={active ? "#06b6d4" : "#444"} />
                  </>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

function CiscCPUView({ step, stepList }: { step?: GuidedStep; stepList: GuidedStep[] }) {
  return (
    <div className="space-y-2">
      <div className="text-[10px] font-mono text-muted-foreground uppercase">Micro-operations (CISC, no pipeline)</div>
      <div className="space-y-1 max-h-64 overflow-auto">
        {stepList.map((s, i) => {
          const active = step?.cycle === s.cycle && step?.stage === s.stage && step?.rawEvent.action === s.rawEvent.action;
          return (
            <div
              key={`${s.cycle}-${i}`}
              className={`rounded border p-2 text-xs font-mono transition-opacity ${active ? "border-primary bg-primary/15 opacity-100" : "border-border opacity-35"}`}
              title={COMPONENT_HELP[s.focusComponent] || "CISC microcode step"}
            >
              <span className="text-muted-foreground mr-2">C{s.cycle}</span>
              <span className="text-foreground">{s.stage}: {s.rawEvent.action}</span>
            </div>
          );
        })}
      </div>
      <div className="rounded border border-primary/30 bg-primary/5 p-2 text-xs font-mono text-primary">
        Data Flow: {step?.pathLabel || "No active flow"}
      </div>
      <div className="rounded border border-border bg-black/20 p-2">
        <div className="text-[10px] font-mono text-muted-foreground mb-2">CISC Microcode Graphic</div>
        <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] gap-2 items-center text-[10px] font-mono">
          <div className={`rounded border p-2 ${step?.focusComponent === "MEMORY" ? "border-primary bg-primary/15" : "border-border opacity-60"}`}>MAR/MDR</div>
          <span className="text-muted-foreground">→</span>
          <div className={`rounded border p-2 ${step?.focusComponent === "ALU" ? "border-primary bg-primary/15" : "border-border opacity-60"}`}>ALU</div>
          <span className="text-muted-foreground">→</span>
          <div className={`rounded border p-2 ${step?.focusComponent === "REGISTERS" ? "border-primary bg-primary/15" : "border-border opacity-60"}`}>Regs/Memory</div>
        </div>
      </div>
    </div>
  );
}

export function CPUView({
  activeArch,
  step,
  stepList,
}: {
  activeArch: "risc" | "cisc";
  step?: GuidedStep;
  stepList: GuidedStep[];
}) {
  return (
    <div className="rounded border border-border bg-card p-3">
      <div className="text-[10px] font-mono text-muted-foreground uppercase mb-2">CPU View (Focus Mode)</div>
      {activeArch === "risc" ? <RiscCPUView step={step} /> : <CiscCPUView step={step} stepList={stepList} />}
    </div>
  );
}
