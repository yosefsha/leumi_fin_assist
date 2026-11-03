"""Process-wide logging setup (stdlib `logging`)."""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Third-party loggers that report every request or model load at INFO. They are
# held at WARNING unless LOG_LEVEL is DEBUG, so the REPL's stderr stays readable.
CHATTY_LIBRARIES = (
    "anthropic",
    "chromadb",
    "fastembed",
    "httpcore",
    "httpx",
    "huggingface_hub",
    "urllib3",
)


def configure_logging(level: str) -> None:
    """Configure the root logger to write to stderr at `level` (e.g. "INFO").

    Call once at startup, from the entry point. Replaces any handlers already
    installed so repeated calls do not duplicate output.
    """
    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)
    library_level = (
        logging.DEBUG
        if level == "DEBUG"
        else max(logging.WARNING, logging.getLevelNamesMapping()[level])
    )
    for name in CHATTY_LIBRARIES:
        logging.getLogger(name).setLevel(library_level)
