"""Cónclave real de revisión de diseño (ADR-077) -- Security Council Gate.

A diferencia de scripts/council_mcp_auto_adopt_adr076.py (que pedía un
veredicto binario sobre una enmienda a un invariante), esto pide una
REVISIÓN para mejorar el diseño antes de implementar -- el operador ya
decidió construirlo; el Cónclave debe presionar puntos ciegos concretos,
no aprobar/rechazar la idea en abstracto.

    PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- \
      .venv/bin/python scripts/council_adr077_design_review.py
"""

from __future__ import annotations

import json
from pathlib import Path

from atlas.core.deliberation_council import build_trio_reviewers, convene_for_decision
from atlas.router.cascade import Difficulty

_DECISION = (
    "Revisar y mejorar (no aprobar/rechazar en abstracto) el diseño de ADR-077: "
    "un 'Security Council Gate' genérico que se antepone al Decider existente "
    "(Human/Autonomous) para cualquier DecisionAction.kind marcado como "
    "'security-gateable'. Mecanismo: escaneo automatizado (reusa semgrep/CWE-"
    "audit/IOC checks ya existentes) + UN auditor LLM barato (no el trío de "
    "Cónclave, reservado para decisiones ADR/irreversibles) -> veredicto "
    "clean|flagged. clean sigue el camino de hoy sin cambios. flagged genera "
    "un informe estructurado (severidad/checks/disparador/acción recomendada), "
    "escribe un rechazo PERMANENTE keyed por action_hash (no se reintenta ni "
    "se re-escala ese mismo action_hash nunca más), y dispara la maquinaria de "
    "aprobación humana existente (Task.AWAITING_APPROVAL/EventType."
    "APPROVAL_REQUIRED/_persist_pending_approval) de forma independiente del "
    "valor de ATLAS_DECIDER."
)

_CONTEXT = """\
POR QUÉ EXISTE ESTE DISEÑO (hallazgos verificados hoy, no hipotéticos):

1. ATLAS_DECIDER=autonomous está activo en el proceso de producción real
   (confirmado leyendo /proc/<pid>/environ del PID vivo de atlas-core.service,
   no solo el .env en disco) desde al menos 2026-07-15.
2. AutonomousDecider (src/atlas/core/decider/autonomous_decider.py) SOLO
   devuelve Allow o Deny -- nunca RequiresHuman. Verificado contra el log
   Merkle real: la vía de cola de aprobación humana (acción "task.routed")
   tiene 2 entradas, ambas de mayo de 2026. El seam autónomo (acción
   "decider.verdict") tiene 603 entradas, la última del mismo día de hoy
   (534 allow / 69 deny). La maquinaria de aprobación humana existe, está
   probada, y lleva meses sin ejecutarse ni una vez.
3. Un bump de dependencia (cold_update_apply, risk="normal") se auto-aplicó
   dos veces hoy sin intervención humana -- reversible=True + sensitivity
   distinto de "high" pasa de largo bajo AutonomousDecider.
4. mcp_adopt contra "ai.adeu/adeu" (candidato YA marcado con hallazgo MAJOR
   de semgrep real en ADR-075) se reintentó 6 veces en un solo día -- se
   deniega correctamente cada vez por la regla constitucional #4, pero nada
   recuerda "esto ya se evaluó y se rechazó, no lo reintentes".

QUÉ NO CAMBIA (verificar que el diseño respeta esto de verdad, no solo en
la intención):

- La regla constitucional #4 (AGENTS.md): sensitivity="high" SIEMPRE fuerza
  deny/require, con independencia del patrón. El gate propuesto es una
  etapa ANTERIOR al Decider existente -- no debería poder, ni por diseño ni
  por accidente de implementación, hacer que un sensitivity="high" termine
  en Allow.
- ADR-076 C (auto-adopción MCP sin clic humano) sigue bloqueado por un
  Cónclave real que dio FAIL 3/3 (BLOCKING+MAJOR+MAJOR) hace unas horas.
  Este gate NO debe convertirse en una puerta trasera hacia eso -- pasar
  el gate (clean) no debe, por sí solo, habilitar auto-adopción de nada.

DISEÑO PROPUESTO EN DETALLE:

- Registro por `kind` (mcp_adopt, cold_update_apply, offensive_action,
  omega_exec para empezar) -- no hardcodeado a MCP.
- Escaneo automatizado reusa piezas existentes por dominio (semgrep para
  MCP stdio, CWE-audit para parches de código, IOC/credential checks que
  ya viven dentro de autonomous_decider.py).
- Auditor LLM: UNA sola llamada hostil en hub plano, barata -- explícitamente
  DISTINTO del trío de deliberation_council (ese sigue reservado para
  decisiones ADR/irreversibles vía should_convene).
- flagged -> SecurityReport (severidad NONE/MINOR/MAJOR/BLOCKING, checks_run,
  triggered_by, recommended_action) + registro de rechazo permanente
  (workspace/security_council/rejected.jsonl, keyed por action_hash, mismo
  patrón que classify_stage2_status/terminal de ADR-076 B.2) + escalada real
  vía Task.AWAITING_APPROVAL, independiente de ATLAS_DECIDER.

PREGUNTAS ABIERTAS QUE EL PANEL DEBE PRESIONAR (no exhaustivo, sugerido):

- ¿Un auditor LLM de una sola voz es suficiente para decidir "flagged" vs
  "clean", o necesita algún tipo de segunda opinión/umbral para casos
  ambiguos (equivalente al MINOR de hoy que va a pending_review, no
  auto-descartado)?
- ¿Qué pasa si el auditor LLM o el escaneo automatizado FALLA (timeout,
  proveedor caído, excepción no anticipada) -- el diseño debe decir
  explícitamente si eso es fail-open (clean por defecto, peligroso) o
  fail-closed (flagged por defecto, más ruido pero más seguro)? El ADR no
  lo especifica hoy.
- El "rechazo permanente" por action_hash -- ¿action_hash captura lo
  suficiente para que dos intentos legítimamente distintos (ej. un parche
  de dependencia con una versión nueva y más limpia) no queden bloqueados
  para siempre por el hash de un intento anterior con datos parecidos?
  ¿Cómo se revisa/revoca un rechazo permanente si resulta ser un falso
  positivo?
- ¿El "informe" que se le da al humano es accionable de verdad, o es
  otro JSONL más que nadie mira (el mismo problema que ya existe hoy con
  pending_review.jsonl de MCP, que probablemente tampoco se revisa)?
- ¿Aplicar este gate a offensive_action/omega_exec tiene el mismo perfil de
  riesgo que aplicarlo a mcp_adopt, o necesita matices por kind (ej. omega_exec
  ya tiene snapshot+undo real, offensive_action puede tener consecuencias
  externas irreversibles incluso "contained")?

No se pide un veredicto binario aprobar/rechazar la idea -- se pide qué
cambiaría el panel del diseño ANTES de la primera línea de código, y si hay
algún punto BLOCKING que impida empezar a implementar tal cual está escrito."""


def main() -> None:
    trio = build_trio_reviewers()
    print(f"trío ensamblado: {[r.provider for r in trio]}")

    ev = convene_for_decision(
        _DECISION,
        context=_CONTEXT,
        difficulty=Difficulty.HARD,
        risk="moderate",
        irreversible=False,
        reviewers=trio,
    )

    if ev is None:
        print("\nGATING: should_convene() devolvió False -- no debería pasar con "
              "difficulty=HARD, pero si ocurre, se procede sin revisión (registrar por qué).")
        return

    print(f"\nVEREDICTO: {ev.verdict.name}")
    if ev.reason:
        print(f"razón: {ev.reason}")
    print("\nvoces (desacuerdo crudo, ANTES de síntesis):")
    for c in ev.checks:
        estado = "PASS" if c.passed else "OBJETA"
        print(f"  - {c.name}: {estado}\n    {c.detail}")

    out = Path("workspace/mcp/council_verdict_adr077_design_review.json")
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
