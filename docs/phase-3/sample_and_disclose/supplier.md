# Phase 3 — Sample-and-disclose: Supplier

**Branch:** `Phase3-Supplier-Sample`
**PR:** TBD (this file is committed before the branch's PR is opened;
PR number added when the PR is raised, per `FIX_PLAN.md` §8 step 8)
**State:** in-progress
**Finding:** MEETING_2026-11-10 §6 row 2 — the second entity in the
seven-PR sample-and-disclose sequence. Supplier already samples on
`master`: `SupplierResponse` carries `narrowing_tip`, and
`build_narrowing_tip`'s default filter-label map is the Supplier one.
PR #2 is therefore mostly a proof that the extractor path works for
the shape that already has all the plumbing — not a wiring change on
the Supplier path itself.

## V0 — Fix statement

Supplier sample-and-disclose is already implemented on `master`. The
synthesizer's plain-list branch (`synthesizer.py` — the
`plain_supplier_bucket` guard) returns a `SupplierResponse` with a
bounded sample and a populated `narrowing_tip` for any filter-less
Supplier intent, with **no** parser, planner, or synthesizer change
needed. PR #2 does not introduce the Supplier path.

What PR #2 contributes:

  (a) **Coverage.** Tests that would have failed if the plain-list
      path, the two-bucket open-PO join, the F-053 four-bucket
      join, or the empty-supplier path were broken. These lock the
      behaviour PR #1 and earlier windows built, and they are the
      regression base for later Supplier work.

  (b) **One new shape.** A Supplier prompt that names **two or more
      distinct child buckets at once** — e.g. contacts *and* sites,
      or contacts *and* addresses *and* open purchase orders — is
      not covered by any local builder on `master`. Every
      `_supplier_with_*` helper in `p2p.py` handles exactly ONE
      child bucket (plus the supplier bucket); a three-bucket shape
      produces `len(outputs) != 1`, so `plain_supplier_bucket`
      returns `None`, no other local builder claims the shape, and
      the response falls to the LLM path. That is the same
      overrun risk the degenerate-output guard was written
      against, and the same class of failure PR #1's
      `get po with distribution details` surfaced on the PO side.
      PR #2 fixes this shape locally, mirroring the existing
      join-builder pattern (`_supplier_with_open_pos` and its
      siblings).

  (c) **Evidence.** The V-walk below records what the plain-list
      case does live, what the two-bucket and four-bucket cases do,
      what the new multi-child case does before and after the fix,
      and which shapes are covered by which local builder — the
      same discovery discipline `purchase_order.md` §Deviations
      recorded for PR #1.

**What PR #2 does NOT do.** It does not introduce a Supplier sibling
extractor. The PurchaseOrder guard in `planner.py`
(`if not intent.filters and not intent.list_all:`) is
PurchaseOrder-specific; there is no Supplier equivalent, so
`intent.list_all` has no Supplier reader and setting it for Supplier
would be a flag that fires and lands nowhere. The original V0
committed at `f36b11c` proposed exactly that; see `## V0 — history`
below. The correction is the finding: **the Supplier path is already
in place, and the PR is coverage plus one shape, not a wiring
change.**

**One carry-forward this V0 records.** PR #2 will not touch
`sql_emitter.py` or `sql_overlay.py`. The Issue C finding file
(`SQL_EMITTER_MULTIFIELD_ITERATION.md`, commit `fe5a41f`) is the
record; a future window fixes both defects in its own PR. If V1's
SQL projection output happens to surface them again, they are noted
here and not fixed in PR #2 — same discipline PR #1's
`purchase_order.md` §Deviations followed.

## V0 — history

The original V0, committed at `f36b11c` and superseded by the V0
above, is preserved here so the branch's own record of what it first
claimed is not lost:

> The parser will set `intent.list_all=True` for a Supplier intent
> that names no narrowing filter, via a sibling extractor
> `_is_sampleable_supplier_request` beside `_is_explicit_po_list` and
> the PR #1 sibling `_is_sampleable_po_request`; the planner's
> existing Supplier path will then permit a bounded 25-row sample,
> and the Supplier `narrowing_tip` that already exists on `master`
> will be populated so the sample discloses itself and tells the
> user how to narrow.

**Why it was wrong.** B7a's inspection on this branch showed that
`intent.list_all` has no Supplier reader: the only guard that
consults it is the PurchaseOrder block in `planner.py`. A sibling
extractor that sets `list_all` for Supplier would fire and land
nowhere. The corrected V0 reflects the code; the original is kept
here for the record.


## V1 — Reproducer (live)

Prompt: `get all suppliers` against `fa-esll-saasfademo1`. Saved
transcript at `/tmp/v1a_rerun.txt` (89 lines, `exit=0`).

**First run** (`/tmp/v1a_get_all_suppliers.txt`, 85 lines): the
answer read `Showing 25 of 402 suppliers.` with the `Truncation:`
block present — but **no `─── Tip ───` block**. The plain-list
branch was missing the `narrowing_tip=` kwarg entirely. See
`## Deviations` Fix D-a.

**Re-run after Fix D-a** (`/tmp/v1a_rerun.txt`):

    Showing 25 of 402 suppliers.
    ...
    Truncation:
      - suppliers: 402 total in source; 25 returned.

    ─── Tip ───
    Reading all 402 suppliers is slow. Narrow with a filter: business
    relationship, country, creation date, name, status.

The Rule 28 defect (SME could answer; earlier runs answered without
disclosure) is closed: 25 rows, honest `25 of 402`, and a tip naming
the entity-level filters the reader can add.

Prompt: `suppliers with their contacts and sites` against
`fa-esll-saasfademo1`. Saved transcripts at
`/tmp/v1b_multi_child.txt` (582 lines, first run) and
`/tmp/v1b_rerun.txt` (586 lines, re-run).

**First run**: three-step plan, 25 suppliers + 93 contacts + 153
sites, all built locally. But the answer's summary read
`Showing 25 of 402 suppliers. 93 contacts 153 sites.` — a full stop
where a colon belongs, no separator between child counts — and the
`─── Tip ───` block was absent. See `## Deviations` Fix D-b (the
multi-child branch I introduced at 0822047 omitted the tip) and
Fix E (the summary prose).

**Re-run after Fix D-b + Fix E** (`/tmp/v1b_rerun.txt`):

    Showing 25 of 402 suppliers: 93 contacts, 153 sites.
    ...
    Truncation:
      - suppliers: 402 total in source; 25 returned.

    ─── Tip ───
    Reading all 402 suppliers is slow. Narrow with a filter: business
    relationship, country, creation date, name, status.

Both V1 shapes answer with a local `SupplierResponse`, a bounded
25-row sample, an honest truncation disclosure, and a narrowing tip.

## V2 — Paraphrase (multi-child, three children)

Prompt: `suppliers with their contacts, sites, and classifications`
against `fa-esll-saasfademo1`. Saved transcript at
`/tmp/v2_multi_three_children.txt` (668 lines, `exit=0`).

This exercises the multi-child branch at its **maximum arity** —
three child kinds in one prompt, the fullest shape the detector
(`_supplier_multi_child`) accepts. V1b proved the two-child branch;
V2 proves the three-child form on real data with a non-empty third
child.

Intent:

    target_entity: Supplier
    include: ['Contact', 'Site', 'Classification']

Plan: four steps —

    search_suppliers
    get_supplier_contacts          (iterating: SupplierId from suppliers)
    search_suppliers_by_site_bu    (iterating: SupplierId from suppliers)
    search_suppliers_by_classification (iterating: SupplierId from suppliers)

All three child steps iterate from the supplier bucket on
`SupplierId`; all three use F-043's dual-purpose tools with only
`supplier_id`, which the tools honour as "fetch all children for this
parent." Output buckets: `suppliers`, `contact`, `site`,
`classification`.

Bucket counts on the run:

    suppliers:      25 record(s)
    contact:        93 record(s)
    site:          153 record(s)
    classification: 20 record(s)

Summary line:

    Showing 25 of 402 suppliers: 93 contacts, 153 sites, 20
    classifications.

Tip block (present):

    Reading all 402 suppliers is slow. Narrow with a filter: business
    relationship, country, creation date, name, status.

Nine per-supplier classification blocks rendered (nine of the 25
suppliers carry classifications; 20 rows across them). The third
child is non-empty, which is what makes V2 stronger than V1b — it
would have passed even if the classifier was silently empty, but
here it is not.

Green on one run. A second run on the same prompt has not been
made; `purchase_order.md` V2 was green on two runs and recorded the
second as the "reproduced twice" evidence. PR #2's V2 is green on
one run; if you want the second-run discipline, it is one more cell.

## V3 — Sibling unchanged (two-bucket supplier + contacts)

Prompt: `contacts for Lee Supplies` against `fa-esll-saasfademo1`.
Saved transcript at `/tmp/v3_contacts_two_bucket.txt` (104 lines,
`exit=0`).

This is the shape PR #2 did **not** change: a two-bucket fetch —
suppliers plus the contacts of each — whose answer is built by
`_supplier_with_contacts` on `master` (long before this branch). V3's
purpose is to prove the multi-child branch added by 0822047 does not
shadow the two-bucket branch; the detector's conservative contract
(`len(outputs) < 3` returns None, fewer than two child kinds returns
None) is supposed to protect it.

Intent:

    target_entity: Supplier
    filters: [{'type': 'name_fragment', 'value': 'Lee Supplies'}]
    include: ['Contact']

Plan: two steps —

    search_suppliers (supplier_name_contains='Lee Supplies')
    get_supplier_contacts (iterating: SupplierId from suppliers)

Bucket counts: `suppliers: 1 record(s)`, `contact: 18 record(s)`.
Two buckets, not three or four.

Summary line:

    Lee Supplies has 18 contacts.

That is `_supplier_with_contacts`'s single-supplier branch, not the
multi-child branch's `Showing N of M suppliers: X contacts, Y sites.`
form. One `Lee Supplies — contacts:` block rendered (the two-bucket
render path); zero ` — sites:` blocks; zero ` — classifications:`
blocks. If the multi-child detector had fired, all three would have
been present.

Green on one run. The multi-child branch does not over-reach onto a
two-bucket shape.

**Commit history note.** V3's content was committed at `4abbb05`
("docs(phase-3): supplier.md V3 (two-bucket contacts unchanged)"). A
second commit, `ce23c69`, was written with a message claiming "V3 +
V4" — but its diff is V4 only, because V3 was already on the branch.
The tree at `ce23c69` is correct; only the commit message is
over-stated. No history rewrite.

## V4 — Negative (get all addresses, still refuses)

Prompt: `get all addresses` against `fa-esll-saasfademo1`. Saved
transcript at `/tmp/v4_addresses_negative.txt` (16 lines, `exit=0`).

This is the shape the sample-and-disclose feature deliberately
excludes (MEETING_2026-11-10 §4.6): an Address is a child of Supplier,
so a sample of "the first 25 addresses" would be "the addresses of the
first 25 suppliers" and would misrepresent the count — 25 addresses
would stand for ~625. The correct behaviour is to refuse, and PR #2
must not accidentally make the shape sampleable.

The refusal is well-formed:

    Reason:   I can look up addresses, but this doesn't say which one.

    Solution: Name the supplier, or give me a country.

    Example:  addresses for supplier 1252
      (refusal: missing_identifier — Address queries require a
       supplier or country filter as addresses are not a top-level
       searchable resource.)

No `Answer:`, no `Plan:`, no `SQL projection:` block — the refusal
fires at the planner's Address guard, before any fetch. The
multi-child detector did not claim an address-shaped input:
address rows carry `SupplierAddressId`, not `SupplierContactId`
/ `SupplierSiteId` / `ClassificationId`, and there is no `Supplier`
bucket for the detector to anchor on.

The Address refusal is intact. PR #2 does not touch `planner.py`
and does not touch `capability.py`'s `_IDENTIFIER_GUIDANCE` entry
for `Address`.

Green on one run.

## V-walk state

TBD after V2. V3–V9 still to fill; `State: closed` after PR merge.
