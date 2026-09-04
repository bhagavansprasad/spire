# Handoff — Spire (Router shipped, promptkit shipped)

Paste this into the new window to continue.

---

## What Spire is

AI-native NL query over Oracle Fusion Cloud (P2P + AR). Deterministic KG
pipeline: **route → parse → plan → execute → synthesize**. Two LLM boundaries —
the module **classifier** and the **parser** (words → Intent); planning,
execution, and synthesis are deterministic (no LLM synthesis call).

- Repo: `github.com/bhagavansprasad/spire`, working dir `~/pocs/spire`
- Current pod: `eqjz` (user `Axel.Grant`), creds in `personas.yaml`
  (`fa-esll-dev37` and `dabpqy` are expired). **Spire reads `personas.yaml`
  ONLY** — the `IKS_FUSION_*` shell env vars are for curl scripts, NOT Spire.
- LLM: Gemini `gemini-3.5-flash` via Vertex AI. `LLM_MAX_OUTPUT_TOKENS = 8000`
  in `src/spire/config.py`.
- Everything below is **merged to `origin/master`** and the suite is green
  (886 passed, 18 deselected).

---

## What shipped (this + prior sessions)

**The module-scoping router — built, validated, DEPLOYED.**
- `route_and_parse(prompt)` (`src/spire/nl_parser/router.py`): a small LLM
  classifier picks the prompt's Fusion module(s), then `parse()` runs against
  only that module's scoped context. Wired into the pipeline
  (`src/spire/graph/pipeline.py` calls `route_and_parse`). **~56% fewer parser
  tokens per request** (measured: ~4,200 vs ~9,600).
- Assembly lifted to `src/spire/nl_parser/context_assembly.py` (one manifest
  reader, `assemble_subset`, `KNOWN_MODULES`, the classifier menu).
- Classifier grounding generated from the KG:
  `scripts/build_classifier_context.py` → `context/routing/classifier_menu.sysprompt`.
- Out-of-scope prompts (no module) fall back to a full-context parse that
  refuses cleanly (not an exception).

**promptkit — the unified prompt-set tool** (`scripts/promptkit.py`). ONE tool,
JSON the single format, flat flags:
- `--generate <txt>` → run prompts through the router, write a `.json`
  (`{prompt, module, tool, note}`, the router's actual choices).
- `--validate <json>` → check each prompt still routes to its recorded module +
  tool. No execution — fast regression net.
- `--run <json>` → execute each prompt end to end against Fusion AND re-check
  routing, reporting **which stage** fails (module → intent → tool → plan →
  execute). Per-prompt output matches run_graph (interleaved, honors the
  diagnostics system: `pyproject.toml` + `--show-*`).
- `--run --prompt "..."` → one ad-hoc prompt (replaces run_graph for singles).
- Supersedes `validate_tool_selection.py` (removed) and `run_graph.py` in the
  docs (run_graph still exists but is no longer the documented entry point).

**Four findings fixed / documented** (from router validation):
- Child-led phrasing ("contacts for supplier X", "lines on PO X") now sets the
  `include` deterministically (`add_child_include_from_prompt` in
  `vocabulary.py`) — returns the child data.
- Top-N invoices by amount: new aggregation op end to end (tool
  `rank_invoices_by_amount` + registries + parser + synthesizer + display),
  zero LLM synthesis. Endpoint curl-confirmed.
- Open-PO as a top-level query: correctly unsupported (status isn't a PO root
  filter). Documented, no fix.
- Out-of-scope router regression: fixed via the full-parse fallback above.

**Also:** truncation-on-empty fix in `search_suppliers` /
`search_suppliers_by_country` (report clean-empty when a client-side filter
matches nothing, instead of `truncated=True`).

**Docs:** README slimmed to a tight accurate overview; the two run guides merged
into `how-to-run.md` (promptkit as the entry point); §7.1 in
`docs/features/prompt_to_intent_framework.md` records the parser's
non-determinism near the token ceiling; `docs/features/actionable_refusals.md`
is a captured (not-yet-built) design.

---

## Findings promptkit surfaced — NOT yet fixed (candidate next work)

Running the existing prompt sets through `promptkit --generate`/`--run`
surfaced real gaps. These are logged, not fixed:

1. **Address child-led gap.** "Addresses for supplier X" refuses. Address has a
   fetcher AND is an edge child, so it was deliberately excluded from the
   child-include map (`_CHILD_INCLUDE_WHEN_PRESENT` in `vocabulary.py`). Needs a
   considered fix (dual-natured entity).
2. **`AccountReceiptApplication` planner crash.** "Show receipt applications for
   customer ABC" → `generate_plan` raises `KeyError: no edge from
   'AccountReceiptApplication' to 'AccountReceipt'`. A real planner/KG edge bug
   — a prompt that CRASHES rather than refuses. **Highest priority (it errors).**
3. **Exposure ranking refused.** "Rank top accounts by outstanding exposure" →
   parser refuses `unsupported_operation`, but the tool
   `rank_customer_accounts_by_exposure` (op `exposure_ranking`) exists. Parser
   doesn't emit the op. Same class as the top-N-invoices fix.
4. **Receipt method distribution refused.** "Show receipt method distribution
   for customer X" → same pattern; tool
   `aggregate_standard_receipts_by_method` (op `receipt_method_distribution`)
   exists, parser doesn't emit it.

Only `01_supplier.json` and `mini.json` corpora exist so far. The other prompt
files (`02_purchase_order`, `03_ar`, `04_columns`, `05_refusals`, `07_alacarte`,
`11_column_vocabulary`, `qa_testcases`) have NOT been turned into `.json`
corpora yet — running `promptkit --generate` on them will surface more.

---

## Other parked / backlog (captured, not started)

- **Generate `.json` for the remaining prompt files** and review the
  refuse/error entries (the batch: `promptkit --generate scripts/prompts/*.txt`).
- **Per-supplier scoping for top-N invoices** — the tool supports
  `supplier_name`; the parser wiring was deferred (increment 1 shipped top_n
  only).
- **Router increment 2** — cross-module union + "unsure" fallback (increment 1
  is single-module happy path; the classifier already returns a list).
- **Actionable-refusals feature** — designed in
  `docs/features/actionable_refusals.md`, not built. Turns machine refusal
  flavors into KG-grounded Reason/Solution/Example refusals.
- **Same truncation-on-empty pattern** likely in `invoices` /
  `purchase_orders` (untested there).
- **Strengthen the routing harness** to exercise the `route_and_parse`
  out-of-scope fallback (promptkit's `--run` flags "weather" as FAILED AT:
  module because the check calls `classify_modules` directly).
- **Auto-reload MCP server** — `fastmcp run src/spire/mcp_server/server.py -t
  http --host 127.0.0.1 --port 3333 --reload --reload-dir src/spire` (HTTP
  transport supports reload); could wrap in a `fastmcp.json` for one-word
  `fastmcp run`.

---

## RECOMMENDED NEXT ACTIVITY

**Fix finding #2 first — the `AccountReceiptApplication` planner crash.** It is
the only one that *crashes* (`KeyError`) rather than refusing gracefully; a user
gets a traceback. It's a planner/KG edge bug. Diagnose it (which edge is
missing/mis-modeled between `AccountReceiptApplication` and `AccountReceipt`),
confirm against the KG (`print_kg.py`, the `kg_edge` table), then fix.

After that, the two "capability exists but parser refuses" findings (#3 exposure
ranking, #4 receipt method distribution) are the same shape as the top-N-invoices
fix already done — teach the parser the existing op, verify end to end.

Then generate `.json` corpora for the remaining prompt files and run them to
surface the rest.

---

## Key facts / lessons (apply to all work)

- **Spire reads `personas.yaml` only** for the pod; env vars don't affect it.
  A wrong pod usually means the **MCP server is stale** — restart it (it loads
  the persona once at startup).
- **The parser is non-deterministic near its ~8,000-token ceiling** — identical
  input can parse or refuse across runs. Single-run results near the ceiling
  aren't trustworthy; the KG is the deterministic oracle. (This is why the
  router matters beyond tokens — scoping stabilizes the parse.)
- **Add parser signals in CODE post-parse, not in the prompt** — the prompt is
  at its ceiling; LLM-visible additions can tip phrasings into MAX_TOKENS
  runaway. (`_is_explicit_po_list`, `add_child_include_from_prompt` are the
  pattern.) The router provides headroom, so scoped-prompt additions are safer,
  but the code-side default still holds.
- **"has a fetcher in `kg_entity_tool`" ≠ "listable bare"** — Invoice,
  StandardReceipt, ReceivablesInvoice have fetchers but the planner requires
  scoping (a supplier/customer/id) and refuses without it. That's correct.
- **Confirmed = actually run/curled**, never inferred from reading code.
- Restart the MCP server after any change under `src/spire/mcp_server/`.
- KG rebuild: `python scripts/rebuild_kg.py` (never the `.sh`); when adding KG
  rows/fields bump tripwires in `scripts/print_kg.py` AND
  `tests/test_kg_metadata.py` together.

---

## WORKING STYLE (STRICT — copy-paste this into the new window)

1. Short, interactive, ONE step at a time. One command at a time; verify before
   proceeding. No batch-generating, no 100+ line dumps to read.
2. Ask permission before generating code or significant content.
3. Offer choices as plain-text numbered options with a recommendation and the
   reason. No widgets.
4. Deliver the COMPLETE updated file, never a patch/diff. Read the current full
   file (from the bundle/upload I provide) before editing — files drift. Verify
   my copy matches the live file (hash) before overwriting.
5. Output via tee to t.txt (`cmd 2>&1 | tee t.txt`); `>` overwrite, `>>` append.
   Never a bare `> t.txt`.
6. Git: one branch per logical change, PR-based merges, named files in `git add`
   (never `-A`), heredoc commit messages (`git commit -F- <<'EOF'`). Docs-only
   may go straight to master. Check the branch before committing.
7. Curl the pod before writing code for any endpoint/field; read
   `docs/spire_fusion_endpoints_reference.md` FIRST.
8. "Confirmed/verified" means actually run, never inferred from code/logs.
9. pytest always `-q`; full suite before any source commit; targeted tests
   during work.
10. KG rebuild: `python scripts/rebuild_kg.py` (never the `.sh`); when adding KG
    rows/fields, bump tripwires in `scripts/print_kg.py` AND
    `tests/test_kg_metadata.py` together.
11. Restart the MCP server after any change under `src/spire/mcp_server/`.
12. Prefer teaching the LLM via the prompt only where it needs judgment; add
    deterministic parser signals in CODE post-parse (respect the ~8,000-token
    ceiling — additions can tip into MAX_TOKENS runaway). The router scopes the
    prompt per module, which provides headroom.
13. I'm always in `~/pocs/spire` (no `cd` needed).

---

## First steps in the new window

1. Read this handoff and `docs/features/prompt_to_intent_framework.md` (esp.
   §7.1) and `docs/features/actionable_refusals.md`.
2. Confirm ground truth: `git log --oneline -5`, `python -m pytest -q`
   (green-or-environmental), MCP server up on the eqjz pod.
3. Start the recommended next activity: diagnose finding #2 (the
   `AccountReceiptApplication → AccountReceipt` edge KeyError) — reproduce with
   `python scripts/promptkit.py --run --prompt "Show receipt applications for
   customer ABC Application Software"`, then inspect `kg_edge` via
   `python scripts/print_kg.py --table kg_edge`.
