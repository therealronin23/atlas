# Diseño — Catálogo como Resources MCP (slice 1)

Brainstorming 2026-06-25. Hueco #1 de `docs/design/mcp_six_primitives_audit.md`: el tronco navega el
catálogo SOLO por tool-calls (queman un turno por consulta). Lo exponemos también como **Resources** (el
"JSON índice para todo el MCP" que pidió el usuario). Aditivo: los tools (`trunk_catalog`/`find`) se quedan.

Backlog: `mcp-audit-six-primitives` (done) → este es su follow-up de implementación.

## Hechos que anclan el diseño (decide-with-facts)
- `mcp` instalado en `.venv` = **1.28.0** (floor `pyproject.toml:41` `mcp>=1.2` es solo suelo).
- Resource templates OK (`@server.resource("catalog://item/{kind}/{name}")`).
- Subscriptions SOLO en el Server low-level (`subscribe_resource`, `ResourceUpdatedNotification`);
  **FastMCP high-level NO expone push** → el push real es follow-up, no se finge (wire-before-claim).
- Loader vivo: `atlas.mcp.catalog.load_catalog(path) -> list[CatalogEntry]`. Items se identifican por
  **kind+name** (ya hay `dedupe_by_kind_name`). `CatalogEntry` tiene: name, sector, sector_label, kind,
  purpose, source, install, status, tags, mode, subsector, phase, version, license, trust, transport.

## Unidades

### Unidad 1 — `CatalogResources` (nuevo `src/atlas/mcp/catalog_resources.py`, SIN dep MCP, testeable solo)
Funciones puras sobre `list[CatalogEntry]`:
- `entry_id(e) -> str` → `f"{e.kind}/{e.name}"`.
- `manifest_json(entries) -> str` → JSON (indent 2, utf-8) con:
  - `summary`: `{total, by_status, by_kind}` (orientación barata).
  - `fresh`: hash sha256[:16] de `(kind,name,status,mode)` ordenado → cambia cuando el catálogo cambia
    (change-detection sin push).
  - `items`: lista de `{id, name, status, kind, domain, subsector, mode}` (los 4 ejes que pidió el
    usuario; `domain` = `e.sector`). Índice LIGERO: nombres + etiquetas, sin prosa.
- `manifest_hash(entries) -> str` → el `fresh` por separado (reutilizable).
- `item_detail(entries, item_id) -> str | None` → JSON con el `CatalogEntry` COMPLETO (todos los campos)
  o `None` si no existe. `item_id` = `"kind/name"`.

### Unidad 2 — cableado en `build_trunk_server` (`trunk_server.py`, dentro del `if catalog is not None`)
- `@server.resource("catalog://manifest", mime_type="application/json")` → `manifest_json(catalog)`.
- `@server.resource("catalog://item/{kind}/{name}", mime_type="application/json")` → `item_detail` con
  `f"{kind}/{name}"`; si `None` → `raise ValueError` (FastMCP lo traduce a error de resource).
- Serializa el catálogo EN MEMORIA (el que se cargó en `serve()`) — consistente con los tools actuales.
  Recarga-desde-disco-en-cada-lectura = follow-up (hoy `build_trunk_server` recibe la lista, no el path).
- URI `{kind}/{name}` (dos segmentos) evita el problema de slash-en-id de un solo `{id}`. Asunción
  documentada: `name` sin `/` (cierto en el catálogo curado; los seeded raros con `/` se acceden por el
  manifest, que es el camino robusto).

### Unidad 3 — subscriptions (push) — FOLLOW-UP HONESTO, no en este slice
FastMCP high-level no expone emisión de `resources/updated`. El push real exige el Server low-level +
watcher de mtime del catálogo + contexto de sesión. Se entrega el MECANISMO de detección (`fresh` hash) y
se registra el follow-up. NO se declara "subscriptions" hechas. Item de backlog nuevo:
`catalog-resources-live-subscriptions`.

## Errores / casos
- item inexistente → `item_detail` devuelve `None` → resource raise (no se inventa item vacío).
- catálogo vacío → `manifest_json` con `items: []`, `summary.total: 0`. Sin excepción.

## Tests (verify-the-real-case)
- Builder (sin MCP, corre siempre): forma del manifest (4 ejes + summary + fresh), `fresh` cambia al
  mutar status/mode y NO cambia al reordenar, `item_detail` encuentra por kind/name y devuelve `None` si no.
- Cableado (in-process FastMCP, como `tests/test_mcp_trunk_*`; corre en `.venv` con mcp 1.28): el resource
  `catalog://manifest` está listado y se lee como JSON parseable; `catalog://item/{kind}/{name}` devuelve el
  detalle de un item sembrado; item inexistente → error.

## Definition of done
Tests verdes + mypy strict (archivos nuevos/tocados) + `WORK_LEDGER.md` y `docs/backlog.yaml` en el mismo
commit (item de audit→este follow-up; nuevo item subscriptions pendiente; runway guard ≥3). wire-before-claim:
no se declara "subscriptions" — solo índice+detalle+fresh.
