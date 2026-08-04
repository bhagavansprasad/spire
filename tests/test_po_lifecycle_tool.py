"""Tests for the PO lifecycle tool (Module 5).

Two layers:

  PURE      the arithmetic, the classification, the risk rating. No pod,
            no client. This is where a wrong number or a wrong rating
            would be invisible, because nothing downstream can check a
            derived figure or a judgement.

  FAKE      The installments fan-out and the setup fetches driven by a
            stub client. These cover the things that fail
            SILENTLY — totalResults read from the wrong page, a bitten
            cap, a child fetch that dies — none of which are reachable
            without a client.

The contract invariant has its own test and its own name because it is
the one that must never regress quietly: paid_state "unknown" implies
fully_paid is None AND remaining_to_pay is None. JSON has no tri-state
bool, so a flattening bug restores the exact defect the contract removed.

Real data used below comes from curls against fa-esll-dev37 on
2026-07-29 and is recorded in docs/spire_fusion_endpoints_reference.md.
PO 701337 and PO 162034 are the two test orders.
"""

from __future__ import annotations

from datetime import date

import pytest

from spire.mcp_server.tools import po_lifecycle as mod
from spire.mcp_server.tools.po_lifecycle import (
    PAID_STATE_NOTHING_DUE,
    PAID_STATE_PAID,
    PAID_STATE_PARTIAL,
    PAID_STATE_UNKNOWN,
    PAID_STATE_UNPAID,
    PAID_STATES,
    RISK_HIGH,
    RISK_LEVELS,
    RISK_LOW,
    RISK_MEDIUM,
    _assess_risk,
    _classify_paid_leg,
    _is_complete,
    _lifecycle_stage,
    _num,
    _parse_date,
    _recommend_action,
    _responsible_team,
    _schedule_rows,
    _summarise_installments,
    _summarise_invoices,
    _summarise_schedules,
    _summarise_setup,
    get_purchase_order_lifecycle_status,
)


# --------------------------------------------------------------------------
# Real pod data — curled 2026-07-29
# --------------------------------------------------------------------------

SCHEDULES_701337 = [
    {"LineNumber": 2, "ScheduleNumber": 1, "Quantity": 1, "Amount": 119,
     "ReceivedQuantity": 1, "ReceivedAmount": 0, "BilledQuantity": 1,
     "BilledAmount": 119, "ScheduleStatus": "Closed"},
    {"LineNumber": 1, "ScheduleNumber": 1, "Quantity": 4, "Amount": 1116,
     "ReceivedQuantity": 1, "ReceivedAmount": 0, "BilledQuantity": 1,
     "BilledAmount": 279, "ScheduleStatus": "Open"},
]

PO_701337 = {
    "POHeaderId": 300000081255594, "OrderNumber": "701337", "Status": "Open",
    "StatusCode": "OPEN", "SupplierId": 300000047414635, "Supplier": "JGA",
    "SupplierSiteId": 300000076246906, "SupplierSite": "JGA Progress US",
    "BuyerDisplayName": "Eleanor White", "CurrencyCode": "USD",
    "Ordered": 1235, "TotalTax": 0, "PaymentTerms": "Net 30",
    "ProcurementBU": "Progress US Business Unit", "PayOnReceiptFlag": True,
    "FundsStatus": "Partially Liquidated", "Revision": 1,
    "RequiredAcknowledgment": "None", "SupplierCommunicationMethod": "None",
    "Requisition": "914032",
}

SUPPLIER_JGA = {
    "SupplierId": 300000047414635, "Supplier": "JGA", "SupplierNumber": "1254",
    "Status": "ACTIVE", "InactiveDate": None,
    "BusinessRelationship": "Spend Authorized",
    "BusinessRelationshipCode": "SPEND_AUTHORIZED", "OnOFACListFlag": None,
    "UseWithholdingTaxFlag": True, "WithholdingTaxGroup": "1099-PRG-10-PCT",
    "ParentSupplier": None, "OneTimeSupplierFlag": None,
}

SITE_JGA_PROGRESS_US = {
    "SupplierSiteId": 300000076246906, "SupplierSite": "JGA Progress US",
    "ProcurementBU": "Progress US Business Unit", "Status": "ACTIVE",
    "InactiveDate": None, "SitePurposePurchasingFlag": True,
    "SitePurposePayFlag": True, "HoldAllNewPurchasingDocumentsFlag": False,
    "PurchasingHoldReason": None, "HoldAllInvoicesFlag": False,
    "HoldUnvalidatedInvoicesFlag": False, "PaymentHoldDate": None,
    "PaymentHoldReason": None, "MatchApprovalLevel": "3 Way",
    "InvoiceMatchOption": "Receipt", "PaymentTerms": "2/10 Net 30",
}

SCHEDULES_162034 = [
    {"LineNumber": 1, "ScheduleNumber": 1, "Quantity": 2, "Amount": 758,
     "ReceivedQuantity": 2, "ReceivedAmount": 0, "BilledQuantity": 2,
     "BilledAmount": 758, "ScheduleStatus": "Closed"},
]

PO_162034 = {
    "POHeaderId": 1, "OrderNumber": "162034", "Status": "Closed",
    "SupplierId": 2, "Supplier": "Lee Supplies",
    "SupplierSiteId": 3, "SupplierSite": "Lee US1",
    "BuyerDisplayName": "Calvin Roth", "CurrencyCode": "USD",
    "Ordered": 758, "TotalTax": 0, "PaymentTerms": "Net 30",
    "ProcurementBU": "US1 Business Unit", "PayOnReceiptFlag": False,
    "FundsStatus": None,
}

SUPPLIER_LEE = {
    "SupplierId": 2, "Supplier": "Lee Supplies", "SupplierNumber": "1252",
    "Status": "ACTIVE", "InactiveDate": None,
    "BusinessRelationship": "Spend Authorized",
    "BusinessRelationshipCode": "SPEND_AUTHORIZED", "OnOFACListFlag": False,
}

SITE_LEE = {
    "SupplierSiteId": 3, "SupplierSite": "Lee US1", "Status": "ACTIVE",
    "InactiveDate": None, "SitePurposePurchasingFlag": True,
    "SitePurposePayFlag": True, "HoldAllNewPurchasingDocumentsFlag": False,
    "HoldAllInvoicesFlag": False, "HoldUnvalidatedInvoicesFlag": False,
    "PaymentHoldDate": None, "PaymentTerms": "Net 30",
}

INVOICE_162034 = {
    "InvoiceId": 300000049373131, "InvoiceNumber": "162034inv",
    "Supplier": "Lee Supplies", "SupplierNumber": "1252",
    "InvoiceAmount": 830.01, "AmountPaid": 830.01, "InvoiceCurrency": "USD",
    "InvoiceDate": "2013-12-16", "PaidStatus": "Paid",
    "ApprovalStatus": "Not required", "ValidationStatus": "Validated",
    "CanceledFlag": False, "PaymentMethod": "Electronic",
    "PurchaseOrderNumber": "162034",
}

INSTALLMENT_162034 = {
    "InstallmentNumber": 1, "GrossAmount": 830.01, "UnpaidAmount": 0,
    "DueDate": "2014-01-15", "HoldFlag": False, "HoldReason": None,
    "HoldType": None, "HeldBy": None, "HoldDate": None,
    "PaymentMethod": "Electronic", "PaymentPriority": 99,
}


# --------------------------------------------------------------------------
# Fake client
# --------------------------------------------------------------------------

class FakeClient:
    """Stub FusionClient. Routes by path substring; records every call.

    `pages` maps a path fragment to a LIST of responses returned in order,
    which is what makes it possible to assert that totalResults is read
    from the first page and not re-read from later ones.

    Fragment order matters: more specific fragments must be checked first,
    because "invoices" is a substring of the installments child path and
    "suppliers" of the sites child path.
    """

    _ORDER = (
        "invoiceInstallments", "child/sites", "purchaseOrderSchedules",
        "purchaseOrders", "invoices", "suppliers",
    )

    def __init__(self, pages: dict[str, list[dict]], fail_on: str | None = None):
        self.pages = {k: list(v) for k, v in pages.items()}
        self.fail_on = fail_on
        self.calls: list[tuple[str, dict]] = []

    async def get(self, path: str, params: dict | None = None) -> dict:
        self.calls.append((path, dict(params or {})))
        if self.fail_on and self.fail_on in path:
            raise RuntimeError("simulated pod failure")

        for fragment in self._ORDER:
            if fragment in path and fragment in self.pages:
                responses = self.pages[fragment]
                if not responses:
                    return {"items": [], "hasMore": False, "totalResults": 0}
                return responses.pop(0) if len(responses) > 1 else responses[0]

        for fragment, responses in self.pages.items():
            if fragment in path:
                return responses[0] if responses else {"items": []}

        return {"items": [], "hasMore": False, "totalResults": 0}

    def paths_called(self, fragment: str) -> int:
        return sum(1 for path, _ in self.calls if fragment in path)


def _page(items, has_more=False, total=None):
    body = {"items": items, "hasMore": has_more}
    if total is not None:
        body["totalResults"] = total
    return body


def _client_for(po, schedules, invoices, installments=None, supplier=None,
                site=None, fail_on=None):
    return FakeClient({
        "invoiceInstallments": [_page(installments or [])],
        "child/sites": [site if site is not None else SITE_JGA_PROGRESS_US],
        "purchaseOrderSchedules": [_page(schedules, total=len(schedules))],
        "purchaseOrders": [_page([po], total=1)],
        "invoices": [_page(invoices, total=len(invoices))],
        "suppliers": [supplier if supplier is not None else SUPPLIER_JGA],
    }, fail_on=fail_on)


# --------------------------------------------------------------------------
# PURE — helpers
# --------------------------------------------------------------------------

def test_num_treats_null_as_zero():
    # BilledAmount is null, not 0, on unbilled rows. Summing must not raise.
    assert _num(None) == 0.0
    assert _num("") == 0.0
    assert _num(119) == 119.0
    assert _num(830.01) == 830.01


def test_is_complete_zero_expected_counts_as_complete():
    # Without this a zero-amount PO reports "not received" forever.
    assert _is_complete(0.0, 0.0) is True
    assert _is_complete(0.0, 100.0) is False
    assert _is_complete(100.0, 100.0) is True


def test_is_complete_honours_tolerance():
    # Guards float noise from the received division, not real gaps.
    assert _is_complete(99.995, 100.0) is True
    assert _is_complete(99.0, 100.0) is False


def test_parse_date_handles_both_pod_formats():
    # The pod mixes plain dates with offset-aware timestamps.
    assert _parse_date("2014-01-15") == date(2014, 1, 15)
    assert _parse_date("2013-12-16T22:16:47.001+00:00") == date(2013, 12, 16)
    assert _parse_date(None) is None
    assert _parse_date("not a date") is None


# --------------------------------------------------------------------------
# PURE — schedule arithmetic (the derivation)
# --------------------------------------------------------------------------

def test_summarise_schedules_derives_received_from_quantity():
    # ReceivedAmount is 0 on every row on this pod; the amount is derived.
    # 1116 * 1/4 = 279, plus 119 * 1/1 = 119  ->  398.00
    ordered, received, invoiced, undivisible = _summarise_schedules(
        SCHEDULES_701337
    )
    assert ordered == pytest.approx(1235.0)
    assert received == pytest.approx(398.0)
    assert invoiced == pytest.approx(398.0)
    assert undivisible == []


def test_summarise_schedules_matches_oracles_own_billed_amount():
    # The cross-check that validates the derivation: Oracle's BilledAmount
    # for line 1 is 279, exactly 1116 * 1/4.
    line_one = [SCHEDULES_701337[1]]
    _, received, invoiced, _ = _summarise_schedules(line_one)
    assert received == pytest.approx(279.0)
    assert received == pytest.approx(invoiced)


def test_summarise_schedules_flags_lines_it_cannot_prorate():
    rows = [{"LineNumber": 7, "Quantity": 0, "Amount": 500,
             "ReceivedQuantity": 3, "BilledAmount": None}]
    ordered, received, invoiced, undivisible = _summarise_schedules(rows)
    assert ordered == 500.0
    assert received == 0.0
    assert invoiced == 0.0
    assert undivisible == [7]


def test_summarise_schedules_empty_is_all_zero():
    assert _summarise_schedules([]) == (0.0, 0.0, 0.0, [])


# --------------------------------------------------------------------------
# PURE — per-schedule detail
# --------------------------------------------------------------------------

def test_schedule_rows_name_the_short_line():
    # The aggregates cannot answer "why is this still open". Prompt A.7
    # needs to say WHICH line is short, not that the total is.
    rows = _schedule_rows(SCHEDULES_701337)
    assert len(rows) == 2

    by_line = {row["line_number"]: row for row in rows}
    assert by_line[2]["received_amount"] == 119.0
    assert by_line[2]["outstanding_amount"] == 0.0
    assert by_line[2]["fully_received"] is True

    assert by_line[1]["received_amount"] == 279.0
    assert by_line[1]["outstanding_amount"] == 837.0
    assert by_line[1]["fully_received"] is False
    assert by_line[1]["status"] == "Open"


def test_schedule_rows_sum_to_the_aggregates():
    # The per-row derivation and the aggregate derivation must not drift.
    rows = _schedule_rows(SCHEDULES_701337)
    ordered, received, _, _ = _summarise_schedules(SCHEDULES_701337)
    assert sum(r["amount"] for r in rows) == pytest.approx(ordered)
    assert sum(r["received_amount"] for r in rows) == pytest.approx(received)


def test_schedule_rows_survive_zero_quantity():
    rows = _schedule_rows([{"LineNumber": 7, "Quantity": 0, "Amount": 500,
                            "ReceivedQuantity": 3, "BilledAmount": None}])
    assert rows[0]["received_amount"] == 0.0
    assert rows[0]["outstanding_amount"] == 500.0


# --------------------------------------------------------------------------
# PURE — invoice arithmetic
# --------------------------------------------------------------------------

def test_summarise_invoices_uses_amount_paid_not_paid_status():
    # THE REGRESSION THIS PREVENTS: summing InvoiceAmount gated on
    # PaidStatus == "Paid" makes a partly paid invoice contribute ZERO,
    # so the `partial` state can never fire from real data.
    invoices = [{"InvoiceAmount": 1000, "AmountPaid": 400,
                 "PaidStatus": "Partially Paid", "CanceledFlag": False}]
    paid, matched, unpaid, canceled, live = _summarise_invoices(invoices)
    assert paid == 400.0
    assert matched == 1000.0
    assert unpaid == 1
    assert canceled == 0
    assert len(live) == 1


def test_summarise_invoices_excludes_cancelled_from_totals():
    # Counting a cancelled invoice inflates what appears to be owed.
    invoices = [
        {"InvoiceAmount": 500, "AmountPaid": 500, "CanceledFlag": False},
        {"InvoiceAmount": 999, "AmountPaid": 0, "CanceledFlag": True},
    ]
    paid, matched, unpaid, canceled, live = _summarise_invoices(invoices)
    assert paid == 500.0
    assert matched == 500.0
    assert unpaid == 0
    assert canceled == 1
    assert len(live) == 1


def test_summarise_invoices_real_162034_row():
    paid, matched, unpaid, canceled, live = _summarise_invoices(
        [INVOICE_162034]
    )
    assert paid == pytest.approx(830.01)
    assert matched == pytest.approx(830.01)
    assert unpaid == 0
    assert canceled == 0


def test_summarise_invoices_null_amount_paid_reads_as_zero():
    invoices = [{"InvoiceAmount": 200, "AmountPaid": None,
                 "CanceledFlag": False}]
    paid, matched, unpaid, _, _ = _summarise_invoices(invoices)
    assert paid == 0.0
    assert matched == 200.0
    assert unpaid == 1


# --------------------------------------------------------------------------
# PURE — the paid leg
# --------------------------------------------------------------------------

def test_paid_leg_unknown_when_billing_exists_but_no_invoice_matched():
    # PO 701337: schedules bill 398.00, no invoice carries the PO number.
    state, fully_paid, remaining = _classify_paid_leg(398.0, 0, 0.0, 0.0)
    assert state == PAID_STATE_UNKNOWN
    assert fully_paid is None
    assert remaining is None


def test_paid_leg_unknown_gate_beats_the_arithmetic():
    # THE REGRESSION THIS PREVENTS: falling through to the comparison with
    # no matched invoices computes 0 paid of 0 billed and concludes
    # "settled" — reporting fully_paid True where nothing was paid.
    state, fully_paid, _ = _classify_paid_leg(398.0, 0, 0.0, 0.0)
    assert state != PAID_STATE_PAID
    assert fully_paid is not True


def test_paid_leg_nothing_due_when_no_billing_anywhere():
    state, fully_paid, remaining = _classify_paid_leg(0.0, 0, 0.0, 0.0)
    assert state == PAID_STATE_NOTHING_DUE
    assert fully_paid is True
    assert remaining == 0.0


def test_paid_leg_paid_when_settled():
    # PO 162034: 830.01 matched, 830.01 paid.
    state, fully_paid, remaining = _classify_paid_leg(758.0, 1, 830.01, 830.01)
    assert state == PAID_STATE_PAID
    assert fully_paid is True
    assert remaining == 0.0


def test_paid_leg_unpaid_when_nothing_paid():
    state, fully_paid, remaining = _classify_paid_leg(1000.0, 1, 1000.0, 0.0)
    assert state == PAID_STATE_UNPAID
    assert fully_paid is False
    assert remaining == 1000.0


def test_paid_leg_partial_when_part_paid():
    state, fully_paid, remaining = _classify_paid_leg(1000.0, 1, 1000.0, 400.0)
    assert state == PAID_STATE_PARTIAL
    assert fully_paid is False
    assert remaining == 600.0


def test_paid_leg_measures_against_ap_not_schedules():
    # remaining_to_pay compares paid to matched_invoice_total. Mixing
    # sources (AP payments vs PO schedule amounts) was the root of the
    # 398.00 assertion on 701337.
    _, _, remaining = _classify_paid_leg(758.0, 1, 830.01, 400.0)
    assert remaining == pytest.approx(430.01)


@pytest.mark.parametrize("args", [
    (398.0, 0, 0.0, 0.0),
    (0.0, 0, 0.0, 0.0),
    (758.0, 1, 830.01, 830.01),
    (1000.0, 1, 1000.0, 0.0),
    (1000.0, 1, 1000.0, 400.0),
])
def test_paid_leg_only_ever_returns_a_known_state(args):
    state, _, _ = _classify_paid_leg(*args)
    assert state in PAID_STATES


# --------------------------------------------------------------------------
# THE CONTRACT INVARIANT
# --------------------------------------------------------------------------

@pytest.mark.parametrize("schedule_invoiced,count,matched,paid", [
    (398.0, 0, 0.0, 0.0),
    (1.0, 0, 0.0, 0.0),
    (999999.0, 0, 0.0, 0.0),
])
def test_unknown_state_never_asserts_a_number(
    schedule_invoiced, count, matched, paid
):
    """paid_state 'unknown' implies BOTH tri-state fields are None.

    JSON has no tri-state bool: None serializes to null and
    `if fully_paid:` reads null as False. If either field is ever coerced
    to 0.0 or False here, the tool goes back to asserting a debt it cannot
    see — which is what `remaining_to_pay: 398.00` on PO 701337 was.
    """
    state, fully_paid, remaining = _classify_paid_leg(
        schedule_invoiced, count, matched, paid
    )
    assert state == PAID_STATE_UNKNOWN
    assert fully_paid is None, "fully_paid must be None, not False or 0"
    assert remaining is None, "remaining_to_pay must be None, not 0.0"


def test_none_fully_paid_only_ever_accompanies_unknown():
    """The inverse: no other state may produce a None bool."""
    for args in [(0.0, 0, 0.0, 0.0), (758.0, 1, 830.01, 830.01),
                 (1000.0, 1, 1000.0, 0.0), (1000.0, 1, 1000.0, 400.0)]:
        state, fully_paid, remaining = _classify_paid_leg(*args)
        assert state != PAID_STATE_UNKNOWN
        assert fully_paid is not None
        assert remaining is not None


# --------------------------------------------------------------------------
# PURE — installments (holds, due dates, the cross-check)
# --------------------------------------------------------------------------

def test_installments_extract_holds():
    # Holds are NOT on the invoice header and there is no `holds` child —
    # invoiceInstallments is the only place they live on this pod.
    rows = [{"InstallmentNumber": 1, "UnpaidAmount": 600,
             "DueDate": "2014-02-01", "HoldFlag": True, "HoldType": "Price",
             "HoldReason": "Price variance", "HeldBy": "CALVIN.ROTH",
             "HoldDate": "2014-01-20"}]
    holds, due, unpaid, overdue = _summarise_installments(
        [({"InvoiceNumber": "INV-A"}, rows)], today=date(2026, 7, 29)
    )
    assert len(holds) == 1
    assert holds[0]["invoice_number"] == "INV-A"
    assert holds[0]["hold_type"] == "Price"
    assert holds[0]["held_by"] == "CALVIN.ROTH"
    assert holds[0]["amount_held"] == 600.0
    assert due == "2014-02-01"
    assert unpaid == 600.0
    assert overdue == (date(2026, 7, 29) - date(2014, 2, 1)).days


def test_installments_no_overdue_when_nothing_unpaid():
    # The demo data is ~12 years old. An unconditional age would label
    # every settled invoice tens of thousands of days overdue.
    holds, due, unpaid, overdue = _summarise_installments(
        [({"InvoiceNumber": "162034inv"}, [INSTALLMENT_162034])],
        today=date(2026, 7, 29),
    )
    assert holds == []
    assert due == "2014-01-15"
    assert unpaid == 0.0
    assert overdue is None, "a settled invoice is not overdue"


def test_installments_earliest_due_across_invoices():
    rows_a = [{"InstallmentNumber": 1, "UnpaidAmount": 0,
               "DueDate": "2015-06-01", "HoldFlag": False}]
    rows_b = [{"InstallmentNumber": 1, "UnpaidAmount": 0,
               "DueDate": "2014-03-01", "HoldFlag": False}]
    _, due, _, _ = _summarise_installments(
        [({"InvoiceNumber": "A"}, rows_a), ({"InvoiceNumber": "B"}, rows_b)],
        today=date(2026, 7, 29),
    )
    assert due == "2014-03-01"


def test_installments_empty_is_safe():
    holds, due, unpaid, overdue = _summarise_installments([])
    assert holds == []
    assert due is None
    assert unpaid == 0.0
    assert overdue is None


# --------------------------------------------------------------------------
# PURE — supplier and site setup
# --------------------------------------------------------------------------

def test_setup_flattens_real_jga_records():
    setup, blockers = _summarise_setup(SUPPLIER_JGA, SITE_JGA_PROGRESS_US)
    assert setup["supplier_number"] == "1254"
    assert setup["supplier_status"] == "ACTIVE"
    assert setup["spend_authorized"] is True
    assert setup["site_status"] == "ACTIVE"
    assert setup["match_approval_level"] == "3 Way"
    assert setup["invoice_match_option"] == "Receipt"
    assert setup["site_payment_terms"] == "2/10 Net 30"
    assert setup["withholding_tax"] is True
    assert blockers == []


def test_setup_missing_records_are_none_not_active():
    """An unread supplier must never read as a clean bill of health.

    Defaulting absent setup to ACTIVE turns a failed fetch into a positive
    assertion — the same class of defect as reporting a debt on a PO whose
    invoice cannot be found.
    """
    setup, blockers = _summarise_setup(None, None)
    assert setup["supplier_status"] is None
    assert setup["site_status"] is None
    assert setup["spend_authorized"] is None
    assert setup["supplier_read"] is False
    assert setup["site_read"] is False
    assert blockers == [], "unknown setup is not a blocker; it is unknown"


def test_setup_flags_sanctioned_supplier():
    # Outranks every other signal in the tool: a sanctioned supplier is
    # not a process problem, it is a stop-work condition.
    setup, blockers = _summarise_setup(
        dict(SUPPLIER_JGA, OnOFACListFlag=True), SITE_JGA_PROGRESS_US
    )
    assert setup["on_ofac_list"] is True
    assert any("OFAC" in b for b in blockers)


def test_setup_flags_inactive_supplier_and_site():
    setup, blockers = _summarise_setup(
        dict(SUPPLIER_JGA, Status="INACTIVE"),
        dict(SITE_JGA_PROGRESS_US, Status="INACTIVE"),
    )
    assert any("supplier status is INACTIVE" in b for b in blockers)
    assert any("site status is INACTIVE" in b for b in blockers)


def test_setup_flags_not_spend_authorized():
    _, blockers = _summarise_setup(
        dict(SUPPLIER_JGA, BusinessRelationshipCode="PROSPECTIVE",
             BusinessRelationship="Prospective"),
        SITE_JGA_PROGRESS_US,
    )
    assert any("not spend authorized" in b for b in blockers)


def test_setup_flags_site_holds():
    _, blockers = _summarise_setup(SUPPLIER_JGA, dict(
        SITE_JGA_PROGRESS_US,
        HoldAllNewPurchasingDocumentsFlag=True,
        PurchasingHoldReason="Under review",
        HoldAllInvoicesFlag=True,
        PaymentHoldDate="2020-01-01",
        PaymentHoldReason="Dispute",
    ))
    assert any("purchasing documents" in b for b in blockers)
    assert any("holds all invoices" in b for b in blockers)
    assert any("payment hold" in b and "Dispute" in b for b in blockers)


def test_setup_flags_site_not_pay_enabled():
    _, blockers = _summarise_setup(
        SUPPLIER_JGA, dict(SITE_JGA_PROGRESS_US, SitePurposePayFlag=False)
    )
    assert any("not enabled for payment" in b for b in blockers)


# --------------------------------------------------------------------------
# PURE — risk (prompt A.10)
# --------------------------------------------------------------------------

def test_risk_low_only_when_everything_reconciles():
    risk, reasons = _assess_risk([], 0, None, False, PAID_STATE_PAID,
                                 True, True, False, False)
    assert risk == RISK_LOW
    assert reasons, "even Low must say why"


def test_risk_high_on_setup_blocker():
    # A sanctioned or held supplier blocks everything downstream.
    risk, reasons = _assess_risk(
        ["supplier is flagged on the OFAC sanctions list"], 0, None, False,
        PAID_STATE_PAID, True, True, False, False,
    )
    assert risk == RISK_HIGH
    assert any("OFAC" in r for r in reasons)


def test_risk_high_on_invoice_hold():
    risk, _ = _assess_risk([], 1, None, False, PAID_STATE_PARTIAL,
                           True, True, False, False)
    assert risk == RISK_HIGH


def test_risk_high_on_overdue_balance():
    risk, reasons = _assess_risk([], 0, 45, False, PAID_STATE_UNPAID,
                                 True, True, False, False)
    assert risk == RISK_HIGH
    assert any("past due" in r for r in reasons)


def test_risk_high_on_truncation():
    """Truncation is High because the ANSWER may be wrong, not the PO.

    Every other High is a business condition. This one says the tool could
    not see everything it needed, which is the most dangerous state of all
    — it is the only one that can make a confident number false.
    """
    risk, reasons = _assess_risk([], 0, None, True, PAID_STATE_PAID,
                                 True, True, False, False)
    assert risk == RISK_HIGH
    assert any("lower bound" in r for r in reasons)


def test_risk_medium_when_paid_leg_unknown():
    risk, reasons = _assess_risk([], 0, None, False, PAID_STATE_UNKNOWN,
                                 True, True, False, False)
    assert risk == RISK_MEDIUM
    assert any("cannot be determined" in r for r in reasons)


def test_risk_medium_on_amount_disagreement():
    # PO 162034: settled and closed, but 830.01 invoiced against 758.00
    # billed. A summary must not wave that through as Low.
    risk, reasons = _assess_risk([], 0, None, False, PAID_STATE_PAID,
                                 True, True, True, False)
    assert risk == RISK_MEDIUM
    assert any("disagree" in r for r in reasons)


def test_risk_medium_on_terms_override():
    # PO 701337: Net 30 against a site default of 2/10 Net 30.
    risk, reasons = _assess_risk([], 0, None, False, PAID_STATE_PAID,
                                 True, True, False, True)
    assert risk == RISK_MEDIUM
    assert any("terms" in r for r in reasons)


def test_risk_high_outranks_medium():
    # Both sets of conditions present; High must win and lead with it.
    risk, reasons = _assess_risk(
        ["supplier status is INACTIVE"], 2, 900, True, PAID_STATE_UNKNOWN,
        False, False, True, True,
    )
    assert risk == RISK_HIGH
    assert "INACTIVE" in reasons[0]


@pytest.mark.parametrize("blockers,holds,overdue,truncated,state", [
    ([], 0, None, False, PAID_STATE_PAID),
    ([], 0, None, False, PAID_STATE_UNKNOWN),
    (["x"], 0, None, False, PAID_STATE_PAID),
    ([], 3, 10, True, PAID_STATE_PARTIAL),
])
def test_risk_is_always_a_known_level_with_reasons(
    blockers, holds, overdue, truncated, state
):
    risk, reasons = _assess_risk(blockers, holds, overdue, truncated, state,
                                 True, True, False, False)
    assert risk in RISK_LEVELS
    assert reasons, "a rating without a reason is an opinion"


# --------------------------------------------------------------------------
# PURE — recommended action (prompt A.10)
# --------------------------------------------------------------------------

def test_action_setup_blocker_outranks_everything():
    action = _recommend_action(
        ["supplier is flagged on the OFAC sanctions list"], 3,
        PAID_STATE_UNPAID, False, False, 500.0, 500.0, True, "USD",
    )
    assert "OFAC" in action


def test_action_hold_outranks_payment():
    action = _recommend_action([], 1, PAID_STATE_PARTIAL, True, True,
                               0.0, 600.0, False, "USD")
    assert "release" in action.lower()


def test_action_unknown_paid_leg_sends_ap_to_find_the_invoice():
    # Prompt A.7's answer for PO 701337.
    action = _recommend_action([], 0, PAID_STATE_UNKNOWN, False, False,
                               837.0, None, False, "USD")
    assert "Accounts Payable" in action
    assert "locate" in action.lower()


def test_action_names_the_outstanding_receipt_amount():
    action = _recommend_action([], 0, PAID_STATE_NOTHING_DUE, False, True,
                               837.0, 0.0, False, "USD")
    assert "837.00" in action
    assert "USD" in action


def test_action_survives_none_remaining_to_pay():
    # remaining_to_pay is None in the unknown state; formatting must not
    # raise, and must not print "None" as an amount.
    action = _recommend_action([], 0, PAID_STATE_UNKNOWN, True, True,
                               0.0, None, False, "USD")
    assert "None" not in action


def test_action_none_when_complete_and_reconciled():
    action = _recommend_action([], 0, PAID_STATE_PAID, True, True,
                               0.0, 0.0, False, "USD")
    assert action.startswith("None")


def test_action_asks_for_review_on_unexplained_variance():
    action = _recommend_action([], 0, PAID_STATE_PAID, True, True,
                               0.0, 0.0, True, "USD")
    assert "confirm" in action.lower()


# --------------------------------------------------------------------------
# PURE — stage and responsible team
# --------------------------------------------------------------------------

def test_stage_earliest_incomplete_leg_wins():
    assert _lifecycle_stage(False, False, PAID_STATE_UNKNOWN) == \
        "Awaiting receipt"
    assert _lifecycle_stage(True, False, PAID_STATE_UNKNOWN) == \
        "Awaiting invoicing"


def test_stage_names_the_break_instead_of_asserting_payment_due():
    # A tri-state bool arriving as None would take a `not fully_paid`
    # branch and report "Awaiting payment" — asserting a payment is due
    # when the tool has just established it cannot tell.
    stage = _lifecycle_stage(True, True, PAID_STATE_UNKNOWN)
    assert "unknown" in stage.lower()
    assert stage != "Awaiting payment"


def test_stage_complete_when_all_three_legs_done():
    assert _lifecycle_stage(True, True, PAID_STATE_PAID) == "Complete"
    assert _lifecycle_stage(True, True, PAID_STATE_NOTHING_DUE) == "Complete"


def test_stage_hold_overrides_only_the_payment_branch():
    assert _lifecycle_stage(True, True, PAID_STATE_UNPAID, 1) == \
        "Invoice on hold"
    assert _lifecycle_stage(True, True, PAID_STATE_UNPAID, 0) == \
        "Awaiting payment"
    # A hold on a PO still awaiting receipt is real, but is not what the
    # order is waiting on.
    assert _lifecycle_stage(False, True, PAID_STATE_UNPAID, 1) == \
        "Awaiting receipt"


def test_unknown_payment_is_owned_by_ap_not_payments():
    # THE REGRESSION THIS PREVENTS: Payments cannot act on an invoice that
    # does not exist. The missing document is AP's to find. Prompt A.7's
    # literal answer is this field.
    team = _responsible_team(True, True, PAID_STATE_UNKNOWN)
    assert "Payable" in team
    assert team != "Payments"


def test_team_tracks_the_stage():
    assert _responsible_team(False, False, PAID_STATE_UNKNOWN) == \
        "Supplier / Receiving"
    assert _responsible_team(True, False, PAID_STATE_UNKNOWN) == \
        "Accounts Payable"
    assert _responsible_team(True, True, PAID_STATE_UNPAID) == "Payments"
    assert "hold" in _responsible_team(True, True, PAID_STATE_UNPAID, 1).lower()
    assert _responsible_team(True, True, PAID_STATE_PAID) == \
        "None — no action outstanding"


def test_complete_but_unreconciled_po_still_has_an_owner():
    """A finding nobody owns is a finding nobody closes.

    THE REGRESSION THIS PREVENTS: PO 162034 reported "None — no action
    outstanding" as its responsible team while simultaneously recommending
    that AP confirm a 72.01 difference. Printed together, that is a
    contradiction the reader has to resolve.
    """
    assert _responsible_team(True, True, PAID_STATE_PAID, 0, True) == \
        "Accounts Payable — review the unexplained difference"
    assert _responsible_team(True, True, PAID_STATE_PAID, 0, False) == \
        "None — no action outstanding"


def test_open_findings_do_not_override_an_incomplete_leg():
    # The earliest incomplete leg still names the owner; a retrospective
    # finding is not what the order is waiting on.
    assert _responsible_team(False, False, PAID_STATE_UNKNOWN, 0, True) == \
        "Supplier / Receiving"


# --------------------------------------------------------------------------
# Paging tests moved to tests/test_pagination.py on 2026-08-04.
#
# They tested this module's private _page_all, which is now the shared
# tools/pagination.page_all used by four tools. The tests were never
# about lifecycle reconciliation; leaving them here would have meant
# one tool's test file owning behaviour every tool depends on.
#
# They also caught the removal: deleting _page_all broke this file's
# import immediately, which is what "enumerate every caller" is for —
# tests/ as well as src/.
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# FAKE — the whole tool
# --------------------------------------------------------------------------

async def test_missing_po_reports_not_found_without_crashing():
    client = FakeClient({"purchaseOrders": [_page([], total=0)]})
    result = await get_purchase_order_lifecycle_status(client, "999999")
    assert result["found"] is False
    assert result["order_number"] == "999999"
    assert result["notes"]


async def test_701337_end_to_end_reports_unknown_not_a_debt():
    client = _client_for(PO_701337, SCHEDULES_701337, [])
    result = await get_purchase_order_lifecycle_status(client, "701337")

    assert result["ordered"] == 1235.0
    assert result["received"] == 398.0
    assert result["received_is_derived"] is True
    assert result["invoiced"] == 398.0
    assert result["paid"] == 0.0

    assert result["paid_state"] == PAID_STATE_UNKNOWN
    assert result["fully_paid"] is None
    assert result["remaining_to_pay"] is None

    assert result["lifecycle_stage"] == "Awaiting receipt"
    assert result["responsible_team"] == "Supplier / Receiving"
    assert any("unknown rather than zero" in n for n in result["notes"])


async def test_701337_notes_the_unconfirmed_self_billing_hypothesis():
    # PayOnReceiptFlag MAY explain the unmatched billing. It is offered as
    # a hypothesis and labelled unconfirmed — never stated as the cause.
    client = _client_for(PO_701337, SCHEDULES_701337, [])
    result = await get_purchase_order_lifecycle_status(client, "701337")
    hypothesis = [n for n in result["notes"] if "PayOnReceipt" in n]
    assert len(hypothesis) == 1
    assert "unconfirmed" in hypothesis[0]


async def test_701337_carries_setup_risk_and_action():
    client = _client_for(PO_701337, SCHEDULES_701337, [])
    result = await get_purchase_order_lifecycle_status(client, "701337")

    assert result["setup"]["supplier_status"] == "ACTIVE"
    assert result["setup"]["match_approval_level"] == "3 Way"
    assert result["risk"] == RISK_MEDIUM
    assert result["risk_reasons"]
    assert "Accounts Payable" in result["recommended_action"]


async def test_701337_detects_the_terms_override():
    # PO says Net 30; the JGA Progress US site default is 2/10 Net 30.
    # Not an error — a documented difference prompt A.2 asks about.
    client = _client_for(PO_701337, SCHEDULES_701337, [])
    result = await get_purchase_order_lifecycle_status(client, "701337")
    assert result["payment_terms_overridden"] is True
    assert any("differ from the supplier site" in n for n in result["notes"])


async def test_701337_schedule_rows_identify_the_open_line():
    client = _client_for(PO_701337, SCHEDULES_701337, [])
    result = await get_purchase_order_lifecycle_status(client, "701337")
    open_rows = [r for r in result["schedules"] if not r["fully_received"]]
    assert len(open_rows) == 1
    assert open_rows[0]["line_number"] == 1
    assert open_rows[0]["outstanding_amount"] == 837.0


async def test_162034_end_to_end_is_complete_and_settled():
    client = _client_for(PO_162034, SCHEDULES_162034, [INVOICE_162034],
                         [INSTALLMENT_162034], supplier=SUPPLIER_LEE,
                         site=SITE_LEE)
    result = await get_purchase_order_lifecycle_status(client, "162034")

    assert result["fully_received"] is True
    assert result["fully_invoiced"] is True
    assert result["fully_paid"] is True
    assert result["paid_state"] == PAID_STATE_PAID
    assert result["remaining_to_pay"] == 0.0
    assert result["lifecycle_stage"] == "Complete"
    assert result["earliest_due_date"] == "2014-01-15"
    assert result["days_overdue"] is None
    assert result["payment_terms_overridden"] is False


async def test_162034_reports_over_invoicing_without_diagnosing_it():
    # 830.01 invoiced against 758.00 ordered. Over-invoicing is not an
    # error — tax, freight and price variance all do this legitimately.
    # The PO header reports TotalTax 0, so PO-side tax does NOT explain
    # it, and the tool must not claim a cause.
    client = _client_for(PO_162034, SCHEDULES_162034, [INVOICE_162034],
                         [INSTALLMENT_162034], supplier=SUPPLIER_LEE,
                         site=SITE_LEE)
    result = await get_purchase_order_lifecycle_status(client, "162034")
    difference = [n for n in result["notes"] if "72.01" in n]
    assert len(difference) == 1
    assert "tax" not in difference[0].lower()


async def test_162034_is_medium_risk_despite_being_complete():
    # A settled, closed PO carrying an unexplained 72.01 is exactly what a
    # summary must not wave through.
    client = _client_for(PO_162034, SCHEDULES_162034, [INVOICE_162034],
                         [INSTALLMENT_162034], supplier=SUPPLIER_LEE,
                         site=SITE_LEE)
    result = await get_purchase_order_lifecycle_status(client, "162034")
    assert result["risk"] == RISK_MEDIUM
    assert any("disagree" in r for r in result["risk_reasons"])


async def test_162034_owner_and_action_do_not_contradict():
    # The PO is complete, but 72.01 is unexplained. Reporting no owner
    # beside an AP recommendation left the reader to reconcile the two.
    client = _client_for(PO_162034, SCHEDULES_162034, [INVOICE_162034],
                         [INSTALLMENT_162034], supplier=SUPPLIER_LEE,
                         site=SITE_LEE)
    result = await get_purchase_order_lifecycle_status(client, "162034")

    assert result["lifecycle_stage"] == "Complete"
    assert "Payable" in result["responsible_team"]
    assert "Accounts Payable" in result["recommended_action"]
    assert not result["responsible_team"].startswith("None")


async def test_setup_is_fetched_once_each_by_id():
    client = _client_for(PO_701337, SCHEDULES_701337, [])
    await get_purchase_order_lifecycle_status(client, "701337")
    assert client.paths_called("child/sites") == 1
    supplier_calls = [
        p for p, _ in client.calls
        if "/suppliers/" in p and "child" not in p
    ]
    assert len(supplier_calls) == 1
    assert "300000047414635" in supplier_calls[0], "fetched by SupplierId"


async def test_supplier_fetch_failure_degrades_to_a_note():
    # Setup is context, not money. A failure must degrade the answer, not
    # invalidate it — and must never be silent.
    client = _client_for(PO_701337, SCHEDULES_701337, [],
                         fail_on="/suppliers/")
    result = await get_purchase_order_lifecycle_status(client, "701337")

    assert result["found"] is True
    assert result["ordered"] == 1235.0, "amounts are unaffected"
    assert result["setup"]["supplier_status"] is None
    assert result["setup"]["supplier_read"] is False
    assert any("could not be read" in n for n in result["notes"])


async def test_installments_are_fetched_once_per_live_invoice():
    client = _client_for(PO_162034, SCHEDULES_162034, [INVOICE_162034],
                         [INSTALLMENT_162034], supplier=SUPPLIER_LEE,
                         site=SITE_LEE)
    await get_purchase_order_lifecycle_status(client, "162034")
    assert client.paths_called("invoiceInstallments") == 1


async def test_cancelled_invoices_are_excluded_and_not_fetched():
    cancelled = dict(INVOICE_162034, InvoiceId=99, InvoiceNumber="DEAD",
                     CanceledFlag=True, InvoiceAmount=5000, AmountPaid=0)
    client = _client_for(PO_162034, SCHEDULES_162034,
                         [INVOICE_162034, cancelled], [INSTALLMENT_162034],
                         supplier=SUPPLIER_LEE, site=SITE_LEE)
    result = await get_purchase_order_lifecycle_status(client, "162034")

    assert result["matched_invoice_total"] == pytest.approx(830.01)
    assert result["canceled_invoice_count"] == 1
    assert result["invoice_count"] == 1
    assert client.paths_called("invoiceInstallments") == 1
    assert any("cancelled" in n for n in result["notes"])


async def test_installment_failure_degrades_to_a_note():
    client = _client_for(PO_162034, SCHEDULES_162034, [INVOICE_162034],
                         [INSTALLMENT_162034], supplier=SUPPLIER_LEE,
                         site=SITE_LEE, fail_on="invoiceInstallments")
    result = await get_purchase_order_lifecycle_status(client, "162034")

    assert result["found"] is True
    assert result["paid"] == pytest.approx(830.01), "money is unaffected"
    assert result["hold_count"] == 0
    assert any("could not be read" in n for n in result["notes"])


async def test_installment_fanout_is_capped(monkeypatch):
    monkeypatch.setattr(mod, "MAX_INSTALLMENT_INVOICES", 2)
    invoices = [
        dict(INVOICE_162034, InvoiceId=i, InvoiceNumber=f"INV-{i}",
             InvoiceAmount=10, AmountPaid=10)
        for i in range(5)
    ]
    client = _client_for(PO_162034, SCHEDULES_162034, invoices,
                         [INSTALLMENT_162034], supplier=SUPPLIER_LEE,
                         site=SITE_LEE)
    result = await get_purchase_order_lifecycle_status(client, "162034")

    assert client.paths_called("invoiceInstallments") == 2
    assert result["installments_capped"] is True
    assert result["invoice_count"] == 5, "the cap must not shrink the count"
    assert result["paid"] == pytest.approx(50.0), "money is uncapped"
    assert any("amounts are unaffected" in n for n in result["notes"])


async def test_header_ordered_disagreement_is_reported_not_resolved():
    po = dict(PO_701337, Ordered=9999)
    client = _client_for(po, SCHEDULES_701337, [])
    result = await get_purchase_order_lifecycle_status(client, "701337")
    assert any("disagrees" in n for n in result["notes"])
    assert result["ordered"] == 9999.0, "the header stays authoritative"


async def test_sanctioned_supplier_drives_high_risk_end_to_end():
    client = _client_for(
        PO_162034, SCHEDULES_162034, [INVOICE_162034], [INSTALLMENT_162034],
        supplier=dict(SUPPLIER_LEE, OnOFACListFlag=True), site=SITE_LEE,
    )
    result = await get_purchase_order_lifecycle_status(client, "162034")

    assert result["risk"] == RISK_HIGH
    assert any("OFAC" in b for b in result["setup_blockers"])
    assert "OFAC" in result["recommended_action"]
    assert any("setup:" in n for n in result["notes"])


async def test_site_payment_hold_drives_high_risk_end_to_end():
    held_site = dict(SITE_LEE, PaymentHoldDate="2020-01-01",
                     PaymentHoldReason="Dispute")
    client = _client_for(PO_162034, SCHEDULES_162034, [INVOICE_162034],
                         [INSTALLMENT_162034], supplier=SUPPLIER_LEE,
                         site=held_site)
    result = await get_purchase_order_lifecycle_status(client, "162034")

    assert result["risk"] == RISK_HIGH
    assert any("payment hold" in b for b in result["setup_blockers"])


async def test_partial_payment_with_hold_routes_to_ap():
    # Neither test PO exercises this path: it needs a partly paid invoice
    # on hold. Both are real Fusion states.
    invoice = dict(INVOICE_162034, InvoiceAmount=1000, AmountPaid=400,
                   PaidStatus="Partially Paid")
    installment = {"InstallmentNumber": 1, "UnpaidAmount": 600,
                   "DueDate": "2014-02-01", "HoldFlag": True,
                   "HoldType": "Price", "HoldReason": "Price variance",
                   "HeldBy": "CALVIN.ROTH"}
    po = dict(PO_162034, Ordered=1000)
    schedules = [dict(SCHEDULES_162034[0], Amount=1000, BilledAmount=1000)]

    client = _client_for(po, schedules, [invoice], [installment],
                         supplier=SUPPLIER_LEE, site=SITE_LEE)
    result = await get_purchase_order_lifecycle_status(client, "1")

    assert result["paid_state"] == PAID_STATE_PARTIAL
    assert result["fully_paid"] is False
    assert result["remaining_to_pay"] == 600.0
    assert result["hold_count"] == 1
    assert result["lifecycle_stage"] == "Invoice on hold"
    assert "Payable" in result["responsible_team"]
    assert result["risk"] == RISK_HIGH


async def test_installment_unpaid_disagreement_is_a_note_not_a_source():
    # UnpaidAmount is a CROSS-CHECK only. Installments are capped and
    # headers are not, so money never comes from here.
    invoice = dict(INVOICE_162034, InvoiceAmount=1000, AmountPaid=400)
    installment = {"InstallmentNumber": 1, "UnpaidAmount": 123.45,
                   "DueDate": "2014-02-01", "HoldFlag": False}
    po = dict(PO_162034, Ordered=1000)
    schedules = [dict(SCHEDULES_162034[0], Amount=1000, BilledAmount=1000)]

    client = _client_for(po, schedules, [invoice], [installment],
                         supplier=SUPPLIER_LEE, site=SITE_LEE)
    result = await get_purchase_order_lifecycle_status(client, "1")

    assert result["remaining_to_pay"] == 600.0, "headers win"
    assert any("installments report" in n for n in result["notes"])


async def test_result_shape_is_stable():
    # The KG rows will encode these keys. A rename after that point is a
    # two-place change.
    client = _client_for(PO_162034, SCHEDULES_162034, [INVOICE_162034],
                         [INSTALLMENT_162034], supplier=SUPPLIER_LEE,
                         site=SITE_LEE)
    result = await get_purchase_order_lifecycle_status(client, "162034")

    for key in [
        "shape", "found", "order_number", "supplier", "buyer", "business_unit",
        "setup", "setup_blockers", "payment_terms_overridden",
        "ordered", "received", "received_is_derived", "invoiced", "paid",
        "matched_invoice_total", "remaining_to_receive",
        "remaining_to_invoice", "remaining_to_pay", "fully_received",
        "fully_invoiced", "fully_paid", "paid_state", "lifecycle_stage",
        "responsible_team", "risk", "risk_reasons", "recommended_action",
        "schedules", "holds", "hold_count", "earliest_due_date",
        "days_overdue", "schedule_count", "invoice_count",
        "canceled_invoice_count", "schedule_total_available",
        "invoice_total_available", "installments_capped", "truncated", "notes",
    ]:
        assert key in result, f"missing contract key: {key}"

    assert result["shape"] == "po_lifecycle_status"
    assert result["risk"] in RISK_LEVELS
    assert result["paid_state"] in PAID_STATES
