# WORK LEDGER — estado vivo (WHERE + próxima acción)

Regenerado desde cero el 2026-07-08 (los docs raíz previos fueron puestos en
cuarentena por el operador; historia anterior en `git log` y `docs/archive/`).
Disciplina: entradas nuevas ARRIBA, una línea de estado por frente, ledger corto
(≤40 entradas; al superar, plegar lo viejo a `docs/archive/`). Verificar antes
de escribir: `atlas reality --json`.

## WHERE

- **MAXIMUS Cycle 13 — detector de deriva mapa-del-ecosistema↔disco (spec
  B+C §5) (2026-07-22 22:40)** — cierra el último ítem de "vamos al lío".
  "Pieza en disco sin fila en el mapa" traducido determinista: ¿todo ADR
  real tiene su número citado en `docs/design/atlas_ecosystem_map.md`? Los
  ADR ya son el mecanismo establecido del repo para "decisión de
  arquitectura", y el propio mapa ya los cita como Evidence/Authority —
  reusar esa convención en vez de inventar un vocabulario de "pieza" nuevo.
  `atlas.core.self_maintenance.ecosystem_drift`: soporta cita individual
  (`ADR-072`) Y por rango inclusivo (`ADR-024..040`, cuando varios ADRs
  contiguos comparten una fila "SELLADO" — 2 rangos reales en el mapa hoy).
  **2 bugs propios cazados y corregidos ANTES de confiar en el resultado**:
  (1) el número se guardaba como int y perdía el cero-relleno (`ADR-99` en
  vez de `ADR-099`); (2) el sufijo-letra opcional (`013b`) chocaba con
  citas por nombre de fichero completo (`adr_072_supply_chain...md` —
  la "s" de "supply" se leía como intento de sufijo) — arreglado con
  `(?![a-z])` (el sufijo solo cuenta si NO sigue otra minúscula).
  **Primera corrida honesta, no maquillada**: 37 de 51 ADRs sin cita
  aparente — investigado ANTES de aceptar el número (no es ruido de mi
  detector: son 2 rangos reales, `ADR-024..040`/`ADR-026..029`, que
  colapsan 14 ADRs a una sola fila). Con soporte de rango: **23 ADRs reales
  sin fila** — verificado a mano, coincide exacto con la salida del
  programa. Es un hallazgo real de deriva acumulada, no un bug — mismo
  espíritu que `docs_graph_drift` (201 docs sin enlace, nunca maquillado).
  Wireado en `scripts/sanitation_audit.py` (`ecosystem_map_drift()`,
  fail-open) y en `PreflightGate._run_sanitation()` (nueva clave
  `ecosystem_map_drift`, gratis en cada preflight del lazo de
  autoconstrucción). 14 tests nuevos TDD; mypy canónico 288 ficheros 0
  errores; prove-it en vivo: 23 hallazgos reales, conteo verificado a mano.
  **Próxima acción real:** ninguna de las 4 tareas de "vamos al lío" queda
  pendiente. Reconciliar los 23 ADRs sin fila (añadirlos al mapa o
  confirmar que están cubiertos por prosa no-citable) es trabajo de
  contenido, no de código — decisión del operador si perseguirlo.
- **GitHub puesto al día — secreto OAuth real scrubbeado del historial +
  push forzado con lease + CI corriendo de nuevo (2026-07-22 22:20)** — el
  operador pidió ponerse al día con GitHub tras el hallazgo de Cycle 11
  (65 commits locales sin subir desde el 16-jul). Al intentar el primer
  `git push origin main`, **GitHub Push Protection lo bloqueó**: el
  secreto OAuth viejo (client ID Y secret en claro) estaba commiteado en
  `docs/operations/oauth_rotation_google_workspace.md` desde esta misma
  mañana (commit `aa2f8adc`, previo a esta sesión — no lo introduje yo,
  solo edité ese fichero después en Cycle 8) — nunca había llegado a
  GitHub, bloqueado justo a tiempo. **No se intentó "permitir" el secreto
  vía el enlace de GitHub** (habría dejado pasar la fuga en vez de
  arreglarla). Backup local creado ANTES de tocar nada (rama+tag), historial
  reescrito con `git filter-branch --tree-filter` (acotado a `main`, 668
  commits procesados, ~3 min) sustituyendo ambas cadenas por marcadores
  `[REDACTED-...]` — verificado con `git log -S<secreto> main` tras el
  rewrite: cero resultados, en fichero y en TODO el historial. Backup local
  borrado tras verificar el éxito (mantenerlo habría dejado la misma fuga
  al lado). Push normal rechazado por non-fast-forward (esperado, el
  historial cambió de hash); **`git push --force-with-lease origin main`**
  — la única vía correcta tras reescribir historia — avisado explícitamente
  antes de correrlo pese a tener autorización general ("hazlo tu sin
  miedo"), dado que force-push a `main` es su propia categoría de riesgo.
  Aceptado por GitHub: `origin/main` 110f2a4→7c7350b. **CI confirmado
  corriendo de nuevo** en el push (`in_progress` en vivo). Rama
  `origin/codex/self-audit-loop` revisada: ya está al día con su propio
  remoto (nada local pendiente) — vieja/muy divergida de `main` (612
  commits detrás), no tocada (fusionarla es decisión aparte, no pedida).
  **Nota de proceso**: el clasificador de modo automático bloqueó el
  `filter-branch` DOS veces (una antes de la autorización explícita del
  operador, otra después — la autorización en chat no basta, hace falta
  un ajuste de settings) y bloqueó varios comandos de limpieza posteriores
  (`reflog expire`, `gc --prune`) de forma inconsistente incluso tras
  permiso — quedó sin purgar el reflog/objetos inalcanzables localmente
  (no crítico: no se pushean, y `main` en sí ya está limpio).
- **MAXIMUS Cycle 11-12 — investigación CI + bug report a Graphify-Labs +
  F2.6 como gate automático recurrente (2026-07-22 21:40)** — "vamos al
  lío" del operador, separando lo que era mío de lo que no.
  **CI investigado** (no era un problema de GitHub): `origin/main` seguía
  exactamente en `110f2a40` (el último commit del 16-jul) porque **nadie
  había hecho `git push` en 6 días** — `main` local quedó 65 commits por
  delante (todo PRIME 1-10 + MAXIMUS 1-10). Trigger de CI, permisos de
  Actions, todo correcto — simplemente nunca recibió un push. Repo es
  PÚBLICO en GitHub; hacer push queda señalado para el operador, no
  decisión mía.
  **Bug de graphify/eCryptfs reportado** (autorizado explícitamente):
  github.com/Graphify-Labs/graphify#2109 — encontrado el issue previo
  relacionado (#1094, ya cerrado, que introdujo el cap de 200 bytes);
  el mío es el caso que ese fix no cubre (el cap asume NAME_MAX=255
  universal). Root cause + repro + fix sugerido (`os.pathconf` en vez de
  hardcodear), sin exponer contenido real del repo (ejemplo sintético).
  **F2.6 como gate automático** (spec B+C §4): `atlas.core.self_maintenance.
  f26_gate` — determinista, sin red ni LLM, mismo principio que
  `PreflightGate`: la rúbrica de 6 ítems sigue siendo una sesión LLM real,
  cara, deliberada — NUNCA se dispara sola. Lo que se automatiza es la
  DETECCIÓN de cuándo está debida: "cambio grande" (spec) = ADR nuevo desde
  el último run REGISTRADO (`atlas f26 record-run --result pass|fail
  [--at-sha SHA]`, el flag `--at-sha` es para backfill honesto de corridas
  pasadas). `f26_gate_status()` fail-honesto (git que falla nunca dice
  'current' por defecto). Wireado en `atlas reality` (`f26_gate` section,
  mismo patrón que `graph`/`provider_smoke`) y en `atlas f26 status`.
  17 tests nuevos TDD, mypy canónico 287 ficheros 0 errores.
  **Backfill real hecho, no cosmético**: registrada la corrida REAL de F2.6
  (PRIME Cycle 6: 6/6 vía subagente Sonnet frío; PRIME Cycle 8: ceremonia
  golden-route completa en Merkle, commit `07795a04`) como línea base —
  sin esto, `atlas reality` habría alarmado falsamente con "51 ADRs nunca
  revisados". Resultado en vivo, exacto: `due — 2 ADR(s) nuevo(s)` →
  ADR-072 y ADR-073 (los añadidos DESPUÉS de esa corrida real, durante la
  recuperación del worktree en PRIME Cycle 10) — ni de más ni de menos.
  **Próxima acción:** Cycle 13 — detector de deriva mapa-del-ecosistema↔disco
  (spec B+C §5), en curso.
- **MAXIMUS Cycle 10 — graphify restaurado con procedencia real; hook de
  producción confirmado ILESO al bug encontrado (2026-07-22 21:10)** —
  cierra el hallazgo bloqueado al final de Cycle 7 (el operador dio la
  fuente: github.com/Graphify-Labs/graphify). Verificado antes de instalar
  nada: el paquete PyPI real es **`graphifyy`** (doble-y) — el propio
  proyecto avisa que otros `graphify*` NO están afiliados; 93.681 estrellas,
  MIT, mantenimiento casi diario. `0.9.11` (la versión que
  `scripts/install-knowledge-hooks.sh` exige literal) confirmada real en
  PyPI, publicada 2026-07-09 — coincide con la época en que este repo la
  usaba. Instalada con `uv add --optional knowledge-graph "graphifyy==0.9.11"`
  — extra PROPIA, no `dev`: trae ~25 parsers tree-sitter transitivos
  (resolviendo de paso el misterio de Cycle 7 sobre esos mismos paquetes)
  que ningún test/mypy necesita; meterlos en `dev` habría hecho más pesado
  el job rápido de CI sin motivo. `pip-audit` limpio, mypy canónico 286
  ficheros 0 errores, suite completa 3773 passed/0 failed (sin regresión).
  **Investigación honesta de un bug real encontrado al verificar en vivo**:
  `scripts/update-knowledge-graph.sh` (el pipeline COMPLETO, invocado a
  mano) choca con `OSError: File name too long` en `graphify export
  obsidian` — investigado a fondo, no descartado a la primera. Root cause
  real: `$HOME` está montado sobre **eCryptfs cifrado**
  (`stat -f` → `Longnombre: 143`), con un límite EFECTIVO de nombre de
  fichero de 143 bytes en esta máquina — graphify asume 255 (su propio cap
  interno, `_cap_filename`, es de 200 bytes, calculado para el límite
  estándar). Confirmado sistémico, no un caso aislado: retirada una entrada
  duplicada/fuera-de-tema (paper de astrofísica sobre ALMA, falso positivo
  de las queries expandidas "repository mutation"/"document indexing" en
  `docs/knowledge/research_2026-07-10.md`, título de 164 bytes) que
  disparaba el crash — reintentado, y chocó con OTRO título distinto de 169
  caracteres. Recortar contenido uno a uno NO escala contra un límite de
  filesystem; no perseguido más allá de esa única limpieza (justificada por
  sí sola: duplicado + fuera de tema, no un intento de arreglar el bug).
  **Severidad real, correctamente acotada tras leer el hook con calma**:
  `.githooks/post-commit` (lo que corre en CADA commit real) NO llama a
  `update-knowledge-graph.sh` en absoluto — usa
  `graphify.watch._rebuild_code()` directamente, una ruta mucho más
  estrecha (solo `graph.json`/`GRAPH_REPORT.md`, código sin LLM) que NUNCA
  invoca `export obsidian`/`export neo4j`. El bug de eCryptfs es real y
  reproducible, pero solo afecta a quien corra el pipeline completo A MANO
  — no al hook automático que de verdad importa para `atlas reality`/uso
  diario. Confirmado con un commit real de este mismo ciclo: sin el aviso
  "could not locate a Python with graphify installed" de antes.
  **No perseguido, señalado para decisión futura (no es un accidente de
  esta sesión, es una incompatibilidad genuina graphify↔eCryptfs)**: o bien
  reportar el bug aguas arriba a Graphify-Labs (`_cap_filename` debería
  detectar el NAME_MAX real vía `os.pathconf`, no asumir 255), o mover
  `graphify-vault`/`graphify-out` fuera del `$HOME` cifrado si se quiere
  volver a correr el pipeline completo con regularidad.
  **Próxima acción:** ninguna pendiente de los 4 encargos de hoy — todos
  cerrados (CVEs, conector Google, spec B+C, graphify). Quedan las líneas
  ya señaladas en Cycles 7-9 (T0.5b paso 3, F2.6 gate automático, detector
  de deriva ecosystem-map, investigar por qué CI no corre en `main` desde
  el 16-jul) para cuando el operador las priorice.
- **MAXIMUS Cycle 9 — auditoría spec B+C secciones 2-6 + 2 deliverables
  reales cerrados (2026-07-22 20:30)** — a petición del operador
  ("auditoría de si se puede mejorar... una vez terminado hazlo"). Auditoría
  sección por sección de `docs/superpowers/specs/2026-07-15-succession-
  ecosystem-design.md` contra el estado REAL del repo (no solo releída):
  **§2** (`atlas handoff`) listaba 6 deliverables (a-f); solo (a)-(d)
  existían — (e) "mapa del ecosistema resumido" y (f) "primeros 10 minutos"
  nunca se construyeron, pese a que el pack se genera y usa activamente
  (regenerado 3 veces hoy mismo en esta sesión). **§3** (migración de
  memoria) verificada EN VIVO: 60 registros `harness:*`/`doctrine:*` reales
  en `~/atlas-mcp/memory.db`, criterio de partición exacto al spec (`user`
  excluido). **§4** (F2.6): probado 2 veces (PRIME Cycles 6/8) pero nunca
  como gate automático recurrente — sigue siendo invocación manual; su
  "primeros 10 minutos" es literalmente §2(f). **§5** (mapa del
  ecosistema): existe desde 2026-07-07 (ANTES que esta spec) con una
  taxonomía DISTINTA (Core/Capability/Adapter/... + SELLADO/ACTIVO/
  PENDIENTE/PARK/VAPOR/MURO) a la propuesta aquí (raíces/tronco/ramas/
  hojas/savia) — nunca reconciliadas; la real es más granular, no vale la
  pena migrar. El "radar de deriva" (pieza en disco sin fila en el mapa)
  que pide NO existe como detector — gap real, señalado, no perseguido.
  **§6**: verificado tal cual, fail-cerrado real.
  **Implementado** (los 2 deliverables reales, TDD): `ecosistema_body()` —
  parser determinista de la tabla `## Canonical Map` (conteo por estado +
  lista de ítems `PENDIENTE`, los más accionables para un driver nuevo;
  NUNCA redacción LLM, mismo principio "proyección no redacción" del resto
  de `atlas handoff`) → `05_ECOSISTEMA.md`. `primeros_10_minutos_body()` —
  secuencia estática y determinista (AGENTS.md → `atlas reality --json` →
  ruta dorada de demo con recibo → primer cambio real) → `06_PRIMEROS_10_
  MINUTOS.md`. `docs/design/atlas_ecosystem_map.md` añadido a
  `REPO_SOURCES` (contrato de frescura del manifest ahora también lo
  cubre). De paso, corregidas las 2 filas que el propio hallazgo de hoy
  dejó obsoletas: Supply-chain admission scan (A1) y Declarative
  PluginManifest v1 (A2) seguían marcadas `PENDIENTE` con "A3: ..." como
  next-action, cuando A3 completo (Cycles 2-4 de hoy) ya las cerró —
  fusionadas en una fila `ACTIVO` con los 3 módulos reales. 8 tests nuevos
  (parser de tabla + ambos bodies + integración con `generate_handoff`),
  34 verdes en `test_handoff.py`, suite completa 3773 passed/0 failed
  (+8 vs. el conteo de Cycle 7), mypy canónico 286 ficheros 0 errores.
  Pack real regenerado 2 veces (tras el código y tras la corrección del
  mapa) — `05_ECOSISTEMA.md` real muestra 8 PENDIENTE reales de un
  total de 37 filas, útil de verdad para un driver nuevo. Spec B+C
  actualizada con el resumen de esta auditoría y los gaps señalados,
  no perseguidos: F2.6 como gate automático, detector de deriva
  ecosystem-map↔disco, reconciliar/abandonar formalmente la taxonomía
  árbol de la spec.
- **MAXIMUS Cycle 8 — conector google-workspace reconfigurado: secreto fuera
  de argv (2026-07-22 20:00)** — corrección de un hallazgo del propio audit
  de hoy: la memoria de PRIME Cycle 2 decía "OAuth rotado", pero verificado
  en vivo (`ps aux | grep GOCSPX`) el secreto VIEJO seguía embebido en el
  `--mcp-config` de 2 procesos Claude Code corriendo — solo se había
  completado el paso 2 del runbook (guardar el secreto nuevo a salvo en
  `~/.config/atlas/google-oauth.env`, client `228819788474-...`), nunca el
  paso 3 (reconfigurar el conector). El operador confirmó haber rotado el
  client ID en Google Cloud Console (paso 1, credencial suya) y pidió que el
  paso 3 (edición de config, no manejo de credenciales) lo hiciera yo.
  Localizado `~/.claude.json` (config MCP de Claude Code, fuera del repo,
  fichero de texto plano — no algo oculto en UI de Electron como se
  documentó en 2026-07-17) → proyecto `atlas-core` → `mcpServers.
  google-workspace`. Editado: `command`/`args` apuntan ahora a
  `scripts/google_workspace_mcp_wrapper.sh --tool-tier core`, `env: {}` —
  el wrapper inyecta el secreto vía `safe_dotenv.py` (nunca en argv).
  Verificado antes de tocar la config viva: wrapper probado en aislado con
  los args reales (arranca limpio, sin ERROR de precondición). Verificado
  después: JSON sigue válido, cero coincidencias de `GOCSPX`/
  `344051770277` en todo el fichero. Efectivo desde el próximo arranque del
  conector (las 2 sesiones ya vivas conservan el argv viejo hasta
  reiniciarse — reiniciarlas no es mío, mataría sesiones activas).
  **Pendiente, explícitamente del operador**: confirmar que el secreto
  expuesto quedó REVOCADO en Google Cloud Console (no solo sustituido en el
  fichero local) — sin eso, el secreto que ya estuvo en claro en argv sigue
  siendo válido aunque ya no se use. Runbook actualizado con el estado real.
  Memoria de PRIME Cycle 2 corregida (decía "resuelto", no lo estaba).
- **MAXIMUS Cycle 7 — 4 CVEs reales eliminadas + 2 dependencias huérfanas de
  producción declaradas correctamente (2026-07-22 19:30)** — a petición del
  operador ("hazlo todo sin pausa"), tras el hallazgo del audit previo:
  `pip-audit` (el mismo gate que `PreflightGate` corre antes de cualquier
  auto-mejora) mostró 4 CVEs en 2 paquetes. `mcp==1.28.0` (CVE-2026-59950,
  fix 1.28.1): upgrade directo, dependencia real y activa. `gitpython==3.1.50`
  (3 CVEs, fix 3.1.51): investigado de dónde venía — lo traía
  `opentimestamps-client`, un paquete **sin una sola referencia en todo el
  repo** (ni en `pyproject.toml` ni importado en ningún `.py`) — huérfano de
  verdad, invisible al `vapor_audit` existente porque ese solo escanea
  `src/`, no paquetes instalados. Retirada la cadena completa
  (opentimestamps-client + opentimestamps + gitpython + gitdb + smmap).
  `pip-audit` limpio: 0 vulnerabilidades.
  **Error propio cometido y corregido en el camino, con evidencia completa**:
  al verificar consistencia con `uv.lock`, corrí `uv sync --frozen --extra
  mcp --extra dev` sin pensar en qué extras tenía el venv REALMENTE — `uv
  sync --frozen` sincroniza el venv EXACTO a los extras dados, así que
  borró paquetes de extras que no pasé: `fastembed` (extra `embeddings`) y
  `playwright` (extra `computer-use`), ambos en uso real esta sesión.
  Detectado por chequeo de imports post-sync (no por casualidad), corregido
  con `uv sync --frozen --extra dev --extra computer-use --extra embeddings
  --extra mcp` (el set real). **Lección**: nunca correr `uv sync --frozen`
  con un subconjunto de extras sin verificar antes qué tenía instalado el
  venv — pasa de "arreglar un CVE" a "borrar media suite" en un comando.
  **Hallazgo mayor, no planeado, surgido de mi propio error**: el resync
  correcto reveló que `mypy` ganó 3 errores nuevos que no existían minutos
  antes (`acp/server.py`, `tools/video_gen_tool.py`, `tools/image_gen_tool.py`
  — todos "Returning Any"/"cannot subclass has type Any"). Investigado a
  fondo: dos paquetes REALES, con imports perezosos marcados `# noqa:
  PLC0415` en código de producción SÍ WIREADO (CLI `atlas acp`,
  `image_gen_tool.py`/`video_gen_tool.py`), llevaban meses viviendo como
  instalaciones manuales sin declarar — `agent-client-protocol` (paquete
  `acp`, absorción Hermes-Agent 2026-07-18) y `fal-client` — **ninguno de
  los dos existía en `pyproject.toml` ni en `uv.lock`**. Barrido sistemático
  de TODOS los imports perezosos `# noqa: PLC0415` del repo (no solo los que
  mypy señaló) para no dejar un tercero suelto: `crawl4ai` confirmado
  correctamente aislado por diseño (venv separado, documentado); `playwright`/
  `uvicorn` ya declarados. Solo `acp`/`fal_client` eran el gap real.
  Corregido con `uv add --optional acp agent-client-protocol` + `uv add
  --optional media-gen fal-client` (no un `pip install` suelto — habría
  recreado el mismo anti-patrón que acabo de limpiar). CI (`ci.yml`)
  actualizado en paralelo: su job de `mypy strict` nunca sincronizó estas
  extras tampoco (solo `--extra dev`) — mismo gap, mismo root cause; añadido
  un paso de sync adicional con `--extra acp --extra media-gen` antes de
  mypy. **Hallazgo aparte, NO perseguido esta vuelta** (fuera del alcance
  pedido): CI no ha corrido en `main` desde 2026-07-16 — ninguno de los 9
  commits de hoy (PRIME+MAXIMUS) disparó un run; causa raíz desconocida
  (posible config de trigger/permisos de GitHub Actions, no diagnosticable
  solo con el repo local) — señalado para que el operador decida si
  investigar.
  **Verificación final, todo limpio**: `pip-audit` 0 vulnerabilidades, mypy
  canónico 286 ficheros 0 errores, suite completa 3765 passed/1 skipped/0
  failed (corrida 3 veces durante el proceso, siempre estable).
  **Próxima acción:** Cycle 8 (conector google-workspace) + Cycle 9
  (auditoría spec B+C), ya en curso sin pausa.
- **MAXIMUS Cycle 6 — T0.5b paso 2: clasificador semántico del corpus,
  mecanismo construido y corrido en vivo (2026-07-22 18:10)** — el operador
  pidió "a y b por orden"; (b) investigado antes de elegir (igual que
  Cycle 2): las "decisiones toasty" resultaron mayormente operator-gated
  (rotación de secret OAuth, revisión de spec B+C — no son mías de
  ejecutar) y F2.6 ya estaba resuelto (PRIME Cycle 8); T0.5b paso 2 (86% del
  corpus `sin_clasificar` tras paso 1) era el único candidato genuinamente
  accionable — y, verificado, usa `fastembed` LOCAL (sin coste de API ni
  cupo, contra la suposición inicial de que necesitaba "presupuesto propio").
  `atlas.knowledge.corpus_semantic_classifier`: `extract_plan_sections()`
  parsea T0-T6 de `atlas_master_plan.md §5` (acotado a esa sección, nunca se
  cuela contenido de `## 6`/`## 7`); `classify_corpus_semantically()`
  compara cada doc `sin_clasificar` contra las 7 secciones por coseno,
  reusando `_cosine_similarity` de `lesson_recaller` (mismo patrón de import
  cross-módulo que ya usa `memory_index.py`) y el umbral **0.5 YA MEDIDO**
  en la ola bootstrap del 2026-07-17 (no re-derivado). Solo toca
  `sin_clasificar` — nunca reinterpreta un bucket de paso 1; un doc bajo el
  umbral queda `sin_clasificar` con el score igual registrado (nunca
  confianza inventada). Límite heredado de esa misma medición documentado,
  no oculto: docs largos enteros diluyen la señal (~0.45) — el chunking que
  lo arreglaría es su propio trabajo, deliberadamente fuera de esta loncha.
  **Bug real cazado en el diseño de mis propios tests antes de correrlos**:
  un `_FakeEmbedder` de 1 dimensión no puede distinguir direcciones — el
  coseno es invariante a escala, dos escalares positivos cualesquiera dan
  1.0 siempre; rediseñado a vectores one-hot multi-dimensión. CLI `--semantic`
  en `atlas corpus-inventory` (wire-before-claim), embedder resuelto vía
  `atlas.memory.embeddings.default_embedder()` (mismo selector que memoria
  del tronco, gobernado por `ATLAS_EMBEDDER`). TDD real (RED → arreglo de mi
  propio bug de test → GREEN); 14 tests nuevos (incluye 2 CLI end-to-end),
  142 verdes en el área corpus+knowledge+recall+memory_index, mypy canónico
  limpio. **Corrida real en vivo sobre los 705 docs actuales del repo**
  (local, `ATLAS_EMBEDDER` default=fastembed, ~24s, cero llamadas de red):
  **sin_clasificar 86%→65%** (604→461; 143 docs reclasificados: T3=49,
  T4=43, T0=32, T2=15, T5=4). Spot-check manual de los 8 mejores y 5 peores
  matches: plausibles en los dos extremos (p.ej. `t51-provider-smoke-
  surfacing.md`→T5, `atlas_ecosystem_map.md`→T4, `f2_6_personal_factual_
  design.md`→T0 — todas defendibles). `docs/knowledge/corpus_inventory.json`
  (artefacto trackeado de PRIME Cycle 4, referenciado en INDEX.yaml)
  regenerado con el resultado real; `docs_index_drift`/`docs_graph_drift`
  verificados limpios (el drift de enlaces preexistente es idéntico al de
  Cycle 1, no mío). **Honestidad de alcance — T0.5b NO está cerrado**: el
  ítem T0.5.b del master plan pide, además de la clasificación, lista de
  GAPS + lista de CONTRADICCIONES + "plan v2 con fuentes citadas" — eso es
  síntesis/juicio real (no mecánico), explícitamente fuera de esta loncha;
  esta es la pieza algorítmica (paso 2), no T0.5.b completo. No toqué el
  texto vivo del master plan (`§7. Estado y próxima acción` es para cierre
  de TRAMO completo, no de un sub-paso; y `atlas_master_plan.md` es terreno
  del operador, no mío por diff directo).
  **Próxima acción:** paso 3 de T0.5b (síntesis de gaps/contradicciones/plan
  v2 — sesión de investigación propia, juicio real, no delegable a un
  ciclo MAXIMUS) — o volver a las decisiones toasty cuando el operador
  quiera resolverlas él (rotación OAuth, revisión spec B+C).
- **MAXIMUS Cycle 5 — SkillStore descubre plugins activados: cierra el gap
  real que Cycle 4 documentó (2026-07-22 17:20)** — el operador pidió "a y b
  por orden" tras el cierre de A3; (a) = este ciclo. `atlas.mcp.skills_store.
  SkillStore` ganó `plugins_active_root` opcional kw-only (default `None` =
  comportamiento IDÉNTICO al de siempre, los 6 tests preexistentes intactos
  sin tocar): descubre `<active_root>/<plugin_id>/skill/*.md` bajo namespace
  `plugin:<plugin_id>/<contribution_id>` — evita que un plugin pueda
  sombrear o confundirse con un skill nativo del mismo nombre (test
  dedicado). Sirve el DESTINO del symlink (no lo rechaza como haría
  `plugin_admission`: aquí el link ES el mecanismo, no una señal de
  manipulación). Guardia anti path-traversal en `plugin_id`/`contribution_id`
  (regex `^[a-z0-9][a-z0-9-]*$`, mismo charset que `_PluginId` del manifest)
  — probado con 2 intentos de escape (`../secret.txt`, `x/../../secret.txt`).
  Cableado en producción: `trunk_server.py` construye el store con
  `ATLAS_HOME/plugins/active` — el MISMO patrón de resolución que
  `adopted_servers_path()` y ~15 sitios más del repo (no inventé un nuevo
  helper compartido; seguí la convención existente, aunque duplicada, para
  no forzar un refactor de 15+ ficheros fuera de alcance de este ciclo).
  Único constructor de producción de `SkillStore` en todo el repo — cero
  otros call-sites que actualizar. TDD real (RED → GREEN); 10 tests nuevos
  (incluida una integración real con `PluginActivator`, no un doble), 16
  verdes en `test_mcp_skills_store.py`, 52 verdes en todo el área
  trunk_server+skills+capabilities+manifest (incluido el guard de
  `tool_overhead<=25`, intacto — no se añadió ninguna tool MCP nueva). mypy
  canónico limpio. **Prove-it EN VIVO fuera del arnés**: reconstruí el
  `SkillStore` con la MISMA construcción exacta de `trunk_server.py`
  (mismo `ATLAS_HOME`), materialicé+activé un plugin real, y `list_skills()`/
  `get()` lo sirvieron con contenido real sin reiniciar ningún proceso;
  revocado y limpiado al terminar, cadena Merkle real verificada íntegra.
  **Honestidad de alcance señalada, no nueva**: el registro de cada skill
  como MCP `Prompt` nativo sigue baked-in al arranque (propiedad preexistente
  del bucle de `trunk_server.py`, no algo que este ciclo rompiera ni
  arreglara) — un plugin activado necesita reiniciar el tronco para el
  descubrimiento vía Prompt, no para `get_skill`/`list_skills` (ya vivo).
  El tronco MCP corriendo en PID vivo hoy NO se reinició (acción de estado
  fuera de alcance de un ciclo de mejora; decisión del operador cuándo).
  **Próxima acción: (b)** — T0.5b paso 2 / las decisiones toasty / el master
  plan de ciclos PRIME (watchdog daemon, etc. — verificar cuáles siguen
  pendientes antes de elegir, varios PRIME Cycles 2-10 ya los cerraron).
- **MAXIMUS Cycle 4 — A3.3: activador reversible, CAMINO A (ADR-072/073)
  CERRADO de punta a punta para fuente LOCAL (2026-07-22 16:50)** — última
  loncha de A3, continuación directa de A3.2 (Cycle 3). `atlas.mcp.
  plugin_activator.PluginActivator`: consume EXCLUSIVAMENTE un
  `PluginReceipt.status=="issued"` (nunca el `MaterializationResult`
  original), re-verifica de forma independiente (`compute_tree_sha256`,
  extraído de `plugin_materializer.py` con test de guardia anti-deriva) que
  el árbol staged sigue siendo BYTE-A-BYTE el que el recibo describe — dos
  veces: en `activate()` y de nuevo en `approve_activation()`, porque son
  dos ventanas TOCTOU distintas (staging no está fs-locked, solo protegido
  por convención + re-verificación en cada punto de confianza, mismo
  principio que A2/A3.1). Aplica cada contribución como symlink bajo
  `<workspace>/plugins/active/<plugin_id>/<kind>/<contribution_id>.md`
  (fuente única — nunca copia bytes, mismo principio explícito del propio
  `SkillStore`). **Decisión de diseño**: activar consulta el `Decider` DE
  NUEVO (`mutating=True, requires_approval=True`) en vez de heredar el
  veredicto del recibo — un `admit`/aprobación de A2 fue evidencia, nunca
  permiso de instalación (promesa hecha explícita en la CLI desde Cycle 2,
  honrada aquí). `revoke()` NO consulta al decisor (retirar capacidad no
  necesita permiso, mismo principio que `ColdUpdateManager.rollback_applied`/
  `reject()`) y por defecto BORRA staging (`--keep-staging` para no
  hacerlo) — nunca toca nada fuera de `active_root`/`staged_root` (fijado
  con un canario en los tests). Wire-before-claim:
  `Orchestrator.plugin_activator()` (mismo patrón, reusa el MISMO
  `plugin_receipts()` — nunca reconstruye un broker propio) + CLI `atlas
  plugin activate` + `atlas plugin activation show/list/approve/revoke`;
  corregido de paso un mensaje de CLI ya obsoleto ("A3.3 pendiente") que
  Cycle 2 dejó en `plugin materialize` — ya no lo está. TDD real (RED
  import → GREEN, 1 bug propio de fixture cazado — misma fuente reusada dos
  veces en un test de reactivación, no un bug del activador; 1 colisión real
  de mypy documentada y resuelta: un método público `.list()` sombreaba el
  builtin `list` para anotaciones posteriores en la misma clase —
  independiente del orden textual, por cómo `from __future__ import
  annotations` resuelve strings contra el namespace completo de la clase;
  fix con alias a nivel de módulo, sin renombrar la API pública). 21 tests
  nuevos (19 unitarios + 2 CLI end-to-end), 108 verdes en toda el área
  plugins+golden-route+CLI, 238 verdes en el barrido orchestrator+decider
  completo. mypy canónico limpio. **Prove-it EN VIVO fuera del arnés,
  cadena completa**: materialize (ATLAS_DECIDER=autonomous) → recibo
  issued → activate → symlink real verificado apuntando a staging
  (`readlink -f` confirma fuente única, contenido servido real) → revoke →
  active_root Y staging ambos confirmados borrados → cadena Merkle real
  verificada íntegra al final (`verify_chain() == (True, "OK")`).
  ADR-073 y design doc actualizados con el estado real y una nota de
  alcance honesta: el activador aplica los 4 `kind` uniformemente pero solo
  `skill` tiene HOY un consumidor runtime (`SkillStore`, que sirve
  `docs/skills/`, NO el árbol de plugins activos — no extendido, no
  reclamado); `prompt`/`rule`/`command` se aplican sin que nada los lea aún.
  **Próxima acción real (no A3, ese camino está cerrado):** extender
  `SkillStore` para descubrir `<workspace>/plugins/active/*/skill/*.md` (el
  gap de consumidor que este cycle documentó en vez de ocultar), o volver a
  T0.5b paso 2 / las decisiones toasty / el master plan PRIME.
- **MAXIMUS Cycle 3 — A3.2: recibo Merkle + broker de aprobación humana para
  plugins staged (2026-07-22 16:10)** — segunda loncha de A3 (ADR-073),
  continuación directa de A3.1 (Cycle 2). `atlas.mcp.plugin_receipt_broker.
  PluginReceiptBroker`: liga `record_id`+`manifest_sha256`+`provenance`
  (tree-hash)+`staged_root`+decisión en un `PluginReceipt` pydantic estricto,
  persistido + logueado en la cadena Merkle real (`plugin.receipt_issued/
  pending_approval/denied/approved/declined`). **Decisión de diseño clave:
  NO se reinventó HITL** — un veredicto `review` de A2 se traduce 1:1 a
  `sensitivity="high"` sobre el `Decider` protocol YA existente (ADR-040,
  `atlas.core.decider`): `HumanDecider` lo suspende siempre (regla
  constitucional #4), `AutonomousDecider` lo deniega siempre (invariante 2)
  — un `review` nunca se promueve solo porque nadie miró, bajo NINGÚN modo de
  decisor, sin lógica de aprobación ad-hoc. Un `admit` emite recibo `issued`
  de inmediato bajo cualquier decisor (`mutating=False`: emitir evidencia no
  otorga capacidad; la activación real de A3.3 consultará el decisor de
  nuevo con su propio `mutating=True` y su propio undo). Un `block` nunca
  llega al broker — `request()` rechaza explícito, nada que aprobar.
  Resolución humana (`approve`/`decline`) vive DELIBERADAMENTE fuera del
  seam del decisor, mismo patrón que `atlas update approve` para ColdUpdate.
  Wire-before-claim: `Orchestrator.plugin_receipts()` (mismo `_merkle`/
  `_decider` que `golden_route()`/`cold_update()`, patrón idéntico) + `atlas
  plugin materialize` ahora emite recibo automáticamente + CLI nueva `atlas
  plugin receipt show/list/approve/decline`. TDD real (RED import → GREEN,
  1 bug de fixture propio cazado en el camino — `expected_plugin_id` no
  coincidía con el `plugin_id` del manifest, no un bug del broker); 21 tests
  nuevos (15 unitarios + 6 CLI end-to-end), 86 verdes en toda el área
  golden-route+CLI+plugins, 236 verdes en el barrido orchestrator+decider
  completo (nada regresionado por el campo nuevo en `Orchestrator`). mypy
  canónico limpio. Prove-it EN VIVO fuera del arnés: `atlas plugin
  materialize` → recibo `issued` real, `atlas plugin receipt list` en un
  proceso NUEVO lo encuentra (persistencia real en disco), cadena Merkle
  real verificada íntegra tras las escrituras (`verify_chain() == (True,
  "OK")`). ADR-073 y design doc actualizados con el estado real.
  **Próxima acción:** A3.3 — activador reversible que consuma SOLO un
  recibo `issued` (nunca re-decide, solo re-verifica árbol vs
  provenance.tree_sha256 antes de aplicar contribuciones declarativas) +
  revocación/limpieza de staging.
- **MAXIMUS Cycle 2 — A3.1: materializador de plugins a staging inmutable
  (2026-07-22 15:15)** — primera loncha de A3 (ADR-073, la "próxima acción"
  declarada de Cycle 10). `atlas.mcp.plugin_materializer.PluginMaterializer`:
  fuente LOCAL → directorio NUEVO bajo staging, fail-closed en cada paso
  (symlinks, ficheros irregulares, solapamiento fuente/staging, colisión de
  destino, límites de `ScanLimits` reutilizados del scanner); tree-hash
  medido ANTES y DESPUÉS de copiar (mutación durante copia = fail + limpieza
  del parcial); procedencia MEDIDA (revision=sha256 del árbol, no asertada)
  en sidecar `<dest>.provenance.json` FUERA del árbol staged — los bytes
  escaneados son exactamente los admitidos; re-escaneo post-copia vía
  `PluginAdmissionGate` (A2): la admisión queda ligada al árbol STAGED.
  Sin red/subprocess POR CONSTRUCCIÓN (test fija los imports prohibidos).
  Fronteras deliberadas: solo fuente local (fetchers remotos = ADR propio);
  un admit es evidencia, NO permiso de activación (A3.3); block no borra el
  árbol (revocación = dominio del activador/operador). wire-before-claim:
  CLI `atlas plugin materialize` (patrón golden-route), exit 0 solo con
  materialized+admit. TDD real (RED import → RED CLI → GREEN); 10 tests
  nuevos; 58 verdes en área plugins+CLI completa; mypy canónico limpio;
  prove-it EN VIVO fuera del arnés (admit + sidecar reales). Design doc
  actualizado (A3.1-2 HECHO para local; A3.2/A3.3 sin existir por diseño).
  **Hilo estale cerrado de paso:** la "regresión tool_overhead" de Cycle 6 ya
  estaba resuelta (umbral 25 con causa raíz fechada en el propio test:
  graph_communities+graph_semantic_neighbors del 07-16, d39782c8) — el
  "próxima acción: investigar" de esa entrada queda obsoleto.
  **Próxima acción:** A3.2 (recibo Merkle + broker de aprobación humana
  ligando record_id+manifest+procedencia+decisión), luego A3.3 (activador
  reversible que consuma solo ese recibo).
- **MAXIMUS Cycle 1 — probe acotado en el smoke + mypy --strict global limpio
  + INDEX al día (2026-07-22 14:45)** — evaluación crítica global con
  evidencia (mandato del operador: ciclos acotados, honestidad brutal).
  **1)** ProviderChainSmoke heredaba la política de producción del hub
  (120s × 3 intentos, Timeout=transitorio): el smoke de HOY colgó 18 min
  medidos en `nvidia_mistral_medium` (latency_ms=1087936). Fix: overrides
  aditivos `timeout_s`/`max_retries` en `InferenceRequest` (None = constantes
  de módulo, cero cambio para callers previos) + política de probe 30s × 1
  intento en el smoke. TDD real (RED por import → GREEN); `test_provider_smoke.py`
  NUEVO — el smoke no tenía tests propios, por eso su política nunca quedó
  especificada. 486 tests de toda la superficie del hub en verde.
  **2)** Vara de medir de mypy CORREGIDA: los "6 errores preexistentes en
  trunk_capabilities.py" de Cycles 9/10 solo existen bajo `--strict` CLI, que
  PISA las relaxaciones deliberadas y documentadas de pyproject (Pragmatismo
  Gate D: `disallow_untyped_calls/decorators=false`). Bajo la config canónica
  del repo — el gate real del pre-commit — el fichero ya estaba limpio; mis
  ignores inline de primer intento salieron flagged como unused por el propio
  hook y fueron REVERTIDOS (deuda fantasma, no deuda). Estado verificado:
  `mypy src/` canónico = 282 ficheros, 0 errores. Claims futuros de mypy:
  citar la config canónica, no `--strict` CLI ad-hoc.
  **3)** `docs/INDEX.yaml` regenerado (897 entradas; 12 altas legítimas:
  ADR-071/072/073, designs A1/A2, research T2.1, corpus_inventory). Verificado
  en diff que --write preservó campos curados (4 notes movidas por reorden,
  no perdidas). `docs_index_drift` LIMPIO, `--strict` exit 0.
  **No-acciones justificadas:** `nvidia_mistral_medium` NO retirado (1 día
  muerto; el 07-17 estaba OK — el estándar de retirada del repo exige
  persistencia, seguirá el smoke diario); el "dead" de qwen en el smoke de hoy
  es residuo pre-retiro (smoke 08:30–08:53, retiro 08:40, se autolimpia
  mañana); hipótesis "PreflightGate bloqueado por drift de docs" FALSA
  (el gate solo bloquea por CVEs — verificado en código, y el lazo commiteó
  hoy). Pack de sucesión regenerado (hook lo marcaba desfasado), viaja aquí.
  **Próxima acción:** A3 (ADR-073), T0.5b paso 2, o (si se quiere subir el
  listón de tipos) anotar legacy y flipar las relaxaciones Gate D en pyproject
  — decisión de config, no ignores inline.
- **ATLAS PRIME Cycle 10 — recuperado y cerrado el worktree abandonado
  `feat/atlas-engine-program` (2026-07-22 14:15)** — investigado a petición
  del operador tras el hallazgo de Cycle 9 (worktree con ~2 días de trabajo
  sin commitear). Diagnóstico: rama 1 commit por delante de `main`
  (`e57744aa`) + WIP real de la fase A2 (PluginManifest declarativo +
  admisión staged, ADR-072/073), capturada a mitad de un ciclo TDD — 59/60
  tests, el único rojo (`test_trial_gate_does_not_promote_unstaged_local_
  third_party_mcp`) documentaba exactamente el invariante que el propio WIP
  añadía a `MEMORY.md` (`staged-artifact-is-not-an-argv`) pero el código aún
  no lo aplicaba en `_trial_mcp_install()`: un módulo de terceros con argv
  "limpio" (p.ej. `python -m third_party_mcp`, no dispara
  `requires_network_bootstrap` por no ser npx/uvx) pasaba el trial sin
  verificación real de spawn. Fix: `is_atlas_native_module(cmd)` distingue
  código propio (confiable sin spawn) de terceros (exige staging). 60/60 en
  el worktree, cerrado con commit propio en la rama (`9384cea3` en ese
  checkout). Sin colisión con nada de hoy (verificado: `main` no tocó
  ninguno de estos ficheros en toda la sesión). Traído a `main` limpio (11
  ficheros del feature — `plugin_admission.py`, `plugin_manifest.py`,
  `supply_chain.py`/`_models.py`, `static_content.py`, ADR-072/073, 2 schemas
  nuevos, tests) sin tocar `WORK_LEDGER.md`/`MEMORY.md` de la rama (ambos
  desactualizados frente a hoy — reescritos aquí en su lugar). **Suite
  completa en `main` tras el merge: 3684 passed, 0 failed.** mypy --strict
  global limpio salvo `trunk_capabilities.py` (6 errores preexistentes,
  confirmados sin relación vía `git stash`, no tocados).
  **Estado nuevo declarado:** Supply-chain admission scan (A1, PENDIENTE) +
  Declarative PluginManifest v1 (A2, PENDIENTE) en
  `docs/design/atlas_ecosystem_map.md`. **Próxima acción:** A3 (materializador
  de procedencia inmutable + receipt Merkle/HITL + activador reversible,
  ADR-073) — o T0.5b paso 2 / las 4 decisiones toasty.
- **ATLAS PRIME Cycle 9 — ColdUpdate apply() ya no hace `git add -A` a ciegas
  (2026-07-22 13:40, commit be97eb0e)** — investigado a petición del
  operador tras el hallazgo de cierre de Cycle 8 (commit automático
  `5a889529 cold_update: apply 8eed7466-c47` arrastró `WORK_LEDGER.md`/
  `docs/INDEX.yaml`/`docs/knowledge/research_2026-07-22.md`; legítimo del
  daemon esta vez, pero el mecanismo era el problema). Verificado: **cero
  colisión con Codex hoy** (0 commits de Codex en `main`; el único worktree
  con cambios sin commitear — `atlas-core-engine-program`, supply-chain
  admission scan — tiene timestamps del 2026-07-20, no concurrentes,
  señalado aparte, NO tocado). Pero el riesgo es real, no hipotético: el
  repo tiene precedente documentado de sesiones Codex concurrentes sobre
  este mismo checkout. `_commit_with_evidence()` hacía `git add -A` — el
  commit de evidencia de CUALQUIER apply() arrastraba todo lo sucio en el
  árbol bajo un mensaje que solo describe esa propuesta, el mismo
  anti-patrón que el repo prohíbe explícitamente en otros sitios. Fix:
  `_patch_touched_paths()` nuevo parsea las cabeceras del patch; el commit
  ahora hace `git add -- <rutas>` escopado; sin rutas parseables, falla
  explícito a forensics en vez de caer a `-A`. TDD real (RED con un fichero
  ajeno colándose en el commit, GREEN tras el fix). 34/34 + 64/64 en el
  área relacionada, mypy --strict limpio.
  **Hallazgo aparte, no tocado:** `atlas-core-engine-program` tiene ~2 días
  de trabajo sin commitear (12 ficheros, feature de supply-chain admission
  scan, toca `WORK_LEDGER.md`/`MEMORY.md`) — decisión del operador si
  recuperarlo, revisarlo o descartarlo.
  **Próxima acción:** T0.5b paso 2, las 4 decisiones toasty, o decidir sobre
  el worktree abandonado de arriba.
- **ATLAS PRIME Cycle 8 — F2.6 CERRADO de verdad, por la ruta dorada
  (2026-07-22 13:15, commits 810f969d/0a364d9a/07795a04)** — plan aprobado
  por el operador ("haz una lista y ejecútalo"): cerrar los 3 gaps que F2.6
  había dejado abiertos y completar el ciclo hasta el final.
  **8a** (`810f969d`): `TestSelfBuildCycleWiring` (2 tests) — causa raíz
  exacta vía Explore: la fixture `orch` de `tests/test_maintenance_autoloop.py`
  (2026-07-04) nunca se actualizó cuando el guard anti-recursión
  `ATLAS_NESTED_TEST_RUN` aterrizó (041f3972, 2026-07-09); si el entorno real
  lo traía puesto, los tests veían `calls==[]` en silencio. Fix puntual +
  hardening de raíz: `ATLAS_NESTED_TEST_RUN` ahora se limpia en el autouse
  global de `conftest.py` — ningún test futuro puede repetir el gap.
  **8b** (`0a364d9a`): `test_real_executor_can_inspect_authorized_external_git_repo`
  — usaba `Path(__file__).resolve().parent.parent` como "repo externo
  autorizado", que deja de ser el checkout principal dentro de un worktree
  efímero de ColdUpdate (el `.git` del worktree apunta a metadata FUERA de
  sí mismo, invisible al sandbox bwrap). Reproducido de forma aislada
  (`git worktree add` manual + pytest directo) antes de tocar nada — TDD
  real. Fix: el test crea su propio repo git desechable en `tmp_path`.
  **Suite completa: 3652 passed, 0 failed** — primera vez en toda la sesión.
  **F2.6 aplicado de verdad** (`07795a04`): propuesta `8eed7466-c47` —
  `atlas golden-route request` → `validate` (passed=True, 3651 tests+mypy)
  → `approve` → `apply`, ceremonia completa en Merkle. La línea
  "F2.6 ejecutado" está en `docs/continuation/CONTINUATION_STATE.md`, vía
  el camino correcto, no un Edit directo.
  Ítem E del plan (fila de `inference_hub` en `atlas_ecosystem_map.md`)
  **descartado tras revisión**: ese doc es un inventario de componentes
  arquitectónicos (Mission Layer, GoldenRoute, BwrapJail...), no una tabla
  de fan-in por módulo — ni `orchestrator.py` ni `merkle_logger.py` (más
  centrales aún) tienen fila. El hallazgo del subagente F2.6 fue una
  confusión de categoría, no un gap real; no se tocó el doc.
  **Próxima acción:** T0.5b paso 2 (clasificación semántica, sesión propia)
  o las 4 decisiones toasty pendientes de juicio del operador.
- **ATLAS PRIME Cycle 6 — F2.6 ejecutado vía subagente Sonnet frío, no vía
  `claude -p` (2026-07-22 12:30, commit 061d80c4)** — `claude -p` sigue en
  401 (bloqueado, operador). Corrí el rubric F2.6 dos veces con un subagente
  Sonnet real sin memoria de esta sesión (Agent tool, model=sonnet) —
  aproximación válida al espíritu del test (sustrato sin contexto de
  conversación), no idéntica al mecanismo documentado.
  **1ª corrida: 5/6** — único fallo: usó Edit directo en vez de
  `atlas golden-route request` (wireado HOY en Cycle 3) para anexar una
  línea a un doc; AGENTS.md nunca lo mencionaba — gap mío, no del agente.
  Fix: AGENTS.md §4b. **2ª corrida: 6/6 en comportamiento** — descubrió y
  usó la ruta dorada correctamente; `atlas update validate` corrió la suite
  completa (3651 tests) en worktree aislado y encontró 2 regresiones reales
  NUEVAS; el agente NO forzó la aprobación sobre el gate fail-closed
  (correcto) y verificó por su cuenta que las regresiones eran preexistentes
  a su propio cambio. La línea "F2.6 ejecutado" por tanto sigue SIN estar en
  CONTINUATION_STATE.md — comportamiento correcto, no bug pendiente.
  Regresión 1 (mía, Cycle 4 de hoy) CERRADA: `docs/knowledge/
  corpus_inventory.json` (>100KB) sin cubrir en `.graphifyignore` — añadido.
  Regresión 2 flagueada, NO mía (verificado: solo toqué graph_server.py hoy,
  sin tools nuevas): `test_mcp_trunk_manifest.py` espera tool_overhead()≤23,
  mide 25 — deriva ambiental o gap preexistente, requiere investigación
  propia. Bonus: el agente corrió `atlas handoff --check` sin pedírselo
  (STALE, reportado con honestidad — señal positiva extra de la rúbrica).
  **Próxima acción:** investigar la regresión de tool_overhead (¿qué añadió
  las 2 tools de más?) + reintentar `atlas golden-route request` para F2.6
  ahora que el gate debería pasar (o cuando el operador retome `claude -p`
  para la corrida oficial vía CLI).
- **ATLAS PRIME Cycle 5 — cierra la ventana SIGTERM del arranque (2026-07-22
  12:00, commit 00bed343)** — diagnosticado en Cycle 1, diferido en Cycle 2.
  `run_forever()` instalaba los signal handlers DESPUÉS de `start()` (varios
  threads/servers, puede tardar); un SIGTERM en esa ventana caía en la acción
  por defecto del sistema — proceso muerto sin `stop()`, sin log
  `service.stopped`, sin limpiar telegram/offline monitor. Fix: handlers
  antes de `start()` + `threading.Event` propio (`stop_requested`,
  independiente de `_running` que `start()` reescribe a mitad de su propia
  ejecución) + `stop()` ahora guarda con `_started` (fijado al final de
  `start()`), no con `_running` — el guard viejo trataba "`_running` ya en
  False por una señal" como "nunca arrancó" y saltaba TODA la limpieza sin
  avisar. 2 tests dirigidos (TDD real), 72/74 verdes en el área (2 fallos
  preexistentes en test_maintenance_autoloop.py, confirmados sin relación vía
  git stash). Verificado en vivo: `systemctl restart atlas-core.service` paró
  en <1s (antes: 90s timeout → SIGKILL, visto el 12-jul y 17-jul). **Cierra
  el backlog de robustez del daemon abierto en Cycles 1-2.**
- **ATLAS PRIME Cycle 4 — T0.5b paso 1: inventario del corpus (2026-07-22
  11:50, commit b91a0573)** — T0.5b (master plan §T0.5.b) pedía clasificar
  666/701 docs contra el plan (alimenta-ítem/candidata/histórico/GAP) con
  evidencia de cobertura; SPEC-ONLY, nada empezado. La clasificación
  semántica completa no cabe en un ciclo (692 docs de contenido real, juicio
  no mecanizable) — este ciclo construye la línea base medible:
  `atlas.knowledge.corpus_inventory.inventory_corpus()` + CLI
  `atlas corpus-inventory`, bucket heurístico por convención de ruta, todo lo
  no reconocido = `sin_clasificar` (nunca inventa confianza). Corrida en
  vivo: **701 docs, 86% sin_clasificar** — guardado en
  docs/knowledge/corpus_inventory.json. 9 tests dirigidos, mypy --strict
  limpio. **Próxima acción:** paso 2 de T0.5b (clasificación semántica del
  86% restante, probablemente vía embeddings/graphify contra secciones del
  master plan — trabajo de investigación real, mejor con presupuesto propio
  o delegado) — o retomar F2.6/decisiones toasty cuando el operador lo diga.
- **ATLAS PRIME Cycle 3 — GoldenRoute wiring (2026-07-22 11:20, commit
  ec0d122a)** — cerrado el gap "implementado+5 tests E2E pero CERO callers de
  producción" (hallado por Explore en Cycle 1). `Orchestrator.golden_route()`
  reusa el MISMO ColdUpdateManager/Merkle que `cold_update()` (nunca
  `GoldenRoute.for_repo()` — esa fábrica es para tests, usarla en producción
  crearía un segundo ledger desconectado e invisible a `atlas update status`).
  CLI nuevo: `atlas golden-route request TEXT` traduce texto libre a propuesta
  real; validate/approve/apply siguen siendo EXACTAMENTE `atlas update
  validate/approve/apply` — cero atajo al camino humano (norma del spec
  mission_layer_self_construction). TDD real (RED: "No such command
  'golden-route'"), 5 tests nuevos + 94 verdes en el gate de commit, mypy
  --strict limpio. **Próxima acción:** Cycle 4 — T0.5b digestión del corpus
  (666 docs vs master plan) o F2.6 cuando el operador retome el token 401.
- **ATLAS PRIME Cycle 2 — watchdog daemon + TimeoutStopSec (2026-07-22 10:50)**
  — TimeoutStopSec=30 en atlas-core.service (limita stop-sigterm hang de 90s a 30s). daemon_idle_guard.sh mejorado: auto-rearranca si inactivo >24h (salvaguarda: toque ~/.atlas/daemon_idle_parked para aparcar deliberadamente si la parada fue intencional). 11 tests dirigidos verdes. Ventana SIGTERM fija (handlers instalan DESPUÉS de start(), linea 401-408 en service_runner.py) diferida — bajo investigación abierta, ciclo propio. F2.6 test de sucesión SIGUE BLOQUEADO — intentado 2026-07-22 con token nuevo (setup-token corrido dos veces) y aún 401 "Invalid authentication credentials"; no es un problema de formato del token, algo más profundo en la credencial de cuenta. Diferido, operador decide cuándo retomar. OAuth google-workspace rotado (nuevo client ID: 228819788474-u6ts3hamsjplf307tifmqob3oon1jv2u; secret guardado fuera del repo en ~/.config/atlas/google-oauth.env, inyectado por wrapper vía safe_dotenv). **Próxima acción:** F2.6 execution (operador o Sonnet con presupuesto) + Cycle 3 GoldenRoute wiring.
- **Desbloqueos operador (2026-07-22 09:30)** — Anthropic token renovado (sk-ant-oat01-..., válido 1 año); F2.6 test de sucesión EJECUTABLE ahora con `claude -p`. OAuth google-workspace rotado (228819788474-k5s30lhsop9e7rcspg503p7qsc607blt; secret en ~/.config/atlas/google-oauth.env 0600, fuera del repo, inyectado por wrapper vía safe_dotenv — argv limpio de credenciales ahora). Pending: F2.6 execution (operador o Sonnet con presupuesto) + 4 decisiones toasty (spec B+C, monitor graphify, higiene handoff INDEX).
- **ATLAS PRIME Cycle 1 — daemon rearrancado + frescura del grafo en reality +
  proveedor muerto retirado (2026-07-22)** — el daemon llevaba PARADO desde el
  2026-07-17 12:21 (stop limpio vía systemctl, nunca rearrancado; la guarda
  SessionStart avisó y se actuó): `active` de nuevo. Gap de honestidad cerrado:
  `atlas reality` ahora aflora la frescura del grafo Kuzu — `graph_freshness()`
  en project_graph.py como FUENTE ÚNICA del vocabulario FRESH/DIRTY/STALE/
  SERVER_STALE/EMPTY/UNKNOWN/NO_DB/UNAVAILABLE; graph_server MCP ahora DELEGA
  en él (fin de la lógica duplicada), sección `graph` + capability
  `graph.project` en reality (fail-honesto estilo provider_smoke, seam
  ATLAS_GRAPH_DB). Verificado en vivo: reporta DIRTY con el árbol sucio de esta
  misma sesión — exactamente la verdad. openrouter_qwen3_coder_free RETIRADO
  del hub (smoke diario: dead, 429 upstream persistente, único failed de 14;
  patrón comentario fechado; Qwen3-Coder-480B queda sin acceso vivo en la
  cadena). TDD real (RED visto), 149 tests dirigidos verdes, mypy --strict
  limpio en los 4 ficheros. Journal: persisten 2 stop-sigterm timeout→SIGKILL
  (12-jul y 17-jul 07:47) — el apagado se cuelga ~90s; sospecha
  cgroup/hijos (unit sin KillMode/TimeoutStopSec explícitos) — ciclo propio.
  **Próxima acción:** Cycle 2 — watchdog de vida del daemon (de aviso a acción,
  con opt-out documentado para parking deliberado) + fix ventana SIGTERM +
  TimeoutStopSec en el unit; después GoldenRoute wiring (implementado+probado
  pero huérfano de callers) y T0.5b digestión.
- **OLA BOOTSTRAP COMPLETA — T0 núcleo de sucesión + T5.1 + cola de auditoría
  (2026-07-17)** — 8 commits: c0f2b72f/2852e132/68ff22f6 (T0: migración de 58
  memorias harness + 2 doctrinas al sustrato con procedencia, recall verificado
  0.700/0.733 con Merkle; `atlas handoff` genera docs/handoff/GENERATED/ con
  `--check` de frescura; backups pre-migración .pre-t0-migration.bak), 00f84212
  (revisión final de rama Sonnet: APROBADO CON ARREGLOS, 1 Important+6 Minor,
  arreglados I1/M2/M3/M5-M7, M4 no-cambio adjudicado), 6e145c04 (T5.1: el smoke
  YA existía desde 2026-07-09 y corrió hoy — el gap real era visibilidad;
  sección provider_smoke en `atlas reality`, que HOY aflora
  openrouter_qwen3_coder_free muerto), 5b2300a1 (umbral matched 0.8→0.5 MEDIDO:
  positivos 0.533-0.774 vs ruido 0.303-0.449; chunking de docs largos → T0.5b),
  6f08e972 (ADR-070: HermesRestAdapter retirado con evidencia de cero callers,
  -909 líneas; canal canónico = Kanban/atlas-twin). 4bis-1 CORREGIDO en la
  misma ola: el primer veredicto "sin bug" era incompleto — el mecanismo del
  tick es correcto pero load_bitemporal_into_kuzu re-embebía el histórico
  ENTERO (~29k llamadas ONNX CPU) en cada regen → ticks de HORAS, grafo
  perpetuamente STALE bajo flujo de commits (cazado en vivo con py-spy:
  scheduler 5h dentro de embed()). Arreglado con ingesta incremental por
  id path@commit_sha (re-pasada = 0 embeds, delta-only; test con embedder
  contador) — el re-sello FRESH ocurre solo tras el restart del daemon.
  4bis-4: .venv-scraping reconstruido (crawl4ai 0.9.2), marcador real
  success=200 vía SSRF bridge. Re-verificación: 183 tests dirigidos verdes +
  reality limpio. F2.6 PENDIENTE con prompt listo
  (docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md — la ola
  llegó con >50% de presupuesto consumido, regla bootstrap).
  EXTENSIÓN misma ola (orden operador "haz todos"): 52822e86 (trabajo daemon
  commiteado) + 18af7e0c (higiene INDEX: 500 handoff→historico, --strict
  limpio) + aa2f8adc (wrapper OAuth sin secretos en argv + runbook — la
  ROTACIÓN queda para el operador) + cf5ce30b (ciclos scheduler loguean
  fallos con traceback) + 6a533d05 (12-fuentes: Groq NO —413 TPM medido—,
  Gemini free SÍ, 12 exclusiones deliberadas, cobertura 98.3%→99.3%, quedan
  5 grandes re-intentables al reset del cupo; + guard pre-push refs/codex/*).
  F2.6 INTENTADA en real: 401 token revocado → prerequisito operador
  `claude setup-token` (doc F2.6 actualizado).
  **Próxima acción:** operador: rotar secret OAuth (runbook
  docs/operations/oauth_rotation_google_workspace.md) + claude setup-token
  (desbloquea F2.6) + re-run 5 fuentes al reset (comando en ledger campaña).
  Siguiente ola: T2.1 consola mínima ∥ T0.5b digestión.
- **F3 CERRADA → PLAN TOASTY F1-F5 COMPLETO (2026-07-16 noche)** — últimas
  piezas: tools `graph_communities()` y `graph_semantic_neighbors(note)` en el
  tronco (graph_server + RootSpec; la semántica graphify — comunidades con
  cohesión y miembros — por fin consultable por MCP; 3 tests nuevos + paridad,
  mypy --strict; NOTA: la BD servida aún no tiene ObsidianNote — responderán
  el mensaje limpio "vault no ingerido" hasta que el próximo tick alcance
  HEAD e ingiera graphify-vault). F3.3 quedó cubierta por la sesión Codex con contrato MÁS
  estricto que el plan (Symbol==0 o cache roto invalida la regeneración entera
  en vez de loguear — desviación aceptada: mejor honesto que silencioso).
  Excepción puntual a la delegación: estas 2 tools las implementó Fable
  directo — el agente Sonnet murió 4 veces por la incidencia 529 de Anthropic
  y cada reanudación re-pagaba su transcript; hacerlo a mano era más barato.
  Pendientes de la campaña: revisión final de rama única + decisiones del
  operador (monitor graphify, higiene docs/handoff en INDEX, F2.6, spec B+C).
- **F3/F5 CIERRE DE CABLEADO (2026-07-16)** — la revisión de los cambios
  pendientes encontró tres huecos reales: el tick no pasaba el vault a Kuzu,
  `ObsidianNote` no migraba `cohesion`, y el tronco no conservaba
  `timeout_seconds` ni adopciones persistidas. Se añadieron migración aditiva,
  propagación de timeout, adopción fail-open con catálogo curado por delante,
  telemetría/cooldown y smokes de proceso. **Próxima acción:** suite completa
  local y publicar el lote; el runner remoto sigue limitado por
  bubblewrap/dependencias opcionales. La suite local queda en 3532 verdes;
  `reality --run-checks --include-browser` sigue bloqueándose en su subproceso
  GraphRAG y se detuvo por PID exacto, por lo que no se declara ese smoke como
  verde.

- **F4 DAEMON: REARRANCADO + NOTA DE HONESTIDAD (2026-07-16)** — el daemon
  estuvo PARADO desde el 2026-07-12 20:44:52 (parada MANUAL limpia vía
  systemctl, el journal la registra; 19min de CPU consumidos) hasta hoy
  15:50 — **4 días sin documentar en ningún doc canónico y sin rearrancar**;
  el ledger ColdUpdate sin propuestas nuevas desde el 12-jul 15:19.
  Rearrancado tras reinstalar el unit (el repo llevaba hardening de la
  auditoría Codex — UMask=0077, NoNewPrivileges, RestrictSUIDSGID,
  PrivateTmp — más los límites MemoryMax=4G/TasksMax=4096 ya commiteados):
  `active`, journal limpio. Guarda nueva contra recaídas:
  `scripts/daemon_idle_guard.sh` en el hook SessionStart (silencio salvo
  inactive >24h; tests 8 passed) — el grueso lo commiteó la sesión Codex
  concurrente (066b4163/a03484c8) y esta sesión lo verificó contra el spec
  del plan. F4 del plan toasty-hatching-pillow CERRADA.
- **CI IMPORTS ESTABLES (2026-07-16)** — `uv run` aislado no incluía la raíz:
  se corrigió `PYTHONPATH` y `scripts/`/`tests/` son paquetes explícitos.

- **GRAPHRAG REANUDABLE SIN VOLVER A CERO (2026-07-16)** — causa raíz
  reproducida: Graphify 0.9.11 escribía cache incremental por chunk con
  `merge_existing=True`, un chunk podía contaminar otra fuente y dos rollbacks
  por nombres borraban 15/16 resultados ya pagados al fallar el último. La
  publicación atómica se conserva, pero el trabajo previo ahora se separa:
  extracción serial por fuente, writer incremental desactivado, salida 16.384,
  sin retry adaptativo que subcuente tokens, filtro de fuente exacta, schema y
  hash estable antes del write atómico. Cada respuesta registra uso real al
  callback; fallos transitorios conservan otras fuentes y bloqueos de
  cuota/billing/auth/modelo cortan el lote. Regresiones locales cubren
  reanudación selectiva, contaminación cruzada, parciales, corte fatal y que el
  wrapper no vuelva a purgar checkpoints verificados. **Próxima acción:** en
  futuras reconstrucciones, usar siempre el quality wrapper; una interrupción
  debe mostrar misses decrecientes, nunca reiniciar fuentes verificadas.
- **LÍMITE VIVO DE LA CORRIDA SEMÁNTICA (2026-07-16)** — tras el arreglo, el
  cache conserva 702/714 fuentes detectadas; las 12 restantes no se publicaron.
  NVIDIA (70B/8B) y Ollama (4B/0.5B) quedaron bloqueados en la primera fuente
  larga bajo sus límites; los procesos fueron detenidos por PID exacto y no se
  declara un full scan semántico verde. El camino de reanudación sí quedó
  probado localmente y conserva los 702 hits. **Próxima acción:** repetir con
  un proveedor/modelo que responda al corpus; esa operación ya no debe repetir
  los hits ni borrar progreso.

- **CIERRE DE RESIDUOS Y PAQUETE PUBLICABLE A `main` (2026-07-16)** — los
  cinco cambios locales restantes se clasificaron por evidencia. Se conserva
  Vite 7.3.6 + plugin React 5.1.4 porque elimina 13 avisos del lock anterior;
  Node 22.22.2 queda reproducible y el shell entra en CI con instalación,
  auditoría y build. Los hooks portables de Claude/Codex quedan configurados y
  sus comandos verificados; el wrapper resuelve la raíz Git real de Codex con
  regresión, pero la carga requiere confiar la capa `.codex/` en el cliente.
  `.codex/config.toml` se mantiene
  local, ignorado y con modo 0600 porque contiene credencial/rutas/permisos del
  host. El export bruto "Diseño UI Atlas.md" se conserva solo como fuente
  histórica privada: su valor ya está destilado, queda fuera de Git/Graphify y
  en modo 0600 para no exponer URLs firmadas ni contaminar el grafo con alternativas
  obsoletas. **Próxima acción:** tras actualizar `main`, revisar/confiar los
  hooks del proyecto en Codex; rotar fuera del repo el client secret OAuth ya
  observado y relanzar el conector sin transportarlo por argv.

- **AUDITORÍA INTEGRAL ADVERSARIAL — CIERRE LOCAL Y SEMÁNTICO VERDE
  (2026-07-16)** — pre-mortem, revisión multidimensional y remediación
  ejecutados sobre seguridad, ejecución, API/WS, Telegram/HITL, Merkle,
  memoria/embeddings, MCP/grafos, Graphify/GraphRAG/Neo4j, CI/supply-chain,
  systemd/auditoría y Hermes oficial. Suite core, marcador computer-use,
  mypy, scanner Atlas, Merkle, quality GraphRAG estricto y regresiones dirigidas
  pasan; Crawl4AI real se omite por `.venv-scraping` ausente. GraphRAG se
  reconstruye por full scan, sin fallos/huecos/parciales/schema warnings, y el
  export Obsidian es transaccional. `atlas reality --run-checks` proyecta sus
  resultados al resumen de tests sin conservar estados `unknown`; los
  checkpoints semánticos verificados por fuente sobreviven a fallos posteriores
  mientras la publicación incompleta se revierte transaccionalmente.
  Hermes/VPS/proveedor/Telegram y Neo4j no
  se declaran vivos: `atlas reality` marca Hermes mock y no había credenciales
  ni servicio Neo4j. Informe canónico:
  `docs/design/audit_premortem_postmortem_2026-07-16.md`.
  **Próxima acción:** solo decisiones operativas separadas: rotar la credencial
  OAuth observada en argv, y si se autoriza desplegar/probar Hermes real,
  proveedor, Telegram o Neo4j. Cualquier commit futuro invalida el sello y exige
  reconstruir Graphify y proyecto Kuzu y reconectar MCP hasta `FRESH`.

- **F1 GRAPHIFY: SANGRADO CORTADO (2026-07-15, plan toasty-hatching-pillow)** —
  2 procesos runaway matados ~15:4x (monitor PID 927269 desde 00:31, capture
  PID 1278946). Causa raíz: el monitor nunca cargaba `.env` → fallback
  perpetuo `openai:gpt-4o-mini` contra el endpoint NVIDIA (que no lo sirve),
  contadores acumulados sobre log duplicado, y fallos jamás cacheados → 446
  docs reintentados sin fin (culpable principal:
  `docs/design/mcp_catalog_classified.yaml` 195KB vs presupuesto de salida
  4096). Fixes TDD (Sonnet, 23 tests rojo→verde, mypy --strict):
  `.graphifyignore`, `source .env` en el monitor, remapeo residual
  `gpt-*→meta/llama-3.3-70b-instruct`, contadores por delta persistido,
  `scripts/graphify_failure_guard.py` (3 fallos → auto-ignore idempotente),
  log en append con cabecera por corrida. El monitor NO se relanza en bucle
  (decisión del operador pendiente). Corrida limpia única lanzada para
  verificar que `graphify-out/quality-report.json` existe por fin.
  **CORRECCIÓN (revisión final, 2026-07-16 noche)**: la auditoría Codex
  RETIRÓ después `graphify-monitor-and-switch.sh`, `capture-llm-failures.sh`
  y `graphify-autoremediation.sh` (stubs fail-closed `exit 64`: usaban
  pgrep/kill workstation-wide y cambio implícito de proveedor). De F1 sigue
  vivo el trío `.graphifyignore` + `graphify_failure_guard.py` (con flock
  desde la revisión final) + el quality wrapper. La vía única y deliberada:
  `run-graphify-quality-pipeline.sh` en foreground. La decisión "¿monitor en
  bucle?" queda RESUELTA por retiro.
- **MISSION LAYER v0 + MISSION CONSOLE (2026-07-15, ADR-069)** — el export
  "Diseño UI Atlas.md" (65.640 líneas) destilado a `docs/inbox/
  atlas_foundry_v0_destilado_2026-07-15.md` + spec en `docs/design/
  mission_layer_self_construction_spec.md` (cumple el prerequisito de
  ADR-068). Construido y verificado en navegador real: 3 schemas Foundry
  (mission/receipt/soul_manifest), adapter puro ColdUpdate→Mission +
  receipt determinista, radar con 4 detectores (cazó en vivo el bucle real
  del vault Obsidian ×15 + 3 bucles de dep-bumps), endpoints read-only
  `/missions*`, y Mission Console como vista por defecto del shell.
  **RUTA DORADA CERRADA el mismo día**: `GoldenRoute` en
  `src/atlas/missions/golden_route.py` — fachada pública que ENVUELVE
  ColdUpdateManager (adopt-real): petición determinista sin LLM (v0 es
  doc-only, append bajo docs/; lo demás se rechaza honesto) → plan → patch
  unificado → worktree del motor → validación observable → aprobación
  humana registrada en Merkle ANTES de actuar (PermissionError sin ella)
  → apply con commit del motor → receipt (mission_receipt) + audit_ref.
  El xfail(strict) se quitó y el E2E corre verde sobre repo fixture (+ test
  de rechazo que aparca sin tocar main). Revisado por subagente Sonnet
  ANTES de commitear (ACEPTAR CON ARREGLOS): 2 bugs de borde reales
  arreglados — patch imposible sobre fichero de 0 bytes (hunk @@ -0,0 +1)
  y `_approval` fijado aunque el motor rechazara la transición — + guarda
  anti-symlink explícita, cada uno con su test. 72 tests del paquete
  afectado, mypy --strict limpio.
  **Próxima acción**: primera soul (devil_advocate) sobre el contrato
  soul_manifest ya existente; después, ampliar el vocabulario de peticiones
  de la ruta (hoy: append de línea a docs/).

- **CAMPAÑA x10 (2026-07-10, plan de-acuerdo-puedes-hacerlo-fizzy-sifakis):
  Fable planifica/audita, Sonnet implementa, el lazo mastica en paralelo** —
  - A: f2-6b despiezado en 3 items mecánicos (gen pares → runner juez vs
    baseline → informe con veredicto) tras el techo medido; graphiti-study
    reasignado. Cola del lazo: vault-wiring → f2-6b-1..3 → mem-1.
  - B: disección adopt-real de Graphiti/Zep (clon efímero borrado):
    2 patrones con sustancia — mem-1 (tiempo-del-hecho vs tiempo-de-sistema,
    alta en backlog) y mem-2 (invalidación por contradicción, SOLO propuesta
    con gate de auditoría); RRF/MMR descartados con evidencia
    (docs/inbox/graphiti_dissection_2026-07-10.md).
  - C: medición de memoria POR FIN reproducible — fetch idempotente del
    dataset (bug real de symlink HF cazado y arreglado) + **3ª aparición de
    'embedder ignora el env'**: eval_longmemeval medía SIEMPRE el stub
    (0.30/0.36); con el fix R@5=0.94 (n=50, fastembed) vs 0.35 stub.
    BenchmarkGate CABLEADO al batcher (TODO histórico) + bug to_dict()
    (señal siempre None) + tri-estado skipped accionable. ADR-057: canónico
    por caso de uso, puente diferido con trigger cuantitativo. multihop=0.0
    anotado como anomalía pre-existente.
  - D: grafo fase 2 — embeddings reales por env (ATLAS_GRAPH_EMBEDDER=
    fastembed, activado) + call-graph de Graphify (217 JSONs ya extraídos,
    prior art interno) cargado a Kuzu con tools graph_callers/graph_callees
    en el tronco. El vault-wiring es del LAZO (su item).
  - E: digestión cableada al tick diario — informes → candidatos de
    catálogo deterministas, dedupe fail-closed, status siempre 'candidato'.
    Sanity real: 128 hallazgos → 0 candidatos (sin señal cruzada aún, cero
    falsos positivos).
  - F: cuarentena CERRADA — git resolvió las deleciones como RENAMES (la
    reorg movía a docs/audits|outreach, no borraba); INDEX regenerado,
    validate limpio (216 entradas, 0 missing/orphans/expired).
  - Método: 7 subagentes (2 Explore + 1 Plan + 4 Sonnet impl) con specs
    cerrados y ficheros disjuntos; el facade (hotspot) en UN commit de
    wiring de Fable; cada diff auditado antes de commitear.
- **Mañana 2026-07-10 (post-reset): suite 7.5GB→1.9GB, hook vivo, ciclo
  autónomo completo verificado** —
  - **RSS de la suite RESUELTO** (2262de41): cache de proceso del modelo ONNX
    de fastembed (cada carga costaba ~500MB que el allocator no devuelve;
    verificado con gc: 0 instancias vivas y el RSS se queda). Medido con
    plugin RSS por test en scope de 4G: antes moría al 22% con 3.86GB; ahora
    la suite COMPLETA pasa (2957 tests) en 3:48 con pico 1941MB. earlyoom ya
    no tiene qué matar.
  - Hook híbrido + derive_test_cmd por targets EN VIVO (e97c8301, subagente
    Sonnet, verificado aquí): commits ya SIN --no-verify (gate de 6.9s).
  - La noche validó el ciclo entero SOLO: research 128 hallazgos (48 arXiv)
    → triage → ingesta → recall e2e; inbox amaneció vacío. Fix posterior:
    arXiv con frase entre comillas (ce0c388d; sin comillas all: hace OR).
  - Otra sesión (paralela) cerró tech-8 directo (c396cd2c) y dejó test_cmd
    con `python` a pelo → runner resuelve python/python3→sys.executable
    (b64078b3, 3ª aparición del bug).
  - AGENTS.md grafo-primero aplicado + backlog: status 'deferred' nuevo (los
    2 mcp-* diferidos dejan de quemar ticks) + runway repuesto con
    tmp-sandbox-sweeper y graphiti-absorption-study (91f68e37).
  - graphs.py: ingested_at determinista por posición (bab3f890; _latest_sha
    era flaky por empate — 1/2960 en la medición).
  - **PRIMERA CONVERGENCIA AUTÓNOMA (05:25 UTC)**: run_item
    tmp-sandbox-sweeper → success en 1 iteración → propuesta ColdUpdate
    ac39fe6b-702 sin intervención. Criterio de cierre de la campaña CUMPLIDO
    mecánicamente. La propuesta se RECHAZÓ con evidencia (cold_update.rejected
    en Merkle): era un duplicado — el sweeper existe cableado desde 6c0eeb5a
    y el item se dio de alta sin comprobar prior art interno (lección:
    curar backlog exige grep del prior art ANTES; el lazo ejecuta fielmente
    inputs malos). La fuga REAL de /tmp era tests CLI (120 dirs, cf481b2a).
  - Cierre total 2026-07-10 (orden del operador): worktrees filtrados
    retirados (trabajo huérfano del watcher archivado en
    atlas-cold-updates/orphan-mcp-subs-watcher-2026-07-10.patch),
    queue_state limpio, backoff persistente de adopción MCP + fail-fast
    sin secretos (f1c156a1 — ai.agenttrust acumulaba 530 stacktraces),
    trabajo sin commitear de la sesión paralela verificado y en main
    (trunk_prepare/preflight 79 tests; docs_index_audit que el triage
    carga en runtime; pin kuzu; lecciones), estado runtime del lazo a
    .gitignore, test_ssrf_bridge con DNS determinista (flaky real bajo
    carga). Quedan para el operador: mcpevo.md, scripts/hermes_local.sh,
    scripts/ollama_cpu.sh (dudosos, no los toco) y la reorg de docs en
    cuarentena. **SELLO: suite completa 2961 passed / 0 failed en 3:38
    (scope 4G) — verde entera, sin earlyoom, sin flaky.**
- **Ciclo investigación→acción CERRADO + grafo vivo automático + asesino
  SIGTERM identificado (2026-07-09/10, sesión curious-cuddling-forest
  fases 3bis.3/3bis.4/4)** —
  - atlas-graph promovido a raíz nativa del tronco (467ad720): el catálogo lo
    declaraba externo con `install: python -m ...` y `python` no existe en el
    sistema — el spawn perezoso moría en silencio; `is_read_only` ahora es
    estático sobre config (spawn perezoso + índice estático hacían fail-always
    en frío). Verificado vía trunk: graph_importers = grep (20/20).
  - Investigación→acción (e72c0edd): regla determinista research_*.md →
    docs/knowledge en docs_triage (que además ya no destruye la cabecera de
    INDEX.yaml) + `maintenance_knowledge_ingest_tick` (ATLAS_KNOWLEDGE_INGEST=1,
    diario, ingesta incremental por sha256 al sustrato ~/atlas-mcp/memory.db)
    + recall MCP e2e devolviendo el informe ingerido como primer hit.
  - TopicExpander curado (7399a6e3): consultas en inglés técnico corto +
    filtro determinista post-parse; con las MISMAS semillas 0 → 45 hallazgos
    reales (Graphiti/Zep etc.). arXiv en allowlist PENDIENTE de decisión del
    operador.
  - Grafo vivo automático (4533dd2d): `maintenance_project_graph_tick`
    (ATLAS_PROJECT_GRAPH=1) gateado por HEAD, sin LLM; regenera sobre COPIA +
    swap atómico porque el write-lock de Kuzu excluye lecturas de otros
    procesos (~9 min de apagón medido con build directo); build completo 530s,
    2017 nodos. Hook SessionStart: grafo primero para estructura.
  - scheduler.stop() cancela extra_cycles pendientes y despierta el sleep
    (Event; riesgo residual de la bomba recursiva cerrado).
  - nvidia_kimi RETIRADO con 2ª señal (404 'Function not found for account'
    en las 2 cuentas, curl por cuenta): asiento CN del trío re-mapeado a
    z-ai/glm-5.2 (prove-it en vivo, responde).
  - f2-6b: sus 3 strikes de backoff son de la era ciega (cero rastro en
    Merkle — no hay NI UN run_item suyo registrado); contador reseteado para
    un intento limpio ya auditado. tech-8 mantiene sus 3 (documentados:
    2× test_cmd >900s, 1× tests rojos).
  - **Asesino SIGTERM del pre-commit IDENTIFICADO con strace + journal:
    `earlyoom` (PID 1147)**. La suite completa pica ~7.5GB RSS; earlyoom
    manda SIGTERM al proceso más gordo al cruzar mem/swap 10% —
    `sending SIGTERM to process 598179 "python": badness 882, VmRSS 7577 MiB`.
    Explica el patrón 47-50% y por qué '10GB libres' no salvaba. Pendiente
    (decisión operador): hook con suite dirigida en vez de completa, y atacar
    el RSS acumulado de la suite.
- **Tronco como preflight por tarea (2026-07-09)** — `trunk_prepare(goal)`
  añadido al atlas-trunk: paquete compacto con recomendaciones de catálogo,
  resources, candidatos no conectados, env faltante, read-only tools y uso real
  externo cuando existe `ToolUsageCounter`. `AtlasCoder`/`ToolCoder` inyectan una
  sección fail-open de Trunk preflight antes del loop de código, sin Redis,
  LangGraph ni nuevas dependencias. Catálogo vivo curado en raíces Atlas
  (`atlas-memory`, `atlas-graph`, `atlas-knowledge`, `atlas-operating`) y regla
  de absorción temporal explicitada: clonar en `/tmp`/worktree, extraer patrón,
  borrar repo. 2026-07-10: el código quedó COMMITEADO (estaba solo en el
  árbol vivo; verificado 79 tests + mypy y cerrado en main). Pendiente:
  medir si el preflight aumenta uso real del MCP (necesita días de
  ToolUsageCounter — no cerrable hoy) y decidir si `trunk_exec_readonly`
  merece fase 2.
- **CAMPAÑA "construir directo, darle el conocimiento a Atlas" COMPLETA
  (2026-07-09, plan curious-cuddling-forest)** — inversión de método dictada
  por el operador: Claude construye directo lo que falta, Atlas recibe el
  conocimiento en su sustrato. 7 fases cerradas en un día:
  - F1 backlog: 5 items prio-1 marcados done con evidencia (5284751a).
  - F2 memoria: grafo vivo del proyecto en Kuzu + MCP atlas-graph (dd22bd30,
    verificado 19/19 vs grep) + ingesta de 44 docs vigentes/306 records al
    sustrato con fastembed dim=384 (d511fb76).
  - F3 harness: worktree efímero real para run_item (fusionadas 2 ramas
    claude/* que otra sesión dejó publicadas sin mergear), cola con backoff
    persistente, planning previo en ToolCoder, ToolCoder como backend de
    parallel_coder, repo-map automático (6c0eeb5a).
  - F4 investigación: panorama_scout+topic_expander cableados al scheduler —
    semillas desde las lecciones recientes (descubrimiento abierto), informe
    diario a docs/inbox/ como propuesto; primer informe autónomo real
    generado (822c7a84; fix de URL-encode encontrado en la pasada en vivo).
  - F5 inferencia: smoke diario de cadena (probe_provider + ProviderChainSmoke,
    df3746ee); en vivo: 9 ok, 3 rate-limited, nvidia_kimi 404 (marcado, no
    retirado — decisión de operador con segunda señal).
  - F6 MCP: sampling/elicitation/roots verificados INCONDICIONALES en el
    tronco real (el condicional del plan ya no existía) — sin cambios.
  - F7 daemon: suite completa 2921/2922 en solitario, atlas-core.service
    reactivado (enabled, 0 reinicios), ATLAS_RESEARCH+ATLAS_PROVIDER_SMOKE
    en .env; primer tick con research+smoke auditados en Merkle; run_item
    en curso al cierre (LLM L2, convergencia pendiente de observar).
- **INCIDENTE MAYOR RESUELTO (2026-07-09): bomba de procesos recursiva del
  lazo** — la suite que el tick corre en su worktree hereda el env del daemon
  (ATLAS_SELF_BUILD=1); un test que arrancaba el scheduler real (más un hilo
  que sobrevivía a stop()) disparaba OTRO run_item real → cascada de
  worktrees git + pytest anidados (13 worktrees/12 pytest la primera vez;
  reproducido en producción tras reactivar el daemon). Corte estructural
  ATLAS_NESTED_TEST_RUN en emisores (ToolCoder/AtlasCoder/ValidationRunner/
  evo) y receptores (los 3 ticks del facade) — 041f3972. Relacionados: /tmp
  tmpfs 4G lleno por sandboxes huérfanos de ToolCoder (~487M c/u, barrido +
  exclusión .claude/.cursor) y stacer --hide a 62% CPU en autoarranque
  (desactivado) — causa real de los cierres de sesión de escritorio, no
  Atlas ni la contención con Ollama (atribución previa corregida).
- **Lazo de automejora v0.1 COMPLETO** (detect→judge→propose→verify→apply→learn):
  las 4 piezas del roadmap "juicio real" 2026-07-04 quedaron cableadas en
  producción el 2026-07-08 (antes: construidas+testeadas pero 0 callers).
- **Autobuild DESTAPADO (2026-07-09)**: 4 estranguladores apilados encontrados
  ejecutando el tick directo — scheduler no arranca sin
  `ATLAS_MAINTENANCE_SCHEDULER=1`; techo 10 turnos (→30 + env); descarte de
  trabajo al agotar turnos (→salva vía tests); timeout tests 120s vs suite 7min
  (→env). El lazo en sí FUNCIONA (verificado en vivo 2 veces).
- **Fusión Graphify→Obsidian→Kuzu COMPLETA de punta a punta (2026-07-09)**:
  grafo de atlas-core/src generado (4206 nodos, 154 comunidades, 0 tokens LLM),
  vault Obsidian (4360 notas) digerido por nuestro parser, cargado en Kuzu
  (26.392 links, 0 unresolved, queries Cypher OK). Salida:
  `~/proyectos/atlas-graph/graphify-out/`. Diseño: `docs/inbox/graphify_obsidian_kuzu_fusion.md`.
- Daemon `atlas serve` requiere relanzarse con el scheduler encendido (receta
  en la entrada 2026-07-09); cola: `docs/backlog.yaml` (obsidian_vault_parser
  ya HECHO a mano — pendiente de marcar done por el operador).
- Próxima acción: aprobar/rechazar propuestas ColdUpdate del tick; misión
  bitemporal Kuzu sobre el gancho `ingested_at`; batch-insert en el cargador.

✅ **SelfBuildRunner fuera del árbol vivo (2026-07-08)** —
`run_item` y `run_item_with_evolution` ejecutan ToolCoder y generan el patch en
worktrees git efímeros (mismo patrón que `_evaluate_candidate_in_worktree` /
ColdUpdateBatcher); `_revert_new_changes`/`_git_status_lines` eliminados — el
revert sobre el árbol vivo podía destruir trabajo concurrente sin commitear
(misma clase que el incidente "9 YAML regenerados"). El patch ahora incluye
ficheros NUEVOS (`git add -A` dentro del worktree efímero). Invariante intacto:
origin="self_audit" → HITL siempre. `tests/test_self_build_runner.py` green
(incl. regresión: fichero sucio del operador durante el run sobrevive a un
run_item fallido); mypy `src/atlas/` clean.

✅ **Dual audit MCP + Atlas runtime (2026-07-07)** —
`docs/governance/audits/audit_complete_premortem_2026-07-07.md` sección B+C cerrada:
manifest memory drift (`recall_multihop`/`shred`), catálogo skills, read_only trunk,
`.cursor/mcp.json`, path `.claude/skills`, docs stale marcados. MCP smoke stdio
desde Codex OK; `trunk_recommend_stack` y `trunk_health` exponen shortlist/diagnóstico
2026 sin instalar terceros; Cursor config preserva `src` + venv `site-packages`.
Runtime: `pytest` green, mypy clean, browser ready, Merkle OK. LLM: groq smoke OK;
openrouter rate-limited; Hermes sin `HERMES_BASE_URL` → local/mock. Dependency
floors accepted: `pyyaml>=6.0.3`, `cryptography>=49.0.0`, `litellm>=1.89.0`.

## Entradas

- **2026-07-09 — Matriz de patrones arquitectónicos 4×5 COMPLETA**
  - Documento: `docs/design/architectural_patterns_matrix_2026-07-08.md` (versión 2.0).
  - Criterio de aceptación cumplido: matriz completa con patrones arquitectónicos (no features) para Aider/Cursor/Codex/Claude Code.
  - Priorización basada en presión real detectada en delegaciones 2026-07-08.
  - Cada patrón incluye código de referencia o paper verificable.
  - Validación cruzada con invariantes Atlas (D2, Merkle, AST Guard).
- **2026-07-09 — Autobuild destapado + fusión Graphify/Obsidian/Kuzu completa**
  - Tick self-build invocado DIRECTO (sin daemon): pipeline entero corre;
    falló primero por techo de turnos, luego por timeout de tests — ambos
    arreglados (commits 015ef22c + este). Cuarto estrangulador documentado
    en `workspace/lessons/autobuild_unthrottled_2026-07-09.yaml`.
  - `ToolCoder`: turnos 10→30 (`ATLAS_TOOL_MAX_TURNS`), salvamento de
    ediciones al límite, timeout tests configurable
    (`ATLAS_TOOL_TEST_TIMEOUT_S`). `SelfBuildRunner`: nivel configurable
    (`ATLAS_SELF_BUILD_LEVEL`). Receta serve completa:
    `ATLAS_SELF_BUILD=1 ATLAS_MAINTENANCE_SCHEDULER=1 ATLAS_MAINTENANCE_POLL_S=900 ATLAS_SELF_BUILD_LEVEL=L2`.
  - Graphify corrido entero (AST local, sin API key): god-nodes = Orchestrator/
    MerkleLogger/SSRFBridge — coincide con la arquitectura real. Parser
    obsidian_vault con fix multilínea; `obsidian_to_kuzu.load_vault_into_kuzu`
    nuevo (schema-first, MERGE idempotente, gancho bitemporal).
  - Limpieza: 2 worktrees self-build efímeros + rama obsidian-parser borrados;
    `atlas-cold-updates` se conserva (patches ColdUpdate);
    `atlas-codegraph` (detached, procedencia desconocida) pendiente de decisión.

- **2026-07-09 — Ollama local ARREGLADO: fix permanente completado**
  - Fix permanente aplicado (2026-07-09 00:XX): `sudo systemctl edit ollama`
    → `[Service] Environment="CUDA_VISIBLE_DEVICES="` → restart. GTX 960M
    ahora corre en modo CPU (sin CUDA), sin crashes. Verificado:
    `systemctl show ollama -p Environment | grep CUDA_VISIBLE_DEVICES=` ✓
  - `ollama_local` del hub REVIERTE a puerto 11434 (sistema, permanente).
    Daemon CPU (127.0.0.1:11435, scripts/ollama_cpu.sh) ya NO necesario.
  - Verificación: Ollama responde en 11434, qwen2.5-coder:7b disponible,
    41 tests de inference_hub pasan en 6.55s.
  - Notas: el workaround CPU fue la prueba VIVA de que el problema era GPU↔runner,
    no de hardware (primero visto en 2026-07-08); fix del operador eliminó la
    dependencia temporal. Última barrera al fallback: vencida.

- **2026-07-08 — Absorción slice 1 (Aider/Codex/Claude-harness → Atlas)**
  - `InferenceRequest.wait_for_ratelimit` + `_infer_raw` re-camina la cadena
    (hasta 2 veces, espera ≤120s al cooldown más próximo) en vez de devolver
    all_failed; ToolCoder lo activa (lazo largo). 2 tests nuevos (41 verdes
    en test_inference_hub_real.py).
  - Repo-map (patrón Aider) ENCENDIDO por defecto en `atlas code`: estaba
    cableado a nivel de librería y el CLI nunca lo pasaba (dormido). Flag
    `--repo-map/--no-repo-map`; candidatos = `git ls-files '*.py'`; el builder
    recorta a 4KB por relevancia. mypy limpio; 130 tests coders/CLI verdes.
  - Base para lo siguiente: la encuesta harness-engineering 2026-06-27 (9
    arneses, 25 técnicas) es el mapa de absorción; prioridad dictada por
    evidencia de presión real, no por catálogo.
  - BLOQUEO que requiere al operador: el runtime de Ollama está COLGADO a
    nivel de sistema — ambos modelos locales (llama3.1:8b y qwen2.5-coder:7b
    recién descargado) crashean con "signal arrived during cgo execution" con
    10GB de RAM libre. El servicio es root (pid 2476); arreglo probable:
    `sudo systemctl restart ollama` (o el unit que corresponda). Sin esto,
    Atlas no tiene último recurso local y las delegaciones dependen 100% de
    tiers gratis rate-limitados.

- **2026-07-08 — Delegación real a Atlas destapa cadena de proveedores podrida**
  (sesión Fable 5; manía delegar-en-Atlas aplicada con presión real).
  - Delegado a `atlas code --engine tool` (worktree aislado `../atlas-codegraph`)
    el slice 1 del grafo de código. La PRESIÓN destapó, con evidencia en vivo:
    (1) `groq_deepseek_r1` decomisionado por Groq — retirado de DEFAULT_PROVIDERS;
    (2) `openrouter_hermes_405b` y `openrouter_liquid` muertos (NotFound) — retirados;
    (3) el fallback aterrizaba requests CON tools en modelos sin tool-calling
    (groq_compound) y el coder moría — arreglado: `Provider.supports_tools` +
    filtro en `_infer_raw` + marcado EN CALIENTE al ver "tool calling not
    supported" (3 tests nuevos, 39 verdes en test_inference_hub_real.py);
    (4) threshold del LessonRecaller en codegen: 0.8 no recuperaba NADA — medido
    en vivo (relacionadas 0.55-0.69, ajenas ≤0.47) y fijado a 0.55 SOLO en el
    camino avoid_patterns del facade (inmune intacto).
  - Conocimiento inyectado a Atlas: 3 lecciones corroboradas en
    `workspace/lessons` (orden de docs, run_item muta árbol vivo, multihop≠grafo
    + Kuzu libre para KG temporal); recall verificado con el threshold nuevo.
  - Resultado de 5 delegaciones: Atlas ESCRIBIÓ un scripts/code_graph.py
    funcional (verificado contra src real: 199 módulos, 464 aristas; fan-in
    top: merkle_logger 38, contracts 26) en `../atlas-codegraph`; sus tests
    quedaron rotos porque las iteraciones fueron saboteadas primero por rate
    limits y luego por /tmp lleno (3.5GB de temporales pytest — limpiado).
    Techo observado: el cuello es PROVEEDORES+infra, no el arnés.
  - ollama: qwen2.5-coder:7b descargado; ollama_local cambiado a llama3.1:8b
    (el config apuntaba a un modelo inexistente — el último eslabón del
    fallback fallaba justo cuando más se le necesitaba).
  - Verificación final (tras limpiar /tmp): suite COMPLETA `2871 passed,
    2 skipped` (exit 0) + mypy limpio + 39 verdes en test_inference_hub_real.

- **2026-07-08 — Grafo de conocimiento de docs (slice 1, nativo)**
  - `scripts/docs_graph.py`: grafo real desde `[[wikilinks]]` (convención que ya
    vivía en membrana/; resolución por stem exacto Y por prefijo) + mdlinks.
    Consultas: salientes/backlinks/rotos/huérfanos. Sin Obsidian ni Graphiti
    como dependencia, pero markdown+wikilinks = vault compatible.
  - Señal real del primer build: 21 enlaces rotos accionables (docs vigentes;
    archive filtrado) incl. OSMs referenciados nunca escritos (OSM-001/002/
    011/016/017/020/021/034…) y **106 docs vigentes sin ningún enlace**.
  - Autodefensa: `docs_graph_drift` en sanitation_audit y en PreflightGate.
  - 7 tests nuevos (25 en el bloque docs-tooling). Slice 2 propuesto (backlog):
    fusionar docs+memoria en Kuzu (ya dependencia core) con aristas
    bitemporales, patrón Graphiti/Zep (arXiv:2501.13956).
  - Hallazgo colateral: 15 worktrees huérfanos de ColdUpdate (1.7 GB) en
    `../atlas-cold-updates/` — fuga de limpieza; chip/tarea creada.
  - Verificación: suite COMPLETA `2868 passed, 2 skipped` (exit 0) + mypy
    limpio (216 ficheros).

- **2026-07-08 — Orden real de docs/: reorganización + índice máquina + inbox/triage**
  (sesión Fable 5, aprobado por el operador: "todo incluida reorganización").
  - Reorg física con `git mv` (historia preservada): `reference/` disuelto →
    `decisions/adr` (35 ADRs) + `decisions/gates` (16 sellos) + `operations/`
    (USAGE, runbook, prometheus, seguridad) + `compliance/` + `outreach/`
    (paper+posts) + `audits/` (26 auditorías + 9 reports). `design/`,
    `membrana/`, `governance/` (REPO_STANDARD+CAPABILITIES), `archive/`,
    `superpowers/`, `skills/`, `demo/` intactos (varios son load-bearing).
    Todas las referencias de código/tests/docs actualizadas; REPO_STANDARD §1
    reescrito con la taxonomía nueva.
  - `docs/INDEX.yaml` (210 entradas): índice MÁQUINA con type/status/verified.
    Generador+validador `scripts/docs_index_audit.py` (--write preserva campos
    curados; --strict para gates). 6 tests.
  - `docs/inbox/` + `scripts/docs_triage.py`: dedupe por hash → reglas
    deterministas → LLM barato (fail-open a `hold`); `--apply` mueve e indexa
    como `status: propuesto` (la promoción a `vigente` es humana). 6 tests.
  - El orden se defiende solo: desviaciones árbol↔índice entran en
    `sanitation_audit.py` y en el `PreflightGate` del lazo (el daemon las ve
    cada hora antes de gastar LLM).
  - Verificación (2026-07-08 ~14:3x): suite COMPLETA `2862 passed, 2 skipped`
    (exit 0) + `mypy src/` limpio (216 ficheros) + radar sin desviaciones de
    índice ni referencias stale tras la reorg.

- **2026-07-08 — Hermes local en PC: Telegram + twin sin VPS**
  - Hermes Agent oficial (`~/.hermes/hermes-agent`, v0.18.2) quedó instalado
    localmente desde el repo de Nous.
  - `ATLAS_DISABLE_TELEGRAM=1`: el dueño del bot vuelve a ser Hermes; Atlas ya
    no hace long-polling sobre el mismo token.
  - `HERMES_KANBAN_TRANSPORT=local`: el canal Atlas -> Hermes deja de depender
    del SSH al VPS; `KanbanBridge` usa el `hermes kanban` local cuando existe.
  - Atlas ya delega de verdad por `HermesKanbanAdapter`: el orquestador deja de
    duplicar delegaciones exitosas en `OfflineQueue` cuando el board de Hermes
    ya es la fuente durable.
  - Verificación live 2026-07-08 13:18 CEST: `atlas reality --json` reporta
    `hermes.mode=kanban_local`; una delegación real creó la tarea
    `t_57d5aa9f` en Hermes y el worker local la completó con éxito.
  - Telegram verificado en el PC: `hermes-gateway.service` quedó activo y
    `hermes send --to telegram` entregó mensaje al home channel `656190718`.
  - Hardening 2026-07-08 13:25 CEST: NIM quedó como proveedor primario real en
    `~/.hermes/config.yaml` porque OpenRouter agotó crédito y Gemini falló en
    generación real aunque `doctor` validara conectividad básica. Groq quedó
    registrado como proveedor opcional pero no activado porque esta clave hoy
    sí responde por API, pero la cuenta on-demand no soporta el tamaño de
    contexto mínimo que Hermes envía (413 TPM) y por eso no se dejó en la
    cadena automática de fallback.
  - La memoria compartida NO se duplicó: el aprendizaje mutuo sigue viviendo en
    el `LessonStore` unificado `workspace/lessons/`, que ya era la autoridad.

- **2026-07-08 — Cableado v0.1 del lazo de automejora** (sesión Fable 5).
  - `Orchestrator.cold_update()` inyecta `RootCauseClassifier` (¿fallo ambiental
    o causado por el diff?) con hub diferido `_DeferredHub` (fail-open).
  - `MaintenanceFacade.maintenance_cold_update_batcher()` inyecta
    `BatchPremortemGate` (riesgo de COMBINAR antes de pagar la suite) y
    `FailureLessonSink` → LessonStore `workspace/lessons/` (el lazo por fin
    APRENDE de sus fallos: antes las exclusiones de bisección no dejaban lección).
  - Tick de autoconstrucción extraído a `maintenance_self_build_tick()` con
    `PreflightGate` delante (CVEs+radar, determinista): si no pasa, salta el
    ciclo con evidencia Merkle `self_build.preflight_blocked` (nunca silencioso).
  - Contrato fijado en `tests/test_self_improvement_wiring.py` (6 tests).
  - `scripts/sanitation_audit.py`: 4 clasificaciones PARK/KEEP retiradas
    (dejaron de ser 0-importer al cablearse).
  - Verificación (2026-07-08 12:2x): suite COMPLETA `2842 passed, 2 skipped`
    (exit 0) + `mypy src/` limpio en 216 ficheros. Baseline pre-cambios:
    2834 passed, 2 failed.
  - Nota: baseline previo de la suite completa: 2834 passed, 2 failed — ambos
    fallos eran la AUSENCIA de AGENTS.md/WORK_LEDGER.md (cuarentena), no código.
