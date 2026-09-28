"""Streamlit frontend for the SPIRE API (Doc B §5.1.6).

One page. Header with connection indicator, one input, one answer.
Reads the JSON envelope from POST /prompt and renders whichever of the
five kinds came back.

Run:      spire-ui
Config:   SPIRE_API_URL (default http://localhost:8000)
Default:  binds 0.0.0.0:8888

This module RENDERS ONLY. It is executed by Streamlit's runtime, which
sets a ScriptRunContext before running the file. The console-script
entry point lives in __main__.py, which launches Streamlit on this file.
Do not add a main() here — the two execution contexts (imported by
__main__.py vs executed as a Streamlit script) would otherwise collide.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
import streamlit as st


API_URL = os.environ.get("SPIRE_API_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT = float(os.environ.get("SPIRE_UI_TIMEOUT", "180"))


# ── API helpers ──────────────────────────────────────────────────────


def _get_status() -> dict | None:
    try:
        r = httpx.get(f"{API_URL}/status", timeout=5.0)
        return {"ok": True, "status_code": r.status_code, "body": r.json()}
    except Exception as exc:                                # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _post_prompt(prompt: str) -> dict:
    r = httpx.post(
        f"{API_URL}/prompt",
        json={"prompt": prompt},
        timeout=REQUEST_TIMEOUT,
    )
    return r.json()


# ── Cell flattening ──────────────────────────────────────────────────
#
# The dataframe cannot render nested lists/dicts — Streamlit shows them
# as "[object Object]". The synthesizer's records nest buyers, lines,
# schedules, contacts, addresses under each row. Flatten those to a
# readable string before display.
#
# Two-step: try the pretty form first (join a "name-like" field), fall
# back to compact JSON. Pretty is what a tester reads; JSON is what they
# paste into a bug report when pretty loses information.
#
# Name-like keys in priority order. These are the display fields the
# synthesizer's nested models actually carry:
#   BuyerInfo.display_name       -> "Gee, May"
#   ContactInfo.contact_name     -> "Kim, John"
#   LineInfo.description         -> "Marketing Assistance"
#   AddressInfo.formatted_address -> "US, 94043, CA, Mountain View"
_NAME_KEYS = (
    "display_name",
    "contact_name",
    "formatted_address",
    "description",
    "name",
)


def _pretty_from_dict(d: dict) -> str | None:
    """Return the first name-like field of a dict, or None."""
    for key in _NAME_KEYS:
        v = d.get(key)
        if v:
            return str(v)
    return None


def _flatten_cell(value: Any) -> Any:
    """Return a scalar Streamlit can render. Lists/dicts become strings."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, list):
        if not value:
            return ""
        # Pretty: list of dicts each carrying a name-like field.
        if all(isinstance(x, dict) for x in value):
            names: list[str] = []
            for item in value:
                pretty = _pretty_from_dict(item)
                if pretty is None:
                    break
                names.append(pretty)
            else:
                return ", ".join(names)
        return json.dumps(value, separators=(",", ":"), default=str)

    if isinstance(value, dict):
        # A single dict — e.g. PurchaseOrderRecord.buyer, or lifecycle
        # DFF. Try the name-like lookup first; fall back to JSON.
        pretty = _pretty_from_dict(value)
        if pretty is not None:
            return pretty
        return json.dumps(value, separators=(",", ":"), default=str)

    return str(value)


def _flatten_records(records: list[dict]) -> list[dict]:
    """One pass over each row. Every cell becomes a scalar."""
    return [
        {k: _flatten_cell(v) for k, v in row.items()}
        for row in records
    ]


# ── Renderers ────────────────────────────────────────────────────────


def _render_metadata(meta: dict) -> None:
    with st.expander("Metadata", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Latency", f"{meta.get('latency_ms', 0)} ms")
        c2.metric("LLM calls", meta.get("llm_calls", 0))
        c3.metric("Tokens in", meta.get("tokens_in", 0))
        c4.metric("Tokens out", meta.get("tokens_out", 0))

        stages = meta.get("stages") or []
        if stages:
            st.caption("Stage breakdown")
            st.dataframe(stages, width="stretch", hide_index=True)
        else:
            st.caption("Stage breakdown: not available for this run.")

        kv = meta.get("kg_version")
        st.caption(f"KG version: {kv if kv else '(not tracked until Phase 3g)'}")


def _render_text(answer: dict, meta: dict) -> None:
    if answer.get("text"):
        st.markdown(answer["text"])


def _render_table(answer: dict, meta: dict) -> None:
    if answer.get("truncated") and answer.get("truncation_note"):
        st.warning(answer["truncation_note"])
    if answer.get("text"):
        st.markdown(answer["text"])
    records = answer.get("records") or []
    if records:
        st.dataframe(
            _flatten_records(records),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("(no records)")


def _render_refusal(answer: dict, meta: dict) -> None:
    detail = answer.get("refusal") or {}
    st.warning(detail.get("reason") or "Refused.")
    if detail.get("solution"):
        st.info(detail["solution"])
    if detail.get("example"):
        st.code(detail["example"], language=None)


def _render_partial(answer: dict, meta: dict) -> None:
    st.warning("Partial result — some steps failed.")
    if answer.get("text"):
        st.markdown(answer["text"])
    records = answer.get("records") or []
    if records:
        st.dataframe(
            _flatten_records(records),
            width="stretch",
            hide_index=True,
        )
    failed = answer.get("failed_steps") or []
    if failed:
        with st.expander("Failed steps"):
            st.json(failed)


def _render_error(answer: dict, meta: dict) -> None:
    err = answer.get("error") or {}
    stage = err.get("stage", "?")
    message = err.get("message", answer.get("text") or "Unknown error")
    st.error(f"{stage}: {message}")
    if not err.get("retryable", True):
        st.caption("This failure will not be fixed by retrying.")


def _render_cli(answer: dict, meta: dict) -> None:
    """Render the CLI's stdout verbatim.

    No parsing, no reformatting, no per-section widgets. The text
    arrives pre-formatted from spire.rendering.formatters.
    render_cli_stdout, the same function promptkit --run prints
    through, so this block is the CLI's stdout character for
    character.
    """
    text = answer.get("text") or ""
    if not text.strip():
        st.caption("(empty response)")
        return
    st.code(text, language=None)


_RENDERERS = {
    # The CLI kind is what the API produces by default; the other
    # kinds are kept so a hand-built envelope still renders.
    "cli":       _render_cli,
    "text":      _render_text,
    "table": _render_table,
    "refusal": _render_refusal,
    "partial": _render_partial,
    "error": _render_error,
}


# ── Page ─────────────────────────────────────────────────────────────


def _page() -> None:
    st.set_page_config(page_title="SPIRE", layout="wide")

    # Zone 1 — header
    col_title, col_status = st.columns([4, 1])
    with col_title:
        st.title("SPIRE")
        st.caption("Natural-language query over Oracle Fusion Cloud")
    with col_status:
        status = _get_status()
        if status and status.get("ok") and status.get("status_code") == 200:
            st.success("Connected")
        else:
            st.error("Not connected")
            if status and status.get("ok"):
                body = status.get("body") or {}
                if body.get("error"):
                    st.caption(body["error"])
            elif status:
                st.caption(status.get("error", ""))

    st.divider()

    # Zone 2 — input
    prompt = st.text_input("Ask a question", key="prompt_input")
    submit = st.button("Submit", type="primary")

    # Zone 3 — answer
    if submit and prompt.strip():
        with st.spinner("Thinking…"):
            try:
                env = _post_prompt(prompt.strip())
            except Exception as exc:                        # noqa: BLE001
                st.error(f"Request to API failed: {exc}")
                return

        kind = env.get("kind", "error")
        answer = env.get("answer") or {}
        meta = env.get("metadata") or {}

        renderer = _RENDERERS.get(kind, _render_error)
        renderer(answer, meta)

        _render_metadata(meta)

        with st.expander("Raw response", expanded=False):
            st.json(env)
    elif submit:
        st.info("Type a question first.")


# ── Auto-run under Streamlit ─────────────────────────────────────────
#
# Streamlit executes this file as a script and sets a ScriptRunContext
# in the executing thread before running it. If that context exists, we
# are under Streamlit and should render. If not, we are being imported
# (by __main__.py, or by anything else) and must do nothing — the
# entry point in __main__.py will launch Streamlit, which will re-enter
# this module with the context set.

from streamlit.runtime.scriptrunner import get_script_run_ctx  # noqa: E402

if get_script_run_ctx() is not None:
    _page()