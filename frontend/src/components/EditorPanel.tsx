import Editor from "@monaco-editor/react";
import { useSimStore } from "@/store/simulationStore";

export function EditorPanel() {
  const { code, setCode } = useSimStore();

  return (
    <div className="h-full flex flex-col bg-[#0d0d0f]">
      <div className="flex items-center px-3 py-1.5 border-b border-border bg-card">
        <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
          Assembly Editor
        </span>
        <span className="ml-auto text-[10px] font-mono text-muted-foreground">
          RISC / CISC
        </span>
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
            glyphMargin: false,
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
          onMount={(editor, monaco) => {
            monaco.editor.setTheme("risc-dark");
          }}
        />
      </div>
    </div>
  );
}
