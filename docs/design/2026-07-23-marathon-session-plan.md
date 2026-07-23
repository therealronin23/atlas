# Sesión maratón autónoma 2026-07-23 — plan de ejecución

Contexto: el operador pidió una sesión de ~7-8h sin interacción, "lo mejor que puedas
hacer, cualquier bloqueante lo resuelvas" (Cónclave para decisiones N3, autorización
amplia de herramientas). Instrucción explícita: **calidad sobre cobertura superficial**
— no tocar las 6 secciones T1-T6 a medias, mejor 2-3 tracks bien hechos que 6 rotos.

Este doc es el mapa de ruta vivo de la sesión — se actualiza a cada cierre de track,
no al final.

## Datos reales que fijan la prioridad (de `corpus_digest_consolidated.json`, 708 docs)

- `alimenta_item` por sección: T1=33, T0=33, T4=22, T2=16, T3=9, T6=9, T5=6.
- `candidata` por sección: 19 sin sección clara, T2=7, T0=3, T1=2, T4=1, T5=1.
- T0 ya está mayormente cerrado (sesiones previas + hoy); sus 33 alimenta_item son
  refinamiento, no gap estructural — baja prioridad esta noche.
- T6 requiere decisión N3 de dinero+credenciales (redeploy VPS real) — fuera de alcance
  de una sesión autónoma sin el operador presente. Se registra su backlog, no se
  ejecuta el redeploy.

## Tracks de esta noche (por prioridad)

### Track A — T1.5 Coding Territory (ADR-068), el más grande y de más juicio

Disección adopt-real de Aider (Apache-2.0) y OpenHands (MIT): clon efímero, medir en
3 tareas reales contra AtlasCoder, veredicto **Cónclave real** (no mi solo criterio —
es requisito explícito del propio ítem del plan maestro), envolver al ganador como
motor de código de Atlas (proveedores del hub, lecciones del sustrato, ceremonia de
ruta dorada alrededor). Evidencia de cierre: tarea de código real completada por el
motor absorbido con proveedores de Atlas, cero tokens Claude del operador, medición
comparativa registrada.

Expectativa honesta: esto es multi-hora incluso bien hecho. Objetivo mínimo de esta
noche: disección + medición + veredicto Cónclave completos y documentados. Si queda
tiempo, arrancar el envolvimiento del ganador (al menos 1 tarea real end-to-end).

### Track B — Extracción del backlog de los 162 documentos (129 alimenta_item + 33 candidata)

Paralelizable por sección T (T1, T4, T2, T3, T5, T6 — T0 se deja para el final o se
omite si no da tiempo). Por cada cluster: subagente lee los docs reales asignados,
NO copia títulos mecánicamente — decide con criterio si cada uno ya tiene backlog real
o hace falta una entrada nueva en `docs/backlog.yaml`, con redacción propia y cita de
fuente. Esto responde directamente "qué queda de los documentos" con hechos, no bultos.

### Track C — T4.2: industrializar el pipeline candidata→diseccionada→absorbida

Construye el mecanismo (hoy manual) y lo prueba en vivo contra los 33 `candidata`
reales del corpus (primera víctima real, no sintética). Evidencia: informe de
disección + entrada en `atlas_ecosystem_map.md` con estado, para al menos 2-3
candidatas reales procesadas de principio a fin.

### Track D — T5: sistema de disponibilidad de proveedores antes de iterar

La idea que planteó el operador esta noche: no solo probar contra `DEFAULT_PROVIDERS`
fija (ya existe, T5.1), sino descubrir qué modelos hay disponibles contra una fuente
viva y exponer disponibilidad/límites/errores ANTES de lanzar trabajo pesado. Diseño +
implementación acotada (T5.2/T5.3), con TDD real.

## Reglas de ejecución (heredadas de esta sesión, no reinventar)

- Nunca declarar un track cerrado sin verificar yo mismo (`pytest`, no solo confiar en
  el subagente).
- Auditoría final agregada (autobuild-auditor) antes de cerrar cada track grande.
- Ledger de autobuild + entrada en `WORK_LEDGER.md` al cerrar cada track.
- Commits separados por track, nunca un mega-commit.
- Cualquier cosa que requiera decisión del operador (dinero, credenciales, alcance
  N3 que Cónclave no pueda resolver por sí solo, ambigüedad genuina de producto) se
  registra en la sección "Cola para el operador" de este doc — NO se bloquea la
  sesión por ello, se sigue con el resto.

## Incidente real: límite de sesión (2026-07-23, madrugada)

Los 6 agentes de la ola 3 fallaron simultáneamente con "You've hit your session
limit · resets 4:10am (Europe/Madrid)". Exactamente el riesgo que el operador
anticipó al pedir la maratón ("necesito que tengas en cuenta los límites de sesión").
Estado parcial encontrado en el árbol (sin commitear, no roto — tests existentes
siguen en verde): `src/atlas/core/tool_coder.py` (+25, de toolcoder-process-sandbox,
incompleto), `src/atlas/core/verify.py` (+8, de irreversible-action-verifier,
incompleto). NO se commiteó nada a medias. Reloj del sistema ya marca las 07:37 CEST
(pasado el reset declarado) — se prueba un redespacho único antes de relanzar los 5
restantes, para no gastar más intentos si el límite sigue activo por otra razón.

## Ola 2 — tras cerrar los 4 tracks principales (sigue la maratón, backlog real)

Con Track A/B/C/D cerrados, se sigue trabajando el backlog recién creado (71 ítems,
32 pending). Elegidos 5 de prioridad p2/p3, backend/lógica pura (sin verificación
visual/GUI necesaria, sin dinero/infra): `t1-golden-route-vocabulary`,
`t1-soul-devil-advocate`, `t1-radar-missions-draft`, `t4-sentinel-tool-coherence`,
`t1-error-registry-lesson-promotion`. Despachados en paralelo, sin solape de ficheros.

## Olas 2-5 — resumen (backlog real, tras cerrar los 4 tracks principales)

- **Ola 2** (5/5 cerrados): golden-route-vocabulary, soul-devil-advocate,
  radar-missions-draft, sentinel-tool-coherence, error-registry-lesson-promotion.
- **Ola 3** (6/6 cerrados, sobrevivió un límite real de sesión con reset a las 4:10am
  — retomados sin perder trabajo): daemon-control-surface, toolcoder-process-sandbox,
  plugin-contribution-consumers, irreversible-action-verifier,
  harness-adapter-contract-registry, governance-fixture-to-real.
- **Ola 4** (6/6 cerrados, 1 resultó ya estar implementado — evitado duplicar):
  git-checkpoint-agentic-wiring, mcp-installer-e2e-wiring, mem-fact-time-vs-system-time,
  project-graph-vault-wiring (ya hecho), openapi-to-capability-compiler,
  node-identity-module.
- **Ola 5** (CERRADA): f2-6b-1-gen-judge-pairs, f2-6b-2-judge-vs-baseline-runner,
  f2-6b-3-verdict-report, t6-workload-benchmark-harness. Los dos últimos fallaron
  una primera vez por un SEGUNDO límite de sesión real ("resets 12:30pm Europe/Madrid",
  distinto del de la madrugada) dejando estado parcial correcto pero incompleto
  (`tests/benchmarks/judge_verdict_report.py` sin escribir, solo su test rojo;
  `scripts/benchmark_workload.py`/`tests/test_benchmark_workload.py` completos pero
  con 1 test real en rojo). Al retomar la sesión tras el reset: implementación de
  `judge_verdict_report.py` completada (11/11 tests, incluye un fix real de
  redondeo de punto flotante en el límite exacto del umbral del 10%); bug real
  encontrado y arreglado en `analyze_bottleneck()` (el flag `gpu_offloads_llm_to_gpu`
  se sobreescribía con el último workload iterado en vez de hacer OR entre todos —
  17/17 tests); mypy limpio en ambos ficheros nuevos. Benchmark real ejecutado en
  este HP Omen (`--fast`, todos los workloads salvo `browser_tasks`, que se
  autodocumenta `skipped` por falta de `playwright` en el venv): cuello de botella
  real = throughput de CPU, no VRAM (confirmado por `ollama ps` en vivo); resultado
  completo en `docs/knowledge/benchmarks/workload_benchmark_2026-07-23.json` y
  resumen en `docs/operations/atlas_box_architecture.md` §"Resultado real".

**Restante del backlog (~19 ítems)**: casi todos son T2.1 (micro-PoCs Flutter/Compose/
Qt, Mission Console dedicada) o T3.1/T3.2 (operador GUI universal) — necesitan
verificación VISUAL real (capturas, lanzar la app, confirmar que se ve bien), que un
agente de fondo sin ojos no puede autoverificar con garantía. Dejados
deliberadamente para cuando el operador esté presente o para una sesión que use
Browser/computer-control-mcp de forma dirigida, no en background ciego.

## Cierre de la maratón (2026-07-23, ~12:55 CEST)

El operador pidió cerrar lo pendiente y volver con un resumen para empezar una
sesión nueva. Ola 5 cerrada (arriba). Sin más ítems de backlog ejecutables sin
GUI/dinero/credenciales pendientes de esta sesión — el resto es la cola para el
operador (abajo) más el trabajo GUI deliberadamente diferido. Suite completa:
4113 passed, 10 failed (mismos 10 preexistentes de `mcp` faltante, cero
regresiones nuevas), 41 skipped.

## Cola para el operador (se rellena según aparezca, vacía al empezar)

- **Confirmar revocación real del secreto OAuth viejo de Google Workspace** en la
  consola de Google Cloud (Track B/T5, `docs/operations/oauth_rotation_google_workspace.md`)
  — el wrapper y el scrubbing del `.claude.json` ya están verificados en código, pero
  la revocación en la consola de Google solo la puede confirmar el operador.

## Estado de tracks (vivo)

- Track A: EN CURSO — 2 disecciones despachadas en paralelo (Aider, OpenHands).
  Pendiente tras ambas: diseñar+correr las 3 tareas de medición comparativa contra
  AtlasCoder, veredicto Cónclave real, envolver ganador.
- Track B: **CERRADO** — 6 secciones completas (T1=11, T2=8, T3=4, T4=1, T5=1, T6=4
  = 29 ítems nuevos), fusionados en `docs/backlog.yaml` (42→71, sin colisión de IDs)
  y commiteado (`7f2c63b`). Incluye edición cosmética ADR-059 (SUPERSEDED→ADR-071).
- Track C: **CERRADO** — pipeline documentado (`docs/design/2026-07-23-t42-candidata-pipeline.md`),
  33 candidata triadas (31 sin acción, 2 reales disecadas y añadidas al mapa: Atlas
  IDE/Void fork PENDIENTE, atlas-editor-zed PARK). Hallazgo real: trabajo YA existente
  en disco sin documentar. 48/48 tests, commiteado (`382a8a4`).
- Track D: **CERRADO (8/8 tareas, 5 commits: f0726a4/dad8ba3/1f6e8cd/1395050)**. Plan en
  `docs/superpowers/plans/2026-07-23-t5-provider-discovery-plan.md` — 8 tareas TDD
  (T1 provider_errors.py, T2 cablear en InferenceHub, T3 provider_discovery.py, T4
  model_catalog_drift.py, T5 provider_preflight.py, T6 tick maintenance, T7 reality,
  T8 cablear en SelfBuildRunner). Paralelizables: T1+T3. Cadenas: T1→T2;
  T3→T4→T6→T7; T3→T5→T8. Despachadas T1+T3 ahora.
