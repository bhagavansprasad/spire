"""SQL overlay — Python structure for the SQL Overlay POC.

Parallel to the KG, not part of it. Six conceptual tables, expressed as
Python data. In a later migration these become Oracle tables with the
same content. For now the emitter reads them directly.

The overlay describes what SQL a Plan step compiles to. It does not
execute, and it does not change the KG, the parser, the planner, or any
tool. See docs/design/SQL_OVERLAY_POC.md.
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
    """One filter: how a (tool_name, tool_arg_name) pair compiles to a
    WHERE predicate.

    - ``predicate_template`` uses ``{alias}`` for the entity alias and
      ``{value}`` for the resolved SQL literal.
    - ``value_map`` maps a runtime arg value to a SQL literal directly
      (e.g. ``{'ACTIVE': \"'Y'\"}``).
    - ``vocab_kind`` names a vocab_kind in ``kg_sql_literal`` for values
      resolved from a lookup (e.g. BU display strings to numeric ids).
    - ``requires_join`` names a (from_entity, to_entity) pair whose join
      clause MUST appear in the FROM before this predicate makes sense.
      The emitter auto-adds the join. Example: the country filter
      references ``L.COUNTRY``, so it requires the Supplier→Address join.
    - ``assumption`` names a row in ``ASSUMPTIONS``.
    """

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
}


# ─────────────────────────────────────────────────────────────────────
# kg_sql_filter
# ─────────────────────────────────────────────────────────────────────

_FILTERS = {
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
        # The predicate names alias L; the join must be present.
        requires_join=("Supplier", "Address"),
        assumption="address_join_for_country",
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
}


# ─────────────────────────────────────────────────────────────────────
# kg_sql_literal — seeded from the live pod, 2026-10-07
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
        "('Y'/'N'). Confirmed by Oracle PO Prism Q24 "
        "(2026-10-07). OQ-1."
    ),
    "address_join_for_country": (
        "Supplier country lives on the child address, not the supplier "
        "row. The join is POZ_SUPPLIERS.PARTY_ID -> HZ_PARTY_SITES.PARTY_ID "
        "-> HZ_LOCATIONS.LOCATION_ID. OQ-3 covers PARTY_TYPE, not this."
    ),
    "bu_literal_from_overlay": (
        "Business-unit name resolves to a numeric BU_ID from "
        "kg_sql_literal. Resolution happens upstream of the emitter "
        "(Resolution A). If the pod changes, the literals are reseeded. "
        "OQ-4."
    ),
    "classification_literal_from_overlay": (
        "Classification display string resolves to a LOOKUP_CODE via "
        "kg_sql_literal. Same pattern as BU."
    ),
    "party_type_not_filtered": (
        "POZ_SUPPLIERS.PARTY_ID is assumed to point at an organization "
        "row only; no HZ_PARTIES.PARTY_TYPE predicate is emitted. OQ-3, "
        "unverified."
    ),
    "contact_party_site_id": (
        "Contact joins via PARTY_SITE_ID, not ORG_PARTY_SITE_ID. Oracle's "
        "own PO Prism Q16 carries an inline comment flagging the same "
        "ambiguity. OQ-2, unverified."
    ),
}


OVERLAY = Overlay(
    tool_to_entity={
        "search_suppliers": "Supplier",
        "search_suppliers_by_site_bu": "Site",
        "search_suppliers_by_classification": "Classification",
        "search_addresses": "Address",
        "get_supplier_contacts": "Contact",
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
