"""Persona configuration loader.

Reads personas.yaml from the repo root and returns the requested persona
as a validated Pydantic model.

A persona groups together all credentials a single environment needs.
For Spire that currently means:
- Fusion REST API credentials (required)
- Oracle Database credentials (optional during transition; required
  once Dynamic Orchestration phases 03+ start needing the KG)

Usage:
    from spire.config import load_persona
    persona = load_persona("default_dev")
    print(persona.fusion.base_url)
    if persona.oracle:
        print(persona.oracle.dsn)
"""

from pathlib import Path

import yaml
from pydantic import BaseModel

from spire.diagnostics import get_logger


PERSONAS_FILE = Path(__file__).resolve().parents[2] / "personas.yaml"


# LLM provider and per-call token counts both ride on `spire.tokens`,
# gated by --show-tokens. They belong together: when you switch token
# reporting on, which model produced those numbers is exactly the
# context you want beside them. Silent unless the flag is set.
_log = get_logger("tokens")


# ─────────────────────────────────────────────────────────────────────
# LLM configuration (single source of truth)
#
# The model name and temperature used by the Design 3 LLM components
# (the nl_parser interpreter and the synthesizer). Centralized here so
# there is exactly one place to change the model. Both components import
# GEMINI_MODEL / GEMINI_TEMPERATURE from this module.
# ─────────────────────────────────────────────────────────────────────

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_TEMPERATURE = 0.0

# Cap output tokens on every provider. Structured-output parses and
# synthesizer responses are small (a DraftIntent is ~300 tokens); without
# a cap, a model that fails to converge can generate to its default
# ceiling (65520 on gemini-flash), turning a bad parse into a ~4-minute
# hang. Capping converts that into a ~2s fast failure the parser handles
# as a refusal. Raise only if a legitimate response is ever truncated.
LLM_MAX_OUTPUT_TOKENS = 8000

# Provider seam. Today only "gemini" is wired; the factory is structured
# so Claude/OpenAI become two more branches plus their deps, without
# touching the parser, synthesizer, or graph. Override via env:
#   SPIRE_LLM_PROVIDER = gemini | anthropic | openai
#   SPIRE_LLM_MODEL    = optional model-name override
import os as _os

LLM_PROVIDER = _os.environ.get("SPIRE_LLM_PROVIDER", "gemini")
LLM_MODEL = _os.environ.get("SPIRE_LLM_MODEL", "")

# Default model per provider (overridable via SPIRE_LLM_MODEL).
ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-5"


def build_llm(temperature: float = GEMINI_TEMPERATURE):
    """Return a LangChain chat model for the configured provider.

    All branches return an object exposing the same
    ``with_structured_output(...).invoke(...)`` surface, so callers
    (parser, synthesizer, graph nodes) are provider-agnostic.

    Gemini, Anthropic (Claude), and OpenAI are all implemented.
    """
    provider = LLM_PROVIDER.lower()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        model = LLM_MODEL or GEMINI_MODEL
        _log.debug("[llm] provider=gemini model=%s", model)
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            max_output_tokens=LLM_MAX_OUTPUT_TOKENS,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        model = LLM_MODEL or ANTHROPIC_MODEL
        _log.debug("[llm] provider=anthropic model=%s", model)
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=LLM_MAX_OUTPUT_TOKENS,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        model = LLM_MODEL or OPENAI_MODEL
        _log.debug("[llm] provider=openai model=%s", model)
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=LLM_MAX_OUTPUT_TOKENS,
        )

    raise ValueError(
        f"Unknown SPIRE_LLM_PROVIDER={LLM_PROVIDER!r}. "
        "Supported: gemini, anthropic, openai."
    )


def log_usage(raw_message, stage: str) -> None:
    """Record token usage for one LLM call, and log it.

    ``raw_message`` is the LangChain ``AIMessage`` returned under the
    ``"raw"`` key when a structured LLM is built with
    ``with_structured_output(..., include_raw=True)``. Its
    ``usage_metadata`` is normalized by LangChain across the gemini,
    anthropic, and openai providers, so the same field works for all.

    Two jobs, and they are deliberately independent. **Recording** into
    ``_USAGE_LOG`` happens unconditionally — ``usage_report()`` must be
    complete at the end of a run whether or not anyone was watching the
    per-call lines. **Logging** goes to ``spire.tokens`` and is silent
    unless ``--show-tokens`` is set.

    Before Phase 1 these were one statement, so the only way to get the
    running total was to accept a line of stderr per LLM call. Keep them
    separate: a future caller may want the numbers without the noise.

    Safe to call with None or an object lacking usage_metadata: it just
    records and logs zeros.
    """
    um = getattr(raw_message, "usage_metadata", None) or {}
    inp = um.get("input_tokens", 0)
    out = um.get("output_tokens", 0)
    _USAGE_LOG.append({"stage": stage, "in": inp, "out": out})
    _log.debug(
        "[llm] stage=%s in=%s out=%s total=%s", stage, inp, out, inp + out
    )


# Per-run token accumulator. The entry script clears it with
# reset_usage() at the start of a run and logs usage_report() at the end.
_USAGE_LOG: list[dict] = []


def reset_usage() -> None:
    """Clear accumulated token usage. Call at the start of a run."""
    _USAGE_LOG.clear()


def usage_report() -> str:
    """Return a small end-of-run token report from accumulated usage.

    Pure: returns the text, prints nothing. The caller decides where it
    goes — which is why this function needed no change in Phase 1, and
    is the pattern the rest of the codebase is moving toward.
    """
    if not _USAGE_LOG:
        return "Token usage:\n  (no LLM calls recorded)"
    lines = ["Token usage:"]
    tot_in = tot_out = 0
    for e in _USAGE_LOG:
        tot_in += e["in"]
        tot_out += e["out"]
        lines.append(
            f"  {e['stage']:<12} in={e['in']:>7}  out={e['out']:>7}  "
            f"total={e['in'] + e['out']:>7}"
        )
    lines.append(
        f"  {'TOTAL':<12} in={tot_in:>7}  out={tot_out:>7}  "
        f"total={tot_in + tot_out:>7}"
    )
    return "\n".join(lines)


class FusionCredentials(BaseModel):
    base_url: str
    username: str
    password: str
    auth_type: str


class OracleCredentials(BaseModel):
    dsn: str
    username: str
    password: str


class Persona(BaseModel):
    fusion: FusionCredentials
    oracle: OracleCredentials | None = None


def load_persona(name: str) -> Persona:
    """Load a persona by name from personas.yaml.

    Raises:
        FileNotFoundError: if personas.yaml is missing.
        KeyError: if the persona name is not in the file.
        pydantic.ValidationError: if the persona entry is malformed.
    """
    with open(PERSONAS_FILE) as f:
        data = yaml.safe_load(f)

    if name not in data:
        raise KeyError(f"Persona '{name}' not found in {PERSONAS_FILE}")

    return Persona(**data[name])
