"""Etapa 1 de ADR-075 — pre-screen estático read-only de candidatos MCP remotos.

Sin descarga, sin ejecución (invariantes I1/I3/I6 del ADR). Cubre los 2111
candidatos sembrados por ``scripts/mcp_seed_registry.py`` a coste mínimo:

1. Heurística de tool-poisoning/prompt-injection sobre la descripción
   (``purpose``) — keyword-based, determinista, barata. Referencia: OWASP
   MCP03-2025 (Tool Poisoning), Invariant Labs ``mcp-scan``.
2. Routing por transporte (autocrítica ADR-075, 2026-07-24): 88.5% del
   catálogo es ``transport: http`` (servicio remoto alojado, sin fuente
   descargable) frente a 10.8% ``stdio`` (paquete local fetchable). Un
   transporte vacío/desconocido se trata como ``unknown`` — fail-closed,
   nunca se asume el camino más permisivo.

El YAML sembrado (fuente de verdad, regenerado por mcp_seed_registry.py)
NUNCA se muta aquí — esta etapa produce un reporte JSONL separado.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

from atlas.core.adversarial_panel import Severity

Track = Literal["stdio", "http", "unknown"]

# Objetivos sensibles: credenciales, secretos, ficheros que un agente honesto
# no necesita leer para "convertir divisas" o "listar pestañas". Coincide en
# espíritu con `_CREDENTIAL_KW` de SentinelGate pero es un detector DISTINTO:
# aquí se busca una instrucción dirigida al AGENTE, no la tool declarando su
# propia capacidad.
_SENSITIVE_TARGETS: tuple[str, ...] = (
    "ssh key", "id_rsa", "private key", "credential", "password", "api key",
    "api_key", ".env", "secret", "access token", "session token", "cookie",
    "browser history", "aws credentials", "keychain", "/etc/passwd",
)

# Lenguaje directivo dirigido al AGENTE (no al usuario humano que lee la
# descripción) -- la firma de un tool-poisoning/prompt-injection real.
_DIRECTIVE_PATTERNS: tuple[str, ...] = (
    "ignore all previous instructions", "ignore previous instructions",
    "disregard previous instructions", "reveal your system prompt",
    "reveal the system prompt", "do not mention this to the user",
    "do not tell the user", "without telling the user", "secretly",
    "before calling this tool, first", "before using this tool, first",
    "before responding, first",
)

# Directivo más débil (tool-shadowing: secuestrar la selección de tool) --
# real pero no concluyente en solitario.
_WEAK_DIRECTIVE_PATTERNS: tuple[str, ...] = (
    "you must always use this tool", "always use this tool instead",
    "you should always use this tool",
)


@dataclass(frozen=True)
class InjectionVerdict:
    severity: Severity
    reason: str


def scan_injection(purpose: str) -> InjectionVerdict:
    """Heurística keyword sobre la descripción. Fail-closed: texto vacío o
    ambiguo nunca se trata como "limpio" (MINOR como mínimo)."""
    text = (purpose or "").strip().lower()
    if not text:
        return InjectionVerdict(Severity.MINOR, "descripción vacía/ausente -- ambiguo, no se asume limpio")

    hit_sensitive = next((t for t in _SENSITIVE_TARGETS if t in text), None)
    hit_directive = next((p for p in _DIRECTIVE_PATTERNS if p in text), None)

    # MAJOR solo por CO-OCURRENCIA: instrucción dirigida al agente + objetivo
    # sensible. Un objetivo sensible EN SOLITARIO (ej. "gestiona tus API keys")
    # es el uso legítimo normal de un MCP de gestión de credenciales -- tratarlo
    # como MAJOR sin más produce falsos positivos masivos (medido en el
    # catálogo real: 43/43 flags eran justo esto). Queda como MINOR, para la
    # pasada semántica/juez opcional de ADR-075, no como auto-rechazo aquí.
    if hit_directive and hit_sensitive:
        return InjectionVerdict(
            Severity.MAJOR,
            f"instrucción dirigida al agente ({hit_directive!r}) + objetivo sensible ({hit_sensitive!r})",
        )
    if hit_directive:
        return InjectionVerdict(Severity.MAJOR, f"instrucción dirigida al agente: {hit_directive!r}")
    if hit_sensitive:
        return InjectionVerdict(
            Severity.MINOR,
            f"objetivo sensible mencionado en solitario (sin instrucción dirigida): {hit_sensitive!r}",
        )

    hit_weak = next((p for p in _WEAK_DIRECTIVE_PATTERNS if p in text), None)
    if hit_weak:
        return InjectionVerdict(Severity.MINOR, f"lenguaje directivo de tool-shadowing: {hit_weak!r}")

    return InjectionVerdict(Severity.NONE, "sin patrones conocidos")


def route_track(transport: str) -> Track:
    """Fail-closed (I6): transporte vacío/desconocido -> "unknown", nunca se
    asume el camino stdio (que habilita fetch+ejecución local)."""
    t = (transport or "").strip().lower()
    if t == "stdio":
        return "stdio"
    if t == "http":
        return "http"
    return "unknown"


@dataclass(frozen=True)
class TriageResult:
    name: str
    track: Track
    injection_severity: Severity
    injection_reason: str
    eligible: bool
    next_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "track": self.track,
            "injection_severity": self.injection_severity.name,
            "injection_reason": self.injection_reason,
            "eligible": self.eligible,
            "next_status": self.next_status,
        }


def triage_candidate(entry: dict[str, Any]) -> TriageResult:
    track = route_track(str(entry.get("transport", "")))
    verdict = scan_injection(str(entry.get("purpose", "")))
    # Elegible para promoción (candidato -> metadata-cleared) solo si el
    # transporte es conocido (stdio/http, no unknown) Y la inyección no pasa
    # de MINOR. MAJOR/BLOCKING o track ambiguo -> pending_review (I6).
    eligible = track != "unknown" and verdict.severity < Severity.MAJOR
    return TriageResult(
        name=str(entry.get("name", "")),
        track=track,
        injection_severity=verdict.severity,
        injection_reason=verdict.reason,
        eligible=eligible,
        next_status="metadata-cleared" if eligible else "pending_review",
    )


def triage_catalog(entries: list[dict[str, Any]]) -> list[TriageResult]:
    return [triage_candidate(e) for e in entries]


def _iter_seeded_entries(seeded_path: Path) -> list[dict[str, Any]]:
    doc = yaml.safe_load(seeded_path.read_text(encoding="utf-8")) or {}
    entries: list[dict[str, Any]] = []
    for sector in (doc.get("sectors") or {}).values():
        entries.extend(sector.get("entries") or [])
    return entries


def run_stage1_triage(seeded_path: str | Path, report_path: str | Path) -> dict[str, int]:
    """Lee el catálogo sembrado (read-only, NUNCA lo muta), corre la etapa 1
    sobre todos los candidatos y escribe un reporte JSONL (una línea por
    candidato, snapshot completo -- sobrescribe el reporte previo, no un log
    incremental). Devuelve un resumen de conteos."""
    seeded = Path(seeded_path)
    if not seeded.is_file():
        raise FileNotFoundError(f"catálogo sembrado no encontrado: {seeded}")

    entries = _iter_seeded_entries(seeded)
    results = triage_catalog(entries)

    out = Path(report_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    snapshot = [r.to_dict() for r in results]
    if out.is_file():
        try:
            prior = [
                {key: value for key, value in json.loads(line).items() if key != "generated_at"}
                for line in out.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, ValueError, TypeError):
            prior = []
        if prior == snapshot:
            return {
                "total": len(results),
                "eligible": sum(1 for r in results if r.eligible),
                "pending_review": sum(1 for r in results if not r.eligible),
                "track_stdio": sum(1 for r in results if r.track == "stdio"),
                "track_http": sum(1 for r in results if r.track == "http"),
                "track_unknown": sum(1 for r in results if r.track == "unknown"),
                "injection_major_or_worse": sum(
                    1 for r in results if r.injection_severity >= Severity.MAJOR
                ),
            }
    generated_at = datetime.now(timezone.utc).isoformat()
    with out.open("w", encoding="utf-8") as f:
        for row in snapshot:
            line = {"generated_at": generated_at, **row}
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    return {
        "total": len(results),
        "eligible": sum(1 for r in results if r.eligible),
        "pending_review": sum(1 for r in results if not r.eligible),
        "track_stdio": sum(1 for r in results if r.track == "stdio"),
        "track_http": sum(1 for r in results if r.track == "http"),
        "track_unknown": sum(1 for r in results if r.track == "unknown"),
        "injection_major_or_worse": sum(1 for r in results if r.injection_severity >= Severity.MAJOR),
    }
