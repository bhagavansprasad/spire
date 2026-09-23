"""F-048 regression tests — vague-adjective default window.

Sysprompt-only fix. The tests are content checks on the sysprompt file
and its byte-equality mirror; the end-to-end behaviour is verified by
V1–V2 (promptkit runs) and by the full `--validate` corpus (V9).

Pre-fix all three tests fail: neither the rule nor the default-value
string is present in either file.
"""

from pathlib import Path


_PROCUREMENT_DIR = (
    Path(__file__).resolve().parents[1]
    / "src" / "spire" / "nl_parser" / "context" / "procurement"
)
_CONTEXT_ASSEMBLY = (
    Path(__file__).resolve().parents[1]
    / "src" / "spire" / "nl_parser" / "context_assembly.py"
)


def test_po_created_date_teaches_vague_adjectives():
    """The date rule names the four vague-recency adjectives.

    F-048. Pre-fix the sysprompt has no rule for adjectives without an N,
    so the parser either refuses (unsupported_filter on 'new') or treats
    the adjective as nothing (missing_identifier on 'recent').
    """
    text = (_PROCUREMENT_DIR / "b_po_created_date.sysprompt").read_text()
    for adjective in ("recent", "new", "latest", "fresh"):
        assert adjective in text.lower(), (
            f"b_po_created_date.sysprompt does not teach '{adjective}' as "
            "a vague-recency adjective. See F-048."
        )


def test_po_created_date_vague_adjective_default_is_three_months():
    """The rule emits months=3 as the default window.

    F-048. Pre-fix there is no default; post-fix the value is hardcoded
    to 3 in the sysprompt.
    """
    text = (_PROCUREMENT_DIR / "b_po_created_date.sysprompt").read_text()
    # The rule text carries the months value in a JSON-shaped literal.
    assert '"months": 3' in text or "{\\\"months\\\": 3}" in text, (
        "b_po_created_date.sysprompt does not encode the 3-month default. "
        "See F-048."
    )


def test_context_assembly_literal_mirrors_the_vague_adjective_rule():
    """The byte-equality literal carries the same rule.

    F-048 site 2. The literal in context_assembly.py is what
    tests/test_parser_context_assembly.py compares the disk-assembled
    preamble against; an edit to the sysprompt that does not also move
    the literal fails the byte-equality oracle.
    """
    text = _CONTEXT_ASSEMBLY.read_text()
    for adjective in ("recent purchase orders", "new purchase orders"):
        assert adjective in text.lower(), (
            f"context_assembly.py::_SYSTEM_PROMPT_PREAMBLE does not carry "
            f"the '{adjective}' rule. See F-048 site 2."
        )
