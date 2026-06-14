"""ADR-039 slice 6 — DepScout (bumps PyPI) + DepProposer (patch → ColdUpdate).

Reglas que estos tests fijan:

- **CERO red real:** ``fetch`` es siempre un callable falso.
- **Egress gateado fail-closed:** dep cuya URL deniega el bridge → se omite.
- **Solo estable y estrictamente mayor:** pre-releases y versiones iguales/menores
  no generan candidato.
- **Materialización revisable:** el proposer construye un diff unificado válido
  (`a/ b/`) y lo entrega a un ``propose`` inyectado; **nunca aplica** (no se toca
  ColdUpdate real). Fail-closed si el piso no está en el ``pyproject``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from atlas.core.self_maintenance import (
    PROVENANCE_AUTHORITATIVE,
    DepCandidate,
    DepProposer,
    DepScout,
    Source,
)
from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.ssrf_bridge import SSRFBridge, BridgeDecision


@pytest.fixture
def merkle(tmp_path: Path) -> MerkleLogger:
    return MerkleLogger(tmp_path / "merkle")


def _pypi_body(version: str) -> str:
    return json.dumps({"info": {"name": "pkg", "version": version}})


class TestDepScout:
    def test_discovers_outdated_only(self, merkle) -> None:
        # click tiene bump (8.1 → 8.2), rich está al día (13.0 → 13.0).
        bodies = {
            "https://pypi.org/pypi/click/json": _pypi_body("8.2.0"),
            "https://pypi.org/pypi/rich/json": _pypi_body("13.0.0"),
        }
        scout = DepScout(
            merkle=merkle,
            bridge=SSRFBridge(),
            fetch=lambda u: bodies[u],
            deps_provider=lambda: [("click", "8.1"), ("rich", "13.0.0")],
        )
        cands = scout.discover()
        assert [(c.name, c.latest) for c in cands] == [("click", "8.2.0")]
        assert cands[0].source.provenance == PROVENANCE_AUTHORITATIVE

    def test_prerelease_skipped(self, merkle) -> None:
        scout = DepScout(
            merkle=merkle,
            bridge=SSRFBridge(),
            fetch=lambda u: _pypi_body("9.0.0rc1"),
            deps_provider=lambda: [("click", "8.1")],
        )
        assert scout.discover() == []

    def test_egress_denied_skips_dep(self, merkle) -> None:
        called: list[str] = []

        class _Deny(SSRFBridge):
            def check(self, url: str) -> BridgeDecision:  # type: ignore[override]
                return BridgeDecision(allowed=False, url=url, reason="x", domain="")

        scout = DepScout(
            merkle=merkle,
            bridge=_Deny(),
            fetch=lambda u: called.append(u) or _pypi_body("9.0"),
            deps_provider=lambda: [("click", "8.1")],
        )
        assert scout.discover() == []
        assert called == []

    def test_fetch_failure_fail_closed(self, merkle) -> None:
        def _boom(u: str) -> str:
            raise ConnectionError("down")

        scout = DepScout(
            merkle=merkle, bridge=SSRFBridge(), fetch=_boom,
            deps_provider=lambda: [("click", "8.1")],
        )
        assert scout.discover() == []

    def test_malformed_version_fail_closed(self, merkle) -> None:
        scout = DepScout(
            merkle=merkle, bridge=SSRFBridge(),
            fetch=lambda u: json.dumps({"info": {"version": "not-a-version"}}),
            deps_provider=lambda: [("click", "8.1")],
        )
        assert scout.discover() == []


_PYPROJECT = """\
[project]
name = "demo"
dependencies = [
    "click>=8.1",
    "uvicorn[standard]>=0.29",
]
"""


def _candidate(name: str, current: str, latest: str) -> DepCandidate:
    return DepCandidate(
        name=name, current=current, latest=latest,
        source=Source(PROVENANCE_AUTHORITATIVE, f"https://pypi.org/pypi/{name}/json", ""),
    )


class TestDepProposer:
    def test_builds_patch_and_delegates(self, merkle, tmp_path) -> None:
        pp = tmp_path / "pyproject.toml"
        pp.write_text(_PYPROJECT, encoding="utf-8")
        seen: dict[str, Any] = {}

        class _Prop:
            id = "cold-0001"

        def _propose(intent, patch_path, **kw):
            seen["intent"] = intent
            seen["patch"] = Path(patch_path).read_text(encoding="utf-8")
            seen["kw"] = kw
            return _Prop()

        proposal = DepProposer(
            merkle=merkle, propose=_propose, pyproject_path=pp,
            installed_version=lambda _n: "8.2.0",
        ).propose_bump(_candidate("click", "8.1", "8.2.0"))

        assert proposal.id == "cold-0001"
        assert seen["kw"]["origin"] == "self_audit"
        assert seen["kw"]["risk"] == "low"
        patch = seen["patch"]
        assert patch.startswith("--- a/pyproject.toml")
        assert "+++ b/pyproject.toml" in patch
        assert '-    "click>=8.1",' in patch
        assert '+    "click>=8.2.0",' in patch
        # No tocó la otra dep.
        assert "uvicorn" not in patch.replace("uvicorn[standard]>=0.29", "")

    def test_handles_extras(self, merkle, tmp_path) -> None:
        pp = tmp_path / "pyproject.toml"
        pp.write_text(_PYPROJECT, encoding="utf-8")
        captured: dict[str, str] = {}

        def _propose(intent, patch_path, **kw):
            captured["patch"] = Path(patch_path).read_text(encoding="utf-8")
            return type("P", (), {"id": "x"})()

        DepProposer(
            merkle=merkle, propose=_propose, pyproject_path=pp,
            installed_version=lambda _n: "0.30.1",
        ).propose_bump(_candidate("uvicorn", "0.29", "0.30.1"))
        assert '+    "uvicorn[standard]>=0.30.1",' in captured["patch"]

    def test_floor_never_exceeds_installed(self, merkle, tmp_path) -> None:
        """Regresión: si ``latest`` supera lo instalado, el piso se ancla a lo
        instalado — nunca se propone ``>=latest`` por encima de la realidad
        (backlog: dep-bump autónomo crea deriva floor>instalado)."""
        pp = tmp_path / "pyproject.toml"
        pp.write_text(_PYPROJECT, encoding="utf-8")
        captured: dict[str, Any] = {}

        def _propose(intent, patch_path, **kw):
            captured["patch"] = Path(patch_path).read_text(encoding="utf-8")
            captured["kw"] = kw
            return type("P", (), {"id": "x"})()

        # latest 8.4.1 publicado en PyPI, pero el entorno solo tiene 8.2.0.
        DepProposer(
            merkle=merkle, propose=_propose, pyproject_path=pp,
            installed_version=lambda _n: "8.2.0",
        ).propose_bump(_candidate("click", "8.1", "8.4.1"))

        assert '+    "click>=8.2.0",' in captured["patch"]
        assert "8.4.1" not in captured["patch"]  # nunca por encima de lo instalado
        assert captured["kw"]["evidence"]["to"] == "8.2.0"
        assert captured["kw"]["evidence"]["latest"] == "8.4.1"

    def test_not_installed_fail_closed(self, merkle, tmp_path) -> None:
        """Si la dep no está instalada no se puede anclar el piso → no se propone."""
        pp = tmp_path / "pyproject.toml"
        pp.write_text(_PYPROJECT, encoding="utf-8")
        called: list[Any] = []

        result = DepProposer(
            merkle=merkle, propose=lambda *a, **k: called.append(a),
            pyproject_path=pp, installed_version=lambda _n: None,
        ).propose_bump(_candidate("click", "8.1", "8.2.0"))

        assert result is None
        assert called == []

    def test_no_target_fail_closed(self, merkle, tmp_path) -> None:
        pp = tmp_path / "pyproject.toml"
        pp.write_text(_PYPROJECT, encoding="utf-8")
        called: list[Any] = []

        result = DepProposer(
            merkle=merkle, propose=lambda *a, **k: called.append(a),
            pyproject_path=pp, installed_version=lambda _n: "2.0",
        ).propose_bump(_candidate("nonexistent", "1.0", "2.0"))

        assert result is None
        assert called == []  # no se entrega nada a ColdUpdate

    def test_unreadable_pyproject_fail_closed(self, merkle, tmp_path) -> None:
        result = DepProposer(
            merkle=merkle, propose=lambda *a, **k: 1 / 0,
            pyproject_path=tmp_path / "missing.toml",
            installed_version=lambda _n: "8.2",
        ).propose_bump(_candidate("click", "8.1", "8.2"))
        assert result is None
