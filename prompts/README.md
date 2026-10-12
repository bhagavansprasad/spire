# SPIRE prompt sets

The quality standard for Spire: what the product must survive.

Full capability surface, tier plan, and legacy cross-walk:
`docs/prompt-sets/SURFACE.md`.

## Layout

Two axes, one tree.

**Capabilities** are folders. Each holds three tier files.

~~~
prompts/
  supplier/                supplier_smoke.txt  supplier_verify.txt  supplier_exhaust.txt
  payables/                payables_smoke.txt  payables_verify.txt  payables_exhaust.txt
  procurement/             procurement_smoke.txt  procurement_verify.txt  procurement_exhaust.txt
  receivables/             receivables_smoke.txt  receivables_verify.txt  receivables_exhaust.txt
  payables_supplier/       payables_supplier_smoke.txt  payables_supplier_verify.txt  payables_supplier_exhaust.txt
  payables_procurement/    payables_procurement_smoke.txt  payables_procurement_verify.txt  payables_procurement_exhaust.txt
  procurement_supplier/    procurement_supplier_smoke.txt  procurement_supplier_verify.txt  procurement_supplier_exhaust.txt
~~~

**Cross-cutting features** are flat files at the root, named
`<tier>_<feature>.txt`.

~~~
prompts/
  columns/                columns_smoke.txt  columns_verify.txt  columns_exhaust.txt
  refusals/               refusals_smoke.txt  refusals_verify.txt  refusals_exhaust.txt  refusal_examples.txt
  lifecycle/              lifecycle_smoke.txt  lifecycle_verify.txt  lifecycle_exhaust.txt
  child_as_root/          child_as_root_smoke.txt  child_as_root_verify.txt  child_as_root_exhaust.txt
  truncation/             truncation_smoke.txt  truncation_verify.txt  truncation_exhaust.txt
  date_filters/           date_filters_smoke.txt  date_filters_verify.txt  date_filters_exhaust.txt
  fields_and_include/     fields_and_include_smoke.txt  fields_and_include_verify.txt  fields_and_include_exhaust.txt
  modes/                  modes_smoke.txt  modes_verify.txt  modes_exhaust.txt
  dipstick/               dipstick_smoke.txt  dipstick_verify.txt  dipstick_exhaust.txt
  scorer/                 parser_stress.txt  tool_selection.txt
  sme/                    testcases.txt
  retest/                 prompts.txt
~~~

**Other files, no tier:**

- `sme/sme_testcases.txt` — external QA corpus, verbatim, no runner contract.
- `refusals/refusals_refusal_examples.txt` — the refusal Examples from `capability.py`, enforced by `tests/test_nl_parser_capability.py`.
- `scorer/` — parser-scorer corpora in a different format (`EXPECT ||| prompt`). Not for promptkit.
- `retest/retest_prompts.txt` — pending fold-in to its targets.

## Tiers

| Tier | Purpose | Size | Runtime |
|---|---|---|---|
| `smoke` | Alive — does it work at all. Every prompt must answer. | 5-10 | Seconds |
| `verify` | Correct — normal shapes, edges, refusals. | 20-40 | Minutes |
| `exhaust` | Stress — every variation we know. Goal: find a crash. | 50+ | Overnight |

Same capability, increasing depth. A smoke prompt is not repeated in verify;
verify adds paraphrases, siblings, boundary cases. Exhaust adds every
documented variation, every vocabulary value, every filter combination.

## Running

The MCP server must be up.

**One set:**

~~~
python scripts/promptkit.py --run --prompt-file prompts/supplier/supplier_smoke.txt
~~~

**A module (all three tiers):**

~~~
python scripts/promptkit.py --run --prompt-file \
    prompts/supplier/supplier_smoke.txt \
    prompts/supplier/supplier_verify.txt \
    prompts/supplier/supplier_exhaust.txt
~~~

**Everything, via the manifest:**

~~~
python scripts/promptkit.py --run --manifest scripts/manifests/promptkit_sets.yaml
~~~

The manifest lists 49 sets in tier order — smoke first, then verify, then
the external corpus, then exhaust. Comment out the exhaust block for a
faster pass.

## Reading the results

**The summary line proves nothing.** A tally has previously reported
"38/38 ran cleanly" while several prompts were being wrongly REFUSED.
Read the ANSWERS.

Score each prompt:

- **pass** — right rows, right claims.
- **fail** — errored, refused when it should not have.
- **wrong but did not error** — the one that matters.

For the third bucket, check specifically:

- an empty data array behind confident narrative prose
- a page count stated as a total ("25 suppliers" where 450 exist)
- a total, average or trend computed over a truncated sample and stated as fact
- claims about fields absent from the displayed projection
- customer-scoped results that never resolve an AccountNumber
- a generalisation true of the first few rows but not the set

Do not print a raw exit code beside each prompt in a loop. A screen of
`exit=4` reads as a screen of crashes even to someone who knows exit 4 is
a refusal.

## Where a set starts

`prompts/dipstick/dipstick_smoke.txt` is depth-ordered on purpose. If depth 2 fails,
the filter layer is broken and every later failure is probably downstream
of it. Run it first and read it first.

If a whole set refuses, check the KG before anything else:

~~~
python scripts/rebuild_kg.py
python scripts/print_kg.py --counts-only
~~~

## Adding prompts

A new prompt goes in the file whose capability it tests, at the tier its
depth warrants. Do not create a new file for a single prompt; extend the
capability's file.

When a bug is fixed, its V1 reproducer from the fix file lands in the
tier of the capability it belongs to. The `exhaust` tier is where those
reproducers live by default — they test an edge that has already bitten.
