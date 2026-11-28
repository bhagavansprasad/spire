# Probe catalogue — module-independent investigation recipes

**Append-only.** Each row is a question that costs one call to settle and
applies to every module. Add a row when a probe is *verified*, not when it is
proposed — a recipe that has not been run is a hypothesis.

Purpose: module #2 should not rediscover what module #1 paid for. These are
the probes that were learned the expensive way during AP/PO discovery.

**Provenance.** The endpoint-specific findings behind each row are in
`docs/reference/spire_fusion_endpoints_reference.md` §14 (dated quirk table),
and the gate-level procedure is `MODULE_SUPPORT_PLAYBOOK.md` §3. This file is
the short list; those are the long form.

## Existence and shape

| # | Probe | Settles | Cost |
|---:|---|---|---|
| 1 | `GET /{resource}/{id}` and read `.links[]` for `child` entries | which child resources exist — no path guessing, no 404 series | 1 call |
| 2 | compare the header's fields against the child's fields for the same record | where a field *actually* lives — an absent header field is not an absent capability | 1 call |
| 3 | does the collection accept `fields=`? send a 2-field projection | whether projection is possible at all (some resources reject `fields=` outright) | 1 call |
| 4 | single-clause `q=` against a known record | whether a server-side filter works, before trusting any composite clause | 1 call |

## Counts and truncation

| # | Probe | Settles | Cost |
|---:|---|---|---|
| 5 | `totalResults=true` on the **first** page | the true collection count, separate from the page size | free with the fetch |
| 6 | read `count` **and** `hasMore` on a child collection | whether `count` is a total or just this page — the SP-005 trap | free with the fetch |
| 7 | empty result: run a control query known to return rows, same session | "no data" vs "the filter silently failed" | 2 calls |
| 8 | `COUNT(DISTINCT a, b)` on the pod when the resource exposes no PK | the identity of a child row (e.g. invoice lines have no line id) | SQL |

## Values and semantics

| # | Probe | Settles | Cost |
|---:|---|---|---|
| 9 | fetch 3–5 rows unprojected and read the field list | the real field names, before any projection is written | 1 call |
| 10 | check a computed date against its source field (due date vs terms date + terms) | whether a field is real or should be derived | 1 call |
| 11 | `COUNT(*)` and `COUNT(col)` on the physical object | whether a column is populated — existence is not evidence | SQL |
| 12 | compare `PaidStatus` gating against a paid-amount field on a partly paid record | whether a status flag can stand in for a money figure (it cannot) | 1 call |

## How to use

1. Before writing a tool, run rows 1–4. They close gate 1.
2. Before claiming a count, run rows 5–6. They close gate 7 for that prompt.
3. Before declaring a field unmodelled, run rows 2 and 9. A refusal that a
   probe would overturn is a defect, not a boundary — the SME test.
4. When a probe teaches something new, append the row and the module that
   paid for it.
