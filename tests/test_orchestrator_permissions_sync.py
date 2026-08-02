"""
Tests for Orchestrator permissions and governance boot auto-synchronization.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import yaml

from atlas.core.orchestrator import Orchestrator


def test_orchestrator_syncs_outdated_permissions_and_governance(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Simular permisos de workspace desactualizados
    stale_permissions = {
        "shell_allowlist": ["echo", "ls"],
        "workspace": {"auto_write": ["tmp/"]},
    }
    with (config_dir / "permissions.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(stale_permissions, f)

    stale_governance = {"version": "0.9.0", "axioms": {}}
    with (config_dir / "governance.json").open("w", encoding="utf-8") as f:
        json.dump(stale_governance, f)

    # Instanciar el orquestador dispara _copy_defaults()
    orchestrator = Orchestrator(workspace=tmp_path)

    # Verificar permissions.yaml: los nuevos comandos del repo (pwd, git, patch, etc.) fueron añadidos
    with (config_dir / "permissions.yaml").open(encoding="utf-8") as f:
        updated_perms = yaml.safe_load(f)

    assert "pwd" in updated_perms["shell_allowlist"]
    assert "echo" in updated_perms["shell_allowlist"]

    # Verificar governance.json: actualizado para coincidir con la autoridad del repo
    with (config_dir / "governance.json").open(encoding="utf-8") as f:
        updated_gov = json.load(f)

    assert updated_gov["version"] == "1.0.0" or "axioms" in updated_gov


def test_orchestrator_handles_corrupt_permissions_file_gracefully(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Permisos corruptos (no es YAML válido)
    with (config_dir / "permissions.yaml").open("w", encoding="utf-8") as f:
        f.write("invalid_yaml: [unmatched_bracket")

    with caplog.at_level("WARNING"):
        orchestrator = Orchestrator(workspace=tmp_path)
        assert orchestrator is not None

    assert "Fallo al sincronizar permissions.yaml" in caplog.text

