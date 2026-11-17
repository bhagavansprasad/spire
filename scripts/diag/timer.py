"""scripts/diag/timer.py — span recorder for promptkit diagnostics.

Spans are collected in call order and printed once, all together, by
summary(). Each entry shows: layer.label and elapsed only.
"""
from __future__ import annotations

import time
from contextlib import contextmanager, asynccontextmanager

_spans: list[dict] = []
_enabled: bool = False


def enable() -> None:
    global _enabled
    _enabled = True


def disable() -> None:
    global _enabled
    _enabled = False


def reset() -> None:
    _spans.clear()


def is_enabled() -> bool:
    return _enabled


@contextmanager
def timer(layer: str, label: str = "", **tags):
    if not _enabled:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _spans.append({"layer": layer, "label": label,
                       "elapsed": time.perf_counter() - t0, **tags})


@asynccontextmanager
async def atimer(layer: str, label: str = "", **tags):
    if not _enabled:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _spans.append({"layer": layer, "label": label,
                       "elapsed": time.perf_counter() - t0, **tags})


def summary() -> str:
    """All spans in call order. Elapsed only, no start/end."""
    if not _spans:
        return "[timings] (no spans recorded)"
    out = [
        "",
        "[timings] spans (in call order)",
        f"  {'#':>2}  {'layer.label':<32} {'elapsed':>10}",
        "  " + "-" * 50,
    ]
    for i, s in enumerate(_spans, start=1):
        tag = f"{s['layer']}.{s['label']}" if s['label'] else s['layer']
        out.append(f"  {i:>2}  {tag:<32} {s['elapsed']:>9.3f}s")
    return "\n".join(out)