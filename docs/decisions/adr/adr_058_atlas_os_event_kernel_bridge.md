# ADR-058 — Atlas OS: canon de eventos como proyección + bridge read-only

- Estado: aceptado (2026-07-10)
- Contexto: arranque de Atlas OS (master prompt Fable 5 + build pack en
  `docs/handoff/`). El pack propone crear bus/store/API nuevos; la auditoría
  (docs/continuation/REPO_AUDIT.md) encontró que EventBus, TransparencyLog,
  dashboard FastAPI y exec_api YA existen, y que instanciar un segundo
  Orchestrator corrompe la cadena Merkle (bug documentado en dashboard.py).

## Decisión

1. **Canon OS = capa de proyección, no segundo bus.** `src/atlas/events/`
   contiene: el modelo pydantic del evento OS (espejo de
   `schemas/event.schema.json`, fusión pack+prompt según DECISION_REVIEW D5),
   un event store JSONL append-only con replay bajo
   `workspace/os_events/` (fuera del árbol git), y un bridge suscriptor que
   proyecta `contracts.Event` (EventType existente) → evento OS. Ni
   `core/contracts.py` ni `core/event_bus.py` cambian.
2. **Bridge HTTP nuevo y separado**: `src/atlas/api/` con app FastAPI propia
   en `127.0.0.1:7341` (el dashboard 7331 no se toca; exec_api sigue igual).
   En v1 el bridge es **read-only sobre el core**: lee reality, grafo Kuzu,
   memoria y transparency; escribe únicamente su propio event store OS.
   **Prohibido instanciar Orchestrator** — si algún día ejecuta intents
   reales, será vía el singleton inyectado por `runtime/service_runner`
   (patrón `set_orchestrator` ya existente).
3. **Real vs simulado es parte del contrato**: todo evento OS lleva
   `payload.simulated: bool` cuando su origen no es el runtime real, y
   `audit.merkle_hash` solo puede venir del TransparencyLog real (nunca
   inventado). La UI muestra la distinción.
4. **Sin dependencias Python nuevas**: fastapi/uvicorn/pydantic ya están en
   pyproject. Validación de schemas con pydantic (no `jsonschema`).

## Consecuencias

- El OS puede crecer (UI, conectores, gates visuales) sin tocar el núcleo
  auditado; el núcleo puede seguir evolucionando sin romper la UI (contrato =
  schemas/ versionados).
- El replay OS es independiente del Merkle: el Merkle sigue siendo la
  autoridad de auditoría; el event store OS es la autoridad de REPRESENTACIÓN.
- Riesgos residuales en docs/risks/RISK_REGISTER.md (OS-R1, OS-R2, OS-R9).
