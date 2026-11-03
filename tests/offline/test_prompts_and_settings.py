"""Prompt templating and the `FILING_FISCAL_YEAR` setting (issue #9)."""

from pathlib import Path

import pytest

from utils.config import ConfigError, Settings
from utils.prompts import PromptPlaceholderError, render_prompt

_KEYS = {"ANTHROPIC_API_KEY": "a", "TAVILY_API_KEY": "t"}


def test_placeholders_are_filled(tmp_path: Path) -> None:
    (tmp_path / "greeting.txt").write_text("FY{{ year }} costs $34,550M {{year}}")
    assert render_prompt("greeting", {"year": "2025"}, tmp_path) == "FY2025 costs $34,550M 2025"


@pytest.mark.parametrize(
    ("values", "problem"),
    [({}, "no value for ['year']"), ({"year": "2025", "extra": "x"}, "unused values ['extra']")],
    ids=["missing", "unused"],
)
def test_mismatched_placeholders_fail_loudly(
    tmp_path: Path, values: dict[str, str], problem: str
) -> None:
    (tmp_path / "greeting.txt").write_text("FY{{year}}")
    with pytest.raises(PromptPlaceholderError, match=problem.replace("[", r"\[")):
        render_prompt("greeting", values, tmp_path)


def test_fiscal_year_defaults_to_the_shipped_filing() -> None:
    assert Settings.from_mapping(_KEYS).filing_fiscal_year == 2025


def test_fiscal_year_is_read_from_the_environment() -> None:
    assert Settings.from_mapping({**_KEYS, "FILING_FISCAL_YEAR": "2024"}).filing_fiscal_year == 2024


@pytest.mark.parametrize("raw", ["25", "FY2025", "02025", "2025.0", "-2025"])
def test_an_invalid_fiscal_year_is_rejected(raw: str) -> None:
    with pytest.raises(ConfigError, match="FILING_FISCAL_YEAR"):
        Settings.from_mapping({**_KEYS, "FILING_FISCAL_YEAR": raw})
