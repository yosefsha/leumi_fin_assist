"""What one agent run returns: the plan, the tool trace, the evidence checks and the answer."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from utils.cited_answer import CitedAnswer
from utils.evidence_review import EvidenceReview
from utils.plan import Plan


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool call the executor ran, in the order the model asked for it.

    `output` is the tool's result text as the tool returned it (before its sources
    were cited), or the error text when `is_error`. `citation_ids` are the IDs the
    call's sources were registered under.
    """

    round: int
    name: str
    args: Mapping[str, Any] = field(hash=False)
    output: str
    is_error: bool = False
    citation_ids: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.is_error


@dataclass(frozen=True)
class EvidenceCheck:
    """One evidence check of a draft answer (#29).

    `review` is the reviewer's verdict, or `None` when the check itself failed
    (model error, refusal or invalid output) and the draft was kept.
    """

    review: EvidenceReview | None

    @property
    def failed(self) -> bool:
        return self.review is None

    @property
    def found_gaps(self) -> bool:
        """True when the review lists gaps: the executor is sent back to gather more."""
        return self.review is not None and not self.review.sufficient


@dataclass(frozen=True)
class AgentResult:
    """The outcome of answering one question.

    `hit_round_limit` is true when the model still wanted tools after the last
    allowed round and was told to answer with what it had. `answer_truncated` is
    true when the answer hit the model's output-token limit and is incomplete.
    `evidence_checks` are the checks run on draft answers, in order.
    """

    question: str
    plan: Plan
    trace: tuple[ToolCallRecord, ...]
    answer: CitedAnswer
    hit_round_limit: bool = False
    answer_truncated: bool = False
    evidence_checks: tuple[EvidenceCheck, ...] = ()
