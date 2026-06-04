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

GEMINI_MODEL = "gemini-2.5-pro"
GEMINI_TEMPERATURE = 0.0

# Provider seam. Today only "gemini" is wired; the factory is structured
# so Claude/OpenAI become two more branches plus their deps, without
# touching the parser, synthesizer, or graph. Override via env:
#   SPIRE_LLM_PROVIDER = gemini | anthropic | openai
#   SPIRE_LLM_MODEL    = optional model-name override
import os as _os

LLM_PROVIDER = _os.environ.get("SPIRE_LLM_PROVIDER", "gemini")
LLM_MODEL = _os.environ.get("SPIRE_LLM_MODEL", "")


def build_llm(temperature: float = GEMINI_TEMPERATURE):
    """Return a LangChain chat model for the configured provider.

    All branches return an object exposing the same
    ``with_structured_output(...).invoke(...)`` surface, so callers
    (parser, synthesizer, graph nodes) are provider-agnostic.

    Only "gemini" is implemented today; "anthropic" and "openai" are
    stubbed to raise a clear NotImplementedError until their deps and
    branches are added (incremental rollout).
    """
    provider = LLM_PROVIDER.lower()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=LLM_MODEL or GEMINI_MODEL,
            temperature=temperature,
        )

    if provider == "anthropic":
        raise NotImplementedError(
            "Anthropic provider not wired yet. Add langchain-anthropic and "
            "a ChatAnthropic branch in build_llm()."
        )

    if provider == "openai":
        raise NotImplementedError(
            "OpenAI provider not wired yet. Add langchain-openai and a "
            "ChatOpenAI branch in build_llm()."
        )

    raise ValueError(
        f"Unknown SPIRE_LLM_PROVIDER={LLM_PROVIDER!r}. "
        "Supported: gemini (anthropic, openai pending)."
    )


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

