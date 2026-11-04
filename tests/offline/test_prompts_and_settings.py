"""Prompt templating and the Filing settings: `FILING_FISCAL_YEAR` (issue #9) and
`FILING_COMPANY`, `SUGGESTED_QUESTIONS_PATH` (issue #35)."""

from pathlib import Path

import pytest

from utils.config import (
    DEFAULT_FILING_PATH,
    PROJECT_ROOT,
    ConfigError,
    MissingSettingError,
    Settings,
)
from utils.prompts import (
    PROMPTS_DIR,
    PromptPlaceholderError,
    load_tool_description,
    render_prompt,
)

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
    assert Settings.from_mapping(_KEYS).filing.fiscal_year == 2025


def test_fiscal_year_is_read_from_the_environment() -> None:
    assert Settings.from_mapping({**_KEYS, "FILING_FISCAL_YEAR": "2024"}).filing.fiscal_year == 2024


@pytest.mark.parametrize("raw", ["25", "FY2025", "02025", "2025.0", "-2025"])
def test_an_invalid_fiscal_year_is_rejected(raw: str) -> None:
    with pytest.raises(ConfigError, match="FILING_FISCAL_YEAR"):
        Settings.from_mapping({**_KEYS, "FILING_FISCAL_YEAR": raw})


_OTHER_FILING = {
    "FILING_PATH": "data/contoso_10k_2026.htm",
    "FILING_COMPANY": "Contoso Ltd.",
    "FILING_FISCAL_YEAR": "2026",
}


def test_the_default_filing_is_apples_fy2025_10k_with_its_own_questions() -> None:
    filing = Settings.from_mapping(_KEYS).filing
    assert filing.path == PROJECT_ROOT / DEFAULT_FILING_PATH
    assert (filing.company, filing.fiscal_year) == ("Apple Inc.", 2025)
    assert filing.suggested_questions_path is None


def test_another_filing_is_configured_by_settings_alone() -> None:
    questions = "prompts/contoso_questions.txt"
    filing = Settings.from_mapping(
        {**_KEYS, **_OTHER_FILING, "SUGGESTED_QUESTIONS_PATH": questions}
    ).filing
    assert filing.path == PROJECT_ROOT / "data/contoso_10k_2026.htm"
    assert (filing.company, filing.fiscal_year) == ("Contoso Ltd.", 2026)
    assert filing.suggested_questions_path == PROJECT_ROOT / questions


@pytest.mark.parametrize("name", ["FILING_COMPANY", "FILING_FISCAL_YEAR"])
@pytest.mark.parametrize("value", [None, "", "   "], ids=["missing", "empty", "blank"])
def test_another_filing_without_its_company_or_year_fails_at_the_boundary(
    name: str, value: str | None
) -> None:
    values = {**_KEYS, **_OTHER_FILING}
    if value is None:
        del values[name]
    else:
        values[name] = value
    with pytest.raises(MissingSettingError, match=f"Required setting {name} is not set") as error:
        Settings.from_mapping(values)
    assert "FILING_PATH names a Filing other than the shipped one" in str(error.value)


@pytest.mark.parametrize("raw", ["Contoso\nLtd.", "C" * 101], ids=["two-lines", "too-long"])
def test_an_invalid_company_is_rejected(raw: str) -> None:
    with pytest.raises(ConfigError, match="FILING_COMPANY"):
        Settings.from_mapping({**_KEYS, **_OTHER_FILING, "FILING_COMPANY": raw})


_PROMPT_VALUES = {"fiscal_year": "2026", "today": "2026-11-04", "company": "Contoso Ltd."}


@pytest.mark.parametrize(
    ("name", "values"),
    [
        ("system_prompt", _PROMPT_VALUES),
        ("planner_prompt", {**_PROMPT_VALUES, "tools": "search_filing"}),
        ("evidence_check_prompt", {**_PROMPT_VALUES, "tools": "search_filing"}),
    ],
)
def test_each_prompt_names_the_configured_company(name: str, values: dict[str, str]) -> None:
    rendered = render_prompt(name, values)
    assert "Contoso Ltd." in rendered
    assert "Apple" not in rendered
    assert "{{" not in rendered
    with pytest.raises(PromptPlaceholderError, match=r"no value for \['company'\]"):
        render_prompt(name, {key: value for key, value in values.items() if key != "company"})


@pytest.mark.parametrize("tool", ["search_filing", "web_search"])
def test_filing_tool_descriptions_name_the_configured_company(tool: str) -> None:
    description = load_tool_description(tool, {"company": "Contoso Ltd."})
    assert "Contoso Ltd.'s 10-K Filing" in description
    assert "Apple" not in description
    with pytest.raises(PromptPlaceholderError, match=r"no value for \['company'\]"):
        load_tool_description(tool)


@pytest.mark.parametrize("tool", ["calculate", "get_passage"])
def test_a_company_for_a_description_without_one_fails_loudly(tool: str) -> None:
    assert "{{" not in load_tool_description(tool)
    with pytest.raises(PromptPlaceholderError, match=r"unused values \['company'\]"):
        load_tool_description(tool, {"company": "Contoso Ltd."})


def test_no_company_is_hard_coded_in_the_prompts() -> None:
    """Only the shipped Filing's own suggested questions may name Apple."""
    for path in PROMPTS_DIR.glob("*.txt"):
        if path.name != "suggested_questions.txt":
            assert "Apple" not in path.read_text(encoding="utf-8"), path.name
