"""Logging setup for fesmqa: the one place log level, format and output are chosen."""

import logging
import sys

LOGGER_NAME = "fesmqa"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(verbose: bool = False) -> None:
    """Send fesmqa's log messages to stderr, at DEBUG level if verbose, else INFO.

    Only the fesmqa logger is configured, so debug output from libraries is not shown.
    Safe to call more than once: the handler is added only the first time.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        logger.addHandler(handler)
