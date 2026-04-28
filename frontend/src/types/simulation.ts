export type ComponentName = "CONTROL" | "PC" | "REGISTERS" | "ALU" | "BUS" | "MEMORY";
export type PipelineStage = "IF" | "ID" | "EX" | "MEM" | "WB";

export interface EventMeta {
  pipeline_stage?: PipelineStage;
  micro_op?: boolean;
  micro_op_index?: number;
  total_micro_ops?: number;
  branch_taken?: boolean;
  stall?: boolean;
  penalty_cycles?: number;
  instruction?: string;
}

export interface SimEvent {
  component: ComponentName;
  action: string;
  inputs: any[];
  output: any;
  meta?: EventMeta;
}

export interface TimelineCycle {
  cycle: number;
  events: SimEvent[];
}

export interface Metrics {
  instruction_count: number;
  total_cycles: number;
  cpi: number;
  t_cycle_ns: number;
  cpu_time_ns: number;
  cpu_time_us: number;
}

export interface FinalState {
  pc: number;
  registers: number[];
  memory: Record<string, number>;
  cycles: number;
  halted: boolean;
  output_log: OutputEntry[];
}

export interface OutputEntry {
  cycle: number;
  type: "register" | "memory" | "string";
  value: string;
  label?: string;
}

export interface ArchResult {
  timeline: TimelineCycle[];
  metrics: Metrics;
  final_state: FinalState;
  output_log: OutputEntry[];
}

export interface Comparison {
  speedup_risc_over_cisc: number;
  cycle_ratio: number;
  analysis: string;
}

export interface X86Result {
  timeline: TimelineCycle[];
  final_state: {
    pc: number;
    registers: Record<string, number>;
    flags: Record<string, boolean>;
    halted: boolean;
    cycles: number;
    output_log?: OutputEntry[];
  };
  parsed_instructions?: {
    instructions: any[];
    labels?: Record<string, number>;
    data_symbols?: Record<string, any>;
    constants?: Record<string, number>;
  };
  arrays: Record<string, number[]>;
  constants: Record<string, number>;
  cycles: number;
  output_log: OutputEntry[];
}

export interface SimulationResponse {
  risc?: ArchResult;
  cisc?: ArchResult;
  comparison?: Comparison;
  x86?: X86Result;
  errors?: Partial<Record<"risc" | "cisc" | "x86", string>>;
  error?: boolean;
  message?: string;
  details?: Record<string, string>;
}

export interface SimulationRequest {
  code: string;
  step: boolean;
  pipeline: boolean;
  transpile?: boolean;
  architecture?: "risc" | "cisc" | "x86" | "auto";
  risc_tcycle?: number;
  cisc_tcycle?: number;
  input_values?: number[];
}
