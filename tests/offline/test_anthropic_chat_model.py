"""The Anthropic `ChatModel` adapter's boundary: requests it builds and errors it translates.

The SDK's `messages.create` is replaced in-process, so no request leaves the machine.
"""

from typing import Any

import anthropic
import httpx2
import pytest
from anthropic.types import Message, TextBlock, Usage

from utils.anthropic_chat_model import AnthropicChatModel
from utils.chat_model import ChatModelError, ChatModelRefusalError, IncompleteReplyError

_FAKE_KEY = "sk-ant-offline-test-key-0123456789"
_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _message(text: str, stop_reason: str = "end_turn") -> Message:
    return Message.model_construct(
        id="msg_1",
        type="message",
        role="assistant",
        model="claude-sonnet-5-5",
        content=[TextBlock(type="text", text=text)],
        stop_reason=stop_reason,
        stop_details=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


def _patched(
    monkeypatch: pytest.MonkeyPatch, outcome: Message | Exception
) -> tuple[AnthropicChatModel, list[dict[str, Any]]]:
    """A new adapter whose SDK call returns (or raises) `outcome`, and its recorded requests."""
    model = AnthropicChatModel(_FAKE_KEY, "claude-sonnet-5-5")
    requests: list[dict[str, Any]] = []

    def create(**params: Any) -> Message:
        requests.append(params)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(model._client.messages, "create", create)
    return model, requests


def test_generate_json_requests_structured_output(monkeypatch: pytest.MonkeyPatch) -> None:
    model, requests = _patched(monkeypatch, _message('{"steps": []}'))
    schema = {"type": "object"}
    assert model.generate_json("sys", "q", schema) == '{"steps": []}'
    assert requests[0]["output_config"] == {"format": {"type": "json_schema", "schema": schema}}
    assert requests[0]["model"] == "claude-sonnet-5-5"


def test_respond_without_tools_sets_tool_choice_none(monkeypatch: pytest.MonkeyPatch) -> None:
    model, requests = _patched(monkeypatch, _message("answer"))
    reply = model.respond("sys", [], [], allow_tool_calls=False)
    assert reply.text == "answer"
    assert requests[0]["tool_choice"] == {"type": "none"}


def test_a_truncated_reply_is_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    model, _ = _patched(monkeypatch, _message("partial", stop_reason="max_tokens"))
    assert model.respond("sys", [], []).truncated


def test_a_refusal_is_a_refusal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    model, _ = _patched(monkeypatch, _message("", stop_reason="refusal"))
    with pytest.raises(ChatModelRefusalError, match="declined"):
        model.respond("sys", [], [])


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (
            anthropic.AuthenticationError(
                f"invalid x-api-key {_FAKE_KEY}",
                response=httpx2.Response(401, request=_REQUEST),
                body=None,
            ),
            "HTTP 401 (AuthenticationError)",
        ),
        (anthropic.APITimeoutError(request=_REQUEST), "timed out"),
        (anthropic.APIConnectionError(request=_REQUEST), "Could not connect"),
        (
            anthropic.APIResponseValidationError(
                response=httpx2.Response(200, request=_REQUEST), body=None
            ),
            "APIResponseValidationError",
        ),
    ],
    ids=["401", "timeout", "connection", "malformed-response"],
)
def test_sdk_errors_become_key_free_chat_model_errors(
    monkeypatch: pytest.MonkeyPatch, error: Exception, reason: str
) -> None:
    model, _ = _patched(monkeypatch, error)
    with pytest.raises(ChatModelError) as raised:
        model.respond("sys", [], [])
    assert reason in str(raised.value)
    assert _FAKE_KEY not in str(raised.value)


def test_a_json_reply_without_text_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    model, _ = _patched(monkeypatch, _message("", stop_reason="max_tokens"))
    with pytest.raises(IncompleteReplyError, match="no complete JSON"):
        model.generate_json("sys", "q", {})
