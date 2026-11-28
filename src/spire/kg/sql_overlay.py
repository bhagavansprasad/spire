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
    # Derived projections (correlated scalar subqueries) appended verbatim
    # to the SELECT list after select_columns. Populated only by the
    # KG-backed overlay builder (spire.rendering.sql_emitter); the
    # hand-authored entities leave this empty.
    derived_columns: list[str] = field(default_factory=list)
    # Predicates that constrain the entity to the dataset REST can see
    # (F-076), as opposed to filtering on what the user asked for. Seeded
    # into the WHERE clause of every statement over this entity, before
    # the per-arg filters. `{alias}` is formatted in by the emitter.
    #
    # These are data-access facts, not business rules: REST is scoped by
    # the integration user's security profile, which no column encodes.
    # An empty list (the default) leaves the entity unscoped.
    scope_predicates: list[str] = field(default_factory=list)
    # Assumption text key explaining WHY the scope is applied, surfaced in
    # the emitted SQL comment block so a reader can see the rows were
    # restricted deliberately rather than by a mistaken filter.
    scope_assumption: str | None = None


@dataclass
class FilterSpec:
    tool_name: str
    arg_name: str
    predicate_template: str
    value_map: dict[str, str] | None = None
    vocab_kind: str | None = None
    requires_join: tuple[str, str] | None = None
    assumption: str | None = None
    match_mode: str | None = None


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
    # Arg name (in step.tool_args) that carries the top-N limit. When
    # set, the emitter emits FETCH FIRST N ROWS ONLY after the ORDER BY,
    # and skips this arg in the filter loop (it is a limit, not a WHERE).
    top_n_arg: str | None = None
    # Arg names to silently skip in the filter loop: args the tool takes
    # that are neither filters nor limits. Used for fetch caps (e.g.
    # 'limit') that bound the FETCH, not the result set.
    skip_args: set[str] = field(default_factory=set)


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
    sql_control_args: set[str] = field(default_factory=set)
    sql_disabled_args: dict[tuple[str, str], str] = field(default_factory=dict)


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
            ("PS", "VENDOR_ID"),
            ("CT", "PARTY_SITE_ID"),
        ],
        base_joins=[
            "JOIN POZ_SUPPLIER_SITES_ALL_M PS ON PS.PARTY_SITE_ID = CT.ORG_PARTY_SITE_ID",
        ],
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
            ("PN", "DISPLAY_NAME"),
            ("P", "AUTHORIZATION_STATUS"),
            ("P", "AMOUNT"),
        ],
        base_joins=[
            "JOIN POZ_SUPPLIERS S ON S.VENDOR_ID = P.VENDOR_ID",
            "JOIN HZ_PARTIES HP ON HP.PARTY_ID = S.PARTY_ID",
            "JOIN PER_ALL_PEOPLE_F BP ON BP.PERSON_ID = P.AGENT_ID "
            "AND SYSDATE BETWEEN BP.EFFECTIVE_START_DATE AND BP.EFFECTIVE_END_DATE",
            "JOIN PER_PERSON_NAMES_F PN ON PN.PERSON_ID = BP.PERSON_ID "
            "AND PN.NAME_TYPE = 'GLOBAL' "
            "AND SYSDATE BETWEEN PN.EFFECTIVE_START_DATE AND PN.EFFECTIVE_END_DATE",
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
            # F-083: LEFT, not INNER. AP_INVOICES_ALL.VENDOR_ID is never
            # NULL, but 11,227 of 53,129 rows carry a VENDOR_ID with no
            # POZ_SUPPLIERS row (the sentinel -222 among them), so an
            # inner join silently dropped 21% of invoices — with no NULL
            # to show for it. REST returns those invoices with a supplier
            # name and a null SupplierNumber.
            #
            # SupplierNumber therefore comes through as NULL here, which
            # is what REST reports. The supplier NAME lives on the invoice
            # itself: AP_INVOICES_ALL.PARTY_ID -> HZ_PARTIES.PARTY_NAME
            # returns 'TEXAS CORP' / 'Info-Systems Pvt Ltd' for the two
            # sentinel rows and agrees with the supplier path on normal
            # invoices. (Joining POZ_SUPPLIERS here is about SEGMENT1
            # only; the party name is not projected by this entity.)
            "LEFT JOIN POZ_SUPPLIERS S ON S.VENDOR_ID = P.VENDOR_ID",
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
    # p15 (2026-11-28). AP invoice holds. Expressible as one SELECT, and more
    # accurately than the REST tool: SQL joins on INVOICE_ID, where REST only
    # exposes InvoiceNumber and needs the Supplier to disambiguate (6 invoice
    # numbers repeat across suppliers on this pod, and invoice 1122 is
    # 295,759.13 at one supplier and 2,000 at another).
    #
    # The join is LEFT because 2 of the 376 active holds are orphans: their
    # INVOICE_ID has no AP_INVOICES_ALL row. An inner join would drop them and
    # the answer would silently under-count the active holds.
    #
    # HoldStatus is not a column — the pod carries only the release pair — so
    # it comes from kg_derived_projection as a CASE over RELEASE_REASON, which
    # is the same test the REST predicate uses.
    "InvoiceHold": EntitySpec(
        name="InvoiceHold",
        fusion_table="AP_HOLDS_ALL",
        alias="H",
        pk_column="HOLD_ID",
        select_columns=[
            ("H", "HOLD_ID"),
            ("H", "HOLD_LOOKUP_CODE"),
            ("H", "HOLD_REASON"),
            ("H", "HOLD_DATE"),
            ("H", "WF_STATUS"),
            ("H", "RELEASE_REASON"),
            ("I", "INVOICE_NUM"),
            ("I", "INVOICE_AMOUNT"),
        ],
        base_joins=[
            "LEFT JOIN AP_INVOICES_ALL I ON I.INVOICE_ID = H.INVOICE_ID",
        ],
        # The entity Spire exposes IS the active holds, not the released
        # history: RELEASE_REASON IS NULL is the definition, the same test the
        # REST tool's server clause uses. It therefore belongs here rather
        # than on an optional argument — an arg-keyed filter would silently
        # vanish whenever the planner did not pass the arg, and the emitted
        # SQL would then return all 14,772 holds while the answer claimed to
        # list the active ones. That is the executes-but-wrong shape this
        # codebase has removed before, so the predicate is unconditional.
        scope_predicates=["{alias}.RELEASE_REASON IS NULL"],
    ),

    # F-077: AP invoice lines. The six columns the prompt asks for are all
    # populated on this pod (verified against invoice 1601397), and
    # (INVOICE_ID, LINE_NUMBER) is unique across all 1,335,566 rows — so it
    # is the identity of a line. AP_INVOICE_LINES_ALL exposes no
    # INVOICE_LINE_ID column on dev49, so LINE_NUMBER carries the pk role.
    "InvoiceLine": EntitySpec(
        name="InvoiceLine",
        fusion_table="AP_INVOICE_LINES_ALL",
        alias="L",
        pk_column="LINE_NUMBER",
        select_columns=[
            ("L", "LINE_NUMBER"),
            ("L", "DESCRIPTION"),
            ("L", "QUANTITY_INVOICED"),
            ("L", "UNIT_PRICE"),
            ("L", "AMOUNT"),
            ("L", "LINE_TYPE_LOOKUP_CODE"),
            ("L", "ITEM_DESCRIPTION"),
            ("L", "UNIT_MEAS_LOOKUP_CODE"),
            ("L", "ACCOUNTING_DATE"),
            ("L", "ASSESSABLE_VALUE"),
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
            ("B", "PERSON_NUMBER"),
            ("PN", "DISPLAY_NAME"),
            ("EA", "EMAIL_ADDRESS"),
        ],
        base_joins=[
            "JOIN PER_PERSON_NAMES_F PN ON PN.PERSON_ID = B.PERSON_ID "
            "AND PN.NAME_TYPE = 'GLOBAL'",
            "JOIN PER_EMAIL_ADDRESSES EA ON EA.EMAIL_ADDRESS_ID = B.PRIMARY_EMAIL_ID",
        ],
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
    "ReceivablesInvoiceTransactionDFF": EntitySpec(
        name="ReceivablesInvoiceTransactionDFF",
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
        base_joins=[
            "JOIN HZ_CUST_ACCOUNTS CA ON CA.CUST_ACCOUNT_ID = C.BILL_TO_CUSTOMER_ID",
            "JOIN HZ_PARTIES HP ON HP.PARTY_ID = CA.PARTY_ID",
        ],
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
            # F-072: the two balances are KG `kg_derived_projection` rows
            # over AR_PAYMENT_SCHEDULES_ALL (ledger currency, verified
            # 29/29 vs REST); the account row does not carry them.
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
            ("R", "STATUS"),
            ("HP", "PARTY_NAME"),
        ],
        base_joins=[
            # LEFT JOIN (not INNER): 39 of 79,777 receipts have NULL
            # PAY_FROM_CUSTOMER (UNID 25 / REV 10 / NSF 2 / APP 2). REST's
            # top-level /standardReceipts returns those receipts with NULL
            # CustomerName/CustomerAccountNumber, so an INNER JOIN would
            # silently drop them (F-074). NULL propagation is the correct
            # behavior here, not a drop.
            "LEFT JOIN HZ_CUST_ACCOUNTS CA ON CA.CUST_ACCOUNT_ID = R.PAY_FROM_CUSTOMER",
            "LEFT JOIN HZ_PARTIES HP ON HP.PARTY_ID = CA.PARTY_ID",
        ],
        # F-076: /standardReceipts does not expose every AR_CASH_RECEIPTS_ALL
        # row. It reports the standard cash receipts only — the single
        # TYPE='MISC' row on dev49 is absent from REST while all 79,733
        # TYPE='CASH' rows are reachable. Measured, not assumed: pod
        # CASH-only receipts excluding the two non-visible business units
        # reconcile to REST's total of 63,065 exactly.
        #
        # The business-unit half of the scope is NOT declared here: it is a
        # property of the integration user's security profile, supplied by
        # the persona (see spire.config.DataScope) and injected by the
        # emitter.
        scope_predicates=["{alias}.TYPE = 'CASH'"],
        scope_assumption="receipts_scoped_to_rest_visible_dataset",
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
        # F-080b: the arg is REST's `Status` (ACTIVE / INACTIVE, matched
        # client-side against the payload). The old carrier was
        # POZ_SUPPLIERS.ENABLED_FLAG, which is 'Y' on all 334 suppliers on
        # this pod and therefore returned 0 rows for "inactive suppliers"
        # while REST reports 2.
        #
        # The real carrier is END_DATE_ACTIVE: REST's InactiveDate equals
        # it on 334/334 suppliers (0 mismatches) and REST's Status is
        # ACTIVE 332 / INACTIVE 2 on exactly the two rows where it is set
        # and past. There is no INACTIVE_DATE column on POZ_SUPPLIERS.
        #
        # ACTIVE and INACTIVE need opposite predicates, so the template
        # branches on the resolved literal. `value_map` still lists only
        # those two values, so any other status raises rather than
        # silently returning suppliers (the F-078 fail-loud rule).
        predicate_template=(
            "CASE WHEN UPPER({value}) = 'INACTIVE' "
            "THEN CASE WHEN {alias}.END_DATE_ACTIVE <= TRUNC(SYSDATE) "
            "THEN 1 ELSE 0 END "
            "ELSE CASE WHEN {alias}.END_DATE_ACTIVE IS NULL "
            "OR {alias}.END_DATE_ACTIVE > TRUNC(SYSDATE) "
            "THEN 1 ELSE 0 END "
            "END = 1"
        ),
        value_map={"ACTIVE": "'ACTIVE'", "INACTIVE": "'INACTIVE'"},
        assumption="status_maps_to_end_date_active",
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
        match_mode="contains",
    ),
    ("search_suppliers_by_site_bu", "supplier_id"): FilterSpec(
        tool_name="search_suppliers_by_site_bu",
        arg_name="supplier_id",
        predicate_template="{alias}.VENDOR_ID = {value}",
        assumption="site_supplier_id_maps_to_vendor_id",
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
    ("search_suppliers_by_classification", "supplier_id"): FilterSpec(
        tool_name="search_suppliers_by_classification",
        arg_name="supplier_id",
        predicate_template="{alias}.VENDOR_ID = {value}",
        assumption="classification_supplier_id",
    ),
    ("get_supplier_contacts", "supplier_id"): FilterSpec(
        tool_name="get_supplier_contacts",
        arg_name="supplier_id",
        predicate_template="PS.VENDOR_ID = {value}",
        assumption="contact_supplier_id",
    ),
    
    # PurchaseOrder filters
    ("search_purchase_orders", "status"): FilterSpec(
        tool_name="search_purchase_orders",
        arg_name="status",
        predicate_template="{alias}.DOCUMENT_STATUS = {value}",
        assumption="po_status_maps_to_authorization_status",
    ),
    ("search_purchase_orders", "supplier_id"): FilterSpec(
        tool_name="search_purchase_orders",
        arg_name="supplier_id",
        # The tool's supplier_id arg is the numeric internal SupplierId
        # (= PO_HEADERS_ALL.VENDOR_ID), NOT the human SupplierNumber
        # (SEGMENT1). The executor iterates over SupplierId, so matching
        # SEGMENT1 against a numeric VENDOR_ID returns 0 rows (F-065).
        predicate_template="{alias}.VENDOR_ID = {value}",
        assumption="supplier_maps_to_vendor_id",
    ),
    ("search_purchase_orders", "supplier_name"): FilterSpec(
        tool_name="search_purchase_orders",
        arg_name="supplier_name",
        predicate_template="HP.PARTY_NAME LIKE {value}",
        assumption="name_like_on_party_name",
        match_mode="contains",
    ),
    ("search_purchase_orders", "created_since"): FilterSpec(
        tool_name="search_purchase_orders",
        arg_name="created_since",
        predicate_template="{alias}.CREATION_DATE >= {value}",
        assumption="po_created_since",
    ),

    # Invoice filters
    ("search_invoices", "invoice_number"): FilterSpec(
        tool_name="search_invoices",
        arg_name="invoice_number",
        predicate_template="{alias}.INVOICE_NUM = {value}",
        assumption="invoice_number_maps_to_invoice_num",
    ),
    ("search_invoices", "supplier_number"): FilterSpec(
        tool_name="search_invoices",
        arg_name="supplier_number",
        predicate_template="S.SEGMENT1 = {value}",
        requires_join=("Invoice", "Supplier"),
        assumption="invoice_supplier_maps_to_segment1",
    ),
    ("search_invoices", "supplier_name"): FilterSpec(
        tool_name="search_invoices",
        arg_name="supplier_name",
        predicate_template=(
            "S.VENDOR_ID IN (SELECT SI.VENDOR_ID FROM POZ_SUPPLIERS SI "
            "JOIN HZ_PARTIES HI ON HI.PARTY_ID = SI.PARTY_ID "
            "WHERE HI.PARTY_NAME LIKE {value})"
        ),
        requires_join=("Invoice", "Supplier"),
        assumption="invoice_supplier_name",
        match_mode="contains",
    ),
    ("search_invoices", "invoice_date_after"): FilterSpec(
        tool_name="search_invoices",
        arg_name="invoice_date_after",
        predicate_template="{alias}.INVOICE_DATE >= {value}",
        assumption="invoice_date_filter",
    ),
    ("search_invoices", "unpaid"): FilterSpec(
        tool_name="search_invoices",
        arg_name="unpaid",
        predicate_template="{alias}.PAYMENT_STATUS_FLAG IN ('N', 'P')",
        assumption="invoice_unpaid_status_flags",
    ),
    
    # AR Invoice filters
    ("get_receivables_invoice_by_id", "customer_transaction_id"): FilterSpec(
        tool_name="get_receivables_invoice_by_id",
        arg_name="customer_transaction_id",
        # F-079/F-082: the plan carries one bare number and cannot know
        # which identifier space it is in — "invoice 112390" is a
        # TRX_NUMBER (the id is 1533822). This mirrors the tool's
        # resolution order exactly: TransactionNumber first, then
        # CustomerTransactionId. MIN() makes it deterministic where the
        # tool's limit=1 takes whatever the pod returns first.
        predicate_template=(
            "{alias}.CUSTOMER_TRX_ID = COALESCE("
            "(SELECT MIN(T.CUSTOMER_TRX_ID) FROM RA_CUSTOMER_TRX_ALL T "
            "WHERE T.TRX_NUMBER = {value}), "
            "(SELECT MIN(T.CUSTOMER_TRX_ID) FROM RA_CUSTOMER_TRX_ALL T "
            "WHERE T.CUSTOMER_TRX_ID = {value}))"
        ),
        assumption="ar_id_resolves_number_then_trx_id",
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
        predicate_template="{alias}.PO_HEADER_ID = {value}",
        assumption="po_distribution_three_way_filter",
    ),
    ("get_purchase_order_distributions", "po_line_id"): FilterSpec(
        tool_name="get_purchase_order_distributions",
        arg_name="po_line_id",
        predicate_template="{alias}.PO_LINE_ID = {value}",
        assumption="po_distribution_three_way_filter",
    ),
    ("get_purchase_order_distributions", "line_location_id"): FilterSpec(
        tool_name="get_purchase_order_distributions",
        arg_name="line_location_id",
        predicate_template="{alias}.LINE_LOCATION_ID = {value}",
        assumption="po_distribution_three_way_filter",
    ),

    # AP child fetchers (F-077)
    ("get_invoice_lines", "invoice_id"): FilterSpec(
        tool_name="get_invoice_lines",
        arg_name="invoice_id",
        predicate_template="{alias}.INVOICE_ID = {value}",
        assumption="ap_line_by_invoice_id",
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
        # F-079: "PO 55040" is a SEGMENT1 (the id is 67), but "PO 2144" is
        # a PO_HEADER_ID. The plan cannot tell them apart, so this mirrors
        # the tool's resolution order: OrderNumber first, header id only
        # when no PO claims that number. Binding a single space silently
        # returned 0 rows for the number form.
        predicate_template=(
            "{alias}.PO_HEADER_ID = COALESCE("
            "(SELECT MIN(H.PO_HEADER_ID) FROM PO_HEADERS_ALL H "
            "WHERE H.SEGMENT1 = {value}), "
            "(SELECT MIN(H.PO_HEADER_ID) FROM PO_HEADERS_ALL H "
            "WHERE H.PO_HEADER_ID = {value}))"
        ),
        assumption="po_by_id_resolves_number_then_id",
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
            "{alias}.TRX_ID = {value} "
            "AND {alias}.ENTITY_CODE = 'TRANSACTIONS'"
        ),
        assumption="ar_tax_line_filter",
    ),
    ("get_receivables_invoice_tax_lines", "line_id"): FilterSpec(
        tool_name="get_receivables_invoice_tax_lines",
        arg_name="line_id",
        predicate_template="{alias}.TRX_LINE_ID = {value}",
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
    ("get_customer_account_by_name", "account_number"): FilterSpec(
        tool_name="get_customer_account_by_name",
        arg_name="account_number",
        predicate_template="{alias}.ACCOUNT_NUMBER = {value}",
        assumption="customer_account_by_number",
    ),
    ("get_customer_transactions", "account_id"): FilterSpec(
        tool_name="get_customer_transactions",
        arg_name="account_id",
        predicate_template="{alias}.CUSTOMER_ID = {value}",
        assumption="customer_transaction_by_customer_id",
    ),
    ("get_customer_transactions", "open_only"): FilterSpec(
        tool_name="get_customer_transactions",
        arg_name="open_only",
        predicate_template=(
            "{alias}.CLASS = 'INV' "
            "AND {alias}.AMOUNT_DUE_REMAINING > 0"
        ),
        assumption="customer_transaction_open_invoice",
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
        # Applications are children of RECEIPTS, which are children of the
        # account (AR_CASH_RECEIPTS_ALL.PAY_FROM_CUSTOMER). The prior
        # template reached the account through "the parent transaction" via
        # CUSTOMER_TRX_ID / TRX_ID — both wrong: AR_RECEIVABLE_APPLICATIONS_ALL
        # has no account id, and RA_CUSTOMER_TRX_ALL has CUSTOMER_TRX_ID (not
        # TRX_ID), and the receipt's own CUSTOMER_TRX_ID is the on-account
        # transaction, not the applied one. Fixed to the receipt path.
        predicate_template=(
            "{alias}.CASH_RECEIPT_ID IN "
            "(SELECT CASH_RECEIPT_ID FROM AR_CASH_RECEIPTS_ALL "
            "WHERE PAY_FROM_CUSTOMER = {value})"
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
        # AR_CASH_RECEIPTS_ALL has NO CUSTOMER_SITE column (F-073): the old
        # "{alias}.CUSTOMER_SITE = ?" raised ORA-00904. The only site column
        # is the numeric CUSTOMER_SITE_USE_ID (18,365/79,777 populated), and
        # REST's CustomerSite is a NAME. Verified carrier: receipt ->
        # HZ_CUST_SITE_USES_ALL -> HZ_CUST_ACCT_SITES_ALL -> HZ_PARTY_SITES
        # -> HZ_LOCATIONS.CITY. Receipts 1/2/21 -> CITY 'Santa Clara' = REST
        # CustomerSite; PARTY_SITE_NAME is NULL. Cardinality: 1,735 site-wide
        # inside the REST business unit = REST's 1,735. A correlated subquery
        # keeps this 4-hop chain out of every StandardReceipt query.
        predicate_template=(
            "{alias}.CUSTOMER_SITE_USE_ID IN ("
            "SELECT SU.SITE_USE_ID FROM HZ_CUST_SITE_USES_ALL SU "
            "JOIN HZ_CUST_ACCT_SITES_ALL CS "
            "  ON CS.CUST_ACCT_SITE_ID = SU.CUST_ACCT_SITE_ID "
            "JOIN HZ_PARTY_SITES PS ON PS.PARTY_SITE_ID = CS.PARTY_SITE_ID "
            "JOIN HZ_LOCATIONS LOC ON LOC.LOCATION_ID = PS.LOCATION_ID "
            "WHERE LOC.CITY = {value})"
        ),
        assumption="standard_receipt_site_client_side",
    ),
    ("search_addresses", "supplier_number"): FilterSpec(
        tool_name="search_addresses",
        arg_name="supplier_number",
        predicate_template=(
            "EXISTS (SELECT 1 FROM POZ_SUPPLIERS SP "
            "WHERE SP.PARTY_ID = PS.PARTY_ID AND SP.SEGMENT1 = {value})"
        ),
        assumption="address_supplier_number",
    ),
    ("search_addresses", "supplier_name"): FilterSpec(
        tool_name="search_addresses",
        arg_name="supplier_name",
        predicate_template=(
            "EXISTS (SELECT 1 FROM POZ_SUPPLIERS SP "
            "JOIN HZ_PARTIES HP ON HP.PARTY_ID = SP.PARTY_ID "
            "WHERE SP.PARTY_ID = PS.PARTY_ID "
            "AND HP.PARTY_NAME LIKE {value})"
        ),
        assumption="address_supplier_name",
        match_mode="contains",
    ),

    # Phase 5: aggregation argument filters
    ("aggregate_invoices_by_supplier", "date_from"): FilterSpec(
        tool_name="aggregate_invoices_by_supplier",
        arg_name="date_from",
        predicate_template="{alias}.INVOICE_DATE >= {value}",
        assumption="aggregation_arg_handling",
    ),
    ("aggregate_invoices_by_supplier", "date_to"): FilterSpec(
        tool_name="aggregate_invoices_by_supplier",
        arg_name="date_to",
        predicate_template="{alias}.INVOICE_DATE < {value}",
        assumption="aggregation_arg_handling",
    ),
    # AP-2 (2026-11-28). Same two bounds, same predicate shapes, different
    # tool. The value reachability requires a third FilterSpec row here or
    # validate_sql_coverage reports both args uncovered.
    ("aggregate_outstanding_invoices_by_supplier", "date_from"): FilterSpec(
        tool_name="aggregate_outstanding_invoices_by_supplier",
        arg_name="date_from",
        predicate_template="{alias}.INVOICE_DATE >= {value}",
        assumption="aggregation_arg_handling",
    ),
    ("aggregate_outstanding_invoices_by_supplier", "date_to"): FilterSpec(
        tool_name="aggregate_outstanding_invoices_by_supplier",
        arg_name="date_to",
        predicate_template="{alias}.INVOICE_DATE < {value}",
        assumption="aggregation_arg_handling",
    ),
    ("aggregate_standard_receipts_by_method", "customer_name"): FilterSpec(
        tool_name="aggregate_standard_receipts_by_method",
        arg_name="customer_name",
        predicate_template="HP.PARTY_NAME = {value}",
        assumption="aggregation_arg_handling",
    ),
    ("aggregate_standard_receipts_by_method", "account_number"): FilterSpec(
        tool_name="aggregate_standard_receipts_by_method",
        arg_name="account_number",
        predicate_template="CA.ACCOUNT_NUMBER = {value}",
        assumption="aggregation_arg_handling",
    ),
    ("rank_invoices_by_amount", "supplier_name"): FilterSpec(
        tool_name="rank_invoices_by_amount",
        arg_name="supplier_name",
        predicate_template=(
            "P.VENDOR_ID IN (SELECT VENDOR_ID FROM POZ_SUPPLIERS "
            "WHERE PARTY_NAME = {value})"
        ),
        assumption="aggregation_arg_handling",
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
    "status_maps_to_end_date_active": (
        "search_suppliers.status is REST's Status (ACTIVE/INACTIVE) and "
        "maps to POZ_SUPPLIERS.END_DATE_ACTIVE, not ENABLED_FLAG. "
        "ENABLED_FLAG is 'Y' on all 334 suppliers on this pod; "
        "END_DATE_ACTIVE is set on the same 2 rows REST reports INACTIVE, "
        "and REST's InactiveDate equals it on 334/334 suppliers. A "
        "supplier is inactive once END_DATE_ACTIVE has passed."
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
        "PO StatusCode maps to PO_HEADERS_ALL.DOCUMENT_STATUS. "
        "Confirmed valid values on fa-euth-dev93: 'OPEN', 'CLOSED', "
        "'CLOSED FOR RECEIVING', 'PENDING APPROVAL'."
    ),
    "supplier_maps_to_vendor_id": (
        "SupplierId maps to PO_HEADERS_ALL.VENDOR_ID."
    ),
    "supplier_number_not_vendor_id": (
        "OBSOLETE (F-065, 2026-11-19): the search_purchase_orders "
        "supplier_id arg is the numeric SupplierId (VENDOR_ID), not the "
        "SupplierNumber (SEGMENT1). Retained for the record; no FilterSpec "
        "references it."
    ),
    "invoice_supplier_maps_to_segment1": (
        "SupplierNumber maps to POZ_SUPPLIERS.SEGMENT1."
    ),
    "invoice_date_filter": (
        "InvoiceDate filters against AP_INVOICES_ALL.INVOICE_DATE."
    ),
    "po_created_since": (
        "CreationDate filters against PO_HEADERS_ALL.CREATION_DATE."
    ),
    "invoice_number_maps_to_invoice_num": (
        "InvoiceNumber filters against AP_INVOICES_ALL.INVOICE_NUM."
    ),
    "invoice_supplier_name": (
        "Supplier substring matches resolve through POZ_SUPPLIERS and "
        "HZ_PARTIES.PARTY_NAME."
    ),
    "invoice_unpaid_status_flags": (
        "Unpaid includes AP_INVOICES_ALL.PAYMENT_STATUS_FLAG values N "
        "and P (unpaid and partially paid)."
    ),
    "customer_account_by_number": (
        "CustomerAccountNumber maps to HZ_CUST_ACCOUNTS.ACCOUNT_NUMBER."
    ),
    "customer_transaction_open_invoice": (
        "Open customer transactions are invoice-class rows with a positive "
        "AR_PAYMENT_SCHEDULES_ALL.AMOUNT_DUE_REMAINING."
    ),
    "address_supplier_number": (
        "Address supplier number resolves through POZ_SUPPLIERS.SEGMENT1 "
        "and the shared PARTY_ID."
    ),
    "address_supplier_name": (
        "Address supplier name resolves through POZ_SUPPLIERS.PARTY_ID "
        "to HZ_PARTIES.PARTY_NAME."
    ),
    "classification_supplier_id": (
        "SupplierId scopes POZ_BUS_CLASSIFICATIONS.VENDOR_ID."
    ),
    "contact_supplier_id": (
        "SupplierId scopes contacts through POZ_SUPPLIER_SITES_ALL_M."
        "VENDOR_ID."
    ),
    "ar_id_resolves_number_then_trx_id": (
        "get_receivables_invoice_by_id accepts a TransactionNumber or a "
        "CustomerTransactionId and tries TransactionNumber first. The "
        "predicate resolves the same way (COALESCE over TRX_NUMBER, then "
        "CUSTOMER_TRX_ID). Confirmed on the pod: AR invoice 112390 is "
        "TRX_NUMBER with CUSTOMER_TRX_ID 1533822."
    ),
    "bu_literal_from_overlay": (
        "Business-unit name resolves to a numeric BU_ID from "
        "kg_sql_literal."
    ),
    "site_supplier_id_maps_to_vendor_id": (
        "search_suppliers_by_site_bu.supplier_id is the numeric SupplierId "
        "(the parent supplier), carried as VENDOR_ID on "
        "POZ_SUPPLIER_SITES_ALL_M. The REST tool reaches sites via the URL "
        "path /suppliers/{SupplierId}/child/sites; the SQL equivalent "
        "filters POZ_SUPPLIER_SITES_ALL_M.VENDOR_ID."
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
    "receipts_scoped_to_rest_visible_dataset": (
        "StandardReceipt SQL is restricted to the rows REST can actually "
        "return (F-076). Two independent rules, both measured on dev49: "
        "(1) TYPE = 'CASH' — /standardReceipts does not expose "
        "miscellaneous receipts (1 MISC row on the pod, absent from REST); "
        "(2) the business-unit filter injected from the persona's "
        "scope.visible_business_units, because REST visibility is set by "
        "the integration user's security profile and is not derivable "
        "from any column. Without rule (2) the SQL returns receipts from "
        "business units the user cannot see (France 9,316 and UK 7,352 on "
        "dev49). Do NOT read this as one business unit: REST sees 14 of "
        "the 16 AR orgs, not a single BU."
    ),
    "ar_line_by_customer_trx_id": (
        "AR line child filters on CUSTOMER_TRX_ID (the AR invoice's "
        "parent id, per the endpoint path "
        "/receivablesInvoices/{id}/child/receivablesInvoiceLines). "
        "Column names are: CUSTOMER_TRX_LINE_ID, LINE_NUMBER, "
        "DESCRIPTION, QUANTITY_INVOICED, UNIT_SELLING_PRICE, "
        "EXTENDED_AMOUNT."
    ),
    "ap_line_by_invoice_id": (
        "AP line child filters on INVOICE_ID (the AP invoice's parent id, "
        "per the endpoint path /invoices/{id}/child/invoiceLines). "
        "Column names are: LINE_NUMBER, DESCRIPTION, QUANTITY_INVOICED, "
        "UNIT_PRICE, AMOUNT, LINE_TYPE_LOOKUP_CODE. AP_INVOICE_LINES_ALL "
        "exposes no INVOICE_LINE_ID on this pod, so (INVOICE_ID, "
        "LINE_NUMBER) is the line identity - unique across all 1,335,566 "
        "rows on dev49."
    ),
    "po_by_id_resolves_number_then_id": (
        "get_purchase_order_by_id accepts either an OrderNumber or a "
        "POHeaderId and tries OrderNumber first. The predicate resolves "
        "the same way (COALESCE over SEGMENT1, then PO_HEADER_ID) because "
        "a bare number in a prompt does not say which space it is in. "
        "Confirmed on the pod: PO 55040 is SEGMENT1 with PO_HEADER_ID 67."
    ),
    "buyer_person_id": (
        "get_buyer looks up PER_ALL_PEOPLE_F by PERSON_ID. Confirmed "
        "via curl against PERSON_ID 300000047340498: returns DISPLAY_NAME "
        "'Calvin Roth', EMPLOYEE_NUMBER '3', EMAIL_ADDRESS "
        "'CALVIN.ROTH_euth-dev93@oraclepdemos.com'."
    ),
    "ar_tax_line_filter": (
        "AR tax lines come from ZX_LINES (the tax engine), joined on "
        "TRX_ID = CUSTOMER_TRX_ID and TRX_LINE_ID = CUSTOMER_TRX_LINE_ID, "
        "with ENTITY_CODE = 'TRANSACTIONS'. Verified via curl + pod against "
        "AR invoice 1002, line 74: two tax rows (COUNTY 2.25%, STATE 6.5%) "
        "on TAX_LINE_ID 9040/9039. RA_CUST_TRX_LINE_GL_DIST_ALL carries "
        "the GL-side tax AMOUNT but none of the rate/regime/jurisdiction "
        "columns, and on this pod has no ACCOUNT_CLASS='TAX' row for line 74 "
        "(only a REV row). The filter takes two ids: customer_transaction_id "
        "and the parent line_id (named bind)."
    ),
    "ar_dff_columns_uncertain": (
        "AR transaction DFF is projected as ATTRIBUTE_CATEGORY (the "
        "flexfield context, matching __FLEX_Context in REST) and "
        "ATTRIBUTE1 (the first segment). The physical DFF column names "
        "are pod-specific; on this pod the context is 'DOO' but no "
        "segment values are populated, so the mapping cannot be "
        "confirmed end-to-end until a pod with populated DFF is "
        "available. If a future prompt reveals different column names, "
        "update the select_columns on ReceivablesInvoiceTransactionDFF."
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
        "through the parent RECEIPT: CASH_RECEIPT_ID IN "
        "(SELECT CASH_RECEIPT_ID FROM AR_CASH_RECEIPTS_ALL WHERE "
        "PAY_FROM_CUSTOMER = ?). The prior parent-transaction path "
        "(CUSTOMER_TRX_ID / TRX_ID) was wrong: AR_RECEIVABLE_APPLICATIONS_ALL."
        "CUSTOMER_TRX_ID is the on-account transaction, not the applied one, "
        "and RA_CUSTOMER_TRX_ALL has CUSTOMER_TRX_ID, not TRX_ID. The tool "
        "filters to ApplicationStatus='Applied' server-side; the emitted SQL "
        "does not add that filter (STATUS='APP' is the physical code)."
    ),
    "standard_receipt_by_customer_name": (
        "search_standard_receipts resolves customer_name to an account "
        "number in the tool, then filters AR_CASH_RECEIPTS_ALL. The "
        "physical table does not carry PARTY_NAME directly; the join "
        "to HZ_CUST_ACCOUNTS and HZ_PARTIES supplies it."
    ),
    "standard_receipt_site_client_side": (
        "search_standard_receipts applies customer_site client-side over "
        "the fetched REST rows (composite q= returns a silent zero on this "
        "endpoint). The emitted SQL resolves the same site NAME through the "
        "receipt's site-use chain: CUSTOMER_SITE_USE_ID -> "
        "HZ_CUST_SITE_USES_ALL -> HZ_CUST_ACCT_SITES_ALL -> HZ_PARTY_SITES "
        "-> HZ_LOCATIONS.CITY. AR_CASH_RECEIPTS_ALL has no CUSTOMER_SITE "
        "column; binding the numeric CUSTOMER_SITE_USE_ID would compare an "
        "id to a name. Verified: receipts 1/2/21 -> CITY 'Santa Clara' = "
        "REST CustomerSite, and 1,735 site-wide rows inside the REST "
        "business unit equals REST's 1,735."
    ),
    "aggregation_measures": (
        "Every aggregation tool selects a grouped column and a SUM or "
        "COUNT over a measure column on the base entity. Where a tool "
        "computes a RATIO or DISTINCT count not derivable as SUM/COUNT "
        "on one column, it is listed in not_expressible instead."
    ),
    "standard_receipt_method_not_mapped": (
        "Both the StandardReceipt and AccountReceipt entities omit the "
        "receipt method from their SELECT lists. The physical column on "
        "AR_CASH_RECEIPTS_ALL is RECEIPT_METHOD_ID (a numeric FK), but "
        "the REST field ReceiptMethod is the display string (e.g. "
        "'Lockbox', 'Check (Directly/No Remit)') which lives on "
        "AR_RECEIPT_METHODS. That join is not yet mapped; emitting the "
        "numeric id where the reader expects a name would be correct in "
        "shape but wrong in kind — the REST answer and the SQL answer "
        "would disagree on that column. Recorded here so a future "
        "session knows the column is deliberately absent, not forgotten."
    ),
    "aggregation_arg_handling": (
        "Aggregations take arguments the emitter handles in three ways: "
        "date and identity args are mapped as WHERE filters (date_from, "
        "date_to, customer_name, account_number, supplier_name); top_n "
        "is emitted as FETCH FIRST N ROWS ONLY after the ORDER BY; and "
        "fetch caps (limit) are deliberately not translated, because "
        "they bound the FETCH, not the RESULT SET. A LIMIT in the tool "
        "does not mean 'top N groups' and must not become a FETCH FIRST "
        "in the SQL."
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
        "search_receivables_invoices": "ReceivablesInvoice",
        "search_customer_accounts": "CustomerAccount",
        "get_purchase_order_lines": "PurchaseOrderLine",
        "get_purchase_order_schedules": "POSchedule",
        "get_purchase_order_distributions": "PODistribution",
        # F-077: AP invoice lines, keyed on the parent InvoiceId like every
        # other child tool.
        "get_invoice_lines": "InvoiceLine",
        "get_receivables_invoice_lines": "ReceivablesInvoiceLine",
        "get_buyer": "Buyer",
        "get_receivables_invoice_tax_lines": "ReceivablesTaxLine",
        "get_receivables_invoice_transaction_dff": "ReceivablesInvoiceTransactionDFF",
        "list_receivables_credit_memos": "CreditMemo",
        "get_customer_account_by_name": "CustomerAccount",
        "get_customer_transactions": "CustomerTransaction",
        "get_account_credit_memos": "AccountCreditMemo",
        "get_account_receipts": "AccountReceipt",
        "get_account_receipt_applications": "AccountReceiptApplication",
        "search_standard_receipts": "StandardReceipt",
        # p15. AP invoice holds. A top-level collection, not a child tool:
        # there is no parent id in the path.
        "search_invoice_holds": "InvoiceHold",
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
            top_n_arg="top_n",
        ),
        # AP-2 (2026-11-28). The measure subtracts AmountPaid, which is on
        # the invoice header. NVL guards the nulls this pod carries on
        # unpaid rows so the subtraction never yields NULL. Cancelled rows
        # are excluded because a cancelled invoice is not owed — 725 of
        # them exist and the first page of 'Unpaid' is mostly cancelled
        # zero-amount rows.
        "aggregate_outstanding_invoices_by_supplier": AggregationSpec(
            tool_name="aggregate_outstanding_invoices_by_supplier",
            base_entity="Invoice",
            group_by_column="VENDOR_ID",
            measure_template=(
                "SUM(GREATEST(NVL(INVOICE_AMOUNT, 0) "
                "- NVL(AMOUNT_PAID, 0), 0))"
            ),
            assumption="aggregation_measures",
            top_n_arg="top_n",
        ),
        "aggregate_purchase_orders_by_status": AggregationSpec(
            tool_name="aggregate_purchase_orders_by_status",
            base_entity="PurchaseOrder",
            group_by_column="DOCUMENT_STATUS",
            measure_template=(
                "SUM((SELECT SUM(L.UNIT_PRICE * L.QUANTITY) "
                "FROM PO_LINES_ALL L "
                "WHERE L.PO_HEADER_ID = P.PO_HEADER_ID))"
            ),
            order_desc_by_measure=False,
            assumption="aggregation_measures",
            top_n_arg="top_n",
        ),
        "aggregate_standard_receipts_by_method": AggregationSpec(
            tool_name="aggregate_standard_receipts_by_method",
            base_entity="StandardReceipt",
            group_by_column="RECEIPT_METHOD_ID",
            measure_template="SUM(AMOUNT)",
            order_desc_by_measure=False,
            assumption="aggregation_measures",
            skip_args={"limit"},
        ),
        "rank_invoices_by_amount": AggregationSpec(
            tool_name="rank_invoices_by_amount",
            base_entity="Invoice",
            group_by_column="INVOICE_ID",
            measure_template="SUM(INVOICE_AMOUNT)",
            assumption="aggregation_measures",
            top_n_arg="top_n",
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
    # 'on_hold' joins the control args: the predicate it represents is already
    # unconditional in InvoiceHold's scope_predicates, so keeping the argument
    # out of the WHERE builder is what prevents the same test being emitted
    # twice (or, worse, once with the wrong polarity).
    sql_control_args={"limit", "fetch_limit", "ctx", "on_hold"},
    sql_disabled_args={
        ("search_suppliers", "business_relationship"): (
            "business relationship has no verified SQL predicate"
        ),
        ("search_suppliers", "created_from"): (
            "date-range handling is not yet represented in SQL"
        ),
        ("search_suppliers", "created_to"): (
            "date-range handling is not yet represented in SQL"
        ),
        ("search_invoices", "purchase_order"): (
            "PO-number invoice filtering is not yet represented in SQL"
        ),
        ("search_invoices", "invoice_date_before"): (
            "invoice date upper-bound handling is not yet represented in SQL"
        ),
        ("search_invoices", "amount_min"): (
            "invoice amount lower-bound handling is not yet represented in SQL"
        ),
        ("search_invoices", "amount_max"): (
            "invoice amount upper-bound handling is not yet represented in SQL"
        ),
        ("search_invoices", "pending"): (
            "pending approval has no verified SQL predicate"
        ),
        ("search_invoices", "overdue"): (
            "the invoice due-date carrier has not been verified on this pod"
        ),
        ("search_addresses", "country"): (
            "address country filtering is not yet represented in SQL"
        ),
        ("search_purchase_orders", "created_before"): (
            "PO creation-date upper-bound handling is not yet represented in SQL"
        ),
        ("search_purchase_orders", "last_updated_before"): (
            "PO last-update filtering is not yet represented in SQL"
        ),
        ("search_purchase_orders", "last_updated_after"): (
            "PO last-update filtering is not yet represented in SQL"
        ),
    },
)


__all__ = [
    "EntitySpec",
    "FilterSpec",
    "JoinSpec",
    "Overlay",
    "OVERLAY",
]
