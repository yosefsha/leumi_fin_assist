"""Prints an agent run's answer, its Sources, and any caveat about how the run ended."""

from typing import TextIO

from utils.agent_result import AgentResult

ROUND_LIMIT_NOTICE = (
    "[Note: the agent reached its tool-call limit and answered with what it had found.]"
)
TRUNCATED_NOTICE = "[Note: the answer hit the model's output limit and is cut short.]"
NO_SOURCES = "Sources: none cited."


class AnswerPrinter:
    """Writes the answer and Sources to `out`, and the run's caveats to `notices`.

    The CLI passes stdout for both, or stderr for `notices` under `--quiet`, so
    stdout then carries only the answer and its Sources.
    """

    def __init__(self, out: TextIO, notices: TextIO) -> None:
        self._out = out
        self._notices = notices

    def print_result(self, result: AgentResult) -> None:
        answer = result.answer
        print(answer.text if answer.sources else f"{answer.body}\n\n{NO_SOURCES}", file=self._out)
        if result.hit_round_limit:
            print(ROUND_LIMIT_NOTICE, file=self._notices)
        if result.answer_truncated:
            print(TRUNCATED_NOTICE, file=self._notices)
        self._out.flush()
        self._notices.flush()
