import { useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { Toolbar } from "@/components/Toolbar";
import { EditorPanel } from "@/components/EditorPanel";
import { DiagramTab } from "@/components/DiagramTab";
import { MetricsTab } from "@/components/MetricsTab";
import { EventsTab } from "@/components/EventsTab";
import { OutputPanel } from "@/components/OutputPanel";
import { useSimStore } from "@/store/simulationStore";

type TabId = "diagram" | "metrics" | "events" | "output";

const TABS: { id: TabId; label: string }[] = [
  { id: "diagram", label: "Diagrama" },
  { id: "metrics", label: "Métricas" },
  { id: "events", label: "Eventos" },
  { id: "output", label: "Salida" },
];

export default function MainLayout() {
  const [activeTab, setActiveTab] = useState<TabId>("diagram");
  const error = useSimStore((s) => s.error);
  const result = useSimStore((s) => s.result);
  const activeArch = useSimStore((s) => s.activeArch);

  // Badge: count output lines for the active arch
  const outputCount = result?.[activeArch]?.output_log?.length ?? 0;

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden">
      <Toolbar />
      {error && (
        <div className="px-3 py-1 bg-destructive/10 border-b border-destructive/30 text-destructive text-xs font-mono">
          {error}
        </div>
      )}
      <div className="flex-1 min-h-0">
        <PanelGroup direction="horizontal">
          <Panel defaultSize={40} minSize={25}>
            <EditorPanel />
          </Panel>
          <PanelResizeHandle className="w-1 bg-border hover:bg-primary/30 transition-colors" />
          <Panel defaultSize={60} minSize={30}>
            <div className="h-full flex flex-col">
              {/* Tabs */}
              <div className="flex items-center border-b border-border bg-card">
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`relative px-4 py-2 text-xs font-mono uppercase tracking-wider transition-all border-b-2 ${
                      activeTab === tab.id
                        ? "text-primary border-primary bg-primary/5"
                        : "text-muted-foreground border-transparent hover:text-foreground"
                    }`}
                  >
                    {tab.label}
                    {tab.id === "output" && outputCount > 0 && (
                      <span className="ml-1.5 px-1 py-0 rounded text-[9px] bg-primary/20 text-primary font-mono">
                        {outputCount}
                      </span>
                    )}
                  </button>
                ))}
              </div>
              <div className="flex-1 min-h-0">
                {activeTab === "diagram" && <DiagramTab />}
                {activeTab === "metrics" && <MetricsTab />}
                {activeTab === "events" && <EventsTab />}
                {activeTab === "output" && <OutputPanel />}
              </div>
            </div>
          </Panel>
        </PanelGroup>
      </div>
    </div>
  );
}
