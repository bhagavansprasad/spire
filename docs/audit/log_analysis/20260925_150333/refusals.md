# refusals/smoke

4 prompts, 3 refusals, 1 truncation, exit 0.

## Classification

| prompt | class | note |
|---|---|---|
| show me contract renewals due next quarter | pass | correct refusal, unknown_entity |
| show me purchase order line items | pass | correct refusal, unknown_entity |
| who should we stop buying from | pass | correct refusal, unsupported_filter |
| active suppliers in US | pass | 25 rows, honest disclosure |

## Notes

- Three refusals, exit 0. Last prompt is a real answer.
- Supports the position hypothesis: exit code appears tied to the final
  prompt, not to the set containing refusals.
