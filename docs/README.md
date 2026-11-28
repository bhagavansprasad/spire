# Spire documentation map

**Reviewed:** 2026-11-26

**Purpose:** entry point for the project's maintained guides, plans,
references, test documents, and generated context captures.

This map describes the documents present in the workspace at review time.
“Active” means a file describes itself as a living guide or queue; it does
not mean its contents have been independently revalidated against the code
or live Fusion pod. Dated snapshots and design notes should be checked
against the current branch before being used as implementation truth.

## Start here

| Need | Start with |
|---|---|
| Understand Spire | [Project README](../README.md) |
| Set up and operate Spire | [Full run guide](../how-to-run.md); use the [quick reference](../Quick_how_to_run.md) for a shorter path |
| Find current prompt-coverage gaps | [Prompt Coverage](../prompt_coverage.md) |
| Resume the KG schema work | [Pending KG schema corpus](plan/PENDING_KG_SCHEMA_CORPUS.md), then check its dated status against the current branch |
| Check the known-failure queue | [Fix Plan](fixes/FIX_PLAN.md); confirm its status against the latest entries and current work |
| Apply the repository rules | [Working Style](plan/WORKING_STYLE.md) |
| Find SME module test context | [Expected answers](../prompts/sme_module_a/sme_module_a_expected.md) and the [dated prompt sheet](../prompts/sme_module_a/PROMPT_SHEET_2026-11-21.md) |
| Add or extend Fusion module support | [Module-support roadmap](plan/module-support/MODULE_SUPPORT_ROADMAP.md) for order and gates; [playbook](plan/module-support/MODULE_SUPPORT_PLAYBOOK.md) for the code procedure |
| Find Fusion endpoint notes | [Fusion Endpoints Reference](reference/spire_fusion_endpoints_reference.md); verify pod-specific details before use |

## Project and operator guides

| Document | Contains | State |
|---|---|---|
| [README.md](../README.md) | Product overview, architecture, quick start, sample prompts, API/UI summary | Main project overview; verify operational details against the run guide |
| [Quick_how_to_run.md](../Quick_how_to_run.md) | Condensed setup, startup, module coverage, and prompt examples | Quick reference; overlaps with the full run guide |
| [how-to-run.md](../how-to-run.md) | Setup, credentials, runtime modes, promptkit usage, troubleshooting | Primary operator guide; commands and environment assumptions can change |
| [prompt_coverage.md](../prompt_coverage.md) | Prompt shapes Spire handles, gaps, and proposed work | Describes itself as a living backlog; validate entries with current tests |
| [copilot-instructions.md](../.github/copilot-instructions.md) | Repository-specific Copilot behavior and links to working-style guidance | Active instruction entry point; see the linked Copilot style below |

## Design and implementation references

| Document | Contains | State |
|---|---|---|
| [ARCHITECTURE.md](design/ARCHITECTURE.md) | Semantic-cache architecture | Design/reference document; compare with current implementation before relying on details |
| [EXTENDING.md](design/sql_overlay/EXTENDING.md) | Maintainer notes for extending the SQL overlay | Useful implementation guide, but its introductory link to `../SQL_OVERLAY_POC.md` does not resolve in the current inventory |
| [POC2_SKETCH.md](design/sql_overlay/POC2_SKETCH.md) | Questions and validation ideas for SQL overlay POC-2 | Sketch, explicitly not a plan |
| [spire_fusion_endpoints_reference.md](reference/spire_fusion_endpoints_reference.md) | Fusion REST endpoint behavior and known quirks | POC reference; pod, endpoint, and authentication details may be stale |

## Fixes, planning, and handovers

| Document | Contains | State |
|---|---|---|
| [FIX_PLAN.md](fixes/FIX_PLAN.md) | Deferred failures, findings, and fix queue | Designated issue queue; use the current working copy and latest entries, not only its dated summary |
| [WORKING_STYLE.md](plan/WORKING_STYLE.md) | The project rulebook: behavior rules, editing mechanics, evidence standards, and durable conventions | Governs every session; the long form of `.github/copilot-instructions.md` |
| [PENDING_KG_SCHEMA_CORPUS.md](plan/PENDING_KG_SCHEMA_CORPUS.md) | KG schema corpus work register and progress notes | Contains a 2026-11-19 status snapshot; reconcile it with current code, branch, and fix queue |
| [sme_prompts_status/](plan/sme_prompts_status/README.md) | The 40-prompt SME set: per-run results, the open SP queue, cross-run comparison, and resume context | Live queue; read `HANDOFF.md` first |
| [module-support/](plan/module-support/STATUS.md) | Fusion module-support planning: portfolio and priority, the eight delivery gates, and the REST-first implementation playbook | Planning baseline; REST is the delivery path and SQL is deferred |
| [HANDOVER_KG_SCHEMA.md](plan/HANDOVER_KG_SCHEMA.md) | Phase 1 KG schema strategy and handover | Historical handover; later revisions in the phase documents and pending register supersede parts of it |
| [HANDOVER_KG_SCHEMA_PHASE2.md](plan/HANDOVER_KG_SCHEMA_PHASE2.md) | Phase 2 schema discovery, reversals, and role-map work | Historical handover; consult the pending register for the dated follow-on state |
| [SESSION_STATUS_2026-11-19.md](plan/SESSION_STATUS_2026-11-19.md) | Evidence-backed KG schema and SQL-emitter status at that session close | Historical point-in-time snapshot; not current repository status |
| [KG_ROLE_MAPS.md](plan/KG_ROLE_MAPS.md) | Per-entity SQL role maps and evidence | Append-only authored reference, per its header |
| [KG_FIELD_TRANSLATION.md](plan/KG_FIELD_TRANSLATION.md) | Translation between drafted SQL roles and KG field names | Mapping/design reference; confirm against current KG seed before changing it |
| [SCHEMA_DISCOVERY_METHOD.md](plan/SCHEMA_DISCOVERY_METHOD.md) | Reusable procedure for discovering Fusion tables, fields, and joins | Reusable method document; use with current pod access and verify results |
| [DEMO_SME_2026-11-20.md](plan/DEMO_SME_2026-11-20.md) | SME demo steps and tested prompts | Dated demo record; prompt readiness is superseded by newer module materials |

## PRISM research

These are adjacent strategy and investigation documents, not Spire runtime
or module-support specifications.

| Document | Contains | State |
|---|---|---|
| [Unified-Data-Strategy.md](spire-prism/Unified-Data-Strategy.md) | Spire and PRISM integration strategy | Strategy document; no current implementation status declared |
| [platform_comparison.md](spire-prism/platform_comparison.md) | PRISM-versus-Spire comparison | Comparison document; check assumptions before reuse |
| [fusion-data-explorer-2026-10-28.md](spire-prism/fusion-data-explorer-2026-10-28.md) | Fusion Data Explorer technical handover | Dated report marked complete; separate project |
| [prism-website-2026-10-28.md](spire-prism/prism-website-2026-10-28.md) | PRISM marketing-site investigation | Dated investigation report; separate repository/project |

## Prompt sets and validation

| Document | Contains | State |
|---|---|---|
| [prompts/README.md](../prompts/README.md) | Prompt-set layout, tier meanings, and corpus notes | Prompt-set guide; its link to `docs/prompt-sets/SURFACE.md` does not resolve in the current inventory |
| [PROMPT_COUNTS.md](../prompts/PROMPT_COUNTS.md) | Counts of prompts by capability and tier | Snapshot dated 2026-10-10; recount after prompt-set changes |
| [release_gate_baseline.md](../prompts/release_gate/release_gate_baseline.md) | Release-gate runtime and pass/fail baseline | Run dated 2026-09-29; historical baseline |
| [PROMPT_SHEET_2026-11-21.md](../prompts/sme_module_a/PROMPT_SHEET_2026-11-21.md) | Pod-verified fill values and readiness notes for 40 SME prompts | Dated validation sheet; verify live values before a new demo |
| [sme_module_a_expected.md](../prompts/sme_module_a/sme_module_a_expected.md) | Expected answers, fill values, readiness ledger, and scoring notes | Module A test reference captured 2026-11-21; pair with the runnable litmus set |
| [tests/manual/ui/checklist.md](../tests/manual/ui/checklist.md) | Manual startup and UI checks | Manual checklist; run before UI-affecting merges |
| [spire_sme_validation_checklist.md](../tests/spire_sme_validation_checklist.md) | Black-box SME validation procedure and scope | Validation checklist; its stated scope is historical and narrower than current module coverage |

## Generated context captures

Files in `context_out/` are generated context bundles, not maintained
documentation. Regenerate them from their source files before relying on
them; do not treat them as the source of truth.

| Document | Captured content | State |
|---|---|---|
| [SQL_EMITTER_SCHEMA_CORPUS.md](../context_out/SQL_EMITTER_SCHEMA_CORPUS.md) | Named SQL-emitter schema corpus bundle | Present but empty at review time |
| [current_overlay_and_emitter.md](../context_out/current_overlay_and_emitter.md) | SQL overlay and emitter source context | Generated snapshot |
| [diag_kg_schema.md](../context_out/diag_kg_schema.md) | KG schema SQL context | Generated snapshot |
| [schema_po_subset.md](../context_out/schema_po_subset.md) | Purchase-order schema subset | Generated snapshot |

## Known stale pointers

The following references were found to point outside the current Markdown
inventory. This map does not silently treat their targets as existing:

- The previous version of this index linked to absent `audit/`,
  `plan/HANDOFF.md`, `fixes/FIXES.md`, and `design/FEATURES.md`.
- [prompts/README.md](../prompts/README.md) points to absent
  `docs/prompt-sets/SURFACE.md`.
- [EXTENDING.md](design/sql_overlay/EXTENDING.md) points to absent
  `docs/design/SQL_OVERLAY_POC.md`.
- *(Resolved 2026-11-28.)* `WORKING_STYLE.md` used to point at
  `SESSION_STARTUP_CHECKLIST.md`, Doc A / Doc B, and a runtime clone layout
  that no longer exists. Those references were removed when the two
  working-style documents were merged into one; the file now describes only
  what is in the tree.

## Updating this map

When adding or moving a Markdown document, update the relevant table here.
Keep status descriptions document-level and evidence-based: distinguish a
dated snapshot, an explicitly live queue, a design/reference, and a generated
capture. Do not imply that a document's claims have been re-tested unless
they have.
