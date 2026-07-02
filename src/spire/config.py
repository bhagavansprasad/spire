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


PERSONAS_FILE = Path(__file__).resolve().parents[2] / "personas.yaml"


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

# Provider seam. Today only "gemini" is wired; the factory is structured
# so Claude/OpenAI become two more branches plus their deps, without
# touching the parser, synthesizer, or graph. Override via env:
#   SPIRE_LLM_PROVIDER = gemini | anthropic | openai
#   SPIRE_LLM_MODEL    = optional model-name override
import os as _os
import sys as _sys

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
        print(f"[llm] provider=gemini model={model}", file=_sys.stderr)
        return ChatGoogleGenerativeAI(model=model, temperature=temperature)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        model = LLM_MODEL or ANTHROPIC_MODEL
        print(f"[llm] provider=anthropic model={model}", file=_sys.stderr)
        return ChatAnthropic(model=model, temperature=temperature)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        model = LLM_MODEL or OPENAI_MODEL
        print(f"[llm] provider=openai model={model}", file=_sys.stderr)
        return ChatOpenAI(model=model, temperature=temperature)

    raise ValueError( 
        f"Unknown SPIRE_LLM_PROVIDER={LLM_PROVIDER!r}. "
        "Supported: gemini, anthropic, openai."
    )


def log_usage(raw_message, stage: str) -> None:
    """Record and print token usage for one LLM call, in the [llm] style.

    ``raw_message`` is the LangChain ``AIMessage`` returned under the
    ``"raw"`` key when a structured LLM is built with
    ``with_structured_output(..., include_raw=True)``. Its
    ``usage_metadata`` is normalized by LangChain across the gemini,
    anthropic, and openai providers, so the same field works for all.

    The per-call numbers are also accumulated in ``_USAGE_LOG`` so the
    entry script can print a combined end-of-run report via
    ``usage_report()``. Call ``reset_usage()`` at the start of a run.

    Safe to call with None or an object lacking usage_metadata: it just
    records and prints zeros.
    """
    um = getattr(raw_message, "usage_metadata", None) or {}
    inp = um.get("input_tokens", 0)
    out = um.get("output_tokens", 0)
    _USAGE_LOG.append({"stage": stage, "in": inp, "out": out})
    print(
        f"[llm] stage={stage} in={inp} out={out} total={inp + out}",
        file=_sys.stderr,
    )


# Per-run token accumulator. The entry script clears it with
# reset_usage() at the start of a run and prints usage_report() at the end.
_USAGE_LOG: list[dict] = []


def reset_usage() -> None:
    """Clear accumulated token usage. Call at the start of a run."""
    _USAGE_LOG.clear()


def usage_report() -> str:
    """Return a small end-of-run token report from accumulated usage."""
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