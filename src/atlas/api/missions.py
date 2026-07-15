"""Mission Layer v0 (Foundry, ADR-069) — adapter ColdUpdate→Mission, receipt
determinista y radar proactivo.

Todo aquí es READ-ONLY y puro: funciones sobre dicts del ledger
(`atlas-cold-updates/proposals.json`). JAMÁS se instancia ColdUpdateManager
(su __init__ barre worktrees — efecto lateral de escritura) ni se ejecuta
nada: los `next_action` son comandos que un HUMANO correría (ADR-058).

Spec: docs/design/mission_layer_self_construction_spec.md
Contratos: schemas/mission.schema.json, schemas/mission_receipt.schema.json
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

__all__ = [
    "proposal_to_mission",
    "mission_receipt",
    "radar_findings",
    "missions_payload",
]

# ledger status → estado de misión (vocabulario del product contract).
# v0 solo afirma los estados que el ledger real puede demostrar.
_STATE_BY_STATUS: dict[str, str] = {
    "proposed": "plan_proposed",
    "validated": "awaiting_human_approval",
    "approved": "approved_pending_apply",
    "applied": "applied",
    "failed": "failed",
    "rejected": "rejected",
}

# comando CLI real que un humano correría a continuación (mismo mapa que
# `_NEXT_ACTION_BY_STATUS` del bridge; se repite aquí para que este módulo
# sea puro y sin dependencia del server).
_COMMAND_BY_STATUS: dict[str, str] = {
    "proposed": "atlas update validate {id}",
    "validated": "atlas update approve {id}",
    "approved": "atlas update apply {id}",
}

_VALID_RISKS = {"none", "low", "medium", "high", "critical"}

_STALE_AFTER = timedelta(hours=48)
_REPEATED_THRESHOLD = 3


def _mission_id(proposal_id: str) -> str:
    return f"msn_{proposal_id}"


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _evidence_refs(proposal: dict[str, Any]) -> list[str]:
    """Referencias comprobables reales — nunca prosa."""
    refs: list[str] = [f"ledger:{proposal.get('id', '?')}"]
    validation = proposal.get("validation")
    if isinstance(validation, dict):
        for key in ("pytest_exit", "mypy_exit"):
            if key in validation:
                refs.append(f"{key}={validation[key]}")
    for key in ("patch_path", "worktree_path"):
        value = proposal.get(key)
        if isinstance(value, str) and value:
            refs.append(f"{key}:{value}")
    return refs


def proposal_to_mission(
    proposal: dict[str, Any],
    files_touched: list[str] | None = None,
) -> dict[str, Any]:
    """Proyecta una propuesta real del ledger como AtlasMission (read-only)."""
    proposal_id = str(proposal.get("id", ""))
    status = str(proposal.get("status", ""))
    state = _STATE_BY_STATUS.get(status, "unknown")
    risk = proposal.get("risk")
    command_template = _COMMAND_BY_STATUS.get(status)
    next_action: dict[str, str] | None = None
    if command_template is not None:
        next_action = {
            "kind": "cli",
            "command": command_template.format(id=proposal_id),
            "actor": "human",
        }
    validation = proposal.get("validation")
    evidence = proposal.get("evidence")
    return {
        "mission_id": _mission_id(proposal_id),
        "intent": str(proposal.get("intent", "")) or "(sin intent)",
        "state": state,
        "risk": risk if risk in _VALID_RISKS else "unknown",
        "origin": str(proposal.get("origin", "unknown")),
        "source": {"kind": "cold_update_proposal", "ref": proposal_id},
        "created_at": proposal.get("created_at"),
        "updated_at": proposal.get("updated_at"),
        "artifacts": list(files_touched or []),
        "evidence_bundle": {
            "validation": validation if isinstance(validation, dict) else None,
            "evidence": evidence if isinstance(evidence, dict) else None,
            "refs": _evidence_refs(proposal),
        },
        "next_action": next_action,
        "human_action_required": next_action is not None,
        "gate": None,
        "model_use": [],
        "soul_invocations": [],
        "receipt_ref": f"rcp_{proposal_id}",
    }


_WHY_BY_RISK: dict[str, str] = {
    "none": "Cambio sin riesgo declarado sobre el propio Atlas.",
    "low": "Mejora de bajo riesgo que Atlas propone sobre sí mismo.",
    "medium": "Cambio de riesgo medio sobre el propio Atlas — merece revisión atenta.",
    "high": "Cambio de ALTO riesgo sobre el propio Atlas — revisar con cuidado antes de decidir.",
    "critical": "Cambio CRÍTICO sobre el propio Atlas — máxima atención humana.",
}


def mission_receipt(
    proposal: dict[str, Any],
    files_touched: list[str] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Receipt v0: determinista, generado SOLO de datos reales del ledger (sin
    LLM). Responde las 5 preguntas del contrato y declara honestamente qué
    falta. `verifiable=true` solo si hay validación real detrás."""
    proposal_id = str(proposal.get("id", ""))
    status = str(proposal.get("status", ""))
    intent = str(proposal.get("intent", "")) or "(sin intent)"
    origin = str(proposal.get("origin", "unknown"))
    risk = str(proposal.get("risk", "unknown"))
    state = _STATE_BY_STATUS.get(status, "unknown")
    raw_validation = proposal.get("validation")
    validation: dict[str, Any] | None = (
        raw_validation if isinstance(raw_validation, dict) and raw_validation
        else None
    )
    has_validation = validation is not None
    passed = bool(validation.get("passed")) if validation is not None else False

    what_happened = (
        f"El lazo de autoconstrucción ({origin}) propuso: {intent}. "
        f"Estado: {state}."
    )
    why = _WHY_BY_RISK.get(
        risk, f"Cambio con riesgo no clasificado ({risk}) sobre el propio Atlas."
    )

    did_parts = ["Creó una propuesta con patch en worktree aislado"]
    if files_touched:
        did_parts.append(f"toca {len(files_touched)} fichero(s): "
                         + ", ".join(files_touched[:5]))
    if validation is not None:
        verdict = "PASÓ" if passed else "FALLÓ"
        did_parts.append(
            "ejecutó la validación (pytest_exit="
            f"{validation.get('pytest_exit', '?')}, "
            f"mypy_exit={validation.get('mypy_exit', '?')}) y {verdict}"
        )
    what_atlas_did = "; ".join(did_parts) + "."

    if status == "validated":
        whats_missing = "Solo falta la decisión humana: aprobar o rechazar."
        decision = f"Aprobar o rechazar: atlas update approve {proposal_id}"
    elif status == "proposed" and not has_validation:
        whats_missing = ("Sin validación todavía: pytest/mypy no se han "
                         "ejecutado sobre el patch.")
        decision = f"Validar primero: atlas update validate {proposal_id}"
    elif status == "proposed":
        whats_missing = "Validación pendiente de re-ejecución o revisión."
        decision = f"Validar: atlas update validate {proposal_id}"
    elif status == "approved":
        whats_missing = "Aprobada pero sin aplicar todavía."
        decision = f"Aplicar: atlas update apply {proposal_id}"
    elif status in {"applied", "rejected", "failed"}:
        whats_missing = "Nada — la misión está cerrada."
        decision = f"Ninguna — misión cerrada ({state})."
    else:
        whats_missing = f"Estado desconocido en el ledger: {status!r}."
        decision = "Revisar el ledger a mano."

    generated = (now or datetime.now(timezone.utc)).isoformat()
    return {
        "receipt_id": f"rcp_{proposal_id}",
        "mission_id": _mission_id(proposal_id),
        "what_happened": what_happened,
        "why_it_matters": why,
        "what_atlas_did": what_atlas_did,
        "whats_missing": whats_missing,
        "decision_needed": decision,
        "evidence_refs": _evidence_refs(proposal),
        "verifiable": has_validation,
        "generated_at": generated,
    }


def _finding(
    detector: str,
    severity: str,
    summary: str,
    mission_ids: list[str],
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "detector": detector,
        "severity": severity,
        "summary": summary,
        "mission_ids": mission_ids,
        "evidence": evidence,
    }


def radar_findings(
    proposals: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Self-Build Radar (Foundry Fase D, primer corte): 4 detectores
    deterministas sobre el ledger real. Salidas graduadas: silent (no se
    emite) < radar (tarjeta informativa) < ask (decisión humana esperando)
    < gate (bloqueado por gate). Ningún detector actúa: solo señala."""
    moment = now or datetime.now(timezone.utc)
    findings: list[dict[str, Any]] = []

    # 1. RepeatedProposalDetector — mismo intent re-propuesto sin converger
    #    (caso real conocido: "Cablear el vault Obsidian…", ADR-068 Act. 2).
    by_intent: dict[str, list[dict[str, Any]]] = {}
    for p in proposals:
        by_intent.setdefault(str(p.get("intent", "")), []).append(p)
    for intent, group in by_intent.items():
        if len(group) < _REPEATED_THRESHOLD:
            continue
        if any(p.get("status") == "applied" for p in group):
            continue  # convergió: no es un bucle
        findings.append(_finding(
            "repeated_proposal",
            "radar",
            f"Intent re-propuesto {len(group)} veces sin converger: “{intent}”",
            [_mission_id(str(p.get("id", ""))) for p in group],
            [f"ledger:{p.get('id')}@{p.get('updated_at')}" for p in group],
        ))

    for p in proposals:
        status = str(p.get("status", ""))
        pid = str(p.get("id", ""))

        # 2. StaleProposalDetector — abierta sin movimiento > 48h.
        if status in {"proposed", "validated"}:
            updated = _parse_ts(p.get("updated_at"))
            if updated is not None and moment - updated > _STALE_AFTER:
                findings.append(_finding(
                    "stale_proposal",
                    "radar",
                    f"Propuesta {status} sin movimiento desde {p.get('updated_at')}: "
                    f"“{p.get('intent', '')}”",
                    [_mission_id(pid)],
                    [f"ledger:{pid}@{p.get('updated_at')}"],
                ))

        # 3. ValidationMissingDetector — propuesta sin validación ejecutada.
        if status == "proposed" and not p.get("validation"):
            findings.append(_finding(
                "validation_missing",
                "radar",
                f"Propuesta sin validación (pytest/mypy no ejecutados): "
                f"“{p.get('intent', '')}”",
                [_mission_id(pid)],
                [f"ledger:{pid}"],
            ))

        # 4. GatePendingDetector — validada, esperando decisión humana.
        if status == "validated":
            findings.append(_finding(
                "gate_pending",
                "ask",
                f"Validada y esperando decisión humana: “{p.get('intent', '')}”",
                [_mission_id(pid)],
                [f"ledger:{pid}", f"next:atlas update approve {pid}"],
            ))

    return findings


def missions_payload(
    proposals: list[dict[str, Any]],
    limit: int = 50,
) -> dict[str, Any]:
    """Payload de GET /missions: misiones adaptadas (activas primero, luego
    por updated_at desc) + agregados por estado/riesgo/origen."""
    missions = [proposal_to_mission(p) for p in proposals]
    # orden estable: updated_at desc primero, luego activas-primero (sort
    # estable de Python preserva el orden anterior dentro de cada grupo).
    missions.sort(key=lambda m: str(m.get("updated_at") or ""), reverse=True)
    missions.sort(key=lambda m: not m["human_action_required"])

    by_state = Counter(m["state"] for m in missions)
    by_risk = Counter(m["risk"] for m in missions)
    by_origin = Counter(m["origin"] for m in missions)
    return {
        "real": True,
        "total": len(missions),
        "by_state": dict(by_state),
        "by_risk": dict(by_risk),
        "by_origin": dict(by_origin),
        "missions": missions[: max(limit, 0)],
    }
