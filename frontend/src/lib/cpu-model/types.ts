export type ControlSignals = {
  RegWrite: 0 | 1;
  MemRead: 0 | 1;
  MemWrite: 0 | 1;
  ALUOp: string;
  ALUSrc: 0 | 1;
};

export type CiscMicroRecord = {
  cycle: number;
  text: string;
  idx?: number;
  total?: number;
};
