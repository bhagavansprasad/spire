"""SQL overlay — Python structure for the SQL Overlay POC.

Maps Spire's REST vocabulary to the underlying Oracle Fusion physical
database tables. Pure projection: (plan, overlay) -> SQL. No LLM, no DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EntitySpec:
    name: str
    fusion_table: str
    alias: str
    pk_column: str
    select_columns: list[tuple[str, str]] = field(default_factory=list)
    base_joins: list[str] = field(default_factory=list)


@dataclass
class FilterSpec:
    tool_name: str
    arg_name: str
    predicate_template: str
    value_map: dict[str, str] | None = None
    vocab_kind: str | None = None
    requires_join: tuple[str, str] | None = None
    assumption: str | None = None


@dataclass
class JoinSpec:
    from_entity: str
    to_entity: str
    join_clause: str
    assumption: str | None = None


@dataclass
class AggregationSpec:
    """One aggregation tool, compiled to a GROUP BY query."""

    tool_name: str
    base_entity: str
    group_by_column: str
    measure_template: str
    order_desc_by_measure: bool = True
    assumption: str | None = None


@dataclass
class Overlay:
    tool_to_entity: dict[str, str]
    entities: dict[str, EntitySpec]
    filters: dict[tuple[str, str], FilterSpec]
    joins: dict[tuple[str, str], JoinSpec]
    literals: dict[tuple[str, str], str]
    assumptions: dict[str, str]
    aggregations: dict[str, AggregationSpec] = field(default_factory=dict)
    # Tools whose SQL is not a single SELECT: multi-resource
    # reconciliations, cross-resource aggregations that compose
    # something not in one table, and tools that call multiple
    # endpoints and join in Python. The emitter treats these as
    # "covered" for the guardrail invariant, and prints an explicit
    # "not expressible as one SELECT" comment rather than a fake
    # SELECT that would return wrong rows.
    not_expressible: set[str] = field(default_factory=set)


# ─────────────────────────────────────────────────────────────────────
# kg_sql_entity
# ─────────────────────────────────────────────────────────────────────

_ENTITIES = {
    "Supplier": EntitySpec(
        name="Supplier",
        fusion_table="POZ_SUPPLIERS",
        alias="P",
        pk_column="VENDOR_ID",
        select_columns=[
            ("P", "VENDOR_ID"),
            ("P", "SEGMENT1"),
            ("HP", "PARTY_NAME"),
            ("P", "ENABLED_FLAG"),
        ],
        base_joins=[
            "JOIN HZ_PARTIES HP ON HP.PARTY_ID = P.PARTY_ID",
        ],
    ),
    "Address": EntitySpec(
        name="Address",
        fusion_table="HZ_PARTY_SITES",
        alias="PS",
        pk_column="PARTY_SITE_ID",
        select_columns=[
            ("PS", "PARTY_SITE_ID"),
            ("PS", "PARTY_ID"),
            ("L", "ADDRESS1"),
            ("L", "CITY"),
            ("L", "STATE"),
            ("L", "COUNTRY"),
        ],
        base_joins=[
            "JOIN HZ_LOCATIONS L ON L.LOCATION_ID = PS.LOCATION_ID",
        ],
    ),
    "Site": EntitySpec(
        name="Site",
        fusion_table="POZ_SUPPLIER_SITES_ALL_M",
        alias="S",
        pk_column="VENDOR_SITE_ID",
        select_columns=[
            ("S", "VENDOR_SITE_ID"),
            ("S", "VENDOR_SITE_CODE"),
            ("S", "PRC_BU_ID"),
        ],
        base_joins=[],
    ),
    "Classification": EntitySpec(
        name="Classification",
        fusion_table="POZ_BUS_CLASSIFICATIONS",
        alias="C",
        pk_column="CLASSIFICATION_ID",
        select_columns=[
            ("C", "CLASSIFICATION_ID"),
            ("C", "VENDOR_ID"),
            ("C", "LOOKUP_CODE"),
            ("C", "STATUS"),
        ],
        base_joins=[],
    ),
    "Contact": EntitySpec(
        name="Contact",
        fusion_table="POZ_SUPPLIER_CONTACTS",
        alias="CT",
        pk_column="VENDOR_CONTACT_ID",
        select_columns=[
            ("CT", "VENDOR_CONTACT_ID"),
            ("CT", "VENDOR_ID"),
            ("CT", "PARTY_SITE_ID"),
        ],
        base_joins=[],
    ),
    "PurchaseOrder": EntitySpec(
        name="PurchaseOrder",
        fusion_table="PO_HEADERS_ALL",
        alias="P",
        pk_column="PO_HEADER_ID",
        select_columns=[
            ("P", "PO_HEADER_ID"),
            ("P", "SEGMENT1"),
            ("HP", "PARTY_NAME"),
            ("BP", "DISPLAY_NAME"),
            ("P", "AUTHORIZATION_STATUS"),
            ("P", "AMOUNT"),
        ],
        base_joins=[
            "JOIN POZ_SUPPLIERS S ON S.VENDOR_ID = P.VENDOR_ID",
            "JOIN HZ_PARTIES HP ON HP.PARTY_ID = S.PARTY_ID",
            "JOIN PER_ALL_PEOPLE_F BP ON BP.PERSON_ID = P.AGENT_ID "
            "AND SYSDATE BETWEEN BP.EFFECTIVE_START_DATE AND BP.EFFECTIVE_END_DATE",
        ],
    ),
    "Invoice": EntitySpec(
        name="Invoice",
        fusion_table="AP_INVOICES_ALL",
        alias="P",
        pk_column="INVOICE_ID",
        select_columns=[
            ("P", "INVOICE_ID"),
            ("P", "INVOICE_NUM"),
            ("P", "INVOICE_AMOUNT"),
            ("P", "INVOICE_DATE"),
            ("P", "INVOICE_CURRENCY_CODE"),
            ("S", "SEGMENT1"),
            ("P", "PAYMENT_STATUS_FLAG"),
        ],
        base_joins=[
            "JOIN POZ_SUPPLIERS S ON S.VENDOR_ID = P.VENDOR_ID",
        ],
    ),
    "ReceivablesInvoice": EntitySpec(
        name="ReceivablesInvoice",
        fusion_table="RA_CUSTOMER_TRX_ALL",
        alias="P",
        pk_column="CUSTOMER_TRX_ID",
        select_columns=[
            ("P", "CUSTOMER_TRX_ID"),
            ("P", "TRX_NUMBER"),
            ("HP", "PARTY_NAME"),
            ("P", "ENTERED_AMOUNT"),
            ("P", "INVOICE_CURRENCY_CODE"),
            ("P", "TRX_DATE"),
            ("P", "STATUS_TRX"),
        ],
        base_joins=[
            "JOIN HZ_CUST_ACCOUNTS CA ON CA.CUST_ACCOUNT_ID = P.BILL_TO_CUSTOMER_ID",
            "JOIN HZ_PARTIES HP ON HP.PARTY_ID = CA.PARTY_ID",
        ],
    ),
    "PurchaseOrderLine": EntitySpec(
        name="PurchaseOrderLine",
        fusion_table="PO_LINES_ALL",
        alias="L",
        pk_column="PO_LINE_ID",
        select_columns=[
            ("L", "PO_LINE_ID"),
            ("L", "LINE_NUM"),
            ("L", "DESCRIPTION"),
            ("L", "CATEGORY_ID"),
            ("L", "QUANTITY"),
            ("L", "PRICE"),
            ("L", "AMOUNT"),
            ("L", "TOTAL_TAX"),
            ("L", "TOTAL"),
            ("L", "STATUS_LOOKUP_CODE"),
        ],
        base_joins=[],
    ),
    "POSchedule": EntitySpec(
        name="POSchedule",
        fusion_table="PO_LINE_LOCATIONS_ALL",
        alias="S",
        pk_column="LINE_LOCATION_ID",
        select_columns=[
            ("S", "LINE_LOCATION_ID"),
            ("S", "SCHEDULE_NUM"),
            ("S", "SHIP_TO_LOCATION_ID"),
            ("S", "REQUESTED_DELIVERY_DATE"),
            ("S", "QUANTITY"),
            ("S", "AMOUNT"),
            ("S", "SCHEDULE_STATUS"),
            ("S", "RECEIVED_QUANTITY"),
            ("S", "BILLED_QUANTITY"),
        ],
        base_joins=[],
    ),
    "PODistribution": EntitySpec(
        name="PODistribution",
        fusion_table="PO_DISTRIBUTIONS_ALL",
        alias="D",
        pk_column="PO_DISTRIBUTION_ID",
        select_columns=[
            ("D", "PO_DISTRIBUTION_ID"),
            ("D", "DISTRIBUTION_NUM"),
            ("D", "PO_CHARGE_ACCOUNT_ID"),
            ("D", "PERCENTAGE"),
            ("D", "AMOUNT_ORDERED"),
            ("D", "STATUS"),
        ],
        base_joins=[],
    ),
    "ReceivablesInvoiceLine": EntitySpec(
        name="ReceivablesInvoiceLine",
        fusion_table="RA_CUSTOMER_TRX_LINES_ALL",
        alias="L",
        pk_column="CUSTOMER_TRX_LINE_ID",
        select_columns=[
            ("L", "CUSTOMER_TRX_LINE_ID"),
            ("L", "LINE_NUMBER"),
            ("L", "DESCRIPTION"),
            ("L", "QUANTITY_INVOICED"),
            ("L", "UNIT_SELLING_PRICE"),
            ("L", "EXTENDED_AMOUNT"),
        ],
        base_joins=[],
    ),
    "Buyer": EntitySpec(
        name="Buyer",
        fusion_table="PER_ALL_PEOPLE_F",
        alias="B",
        pk_column="PERSON_ID",
        select_columns=[
            ("B", "PERSON_ID"),
            ("B", "EMPLOYEE_NUMBER"),      # PersonNumber
            ("B", "DISPLAY_NAME"),
            ("B", "EMAIL_ADDRESS"),        # WorkEmail
        ],
        base_joins=[],
    ),
    "ReceivablesTaxLine": EntitySpec(
        name="ReceivablesTaxLine",
        fusion_table="RA_CUST_TRX_LINE_GL_DIST_ALL",
        alias="T",
        pk_column="CUST_TRX_LINE_GL_DIST_ID",
        select_columns=[
            ("T", "CUST_TRX_LINE_GL_DIST_ID"),
            ("T", "TAX_LINE_NUMBER"),
            ("T", "TAX_JURISDICTION_CODE"),
            ("T", "TAX_RATE"),
            ("T", "TAX_RATE_CODE"),
            ("T", "TAX_REGIME_CODE"),
            ("T", "TAX"),
            ("T", "AMOUNT"),               # TaxAmount
            ("T", "TAXABLE_AMOUNT"),
        ],
        base_joins=[],
    ),
    "ReceivablesTransactionDFF": EntitySpec(
        name="ReceivablesTransactionDFF",
        fusion_table="RA_CUSTOMER_TRX_ALL",
        alias="D",
        pk_column="CUSTOMER_TRX_ID",
        select_columns=[
            ("D", "CUSTOMER_TRX_ID"),
            ("D", "ATTRIBUTE_CATEGORY"),   # __FLEX_Context
            ("D", "ATTRIBUTE1"),           # first DFF segment (project-specific)
        ],
        base_joins=[],
    ),
    "CreditMemo": EntitySpec(
        name="CreditMemo",
        fusion_table="RA_CUSTOMER_TRX_ALL",
        alias="C",
        pk_column="CUSTOMER_TRX_ID",
        select_columns=[
            ("C", "CUSTOMER_TRX_ID"),
            ("C", "TRX_NUMBER"),
            ("C", "TRX_DATE"),
            ("C", "ENTERED_AMOUNT"),
            ("C", "INVOICE_CURRENCY_CODE"),
            ("C", "STATUS_TRX"),
        ],
        base_joins=[],
    ),
    "CustomerAccount": EntitySpec(
        name="CustomerAccount",
        fusion_table="HZ_CUST_ACCOUNTS",
        alias="CA",
        pk_column="CUST_ACCOUNT_ID",
        select_columns=[
            ("CA", "CUST_ACCOUNT_ID"),      # AccountId
            ("CA", "ACCOUNT_NUMBER"),
            ("HP", "PARTY_NAME"),           # CustomerName
            # Balances live on a related view on the pod; the account
            # row does not carry them directly. Leave out of the base
            # SELECT until verified against the physical view name.
        ],
        base_joins=[
            "JOIN HZ_PARTIES HP ON HP.PARTY_ID = CA.PARTY_ID",
        ],
    ),
    "CustomerTransaction": EntitySpec(
        name="CustomerTransaction",
        fusion_table="AR_PAYMENT_SCHEDULES_ALL",
        alias="T",
        pk_column="PAYMENT_SCHEDULE_ID",
        select_columns=[
            ("T", "PAYMENT_SCHEDULE_ID"),   # InstallmentId
            ("T", "TRX_NUMBER"),            # TransactionNumber
            ("T", "CLASS"),                 # TransactionClass
            ("T", "TRX_DATE"),              # TransactionDate
            ("T", "DUE_DATE"),              # PaymentScheduleDueDate
            ("T", "AMOUNT_DUE_ORIGINAL"),   # TotalOriginalAmount
            ("T", "AMOUNT_DUE_REMAINING"),  # TotalBalanceAmount
            ("T", "STATUS"),                # InstallmentStatus
        ],
        base_joins=[],
    ),
    "AccountCreditMemo": EntitySpec(
        name="AccountCreditMemo",
        fusion_table="AR_PAYMENT_SCHEDULES_ALL",
        alias="T",
        pk_column="PAYMENT_SCHEDULE_ID",
        select_columns=[
            ("T", "PAYMENT_SCHEDULE_ID"),   # InstallmentId (the pod's CreditMemoId)
            ("T", "TRX_NUMBER"),            # CreditMemoNumber
            ("T", "TRX_DATE"),              # CreditMemoDate
            ("T", "AMOUNT_DUE_ORIGINAL"),   # TotalOriginalAmount (normally negative)
            ("T", "AMOUNT_DUE_REMAINING"),  # TotalBalanceAmount
            ("T", "STATUS"),                # CreditMemoStatus
            ("T", "INVOICE_CURRENCY_CODE"), # CreditMemoCurrency
            ("T", "CLASS"),                 # TransactionClass
        ],
        base_joins=[],
    ),
    "AccountReceipt": EntitySpec(
        name="AccountReceipt",
        fusion_table="AR_CASH_RECEIPTS_ALL",
        alias="R",
        pk_column="CASH_RECEIPT_ID",
        select_columns=[
            ("R", "CASH_RECEIPT_ID"),       # StandardReceiptId
            ("R", "RECEIPT_NUMBER"),
            ("R", "RECEIPT_DATE"),
            ("R", "AMOUNT"),
            ("R", "CURRENCY_CODE"),         # Currency
            ("R", "RECEIPT_METHOD_ID"),     # ReceiptMethod (join to AR_RECEIPT_METHODS for display)
            ("R", "STATUS"),                # State (Applied/Unapplied)
            ("R", "AMOUNT_APPLIED"),        # derive UnappliedAmount = AMOUNT - AMOUNT_APPLIED
        ],
        base_joins=[],
    ),
    "AccountReceiptApplication": EntitySpec(
        name="AccountReceiptApplication",
        fusion_table="AR_RECEIVABLE_APPLICATIONS_ALL",
        alias="A",
        pk_column="RECEIVABLE_APPLICATION_ID",
        select_columns=[
            ("A", "RECEIVABLE_APPLICATION_ID"),  # ApplicationId
            ("A", "APPLY_DATE"),                 # ApplicationDate
            ("A", "AMOUNT_APPLIED"),             # ApplicationAmount
            ("A", "STATUS"),                     # ApplicationStatus (Applied/Unapplied)
            ("A", "CASH_RECEIPT_ID"),            # StandardReceiptId
            ("A", "PAYMENT_SCHEDULE_ID"),        # ReferenceInstallmentId
        ],
        base_joins=[],
    ),
    "StandardReceipt": EntitySpec(
        name="StandardReceipt",
        fusion_table="AR_CASH_RECEIPTS_ALL",
        alias="R",
        pk_column="CASH_RECEIPT_ID",
        select_columns=[
            ("R", "CASH_RECEIPT_ID"),
            ("R", "RECEIPT_NUMBER"),
            ("R", "RECEIPT_DATE"),
            ("R", "AMOUNT"),
            ("R", "CURRENCY_CODE"),
            ("R", "RECEIPT_METHOD_ID"),
            ("R", "STATUS"),
            ("HP", "PARTY_NAME"),
        ],
        base_joins=[
            "JOIN HZ_CUST_ACCOUNTS CA ON CA.CUST_ACCOUNT_ID = R.PAY_FROM_CUSTOMER",
            "JOIN HZ_PARTIES HP ON HP.PARTY_ID = CA.PARTY_ID",
        ],
    ),
}


# ─────────────────────────────────────────────────────────────────────
# kg_sql_filter
# ─────────────────────────────────────────────────────────────────────

_FILTERS = {
    # Supplier filters
    ("search_suppliers", "status"): FilterSpec(
        tool_name="search_suppliers",
        arg_name="status",
        predicate_template="{alias}.ENABLED_FLAG = {value}",
        value_map={"ACTIVE": "'Y'", "INACTIVE": "'N'"},
        assumption="status_maps_to_enabled_flag",
    ),
    ("search_suppliers", "country"): FilterSpec(
        tool_name="search_suppliers",
        arg_name="country",
        predicate_template="L.COUNTRY = {value}",
        requires_join=("Supplier", "Address"),
        assumption="address_join_for_country",
    ),
    ("search_suppliers", "supplier_name_contains"): FilterSpec(
        tool_name="search_suppliers",
        arg_name="supplier_name_contains",
        predicate_template="HP.PARTY_NAME LIKE {value}",
        assumption="name_like_on_party_name",
    ),
    ("search_suppliers_by_site_bu", "business_unit"): FilterSpec(
        tool_name="search_suppliers_by_site_bu",
        arg_name="business_unit",
        predicate_template="{alias}.PRC_BU_ID = {value}",
        vocab_kind="supplier_site_bu",
        assumption="bu_literal_from_overlay",
    ),
    ("search_suppliers_by_classification", "classification"): FilterSpec(
        tool_name="search_suppliers_by_classification",
        arg_name="classification",
        predicate_template="{alias}.LOOKUP_CODE = {value}",
        vocab_kind="supplier_classification",
        assumption="classification_literal_from_overlay",
    ),
    
    # PurchaseOrder filters
    ("search_purchase_orders", "status"): FilterSpec(
        tool_name="search_purchase_orders",
        arg_name="status",
        predicate_template="{alias}.AUTHORIZATION_STATUS = {value}",
        assumption="po_status_maps_to_authorization_status",
    ),
    ("search_purchase_orders", "supplier_id"): FilterSpec(
        tool_name="search_purchase_orders",
        arg_name="supplier_id",
        # The planner routes an all-digit value here as a SupplierNumber.
        # Join through POZ_SUPPLIERS to match on SEGMENT1, not the raw
        # VENDOR_ID, which is a numeric internal id.
        predicate_template=(
            "P.VENDOR_ID IN (SELECT VENDOR_ID FROM POZ_SUPPLIERS "
            "WHERE SEGMENT1 = {value})"
        ),
        assumption="supplier_number_not_vendor_id",
    ),

    # Invoice filters
    ("search_invoices", "supplier_number"): FilterSpec(
        tool_name="search_invoices",
        arg_name="supplier_number",
        predicate_template="S.SEGMENT1 = {value}",
        requires_join=("Invoice", "Supplier"),
        assumption="invoice_supplier_maps_to_segment1",
    ),
    ("search_invoices", "invoice_date_after"): FilterSpec(
        tool_name="search_invoices",
        arg_name="invoice_date_after",
        predicate_template="{alias}.INVOICE_DATE >= {value}",
        assumption="invoice_date_filter",
    ),
    
    # AR Invoice filters
    ("get_receivables_invoice_by_id", "customer_transaction_id"): FilterSpec(
        tool_name="get_receivables_invoice_by_id",
        arg_name="customer_transaction_id",
        predicate_template="{alias}.CUSTOMER_TRX_ID = {value}",
        assumption="ar_id_maps_to_customer_trx_id",
    ),

    # PO child fetchers (Phase 1)
    ("get_purchase_order_lines", "po_header_id"): FilterSpec(
        tool_name="get_purchase_order_lines",
        arg_name="po_header_id",
        predicate_template="{alias}.PO_HEADER_ID = {value}",
        assumption="po_child_by_header_id",
    ),
    ("get_purchase_order_schedules", "po_header_id"): FilterSpec(
        tool_name="get_purchase_order_schedules",
        arg_name="po_header_id",
        predicate_template="{alias}.PO_HEADER_ID = {value}",
        assumption="po_schedule_columns_from_reference",
    ),
    ("get_purchase_order_distributions", "po_header_id"): FilterSpec(
        tool_name="get_purchase_order_distributions",
        arg_name="po_header_id",
        predicate_template=(
            "{alias}.PO_HEADER_ID = {value} "
            "AND {alias}.PO_LINE_ID = :po_line_id "
            "AND {alias}.LINE_LOCATION_ID = :line_location_id"
        ),
        assumption="po_distribution_three_way_filter",
    ),

    # AR child fetchers (Phase 1)
    ("get_receivables_invoice_lines", "customer_transaction_id"): FilterSpec(
        tool_name="get_receivables_invoice_lines",
        arg_name="customer_transaction_id",
        predicate_template="{alias}.CUSTOMER_TRX_ID = {value}",
        assumption="ar_line_by_customer_trx_id",
    ),

    # PO by-id fetcher (Phase 1b)
    ("get_purchase_order_by_id", "po_header_id"): FilterSpec(
        tool_name="get_purchase_order_by_id",
        arg_name="po_header_id",
        predicate_template="{alias}.PO_HEADER_ID = {value}",
        assumption="po_by_id",
    ),

    # Phase 2 filters
    ("get_buyer", "buyer_id"): FilterSpec(
        tool_name="get_buyer",
        arg_name="buyer_id",
        predicate_template="{alias}.PERSON_ID = {value}",
        assumption="buyer_person_id",
    ),
    ("get_receivables_invoice_tax_lines", "customer_transaction_id"): FilterSpec(
        tool_name="get_receivables_invoice_tax_lines",
        arg_name="customer_transaction_id",
        predicate_template=(
            "{alias}.CUSTOMER_TRX_ID = {value} "
            "AND {alias}.CUST_TRX_LINE_ID = :line_id "
            "AND {alias}.ACCOUNT_CLASS = 'TAX'"
        ),
        assumption="ar_tax_line_filter",
    ),
    ("get_receivables_invoice_transaction_dff", "customer_transaction_id"): FilterSpec(
        tool_name="get_receivables_invoice_transaction_dff",
        arg_name="customer_transaction_id",
        predicate_template="{alias}.CUSTOMER_TRX_ID = {value}",
        assumption="ar_dff_columns_uncertain",
    ),
    # list_receivables_credit_memos takes no filter; it is a top-N list.
    # The WHERE clause is supplied by a base join on TRX_CLASS (below).

    # Phase 3 filters
    ("get_customer_account_by_name", "customer_name"): FilterSpec(
        tool_name="get_customer_account_by_name",
        arg_name="customer_name",
        predicate_template="HP.PARTY_NAME = {value}",
        assumption="customer_account_by_party_name",
    ),
    ("get_customer_transactions", "account_id"): FilterSpec(
        tool_name="get_customer_transactions",
        arg_name="account_id",
        predicate_template="{alias}.CUSTOMER_ID = {value}",
        assumption="customer_transaction_by_customer_id",
    ),
    ("get_account_credit_memos", "account_id"): FilterSpec(
        tool_name="get_account_credit_memos",
        arg_name="account_id",
        predicate_template=(
            "{alias}.CUSTOMER_ID = {value} AND {alias}.CLASS = 'CM'"
        ),
        assumption="account_credit_memo_by_customer_class",
    ),
    ("get_account_receipts", "account_id"): FilterSpec(
        tool_name="get_account_receipts",
        arg_name="account_id",
        predicate_template=(
            "{alias}.PAY_FROM_CUSTOMER = {value}"
        ),
        assumption="account_receipt_by_pay_from_customer",
    ),
    ("get_account_receipt_applications", "account_id"): FilterSpec(
        tool_name="get_account_receipt_applications",
        arg_name="account_id",
        predicate_template=(
            "{alias}.CUSTOMER_TRX_ID IN "
            "(SELECT TRX_ID FROM RA_CUSTOMER_TRX_ALL WHERE BILL_TO_CUSTOMER_ID = {value})"
        ),
        assumption="account_receipt_application_by_customer",
    ),
    ("search_standard_receipts", "customer_name"): FilterSpec(
        tool_name="search_standard_receipts",
        arg_name="customer_name",
        predicate_template="HP.PARTY_NAME = {value}",
        assumption="standard_receipt_by_customer_name",
    ),
    ("search_standard_receipts", "customer_site"): FilterSpec(
        tool_name="search_standard_receipts",
        arg_name="customer_site",
        predicate_template="{alias}.CUSTOMER_SITE = {value}",
        assumption="standard_receipt_site_client_side",
    ),
}


# ─────────────────────────────────────────────────────────────────────
# kg_sql_join
# ─────────────────────────────────────────────────────────────────────

_JOINS = {
    ("Supplier", "Address"): JoinSpec(
        from_entity="Supplier",
        to_entity="Address",
        join_clause=(
            "LEFT JOIN HZ_PARTY_SITES PS ON PS.PARTY_ID = P.PARTY_ID\n"
            "LEFT JOIN HZ_LOCATIONS L ON L.LOCATION_ID = PS.LOCATION_ID"
        ),
        assumption="address_join_for_country",
    ),
    ("Invoice", "Supplier"): JoinSpec(
        from_entity="Invoice",
        to_entity="Supplier",
        join_clause="JOIN POZ_SUPPLIERS S ON S.VENDOR_ID = P.VENDOR_ID",
        assumption="invoice_supplier_join",
    ),
}


# ─────────────────────────────────────────────────────────────────────
# kg_sql_literal — seeded from the live pod
# ─────────────────────────────────────────────────────────────────────

_LITERALS = {
    ("supplier_site_bu", "US1 Business Unit"): "300000046987012",
    ("supplier_site_bu", "Australia Business Unit"): "300000047826661",
    ("supplier_site_bu", "India Business Unit"): "300000047826665",
    ("supplier_site_bu", "Japan Business Unit"): "300000047826669",
    ("supplier_classification", "Small Business"): "'SMALL_BUSINESS'",
    ("supplier_classification", "Woman Owned"): "'WOMAN_OWNED'",
}


# ─────────────────────────────────────────────────────────────────────
# kg_sql_assumption
# ─────────────────────────────────────────────────────────────────────

_ASSUMPTIONS = {
    "status_maps_to_enabled_flag": (
        "Supplier ACTIVE/INACTIVE maps to POZ_SUPPLIERS.ENABLED_FLAG "
        "('Y'/'N')."
    ),
    "address_join_for_country": (
        "Supplier country lives on the child address. "
        "Join: POZ_SUPPLIERS.PARTY_ID -> HZ_PARTY_SITES.PARTY_ID -> "
        "HZ_LOCATIONS.LOCATION_ID."
    ),
    "name_like_on_party_name": (
        "Supplier name filter is applied as a LIKE on "
        "HZ_PARTIES.PARTY_NAME, not POZ_SUPPLIERS.SEGMENT1."
    ),
    "po_status_maps_to_authorization_status": (
        "PO StatusCode maps to PO_HEADERS_ALL.AUTHORIZATION_STATUS. "
        "Confirmed valid values on fa-euth-dev93: 'OPEN', 'CLOSED', "
        "'CLOSED FOR RECEIVING', 'PENDING APPROVAL'."
    ),
    "supplier_maps_to_vendor_id": (
        "SupplierId maps to PO_HEADERS_ALL.VENDOR_ID."
    ),
    "supplier_number_not_vendor_id": (
        "The search_purchase_orders tool takes a supplier reference that "
        "may be a SupplierNumber (all-digit string like '1252') OR a "
        "SupplierId (numeric internal id). The plan's supplier_id arg is "
        "assumed to be a SupplierNumber, so the filter joins through "
        "POZ_SUPPLIERS.SEGMENT1 rather than comparing against "
        "PO_HEADERS_ALL.VENDOR_ID directly. If this returns 0 rows on a "
        "real pod, the value is a numeric SupplierId and the filter "
        "should fall back to a direct VENDOR_ID comparison."
    ),
    "invoice_supplier_maps_to_segment1": (
        "SupplierNumber maps to POZ_SUPPLIERS.SEGMENT1."
    ),
    "invoice_date_filter": (
        "InvoiceDate filters against AP_INVOICES_ALL.INVOICE_DATE."
    ),
    "ar_id_maps_to_customer_trx_id": (
        "AR CustomerTransactionId maps to "
        "RA_CUSTOMER_TRX_ALL.CUSTOMER_TRX_ID."
    ),
    "bu_literal_from_overlay": (
        "Business-unit name resolves to a numeric BU_ID from "
        "kg_sql_literal."
    ),
    "classification_literal_from_overlay": (
        "Classification display string resolves to a LOOKUP_CODE via "
        "kg_sql_literal."
    ),
    "party_type_not_filtered": (
        "POZ_SUPPLIERS.PARTY_ID is assumed to point at an organization "
        "row only; no HZ_PARTIES.PARTY_TYPE predicate is emitted."
    ),
    "contact_party_site_id": (
        "Contact joins via PARTY_SITE_ID, not ORG_PARTY_SITE_ID."
    ),
    "invoice_supplier_join": (
        "AP invoice joins to supplier via VENDOR_ID on both sides."
    ),
    "po_child_by_header_id": (
        "PO line child filters on PO_HEADER_ID. Confirmed via curl "
        "against PO 55269 (POHeaderId 2055): the line body carries "
        "POHeaderId and the projection includes POLineId, LineNumber, "
        "Description, Category, Quantity, Price, Ordered, TotalTax, "
        "Total, and Status."
    ),
    "po_schedule_columns_from_reference": (
        "PO schedule columns taken from the endpoint reference, not "
        "confirmed via curl against this pod. Column names are: "
        "LINE_LOCATION_ID, SCHEDULE_NUM, SHIP_TO_LOCATION_ID, "
        "REQUESTED_DELIVERY_DATE, QUANTITY, AMOUNT, SCHEDULE_STATUS, "
        "RECEIVED_QUANTITY, BILLED_QUANTITY. If execution fails, curl "
        "/purchaseOrderSchedules and update the spec."
    ),
    "po_distribution_three_way_filter": (
        "PO distribution requires three ids from the parent schedule "
        "row: POHeaderId, POLineId, LineLocationId. The filter template "
        "uses {value} for PO_HEADER_ID and named binds for the other "
        "two. The plan's tool_args must supply all three."
    ),
    "ar_line_by_customer_trx_id": (
        "AR line child filters on CUSTOMER_TRX_ID (the AR invoice's "
        "parent id, per the endpoint path "
        "/receivablesInvoices/{id}/child/receivablesInvoiceLines). "
        "Column names are: CUSTOMER_TRX_LINE_ID, LINE_NUMBER, "
        "DESCRIPTION, QUANTITY_INVOICED, UNIT_SELLING_PRICE, "
        "EXTENDED_AMOUNT."
    ),
    "po_by_id": (
        "get_purchase_order_by_id fetches one PO by PO_HEADER_ID (the "
        "numeric internal id, not OrderNumber). Confirmed against the "
        "pod: /purchaseOrders/2055 returns PO 55269."
    ),
    "buyer_person_id": (
        "get_buyer looks up PER_ALL_PEOPLE_F by PERSON_ID. Confirmed "
        "via curl against PERSON_ID 300000047340498: returns DISPLAY_NAME "
        "'Calvin Roth', EMPLOYEE_NUMBER '3', EMAIL_ADDRESS "
        "'CALVIN.ROTH_euth-dev93@oraclepdemos.com'."
    ),
    "ar_tax_line_filter": (
        "AR tax lines come from RA_CUST_TRX_LINE_GL_DIST_ALL filtered "
        "to ACCOUNT_CLASS = 'TAX'. Confirmed via curl against AR "
        "invoice 1002, line 74: two tax rows (COUNTY 2.25%, STATE 6.5%) "
        "with their own CUST_TRX_LINE_GL_DIST_IDs (112, 113) - distinct "
        "from the parent invoice line (74). The filter takes two ids: "
        "customer_transaction_id and the parent line_id (named bind). "
        "The physical column name for the parent line id is not "
        "confirmed; if execution fails, curl the AR endpoint and update."
    ),
    "ar_dff_columns_uncertain": (
        "AR transaction DFF is projected as ATTRIBUTE_CATEGORY (the "
        "flexfield context, matching __FLEX_Context in REST) and "
        "ATTRIBUTE1 (the first segment). The physical DFF column names "
        "are pod-specific; on this pod the context is 'DOO' but no "
        "segment values are populated, so the mapping cannot be "
        "confirmed end-to-end until a pod with populated DFF is "
        "available. If a future prompt reveals different column names, "
        "update the select_columns on ReceivablesTransactionDFF."
    ),
    "customer_account_by_party_name": (
        "get_customer_account_by_name resolves HZ_CUST_ACCOUNTS joined "
        "to HZ_PARTIES on PARTY_ID, filtered by PARTY_NAME. Confirmed "
        "via curl: q=CustomerName='ABC Corporation Americas' returns "
        "AccountId 300000047368527, AccountNumber 26370."
    ),
    "customer_transaction_by_customer_id": (
        "get_customer_transactions reads AR_PAYMENT_SCHEDULES_ALL "
        "filtered by CUSTOMER_ID (the AR account id, not the PartyId). "
        "Confirmed via curl against account 300000047368527: two rows "
        "returned with TransactionClass='Invoice'. The physical "
        "CUSTOMER_ID column holds the account's CUST_ACCOUNT_ID."
    ),
    "account_credit_memo_by_customer_class": (
        "get_account_credit_memos reads the same AR_PAYMENT_SCHEDULES_ALL "
        "but filters CLASS='CM' (credit memo), which is the physical "
        "code that REST exposes as TransactionClass='On Account Credit "
        "Memo'. Confirmed via curl: two rows returned with "
        "CreditMemoStatus='Closed' and TotalOriginalAmount negative."
    ),
    "account_receipt_by_pay_from_customer": (
        "get_account_receipts reads AR_CASH_RECEIPTS_ALL filtered by "
        "PAY_FROM_CUSTOMER (the account id). Confirmed via curl: two "
        "rows returned with State='Applied'. STATUS holds the state "
        "value; AMOUNT_APPLIED is the applied portion, so the "
        "unapplied remainder is AMOUNT - AMOUNT_APPLIED."
    ),
    "account_receipt_application_by_customer": (
        "get_account_receipt_applications reads "
        "AR_RECEIVABLE_APPLICATIONS_ALL. The table does not carry a "
        "direct account id column, so the filter reaches the account "
        "through its parent transaction: CUSTOMER_TRX_ID IN "
        "(SELECT TRX_ID FROM RA_CUSTOMER_TRX_ALL WHERE "
        "BILL_TO_CUSTOMER_ID = ?). Confirmed via curl: two rows "
        "returned, one Applied (ReferenceTransactionId populated) and "
        "one Unapplied (ReferenceTransaction* null). The tool's own "
        "client_filters discard Unapplied rows; the emitted SQL does "
        "not add that filter because the tool does it downstream."
    ),
    "standard_receipt_by_customer_name": (
        "search_standard_receipts resolves customer_name to an account "
        "number in the tool, then filters AR_CASH_RECEIPTS_ALL. The "
        "physical table does not carry PARTY_NAME directly; the join "
        "to HZ_CUST_ACCOUNTS and HZ_PARTIES supplies it."
    ),
    "standard_receipt_site_client_side": (
        "customer_site on AR_CASH_RECEIPTS_ALL is populated but "
        "sparse; the tool matches it client-side. The emitted SQL adds "
        "CUSTOMER_SITE = ? to the WHERE clause."
    ),
    "aggregation_measures": (
        "Every aggregation tool selects a grouped column and a SUM or "
        "COUNT over a measure column on the base entity. Where a tool "
        "computes a RATIO or DISTINCT count not derivable as SUM/COUNT "
        "on one column, it is listed in not_expressible instead."
    ),
}


OVERLAY = Overlay(
    tool_to_entity={
        "search_suppliers": "Supplier",
        "search_suppliers_by_site_bu": "Site",
        "search_suppliers_by_classification": "Classification",
        "search_addresses": "Address",
        "get_supplier_contacts": "Contact",
        "search_purchase_orders": "PurchaseOrder",
        "get_purchase_order_by_id": "PurchaseOrder",
        "search_invoices": "Invoice",
        "get_receivables_invoice_by_id": "ReceivablesInvoice",
        "get_purchase_order_lines": "PurchaseOrderLine",
        "get_purchase_order_schedules": "POSchedule",
        "get_purchase_order_distributions": "PODistribution",
        "get_receivables_invoice_lines": "ReceivablesInvoiceLine",
        "get_buyer": "Buyer",
        "get_receivables_invoice_tax_lines": "ReceivablesTaxLine",
        "get_receivables_invoice_transaction_dff": "ReceivablesTransactionDFF",
        "list_receivables_credit_memos": "CreditMemo",
        "get_customer_account_by_name": "CustomerAccount",
        "get_customer_transactions": "CustomerTransaction",
        "get_account_credit_memos": "AccountCreditMemo",
        "get_account_receipts": "AccountReceipt",
        "get_account_receipt_applications": "AccountReceiptApplication",
        "search_standard_receipts": "StandardReceipt",
    },
    entities=_ENTITIES,
    filters=_FILTERS,
    joins=_JOINS,
    literals=_LITERALS,
    assumptions=_ASSUMPTIONS,
    aggregations={
        "aggregate_invoices_by_supplier": AggregationSpec(
            tool_name="aggregate_invoices_by_supplier",
            base_entity="Invoice",
            group_by_column="VENDOR_ID",
            measure_template="SUM(INVOICE_AMOUNT)",
            assumption="aggregation_measures",
        ),
        "aggregate_purchase_orders_by_status": AggregationSpec(
            tool_name="aggregate_purchase_orders_by_status",
            base_entity="PurchaseOrder",
            group_by_column="AUTHORIZATION_STATUS",
            measure_template="SUM(AMOUNT)",
            order_desc_by_measure=False,
            assumption="aggregation_measures",
        ),
        "aggregate_standard_receipts_by_method": AggregationSpec(
            tool_name="aggregate_standard_receipts_by_method",
            base_entity="StandardReceipt",
            group_by_column="RECEIPT_METHOD_ID",
            measure_template="SUM(AMOUNT)",
            order_desc_by_measure=False,
            assumption="aggregation_measures",
        ),
        "rank_invoices_by_amount": AggregationSpec(
            tool_name="rank_invoices_by_amount",
            base_entity="Invoice",
            group_by_column="INVOICE_ID",
            measure_template="SUM(INVOICE_AMOUNT)",
            assumption="aggregation_measures",
        ),
    },
    not_expressible={
        "get_purchase_order_lifecycle_status",
        "compare_purchase_order_to_invoices",
        "compare_supplier_orders_to_invoices",
        "compare_top_suppliers_orders_to_invoices",
        "aggregate_purchase_orders_by_supplier",
        "rank_customer_accounts_by_exposure",
        "summarize_open_purchase_orders",
    },
)


__all__ = [
    "EntitySpec",
    "FilterSpec",
    "JoinSpec",
    "Overlay",
    "OVERLAY",
]
