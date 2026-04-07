"""
Custom exception hierarchy for the CPU simulator.

Using specific exceptions makes error-handling in the API layer cleaner
and lets us return meaningful HTTP status codes + messages.
"""


class SimulatorError(Exception):
    """Base class for all simulator errors."""


class ParseError(SimulatorError):
    """Raised when the assembly parser encounters invalid syntax."""

    def __init__(self, message: str, line_number: int | None = None) -> None:
        self.line_number = line_number
        detail = f"Line {line_number}: {message}" if line_number else message
        super().__init__(detail)


class ExecutionError(SimulatorError):
    """Raised when a runtime error occurs during simulation."""

    def __init__(self, message: str, pc: int | None = None) -> None:
        self.pc = pc
        detail = f"PC={pc}: {message}" if pc is not None else message
        super().__init__(detail)


class InvalidInstructionError(ParseError):
    """Raised when an unknown or malformed instruction is encountered."""


class InvalidRegisterError(ExecutionError):
    """Raised when a non-existent register is referenced."""


class InvalidMemoryAccessError(ExecutionError):
    """Raised on out-of-bounds memory access."""
