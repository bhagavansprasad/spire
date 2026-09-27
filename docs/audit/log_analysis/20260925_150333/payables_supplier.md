# payables_supplier/smoke

2 prompts, 0 refusals, 2 truncations, exit 0.

## Classification

| prompt | class | note |
|---|---|---|
| Show me invoices for supplier 1252 | pass | same shape as payables prompt 1 |
| suppliers with invoice amount greater than 10000 | pass | F-010 language present |

## F-010 relevance

Prompt 2 plan includes `filter_source_when_nonempty: True` on step 2.

Answer: `Examined 25 of 695 suppliers. Of those 25, 19 match the filter.`

- The count (19) is over the matched bucket, not over all 695.
- The examined-vs-total limitation is disclosed.
- This is consistent with F-010 being fixed for this set.

## Candidates

None.
