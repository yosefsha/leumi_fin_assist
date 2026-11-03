"""The two required queries from docs/TASKS.md, end to end against Anthropic and Tavily (#11).

These are `live` tests: they run only with `RUN_LIVE_TESTS=true` (ADR-0004) and
spend tokens and Tavily quota. They assert the structure of the run (which tools,
scoped to which Items, which sources the answer cites) and the figures the
answer gives, never its wording. Expected figures are computed here from the
parsed income statement, not hardcoded.

Each test collects every failed check and reports them together with the plan,
trace and answer, so a failing CI log says what the agent actually did.
"""

import re
from collections.abc import Iterable

import pytest

from agent import ResearchAgent
from agent_factory import build_agent
from tools.tavily_search import NO_RESULTS_PREFIX
from utils.agent_result import AgentResult, ToolCallRecord
from utils.config import Settings
from utils.cross_reference_resolver import CrossReferenceResolver, UnknownReferenceError
from utils.filing_items import parse_item_label
from utils.passage import Passage, PassageKind

# The required queries, word for word from docs/TASKS.md, and what each run must show.
QUERY_1 = (
    "What are Apple's top 3 risk factors mentioned in their latest 10-K, "
    "and what percentage of total revenue did they spend on R&D?"
)
QUERY_2 = (
    "How does Apple's gross margin compare to Microsoft's current gross margin, "
    "and what reasons does Apple cite in their 10-K for any margin pressure?"
)
RISK_FACTOR_COUNT = 3
PERCENT_TOLERANCE_PP = 0.1
"""How far (in percentage points) the answer's figure may be from the one computed here."""

INCOME_STATEMENT = "CONSOLIDATED STATEMENTS OF OPERATIONS"
TOTAL_NET_SALES = "Total net sales"
RESEARCH_AND_DEVELOPMENT = "Research and development"
GROSS_MARGIN = "Gross margin"

_FILING_SOURCE = re.compile(r"^10-K FY\d{4} — (?P<item>Item \w+)\b")
_WEB_SOURCE = re.compile(r"https?://")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b)")
_NUMBER = re.compile(r"[\d,]+(?:\.\d+)?")

pytestmark = pytest.mark.live


@pytest.fixture(scope="session")
def agent() -> ResearchAgent:
    """The agent as the CLI builds it: real Anthropic, Tavily and the on-disk index."""
    return build_agent(Settings.load())


@pytest.fixture(scope="session")
def income_statement(passages: tuple[Passage, ...]) -> Passage:
    """Item 8's Consolidated Statements of Operations table, as parsed from the Filing."""
    [table] = [
        passage
        for passage in passages
        if passage.item == "Item 8"
        and passage.kind is PassageKind.TABLE
        and passage.section_path[-1] == INCOME_STATEMENT
    ]
    return table


@pytest.fixture(scope="session")
def reference_resolver(passages: tuple[Passage, ...]) -> CrossReferenceResolver:
    """Resolves the agent's `get_passage` references to the Passages it fetched."""
    return CrossReferenceResolver(passages)


def test_query_1_risk_factors_and_rd_share(
    agent: ResearchAgent,
    income_statement: Passage,
    reference_resolver: CrossReferenceResolver,
) -> None:
    rd_share = _share(income_statement, RESEARCH_AND_DEVELOPMENT)
    result = agent.answer(QUERY_1)
    _print_summary(result)
    checks = _Checks()
    _check_run_completed(checks, result)

    searched = _items_searched(result.trace)
    checks.expect("Item 8" in searched, f"search_filing scoped to Item 8 (searched: {searched})")
    fetched = _items_fetched(result.trace, reference_resolver)
    checks.expect(
        "Item 1A" in searched | fetched,
        "Item 1A consulted via search_filing(item='1A') or get_passage "
        f"(searched: {searched}, fetched: {fetched})",
    )
    checks.expect(_called(result.trace, "calculate"), "calculate called")

    cited = _cited_items(result.answer.sources)
    risk_sources = sum(1 for item in cited if item == "Item 1A")
    checks.expect(
        risk_sources >= RISK_FACTOR_COUNT,
        f"at least {RISK_FACTOR_COUNT} distinct Item 1A Sources, one per risk factor "
        f"(got {risk_sources})",
    )
    checks.expect("Item 8" in cited, f"Sources cite Item 8 (cited: {cited})")
    _check_percentage(checks, result.answer.body, rd_share, "R&D share of total net sales")
    checks.report(result)


def test_query_2_gross_margin_vs_microsoft(agent: ResearchAgent, income_statement: Passage) -> None:
    gross_margin = _share(income_statement, GROSS_MARGIN)
    result = agent.answer(QUERY_2)
    _print_summary(result)
    checks = _Checks()
    _check_run_completed(checks, result)

    searched = _items_searched(result.trace)
    for item in ("Item 8", "Item 7"):
        checks.expect(item in searched, f"search_filing scoped to {item} (searched: {searched})")
    checks.expect(_called(result.trace, "web_search"), "web_search called")

    sources = result.answer.sources
    checks.expect(bool(_cited_items(sources)), "Sources cite at least one Filing Passage")
    checks.expect(
        any(_WEB_SOURCE.search(source) for source in sources),
        "Sources cite at least one web result",
    )
    checks.expect("microsoft" in result.answer.body.casefold(), "the answer mentions Microsoft")
    _check_percentage(checks, result.answer.body, gross_margin, "Apple's gross margin")
    checks.report(result)


class _Checks:
    """Collects failed checks so one assertion reports them all, with the run attached."""

    def __init__(self) -> None:
        self._failures: list[str] = []

    def expect(self, condition: bool, description: str) -> None:
        if not condition:
            self._failures.append(description)

    def report(self, result: AgentResult) -> None:
        failures = "\n".join(f"- {failure}" for failure in self._failures)
        assert not self._failures, f"Failed checks:\n{failures}\n\n{_describe(result)}"


def _check_run_completed(checks: _Checks, result: AgentResult) -> None:
    checks.expect(not result.hit_round_limit, "the run finished within the tool-round limit")
    checks.expect(not result.answer_truncated, "the answer was not truncated")
    errors = [f"{call.name} {dict(call.args)}" for call in result.trace if _unexpected_error(call)]
    checks.expect(not errors, f"no tool call failed unexpectedly (failed: {errors})")


def _unexpected_error(call: ToolCallRecord) -> bool:
    """A failed call, other than a web search that found nothing (the agent retries those)."""
    return call.is_error and not (
        call.name == "web_search" and call.output.startswith(NO_RESULTS_PREFIX)
    )


def _check_percentage(checks: _Checks, body: str, expected: float, what: str) -> None:
    found = [float(value) for value in _PERCENT.findall(body)]
    checks.expect(
        any(abs(value - expected) <= PERCENT_TOLERANCE_PP for value in found),
        f"{what} {expected:.2f}% ±{PERCENT_TOLERANCE_PP}pp in the answer (percentages: {found})",
    )


def _share(income_statement: Passage, line_item: str) -> float:
    """`line_item` as a percentage of total net sales for the latest fiscal year."""
    return (
        100
        * _latest_value(income_statement, line_item)
        / _latest_value(income_statement, TOTAL_NET_SALES)
    )


def _latest_value(table: Passage, line_item: str) -> float:
    """The first (latest-year) figure on `line_item`'s row of a Markdown table."""
    for line in table.content.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == line_item and len(cells) > 1:
            number = _NUMBER.search(cells[1])
            if number is not None:
                return float(number.group().replace(",", ""))
    raise AssertionError(f"No {line_item!r} figure in {table.passage_id}")


def _called(trace: Iterable[ToolCallRecord], tool: str) -> bool:
    return any(call.name == tool and call.ok for call in trace)


def _items_searched(trace: Iterable[ToolCallRecord]) -> set[str]:
    """The Items successful `search_filing` calls were scoped to, e.g. `{"Item 8"}`."""
    return {
        item
        for call in trace
        if call.name == "search_filing" and call.ok and isinstance(call.args.get("item"), str)
        if (item := parse_item_label(call.args["item"])) is not None
    }


def _items_fetched(trace: Iterable[ToolCallRecord], resolver: CrossReferenceResolver) -> set[str]:
    """The Items successful `get_passage` calls fetched from (an Item, Note or passage_id)."""
    items: set[str] = set()
    for call in trace:
        if call.name != "get_passage" or not call.ok:
            continue
        try:
            items.add(resolver.resolve(str(call.args.get("reference", ""))).passage.item)
        except UnknownReferenceError:
            continue
    return items


def _cited_items(sources: Iterable[str]) -> list[str]:
    """The Item of each Filing source in the Sources list, in order (one per source)."""
    return [match["item"] for source in sources if (match := _FILING_SOURCE.match(source))]


def _describe(result: AgentResult) -> str:
    """The plan, trace and answer, for a failure message or the `-s` run log."""
    trace = "\n".join(_trace_line(call) for call in result.trace)
    return (
        f"QUESTION: {result.question}\n\nPLAN:\n{result.plan.numbered()}\n\n"
        f"TRACE:\n{trace}\n\n"
        f"hit_round_limit={result.hit_round_limit} answer_truncated={result.answer_truncated}"
        f"\n\nANSWER:\n{result.answer.text}"
    )


def _trace_line(call: ToolCallRecord) -> str:
    if call.is_error:
        outcome = "ERROR: " + _first_line(call.output)
    else:
        outcome = ", ".join(call.citation_ids) or _first_line(call.output)
    return f"[round {call.round}] {call.name} {dict(call.args)} -> {outcome}"


def _first_line(text: str, limit: int = 160) -> str:
    lines = text.strip().splitlines()
    return lines[0][:limit] if lines else ""


def _print_summary(result: AgentResult) -> None:
    """Print the run, so `pytest -s` shows what the agent did even when it passes."""
    print(f"\n{'=' * 80}\n{_describe(result)}\n{'=' * 80}")
