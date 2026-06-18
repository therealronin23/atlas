"""
Atlas Core — SLMClassifier (ADR-010, Gate D/D2)

Clasificador basado en SLM (Small Language Model) como complemento al
rule-based Classifier. La idea NO es reemplazar — los patrones regex
son deterministicos, microsegundos y validados — sino actuar como capa
inteligente cuando el rule-based es ambiguo (confidence baja).

Arquitectura:
    intent
      |
      v
    Classifier (rule-based)            <-- fast path
      |
      | confidence < umbral?
      v
    SLMClassifier (LiteLLM via InferenceHub)
      |
      |  - prompt estructurado pidiendo JSON con RoutingLevel + reason
      |  - cache de resultados via GhostReplay (opcional)
      v
    ClassificationResult

Modo auto/live/stub coherente con InferenceHub:
  - "auto" (default): live cuando hay key + litellm + no en pytest;
                       stub en otro caso.
  - "live": fuerza llamada real.
  - "stub": clasificacion deterministica simple (longitud + palabras
            clave) sin red.

El cableo automatico al pipeline del Orchestrator (hibridar rule-based
y SLM) queda como follow-up; aqui se entrega la pieza aislada con
contrato claro.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from atlas.core.contracts import RoutingLevel
from atlas.core.inference_hub import (
    InferenceHub,
    InferenceLevel,
    InferenceRequest,
)


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SLMClassification:
    """Resultado de clasificacion SLM-based."""

    level: RoutingLevel
    confidence: float          # 0.0-1.0
    reason: str                # explicacion del SLM (o regla del stub)
    mode: str                  # "live" | "stub" | "cache"
    provider: str | None = None
    raw_text: str | None = None  # texto crudo devuelto por el LLM si live


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


SLM_SYSTEM_PROMPT = """Eres el router de Atlas Core. Dado un intent del usuario,
clasificalo en uno de estos niveles:

- deterministic_tool: tarea simple y segura (leer ficheros del workspace,
  git status, listar directorios, consultar estado). Sin LLM.
- local_safe: tarea que requiere razonamiento o LLM pero no efectos
  externos peligrosos. INCLUYE: saludos, charla, preguntas conversacionales,
  resumir codigo, explicar un concepto, generar texto, traducir, definir.
  USA ESTE NIVEL POR DEFECTO si dudas — Atlas responde conversando.
- requires_approval: tarea con efectos destructivos o irreversibles
  (git push/reset, instalar, borrar archivos, modificar config).
- delegate_hermes: tarea que necesita estar disponible cuando Atlas no
  esta (scraping, webhooks, monitoreo 24/7, recordatorios programados).
- blocked: SOLO acciones que CLARAMENTE violan la constitucion
  (sudo, rm -rf /, modificar governance.json, deshabilitar guards,
  pedir credenciales/secretos, ejecutar codigo no-confiable). NO uses
  blocked para intents ambiguos, vacios o conversacionales — esos son
  local_safe.

Responde EXCLUSIVAMENTE con un objeto JSON con esta forma exacta:
{"level": "...", "confidence": 0.0, "reason": "..."}

confidence es tu certeza en [0.0, 1.0]. reason en 1 frase corta."""


def _build_prompt(intent: str) -> str:
    return f"Intent del usuario:\n{intent.strip()}\n\nDevuelve solo el JSON."


# ---------------------------------------------------------------------------
# Clasificador
# ---------------------------------------------------------------------------


_VALID_LEVELS = {lvl.value: lvl for lvl in RoutingLevel}


class SLMClassifier:
    """
    Clasificador basado en SLM. Acepta InferenceHub para la llamada real.

    Si se le pasa un GhostReplay (lazy-imported para evitar acoplamiento),
    cachea las clasificaciones bajo:
        intent = intent
        sensitivity = "classification"
        context_signature = "slm-classifier-v1"

    Si se le pasa un MemoryDistiller (ADR-018 / FU-5), comprime el contexto
    del sistema antes de enviarlo al SLM:
        build_context(query=intent, system_chunks=[SLM_SYSTEM_PROMPT])
    El resultado reemplaza a SLM_SYSTEM_PROMPT como context del InferenceRequest,
    reduciendo tokens y inyectando patrones/errores relevantes del vault.
    """

    DEFAULT_TIMEOUT_S = 5
    DEFAULT_MAX_TOKENS = 200
    _DISTILLER_BUDGET_TOKENS = 800   # deja margen para prompt + respuesta

    def __init__(
        self,
        hub: InferenceHub | None = None,
        *,
        mode: str = "auto",
        ghost_replay: Any = None,
        distiller: Any = None,        # MemoryDistiller | None (lazy para evitar ciclos)
    ) -> None:
        if mode not in ("auto", "live", "stub"):
            raise ValueError(f"mode invalido: {mode}")
        self._hub = hub
        self._mode = os.environ.get("ATLAS_SLM_CLASSIFIER_MODE", mode)
        self._cache = ghost_replay
        self._distiller = distiller

    @property
    def mode(self) -> str:
        return self._mode

    def classify(self, intent: str) -> SLMClassification:
        if not intent or not intent.strip():
            return SLMClassification(
                level=RoutingLevel.DETERMINISTIC_TOOL,
                confidence=0.0,
                reason="intent vacio -> tool determinista por defecto",
                mode=self._resolve_mode(),
            )

        # Cache lookup
        if self._cache is not None:
            try:
                hit = self._cache.lookup(intent, "classification", "slm-classifier-v1")
            except Exception:  # noqa: BLE001 — cache no debe romper la clasificacion
                hit = None
            if hit is not None:
                payload = hit.result
                return SLMClassification(
                    level=RoutingLevel(payload["level"]),
                    confidence=float(payload["confidence"]),
                    reason=str(payload["reason"]),
                    mode="cache",
                    provider=payload.get("provider"),
                    raw_text=payload.get("raw_text"),
                )

        if self._resolve_mode() == "live" and self._hub is not None:
            result = self._classify_live(intent)
        else:
            result = self._classify_stub(intent)

        # Cache store
        if self._cache is not None:
            try:
                self._cache.record(
                    intent, "classification", "slm-classifier-v1",
                    {
                        "level":      result.level.value,
                        "confidence": result.confidence,
                        "reason":     result.reason,
                        "provider":   result.provider,
                        "raw_text":   result.raw_text,
                    },
                    metadata={"mode": result.mode},
                )
            except Exception:  # noqa: BLE001
                pass

        return result

    # ------------------------------------------------------------------
    # Live: llama al InferenceHub
    # ------------------------------------------------------------------

    def _build_context(self, intent: str) -> str:
        """
        Construye el contexto del sistema para el SLM.
        Si hay MemoryDistiller disponible, comprime el contexto por relevancia
        con budget de tokens. Si no, devuelve SLM_SYSTEM_PROMPT sin modificar.
        """
        if self._distiller is None:
            return SLM_SYSTEM_PROMPT
        try:
            ctx, _chunks = self._distiller.build_context(
                query=intent,
                system_chunks=[SLM_SYSTEM_PROMPT],
                budget_tokens=self._DISTILLER_BUDGET_TOKENS,
            )
            return ctx if ctx.strip() else SLM_SYSTEM_PROMPT
        except Exception:  # noqa: BLE001 — distiller nunca debe romper la clasificacion
            return SLM_SYSTEM_PROMPT

    def _classify_live(self, intent: str) -> SLMClassification:
        assert self._hub is not None
        request = InferenceRequest(
            prompt=_build_prompt(intent),
            level=InferenceLevel.L1,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            temperature=0.0,
            context=self._build_context(intent),
        )
        resp = self._hub.infer(request)
        if not resp.success:
            return SLMClassification(
                level=RoutingLevel.LOCAL_SAFE,
                confidence=0.0,
                reason=f"fallback: hub no devolvio respuesta ({resp.error or 'desconocido'})",
                mode="live",
                provider=resp.provider,
            )

        parsed = _parse_classification_json(resp.text)
        if parsed is None:
            return SLMClassification(
                level=RoutingLevel.LOCAL_SAFE,
                confidence=0.3,
                reason="JSON no parseable; fallback a LOCAL_SAFE",
                mode="live",
                provider=resp.provider,
                raw_text=resp.text,
            )
        level_str, conf, reason = parsed
        if level_str not in _VALID_LEVELS:
            return SLMClassification(
                level=RoutingLevel.LOCAL_SAFE,
                confidence=max(0.0, min(conf, 0.4)),
                reason=f"level desconocido '{level_str}'; fallback a LOCAL_SAFE",
                mode="live",
                provider=resp.provider,
                raw_text=resp.text,
            )
        return SLMClassification(
            level=_VALID_LEVELS[level_str],
            confidence=conf,
            reason=reason,
            mode="live",
            provider=resp.provider,
            raw_text=resp.text,
        )

    # ------------------------------------------------------------------
    # Stub: heuristica simple sin red
    # ------------------------------------------------------------------

    def _classify_stub(self, intent: str) -> SLMClassification:
        text = intent.lower()
        # Reproduce a grandes rasgos la jerarquia del rule-based (sin
        # acoplarse): governance > approval > hermes > deterministic > local_safe.
        if re.search(r"\b(sudo|rm\s+-rf|chmod\s+777|governance\.json)\b", text):
            return SLMClassification(
                level=RoutingLevel.BLOCKED,
                confidence=1.0,
                reason="stub: detectado patron de governance",
                mode="stub",
            )
        if re.search(
            r"\b(borra|elimina|delete|remove|push|reset|rebase|instala|format)\w*\b",
            text,
        ):
            return SLMClassification(
                level=RoutingLevel.REQUIRES_APPROVAL,
                confidence=0.85,
                reason="stub: detectado patron de operacion destructiva",
                mode="stub",
            )
        if re.search(
            r"\b(scrape|webhook|cuando.*no.*est|disponible.*24|monitor|recordatorio)\b",
            text,
        ):
            return SLMClassification(
                level=RoutingLevel.DELEGATE_HERMES,
                confidence=0.8,
                reason="stub: tarea de larga duracion o asincrona",
                mode="stub",
            )
        if re.search(
            r"\b(lee|leer|muestra|abre|lista|listar|status|log|busca|grep)\b",
            text,
        ):
            return SLMClassification(
                level=RoutingLevel.DETERMINISTIC_TOOL,
                confidence=0.9,
                reason="stub: comando de inspeccion local",
                mode="stub",
            )
        return SLMClassification(
            level=RoutingLevel.LOCAL_SAFE,
            confidence=0.6,
            reason="stub: sin coincidencias, default a LOCAL_SAFE",
            mode="stub",
        )

    # ------------------------------------------------------------------
    # Mode resolution (coherente con InferenceHub/Embeddings)
    # ------------------------------------------------------------------

    def _resolve_mode(self) -> str:
        if self._mode == "stub":
            return "stub"
        if self._mode == "live":
            return "live"
        # auto
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return "stub"
        if self._hub is None:
            return "stub"
        return "live"


# ---------------------------------------------------------------------------
# Parseo del JSON devuelto por el SLM
# ---------------------------------------------------------------------------


_JSON_BLOCK_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _parse_classification_json(text: str) -> tuple[str, float, str] | None:
    """
    Extrae {"level":..., "confidence":..., "reason":...} del texto.
    Tolera fences markdown y texto antes/despues del JSON.
    """
    if not text:
        return None
    # Quitar fences ``` ... ```
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
    stripped = re.sub(r"\s*```\s*$", "", stripped)

    candidates = [stripped]
    for m in _JSON_BLOCK_RE.finditer(text):
        candidates.append(m.group(0))

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        level = data.get("level")
        confidence = data.get("confidence")
        reason = data.get("reason", "")
        if not isinstance(level, str):
            continue
        if confidence is None:
            continue
        try:
            conf = float(confidence)
        except (TypeError, ValueError):
            continue
        conf = max(0.0, min(conf, 1.0))
        return level, conf, str(reason)
    return None
