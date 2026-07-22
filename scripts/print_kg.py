#!/usr/bin/env python3
"""
print_kg.py — Inspect the Spire Knowledge Graph.

Reads the 9 KG tables (kg_entity, kg_entity_field, kg_edge, kg_pattern,
kg_vocabulary, kg_pattern_binding, kg_entity_tool, kg_entity_filter,
kg_edge_tool) and prints them as formatted ASCII tables, with row counts
and an FK summary.

Requires:
- Oracle container running (oracle26ai_db_bhagavan)
- personas.yaml present with the default_dev persona
- spire installed in the active environment (pip install -e . from repo root)

Usage:
    # From the repo root, with venv active:
    python scripts/print_kg.py                      # print everything
    python scripts/print_kg.py --table kg_entity    # just one table
    python scripts/print_kg.py --schema-only        # skip data rows
    python scripts/print_kg.py --counts-only        # just row counts
    python scripts/print_kg.py --max-col-width 60   # truncate wide cols
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from textwrap import shorten

from spire.config import load_persona
from spire.oracle.client import OracleClient


# ---------------------------------------------------------------------------
# Table metadata — names, column lists, and the SQL to read them.
#
# Ordered parent-first so FK relationships read naturally top-to-bottom.
# ---------------------------------------------------------------------------

TABLES: list[dict] = [
    {
        "name": "kg_entity",
        "purpose": "The 5 entities Spire knows about (Supplier, Invoice, "
                   "PurchaseOrder, Buyer, Address).",
        "columns": ["entity_name", "canonical_id_field", "display_name_field",
                    "endpoint_path", "description"],
        "sql": "SELECT entity_name, canonical_id_field, display_name_field, "
               "endpoint_path, description FROM kg_entity "
               "ORDER BY entity_name",
        "clob_cols": {"description"},
        "expected_rows": 20,
    },
    {
        "name": "kg_entity_field",
        "purpose": "Per-entity field catalog. field_role tells the planner "
                   "what each field is (canonical_id, display_name, status, "
                   "date, amount, reference, projection).",
        "columns": ["entity_name", "field_name", "field_role",
                    "data_type_hint", "notes"],
        "sql": "SELECT entity_name, field_name, field_role, data_type_hint, "
               "notes FROM kg_entity_field "
               "ORDER BY entity_name, field_name",
        "clob_cols": set(),
        "expected_rows": 169,
    },
    {
        "name": "kg_edge",
        "purpose": "Relationships between entities. Each edge declares "
                   "from_entity, to_entity, the join fields on each side, "
                   "and a traversal_hint.",
        "columns": ["edge_name", "from_entity", "to_entity",
                    "from_join_field", "to_join_field", "cardinality",
                    "traversal_hint", "notes"],
        "sql": "SELECT edge_name, from_entity, to_entity, from_join_field, "
               "to_join_field, cardinality, traversal_hint, notes "
               "FROM kg_edge ORDER BY edge_name",
        "clob_cols": {"traversal_hint", "notes"},
        "expected_rows": 16,
    },
    {
        "name": "kg_pattern",
        "purpose": "Reusable logical shapes (e.g., no_invoices_in_N_months) "
                   "the planner can apply. 'mechanics' is the step-by-step "
                   "expansion the planner emits.",
        "columns": ["pattern_name", "shape", "parameters", "mechanics",
                    "example"],
        "sql": "SELECT pattern_name, shape, parameters, mechanics, example "
               "FROM kg_pattern ORDER BY pattern_name",
        "clob_cols": {"parameters", "mechanics"},
        "expected_rows": 3,
    },
    {
        "name": "kg_vocabulary",
        "purpose": "Business-term → canonical-value mappings: country "
                   "names, PO statuses, entity synonyms, relationship "
                   "phrases.",
        "columns": ["vocab_kind", "term", "canonical_value", "notes"],
        "sql": "SELECT vocab_kind, term, canonical_value, notes "
               "FROM kg_vocabulary ORDER BY vocab_kind, term",
        "clob_cols": set(),
        "expected_rows": 93,
    },
    {
        "name": "kg_pattern_binding",
        "purpose": "Wires an entity's filter_type (e.g. Supplier + "
                   "has_no_recent_invoices) to a pattern_name plus the "
                   "parameter bindings that fill in the pattern.",
        "columns": ["entity_name", "filter_type", "pattern_name",
                    "parameter_bindings"],
        "sql": "SELECT entity_name, filter_type, pattern_name, "
               "parameter_bindings FROM kg_pattern_binding "
               "ORDER BY entity_name, filter_type",
        "clob_cols": {"parameter_bindings"},
        "expected_rows": 3,
    },
    {
        "name": "kg_entity_tool",
        "purpose": "Maps (entity_name, filter_type) to the MCP tool the "
                   "executor calls to fetch that entity with that filter.",
        "columns": ["entity_name", "filter_type", "mcp_tool_name", "notes"],
        "sql": "SELECT entity_name, filter_type, mcp_tool_name, notes "
               "FROM kg_entity_tool ORDER BY entity_name, filter_type",
        "clob_cols": set(),
        "expected_rows": 8,
    },
    {
        "name": "kg_entity_filter",
        "purpose": "Filter definitions (formerly hardcoded in the planner). "
                   "mechanism tells the planner if a filter is entity_level "
                   "(dedicated fetcher) or edge_traversal (walks to a child).",
        "columns": ["entity_name", "filter_type", "mechanism",
                    "tool_arg_name", "vocab_kind", "target_entity",
                    "kg_filter_type", "implicit_vocab_kind", "implicit_term",
                    "query_style", "filter_field", "filter_op", "notes"],
        "sql": "SELECT entity_name, filter_type, mechanism, tool_arg_name, "
               "vocab_kind, target_entity, kg_filter_type, "
               "implicit_vocab_kind, implicit_term, query_style, "
               "filter_field, filter_op, notes "
               "FROM kg_entity_filter ORDER BY entity_name, filter_type",
        "clob_cols": set(),
        "expected_rows": 21,
    },
    {
        "name": "kg_edge_tool",
        "purpose": "Maps an edge_name to the MCP tool the executor calls "
                   "to traverse that edge.",
        "columns": ["edge_name", "mcp_tool_name", "notes"],
        "sql": "SELECT edge_name, mcp_tool_name, notes FROM kg_edge_tool "
               "ORDER BY edge_name",
        "clob_cols": set(),
        "expected_rows": 15,
    },
]


# Foreign-key relationships, for the relations summary.
FK_RELATIONS: list[tuple[str, str, str]] = [
    ("kg_entity_field",    "entity_name",  "kg_entity.entity_name"),
    ("kg_edge",            "from_entity",  "kg_entity.entity_name"),
    ("kg_edge",            "to_entity",    "kg_entity.entity_name"),
    ("kg_pattern_binding", "entity_name",  "kg_entity.entity_name"),
    ("kg_pattern_binding", "pattern_name", "kg_pattern.pattern_name"),
    ("kg_entity_tool",     "entity_name",  "kg_entity.entity_name"),
    ("kg_entity_filter",   "entity_name",  "kg_entity.entity_name"),
    ("kg_edge_tool",       "edge_name",    "kg_edge.edge_name"),
]


# ---------------------------------------------------------------------------
# CLOB helper — mirrors loader.py's approach.
# ---------------------------------------------------------------------------

async def _read_clob(value) -> str:
    """Coerce a possibly-CLOB column value to a Python str.

    Must be called while the OracleClient connection is still open.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # AsyncLOB has a .read() coroutine.
    read = getattr(value, "read", None)
    if read is not None:
        result = read()
        if asyncio.iscoroutine(result):
            return await result
        return result
    return str(value)


async def _materialize_row(row: tuple, columns: list[str],
                           clob_cols: set[str]) -> tuple:
    """Read any CLOB columns in this row and return a plain-string tuple."""
    out: list = []
    for col, val in zip(columns, row):
        if col in clob_cols:
            out.append(await _read_clob(val))
        else:
            out.append("" if val is None else str(val))
    return tuple(out)


# ---------------------------------------------------------------------------
# ASCII table rendering.
# ---------------------------------------------------------------------------

def _truncate(value: str, max_width: int) -> str:
    """Shorten a cell value, replacing internal newlines for compact display."""
    if value is None:
        return ""
    # Collapse internal newlines so a row stays on one line.
    flat = value.replace("\n", " ").replace("\r", " ")
    if max_width and len(flat) > max_width:
        return shorten(flat, width=max_width, placeholder="…")
    return flat


def render_table(columns: list[str], rows: list[tuple],
                 max_col_width: int) -> str:
    """Render rows as a fixed-width ASCII table."""
    if not rows:
        # Header only.
        header = " | ".join(columns)
        sep = "-+-".join("-" * len(c) for c in columns)
        return f"{header}\n{sep}\n(no rows)"

    # Truncate everything first.
    truncated: list[list[str]] = []
    for row in rows:
        truncated.append([_truncate(cell, max_col_width) for cell in row])

    # Column widths = max of header and any cell.
    widths: list[int] = []
    for i, col in enumerate(columns):
        cell_max = max((len(r[i]) for r in truncated), default=0)
        widths.append(max(len(col), cell_max))

    def fmt_row(cells: list[str]) -> str:
        return " | ".join(c.ljust(w) for c, w in zip(cells, widths))

    header = fmt_row(columns)
    sep = "-+-".join("-" * w for w in widths)
    body = "\n".join(fmt_row(r) for r in truncated)
    return f"{header}\n{sep}\n{body}"


# ---------------------------------------------------------------------------
# Top-level operations.
# ---------------------------------------------------------------------------

async def fetch_table(oc: OracleClient, meta: dict) -> list[tuple]:
    """Run the SELECT for a table and materialize CLOBs."""
    raw = await oc.fetch_all(meta["sql"])
    out: list[tuple] = []
    for row in raw:
        out.append(await _materialize_row(row, meta["columns"],
                                          meta["clob_cols"]))
    return out


def print_section(title: str) -> None:
    bar = "=" * 78
    print(f"\n{bar}\n{title}\n{bar}")


def print_subsection(title: str) -> None:
    print(f"\n--- {title} ---\n")


async def main_async(args) -> int:
    persona = load_persona("default_dev")
    if persona.oracle is None:
        print("ERROR: persona has no oracle config; check personas.yaml",
              file=sys.stderr)
        return 1

    tables_to_show = TABLES
    if args.table:
        tables_to_show = [t for t in TABLES if t["name"] == args.table]
        if not tables_to_show:
            print(f"ERROR: unknown table '{args.table}'. Choose from: "
                  f"{', '.join(t['name'] for t in TABLES)}",
                  file=sys.stderr)
            return 1

    # ---- Counts pass ----
    print_section("Knowledge Graph — Tables and Row Counts")
    async with OracleClient(persona) as oc:
        actual_counts: dict[str, int] = {}
        for meta in tables_to_show:
            rows = await oc.fetch_all(f"SELECT COUNT(*) FROM {meta['name']}")
            count = rows[0][0] if rows else 0
            actual_counts[meta["name"]] = count

        # Print the counts summary.
        name_w = max(len(t["name"]) for t in tables_to_show)
        print(f"{'Table'.ljust(name_w)}   Rows   Expected   Status")
        print("-" * (name_w + 30))
        for meta in tables_to_show:
            actual = actual_counts[meta["name"]]
            expected = meta["expected_rows"]
            status = "ok" if actual == expected else f"!! drift ({expected})"
            print(f"{meta['name'].ljust(name_w)}   "
                  f"{str(actual).rjust(4)}   "
                  f"{str(expected).rjust(8)}   {status}")

        if args.counts_only:
            return 0

        # ---- Relations pass ----
        if not args.table:
            print_section("Knowledge Graph — Foreign-Key Relations")
            child_w = max(len(r[0]) for r in FK_RELATIONS)
            col_w = max(len(r[1]) for r in FK_RELATIONS)
            print(f"{'Child table'.ljust(child_w)}   "
                  f"{'Column'.ljust(col_w)}   References")
            print("-" * (child_w + col_w + 30))
            for child, col, ref in FK_RELATIONS:
                print(f"{child.ljust(child_w)}   "
                      f"{col.ljust(col_w)}   {ref}")

        # ---- Per-table dump ----
        print_section("Knowledge Graph — Table Contents")
        for meta in tables_to_show:
            print_subsection(f"{meta['name']}  ({actual_counts[meta['name']]} rows)")
            print(f"Purpose: {meta['purpose']}\n")

            if args.schema_only:
                print("Columns: " + ", ".join(meta["columns"]))
                continue

            rows = await fetch_table(oc, meta)
            print(render_table(meta["columns"], rows, args.max_col_width))

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print Spire Knowledge Graph tables, relations, and data.",
    )
    parser.add_argument(
        "--table",
        choices=[t["name"] for t in TABLES],
        help="Print just one table instead of all nine.",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Skip data rows; show only column lists and counts.",
    )
    parser.add_argument(
        "--counts-only",
        action="store_true",
        help="Print only the row-count summary and exit.",
    )
    parser.add_argument(
        "--max-col-width",
        type=int,
        default=50,
        help="Truncate cell values longer than this many characters "
             "(default: 50; use 0 for no truncation).",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())


