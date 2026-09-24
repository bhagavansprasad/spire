"""
F-003 / F-050: the modes/ and columns/ folders must be reachable from a
router-scoped parse.

Before this fix, _TIER1 named only "core" and "refusals", and
assemble_subset loads set(_TIER1) | set(modules). "modes" and "columns"
were in neither, so no routed parse saw their content. F-003's three PO
aggregation ops and F-050's column-projection rules were unreachable.

The last test closes the reverse drift: the op set in DraftAggregate.op's
description must equal the op set in modes/m_aggregation.sysprompt, or a
future op added to one and not the other will reintroduce the F-004
misroute (a PO-value ranking that reaches for a comparison op because the
right aggregation op is invisible).
"""

from __future__ import annotations

import re
from pathlib import Path

from spire.nl_parser.context_assembly import (
    _CONTEXT_DIR,
    _TIER1,
    assemble_subset,
)
from spire.nl_parser.vocabulary import load_kg_menu


_MODES_FILE = _CONTEXT_DIR / "modes" / "m_aggregation.sysprompt"

# Each op bullet in modes/m_aggregation.sysprompt starts with "- op='name'".
_OP_RE = re.compile(r"^- op='([a-z_]+)'", re.MULTILINE)

# The op set the two registries must agree on. Named explicitly (rather
# than derived) so a future op added to one file and not the other trips
# this test with a message naming the side that drifted.
_EXPECTED_OPS = frozenset({
    "by_supplier",
    "top_invoices_by_amount",
    "po_value_by_supplier",
    "po_count_by_status",
    "open_po_summary",
    "exposure_ranking",
    "receipt_method_distribution",
})


def test_tier1_includes_modes_and_columns():
    """F-003 + F-050: both cross-cutting folders are Tier 1."""
    assert "modes" in _TIER1, "F-003: modes/ must be in _TIER1"
    assert "columns" in _TIER1, "F-050: columns/ must be in _TIER1"


def test_scoped_parse_loads_modes_content():
    """F-003: a procurement-scoped parse sees an aggregation rule from modes/."""
    menu = load_kg_menu()
    scoped = assemble_subset(["procurement"], menu)
    assert scoped is not None
    # Distinctive phrase from modes/m_aggregation.sysprompt.
    assert "po_count_by_status" in scoped, (
        "F-003: modes/ content missing from a scoped parse"
    )


def test_scoped_parse_loads_columns_content():
    """F-050: a supplier-scoped parse sees a column rule from columns/."""
    menu = load_kg_menu()
    scoped = assemble_subset(["supplier"], menu)
    assert scoped is not None
    # Distinctive phrase from columns/b_who_columns.sysprompt.
    assert "AUDIT/WHO COLUMNS" in scoped, (
        "F-050: columns/ content missing from a scoped parse"
    )


def test_op_registries_agree():
    """F-003: DraftAggregate.op and modes/m_aggregation.sysprompt list the
    same ops.

    Before this fix, DraftAggregate.op listed top_invoices_by_amount but
    not the three PO ops; m_aggregation.sysprompt listed the three PO ops
    but not top_invoices_by_amount. Both directions are closed now. A
    future op added to one file must be added to the other, or this test
    fails and names the side that drifted.
    """
    from spire.nl_parser.draft import DraftAggregate

    modes_text = _MODES_FILE.read_text(encoding="utf-8")
    modes_ops = set(_OP_RE.findall(modes_text))
    assert modes_ops == _EXPECTED_OPS, (
        "m_aggregation.sysprompt op set drifted from expected.\n"
        f"  extra   (in file, not expected): {sorted(modes_ops - _EXPECTED_OPS)}\n"
        f"  missing (expected, not in file): {sorted(_EXPECTED_OPS - modes_ops)}"
    )

    desc = DraftAggregate.model_fields["op"].description or ""
    missing_from_draft = {op for op in _EXPECTED_OPS if f"'{op}'" not in desc}
    assert not missing_from_draft, (
        f"DraftAggregate.op description missing ops: "
        f"{sorted(missing_from_draft)}"
    )
