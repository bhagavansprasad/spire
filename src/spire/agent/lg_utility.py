"""LangGraph visualization helpers.

Optional — used by scripts/draw_graph.py to produce a one-shot PNG
of the agent graph. Not invoked during normal agent runs.
"""

from pathlib import Path

from langchain_core.runnables.graph_mermaid import MermaidDrawMethod


def save_graph_as_png(graph, output_path: Path) -> None:
    """Render a LangGraph as PNG at output_path."""
    png_bytes = graph.get_graph().draw_mermaid_png(
        draw_method=MermaidDrawMethod.PYPPETEER,
    )
    output_path.write_bytes(png_bytes)
