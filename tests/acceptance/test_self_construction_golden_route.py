"""Test E2E de la RUTA DORADA de autoconstrucción — DELIBERADAMENTE ROJO.

Este test describe el producto interno de Atlas (Foundry v0, ADR-069; brief
"Self-Construction Rescue Session v0.2" del export Diseño UI Atlas L45472):

    Usuario pide una mejora concreta de Atlas por una superficie PÚBLICA
    → Atlas verifica el repo real → propone plan mínimo → worktree aislado
    → cambio acotado → tests/mypy → diff visible + riesgo + evidencia
    → APROBACIÓN HUMANA obligatoria → aplica o aparca (reversible)
    → actualiza ledger/memoria/grafo/auditoría → receipt verificable.

Está marcado xfail(strict=True) mientras la ruta no exista: NO es un test
aspiracional decorativo — es el contrato de qué falta, en código. Cuando la
ruta se cierre de verdad, el xfail saltará como XPASS(strict) y OBLIGARÁ a
quitar el marcador (momento de celebrarlo, no de silenciarlo).

Reglas que el test codifica (deben seguir siendo ciertas cuando se cierre):
  * jamás llamar clases internas directamente (solo superficie pública),
  * jamás editar el árbol principal antes de aprobación,
  * jamás aplicar sin aprobación humana registrada,
  * siempre diff visible + tests observables + receipt,
  * jamás tocar rutas protegidas (config/governance.json),
  * jamás push ni efectos externos.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.xfail(
    reason=(
        "La ruta dorada de autoconstrucción no está cerrada todavía "
        "(Foundry v0 en construcción, ADR-069): existe la proyección "
        "read-only (/missions) pero no la superficie pública de petición "
        "→ plan → worktree → diff → aprobación → apply/park → receipt."
    ),
    strict=True,
)


def test_self_build_golden_route_requires_approval_and_receipt() -> None:
    # Superficie pública de petición: aún no existe. Cuando exista debe ser
    # un módulo importable sin efectos laterales (contrato, no clase interna).
    from atlas.missions.golden_route import GoldenRoute  # noqa: F401

    route = GoldenRoute()
    session = route.request(
        "añade una línea al final de docs/demo/GOLDEN_ROUTE_DEMO.md",
    )

    # plan mínimo antes de tocar nada
    assert session.plan is not None
    assert session.state == "plan_proposed"

    # worktree aislado, jamás el árbol principal
    assert session.worktree_path is not None
    assert "atlas-core" not in str(session.worktree_path)

    # cambio acotado + validación observable
    session.execute()
    assert session.diff  # diff visible o no cuenta
    assert session.validation["pytest_exit"] is not None

    # SIN aprobación no hay apply — debe negarse, no aplicar en silencio
    with pytest.raises(PermissionError):
        session.apply()

    # aprobación humana registrada → apply o park reversible
    session.approve(actor="operator", decision="approve")
    result = session.apply()
    assert result.receipt["verifiable"] is True
    assert result.receipt["decision_needed"].startswith("Ninguna")
    assert result.audit_ref  # Merkle o no ocurrió
