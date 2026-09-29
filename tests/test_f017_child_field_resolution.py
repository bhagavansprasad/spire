"""F-017 — child-entity fields must resolve against the include's catalog.

THE BUG THESE PIN
"Show PO 2144 and its lines with description" was answered with a note
that Description was not available on PurchaseOrder — while the fetched
line rows carried Description ("Marketing Assistance"). The field-split
in validate_intent classified the requested column against the TARGET
entity's catalog only; a column that lived on the child include was
never checked against it, so it fell to unresolved_fields and the
display reported a false miss.

The fix consults, for each requested column, the target's own catalog
FIRST and then the KG catalog of every entity in intent.include. The
curated _FIELDS_SATISFIED_BY_INCLUDE map stays — it carries four
Address synonyms (city, state, address, addresses) that are NOT columns
on the Address KG catalog and would be lost without it.

WHY A HAND-BUILT KGMenu
The parser's unit-test fixtures build a minimal KGMenu by hand; this
file follows that convention. No Oracle connection, no pod dependency,
no test-skip on personas.yaml. The mechanism under test is a set
operation over two dictionaries — the fixture supplies exactly the
shape the code reads and nothing else.
"""

from __future__ import annotations

from spire.nl_parser.intent_validation import validate_intent
from spire.nl_parser.vocabulary import KGMenu
from spire.planner.planner import Intent


def _menu() -> KGMenu:
    """A minimal KGMenu with just the entities and columns this finding
    needs. Two-entity include edges so the include gate exercises the
    same code path production does rather than short-circuiting."""
    return KGMenu(
        target_entities={"PurchaseOrder", "Supplier"},
        filter_types={"by_id"},
        entity_descriptions={
            "PurchaseOrder": "a purchase order",
            "PurchaseOrderLine": "a line on a PO",
            "Supplier": "a supplier",
            "Address": "a supplier address",
        },
        entity_columns={
            "PurchaseOrder": [
                "POHeaderId", "OrderNumber", "StatusCode", "Status",
                "Ordered", "Total",
            ],
            "PurchaseOrderLine": [
                "POLineId", "LineNumber", "Description", "Ordered",
                "Total",
            ],
            "Supplier": [
                "SupplierId", "SupplierNumber", "Supplier", "Status",
            ],
            # The Address KG catalog carries ONLY these two — the
            # curated map's "city"/"state"/"address"/"addresses" are
            # NOT here, which is why the map remains load-bearing.
            "Address": ["CountryCode", "Country"],
        },
        edge_pairs={
            ("PurchaseOrder", "PurchaseOrderLine"),
            ("Supplier", "Address"),
        },
    )


def _intent(
    target: str,
    include: list[str] | None = None,
    fields: list[str] | None = None,
) -> Intent:
    return Intent(
        target_entity=target,
        filters=[],
        include=include or [],
        fields=fields or [],
    )


# ─────────────────────────────────────────────────────────────────────
# The reproducer and its mirror
# ─────────────────────────────────────────────────────────────────────


def test_child_field_on_include_not_classified_unresolved():
    """The F-017 reproducer. 'Description' lives on PurchaseOrderLine,
    which is in the include. Post-fix it is neither in `fields` (it is
    not a PurchaseOrder column) nor in `unresolved_fields` (the include
    carries it)."""
    menu = _menu()
    intent = _intent(
        "PurchaseOrder",
        include=["PurchaseOrderLine"],
        fields=["Description"],
    )
    result = validate_intent(intent, menu)
    assert result is None
    assert intent.unresolved_fields == []
    assert intent.fields == []


def test_child_field_without_include_still_unresolved():
    """Negative: the same column, no include. Must still be reported —
    proves the fix does not invent a phantom include to satisfy the
    field."""
    menu = _menu()
    intent = _intent("PurchaseOrder", fields=["Description"])
    result = validate_intent(intent, menu)
    assert result is None
    assert intent.unresolved_fields == ["Description"]
    assert intent.fields == []


# ─────────────────────────────────────────────────────────────────────
# Target-catalog precedence — the guard against the include branch
# stealing a column that belongs to the target's projection.
# ─────────────────────────────────────────────────────────────────────


def test_target_field_wins_over_include():
    """'Ordered' is on BOTH the target (PurchaseOrder) and the include
    (PurchaseOrderLine). The target-catalog check runs first, so the
    column stays in `fields` and continues to be projected. If the
    include branch short-circuited, this would vanish from the
    projection — the ordering matters, not just the union."""
    menu = _menu()
    intent = _intent(
        "PurchaseOrder",
        include=["PurchaseOrderLine"],
        fields=["Ordered"],
    )
    result = validate_intent(intent, menu)
    assert result is None
    assert intent.fields == ["Ordered"]
    assert intent.unresolved_fields == []


def test_multiple_fields_mixed_target_and_child():
    """A target field and a child field in one request: the target field
    stays, the child field is absorbed by the include, and unresolved
    stays empty."""
    menu = _menu()
    intent = _intent(
        "PurchaseOrder",
        include=["PurchaseOrderLine"],
        fields=["Status", "Description"],
    )
    result = validate_intent(intent, menu)
    assert result is None
    assert intent.fields == ["Status"]
    assert intent.unresolved_fields == []


# ─────────────────────────────────────────────────────────────────────
# The curated map is still load-bearing
# ─────────────────────────────────────────────────────────────────────


def test_address_map_entry_still_load_bearing():
    """'city' is in _FIELDS_SATISFIED_BY_INCLUDE['Address'] but NOT in
    the Address KG catalog. The general include-catalogue check alone
    would report it unresolved; the map must still satisfy it."""
    menu = _menu()
    intent = _intent("Supplier", include=["Address"], fields=["city"])
    result = validate_intent(intent, menu)
    assert result is None
    assert intent.unresolved_fields == []
    assert intent.fields == []


def test_address_country_now_via_include_catalogue():
    """'Country' IS on the Address KG catalog. The new include-catalogue
    path satisfies it; previously the curated map's 'country' entry did.
    Same outcome either way — this pins that the new path works."""
    menu = _menu()
    intent = _intent("Supplier", include=["Address"], fields=["Country"])
    result = validate_intent(intent, menu)
    assert result is None
    assert intent.unresolved_fields == []
    assert intent.fields == []


# ─────────────────────────────────────────────────────────────────────
# Case handling
# ─────────────────────────────────────────────────────────────────────


def test_case_insensitive_include_catalogue_match():
    """The parser can emit a lowercase column; the include-catalogue
    check case-folds, so 'description' matches 'Description'.
    'menu.is_known_field' is case-sensitive, so lowercase text falls to
    the include branch rather than matching the target — this is the
    pre-existing behaviour and is unchanged."""
    menu = _menu()
    intent = _intent(
        "PurchaseOrder",
        include=["PurchaseOrderLine"],
        fields=["description"],
    )
    result = validate_intent(intent, menu)
    assert result is None
    assert intent.unresolved_fields == []
    # 'description' did NOT match the target (case-sensitive), so it
    # fell to the include branch and was dropped from fields entirely.
    assert intent.fields == []


# ─────────────────────────────────────────────────────────────────────
# The "genuinely unknown" case still behaves
# ─────────────────────────────────────────────────────────────────────


def test_genuinely_unknown_field_still_unresolved():
    """'quantum flux' matches neither the target nor any include. The
    display note must still fire — the fix is narrow."""
    menu = _menu()
    intent = _intent(
        "PurchaseOrder",
        include=["PurchaseOrderLine"],
        fields=["quantum flux"],
    )
    result = validate_intent(intent, menu)
    assert result is None
    assert intent.unresolved_fields == ["quantum flux"]
    assert intent.fields == []
