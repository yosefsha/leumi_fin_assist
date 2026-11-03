"""The `RUN_LIVE_TESTS` switch (ADR-0004): off unless exactly `true`; missing keys are named."""

import pytest

from live_switch import live_tests_enabled, missing_keys_message, missing_live_keys

_KEYS = {"ANTHROPIC_API_KEY": "sk-ant-x", "TAVILY_API_KEY": "tvly-x"}


@pytest.mark.parametrize("value", ["true", "TRUE", " True "])
def test_true_enables_live_tests(value: str) -> None:
    assert live_tests_enabled({"RUN_LIVE_TESTS": value})


@pytest.mark.parametrize("value", ["", "false", "1", "yes", "on"])
def test_anything_else_keeps_live_tests_off(value: str) -> None:
    assert not live_tests_enabled({"RUN_LIVE_TESTS": value})


def test_unset_keeps_live_tests_off() -> None:
    assert not live_tests_enabled({})


def test_both_keys_present_means_nothing_missing() -> None:
    assert missing_live_keys(_KEYS) == ()


def test_missing_and_blank_keys_are_named() -> None:
    missing = missing_live_keys({"TAVILY_API_KEY": "  "})
    assert missing == ("ANTHROPIC_API_KEY", "TAVILY_API_KEY")
    message = missing_keys_message(missing)
    assert "ANTHROPIC_API_KEY, TAVILY_API_KEY are not set" in message


def test_one_missing_key_is_named() -> None:
    message = missing_keys_message(missing_live_keys({"TAVILY_API_KEY": "tvly-x"}))
    assert message.startswith("RUN_LIVE_TESTS=true but ANTHROPIC_API_KEY is not set.")
