"""The research agent: a planning call, then a native tool-use execution loop (issue #9)."""

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from anthropic.types import MessageParam, TextBlockParam, ToolResultBlockParam, ToolUseBlock

from tools.registry import ToolOutput, ToolRegistry
from utils.agent_observer import AgentObserver, SilentObserver
from utils.agent_result import AgentResult, ToolCallRecord
from utils.chat_model import ChatModel, ChatModelError, ModelReply
from utils.citations import CitationRegistry
from utils.cited_answer import CitationResolver
from utils.plan import Plan
from utils.planner import Planner
from utils.prompts import load_prompt, render_prompt
from utils.tool_result_citer import ToolResultCiter

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8
SYSTEM_PROMPT = "system_prompt"
ROUND_LIMIT_PROMPT = "round_limit"


class ResearchAgent:
    """Answers one question at a time from the Filing and the web, with citations.

    1. The `Planner` proposes a Plan, reported to the observer before any tool runs.
    2. The executor converses with the model using the registry's tools. Every
       `tool_use` block of a turn runs concurrently and all results go back in one
       message. Each result's sources get citation IDs from a registry created
       fresh for the question, before the model sees them.
    3. After `MAX_TOOL_ROUNDS` rounds of tool calls, the model is told to answer
       with what it has and name the gaps, and may call no more tools.
    4. The final text's citation markers are checked against the registry; unknown
       ones are dropped and the rest become a numbered Sources list.

    A tool failure is an `is_error` tool result for the model to work around. A
    model failure (after the client's retries), a refusal, a tool call cut off by
    the output limit, or a final turn with no text raises `ChatModelError`. A final
    answer cut off by the output limit is returned with `answer_truncated` set.
    """

    def __init__(
        self,
        model: ChatModel,
        tools: ToolRegistry,
        citer: ToolResultCiter,
        resolver: CitationResolver,
        fiscal_year: int,
        observer: AgentObserver | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._model = model
        self._tools = tools
        self._citer = citer
        self._resolver = resolver
        self._fiscal_year = fiscal_year
        self._planner = Planner(model, fiscal_year)
        self._observer = observer or SilentObserver()
        self._today = today

    def answer(self, question: str) -> AgentResult:
        """Plan, gather evidence with tools, and return the cited answer to `question`."""
        question = question.strip()
        if not question:
            raise ValueError("The question is empty.")
        today = self._today()
        definitions = self._tools.definitions()

        plan = self._planner.plan(question, definitions, today)
        self._observer.on_plan(plan)

        system = render_prompt(
            SYSTEM_PROMPT, {"fiscal_year": str(self._fiscal_year), "today": today.isoformat()}
        )
        registry = CitationRegistry()
        messages: list[MessageParam] = [{"role": "user", "content": _task(question, plan)}]
        trace: list[ToolCallRecord] = []

        rounds = 0
        while True:
            tools_allowed = rounds < MAX_TOOL_ROUNDS
            reply = self._model.respond(
                system, messages, definitions, allow_tool_calls=tools_allowed
            )
            messages.append({"role": "assistant", "content": list(reply.content)})
            if reply.truncated and reply.tool_calls:
                # A tool call cut off by the output limit has incomplete arguments.
                raise ChatModelError("The model hit its output limit while calling a tool.")
            if not reply.tool_calls or not tools_allowed:
                return self._finish(
                    question, plan, trace, reply, registry, hit_limit=not tools_allowed
                )
            rounds += 1
            content: list[ToolResultBlockParam | TextBlockParam] = list(
                self._run_round(rounds, reply.tool_calls, registry, trace)
            )
            if rounds == MAX_TOOL_ROUNDS:
                logger.warning("Tool round limit (%d) reached; asking for an answer.", rounds)
                content.append({"type": "text", "text": load_prompt(ROUND_LIMIT_PROMPT).strip()})
            messages.append({"role": "user", "content": content})

    def _run_round(
        self,
        round_number: int,
        calls: Sequence[ToolUseBlock],
        registry: CitationRegistry,
        trace: list[ToolCallRecord],
    ) -> list[ToolResultBlockParam]:
        """Run `calls` concurrently; cite and record them in call order; return the results."""
        pool = ThreadPoolExecutor(max_workers=len(calls))
        try:
            outputs = list(pool.map(self._dispatch, calls))
        except BaseException:
            # Interrupted (Ctrl-C): return now rather than wait for calls still in flight.
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        pool.shutdown()

        results: list[ToolResultBlockParam] = []
        for call, output in zip(calls, outputs, strict=True):
            cited = self._citer.cite(output, registry)
            record = ToolCallRecord(
                round=round_number,
                name=call.name,
                args=dict(call.input) if isinstance(call.input, dict) else {},
                output=output.content,
                is_error=output.is_error,
                citation_ids=cited.citation_ids,
            )
            if output.is_error:
                logger.warning("Tool %s failed: %s", call.name, output.content)
            trace.append(record)
            self._observer.on_tool_call(record)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": cited.content,
                    "is_error": output.is_error,
                }
            )
        return results

    def _dispatch(self, call: ToolUseBlock) -> ToolOutput:
        """Run one call; an exception a tool should not raise becomes an error result."""
        args = call.input if isinstance(call.input, dict) else {}
        try:
            return self._tools.dispatch(call.name, args)
        except Exception as error:  # a tool bug must not end the run; the model is told
            logger.exception("Tool %s raised unexpectedly", call.name)
            return ToolOutput(
                content=f"Tool {call.name} failed unexpectedly ({type(error).__name__}).",
                is_error=True,
            )

    def _finish(
        self,
        question: str,
        plan: Plan,
        trace: list[ToolCallRecord],
        reply: ModelReply,
        registry: CitationRegistry,
        hit_limit: bool,
    ) -> AgentResult:
        if not reply.text:
            raise ChatModelError("The model ended its turn without an answer.")
        if reply.truncated:
            logger.warning("The final answer hit the output-token limit and is cut short.")
        return AgentResult(
            question=question,
            plan=plan,
            trace=tuple(trace),
            answer=self._resolver.resolve(reply.text, registry),
            hit_round_limit=hit_limit,
            answer_truncated=reply.truncated,
        )


def _task(question: str, plan: Plan) -> str:
    """The first user turn: the question, and the plan when there is one."""
    task = f"<question>\n{question}\n</question>"
    if plan.steps:
        task += f"\n\n<plan>\n{plan.numbered()}\n</plan>"
    return task
