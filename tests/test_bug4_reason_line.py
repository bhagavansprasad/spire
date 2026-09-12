"""
Regression tests for BUG-4 sub-part A — the Reason line of an
unsupported_filter refusal prefers the parser's specific `detail` over
the generic narrowing sentence, BUT ONLY when the detail is plain prose
and not prose quoting an internal identifier.

BACKGROUND

When the parser self-declares a refusal with `unanswerable_kind=
'unsupported_filter'`, the resulting Refusal has flavor
UNSUPPORTED_FILTER and an EMPTY `offending_filters` (that field is only
populated by the KG-validation path). Before this fix, `_reason_line`
fell through to "I can look up suppliers, but not the way this question
narrows them" and DISCARDED the model's `detail`.

The S1 case is why that was wrong: the detail was a specific, accurate
diagnosis — "Cannot retrieve supplier details for a specific purchase
order because Supplier is not an allowed include on PurchaseOrder." —
and the generic sentence threw it away.

But the second branch exists for a reason. The model sometimes echoes an
internal identifier verbatim — "requires the 'by_customer_name' filter"
— which must not reach a user. That shape is what
test_nl_parser_capability.py::test_unsupported_filter_without_named_filters_still_reads
protects against, and it caught the first attempt at this fix.

So the discriminator is: show detail if it has no snake_case token,
fall to the generic sentence if it does. These tests pin both sides.

The tests hit `load_kg_menu()` only so `_known_entity` can look entities
up; skipped if personas.yaml is absent, same as the other capability
tests.
"""

from __future__ import annotations

import pytest

from spire.config import PERSONAS_FILE
from spire.nl_parser.capability import (
    _detail_has_internal_identifier,
    capability_message,
)
from spire.nl_parser.result import Refusal, RefusalFlavor
from spire.nl_parser.vocabulary import KGMenu, load_kg_menu


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping KG-backed tests",
)


@pytest.fixture(scope="module")
def menu() -> KGMenu:
    return load_kg_menu()


def _reason_of(refusal: Refusal, menu: KGMenu) -> str:
    """Extract the reason text from a capability message."""
    msg = capability_message(refusal, menu)
    first_para = msg.split("\n\n")[0]
    return first_para.replace("Reason:", "").strip()


# ── The fix: self-declared UNSUPPORTED_FILTER + clean prose detail ─────


def test_unsupported_filter_with_clean_detail_uses_detail(menu: KGMenu) -> None:
    """The specific case: self-declared UNSUPPORTED_FILTER whose `detail`
    is plain-language prose. Reason line must be the detail verbatim."""
    detail = (
        "Cannot retrieve supplier details for a specific purchase order "
        "because Supplier is not an allowed include on PurchaseOrder."
    )
    refusal = Refusal(
        flavor=RefusalFlavor.UNSUPPORTED_FILTER,
        detail=detail,
        offending_entity="Supplier",
    )
    assert _reason_of(refusal, menu) == detail


def test_unsupported_filter_with_clean_detail_and_no_entity(menu: KGMenu) -> None:
    """Same, but no entity is named. Detail still wins."""
    detail = "The question needs an aggregation that is not supported."
    refusal = Refusal(
        flavor=RefusalFlavor.UNSUPPORTED_FILTER,
        detail=detail,
        offending_entity=None,
    )
    assert _reason_of(refusal, menu) == detail


# ── The discriminator: leaky prose falls to generic ────────────────────


def test_unsupported_filter_with_snake_case_in_detail_falls_to_generic(
    menu: KGMenu,
) -> None:
    """A detail quoting a snake_case filter key is unsafe to render — it
    would leak an internal identifier. The generic sentence fires instead.
    This is the boundary the fix must respect: clean prose is shown,
    jargon is not."""
    refusal = Refusal(
        flavor=RefusalFlavor.UNSUPPORTED_FILTER,
        detail="This filter requires the 'by_customer_name' argument.",
        offending_entity="Supplier",
    )
    reason = _reason_of(refusal, menu)
    assert "by_customer_name" not in reason
    # We do not translate; we hide. The generic sentence is what fires.
    assert "not the way this question narrows them" in reason


def test_unsupported_filter_with_has_open_PO_in_detail_falls_to_generic(
    menu: KGMenu,
) -> None:
    """Same as above with a different snake_case key — has_open_PO has
    internal capitalisation and the regex must be case-insensitive."""
    refusal = Refusal(
        flavor=RefusalFlavor.UNSUPPORTED_FILTER,
        detail="Only has_open_PO can be filtered on.",
        offending_entity="Supplier",
    )
    reason = _reason_of(refusal, menu)
    assert "has_open_PO" not in reason
    assert "not the way this question narrows them" in reason


# ── The discriminator itself (unit) ────────────────────────────────────


def test_detail_has_internal_identifier_flags_snake_case() -> None:
    assert _detail_has_internal_identifier(
        "requires the 'by_customer_name' filter"
    )
    assert _detail_has_internal_identifier("filter has_open_PO")
    assert _detail_has_internal_identifier("by created_before date")
    assert _detail_has_internal_identifier("uses supplier_number as a key")


def test_detail_has_internal_identifier_admits_plain_prose() -> None:
    assert not _detail_has_internal_identifier("")
    assert not _detail_has_internal_identifier(
        "Cannot retrieve supplier details for a specific purchase order."
    )
    assert not _detail_has_internal_identifier(
        "Supplier is not an allowed include on PurchaseOrder."
    )
    # CamelCase is deliberately allowed through — see the module docstring.
    assert not _detail_has_internal_identifier(
        "ReceivablesInvoice cannot be filtered this way."
    )


# ── The fix must not break the KG-validation path ─────────────────────


def test_unsupported_filter_with_offending_filters_still_uses_them(
    menu: KGMenu,
) -> None:
    """The KG-validation path sets `offending_filters`. That path must
    NEVER show `detail` (it's a raw dump of internal filter names).
    Reason line should be the structured "not by <filters>" form."""
    refusal = Refusal(
        flavor=RefusalFlavor.UNSUPPORTED_FILTER,
        detail="Unsupported filter type(s): ['net_30_terms']. Supported "
        "filters: [21 more]",
        offending_entity="Supplier",
        offending_filters=["net_30_terms"],
    )
    reason = _reason_of(refusal, menu)
    # Structured form fires; must not contain the raw-dump text.
    assert "net 30 terms" in reason
    assert "Supported filters:" not in reason
    assert "Unsupported filter type(s):" not in reason


# ── Edge case: no detail → generic sentence still fires ───────────────


def test_unsupported_filter_no_detail_falls_to_generic(menu: KGMenu) -> None:
    """When `detail` is empty (rare but possible), the generic narrowing
    sentence is the honest fallback — the fix must not break it."""
    refusal = Refusal(
        flavor=RefusalFlavor.UNSUPPORTED_FILTER,
        detail="",
        offending_entity="Supplier",
    )
    reason = _reason_of(refusal, menu)
    assert "not the way this question narrows them" in reason