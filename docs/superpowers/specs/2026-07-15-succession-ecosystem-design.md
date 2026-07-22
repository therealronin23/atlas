# Sucesión + Ecosistema — diseño B+C (2026-07-15)

Estado: **borrador aprobado en arquitectura** (sección 1 aprobada en chat; secciones
2-6 presentadas vía este doc para ahorrar tokens de sesión — pendientes de revisión
del operador). Enfoque elegido por el operador: **B + C** ("b y c").

**Auditoría MAXIMUS Cycle 9 (2026-07-22)** — secciones 2-6 contrastadas contra el
estado REAL del repo (no solo releídas). Resumen por sección, detalle completo en
WORK_LEDGER.md:
- **§2 (`atlas handoff`)**: 4/6 deliverables (a-d) ya existían; (e) mapa del
  ecosistema resumido y (f) primeros 10 minutos NO existían — implementados hoy
  (`05_ECOSISTEMA.md`/`06_PRIMEROS_10_MINUTOS.md`, TDD, 8 tests nuevos). Cabecera
  `GENERADO...NO EDITAR`, determinismo y fail-cerrado: verificados, tal cual.
- **§3 (migración de memoria)**: HECHA y verificada en vivo — 60 registros
  `harness:*`/`doctrine:*` reales en el sustrato (`~/atlas-mcp/memory.db`),
  criterio de partición (`user` excluido) exactamente como se especificó.
- **§4 (onboarding + F2.6)**: F2.6 como rúbrica PROBADA dos veces (PRIME Cycles 6
  y 8) pero NO como `atlas onboard` ni gate automático recurrente — sigue
  siendo invocación manual. El "primeros 10 minutos" de esta sección es
  literalmente lo que §2(f) pedía; implementado ahí, no duplicado aquí.
- **§5 (mapa del ecosistema)**: existe (`atlas_ecosystem_map.md`, desde
  2026-07-07, ANTES de esta spec) pero con una taxonomía DISTINTA a la
  propuesta aquí (raíces/tronco/ramas/hojas/savia) — usa categorías
  Core/Capability/Adapter/MCP Surface/etc. + estados SELLADO/ACTIVO/PENDIENTE/
  PARK/VAPOR/MURO. Nunca se reconciliaron; la implementación real es más
  granular que la propuesta y no vale la pena migrar. Dos filas corregidas hoy
  (A1/A2 marcadas PENDIENTE cuando A3 ya cerró el camino completo). El "radar
  de deriva" (pieza en disco sin fila en el mapa) que esta sección pide **NO
  existe** como detector dedicado — `sanitation_audit.py` no lo cubre.
- **§6 (testing/errores)**: verificado tal cual — `FUENTE NO DISPONIBLE`
  fail-cerrado real, TDD real en `atlas handoff`.

**No perseguido esta vuelta** (fuera del bounded cycle, señalado para decisión
del operador): wirear F2.6 como gate automático tras cambios grandes; detector
de deriva ecosystem-map↔disco; reconciliar o abandonar formalmente la taxonomía
árbol de esta spec en favor de la ya construida.

**Decisión del operador (2026-07-22, cierre de sesión MAXIMUS)**: la taxonomía
raíces/tronco/ramas/hojas/savia de la Sección 5 queda **formalmente SUPERSEDED**
por la taxonomía real construida en `atlas_ecosystem_map.md` (Core/Capability/
Adapter/MCP Surface/etc. + SELLADO/ACTIVO/PENDIENTE/PARK/VAPOR/MURO) — no se
migra ni se abandona el mapa real; se abandona SOLO el vocabulario árbol de
esta spec, que nunca se implementó y ya no debe usarse como referencia viva.
El detector de deriva de Cycle 13 (`ecosystem_map_drift`, ver arriba) SÍ
implementa el espíritu de "pieza sin fila en el mapa" que esta sección pedía
— pero contra el mapa real, no contra un árbol paralelo.

Esto fue el arreglo rápido decidido explícitamente por el operador ("algo
rápido ahora, dejo apuntado para la sesión que lo haga bien") en vez de la
reconciliación completa, que es trabajo de ingeniería real y se deja
diseñado, no ejecutado, para una sesión futura dedicada:

**Diseño de la reconciliación completa (para sesión futura, NO ejecutar aquí
con presión de cierre)**:
1. Añadir una columna `Tramo` (raíz/tronco/rama/hoja/savia) a cada una de las
   51 filas de `atlas_ecosystem_map.md` — mapeo humano, no automatizable
   (requiere juicio: ¿el Decider protocol es tronco o savia? ¿MerkleLogger es
   savia o rama?). Estimado: 1-2h de trabajo de clasificación real, no de
   código.
2. Verificar que el mapeo produce una partición útil (cada Tramo debe agrupar
   piezas con blast-radius/ciclo-de-vida similar — si `Tramo` no predice nada
   que las columnas existentes ya no digan, es vocabulario decorativo y debe
   descartarse formalmente en vez de mantenerse a medias).
3. Solo si (2) confirma valor real: extender `ecosystem_drift.py` para poder
   filtrar/agrupar por Tramo (p.ej. "deriva solo en ramas", útil para priorizar
   qué auditar primero cuando el radar encuentra muchos hallazgos a la vez).
4. Actualizar esta spec (Sección 5) para apuntar al mapa real con Tramo en vez
   de describir un árbol que nunca existió como artefacto independiente.

## Contexto y decisiones previas

- Miedo nº1 del operador: sucesión de modelo — cuando Fable no esté, ningún driver
  (Sonnet/Opus/GPT) sabrá operar Atlas. Ver memoria succession-proofing-priority.
- Escenario de diseño (respuesta del operador): **por capas** — capa 1: cualquier
  driver opera Atlas vía harness+hooks+sustrato; capa 2 (destino): Atlas autónomo
  con sus propios motores ("Claude Code es un plus, no una dependencia").
- Hallazgo que motiva B: la memoria privada de Claude Code
  (`~/.claude/projects/-home-ronin-proyectos-atlas-core/memory/`, ~40 ficheros:
  manías del operador, decisiones, historia) es INVISIBLE para cualquier otro
  harness y para Atlas mismo. El traspaso real Fable→Atlas es migrar eso al sustrato.
- Evidencia que mata el enfoque A (pack estático): docs/continuation/ entero quedó
  obsoleto en 4 días. Los packs manuales se pudren.
- cipher: rol aún no claro para el operador → entra como pieza **candidata**
  (disección adopt-real antes de decidir), no como dependencia.

## Sección 1 — Arquitectura (APROBADA)

Principio: el conocimiento operativo vive en el sustrato; todo lo legible-por-humanos
se GENERA desde él. Cuatro componentes:

1. **Fuente única = sustrato**: atlas-memory (procedencia Merkle) + grafo Kuzu +
   WORK_LEDGER + `atlas reality`. Incluye migración de la memoria privada de Fable.
2. **Proyección generada**: comando `atlas handoff` regenera docs/handoff/ desde
   ledger+memoria+grafo+reality. Nunca se edita a mano (como INDEX.yaml).
3. **Onboarding ejecutable**: misión guiada de arranque para driver nuevo + test de
   sucesión (rúbrica 6/6, F2.6) como gate recurrente barato.
4. **Mapa del ecosistema como taxonomía árbol** con ciclo de vida por pieza y
   detección de deriva.

Relación con el plan toasty-hatching-pillow: F2 = "primera generación manual" del
pack; B+C se construye después sin bloquear F1-F5.

## Sección 2 — `atlas handoff` (proyección generada)

- Subcomando CLI (mismo patrón que `atlas reality`). Salida: docs/handoff/GENERATED/
  con: (a) estado vivo (reality + head del ledger), (b) quién-es-quién
  (actor_roles), (c) invariantes duros (extraídos de AGENTS.md + PolicyEngine),
  (d) top-N memorias de sustrato por clase con procedencia, (e) mapa del ecosistema
  resumido, (f) "primeros 10 minutos": secuencia exacta de arranque en frío.
- Cabecera obligatoria en cada fichero generado: `GENERADO por atlas handoff <ts> —
  NO EDITAR A MANO; regenerar con: atlas handoff`.
- Determinista dado el mismo sustrato (sin LLM en v0 — proyección, no redacción).
- Gate anti-podredumbre: el PreflightGate ya cablea drift de INDEX; se añade check
  de frescura (si HEAD avanzó N commits desde la última generación → aviso).

## Sección 3 — Migración de la memoria privada de Fable al sustrato

- Criterio de partición (decisión clave a validar con el operador):
  - **project/feedback/reference → sustrato** (atlas-memory con clase + procedencia
    "migrado de memoria-harness 2026-07"). Son conocimiento de Atlas, no del driver.
  - **user (identidad/preferencias personales del operador) → quedan en el harness**
    y además se resumen en actor_roles.md en lo operativo (p.ej. "docs raíz los
    cura el operador") sin datos personales.
- Mecánica: script one-shot que lee los .md de memoria (frontmatter ya tipado),
  ingesta vía API Python de atlas-memory, y deja los originales intactos (el
  harness sigue funcionando; el sustrato deja de depender de él).
- Verificación: recall de 5 memorias clave desde una sesión SIN acceso al dir
  privado devuelve el contenido con procedencia.

## Sección 4 — Onboarding ejecutable + gate de sucesión (C)

- Misión de arranque (`atlas onboard` o doc ejecutable): AGENTS.md → `atlas
  reality` → una ruta dorada de demo (GoldenRoute sobre repo fixture) con receipt.
  El driver nuevo APRENDE HACIENDO la ceremonia completa con aprobación humana.
- Test de sucesión (F2.6, hoy diferido por coste): rúbrica 6 ítems, sesión real
  `claude -p --model sonnet`. Como gate RECURRENTE: se corre tras cambios grandes
  (nueva fase, ADR nuevo), no en cada commit. Cada fallo = gap estructural →
  arreglo en sustrato/docs generados, jamás parche en el prompt del test.

## Sección 5 — Mapa del ecosistema: taxonomía árbol + ciclo de vida

- Taxonomía (palabras del operador formalizadas): **raíces** = fuentes (repo, vault
  Obsidian, graphify, APIs externas, candidatas como cipher) · **tronco** =
  absorción/routing MCP · **ramas** = motores (Orchestrator, GoldenRoute, Cónclave,
  research) · **hojas** = superficies (shell, CLI, bridge 7341) · **savia** =
  sustrato transversal (memoria+grafo+Merkle).
- Ciclo de vida por pieza: `candidata → diseccionada → absorbida → vigente →
  aparcada`. Ejemplos: cipher=candidata; Neo4j=aparcada; NotebookLM=capa humana
  (fuera del ciclo, documentada).
- Deriva: pieza en disco sin fila en el mapa → hallazgo del radar (detector nuevo,
  barato, corre con el daemon).

## Sección 6 — Errores, pruebas y fuera de alcance

- Testing: cada componente con TDD; `atlas handoff` con golden-file test sobre un
  sustrato fixture; migración con test de ida (ingesta) y verificación de recall.
- Errores: handoff falla CERRADO (si una fuente no responde, genera con sección
  "FUENTE NO DISPONIBLE" explícita — nunca silencio).
- Fuera de alcance v0: redacción LLM del pack, sincronización bidireccional
  harness↔sustrato, UI del mapa (UI sigue aparcada).

## Próximo paso

Revisión del operador de las secciones 2-6 → writing-plans → implementación
(después de cerrar F2-F5 del plan vigente).
