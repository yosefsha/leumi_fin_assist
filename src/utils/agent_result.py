"""What one agent run returns: the plan, the tool trace, and the cited answer."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from utils.cited_answer import CitedAnswer
from utils.plan import Plan


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool call the executor ran, in the order the model asked for it.

    `error` is the error result's text when the call failed, else `None`.
    `citation_ids` are the IDs the call's sources were registered under.
    """

    round: int
    name: str
    args: Mapping[str, Any] = field(hash=False)
    error: str | None = None
    citation_ids: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class AgentResult:
    """The outcome of answering one question.

    `hit_round_limit` is true when the model still wanted tools after the last
    allowed round and was told to answer with what it had. `answer_truncated` is
    true when the answer hit the model's output-token limit and is incomplete.
    """

    question: str
    plan: Plan
    trace: tuple[ToolCallRecord, ...]
    answer: CitedAnswer
    hit_round_limit: bool = False
    answer_truncated: bool = False
