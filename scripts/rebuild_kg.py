#!/usr/bin/env python3
"""
Rebuild the KG schema and seed data — over the network, via oracledb.

Unlike the old rebuild_kg.sh (which did `docker exec <container> sqlplus`
and only worked against a local container), this connects to Oracle over
the network using the same credential source as the rest of the app:

    env (SPIRE_DB_USER/_PASSWORD/_DSN) -> personas.yaml oracle block

So it works identically for a local container or a remote DB host — just
point the DSN at the right host:port/service in personas.yaml.

The SQL lives in scripts/sql/kg_schema.sql (extracted verbatim from the
original rebuild). This runner parses that file into individual
statements and executes them in order. sqlplus-only directives
(SET / PROMPT / EXIT) are ignored; they have no oracledb equivalent and
aren't needed.

Usage:
    python scripts/rebuild_kg.py
    python scripts/rebuild_kg.py --sql path/to/other.sql
    python scripts/rebuild_kg.py --quiet      # suppress per-statement echo

Requires: oracledb (already a project dependency). No sqlplus, no docker.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import oracledb

from spire.planner.planner import _oracle_credentials


DEFAULT_SQL = Path(__file__).resolve().parent / "sql" / "kg_schema.sql"

# sqlplus directives that have no oracledb meaning — skip these lines.
_SQLPLUS_DIRECTIVES = ("SET ", "PROMPT", "EXIT", "SPOOL", "WHENEVER")


def _split_statements(sql_text: str) -> list[str]:
    """Split a sqlplus-style script into executable statements.

    Rules (matching how sqlplus reads the original file):
      - A line that is exactly '/' terminates the current block (used for
        PL/SQL BEGIN...END blocks). The block is emitted WITHOUT the '/'.
      - Otherwise a ';' at end of a line terminates a plain SQL statement.
        The ';' is stripped (oracledb doesn't want it).
      - Lines that are sqlplus directives (SET/PROMPT/EXIT/...) or pure
        comments/blank are skipped between statements.
    """
    statements: list[str] = []
    buffer: list[str] = []

    def flush(strip_trailing_semicolon: bool) -> None:
        text = "\n".join(buffer).strip()
        buffer.clear()
        if not text:
            return
        if strip_trailing_semicolon and text.endswith(";"):
            text = text[:-1].rstrip()
        if text:
            statements.append(text)

    for raw in sql_text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        # A lone '/' ends a PL/SQL block.
        if stripped == "/":
            flush(strip_trailing_semicolon=False)
            continue

        # Between statements (empty buffer), skip blanks, full-line
        # comments, and sqlplus directives so they never glue onto the
        # next statement.
        if not buffer:
            if not stripped:
                continue
            if stripped.startswith("--"):
                continue
            if stripped.upper().startswith(_SQLPLUS_DIRECTIVES):
                continue

        buffer.append(line)

        # A ';'-terminated line ends a plain statement — but only if we
        # are NOT inside a PL/SQL block (those end with '/'). Heuristic:
        # if the buffer's first non-comment line starts with BEGIN or
        # DECLARE, wait for '/'. Otherwise ';' terminates.
        if stripped.endswith(";"):
            head = next(
                (b.strip().upper() for b in buffer
                 if b.strip() and not b.strip().startswith("--")),
                "",
            )
            if not head.startswith(("BEGIN", "DECLARE")):
                flush(strip_trailing_semicolon=True)

    # Anything left over.
    flush(strip_trailing_semicolon=True)
    return statements


def _is_query(statement: str) -> bool:
    """True if the statement is a SELECT (we fetch+show rows instead of
    just executing)."""
    head = next(
        (ln.strip().upper() for ln in statement.splitlines()
         if ln.strip() and not ln.strip().startswith("--")),
        "",
    )
    return head.startswith("SELECT")


def rebuild(sql_path: Path, quiet: bool = False) -> int:
    user, password, dsn = _oracle_credentials()
    print(f"Connecting to {dsn} as {user} ...")

    sql_text = sql_path.read_text()
    statements = _split_statements(sql_text)
    print(f"Loaded {len(statements)} statement(s) from {sql_path.name}.")

    connection = oracledb.connect(user=user, password=password, dsn=dsn)
    try:
        with connection.cursor() as cursor:
            for i, stmt in enumerate(statements, 1):
                preview = " ".join(stmt.split())[:70]
                try:
                    cursor.execute(stmt)
                    if _is_query(stmt):
                        rows = cursor.fetchall()
                        if not quiet:
                            print(f"[{i}] {preview}")
                            for row in rows:
                                print(f"      {row}")
                    elif not quiet:
                        print(f"[{i}] {preview}")
                except Exception as exc:
                    print(f"[{i}] FAILED: {preview}", file=sys.stderr)
                    print(f"      {exc}", file=sys.stderr)
                    raise
        connection.commit()
    finally:
        connection.close()

    print("KG rebuild complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the KG schema over the network via oracledb."
    )
    parser.add_argument(
        "--sql",
        type=Path,
        default=DEFAULT_SQL,
        help=f"Path to the schema SQL (default: {DEFAULT_SQL}).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-statement echo.",
    )
    args = parser.parse_args()

    if not args.sql.exists():
        print(f"ERROR: SQL file not found: {args.sql}", file=sys.stderr)
        return 1
    return rebuild(args.sql, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
