"""Atlas Business Core + Adaptive Question Engine + Legacy Link (ADR-061)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.business.core_engine import (
    ActivationError,
    BusinessCoreEngine,
    ModuleDisabledError,
    ReviewRequiredError,
)
from atlas.business.extract import extract_contacts_from_gmail, extract_from_invoices
from atlas.business.legacy import (
    SyncNotApprovedError,
    canonicality_for_link,
    enable_sync,
    propose_link,
)
from atlas.business.models import (
    BusinessCore,
    CanonicalityMode,
    CreatedFrom,
    CreatedFromKind,
    EntityCandidate,
    EntityKind,
    LegacyLinkMode,
    Modules,
    OnboardingSession,
    SessionStatus,
)
from atlas.business.questions import (
    OnboardingError,
    QuestionEngine,
    load_all_packs,
    load_pack,
)
from atlas.events.store import OsEventStore

REPO_ROOT = Path(__file__).resolve().parents[1]
QUESTION_PACKS_DIR = REPO_ROOT / "fixtures" / "question_packs"
BUSINESS_CORE_DIR = REPO_ROOT / "fixtures" / "business_core"

EXPECTED_PACKS = {
    "qp_gestoria_fiscal_contable", "qp_restauracion_hosteleria", "qp_ventas_crm",
    "qp_software_it_seguridad", "qp_vida_personal_familia",
}


# -- Question packs ----------------------------------------------------------

def test_all_question_packs_load() -> None:
    packs = load_all_packs(QUESTION_PACKS_DIR)
    assert set(packs) == EXPECTED_PACKS
    for pack in packs.values():
        assert len(pack.questions) >= 1


def test_onboarding_fixtures_parse_against_model() -> None:
    for name in ["restaurant_business_onboarding.json", "gestoria_business_onboarding.json"]:
        raw = json.loads((BUSINESS_CORE_DIR / name).read_text(encoding="utf-8"))
        session = OnboardingSession.model_validate(raw)
        assert session.status is SessionStatus.PREVIEW
        assert session.proposed is not None


def test_business_core_draft_fixtures_parse_against_model() -> None:
    for name in ["restaurant_business_core_draft.json", "gestoria_business_core_draft.json",
                 "activation_gate_demo.json"]:
        raw = json.loads((BUSINESS_CORE_DIR / name).read_text(encoding="utf-8"))
        core = BusinessCore.model_validate(raw)
        assert core.activation.approved is False


def test_entity_candidate_fixtures_parse_against_model() -> None:
    for name in ["crm_from_gmail_candidates.json", "erp_from_invoices_candidates.json"]:
        raw = json.loads((BUSINESS_CORE_DIR / name).read_text(encoding="utf-8"))
        for item in raw["candidates"]:
            EntityCandidate.model_validate(item)


def test_full_onboarding_loop_requires_confirmation_before_progress() -> None:
    pack = load_pack(QUESTION_PACKS_DIR / "restauracion_hosteleria.json")
    engine = QuestionEngine()
    session = engine.start_session(pack, demo=True)
    assert session.status is SessionStatus.ACTIVE
    assert set(session.pending_questions) == {q.question_id for q in pack.questions}

    session = engine.submit_answer(
        session, pack, "sales_channels", ["local", "delivery"],
    )
    # Sin confirmar, build_preview debe rechazar aunque no queden pendientes.
    with pytest.raises(OnboardingError):
        engine.build_preview(session, pack)


def test_uncertain_answer_does_not_grant_capabilities() -> None:
    """La rama 'no sé' es válida (no bloquea) pero NO desbloquea capacidades:
    Atlas no concede permisos sobre una incertidumbre."""
    pack = load_pack(QUESTION_PACKS_DIR / "gestoria_fiscal_contable.json")
    engine = QuestionEngine()
    session = engine.start_session(pack)

    session = engine.submit_answer(session, pack, "clients_type",
                                    ["autonomos", "companies"])
    session = engine.confirm_answer(session, "clients_type")
    session = engine.submit_answer(session, pack, "client_files_location",
                                    "drive_onedrive")
    session = engine.confirm_answer(session, "client_files_location")
    session = engine.submit_answer(session, pack, "accounting_software", "odoo")
    session = engine.confirm_answer(session, "accounting_software")
    session = engine.submit_answer(session, pack, "uses_digital_certificate",
                                    None, uncertain=True)
    session = engine.confirm_answer(session, "uses_digital_certificate")

    assert session.pending_questions == []
    preview = engine.build_preview(session, pack)
    assert preview.status is SessionStatus.PREVIEW
    assert "certificate.use" not in preview.proposed.capabilities
    assert "official.submit" not in preview.proposed.capabilities
    assert "erp.customers.read" in preview.proposed.capabilities

    confirmed = engine.confirm_session(preview)
    assert confirmed.status is SessionStatus.CONFIRMED


def test_uncertainty_rejected_when_not_allowed() -> None:
    pack = load_pack(QUESTION_PACKS_DIR / "restauracion_hosteleria.json")
    engine = QuestionEngine()
    session = engine.start_session(pack)
    with pytest.raises(OnboardingError):
        engine.submit_answer(session, pack, "sales_channels", None, uncertain=True)


def test_skip_only_when_allowed() -> None:
    pack = load_pack(QUESTION_PACKS_DIR / "restauracion_hosteleria.json")
    engine = QuestionEngine()
    session = engine.start_session(pack)
    # sales_channels no admite skip.
    with pytest.raises(OnboardingError):
        engine.skip_question(session, pack, "sales_channels")
    # uses_pos sí lo admite.
    session = engine.submit_answer(session, pack, "sales_channels", ["local"])
    session = engine.confirm_answer(session, "sales_channels")
    session = engine.submit_answer(session, pack, "has_menu", "no")
    session = engine.confirm_answer(session, "has_menu")
    session = engine.submit_answer(session, pack, "stock_control", "no")
    session = engine.confirm_answer(session, "stock_control")
    session = engine.skip_question(session, pack, "uses_pos")
    assert session.pending_questions == []
    preview = engine.build_preview(session, pack)
    assert preview.proposed is not None


def test_invalid_option_is_rejected() -> None:
    pack = load_pack(QUESTION_PACKS_DIR / "restauracion_hosteleria.json")
    engine = QuestionEngine()
    session = engine.start_session(pack)
    with pytest.raises(OnboardingError):
        engine.submit_answer(session, pack, "has_menu", "not_an_option")


def test_multi_choice_min_selected_enforced() -> None:
    pack = load_pack(QUESTION_PACKS_DIR / "restauracion_hosteleria.json")
    engine = QuestionEngine()
    session = engine.start_session(pack)
    with pytest.raises(OnboardingError):
        engine.submit_answer(session, pack, "sales_channels", [])


# -- Business Core: draft-first + activación gateada -------------------------

def test_business_core_starts_draft_and_requires_gate_to_activate(tmp_path: Path) -> None:
    store = OsEventStore(tmp_path / "events.jsonl")
    engine = BusinessCoreEngine(store=store, path=tmp_path / "bcore.json")
    core = engine.create_draft(
        "restauracion_hosteleria",
        CreatedFrom(kind=CreatedFromKind.ONBOARDING, ref="obs_restaurant_demo"),
    )
    assert core.status.value == "draft"
    assert core.activation.approved is False

    # Activar sin pasar por request_activation: prohibido.
    with pytest.raises(ActivationError):
        engine.approve_activation(core.business_core_id, approved_by="operador")

    pending = engine.request_activation(core.business_core_id)
    assert pending.status.value == "pending_activation"

    active = engine.approve_activation(core.business_core_id, approved_by="operador")
    assert active.status.value == "active"
    assert active.activation.approved is True
    assert active.activation.approved_by == "operador"

    events = [e.type for e in store.iter_events()]
    assert "business_core.activation.requested" in events
    assert "business_core.activated" in events


def test_cannot_reactivate_already_active_core(tmp_path: Path) -> None:
    engine = BusinessCoreEngine(path=tmp_path / "bcore.json")
    core = engine.create_draft(
        "restauracion_hosteleria",
        CreatedFrom(kind=CreatedFromKind.MANUAL, ref="manual"),
    )
    engine.request_activation(core.business_core_id)
    engine.approve_activation(core.business_core_id, approved_by="op")
    with pytest.raises(ActivationError):
        engine.request_activation(core.business_core_id)


def test_activation_opens_and_approves_a_real_gate_ticket(tmp_path: Path) -> None:
    """ADR-063: request_activation abre un GateTicket real; approve_activation
    lo aprueba por el Gate Engine antes de activar. 'gated' es un objeto."""
    from atlas.fabric.models import GateStatus  # noqa: PLC0415

    engine = BusinessCoreEngine(path=tmp_path / "bcore.json")
    core = engine.create_draft(
        "restauracion_hosteleria",
        CreatedFrom(kind=CreatedFromKind.MANUAL, ref="manual"),
    )
    pending = engine.request_activation(core.business_core_id)
    ticket_id = pending.activation.gate_ticket_id
    assert ticket_id is not None
    assert engine.gates.get(ticket_id).status is GateStatus.OPEN
    assert engine.gates.list_open()  # aparece en la cola

    active = engine.approve_activation(
        core.business_core_id, approved_by="operador",
        decision_note="revisado", evidence=["ref:audit"],
    )
    assert active.status.value == "active"
    assert engine.gates.get(ticket_id).status is GateStatus.APPROVED
    assert engine.gates.list_open() == []


def test_reject_activation_returns_core_to_draft(tmp_path: Path) -> None:
    from atlas.fabric.models import GateStatus  # noqa: PLC0415

    engine = BusinessCoreEngine(path=tmp_path / "bcore.json")
    core = engine.create_draft(
        "restauracion_hosteleria",
        CreatedFrom(kind=CreatedFromKind.MANUAL, ref="manual"),
    )
    pending = engine.request_activation(core.business_core_id)
    ticket_id = pending.activation.gate_ticket_id
    rejected = engine.reject_activation(
        core.business_core_id, rejected_by="operador", decision_note="faltan datos",
    )
    assert rejected.status.value == "draft"
    assert rejected.activation.gate_ticket_id is None
    assert engine.gates.get(ticket_id).status is GateStatus.REJECTED
    # Tras rechazo se puede volver a pedir.
    engine.request_activation(core.business_core_id)


def test_module_flag_is_enforced_not_decorative(tmp_path: Path) -> None:
    """modules.crm/erp dejó de ser decorativo (hallazgo de la auditoría):
    añadir una entidad exclusiva de un módulo desactivado se rechaza, y las
    vistas CRM_KINDS/ERP_KINDS de entities.py se usan de verdad."""
    engine = BusinessCoreEngine(path=tmp_path / "bcore.json")
    erp_only = engine.create_draft(
        "restauracion_hosteleria",
        CreatedFrom(kind=CreatedFromKind.MANUAL, ref="m"),
        modules=Modules(crm=False, erp=True),
    )
    # invoice es ERP → permitido; opportunity es CRM puro → rechazado.
    engine.add_entity(erp_only.business_core_id, EntityKind.INVOICE, "F-1")
    with pytest.raises(ModuleDisabledError):
        engine.add_entity(erp_only.business_core_id, EntityKind.OPPORTUNITY, "Deal")
    # document es SHARED (ni CRM ni ERP exclusivo) → siempre permitido.
    engine.add_entity(erp_only.business_core_id, EntityKind.DOCUMENT, "doc")


def test_promote_candidate_requires_human_review(tmp_path: Path) -> None:
    engine = BusinessCoreEngine(path=tmp_path / "bcore.json")
    core = engine.create_draft(
        "restauracion_hosteleria",
        CreatedFrom(kind=CreatedFromKind.IMPORT, ref="import:demo"),
    )
    candidate = EntityCandidate(
        candidate_id="cand_x", kind=EntityKind.SUPPLIER, label="Proveedor X",
        confidence=0.9, source_refs=["import:demo"], proposed_data={},
        requires_review=True,
    )
    with pytest.raises(ReviewRequiredError):
        engine.promote_candidate(core.business_core_id, candidate, reviewed_by=None)

    entity = engine.promote_candidate(
        core.business_core_id, candidate, reviewed_by="operador",
    )
    assert entity.requires_review is False
    assert "candidate:cand_x" in entity.source_refs
    entities = engine.list_entities(core.business_core_id)
    assert len(entities) == 1


# -- Extracción determinista --------------------------------------------------

def test_extract_contacts_from_gmail_is_deterministic() -> None:
    contacts = [
        {"name": "Ana", "email": "ana@example.com"},
        {"name": None, "email": "solo@example.com"},
        {"name": "Sin email", "email": None},
    ]
    candidates = extract_contacts_from_gmail(contacts, "import:demo")
    assert len(candidates) == 2  # el tercero sin email se descarta
    assert all(c.requires_review for c in candidates)
    with_name = next(c for c in candidates if c.proposed_data["email"] == "ana@example.com")
    assert with_name.confidence == 0.9
    without_name = next(c for c in candidates if c.proposed_data["email"] == "solo@example.com")
    assert without_name.confidence == 0.6


def test_extract_from_invoices_produces_party_and_invoice_candidates() -> None:
    invoices = [
        {"role": "supplier", "name": "Proveedor Demo", "tax_id": "B123",
         "invoice_number": "F-001", "amount": 100.0},
    ]
    candidates = extract_from_invoices(invoices, "import:demo")
    kinds = {c.kind for c in candidates}
    assert kinds == {EntityKind.SUPPLIER, EntityKind.INVOICE}
    supplier = next(c for c in candidates if c.kind is EntityKind.SUPPLIER)
    assert supplier.confidence == 0.95  # tiene tax_id


# -- Legacy Link Layer ---------------------------------------------------------

def test_legacy_link_always_starts_sync_disabled() -> None:
    link = propose_link("odoo", LegacyLinkMode.PARTIAL_SYNC)
    assert link.sync_enabled is False


def test_canonicality_explicit_from_link_mode() -> None:
    mirror = propose_link("odoo", LegacyLinkMode.READ_ONLY_MIRROR)
    canon = canonicality_for_link(mirror)
    assert canon.mode is CanonicalityMode.EXTERNAL_CANONICAL
    assert canon.source_of_truth == "odoo"

    migration = propose_link("excel_legacy", LegacyLinkMode.MIGRATION)
    canon2 = canonicality_for_link(migration)
    assert canon2.mode is CanonicalityMode.HYBRID_CANONICAL


def test_enable_sync_requires_human_approval() -> None:
    link = propose_link("odoo", LegacyLinkMode.PARTIAL_SYNC)
    with pytest.raises(SyncNotApprovedError):
        enable_sync(link, human_approved=False)
    approved = enable_sync(link, human_approved=True)
    assert approved.sync_enabled is True
    assert link.sync_enabled is False  # el original no muta
