# procurement/smoke

5 prompts, 1 refusal, 1 truncation, exit 1.

## Classification

| prompt | class | note |
|---|---|---|
| What is purchase order 2144 about? | pass | 1 record, correct |
| Show PO 2144 and its lines | pass | header + 2 lines |
| Show PO 2144 and its distributions | pass | header + schedules + distributions |
| Purchase orders created before 2015 | pass | 25 of 878, status breakdown matches table |
| purchase orders | pass | correct refusal, missing_identifier |

## F-052 signature

- One Reason line at 293.
- No ERROR banner.
- File ends after the refusal.
- Matches F-052 at signature level.

## Observation

- Prompt 4's plan names the output bucket open_pos, but the prompt asks
  for "created before 2015", not "open". Internal naming only. Does not
  affect the answer.
