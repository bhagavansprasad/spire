# Issue C — SQL emitter defects

**File:** `src/spire/rendering/sql_emitter.py`
**Status:** finding only. No fix in this file. No source change.
**Owner:** PR #2 window, before any Supplier work begins (STATUS.md
§Next concrete action, step 1).
**Not this file:** Issue B (MCP dependency conflict) has its own
finding at `MCP_DEPENDENCY_CONFLICT.md`. It is unrelated and is not
touched here.

## 0. What this file records

Two defects were observed in the `SQL projection:` diagnostic during
PR #1's V1 run on `fa-esll-saasfademo1`. Both are in
`sql_emitter.py`. Both are pre-existing — neither is caused by PR #1,
and neither is fixed by PR #1. Both are diagnostic-only: the SQL
projection is a POC-2 artifact per `docs/design/SQL_OVERLAY_POC.md`,
and its statements are not executed by the pipeline. The defects
therefore do not affect any answer PR #1 or PR #2 produces. They do
affect the SQL projection's credibility as a reviewable artifact, and
left unrecorded they would be re-discovered by the next window that
looks at that diagnostic — which is why STATUS.md required this file
to land before PR #2's work begins.

Both were **observed**, not inferred. Quotes below are verbatim from
`purchase_order.md` §Deviations, from V1's transcript against
`fa-esll-saasfademo1`.

## 1. Multi-field iteration sentinel handling (`_emit_step`)

### 1.1 The defect

`_emit_step` handles the `ITERATION_SENTINEL` as if every iterating
step carries exactly **one** sentinel-valued argument. The branch:

    if arg_value == ITERATION_SENTINEL:
        fspec = overlay.filters.get((step.tool_name, arg_name))
        if fspec is None:
            where.append(f"-- unmapped iteration arg: {arg_name}")
            continue
        if fspec.requires_join is not None:
            _maybe_add_join(fspec.requires_join, joins, assumptions, overlay)
        where.append(
            fspec.predicate_template.format(
                alias=entity.alias, value=":iteration_value"
            )
        )
        if fspec.assumption:
            assumptions.append(fspec.assumption)
        continue

This is correct for every single-field iterating step in the system.
It is wrong for the one multi-field step in the system:
`get_purchase_order_distributions`, whose `tool_args` carry **three**
sentinels — `po_header_id`, `po_line_id`, `line_location_id` — all
set to `"$iteration_value"`.

The loop hits the sentinel branch three times. Two consequences follow,
one per sentinel class:

**1.1.a — Unmapped iteration args.** `overlay.filters` has a key for
`(get_purchase_order_distributions, po_header_id)` and for neither of
the other two. So `po_line_id` and `line_location_id` each hit the
`fspec is None` branch and emit `-- unmapped iteration arg: <name>`
into the `WHERE` clause.

**1.1.b — One bind for three values.** The one sentinel that does
resolve, `po_header_id`, formats its `predicate_template` with
`value=":iteration_value"`. That template is:

    {alias}.PO_HEADER_ID = {value}
      AND {alias}.PO_LINE_ID = :po_line_id
      AND {alias}.LINE_LOCATION_ID = :line_location_id

The template was written for a **single-field** iteration whose
`:iteration_value` would be `PO_HEADER_ID` and whose two named binds
would be supplied by the surrounding step. Used as a **multi-field**
template, it produces one `:iteration_value` for three different bind
values that the planner has not emitted. The template is not wrong;
its use in this branch is.

### 1.2 The observed output

From `purchase_order.md` §Deviations, V1's transcript:

    AND -- unmapped iteration arg: po_line_id
    AND -- unmapped iteration arg: line_location_id;

The trailing `;` is **part of the defect**, not a transcription
artifact. The emitter appends the statement terminator to the final
line of the SQL body. In the malformed case, the final line of the
`WHERE` chain is the `-- unmapped iteration arg: line_location_id`
comment, so the terminator lands on a comment. The statement has:

- a SQL body that is not terminated (no `;` on any executable line), and
- a comment that is terminated (`;` on a `--` line, which is legal SQL
  trivia but renders the output misleading to a reader).

Both are visible in one output line. Both are within §1's fix surface.

### 1.3 The fix site

`_emit_step`, `sql_emitter.py`. Not `sql_overlay.py`. The
`_FILTERS` entry for `get_purchase_order_distributions` already names
the correct template with all three binds; the defect is that
`_emit_step` cannot distinguish single-field from multi-field
iteration, so it treats the three-sentinel case as three independent
single-sentinel cases. Confirmed by the previous window (see
`docs/plan/HANDOFF.md` §6 conversation for `d0acaf8`).

The shape the fix will take, per the same confirmation, is to mirror
the executor's existing pattern: the executor distinguishes
single-field (`iterate_over["field"]`) from multi-field
(`iterate_over["fields"]`) when it substitutes; the emitter must do the
same. That is `Step.iterate_over` gaining a `fields` shape in the plan
(which the planner already produces for this edge — see
`plan_builders._build_...` / `sql_emitter._emit_step` split) and the
emitter branching on it. Both sides of that split are visible in the
current code; the emitter's side is not yet implemented.

**No fix is made in this file.** The fix belongs in the PR that
schedules it, and per STATUS.md §Issue C, that PR is not PR #2.

## 2. Numeric-literal quoting on non-string columns (`_resolve_value`)

### 2.1 The defect

`_resolve_value` quotes every value that is not gated by a `value_map`
and not routed through a `vocab_kind`:

    def _resolve_value(fspec, raw, overlay) -> str | None:
        key = str(raw)
        if fspec.value_map is not None:
            return fspec.value_map.get(key)
        if fspec.vocab_kind is not None:
            return overlay.literals.get((fspec.vocab_kind, key))
        safe = key.replace("'", "''")
        return f"'{safe}'"

The last three lines are correct for string-valued columns. They are
wrong for numeric-valued columns: `po_header_id: "2144"` renders as
`WHERE P.PO_HEADER_ID = '2144'`, a numeric column compared to a string
literal.

On Oracle, `'2144'` and `2144` are usually the same value via implicit
conversion. The statement runs. But it is not the SQL you would
hand-write, and it hides the defect on the pods where it *does* fail —
an implicit conversion can defeat an index scan, or a plan choice, in
ways a string-literal query will not. The projection is reviewed by a
reader as if it were the query a Fusion DBA would write; that is the
artifact's whole value. A quoted numeric literal is not that query.

### 2.2 The observed output

From `purchase_order.md` §Deviations, V1's transcript (statement 1 or
3 of the run):

    WHERE P.PO_HEADER_ID = '2144'

The column is numeric (`PO_HEADER_ID`); the literal is a string.

### 2.3 The fix site

`_resolve_value`, `sql_emitter.py`. Same file as §1, different
function, different fix. Confirmed by the previous window that the two
defects should be recorded in one file (this file) rather than split
across two, because one reproducer run produces both and a split
reintroduces the drift the project keeps fighting.

### 2.4 Candidate fix shapes

`_resolve_value` has no way to know whether a predicate's bind column
is numeric or string-valued — the overlay does not currently carry that
fact. Three shapes would give it that knowledge, each with a trade-off:

**Candidate A — `FilterSpec.value_kind: str | None = None`.** The
`FilterSpec` gains a field naming the value's type (`"numeric"`,
`"string"`, `None`). Opt-in: unfilled stays current behaviour.
*Trade-off:* smallest change, sits at the same abstraction level as
the other `FilterSpec` predicate fields (`arg_name`, `predicate_template`,
`assumption`), and requires the fewest edits. Does not scale to
predicates that bind more than one value of different kinds in one
template (none today, but the multi-field fix may introduce one).

**Candidate B — typed `EntitySpec.select_columns`.** The
`EntitySpec.select_columns` becomes a list of `(alias, column, type)`
instead of `(alias, column)`. `_resolve_value` looks up the bind's
column type from the same table.
*Trade-off:* the type information becomes a property of the column,
not of the filter — which is where it belongs on principle, and scales
to multi-bind predicates. Costs a data-shape change on every `EntitySpec`
even when no filter uses a numeric column. Would also let a later
change type-check the whole emitter, not just the value resolver.

**Candidate C — template-declared bind types.** The `predicate_template`
declares the type of each bind it carries, e.g. `{value:numeric}` for
`P.PO_HEADER_ID = {value:numeric}`. `_resolve_value` parses the
template.
*Trade-off:* no new fields, no data migration. But it pushes a
type decision into a string literal, which is exactly the kind of
"type information hiding in prose" the project has been systematically
removing elsewhere (see the KG filters read moving out of the planner
into `kg_entity_filter`). It also makes the template harder to read
at a glance, and parser-string reuse of templates (the multi-field
fix will reuse the `get_purchase_order_distributions` template across
three binds) would need careful escape handling.

**Recommended:** Candidate A. It matches the abstraction the overlay
already uses (a `FilterSpec` is a per-(tool, arg) descriptor, and
`value_kind` is a per-(tool, arg) fact), it is opt-in for the columns
that already work, and it does not require a data-shape change to the
entity model on a file whose primary subject is the multi-field defect.
Candidates B and C are recorded so a future change with a wider scope
(a type-checked emitter, or a multi-bind template) can revisit this
choice with the full trade-off in view.

**No fix is made in this file.** The decision of *which* candidate to
implement is deferred to the fix PR's scheduling window; this finding
records the surface and the three candidates so the next window does
not re-derive them.

## 3. What this finding is not

- **Not Issue B.** `MCP_DEPENDENCY_CONFLICT.md` covers the
  `fastmcp 4` / `langchain-mcp-adapters 0.3.1` / `mcp 2.x` triangle.
  That file exists, is committed at `c71488d`, and is untouched here.
- **Not a PR #1 defect.** Both defects were pre-existing when PR #1's
  V1 first ran. PR #1 surfaced them by exercising the diagnostic; it
  did not cause them.
- **Not a PR #2 defect.** PR #2 (Supplier sample-and-disclose) does not
  traverse the multi-field iteration shape (Supplier has no equivalent
  to PO distributions) and does not by-id fetch a numeric column with a
  `vocab_kind`-less filter (Supplier by-id filters do not exist in the
  current surface). PR #2 will not reproduce either defect. That is why
  this file is written *before* PR #2's work begins — to record the
  finding while it is fresh, not because PR #2 needs it.

## 4. Not checked

- **Whether the `'2144'` string-literal case executes on this pod.**
  Not tested via a `SELECT`; both the diagnostic and this file are
  static reads of `sql_emitter.py`. If a future window wants to know
  whether Oracle's implicit conversion defeats an index on this
  specific pod, that is a `EXPLAIN PLAN` run against the pod, and it is
  not in scope here.
- **Whether other `_FILTERS` entries have the same "template written
  for the wrong arity" defect.** §1 names the one that was observed
  (`get_purchase_order_distributions`). A systematic audit of every
  `_FILTERS` entry against its tool's arity is not done here. If a
  future window finds a second entry in the same shape, it should be
  recorded here as §1.1.c, not opened as a new finding — same defect,
  same fix, same file.
- **Whether `-- unmapped iteration arg` should abort or warn.** The
  emitter currently emits a comment and continues. Whether a future fix
  should make this a hard error is a policy question for the fix PR,
  not for the finding.

## 5. Cross-references

- `docs/phase-3/sample_and_disclose/purchase_order.md` §Deviations —
  the V1 transcript quotes reproduced verbatim in §1.2 and §2.2.
- `docs/phase-3/sample_and_disclose/STATUS.md` §Issue C — the pointer
  that required this file.
- `docs/design/SQL_OVERLAY_POC.md` — the "SQL execution is
  deliberately out" scope note that makes both defects
  diagnostic-only rather than correctness bugs.
- `src/spire/rendering/sql_emitter.py` — the fix site for both
  sections (`_emit_step`, `_resolve_value`).
- `src/spire/kg/sql_overlay.py` — read here only to confirm it is *not*
  the fix site for §1; its `_FILTERS` entries are correct.

---

*End of finding file.*

---

## 6. Resolution — landed 2026-11-13

Both defects and both extensions recorded in §1 and §2 are fixed on
branch `Phase3-SQL-Emitter-Multifield-Fix`, merged via PR #210.
The commit is `5a853e6`. This section is the resolution record; §1–§5
above are unchanged as the finding as originally observed.

### 6.1 Defect 1 — multi-field iteration (fixed)

Fix site: `_emit_step` in `src/spire/rendering/sql_emitter.py`.
The multi-field shape is detected from `step.iterate_over` having a
`"fields"` key rather than `"field"` — the same dispatch
`executor.py::_collect_iteration_values` uses. On the multi-field
path, sibling sentinel args with no FilterSpec are skipped: the
primary arg's FilterSpec template already names every predicate, so
the siblings must not each be appended as independent
`-- unmapped iteration arg` comments.

The trailing `;` landing on the `line_location_id` comment (§1.2)
is fixed by the same change — with the comments gone, the
terminator lands on the executable `LINE_LOCATION_ID = :line_location_id`
line.

Post-fix diff, prompts 1 and 3 (identical shape):

    < WHERE D.PO_HEADER_ID = :iteration_value AND D.PO_LINE_ID = :po_line_id AND D.LINE_LOCATION_ID = :line_location_id
    <   AND -- unmapped iteration arg: po_line_id
    <   AND -- unmapped iteration arg: line_location_id;
    ---
    > WHERE D.PO_HEADER_ID = :iteration_value AND D.PO_LINE_ID = :po_line_id AND D.LINE_LOCATION_ID = :line_location_id;

Three lines become one; both halves of §1.2 fixed on the same line.

### 6.2 Defect 2 — numeric-literal quoting (fixed)

Fix site: `_resolve_value` in `src/spire/rendering/sql_emitter.py`.
**Candidate A** from §2.4: `FilterSpec.value_kind` (`"numeric"`
/ `"string"` / `None`, opt-in, `None` preserves current quoted
behaviour). Fourteen numeric-id FilterSpecs in `sql_overlay.py`
tagged `value_kind="numeric"`. `value_map` and `vocab_kind` remain
ahead of `value_kind` — those routes already emit correct output
and do not need the numeric branch.

Post-fix diff, prompt 2:

    < WHERE P.PO_HEADER_ID = '2144';
    ---
    > WHERE P.PO_HEADER_ID = 2144;

One line changed, quoted literal to unquoted. No other line in the
statement moved — the fix did not over-reach into any other binding.

### 6.3 §1.1.c — `_emit_aggregation_step`'s sibling defect (fixed)

`_emit_aggregation_step` in the same file carried the same sentinel
loop shape — a per-arg fallthrough emitting `-- unmapped iteration
arg: <name>` for an unmapped sentinel. Fixed with the same
`multi_field` guard, per this file's own §4 instruction: *"If a
future window finds a second entry in the same shape, it should be
recorded here as §1.1.c, not opened as a new finding — same defect,
same fix, same file."* No aggregation tool currently iterates, so
the branch is defensive — but leaving it live while fixing its
sibling would reintroduce the defect the moment an aggregation tool
gains an iteration.

### 6.4 §1.1.d — `search_suppliers_by_site_bu`'s missing FilterSpec (fixed)

Not recorded in §1–§5 but the same defect shape: `search_suppliers_
by_site_bu`'s `supplier_id` sentinel had no FilterSpec. Pre-patch
the step emitted `-- unmapped iteration arg: supplier_id` where
`S.VENDOR_ID = :iteration_value` belonged — the parent Supplier's
`SupplierId` (VENDOR_ID) is exactly what the sites table joins on.

FilterSpec added:

    ("search_suppliers_by_site_bu", "supplier_id"): FilterSpec(
        tool_name="search_suppliers_by_site_bu",
        arg_name="supplier_id",
        predicate_template="{alias}.VENDOR_ID = {value}",
        value_kind="numeric",
        assumption="supplier_site_by_parent_vendor_id",
    ),

This closed a pre-existing red test, `test_shape_4_suppliers_
with_site_in_bu`, whose original `":supplier_id"` assertion was
aspirational — the sentinel branch hardcodes `value=":iteration_
value"`, so `:supplier_id` cannot appear under any correct call.
The test is corrected in the same PR to assert
`S.VENDOR_ID = :iteration_value` (what the new FilterSpec emits) and
the accompanying `ASSUMPTION [supplier_site_by_parent_vendor_id]`
block.

### 6.5 Gap 3 — Invoice FilterSpecs (out of scope)

Deferred. Gap 3 is the absence of `kg_sql_filter` rows for the
Invoice-side filters `invoice_date_before`, `unpaid`, `overdue`,
and `pending`. It is a schema-and-seed change — a KG rebuild — and
per `docs/design/SQL_OVERLAY_COMPLETENESS.md` Phase 1 it belongs in
a phase-driven POC-2 window, not a defect-fix PR. The deferral is
recorded here as one line, per WORKING_STYLE §14.1, and the fix will
ride its own branch and PR when scheduled.

### 6.6 Verification

Pre-fix and post-fix transcripts captured for three reproducer
prompts (`/tmp/sql_prefix_<n>.txt` and `/tmp/sql_postfix_<n>.txt`,
not committed). The three diffs of the SQL projection blocks show
the defect shape present before and absent after:

  - Prompt 1 and Prompt 3: `-- unmapped iteration arg: po_line_id`
    and `-- unmapped iteration arg: line_location_id` gone; the
    terminator on the executable line.
  - Prompt 2: `PO_HEADER_ID = '2144'` → `PO_HEADER_ID = 2144`.

The five post-fix greps (all zero on the defect shapes; one on the
numeric form; zero on the trailing-`;`-on-comment shape) are the
load-bearing evidence. The emitted SQL was not executed against the
pod — execution is deliberately out per `SQL_OVERLAY_POC.md`.

### 6.7 Process notes

Two cell-shape failures during this window, recorded so future
windows can recognise the pattern:

  - The first commit-then-branch attempt placed `git checkout -b`
    and `git commit -F -` in one paste cell across a `MSGEOF`
    heredoc boundary. The shell ran the commit before the
    checkout, moving local `master` to `5a853e6`. Corrected with
    `git reset --hard 0ffde8f` on `master`; `origin/master` was
    never touched. WORKING_STYLE §2.1's 'one command per cell'
    rule applies across heredoc ends — a heredoc end is a command
    boundary.
  - Two earlier cell-A attempts for `sql_emitter.py` did not land,
    because the anchors were exercised but the write was suppressed
    by a script-level failure whose stderr was not visible from the
    verify cell. Cell B for every patch now includes
    `git diff --stat HEAD` for the patched file, so a non-landed
    patch shows as `0 files changed` alongside the greps that would
    also fail. That is the verification pattern for future patch
    cells.

### 6.8 Where to look next

  - `tests/test_sql_emitter.py` — the twelve tests pin the two
    defects and their fixes, plus the corrected `test_shape_4`
    (a pre-existing red test that this PR also closes).
  - `src/spire/rendering/sql_emitter.py` — `_emit_step`,
    `_emit_aggregation_step`, `_resolve_value` are the three fix
    sites; each has an inline comment naming this file and the
    defect.
  - `src/spire/kg/sql_overlay.py` — `FilterSpec.value_kind` and
    the fourteen numeric-id FilterSpecs. The
    `supplier_site_by_parent_vendor_id` assumption is at
    `_ASSUMPTIONS`.
  - `docs/design/SQL_OVERLAY_COMPLETENESS.md` Phase 1 — where the
    Gap 3 deferral is recorded as scheduled work.

*End of resolution.*
