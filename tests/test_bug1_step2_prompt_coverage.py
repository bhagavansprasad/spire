"""
Regression tests for BUG-1 Step 2 — the parser preamble has a rule for
"supplier details for PO X".

BACKGROUND

'Show supplier details for PO 701337.' is answerable — the supplier
name, number, site and contact ride on the PO header and are projected
by the by_id fetcher. But the parser preamble has no rule for the
phrasing, so the model guesses. The guess is bimodal: sometimes
include=['Supplier'] (a shape that does not exist in the KG), sometimes
unanswerable=true with a self-declared reason. Step 1 (the strip)
closed the first mode. Step 2 closes the second by giving the model an
explicit rule.

This test file pins three things:

  1. The new .sysprompt block exists on disk and contains the expected
     rule text.

  2. The manifest references it, in the position right after
     procurement/b_buyer_include.sysprompt — so a future edit that
     moves it or drops it fails here.

  3. The ASSEMBLED preamble (built from the files at import) contains
     the rule text — so the scoped prompt a module-routed parse sends
     really carries it.

Plus the byte-equality contract is checked by the pre-existing
tests/test_parser_context_assembly.py, which the same fix updates via
scripts/apply_bug1_step2_context_assembly.py. That test is the one
that proves the literal and the assembled preamble still agree byte
for byte.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spire.nl_parser.context_assembly import (
    _ASSEMBLED_PREAMBLE,
    _CONTEXT_DIR,
    _manifest_pairs,
)


BLOCK_REL = "procurement/b_po_supplier_details.sysprompt"
BLOCK_PATH = _CONTEXT_DIR / BLOCK_REL

# The discriminating text of the new rule. If the block or the manifest
# is edited away, or the wording drifts, these substrings no longer
# appear and the corresponding test fails.
RULE_KEY_PHRASES = (
    "supplier details for PO X",
    "show the supplier on PO X",
    "who is the supplier on PO X",
    "Do NOT add 'Supplier' to include",
    "projected directly from the PO header",
)


# ── 1. The block file exists and carries the rule ──────────────────────


def test_block_file_exists() -> None:
    assert BLOCK_PATH.is_file(), (
        f"Expected prompt block at {BLOCK_PATH}. "
        f"Step 2 adds this file; if it is missing the fix was not applied."
    )


def test_block_contains_rule_key_phrases() -> None:
    text = BLOCK_PATH.read_text(encoding="utf-8")
    missing = [p for p in RULE_KEY_PHRASES if p not in text]
    assert not missing, (
        f"Prompt block {BLOCK_REL} is missing expected phrase(s): {missing}"
    )


def test_block_starts_with_a_bullet() -> None:
    """Every b_*.sysprompt block is a bullet list, one bullet per line,
    starting with '- '. Not a hard rule of the format, but the pattern
    the other procurement blocks follow, and a mismatched block would
    read strangely in the assembled preamble."""
    text = BLOCK_PATH.read_text(encoding="utf-8")
    assert text.lstrip().startswith("- "), (
        f"Block {BLOCK_REL} does not start with a bullet. "
        f"First 60 chars: {text[:60]!r}"
    )


# ── 2. The manifest lists the block in the right position ──────────────


def _manifest_relpaths() -> list[str]:
    return [rel for _module, rel in _manifest_pairs()]


def test_manifest_lists_the_block() -> None:
    rels = _manifest_relpaths()
    assert BLOCK_REL in rels, (
        f"{BLOCK_REL} is not listed in order.manifest. "
        f"The block file exists but the preamble never loads it."
    )


def test_manifest_position_is_after_buyer_include() -> None:
    """The new block sits immediately after
    procurement/b_buyer_include.sysprompt — the two 'how to fetch
    something on a PO' rules read together. This is the slot the fix's
    verification script confirmed; moving it later would change the
    reading order and confuse the two rules."""
    rels = _manifest_relpaths()
    buyer_idx = rels.index("procurement/b_buyer_include.sysprompt")
    new_idx = rels.index(BLOCK_REL)
    assert new_idx == buyer_idx + 1, (
        f"{BLOCK_REL} is at manifest position {new_idx}, but should be "
        f"immediately after procurement/b_buyer_include.sysprompt "
        f"(position {buyer_idx + 1})."
    )


# ── 3. The assembled preamble carries the rule ─────────────────────────


def test_assembled_preamble_contains_the_rule() -> None:
    """The ASSEMBLED preamble is what production sends (built from the
    .sysprompt files in manifest order at import). If the block or the
    manifest were dropped, the assembled preamble would not contain the
    rule text and this test fails."""
    missing = [p for p in RULE_KEY_PHRASES if p not in _ASSEMBLED_PREAMBLE]
    assert not missing, (
        f"Assembled preamble is missing expected phrase(s): {missing}. "
        f"The .sysprompt block or the manifest entry is not being loaded."
    )