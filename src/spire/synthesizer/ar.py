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


# ─────────────────────────────────────────────────────────────────────
# The single-parent shape
#
# plain_supplier_bucket and plain_credit_memo_bucket both require
# len(outputs) == 1. That was right for them and rejects almost
# everything in AR: of sixteen prompts in 03_ar.txt, four are single
# bucket, nine carry a parent plus one or two children, and two are
# aggregations that were already local.
#
# The rule below was derived from all sixteen rather than from the first
# three looked at — which matters, because the rule the first three
# suggested was "one parent, ONE child" and the invoice-with-tax-lines
# case has two.
#
#   One parent row, any number of child buckets.
#
# The single parent row is what makes it safe. plain_supplier_bucket's
# docstring defers multi-bucket deliberately: with 25 suppliers and a
# bucket of buyers, working out which buyer belongs to which supplier is
# real work and stays with the model. With exactly ONE parent there is
# no attribution question to get wrong — every child belongs to it by
# construction. Every parent bucket across those sixteen prompts holds
# exactly one row.
# ─────────────────────────────────────────────────────────────────────


def single_parent_shape(
    outputs: dict[str, list[dict]],
    parent_markers: tuple[str, ...],
) -> tuple[str, dict[str, list[dict]]] | None:
    """Find a one-row parent bucket and its children.

    Args:
        outputs: Executor output buckets.
        parent_markers: Field names that identify the parent's rows. ALL
            must be present on the first row. Several rather than one
            because AR shapes overlap — an AR invoice row and a credit
            memo row both carry CustomerTransactionId, and a detector
            keyed on that alone would claim the wrong bucket. A wrong
            bucket returns wrong data confidently, which is the failure
            mode this whole line of work exists to remove.

    Returns:
        (parent_bucket_name, {child_bucket: rows}) or None.

        None when there is no matching bucket, when the parent holds
        anything other than exactly one row, or when a second bucket
        also matches the markers — that last is ambiguous and belongs
        with the model.
    """
    if not outputs:
        return None

    matches = [
        name
        for name, rows in outputs.items()
        if rows
        and isinstance(rows[0], dict)
        and all(m in rows[0] for m in parent_markers)
    ]
    if len(matches) != 1:
        return None

    parent = matches[0]
    if len(outputs[parent]) != 1:
        return None

    children = {n: r for n, r in outputs.items() if n != parent}
    return parent, children


def build_receivables_invoice_records(
    parent_rows: list[dict],
    children: dict[str, list[dict]],
) -> list["ReceivablesInvoiceRecord"]:
    """Executor AR-invoice rows -> ReceivablesInvoiceRecord, verbatim.

    Pure: no LLM, no I/O. Children are attached to the single parent by
    construction — see single_parent_shape for why that is safe.

    Line rows carry TransacationBusinessCategory, misspelled by Oracle.
    Not read here, but noted: anything that does read it must use the
    typo exactly.

    TAX LINES JOIN ON ParentCustomerTransactionLineId, NOT on their own
    CustomerTransactionLineId. The tax row carries BOTH, and its own is
    the TAX line's PK — 112, say — while the invoice line it belongs to
    is 74. Joining on the obvious-looking field matches nothing, or
    matches the wrong line.

    That is not a deduction from the field names. It is written down in
    docs/spire_fusion_endpoints_reference.md, under a CAUTION, and was
    found only after two wrong guesses at how to fetch these rows at
    all — including a curl against an endpoint that does not exist
    (`receivablesTaxLines`; the real one is
    `receivablesInvoiceLineTaxLines`). The reference doc is the
    authority on pod behaviour and reading it first would have cost a
    minute.
    """
    records: list[ReceivablesInvoiceRecord] = []
    line_rows = children.get("receivables_invoice_lines") or []
    tax_rows = children.get("receivablestaxline") or []

    # Group tax rows by the line they belong to. Rows whose parent id is
    # missing are dropped rather than attached to an arbitrary line: a
    # tax figure under the wrong line is worse than one not shown.
    tax_by_line: dict[int, list[dict]] = {}
    for tx in tax_rows:
        parent_line = tx.get("ParentCustomerTransactionLineId")
        if parent_line is None:
            continue
        tax_by_line.setdefault(parent_line, []).append(tx)

    for row in parent_rows:
        lines = [
            ReceivablesInvoiceLineInfo(
                customer_transaction_line_id=ln.get("CustomerTransactionLineId") or 0,
                line_number=ln.get("LineNumber") or 0,
                description=str(ln.get("Description") or ""),
                quantity=float(ln.get("Quantity") or 0),
                unit_selling_price=float(ln.get("UnitSellingPrice") or 0),
                amount=float(ln.get("LineAmount") or 0),
                tax_lines=[
                    ReceivablesTaxLineInfo(
                        customer_transaction_line_id=(
                            tx.get("CustomerTransactionLineId") or 0
                        ),
                        tax_line_number=tx.get("TaxLineNumber") or 0,
                        tax=str(tx.get("Tax") or ""),
                        tax_rate=float(tx.get("TaxRate") or 0),
                        tax_amount=float(tx.get("TaxAmount") or 0),
                        taxable_amount=float(tx.get("TaxableAmount") or 0),
                        jurisdiction=str(tx.get("TaxJurisdictionCode") or ""),
                    )
                    for tx in tax_by_line.get(
                        ln.get("CustomerTransactionLineId"), []
                    )
                ],
            )
            for ln in line_rows
        ]
        records.append(
            ReceivablesInvoiceRecord(
                customer_transaction_id=row.get("CustomerTransactionId") or 0,
                transaction_number=str(row.get("TransactionNumber") or ""),
                transaction_date=str(row.get("TransactionDate") or ""),
                bill_to_customer_name=str(row.get("BillToCustomerName") or ""),
                status=str(row.get("InvoiceStatus") or ""),
                currency=str(row.get("InvoiceCurrencyCode") or ""),
                amount=float(row.get("EnteredAmount") or 0),
                balance=float(row.get("InvoiceBalanceAmount") or 0),
                lines=lines,
                dff=build_invoice_dff(
                    children.get("receivablesinvoicetransactiondff") or []
                ),
            )
        )
    return records


def build_customer_account_records(
    parent_rows: list[dict],
    children: dict[str, list[dict]],
) -> list["CustomerAccountRecord"]:
    """Executor customer-account rows -> CustomerAccountRecord, verbatim.

    Pure: no LLM, no I/O. One parent row, so every child bucket present
    belongs to it — see single_parent_shape.

    Four child buckets, each with its own key names, and none of them
    guessable from the model's field names:

      customer_transactions        TransactionId, TotalOriginalAmount
      account_credit_memos         CreditMemoId, TotalOriginalAmount
      account_receipts             StandardReceiptId, Amount
      account_receipt_applications ApplicationId, ReferenceTransactionId

    The applications bucket is the trap. Its transaction fields are
    ReferenceTransactionId and ReferenceTransactionNumber, NOT
    TransactionId — a builder copying the pattern from
    customer_transactions reads two fields that do not exist and
    silently produces zeroes.

    FLOAT NOTE: TotalTransactionsDueForAccount on account 26370 is
    1179915.3225. Four decimal places do not terminate in IEEE-754 and
    the synthesizer once emitted the full binary expansion to the token
    cap. float() here is a straight copy of a value the pod already
    rounded in transit; the rounding guards elsewhere still apply.
    """
    records: list[CustomerAccountRecord] = []

    transactions = [
        CustomerAccountTransactionInfo(
            transaction_id=t.get("TransactionId") or 0,
            transaction_number=str(t.get("TransactionNumber") or ""),
            transaction_class=str(t.get("TransactionClass") or ""),
            transaction_date=str(t.get("TransactionDate") or ""),
            amount=float(t.get("TotalOriginalAmount") or 0),
            balance=float(t.get("TotalBalanceAmount") or 0),
            status=str(t.get("InstallmentStatus") or ""),
        )
        for t in (children.get("customer_transactions") or [])
    ]

    credit_memos = [
        AccountCreditMemoInfo(
            credit_memo_id=m.get("CreditMemoId") or 0,
            credit_memo_number=str(m.get("CreditMemoNumber") or ""),
            credit_memo_date=str(m.get("CreditMemoDate") or ""),
            amount=float(m.get("TotalOriginalAmount") or 0),
            balance=float(m.get("TotalBalanceAmount") or 0),
            status=str(m.get("CreditMemoStatus") or ""),
            currency=str(m.get("CreditMemoCurrency") or ""),
        )
        for m in (children.get("account_credit_memos") or [])
    ]

    receipts = [
        AccountReceiptInfo(
            receipt_id=r.get("StandardReceiptId") or 0,
            receipt_number=str(r.get("ReceiptNumber") or ""),
            receipt_date=str(r.get("ReceiptDate") or ""),
            amount=float(r.get("Amount") or 0),
            currency=str(r.get("Currency") or ""),
            receipt_method=str(r.get("ReceiptMethod") or ""),
            state=str(r.get("State") or ""),
            unapplied_amount=float(r.get("UnappliedAmount") or 0),
        )
        for r in (children.get("account_receipts") or [])
    ]

    applications = [
        AccountReceiptApplicationInfo(
            application_id=a.get("ApplicationId") or 0,
            receipt_id=a.get("StandardReceiptId") or 0,
            receipt_number=str(a.get("ReceiptNumber") or ""),
            receipt_method=str(a.get("ReceiptMethod") or ""),
            # Reference*, not Transaction*. See the docstring.
            transaction_id=a.get("ReferenceTransactionId") or 0,
            transaction_number=str(a.get("ReferenceTransactionNumber") or ""),
            transaction_status=str(a.get("ReferenceTransactionStatus") or ""),
            application_amount=float(a.get("ApplicationAmount") or 0),
            application_date=str(a.get("ApplicationDate") or ""),
            currency=str(a.get("EnteredCurrency") or ""),
        )
        for a in (children.get("account_receipt_applications") or [])
    ]

    for row in parent_rows:
        records.append(
            CustomerAccountRecord(
                account_id=row.get("AccountId") or 0,
                account_number=str(row.get("AccountNumber") or ""),
                customer_name=str(row.get("CustomerName") or ""),
                open_receivables=float(
                    row.get("TotalOpenReceivablesForAccount") or 0
                ),
                transactions_due=float(
                    row.get("TotalTransactionsDueForAccount") or 0
                ),
                transactions=transactions,
                credit_memos=credit_memos,
                receipts=receipts,
                applications=applications,
            )
        )
    return records


def build_standard_receipt_records(
    rows: list[dict],
) -> list["StandardReceiptRecord"]:
    """Executor standard-receipt rows -> StandardReceiptRecord, verbatim.

    Pure: no LLM, no I/O. A top-level list, not a child of an account —
    the site-filtered receipts prompt uses /standardReceipts directly.

    Distinct from account_receipts despite the shared StandardReceiptId:
    these rows carry CustomerName, CustomerAccountNumber and the
    remittance bank fields, which the account child does not, and lack
    State and UnappliedAmount, which it does.

    TRAP, from the endpoints reference: "Santa Clara" spans accounts
    26360 AND 26370. A result that does not resolve to an
    AccountNumber cannot be trusted — which is why CustomerAccountNumber
    is copied here rather than left out as redundant.
    """
    return [
        StandardReceiptRecord(
            standard_receipt_id=r.get("StandardReceiptId") or 0,
            receipt_number=str(r.get("ReceiptNumber") or ""),
            receipt_date=str(r.get("ReceiptDate") or ""),
            amount=float(r.get("Amount") or 0),
            currency=str(r.get("Currency") or ""),
            receipt_method=str(r.get("ReceiptMethod") or ""),
            status=str(r.get("Status") or ""),
            customer_name=str(r.get("CustomerName") or ""),
            customer_account_number=str(r.get("CustomerAccountNumber") or ""),
            customer_site=str(r.get("CustomerSite") or ""),
            remittance_bank_name=str(r.get("RemittanceBankName") or ""),
            remittance_bank_branch=str(r.get("RemittanceBankBranch") or ""),
            remittance_bank_account_number=str(
                r.get("RemittanceBankAccountNumber") or ""
            ),
        )
        for r in rows
    ]


def build_invoice_dff(rows: list[dict]) -> "ReceivablesInvoiceTransactionDFFInfo | None":
    """DFF row -> ReceivablesInvoiceTransactionDFFInfo, or None.

    The key names here are unlike every other AR bucket and would not
    have been guessed: the id is `CustomerTrxId`, not
    CustomerTransactionId, and the context fields carry a DOUBLE
    LEADING UNDERSCORE — `__FLEX_Context`, `__FLEX_Context_DisplayValue`.

    Observed, not inferred. Reading them wrong yields a DFF block that
    renders empty, which looks like an invoice without flexfield values
    rather than like a bug.
    """
    if not rows:
        return None
    row = rows[0]
    return ReceivablesInvoiceTransactionDFFInfo(
        context=str(row.get("__FLEX_Context") or ""),
        context_display_value=str(row.get("__FLEX_Context_DisplayValue") or ""),
    )
