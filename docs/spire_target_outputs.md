# Spire — Working Notes

**Date:** 2026-07-24
**Type:** working notes, not a plan

---

## 1. Status report

For pasting or showing.

```
Spire — status

Done:      Parser, planner, intent, synthesizer — full pipeline live
Done:      PO, AP, Supplier, Buyer, AR modules complete
Working:   column output is fixed, not dynamic — user columns not honored

Mandatory:  dynamic columns + CSV spill when too wide
Mandatory:  GL and AP-write modules
Important:  lifecycle view — PoC one prompt proves the architecture
Later:      parser token optimization — RAG
```

**Priority categories:**

| Item | Category | Weight |
|---|---|---|
| Dynamic column output + CSV | Synthesizer | Mandatory |
| GL, AP-write | New modules | Mandatory |
| Lifecycle view (PoC first) | New feature | Important |
| Parser token cost (RAG) | Optimization | Later |

---

## 2. Column output + overflow to CSV / Excel

**Two separate problems. Don't conflate them.**

### 2a. Column output is fixed, not dynamic

**Today the output prints a fixed set of columns, not the ones the user
asks for.** Specific user-requested columns are not honored. This is the
gap to close: the columns a prompt names must be the columns that print.

**The data is already available.** The endpoint returns these columns; the
executor reads them. This is not a retrieval problem — nothing new needs
fetching from the database, and nothing upstream needs redoing.

**The columns are lost between the intent and the report.** When a prompt
names columns, they are dropped either at the parser (never carried into
the intent) or at the synthesizer (present but not printed). Which of the
two is not yet confirmed.

Seen on the EIP Inc probe (2026-07-24): asked for PO number, PO line
number, line number — only `PurchaseOrderNumber` survived into the intent.
The other two vanished with no error.

**The fix is confined to the output path.** The parser must carry every
requested column into the intent, and the synthesizer must print every
column the intent carries. No change to retrieval, no new endpoints, no
rework of the planner or executor.

**Mandatory.** Printing what the user asked for is core correctness. Fix
this before the CSV work — no point routing dropped columns to a wider
format.

### 2b. Wide output → CSV / Excel

When the result has too many columns for the console, write a file instead
of truncating.

Design questions to settle:
- **Trigger** — automatic on column count / width, or an explicit flag
  (`--csv`, `--xlsx`)? Explicit is simpler and predictable.
- **Format** — CSV is trivial and universal. Excel adds formatting but
  needs a library. Start with CSV.
- **What goes in the file** — the full projection (all requested columns,
  all rows), while the console shows a summary line and the file path.
- **Where** — a known output dir, filename from the prompt or a timestamp.

**Sequence:** fix 2a first, then 2b becomes "the columns now exist, put the
wide ones in a file."

---

## 3. Parse-token optimization — RAG

**The problem, measured.** Every parse call sends ~8,118 tokens. Confirmed
constant across 103 prompts — min 8,112, max 8,137. That is the KG menu
(entities, filters, vocabulary), rebuilt and resent every time. The actual
question is 10–20 tokens of it.

Parse is **65% of all token consumption** in a run, and almost all of it is
this fixed payload.

**The idea.** A plain RAG system with a vector database. Embed the KG
menu once. Per prompt, retrieve only the relevant slice instead of sending
the whole menu.

### Open question — this is a design shift, not just a saving

Right now the parser is **deterministic**: the full menu goes every time,
so the same prompt always sees the same options. That is the core premise
of Design 3 — tool selection is a lookup, not a guess.

A top-k vector retrieval changes that. Two similar prompts could retrieve
slightly different menus, and a prompt could miss an entity that didn't
rank in the top-k. The determinism becomes a similarity judgment.

**This needs a decision before building:**
- Does the retrieved slice have to be provably complete for the prompt, or
  is best-effort acceptable?
- What is the fallback when retrieval misses — send the full menu?
- Is the risk of a wrong-but-cheaper parse acceptable, given the run
  already has a parse-runaway problem on multi-field prompts?

### A cheaper alternative worth comparing

**Prompt caching on the parse call.** The system prompt is byte-identical
every time. Caching it cuts the repeated cost with **zero behaviour
change** — the parser stays fully deterministic. No vector DB, no retrieval
risk.

Not either/or. Caching is the low-risk win available immediately; RAG is
the larger change. Worth measuring what caching alone saves before
committing to RAG — it may capture most of the benefit at none of the
determinism cost.

---

## 4. Lifecycle view — the architecture test

The lifecycle view (see `spire_lifecycle_goal.md`) is not just another
feature. It is a **test of whether Spire's architecture can do everything
it would need to.**

**The reasoning.** If Spire can produce even one lifecycle prompt as
anticipated — assembling documents across systems, reconciling amounts,
detecting exceptions, attributing ownership — then the design holds and
everything else is more of the same shape. If it cannot, that is a finding
about the architecture worth knowing before building more.

**Two phases:**
1. **PoC** — one prompt (Shape C or a single PO), end to end. The point is
   the proof, not the polish.
2. **Build** — the full feature, only if the PoC validates the approach.

The PoC is high-value precisely because it is cheap relative to what it
tells you: whether the ceiling is where the goal assumes it is.

---

## Suggested order

1. **Fix 2a** — dynamic columns. Mandatory correctness; small.
2. **Lifecycle PoC** — one prompt. Proves the architecture before more is
   built on it.
3. **2b — CSV output** — once columns are honored.
4. **GL and AP-write modules** — mandatory coverage, known pattern.
5. **RAG** — last. Biggest change, one unresolved design question
   (determinism), and prompt caching may capture most of the benefit first
   at no risk.

Reason for this order: 1 is mandatory and small. 2 is cheap and answers
the largest open question about Spire's ceiling — worth doing before
investing in more modules. 5 goes last: it is the most interesting but the
riskiest, and should not lead just for that reason.
