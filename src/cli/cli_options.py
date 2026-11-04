"""The command-line options and their parser."""

import argparse
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass

from cli.suggested_questions import UNKNOWN_COMPANY, SuggestedQuestions, is_number_choice

PROG = "finassist"
HELP_WIDTH = 79

DESCRIPTION = (
    "Answer questions about {filer}'s 10-K filing and the live web, with citations. "
    "Without a question, starts an interactive prompt that lists suggested questions "
    "(type a number or your own question; 'help' shows the list again; 'exit' or 'quit', "
    "or Ctrl-D, leaves; Ctrl-C cancels a running question)."
)
SAME_AS_MAIN = "`python src/main.py` takes the same arguments."
EXAMPLES = (
    ("finassist", "interactive prompt with suggested questions"),
    ('finassist "QUESTION"', "answer one question, then exit"),
    ("finassist 1", "run suggested question 1, then exit"),
    ('finassist --quiet "QUESTION"', "print only the answer and its Sources"),
    ("finassist --rebuild-index", "rebuild the Filing index, then start the prompt"),
)
SETTINGS_NOTE = (
    "API keys and other settings come from the environment or the project's .env (see "
    ".env.example), wherever finassist is run from. Logs go to stderr at LOG_LEVEL. "
    "Exit status: 0 on success, 1 when the model API fails or the Filing index cannot be "
    "opened, 2 for invalid usage or configuration, 130 when a single question or startup "
    "is interrupted (leaving the prompt is a normal exit)."
)


@dataclass(frozen=True)
class CliOptions:
    """What the user asked the CLI to do.

    `query` is set for a single-shot run; `announce_query` when it was picked by
    number, so the CLI echoes the question it is answering.
    """

    quiet: bool = False
    rebuild_index: bool = False
    query: str | None = None
    announce_query: bool = False


def parse_cli_args(
    suggestions: SuggestedQuestions,
    argv: Sequence[str] | None = None,
    company: str | None = None,
) -> CliOptions:
    """Parse `argv` (default: `sys.argv[1:]`); invalid usage exits with status 2.

    The question comes as a positional argument or, equivalently, `--query`. A
    question that is only a number runs that suggested question. `--help` names
    `company` as the filer, or "the company" when it is `None` (settings not loaded).
    """
    parser = _parser(suggestions, company)
    namespace = parser.parse_args(argv)
    if namespace.question is not None and namespace.query is not None:
        parser.error("give the question once: as an argument or with --query, not both")
    query = namespace.question if namespace.question is not None else namespace.query
    options = CliOptions(quiet=namespace.quiet, rebuild_index=namespace.rebuild_index, query=query)
    if query is None or not is_number_choice(query):
        return options
    picked = suggestions.pick(query)
    if picked is None:
        parser.error(f"{suggestions.out_of_range(query)} See {PROG} --help for the list.")
    return CliOptions(
        quiet=options.quiet, rebuild_index=options.rebuild_index, query=picked, announce_query=True
    )


def _parser(suggestions: SuggestedQuestions, company: str | None) -> argparse.ArgumentParser:
    description = DESCRIPTION.format(filer=company or UNKNOWN_COMPANY)
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=f"{textwrap.fill(description, HELP_WIDTH)}\n\n{SAME_AS_MAIN}",
        epilog=_epilog(suggestions),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "question",
        nargs="?",
        metavar="QUESTION",
        type=_question,
        help="answer QUESTION once and exit; a number (e.g. 1) runs that suggested question",
    )
    parser.add_argument(
        "--query",
        metavar="QUESTION",
        type=_question,
        help="the same as giving QUESTION as an argument (kept for existing scripts)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print only the answer and its Sources (no plan, tool trace or progress line)",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="rebuild the Filing's search index before starting, even if it is current",
    )
    return parser


def _epilog(suggestions: SuggestedQuestions) -> str:
    width = max(len(command) for command, _ in EXAMPLES) + 2
    examples = [f"  {command:<{width}}{what}" for command, what in EXAMPLES]
    numbered = [_numbered(n, question) for n, question in enumerate(suggestions.questions, 1)]
    return "\n".join(
        [
            "examples:",
            *examples,
            "",
            f"suggested questions (run one with `{PROG} <number>`):",
            *numbered,
            "",
            textwrap.fill(SETTINGS_NOTE, HELP_WIDTH),
        ]
    )


def _numbered(number: int, question: str) -> str:
    """`  1) question`, wrapped with its continuation lines aligned under the text."""
    label = f"  {number}) "
    return textwrap.fill(
        question, HELP_WIDTH, initial_indent=label, subsequent_indent=" " * len(label)
    )


def _question(raw: str) -> str:
    question = raw.strip()
    if not question:
        raise argparse.ArgumentTypeError("the question is empty")
    return question
