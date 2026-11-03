"""Asks the agent one question and prints the outcome, success or failure."""

from enum import Enum
from typing import TextIO

from cli.answer_printer import AnswerPrinter
from cli.question_answerer import QuestionAnswerer
from utils.chat_model import ChatModelError

PROCESSING_LINE = "[Agent processing...]"
CANCELLED_LINE = "[Cancelled]"


class Outcome(Enum):
    """How asking one question ended."""

    ANSWERED = "answered"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QuestionSession:
    """Runs a question through the agent and prints the answer or a one-line error.

    A model/API failure (`ChatModelError`, after the client's retries) is printed
    to `err` as one line. Ctrl-C while the agent works cancels the question.
    Anything else is a bug and propagates.
    """

    def __init__(
        self,
        agent: QuestionAnswerer,
        printer: AnswerPrinter,
        out: TextIO,
        err: TextIO,
        show_progress: bool,
    ) -> None:
        self._agent = agent
        self._printer = printer
        self._out = out
        self._err = err
        self._show_progress = show_progress

    def ask(self, question: str) -> Outcome:
        if self._show_progress:
            print(PROCESSING_LINE, file=self._out, flush=True)
        try:
            result = self._agent.answer(question)
        except ChatModelError as error:
            print(f"Error: {error}", file=self._err, flush=True)
            return Outcome.FAILED
        except KeyboardInterrupt:
            print(CANCELLED_LINE, file=self._err, flush=True)
            return Outcome.CANCELLED
        if self._show_progress:
            print(file=self._out)
        self._printer.print_result(result)
        return Outcome.ANSWERED
