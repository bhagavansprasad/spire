"""Persona configuration loader.

Reads personas.yaml from the repo root and returns the requested persona
as a validated Pydantic model.

Usage:
    from spire.config import load_persona
    persona = load_persona("default_dev")
"""

from pathlib import Path

import yaml
from pydantic import BaseModel


PERSONAS_FILE = Path(__file__).resolve().parents[2] / "personas.yaml"


class Persona(BaseModel):
    base_url: str
    username: str
    password: str
    auth_type: str


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
