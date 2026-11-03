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


class ScriptedChatModel:
    """Answers `generate_json` with `plan_json` and each `respond` with the next outcome.

    Running out of scripted replies is a test bug, so it raises `AssertionError`.
    """

    def __init__(
        self, replies: Iterable[Outcome], plan_json: str | ChatModelError = '{"steps": []}'
    ) -> None:
        self._replies = list(replies)
        self._plan_json = plan_json
        self.json_requests: list[tuple[str, str, Mapping[str, Any]]] = []
        self.respond_calls: list[RespondCall] = []

    def generate_json(self, system: str, prompt: str, schema: Mapping[str, Any]) -> str:
        self.json_requests.append((system, prompt, schema))
        if isinstance(self._plan_json, ChatModelError):
            raise self._plan_json
        return self._plan_json

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
