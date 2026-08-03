# Spire — Session Handoff (2026-08-03)

Supersedes the 2026-07-30 handoff.

---

## Who / what

Continuing **Spire** — AI-native NL query over Oracle Fusion Cloud (P2P +
AR). Deterministic KG pipeline: parse → plan → execute → synthesize.
Tool selection is a KG lookup, not an LLM judgement. Not an agent
architecture.

Repo `github.com/bhagavansprasad/spire`, working dir `~/pocs/spire`, pod
`fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`, creds in
`personas.yaml`.

**On `master`, clean, 799 tests passing.** Eight branches merged across
two sessions.

**The two-LLM-boundary description now needs a caveat.** The synthesize
boundary is gone on most read paths — supplier lists, credit memos, AR
invoices, customer accounts and standard receipts all build their
answers in code. The parse boundary is untouched.

---

## What these sessions did

Three threads, in order.

### 1. Refusals (merged)

A sixth `RefusalFlavor`, `UNSUPPORTED_FIELD`, plus `_FIELD_GUIDANCE` in
`capability.py`. Column problems had no flavor, so the model chose
`unsupported_filter` — the correct choice from a bad menu.

**Largely superseded the same week**, see "The output contract" below.

### 2. The output contract (specified, partly built)

Agreed with the SME on 2026-08-02, in `spire_enhancement_requirements.md`
§4B as OUT-01 to OUT-05:

- **Two outcomes, not three.** "Refused" stops being a user-facing
  category. Zero rows is an ANSWER and gets said plainly. A query that
  CAN run, runs.
- **Answer format** — counts line, short statements, and the summary may
  cite only fields the reader can see.
- **Inability message** — labelled first line, Fusion business
  vocabulary, no "entity"/"table"/"filter".
- **OUT-04 local synthesis** — anything derivable from the data is
  computed; the model never produces a number.
- **OUT-05 one record renderer** — table for many, field-per-line for
  one, indented tables for children.

OUT-04 and OUT-05 are built. **OUT-01 to OUT-03 are only partly
delivered** by them — the two-outcome model itself has not been
implemented.

### 3. Local synthesis (merged, six shapes)

The largest piece. Records and prose both built in code on:

| Entity | LLM call |
|---|---|
| Supplier lists | **none** |
| Credit memos | **none** |
| AR invoices + lines + tax + DFF | **none** |
| Customer accounts + 4 child types | **none** |
| Standard receipts | **none** |
| Aggregations | records local, prose still model |

Fourteen of sixteen `03_ar.txt` prompts run with no synthesize call.
Invoice 1002 went from 15,244 tokens to 9,073 with byte-identical
output.

Also merged: records render as tables everywhere (was bullets on eight
branches), quantities right-align, children indent under their parent.

---

## Numbers to carry forward

| Metric | Value |
|---|---|
| Tests passing | **799** (18 deselected, 1 xfailed) |
| `03_ar.txt` | 16/16 run; 14 with no synthesize call |
| `01_supplier.txt` | 40/40 run |
| `10_refusal_examples.txt` | **19/19** must answer (was 18) |
| Invoice 1002 tokens | 15,244 → **9,073** |

**A green suite proves nothing about the local paths.** Three separate
LLM-call removals left it at 771 → 771, 779 → 779, 789 → 789. Nothing
mocked those calls. Twenty tests were added afterwards; the untested
paths are the ones to worry about.

---

## Where the plan stands

- **Phase 0, 1** — done, merged.
- **Phase 2** — UX-01 done. UX-02, UX-03 not started.
- **Phase 2A** — OUT-04, OUT-05 merged. OUT-01 to OUT-03 partial.
  **COL-01, COL-02, COL-03 and CSV-01 NOT STARTED.**
- **Phases 3–12** — not started.

**Read `docs/spire_enhancement_status.md` §G12.7 before choosing what to
do next.** Two full days went into output quality, which began as an
observation about paragraph summaries. The column work — what the SME
actually raised, marked P0 since 2026-07-31 — has not been started.

---

## Next: choose deliberately

**Option A — COL-03, partial column resolution.** The SME's original
request. A prompt naming several columns where some do not exist should
return the ones that do and name the rest. Currently it either refuses
the whole query (5 of 6 measured cases) or drops the term silently (1).
Spec is written, nothing built.

**Option B — finish local synthesis.** P2P invoice and PO lists, plus
ranking prose. `single_parent_shape` is entity-agnostic and carries
straight over. Extends a proven pattern; no open questions.

**Option C — the two-outcome model (OUT-01).** The deepest of the
output-contract items and the one that changes behaviour rather than
wording.

A is the one that was asked for. B is the one that is warm.

---

## Carried forward — still open

**Can put a wrong number in front of someone**

- **Aggregates over a 25-row sample, stated as fact.** Now known to be
  worse than believed: `/invoices` returns DIFFERENT rows on each run
  (see §15 of the endpoints reference), so the same question answered
  twice gives two answers, with no error either time.
- **"Country" returns a full address.**
- **Only the FIRST address is shown** for suppliers with many — now at
  least marked `(+N more)`.
- **`StandardReceipt` and `AccountReceipt` model the same receipts** with
  disagreeing counts, and both are routable.
- **An aggregate stopped at exactly 50 pages / 25,000 rows** and reported
  0 records. Looks like `MAX_PAGES` — unconfirmed.

**Pinned bugs**

- `search_standard_receipts` can never report `truncated=True`.
- W7 — "supplier sites" mis-parses as addresses. `Site` has ZERO field
  rows in the KG, which is why.

**Open questions**

- **Why does `who columns` alone drop silently** while ten other
  unresolvable terms refuse loudly? Plurality and jargon-as-a-collective
  were both tested and excluded. No explanation. §G7.5.
- **`--show-timings` emits nothing.** A diagnostic flag that is accepted
  and does nothing.
- **"Show invoice lines for invoice X" returns a count, not the lines.**
  Same shape as the applications defect fixed this session.

**Closed this session**

- ~~§G7.1: narration citing fields absent from the raw row~~ — **not a
  synthesizer defect.** `--show-raw-output` was truncating rows at six
  fields silently. Fixed; it now names what it holds back.
- ~~"1 suppliers", doubled blank lines, "None examined"~~ — fixed.

---

## Hard-won lessons (carried + new)

**Curl before code.** Exercised twice this session and both times it
changed the answer.

**A claim from inspection is not a finding — and a claim from a VIEW of
the data is not one either.** Two wrong conclusions this session, both
from reading an abbreviated view and treating it as the thing itself:
six fields of a row read as the whole row, and one measured prompt read
as characterising all cases. **A view that does not announce its own
limits will produce confident wrong answers indefinitely** — which is
why `--show-raw-output` now names what it hides.

**Read the reference doc before curling.** The tax-line join key is
documented under a CAUTION in
`docs/spire_fusion_endpoints_reference.md`. It was found after two wrong
guesses including a curl against an endpoint that does not exist. The
doc is the authority on pod behaviour; it was faster than the guessing.

**Enumerate before generalising.** The single-parent rule was nearly
written from the first three shapes looked at. Those three suggested
"one parent, one child"; the fourth has two children. Enumerating all
sixteen cost one command.

**Removing a layer exposes what it was masking.** Local synthesis made
`Applications : 10` visible as a defect — the model's narration had been
covering for a display that showed counts where rows were asked for.
Expect more of these as the remaining entities convert.

**Measurement tests whether a thing works, not whether it should
exist.** Eleven prompts correctly measured the refusal machinery and
could not have revealed that the third outcome should not exist. The SME
question — "why is there a third category at all" — did what no prompt
could.

**A tally is not a verdict.** Unchanged, and still true.

**An example in a prompt is an instruction.** Unchanged.

**Deliver the complete file, never a fragment.** Unchanged.

---

## Reference

- KG rebuild: `python scripts/rebuild_kg.py` — always from scratch, and
  **every session**.
- **Restart the MCP server after ANY change under
  `src/spire/mcp_server/`.**
- Full suite: `python -m pytest -q` — **799 passed, 18 deselected, 1
  xfailed**. ~2.5 minutes.
- Setup and flags: **`spire_setup_guide.md`** (renamed from
  `how-to-run-02.md`).
- Prompt sets: `scripts/prompts/README.md` — counts corrected, all
  eleven sets listed.
- Pod quirks: `docs/spire_fusion_endpoints_reference.md` — **§15 is
  new**, field names for every AR bucket plus the ordering-stability
  finding.
- Token check: `--show-tokens`. A local path shows `parse` alone.
- `--show-raw-output` now names the fields it holds back. Trust it.

**Concurrency:** unchanged — single-threaded, sequential, `asyncio` for
non-blocking I/O.

**Files to share when starting the next task:** this handoff,
`docs/spire_enhancement_requirements.md`,
`docs/spire_enhancement_status.md`, plus the code files the task
touches. Every file in this project drifts between sessions —
re-sharing is the standing rule, not an exception.

**One request for the next session:** give uploads distinct names. Every
file this session was called `t.txt`, so each upload replaced the last
and earlier results could not be referred back to.
