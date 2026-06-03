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

