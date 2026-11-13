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
    # §1.1.d (SQL_EMITTER_MULTIFIELD_ITERATION.md §4 extension):
    # the iterated `supplier_id` sentinel is now mapped, so it renders
    # as S.VENDOR_ID = :iteration_value. Pre-patch it fell through to
    # `-- unmapped iteration arg: supplier_id`, which is not SQL.
    #
    # The old assertion `":supplier_id" in step2` was aspirational:
    # _emit_step's sentinel branch hardcodes value=":iteration_value"
    # for every sentinel arg, so `:supplier_id` can never appear. That
    # is why this test was red on master before this window and would
    # have stayed red after the fix — the assertion, not the emitter,
    # was wrong. See §Deviations in SQL_EMITTER_MULTIFIELD_ITERATION.md.
    assert "S.VENDOR_ID = :iteration_value" in step2
    assert "ASSUMPTION [supplier_site_by_parent_vendor_id]" in step2
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


# ─────────────────────────────────────────────────────────────────────
# Defect 1 — multi-field iteration (SQL_EMITTER_MULTIFIELD_ITERATION.md §1)
#
# Plan Step 3 of `get po with distribution details` (and of the
# supplementary prompt 3) has three $iteration_value sentinels on one
# Step. The primary arg (`po_header_id`) has a FilterSpec whose
# template names all three predicates. The siblings (`po_line_id`,
# `line_location_id`) have no FilterSpec, so pre-fix the fallthrough
# appended `-- unmapped iteration arg: <name>` twice into the WHERE
# chain. That is not SQL. Post-fix the multi_field guard suppresses
# the siblings and the primary's three-predicate template stands alone.
# ─────────────────────────────────────────────────────────────────────


def test_shape_6_multifield_iteration_emits_one_predicate():
    """Defect 1. A three-sentinel Step must produce ONE predicate.

    The shape is verbatim from the runtime Plan (captured 2026-11-13):
    Step 3 iterates the poschedule bucket and passes three parent
    fields per call. The primary FilterSpec's template is
    `{alias}.PO_HEADER_ID = {value} AND {alias}.PO_LINE_ID =
    :po_line_id AND {alias}.LINE_LOCATION_ID = :line_location_id`,
    which already names every bind. The fix is that the emitter must
    not append a `-- unmapped iteration arg` comment for each sibling
    — the primary's template is the whole predicate.
    """
    plan = [
        Step(
            1,
            "get_purchase_order_distributions",
            {
                "po_header_id": "$iteration_value",
                "po_line_id": "$iteration_value",
                "line_location_id": "$iteration_value",
            },
            iterate_over={
                "from_step": "poschedule",
                "fields": {
                    "po_header_id": "POHeaderId",
                    "po_line_id": "POLineId",
                    "line_location_id": "LineLocationId",
                },
            },
            filter_source_when_nonempty=False,
        ),
    ]
    sql = emit_sql(plan)[0]

    # (i) No unmapped-iteration comments. This is the defect's signature.
    #     Anchored on the exact shape _emit_step produced ('-- unmapped
    #     iteration arg:'), not the bare phrase, so a future comment
    #     mentioning the same words does not fail the test.
    assert "-- unmapped iteration arg:" not in sql, sql

    # (ii) The primary's three-predicate template is present, once.
    assert sql.count("PO_HEADER_ID = :iteration_value") == 1, sql
    assert sql.count("PO_LINE_ID = :po_line_id") == 1, sql
    assert sql.count("LINE_LOCATION_ID = :line_location_id") == 1, sql

    # (iii) The semicolon lands on the SQL body, not on a comment.
    #     This is a stricter version of test_semicolon_not_glued_to_comment
    #     that uses the multi-field shape as its vehicle.
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            assert not line.rstrip().endswith(";"), (
                f"a comment line ends with ';': {line!r}"
            )
    assert _sql_body(sql).rstrip().endswith(";")


# ─────────────────────────────────────────────────────────────────────
# Defect 2 — numeric-literal quoting (SQL_EMITTER_MULTIFIELD_ITERATION.md §2)
#
# `show me PO 2144` resolves to Step 1 get_purchase_order_by_id with
# tool_args {'po_header_id': '2144'}. PO_HEADER_ID is a numeric column
# on PO_HEADERS_ALL; the pre-fix predicate emitted `= '2144'` (a string
# literal). Post-fix `value_kind="numeric"` on the FilterSpec makes
# _resolve_value emit `= 2144` unquoted.
# ─────────────────────────────────────────────────────────────────────


def test_shape_7_numeric_literal_is_unquoted():
    """Defect 2. A numeric column compares to a numeric literal.

    The shape is verbatim from the runtime Plan (captured 2026-11-13):
    Step 1 of `show me PO 2144` carries a single by-id filter whose
    template is `{alias}.PO_HEADER_ID = {value}`. PO_HEADER_ID is
    numeric; the pre-fix output was `= '2144'`. Post-fix it is `= 2144`.
    """
    plan = [Step(1, "get_purchase_order_by_id", {"po_header_id": "2144"})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)

    # The numeric form is present.
    assert "WHERE P.PO_HEADER_ID = 2144" in body, sql
    # The quoted-string form is absent.
    assert "WHERE P.PO_HEADER_ID = '2144'" not in body, sql


def test_shape_8_string_literal_stays_quoted():
    """Over-reach guard for Defect 2. value_kind is opt-in: a filter
    without it keeps the quoted-string form.

    `status='ACTIVE'` is the existing single-WHERE shape (test_shape_1)
    and its predicate (`ENABLED_FLAG = 'Y'`) does not go through the
    numeric branch. This test pins that _resolve_value's default is
    unchanged for the filters the fix did not touch.
    """
    plan = [Step(1, "search_suppliers", {"status": "ACTIVE"})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)
    assert "P.ENABLED_FLAG = 'Y'" in body, sql
