# T2.1 — La UX REAL de Atlas (plan de arranque para sesión fresca)

## LEE ESTO PRIMERO — readback aceptado por el operador (2026-07-17)

El operador vio la consola y fue literal: *"es una puta mierda, no se parece
en nada a lo que yo quiero, es súper genérica y se ve que está generada por
IA… buscaba algo definitivo y profesional, pero no sé el que, habría que
investigar"*.

**No es un fallo de ejecución: es una decisión.** `ui/atlas-shell/README.md`
declara D11 — *"el shell actual es arnés de validación, no la UX final"* — y
`docs/continuation/NEXT_AI_INSTRUCTIONS.md:37` registra que el **pedido de
rediseño JARVIS del operador quedó "SUPERSEDED por el pack de producto antes
de escribirse código"**. La UX final NUNCA se construyó. Se ve generada por
IA porque literalmente es un andamio sin dirección estética.

**D11 QUEDA REABIERTA por el operador** (2026-07-17, es N3: alcance de
producto). El shell deja de ser arnés: pasa a ser la UX real.

**Intención capturada (respuestas del operador, NO reinterpretar):**
1. *Convivencia*: **"Donde yo esté, incluido el móvil"** — necesita alcanzar
   Atlas desde el sofá/la calle, no solo desde el portátil.
2. *Carácter*: **"Cinematográfico (JARVIS, tus 9 mockups)"** — presencia,
   movimiento, que se sienta vivo; impresiona al verlo, no solo al usarlo.

**Consecuencia de encuadre (criterio del driver, revisable):** "es una web"
era el SÍNTOMA, no la causa. Con el móvil como requisito duro, la base web
(ADR-059) se CONFIRMA — reescribir en Tauri daría la misma pantalla genérica
y además mataría el móvil. Lo que falta es dirección estética + presencia
(PWA instalable a pantalla completa, motion real, densidad elegida). La
investigación debe VALIDAR o TUMBAR esto con evidencia, no asumirlo.

**BLOQUEANTE #1 — los 9 mockups NO EXISTEN en el repo** (verificado
2026-07-17: cero imágenes bajo `docs/`; los hits de "jarvis" son proyectos
ajenos del vault). Vivieron en un chat y se perdieron: "estilo JARVIS" ha
sido una referencia fantasma que ningún modelo pudo ver — por eso nadie la
ejecutó. **Primera acción de la ola: pedir al operador que los deposite en
`docs/design/ui/references/`** (o cualquier referencia visual que le guste:
capturas, apps, vídeos). Sin imagen, "cinematográfico" es una palabra y la
IA volverá a inventar genérico. Esto es T0.5-en-vivo: la intención del
operador debe quedar en el sustrato, no en un chat.

## Investigación OBLIGATORIA antes de tocar píxeles (el operador la pidió)

Manía registrada (investigar-antes-de-decidir): barrer el SOTA y comparar,
con enjambre + Cónclave, no con la opinión de una sesión. Preguntas a
responder CON EVIDENCIA (demos/capturas, no prosa):
- ¿Cómo consiguen presencia cinematográfica los productos que se sienten
  definitivos? (motion design, densidad, tipografía, sonido, latencia
  percibida). Referencias reales, no adjetivos.
- ¿Qué stack sostiene "una superficie, escritorio + móvil, sensación nativa"?
  (PWA instalable, Capacitor, React Native, Tauri móvil…) — medir, no opinar.
- ¿Qué hacen las UIs de agentes del SOTA y qué se siente genérico en ellas
  (para NO copiarlo)?
Entregable: 2-3 direcciones REALES que el operador pueda MIRAR y comparar
(prototipo navegable > documento). El operador elige carácter; el driver
elige tecnología (regla de oro: al operador jamás el CÓMO técnico).

---

## (Contexto previo — inventario del andamio actual)

**Para el driver que lea esto**: el operador quiere ponerse a fondo con la
UI/UX. Esta es la ola. NO hay dependencias pendientes: T0 está cerrado
(sucesión viva), el daemon produce misiones/receipts reales, y el grafo se
re-sella solo. La secuencia "T2 después de T1" del plan maestro §5 se
adelanta por criterio de la doctrina §2.5 (el operador NO programa: cada
semana sin consola es él pegando textos entre 200 IAs) — cambio de secuencia,
no de alcance.

## Lo que YA existe (verificado 2026-07-17, no asumir que falta)

- `ui/atlas-shell/` — Vite/React (ADR-059), **1.930 líneas de TSX reales**,
  `node_modules` instalado, scripts `dev`/`build`/`preview`.
- Componentes: `MissionConsole.tsx` (458), `LivingGraph.tsx` (465),
  `AutobuildLedger` (236), `HarnessPanel` (195), `UniversalBar`,
  `RealityPanel`, `MemoryVault`, `Timeline`, `EventInspector`,
  `ExecutionPipeline`, `App.tsx` (291).
- **No son mocks**: `src/core/api.ts` hace `fetch` real contra la API
  (`api.health/graph/events/reality/memorySummary/connectors/permissions`) y
  `connectEventsWs` abre WebSocket de eventos.
- Backend: `src/atlas/api/server.py` (bridge read-only 7341 — JAMÁS meter el
  Orchestrator dentro: corrompe Merkle, memoria atlas-os-foundation).

## Lo que NO se sabe (primer trabajo de la ola: MEDIR, no suponer)

El API server no estaba corriendo el 2026-07-17, así que **nadie ha visto esta
UI viva recientemente**. Antes de diseñar nada:

1. Arrancar API + `npm run dev` (vía preview_start, jamás Bash para servers).
2. Inventario honesto por componente: ¿pinta datos reales, vacío, o revienta?
   Tabla `componente → estado → causa` con evidencia (consola/red/captura).
3. Solo entonces decidir qué se arregla, qué se rehace y qué sobra.

Regla: es EVOLUCIÓN de la consola existente, no reescritura (decisión sellada,
plan maestro §4). Si un componente estorba, se jubila con motivo escrito.

## El objetivo de la ola (evidencia observable)

**El operador aprueba una misión real de la ruta dorada desde la pantalla**,
sin tocar texto ni terminal, y el receipt queda en Merkle. Ese es el corte:
ni más features ni menos.

## Estándar obligatorio (doble skill, sellado)

- `frontend-design:frontend-design` — dirección estética con carácter; los 9
  mockups JARVIS del operador son la referencia. Nada de "AI slop".
- `agent-skills:frontend-ui-engineering` — composición, WCAG 2.1 AA, estados
  loading/empty/error, responsive 320-1440.
- Implementación: Sonnet (economía sellada). Fable/Opus: criterio y auditoría.

## Riesgos conocidos (premortem corto)

- **Reescribir por impulso estético**: 1.930 líneas funcionando valen más que
  un lienzo en blanco bonito. Medir primero (§"Lo que NO se sabe").
- **UI que miente**: si un panel no tiene datos reales, debe decir "sin datos"
  — jamás pintar un placeholder que parezca vivo. Es la disciplina de
  honestidad del proyecto aplicada a píxeles.
- **Meter escritura en el bridge read-only**: la aprobación necesita un camino
  de escritura; diseñarlo por la ruta dorada (aprobación registrada), NO
  abriendo el bridge. Decisión N2 → Cónclave al llegar ahí.

## Después de esta ola

T2.2 (Knowledge view sobre el grafo Kuzu: comunidades navegables — las tools
`graph_communities`/`graph_semantic_neighbors` ya existen) y T2.3 (Visual
Orchestrator, ADR-066).
