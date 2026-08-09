"""El canon no puede afirmar que preservó algo que no existe.

Auditoría 2026-08-09. `docs/canon/source_registry.jsonl` (1.317 filas) es un
manifiesto de inventario por diseño: la mayoría son `INVENTORIED` con
`preserved_path: null`, y que los ZIPs de origen no estén NO es un defecto.

Pero 123 filas decían `coverage_level: PHYSICALLY_PRESERVED` y 122 de ellas
apuntaban a un fichero AUSENTE. `disposition: PRESERVED_UNIQUE_TEXT`: 122
filas, cero existen. La ruta declarada —`evidence/legacy_exclusive/…`— nunca
estuvo en git (`git log --all -- "evidence/*"` vacío) ni está en el disco.

671 KB: 65 `.md`, 32 `.yaml`, 22 `.txt`. Incluidos `claim.schema.yaml`,
`decision.schema.yaml` y `mission.schema.yaml`, sin equivalente vivo.

La ironía es que son justo las fuentes que el compilador clasificó como NO
duplicadas: los duplicados se descartaron bien porque existían en otro sitio;
lo único se marcó preservado y no está.

Lo que importa no es el bookkeeping. Es que **ninguna afirmación del canon
podía re-verificarse contra su fuente**, y el registro decía lo contrario.
Afirmar algo comprobablemente falso es peor que no afirmar nada.

Este test convierte la invariante en código, igual que `ProjectGraphWriterLock`
hizo con `graph-rebuild-single-writer`. Lección de la semana: una regla que
sólo vive en prosa se rompe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "docs" / "canon" / "source_registry.jsonl"

#: Estados que AFIRMAN que el contenido está en disco.
CLAIMS_PRESENCE = {"PHYSICALLY_PRESERVED", "PHYSICALLY_PRESERVED_WITH_CORRECTED_STATE"}


def _rows() -> list[dict[str, object]]:
    if not CORPUS.exists():
        pytest.skip("source_registry.jsonl ausente")
    return [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_lo_que_dice_estar_preservado_existe() -> None:
    """LA invariante. Si esto falla, el canon está mintiendo sobre su propia
    evidencia."""
    mentiras = [
        r for r in _rows()
        if str(r.get("coverage_level")) in CLAIMS_PRESENCE
        and not (REPO / str(r.get("preserved_path") or "")).exists()
    ]

    assert not mentiras, (
        f"{len(mentiras)} filas afirman preservación física y su fichero no existe. "
        f"Ejemplo: {mentiras[0].get('preserved_path')}"
    )


def test_un_preserved_path_no_nulo_apunta_a_algo() -> None:
    """Si se declara una ruta, tiene que resolver. `null` es una respuesta
    honesta; una ruta rota no."""
    rotas = [
        r for r in _rows()
        if r.get("preserved_path") and not (REPO / str(r["preserved_path"])).exists()
    ]

    assert not rotas, f"{len(rotas)} preserved_path no resuelven"


def test_lo_perdido_se_declara_perdido() -> None:
    """Las filas cuya evidencia se perdió llevan un estado que lo dice, con
    motivo y con la ruta que SE DECLARÓ en su día — sin eso sería borrar el
    rastro en vez de corregirlo."""
    perdidas = [r for r in _rows() if str(r.get("coverage_level")) == "LOST_NOT_PRESERVED"]

    if not perdidas:
        pytest.skip("nada marcado como perdido en este corpus")
    for row in perdidas:
        assert row.get("loss_reason"), "un estado sin motivo no es un registro"
        assert row.get("preserved_path_declared"), "se pierde el fichero, no la traza"
        assert row.get("preserved_path") is None


def test_la_correccion_no_borro_procedencia() -> None:
    """Se pierde el CONTENIDO, no la PROCEDENCIA. Marcar algo como perdido no
    puede llevarse por delante su hash.

    No se exige `sha256` en todas: 6 de las 1.317 filas nunca lo tuvieron (son
    entradas de handoff con otra forma). La invariante es que la corrección no
    quitó ninguno, no que todas lo tengan.
    """
    rows = _rows()
    con_hash = sum(1 for r in rows if r.get("sha256"))

    assert con_hash >= 1311, f"sólo {con_hash} filas conservan sha256"


def test_el_inventario_sin_preservar_sigue_siendo_valido() -> None:
    """`INVENTORIED` + `preserved_path: null` es el caso normal y mayoritario:
    se registró que la fuente existió, con su hash, sin quedarse el fichero.
    Este test existe para que el arreglo no convierta eso en un falso positivo.
    """
    rows = _rows()
    inventariadas = [r for r in rows if str(r.get("coverage_level")) == "INVENTORIED"]

    assert len(inventariadas) > 500, "el grueso del registro es inventario"
    assert all(not r.get("preserved_path") for r in inventariadas)
