# PHASE_15_EXECUTION_PLAN — fundaciones del Product OS

Objetivo: base coherente y testeada para Integration Fabric + Easy Connection
Layer + Business Core + Adaptive Question Engine + Legacy Link + Policy/Gates.
NO producto completo; NO conectores reales con efectos; NO UX final.

Unidad de producto que todo debe servir:
`Objetivo → Sector → Datos → Liquid Workbench → Validación → Gate → Acción auditada → Memoria`.

## Pasos (cada uno termina con tests verdes + commit selectivo)

1. **Contratos** — 10 schemas estrictos en `schemas/` + espejos pydantic en
   `src/atlas/fabric/models.py` y `src/atlas/business/models.py` + paridad
   (patrón exacto de tests/test_os_event_schema.py).
   - connection_recipe, connector_pack, connector_health
   - capability, policy_rule
   - question_pack, onboarding_session
   - business_core, business_entity, entity_candidate
2. **Integration Fabric** (`src/atlas/fabric/`) —
   - `ladder.py`: los 12 peldaños ordenados por riesgo; computer-use = 11 de 12;
     API-first codificado como dato, no como comentario.
   - `recipes.py`/`packs.py`: carga+validación de fixtures, catálogo por categoría.
   - `concierge.py`: plan de conexión humano (ruta, dificultad, permisos, gates,
     pasos, qué hará/qué NO hará Atlas).
   - `registry.py`: perfiles de conector + hash de descriptor (anti rug-pull de
     tools) + estados de salud; eventos al OsEventStore.
   - `auth_broker.py`: SOLO `credential_reference` opaco; captura manual guiada
     como flujo declarado; almacenamiento real de secretos = BLOCKED_BY_DESIGN
     hasta ADR de vault (no fingir keyring).
   - `testing.py`: ConnectionTestRunner en modo mock/sandbox → eventos.
   - Discovery engine: stub honesto (rutas candidatas desde recipes; sin red).
3. **Policy/Security** (`src/atlas/fabric/policy.py` + fixtures/security/) —
   - Taxonomía de capacidades (≥22 del prompt) con risk + data_class.
   - PolicyEngine determinista fail-closed: invariantes DUROS en código
     (indistinguibles de fixtures borradas): whatsapp_personal send → deny;
     model.cloud_call+sensitive → deny sin aprobación humana; erp.accounting.write,
     official.submit, certificate.use → gate SIEMPRE; computer_use.execute →
     gate + jamás ruta primera; capability desconocida → deny.
   - Source-trust: acciones con provenance de contenido no confiable → deny
     (contratación determinista, no heurística LLM).
   - Corpus de fixtures de ataque del pack (inyección, tool poisoning, memory
     poisoning) copiado y usado como regresión de las detecciones deterministas
     que sí existen (rug-pull por hash, provenance, requires_review).
4. **Business Core** (`src/atlas/business/`) —
   - `entities.py`: 22 kinds; `core_engine.py`: draft-first, persistencia bajo
     $ATLAS_HOME/business_core/, activación SOLO con aprobación humana explícita
     (evento gate + estado pending_activation si falta).
   - CRM/ERP como vistas moduladas del mismo core (no dos sistemas).
   - `questions.py`: packs por sector (5), sesión start/answer/preview con rama
     "no_se", interpretación mostrada y confirmable, mapeo respuestas→entidades/
     capacidades/workbenches/connector-pack.
   - `extract.py`: EntityCandidateExtractor determinista sobre fixtures (gmail→
     contactos candidatos; facturas→clientes/proveedores/productos) con
     confidence + requires_review; nada se promociona solo.
   - `legacy.py`: canonicidad explícita obligatoria; mirror read-only default;
     sync off default; propuesta de migración como draft.
5. **API + CLI** — `src/atlas/api/product_routes.py` registrado en `create_app`;
   grupos `atlas connections` y `atlas business`; guard anti-Orchestrator
   extendido a fabric/ y business/.
6. **Cierre** — ADR-060 (Integration Fabric + Easy Connection + policy) y
   ADR-061 (Business Core draft-first + Question Engine + canonicidad);
   UI_QUALITY_GATE doc + checklist máquina; README arnés en ui/atlas-shell;
   docs de cierre phase15 (COMPLETION_REPORT, WHAT_WAS[_NOT]_IMPLEMENTED,
   NEW_GAPS_FOUND ≥10 clasificados, RECOMMENDED_PHASE_16, IMPROVEMENT_PROPOSALS);
   actualización de CONTINUATION_STATE/NEXT_AI_INSTRUCTIONS/TESTING_STATUS/
   KNOWN_RISKS/OPEN_QUESTIONS; INDEX.yaml regenerado; suite completa.

## Qué queda explícitamente FUERA (a Fase 16+, sin fingir)

- Conectores reales (Gmail/Odoo/Claude en vivo), OAuth real, webhooks reales.
- Vault de secretos (solo referencias opacas en Fase 15).
- Sector Registry/Objective Registry completos, Presence Engine, Atlas Sheet,
  Liquid App Runtime, gestoría vertical completa, Slint/wgpu spike.
- Ingesta de candidatos al índice canónico de memoria (sigue en os_import_v1).
- UI final; pantallas de arnés solo si sobra presupuesto de sesión.

## Criterios de éxito medibles

- `pytest tests/test_os_*.py` verde (39 previos + ~60 nuevos), mypy strict limpio
  en api/events/fabric/business, `npm run build` intacto.
- Defaults seguros PROBADOS: gmail send bloqueado por defecto, whatsapp personal
  send imposible, activación de core exige aprobación, computer-use nunca primera
  ruta, cloud+sensible denegado.
- Todos los fixtures marcados demo/simulated; cero secretos.
