#!/usr/bin/env python3
"""
Carve the parser system-prompt monolith into modular .sysprompt files.

This is the ONE-TIME migration tool for Phase 1 of parser context
modularization (docs/design/FEATURES.md, §4.1). It reads
the live ``_SYSTEM_PROMPT_PREAMBLE`` literal out of
``src/spire/nl_parser/parser.py``, slices it at the approved block boundaries,
and writes 48 ``.sysprompt`` block files plus an ``order.manifest`` under
``src/spire/nl_parser/context/``.

WHY A CARVE SCRIPT (not hand-written files): the files are derived from the live
literal by evaluating each source-line slice, so their concatenation is
byte-identical to the original by construction. The script re-verifies this at
the end and refuses to finish if the join does not equal the literal. It is
idempotent: if the literal ever legitimately changes, re-running re-carves.

Run from the repo root:

    python scripts/build_parser_context.py 2>&1 | tee t.txt

The runtime assembly in parser.py READS these files (once, at import). This
script only CREATES them. The standing invariant that assembly == literal is
enforced by tests/test_parser_context_assembly.py.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


# --- locations -------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
PARSER_PY = REPO_ROOT / "src" / "spire" / "nl_parser" / "parser.py"
CONTEXT_DIR = REPO_ROOT / "src" / "spire" / "nl_parser" / "context"

_LITERAL_ANCHOR = "_SYSTEM_PROMPT_PREAMBLE = ("


# --- the approved carve map ------------------------------------------------
# (block_id, module, start_line, end_line) — 1-based, inclusive, relative to
# parser.py. EMIT ORDER is exactly this order (Phase 1 preserves the original
# top-to-bottom byte order; see design §4.1 / Decision "Option 1").
#
# Line 48 (the "_SYSTEM_PROMPT_PREAMBLE = (" opener) and the bare ")" closer
# carry no string bytes and are deliberately excluded: role_contract starts at
# 49, signoff ends at 522.
#
# IMPORTANT: these line numbers are validated against a known literal hash
# below. If parser.py's literal is edited, the hash guard trips and the map
# must be re-approved before re-carving.

CARVE: list[tuple[str, str, int, int]] = [
    ("role_contract",           "core",         49,  61),
    ("b_country",               "supplier",     62,  63),
    ("b_open_po",               "payables",     64,  65),
    ("b_no_recent_invoices",    "payables",     66,  70),
    ("b_invoice_over_amount",   "supplier",     71,  76),
    ("b_site_in_bu",            "supplier",     77,  94),
    ("b_classification",        "supplier",     95, 107),
    ("b_status",                "supplier",    108, 109),
    ("b_business_relationship", "supplier",    110, 112),
    ("b_name_fragment",         "supplier",    113, 114),
    ("b_created_date",          "supplier",    115, 119),
    ("b_invoices_for_supplier", "payables",    120, 124),
    ("b_invoice_date",          "payables",    125, 128),
    ("b_invoice_amount",        "payables",    129, 132),
    ("b_addresses",             "payables",    133, 137),
    ("b_buyer_include",         "procurement", 138, 139),
    ("b_po_by_id",              "procurement", 140, 152),
    ("b_po_lines",              "procurement", 153, 155),
    ("b_ar_invoice_by_id",      "receivables", 156, 167),
    ("b_ar_invoice_lines",      "receivables", 168, 170),
    ("b_ar_tax_lines",          "receivables", 171, 175),
    ("b_ar_dff",                "receivables", 176, 182),
    ("b_customer_invoices",     "receivables", 183, 195),
    ("b_account_balance",       "receivables", 196, 215),
    ("b_credit_memos",          "receivables", 216, 233),
    ("b_customer_credit_memos", "receivables", 234, 247),
    ("b_account_receipts",      "receivables", 248, 262),
    ("b_site_receipts",         "receivables", 263, 273),
    ("b_receipt_applications",  "receivables", 274, 283),
    ("b_po_schedules",          "procurement", 284, 286),
    ("b_po_distributions",      "procurement", 287, 291),
    ("b_po_created_date",       "procurement", 292, 300),
    ("b_invoices_for_po",       "payables",    301, 305),
    ("b_po_received",           "procurement", 306, 310),
    ("b_contacts",              "supplier",    311, 318),
    ("b_who_columns",           "columns",     319, 325),
    ("b_suppliers_addresses",   "supplier",    326, 332),
    ("b_column_fields",         "columns",     333, 336),
    ("completeness_tail",       "core",        337, 339),
    ("out_of_scope",            "refusals",    340, 349),
    ("m_aggregation",           "modes",       350, 406),
    ("m_comparison",            "modes",       407, 426),
    ("m_count",                 "modes",       427, 433),
    ("m_open_invoices",         "modes",       434, 441),
    ("m_account_balance",       "modes",       442, 452),
    ("m_topn_open_invoices",    "modes",       453, 460),
    ("m_po_lifecycle",          "procurement", 461, 518),
    ("signoff",                 "core",        519, 522),
]

# The known-good hash of the literal these line numbers were approved against.
# A guard, not a lock: if the literal changes, re-approve the carve then update
# this. sha256 of the 29292-char evaluated preamble.
_EXPECTED_LITERAL_SHA = (
    "be6fcaeb07062767d72723befc4b0cd5b4e26a805827f74a82438ec430a2e02b"
)


# --- carve -----------------------------------------------------------------

def _read_parser_source() -> list[str]:
    if not PARSER_PY.is_file():
        raise FileNotFoundError(f"parser.py not found at {PARSER_PY}")
    return PARSER_PY.read_text(encoding="utf-8").split("\n")


def _extract_reference_literal(src_text: str) -> str:
    """Evaluate the whole _SYSTEM_PROMPT_PREAMBLE literal to its exact value."""
    start = src_text.index(_LITERAL_ANCHOR)
    end = src_text.index("\n)\n", start) + 2  # include the closing ")"
    namespace: dict = {}
    exec(src_text[start:end], namespace)  # noqa: S102 - trusted repo source
    return namespace["_SYSTEM_PROMPT_PREAMBLE"]


def _eval_slice(lines: list[str], start: int, end: int) -> str:
    """Evaluate the adjacent string fragments on lines [start, end] to the
    exact text they concatenate to — the same way Python builds the literal."""
    fragment = "\n".join(lines[start - 1:end])  # 1-based inclusive
    namespace: dict = {}
    exec("____value = (\n" + fragment + "\n)", namespace)  # noqa: S102
    return namespace["____value"]


def main() -> int:
    lines = _read_parser_source()
    src_text = "\n".join(lines)

    reference = _extract_reference_literal(src_text)
    ref_sha = hashlib.sha256(reference.encode("utf-8")).hexdigest()

    print(f"parser.py literal: {len(reference)} chars, sha256 {ref_sha}")
    if ref_sha != _EXPECTED_LITERAL_SHA:
        print()
        print("!! LITERAL HASH MISMATCH")
        print(f"   expected {_EXPECTED_LITERAL_SHA}")
        print(f"   got      {ref_sha}")
        print("   The parser literal changed since the carve was approved.")
        print("   Re-approve the CARVE line ranges, then update")
        print("   _EXPECTED_LITERAL_SHA. Refusing to carve against an")
        print("   unverified literal.")
        return 1

    # Fresh context dir every run (idempotent).
    if CONTEXT_DIR.exists():
        shutil.rmtree(CONTEXT_DIR)
    CONTEXT_DIR.mkdir(parents=True)

    manifest: list[str] = []
    assembled_parts: list[str] = []

    for block_id, module, start, end in CARVE:
        text = _eval_slice(lines, start, end)
        module_dir = CONTEXT_DIR / module
        module_dir.mkdir(exist_ok=True)
        rel_path = f"{module}/{block_id}.sysprompt"
        (CONTEXT_DIR / rel_path).write_text(text, encoding="utf-8")
        manifest.append(rel_path)
        assembled_parts.append(text)

    (CONTEXT_DIR / "order.manifest").write_text(
        "\n".join(manifest) + "\n", encoding="utf-8"
    )

    # --- self-verify: joined blocks must equal the literal, byte-for-byte ---
    assembled = "".join(assembled_parts)
    asm_sha = hashlib.sha256(assembled.encode("utf-8")).hexdigest()

    print(f"wrote {len(manifest)} block files + order.manifest to {CONTEXT_DIR}")
    print(f"assembled: {len(assembled)} chars, sha256 {asm_sha}")

    if assembled != reference:
        # Locate first divergence for a useful failure.
        for i, (a, b) in enumerate(zip(assembled, reference)):
            if a != b:
                print(f"!! BYTE MISMATCH at char {i}: {a!r} vs {b!r}")
                print(f"   assembled: ...{assembled[max(0, i - 40):i + 10]!r}")
                print(f"   reference: ...{reference[max(0, i - 40):i + 10]!r}")
                break
        else:
            print(f"!! LENGTH MISMATCH: {len(assembled)} vs {len(reference)}")
        print("   Carve is NOT faithful. Files written but INVALID.")
        return 1

    print("BYTE-EQUAL: True  ✓  carve is faithful to the literal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
