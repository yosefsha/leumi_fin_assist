"""The agent loop's deterministic behaviour (issue #9), driven by a scripted `ChatModel`.

These tests script the model's turns to check what the loop does with them: the
round cap, error results, parallel calls, citation IDs and the plan. They do not
assert which tools a real model would choose (ADR-0004); the live tier does that.
"""

import json
import os
import re
import signal
import threading
import time
from collections.abc import Mapping
from datetime import date
from typing import Any

import pytest
from anthropic.types import TextBlock

from agent import MAX_TOOL_ROUNDS, ResearchAgent
from agent_factory import build_tool_registry
from fakes.scripted_chat_model import ScriptedChatModel, text_reply, tool_reply
from fakes.scripted_web_search_client import ScriptedWebSearchClient
from tools.calculator import CalculateTool
from tools.registry import ToolOutput, ToolRegistry
from utils.agent_result import EvidenceCheck, ToolCallRecord
from utils.chat_model import ChatModelError, ChatModelRefusalError, IncompleteReplyError, ModelReply
from utils.citation_format import CitationFormatter
from utils.cited_answer import CitationResolver
from utils.evidence_review import EvidenceReview
from utils.filing_index import FilingIndex
from utils.passage import Passage, PassageKind
from utils.plan import Plan
from utils.prompts import load_prompt
from utils.tool_result_citer import ToolResultCiter
from utils.web_result import WebResult

_PASSAGE = Passage(
    passage_id="item-8-003",
    item="Item 8",
    section_path=("Item 8", "CONSOLIDATED STATEMENTS OF OPERATIONS"),
    page=29,
    kind=PassageKind.TABLE,
    content="| Research and development | $ 34,550 |",
)
_WEB = WebResult(
    url="https://www.microsoft.com/en-us/investor",
    title="Microsoft earnings",
    content="Gross margin was 69% in the quarter ended September 30, 2025.",
)
_PLAN = Plan.model_validate(
    {"steps": [{"tool": "search_filing", "purpose": "Find R&D expense in Item 8."}]}
)


class _StaticTool:
    """A tool that returns the same output for every call and records its arguments."""

    def __init__(self, name: str, output: ToolOutput) -> None:
        self._name = name
        self._output = output
        self.calls: list[Mapping[str, Any]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"The {self._name} test tool."

    @property
    def input_schema(self) -> Mapping[str, Any]:
        return {"type": "object", "properties": {}}

    def run(self, args: Mapping[str, Any]) -> ToolOutput:
        self.calls.append(args)
        return self._output


class _RendezvousTool(_StaticTool):
    """Returns only once `parties` calls are running at the same time."""

    def __init__(self, name: str, barrier: threading.Barrier) -> None:
        super().__init__(name, ToolOutput(content=f"{name} done"))
        self._barrier = barrier

    def run(self, args: Mapping[str, Any]) -> ToolOutput:
        self._barrier.wait()
        return super().run(args)


class _RaisingTool(_StaticTool):
    def run(self, args: Mapping[str, Any]) -> ToolOutput:
        raise RuntimeError("bug")


class _Recorder:
    """An `AgentObserver` that records events in order."""

    def __init__(self) -> None:
        self.events: list[Plan | ToolCallRecord | EvidenceCheck] = []

    def on_plan(self, plan: Plan) -> None:
        self.events.append(plan)

    def on_tool_call(self, record: ToolCallRecord) -> None:
        self.events.append(record)

    def on_evidence_check(self, check: EvidenceCheck) -> None:
        self.events.append(check)


def _registry(*tools: _StaticTool | CalculateTool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def _agent(
    model: ScriptedChatModel, registry: ToolRegistry, observer: _Recorder | None = None
) -> ResearchAgent:
    formatter = CitationFormatter(fiscal_year=2025)
    return ResearchAgent(
        model=model,
        tools=registry,
        citer=ToolResultCiter(formatter),
        resolver=CitationResolver(formatter),
        fiscal_year=2025,
        observer=observer,
        today=lambda: date(2026, 11, 3),
    )


def _tool_results(model: ScriptedChatModel, call_index: int) -> list[dict[str, Any]]:
    """The tool_result blocks in the last user message of the `call_index`-th respond call."""
    content = model.respond_calls[call_index].messages[-1]["content"]
    assert isinstance(content, list)
    return [block for block in content if block["type"] == "tool_result"]


def test_round_cap_stops_tools_and_asks_for_an_answer_with_what_it_has() -> None:
    calculate = ("calculate", {"expression": "1 + 1"})
    model = ScriptedChatModel(
        [tool_reply(calculate)] * MAX_TOOL_ROUNDS + [text_reply("Partial answer; R&D missing.")]
    )

    result = _agent(model, _registry(CalculateTool())).answer("question")

    assert result.hit_round_limit
    assert len(result.trace) == MAX_TOOL_ROUNDS
    assert [call.allow_tool_calls for call in model.respond_calls] == [True] * MAX_TOOL_ROUNDS + [
        False
    ]
    last_turn = model.respond_calls[-1].messages[-1]["content"]
    assert last_turn[-1] == {"type": "text", "text": load_prompt("round_limit").strip()}
    assert result.answer.body == "Partial answer; R&D missing."


def test_an_answer_within_the_cap_is_not_flagged() -> None:
    model = ScriptedChatModel([tool_reply(("calculate", {"expression": "2 * 3"})), text_reply("6")])
    result = _agent(model, _registry(CalculateTool())).answer("question")
    assert not result.hit_round_limit
    assert [record.name for record in result.trace] == ["calculate"]
    assert _tool_results(model, 1)[0]["content"] == '{"expression": "2 * 3", "result": 6}'


def test_tool_failures_go_back_to_the_model_as_error_results() -> None:
    model = ScriptedChatModel(
        [
            tool_reply(
                ("calculate", {"expression": "1 / 0"}),
                ("no_such_tool", {}),
                ("broken", {}),
            ),
            text_reply("Could not compute."),
        ]
    )
    registry = _registry(CalculateTool(), _RaisingTool("broken", ToolOutput("unused")))

    result = _agent(model, registry).answer("question")

    results = _tool_results(model, 1)
    assert [block["is_error"] for block in results] == [True, True, True]
    assert "zero" in results[0]["content"].lower()
    assert results[1]["content"].startswith("Unknown tool 'no_such_tool'")
    assert results[2]["content"] == "Tool broken failed unexpectedly (RuntimeError)."
    assert [record.ok for record in result.trace] == [False, False, False]
    assert result.trace[1].output == results[1]["content"]


def test_parallel_tool_calls_run_concurrently_and_are_all_answered_in_one_message() -> None:
    barrier = threading.Barrier(3, timeout=5)
    tools = [_RendezvousTool(name, barrier) for name in ("alpha", "beta", "gamma")]
    model = ScriptedChatModel(
        [tool_reply(("alpha", {"n": 1}), ("beta", {"n": 2}), ("gamma", {"n": 3})), text_reply("ok")]
    )

    result = _agent(model, _registry(*tools)).answer("question")

    # The barrier only releases when all three calls are in flight at once.
    results = _tool_results(model, 1)
    assert [block["tool_use_id"] for block in results] == ["call_1", "call_2", "call_3"]
    assert [block["content"] for block in results] == ["alpha done", "beta done", "gamma done"]
    assert [(r.name, r.args) for r in result.trace] == [
        ("alpha", {"n": 1}),
        ("beta", {"n": 2}),
        ("gamma", {"n": 3}),
    ]


class _CtrlCTool(_StaticTool):
    """Sends this process SIGINT (Ctrl-C) while the main thread waits for the round."""

    def run(self, args: Mapping[str, Any]) -> ToolOutput:
        time.sleep(0.1)
        os.kill(os.getpid(), signal.SIGINT)
        return super().run(args)


class _BlockingTool(_StaticTool):
    """Blocks until `release` is set, like a slow web request."""

    def __init__(self, name: str, release: threading.Event) -> None:
        super().__init__(name, ToolOutput(content=f"{name} done"))
        self._release = release

    def run(self, args: Mapping[str, Any]) -> ToolOutput:
        self._release.wait(timeout=10)
        return super().run(args)


def test_an_interrupt_during_a_tool_round_does_not_wait_for_calls_in_flight() -> None:
    release = threading.Event()
    tools = [_CtrlCTool("stop", ToolOutput(content="")), _BlockingTool("slow", release)]
    model = ScriptedChatModel([tool_reply(("stop", {}), ("slow", {}))])
    started = time.monotonic()
    try:
        with pytest.raises(KeyboardInterrupt):
            _agent(model, _registry(*tools)).answer("question")
        assert time.monotonic() - started < 5  # the slow call blocks for 10 s
    finally:
        release.set()


def test_sources_get_citation_ids_before_the_model_sees_them() -> None:
    filing = _StaticTool("search_filing", ToolOutput(content='{"found": 1}', sources=(_PASSAGE,)))
    web = _StaticTool("web_search", ToolOutput(content='{"found": 1}', sources=(_WEB,)))
    model = ScriptedChatModel(
        [
            tool_reply(("search_filing", {}), ("web_search", {})),
            tool_reply(("search_filing", {})),
            text_reply("R&D was $34,550M [F1]. Microsoft's margin was 69% [W1] [W7] [F2]."),
        ]
    )

    result = _agent(model, _registry(filing, web)).answer("question")

    first, second = _tool_results(model, 1)
    assert first["content"] == (
        '{"found": 1}\n\n[F1] Item 8 > CONSOLIDATED STATEMENTS OF OPERATIONS — p. 29 '
        "(passage_id item-8-003, table)\n| Research and development | $ 34,550 |"
    )
    assert second["content"].startswith(
        '{"found": 1}\n\n[W1] Microsoft earnings — https://www.microsoft.com/en-us/investor '
        "(date unknown)\n"
    )
    # The same Passage found again keeps its ID and is not resent in full.
    assert _tool_results(model, 2)[0]["content"] == (
        '{"found": 1}\n\n[F1] Item 8 > CONSOLIDATED STATEMENTS OF OPERATIONS — p. 29 '
        "(passage_id item-8-003, table) (content shown above)"
    )
    assert [record.citation_ids for record in result.trace] == [("F1",), ("W1",), ("F1",)]
    # Unknown markers ([W7], [F2]) are dropped; the rest are renumbered with Sources.
    assert result.answer.body == "R&D was $34,550M [1]. Microsoft's margin was 69% [2]."
    assert result.answer.sources == (
        "10-K FY2025 — Item 8 > CONSOLIDATED STATEMENTS OF OPERATIONS, p. 29",
        "Microsoft earnings — https://www.microsoft.com/en-us/investor (date unknown)",
    )


def test_each_question_gets_a_fresh_citation_registry() -> None:
    web = _StaticTool("web_search", ToolOutput(content="", sources=(_WEB,)))
    other = WebResult(url="https://example.com/other", title="Other", content="x")
    other_tool = _StaticTool("other_search", ToolOutput(content="", sources=(other,)))
    model = ScriptedChatModel(
        [
            tool_reply(("web_search", {})),
            text_reply("A [W1]."),
            tool_reply(("other_search", {})),
            text_reply("B [W1]."),
        ]
    )
    agent = _agent(model, _registry(web, other_tool))

    agent.answer("first")
    second = agent.answer("second")

    assert second.trace[0].citation_ids == ("W1",)
    assert second.answer.sources == ("Other — https://example.com/other (date unknown)",)


def test_the_plan_is_reported_before_tools_run_and_given_to_the_executor() -> None:
    observer = _Recorder()
    model = ScriptedChatModel(
        [tool_reply(("calculate", {"expression": "1 + 2"})), text_reply("3")],
        plan_json=_PLAN.model_dump_json(),
    )

    result = _agent(model, _registry(CalculateTool()), observer).answer("What is 1 + 2?")

    assert result.plan == _PLAN
    assert observer.events[0] == _PLAN
    assert isinstance(observer.events[1], ToolCallRecord)
    assert model.respond_calls[0].messages[0]["content"] == (
        "<question>\nWhat is 1 + 2?\n</question>\n\n"
        "<plan>\n1. search_filing — Find R&D expense in Item 8.\n</plan>"
    )


def test_the_planner_may_only_name_registered_tools() -> None:
    model = ScriptedChatModel([text_reply("answer")])
    _agent(model, _registry(CalculateTool())).answer("question")
    system, prompt, schema = model.json_requests[0]
    assert prompt == "question"
    assert schema["properties"]["steps"]["items"]["properties"]["tool"]["enum"] == ["calculate"]
    assert "### calculate" in system
    assert "2026-11-03" in system and "fiscal year 2025" in system


@pytest.mark.parametrize(
    "plan_json",
    [
        '{"steps": [{"tool": "calculate"}]}',
        "not json",
        ChatModelRefusalError("declined"),
        IncompleteReplyError("no complete JSON"),
    ],
    ids=["invalid-step", "not-json", "refusal", "incomplete"],
)
def test_an_unusable_plan_leaves_the_executor_without_one(
    plan_json: str | ChatModelError,
) -> None:
    model = ScriptedChatModel([text_reply("answer")], plan_json=plan_json)
    result = _agent(model, _registry(CalculateTool())).answer("question")
    assert result.plan == Plan()
    assert "<plan>" not in model.respond_calls[0].messages[0]["content"]


def test_a_model_failure_is_raised_as_a_chat_model_error() -> None:
    model = ScriptedChatModel([ChatModelError("Anthropic API returned HTTP 529.")])
    with pytest.raises(ChatModelError, match="529"):
        _agent(model, _registry(CalculateTool())).answer("question")


def test_a_planner_api_failure_is_raised_too() -> None:
    model = ScriptedChatModel([], plan_json=ChatModelError("Could not connect."))
    with pytest.raises(ChatModelError, match="connect"):
        _agent(model, _registry(CalculateTool())).answer("question")


def test_a_final_turn_without_text_is_an_error() -> None:
    model = ScriptedChatModel([text_reply("   ")])
    with pytest.raises(ChatModelError, match="without an answer"):
        _agent(model, _registry(CalculateTool())).answer("question")


def test_a_tool_call_cut_off_by_the_output_limit_is_an_error() -> None:
    cut_off = tool_reply(("calculate", {"expression": "1 +"}))
    model = ScriptedChatModel([ModelReply(content=cut_off.content, truncated=True)])
    with pytest.raises(ChatModelError, match="output limit"):
        _agent(model, _registry(CalculateTool())).answer("question")


def test_a_cut_off_answer_is_flagged() -> None:
    model = ScriptedChatModel([ModelReply(content=text_reply("1. First").content, truncated=True)])
    result = _agent(model, _registry(CalculateTool())).answer("question")
    assert result.answer_truncated
    assert result.answer.body == "1. First"


def test_text_blocks_are_joined_as_paragraphs() -> None:
    blocks = ("Net sales [F1].", "  ", "R&D.")
    reply = ModelReply(content=tuple(TextBlock(type="text", text=text) for text in blocks))
    assert reply.text == "Net sales [F1].\n\nR&D."


def test_an_empty_question_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        _agent(ScriptedChatModel([]), _registry(CalculateTool())).answer("  ")


def test_wired_tools_cite_the_income_statement_for_rd_expense(filing_index: FilingIndex) -> None:
    """The composition root's registry over the real index: search results arrive as [F#] blocks."""
    web = ScriptedWebSearchClient([[_WEB]])
    model = ScriptedChatModel(
        [
            tool_reply(
                ("search_filing", {"query": "research and development expense", "item": "8"}),
                ("web_search", {"query": "Microsoft gross margin latest quarter"}),
            ),
            text_reply("R&D [F1]; Microsoft [W1]."),
        ]
    )

    result = _agent(model, build_tool_registry(filing_index, web)).answer("question")

    search, web_result = _tool_results(model, 1)
    assert json.loads(search["content"].partition("\n\n")[0])["item"] == "Item 8"
    assert "\n\n[F1] Item 8 > CONSOLIDATED STATEMENTS OF OPERATIONS — p. 29" in search["content"]
    assert "[W1] Microsoft earnings" in web_result["content"]
    assert result.answer.sources[0].startswith(
        "10-K FY2025 — Item 8 > CONSOLIDATED STATEMENTS OF OPERATIONS"
    )


# --- The evidence check (#29) ----------------------------------------------------------------

_GAP = {
    "requirement": "Company-wide gross margin, latest quarter",
    "problem": "segment_not_company_wide",
    "retry_guidance": "Search the latest earnings release for revenue and cost of revenue.",
}
_GAP_REVIEW = json.dumps({"gaps": [_GAP], "sufficient": False})
_SUFFICIENT_REVIEW = '{"gaps": [], "sufficient": true}'


def _web_tool() -> _StaticTool:
    return _StaticTool("web_search", ToolOutput(content='{"found": 1}', sources=(_WEB,)))


def test_sufficient_evidence_answers_at_once_without_another_round() -> None:
    observer = _Recorder()
    model = ScriptedChatModel(
        [tool_reply(("web_search", {"query": "margin"})), text_reply("69% [W1].")],
        reviews=[_SUFFICIENT_REVIEW],
    )

    result = _agent(model, _registry(_web_tool()), observer).answer("question")

    assert len(model.respond_calls) == 2
    assert len(model.review_requests) == 1
    assert result.answer.body == "69% [1]."
    [check] = result.evidence_checks
    assert check.review is not None and check.review.sufficient
    assert observer.events[-1] == check


def test_the_check_sees_the_question_plan_cited_evidence_and_draft() -> None:
    model = ScriptedChatModel(
        [tool_reply(("web_search", {"query": "margin"})), text_reply("69% [W1].")],
        plan_json=_PLAN.model_dump_json(),
        reviews=[_SUFFICIENT_REVIEW],
    )

    _agent(model, _registry(_web_tool())).answer("What is the margin?")

    [(system, prompt, schema)] = model.review_requests
    assert "2026-11-03" in system and "fiscal year 2025" in system and "web_search" in system
    assert "<question>\nWhat is the margin?\n</question>" in prompt
    assert "1. search_filing — Find R&D expense in Item 8." in prompt
    assert '<tool_call round="1" name="web_search">' in prompt
    assert '<arguments>{"query": "margin"}</arguments>' in prompt
    assert "[W1] Microsoft earnings — https://www.microsoft.com/en-us/investor" in prompt
    assert "<draft_answer>\n69% [W1].\n</draft_answer>" in prompt
    assert schema == EvidenceReview.json_schema()


def test_gaps_go_back_to_the_model_and_tools_are_allowed_again() -> None:
    observer = _Recorder()
    model = ScriptedChatModel(
        [
            tool_reply(("web_search", {"query": "margin"})),
            text_reply("Only a segment margin was found [W1]."),
            tool_reply(("web_search", {"query": "earnings release revenue cost of revenue"})),
            text_reply("Company-wide margin [W1]."),
        ],
        reviews=[_GAP_REVIEW],
    )

    result = _agent(model, _registry(_web_tool()), observer).answer("question")

    retry_call = model.respond_calls[2]
    assert retry_call.allow_tool_calls
    retry_turn = retry_call.messages[-1]
    assert retry_turn["role"] == "user"
    assert retry_turn["content"].startswith("An evidence check of your draft answer found")
    assert (
        "1. Company-wide gross margin, latest quarter (segment_not_company_wide). Next: Search "
        "the latest earnings release for revenue and cost of revenue."
    ) in retry_turn["content"]
    assert [record.round for record in result.trace] == [1, 2]
    assert result.answer.body == "Company-wide margin [1]."
    [check] = result.evidence_checks
    assert check.found_gaps
    assert [type(event) for event in observer.events] == [
        Plan,
        ToolCallRecord,
        EvidenceCheck,
        ToolCallRecord,
    ]


def test_only_one_retry_per_question() -> None:
    # The fake fails the test on a second evidence check: only one review is scripted.
    model = ScriptedChatModel(
        [text_reply("Draft."), tool_reply(("calculate", {"expression": "1 + 1"})), text_reply("2")],
        reviews=[_GAP_REVIEW],
    )
    result = _agent(model, _registry(CalculateTool())).answer("question")
    assert len(model.review_requests) == 1
    assert result.answer.body == "2"


def test_a_retry_with_no_further_tool_use_returns_the_new_answer() -> None:
    model = ScriptedChatModel(
        [text_reply("Draft."), text_reply("Still nothing; the margin is missing.")],
        reviews=[_GAP_REVIEW],
    )
    result = _agent(model, _registry(CalculateTool())).answer("question")
    assert result.answer.body == "Still nothing; the margin is missing."
    assert result.trace == ()


@pytest.mark.parametrize(
    "review",
    [
        ChatModelError("Anthropic API returned HTTP 529."),
        ChatModelRefusalError("declined"),
        IncompleteReplyError("no complete JSON"),
        "not json",
        '{"gaps": [], "sufficient": false}',
        json.dumps({"gaps": [_GAP], "sufficient": True}),
        json.dumps({"gaps": [{**_GAP, "problem": "unknown"}], "sufficient": False}),
    ],
    ids=[
        "api-error",
        "refusal",
        "incomplete",
        "not-json",
        "insufficient-without-gaps",
        "sufficient-with-gaps",
        "unknown-problem",
    ],
)
def test_a_failed_check_keeps_the_draft(review: str | ChatModelError) -> None:
    observer = _Recorder()
    model = ScriptedChatModel([text_reply("Draft answer.")], reviews=[review])
    result = _agent(model, _registry(CalculateTool()), observer).answer("question")
    assert result.answer.body == "Draft answer."
    assert len(model.respond_calls) == 1
    [check] = result.evidence_checks
    assert check.failed
    assert observer.events[-1] == check


def test_no_check_once_the_round_budget_is_spent() -> None:
    calculate = ("calculate", {"expression": "1 + 1"})
    model = ScriptedChatModel(
        [tool_reply(calculate)] * MAX_TOOL_ROUNDS + [text_reply("Partial.")], reviews=[]
    )
    result = _agent(model, _registry(CalculateTool())).answer("question")
    assert model.review_requests == []
    assert result.evidence_checks == ()
    assert result.hit_round_limit


def test_retry_rounds_share_the_round_budget() -> None:
    calculate = ("calculate", {"expression": "1 + 1"})
    model = ScriptedChatModel(
        [tool_reply(calculate)] * (MAX_TOOL_ROUNDS - 1)
        + [text_reply("Draft."), tool_reply(calculate), text_reply("Final.")],
        reviews=[_GAP_REVIEW],
    )

    result = _agent(model, _registry(CalculateTool())).answer("question")

    assert len(result.trace) == MAX_TOOL_ROUNDS
    assert model.respond_calls[-1].allow_tool_calls is False
    last_turn = model.respond_calls[-1].messages[-1]["content"]
    assert last_turn[-1] == {"type": "text", "text": load_prompt("round_limit").strip()}
    assert result.answer.body == "Final."
    assert result.hit_round_limit


@pytest.mark.parametrize("name", ["evidence_check_prompt", "evidence_retry"])
def test_evidence_prompts_name_no_source_or_competitor(name: str) -> None:
    text = load_prompt(name).lower()
    assert not re.search(r"https?://|www\.|\.com\b|\.org\b|microsoft|macrotrends|yahoo", text)
