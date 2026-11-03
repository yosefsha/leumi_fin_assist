"""How asking one question ended."""

from enum import Enum


class QuestionOutcome(Enum):
    """The result of `QuestionSession.ask`, which the CLI maps to an exit status."""

    ANSWERED = "answered"
    FAILED = "failed"
    CANCELLED = "cancelled"
