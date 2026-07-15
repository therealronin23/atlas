# Mission Layer v0 + Dynamic Workflow Control Surface — spec de alcance y plan

- Fecha: 2026-07-15
- Estado: en construcción (esta sesión)
- Cumple: el prerequisito de ADR-068 ("antes de escribir código de UI para
  cualquiera de las dos [F5/F6], hace falta un spec de alcance real: qué
  pantallas, qué estados, qué endpoints"). Este documento ES ese spec para
  la Dynamic Workflow Control Surface, reencuadrada como Mission Layer.
- Fuente: `docs/inbox/atlas_foundry_v0_destilado_2026-07-15.md` (destilación
  del export "Diseño UI Atlas.md", 65.640 líneas) + estado real del repo.

## Tesis (una línea)

Convertir las 237 propuestas REALES del ledger de ColdUpdate en **misiones**
observables y gobernables, con radar proactivo y recibo humano — el primer
circuito del "Atlas construyendo Atlas" (Foundry v0), sin tocar el carácter
read-only del bridge.

## Qué se construye (esta sesión)

### 1. Contratos (Foundry Fase A, recortada a lo que la ruta necesita)

Tres schemas nuevos junto a los 26 existentes, misma convención
(JSON Schema 2020-12, `$id` atlas.local, títulos `AtlasX`):

- `schemas/mission.schema.json` — Mission con `$defs` embebidos:
  EvidenceBundle, GateReference, ModelUse, SoulInvocation. Campos núcleo:
  `mission_id` (`msn_*`), `intent`, `state` (16 estados visibles del
  product contract del export L45597), `risk`, `origin`, `artifacts`
  (ficheros tocados), `validation`, `next_action`, `human_action_required`,
  `receipt_ref`, `source` (`cold_update_proposal` v0).
- `schemas/mission_receipt.schema.json` — el recibo humano accionable:
  qué pasó / por qué importa / qué hizo Atlas / qué falta / qué decisión
  se necesita + `evidence_refs` + `verifiable` (rutas reales comprobables).
- `schemas/soul_manifest.schema.json` — contrato de soul ejecutable
  (system_prompt_ref, skills, tools permitidas/prohibidas, modelo
  preferente, política de privacidad, schema de salida, memoria permitida,
  criterio de evaluación). Solo el CONTRATO en v0; las souls corren en
  fases posteriores (Devil's Advocate primera).

### 2. Adapter + Radar (Foundry Fase B + primer detector de Fase D)

`src/atlas/api/missions.py` — funciones puras read-only (patrón
`_self_build_summary`: leer `proposals.json`, JAMÁS instanciar
`ColdUpdateManager`):

- `proposal_to_mission(p) -> dict` — mapeo fiel: `validation` →
  EvidenceBundle, `status` → estado de misión, `next_action` (hint CLI ya
  existente) → `Mission.next_action`, ficheros del patch → `artifacts`.
- `mission_receipt(p) -> dict` — receipt v0 generado de datos reales (sin
  LLM: plantilla determinista con evidencia; honesto sobre lo que falta).
- Radar con 4 detectores deterministas (salida `silent|radar|ask|gate`):
  - `RepeatedProposalDetector` — mismo intent re-propuesto N≥3 veces sin
    converger (caza el caso real conocido: "Cablear el vault Obsidian…"
    repetida cada 1-2h, nombrada en ADR-068 Actualización 2).
  - `StaleProposalDetector` — `proposed`/`validated` sin update > 48h.
  - `ValidationMissingDetector` — `proposed` con patch pero sin validation.
  - `GatePendingDetector` — `validated` esperando `approve` humano.

### 3. Endpoints bridge (read-only, aditivos)

- `GET /missions?limit=` — lista de misiones (proposals adaptadas) +
  agregados por estado/riesgo/origen.
- `GET /missions/{id}` — misión completa + receipt + files_touched +
  next_action.
- `GET /missions/radar` — hallazgos de los 4 detectores con severidad.

### 4. UI — Mission Console (primera superficie de la Dynamic Workflow
Control Surface completa)

Nueva vista "⟁ Mission Console" en `ui/atlas-shell` (React/Vite existente —
decisión de stack del export L48277: React AHORA, nativo después). Zonas
(pantalla madre del export, adaptada al design system HUD ya existente):

- **Radar strip** (arriba): cards de hallazgos del radar con severidad —
  atención dirigida, no mar de datos (principio attention-directing).
- **Mission list** (izquierda): misiones activas primero (proposed/
  validated/approved), luego historial; riesgo y estado con semántica
  visual distinta (no todo cian).
- **Mission Inspector** (derecha): el Cognitive Trace de la misión
  seleccionada — intent, estado, riesgo, evidencia real (pytest/mypy),
  ficheros tocados, siguiente acción humana (comando CLI real, nunca
  ejecutado desde la UI), receipt.
- **Receipt panel**: qué pasó / por qué importa / qué falta / qué decisión
  se necesita.

Estados de datos: REAL (bridge vivo) / BLOCKED_BY_MISSING_DEPENDENCY /
sin bridge (banner existente). La UI no inventa nada (norma del shell).

### 5. Test E2E rojo (Mission 4 del rescue brief)

`tests/acceptance/test_self_construction_golden_route.py` — describe la
ruta dorada completa (petición → plan → worktree → diff → tests →
aprobación → apply/park → receipt → memoria/grafo/audit) y está marcado
`xfail(strict=False)` con razón explícita: la ruta no está cerrada. Es el
contrato de qué falta, en código, no en prosa. Se irá poniendo verde por
pasos en sesiones siguientes.

## Qué NO se construye (esta sesión)

Souls ejecutándose (solo su contrato) · Model Fabric routing · escritura
de misiones (el bridge sigue read-only; aplicar/aprobar sigue siendo CLI
humano) · Coding+Research Workbench (F6, la otra mitad — sesión propia) ·
verticales de negocio · empaquetado nativo.

## Criterio de éxito de la sesión

Abrir el shell y ver: misiones reales con estado/riesgo/evidencia, el
radar señalando la propuesta repetida REAL del vault Obsidian, receipt
legible por humano con siguiente acción, tests OS verdes + mypy limpio +
tsc/vite build limpio, y el test E2E rojo documentando lo que falta.

## Orden de implementación

1. Schemas (TDD: test de carga primero) → 2. missions.py (adapter+radar,
tests) → 3. endpoints (tests API) → 4. UI Mission Console → 5. verificación
en navegador real contra bridge real → 6. test E2E rojo → 7. ledger +
memoria + ADR-069 + commit.
