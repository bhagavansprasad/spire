"""FastAPI backend for the SPIRE UI (Doc B §5.1).

Two endpoints:
  GET  /status   — liveness + readiness
  POST /prompt   — run a prompt through the pipeline

Node-level timings come from GRAPH.astream_events(version="v2"). The
final GraphState is the last on_chain_end event whose output carries
the input key ("prompt") — that identifies the root graph, not a node.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from spire.api.models import (
    CLIAnswer,
    ErrorAnswer,
    ErrorDetail,
    Metadata,
    PersonaInfo,
    PromptRequest,
    ResponseEnvelope,
    StageTiming,
    StatusResponse,
)
from spire.api.translate import translate
from spire.rendering.formatters import render_cli_stdout
from spire.config import load_persona


# ── Configuration ────────────────────────────────────────────────────

_STARTED_AT = datetime.now(timezone.utc)
VERSION = "0.1.0"
_PIPELINE_NODES = {"parse", "plan", "execute", "synthesize"}


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


MCP_URL = _env("SPIRE_MCP_URL", "http://127.0.0.1:3333/mcp")
UI_ORIGIN = _env("SPIRE_UI_ORIGIN", "http://localhost:8888")
API_HOST = _env("SPIRE_API_HOST", "0.0.0.0")
API_PORT = int(_env("SPIRE_API_PORT", "8000"))


def _uptime_s() -> int:
    return int((datetime.now(timezone.utc) - _STARTED_AT).total_seconds())


def _mask_password(password: str) -> str:
    """Display form: first 2, last 2, dots between."""
    if not password or len(password) < 8:
        return "\u2022" * 8
    return password[:2] + "\u2022" * (len(password) - 4) + password[-2:]


# ── Lifespan ─────────────────────────────────────────────────────────


async def _maybe_await(value):
    return await value if inspect.isawaitable(value) else value


async def _load_menu():
    from spire.nl_parser.vocabulary import load_kg_menu
    return await _maybe_await(load_kg_menu())


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.menu = None
    app.state.mcp = None
    app.state.persona = None
    app.state.pipeline_ready = False
    app.state.pipeline_error = None
    app.state.lock = asyncio.Lock()

    try:
        app.state.menu = await _load_menu()
    except Exception as exc:                                # noqa: BLE001
        app.state.pipeline_error = f"menu load failed: {exc}"

    try:
        _persona = load_persona(
            os.environ.get("SPIRE_PERSONA", "default_dev")
        )
        _fusion = getattr(_persona, "fusion", None)
        if _fusion is not None:
            app.state.persona = PersonaInfo(
                base_url=(getattr(_fusion, "base_url", "") or "").split("://", 1)[-1].split(".", 1)[0],
                username=getattr(_fusion, "username", "") or "",
                password_masked=_mask_password(
                    getattr(_fusion, "password", "") or ""
                ),
            )
    except Exception:                                       # noqa: BLE001
        app.state.persona = None

    try:
        from fastmcp import Client
        client = Client(MCP_URL)
        await client.__aenter__()
        app.state.mcp = client
    except Exception as exc:                                # noqa: BLE001
        prior = app.state.pipeline_error
        app.state.pipeline_error = (
            f"{prior} | mcp connect failed: {exc}" if prior
            else f"mcp connect failed: {exc}"
        )

    app.state.pipeline_ready = (
        app.state.menu is not None and app.state.mcp is not None
    )

    try:
        yield
    finally:
        if app.state.mcp is not None:
            try:
                await app.state.mcp.__aexit__(None, None, None)
            except Exception:                               # noqa: BLE001
                pass


# ── App ──────────────────────────────────────────────────────────────

app = FastAPI(title="spire-api", version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[UI_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pipeline runner ──────────────────────────────────────────────────


async def _run_graph_traced(inputs: dict) -> tuple[dict, list[StageTiming]]:
    """Run the graph and collect per-node timings.

    Returns (final_state, stages). The final state is the last
    on_chain_end whose output is a dict carrying the input key
    "prompt" — that is the root graph's state merge, not a node's
    partial return.
    """
    from spire.graph.pipeline import GRAPH

    starts: dict = {}
    stages: list[StageTiming] = []
    final_state: dict = {}

    async for event in GRAPH.astream_events(inputs, version="v2"):
        ev = event.get("event")
        name = event.get("name")
        rid = event.get("run_id")

        if ev == "on_chain_start" and name in _PIPELINE_NODES:
            starts[rid] = (name, time.perf_counter())

        elif ev == "on_chain_end" and name in _PIPELINE_NODES:
            entry = starts.pop(rid, None)
            if entry is not None:
                node_name, t0 = entry
                stages.append(
                    StageTiming(
                        name=node_name,
                        ms=int((time.perf_counter() - t0) * 1000),
                    )
                )

        elif ev == "on_chain_end":
            out = (event.get("data") or {}).get("output")
            if isinstance(out, dict) and "prompt" in out:
                final_state = out

    return final_state, stages


# ── Endpoints ────────────────────────────────────────────────────────


@app.get("/status")
async def status(request: Request) -> JSONResponse:
    ready = bool(getattr(request.app.state, "pipeline_ready", False))

    if not ready:
        body = StatusResponse(
            ok=False,
            version=VERSION,
            started_at=_STARTED_AT.isoformat(),
            uptime_s=_uptime_s(),
            kg_version=None,
            pipeline_ready=False,
            error=(
                getattr(request.app.state, "pipeline_error", None)
                or "pipeline not initialised"
            ),
            persona=getattr(request.app.state, "persona", None),
        )
        return JSONResponse(status_code=503, content=body.model_dump())

    body = StatusResponse(
        ok=True,
        version=VERSION,
        started_at=_STARTED_AT.isoformat(),
        uptime_s=_uptime_s(),
        kg_version=None,
        pipeline_ready=True,
        persona=getattr(request.app.state, "persona", None),
    )
    return JSONResponse(status_code=200, content=body.model_dump())


def _not_ready_envelope(request_id: str, reason: str) -> ResponseEnvelope:
    return ResponseEnvelope(
        request_id=request_id,
        kind="error",
        answer=ErrorAnswer(
            text="Pipeline not ready.",
            error=ErrorDetail(stage="startup", message=reason, retryable=True),
        ),
        metadata=Metadata(
            latency_ms=0, llm_calls=0, tokens_in=0, tokens_out=0,
            kg_version=None, stages=[],
        ),
    )


@app.post("/prompt")
async def prompt(req: PromptRequest, request: Request) -> JSONResponse:
    request_id = str(uuid4())

    if not getattr(request.app.state, "pipeline_ready", False):
        env = _not_ready_envelope(
            request_id,
            getattr(request.app.state, "pipeline_error", None)
            or "pipeline not initialised",
        )
        return JSONResponse(status_code=503, content=env.model_dump())

    inputs = {
        "prompt": req.prompt,
        "menu": request.app.state.menu,
        "session": request.app.state.mcp,
    }

    t0 = time.perf_counter()
    try:
        async with request.app.state.lock:
            final_state, stages = await _run_graph_traced(inputs)
    except Exception as exc:                                # noqa: BLE001
        latency_ms = int((time.perf_counter() - t0) * 1000)
        env = ResponseEnvelope(
            request_id=request_id,
            kind="error",
            answer=ErrorAnswer(
                text=f"Graph invocation failed: {exc}",
                error=ErrorDetail(
                    stage="invoke",
                    message=str(exc),
                    retryable=True,
                ),
            ),
            metadata=Metadata(
                latency_ms=latency_ms, llm_calls=0, tokens_in=0,
                tokens_out=0, kg_version=None, stages=[],
            ),
        )
        return JSONResponse(status_code=500, content=env.model_dump())

    latency_ms = int((time.perf_counter() - t0) * 1000)
    # UI contract: show the CLI's stdout verbatim. render_cli_stdout
    # is the shared renderer promptkit.py also emits through, so
    # the two cannot drift.
    cli_text = render_cli_stdout(final_state, request.app.state.menu)

    envelope = ResponseEnvelope(
        request_id=request_id,
        kind="cli",
        answer=CLIAnswer(text=cli_text),
        metadata=Metadata(
            latency_ms=latency_ms,
            llm_calls=0,
            tokens_in=0,
            tokens_out=0,
            kg_version=None,
            stages=stages,
        ),
    )
    return JSONResponse(status_code=200, content=envelope.model_dump())


# ── Entry point ──────────────────────────────────────────────────────


def main() -> None:
    import uvicorn

    uvicorn.run(
        "spire.api.server:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get(
            "SPIRE_FORWARDED_ALLOW_IPS", "127.0.0.1"
        ),
    )


if __name__ == "__main__":
    main()