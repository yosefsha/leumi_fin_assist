"""Runs the CLI once its options are parsed: a single `--query`, or the interactive REPL."""

from collections.abc import Callable
from typing import TextIO

from cli.answer_printer import AnswerPrinter
from cli.cli_options import CliOptions
from cli.question_answerer import QuestionAnswerer
from cli.question_outcome import QuestionOutcome
from cli.question_session import QuestionSession
from cli.repl import Repl
from cli.trace_printer import TracePrinter
from utils.agent_observer import AgentObserver

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CONFIG_ERROR = 2
EXIT_INTERRUPTED = 130

BANNER = "Ask a question about the filing, or type 'exit' to quit."

_EXIT_STATUS = {
    QuestionOutcome.ANSWERED: EXIT_OK,
    QuestionOutcome.FAILED: EXIT_FAILURE,
    QuestionOutcome.CANCELLED: EXIT_INTERRUPTED,
}

type AgentBuilder = Callable[[AgentObserver | None], QuestionAnswerer]
type LineReader = Callable[[str], str]


def run_cli(
    options: CliOptions,
    build_agent: AgentBuilder,
    read_line: LineReader,
    out: TextIO,
    err: TextIO,
) -> int:
    """Build the agent once, then answer `options.query` or run the REPL; return the exit status.

    Without `--quiet` the agent reports to a `TracePrinter` on `out`. With it, `out`
    carries only answers and Sources; the prompt, caveats and errors go to `err`.
    """
    agent = build_agent(None if options.quiet else TracePrinter(out))
    ui = err if options.quiet else out
    printer = AnswerPrinter(out, notices=ui)
    session = QuestionSession(agent, printer, out, err, show_progress=not options.quiet)
    if options.query is not None:
        return _EXIT_STATUS[session.ask(options.query)]
    if options.quiet:
        read_line = _prompting_on(err, read_line)
    else:
        print(BANNER, file=out, flush=True)
    return Repl(session, read_line, ui).run()


def _prompting_on(stream: TextIO, read_line: LineReader) -> LineReader:
    """A reader that writes its prompt to `stream` instead of letting `read_line` print it."""

    def read(prompt: str) -> str:
        print(prompt, end="", file=stream, flush=True)
        return read_line("")

    return read
