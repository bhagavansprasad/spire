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

