"""
BCOS Logging

Nothing in BCOS wrote a log. `agent/logs/agent.log` existed as a
0-byte file created by the scaffold, `LOGS_DIR` had no importers,
and `Agent.trace()` is stdout-only and is wiped at the top of
every `ask()`.

That is why a TypeError which made every question fail could only
be reported as "Qwen cannot search": the REPL printed `str(exc)`
with no traceback, and nothing survived on disk to post-mortem.

Everything here is best-effort. A read-only or missing logs
directory must never stop the agent from answering, so setup
failures fall back to stderr.
"""

import logging
import sys

from paths import LOGS_DIR


LOG_FILE = LOGS_DIR / "agent.log"

ROOT_NAME = "bcos"

_configured = False


def setup(level=logging.INFO):
    """
    Attach a file handler to the 'bcos' logger tree, once.
    """

    global _configured

    if _configured:
        return logging.getLogger(
            ROOT_NAME
        )

    logger = logging.getLogger(
        ROOT_NAME
    )

    logger.setLevel(
        level
    )

    # Don't let records reach the root logger, which would print
    # them to the console and mix into the agent's own output.
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s "
        "%(name)s %(message)s"
    )

    try:

        LOGS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        handler = logging.FileHandler(
            LOG_FILE,
            encoding="utf-8",
        )

    except OSError as exc:

        handler = logging.StreamHandler(
            sys.stderr
        )

        handler.setFormatter(
            formatter
        )

        logger.addHandler(
            handler
        )

        _configured = True

        logger.warning(
            "could not open %s (%s); "
            "logging to stderr",
            LOG_FILE,
            exc,
        )

        return logger

    handler.setFormatter(
        formatter
    )

    logger.addHandler(
        handler
    )

    _configured = True

    return logger


def get(name):
    """
    Logger for a BCOS module: get("planner") -> "bcos.planner".
    """

    setup()

    return logging.getLogger(
        f"{ROOT_NAME}.{name}"
    )
