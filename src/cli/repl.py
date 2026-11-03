"""The interactive loop: read a question at `> `, answer it, repeat until the user leaves."""

from collections.abc import Callable
from typing import TextIO

from cli.question_session import QuestionSession

PROMPT = "> "
EXIT_COMMANDS = frozenset({"exit", "quit"})


class Repl:
    """Reads questions with `read_line` until `exit`, `quit`, Ctrl-D or Ctrl-C at the prompt.

    Blank lines are ignored. A failed or cancelled question returns to the prompt.
    `ui` receives the blank separator lines (stderr under `--quiet`, so stdout
    carries only answers).
    """

    def __init__(
        self, session: QuestionSession, read_line: Callable[[str], str], ui: TextIO
    ) -> None:
        self._session = session
        self._read_line = read_line
        self._ui = ui

    def run(self) -> int:
        """Loop until the user leaves; leaving is a normal exit, so the status is always 0."""
        while True:
            try:
                line = self._read_line(PROMPT).strip()
            except (EOFError, KeyboardInterrupt):
                print(file=self._ui, flush=True)  # end the prompt's line
                return 0
            if not line:
                continue
            if line.lower() in EXIT_COMMANDS:
                return 0
            self._session.ask(line)
            print(file=self._ui, flush=True)
