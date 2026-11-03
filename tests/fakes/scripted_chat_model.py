"""In-memory `ChatModel` fake: returns scripted replies and records what it was sent."""

import copy
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from anthropic.types import MessageParam, TextBlock, ToolParam, ToolUseBlock

from utils.chat_model import ChatModelError, ModelReply


def text_reply(text: str) -> ModelReply:
    """A final assistant turn: text only."""
    return ModelReply(content=(TextBlock(type="text", text=text),))


def tool_reply(*calls: tuple[str, Mapping[str, Any]]) -> ModelReply:
    """An assistant turn asking for `(tool name, input)` calls, with ids `call_1`, `call_2`…"""
    return ModelReply(
        content=tuple(
            ToolUseBlock(type="tool_use", id=f"call_{n}", name=name, input=dict(args))
            for n, (name, args) in enumerate(calls, 1)
        )
    )


@dataclass(frozen=True)
class RespondCall:
    """One `respond` request as the fake received it (messages deep-copied)."""

    system: str
    messages: list[MessageParam]
    tool_names: tuple[str, ...]
    allow_tool_calls: bool


type Outcome = ModelReply | ChatModelError


SUFFICIENT_REVIEW = '{"gaps": [], "sufficient": true}'

type JsonOutcome = str | ChatModelError


class ScriptedChatModel:
    """Scripted `ChatModel`: plans, evidence reviews and executor turns.

    `generate_json` answers a planner request (a schema with `steps`) with
    `plan_json`, and an evidence-check request with the next of `reviews`; when
    `reviews` is not given, every check finds the evidence sufficient. Each
    `respond` returns the next outcome. Running out of scripted replies or
    reviews is a test bug, so it raises `AssertionError`.
    """

    def __init__(
        self,
        replies: Iterable[Outcome],
        plan_json: JsonOutcome = '{"steps": []}',
        reviews: Iterable[JsonOutcome] | None = None,
    ) -> None:
        self._replies = list(replies)
        self._plan_json = plan_json
        self._reviews = None if reviews is None else list(reviews)
        self.json_requests: list[tuple[str, str, Mapping[str, Any]]] = []
        self.review_requests: list[tuple[str, str, Mapping[str, Any]]] = []
        self.respond_calls: list[RespondCall] = []

    def generate_json(self, system: str, prompt: str, schema: Mapping[str, Any]) -> str:
        if "steps" in schema.get("properties", {}):
            self.json_requests.append((system, prompt, schema))
            return _outcome(self._plan_json)
        self.review_requests.append((system, prompt, schema))
        if self._reviews is None:
            return SUFFICIENT_REVIEW
        if not self._reviews:
            raise AssertionError("Unexpected extra evidence check.")
        return _outcome(self._reviews.pop(0))

    def respond(
        self,
        system: str,
        messages: Sequence[MessageParam],
        tools: Sequence[ToolParam],
        allow_tool_calls: bool = True,
    ) -> ModelReply:
        self.respond_calls.append(
            RespondCall(
                system=system,
                messages=copy.deepcopy(list(messages)),
                tool_names=tuple(tool["name"] for tool in tools),
                allow_tool_calls=allow_tool_calls,
            )
        )
        if not self._replies:
            raise AssertionError("Unexpected extra respond call.")
        outcome = self._replies.pop(0)
        if isinstance(outcome, ChatModelError):
            raise outcome
        return outcome


def _outcome(outcome: JsonOutcome) -> str:
    if isinstance(outcome, ChatModelError):
        raise outcome
    return outcome
