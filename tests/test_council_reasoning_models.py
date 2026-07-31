"""El Cónclave ahogaba a los modelos de razonamiento (2026-07-31).

Lo destapó el operador preguntando *"¿qué cojones le pasa a Gemini que habla de
forma agresiva o extraña?"*. No era rareza del modelo: eran dos defectos
superpuestos, ambos medidos en vivo.

**1. Presupuesto insuficiente.** `LlmReviewer.review()` no fijaba
`max_tokens`, así que heredaba el default de 1024 de `InferenceRequest`.
`gemini-2.5-flash` es un modelo de RAZONAMIENTO: su presupuesto de salida
incluye los tokens que gasta pensando. Medido con el mismo prompt::

    max_tokens=1024 -> 153 chars, UNA frase cortada
    max_tokens=4096 -> 510 chars, TRES objeciones completas

Y el fallo es especialmente traicionero porque **el insulto va primero y el
análisis después**: la truncación se come la parte útil y deja intacta la
agresividad. Parecía que Gemini sólo sabía insultar; en realidad razonaba y
nunca se llegaba a ver. En el Cónclave real de ese día su voto ``BLOCKING`` se
emitió sobre un fragmento, y el panel lo contó como voz completa.

**2. Cadena de pensamiento sin filtrar.** Qwen emite ``<think>...</think>``
antes de responder. Como la severidad se ancla a la PRIMERA línea, esa línea
era ``<think>`` y no una severidad, así que el parseo caía al fail-closed
``MAJOR`` — **descartando la severidad real que el modelo había emitido**
(``BLOCKING`` en su propio texto). No es cosmética: el panel registraba una
severidad distinta de la que la voz dio.
"""

from __future__ import annotations

from dataclasses import dataclass

from atlas.core.adversarial_panel import Severity
from atlas.core.inference_hub import InferenceLevel
from atlas.core.deliberation_council import LlmReviewer


@dataclass
class _Resp:
    text: str
    success: bool = True


class _SpyHub:
    """Captura la petición para poder afirmar sobre el presupuesto pedido."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.requests: list[object] = []

    def infer(self, request: object) -> _Resp:
        self.requests.append(request)
        return _Resp(self._text)


def _reviewer(hub: object) -> LlmReviewer:
    return LlmReviewer("r1", "p1", hub, InferenceLevel.L0)  # type: ignore[arg-type]


class TestReasoningBudget:
    def test_asks_for_more_than_the_default_budget(self) -> None:
        """1024 deja a un modelo de razonamiento con ~40 tokens de respuesta."""
        hub = _SpyHub("MAJOR\nobjecion concreta")

        _reviewer(hub).review("una decision")

        assert hub.requests, "no se llamó al hub"
        assert getattr(hub.requests[0], "max_tokens", 0) >= 4096


class TestThinkingBlocksAreStripped:
    def test_severity_survives_a_leading_think_block(self) -> None:
        # El caso real de Qwen: emitió BLOCKING, el panel registró MAJOR
        # porque la primera línea era `<think>`.
        hub = _SpyHub("<think>\nDejame razonar esto...\n</think>\nBLOCKING\nrompe el invariante")

        objection = _reviewer(hub).review("una decision")

        assert objection.severity is Severity.BLOCKING
        assert "rompe el invariante" in objection.detail

    def test_the_thinking_text_is_not_kept_as_the_objection(self) -> None:
        hub = _SpyHub("<think>\nruido interno\n</think>\nMINOR\nla objecion de verdad")

        objection = _reviewer(hub).review("una decision")

        assert "ruido interno" not in objection.detail
        assert objection.detail == "la objecion de verdad"

    def test_an_unclosed_think_block_does_not_swallow_everything(self) -> None:
        # Si el modelo se queda sin presupuesto a mitad del <think>, no hay
        # cierre. Preferible conservar el texto a devolver vacío.
        hub = _SpyHub("<think>\nme quede sin tokens a mitad")

        objection = _reviewer(hub).review("una decision")

        assert objection.severity is Severity.MAJOR  # fail-closed
        assert objection.detail.strip()


class TestExistingBehaviourPreserved:
    def test_a_clean_response_still_parses(self) -> None:
        hub = _SpyHub("BLOCKING\nla objecion")

        objection = _reviewer(hub).review("una decision")

        assert objection.severity is Severity.BLOCKING
        assert objection.detail == "la objecion"
        assert objection.reachable is True

    def test_a_failed_call_is_still_unreachable(self) -> None:
        class _Dead:
            def infer(self, request: object) -> _Resp:
                return _Resp("", success=False)

        objection = _reviewer(_Dead()).review("una decision")

        assert objection.reachable is False
