#!/usr/bin/env python3
"""
BUG-1 Step 3 verification — the supplier contact and supplier site gaps.

Read-only. Static analysis + one synthetic build-and-render. Does NOT call
any LLM, does NOT touch the KG, does NOT modify any file.

Two distinct gaps, demonstrated by four checks:

  1. CONTACT IS NOT FETCHED. `get_purchase_order_by_id`'s
     `_PROJECTED_FIELDS` list does not include `SupplierContactDisplayName`.
     curl against /purchaseOrders confirms the field exists on the endpoint
     (returns 'Seth Ries' for PO 701337).

  2. SITE IS FETCHED BUT NOT RENDERED. The tool DOES project
     `SupplierSite` (curl confirms 'JGA Progress US'), but the typed
     `PurchaseOrderRecord` in the synthesizer does not carry it, so the
     display never shows it.

  [A] Tool projection    — what the by_id tool actually asks the pod for
  [B] Typed record       — what PurchaseOrderRecord carries today
  [C] Display columns    — what the PO branch of _format_synthesized renders
  [D] Synthetic demo     — an executor row carrying both fields, run through
                           build_purchase_order_records and _format_synthesized,
                           showing both are dropped

Usage:
    python scripts/verify_bug1_step3.py 2>&1 | tee verify_bug1_step3.txt
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DISPLAY_PY = REPO_ROOT / "scripts" / "display_formatters.py"


# ── [A] Tool projection ──────────────────────────────────────────────


def check_tool_projection() -> None:
    print("[A] The tool's projection — "
          "src/spire/mcp_server/tools/purchase_order_by_id.py\n")

    from spire.mcp_server.tools.purchase_order_by_id import _PROJECTED_FIELDS

    has_site = "SupplierSite" in _PROJECTED_FIELDS
    has_contact = "SupplierContactDisplayName" in _PROJECTED_FIELDS

    print(f"    SupplierSite                 in _PROJECTED_FIELDS: {has_site}")
    print(f"    SupplierContactDisplayName   in _PROJECTED_FIELDS: {has_contact}")
    print()

    if has_site and not has_contact:
        print("    --> Site IS fetched. Contact is NOT.")
        print("        Gap 1 confirmed: add SupplierContactDisplayName.")
    elif not has_site and not has_contact:
        print("    --> Neither is fetched. Both gaps present.")
    elif has_contact and has_site:
        print("    --> Both present. The tool layer is already done.")
    else:
        print("    --> Contact present, site missing (unexpected).")
    print()


# ── [B] Typed record ─────────────────────────────────────────────────


def check_record_fields() -> None:
    print("[B] The typed record — src/spire/synthesizer/p2p.py "
          "(PurchaseOrderRecord)\n")

    from spire.synthesizer.p2p import PurchaseOrderRecord

    fields = sorted(PurchaseOrderRecord.model_fields.keys())
    has_site = "supplier_site" in fields
    has_contact = "supplier_contact" in fields

    print(f"    PurchaseOrderRecord fields: {fields}")
    print()
    print(f"    supplier_site                present: {has_site}")
    print(f"    supplier_contact             present: {has_contact}")
    print()

    if has_site and has_contact:
        print("    --> Both present. The synthesizer schema is already done.")
    else:
        missing = [f for f, ok in (("supplier_site", has_site),
                                    ("supplier_contact", has_contact)) if not ok]
        print(f"    --> Missing: {missing}")
        print("        Gap 2 confirmed: add these fields to the record and")
        print("        populate them in build_purchase_order_records and")
        print("        build_po_with_children.")
    print()


# ── [C] Display columns ──────────────────────────────────────────────


def check_display_columns() -> None:
    print("[C] The display — scripts/display_formatters.py, the "
          "PurchaseOrderResponse branch\n")

    src = DISPLAY_PY.read_text(encoding="utf-8")
    marker = "if isinstance(response, PurchaseOrderResponse):"
    idx = src.find(marker)
    if idx == -1:
        print("    !! Could not locate the PurchaseOrderResponse branch.")
        print("        Has the file been restructured? Inspect it manually.")
        return

    # Bounded window: the branch, up to the next isinstance(...) check.
    tail = src[idx : idx + 4000]
    next_branch = tail.find("\n    if isinstance(response,", 1)
    if next_branch != -1:
        tail = tail[:next_branch]

    # The base column list and the conditional extras tuple.
    cols_line = next(
        (ln.strip() for ln in tail.splitlines() if ln.strip().startswith("cols = ")),
        "<not found>",
    )
    extras_line = next(
        (ln.strip() for ln in tail.splitlines() if "for extra in" in ln),
        "<not found>",
    )

    print(f"    base column list:  {cols_line}")
    print(f"    extras iteration:  {extras_line}")
    print()

    has_site_col = '"Site"' in tail
    has_contact_col = '"Contact"' in tail

    print(f"    'Site' column referenced:     {has_site_col}")
    print(f"    'Contact' column referenced:  {has_contact_col}")
    print()

    if not (has_site_col or has_contact_col):
        print("    --> Neither column is rendered by the PO branch.")
        print("        Gap 3 confirmed: add Site and Contact to the row dicts")
        print("        and to the conditional extras list.")
    print()


# ── [D] Synthetic build-and-render ───────────────────────────────────


def synthetic_build_and_render() -> None:
    print("[D] Synthetic demo — an executor row carrying site and contact, "
          "through the builder and into the display\n")

    from spire.synthesizer.p2p import (
        PurchaseOrderResponse,
        build_purchase_order_records,
    )
    from scripts.display_formatters import _format_synthesized

    # One executor row, shaped like what get_purchase_order_by_id returns
    # for PO 701337 today (per four_bugs.md §2.1's curl).
    # SupplierContactDisplayName would come from the tool AFTER Step 3; here
    # it is placed on the row to show that even when present, the record
    # builder drops it.
    row = {
        "POHeaderId": 300000081255594,
        "OrderNumber": "701337",
        "Status": "Open",
        "StatusCode": "OPEN",
        "Supplier": "JGA",
        "SupplierId": 300000047414635,
        "SupplierSite": "JGA Progress US",
        "SupplierContactDisplayName": "Seth Ries",
        "Buyer": "White, Eleanor",
        "BuyerId": 300000076218768,
    }

    print("    Executor row carries:")
    print(f"      SupplierSite               = {row['SupplierSite']!r}")
    print(f"      SupplierContactDisplayName = "
          f"{row['SupplierContactDisplayName']!r}")
    print()

    records = build_purchase_order_records([row])
    record = records[0]

    print("    After build_purchase_order_records:")
    print(f"      record.supplier_name         = {record.supplier_name!r}")
    print(f"      record.supplier_site         = "
          f"{getattr(record, 'supplier_site', '<field does not exist>')!r}")
    print(f"      record.supplier_contact      = "
          f"{getattr(record, 'supplier_contact', '<field does not exist>')!r}")
    print()

    response = PurchaseOrderResponse(
        summary="PO 701337 — supplier JGA.",
        purchase_orders=records,
        truncation_notes=[],
    )

    rendered = _format_synthesized(response)

    print("    Rendered output (current code):")
    print("    " + "-" * 62)
    for line in rendered.splitlines():
        print(f"    {line}")
    print("    " + "-" * 62)
    print()

    mentions_site = "JGA Progress US" in rendered
    mentions_contact = "Seth Ries" in rendered

    print(f"    render mentions 'JGA Progress US':  {mentions_site}")
    print(f"    render mentions 'Seth Ries':        {mentions_contact}")
    print()

    if not mentions_site and not mentions_contact:
        print("    --> Both fields present on the executor row; both absent")
        print("        from the render. Confirms the two-layer gap: the typed")
        print("        record drops them, and the display has no column for them.")
    print()

    print("    After Step 3 the render is expected to show, conditionally:")
    print("      Site       JGA Progress US")
    print("      Contact    Seth Ries")
    print()


# ── main ─────────────────────────────────────────────────────────────


def main() -> None:
    print("=== BUG-1 Step 3 verification — contact not fetched, "
          "site not rendered ===\n")

    # NOTE: run from the repo root with the venv active — the imports below
    # reach into spire.* and scripts.*.
    check_tool_projection()
    check_record_fields()
    check_display_columns()
    synthetic_build_and_render()

    print("=== done ===")


if __name__ == "__main__":
    main()