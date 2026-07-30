# Status — Atlas Definitive Candidate

Fecha de corte: 2026-07-29. Baseline:
`c95038c9d7e97ddc6339f38abe6dad09b166f47d`.

Este fichero no concede aceptación. El estado granular de 137 componentes y
capacidades está en `docs/canon/component_reality_matrix.jsonl`.

## Vocabulario

| Estado | Significado |
|---|---|
| MISSING | no existe la capacidad |
| HISTORICAL | solo hay evidencia pasada |
| RESEARCH | material para estudiar, sin decisión |
| PROPOSED_DESIGN | diseño no aceptado |
| ACCEPTED_DESIGN | arquitectura aceptada, no necesariamente construida |
| PROTOTYPE | prueba de concepto acotada |
| VALIDATION_HARNESS | arnés para validar backend/hipótesis, no producto |
| CODE_PRESENT | implementación localizada |
| TESTED | pruebas aplicables presentes y satisfactorias en la evidencia citada |
| WIRED | existe caller/route real |
| RUNTIME_CONFIGURED | configuración observada; no prueba comportamiento |
| LIVE_VERIFIED | observación fresca fechada y satisfactoria |
| PRODUCT_ACCEPTED | aceptación explícita del operador |
| PARKED | conservado fuera de construcción activa |
| SUPERSEDED | reemplazado en un alcance explícito |
| CONTRADICTED | fuentes válidas discrepan o el registro derivado no está resuelto |

La candidata no hereda `LIVE_VERIFIED` del baseline después de cambiar el
árbol. Las observaciones base se preservan abajo y deben repetirse contra el
commit final cuando el mismo scope lo permita.

## Integración y continuidad

El 2026-07-29 la rama definitiva se integró y publicó por fast-forward:
`main`, `origin/main` y la rama candidata coincidían en `0fea4c6` antes del
commit de continuidad posterior. El checkout no conserva cambios de esta
sesión fuera de Git; sólo el ZIP fuente R2.1 permanece deliberadamente
untracked. Las variantes vivas anteriores están publicadas en
`recovery/pre-definitive-live-20260729`.

La tabla de candidata inferior es evidencia histórica de sus anchors, no una
validación integral del HEAD actual. Después se añadieron hardenings de
ColdUpdate/Bwrap/Kuzu/editor/router con pruebas focales y receipts Bwrap, por
lo que la siguiente sesión debe ejecutar suite completa, mypy completo, UI,
audit y Reality antes de elevar la candidata. Reality fresco de este cierre
proyectó: grafo `STALE` en `c95038c`, F2.6 `due` por siete ADR, navegador
degradado sin Playwright y Hermes mock/no configurado.

**Esa revalidación se ejecutó el 2026-07-29** (ver sección siguiente). Dos de
sus proyecciones no se confirmaron al medirlas: el navegador estaba `ready` con
Chromium presente, y el grafo estaba `DIRTY` frente a HEAD, no `STALE` en
`c95038c`.

## Revalidación ejecutada — 2026-07-29

Evidencia fresca con exit code capturado. **No eleva la candidata a
`LIVE_VERIFIED`**: concede `TESTED` fechado y nada más, porque parte se midió
sobre un árbol con delta sin commitear (no reproducible por SHA) y el resto
sobre `739ca8f`+.

| Comprobación | Exit | Resultado |
|---|---|---|
| `pytest tests/ -q` | 0 | 4692 passed, 6 skipped, 27 deselected |
| `mypy src/atlas/` | 0 | 331 ficheros |
| `atlas audit --verify` | 0 | cadena Merkle íntegra |
| `atlas reality --run-checks --include-browser` | — | `status=ok`, `strict_failures=[]`; browser 27 passed |
| `uv lock --check` | 0 | 301 paquetes |
| `pip-audit` | 0 | 0 vulnerabilidades tras ADR-079 |
| UI `npm ci --engine-strict` | 1 | **ENVIRONMENTAL FAIL**: `EBADENGINE`, host npm 11.14.1 vs `>=10.9.0 <11` |
| UI `npm ci` + `build` + `audit --audit-level=high` | 0/0/0 | 0 vulnerabilidades; chunk 674,82 kB |

Hallazgos de la revalidación, ya cerrados: el vocabulario `blocked-admission`
rompía el catálogo MCP en runtime (37 tests); el pre-commit no mapeaba ficheros
de datos a tests y lo dejó pasar; `mcp` 1.23.3 arrastraba 3 advisories con
exposición cero (ADR-079); 6 worktrees efímeros huérfanos y su causa.

Sigue sin poder afirmarse: Hermes `mock`, MCP con 2 servidores **sin
handshake**, sin proveedores externos en el entorno del comando.

**F2.6: `current`, con veredicto `fail` (2/6).** El primer intento del
2026-07-29 con el driver `claude` falló (`401 OAuth access token has been
revoked`) y correctamente no registró nada sin transcript válido. Después se
construyó `--driver agentic` (`f26_agentic_dispatch.py`): bucle de
tool-calling de `InferenceHub` sobre cualquier proveedor de `.env`, mismo
grading sin tocar. Corrida real con `gemini_free`: 29,3 s, exit 0,
auto-registrada (`last_run_sha=ee8003d`). **F2.6 ya no depende de una
credencial de Claude.** Lo que falta para un pase es scaffolding del
prompt/harness o un modelo con más capacidad agéntica — el 2/6 se conserva
sin retocar el prompt, que sería gaming de la propia rúbrica.

**Nota durable:** `pip-audit --strict` no puede pasar en este checkout ni con
cero vulnerabilidades — trata "no auditable" como fallo y `atlas-core` (local,
0.12.0) no está en PyPI. La fila `pip-audit --strict | PASS` de la tabla
histórica inferior no es reproducible aquí.

El pack `docs/handoff/GENERATED/` se regenera desde las fuentes canónicas. Su
gate admite únicamente el commit descendiente que contiene paths no vacíos y
exclusivos del propio pack; cualquier commit vacío, ajeno o mezclado sigue
marcándolo `STALE`. El snapshot runtime gitignorado
`docs/audit_complete_latest.json` queda fuera del índice documental, mientras
`docs/audits/audit_complete_latest.json` conserva su papel de evidencia.

## Validación de baseline

| Comprobación | Resultado fresco | Interpretación |
|---|---|---|
| ZIP R2.1 SHA-256/CRC | PASS | paquete íntegro, no canon automático |
| validator/secret scan/tests del paquete | PASS / 19 tests | metodología del paquete consistente; no prueba Atlas |
| `pytest tests/ -q` | PASS: 4515, 6 skipped, 27 deselected | base Python sin fallo |
| `mypy src/atlas/` | PASS: 318 archivos | base tipada sin issue |
| `atlas audit --verify` | PASS | cadena Merkle base íntegra |
| `atlas reality --json` | PASS | agregador base ejecutó; sus límites se conservan |
| `atlas doctor` / `atlas health` | exit 0 con warnings | sin proveedores externos ni Hermes live |
| UI `npm ci --engine-strict` | ENVIRONMENTAL FAIL | host Node 24/npm 11; proyecto exige Node 22.22.2/npm 10.x |
| UI `npm ci` + `npm run build` | PASS con warning de engine | código compila en host no canónico |
| UI `npm audit --audit-level=high` | BASE: PRE_EXISTING MAJOR; CANDIDATE: PASS | override lock-only a PostCSS 8.5.23; 0 vulnerabilidades tras `npm ci` |

El build produjo un chunk JS de ~675 kB y Vite advirtió sobre code splitting;
es deuda de rendimiento, no fallo de compilación.

## Validación de candidata

Anchor sustantivo validado:
`ff439d2840e30754fbf8175e0b61c59cf4e3c4de`.
En ese corte los commits posteriores eran estado/reportes; esta afirmación
quedó supersedida por los hardenings integrados después. La tabla se conserva
como receipt histórico y no se extrapola al HEAD actual.

| Comprobación | Resultado | Clasificación |
|---|---|---|
| `pytest tests/ -q` | PASS: 4559, 6 skipped, 27 deselected | sin regresiones |
| `mypy src/atlas/` | PASS: 318 módulos | sin issues |
| `atlas reality --run-checks --include-browser --json` | PASS / `status=ok`, 0 strict failures | core, mypy y browser proyectados |
| Browser marker | PASS: 26, 1 skipped, 4565 deselected | navegador fresco |
| `atlas audit --verify` | PASS | Merkle íntegro |
| Canon + tests | PASS: 2062 registros / 15 tests | autoridad machine-readable íntegra |
| Docs index strict | PASS: 906 entradas | 0 ausentes/huérfanas de índice |
| UI install/build/audit | PASS / 0 vulnerabilidades | warning ambiental de engine y chunk |
| `uv lock --check` | PASS: 301 paquetes | lock coherente |
| `pip-audit --strict` | PASS | 0 vulnerabilidades conocidas |
| Wheel Python 3.11 | PASS | import, recursos y CLI fuera del checkout |
| Secret scan de cambios | PASS | 0 tokens/claves/credenciales detectados |

Reality fresco conserva límites, no los maquilla: Hermes está mock/no
configurado/no live; MCP tiene dos servidores configurados sin handshake; no
hay proveedores externos; el grafo Kuzu compartido corresponde al baseline y
está `STALE` frente a la candidata. No se sobrescribió desde el worktree para
no contaminar el runtime del checkout original.

## Runtime base observado

El checkout original, no este worktree candidato, estaba ejecutando
`atlas serve`. Observaciones permitidas, sin exponer secretos:

- Reality 0.12.0: 318 archivos fuente y 358 archivos de tests;
- Merkle: 10.012 registros verificados;
- grafo estructural: `FRESH` en el SHA base, 289 módulos/741 imports;
- browser/Chromium: disponibles;
- MCP: dos servidores habilitados en configuración; sin handshake vivo;
- Hermes: mock, no configurado, no live;
- providers externos: ninguno en el entorno del comando;
- Gate D, project graph, research, self-build, MCP vetting y Security Council:
  flags configurados en el proceso original;
- MCP reseed y ColdUpdate auto-apply: apagados;
- F2.6: `never_run`, no ejecutado porque no estaba `due`.

Estos datos prueban exactamente configuración/observación del baseline. No
prueban el worktree candidato, tráfico de todos los gates ni producto aceptado.

## Estado por programa

| Programa | Current demostrado | Target/gap principal |
|---|---|---|
| P00 | autoridad distribuida; registries y gate de candidata | aceptación del operador y mantenimiento continuo |
| P01 | Policy/Decider/capabilities fragmentados pero reales | owners tipados y boundary Mission/Task |
| P02 | graph/trunk code+tests+wiring; base graph fresh | refresh final y ContextPackets reproducibles |
| P03 | cognition/orchestrator/task code+tests+wiring | separar autoridades y cerrar Task owner |
| P04 | stores, tenancy, cifrado, shred y wiring | memory authority y private→shared distillation |
| P05 | research/knowledge code+tests+wiring; ticks base | temporal claims y promoción verificable |
| P06 | Golden Route/Foundry/ColdUpdate v0 wired | build completo medido y rollback aceptado |
| P07 | plugins, MCP/ACP, vetting A/B implementados | smokes live; C permanece ausente |
| P08 | shell como harness; host/donors aceptados; desktop MCP code/wiring presente pero runtime `CONTRADICTED` por cuarentena | Cut 1 interno, admisión desktop gobernada, Workbench integral y Android |
| P09 | seguridad/eval/ops reales; Merkle base verificado; EngineeringFinding v1, review, diagnóstico, reproducción Bwrap auditada, publisher Merkle/EventBus, baseline, normalizador incremental observacional y preflight de bloqueo absoluto del editor code+tests sin wiring | routing gobernado, recovery y traffic evidence |
| P10 | Hermes Kanban wired; NodeIdentity code+tests | pairing/federation live autorizado |
| P11 | Hosted Linux actual | Hosted product; Native Wave 5 bloqueada |
| P12 | corpus OSM + slice ADR-074 | guarantee profile y promotions medibles |

## Componentes críticos

### Canon y Reality

- Authority registry: **CODE_PRESENT** como artefacto de candidata; validación
  CI incluida. No es una nueva constitución.
- Reality Kernel: **CODE_PRESENT / TESTED / WIRED**. El comando base ejecutó
  satisfactoriamente. `overall=ok` no significa que Hermes, MCP, graph,
  browser y todos los subsistemas estén live salvo checks explícitos.
- Structural graph: **CODE_PRESENT / TESTED / WIRED**; baseline
  **LIVE_VERIFIED FRESH**. Tras commits de candidata: refresh pendiente.

### Mission, Foundry, Memory y Knowledge

- Mission/Golden Route: **ACCEPTED_DESIGN / CODE_PRESENT / TESTED / WIRED**.
  Es v0 acotado; no `PRODUCT_ACCEPTED`.
- SelfBuild/Foundry/ColdUpdate: **CODE_PRESENT / TESTED / WIRED**. ColdUpdate
  rechaza antes de worktree/apply rutas fuera de su allowlist, cambios a
  `config/governance.json` y artefactos cuyo SHA-256 ya no coincide con la
  propuesta. `ValidationRunner` ejecuta candidatos en Bwrap read-only/sin red
  y no hereda secretos del host. Kuzu abre con mapa máximo/buffer explícitos y
  sus rutas focales pasan en Bwrap de 2 GiB; todavía no existe un receipt de
  suite completa bajo un cgroup físico independiente. Ninguna de estas
  protecciones prueba un build exitoso. El evento fresco fue preflight
  bloqueado, no build exitoso. Para tests que ya inyectan fetchers, el perfil
  candidato aporta sólo una respuesta DNS pública determinista dentro de
  pytest; Bwrap sigue sin red y `SSRFBridge` de runtime no se relaja. El hook
  de routing `--no-state` ya no exige HOME al importarse y pasa dentro del
  jail real; esto tampoco constituye un receipt completo.
- SQLite/BlockMemory: **CODE_PRESENT / TESTED / WIRED**. El owner final y la
  promoción entre stores requieren operador.
- Knowledge/Research: **CODE_PRESENT / TESTED / WIRED**; ticks base
  observados. Semantic GraphRAG conserva estado de hipótesis.

### Integration, MCP y plugins

- Supply-chain scanner: **CODE_PRESENT / TESTED / WIRED**; alimenta admission
  local, pero su informe es evidencia y nunca concede permiso por sí solo.
- PluginManifest local declarativo: **ACCEPTED_DESIGN / CODE_PRESENT /
  TESTED / WIRED**; tipos remotos ejecutables fuera de alcance.
- MCP reseed (ADR-076 A): **CODE_PRESENT / TESTED / WIRED**, opt-in y apagado
  en el proceso observado.
- MCP vetting (ADR-076 B): **CODE_PRESENT / TESTED / WIRED /
  RUNTIME_CONFIGURED**; cubre stage1/stage2 acotado, no las etapas 3–6
  completas; el flag fue observado en el proceso original.
- MCP auto-adopt ejecutable (ADR-076 C): **MISSING por decisión**;
  **REJECTED / NOT_IMPLEMENTED / ABSENT** en el registro de decisiones.
- Seis candidatos de research: `status=candidato`,
  `deployment_state=NOT_INSTALLED`, pendientes de source/license, vetting,
  TrialGate, Decider/HITL y receipt.

### Seguridad

- ShadowRouter/DriftTripwire: **ACCEPTED_DESIGN / CODE_PRESENT / TESTED /
  WIRED / RUNTIME_CONFIGURED**; no hay tráfico shadow fresco de candidata.
- Security Council: **ACCEPTED_DESIGN / CODE_PRESENT / TESTED / WIRED /
  RUNTIME_CONFIGURED**, opt-in. Los rechazos anteriores son evidencia
  histórica/operacional, no una acción fresca de este commit.
- ADR-077 C: escalación universal a `Task.AWAITING_APPROVAL` **MISSING**; sí
  existen `RequiresHuman`, Merkle y notificación.
- ADR-077 D: unblock **CODE_PRESENT / TESTED**; actor explícito, sin identidad
  humana criptográficamente demostrada.
- Guard high: esta candidata impide que un custom Decider inyectado convierta
  sensibilidad alta en `Allow`; pruebas focalizadas y full suite requeridas.
- Sentinel: snapshots corruptos y errores internos de `vet_call` fallan
  cerrados; el re-vet revoca y pone en cuarentena el server ante drift/error.

### Product OS

- `atlas-shell`: **VALIDATION_HARNESS / CODE_PRESENT / TESTED por build**.
  ADR-059 está supersedido por ADR-071 solo para UX final.
- Universal Bar: **VALIDATION_HARNESS / PROTOTYPE / CODE_PRESENT**; intent
  pipeline simulado.
- NebulaGraph: fixture/snapshot baked; sin commit/date/schema, no live.
- LivingGraph: **CODE_PRESENT en harness**, sin importadores; integrar o
  aparcar, nunca sobreafirmar.
- Desktop-control: **CODE_PRESENT / WIRED / CONTRADICTED**. Sentinel demuestra
  cuarentena pre-spawn auditada para el ejecutable sin receipt; los cuatro E2E
  Xvfb se conservan pero se difieren por `ADC-WO-124`. La ejecución de
  2026-07-24 es histórica y no concede `TESTED` actual ni `LIVE_VERIFIED`.
- Bridge 7341: **CODE_PRESENT / TESTED / WIRED / CONTRADICTED**. ADR-058/071
  lo definen read-only, pero el código contiene POST mutantes; `ADC-WO-107`
  requiere decisión del operador y la candidata no amplía esa superficie.
- Presence Engine y Liquid UI: **PROPOSED_DESIGN**.
- Atlas Engineering Workbench: **ACCEPTED_DESIGN / MISSING**; es el primer
  producto decidido por ADR-078, todavía no `PRODUCT_ACCEPTED`.
- CodeOSS/VSCodium: **HOST_BASELINE / ACCEPTED_DESIGN**, código externo no
  importado a Atlas Core en esta candidata.
- Void: **PORT_SOURCE / PROTOTYPE / ACCEPTED_DESIGN** como donante de
  capacidades; no wired en Atlas Core.
- Zed: **PATTERN_DONOR / RESEARCH / ACCEPTED_DESIGN** para ACP y patrones
  seleccionados; no wired ni adoptado como producto.
- Android dedicado: **ACCEPTED_DESIGN / MISSING**, bloqueado hasta estabilizar
  Surface API y Workbench contracts.

### Hermes, Hosted y Membrane

- Hermes Kanban: **CODE_PRESENT / TESTED / WIRED / HISTORICAL**; no
  `RUNTIME_CONFIGURED` ni `LIVE_VERIFIED` en el preflight.
- NodeIdentity: **CODE_PRESENT / TESTED**, no wired.
- Hosted Linux: **CODE_PRESENT / WIRED / RUNTIME_CONFIGURED** como sustrato,
  no como producto final aceptado.
- Native: **RESEARCH / PARKED**; Wave 5 **BLOCKED**.
- Membrane/Osmosis: **RESEARCH** con código/slices parciales; ADR-074 promueve
  solo OSM-042 fase 1.

## Documentos y fuentes dirty

- Cuatro research reports: importados íntegros como `RESEARCH/PROPOSED`.
- `docs/INDEX.yaml`: se regenera para esos informes, ADR-076/077/078 y canon.
- Stage-1 MCP: diff rechazado, era solo `generated_at` sobre 2.106 filas
  semánticamente idénticas.
- Classified MCP: seis candidatos importados con estado no instalado
  explícito; no se hereda la falsa lectura de `mode=installed`.
- ZIP: verificado y usado como fuente inmutable; no copiado como un segundo
  Atlas dentro del repo.

## Pendiente, aparcado, bloqueado y supersedido

- **Pendiente operador:** Mission/Task, memory authority, boundaries exactos
  del Cut 2, arquitectura Android, Hermes live y Osmosis enforcement.
- **Aparcado:** Native research y surfaces de producto posteriores.
- **Bloqueado:** Native Wave 5; cualquier debilitamiento de high; MCP remote
  executable auto-adoption.
- **Bloqueado técnicamente:** promoción de validación completa ColdUpdate:
  el perfil Kuzu ya es explícito, pero falta un receipt completo repetible
  bajo un cgroup físico independiente; no se relaja el techo Bwrap ni se
  infiere éxito desde rutas focales.
- **Supersedido:** ADR-059 solo para UX final por ADR-071; ADR-066 solo en su
  framing F5/F6 por ADR-068, conservando parking; Hermes REST por ADR-070.
- **No resuelto pero visible:** records derivados “recovered component
  requiring semantic review”, ownership y guarantee profiles.

La lista ejecutable y los defaults fail-closed están en `PLAN.md` y
`docs/canon/implementation_registry.yaml`.
