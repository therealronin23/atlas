"""
Tests de verificación — Tarea C (técnica #15, Aider): cuando el linter
bloqueante rechaza una edición, el ERROR se retroalimenta al modelo en la
siguiente iteración (no solo se loggea) — el modelo puede corregirse a sí
mismo en vez de repetir el mismo error a ciegas.
"""

from __future__ import annotations

from atlas.core.atlas_coder import AtlasCoder


def _sr(search: str, replace: str) -> str:
    return f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"


class _SequenceHub:
    """Hub que devuelve respuestas distintas por llamada y captura los prompts."""

    def __init__(self, responses: list[str]):
        self._responses = responses
        self.prompts: list[str] = []
        self._i = 0

    def infer(self, req):
        from atlas.core.inference_hub import InferenceResponse, InferenceLevel
        self.prompts.append(req.prompt)
        text = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return InferenceResponse(
            success=True, text=text, provider="stub", model="stub",
            level=InferenceLevel.L1, latency_ms=0,
        )

    def infer_for_role(self, role, req):
        return self.infer(req)


def test_lint_rejection_is_fed_back_to_model(tmp_path):
    """Iteración 1: edición con sintaxis rota (rechazada por el linter).
    Iteración 2: el prompt DEBE mencionar el rechazo del linter para que el
    modelo sepa qué corregir."""
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")

    hub = _SequenceHub([
        _sr("x = 1", "x = ((( roto"),   # iter 1: linter la rechaza
        _sr("x = 1", "x = 2"),           # iter 2: corregida
    ])

    coder = AtlasCoder(hub, repo_root=tmp_path)
    result = coder.code(
        task="cambia x",
        context_files=["foo.py"],
        test_cmd=["false"],  # tests siempre fallan → fuerza 2ª iteración
        max_iterations=2,
    )

    assert len(hub.prompts) == 2
    # El segundo prompt menciona el problema de sintaxis del intento anterior
    assert "SyntaxError" in hub.prompts[1] or "sintaxis" in hub.prompts[1].lower()
