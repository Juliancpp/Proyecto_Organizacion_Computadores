import { useEffect, useRef } from "react";
import Editor, { type Monaco } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { useSimStore } from "@/store/simulationStore";

export function EditorPanel() {
  const { code, setCode, result, activeArch, currentCycle } = useSimStore();
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<Monaco | null>(null);
  const decorationsRef = useRef<string[]>([]);

  // Compute the current PC from the timeline snapshot
  const timeline = result?.[activeArch]?.timeline ?? [];
  const snapshot = timeline[currentCycle];
  const currentPc = snapshot?.pc ?? -1;

  // Map PC index → source line number using parsed_instructions
  const parsedInstructions = result?.[activeArch]?.parsed_instructions?.instructions ?? [];

  useEffect(() => {
    const ed = editorRef.current;
    const monaco = monacoRef.current;
    if (!ed || !monaco) return;

    // Clear previous decorations
    decorationsRef.current = ed.deltaDecorations(decorationsRef.current, []);

    if (currentPc < 0 || currentPc >= parsedInstructions.length) return;

    const lineNumber = parsedInstructions[currentPc]?.line_number;
    if (!lineNumber) return;

    decorationsRef.current = ed.deltaDecorations([], [
      {
        range: new monaco.Range(lineNumber, 1, lineNumber, 1),
        options: {
          isWholeLine: true,
          className: "current-instruction-highlight",
          glyphMarginClassName: "current-instruction-glyph",
          overviewRuler: {
            color: "rgba(99,102,241,0.8)",
            position: monaco.editor.OverviewRulerLane.Left,
          },
        },
      },
    ]);

    // Reveal the line
    ed.revealLineInCenterIfOutsideViewport(lineNumber);
  }, [currentPc, parsedInstructions]);

  return (
    <div className="h-full flex flex-col bg-[#0d0d0f]">
      <div className="flex items-center px-3 py-1.5 border-b border-border bg-card">
        <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
          Assembly Editor
        </span>
        <span className="ml-auto text-[10px] font-mono text-muted-foreground">
          RISC / CISC
        </span>
        {currentPc >= 0 && parsedInstructions.length > 0 && (
          <span className="ml-2 text-[10px] font-mono text-primary">
            PC={currentPc}
          </span>
        )}
      </div>
      <div className="flex-1">
        <Editor
          height="100%"
          language="plaintext"
          theme="vs-dark"
          value={code}
          onChange={(v) => setCode(v || "")}
          options={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 13,
            lineHeight: 20,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            padding: { top: 12 },
            renderLineHighlight: "gutter",
            glyphMargin: true,
            folding: false,
            lineNumbersMinChars: 3,
            overviewRulerBorder: false,
            hideCursorInOverviewRuler: true,
            scrollbar: { verticalScrollbarSize: 6, horizontalScrollbarSize: 6 },
          }}
          beforeMount={(monaco) => {
            monaco.editor.defineTheme("risc-dark", {
              base: "vs-dark",
              inherit: true,
              rules: [],
              colors: {
                "editor.background": "#0d0d0f",
                "editor.lineHighlightBackground": "#ffffff08",
                "editorGutter.background": "#0d0d0f",
              },
            });
          }}
          onMount={(ed, monaco) => {
            editorRef.current = ed;
            monacoRef.current = monaco;
            monaco.editor.setTheme("risc-dark");

            // Inject highlight CSS once
            const styleId = "risc-editor-highlight";
            if (!document.getElementById(styleId)) {
              const style = document.createElement("style");
              style.id = styleId;
              style.textContent = `
                .current-instruction-highlight {
                  background: rgba(99,102,241,0.15) !important;
                  border-left: 2px solid rgba(99,102,241,0.8);
                }
                .current-instruction-glyph::before {
                  content: "▶";
                  color: rgba(99,102,241,0.9);
                  font-size: 10px;
                  margin-left: 2px;
                }
              `;
              document.head.appendChild(style);
            }
          }}
        />
      </div>
    </div>
  );
}
