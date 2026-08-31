#!/usr/bin/env python3
"""
Add the entity->module mapping to the KG schema (Phase 1, part 2).

Patches scripts/sql/kg_schema.sql in place, making two edits:

  1. kg_entity CREATE TABLE: add a `module` column, NOT NULL, with a CHECK
     constraint limiting it to the four Fusion modules.
  2. All 22 `INSERT INTO kg_entity VALUES (...)` statements: append the entity's
     module as a new trailing value (the INSERTs are positional, so a new column
     means a new value in every row).

The `module` field is the KG's source of truth for which Fusion module an entity
belongs to — read by the selective-load harness (part 3) and the Phase-2 router.
See docs/features/parser_context_modularization.md §4.3.

This is idempotent-guarded: it asserts the column is not already present and that
exactly 22 INSERTs are patched, each once. Run from the repo root:

    python scripts/add_entity_module.py 2>&1 | tee t.txt

After it succeeds: bump the tripwires (print_kg.py, test_kg_metadata.py) — those
are separate edits — then rebuild:  python scripts/rebuild_kg.py
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "sql" / "kg_schema.sql"
# kg_schema.sql lives under scripts/sql/, and this script under scripts/, so:
SCHEMA = REPO_ROOT / "scripts" / "sql" / "kg_schema.sql"


# entity_name -> Fusion module. All 22 entities; every child mapped to the
# module of the endpoint it hangs off. Confirmed grouping.
ENTITY_MODULE: dict[str, str] = {
    # payables
    "Invoice": "payables",
    # procurement
    "PurchaseOrder": "procurement",
    "PurchaseOrderLine": "procurement",
    "PODistribution": "procurement",
    "POSchedule": "procurement",
    "Buyer": "procurement",
    # receivables
    "ReceivablesInvoice": "receivables",
    "ReceivablesInvoiceLine": "receivables",
    "ReceivablesTaxLine": "receivables",
    "ReceivablesInvoiceTransactionDFF": "receivables",
    "CreditMemo": "receivables",
    "AccountCreditMemo": "receivables",
    "CustomerAccount": "receivables",
    "CustomerTransaction": "receivables",
    "StandardReceipt": "receivables",
    "AccountReceipt": "receivables",
    "AccountReceiptApplication": "receivables",
    # supplier
    "Supplier": "supplier",
    "Address": "supplier",
    "Site": "supplier",
    "Classification": "supplier",
    "Contact": "supplier",
}

_VALID_MODULES = ("payables", "procurement", "receivables", "supplier")

# --- the two anchors ------------------------------------------------------

# Edit 1: the kg_entity table definition, verbatim.
_TABLE_OLD = """CREATE TABLE kg_entity (
  entity_name           VARCHAR2(64)   NOT NULL,
  canonical_id_field    VARCHAR2(64)   NOT NULL,
  display_name_field    VARCHAR2(64),
  endpoint_path         VARCHAR2(512)  NOT NULL,
  description           VARCHAR2(2000),
  CONSTRAINT pk_kg_entity PRIMARY KEY (entity_name)
);"""

_TABLE_NEW = """CREATE TABLE kg_entity (
  entity_name           VARCHAR2(64)   NOT NULL,
  canonical_id_field    VARCHAR2(64)   NOT NULL,
  display_name_field    VARCHAR2(64),
  endpoint_path         VARCHAR2(512)  NOT NULL,
  description           VARCHAR2(2000),
  module                VARCHAR2(32)   NOT NULL,
  CONSTRAINT pk_kg_entity PRIMARY KEY (entity_name),
  CONSTRAINT chk_kg_entity_module
    CHECK (module IN ('payables', 'procurement', 'receivables', 'supplier'))
);"""


def _patch_table(text: str) -> str:
    if "module" in _TABLE_OLD:
        raise AssertionError("sanity: _TABLE_OLD should not mention module")
    count = text.count(_TABLE_OLD)
    if count != 1:
        raise AssertionError(
            f"kg_entity CREATE TABLE anchor found {count} times (expected 1). "
            "Has the schema changed, or is module already added?"
        )
    return text.replace(_TABLE_OLD, _TABLE_NEW)


def _patch_inserts(text: str) -> tuple[str, int]:
    """Append the module value to each entity's positional INSERT.

    Each INSERT looks like:

        INSERT INTO kg_entity VALUES (
          'EntityName', 'IdField', 'DisplayField',
          '/endpoint/path',
          'Description text.'
        );

    We find the block for each entity by its name on the line after VALUES (,
    then insert  ,\\n  'module'  before the closing  \\n);  of that block.
    """
    patched = 0
    for entity, module in ENTITY_MODULE.items():
        # The entity name is the first quoted token after "VALUES (".
        marker = f"INSERT INTO kg_entity VALUES (\n  '{entity}',"
        idx = text.find(marker)
        if idx == -1:
            raise AssertionError(
                f"INSERT for entity {entity!r} not found (marker mismatch)."
            )
        if text.count(marker) != 1:
            raise AssertionError(
                f"INSERT marker for {entity!r} is not unique "
                f"({text.count(marker)} occurrences)."
            )
        # Find the closing ");" that ends THIS insert: the first "\n);" after idx.
        close = text.find("\n);", idx)
        if close == -1:
            raise AssertionError(f"closing ');' not found for {entity!r}.")
        # Guard: no other INSERT starts between idx and close (blocks don't nest).
        between = text[idx + len(marker):close]
        if "INSERT INTO kg_entity" in between:
            raise AssertionError(
                f"insert block for {entity!r} appears malformed (nested INSERT)."
            )
        insertion = f",\n  '{module}'"
        text = text[:close] + insertion + text[close:]
        patched += 1
    return text, patched


def main() -> int:
    if not SCHEMA.is_file():
        print(f"ERROR: schema not found at {SCHEMA}")
        return 1

    text = SCHEMA.read_text(encoding="utf-8")

    # Refuse if already patched.
    if "chk_kg_entity_module" in text or "module                VARCHAR2" in text:
        print("Schema already has the module column — nothing to do.")
        return 1

    before_len = len(text)

    text = _patch_table(text)
    text, patched = _patch_inserts(text)

    if patched != 22:
        print(f"ERROR: patched {patched} INSERTs, expected 22.")
        return 1

    # Sanity: every module written is valid.
    for entity, module in ENTITY_MODULE.items():
        if module not in _VALID_MODULES:
            print(f"ERROR: invalid module {module!r} for {entity!r}.")
            return 1

    SCHEMA.write_text(text, encoding="utf-8")

    after_len = len(text)
    print(f"Patched {SCHEMA}")
    print(f"  kg_entity table: added module column (NOT NULL + CHECK)")
    print(f"  entity INSERTs patched: {patched}/22")
    print(f"  bytes: {before_len} -> {after_len}")
    print()
    print("Per-module counts:")
    from collections import Counter
    for mod, n in sorted(Counter(ENTITY_MODULE.values()).items()):
        print(f"  {mod:12s}: {n}")
    print()
    print("NEXT: bump print_kg.py + test_kg_metadata.py, then rebuild_kg.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
