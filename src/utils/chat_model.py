"""The chat-model port: what the agent needs from an LLM provider.

The agent depends on `ChatModel` only; the Anthropic implementation lives in its
own module and is injected where the agent is wired together. Content blocks and
messages use the Anthropic Messages API types, which are the agent's vocabulary
for a conversation with tools (the tool registry already speaks `ToolParam`).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from anthropic.types import ContentBlock, MessageParam, ToolParam, ToolUseBlock


class ChatModelError(Exception):
    """The model could not be called or gave no usable reply. The message is one key-free line."""


class ChatModelRefusalError(ChatModelError):
    """The model declined the request (`stop_reason: refusal`)."""


@dataclass(frozen=True)
class ModelReply:
    """One assistant turn.

    `content` must be appended to the conversation unchanged (it can hold thinking
    blocks the API validates on the next request). `truncated` is true when the
    reply hit the output-token limit.
    """

    content: tuple[ContentBlock, ...]
    truncated: bool = False

    @property
    def text(self) -> str:
        """The reply's text blocks, joined."""
        return "".join(block.text for block in self.content if block.type == "text").strip()

    @property
    def tool_calls(self) -> tuple[ToolUseBlock, ...]:
        """The tool calls the model asked for, in the order it wrote them."""
        return tuple(block for block in self.content if block.type == "tool_use")


class ChatModel(Protocol):
    """A chat model that can answer with structured JSON or converse using tools."""

    def generate_json(self, system: str, prompt: str, schema: Mapping[str, Any]) -> str:
        """Return the model's answer to `prompt` as JSON text conforming to `schema`.

        Raises `ChatModelRefusalError` if the model declines and `ChatModelError`
        when the call fails or the reply holds no JSON.
        """
        ...

    def respond(
        self,
        system: str,
        messages: Sequence[MessageParam],
        tools: Sequence[ToolParam],
        allow_tool_calls: bool = True,
    ) -> ModelReply:
        """Return the next assistant turn of `messages`.

        With `allow_tool_calls=False` the model sees `tools` (the conversation may
        already contain calls to them) but must answer in text.

        Raises `ChatModelRefusalError` if the model declines and `ChatModelError`
        when the call fails.
        """
        ...
