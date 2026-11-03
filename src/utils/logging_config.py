"""Process-wide logging setup (stdlib `logging`)."""

import logging
import sys
from functools import cache
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
SOURCE_ROOT = Path(__file__).resolve().parents[1]  # src/: the application's own modules


def configure_logging(level: str) -> None:
    """Log to stderr: this application's records at `level` (e.g. "INFO"), libraries quieter.

    Third-party libraries (the HTTP clients, Chroma, fastembed…) log every request
    or model load at INFO, so their records below WARNING are dropped unless
    `level` is DEBUG. Call once at startup, from the entry point. Replaces any
    handlers already installed so repeated calls do not duplicate output.
    """
    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)
    if logging.getLevelNamesMapping()[level] > logging.DEBUG:
        for handler in logging.getLogger().handlers:
            handler.addFilter(LibraryNoiseFilter(logging.WARNING))


class LibraryNoiseFilter(logging.Filter):
    """Passes every record from a module under `src/`, and others only from `min_level` up."""

    def __init__(self, min_level: int) -> None:
        super().__init__()
        self._min_level = min_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= self._min_level or _is_application_module(record.name)


@cache
def _is_application_module(logger_name: str) -> bool:
    """Whether `logger_name`'s top-level module (e.g. `utils` of `utils.config`) lives in src/."""
    module = sys.modules.get(logger_name.split(".", 1)[0])
    path = getattr(module, "__file__", None)
    return path is not None and Path(path).resolve().is_relative_to(SOURCE_ROOT)
