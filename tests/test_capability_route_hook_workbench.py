"""Smoke test del hook completo (subprocess real) — mesa de trabajo
obligatoria cableada en capability_route_hook.py (2026-07-23)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_MIN_CATALOG = """
taxonomy: {}
sectors:
  programacion:
    label: Programación
    entries: []
"""


def _isolated_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs" / "design").mkdir(parents=True)
    (repo / "docs" / "design" / "mcp_catalog.yaml").write_text(_MIN_CATALOG, encoding="utf-8")
    return repo


def test_hook_prints_workbench_notice_when_stale(tmp_path: Path) -> None:
    repo = _isolated_repo(tmp_path)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = {"HOME": str(fake_home), "PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"}

    result = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "capability_route_hook.py"),
            "--prompt", "hola mundo", "--repo-root", str(repo),
        ],
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "mesa de trabajo" in result.stdout.lower()
    assert "workbench" in result.stdout.lower()
    findings = repo / "workspace" / "mcp" / "workbench_compliance_findings.jsonl"
    assert findings.is_file()


def test_hook_omits_workbench_notice_when_fresh(tmp_path: Path) -> None:
    repo = _isolated_repo(tmp_path)
    fake_home = tmp_path / "home"
    (fake_home / "atlas-mcp").mkdir(parents=True)
    from atlas.mcp.workbench_resources import record_consultation

    record_consultation(fake_home / "atlas-mcp" / "workbench_consultations.jsonl")
    env = {"HOME": str(fake_home), "PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"}

    result = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "capability_route_hook.py"),
            "--prompt", "hola mundo", "--repo-root", str(repo),
        ],
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "mesa de trabajo" not in result.stdout.lower()


def test_hook_stale_beyond_synthesis_cooldown_falls_back_safely_without_key(
    tmp_path: Path,
) -> None:
    """Fase 1 (2026-07-25): cuando la última consulta real es tan vieja que
    tocaría síntesis Gemini (is_synthesis_due) Y no hay GEMINI_API_KEY en el
    entorno (como en este subprocess aislado), la llamada real al hub debe
    fallar rápido y en silencio (auto-skip por falta de clave) -- el hook
    sigue devolviendo el aviso de texto plano de siempre, nunca cuelga ni
    revienta."""
    repo = _isolated_repo(tmp_path)
    fake_home = tmp_path / "home"
    (fake_home / "atlas-mcp").mkdir(parents=True)
    from datetime import datetime, timedelta, timezone

    old = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
    (fake_home / "atlas-mcp" / "workbench_consultations.jsonl").write_text(
        json.dumps({"at": old}) + "\n", encoding="utf-8"
    )
    env = {"HOME": str(fake_home), "PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"}

    result = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "capability_route_hook.py"),
            "--prompt", "hola mundo", "--repo-root", str(repo),
        ],
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "mesa de trabajo" in result.stdout.lower()


def test_hook_no_state_flag_also_skips_workbench_check(tmp_path: Path) -> None:
    """--no-state respeta su propio contrato ('no toca workspace/mcp') --
    aunque la mesa de trabajo esté stale, con --no-state no debe escribir ni
    avisar (mismo alcance que cooldown/telemetría)."""
    repo = _isolated_repo(tmp_path)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = {"HOME": str(fake_home), "PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"}

    result = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "capability_route_hook.py"),
            "--prompt", "hola mundo", "--no-state", "--repo-root", str(repo),
        ],
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "mesa de trabajo" not in result.stdout.lower()
    assert not (repo / "workspace" / "mcp").exists()
