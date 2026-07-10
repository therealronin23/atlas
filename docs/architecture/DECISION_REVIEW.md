# DECISION_REVIEW — Atlas OS (2026-07-10)

Protocolo del master prompt aplicado a las decisiones heredadas (build pack +
handoff + prompt) contra el estado real del repo. Veredictos: KEEP /
KEEP_WITH_BOUNDARY / MODIFY / REPLACE / DEPRECATE / INVESTIGATE / REJECT.

## D1 — Event Kernel como módulo nuevo `src/atlas/events/`

- **Decisión heredada**: pack §20 propone `events/event_bus.py` +
  `event_store.py` + `schemas.py` nuevos.
- **Supuesto**: el repo no tiene sistema de eventos.
- **Riesgo actual**: FALSO el supuesto — existe `core/event_bus.py` (tipado,
  usado por orchestrator y hermes_webhook) y `transparency/` (Merkle). Crear
  un segundo bus = dos fuentes de verdad, el pecado que ADR-057 acaba de
  evitar en memoria.
- **Veredicto: MODIFY.** `src/atlas/events/` se crea pero contiene el **canon
  OS** (evento JSON serializable rico: risk/summary/causality/audit/ui),
  un **event store** JSONL append-only con replay, y un **bridge** que se
  SUSCRIBE al EventBus existente y proyecta `contracts.Event` → evento OS.
  `core/contracts.py` y `core/event_bus.py` NO se tocan (blast radius:
  orchestrator). El campo `audit` del evento OS referencia hashes del Merkle
  real cuando existen; nunca inventa hashes.
- **Evidencia**: grafo vivo (importers), REPO_AUDIT.md, dashboard.py:52-58.
- **Registra**: ADR-058.

## D2 — Backend Bridge: app nueva vs dashboard existente

- **Decisión heredada**: pack §08 propone `src/atlas/api/server.py` con
  /health /graph /timeline /intent /memory/summary + WS /events.
- **Supuesto**: no hay API. FALSO: dashboard.py (7331) + exec_api.py (HMAC).
- **Riesgo actual**: el bug documentado del **doble Orchestrator** — dos
  instancias escribiendo el mismo Merkle log corrompen la cadena. Un bridge
  que instancie Orchestrator repetiría el incidente.
- **Veredicto: MODIFY (KEEP_WITH_BOUNDARY del core).** App FastAPI nueva y
  separada (`src/atlas/api/`, puerto propio 7341) porque su ciclo de vida y
  su público (la UI OS) difieren del dashboard Jinja2; PERO en v1 es
  **read-only sobre el core**: reality, grafo Kuzu, memoria y transparency se
  leen; el único estado que ESCRIBE es su propio event store OS. Cero
  Orchestrator. POST /intent en v1 emite el pipeline de eventos marcado
  `simulated` (más adelante, integración real vía el singleton inyectado del
  service_runner, nunca instancia propia).
- **Registra**: ADR-058.

## D3 — Stack UI: Tauri + React (pack ADR-0005)

- **Supuesto**: hace falta desktop nativo desde v1.
- **Riesgo actual**: node 18.19 (Vite>5 exige node 20+); compilar Tauri mete
  toolchain Rust + webkit2gtk en el camino crítico de una máquina con 4GB de
  /tmp y historial earlyoom; y el valor v1 está en el shell reactivo a
  eventos, no en el empaquetado.
- **Veredicto: MODIFY.** v1 = **web-first**: Vite 5 + React 18 + TypeScript en
  `ui/atlas-shell/`, servida por el bridge (build estático) o `vite dev`.
  El pack ADR-0006 (renderer abstraction) se KEEP: el dominio/eventos viven
  fuera de React; Tauri queda como wrapper futuro documentado, no bloqueado.
- **Registra**: ADR-059.

## D4 — Librería de grafo para Living Knowledge Graph

- **Decisión heredada**: pack §14: React Flow para Orchestrator, Cytoscape/
  Sigma/custom para Living Graph.
- **Veredicto: MODIFY (v1) + INVESTIGATE (v2).** v1 usa SVG custom +
  `d3-force` (micro-dependencia enfocada, ~15kB) — los fixtures tienen
  decenas de nodos, no miles; meter Cytoscape hoy sería framework-as-kernel.
  Cuando el grafo real (4206 nodos de atlas-core en Kuzu) entre en la UI,
  investigar Sigma/WebGL con digest formal.
- **Registra**: ADR-059 + docs/continuation/OPEN_QUESTIONS.md.

## D5 — Schema de evento: pack vs prompt (contradicción detectada)

- **Conflicto**: pack (actor string, status enum, `visible` bool, flat) ≠
  prompt §13 (actor objeto, `causality`, `ui` hints, `visibility` enum).
- **Veredicto: MODIFY (fusión).** Base = pack (prioridad 4 > 5; y sus
  fixtures son la evidencia ejecutable) con lo del prompt que añade capacidad
  real como OPCIONAL: `causality` {parent_event_id, trace_id}, `audit`
  {merkle_hash, previous_hash, reversible}, `ui` hints, `simulated` bool.
  `actor` se queda string|null en 1.0 (los fixtures lo usan así); el actor
  estructurado {type,id} entra en 1.1 de forma aditiva. `visible: bool` se
  mantiene (más simple que el enum de 3 valores; additive después).
  `schema_version` = "1.0". Validación con **pydantic** (ya dep) espejando el
  JSON Schema; sin dependencia `jsonschema` nueva (invariante 6 de AGENTS.md).
- **Registra**: schemas/event.schema.json + src/atlas/events/schemas.py + test
  de fixtures contra modelo.

## D6 — Rutas de docs del prompt vs orden real de docs/

- **Conflicto**: prompt pide `docs/adr/`; el repo tiene
  `docs/decisions/adr/adr_NNN` (57 ADRs) + INDEX.yaml máquina + inbox/triage.
- **Veredicto: REJECT `docs/adr/` paralelo; KEEP convención real.** ADRs
  nuevos → `docs/decisions/adr/adr_058+`. Los 10 "ADR-000x" del pack quedan
  en docs/handoff/ como propuestas históricas; los que se aceptan se
  re-emiten con número real. `docs/continuation|architecture|risks|improvement`
  se crean (no colisionan) y se registran en INDEX.yaml vía
  `scripts/docs_index_audit.py --write`.

## D7 — `schemas/` y `fixtures/` en la raíz del repo

- **Veredicto: KEEP (pack).** Son contratos ejecutables, no docs curados; la
  raíz ya aloja config/ y scripts/. Tests los validan (contracts-first).

## D8 — Improvement Engine como sistema nuevo

- **Supuesto del pack**: no existe radar SOTA.
- **Riesgo**: duplicar lo vivo — el repo YA tiene investigación abierta
  autónoma (TopicExpander 128 hallazgos/noche), `research_digest` →
  candidatos de catálogo (digestión cableada al tick, commit e10c5bcc) y
  triage/ingesta a memoria con recall e2e.
- **Veredicto: KEEP existente + documentar.** `docs/improvement/` describe y
  enlaza el motor real; los registries (PRODUCT/PAPER/REPO_PRIMITIVES) nacen
  como salidas del pipeline real, no como tablas manuales muertas.

## D9 — WhatsApp y conectores outbound

- **Veredicto: KEEP (prompt §11) reforzado por invariantes propios**: todo
  outbound (email/mensajes/push) pasa por Gate + aprobación humana explícita;
  WhatsApp personal NO se automatiza (riesgo ToS documentado); en v1 los
  conectores son specs + mock/sandbox con credential_reference, sin secretos.

## D10 — "Copiar la bible al repo" (pack README paso 1)

- **Veredicto: MODIFY.** Se copia a `docs/handoff/` (hecho) como material de
  referencia con status propuesto, no a docs/ raíz como vigente. La doctrina
  útil se destila en docs/architecture/ y ADRs reales. Motivo: el propio
  operador considera que docs largos no curados contaminan (memoria
  feedback-root-docs-are-operator-curated).

## D11 — Rediseño visual JARVIS del shell (petición 2026-07-10 tarde)

- **Contexto**: el operador pidió acabado enterprise/JARVIS para atlas-shell;
  horas después entregó atlas_product_os_liquid_ui_pack_v1 cuyo DO_NOT_DO
  prohíbe "polish the web harness as final UX" y "cheap Jarvis".
- **Veredicto: SUPERSEDED.** El pack (constitución de producto más reciente)
  gana: el shell React queda declarado VALIDATION HARNESS (README en
  ui/atlas-shell/). La calidad visual final pertenece a la superficie nativa
  futura (Slint/wgpu, diferida) gobernada por UI_QUALITY_GATE. No se escribió
  código del rediseño; nada que revertir.

## D12 — Schemas laxos del pack vs patrón estricto del repo

- **Veredicto: MODIFY (endurecer).** El pack trae contratos con required:[] y
  additionalProperties:true; el repo valida contratos estrictos con espejos
  pydantic + tests de paridad. La "improvement law" de la constitución permite
  reforzar sin diluir: los 10 schemas núcleo de Fase 15 se escriben estrictos
  conservando los nombres de campo del pack.

## D13 — Prefijo de rutas API `/atlas/*` sugerido por el prompt

- **Veredicto: MODIFY.** El bridge existente expone rutas sin prefijo
  (/health, /events, /connectors...). Las nuevas superficies siguen el estilo
  vigente: /connections/*, /business/*, /integrations/health. Repo real >
  prompt.

## D14 — PolicyEngine nuevo vs evaluador v1 de gates

- **Veredicto: EXTEND, no duplicar.** El evaluador v1 (patrones de acción →
  gates.json, fail-closed) se mantiene para /permissions/evaluate. El
  PolicyEngine de Fase 15 CONSUME los mismos gates y añade capability,
  data_class, provenance e invariantes duros en código (no relajables
  borrando fixtures). Toda superficie nueva (connections/business) evalúa por
  PolicyEngine. Convergencia total = candidata Fase 16.
