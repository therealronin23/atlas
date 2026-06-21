# Operational Runbook — Atlas Core

**Date:** 2026-05-25  
**Scope:** Sesion A — validar loop operativo local + Hermes VPS + Telegram.

## Prerequisites

```bash
cd ~/proyectos/atlas-core
source .venv/bin/activate
source .env   # HERMES_*, TELEGRAM_*, API keys; todas las lineas KEY=value
```

Variables minimas:

| Variable | Uso |
|----------|-----|
| `HERMES_BASE_URL` | Tailscale URL del VPS (ej. `http://100.x.x.x:8443`) |
| `HERMES_API_KEY` | Secreto HMAC compartido |
| `ATLAS_PENDING_HMAC_KEY` | Opcional; si falta, usa `HERMES_API_KEY` para firmar pending |
| `TELEGRAM_BOT_TOKEN` | Bot API token |
| `TELEGRAM_CHAT_ID` | Chat autorizado (ADR-013) |
| `ATLAS_HOME` | Opcional; default `~/atlas` |

## Automated smoke

```bash
PYTHONPATH=src python scripts/operational_smoke.py
```

Pasos: env → `Orchestrator.status` → Hermes REST → ciclo editor approval en workspace temporal → Telegram outbound (si tokens presentes).

Opciones:

```bash
PYTHONPATH=src python scripts/operational_smoke.py --skip-telegram
PYTHONPATH=src python scripts/operational_smoke.py --workspace ~/atlas
```

## Gate I — servicio 24/7

```bash
# Foreground (Telegram + OfflineMonitor)
atlas serve

# Health JSON
atlas health
curl -s http://127.0.0.1:7331/api/health   # si ATLAS_SERVE_DASHBOARD=1

PYTHONPATH=src python scripts/gate_i_smoke.py
```

systemd user unit: copiar `scripts/atlas-core.service` a `~/.config/systemd/user/` y `systemctl --user enable --now atlas-core`.

Env opcionales: `ATLAS_SERVE_DASHBOARD=1`, `ATLAS_THERMAL_MONITOR=1`, `ATLAS_PIPELINE_GATE_D=1`.

Smokes individuales (regresion):

```bash
PYTHONPATH=src python scripts/hermes_smoke.py
PYTHONPATH=src python scripts/pipeline_smoke.py
PYTHONPATH=src python scripts/inference_smoke.py
```

## Manual checklist

### 1. Status

```bash
atlas status
```

Esperado: Governance OK, Merkle chain OK, Hermes mode live (no offline).

### 2. CLI approval flow

```bash
atlas task "editor write projects/smoke.txt :: ok"
atlas pending
atlas approve <task_id>
atlas pending   # debe quedar vacio
```

Verificar fichero `~/atlas/projects/smoke.txt` y entrada Merkle `task.approval`, `approval.persisted`.

### 3. Telegram (manual)

Arrancar bot (desde Python o integracion existente):

```python
from atlas.core.orchestrator import Orchestrator
orch = Orchestrator()
orch.start_telegram_bot()  # requiere TELEGRAM_BOT_TOKEN en env
```

Desde el cliente Telegram autorizado:

- `/status` — resumen del core
- `/task modificar algo sensible` — debe pedir approval si aplica
- `/pending` — lista pendientes
- Aprobar con `/approve <task_id> <passphrase>` si `require_passphrase_for_approve: true` en `permissions.yaml`

### 4. Hermes delegation

Intent que clasifique como `DELEGATE_HERMES` (tarea larga / investigacion). Verificar en VPS cola o `scripts/hermes_smoke.py`.

### 5. Merkle audit

```bash
atlas audit
```

Buscar acciones recientes: `task.created`, `task.approval`, `hermes.delegated`, `pipeline.gate_d_enabled`.

## Pending approvals (v1 HMAC)

Ficheros en `~/atlas/memory/pending_approvals/<task_id>.json` usan envelope `{"v":1,"task":{...},"mac":"..."}`.

Ficheros legacy sin `mac` se **rechazan** al cargar. Borrar JSON viejos o re-enviar la tarea.

## Gate D + memoria vectorial

```bash
export ATLAS_PIPELINE_GATE_D=1
export ATLAS_MEMORY_VECTOR=1   # default; usar 0 para desactivar Kuzu
atlas task "lista los archivos"
```

Tras activar pipeline: Kuzu en `~/atlas/memory/kuzu/atlas.kuzu`, distiller y registros conectados.

## Troubleshooting

| Sintoma | Accion |
|---------|--------|
| `source .env` falla en zsh | Solo lineas `KEY=value` o `KEY="valor"` |
| Hermes offline | `tailscale status`, `scripts/hermes_smoke.py` |
| Pending no carga | Verificar `ATLAS_PENDING_HMAC_KEY` o `HERMES_API_KEY`; eliminar JSON legacy |
| Telegram no responde | Token, `TELEGRAM_CHAT_ID`, bot no en otro proceso |

## Evidence template (Gate G+)

```
Date:
Host:
atlas status: OK / FAIL
operational_smoke.py: OK / FAIL
CLI approve cycle: task_id=... OK
Telegram /status /pending: OK / manual skip
```
