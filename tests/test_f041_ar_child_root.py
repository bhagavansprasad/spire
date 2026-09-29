"""F-041 regression — AR children named first route to receivables and
root on the parent.

Three layers make the fix work; each has a test below:

  1. Router: the LLM classifier picks 'payables' when the prompt's leading
     noun is 'invoice', even with the child synonym in its menu.
     `_correct_modules_for_ar_child` adds 'receivables' deterministically,
     so the AR sysprompt blocks load.
  2. Parser: the three AR sysprompt blocks teach the leading phrasing
     (child noun first, parent id after), so the parser roots on
     ReceivablesInvoice and includes the child.
  3. Field-split: a DFF column requested on the parent is satisfied by
     the active DFF include, so it is not reported as unresolved.

Each layer can regress independently; each has its own assertion.
"""

from __future__ import annotations

from pathlib import Path

from spire.nl_parser.intent_validation import _FIELDS_SATISFIED_BY_INCLUDE
from spire.nl_parser.router import _correct_modules_for_ar_child


_CONTEXT = (
    Path(__file__).resolve().parents[1]
    / "src" / "spire" / "nl_parser" / "context" / "receivables"
)


# ── Layer 1: router correction ────────────────────────────────────────


def test_router_adds_receivables_for_invoice_lines_phrasing():
    """'invoice lines for invoice X' must route receivables.

    The LLM classifier picks payables for this prompt (F-041 evidence);
    the deterministic corrector adds receivables so the AR sysprompt
    blocks load.
    """
    out = _correct_modules_for_ar_child(
        "show invoice lines for invoice 300000248096352", ["payables"]
    )
    assert "receivables" in out


def test_router_adds_receivables_for_dff_phrasing():
    out = _correct_modules_for_ar_child(
        "show flexfield for invoice 1002", ["payables"]
    )
    assert "receivables" in out


def test_router_adds_receivables_for_tax_phrasing():
    out = _correct_modules_for_ar_child(
        "what tax was charged on invoice 1002", ["payables"]
    )
    assert "receivables" in out


def test_router_does_not_trigger_on_plain_invoice_query():
    """A payables invoice query with no child noun must NOT be redirected.

    The corrector fires on the child-noun shape only; a plain supplier-
    invoice query stays payables.
    """
    out = _correct_modules_for_ar_child(
        "invoices for supplier 1252", ["payables"]
    )
    assert "receivables" not in out


def test_router_does_not_trigger_on_po_children():
    """PO lines are procurement's; the AR corrector must leave them alone."""
    out = _correct_modules_for_ar_child(
        "show PO lines for PO 2144", ["procurement"]
    )
    assert out == ["procurement"]


def test_router_corrector_is_idempotent():
    """When the classifier already returned receivables, the corrector is
    a no-op and does not duplicate the module."""
    out = _correct_modules_for_ar_child(
        "show tax lines for invoice 1002", ["receivables"]
    )
    assert out == ["receivables"]


# ── Layer 2: the three sysprompt blocks carry the leading rule ────────


def _read(rel: str) -> str:
    return (_CONTEXT / rel).read_text(encoding="utf-8")


def test_ar_invoice_lines_block_teaches_leading_phrasing():
    body = _read("b_ar_invoice_lines.sysprompt")
    assert "invoice lines for invoice X" in body, (
        "b_ar_invoice_lines.sysprompt no longer teaches the leading "
        "phrasing 'invoice lines for invoice X'; the parser will fall "
        "back to rooting on ReceivablesInvoiceLine, which is not a "
        "valid target, and refuse."
    )


def test_ar_dff_block_teaches_leading_phrasing():
    body = _read("b_ar_dff.sysprompt")
    assert "flexfield for invoice X" in body
    # The DFF-context sub-rule is the residual fix: a column of the DFF
    # child (not the child named directly) must route the same way.
    assert "flexfield context on invoice X" in body


def test_ar_tax_lines_block_teaches_natural_tax_phrasings():
    body = _read("b_ar_tax_lines.sysprompt")
    assert "what tax was charged on invoice X" in body
    assert "tax breakdown for invoice X" in body
    assert "the tax on invoice X" in body


# ── Layer 3: field-split knows DFF columns live on the include ────────


def test_dff_include_entry_present_in_satisfied_by_include():
    """`__FLEX_Context` is a column on the DFF child, not on the parent
    ReceivablesInvoice. The field-split must know this or it flags the
    column as unresolved and the display prints a false 'column not
    available' note over data the pipeline has already fetched.
    """
    dff = _FIELDS_SATISFIED_BY_INCLUDE.get("ReceivablesInvoiceTransactionDFF")
    assert dff is not None, (
        "_FIELDS_SATISFIED_BY_INCLUDE has no entry for "
        "ReceivablesInvoiceTransactionDFF; DFF columns will be reported "
        "as unresolved on the parent."
    )
    assert "__flex_context" in dff
