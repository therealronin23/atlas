"""Cónclave real (C.1, ADR-076) sobre la enmienda de auto-adopción MCP.

No es una feature aditiva: ADR-075 tiene dos invariantes aceptados el mismo
día que la petición de auto-adopción contradice directamente (I5: "nunca
auto-aprobación masiva"; I2-R: techo de confianza permanentemente bajo para
la pista http). Este script convoca el trío REAL (mismo patrón que
scripts/council_smoke.py) con el contexto exacto que el plan especifica --
la pregunta se plantea SIN prejuzgar el resultado.

    PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- \
      .venv/bin/python scripts/council_mcp_auto_adopt_adr076.py
"""

from __future__ import annotations

import json
from pathlib import Path

from atlas.core.deliberation_council import build_trio_reviewers, convene_for_decision
from atlas.router.cascade import Difficulty

_DECISION = (
    "¿mcp_auto_adopt_prevetted (adopción de servers MCP que ya pasaron TODO el "
    "pipeline de vetting de ADR-075: lookup + descarga verificada + extracción "
    "segura + entry point + análisis estático limpio) debería MANTENER "
    "sensitivity=\"high\" -- lo que significa que sigue exigiendo un clic humano "
    "explícito, pero ahora con todo el escaneo automático ya hecho de antemano --"
    " o hace falta BAJARLA para permitir adopción sin intervención humana en "
    "absoluto? Bajarla contradice la regla constitucional #4 de AGENTS.md "
    "(\"sensitivity=high SIEMPRE fuerza aprobación, con independencia del "
    "patrón\") tal como está escrita hoy."
)

_CONTEXT = """\
ANTECEDENTE DIRECTO (mismo día, mismo repo): un Cónclave real ya convocado hoy
sobre este pipeline forzó el diseño vigente con una objeción MAJOR sustantiva
(Gemini + GLM convergieron independientemente, Mistral EU no disponible ese
turno): "el pipeline usaba aislamiento de RED como si mitigara un ataque
SEMÁNTICO (tool-poisoning); no lo hace -- un MCP ofuscado que pasa el escaneo
de metadatos entra al sandbox, y el LLM actúa como canal encubierto sin
necesitar egress de red." Esa corrección añadió los invariantes I2/I3 que hoy
son parte aceptada de ADR-075.

INVARIANTES ACEPTADOS DE ADR-075 (Aceptado, 2026-07-24) QUE ESTA PREGUNTA
PONE EN TENSIÓN -- citados VERBATIM:

> I5 · admisión HITL por lotes vía el Decider A3 + receipt Merkle; activación
> reversible (A3.3). Cero auto-adopción de tipos remotos ejecutables.
> [sección "Decisión — invariantes no negociables"]

> 5. Aprobación HITL por lotes vía Decider A3 + receipt Merkle; activación
> reversible (A3.3). Nunca auto-aprobación masiva.
> [sección "Pipeline por etapas", paso 5]

> I2-R · para la pista remota (http, 1869 candidatos): admisión basada 100% en
> comportamiento observado + IOC, nunca en "hemos visto el código". Riesgo
> residual reconocido, no oculto (ver Consecuencias).
> [sección "Decisión — invariantes no negociables"]

CÓDIGO REAL VERIFICADO HOY (no de memoria): Orchestrator.adopt_mcp_server
(src/atlas/core/orchestrator.py:318) declara sensitivity="high"; tanto
HumanDecider (src/atlas/core/decider/human_decider.py:32-33) como
AutonomousDecider (src/atlas/core/decider/autonomous_decider.py:93-94, "regla
constitucional #4" de AGENTS.md) fuerzan RequiresHuman/Deny sin excepción para
sensitivity="high". Hoy no existe ningún camino de auto-adopción condicional
-- se propone uno nuevo (adopt_mcp_server_prevetted, kind distinto,
NO se toca adopt_mcp_server), gateado detrás de un flag opt-in
(ATLAS_MCP_AUTO_ADOPT=1, default apagado) y de un criterio estricto de
"limpio" (completed=True, stage_reached="static_scan", worst_severity=NONE,
entrypoint_module no vacío -- implica hash verificado + sin path-traversal,
porque un fallo en esos pasos hubiera detenido stage_reached antes).

CANDIDATO A DECISIÓN ADICIONAL (a validar, no zanjado aquí): excluir la pista
http de cualquier auto-adopción en esta fase. run_stage2b_http SOLO confirma
que el handshake de protocolo responde y cuenta tools -- tool_count>0 es señal
de CONECTIVIDAD, no de seguridad, y I2-R ya establece que ahí no hay fuente de
código que analizar (es exactamente el tipo de riesgo que I2-R reconoce como
residual y permanente). Si el veredicto considera que http NUNCA debería
auto-adoptarse aunque stdio sí, indicarlo explícitamente.

LA PREGUNTA NO ESTÁ PREJUZGADA: no se asume que el veredicto será aprobar ni
rechazar. Si hay objeción sustantiva (MAJOR/BLOCKING) de cualquier voz, o el
panel da FAIL/UNKNOWN por falta de diversidad real, la sección C completa del
plan (implementación de auto-adopción) se queda SIN CONSTRUIR -- el flag
ATLAS_MCP_AUTO_ADOPT se deja hardcodeado a False citando este veredicto, y
ADR-076 se redacta como "Propuesto, C bloqueado por el Cónclave", no
"Aceptado"."""


def main() -> None:
    trio = build_trio_reviewers()
    print(f"trío ensamblado: {[r.provider for r in trio]}")

    ev = convene_for_decision(
        _DECISION,
        context=_CONTEXT,
        difficulty=Difficulty.HARD,
        risk="high",
        irreversible=True,
        reviewers=trio,
    )

    if ev is None:
        print("\nGATING: should_convene() devolvió False -- no debería pasar con "
              "irreversible=True, pero si ocurre, C queda sin implementar (fail-closed).")
        return

    print(f"\nVEREDICTO: {ev.verdict.name}")
    if ev.reason:
        print(f"razón: {ev.reason}")
    print("\nvoces (desacuerdo crudo, ANTES de síntesis):")
    for c in ev.checks:
        estado = "PASS" if c.passed else "OBJETA"
        print(f"  - {c.name}: {estado}\n    {c.detail}")

    # Persistir el veredicto completo para pegarlo tal cual en ADR-076 --
    # mismo espíritu que el receipt Merkle: la decisión de gobernanza queda
    # trazable, no solo en la salida de esta terminal.
    out = Path("workspace/mcp/council_verdict_adr076.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "verdict": ev.verdict.name,
        "reason": ev.reason,
        "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in ev.checks],
        "reviewers": [r.provider for r in trio],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nveredicto persistido en {out}")


if __name__ == "__main__":
    main()
