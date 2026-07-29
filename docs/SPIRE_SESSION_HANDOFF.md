# Spire — Session Handoff (2026-07-29)

Paste into the new window to continue. Supersedes the 2026-07-28 handoff.

---

## Who / what

Continuing **Spire** — AI-native NL query over Oracle Fusion Cloud (P2P +
AR). Deterministic KG pipeline: parse → plan → execute → synthesize, two
LLM boundaries only (parser, synthesizer). Tool selection is a KG lookup,
not an LLM judgement. Not an agent architecture.

Repo `github.com/bhagavansprasad/spire`, working dir `~/pocs/spire`, pod
`fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`, creds in
`personas.yaml` (gitignored).

**Currently on branch `lifecycle-poc`**, freshly merged with master, 504
tests passing.

---

## What the last session did

An SME (Venu) ran 25 prompts and reported 21 failures. The session
started by analysing that report and ended nine merged phases later.

**The report was wrong in both directions.** Twelve of the 21 "failures"
were one stale KG — parse input was ~6,845 tokens against a known-good
~8,119, which is the KG menu arriving short. Seven more were correct
refusals of genuinely unanswerable prompts. Meanwhile FOUR real defects
sat inside prompts marked `[ok]`, including a credit-memo total that
summed USD, CAD, GBP and EUR into one number and printed it as fact.

Score went from **11/25 to 25/25 behaving correctly.**

### Merged to master (nine phases)

| # | What | Why it mattered |
|---|---|---|
| 0 | Test-suite realignment | Suite could not COLLECT. 32 failures: 31 stale tests, 1 real bug |
| 1 | Planner refusal quality | Filter dumps → guards with typeable examples |
| 2 | Credit-memo currency | `Total credit value: -17232.52` across 4 currencies |
| 3a | Tools report `totalResults` | 3 tools could never report truncation |
| 3b | Synthesizer narrates truncation | "25 credit memos" where 2,111 exist |
| 4 | Deterministic supplier records | 2 prompts burned 48,750 tokens producing NOTHING |
| 5 | `plan_refusal` flag | Refusal-vs-crash was decided by grepping the message |
| 6 | StandardReceipt KG alignment | KG advertised a tool the server does not have |
| 7 | Column display | Record block + table printed the same data twice |

### The finding that outranks the fixes

**The KG was not reproducible.** A `lag_query` filter and a
`get_receipts_with_lag` entity tool were live in the Oracle KG but in
NEITHER the seed nor master — the code is on
`feature/ar-prompt-18-parking`. The KG was advertising a tool the running
server does not have. Anyone running `rebuild_kg.sh` got a different
system from the one being tested against.

Both rows were removed; they belong with prompt 18 when it lands.
Seed and database now agree. Counts: `kg_entity_tool` 9,
`kg_entity_filter` 23.

---

## Where the lifecycle work stands

Target prompt (SME catalog A.4 + A.2, agreed):

> "Has PO [number] been fully received, fully invoiced, and fully paid?
> Show ordered, received, invoiced, paid, and remaining amounts with
> supplier details, and identify the current lifecycle stage and
> responsible team."

**Build sequence position: steps 1–2 done, step 3 next.**

| Step | Status |
|---|---|
| curl discovery | ✅ done |
| standalone tool | ✅ `src/spire/mcp_server/tools/po_lifecycle.py` |
| KG rows | ⬅ **NEXT** |
| planner / parser / server wrapper | pending |
| synthesizer / display / prompts / tests | pending |

### Curl findings (all verified 2026-07-28)

- `/purchaseOrders`, `/purchaseOrderSchedules` both filter server-side on
  `q=OrderNumber='<n>'` — the schedules one was previously undocumented
  (only `POHeaderId` was known).
- **`ReceivedAmount` is 0 or null on EVERY schedule row on this pod**
  (~4,500 rows checked). The received leg exists only as a QUANTITY, so
  the amount is DERIVED: `Amount * (ReceivedQuantity / Quantity)`.
  Oracle's own arithmetic agrees — PO 701337 line 1 is Amount 1116,
  Quantity 4, ReceivedQuantity 1, and the pod's BilledAmount is 279,
  exactly 1116 × ¼.
- Header `Ordered` is Oracle's own total; the schedule sum cross-checks it.

### The two test POs

| PO | Ordered | Received | Invoiced | Paid |
|---|---|---|---|---|
| **701337** (JGA, Open) | 1235.00 | 398.00 derived (2 of 5 units) | 398.00 | none |
| **162034** (Lee Supplies, Closed) | 758.00 | 758.00 | 758.00 | 830.01 ✓ |

Neither has all four legs; together they cover everything. 701337 proves
partial reconciliation and mixed line statuses (one Open, one Closed);
162034 proves the invoice join and carries a genuine exception — an
invoice **72.01 ABOVE** the order, probably tax, unconfirmed.

701337 has `PayOnReceiptFlag: true`, which may explain why it has billing
with no PO-linked invoice (self-billing). **Unconfirmed hypothesis.**

### Two decisions still open on `po_lifecycle.py`

**1. The paid leg for a PO with no matched invoice.** 701337 reports
`remaining_to_pay: 398.00`, computed as invoiced − paid where "invoiced"
comes from SCHEDULES. But no AP invoice exists, so it asserts 398 is owed
when the truth is "the bill cannot be found."

Options were: leave it; base the paid leg on matched invoices (gives 0.00
but then `fully_paid: true` on a PO where nothing was paid); or
**tri-state it** — paid / partially paid / **unknown**. The third was
recommended and NOT yet decided: it is the only one that doesn't assert
something false, and "the chain breaks here" is what a lifecycle view
should say.

**2. The tool predates this session's patterns.** Its `_page_all` does
not request `totalResults` — the same gap fixed in three AR tools in
phase 3a. Low impact (both fetches are scoped to one PO) but the
`MAX_PAGES` cap can still be hit silently. Worth aligning before KG rows
lock the interface.

---

## Open issues, carried forward

Ordered by how much damage each can do.

### Can put a wrong number in front of someone

- **Invoice total over a sample.** "invoices for Lee Supplies" says "The
  total amount for these invoices is 36646.61 USD" — a sum over 25 of
  1,343 rows, stated flat. Same family as the credit-memo total already
  fixed, different mechanism.
- **"country" returns a full address.** "Supplier number and country for
  active suppliers" produces an `Address` column holding
  `7 Saxon Close,AGHORY,Armagh,UNITED KINGDOM`. An analyst asking for
  country wants "United Kingdom".
- **Only the FIRST address is shown**, silently, for suppliers with 25.
- **`StandardReceipt` and `AccountReceipt` model the same receipts** with
  different projections and — per the KG's own notes — DISAGREEING
  COUNTS. Both are routable by the planner, so two near-identical prompts
  can return different numbers.

### Known bugs, pinned

- **`search_standard_receipts` can never report `truncated=True`.** It
  computes truncation then passes `total_available=None`, and
  `ToolResult.build` derives truncated FROM that None. Pinned by a
  `strict=True` xfail in `tests/test_standard_receipts_tool.py`, so it
  cannot be fixed silently. Needs `ToolResult` to express "truncated,
  total unknown".
- **W7 — "supplier sites" mis-parses as addresses.** Root cause found:
  `Address` and `Site` have ZERO `entity_synonym` vocab rows while ten
  other entities have them, so the parser guesses. But this is a full
  phase, not a data fix: the synthesizer has NO concept of a site (no
  `SiteInfo`, no `SupplierRecord.sites`, no prompt clause, no display).
  Five of ten build steps outstanding.

### Housekeeping

- **17 tests are DESELECTED** by a marker filter nobody has examined. A
  green suite that silently skips 17 tests is a weaker guarantee than it
  looks. One command to find out.
- `print_kg.py` counts may disagree with the tests again after phase 6.
- Address flattening exists TWICE: `_format_projected_table` for the
  table, `_address_info` in the synthesizer. One behaviour, two places.
- "Answer:" prints twice on column queries — once for the summary, once
  above the table.
- 31 branches on the remote, most looking merged. Worth a prune.

---

## Token profile (measured, 25-prompt run, post-fixes)

```
parse       25 calls  in=202,980  out= 7,990  total=210,970   (75%)
synthesize  10 calls  in= 53,110  out=15,562  total= 68,672   (25%)
GRAND                                          total=279,642
```

**Parse input is constant at ~8,119 per call** — the KG menu (22
entities, 23 filters, 97 vocab terms) rebuilt and re-sent every time. The
question itself is 10–20 tokens of that.

Parse rose from 65% to **75% of consumption** this session — not because
parse grew, but because synthesize shrank. The prompt-caching argument is
now stronger, and its target is unchanged: 202,980 input tokens
re-sending the same menu 25 times.

**Diagnostic:** if `parse in=` is much below ~8,119, the KG did not
rebuild. Everything downstream is then meaningless. Check this before
reading anything into a run.

---

## How to test (give this to QA)

```
1. git pull
2. python scripts/rebuild_kg.py          # don't skip — the seed changed
3. Terminal 1:  python -m spire.mcp_server.server
   (already running? restart it, or you test old code)
4. Terminal 2:  python scripts/run_prompt_set.py \
                  --prompt-file scripts/prompts/qa_testcases.txt
```

**Classify results in four buckets, not pass/fail:**

| Bucket | Meaning | Bug? |
|---|---|---|
| Passed | Answered, and the answer is right | no |
| Not a valid prompt | Can't be answered as written | no — fix the prompt |
| Refused | Fair question, not supported yet | no — feature request |
| Failed | Crashed, or answered WRONGLY | **yes** |

A refusal is not a failure. The dangerous outcome is a confident wrong
answer — it is the only one that passes a quick read, and it is exactly
what the SME's original report missed.

**Every prompt runs on its own.** No memory of the prompt before or
after. "For that PO, how much was received?" cannot work; write "For PO
2144, how much was received versus ordered?" instead.

---

## Hard-won lessons (carried + new)

**Curl before code.** Every fix that stuck started with a curl; every
theory-first attempt got reverted.

**A diagnosis from a previous session is a claim, not a fact.**
Re-observe before acting.

**Read the answers, not the tally.** "21/25 ran cleanly" was true of a
run where 4 answers were silently wrong. The runner prints this warning
itself.

**Check the environment before believing a failure report.** One token
count would have invalidated 12 of the SME's 21 findings before anyone
read them.

**Fixing a bug can expose a rule the bug was enforcing.** Making the
synthesizer succeed on address queries removed the failure that had been
keeping the record block off column output. Nothing else enforced it.

**Don't classify on message text.** Refusal-vs-crash was decided by
`"require" in err`. Rewording a guard silently reclassified it — and did.

**Compute in the tool, not the prompt.** Every numeric bug fixed has been
fixed by having the tool compute and the synthesizer copy.

**Ask what already exists before building.** The deterministic-record fix
was built parallel to the column feature, which had already established
the same principle and even the same address flattening. Cost: duplicated
logic and a display regression.

---

## Reference

- KG rebuild: `python scripts/rebuild_kg.py` — always from scratch.
- **Restart the MCP server after ANY change under
  `src/spire/mcp_server/`.** Tool definitions are built at import. This
  has cost false diagnoses more than once. Planner, parser and
  synthesizer changes do NOT need a restart.
- Synthesizer five-place rule: adding an entity touches the registry,
  `_SYSTEM_PROMPT_BY_ENTITY`, `_collect_valid_ids`, the validator
  function, and the validator dispatch — plus the empty-array guard,
  whose bucket name must match `_OUTPUT_NAME_BY_ENTITY` exactly.
- KG tripwires: bump `print_kg.py` AND `tests/test_kg_metadata.py`
  together.
- Pod quirks (confirmed): composite `q=` fails silently with HTTP 200 /
  `totalResults: 0` — use SINGLE clauses only; `expand=sites` ignored on
  bulk fetches; `/standardReceipts` rejects `fields=` (500);
  `Supplier.Status` must be matched client-side; child bodies omit the
  parent id (join key is the URL path); addresses use `expand=addresses`
  with PascalCase keys and `SupplierAddressId`;
  `TransacationBusinessCategory` is misspelled by Oracle — use the typo;
  `curl --compressed` required.

**Files to share when starting a task:** `docs/spire_plan.md`,
`docs/spire_fusion_endpoints_reference.md`, this handoff, plus the code
files the task touches. Always re-share before editing — never work from
a copy pasted earlier in the session.
