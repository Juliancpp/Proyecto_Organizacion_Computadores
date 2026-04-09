import { useState, useEffect } from "react";
import type { Quiz } from "@/lib/cpu-model/guidedExecution";

interface InteractiveQuizPanelProps {
  quiz?: Quiz;
  onAnswered: () => void;
}

export function InteractiveQuizPanel({ quiz, onAnswered }: InteractiveQuizPanelProps) {
  const [selected, setSelected] = useState<string | null>(null);

  // Reset when quiz changes
  useEffect(() => {
    setSelected(null);
  }, [quiz]);

  if (!quiz) return null;

  const handleSelect = (option: string) => {
    if (selected) return; // Prevent changing answer
    setSelected(option);
    setTimeout(() => {
      onAnswered();
    }, 2000); // Wait 2s to show explanation before moving on
  };

  const isCorrect = selected === quiz.answer;

  return (
    <div className="rounded border border-primary/50 bg-primary/5 p-4 my-2 shadow-[0_0_10px_rgba(6,182,212,0.1)]">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xl">🧠</span>
        <h3 className="text-sm font-semibold text-primary uppercase tracker-wider">Interactive Thinking Mode</h3>
      </div>
      <p className="text-sm text-foreground mb-4 font-medium">{quiz.question}</p>
      
      <div className="space-y-2">
        {quiz.options.map((opt) => {
          let btnClass = "border-border hover:bg-white/5";
          if (selected) {
            if (opt === quiz.answer) btnClass = "border-neon-green bg-neon-green/10 text-neon-green";
            else if (opt === selected) btnClass = "border-red-500 bg-red-500/10 text-red-500";
            else btnClass = "opacity-50 border-border";
          }

          return (
            <button
              key={opt}
              onClick={() => handleSelect(opt)}
              disabled={selected !== null}
              className={`w-full text-left px-3 py-2 rounded border text-sm transition-colors ${btnClass}`}
            >
              {opt}
            </button>
          );
        })}
      </div>

      {selected && (
        <div className={`mt-4 p-3 rounded text-xs leading-relaxed ${isCorrect ? 'bg-neon-green/10 text-neon-green border border-neon-green/30' : 'bg-red-500/10 text-red-400 border border-red-500/30'}`}>
          <p className="font-semibold mb-1">{isCorrect ? '✓ Correct!' : '✗ Not quite.'}</p>
          <p>{quiz.explanation}</p>
        </div>
      )}
    </div>
  );
}
