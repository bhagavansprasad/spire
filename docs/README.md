# SPIRE — Docs Index

Six buckets. One README. Max depth 3.

| Folder | What lives here |
|---|---|
| [`00-plan/`](00-plan/) | The frozen plan, session logs per phase, working style, the handoff. |
| [`01-audit/`](01-audit/) | Phase 1 audit, findings log, the byte-equality goldens. |
| [`02-fixes/`](02-fixes/) | The Phase 2 fix plan, all fix records in one file, per-finding evidence. |
| [`03-design/`](03-design/) | Architecture (cache, context bundles), future feature designs, UML/design diagrams. |
| [`04-reference/`](04-reference/) | Fusion endpoints reference, images, PDFs, data files. |
| [`05-prompts/`](05-prompts/) | Prompt-set surface doc. |

## Where to start

- **New session?** [`00-plan/HANDOFF.md`](00-plan/HANDOFF.md) first.
- **Working a bug?** [`02-fixes/FIX_PLAN.md`](02-fixes/FIX_PLAN.md) is the live queue.
- **Reading a fix?** [`02-fixes/FIXES.md`](02-fixes/FIXES.md) — all F-NNN records, F-number order.
- **Checking a Fusion fact?** [`04-reference/spire_fusion_endpoints_reference.md`](04-reference/spire_fusion_endpoints_reference.md).

## Rules

1. New finding → append to `02-fixes/FIXES.md`, not a new file.
2. New evidence capture → new file under `02-fixes/evidence/`. The only exception.
3. New session entry → prepend to the current `00-plan/0N_Phase_*.md`.
4. New feature design → append to `03-design/FEATURES.md`.
5. New endpoint fact → append to `04-reference/spire_fusion_endpoints_reference.md`.
6. Generated context bundles go to `context_out/`, never in `docs/`.

