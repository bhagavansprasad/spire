"""Agent run tracing.

Each call to run_agent gets a unique run_id and writes a JSON-lines
file to traces/{run_id}.jsonl. One line per logged event.

Inspect a trace:
    cat traces/2026-05-15T14-30-00.jsonl | jq .
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import structlog


TRACES_DIR = Path(__file__).resolve().parents[3] / "traces"


def make_trace_logger() -> tuple[structlog.BoundLogger, Path]:
    """Configure structlog to write JSON lines to a per-run trace file.

    Returns the configured logger and the trace file path.
    """
    TRACES_DIR.mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")
    trace_path = TRACES_DIR / f"{run_id}.jsonl"

    handler = logging.FileHandler(trace_path)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger(f"spire.agent.{run_id}")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    logger = structlog.get_logger(f"spire.agent.{run_id}").bind(run_id=run_id)
    return logger, trace_path


def truncate_tool_result(items: list[dict], keep: int = 2) -> dict:
    """Compress a tool result for tracing — keep first N items + count."""
    return {
        "total_items": len(items),
        "preview": items[:keep],
        "truncated": len(items) > keep,
    }
