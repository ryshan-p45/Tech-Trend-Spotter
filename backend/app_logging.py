import json
import logging
import sys
from datetime import datetime, timezone

"""
Structured (JSON) logging shared by the whole backend.

Every log line contains: UTC timestamp, severity, service name, message,
and a correlation ID (when one is passed) so a single request or collection
run can be traced across components.

Usage:
    logger = get_logger("data_collection")
    logger.info("Fetched feed", extra={"correlation_id": cid, "context": {...}})

Never pass secrets, tokens or personal data in `extra` - they will be logged.
"""


# Fields we pull out of `extra` and promote to top-level JSON keys
_PROMOTED_FIELDS = ("correlation_id", "context")


class JsonFormatter(logging.Formatter):
    """Turns a LogRecord into a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": record.name,
            "message": record.getMessage(),
        }

        # Copy optional tracing/context fields if the caller provided them
        for field in _PROMOTED_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value

        # Include the stack trace for logger.exception(...) calls
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)


def get_logger(service_name: str) -> logging.Logger:
    """Return a logger that writes JSON lines to stdout. Safe to call repeatedly."""
    logger = logging.getLogger(service_name)

    # Only attach a handler once, otherwise each call would duplicate log lines
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

    return logger
