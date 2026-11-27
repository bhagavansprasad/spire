#!/usr/bin/env bash
# Rebuild the KG schema and seed data.
#
# This is a THIN WRAPPER around scripts/rebuild_kg.py. It used to carry its
# own copy of the DDL and seed, and that copy went stale: it created 8 of
# the 12 KG tables (no kg_entity_sql, kg_sql_column, kg_derived_projection,
# kg_entity_filter) and seeded 5 entities / 27 fields instead of 22 / 227.
# Running it therefore did not rebuild the KG, it REDUCED it, and the
# failure was silent - the script printed "All KG tables dropped" and
# "Rebuild complete" and exited 0.
#
# Evidence (F-085, 2026-11-27): after a run of the old script the live KG
# reported kg_entity 5, kg_entity_field 27, kg_entity_sql missing, and
# every subsequent emitter test failed because no SQL carrier existed.
# The drop step had also been failing with ORA-02449 for kg_entity and
# kg_entity_field (FKs from the satellites it never dropped), so a seed
# edit could appear to apply while the old rows stayed in place.
#
# scripts/rebuild_kg.py is the canonical builder: it reads the whole of
# scripts/sql/kg_schema.sql (all 12 tables, 22 entities) and connects
# through personas.yaml, so it works against the local container exactly
# as it does against a remote host.
#
# Usage:
#   ./scripts/rebuild_kg.sh              # rebuild from the canonical seed
#   ./scripts/rebuild_kg.sh --quiet      # passed through to rebuild_kg.py
#
# The old positional container argument is accepted and ignored, so an
# existing `./scripts/rebuild_kg.sh oracle26ai_db_spire_iks` still works
# instead of aborting.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${SPIRE_PYTHON:-/home/bhagavan/virtenv/spire/bin/python}"

if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

# Drop a leading container-name argument: rebuild_kg.py connects over the
# network from personas.yaml and does not take one.
if [[ $# -gt 0 && "$1" != -* ]]; then
  echo "rebuild_kg.sh: ignoring container argument '$1' - the rebuild now" >&2
  echo "connects via personas.yaml (oracledb), not docker exec." >&2
  shift
fi

cd "$ROOT"
exec "$PY" scripts/rebuild_kg.py "$@"
