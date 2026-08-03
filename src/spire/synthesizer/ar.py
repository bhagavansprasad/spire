"""AR (accounts receivable) response schemas.

ReceivablesInvoice, CustomerAccount, CreditMemo and StandardReceipt are
the AR-side target entities with a direct fetcher. This is the largest
schema module because AR carries the deepest nesting — an AR invoice has
tax lines, transaction DFF, and line detail all nested three levels down.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from spire.synthesizer.models_common import _SUMMARY_FIELD, _TRUNCATION_FIELD


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


# ─────────────────────────────────────────────────────────────────────
# Deterministic builders
#
# p2p.py has had build_supplier_records since the supplier list path
# went local; AR had no equivalent, so the model built both the prose
# AND every record on these routes. That is the expensive half: prose is
# one paragraph, records are 25 rows the model has to re-emit field by
# field from data it was already given.
#
# A builder is a field rename. It cannot invent a customer name, cannot
# miscount, cannot round 1179915.3225 to its binary expansion, and
# cannot drop the eighth field of a row. Those are not hypotheticals —
# each one has happened on this pod.
# ─────────────────────────────────────────────────────────────────────


def build_credit_memo_records(rows: list[dict]) -> list["CreditMemoRecord"]:
    """Executor credit-memo rows -> CreditMemoRecord list, verbatim.

    Pure: no LLM, no I/O. Every field the response needs is already on
    the row — list_receivables_credit_memos projects all eight.

    That projection is worth a note, because reading it wrong cost a
    session. A row rendered by --show-raw-output shows six fields and
    stops, silently; BillToCustomerName is the seventh. The obvious
    reading of a populated Customer column above a six-field row is that
    the model invented it. It did not. The diagnostic was abbreviating
    and the tool had been fetching the field all along.

    EnteredAmount is normally negative and the pod carries at least one
    POSITIVE, Incomplete memo. No sign correction here: the value is
    copied as it stands, because "normally negative" is an observation
    about the data and not a rule the renderer may enforce.
    """
    records: list[CreditMemoRecord] = []
    for row in rows:
        records.append(
            CreditMemoRecord(
                customer_transaction_id=row.get("CustomerTransactionId") or 0,
                transaction_number=str(row.get("TransactionNumber") or ""),
                transaction_date=str(row.get("TransactionDate") or ""),
                entered_amount=float(row.get("EnteredAmount") or 0),
                currency=str(row.get("CreditMemoCurrency") or ""),
                status=str(row.get("CreditMemoStatus") or ""),
                customer_name=str(row.get("BillToCustomerName") or ""),
                customer_number=str(row.get("BillToCustomerNumber") or ""),
            )
        )
    return records


def plain_credit_memo_bucket(outputs: dict[str, list[dict]]) -> str | None:
    """Name of the credit-memo bucket when this is a PLAIN memo list.

    "Plain" means one bucket of credit-memo rows and nothing else, so
    every field the response needs is on those rows.

    Deliberately conservative, for the same reason as
    plain_supplier_bucket: returning None too often costs tokens,
    returning a wrong bucket costs correctness. Anything that would need
    a join across buckets stays with the LLM.
    """
    if len(outputs) != 1:
        return None
    name, rows = next(iter(outputs.items()))
    if not rows or not isinstance(rows[0], dict):
        return None
    first = rows[0]
    if "CustomerTransactionId" in first and "CreditMemoCurrency" in first:
        return name
    return None
