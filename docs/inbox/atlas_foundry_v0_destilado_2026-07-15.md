---
status: propuesto
fecha: 2026-07-15
autor: destilación Claude Code (a partir del export de ChatGPT del operador)
fuente: '"Diseño UI Atlas.md" (raíz del repo) — export ChatGPT, 148 turnos, 65.640 líneas, ~2026-07-08→15'
---

# ATLAS_FOUNDRY_V0 — destilación ejecutable del export "Diseño UI Atlas"

El export es una conversación de ~una semana que empieza como diseño de UI y termina en una
decisión estratégica concreta. Esta destilación extrae SOLO lo accionable y lo cruza con el
estado real del repo a 2026-07-15. El fichero crudo queda como fuente; el mapa de líneas de
abajo permite recuperar cualquier detalle sin releerlo entero.

**Verificado contra el repo hoy**: entre los 26 `schemas/*.schema.json` NO existe ninguno de
los contratos Foundry (mission, receipt, soul, evidence_bundle, model_use). Los "mission" que
aparecen en `src/` son falsos positivos (`permission`). El gap que diagnostica la conversación
es real.

---

## 1. Mapa del export (para archivar el crudo sin perder nada)

| Líneas | Contenido |
|---|---|
| 1–1443 | Diseño UI inicial: "Atlas Nexus", 4 propuestas de layout, crítica componente a componente con valoraciones |
| 1444–3049 | Giro conceptual: "es un sistema operativo" → Atlas OS (Cognitive OS) |
| 3050–4115 | Identidad visual: esfera viva central (Obsidian×Siri), grafo con conexiones reales, paletas |
| 4116–6917 | Territorios más allá del grafo (coding, vínculo, deep research); idea "biblia + prototipo"; auditoría premortem |
| 6918–12714 | Ingesta de la investigación paralela "harness orquestador + adapters"; preparación del ZIP 1 y prompt para Fable |
| 12715–20732 | Referencias JARVIS/OpenJarvis/Odysseus; "software líquido"; verticales y sectores |
| 20733–34586 | Generación del contenido de los ZIPs (secuencia "Siguiente" ×13) |
| 34587–38298 | Huecos de conectividad (OAuth click-click, computer-use como fallback), CRM/ERP propio, ZIPs 2-3 |
| 38299–44175 | Ejecución real con Fable/Sonnet: F15, F16, cierre de ZIPs — **ya reflejado en el repo** |
| 44176 | Corrección de foco del operador (autoconstrucción primero, verticales = futuro lejano) — **es la génesis de ADR-068** |
| 44512–53172 | Sesión 15-jul: estética premium, "ser cognitivo vivo", pensamiento observable en todas las capas, UX de futuro |
| 53173–55108 | Multiplataforma/conectividad por sector; **Surface Lifecycle Model** (L53927+) |
| 55109–58800 | Crítica sin sycophancy; Atlas frente al SOTA jul-2026 |
| 58801–63076 | Proactividad (cuándo hablar y qué decir), Model Fabric multi-modelo, catálogo de souls (abogado del diablo, L62412) |
| 63077–65641 | **Síntesis final**: 15 gaps, 7 piedras, contratos mínimos, Atlas Foundry, fases A–F, criterio de éxito |

## 2. Ya ejecutado — NO re-proponer

- F15 (Product OS) y F16 (Gate Engine, Gmail connector) construidas; 3 ZIPs cerrados
  `CLOSED_WITH_PARKED_ITEMS` el 2026-07-11.
- ADR-068 ya reencuadra F5/F6 como núcleo de autoconstrucción — coincide con la corrección
  del operador en L44176 y con la conclusión final del export.
- La exploración estética (esfera Man of Steel, paletas, mockups) fue iterativa y NO terminó
  en decisión de implementación; queda como material de referencia, no como spec.

## 3. La decisión final del export

**Criterio de inclusión** (filtro para todo lo nuevo):

> ¿Esta pieza ayuda a Atlas a construirse mejor, con más seguridad, más trazabilidad, más
> criterio o más autonomía? → entra. ¿Sirve para un sector futuro / demo bonita / vender
> visión? → se aparca.

**Qué se construye**: no "Atlas completo", sino **Atlas Foundry** — la capa operativa donde
Atlas observa, evalúa, critica, explica y gobierna su propia autoconstrucción. UI/UX, souls,
Model Fabric, proactividad y privacidad SÍ entran, pero subordinados a Foundry (maquinaria,
no adorno). Encaja con el objetivo (a) de la visión: que Atlas se construya solo más rápido.

## 4. Las 7 piedras en el zapato (diagnóstico, L63551)

1. **Hay motor, no unidad semántica** — falta la entidad Mission que una eventos, gates,
   policy, proposals y UI.
2. **Seguridad fuerte, privacidad incompleta** — falta redacción, trust boundaries, leak
   verifier, delegation protocol.
3. **Self-build funciona mecánicamente, no epistemológicamente** — valida tareas pequeñas
   pero nadie desafía sus decisiones: faltan Devil's Advocate + Verifier + Arbiter + benchmark.
4. **La UI muestra estado, no intención** — el Autobuild Ledger enseña propuestas, no la
   historia operativa de una misión viva.
5. **Souls sin canal ejecutable** — MCP no puede imponer system prompt (`MURO` ya conocido):
   el Soul Catalog debe ser runtime propio, no carpeta de prompts.
6. **Proactividad sin feedback learning será ruido** — hay que aprender de
   aceptado/ignorado/demasiado-pronto/demasiado-tarde.
7. **Demasiados documentos, poca síntesis ejecutable** — cerrar antes de abrir. (Esta
   destilación intenta ser parte de la cura, no del síntoma.)

## 5. Fase A — Contratos primero (el primer paso real)

Schemas mínimos sin lógica, al lado de los 26 existentes:

```
mission, mission_candidate, mission_receipt, evidence_bundle,
capability_use, model_use, soul_invocation / soul_manifest,
gate_reference, memory_candidate, interruption_decision
```

## 6. Fase B — Adaptar lo real (no inventar)

```
ColdUpdate proposal      → Mission
validation               → EvidenceBundle
next_action              → Mission.next_action
files_touched            → artifacts
/self-build/proposal/{id}→ /missions/{id}
Autobuild Ledger         → Self-Build Workbench
```

## 7. Fase C — Souls mínimas (manifiestos ejecutables)

Paquete por soul: system prompt + skills + tools permitidas/prohibidas + modelo preferente +
política de privacidad + schema de salida + memoria permitida + criterio de evaluación.

Mínimas: `devil_advocate` (la primera y crítica), `verifier`, `arbiter`, `context_sculptor`,
`guardian`. Después: `coder`, `researcher`, `privacy_boundary`, `proactivity_steward`,
`memory_curator`. Al principio pueden producir reviews estructuradas con ejecución parcial
manual/stub marcada — pero el contrato debe existir.

## 8. Model Fabric mínimo (envolver InferenceHub, no reemplazarlo)

Enrutar por tarea (planificación / análisis de diff / patch / aplicación mecánica / review
adversarial / verificación / resumen receipt) y por frontera de confianza:

```
LOCAL_ONLY | LOCAL_DEGRADED | EXTERNAL_REDACTED | EXTERNAL_EXPLICIT_EXPORT | BLOCKED
```

## 9. Fase D — Proactividad acotada: Self-Build Radar

Detectores iniciales (empezar por UNO: `RepeatedSelfBuildProposalDetector` — hay caso real:
la propuesta del vault Obsidian que se repite cada 1-2h sin converger):

```
propuesta repetida · propuesta stale · tests fallidos · worktree atascado ·
patch sin validación · diff demasiado grande · ficheros sensibles ·
governance tocado · dependencia nueva sin ADR · modelo caído · gate pendiente
```

Salidas graduadas: `silent → radar → ask → gate → block`. Con registro de feedback del
operador (piedra 6) desde el día uno.

## 10. Fase E — UI/UX Foundry: "sistema de decisión", no "vistas del sistema"

Superficies: **Mission Console** (centro mental, sustituye al Command Center), **Self-Build
Workbench**, **Mission Radar**, **Unified Inspector** (de cualquier elemento: por qué existe,
evidencia, soul/modelo, capability, policy, audit ref), **Receipt Panel** (qué pasó / por qué
importa / qué hizo Atlas / qué falta / qué decisión se necesita), **Failure Inbox**, **Human
Override Bar** (pause self-build / read-only / stop external models / stop memory writes /
quarantine / reject-and-remember-why — desde el principio, no al final).

Principios de diseño que sobreviven de la fase estética:
- **Surface Lifecycle Model** (L53927): superficies perennes / efímeras / contextuales — las
  pantallas se piensan todas, pero solo se exponen las que el momento o el sector necesita.
- **Pensamiento observable**: toda capa de razonamiento de Atlas debe poder inspeccionarse
  (enlaza con el Unified Inspector y el Merkle audit, no con animaciones).
- El LivingGraph puede quedarse, pero alimentado por misiones reales, no fixture.

## 11. Fase F — Benchmark

Rejugar ~10 misiones self-build históricas y medir: calidad de receipt, riesgo bien
clasificado, diff mínimo, tests relevantes, gate correcto, review adversarial útil.
Es lo que separa "se autoconstruye" de "se autoestropea con disciplina".

## 12. Criterio de éxito (cierre de Foundry v0)

Abrir Atlas y ver: "3 propuestas self-build relevantes — una lista para validar, una
atascada/repetida, una que toca zona sensible y requiere gate", y para cada una: misión,
patch, tests, riesgo, review adversarial, verificación, siguiente acción, botones
aprobar/rechazar/aparcar/pausar, y receipt al terminar.

## 13. Aparcado explícitamente (no desbloquea Foundry)

Sectores finales (gestoría/legal/TPV), móvil/watch, RAG masivo, cien modelos, cien souls,
UI generativa total, CRM/ERP propio, conectividad universal click-click. Documentados en el
export (L34587–38298, L53173+) para cuando toquen.

## 14. ADDENDUM (2ª pasada, barrido completo) — piezas que la 1ª destilación no recogió

### 14.1 La ruta dorada de autoconstrucción (L45286+, es EL producto interno)

```
Usuario pide mejora concreta de Atlas → Atlas inspecciona repo real → propone plan mínimo
→ worktree aislado → modifica ficheros → tests/mypy/build → muestra diff+riesgo+evidencia
→ humano aprueba/rechaza → aplica/commitea o aparca → actualiza memoria/grafo/auditoría
→ recibo verificable
```

Test E2E rojo que la define: `test_self_build_golden_route_requires_approval_and_receipt`
(falla si: clase interna directa, edición sin worktree, apply sin aprobación, sin diff
visible, sin tests observables, sin receipt, memoria silenciosa, daemon oculto).

### 14.2 Los 8 huecos reales (L45333, verificado contra repo por GPT con GitHub)

1. No hay ruta dorada única · 2. UI/UX de autoconstrucción sin cerrar · 3. F5/F6 son el
núcleo (F5→Dynamic Workflow Control Surface, F6→Coding+Research Workbench) · 4. El daemon
autónomo necesita superficie de control (Autobuild Console: registry, runs, owner, scope,
kill switch, pause/resume) · 5. Falta contrato de delegación (task spec, worker role,
allowed/forbidden files, budget, timeout, acceptance, verification, artifact, failure mode)
· 6. Memoria/grafo/auditoría fuera del ciclo (DecisionMemory, FailureMemory, PatternMemory,
CodeChangeMemory, GraphImpactRecord, ReplayReceipt) · 7. Falta el test E2E rojo · 8. Falta
"modo producto" (una única ruta interna).

### 14.3 Brief "Self-Construction Rescue Session v0.2" (L45472–45810)

7 misiones: checkpoint de realidad → auditoría forense (clasificar REAL/MOCK/STUB/DOC_ONLY/
LAB/DEAD/DANGEROUS/UNKNOWN con cita obligatoria) → product contract (16 estados visibles
usuario) → UI/UX spec (17 superficies) → test E2E rojo → plan mínimo 10 pasos → clasificación
de módulos → STOP para aprobación. Regla dura: "si la sesión produce otra pila de
arquitectura en vez de un test E2E rojo y un plan mínimo, la sesión ha fracasado".

### 14.4 Decisión de stack UI (L48277, definitiva)

**Ahora: React/Vite en `ui/atlas-shell` existente** (ya conectado al bridge, ya tiene
AutobuildLedger). Componentes diseñados como portables (AppShell, LeftRail, TopStatusBar,
LivingGraphSurface, ProposalCard, RightInspector, DiffPanel, GateLab, PipelineTimeline,
MemoryContextPanel, AuditTimeline). Después: Tauri para empaquetar. Final: Rust+Slint+wgpu
SOLO cuando UX y contratos estén cerrados. "React es el campo de pruebas donde se gana o se
pierde la UX."

### 14.5 Pantalla madre: Atlas Cognitive Reactor (L52529, con papers)

4 zonas: **Cognitive Reactor** centro (latido, foco, misión activa, rutas de atención,
agentes, formación de memoria, gates — "atención hecha visible", no grafo decorativo) ·
**Composer** abajo (chat persistente como base de mando, modos Ask/Plan/Propose/Apply
L48627) · **Inspector** derecha (por qué, evidencia, cambio, riesgo, tests, gate, diff,
memoria, siguientes pasos) · **Timeline/Audit Strip**. Regla central: **no enseñar el
cerebro bruto sino el Cognitive Trace** (intento, foco, plan resumido, agentes, acciones,
evidencia, validación, memoria candidata, recibo, acción humana). Cada estado se siente
distinto (investiga/planifica/codifica/valida/aprende/necesita-humano, L52596; catálogo
completo de 14 estados visuales en L17199–17433).

### 14.6 Gramática de eventos (L52710 — sin esto la UX viva es "visual dressing")

`intent.created, context.ingested, research.started, source.fetched, source.validated,
plan.generated, alternative.rejected, agent.spawned, tool.called, file.opened, file.patched,
test.started, test.passed, test.failed, gate.requested, gate.approved, gate.rejected,
memory.candidate_created, memory.committed, audit.receipt_written` — cada uno con
timestamp, actor, scope, confidence, risk, evidence_refs, ui_importance, reversible?,
human_action_required?.

### 14.7 Principios AX del SOTA (L51306, investigación UX de futuro)

Agent Experience además de UX · UI generativa (interfaces materializadas por contexto, +72%
preferencia humana vs chat puro) · Situation Awareness en vez de dashboard · trayectorias
visibles en vez de logs (SeaView) · auditabilidad nativa (Auditable Agents: 5 dimensiones,
~8.3ms overhead) · attention-directing (la UI lleva al punto donde el juicio humano importa).
Conceptos propios: Cognitive Heartbeat, Living Knowledge Field, Agent Trails, Persistent
Composer, Workbench Router, Context Vault, Gate Lab, Drift/Learning Monitor.

### 14.8 Otros materiales mapeados (con líneas, para no perderlos)

- Premortem 13 modos de fallo de Atlas OS v0 (L6505–6901) y auditoría premortem del proyecto
  completo (L39341+).
- 13+2 dossiers Research 01–15 del bloque ZIP (L22166–36520): Jarvis-likes, UI stack,
  Workflow Canvas n8n/LangGraph, External Thought Import, Liquid Software/Atlas Sheet,
  taxonomía de sectores, gestoría deep-dive, device mesh, seguridad agéntica, Presence
  Engine/Cognitive Physics, UI/UX pantalla-por-pantalla, política de asimilación,
  Integration Fabric/Connector Ladder, CRM/ERP nativo.
- Pantallas obligatorias 1–19 (L16034–16706) y anatomía fija + botones universales (L20380+).
- Surface Lifecycle Model: perennes/efímeras/contextuales (L53927).
- Cognitive Physics/estados visuales completos (L17199–17560) + zoom semántico.
- Souls: catálogo con roles + abogado del diablo (L61880–63076).
- Las imágenes de mockups de GPT: URLs firmadas caducadas (403 verificado) — NO recuperables;
  solo sobrevive el texto descriptivo.

## 15. Cuestiones abiertas para el operador

1. **Destino del fichero crudo**: 1.6MB en la raíz del repo. Propuesta: moverlo a
   `docs/archive/` (o fuera del repo) una vez validada esta destilación — decisión tuya, no
   lo he movido.
2. **Business Core (F15) bajo el criterio Foundry**: queda formalmente "producto/vertical" —
   ¿se congela su evolución hasta cerrar Foundry v0, o se mantiene en mantenimiento pasivo?
3. **Encaje con ADR-066/068**: esta destilación es la continuación natural de ADR-068. Si se
   acepta, probablemente merezca un ADR propio (Foundry como foco) en vez de quedarse en inbox.
