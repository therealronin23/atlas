# Artefactos archivados — sesión de VS Code (2026-06-17)

Estos archivos los generó una sesión de asistente en VS Code que auditó el proyecto.
Se **archivan, no se borran** (reversible). Razón: divergen del trabajo canónico y
violan reglas del proyecto.

## Por qué se archivaron

- **Colisión de nombres con significado opuesto.** Definen `Membrane` y `OsmosisFilter`
  como escáner de malware de payloads antes del Orchestrator. El significado canónico es
  otro: *admission gate* (compuerta de admisión de conocimiento) e *in-path verifiable AI
  compliance filter*. Ver `docs/membrana/OSM-000_membrana.md` (glosario + autoridad).
- **Cita alucinada.** `osmosis_filter_design.md` afirma "implementa la lógica descrita en
  ADR-054". ADR-054 menciona "osmosis"/"membrana" **cero veces**. Referencia inventada.
- **Código roto y sin usar** (`code/membrane.py`, `code/antivirus.py`): importan
  `..decider` (no existe; es `core.decider`) y `MerkleLogger` desde `transparency.merkle_tree`
  (está en `logging/`); llaman `decider.evaluate(...)` (la API real es
  `decide(action, sanctioned_intent, context)`). No los importaba nada.
- **Violan la regla de nombres** de `AGENTS.md` (nombres técnicos en código; los narrativos
  solo en docs históricos).

## Qué los supersede

- Concepto y diseño canónicos: `docs/membrana/` (OSM-000..039) y
  `docs/paper_subject_enforced_completeness.md`.

Si algo de aquí resulta útil más adelante, se reintroduce pasando la compuerta de la
membrana (OSM-000), con nombre técnico y verificación.
