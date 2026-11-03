"""Progress events an agent run reports while it works (the CLI's live trace)."""

from typing import Protocol

from utils.agent_result import ToolCallRecord
from utils.plan import Plan


class AgentObserver(Protocol):
    """Receives the plan before execution starts and each tool call as it finishes."""

    def on_plan(self, plan: Plan) -> None: ...

    def on_tool_call(self, record: ToolCallRecord) -> None: ...


class SilentObserver:
    """An `AgentObserver` that ignores every event."""

    def on_plan(self, plan: Plan) -> None:
        pass

    def on_tool_call(self, record: ToolCallRecord) -> None:
        pass
