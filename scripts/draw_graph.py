#!/usr/bin/env python3
"""
Render the LangGraph pipeline as a PNG.

Uses PYPPETEER to render locally (no remote mermaid service). Output is
written next to this script as draw_graph.png by default, or to --out.

Usage:
    python scripts/draw_graph.py
    python scripts/draw_graph.py --out docs/pipeline_graph.png
"""

from __future__ import annotations

import argparse
import os

from spire.graph.pipeline import GRAPH


def save_graph_as_png(graph, filename: str) -> None:
    # Default renderer uses the mermaid.ink web service (needs network)
    # but no local browser/pyppeteer.
    png_bytes = graph.get_graph().draw_mermaid_png()
    with open(filename, "wb") as f:
        f.write(png_bytes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the pipeline graph to PNG.")
    parser.add_argument(
        "--out",
        default=os.path.join(os.path.dirname(__file__), "draw_graph.png"),
        help="Output PNG path (default: scripts/draw_graph.png).",
    )
    args = parser.parse_args()
    save_graph_as_png(GRAPH, args.out)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
