# SPIRE — Findings Log

**Purpose.** Append-only notebook. One entry per finding, as we make it.
This is the lab notebook, not the report. The formal audit —
`phase-1-audit.md` — is updated separately, in batches, when we have
enough to consolidate.

**Finding ID:** `F-NNN`, monotonic. Never reused. Never renumbered.
**Newest at the top.** Append below the header; correct by adding a new
entry, never by editing an old one.

**Entry format** (keep it short — this is a notebook, not prose):

```
## F-NNN — {one-line title}

**Date:** YYYY-MM-DD
**Status:** open · root-caused · fix-in-progress · fixed · closed-as-not-a-bug
**Cross-refs:** bug IDs from phase-1-audit.md

**Evidence.** Commands run and what they printed. Copy-paste, not paraphrase.

**Root cause.** One paragraph. The mechanism, not the symptom.

**Fix location (for Phase 2).** Where the change goes, not the change itself.
The fix is Phase 2's job; this log records where.
```

**Update 2026-09-19 — scope expanded to two layers.**

Working the fix revealed the failure is not one layer but two. The Router:
line for every failing prompt shows `modules=['payables']` — the receivables
sysprompt blocks are never loaded. The classifier menu (generated from
`kg_vocabulary WHERE vocab_kind = 'entity_synonym'`) carries ZERO synonyms
for the three AR children:

    receivables:
      ReceivablesInvoiceLine               ← no aka
      ReceivablesInvoiceTransactionDFF     ← no aka
      ReceivablesTaxLine                   ← no aka

So the classifier sees only `invoice` (which maps to the payables `Invoice`)
and never routes to receivables. Even a perfect parser rule would never run.

Two layers, both required for the same user outcome:

1. **Router.** Add `entity_synonym` rows in `scripts/sql/kg_schema.sql` for
   `invoice line(s)`, `tax line(s)`, `DFF`, `flexfield`, `descriptive
   flexfield`, mapped to the correct receivables entities. Then
   `rebuild_kg.py` and `build_classifier_context.py`.
2. **Parser.** The three AR sysprompt edits (previously the whole of
   F-041's fix location).

The two layers are one fix; neither half alone solves the user's problem.

---
