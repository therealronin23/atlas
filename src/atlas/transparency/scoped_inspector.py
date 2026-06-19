"""Inspector de contenido ACOTADO contra lista cerrada gobernada (OSM-028 nivel 3).

LÍMITES HONESTOS — leer antes de usar:

  Este módulo es un matcher determinista contra una lista cerrada gobernada.
  NO es un clasificador semántico, NO detecta intención y NO tiene cobertura
  universal.  Un atacante que reformule la instrucción evadirá todos los
  patrones (FALSOS NEGATIVOS por diseño).  El eje del mecanismo NO es
  detección perfecta: es producir una *causa registrada y auditable* cuando
  un patrón conocido aparece, de modo que la escalada quede en el log Merkle
  con atribución explícita (OSM-028 I2/I3).

  El inspector NUNCA retiene ni perfila el contenido inspeccionado.  La
  string `content` existe solo durante la llamada a `inspect()` y no se
  asigna a ningún atributo de la instancia.

Gobernanza:
  La lista de patrones la INYECTA el caller (gobernada/sancionada por el
  PDP — el inspector no la inventa).  `DEFAULT_ABUSE_PATTERNS` es un ejemplo
  mínimo; en producción el PDP mantiene la lista canónica.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.transparency.attestation import AttestedInspector


# ---------------------------------------------------------------------------
# Tipos de datos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AbusePattern:
    """Patrón de abuso: etiqueta + regex + descripción opcional.

    Attributes:
        label:       Categoría corta del patrón (p.ej. "jailbreak").
        pattern:     Expresión regular compilada con re.IGNORECASE.
        description: Descripción humano-legible (informativa, no normativa).
    """

    label: str
    pattern: str
    description: str = ""


@dataclass(frozen=True)
class InspectionResult:
    """Resultado de una inspección de contenido.

    Attributes:
        matched: True si al menos un patrón disparó.
        labels:  Tupla ordenada y sin duplicados de etiquetas que dispararon.
    """

    matched: bool
    labels: tuple[str, ...]


# ---------------------------------------------------------------------------
# Inspector principal
# ---------------------------------------------------------------------------


class ScopedInspector:
    """Inspector determinista contra una lista cerrada de patrones gobernada.

    La lista de patrones se inyecta en el constructor (no se crea internamente).
    Los regex se compilan una sola vez (re.IGNORECASE) para eficiencia.

    Si se inyecta un `attested_inspector`, se invoca su gating ANTES de cada
    inspección; si lanza `AttestationError`, ésta se propaga y no se inspecciona.
    """

    def __init__(
        self,
        patterns: tuple[AbusePattern, ...],
        *,
        attested_inspector: "AttestedInspector | None" = None,
    ) -> None:
        """
        Args:
            patterns:            Lista cerrada de patrones (gobernada por PDP).
            attested_inspector:  Gating de attestation opcional (OSM-025).
        """
        self._patterns = patterns
        self._attested_inspector = attested_inspector
        # Compilar una vez; re.IGNORECASE para cobertura de mayúsculas/minúsculas.
        self._compiled: tuple[tuple[AbusePattern, re.Pattern[str]], ...] = tuple(
            (p, re.compile(p.pattern, re.IGNORECASE)) for p in patterns
        )

    def inspect(self, content: str | bytes) -> InspectionResult:
        """Inspecciona `content` contra la lista cerrada de patrones.

        El contenido NO se almacena en ningún atributo (I3: sin retención).

        Args:
            content: Texto o bytes a inspeccionar.  Los bytes se decodifican
                     con utf-8, errors='replace'.

        Returns:
            InspectionResult con matched=True y las etiquetas disparadas si
            hay coincidencias; matched=False y labels=() en caso contrario.

        Raises:
            AttestationError: si `attested_inspector` está configurado y su
                              appraisal falla (propagada sin inspeccionar).
        """
        # Gating de attestation — si falla, propaga sin inspeccionar.
        if self._attested_inspector is not None:
            self._attested_inspector.inspect(None)  # gating: lanza AttestationError si falla

        # Decodificar bytes si es necesario; no retener la string resultante
        # más allá de esta llamada (no se asigna a self).
        text: str = (
            content if isinstance(content, str)
            else content.decode("utf-8", errors="replace")
        )

        fired: list[str] = []
        for abuse_pattern, compiled in self._compiled:
            if compiled.search(text):
                fired.append(abuse_pattern.label)

        # Ordenar y deduplicar etiquetas para resultado determinista.
        labels: tuple[str, ...] = tuple(sorted(set(fired)))
        return InspectionResult(matched=bool(labels), labels=labels)


# ---------------------------------------------------------------------------
# Lista cerrada de ejemplo — gobernada por PDP en producción
# ---------------------------------------------------------------------------

# NOTA: Esta lista es un EJEMPLO mínimo para ejercitar el mecanismo.
# En producción la lista canónica la mantiene y sanciona el PDP (Policy
# Decision Point).  Añadir o eliminar patrones sin revisión del PDP
# equivale a alterar la política de forma no auditada.

DEFAULT_ABUSE_PATTERNS: tuple[AbusePattern, ...] = (
    AbusePattern(
        label="jailbreak",
        pattern=r"ignore (all )?previous instructions",
        description="Intento de anular instrucciones del sistema.",
    ),
    AbusePattern(
        label="jailbreak",
        pattern=r"developer mode",
        description="Activación de modo no restringido ficticio.",
    ),
    AbusePattern(
        label="jailbreak",
        pattern=r"system prompt",
        description="Referencia directa al system prompt para manipularlo.",
    ),
    AbusePattern(
        label="override",
        pattern=r"disregard (all )?prior (instructions|rules|constraints)",
        description="Instrucción de ignorar restricciones previas.",
    ),
    AbusePattern(
        label="override",
        pattern=r"you (are|must) (now )?act as",
        description="Intento de redefinir el rol del modelo.",
    ),
    AbusePattern(
        label="exfiltration",
        pattern=r"exfiltrat",
        description="Término relacionado con exfiltración de datos.",
    ),
    AbusePattern(
        label="exfiltration",
        pattern=r"leak.*(key|secret|credential)",
        description="Solicitud de filtrar claves o credenciales.",
    ),
    AbusePattern(
        label="prompt_injection",
        pattern=r"<\s*inject\s*>",
        description="Marcador de inyección de prompt estructurada.",
    ),
)
