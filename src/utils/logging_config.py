"""Process-wide logging setup (stdlib `logging`)."""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str) -> None:
    """Configure the root logger to write to stderr at `level` (e.g. "INFO").

    Call once at startup, from the entry point. Replaces any handlers already
    installed so repeated calls do not duplicate output.
    """
    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)
