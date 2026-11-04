"""The CLI's deterministic behaviour (issues #10, #31, #35): the REPL and its menu, the
arguments, trace lines and errors, and the configured company in the banner and `--help`.

The agent is the real `ResearchAgent` over a scripted `ChatModel` (or a stub for
interrupts and caveats), so these tests check what the CLI prints and returns, not
which tools a real model would choose (ADR-0004).
"""

import importlib
import io
import logging
import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pytest

import main as main_module
from agent import ResearchAgent
from cli.answer_printer import NO_SOURCES, ROUND_LIMIT_NOTICE, TRUNCATED_NOTICE
from cli.cli_app import (
    EXIT_CONFIG_ERROR,
    EXIT_FAILURE,
    EXIT_INTERRUPTED,
    EXIT_OK,
    run_cli,
    trace_observer,
)
from cli.cli_options import CliOptions, parse_cli_args
from cli.menu import Menu, welcome_title
from cli.question_session import CANCELLED_LINE, PROCESSING_LINE
from cli.repl import PROMPT, QUESTION_LABEL
from cli.suggested_questions import (
    SuggestedQuestions,
    SuggestedQuestionsFileError,
    load_suggested_questions,
)
from cli.tool_call_format import describe_outcome
from cli.trace_printer import TracePrinter, describe_check
from fakes.scripted_chat_model import Outcome, ScriptedChatModel, text_reply, tool_reply
from main import main
from tools.calculator import CalculateTool
from tools.registry import ToolOutput, ToolRegistry
from utils.agent_observer import AgentObserver
from utils.agent_result import AgentResult, EvidenceCheck, ToolCallRecord
from utils.chat_model import ChatModelError
from utils.citation_format import CitationFormatter
from utils.cited_answer import CitationResolver, CitedAnswer
from utils.config import (
    DEFAULT_ENV_FILE,
    DEFAULT_FILING_PATH,
    PROJECT_ROOT,
    ConfigError,
    FilingProfile,
    Settings,
)
from utils.embedder import EmbedderError
from utils.evidence_review import EvidenceReview
from utils.logging_config import LibraryNoiseFilter, configure_logging
from utils.passage import Passage, PassageKind
from utils.plan import Plan
from utils.tool_result_citer import ToolResultCiter

_PASSAGE = Passage(
    passage_id="item-8-003",
    item="Item 8",
    section_path=("Item 8", "CONSOLIDATED STATEMENTS OF OPERATIONS"),
    page=29,
    kind=PassageKind.TABLE,
    content="| Research and development | $ 34,550 |",
)
_PLAN_JSON = (
    '{"steps": [{"tool": "search_filing", "purpose": "Find R&D expense in Item 8."},'
    ' {"tool": "calculate", "purpose": "R&D as a share of net sales."}]}'
)
_SEARCH = ("search_filing", {"query": "research and development expense", "item": "8"})
_CALCULATE = ("calculate", {"expression": "34550 / 416161 * 100"})
_ANSWER = "R&D was 8.3% of net sales [F1]."
_SOURCE_LINE = "10-K FY2025 — Item 8 > CONSOLIDATED STATEMENTS OF OPERATIONS, p. 29"
_SUGGESTIONS = SuggestedQuestions(("First suggestion?", "Second suggestion?"))
_APPLE_FILING = FilingProfile.from_mapping({})
_OTHER_FILING = FilingProfile.from_mapping(
    {
        "FILING_PATH": "data/contoso_10k_2026.htm",
        "FILING_COMPANY": "Contoso Ltd.",
        "FILING_FISCAL_YEAR": "2026",
    }
)
_MENU = Menu("Test assistant", _SUGGESTIONS)
_WELCOME = (
    "Test assistant\n"
    "Try one of these, or type your own question:\n"
    "  1) First suggestion?\n"
    "  2) Second suggestion?\n"
    "Type a number, a question, 'help' to show this list again, or 'exit' to quit.\n"
)
_LISTING = _WELCOME.removeprefix("Test assistant\n")


class _SearchTool:
    """A `search_filing` stand-in that always finds `_PASSAGE`."""

    name = "search_filing"
    description = "Search the Filing."
    input_schema: Mapping[str, Any] = {"type": "object", "properties": {}}

    def run(self, args: Mapping[str, Any]) -> ToolOutput:
        return ToolOutput(content='{"results_found": 1}', sources=(_PASSAGE,))


class _StubAgent:
    """Returns `result` or raises `error` for every question, and records the questions."""

    def __init__(self, result: AgentResult | None = None, error: BaseException | None = None):
        self._result = result
        self._error = error
        self.questions: list[str] = []

    def answer(self, question: str) -> AgentResult:
        self.questions.append(question)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _scripted_builder(
    replies: Iterable[Outcome], plan_json: str = _PLAN_JSON, reviews: Iterable[str] | None = None
) -> Callable[[AgentObserver | None], ResearchAgent]:
    """Build the real agent over a scripted model, with the observer the CLI hands it."""

    def build(observer: AgentObserver | None) -> ResearchAgent:
        registry = ToolRegistry()
        registry.register(_SearchTool())
        registry.register(CalculateTool())
        formatter = CitationFormatter(fiscal_year=2025)
        return ResearchAgent(
            model=ScriptedChatModel(replies, plan_json=plan_json, reviews=reviews),
            tools=registry,
            citer=ToolResultCiter(formatter),
            resolver=CitationResolver(formatter),
            fiscal_year=2025,
            company="Apple Inc.",
            observer=observer,
            today=lambda: date(2026, 11, 3),
        )

    return build


def _lines(*lines: str | type[BaseException]) -> Callable[[str], str]:
    """A `read_line` that returns `lines` in turn, raising any exception class it meets,
    then raises `EOFError` (Ctrl-D)."""
    pending: Iterator[str | type[BaseException]] = iter(lines)

    def read_line(prompt: str) -> str:
        assert prompt in (PROMPT, "")  # "" when --quiet writes the prompt to stderr itself
        line = next(pending, EOFError)
        if isinstance(line, type):
            raise line()
        return line

    return read_line


def _run(
    options: CliOptions,
    agent: _StubAgent | Callable[[AgentObserver | None], ResearchAgent],
    read_line: Callable[[str], str] | None = None,
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    if not isinstance(agent, _StubAgent):
        agent = agent(trace_observer(options, out))
    status = run_cli(options, agent, read_line or _lines(), out, err, _MENU)
    return status, out.getvalue(), err.getvalue()


def _result(answer: CitedAnswer, **flags: bool) -> AgentResult:
    return AgentResult(question="q", plan=Plan(), trace=(), answer=answer, **flags)


def _record(name: str, args: Mapping[str, Any], output: str = "", is_error: bool = False):
    return ToolCallRecord(round=1, name=name, args=args, output=output, is_error=is_error)


# --- The REPL -------------------------------------------------------------------------------


@pytest.mark.parametrize("command", ["exit", "quit", "  EXIT ", "Quit"])
def test_exit_commands_leave_with_status_zero_without_asking(command: str) -> None:
    agent = _StubAgent(error=AssertionError("not asked"))
    status, out, err = _run(CliOptions(), agent, _lines(command, "never read"))
    assert (status, agent.questions, out, err) == (EXIT_OK, [], _WELCOME, "")


@pytest.mark.parametrize("key", [EOFError, KeyboardInterrupt], ids=["ctrl-d", "ctrl-c"])
def test_ctrl_d_or_ctrl_c_at_the_prompt_leaves_cleanly(key: type[BaseException]) -> None:
    agent = _StubAgent(error=AssertionError("not asked"))
    status, out, err = _run(CliOptions(), agent, _lines("", key, "never read"))
    assert (status, agent.questions, err) == (EXIT_OK, [], "")
    assert out == f"{_WELCOME}\n"  # the menu, then a newline that ends the prompt's line


def test_quiet_repl_keeps_the_prompt_and_separators_off_stdout() -> None:
    agent = _StubAgent(result=_result(CitedAnswer(body="Hi.", sources=())))
    status, out, err = _run(CliOptions(quiet=True), agent, _lines("one", "two"))
    assert status == EXIT_OK
    assert out == f"Hi.\n\n{NO_SOURCES}\n" * 2
    assert err == f"{_WELCOME}{PROMPT}\n{PROMPT}\n{PROMPT}\n"


def test_ctrl_c_while_the_answer_prints_cancels_only_that_question() -> None:
    class _InterruptingOut(io.StringIO):
        def write(self, text: str) -> int:
            if text.startswith("Hi."):
                raise KeyboardInterrupt
            return super().write(text)

    agent = _StubAgent(result=_result(CitedAnswer(body="Hi.", sources=())))
    out, err = _InterruptingOut(), io.StringIO()
    status = run_cli(CliOptions(), agent, _lines("one", "two"), out, err, _MENU)
    assert (status, agent.questions) == (EXIT_OK, ["one", "two"])
    assert err.getvalue() == f"{CANCELLED_LINE}\n{CANCELLED_LINE}\n"


def test_blank_lines_are_ignored() -> None:
    agent = _StubAgent(result=_result(CitedAnswer(body="Hi.", sources=())))
    _run(CliOptions(quiet=True), agent, _lines("", "   ", "\t", "hello"))
    assert agent.questions == ["hello"]


def test_a_question_prints_progress_plan_trace_answer_and_sources_in_order() -> None:
    build = _scripted_builder([tool_reply(_SEARCH, _CALCULATE), text_reply(_ANSWER)])
    status, out, err = _run(CliOptions(), build, _lines("What share of sales was R&D?"))

    expected_answer = CitedAnswer(
        body="R&D was 8.3% of net sales [1].",
        sources=(_SOURCE_LINE,),
    )
    assert status == EXIT_OK
    assert err == ""
    assert out == (
        f"{_WELCOME}"
        f"{PROCESSING_LINE}\n"
        "[Plan] 1) search_filing — Find R&D expense in Item 8.\n"
        "       2) calculate — R&D as a share of net sales.\n"
        '[Tool: search_filing(item="8") "research and development expense"]\n'
        "[Tool: calculate] 34550 / 416161 * 100 = 8.302075398703867\n"
        "[Check] evidence sufficient\n"
        "\n"
        f"{expected_answer.text}\n"
        "\n"  # spacing before the next prompt
        "\n"  # Ctrl-D ends the prompt's line
    )
    assert "Sources:\n[1] " in out


def test_each_question_gets_a_fresh_citation_registry() -> None:
    """The second question cites [F1] without searching: that ID is not its own, so it drops."""
    build = _scripted_builder(
        [tool_reply(_SEARCH), text_reply(_ANSWER), text_reply("Again [F1].")],
        plan_json='{"steps": []}',
    )
    status, out, _ = _run(CliOptions(quiet=True), build, _lines("first", "second"))
    assert status == EXIT_OK
    assert "Sources:\n[1] " in out
    assert f"Again.\n\n{NO_SOURCES}\n" in out


def test_an_api_failure_prints_one_error_line_and_the_repl_keeps_going() -> None:
    build = _scripted_builder(
        [ChatModelError("The model API is unavailable (HTTP 529)."), text_reply("Recovered.")],
        plan_json='{"steps": []}',
    )
    status, out, err = _run(CliOptions(), build, _lines("first", "second"))
    assert status == EXIT_OK
    assert err == "Error: The model API is unavailable (HTTP 529).\n"
    assert "Recovered." in out


def test_ctrl_c_while_answering_cancels_the_question_and_returns_to_the_prompt() -> None:
    agent = _StubAgent(error=KeyboardInterrupt())
    status, _, err = _run(CliOptions(), agent, _lines("slow question", "another"))
    assert status == EXIT_OK
    assert agent.questions == ["slow question", "another"]
    assert err == f"{CANCELLED_LINE}\n{CANCELLED_LINE}\n"


# --- The menu of suggested questions --------------------------------------------------------


def test_a_number_at_the_prompt_echoes_and_asks_that_suggestion() -> None:
    agent = _StubAgent(result=_result(CitedAnswer(body="Hi.", sources=())))
    status, out, err = _run(CliOptions(), agent, _lines(" 2 "))
    assert (status, agent.questions, err) == (EXIT_OK, ["Second suggestion?"], "")
    assert out.startswith(f"{_WELCOME}{QUESTION_LABEL}Second suggestion?\n{PROCESSING_LINE}\n")


def test_free_text_at_the_prompt_is_asked_as_typed_without_an_echo() -> None:
    agent = _StubAgent(result=_result(CitedAnswer(body="Hi.", sources=())))
    _, out, _ = _run(CliOptions(), agent, _lines("What is 2 + 2?"))
    assert agent.questions == ["What is 2 + 2?"]
    assert QUESTION_LABEL not in out


@pytest.mark.parametrize("number", ["0", "3", "42", pytest.param("9" * 5000, id="5000-digits")])
def test_an_out_of_range_number_gets_one_line_and_the_menu_is_not_reprinted(number: str) -> None:
    agent = _StubAgent(error=AssertionError("not asked"))
    status, out, _ = _run(CliOptions(), agent, _lines(number))
    assert (status, agent.questions) == (EXIT_OK, [])
    assert out == (
        f"{_WELCOME}There is no suggestion {number}: choose a number from 1 to 2. "
        "Type 'help' to see the list.\n\n"
    )


def test_a_number_with_leading_zeros_still_picks_its_suggestion() -> None:
    assert _SUGGESTIONS.pick(" 02 ") == "Second suggestion?"


@pytest.mark.parametrize("command", ["help", "?", " HELP "])
def test_help_shows_the_suggestions_again(command: str) -> None:
    agent = _StubAgent(error=AssertionError("not asked"))
    status, out, _ = _run(CliOptions(), agent, _lines(command))
    assert (status, agent.questions) == (EXIT_OK, [])
    assert out == f"{_WELCOME}{_LISTING}\n"


def test_quiet_menu_and_echo_go_to_stderr() -> None:
    agent = _StubAgent(result=_result(CitedAnswer(body="Hi.", sources=())))
    _, out, err = _run(CliOptions(quiet=True), agent, _lines("1"))
    assert out == f"Hi.\n\n{NO_SOURCES}\n"
    assert err.startswith(f"{_WELCOME}{PROMPT}{QUESTION_LABEL}First suggestion?\n")


def test_a_question_picked_by_number_is_echoed_before_a_single_shot_answer() -> None:
    agent = _StubAgent(result=_result(CitedAnswer(body="Hi.", sources=())))
    options = CliOptions(query="First suggestion?", announce_query=True)
    status, out, _ = _run(options, agent)
    assert status == EXIT_OK
    assert out.startswith(f"{QUESTION_LABEL}First suggestion?\n{PROCESSING_LINE}\n")


def test_suggestions_file_skips_comments_and_blank_lines() -> None:
    text = "# heading\n\nFirst?\n  # indented comment\n  Second?  \n"
    assert SuggestedQuestions.parse(text).questions == ("First?", "Second?")


def test_an_empty_suggestions_file_is_rejected() -> None:
    with pytest.raises(ValueError, match="no suggested questions"):
        SuggestedQuestions.parse("# only a comment\n")


# --- Single shot (--query) and --quiet -------------------------------------------------------


def test_quiet_query_prints_only_the_answer_and_sources() -> None:
    build = _scripted_builder([tool_reply(_SEARCH), text_reply(_ANSWER)])
    status, out, err = _run(CliOptions(quiet=True, query="R&D share?"), build)
    assert (status, err) == (EXIT_OK, "")
    assert out == (f"R&D was 8.3% of net sales [1].\n\nSources:\n[1] {_SOURCE_LINE}\n")


def test_query_without_quiet_shows_the_trace_but_no_menu() -> None:
    build = _scripted_builder([text_reply("Done.")], plan_json='{"steps": []}')
    status, out, _ = _run(CliOptions(query="q"), build)
    assert status == EXIT_OK
    assert out.startswith(f"{PROCESSING_LINE}\n[Plan] none — working from the question alone\n")
    assert "Test assistant" not in out


_GAP_REVIEW = (
    '{"gaps": [{"requirement": "Company-wide gross margin, latest quarter",'
    ' "problem": "segment_not_company_wide", "retry_guidance": "Search the earnings release."}],'
    ' "sufficient": false}'
)


@pytest.mark.parametrize(("quiet", "shown"), [(False, True), (True, False)], ids=["trace", "quiet"])
def test_check_lines_show_a_retry_and_quiet_hides_them(quiet: bool, shown: bool) -> None:
    build = _scripted_builder(
        [text_reply("Segment only."), tool_reply(_SEARCH), text_reply(_ANSWER)],
        reviews=[_GAP_REVIEW],
    )
    status, out, err = _run(CliOptions(quiet=quiet, query="q"), build)
    check_line = (
        "[Check] 1 gap: Company-wide gross margin, latest quarter — "
        "segment_not_company_wide → retrying\n"
    )
    assert (status, err) == (EXIT_OK, "")
    assert (check_line in out) is shown
    assert ("[Check]" in out) is shown
    assert out.endswith(f"R&D was 8.3% of net sales [1].\n\nSources:\n[1] {_SOURCE_LINE}\n")


def _review(json_text: str) -> EvidenceCheck:
    return EvidenceCheck(review=EvidenceReview.model_validate_json(json_text))


@pytest.mark.parametrize(
    ("check", "line"),
    [
        (_review('{"gaps": [], "sufficient": true}'), "evidence sufficient"),
        (EvidenceCheck(review=None), "unavailable — keeping the draft answer"),
        (
            _review(
                '{"gaps": [{"requirement": "A", "problem": "missing", "retry_guidance": "x"},'
                ' {"requirement": "B", "problem": "secondary_source", "retry_guidance": "y"}],'
                ' "sufficient": false}'
            ),
            "2 gaps: A — missing; B — secondary_source → retrying",
        ),
    ],
    ids=["sufficient", "failed", "two-gaps"],
)
def test_check_lines(check: EvidenceCheck, line: str) -> None:
    assert describe_check(check) == line


def test_query_exits_non_zero_on_an_api_failure() -> None:
    build = _scripted_builder([ChatModelError("Could not reach the model API.")])
    status, out, err = _run(CliOptions(quiet=True, query="q"), build)
    assert (status, out, err) == (EXIT_FAILURE, "", "Error: Could not reach the model API.\n")


def test_query_interrupted_exits_130() -> None:
    status, out, err = _run(
        CliOptions(quiet=True, query="q"), _StubAgent(error=KeyboardInterrupt())
    )
    assert (status, out, err) == (EXIT_INTERRUPTED, "", f"{CANCELLED_LINE}\n")


@pytest.mark.parametrize(
    ("quiet", "in_stdout"), [(False, True), (True, False)], ids=["trace", "quiet"]
)
def test_round_limit_and_truncation_are_noted_on_stdout_or_on_stderr_when_quiet(
    quiet: bool, in_stdout: bool
) -> None:
    result = _result(
        CitedAnswer(body="Partial.", sources=()), hit_round_limit=True, answer_truncated=True
    )
    _, out, err = _run(CliOptions(quiet=quiet, query="q"), _StubAgent(result=result))
    notes = f"{ROUND_LIMIT_NOTICE}\n{TRUNCATED_NOTICE}\n"
    assert (notes in out, notes in err) == (in_stdout, not in_stdout)


def test_unexpected_errors_are_not_swallowed() -> None:
    with pytest.raises(RuntimeError):
        _run(CliOptions(query="q"), _StubAgent(error=RuntimeError("bug")))


# --- Trace lines -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("record", "line"),
    [
        (_record(*_SEARCH), '[Tool: search_filing(item="8") "research and development expense"]'),
        (
            _record("search_filing", {"query": "risk factors"}),
            '[Tool: search_filing "risk factors"]',
        ),
        (_record("get_passage", {"reference": "Note 5"}), '[Tool: get_passage "Note 5"]'),
        (_record("web_search", {"query": "MSFT margin"}), '[Tool: web_search "MSFT margin"]'),
        (
            _record("calculate", {"expression": "1 + 2"}, '{"expression": "1 + 2", "result": 3}'),
            "[Tool: calculate] 1 + 2 = 3",
        ),
        (
            _record("calculate", {"expression": "1 / 0"}, "Division by zero.", is_error=True),
            '[Tool error: calculate "1 / 0" — Division by zero.]',
        ),
        (
            _record("lookup", {"ticker": "MSFT", "n": 2}, "Unknown tool: lookup", is_error=True),
            '[Tool error: lookup(ticker="MSFT", n=2) — Unknown tool: lookup]',
        ),
        (_record("lookup", {"ticker": "MSFT"}), '[Tool: lookup(ticker="MSFT")]'),
    ],
)
def test_tool_call_lines(record: ToolCallRecord, line: str) -> None:
    assert describe_outcome(record) == line


def test_long_or_multiline_arguments_and_errors_stay_on_one_short_line() -> None:
    record = _record("web_search", {"query": "word " * 100}, "line one\nline two " * 50, True)
    line = describe_outcome(record)
    assert "\n" not in line
    assert len(line) < 400
    assert "…" in line


def test_trace_printer_writes_each_event_as_it_arrives() -> None:
    out = io.StringIO()
    printer = TracePrinter(out)
    printer.on_plan(Plan.model_validate({"steps": [{"tool": "web_search", "purpose": "Look."}]}))
    assert out.getvalue() == "[Plan] 1) web_search — Look.\n"
    printer.on_tool_call(_record("web_search", {"query": "x"}))
    assert out.getvalue().endswith('[Tool: web_search "x"]\n')


# --- Options, startup and logging ------------------------------------------------------------


def test_options_default_to_the_interactive_prompt() -> None:
    assert parse_cli_args(_SUGGESTIONS, []) == CliOptions(
        quiet=False, rebuild_index=False, query=None
    )


@pytest.mark.parametrize(
    "argv",
    [["  hi ", "--quiet", "--rebuild-index"], ["--query", "  hi ", "--quiet", "--rebuild-index"]],
    ids=["positional", "query-alias"],
)
def test_a_question_comes_as_an_argument_or_with_query(argv: list[str]) -> None:
    assert parse_cli_args(_SUGGESTIONS, argv) == CliOptions(
        quiet=True, rebuild_index=True, query="hi"
    )


@pytest.mark.parametrize("argv", [["2"], ["--query", " 2 "]], ids=["positional", "query-alias"])
def test_a_number_argument_runs_that_suggestion(argv: list[str]) -> None:
    assert parse_cli_args(_SUGGESTIONS, argv) == CliOptions(
        query="Second suggestion?", announce_query=True
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["--query", "  "],
        ["  "],
        ["--verbose"],
        ["one", "two"],
        ["q", "--query", "q"],
        ["3"],
        ["0"],
        pytest.param(["9" * 5000], id="5000-digits"),
    ],
)
def test_invalid_usage_exits_with_status_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        parse_cli_args(_SUGGESTIONS, argv)
    assert exit_info.value.code == 2


def test_help_lists_the_usage_forms_and_the_suggestions(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        parse_cli_args(_SUGGESTIONS, ["--help"])
    help_text = capsys.readouterr().out
    assert exit_info.value.code == 0
    for form in ("finassist ", 'finassist "QUESTION"', "finassist 1", "--quiet", "--rebuild-index"):
        assert form in help_text
    assert "  1) First suggestion?\n  2) Second suggestion?\n" in help_text


def test_missing_api_key_is_one_startup_line_naming_the_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    empty_env = tmp_path / ".env"
    empty_env.write_text("")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    status = main(
        ["--query", "q"],
        load_settings=lambda: Settings.load(empty_env),
        load_filing=lambda: _APPLE_FILING,
    )

    captured = capsys.readouterr()
    assert status == EXIT_CONFIG_ERROR
    assert captured.out == ""
    assert captured.err.count("\n") == 1
    assert captured.err.startswith("Error: Required setting ANTHROPIC_API_KEY is not set.")


@pytest.mark.parametrize("contents", [None, "# no questions\n"], ids=["missing", "empty"])
def test_unusable_suggestions_are_one_startup_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], contents: str | None
) -> None:
    if contents is not None:
        (tmp_path / "suggested_questions.txt").write_text(contents)

    status = main(
        ["--help"],
        load_filing=lambda: _APPLE_FILING,
        load_suggestions=lambda filing: load_suggested_questions(filing, tmp_path),
    )

    captured = capsys.readouterr()
    assert (status, captured.out) == (EXIT_CONFIG_ERROR, "")
    assert captured.err.count("\n") == 1
    assert captured.err.startswith("Error: cannot load the suggested questions: ")


def test_an_index_that_cannot_be_opened_is_one_startup_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing_build(*_: object) -> ResearchAgent:
        raise EmbedderError("Cannot load the embedding model: offline")

    monkeypatch.setattr(main_module, "build_agent", failing_build)
    monkeypatch.setattr(main_module, "configure_logging", lambda level: None)
    settings = Settings.from_mapping({"ANTHROPIC_API_KEY": "a", "TAVILY_API_KEY": "t"})

    status = main(
        ["--query", "q"], load_settings=lambda: settings, load_filing=lambda: _APPLE_FILING
    )

    captured = capsys.readouterr()
    assert (status, captured.out) == (EXIT_FAILURE, "")
    assert captured.err == (
        "Error: cannot open the Filing index: Cannot load the embedding model: offline\n"
    )


def _main_with_agent(monkeypatch: pytest.MonkeyPatch, agent: _StubAgent, argv: list[str]) -> int:
    monkeypatch.setattr(main_module, "build_agent", lambda *_: agent)
    monkeypatch.setattr(main_module, "configure_logging", lambda level: None)
    settings = Settings.from_mapping({"ANTHROPIC_API_KEY": "a", "TAVILY_API_KEY": "t"})
    return main(argv, load_settings=lambda: settings)


@pytest.mark.parametrize("argv", [["q"], ["--query", "q"]], ids=["positional", "query-alias"])
@pytest.mark.parametrize(
    ("agent", "status"),
    [
        (_StubAgent(result=_result(CitedAnswer(body="Hi.", sources=()))), EXIT_OK),
        (_StubAgent(error=ChatModelError("down")), EXIT_FAILURE),
    ],
    ids=["answered", "api-failure"],
)
def test_a_positional_question_exits_like_query(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], agent: _StubAgent, status: int
) -> None:
    assert _main_with_agent(monkeypatch, agent, argv) == status


def test_a_cancelled_query_exits_130_at_once_without_waiting_for_tool_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exits: list[int] = []

    def fake_exit(status: int) -> None:
        exits.append(status)
        raise SystemExit(status)

    monkeypatch.setattr(main_module.os, "_exit", fake_exit)
    with pytest.raises(SystemExit):
        _main_with_agent(monkeypatch, _StubAgent(error=KeyboardInterrupt()), ["--query", "q"])
    assert exits == [EXIT_INTERRUPTED]


def test_an_index_error_during_a_question_is_not_reported_as_a_startup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _StubAgent(error=EmbedderError("Embedding the query failed"))
    with pytest.raises(EmbedderError):
        _main_with_agent(monkeypatch, agent, ["--query", "q"])


@pytest.fixture
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def _passes(record_logger: str, level: int) -> bool:
    record = logging.LogRecord(record_logger, level, __file__, 1, "message", None, None)
    return all(handler.filter(record) for handler in logging.getLogger().handlers)


@pytest.mark.usefixtures("restore_logging")
def test_library_records_below_warning_are_dropped_and_the_apps_are_kept() -> None:
    configure_logging("INFO")
    assert not _passes("httpx", logging.INFO)
    assert not _passes("chromadb.api.segment", logging.INFO)
    assert _passes("httpx", logging.WARNING)
    assert _passes("utils.filing_index_loader", logging.INFO)
    assert _passes("agent", logging.INFO)
    assert _passes("cli.repl", logging.INFO)
    assert logging.getLogger().level == logging.INFO


@pytest.mark.usefixtures("restore_logging")
def test_debug_shows_library_records_too() -> None:
    configure_logging("DEBUG")
    assert _passes("httpx", logging.DEBUG)
    assert not any(
        isinstance(f, LibraryNoiseFilter) for h in logging.getLogger().handlers for f in h.filters
    )


# --- The finassist command, from any directory ----------------------------------------------


def test_the_shipped_suggestions_start_with_the_two_assignment_queries() -> None:
    questions = load_suggested_questions(_APPLE_FILING).questions
    assert questions[0].startswith("What are Apple's top 3 risk factors")
    assert questions[1].startswith("How does Apple's gross margin compare to Microsoft's")
    assert len(questions) >= 6  # Filing-only, web-only, cross-reference and calculation too


def test_finassist_is_declared_as_the_main_function() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject:
        scripts = tomllib.load(pyproject)["project"]["scripts"]
    module, _, function = scripts["finassist"].partition(":")
    assert getattr(importlib.import_module(module), function) is main


def test_files_resolve_against_the_project_root_from_another_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_mapping(
        {"ANTHROPIC_API_KEY": "a", "TAVILY_API_KEY": "t", "INDEX_DIR": ".index"}
    )
    assert settings.filing.path == PROJECT_ROOT / DEFAULT_FILING_PATH
    assert settings.filing.path.is_file()
    assert settings.index_dir == PROJECT_ROOT / ".index"
    assert DEFAULT_ENV_FILE == PROJECT_ROOT / ".env"
    assert load_suggested_questions(settings.filing).questions  # prompts/ is found too


def test_main_py_runs_from_another_directory(tmp_path: Path) -> None:
    """`python src/main.py --help` (what `finassist --help` runs) needs no keys and no CWD."""
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "src" / "main.py"), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr  # stderr may carry library import noise
    assert "usage: finassist" in completed.stdout
    assert "  1) What are Apple's top 3 risk factors" in completed.stdout


# --- The configured company (issue #35) ------------------------------------------------------


def test_the_banner_names_the_configured_company_and_fiscal_year() -> None:
    assert welcome_title("Apple Inc.", 2025) == (
        "Financial Research Assistant — Apple Inc. 10-K (FY2025) + web search"
    )
    assert "Contoso Ltd. 10-K (FY2026)" in welcome_title("Contoso Ltd.", 2026)


@pytest.mark.parametrize(
    ("company", "filer"),
    [("Contoso Ltd.", "Contoso Ltd.'s 10-K"), (None, "the company's 10-K")],
    ids=["configured", "settings-not-loaded"],
)
def test_help_names_the_configured_company_or_a_generic_one(
    capsys: pytest.CaptureFixture[str], company: str | None, filer: str
) -> None:
    with pytest.raises(SystemExit):
        parse_cli_args(_SUGGESTIONS, ["--help"], company)
    help_text = " ".join(capsys.readouterr().out.split())
    assert f"Answer questions about {filer} filing" in help_text
    assert "Apple" not in help_text


def test_help_for_another_company_lists_questions_written_for_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"], load_filing=lambda: _OTHER_FILING)
    help_text = " ".join(capsys.readouterr().out.split())
    assert exit_info.value.code == EXIT_OK
    assert "about Contoso Ltd.'s 10-K filing" in help_text
    assert "1) What are Contoso Ltd.'s top 3 risk factors" in help_text
    assert "Apple" not in help_text


def test_help_works_with_unloadable_settings_in_generic_wording(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unloadable() -> FilingProfile:
        raise ConfigError("FILING_FISCAL_YEAR must be a four-digit year")

    with pytest.raises(SystemExit) as exit_info:
        main(["--help"], load_filing=unloadable)

    help_text = " ".join(capsys.readouterr().out.split())
    assert exit_info.value.code == EXIT_OK
    assert "about the company's 10-K filing" in help_text
    assert "1) What are the company's top 3 risk factors" in help_text


def test_another_company_without_a_questions_file_gets_the_generic_list() -> None:
    questions = load_suggested_questions(_OTHER_FILING).questions
    assert questions[0].startswith("What are Contoso Ltd.'s top 3 risk factors")
    assert len(questions) >= 6
    assert not any("Apple" in question or "{{" in question for question in questions)


@pytest.mark.parametrize(
    ("values", "first"),
    [
        ({"FILING_COMPANY": "Apple"}, "What are Apple's top 3 risk factors"),
        (
            {
                "FILING_PATH": str(PROJECT_ROOT / "data" / ".." / DEFAULT_FILING_PATH),
                "FILING_COMPANY": "Apple Inc.",
            },
            "What are Apple's top 3 risk factors",
        ),
        (
            {
                "FILING_PATH": "data/apple_10k_2024.htm",
                "FILING_COMPANY": "Apple Inc.",
                "FILING_FISCAL_YEAR": "2024",
            },
            "What are Apple Inc.'s top 3 risk factors",
        ),
    ],
    ids=["shipped-filing-renamed", "shipped-filing-respelled", "other-apple-filing"],
)
def test_the_shipped_list_follows_the_shipped_filing_not_the_company_name(
    values: dict[str, str], first: str
) -> None:
    """The shipped list asks about FY2025 and its Note 7, so only the shipped Filing gets it."""
    assert (
        load_suggested_questions(FilingProfile.from_mapping(values)).questions[0].startswith(first)
    )


def test_a_configured_questions_file_is_used_for_any_company(tmp_path: Path) -> None:
    listed = tmp_path / "contoso_questions.txt"
    listed.write_text("# Contoso's own list\nHow big is the widget backlog?\n")
    filing = FilingProfile.from_mapping(
        {"SUGGESTED_QUESTIONS_PATH": str(listed), "FILING_COMPANY": "Contoso Ltd."}
    )
    assert load_suggested_questions(filing).questions == ("How big is the widget backlog?",)


def test_an_unreadable_questions_file_is_one_startup_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    filing = FilingProfile.from_mapping({"SUGGESTED_QUESTIONS_PATH": str(tmp_path / "none.txt")})
    with pytest.raises(SuggestedQuestionsFileError, match="SUGGESTED_QUESTIONS_PATH"):
        load_suggested_questions(filing)

    status = main(["--help"], load_filing=lambda: filing)

    captured = capsys.readouterr()
    assert (status, captured.out) == (EXIT_CONFIG_ERROR, "")
    assert captured.err.startswith("Error: cannot load the suggested questions: ")
    assert captured.err.count("\n") == 1
