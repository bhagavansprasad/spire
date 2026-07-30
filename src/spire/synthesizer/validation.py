"""Hallucination guard: the source-data fingerprint and the validators.

Two halves. _collect_valid_ids walks the executor's raw output once and
builds the set of ids every response is allowed to mention — the
fingerprint. Each _validate_* function then checks one response type's
ids against that fingerprint and raises HallucinationError the moment one
doesn't belong. _validate_no_hallucinated_ids is the single dispatch
point synthesize_response calls; everything above it exists to serve
that one call.

Imports every response type it validates, so this module sits above the
schema modules (p2p, ar, aggregation, lifecycle) in the dependency order
and is imported by the orchestrator, never the reverse.
"""

from __future__ import annotations

from pydantic import BaseModel

from spire.synthesizer.constants import LIFECYCLE_SHAPE
from spire.synthesizer.errors import HallucinationError, UnsupportedEntityError
from spire.synthesizer.lifecycle import POLifecycleResponse, _validate_po_lifecycle
from spire.synthesizer.p2p import (
    AddressResponse,
    InvoiceResponse,
    PurchaseOrderResponse,
    SupplierResponse,
)
from spire.synthesizer.ar import (
    CreditMemoListResponse,
    CustomerAccountResponse,
    ReceivablesInvoiceResponse,
    StandardReceiptResponse,
)
from spire.synthesizer.aggregation import (
    ExposureRankingResponse,
    OpenPOSummaryResponse,
    POStatusBreakdownResponse,
    ReceiptMethodDistributionResponse,
    SupplierPOValueRankingResponse,
    SupplierSpendRankingResponse,
)


# ─────────────────────────────────────────────────────────────────────
# Source-data fingerprint (prompt building + validation)
# ─────────────────────────────────────────────────────────────────────


def _is_supplier_spend_ranking(outputs: dict[str, list[dict]]) -> bool:
    """True if the executor output is an aggregation ranking rather than
    an entity list. The aggregation tool returns a single object tagged
    shape='supplier_spend_ranking', which the executor places (wrapped in
    a one-element list) under the 'aggregation' bucket."""
    bucket = outputs.get("aggregation")
    if not bucket:
        return False
    first = bucket[0]
    return isinstance(first, dict) and first.get("shape") == "supplier_spend_ranking"


def _collect_valid_ids(outputs: dict[str, list[dict]]) -> dict[str, set]:
    """Walk the executor outputs and collect the IDs the response is
    allowed to mention. Bucket order doesn't matter — every bucket is
    scanned for every id field."""
    supplier_ids: set = set()
    supplier_numbers: set = set()
    person_ids: set = set()
    invoice_ids: set = set()
    address_ids: set = set()
    # P5b: the PO child hierarchy and supplier contacts.
    po_line_ids: set = set()
    line_location_ids: set = set()
    po_distribution_ids: set = set()
    contact_ids: set = set()
    # AR-P2: receivables invoice + its lines.
    customer_transaction_ids: set = set()
    customer_transaction_line_ids: set = set()
    # AR-P2b: customer account + its transactions (payment schedules).
    customer_account_ids: set = set()
    customer_account_transaction_ids: set = set()
    account_credit_memo_ids: set = set()
    account_receipt_ids: set = set()
    application_ids: set = set()
    standard_receipt_ids: set = set()
    # Module 5: the PO the lifecycle answer is allowed to be about.
    lifecycle_order_numbers: set = set()
    
    for bucket in outputs.values():
        for item in bucket:
            if (sid := item.get("SupplierId")) is not None:
                supplier_ids.add(sid)
            if (snum := item.get("SupplierNumber")) is not None:
                supplier_numbers.add(snum)
            if (pid := item.get("PersonId")) is not None:
                person_ids.add(pid)
            # BuyerId on a PO equals PersonId on a Buyer record.
            if (bid := item.get("BuyerId")) is not None:
                person_ids.add(bid)
            if (iid := item.get("InvoiceId")) is not None:
                invoice_ids.add(iid)
            if (aid := item.get("SupplierAddressId")) is not None:
                address_ids.add(aid)
            # P5b: PO children and supplier contacts.
            if (plid := item.get("POLineId")) is not None:
                po_line_ids.add(plid)
            if (llid := item.get("LineLocationId")) is not None:
                line_location_ids.add(llid)
            if (pdid := item.get("PODistributionId")) is not None:
                po_distribution_ids.add(pdid)
            if (scid := item.get("SupplierContactId")) is not None:
                contact_ids.add(scid)
            # AR-P2: receivables invoice header id and line id.
            if (ctid := item.get("CustomerTransactionId")) is not None:
                customer_transaction_ids.add(ctid)
            if (ctlid := item.get("CustomerTransactionLineId")) is not None:
                customer_transaction_line_ids.add(ctlid)
            # AR-P2b: customer account id and its transaction id (the
            # payment-schedule TransactionId, distinct from the AR-invoice
            # CustomerTransactionId above).
            if (caid := item.get("AccountId")) is not None:
                customer_account_ids.add(caid)
            if (catid := item.get("TransactionId")) is not None:
                customer_account_transaction_ids.add(catid)
            # AR-P5 prompt 7: the account's credit memos. CreditMemoId is
            # its OWN id space — small ints, unrelated to the AR-invoice
            # CustomerTransactionId that AR-P4's top-level CreditMemo uses.
            # Kept in a separate set so a memo id can never validate
            # against the wrong entity's ids.
            if (acmid := item.get("CreditMemoId")) is not None:
                account_credit_memo_ids.add(acmid)
            # AR-P5 prompt 8: the account's receipts. StandardReceiptId is
            # a fifth AR id space, and one that MIXES WIDTHS within a
            # single collection (small ints for backfilled rows, large for
            # recent). Harvested as-is — never normalized, since the raw
            # value is what the validator compares against.
            if (arid := item.get("StandardReceiptId")) is not None:
                account_receipt_ids.add(arid)
            # Prompt 9: receipt applications. ApplicationId is a sixth AR
            # id space.
            if (aid := item.get("ApplicationId")) is not None:
                application_ids.add(aid)
                
            if (srid := item.get("StandardReceiptId")) is not None:
                standard_receipt_ids.add(srid)

            # Module 5: the PO lifecycle record is the one tool output
            # whose keys are snake_case rather than Fusion's PascalCase —
            # its fields are COMPUTED, not passed through, so there is no
            # Fusion name to keep. Every id check above misses it, which
            # is how a legitimate supplier_id from a lifecycle answer was
            # reported as hallucinated. Harvest the snake_case forms too.
            if item.get("shape") == LIFECYCLE_SHAPE:
                if (lsid := item.get("supplier_id")) is not None:
                    supplier_ids.add(lsid)
                if (lsn := item.get("supplier_number")) is not None:
                    supplier_numbers.add(lsn)
                setup = item.get("setup")
                if isinstance(setup, dict):
                    if (ssn := setup.get("supplier_number")) is not None:
                        supplier_numbers.add(ssn)
                if (lon := item.get("order_number")) is not None:
                    lifecycle_order_numbers.add(str(lon))

            if isinstance(item.get("rows"), list):
                for row in item["rows"]:
                    if (rn := row.get("supplier_number")) is not None:
                        supplier_numbers.add(rn)
                    if (rsid := row.get("supplier_id")) is not None:
                        supplier_ids.add(rsid)
                    # --- Add this line ---
                    if (aid := row.get("account_id")) is not None:
                        customer_account_ids.add(aid)
                                    
            # Phase 9: a supplier-rooted query with addresses nests each
            # supplier's addresses under "addresses"; harvest their ids so
            # the nested AddressInfo entries validate.
            if isinstance(item.get("addresses"), list):
                for addr in item["addresses"]:
                    if (na := addr.get("SupplierAddressId")) is not None:
                        address_ids.add(na)
            # Feature 7: an aggregation ranking carries its suppliers
            # nested under "rows", each with a lowercase "supplier_number".
            # P6: the PO-value ranking's rows carry "supplier_id" instead
            # (POs have no supplier number), so harvest both — otherwise
            # every id in a PO ranking looks invented and the guard fires
            # on legitimate data.
            if isinstance(item.get("rows"), list):
                for row in item["rows"]:
                    if (rn := row.get("supplier_number")) is not None:
                        supplier_numbers.add(rn)
                    if (rsid := row.get("supplier_id")) is not None:
                        supplier_ids.add(rsid)

    return {
        "supplier_ids": supplier_ids,
        "supplier_numbers": supplier_numbers,
        "person_ids": person_ids,
        "invoice_ids": invoice_ids,
        "address_ids": address_ids,
        "po_line_ids": po_line_ids,
        "line_location_ids": line_location_ids,
        "po_distribution_ids": po_distribution_ids,
        "contact_ids": contact_ids,
        "customer_transaction_ids": customer_transaction_ids,
        "customer_transaction_line_ids": customer_transaction_line_ids,
        "customer_account_ids": customer_account_ids,
        "customer_account_transaction_ids": customer_account_transaction_ids,
        "account_credit_memo_ids": account_credit_memo_ids,
        "account_receipt_ids": account_receipt_ids,
        "application_ids": application_ids,
        "standard_receipt_ids": standard_receipt_ids,
        "lifecycle_order_numbers": lifecycle_order_numbers,
    }


def _raise_if_bad(parts: list[str]) -> None:
    if parts:
        raise HallucinationError(
            "Synthesizer produced IDs that do not appear in the executor "
            "output: " + "; ".join(parts)
        )


def _validate_supplier(response: SupplierResponse, valid: dict[str, set]) -> None:
    bad_sid: list[int] = []
    bad_snum: list[str] = []
    bad_pid: list[int] = []
    bad_aid: list[int] = []
    bad_cid: list[int] = []
    for s in response.suppliers:
        if s.supplier_id not in valid["supplier_ids"]:
            bad_sid.append(s.supplier_id)
        if s.supplier_number not in valid["supplier_numbers"]:
            bad_snum.append(s.supplier_number)
        for b in s.buyers:
            if b.person_id not in valid["person_ids"]:
                bad_pid.append(b.person_id)
        for a in s.addresses:
            if a.address_id not in valid["address_ids"]:
                bad_aid.append(a.address_id)
        for c in s.contacts:
            if c.supplier_contact_id not in valid["contact_ids"]:
                bad_cid.append(c.supplier_contact_id)
    parts = []
    if bad_sid:
        parts.append(f"supplier_ids={bad_sid}")
    if bad_snum:
        parts.append(f"supplier_numbers={bad_snum}")
    if bad_pid:
        parts.append(f"person_ids={bad_pid}")
    if bad_aid:
        parts.append(f"address_ids={bad_aid}")
    if bad_cid:
        parts.append(f"supplier_contact_ids={bad_cid}")
    _raise_if_bad(parts)


def _validate_invoice(response: InvoiceResponse, valid: dict[str, set]) -> None:
    bad_iid: list[int] = []
    bad_snum: list[str] = []
    for inv in response.invoices:
        if inv.invoice_id not in valid["invoice_ids"]:
            bad_iid.append(inv.invoice_id)
        if inv.supplier_number not in valid["supplier_numbers"]:
            bad_snum.append(inv.supplier_number)
    parts = []
    if bad_iid:
        parts.append(f"invoice_ids={bad_iid}")
    if bad_snum:
        parts.append(f"supplier_numbers={bad_snum}")
    _raise_if_bad(parts)


def _validate_address(response: AddressResponse, valid: dict[str, set]) -> None:
    bad_aid: list[int] = []
    bad_snum: list[str] = []
    for a in response.addresses:
        if a.address_id not in valid["address_ids"]:
            bad_aid.append(a.address_id)
        if a.supplier_number not in valid["supplier_numbers"]:
            bad_snum.append(a.supplier_number)
    parts = []
    if bad_aid:
        parts.append(f"address_ids={bad_aid}")
    if bad_snum:
        parts.append(f"supplier_numbers={bad_snum}")
    _raise_if_bad(parts)


def _validate_purchase_order(
    response: PurchaseOrderResponse, valid: dict[str, set]
) -> None:
    bad_sid: list[int] = []
    bad_pid: list[int] = []
    bad_line: list[int] = []
    bad_sched: list[int] = []
    bad_dist: list[int] = []
    for po in response.purchase_orders:
        if po.supplier_id not in valid["supplier_ids"]:
            bad_sid.append(po.supplier_id)
        if po.buyer is not None and po.buyer.person_id not in valid["person_ids"]:
            bad_pid.append(po.buyer.person_id)
        # P5b: the PO child hierarchy. These fields are exactly where
        # invented detail would surface, so every id is cross-referenced.
        for ln in po.lines:
            if ln.po_line_id not in valid["po_line_ids"]:
                bad_line.append(ln.po_line_id)
        for sch in po.schedules:
            if sch.line_location_id not in valid["line_location_ids"]:
                bad_sched.append(sch.line_location_id)
        for d in po.distributions:
            if d.po_distribution_id not in valid["po_distribution_ids"]:
                bad_dist.append(d.po_distribution_id)
    parts = []
    if bad_sid:
        parts.append(f"supplier_ids={bad_sid}")
    if bad_pid:
        parts.append(f"person_ids={bad_pid}")
    if bad_line:
        parts.append(f"po_line_ids={bad_line}")
    if bad_sched:
        parts.append(f"line_location_ids={bad_sched}")
    if bad_dist:
        parts.append(f"po_distribution_ids={bad_dist}")
    _raise_if_bad(parts)


def _validate_receivables_invoice(
    response: ReceivablesInvoiceResponse, valid: dict[str, set]
) -> None:
    bad_inv: list[int] = []
    bad_line: list[int] = []
    for inv in response.receivables_invoices:
        if inv.customer_transaction_id not in valid["customer_transaction_ids"]:
            bad_inv.append(inv.customer_transaction_id)
        # AR lines are exactly where invented detail would surface, so every
        # id is cross-referenced (mirrors the PO line/schedule/distribution
        # guard above).
        for ln in inv.lines:
            if (
                ln.customer_transaction_line_id
                not in valid["customer_transaction_line_ids"]
            ):
                bad_line.append(ln.customer_transaction_line_id)
            # AR-P3: tax lines nest one level deeper. The tax-line PK is
            # also a CustomerTransactionLineId, so it validates against the
            # same bucket (the harvest collects both from the output).
            for tx in ln.tax_lines:
                if (
                    tx.customer_transaction_line_id
                    not in valid["customer_transaction_line_ids"]
                ):
                    bad_line.append(tx.customer_transaction_line_id)
    parts = []
    if bad_inv:
        parts.append(f"customer_transaction_ids={bad_inv}")
    if bad_line:
        parts.append(f"customer_transaction_line_ids={bad_line}")
    _raise_if_bad(parts)


def _validate_customer_account(
    response: CustomerAccountResponse, valid: dict[str, set]
) -> None:
    bad_acct: list[int] = []
    bad_txn: list[int] = []
    bad_memo: list[int] = []
    bad_receipt: list[int] = []
    bad_apps: list[int] = []
    for acct in response.customer_accounts:
        if acct.account_id not in valid["customer_account_ids"]:
            bad_acct.append(acct.account_id)
        # The account's transactions are where invented detail would
        # surface, so every id is cross-referenced.
        for txn in acct.transactions:
            if (
                txn.transaction_id
                not in valid["customer_account_transaction_ids"]
            ):
                bad_txn.append(txn.transaction_id)
        # AR-P5 prompt 7: same reasoning for the account's credit memos.
        # Checked against account_credit_memo_ids specifically — NOT the
        # customer_transaction_ids that AR-P4's top-level CreditMemo uses,
        # since CreditMemoId is a separate id space and cross-checking
        # against the wrong set would let invented ids pass.
        for memo in acct.credit_memos:
            if memo.credit_memo_id not in valid["account_credit_memo_ids"]:
                bad_memo.append(memo.credit_memo_id)
        # AR-P5 prompt 8: same again for receipts, against their own set.
        # StandardReceiptId is its own id space and mixes widths, so it
        # can neither be checked against another entity's ids nor
        # inferred from magnitude.
        for rcpt in acct.receipts:
            if rcpt.receipt_id not in valid["account_receipt_ids"]:
                bad_receipt.append(rcpt.receipt_id)
        # Prompt 9: receipt applications.
        for app in acct.applications:
            if app.application_id not in valid["application_ids"]:
                bad_apps.append(app.application_id)
    parts = []
    if bad_acct:
        parts.append(f"customer_account_ids={bad_acct}")
    if bad_txn:
        parts.append(f"customer_account_transaction_ids={bad_txn}")
    if bad_memo:
        parts.append(f"account_credit_memo_ids={bad_memo}")
    if bad_receipt:
        parts.append(f"account_receipt_ids={bad_receipt}")
    if bad_apps:
        parts.append(f"application_ids={bad_apps}")
    _raise_if_bad(parts)


def _validate_credit_memo(
    response: CreditMemoListResponse, valid: dict[str, set]
) -> None:
    """Cross-reference each listed credit memo's CustomerTransactionId
    against the executor's data. Credit memos share the id space of AR
    invoices (CustomerTransactionId), harvested into customer_transaction_ids,
    so no separate id set is needed. total_credit is a copied scalar, not an
    id, so there is nothing to cross-check there."""
    bad_cm: list[int] = []
    for cm in response.credit_memos:
        if cm.customer_transaction_id not in valid["customer_transaction_ids"]:
            bad_cm.append(cm.customer_transaction_id)
    parts = []
    if bad_cm:
        parts.append(f"customer_transaction_ids={bad_cm}")
    _raise_if_bad(parts)


def _validate_supplier_spend_ranking(
    response: SupplierSpendRankingResponse, valid: dict[str, set]
) -> None:
    bad_snum: list[str] = []
    for row in response.suppliers:
        if row.supplier_number not in valid["supplier_numbers"]:
            bad_snum.append(row.supplier_number)
    parts = []
    if bad_snum:
        parts.append(f"supplier_numbers={bad_snum}")
    _raise_if_bad(parts)


def _validate_supplier_po_value_ranking(
    response: SupplierPOValueRankingResponse, valid: dict[str, set]
) -> None:
    """Cross-reference the ranking's supplier_ids against the executor's
    data.

    Checks supplier_IDS, not supplier_numbers — purchase orders carry no
    SupplierNumber, which is exactly why this ranking has its own row type
    rather than reusing SupplierSpendRow."""
    bad = [
        r.supplier_id
        for r in response.suppliers
        if r.supplier_id not in valid["supplier_ids"]
    ]
    parts = []
    if bad:
        parts.append(f"supplier_ids={bad}")
    _raise_if_bad(parts)


def _validate_no_ids(response: BaseModel, valid: dict[str, set]) -> None:
    """No-op validator for aggregation shapes that carry no identifiers.

    The status breakdown and the open-PO summary report only counts and
    sums — there is no id in them to invent, so there is nothing to
    cross-reference. Registered explicitly rather than left out: the
    dispatch raises for unregistered response types (fail loud rather
    than skip validation silently), so "nothing to check" must be stated,
    not implied by absence.

    The numbers themselves are not validated here. They cannot be: they
    are computed by the tool, and the prompt tells the LLM to copy them
    exactly. A miscopied total would slip through — the guard against
    that is the instruction plus zero-temperature, not this function."""
    return

def _validate_standard_receipt(
    response: StandardReceiptResponse, valid: dict[str, set]
) -> None:
    bad_ids: list[int] = []
    for rec in response.standard_receipts:
        if rec.standard_receipt_id not in valid["standard_receipt_ids"]:
            bad_ids.append(rec.standard_receipt_id)
    parts = []
    if bad_ids:
        parts.append(f"standard_receipt_ids={bad_ids}")
    if parts:
        raise HallucinationError(
            "Synthesizer produced IDs that do not appear in the executor "
            "output: " + "; ".join(parts)
        )

def _validate_exposure_ranking(
    response: ExposureRankingResponse, valid: dict[str, set]
) -> None:
    bad_ids: list[int] = []
    for row in response.accounts:
        if row.account_id not in valid["customer_account_ids"]:
            bad_ids.append(row.account_id)
    parts = []
    if bad_ids:
        parts.append(f"customer_account_ids={bad_ids}")
    if parts:
        raise HallucinationError(
            "Synthesizer produced IDs that do not appear in the executor "
            "output: " + "; ".join(parts)
        )

def _validate_receipt_method_distribution(
    response: ReceiptMethodDistributionResponse, valid: dict[str, set]
) -> None:
    # No IDs to validate; counts and sums are copied from the data.
    return


_VALIDATORS = {
    SupplierResponse: _validate_supplier,
    InvoiceResponse: _validate_invoice,
    AddressResponse: _validate_address,
    PurchaseOrderResponse: _validate_purchase_order,
    ReceivablesInvoiceResponse: _validate_receivables_invoice,
    CustomerAccountResponse: _validate_customer_account,
    CreditMemoListResponse: _validate_credit_memo,
    SupplierSpendRankingResponse: _validate_supplier_spend_ranking,
    SupplierPOValueRankingResponse: _validate_supplier_po_value_ranking,
    POStatusBreakdownResponse: _validate_no_ids,
    OpenPOSummaryResponse: _validate_no_ids,
    StandardReceiptResponse: _validate_standard_receipt,
    ExposureRankingResponse: _validate_exposure_ranking,
    ReceiptMethodDistributionResponse: _validate_receipt_method_distribution,
    POLifecycleResponse: _validate_po_lifecycle,
}


def _validate_no_hallucinated_ids(
    response: BaseModel, outputs: dict[str, list[dict]]
) -> None:
    """Dispatch to the validator for the response's concrete type.
    An empty record list is always valid."""
    valid = _collect_valid_ids(outputs)
    validator = _VALIDATORS.get(type(response))
    if validator is None:
        # Unknown response type — should never happen given schema
        # selection, but fail loud rather than skip validation silently.
        raise UnsupportedEntityError(
            f"No hallucination validator for response type "
            f"{type(response).__name__}."
        )
    validator(response, valid)
