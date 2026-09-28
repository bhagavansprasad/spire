"""F-055 regression — days-based Invoice windows must convert to whole
months.

Reproducer: "invoices in the last 7 days" — pre-fix the model converts
7 days to 0.23 months, and the planner's integer guard
(`_build_entity_fetcher_args` in plan_builders.py) rejects the filter.
The sibling "invoices in the last 30 days" works because 30 is exactly
1 month; the phrasing list in b_invoice_date.sysprompt treats days as a
synonym of months but never names the conversion.

The fix teaches the conversion in the sysprompt (and its byte-equality
mirror in context_assembly.py): for a days or weeks phrasing, round up
to a whole number of months. The value must be a positive INTEGER.

These are content tests — the sysprompt text is the fix. The model's
actual behaviour (does it obey the new clause?) is verified by the
V-walk's N>=20 sweep, per FIX_PLAN V8. What is deterministic here is
that both files carry the rule.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SYSPROMPT = REPO / "src/spire/nl_parser/context/payables/b_invoice_date.sysprompt"
ASSEMBLY = REPO / "src/spire/nl_parser/context_assembly.py"


# Markers of the conversion clause. The exact wording is flexible; any
# combination of these says "days count -> whole number of months".
# Pre-fix none appear — the rule lists days phrasings without ever
# saying how to convert them.
_WHOLE_MONTH_MARKERS = ("whole number", "integer")
_ROUND_MARKERS = ("round up", "rounded up", "rounding up", "ceil")


def _has_conversion_clause(text: str) -> bool:
    lower = text.lower()
    return (
        "days" in lower
        and any(m in lower for m in _WHOLE_MONTH_MARKERS)
        and any(m in lower for m in _ROUND_MARKERS)
    )


def test_sysprompt_teaches_days_to_months_conversion():
    """F-055: the RELATIVE RECENT rule must state that a days count
    converts to a whole number of months.

    Pre-fix the bullet lists 'invoices in the last 30 days' as a covered
    phrasing without saying how to convert. The model does 7/30 = 0.23
    and the planner rejects it.
    """
    text = SYSPROMPT.read_text()
    assert _has_conversion_clause(text), (
        "F-055: b_invoice_date.sysprompt lists days phrasings but does "
        "not tell the model to round up to a WHOLE NUMBER of months. "
        "The model will emit 0.23 for '7 days' and the planner will "
        "reject it."
    )


def test_assembly_mirror_teaches_days_to_months_conversion():
    """The byte-equality mirror in context_assembly.py must carry the
    same rule, or the oracle in test_parser_context_assembly.py fails."""
    text = ASSEMBLY.read_text()
    assert _has_conversion_clause(text), (
        "F-055: context_assembly.py::_SYSTEM_PROMPT_PREAMBLE does not "
        "carry the days-to-months conversion rule. The byte-equality "
        "oracle will fail; both files must be updated together."
    )


def test_relative_recent_bullets_match_between_sysprompt_and_mirror():
    """The Invoice RELATIVE RECENT bullet must be identical in both
    files. The byte-equality oracle checks the whole preamble; this
    pinpoints the one bullet F-055 changes, so a partial edit fails
    here with a narrower message than the oracle's."""
    def _invoice_bullet(path: Path) -> str | None:
        for line in path.read_text().splitlines():
            if (
                line.startswith("- RELATIVE RECENT:")
                and "'invoices in the last 6 months'" in line
            ):
                return line
        return None

    sys_bullet = _invoice_bullet(SYSPROMPT)
    asm_bullet = _invoice_bullet(ASSEMBLY)
    assert sys_bullet is not None, (
        "Invoice RELATIVE RECENT bullet not found in b_invoice_date.sysprompt"
    )
    assert asm_bullet is not None, (
        "Invoice RELATIVE RECENT bullet not found in context_assembly.py"
    )
    assert sys_bullet == asm_bullet, (
        "F-055: the Invoice RELATIVE RECENT bullet has drifted between "
        "the sysprompt and the context_assembly.py mirror. Update both."
    )
