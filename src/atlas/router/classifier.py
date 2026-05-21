"""
Atlas Core — Router y Clasificador
Clasificador rule-based deterministico (v0.1).
No usa LLM. Decide el nivel de routing segun patrones en orden de prioridad.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from atlas.core.contracts import RoutingLevel
from atlas.governance.governance_l0 import GovernanceL0


# ---------------------------------------------------------------------------
# Patrones de clasificacion (orden de evaluacion importa)
# ---------------------------------------------------------------------------

# 1. Patrones de governance → siempre BLOCKED
GOVERNANCE_PATTERNS: list[str] = [
    r"rm\s+-rf\s*/",
    r"\bsudo\b",
    r"chmod\s+777",
    r"\.\.([/\\]\.\.)+",          # Path traversal
    r"governance\.json",
    r"merkle.{0,20}(disable|deshabilit)",
    r"ast.{0,10}guard.{0,20}(disable|deshabilit)",
    r"sandbox.{0,20}(disable|deshabilit)",
    r"__import__\s*\(",
    r"eval\s*\(",
    r"exec\s*\(",
]

# 2. Patrones de aprobacion → REQUIRES_APPROVAL
APPROVAL_PATTERNS: list[str] = [
    r"\b(elimina|borra|delete|remove|drop)\b",
    r"\bgit\s+push\b",
    r"\bgit\s+reset\b",
    r"\bgit\s+rebase\b",
    r"\binstala(r)?\b|\binstall\b",
    r"\bformatea(r)?\b|\bformat\b",
    r"\bdesinstala(r)?\b|\buninstall\b",
]

# 3. Patrones de delegacion → DELEGATE_HERMES
HERMES_PATTERNS: list[str] = [
    r"(cuando|mientras)\s+(yo\s+)?(no\s+est[eé]|duerm[ao]|est[eé]\s+fuera)",
    r"\bscrape\b|\bscraping\b",
    r"webhook",
    r"api\s+externa",
    r"disponible\s+(24|siempre)",
    r"monitoriza(r)?.{0,30}(servidor|site|endpoint)",
    r"avisa(r?)?\s+(por\s+)?telegram",
    r"recordatorio\s+programado",
]

# 4. Patrones deterministicos → DETERMINISTIC_TOOL (L-det, sin LLM)
DETERMINISTIC_PATTERNS: list[str] = [
    r"(lee|leer|muestra|abre)\s+el\s+(archivo|fichero|file)",
    r"read\s+file",
    r"\bgit\s+(status|log|diff)\b",
    r"(busca|buscar|search).{0,30}(workspace|proyecto|directorio)",
    r"(lista|listar|list)\s+(los\s+)?(archivos|ficheros|files|directorios)",
    r"\batlas\s+status\b",
    r"\bestado\s+de\s+atlas\b",
    r"\bmemoria\s+de\s+atlas\b",
    r"\baudit\s+log\b",
    r"ripgrep|agentgrep",
    r"\bgit\s+log\b",
]


# ---------------------------------------------------------------------------
# Resultado de clasificacion
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClassificationResult:
    level: RoutingLevel
    confidence: float          # 0.0-1.0 (1.0 = regla determinista disparada)
    matched_pattern: str | None
    governance_blocked: bool
    reason: str


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class Classifier:
    """
    Clasificador deterministico de intenciones.
    Evalua patrones en orden de prioridad.
    """

    def __init__(self) -> None:
        self._gov_patterns   = [re.compile(p, re.IGNORECASE) for p in GOVERNANCE_PATTERNS]
        self._approval_pats  = [re.compile(p, re.IGNORECASE) for p in APPROVAL_PATTERNS]
        self._hermes_pats    = [re.compile(p, re.IGNORECASE) for p in HERMES_PATTERNS]
        self._det_pats       = [re.compile(p, re.IGNORECASE) for p in DETERMINISTIC_PATTERNS]

    def classify(self, intent: str, sensitivity: str = "low") -> ClassificationResult:
        # 0. Sensitivity override — antes de cualquier patron
        # Tarea marcada alta sensibilidad → siempre confirmacion, aunque sea L-det
        if sensitivity == "high":
            return ClassificationResult(
                level=RoutingLevel.REQUIRES_APPROVAL,
                confidence=1.0,
                matched_pattern="sensitivity:high",
                governance_blocked=False,
                reason="Tarea marcada como alta sensibilidad → confirmacion requerida siempre.",
            )

        # 1. Verificar Governance L0 primero
        try:
            gov = GovernanceL0.get_instance()
            violation = gov.evaluate(intent)
            if violation:
                return ClassificationResult(
                    level=RoutingLevel.BLOCKED,
                    confidence=1.0,
                    matched_pattern=violation.pattern,
                    governance_blocked=True,
                    reason=f"[Governance L0] {violation.hard_block}",
                )
        except RuntimeError:
            pass  # Governance no inicializado aun (tests unitarios del router)

        # 1. Patrones de governance propios del classifier
        for pat in self._gov_patterns:
            m = pat.search(intent)
            if m:
                return ClassificationResult(
                    level=RoutingLevel.BLOCKED,
                    confidence=1.0,
                    matched_pattern=pat.pattern,
                    governance_blocked=True,
                    reason=f"Patron de bloqueo absoluto detectado: '{m.group()}'",
                )

        # 2. Patrones de aprobacion
        for pat in self._approval_pats:
            m = pat.search(intent)
            if m:
                return ClassificationResult(
                    level=RoutingLevel.REQUIRES_APPROVAL,
                    confidence=1.0,
                    matched_pattern=pat.pattern,
                    governance_blocked=False,
                    reason=f"Accion de alto riesgo detectada: '{m.group()}'",
                )

        # 3. Patrones de delegacion
        for pat in self._hermes_pats:
            m = pat.search(intent)
            if m:
                return ClassificationResult(
                    level=RoutingLevel.DELEGATE_HERMES,
                    confidence=1.0,
                    matched_pattern=pat.pattern,
                    governance_blocked=False,
                    reason=f"Tarea para Hermes-VPS: '{m.group()}'",
                )

        # 4. Patrones deterministicos
        for pat in self._det_pats:
            m = pat.search(intent)
            if m:
                return ClassificationResult(
                    level=RoutingLevel.DETERMINISTIC_TOOL,
                    confidence=1.0,
                    matched_pattern=pat.pattern,
                    governance_blocked=False,
                    reason=f"Herramienta deterministica identificada: '{m.group()}'",
                )

        # 5. Default → LOCAL_SAFE
        return ClassificationResult(
            level=RoutingLevel.LOCAL_SAFE,
            confidence=0.6,
            matched_pattern=None,
            governance_blocked=False,
            reason="Sin patron especifico. Clasificado como tarea local segura.",
        )
