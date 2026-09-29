# columns/smoke

5 prompts, 1 refusal, 4 truncations, exit 0.

## Classification

| prompt | class | note |
|---|---|---|
| List active suppliers with supplier name, supplier number, and status | pass | 25 rows, honest disclosure |
| Show me invoices for EIP Inc with invoice number, amount, and date | pass | 25 of 3284, three requested columns |
| Order number and status for purchase orders created before 2015 | pass | breakdown 17/6/2 matches table |
| Just the names of active suppliers | pass | single-column output |
| List active suppliers with supplier name, supplier number, and address | fail | unparseable refusal |

## Candidate

- C-004: prompt 5 refused as unparseable. Parser produced no target_entity.
  Same shape as prompt 1 plus address. truncation prompt 3 with addresses
  succeeded. F-001 adjacent.
