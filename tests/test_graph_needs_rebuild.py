"""El tick del grafo dejaba de curarse si la corrupción no movía el HEAD.

`maintenance_project_graph_tick` cortaba con `if state["last_head"] == head:
return up_to_date`. El fichero de estado dice lo que pasó la última vez; la BD
dice lo que hay ahora. Confiar sólo en el primero convierte una corrupción en
permanente.

Es exactamente el agujero que dejó el incidente del 2026-08-08: el catálogo
perdió FileVersion/Module/IMPORTS por dos escritores concurrentes, y el HEAD no
cambió. Con esa lógica el tick habría contestado "al día" indefinidamente sobre
una BD inservible.

Se salvó de puro azar: siguieron llegando commits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atlas.core.orchestrator_parts.maintenance_facade import graph_needs_rebuild


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "project_graph.kuzu"


def _freshness(monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    def fake(*_: Any, **__: Any) -> dict[str, Any]:
        return {"status": status, "reason": "fixture"}

    monkeypatch.setattr("atlas.memory.project_graph.graph_freshness", fake)


# --------------------------------------------------------------------------
# Motivo 1: el HEAD avanzó
# --------------------------------------------------------------------------


def test_head_distinto_siempre_reconstruye(db: Path, tmp_path: Path) -> None:
    assert graph_needs_rebuild({"last_head": "viejo"}, "nuevo", db, tmp_path) is True


def test_sin_estado_previo_reconstruye(db: Path, tmp_path: Path) -> None:
    assert graph_needs_rebuild({}, "abc", db, tmp_path) is True


# --------------------------------------------------------------------------
# Motivo 2: el HEAD coincide pero la BD no sirve — el que faltaba
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["EMPTY", "UNAVAILABLE", "NO_DB"])
def test_bd_inservible_reconstruye_aunque_coincida_el_head(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    """El caso del incidente: catálogo roto, HEAD intacto."""
    _freshness(monkeypatch, status)

    assert graph_needs_rebuild({"last_head": "abc"}, "abc", db, tmp_path) is True


@pytest.mark.parametrize("status", ["FRESH", "DIRTY", "STALE", "SERVER_STALE"])
def test_bd_sana_con_head_igual_no_reconstruye(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    """El corte barato sigue vivo: regenerar el grafo cuesta minutos y no puede
    dispararse en cada tick por si acaso."""
    _freshness(monkeypatch, status)

    assert graph_needs_rebuild({"last_head": "abc"}, "abc", db, tmp_path) is False


def test_un_estado_desconocido_no_dispara_reconstruccion(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Vocabulario nuevo en `graph_freshness` no debe convertir el tick en un
    bucle de reconstrucción: sólo los estados que significan "no sirve"."""
    _freshness(monkeypatch, "UNKNOWN")

    assert graph_needs_rebuild({"last_head": "abc"}, "abc", db, tmp_path) is False


def test_no_consulta_la_bd_si_el_head_ya_difiere(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corte barato: con el HEAD movido la respuesta ya está decidida y abrir
    Kuzu para confirmarlo sería pagar de más."""
    llamadas: list[int] = []

    def fake(*_: Any, **__: Any) -> dict[str, Any]:
        llamadas.append(1)
        return {"status": "FRESH"}

    monkeypatch.setattr("atlas.memory.project_graph.graph_freshness", fake)

    graph_needs_rebuild({"last_head": "viejo"}, "nuevo", db, tmp_path)

    assert llamadas == []


def test_contra_una_bd_real_inexistente(db: Path, tmp_path: Path) -> None:
    """Sin mocks: una BD que no existe es NO_DB y debe reconstruir."""
    assert graph_needs_rebuild({"last_head": "abc"}, "abc", db, tmp_path) is True
