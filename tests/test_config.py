"""Tests for spire.config persona loader."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from spire.config import FusionCredentials, OracleCredentials, Persona, load_persona


SAMPLE_YAML = """
default_dev:
  fusion:
    base_url: "https://example.oraclecloud.com"
    username: "test@example.com"
    password: "fusion-secret"
    auth_type: "basic"
  oracle:
    dsn: "localhost:1521/FREEPDB1"
    username: "spire"
    password: "oracle-secret"

fusion_only:
  fusion:
    base_url: "https://example.oraclecloud.com"
    username: "test@example.com"
    password: "fusion-secret"
    auth_type: "basic"

malformed:
  fusion:
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


def test_load_persona_with_fusion_and_oracle(personas_file):
    persona = load_persona("default_dev")
    assert isinstance(persona, Persona)
    assert isinstance(persona.fusion, FusionCredentials)
    assert persona.fusion.base_url == "https://example.oraclecloud.com"
    assert persona.fusion.username == "test@example.com"
    assert persona.fusion.password == "fusion-secret"
    assert persona.fusion.auth_type == "basic"
    assert isinstance(persona.oracle, OracleCredentials)
    assert persona.oracle.dsn == "localhost:1521/FREEPDB1"
    assert persona.oracle.username == "spire"
    assert persona.oracle.password == "oracle-secret"


def test_load_persona_fusion_only_oracle_is_none(personas_file):
    """A persona without an `oracle:` block is still valid; oracle is None."""
    persona = load_persona("fusion_only")
    assert isinstance(persona, Persona)
    assert isinstance(persona.fusion, FusionCredentials)
    assert persona.oracle is None


def test_unknown_persona_raises_key_error(personas_file):
    with pytest.raises(KeyError, match="nonexistent"):
        load_persona("nonexistent")


def test_malformed_persona_raises_validation_error(personas_file):
    with pytest.raises(ValidationError):
        load_persona("malformed")
