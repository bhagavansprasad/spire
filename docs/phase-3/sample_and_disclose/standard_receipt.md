# Phase 3 — Sample-and-disclose: StandardReceipt

**Branch:** `Phase3-StandardReceipt-Sample`
**PR:** #206 (filled when the PR is opened, per FIX_PLAN.md §8 step 8)
**State:** closed
**Finding:** MEETING_2026-11-10 §6 row 4 — the fourth entity in the
seven-PR sample-and-disclose sequence. StandardReceipt's **scoped** path
already samples on `master`: `synthesizer.py` returns a local
`StandardReceiptResponse` built by `build_standard_receipt_records`
(`ar.py`), with a local summary from `local_list_summary` and a
truncation disclosure from `_local_truncation`. PR #4 is therefore a
coverage + one-new-shape PR (the `narrowing_tip`), not a wiring change
on the StandardReceipt path.

The **unscoped** case (`get all receipts`) is a separate matter — see
"What PR #4 does NOT do" and §Deviations.

## V0 — Fix statement

StandardReceipt sample-and-disclose is **already implemented on
`master` at `6b299d0`** for the scoped single-bucket case. The
synthesizer branch

    if target_entity == "StandardReceipt" and len(outputs) == 1:
        name, rows = next(iter(outputs.items()))
        if rows and isinstance(rows[0], dict) \
                and "StandardReceiptId" in rows[0] \
                and "CustomerAccountNumber" in rows[0]:
            total_available, notes = _local_truncation(...)
            return StandardReceiptResponse(
                summary="\n".join(local_list_summary(...)),
                standard_receipts=build_standard_receipt_records(rows),
                truncation_notes=notes,
            )

returns a local, no-LLM `StandardReceiptResponse` with a bounded
sample, a local summary, and a truncation disclosure. **PR #4 does not
introduce the StandardReceipt scoped-list path.**

What PR #4 contributes:

  (a) **The narrowing tip.** `StandardReceiptResponse` (`ar.py`)
      carries `summary`, `standard_receipts`, and `truncation_notes`
      only — no `narrowing_tip` field. `PurchaseOrderResponse`,
      `SupplierResponse`, and `InvoiceResponse` all carry it. PR #4
      adds the field to `StandardReceiptResponse`, adds a
      `_STANDARD_RECEIPT_FILTER_LABELS` dict beside
      `_INVOICE_FILTER_LABELS` and `_SUPPLIER_FILTER_LABELS` in
      `p2p.py` (two entries — see (c)), and adds a
      `narrowing_tip=build_narrowing_tip(…, labels_map=_STANDARD_RECEIPT_FILTER_LABELS)`
      kwarg at the StandardReceipt return, mirroring the PO
      plain-list call-site and the Invoice plain-list call-site. The
      `build_narrowing_tip` function itself (`p2p.py`) already
      accepts `labels_map=` and de-duplicates labels (PR #1's Fix A);
      **it needs no change.**

  (b) **Coverage.** Tests that lock the scoped-list path (the
      synthesizer branch above), lock the new `narrowing_tip`
      population on a sampled result, and lock that the tip is
      **absent** on a complete fetch (mirroring PR #3's V3c guard).
      The `len(rows) < total_available` guard on the kwarg is the
      same sample-only guard PR #3 landed at `d7d78c5`; the tests
      exercise it on StandardReceipt.

  (c) **Evidence.** The V-walk below.

**The label map is two entries, not seven.** The KG's entity-level
filter set for StandardReceipt, read at `6b299d0` via
`_entity_level_filter_types()`, is:

    ['customer_name', 'customer_site']

That is the whole narrowing surface for this entity. `_STANDARD_RECEIPT_FILTER_LABELS`
maps exactly those two, and StandardReceipt has **no `by_id` filter in
the KG's entity-level set**, so the `if ft != "by_id"` exclusion every
other entity's call site uses is a no-op here — but the call site
keeps it anyway, matching the pattern, so a future KG change that adds
`by_id` does not silently widen the tip.

**What PR #4 does NOT do, and why.** The meeting §6 row 4
prescription ("Extend extractor; `sample_all=True` on
`search_standard_receipts`; field on `StandardReceiptResponse`; tip
block") describes a change master's StandardReceipt path does not need
and cannot use:

- `search_standard_receipts` (`src/spire/mcp_server/tools/standard_receipts.py`)
  has **no `sample_all`** argument.
- The tool **refuses to run unscoped**: its first statement is
  `raise ValueError("At least one of customer_name or customer_site is
  required.")`. The planner's StandardReceipt guard
  (`planner.py`, the `if intent.target_entity == "StandardReceipt":`
  block) exists precisely to pre-empt that ValueError — the planner's
  own comment records this: *"The KG advertised a fetcher the tool
  would not honour … The user saw a raw tool exception; the planner
  had every means to say so first."*
- A parser-side sibling extractor that set `list_all` for
  StandardReceipt would therefore fire and land at the planner's
  `MISSING_IDENTIFIER` refusal — the `f36b11c` defect
  `supplier.md` §V0-history records for Supplier, one entity over, but
  worse: for Supplier, `list_all` landed nowhere; for StandardReceipt,
  it would land in an explicit refusal.

**Out of scope, noted here as required.**

- The unscoped StandardReceipt case (`get all receipts`) is refused
  at `planner.py`'s `MISSING_IDENTIFIER` guard by design. The tool
  (`standard_receipts.py`) requires a `customer_name` or
  `customer_site` and raises `ValueError` without one; the guard
  pre-empts that. Relaxing the tool and the guard is a separate PR
  (tool-side scope-check relaxation plus honest-total work), not this
  one's scope. See §Deviations for the one-line pointer.
- `SQL_EMITTER_MULTIFIELD_ITERATION.md` and `MCP_DEPENDENCY_CONFLICT.md`
  — same as PR #1, PR #2, PR #3. A future window's PRs.
- `personas.yaml` — local credential edit, never staged, not part of
  any PR.

## V0 — history

The original V0 would have been the meeting §6 row 4 prescription
above, corrected on reading master. Preserved here per the
`supplier.md` §V0-history precedent so the branch's own record of
what it first claimed is not lost:

> The parser will set `intent.list_all=True` for a
> StandardReceipt intent that names no narrowing filter, via a
> sibling extractor beside `_is_explicit_po_list` and the PR #1
> sibling `_is_sampleable_po_request`; `search_standard_receipts`
> will accept `sample_all=True`; the planner's existing
> StandardReceipt path will then permit a bounded 25-row sample;
> and `StandardReceiptResponse` will gain a `narrowing_tip` field
> so the sample discloses itself.

**Why it was wrong.** Read from `master` at `6b299d0`:

- `search_standard_receipts` has no `sample_all` argument
  (`grep 'sample_all' src/spire/mcp_server/tools/standard_receipts.py`
  returns nothing).
- The tool raises `ValueError` if both `customer_name` and
  `customer_site` are absent — the scope check is a hard requirement,
  not a missing default.
- `intent.list_all` has exactly one reader in the planner: the
  PurchaseOrder guard. A parser-side sibling that set it for
  StandardReceipt would hit the StandardReceipt guard first, which
  raises `RefusalError(MISSING_IDENTIFIER)`. It would fire and land
  in a refusal, not a sample.
- `StandardReceiptResponse` does carry `summary`, `standard_receipts`,
  `truncation_notes` — the fields needed by the scoped path — and the
  scoped path already runs locally in `synthesize_response`.

**The correction is the finding.** StandardReceipt's scoped path is
already in place; PR #4 is coverage plus one shape (the tip), not a
wiring change. The unscoped case stays refused by design, recorded as
one line in §Deviations.

This is the **fourth** such correction in four PRs:
- PR #1 (PurchaseOrder): `purchase_order.md` §Deviations Fix A/B/C —
  three defects the unit tests did not catch, surfaced by the V-walk.
- PR #2 (Supplier): `supplier.md` §V0-history — the `f36b11c`
  defect; the V0 itself corrected at `7b7bb51`.
- PR #3 (Invoice): `invoice.md` §Deviations — V3c; the V0 itself
  corrected on reading `master`.
- PR #4 (StandardReceipt): this file — meeting row's Verify column
  ("`get all receipts` answers") is not satisfiable from master without
  changing the tool and the planner guard; recorded rather than
  silently patched.

The brief's prediction ("expect to repeat that correction") is no
longer a prediction; it is the observed four-for-four rate.

## V1 — Reproducer (live)

Three live prompts against `fa-esll-saasfademo1`, run after the MCP server
was restarted to pick up the tip fix at `6811fb1` and the Fix P fix at
`3d7f4b6` (WORKING_STYLE §22.1). Each ran on the dev MCP server, port 4001,
against the dev pod.

Prompt 1: `receipts for Stark Industries at Manchester` — the scoped
sampled case. Saved transcript at `/tmp/v1_standard_receipt_tip_positive.txt`
(103 lines, `exit=0`). Result: **green**.

  Intent: `StandardReceipt` with `customer_name='Stark Industries'` and
  `customer_site='Manchester'`.

  Plan: 1 step, `search_standard_receipts` with both filters.

  Outputs: `standard_receipts: 25 record(s)` of 150 total.

  Summary: `Showing 25 of 150 receipts.`

  Truncation: `standard_receipts: 150 total in source; 25 returned.`

  Tip: `Reading all 150 receipts is slow. Narrow with a filter: customer
  name, customer site.`

The tip fires on a sample of 25 of 150, names exactly the two labels from
`_STANDARD_RECEIPT_FILTER_LABELS`, and does not leak Invoice, Supplier, or
PO labels. The unit test at `6811fb1` predicted this shape; the live run
confirms it on real pod data.

Prompt 2: `receipts for ABC Application Software at Santa Clara` — the
scoped empty case, pre-Fix-P. Saved transcript at
`/tmp/v1_standard_receipt_sampled.txt` (56 lines, `exit=0`). Result:
**red**, and this is where Fix P came from.

  Intent: `StandardReceipt` with `customer_name='ABC Application Software'`
  and `customer_site='Santa Clara'`.

  Plan: 1 step, `search_standard_receipts` with both filters.

  Outputs: `standard_receipts: 0 record(s)`. The site filter ran
  client-side over the account's receipts and matched none — ABC
  Application Software's receipts have null `CustomerSite` on the
  top-level endpoint (see §V2 below; the nulls are a fact about this
  customer, not the endpoint). The site filter dropped every row.

  Answer (pre-Fix-P): `No receipts found in the examined sample. The
  search was capped before examining all matching records, so more may
  exist beyond the examined window.`

  Truncation: `standard_receipts: an unknown number of total in source;
  the fetch was capped before examining all of them, so the result is a
  sample, not the whole.`

That answer is the class Fix P corrects: the fetch was capped, but the
fetch returned zero rows, so the cap is not why the answer is empty. The
site filter dropped every row within the examined window; more rows would
also have been dropped. The summary asserts a cause the data does not
support.

Prompt 3: `receipts for ABC Application Software at Santa Clara` — the
same prompt, post-Fix-P. Saved transcript at
`/tmp/v1_standard_receipt_postfixp.txt` (56 lines, `exit=0`). Result:
**green**.

  Same Intent, same Plan, same Outputs (0 records).

  Answer (post-Fix-P): `No receipts found matching the criteria.`

  Truncation: `standard_receipts: an unknown number of total in source;
  the fetch was capped before examining all of them, so the result is a
  sample, not the whole.`

The summary no longer narrates the cap; the truncation block still
discloses it. Same prompt, same data, the delta being exactly Fix P's
change. The unit test at `3d7f4b6` (red at `055a003`) predicted this
shape; the live run confirms it.

## V2 — Paraphrase (different customer, different site)

The positive-tip prompt is V2's paraphrase relative to V3's empty prompt.
Different customer (`Stark Industries` vs `ABC Application Software`),
different site (`Manchester` vs `Santa Clara`), same shape: scoped
`StandardReceipt` with both filters. Both routes reach the same
synthesizer branch (`if target_entity == "StandardReceipt" and
len(outputs) == 1`); the branch produces a sample on one (25 of 150) and
an empty on the other (0 of 150-pending).

That the same branch produces the tip on one input and the correct "no
matches" on the other confirms the branch handles both the positive case
and the empty case without over-reaching. The tip fires where it should
and stays absent where it should.

A second V2 — a paraphrase that exercises the *same* customer with a
different site filter — was not made. V3's empty prompt and V1's positive
prompt are already the same-shape, different-input pair; a third such
prompt would not add coverage.

## V3 — Sibling (unchanged)

Three sub-cases, one per class of sibling PR #4 could have over-reached
into.

### V3a — the CustomerAccount `AccountReceipt` path (unchanged)

Prompt: `receipts for ABC Application Software` (no site filter).

This prompt **does not route to `StandardReceipt`** — the parser's
`ar.py` instruction routes it to `CustomerAccount` with a
`by_customer_name` filter and an `AccountReceipt` include, the
account-child shape. The account-child synthesizer branch has its own
disclosure mechanism (`child_totals`, rendering `(showing 10 of 2,317)`
inline on the child table) and no narrowing tip.

That is correct on master. A `StandardReceipt` tip on the
`AccountReceipt` path would mean the tip's call site leaked across entity
types, which the `_STANDARD_RECEIPT_FILTER_LABELS` scoping prevents. This
is the sibling PR #4 did **not** over-reach into.

Saved transcript: `/tmp/v1_standard_receipt_sampled_pos.txt` (101 lines,
`exit=0`). The output carries `Customer Accounts:` with the account row,
`ABC Application Software — receipts (showing 10 of 2,317)` as the child
table header, and **no** `Tip:` block. Correct on both counts.

### V3b — the empty path (green)

V1 Prompt 3 (`receipts for ABC Application Software at Santa Clara`, post-
Fix-P) is the empty path. The `_all_buckets_empty` short-circuit fires
before the tip's guard (`len(rows) < total_available` with `0 < 0`
returns false), the plain "no matching criteria" summary prints, and the
tip is absent. See V1 Prompt 3's transcript.

### V3c — the complete-fetch path (green)

A complete fetch on `StandardReceipt` — where `len(rows) ==
total_available` and no truncation occurs — is exercised by the unit test
at `6811fb1` (`test_narrowing_tip_absent_when_source_is_complete`). The
live pipeline for this shape is not exercised, because to get there a
prompt must name a customer/site with a receipt count strictly between
26 and 499 at one site, and **the fetch must not cap**. The window is
narrow: the tool's `OVERFETCH_LIMIT=500` and the tip's `total_available
is not None` guard together mean the fetch must return fewer than 500
rows total, and >25 must match at one site.

Stark Industries / Manchester (V1 Prompt 1) is near the boundary at
150 total, but 150 > 25 means it is a sample, not a complete fetch. A
complete fetch would require a customer with ≤25 total at one site, where
the tip's guard is `False` because `len(rows) == total_available`. The
pod's data does not obviously provide such a pair at a site with a
non-null `CustomerSite` on the top-level endpoint; whether one exists is
unknown without a full collection walk. This sub-case is therefore
**recorded as covered by the unit test, not exercised live**. Same class
as PR #2's V3 "multi-child branch does not over-reach onto a two-bucket
shape, green on one run": the code is correct, the live case is not
obtained.

## V4 — Negative (cross-entity, unchanged)

Prompt: `get all receipts`. Saved transcript at
`/tmp/v4_standard_receipt_unscoped.txt` (16 lines, `exit=0`).

The refusal is well-formed:

    Reason:   I can look up receipts, but this doesn't say which one.

    Solution: Name the customer, or give me a site.

    Example:  receipts for ABC Application Software
      (refusal: missing_identifier — Querying receipts requires specifying a customer name or account number.)

No `Answer:`, no `Plan:`, no `SQL projection:` block, no `Outputs:`. The
refusal fires before any fetch. PR #4 did not touch `planner.py`'s
StandardReceipt guard or `standard_receipts.py`'s scope check; the
refusal is unchanged from the pre-PR behavior recorded in the V0's
§Deviations.

## V5 — Goldens (Intent-only)

Same scope PR #1, PR #2, and PR #3 used: compare the `Intent:` block from
each golden to the current pipeline's `Intent:` block for the same
prompt. Saved transcripts at `/tmp/v5_1_count_suppliers.txt`,
`/tmp/v5_2_po_2144_lines.txt`, `/tmp/v5_3_suppliers_open_pos_retry.txt`
(PR #2's §V5-3 transient timeout re-occurred on the first attempt and
cleared on retry; the retry's Intent matched the golden).

| Golden | Golden Intent | Current Intent | Result |
|---|---|---|---|
| `count_suppliers.txt` | Supplier, `count_only: True` | same | **MATCH** |
| `po_2144_and_lines.txt` | PurchaseOrder, `by_id: 2144`, `include: ['PurchaseOrderLine']` | same | **MATCH** |
| `suppliers_with_open_pos.txt` | Supplier, `has_open_PO: True` | same | **MATCH** (retry) |

Three intents matched. The three prompts route to Supplier count,
PurchaseOrder by_id, and Supplier with has_open_PO — none route to
StandardReceipt, so PR #4's changes (all in `ar.py`, `p2p.py`,
`synthesizer.py`, none touching the parser or planner) do not reach
them. Same scope-boundary reasoning `supplier.md` §V5 and `invoice.md`
§V5 used.

**V5-3 first run: transient upstream timeout, not a shape change.** The
first `suppliers with open purchase orders` run in Cell 42's transcript
produced no `Intent:` block — the same `ERROR: execute: Upstream request
timed out` class `supplier.md` §V5-3 recorded at PR #2 and `invoice.md`
§V5 did not (its V5-3 was on a different prompt but the same shape).
Retried immediately; the retry reached execute and produced an Intent
that matched the golden. The `has_open_PO` shape does 25 sequential
`search_purchase_orders` fan-out calls to the pod; one upstream call can
exceed `FusionClient`'s 30s timeout. Pre-existing cost-profile behavior,
not a PR #4 defect.

## V6 — pytest (scoped + narrow + synth blast-radius; full deferred)

**V6-full cannot run to completion on this environment.** Same class as
PR #1's V6 and PR #2's V6: the `mcp 2.x` / `langchain-mcp-adapters 0.3.1`
conflict breaks `tests/test_agent_runner.py` collection. Deferred to the
MCP migration PR.

V6 was therefore run in two scoped forms:

| Layer | Command | Result |
|---|---|---|
| scoped | `pytest -q tests/test_sample_and_disclose_standard_receipt.py` | **6 passed in 0.22s** |
| synth blast-radius | four files: `test_synthesizer`, `test_synthesizer_supplier_records`, `test_synthesizer_truncation_narration`, `test_synthesizer_aggregation` | **97 passed, 1 deselected in 0.24s** |

Saved logs: `/tmp/t_pr4_vwalk_green.log`, `/tmp/t_pr4_synth_siblings.log`.

The 97/1 count matches PR #2's V6 blast radius exactly, confirming PR #4's
changes did not perturb the synthesizer surface those four files cover. The
6-passed file includes the tip test at `6811fb1` and the Fix P test at
`055a003` (red) → `3d7f4b6` (green).

What is **not** established: whether some test in the full suite regresses
for reasons PR #4 caused indirectly. Same gap PR #1, PR #2, and PR #3
recorded; the same `MCP_DEPENDENCY_CONFLICT.md` blocks its resolution.

## V7 — Test fails without the fix

Two red-base commits on the branch, each committed **before** its
corresponding source fix, per FIX_PLAN.md §8 step 3. Neither was a post-hoc
stash; both were verified red at commit time.

### V7-a — the tip tests (commit `29e8050`)

`tests/test_sample_and_disclose_standard_receipt.py` was committed at
`29e8050` with 5 tests, 4 of them red. The four red tests:

    test_plain_receipt_list_carries_narrowing_tip
    test_narrowing_tip_absent_when_source_is_complete
    test_empty_result_does_not_carry_narrowing_tip
    test_tip_labels_do_not_leak_from_invoice

All four failed at the same line — `AttributeError:
'StandardReceiptResponse' object has no attribute 'narrowing_tip'`.
That is the missing-field signature, not a wrong-path failure. The test
that passed (`test_plain_receipt_list_builds_locally_no_llm`) was green
because the scoped path is **already local** on master; it locks that
fact against future regression.

Saved log: `/tmp/t_pr4_red.log` (4 FAILED, 1 passed, exit 1).

Fix at `6811fb1` adds the `narrowing_tip` field to
`StandardReceiptResponse`, the `_STANDARD_RECEIPT_FILTER_LABELS` dict, and
the kwarg at the StandardReceipt return. The six tests pass after
(`/tmp/t_pr4_vwalk_green.log`: `6 passed`).

### V7-b — the Fix P test (commit `055a003`)

The V-walk surfaced a second defect (V1 Prompt 2's pre-Fix-P transcript):
the `_all_buckets_empty` truncated sub-branch narrated the cap as the
cause of an empty result. The test at `055a003`:

    test_empty_result_with_capped_fetch_does_not_claim_the_cap_is_the_cause

Failed on the pre-Fix-P code: the summary contained `capped`, the test
asserted `"capped" not in summary`.

Saved log: `/tmp/t_pr4_vwalk_red.log` (1 FAILED, 5 passed, exit 1).

Fix at `3d7f4b6` replaces the two-string `if`/`else` construction with a
single plain `No {label} found matching the criteria.` return while
keeping the `notes` construction. The truncation block still discloses
the cap. The test passes after (`/tmp/t_pr4_vwalk_green.log`: `6 passed`).

### Why two red bases, not one

V7-a covers the tip's positive and negative cases, the field's existence,
and the label-map scoping. V7-b covers the empty-truncated narrative, a
defect the tip tests did not exercise. Same discipline as PR #2's two
red bases (`f4f9a13` for the multi-child test, `257bf56` for the tip
tests): the V-walk surfaces a defect class the earlier red base did not
cover, and the new defect gets its own red.

## V8 — N-run reproducibility (deferred)

Deferred alongside V6. The positive-tip prompt ran once
(`/tmp/v1_standard_receipt_tip_positive.txt`, 25 of 150, tip present). A
20-run sweep would test whether the tip fires deterministically on the
same prompt; the branch's only variability on this prompt is the pod's
own receipt count (Stark Industries at Manchester is 150 today, may drift)
and the parser's include/add decisions (deterministic per `ar.py`'s
`_IDENTIFIER_GUIDANCE` and the router's `_correct_modules_for_ar_child`).
A single green run does not rule out a rare parser misfire or pod timeout
on the site filter's client-side pass.

A second obstacle specific to this entity: the tip's guard requires a
customer in a narrow total-count window (26–499, with >25 matching at one
site), and the pod's data does not guarantee such a window survives pod
changes. An N≥20 sweep on `Stark Industries at Manchester` would work
today but the assertion would be `"tip present"` at a specific count;
that is more brittle than the assertion the other V8s ran. Deferring V8
records that the tip is verified green once, not that it is verified
deterministic across twenty runs.

## V9 — --validate (not required)

No `.sysprompt` block was changed in this PR. The tip call-site and the
label map are pure-Python; the Fix P change is a Python conditional. Per
PR #1's precedent (`_is_explicit_po_list` is code-only and had no V9
requirement), PR #2's, and PR #3's.

## V-walk state

| V | Status | Note |
|---|---|---|
| V0 | done | opened with the meeting row's prescription; corrected on reading `master` at `6b299d0` to reflect the already-implemented scoped path (`ce75b39`) |
| V1 | **green** | scoped sampled (`Stark Industries at Manchester`, 25 of 150, tip present) + scoped empty pre- and post-Fix-P |
| V2 | **green** | same branch, different customer/site — Stark vs ABC, Manchester vs Santa Clara |
| V3 | **green** (V3a and V3b live; V3c by unit test) | V3a CustomerAccount path unchanged; V3b empty path post-Fix-P; V3c complete-fetch covered by unit test, not exercised live (window is narrow) |
| V4 | **green** | `get all receipts` — `missing_identifier` refusal, unchanged |
| V5 | **green** | three golden Intents matched (`count_suppliers`, `po_2144_and_lines`, `suppliers_with_open_pos`); V5-3 green on retry after a transient upstream timeout |
| V6 | scoped + synth **green**; full **deferred** | branch tests 6/6, synth blast-radius 97/97; full-suite blocked by MCP conflict as at PR #1–3 |
| V7 | **green** | two red bases (`29e8050` for the tip tests, `055a003` for the Fix P test), both committed red before their fixes |
| V8 | **deferred** | one green run on the positive prompt; N≥20 sweep deferred, same class as PR #1–3 |
| V9 | not required | no `.sysprompt` change on the branch |

## Deviations

### Unscoped StandardReceipt is refused by design

`get all receipts` is refused at `planner.py`'s `MISSING_IDENTIFIER`
guard (`if intent.target_entity == "StandardReceipt": has_scope = …;
if not has_scope: raise RefusalError(...)`). The tool
`search_standard_receipts` requires one of `customer_name` or
`customer_site` and raises `ValueError` without one; the guard
pre-empts that ValueError with a structured refusal. Relaxing the
tool and the planner guard together — and adding honest total-count
handling for an unscoped fetch (the tool's `OVERFETCH_LIMIT=500`
caps the observable count, so `total_available` for an unscoped fetch
is a lower bound) — is a separate PR with its own V0, not PR #4's
scope. The meeting §6 row-4 Verify column ("`get all receipts`
answers with 25 rows + tip") is therefore not satisfied by this PR,
and this note records that rather than patching it.

### Fix P — the empty-truncated summary narrated the cap as the cause

V-walk-surfaced, at V1 Prompt 2. The `_all_buckets_empty` truncated
sub-branch constructed its summary from the truncation entry's
`truncated=True` and narrated a cap as the cause of an empty result.
Over 0 rows, that asserts a cause the data does not support — zero
rows matched within the cap, so more in the source would also not
match.

Fixed at `3d7f4b6` (red base `055a003`). The fix replaces the two-string
`if`/`total_available is None` construction with a single plain
`No {label} found matching the criteria.` return, while keeping the
`truncation_notes` construction so the cap is still disclosed. The
summary no longer names the cap; the truncation block does.

Unit test at `055a003`, live confirmation at V1 Prompt 3
(`/tmp/v1_standard_receipt_postfixp.txt`). Same class as PR #1's Fix A/B/C,
PR #2's Fix D-a/D-b/E, and PR #3's V3c: a defect the unit tests did not
catch, found by a real prompt against the pod, fixed as its own commit
pair.

### `personas.yaml` in the working tree

Local credential edit, never staged, not part of any PR.

### Design decision: sysprompt stays untouched on this PR

Same as PR #1, PR #2, PR #3: pure-Python fix, no `.sysprompt` change,
so no V9 sweep required. `_STANDARD_RECEIPT_FILTER_LABELS` is Python
data.

## Not checked

- **V6-full** and **V8** — both deferred to the MCP migration PR, same
  as PR #1, PR #2, and PR #3.
- **V3c complete-fetch, live** — the tip's guard's complete-fetch
  branch (len(rows) == total_available) is covered by the unit test at
  `6811fb1` but not exercised on the live pod: the window for a
  complete fetch on a site-filtered StandardReceipt prompt
  (`26–499` total receipts, ≤25 at the requested site, and the fetch
  does not hit `OVERFETCH_LIMIT=500`) is narrow, and no customer/site
  pair providing it was found in the first 15,000 rows of the pod's
  top-level collection. Whether one exists elsewhere is unknown.
- **The pod's `CustomerSite` nullability across the collection** —
  Cell 33's probe showed ABC Application Software's receipts carry
  null `CustomerSite` on the top-level endpoint; Cell 34's probe
  showed the collection at large populates `CustomerSite` on 100% of
  the first 500 rows. The two are compatible (a per-customer data
  fact), but whether any *other* customer has the same null-site
  pattern is not established. Not a PR #4 concern; recorded as a pod
  data fact for a future window.
- **The other entity's tip call-sites** — PR #4 did not touch them.
  `suppliers`, `purchase_orders`, `invoices` all still carry their tips
  as landed at `6811fb1`'s predecessors.
- **`SQL_EMITTER_MULTIFIELD_ITERATION.md` and `MCP_DEPENDENCY_CONFLICT.md`**
  — out of scope, as recorded in §V0.

## S11 — Coverage expansion

The V-walk's coverage-contributing shapes:

- **Positive-tip sample** — `receipts for Stark Industries at
  Manchester` (25 of 150). This is the tip's positive case. The
  prompt shape (site-filtered StandardReceipt) is the only shape that
  reaches the tip; the account-only shape routes to `CustomerAccount`
  and does not.
- **Empty-truncated** — `receipts for ABC Application Software at
  Santa Clara` (0 of unknown). Fix P's positive case; the summary
  says "no matching criteria" and the truncation block discloses the
  cap.
- **Empty-unscoped** — `get all receipts`. The refusal, unchanged.
- **Complete fetch** — not exercised live (narrow window); covered
  by the unit test at `6811fb1`.

Sibling prompts (existing or to-be-written) for the same shape:

- `prompts/receivables/receivables_exhaust.txt` — receipts under
  `payables_supplier` / `receivables` and the site-filtered forms.
- A future N≥20 prompt set for StandardReceipt receipt queries, once a
  customer/site window is characterized (see §Not checked).
- The parser splits the two receipt shapes (StandardReceipt for
  site-filtered, CustomerAccount+AccountReceipt for account-only), and
  a prompt set should exercise both — the tip's positive case is the
  former, and it is the one an SME is likely to phrase first ("receipts
  for X at Y").

**State:** closed. PR number filled at close, per `FIX_PLAN.md` §8 step 9.
