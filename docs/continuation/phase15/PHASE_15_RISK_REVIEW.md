# PHASE_15_RISK_REVIEW — riesgos de esta fase y mitigaciones

| # | Riesgo | Mitigación en Fase 15 |
| --- | --- | --- |
| P15-R1 | Clonar CRM/ERP/n8n en vez de núcleo modular | Business Core = un solo store de entidades draft-first; CRM/ERP son vistas; sin workflow engine nuevo |
| P15-R2 | Seguridad "de fixture": borrar un JSON relaja invariantes | Invariantes duros replicados en código (PolicyEngine) + tests que borran/ignoran el fixture y comprueban que el deny persiste |
| P15-R3 | Fingir detección de prompt-injection con heurísticas débiles | Solo detecciones deterministas (hash rug-pull, provenance, requires_review); el corpus del pack queda como regresión de POLÍTICA, no como "detector IA" |
| P15-R4 | Secretos: tentación de guardar API keys para "probar" | AuthBroker solo emite/valida referencias opacas; test que rechaza material que parezca secreto (longitud/formato) en recipes y store |
| P15-R5 | Activación silenciosa del Business Core | `activate()` sin aprobación humana → estado pending_activation + evento waiting_user; test explícito; sin flag de bypass |
| P15-R6 | Duplicar el evaluador de permisos (v1 gates vs PolicyEngine) | PolicyEngine ENVUELVE los gates existentes (mismo fixture gates.json) y añade capability/data_class; /permissions/evaluate v1 se mantiene, nueva superficie usa PolicyEngine; convergencia documentada como gap si duele |
| P15-R7 | Explosión de alcance (80 schemas del pack) | Solo 10 schemas núcleo esta fase; el resto mapeado en NEW_GAPS_FOUND/PHASE_16 |
| P15-R8 | Romper suite/mypy existentes (3049 tests) | Módulos nuevos aislados; server.py/cli.py solo aditivo; suite completa antes del cierre |
| P15-R9 | Committear basura del operador | Nunca `git add -A`; add por ruta explícita; dirty paths del operador intactos |
| P15-R10 | Doble Orchestrator vía módulos nuevos | Guard estático extendido a src/atlas/{fabric,business}; los motores solo reciben OsEventStore |
| P15-R11 | Datos demo confundibles con reales | Todo fixture con `"demo": true` y/o ids *_demo; eventos emitidos con simulated=true salvo persistencia local real |
| P15-R12 | WhatsApp/gestoría: implicaciones legales/ToS | Recipes declaran legal_notes; whatsapp_personal = import/draft/review only con deny duro; sin automatización de portales oficiales (browser assist = fixture demo bloqueado) |
