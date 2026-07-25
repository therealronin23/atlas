# Diseño — Precisión del pipeline de discovery MCP + fuentes curadas

Brainstorming 2026-07-25, tras la auditoría completa del proyecto. Root cause identificada de por qué
`mcp_catalog_classified.yaml` acumula ruido (`java-bst`, `manyana` VCS toy, etc.): `PanoramaScout._search_github`
ordena por `sort=updated` sin mínimo de estrellas, y ningún paso del pipeline juzga relevancia semántica real —
`TopicExpander` solo genera las queries, `research_digest.py` (deliberadamente puro, sin LLM) solo cuenta
repeticiones (`≥2 temas` o `≥2 informes`). Dos queries expandidas sin relación real pueden coincidir por azar de
keywords y colar un candidato irrelevante.

Alcance: NO toca `adopt_mcp_server` ni el invariante `sensitivity="high"` (ADR-075 I5). Solo mejora qué entra en
`status: candidato`. La auto-adopción real (ADR-076 sección C, rechazada 3/3 por el Cónclave) es una spec aparte.

## Estado actual (workbench://manifest, 2026-07-25)
Catálogo: 2845 total — 16 `instalado`, 5 `verificado`, **2824 `candidato`** (todo del pipeline viejo, sin vetting
de calidad real). `mcp_servers.json` solo carga 2 servidores reales (`atlas-trunk`, `computer-control-mcp`).

## Piezas

### 1 — Fuentes curadas (`docs/knowledge/curated_sources.yaml`)
Fichero plano, editado a mano por el operador: lista de `{url, note}` (ej. registro MCP de Vercel, tododeia.com,
un repo suelto encontrado fuera del pipeline). `PanoramaScout.discover()` lo lee en cada ciclo y lo inyecta como
hallazgos adicionales — **mismo formato que un hallazgo automático** (`### [github|web] title` + `tema:`/`url:`/
`seed:`). Decisión explícita del operador: sin atajo de confianza — compite en el mismo embudo que todo lo demás
(pieza 3 incluida). Si nunca acumula señal suficiente ni pasa el veredicto, no se propone, igual que cualquier
hallazgo automático.

### 2 — Filtro de estrellas en `PanoramaScout._search_github`
Se mantiene `sort=updated` (no perder lo emergente). Se añade el calificador `stars:>=N` a la query de búsqueda
de GitHub (filtro server-side, no post-fetch). Default `N=5`, configurable vía `ATLAS_MCP_DISCOVERY_MIN_STARS`
(mismo patrón que `ATLAS_MCP_RESEED_INTERVAL_S`).

### 3 — Trazabilidad del seed + veredicto LLM de calidad/relevancia
**3a.** El formato de informe (`_render_research_report`) gana una línea nueva `- seed:` — hoy `TopicExpansion`
(`topic_expander.py::expand_detailed`) ya conoce el seed amplio original (ej. "memoria de agentes de IA") que
generó cada query corta, pero se pierde al aplanar a `queries: list[str]`. Hay que enhebrar `expand_detailed`
hasta el render en vez de `expand`.

**3b.** Módulo nuevo `mcp_discovery_quality_gate.py`, mismo patrón de inyección que `security_council_gate.py`
(`judge_fn: Callable[[CandidateSuggestion, JudgeContext], QualityVerdict]`, `build_llm_judge_fn(hub)` para
producción, stub determinista para tests). Se ejecuta después de `digest_findings` (que sigue puro, sin tocar)
y antes de `append_candidates_to_catalog`. Una sola llamada LLM barata por candidato ya deduplicado (no por
hallazgo crudo).

El prompt compara contra **dos anclas**, no una:
- el **seed amplio original** (de 3a), no la query corta que lo encontró;
- un **resumen compacto de lo que Atlas ya tiene** (sectores + conteo `instalado`/`verificado`, ya disponible
  vía `workbench://manifest`, sin fetch nuevo).

Salida: `{real_mantenido: bool, relevante_al_seed: bool, cubre_hueco_real: bool, motivo: str}`.
**Gate duro:** `real_mantenido AND relevante_al_seed` (obligatorias). `cubre_hueco_real` NO es gate — es señal
registrada en `motivo`/`evidence` para que el humano que revise `vetted` sepa si es redundante o llena un hueco,
sin bloquear alternativas genuinamente mejores a algo ya instalado.

Fail-closed: si el LLM falla o no responde en el formato esperado, el candidato **no se propone** esta vez — no
se pierde permanentemente, se reintenta solo si vuelve a aparecer con señal en un ciclo futuro.

Coste: solo candidatos NUEVOS que pasan estrellas + señal ≥2 (hoy ese conjunto es pequeño por ciclo, no los 2824
acumulados).

### 4 — Barrido de limpieza (una vez, manual, DESPUÉS de 1-3 en producción)
Script `scripts/mcp_catalog_reset_candidates.py`: filtra `mcp_catalog_classified.yaml` dejando solo entradas con
`status != candidato` (preserva los 16 `instalado` + 5 `verificado` intactos). Elimina los ~2824 `candidato` del
pipeline viejo. No es destructivo de verdad — git conserva el historial completo (`git show` recupera cualquier
entrada si hiciera falta). Ejecución manual, una sola vez — nunca automático, para que no se repita por
accidente ni borre candidatos nuevos ya vetados con el pipeline mejorado.

**Orden de ejecución obligatorio:** 1 → 2 → 3 en producción primero; 4 se ejecuta después, a mano. Invertir el
orden dejaría al daemon (ya activo con `ATLAS_MCP_RESEED=1`/`ATLAS_MCP_VETTING=1` desde 2026-07-25) repoblando
el catálogo con la lógica vieja antes de que la mejorada esté lista.

## Fuera de alcance (decisión explícita)
- Distinción "adoptar / aprender sin implantar / forkear" — sigue siendo juicio humano en la revisión de
  `vetted`, no se automatiza aquí.
- Re-vetting retroactivo de candidatos previos a esta spec — la pieza 4 los borra, no los re-juzga.
- Cualquier cambio a `adopt_mcp_server` / `sensitivity="high"` / auto-adopción — spec aparte (ADR-076 C).

## DoD
Tests por pieza (fixtures deterministas para `judge_fn` inyectado, sin red real en CI) + mypy limpio + ledger.
Pieza 4 requiere confirmación explícita del operador en el momento de correrla (irreversible en la práctica
aunque recuperable por git, y afecta un fichero de 25k+ líneas).
