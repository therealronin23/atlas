"""Por qué las lecciones nunca se recuperaban: los vocabularios no se cruzaban.

Medido el 2026-08-09. De 17 lecciones en disco, 16 en `stale` y 15 con
`recall_count: 0`. El `LessonStore` tiene `search_by_tag`, recall y
reactivación cableados, y aun así no enganchaba nunca.

La causa, medida y no supuesta:

  - `search_by_tag` tiene UN solo llamador de producción: `memory_hypothesis`,
    vía `compose_hypotheses`, que consulta `f"module:{module}"`.
  - Los 23 tags que existen en disco son semánticos: `conclave`, `autonomia`,
    `merkle`, `regex`, `memory`, `discovery`…
  - Tags `module:*` en disco: **CERO**.

Es decir: la única consulta de producción pedía un vocabulario que nadie
escribía. No es que el recall fallara — es que no podía acertar.

El arreglo NO inventa un motor nuevo. Añade un fallback por SEGMENTOS del
nombre de módulo, que es el vocabulario que las lecciones sí usan: de
`atlas.memory.memory_index` se prueban `memory` y `memory_index`. Medido sobre
el corpus real, eso pasa de 0 tags alcanzables a 4 (`discovery`, `knowledge`,
`memory`, `self-audit`).

Cuatro de veintitrés no es una victoria; es honestidad: el resto de tags son
conceptos (`conclave`, `hitl`, `juicio-real`) que ningún nombre de módulo
contiene, y fingir que un fallback los alcanza sería peor que no tenerlo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.lesson_store import Lesson, LessonProvenance, LessonStore
from atlas.engineering.hypotheses import memory_hypothesis


@pytest.fixture
def store(tmp_path: Path) -> LessonStore:
    st = LessonStore(tmp_path / "lessons")
    st.add(
        Lesson(
            id="l-memoria", title="El índice de memoria se corrompía",
            provenance=LessonProvenance.INTERNAL_FAILURE,
            detection_heuristic="h", avoid_pattern="a", evidence={"verdict": "pass"},
            tags=("memory", "concurrency"),
        )
    )
    st.add(
        Lesson(
            id="l-conclave", title="El Cónclave ahogaba a los modelos",
            provenance=LessonProvenance.INTERNAL_FAILURE,
            detection_heuristic="h", avoid_pattern="a", evidence={"verdict": "pass"},
            tags=("conclave", "razonamiento"),
        )
    )
    return st


def test_el_tag_exacto_sigue_teniendo_prioridad(store: LessonStore) -> None:
    """Si alguien SÍ etiqueta `module:...`, esa es la respuesta buena y el
    fallback no debe estorbar."""
    store.add(
        Lesson(
            id="l-exacta", title="t",
            provenance=LessonProvenance.INTERNAL_FAILURE,
            detection_heuristic="h", avoid_pattern="a", evidence={"verdict": "pass"},
            tags=("module:atlas.memory.memory_index",),
        )
    )

    r = memory_hypothesis(store, "module:atlas.memory.memory_index")

    assert r.available is True
    assert "l-exacta" in r.lesson_ids


def test_sin_tag_exacto_cae_a_los_segmentos_del_modulo(store: LessonStore) -> None:
    """EL arreglo. `module:atlas.memory.memory_index` no existe como tag, pero
    `memory` sí — y es la misma lección que se quería."""
    r = memory_hypothesis(store, "module:atlas.memory.memory_index")

    assert r.available is True
    assert "l-memoria" in r.lesson_ids


def test_no_arrastra_lecciones_de_otro_asunto(store: LessonStore) -> None:
    """Un fallback demasiado ancho devolvería todo y sería ruido con formato de
    señal — peor que no devolver nada."""
    r = memory_hypothesis(store, "module:atlas.memory.memory_index")

    assert "l-conclave" not in r.lesson_ids


def test_un_modulo_sin_leccion_no_inventa(store: LessonStore) -> None:
    r = memory_hypothesis(store, "module:atlas.security.bwrap_jail")

    assert r.lesson_count == 0


def test_los_guiones_y_los_underscores_son_el_mismo_concepto(tmp_path: Path) -> None:
    """`self-audit` en los tags y `self_audit` en los módulos: el corpus real
    usa guiones y el código underscores."""
    st = LessonStore(tmp_path / "l")
    st.add(
        Lesson(
            id="l-audit", title="t",
            provenance=LessonProvenance.INTERNAL_FAILURE,
            detection_heuristic="h", avoid_pattern="a", evidence={"verdict": "pass"},
            tags=("self-audit",),
        )
    )

    r = memory_hypothesis(st, "module:atlas.core.self_audit")

    assert "l-audit" in r.lesson_ids


def test_no_cae_por_segmentos_genericos(tmp_path: Path) -> None:
    """`atlas` y `core` son segmentos de casi todo: usarlos devolvería el
    corpus entero para cualquier consulta."""
    st = LessonStore(tmp_path / "l")
    st.add(
        Lesson(
            id="l-generica", title="t",
            provenance=LessonProvenance.INTERNAL_FAILURE,
            detection_heuristic="h", avoid_pattern="a", evidence={"verdict": "pass"},
            tags=("core",),
        )
    )

    r = memory_hypothesis(st, "module:atlas.core.orchestrator")

    assert "l-generica" not in r.lesson_ids


def test_un_tag_no_module_se_consulta_tal_cual(store: LessonStore) -> None:
    """El fallback es sólo para tags `module:`; una consulta directa no cambia."""
    r = memory_hypothesis(store, "conclave")

    assert "l-conclave" in r.lesson_ids


def test_sigue_sin_lanzar_si_el_store_falla(tmp_path: Path) -> None:
    class _Roto:
        def search_by_tag(self, tag: str) -> list:
            raise OSError("disco")

    r = memory_hypothesis(_Roto(), "module:atlas.core.x")  # type: ignore[arg-type]

    assert r.available is False
    assert r.reason
