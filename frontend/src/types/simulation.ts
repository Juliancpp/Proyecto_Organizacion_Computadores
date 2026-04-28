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

export interface SimulationResponse {
  risc?: ArchResult;
  cisc?: ArchResult;
  comparison?: Comparison;
  errors?: Partial<Record<"risc" | "cisc", string>>;
}

export interface SimulationRequest {
  code: string;
  step: boolean;
  pipeline: boolean;
  transpile?: boolean;
  risc_tcycle: number;
  cisc_tcycle: number;
  input_values?: number[];
}
