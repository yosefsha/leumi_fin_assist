"""The `Tool` contract and the registry the agent loop dispatches tool calls through."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from anthropic.types import ToolParam

from utils.passage import Passage
from utils.web_result import WebResult

# Anthropic's constraint on tool names.
_TOOL_NAME = re.compile(r"[a-zA-Z0-9_-]{1,64}")


type Source = Passage | WebResult
"""Something a tool returns that the answer can cite: a Filing Passage or a web result."""


@dataclass(frozen=True)
class ToolOutput:
    """The result of one tool call, returned to the model as a `tool_result` block.

    `content` is what the tool says about the call (what was searched, a "nothing
    found" message, an outline of related Passages, a computed value, an error).
    `sources` are the citable Passages or web results it found. The agent loop
    registers each source with the per-query Citation registry and shows it to the
    model under its citation ID after `content`, so a tool never invents or sees an ID.
    An error result has no sources.
    """

    content: str
    is_error: bool = False
    sources: tuple[Source, ...] = ()

    def __post_init__(self) -> None:
        if self.is_error and self.sources:
            raise ValueError("An error ToolOutput cannot carry sources.")


class Tool(Protocol):
    """A capability the agent can call by name.

    `run` receives the model-supplied arguments, validates them against
    `input_schema`, and reports expected failures (bad arguments, an unavailable
    source, nothing found) as a `ToolOutput` with `is_error=True` rather than raising.
    """

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def input_schema(self) -> Mapping[str, Any]: ...

    def run(self, args: Mapping[str, Any]) -> ToolOutput: ...


class DuplicateToolError(ValueError):
    """A tool with the same name is already registered."""


class ToolRegistry:
    """Holds the agent's tools, describes them to the model, and dispatches calls by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Add `tool`. Raises `ValueError` for an invalid name or a name already registered."""
        if not _TOOL_NAME.fullmatch(tool.name):
            raise ValueError(
                f"Invalid tool name {tool.name!r}: use 1-64 letters, digits, '_' or '-'."
            )
        if tool.name in self._tools:
            raise DuplicateToolError(f"Tool {tool.name!r} is already registered.")
        self._tools[tool.name] = tool

    def definitions(self) -> list[ToolParam]:
        """Return the Anthropic Messages API `tools` definitions, in registration order."""
        return [
            ToolParam(
                name=tool.name,
                description=tool.description,
                input_schema=dict(tool.input_schema),
            )
            for tool in self._tools.values()
        ]

    def dispatch(self, name: str, args: Mapping[str, Any]) -> ToolOutput:
        """Run the tool called `name`; an unknown name yields an error result, not an exception."""
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(sorted(self._tools)) or "none"
            return ToolOutput(
                content=f"Unknown tool {name!r}. Available tools: {available}.",
                is_error=True,
            )
        return tool.run(args)
