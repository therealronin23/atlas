# Gate C — Seal

> **Evidencia histórica (2026-05-23), no estado operativo actual.** Este sello
> documenta el antiguo stub REST/Docker. No debe ejecutarse como runbook ni
> usarse para afirmar que Hermes, el VPS o Telegram están vivos. Autoridad
> actual: `atlas reality`, `docs/design/atlas_ecosystem_map.md` y ADR-026..029.

**Fecha:** 2026-05-23
**Estado:** COMPLETE
**Tests:** 147/147 passing

## Resumen

Gate C cierra con Hermes-VPS desplegado en infra real (Hetzner CPX22),
Tailscale tunnel operativo entre HP Omen y VPS, y `HermesRestAdapter`
verificado end-to-end contra el stub vivo. El tráfico Atlas↔Hermes va
cifrado por WireGuard sobre una IP `100.x` interna; el puerto 8443
del VPS no se expone a Internet (Tailscale provee el transporte).

## Infraestructura desplegada

- **VPS:** Hetzner Cloud CPX22 (`hermes-vps`), 2 vCPU AMD, 4 GB RAM, 80 GB disk.
- **OS:** Ubuntu 26.04 LTS.
- **Software en VPS:**
  - Docker Engine 29.5.2
  - `hermes-agent-stub:0.1` corriendo en contenedor `hermes-agent`, expone puerto 8443.
  - Systemd unit `hermes-agent.service` (auto-start tras reboot).
  - Tailscale 1.98.3, `tailscaled` enabled.
- **Software en HP Omen:**
  - Tailscale 1.98.3 conectado a la misma tailnet.

## Configuración Atlas Core

`.env` local (no commiteado, en `.gitignore`):
```
HERMES_BASE_URL=http://<tailnet-ip-vps>:8443
HERMES_API_KEY=<shared-secret-emitido-por-install_hermes_vps.sh>
```

## Smoke test verificado

Comando:
```bash
set -a && source .env && set +a
PYTHONPATH=src python scripts/hermes_smoke.py
```

Salida:
```
[1/4] health_check http://<tailnet-ip-vps>:8443 ...
      reachable=True mode=live version=stub-0.1.0
[2/4] enqueue_task echo ...
      accepted=True delegation_id=<uuid>
[3/4] get_queue_status ...
      depth=1 next=<uuid>
[4/4] cancel_task ...
      cancelled=True
OK
```

## Sub-objetivos

| Sub | Resultado |
|---|---|
| C1 — Hermes Agent en VPS | DONE: instalado vía `scripts/install_hermes_vps.sh`. |
| C2 — Tailscale tunnel | DONE: tailnet operativo, IP interna `100.x` usada para HERMES_BASE_URL. |
| C3 — HermesRestAdapter | DONE: 11 tests unit + smoke real PASS. |
| C4 — Telegram bot | DONE: skeleton + Orchestrator integration + approval flow + OfflineMonitor. |
| C5 — Cierre + tag | DONE (este documento + tag `v0.2-gate-c`). |

## ADRs cerrados o confirmados por Gate C

- **ADR-011** — Atlas↔Hermes: REST HTTPS + HMAC-SHA256, transporte Tailscale en producción. CONFIRMADO.
- **ADR-013** — Telegram auth: chat_id whitelist. CONFIRMADO en C4-s1.
- **ADR-017** — Tunnel: Tailscale (WireGuard). CONFIRMADO.

## Lo que NO se hizo en Gate C (consciente)

- El stub Hermes no ejecuta tareas reales — devuelve respuestas simuladas. Sustitución real va en Gate D junto al InferenceHub real y el SLM classifier.
- `OfflineFallbackMode` real con notificación a Telegram tras 15 min sin ping está implementado en código (C4-s2) pero no probado contra una caída real del VPS — se valida en operación.
- La rotación periódica de `HERMES_API_KEY` no está automatizada — manual por ahora.

## Siguiente

Gate D — InferenceHub real (LiteLLM, fallback chain Groq>OpenRouter>Together>Gemini>L0), SLM classifier, memoria vectorial (KuzuDB), MemoryDistiller.
