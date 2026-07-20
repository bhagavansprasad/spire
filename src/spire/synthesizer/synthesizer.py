"""
Response synthesizer for the KG-driven path (Architecture Option 3).

Takes the executor's output (dict[output_name, list[dict]]) and
produces a structured, validated answer for the user.

Architecture decisions locked for v1:
- LLM: Gemini 2.0 Flash via langchain-google-genai (same as runner.py)
- Output: Pydantic-typed JSON via with_structured_output, NOT free-form
  prose. Variance is bounded by the schema; row 7 of the rubric becomes
  mechanically verifiable.
- Hallucination guard: every supplier_id / supplier_number / person_id /
  invoice identifier in the response is cross-referenced against the
  executor's source data. Invented IDs raise HallucinationError loudly —
  no auto-retry, no silent acceptance.

Feature 5 (schema generalization):
- The response schema is no longer fixed to the supplier-rooted shape.
  Three sibling top-level schemas exist — one per target entity that has
  an entity-level fetcher today (Supplier, Invoice, PurchaseOrder). The
  schema is selected from intent.target_entity at synthesis time and
  bound to with_structured_output. Each schema carries its own typed
  record list and its own hallucination validator.
- A target_entity with no schema (e.g. Buyer aggregation, Contract)
  raises UnsupportedEntityError loudly. Graceful messaging for that case
  is feature 8's job, not the synthesizer's.

Companion design refs: docs/feature_roadmap.md (feature 5);
docs/design3_measurement_report.md (row 7 = no synthesizer).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from spire.config import GEMINI_MODEL, GEMINI_TEMPERATURE


# ─────────────────────────────────────────────────────────────────────
# LLM configuration
# ─────────────────────────────────────────────────────────────────────

# Model and determinism come from spire.config (single source of truth).
_MODEL_NAME = GEMINI_MODEL
_TEMPERATURE = GEMINI_TEMPERATURE


# ─────────────────────────────────────────────────────────────────────
# Shared sub-models
# ─────────────────────────────────────────────────────────────────────


class BuyerInfo(BaseModel):
    """One buyer mentioned in the synthesized response.

    person_id is validated against the executor's buyers output after
    synthesis — it MUST appear there."""

    person_id: int = Field(description="The buyer's PersonId (HCM key).")
    display_name: str = Field(description="The buyer's display name.")


class AddressInfo(BaseModel):
    """One address nested under a supplier in a supplier-rooted response.

    address_id is validated against the executor's output after synthesis
    — it MUST appear there. Used for the "suppliers with their addresses"
    shape, where addresses hang off each supplier record."""

    address_id: int = Field(
        description="The address's SupplierAddressId (numeric key). "
        "Must appear in the data."
    )
    country: str = Field(default="", description="Full country name, if present.")
    city: str = Field(default="", description="City, if present.")
    state: str = Field(default="", description="State/province, if present.")
    formatted_address: str = Field(
        default="", description="One-line formatted address, if present."
    )


# ─────────────────────────────────────────────────────────────────────
# Per-entity record models
# ─────────────────────────────────────────────────────────────────────


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


_TRUNCATION_FIELD = Field(
    default_factory=list,
    description="One short note per truncated step. Each note states the "
    "step's output_name, the total_available count if known, and how many "
    "records were examined. Empty when no step was truncated. Populate ONLY "
    "from the truncation block in the executor output; never invent counts.",
)

_SUMMARY_FIELD = Field(
    description="One-paragraph natural-language summary (3-5 sentences). "
    "Do not invent specifics not in the data."
)


class SupplierResponse(BaseModel):
    """Supplier-rooted synthesized response."""

    summary: str = _SUMMARY_FIELD
    suppliers: list[SupplierRecord] = Field(
        default_factory=list,
        description="One entry per supplier in the final filtered set. "
        "Empty if none passed the filters.",
    )
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


class ReceivablesInvoiceLineInfo(BaseModel):
    """One AR invoice line nested under a receivables invoice.

    customer_transaction_line_id is validated against the executor's output
    after synthesis — it MUST appear there."""

    customer_transaction_line_id: int = Field(
        description="The line's CustomerTransactionLineId (numeric key). "
        "Must appear in the data."
    )
    line_number: int = Field(description="The line number within the invoice.")
    description: str = Field(default="", description="Line description.")
    quantity: float | None = Field(default=None, description="Line quantity.")
    unit_selling_price: float | None = Field(
        default=None, description="Unit selling price for the line."
    )
    amount: float | None = Field(
        default=None, description="Line amount (the LineAmount field)."
    )


class ReceivablesInvoiceRecord(BaseModel):
    """One AR invoice in a receivables-invoice-rooted response.

    customer_transaction_id is validated against the executor's output."""

    customer_transaction_id: int = Field(
        description="The invoice's CustomerTransactionId (numeric PK)."
    )
    transaction_number: str = Field(
        description="The invoice's TransactionNumber."
    )
    bill_to_customer_name: str = Field(
        default="", description="Bill-to customer display name."
    )
    status: str = Field(
        default="", description="The invoice status (e.g. Complete)."
    )
    currency: str = Field(
        default="", description="Invoice currency (InvoiceCurrencyCode)."
    )
    amount: float | None = Field(
        default=None, description="Invoice amount (EnteredAmount)."
    )
    balance: float | None = Field(
        default=None, description="Open balance (InvoiceBalanceAmount)."
    )
    lines: list[ReceivablesInvoiceLineInfo] = Field(
        default_factory=list,
        description="This invoice's lines, when the query asked for them (a "
        "'receivablesinvoiceline' bucket in the data). Empty otherwise. Each "
        "customer_transaction_line_id must appear in the executor's output.",
    )


class ReceivablesInvoiceResponse(BaseModel):
    """ReceivablesInvoice-rooted synthesized response."""

    summary: str = _SUMMARY_FIELD
    receivables_invoices: list[ReceivablesInvoiceRecord] = Field(
        default_factory=list,
        description="One entry per AR invoice in the final set. "
        "Empty if none.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class CustomerAccountTransactionInfo(BaseModel):
    """One transaction nested under a customer account.

    transaction_id is validated against the executor's output after
    synthesis — it MUST appear there. This is the account's payment-schedule
    transaction (a TransactionId, small int), NOT the AR-invoice
    CustomerTransactionId."""

    transaction_id: int = Field(
        description="The transaction's TransactionId (numeric key). Must "
        "appear in the data."
    )
    transaction_number: str = Field(
        description="The transaction number."
    )
    transaction_class: str = Field(
        default="", description="Transaction class (e.g. Invoice)."
    )
    transaction_date: str = Field(
        default="", description="Transaction date."
    )
    amount: float | None = Field(
        default=None, description="Original amount (TotalOriginalAmount)."
    )
    balance: float | None = Field(
        default=None, description="Open balance (TotalBalanceAmount)."
    )
    status: str = Field(
        default="", description="Installment status (e.g. Closed)."
    )


class CustomerAccountRecord(BaseModel):
    """One customer account in a customer-account-rooted response.

    account_id is validated against the executor's output."""

    account_id: int = Field(
        description="The account's AccountId (numeric PK)."
    )
    account_number: str = Field(
        description="The account number."
    )
    customer_name: str = Field(
        default="", description="Customer display name."
    )
    open_receivables: float | None = Field(
        default=None,
        description="Open receivables for the account "
        "(TotalOpenReceivablesForAccount).",
    )
    transactions: list[CustomerAccountTransactionInfo] = Field(
        default_factory=list,
        description="This account's transactions, when the query asked for "
        "them (a 'customertransaction' bucket in the data). Empty "
        "otherwise. Each transaction_id must appear in the executor's "
        "output.",
    )


class CustomerAccountResponse(BaseModel):
    """CustomerAccount-rooted synthesized response."""

    summary: str = _SUMMARY_FIELD
    customer_accounts: list[CustomerAccountRecord] = Field(
        default_factory=list,
        description="One entry per customer account in the final set. "
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


class SupplierSpendRow(BaseModel):
    """One supplier in a spend ranking (feature 7 aggregation).

    supplier_number is validated against the ranking the executor
    produced — the LLM must not invent or reorder suppliers."""

    supplier_name: str = Field(description="The supplier's display name.")
    supplier_number: str = Field(
        description="The supplier's SupplierNumber (human-readable id)."
    )
    total_spend: float = Field(
        description="Total invoiced amount for this supplier over the range, "
        "copied exactly from the ranking data. Never recompute."
    )
    invoice_count: int = Field(
        description="Number of invoices for this supplier, copied from the "
        "ranking data."
    )


class SupplierSpendRankingResponse(BaseModel):
    """Aggregation response: suppliers ranked by total spend (feature 7)."""

    summary: str = _SUMMARY_FIELD
    suppliers: list[SupplierSpendRow] = Field(
        default_factory=list,
        description="Suppliers in ranked order (highest spend first), copied "
        "from the ranking data. Do not reorder, add, or drop suppliers.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class SupplierPOValueRow(BaseModel):
    """One supplier in a PO-value ranking (P6 aggregation).

    Note supplier_ID, not supplier_number: purchase orders do not carry a
    SupplierNumber (the PO header has SupplierId and Supplier only), so
    this ranking cannot reuse SupplierSpendRow. Validated against the
    ranking the executor produced — the LLM must not invent or reorder
    suppliers."""

    supplier_name: str = Field(description="The supplier's display name.")
    supplier_id: int = Field(
        description="The supplier's SupplierId (numeric key). Must appear "
        "in the ranking data."
    )
    total_ordered: float = Field(
        description="Total committed PO value for this supplier, copied "
        "exactly from the ranking data. Never recompute."
    )
    po_count: int = Field(
        description="Number of purchase orders for this supplier, copied "
        "from the ranking data."
    )


class SupplierPOValueRankingResponse(BaseModel):
    """Aggregation response: suppliers ranked by committed PO value."""

    summary: str = _SUMMARY_FIELD
    suppliers: list[SupplierPOValueRow] = Field(
        default_factory=list,
        description="Suppliers in ranked order (highest committed value "
        "first), copied from the ranking data. Do not reorder, add, or "
        "drop suppliers.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class POStatusRow(BaseModel):
    """One status bucket in a PO status breakdown (P6 aggregation)."""

    status: str = Field(
        description="The StatusCode, copied exactly (e.g. 'OPEN', "
        "'CLOSED FOR RECEIVING'). Note the pod uses spaces, not "
        "underscores."
    )
    po_count: int = Field(
        description="Number of POs in this status, copied from the data."
    )
    total_ordered: float = Field(
        description="Total committed value in this status, copied exactly. "
        "Never recompute."
    )


class POStatusBreakdownResponse(BaseModel):
    """Aggregation response: PO count and value broken down by status."""

    summary: str = _SUMMARY_FIELD
    total_pos: int = Field(
        description="Grand count across all statuses, copied from the data."
    )
    total_ordered: float = Field(
        description="Grand total value across all statuses, copied exactly."
    )
    statuses: list[POStatusRow] = Field(
        default_factory=list,
        description="One row per status, value descending, copied from the "
        "data. Do not reorder, add, drop, or merge statuses.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class OpenPOSummaryResponse(BaseModel):
    """Aggregation response: committed spend and open-PO count (P6)."""

    summary: str = _SUMMARY_FIELD
    po_count: int = Field(
        description="Number of open POs, copied from the data."
    )
    total_ordered: float = Field(
        description="Total committed value across the open POs, copied "
        "exactly. Never recompute."
    )
    supplier_count: int = Field(
        description="Number of distinct suppliers with an open PO, copied "
        "from the data."
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class CountResponse(BaseModel):
    """Count response: the size of a (possibly filtered) entity set.

    Built deterministically, without the LLM — the count is already in the
    executor output / truncation block, so there is nothing to synthesize
    and no risk of an invented number. Phase 10."""

    summary: str = Field(
        description="One-sentence statement of the count."
    )
    entity: str = Field(description="The entity counted, e.g. 'Supplier'.")
    count: int | None = Field(
        description="The exact count, or null when the true total is not "
        "known (a client-side filter exceeded the examine cap)."
    )
    count_is_exact: bool = Field(
        description="True when count is the exact total; False when it is a "
        "lower bound (the true total was not fully retrieved)."
    )
    truncation_notes: list[str] = Field(
        default_factory=list,
        description="Unused for counts (the count itself carries the total); "
        "present for formatter compatibility with other responses.",
    )


class ComparisonResponse(BaseModel):
    """Comparison response: invoiced vs ordered (P6c).

    Built deterministically, without the LLM — the comparison tool has
    already fetched both sides, joined them, and computed the totals and
    the difference. There is nothing to synthesize and no risk of an
    invented number, so this mirrors CountResponse rather than the
    LLM-driven aggregation path. The 'summary' is templated from the
    tool's own numbers; the structured fields carry those numbers through
    unchanged."""

    summary: str = Field(
        description="Plain-language statement of the comparison."
    )
    shape: str = Field(
        description="The comparison shape tag, e.g. 'po_invoiced_vs_ordered'."
    )
    truncation_notes: list[str] = Field(
        default_factory=list,
        description="Any truncation note carried from the tool.",
    )

# SynthesizedResponse. Keeping the name means supplier-path code and
# tests that import SynthesizedResponse / SupplierSummary still work.
SynthesizedResponse = SupplierResponse
SupplierSummary = SupplierRecord


# entity name -> (response schema). Only entities with a real fetcher.
SYNTHESIS_SCHEMAS: dict[str, type[BaseModel]] = {
    "Supplier": SupplierResponse,
    "Invoice": InvoiceResponse,
    "Address": AddressResponse,
    "PurchaseOrder": PurchaseOrderResponse,
    "ReceivablesInvoice": ReceivablesInvoiceResponse,
    "CustomerAccount": CustomerAccountResponse,
}


# Aggregation responses are selected by the SHAPE TAG the tool stamps on
# its result, not by target_entity (an aggregation Intent carries an
# aggregate block instead of a target entity). The executor puts that
# result under the "aggregation" bucket. Mirrors SYNTHESIS_SCHEMAS above:
# one entry per shape, so a new aggregation tool is a new row here rather
# than another branch in the routing.
AGGREGATION_SCHEMAS: dict[str, tuple[type[BaseModel], str]] = {
    "supplier_spend_ranking": (
        SupplierSpendRankingResponse,
        "SupplierSpendRanking",
    ),
    "supplier_po_value_ranking": (
        SupplierPOValueRankingResponse,
        "SupplierPOValueRanking",
    ),
    "po_status_breakdown": (POStatusBreakdownResponse, "POStatusBreakdown"),
    "open_po_summary": (OpenPOSummaryResponse, "OpenPOSummary"),
}


def _aggregation_shape(outputs: dict[str, list[dict]]) -> str | None:
    """Return the shape tag of an aggregation result, or None if the
    outputs are an entity list rather than an aggregation.

    The aggregation tools each stamp their result with a 'shape'; the
    executor wraps it in a one-element list under 'aggregation'."""
    bucket = outputs.get("aggregation")
    if not bucket:
        return None
    first = bucket[0]
    if not isinstance(first, dict):
        return None
    shape = first.get("shape")
    return shape if isinstance(shape, str) else None


def _comparison_shape(outputs: dict[str, list[dict]]) -> str | None:
    """Return the shape tag of a comparison result, or None if the outputs
    are not a comparison.

    The comparison tools each stamp their result with a 'shape'; the
    executor wraps it in a one-element list under 'comparison' (the step's
    output_name). Mirrors _aggregation_shape."""
    bucket = outputs.get("comparison")
    if not bucket:
        return None
    first = bucket[0]
    if not isinstance(first, dict):
        return None
    shape = first.get("shape")
    return shape if isinstance(shape, str) else None


# ─────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────


class HallucinationError(RuntimeError):
    """The LLM produced structured output containing IDs that don't
    appear in the executor's source data. The message names the
    offending IDs so the gap is actionable."""


class UnsupportedEntityError(RuntimeError):
    """The Intent's target_entity has no synthesizer schema. Loud by
    design — graceful user-facing messaging is feature 8's job."""


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
    }


# ─────────────────────────────────────────────────────────────────────
# Prompt building
# ─────────────────────────────────────────────────────────────────────


_SYSTEM_PROMPT_PREAMBLE = (
    "You are a response synthesizer for an Oracle Fusion Cloud query "
    "assistant. You are given the structured output of a deterministic "
    "data-fetch pipeline (a dict of named result buckets). Produce a "
    "clear, concise answer of what the data shows.\n\n"
    "Rules you MUST follow for every response:\n"
    "- Only reference IDs (SupplierId, SupplierNumber, PersonId/BuyerId, "
    "InvoiceId) that appear in the data given to you. Do NOT invent IDs.\n"
    "- Do not add details not in the data (invented addresses, amounts, "
    "dates, emails).\n"
    "- Keep the summary to 3-5 sentences. Plain English. No marketing "
    "language.\n"
    "- If the final set is empty, say so plainly and return an empty "
    "records list.\n"
    "- If the input includes a 'truncation' block, populate "
    "truncation_notes with one note per entry: the step's output_name, "
    "the total_available count (or 'unknown' if null), and how many "
    "records were examined. Example: 'us_suppliers: 137 total in source; "
    "25 examined for filtering.' Copy numbers from the truncation block; "
    "never invent them. If no truncation block, return an empty list.\n\n"
)

# Per-entity instruction block, appended to the preamble.
_SYSTEM_PROMPT_BY_ENTITY: dict[str, str] = {
    "Supplier": (
        "This is a SUPPLIER-rooted query. For each supplier in the final "
        "filtered set, emit one entry under 'suppliers'. "
        "ONLY IF an open_pos bucket is present in the data: set "
        "open_po_count to the exact count of that supplier's POs in it, and "
        "list each unique buyer assigned to those POs (each buyer's "
        "person_id must appear in the buyers bucket). If there is NO "
        "open_pos bucket, leave open_po_count null and buyers empty, and do "
        "not mention purchase orders or buyers in the summary at all — the "
        "question did not ask about them. "
        "If a supplier record carries an 'addresses' list (the query asked "
        "for supplier addresses), emit each one under that supplier's "
        "'addresses' with its address_id and the country, city, state, and "
        "formatted_address when present; each address_id must appear in the "
        "data. If a supplier has no addresses field, leave its 'addresses' "
        "empty. "
        "If the data has a 'contact' bucket (the query asked for the "
        "supplier's contacts), emit each contact under that supplier's "
        "'contacts' with its supplier_contact_id, contact_name, and the "
        "email, job_title and is_administrative flag when present; each "
        "supplier_contact_id must appear in the data. When contacts are "
        "present, the summary MUST say how many there are and name the "
        "administrative contact if one is flagged."
    ),
    "Invoice": (
        "This is an INVOICE-rooted query. For each invoice in the final "
        "set, emit one entry under 'invoices' with its id, number, date, "
        "amount, currency, and the supplier name/number. supplier_number "
        "must appear in the data. Do not group or aggregate; list the "
        "invoices as returned."
    ),
    "Address": (
        "This is an ADDRESS-rooted query. For each address in the final "
        "set, emit one entry under 'addresses' with its address_id, the "
        "parent supplier's name and number, and the country, city, state, "
        "and formatted_address when present. address_id and supplier_number "
        "must appear in the data. Do not group or aggregate; list the "
        "addresses as returned."
    ),
    "PurchaseOrder": (
        "This is a PURCHASE-ORDER-rooted query. For each PO in the final "
        "set, emit one entry under 'purchase_orders' with its header id, "
        "order number, status, and supplier name/id. supplier_id must "
        "appear in the data.\n"
        "BUYER: a PO row usually carries Buyer (a name) and BuyerId "
        "directly — when it does, emit that as the buyer, using BuyerId as "
        "person_id and Buyer as display_name. A separate 'buyers' bucket "
        "may ALSO be present (when the query walked the buyer edge); "
        "either source is valid. Only say a PO has no buyer when BOTH the "
        "PO row's Buyer/BuyerId are absent AND there is no matching buyers "
        "entry — do not report 'no buyer' merely because there is no "
        "buyers bucket. The person_id must appear somewhere in the data.\n"
        "CHILD DETAIL — the question asked for it if the bucket is there, so "
        "the summary MUST describe it, not just the PO header:\n"
        "- 'purchaseorderline' bucket: emit each line under that PO's "
        "'lines' (po_line_id, line_number, description, category, quantity, "
        "amount). The summary must say how many lines and what they are for.\n"
        "- 'poschedule' bucket: emit each schedule under 'schedules' "
        "(line_location_id, schedule_number, ship_to_location, "
        "requested_delivery_date, and the ordered/received/billed quantities "
        "and amounts). The summary must state ship-to and need-by, and — "
        "when received or billed figures are present — state received "
        "against ordered as plain counts, e.g. '1 of 1 received; 33000 of "
        "33000 billed'. COPY these numbers exactly as given. Do NOT compute "
        "percentages, deltas, or any other arithmetic.\n"
        "- 'podistribution' bucket: emit each distribution under "
        "'distributions' (po_distribution_id, distribution_number, the "
        "charge/accrual/variance accounts, percentage, amount). The summary "
        "must name the charge account(s) the PO is booked to.\n"
        "Every po_line_id, line_location_id and po_distribution_id must "
        "appear in the data. If a bucket is absent, leave that list empty "
        "and do not mention it."
    ),
    "ReceivablesInvoice": (
        "This is an AR-INVOICE-rooted query (accounts receivable, "
        "sell-side). For each invoice in the final set, emit one entry under "
        "'receivables_invoices' with its customer_transaction_id, "
        "transaction_number, bill_to_customer_name, status, currency, "
        "amount (EnteredAmount), and balance (InvoiceBalanceAmount). "
        "customer_transaction_id must appear in the data.\n"
        "CHILD DETAIL — the question asked for it if the bucket is there, so "
        "the summary MUST describe it, not just the invoice header:\n"
        "- 'receivablesinvoiceline' bucket: emit each line under that "
        "invoice's 'lines' (customer_transaction_line_id, line_number, "
        "description, quantity, unit_selling_price, amount). The summary "
        "must say how many lines and what they are for. COPY the amounts "
        "exactly as given. Do NOT compute totals, tax, or any arithmetic.\n"
        "Every customer_transaction_line_id must appear in the data. If the "
        "bucket is absent, leave 'lines' empty and do not mention it."
    ),
    "CustomerAccount": (
        "This is a CUSTOMER-ACCOUNT-rooted query (accounts receivable). The "
        "customer was resolved to their account(s); for each account in the "
        "final set, emit one entry under 'customer_accounts' with its "
        "account_id, account_number, customer_name, and open_receivables "
        "(TotalOpenReceivablesForAccount). account_id must appear in the "
        "data.\n"
        "CHILD DETAIL — the question asked for the customer's invoices if "
        "the bucket is there, so the summary MUST describe them, not just "
        "the account:\n"
        "- 'customertransaction' bucket: emit each transaction under that "
        "account's 'transactions' (transaction_id, transaction_number, "
        "transaction_class, transaction_date, amount, balance, status). The "
        "summary must say how many invoices and, where useful, their total "
        "value — but COPY amounts exactly as given; do NOT compute sums, "
        "tax, or any arithmetic. Every transaction_id must appear in the "
        "data. If the bucket is absent, leave 'transactions' empty and do "
        "not mention it."
    ),
    "SupplierSpendRanking": (
        "This is a SUPPLIER SPEND RANKING (an aggregation). The data has a "
        "single 'aggregation' bucket containing one ranking object with a "
        "'rows' list, already sorted by total spend (highest first). For "
        "each row, emit one entry under 'suppliers' in the SAME order, "
        "copying supplier_name, supplier_number, total_spend, and "
        "invoice_count EXACTLY. Do not reorder, recompute, add, or drop "
        "suppliers, and do not do any arithmetic — the totals are already "
        "computed. In the summary, state the date range (from date_from/"
        "date_to), how many suppliers were ranked (total_suppliers), and "
        "name the top one or two with their totals. If 'truncated' is true, "
        "say plainly that the totals are based on a sample of invoices and "
        "may understate actual spend."
    ),
    "SupplierPOValueRanking": (
        "This is a SUPPLIER PO-VALUE RANKING (an aggregation). The data has "
        "a single 'aggregation' bucket containing one ranking object with a "
        "'rows' list, already sorted by committed value (highest first). For "
        "each row, emit one entry under 'suppliers' in the SAME order, "
        "copying supplier (as supplier_name), supplier_id, total_ordered and "
        "po_count EXACTLY. Note these carry supplier_ID, not supplier_number "
        "— purchase orders do not have a supplier number. Do not reorder, "
        "recompute, add, or drop suppliers, and do no arithmetic — the "
        "totals are already computed. In the summary, say how many suppliers "
        "were ranked (total_suppliers), name the top one or two with their "
        "committed values, and state the status filter if 'status' is set "
        "(e.g. 'open POs only'). If 'truncated' is true, say plainly that "
        "the totals are based on a sample of purchase orders and may "
        "understate the true committed value."
    ),
    "POStatusBreakdown": (
        "This is a PO STATUS BREAKDOWN (an aggregation). The data has a "
        "single 'aggregation' bucket containing one object with a 'rows' "
        "list, already sorted by value (highest first), plus total_pos and "
        "total_ordered grand figures. Copy total_pos and total_ordered "
        "EXACTLY into the response. For each row, emit one entry under "
        "'statuses' in the SAME order, copying status, po_count and "
        "total_ordered EXACTLY. Do not reorder, recompute, add, drop, or "
        "MERGE statuses — 'CLOSED', 'CLOSED FOR RECEIVING' and 'CLOSED FOR "
        "INVOICING' are genuinely different states and must stay separate. "
        "Do no arithmetic. In the summary, state the grand total count and "
        "value, then the two or three largest statuses by value. If "
        "'truncated' is true, say plainly that the figures cover only the "
        "purchase orders examined."
    ),
    "OpenPOSummary": (
        "This is an OPEN-PO SUMMARY (an aggregation). The data has a single "
        "'aggregation' bucket containing one object with po_count, "
        "total_ordered and supplier_count. Copy all three EXACTLY into the "
        "response and do no arithmetic. In the summary, state the committed "
        "value, how many open purchase orders it spans, and across how many "
        "suppliers. If 'truncated' is true, say plainly that the figures "
        "cover only the purchase orders examined."
    ),
}


def _build_system_prompt(target_entity: str) -> str:
    """Preamble + the per-entity instruction block."""
    block = _SYSTEM_PROMPT_BY_ENTITY[target_entity]
    return _SYSTEM_PROMPT_PREAMBLE + block


def _build_synthesis_prompt(
    outputs: dict[str, list[dict]],
    truncation_by_step: dict[str, dict] | None = None,
) -> str:
    """Build the user-message portion of the prompt: outputs as JSON,
    plus an optional truncation block."""
    rendered = json.dumps(outputs, default=str, indent=2)
    parts = [
        "Here is the executor's output. Each top-level key is the "
        "output_name of a step; each value is a list of records returned "
        f"by that step.\n\n```json\n{rendered}\n```\n"
    ]
    if truncation_by_step:
        truncation_rendered = json.dumps(truncation_by_step, default=str, indent=2)
        parts.append(
            "\nThe following steps were truncated. Each entry tells you how "
            "many records actually match in the source vs. how many were "
            "examined. Populate truncation_notes from this block; do NOT "
            f"invent counts.\n\n```json\n{truncation_rendered}\n```\n"
        )
    parts.append(
        "\nProduce the structured response per the schema. Remember: only "
        "reference IDs present in the data above; do not invent."
    )
    return "".join(parts)


# ─────────────────────────────────────────────────────────────────────
# Hallucination validation — dispatched per response type
# ─────────────────────────────────────────────────────────────────────


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
    parts = []
    if bad_acct:
        parts.append(f"customer_account_ids={bad_acct}")
    if bad_txn:
        parts.append(f"customer_account_transaction_ids={bad_txn}")
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


_VALIDATORS = {
    SupplierResponse: _validate_supplier,
    InvoiceResponse: _validate_invoice,
    AddressResponse: _validate_address,
    PurchaseOrderResponse: _validate_purchase_order,
    ReceivablesInvoiceResponse: _validate_receivables_invoice,
    CustomerAccountResponse: _validate_customer_account,
    SupplierSpendRankingResponse: _validate_supplier_spend_ranking,
    SupplierPOValueRankingResponse: _validate_supplier_po_value_ranking,
    POStatusBreakdownResponse: _validate_no_ids,
    OpenPOSummaryResponse: _validate_no_ids,
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


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────


def _build_count_response(
    outputs: dict[str, list[dict]],
    target_entity: str,
    truncation_by_step: dict[str, dict] | None,
) -> CountResponse:
    """Build a count response deterministically — no LLM (Phase 10).

    Count source, in order of preference:
      1. A truncation entry's total_available (authoritative; e.g. the
         unfiltered totalResults count, or the exact filtered total).
      2. If truncation says total_available is null, the true count is not
         known — a client-side filter exceeded the examine cap. Report the
         examined count as a lower bound.
      3. No truncation block: every matching record was returned, so the
         length of the single output bucket is the exact count.
    """
    # The count query runs one fetch → one output bucket.
    bucket = next(iter(outputs.values()), [])
    examined = len(bucket)

    total_available = None
    examined_note = examined
    if truncation_by_step:
        entry = next(iter(truncation_by_step.values()), {})
        total_available = entry.get("total_available")
        examined_note = entry.get("examined", examined)

    if total_available is not None:
        count = int(total_available)
        exact = True
        summary = f"There are {count} {target_entity.lower()}s."
    elif truncation_by_step:
        # total known-unknown: filter exceeded the cap. Lower bound only.
        count = int(examined_note)
        exact = False
        summary = (
            f"There are more than {count} {target_entity.lower()}s — the "
            f"exact total was not retrieved (more than the examine cap "
            f"matched)."
        )
    else:
        # No truncation: complete set returned.
        count = examined
        exact = True
        summary = f"There are {count} {target_entity.lower()}s."

    return CountResponse(
        summary=summary,
        entity=target_entity,
        count=count,
        count_is_exact=exact,
    )


# ─────────────────────────────────────────────────────────────────────
# Comparison responses (P6c) — deterministic, no LLM
# ─────────────────────────────────────────────────────────────────────
#
# The comparison tool has already done the fetch, join, and arithmetic.
# These builders template its numbers into prose; they never recompute a
# figure. Mirrors _build_count_response. The over/under-invoiced phrasing
# is neutral and factual (an over-invoice is real data — tax, freight,
# variance — not an error), matching the tool's own stance.


def _direction_phrase(difference: float) -> str:
    """Neutral over/under/fully phrasing for a signed difference."""
    if difference > 0:
        return f"over-invoiced by {difference:,.2f}"
    if difference < 0:
        return f"under-invoiced by {abs(difference):,.2f}"
    return "fully invoiced (invoiced equals ordered)"


def _summarize_po_comparison(data: dict) -> str:
    if not data.get("found"):
        return (
            f"No purchase order {data.get('order_number')!r} was found, so "
            f"there is nothing to compare."
        )
    ordered = data.get("ordered", 0.0)
    invoiced = data.get("invoiced", 0.0)
    diff = data.get("difference", 0.0)
    n = data.get("invoice_count", 0)
    supplier = data.get("supplier")
    inv_word = "invoice" if n == 1 else "invoices"
    return (
        f"PO {data.get('order_number')} ({supplier}): ordered {ordered:,.2f}, "
        f"invoiced {invoiced:,.2f} across {n} {inv_word} — "
        f"{_direction_phrase(diff)}."
    )


def _summarize_supplier_comparison(data: dict) -> str:
    if not data.get("found"):
        return (
            f"No supplier matching {data.get('supplier_name')!r} was found, "
            f"so there is nothing to compare."
        )
    if data.get("ambiguous"):
        candidates = data.get("candidates", [])
        shown = ", ".join(str(c) for c in candidates)
        return (
            f"{data.get('supplier_name')!r} matches several suppliers "
            f"({shown}). Name one exactly to compare its orders to invoices."
        )
    ordered = data.get("total_ordered", 0.0)
    invoiced = data.get("total_invoiced", 0.0)
    diff = data.get("total_difference", 0.0)
    po_count = data.get("po_count", 0)
    unmatched = data.get("unmatched_invoice_count", 0)
    parts = [
        f"{data.get('supplier')}: across {po_count} purchase order(s), "
        f"ordered {ordered:,.2f} and PO-matched invoiced {invoiced:,.2f} — "
        f"{_direction_phrase(diff)}."
    ]
    if unmatched:
        parts.append(
            f"{unmatched:,} of this supplier's invoices were not linked to a "
            f"PO and are excluded from the comparison."
        )
    return " ".join(parts)


def _summarize_top_suppliers_comparison(data: dict) -> str:
    suppliers = data.get("suppliers", [])
    returned = data.get("returned", len(suppliers))
    if not suppliers:
        return "No suppliers were found to compare."
    lines = [
        f"Invoiced vs ordered for the top {returned} supplier(s) by PO value:"
    ]
    for s in suppliers:
        ordered = s.get("total_ordered", 0.0)
        invoiced = s.get("total_invoiced", 0.0)
        diff = s.get("total_difference", 0.0)
        unmatched = s.get("unmatched_invoice_count", 0)
        line = (
            f"- {s.get('supplier')}: ordered {ordered:,.2f}, PO-matched "
            f"invoiced {invoiced:,.2f} — {_direction_phrase(diff)}"
        )
        if unmatched:
            line += f" ({unmatched:,} non-PO invoices excluded)"
        line += "."
        lines.append(line)
    return "\n".join(lines)


# shape tag -> builder. One row per shape, like AGGREGATION_SCHEMAS: a new
# comparison tool is a new row here, not another branch in the routing.
_COMPARISON_BUILDERS = {
    "po_invoiced_vs_ordered": _summarize_po_comparison,
    "supplier_invoiced_vs_ordered": _summarize_supplier_comparison,
    "top_suppliers_invoiced_vs_ordered": _summarize_top_suppliers_comparison,
}


def _build_comparison_response(
    outputs: dict[str, list[dict]], shape: str
) -> ComparisonResponse:
    """Build a comparison response deterministically from the tool's data.

    The comparison tool result sits under the 'comparison' bucket as a
    single object. The builder for its shape templates the summary; no LLM
    and no recomputation.
    """
    data = outputs["comparison"][0]
    builder = _COMPARISON_BUILDERS.get(shape)
    if builder is None:
        raise UnsupportedEntityError(
            f"No synthesizer builder for comparison shape {shape!r}. "
            f"Supported: {sorted(_COMPARISON_BUILDERS)}."
        )
    truncation_notes = (
        ["Some results were truncated at the page cap."]
        if data.get("truncated")
        else []
    )
    return ComparisonResponse(
        summary=builder(data),
        shape=shape,
        truncation_notes=truncation_notes,
    )


def synthesize_response(
    outputs: dict[str, list[dict]],
    target_entity: str,
    llm: Any | None = None,
    truncation_by_step: dict[str, dict] | None = None,
    count_only: bool = False,
) -> BaseModel:
    """Turn the executor's output into a validated structured response,
    using the schema for the Intent's target_entity.

    Args:
        outputs: The dict returned by spire.executor.execute_plan.
        target_entity: The Intent's target_entity ("Supplier", "Invoice",
            or "PurchaseOrder"). Selects the response schema.
        llm: Optional pre-built LangChain LLM. Tests inject a mock;
            production passes None and a fresh ChatGoogleGenerativeAI is
            built (reads GEMINI_API_KEY from the environment).
        truncation_by_step: Optional dict from execute_plan keyed by
            output_name. When present, the LLM populates truncation_notes.

    Returns:
        A Pydantic model — SupplierResponse, InvoiceResponse, or
        PurchaseOrderResponse depending on target_entity.

    Raises:
        UnsupportedEntityError if target_entity has no schema.
        HallucinationError if any structured ID isn't in the executor data.
        Pydantic ValidationError if the LLM output doesn't fit the schema.
        Anything raised by the LLM call propagates.
    """
    # Phase 10: a count query needs no LLM — the count is already in the
    # executor output / truncation block. Build it deterministically.
    if count_only:
        return _build_count_response(outputs, target_entity, truncation_by_step)

    # P6c: a comparison produces an invoiced-vs-ordered result, not an
    # entity list. Like aggregation it has no target_entity (the Intent
    # carried a compare block); select by the shape the tool stamped under
    # the "comparison" bucket. Built deterministically — the tool already
    # computed every number — so this returns before any LLM setup.
    comparison_shape = _comparison_shape(outputs)
    if comparison_shape is not None:
        return _build_comparison_response(outputs, comparison_shape)

    # Feature 7: an aggregation produces a ranking, not an entity list.
    # It has no target_entity (the Intent carried an aggregate block
    # instead), so select the schema from the data shape. The executor
    # places the ranking under "aggregation" as a single object whose
    # "shape" identifies it.
    shape = _aggregation_shape(outputs)
    if shape is not None:
        entry = AGGREGATION_SCHEMAS.get(shape)
        if entry is None:
            raise UnsupportedEntityError(
                f"No synthesizer schema for aggregation shape {shape!r}. "
                f"Supported: {sorted(AGGREGATION_SCHEMAS)}."
            )
        schema: type[BaseModel] = entry[0]
        prompt_key = entry[1]
    else:
        schema = SYNTHESIS_SCHEMAS.get(target_entity)
        if schema is None:
            raise UnsupportedEntityError(
                f"No synthesizer schema for target_entity={target_entity!r}. "
                f"Supported: {sorted(SYNTHESIS_SCHEMAS)}."
            )
        prompt_key = target_entity

    if llm is None:
        from spire.config import build_llm

        llm = build_llm(_TEMPERATURE)

    structured_llm = llm.with_structured_output(schema, include_raw=True)
    system_prompt = _build_system_prompt(prompt_key)
    user_message = _build_synthesis_prompt(outputs, truncation_by_step)

    result = structured_llm.invoke(
        [("system", system_prompt), ("human", user_message)]
    )

    # With include_raw=True the real LLM returns
    # {"raw": AIMessage, "parsed": schema, "parsing_error": ...}. Unit
    # tests inject a mock returning the bare model (or a dict); handle
    # both so token logging never breaks the mock path.
    if isinstance(result, dict) and "parsed" in result:
        from spire.config import log_usage

        log_usage(result.get("raw"), stage="synthesize")
        response = result["parsed"]
    else:
        response = result

    if isinstance(response, dict):
        response = schema(**response)

    _validate_no_hallucinated_ids(response, outputs)
    return response









