"""Pydantic models for the SPIRE API envelope (Doc B §5.1.4).

Every response to POST /prompt is a ResponseEnvelope. `kind` is the
discriminator; `answer` is a discriminated union keyed on it.

The `partial` kind is unreachable today — the executor fails the whole
plan on any tool error. Phase 2 §8.3.7 changes that. The envelope
carries the kind now so the UI is written once.
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field


# ── Request ──────────────────────────────────────────────────────────


class PromptRequest(BaseModel):
    prompt: str
    session_id: str | None = None


# ── Metadata ─────────────────────────────────────────────────────────


class StageTiming(BaseModel):
    name: Literal["parse", "plan", "execute", "synthesize"]
    ms: int


class Metadata(BaseModel):
    latency_ms: int
    llm_calls: int                       # 0 until Phase 5 wires counters
    tokens_in: int                       # 0 until Phase 5
    tokens_out: int                      # 0 until Phase 5
    kg_version: str | None               # None until Phase 3g
    stages: list[StageTiming] = Field(default_factory=list)


# ── Answer variants ──────────────────────────────────────────────────


class TextAnswer(BaseModel):
    """Used for kind='text' and kind='table'.

    `records` empty → text only; non-empty → the UI renders a dataframe.
    """

    text: str
    records: list[dict] = Field(default_factory=list)
    truncated: bool = False
    truncation_note: str | None = None


class RefusalDetail(BaseModel):
    reason: str
    solution: str | None = None
    example: str | None = None


class RefusalAnswer(BaseModel):
    text: None = None
    refusal: RefusalDetail


class PartialAnswer(BaseModel):
    """Unreachable until Phase 2 §8.3.7 (partial execution)."""

    text: str
    records: list[dict] = Field(default_factory=list)
    coverage: Literal["partial"] = "partial"
    failed_steps: list[dict] = Field(default_factory=list)


class ErrorDetail(BaseModel):
    stage: str
    message: str
    retryable: bool


class ErrorAnswer(BaseModel):
    text: str
    error: ErrorDetail


class CLIAnswer(BaseModel):
    """Raw terminal text - the CLI's stdout, verbatim.

    The UI renders this in a monospace block and touches nothing else:
    no markdown, no dataframe, no per-section widgets.
    """
    text: str


Answer = Union[TextAnswer, RefusalAnswer, PartialAnswer, ErrorAnswer, CLIAnswer]


# ── Envelopes ────────────────────────────────────────────────────────


class ResponseEnvelope(BaseModel):
    request_id: str
    kind: Literal["text", "table", "refusal", "partial", "error", "cli"]
    answer: Answer
    metadata: Metadata


class PersonaInfo(BaseModel):
    base_url: str
    username: str
    password_masked: str


class StatusResponse(BaseModel):
    ok: bool
    service: Literal["spire-api"] = "spire-api"
    version: str
    started_at: str
    uptime_s: int
    kg_version: str | None
    pipeline_ready: bool
    error: str | None = None
    persona: PersonaInfo | None = None

