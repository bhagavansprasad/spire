#!/usr/bin/env python3
"""validate_kg_schema.py — §3.4 build self-check (on-demand release/CI).

Two checks. Both read the KG (Oracle FREEPDB1 via oracledb); the
pod-dependent parts also query the Fusion pod (via ``./runsql.sh``).

1. Derived-projection column validation (Phase 2 Q6).
   Walk every ``kg_derived_projection`` expression, resolve each table
   alias to a physical table (entity ``fusion_table`` + ``base_joins`` +
   the expression's own ``FROM`` clauses), and classify every referenced
   ``(physical_table, column_name)``:
     - present in ``kg_sql_column``  -> validated carrier (OK)
     - absent there but on the pod     -> join key / non-projected (OK)
     - absent from both                -> MISSING column (FAIL)

   This is the column-level guard against the F-070-class bug (a derived
   expression naming a column the pod does not carry, e.g. ``TRX_ID``):
   every physical column a derived role reads must be a real pod column,
   and anything that is a *measure* (not a join key) must additionally be
   a ``kg_sql_column`` carrier. See ``docs/plan/PENDING_KG_SCHEMA_CORPUS.md`` §4.

2. Nullable join-key NULL-count checks (Phase 2 Q4).
   For each known nullable join key, count NULLs on the joining-side
   table and require zero — with the one documented exception that
   ``PO_HEADERS_ALL.VENDOR_ID`` may be NULL only on
   ``DOCUMENT_STATUS = 'INCOMPLETE'`` rows. Non-zero fails the build
   (an inner join through a nullable key silently drops rows).

Exit code 0 = every check that could run passed; 1 = a check failed, or
a required data source was unavailable while a check depended on it.

Usage:
    /home/bhagavan/virtenv/spire/bin/python scripts/validate_kg_schema.py
    /home/bhagavan/virtenv/spire/bin/python scripts/validate_kg_schema.py --kg-only
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from spire.kg.sql_overlay import OVERLAY
from spire.planner.kg_db import _kg_cursor

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNSQL = REPO_ROOT / "runsql.sh"

_JOIN_ALIAS_RE = re.compile(
    r"(?:LEFT\s+|RIGHT\s+|FULL\s+|INNER\s+)?JOIN\s+"
    r"([A-Za-z0-9_$#]+)\s+([A-Za-z0-9_$#]+)\s+ON",
    re.IGNORECASE,
)
_FROM_ALIAS_RE = re.compile(
    r"\bFROM\s+([A-Za-z0-9_$#]+)\s+([A-Za-z0-9_$#]+)",
    re.IGNORECASE,
)
_COLUMN_REF_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9_$#]*)\s*\.\s*([A-Za-z][A-Za-z0-9_$#]*)"
)

# The known nullable join keys (§4 of PENDING_KG_SCHEMA_CORPUS.md, extended
# from 3 to 6 by the Receivables role maps). ``exclude`` is an extra AND
# predicate that carves out rows allowed to be NULL (only PurchaseOrder's
# VENDOR_ID has one). Two entries — ReceivablesInvoice and CreditMemo —
# share one physical column (RA_CUSTOMER_TRX_ALL.BILL_TO_CUSTOMER_ID).
NULLABLE_KEYS: list[dict] = [
    {
        "entity": "Contact",
        "table": "POZ_SUPPLIER_SITES_ALL_M",
        "column": "PARTY_SITE_ID",
        "exclude": "",
        "note": "count NULLs = 0",
    },
    {
        "entity": "PurchaseOrder",
        "table": "PO_HEADERS_ALL",
        "column": "VENDOR_ID",
        "exclude": "NVL(DOCUMENT_STATUS, 'x') <> 'INCOMPLETE'",
        "note": "count NULLs = 0 except DOCUMENT_STATUS='INCOMPLETE'",
    },
    {
        "entity": "Invoice",
        "table": "AP_INVOICES_ALL",
        "column": "VENDOR_ID",
        "exclude": "",
        "note": "count NULLs = 0",
    },
    {
        "entity": "ReceivablesInvoice",
        "table": "RA_CUSTOMER_TRX_ALL",
        "column": "BILL_TO_CUSTOMER_ID",
        "exclude": "",
        "note": "count NULLs = 0",
    },
    {
        "entity": "CreditMemo",
        "table": "RA_CUSTOMER_TRX_ALL",
        "column": "BILL_TO_CUSTOMER_ID",
        "exclude": "",
        "note": "count NULLs = 0 (shares physical column with ReceivablesInvoice)",
    },
    {
        "entity": "StandardReceipt",
        "table": "AR_CASH_RECEIPTS_ALL",
        "column": "PAY_FROM_CUSTOMER",
        "exclude": "",
        # OPEN (F-074): the pod has 39 NULL rows (UNID 25 / REV 10 / NSF 2 /
        # APP 2), so this check fails until the drop-vs-LEFT-JOIN decision
        # lands. Deliberately NOT weakened — see docs/fixes/FIX_PLAN.md F-074.
        "note": "count NULLs = 0 (open: F-074, pod has 39 NULLs)",
    },
]


# ---------------------------------------------------------------------------
# Pod access (via ./runsql.sh, the canonical Fusion SQL validator)
# ---------------------------------------------------------------------------

def _run_pod_sql(sql: str) -> str:
    """Run ``sql`` against the Fusion pod and return CSV stdout."""
    if not RUNSQL.exists():
        raise RuntimeError(f"runsql.sh not found at {RUNSQL}")
    env = dict(os.environ)
    env["FORMAT"] = "csv"
    proc = subprocess.run(
        [str(RUNSQL), sql],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"runsql.sh exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


def _pod_columns(table: str) -> set[str]:
    """Return the set of column names on the pod for ``table`` (uppercased)."""
    sql = (
        "SELECT COLUMN_NAME FROM ALL_TAB_COLUMNS "
        f"WHERE OWNER='FUSION' AND TABLE_NAME='{table}'"
    )
    out = _run_pod_sql(sql)
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return {ln.upper() for ln in lines[1:]}  # skip the CSV header


def _pod_null_count(table: str, column: str, exclude: str) -> int:
    """Count rows where ``column`` IS NULL, minus the ``exclude`` carve-out."""
    where = f"{column} IS NULL"
    if exclude:
        where += f" AND {exclude}"
    sql = f"SELECT COUNT(*) AS NULL_CNT FROM {table} WHERE {where}"
    out = _run_pod_sql(sql)
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise RuntimeError(f"unexpected runsql.sh output for {sql!r}: {out!r}")
    return int(lines[-1])


# ---------------------------------------------------------------------------
# KG access (via the process-lifetime oracle pool)
# ---------------------------------------------------------------------------

def _read_kg() -> tuple[dict, set[tuple[str, str]], list[tuple[str, str, str]]]:
    """Return (entity_sql, kg_columns, derived).

    - entity_sql: {entity_name: {"fusion_table", "pk_column"}}
    - kg_columns: {(physical_table, column_name)} across every kg_sql_column row
    - derived:    [(entity_name, field_name, expression)]
    """
    with _kg_cursor() as cur:
        cur.execute(
            "SELECT entity_name, fusion_table, pk_column FROM kg_entity_sql"
        )
        entity_sql = {
            row[0]: {"fusion_table": row[1], "pk_column": row[2]}
            for row in cur.fetchall()
        }
        cur.execute(
            "SELECT DISTINCT physical_table, column_name FROM kg_sql_column"
        )
        kg_columns = {
            (table.upper(), column.upper()) for table, column in cur.fetchall()
        }
        cur.execute(
            "SELECT entity_name, field_name, expression "
            "FROM kg_derived_projection ORDER BY entity_name, field_name"
        )
        derived = [(e, f, expr) for e, f, expr in cur.fetchall()]
    return entity_sql, kg_columns, derived


# ---------------------------------------------------------------------------
# Alias resolution
# ---------------------------------------------------------------------------

def _alias_map(entity_name: str, entity_sql: dict, expression: str) -> dict[str, str]:
    """Map table alias -> physical table for one derived expression.

    Outer scope: the entity's own alias (from ``OVERLAY``) bound to its
    KG ``fusion_table``, plus its ``base_joins``. Subquery scope: aliases
    introduced by the expression's own ``FROM`` clauses, which are added
    last so they shadow the outer scope.
    """
    alias_map: dict[str, str] = {}
    fusion_table = entity_sql[entity_name]["fusion_table"]
    entity = OVERLAY.entities.get(entity_name)
    if entity is not None:
        alias_map[entity.alias.upper()] = (fusion_table or "").upper()
        joined = "\n".join(entity.base_joins)
        for table, alias in _JOIN_ALIAS_RE.findall(joined):
            alias_map[alias.upper()] = table.upper()
    for table, alias in _FROM_ALIAS_RE.findall(expression):
        alias_map[alias.upper()] = table.upper()
    return alias_map


def _extract_refs(expression: str) -> list[tuple[str, str]]:
    """Return every ``alias.column`` reference, uppercased, in order."""
    return [
        (alias.upper(), column.upper())
        for alias, column in _COLUMN_REF_RE.findall(expression)
    ]


# ---------------------------------------------------------------------------
# Check 1 — derived-projection column validation (Q6)
# ---------------------------------------------------------------------------

def _check_derived(
    entity_sql: dict, kg_columns: set, derived: list, check_pod: bool
) -> tuple[list[str], bool]:
    """Validate every derived projection. Returns (report_lines, ok)."""
    lines: list[str] = []
    ok = True

    for entity_name, field_name, expression in derived:
        label = f"{entity_name}.{field_name}"
        alias_map = _alias_map(entity_name, entity_sql, expression)
        refs = _extract_refs(expression)

        # Resolve each alias.column -> (physical_table, column_name).
        resolved: list[tuple[str, str]] = []
        unresolved: list[tuple[str, str]] = []
        for alias, column in refs:
            table = alias_map.get(alias)
            if table:
                resolved.append((table, column))
            else:
                unresolved.append((alias, column))

        lines.append(f"{label}\n    {expression}")

        # Columns not in kg_sql_column need a pod existence check.
        to_verify = [
            (table, column)
            for table, column in resolved
            if (table, column) not in kg_columns
        ]
        pod_cols: dict[str, set[str]] = {}
        if to_verify and check_pod:
            for table in sorted({t for t, _ in to_verify}):
                pod_cols[table] = _pod_columns(table)

        for alias, column in unresolved:
            lines.append(f"    !! UNRESOLVED alias: {alias}.{column}")
            ok = False

        for table, column in sorted(set(resolved)):
            if (table, column) in kg_columns:
                lines.append(f"    ok  carrier        {table}.{column}")
            elif check_pod:
                if column in pod_cols.get(table, set()):
                    lines.append(
                        f"    ok  join-key/pod   {table}.{column}"
                    )
                else:
                    lines.append(f"    !! MISSING column  {table}.{column}")
                    ok = False
            else:
                lines.append(
                    f"    ??  not-in-kg      {table}.{column} "
                    f"(pod check skipped with --kg-only)"
                )

        if not resolved and not unresolved:
            lines.append("    (no column references found)")

    return lines, ok


# ---------------------------------------------------------------------------
# Check 2 — nullable join-key NULL-count checks (Q4)
# ---------------------------------------------------------------------------

def _check_nullable_keys(check_pod: bool) -> tuple[list[str], bool]:
    """Run the NULL-count checks. Returns (report_lines, ok)."""
    lines: list[str] = []
    if not check_pod:
        lines.append("(skipped with --kg-only)")
        return lines, True

    # Dedupe the physical query; ReceivablesInvoice + CreditMemo share one.
    results: dict[tuple[str, str, str], int] = {}
    for key in NULLABLE_KEYS:
        k = (key["table"], key["column"], key["exclude"])
        if k not in results:
            results[k] = _pod_null_count(*k)

    ok = True
    for key in NULLABLE_KEYS:
        count = results[(key["table"], key["column"], key["exclude"])]
        label = f"{key['entity']} {key['table']}.{key['column']}"
        if count == 0:
            lines.append(f"[PASS] {label}: NULLs = 0 ({key['note']})")
        else:
            lines.append(
                f"[FAIL] {label}: NULLs = {count} (expected 0; {key['note']})"
            )
            ok = False
    return lines, ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="§3.4 KG-schema self-check (derived-projection columns "
        "and nullable join-key NULL counts)."
    )
    parser.add_argument(
        "--kg-only",
        action="store_true",
        help="Skip all pod checks (nullable keys and pod column-existence); "
        "report only the KG-internal carrier classification.",
    )
    args = parser.parse_args()

    entity_sql, kg_columns, derived = _read_kg()
    check_pod = not args.kg_only

    print("=== Derived-projection column validation (Phase 2 Q6) ===")
    if not derived:
        print("(no kg_derived_projection rows)")
    derived_lines, derived_ok = _check_derived(
        entity_sql, kg_columns, derived, check_pod
    )
    for line in derived_lines:
        print(line)

    print()
    print("=== Nullable join-key NULL-count checks (Phase 2 Q4) ===")
    nullable_lines, nullable_ok = _check_nullable_keys(check_pod)
    for line in nullable_lines:
        print(line)

    print()
    ok = derived_ok and nullable_ok
    if ok:
        print("Result: PASS")
        return 0
    print("Result: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
