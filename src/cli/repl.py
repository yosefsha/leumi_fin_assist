"""The interactive loop: show the menu, read a question or a number at `> `, answer, repeat."""

from collections.abc import Callable
from typing import TextIO

from cli.menu import Menu
from cli.question_session import QuestionSession
from cli.suggested_questions import suggestion_number

PROMPT = "> "
EXIT_COMMANDS = frozenset({"exit", "quit"})
HELP_COMMANDS = frozenset({"help", "?"})
QUESTION_LABEL = "Question: "


class Repl:
    """Reads lines with `read_line` until `exit`, `quit`, Ctrl-D or Ctrl-C at the prompt.

    A number picks a suggested question from `menu` and echoes it before answering;
    `help` or `?` shows the suggestions again; anything else is the question.
    Blank lines are ignored. A failed or cancelled question returns to the prompt.
    `ui` receives the menu, echoes, messages and blank separator lines (stderr under
    `--quiet`, so stdout carries only answers).
    """

    def __init__(
        self,
        session: QuestionSession,
        read_line: Callable[[str], str],
        ui: TextIO,
        menu: Menu,
    ) -> None:
        self._session = session
        self._read_line = read_line
        self._ui = ui
        self._menu = menu

    def run(self) -> int:
        """Loop until the user leaves; leaving is a normal exit, so the status is always 0."""
        self._show(self._menu.welcome())
        while True:
            try:
                line = self._read_line(PROMPT).strip()
            except (EOFError, KeyboardInterrupt):
                print(file=self._ui, flush=True)  # end the prompt's line
                return 0
            if not line:
                continue
            command = line.lower()
            if command in EXIT_COMMANDS:
                return 0
            if command in HELP_COMMANDS:
                self._show(self._menu.listing())
                continue
            question = self._question_for(line)
            if question is None:
                continue
            self._session.ask(question)
            print(file=self._ui, flush=True)

    def _question_for(self, line: str) -> str | None:
        """The question `line` asks: itself, or the suggestion it numbers (echoed first)."""
        number = suggestion_number(line)
        if number is None:
            return line
        suggestions = self._menu.suggestions
        question = suggestions.get(number)
        if question is None:
            self._show(f"{suggestions.out_of_range(number)} Type 'help' to see the list.")
        else:
            self._show(f"{QUESTION_LABEL}{question}")
        return question

    def _show(self, text: str) -> None:
        print(text, file=self._ui, flush=True)
