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

## Componentes NOMBRADOS en el prompt maestro que NO existen como clase

(Añadido tras auditoría 2026-07-11 — antes esta doc callaba estos, lo que
se leía como si estuviera todo. Honestidad: no están.)

**MODULE 1 — Integration Fabric**, nombrados pero inexistentes como código:
- `APISpecImporter`, `WebhookManager`, `MCPGateway profile layer` — **no
  existen en ninguna forma**. Genuinamente ausentes → Fase 16.
- Capas de perfil por tipo de conector (`DatabaseConnector`,
  `FileImportExport`, `BrowserAssist`, `DesktopAutomation`, `ComputerUse`) —
  **realizadas como DATOS, no como clases**: cada tipo está representado por
  una receta (`local_csv_folder` = database_file, `legacy_desktop_app` =
  desktop_automation/computer_use, etc.) y su comportamiento lo gobiernan la
  Connection Ladder + PolicyEngine. Decisión de diseño (receta = perfil como
  dato), no omisión — pero no estaba documentada como tal.
- `ConnectorCapabilityProfile` — realizado como `CapabilitySpec` +
  `fabric/capabilities.py` (catálogo), no como clase con ese nombre.

**MODULE 3 — Business Core**, nombrados pero inexistentes como clase:
- `CRMCoreEngine`, `ERPCoreEngine` — **no existen como motores separados**;
  CRM/ERP son vistas (`CRM_KINDS`/`ERP_KINDS` en `entities.py`, ahora
  enforced por `modules.crm/erp`) sobre un único `BusinessCoreEngine`.
  Decisión de diseño consciente (un store modular, no dos ERPs), coherente
  con ADR-061; pero eran nombres explícitos del prompt.
- `BusinessModelBuilder` — **no existe**; su función (proponer estructura
  desde onboarding) la reparten `QuestionEngine.build_preview` +
  `EntityCandidateExtractor`. Sin una clase orquestadora → candidata Fase 16.
- `CanonicalityEngine` — realizado como funciones en `legacy.py`
  (`canonicality_for_link`), no como clase/motor.
- `BusinessCoreActivationGate` — realizado como la lógica
  `request_activation`/`approve_activation` embebida en `BusinessCoreEngine`,
  no como clase Gate separada (ver gap #3: falta enlazar a un Gate Engine
  real de governance/).
