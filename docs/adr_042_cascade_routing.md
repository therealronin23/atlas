# ADR-042 — Cascada con routing (Capa 2)

Fecha: 2026-06-12 · Estado: aceptado · Contexto: `docs/direction_2026-06-12_construir_hacia_arriba.md`, ADR-041

## Decisión

`CascadeRouter` en `src/atlas/router/cascade.py`: clasifica cada tarea por
dificultad (estimador inyectable, default rule-based) y la asigna al
producer más barato con capability suficiente. Todo artefacto producido
pasa por el seam de la capa 1 (`UniversalVerifier`); FAIL o UNKNOWN
escalan al siguiente producer. Agotada la cascada se devuelve el último
veredicto real — nunca un PASS fingido.

Métrica de éxito de la capa: **coste por resultado verificado**
(`CostLedger`, unidades ordinales de `CostTier`).

## Decisiones y porqués

| Decisión | Elegida | Porqué |
|---|---|---|
| Ubicación | `router/cascade.py` | es routing; capa distinta del Classifier de seguridad, fichero distinto |
| Relación con Classifier/RoutingLevel | ortogonal: seguridad decide *si* y *dónde*; la cascada *quién produce*. Cinturón: spec con `governance_blocked` lanza ValueError | fusionarlos acoplaría governance a coste |
| Relación con Decider | la cascada no consulta al Decider por intento | el decider asigna políticas/envelopes, no acciones; aprobar cada escalada = HITL con otro nombre |
| Coste frontier | `CostTier.FRONTIER=6` añadido en `core/verify.py` (aditivo; `MODEL` queda para L0/L1) | un solo eje ordinal mantiene la regla asimétrica comparable entre capas |
| UNKNOWN | escala igual que FAIL; al final de la cascada se devuelve tal cual | unknown > mentir. Además escalar sube `producer_cost` y puede habilitar verificadores (regla asimétrica): cascada y regla cooperan |
| Dificultad | `DifficultyEstimator` Protocol + default rule-based; ante señales mixtas gana HARD | el SLMClassifier podrá entrar como implementación después; LLM en el path crítico hoy = red y no testeable barato |
| Producer mentiroso | el router corrige `artifact.producer_cost` al coste real del producer | un artifact que se declara más barato burlaría la regla asimétrica |
| Orchestrator | NO cableado aquí; usable como librería | el cableado al tick vivo merece sesión propia con el servicio parado |

## Tipos

- `Difficulty`: MECHANICAL < STANDARD < HARD.
- `Producer` (Protocol): `producer_id`, `cost`, `capability`, `produce(spec) -> Artifact`.
- `CascadeResult`: artefacto, `Evidence`, intentos, escaladas; `to_dict()` JSON-serializable (Merkle-ready).
- `InferenceProducer`: adaptador InferenceHub→cascada (L0/L1→MODEL, L2→FRONTIER); hub inyectado, fake en tests.

## Consumidores previstos

- **Capa 3 (enjambre)**: cada worker es un producer más; el blackboard
  consume `CascadeResult.to_dict()`.
- **Capa 4 (LessonStore)**: los intentos fallidos de la cascada son la
  materia prima de las lecciones tipadas.
