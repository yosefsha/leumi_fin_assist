"""The `web_search` tool (issue #6, PR #19): retry once on timeout, every failure an error result.

Tool behaviour runs against the in-memory `WebSearchClient` fake. The key-leak
check drives the real `TavilyWebSearchClient` with the HTTP session stubbed, so
no request leaves the process.
"""

import json
import logging
from typing import Any

import pytest
import requests

from fakes.scripted_web_search_client import ScriptedWebSearchClient
from tools.tavily_search import WebSearchTool
from utils.tavily_web_search_client import TavilyWebSearchClient
from utils.web_result import WebResult
from utils.web_search import WebSearchError, WebSearchTimeoutError

_RESULT = WebResult(
    url="https://www.microsoft.com/investor",
    title="Microsoft FY26 Q1 earnings",
    content="Gross margin was 69%.",
    published_date="2025-10-29",
)
_QUERY = {"query": "Microsoft gross margin latest quarter"}
_FAKE_KEY = "tvly-offline-test-key-0123456789"


def test_results_are_returned_as_sources() -> None:
    client = ScriptedWebSearchClient([[_RESULT]])
    output = WebSearchTool(client).run(_QUERY)
    assert not output.is_error
    assert json.loads(output.content) == {"query": _QUERY["query"], "results_found": 1}
    assert output.sources == (_RESULT,)


def test_a_timeout_is_retried_exactly_once() -> None:
    client = ScriptedWebSearchClient([WebSearchTimeoutError("slow"), [_RESULT]])
    output = WebSearchTool(client).run(_QUERY)
    assert not output.is_error
    assert client.queries == [_QUERY["query"]] * 2


def test_a_second_timeout_is_an_error_result() -> None:
    client = ScriptedWebSearchClient([WebSearchTimeoutError("slow"), WebSearchTimeoutError("slow")])
    output = WebSearchTool(client).run(_QUERY)
    assert output.is_error
    assert output.content == "Web search failed: slow"
    assert len(client.queries) == 2


def test_a_provider_error_is_not_retried() -> None:
    client = ScriptedWebSearchClient([WebSearchError("Tavily returned HTTP 500.")])
    output = WebSearchTool(client).run(_QUERY)
    assert output.is_error
    assert "HTTP 500" in output.content
    assert len(client.queries) == 1


def test_no_results_is_an_error_result() -> None:
    output = WebSearchTool(ScriptedWebSearchClient([[]])).run(_QUERY)
    assert output.is_error
    assert output.content.startswith("No web results found")


@pytest.mark.parametrize(
    "args",
    [{}, {"query": ""}, {"query": "   "}, {"query": "x" * 401}, {"query": 42}, {**_QUERY, "n": 3}],
    ids=["missing", "empty", "blank", "too-long", "not-a-string", "extra-key"],
)
def test_invalid_arguments_are_an_error_result_without_a_search(args: dict[str, Any]) -> None:
    client = ScriptedWebSearchClient([])
    output = WebSearchTool(client).run(args)
    assert output.is_error
    assert output.content.startswith("Invalid web_search arguments:")
    assert client.queries == []


def _respond(status: int) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps({"detail": {"error": "rejected"}}).encode()
    return response


@pytest.mark.parametrize(
    ("post_outcome", "reason"),
    [
        (_respond(401), "rejected the API key"),
        (_respond(429), "rate limit"),
        (_respond(500), "HTTP 500"),
        (requests.ConnectionError(f"refused; Authorization: Bearer {_FAKE_KEY}"), "Network error"),
        (requests.Timeout(f"timed out for key {_FAKE_KEY}"), "did not respond"),
    ],
    ids=["401", "429", "500", "network", "timeout"],
)
def test_the_api_key_never_reaches_logs_or_results(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    post_outcome: requests.Response | requests.RequestException,
    reason: str,
) -> None:
    def post(*_args: object, **_kwargs: object) -> requests.Response:
        if isinstance(post_outcome, Exception):
            raise post_outcome
        return post_outcome

    monkeypatch.setattr(requests.Session, "post", post)
    tool = WebSearchTool(TavilyWebSearchClient(_FAKE_KEY))

    with caplog.at_level(logging.DEBUG):
        output = tool.run(_QUERY)

    assert output.is_error
    assert reason in output.content
    assert caplog.records, "the failure should have been logged"
    assert _FAKE_KEY not in caplog.text
    assert _FAKE_KEY not in output.content
