# procurement_supplier/smoke

2 prompts, 0 refusals, 2 truncations, exit 0.

## Classification

| prompt | class | note |
|---|---|---|
| purchase orders for supplier EIP Inc | pass | 25 of 2013, buyer breakdown 8+8+5+4=25, matches table |
| suppliers with open purchase orders | wrong-but-no-error | see C-003 |

## F-010 relevance

Prompt 2 plan step 2 does NOT set `filter_source_when_nonempty`. Step 1
returns the first 25 suppliers without filter. Answer lists all 25,
including nine with Open POs = 0.

Compare payables_supplier prompt 2, which DOES set
`filter_source_when_nonempty: True` and filters the source list.

## Candidates

- C-003: suppliers with open purchase orders shows suppliers with zero
  open POs.
