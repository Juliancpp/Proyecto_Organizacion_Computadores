"""
Event model for cycle-by-cycle CPU simulation.

Each CPU cycle produces one or more events that describe what hardware
components were activated and what they did.  Events form the raw data
that the frontend renders into a visual timeline.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Component enum — restricts the set of valid hardware components
# ---------------------------------------------------------------------------

class Component(str, Enum):
    """Hardware components that can generate events."""
    ALU = "ALU"
    MEMORY = "MEMORY"
    PC = "PC"
    REGISTERS = "REGISTERS"
    CONTROL = "CONTROL"
    BUS = "BUS"


# ---------------------------------------------------------------------------
# Event class
# ---------------------------------------------------------------------------

class Event:
    """
    Represents a single hardware event within one CPU cycle.

    Attributes:
        component:  Which hardware unit performed the action.
        action:     Human-readable description of what happened.
        inputs:     Operand values consumed by the component.
        output:     Result produced by the component (if any).
        meta:       Optional dictionary with extra diagnostic info.
    """

    __slots__ = ("component", "action", "inputs", "output", "meta")

    def __init__(
        self,
        component: Component | str,
        action: str,
        inputs: list[Any] | None = None,
        output: Any = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        # Accept both Component enum and raw strings
        if isinstance(component, str) and not isinstance(component, Component):
            component = Component(component)
        self.component = component
        self.action = action
        self.inputs = inputs or []
        self.output = output
        self.meta = meta or {}

    # ---- serialization -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the event for JSON output."""
        result: dict[str, Any] = {
            "component": self.component.value,
            "action": self.action,
            "inputs": self.inputs,
            "output": self.output,
        }
        if self.meta:
            result["meta"] = self.meta
        return result

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Event({self.component.value}, {self.action!r}, "
            f"inputs={self.inputs}, output={self.output})"
        )
