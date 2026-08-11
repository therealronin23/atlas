"""ADC-WO-109: el E2E `change → finding → proposal → approval → receipt`.

Uno de los cuatro tests que la ficha de Cut 2 nombra y el único que
demuestra el producto entero en vez de una costura. Los otros tres:
`bridge version negotiation` y `backend-loss degradation` viven en
`tests/test_coding_bridge_negotiation.py`; `upstream reproducible build` es
del checkout de CodeOSS, no de aquí.

Qué distingue esto del E2E que YA existía. `test_self_construction_golden_
route.py` recorre la ruta dorada, que empieza en una PETICIÓN del usuario.
Ésta empieza en un CAMBIO en el repo y la detección es de Atlas, no del
usuario: es el lazo autónomo, no el asistido. Comparten el final —recibo
Merkle— y nada más.

Lo que aquí es real y no está doblado: el repo git, el `git status` que
produce el hallazgo, el patch (generado con `git diff` de verdad), el
worktree aislado, el sha256 del patch, el ledger Merkle encadenado y su
verificación. Lo único inyectado es el runner de validación, que ejecuta un
subproceso real barato en vez de la suite completa — igual que la ruta
dorada, y por el mismo motivo: la validación real ya la cubre
`tests/test_cold_update_manager.py`, y meterla aquí convertiría un E2E de 2
segundos en uno de 10 minutos que nadie correría.

Las tres cosas que este test impide que se rompan en silencio:

1. El hallazgo sale del ESTADO REAL del repo, no de una lista escrita a mano.
2. `approve()` es una PUERTA: sin validación previa, revienta. Un E2E que
   sólo recorriera el camino feliz no distinguiría una puerta de un adorno.
3. El recibo es la CADENA, no una línea suelta: el ledger tiene la traza
   completa y en orden, y `verify_chain()` la valida.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from atlas.core.cold_update_manager import ColdUpdateManager, PatchIntakeError
from atlas.core.self_audit import SelfAuditRunner
from atlas.core.validation_runner import ValidationReport
from atlas.logging.merkle_logger import MerkleLogger


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Repo git real, limpio y con la forma que ColdUpdate exige (`docs/`
    está en la allowlist de rutas; un patch fuera de ella se rechaza)."""
    root = tmp_path / "producto"
    (root / "docs").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / "docs" / "manual.md").write_text(
        "# Manual\n\nEl puerto del bridge es 7341.\n", encoding="utf-8"
    )
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "e2e@atlas.local")
    _git(root, "config", "user.name", "atlas-e2e")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    return root


class _RunnerReal:
    """Subproceso de verdad con código de salida de verdad, barato."""

    resultado = 0

    def __init__(self, path: Path) -> None:
        self._path = path

    def run(self, timeout_s: int = 600) -> ValidationReport:
        code = subprocess.run(
            [sys.executable, "-c", f"raise SystemExit({_RunnerReal.resultado})"],
            cwd=self._path,
        ).returncode
        return ValidationReport(
            passed=code == 0,
            pytest_exit=code,
            mypy_exit=code,
            pytest_summary="subproceso real del E2E",
            mypy_summary="subproceso real del E2E",
        )


def _acciones(merkle: MerkleLogger) -> list[str]:
    """`read_all()` devuelve `AuditRecord`, no dicts."""
    return [registro.action for registro in merkle.read_all()]


def _patch_de(repo: Path, fichero: str, contenido: str) -> Path:
    """Un patch git REAL: se escribe el cambio, se saca el `git diff` y se
    revierte el árbol. Escribir el diff a mano dejaría de probar el intake."""
    destino = repo / fichero
    original = destino.read_text(encoding="utf-8")
    destino.write_text(contenido, encoding="utf-8")
    diff = _git(repo, "diff")
    destino.write_text(original, encoding="utf-8")
    ruta = repo.parent / "cambio.patch"
    ruta.write_text(diff, encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# El recorrido completo
# ---------------------------------------------------------------------------


def test_de_un_cambio_en_el_repo_a_un_recibo_verificable(
    repo: Path, tmp_path: Path
) -> None:
    merkle = MerkleLogger(tmp_path / "audit")
    _RunnerReal.resultado = 0

    # --- 1. CAMBIO -------------------------------------------------------
    # Un fichero rastreado se modifica. Nadie se lo cuenta a Atlas.
    (repo / "docs" / "manual.md").write_text(
        "# Manual\n\nEl puerto del bridge es 7341.\nlinea suelta\n",
        encoding="utf-8",
    )
    assert _git(repo, "status", "--short").strip(), "el cambio no existe"

    # --- 2. HALLAZGO -----------------------------------------------------
    # El self-audit mira el repo REAL y lo encuentra solo.
    auditor = SelfAuditRunner(repo, merkle, docs_dir=tmp_path / "informes")
    ciclo = auditor.run_cycle(index=1)

    hallazgos = {f.id: f for f in ciclo.findings}
    assert "repo-dirty-tracked" in hallazgos, [f.id for f in ciclo.findings]
    assert hallazgos["repo-dirty-tracked"].severity == "high"
    # Y el hallazgo produce candidato: un hallazgo sin candidato es una queja.
    assert any(c.id == "candidate-repo-dirty-tracked" for c in ciclo.candidates)

    # El repo vuelve a estar limpio antes de proponer nada: el patch se aplica
    # sobre un árbol conocido, no sobre uno a medias.
    _git(repo, "checkout", "--", "docs/manual.md")

    # --- 3. PROPUESTA ----------------------------------------------------
    patch = _patch_de(
        repo, "docs/manual.md",
        "# Manual\n\nEl puerto del bridge es 7342.\n",
    )
    gestor = ColdUpdateManager(
        repo, merkle,
        store_dir=tmp_path / "updates",
        runner_factory=_RunnerReal,
    )
    propuesta = gestor.propose(
        "corrige el puerto del bridge en el manual",
        patch,
        origin="self_audit",
        risk="low",
        evidence={"finding": "repo-dirty-tracked", "cycle": ciclo.index},
    )

    assert propuesta.status == "proposed"
    assert propuesta.patch_sha256, "sin huella no hay integridad que comprobar"
    # El árbol principal NO se ha tocado: el cambio vive en un worktree aparte.
    assert "7341" in (repo / "docs" / "manual.md").read_text(encoding="utf-8")
    assert Path(propuesta.worktree_path).is_dir()
    assert "7342" in (
        Path(propuesta.worktree_path) / "docs" / "manual.md"
    ).read_text(encoding="utf-8")

    # --- 4. APROBACIÓN ---------------------------------------------------
    # La puerta, PRIMERO. Sin esta comprobación el resto del test no
    # distinguiría una puerta de un adorno.
    with pytest.raises(RuntimeError, match="Requiere validacion previa"):
        gestor.approve(propuesta.id)

    informe = gestor.validate(propuesta.id)
    assert informe.passed
    assert gestor.get(propuesta.id).status == "validated"  # type: ignore[union-attr]

    aprobada = gestor.approve(propuesta.id)
    assert aprobada.status == "approved"

    # --- 5. RECIBO -------------------------------------------------------
    resultado = gestor.apply(propuesta.id)
    assert resultado["status"] == "applied"
    # El cambio está en el árbol principal, y lo commiteó el motor.
    assert "7342" in (repo / "docs" / "manual.md").read_text(encoding="utf-8")
    assert not _git(repo, "status", "--short").strip(), "quedó trabajo sin commitear"
    assert propuesta.id in _git(repo, "log", "-1", "--format=%B")

    # El recibo es la CADENA entera, en orden, no una línea suelta.
    acciones = _acciones(merkle)
    esperadas = [
        "self_audit.cycle",
        "cold_update.proposed",
        "cold_update.validated",
        "cold_update.approved",
        "cold_update.applied",
    ]
    posiciones = [acciones.index(a) for a in esperadas]
    assert posiciones == sorted(posiciones), list(zip(esperadas, posiciones))
    assert merkle.verify_chain()[0] is True, merkle.verify_chain()[1]


# ---------------------------------------------------------------------------
# Las tres formas de romperlo
# ---------------------------------------------------------------------------


def test_una_validacion_fallida_no_llega_a_aprobarse(
    repo: Path, tmp_path: Path
) -> None:
    merkle = MerkleLogger(tmp_path / "audit")
    _RunnerReal.resultado = 1
    try:
        gestor = ColdUpdateManager(
            repo, merkle,
            store_dir=tmp_path / "updates",
            runner_factory=_RunnerReal,
        )
        propuesta = gestor.propose(
            "cambio que no valida",
            _patch_de(repo, "docs/manual.md", "# Manual\n\nroto\n"),
            origin="self_audit",
        )
        informe = gestor.validate(propuesta.id)

        assert not informe.passed
        assert gestor.get(propuesta.id).status == "failed"  # type: ignore[union-attr]
        with pytest.raises(RuntimeError):
            gestor.approve(propuesta.id)
        # El árbol principal sigue intacto.
        assert "7341" in (repo / "docs" / "manual.md").read_text(encoding="utf-8")
    finally:
        _RunnerReal.resultado = 0


def test_manipular_el_patch_tras_aprobarlo_impide_aplicarlo(
    repo: Path, tmp_path: Path
) -> None:
    """Aprobar es aprobar UN patch concreto, no un identificador. Sin esto,
    el hueco entre aprobación y aplicación sería un sitio donde cambiar lo
    que el humano ya dijo que sí."""
    merkle = MerkleLogger(tmp_path / "audit")
    _RunnerReal.resultado = 0
    gestor = ColdUpdateManager(
        repo, merkle,
        store_dir=tmp_path / "updates",
        runner_factory=_RunnerReal,
    )
    propuesta = gestor.propose(
        "cambio honesto",
        _patch_de(repo, "docs/manual.md", "# Manual\n\nEl puerto es 7342.\n"),
        origin="self_audit",
    )
    gestor.validate(propuesta.id)
    gestor.approve(propuesta.id)

    almacenado = Path(propuesta.patch_path)
    almacenado.write_text(
        almacenado.read_text(encoding="utf-8").replace("7342", "6666"),
        encoding="utf-8",
    )

    with pytest.raises(PatchIntakeError, match="digest"):
        gestor.apply(propuesta.id)
    assert "7341" in (repo / "docs" / "manual.md").read_text(encoding="utf-8")
    assert "6666" not in (repo / "docs" / "manual.md").read_text(encoding="utf-8")


def test_un_patch_fuera_de_la_allowlist_no_llega_ni_a_propuesta(
    repo: Path, tmp_path: Path
) -> None:
    """La allowlist es fail-closed y actúa ANTES de crear el worktree: un
    rechazo que dejara worktrees por el suelo sería un rechazo caro."""
    merkle = MerkleLogger(tmp_path / "audit")
    (repo / "veneno.txt").write_text("no\n", encoding="utf-8")
    _git(repo, "add", "veneno.txt")
    _git(repo, "commit", "-m", "fuera de docs")
    patch = _patch_de(repo, "veneno.txt", "si\n")

    store = tmp_path / "updates"
    gestor = ColdUpdateManager(
        repo, merkle, store_dir=store, runner_factory=_RunnerReal,
    )
    with pytest.raises(Exception, match="allowlist"):
        gestor.propose("tocar la raíz", patch, origin="self_audit")

    assert not list(store.glob("worktree-*")), "se creó un worktree para nada"


def test_el_recibo_no_sobrevive_a_que_alguien_toque_el_ledger(
    repo: Path, tmp_path: Path
) -> None:
    """El último eslabón: si el recibo se pudiera editar, todo lo anterior
    sería decorativo. Se corrompe una entrada a mano y la cadena lo dice."""
    merkle = MerkleLogger(tmp_path / "audit")
    gestor = ColdUpdateManager(
        repo, merkle, store_dir=tmp_path / "updates", runner_factory=_RunnerReal,
    )
    propuesta = gestor.propose(
        "cambio con recibo",
        _patch_de(repo, "docs/manual.md", "# Manual\n\nEl puerto es 7342.\n"),
        origin="self_audit",
    )
    gestor.validate(propuesta.id)
    gestor.approve(propuesta.id)
    assert merkle.verify_chain()[0] is True, merkle.verify_chain()[1]

    ficheros = sorted(p for p in (tmp_path / "audit").rglob("*") if p.is_file())
    objetivo = next(p for p in ficheros if p.stat().st_size > 0)
    lineas = objetivo.read_text(encoding="utf-8").splitlines()
    assert len(lineas) >= 2
    lineas[1] = lineas[1].replace('"success"', '"failure"', 1)
    objetivo.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    valida, motivo = merkle.verify_chain()
    assert valida is False
    assert "Record #2" in motivo, motivo
