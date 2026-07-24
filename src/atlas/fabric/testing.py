"""ConnectionTestRunner — prueba conexiones en mock/sandbox, y en real para
los conectores que ya tienen implementación real (hoy solo gmail, ADR-065).
Pedir modo real para un connector_id sin conector real devuelve
BLOCKED_BY_MISSING_DEPENDENCY, nunca un éxito fingido."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from atlas.events.emit import emit_event
from atlas.events.store import OsEventStore
from atlas.fabric.health import HealthMonitor
from atlas.fabric.models import HealthIssue, HealthStatus
from atlas.fabric.recipes import RecipeEngine

if TYPE_CHECKING:
    from atlas.fabric.auth_broker import AuthBroker
    from atlas.fabric.registry import ConnectorRegistry

# Conectores con implementación real cableada aquí. Ampliar esta tabla es la
# única acción necesaria para dar a un connector_id soporte de mode="real"
# cuando exista su conector (patrón: 1 entrada = 1 conector real, ADR-065).
_REAL_CONNECTORS = {"gmail"}


class ConnectionTestRunner:
    def __init__(
        self,
        recipes: RecipeEngine,
        health: HealthMonitor,
        store: OsEventStore | None = None,
        auth_broker: "AuthBroker | None" = None,
        registry: "ConnectorRegistry | None" = None,
    ) -> None:
        self._recipes = recipes
        self._health = health
        self._store = store
        self._auth_broker = auth_broker
        self._registry = registry

    def _find_credential_reference(self, provider: str) -> dict[str, Any] | None:
        if self._auth_broker is None:
            return None
        for ref in self._auth_broker.list_references():
            if ref["provider"] == provider:
                return ref
        return None

    def _test_gmail_real(self) -> dict[str, Any]:
        from atlas.fabric.connectors.gmail import GmailReadOnlyConnector

        ref = self._find_credential_reference("gmail")
        if ref is None or not self._auth_broker.reference_available(ref["credential_ref_id"]):  # type: ignore[union-attr]
            self._health.report(
                "gmail", HealthStatus.NEVER_CONNECTED,
                [HealthIssue(code="no_credential_reference",
                             detail="registra una referencia con AuthBroker.create_env_reference "
                                    "antes de probar en real")],
                simulated=False,
            )
            return {
                "ok": False,
                "status": "BLOCKED_BY_MISSING_DEPENDENCY",
                "connector_id": "gmail",
                "detail": "sin referencia de credencial disponible (AuthBroker)",
            }

        env_var = str(ref["reference"]).removeprefix("env:")
        connector = GmailReadOnlyConnector(token_env_var=env_var)
        descriptor = {"capabilities": connector.capabilities()}

        if self._registry is not None:
            verdict = self._registry.verify_descriptor("gmail", descriptor)
            if verdict["status"] == "unapproved":
                self._registry.approve_descriptor("gmail", descriptor)
            elif verdict["status"] == "rug_pull_suspected":
                self._health.report(
                    "gmail", HealthStatus.DEGRADED,
                    [HealthIssue(code="rug_pull_suspected",
                                 detail="el descriptor del conector cambió tras su "
                                        "aprobación; requiere re-aprobación humana")],
                    simulated=False,
                )
                return {
                    "ok": False,
                    "status": "rug_pull_suspected",
                    "connector_id": "gmail",
                    "detail": "descriptor cambió respecto a la aprobación previa; "
                              "re-aprueba con ConnectorRegistry.approve_descriptor",
                }

        result = connector.list_messages(max_results=1)
        if not result["ok"]:
            self._health.report(
                "gmail", HealthStatus.ERROR,
                [HealthIssue(code="connector_error", detail=result["detail"])],
                simulated=False,
            )
            return {"ok": False, "status": "error", "connector_id": "gmail",
                     "detail": result["detail"], "real": True}

        emit_event(
            self._store,
            "connector.test.finished",
            "Test real de Gmail: conexión verificada vía API real",
            actor="connector",
            source="atlas.fabric.testing",
            payload={"connector_id": "gmail", "mode": "real"},
            simulated=False,
        )
        health = self._health.report("gmail", HealthStatus.CONNECTED, simulated=False)
        return {
            "ok": True,
            "simulated": False,
            "real": True,
            "mode": "real",
            "connector_id": "gmail",
            "health": health.model_dump(mode="json"),
            "message_count": result["count"],
        }

    def test(self, connector_id: str, mode: str = "mock") -> dict[str, Any]:
        recipe = self._recipes.get(connector_id)
        if recipe is None:
            return {"ok": False, "status": "unknown_connector",
                    "connector_id": connector_id}
        if mode == "real":
            if connector_id in _REAL_CONNECTORS:
                return self._test_gmail_real()
            self._health.report(
                connector_id, HealthStatus.NEVER_CONNECTED,
                [HealthIssue(code="no_real_connector",
                             detail="no hay conector real implementado para este connector_id")],
            )
            return {
                "ok": False,
                "status": "BLOCKED_BY_MISSING_DEPENDENCY",
                "connector_id": connector_id,
                "detail": "no hay conector real implementado; usa mock/sandbox",
            }
        if mode not in {"mock", "sandbox"}:
            return {"ok": False, "status": "invalid_mode", "mode": mode}
        emit_event(
            self._store,
            "connector.test.finished",
            f"Test {mode} de {recipe.human_name}: ruta "
            f"{recipe.recommended_route.value} verificada en simulación",
            actor="connector",
            source="atlas.fabric.testing",
            payload={"connector_id": connector_id, "mode": mode,
                     "route": recipe.recommended_route.value},
        )
        health = self._health.report(connector_id, HealthStatus.CONNECTED,
                                     simulated=True)
        return {
            "ok": True,
            "simulated": True,
            "mode": mode,
            "connector_id": connector_id,
            "health": health.model_dump(mode="json"),
        }
