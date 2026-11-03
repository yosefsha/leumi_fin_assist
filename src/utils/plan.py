"""The Plan: the planner's tool-by-tool approach to a question (Bonus 3)."""

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlanStep(BaseModel):
    """One step of a Plan: the tool to call and why."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    tool: str = Field(min_length=1)
    purpose: str = Field(min_length=1)


class Plan(BaseModel):
    """The ordered steps the planner proposes. The executor treats them as guidance.

    An empty Plan means the planner produced no usable plan; the executor then
    works from the question alone.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    steps: tuple[PlanStep, ...] = ()

    def numbered(self) -> str:
        """The steps as `1. <tool> — <purpose>` lines."""
        return "\n".join(
            f"{n}. {step.tool} — {step.purpose}" for n, step in enumerate(self.steps, 1)
        )

    @staticmethod
    def json_schema(tool_names: Sequence[str]) -> dict[str, Any]:
        """The structured-output schema for a Plan whose steps use only `tool_names`."""
        return {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool": {"type": "string", "enum": list(tool_names)},
                            "purpose": {"type": "string"},
                        },
                        "required": ["tool", "purpose"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["steps"],
            "additionalProperties": False,
        }
