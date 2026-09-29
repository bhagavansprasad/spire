# SPIRE — Session Handoff, 2026-09-29 (window 26, four-prompt triage)

**Scope of this handoff.** Four prompts were run against the pod on
2026-09-29. Three produced defects; one passed. This handoff covers
only those four prompts, their results, and the agenda to fix them.
The previous window's record (F-053, F-055, process-doc hardening) is
in `git log` on `hardening-master`; it is not restated here.

**Read this first.** Then `docs/plan/WORKING_STYLE.md` (R + S0–S11),
then `docs/fixes/FIXES.md` (the playbook).

---

## Where we are

**Branch:** `master`. This session ran and was tested on `master`,
not `hardening-master`.

**Pod:** dev instance, MCP 4001 / API 4002 / UI 4003.

**Test suite:** not re-run this session.

---

## The four prompts

| # | prompt | result |
|---|---|---|
| 1 | Count of suppliers | FAIL |
| 2 | Show PO 2144 and its lines | PASS |
| 3 | Which suppliers have open purchase orders? | FAIL |
| 4 | Top 5 suppliers by spend this year | PARTIAL |

Raw captures (gitignored; on disk at handoff time):
`t_test_1_count.txt`, `t_test_2_po2144.txt`,
`t_test_3_open_pos.txt`, `t_test_4_top5.txt`.

Reproduce with:

    python scripts/promptkit.py --run --prompt "Count of suppliers" --show-planner > t_test_1_count.txt 2>&1
    python scripts/promptkit.py --run --prompt "Show PO 2144 and its lines" --show-planner > t_test_2_po2144.txt 2>&1
    python scripts/promptkit.py --run --prompt "Which suppliers have open purchase orders?" --show-planner > t_test_3_open_pos.txt 2>&1
    python scripts/promptkit.py --run --prompt "Top 5 suppliers by spend this year" --show-planner > t_test_4_top5.txt 2>&1

---

## P1 — Count of suppliers — FAIL

Answer, verbatim:

    There are 25 suppliers.

25 is the page size of the source fetch, not the pod total. The
`Outputs:` block shows `suppliers: 25 record(s)` — a capped page — and
there is no `Truncation:` block in the answer. A correct answer would
name the pod total (thousands on this pod; the window-18 golden
`count_suppliers.txt` said 431, and later runs have shown 6,500+).

Suspected site: `synthesizer/aggregation.py::_build_count_response`,
on the plain unfiltered-count path. When
`truncation["suppliers"]["total_available"]` is None the function
falls to `len(bucket)`. Two candidates, neither confirmed:

  - `search_suppliers` stopped reporting `totalResults`.
  - `truncation_by_step` did not reach the synthesizer for this shape.

Confirm at R, then walk S0–S11.

---

## P2 — Show PO 2144 and its lines — PASS

Matches the golden `po_2144_and_lines.txt`: 1 PO row, 2 lines, buyer
`Gee, May`, site `EIP US1`, contact `John Kim`. No work.

---

## P3 — Which suppliers have open purchase orders? — FAIL

Intent and plan are correct:

    Intent:  target_entity: Supplier
             filters: [{'type': 'has_open_PO', 'value': True}]

    Step 1:  search_suppliers           {}              → suppliers
    Step 2:  search_purchase_orders     status OPEN,
             filter_source_when_nonempty True
             iterate suppliers.SupplierId → suppliers_has_open_PO

But `Outputs:` shows:

    suppliers: 0 record(s)
    suppliers_has_open_PO: 0 record(s)

Step 1 called `search_suppliers` with an empty arg dict and got zero
rows. The same call in P1 — in this same window, minutes earlier —
returned 25 rows. The only difference between the two prompts:

  - P1 routed to `['supplier']`.
  - P3 routed to `['supplier', 'procurement']`.

Same plan, same tool call, same arg dict. So either the source fetch
failed transiently, or something about the two-module route affects
the fetch. Neither confirmed.

**R first.** Re-run P3 once:

  - `suppliers: 25` → transient; note the flake and move on.
  - `suppliers: 0` again → a finding. Blast radius may be broad —
    the source-fetch path is the entry point to every Supplier query.

---

## P4 — Top 5 suppliers by spend this year — PARTIAL

The ranking works; the date window does not.

Intent, verbatim:

    target_entity: Supplier
    aggregate: {'op': 'by_supplier', 'date_from': None, 'date_to': None, 'top_n': 5}

`date_from` and `date_to` are both None — `this year` was dropped at
parse. The aggregation ran over all time, not the year.

Header, verbatim:

    PARTIAL: 25,000 of 53,843 invoices examined (46%). These totals are lower bounds.
    Top 5 of 248 suppliers by spend.

Truncation disclosure is good. The scope error is silent.

Suspected site: the parser sysprompt. The prompt has rules for
absolute years and months, and vague-recency adjectives (F-048:
`recent` → 3-month default). It has no rule for period-anchored
phrases like `this year`, `this quarter`, `this month`, `last year`
— the model leaves both bounds empty. Sibling shape to F-048. New
finding candidate.

---

## P5 — n/a (only four prompts)

---

## Agenda for the new window

1. **R + S0–S11 on P3.** First action. One re-run settles
   transient-vs-real. If it reproduces, walk the full standard and
   land as an F-NNN; that path touches every Supplier query.
2. **Root-cause P1.** Confirm whether the pod total is missing from
   the source fetch or from the synthesizer wiring. Fix on a branch.
3. **File and fix P4.** New F-NNN for the unparsed period phrases.
   Likely sysprompt-only: teach `this year` → current calendar
   year's bounds, plus its byte-equality mirror in
   `context_assembly.py`.
4. **P2 stays as the sibling that must not regress.**

---

## Rules that keep biting

- **One command at a time (rule 2.1: split on uncertainty, not
  count).**
- **Every file edit is two cells — Python script, then shell
  verification.**
- **Capture complete output to a file, then grep (rule 15.1).**
- **`~~~` for any outer fence whose content contains triple
  backticks.**
- **Name a slow command's cost (rule 15.2).**
- **Branch-first for fixes. PR into the current integration branch.**
- **V0 first — fix file written and committed before any source file
  (FIX_PLAN §8 step 1).**

---

*End of handover.*
