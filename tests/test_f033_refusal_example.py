"""F-033 regression — a `_NOT_A_ROOT_GUIDANCE` example must not be the
prompt that triggers the refusal it explains.

The `_NOT_A_ROOT_GUIDANCE` map holds, per child entity, a Solution (how to
ask for the child through its parent) and an Example (a prompt that
demonstrates the advice). For `ReceivablesInvoiceLine` the Example was
byte-identical to `"Show invoice lines for invoice 300000248096352"` — the
exact prompt whose refusal is being explained. A user told "ask for the
invoice and its lines together" was handed back the same failing input.

Fix: the Example now names the invoice (a valid target) and pulls its
lines via include — mirroring the sibling `ReceivablesTaxLine` entry.

The two tests below fail if the entry reverts to the failing shape.
"""

from __future__ import annotations

from spire.nl_parser.capability import _NOT_A_ROOT_GUIDANCE


def test_receivables_invoice_line_example_is_not_the_failing_prompt():
    """The example for ReceivablesInvoiceLine refusals must not be the
    prompt that triggers them."""
    _, example = _NOT_A_ROOT_GUIDANCE["ReceivablesInvoiceLine"]
    assert example != "Show invoice lines for invoice 300000248096352", (
        "The example offered with a ReceivablesInvoiceLine refusal is "
        "byte-identical to the prompt that triggers the refusal — the "
        "user is shown the same failing input back."
    )
    # The working shape roots on the invoice (a valid target) by its
    # queryable id.
    assert "CustomerTransactionId" in example, (
        f"Example {example!r} does not name the invoice by its queryable id; "
        "the refusal explains that the child cannot be a query root, so the "
        "example must demonstrate rooting on the parent."
    )


def test_every_not_a_root_example_is_nonempty():
    """Every _NOT_A_ROOT_GUIDANCE entry carries a non-empty Solution and
    Example.

    Class-level guard for the F-033 defect: the map's purpose is to offer
    a refused user a path forward, and an empty slot is that offer missing.
    Does not run the examples through the pipeline (that belongs to the
    integration test the docstring of test_nl_parser_capability.py
    describes), only asserts the offers exist.
    """
    for entity, (solution, example) in _NOT_A_ROOT_GUIDANCE.items():
        assert solution, f"{entity}: Solution is empty"
        assert example, f"{entity}: Example is empty"
