"""Process-wide logging setup (stdlib `logging`)."""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# The top-level loggers of this application's own modules (imports are rooted at src/).
APP_LOGGERS = ("agent", "agent_factory", "cli", "main", "tools", "utils")


def configure_logging(level: str) -> None:
    """Log to stderr: this application's modules at `level` (e.g. "INFO"), libraries quieter.

    Third-party libraries (the HTTP clients, Chroma, fastembed…) log every request
    or model load at INFO, so they are held at WARNING unless `level` is DEBUG.
    Call once at startup, from the entry point. Replaces any handlers already
    installed so repeated calls do not duplicate output.
    """
    app_level = logging.getLevelNamesMapping()[level]
    library_level = app_level if app_level <= logging.DEBUG else max(app_level, logging.WARNING)
    logging.basicConfig(level=library_level, format=LOG_FORMAT, force=True)
    for name in APP_LOGGERS:
        logging.getLogger(name).setLevel(app_level)
