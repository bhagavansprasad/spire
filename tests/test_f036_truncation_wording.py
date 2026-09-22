"""F-036 regression — the truncation note must not claim "for filtering"
on a fetch that applied no filter.

F-036: 'Suppliers with their addresses' produces a note reading
``25 examined for filtering``. The fetch applied no filter —
``tool_args`` carries only ``include_addresses=True``. The phrase is
hardcoded in ``_local_truncation`` and fires unconditionally.

The fix: replace the phrase with a neutral verb that is true on both
filtered and unfiltered fetches. The count itself stays — the fix
removes the false claim, not the count.

Deterministic. No LLM, no pod.
"""
from __future__ import annotations

from spire.synthesizer.synthesizer import synthesize_response


def _supplier_rows(n: int) -> list[dict]:
    return [
        {
            "SupplierId": 300000000000000 + i,
            "SupplierNumber": str(1252 + i),
            "Supplier": f"Supplier {i}",
        }
        for i in range(n)
    ]


def _truncation() -> dict:
    return {
        "suppliers": {
            "total_available": 656,
            "truncated": True,
            "limit_applied": 25,
        }
    }


def test_unfiltered_fetch_note_does_not_say_for_filtering():
    """F-036's reproducer. A fetch with no filter must not use the
    phrase 'for filtering' in its truncation note."""
    outputs = {"suppliers": _supplier_rows(5)}
    result = synthesize_response(
        outputs,
        target_entity="Supplier",
        truncation_by_step=_truncation(),
    )
    assert result.truncation_notes, (
        "F-036: the fixture should produce a note; none appeared."
    )
    for note in result.truncation_notes:
        assert "for filtering" not in note, (
            f"F-036: an unfiltered fetch still claims 'for filtering'. "
            f"Note was: {note!r}"
        )


def test_note_still_names_the_row_count():
    """The fix removes the FALSE claim, not the count. The note still
    says how many rows are shown and what the source total is."""
    outputs = {"suppliers": _supplier_rows(5)}
    result = synthesize_response(
        outputs,
        target_entity="Supplier",
        truncation_by_step=_truncation(),
    )
    joined = " | ".join(result.truncation_notes)
    assert "656" in joined, (
        f"F-036: the note lost the source total. Notes: "
        f"{result.truncation_notes!r}"
    )
    assert "5 returned" in joined, (
        f"F-036: the note lost the row count or kept the old verb. "
        f"Notes: {result.truncation_notes!r}"
    )
