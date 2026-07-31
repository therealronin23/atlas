<!-- GENERADO por atlas handoff 2026-07-31T01:25:00.683989+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-07-31 — auditoría de mis propios diffs (encontró fallos reales),
  Cónclave con quórum real (FAIL), ADC-WO-108 CERRADO (5/5), 2 dossiers de
  decisión nuevos + 1 hallazgo de seguridad, higiene de worktrees.**
  **Auditoría de mis 3 diffs propuestos**: los tres eran pseudo-diffs
  ilustrativos que `git apply --check` rechazaba — ninguno era el "listo
  para aprobar" que afirmé. Regenerados como parches reales (verificados
  aplicables): STATUS.md (4807 passed medido hoy, no 4794), backlog.yaml
  (t4-workbench-compliance-review-tick → done), decisión nº10 en
  OPERATOR_DECISIONS_REQUIRED.md (ADC-WO-124, colocada al final, no entre
  el 4 y el 5 como en mi primer borrador). Hallazgo colateral contra mí:
  `WORK_LEDGER.md` llevaba parado desde `117b788`, así que el pack de
  sucesión regenerado en la Fase 1 NO había quedado fresco de verdad
  (`handoff.estado_body()` copia literal el bloque `## WHERE`) — corregido.
  **Cónclave: quórum 3/3 real por primera vez, veredicto FAIL.** Dos
  causas raíz arregladas con evidencia medida: tope de tiempo por-intento
  → presupuesto total (`ac0243c`, 360s→123s), fallback de linaje
  inalcanzable por nivel → recorrido de niveles (`5b912d6`), linaje CN
  invertido porque `nvidia_glm` se cuelga siempre (`7936cad`, medido 3
  veces distintas: 123s→9.2s). Con las tres voces respondiendo, el
  veredicto real sobre el stack T2.1 es **FAIL**: el benchmark de
  referencia (una pantalla) es demasiado estrecho para extrapolar a ~20
  pantallas — no descalifica a Qt, exige medir con más carga antes de
  comprometerse.
  **ADC-WO-108 CERRADO, las 5 piezas** (único WO `READY` del canon):
  tick de Orchestrator (opt-in, cadencia 24h, Merkle), eventos runtime al
  EventBus real (Merkle SIEMPRE antes que el bus, verificado por un test
  que resuelve el audit_ref desde dentro del propio suscriptor), proyección
  read-only en la API (`GET /engineering/findings`, sin verbos mutantes),
  hipótesis graph/history/memory (compone QUERIES+git log+LessonStore, sin
  motor nuevo — verificado con datos reales: 5 importadores, 14 en radio
  de impacto, 101 commits), producción de correcciones (invariante no
  negociable "no patch application from a finding" — solo enruta el
  patch_ref que el finding YA carga a `ColdUpdateManager.propose()`, nunca
  aplica ni aprueba). `src/atlas/engineering/` pasó de 2209 líneas
  dormidas a con callers reales.
  **2 dossiers de decisión nuevos** (ADC-WO-107, ADC-WO-124) con evidencia
  medida, no opinión. ADC-WO-107: 13 de 21 rutas POST del bridge 7341
  mutan estado real; hallazgo nuevo — `business/core/activate`/`reject`
  ejecutan aprobación completa SIN separación de proceso, más grave que el
  caso ya conocido (`permissions/approve`, que sí usa un subprocess CLI).
  **Hallazgo de seguridad ADC-WO-124**: `computer-control-mcp==0.3.10`
  saltó por completo el pipeline de vetting de ADR-075 (0 apariciones en
  ambos informes de catálogo, `pip install` directo ya ejecutó código de
  build) — registrado con hash del árbol/licencia/deps/semgrep reales (14
  rutas, 0 hallazgos), NO se tocó la instalación ni el catálogo.
  **Higiene de worktrees**: de 11 a 5. Verificado ANTES de tocar nada
  (commits sin mergear + ficheros sucios) que 6 eran seguros (0/0) y 5 NO
  lo eran — dos `atlas-doc0-rc2-*` con **639-640 commits sin mergear cada
  uno** (mi plan original los daba por restos pequeños, estaba mal
  informado), `atlas-definitive-convergence` con 4 commits reales, y el
  worktree de cold-updates que es un proposal `proposed` EN VIVO (jamás
  tocar). 1 cuarentena vencida confirmada por el tool real
  (`sanitation_audit.py`, no por la nota vieja del ledger que decía 2) —
  documentada, NO borrada (acción de `git rm` queda a decisión del
  operador). `component_wiring_drift` batcheado (una conexión Kuzu, no
  una por módulo): medido 10.01s→5.43s contra el matrix real de 142 filas.
  **Estado medido**: full suite 4829 passed/0 fallos (494.57s, checkpoint
  DESPUÉS de cerrar ADC-WO-108, ANTES del fix de rendimiento).
  **Pendiente real, grande, sin empezar**: dossiers completos de
  ADC-WO-102 (falsifier = bench de recuperación sobre TaskPersistence,
  nunca ejecutado) y ADC-WO-103 (falsifier = LongMemEval n=500 completo,
  herramientas ya existen: `scripts/fetch_longmemeval.py` +
  `scripts/eval_longmemeval.py`, solo falta correrlas a escala completa).
  El resto de las 6 decisiones REQUIRES_OPERATOR (100/102/103/105/107/124)
  siguen sin resolver — son del operador, no mías.
