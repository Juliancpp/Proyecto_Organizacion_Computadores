import { create } from "zustand";
import type { SimulationResponse } from "@/types/simulation";

interface SimState {
  code: string;
  pipeline: boolean;
  result: SimulationResponse | null;
  loading: boolean;
  error: string | null;

  // Architecture selection
  selectedArchitecture: "auto" | "risc" | "cisc" | "x86";

  // Playback
  activeArch: "risc" | "cisc" | "x86";
  currentCycle: number;
  playing: boolean;
  speed: number; // 1, 2, 4, 8
  learningMode: boolean;
  isPausedForQuestion: boolean;

  // Input values for READ instructions
  inputValues: number[];

  // Actions
  setCode: (code: string) => void;
  setPipeline: (v: boolean) => void;
  setSelectedArchitecture: (a: "auto" | "risc" | "cisc" | "x86") => void;
  setResult: (r: SimulationResponse | null) => void;
  setLoading: (v: boolean) => void;
  setError: (e: string | null) => void;
  setActiveArch: (a: "risc" | "cisc" | "x86") => void;
  setCurrentCycle: (c: number) => void;
  setPlaying: (v: boolean) => void;
  setSpeed: (s: number) => void;
  setLearningMode: (v: boolean) => void;
  setIsPausedForQuestion: (v: boolean) => void;
  setInputValues: (v: number[]) => void;
  stepForward: () => void;
  resetPlayback: () => void;
}

const DEFAULT_CODE = `MOV R0, 5
MOV R1, 3
ADD R2, R0, R1
STORE R2, 100
LOAD R3, 100
HALT`;

export const useSimStore = create<SimState>((set, get) => ({
  code: DEFAULT_CODE,
  pipeline: false,
  result: null,
  loading: false,
  error: null,
  selectedArchitecture: "auto",
  activeArch: "risc",
  currentCycle: 0,
  playing: false,
  speed: 1,
  learningMode: true,
  isPausedForQuestion: false,
  inputValues: [],

  setCode: (code) => set({ code }),
  setPipeline: (pipeline) => set({ pipeline }),
  setSelectedArchitecture: (selectedArchitecture) => set({ selectedArchitecture }),
  setResult: (result) => {
    // Determine available architecture for playback
    let availableArch: "risc" | "cisc" | "x86" = "risc";
    if (result?.x86) {
      availableArch = "x86";
    } else if (result?.risc) {
      availableArch = "risc";
    } else if (result?.cisc) {
      availableArch = "cisc";
    }
    set({ result, activeArch: availableArch, currentCycle: 0, playing: false });
  },
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  setActiveArch: (activeArch) => set({ activeArch, currentCycle: 0, playing: false }),
  setCurrentCycle: (currentCycle) => set({ currentCycle }),
  setPlaying: (playing) => set({ playing }),
  setSpeed: (speed) => set({ speed }),
  setLearningMode: (learningMode) => set({ learningMode }),
  setIsPausedForQuestion: (isPausedForQuestion) => set({ isPausedForQuestion }),
  setInputValues: (inputValues) => set({ inputValues }),
  stepForward: () => {
    const { result, activeArch, currentCycle } = get();
    if (!result) return;
    const timeline = result[activeArch]?.timeline ?? [];
    if (currentCycle < timeline.length - 1) {
      set({ currentCycle: currentCycle + 1, isPausedForQuestion: false });
    } else {
      set({ playing: false, isPausedForQuestion: false });
    }
  },
  resetPlayback: () => set({ currentCycle: 0, playing: false, isPausedForQuestion: false }),
}));
