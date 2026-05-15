"""Tests for spire.config persona loader."""

from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from spire.config import Persona, load_persona


SAMPLE_YAML = """
default_dev:
  base_url: "https://example.oraclecloud.com"
  username: "test@example.com"
  password: "secret123"
  auth_type: "basic"

malformed:
  base_url: "https://example.oraclecloud.com"
  username: "test@example.com"
  # password missing
  auth_type: "basic"
"""


@pytest.fixture
def personas_file(tmp_path):
    """Write a temp personas.yaml and patch the module to point at it."""
    path = tmp_path / "personas.yaml"
    path.write_text(SAMPLE_YAML)
    with patch("spire.config.PERSONAS_FILE", path):
        yield path


def test_load_valid_persona(personas_file):
    persona = load_persona("default_dev")
    assert isinstance(persona, Persona)
    assert persona.base_url == "https://example.oraclecloud.com"
    assert persona.username == "test@example.com"
    assert persona.password == "secret123"
    assert persona.auth_type == "basic"


def test_unknown_persona_raises_key_error(personas_file):
    with pytest.raises(KeyError, match="nonexistent"):
        load_persona("nonexistent")


def test_malformed_persona_raises_validation_error(personas_file):
    with pytest.raises(ValidationError):
        load_persona("malformed")
