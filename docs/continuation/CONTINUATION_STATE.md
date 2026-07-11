# CONTINUATION_STATE — Atlas OS

Actualizado: 2026-07-11 (sesión Fable 5/Opus, Fase 15 + Fase 16 — Product OS;
misma fecha, sesión posterior Sonnet — Phase Recovery F1-F16).

## Current Status

Sobre la base final-compatible del 2026-07-10 (Event Kernel, Backend
Bridge, UI shell, governance inicial), Fase 15 construyó el sustrato de
producto exigido por `atlas_product_os_liquid_ui_pack_v1` (Integration
Fabric, PolicyEngine, Business Core, Question Engine). Fase 16 (misma
sesión, más tarde) cerró los 8 gaps priorizados en
`docs/continuation/phase15/RECOMMENDED_PHASE_16.md`: convergencia de
evaluadores, Gate Engine real, persistencia, Sector/Objective Registry,
Legal registry, invariante estructural, primer conector real (Gmail),
arnés UI. **26 schemas, 190 tests OS.** Detalle: `docs/continuation/
phase15/PHASE_15_COMPLETION_REPORT.md` (Fase 15) + este fichero (Fase 16).

Una tercera sesión (misma fecha) auditó si las fases 1-14 realmente
existían antes de F15/F16 (el usuario sospechaba un salto de numeración sin
verificar). Veredicto completo: `docs/continuation/phase_recovery/
PHASE_RECOVERY_FINAL_VERDICT.md`. Resumen: F0-F4/F7-F10 SÍ están
implementadas con evidencia real; F11-F14 nunca existieron como concepto
(5 numeraciones de fase distintas entre los 3 packs, ninguna las define);
Fase 5 (Visual Orchestrator Territory) y Fase 6 (Coding+Research
Territories) de `atlas_build_pack/docs/atlas-bible/17_PHASES_ROADMAP.md`
SÍ estaban definidas y NUNCA se ejecutaron — parkeadas formalmente en
ADR-066 (no bloqueaban F15/F16, no se implementan ahora). F15/F16
reconciliadas: siguen sanas, sin cimientos rotos.

Una cuarta sesión (misma fecha) cerró los 3 ZIPs fuente como unidades
formales (`docs/continuation/zip_closure/FINAL_ZIP_CLOSURE_VERDICT.md`,
ADR-067 sobre autoridad de la Constitución) y luego, ante la sospecha del
operador de que el foco se había desviado hacia verticales de negocio
demasiado pronto, corrigió el encuadre con **ADR-068**: F5/F6 no son
trabajo de producto opcional, son candidatas a **núcleo de
autoconstrucción** (Dynamic Workflow Control Surface / Coding+Research
Workbench) — pero siguen SIN implementarse (ADR-066 sigue vigente en
cuanto al parking en sí). No se escribieron specs de alcance de UI nuevas
en esta sesión por escasez real de tiempo — ver "Estado real honesto"
abajo en vez de asumir que hay más trabajo de planificación hecho del que
realmente hay.

## Estado real honesto (2026-07-11, para cuando no haya tiempo de releer todo)

Preguntas que el operador hizo directamente, respondidas con evidencia,
no con optimismo:

- **¿Está completo el grafo (Kuzu)?** Real y sano en lo que cubre: 237
  módulos, 73 commits ingeridos, hubs con sentido (`merkle_logger` fan-in
  38, `core.contracts` 27, `inference_hub` 20 — coincide con lo que
  realmente es central en el repo). **Pero va por detrás**: no ha
  ingerido los últimos ~4 commits de hoy (Phase Recovery, cierre de ZIPs,
  ADR-067/068) porque la ingesta está gateada por HEAD con swap (el
  write-lock de Kuzu excluye lectores mientras otro proceso escribe —
  arquitectura conocida, no un bug nuevo). No está roto. Está desfasado
  unas horas, lo normal.
- **¿Está bien la UI/UX?** No, y eso es correcto, no un fallo: `ui/
  atlas-shell` es un arnés de validación (D11, ADR-059), nunca se diseñó
  para verse bien. 13 componentes reales (no stubs, verificado línea a
  línea en `docs/continuation/phase_recovery/PACK_MANIFEST_atlas_fable5_
  handoff_v1.md`), pero cero inversión estética deliberada. Que "sea una
  mierda" visualmente es la decisión tomada, no una sorpresa.
- **¿Se construye bien Atlas a sí mismo?** El MECANISMO funciona,
  verificado con evidencia fresca de hoy: el daemon de `ColdUpdate`/
  self-build dejó 12 worktrees, uno modificado hoy mismo
  (2026-07-11 18:29), y uno de ellos (`9ffbf78c`, "atlas update status")
  ya está mergeado en `main` limpiamente (confirmado `ANCESTOR-OF-MAIN`).
  Es decir: el lazo construye, prueba y mergea trabajo real sin
  intervención, al menos para tareas pequeñas. Lo que NO está verificado
  con la misma solidez es la CALIDAD de las decisiones que toma sin
  supervisión en tareas grandes — eso requeriría auditar contenido, no
  solo mecánica, y no hubo tiempo esta sesión.

## What Is Real

- Todo lo de Fase 15 (Integration Fabric, PolicyEngine, Business Core
  draft-first, Question Engine — ver entrada anterior de este fichero).
- **Gate Engine**: `request_activation` abre un `GateTicket` real
  (`open→approved|rejected`), `approve_activation` lo aprueba, nuevo
  `reject_activation`. "Gated" es un objeto auditable, no un flag.
  `GET /gates/open`, `atlas gates list`.
- **PolicyEngine converge con `/permissions/evaluate`** para toda acción
  que sea una capability del catálogo (ADR-062); legacy intacto para el
  resto.
- **Sesiones de onboarding persisten a disco** (sobreviven reinicio del
  bridge, probado con dos apps sobre el mismo path).
- **Sector Registry + Objective Registry**: `GET /sectors`, `/objectives`;
  test de drift real contra los packs existentes.
- **Legal/ToS registry**: `recipes_missing_terms` audita que toda receta
  de riesgo legal tiene su entrada.
- **`personal_channel` estructural**: el invariante de canal personal ya
  no depende del nombre del conector, es un campo del schema chequeado
  en código.
- **Primer conector real**: `GmailReadOnlyConnector` (stdlib `urllib`,
  cero dependencia nueva). Real solo si `env:GMAIL_OAUTH_TOKEN` existe;
  si no, `BLOCKED_BY_MISSING_DEPENDENCY` honesto. `email.send` ausente.
- **Arnés UI real**: vista "⚑ Harness" en `ui/atlas-shell` conduce
  `/connections`, `/business`, `/gates` reales — verificado con
  navegador real (no solo build).
- **Autobuild Ledger real** (2026-07-11, ADR-068): vista "◎ Autobuild
  Ledger" + `GET /self-build/summary` — primera porción real de la
  Dynamic Workflow Control Surface reencuadrada. Lee
  `atlas-cold-updates/proposals.json` (ledger real de ColdUpdateManager,
  ADR-025) sin instanciar la clase (solo lectura de fichero, igual que
  `/memory/summary`). Muestra las 229 propuestas reales del lazo de
  autoconstrucción con su estado real. Verificado en navegador real
  contra bridge real, 192 tests OS verdes (190+2 nuevos), mypy limpio.
- **Primer rediseño visual real del shell** (2026-07-11): `ui/atlas-shell`
  deja de ser puro arnés sin inversión estética (D11 seguía vigente en la
  parte "cero inversión estética" hasta ahora). Nuevo sistema de diseño en
  `styles.css` + `index.html`: tipografía Chakra Petch (display) + JetBrains
  Mono (datos/cuerpo, coherente con "es un panel de telemetría, no una app
  de consumo"), paleta HUD (cian eléctrico `--accent: #2fe3ff`, violeta
  `--accent-2`), paneles con esquinas recortadas (`clip-path`), glow real en
  estados activos/conectados, textura de rejilla de fondo. Es solo capa
  visual — cero cambio de lógica, cero componente nuevo, cero endpoint
  nuevo. Verificado: `tsc --noEmit && vite build` limpio, navegador real
  contra bridge real (fuentes/clip-path/colores confirmados vía
  `getComputedStyle`, no solo captura visual). D11 sigue vigente en cuanto
  a "no es la IA final" — esto es un sistema de diseño coherente, no una
  reestructuración de información ni nuevas pantallas.
- **Autobuild Ledger — detalle de propuesta** (2026-07-11): `GET
  /self-build/proposal/{id}` (parsea el `.patch` real para listar ficheros
  tocados, expone validación pytest/mypy real, calcula el siguiente
  comando CLI real sin ejecutarlo — el bridge sigue read-only). Ver
  ADR-068 "Actualización 2" para el detalle y para un hallazgo real
  encontrado al verificar: hay una propuesta (`Cablear el vault Obsidian
  al tick del grafo`) que se repite cada 1-2 horas en estado `proposed`
  sin converger nunca a `validated` — self-build daemon posiblemente
  atascado en un reintento no convergente. Nombrado como candidato de
  investigación, no investigado todavía.
- **Living Knowledge Graph con presencia real** (2026-07-11): el panel
  central dejó de congelarse en cuanto el layout de d3-force se asienta.
  Nodos respiran (`atlas-breathe`, ritmo distinto por nodo vía hash
  determinista del id — no en bloque), los nodos `running`/con actividad
  alta tienen halo con glow real (filtro SVG `feGaussianBlur`), las
  aristas conectadas a un nodo activo hacen fluir un dash animado
  (`atlas-flow`) con el color del nodo, y el fondo tiene atmósfera de
  radar (3 anillos + barrido rotatorio de 10s). Colores de nodo ahora
  referencian las mismas CSS vars del sistema de diseño HUD (`--accent`,
  `--accent-2`, `--ok`, `--warn`, `--danger`) en vez de una paleta
  hardcodeada desconectada del resto del shell. Verificado en navegador
  real: `getComputedStyle` confirma las 3 animaciones activas
  (`atlas-breathe`/`atlas-flow`/`atlas-sweep`), click-to-inspect intacto,
  cero regresión. `tsc --noEmit && vite build` limpio.

## What Is Simulated

- Todo lo de Fase 15 sigue simulado igual (intent pipeline, conectores
  Fase 4-9 mock, /graph fixture).
- Gmail sigue en `mode=mock` de facto hasta que el operador aporte
  `GMAIL_OAUTH_TOKEN`; el seam es real, la llamada viva está gateada a
  la credencial.
- `BusinessCore.activation.gate_ticket_id` referencia un ticket real,
  pero el Gate Engine todavía solo cubre activaciones de Business Core,
  no toda acción `require_gate` del PolicyEngine (Fase 17).

## What Was Changed (Fase 16)

8 commits en `main` (sin push): `51c57c77`→`847a18c2`. Todo aditivo salvo
`fixtures/governance/gates.json` (+8 gates, ya en Fase 15) y el rename del
invariante whatsapp→`pol_hard_personal_channel_send`. Un título de commit
corregido con `amend` (copy-paste, cuerpo ya era correcto — no se cambió
contenido, solo el título).

**Hallazgo relevante**: el daemon de autoconstrucción del repo
(`ATLAS_SELF_BUILD=1`, proceso vivo) implementó F16-6 (HarnessPanel) de
forma autónoma, en paralelo, usando los endpoints reales según se
commiteaban esta sesión. Verificado y aceptado tras auditoría completa
(build+bridge real+navegador real). Ver IMPLEMENTATION_LOG para el detalle.

## Architecture Decisions Made (Fase 16)

- ADR-062 (convergencia PolicyEngine ↔ evaluador v1).
- ADR-063 (Gate Engine real).
- ADR-065 (primer conector real Gmail, cliente propio stdlib — el
  Cónclave descartó la ruta MCP-del-tronco por hecho: el bridge no puede
  llamar MCP).

## Risks

Ver `docs/risks/RISK_REGISTER.md`. Nuevo: el daemon de autoconstrucción
corre en paralelo contra el mismo repo sin coordinación explícita con la
sesión interactiva — funcionó bien esta vez (cero colisión de ficheros)
pero es un riesgo de coordinación a vigilar si crece el paralelismo.

## Next Best Tasks

`docs/continuation/phase15/RECOMMENDED_PHASE_16.md` queda con sus 8 ítems
todos cerrados. Ver `docs/continuation/zip_closure/CANONICAL_WORK_ORDER_
AFTER_ZIPS.md` para los candidatos nombrados formalmente.

**Orden de prioridad corregido (2026-07-11, ADR-068)**: antes de
verticales de negocio (restaurante, gestoría, legal, sanidad, CRM/ERP
completos — todos siguen sin fecha), lo que de verdad desbloquea a Atlas
es que se autoconstruya mejor: Coding+Research Workbench y Dynamic
Workflow Control Surface (F5/F6 reencuadradas) están por delante de
cualquier vertical en la lista de intención — pero **ninguna de las dos
tiene todavía un spec de alcance escrito**, y no se escribió en esta
sesión por tiempo real. Es la tarea más honesta pendiente para la próxima
sesión con presupuesto: escribir el spec de UNA de las dos (no ambas a la
vez), no más documentos de reencuadre.

## How To Run

```bash
cd ~/proyectos/atlas-core && source .venv/bin/activate
PYTHONPATH=src atlas os-bridge          # bridge en 127.0.0.1:7341
cd ui/atlas-shell && npm install && npm run dev   # shell en 127.0.0.1:5173 (ARNÉS, ver su README)
```

## How To Test

```bash
PYTHONPATH=src ATLAS_NESTED_TEST_RUN=1 python -m pytest tests/test_os_*.py -q   # 190 passed
MYPYPATH=src python -m mypy src/atlas/api/ src/atlas/events/ src/atlas/fabric/ src/atlas/business/ src/atlas/interfaces/cli.py
cd ui/atlas-shell && npm run build      # tsc strict + vite
```

## Known Failures

Ninguno en los 190 tests OS al cierre de Fase 16.

## Where To Continue

Leer EN ORDEN: este doc → `docs/continuation/IMPLEMENTATION_LOG.md`
(entrada Fase 16) → ADR-062/063/065 → el código de `src/atlas/fabric/gates.py`,
`src/atlas/business/registries.py`, `src/atlas/fabric/connectors/gmail.py`.

## Warning To Next AI

Todo lo de Fase 15 sigue aplicando (ver entrada anterior de este fichero:
NO Orchestrator, NO tocar ficheros del operador, NO `git add -A`, NO
importar `atlas.api.*` a nivel de módulo desde `fabric/`/`business/`,
motores nuevos con `path` explícito en tests). Añadido en Fase 16: **hay
un daemon de autoconstrucción vivo contra este repo** — antes de escribir
código nuevo, comprueba `ps aux | grep ATLAS_SELF_BUILD` y `git status`
por si ya hizo el trabajo; verifícalo (build+tests+smoke real) en vez de
descartarlo o sobrescribirlo a ciegas.
