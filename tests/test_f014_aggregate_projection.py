"""F-014 — `fields` on an aggregate intent must not project the wrapper.

An aggregate intent's output bucket holds a single shape-wrapper record
(`{"shape": "supplier_spend_ranking", "rows": [...], "returned": 5,
...}`), not a list of entity rows. The pipeline's `_project_outputs`
applied the intent's `fields` to the wrapper's own keys; none matched,
the requested columns rendered as em dashes, and the real values sat one
level down in `rows[]`.

Two fixes, both tested here:

  parser.py   — clears `intent.fields` when `aggregate` or `compare` is
                set (a deterministic post-parse correction; the model
                emits fields regardless of any sysprompt instruction).
  pipeline.py — `_project_outputs` skips any bucket whose first record
                carries a `shape` key (a tool-computed wrapper).

The tests split cleanly: the parser correction is a one-line predicate
over the intent; the pipeline defence is a pure function over a dict of
buckets. Neither touches the pod, so no fetch and no LLM in the path.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from spire.graph.pipeline import _project_outputs
from spire.nl_parser.draft import (
    DraftAggregate,
    DraftCompare,
    DraftFilter,
    DraftIntent,
)
from spire.nl_parser.parser import parse
from spire.nl_parser.vocabulary import KGMenu


def _menu() -> KGMenu:
    """Minimal menu — enough for parse() to validate an aggregate or a
    plain Supplier intent. Same convention as the other F-0NN test files."""
    return KGMenu(
        target_entities={"Supplier"},
        filter_types={"status", "country"},
        entity_descriptions={"Supplier": "a supplier"},
        entity_columns={
            "Supplier": ["SupplierId", "SupplierNumber", "Supplier", "Status"],
        },
    )


def _mock_llm_returning(draft: DraftIntent) -> MagicMock:
    llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = {"parsed": draft, "raw": None}
    llm.with_structured_output.return_value = structured
    return llm


# ─────────────────────────────────────────────────────────────────────
# Parser correction — aggregate and compare intents lose their fields
# ─────────────────────────────────────────────────────────────────────


def test_paraphrase_aggregate_fields_cleared():
    """The V2 paraphrase: an aggregate intent that arrives with fields
    populated must come out of parse() with fields=[]."""
    draft = DraftIntent(
        target_entity="Supplier",
        fields=["Supplier", "Total"],
        aggregate=DraftAggregate(
            op="by_supplier",
            date_from="2022-01-01",
            date_to="2023-01-01",
            top_n=5,
        ),
    )
    result = parse(
        "Top 5 suppliers by invoice spend in 2022 with supplier name and total",
        llm=_mock_llm_returning(draft),
        menu=_menu(),
    )
    assert not result.is_refusal
    assert result.intent.aggregate is not None
    assert result.intent.fields == []


def test_compare_fields_cleared():
    """The compare block gets the same treatment as aggregate — the fix
    covers both, per the entry's note that the comparison bucket has the
    same wrapper shape."""
    draft = DraftIntent(
        target_entity="Supplier",
        fields=["Supplier"],
        compare=DraftCompare(
            op="supplier_invoiced_vs_ordered",
            supplier_name="Lee Supplies",
            top_n=5,
        ),
    )
    result = parse(
        "How does invoiced compare to ordered for Lee Supplies",
        llm=_mock_llm_returning(draft),
        menu=_menu(),
    )
    assert not result.is_refusal
    assert result.intent.compare is not None
    assert result.intent.fields == []


def test_non_aggregate_fields_preserved():
    """Over-reach guard: a plain list intent keeps its fields. The
    correction is scoped to aggregate / compare only."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[DraftFilter(type="status", value_json='"active"')],
        fields=["SupplierNumber"],
    )
    result = parse(
        "List active suppliers with supplier number",
        llm=_mock_llm_returning(draft),
        menu=_menu(),
    )
    assert not result.is_refusal
    assert result.intent.aggregate is None
    assert result.intent.fields == ["SupplierNumber"]


# ─────────────────────────────────────────────────────────────────────
# Pipeline defence — the shape-wrapper skip in _project_outputs
# ─────────────────────────────────────────────────────────────────────


def _aggregate_wrapper() -> dict:
    """The exact wrapper shape the supplier_spend_ranking tool returns,
    trimmed to the fields F-014 cares about."""
    return {
        "shape": "supplier_spend_ranking",
        "date_from": "2022-01-01",
        "date_to": "2023-01-01",
        "total_suppliers": 50,
        "returned": 5,
        "truncated": False,
        "rows": [
            {"supplier": "EIP Inc", "supplier_number": "1262",
             "total_spend": 141_171_590.98, "invoice_count": 261},
        ],
    }


def test_projection_skips_shape_wrapper():
    """The V3 sibling: a wrapper bucket is returned unchanged — not
    trimmed to {}, not trimmed to {}, with the original record preserved
    by the fallback. The tool has already projected its rows."""
    outputs = {"aggregation": [_aggregate_wrapper()]}
    projected = _project_outputs(outputs, fields=["Supplier", "Total"])
    assert projected["aggregation"] == outputs["aggregation"]


def test_projection_trims_normal_entity_bucket():
    """The V4 negative: a normal entity bucket still trims to the
    requested fields. The shape-skip must not swallow entity buckets."""
    outputs = {
        "suppliers": [
            {
                "SupplierNumber": "1252",
                "Supplier": "Lee Supplies",
                "SupplierId": 300000047414503,
                "Status": "ACTIVE",
            },
            {
                "SupplierNumber": "1254",
                "Supplier": "JGA",
                "SupplierId": 300000047414635,
                "Status": "ACTIVE",
            },
        ]
    }
    projected = _project_outputs(outputs, fields=["SupplierNumber"])
    assert projected["suppliers"] == [
        {"SupplierNumber": "1252"},
        {"SupplierNumber": "1254"},
    ]


def test_projection_handles_empty_wrapper():
    """A wrapper with an empty `rows[]` (no suppliers matched) is still
    skipped — the shape key is on the wrapper, not on the rows."""
    wrapper = dict(_aggregate_wrapper())
    wrapper["rows"] = []
    outputs = {"aggregation": [wrapper]}
    projected = _project_outputs(outputs, fields=["Supplier", "Total"])
    assert projected["aggregation"] == [wrapper]


def test_projection_unchanged_when_fields_empty():
    """The pre-existing no-op path: fields=[] returns the outputs dict
    unchanged, wrapper or not."""
    outputs = {"aggregation": [_aggregate_wrapper()]}
    projected = _project_outputs(outputs, fields=[])
    assert projected is outputs


def test_projection_mixed_buckets():
    """A pipeline that produced both an aggregate wrapper and a normal
    entity bucket projects only the entity bucket."""
    wrapper = _aggregate_wrapper()
    entity_row = {
        "SupplierNumber": "1252",
        "Supplier": "Lee Supplies",
        "SupplierId": 300000047414503,
    }
    outputs = {
        "aggregation": [wrapper],
        "suppliers": [entity_row],
    }
    projected = _project_outputs(outputs, fields=["SupplierNumber"])
    assert projected["aggregation"] == [wrapper]
    assert projected["suppliers"] == [{"SupplierNumber": "1252"}]
