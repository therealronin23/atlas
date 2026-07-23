"""PolicyEngine — determinista, fail-closed, sin juicio LLM (D14, ADR-060).

Capas de evaluación, en orden:
  1. Invariantes DUROS en código (no relajables borrando fixtures — P15-R2).
  2. Reglas de fixture (fixtures/security/policies.json), solo si enabled.
  3. Spec de la capacidad (gate_required → gate).
  4. Default fail-closed: lectura de bajo riesgo → allow; el resto → gate.

El modelo NUNCA es frontera de seguridad: provenance de contenido externo
no confiable se deniega por contrato, no por heurística.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from atlas.events.emit import emit_event
from atlas.events.schemas import EventStatus, Risk
from atlas.events.store import OsEventStore
from atlas.fabric.capabilities import get_capability, is_read_capability
from atlas.fabric.models import (
    DataClass,
    PolicyAppliesTo,
    PolicyEffect,
    PolicyRule,
    RouteType,
    UnlessCondition,
)

if TYPE_CHECKING:
    # fabric es capa inferior a api: importar atlas.api.models a nivel de
    # módulo dispara atlas/api/__init__ → server → product_routes →
    # fabric.concierge → fabric.policy (ciclo). Solo tipo; en runtime se
    # importa perezosamente dentro de load_gates().
    from atlas.api.models import GateSpec

_DATA_SEVERITY: dict[DataClass, int] = {
    DataClass.PUBLIC: 0,
    DataClass.INTERNAL: 1,
    DataClass.PERSONAL: 2,
    DataClass.SENSITIVE: 3,
    DataClass.CREDENTIALS: 4,
}

_RISK_SEVERITY: dict[Risk, int] = {
    Risk.NONE: 0, Risk.LOW: 1, Risk.MEDIUM: 2, Risk.HIGH: 3, Risk.CRITICAL: 4,
}


class SourceTrust(str, Enum):
    """De dónde viene la orden. Contenido externo JAMÁS ordena acciones."""

    USER = "user"
    ATLAS = "atlas"
    EXTERNAL_CONTENT = "external_content"


class PolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: str
    connector_id: str | None = None
    data_class: DataClass | None = None
    route: RouteType | None = None
    provenance: SourceTrust = SourceTrust.USER
    approvals: list[UnlessCondition] = Field(default_factory=list)
    personal_channel: bool = False


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["allow", "deny", "require_gate"]
    capability: str
    risk: Risk
    reason: str
    policy_id: str | None = None
    gate_id: str | None = None
    hard: bool = False
    simulated: bool = True


def _hard(policy_id: str, description: str, applies: PolicyAppliesTo,
          effect: PolicyEffect, unless: list[UnlessCondition]) -> PolicyRule:
    return PolicyRule(
        policy_id=policy_id, description=description, applies_to=applies,
        effect=effect, unless=unless, hard=True, enabled=True,
    )


# Invariantes constitucionales. Replicados como fixture SOLO para visibilidad;
# esta lista es la autoridad ejecutable.
HARD_RULES: list[PolicyRule] = [
    _hard("pol_hard_untrusted_provenance",
          "Contenido externo no confiable jamás dispara acciones",
          PolicyAppliesTo(), PolicyEffect.DENY, []),
    # pol_hard_personal_channel_send: NO vive aquí como PolicyRule de
    # applies_to (por connector_id) — sería evadible renombrando el
    # connector_id. Es un chequeo directo en código en _evaluate(), igual
    # que la provenance no confiable arriba: matchea por el campo
    # estructural PolicyRequest.personal_channel, no por convención de
    # nombre.
    _hard("pol_hard_cloud_sensitive",
          "Datos sensibles/credenciales no van a cloud sin aprobación humana",
          PolicyAppliesTo(capabilities=["model.cloud_call"],
                          data_classes=[DataClass.SENSITIVE,
                                        DataClass.CREDENTIALS]),
          PolicyEffect.DENY, [UnlessCondition.HUMAN_APPROVED]),
    _hard("pol_hard_certificate",
          "Certificado digital: nunca silencioso",
          PolicyAppliesTo(capabilities=["certificate.use"]),
          PolicyEffect.DENY,
          [UnlessCondition.HUMAN_APPROVED, UnlessCondition.GATE_APPROVED]),
    _hard("pol_hard_official_submit",
          "Presentación oficial siempre con ceremonia de gate",
          PolicyAppliesTo(capabilities=["official.submit"]),
          PolicyEffect.REQUIRE_GATE, [UnlessCondition.GATE_APPROVED]),
    _hard("pol_hard_accounting_write",
          "Escritura contable real siempre gateada",
          PolicyAppliesTo(capabilities=["erp.accounting.write"]),
          PolicyEffect.REQUIRE_GATE, [UnlessCondition.GATE_APPROVED]),
    _hard("pol_hard_computer_use",
          "Computer-use: último recurso, sesión visible, gate",
          PolicyAppliesTo(capabilities=["computer_use.execute"]),
          PolicyEffect.REQUIRE_GATE, [UnlessCondition.GATE_APPROVED]),
]


def _matches(rule: PolicyRule, req: PolicyRequest,
             effective_class: DataClass) -> bool:
    at = rule.applies_to
    if at.capabilities:
        ok = any(
            req.capability == pat
            or (pat.endswith("*") and req.capability.startswith(pat[:-1]))
            for pat in at.capabilities
        )
        if not ok:
            return False
    if at.connectors:
        conn = req.connector_id or ""
        ok = any(
            conn == pat or (pat.endswith("*") and conn.startswith(pat[:-1]))
            for pat in at.connectors
        )
        if not ok:
            return False
    if at.data_classes and effective_class not in at.data_classes:
        return False
    if at.routes:
        if req.route is None or req.route.value not in at.routes:
            return False
    return True


class PolicyEngine:
    """Evalúa PolicyRequest → PolicyDecision. Sin red, sin LLM, sin estado."""

    def __init__(
        self,
        rules_path: Path | None = None,
        gates: list[GateSpec] | None = None,
        store: OsEventStore | None = None,
        *,
        simulated: bool = True,
    ) -> None:
        self._soft_rules: list[PolicyRule] = []
        if rules_path is not None and rules_path.exists():
            raw = json.loads(rules_path.read_text(encoding="utf-8"))
            self._soft_rules = [PolicyRule.model_validate(r) for r in raw]
        self._gates = {g.gate_id: g for g in (gates or [])}
        self._store = store
        # T1: si los gates vienen de la governance real (config/governance/
        # gates.json) en vez del fixture, el llamador pasa simulated=False —
        # se propaga a toda PolicyDecision devuelta (ver evaluate()).
        self._simulated = simulated

    @property
    def hard_rules(self) -> list[PolicyRule]:
        return list(HARD_RULES)

    @property
    def soft_rules(self) -> list[PolicyRule]:
        return list(self._soft_rules)

    def evaluate(self, req: PolicyRequest) -> PolicyDecision:
        decision = self._evaluate(req)
        # Un único punto de verdad para `simulated`, sin importar qué rama
        # interna (invariante duro, regla blanda, spec de capacidad, default
        # fail-closed) construyó la decisión.
        if decision.simulated != self._simulated:
            decision = decision.model_copy(update={"simulated": self._simulated})
        if self._store is not None:
            emit_event(
                self._store,
                "policy.evaluated",
                f"{req.capability} → {decision.decision}",
                actor="governance",
                source="atlas.fabric.policy",
                risk=decision.risk,
                status=EventStatus.WAITING_USER
                if decision.decision == "require_gate"
                else EventStatus.COMPLETED,
                payload={"request": req.model_dump(mode="json"),
                         "decision": decision.model_dump(mode="json")},
            )
        return decision

    # -- internals ----------------------------------------------------------

    def _evaluate(self, req: PolicyRequest) -> PolicyDecision:
        spec = get_capability(req.capability)
        if spec is None:
            return PolicyDecision(
                decision="deny", capability=req.capability, risk=Risk.HIGH,
                reason="capacidad desconocida: fail-closed",
                policy_id="pol_hard_unknown_capability", hard=True,
            )

        effective_class = spec.data_class
        if req.data_class is not None and (
            _DATA_SEVERITY[req.data_class] > _DATA_SEVERITY[effective_class]
        ):
            effective_class = req.data_class

        # 1) provenance: contenido externo jamás ordena (regla dura 0).
        if req.provenance is SourceTrust.EXTERNAL_CONTENT:
            return PolicyDecision(
                decision="deny", capability=req.capability, risk=Risk.CRITICAL,
                reason="orden originada en contenido externo no confiable "
                       "(inyección): denegada por contrato",
                policy_id="pol_hard_untrusted_provenance", hard=True,
            )

        # 1b) canal personal (p.ej. WhatsApp personal): invariante duro por
        # CAMPO ESTRUCTURAL, no por prefijo de connector_id (evadible
        # renombrando). Ninguna aprobación lo levanta.
        if req.personal_channel is True and req.capability in {
            "message.send", "email.send", "browser.submit",
        }:
            return PolicyDecision(
                decision="deny", capability=req.capability, risk=Risk.CRITICAL,
                reason="canal personal: import/borrador/revisión SOLO; "
                       "enviar es imposible",
                policy_id="pol_hard_personal_channel_send", hard=True,
            )

        # 2) invariantes duros (la de provenance ya se aplicó arriba: con
        #    applies_to vacío casaría con todo dentro de este bucle).
        for rule in HARD_RULES:
            if rule.policy_id == "pol_hard_untrusted_provenance":
                continue
            if not _matches(rule, req, effective_class):
                continue
            resolved = self._apply_effect(rule, req, spec.risk, effective_class)
            if resolved is not None:
                return resolved

        # 3) reglas blandas del fixture.
        for rule in self._soft_rules:
            if not rule.enabled or not _matches(rule, req, effective_class):
                continue
            resolved = self._apply_effect(rule, req, spec.risk, effective_class)
            if resolved is not None:
                return resolved

        # 4) spec de la capacidad.
        if spec.gate_required:
            return self._gate_decision(
                spec.gate_id, req, spec.risk,
                reason=f"capacidad {req.capability} declara gate obligatorio",
                policy_id=None,
            )

        # 5) default fail-closed.
        if is_read_capability(req.capability) or (
            _RISK_SEVERITY[spec.risk] <= _RISK_SEVERITY[Risk.LOW]
        ):
            return PolicyDecision(
                decision="allow", capability=req.capability, risk=spec.risk,
                reason="lectura/bajo riesgo sin regla en contra",
            )
        if (
            _RISK_SEVERITY[spec.risk] <= _RISK_SEVERITY[Risk.MEDIUM]
            and _DATA_SEVERITY[effective_class] <= _DATA_SEVERITY[DataClass.INTERNAL]
        ):
            return PolicyDecision(
                decision="allow", capability=req.capability, risk=spec.risk,
                reason="riesgo medio con datos internos: permitido",
            )
        return PolicyDecision(
            decision="require_gate", capability=req.capability, risk=spec.risk,
            reason="sin regla que lo permita: fail-closed a aprobación humana",
        )

    def _apply_effect(
        self, rule: PolicyRule, req: PolicyRequest, risk: Risk,
        effective_class: DataClass,
    ) -> PolicyDecision | None:
        lifted = rule.unless and all(u in req.approvals for u in rule.unless)
        if rule.effect is PolicyEffect.DENY:
            if lifted:
                return PolicyDecision(
                    decision="allow", capability=req.capability, risk=risk,
                    reason=f"{rule.policy_id} levantada por "
                           f"{[u.value for u in rule.unless]}",
                    policy_id=rule.policy_id, hard=rule.hard,
                )
            return PolicyDecision(
                decision="deny", capability=req.capability,
                risk=Risk.CRITICAL if rule.hard else risk,
                reason=rule.description, policy_id=rule.policy_id,
                hard=rule.hard,
            )
        if rule.effect is PolicyEffect.REQUIRE_GATE:
            if lifted:
                return PolicyDecision(
                    decision="allow", capability=req.capability, risk=risk,
                    reason=f"{rule.policy_id} aprobada vía gate",
                    policy_id=rule.policy_id, hard=rule.hard,
                )
            spec = get_capability(req.capability)
            gate_id = spec.gate_id if spec is not None else None
            return self._gate_decision(
                gate_id, req, risk, reason=rule.description,
                policy_id=rule.policy_id, hard=rule.hard,
            )
        if rule.effect is PolicyEffect.ALLOW_READONLY:
            if is_read_capability(req.capability):
                return PolicyDecision(
                    decision="allow", capability=req.capability, risk=risk,
                    reason=rule.description, policy_id=rule.policy_id,
                    hard=rule.hard,
                )
            return None  # no aplica a escrituras: siguen evaluándose
        if rule.effect is PolicyEffect.ALLOW:
            return PolicyDecision(
                decision="allow", capability=req.capability, risk=risk,
                reason=rule.description, policy_id=rule.policy_id,
                hard=rule.hard,
            )
        return None

    def _gate_decision(
        self, gate_id: str | None, req: PolicyRequest, risk: Risk, *,
        reason: str, policy_id: str | None, hard: bool = False,
    ) -> PolicyDecision:
        gate = self._gates.get(gate_id) if gate_id else None
        if gate is not None and gate.approval_mode == "always_block":
            return PolicyDecision(
                decision="deny", capability=req.capability, risk=risk,
                reason=f"{reason} — gate {gate.gate_id} bloquea siempre",
                policy_id=policy_id, gate_id=gate.gate_id, hard=hard,
            )
        if UnlessCondition.GATE_APPROVED in req.approvals:
            return PolicyDecision(
                decision="allow", capability=req.capability, risk=risk,
                reason=f"{reason} — aprobado en gate", policy_id=policy_id,
                gate_id=gate_id, hard=hard,
            )
        return PolicyDecision(
            decision="require_gate", capability=req.capability, risk=risk,
            reason=reason, policy_id=policy_id, gate_id=gate_id, hard=hard,
        )


def load_gates(gates_path: Path) -> list[GateSpec]:
    """Loader local. Import perezoso de GateSpec (ver nota TYPE_CHECKING
    arriba): evita el ciclo fabric→api→fabric al cargar el módulo."""
    from atlas.api.models import GateSpec  # noqa: PLC0415

    if not gates_path.exists():
        return []
    raw = json.loads(gates_path.read_text(encoding="utf-8"))
    return [GateSpec.model_validate(g) for g in raw]


def default_policy_engine(
    repo_root: Path, store: OsEventStore | None = None, *, real: bool = False,
) -> PolicyEngine:
    """Motor con las rutas convencionales del repo.

    T1 (docs/architecture/GOVERNANCE_KERNEL.md, "Camino a real" #1):

    * ``real=False`` (default, sin cambios de comportamiento): gates de
      ``fixtures/governance/gates.json`` — catálogo de desarrollo/tests,
      decisiones marcadas ``simulated=True``.
    * ``real=True``: gates de ``config/governance/gates.json`` — catálogo
      real mantenido por el operador. Lectura READ-ONLY (invariante 3: nunca
      se escribe governance desde aquí); decisiones marcadas
      ``simulated=False``. Si el fichero no existe todavía, se comporta
      igual que una lista de gates vacía (fail-closed: los invariantes
      duros y el default de PolicyEngine siguen aplicando).
    """
    gates_path = (
        repo_root / "config" / "governance" / "gates.json"
        if real
        else repo_root / "fixtures" / "governance" / "gates.json"
    )
    return PolicyEngine(
        rules_path=repo_root / "fixtures" / "security" / "policies.json",
        gates=load_gates(gates_path),
        store=store,
        simulated=not real,
    )
