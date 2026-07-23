"""Test E2E de la RUTA DORADA de autoconstrucción (Foundry v0, ADR-069).

Describe el producto interno de Atlas (brief "Self-Construction Rescue
Session v0.2" del export Diseño UI Atlas L45472):

    Usuario pide una mejora concreta de Atlas por una superficie PÚBLICA
    → Atlas propone plan mínimo → worktree aislado → cambio acotado
    → validación observable → diff visible + riesgo + evidencia
    → APROBACIÓN HUMANA obligatoria → aplica (commit del motor) o aparca
    → receipt verificable + audit ref Merkle.

Corre sobre un repo fixture (como exige el brief: "a clean test repo or
fixture repo, a tiny documentation-only requested change") con un runner de
validación inyectado que ejecuta subprocesos REALES baratos — la validación
pytest/mypy real del motor ya está cubierta por tests/test_cold_update_manager.py
y no se re-testea aquí.

Reglas que el test codifica:
  * jamás llamar clases internas del motor directamente (solo GoldenRoute),
  * jamás editar el árbol principal antes de aprobación,
  * jamás aplicar sin aprobación humana registrada (PermissionError),
  * siempre diff visible + validación observable + receipt,
  * el apply lo commitea el MOTOR con evidencia (nunca push).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from atlas.core.validation_runner import ValidationReport


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    """Repo git mínimo con el doc de demo commiteado."""
    repo = tmp_path / "demo-repo"
    (repo / "docs" / "demo").mkdir(parents=True)
    (repo / "docs" / "demo" / "GOLDEN_ROUTE_DEMO.md").write_text(
        "# Golden Route Demo\n\nLínea base.\n", encoding="utf-8"
    )
    (repo / "docs" / "demo" / "EMPTY.md").write_text("", encoding="utf-8")
    (repo / "src" / "demo_pkg").mkdir(parents=True)
    (repo / "src" / "demo_pkg" / "helper.py").write_text(
        "def old_helper() -> int:\n"
        "    return 1\n"
        "\n"
        "\n"
        "def caller() -> int:\n"
        "    return old_helper()\n",
        encoding="utf-8",
    )
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "test@atlas.local")
    _run_git(repo, "config", "user.name", "atlas-test")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "base")
    return repo


class _SubprocessRunner:
    """Checks reales baratos: subprocesos de verdad, exit codes de verdad."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def run(self, timeout_s: int = 600) -> ValidationReport:
        code = subprocess.run(
            [sys.executable, "-c", "raise SystemExit(0)"], cwd=self._path
        ).returncode
        return ValidationReport(
            passed=code == 0,
            pytest_exit=code,
            mypy_exit=code,
            pytest_summary="fixture subprocess check",
            mypy_summary="fixture subprocess check",
        )


def test_self_build_golden_route_requires_approval_and_receipt(
    fixture_repo: Path, tmp_path: Path
) -> None:
    from atlas.missions.golden_route import GoldenRoute

    route = GoldenRoute.for_repo(
        fixture_repo,
        store_dir=tmp_path / "updates",
        audit_dir=tmp_path / "audit",
        runner_factory=_SubprocessRunner,
    )
    session = route.request(
        "añade una línea al final de docs/demo/GOLDEN_ROUTE_DEMO.md"
    )

    # plan mínimo antes de tocar nada
    assert session.plan is not None
    assert session.plan["path"] == "docs/demo/GOLDEN_ROUTE_DEMO.md"
    assert session.state == "plan_proposed"

    # worktree aislado, jamás el árbol principal
    assert session.worktree_path is not None
    assert not str(session.worktree_path).startswith(str(fixture_repo))
    main_doc = (fixture_repo / "docs" / "demo" / "GOLDEN_ROUTE_DEMO.md").read_text(
        encoding="utf-8"
    )
    assert main_doc == "# Golden Route Demo\n\nLínea base.\n"  # intacto

    # cambio acotado + validación observable
    session.execute()
    assert session.state == "awaiting_human_approval"
    assert session.diff and "GOLDEN_ROUTE_DEMO.md" in session.diff
    assert session.validation is not None
    assert session.validation["pytest_exit"] is not None

    # SIN aprobación no hay apply — debe negarse, no aplicar en silencio
    with pytest.raises(PermissionError):
        session.apply()
    # y el árbol principal sigue intacto tras el intento
    assert (fixture_repo / "docs" / "demo" / "GOLDEN_ROUTE_DEMO.md").read_text(
        encoding="utf-8"
    ) == "# Golden Route Demo\n\nLínea base.\n"

    # aprobación humana registrada → apply
    session.approve(actor="operator", decision="approve")
    assert session.state == "approved_pending_apply"
    result = session.apply()

    # el cambio llegó al árbol principal y el MOTOR lo commiteó
    final_doc = (fixture_repo / "docs" / "demo" / "GOLDEN_ROUTE_DEMO.md").read_text(
        encoding="utf-8"
    )
    assert final_doc.startswith("# Golden Route Demo\n\nLínea base.\n")
    assert len(final_doc) > len(main_doc)  # la línea nueva está
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=fixture_repo,
        capture_output=True, text=True, check=True,
    ).stdout
    assert len(log.strip().splitlines()) == 2  # base + commit del motor

    # receipt verificable + auditoría Merkle
    assert result.receipt["verifiable"] is True
    assert result.receipt["decision_needed"].startswith("Ninguna")
    assert result.receipt["mission_id"] == f"msn_{result.proposal_id}"
    assert result.audit_ref  # hash_self del registro Merkle
    assert session.state == "applied"


def test_golden_route_reject_parks_without_touching_main(
    fixture_repo: Path, tmp_path: Path
) -> None:
    from atlas.missions.golden_route import GoldenRoute

    route = GoldenRoute.for_repo(
        fixture_repo,
        store_dir=tmp_path / "updates",
        audit_dir=tmp_path / "audit",
        runner_factory=_SubprocessRunner,
    )
    session = route.request(
        'añade la línea "No debería llegar a main" al final de '
        "docs/demo/GOLDEN_ROUTE_DEMO.md"
    )
    session.execute()
    session.approve(actor="operator", decision="reject")
    assert session.state == "rejected"

    with pytest.raises(PermissionError):
        session.apply()
    assert (fixture_repo / "docs" / "demo" / "GOLDEN_ROUTE_DEMO.md").read_text(
        encoding="utf-8"
    ) == "# Golden Route Demo\n\nLínea base.\n"


def test_golden_route_appends_to_empty_doc_end_to_end(
    fixture_repo: Path, tmp_path: Path
) -> None:
    """Caso borde real (revisión Sonnet): un .md recién creado de 0 bytes."""
    from atlas.missions.golden_route import GoldenRoute

    route = GoldenRoute.for_repo(
        fixture_repo,
        store_dir=tmp_path / "updates",
        audit_dir=tmp_path / "audit",
        runner_factory=_SubprocessRunner,
    )
    session = route.request(
        'añade la línea "Primera" al final de docs/demo/EMPTY.md'
    )
    session.execute()
    session.approve(actor="operator", decision="approve")
    result = session.apply()
    assert result.receipt["verifiable"] is True
    assert (fixture_repo / "docs" / "demo" / "EMPTY.md").read_text(
        encoding="utf-8"
    ) == "Primera\n"


def test_golden_route_renames_identifier_end_to_end(
    fixture_repo: Path, tmp_path: Path
) -> None:
    """Segundo patrón del vocabulario (T1.1): 'renombra X a Y en <fichero>'
    produce un cambio de código acotado (no documentation-only), recorriendo
    la MISMA ceremonia completa: plan→worktree→diff→aprobación→apply→receipt."""
    from atlas.missions.golden_route import GoldenRoute

    route = GoldenRoute.for_repo(
        fixture_repo,
        store_dir=tmp_path / "updates",
        audit_dir=tmp_path / "audit",
        runner_factory=_SubprocessRunner,
    )
    session = route.request("renombra old_helper a new_helper en src/demo_pkg/helper.py")

    # plan mínimo antes de tocar nada
    assert session.plan["action"] == "rename_identifier"
    assert session.plan["path"] == "src/demo_pkg/helper.py"
    assert session.state == "plan_proposed"

    # worktree aislado, jamás el árbol principal
    assert session.worktree_path is not None
    assert not str(session.worktree_path).startswith(str(fixture_repo))
    main_file = (fixture_repo / "src" / "demo_pkg" / "helper.py").read_text(
        encoding="utf-8"
    )
    assert "old_helper" in main_file  # intacto

    # cambio acotado + validación observable
    session.execute()
    assert session.state == "awaiting_human_approval"
    assert session.diff and "helper.py" in session.diff
    assert "-def old_helper" in session.diff
    assert "+def new_helper" in session.diff
    assert session.validation is not None
    assert session.validation["pytest_exit"] is not None

    # SIN aprobación no hay apply
    with pytest.raises(PermissionError):
        session.apply()
    assert (fixture_repo / "src" / "demo_pkg" / "helper.py").read_text(
        encoding="utf-8"
    ) == main_file

    # aprobación humana registrada → apply
    session.approve(actor="operator", decision="approve")
    assert session.state == "approved_pending_apply"
    result = session.apply()

    # el cambio llegó al árbol principal, con AMBAS ocurrencias renombradas
    final_file = (fixture_repo / "src" / "demo_pkg" / "helper.py").read_text(
        encoding="utf-8"
    )
    assert "old_helper" not in final_file
    assert final_file.count("new_helper") == 2  # definición + llamada

    # el MOTOR lo commiteó (no nosotros)
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=fixture_repo,
        capture_output=True, text=True, check=True,
    ).stdout
    assert len(log.strip().splitlines()) == 2  # base + commit del motor

    # receipt verificable + auditoría Merkle
    assert result.receipt["verifiable"] is True
    assert result.audit_ref
    assert session.state == "applied"


def test_golden_route_out_of_order_approve_does_not_mark_decision(
    fixture_repo: Path, tmp_path: Path
) -> None:
    """approve() antes de execute(): el motor rechaza la transición y la
    sesión NO debe quedar marcada como decidida — apply() sigue exigiendo
    aprobación con PermissionError (no el RuntimeError genérico)."""
    from atlas.missions.golden_route import GoldenRoute

    route = GoldenRoute.for_repo(
        fixture_repo,
        store_dir=tmp_path / "updates",
        audit_dir=tmp_path / "audit",
        runner_factory=_SubprocessRunner,
    )
    session = route.request(
        "añade una línea al final de docs/demo/GOLDEN_ROUTE_DEMO.md"
    )
    with pytest.raises(RuntimeError):
        session.approve(actor="operator", decision="approve")
    with pytest.raises(PermissionError):
        session.apply()


def test_golden_route_refuses_symlink_under_docs(
    fixture_repo: Path, tmp_path: Path
) -> None:
    """Defensa explícita, no accidente de git apply/patch."""
    from atlas.missions.golden_route import GoldenRoute, UnsupportedRequestError

    secret = tmp_path / "secret.txt"
    secret.write_text("fuera del repo\n", encoding="utf-8")
    (fixture_repo / "docs" / "evil.md").symlink_to(secret)
    route = GoldenRoute.for_repo(
        fixture_repo,
        store_dir=tmp_path / "updates",
        audit_dir=tmp_path / "audit",
        runner_factory=_SubprocessRunner,
    )
    with pytest.raises(UnsupportedRequestError, match="symlink"):
        route.request("añade una línea al final de docs/evil.md")
