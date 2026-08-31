# Handoff — Parser Context Modularization, PHASE 1 (Fusion-Module Axis)

Paste this into the new window to continue. **Read the design doc first, in
full:** `docs/features/parser_context_modularization.md` (v2 — Fusion-module
axis). This handoff summarizes; the doc is authoritative.

---

## What Spire is

AI-native NL query over Oracle Fusion Cloud (P2P + AR). Deterministic KG
pipeline: **parse → plan → execute → synthesize**. Two LLM boundaries — the
parser (words → Intent) and the synthesizer (records → prose); everything
between is a KG lookup.

- Repo: `github.com/bhagavansprasad/spire`, working dir `~/pocs/spire`
- Pod: `fa-etaj-saasfademo1` (user `Dean.White`), creds in shell env
  - Prior pod (`fa-esll-dev37`) expired; the endpoints reference may still cite
    the old URL — update when touched.
- LLM: Gemini (`gemini-2.5-flash`) via Vertex AI. `LLM_MAX_OUTPUT_TOKENS = 8000`,
  hardcoded in `src/spire/config.py` (no env override).

---

## The organizing principle (design doc §0)

**The Oracle Fusion module is THE axis of organization for Spire.** Tools,
parser context, and prompts all partition along the same four modules. Adding a
Fusion module means adding its tool group + context module + prompts as one unit.
Everything derives from the module.

The four modules and their root entities:

| Module | Root entities |
|---|---|
| **payables** | Invoice |
| **procurement** | PurchaseOrder |
| **receivables** | ReceivablesInvoice, CreditMemo, CustomerAccount, StandardReceipt |
| **supplier** | Supplier, Address |

Tools already follow this axis. This work brings **parser context** and
**prompts** onto it.

---

## The task: PHASE 1 only

Implement **Phase 1** from the design doc (§4). **Phase 2 (the router) is
deferred — do not start it.**

### Why this exists

The parser system prompt — `_SYSTEM_PROMPT_PREAMBLE` in
`src/spire/nl_parser/parser.py`, **one string literal, lines 48–~520**
(`_format_menu` at 526, `_build_system_prompt` at 570, `parse` at 574) — is an
**all-module monolith**, ~8000 tokens, shipped on every parse. Two costs:
1. Testing is expensive (full all-module context every check).
2. No module isolation — can't test/edit/bisect one module's parser behavior.

These cost ~5 hours on issue #32. Phase 1 fixes the *organization and tooling*.

### Phase 1 deliverables (design doc §4.2)

**A. Split the monolith into two tiers of context files** under
`src/spire/nl_parser/context/`:

```
Tier 1 — ALWAYS loaded (not Fusion modules; the shared base):
  core.txt       role, output/Intent contract, global rules, entity roster
  refusals.txt   refusal format + capability guidance
                 (always-on: you can't know a prompt will be refused pre-parse)

Tier 2 — selected by the router in Phase 2; ALL loaded in Phase 1:
  payables.txt      AP invoice queries
  procurement.txt   PO / purchasing / lifecycle queries
  receivables.txt   AR invoices, credit memos, receipts, customers
  supplier.txt      suppliers, sites, contacts, classifications, addresses
  columns.txt       column-projection rules (cross-cutting CONCERN)
```

`_build_system_prompt` reads and joins the files in fixed order, then appends the
KG menu. **In Phase 1 it joins ALL of them.**

**B. THE CRITICAL GUARDRAIL — string-equality (§4.1).** The assembled all-files
preamble must be **byte-for-byte string-equal** to the current
`_SYSTEM_PROMPT_PREAMBLE`, enforced by a test. Phase 1 changes *where the text
lives*, not *what production sends*. **Until string-equality holds, the split is
not done.** NEVER reword prose in this split — it is pure relocation. Any
semantic change to production behavior is out of scope (that is Phase 2).

**C. Entity→module mapping in the KG (§4.3).** Add a `module` field per entity
(Invoice→payables, PurchaseOrder→procurement, CreditMemo/ReceivablesInvoice/
CustomerAccount/StandardReceipt→receivables, Supplier/Address→supplier). The KG
is Spire's source of truth; the mapping belongs there, read by tools, context
selection, and the Phase-2 router alike.
- Bump row-count tripwires in `scripts/print_kg.py` AND `tests/test_kg_metadata.py`
  together; rebuild with `python scripts/rebuild_kg.py`.

**D. Selective-load test harness (§7)** — extend
`scripts/score_parser_prompts.py`:
- `EXPECT=<expectation> ||| MODULES=procurement ||| <prompt>` → assemble Tier 1 +
  named Tier-2 files only (cheap; bisects one module).
- `MODULES` absent → assemble ALL files (the **fidelity oracle**).
- Richer `EXPECT` grammar: `list_all`, `filter:lifecycle_status`, `no_filters`,
  `refuse[:flavor]`, alongside existing `target:`, `filter:`, `combo:`, `count`,
  `aggregate`.

**E. Capture #32 fault (a)** as a tracked KNOWN-FAIL case on `MODULES=all` (§7.3):
```
filter:lifecycle_status ||| MODULES=all ||| Is PO 162034 complete?
```

### What already exists — build on, don't reinvent (§2)

- `scripts/score_parser_prompts.py` — parse-only scorer (`EXPECT=... ||| prompt`),
  the harness's **execution engine**. Extend it (module selection + richer
  expectations).
- `scripts/prompts/scorer/parser_stress.txt` — ~60-prompt corpus, the **format to
  extend**.
- Tools already group by module; prompt sets `01_supplier`, `02_purchase_order`,
  `03_ar` already align; `04_columns`, `05_refusals`, `10_refusal_examples`,
  `11_column_vocabulary` are cross-cutting and **stay as-is** (§6).

### The fidelity caveat (§7.4) — keep the harness honest

A subset-context (`MODULES=<subset>`) run **DIAGNOSES** which module drives a
behavior. The **full assembly VERIFIES** production-equivalent behavior. A slim
context can false-pass. Assert every tracked correctness expectation on the full
assembly. (In Phase 2, fidelity becomes: router-selected == full assembly.)

### Hard boundary

**Do NOT change the LLM prompt text semantically.** Phase 1 is pure relocation
guarded by string-equality. Do NOT build the Phase-2 router. If you find yourself
editing prose to change what the model does, stop — that's out of scope.

---

## Phase 2 (deferred — context only)

Phase 2 (design doc §5) scopes context to the targeting module(s) at runtime via
a **tiny first-pass LLM classifier**: reads the raw prompt, returns the module
set (union for cross-module prompts like "suppliers with open POs"), falls back
to **all modules** when unsure (degrades to Phase-1 behavior, proven safe).
Verified against the full-assembly oracle (router-selected == full). **This is a
separate later effort. Do not start it.**

The chicken-and-egg (you must know the module before parsing, but parsing
determines the module) is real and exists **only at the parser boundary** —
downstream (plan/execute/synthesize) the KG already derives the module
deterministically from `target_entity`. That's why the router is a *pre-parse*
classifier with an all-modules fallback.

---

## Where issue #32 stands (context, not tasks)

Three High-severity issues fixed and merged in the prior session:
- **#32 fault (b)** (PR #132) — filter-less PurchaseOrder intent refuses instead
  of dumping. Signal (`Intent.list_all`) set in deterministic Python code
  (`_is_explicit_po_list`), system prompt byte-for-byte unchanged.
- **#34** (PR #133) — projection reads the bucket holding the requested column,
  not the last (`_pick_projection_bucket` in `scripts/display_formatters.py`).
- **#27** (merged) — credit-memo total withheld over a truncated sample
  (`compute_total_credit` gained a `total_available` guard).

**#32 fault (a)** — "Is PO N complete?" (Procurement) deterministically drops the
PO id. **Measured facts:** NOT a token-cap problem (short, valid, *wrong* parses
at 8000); NOT a KG-definition problem (the lifecycle target exists; explicit
phrasings reach it). A classification miss in the all-module monolith; adding
prompt text induced **MAX_TOKENS runaway (proven 3×)** — the monolith has no
headroom. De-risked by the (b) guard (fails safe to a refusal). Severity high,
tracked. **This framework is (a)'s home:** the `procurement.txt` file makes those
rules editable/testable in isolation; the harness bisects which module (or added
text) misclassifies "complete?"; any fix (a code-side injection, or reweighting
`procurement.txt`) is verified on the full assembly.

**Lesson (applies to all parser work): add parser signals in CODE, not prompt.**
The monolith is fragile; LLM-visible additions tip phrasings into runaway.

---

## Phase 1 acceptance criteria (§4.2 / §9)

1. Seven context files under `context/`; assembled all-files preamble
   **string-equal** to the pre-split literal (test-enforced).
2. Production parses **unchanged** (same intents on the existing corpus).
3. KG carries an entity→`module` mapping; tripwires bumped; KG rebuilt.
4. Harness runs a case against a **named module subset** at a fraction of the
   full token cost; richer `EXPECT` grammar supported.
5. **#32 fault (a)** captured as a tracked KNOWN-FAIL on `MODULES=all`.
6. Full `pytest -q` green before any source commit.

---

## Recommended first steps (in the new window)

1. **Read** the design doc in full.
2. **Propose the carve** of the literal (lines 48–520) into the seven files —
   show where each block goes and how string-equality will be proven. **Get
   agreement on boundaries before writing any file.**
3. **Split behind the string-equality test FIRST** (pure relocation, offline-
   verifiable). Land it before anything else.
4. **Then** the KG `module` mapping; **then** the harness (module selection +
   richer expectations); **then** the #32a KNOWN-FAIL case.
5. One branch per logical step, PR-based. Full `pytest -q` before any source
   commit.

---

## Open questions to resolve during implementation (§11)

1. Exact carve of the literal; where prose that references multiple modules goes
   (duplicate into each module, or hoist to `core`).
2. Module dependency rules; how the harness enforces "Tier 1 always included."
3. Corpus expectation grammar; migrate `parser_stress.txt` without losing
   coverage.
4. KG `module` field shape — one module per entity (cleanest); confirm no ROOT
   entity legitimately spans two (includes are the router's job, not
   multi-module entities).
5. (Phase 2) classifier confidence threshold for the all-modules fallback.
6. Menu handling — keep the KG menu a separate always-on append (likely) or fold
   into `core`.

---

## Working style (STRICT)

1. Short, interactive, ONE step at a time. One command at a time; verify before
   proceeding. No batch-generating, no 100+ line dumps.
2. Ask permission before generating code or significant content.
3. Plain-text numbered options with a recommendation and reason. No widgets.
4. Deliver the COMPLETE updated file, never a patch. Read the current full file
   (from provided bundle context) before editing — files drift.
5. Output via `tee` to `t.txt`; `>` overwrite, `>>` append. Never a bare
   `> t.txt`.
6. Git: one branch per logical change, PR-based, named files in `git add`
   (never `-A`), heredoc commit messages. Docs-only may go straight to master.
   Check the branch before committing.
7. Curl the pod before writing code for any endpoint/field; read the endpoints
   reference first. (This work is mostly offline.)
8. "Confirmed" = actually run, never inferred. Instrument before theorizing.
9. pytest always `-q`; full suite before any source commit.
10. KG rebuild: `python scripts/rebuild_kg.py` (never the `.sh`); bump
    `print_kg.py` + `test_kg_metadata.py` tripwires together when KG changes.
11. Restart the MCP server after any change under `src/spire/mcp_server/`
    (this work does not touch it).
12. Read files from provided bundle context before asking for a paste. Always
    already in `~/pocs/spire` (no `cd`).

---

## The single most important thing

**String-equality is the guardrail.** The split must produce a preamble
byte-for-byte identical to today's literal, test-enforced. That is what makes
Phase 1 safe — it cannot change production behavior. Do the split behind that
test before anything else, and never let a "cleanup" of the prose sneak a
semantic change into a relocation that is supposed to change nothing but file
layout.
