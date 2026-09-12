# Spire S1 — Investigation Report and Remediation Plan

**Issue under investigation:** `Show supplier details for PO 701337.`
**Date:** 2026-09-12
**Status:** Investigation complete; remediation complete on branch `fix/s1-remediation` (cleanup commit pending)
**Prepared for:** SME review and staged implementation
**Related document:** `Spire — S1 problem writeup for SME review` (2026-09-11)

---

## 0. How to use this document

The issues below are **numbered and ordered**. Each issue is self-contained: it has its own evidence, its own fix, its own blast-radius list, and its own acceptance test. The intent is that we fix **one issue, test it, commit it, then move to the next** — not that we batch all of them.

Two issues (**BUG-1** and **BUG-2**) are unconditionally right regardless of how the SME answers the open questions in §5. They can be started immediately.

Two issues (**BUG-3** and **BUG-4**) have their *mechanism* decided but their *user-facing behaviour* partially depends on the SME's answer. Marked inline.

One issue (**BUG-5**, a classify-stage observation) is **not S1-related** and is listed for completeness only. Do not fix it during this cycle.

**Structure of this document.** The original analysis, evidence and proposed fixes are preserved verbatim. As each bug is fixed, a **Status update** subsection is appended under that bug's §4 entry — it does not replace the original text. New top-level sections (§0.1, §6.1, §8.1, §9) were added below their originals rather than in place.

### 0.1 Progress at a glance

*(Added 2026-09-12 after the third fix. Updated as later fixes landed.)*

| # | Issue | Status | Commit |
|---:|---|---|---|
| BUG-2 | No general un-wireable-include gate in `validate_intent` | ✅ **FIXED** | `97bc8f7` |
| BUG-3 | Planner raises raw `KeyError` for a bad include | ✅ **FIXED** | `acd3f6f` |
| BUG-1 Step 1 | Code-side strip of the un-wireable `Supplier` include | ✅ **FIXED** | `333ea95` |
| BUG-1 Step 2 | Parser prompt rule for "supplier details for PO X" | ✅ **FIXED** | `29737de` |
| BUG-4 sub-part A | Refusal Reason line prefers clean detail | ✅ **FIXED** | `7989d24` |
| BUG-1 Step 3 | Render supplier site and contact in PO answers | ✅ **FIXED** (this commit) | — |
| BUG-4 sub-part B | New `UNSUPPORTED_INCLUDE` flavor | ⏳ deferred | — |
| BUG-5 | Classify stage fires twice | ⏸ out of scope | — |
| Cleanup | Revert `c9c4fb1`; add `.gitignore` entries | ⏳ pending | — |

**Current observable state of the S1 prompt:** `Show supplier details for PO 701337.` **20/20 answers**. S1 is closed. The prompt returns `Supplier: JGA`, `Site: JGA Progress US`, `Contact: Seth Ries`, `Buyer: White, Eleanor` deterministically; no refusals, no crashes. Steps 1 and 2 together closed both failure modes — Step 1 eliminated the crash path by stripping the bad include, Step 2 eliminated the parser's self-declared-refusal attractor by giving the model an explicit rule to land on. Step 3 extended the answer with the two fields the SME asked for in §5.1.

**Refusal-message state after BUG-4 sub-part A:** an include-shaped self-declared refusal (the S1-attractor shape, if it ever fires for a different prompt) now shows the parser's specific diagnosis in the Reason line, not the generic "not the way this question narrows them". Include-shaped refusals whose detail quotes an internal snake_case identifier still fall to the generic sentence; that is the discriminator working as designed.

---

## 1. Executive summary

**The S1 prompt is a one-fetch query. The data lives on the PO header. Spire has the tool that returns it. The parser is not routing the question to that tool.**

Concretely:

- **Fusion proves the data is present.** A curl against `/purchaseOrders?q=OrderNumber=701337` returns `Supplier: 'JGA'`, `SupplierSite: 'JGA Progress US'`, `SupplierContact: 'Ries, Seth'`, `SupplierId: 300000047414635` — all on the PO header itself, no join required.
- **Spire has the tool.** `get_purchase_order_by_id` already projects `Supplier`, `SupplierId`, `SupplierSite` — verified by reading `_PROJECTED_FIELDS` in `purchase_order_by_id.py`.
- **The parser prompt does not cover this case.** There is a rule for `include the buyer` (edge `ASSIGNED_TO` exists). There is no rule for `supplier details for PO X`. The model must guess. It guesses `include: ['Supplier']`, for which no edge exists, and the pipeline breaks in one of two ways.
- **The failure is not a capability gap.** It is a parser-prompt gap, a validator gap, and a defensive-coding gap — three specific, locatable bugs. None requires a new tool or new Fusion endpoint.

**Twenty-run measurement (2026-09-12, live, baseline before any fix):** 9/20 refused, 11/20 crashed, 0/20 answered correctly. The parse output-token count perfectly predicts which outcome fires: `out=3440` → refusal (9/9); `out=3741` → crash (11/11). Zero exceptions.

---

## 2. Evidence

All raw evidence is on file. This section cites each source and states what it proves.

### 2.1 Fusion curl — the data exists on the PO header

**Source:** `curl` output captured 2026-09-12.

**First curl (unfiltered, no `fields=`):**

```
totalResults: 1
{'POHeaderId': 300000081255594, 'OrderNumber': '701337', 'StatusCode': 'OPEN',
 'Status': 'Open', 'BuyerId': 300000076218768, 'Buyer': 'White, Eleanor',
 'SupplierId': 300000047414635, 'Supplier': 'JGA',
 'SupplierPartyId': 300000047414633, 'SupplierSiteId': 300000076246906,
 'SupplierSite': 'JGA Progress US', 'SupplierContactId': 300000076246927,
 'SupplierContact': 'Ries, Seth', ...}
```

**Second curl (`fields=POHeaderId,OrderNumber,Supplier,SupplierId,SupplierSite,SupplierContact,Status,StatusCode`):**

Returns HTTP 200 with a clean subset of exactly those fields. **No 400, no error.** The projection is accepted.

**Proves:**

1. `Supplier`, `SupplierId`, `SupplierSite`, `SupplierContact`, `SupplierContactId`, `SupplierContactDisplayName` are all fields on the `/purchaseOrders` header.
2. They are projectable via `?fields=`.
3. No second call to `/suppliers` is needed to answer "supplier details for PO X".
4. The question is a **one-fetch query**.

### 2.2 The existing tool already projects the fields

**Source:** `src/spire/mcp_server/tools/purchase_order_by_id.py`, `_PROJECTED_FIELDS` list.

```python
_PROJECTED_FIELDS = [
    "POHeaderId", "OrderNumber", "Status", "StatusCode",
    "Supplier", "SupplierId", "Buyer", "BuyerId",
    "SupplierSite",           # <-- present
    "Ordered", "Total", "TotalTax", "CurrencyCode", "PaymentTerms",
    "ShipToLocationCode", "BillToLocation", "OrderDate", "Description",
    "CreatedBy", "CreationDate", "LastUpdatedBy", "LastUpdateDate",
]
```

The tool resolves the PO via `q=OrderNumber='X'` (tries OrderNumber first, POHeaderId fallback). Given `Show supplier details for PO 701337.`, a call to `get_purchase_order_by_id(701337)` would return `Supplier: 'JGA'`, `SupplierSite: 'JGA Progress US'`, `SupplierId: 300000047414635` — the answer to the user's question.

**Proves:** No new tool is required. The tool exists, is routed to by the `PurchaseOrder` + `by_id` filter today, and returns the fields in question.

**Not present in the projection but present on the endpoint (per curl):** `SupplierContact`, `SupplierContactId`, `SupplierContactDisplayName`. These are the fields the SME needs to decide on (see Open Question §5.1).

### 2.3 Standalone planner traceback — where the crash originates

**Source:** Direct `generate_plan()` call with `Intent(target_entity='PurchaseOrder', filters=[{'type':'by_id','value':'701337'}], include=['Supplier'])`.

```
Traceback (most recent call last):
  File ".../planner.py", line 466, in generate_plan
    edge = find_edge(previous_entity, include_entity)
  File ".../lookup.py", line 134, in find_edge
    raise KeyError("No edge from 'PurchaseOrder' to 'Supplier'")

During handling of the above exception, another exception occurred:

  File ".../planner.py", line 470, in generate_plan
    edge = find_edge(root_entity, include_entity)
  File ".../lookup.py", line 134, in find_edge
    raise KeyError("No edge from 'PurchaseOrder' to 'Supplier'")

During handling of the above exception, another exception occurred:

  File ".../planner.py", line 472, in generate_plan
    raise KeyError(
        "No edge to include 'Supplier': it is neither a child of "
        "'PurchaseOrder' (chain) nor of 'PurchaseOrder' (sibling under "
        "the root)."
    )
```

**Proves:**

1. The crash is in **Block 3 (includes)** of `generate_plan` — planner.py line 466–472.
2. **Both hops fail** — the chain hop (`PurchaseOrder → Supplier`) and the sibling hop (`PurchaseOrder → Supplier` again, since root == target here).
3. The KG declares no edge from `PurchaseOrder` to `Supplier`. (`HAS_PURCHASE_ORDER` is `Supplier → PurchaseOrder` — the wrong direction.)
4. `find_edge()` raises `KeyError`; `generate_plan` catches it, tries the sibling hop, and re-raises a `KeyError` with the compounded message. This is the string that reaches `plan_node` and, from there, `run_graph.py` stderr.

### 2.4 Lifecycle paraphrase — the path that works

**Source:** `python scripts/promptkit.py --run --prompt "Show ordered, received, invoiced and paid amounts for PO 701337 with supplier details."`

Key lines:

```
Router: modules=['procurement', 'supplier']
[DBG raw-intent] target='PurchaseOrder' include=[] filters=['lifecycle_status']
[DBG validate] refusal=None post-validate include=[]
Plan:
  Step 1: get_purchase_order_lifecycle_status
    tool_args: {'po_number': '701337'}
```

Output included:

```
Supplier setup:
  - Supplier JGA (1254) is ACTIVE and Spend Authorized.
  - Site JGA Progress US is ACTIVE, purchasing enabled, pay enabled.
  - Invoice matching is 3 Way against Receipt.
  - PO payment terms (Net 30) differ from the site default (2/10 Net 30).
```

**Proves:**

1. The router classifies the paraphrased question as `['procurement', 'supplier']` — **the same modules the S1 wording gets** (see §2.5).
2. The parser emits `include=[]` on this wording — **it does not attempt `include=['Supplier']`** — because the `lifecycle_status` rule in the parser prompt explicitly says *"Emit no other filters and no includes."*
3. The supplier details (JGA, site, matching, terms) reach the user as part of the lifecycle answer.
4. The data path exists.

**Interpretation:** The paraphrase works because the parser prompt has an explicit rule for it that includes a strong "no includes" instruction. The S1 wording has no such rule; the model falls back to the nearest pattern-match (`include the buyer → include Buyer`), substitutes `Supplier`, and produces a shape that cannot be planned.

### 2.5 S1 twenty-run batch — measured behaviour

**Source:** `s1_full_20runs.txt`, captured 2026-09-12, `gemini-3.5-flash`, temperature 0.0.

| Run | Classify out | Parse out | Outcome |
|----:|-------------:|----------:|---------|
| 1 | 315 / 121 | 3440 | refusal |
| 2 | 315 / 121 | 3440 | refusal |
| 3 | 121 / 315 | 3741 | crash |
| 4 | 121 / 121 | 3741 | crash |
| 5 | 121 / 121 | 3741 | crash |
| 6 | 121 / 315 | 3440 | refusal |
| 7 | 121 / 121 | 3440 | refusal |
| 8 | 315 / 315 | 3440 | refusal |
| 9 | 121 / 121 | 3440 | refusal |
| 10 | 121 / 315 | 3741 | crash |
| 11 | 121 / 121 | 3741 | crash |
| 12 | 121 / 121 | 3741 | crash |
| 13 | 315 / 315 | 3440 | refusal |
| 14 | 121 / 315 | 3440 | refusal |
| 15 | 121 / 315 | 3741 | crash |
| 16 | 315 / 315 | 3741 | crash |
| 17 | 121 / 315 | 3741 | crash |
| 18 | 315 / 121 | 3741 | crash |
| 19 | 121 / 121 | 3440 | refusal |
| 20 | 315 / 315 | 3741 | crash |

**Totals:** 9 refusals, 11 crashes, 0 correct answers.

**Perfect correlation:** `parse out=3440` → refusal (9/9). `parse out=3741` → crash (11/11). No exceptions.

**Refusal-path raw-intent** (from the `Reason:`/detail block):

```
Reason:   I can look up suppliers, but not the way this question narrows them.

Solution: Narrow by country, status or name instead.

Example:  active suppliers in US
  (refusal: unsupported_filter — Cannot retrieve supplier details for a
   specific purchase order because Supplier is not an allowed include on
   PurchaseOrder, and Supplier cannot be filtered by purchase order number.)
```

**Crash-path raw-intent** (from the `[DBG ...]` lines):

```
[DBG raw-intent] target='PurchaseOrder' include=['Supplier'] filters=['by_id']
[DBG validate] refusal=None post-validate include=['Supplier']
ERROR: plan: "No edge to include 'Supplier': ..."
```

**Proves:**

1. **The two outcomes are bimodal.** Not a smooth distribution — two discrete completion shapes, perfectly separated by output token count.
2. **The parser knows the rule.** On the refusal path, its own `unanswerable_reason` reads *"Supplier is not an allowed include on PurchaseOrder"* — accurate, specific, actionable. The rule is not missing; it is intermittently not applied.
3. **`validate_intent` does not catch the bad include.** `refusal=None` after validation, with `include=['Supplier']` still present. Confirms the writeup's "Fact B" — no general un-wireable-include gate.
4. **The router classifies the S1 wording as `['procurement', 'supplier']` — identical to the working paraphrase.** So the parse prompt the model sees is the same in both cases. The difference is entirely in what the model does with that prompt, and that difference correlates with whether the prompt *contains an explicit rule for the case*.
5. **The "8,000-token ceiling" framing in the original writeup is not supported.** 3,440–3,741 output tokens is 43–47% of the ceiling. The degenerate-parse guard (`out_tokens >= LLM_MAX_OUTPUT_TOKENS * 0.95 and finish_reason != "stop"`) does not fire and should not fire. The instability is a **reasoning-path divergence**, not a ceiling effect.

### 2.6 `intent_validation.py` — the missing general gate

**Source:** `src/spire/nl_parser/intent_validation.py`, Step 3b, verbatim:

```python
if "Site" in intent.include:
    return Refusal(
        flavor=RefusalFlavor.UNSUPPORTED_OPERATION,
        detail="Supplier sites aren't available as a standalone listing.",
        offending_entity="SupplierSiteListing",
    )
```

**Proves:** The gate is hardcoded to a single entity (`Site`). There is no corresponding check that the requested `include` has a declared edge from the target entity (or its root). `include=['Supplier']` on a `PurchaseOrder` intent passes through untouched. This is exactly why the crash path reaches the planner.

### 2.7 `capability.py` — the message layer's misclassification

**Source:** `src/spire/nl_parser/capability.py`, docstring of `_reason_line`, plus the observed refusal output.

The parser declared `unsupported_filter` on the refusal path. The user-facing message that follows is generated by `capability.py` keyed on flavor. For `UNSUPPORTED_FILTER` + `Supplier`:

```python
_FILTER_GUIDANCE = {
    "Supplier": (
        "Narrow by country, status or name instead.",
        "active suppliers in US",
    ),
    ...
}
```

**Proves:** The message and example offered are for a **filter** problem (narrowing a supplier list). The parser's own diagnosis was an **include** problem ("Supplier is not an allowed include on PurchaseOrder"). The five `RefusalFlavor` values have no home for "the entity is fine but cannot be included on the target", so the model picks the nearest fit and the message layer renders the wrong advice. This is the same defect class `capability.py`'s own docstring documents for `UNSUPPORTED_FIELD`.

### 2.8 Classify-stage double-call (non-S1 observation)

**Source:** Every run in `s1_full_20runs.txt`.

Each run shows the classify call firing **twice** on identical `in=551` bytes, with different output token counts (121 and 315, in either order). The final `Router: modules=['procurement', 'supplier']` line is the same regardless of which attempt's result is kept. The two classify attempts do not correlate with the parse outcome (I checked all four combinations).

**Not S1.** Recorded for completeness. Do not fix during this cycle. See §7.

---

## 3. Analysis and decision points

### 3.1 What kind of problem is this?

The original writeup framed it as *"LLM non-determinism on identical input, so a prompt edit cannot reliably fix it."* The evidence supports a more precise framing:

**The parser is not failing at random. It is falling into one of two stable attractors, and which attractor it lands in depends on whether the parser prompt contains an explicit rule for the case at hand.**

- When the case is covered by an explicit rule (as the lifecycle paraphrase is): the model follows the rule, `include=[]`, both paths agree, the answer runs.
- When the case is *not* covered (as the S1 wording is): the model has to guess, and the guess is unstable across completions.

This reframing matters because it changes the fix. If the problem were "unfixable LLM variance", the only options would be (a) accept the failure, or (b) add a deterministic code-side guard. If the problem is "prompt coverage gap", the options include (c) **close the gap**.

(c) is the correct fix. Code-side guards (a/b) are the safety nets — necessary, but secondary.

### 3.2 Why prompt-side fix has a risk, and the code-side workaround

The parser prompt is at **19,731 characters**. Adding text to it carries the risk the writeup's own notes already record: another batch of prompts tipping into degenerate parse. The `parse()` function's existing commentary says as much:

> *the parser prompt is at its token ceiling and any added prompt/schema text tips specific phrasings into degenerate (MAX_TOKENS) generation. A post-parse string check sidesteps that entirely.*

The precedent for a code-side, prompt-free fix already exists in the codebase: `correct_include_from_prompt` and `add_child_include_from_prompt` in `vocabulary.py` deterministically correct the include list after the LLM, from the raw prompt, with zero LLM-visible text. That is the pattern to follow.

**Decision (Pending SME — see §5.2):**

- **Option A — prompt bullet.** Add one bullet to the parser preamble in the same shape as the existing `include the buyer` rule, documenting that supplier details come from the PO header. Correct long-term. Risks destabilizing other prompts.
- **Option B — code-side strip.** In `parse()`, after the LLM, if `intent.target_entity == 'PurchaseOrder'` and `intent.include == ['Supplier']`, strip the `Supplier` from the include list. Zero prompt change. Deterministic. Minimal blast radius. Requires a comment explaining why.
- **Option C — both.** Do B now (safe, immediate), plan A for a later cycle with a full regression run across `scripts/prompts/*.txt`.

**Recommended: Option C, with B shipped first.** The user-facing bug is fixed immediately and safely; the prompt is brought into line in a follow-up with proper regression coverage. **This is the path taken.** Option B shipped as `333ea95` (BUG-1 Step 1); Option A shipped as `29737de` (BUG-1 Step 2).

### 3.3 Where each fix belongs

| # | Bug | Layer | Fix location |
|---|---|---|---|
| BUG-1 | Parser prompt lacks coverage for "supplier details for PO" | Parser post-processing | `src/spire/nl_parser/parser.py` (parse()) |
| BUG-2 | `validate_intent` has no general un-wireable-include gate | Validator | `src/spire/nl_parser/intent_validation.py` (Step 3b) |
| BUG-3 | Planner Block 3 raises raw `KeyError` | Planner | `src/spire/planner/planner.py` (line 466–472) |
| BUG-4 | Refusal message names wrong problem ("narrow by...") | Capability rendering | `src/spire/nl_parser/capability.py` |
| BUG-5 | Classify stage fires twice | Router | `src/spire/nl_parser/router.py` (not S1) |

### 3.4 Precedence

**BUG-2 and BUG-3** are the safety nets. Either one alone prevents the crash. Both are unconditionally correct. Ship first.

**BUG-1** is the actual fix — makes the S1 prompt answer correctly. Ships second (after BUG-2, since BUG-2's gate is the backstop that makes BUG-1's code path *refusable* if the strip ever fails).

**BUG-4** is cosmetic-but-important. Ships third, once the pipeline is behaving, because the message never reaches the user if BUG-1 is fixed (the S1 prompt now answers instead of refusing).

**BUG-5** is out of scope. Ships last, in a separate cycle.

---

## 4. Proposed issues, each with its own test

### BUG-2 — Add a general un-wireable-include gate to `validate_intent`

**Severity:** High. Directly prevents the S1 crash.
**Blast radius:** Any intent with an `include` whose target entity has no declared edge.

**Evidence:** §2.3, §2.6, §2.5.

**Root cause:** Step 3b of `intent_validation.py` checks for `Site` only. There is no equivalent check for any other entity.

**Fix (proposed):**

Replace:

```python
if "Site" in intent.include:
    return Refusal(
        flavor=RefusalFlavor.UNSUPPORTED_OPERATION,
        detail="Supplier sites aren't available as a standalone listing.",
        offending_entity="SupplierSiteListing",
    )
```

with a general loop:

```python
for include_entity in intent.include:
    # Try the chain hop first (target -> include), then the sibling
    # hop (root -> include). Either succeeds => the include has a
    # declared edge. Otherwise: refuse with the parser's own reason.
    has_edge = False
    for from_entity in (entity, entity):  # both hops start from the target here
        # (In practice, we need the same lookup the planner does.)
        if menu.has_edge(from_entity, include_entity):
            has_edge = True
            break
    if not has_edge:
        return Refusal(
            flavor=RefusalFlavor.UNSUPPORTED_OPERATION,
            detail=f"{include_entity} is not a valid include on {entity}.",
            offending_entity=include_entity,
        )
```

The exact API of `menu.has_edge` would be new — `KGMenu` doesn't currently expose an edge-check. It has `is_known_entity`, `is_valid_target`, `is_known_filter`, `is_known_field`, `available_columns`. **Adding `has_edge(from_entity, to_entity)` to `KGMenu` is part of this fix.**

The `Site` gate can be preserved for its distinct message, or its message merged into the general case. Decision point: see §5.3.

**Files touched:**

- `src/spire/nl_parser/intent_validation.py` — the gate itself
- `src/spire/nl_parser/vocabulary.py` — add `has_edge()` to `KGMenu`
- `tests/test_nl_parser.py`, `tests/test_nl_parser_integration.py` — add regression cases
- No KG change, no schema change, no tool change

**Acceptance test:**

1. Direct `validate_intent` unit test with `Intent(target_entity='PurchaseOrder', include=['Supplier'])` returns a `Refusal` with `offending_entity='Supplier'`.
2. The same intent with `include=['Buyer']` (which HAS an edge) returns `None` (valid).
3. `include=['Site']` still returns the existing `SupplierSiteListing` message (or the equivalent).
4. Full `scripts/prompts/08_lifecycle.txt` still runs — no regression on the working lifecycle paths.
5. Re-run the 20-run S1 batch: crash count drops to 0. Refusals may still occur (BUG-1 not yet fixed).

**Commit boundary:** one PR, one commit. Small enough to review at a glance.

#### Status update (2026-09-12) — ✅ FIXED

**Commit:** `97bc8f7` on `fix/s1-remediation`.

**Files actually changed:**

- `src/spire/nl_parser/vocabulary.py` — `KGMenu` gained `edge_pairs`, `edge_traversal_targets`, `has_edge()`, `edge_traversal_target()`; `load_kg_menu()` populates both
- `src/spire/nl_parser/intent_validation.py` — Step 3b generalised
- `tests/test_bug2_include_gate.py` — new (17 tests)
- `scripts/verify_bug2.py` — new (standalone probe)

**What was learned during the fix (not in the original proposal):**

The first draft of the general gate broke 5 pre-existing tests in `tests/test_nl_parser.py`. Those tests use hand-built `KGMenu` fixtures with `edge_pairs=set()` — they populate only the fields needed for parser/Intent logic, never edges. The gate consulted `edge_pairs`, found it empty, and refused every include.

The fix: **the gate is a no-op when `menu.edge_pairs` is empty**, matching the contract `KGMenu` already follows for `field_synonyms`, `entity_synonyms`, and `entity_columns` (all treated as "absent => feature disabled", not "error"). The `Site` string check is a hardcoded string test and does NOT depend on edges, so it still fires.

A second design point settled during the fix: the gate **simulates the planner's Block 2** before running its include chain. An edge-traversal filter (`has_open_PO`, `has_no_recent_invoices`, ...) updates the "previous entity" the first include chains from — without the simulation, `Supplier + has_open_PO + include=['Buyer']` would be falsely refused, because `Supplier → Buyer` has no edge but `PurchaseOrder → Buyer` does. The gate now walks that hop.

**Also confirmed by the fix, broader than the original bug:** `HAS_CLASSIFICATION` (Supplier → Classification) has an edge but its only tool (`search_suppliers_by_classification`) is a *reverse filter* — it needs a `classification` arg the executor never supplies. Before the fix, that shape reached the executor and crashed on a missing required arg. The gate now refuses it with `offending_entity='Classification'`. Same defect class as S1, different trigger.

**Verification (2026-09-12):**

- `tests/test_bug2_include_gate.py`: **17 passed**
- `tests/test_nl_parser.py`: **35 passed** (5 previously-failing tests now pass)
- Full suite: **934 passed**, 18 deselected
- 20-run S1 batch: **crash count 11 → 0** (all runs now produce refusals — clean messages, not crashes)
- `verify_bug2.py`: rows [1], [4c], [5a], [5b] flip from PASSED to REFUSED; rows [2], [3], [4a], [4b], [6] unchanged

---

### BUG-3 — Planner Block 3 should not raise a raw `KeyError`

**Severity:** High (defense in depth). If BUG-2 has any gap, this catches it.
**Blast radius:** Any future intent with an include that slips past BUG-2.

**Evidence:** §2.3.

**Root cause:** `planner.py` line 472 raises `KeyError`. `plan_node` (in `graph/pipeline.py`) wraps it as `{"error": f"plan: {exc}"}` without setting `plan_refusal=True`, so `run_graph.py` treats it as a hard failure and prints to stderr.

**Fix (proposed):**

In `planner.py` Block 3, replace the final `raise KeyError(...)` with a structured `RefusalError`, mirroring the pattern used elsewhere in `generate_plan`:

```python
from spire.nl_parser.result import Refusal, RefusalError, RefusalFlavor

try:
    edge = find_edge(previous_entity, include_entity)
    include_iter_output = previous_output_name
except KeyError:
    try:
        edge = find_edge(root_entity, include_entity)
    except KeyError:
        raise RefusalError(
            Refusal(
                flavor=RefusalFlavor.UNSUPPORTED_OPERATION,
                detail=(
                    f"{include_entity} is not a valid include on "
                    f"{previous_entity} or {root_entity}."
                ),
                offending_entity=include_entity,
            )
        )
    include_iter_output = root_output_name
```

`plan_node` already catches `RefusalError` and routes `exc.refusal` into `state["refusal"]` — that is the same channel the parser's refusals use, and it renders through `capability_message`. So this fix makes the S1 crash-path render as a clean refusal (until BUG-1 eliminates it entirely).

**Files touched:**

- `src/spire/planner/planner.py` — Block 3, the `raise KeyError` at line 472
- `tests/test_planner.py` — add a case for the un-wireable include

**Acceptance test:**

1. Direct `generate_plan` call with the failing intent raises `RefusalError` (not `KeyError`).
2. `plan_node` receives it and returns `{"refusal": ...}` — no `error`, no `plan_refusal` flag needed.
3. `run_graph.py` prints the refusal to stdout, exit code 4.
4. Re-run the standalone repro from §2.3: no traceback, clean refusal.
5. Full test suite passes.

**Commit boundary:** one PR. Independent of BUG-2.

#### Status update (2026-09-12) — ✅ FIXED

**Commit:** `acd3f6f` on `fix/s1-remediation`.

**Files actually changed:**

- `src/spire/planner/planner.py` — Block 3, the inner `raise KeyError` at line 472 replaced by `RefusalError(Refusal(flavor=UNSUPPORTED_OPERATION, ...))`. The outer control flow (chain hop then sibling hop) is unchanged.
- `tests/test_bug3_planner_include.py` — new (6 tests)
- `scripts/verify_bug3.py` — new (standalone probe)

**What was learned during the fix:** `plan_node` already catches `RefusalError` and routes `exc.refusal` into `state["refusal"]` — the same channel a parser decline uses. No change was needed in the pipeline, only in the planner's raise. This is the shortest fix of the three.

**Verification (2026-09-12):**

- `tests/test_bug3_planner_include.py`: **6 passed**
- Full suite: **940 passed**, 18 deselected (934 + 6)
- `verify_bug3.py` after fix: [1] `KeyError → RefusalError`; [3] `KeyError → RefusalError` (offending=Supplier, correct element in a multi-include list); [4] `{'error': ...}` with `plan_refusal = <MISSING>` → `{'refusal': Refusal}`; [2] and [5] unchanged

**Reachability note (added by the fix, not in the original):** after BUG-2's gate, this path is unreachable for parser-generated intents. It is now a **layered backstop** for two cases the gate cannot reach — hand-built `Intent`s (the planner is a public API; `run_plan.py` and tests construct Intents directly, bypassing the parser), and future KG drift (a KG change that removes an edge a working parser include still assumes).

---

### BUG-1 — Close the parser coverage gap for "supplier details for PO X"

**Severity:** High. This is the actual fix that makes S1 answer correctly.
**Blast radius:** Any `PurchaseOrder` + `by_id` intent that acquires a bad `include=['Supplier']` from the LLM.

**Evidence:** §2.1, §2.2, §2.4, §2.5.

**Root cause:** The parser prompt has no rule for "supplier details for PO X". The model pattern-matches against the `include the buyer` rule and emits `include: ['Supplier']`, for which no edge exists.

**Fix (proposed — Option C from §3.2):**

**Step 1 (immediate, safe): code-side strip in `parse()`.**

Add to `parse()` in `parser.py`, alongside the other post-parse correction passes (`expand_field_synonyms`, `correct_include_from_prompt`, `add_child_include_from_prompt`):

```python
# S1: the parser sometimes emits include=['Supplier'] on a PurchaseOrder
# intent, because 'supplier details for PO X' looks like 'include the
# buyer'. There is no PurchaseOrder -> Supplier edge, and none is
# needed: the supplier name, number, site and contact all ride on the
# PO header itself (verified by curl against /purchaseOrders). Strip
# the invalid include and let the header fetch answer the question.
# Deterministic, KG-grounded, after the LLM — same pattern as
# correct_include_from_prompt. See scripts/prompts for the S1 repro.
if (
    intent.target_entity == "PurchaseOrder"
    and "Supplier" in intent.include
    and not menu.has_edge("PurchaseOrder", "Supplier")
):
    intent.include = [e for e in intent.include if e != "Supplier"]
```

This depends on `menu.has_edge` existing — which BUG-2 also adds. Do BUG-2 first, then BUG-1 Step 1.

**Step 2 (follow-up, planned): parser prompt bullet.**

Add one bullet to the parser preamble (in `context/procurement/`, a new file like `b_po_supplier_details.sysprompt`), in the shape of the existing `b_buyer_include.sysprompt`:

> *'supplier details for PO X' / 'show the supplier on PO X' / 'who is the supplier on PO X' → target_entity 'PurchaseOrder' with a 'by_id' filter. Do NOT add 'Supplier' to include. The supplier name, supplier number, supplier site and supplier contact are projected directly from the PO header by the by_id fetcher.*

This must be accompanied by:

- A re-run of `python scripts/build_parser_context.py` (it verifies byte-equality against the reference literal; adding a bullet is a legitimate change that requires re-approval of `_EXPECTED_LITERAL_SHA` in that script).
- A full regression across `scripts/prompts/*.txt` to confirm the token-ceiling concern doesn't materialize. If it does, revert Step 2 and rely on Step 1 alone.

**Step 3 (optional): add `SupplierContactDisplayName` to the by_id projection.**

Depends on Open Question §5.1. If the SME wants the contact name in the answer, add it to `_PROJECTED_FIELDS` in `purchase_order_by_id.py`. Three-line additive change.

**Files touched (Step 1 only):**

- `src/spire/nl_parser/parser.py` — post-parse strip
- `tests/test_nl_parser.py` — a case asserting the strip

**Files touched (Step 2, later):**

- `src/spire/nl_parser/context/procurement/b_po_supplier_details.sysprompt` (new)
- `src/spire/nl_parser/context/order.manifest` — add the new block
- `scripts/build_parser_context.py` — bump `_EXPECTED_LITERAL_SHA`
- `tests/test_parser_context_assembly.py` — the byte-equality oracle will need updating
- `src/spire/nl_parser/context_assembly.py` — the `_SYSTEM_PROMPT_PREAMBLE` literal (used as an oracle) will need a matching update

**Files touched (Step 3, optional):**

- `src/spire/mcp_server/tools/purchase_order_by_id.py` — add the contact field
- `tests/test_purchase_order_detail_tool.py` — assert the new field

**Acceptance test:**

1. **Step 1:** Re-run the 20-run S1 batch. **Expected: 20/20 answer correctly.** No refusals, no crashes.
2. Confirm the S1 answer contains at least `Supplier` and `SupplierSite` (and `SupplierContact` if Step 3 is applied).
3. Full test suite passes.
4. **Step 2 (after Step 1 ships and holds):** re-run `scripts/prompts/01_supplier.txt`, `02_purchase_order.txt`, `08_lifecycle.txt`, `11_column_vocabulary.txt` — no regressions, no new degenerate parses.
5. **Step 3 (if applied):** the same 20-run batch prints `JGA Progress US` and `Seth Ries`.

**Commit boundary:** Step 1 is its own PR. Step 2 is a separate PR gated on Step 1's stability. Step 3 is separate again.

#### Status update (2026-09-12) — ✅ Step 1 FIXED

**Commit:** `333ea95` on `fix/s1-remediation`.

**Files actually changed (Step 1 only):**

- `src/spire/nl_parser/vocabulary.py` — new helper `strip_po_supplier_include(target, include, menu)` and the module-level pair `_STRIP_INCLUDE_WHEN_NO_EDGE = ("PurchaseOrder", "Supplier")`. The helper is **KG-gated**: it fires only if `menu.has_edge("PurchaseOrder", "Supplier")` is False, so if a future KG change declares the edge the strip becomes a no-op — self-retiring, no code change needed.
- `src/spire/nl_parser/parser.py` — imports and calls `strip_po_supplier_include` after `add_child_include_from_prompt`, before `validate_intent`. The three S1 debug prints from `c9c4fb1` are preserved verbatim.
- `tests/test_bug1_po_supplier_strip.py` — new (13 tests: 7 primitive on the helper, 6 end-to-end via a mock LLM)
- `scripts/verify_bug1.py` — new (standalone probe, deterministic via a mock LLM)

**What was learned during the fix:**

The live 20-run S1 batch after the strip shows the fix works where the parser emits the bad include, but the model is still **bimodal**: 7/20 answer, 13/20 refuse. The refusals are the parser's **self-declared-refusal attractor** — the model emits `unanswerable=true` with a reason and never produces an `Intent`, so the strip has nothing to strip from. **Step 2 (the parser prompt bullet) is what addresses the self-declared-refusal mode.** The strip closes the crash path and the `include=['Supplier']` path; Step 2 closes the third path.

**Live S1 batch after this fix (20 runs):**

- **Crashes:** 0
- **Refusals:** 13 (parser self-declared — Step 2's target)
- **Answers (JGA, White Eleanor):** 7

**Progress across the branch (20-run S1 batch):**

| Metric | Baseline | After BUG-2 | After BUG-3 | After BUG-1 Step 1 |
|---|---:|---:|---:|---:|
| Crashes | 11 | 0 | 0 | **0** |
| Refusals | 9 | 20 | 20 | **13** |
| Answers | 0 | 0 | 0 | **7** |

**Verification (2026-09-12):**

- `tests/test_bug1_po_supplier_strip.py`: **13 passed**
- Full suite: **953 passed**, 18 deselected (940 + 13)
- `verify_bug1.py` after fix: [1]-[3] REFUSED → OK with `Supplier` stripped and survivors preserved; [4]-[8] controls unchanged
- Canary `scripts/prompts/00_dipstick.txt`: 6/6 pass

**Presentation gap noticed during the fix (not part of BUG-1):** the typed `PurchaseOrder` record renders `Supplier` but not `SupplierSite`, even though `SupplierSite: 'JGA Progress US'` is present in the raw output. This is a **synthesizer schema** issue (`PurchaseOrderRecord` in the synthesizer does not carry `supplier_site`), separate from BUG-1. Recorded here for a future cycle; not addressed in this commit.

#### Status update (2026-09-12) — ✅ **Step 2 FIXED — S1 CLOSED**

**Commit:** `29737de` (BUG-1 Step 2) on `fix/s1-remediation`.

**Files changed (Step 2 only):**

- `src/spire/nl_parser/context/procurement/b_po_supplier_details.sysprompt` — new. One bullet, 290 chars, added at position 17 in the manifest (immediately after `b_buyer_include.sysprompt`).
- `src/spire/nl_parser/context/order.manifest` — one line added. Now 49 blocks.
- `src/spire/nl_parser/context_assembly.py` — `_SYSTEM_PROMPT_PREAMBLE` literal extended with the matching fragment block, applied via the script below. Diff is exactly five lines.
- `scripts/apply_bug1_step2_context_assembly.py` — new. One-shot, idempotent insertion script. Inserted the fragment after `add 'Buyer' to include.\n`.
- `tests/test_bug1_step2_prompt_coverage.py` — new. Six tests: block exists, starts with a bullet, carries the expected phrasing, manifest lists it, manifest position is right, assembled preamble contains the rule.
- `tests/test_parser_context_assembly.py` — `_EXPECTED_BLOCK_COUNT` bumped from 48 to 49 (the byte-equality tripwire correctly flagged the manifest change).

**Verification:**

- `tests/test_parser_context_assembly.py`: **5/5 passed** — the byte-equality oracle confirms the literal and the files agree byte for byte.
- `tests/test_bug1_step2_prompt_coverage.py`: **6/6 passed**.
- Regression across the four affected prompt sets: **134/134 passed** — `01_supplier` (40), `02_purchase_order` (10), `08_lifecycle` (31), `11_column_vocabulary` (53). No new refusals, no degenerate parses.
- Live S1 batch (20 runs): **20/20 answered, 0 crashes, 0 refusals.**

**Progress across the branch — 20-run S1 batch:**

| Metric | Baseline | BUG-2 | BUG-3 | Step 1 | **Step 2** |
|---|---:|---:|---:|---:|---:|
| Crashes | 11 | 0 | 0 | 0 | **0** |
| Refusals | 9 | 20 | 20 | 13 | **0** |
| Answers | 0 | 0 | 0 | 7 | **20** |

**S1 status: CLOSED.** The prompt `Show supplier details for PO 701337.` answers correctly and deterministically.

**What this does NOT close (still open on the branch at the time of this commit):**

- **BUG-4** (sub-part A, later shipped as `7989d24`) — the refusal MESSAGE for include-shaped problems is still the generic `UNSUPPORTED_OPERATION` fallback. Not observable on S1 anymore (S1 answers instead of refusing), but still a defect for other prompts that reach the refusal path.
- **BUG-1 Step 3** (shipped in the next commit) — adding `SupplierContactDisplayName` to the `by_id` projection and rendering the site and contact in the answer.
- **BUG-5** — out of scope.
- **Cleanup commit** — reverting the temporary debug instrumentation from `c9c4fb1` and adding `.gitignore` entries for `isolation/`, `s1_*.txt`, `test_bug1*.txt`, `verify_bug*.txt`.

**Note on the tripwire:** the byte-equality test file was updated as part of this fix, not as a separate cleanup. The `_EXPECTED_BLOCK_COUNT` constant is the intended notification mechanism — the manifest change moved the count from 48 to 49, the test failed loudly, and the constant was bumped. This is the tripwire working as designed, documented in the test's own docstring. It is not a workaround.

#### Status update (2026-09-12) — ✅ Step 3 FIXED

**Commit:** this commit on `fix/s1-remediation`.

**Files changed:**

- `src/spire/mcp_server/tools/purchase_order_by_id.py` — `SupplierContactDisplayName` added to `_PROJECTED_FIELDS`.
- `src/spire/synthesizer/p2p.py` — `supplier_site` and `supplier_contact` added to `PurchaseOrderRecord` (both default `""`); populated in `build_purchase_order_records` and `build_po_with_children`.
- `scripts/display_formatters.py` — `Site` and `Contact` columns added to the `PurchaseOrderResponse` branch, conditional on at least one row carrying a value (same pattern as `Buyer`).
- `tests/test_bug1_step3_supplier_details.py` — new (12 tests, all three layers).
- `scripts/verify_bug1_step3.py` — new (standalone probe, added before the fix).

**Answers SME §5.1 option (c) — add the contact AND fix the site rendering gap.** Both gaps were demonstrated by the Step 3 probe (`verify_bug1_step3.py`), and both were already visible in Step 1's own §4 finding: the tool fetched `SupplierSite` but the synthesizer dropped it; the tool never fetched the contact at all.

**What was learned during the fix:**

The probe confirmed the shape the handoff had hedged on — Step 3 is the **medium** variant (tool + synthesizer + display), not the small one (tool + display). `PurchaseOrderRecord` carried neither field, so the synthesizer is the middle layer that both ends of the pipeline pass through. Both of the synthesizer's PO builders instantiate the record by hand; touching only one leaves the other path silently without the new fields, which is why the tests pin both.

The field additions default to `""` rather than being required. That matches `supplier_name` / `status` on the same record, and keeps the record constructible without them — the existing tests that instantiate `PurchaseOrderRecord` directly did not need updating, and any future PO shape that does not carry a site or contact degrades to an empty string rather than a validation failure.

The prompt block for `PurchaseOrder` was deliberately NOT extended. The parser prompt is at its token ceiling (documented in the handoff's §7) and the new fields reach the answer through the two local builders, not through the LLM. An LLM path that misses them produces `""` and the display omits the column — the same behaviour as today, which is the right failure mode.

**Verification (2026-09-12):**

- `tests/test_bug1_step3_supplier_details.py`: **12 passed**
- Full suite: **979 passed**, 18 deselected (967 + 12)
- Canary `scripts/prompts/00_dipstick.json`: 6/6 pass
- Live S1 prompt `python scripts/promptkit.py --run --prompt "Show supplier details for PO 701337."` — answer now shows `Site  JGA Progress US` and `Contact  Seth Ries` in the PO block, in addition to `Supplier  JGA` and `Buyer  White, Eleanor`.
- `verify_bug1_step3.py` after fix: all four sections green — [A] both fields in `_PROJECTED_FIELDS`; [B] both fields on `PurchaseOrderRecord`; [C] both columns referenced by the display; [D] round-trip through `build_purchase_order_records` and `_format_synthesized` preserves both.

---

### BUG-4 — Refusal message names the wrong problem

**Severity:** Medium. Cosmetic-once-BUG-1-lands, high-visibility-until-then.
**Blast radius:** Any `unsupported_filter` refusal where the underlying issue is an *include* problem, not a *filter* problem.

**Evidence:** §2.7.

**Root cause:** Five `RefusalFlavor` values, no home for "the entity is fine but cannot be included on the target". The model picks the nearest fit (`unsupported_filter`) and `capability.py` renders filter guidance keyed on `Supplier`.

**Fix (proposed):** Two sub-parts, and both are needed.

**Sub-part A: use the parser's own `detail` when the flavor's structured fields are absent.** `capability.py`'s `_reason_line` already does this for `UNSUPPORTED_FIELD` — its docstring records the same defect pattern:

> *Every one of those was discarded in favour of "not the way this question narrows them". Throwing away a correct diagnosis to print a wrong one is the UX-01 defect in a second location; this branch is that fix.*

The same reasoning applies to `UNSUPPORTED_FILTER`: when `refusal.offending_filters` is empty but `refusal.detail` carries a specific, accurate reason (as it does here — *"Supplier is not an allowed include on PurchaseOrder"*), **prefer the detail.** Change `_reason_line` for `UNSUPPORTED_FILTER` to fall back to `refusal.detail` before the generic sentence.

**Sub-part B (optional, decision needed):** Add a new `RefusalFlavor.UNSUPPORTED_INCLUDE` for this class of problem, with its own guidance table. This is a schema change that ripples through `RefusalFlavor`, `_KIND_TO_FLAVOR`, `_FALLBACK`, and the parser prompt's `unanswerable_kind` enum. Bigger change, cleaner long-term. **Recommendation: defer to a later cycle, do sub-part A now.**

**Files touched (sub-part A):**

- `src/spire/nl_parser/capability.py` — one branch in `_reason_line`
- `tests/test_nl_parser_capability.py` — a case asserting the specific reason appears

**Acceptance test:**

1. Given the S1 refusal intent (post-BUG-2, post-BUG-3 — this is now a clean refusal not a crash), the user-facing message names the specific problem ("Supplier is not an allowed include on PurchaseOrder" or equivalent) rather than the generic "narrow by country, status or name".
2. Full refusal test suite passes.
3. **BUG-1 note:** once BUG-1 lands, this bug stops being observable on S1 — the prompt answers instead of refusing. But the fix is still worth shipping, because the defect class exists for any other include-shaped problem that reaches the refusal path.

**Commit boundary:** one PR, sub-part A only. Sub-part B deferred.

#### Status update (2026-09-12) — ✅ sub-part A FIXED

**Commit:** `7989d24` on `fix/s1-remediation`.

**Files changed:**

- `src/spire/nl_parser/capability.py` — new module-level `_INTERNAL_IDENTIFIER_RE` regex and `_detail_has_internal_identifier` helper. The `UNSUPPORTED_FILTER` self-declared branch now surfaces `detail` only when the discriminator passes. The KG-validation path (which always sets `offending_filters`) is unchanged — it never reaches the new branch.
- `tests/test_bug4_reason_line.py` — new (8 tests).
- `scripts/verify_bug4.py` — new (standalone probe).

**What was learned — the first attempt broke a pre-existing test:**

The first attempt at sub-part A surfaced `detail` unconditionally on the self-declared path. It broke `tests/test_nl_parser_capability.py::test_unsupported_filter_without_named_filters_still_reads`, which protects against the model echoing an internal identifier verbatim — *"requires the 'by_customer_name' filter"*. That is the second-branch leak the existing code was written to hide. The test caught it, which is exactly what it exists for.

The corrected version discriminates. Filter and field keys on this pod are snake_case (`by_customer_name`, `has_open_PO`, `created_before`); underscores in English prose are essentially always identifiers. A `detail` that contains a snake_case token is NOT safe to render; the generic sentence fires instead. A `detail` without one IS the model's specific diagnosis and is shown verbatim. CamelCase class names (`PurchaseOrder`, `ReceivablesInvoice`) do not match the discriminator and are deliberately allowed through — users read them as the noun phrase they spell, and the S1 diagnosis relies on `PurchaseOrder` being visible to make its point.

**Verification (2026-09-12):**

- `tests/test_bug4_reason_line.py`: **8 passed** — including boundary tests for the discriminator in both directions.
- `tests/test_nl_parser_capability.py`: **101 passed**, including the previously-broken `test_unsupported_filter_without_named_filters_still_reads`.
- Full suite: **967 passed**, 18 deselected.
- `verify_bug4.py`: [1] shows the specific detail verbatim (was the generic sentence before the fix); [2], [3], [4] unchanged.
- S1 is unaffected — it already answers via BUG-1 Step 2 and no longer reaches the refusal path.

**Sub-part B (a new `RefusalFlavor.UNSUPPORTED_INCLUDE`) remains deferred** per §5.4.

---

### BUG-5 — Classify stage fires twice per invocation

**Severity:** Low. Not S1-related.
**Blast radius:** Every prompt costs one extra LLM call.

**Evidence:** §2.8.

**Root cause:** Unknown. The second call has identical `in=551` but different output, and the router uses only the final result. Likely a retry in `with_structured_output(include_raw=True)` or in the LangChain Google client.

**Fix (proposed):** Investigate in a separate cycle. Do not fix now.

**Deferred.** No action in this remediation.

#### Status update (2026-09-12) — ⏸ out of scope

Deferred to a separate cycle per §3.4.

---

## 5. Open questions for SME

### 5.1 — What does "supplier details" mean for the answer?

Fusion returns (per curl, §2.1) on the PO header: `Supplier: 'JGA'`, `SupplierId`, `SupplierSite: 'JGA Progress US'`, `SupplierSiteId`, `SupplierContact: 'Ries, Seth'`, `SupplierContactId`, `SupplierContactDisplayName: 'Seth Ries'`.

The current `get_purchase_order_by_id` projection includes Supplier, SupplierId, SupplierSite. It does **not** include the contact fields.

**Question:** should `Show supplier details for PO X` include the contact name (`Seth Ries`)?

**Recommendation:** include the contact.

**Note after the S1 fix:** the typed PurchaseOrder record renders `Supplier` and `Buyer`, but not `SupplierSite` even though the raw output has it. That is a **synthesizer schema** issue (`PurchaseOrderRecord` does not carry `supplier_site`), separate from BUG-1. If the SME wants both the site and the contact in the answer, two things are needed: (a) add `SupplierSite` (and `SupplierContactDisplayName` if desired) to `PurchaseOrderRecord` in the synthesizer, and (b) add `SupplierContactDisplayName` to `_PROJECTED_FIELDS` in `purchase_order_by_id.py`. These could ship together as a follow-up.

**SME answer:** (c) — add the supplier contact **and** fix the site rendering gap. Shipped as BUG-1 Step 3.

### 5.2 — Prompt bullet (Option A/Step 2) or code-side strip only (Option B/Step 1)?

**Recommendation:** yes to Step 2, but as a separate, later PR after Step 1 has proven stable.

**Decided and shipped.** Step 2 shipped as the follow-up. §6.1 promoted it to run before BUG-4, on the grounds that it was the fix that closed the remaining 13/20 S1 failures — not merely tidier, but load-bearing. The regression across all four affected prompt sets passed cleanly.

### 5.3 — Preserve the `Site` gate's distinct message, or generalise?

**Recommendation:** preserve. **Decided and shipped in BUG-2** — the Site message is retained verbatim (see §4 BUG-2 status update).

### 5.4 — BUG-4: detail-passthrough now, or new flavor later?

**Recommendation:** yes to both. Sub-part A now, sub-part B deferred.

**Decided and shipped.** Sub-part A shipped as `7989d24`, with a discriminator to prevent the leak that a first attempt introduced. Sub-part B remains deferred.

---

## 6. Execution plan — one issue at a time

The following order is chosen so that each step is **safe on its own** and each subsequent step builds on a proven foundation.

| Step | Issue | Depends on | Est. files | Test |
|---:|---|---|---:|---|
| 1 | **BUG-2** — validator gate | none | 4 | unit + 20-run S1 batch (crashes → 0) |
| 2 | **BUG-3** — planner raises `RefusalError` | none (parallel to 1) | 2 | standalone repro + full suite |
| 3 | **BUG-1 Step 1** — code-side strip in `parse()` | BUG-2 (`menu.has_edge`) | 2 | **20-run S1 batch: 20/20 answer** |
| 4 | **BUG-4 sub-part A** — `_reason_line` prefers detail | none | 2 | refusal-message assertion |
| 5 | **BUG-1 Step 3** (optional) — add contact field | Step 3, SME answer to §5.1 | 2 | 20-run batch shows `Seth Ries` |
| 6 | **BUG-1 Step 2** — parser prompt bullet | Step 3 stable for one cycle, SME answer to §5.2 | 6 | full `scripts/prompts/*.txt` regression |
| 7 | **BUG-4 sub-part B** (deferred) — new flavor | SME answer to §5.4 | 4 | refusal test suite |
| — | **BUG-5** — classify double-call | — | — | **out of scope; separate cycle** |

**After each step:**

1. Run the step's acceptance test from §4.
2. Run the full test suite (`pytest`).
3. Run `scripts/prompts/00_dipstick.txt` as a canary.
4. Commit and tag.
5. Only then move to the next step.

**After Step 3:** re-run the 20-run S1 batch as the definitive proof. If 20/20 answer correctly, the S1 problem is closed.

### 6.1 Current execution status (2026-09-12)

*(Added 2026-09-12 after the third fix. Updated as later fixes landed.)*

| Step | Issue | Status | Commit | Verified by |
|---:|---|---|---|---|
| 1 | BUG-2 — validator gate | ✅ **DONE** | `97bc8f7` | 17 new tests; 934-suite green; crash count 11→0 |
| 2 | BUG-3 — planner raises `RefusalError` | ✅ **DONE** | `acd3f6f` | 6 new tests; 940-suite green |
| 3 | BUG-1 Step 1 — code-side strip | ✅ **DONE** | `333ea95` | 13 new tests; 953-suite green; batch answers 0→7, crashes 0 |
| 4 | BUG-1 Step 2 (promoted) — parser prompt rule | ✅ **DONE — S1 CLOSED** | `29737de` | 6 new tests; 134/134 across four regression sets; batch answers 7→20, refusals 13→0 |
| 5 | BUG-4 sub-part A — `_reason_line` prefers clean detail | ✅ **DONE** | `7989d24` | 8 new tests; 967-suite green; discriminator pinned by boundary tests |
| 6 | BUG-1 Step 3 — render supplier site and contact | ✅ **DONE** | this commit | 12 new tests; 979-suite green; live S1 shows Site and Contact |
| 7 | BUG-4 sub-part B (deferred) — new flavor | ⏳ deferred | — | SME §5.4 |
| — | BUG-5 — classify double-call | ⏸ out of scope | — | separate cycle |
| — | Cleanup commit | ⏳ **PENDING** | — | revert `c9c4fb1` debug prints; `.gitignore` |

**Step 3 acceptance — the original plan said "20/20 answer".** Step 1 alone delivered 7/20 answers (crashes 0, refusals 13). The remaining 13 were the parser's self-declared-refusal mode, which the strip could not touch. **Step 2 was the fix that closed them**, and §6.1 promoted it to run before BUG-4 for that reason. The plan's step order (3, 4, 5, 6) is preserved above; the promotion is a schedule adjustment, not a reorder.

**Step 4 outcome:** S1 CLOSED — 20/20 answers, 0 refusals, 0 crashes on the live batch. Regression across the four affected prompt sets: 134/134 passed.

**Step 5 outcome:** BUG-4 sub-part A fixed on the second attempt (the first attempt broke `test_unsupported_filter_without_named_filters_still_reads`; the corrected version adds a snake_case discriminator to the detail passthrough). Full suite 967 green.

**Step 6 outcome (BUG-1 Step 3):** the SME's §5.1 option (c) shipped in three layers — tool projection, synthesizer record + both builders, display formatter. 12 new tests; full suite 979 green; live S1 prompt now shows both fields. Only the cleanup commit remains on the branch.

---

## 7. What this document does **not** claim

To keep the record honest:

1. **Not all failure modes are mapped.** Other prompts that acquire an unsatisfiable include may exist. BUG-2's general gate is designed to catch them, but it has not been exhaustively fuzzed.
2. **Not all `PurchaseOrder` prompts have been tested.** The 20-run batch used only the S1 wording. `scripts/prompts/02_purchase_order.txt` and `08_lifecycle.txt` have been spot-checked, not re-run.
3. **The classify double-call (§2.8) is unexplained.** It may correlate with something we haven't measured.
4. **The 9/11 ratio in this batch differs from the earlier session's 7/3.** We do not know why. It does not affect the fix, but it means the writeup's "8/10 refuse, 2/10 crash" characterization should be updated to "bimodal; ratio not stable".
5. **The "8,000-token ceiling" framing in the original writeup is not supported by the evidence.** The fix does not depend on that framing.

---

## 8. Summary table for SME sign-off

| # | Issue | Fix type | Ships | SME input needed |
|---:|---|---|---|---|
| BUG-2 | No general un-wireable-include gate | code (validator) | Step 1 | §5.3 (preserve Site message) |
| BUG-3 | Planner raises raw `KeyError` | code (planner) | Step 2 | none |
| BUG-1 | Parser gap on "supplier details for PO X" | code (strip) + prompt (bullet) | Steps 3, 6 | §5.1 (contact field), §5.2 (bullet or not) |
| BUG-4 | Refusal message names wrong problem | code (capability) | Step 4 | §5.4 (new flavor or not) |
| BUG-5 | Classify fires twice | code (router) | out of scope | none |

### 8.1 Current summary (2026-09-12)

*(Added 2026-09-12 after the third fix. Updated as later fixes landed.)*

| # | Issue | Fix type | Status | SME input needed |
|---:|---|---|---|---|
| BUG-2 | No general un-wireable-include gate | code (validator) | ✅ FIXED `97bc8f7` | none (Site preservation decided — retained) |
| BUG-3 | Planner raises raw `KeyError` | code (planner) | ✅ FIXED `acd3f6f` | none |
| BUG-1 | Parser gap on "supplier details for PO X" | code (strip) + prompt (bullet) + render (site + contact) | ✅ **All three steps FIXED — S1 CLOSED with full supplier details** | none |
| BUG-4 sub-part A | Refusal Reason line prefers clean detail | code (capability) | ✅ FIXED `7989d24` | none |
| BUG-4 sub-part B | New `UNSUPPORTED_INCLUDE` flavor | code (capability) | ⏳ deferred | §5.4 |
| BUG-5 | Classify fires twice | code (router) | ⏸ out of scope | none |

---

## 9. Branch history

*(Added 2026-09-12. New section. Updated as later commits landed.)*

Branch: `fix/s1-remediation`, based on `master`.

| Commit | Message | Files |
|---|---|---|
| `97bc8f7` | Fix S1: general include gate in validate_intent | `vocabulary.py`, `intent_validation.py`, `test_bug2_include_gate.py`, `verify_bug2.py` |
| `c9c4fb1` | chore: S1 debug instrumentation (temporary) | `parser.py`, `router.py` — *to be reverted in a cleanup commit at the end of the branch* |
| `09ae116` | chore: S1 investigation artifacts | `four_bugs.md`, `prompts/12_po_supplier_include.{txt,json}`, `t_s1_isolate.py`, `t_s1_repro.py` |
| `854b81c` | Updating readme, overnight bugs status and utility prograpm | `README.md`, `docs/spire_findings_11-Sep-2026.md`, `isolation/*` |
| `acd3f6f` | Fix S1: planner raises RefusalError, not KeyError, for a bad include | `planner.py`, `test_bug3_planner_include.py`, `verify_bug3.py` |
| `333ea95` | Fix S1: strip the un-wireable Supplier include on PurchaseOrder | `vocabulary.py`, `parser.py`, `test_bug1_po_supplier_strip.py`, `verify_bug1.py`, `docs/four_bugs.md` |
| `29737de` | Fix S1: parser prompt rule for 'supplier details for PO X' | `b_po_supplier_details.sysprompt`, `order.manifest`, `context_assembly.py`, `apply_bug1_step2_context_assembly.py`, `verify_bug1_step2.py`, `test_bug1_step2_prompt_coverage.py`, `test_parser_context_assembly.py`, `docs/four_bugs.md` |
| `7989d24` | Fix S1: refusal Reason line prefers clean detail over generic sentence | `capability.py`, `test_bug4_reason_line.py`, `verify_bug4.py`, `docs/four_bugs.md` |
| `<this commit>` | Fix S1: render supplier site and contact in PO answers | `purchase_order_by_id.py`, `p2p.py`, `display_formatters.py`, `test_bug1_step3_supplier_details.py`, `docs/four_bugs.md` |

**Cleanup commit still pending:** revert the temporary debug instrumentation from `c9c4fb1` once BUG-1 Step 3 is settled (it now is), and add `.gitignore` entries for local-only artifacts (`isolation/`, `s1_*.txt`, `test_bug*.txt`, `verify_bug*.txt`, `s1_step2_*.txt`, `pipeline_*.txt`, `source-tree.txt`).

**Process note:** from commit `333ea95` onward, every commit on `fix/s1-remediation` includes an updated `docs/four_bugs.md` as part of the commit. The document tracks what was fixed, by which commit, and any deviations from the plan discovered during the fix.

---

**End of document.**