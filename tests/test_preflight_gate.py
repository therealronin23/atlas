"""Tests para PreflightGate — el primer paso barato/determinista de autoauditoría.

Cubre: escaneo de CVEs vía pip-audit (mockeado, nunca real en test) + radar de
saneamiento (sanitation_audit.py real, read-only, rápido). Ver spec en la tarea
del roadmap "juicio real para autoauditoría".
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from atlas.core.self_maintenance.preflight_gate import PreflightGate, PreflightResult


def _fake_run_factory(stdout: str, returncode: int = 0, stderr: str = ""):
    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    return _fake_run


def test_no_cves_passes(monkeypatch):
    payload = {
        "dependencies": [
            {"name": "requests", "version": "2.31.0", "vulns": []},
            {"name": "cryptography", "version": "49.0.0", "vulns": []},
        ],
        "fixes": [],
    }
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run",
        _fake_run_factory(json.dumps(payload), returncode=0),
    )
    gate = PreflightGate()
    result = gate.check()
    assert result.passed is True
    assert result.cve_found is False
    assert result.cve_findings == []


def test_cves_found_fails(monkeypatch, tmp_path):
    payload = {
        "dependencies": [
            {
                "name": "somepkg",
                "version": "1.0.0",
                "vulns": [
                    {
                        "id": "CVE-2026-0001",
                        "fix_versions": ["1.0.1"],
                        "description": "algo malo",
                    }
                ],
            },
            {"name": "otherpkg", "version": "2.0.0", "vulns": []},
        ],
        "fixes": [],
    }
    # pip-audit devuelve returncode != 0 cuando SÍ encuentra vulnerabilidades
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run",
        _fake_run_factory(json.dumps(payload), returncode=1),
    )
    # Raíz aislada: sin ella el gate descubriría los venvs hermanos REALES
    # de la máquina y el recuento dependería de qué hay instalado.
    gate = PreflightGate(repo_root=tmp_path)
    result = gate.check()
    assert result.passed is False
    assert result.cve_found is True
    assert len(result.cve_findings) == 1
    finding = result.cve_findings[0]
    assert "somepkg" in finding
    assert "1.0.0" in finding
    assert "CVE-2026-0001" in finding
    assert "1.0.1" in finding


def test_pip_audit_raises_fails_closed(monkeypatch, tmp_path):
    def _raise_run(*args, **kwargs):
        raise OSError("pip-audit no encontrado")

    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run", _raise_run
    )
    # Raíz aislada: sin ella el gate descubriría los venvs hermanos REALES
    # de la máquina y el recuento dependería de qué hay instalado.
    gate = PreflightGate(repo_root=tmp_path)
    result = gate.check()
    assert result.passed is False
    assert result.cve_found is True
    assert len(result.cve_findings) == 1
    assert "pip-audit no pudo ejecutarse" in result.cve_findings[0]


def test_pip_audit_non_json_stdout_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run",
        _fake_run_factory("esto no es json", returncode=0, stderr="algo raro"),
    )
    # Raíz aislada: sin ella el gate descubriría los venvs hermanos REALES
    # de la máquina y el recuento dependería de qué hay instalado.
    gate = PreflightGate(repo_root=tmp_path)
    result = gate.check()
    assert result.passed is False
    assert result.cve_found is True
    assert len(result.cve_findings) == 1
    assert "no-JSON" in result.cve_findings[0] or "pip-audit no pudo ejecutarse" in result.cve_findings[0]


def test_sanitation_findings_has_expected_keys(monkeypatch):
    payload = {"dependencies": [{"name": "requests", "version": "2.31.0", "vulns": []}], "fixes": []}
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run",
        _fake_run_factory(json.dumps(payload), returncode=0),
    )
    gate = PreflightGate()
    result = gate.check()
    assert set(result.sanitation_findings.keys()) == {
        "vapor",
        "classified_zero_importers",
        "graveyard_overdue",
        "empty_dirs",
        "stale_refs",
        "docs_index_drift",  # 2026-07-08: el orden de docs entra al preflight
        "docs_graph_drift",  # 2026-07-08: y el grafo de enlaces también
        "ecosystem_map_drift",  # 2026-07-22: MAXIMUS Cycle 13, spec B+C §5
        # 2026-07-30: la deriva canon↔grafo AST pertenece a ESTA puerta, no
        # sólo al radar manual — es la que gobierna la automodificación, así
        # que el lazo no debe poder proponerse cambios mientras el canon
        # miente sobre qué está cableado. El dict de _run_sanitation es
        # explícito: un detector nuevo en sanitation_audit.py NO llega aquí
        # solo, y este test es lo que lo fuerza.
        "component_wiring_drift",
    }
    for key, value in result.sanitation_findings.items():
        assert isinstance(value, list)


def test_sanitation_audit_load_failure_yields_error_key(monkeypatch):
    payload = {"dependencies": [], "fixes": []}
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run",
        _fake_run_factory(json.dumps(payload), returncode=0),
    )
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.importlib.util.spec_from_file_location",
        lambda *args, **kwargs: None,
    )
    gate = PreflightGate()
    result = gate.check()
    assert "error" in result.sanitation_findings
    assert isinstance(result.sanitation_findings["error"], list)
    assert len(result.sanitation_findings["error"]) == 1


def test_to_dict_roundtrip():
    result = PreflightResult(
        passed=False,
        cve_found=True,
        cve_findings=["pkg==1.0.0: CVE-2026-9999 (fix: 1.0.1)"],
        sanitation_findings={
            "vapor": ["a.py"],
            "graveyard_overdue": [],
            "empty_dirs": [],
            "stale_refs": ["README.md -> docs/x.md (no existe)"],
        },
    )
    d = result.to_dict()
    assert d == {
        "passed": False,
        "cve_found": True,
        "cve_findings": ["pkg==1.0.0: CVE-2026-9999 (fix: 1.0.1)"],
        "cve_advisories": [],
        "sanitation_findings": {
            "vapor": ["a.py"],
            "graveyard_overdue": [],
            "empty_dirs": [],
            "stale_refs": ["README.md -> docs/x.md (no existe)"],
        },
    }


# ---------------------------------------------------------------------------
# Los venvs aislados también entran en el barrido
# ---------------------------------------------------------------------------
#
# Encontrado el 2026-08-10: `_scan_cves` corría pip-audit con `sys.executable`,
# o sea SÓLO el venv principal. Los tres venvs aislados del repo llevaban desde
# que existen sin auditar, y el primer barrido sacó 11 CVEs en `.venv-scraping`
# —aiohttp y h2, justo el proceso que trae contenido remoto no confiable—.
# Aislado no es exento: un venv que nadie audita es igual de explotable que uno
# que nadie aisló.


def _venv_falso(raiz, nombre: str):
    d = raiz / nombre / "lib" / "python3.12" / "site-packages"
    d.mkdir(parents=True)
    (raiz / nombre / "bin").mkdir(parents=True)
    (raiz / nombre / "bin" / "python").write_text("#!/bin/sh\n")
    return raiz / nombre


def test_descubre_los_venvs_aislados_del_repo(tmp_path, monkeypatch):
    """Descubiertos, no listados a mano: una lista de nombres se queda vieja en
    cuanto alguien añade un venv, y ése es justo el fallo que se está
    arreglando."""
    _venv_falso(tmp_path, ".venv-scraping")
    _venv_falso(tmp_path, ".venv-desktop")
    (tmp_path / "src").mkdir()
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate._REPO_ROOT", tmp_path
    )

    encontrados = PreflightGate(repo_root=tmp_path)._isolated_venvs()

    assert {p.name for p in encontrados} == {".venv-scraping", ".venv-desktop"}


def test_un_directorio_sin_interprete_no_cuenta(tmp_path, monkeypatch):
    (tmp_path / ".venv-basura").mkdir()
    (tmp_path / "src").mkdir()

    assert PreflightGate(repo_root=tmp_path)._isolated_venvs() == []


def test_una_cve_en_un_venv_cableado_bloquea(tmp_path, monkeypatch):
    """`.venv-scraping` lo invoca `crawler.py`: sus CVEs son ruta de ataque."""
    _venv_falso(tmp_path, ".venv-scraping")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "crawler.py").write_text('P = ".venv-scraping/bin/python3"\n')
    payload = {"dependencies": [
        {"name": "aiohttp", "version": "3.14.1",
         "vulns": [{"id": "PYSEC-2026-3545", "fix_versions": ["3.14.3"]}]},
    ]}
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run",
        _fake_run_factory(json.dumps(payload), returncode=1),
    )

    resultado = PreflightGate(repo_root=tmp_path).check()

    assert resultado.cve_found is True
    assert resultado.passed is False
    assert any(".venv-scraping" in f and "aiohttp" in f for f in resultado.cve_findings)


def test_una_cve_en_un_venv_sin_cablear_avisa_pero_no_bloquea(tmp_path, monkeypatch):
    """`.venv-desktop` no lo invoca ningún camino de runtime (su tool lanza
    RuntimeError por diseño). Bloquear el lazo entero por una CVE inalcanzable
    es el fail-closed sobre falso positivo que ya se pagó esta semana; callarla
    es lo contrario. Se avisa."""
    _venv_falso(tmp_path, ".venv-desktop")
    (tmp_path / "src").mkdir()
    payload = {"dependencies": [
        {"name": "pillow", "version": "11.3.0",
         "vulns": [{"id": "PYSEC-2026-2256", "fix_versions": ["12.3.0"]}]},
    ]}
    monkeypatch.setattr(
        "atlas.core.self_maintenance.preflight_gate.subprocess.run",
        _fake_run_factory(json.dumps(payload), returncode=1),
    )

    resultado = PreflightGate(repo_root=tmp_path).check()

    assert resultado.passed is False, "el venv principal sí bloquea"
    assert any(".venv-desktop" in a for a in resultado.cve_advisories)
    assert not any(".venv-desktop" in f for f in resultado.cve_findings)


def test_los_avisos_viajan_en_el_dict(tmp_path):
    r = PreflightResult(
        passed=True, cve_found=False, cve_findings=[],
        cve_advisories=[".venv-desktop pillow==11.3.0: PYSEC-2026-2256"],
        sanitation_findings={},
    )

    assert r.to_dict()["cve_advisories"] == [
        ".venv-desktop pillow==11.3.0: PYSEC-2026-2256"
    ]


def test_mencionar_un_venv_no_es_invocarlo(tmp_path):
    """Los dos falsos positivos reales, vistos al ejecutar el barrido de verdad:
    los venvs aparecen en listas de exclusión de barrido (`tool_coder`,
    `dormant_modules`) y en mensajes de error ("pendiente de un entorno con
    Xvfb :99 + .venv-desktop"). Con el criterio ingenuo los TRES bloqueaban y la
    puerta se volvía inservible."""
    _venv_falso(tmp_path, ".venv-desktop")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "excluye.py").write_text(
        'IGNORAR = (".git", ".venv", ".venv-desktop", "__pycache__")\n'
    )
    (tmp_path / "src" / "avisa.py").write_text(
        'MSG = "no cableado: falta un entorno con Xvfb :99 + .venv-desktop"\n'
    )
    gate = PreflightGate(repo_root=tmp_path)

    assert gate._venv_en_ruta_de_runtime(tmp_path / ".venv-desktop") is False


def test_construir_su_interprete_si_es_invocarlo(tmp_path):
    """La forma real de `crawler.py`: la ruta se compone por partes."""
    _venv_falso(tmp_path, ".venv-scraping")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "crawler.py").write_text(
        '_PY = _REPO_ROOT / ".venv-scraping" / "bin" / "python3"\n'
    )
    gate = PreflightGate(repo_root=tmp_path)

    assert gate._venv_en_ruta_de_runtime(tmp_path / ".venv-scraping") is True


def test_el_propio_venv_no_se_cuenta_como_aislado():
    """Visto al ejecutarlo: `bin/python` de un venv es un SYMLINK al intérprete
    del sistema, así que `Path(sys.executable).resolve()` devuelve /usr y el
    venv principal se colaba en su propia lista de aislados — auditándose dos
    veces y duplicando cada hallazgo."""
    import sys as _sys
    from pathlib import Path as _Path

    aislados = {p.resolve() for p in PreflightGate()._isolated_venvs()}

    assert _Path(_sys.prefix).resolve() not in aislados
