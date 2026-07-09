# Fusión Graphify → Obsidian → Kuzu — diseño y evidencia (2026-07-09)

**Estado: propuesto** (inbox/triage). Cubre las misiones `graphify_download_study`
y `graphify_obsidian_kuzu_fusion_design` del backlog con datos MEDIDOS, no especulados.

## Qué es Graphify (estudiado en ~/proyectos/graphify-study, clon completo)

Pipeline `detect → extract(AST) → build(NetworkX) → cluster → analyze → report → export`.
Para código es **100% local y determinista**: tree-sitter AST, sin LLM, sin embeddings,
sin API key. La extracción semántica (docs/PDF/imágenes) es opcional y solo con
Gemini o el agente anfitrión. Etiqueta cada arista con confianza
EXTRACTED/INFERRED/AMBIGUOUS — trail auditable, alineado con nuestra norma de
procedencia verificable.

- Paquete PyPI: `graphifyy` (doble y); CLI/skill por plataforma (`/graphify`).
- Exports nativos: JSON (GraphRAG-ready), HTML interactivo, **vault Obsidian**
  (una nota .md por nodo con [[wikilinks]] + frontmatter YAML), **Cypher**, Canvas,
  GraphML, SVG. Servidor MCP incluido (`python -m graphify.serve graph.json`).

## Corrida real sobre atlas-core/src (2026-07-09)

| métrica | valor |
|---|---|
| corpus | 225 ficheros, ~168k palabras |
| grafo | 4206 nodos, 10485 aristas, 154 comunidades |
| confianza | 81% EXTRACTED, 19% INFERRED, 0% AMBIGUOUS |
| coste LLM | 0 tokens (AST puro) |
| vault Obsidian | 4360 notas generadas |
| god nodes top | Orchestrator, MerkleLogger, SSRFBridge, DeferredHub |

Los god-nodes y comunidades coinciden con la arquitectura real (Orchestrator,
InferenceHub, ToolCoder, SelfBuildRunner, Cónclave…) — validación externa gratis
del mapa del sistema. Salida en `~/proyectos/atlas-graph/graphify-out/`.

## La cadena de fusión (cada eslabón probado hoy)

1. **Graphify → Obsidian**: nativo (`export.to_obsidian`). 4360 notas. HECHO.
2. **Obsidian → estructuras Atlas**: `atlas.memory.obsidian_vault.parse_vault`
   (nuestro, committeado). Digiere el vault completo: 26.392 wikilinks,
   21.201 tags. HECHO.
3. **Obsidian → Kuzu**: `obsidian_to_kuzu.load_vault_into_kuzu` (nuevo).
   Kuzu es schema-first: DDL idempotente `ObsidianNote` + `LINKS_TO`, wikilinks
   resueltos por stem (convención Obsidian), `ingested_at` como gancho
   bitemporal. Kuzu 0.11.3 ya estaba en el venv (KuzuVectorStore Gate-D).
4. **Capa bitemporal**: misión `kuzu_bitemporal_schema` pendiente — extender el
   esquema con valid_from/valid_to + transaction time sobre el gancho ya dejado.

## Usamos / Adaptamos / Descartamos

- **USAMOS entero**: pipeline AST, exports Obsidian/Cypher/HTML, informe con
  confianzas, servidor MCP (candidato a entrar por el catálogo del tronco como
  server de solo-lectura sobre graph.json).
- **ADAPTAMOS**: la resolución wikilink→Kuzu es nuestra (Graphify exporta Cypher
  para Neo4j/FalkorDB con MERGE laissez-faire; Kuzu exige esquema — por eso el
  cargador propio, ~90 líneas). El vault convive con nuestro parser sin tocar
  Graphify (manifest anti-clobber de Graphify respetado: nunca pisa notas ajenas).
- **DESCARTAMOS (por ahora)**: extracción semántica con Gemini (regla: embedder/
  LLM local primero), instalación de skill per-IDE (ya tenemos routing propio),
  watch/hooks siempre-encendidos (el PreflightGate/radar cubre eso).

## Prior art

`lucasrosati/claude-code-memory-setup` (⭐832): fusión Obsidian+Graphify como
memoria persistente de agente (afirma 71,5× menos tokens/sesión). Nuestra
diferencia: el grafo aterriza en Kuzu (queryable con Cypher embebido, sin
servidor) y se ancla al sustrato verificable (Merkle) en vez de a ficheros sueltos.

## Siguiente paso propuesto

Regenerar el grafo tras cada lote de ColdUpdate aprobado (gancho post-apply) y
cargar el delta en Kuzu — el mapa del sistema deja de ser un artefacto puntual
y pasa a ser memoria estructural viva que Cónclave/decisor/recaller consultan.
