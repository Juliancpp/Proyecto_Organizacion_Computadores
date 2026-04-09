import { useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { Toolbar } from "@/components/Toolbar";
import { EditorPanel } from "@/components/EditorPanel";
import { DiagramTab } from "@/components/DiagramTab";
import { MetricsTab } from "@/components/MetricsTab";
import { EventsTab } from "@/components/EventsTab";
import { useSimStore } from "@/store/simulationStore";

type TabId = "diagram" | "metrics" | "events";

const TABS: { id: TabId; label: string }[] = [
  { id: "diagram", label: "Diagrama" },
  { id: "metrics", label: "Métricas" },
  { id: "events", label: "Eventos" },
];

export default function MainLayout() {
  const [activeTab, setActiveTab] = useState<TabId>("diagram");
  const error = useSimStore((s) => s.error);

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
                    className={`px-4 py-2 text-xs font-mono uppercase tracking-wider transition-all border-b-2 ${
                      activeTab === tab.id
                        ? "text-primary border-primary bg-primary/5"
                        : "text-muted-foreground border-transparent hover:text-foreground"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              <div className="flex-1 min-h-0">
                {activeTab === "diagram" && <DiagramTab />}
                {activeTab === "metrics" && <MetricsTab />}
                {activeTab === "events" && <EventsTab />}
              </div>
            </div>
          </Panel>
        </PanelGroup>
      </div>
    </div>
  );
}
