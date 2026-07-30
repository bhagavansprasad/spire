"""Oracle KG connection and the lazy-loaded filter definitions.

Two things live here because the second depends on the first:
_oracle_credentials / _kg_cursor / _read_clob are the raw connection
layer, and _load_filter_defs and its accessors are the one KG table read
through that connection, cached for the process lifetime. No other
planner module opens a connection — every KG-lookup function elsewhere
goes through _kg_cursor from here.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

import oracledb


# ─────────────────────────────────────────────────────────────────────
# KG connection
# ─────────────────────────────────────────────────────────────────────

# Oracle KG credentials resolve in this order, per field:
#   1. Environment variable (SPIRE_DB_USER / _PASSWORD / _DSN) — for CI
#      and ad-hoc overrides.
#   2. The persona's `oracle` block in personas.yaml — the normal source
#      and the single place to configure DB credentials.
# There is no hardcoded credential fallback: if neither source supplies a
# value, _oracle_credentials raises. (The DSN, being a non-secret local
# address, keeps a default; user and password must be configured.)

_DEFAULT_DSN = "localhost:1521/FREEPDB1"


def _oracle_credentials() -> tuple[str, str, str]:
    """Resolve (user, password, dsn) for the KG connection.

    Env vars win, then the persona's oracle block. No credential is
    hardcoded: if neither source provides a username/password, raise a
    clear error rather than silently using a baked-in default. The DSN
    falls back to the local address (not a secret) if unspecified."""
    persona_oracle = None
    try:
        from spire.config import load_persona

        persona_name = os.environ.get("SPIRE_PERSONA", "default_dev")
        persona_oracle = load_persona(persona_name).oracle
    except Exception:
        # No personas.yaml, unknown persona, or no oracle block — env
        # vars may still supply the credentials.
        persona_oracle = None

    user = os.environ.get("SPIRE_DB_USER") or (
        persona_oracle.username if persona_oracle else None
    )
    password = os.environ.get("SPIRE_DB_PASSWORD") or (
        persona_oracle.password if persona_oracle else None
    )
    dsn = os.environ.get("SPIRE_DB_DSN") or (
        persona_oracle.dsn if persona_oracle else None
    ) or _DEFAULT_DSN

    if not user or not password:
        raise RuntimeError(
            "No Oracle DB credentials. Set the oracle block in "
            "personas.yaml (username + password), or export "
            "SPIRE_DB_USER / SPIRE_DB_PASSWORD."
        )
    return user, password, dsn


@contextmanager
def _kg_cursor() -> Iterator[oracledb.Cursor]:
    """
    Yield a cursor against the KG database. Closes connection on exit.

    Every KG-lookup function opens a fresh connection; pooling can be
    added later if profiling shows it matters.
    """
    user, password, dsn = _oracle_credentials()
    connection = oracledb.connect(user=user, password=password, dsn=dsn)
    try:
        with connection.cursor() as cursor:
            yield cursor
    finally:
        connection.close()


def _read_clob(value: Any) -> str:
    """
    Coerce a possibly-CLOB column value to a Python str.

    Sync oracledb sometimes returns CLOB values as oracledb.LOB objects
    (which have a sync .read() method), and sometimes — depending on
    driver version and column size — as plain strings. Handle both.

    Returns empty string for None.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # Sync oracledb.LOB: .read() is synchronous (unlike AsyncLOB).
    return value.read()


# ─────────────────────────────────────────────────────────────────────
# Filter definitions — loaded from kg_entity_filter (lazy, cached).
#
# Replaces the hardcoded filter dicts. Read once on first use, cached
# for the process lifetime. Mirrors the lazy-read style of the other
# KG lookups in this module.
# ─────────────────────────────────────────────────────────────────────

_FILTER_DEFS_CACHE: dict[tuple[str, str], dict[str, Any]] | None = None


def _load_filter_defs() -> dict[tuple[str, str], dict[str, Any]]:
    """Read kg_entity_filter once; cache by (filter_type, entity_name)."""
    global _FILTER_DEFS_CACHE
    if _FILTER_DEFS_CACHE is not None:
        return _FILTER_DEFS_CACHE

    defs: dict[tuple[str, str], dict[str, Any]] = {}
    with _kg_cursor() as cursor:
        cursor.execute(
            "SELECT filter_type, mechanism, tool_arg_name, tool_arg_name_hi, "
            "vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, "
            "implicit_term, entity_name FROM kg_entity_filter"
        )
        for row in cursor.fetchall():
            (ftype, mechanism, tool_arg, tool_arg_hi, vocab_kind, target,
             kg_filter_type, imp_vocab, imp_term, entity) = row
            key = (ftype, entity)
            defs[key] = {
                "mechanism": mechanism,
                "tool_arg_name": tool_arg,
                "tool_arg_name_hi": tool_arg_hi,
                "vocab_kind": vocab_kind,
                "target_entity": target,
                "kg_filter_type": kg_filter_type,
                "implicit_vocab_kind": imp_vocab,
                "implicit_term": imp_term,
            }
    _FILTER_DEFS_CACHE = defs
    return defs


def _filter_def_for(ftype: str, entity: str) -> dict[str, Any]:
    """Return the filter definition for (filter_type, source_entity)."""
    defs = _load_filter_defs()
    key = (ftype, entity)
    if key not in defs:
        raise KeyError(f"No filter definition for ({ftype!r}, {entity!r})")
    return defs[key]


def _entity_level_filter_types() -> dict[str, set[str]]:
    """Filter types with a dedicated entity-level fetcher, grouped by source entity."""
    defs = _load_filter_defs()
    result: dict[str, set[str]] = {}
    for (ftype, entity), d in defs.items():
        if d["mechanism"] == "entity_level":
            result.setdefault(entity, set()).add(ftype)
    return result


def _edge_traversal_filters() -> dict[str, tuple[str, str]]:
    """Edge-traversal filters: type -> (target_entity, kg_filter_type)."""
    defs = _load_filter_defs()
    result: dict[str, tuple[str, str]] = {}
    for (ftype, entity), d in defs.items():
        if d["mechanism"] == "edge_traversal":
            result[ftype] = (d["target_entity"], d["kg_filter_type"])
    return result


def _edge_filter_implicit_values() -> dict[str, tuple[str, str]]:
    """Edge filters with an implicit value: type -> (vocab_kind, term)."""
    defs = _load_filter_defs()
    result: dict[str, tuple[str, str]] = {}
    for (ftype, entity), d in defs.items():
        if d["implicit_vocab_kind"] is not None:
            result[ftype] = (d["implicit_vocab_kind"], d["implicit_term"])
    return result

