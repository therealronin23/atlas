"""
Tests — AtlasCoder consulta LessonStore ANTES de generar código (cierra el
hueco señalado por el usuario: las lecciones se escribían tras fallar pero
nadie las leía antes del siguiente intento).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from atlas.core.atlas_coder import AtlasCoder
from atlas.core.lesson_store import Lesson, LessonProvenance, LessonStore
from atlas.core.verify import Verdict
from atlas.immunity.lesson_recaller import LessonRecaller


def _stub_hub(response_text: str = ""):
    hub = MagicMock()
    resp = MagicMock()
    resp.success = True
    resp.text = response_text
    resp.error = None
    hub.infer.return_value = resp
    hub.infer_for_role.return_value = resp
    return hub


def _lesson(lesson_id: str, avoid_pattern: str, heuristic: str) -> Lesson:
    return Lesson(
        id=lesson_id,
        title=lesson_id,
        detection_heuristic=heuristic,
        avoid_pattern=avoid_pattern,
        provenance=LessonProvenance.INTERNAL_FAILURE,
        evidence={"verdict": Verdict.PASS.value},
    )


def test_code_without_lesson_store_unchanged(tmp_path):
    """Sin lesson_store (default None), comportamiento idéntico — aditivo."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    sr = "<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE"
    hub = _stub_hub(sr)

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(task="cambia x", context_files=["foo.py"], test_cmd=["true"])

    assert result.success is True
    assert "x = 2" in f.read_text()


def test_code_injects_relevant_lesson_into_prompt(tmp_path):
    """Con lesson_store + lesson_recaller, una lección relevante a la tarea
    aparece en el prompt ANTES de llamar al modelo."""
    store = LessonStore(tmp_path / "lessons")
    store.add(_lesson(
        "l1",
        avoid_pattern="No uses eval() para parsear config — usa json.loads",
        heuristic="tarea menciona parsear configuracion con eval",
    ))
    recaller = LessonRecaller(store, threshold=0.0)  # threshold 0 = todo matchea

    captured_prompts: list[str] = []

    class _CapturingHub:
        def infer(self, req):
            captured_prompts.append(req.prompt)
            from atlas.core.inference_hub import InferenceResponse, InferenceLevel
            return InferenceResponse(
                success=True, text="", provider="stub", model="stub",
                level=InferenceLevel.L1, latency_ms=0,
            )

        def infer_for_role(self, role, req):
            return self.infer(req)

    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")

    coder = AtlasCoder(
        hub=_CapturingHub(), repo_root=tmp_path,
        lesson_store=store, lesson_recaller=recaller,
    )
    coder.code(
        task="parsear configuracion con eval",
        context_files=["foo.py"], test_cmd=["true"], max_iterations=1,
    )

    assert captured_prompts
    assert "Patrones a evitar" in captured_prompts[0]
    assert "eval()" in captured_prompts[0]


def test_code_no_relevant_lesson_no_section(tmp_path):
    """Lección irrelevante a la tarea → no aparece la sección (evita ruido)."""
    store = LessonStore(tmp_path / "lessons")
    store.add(_lesson(
        "l1",
        avoid_pattern="nunca hardcodear credenciales AWS",
        heuristic="tarea toca secretos de AWS",
    ))
    recaller = LessonRecaller(store, threshold=0.99)  # threshold alto = casi nada matchea

    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    sr = "<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE"
    hub = _stub_hub(sr)

    coder = AtlasCoder(
        hub=hub, repo_root=tmp_path, lesson_store=store, lesson_recaller=recaller,
    )
    result = coder.code(
        task="cambia el valor de x", context_files=["foo.py"], test_cmd=["true"],
    )

    assert result.success is True  # no rompe nada aunque no haya match


def test_with_default_lessons_factory(tmp_path):
    """AtlasCoder.with_default_lessons() cablea LessonStore + LessonRecaller
    (threshold del caso de uso, no el 0.8 de casi-duplicados) sin que el
    llamador pueda olvidarlo — cierra el error medido en el enjambre: se
    construyó la consulta de lecciones pero las delegaciones no la usaban."""
    lessons_dir = tmp_path / "lessons"
    coder = AtlasCoder.with_default_lessons(
        hub=_stub_hub(), repo_root=tmp_path, lessons_path=lessons_dir,
    )
    assert coder._lesson_store is not None
    assert coder._lesson_recaller is not None
    assert coder._lesson_recaller._threshold == 0.35
