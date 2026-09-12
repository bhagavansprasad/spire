#!/usr/bin/env python3
"""
Apply the BUG-1 Step 2 insertion into context_assembly.py.

The _SYSTEM_PROMPT_PREAMBLE literal is a byte-equality oracle the tests
use to prove the assembled preamble matches. Inserting the new
b_po_supplier_details bullet means adding one string-fragment block to
that literal at the position matching its slot in order.manifest
(right after the 'include the buyer' bullet).

This script modifies src/spire/nl_parser/context_assembly.py IN PLACE.
It is idempotent: a second run is a no-op. It aborts if the anchor is
missing.

Run AFTER:
  - adding procurement/b_po_supplier_details.sysprompt
  - adding the manifest line

Run BEFORE:
  - pytest tests/test_parser_context_assembly.py

Usage:
    python scripts/apply_bug1_step2_context_assembly.py --dry-run
    python scripts/apply_bug1_step2_context_assembly.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "src" / "spire" / "nl_parser" / "context_assembly.py"

# The discriminating text of the anchor line — everything else about the
# line (leading spaces, surrounding quotes, \n escape) may vary. If this
# substring is not in any line, we abort.
ANCHOR_NEEDLE = "add 'Buyer' to include."

# Marker that tells us the insertion has already been applied.
ALREADY_APPLIED_MARKER = "supplier details for PO X"

# The new source lines to insert, WITHOUT trailing newlines (the join
# adds them). Each line is a Python string fragment inside the literal.
# Indented 4 spaces to match the surrounding fragments. The final line
# ends with the escape sequence \n (backslash, n) — written as \\n here
# so this script's own source is correct.
INSERTION_LINES = [
    '    "- \'supplier details for PO X\' / \'show the supplier on PO X\' / "',
    '    "\'who is the supplier on PO X\' -> target_entity \'PurchaseOrder\' "',
    '    "with a \'by_id\' filter. Do NOT add \'Supplier\' to include; the "',
    '    "supplier name, number, site and contact are projected directly "',
    '    "from the PO header by the by_id fetcher.\\n"',
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would change; do not write.")
    args = ap.parse_args()

    if not TARGET.is_file():
        print(f"ERROR: target file not found: {TARGET}", file=sys.stderr)
        return 1

    text = TARGET.read_text(encoding="utf-8")

    if ALREADY_APPLIED_MARKER in text:
        print(f"Already applied — marker present in {TARGET}. No change.")
        return 0

    lines = text.split("\n")
    anchor_index = -1
    for i, line in enumerate(lines):
        if ANCHOR_NEEDLE in line:
            anchor_index = i
            break

    if anchor_index < 0:
        print(f"ERROR: anchor not found in {TARGET}.", file=sys.stderr)
        print(f"  Expected a line containing: {ANCHOR_NEEDLE!r}",
              file=sys.stderr)
        print("  Aborting without modifying the file.", file=sys.stderr)
        return 1

    new_lines = lines[: anchor_index + 1] + INSERTION_LINES + lines[anchor_index + 1:]
    new_text = "\n".join(new_lines)

    if args.dry_run:
        print(f"[dry-run] anchor at line {anchor_index + 1}: "
              f"{lines[anchor_index].strip()}")
        print(f"[dry-run] would insert {len(INSERTION_LINES)} line(s) "
              f"({len(new_text) - len(text)} chars)")
        print(f"[dry-run] file would grow from {len(text)} to {len(new_text)} chars")
        return 0

    TARGET.write_text(new_text, encoding="utf-8")
    print(f"Updated {TARGET}")
    print(f"  inserted {len(INSERTION_LINES)} line(s) after line {anchor_index + 1}")
    print(f"  file grew by {len(new_text) - len(text)} chars")
    print()
    print("Next: pytest tests/test_parser_context_assembly.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())