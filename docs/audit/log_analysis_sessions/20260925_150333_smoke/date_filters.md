# date_filters/smoke

6 prompts, 0 refusals, 5 truncations, exit 0.

## Classification

| prompt | class | note |
|---|---|---|
| purchase orders created before 2024-01-01 | pass | 25 of 14,387 |
| purchase orders older than 6 months | pass | 25 of 16,937 |
| purchase orders not touched in the last year | pass | 25 of 16,123 |
| invoices in 2024 | pass | 18 rows, true count not known |
| invoices older than 6 months | pass | 25 of 53,359 |
| invoices created before 2024-01-01 | pass | 22 rows, no truncation needed |

## C-001 blast radius

None of these share C-001's mechanism.

| prompt | tool_args | shape |
|---|---|---|
| created before 2024-01-01 | created_before | one-sided upper bound |
| older than 6 months | created_before | one-sided upper bound |
| not touched in the last year | last_updated_before | one-sided upper bound |
| invoices in 2024 | invoice_date_after + _before | bounded |
| invoices older than 6 months | invoice_date_before | one-sided upper bound |
| invoices created before 2024-01-01 | invoice_date_before | one-sided upper bound |

C-001's mechanism is "in the last N" -> date_after only, no upper bound.
None of the six here use that phrasing or that plan shape.

Conclusion: C-001 is one prompt in this batch, not a class.
The mechanism is general (any "in the last N" prompt would trigger it),
but this batch only contains one.

## Candidates

None.
