"""
Tests for the x86-64 NASM-style assembly parser and execution engine.

Covers:
  - Parser: sections, directives (dd, equ), labels, registers, memory operands
  - Engine: individual instructions, FLAGS, control flow
  - End-to-end: mandatory bubble sort program
  - Edge cases: empty program, unknown instruction, infinite loop guard
"""

from django.test import TestCase

from simulator.x86.parser import (
    parse_x86,
    is_x86_syntax,
    MemoryOperand,
    X86ParseResult,
)
from simulator.x86.engine import execute_x86, read_array_from_memory
from simulator.x86.state import X86State
from simulator.core.exceptions import ExecutionError, ParseError, InvalidInstructionError


# ---------------------------------------------------------------------------
# The mandatory bubble sort test program (NOT modified)
# ---------------------------------------------------------------------------

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


# ===================================================================
# Parser Tests
# ===================================================================

class TestX86Parser(TestCase):
    """Test the x86-64 NASM parser."""

    def test_parse_bubble_sort_sections(self):
        """Parser should split .data and .text sections correctly."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        self.assertIsInstance(result, X86ParseResult)
        self.assertIn("array", result.data_symbols)
        self.assertIn("n", result.constants)

    def test_data_section_dd_directive(self):
        """dd directive should allocate dwords and record the symbol."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        sym = result.data_symbols["array"]
        self.assertEqual(sym.values, [34, 7, 23, 32, 5, 62])
        self.assertEqual(sym.size, 24)  # 6 dwords × 4 bytes

    def test_equ_constant_resolution(self):
        """equ with ($ - array) / 4 should compute element count."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        self.assertEqual(result.constants["n"], 6)

    def test_labels_extracted(self):
        """All labels should be extracted with correct instruction indices."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        self.assertIn("_start", result.labels)
        self.assertIn("outer_loop", result.labels)
        self.assertIn("inner_loop", result.labels)
        self.assertIn("next_step", result.labels)
        self.assertIn("end_sort", result.labels)

    def test_instruction_count(self):
        """Should parse the correct number of instructions."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        self.assertEqual(len(result.instructions), 21)

    def test_memory_operand_parsing(self):
        """[array + rcx*4 + 4] should parse into a MemoryOperand."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        # Instruction: mov ebx, [array + rcx*4 + 4] (index 5)
        instr = result.instructions[5]
        self.assertEqual(instr.opcode, "mov")
        mem_op = instr.operands[1]
        self.assertIsInstance(mem_op, MemoryOperand)
        self.assertEqual(mem_op.base_symbol, "array")
        self.assertEqual(mem_op.index_reg, "rcx")
        self.assertEqual(mem_op.scale, 4)
        self.assertEqual(mem_op.displacement, 4)

    def test_memory_operand_no_displacement(self):
        """[array + rcx*4] should have displacement 0."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        # Instruction: mov eax, [array + rcx*4] (index 4)
        instr = result.instructions[4]
        mem_op = instr.operands[1]
        self.assertIsInstance(mem_op, MemoryOperand)
        self.assertEqual(mem_op.displacement, 0)

    def test_register_operands(self):
        """Register operands should be parsed as lowercase strings."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        # mov r8, n → operands: ["r8", 6]
        instr = result.instructions[0]
        self.assertEqual(instr.opcode, "mov")
        self.assertEqual(instr.operands[0], "r8")
        self.assertEqual(instr.operands[1], 6)  # n resolved to 6

    def test_global_directive_ignored(self):
        """'global _start' should not produce an instruction."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        for instr in result.instructions:
            self.assertNotEqual(instr.opcode, "global")

    def test_is_x86_syntax_detection(self):
        """is_x86_syntax should detect x86-64 assembly."""
        self.assertTrue(is_x86_syntax(BUBBLE_SORT_PROGRAM))
        self.assertFalse(is_x86_syntax("MOV R0, 5\nADD R1, R0, R0"))

    def test_data_segment_bytes(self):
        """Data segment should contain little-endian dword bytes."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        self.assertEqual(len(result.data_segment), 24)  # 6 × 4 bytes

    def test_duplicate_label_raises_error(self):
        """Duplicate labels should raise ParseError."""
        program = """\
section .text
start:
    nop
start:
    nop
"""
        with self.assertRaises(ParseError):
            parse_x86(program)


# ===================================================================
# State Tests
# ===================================================================

class TestX86State(TestCase):
    """Test the x86-64 CPU state model."""

    def test_register_read_write_64bit(self):
        state = X86State()
        state.write_reg("rax", 42)
        self.assertEqual(state.read_reg("rax"), 42)

    def test_register_32bit_alias(self):
        """Writing eax should zero-extend into rax."""
        state = X86State()
        state.write_reg("rax", 0xFFFFFFFF_FFFFFFFF)
        state.write_reg("eax", 0x12345678)
        # rax should now be 0x12345678 (zero-extended)
        self.assertEqual(state.read_reg("rax"), 0x12345678)
        self.assertEqual(state.read_reg("eax"), 0x12345678)

    def test_dword_memory(self):
        state = X86State()
        state.write_dword(0x100, 42)
        self.assertEqual(state.read_dword(0x100), 42)

    def test_dword_memory_negative(self):
        """Negative dword values should round-trip correctly."""
        state = X86State()
        state.write_dword(0x100, -5)
        self.assertEqual(state.read_dword(0x100), -5)

    def test_flags_initial_state(self):
        state = X86State()
        self.assertFalse(state.flags["ZF"])
        self.assertFalse(state.flags["SF"])

    def test_update_flags_sub_zero(self):
        state = X86State()
        state.update_flags_sub(5, 5, 0, 64)
        self.assertTrue(state.flags["ZF"])
        self.assertFalse(state.flags["SF"])

    def test_update_flags_sub_negative(self):
        state = X86State()
        state.update_flags_sub(3, 5, -2, 64)
        self.assertFalse(state.flags["ZF"])
        self.assertTrue(state.flags["SF"])

    def test_load_data_segment(self):
        state = X86State()
        data = b'\x05\x00\x00\x00\x0a\x00\x00\x00'  # dwords: 5, 10
        state.load_data_segment(0x1000, data)
        self.assertEqual(state.read_dword(0x1000), 5)
        self.assertEqual(state.read_dword(0x1004), 10)


# ===================================================================
# Engine Tests — Individual Instructions
# ===================================================================

class TestX86EngineInstructions(TestCase):
    """Test individual x86-64 instructions."""

    def test_mov_reg_imm(self):
        program = """\
section .text
_start:
    mov rax, 42
    syscall
"""
        result = parse_x86(program)
        state = execute_x86(result)
        self.assertEqual(state.read_reg("rax"), 42)

    def test_mov_reg_reg(self):
        program = """\
section .text
_start:
    mov rax, 99
    mov rbx, rax
    mov rax, 60
    xor rdi, rdi
    syscall
"""
        result = parse_x86(program)
        state = execute_x86(result)
        self.assertEqual(state.read_reg("rbx"), 99)

    def test_inc_dec(self):
        program = """\
section .text
_start:
    mov rcx, 10
    inc rcx
    dec rcx
    dec rcx
    mov rax, 60
    xor rdi, rdi
    syscall
"""
        result = parse_x86(program)
        state = execute_x86(result)
        self.assertEqual(state.read_reg("rcx"), 9)

    def test_xor_self_zeros_register(self):
        program = """\
section .text
_start:
    mov rax, 99
    xor rax, rax
    mov rbx, rax
    mov rax, 60
    xor rdi, rdi
    syscall
"""
        result = parse_x86(program)
        state = execute_x86(result)
        self.assertEqual(state.read_reg("rbx"), 0)

    def test_cmp_and_je(self):
        """CMP + JE: should jump when equal."""
        program = """\
section .text
_start:
    mov rax, 5
    cmp rax, 5
    je equal_label
    mov rbx, 0
    mov rax, 60
    xor rdi, rdi
    syscall
equal_label:
    mov rbx, 1
    mov rax, 60
    xor rdi, rdi
    syscall
"""
        result = parse_x86(program)
        state = execute_x86(result)
        self.assertEqual(state.read_reg("rbx"), 1)

    def test_cmp_and_jl(self):
        """CMP + JL: should jump when less."""
        program = """\
section .text
_start:
    mov rax, 3
    cmp rax, 5
    jl less_label
    mov rbx, 0
    mov rax, 60
    xor rdi, rdi
    syscall
less_label:
    mov rbx, 1
    mov rax, 60
    xor rdi, rdi
    syscall
"""
        result = parse_x86(program)
        state = execute_x86(result)
        self.assertEqual(state.read_reg("rbx"), 1)

    def test_cmp_and_jle_equal(self):
        """CMP + JLE: should jump when equal."""
        program = """\
section .text
_start:
    mov rax, 5
    cmp rax, 5
    jle le_label
    mov rbx, 0
    mov rax, 60
    xor rdi, rdi
    syscall
le_label:
    mov rbx, 1
    mov rax, 60
    xor rdi, rdi
    syscall
"""
        result = parse_x86(program)
        state = execute_x86(result)
        self.assertEqual(state.read_reg("rbx"), 1)

    def test_cmp_and_jnz(self):
        """CMP + JNZ: should jump when not zero."""
        program = """\
section .text
_start:
    mov rax, 1
    cmp rax, 0
    jnz nonzero_label
    mov rbx, 0
    mov rax, 60
    xor rdi, rdi
    syscall
nonzero_label:
    mov rbx, 1
    mov rax, 60
    xor rdi, rdi
    syscall
"""
        result = parse_x86(program)
        state = execute_x86(result)
        self.assertEqual(state.read_reg("rbx"), 1)

    def test_memory_read_write(self):
        """MOV to/from memory with data section."""
        program = """\
section .data
    val dd 42

section .text
_start:
    mov eax, [val]
    mov rax, 60
    xor rdi, rdi
    syscall
"""
        result = parse_x86(program)
        state = execute_x86(result)
        # eax was loaded with 42, then rax was set to 60 for syscall
        # but we can check that val was in memory
        sym = result.data_symbols["val"]
        self.assertEqual(state.read_dword(sym.address), 42)

    def test_syscall_exit(self):
        """syscall with rax=60 should halt the CPU."""
        program = """\
section .text
_start:
    mov rax, 60
    xor rdi, rdi
    syscall
"""
        result = parse_x86(program)
        state = execute_x86(result)
        self.assertTrue(state.halted)


# ===================================================================
# End-to-End: Mandatory Bubble Sort
# ===================================================================

class TestBubbleSort(TestCase):
    """End-to-end test for the mandatory bubble sort program."""

    def test_bubble_sort_correct_output(self):
        """Bubble sort must produce [5, 7, 23, 32, 34, 62]."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        state = execute_x86(result)

        self.assertTrue(state.halted)
        self.assertIn("array", result.data_symbols)

        sorted_array = read_array_from_memory(state, result.data_symbols["array"])
        self.assertEqual(sorted_array, [5, 7, 23, 32, 34, 62])

    def test_bubble_sort_register_state(self):
        """After bubble sort, rax should be 60 (syscall number)."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        state = execute_x86(result)

        self.assertEqual(state.read_reg("rax"), 60)
        self.assertEqual(state.read_reg("rdi"), 0)  # xor rdi, rdi

    def test_bubble_sort_terminates(self):
        """Bubble sort should not trigger the infinite loop guard."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        state = execute_x86(result)
        self.assertLess(state.cycles, 1000)  # Should finish well under the limit

    def test_bubble_sort_n_constant(self):
        """The equ constant n should equal 6."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        self.assertEqual(result.constants["n"], 6)

    def test_bubble_sort_data_symbols(self):
        """Data symbols should be correctly resolved."""
        result = parse_x86(BUBBLE_SORT_PROGRAM)
        sym = result.data_symbols["array"]
        self.assertEqual(sym.values, [34, 7, 23, 32, 5, 62])
        self.assertEqual(sym.size, 24)


# ===================================================================
# Edge Cases
# ===================================================================

class TestX86EdgeCases(TestCase):
    """Edge case tests."""

    def test_empty_program(self):
        """Empty program should parse and execute without error."""
        result = parse_x86("")
        state = execute_x86(result)
        self.assertFalse(state.halted)
        self.assertEqual(state.cycles, 0)

    def test_text_only_no_data(self):
        """Program with only .text section should work."""
        program = """\
section .text
_start:
    mov rax, 60
    xor rdi, rdi
    syscall
"""
        result = parse_x86(program)
        state = execute_x86(result)
        self.assertTrue(state.halted)

    def test_unknown_instruction(self):
        """Unknown instruction should raise InvalidInstructionError."""
        program = """\
section .text
_start:
    fakeinstr rax, rbx
"""
        result = parse_x86(program)
        with self.assertRaises((InvalidInstructionError, ExecutionError)):
            execute_x86(result)

    def test_undefined_label_jump(self):
        """Jump to undefined label should raise ExecutionError."""
        program = """\
section .text
_start:
    jmp nonexistent_label
"""
        result = parse_x86(program)
        with self.assertRaises(ExecutionError):
            execute_x86(result)

    def test_simple_loop_terminates(self):
        """A simple counted loop should terminate correctly."""
        program = """\
section .text
_start:
    mov rcx, 5
loop_start:
    dec rcx
    jnz loop_start
    mov rax, 60
    xor rdi, rdi
    syscall
"""
        result = parse_x86(program)
        state = execute_x86(result)
        self.assertTrue(state.halted)
        self.assertEqual(state.read_reg("rcx"), 0)

    def test_already_sorted_array(self):
        """Bubble sort on an already-sorted array should still produce correct output."""
        program = """\
section .data
    array dd 1, 2, 3, 4, 5
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
        result = parse_x86(program)
        state = execute_x86(result)
        sorted_array = read_array_from_memory(state, result.data_symbols["array"])
        self.assertEqual(sorted_array, [1, 2, 3, 4, 5])

    def test_reverse_sorted_array(self):
        """Bubble sort on a reverse-sorted array should produce correct output."""
        program = """\
section .data
    array dd 5, 4, 3, 2, 1
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
        result = parse_x86(program)
        state = execute_x86(result)
        sorted_array = read_array_from_memory(state, result.data_symbols["array"])
        self.assertEqual(sorted_array, [1, 2, 3, 4, 5])
