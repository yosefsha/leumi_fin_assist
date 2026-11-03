"""A tool call as evidence: the call and the cited result the executor saw (#29)."""

import json
from dataclasses import dataclass

from utils.agent_result import ToolCallRecord


@dataclass(frozen=True)
class ToolEvidence:
    """One tool call and its result as the model saw it, sources under their citation IDs."""

    record: ToolCallRecord
    cited_content: str

    def render(self) -> str:
        """The call and its result as one block of the evidence check's prompt."""
        status = "error" if self.record.is_error else "result"
        args = json.dumps(dict(self.record.args), ensure_ascii=False)
        return (
            f'<tool_call round="{self.record.round}" name="{self.record.name}">\n'
            f"<arguments>{args}</arguments>\n"
            f"<{status}>\n{self.cited_content}\n</{status}>\n"
            "</tool_call>"
        )
