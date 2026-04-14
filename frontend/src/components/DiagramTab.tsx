import { useEffect, useMemo, useRef, useState } from "react";
import { useSimStore } from "@/store/simulationStore";
import { buildGuidedSteps } from "@/lib/cpu-model";
import { ControlPanel } from "@/components/diagram/ControlPanel";
import { StatePanel } from "@/components/diagram/StatePanel";
import { CPUView } from "@/components/diagram/CPUView";
import { ExplanationPanel } from "@/components/diagram/ExplanationPanel";
import { ModeSwitcher } from "@/components/diagram/ModeSwitcher";
import { InteractiveQuizPanel } from "@/components/diagram/InteractiveQuizPanel";
import { DecisionFlowPanel } from "@/components/diagram/DecisionFlowPanel";
import { BeforeAfterPanel } from "@/components/diagram/BeforeAfterPanel";
import { InstructionSummaryPanel } from "@/components/diagram/InstructionSummaryPanel";

export function DiagramTab() {
  const { result, activeArch, playing, speed, learningMode, setLearningMode, isPausedForQuestion, setIsPausedForQuestion } = useSimStore();
  const { setPlaying, resetPlayback, setActiveArch, setCurrentCycle } = useSimStore();
  const intervalRef = useRef<number | null>(null);
  const [guidedIndex, setGuidedIndex] = useState(0);

  const timeline = result?.[activeArch]?.timeline || [];
  const steps = useMemo(() => buildGuidedSteps(activeArch, timeline), [activeArch, timeline]);
  const currentStep = steps[guidedIndex];

  // Pause automatically if learningMode is on and a quiz is active
  useEffect(() => {
    if (learningMode && currentStep?.quiz && playing) {
       setIsPausedForQuestion(true);
    }
  }, [guidedIndex, currentStep, learningMode, playing, setIsPausedForQuestion]);

  useEffect(() => {
    setGuidedIndex(0);
    setCurrentCycle(0);
    setPlaying(false);
    setIsPausedForQuestion(false);
  }, [activeArch, timeline.length, setCurrentCycle, setPlaying, setIsPausedForQuestion]);

  useEffect(() => {
    if (playing && steps.length > 0 && !isPausedForQuestion) {
      const delay = 4000 / speed;
      intervalRef.current = window.setInterval(() => {
        setGuidedIndex((prev) => {
          const next = Math.min(prev + 1, steps.length - 1);
          const cycleIndex = Math.max(0, timeline.findIndex((c) => c.cycle === steps[next].cycle));
          setCurrentCycle(cycleIndex);
          if (next === steps.length - 1) setPlaying(false);
          return next;
        });
      }, delay);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [playing, steps, timeline, setCurrentCycle, setPlaying, speed, isPausedForQuestion]);

  const nextStep = () => {
    setGuidedIndex((prev) => {
      const next = Math.min(prev + 1, Math.max(0, steps.length - 1));
      const cycleIndex = Math.max(0, timeline.findIndex((c) => c.cycle === steps[next]?.cycle));
      setCurrentCycle(cycleIndex);
      return next;
    });
  };

  const resetSteps = () => {
    resetPlayback();
    setGuidedIndex(0);
    setPlaying(false);
    setIsPausedForQuestion(false);
  };

  const showContent = !learningMode || !isPausedForQuestion || !currentStep?.quiz;

  return (
    <div className="h-full flex flex-col bg-diagram-bg">
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {!result ? (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm font-mono">
            Run a simulation to see the didactic diagram
          </div>
        ) : (
          <div className="max-w-6xl mx-auto space-y-4">
            <div className="flex justify-between items-center bg-card p-2 rounded border border-border shadow-sm">
              <ModeSwitcher
                activeArch={activeArch}
                setActiveArch={setActiveArch}
                riscAvailable={Boolean(result?.risc)}
                ciscAvailable={Boolean(result?.cisc)}
              />
              <label className="flex items-center gap-2 text-sm font-mono text-primary font-semibold mr-4 cursor-pointer hover:text-neon-cyan transition-colors">
                <input 
                  type="checkbox" 
                  checked={learningMode} 
                  onChange={(e) => setLearningMode(e.target.checked)} 
                  className="accent-primary w-4 h-4" 
                />
                🎓 Learning Mode
              </label>
            </div>
            
            <ControlPanel
              isPlaying={playing}
              canStep={steps.length > 0 && guidedIndex < steps.length - 1}
              cycle={currentStep?.cycle ?? 0}
              onNextStep={nextStep}
              onTogglePlay={() => setPlaying(!playing)}
              onReset={resetSteps}
            />

            {learningMode && currentStep?.quiz && isPausedForQuestion && (
              <InteractiveQuizPanel
                quiz={currentStep.quiz}
                onAnswered={() => setIsPausedForQuestion(false)}
              />
            )}

            <div className={`transition-all duration-700 ease-in-out space-y-3 ${showContent ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-4 pointer-events-none h-0 overflow-hidden"}`}>
              <ExplanationPanel step={currentStep} />
              
              {currentStep?.beforeState && currentStep?.afterState && (
                <BeforeAfterPanel 
                  beforeState={currentStep.beforeState} 
                  afterState={currentStep.afterState} 
                  operationLabel={currentStep.operationLabel} 
                />
              )}

              <div className="flex flex-col gap-4">
                {/* TOP SECTION: Decision Tree | Current State */}
                <div className="flex flex-col lg:flex-row gap-3 items-stretch">
                  {currentStep?.decisionFlow && (
                    <div className="flex-1 min-w-0 flex flex-col">
                      <DecisionFlowPanel flow={currentStep.decisionFlow} />
                    </div>
                  )}
                  <div className="flex-1 min-w-0 flex flex-col">
                    <StatePanel step={currentStep} />
                  </div>
                </div>

                {/* BOTTOM SECTION: Arquitectura Global */}
                <div className="w-full">
                  <CPUView activeArch={activeArch} step={currentStep} stepList={steps} />
                </div>
              </div>

              {currentStep?.microSummary && (
                <div className="col-span-full">
                  <InstructionSummaryPanel summary={currentStep.microSummary} />
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
