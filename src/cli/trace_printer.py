"""The live trace: an `AgentObserver` that prints the plan and each tool call as it happens."""

from typing import TextIO

from cli.tool_call_format import describe_outcome
from utils.agent_result import ToolCallRecord
from utils.plan import Plan

PLAN_LABEL = "[Plan] "


class TracePrinter:
    """Writes `[Plan] …` and `[Tool: …]` lines to `out`, flushing each so they appear live."""

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

    def _write(self, text: str) -> None:
        print(text, file=self._out, flush=True)
