# CONTINUATION_STATE — Atlas OS

Actualizado: 2026-07-10 (sesión Fable 5, master build prompt).

## Current Status

Primera versión final-compatible de la base Atlas OS: contratos (12 schemas),
Event Kernel (proyección del bus real, ADR-058), Backend Bridge read-only
(7341), UI shell dos-caras (ADR-059), Integration Fabric mock, governance
inicial fail-closed, Memory OS import con provenance. Todo con tests y
verificación en vivo.

## What Is Real

- Event Kernel: store JSONL + player + CoreEventBridge (proyecta el EventBus
  real del core con simulated=false).
- Bridge: /health, /reality (atlas reality real), /memory/summary (338
  registros del índice canónico, sqlite read-only), WS /events con push vivo.
- Memory import: raw preservado en disco, extracción rules_v1, idempotencia.
- UI: WS en vivo, pipeline encadenado, personalización persistida con efectos
  reales, probador de permisos contra el evaluador del bridge.
- Evaluador de permisos: lógica real fail-closed (sobre gates de fixture).

## What Is Simulated

- POST /intent → pipeline de eventos SIMULADO (marcado en cada evento y en la
  UI). No ejecuta nada en el core (a propósito: OS-R1).
- Conectores: TODOS mock (mode declarado en spec y visible en UI).
- El grafo servido por /graph es el fixture (badge FIXTURE en la UI); el grafo
  Kuzu real (4206 nodos) NO está aún en la UI (OPEN_QUESTIONS #3).
- Los gates del evaluador vienen de fixtures/governance/gates.json, no de la
  governance real del core.

## What Was Changed

Commits de la sesión (todos en main, sin push): docs fase 0-1 → Event Kernel →
Backend Bridge → atlas-shell UI → Memory import → continuidad. Un solo fichero
core tocado: `interfaces/cli.py` (+comando os-bridge, aditivo). `contracts.py`,
`event_bus.py`, `governance/*` intactos.

## Architecture Decisions Made

- ADR-058 (canon OS = proyección; bridge read-only; real-vs-sim contractual).
- ADR-059 (UI web-first Vite+React+d3-force; Tauri diferido).
- DECISION_REVIEW.md D1-D10 (incluye rechazos, abajo).

## Decisions Rejected

- Segundo event bus (pack §20) — duplicaba core/event_bus.py.
- docs/adr/ paralelo — el repo ya tiene docs/decisions/adr/.
- Tauri en v1 — node 18 + presión RAM; re-evaluable con digest.
- Cytoscape/Sigma hoy — d3-force basta para fixtures; digest cuando entre Kuzu.
- Registries de primitivas como tablas manuales — serían cascarón; nacen del
  pipeline real de digestión.

## Risks

Ver docs/risks/RISK_REGISTER.md (OS-R1..R11). Los tres letales: doble
Orchestrator (guard estático en test), hashes Merkle inventados (player los
rechaza), pisar cambios sin commitear del operador (add selectivo SIEMPRE).

## Next Best Tasks

1. Proyectar approval.required del core en el bridge y representar la cola
   HITL real (atlas pending) en Security Center — solo lectura primero.
2. /graph real: overview del grafo Kuzu (read-only, con swap-lock cuidado —
   el write-lock de Kuzu excluye lectores de otros procesos).
3. Gates del evaluador desde governance real (read-only) en vez de fixture.
4. Ingesta de os_import_v1 al índice canónico vía knowledge_ingest (respetando
   ADR-057).
5. Digest formal Gmail: wrap del MCP google-workspace vs conector nativo.
6. Demo 90s guiada (§17): los 13 pasos ya son posibles a mano; grabarla.

## How To Run

```bash
cd ~/proyectos/atlas-core && source .venv/bin/activate
PYTHONPATH=src atlas os-bridge          # bridge en 127.0.0.1:7341
cd ui/atlas-shell && npm install && npm run dev   # shell en 127.0.0.1:5173
```

## How To Test

```bash
PYTHONPATH=src ATLAS_NESTED_TEST_RUN=1 python -m pytest tests/test_os_*.py -q
MYPYPATH=src python -m mypy src/atlas/api/ src/atlas/events/
cd ui/atlas-shell && npm run build      # tsc strict + vite
```

## Known Failures

- Ninguno en los tests OS (54 tests verdes al cierre). Anomalía pre-existente
  del repo sin relación: multihop=0.0 en eval_longmemeval (anotada en ledger).

## Where To Continue

Leer EN ORDEN: este doc → docs/continuation/KNOWN_RISKS.md →
docs/architecture/ARCHITECTURE_MAP.md → ADR-058/059 → el código de
src/atlas/events/ y src/atlas/api/ (pequeño a propósito).

## Warning To Next AI

NO instancies Orchestrator en el bridge. NO toques WORK_LEDGER/AGENTS/backlog/
governance.json/carpeta 1/. NO `git add -A`. NO inventes merkle_hash. NO
añadas deps Python sin ADR. Regenera docs/INDEX.yaml al añadir docs. Todo lo
simulado se marca; si no puedes verificar algo, di UNVERIFIED en vez de
afirmarlo.
