# Parser Context Modularization — Architecture

Status: **Proposed** (design only; no implementation)
Author: (drafted 2026-08-18)
Scope: the NL parser's system prompt (`_SYSTEM_PROMPT_PREAMBLE` in
`src/spire/nl_parser/parser.py`) and its testing.

This document defines **two features**, designed together but **implemented
separately and in order**:

- **Feature A — Modular context + selective-load test harness.**
  Split the monolithic parser context into module files. Production keeps
  assembling *all* of them (byte-identical behavior). A test harness assembles
  a *chosen subset* per test, so a single prompt-to-intent check costs a
  fraction of the tokens and can be bisected to the responsible module.
  **Production is not changed by Feature A.**

- **Feature B — Production dynamic module assembly.**
  Production selects only the modules relevant to a given prompt, cutting the
  ~8000-token-per-parse cost and reducing prompt fragility in production.
  Larger and riskier (module selection is itself a routing problem). **Deferred
  until Feature A exists and validates the module boundaries.**

---

## 1. Problem

### 1.1 The monolith

The parser sends the LLM one large system prompt on **every** parse:

- `_SYSTEM_PROMPT_PREAMBLE` — a single string literal
  (`parser.py:48`, ~470 lines): entity rules, the PO lifecycle block, the flag
  instructions (count/open/balance/…), column rules, worked examples.
- `+ _format_menu(menu)` — the KG menu appended by `_build_system_prompt`
  (`parser.py:571`).

Measured cost: **~8000 input tokens per parse** (e.g. `in=9195`–`9514` observed
across recent runs; the preamble is the dominant, fixed part).

### 1.2 Two costs this imposes

**Cost 1 — testing is expensive and slow.** Every prompt-to-intent test ships
the full ~8000-token context, even to check one narrow behavior (does
"Is PO N complete?" route to lifecycle?). A 60-prompt parser stress run pays
that cost 60 times.

**Cost 2 — fragility is un-bisectable.** The monolith is a single blob to the
LLM. When one phrasing misclassifies (or, with additions, derails into runaway
generation), there is no way to isolate *which part of the context* is
responsible. You cannot ask "does the lifecycle block alone classify this
right? does adding the flags block break it?" — the context is all-or-nothing.

### 1.3 Concrete motivation (issue #32)

Fixing #32 fault (b) took ~5 hours largely because of Cost 2. The terse
phrasing "Is PO N complete?" **deterministically misclassifies** to a bare
`PurchaseOrder` intent (`filters=[]`, dropping the PO id) — a classification
miss, not a token-limit problem (measured: 10/10 valid, short, wrong parses at
the current 8000 cap). Attempts to fix it by *adding* prompt text repeatedly
induced **non-deterministic MAX_TOKENS runaway** (out_tokens=7984 for a task
needing ~100), because additions to the monolith perturb the model
unpredictably. With no way to bisect the context, every attempt was
whack-a-mole. The eventual safe fix set the disambiguating signal
(`Intent.list_all`) in **deterministic Python code**, leaving the prompt
byte-for-byte unchanged — precisely to avoid perturbing the monolith.

A modular context + a cheap, bisectable harness would have made that diagnosis
minutes, not hours: load lifecycle-only → classifies right? add flags module →
breaks? → the flags module is interfering.

---

## 2. What already exists (build on, don't reinvent)

- **`scripts/score_parser_prompts.py`** — a parse-only scorer. Reads
  `EXPECT=<expectation> ||| <prompt>` lines, runs `parse()` (intent only, no
  slow execution), reduces the result to a comparable summary
  (`target_entity`, `filters`, `count_only`, `aggregate`, `refuse`), prints a
  table, and reports failures. This is Feature A's **execution engine, already
  built**.
- **`scripts/prompts/scorer/parser_stress.txt`** — a ~60-prompt corpus in the
  `EXPECT=... ||| prompt` format, organized by trap category (status paraphrase,
  country collisions, name fragments, …). This is Feature A's **corpus format,
  already established.**

**Gaps** (what Feature A adds to the above):
1. The scorer uses the **full monolith** — no way to select a context subset.
2. The corpus expectations are **coarse** (`filter:status`, `target:entity`).
   They do not assert richer intent facts we now care about
   (`list_all`, a specific `lifecycle_status` filter, a dropped-id case).
3. There is **no module structure** to select from.

---

## 3. Feature A — Modular context + selective-load harness

### 3.1 Split the monolith into module files

Carve `_SYSTEM_PROMPT_PREAMBLE` into ordered module files on disk. Proposed
boundaries (to be finalized against the actual literal):

```
src/spire/nl_parser/context/
  00_core.txt          # role, output-shape contract, global rules
  10_entities.txt      # entity roster + when-to-root rules
  20_filters.txt       # filter vocabulary and validity
  30_lifecycle.txt     # PO lifecycle block (the four legs, status/completion)
  40_flags.txt         # count_only / open_only / balance_only / invoice_limit
  50_columns.txt       # column selection / projection rules
  90_examples.txt      # worked examples
```

The module set and ordering are a design task in themselves — the split must be
**behavior-preserving** (see 3.2). Modules should be as independent as the
current prose allows; where the current text has cross-references, those are
documented as module dependencies (e.g. lifecycle examples may assume the
entity roster).

### 3.2 Production invariant: byte-identical assembly

`_build_system_prompt` changes from returning a literal to **reading and
joining the modules in order**, then appending the menu:

```
_build_system_prompt(menu):
    preamble = "\n".join(read(module) for module in ORDERED_MODULES)
    return preamble + "\n" + _format_menu(menu)
```

**The invariant, enforced by a test:** the assembled full-module preamble is
**string-equal** to the current `_SYSTEM_PROMPT_PREAMBLE`. This guarantees
production behavior is unchanged by Feature A — same bytes to the LLM, same
parses. The split is a pure refactor of *where the text lives*, not *what
production sends*.

> Migration note: capture the current `_SYSTEM_PROMPT_PREAMBLE` value first,
> split it into files, then assert equality. Until equality holds, the split is
> not done. This is the single most important guardrail — it makes Feature A
> unable to regress production.

### 3.3 The selective-load test harness

Extend the existing scorer (or add a sibling) so a test can specify **which
modules** to assemble for that case:

```
EXPECT=<intent expectation> ||| MODULES=core,lifecycle ||| <prompt>
```

- With `MODULES=...` present → assemble only those modules (+ core always) +
  the menu, and parse. Cheap: a lifecycle-only context is a few hundred tokens,
  not 8000.
- With `MODULES` absent → assemble **all** modules (the production-equivalent
  full context). This is the fidelity path (see 3.5).

The harness reuses `score_parser_prompts.py`'s parse-only execution and summary
reduction; it adds (a) module selection and (b) richer expectations (3.4).

### 3.4 Richer intent expectations

Extend the `EXPECT` grammar to assert the facts #32-class bugs turn on:

```
filter:lifecycle_status   -> intent carries a lifecycle_status filter
list_all                  -> intent.list_all is True
no_filters                -> intent.filters == []   (the dropped-id shape)
target:PurchaseOrder      -> (existing) target_entity
combo:a+b                 -> (existing) multiple filters
refuse[:flavor]           -> (existing/extended) refusal, optional flavor
```

Fault (a) then becomes a **tracked corpus case**, e.g.:

```
# KNOWN-FAIL (#32a): terse completion question should route to lifecycle,
# but the full-context parser drops the id. Tracked, severity: high.
filter:lifecycle_status ||| MODULES=all ||| Is PO 162034 complete?
```

### 3.5 The fidelity caveat (critical — do not skip)

**A subset-context test is a diagnosis tool, not a production oracle.**

Production ships the *full* context. A phrasing that classifies correctly under
`MODULES=lifecycle` proves nothing about production, which parses it under the
full monolith. Indeed #32 shows the failure is *induced by the full context* —
a slim context might parse "Is PO N complete?" correctly and **false-pass**.

Therefore:
- **Bisection runs** (`MODULES=<subset>`) are for *finding which module drives
  a behavior* — the debugging workflow that was missing.
- **Fidelity runs** (`MODULES=all`) are for *asserting production-equivalent
  behavior* — these are the ones that gate correctness.
- Every tracked correctness expectation (like #32a) is asserted on
  `MODULES=all`. Subset runs are diagnostic scaffolding around it.

This distinction is what keeps the harness honest: cheap subset runs to
*diagnose*, full-context runs to *verify*.

### 3.6 Feature A acceptance criteria

1. `_SYSTEM_PROMPT_PREAMBLE` is split into module files; assembled full-module
   preamble is **string-equal** to the pre-split literal (test-enforced).
2. Production parses are **unchanged** (same intents on the existing corpus;
   `MODULES=all` is the default when unspecified).
3. The harness can run a case against a **named module subset** at a fraction
   of the full token cost.
4. The corpus supports **richer intent expectations** (`list_all`,
   `lifecycle_status`, `no_filters`, refusal flavor).
5. **#32 fault (a) is captured** as a tracked KNOWN-FAIL case on `MODULES=all`.
6. A short doc/README explains the bisection vs fidelity workflow (3.5).

---

## 4. Feature B — Production dynamic module assembly (deferred)

### 4.1 Idea

Instead of always sending all modules, production assembles **only the modules
relevant to the incoming prompt** — e.g. a lifecycle question ships core +
entities + lifecycle, not columns/flags/examples. Real per-parse token savings
and reduced fragility *in production*, not just in tests.

### 4.2 The hard part, named honestly

**Module selection is itself a classification/routing problem.** Deciding which
modules a prompt needs — before parsing it — is a pre-parse router with its own
failure modes:
- Under-selection drops a needed module → the parse misclassifies for lack of
  guidance (a *new* class of bug).
- Over-selection erodes the token savings and reintroduces monolith fragility.
- The router must be cheap and reliable, or it costs more than it saves.

Options for the router (to be evaluated in B's own design):
- **Deterministic keyword/heuristic routing** (cheapest, most predictable;
  same philosophy as the code-side `_is_explicit_po_list` used in #32) —
  likely the right starting point.
- A lightweight first-pass LLM classifier (more flexible, adds a call).
- Static always-on core + conditional modules by cheap signal.

### 4.3 Why B waits for A

- A produces the **module boundaries** and the **fidelity harness** B needs to
  prove it doesn't regress. Without A's `MODULES=all` fidelity runs, B has no
  way to show that a dynamically-assembled subset matches full-context behavior.
- A delivers most of the *developer* value (cheap, bisectable testing) at
  near-zero production risk. B is a production behavior change; it should only
  be attempted once A has de-risked the decomposition.

### 4.4 Feature B acceptance (sketch, to be expanded in B's own doc)

1. A deterministic (or measured-reliable) module router.
2. For a representative prompt corpus, dynamically-assembled context yields
   **the same intents** as `MODULES=all` (fidelity, via A's harness).
3. Measured token/latency reduction versus the monolith, with the router's own
   cost accounted for.
4. No new misclassification from under-selection on the tracked corpus.

---

## 5. Sequencing & risk summary

| | Feature A | Feature B |
|---|---|---|
| Changes production? | **No** (byte-identical assembly) | **Yes** (dynamic subset) |
| Primary value | Cheap, bisectable parser testing | Production token/fragility reduction |
| Main risk | Low (guarded by string-equality invariant) | Higher (router is a new classifier) |
| Depends on | Existing scorer + corpus | **Feature A** |
| Order | **First** | After A validates boundaries |

**Recommended path:** implement A first, in small steps, each guarded by the
string-equality invariant (3.2) and the existing green suite. Land the module
split and the fidelity/bisection harness; capture #32a as a tracked case.
Evaluate B separately, in its own design doc, once A is in place.

---

## 6. Relationship to issue #32

- **#32 fault (b)** — fixed and merged (PR #132): filter-less PO queries refuse
  instead of dumping; explicit "list purchase orders" still lists. The
  disambiguating signal is set in Python code, prompt untouched.
- **#32 fault (a)** — the terse-phrasing classification miss ("Is PO N
  complete?" drops the id). Characterized: deterministic, **not** a token-cap
  problem, **not** a KG-definition problem (the lifecycle target exists in the
  KG and is reached by explicit phrasings). Currently **de-risked** by the (b)
  guard (fails safe to a refusal, no dump). Severity: **high**; tracked.
- This framework is the **proper home** for (a): captured as a tracked
  KNOWN-FAIL corpus case (3.4), diagnosable by bisection (3.5), and fixable
  either by a code-side injection (mirroring `_is_explicit_po_list`) or, once
  Feature B exists, by giving the lifecycle module more weight in a slimmer
  context — each verifiable on `MODULES=all`.

---

## 7. Open questions (resolve during A's implementation)

1. **Exact module boundaries** — the split in 3.1 is a proposal; the real
   boundaries fall out of the current literal's structure and its internal
   cross-references.
2. **Module dependency rules** — which modules assume others (e.g. examples
   assuming the entity roster); how the harness enforces "core always included."
3. **Corpus expectation grammar** — finalize the `EXPECT` extensions (3.4) and
   migrate `parser_stress.txt` to them without losing existing coverage.
4. **Where the harness lives** — extend `score_parser_prompts.py` in place vs.
   a sibling `score_parser_modular.py` that imports its engine.
5. **Menu handling** — the KG menu is appended after the preamble; decide
   whether it is a module or stays a separate always-on append.
