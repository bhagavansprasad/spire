
"""FastMCP server for Spire.

Loads the 'default_dev' persona at startup and exposes Fusion-backed
tools over HTTP. Run with:

    python -m spire.mcp_server.server

Tools currently exposed:
- search_suppliers
- search_invoices
- search_addresses
- search_purchase_orders
- search_suppliers_by_site_bu
- search_suppliers_by_classification
- get_buyer
- get_purchase_order_by_id
- get_purchase_order_lifecycle_status
- get_purchase_order_lines
- get_purchase_order_schedules
- get_supplier_contacts
- get_purchase_order_distributions
- aggregate_purchase_orders_by_supplier
- aggregate_purchase_orders_by_status
- summarize_open_purchase_orders
- compare_purchase_order_to_invoices
- compare_supplier_orders_to_invoices
- compare_top_suppliers_orders_to_invoices
"""

from fastmcp import Context, FastMCP

from spire.config import load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.aggregate_invoices import (
    aggregate_invoices_by_supplier as _aggregate_invoices_by_supplier,
)
from spire.mcp_server.tools.aggregate_purchase_orders import (
    aggregate_purchase_orders_by_supplier as _aggregate_purchase_orders_by_supplier,
    aggregate_purchase_orders_by_status as _aggregate_purchase_orders_by_status,
    summarize_open_purchase_orders as _summarize_open_purchase_orders,
)
from spire.mcp_server.tools.buyer import get_buyer as _get_buyer
from spire.mcp_server.tools.invoices import search_invoices as _search_invoices
from spire.mcp_server.tools.purchase_orders import (
    search_purchase_orders as _search_purchase_orders,
)
from spire.mcp_server.tools.suppliers import search_suppliers as _search_suppliers
from spire.mcp_server.tools.addresses import search_addresses as _search_addresses
from spire.mcp_server.tools.supplier_sites import (
    search_suppliers_by_site_bu as _search_suppliers_by_site_bu,
)
from spire.mcp_server.tools.supplier_classifications import (
    search_suppliers_by_classification as _search_suppliers_by_classification,
)
from spire.mcp_server.tools.purchase_order_by_id import (
    get_purchase_order_by_id as _get_purchase_order_by_id,
)
from spire.mcp_server.tools.po_lifecycle import (
    get_purchase_order_lifecycle_status as _get_purchase_order_lifecycle_status,
)
from spire.mcp_server.tools.purchase_order_lines import (
    get_purchase_order_lines as _get_purchase_order_lines,
)
from spire.mcp_server.tools.receivables_invoice_by_id import (
    get_receivables_invoice_by_id as _get_receivables_invoice_by_id,
)
from spire.mcp_server.tools.receivables_invoice_lines import (
    get_receivables_invoice_lines as _get_receivables_invoice_lines,
)
from spire.mcp_server.tools.receivables_invoice_tax_lines import (
    get_receivables_invoice_tax_lines as _get_receivables_invoice_tax_lines,
)
from spire.mcp_server.tools.receivables_invoice_transaction_dff import (
    get_receivables_invoice_transaction_dff as _get_receivables_invoice_transaction_dff,
)
from spire.mcp_server.tools.receivables_credit_memos import (
    list_receivables_credit_memos as _list_receivables_credit_memos,
    compute_total_credit as _compute_total_credit,
)
from spire.mcp_server.tools.customer_account_by_name import (
    get_customer_account_by_name as _get_customer_account_by_name,
)
from spire.mcp_server.tools.customer_transactions import (
    get_customer_transactions as _get_customer_transactions,
)
from spire.mcp_server.tools.account_credit_memos import (
    get_account_credit_memos as _get_account_credit_memos,
)
from spire.mcp_server.tools.account_receipts import (
    get_account_receipts as _get_account_receipts,
)
from spire.mcp_server.tools.purchase_order_schedules import (
    get_purchase_order_schedules as _get_purchase_order_schedules,
)
from spire.mcp_server.tools.supplier_contacts import (
    get_supplier_contacts as _get_supplier_contacts,
)
from spire.mcp_server.tools.purchase_order_distributions import (
    get_purchase_order_distributions as _get_purchase_order_distributions,
)
from spire.mcp_server.tools.compare_orders_to_invoices import (
    compare_purchase_order_to_invoices as _compare_purchase_order_to_invoices,
    compare_supplier_orders_to_invoices as _compare_supplier_orders_to_invoices,
    compare_top_suppliers_orders_to_invoices as _compare_top_suppliers_orders_to_invoices,
)

from spire.mcp_server.tools.account_receipt_applications import (
    get_account_receipt_applications as _get_account_receipt_applications,
)

from spire.mcp_server.tools.standard_receipts import (
    search_standard_receipts as _search_standard_receipts,
)

from spire.mcp_server.tools.rank_customer_accounts_by_exposure import (
    rank_customer_accounts_by_exposure as _rank_customer_accounts_by_exposure,
)

from spire.mcp_server.tools.aggregate_standard_receipts_by_method import (
    aggregate_standard_receipts_by_method as _aggregate_standard_receipts_by_method,
)

PERSONA_NAME = "default_dev"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3333

mcp = FastMCP("spire")
_persona = load_persona(PERSONA_NAME)


@mcp.tool()
async def search_suppliers(
    supplier_name_contains: str | None = None,
    status: str | None = None,
    business_relationship: str | None = None,
    country: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    include_addresses: bool = False,
    limit: int = 25,
) -> dict:
    """Search Oracle Fusion suppliers by any combination of filters.

    Use for supplier questions with any mix of: a name fragment, a
    status, a country, and a creation-date range. Filters stack
    (e.g. "active US suppliers named Lee").

    Args:
        supplier_name_contains: Optional substring to match in supplier name.
        status: Exact Status match (e.g., "ACTIVE", "INACTIVE"). Applied
            client-side. Use for "active suppliers" / "inactive suppliers".
        business_relationship: Exact BusinessRelationship match (e.g.,
            "Spend Authorized", "Prospective"). Applied client-side. Use
            for "spend authorized suppliers" / "prospective suppliers".
        country: ISO-2 code (e.g., "US", "GB") or full name (e.g.,
            "United States"). Matched against the addresses child
            resource. Three-letter codes like "USA" are not supported.
        created_from: Lower bound on CreationDate ("YYYY-MM-DD").
        created_to: Upper bound on CreationDate ("YYYY-MM-DD").
        include_addresses: When True, nest each supplier's addresses under
            an 'addresses' key (via expand=addresses). Use for "suppliers
            with their addresses".
        limit: Max records to return (default 25).
    """
    async with FusionClient(_persona) as client:
        result = await _search_suppliers(
            client,
            supplier_name_contains=supplier_name_contains,
            status=status,
            business_relationship=business_relationship,
            country=country,
            created_from=created_from,
            created_to=created_to,
            include_addresses=include_addresses,
            limit=limit,
        )
        return result.to_dict()


@mcp.tool()
async def search_invoices(
    purchase_order: str | None = None,
    supplier_number: str | None = None,
    supplier_name: str | None = None,
    invoice_date_after: str | None = None,
    invoice_date_before: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    limit: int = 25,
) -> dict:
    """Search Oracle Fusion invoices.

    Use this to find invoices for a specific supplier OR for a specific
    purchase order, optionally filtered by date and/or amount. For "which
    invoices were raised against PO 162034?" pass purchase_order="162034"
    (the PO NUMBER as shown on the order, not POHeaderId). For the question "are there invoices for
    supplier X in the last N months?" pass the supplier's number plus an
    invoice_date_after of (today - N months) and check whether the result
    is empty.

    For a calendar month, combine the bounds: Jan 2022 is
    invoice_date_after="2022-01-01" and invoice_date_before="2022-02-01".

    Args:
        purchase_order: Exact PurchaseOrderNumber, e.g. "162034". Returns
            the invoices raised against that PO. This is the PO NUMBER
            (OrderNumber), not POHeaderId.
        supplier_number: Exact SupplierNumber, e.g., "1252". Get this from
            search_suppliers first.
        supplier_name: Substring match on Supplier name. Use when the
            supplier_number is unknown.
        invoice_date_after: ISO date "YYYY-MM-DD". Returns invoices on
            or after this date (inclusive).
        invoice_date_before: ISO date "YYYY-MM-DD". Returns invoices
            strictly before this date (exclusive).
        amount_min: Lower bound on InvoiceAmount (inclusive).
        amount_max: Upper bound on InvoiceAmount (inclusive).
        limit: Max records to return.
    """
    async with FusionClient(_persona) as client:
        result = await _search_invoices(
            client,
            purchase_order=purchase_order,
            supplier_number=supplier_number,
            supplier_name=supplier_name,
            invoice_date_after=invoice_date_after,
            invoice_date_before=invoice_date_before,
            amount_min=amount_min,
            amount_max=amount_max,
            limit=limit,
        )
        return result.to_dict()


@mcp.tool()
async def search_addresses(
    supplier_number: str | None = None,
    supplier_name: str | None = None,
    country: str | None = None,
    limit: int = 25,
) -> dict:
    """Fetch supplier addresses as flat records.

    Use for address questions. Requires at least one of supplier_number,
    supplier_name, or country — addresses are a child of the supplier
    record, so an unfiltered fetch would pull every address on the pod.

    Args:
        supplier_number: Exact SupplierNumber, e.g. "1252".
        supplier_name: Substring match on Supplier name.
        country: ISO-2 code (e.g. "US") or full name (e.g. "United
            States"), matched against each address.
        limit: Max address records to return.
    """
    async with FusionClient(_persona) as client:
        result = await _search_addresses(
            client,
            supplier_number=supplier_number,
            supplier_name=supplier_name,
            country=country,
            limit=limit,
        )
        return result.to_dict()


@mcp.tool()
async def search_purchase_orders(
    supplier_name: str | None = None,
    supplier_id: int | None = None,
    status: str | None = None,
    created_before: str | None = None,
    created_since: str | None = None,
    limit: int = 25,
) -> dict:
    """Search Oracle Fusion purchase orders.

    Use this to find POs for a specific supplier, optionally filtered by
    status. For "find open POs for supplier X" pass supplier_name or
    supplier_id along with status="OPEN". For "POs created before 2015"
    pass created_before="2015-01-01".

    Dates filter CreationDate, NOT OrderDate — OrderDate is not queryable
    on this pod. Pass ABSOLUTE dates only; this tool does no relative-date
    arithmetic.

    Args:
        supplier_name: Substring match on Supplier name (LIKE). Use when
            you have the supplier name as a string.
        supplier_id: Exact SupplierId match (numeric). Get this from
            search_suppliers if available.
        status: Exact StatusCode match. The pod has eleven values — OPEN,
            CLOSED, CLOSED FOR RECEIVING, REJECTED, PENDING APPROVAL,
            WITHDRAWN, INCOMPLETE, CLOSED FOR INVOICING, PENDING
            SIGNATURE, CANCELED, ON HOLD (spaces, not underscores).
        created_before: ISO "YYYY-MM-DD". POs whose CreationDate is
            strictly before this date.
        created_since: ISO "YYYY-MM-DD". POs whose CreationDate is on or
            after this date.
        limit: Max records to return.
    """
    async with FusionClient(_persona) as client:
        result = await _search_purchase_orders(
            client,
            supplier_name=supplier_name,
            supplier_id=supplier_id,
            status=status,
            created_before=created_before,
            created_since=created_since,
            limit=limit,
        )
        return result.to_dict()


@mcp.tool()
async def search_suppliers_by_site_bu(
    supplier_id: int,
    business_unit: str,
    limit: int = 25,
) -> dict:
    """Check whether one supplier has a site in a given business unit.

    Edge tool: called once per supplier to filter suppliers by their
    sites' ProcurementBU. For "suppliers with a site in business unit X",
    the executor calls this per supplier and keeps those whose result is
    non-empty. ProcurementBU filters server-side on the sites child.

    Args:
        supplier_id: The SupplierId of the supplier to check. Get this
            from search_suppliers.
        business_unit: Exact ProcurementBU display string, e.g.
            "US1 Business Unit".
        limit: Max site records to return.

    Returns:
        A ToolResult dict whose items are the supplier's matching sites.
        Empty items means the supplier has no site in that BU.
    """
    async with FusionClient(_persona) as client:
        result = await _search_suppliers_by_site_bu(
            client,
            supplier_id=supplier_id,
            business_unit=business_unit,
            limit=limit,
        )
        return result.to_dict()


@mcp.tool()
async def search_suppliers_by_classification(
    supplier_id: int,
    classification: str,
    limit: int = 25,
) -> dict:
    """Check whether one supplier has a given business classification.

    Edge tool: called once per supplier to filter suppliers by their
    business classifications. For "suppliers that are small business /
    woman owned / minority owned", the executor calls this per supplier
    and keeps those whose result is non-empty. Classification filters
    server-side on the businessClassifications child.

    Args:
        supplier_id: The SupplierId of the supplier to check. Get this
            from search_suppliers.
        classification: Exact Classification display string, e.g.
            "Small Business".
        limit: Max classification records to return.

    Returns:
        A ToolResult dict whose items are the supplier's matching
        classifications. Empty items means no match.
    """
    async with FusionClient(_persona) as client:
        result = await _search_suppliers_by_classification(
            client,
            supplier_id=supplier_id,
            classification=classification,
            limit=limit,
        )
        return result.to_dict()


@mcp.tool()
async def aggregate_invoices_by_supplier(
    ctx: Context,
    date_from: str | None = None,
    date_to: str | None = None,
    top_n: int = 10,
) -> dict:
    """Rank suppliers by total invoice spend over a date range.

    Use this for ranking/total questions like "top 10 suppliers by
    spend" or "which suppliers did we spend the most with in Q1". The
    tool groups invoices by supplier, sums InvoiceAmount, and returns the
    top_n suppliers by total spend. Grouping (supplier) and measure (sum
    of spend) are fixed — this is a bounded aggregation, not a general
    engine.

    Args:
        date_from: ISO "YYYY-MM-DD". Inclusive lower bound on InvoiceDate.
        date_to: ISO "YYYY-MM-DD". Exclusive upper bound on InvoiceDate.
            For Q1 2026: date_from="2026-01-01", date_to="2026-04-01".
        top_n: Number of suppliers to return (default 10).

    Returns:
        A "supplier_spend_ranking" dict: ranked rows of
        {supplier, supplier_number, total_spend, invoice_count} plus
        total_suppliers, returned, truncated, and the echoed date range.
    """
    async with FusionClient(_persona) as client:
        return await _aggregate_invoices_by_supplier(
            client,
            date_from=date_from,
            date_to=date_to,
            top_n=top_n,
            report_progress=ctx.report_progress,
        )


@mcp.tool()
async def get_buyer(buyer_id: int) -> dict | None:
    """Look up a buyer (purchasing agent) by ID.

    Buyer IDs come from purchase orders (the BuyerId field returned by
    search_purchase_orders). This tool returns the buyer's name, email,
    and username from the HCM workers system.

    Args:
        buyer_id: The numeric BuyerId from a purchase order.

    Returns:
        A dict with PersonId, DisplayName, FirstName, LastName, WorkEmail,
        Username, and PersonNumber. Returns null if no buyer matches.
    """
    async with FusionClient(_persona) as client:
        return await _get_buyer(client, buyer_id=buyer_id)


@mcp.tool()
async def get_purchase_order_by_id(po_header_id: int) -> dict | None:
    """Fetch one purchase order by its POHeaderId.

    Use this to answer questions about a specific purchase order, e.g.
    "what is PO 2144 about" or "show PO 2144". POHeaderId is the numeric
    id of the PO. To also see the PO's line items, call
    get_purchase_order_lines with the same id.

    Args:
        po_header_id: The numeric POHeaderId of the purchase order.

    Returns:
        A dict of the PO header fields (OrderNumber, Supplier, Status,
        Buyer, Ordered, Total, TotalTax, PaymentTerms, ship-to/bill-to,
        OrderDate, and more), or null if no PO with that id exists.
    """
    async with FusionClient(_persona) as client:
        return await _get_purchase_order_by_id(
            client, po_header_id=po_header_id
        )


@mcp.tool()
async def get_purchase_order_lifecycle_status(po_number: str) -> dict:
    """Reconcile ONE purchase order end to end: ordered vs received vs
    invoiced vs paid.

    Use this for questions about a single PO's progress through receiving,
    invoicing and payment — "has PO 701337 been fully received, fully
    invoiced and fully paid", "why is PO 701337 still open", "who owns the
    next action on PO 701337", "end-to-end summary of PO 701337".

    Distinct from get_purchase_order_by_id, which returns the header alone.
    Distinct from search_invoices with a purchase_order filter, which lists
    the invoices raised against a PO rather than reconciling the order.

    Takes the PO NUMBER (OrderNumber, the number printed on the order),
    NOT the POHeaderId. Assembles six resources: PO header, schedules,
    invoices, invoice installments, supplier and supplier site.

    Args:
        po_number: The PO's OrderNumber, e.g. "701337".

    Returns:
        One po_lifecycle_status dict — NOT a list. Carries the four amounts
        (received is DERIVED from quantities; ReceivedAmount is empty on
        this pod), the three remainders, the completion flags, per-schedule
        detail, supplier and site setup, invoice holds, lifecycle_stage,
        responsible_team, risk with risk_reasons, recommended_action, and a
        notes list carrying every gap found. found=False if no such PO.

        TWO FIELDS CAN BE null AND MUST NOT BE READ AS false OR 0:
        fully_paid and remaining_to_pay, both null when paid_state is
        "unknown" — the case where the schedules record billing but no AP
        invoice carries this PO number. Branch on paid_state, never on the
        truthiness of fully_paid.

        risk and recommended_action are COMPUTED here and must be copied
        verbatim, never re-derived downstream.
    """
    async with FusionClient(_persona) as client:
        return await _get_purchase_order_lifecycle_status(
            client, po_number=po_number
        )


@mcp.tool()
async def get_purchase_order_lines(
    po_header_id: int, limit: int = 25
) -> dict:
    """Fetch the line items of one purchase order.

    Use this for "show the lines of PO 2144" or as the second half of
    "what is PO 2144 about, show its lines" (call get_purchase_order_by_id
    for the header, then this for the lines).

    Args:
        po_header_id: The numeric POHeaderId of the parent purchase order.
        limit: Max line records to return (default 25).

    Returns:
        A dict with the PO's lines: LineNumber, Description, Category,
        Quantity, Price, Ordered, TotalTax, Total, and Status per line.
    """
    async with FusionClient(_persona) as client:
        result = await _get_purchase_order_lines(
            client, po_header_id=po_header_id, limit=limit
        )
        return result.to_dict()


@mcp.tool()
async def get_receivables_invoice_by_id(
    customer_transaction_id: int,
) -> dict | None:
    """Fetch one AR (accounts-receivable) invoice by its CustomerTransactionId.

    Use this for a specific AR invoice, e.g. "the AR invoice with
    CustomerTransactionId 300000248096352" or "show receivables invoice X".
    To also see its lines, call get_receivables_invoice_lines with the same
    id. This is the sell-side (receivables) invoice, distinct from the AP
    invoice tools.

    Args:
        customer_transaction_id: The numeric CustomerTransactionId of the
            AR invoice.

    Returns:
        A dict of the AR invoice header (TransactionNumber, BillToCustomerName,
        BillToCustomerNumber, EnteredAmount, InvoiceBalanceAmount,
        InvoiceCurrencyCode, TransactionDate, DueDate, InvoiceStatus, and
        more), or null if no invoice with that id exists.
    """
    async with FusionClient(_persona) as client:
        return await _get_receivables_invoice_by_id(
            client, customer_transaction_id=customer_transaction_id
        )


@mcp.tool()
async def get_receivables_invoice_lines(
    customer_transaction_id: int, limit: int = 25
) -> dict:
    """Fetch the line items of one AR invoice.

    Use this for "show the lines of AR invoice X" or as the second half of
    "the AR invoice with CustomerTransactionId X and its lines" (call
    get_receivables_invoice_by_id for the header, then this for the lines).

    Args:
        customer_transaction_id: The numeric CustomerTransactionId of the
            parent AR invoice.
        limit: Max line records to return (default 25).

    Returns:
        A dict with the invoice's lines: LineNumber, Description, Quantity,
        UnitSellingPrice, LineAmount, and tax fields per line.
    """
    async with FusionClient(_persona) as client:
        result = await _get_receivables_invoice_lines(
            client, customer_transaction_id=customer_transaction_id, limit=limit
        )
        return result.to_dict()


@mcp.tool()
async def get_receivables_invoice_tax_lines(
    customer_transaction_id: int, line_id: int, limit: int = 25
) -> dict:
    """Fetch the tax lines of one AR invoice line.

    Use this as the third hop of "the AR invoice with CustomerTransactionId X
    and its tax lines": call get_receivables_invoice_by_id for the header,
    get_receivables_invoice_lines for the lines, then this for each line's tax
    lines. Tax lines are the jurisdiction/rate/amount breakdown for a line
    (e.g. a STATE row and a COUNTY row).

    Args:
        customer_transaction_id: The numeric CustomerTransactionId of the
            parent AR invoice.
        line_id: The numeric CustomerTransactionLineId of the parent invoice
            line (the parent line's PK, not the tax line's).
        limit: Max tax-line records to return (default 25).

    Returns:
        A dict with the line's tax lines: TaxLineNumber, Tax, TaxRate,
        TaxAmount, TaxableAmount, TaxJurisdictionCode, and related tax fields.
    """
    async with FusionClient(_persona) as client:
        result = await _get_receivables_invoice_tax_lines(
            client,
            customer_transaction_id=customer_transaction_id,
            line_id=line_id,
            limit=limit,
        )
        return result.to_dict()


@mcp.tool()
async def get_receivables_invoice_transaction_dff(
    customer_transaction_id: int, limit: int = 25
) -> dict:
    """Fetch the transaction DFF (descriptive flexfield) of one AR invoice.

    Use this for "fetch the DFF values for AR invoice X". AR invoices expose
    two DFF children; this is the transaction DFF, the populated one on this
    pod. Call get_receivables_invoice_by_id for the header, then this for the
    DFF.

    Args:
        customer_transaction_id: The numeric CustomerTransactionId of the
            parent AR invoice.
        limit: Max DFF records to return (default 25; an invoice has one).

    Returns:
        A dict with the invoice's DFF row: CustomerTrxId, __FLEX_Context, and
        __FLEX_Context_DisplayValue.
    """
    async with FusionClient(_persona) as client:
        result = await _get_receivables_invoice_transaction_dff(
            client, customer_transaction_id=customer_transaction_id, limit=limit
        )
        return result.to_dict()


@mcp.tool()
async def list_receivables_credit_memos(limit: int = 25) -> dict:
    """List recent AR credit memos with their total credit value.

    Use this for "list credit memos", "recent credit memos", "top N credit
    memos", or "total value of credit memos". Returns the most recent credit
    memos (ordered by TransactionDate descending, server-side) up to `limit`,
    plus `total_credit` — the ledger sum of EnteredAmount across the
    returned memos (a positive memo offsets the negatives).

    The total is only meaningful within ONE currency. When the returned
    memos span several, `total_credit` is null and `total_credit_note`
    explains why; render the note INSTEAD of a number, never both.

    Args:
        limit: Max credit-memo records to return (default 25).

    Returns:
        A dict with `items` (the credit memos, newest first),
        `total_credit` (ledger sum over those items, or null when they
        span several currencies) and `total_credit_note` (why the total
        was withheld, or null when a total is given).
    """
    async with FusionClient(_persona) as client:
        result = await _list_receivables_credit_memos(client, limit=limit)
        payload = result.to_dict()
        items = payload.get("items", [])
        # Currency-aware AND truncation-aware: returns a total OR a note,
        # never both. total_available is the pod's own count (totalResults);
        # passing it lets compute_total_credit withhold a total when these
        # rows are only a capped sample of a larger set (#27), the same way
        # it withholds across currencies. See compute_total_credit for why a
        # plain sum over a truncated sample was wrong.
        total_credit, total_credit_note = _compute_total_credit(
            items, total_available=payload.get("total_available")
        )
        payload["total_credit"] = total_credit
        payload["total_credit_note"] = total_credit_note
        # The executor unwraps a ToolResult to its `items` list and discards
        # every other top-level key, so top-level keys would never reach the
        # synthesizer. Stamp both onto EACH item so they survive the unwrap
        # and the synthesizer can read them off any row.
        for m in items:
            m["total_credit"] = total_credit
            m["total_credit_note"] = total_credit_note
        return payload


@mcp.tool()
async def get_customer_account_by_name(
    customer_name: str, limit: int = 25
) -> list[dict]:
    """Resolve a customer name to their receivables account(s).

    Use this as the first half of a customer-scoped AR-invoice query, e.g.
    "AR invoices for ABC Corporation Americas" or "invoices for customer
    X": resolve the customer to their account(s) here, then call
    get_customer_transactions with each AccountId to list the invoices.

    Args:
        customer_name: The customer's display name, matched exactly.

    Returns:
        A list of account dicts (AccountId, AccountNumber, CustomerName,
        CustomerId, and the account balances), one per matching account.
        Empty if the name matches nothing.
    """
    async with FusionClient(_persona) as client:
        return await _get_customer_account_by_name(
            client, customer_name=customer_name, limit=limit
        )


@mcp.tool()
async def get_customer_transactions(
    account_id: int,
    open_only: bool = False,
    limit: int = 25,
) -> dict:
    """List a customer account's invoice transactions.

    Use this as the second half of a customer-scoped AR-invoice query:
    after get_customer_account_by_name resolves the customer to an
    AccountId, this returns that account's invoices.

    Args:
        account_id: The AccountId of the customer account.
        open_only: When True, keep only invoices with a positive open
            balance. (Reserved for the open-invoices flow; defaults False.)
        limit: Max transactions to return after filtering.

    Returns:
        A dict with the account's invoice transactions: TransactionNumber,
        TransactionClass, TransactionDate, TotalOriginalAmount,
        TotalBalanceAmount, and InstallmentStatus per row.
    """
    async with FusionClient(_persona) as client:
        result = await _get_customer_transactions(
            client, account_id=account_id, open_only=open_only, limit=limit
        )
        return result.to_dict()


@mcp.tool()
async def get_account_credit_memos(
    account_id: int,
    limit: int = 25,
) -> dict:
    """List a customer account's credit memos, newest first.

    Use this as the second half of a customer-scoped credit-memo query:
    after get_customer_account_by_name resolves the customer to an
    AccountId, this returns that account's credit memos.

    NOT interchangeable with list_receivables_credit_memos. That tool
    reads the TOP-LEVEL receivablesCreditMemos collection (everyone's
    memos, keyed by CustomerTransactionId) and reports a total; this one
    reads a SINGLE account's creditMemos child (keyed by CreditMemoId, a
    different id space, with a different field projection). A question
    naming a customer belongs here; a bare "recent credit memos" belongs
    there.

    Args:
        account_id: The AccountId of the customer account.
        limit: Max credit memos to return. Applied server-side alongside
            a newest-first sort, so this is a true "N most recent" — the
            child holds credit memos only, so nothing is filtered out
            afterwards.

    Returns:
        A dict with the account's credit memos: CreditMemoId,
        CreditMemoNumber, CreditMemoDate, TransactionClass,
        TotalOriginalAmount, TotalBalanceAmount, AvailableAmount,
        CreditMemoStatus, CreditMemoCurrency and BillToSiteNumber per row.
    """
    async with FusionClient(_persona) as client:
        result = await _get_account_credit_memos(
            client, account_id=account_id, limit=limit
        )
        return result.to_dict()


@mcp.tool()
async def get_account_receipts(
    account_id: int,
    limit: int = 10,
) -> dict:
    """List a customer account's standard receipts, newest first.

    Use this as the second half of a customer-scoped receipts query:
    after get_customer_account_by_name resolves the customer to an
    AccountId, this returns that account's receipts.

    A RECEIPT is CASH RECEIVED from a customer — a payment. It is not an
    invoice of any kind: not an AP invoice (search_invoices, money owed
    to a supplier), not an AR invoice (get_receivables_invoice_by_id,
    money a customer owes), and not a credit memo
    (get_account_credit_memos). Pick this tool only for
    payments/receipts.

    Returns receipts in EVERY state. Rows with State='Unapplied' are cash
    received but not yet matched to an invoice — real money, not noise,
    so they are included rather than filtered.

    Args:
        account_id: The AccountId of the customer account.
        limit: Max receipts to return. Applied server-side alongside a
            newest-first sort, so this is a true "N most recent" — the
            child holds receipts only, so nothing is filtered out
            afterwards. Defaults to 10 rather than 25: 25 varied receipt
            rows overran the synthesizer's output budget and produced an
            answer with an empty receipts list, so keep this small unless
            an end-to-end run proves a larger value safe.

    Returns:
        A dict with the account's receipts: StandardReceiptId,
        ReceiptNumber, ReceiptDate, Amount, Currency, ReceiptMethod,
        State, ProcessStatus, UnappliedAmount, CustomerSite and
        BusinessUnit per row. Note StandardReceiptId mixes id widths —
        backfilled rows carry small ints, recent ones large.
    """
    async with FusionClient(_persona) as client:
        result = await _get_account_receipts(
            client, account_id=account_id, limit=limit
        )
        return result.to_dict()


@mcp.tool()
async def get_purchase_order_schedules(
    po_header_id: int, limit: int = 25
) -> dict:
    """Fetch the shipment schedules of one purchase order.

    Use this for "show the schedules for PO 2144" or "what is PO 2144
    about, show its schedules". Each schedule gives the ship-to location,
    requested (need-by) delivery date, quantity, amount and status.

    Args:
        po_header_id: The numeric POHeaderId of the purchase order.
        limit: Max schedule records to return (default 25).

    Returns:
        A dict with the PO's schedules: ScheduleNumber, ShipToLocation,
        RequestedDeliveryDate, Quantity, Amount and ScheduleStatus per
        schedule.
    """
    async with FusionClient(_persona) as client:
        result = await _get_purchase_order_schedules(
            client, po_header_id=po_header_id, limit=limit
        )
        return result.to_dict()


@mcp.tool()
async def get_supplier_contacts(
    supplier_id: int, limit: int = 25
) -> dict:
    """Fetch the contact people of one supplier.

    Use this for "show supplier 1262 and its contacts" or "who are the
    contacts for EIP Inc". Each contact gives a name, email, optional job
    title, status, and a flag marking the primary (administrative) contact.

    Args:
        supplier_id: The numeric SupplierId of the supplier.
        limit: Max contact records to return (default 25).

    Returns:
        A dict with the supplier's contacts: ContactName, FirstName,
        LastName, Email, JobTitle, Status and AdministrativeContactFlag
        per contact.
    """
    async with FusionClient(_persona) as client:
        result = await _get_supplier_contacts(
            client, supplier_id=supplier_id, limit=limit
        )
        return result.to_dict()


@mcp.tool()
async def get_purchase_order_distributions(
    po_header_id: int,
    po_line_id: int,
    line_location_id: int,
    limit: int = 25,
) -> dict:
    """Fetch the distribution accounts of one PO schedule.

    Use this for "show PO 2144 and its distributions" or "what accounts
    is this PO booked to". Distributions are the deepest PO detail: the
    charge, accrual and variance accounts a schedule's amount is booked
    to. All three ids come from the parent schedule row (see
    get_purchase_order_schedules), because the distributions resource
    exists only on the deep nested path.

    Args:
        po_header_id: The numeric POHeaderId of the PO.
        po_line_id: The numeric POLineId of the line.
        line_location_id: The numeric LineLocationId (schedule id).
        limit: Max distribution records to return (default 25).

    Returns:
        A dict with the schedule's distributions: DistributionNumber,
        POChargeAccount, POAccrualAccount, POVarianceAccount,
        DeliverToLocationCode, Percentage, Quantity, Ordered, Total and
        Status per distribution.
    """
    async with FusionClient(_persona) as client:
        result = await _get_purchase_order_distributions(
            client,
            po_header_id=po_header_id,
            po_line_id=po_line_id,
            line_location_id=line_location_id,
            limit=limit,
        )
        return result.to_dict()


@mcp.tool()
async def aggregate_purchase_orders_by_supplier(
    ctx: Context,
    status: str | None = None,
    top_n: int = 10,
) -> dict:
    """Rank suppliers by total committed purchase-order value.

    Use this for "top 5 suppliers by purchase order value" or "which
    suppliers have we committed the most to". Groups POs by supplier and
    sums Ordered (the committed value, excluding tax).

    NOT the same as aggregate_invoices_by_supplier: that ranks by what was
    INVOICED; this ranks by what was ORDERED. A supplier can top one and
    not the other.

    No date range: PO dates are not filterable on this pod.

    Args:
        status: Optional StatusCode to restrict to, e.g. "OPEN". Bounds
            the fetch server-side. Omit to aggregate every PO.
        top_n: Number of suppliers to return (default 10).

    Returns:
        A "supplier_po_value_ranking" dict: ranked rows of
        {supplier, supplier_id, total_ordered, po_count} plus
        total_suppliers, returned, truncated, and the echoed status.
        Note supplier_id — POs carry no supplier number.
    """
    async with FusionClient(_persona) as client:
        return await _aggregate_purchase_orders_by_supplier(
            client,
            status=status,
            top_n=top_n,
            report_progress=ctx.report_progress,
        )


@mcp.tool()
async def aggregate_purchase_orders_by_status(ctx: Context) -> dict:
    """Break purchase orders down by status: count and value per status.

    Use this for "how many purchase orders are there and what are they
    worth" or "break POs down by status". Groups every PO by StatusCode,
    counting them and summing Ordered per status.

    Takes no filter by design — grouping BY status needs every status, so
    nothing can be pushed to the server. This scans the whole collection
    (~3,362 POs, ~17 pages, about a minute); progress is reported per page.

    Returns:
        A "po_status_breakdown" dict: total_pos, total_ordered, truncated,
        and rows of {status, po_count, total_ordered} ordered by value.
        Statuses on this pod include CLOSED, OPEN, CLOSED FOR RECEIVING,
        REJECTED, PENDING APPROVAL, WITHDRAWN, INCOMPLETE, CLOSED FOR
        INVOICING, PENDING SIGNATURE, CANCELED and ON HOLD — the three
        closed-ish states are distinct and are not merged.
    """
    async with FusionClient(_persona) as client:
        return await _aggregate_purchase_orders_by_status(
            client,
            report_progress=ctx.report_progress,
        )


@mcp.tool()
async def summarize_open_purchase_orders(ctx: Context) -> dict:
    """Committed spend and open-PO count.

    Use this for "how much have we committed in open purchase orders" or
    "what is our open PO commitment". Sums Ordered across open POs and
    counts them.

    Open-only by identity, not by parameter — a summary of another status
    is a different question; use aggregate_purchase_orders_by_status for
    the full breakdown.

    Returns:
        An "open_po_summary" dict: po_count, total_ordered,
        supplier_count, truncated.
    """
    async with FusionClient(_persona) as client:
        return await _summarize_open_purchase_orders(
            client,
            report_progress=ctx.report_progress,
        )


@mcp.tool()
async def compare_purchase_order_to_invoices(
    ctx: Context,
    po_number: str,
) -> dict:
    """Compare what one purchase order ordered against what was invoiced against it.

    Use this for "how does invoiced compare to ordered for PO 162034" or
    "was PO US164932 over- or under-invoiced". Fetches the PO and the
    invoices that reference it, and reports ordered, invoiced, and the
    difference. Both sides are exact — the PO is one record, its invoices
    are server-filtered by PurchaseOrderNumber.

    An over-invoice (invoiced > ordered) is NOT flagged as an error: tax,
    freight and price variances legitimately push an invoice above the
    order. The numbers are reported; judging them is the reader's job.

    Args:
        po_number: The PO's OrderNumber (e.g. "162034") — the number
            printed on the order, which is also the key invoices carry.
            NOT the POHeaderId.

    Returns:
        A "po_invoiced_vs_ordered" dict: order_number, po_header_id,
        supplier, status, ordered, invoiced, difference, invoice_count,
        and the matching invoices. found=False when no such PO exists.
    """
    async with FusionClient(_persona) as client:
        return await _compare_purchase_order_to_invoices(
            client,
            po_number,
            report_progress=ctx.report_progress,
        )


@mcp.tool()
async def compare_supplier_orders_to_invoices(
    ctx: Context,
    supplier_name: str,
    top_n: int = 10,
) -> dict:
    """Compare ordered against invoiced across one supplier's purchase orders.

    Use this for "how does invoiced compare to ordered for Lee Supplies".
    Resolves the supplier by name, then matches its POs against its
    invoices on PurchaseOrderNumber.

    NOTE ON DATA: on this pod most invoices are not PO-linked (debit
    memos, prepayments), so a supplier's PO-matched invoiced total is
    typically far below its total invoiced. unmatched_invoice_count
    reports the non-PO invoices; they are context, not folded into the
    comparison.

    The name must match exactly one supplier. If several match (e.g. "Lee
    Supplies" also matches "Lee Supplies56 2026"), the tool returns
    ambiguous=True with the candidates rather than guessing.

    Args:
        supplier_name: Substring of the supplier's name. Must resolve to
            exactly one supplier.
        top_n: How many PO rows to return, biggest absolute difference
            first. Totals always cover ALL the supplier's POs.

    Returns:
        A "supplier_invoiced_vs_ordered" dict: supplier, supplier_id,
        supplier_number, po_count, invoice_count, total_ordered,
        total_invoiced, total_difference, unmatched_invoice_count,
        returned, truncated, and the top_n rows. found=False when the
        name matches nothing; ambiguous=True when it matches several.
    """
    async with FusionClient(_persona) as client:
        return await _compare_supplier_orders_to_invoices(
            client,
            supplier_name,
            top_n=top_n,
            report_progress=ctx.report_progress,
        )


@mcp.tool()
async def compare_top_suppliers_orders_to_invoices(
    ctx: Context,
    top_n: int = 5,
    status: str | None = None,
) -> dict:
    """Compare ordered vs invoiced for the top-N suppliers by PO value.

    Use this for "how does invoiced compare to ordered for our biggest
    suppliers" or concentration-risk questions ("which suppliers do we
    lean on most, and are their orders getting invoiced"). Ranks
    suppliers by committed PO value, then compares each one's ordered
    against invoiced.

    Its identity is fixed — the top-N suppliers by PO value — so it is a
    bounded tool, not a generic engine. It does NOT compute a
    concentration figure; it reports each supplier's numbers and lets the
    narration phrase the risk.

    NOTE ON DATA: on this pod most invoices are not PO-linked, so
    PO-matched invoiced totals are typically far below total invoiced.
    Each supplier row carries unmatched_invoice_count for context.

    Args:
        top_n: How many suppliers to compare (default 5), ranked by
            committed PO value descending.
        status: Optional StatusCode (e.g. "OPEN") passed to the ranking
            to bound which POs count toward "biggest". Omit to rank
            across all POs.

    Returns:
        A "top_suppliers_invoiced_vs_ordered" dict: status (echoed),
        total_suppliers, returned, truncated, and a suppliers list of
        "supplier_invoiced_vs_ordered" dicts in ranking order.
    """
    async with FusionClient(_persona) as client:
        return await _compare_top_suppliers_orders_to_invoices(
            client,
            top_n=top_n,
            status=status,
            report_progress=ctx.report_progress,
        )

@mcp.tool()
async def get_account_receipt_applications(
    account_id: int,
    limit: int = 10,
) -> dict:
    """Fetch a customer account's receipt applications (cash-to-invoice matching), newest first.

    Use this as the second half of a customer-scoped receipt-applications query:
    after get_customer_account_by_name resolves the customer to an AccountId,
    this returns that account's applications.

    A receipt application is the matching of a receipt (cash received) to an
    invoice (money owed). Each row is PRE-JOINED: it carries the receipt side
    and the transaction side on one record.

    Args:
        account_id: The AccountId of the customer account.
        limit: Max applications to return AFTER filtering (default 25).

    Returns:
        A dict with the account's receipt applications: ApplicationId,
        StandardReceiptId, ReceiptNumber, ReceiptMethod, ReferenceTransactionId,
        ReferenceTransactionNumber, ReferenceTransactionStatus, ApplicationAmount,
        ApplicationDate, ApplicationStatus, EnteredCurrency, and CustomerSite
        per row. Only Applied rows are returned (unapplied cash rows are filtered out).
    """
    async with FusionClient(_persona) as client:
        result = await _get_account_receipt_applications(
            client,
            account_id=account_id,
            limit=limit,
        )
        return result.to_dict()

@mcp.tool()
async def search_standard_receipts(
    customer_name: str | None = None,
    customer_site: str | None = None,
    limit: int = 25,
) -> dict:
    """Search top-level standard receipts (cash received from customers).

    Use for receipt queries that specify both a customer account and a site,
    e.g. "Show receipts for ABC Application Software at Santa Clara".

    Args:
        customer_name: Customer name (e.g. "ABC Application Software"). Resolved
            to account number server-side by the tool.
        customer_site: Customer site (e.g. "Santa Clara"). Applied client-side.
        limit: Max records to return (default 25).
    """
    async with FusionClient(_persona) as client:
        result = await _search_standard_receipts(
            client,
            customer_name=customer_name,
            customer_site=customer_site,
            limit=limit,
        )
        return result.to_dict()

@mcp.tool()
async def rank_customer_accounts_by_exposure(
    top_n: int = 10,
) -> dict:
    """Rank customer accounts by outstanding exposure (open receivables).

    Use for "rank top accounts by outstanding exposure", "top accounts by exposure",
    or "which accounts have the most outstanding receivables".

    Args:
        top_n: Number of accounts to return (default 10).

    Returns:
        A ranking dict with shape "exposure_ranking": rows of account_id,
        account_number, customer_name, open_receivables, transactions_due.
    """
    async with FusionClient(_persona) as client:
        return await _rank_customer_accounts_by_exposure(
            client,
            top_n=top_n,
        )

@mcp.tool()
async def aggregate_standard_receipts_by_method(
    customer_name: str | None = None,
    account_number: str | None = None,
    limit: int | None = None,
) -> dict:
    """Aggregate standard receipts by receipt method.

    Use for "receipt method distribution", "receipts by method", or
    "what payment methods do we receive". Scope to one customer with
    customer_name (or account_number if the number is already known);
    omit both for a pod-wide distribution.

    Args:
        customer_name: Optional customer name to filter. Resolved to an
            account number by the tool.
        account_number: Optional customer account number to filter. Used
            when customer_name is not provided.
        limit: If provided, return only the top N methods by total amount.
            Omit to return all methods.

    Returns:
        A distribution dict with shape "receipt_method_distribution":
        rows of receipt_method, receipt_count, total_amount.
    """
    async with FusionClient(_persona) as client:
        return await _aggregate_standard_receipts_by_method(
            client,
            customer_name=customer_name,
            account_number=account_number,
            limit=limit,
        )
        
if __name__ == "__main__":
    mcp.run(transport="http", host=DEFAULT_HOST, port=DEFAULT_PORT)



