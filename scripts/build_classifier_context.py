#!/usr/bin/env python3
"""
build_classifier_context.py — Generate the module-classification menu for the
prompt-to-intent router (Phase 2).

The router's first step is a small LLM call that classifies a natural-language
prompt to its Fusion module(s) (docs/features/prompt_to_intent_framework.md,
§2.1, D2/D3/D4). That classifier needs GROUNDING: for each module, the entities
it owns and their colloquial synonyms ("vendor" -> Supplier, "bill" -> Invoice).
This script generates that grounding from the KG and writes it to a committed
`.sysprompt`-style file that the router reads and caches at import — exactly as
Phase 1 generates, commits, and reads parser-context blocks.

Grounding source (D2/D3):
- Entities and their module:   kg_entity.entity_name, kg_entity.module
- Colloquial synonyms:         kg_vocabulary WHERE vocab_kind = 'entity_synonym'
                               (term = synonym, canonical_value = entity_name)

Scoped to `entity_synonym` only — other vocab kinds (field synonyms, statuses,
countries) do not inform module choice and would only add noise.

WHY GENERATED (not hand-written): the menu stays in sync with the KG
automatically. Add an entity or a synonym in the seed, rebuild the KG, re-run
this — the classifier's grounding updates. A hand-written file would drift.

Run from the repo root, with the venv active and the Oracle container up:

    python scripts/build_classifier_context.py 2>&1 | tee t.txt

This script only CREATES the menu file. The router READS it (once, at import).
A tripwire test keeps the file in sync with the KG, as with the KG row-count
tripwires.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from spire.config import load_persona
from spire.oracle.client import OracleClient


# --- locations -------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "src" / "spire" / "nl_parser" / "context" / "routing"
OUT_PATH = OUT_DIR / "classifier_menu.sysprompt"


# --- the grounding query ---------------------------------------------------
# LEFT JOIN so an entity with zero synonyms still appears (we want to see it in
# the menu, and its absence from the join would silently drop it). Scoped to
# entity_synonym on the join's ON clause so non-synonym vocab never widens the
# result. Ordered so the generated file is byte-stable run to run.

MENU_SQL = (
    "SELECT e.module, e.entity_name, v.term "
    "FROM kg_entity e "
    "LEFT JOIN kg_vocabulary v "
    "  ON v.canonical_value = e.entity_name "
    "  AND v.vocab_kind = 'entity_synonym' "
    "ORDER BY e.module, e.entity_name, v.term"
)

# Sanity check: entity_synonym rows whose canonical_value matches no entity.
# There is no FK on canonical_value, so a typo in the seed would create a
# synonym that maps to nothing — invisible in the LEFT JOIN above (it only
# shows entities). Count them here and warn.
ORPHAN_SQL = (
    "SELECT v.term, v.canonical_value "
    "FROM kg_vocabulary v "
    "WHERE v.vocab_kind = 'entity_synonym' "
    "  AND v.canonical_value NOT IN (SELECT entity_name FROM kg_entity) "
    "ORDER BY v.canonical_value, v.term"
)

# The four modules the KG's CHECK constraint allows. Used only to render every
# module header even if (defensively) one somehow had no entities — a module
# vanishing from the menu should be loud, not silent.
KNOWN_MODULES = ["payables", "procurement", "receivables", "supplier"]


# --- file header -----------------------------------------------------------

FILE_HEADER = (
    "# Fusion module classification menu — GENERATED from the KG.\n"
    "# Source: kg_entity.module + kg_vocabulary(vocab_kind='entity_synonym').\n"
    "# Regenerate: python scripts/build_classifier_context.py\n"
    "# Do not hand-edit — changes are overwritten on regeneration.\n"
    "#\n"
    "# For each module, its entities and their colloquial synonyms. The router\n"
    "# classifies a prompt to the module(s) whose entities/synonyms it names.\n"
    "\n"
)


# --- rendering -------------------------------------------------------------

def render_menu(rows: list[tuple]) -> str:
    """Turn (module, entity_name, synonym|None) rows into the menu text.

    Rows arrive grouped and ordered by module, then entity, then synonym, with
    one row per (entity, synonym) and a single row with a NULL synonym for an
    entity that has none. Collapse them to:

        module:
          Entity (aka: syn, syn)
          EntityWithNoSynonyms
    """
    # module -> entity_name -> [synonyms]
    grouped: dict[str, dict[str, list[str]]] = {}
    for module, entity_name, synonym in rows:
        module = "" if module is None else str(module)
        entity_name = "" if entity_name is None else str(entity_name)
        entities = grouped.setdefault(module, {})
        syns = entities.setdefault(entity_name, [])
        if synonym is not None and str(synonym) != "":
            syns.append(str(synonym))

    # Emit KNOWN_MODULES first in fixed order, then any unexpected module the
    # KG produced (should be none given the CHECK, but never drop data silently).
    ordered_modules = [m for m in KNOWN_MODULES if m in grouped]
    ordered_modules += [m for m in grouped if m not in KNOWN_MODULES]

    lines: list[str] = []
    for module in ordered_modules:
        lines.append(f"{module}:")
        for entity_name in grouped[module]:  # already entity-ordered by SQL
            syns = grouped[module][entity_name]
            if syns:
                lines.append(f"  {entity_name} (aka: {', '.join(syns)})")
            else:
                lines.append(f"  {entity_name}")
        lines.append("")  # blank line between modules

    # Trailing single newline, no double blank at EOF.
    body = "\n".join(lines).rstrip("\n") + "\n"
    return FILE_HEADER + body


# --- main ------------------------------------------------------------------

async def main_async() -> int:
    persona = load_persona("default_dev")
    if persona.oracle is None:
        print("ERROR: persona has no oracle config; check personas.yaml",
              file=sys.stderr)
        return 1

    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(MENU_SQL)
        orphans = await oc.fetch_all(ORPHAN_SQL)

    # --- report what we read -------------------------------------------------
    modules_seen = sorted({r[0] for r in rows if r[0] is not None})
    entities_seen = {(r[0], r[1]) for r in rows}
    synonym_rows = [r for r in rows if r[2] is not None and str(r[2]) != ""]

    print(f"read {len(entities_seen)} entities across "
          f"{len(modules_seen)} modules: {', '.join(modules_seen)}")
    print(f"read {len(synonym_rows)} entity_synonym mappings")

    # --- orphan sanity check -------------------------------------------------
    if orphans:
        print()
        print(f"!! {len(orphans)} entity_synonym row(s) map to a "
              f"canonical_value that is NOT an entity_name:")
        for term, canonical_value in orphans:
            print(f"     term={term!r}  ->  canonical_value={canonical_value!r}")
        print("   These synonyms will never route (they name no known entity).")
        print("   Fix the seed (scripts/sql/kg_schema.sql) and rebuild the KG.")
        print("   Refusing to generate a menu with orphaned synonyms.")
        return 1

    # --- defensive: every known module must have at least one entity ---------
    missing = [m for m in KNOWN_MODULES if m not in modules_seen]
    if missing:
        print()
        print(f"!! module(s) with no entities: {', '.join(missing)}")
        print("   A module in the CHECK constraint has no entity mapped to it.")
        print("   The classifier could never route to it. Check the seed.")
        return 1

    # --- write ---------------------------------------------------------------
    menu_text = render_menu(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(menu_text, encoding="utf-8")

    print()
    print(f"wrote {OUT_PATH}")
    print(f"       {len(menu_text)} chars, {menu_text.count(chr(10))} lines")

    # --- echo the generated file so the run's tee captures it ----------------
    print()
    print("--- generated classifier_menu.sysprompt ---")
    print(menu_text, end="")
    print("--- end ---")

    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
