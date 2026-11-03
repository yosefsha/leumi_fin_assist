"""The `RUN_LIVE_TESTS` switch: whether `live` tests may call the paid APIs (ADR-0004)."""

from collections.abc import Mapping

SWITCH = "RUN_LIVE_TESTS"
SKIP_REASON = f"set {SWITCH}=true to run"
LIVE_API_KEYS = ("ANTHROPIC_API_KEY", "TAVILY_API_KEY")


def live_tests_enabled(values: Mapping[str, str]) -> bool:
    """Whether `values` sets `RUN_LIVE_TESTS` to `true` (case-insensitive). Off by default."""
    return values.get(SWITCH, "").strip().lower() == "true"


def missing_live_keys(values: Mapping[str, str]) -> tuple[str, ...]:
    """The API keys a live test needs that `values` leaves absent or blank, in a fixed order."""
    return tuple(name for name in LIVE_API_KEYS if not values.get(name, "").strip())


def missing_keys_message(missing: tuple[str, ...]) -> str:
    """Why a live test failed when the switch is on but keys are missing."""
    return (
        f"{SWITCH}=true but {', '.join(missing)} "
        f"{'is' if len(missing) == 1 else 'are'} not set. Set "
        f"{'it' if len(missing) == 1 else 'them'} in the environment or in .env, "
        f"or unset {SWITCH} to skip the live tests."
    )
