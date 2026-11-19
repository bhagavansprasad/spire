"""Unit tests for the SQL emitter — one per plan shape in the POC.

Shapes are taken verbatim from the runtime Plans captured on the live
pod (2026-10-07). The emitter's input is a Plan, which is a list of
Step objects. These tests construct minimal Step objects with the same
attributes the real planner produces; no LLM, no KG, no executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

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
    # Order is alphabetical by field_name now that columns come from the
    # KG (kg_sql_column), not the hand-authored list — so assert presence,
    # not first-position.
    assert "P.VENDOR_ID" in body
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
    assert "S.VENDOR_ID = :iteration_value" in step2
    assert "keep parents where this returns rows" in step2
    assert "ASSUMPTION [bu_literal_from_overlay]" in step2
    assert "ASSUMPTION [site_supplier_id_maps_to_vendor_id]" in step2


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
# §3.3b — filter/aggregation columns resolve to verified KG carriers
# (not hand-authored stub columns). F-060 taught us existence ≠ populated
# and that a hand-authored column can be absent from the pod entirely.
# ─────────────────────────────────────────────────────────────────────


def test_po_status_filter_uses_document_status_not_authorization_status():
    """PO_HEADERS_ALL has DOCUMENT_STATUS, not AUTHORIZATION_STATUS. The
    filter's predicate_template must name the real column, or the emitted
    SQL fails ORA-00904 on the pod."""
    plan = [Step(1, "search_purchase_orders", {"status": "OPEN"})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)
    assert "P.DOCUMENT_STATUS = 'OPEN'" in body
    assert "AUTHORIZATION_STATUS" not in sql


def test_po_status_aggregation_uses_document_status_and_derived_amount():
    """aggregate_purchase_orders_by_status grouped on the absent
    AUTHORIZATION_STATUS and summed the absent AMOUNT. Both must be the
    verified carriers: DOCUMENT_STATUS and the derived line-amount sum."""
    plan = [Step(1, "aggregate_purchase_orders_by_status", {"top_n": "5"})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)
    assert "GROUP BY P.DOCUMENT_STATUS" in body
    assert "AUTHORIZATION_STATUS" not in sql
    assert "SUM(P.AMOUNT)" not in body
    assert "UNIT_PRICE * L.QUANTITY" in body
    # The derived measure is a correlated subquery and must NOT be
    # re-qualified with the base alias (would become SUM(P.(SELECT ...))).
    assert "P.(SELECT" not in body


def test_qualify_measure_passes_nested_subquery_through_unchanged():
    """A measure whose argument is a correlated subquery already carries
    its own aliases; _qualify_measure must not prefix the base alias."""
    from spire.rendering.sql_emitter import _qualify_measure

    template = (
        "SUM((SELECT SUM(L.UNIT_PRICE * L.QUANTITY) FROM PO_LINES_ALL L "
        "WHERE L.PO_HEADER_ID = P.PO_HEADER_ID))"
    )
    assert _qualify_measure(template, "P") == template
    # The plain-column path still qualifies.
    assert _qualify_measure("SUM(INVOICE_AMOUNT)", "P") == "SUM(P.INVOICE_AMOUNT)"


def test_po_supplier_id_filter_uses_vendor_id_not_segment1():
    """F-065: the search_purchase_orders supplier_id arg is the numeric
    SupplierId (= VENDOR_ID), not the SupplierNumber (SEGMENT1). The old
    template matched SEGMENT1 against a numeric VENDOR_ID and returned 0
    rows where REST returned the supplier's open POs."""
    plan = [Step(1, "search_purchase_orders", {"supplier_id": "300000047414503"})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)
    assert "P.VENDOR_ID = '300000047414503'" in body
    # SEGMENT1 legitimately appears in the SELECT list (the PO number);
    # what must be absent is the old WHERE predicate that matched it.
    assert "SEGMENT1 = '300000047414503'" not in body
    assert "IN (SELECT VENDOR_ID FROM POZ_SUPPLIERS" not in body
    assert "ASSUMPTION [supplier_maps_to_vendor_id]" in sql


def test_standard_receipt_uses_left_join_for_nullable_pay_from_customer():
    """F-074: AR_CASH_RECEIPTS_ALL.PAY_FROM_CUSTOMER is NULL on 39 of
    79,777 receipts (UNID/REV/NSF/APP). REST's top-level /standardReceipts
    returns those receipts with NULL CustomerName/CustomerAccountNumber, so
    the emitted SQL must LEFT JOIN (keep them with NULL customer), not
    INNER JOIN (silently drop them)."""
    plan = [Step(1, "search_standard_receipts", {"customer_name": "ABC Corporation Americas"})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)
    assert "LEFT JOIN HZ_CUST_ACCOUNTS CA ON CA.CUST_ACCOUNT_ID = R.PAY_FROM_CUSTOMER" in body
    assert "LEFT JOIN HZ_PARTIES HP ON HP.PARTY_ID = CA.PARTY_ID" in body
    # The old INNER JOIN (bare "JOIN") must be gone: the only join lines
    # are the two LEFT JOINs above.
    join_lines = [
        l.strip() for l in body.splitlines()
        if l.strip().startswith("JOIN ") or l.strip().startswith("LEFT JOIN ")
    ]
    assert join_lines == [
        "LEFT JOIN HZ_CUST_ACCOUNTS CA ON CA.CUST_ACCOUNT_ID = R.PAY_FROM_CUSTOMER",
        "LEFT JOIN HZ_PARTIES HP ON HP.PARTY_ID = CA.PARTY_ID",
    ]


def test_standard_receipt_customer_site_resolves_name_not_absent_column():
    """F-073: AR_CASH_RECEIPTS_ALL has no CUSTOMER_SITE column — only the
    numeric CUSTOMER_SITE_USE_ID (18,365/79,777 populated) — so the old
    ``{alias}.CUSTOMER_SITE = ?`` predicate raised ORA-00904. The site
    NAME is the receipt's site-use chain's HZ_LOCATIONS.CITY (verified:
    receipts 1/2/21 -> CITY 'Santa Clara' = REST CustomerSite; 1,735
    site-wide inside the REST business unit = REST's 1,735)."""
    plan = [Step(1, "search_standard_receipts", {"customer_site": "Santa Clara"})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)

    # The absent column must not be referenced.
    assert "R.CUSTOMER_SITE = " not in body
    # The site name resolves through the receipt -> site-use -> acct-site
    # -> party-site -> location chain.
    assert "R.CUSTOMER_SITE_USE_ID IN (SELECT SU.SITE_USE_ID" in body
    assert "HZ_CUST_SITE_USES_ALL SU" in body
    assert "HZ_CUST_ACCT_SITES_ALL CS" in body
    assert "HZ_PARTY_SITES PS" in body
    assert "HZ_LOCATIONS LOC ON LOC.LOCATION_ID = PS.LOCATION_ID" in body
    assert "LOC.CITY = 'Santa Clara'" in body
    assert "ASSUMPTION [standard_receipt_site_client_side]" in sql


def test_standard_receipt_customer_name_and_site_both_filter():
    """A customer-scoped site prompt must constrain both: PARTY_NAME on the
    customer and the resolved site name on the location chain."""
    plan = [
        Step(
            1,
            "search_standard_receipts",
            {"customer_name": "ABC Corporation Americas", "customer_site": "Santa Clara"},
        )
    ]
    body = _strip_comments(emit_sql(plan)[0])
    assert "HP.PARTY_NAME = 'ABC Corporation Americas'" in body
    assert "LOC.CITY = 'Santa Clara'" in body
    assert " AND " in body


def test_customer_account_balances_use_ledger_currency_aggregates():
    """F-072: both CustomerAccount balances are computed aggregates over
    AR_PAYMENT_SCHEDULES_ALL in LEDGER currency. The invoice-currency sum
    misses the GBP->USD conversion (account 26370's -1,500 GBP payment row
    is -948.17 USD, the residual that never reconciled). Verified exact on
    29 accounts: open = SUM over all classes; transactions due = SUM where
    CLASS in ('INV','DM') and DUE_DATE <= SYSDATE (CM/PMT and future
    installments excluded)."""
    plan = [
        Step(
            1,
            "get_customer_account_by_name",
            {"customer_name": "ABC Corporation Americas"},
        )
    ]
    body = _strip_comments(emit_sql(plan)[0])
    assert "SUM(S.ACCTD_AMOUNT_DUE_REMAINING)" in body
    assert "S.CLASS IN ('INV','DM') AND S.DUE_DATE <= TRUNC(SYSDATE)" in body
    # The invoice-currency column must not carry either balance.
    assert "SUM(S.AMOUNT_DUE_REMAINING)" not in body
    # SUM is NULL for an account with no schedules; REST returns 0.
    assert "NVL((SELECT SUM(S.ACCTD_AMOUNT_DUE_REMAINING)" in body


def test_account_receipt_unapplied_amount_reads_pmt_schedule():
    """F-075: AMOUNT - SUM(AR_RECEIVABLE_APPLICATIONS_ALL.AMOUNT_APPLIED)
    overstates on partially-applied receipts (REST reports 0 where the
    applications table sums to less than AMOUNT). The receipt's own PMT
    schedule remaining is exact: -AMOUNT_DUE_REMAINING (8/8 receipts equal
    REST, including 619466 -> 0 and 300000066476397 -> 1135.2)."""
    plan = [Step(1, "get_account_receipts", {"account_id": "300000047368730"})]
    body = _strip_comments(emit_sql(plan)[0])
    assert "SELECT -S.AMOUNT_DUE_REMAINING FROM AR_PAYMENT_SCHEDULES_ALL S" in body
    assert "S.CLASS = 'PMT'" in body
    assert "AR_RECEIVABLE_APPLICATIONS_ALL" not in body


def test_poschedule_amount_is_derived_not_stub_amout():
    """F-062: PO_LINE_LOCATIONS_ALL.AMOUNT is a stub (NULL on 99.95% of
    rows), so POSchedule.Amount must derive line UNIT_PRICE x schedule
    QUANTITY, not bind the stub AMOUNT column."""
    plan = [Step(1, "get_purchase_order_schedules", {"po_header_id": "2144"})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)
    assert (
        "(SELECT L.UNIT_PRICE FROM PO_LINES_ALL L WHERE L.PO_LINE_ID = S.PO_LINE_ID) * S.QUANTITY"
        in body
    )
    # The stub AMOUNT column must not be selected as a bare column.
    assert "S.AMOUNT" not in body


def test_purchase_order_line_tax_is_from_distributions_not_schedule_stub():
    """F-063: PO_LINE_LOCATIONS_ALL.ESTIMATED_TAX_AMOUNT is NULL on ALL
    310,952 schedule rows (a complete stub), so the line TotalTax/Total
    must read PO_DISTRIBUTIONS_ALL.RECOVERABLE_TAX + NONRECOVERABLE_TAX,
    NVL-wrapped to 0 when a line has no distributions / no tax."""
    plan = [Step(1, "get_purchase_order_lines", {"po_header_id": "2144"})]
    sql = emit_sql(plan)[0]
    body = _strip_comments(sql)
    assert "RECOVERABLE_TAX + D.NONRECOVERABLE_TAX" in body
    assert "NVL(" in body
    # The stub ESTIMATED_TAX_AMOUNT carrier must be gone.
    assert "ESTIMATED_TAX_AMOUNT" not in body
