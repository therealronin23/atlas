# ADR-069 — Mission Layer v0: la unidad semántica de autoconstrucción (Foundry)

- Estado: aceptado (2026-07-15)
- Contexto: el operador destiló su conversación de diseño completa (export
  "Diseño UI Atlas.md", 65.640 líneas → `docs/inbox/
  atlas_foundry_v0_destilado_2026-07-15.md`) y pidió construir. La conclusión
  del export coincide con ADR-068: lo que desbloquea a Atlas es que se
  construya mejor a sí mismo ("Atlas Foundry"), y la pieza que falta no es
  otra feature sino la **unidad semántica** que une propuestas, eventos,
  gates, tests, riesgo y decisión: la **Misión**. El spec de alcance que
  ADR-068 exigía antes de escribir UI de F5/F6 existe ahora:
  `docs/design/mission_layer_self_construction_spec.md`.

## Decisión

1. **Contratos primero** (Foundry Fase A, recortada): 3 schemas nuevos junto
   a los 26 existentes — `mission.schema.json` (con $defs EvidenceBundle,
   NextAction, GateReference, ModelUse, SoulInvocation),
   `mission_receipt.schema.json` (qué pasó / por qué importa / qué hizo
   Atlas / qué falta / qué decisión se necesita + `verifiable` honesto) y
   `soul_manifest.schema.json` (solo el contrato; ninguna soul se ejecuta
   todavía — la primera será devil_advocate).
2. **Proyección, no invención** (Fase B): `src/atlas/api/missions.py` son
   funciones PURAS read-only sobre `proposals.json` (ledger real de
   ColdUpdateManager, ADR-025). Jamás se instancia ColdUpdateManager desde
   el bridge (su `__init__` escribe). El adapter valida contra el schema
   (test que lo prueba), no es decoración.
3. **Radar proactivo determinista** (primer corte de Fase D): 4 detectores
   sin LLM — repeated_proposal, stale_proposal, validation_missing,
   gate_pending — con severidades graduadas `silent<radar<ask<gate`. El
   radar SEÑALA, nunca actúa. Verificado en vivo el día del ADR: cazó la
   propuesta repetida real del vault Obsidian (×15, candidata de
   investigación nombrada en ADR-068 Act. 2) y 3 bucles de bumps de
   dependencias (cryptography ×8, litellm ×8, fastapi ×6).
4. **Endpoints aditivos read-only**: `GET /missions`, `GET /missions/{id}`
   (misión + receipt), `GET /missions/radar`. `/missions/radar` registrado
   antes que `/missions/{id}` (el path param no debe capturar "radar").
5. **Mission Console** como centro mental del shell (el export lo pide
   explícitamente: "sustituir el Command Center como centro mental"): nueva
   vista por defecto en `ui/atlas-shell` — radar strip con atención
   dirigida (decisiones y bucles individuales; mantenimiento agregado en
   tarjetas-resumen), lista con "esperan decisión humana" primero, e
   inspector con el Cognitive Trace + receipt como documento. React/Vite
   actual por decisión explícita del export (L48277): React es el campo de
   pruebas; Tauri/Slint/wgpu solo cuando UX y contratos estén cerrados.
6. **Test E2E rojo de la ruta dorada**:
   `tests/acceptance/test_self_construction_golden_route.py`, marcado
   `xfail(strict=True)` — el contrato en código de lo que falta (petición
   pública → plan → worktree → diff → aprobación → apply/park → receipt).
   `strict=True` obliga a quitar el marcador el día que la ruta cierre.
   **CERRADO el mismo día**: `GoldenRoute`
   (`src/atlas/missions/golden_route.py`) envuelve ColdUpdateManager —
   petición determinista (v0 doc-only), aprobación humana en Merkle antes
   de actuar (PermissionError sin ella), receipt + audit_ref. El marcador
   xfail se retiró y el E2E corre verde sobre repo fixture. El bridge
   sigue sin importar `atlas.missions` (ADR-058 intacto).

## Lo que esto NO es

- No es la ruta dorada cerrada: las misiones se VEN y el radar SEÑALA, pero
  pedir/aprobar/aplicar sigue siendo CLI humano (`atlas update …`).
- No ejecuta souls, no enruta modelos (Model Fabric pendiente), no escribe
  memoria ni eventos nuevos.
- No supersede ADR-058 (bridge read-only, sin Orchestrator) ni ADR-066/068:
  los implementa en la dirección reencuadrada.

## Evidencia (día del ADR)

- 24 tests nuevos en `tests/test_os_missions.py`; 60 pasan en el paquete
  OS afectado + 1 xfail deliberado; mypy --strict limpio en los 2 módulos
  tocados; `tsc --noEmit` + `vite build` limpios.
- Verificado en navegador real contra bridge real: 237 misiones reales,
  radar con 12 tarjetas (agregación de 56 hallazgos crudos), receipt de 5
  preguntas con sello "SIN VALIDACIÓN" honesto, comando siguiente real
  mostrado y nunca ejecutado.
