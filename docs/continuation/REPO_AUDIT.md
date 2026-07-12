# REPO_AUDIT — Atlas OS build (Fase 0, 2026-07-10)

Auditoría forense del repo real ANTES de construir Atlas OS. Fuente de verdad:
`atlas reality --json` (commit d70b75e0, v0.12.0, dirty=12 rutas del operador)
+ grafo vivo (trunk MCP) + lectura dirigida. Los paquetes handoff están en
`docs/handoff/` y son GUÍA, no ley (orden de prioridad: repo > evidencia >
handoff > build pack > prompt).

## Stack real

| Pieza | Estado |
| --- | --- |
| Python 3.12.3, `uv`/pip, pyproject | 227 ficheros src, 2957 tests (suite completa VERDE 2026-07-10, 3:48, pico 1.9GB) |
| CLI | `atlas = atlas.interfaces.cli:cli` (click): reality/doctor/health/audit/dashboard |
| Web | **fastapi + uvicorn YA son dependencias.** `interfaces/dashboard.py` (puerto 7331, Jinja2 + JSON: /api/status, /api/health, /api/observability, /api/providers, /api/agentic/progress) y `interfaces/exec_api.py` (ADR-027: /api/exec/* HMAC + endpoints Merkle /entries /tree /proof) |
| Eventos | `core/event_bus.py`: EventBus in-process tipado sobre `core/contracts.py` (Event: type/payload/id/producer/task_id/timestamp; EventType enum PEQUEÑO — security, hermes, cold_update) |
| Auditoría | `transparency/`: TransparencyLog + MerkleLogger + gateway (6863 registros vivos en ~/atlas) |
| Memoria | `memory/`: memory_system (SystemContextLoader/ErrorRegistry/ApprovedPatternStore/ProviderMetricsStore), vector_store, Kuzu (project_graph, callgraph, obsidian), knowledge_ingest, lesson_index |
| Governance | `governance/` + config/governance.json (INTOCABLE) + pipeline CapabilityIssuer/PermissionProfile/AtlasExecutor + gates |
| Orquestación | `core/orchestrator.py` + InferenceHub + lazo de automejora (daemon/scheduler) + MCP trunk (atlas-trunk: graph_*, trunk_invoke*) |
| Observabilidad | `monitoring/prometheus_exporter.py` |
| UI toolchain | node v18.19.1, npm 9.2.0, cargo/rustc 1.95.0 — Tauri COMPILARÍA pero node 18 limita Vite a v5; sin UI JS existente en el repo |

## Colisiones build-pack ↔ repo real (lo que NO hay que duplicar)

| Build pack propone | Ya existe | Veredicto |
| --- | --- | --- |
| `src/atlas/events/event_bus.py` | `core/event_bus.py` (importado por orchestrator, hermes_webhook) | NO duplicar el bus; `src/atlas/events/` = canon OS + store + replay, PUENTEADO al bus existente |
| `src/atlas/api/server.py` | `interfaces/dashboard.py` + `exec_api.py` | App bridge nueva SOLO lectura del core en v1 (ver riesgo Merkle abajo); no montar segundo Orchestrator |
| Event canon rico (risk/summary/causality) | contracts.Event mínimo | Canon OS = capa nueva serializada (schemas/), mapping desde EventType existente; contracts.py NO se toca |
| MerkleLogger/audit | transparency/ completo | Reusar; el campo audit del evento OS referencia el Merkle real |
| Memory Vault | memory/ completo | Bridge de lectura; NO nueva memoria |
| Gates/policies | governance/ + config | Evaluador del bridge delega en lo existente; UI solo visualiza |

## Peligro nº1 detectado

`dashboard.py` documenta el **bug del doble Orchestrator**: dos instancias
escribiendo el mismo log Merkle desde locks distintos CORROMPEN la cadena.
El runtime real inyecta el singleton vía `set_orchestrator()`
(runtime/service_runner). Regla para el bridge v1: **cero instanciación de
Orchestrator**; solo lecturas (reality, graph Kuzu, memoria, transparency) y
eventos propios en store propio.

## Governance de docs (real)

- `docs/INDEX.yaml` máquina, generado/validado por `scripts/docs_index_audit.py`
  (216 entradas limpias al inicio de sesión). Todo doc nuevo debe registrarse.
- ADRs viven en `docs/decisions/adr/adr_NNN_slug.md` (último: adr_057). El
  prompt pide `docs/adr/` — se rechaza: convención real gana.
- Docs raíz (README, AGENTS, WORK_LEDGER, backlog) los cura el OPERADOR: no
  editarlos sin proponer diff. `WORK_LEDGER.md` tiene cambios sin commitear del
  operador → no tocar ni commitear; proponer entrada en chat.
- Carpeta `1/` = cuarentena, no leer.

## Estado git al inicio

main, 57 commits por delante de origin (NO push sin permiso), 12 rutas dirty
del operador (se preservan; jamás `git add -A`). Hook pre-commit vivo (~7s).
Daemon del lazo puede estar activo: guardia ATLAS_NESTED_TEST_RUN ya cableada.

## Handoff packs (docs/handoff/)

- `atlas_fable5_handoff_v1/`: specs UI/backend/continuation/quality + prompt.
- `atlas_build_pack/`: atlas-bible (21 docs + 10 ADRs propios), 4 schemas JSON,
  5 fixtures JSONL + grafo inicial. Los 10 ADRs del pack son PROPUESTOS, no
  vigentes; se reconcilian en DECISION_REVIEW.
- Contradicción detectada: el schema de evento del prompt (§13: actor objeto,
  causality, ui hints) ≠ schema del pack (actor string, status enum, visible
  bool). Se reconcilia en Fase 2 (pack como base por prioridad, campos del
  prompt como objetos opcionales).
