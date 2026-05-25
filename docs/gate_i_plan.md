# Gate I — Operational 24/7 Service

**Status:** MVP  
**Tag:** `v0.8-gate-i`

## Goal

Single long-running process for Telegram, Hermes offline monitoring, health JSON, and optional dashboard.

## Deliverables

| ID | Item |
|----|------|
| I1 | `atlas serve` + `AtlasServiceRunner` |
| I2 | `atlas health` + `GET /api/health` |
| I3 | EventBus alert logging (SHADOW, THERMAL, Hermes reconnect) |
| I4 | `scripts/atlas-core.service` systemd user unit |
| I5 | `scripts/gate_i_smoke.py` |

## Env

| Variable | Purpose |
|----------|---------|
| `ATLAS_SERVE_DASHBOARD` | Start dashboard thread on :7331 |
| `ATLAS_THERMAL_MONITOR` | Start ThermalWatchdog |
| `ATLAS_OFFLINE_POLL_S` | OfflineMonitor interval (default 60) |

## Not in Gate I

- ADR-024 full observability stack
- ADR-025 ColdUpdateManager
- Hermes push webhooks
