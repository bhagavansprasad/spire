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
class Overlay:
    tool_to_entity: dict[str, str]
    entities: dict[str, EntitySpec]
    filters: dict[tuple[str, str], FilterSpec]
    joins: dict[tuple[str, str], JoinSpec]
    literals: dict[tuple[str, str], str]
    assumptions: dict[str, str]


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
    },
    entities=_ENTITIES,
    filters=_FILTERS,
    joins=_JOINS,
    literals=_LITERALS,
    assumptions=_ASSUMPTIONS,
)


__all__ = [
    "EntitySpec",
    "FilterSpec",
    "JoinSpec",
    "Overlay",
    "OVERLAY",
]
