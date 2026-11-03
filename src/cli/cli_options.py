"""The command-line options and their parser."""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass

DESCRIPTION = (
    "Answer questions about Apple's 10-K filing and the live web, with citations. "
    "Without --query, starts an interactive prompt (type 'exit' or 'quit', or press "
    "Ctrl-D, to leave; Ctrl-C cancels a running question)."
)
EPILOG = (
    "API keys and other settings come from the environment or .env (see .env.example). "
    "Logs go to stderr at LOG_LEVEL. Exit status: 0 on success, 1 when the model API "
    "fails or the Filing index cannot be opened, 2 for invalid usage or configuration, "
    "130 when a --query or startup is interrupted (leaving the prompt is a normal exit)."
)


@dataclass(frozen=True)
class CliOptions:
    """What the user asked the CLI to do. `query` is set for a single-shot run."""

    quiet: bool = False
    rebuild_index: bool = False
    query: str | None = None


def parse_cli_args(argv: Sequence[str] | None = None) -> CliOptions:
    """Parse `argv` (default: `sys.argv[1:]`); invalid usage exits with status 2."""
    namespace = _parser().parse_args(argv)
    return CliOptions(
        quiet=namespace.quiet, rebuild_index=namespace.rebuild_index, query=namespace.query
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python src/main.py", description=DESCRIPTION, epilog=EPILOG
    )
    parser.add_argument(
        "--query",
        metavar="QUESTION",
        type=_question,
        help="answer QUESTION once and exit instead of starting the interactive prompt",
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


def _question(raw: str) -> str:
    question = raw.strip()
    if not question:
        raise argparse.ArgumentTypeError("the question is empty")
    return question
