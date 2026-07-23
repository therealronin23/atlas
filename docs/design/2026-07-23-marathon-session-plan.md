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
- Track D: PLAN CERRADO, implementación en curso. Plan en
  `docs/superpowers/plans/2026-07-23-t5-provider-discovery-plan.md` — 8 tareas TDD
  (T1 provider_errors.py, T2 cablear en InferenceHub, T3 provider_discovery.py, T4
  model_catalog_drift.py, T5 provider_preflight.py, T6 tick maintenance, T7 reality,
  T8 cablear en SelfBuildRunner). Paralelizables: T1+T3. Cadenas: T1→T2;
  T3→T4→T6→T7; T3→T5→T8. Despachadas T1+T3 ahora.
