"""P2P (procure-to-pay) response schemas.

Supplier, Invoice and PurchaseOrder are the three target entities with a
direct entity-level fetcher on the procurement side, plus the
Address-rooted schema (supplier addresses fetched as their own entity
rather than nested under a supplier). Each top-level response carries a
summary, its typed records, and truncation_notes — the pattern every
schema in this package follows.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from spire.synthesizer.models_common import (
    AddressInfo,
    BuyerInfo,
    _SUMMARY_FIELD,
    _TRUNCATION_FIELD,
)


class LineInfo(BaseModel):
    """One PO line nested under a purchase order.

    po_line_id is validated against the executor's output after synthesis
    — it MUST appear there."""

    po_line_id: int = Field(
        description="The line's POLineId (numeric key). Must appear in the data."
    )
    line_number: int = Field(description="The line number within the PO.")
    description: str = Field(default="", description="Line description.")
    category: str = Field(default="", description="Purchasing category.")
    quantity: float | None = Field(default=None, description="Ordered quantity.")
    amount: float | None = Field(
        default=None, description="Line amount (the Ordered field, excl. tax)."
    )


class ScheduleInfo(BaseModel):
    """One shipment schedule nested under a purchase order.

    line_location_id is validated against the executor's output after
    synthesis — it MUST appear there.

    Carries the ordered figures alongside the received/billed ones so the
    summary can state received-vs-ordered. Copy the numbers as given; do
    NOT compute percentages or deltas."""

    line_location_id: int = Field(
        description="The schedule's LineLocationId (numeric key). Must appear "
        "in the data."
    )
    schedule_number: int = Field(description="Schedule number within the line.")
    ship_to_location: str = Field(default="", description="Ship-to location.")
    requested_delivery_date: str = Field(
        default="", description="Requested (need-by) delivery date, if present."
    )
    ordered_quantity: float | None = Field(
        default=None, description="Quantity ordered (the Quantity field)."
    )
    ordered_amount: float | None = Field(
        default=None, description="Amount ordered (the Amount field)."
    )
    received_quantity: float | None = Field(
        default=None, description="Quantity received."
    )
    billed_quantity: float | None = Field(
        default=None, description="Quantity billed."
    )
    received_amount: float | None = Field(
        default=None, description="Amount received."
    )
    billed_amount: float | None = Field(default=None, description="Amount billed.")


class DistributionInfo(BaseModel):
    """One distribution nested under a purchase order — the accounts a
    schedule's amount is booked to.

    po_distribution_id is validated against the executor's output after
    synthesis — it MUST appear there."""

    po_distribution_id: int = Field(
        description="The distribution's PODistributionId (numeric key). Must "
        "appear in the data."
    )
    distribution_number: int = Field(description="Distribution number.")
    charge_account: str = Field(
        default="", description="POChargeAccount code combination."
    )
    accrual_account: str = Field(
        default="", description="POAccrualAccount code combination."
    )
    variance_account: str = Field(
        default="", description="POVarianceAccount code combination."
    )
    percentage: float | None = Field(
        default=None, description="Percentage of the schedule allocated here."
    )
    amount: float | None = Field(
        default=None, description="Distributed amount (the Ordered field)."
    )


class ContactInfo(BaseModel):
    """One contact nested under a supplier.

    supplier_contact_id is validated against the executor's output after
    synthesis — it MUST appear there."""

    supplier_contact_id: int = Field(
        description="The contact's SupplierContactId (numeric key). Must "
        "appear in the data."
    )
    contact_name: str = Field(
        description="The contact's display name (last-first, e.g. 'Kim, John')."
    )
    email: str = Field(default="", description="Contact email, if present.")
    job_title: str = Field(default="", description="Job title, if present.")
    is_administrative: bool = Field(
        default=False,
        description="True if this is the primary/administrative contact "
        "(AdministrativeContactFlag).",
    )


class SupplierRecord(BaseModel):
    """One supplier in a supplier-rooted response.

    supplier_id and supplier_number are both validated against the
    executor's output. The LLM must not invent either."""

    supplier_id: int = Field(description="The supplier's SupplierId (numeric PK).")
    supplier_number: str = Field(
        description="The supplier's SupplierNumber (human-readable id)."
    )
    supplier_name: str = Field(description="The supplier's display name.")
    open_po_count: int | None = Field(
        default=None,
        description="Number of open purchase orders for this supplier in the "
        "executor's open_pos output. Set this ONLY when an open_pos bucket is "
        "actually present in the data — leave it null when the query had "
        "nothing to do with purchase orders. Do not report 0 for a query that "
        "never asked about POs.",
    )
    buyers: list[BuyerInfo] = Field(
        default_factory=list,
        description="Buyers assigned to this supplier's open POs. Each "
        "buyer's person_id must appear in the executor's buyers output.",
    )
    addresses: list[AddressInfo] = Field(
        default_factory=list,
        description="This supplier's addresses, when the query asked for "
        "them (nested from the supplier fetch's expand=addresses). Empty "
        "otherwise. Each address_id must appear in the executor's output.",
    )
    contacts: list[ContactInfo] = Field(
        default_factory=list,
        description="This supplier's contacts, when the query asked for them "
        "(a 'contact' bucket in the data). Empty otherwise. Each "
        "supplier_contact_id must appear in the executor's output.",
    )


class InvoiceRecord(BaseModel):
    """One invoice in an invoice-rooted response.

    supplier_number / supplier_id are validated against the executor's
    output when present. invoice_number is free text from the source."""

    invoice_id: int = Field(description="The invoice's InvoiceId (numeric PK).")
    invoice_number: str = Field(description="The invoice's InvoiceNumber.")
    invoice_date: str = Field(description="The invoice date (ISO string).")
    invoice_amount: float = Field(description="The invoice amount.")
    invoice_currency: str = Field(
        default="", description="The invoice currency code, if present."
    )
    supplier_name: str = Field(description="The supplier's display name.")
    supplier_number: str = Field(
        description="The supplier's SupplierNumber. Must appear in the data."
    )


class PurchaseOrderRecord(BaseModel):
    """One purchase order in a PO-rooted response.

    supplier_id and buyer.person_id are validated against the executor's
    output when present."""

    po_header_id: int = Field(description="The PO's POHeaderId (numeric PK).")
    order_number: str = Field(description="The PO's OrderNumber.")
    status: str = Field(description="The PO status (e.g. OPEN, CLOSED).")
    supplier_name: str = Field(description="The supplier's display name.")
    supplier_id: int = Field(
        description="The supplier's SupplierId. Must appear in the data."
    )
    buyer: BuyerInfo | None = Field(
        default=None,
        description="The buyer assigned to this PO, if one is in the data. "
        "person_id must appear in the executor's buyers output.",
    )
    lines: list[LineInfo] = Field(
        default_factory=list,
        description="This PO's lines, when the query asked for them (a "
        "'purchaseorderline' bucket in the data). Empty otherwise. Each "
        "po_line_id must appear in the executor's output.",
    )
    schedules: list[ScheduleInfo] = Field(
        default_factory=list,
        description="This PO's shipment schedules, when the query asked for "
        "them (a 'poschedule' bucket in the data). Empty otherwise. Each "
        "line_location_id must appear in the executor's output.",
    )
    distributions: list[DistributionInfo] = Field(
        default_factory=list,
        description="This PO's distributions — the accounts its amounts are "
        "booked to — when the query asked for them (a 'podistribution' "
        "bucket). Empty otherwise. Each po_distribution_id must appear in "
        "the executor's output.",
    )


# ─────────────────────────────────────────────────────────────────────
# Per-entity top-level response models
#
# Three siblings, one per target entity with an entity-level fetcher.
# Each carries summary + typed records + truncation_notes. The schema
# bound to with_structured_output is selected by target_entity.
#
# SynthesizedResponse is kept as an alias of the supplier-rooted schema
# so existing supplier-path callers/tests are unaffected.
# ─────────────────────────────────────────────────────────────────────


class SupplierResponse(BaseModel):
    """Supplier-rooted synthesized response."""

    summary: str = _SUMMARY_FIELD
    suppliers: list[SupplierRecord] = Field(
        default_factory=list,
        description="One entry per supplier in the final filtered set. "
        "Empty if none passed the filters.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD
    narrowing_tip: str = Field(
        default="",
        description="Optional completeness advisory (QA-12). Set only when "
        "the answer is a SAMPLE (examined < total) — tells the reader the "
        "full scan is slow and lists the entity-level filters that would "
        "narrow it. Empty when the answer already covers the full set.",
    )


class SupplierSummaryResponse(BaseModel):
    """Summary-only schema for the plain supplier-list path.

    The supplier records are built deterministically from the executor
    output (build_supplier_records), so the LLM is asked for the one
    thing it is actually needed for: the prose. Asking it to ALSO re-emit
    25 supplier rows with their addresses cost ~7,900 output tokens, hit
    the model ceiling mid-string, and produced nothing at all.
    """

    summary: str = _SUMMARY_FIELD
    truncation_notes: list[str] = _TRUNCATION_FIELD


class InvoiceResponse(BaseModel):
    """Invoice-rooted synthesized response."""

    summary: str = _SUMMARY_FIELD
    invoices: list[InvoiceRecord] = Field(
        default_factory=list,
        description="One entry per invoice in the final set. Empty if none.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class PurchaseOrderResponse(BaseModel):
    """PurchaseOrder-rooted synthesized response."""

    summary: str = _SUMMARY_FIELD
    purchase_orders: list[PurchaseOrderRecord] = Field(
        default_factory=list,
        description="One entry per purchase order in the final set. "
        "Empty if none.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class AddressRecord(BaseModel):
    """One supplier address in an address-rooted response.

    address_id and supplier_number are validated against the executor's
    output. Address fields are free text from the source."""

    address_id: int = Field(
        description="The address's SupplierAddressId (numeric key). "
        "Must appear in the data."
    )
    supplier_name: str = Field(description="The parent supplier's display name.")
    supplier_number: str = Field(
        description="The parent supplier's SupplierNumber. Must appear in "
        "the data."
    )
    country: str = Field(default="", description="Full country name, if present.")
    city: str = Field(default="", description="City, if present.")
    state: str = Field(default="", description="State/province, if present.")
    formatted_address: str = Field(
        default="", description="One-line formatted address, if present."
    )


class AddressResponse(BaseModel):
    """Address-rooted synthesized response."""

    summary: str = _SUMMARY_FIELD
    addresses: list[AddressRecord] = Field(
        default_factory=list,
        description="One entry per address in the final set. Empty if none.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


# ─────────────────────────────────────────────────────────────────────
# Deterministic record building
#
# "Suppliers with their addresses" used to fail outright. The LLM was
# asked to emit the whole SupplierResponse — every supplier_id,
# supplier_number, supplier_name and nested address copied verbatim from
# data the executor already had. 16,390 tokens in, 7,985 out, response
# truncated mid-string, degenerate-output guard fired, user got nothing
# after a 48-second wait. The saved trace shows well-formed, correct,
# non-repeating JSON that simply ran out of room: the model was doing a
# transcription, not a synthesis.
#
# Records are now built from the executor output directly and the LLM is
# asked only for the summary. Output drops ~7,900 -> ~150 tokens, and the
# answer arrives.
#
# This removes a class of error rather than guarding against it: an id
# copied by code cannot be hallucinated, so the id-validation pass has
# nothing to catch on this path.
# ─────────────────────────────────────────────────────────────────────

def _address_info(raw: dict) -> AddressInfo:
    """One nested address row -> AddressInfo. The incoming field names are
    the tool's (see _flatten_address in suppliers.py)."""
    return AddressInfo(
        address_id=raw.get("SupplierAddressId") or 0,
        country=raw.get("Country") or "",
        city=raw.get("City") or "",
        state=raw.get("State") or "",
        formatted_address=raw.get("FormattedAddress") or "",
    )


def build_supplier_records(rows: list[dict]) -> list[SupplierRecord]:
    """Executor supplier rows -> SupplierRecord list, verbatim.

    Pure: no LLM, no I/O. Addresses arrive already nested on each row (the
    suppliers tool sets row["addresses"] when include_addresses is on), so
    this is a field rename, not a reconstruction — there is no join here.

    buyers, contacts and open_po_count stay empty BY DESIGN: this path
    only runs when the executor produced a single supplier bucket, which
    means nothing was fetched to put in them. A query that DOES fetch
    buyers takes the LLM path, where the cross-bucket join is still the
    model's job.
    """
    records: list[SupplierRecord] = []
    for row in rows:
        records.append(
            SupplierRecord(
                supplier_id=row.get("SupplierId") or 0,
                supplier_number=str(row.get("SupplierNumber") or ""),
                supplier_name=row.get("Supplier") or "",
                addresses=[
                    _address_info(a) for a in (row.get("addresses") or [])
                ],
            )
        )
    return records


def plain_supplier_bucket(outputs: dict[str, list[dict]]) -> str | None:
    """Name of the supplier bucket when this is a PLAIN supplier list.

    "Plain" means one bucket of supplier rows and nothing else, so every
    field the response needs is already on those rows. Returns None the
    moment anything would have to be joined across buckets — the anchor
    question fetches suppliers, open POs and buyers, and working out which
    buyer belongs to which supplier is real work that stays with the LLM.

    Deliberately conservative: returning None too often costs tokens,
    returning a wrong bucket costs correctness.
    """
    if len(outputs) != 1:
        return None
    name, rows = next(iter(outputs.items()))
    if not rows or not isinstance(rows[0], dict):
        return None
    first = rows[0]
    if "SupplierId" in first and "Supplier" in first:
        return name
    return None


def _supplier_with_open_pos(
    outputs: dict[str, list[dict]],
) -> tuple[str, str] | None:
    """(supplier_bucket, po_bucket) for the "suppliers with open POs" join.

    The shape is exactly two buckets: a supplier list (rows with SupplierId
    and Supplier) and a PO list (rows with POHeaderId and SupplierId). Each
    supplier's open-PO count and buyers come from joining the PO bucket onto
    the supplier rows by SupplierId — the join plain_supplier_bucket
    deliberately leaves out, so it used to fall to the LLM (which miscounted
    its own table, 42 vs 43). Building it here makes the count exact.

    Returns None unless there are exactly two buckets of the right shapes,
    so plain lists and other joins are unaffected. Conservative by design:
    a wrong match costs correctness, a miss only costs tokens.
    """
    if len(outputs) != 2:
        return None
    supplier_bucket: str | None = None
    po_bucket: str | None = None
    for name, rows in outputs.items():
        if not rows or not isinstance(rows[0], dict):
            return None
        first = rows[0]
        if "POHeaderId" in first and "SupplierId" in first:
            po_bucket = name
        elif "SupplierId" in first and "Supplier" in first:
            supplier_bucket = name
    if supplier_bucket is None or po_bucket is None:
        return None
    return supplier_bucket, po_bucket


def build_suppliers_with_open_pos(
    supplier_rows: list[dict], po_rows: list[dict]
) -> list[SupplierRecord]:
    """Supplier rows + PO rows -> SupplierRecords with open_po_count + buyers.

    Pure: no LLM, no I/O. Groups po_rows by SupplierId, then for each
    supplier sets open_po_count to that group's size and buyers to the
    distinct buyers on those POs (BuyerId/Buyer sit on each PO row, so no
    separate bucket). Buyers dedupe by person_id, in first-seen order;
    a PO with no BuyerId contributes no buyer.

    This is the deterministic version of the cross-bucket join
    build_supplier_records leaves empty by design — every count is
    len(group), never a model estimate.
    """
    by_supplier: dict[int, list[dict]] = {}
    for po in po_rows:
        sid = po.get("SupplierId")
        if sid is None:
            continue
        by_supplier.setdefault(sid, []).append(po)

    records: list[SupplierRecord] = []
    for row in supplier_rows:
        sid = row.get("SupplierId") or 0
        group = by_supplier.get(sid, [])
        buyers: list[BuyerInfo] = []
        seen: set = set()
        for po in group:
            bid = po.get("BuyerId")
            if bid is None or bid in seen:
                continue
            seen.add(bid)
            buyers.append(
                BuyerInfo(person_id=bid, display_name=po.get("Buyer") or "")
            )
        records.append(
            SupplierRecord(
                supplier_id=sid,
                supplier_number=str(row.get("SupplierNumber") or ""),
                supplier_name=row.get("Supplier") or "",
                open_po_count=len(group),
                buyers=buyers,
            )
        )
    return records


def _supplier_with_contacts(
    outputs: dict[str, list[dict]],
) -> tuple[str, str] | None:
    """(supplier_bucket, contact_bucket) for the "suppliers + contacts" join.

    Two buckets: a supplier list (rows with SupplierId and Supplier) and a
    contact list (rows with SupplierContactId). Contacts now carry their
    parent SupplierId (stamped by the supplier_contacts tool), so they can
    be grouped back to their supplier here instead of by the LLM — the join
    that used to fall through to synthesis for both the single-supplier
    ("contacts for Lee Supplies") and multi-supplier ("contacts for
    suppliers in US") shapes.

    Returns None unless there are exactly two buckets of the right shapes,
    so plain lists and other joins are unaffected. Conservative by design.
    """
    if len(outputs) != 2:
        return None
    supplier_bucket: str | None = None
    contact_bucket: str | None = None
    for name, rows in outputs.items():
        if not rows or not isinstance(rows[0], dict):
            return None
        first = rows[0]
        if "SupplierContactId" in first:
            contact_bucket = name
        elif "SupplierId" in first and "Supplier" in first:
            supplier_bucket = name
    if supplier_bucket is None or contact_bucket is None:
        return None
    return supplier_bucket, contact_bucket


def build_suppliers_with_contacts(
    supplier_rows: list[dict], contact_rows: list[dict]
) -> list[SupplierRecord]:
    """Supplier rows + contact rows -> SupplierRecords with nested contacts.

    Pure: no LLM, no I/O. Groups contact_rows by their stamped SupplierId,
    then attaches each supplier's contacts as ContactInfo, with
    is_administrative read from AdministrativeContactFlag. The deterministic
    version of the join build_supplier_records leaves empty by design.

    is_administrative coerces the pod's flag: it may arrive as the string
    "Y"/"N" or a bool; only a truthy "Y"/True marks the primary contact.
    """
    by_supplier: dict[int, list[dict]] = {}
    for c in contact_rows:
        sid = c.get("SupplierId")
        if sid is None:
            continue
        by_supplier.setdefault(sid, []).append(c)

    records: list[SupplierRecord] = []
    for row in supplier_rows:
        sid = row.get("SupplierId") or 0
        group = by_supplier.get(sid, [])
        contacts: list[ContactInfo] = []
        for c in group:
            flag = c.get("AdministrativeContactFlag")
            is_admin = flag is True or (
                isinstance(flag, str) and flag.strip().upper() == "Y"
            )
            contacts.append(
                ContactInfo(
                    supplier_contact_id=c.get("SupplierContactId") or 0,
                    contact_name=c.get("ContactName") or "",
                    email=c.get("Email") or "",
                    job_title=c.get("JobTitle") or "",
                    is_administrative=is_admin,
                )
            )
        records.append(
            SupplierRecord(
                supplier_id=sid,
                supplier_number=str(row.get("SupplierNumber") or ""),
                supplier_name=row.get("Supplier") or "",
                contacts=contacts,
            )
        )
    return records


def build_purchase_order_records(rows: list[dict]) -> list[PurchaseOrderRecord]:
    """Executor PO rows -> PurchaseOrderRecord list, verbatim.

    Pure: no LLM, no I/O. The mirror of build_supplier_records for the
    plain PO-list path (REC-2). Every field the record needs is already on
    the row — order number, status, supplier, and the buyer — so this is a
    rename, not a reconstruction, and there is no cross-bucket join.

    supplier_id uses `or 0`: a supplierless PO (e.g. the pod's Incomplete
    OrderNumber "1", SupplierId null) coerces to 0, the same "no supplier"
    sentinel the response validator now skips rather than flagging as a
    hallucinated id.

    buyer is populated from the SAME row (BuyerId / Buyer sit on the PO
    header, not in a separate bucket), so it is deterministic here — unlike
    the supplier path, where a buyer would require a join and is left to the
    LLM. When BuyerId is null there is no buyer to name, so buyer stays None.

    lines / schedules / distributions stay empty BY DESIGN: this path runs
    only when the executor produced a single PO bucket, so no child rows
    were fetched to put in them. A query that DOES fetch a PO's children
    takes the LLM path, where the hierarchy join is still the model's job.
    """
    records: list[PurchaseOrderRecord] = []
    for row in rows:
        buyer_id = row.get("BuyerId")
        buyer = (
            BuyerInfo(
                person_id=buyer_id,
                display_name=row.get("Buyer") or "",
            )
            if buyer_id is not None
            else None
        )
        records.append(
            PurchaseOrderRecord(
                po_header_id=row.get("POHeaderId") or 0,
                order_number=str(row.get("OrderNumber") or ""),
                status=row.get("Status") or row.get("StatusCode") or "",
                supplier_name=row.get("Supplier") or "",
                supplier_id=row.get("SupplierId") or 0,
                buyer=buyer,
            )
        )
    return records


def plain_po_bucket(outputs: dict[str, list[dict]]) -> str | None:
    """Name of the PO bucket when this is a PLAIN purchase-order list.

    The mirror of plain_supplier_bucket. "Plain" means one bucket of PO
    rows and nothing else, so every field the response needs — including
    the buyer, which rides on the PO header — is already on those rows.
    Returns None the moment there is more than one bucket: a PO query that
    also fetched lines / schedules / distributions is the "PO with children"
    shape, handled locally by po_with_children_buckets +
    build_po_with_children — not here, and no longer on the LLM.

    Deliberately conservative, same as the supplier version: returning None
    too often costs tokens; returning a wrong bucket costs correctness.
    """
    if len(outputs) != 1:
        return None
    name, rows = next(iter(outputs.items()))
    if not rows or not isinstance(rows[0], dict):
        return None
    first = rows[0]
    if "POHeaderId" in first and "OrderNumber" in first:
        return name
    return None


def build_invoice_records(rows: list[dict]) -> list[InvoiceRecord]:
    """Executor invoice rows -> InvoiceRecord list, verbatim.

    Pure: no LLM, no I/O. The mirror of build_supplier_records and
    build_purchase_order_records for the plain invoice-list path (#3).
    Every field the record needs — number, date, amount, currency,
    supplier name and number — is already on the row, so this is a rename,
    not a reconstruction, and there is no cross-bucket join. Previously an
    invoice list was the model's job: it re-emitted every row field by
    field (the expensive half that can silently drop a field), plus a
    date-range/amount-range summary. The record table is now built here;
    the summary comes from local_list_summary like the sibling paths.

    invoice_id uses `or 0` and amount `or 0.0` so a null coerces cleanly
    rather than failing schema validation; a genuinely null-amount invoice
    (the pod has some at 0) reads as 0.0, which is what it is.
    """
    records: list[InvoiceRecord] = []
    for row in rows:
        records.append(
            InvoiceRecord(
                invoice_id=row.get("InvoiceId") or 0,
                invoice_number=str(row.get("InvoiceNumber") or ""),
                invoice_date=str(row.get("InvoiceDate") or ""),
                invoice_amount=row.get("InvoiceAmount") or 0.0,
                invoice_currency=str(row.get("InvoiceCurrency") or ""),
                supplier_name=row.get("Supplier") or "",
                supplier_number=str(row.get("SupplierNumber") or ""),
            )
        )
    return records


def plain_invoice_bucket(outputs: dict[str, list[dict]]) -> str | None:
    """Name of the invoice bucket when this is a PLAIN invoice list.

    The mirror of plain_supplier_bucket / plain_po_bucket. "Plain" means
    one bucket of invoice rows and nothing else, so every field the
    response needs is already on those rows. Returns None the moment there
    is more than one bucket: an invoice query that also fetched lines, tax
    lines or a DFF is a multi-bucket shape and stays on its own path (or
    the LLM), not here.

    Deliberately conservative, same as the siblings: returning None too
    often costs tokens; returning a wrong bucket costs correctness.
    """
    if len(outputs) != 1:
        return None
    name, rows = next(iter(outputs.items()))
    if not rows or not isinstance(rows[0], dict):
        return None
    first = rows[0]
    if "InvoiceId" in first and "InvoiceNumber" in first:
        return name
    return None


def _derived_received_amount(row: dict) -> float | None:
    """Received AMOUNT for a schedule row, derived from quantity.

    ReceivedAmount is 0 or null on every schedule row on this pod (curl-
    confirmed across ~4,500 rows) — the received leg exists only as a
    QUANTITY. So a received amount must be prorated from the ordered amount
    by the received fraction, exactly as Oracle's own BilledAmount is
    derived, and exactly as the lifecycle tool already does it. Presenting
    raw ReceivedAmount (0.0) beside a prose line that says "1 of 1 received"
    is the AI-12 contradiction this replaces.

    amount * (received_quantity / ordered_quantity), guarded: a null amount,
    a null received quantity, or a zero/absent ordered quantity all yield
    None rather than a wrong number or a ZeroDivisionError.
    """
    amount = row.get("Amount")
    ordered_q = row.get("Quantity")
    received_q = row.get("ReceivedQuantity")
    if amount is None or received_q is None or not ordered_q:
        return None
    return amount * (received_q / ordered_q)


def _build_line(row: dict) -> LineInfo:
    return LineInfo(
        po_line_id=row.get("POLineId") or 0,
        line_number=row.get("LineNumber") or 0,
        description=row.get("Description") or "",
        category=row.get("Category") or "",
        quantity=row.get("Quantity"),
        amount=row.get("Ordered"),
    )


def _build_schedule(row: dict) -> ScheduleInfo:
    # received_amount is DERIVED (see _derived_received_amount); every other
    # figure is copied as-is. ordered_amount is the schedule's Amount (the
    # ordered figure on this resource), ordered_quantity its Quantity.
    return ScheduleInfo(
        line_location_id=row.get("LineLocationId") or 0,
        schedule_number=row.get("ScheduleNumber") or 0,
        ship_to_location=row.get("ShipToLocation") or "",
        requested_delivery_date=row.get("RequestedDeliveryDate") or "",
        ordered_quantity=row.get("Quantity"),
        ordered_amount=row.get("Amount"),
        received_quantity=row.get("ReceivedQuantity"),
        billed_quantity=row.get("BilledQuantity"),
        received_amount=_derived_received_amount(row),
        billed_amount=row.get("BilledAmount"),
    )


def _build_distribution(row: dict) -> DistributionInfo:
    # amount is the ex-tax Ordered figure, NOT Total (inc-tax): the line and
    # schedule tables beside it show ex-tax (Ordered / Amount), so a Total
    # here would silently mix tax bases down one column. Matches the figure
    # the LLM path showed before this branch existed.
    return DistributionInfo(
        po_distribution_id=row.get("PODistributionId") or 0,
        distribution_number=row.get("DistributionNumber") or 0,
        charge_account=row.get("POChargeAccount") or "",
        accrual_account=row.get("POAccrualAccount") or "",
        variance_account=row.get("POVarianceAccount") or "",
        percentage=row.get("Percentage"),
        amount=row.get("Ordered"),
    )


# Signature fields that identify each PO child bucket by CONTENT, not by the
# plan's output_name (which the parser sets and could rename). A distribution
# row is the only one carrying PODistributionId; a schedule the only one with
# LineLocationId but no PODistributionId; a line has POLineId but neither. The
# order of these checks matters — distribution before schedule before line —
# because a distribution row also carries POLineId and a schedule also carries
# POLineId, so the most-specific key must be tested first.
def _classify_po_child(rows: list[dict]) -> str | None:
    if not rows or not isinstance(rows[0], dict):
        return None
    first = rows[0]
    if "PODistributionId" in first:
        return "distributions"
    if "LineLocationId" in first:
        return "schedules"
    if "POLineId" in first and "LineNumber" in first:
        return "lines"
    return None


def po_with_children_buckets(outputs: dict[str, list[dict]]) -> dict[str, str] | None:
    """Map roles -> bucket names for a "PO plus its children" result.

    Returns e.g. {"po": "po", "schedules": "poschedule"} when the executor
    produced a PO header bucket AND at least one child bucket (lines,
    schedules, distributions). Returns None otherwise — for the single-bucket
    plain-list case (plain_po_bucket owns that) or anything not PO-shaped.

    Buckets are matched by content signature, not output_name, so a rename in
    the plan cannot mis-route. The PO bucket is the one carrying POHeaderId +
    OrderNumber but no child key; children are classified by _classify_po_child.

    This is what lets the PO-with-children path synthesize locally instead of
    on the LLM: once the buckets are identified, build_po_with_children
    assembles the nested record deterministically.
    """
    po_name: str | None = None
    child_map: dict[str, str] = {}
    for name, rows in outputs.items():
        if not rows or not isinstance(rows[0], dict):
            continue
        role = _classify_po_child(rows)
        if role is not None:
            # First bucket of a given child role wins; a second is ignored
            # (the executor produces one bucket per child type).
            child_map.setdefault(role, name)
            continue
        first = rows[0]
        if "POHeaderId" in first and "OrderNumber" in first:
            po_name = name
    if po_name is None or not child_map:
        return None
    result = {"po": po_name}
    result.update(child_map)
    return result


def build_po_with_children(
    outputs: dict[str, list[dict]], buckets: dict[str, str]
) -> list[PurchaseOrderRecord]:
    """Assemble PO records with nested lines/schedules/distributions, no LLM.

    The child lists are FLAT under each PO — lines, schedules and
    distributions are siblings, matching how the models are shaped and how
    the display renders three sub-tables. So this attaches every line /
    schedule / distribution belonging to a PO (matched on POHeaderId) to that
    PO's list; it does not build a line->schedule->distribution tree. Received
    amounts are derived in _build_schedule.

    Every id on every child comes straight from an executor row, so the
    response validator's child-id cross-checks (po_line_ids,
    line_location_ids, po_distribution_ids) all pass by construction.
    """
    po_rows = outputs.get(buckets["po"], [])
    line_rows = outputs.get(buckets.get("lines", ""), [])
    sched_rows = outputs.get(buckets.get("schedules", ""), [])
    dist_rows = outputs.get(buckets.get("distributions", ""), [])

    def _for_po(rows: list[dict], po_header_id: int) -> list[dict]:
        return [r for r in rows if r.get("POHeaderId") == po_header_id]

    records: list[PurchaseOrderRecord] = []
    for po in po_rows:
        ph = po.get("POHeaderId")
        buyer_id = po.get("BuyerId")
        buyer = (
            BuyerInfo(person_id=buyer_id, display_name=po.get("Buyer") or "")
            if buyer_id is not None
            else None
        )
        records.append(
            PurchaseOrderRecord(
                po_header_id=ph or 0,
                order_number=str(po.get("OrderNumber") or ""),
                status=po.get("Status") or po.get("StatusCode") or "",
                supplier_name=po.get("Supplier") or "",
                supplier_id=po.get("SupplierId") or 0,
                buyer=buyer,
                lines=[_build_line(r) for r in _for_po(line_rows, ph)],
                schedules=[_build_schedule(r) for r in _for_po(sched_rows, ph)],
                distributions=[
                    _build_distribution(r) for r in _for_po(dist_rows, ph)
                ],
            )
        )
    return records




def _filtered_supplier_list(
    outputs: dict[str, list[dict]],
) -> tuple[str, str] | None:
    """Names of (source, matched) buckets for a FILTERED supplier list.

    The mirror of plain_supplier_bucket for the two-bucket case. An
    edge-traversal filter (has_classification, has_site_in_bu,
    has_invoice_over_amount, and the rest) fetches a source list, then
    keeps the rows that match, via filter_source_when_nonempty. The
    executor names the matched bucket ``{source}_{suffix}`` — so exactly
    two buckets remain and one name is the other's prefix.

    Returns (source_bucket, matched_bucket) when the outputs have that
    shape and both hold supplier rows; None otherwise. Conservative in
    the same spirit as plain_supplier_bucket: return None the moment the
    shape is not unmistakably a source + matched pair, so a wrong guess
    never routes a join-shaped result through the honest-denominator
    branch.

    Detection is by name (``{source}_{suffix}``), not by row count: the
    matched set can equal, be smaller than, or in a degenerate case match
    the source size, so length cannot tell source from matched. The name
    can.
    """
    if len(outputs) != 2:
        return None
    names = list(outputs.keys())
    # One name must be a strict prefix of the other, with an underscore
    # boundary — that is the source/matched naming, not a coincidence.
    a, b = names
    if b.startswith(a + "_"):
        source, matched = a, b
    elif a.startswith(b + "_"):
        source, matched = b, a
    else:
        return None
    # Both buckets must be supplier rows (or empty — an empty matched set
    # is a valid answer: "0 of 25 match").
    for bucket in (source, matched):
        rows = outputs[bucket]
        if rows and (not isinstance(rows[0], dict) or "SupplierId" not in rows[0]):
            return None
    # The source bucket must actually carry supplier rows; if it is empty
    # there was nothing to examine and this is not the shape we handle.
    if not outputs[source]:
        return None
    return (source, matched)
# ─────────────────────────────────────────────────────────────────────
# QA-12 completeness advisory
# ─────────────────────────────────────────────────────────────────────

# Reader-facing label for each entity-level Supplier filter type. Only
# the NARROWING filters appear — by_id is a fetch-one and is excluded by
# the caller, so it needs no label. Kept here beside the response it
# feeds; if a new entity-level filter is added to kg_entity_filter, add
# its label here or it will show as its raw type name.
_SUPPLIER_FILTER_LABELS: dict[str, str] = {
    "country": "country",
    "status": "status",
    "business_relationship": "business relationship",
    "name_fragment": "name",
    "created_date": "creation date",
}


def build_narrowing_tip(
    filter_types: set[str],
    total: int | None,
    entity_label: str = "suppliers",
) -> str:
    """Short completeness advisory (QA-12), or "" when not applicable.

    Given the entity-level filter types available for the entity (from
    kg_entity_filter, mechanism=entity_level) and the pod total, return a
    one-line tip naming the filters a reader can add to get a complete
    answer cheaply. Deterministic — the filter names come from the KG,
    never guessed. Returns "" when there is no total to talk about.

    The wording states WHY (the full scan is slow) so the ask to narrow
    is not mysterious. Kept crisp on purpose: a long tip does not get
    read.
    """
    if total is None:
        return ""
    labels = [
        _SUPPLIER_FILTER_LABELS.get(ft, ft)
        for ft in filter_types
        if ft in _SUPPLIER_FILTER_LABELS
    ]
    if not labels:
        return ""
    labels.sort()
    filters_text = ", ".join(labels)
    return (
        f"Reading all {total:,} {entity_label} is slow. "
        f"Narrow with a filter: {filters_text}."
    )


