"""Inspect an agent trace and produce a readable summary.

Usage:
    python scripts/inspect_trace.py                  # most recent in traces/
    python scripts/inspect_trace.py PATH             # specific file
    python scripts/inspect_trace.py PATH --full      # don't truncate the final answer
    python scripts/inspect_trace.py PATH --json      # emit structured JSON

The summary is designed for two consumers:
- a human eyeballing an individual run (default text format)
- phase 08 rubric scoring scripts that want structured data (--json)

Heuristics:
- "premature termination" = the agent finished with an empty answer AND
  made at most one tool call. Matches Track A baseline failure mode 1.
- "crashed mid-run" = there is no agent_finished event in the trace.

Note on content normalization:
Some traces (those produced before runner.py's content normalizer landed,
or with models that return structured content like gemini-2.5-pro) recorded
answer_preview as a list-of-dicts instead of a string. The parser coerces
to plain text defensively so old traces remain readable.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


TRACES_DIR = Path(__file__).resolve().parent.parent / "traces"


@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class TraceSummary:
    run_id: str
    trace_file: str
    prompt: str | None = None
    model: str | None = None
    kg_enabled: bool | None = None
    kg_chars: int | None = None
    system_prompt_chars: int | None = None
    tools_available: list[str] = field(default_factory=list)
    turns: list[list[ToolCall]] = field(default_factory=list)
    final_answer: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    completed_normally: bool = False
    termination_note: str = ""

    @property
    def total_tool_calls(self) -> int:
        return sum(len(turn) for turn in self.turns)

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


def _parse_event(line: str) -> dict | None:
    """Parse one JSONL line. Returns None for blank or unparseable lines."""
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _parse_ts(ts: str | None) -> datetime | None:
    """Parse the ISO timestamps that structlog produces."""
    if not ts:
        return None
    # Replace trailing Z with +00:00 for fromisoformat compatibility.
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _normalize_content(raw) -> str:
    """Coerce content from a trace event to a plain string.

    Newer traces have plain-string answer_preview. Older traces (or those
    produced by models like gemini-2.5-pro before the runner normalizer
    landed) recorded answer_preview as a list of {"type": "text",
    "text": "..."} dicts. This helper handles both.
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(raw)


def parse_trace(path: Path) -> TraceSummary:
    """Read a trace file and produce a TraceSummary."""
    summary = TraceSummary(run_id=path.stem, trace_file=str(path))

    with path.open() as f:
        events = [e for e in (_parse_event(line) for line in f) if e is not None]

    for ev in events:
        event_name = ev.get("event")

        if event_name == "agent_started":
            summary.prompt = ev.get("prompt")
            summary.model = ev.get("model")
            summary.kg_enabled = ev.get("kg_enabled")
            summary.started_at = _parse_ts(ev.get("timestamp"))

        elif event_name == "kg_context_loaded":
            summary.kg_chars = ev.get("chars")

        elif event_name == "system_prompt_built":
            summary.system_prompt_chars = ev.get("chars")

        elif event_name == "tools_loaded":
            tools = ev.get("tools")
            if isinstance(tools, list):
                summary.tools_available = tools

        elif event_name == "message":
            tool_calls = ev.get("tool_calls")
            if tool_calls:
                turn = [ToolCall(name=tc.get("name", ""), args=tc.get("args", {}))
                        for tc in tool_calls]
                summary.turns.append(turn)

        elif event_name == "agent_finished":
            summary.finished_at = _parse_ts(ev.get("timestamp"))
            summary.final_answer = _normalize_content(ev.get("answer_preview", ""))
            summary.completed_normally = True

    # Termination heuristics.
    if not summary.completed_normally:
        summary.termination_note = "crashed mid-run (no agent_finished event)"
    elif summary.total_tool_calls <= 1 and summary.final_answer.strip() == "":
        summary.termination_note = "premature termination (one or zero tool calls, empty answer)"
    elif summary.final_answer.strip() == "":
        summary.termination_note = "completed but produced no answer"
    else:
        summary.termination_note = "completed normally"

    return summary


def format_text(summary: TraceSummary, full_answer: bool) -> str:
    """Format a TraceSummary as a human-readable text block."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"Trace: {summary.run_id}")
    lines.append("=" * 80)
    lines.append(f"Prompt:       {summary.prompt or '<missing>'}")
    lines.append(f"KG enabled:   {summary.kg_enabled}")
    lines.append(f"Model:        {summary.model or '<missing>'}")
    duration = summary.duration_seconds
    duration_str = f"{duration:.1f} seconds" if duration is not None else "<unknown>"
    lines.append(f"Duration:     {duration_str}")
    lines.append(f"Tool count:   {summary.total_tool_calls} calls across {len(summary.turns)} LLM turns")
    lines.append("")
    if summary.system_prompt_chars is not None:
        kg_note = (f" (KG context: {summary.kg_chars} chars)"
                   if summary.kg_chars is not None else "")
        lines.append(f"System prompt: {summary.system_prompt_chars} chars{kg_note}")
    if summary.tools_available:
        lines.append(f"Tools available: {', '.join(summary.tools_available)}")
    lines.append("")

    if summary.turns:
        lines.append("--- Tool call sequence ---")
        lines.append("")
        for i, turn in enumerate(summary.turns, start=1):
            if len(turn) == 1:
                tc = turn[0]
                lines.append(f"Turn {i}:")
                lines.append(f"  {tc.name}({_format_args(tc.args)})")
            else:
                lines.append(f"Turn {i}: ({len(turn)} parallel calls)")
                for tc in turn:
                    lines.append(f"  {tc.name}({_format_args(tc.args)})")
            lines.append("")
    else:
        lines.append("--- Tool call sequence ---")
        lines.append("(no tool calls)")
        lines.append("")

    lines.append("--- Final answer ---")
    answer = summary.final_answer
    if not answer.strip():
        lines.append("(empty)")
    elif full_answer or len(answer) <= 500:
        lines.append(answer)
    else:
        lines.append(answer[:500] + "\n[...truncated; use --full to see all...]")
    lines.append("")

    lines.append("--- Termination ---")
    lines.append(f"Status: {summary.termination_note}")
    lines.append("")
    return "\n".join(lines)


def _format_args(args: dict) -> str:
    """Format tool-call args as kw=val, kw=val. Keeps key order stable
    by sorting, so identical calls render identically across runs."""
    if not args:
        return ""
    parts = []
    for k in sorted(args.keys()):
        v = args[k]
        if isinstance(v, str):
            parts.append(f'{k}="{v}"')
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts)


def format_json(summary: TraceSummary, full_answer: bool) -> str:
    """Format a TraceSummary as structured JSON. The --full flag is honored
    by always including the complete answer (no truncation in JSON)."""
    return json.dumps({
        "run_id": summary.run_id,
        "trace_file": summary.trace_file,
        "prompt": summary.prompt,
        "model": summary.model,
        "kg_enabled": summary.kg_enabled,
        "kg_chars": summary.kg_chars,
        "system_prompt_chars": summary.system_prompt_chars,
        "tools_available": summary.tools_available,
        "turns": [
            [{"name": tc.name, "args": tc.args} for tc in turn]
            for turn in summary.turns
        ],
        "total_tool_calls": summary.total_tool_calls,
        "final_answer": summary.final_answer,
        "duration_seconds": summary.duration_seconds,
        "completed_normally": summary.completed_normally,
        "termination_note": summary.termination_note,
    }, indent=2)


def _most_recent_trace() -> Path | None:
    """Find the newest trace file in TRACES_DIR. Returns None if none exist."""
    if not TRACES_DIR.exists():
        return None
    candidates = list(TRACES_DIR.glob("*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect a Spire agent trace.")
    parser.add_argument(
        "trace_file",
        nargs="?",
        help="Path to a trace file. Defaults to the most recent in traces/.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Include the full final answer (no truncation).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON instead of formatted text.",
    )
    args = parser.parse_args(argv)

    if args.trace_file:
        path = Path(args.trace_file)
        if not path.exists():
            print(f"Trace file not found: {path}", file=sys.stderr)
            return 1
    else:
        recent = _most_recent_trace()
        if recent is None:
            print(
                f"No trace files found in {TRACES_DIR}. "
                "Run the agent first, or pass an explicit path.",
                file=sys.stderr,
            )
            return 1
        path = recent

    summary = parse_trace(path)
    if args.json:
        print(format_json(summary, full_answer=args.full))
    else:
        print(format_text(summary, full_answer=args.full))
    return 0


if __name__ == "__main__":
    sys.exit(main())
