"""F-084 — the projected supplier `Enabled` column read the `ENABLED_FLAG` stub.

F-080b fixed the *filter* for supplier status. The *projection* was still
wrong: the KG bound `Supplier.Enabled` to `POZ_SUPPLIERS.ENABLED_FLAG`,
which is `'Y'` on every supplier on this pod, so the emitted SQL reported
every supplier as enabled while REST reports Status ACTIVE/INACTIVE.

Measured on dev49 (one session, 335 suppliers by then):

    POZ_SUPPLIERS.ENABLED_FLAG       'Y' on 335/335
    REST Status                      ACTIVE 333 / INACTIVE 2
    CASE over END_DATE_ACTIVE        ACTIVE 333 / INACTIVE 2
    per-SupplierNumber comparison    335 matched, 0 mismatches

The fix seeds `kg_derived_projection ('Supplier','Status', CASE ...)` and
removes the `Supplier.Enabled -> ENABLED_FLAG` `kg_sql_column` row. There
is no `INACTIVE_DATE` column on `POZ_SUPPLIERS`, so `END_DATE_ACTIVE` is
the only carrier REST's `InactiveDate`/`Status` can come from.

Also covered here: **F-085**, the rebuild script that made this seed edit
impossible to apply. `scripts/rebuild_kg.sh` carried a stale partial seed
(8 of 12 tables, 5 of 22 entities) and its drop step failed with
ORA-02449 while still exiting 0, so an edit to `kg_sql_column` /
`kg_derived_projection` silently had no effect. It now delegates to
`rebuild_kg.py`, the script that reads the whole seed.

FIX_PLAN §6 F-084, F-085.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spire.planner.models import Step
from spire.rendering.sql_emitter import emit_sql

REPO = Path(__file__).resolve().parents[1]
SEED = REPO / "scripts" / "sql" / "kg_schema.sql"
STATUS_EXPR = "CASE WHEN P.END_DATE_ACTIVE <= TRUNC(SYSDATE) THEN 'INACTIVE' ELSE 'ACTIVE' END"


def _supplier_sql() -> str:
    step = Step(
        step_id=1,
        tool_name="search_suppliers",
        tool_args={},
        iterate_over=None,
        client_filters=(),
        output_name="out1",
        output_dedupe_by=None,
    )
    return emit_sql([step])[0]


def _strip_comments(sql: str) -> str:
    return "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )


# ── The seed ──────────────────────────────────────────────────────────


def test_seed_declares_the_status_derived_projection():
    text = SEED.read_text()
    assert "'Supplier', 'Status', 'CASE WHEN P.END_DATE_ACTIVE" in text
    assert "THEN ''INACTIVE'' ELSE ''ACTIVE'' END'" in text


def test_seed_no_longer_binds_enabled_to_the_stub():
    text = SEED.read_text()
    assert (
        "'Supplier', 'Enabled', 'POZ_SUPPLIERS', 'ENABLED_FLAG'" not in text
    ), "the stub binding is back; see F-084"


def test_seed_keeps_the_enabled_field_as_field_only():
    """Removing the carrier must not remove the field row.

    `kg_entity_field` records that the role EXISTS (field-only). Deleting
    it would change the field vocabulary and break kg_entity_field counts.
    """
    assert "'Supplier', 'Enabled', 'projection'" in SEED.read_text()


# ── The emitted SQL ───────────────────────────────────────────────────


def test_projection_carries_the_status_expression():
    body = _strip_comments(_supplier_sql())
    assert STATUS_EXPR in body


def test_projection_does_not_read_the_enabled_flag_stub():
    body = _strip_comments(_supplier_sql())
    assert "ENABLED_FLAG" not in body


def test_status_expression_is_a_single_value_not_a_boolean():
    """It must render ACTIVE/INACTIVE, matching REST's Status.

    A `1/0` form would satisfy the filter but print a number in the
    status column, which is what F-084 is about.
    """
    body = _strip_comments(_supplier_sql())
    assert "'ACTIVE'" in body and "'INACTIVE'" in body
    assert "THEN 1 ELSE 0" not in body


# ── F-085: the rebuild path ───────────────────────────────────────────


def test_rebuild_shell_script_delegates_to_the_canonical_builder():
    script = (REPO / "scripts" / "rebuild_kg.sh").read_text()
    assert "rebuild_kg.py" in script, "the wrapper stopped delegating"
    # The stale partial seed must be gone: no CREATE TABLE / INSERT inline.
    assert "CREATE TABLE" not in script
    assert "INSERT INTO kg_" not in script


def test_canonical_builder_applies_the_file_that_holds_the_fix():
    builder = (REPO / "scripts" / "rebuild_kg.py").read_text()
    assert "sql/kg_schema.sql" in builder


@pytest.mark.parametrize(
    "table",
    [
        "kg_entity_sql",
        "kg_sql_column",
        "kg_derived_projection",
        "kg_entity_filter",
    ],
)
def test_seed_creates_every_sql_satellite(table):
    """F-085: the old shell seed created only 8 of the 12 KG tables."""
    assert f"CREATE TABLE {table}" in SEED.read_text()
