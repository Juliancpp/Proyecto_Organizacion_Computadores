"""
Demo program: Compute f(n) = n! + n²  for n = 5.

Expected result: 5! + 5²  =  120 + 25  =  145  (stored at MEM[100]).

The program is written in the **common dialect** accepted by
`transpile_common_to_risc_cisc`, so it runs identically on both
the RISC and CISC simulation engines after transpilation.

Instructions exercised:
    MOV    — load immediates into registers
    STORE  — save values to memory
    LOAD   — read memory into registers
    MUL    — multi-cycle integer multiplication
    ADD    — register addition
    SUB    — decrement counter
    BEQ    — conditional branch (loop termination)
    JMP    — unconditional back-branch
    HALT   — end of program

Memory layout after execution:
    MEM[10]  = n      = 5
    MEM[11]  = n²     = 25
    MEM[12]  = n!     = 120
    MEM[100] = n!+n²  = 145   ← final result
"""

PROGRAM = """\
; ----------------------------------------------------------------
; f(n) = n! + n²    for n = 5       ─ common-dialect assembly
; Expected final state:  MEM[100] = 145
;
; Register map (uses only R0-R5; leaves R6, R7 for transpiler scratch):
;   R0 = n (input)
;   R1 = factorial counter
;   R2 = factorial accumulator
;   R3 = 0 (constant for BEQ comparison)
;   R4 = 1 (decrement constant)
;   R5 = temporary for intermediate values and final sum
; ----------------------------------------------------------------

; ── Setup ─────────────────────────────────────────────────
MOV R0, 5               ; R0 = n = 5
STORE R0, 10            ; MEM[10] = n

; ── Compute n²  → MEM[11] ─────────────────────────────────
MUL R5, R0, R0          ; R5 = n * n = 25
STORE R5, 11            ; MEM[11] = n²

; ── Compute n!  (iterative loop) ──────────────────────────
LOAD R1, 10             ; R1 = n    (loop counter)
MOV R2, 1               ; R2 = 1    (factorial accumulator)
MOV R3, 0               ; R3 = 0    (loop-exit comparison)
MOV R4, 1               ; R4 = 1    (decrement constant)

FACT_LOOP:
BEQ R1, R3, FACT_DONE   ; while counter != 0
MUL R2, R2, R1          ;   accum *= counter
SUB R1, R1, R4          ;   counter--
JMP FACT_LOOP

FACT_DONE:
STORE R2, 12            ; MEM[12] = n!

; ── Compute n! + n²  → MEM[100] ───────────────────────────
LOAD R1, 11             ; R1 = n²   (reuse R1)
LOAD R2, 12             ; R2 = n!   (reuse R2)
ADD R5, R1, R2          ; R5 = n² + n!
STORE R5, 100           ; MEM[100] = final result = 145

HALT
"""

EXPECTED_FINAL_MEMORY: dict[int, int] = {
    10: 5,
    11: 25,
    12: 120,
    100: 145,
}
