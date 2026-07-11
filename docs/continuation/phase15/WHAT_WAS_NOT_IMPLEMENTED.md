# WHAT_WAS_NOT_IMPLEMENTED — Fase 15 (honesto, no oculta huecos)

Del prompt/pack, explícitamente diferido (documentado en
PHASE_15_EXECUTION_PLAN.md desde el inicio, no descubierto tarde):

- **Conectores reales**: Gmail/Odoo/Claude/WhatsApp Business en
  producción. Todo sigue en mock/sandbox.
- **Vault de secretos propio**: AuthBroker usa referencias `env:VAR`; no
  hay backend de almacenamiento cifrado dedicado.
- **Sector Registry / Objective Registry completos**: solo los 5 sectores
  con question pack + connector pack; el pack lista 22 sectores totales.
- **Gestoría vertical completa** (Atlas Sheet, Document Review, Submission
  Ceremony, Audit Result): solo el question pack + connector pack de
  gestoría; las pantallas y el motor fiscal específico no existen.
- **Presence Engine / Cognitive Physics**: fuera de alcance de Fase 15
  (pertenece a la superficie nativa futura, no al backend).
- **Liquid App Runtime / generación de workbenches líquidos real**: los
  `resulting_workbenches` de las preguntas son strings identificadores;
  no hay motor que genere una superficie a partir de ellos.
- **Discovery de red real** (`ConnectorDiscoveryEngine.discover` para
  targets desconocidos): solo sugiere la escalera genérica, no investiga.
- **Enlace real al motor de gates de `governance/`**: `gate_id` en
  `BusinessCore.activation` y en `PolicyDecision` son identificadores
  descriptivos; no hay una ceremonia de aprobación conectada al sistema de
  gates general del repo (que sí existe para otras superficies).
- **Ingesta de candidatos promovidos al índice canónico de memoria**: un
  `BusinessEntity` promovido queda en `$ATLAS_HOME/business_core/`, no se
  escribe automáticamente en el índice de memoria (mismo gap ya conocido
  para `os_import_v1`, ver memoria `atlas-os-foundation-2026-07-10`).
- **UI de producto (nativa o cualquier superficie pulida)**: el shell
  React sigue siendo arnés; no se construyó ninguna pantalla de Business
  Core/Connection Store en la UI esta fase (presupuesto de sesión fue a
  backend/contratos).
