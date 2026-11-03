"""Command-line entry point: `finassist [QUESTION | NUMBER] [--quiet] [--rebuild-index]`.

The `finassist` command (installed by `pip install -e .`) runs `main`; so does
`python src/main.py`, with the same arguments. Parses the options, loads the
settings, configures logging, builds the agent once and hands over to `run_cli`,
which answers one question or many.
"""

import contextlib
import os
import sys
from collections.abc import Callable, Sequence

from agent_factory import build_agent
from cli.cli_app import EXIT_CONFIG_ERROR, EXIT_FAILURE, EXIT_INTERRUPTED, run_cli, trace_observer
from cli.cli_options import parse_cli_args
from cli.menu import Menu, welcome_title
from cli.suggested_questions import (
    NoSuggestedQuestionsError,
    SuggestedQuestions,
    load_suggested_questions,
)
from utils.config import ConfigError, Settings
from utils.filing_index_factory import INDEX_LOAD_ERRORS
from utils.logging_config import configure_logging
from utils.prompts import PromptNotFoundError

with contextlib.suppress(ImportError):  # line editing and history at the prompt, where available
    import readline  # noqa: F401


def main(
    argv: Sequence[str] | None = None,
    load_settings: Callable[[], Settings] = Settings.load,
    load_suggestions: Callable[[], SuggestedQuestions] = load_suggested_questions,
) -> int:
    """Run the CLI and return its exit status."""
    try:
        suggestions = load_suggestions()
    except (PromptNotFoundError, NoSuggestedQuestionsError) as error:
        print(f"Error: cannot load the suggested questions: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    options = parse_cli_args(suggestions, argv)
    try:
        settings = load_settings()
    except ConfigError as error:
        print(f"Error: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    configure_logging(settings.log_level)
    try:
        agent = build_agent(settings, options.rebuild_index, trace_observer(options, sys.stdout))
    except INDEX_LOAD_ERRORS as error:
        print(f"Error: cannot open the Filing index: {error}", file=sys.stderr)
        return EXIT_FAILURE
    except KeyboardInterrupt:  # while the index loads, before the prompt is up
        print(file=sys.stderr)
        return EXIT_INTERRUPTED
    menu = Menu(welcome_title(settings.filing_fiscal_year), suggestions)
    status = run_cli(options, agent, input, sys.stdout, sys.stderr, menu)
    if status == EXIT_INTERRUPTED:
        # A cancelled single question may leave tool calls in flight on worker threads, which
        # the interpreter would wait for at exit; nothing is left to clean up, so go now.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(status)
    return status


if __name__ == "__main__":
    sys.exit(main())
