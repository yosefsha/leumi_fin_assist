"""`ChatModel` implementation backed by the Anthropic Messages API."""

import logging
from collections.abc import Mapping, Sequence
from typing import Any

import anthropic
from anthropic.types import Message, MessageParam, ToolParam

from utils.chat_model import (
    ChatModelError,
    ChatModelRefusalError,
    IncompleteReplyError,
    ModelReply,
)

logger = logging.getLogger(__name__)

# Retries for connection errors, 408, 409, 429 and 5xx, with the SDK's backoff (issue #9).
MAX_RETRIES = 3
# Non-streaming requests: large enough for a full cited answer, small enough to
# stay under the SDK's request timeout.
MAX_OUTPUT_TOKENS = 16_000


class AnthropicChatModel:
    """Calls one Claude model through the Anthropic SDK.

    Every SDK error becomes a `ChatModelError` whose message names the failure
    (status code, connection problem) and never contains the API key.
    """

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key.strip():
            raise ValueError("An Anthropic API key is required.")
        if not model.strip():
            raise ValueError("A model name is required.")
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=MAX_RETRIES)
        self._model = model

    def generate_json(self, system: str, prompt: str, schema: Mapping[str, Any]) -> str:
        """Ask for JSON constrained by `schema` (structured outputs); see `ChatModel`."""
        message = self._create(
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": dict(schema)}},
        )
        reply = _reply(message)
        if reply.truncated or not reply.text:
            raise IncompleteReplyError(
                f"{self._model} returned no complete JSON (stop reason {message.stop_reason})."
            )
        return reply.text

    def respond(
        self,
        system: str,
        messages: Sequence[MessageParam],
        tools: Sequence[ToolParam],
        allow_tool_calls: bool = True,
    ) -> ModelReply:
        """Return the next assistant turn; see `ChatModel`."""
        message = self._create(
            system=system,
            messages=list(messages),
            tools=list(tools),
            tool_choice={"type": "auto" if allow_tool_calls else "none"},
        )
        return _reply(message)

    def _create(self, **params: Any) -> Message:
        try:
            message = self._client.messages.create(
                model=self._model, max_tokens=MAX_OUTPUT_TOKENS, **params
            )
        except anthropic.APIStatusError as error:
            raise ChatModelError(
                f"Anthropic API returned HTTP {error.status_code} ({type(error).__name__})"
                f" for model {self._model}."
            ) from error
        except anthropic.APITimeoutError as error:
            raise ChatModelError("Anthropic API timed out after retries.") from error
        except anthropic.APIConnectionError as error:
            raise ChatModelError("Could not connect to the Anthropic API.") from error
        except anthropic.APIError as error:
            raise ChatModelError(
                f"Anthropic API call failed ({type(error).__name__}) for model {self._model}."
            ) from error
        logger.debug(
            "%s: stop=%s input_tokens=%s output_tokens=%s",
            self._model,
            message.stop_reason,
            message.usage.input_tokens,
            message.usage.output_tokens,
        )
        if message.stop_reason == "refusal":
            category = getattr(message.stop_details, "category", None) or "unspecified"
            raise ChatModelRefusalError(f"{self._model} declined the request ({category}).")
        return message


def _reply(message: Message) -> ModelReply:
    return ModelReply(content=tuple(message.content), truncated=message.stop_reason == "max_tokens")
