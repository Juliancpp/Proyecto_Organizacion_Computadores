#!/usr/bin/env python3
"""
Standalone runner for the x86-64 simulator.

Usage:
    python -m simulator.x86.run

Runs the mandatory bubble sort test program and prints results.
"""

from __future__ import annotations

import sys
import os

# Add backend to path so imports work when run standalone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from simulator.x86.parser import parse_x86
from simulator.x86.engine import execute_x86, read_array_from_memory


BUBBLE_SORT_PROGRAM = """\
section .data
    array dd 34, 7, 23, 32, 5, 62
    n equ ($ - array) / 4

section .text
    global _start

_start:
    mov r8, n
    dec r8

outer_loop:
    mov rcx, 0
    mov r9, 0

inner_loop:
    mov eax, [array + rcx*4]
    mov ebx, [array + rcx*4 + 4]

    cmp eax, ebx
    jle next_step

    mov [array + rcx*4], ebx
    mov [array + rcx*4 + 4], eax
    mov r9, 1

next_step:
    inc rcx
    cmp rcx, r8
    jl inner_loop

    cmp r9, 0
    je end_sort

    dec r8
    jnz outer_loop

end_sort:
    mov rax, 60
    xor rdi, rdi
    syscall
"""


def main() -> None:
    print("=" * 60)
    print("x86-64 Simulator — Bubble Sort Test")
    print("=" * 60)

    # Parse
    print("\n[1] Parsing program...")
    result = parse_x86(BUBBLE_SORT_PROGRAM)
    print(f"    Instructions: {len(result.instructions)}")
    print(f"    Labels:       {result.labels}")
    print(f"    Data symbols: {list(result.data_symbols.keys())}")
    print(f"    Constants:    {result.constants}")

    # Execute
    print("\n[2] Executing...")
    state = execute_x86(result)
    print(f"    Cycles:  {state.cycles}")
    print(f"    Halted:  {state.halted}")

    # Read sorted array
    print("\n[3] Results:")
    if "array" in result.data_symbols:
        sorted_array = read_array_from_memory(state, result.data_symbols["array"])
        print(f"    Sorted array: {sorted_array}")

        expected = [5, 7, 23, 32, 34, 62]
        if sorted_array == expected:
            print("    ✅ CORRECT — matches expected output")
        else:
            print(f"    ❌ INCORRECT — expected {expected}")
    else:
        print("    ⚠️  No 'array' symbol found in .data")

    # Register state
    print("\n[4] Register state:")
    for reg, val in state.registers.items():
        if val != 0:
            print(f"    {reg:4s} = {val}")

    # FLAGS
    print(f"\n    FLAGS: {state.flags}")
    print("=" * 60)


if __name__ == "__main__":
    main()
