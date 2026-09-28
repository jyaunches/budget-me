"""Structured JSON logging setup compatible with Loki."""

import json
import sys
from datetime import UTC, datetime
from typing import Any

from loguru import logger


def json_sink(message):
    """Sink that formats log messages as JSON for Loki compatibility.

    This is used as a sink (not a format) to have full control over output.
    """
    record = message.record

    # Base log entry
    log_entry: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "logger": record["name"],
    }

    # Add location info for debugging
    if record.get("file"):
        log_entry["file"] = record["file"].name
        log_entry["line"] = record["line"]
        log_entry["function"] = record["function"]

    # Add any extra context fields bound to the logger
    extra = record.get("extra", {})
    for key, value in extra.items():
        if key not in log_entry:
            log_entry[key] = value

    # Add exception info if present
    if record.get("exception"):
        exc = record["exception"]
        if exc.type is not None:
            log_entry["exception"] = {
                "type": exc.type.__name__,
                "value": str(exc.value),
            }

    print(json.dumps(log_entry), file=sys.stdout, flush=True)


def setup_logging(log_level: str = "INFO", json_output: bool = True) -> None:
    """Configure logging with JSON output for Loki compatibility.

    Args:
        log_level: The minimum log level to output (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, output JSON format; if False, use standard format
    """
    # Remove default handler
    logger.remove()

    if json_output:
        # Add JSON sink for production/Loki
        logger.add(
            json_sink,
            level=log_level,
            format="{message}",  # Required but unused since we handle output in sink
        )
    else:
        # Standard format for local development
        logger.add(
            sys.stdout,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            level=log_level,
            colorize=True,
        )


def get_logger(name: str) -> "logger":
    """Get a logger instance with the given name.

    Args:
        name: Logger name (typically module __name__)

    Returns:
        A loguru logger instance bound with the given name
    """
    return logger.bind(logger=name)
