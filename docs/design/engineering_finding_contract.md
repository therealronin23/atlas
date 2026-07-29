# EngineeringFinding v1 — contrato de proyección interna

**Autoridad.** ADR-078 y
`docs/superpowers/specs/2026-07-28-atlas-lineage-workbench-symbiosis-design.md`
§6.1. Este documento describe el primer subcorte de `ADC-WO-108`; no sustituye
los tipos especializados ni autoriza efectos.

## Current (2026-07-29)

`schemas/engineering_finding.schema.json` y
`atlas.engineering.findings.EngineeringFinding` definen un contrato v1
serializable con identidad, revisión, fuente, severidad, lifecycle, ubicación,
evidencia, reproducción, acción sugerida y referencia opaca de patch.

`EngineeringFindingStore` recibe un path de runtime del llamador y conserva un
journal JSONL append-only. Repetir la misma `dedupe_key` devuelve el finding
original sin crear una alerta nueva; toda transición de estado conserva el
snapshot anterior y exige una razón. El store no recibe un root de repositorio
ni abre `patch_ref`, por lo que no puede aplicar un patch estructuralmente.

`from_self_audit_finding()` proyecta el tipo existente `SelfAuditFinding` sin
modificarlo. Sólo la severidad `critical` de self-audit se normaliza a
`BLOCKING`; el routing, Merkle y cualquier elevación posterior pertenecen a un
coordinador y a Policy, no al adaptador.

`EngineeringReviewCoordinator` ya compone adapters en orden determinista. Su
adaptador `UniversalVerifierReviewAdapter` reutiliza el seam `UniversalVerifier`
para un diff acotado: `PASS` no crea finding, `FAIL` se proyecta con evidencia y
una excepción de reviewer queda como `UNKNOWN`. Antes de persistir, el
coordinador verifica `run_id`, Task, repositorio, revisiones y source del
finding; un adapter que intenta cruzar ese contexto queda `UNKNOWN` y no escribe
el journal.

`EngineeringDiagnosticCoordinator` recibe un `ValidationReport` ya capturado y
un `RootCauseClassifier` inyectado: no vuelve a ejecutar el comando ni crea un
worktree. Normaliza el vocabulario de diagnóstico de ADR-078, conserva una
excepción o clasificación no soportada como `UNKNOWN`, filtra paths absolutos o
con traversal y no copia salida cruda ni el texto libre del clasificador al
journal. La clasificación y el uso de modelo quedan como evidencia estructurada,
no sólo texto. El llamador conserva la política que decide si el
clasificador puede usar un modelo; el coordinador no configura proveedores.

`EngineeringEventPublisher` es un bridge opt-in: antes de publicar
`engineering.finding` o `engineering.review_completed` en el `EventBus`,
escribe un receipt en Merkle. Su payload se limita a identidad, revisión,
estado, severidad, conteos y riesgo; no lleva diff, detalle, evidencia, patch o
recomendación. Si Merkle falla, el evento no se publica. El bridge no crea Task,
no contacta al Orchestrator y no convierte el hash incluido como metadata en una
referencia de auditoría verificable para la UI.

`EngineeringReviewBaselineStore` conserva una revisión base sólo cuando un
llamador presenta un `PASS` con al menos un reviewer y una `acceptance_ref`
opaca. El journal append-only captura la revisión aceptada y un snapshot mínimo
del lifecycle de findings, pero no verifica la referencia, no abre Git, no
calcula ancestry/diff ni altera la resolución de un finding posterior. La
selección resultante obliga al llamador a verificar ancestry antes de construir
el delta incremental.

## Boundary

Un finding es una observación con procedencia. No es una prueba automática, una
propuesta aprobada, un permiso ni un efecto. Sus estados son `OPEN`,
`ACKNOWLEDGED`, `FIX_PROPOSED`, `RESOLVED`, `DISMISSED` y `BLOCKED`; la
transición persistida no ejecuta ninguna acción ni sustituye los gates de
aprobación.

Los campos requeridos, incluidos los que todavía no se conocen, aparecen como
valor explícito o `null`. Así un cliente no puede convertir por omisión la
ausencia de `task_id`, SHA o patch en un hecho positivo.

## Transition

El siguiente subcorte de `ADC-WO-108` añade deduplicación incremental sobre la
última revisión aceptada, cálculo del delta tras verificar ancestry y reproducción
aislada con hipótesis de grafo/historial/memoria. El wiring de eventos Merkle, routing hacia Orchestrator,
producción y validación de correcciones y una proyección read-only esperan sus
contratos y la frontera durable Mission/Task; no se declaran implementados por este
contrato.

## Rollback

Desconectar el futuro coordinador o sus llamadores deja intactos los
verificadores especializados. El journal existente permanece como evidencia
append-only; no se reescribe ni se convierte en autorización de patch.
