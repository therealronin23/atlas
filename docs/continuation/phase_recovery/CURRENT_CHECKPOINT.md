# CURRENT_CHECKPOINT — Phase Recovery (2026-07-11)

Producido al inicio de la auditoría de recuperación de fases F1-F16, antes de
tocar ningún fichero de código.

## Estado del repo al arrancar

- **Branch**: `main`.
- **Commit**: `4faaf70f` (`docs(os): cierre Fase 16 — continuidad, riesgo del
  daemon paralelo documentado`).
- **`atlas reality --json`**: `dirty=true`, `dirty_count=15`, workspace Merkle
  `status=ok` (7136 registros), browser ready, MCP configurado (2 servers),
  LLM configurado (groq/openrouter/gemini).

## Commits recientes (25)

```
4faaf70f docs(os): cierre Fase 16 — continuidad, riesgo del daemon paralelo documentado
847a18c2 feat(os): F16-6 arnés UI mínimo honesto para /connections + /business + /gates
63f8fa60 feat(os): F16-4 primer conector real — Gmail read-only, cliente propio stdlib (ADR-065, Cónclave)
9b36c7bc feat(os): F16-7 Legal/ToS registry por conector
69b6eff3 feat(os): F16-5 Sector Registry + Objective Registry formales
967b7870 feat(os): F16-8 personal_channel estructural — invariante no evadible por nombre
6ee54104 feat(os): F16-3 persistir sesiones de onboarding a disco
df8f9910 feat(os): F16-2 Gate Engine real — tickets auditables para activaciones (ADR-063)
51c57c77 feat(os): F16-1 converge /permissions/evaluate con PolicyEngine (ADR-062)
be85665f fix(os): auditoría Fase 15 — mata código muerto, cierra huecos de test, honestidad en docs
a1ead24e docs(os): cierre Fase 15 — ADR-060/061, gap real de gates fijado, continuidad completa
cd3fd214 feat(os): API /connections + /business + CLI (Fase 15)
13f724f8 feat(os): Atlas Business Core + Adaptive Question Engine + Legacy Link (Fase 15)
63932f44 test(os): corpus de seguridad Fase 15 — escenarios de política + ataques
986c77f0 feat(os): Integration Fabric + Easy Connection Layer + PolicyEngine (Fase 15)
50293445 feat(os): contratos Fase 15 — 10 schemas estrictos + espejos fabric/business + paridad
bac77283 docs(os): ingesta atlas_product_os_liquid_ui_pack_v1 + alineamiento y plan Fase 15
fb914400 docs(os): continuidad completa — CONTINUATION_STATE, NEXT_AI_INSTRUCTIONS, docs por kernel
7f161bee feat(os): Memory OS Fase 8 — import de conversaciones con raw preservado y provenance
1ced8944 feat(os): atlas-shell — Cognitive Surface + Control Plane web-first (ADR-059)
2902350e feat(os): Backend Bridge 7341 — read-only sobre el core, WS de eventos, fabric mock, evaluador fail-closed
2e20312a feat(os): Event Kernel — canon 1.0, store JSONL+replay, bridge del bus real (ADR-058)
44bd8971 docs(os): Atlas OS fase 0-1 — auditoría forense, decision review, ADR-058/059, handoff packs
d70b75e0 fix(memory): fetch_longmemeval resuelve el symlink del cache HF antes de enlazar
8500c3c7 feat(loop): cableado único del facade — benchmark_gate + embedder del grafo + call-graph + digestión
```

Nótese: NO hay commits etiquetados "Fase 5/6/7/9/10" explícitamente en los
mensajes de git — esos números vienen de `docs/continuation/IMPLEMENTATION_LOG.md`
(narrativa retrospectiva), no de los commits en sí. `1ced8944` (shell) y
`7f161bee` (memoria import) son los commits reales detrás de esas fases
narrativas.

## Ficheros sucios (dirty) — TODOS del operador, NO tocar

```
 M WORK_LEDGER.md
 M docs/design/mcp_catalog_classified.yaml
 D feedback-absorb-without-cloning.md
 M scripts/README.md
 M scripts/eval_longmemeval.py
 M scripts/redteam/README.md
 D start_prometheus.sh
?? atlas_fable5_handoff_v1.zip
?? atlas_os_build_pack_v1.zip
?? atlas_product_os_liquid_ui_pack_v1.zip
?? docs/decisions/adr/adr_057_memory_canonical_by_use_case.md
?? docs/knowledge/research_2026-07-11.md
?? mcpevo.md
?? scripts/hermes_local.sh
?? scripts/ollama_cpu.sh
```

Estas rutas coinciden EXACTAMENTE con el `git status` al inicio de la sesión
anterior (Fase 16) y con el inicio de esta sesión — nada fue tocado por mí en
el intervalo. Los 3 ZIP aparecen como `??` (no trackeados) porque nunca se
commitearon como binarios — se ingirieron descomprimidos a `docs/handoff/`
(ver `PACK_LOCATION_REPORT.md`), que sí está trackeado.

## Estado en vuelo (in-flight)

Ninguno. La Fase 16 quedó cerrada y commiteada de punta a punta en la sesión
anterior (9 commits, suite completa 3200 passed/1 skipped verificada, memoria
guardada). No hay ronda a medias, no hay ledger de `.autobuild/` con trabajo
pendiente de esta sesión. Es seguro empezar la auditoría de recuperación de
fases sin parchear ni terminar nada primero.

## Seguridad para auditar

**SÍ, el árbol está seguro para auditar.** Razones:
- Cero cambios sin commitear que sean míos.
- Los 15 paths dirty son 100% del operador (ya documentado en 3 sesiones
  previas, ver `docs/continuation/REPO_AUDIT.md` y `KNOWN_RISKS.md` #2/#3).
- El daemon de autoconstrucción (`ATLAS_SELF_BUILD=1`) puede seguir vivo en
  paralelo (ver `KNOWN_RISKS.md` #12) — antes de escribir código nuevo en
  cualquier fase de backfill, se re-verificará `git status` y `ps aux | grep
  ATLAS_SELF_BUILD`.

## Próxima acción exacta

Proceder a **Fase 1 — localizar e indexar los 3 packs ZIP**
(`PACK_LOCATION_REPORT.md`), ya iniciada en paralelo a este checkpoint.
