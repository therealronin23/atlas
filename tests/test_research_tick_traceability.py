"""t15: una pasada que pisa el informe de investigación deja rastro, pase lo
que pase — y dos pasadas no se solapan.

QUÉ SE OBSERVÓ (2026-08-11, sin buscarlo). El ledger registra un
`research_tick` el 2026-08-10 a las 00:14 con `queries_count: 12` y
`findings_count: 122`. Pero `docs/inbox/research_2026-08-10.md` quedó escrito
más tarde con **4 hallazgos** y una expansión degradada, y **sin ninguna
entrada en el ledger**. Una escritura en el repo sin rastro.

QUÉ SE PUDO MEDIR, y qué no:

- Sólo hay UN escritor de `docs/inbox/research_<fecha>.md`:
  `maintenance_research_tick`. No hay un segundo camino.
- `curated_sources.yaml` no cambia desde el 2026-07-25, así que la mitad `sha`
  del guardia NO pudo diferir entre las dos pasadas.
- El ledger tiene exactamente una entrada por día (09, 10 y 11 de agosto), las
  tres con 122 hallazgos. La segunda pasada del 10 no está.
- En el informe degradado, las "consultas expandidas" son IDÉNTICAS a las
  semillas, y las semillas son las tres de reserva por código — la rama que
  sólo se toma con el LessonStore VACÍO. O sea: esa pasada no vio las
  lecciones del repo y tampoco obtuvo expansión del LLM.
- `_project_root()` cae a **`Path.cwd()`** si no hay `ATLAS_CORE_ROOT`,
  mientras que el ledger cuelga de `ATLAS_HOME`. Las dos rutas pueden
  divergir: un proceso puede escribir el informe en un sitio y auditar en
  otro.

**No se pudo establecer qué proceso concreto escribió aquel fichero**, y
decirlo importa más que inventar una causa. Lo que sí se puede es hacer que la
pregunta sea contestable la próxima vez y que el solapamiento no ocurra:

1. Pisar un informe existente deja `research_tick.overwrite` en el ledger
   ANTES de escribir. Antes, el único registro iba después de la escritura, y
   cualquier fallo en medio se llevaba el rastro.
2. La entrada lleva `project_root` y `atlas_home` resueltos, que es justo lo
   que faltaba para responder "¿desde dónde corrió esto?".
3. El guardia de "ya corrió hoy" se leía arriba y se escribía abajo, con horas
   de tick en medio y sin lock: dos pasadas solapadas lo cruzaban las dos. El
   mismo agujero que el grafo tuvo hasta el 2026-08-08, y ahí se cerró con un
   lock. Aquí también.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from atlas.core.orchestrator_parts.maintenance_facade import (
    ResearchReportWriter,
)


class _MerkleFalso:
    def __init__(self) -> None:
        self.entradas: list[dict[str, Any]] = []

    def log(self, **kwargs: Any) -> None:
        self.entradas.append(kwargs)

    def acciones(self) -> list[str]:
        return [str(e.get("action", "")) for e in self.entradas]


@pytest.fixture
def raiz(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "inbox").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# El rastro
# ---------------------------------------------------------------------------


def test_un_informe_nuevo_no_registra_sobrescritura(raiz: Path) -> None:
    merkle = _MerkleFalso()
    escritor = ResearchReportWriter(raiz, merkle, home=raiz / "home")

    escritor.write("2026-08-10", "# informe\n")

    assert "self_maintenance.research_tick.overwrite" not in merkle.acciones()
    assert (raiz / "docs" / "inbox" / "research_2026-08-10.md").exists()


def test_pisar_un_informe_deja_rastro_ANTES_de_pisarlo(raiz: Path) -> None:
    """El orden importa: si el registro fuera después de escribir, un fallo
    en medio se llevaría por delante el informe Y el rastro, que es
    exactamente lo que pasó el 2026-08-10."""
    destino = raiz / "docs" / "inbox" / "research_2026-08-10.md"
    destino.write_text("# el bueno\n" + "x" * 500, encoding="utf-8")
    merkle = _MerkleFalso()
    escritor = ResearchReportWriter(raiz, merkle, home=raiz / "home")

    def _explota(*_a: object, **_k: object) -> None:
        raise OSError("disco lleno")

    escritor._escribir = _explota  # type: ignore[method-assign]
    with pytest.raises(OSError):
        escritor.write("2026-08-10", "# el degradado\n")

    # El informe no se escribió, pero el intento de pisarlo SÍ dejó rastro.
    assert "self_maintenance.research_tick.overwrite" in merkle.acciones()
    assert destino.read_text(encoding="utf-8").startswith("# el bueno")


def test_el_rastro_dice_que_habia_antes_y_desde_donde_se_escribe(raiz: Path) -> None:
    """Sin el tamaño previo no se puede saber si lo que se pisó era mejor;
    sin las rutas resueltas no se puede saber qué proceso fue."""
    destino = raiz / "docs" / "inbox" / "research_2026-08-10.md"
    previo = "# el bueno\n" + "x" * 1234
    destino.write_text(previo, encoding="utf-8")
    merkle = _MerkleFalso()

    ResearchReportWriter(raiz, merkle, home=raiz / "home").write(
        "2026-08-10", "# corto\n"
    )

    entrada = next(
        e for e in merkle.entradas
        if e["action"] == "self_maintenance.research_tick.overwrite"
    )
    payload = entrada["payload"]
    assert payload["previous_bytes"] == len(previo.encode("utf-8"))
    assert payload["new_bytes"] == len("# corto\n".encode("utf-8"))
    assert payload["project_root"] == str(raiz)
    assert payload["atlas_home"] == str(raiz / "home")
    # Pisar un informe es un evento de riesgo, no rutina.
    assert entrada["risk_level"] == "high"


def test_el_contenido_escrito_es_exactamente_el_pedido(raiz: Path) -> None:
    merkle = _MerkleFalso()
    ResearchReportWriter(raiz, merkle, home=raiz / "home").write(
        "2026-08-10", "# contenido\n"
    )

    destino = raiz / "docs" / "inbox" / "research_2026-08-10.md"
    assert destino.read_text(encoding="utf-8") == "# contenido\n"


# ---------------------------------------------------------------------------
# El solapamiento
# ---------------------------------------------------------------------------


def test_dos_pasadas_no_pueden_solaparse(raiz: Path) -> None:
    """El guardia `already_ran_today` se lee al principio y el estado se
    escribe al final, con todo el tick en medio. Sin lock, una segunda pasada
    que entre durante la primera lo cruza sin enterarse."""
    from atlas.security.writer_lock import ResearchWriterLock, WriterLockHeld

    primero = ResearchWriterLock(raiz)
    primero.acquire()
    try:
        with pytest.raises(WriterLockHeld):
            ResearchWriterLock(raiz).acquire()
    finally:
        primero.release()

    # Y liberado, el siguiente entra sin problema: es un turno, no una avería.
    segundo = ResearchWriterLock(raiz)
    segundo.acquire()
    segundo.release()


def test_el_lock_de_investigacion_no_choca_con_el_del_grafo(raiz: Path) -> None:
    """Recursos distintos, locks distintos: bloquear la investigación porque
    el grafo se está reconstruyendo sería un falso positivo."""
    from atlas.security.writer_lock import ProjectGraphWriterLock, ResearchWriterLock

    grafo = ProjectGraphWriterLock(raiz / "grafo.kuzu")
    grafo.acquire()
    try:
        investigacion = ResearchWriterLock(raiz)
        investigacion.acquire()
        investigacion.release()
    finally:
        grafo.release()


def test_el_tick_cede_el_turno_en_vez_de_reventar(
    raiz: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Solaparse no es un error del scheduler: el segundo cede y el siguiente
    ciclo lo recoge. Mismo criterio que el tick del grafo."""
    from atlas.security.writer_lock import ResearchWriterLock

    from atlas.core.orchestrator import Orchestrator

    monkeypatch.setenv("ATLAS_RESEARCH", "1")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(raiz))
    monkeypatch.delenv("ATLAS_NESTED_TEST_RUN", raising=False)

    otro = ResearchWriterLock(raiz)
    otro.acquire()
    try:
        facade = Orchestrator.__new__(Orchestrator)  # sin construir el mundo
        from atlas.core.orchestrator_parts.maintenance_facade import (
            MaintenanceFacade,
        )

        resultado = MaintenanceFacade(facade).maintenance_research_tick()
    finally:
        otro.release()

    assert resultado["status"] == "locked"
    assert "otro escritor" in resultado["reason"]


# ---------------------------------------------------------------------------
# Que no vuelva a haber dos rutas para lo mismo
# ---------------------------------------------------------------------------


def test_solo_el_escritor_construye_la_ruta_del_informe() -> None:
    """Si alguien vuelve a componer `docs/inbox/research_...md` por su
    cuenta, el rastro deja de ser obligatorio para ese camino."""
    import ast

    src = Path(__file__).resolve().parent.parent / "src" / "atlas"
    culpables: list[tuple[str, int]] = []
    for path in sorted(src.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        codigo = path.read_text(encoding="utf-8", errors="replace")
        if "research_" not in codigo:
            continue
        for node in ast.walk(ast.parse(codigo)):
            if not isinstance(node, ast.JoinedStr):
                continue
            texto = ast.unparse(node)
            if "research_" in texto and ".md" in texto:
                culpables.append((path.relative_to(src).as_posix(), node.lineno))
    assert culpables == [
        ("core/orchestrator_parts/maintenance_facade.py", _linea_del_escritor())
    ], culpables


def _linea_del_escritor() -> int:
    """La línea donde `ResearchReportWriter` compone la ruta. Se busca en vez
    de fijarse para que mover código no rompa el test por la razón
    equivocada."""
    ruta = (
        Path(__file__).resolve().parent.parent
        / "src" / "atlas" / "core" / "orchestrator_parts" / "maintenance_facade.py"
    )
    for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
        if 'f"research_{' in linea:
            return numero
    raise AssertionError("no se encontró la composición de la ruta del informe")
