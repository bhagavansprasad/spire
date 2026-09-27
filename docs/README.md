# SPIRE — Docs Index

Six buckets. One README. Max depth 3.

| Folder | What lives here |
|---|---|
| [`plan/`](plan/) | The frozen plan, session logs per phase, working style, the handoff. |
| [`audit/`](audit/) | Phase 1 audit, findings log, the byte-equality goldens. |
| [`fixes/`](fixes/) | The Phase 2 fix plan, all fix records in one file, per-finding evidence. |
| [`design/`](design/) | Architecture (cache, context bundles), future feature designs, UML/design diagrams. |
| [`reference/`](reference/) | Fusion endpoints reference, images, PDFs, data files. |
| [`prompts/`](prompts/) | Prompt-set surface doc. |

## Where to start

- **New session?** [`plan/HANDOFF.md`](plan/HANDOFF.md) first.
- **Working a bug?** [`fixes/FIX_PLAN.md`](fixes/FIX_PLAN.md) is the live queue.
- **Reading a fix?** [`fixes/FIXES.md`](fixes/FIXES.md) — all F-NNN records, F-number order.
- **Checking a Fusion fact?** [`reference/spire_fusion_endpoints_reference.md`](reference/spire_fusion_endpoints_reference.md).

## Rules

1. New finding → append to `fixes/FIXES.md`, not a new file.
2. New evidence capture → new file under `fixes/evidence/`. The only exception.
3. New session entry → prepend to the current `plan/0N_Phase_*.md`.
4. New feature design → append to `design/FEATURES.md`.
5. New endpoint fact → append to `reference/spire_fusion_endpoints_reference.md`.
6. Generated context bundles go to `context_out/`, never in `docs/`.
