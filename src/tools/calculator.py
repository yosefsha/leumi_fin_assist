"""The `calculate` tool: exact, visible arithmetic for the agent."""

import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tools.arithmetic import MAX_EXPRESSION_LENGTH, InvalidExpressionError, evaluate_arithmetic
from tools.registry import ToolOutput
from utils.prompts import load_tool_description


class CalculateArgs(BaseModel):
    """The model-supplied arguments of a `calculate` call."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    expression: str = Field(
        min_length=1,
        max_length=MAX_EXPRESSION_LENGTH,
        description="The arithmetic expression to evaluate, e.g. '34550 / 416161 * 100'.",
    )


class CalculateTool:
    """Evaluates an arithmetic expression and returns `{expression, result}` as JSON."""

    def __init__(self) -> None:
        self._description = load_tool_description(self.name)
        self._input_schema = CalculateArgs.model_json_schema()

    @property
    def name(self) -> str:
        return "calculate"

    @property
    def description(self) -> str:
        return self._description

    @property
    def input_schema(self) -> Mapping[str, Any]:
        return self._input_schema

    def run(self, args: Mapping[str, Any]) -> ToolOutput:
        """Evaluate `args["expression"]`; invalid arguments or expressions yield an error result."""
        try:
            expression = CalculateArgs.model_validate(args).expression
        except ValidationError as error:
            problems = "; ".join(
                f"{'.'.join(map(str, issue['loc'])) or 'arguments'}: {issue['msg']}"
                for issue in error.errors()
            )
            return ToolOutput(content=f"Invalid arguments: {problems}.", is_error=True)
        try:
            result = evaluate_arithmetic(expression)
        except InvalidExpressionError as error:
            return ToolOutput(content=str(error), is_error=True)
        return ToolOutput(content=json.dumps({"expression": expression, "result": result}))
