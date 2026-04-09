import type { GuidedStep } from "@/lib/cpu-model";

export function ExplanationPanel({ step }: { step?: GuidedStep }) {
  return (
    <div className="rounded border-2 border-primary/40 bg-primary/10 p-4 relative overflow-hidden shadow-lg">
      <div className="absolute top-0 right-0 p-4 opacity-10 text-4xl">👨‍🏫</div>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xl">👨‍🏫</span>
        <div className="text-xs font-bold text-primary uppercase tracking-wider">Professor's Explanation</div>
      </div>
      <p className="text-sm font-medium text-foreground leading-relaxed mt-2">
        {step?.narration || "Click 'Next Step' to begin the guided walkthrough execution."}
      </p>
      {step?.pathLabel && (
        <div className="mt-3 bg-background/50 p-2 rounded text-xs font-mono text-primary/90 border border-primary/20">
          <span className="text-muted-foreground mr-1">Path:</span> {step.pathLabel}
        </div>
      )}
    </div>
  );
}
