# supplier/smoke

6 prompts, 1 refusal, 2 truncations, exit 0.

## Classification

| prompt | class | note |
|---|---|---|
| Count of suppliers | pass | 695 full-set count, not sample |
| Get list of active suppliers | pass | 25 rows, honest disclosure |
| Addresses for supplier 1252 | pass | 25 addresses, no truncation disclosure |
| Suppliers with their addresses | pass | 25 of 695, honest disclosure |
| Show supplier EIP Inc and its contacts | pass | 10 contacts, matches child_as_root prompt 4 |
| show me contract renewals due next quarter | pass | correct refusal, unknown_entity |

## Cross-set confirmations

- Prompt 4 matches truncation prompt 3 (Suppliers with their addresses).
- Prompt 5 matches child_as_root prompt 4 (show contacts for supplier EIP Inc).
- Prompt 6 matches refusals prompt 1 and dipstick prompt 6. Same refusal
  class. Wording differs slightly across sets but the class is the same.

## Observation (repeated from dipstick, now doubly confirmed)

Prompt 3 "Addresses for supplier 1252" has no truncation disclosure.
Same shape as dipstick prompt 3. Two sets, same prompt, same missing
"Showing N of M" header and same missing Truncation line.

Cannot tell from the logs whether 25 is a truncation limit or the true
count. Recorded as observation, not a candidate.

## Candidates

None.
