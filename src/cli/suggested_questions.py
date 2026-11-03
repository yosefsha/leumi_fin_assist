"""The suggested questions the CLI offers by number, read from `prompts/suggested_questions.txt`."""

from dataclasses import dataclass
from pathlib import Path

from utils.prompts import PROMPTS_DIR, load_prompt

SUGGESTIONS_PROMPT = "suggested_questions"


class NoSuggestedQuestionsError(ValueError):
    """The suggested-questions file lists no question."""


@dataclass(frozen=True)
class SuggestedQuestions:
    """The questions, numbered from 1 in file order."""

    questions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.questions:
            raise NoSuggestedQuestionsError("There are no suggested questions.")

    @classmethod
    def parse(cls, text: str) -> "SuggestedQuestions":
        """One question per non-blank line; lines starting with `#` are comments."""
        lines = (line.strip() for line in text.splitlines())
        return cls(tuple(line for line in lines if line and not line.startswith("#")))

    def get(self, number: int) -> str | None:
        """The question numbered `number`, or None when there is no such number."""
        return self.questions[number - 1] if 1 <= number <= len(self.questions) else None

    def numbered_lines(self, indent: str = "  ") -> list[str]:
        """`  1) question`, one line per question."""
        return [f"{indent}{n}) {question}" for n, question in enumerate(self.questions, 1)]

    def pick(self, choice: str) -> str | None:
        """The question a number choice (see `is_number_choice`) names, or None if none does.

        A choice with more digits than the largest number is never converted, so an
        arbitrarily long digit string cannot hit Python's int-conversion limit.
        """
        digits = choice.strip().lstrip("0") or "0"
        if len(digits) > len(str(len(self.questions))):
            return None
        return self.get(int(digits))

    def out_of_range(self, choice: str) -> str:
        """The message for a number choice with no question."""
        return (
            f"There is no suggestion {choice.strip()}: "
            f"choose a number from 1 to {len(self.questions)}."
        )


def is_number_choice(text: str) -> bool:
    """Whether `text` is only digits (e.g. `"2"`), so it picks a suggestion by number."""
    stripped = text.strip()
    return stripped.isascii() and stripped.isdigit()


def load_suggested_questions(prompts_dir: Path = PROMPTS_DIR) -> SuggestedQuestions:
    """Read `<prompts_dir>/suggested_questions.txt`.

    Raises `PromptNotFoundError` when the file is missing and
    `NoSuggestedQuestionsError` when it lists no question.
    """
    return SuggestedQuestions.parse(load_prompt(SUGGESTIONS_PROMPT, prompts_dir))
