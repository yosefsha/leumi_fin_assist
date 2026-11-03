"""Command-line entry point: `python src/main.py [--query QUESTION] [--quiet] [--rebuild-index]`.

Parses the options, loads the settings, configures logging and hands over to
`run_cli`, which builds the agent once and answers one question or many.
"""

import contextlib
import sys
from collections.abc import Callable, Sequence

from agent_factory import build_agent
from cli.cli_app import EXIT_CONFIG_ERROR, EXIT_FAILURE, EXIT_INTERRUPTED, run_cli
from cli.cli_options import parse_cli_args
from utils.config import ConfigError, Settings
from utils.filing_index_factory import INDEX_LOAD_ERRORS
from utils.logging_config import configure_logging

with contextlib.suppress(ImportError):  # line editing and history at the prompt, where available
    import readline  # noqa: F401


def main(
    argv: Sequence[str] | None = None, load_settings: Callable[[], Settings] = Settings.load
) -> int:
    """Run the CLI and return its exit status."""
    options = parse_cli_args(argv)
    try:
        settings = load_settings()
    except ConfigError as error:
        print(f"Error: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    configure_logging(settings.log_level)
    try:
        return run_cli(
            options,
            lambda observer: build_agent(settings, options.rebuild_index, observer),
            input,
            sys.stdout,
            sys.stderr,
        )
    except INDEX_LOAD_ERRORS as error:
        print(f"Error: cannot open the Filing index: {error}", file=sys.stderr)
        return EXIT_FAILURE
    except KeyboardInterrupt:  # while the index loads, before the prompt is up
        print(file=sys.stderr)
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())
