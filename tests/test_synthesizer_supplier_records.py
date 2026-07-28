"""Deterministic supplier records — the fix for a query that returned nothing.

THE BUG THESE PIN
"Suppliers with their addresses" produced no answer at all. The LLM was
asked to emit the whole SupplierResponse: every supplier_id,
supplier_number, supplier_name and nested address, copied verbatim from
data the executor already had. 16,390 tokens in, 7,985 out, response cut
off mid-string, degenerate-output guard fired, run reported [ok] with
"Synthesized response: (none)". Two prompts did this — the second was
"Get supplier sites for suppliers", which parsed to the same shape — and
between them they burned 48,750 tokens producing nothing: 28% of the QA
run's total.

The saved trace settled what kind of failure it was. The output was
well-formed, correct, non-repeating JSON that ran out of room:

    "formatted_address": "JAPAN,272-0127,Chiba,Ichikawa-shi,

Not degenerate. Just a transcription too large to fit. So the records
are built here instead, and the model is asked only for the summary.
"""

from spire.synthesizer.synthesizer import (
    build_supplier_records,
    plain_supplier_bucket,
)


def _supplier(sid, number, name, addresses=None):
    row = {
        "SupplierId": sid,
        "SupplierNumber": number,
        "Supplier": name,
        "Status": "ACTIVE",
        "BusinessRelationship": "Spend Authorized",
    }
    if addresses is not None:
        row["addresses"] = addresses
    return row


def _address(aid, city, country, state="", formatted=""):
    return {
        "SupplierAddressId": aid,
        "City": city,
        "Country": country,
        "State": state,
        "FormattedAddress": formatted,
    }


# ─────────────────────────────────────────────────────────────────────
# build_supplier_records
# ─────────────────────────────────────────────────────────────────────


def test_maps_the_identity_fields():
    """Supplier -> supplier_name is the one rename that isn't mechanical;
    a naming convention would have got it wrong."""
    [record] = build_supplier_records(
        [_supplier(300000047414503, "1252", "Lee Supplies")]
    )
    assert record.supplier_id == 300000047414503
    assert record.supplier_number == "1252"
    assert record.supplier_name == "Lee Supplies"


def test_nested_addresses_come_through():
    """The addresses arrive already nested on the row — the tool sets
    row["addresses"]. No join, just a rename."""
    [record] = build_supplier_records(
        [
            _supplier(
                1,
                "1289",
                "Shangduo Inc",
                addresses=[
                    _address(
                        300000075469556,
                        "Wenzhou",
                        "China",
                        formatted="CHINA,325604 ZHEJIANG,Wenzhou",
                    )
                ],
            )
        ]
    )
    assert len(record.addresses) == 1
    addr = record.addresses[0]
    assert addr.address_id == 300000075469556
    assert addr.city == "Wenzhou"
    assert addr.country == "China"
    assert addr.formatted_address == "CHINA,325604 ZHEJIANG,Wenzhou"


def test_multiple_addresses_per_supplier():
    [record] = build_supplier_records(
        [
            _supplier(
                1,
                "1252",
                "Lee Supplies",
                addresses=[_address(10, "Reston", "United States"),
                           _address(11, "Austin", "United States")],
            )
        ]
    )
    assert [a.address_id for a in record.addresses] == [10, 11]


def test_supplier_without_addresses_gets_an_empty_list():
    """A supplier query that never asked for addresses must not invent an
    addresses key or fail on its absence."""
    [record] = build_supplier_records([_supplier(1, "1252", "Lee Supplies")])
    assert record.addresses == []


def test_buyers_and_contacts_stay_empty():
    """BY DESIGN. This path only runs on a single supplier bucket, so
    nothing was fetched to fill them. A query that DOES fetch buyers takes
    the LLM path, where the cross-bucket join is still the model's job —
    silently emitting empty lists there would be a wrong answer, not a
    missing one."""
    [record] = build_supplier_records([_supplier(1, "1252", "Lee Supplies")])
    assert record.buyers == []
    assert record.contacts == []
    assert record.open_po_count is None


def test_missing_fields_do_not_raise():
    """Executor rows are projections and a field can be absent. Falling
    back to an empty value beats failing the whole response."""
    [record] = build_supplier_records([{"SupplierId": 1, "Supplier": "X"}])
    assert record.supplier_number == ""
    assert record.supplier_name == "X"


def test_null_address_fields_become_empty_strings():
    """The pod returns null for absent address parts; AddressInfo wants
    strings."""
    [record] = build_supplier_records(
        [
            _supplier(
                1,
                "1",
                "X",
                addresses=[
                    {
                        "SupplierAddressId": 5,
                        "City": None,
                        "Country": None,
                        "State": None,
                        "FormattedAddress": None,
                    }
                ],
            )
        ]
    )
    addr = record.addresses[0]
    assert addr.city == ""
    assert addr.country == ""
    assert addr.state == ""


def test_empty_input_gives_empty_output():
    assert build_supplier_records([]) == []


def test_order_is_preserved():
    """The executor already ordered these; re-ordering would silently
    contradict the tool's sort."""
    records = build_supplier_records(
        [_supplier(i, str(i), f"S{i}") for i in range(5)]
    )
    assert [r.supplier_id for r in records] == [0, 1, 2, 3, 4]


# ─────────────────────────────────────────────────────────────────────
# plain_supplier_bucket — the guard deciding which path runs
# ─────────────────────────────────────────────────────────────────────


def test_single_supplier_bucket_is_plain():
    outputs = {"suppliers": [_supplier(1, "1252", "Lee Supplies")]}
    assert plain_supplier_bucket(outputs) == "suppliers"


def test_bucket_name_is_not_assumed():
    """Output names are generated (us_suppliers, suppliers_has_open_PO,
    ...), so the bucket is identified by its CONTENT, not its name."""
    outputs = {"us_suppliers": [_supplier(1, "1252", "Lee Supplies")]}
    assert plain_supplier_bucket(outputs) == "us_suppliers"


def test_multiple_buckets_are_not_plain():
    """The anchor question fetches suppliers, open POs and buyers. Which
    buyer belongs to which supplier is a real join — that stays with the
    LLM. This guard is what keeps the change narrow."""
    outputs = {
        "us_suppliers": [_supplier(1, "1252", "Lee Supplies")],
        "open_pos": [{"POHeaderId": 9}],
        "buyers": [{"PersonId": 7, "DisplayName": "Gee, May"}],
    }
    assert plain_supplier_bucket(outputs) is None


def test_non_supplier_bucket_is_not_plain():
    """An invoice list is a single bucket too. Content, not cardinality."""
    outputs = {"invoices": [{"InvoiceId": 1, "InvoiceNumber": "X"}]}
    assert plain_supplier_bucket(outputs) is None


def test_empty_bucket_falls_back_to_the_llm():
    """Nothing proves an empty bucket is suppliers, and the LLM path
    already says 'no suppliers found' correctly. Falling back costs
    tokens; guessing costs correctness."""
    assert plain_supplier_bucket({"suppliers": []}) is None


def test_no_buckets_at_all():
    assert plain_supplier_bucket({}) is None


def test_rows_that_are_not_dicts():
    """Defensive: an aggregation bucket holds objects, not entity rows."""
    assert plain_supplier_bucket({"aggregation": ["not a dict"]}) is None
