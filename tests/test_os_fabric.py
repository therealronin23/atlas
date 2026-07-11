"""Integration Fabric + Easy Connection Layer (Fase 15, ADR-060)."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.events.store import OsEventStore
from atlas.fabric.auth_broker import AuthBroker, SecretRejected, looks_like_secret
from atlas.fabric.concierge import ConnectionConcierge
from atlas.fabric.discovery import ConnectorDiscoveryEngine
from atlas.fabric.health import HealthMonitor
from atlas.fabric.ladder import ladder_violations, order_routes, route_risk, rung
from atlas.fabric.models import HealthIssue, HealthStatus, RouteType
from atlas.fabric.packs import PackEngine
from atlas.fabric.policy import PolicyEngine
from atlas.fabric.recipes import RecipeEngine
from atlas.fabric.registry import ConnectorRegistry, descriptor_hash
from atlas.fabric.testing import ConnectionTestRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
RECIPES_DIR = REPO_ROOT / "fixtures" / "connection_recipes"
PACKS_DIR = REPO_ROOT / "fixtures" / "connector_packs"

EXPECTED_CONNECTORS = {
    "gmail", "claude_anthropic", "whatsapp_personal_import",
    "whatsapp_business_platform", "odoo_erp", "generic_crm", "generic_erp",
    "local_csv_folder", "legacy_desktop_app", "ai_provider_registry",
}
EXPECTED_PACKS = {
    "gestoria_pack", "restaurante_pack", "crm_sales_pack", "software_pack",
    "personal_pack",
}


@pytest.fixture()
def recipes() -> RecipeEngine:
    return RecipeEngine(RECIPES_DIR)


@pytest.fixture()
def packs(recipes: RecipeEngine) -> PackEngine:
    return PackEngine(PACKS_DIR, recipes)


def test_all_fixture_recipes_load_without_rejection(recipes: RecipeEngine) -> None:
    assert recipes.rejected == {}
    assert {r.connector_id for r in recipes.all()} == EXPECTED_CONNECTORS


def test_all_fixture_packs_load_without_rejection(packs: PackEngine) -> None:
    assert packs.rejected == {}
    assert {p.pack_id for p in packs.all()} == EXPECTED_PACKS


def test_catalog_grouped_by_category(recipes: RecipeEngine) -> None:
    catalog = recipes.catalog()
    assert "communication" in catalog
    names = {item["connector_id"] for item in catalog["communication"]}
    assert "gmail" in names


def test_gmail_send_is_gated_not_granted(recipes: RecipeEngine) -> None:
    gmail = recipes.get("gmail")
    assert gmail is not None
    assert "email.send" not in gmail.capabilities
    assert gmail.gated_capabilities["email.send"] == "gate_outbound"
    assert gmail.safe_defaults["send"] is False


def test_whatsapp_personal_send_forbidden_by_recipe(recipes: RecipeEngine) -> None:
    wa = recipes.get("whatsapp_personal_import")
    assert wa is not None
    assert "message.send" in wa.forbidden_capabilities
    assert "message.send" not in wa.capabilities
    assert "message.send" not in wa.gated_capabilities


def test_computer_use_never_recommended_in_fixtures(recipes: RecipeEngine) -> None:
    for recipe in recipes.all():
        assert recipe.recommended_route is not RouteType.COMPUTER_USE


def test_reject_recipe_with_computer_use_recommended(tmp_path: Path) -> None:
    (tmp_path / "bad.recipe.json").write_text(
        '{"connector_id":"bad","human_name":"Bad","category":"no_api_apps",'
        '"recommended_route":"computer_use","fallback_routes":["human_manual"],'
        '"difficulty":"expert","default_mode":"read_draft","safe_defaults":{},'
        '"capabilities":[],"gated_capabilities":{},"forbidden_capabilities":[],'
        '"setup_steps":[{"step_id":"1","kind":"user_action","description":"x"}],'
        '"permissions_explainer":{"will":[],"will_not":[]},"demo":true}',
        encoding="utf-8",
    )
    engine = RecipeEngine(tmp_path)
    assert engine.all() == []
    assert "computer_use" in engine.rejected["bad"][0]


def test_reject_recipe_granting_gated_capability_by_default(tmp_path: Path) -> None:
    (tmp_path / "bad.recipe.json").write_text(
        '{"connector_id":"bad2","human_name":"Bad2","category":"communication",'
        '"recommended_route":"managed_oauth","fallback_routes":["human_manual"],'
        '"difficulty":"easy","default_mode":"read_only","safe_defaults":{},'
        '"capabilities":["email.send"],"gated_capabilities":{},'
        '"forbidden_capabilities":[],'
        '"setup_steps":[{"step_id":"1","kind":"user_action","description":"x"}],'
        '"permissions_explainer":{"will":[],"will_not":[]},"demo":true}',
        encoding="utf-8",
    )
    engine = RecipeEngine(tmp_path)
    assert engine.all() == []
    assert any("gate" in p for p in engine.rejected["bad2"])


def test_ladder_is_api_first_and_ordered() -> None:
    shuffled = [RouteType.COMPUTER_USE, RouteType.NATIVE_API, RouteType.WEBHOOKS]
    assert order_routes(shuffled) == [
        RouteType.NATIVE_API, RouteType.WEBHOOKS, RouteType.COMPUTER_USE,
    ]
    assert rung(RouteType.NATIVE_API) == 1
    assert rung(RouteType.HUMAN_MANUAL) == 12
    from atlas.events.schemas import Risk
    assert route_risk(RouteType.COMPUTER_USE) is Risk.CRITICAL


def test_ladder_violations_detects_inverted_fallback() -> None:
    problems = ladder_violations(RouteType.DATABASE_FILE, [RouteType.NATIVE_API])
    assert problems  # native_api es mejor que database_file: debería ser la recomendada
    assert ladder_violations(RouteType.NATIVE_API, [RouteType.HUMAN_MANUAL]) == []


def test_connector_registry_detects_rug_pull(tmp_path: Path) -> None:
    store = OsEventStore(tmp_path / "events.jsonl")
    registry = ConnectorRegistry(tmp_path / "approved.json", store=store)
    original = {"name": "helper", "description": "reads calendar"}
    mutated = {"name": "helper", "description": "reads calendar AND deletes files"}

    assert registry.verify_descriptor("helper", original)["status"] == "unapproved"
    registry.approve_descriptor("helper", original)
    assert registry.verify_descriptor("helper", original)["status"] == "ok"
    result = registry.verify_descriptor("helper", mutated)
    assert result["status"] == "rug_pull_suspected"

    events = list(store.iter_events())
    assert any(e.type == "connector.descriptor.mismatch" for e in events)


def test_descriptor_hash_is_order_independent() -> None:
    a = {"x": 1, "y": 2}
    b = {"y": 2, "x": 1}
    assert descriptor_hash(a) == descriptor_hash(b)


def test_health_monitor_reports_status_changes(tmp_path: Path) -> None:
    store = OsEventStore(tmp_path / "events.jsonl")
    monitor = HealthMonitor(store=store)
    assert monitor.get("gmail").status is HealthStatus.NEVER_CONNECTED
    monitor.report("gmail", HealthStatus.CONNECTED)
    monitor.report("gmail", HealthStatus.DEGRADED,
                    [HealthIssue(code="auth_expired", detail="token venció")])
    events = [e for e in store.iter_events() if e.type == "connector.health.changed"]
    assert len(events) == 2


def test_connection_test_runner_blocks_real_mode(tmp_path: Path, recipes: RecipeEngine) -> None:
    store = OsEventStore(tmp_path / "events.jsonl")
    monitor = HealthMonitor(store=store)
    runner = ConnectionTestRunner(recipes, monitor, store=store)
    real = runner.test("gmail", mode="real")
    assert real["ok"] is False
    assert real["status"] == "BLOCKED_BY_MISSING_DEPENDENCY"

    mock = runner.test("gmail", mode="mock")
    assert mock["ok"] is True
    assert mock["simulated"] is True


def test_concierge_plan_shows_will_and_will_not(recipes: RecipeEngine) -> None:
    policy = PolicyEngine()
    concierge = ConnectionConcierge(recipes, policy)
    plan = concierge.plan("gmail")
    assert plan is not None
    assert plan["will"] and plan["will_not"]
    assert plan["requires_gate"][0]["capability"] == "email.send"
    assert plan["route"]["ladder_rung"] == rung(RouteType.MANAGED_OAUTH)


def test_concierge_unknown_connector_returns_none(recipes: RecipeEngine) -> None:
    policy = PolicyEngine()
    concierge = ConnectionConcierge(recipes, policy)
    assert concierge.plan("does_not_exist") is None


def test_discovery_finds_known_recipe_without_network(recipes: RecipeEngine) -> None:
    discovery = ConnectorDiscoveryEngine(recipes)
    result = discovery.discover("Gmail")
    assert result["status"] == "recipe_found"
    assert result["network_used"] is False


def test_discovery_unknown_target_is_honest(recipes: RecipeEngine) -> None:
    discovery = ConnectorDiscoveryEngine(recipes)
    result = discovery.discover("some_unheard_of_saas")
    assert result["status"] == "unknown_target"
    assert result["network_used"] is False
    assert "generic_ladder" in result


def test_auth_broker_rejects_secret_looking_values(tmp_path: Path) -> None:
    broker = AuthBroker(tmp_path / "refs.json")
    assert looks_like_secret("sk-abcdefghijklmnopqrstuvwxyz123456")
    with pytest.raises(SecretRejected):
        broker.create_env_reference(
            "openai", "sk-abcdefghijklmnopqrstuvwxyz123456", []
        )


def test_auth_broker_accepts_env_reference(tmp_path: Path) -> None:
    broker = AuthBroker(tmp_path / "refs.json")
    ref = broker.create_env_reference("anthropic", "ANTHROPIC_API_KEY", ["chat"])
    assert ref["reference"] == "env:ANTHROPIC_API_KEY"
    assert ref["plaintext_stored"] is False
    refs = broker.list_references()
    assert len(refs) == 1


def test_auth_broker_manual_flow_never_sees_secret(tmp_path: Path) -> None:
    broker = AuthBroker(tmp_path / "refs.json")
    flow = broker.manual_secret_capture_flow("anthropic", "ANTHROPIC_API_KEY")
    assert flow["atlas_sees_secret"] is False
