"""Con el lazo pausado, ningún tick puede seguir gastando inferencia.

Medido el 2026-08-09. El lazo estaba pausado desde el día 6 y el daemon seguía
haciendo, en dos días, 128 `analyst_analyze` y 72 `panorama_scout_discover`:
deliberación cuyo consumidor no existía. La causa era exacta — `is_paused()` se
consultaba en **un solo sitio**, el tick de self_build.

El criterio del gate es "consume inferencia", NO una lista de nombres. Un tick
sin LLM es gratis y da observabilidad justo cuando el lazo está parado (grafo,
higiene de cuarentena, watchdog): esos siguen.

**Este fichero es el mecanismo, no la lista.** `PAUSED_LLM_TICKS` documenta;
quien impide que envejezca es el test que recorre los ticks REALES y falla si
aparece uno con inferencia y sin guardia. Es la lección de la semana aplicada:
una regla que sólo vive en prosa se rompe — dos veces en esta misma sesión.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from atlas.core.self_maintenance.self_build_pause import (
    PAUSED_LLM_TICKS,
    is_paused,
    llm_spend_paused,
    pause,
    resume,
)

FACADE = (
    Path(__file__).resolve().parent.parent
    / "src" / "atlas" / "core" / "orchestrator_parts" / "maintenance_facade.py"
)

#: Módulos de self_maintenance que hacen llamadas de inferencia. Derivado
#: midiendo, no a mano: son los que importan InferenceRequest o llaman a
#: `hub.infer`.
_MODULOS_CON_LLM = (
    "topic_expander",
    "batch_premortem",
    "model_catalog_drift",
    "mcp_discovery_quality_gate",
    "analyst",
)


def _ticks() -> dict[str, str]:
    """Nombre de tick -> su código fuente."""
    source = FACADE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("maintenance_"):
            out[node.name] = ast.get_source_segment(source, node) or ""
    return out


# --------------------------------------------------------------------------
# El semáforo
# --------------------------------------------------------------------------


def test_la_pausa_detiene_el_gasto(tmp_path: Path) -> None:
    pause(tmp_path, reason="prueba")
    try:
        assert llm_spend_paused(tmp_path) is True
    finally:
        resume(tmp_path)


def test_sin_pausa_se_puede_gastar(tmp_path: Path) -> None:
    assert llm_spend_paused(tmp_path) is False


def test_es_la_misma_verdad_que_is_paused(tmp_path: Path) -> None:
    """Dos banderas distintas para lo mismo divergirían en cuanto alguien
    tocara una. El nombre propio es por legibilidad del call site, no un
    estado nuevo."""
    pause(tmp_path, reason="prueba")
    try:
        assert llm_spend_paused(tmp_path) == is_paused(tmp_path)
    finally:
        resume(tmp_path)


# --------------------------------------------------------------------------
# El mecanismo anti-envejecimiento
# --------------------------------------------------------------------------


def _es_accesor(cuerpo: str) -> bool:
    """Un accesor CONSTRUYE y devuelve un componente cacheado; no ejecuta.

    La distinción salió de romperlo: puse la guardia en `maintenance_scheduler`
    y devolvía `None` con el lazo pausado, rompiendo a todo el que esperaba el
    objeto. Un constructor no gasta inferencia — la gasta el ciclo que se
    ejecuta después, y ahí es donde va el freno (`service_runner`).
    """
    return "if self._maintenance_" in cuerpo and "is None:" in cuerpo


def test_todo_tick_que_gasta_LLM_consulta_la_pausa() -> None:
    """LA prueba. Si alguien añade un tick con inferencia y sin guardia, esto
    falla — que es la única forma de que la regla no se quede en prosa."""
    sin_guardia = []
    for nombre, cuerpo in _ticks().items():
        gasta = any(m in cuerpo for m in _MODULOS_CON_LLM) or "InferenceRequest" in cuerpo
        if not gasta or _es_accesor(cuerpo):
            continue
        if "is_paused" not in cuerpo and "llm_spend_paused" not in cuerpo:
            sin_guardia.append(nombre)

    assert not sin_guardia, (
        f"ticks que gastan inferencia sin consultar la pausa: {sin_guardia}. "
        "Añade la guardia o justifica por qué debe gastar con el lazo parado."
    )


def test_el_arranque_del_scheduler_respeta_la_pausa() -> None:
    """El scheduler es un accesor, así que su freno va donde el daemon decide
    ARRANCARLO. Sin esto, el gasto del `MaintenanceAnalyst` (128 llamadas en
    dos días) seguiría con el lazo parado."""
    source = (
        Path(__file__).resolve().parent.parent
        / "src" / "atlas" / "runtime" / "service_runner.py"
    ).read_text(encoding="utf-8")
    # Por AST y no partiendo cadenas: el nombre aparece tres veces (definición
    # y llamadas) y `split` cogía la ocurrencia equivocada.
    tree = ast.parse(source)
    cuerpo = next(
        ast.get_source_segment(source, n) or ""
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef)
        and n.name == "_start_maintenance_scheduler_if_enabled"
    )

    assert "llm_spend_paused" in cuerpo


def test_los_ticks_gratuitos_NO_se_pausan() -> None:
    """Pausar el grafo, la higiene o el watchdog sería un error: son gratis y
    son justo lo que se quiere ver mientras el lazo no corre."""
    ticks = _ticks()
    for nombre in ("maintenance_project_graph_tick", "maintenance_mcp_trial_tick"):
        cuerpo = ticks.get(nombre, "")
        assert cuerpo, f"{nombre} no encontrado"
        assert "llm_spend_paused" not in cuerpo


def test_la_lista_documentada_no_miente() -> None:
    """`PAUSED_LLM_TICKS` es documentación; si nombra un tick inexistente,
    engaña a quien la lea."""
    ticks = _ticks()
    fantasmas = [t for t in PAUSED_LLM_TICKS if t not in ticks]

    assert not fantasmas, f"la lista nombra ticks que no existen: {fantasmas}"
