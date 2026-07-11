"""Atlas OS — rutas de producto (Fase 15): Integration Fabric + Business Core.

Se registran sobre la app existente del bridge (server.create_app), nunca al
revés: este módulo NUNCA importa Orchestrator (guard estático en
test_os_api.py, ampliado a fabric/business). Estado nuevo propio bajo
$ATLAS_HOME/connections/ y $ATLAS_HOME/business_core/ — no toca el core.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from atlas.business.core_engine import (
    ActivationError,
    BusinessCoreEngine,
    ReviewRequiredError,
)
from atlas.business.models import CreatedFrom, CreatedFromKind, Modules, OnboardingSession
from atlas.business.questions import (
    OnboardingError,
    QuestionEngine,
    load_all_packs,
)
from atlas.events.store import OsEventStore
from atlas.fabric.concierge import ConnectionConcierge
from atlas.fabric.discovery import ConnectorDiscoveryEngine
from atlas.fabric.health import HealthMonitor
from atlas.fabric.packs import PackEngine
from atlas.fabric.policy import PolicyEngine, load_gates
from atlas.fabric.recipes import RecipeEngine
from atlas.fabric.testing import ConnectionTestRunner


class ConnectionPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: str


class ConnectionTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: str
    mode: str = "mock"


class OnboardingStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: str


class OnboardingAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    question_id: str
    value: Any = None
    uncertain: bool = False


class OnboardingQuestionRefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    question_id: str


class OnboardingSessionIdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str


class CoreDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sector_id: str
    created_from_kind: str
    created_from_ref: str
    crm: bool = True
    erp: bool = True
    demo: bool = False


class CoreActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_core_id: str


class CoreActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_core_id: str
    approved_by: str = Field(min_length=1)
    decision_note: str | None = None
    evidence: list[str] = Field(default_factory=list)


class CoreRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_core_id: str
    rejected_by: str = Field(min_length=1)
    decision_note: str | None = None


def _default_sessions_path() -> Path:
    home = Path(os.environ.get("ATLAS_HOME", "~/atlas")).expanduser()
    return home / "business_core" / "onboarding_sessions.json"


class _SessionStore:
    """Persistencia de sesiones de onboarding en un único JSON (mismo patrón
    que `atlas.business.core_engine._Store`) — sobreviven a reinicios del
    bridge en vez de vivir solo en un dict en memoria."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        data: dict[str, dict[str, Any]] = json.loads(
            self._path.read_text(encoding="utf-8")
        )
        return data

    def _write(self, data: dict[str, dict[str, Any]]) -> None:
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def save(self, session: OnboardingSession) -> None:
        with self._lock:
            data = self._read()
            data[session.session_id] = session.model_dump(mode="json")
            self._write(data)

    def get(self, session_id: str) -> OnboardingSession | None:
        data = self._read()
        raw = data.get(session_id)
        return OnboardingSession.model_validate(raw) if raw else None


def register_product_routes(
    app: FastAPI,
    store: OsEventStore,
    fixtures_dir: Path,
    business_core_path: Path | None = None,
) -> None:
    """`business_core_path` es explícito a propósito: sin él, BusinessCoreEngine
    caería a $ATLAS_HOME real (mismo bug clase que ya se corrigió para `app`
    perezosa) — los tests SIEMPRE deben pasarlo bajo tmp_path."""
    recipes = RecipeEngine(fixtures_dir / "connection_recipes")
    packs = PackEngine(fixtures_dir / "connector_packs", recipes)
    policy = PolicyEngine(
        rules_path=fixtures_dir / "security" / "policies.json",
        gates=load_gates(fixtures_dir / "governance" / "gates.json"),
        store=store,
    )
    concierge = ConnectionConcierge(recipes, policy)
    discovery = ConnectorDiscoveryEngine(recipes)
    health = HealthMonitor(store=store)
    tester = ConnectionTestRunner(recipes, health, store=store)
    question_packs = load_all_packs(fixtures_dir / "question_packs")
    questions = QuestionEngine()
    business = BusinessCoreEngine(store=store, path=business_core_path)

    sessions_path = (
        business_core_path.parent / "onboarding_sessions.json"
        if business_core_path is not None
        else _default_sessions_path()
    )
    session_store = _SessionStore(sessions_path)

    def _load_session(session_id: str) -> tuple[OnboardingSession, Any]:
        session = session_store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="sesión desconocida")
        pack = question_packs.get(session.pack_id)
        if pack is None:
            raise HTTPException(
                status_code=500, detail="pack de la sesión ya no existe"
            )
        return session, pack

    # -- Integration Fabric / Easy Connection Layer --------------------------

    @app.get("/connections/catalog")
    def connections_catalog() -> dict[str, Any]:
        return {"categories": recipes.catalog(), "rejected": recipes.rejected}

    @app.get("/connections/recipes")
    def connections_recipes() -> dict[str, Any]:
        return {
            "count": len(recipes.all()),
            "recipes": [r.model_dump(mode="json") for r in recipes.all()],
        }

    @app.get("/connections/packs")
    def connections_packs() -> dict[str, Any]:
        return {
            "count": len(packs.all()),
            "packs": [p.model_dump(mode="json") for p in packs.all()],
        }

    @app.post("/connections/plan")
    def connections_plan(req: ConnectionPlanRequest) -> dict[str, Any]:
        plan = concierge.plan(req.connector_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="receta desconocida")
        return plan

    @app.post("/connections/test")
    def connections_test(req: ConnectionTestRequest) -> dict[str, Any]:
        return tester.test(req.connector_id, mode=req.mode)

    @app.get("/connections/discover")
    def connections_discover(target: str) -> dict[str, Any]:
        return discovery.discover(target)

    @app.get("/integrations/health")
    def integrations_health() -> dict[str, Any]:
        return {
            "connectors": [h.model_dump(mode="json") for h in health.snapshot()],
        }

    # -- Adaptive Question Engine / Onboarding --------------------------------

    @app.get("/business/question-packs")
    def business_question_packs() -> dict[str, Any]:
        return {
            "count": len(question_packs),
            "packs": [p.model_dump(mode="json") for p in question_packs.values()],
        }

    @app.post("/business/onboarding/start")
    def onboarding_start(req: OnboardingStartRequest) -> dict[str, Any]:
        pack = question_packs.get(req.pack_id)
        if pack is None:
            raise HTTPException(status_code=404, detail="pack desconocido")
        session = questions.start_session(pack, demo=True)
        session_store.save(session)
        return session.model_dump(mode="json")

    @app.post("/business/onboarding/answer")
    def onboarding_answer(req: OnboardingAnswerRequest) -> dict[str, Any]:
        session, pack = _load_session(req.session_id)
        try:
            session = questions.submit_answer(
                session, pack, req.question_id, req.value, uncertain=req.uncertain,
            )
        except OnboardingError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        session_store.save(session)
        return session.model_dump(mode="json")

    @app.post("/business/onboarding/confirm_answer")
    def onboarding_confirm_answer(req: OnboardingQuestionRefRequest) -> dict[str, Any]:
        session, _pack = _load_session(req.session_id)
        try:
            session = questions.confirm_answer(session, req.question_id)
        except OnboardingError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        session_store.save(session)
        return session.model_dump(mode="json")

    @app.post("/business/onboarding/skip")
    def onboarding_skip(req: OnboardingQuestionRefRequest) -> dict[str, Any]:
        session, pack = _load_session(req.session_id)
        try:
            session = questions.skip_question(session, pack, req.question_id)
        except OnboardingError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        session_store.save(session)
        return session.model_dump(mode="json")

    @app.post("/business/onboarding/preview")
    def onboarding_preview(req: OnboardingSessionIdRequest) -> dict[str, Any]:
        session, pack = _load_session(req.session_id)
        try:
            session = questions.build_preview(session, pack)
        except OnboardingError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        session_store.save(session)
        return session.model_dump(mode="json")

    @app.post("/business/onboarding/confirm")
    def onboarding_confirm(req: OnboardingSessionIdRequest) -> dict[str, Any]:
        session, _pack = _load_session(req.session_id)
        try:
            session = questions.confirm_session(session)
        except OnboardingError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        session_store.save(session)
        return session.model_dump(mode="json")

    # -- Business Core ----------------------------------------------------------

    @app.post("/business/core/draft")
    def business_core_draft(req: CoreDraftRequest) -> dict[str, Any]:
        try:
            kind = CreatedFromKind(req.created_from_kind)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        core = business.create_draft(
            req.sector_id,
            CreatedFrom(kind=kind, ref=req.created_from_ref),
            Modules(crm=req.crm, erp=req.erp),
            demo=req.demo,
        )
        return core.model_dump(mode="json")

    @app.get("/business/core/{business_core_id}")
    def business_core_get(business_core_id: str) -> dict[str, Any]:
        core = business.get(business_core_id)
        if core is None:
            raise HTTPException(status_code=404, detail="business core desconocido")
        return core.model_dump(mode="json")

    @app.get("/business/core/{business_core_id}/entities")
    def business_core_entities(business_core_id: str) -> dict[str, Any]:
        entities = business.list_entities(business_core_id)
        return {
            "count": len(entities),
            "entities": [e.model_dump(mode="json") for e in entities],
        }

    @app.post("/business/core/request-activation")
    def business_core_request_activation(req: CoreActionRequest) -> dict[str, Any]:
        try:
            core = business.request_activation(req.business_core_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ActivationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return core.model_dump(mode="json")

    @app.post("/business/core/activate")
    def business_core_activate(req: CoreActivateRequest) -> dict[str, Any]:
        try:
            core = business.approve_activation(
                req.business_core_id, req.approved_by,
                decision_note=req.decision_note, evidence=req.evidence,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ActivationError, ReviewRequiredError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return core.model_dump(mode="json")

    @app.post("/business/core/reject")
    def business_core_reject(req: CoreRejectRequest) -> dict[str, Any]:
        try:
            core = business.reject_activation(
                req.business_core_id, req.rejected_by,
                decision_note=req.decision_note,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ActivationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return core.model_dump(mode="json")

    # -- Gate Engine: cola de decisiones humanas ------------------------------

    @app.get("/gates/open")
    def gates_open() -> dict[str, Any]:
        tickets = business.gates.list_open()
        return {"count": len(tickets),
                "tickets": [t.model_dump(mode="json") for t in tickets]}

    @app.get("/gates/{gate_ticket_id}")
    def gate_get(gate_ticket_id: str) -> dict[str, Any]:
        ticket = business.gates.get(gate_ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="gate ticket desconocido")
        return ticket.model_dump(mode="json")
