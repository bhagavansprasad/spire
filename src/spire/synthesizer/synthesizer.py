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
from decimal import Decimal
import sys
from typing import Any

from pydantic import BaseModel, Field

from spire.config import GEMINI_MODEL, GEMINI_TEMPERATURE, LLM_MAX_OUTPUT_TOKENS


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
    "Do not invent specifics not in the data. If truncation_notes is "
    "non-empty this summary MUST say the result is partial and give the "
    "total from the truncation block — the count of rows shown is NOT the "
    "number that exist."
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


class ReceivablesTaxLineInfo(BaseModel):
    """One tax line nested under an AR invoice line.

    customer_transaction_line_id here is the TAX line's own PK (e.g. 112) —
    a different value from the parent invoice line's id. It is validated
    against the executor's output after synthesis; it MUST appear there."""

    customer_transaction_line_id: int = Field(
        description="The tax line's own CustomerTransactionLineId (numeric "
        "key — the TAX line PK, not the parent line's). Must appear in the "
        "data."
    )
    tax_line_number: int = Field(
        description="The tax line number within the invoice line."
    )
    tax: str = Field(
        default="", description="The tax type (e.g. 'STATE', 'COUNTY')."
    )
    tax_rate: float | None = Field(
        default=None, description="The tax rate percentage (e.g. 6.5)."
    )
    tax_amount: float | None = Field(
        default=None, description="The tax amount charged for this tax line."
    )
    taxable_amount: float | None = Field(
        default=None, description="The amount the tax was computed on."
    )
    jurisdiction: str = Field(
        default="", description="The tax jurisdiction code."
    )


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
    tax_lines: list[ReceivablesTaxLineInfo] = Field(
        default_factory=list,
        description="This line's tax lines, when the query asked for them (a "
        "'receivablestaxline' bucket in the data). Empty otherwise. Each "
        "customer_transaction_line_id must appear in the executor's output.",
    )


class ReceivablesInvoiceTransactionDFFInfo(BaseModel):
    """The transaction descriptive flexfield (DFF) nested under an AR invoice.

    Carries only the DFF context name and its display value. No id of its own
    to validate — CustomerTrxId echoes the parent invoice — so this model is
    not hallucination-checked.
    """

    context: str = Field(
        default="",
        description="The DFF context name, __FLEX_Context (e.g. 'DOO'). "
        "Empty when no context is set.",
    )
    context_display_value: str = Field(
        default="",
        description="The DFF context display value, __FLEX_Context_DisplayValue "
        "(often null on this pod).",
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
    transaction_date: str = Field(
        default="",
        description="The invoice's TransactionDate, ISO format (e.g. "
        "'2012-03-21'). Copy it exactly from the data; do not reformat.",
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
        "'receivables_invoice_lines' bucket in the data). Empty otherwise. Each "
        "customer_transaction_line_id must appear in the executor's output.",
        )
    dff: ReceivablesInvoiceTransactionDFFInfo | None = Field(
        default=None,
        description="This invoice's transaction DFF, when the query asked for "
        "it (a 'receivablesinvoicetransactiondff' bucket in the data). None "
        "otherwise.",
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


class AccountCreditMemoInfo(BaseModel):
    """One credit memo on a customer account (AR-P5 prompt 7).

    NOT the same shape as CreditMemoRecord (AR-P4). That one describes the
    TOP-LEVEL receivablesCreditMemos resource and is keyed by
    CustomerTransactionId; this describes a single account's creditMemos
    child, keyed by CreditMemoId — a different id space entirely, with the
    installment projection (balance/available) rather than the transaction
    projection. credit_memo_id is validated against the executor's output.
    """

    credit_memo_id: int = Field(
        description="The memo's CreditMemoId (numeric PK). NOT a "
        "CustomerTransactionId — a different id space."
    )
    credit_memo_number: str = Field(
        default="", description="The credit memo number."
    )
    credit_memo_date: str = Field(
        default="", description="Credit memo date."
    )
    amount: float | None = Field(
        default=None,
        description="Original memo amount (TotalOriginalAmount). Normally "
        "negative. Copy it exactly as given; do NOT sum, negate or "
        "otherwise compute with it.",
    )
    balance: float | None = Field(
        default=None,
        description="Remaining balance (TotalBalanceAmount). Non-zero on "
        "Open memos, 0 on Closed ones.",
    )
    status: str = Field(
        default="", description="Memo status (Open or Closed)."
    )
    currency: str = Field(
        default="", description="Memo currency (e.g. USD)."
    )


class AccountReceiptInfo(BaseModel):
    """One standard receipt on a customer account (AR-P5 prompt 8).

    A receipt is CASH RECEIVED — a payment from the customer. Distinct
    from an AR invoice (money owed) and a credit memo (a credit issued).
    receipt_id is validated against the executor's output.
    """

    receipt_id: int = Field(
        description="The receipt's StandardReceiptId (numeric PK). NOTE "
        "this collection MIXES id widths — backfilled rows carry small "
        "ints, recent ones large. Copy it exactly; never reformat or "
        "truncate it."
    )
    receipt_number: str = Field(
        default="", description="The receipt number."
    )
    receipt_date: str = Field(
        default="", description="Receipt date."
    )
    amount: float | None = Field(
        default=None,
        description="Receipt amount, i.e. cash received. Positive. Copy "
        "it exactly as given; do NOT sum or otherwise compute with it.",
    )
    currency: str = Field(
        default="", description="Receipt currency (e.g. USD)."
    )
    receipt_method: str = Field(
        default="",
        description="How the payment arrived (e.g. Lockbox, Check).",
    )
    state: str = Field(
        default="",
        description="Application state — 'Applied' or 'Unapplied'. "
        "Unapplied means cash received but not yet matched to an "
        "invoice. That is normal and is real money; do NOT describe an "
        "Unapplied receipt as missing, pending, failed or in error.",
    )
    unapplied_amount: float | None = Field(
        default=None,
        description="Portion not yet applied to a transaction. 0 on "
        "fully applied receipts.",
    )


class AccountReceiptApplicationInfo(BaseModel):
    """One receipt application on a customer account (AR-P5 prompt 9).

    A receipt application is the matching of a receipt (cash received) to an
    invoice (money owed). Each row is PRE-JOINED: it carries the receipt side
    and the transaction side on one record. application_id is validated against
    the executor's output.
    """

    application_id: int = Field(
        description="The application's ApplicationId (numeric PK)."
    )
    receipt_id: int = Field(
        description="The receipt's StandardReceiptId (numeric)."
    )
    receipt_number: str = Field(
        default="", description="The receipt number."
    )
    receipt_method: str = Field(
        default="", description="How the payment arrived (e.g. Lockbox)."
    )
    transaction_id: int | None = Field(
        default=None,
        description="The transaction's ReferenceTransactionId (the payment "
        "schedule id, a small int). Null only when unapplied, but we filter "
        "those out, so this is always populated.",
    )
    transaction_number: str = Field(
        default="", description="The transaction number."
    )
    transaction_status: str = Field(
        default="", description="Transaction status (e.g. Open, Closed)."
    )
    application_amount: float = Field(
        description="The amount applied to the transaction."
    )
    application_date: str = Field(
        default="", description="Application date."
    )
    currency: str = Field(
        default="", description="Application currency (EnteredCurrency)."
    )

class StandardReceiptRecord(BaseModel):
    """One standard receipt in a top-level StandardReceipt-rooted response (Prompt 13).

    This is the top-level /standardReceipts projection, which includes CustomerName,
    CustomerAccountNumber, and bank fields. Distinct from AccountReceipt (the
    per-account child) which has ProcessStatus and omits these fields.
    """

    standard_receipt_id: int = Field(
        description="The receipt's StandardReceiptId (numeric PK)."
    )
    receipt_number: str = Field(
        default="", description="Human-readable receipt number."
    )
    receipt_date: str = Field(
        default="", description="Receipt date."
    )
    amount: float | None = Field(
        default=None, description="Receipt amount (cash received)."
    )
    currency: str = Field(
        default="", description="Receipt currency (e.g. USD)."
    )
    receipt_method: str = Field(
        default="", description="How the payment arrived (e.g. Lockbox, Check)."
    )
    status: str = Field(
        default="", description="Top-level status (Cleared, etc.)."
    )
    customer_name: str = Field(
        default="", description="Customer display name."
    )
    customer_account_number: str = Field(
        default="", description="Customer account number."
    )
    customer_site: str = Field(
        default="", description="Customer site (e.g. Santa Clara)."
    )
    remittance_bank_name: str = Field(
        default="", description="Remittance bank name."
    )
    remittance_bank_branch: str = Field(
        default="", description="Remittance bank branch."
    )
    remittance_bank_account_number: str = Field(
        default="", description="Remittance bank account number."
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
    transactions_due: float | None = Field(
        default=None,
        description="Total transactions due for the account "
        "(TotalTransactionsDueForAccount). Copy it exactly as given; do "
        "NOT compute or reconcile it against open_receivables — the two "
        "are separate figures on the account record and need not agree.",
    )
    transactions: list[CustomerAccountTransactionInfo] = Field(
        default_factory=list,
        description="This account's transactions, when the query asked for "
        "them (a 'customertransaction' bucket in the data). Empty "
        "otherwise. Each transaction_id must appear in the executor's "
        "output.",
    )
    credit_memos: list[AccountCreditMemoInfo] = Field(
        default_factory=list,
        description="This account's credit memos, when the query asked for "
        "them (an 'accountcreditmemo' bucket in the data). Empty "
        "otherwise. Each credit_memo_id must appear in the executor's "
        "output.",
    )
    receipts: list[AccountReceiptInfo] = Field(
        default_factory=list,
        description="This account's receipts (cash received), when the "
        "query asked for them (an 'accountreceipt' bucket in the data). "
        "Empty otherwise. Each receipt_id must appear in the executor's "
        "output.",
    )
    applications: list[AccountReceiptApplicationInfo] = Field(
        default_factory=list,
        description="This account's receipt applications, when the query asked for "
        "them (an 'account_receipt_applications' bucket in the data). Empty "
        "otherwise. Each application_id must appear in the executor's output.",
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

class StandardReceiptResponse(BaseModel):
    """StandardReceipt-rooted synthesized response (Prompt 13)."""

    summary: str = _SUMMARY_FIELD
    standard_receipts: list[StandardReceiptRecord] = Field(
        default_factory=list,
        description="One entry per standard receipt in the final set. "
        "Empty if none.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD

class CreditMemoRecord(BaseModel):
    """One credit memo in a credit-memo-rooted response."""

    customer_transaction_id: int = Field(
        description="The credit memo's CustomerTransactionId (system id)."
    )
    transaction_number: str = Field(
        description="The credit memo's TransactionNumber (human-readable)."
    )
    transaction_date: str = Field(
        default="", description="Credit memo date (TransactionDate)."
    )
    entered_amount: float = Field(
        description="Credit memo amount (EnteredAmount; normally negative)."
    )
    currency: str = Field(
        default="", description="Credit memo currency (CreditMemoCurrency)."
    )
    status: str = Field(
        default="", description="Credit memo status (CreditMemoStatus)."
    )
    customer_name: str = Field(
        default="", description="Bill-to customer name (BillToCustomerName)."
    )
    customer_number: str = Field(
        default="", description="Bill-to customer number (BillToCustomerNumber)."
    )


class CreditMemoListResponse(BaseModel):
    """Credit-memo-rooted synthesized response: a list plus the total.

    The executor returns credit memos under the 'credit_memos' bucket, each
    carrying a top-level 'total_credit' the wrapper computed. This response
    surfaces both.
    """

    summary: str = _SUMMARY_FIELD
    credit_memos: list[CreditMemoRecord] = Field(
        default_factory=list,
        description="Credit memos in date-descending (recent-first) order. "
        "Empty if none exist.",
    )
    total_credit: float | None = Field(
        default=None,
        description="Total credit value: the ledger sum of EnteredAmount "
        "across the listed memos, copied from the executor's total_credit. "
        "Do NOT recompute it. NULL when the memos span more than one "
        "currency — there is no single total to give, and inventing one "
        "would be a figure in no currency at all. When this is null, "
        "total_credit_note says why.",
    )
    total_credit_note: str | None = Field(
        default=None,
        description="Why no total was given, copied verbatim from the "
        "executor's total_credit_note. Null whenever total_credit has a "
        "value. Exactly one of the two is ever set.",
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

class ExposureRankingRow(BaseModel):
    """One account in an exposure ranking."""

    account_id: int = Field(description="The account's AccountId.")
    account_number: str = Field(description="The account's AccountNumber.")
    customer_name: str = Field(description="The customer's display name.")
    open_receivables: float | None = Field(default=None, description="Total open receivables for the account.")
    transactions_due: float | None = Field(default=None, description="Total transactions due for the account.")


class ExposureRankingResponse(BaseModel):
    """Aggregation response: customer accounts ranked by outstanding exposure."""

    summary: str = _SUMMARY_FIELD
    accounts: list[ExposureRankingRow] = Field(
        default_factory=list,
        description="Accounts in ranked order (highest exposure first), copied "
        "from the ranking data. Do not reorder, add, or drop.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD

class ReceiptMethodDistributionRow(BaseModel):
    """One receipt method bucket in a distribution."""

    receipt_method: str = Field(description="The receipt method (e.g. Lockbox, Check).")
    receipt_count: int = Field(description="Number of receipts using this method.")
    total_amount: float = Field(description="Total amount for this method.")


class ReceiptMethodDistributionResponse(BaseModel):
    """Aggregation response: receipts grouped by receipt method."""

    summary: str = _SUMMARY_FIELD
    total_receipts: int = Field(description="Total number of receipts examined.")
    total_amount: float = Field(description="Total amount across all receipts.")
    methods: list[ReceiptMethodDistributionRow] = Field(
        default_factory=list,
        description="One row per method, sorted by total_amount descending.",
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
    "CreditMemo": CreditMemoListResponse,
    "StandardReceipt": StandardReceiptResponse,
}


# Aggregation responses are selected by the SHAPE TAG the tool stamps on
# its result, not by target_entity (an aggregation Intent carries an
# aggregate block instead of a target entity). The executor puts that
# result under the "aggregation" bucket. Mirrors SYNTHESIS_SCHEMAS above:
# one entry per shape, so a new aggregation tool is a new row here rather
# than another branch in the routing.
# ─────────────────────────────────────────────────────────────────────
# Module 5 — PO lifecycle
#
# ONE response for five catalog prompts (A.2, A.3, A.4, A.7, A.10). They
# ask for the same DATA and differ only in emphasis: is it done, why is
# it stuck, should I care. Choosing emphasis from a question is what a
# language model is for; three schemas would triple the five-place work
# and need a routing signal the parser does not emit.
#
# EVERY NUMBER AND EVERY JUDGEMENT IS COPIED, NEVER DERIVED. risk,
# risk_reasons, recommended_action, lifecycle_stage and responsible_team
# are all computed in the tool precisely so they are reproducible and
# auditable. A model that re-derives them produces a different answer to
# the same question on a different day.
# ─────────────────────────────────────────────────────────────────────

LIFECYCLE_SHAPE = "po_lifecycle_status"


class POLifecycleLeg(BaseModel):
    """One leg of the ordered -> received -> invoiced -> paid chain."""

    name: str = Field(
        description="The leg: 'Ordered', 'Received', 'Invoiced' or 'Paid'."
    )
    amount: float | None = Field(
        default=None,
        description="The amount for this leg, copied exactly. NULL for the "
        "paid leg when paid_state is 'unknown' — do NOT substitute 0.",
    )
    remaining: float | None = Field(
        default=None,
        description="What is still outstanding on this leg, copied exactly. "
        "NULL when unknown — do NOT substitute 0.",
    )
    complete: bool | None = Field(
        default=None,
        description="Whether this leg is finished, copied from "
        "fully_received / fully_invoiced / fully_paid. NULL means UNKNOWN, "
        "not false — only the paid leg can be null.",
    )
    note: str | None = Field(
        default=None,
        description="One short clause if this leg needs qualifying — e.g. "
        "that received is derived from quantities, or that the paid leg "
        "cannot be determined. Otherwise null.",
    )


class POLifecycleScheduleRow(BaseModel):
    """One PO schedule line, copied from the schedules array."""

    line_number: int | None = Field(default=None, description="PO line number.")
    status: str | None = Field(default=None, description="Schedule status.")
    amount: float | None = Field(default=None, description="Ordered amount.")
    received_amount: float | None = Field(
        default=None, description="Received amount (DERIVED from quantity)."
    )
    outstanding_amount: float | None = Field(
        default=None, description="Ordered minus received."
    )


class POLifecycleResponse(BaseModel):
    """The lifecycle answer for ONE purchase order.

    Adapts to the question asked. A 'has it been paid' question leads with
    the legs; a 'why is it stuck' question leads with the blockage and the
    owner; a 'summarise this PO' question leads with value and risk. The
    FIELDS are the same either way — only the summary's emphasis moves.
    """

    summary: str = _SUMMARY_FIELD
    order_number: str = Field(
        description="The PO's OrderNumber, copied exactly from the data."
    )
    supplier: str | None = Field(
        default=None, description="Supplier name, copied from the data."
    )
    currency: str | None = Field(default=None, description="PO currency code.")
    legs: list[POLifecycleLeg] = Field(
        default_factory=list,
        description="The four legs in order: Ordered, Received, Invoiced, "
        "Paid. Always all four, even when a leg is unknown.",
    )
    lifecycle_stage: str = Field(
        description="Copied EXACTLY from lifecycle_stage. Do not reword."
    )
    responsible_team: str = Field(
        description="Copied EXACTLY from responsible_team. Do not reword, "
        "and do not decide the owner yourself."
    )
    risk: str = Field(
        description="Copied EXACTLY from risk — 'Low', 'Medium' or 'High'. "
        "NEVER assess the risk yourself; it is computed."
    )
    risk_reasons: list[str] = Field(
        default_factory=list,
        description="Copied from risk_reasons, in order. Do not add, drop "
        "or reword.",
    )
    recommended_action: str = Field(
        description="Copied EXACTLY from recommended_action. Do not invent "
        "an action, and do not soften or extend the one given."
    )
    setup_notes: list[str] = Field(
        default_factory=list,
        description="Supplier and site setup worth stating: status, spend "
        "authorization, site status, matching level, any hold. Copied from "
        "the setup block. Empty when nothing is notable.",
    )
    exceptions: list[str] = Field(
        default_factory=list,
        description="The unresolved findings, copied from notes. Keep each "
        "one's meaning intact — especially any labelled unconfirmed, which "
        "must stay labelled.",
    )
    schedules: list[POLifecycleScheduleRow] = Field(
        default_factory=list,
        description="Per-line detail, copied from the schedules array. "
        "Include when the question asks why the PO is open or which line "
        "is short; otherwise leave empty.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class POLifecycleSummaryResponse(BaseModel):
    """What the LLM is asked for on the lifecycle path: the summary only.

    Everything else in POLifecycleResponse is built by code from the
    record. A first attempt let the model fill the whole schema and it
    reported the paid leg as `amount=0.0` beside the note "cannot be
    determined" — faithfully copying the tool's `paid: 0.0` while
    destroying its meaning. A reader sees 0.00 and concludes nothing was
    paid, which is the exact assertion the tri-state exists to prevent.

    Same reasoning as build_supplier_records: a value copied by code
    cannot be misreported, so the failure mode is removed rather than
    guarded against. It also stops the model inventing fields the data
    does not have — the first run marked the Ordered leg complete=True,
    which no field says.
    """

    summary: str = _SUMMARY_FIELD
    truncation_notes: list[str] = _TRUNCATION_FIELD


def _build_lifecycle_legs(record: dict) -> list[POLifecycleLeg]:
    """The four legs, built from the record. Never from the model.

    The paid leg is the reason this function exists. When paid_state is
    'unknown' its amount is None — NOT the record's `paid` value, which
    is a legitimate 0.0 meaning "no payment has been observed" and reads
    in a table as "nothing was paid". Those are different statements and
    only one of them is true.
    """
    paid_state = record.get("paid_state")
    paid_unknown = paid_state == "unknown"

    received_note = None
    if record.get("received_is_derived"):
        received_note = "derived from quantity — the pod carries no received amount"

    paid_note = None
    if paid_unknown:
        paid_note = (
            "cannot be determined: the schedules record billing but no AP "
            "invoice carries this PO number"
        )
    elif paid_state == "nothing_due":
        paid_note = "nothing was billed, so nothing is due"

    return [
        POLifecycleLeg(
            name="Ordered",
            amount=record.get("ordered"),
            remaining=None,
            complete=None,
            note=None,
        ),
        POLifecycleLeg(
            name="Received",
            amount=record.get("received"),
            remaining=record.get("remaining_to_receive"),
            complete=record.get("fully_received"),
            note=received_note,
        ),
        POLifecycleLeg(
            name="Invoiced",
            amount=record.get("invoiced"),
            remaining=record.get("remaining_to_invoice"),
            complete=record.get("fully_invoiced"),
            note=None,
        ),
        POLifecycleLeg(
            # amount is None, not record["paid"], when the leg is unknown.
            name="Paid",
            amount=None if paid_unknown else record.get("paid"),
            remaining=record.get("remaining_to_pay"),
            complete=record.get("fully_paid"),
            note=paid_note,
        ),
    ]


def _build_lifecycle_setup_notes(record: dict) -> list[str]:
    """Supplier and site setup, phrased from the record. Deterministic.

    Reports what could not be read as unread, never as clean: an absent
    supplier record is unknown setup, not an active supplier.
    """
    setup = record.get("setup") or {}
    notes: list[str] = []

    if not setup.get("supplier_read"):
        notes.append("Supplier master could not be read.")
    else:
        bits = [f"Supplier {record.get('supplier')}"]
        if setup.get("supplier_number"):
            bits.append(f"({setup['supplier_number']})")
        bits.append(f"is {setup.get('supplier_status') or 'of unknown status'}")
        if setup.get("business_relationship"):
            bits.append(f"and {setup['business_relationship']}")
        notes.append(" ".join(bits) + ".")
        if setup.get("on_ofac_list"):
            notes.append("Supplier is flagged on the OFAC sanctions list.")

    if not setup.get("site_read"):
        notes.append("Supplier site could not be read.")
    else:
        notes.append(
            f"Site {record.get('supplier_site')} is "
            f"{setup.get('site_status') or 'of unknown status'}, "
            f"purchasing {'enabled' if setup.get('site_purchasing_enabled') else 'not enabled'}, "
            f"pay {'enabled' if setup.get('site_pay_enabled') else 'not enabled'}."
        )
        if setup.get("match_approval_level"):
            notes.append(
                f"Invoice matching is {setup['match_approval_level']} against "
                f"{setup.get('invoice_match_option') or 'an unspecified basis'}."
            )

    if record.get("payment_terms_overridden"):
        notes.append(
            f"PO payment terms ({record.get('payment_terms')}) differ from the "
            f"site default ({setup.get('site_payment_terms')})."
        )
    return notes


def build_lifecycle_response(
    record: dict, summary: str, truncation_notes: list[str]
) -> POLifecycleResponse:
    """Assemble the full lifecycle answer. Only `summary` comes from the LLM."""
    schedules = [
        POLifecycleScheduleRow(
            line_number=row.get("line_number"),
            status=row.get("status"),
            amount=row.get("amount"),
            received_amount=row.get("received_amount"),
            outstanding_amount=row.get("outstanding_amount"),
        )
        for row in (record.get("schedules") or [])
    ]
    return POLifecycleResponse(
        summary=summary,
        order_number=str(record.get("order_number") or ""),
        supplier=record.get("supplier"),
        currency=record.get("currency"),
        legs=_build_lifecycle_legs(record),
        lifecycle_stage=record.get("lifecycle_stage") or "",
        responsible_team=record.get("responsible_team") or "",
        risk=record.get("risk") or "",
        risk_reasons=list(record.get("risk_reasons") or []),
        recommended_action=record.get("recommended_action") or "",
        setup_notes=_build_lifecycle_setup_notes(record),
        exceptions=list(record.get("notes") or []),
        schedules=schedules,
        truncation_notes=truncation_notes,
    )


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
    "exposure_ranking": (ExposureRankingResponse, "ExposureRanking"),
    "receipt_method_distribution": (ReceiptMethodDistributionResponse, "ReceiptMethodDistribution"),
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


def _lifecycle_shape(outputs: dict[str, list[dict]]) -> dict | None:
    """Return the PO lifecycle record if the outputs carry one, else None.

    Unlike _aggregation_shape and _comparison_shape this scans EVERY
    bucket rather than one named one. The lifecycle step is an ordinary
    entity fetch, so the planner names its bucket after the step — there
    is no fixed "lifecycle" key to look under, and hardcoding a guess
    would break the first time a plan named it differently.
    """
    for bucket in outputs.values():
        if not bucket:
            continue
        first = bucket[0]
        if isinstance(first, dict) and first.get("shape") == LIFECYCLE_SHAPE:
            return first
    return None


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


class DegenerateOutputError(RuntimeError):
    """The LLM produced degenerate output (runaway tokens, empty child
    arrays despite source data, etc.). Raw text is saved to traces/."""


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


# ─────────────────────────────────────────────────────────────────────
# Prompt building
# ─────────────────────────────────────────────────────────────────────




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
    "- For any numeric value, copy it exactly as given in the data."
    "If the data shows a number with more than two decimal places, "
    "round it to two decimal places. Do NOT generate numbers with more"
    "than two decimal places.\n"
    "- If the input includes a 'truncation' block, populate "
    "truncation_notes with one note per entry: the step's output_name, "
    "the total_available count (or 'unknown' if null), and how many "
    "records were examined. Example: 'us_suppliers: 137 total in source; "
    "25 examined for filtering.' Copy numbers from the truncation block; "
    "never invent them. If no truncation block, return an empty list.\n"
    "- When there IS a truncation block, the SUMMARY must say so too, "
    "with the total: 'showing 25 of 2,111 credit memos'. Filling "
    "truncation_notes is not enough — a reader stops at the summary. "
    "A summary that says 'there are 25 credit memos' when 2,111 exist "
    "is wrong even with a correct note printed below it. Never state a "
    "count as the total when the data says otherwise.\n\n"
)

# Per-entity instruction block, appended to the preamble.
_SYSTEM_PROMPT_BY_ENTITY: dict[str, str] = {
    "POLifecycle": (
        "You are answering a question about ONE purchase order's journey "
        "from order to payment. The data is a single reconciliation record "
        "assembled from six Oracle Fusion resources.\n\n"
        "COPY, DO NOT COMPUTE. Every number, stage, team, risk rating and "
        "recommended action in the data was computed deterministically so "
        "that the same question always gets the same answer. Copy them "
        "exactly. Do NOT add up amounts yourself, do NOT decide who is "
        "responsible, and do NOT form your own view of the risk. If you "
        "disagree with a value, copy it anyway.\n\n"
        "THE PAID LEG CAN BE UNKNOWN. When paid_state is 'unknown', the "
        "schedules record billing but no accounts-payable invoice carries "
        "this PO number. That does NOT mean nothing is owed and it does "
        "NOT mean the supplier was paid. It means the bill cannot be "
        "found. Say so plainly. fully_paid and remaining_to_pay are null "
        "in that case: leave them null, never write 0, and never say the "
        "PO is unpaid or fully paid.\n\n"
        "RECEIVED IS DERIVED. The pod carries no received AMOUNT, only a "
        "received QUANTITY, so the received figure is prorated from it. "
        "When you state the received amount, say it is derived from "
        "quantity. Presenting it as a fetched figure is the exact error "
        "this system exists to avoid.\n\n"
        "YOU WRITE THE SUMMARY ONLY. Every other field is assembled from "
        "the record by code, so you cannot get a number wrong here — but "
        "you can get one wrong in the prose. Quote figures exactly as they "
        "appear.\n\n"
        "ANSWER THE QUESTION ASKED. The data is always the same; the "
        "emphasis is not.\n"
        "- 'has it been received / invoiced / paid', 'is it complete' — "
        "lead with the four legs and a direct yes or no per leg, using "
        "'cannot be determined' where a leg is unknown.\n"
        "- 'why is it still open', 'what is blocking it', 'who owns it' — "
        "lead with the stage, the responsible team and the exceptions, and "
        "include the per-line schedule detail so the short line is named.\n"
        "- 'summarise it', 'executive summary', 'from supplier setup "
        "through payment' — lead with supplier, value and risk, then the "
        "legs, then the recommended action.\n"
        "- 'what is the supplier / approval / matching / payment status' — "
        "walk the stages in order, including the setup notes.\n\n"
        "UNCONFIRMED STAYS UNCONFIRMED. Some notes carry an explicit "
        "hypothesis — for example that a PayOnReceipt flag may explain "
        "unmatched billing. Keep the hedge. Never promote a hypothesis to "
        "a cause, and never supply a cause of your own for a difference "
        "the data does not explain.\n\n"
        "Over-invoicing is not an error. An invoice above the order can be "
        "tax, freight or price variance. Report the difference; do not "
        "call it a problem and do not guess its cause."
    ),
    "SupplierSummaryOnly": (
        "This is a SUPPLIER LIST. Write ONLY the summary and the "
        "truncation notes — the supplier records are built from the data "
        "directly and are NOT your job. Do not emit supplier rows, ids, "
        "names or addresses as structured output. In the summary state "
        "how many suppliers are shown and what they have in common "
        "(status, country, whether addresses were included). Name at most "
        "two or three suppliers as examples; do not list them all — the "
        "records below the summary already do that."
    ),
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
        "bucket is absent, leave 'lines' empty and do not mention it.\n"
        "- 'receivablestaxline' bucket: emit each tax line under its parent "
        "line's 'tax_lines' (customer_transaction_line_id — the TAX line's "
        "own key, tax_line_number, tax, tax_rate, tax_amount, taxable_amount, "
        "jurisdiction). MATCH each tax line to its parent line by its "
        "'ParentCustomerTransactionLineId', which equals that line's "
        "'CustomerTransactionLineId' — nest it under THAT line, not any other. "
        "The summary must describe the tax charged (the tax "
        "types and rates). COPY every amount and rate exactly; do NOT sum or "
        "compute anything. Every customer_transaction_line_id must appear in "
        "the data. If the bucket is absent, leave 'tax_lines' empty and do "
        "not mention it.\n"
        "- 'receivablesinvoicetransactiondff' bucket: emit the invoice's DFF "
        "under 'dff' (context from __FLEX_Context, context_display_value from "
        "__FLEX_Context_DisplayValue). The summary must state the DFF context "
        "(e.g. 'DOO'), or note it is empty if no context is set. COPY the "
        "values exactly. If the bucket is absent, leave 'dff' as null and do "
        "not mention it."
    ),
    "CustomerAccount": (
        "This is a CUSTOMER-ACCOUNT-rooted query (accounts receivable). The "
        "customer was resolved to their account(s); for each account in the "
        "final set, emit one entry under 'customer_accounts' with its "
        "account_id, account_number, customer_name, open_receivables "
        "(TotalOpenReceivablesForAccount) and transactions_due "
        "(TotalTransactionsDueForAccount). account_id must appear in the "
        "data. COPY both figures exactly as given — do NOT sum, subtract, "
        "reconcile or otherwise compute with them; they are separate fields "
        "on the account record and need not agree with each other.\n"
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
        "not mention it.\n"
        "- 'accountcreditmemo' bucket: emit each memo under that account's "
        "'credit_memos' (credit_memo_id, credit_memo_number, "
        "credit_memo_date, amount, balance, status, currency), newest "
        "first as given. The summary must say how many memos and name the "
        "customer — but COPY every amount exactly; do NOT total them, do "
        "NOT negate them, do NOT compute a net. Memo amounts are normally "
        "negative, which is correct and needs no explanation or "
        "sign-flipping. Every credit_memo_id must appear in the data; "
        "credit_memo_id is the memo's OWN id (CreditMemoId), not a "
        "transaction id. If the bucket is absent, leave 'credit_memos' "
        "empty and do not mention it.\n"
        "- 'accountreceipt' bucket: emit each receipt under that account's "
        "'receipts' (receipt_id, receipt_number, receipt_date, amount, "
        "currency, receipt_method, state, unapplied_amount), newest first "
        "as given. A RECEIPT IS CASH RECEIVED from the customer — a "
        "payment, NOT an invoice and NOT a credit memo. The summary must "
        "say how many receipts and name the customer — but COPY every "
        "amount exactly; do NOT total them, average them, or compute what "
        "share is applied. A receipt whose state is 'Unapplied' is cash "
        "received that has not yet been matched to an invoice: that is "
        "normal and it is real money, so do NOT call it missing, pending, "
        "failed, unpaid or an error. Every receipt_id must appear in the "
        "data, copied exactly — these ids vary in length, and a short one "
        "is just as valid as a long one. If the bucket is absent, leave "
        "'receipts' empty and do not mention it.\n"
        "- 'account_receipt_applications' bucket: emit each application under that "
        "account's 'applications' (application_id, receipt_id, receipt_number, "
        "receipt_method, transaction_id, transaction_number, transaction_status, "
        "application_amount, application_date, currency). The summary must say "
        "how many applications and name the customer — but COPY every amount "
        "exactly; do NOT total them. Every application_id must appear in the "
        "data. If the bucket is absent, leave 'applications' empty and do not "
        "mention it.\n"
        "BALANCE-ONLY SHAPE — when there is NO child bucket at all "
        "(none of 'customertransaction', 'accountcreditmemo' or "
        "'accountreceipt'), the "
        "question asked for the account's BALANCE or ACTIVITY SUMMARY, not "
        "for a list of anything. ONLY in that case, write the summary as "
        "EXACTLY TWO SENTENCES and then STOP: (1) name the customer and "
        "account number and give the open receivables; (2) give the "
        "transactions due. Say nothing else. In particular, transactions, "
        "invoices, credit memos and receipts are not part of this answer "
        "at all — do "
        "not describe them, count them, comment on their absence, or note "
        "whether any were requested or found. None were fetched, so there "
        "is nothing true to say about them either way; a sentence such as "
        "'no transaction details were requested or found' is WRONG and "
        "must not appear. If ANY child bucket IS present, this shape does "
        "not apply — describe that child instead, per the rules above.\n"
        "\n"
        "IMPORTANT: Round all floating-point numbers (amounts, balances, "
        "totals) to exactly 2 decimal places. Do NOT output more than 2 "
        "decimal places. This applies to the summary and every numeric field. "
        "For example, output 1179915.32, not 1179915.3225000001."
    ),
    "CreditMemo": (
        "This is a CREDIT-MEMO-rooted query. The data has a 'credit_memos' "
        "bucket (a list of memo rows, newest first). EACH row carries a "
        "'total_credit' field with the SAME value — the pre-computed total "
        "credit across all memos. Emit one entry under 'credit_memos' for "
        "each row, copying its customer_transaction_id, transaction_number, "
        "transaction_date, entered_amount (normally negative), currency, "
        "status, customer_name, and customer_number. Set the response's "
        "'total_credit' to the 'total_credit' value from any row EXACTLY — "
        "do NOT recompute or sum entered_amount yourself; the total is "
        "provided. If that value is NULL, the memos span several "
        "currencies: set 'total_credit' to null, copy the row's "
        "'total_credit_note' into 'total_credit_note' verbatim, and the "
        "summary MUST NOT state any total — say instead that the memos "
        "span multiple currencies and were not totalled. Never add up the "
        "amounts yourself to fill the gap. Otherwise the summary MUST "
        "state how many credit memos were listed and the total credit "
        "value. If the list is empty, say there are no credit memos and "
        "set total_credit to 0. Every customer_transaction_id must appear "
        "in the data."
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
    "ExposureRanking": (
        "This is an EXPOSURE RANKING (an aggregation). The data has a "
        "single 'aggregation' bucket containing one ranking object with a "
        "'rows' list, already sorted by outstanding exposure (highest first). "
        "For each row, emit one entry under 'accounts' in the SAME order, "
        "copying account_id, account_number, customer_name, open_receivables, "
        "and transactions_due EXACTLY. Do not reorder, recompute, add, or drop. "
        "In the summary, state how many accounts were ranked and name the top "
        "one or two with their exposure amounts."
    ),
    "StandardReceipt": (
        "This is a STANDARD-RECEIPT-rooted query (top-level cash receipts). "
        "For each receipt in the final set, emit one entry under 'standard_receipts' "
        "with its standard_receipt_id, receipt_number, receipt_date, amount, currency, "
        "receipt_method, status, customer_name, customer_account_number, customer_site, "
        "and bank fields (remittance_bank_name, remittance_bank_branch, "
        "remittance_bank_account_number). standard_receipt_id must appear in the data. "
        "Copy every amount exactly. If the query included a site filter, the summary "
        "should mention that the receipts are for the specified site. If the list is "
        "empty, say so plainly."
    ),
    "ReceiptMethodDistribution": (
        "This is a RECEIPT METHOD DISTRIBUTION (an aggregation). The data has a "
        "single 'aggregation' bucket containing one object with 'total_receipts', "
        "'total_amount', and a 'rows' list already sorted by total amount "
        "(highest first). For each row, emit one entry under 'methods' in the "
        "SAME order, copying receipt_method, receipt_count, and total_amount "
        "EXACTLY. In the summary, state the total receipts and total amount, "
        "and name the top one or two methods."
    ),
}


def _build_system_prompt(target_entity: str) -> str:
    """Preamble + the per-entity instruction block."""
    block = _SYSTEM_PROMPT_BY_ENTITY[target_entity]
    return _SYSTEM_PROMPT_PREAMBLE + block


def _round_floats(obj):
    """Recursively round floats in a dict/list to 2 decimal places."""
    if isinstance(obj, (float, Decimal)):
        return round(float(obj), 2)
    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(item) for item in obj]
    return obj

def _build_synthesis_prompt(
    outputs: dict[str, list[dict]],
    truncation_by_step: dict[str, dict] | None = None,
    metadata_by_step: dict[str, dict] | None = None,
) -> str:
    """Build the user-message portion of the prompt: outputs as JSON,
    plus an optional truncation block and optional metadata totals."""
    rounded = _round_floats(outputs)
    rendered = json.dumps(rounded, default=str, indent=2)
    parts = [
        "Here is the executor's output. Each top-level key is the "
        "output_name of a step; each value is a list of records returned "
        f"by that step.\n\n```json\n{rendered}\n```\n"
    ]
    # ---- Add metadata note if available (fixes receipt-applications count) ----
    if metadata_by_step:
        apps_meta = metadata_by_step.get("account_receipt_applications")
        if apps_meta and apps_meta.get("total_available") is not None:
            total = apps_meta["total_available"]
            parts.append(
                f"\nThe total number of applied receipt applications for this account "
                f"is {total}.\n"
            )
            
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

def _validate_po_lifecycle(
    response: "POLifecycleResponse", valid: dict[str, set]
) -> None:
    """Check the lifecycle answer against its source record.

    The response carries no numeric ids, so there is little for the
    generic id guard to catch. What CAN go wrong here is different and
    worse: the model reporting a different PO than the one asked about,
    or quietly turning an unknown paid leg into a number. Both would read
    as a confident, correct-looking answer.
    """
    order = (response.order_number or "").strip()
    valid_orders = valid.get("lifecycle_order_numbers") or set()
    if valid_orders and order not in valid_orders:
        raise HallucinationError(
            "Synthesizer answered about a purchase order that is not in the "
            f"executor output: order_number={order!r}, "
            f"available={sorted(valid_orders)}"
        )


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
    metadata_by_step: dict[str, dict] | None = None,
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
        metadata_by_step: Optional dict from execute_plan containing
            ToolResult metadata (e.g. total_available) for non-iterating
            steps. Used to provide exact totals to the LLM.

    Returns:
        A Pydantic model — SupplierResponse, InvoiceResponse, or
        PurchaseOrderResponse depending on target_entity.

    Raises:
        UnsupportedEntityError if target_entity has no schema.
        HallucinationError if any structured ID isn't in the executor data.
        Pydantic ValidationError if the LLM output doesn't fit the schema.
        DegenerateOutputError if the LLM output is degenerate (runaway tokens, empty arrays).
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
    # Module 5: a PO lifecycle result is a single reconciliation record,
    # not an entity list. It roots on PurchaseOrder, which already has a
    # schema and a prompt, so it CANNOT be selected by target_entity —
    # select on the shape the tool stamped, as aggregation and comparison
    # do. Without this the record falls through to the PO-LIST schema and
    # the model quotes ids that schema never harvested, which the
    # hallucination guard then reports as invented data.
    lifecycle_record = _lifecycle_shape(outputs)

    shape = _aggregation_shape(outputs)
    print(f"[debug] shape = {shape}", file=sys.stderr)
    if lifecycle_record is not None:
        # Summary-only, like the supplier-record path: the model writes
        # the prose and code assembles every value. See
        # POLifecycleSummaryResponse for why.
        if llm is None:
            from spire.config import build_llm

            llm = build_llm(_TEMPERATURE)
        summary_llm = llm.with_structured_output(
            POLifecycleSummaryResponse, include_raw=True
        )
        result = summary_llm.invoke(
            [
                ("system", _build_system_prompt("POLifecycle")),
                (
                    "human",
                    _build_synthesis_prompt(
                        outputs, truncation_by_step, metadata_by_step
                    ),
                ),
            ]
        )
        if isinstance(result, dict) and "parsed" in result:
            from spire.config import log_usage

            log_usage(result.get("raw"), stage="synthesize")
            parsed = result["parsed"]
        else:
            parsed = result
        if isinstance(parsed, dict):
            parsed = POLifecycleSummaryResponse(**parsed)
        return build_lifecycle_response(
            lifecycle_record, parsed.summary, parsed.truncation_notes
        )

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

    # Plain supplier list: build the records here and ask the LLM only for
    # the summary. See build_supplier_records for why. Placed with the
    # other pre-LLM short-circuits (count_only, comparison, aggregation)
    # because it is the same idea: when the data already determines the
    # answer, do not pay a language model to restate it.
    supplier_bucket = (
        plain_supplier_bucket(outputs) if target_entity == "Supplier" else None
    )
    if supplier_bucket is not None:
        if llm is None:
            from spire.config import build_llm

            llm = build_llm(_TEMPERATURE)
        # include_raw so the call lands in the token log like every
        # other stage. Without it this call is invisible in the usage
        # totals — and those totals are the evidence base for the
        # parse-cost work ("parse is 65% of consumption"). A synthesize
        # call missing from the ledger would quietly flatter it.
        summary_llm = llm.with_structured_output(
            SupplierSummaryResponse, include_raw=True
        )
        result = summary_llm.invoke(
            [
                ("system", _build_system_prompt("SupplierSummaryOnly")),
                (
                    "human",
                    _build_synthesis_prompt(
                        outputs, truncation_by_step, metadata_by_step
                    ),
                ),
            ]
        )
        # Real LLM returns {"raw", "parsed", ...}; unit-test mocks return
        # the bare model or a dict. Handle both, as the main path does.
        if isinstance(result, dict) and "parsed" in result:
            from spire.config import log_usage

            log_usage(result.get("raw"), stage="synthesize")
            summary = result["parsed"]
        else:
            summary = result
        if isinstance(summary, dict):
            summary = SupplierSummaryResponse(**summary)
        return SupplierResponse(
            summary=summary.summary,
            suppliers=build_supplier_records(outputs[supplier_bucket]),
            truncation_notes=summary.truncation_notes,
        )

    if llm is None:
        from spire.config import build_llm

        llm = build_llm(_TEMPERATURE)

    structured_llm = llm.with_structured_output(schema, include_raw=True)
    system_prompt = _build_system_prompt(prompt_key)
    # Pass metadata_by_step to the prompt builder
    user_message = _build_synthesis_prompt(outputs, truncation_by_step, metadata_by_step)

    result = structured_llm.invoke(
        [("system", system_prompt), ("human", user_message)]
    )

    # With include_raw=True the real LLM returns
    # {"raw": AIMessage, "parsed": schema, "parsing_error": ...}. Unit
    # tests inject a mock returning the bare model (or a dict); handle
    # both so token logging never breaks the mock path.
    if isinstance(result, dict) and "parsed" in result:
        from spire.config import log_usage
        from pathlib import Path
        import time

        log_usage(result.get("raw"), stage="synthesize")

        # --- Guard: degenerate synthesis (runaway / non-stop) ---
        raw = result.get("raw")
        if raw is not None:
            usage = getattr(raw, "usage_metadata", {})
            out_tokens = usage.get("output_tokens", 0)
            finish_reason = getattr(raw, "response_metadata", {}).get("finish_reason")
            if out_tokens >= int(LLM_MAX_OUTPUT_TOKENS * 0.95) and finish_reason != "stop":
                raw_text = getattr(raw, "content", "")
                ts = time.strftime("%Y%m%d_%H%M%S")
                Path("traces").mkdir(exist_ok=True)
                with open(f"traces/degenerate_synthesize_{ts}.txt", "w", encoding="utf-8") as f:
                    f.write(f"target_entity: {target_entity}\nfinish_reason: {finish_reason}\nout_tokens: {out_tokens}\n--- raw response ---\n{raw_text}\n")
                raise DegenerateOutputError(
                    f"Degenerate synthesis (finish_reason={finish_reason}, out_tokens={out_tokens})"
                )

        response = result["parsed"]
    else:
        response = result

    if isinstance(response, dict):
        response = schema(**response)

    # --- Additional check: empty child arrays despite source data ---
    # For CustomerAccount responses, check child arrays (transactions, credit_memos, receipts, applications).
    # This catches cases where the LLM generates a summary but leaves arrays empty.
    if isinstance(response, CustomerAccountResponse):
        for account in response.customer_accounts:
            # Check each child array
            if hasattr(account, "transactions") and not account.transactions:
                if outputs.get("customer_transactions"):
                    raise DegenerateOutputError(
                        f"Account {account.account_id} has non-empty 'customertransaction' bucket but 'transactions' list is empty."
                    )
            if hasattr(account, "credit_memos") and not account.credit_memos:
                if outputs.get("account_credit_memos"):
                    raise DegenerateOutputError(
                        f"Account {account.account_id} has non-empty 'accountcreditmemo' bucket but 'credit_memos' list is empty."
                    )
            if hasattr(account, "receipts") and not account.receipts:
                if outputs.get("account_receipts"):
                    raise DegenerateOutputError(
                        f"Account {account.account_id} has non-empty 'accountreceipt' bucket but 'receipts' list is empty."
                    )
            # Check applications – corrected bucket name
            if hasattr(account, "applications") and not account.applications:
                if outputs.get("account_receipt_applications"):   # was "accountreceiptapplication"
                    raise DegenerateOutputError(
                        f"Account {account.account_id} has non-empty 'account_receipt_applications' bucket but 'applications' list is empty."
                    )

    _validate_no_hallucinated_ids(response, outputs)

    # --- Post-process: round any float values in the response (defend against LLM-generated long decimals) ---
    # The LLM sometimes generates many decimal places even when the input is rounded.
    response_dict = response.model_dump()
    rounded_dict = _round_floats(response_dict)
    response = response.__class__(**rounded_dict)

    return response

