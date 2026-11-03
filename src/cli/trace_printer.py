"""The live trace: an `AgentObserver` that prints the plan, tool calls and evidence checks."""

from typing import TextIO

from cli.tool_call_format import describe_outcome
from utils.agent_result import EvidenceCheck, ToolCallRecord
from utils.plan import Plan

PLAN_LABEL = "[Plan] "
CHECK_LABEL = "[Check] "


class TracePrinter:
    """Writes `[Plan] …`, `[Tool: …]` and `[Check] …` lines to `out`, flushing each line."""

    def __init__(self, out: TextIO) -> None:
        self._out = out

    def on_plan(self, plan: Plan) -> None:
        if not plan.steps:
            self._write(f"{PLAN_LABEL}none — working from the question alone")
            return
        indent = " " * len(PLAN_LABEL)
        lines = [
            f"{indent if n > 1 else PLAN_LABEL}{n}) {step.tool} — {step.purpose}"
            for n, step in enumerate(plan.steps, 1)
        ]
        self._write("\n".join(lines))

    def on_tool_call(self, record: ToolCallRecord) -> None:
        self._write(describe_outcome(record))

    def on_evidence_check(self, check: EvidenceCheck) -> None:
        self._write(CHECK_LABEL + describe_check(check))

    def _write(self, text: str) -> None:
        print(text, file=self._out, flush=True)


def describe_check(check: EvidenceCheck) -> str:
    """The `[Check]` line's text: sufficient, the gaps it sends back, or a failed check."""
    review = check.review
    if review is None:
        return "unavailable — keeping the draft answer"
    if review.sufficient:
        return "evidence sufficient"
    count = len(review.gaps)
    gaps = "; ".join(f"{gap.requirement} — {gap.problem.value}" for gap in review.gaps)
    return f"{count} gap{'s' if count > 1 else ''}: {gaps} → retrying"
