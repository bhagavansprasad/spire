#!/usr/bin/env python3
"""
BUG-1 Step 2 verification — does the parser preamble have a rule for
"supplier details for PO X"?

Read-only. Static analysis of the parser prompt blocks. Does NOT call any
LLM, does NOT touch the KG, does NOT modify any file.

Four questions:
  1. Does the current preamble mention any S1-shaped phrasing?
     (If yes, the model has a rule; if no, we are adding coverage.)
  2. Where does a new bullet slot into order.manifest?
  3. How many bytes does the preamble gain, and is that a concern?
  4. What oracle chain needs updating when the prompt changes?

Usage:
    python scripts/verify_bug1_step2.py 2>&1 | tee verify_bug1_step2.txt
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTEXT_DIR = REPO_ROOT / "src" / "spire" / "nl_parser" / "context"
MANIFEST = CONTEXT_DIR / "order.manifest"
CONTEXT_ASSEMBLY = (
    REPO_ROOT / "src" / "spire" / "nl_parser" / "context_assembly.py"
)
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_parser_context.py"


# Phrases that, if present, would mean the model already has an explicit
# rule for "supplier details for PO X" and would not have to guess.
S1_PHRASES = [
    "supplier details for po",
    "show the supplier on po",
    "who is the supplier on po",
    "supplier on po",
    "supplier for po",
    "po's supplier",
    "supplier information for po",
]

# Comparison phrases — rules we KNOW exist and that the S1 case is
# pattern-matching against. Printed for contrast.
REFERENCE_PHRASES = [
    "include the buyer",
    "with the buyer",
    "show the buyer assigned",
    "supplier details",
    "supplier site",
]


def _manifest_entries() -> list[str]:
    """Return the manifest's non-comment, non-blank lines, in order."""
    if not MANIFEST.is_file():
        return []
    return [
        ln.strip()
        for ln in MANIFEST.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def _assembled_text() -> str:
    """Concatenate every block in manifest order, the same way production does."""
    parts: list[str] = []
    for rel in _manifest_entries():
        block = CONTEXT_DIR / rel
        if block.is_file():
            parts.append(block.read_text(encoding="utf-8"))
    return "".join(parts)


def check_phrases() -> None:
    print("[1] Does the current preamble mention any S1-shaped phrasing?")
    print(f"    Reading {CONTEXT_DIR} .sysprompt blocks in manifest order.\n")

    full = _assembled_text()
    if not full:
        print("    !! No preamble text found. Manifest or blocks missing.\n")
        return

    full_lower = full.lower()

    print("    S1 candidate phrasings (the rule we would be ADDING):")
    s1_total = 0
    for phrase in S1_PHRASES:
        n = full_lower.count(phrase)
        s1_total += n
        print(f"      {phrase!r:<42}  {n if n else 'not found'}")

    print("\n    Reference phrasings (rules we KNOW exist, for contrast):")
    for phrase in REFERENCE_PHRASES:
        n = full_lower.count(phrase)
        print(f"      {phrase!r:<42}  {n if n else 'not found'}")

    print()
    if s1_total == 0:
        print("    --> No S1-shaped rule found. Confirms the gap: the model")
        print("        must guess for 'supplier details for PO X', and the")
        print("        guess is unstable (13/20 refuse on the live batch).")
        print("        Step 2 adds the missing rule.")
    else:
        print("    --> Some S1-shaped phrasing is already present. Before")
        print("        adding anything, we need to see why the existing")
        print("        mention is not sufficient. Investigate before fixing.")
    print()


def where_to_insert() -> None:
    print("[2] Where a new block would slot into order.manifest\n")

    entries = _manifest_entries()
    if not entries:
        print("    !! No manifest entries found.\n")
        return

    print(f"    Manifest has {len(entries)} blocks. Procurement section:")
    for i, rel in enumerate(entries, 1):
        if rel.startswith("procurement/"):
            print(f"      line {i:>3}:  {rel}")
    print()

    print("    Proposed insertion point:")
    print("      'procurement/b_po_supplier_details.sysprompt' inserted")
    print("      immediately AFTER 'procurement/b_buyer_include.sysprompt',")
    print("      so the two 'how to fetch something on a PO' rules read")
    print("      together. That is the same pattern the manifest already")
    print("      follows for related blocks.")
    print()


def size_check() -> None:
    print("[3] Byte-count impact\n")

    full = _assembled_text()
    current = len(full)
    print(f"    Current assembled preamble:  {current:>8,} chars")

    # The proposed bullet as we would ship it. Kept identical to the text
    # that would go into the new .sysprompt block. Adjust if the wording
    # changes during the fix — this is a draft, not a commitment.
    proposed = (
        "- 'supplier details for PO X' / 'show the supplier on PO X' / "
        "'who is the supplier on PO X' -> target_entity 'PurchaseOrder' "
        "with a 'by_id' filter. Do NOT add 'Supplier' to include; the "
        "supplier name, number, site and contact are projected directly "
        "from the PO header by the by_id fetcher.\n"
    )
    print(f"    Proposed bullet:             {len(proposed):>8,} chars")
    print(f"    Projected preamble:          {current + len(proposed):>8,} chars")
    delta_pct = (len(proposed) / current * 100) if current else 0.0
    print(f"    Delta:                       {delta_pct:>7.2f}%")
    print()

    print("    Context for judging risk:")
    print("      - The S1 parse emits 3,440-3,741 output tokens against a")
    print("        ~8,000 output ceiling. Adding ~350 input chars translates")
    print("        to about 90 input tokens. The output ceiling is untouched.")
    print("      - The classifier already runs against a 2,321-char prompt")
    print("        that includes the full module menu — much of the parser's")
    print("        content is not sent in single-module routing.")
    print("      - The parse prompt in the live S1 run showed [len=19731 chars]")
    print("        and 4,898 input tokens. +90 tokens is a +1.8% input change.")
    print("      - The deterministic BUG-2 gate + BUG-3 backstop still hold if")
    print("        a bad include slips past the parser. The blast radius of a")
    print("        wrong bullet is bounded by those guards.")
    print()
    print("    Recommendation: proceed. The regression run across")
    print("    scripts/prompts/*.txt after the fix is what proves it.")
    print()


def check_oracle_chain() -> None:
    print("[4] Byte-equality oracle chain — what needs updating\n")

    for path in (BUILD_SCRIPT, CONTEXT_ASSEMBLY):
        rel = path.relative_to(REPO_ROOT)
        exists = "present" if path.is_file() else "MISSING"
        print(f"    {rel}   [{exists}]")

    test = REPO_ROOT / "tests" / "test_parser_context_assembly.py"
    rel = test.relative_to(REPO_ROOT)
    exists = "present" if test.is_file() else "MISSING"
    print(f"    {rel}   [{exists}]")

    print()
    print("    The fix will touch four places, in this order:")
    print("      1. Add src/spire/nl_parser/context/procurement/"
          "b_po_supplier_details.sysprompt")
    print("      2. Add the file to order.manifest (after b_buyer_include)")
    print("      3. Insert the same text into _SYSTEM_PROMPT_PREAMBLE in")
    print("         context_assembly.py, at the position matching its slot")
    print("         in the manifest")
    print("      4. Recompute _EXPECTED_LITERAL_SHA in build_parser_context.py")
    print()
    print("    Then tests/test_parser_context_assembly.py proves the")
    print("    assembled-from-files preamble still equals the literal —")
    print("    byte for byte. If it fails, the insertion position or the")
    print("    text differs between the two, and the fix is wrong.")
    print()


def main() -> None:
    print("=== BUG-1 Step 2 verification — parser prompt coverage ===\n")
    check_phrases()
    where_to_insert()
    size_check()
    check_oracle_chain()
    print("=== done ===")


if __name__ == "__main__":
    main()