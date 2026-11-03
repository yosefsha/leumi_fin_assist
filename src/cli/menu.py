"""The interactive mode's welcome screen: a title and the numbered suggested questions."""

from dataclasses import dataclass

from cli.suggested_questions import SuggestedQuestions

MENU_INTRO = "Try one of these, or type your own question:"
MENU_HINT = "Type a number, a question, 'help' to show this list again, or 'exit' to quit."


def welcome_title(fiscal_year: int) -> str:
    """The first line of the interactive mode, naming the Filing it answers from."""
    return f"Financial Research Assistant — Apple 10-K (FY{fiscal_year}) + web search"


@dataclass(frozen=True)
class Menu:
    """What the interactive mode shows at start-up and on `help`."""

    title: str
    suggestions: SuggestedQuestions

    def welcome(self) -> str:
        """The title followed by the suggestion list."""
        return f"{self.title}\n{self.listing()}"

    def listing(self) -> str:
        """The numbered suggestions with the line that says what can be typed."""
        return "\n".join([MENU_INTRO, *self.suggestions.numbered_lines(), MENU_HINT])
