"""Paso 3 del roadmap "juicio real para autoauditoría" (tras PreflightGate y
BatchPremortemGate). Incidente real que motiva esto: 9 YAML regenerados sin
commit hicieron fallar 38 propuestas legítimas de bump de dependencias
durante una semana — el worktree se construyó desde HEAD (que tenía una
versión vieja/vacía de un archivo) mientras la carpeta de trabajo real tenía
la versión buena SIN COMMITEAR, y nadie razonó el PORQUÉ del fallo porque
``ValidationRunner`` solo guarda el texto de pytest.

Barato antes que caro: el chequeo determinista contra git es SIEMPRE gratis
(nunca llama al LLM) y tiene prioridad — es exactamente lo que habría
detectado el incidente real (archivo mencionado en el fallo con diferencias
sin commitear entre HEAD y la carpeta de trabajo). Solo si ese chequeo no
encuentra evidencia clara cae a un LLM barato que razona sobre el texto del
fallo, mismo patrón dual-LLM que ``analyst.py`` / ``batch_premortem.py``."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from atlas.core.git_env import clean_git_env
from atlas.core.inference_hub import InferenceLevel, InferenceRequest

# Extrae candidatos de ruta de archivo mencionados en texto de pytest/mypy:
# rutas relativas con extensión conocida, evita falsos positivos triviales
# (URLs, números de línea sueltos, etc.)
_PATH_PATTERN = re.compile(
    r"[\w./\-]+\.(?:py|yaml|yml|json|toml|md|txt|cfg|ini)"
)

_CLASSIFY_INSTRUCTION = (
    "Un fallo de validación ocurrió al probar un cambio propuesto. Razona si el "
    "fallo lo CAUSA de verdad el cambio propuesto, o si es AMBIENTAL (ajeno al "
    "diff: infraestructura, flakiness, dependencias externas, etc.). Responde "
    "con un objeto JSON {\"classification\": \"causado_por_diff\"|\"ambiental\"|"
    "\"unknown\", \"reason\": \"...\"}. Nada más."
)


@dataclass
class RootCauseVerdict:
    classification: str          # "ambiental" | "causado_por_diff" | "unknown"
    reason: str
    evidence_paths: list[str] = field(default_factory=list)  # archivos con divergencia git detectada
    used_llm: bool = False       # False si el chequeo determinista bastó (ahorro real)

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "reason": self.reason,
            "evidence_paths": list(self.evidence_paths),
            "used_llm": self.used_llm,
        }


class RootCauseClassifier:
    """Clasifica un fallo de validación: ¿ambiental (ajeno al diff) o causado
    de verdad por el cambio propuesto? Barato antes que caro: primero un
    chequeo determinista contra git (gratis), solo si no hay evidencia cae
    a un LLM barato que razona sobre el texto del fallo."""

    AGENT = "self_maintenance.root_cause_classifier"

    def __init__(self, *, hub: Any, repo_root: Path, merkle: Any | None = None) -> None:
        self._hub = hub
        self._repo_root = repo_root
        self._merkle = merkle

    def classify(self, *, pytest_summary: str, mypy_summary: str, base_ref: str = "HEAD") -> RootCauseVerdict:
        candidate_paths = self._extract_candidate_paths(pytest_summary + "\n" + mypy_summary)
        dirty = self._find_dirty_relative_to_base(candidate_paths, base_ref)
        if dirty:
            return RootCauseVerdict(
                classification="ambiental",
                reason=(
                    f"El worktree se construyó desde '{base_ref}', pero el/los archivo(s) "
                    f"{', '.join(dirty)} tienen cambios sin commitear en la carpeta de trabajo "
                    "real que el worktree no incluye — el fallo probablemente no tiene relación "
                    "con el cambio propuesto."
                ),
                evidence_paths=dirty,
                used_llm=False,
            )
        return self._classify_with_llm(pytest_summary, mypy_summary)

    # ------------------------------------------------------------------
    # extracción determinista de paths candidatos
    # ------------------------------------------------------------------

    def _extract_candidate_paths(self, text: str) -> list[str]:
        seen: dict[str, None] = {}
        for match in _PATH_PATTERN.findall(text):
            path = match.strip()
            if not path or path.startswith("/"):
                continue  # rutas absolutas fuera del repo no son candidatas
            seen.setdefault(path, None)
        return list(seen)

    # ------------------------------------------------------------------
    # chequeo determinista contra git: SIEMPRE gratis, nunca llama al LLM.
    # Es exactamente lo que habría detectado el incidente real (worktree
    # construido desde HEAD sin los cambios sin commitear de la carpeta
    # real), así que tiene prioridad absoluta sobre el camino LLM.
    # ------------------------------------------------------------------

    def _find_dirty_relative_to_base(self, paths: list[str], base_ref: str) -> list[str]:
        dirty: list[str] = []
        for path in paths:
            try:
                result = subprocess.run(
                    ["git", "diff", "--stat", base_ref, "--", path],
                    cwd=self._repo_root,
                    env=clean_git_env(),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (OSError, subprocess.SubprocessError):
                # repo no es git, git no disponible, etc.: sin evidencia,
                # no propaga la excepción, cae al LLM igual.
                continue
            if result.returncode != 0:
                continue  # p.ej. base_ref inválido: sin evidencia, no es un error fatal
            if result.stdout.strip():
                dirty.append(path)
        return dirty

    # ------------------------------------------------------------------
    # camino de escalada: un solo LLM barato, fail-open si no parsea/falla
    # ------------------------------------------------------------------

    def _classify_with_llm(self, pytest_summary: str, mypy_summary: str) -> RootCauseVerdict:
        prompt = (
            f"{_CLASSIFY_INSTRUCTION}\n\npytest:\n{pytest_summary}\n\nmypy:\n{mypy_summary}"
        )
        try:
            resp = self._hub.infer(InferenceRequest(
                prompt=prompt,
                level=InferenceLevel.L1,
                temperature=0.0,
                task_id="root_cause_classifier",
            ))
        except Exception:  # noqa: BLE001 — señal adicional, nunca crashea
            return RootCauseVerdict(classification="unknown", reason="", used_llm=True)

        if not resp.success:
            return RootCauseVerdict(classification="unknown", reason="", used_llm=True)

        data = _parse_json_object(resp.text)
        if data is None:
            return RootCauseVerdict(classification="unknown", reason="", used_llm=True)

        classification = data.get("classification")
        if classification not in ("causado_por_diff", "ambiental", "unknown"):
            return RootCauseVerdict(classification="unknown", reason="", used_llm=True)

        reason = str(data.get("reason") or "").strip()
        return RootCauseVerdict(classification=classification, reason=reason, used_llm=True)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Extrae el primer objeto JSON del texto del modelo. Tolerante a prosa
    alrededor; ``None`` si no parsea (fail-open aguas arriba, unknown)."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None
