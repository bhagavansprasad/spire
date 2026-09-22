"""F-015 regression — an empty result that arrived via a capped fetch
must say so, not narrate as clean "nothing found".

F-015: ``Show receipts for ABC Corporation Americas at Santa Clara``
returns ``No receipts found matching the criteria.`` — indistinguishable
from a query whose source genuinely holds no matching records. The truth
is different: the fetch was capped (the site filter runs client-side over
a 500-row over-fetch, and account 26370 holds 1,386 receipts), so the
empty result came from a sample, not from the whole collection.

The defect was in ``synthesize_response``'s empty-bucket shortcut, which
fired BEFORE truncation was consulted and constructed the response with
``truncation_notes=[]`` unconditionally. Both ``truncation_by_step`` and
``metadata_by_step`` were parameters of the function and reachable from
the shortcut's scope — the flag existed, nothing read it.

The fix consults them via ``_truncated_steps`` and, when a step was
capped, replaces the summary and populates the notes.

Three tests, one per state the fix must distinguish:

  * empty AND capped     -> summary names the sample, notes non-empty
  * empty AND complete   -> clean "No ... found" wording, no notes
  * empty with total     -> the source total is named when the tool
                            reported one

All local. No LLM on this path — the shortcut returns before any LLM
setup, and the fix keeps it that way.
"""
from __future__ import annotations

from spire.synthesizer.synthesizer import (
    StandardReceiptResponse,
    synthesize_response,
)

# The fix's helper is imported lazily, not at module level. On a reverted
# tree the module-level import would fail at COLLECTION, aborting the
# whole file and telling us nothing about the behavioural tests. Same
# pattern as test_f007_empty_child_ack.py.
def _helper():
    from spire.synthesizer.synthesizer import _truncated_steps
    return _truncated_steps


# ─────────────────────────────────────────────────────────────────────
# The bug — an empty result from a capped fetch must say so
# ─────────────────────────────────────────────────────────────────────


def test_empty_result_from_capped_fetch_names_the_sample():
    """F-015's reproducer.

    The executor produces an empty ``standard_receipts`` bucket and a
    truncation entry with ``truncated=True`` and ``total_available=None``
    (the tool's AI-7 shape — the site filter exceeded the cap, so the
    true count is unknown). The old code returned a clean "No receipts
    found matching the criteria."; the fix must acknowledge the cap.
    """
    outputs = {"standard_receipts": []}
    truncation = {
        "standard_receipts": {
            "truncated": True,
            "total_available": None,
            "limit_applied": 25,
        }
    }
    result = synthesize_response(
        outputs,
        target_entity="StandardReceipt",
        truncation_by_step=truncation,
    )
    assert isinstance(result, StandardReceiptResponse)
    assert "sample" in result.summary.lower() or "capped" in result.summary.lower(), (
        f"F-015: an empty result from a capped fetch narrated as a clean "
        f"'nothing found'. Summary was: {result.summary!r}"
    )
    assert result.truncation_notes, (
        "F-015: the truncation flag was set but no note reached the answer."
    )


# ─────────────────────────────────────────────────────────────────────
# The guard — a genuinely empty result must stay clean
# ─────────────────────────────────────────────────────────────────────


def test_genuinely_empty_result_unchanged():
    """No truncation flag: the source really holds no matching records.

    The summary must remain the clean "No receipts found matching the
    criteria." — the fix must not fire where nothing was capped, or every
    empty query gains a spurious "sample" caveat about a cap that never
    happened.
    """
    outputs = {"standard_receipts": []}
    result = synthesize_response(
        outputs,
        target_entity="StandardReceipt",
        truncation_by_step=None,
    )
    assert isinstance(result, StandardReceiptResponse)
    assert result.summary == "No receipts found matching the criteria."
    assert result.truncation_notes == []


def test_truncated_false_is_not_treated_as_capped():
    """A truncation entry with ``truncated=False`` is not a cap.

    The condition is exactly ``entry.get("truncated") is True`` — not
    truthiness, not mere presence. An entry that says False (a complete
    fetch with the flag explicitly cleared) must fall through to the
    clean wording, or the "sample" narrative fires on every query whose
    metadata happens to be populated.
    """
    outputs = {"standard_receipts": []}
    metadata = {
        "standard_receipts": {
            "truncated": False,
            "total_available": 0,
        }
    }
    result = synthesize_response(
        outputs,
        target_entity="StandardReceipt",
        metadata_by_step=metadata,
    )
    assert result.summary == "No receipts found matching the criteria."
    assert result.truncation_notes == []


# ─────────────────────────────────────────────────────────────────────
# With a known total — name it
# ─────────────────────────────────────────────────────────────────────


def test_empty_result_with_known_total_names_it():
    """When the tool reported a count, the summary names it.

    ``metadata_by_step`` covers the non-iterating steps and may carry a
    real ``total_available``. The summary should say how many exist in
    the source, so the reader can tell a 0-of-5 from a 0-of-1,000,000.
    """
    outputs = {"standard_receipts": []}
    metadata = {
        "standard_receipts": {
            "truncated": True,
            "total_available": 1386,
        }
    }
    result = synthesize_response(
        outputs,
        target_entity="StandardReceipt",
        metadata_by_step=metadata,
    )
    assert "1,386" in result.summary, (
        f"F-015: a known source total was not named. Summary was: "
        f"{result.summary!r}"
    )


# ─────────────────────────────────────────────────────────────────────
# The helper, directly
# ─────────────────────────────────────────────────────────────────────


def test_helper_empty_when_nothing_truncated():
    assert _helper()(None, None) == []
    assert _helper()({}, {}) == []
    assert _helper()(
        {"x": {"truncated": False}}, {"y": {"truncated": False}}
    ) == []


def test_helper_reads_both_sources_and_dedupes():
    """A name in both sources is taken once — the first source wins."""
    truncation = {"a": {"truncated": True, "total_available": 5}}
    metadata = {
        "a": {"truncated": True, "total_available": 5},   # dup, ignored
        "b": {"truncated": True, "total_available": None},
    }
    result = _helper()(truncation, metadata)
    names = [name for name, _ in result]
    assert names == ["a", "b"]


def test_helper_ignores_non_dict_entries():
    """A stray non-dict in either source must not raise."""
    assert _helper()({"x": "not-a-dict"}, None) == []
