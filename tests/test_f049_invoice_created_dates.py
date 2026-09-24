"""F-049 - absolute-date Invoice phrasings starting with "created" must parse.

Regression test for the coverage gap in b_invoice_date.sysprompt and its
byte-equality mirror in context_assembly.py::_SYSTEM_PROMPT_PREAMBLE. The
sibling b_po_created_date.sysprompt teaches "POs created before 2015"
verbatim; the Invoice bullet does not, so "created" phrasings fall through
to a filter-less Invoice intent and the planner refuses on missing_identifier.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SYSPROMPT = REPO / "src/spire/nl_parser/context/payables/b_invoice_date.sysprompt"
ASSEMBLY = REPO / "src/spire/nl_parser/context_assembly.py"

REQUIRED = (
    "invoices created before",
    "invoices created since",
    "invoices raised before",
)


def test_sysprompt_teaches_created_phrasings():
    text = SYSPROMPT.read_text()
    for phrase in REQUIRED:
        assert phrase in text, f"missing from b_invoice_date.sysprompt: {phrase}"


def test_assembly_mirror_teaches_created_phrasings():
    text = ASSEMBLY.read_text()
    for phrase in REQUIRED:
        assert phrase in text, f"missing from context_assembly mirror: {phrase}"


def test_absolute_date_bullet_still_mirrored():
    sys_lines = [
        ln for ln in SYSPROMPT.read_text().splitlines()
        if "invoice_date" in ln and '"from"' in ln
    ]
    asm_lines = [
        ln for ln in ASSEMBLY.read_text().splitlines()
        if "invoice_date" in ln and '"from"' in ln
    ]
    assert len(sys_lines) == 1, f"expected 1 bullet, found {len(sys_lines)}"
    assert len(asm_lines) == 1, f"expected 1 bullet, found {len(asm_lines)}"
    assert sys_lines[0] == asm_lines[0], "sysprompt and mirror have drifted"
