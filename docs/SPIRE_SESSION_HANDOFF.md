# Spire — Session Handoff (2026-07-30)

Paste the companion text into the new window to continue. Supersedes the
2026-07-29 handoff.

---

## Who / what

Continuing **Spire** — AI-native NL query over Oracle Fusion Cloud (P2P +
AR). Deterministic KG pipeline: parse → plan → execute → synthesize, two
LLM boundaries only (parser, synthesizer). Tool selection is a KG lookup,
not an LLM judgement. Not an agent architecture.

Repo `github.com/bhagavansprasad/spire`, working dir `~/pocs/spire`, pod
`fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`, creds in
`personas.yaml` (gitignored).

**On `master`, clean, 602 tests passing.** Nothing outstanding in the
working tree.

---

## What this session did

**Module 5 (PO Lifecycle) went from a standalone tool to five catalog
prompts answering end to end.** Phases 3 through 9 of the build sequence,
merged to master in two commits.

### Merged

| Branch | Phases | Scope |
|---|---|---|
| `lifecycle-phase-3-4-tool-layer` | 3, 4 | Tool contract, supplier setup, computed risk, per-line detail |
| `lifecycle-phase-5-9-pipeline` | 5–9 | KG rows, parser, planner, server wrapper, synthesizer, display |

### The five prompts now answering

Catalog section 4.A: **A.2, A.3, A.4, A.7, A.10.** One tool, one KG filter,
three output shapes (status matrix, executive summary, diagnostic).

`scripts/prompts/08_lifecycle.txt` — 31 prompts, **30 routed as intended.**
Zero regressions on the five neighbouring routes that share vocabulary.

### Measured, post-merge

| Metric | Value |
|---|---|
| Full suite | 602 passed, 17 deselected, 1 xfailed |
| Lifecycle tool tests | 98 (`tests/test_po_lifecycle_tool.py`) |
| Mean wall-clock, answered prompt | 16.0 s (range 4.8–21.4) |
| Mean tokens per prompt | 12,230 (median 12,288) |
| **Parse input baseline** | **~8,671** — see the diagnostic note below |
| Parse share of all input | 78% |
| KG counts | `kg_entity_tool` 10, `kg_entity_filter` 24 |

**THE STALE-KG DIAGNOSTIC HAS MOVED.** The old rule was "if `parse in=` is
materially below ~8,119, the KG did not rebuild." Phase 6 added ~546 tokens
to the parse prompt. **The new baseline is ~8,671.** A run at 8,119 now
means something is wrong, not right.

---

## Contract decisions closed this session

Recorded because they constrain everything downstream.

**D1 — the paid leg is TRI-STATE.** A PO can carry `BilledAmount` on its
schedules with no AP invoice bearing its number (701337 does). The tool used
to report `remaining_to_pay: 398.00`, asserting a debt when the truth is the
bill cannot be found. Now `paid_state: "unknown"`, `fully_paid: None`,
`remaining_to_pay: None`.

**Branch on `paid_state`, never on the truthiness of `fully_paid`.** JSON
has no tri-state bool; `None` serializes to `null` and `if fully_paid:`
reads null as False, which restores the exact defect.

**D2 — `totalResults=true` on every paged fetch**, read from the FIRST page.
Reading it from the last loses it when the cap is hit, which is the case the
count is needed for.

**D3 — `risk` and `recommended_action` are computed in the tool**, never in
the synthesizer, with `risk_reasons` always accompanying the rating. A
rating an LLM invents is unreproducible and unauditable.

**D4 — money from invoice headers, context from installments.** Installments
are one call per invoice and therefore capped; headers never are. Sourcing
money from a capped fetch gives a silently short total. `UnpaidAmount` is a
cross-check that lands in `notes`, never a source. A bitten cap costs hold
visibility, never a number.

**D5 — a FILTER on PurchaseOrder, not a new entity.** The vocabulary already
binds "purchase order", "PO" and "order" to `PurchaseOrder`; a `POLifecycle`
entity would compete for those words and lose. No `kg_entity_field` rows
either — the tool's fields are computed, not endpoint fields.

**D6 — ONE filter, not three**, though five prompts route through three
shapes. They want the same data and differ only in emphasis; rendering is
the synthesizer's choice, not the planner's.

**D7 — the synthesizer writes the summary ONLY.** Legs, stage, team, risk,
action, setup notes, exceptions and tables are all built in code by
`build_lifecycle_response`. See "the paid-leg lesson" below.

---

## Three known defects, carried forward

All three found by reading actual output. None produces a wrong number.

**1. A risk-only question is refused.**
*"What is the risk rating on PO 701337 and why?"* → *"The system does not
track 'risk rating' for purchase orders."* It does — risk appears with full
reasoning whenever a broader question is asked. The parser's PO LIFECYCLE
section covers risk only inside the summary case. **One line of parser
instruction.**

**2. A non-existent PO renders as "cannot be determined".**
`found: False` produces *Received: cannot be determined · Invoiced: cannot
be determined · Paid: cannot be determined*, which implies the order exists
and is unknowable. The summary sentence is correct and the verdict line
contradicts it. `build_lifecycle_response` does not branch on
`found=False`.

**3. Internal ids leak into user-facing prose.**
The summary says *"supplier JGA (ID 300000047414635)"*. Real, but no finance
user wants it. One line in the synthesizer prompt.

**Also spotted, not yet fixed:** when the supplier site cannot be read,
`_build_lifecycle_setup_notes` still prints *"differ from the site default
(None)"* — comparing against a value it does not have. Same species as
defect 2: a null rendered as a statement. Gate it on `site_read`.

---

## Curl findings added to the reference (section 14)

All verified 2026-07-29. Eleven rows for the quirk table are in §14.0,
**still to be pasted into the table at the top of the file** — the section
was appended but the table rows are a manual step.

- `totalResults=true` honoured on `/purchaseOrderSchedules` and `/invoices`
- **Invoice holds live on `invoiceInstallments`**, not the invoice header.
  There is no `holds` child. `HoldFlag`, `HoldReason`, `HoldType`, `HeldBy`,
  `HoldDate`, plus a real `DueDate` and `UnpaidAmount`
- **NO payment document exists anywhere on the AP path** — no payment
  number, no payment date, on either the invoice or the installment. This is
  an absence, not an undiscovered endpoint
- `AmountPaid` and `CanceledFlag` are on the invoice header. Summing
  `InvoiceAmount` gated on `PaidStatus == "Paid"` drops partial payments
  entirely
- `expand=sites` **works on a single-supplier GET** — the existing "silently
  ignored" quirk is about BULK fetches only. It returned 22 sites for JGA
- `suppliers/{id}/child/sites/{siteId}` accepts `fields=` and carries five
  hold flags plus `MatchApprovalLevel` and `InvoiceMatchOption`
- Fetch the supplier **by SupplierId** (on the PO header) to sidestep the
  client-side `Status` matching quirk
- PO header has supplier-communication fields but **no approval date and no
  approver**
- `TotalTax: 0` on 701337 — so PO-side tax does NOT explain 162034's 72.01,
  which the previous session had guessed
- `FundsStatus` is null on closed POs

---

## Test data

| PO | Supplier | Status | Ordered | Received | Invoiced | Paid | Stage |
|---|---|---|---|---|---|---|---|
| **701337** | JGA | Open | 1235.00 | 398.00 derived | 398.00 | **unknown** | Awaiting receipt |
| **162034** | Lee Supplies | Closed | 758.00 | 758.00 | 758.00 | 830.01 | **Complete** |

701337 proves partial reconciliation, mixed line statuses (line 1 Open with
837.00 outstanding, line 2 Closed), the unknown paid state, and the
payment-terms override (PO Net 30 vs site default 2/10 Net 30).
`PayOnReceiptFlag: true` **may** explain the unmatched billing via
self-billing — **unconfirmed, and labelled as such in output.**

162034 proves the invoice join, the installment join and the Complete stage.
Carries an unexplained **72.01** over-invoice.

**What these two do NOT cover:** a partly paid invoice, an invoice on hold,
a supplier setup blocker, a truncated fetch. All four exist in code and are
covered by synthetic test cases only. **Finding real POs for the first two
is worth an hour before any SME demo.**

---

## Corrections made this session

Recorded because the pattern matters more than the individual errors.

**"`responsible_team` returns Payments on 701337" — WRONG.** 701337 is only
partially received, so it stops at *Awaiting receipt* / *Supplier /
Receiving*, both legs before the paid leg. The wrong-team bug was real but
reachable only on a PO fully received AND fully invoiced with unmatched
billing — neither test PO. Confirmed synthetically instead.

**"Neither test PO reaches the Complete stage" — WRONG.** 162034 does, under
both old and new code.

**"The planner may need zero changes" — WRONG.** It needed two, and one was
a hard blocker: the `PurchaseOrder` rooting guard accepted only `by_id`,
`created_before` and `created_since`, so a correctly parsed lifecycle intent
would still have been refused.

**Invented a helper that did not exist.** Wrote a synthesizer branch calling
`_synthesize_with_schema`, inferred from the shape of surrounding code.
Caught by grep before it shipped.

**All four came from reading code rather than running it.** The plan
document now carries the first two as explicit corrections rather than
quietly fixing them.

---

## Hard-won lessons (carried + new)

**Curl before code.** Every fix that stuck started with a curl; every
theory-first attempt got reverted.

**A claim from inspection is not a finding.** Four times this session. Cheap
when caught before the doc lands; expensive in a demo.

**Measure rather than infer, when measurement is one command.** Two KG rows
with ~150-word `notes` moved parse input by **8 tokens** — which proved the
notes never reach the parser at all. `KGMenu` carries `filter_types` as bare
strings: entities get descriptions, filters get nothing. That one number
settled a question two rounds of code reading had not.

**An absent child rules out a PATH, not a capability.** Invoice holds were
briefly written off because `/invoices` has no `holds` child. They were one
level down, on `invoiceInstallments`. Check the children of the children
before declaring absence.

**A `.links[]` listing beats guessing paths.** One call named every child of
`/invoices` and ruled out two guesses at once.

**A control curl is what makes an empty result trustworthy.** 701337's zero
invoices only became a finding once 162034 proved the filter works. Second
session running where a control changed the diagnosis.

**Parser instruction placement is load-bearing — confirmed again.** The
refusal cost `out=1412`; the routed answer costs `out=231`. Six times
smaller, from putting the instruction in a standalone labeled section rather
than a bullet inside `COMPLETENESS`.

**THE PAID-LEG LESSON — code-built beats prompt-instructed.** The first
working run reported `Paid: amount=0.0` beside the note *"cannot be
determined"*. The model copied the tool's `paid: 0.0` faithfully and
destroyed its meaning: a reader sees 0.00 and concludes nothing was paid.
The prompt already said not to. Moving leg construction into code removed
the failure mode instead of guarding against it — and cut synthesize output
1,824 → 924 for a better answer. **Generalise this pattern.**

**Verify `fields=` per endpoint.** `/standardReceipts` 500s on any
projection; the supplier-site child accepts it. Neither is inferable from
the other.

---

## Documents produced this session

| Document | Purpose |
|---|---|
| `docs/spire_plan.md` §Module 5 | Rewritten with two corrections marked as corrections, phases 3–9 status, seven carried risks |
| `docs/spire_fusion_endpoints_reference.md` §14 | The 2026-07-29 curl findings. §14.0 rows still to be pasted into the top table |
| `spire_lifecycle_sme_update.md` | SME-facing: all 31 prompts with results, every refusal explained, known limitations up front |
| `spire_enhancement_roadmap.md` | 16 raw enhancement items grouped into six themes, resequenced |
| `spire_enhancement_requirements.md` | Formal spec: 27 requirements, 3 decisions, 12 phases, full traceability to the original 16 |

**The last two are not in the repo yet, and the requirements document is now
the governing plan for the next phase of work** — see THE NEXT GOAL below.
Filing them is the first action of the next session.

---

## THE NEXT GOAL

**Deliver the enhancement requirements document, and clear the open defects
along the way.**

That is the whole of the next phase of work. Module 5's five prompts are
delivered; new catalog coverage (A.1, A.5, A.6, A.8, A.9) is explicitly
NOT the next goal and should not be started without a decision to change
direction.

### The governing document

`spire_enhancement_requirements.md` — **27 requirements, 3 decisions, 12
phases.** It is the plan. It supersedes any ad-hoc feature list, including
the raw 16-item list it was derived from, and including the roadmap draft
that preceded it.

**IT IS NOT IN THE REPO YET.** First action of the next session: file both
planning documents deliberately — `docs/spire_enhancement_requirements.md`
and, if kept, `docs/spire_enhancement_roadmap.md`. A governing plan that
lives only in an attachment will be lost.

Requirement IDs are stable and should be quoted in branch names, commit
messages and test names: `UX-01`, `OBS-03`, `TST-02`, `PRF-05`, `API-01`,
`DEC-01`.

### Phase 0 — the open defects

Not in the requirements document, because they predate it. Clear them first:
they are small, they are in front of an SME right now, and two of them are
instances of the very class `UX-01` addresses.

| # | Defect | Fix |
|---|---|---|
| 1 | Risk-only question refused | One line in the parser's PO LIFECYCLE section |
| 2 | Non-existent PO renders "cannot be determined" | `found=False` branch in `build_lifecycle_response` + a display case |
| 3 | Internal `SupplierId` in user-facing prose | One line in the synthesizer prompt |
| 4 | Terms note prints "(None)" when the site is unread | Gate on `site_read` in `_build_lifecycle_setup_notes` |

Roughly half a day. Defects 2 and 4 are the same species — a null rendered
as a statement — and should be fixed together.

### Then the requirements phases, in order

Sequence is per §10 of the requirements document. Dependency-ordered, not
priority-ordered.

| Phase | Requirements | What it is |
|---|---|---|
| **1** | `UX-05`, `OBS-01`, `OBS-02` | Quiet default output; independent per-component debug flags; config file with CLI override |
| **2** | `UX-01`, `UX-02`, `UX-03` | Structured refusals; narrowing guidance for over-broad queries; truncation disclosure |
| **3** | `OBS-03`, `OBS-04`, `OBS-05` | Per-stage timing; per-Fusion-call timing; machine-readable run record |
| **4** | `TST-02`, `TST-03`, `TST-01` | Plan tests (no LLM, no pod — do first); synthesizer tests on fixed records; routing tests |
| **5** | `PRF-01` | Deterministic response construction across all shapes |
| **6** | `PRF-02`, `PRF-03` | Prompt caching for the KG menu; exact-match intent cache |
| **7** | `PRF-05` | Concurrent Fusion calls |
| **8** | `UX-04`, `PRF-07`, `PRF-08` | Aggregate fallback; verify against the latency and token targets |
| **9** | `API-01`, `API-02` | REST interface; structured response contract |
| **10** | `API-03` | Spire as one MCP tool — requires `DEC-02` |
| **11** | `PRF-06`, `PRF-04` | Vocabulary into the KG; evaluate the semantic intent cache |
| **12** | `API-04`, `API-05` | Configuration UI; query console — constrained by `DEC-03` |

**Phases 1 to 4 produce no new capability**, and that is the point. They are
the reason every later phase is faster and safer: without phase 3 no
optimisation can be proven to have helped, and without phase 4 none can be
shown not to have broken something.

**Resist starting at phase 5 or 6.** The gains there are visible and the
temptation is real. It is also how an unmeasured optimisation becomes an
unnoticed regression.

### The baseline the targets are measured against

From this session, on the 31-prompt run. `PRF-07` and `PRF-08` are stated
relative to these numbers, so they must not be re-derived from a different
run without saying so.

| Metric | Baseline | Target |
|---|---|---|
| Mean wall-clock, answered prompt | 16.0 s | under 8 s (`PRF-07`) |
| Mean tokens per prompt | 12,230 | under 4,000 (`PRF-08`) |
| Parse share of all input tokens | 78% | — |
| Fusion calls per lifecycle prompt | 6, sequential | concurrent (`PRF-05`) |

## Open questions awaiting a decision

From the requirements document §9. **Decisions, not tasks.**

**DEC-01 — planner architecture.** Should the KG planner be supplemented or
replaced by an LLM planner, single-agent or multi-agent? **This is a
reversal of Design 3, not an enhancement.** Proposed resolution: keep the KG
planner primary, add an LLM fallback for currently-refused questions only —
additive, evaluable, no rewrite.

**DEC-02 — copilot exposure.** Expose the MCP tools directly (discards KG
planning and every guard), expose Spire as ONE MCP tool running the full
pipeline (preserves everything), or expose REST? Proposed: the second, with
REST for breadth.

**DEC-03 — multi-backend.** "Connect to any HCM" is a programme, not a
configuration screen. Every documented pod quirk is Fusion-specific. Must
not block the UI work.

---

## Carried forward from the previous handoff — still open

Not touched this session.

**Can put a wrong number in front of someone**

- **Invoice total over a sample.** "invoices for Lee Supplies" states a
  total summed over 25 of 1,343 rows as fact. Same family as the
  credit-memo defect already fixed, different mechanism.
- **"Country" returns a full address.** Asking for country yields
  `7 Saxon Close,AGHORY,Armagh,UNITED KINGDOM`.
- **Only the FIRST address is shown**, silently, for suppliers with many.
- **`StandardReceipt` and `AccountReceipt` model the same receipts** with
  disagreeing counts, and both are routable.

**Pinned bugs**

- **`search_standard_receipts` can never report `truncated=True`.** Pinned
  by a `strict=True` xfail. Needs `ToolResult` to express "truncated, total
  unknown".
- **W7 — "supplier sites" mis-parses as addresses.** Root cause: `Address`
  and `Site` have ZERO `entity_synonym` rows. But the synthesizer has no
  concept of a site at all, so this is a full phase, not a data fix.

**Housekeeping**

- **17 tests are DESELECTED** by a marker filter nobody has examined.
- Address flattening exists twice.
- ~31 branches on the remote, most looking merged. Worth a prune.

---

## Reference

- KG rebuild: `python scripts/rebuild_kg.py` — always from scratch. Seed is
  `scripts/sql/kg_schema.sql` (schema AND data, 384 inserts).
- **Restart the MCP server after ANY change under `src/spire/mcp_server/`.**
  Tool definitions are built at import. Planner, parser and synthesizer
  changes do NOT need a restart.
- **KG counts live in FOUR places, not two:** `scripts/print_kg.py`,
  `tests/test_kg_metadata.py`, and the two `PROMPT Seeded ... (N rows)`
  banners inside the seed file itself.
- Synthesizer five-place rule: registry, `_SYSTEM_PROMPT_BY_ENTITY`,
  `_collect_valid_ids`, the validator function, the validator dispatch —
  plus the empty-array guard, whose bucket name must match
  `_OUTPUT_NAME_BY_ENTITY` exactly. **Module 5 needed two more:** a shape
  detector, and a branch in the schema-selection chain.
- Standalone tool runner: `python test_tools/try_po_lifecycle.py 701337
  162034`. No MCP, no KG, no LLM — a failure is the tool's or the pod's and
  can be nothing else. It asserts the contract and exits non-zero on a
  violation.
- Pod quirks: see `docs/spire_fusion_endpoints_reference.md`. Composite `q=`
  fails silently with HTTP 200 / `totalResults: 0` — SINGLE clauses only.

**Files to share when starting a task:** `docs/spire_plan.md`,
`docs/spire_fusion_endpoints_reference.md`, this handoff, plus the code
files the task touches. **Always re-share before editing — never work from a
copy pasted earlier in the session.** Three files were edited from bundle
copies this session; all three needed a "diff before copying in" warning.
