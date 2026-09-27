# dipstick/smoke

6 prompts, 1 refusal, 1 truncation, exit 0.

## Classification

| prompt | class | note |
|---|---|---|
| Count of suppliers | pass | "There are 695 suppliers"; full-set count, not sample |
| Get list of active suppliers | pass | 25 rows, honest disclosure |
| Addresses for supplier 1252 | pass | 25 addresses rendered, 13 countries |
| Show PO 2144 and its lines | pass | identical to procurement prompt 2 |
| Show me AR invoices for customer ABC Corporation Americas | pass | AccountNumber 26370 resolved, 25 of 486 |
| Show me contract renewals due next quarter | pass | correct refusal, unknown_entity |

## Cross-set consistency

- Prompt 4 "Show PO 2144 and its lines" matches procurement/smoke
  prompt 2 identically. Cross-set consistency confirmed.
- Prompt 6 "Show me contract renewals due next quarter" matches
  refusals/smoke prompt 1: same refusal class (unknown_entity). Cross-set
  consistency confirmed.

## Observation (not a candidate)

Prompt 3 "Addresses for supplier 1252":

- Answer opens with "The data shows 25 addresses associated with the
  supplier Lee Supplies (Supplier Number 1252)."
- No "Showing 25 of N" header.
- No Truncation line.

Every other list-shaped answer in this run discloses either
"Showing N of M" or "the true matching count is not known". This is the
one list-shaped answer with no truncation disclosure.

Two possible explanations: (a) the Address tool returned no total; (b)
there really are exactly 25 addresses for supplier 1252. Cannot
distinguish from the log alone.

If verifiable and >25, this would be a candidate. Left as observation
for now.

## Candidates

None at this time. Observation may be promoted.
