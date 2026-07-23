"""PolicyEngine + capacidades + corpus de seguridad (Fase 15, ADR-060/D14).

Filosofía (P15-R3): nada aquí "detecta" prompt injection con heurística de
texto. Los ataques del corpus se traducen a la dimensión que SÍ es
determinista — provenance no confiable, hash de descriptor, formato de
secreto — y se prueba que esa dimensión deniega, no que un LLM "se dio
cuenta". El corpus de texto queda como evidencia legible, no como oráculo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.fabric.auth_broker import looks_like_secret
from atlas.fabric.capabilities import CAPABILITY_CATALOG
from atlas.fabric.policy import PolicyDecision, PolicyEngine, PolicyRequest
from atlas.fabric.registry import ConnectorRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
SECURITY_DIR = REPO_ROOT / "fixtures" / "security"

SCENARIO_FILES = [
    "whatsapp_personal_send_blocked.json",
    "cloud_sensitive_data_denied.json",
    "erp_accounting_write_blocked.json",
    "crm_write_requires_gate.json",
    "connector_scope_escalation_denied.json",
]


def _load(name: str) -> dict:
    return json.loads((SECURITY_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture()
def bare_engine() -> PolicyEngine:
    """Motor SIN fixture de reglas (rules_path=None, gates=None): las
    decisiones duras deben sobrevivir intactas — no dependen de disco."""
    return PolicyEngine()


@pytest.mark.parametrize("filename", SCENARIO_FILES)
def test_scenario_matches_expected_decision(filename: str, bare_engine: PolicyEngine) -> None:
    scenario = _load(filename)
    decision = bare_engine.evaluate(PolicyRequest(**scenario["request"]))
    assert decision.decision == scenario["expected_decision"], scenario["description"]
    if "expected_hard" in scenario:
        assert decision.hard == scenario["expected_hard"]
    if "expected_policy_id" in scenario:
        assert decision.policy_id == scenario["expected_policy_id"]
    if "expected_gate_id" in scenario:
        assert decision.gate_id == scenario["expected_gate_id"]


def test_cloud_sensitive_lifted_by_human_approval(bare_engine: PolicyEngine) -> None:
    scenario = _load("cloud_sensitive_data_denied.json")
    variant = scenario["variant_with_approval"]
    decision = bare_engine.evaluate(PolicyRequest(**variant["request"]))
    assert decision.decision == variant["expected_decision"]


def test_accounting_write_lifted_by_gate_approval(bare_engine: PolicyEngine) -> None:
    scenario = _load("erp_accounting_write_blocked.json")
    variant = scenario["variant_with_gate_approval"]
    decision = bare_engine.evaluate(PolicyRequest(**variant["request"]))
    assert decision.decision == variant["expected_decision"]


def test_hard_rules_independent_of_fixture_file(tmp_path: Path) -> None:
    """P15-R2: apuntar rules_path a un fichero vacío/borrado no relaja nada.
    Esto es justo lo que ocurriría si alguien 'arregla' el test borrando el
    fixture: las decisiones duras deben seguir siendo las mismas."""
    missing = tmp_path / "no_existe.json"
    engine_no_fixture = PolicyEngine(rules_path=missing)
    engine_empty_fixture = PolicyEngine(
        rules_path=SECURITY_DIR / "policies.json"  # está vacío: []
    )
    for scenario_file in SCENARIO_FILES:
        scenario = _load(scenario_file)
        req = PolicyRequest(**scenario["request"])
        d1 = engine_no_fixture.evaluate(req)
        d2 = engine_empty_fixture.evaluate(req)
        assert d1.decision == d2.decision == scenario["expected_decision"]


@pytest.mark.parametrize("capability", [
    "erp.customers.read", "crm.contacts.read", "email.read", "files.read",
])
def test_untrusted_provenance_denies_even_read_capabilities(
    capability: str, bare_engine: PolicyEngine
) -> None:
    """Corpus: prompt_injection_direct.txt / malicious_github_issue.md /
    workflow_hijack_attempt.json representan contenido externo intentando
    disparar acciones. La mitigación determinista: provenance=external
    deniega SIEMPRE, incluso capacidades de solo lectura que normalmente
    se conceden por defecto."""
    decision = bare_engine.evaluate(PolicyRequest(
        capability=capability, provenance="external_content",
    ))
    assert decision.decision == "deny"
    assert decision.policy_id == "pol_hard_untrusted_provenance"


def test_browser_submit_requires_gate_by_default(bare_engine: PolicyEngine) -> None:
    """browser_submit_blocked.json: enviar formularios web nunca es
    allow-by-default."""
    fixture = _load("browser_submit_blocked.json")
    decision = bare_engine.evaluate(PolicyRequest(capability="browser.submit"))
    assert (decision.decision == "allow") is fixture["allowed"]
    assert (decision.decision == "require_gate") is fixture["requires_gate"]


def test_computer_use_matches_remote_command_high_risk_profile(
    bare_engine: PolicyEngine,
) -> None:
    """remote_command_high_risk.json: risk_class R6 exige step-up (gate)."""
    fixture = _load("remote_command_high_risk.json")
    decision = bare_engine.evaluate(PolicyRequest(capability="computer_use.execute"))
    assert fixture["requires_step_up"] is True
    assert decision.decision == "require_gate"
    assert decision.hard is True


def test_unknown_capability_is_deny_not_allow(bare_engine: PolicyEngine) -> None:
    decision = bare_engine.evaluate(PolicyRequest(capability="something.made_up"))
    assert decision.decision == "deny"


@pytest.mark.parametrize("corpus_file", [
    "memory_poisoning_attempt.md",
    "prompt_injection_indirect_email.md",
    "prompt_injection_pdf_ocr.txt",
    "malicious_github_issue.md",
])
def test_corpus_attacks_denied_when_carried_as_external_provenance(
    corpus_file: str, bare_engine: PolicyEngine,
) -> None:
    """Ata cada fichero del corpus a su mitigación determinista (antes eran
    peso muerto: copiados sin test — hallazgo de la auditoría). El contenido
    del fichero es la ORDEN externa; la capacidad que intenta disparar
    (memory.write para memory poisoning, email.send para 'send credentials',
    etc.) se deniega por provenance no confiable, no por leer el texto."""
    text = (SECURITY_DIR / corpus_file).read_text(encoding="utf-8").lower()
    # Elegimos la capacidad que el ataque intenta provocar según su contenido.
    if "email" in text or "send" in text or "credential" in text:
        capability = "email.send"
    elif "memory" in text or "from now on" in text:
        capability = "memory.write"
    else:
        capability = "files.read"
    decision = bare_engine.evaluate(PolicyRequest(
        capability=capability, provenance="external_content",
    ))
    assert decision.decision == "deny"
    assert decision.policy_id == "pol_hard_untrusted_provenance"


def test_crm_bulk_export_requires_gate(bare_engine: PolicyEngine) -> None:
    """Criterio de aceptación #7 del pack (MODULE 9): la exportación masiva
    de CRM exige gate. Antes: la capacidad existía con gate pero NINGÚN test
    lo probaba (hallazgo de la auditoría)."""
    decision = bare_engine.evaluate(PolicyRequest(capability="crm.bulk_export"))
    assert decision.decision == "require_gate"
    assert decision.gate_id == "gate_data_export"


def test_expected_policy_decisions_corpus_summary_holds(bare_engine: PolicyEngine) -> None:
    """Ata expected_policy_decisions.json (antes huérfano) a comportamiento
    real: sus 3 afirmaciones deben cumplirse en el motor."""
    expected = _load("expected_policy_decisions.json")
    # 1) contenido no confiable no puede llamar tools/capacidades:
    untrusted = bare_engine.evaluate(PolicyRequest(
        capability="files.read", provenance="external_content"))
    assert (untrusted.decision != "deny") is expected["untrusted_content_can_call_tools"]
    # 2) enviar exige gate (nunca allow directo):
    send = bare_engine.evaluate(PolicyRequest(capability="email.send"))
    assert (send.decision == "require_gate") is expected["send_requires_gate"]
    # 3) el material con forma de secreto se reconoce (base de la redacción):
    assert looks_like_secret("sk-" + "a1b2c3d4e5f6g7h8i9j0" * 2) is expected["secrets_redacted"]


def test_every_capability_gate_id_resolves_to_a_real_gate() -> None:
    """Gap real encontrado en el cierre de Fase 15: 8 capacidades apuntaban
    a gate_ids que no existían en fixtures/governance/gates.json (el
    require_gate seguía siendo seguro por defecto, pero el gate_id era un
    callejón sin salida). Regresión: todo gate_id declarado en el catálogo
    de capacidades debe existir de verdad."""
    gates_path = REPO_ROOT / "fixtures" / "governance" / "gates.json"
    known_gate_ids = {g["gate_id"] for g in json.loads(gates_path.read_text())}
    for cap in CAPABILITY_CATALOG.values():
        if cap.gate_id is not None:
            assert cap.gate_id in known_gate_ids, (
                f"{cap.capability} apunta a {cap.gate_id!r}, ausente en "
                "fixtures/governance/gates.json"
            )


def test_capability_catalog_covers_prompt_minimum() -> None:
    """El prompt exige al menos estas 22 capacidades (MODULE 6)."""
    required = {
        "email.read", "email.draft", "email.send",
        "crm.contacts.read", "crm.contacts.write",
        "crm.deals.read", "crm.deals.update",
        "erp.customers.read", "erp.invoices.read",
        "erp.invoices.create_draft", "erp.accounting.write",
        "files.read", "files.write",
        "browser.capture", "browser.fill", "browser.submit",
        "computer_use.execute", "model.cloud_call", "memory.write",
        "official.submit", "credential.use", "certificate.use",
    }
    assert required <= set(CAPABILITY_CATALOG)


def test_secret_leak_attempt_corpus_has_recognizable_secret_marker() -> None:
    """secret_leak_attempt.txt trae un placeholder deliberadamente corto
    ('sk-demo-secret'), demasiado corto para que la heurística de formato
    de AuthBroker lo confunda con un secreto real (los reales son largos
    y aleatorios — ver test_auth_broker_rejects_secret_looking_values).
    Lo que SÍ es determinista: el marcador estructural 'API_KEY=' está
    presente, que es la señal que dispara redacción/revisión en logs."""
    text = (SECURITY_DIR / "secret_leak_attempt.txt").read_text(encoding="utf-8")
    assert "API_KEY=" in text
    # Un token con la forma real (largo, sin espacios) SÍ se reconoce:
    assert looks_like_secret("sk-" + "a1b2c3d4e5f6g7h8i9j0" * 2)


def test_rug_pull_corpus_detected_by_hash_not_by_reading_description(
    tmp_path: Path,
) -> None:
    """rug_pull_tool_descriptor_before/after.json: mismo 'tool', descripción
    mutada tras aprobación. La detección es por hash del descriptor
    completo, no por parsear si la nueva frase 'suena mal'."""
    before = json.loads(
        (SECURITY_DIR / "rug_pull_tool_descriptor_before.json").read_text()
    )
    after = json.loads(
        (SECURITY_DIR / "rug_pull_tool_descriptor_after.json").read_text()
    )
    registry = ConnectorRegistry(tmp_path / "approved.json")
    registry.approve_descriptor("demo_tool", before)
    result = registry.verify_descriptor("demo_tool", after)
    assert result["status"] == "rug_pull_suspected"


def test_poisoned_descriptor_was_never_approved(tmp_path: Path) -> None:
    """poisoned_tool_descriptor.json nunca pasó por approve_descriptor:
    debe reportarse unapproved (no se usa hasta que un humano lo apruebe)."""
    poisoned = json.loads(
        (SECURITY_DIR / "poisoned_tool_descriptor.json").read_text()
    )
    registry = ConnectorRegistry(tmp_path / "approved.json")
    result = registry.verify_descriptor("demo", poisoned)
    assert result["status"] == "unapproved"


def test_policy_decision_is_json_serializable() -> None:
    decision = PolicyEngine().evaluate(PolicyRequest(capability="email.read"))
    assert isinstance(decision, PolicyDecision)
    dumped = decision.model_dump(mode="json")
    json.dumps(dumped)  # no debe reventar


# -- T1: modo real de governance (GOVERNANCE_KERNEL.md "Camino a real" #1) --


def test_engine_defaults_to_simulated_true() -> None:
    """Sin pasar `simulated=`, el comportamiento no cambia: sigue siendo
    modo fixture/dev (backward-compat)."""
    decision = PolicyEngine().evaluate(PolicyRequest(capability="email.send"))
    assert decision.simulated is True


def test_engine_real_mode_marks_every_branch_simulated_false() -> None:
    """`simulated=False` se propaga desde evaluate() sin importar qué rama
    interna decidió: invariante duro (hard rule), gate de capability y el
    default fail-closed de lectura de bajo riesgo."""
    engine = PolicyEngine(simulated=False)

    hard = engine.evaluate(PolicyRequest(capability="certificate.use"))
    assert hard.hard is True
    assert hard.simulated is False

    gated = engine.evaluate(PolicyRequest(capability="email.send"))
    assert gated.decision == "require_gate"
    assert gated.simulated is False

    read = engine.evaluate(PolicyRequest(capability="email.read"))
    assert read.decision == "allow"
    assert read.simulated is False


def test_default_policy_engine_real_reads_config_governance_gates(
    tmp_path: Path,
) -> None:
    """`default_policy_engine(repo_root, real=True)` lee
    config/governance/gates.json (real) en vez de fixtures/governance/
    gates.json — y marca las decisiones simulated=False. El modo fixture
    (default) sigue leyendo el fixture y queda simulated=True."""
    from atlas.fabric.policy import default_policy_engine

    repo_root = tmp_path / "repo"
    (repo_root / "config" / "governance").mkdir(parents=True)
    (repo_root / "fixtures" / "governance").mkdir(parents=True)
    (repo_root / "fixtures" / "security").mkdir(parents=True)
    (repo_root / "config" / "governance" / "gates.json").write_text(
        json.dumps([{
            "gate_id": "gate_t1_real_only",
            "display_name": "Gate solo en config real",
            "applies_to": ["t1.real_only_action"],
            "risk_threshold": "high",
            "approval_mode": "human_explicit",
            "default_decision": "require_approval",
            "enabled": True,
        }]),
        encoding="utf-8",
    )
    # fixtures/governance/gates.json queda vacío a propósito: si el motor
    # "real" leyera el fixture por error, esta gate no existiría ahí.
    (repo_root / "fixtures" / "governance" / "gates.json").write_text("[]", encoding="utf-8")

    real_engine = default_policy_engine(repo_root, real=True)
    fixture_engine = default_policy_engine(repo_root, real=False)

    # gate_id inexistente en el catálogo de capabilities → siempre cae al
    # evaluador v1 legacy en el bridge, pero a nivel de PolicyEngine puro
    # basta con comprobar que el gate real cargó y el fixture no.
    assert real_engine._gates.get("gate_t1_real_only") is not None  # noqa: SLF001
    assert fixture_engine._gates.get("gate_t1_real_only") is None  # noqa: SLF001

    decision = real_engine.evaluate(PolicyRequest(capability="email.send"))
    assert decision.simulated is False
    decision_fixture = fixture_engine.evaluate(PolicyRequest(capability="email.send"))
    assert decision_fixture.simulated is True


def test_default_policy_engine_real_missing_file_is_fail_closed(tmp_path: Path) -> None:
    """Si config/governance/gates.json todavía no existe, real=True no
    revienta: se comporta como lista de gates vacía (los invariantes duros y
    el default fail-closed de PolicyEngine siguen aplicando)."""
    from atlas.fabric.policy import default_policy_engine

    repo_root = tmp_path / "repo_sin_config"
    repo_root.mkdir()
    engine = default_policy_engine(repo_root, real=True)
    assert engine._gates == {}  # noqa: SLF001
    decision = engine.evaluate(PolicyRequest(capability="email.send"))
    assert decision.simulated is False
    assert decision.decision == "require_gate"  # spec de la capability lo exige
