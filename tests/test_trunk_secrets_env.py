"""Tests para load_secrets_env (trunk_server.py).

Cubre:
- fichero con ``export KEY="VALUE"``, ``KEY=VALUE``, comentario y línea vacía.
- fichero inexistente → {}.
- valores con comillas simples.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.mcp.trunk_server import load_secrets_env


def test_load_secrets_env_basic(tmp_path: Path) -> None:
    """Parsea export/bare, ignora comentarios y vacías, quita comillas dobles."""
    secrets = tmp_path / "secrets.env"
    secrets.write_text(
        'export A="uno"\n'
        "B=dos\n"
        "# esto es un comentario\n"
        "\n",
        encoding="utf-8",
    )
    result = load_secrets_env(secrets)
    assert result == {"A": "uno", "B": "dos"}


def test_load_secrets_env_missing() -> None:
    """Fichero inexistente → dict vacío."""
    result = load_secrets_env(Path("/tmp/atlas_nonexistent_secrets_xyz.env"))
    assert result == {}


def test_load_secrets_env_single_quotes(tmp_path: Path) -> None:
    """Valores con comillas simples también se desenvuelven."""
    secrets = tmp_path / "secrets.env"
    secrets.write_text("C='tres'\n", encoding="utf-8")
    result = load_secrets_env(secrets)
    assert result == {"C": "tres"}
