"""Logging configuration.

We don't go full structured-JSON-logger here. The prsage logs are read by
humans (Railway log stream, local terminal) so plain text with consistent
fields is more useful than JSON.

Format:

    2026-04-25T18:42:11Z INFO prsage.runner posted review pr=amin/test#5 tokens=900

Set ``LOG_LEVEL`` in the env to override the default ``INFO``.
"""

from __future__ import annotations

import logging
import sys
from logging import Formatter, StreamHandler


class UTCFormatter(Formatter):
    """ISO-8601 UTC timestamps with a trailing Z."""

    def formatTime(self, record, datefmt=None):  # noqa: N802 (overrides logging API)
        from datetime import datetime, timezone

        return (
            datetime.fromtimestamp(record.created, tz=timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )


def configure_logging(level: str = "info") -> None:
    """Install a single stdout handler with a consistent prsage format.

    Idempotent: running twice (e.g. on test reload) doesn't double-handle.
    """
    root = logging.getLogger()
    if any(getattr(h, "_prsage_handler", False) for h in root.handlers):
        return

    handler = StreamHandler(sys.stdout)
    handler.setFormatter(
        UTCFormatter(fmt="%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler._prsage_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Quiet down a couple of noisy third-party loggers.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
