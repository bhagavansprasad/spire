"""PROTOTYPE — local summary generation, no LLM call.

Experiment for the rule agreed 2026-08-02: synthesize as much as possible
locally; go to the LLM only if required.

This is not new architecture. `synthesize_response` already returns
before any LLM setup on three paths — count_only, comparison, and
lifecycle — and `_build_count_response` states the pattern in its own
docstring: prefer the authoritative number, say plainly when it is a
lower bound rather than a total. Entity lists are the one path that
still hands everything to the model, and this is that path.

WHAT THE MODEL GOT WRONG THAT CODE CANNOT
=========================================

Measured over eight prompts on 2026-08-02, three runs each, byte
identical every run — these are deterministic defects, not variance:

  "Showing 20 of 426 suppliers"   while 25 rows printed below it
  "total original amount of 254585.25"   summed over a 25-row sample
  "Some suppliers have a Taxpayer Country Code"   a column not displayed

len(rows) cannot be 20 when there are 25. A sum of a displayed column
cannot include rows that were never fetched. A field absent from the
projection cannot be described. Each of these is a defect only because
a language model was asked to do arithmetic and inventory.

WHAT THE MODEL IS STILL BETTER AT
=================================

Deciding what is worth saying. "All 25 are ACTIVE" is a judgement about
which of many possible observations matters to this reader. The rules
below are a deliberately crude substitute — uniformity, splits, and
counts — and whether that is good enough is the question this prototype
exists to answer, not one to settle by argument.

Read the output, not this docstring.
"""

from __future__ import annotations

from typing import Any


# Fields never worth reporting on: keys, ids, and internal plumbing. A
# summary saying "all 25 have a distinct SupplierId" is noise.
_UNINTERESTING = {
    "supplierid",
    "suppliernumber",
    "poheaderid",
    "polineid",
    "invoiceid",
    "customertransactionid",
    "accountid",
    "personid",
    "addressid",
    "supplieraddressid",
}

# Above this many distinct values a field is descriptive rather than
# categorical — "25 different names" tells the reader nothing they
# cannot see. Chosen by eye, not measured; the first thing to revisit.
_MAX_CATEGORIES = 4

# A ratio guard, and the more important of the two. A cap alone is not
# enough: three supplier NAMES in three rows passes _MAX_CATEGORIES and
# produces "Supplier: 1 Lee Supplies, 1 JGA, 1 US Gas and Electric",
# which is the column read aloud. Found by running case E, not by
# reading the code.
#
# The test that matters is not how many distinct values there are but
# how many there are RELATIVE TO the rows. When nearly every row has its
# own value the field identifies rows rather than grouping them, and
# there is no grouping to report at any row count.
_MAX_DISTINCT_RATIO = 0.5


def _is_reportable(key: str, values: list[Any]) -> bool:
    """A field worth making a statement about."""
    if key.lower() in _UNINTERESTING:
        return False
    if not values:
        return False
    # All-null adds nothing.
    if all(v in (None, "", []) for v in values):
        return False
    return True


def _count_phrase(n: int, plural_label: str) -> str:
    """"1 supplier" / "25 suppliers".

    The prompt set printed "1 suppliers." forty times over before anyone
    read it, because the label arrives already plural and nothing ever
    looked at the number. Naive de-pluralisation (strip a trailing "s")
    is wrong for the words that will arrive here next — "credit memos"
    is fine, "addresses" is not — so the singular is derived only for
    the -es and -s cases that actually occur and otherwise left alone.
    """
    if n != 1:
        return f"{n} {plural_label}"
    label = plural_label
    if label.endswith("sses") or label.endswith("xes"):
        label = label[:-2]          # addresses -> address
    elif label.endswith("ies"):
        label = label[:-3] + "y"    # entries -> entry
    elif label.endswith("s"):
        label = label[:-1]          # suppliers -> supplier
    return f"1 {label}"


def _sentence(text: str) -> str:
    """End with exactly one full stop.

    "All 1 have Supplier Dell Inc.." — the value already ended in a
    period and the format string added another. Values come from the pod
    and carry their own punctuation; the renderer cannot assume they do
    not.
    """
    text = text.rstrip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _distinct(values: list[Any]) -> list[Any]:
    """Distinct values, order preserved, hashable-safe."""
    seen: list[Any] = []
    for v in values:
        if v not in seen:
            seen.append(v)
    return seen


def local_list_summary(
    rows: list[dict],
    entity_label: str,
    displayed_fields: list[str] | None = None,
    filtered_fields: list[str] | None = None,
    total_available: int | None = None,
    truncated: bool = False,
    labels: dict[str, str] | None = None,
) -> list[str]:
    """Build summary statements from the rows, without an LLM.

    Args:
        rows: The records that will actually be displayed.
        entity_label: Plural noun for the reader — "suppliers".
        displayed_fields: The columns the renderer will print.
        filtered_fields: Fields the user filtered on. Sayable even when
            not rendered, because the reader supplied them.

            Together these two are the whole rule: a field may be
            described if the reader can SEE it or if the reader ASKED
            for it. Anything else is a claim they cannot check.

            The rule is structural, not advisory. The loop iterates over
            the permitted fields and never sees the others, so it cannot
            describe them. The same rule as an INSTRUCTION failed four
            times against the model, and not because the model was
            careless: it receives the whole record and has no way to
            know which fields the renderer prints. It was asked to obey
            a rule it lacked the information to follow.

            Worth being exact about what that failure was. The model
            reported "Some suppliers have a Taxpayer Country Code" and
            TaxpayerCountryCode is genuinely on the rows — it is simply
            not rendered, and it is null on 17 of 25. Not invention.
            Describing data the reader cannot see, which is its own
            defect and needs its own fix.

            Both None means no restriction: every field on the row is
            fair game. That is the pre-2026-08-02 behaviour and is kept
            only so a caller that has not been updated still works.
        total_available: The authoritative total from the truncation
            block, when known.
        truncated: True when the fetch was capped. Only consulted when
            total_available is None: with a known total the "Showing N
            of M" line already tells the sample story, and with neither
            nothing is claimed. When True and total_available is None,
            the summary says the result is a sample without inventing
            a denominator (F-012).
        labels: Optional field-name -> display-label map. The summary
            names a field in the reader's terms, not the pod's.

            Without it the summary says "CreditMemoCurrency: 16 USD"
            above a table whose header says "Currency". Same field, two
            names, one line apart — the same inconsistency that made
            records render two ways depending on the code path, in
            miniature.

            Optional because most fields need no translation: Status,
            Supplier and Amount already read as themselves.

    Returns:
        Statements, one fact each. Empty list when there is nothing
        truthful to say — which is a valid answer and better than
        padding.
    """
    shown = len(rows)
    out: list[str] = []

    # ---- counts, first and always ----
    #
    # This is the statement the model got wrong ("Showing 20" against 25
    # rows). It is len(). It cannot be wrong again.
    if total_available is not None and total_available > shown:
        # The ONE count worth stating: the reader cannot see 426
        # anywhere. Everything else about this line they can count.
        out.append(f"Showing {shown} of {total_available:,} {entity_label}.")
    elif shown == 0:
        # Zero rows is an answer, not an error, and gets said plainly
        # rather than printing nothing. (OUT-01.)
        return [f"No {entity_label} matched."]
    elif truncated and total_available is None:
        # F-012: the fetch was capped (truncated=True) but the source
        # total is unknown (total_available is None). "Showing N of M"
        # cannot be said — there is no M. But N rows must not read as
        # the complete answer either. Say the sample; name no
        # denominator, because there is none to name.
        #
        # This branch only fires when BOTH conditions hold. A known
        # total takes the branch above; an untruncated fetch falls
        # through to the observations below unchanged.
        out.append(
            f"Showing {shown} {entity_label} from an examined sample; "
            f"the true matching count is not known."
        )
    # Otherwise: say nothing about the count.
    #
    # "3 suppliers." above a three-row table, "1 supplier." above a
    # single record. The number is the row count of a table printed
    # immediately below it, and restating it is the paragraph problem in
    # miniature — output that repeats what the reader is already looking
    # at.
    #
    # This only became visible once records rendered as a table. Against
    # the old bullet list the count read as a useful header; against a
    # table with its rows lined up under it, it reads as noise. Worth
    # noting for the next format change: the value of a summary line is
    # not a property of the line, it is a property of what sits below
    # it.

    if not rows:
        return out

    # One row generalises about nothing. "All 1 have Supplier Dell Inc."
    # names a value the reader can see on the very next line, and reads
    # as though it were a finding. The counts line is the whole answer.
    #
    # The ratio guard below does not catch this: it applies to SPLITS,
    # and a single row is trivially uniform, so it took the uniform
    # branch untested. Found by running 40 prompts, not by reading the
    # code.
    if shown == 1:
        return out

    # ---- what is uniform, and what splits ----
    #
    # Permitted = shown to the reader, or named by the reader. Order is
    # displayed-first: a column on screen is more useful to describe
    # than one the reader only implied by filtering.
    if displayed_fields or filtered_fields:
        keys = list(displayed_fields or [])
        # Filter types arrive in the USER's vocabulary and lower case —
        # "status", "country" — while row keys are the pod's PascalCase.
        # Match case-insensitively against the actual keys and use the
        # row's spelling, so the summary reads in the pod's terms and
        # the lookup still finds the column.
        #
        # This resolves "status" -> "Status". It does NOT resolve
        # "country" -> "TaxpayerCountryCode", and nothing here can:
        # that is a synonym, and synonyms belong in the KG
        # (kg_vocabulary), not in a display helper. A filter whose name
        # does not case-match a column is silently not described, which
        # is the safe failure — a missing true statement rather than a
        # wrong one.
        row_keys = {k.lower(): k for k in rows[0]}
        for f in filtered_fields or []:
            actual = row_keys.get(str(f).lower())
            if actual and actual not in keys:
                keys.append(actual)
    else:
        keys = list(rows[0].keys())

    for key in keys:
        if len(out) >= 4:  # counts + three observations
            break
        values = [r.get(key) for r in rows if r.get(key) not in (None, "")]
        if not _is_reportable(key, values):
            continue
        distinct = _distinct(values)

        if len(distinct) == 1 and len(values) == shown:
            # Every row shares one value AND every row HAS one. Both
            # halves matter: TaxpayerCountryCode was uniform 'US' across
            # the 8 rows that carried it and null on the other 17, which
            # would have produced "All 25 have TaxpayerCountryCode US"
            # from 8 rows. len(values) == shown is what excludes it.
            label = (labels or {}).get(key, key)
            out.append(_sentence(f"All {shown} have {label} {distinct[0]}"))
        elif len(distinct) == 1:
            # Uniform where present, absent elsewhere. Say both numbers
            # rather than rounding the gap away.
            out.append(
                _sentence(
                    f"{len(values)} of {shown} have "
                    f"{(labels or {}).get(key, key)} {distinct[0]}; "
                    f"the rest have none"
                )
            )
        elif (
            1 < len(distinct) <= _MAX_CATEGORIES
            and len(distinct) / len(values) <= _MAX_DISTINCT_RATIO
        ):
            # A genuine split. Largest group first: the reader wants the
            # shape of the set, and the exception is more interesting
            # stated second.
            counts = {d: sum(1 for v in values if v == d) for d in distinct}
            ordered = sorted(counts.items(), key=lambda kv: -kv[1])
            parts = ", ".join(f"{n} {d}" for d, n in ordered)
            out.append(_sentence(f"{(labels or {}).get(key, key)}: {parts}"))
        # Otherwise descriptive — the column already shows it.

    return out
