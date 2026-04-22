import type { MicroSummary } from "@/lib/cpu-model/guidedExecution";
import { CheckCircle2 } from "lucide-react";

const memoryLabel: Record<string, string> = { "Yes": "Sí", "No": "No", "Maybe": "Posible" };
const storedLabel: Record<string, string> = { "Register": "Registro", "Memory": "Memoria", "None": "Ninguno", "Register/Internal": "Registro/Interno" };

export function InstructionSummaryPanel({ summary }: { summary?: MicroSummary }) {
  if (!summary) return null;

  return (
    <div className="rounded border-2 border-neon-green/50 bg-neon-green/5 p-5 my-4 animate-in fade-in slide-in-from-bottom-2">
      <div className="flex items-center gap-2 mb-4">
        <CheckCircle2 className="w-5 h-5 text-neon-green" />
        <h3 className="text-sm font-bold text-neon-green">Instrucción Completada</h3>
      </div>
      
      <div className="grid grid-cols-2 gap-y-3 text-sm font-mono">
        <span className="text-muted-foreground">Instrucción:</span>
        <span className="text-foreground font-bold">{summary.instruction}</span>
        
        <span className="text-muted-foreground">Componentes usados:</span>
        <span className="text-foreground">{summary.componentsUsed.join(", ")}</span>
        
        <span className="text-muted-foreground">¿Accedió a memoria?</span>
        <span className={summary.memoryAccessed === "Yes" ? "text-neon-amber font-bold" : "text-foreground"}>
          {memoryLabel[summary.memoryAccessed] ?? summary.memoryAccessed}
        </span>
        
        <span className="text-muted-foreground">Resultado guardado en:</span>
        <span className={summary.resultStoredIn !== "None" ? "text-neon-green font-bold" : "text-foreground"}>
          {storedLabel[summary.resultStoredIn] ?? summary.resultStoredIn}
        </span>
      </div>
    </div>
  );
}
