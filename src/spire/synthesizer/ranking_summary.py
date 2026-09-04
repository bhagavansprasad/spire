"""Local summary generation for aggregation results — no LLM call.

Companion to local_summary.py, which does the same job for ENTITY LISTS.
Kept separate because the two share no rules. An entity list is a SET and
the interesting facts about it are shape facts — what is uniform, what
splits, how many categories. An aggregation is ORDERED or PARTITIONED and
the interesting facts are position and magnitude — who leads, by how
much, which bucket dominates.

Feeding ranked rows to local_list_summary produces nothing: five supplier
names in five rows trip its distinct-ratio guard, and five distinct
floats read as descriptive. It would return the counts line alone. That
is not a bug in it; it is the wrong function.

WHAT THE MODEL WAS DOING HERE
=============================

Measured 2026-08-04 on "top 5 suppliers by spend":

    synthesize   in=1004  out=1880

1,880 output tokens for five rows and one paragraph. The ranking was
already computed — aggregate_invoices.py does the grouping, the summing
and the sort — and handed over so the model could retype it field by
field. That is the expensive half, and it is the half where a dropped
field goes unnoticed: the id validators catch invented suppliers, not
missing amounts.

The prose it produced:

    "This report ranks suppliers by total spend. The date range for this
    analysis is not specified. It shows the top 5 out of 117 suppliers.
    Staffing Services is the top supplier with a total spend of
    $284,449,939.51, followed by JGA with $102,877,202.30. As the data is
    truncated, these totals are based on a sample of invoices and may
    understate actual spend."

Six sentences. Two are padding ("this report ranks suppliers by total
spend" restates the heading printed below it). One is a sentence about
two null fields — date_from and date_to were both None, and rather than
say nothing the model announced their absence. The remaining three are
facts the bucket already holds.

WHAT THIS MODULE WILL NOT SAY
=============================

**Nothing about dates.** date_from/date_to are echoed back by
aggregate_invoices and are usually None. There is no sentence worth
writing about a filter the user did not apply.

**No concentration for rankings.** "The top 5 account for N% of total
spend" is the natural next statement and it CANNOT BE COMPUTED. The
denominator does not survive: _aggregate_rows ranks every supplier and
then returns ranked[:top_n], so the spend of suppliers 6..117 is
discarded inside the tool. total_suppliers is a COUNT, not a sum.
Computing the percentage over the visible five would produce 100% every
time, which is the arithmetic-over-a-sample defect this whole thread
exists to remove.

The two DISTRIBUTION shapes are the exception and the reason the split
into three functions is real rather than cosmetic: po_status_breakdown
carries total_ordered and receipt_method_distribution carries
total_amount, both grand totals across every bucket. There the share IS
derivable, and it is the most useful thing to say.

SHAPES, AND WHY THEY NEEDED ENUMERATING
=======================================

The six were read end to end before this was written, and they disagree
in ways that would each have broken a function generalised from the
first one or two:

    shape                        rows  count key      truncated
    supplier_spend_ranking        yes  invoice_count    yes
    supplier_po_value_ranking     yes  po_count         yes
    exposure_ranking              yes  NONE             NO
    po_status_breakdown           yes  po_count         yes
    receipt_method_distribution   yes  receipt_count    yes
    open_po_summary               NO   n/a              yes

open_po_summary has no rows at all — three scalars — so a row-walking
function cannot touch it. exposure_ranking has no truncated key, so the
truncation check must be absent-safe rather than False-safe. And the
measure is spelled three ways across the six (total_spend, total_ordered,
total_amount), as is the count (invoice_count, po_count, receipt_count).

EXPOSURE IS NOT LIKE THE OTHER TWO RANKINGS
===========================================

rank_customer_accounts_by_exposure does no arithmetic. open_receivables
and transactions_due come straight off the pod per account; the tool
sorts and cuts, nothing more. It carries TWO measures, and it is sorted
on TotalOpenReceivablesForAccount only:

    key=lambda x: x.get("TotalOpenReceivablesForAccount") or 0

So open_receivables is the measure the leader statement may quote.
Quoting transactions_due would name a figure that is not why the account
is first — fluent, and wrong, which is the exact failure mode being
removed here.

(Noted in passing, not fixed here: that sort has no tiebreaker, unlike
the other two rankings which sort on (-measure, name). Two accounts with
equal open receivables can swap places between runs.)
"""

from __future__ import annotations

from typing import Any


# Per-shape field mapping. The six tools were written at different times
# and named the same concepts differently; this is the translation table
# and nothing more. Deliberately data rather than code — the mapping
# genuinely varies only by field name, unlike the three SHAPES, which
# vary structurally and so get three functions.
_RANKING_FIELDS: dict[str, dict[str, Any]] = {
    "supplier_spend_ranking": {
        "label_key": "supplier",
        "measure_key": "total_spend",
        "total_key": "total_suppliers",
        "entity_label": "suppliers",
        # WHAT WAS FETCHED, which on a ranking is not what was ranked.
        # total_available and examined count INVOICES; total_suppliers
        # counts the distinct suppliers those invoices grouped into.
        # Labelling the truncation note with entity_label would print
        # "25,000 of 48,931 suppliers examined" over a pod holding 117
        # suppliers — a wrong number stated with total confidence, which
        # is the exact failure this module exists to remove. Caught while
        # wiring the note, not by a test.
        "source_label": "invoices",
        "measure_label": "spend",
    },
    "supplier_po_value_ranking": {
        "label_key": "supplier",
        "measure_key": "total_ordered",
        "total_key": "total_suppliers",
        "entity_label": "suppliers",
        "source_label": "purchase orders",
        "measure_label": "committed value",
    },
    "invoice_amount_ranking": {
        # Rows are individual invoices, so the keys are the raw invoice field
        # names and the "entity" ranked IS the source (no grouping step).
        "label_key": "InvoiceNumber",
        "measure_key": "InvoiceAmount",
        "total_key": "total_available",
        "entity_label": "invoices",
        "source_label": "invoices",
        "measure_label": "amount",
    },
    "exposure_ranking": {
        "label_key": "customer_name",
        # The sort key, not transactions_due. See module docstring.
        "measure_key": "open_receivables",
        "total_key": "total_accounts",
        "entity_label": "accounts",
        # The one shape where source and entity coincide: the tool
        # fetches accounts and ranks accounts, with no grouping step.
        "source_label": "accounts",
        "measure_label": "open receivables",
    },
}

_DISTRIBUTION_FIELDS: dict[str, dict[str, Any]] = {
    "po_status_breakdown": {
        "label_key": "status",
        "measure_key": "total_ordered",
        "grand_total_key": "total_ordered",
        "grand_count_key": "total_pos",
        "entity_label": "purchase orders",
        # Distributions partition what they fetched, so the two labels
        # agree here — unlike the rankings above, where a grouping step
        # sits between them.
        "source_label": "purchase orders",
    },
    "receipt_method_distribution": {
        "label_key": "receipt_method",
        "measure_key": "total_amount",
        # Same spelling as the row measure. Reading the wrong one gives a
        # share of itself — always 100%.
        "grand_total_key": "total_amount",
        "grand_count_key": "total_receipts",
        "entity_label": "receipts",
        "source_label": "receipts",
    },
}


# Below this multiple, the gap between first and second is not worth
# stating. Measured 2026-08-04 on two real rankings:
#
#   supplier spend      284,449,939 vs 102,877,202   ->  2.8x
#   account exposure    165,428,563 vs 143,551,790   ->  1.2x
#
# The first is a finding: one supplier is nearly three times the next and
# nothing on screen announces it. The second is noise — five accounts
# spanning 165M to 119M, with rows three and four inside 0.1% of each
# other. "Motique Gym leads with X — 1.2x the next" implies a separation
# the column already shows to be absent.
#
# Same principle as _MAX_DISTINCT_RATIO in local_summary.py: a
# technically-true observation about a column the reader is looking at is
# noise, and the guard is there to say nothing rather than something
# unhelpful.
#
# 1.5 is chosen by eye from those two cases, not measured across a set —
# the first thing to revisit if a ranking reads wrong. The leader is
# still named below the threshold; only the multiple is dropped.
_MIN_GAP_RATIO = 1.5


def _money(value: Any) -> str:
    """Format a measure the way the table below it does.

    Thousands separated, two decimals. The summary sitting one line above
    a table that formats differently is the same inconsistency that made
    records render two ways depending on code path, in miniature.
    """
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value:,.2f}"


def _num(value: Any) -> str:
    """Format a plain count."""
    if not isinstance(value, int):
        return "—"
    return f"{value:,}"


def _truncation_note(
    bucket: dict, what: str, entity_label: str = "records"
) -> list[str]:
    """The one sentence worth writing about a capped fetch.

    .get() rather than [] because exposure_ranking has no truncated key
    at all — absent means "the tool cannot be incomplete", which is true
    of that endpoint (435 rows, fetched whole).

    SAYS HOW MUCH IS MISSING, WHEN THE TOOL KNOWS. Until 2026-08-04 this
    read "the fetch stopped at the page cap, so these figures are lower
    bounds". True, and far too quiet. Measured that day:

        /invoices    25,000 examined of 48,931   51%
        /purchaseOrders (before the page-size fix)
                     10,000 examined of 15,839   63%

    The second case understated one status by 860 million and read like a
    complete answer with a footnote. "Lower bound" does not tell a reader
    whether the shortfall is one row or half the collection, and that is
    the only thing they need to know in order to judge the number.

    The counts come from total_available and examined, which the fetch
    helper now puts on every bucket it returns. Both absent — an older
    tool, or a pod that returned no count — falls back to the original
    sentence, which is everything that can honestly be said without them.

    No warning symbol. It renders inconsistently across terminals and
    log viewers, and a word carries the same weight without the risk.
    """
    if bucket.get("truncated") is not True:
        return []

    total = bucket.get("total_available")
    examined = bucket.get("examined")

    if isinstance(total, int) and isinstance(examined, int) and total > 0:
        return [
            f"PARTIAL: {examined:,} of {total:,} {entity_label} examined "
            f"({examined / total:.0%}). These {what} are lower bounds."
        ]

    return [
        f"The fetch stopped at the page cap, so these {what} "
        f"are lower bounds — there may be more."
    ]


def _ranking_summary(bucket: dict, shape: str) -> list[str]:
    """Summary for an ordered top-N ranking.

    Three statements, in this order:

      1. Counts — "Top 5 of 117 suppliers by spend."
      2. Leader and gap — "Staffing Services leads with X — 2.8x the next."
      3. Truncation, when flagged.

    Each is omitted when it would not be true or would restate the table.
    """
    fields = _RANKING_FIELDS[shape]
    rows = bucket.get("rows") or []
    entity_label = fields["entity_label"]

    # Zero rows is an ANSWER, said plainly, not an error and not silence.
    # (OUT-01, and the same rule local_list_summary follows.)
    if not rows:
        return [f"No {entity_label} matched."]

    out: list[str] = []
    returned = bucket.get("returned")
    if not isinstance(returned, int):
        returned = len(rows)
    total = bucket.get(fields["total_key"])

    # ---- 0. how complete this answer is ----
    #
    # FIRST, not last. It used to sit at the bottom, which is where the
    # model put it too: state the figures, then hedge. If an answer covers
    # 51% of the collection, that is not a closing caveat — it is the
    # thing a reader needs before they read the numbers, because it
    # decides whether the numbers are worth reading at all.
    out.extend(
        _truncation_note(bucket, "totals", fields["source_label"])
    )

    # ---- 1. counts ----
    #
    # Only when there is something the reader CANNOT see. The 117 appears
    # nowhere on screen; the 5 is the row count of the table printed
    # directly below. Stating "5 suppliers" above five rows is the
    # paragraph problem in miniature.
    if isinstance(total, int) and total > returned:
        out.append(
            f"Top {returned} of {_num(total)} {entity_label} "
            f"by {fields['measure_label']}."
        )

    # ---- 2. leader and gap ----
    #
    # The ratio is the fact a reader cannot get by glancing: two large
    # numbers side by side do not announce that one is nearly three times
    # the other. One row means there is no gap to state.
    leader = rows[0]
    name = leader.get(fields["label_key"]) or "(unnamed)"
    measure = leader.get(fields["measure_key"])

    if len(rows) >= 2 and isinstance(measure, (int, float)):
        second = rows[1].get(fields["measure_key"])
        # Positive divisor only. A zero or negative second value makes the
        # ratio meaningless or misleading, and exposure figures can be
        # None — in every such case say the leader without the comparison
        # rather than compute something unsayable.
        #
        # And a ratio below _MIN_GAP_RATIO is dropped even though it
        # computes cleanly: see the constant for the two measured cases
        # that motivate it.
        if (
            isinstance(second, (int, float))
            and second > 0
            and measure / second >= _MIN_GAP_RATIO
        ):
            ratio = measure / second
            out.append(
                f"{name} leads with {_money(measure)} — "
                f"{ratio:.1f}x the next."
            )
        else:
            out.append(f"{name} leads with {_money(measure)}.")
    elif isinstance(measure, (int, float)):
        out.append(f"{name} leads with {_money(measure)}.")

    return out


def _distribution_summary(bucket: dict, shape: str) -> list[str]:
    """Summary for a partition into buckets.

    Unlike a ranking, a distribution carries its own grand total, so the
    dominant bucket's SHARE is derivable — but only when the fetch was
    complete. See below.
    """
    fields = _DISTRIBUTION_FIELDS[shape]
    rows = bucket.get("rows") or []
    entity_label = fields["entity_label"]

    if not rows:
        return [f"No {entity_label} matched."]

    out: list[str] = []
    grand_total = bucket.get(fields["grand_total_key"])
    truncated = bucket.get("truncated") is True

    # ---- 0. how complete this answer is ---- (see _ranking_summary)
    out.extend(
        _truncation_note(bucket, "figures", fields["source_label"])
    )

    # ---- 1. how many groups ----
    #
    # The grand count and grand total are NOT stated here. The display
    # formatter already prints both on its own line:
    #
    #     Total receipts: 5000, total amount: 874,836,787.64
    #
    # Measured 2026-08-04 — an earlier version of this function opened
    # with "5,000 receipts, 874,836,787.64 in total, across 4 groups",
    # which duplicated the formatter word for word. Same lesson as
    # open_po_summary: the formatter line is shared with the LLM path and
    # stays; the summary says what the formatter cannot.
    #
    # The group count is not on that line, and it is not trivially
    # countable from a long list, so it survives.
    # "Across 1 groups." was printing whenever a distribution had a single
    # bucket — visible on the receipt distribution while its fetch was
    # capped at 5,000 rows and returned three methods, and on any
    # single-status PO breakdown. The same defect local_summary._count_phrase
    # exists to fix, reappearing here because this module was written
    # separately and did not reuse it.
    #
    # Not reused now either: _count_phrase takes a plural label and
    # derives the singular, which is the right shape for "25 suppliers"
    # but heavier than one word needs. If a third caller appears, share it.
    group_word = "group" if len(rows) == 1 else "groups"
    out.append(f"Across {len(rows)} {group_word}.")

    # ---- 2. the dominant bucket, and its share only when it is real ----
    #
    # Rows arrive sorted by measure descending from every distribution
    # tool, so rows[0] is the largest without re-sorting here.
    #
    # THE SHARE IS SUPPRESSED WHEN THE FETCH WAS TRUNCATED, and this was
    # got wrong first time round. Measured on "receipts by receipt
    # method": the run reported exactly 5,000 receipts with truncated
    # true — a page cap, not a count — and this function printed
    # "Lockbox is the largest at 869,350,062.55 (99% of the total)".
    #
    # That is a ratio of two lower bounds presented as a share of the
    # whole: precisely the arithmetic-over-a-sample defect this module
    # exists to remove, reintroduced in the one shape where the grand
    # total looked trustworthy enough to divide by. A truncation sentence
    # printed underneath does not repair it — stating the figure and then
    # hedging it is what the model used to do.
    top = rows[0]
    label = top.get(fields["label_key"]) or "(unknown)"
    measure = top.get(fields["measure_key"])

    if isinstance(measure, (int, float)):
        if (
            not truncated
            and isinstance(grand_total, (int, float))
            and grand_total > 0
        ):
            share = measure / grand_total * 100
            out.append(
                f"{label} is the largest at {_money(measure)} "
                f"({share:.0f}% of the total)."
            )
        else:
            # Truncated, or no usable grand total: the figure is still
            # true, the proportion is not.
            out.append(f"{label} is the largest at {_money(measure)}.")

    return out


def _scalar_summary(bucket: dict) -> list[str]:
    """Summary for open_po_summary — the truncation note, and nothing else.

    This function used to state the three figures. Measured 2026-08-04
    against the pod, that produced:

        1,085 open purchase orders worth 32,790,396.90, across 66 suppliers.
        Open PO count: 1085, total ordered: 32,790,396.90, suppliers: 66

    Both lines correct, both saying the same thing. The second is the
    display formatter rendering po_count, total_ordered and
    supplier_count — it was always there, and the model's paragraph read
    as a recap rather than a duplicate because it was longer and vaguer.
    Removing the model made the duplication visible, which is the third
    time in this project that taking a layer out exposed what it was
    covering for.

    The formatter line is the one that stays: it is shared with the LLM
    path, so changing it has a blast radius this shape does not justify.

    What is NOT in the formatter line is the truncation state, so that is
    what survives here. An empty list is a valid and complete answer for
    this shape — a summary with nothing to add prints nothing rather than
    padding.
    """
    if bucket.get("po_count") == 0:
        # The formatter still prints three zeroes, which reads as a
        # malfunction rather than an answer. Saying it plainly is the one
        # case where a sentence beats the scalars. (OUT-01.)
        return ["No open purchase orders."]

    return _truncation_note(bucket, "figures", "purchase orders")


def local_aggregation_summary(bucket: dict) -> list[str] | None:
    """Build summary statements for an aggregation result, without an LLM.

    Args:
        bucket: The single dict an aggregation tool returned, as the
            executor holds it under the "aggregation" output. Carries a
            "shape" tag identifying which of the six it is.

    Returns:
        Statements, one fact each — or None when the shape is not one this
        module handles.

        None and [] mean different things and the caller must not conflate
        them. None is "I do not know this shape, fall back to the model".
        [] is "I know this shape and there is nothing worth saying", which
        is a valid answer for a summary printed above a table that already
        shows everything.
    """
    if not isinstance(bucket, dict):
        return None

    shape = bucket.get("shape")
    if not isinstance(shape, str):
        return None

    if shape in _RANKING_FIELDS:
        return _ranking_summary(bucket, shape)
    if shape in _DISTRIBUTION_FIELDS:
        return _distribution_summary(bucket, shape)
    if shape == "open_po_summary":
        return _scalar_summary(bucket)

    # A seventh aggregation tool added later lands here and keeps working
    # through the model until someone adds it above. Silent fallback is
    # right for a summary; it would be wrong for a record builder.
    return None
