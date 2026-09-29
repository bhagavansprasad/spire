"""F-006 regression — the MCP boundary must accept an alpha OrderNumber.

F-006: ``get_purchase_order_by_id`` crashed on "What is purchase order
US164932 about?" with::

    ERROR: execute: 1 validation error for call[get_purchase_order_by_id]
    po_header_id
      Input should be a valid integer, unable to parse string as an integer
        [type=int_parsing, input_value='US164932', input_type=str]

The MCP server log named the site: ``server.py:1325`` rejected the call
before dispatch, at the schema FastMCP derives from the wrapper's
annotation. The internal resolver in ``tools/purchase_order_by_id.py``
was never broken — its own docstring says it "Resolves ONE purchase
order from whatever number the user gave" and its body tries
``q=OrderNumber='X'`` first, then ``/purchaseOrders/X``. But the wrapper
was annotated ``po_header_id: int``, so ``'US164932'`` never reached it.

The fix is one word on the wrapper: ``int`` -> ``str | int``. Two tests
below, at two layers:

  * ``test_wrapper_annotation_admits_str`` proves the FIX at the layer
    it was made. Pure; no pod, no FastMCP internals. This is the
    load-bearing assertion and the one that fails on revert.

  * ``test_mcp_call_accepts_alpha_order_number`` proves the CONTRACT —
    FastMCP's derived schema admits the string at runtime, which is the
    layer the original error came from. Needs the pod (the resolver does
    a real Fusion lookup for US164932).

Why these tests do not live with the other PO-tool tests: those call the
internal tool functions directly (``_get_purchase_order_by_id(client,
po_header_id=...)``), bypassing FastMCP entirely. They could never have
caught F-006 — the internal function was always correct. This file is
the first to exercise the MCP wrapper's own contract.
"""
from __future__ import annotations

import inspect


# ─────────────────────────────────────────────────────────────────────
# Layer 1 — the fix, at the layer it was made
# ─────────────────────────────────────────────────────────────────────


def test_wrapper_annotation_admits_str():
    """F-006's fix is the ``str | int`` annotation on the FastMCP wrapper.

    Before: ``po_header_id: int``. After: ``po_header_id: str | int``.
    The internal resolver already handles both shapes; this annotation
    is what lets a string OrderNumber reach it.

    ``str | int`` (PEP 604) produces a ``types.UnionType`` at runtime;
    ``getattr(ann, "__args__", ())`` returns ``(str, int)`` regardless of
    whether the annotation is a UnionType or a typing.Union. The check is
    the same in both cases.
    """
    from spire.mcp_server.server import get_purchase_order_by_id as wrapper

    param = inspect.signature(wrapper).parameters.get("po_header_id")
    assert param is not None, (
        "get_purchase_order_by_id no longer has a 'po_header_id' "
        "parameter; F-006's fix may have been refactored away."
    )
    ann = param.annotation
    args = getattr(ann, "__args__", ())
    assert str in args, (
        f"po_header_id annotation is {ann!r}. F-006 requires it to admit "
        f"str — OrderNumber values like 'US164932' are strings on this "
        f"pod, and the schema FastMCP derives from a bare `int` "
        f"annotation rejects them at dispatch."
    )


# ─────────────────────────────────────────────────────────────────────
# Layer 2 — the contract, at the layer the original error came from
# ─────────────────────────────────────────────────────────────────────


def test_mcp_call_accepts_alpha_order_number():
    """End-to-end: the MCP boundary must not reject 'US164932'.

    Exercises the FastMCP-derived schema (the site of the original
    ``int_parsing`` error). Pre-fix this surfaces the Pydantic error;
    post-fix the string is admitted and passed to the resolver, which
    returns PO US164932 (POHeaderId 560869 per the F-006 evidence).

    Needs the pod — the resolver does a real Fusion lookup — and is
    therefore deterministic when the pod is up (single-run test, per
    FIX_PLAN §8.3.2).

    Tolerates the two legitimate post-fix outcomes: a successful result,
    or a not-found if the pod has dropped US164932. It asserts on the
    ABSENCE of the pre-fix error, which is what distinguishes before from
    after regardless of which of those two the call returns.
    """
    import asyncio

    from fastmcp import Client

    from spire.mcp_server.server import mcp

    async def _call():
        async with Client(mcp) as client:
            try:
                return await client.call_tool(
                    "get_purchase_order_by_id",
                    {"po_header_id": "US164932"},
                )
            except Exception as exc:  # noqa: BLE001 - the shape IS the test
                return exc

    outcome = asyncio.run(_call())
    text = repr(outcome)

    # 1. The load-bearing assertion: the pre-fix error must not appear.
    #    Its two identifying fragments are the Pydantic type tag and the
    #    field name — both present in the server's WARNING line, both
    #    absent from any success or not-found outcome.
    assert "int_parsing" not in text, (
        f"the MCP boundary still rejects the alpha OrderNumber. Got: "
        f"{text[:600]}"
    )
    assert not ("po_header_id" in text and "valid integer" in text), (
        f"a Pydantic integer-parse error for po_header_id resurfaced. "
        f"Got: {text[:600]}"
    )

    # 2. The call must have REACHED the tool. Without this, a transport
    #    or connection failure — an exception whose text happens to lack
    #    the pre-fix fragments — would pass the assertions above
    #    (verified: an earlier draft did exactly that, connecting to
    #    nothing in 1.9s and passing). A real call returns
    #    CallToolResult; a failure returns an Exception. Distinguish
    #    explicitly rather than inferring from text.
    from fastmcp.client.client import CallToolResult

    assert isinstance(outcome, CallToolResult), (
        f"the MCP call did not reach the tool — got {type(outcome).__name__}: "
        f"{text[:600]}"
    )
    # And the response must carry a PO header — either US164932 (the
    # pod's current value, POHeaderId 560869) or a well-formed not-found
    # if the pod ever drops it. Either is a legitimate post-fix outcome;
    # neither is the pre-fix crash.
    assert "POHeaderId" in text or "found" in text.lower(), (
        f"the tool returned a shape that carries neither a PO header nor "
        f"a not-found marker. Got: {text[:600]}"
    )
