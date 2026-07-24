# SPIRE — SESSION HANDOFF

**Written:** 2026-07-24, end of a verification-and-fix session.
**Supersedes:** the 2026-07-23 handoff, whose Issue 6 diagnosis was
already stale when it was written. See "What the last handoff got wrong".

---

## READ THIS FIRST

The previous session ended with prompts claimed as working but never
observed running. This session ran them. **Nine bugs were found and
fixed, all verified end-to-end against the live pod.** Everything below
marked VERIFIED was watched running; everything marked OPEN was observed
failing and is not fixed.

The one instruction worth carrying: **run a curl against the pod before
changing code.** Every fix that stuck this session started with a curl.
Every attempt that was reverted started with a theory.

---

## WHAT THE LAST HANDOFF GOT WRONG

Recorded because the failure mode matters more than the specific error.

**Issue 6 ("three prompts broken, filter-lookup change applied to the
loader but not its callers") was already fixed.** `planner.py` lines 351,
361 and 371 unpack the tuple key correctly. The error it described,
`Supported entity-level: []`, does not occur anywhere.

The three prompts were failing for **three different reasons**, and one
was not failing at all:

| Prompt | Handoff said | Actually |
|---|---|---|
| `Supplier`/`name_fragment` | broken | **passes** — was already fine |
| `Invoice`/`supplier` | broken, plan time | failed at EXECUTE — placeholder arg |
| `Invoice`/`purchase_order` | broken, plan time | failed at PLAN — a stale guard |

**The lesson:** a diagnosis written in one session and read in the next
is a claim, not a fact. Re-observe before acting on it. Roughly an hour
went into chasing a bug that had already been fixed.

---

## VERIFIED THIS SESSION — nine fixes

Each was watched failing, then watched passing.

| # | Bug | Where | Prompts |
|---|---|---|---|
| 1 | `tool_arg_name: 'supplier'` was a PLACEHOLDER nothing implemented. Both KG rows document the routing ("all-digit → supplier_number, else supplier_name") but no code did it | planner | Address/supplier, Invoice/supplier |
| 2 | Invoice guard demanded a supplier and rejected `purchase_order`. The PO guard's own comment described the Invoice guard as already widened — it was not | planner | Invoice/purchase_order |
| 3 | Synthesizer registry keyed `ExposureRanking` (PascalCase) where the parser emits `exposure_ranking`. Lone PascalCase entry among five | synthesizer | 10 |
| 4 | `_build_aggregation_plan` never read `intent.filters`, so the customer scope was silently dropped and the tool ran pod-wide. Plus a duplicate dict key silently shadowing `account_number` | planner | 17 |
| 5 | Server wrapper missing `customer_name` — the standalone tool had it, the MCP-exposed wrapper did not | server | 17 |
| 6 | Aggregation tool capped at 500 rows with no pagination: reported a 500-row sample of 1,386 as a total, and hid an entire receipt method | tool | 17 |
| 7 | Receipt applications over-fetched 500 and filtered client-side; bucket name wrong in FOUR places | tool + synthesizer | 9 |
| 8 | `total_available` discarded by the executor's unwrap. Count reported the page size (10) as the account total (7,038) | executor | 9 |
| 9 | Synthesizer expanded a float to the token cap: `1179915.3225` → full IEEE-754 binary expansion, then trailing zeros | synthesizer | AR invoices by customer |

**Plus: three dead validators.** The empty-array guards in
`synthesize_response` checked bucket names that do not exist
(`accountreceiptapplication`, `customertransaction`, and two others).
They had never fired. All four now match `_OUTPUT_NAME_BY_ENTITY` and
one caught a real failure the moment it was corrected.

**Plus: display-layer fixes.** `transaction_date` missing from the AR
invoice schema (crashed the whole AR set), and `run_plan.py` having no
tax-line branch at all (8 tax lines fetched, none displayed).

**Plus: crash isolation in `run_prompt_set.py`.** One `AttributeError`
in the display layer killed the AR set after prompt 1; 15 prompts never
ran. Each prompt now runs in a try/except.

---

## OPEN ISSUES — observed failing, not fixed

Ordered by severity.

### 1. Receipt-method aggregate is not reproducible

Two runs, same account, same tool, consecutive days:

| | Run A | Run B |
|---|---|---|
| Total receipts | 1,386 | 1,386 |
| Total amount | 215,721,775.28 | **250,557,301.49** |
| Lockbox | 993 / 211,999,593.81 | **1,132 / 247,941,421.77** |
| Check | 393 / 3,722,181.47 | **254 / 2,615,879.72** |

Same row COUNT, different rows. Both splits sum to 1,386. A 35M
difference in total means it is fetching a different 1,386 rows each
time.

**Hypothesis (unconfirmed):** `/standardReceipts` has no default
ordering. The tool pages with `offset` and no `orderBy`, so the pod can
return shifted or overlapping pages. Fix is the same as the one applied
to receipt applications: add a deterministic `orderBy` to the paginated
fetch. **Confirm with a curl before changing code.**

### 2. Column selection does not work — a designed feature, inert

`fields` is parsed into the Intent correctly and NOTHING downstream uses
it. `_project_outputs(outputs, fields)` exists in `graph/pipeline.py`;
`run_plan.py` never calls it.

Evidence: asking for ONE field and asking for TWO produced
**byte-identical output** — same token counts, same answer text, same six
columns. Same for the Invoice and PO roots.

Second, separate defect: requesting `country` as a FIELD triggers the
address over-fetch used for country FILTERING. Synthesizer input 16,881
tokens vs 2,729 for the working prompts, then MAX_TOKENS. The four-field
form also degraded the parser (out=820 vs 227-285).

### 3. `open_only` may not filter

`Show me open invoices for customer ABC Corporation Americas` returns 25
"open" invoices. The unfiltered prompt on the SAME account says all 25
transactions are "currently closed with a balance of 0.00". Both cannot
be true. Either `open_only=True` is not reaching the filter or the closed
claim is fabricated.

### 4. `count_only` is parsed and ignored

Intent carries `count_only: True`; the plan ignores it and fetches 25
rows. The answer ("424 suppliers") is plausible and consistent with the
truncation note, but its provenance is unverified — the executor returns
25 rows and the number is not among them.

### 5. Page size stated as total — at least five prompts

"There are 25 receipt applications", "The account has 5 open invoices",
"25 credit memos", "The query returned 25 suppliers" (of 421). The
truncation block reports the real number; the narration does not always
use it. Prompt 9 was fixed by threading `metadata_by_step`; the same
pattern applies elsewhere.

### 6. Synthesizer asserts fields absent from the output

Seen 5+ times: "all currently closed with a balance of 0.00", "the
administrative contact is John Kim", "some invoices are marked as paid,
while others are unpaid". None of those fields are in the displayed
projection. Probably real data behind display truncation, but
unverified — and indistinguishable from fabrication without checking.

### 7. `Suppliers with their addresses` — MAX_TOKENS

The nested-address expansion overruns the synthesizer. Same root as the
`country` column failure.

### 8. Creation-to-update lag prompt refuses

`Show lag between creation and last update for receipts of X` refuses as
out-of-scope. The KG has a `lag_query` filter and a
`get_receipts_with_lag` tool is registered. Either the filter is not
reaching the parser menu or the tool is not wired.

### 9. PO totals disagree between prompts

`Show PO 2144 and its lines` reports 41,250.00; `What is purchase order
2144 about?` reports 45,168.75. Same PO. One is `Ordered` (ex-tax), the
other `Total` (inc-tax). Both defensible; a user asking twice gets two
numbers with no explanation.

### 10. `How many purchase orders are there and what are they worth?`

Reports 10,000 POs. The prompt set says ~3,362. 10,000 is a suspiciously
round cap, and the per-status counts (6,991 + 713 + 262 + …) do not reach
it either.

### 11. `Invoices for Lee Supplies in 2023` — inconsistent across days

Returned 11 invoices with real amounts across the year on one run, then 5
invoices all dated 2023-06-23 and all 0.00 USD on the next. Either the
data changed or the filter did. Not investigated.

### 12. Housekeeping

- **`pytest` has NOT been run this session.** `execute_plan`'s signature
  changed from 2 return values to 3. `test_executor.py` very likely
  asserts the old shape. This is the highest-risk unknown in the repo.
- KG tripwires drifting: `kg_entity_tool` 10 vs expected 9,
  `kg_entity_filter` 25 vs expected 23. Bump both in `print_kg.py` AND
  `tests/test_kg_metadata.py` together.
- No validator exists for tax lines. Four child buckets have guards; tax
  lines does not.
- `_build_synthesis_prompt`'s metadata block is hardcoded to the
  `account_receipt_applications` bucket. Does not generalise.

---

## HARD-WON LESSONS FROM THIS SESSION

**Repair code placed before a check disables the check.** A structural
fallback populated an empty `applications` list from the raw bucket. It
ran BEFORE the validator that tested for an empty list, so the validator
could never fire — recreating the exact silent failure that had just been
fixed. Removing it revealed the model had never been populating that list
at all; the fallback was doing 100% of the work on every run.

**A factual statement in the synthesis prompt can suppress row
emission.** The metadata sentence read "The total ... is 7038. The list
below shows only the most recent ones." That second clause read as
permission to skip the rows: the model stated the total and wrote a
summary (out≈793) instead of emitting them. Dropping the clause restored
emission (out≈2148). Same family as the parser runaway — the model
over-reads an instruction.

**Rounding at source was NOT sufficient for the float bug.** With the
tool returning `1179915.32`, the model still emitted the unrounded
expansion. It was GENERATING those digits, not copying them. Only
post-processing the response (`_round_floats` after synthesis) made it
deterministic.

**Naming across un-typechecked boundaries is the dominant bug class.**
Five this session: KG→tool arg name, parser→synthesizer shape key,
planner→wrapper parameter, synthesizer→executor bucket name (×4), and
schema→display field name. None of these boundaries type-check. All five
failed silently.

**The display layer runs behind the schema.** Three separate bugs:
a schema field the formatter read but did not exist, a schema field the
formatter never read, and a projection function never called. A generic
formatter walking the Pydantic model would have had none of them.

**Compute in the tool, not the prompt.** Every numeric bug fixed this
session was fixed by having the tool compute the value and the
synthesizer copy it. Where the tool did the work it was right first time;
where the prompt asked the model to do it, it took multiple rounds.

---

## TOKEN PROFILE (measured, ~15 runs)

| Stage | Input | Output |
|---|---|---|
| Parse | ~8,120 (constant) | 200–800 |
| Synthesize | 1,100–5,900 | 720–3,100 |

**Parse input is fixed at ~8,120 regardless of the question.** That is
the KG menu — 22 entities, 25 filters, 97 vocabulary terms — rebuilt and
re-sent on every call. The actual question is 10-20 tokens of it.

Parse:synthesize on total tokens runs about **1.5:1**, ranging from 4:1
on a single-record answer to 1.1:1 on a 25-row answer.

**Highest-leverage cost reduction: prompt caching on the parse call.**
The system prompt is byte-identical across every call. No behaviour
change.

---

## RECOMMENDED ORDER FOR THE NEXT SESSION

1. **`python -m pytest -q`.** It has not run. The executor signature
   changed. Everything else is built on this.
2. **Bump the two KG tripwires** (10 and 25) in both files.
3. **Curl `/standardReceipts` with and without `orderBy`** to confirm
   the pagination hypothesis behind open issue 1, then fix.
4. **Wire `_project_outputs` into `run_plan.py`** — column selection is
   designed and inert.
5. Investigate `open_only` (issue 3) and `count_only` (issue 4).
6. Prompt caching on the parse call.

---

# REFERENCE

## Repo & environment

- Repo `github.com/bhagavansprasad/spire`, working dir `~/pocs/spire`
- Demo pod `fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`
- Credentials in `personas.yaml` (gitignored)
- KG rebuild: `python scripts/rebuild_kg.py` — always from scratch, never
  incrementally
- LLM: Gemini via Vertex AI; multi-provider seam in `build_llm()`
- `LLM_MAX_OUTPUT_TOKENS = 8000` — deliberately not lower; legitimate
  synthesizer output on large result sets needs ~3,400

## Prompt sets — REORGANISED 2026-07-24

```
scripts/prompts/
  00_dipstick.txt          6   depth-ordered triage — run first
  01_supplier.txt         38
  02_purchase_order.txt    9
  03_ar.txt               15
  04_columns.txt           8   feature is BROKEN, set documents it
  05_refusals.txt         10
  06_slow.txt             16   minutes each
  scorer/parser_stress.txt 60  EXPECT ||| format — SCORER ONLY
```

`run_prompt_set.py` takes several files:

```
python scripts/run_prompt_set.py --prompt-file \
  scripts/prompts/00_dipstick.txt scripts/prompts/03_ar.txt
```

**The summary line is not a verdict.** "16/16 ran cleanly" was true of an
AR run in which 6 of 16 answers were wrong. Read the answers.

## MCP server

Restart after ANY change under `src/spire/mcp_server/`. Tool definitions
are built at import. This cost three false diagnoses in one session —
edits looked like they had failed when the old process was still serving.

```
pkill -f "spire.mcp_server.server"
python -m spire.mcp_server.server
```

Planner, parser and synthesizer changes do NOT need a restart.

## Build sequence for a new phase

curl discovery → standalone tool → KG rows → planner → parser → **server
wrapper** → synthesizer → `run_plan.py` display → prompt set → tests →
verify end-to-end → branch/PR/merge.

The two steps most often skipped, both of which bit this session: the
**server wrapper** (a standalone tool gains a parameter, the wrapper does
not) and the **`run_plan.py` display** (the schema grows, the formatter
does not).

## Synthesizer update points

Adding an entity touches: registry `SYNTHESIS_SCHEMAS`,
`_SYSTEM_PROMPT_BY_ENTITY`, `_collect_valid_ids`, the validator function,
the validator dispatch dict — **and the empty-array guard, whose bucket
name must match `_OUTPUT_NAME_BY_ENTITY` exactly.** That last one is new:
three of the four existing guards had the wrong name and had never fired.

## Files to share in a new window

`spire_expansion_plan.md`, `spire_fusion_endpoints_reference.md`, this
handoff, plus whichever of `planner.py` / `synthesizer.py` /
`server.py` / the relevant tool the task touches. **Always re-share
before editing** — do not work from a copy pasted earlier in the session.
