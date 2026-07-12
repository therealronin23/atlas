"""IntegrationHealthMonitor — representa estados de salud, jamás los inventa:
sin check → never_connected. Cada cambio de estado emite evento."""

from __future__ import annotations

from datetime import datetime, timezone

from atlas.events.emit import emit_event
from atlas.events.schemas import Risk
from atlas.events.store import OsEventStore
from atlas.fabric.models import ConnectorHealth, HealthIssue, HealthStatus

_STATUS_RISK: dict[HealthStatus, Risk] = {
    HealthStatus.NEVER_CONNECTED: Risk.NONE,
    HealthStatus.CONNECTED: Risk.NONE,
    HealthStatus.DEGRADED: Risk.MEDIUM,
    HealthStatus.AUTH_EXPIRED: Risk.MEDIUM,
    HealthStatus.ERROR: Risk.HIGH,
    HealthStatus.DISCONNECTED: Risk.LOW,
}


class HealthMonitor:
    def __init__(self, store: OsEventStore | None = None) -> None:
        self._store = store
        self._states: dict[str, ConnectorHealth] = {}

    def report(
        self,
        connector_id: str,
        status: HealthStatus,
        issues: list[HealthIssue] | None = None,
        *,
        simulated: bool = True,
    ) -> ConnectorHealth:
        health = ConnectorHealth(
            connector_id=connector_id,
            status=status,
            issues=issues or [],
            last_check=datetime.now(timezone.utc).isoformat(),
            simulated=simulated,
        )
        previous = self._states.get(connector_id)
        self._states[connector_id] = health
        if previous is None or previous.status is not status:
            emit_event(
                self._store,
                "connector.health.changed",
                f"{connector_id}: "
                f"{previous.status.value if previous else 'sin estado'}"
                f" → {status.value}",
                actor="connector",
                source="atlas.fabric.health",
                risk=_STATUS_RISK[status],
                payload=health.model_dump(mode="json"),
                simulated=simulated,
            )
        return health

    def get(self, connector_id: str) -> ConnectorHealth:
        return self._states.get(connector_id) or ConnectorHealth(
            connector_id=connector_id,
            status=HealthStatus.NEVER_CONNECTED,
            issues=[],
        )

    def snapshot(self) -> list[ConnectorHealth]:
        return list(self._states.values())
