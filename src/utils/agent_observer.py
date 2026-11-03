"""Progress events an agent run reports while it works (the CLI's live trace)."""

from typing import Protocol

from utils.agent_result import EvidenceCheck, ToolCallRecord
from utils.plan import Plan


class AgentObserver(Protocol):
    """Receives the plan before execution starts, each tool call as it finishes, and
    each evidence check of a draft answer."""

    def on_plan(self, plan: Plan) -> None: ...

    def on_tool_call(self, record: ToolCallRecord) -> None: ...

    def on_evidence_check(self, check: EvidenceCheck) -> None: ...


class SilentObserver:
    """An `AgentObserver` that ignores every event."""

    def on_plan(self, plan: Plan) -> None:
        pass

    def on_tool_call(self, record: ToolCallRecord) -> None:
        pass

    def on_evidence_check(self, check: EvidenceCheck) -> None:
        pass
