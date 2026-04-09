export function ModeSwitcher({
  activeArch,
  setActiveArch,
  riscAvailable,
  ciscAvailable,
}: {
  activeArch: "risc" | "cisc";
  setActiveArch: (arch: "risc" | "cisc") => void;
  riscAvailable: boolean;
  ciscAvailable: boolean;
}) {
  return (
    <div className="flex items-center gap-1">
      <button
        disabled={!riscAvailable}
        onClick={() => setActiveArch("risc")}
        className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase ${
          activeArch === "risc" ? "bg-primary/20 text-primary border border-primary/40" : "text-muted-foreground"
        } disabled:opacity-40`}
      >
        RISC
      </button>
      <button
        disabled={!ciscAvailable}
        onClick={() => setActiveArch("cisc")}
        className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase ${
          activeArch === "cisc" ? "bg-primary/20 text-primary border border-primary/40" : "text-muted-foreground"
        } disabled:opacity-40`}
      >
        CISC
      </button>
    </div>
  );
}
