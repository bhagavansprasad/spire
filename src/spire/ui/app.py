"""Streamlit frontend for the SPIRE API.

ChatGPT-style single-frame layout:

  - Sidebar (left): compact brand block (icon + name), connection
    status, and a reserved persona section for a later change.
  - Main column: the user's prompt in a chat bubble, the assistant's
    answer in a monospace block below it, and the input pinned to the
    bottom by Streamlit.

ONE FRAME ONLY. The current prompt and its response live in a single
slot on ``st.session_state``. The next submit replaces them. No list,
no history, no persistence anywhere.

The answer is displayed exactly as the CLI prints it: the API returns
a ``kind="cli"`` envelope whose ``answer.text`` is
``render_cli_stdout``'s output, and this file drops that string into
``st.code(text, language=None)`` and touches nothing else.

Run:      spire-ui
Config:   SPIRE_API_URL (default http://localhost:8000)
Default:  binds 0.0.0.0:8888

This module RENDERS ONLY. It is executed by Streamlit's runtime, which
sets a ScriptRunContext before running the file. The console-script
entry point lives in __main__.py, which launches Streamlit on this
file. Do not add a main() here.
"""

from __future__ import annotations

import os

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


def _post_prompt_safe(prompt: str) -> dict:
    """Wrap _post_prompt so a request-level failure becomes an envelope
    the renderer can display. A failed POST should look like an
    assistant message, not a Streamlit traceback."""
    try:
        return _post_prompt(prompt)
    except Exception as exc:                                # noqa: BLE001
        return {
            "kind": "error",
            "answer": {
                "text": f"Request to API failed: {exc}",
                "error": {
                    "stage": "invoke",
                    "message": str(exc),
                    "retryable": True,
                },
            },
            "metadata": {},
        }


# ── Rendering ────────────────────────────────────────────────────────


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
        st.caption(
            f"KG version: {kv if kv else '(not tracked until Phase 3g)'}"
        )


def _render_answer(env: dict) -> None:
    """Render one response envelope.

    The API produces ``kind="cli"`` by default. ``kind="error"`` still
    appears if the pipeline fails before the CLI renderer runs. Any
    other kind is a legacy envelope and falls through to a text
    fallback; no path here reformats or parses the CLI text.
    """
    kind = env.get("kind", "error")
    answer = env.get("answer") or {}
    meta = env.get("metadata") or {}

    if kind == "cli":
        text = answer.get("text") or ""
        if text.strip():
            st.code(text, language=None)
        else:
            st.caption("(empty response)")
    elif kind == "error":
        err = answer.get("error") or {}
        msg = err.get("message") or answer.get("text") or "Unknown error"
        st.error(msg)
    else:
        # A shape the API no longer produces. Show whatever text came
        # back, unmodified.
        text = answer.get("text") or ""
        if text:
            st.code(text, language=None)
        else:
            st.caption(f"(unhandled kind: {kind})")

    if meta:
        _render_metadata(meta)

    with st.expander("Raw response", expanded=False):
        st.json(env)


# ── Sidebar ──────────────────────────────────────────────────────────


def _render_sidebar() -> None:
    with st.sidebar:
        # Brand block - compact. Icon is a PLACEHOLDER; the real Spire
        # icon will replace the div below when it's ready. Two ways:
        #
        #   st.image("path/to/spire-icon.png", width=28)
        #   st.logo("path/to/spire-icon.png")   # built-in sidebar logo
        #
        # The character &#9670; below is a blue filled diamond used as
        # a visual placeholder, not a permanent choice.
        st.markdown(
            """
            <div style="display: flex; align-items: center; gap: 12px;
                        padding: 8px 0 12px 0;">
              <div style="font-size: 28px; line-height: 1;
                          color: #2563eb;">&#9670;</div>
              <div>
                <div style="font-size: 19px; font-weight: 600;
                            letter-spacing: 0.02em;">SPIRE</div>
                <div style="font-size: 12px; color: #888;
                            margin-top: -1px;">Fusion NL query</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.divider()

        # Connection status
        status = _get_status()
        if status and status.get("ok") and status.get("status_code") == 200:
            st.markdown(
                "<div style='font-size: 12px; padding: 2px 0;'>"
                "<span style='color: #22c55e;'>&#9679;</span>&nbsp;"
                "Connected</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='font-size: 12px; padding: 2px 0;'>"
                "<span style='color: #ef4444;'>&#9679;</span>&nbsp;"
                "Not connected</div>",
                unsafe_allow_html=True,
            )
            if status and status.get("ok"):
                body = status.get("body") or {}
                if body.get("error"):
                    st.caption(body["error"])
            elif status:
                st.caption(status.get("error", ""))

        st.divider()

        # Persona block - RESERVED. A later change will add the four
        # persona fields here (base_url, username, password, auth_type)
        # with an empty value meaning "use the default from
        # personas.yaml".
        st.caption("Persona")
        st.caption("Uses defaults from `personas.yaml`.")


# ── Page ─────────────────────────────────────────────────────────────


def _page() -> None:
    st.set_page_config(
        page_title="SPIRE",
        page_icon="\U0001F537",     # blue diamond emoji, placeholder
        layout="centered",
        initial_sidebar_state="expanded",
    )

    _render_sidebar()

    # ONE frame only. The next submit replaces it. No list, no history.
    if "frame" not in st.session_state:
        st.session_state.frame = None

    frame = st.session_state.frame
    if frame is not None:
        with st.chat_message("user"):
            st.markdown(frame["prompt"])

        with st.chat_message("assistant"):
            env = frame.get("env")
            if env is None:
                with st.spinner("Thinking\u2026"):
                    env = _post_prompt_safe(frame["prompt"])
                st.session_state.frame["env"] = env
                st.rerun()
            _render_answer(env)
    else:
        st.markdown(
            "<div style='text-align: center; color: #999; "
            "padding: 96px 0; font-size: 14px;'>"
            "Ask a question to begin.</div>",
            unsafe_allow_html=True,
        )

    prompt = st.chat_input("Ask a question\u2026")
    if prompt:
        st.session_state.frame = {"prompt": prompt, "env": None}
        st.rerun()


# ── Auto-run under Streamlit ─────────────────────────────────────────
#
# Streamlit executes this file as a script and sets a ScriptRunContext
# before running it. If that context exists, we render. If not, we are
# being imported (by __main__.py) and must do nothing.

from streamlit.runtime.scriptrunner import get_script_run_ctx  # noqa: E402

if get_script_run_ctx() is not None:
    _page()
