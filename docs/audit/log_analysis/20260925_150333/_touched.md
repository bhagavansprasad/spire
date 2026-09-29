# 20260925_150333 - F-NNN cross-links

One row per finding this run touched. Appended at the review gate,
after each candidate resolved.

| F-NNN | role | prompt | resolution |
|---|---|---|---|
| F-052 | first observed | List active suppliers with supplier name, supplier number, and address | C-004 to F-052 (closed-as-not-a-bug) |
| F-053 | first observed | suppliers with open purchase orders | C-003 to F-053 (confirmed) |
| F-054 | first observed | invoices in the last 30 days | C-001 to F-054 (closed-as-not-a-bug, latent) |
| F-055 | sibling-surfaced | invoices in the last 7 days | C-005 to F-055 (confirmed) |

Notes:

- F-052 was closed on R: N=20 clean on the same prompt. The shape did
  not reproduce; the original failure was the documented ~3% JSON-mode
  empty-draft mode.
- F-053 was confirmed in one run. Deterministic - the registry
  omission fires every time or never.
- F-054 was closed on latent-shape grounds. The plan is still one-sided;
  the pod no longer carries future-dated rows in the window.
- F-055 was surfaced by R's sibling run - `invoices in the last 7 days`
  refuses on fractional-months conversion. No prompt in the smoke set
  exercised this N.
