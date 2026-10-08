"""Unit tests for the SQL emitter — one per plan shape in the POC.

Shapes are taken verbatim from the runtime Plans captured on the live
pod (2026-10-07). The emitter's input is a Plan, which is a list of
Step objects. These tests construct minimal Step objects with the same
attributes the real planner produces; no LLM, no KG, no executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from spire.rendering.sql_emitter import emit_sql


@dataclass
class Step:
    step_id: int
    tool_name: str
    tool_args: dict[str, Any]
    iterate_over: dict[str, str] | None = None
    client_filters: list[dict[str, Any]] | None = None
    output_name: str = "out"
    output_dedupe_by: str | None = None
    filter_source_when_empty: bool = False
    filter_source_when_nonempty: bool = False
    stamp_parent_key: bool = False


def _strip_comments(sql: str) -> str:
    return "\n".join(
        line for line in sql.splitlines()
        if not line.strip().startswith("--")
    ).strip()


def _sql_body(stmt: str) -> str:
    """Everything up to the first blank line, minus header comments."""
    block = stmt.split("\n\n")[0]
    lines = [
        l for l in block.splitlines()
        if not l.strip().startswith("--")
    ]
    return "\n".join(lines).strip()


# ─────────────────────────────────────────────────────────────────────
# Shape 1 — simple WHERE
# ─────────────────────────────────────────────────────────────────────


def test_shape_1_active_suppliers():
    plan = [Step(1, "search_suppliers", {"status": "ACTIVE"})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)
    assert "SELECT P.VENDOR_ID" in body
    assert "HP.PARTY_NAME" in body
    assert "FROM POZ_SUPPLIERS P" in body
    assert "JOIN HZ_PARTIES HP ON HP.PARTY_ID = P.PARTY_ID" in body
    assert "WHERE P.ENABLED_FLAG = 'Y'" in body
    assert "ASSUMPTION [status_maps_to_enabled_flag]" in sql


# ─────────────────────────────────────────────────────────────────────
# Shape 2 — multi-filter AND (country filter requires the address join)
# ─────────────────────────────────────────────────────────────────────


def test_shape_2_active_suppliers_in_us():
    plan = [Step(1, "search_suppliers",
                 {"status": "ACTIVE", "country": "US"})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)
    assert "P.ENABLED_FLAG = 'Y'" in body
    assert "L.COUNTRY = 'US'" in body
    assert "AND" in body
    assert "ASSUMPTION [status_maps_to_enabled_flag]" in sql
    assert "ASSUMPTION [address_join_for_country]" in sql


def test_shape_2_country_filter_pulls_in_address_join():
    """Regression: the country filter references L.COUNTRY. Before the
    requires_join field, the join was missing and the SQL was invalid."""
    plan = [Step(1, "search_suppliers", {"country": "US"})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)
    assert "L.COUNTRY = 'US'" in body
    assert "JOIN HZ_PARTY_SITES PS" in body
    assert "JOIN HZ_LOCATIONS L" in body


# ─────────────────────────────────────────────────────────────────────
# Shape 3 — include flag (LEFT JOIN)
# ─────────────────────────────────────────────────────────────────────


def test_shape_3_suppliers_with_addresses():
    plan = [Step(1, "search_suppliers", {"include_addresses": True})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)
    assert "LEFT JOIN HZ_PARTY_SITES PS" in body
    assert "LEFT JOIN HZ_LOCATIONS L" in body
    assert "WHERE" not in body


# ─────────────────────────────────────────────────────────────────────
# Shape 4 — two-step iterating edge traversal
# ─────────────────────────────────────────────────────────────────────


def test_shape_4_suppliers_with_site_in_bu():
    plan = [
        Step(1, "search_suppliers", {}),
        Step(
            2,
            "search_suppliers_by_site_bu",
            {"supplier_id": "$iteration_value",
             "business_unit": "US1 Business Unit"},
            iterate_over={"from_step": "suppliers", "field": "SupplierId"},
            filter_source_when_nonempty=True,
        ),
    ]
    sqls = emit_sql(plan)
    assert len(sqls) == 2
    step1, step2 = sqls
    assert "FROM POZ_SUPPLIERS P" in step1
    assert "WHERE" not in _strip_comments(step1)
    assert "FROM POZ_SUPPLIER_SITES_ALL_M S" in step2
    assert "S.PRC_BU_ID = 300000046987012" in step2
    assert ":supplier_id" in step2
    assert "keep parents where this returns rows" in step2
    assert "ASSUMPTION [bu_literal_from_overlay]" in step2


# ─────────────────────────────────────────────────────────────────────
# Shape 5 — plain fetch (count is downstream)
# ─────────────────────────────────────────────────────────────────────


def test_shape_5_count_of_suppliers():
    plan = [Step(1, "search_suppliers", {})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)
    assert "FROM POZ_SUPPLIERS P" in body
    assert "JOIN HZ_PARTIES HP" in body
    assert "WHERE" not in body
    assert "COUNT" not in body.upper()


# ─────────────────────────────────────────────────────────────────────
# Terminator placement — the semicolon belongs on the SQL body
# ─────────────────────────────────────────────────────────────────────


def test_semicolon_not_glued_to_comment():
    """Regression: the terminator was being glued to the last assumption
    comment ('...unverified.;'). The SQL body now ends with ';' and the
    assumptions follow on their own lines."""
    plan = [Step(1, "search_suppliers", {"status": "ACTIVE"})]
    sql = emit_sql(plan)[0]
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            assert not line.rstrip().endswith(";"), (
                f"a comment line ends with ';': {line!r}"
            )
    assert _sql_body(sql).rstrip().endswith(";")


def test_all_statements_end_with_semicolon():
    plan = [
        Step(1, "search_suppliers", {}),
        Step(
            2,
            "search_suppliers_by_site_bu",
            {"supplier_id": "$iteration_value",
             "business_unit": "US1 Business Unit"},
            iterate_over={"from_step": "suppliers", "field": "SupplierId"},
            filter_source_when_nonempty=True,
        ),
    ]
    for stmt in emit_sql(plan):
        assert _sql_body(stmt).rstrip().endswith(";")


# ─────────────────────────────────────────────────────────────────────
# Determinism
# ─────────────────────────────────────────────────────────────────────


def test_determinism():
    plan = [Step(1, "search_suppliers", {"status": "ACTIVE"})]
    assert emit_sql(plan) == emit_sql(plan)
