# ADR-048 — VerifiedProducer: el productor como lazo cerrado

Fecha: 2026-06-13 · Estado: **en construcción** (fases A-B hechas) · Contexto:
ADR-041/042/044/045/046, ADR-047 (panel adversarial).

## Decisión

`produce_diff` no es "LLM→diff y reza". Es un lazo (`core/verified_producer.py`)
cuyo **juez es evidencia barata (capa 1), no la opinión del modelo**:

```
estimar → ground → [producir → verificar → (retar) → reflexionar]* → aprender
 (c2)      (c4)       (prod)     (c1)       (047)      (feedback)      (c4)
```

Lo que lo hace único: el crítico del lazo es un verificador *más barato que el
productor* (verificación asimétrica metida dentro de la generación), no otra
llamada LLM que se auto-engaña. Solo es construible porque la pila de
verificación se construyó primero.

## Piezas y decisiones

| # | Decisión | Elegida | Porqué |
|---|---|---|---|
| 1 | Forma | lazo, no función | el juez es evidencia, no auto-opinión |
| 2 | Productores | ambos siempre: determinista-arnés (barato) + LLM-potenciador (escala) | el arnés acota+comprueba, el LLM evoluciona dentro |
| 3 | Crítico pre-emisión | UniversalVerifier antes de emitir | nada sube sin verificación |
| 4 | Reto | `AdversarialPanel` con **gating** (solo irreversible/alto-riesgo/difícil) y **diversidad** obligatoria (proveedores distintos o UNKNOWN) | convocar modelos para un typo es absurdo; un panel del mismo modelo es opinión ×N |
| 5 | Reflexión | la evidencia REAL del fallo vuelve como contexto, se escala de productor | anclar a verdad-terreno, no a otro LLM |
| 6 | Grounding+aprendizaje | carga lecciones (avoid_pattern=restricción); el par fallo→éxito se ofrece como lección **candidata** | ventaja compuesta sin auto-envenenamiento |
| 7 | Seguridad | `budget_units` corta el lazo; nada se aplica (sube por blackboard→decider) | un lazo reflexivo sin tope quema cómputo |

## Estado de construcción

- **Fase A — `AdversarialPanel`** (commit 131784d): hecho. Gating + diversidad,
  revisores inyectados, fakes en tests.
- **Fase B — lazo `VerifiedProducer`** (commit 824634f): hecho. Compone todo,
  inyectado, sin ejecución real. 11 tests.
- **Fase C — `DeterministicProducer` (arnés)** + primer transform real (AST):
  pendiente.
- **Fase D — `LLMProducer`** (envuelve InferenceProducer de capa 2): pendiente.
- **Fase E — `RepoMaintenanceScout`** (fuente de tareas, dedup contra
  propuestas abiertas): pendiente.
- **Fase F — integración** (`WorktreeWorker.produce_diff = VerifiedProducer` →
  blackboard → reconciler → ColdUpdate, auto-apply OFF): pendiente.

## Disciplinas heredadas (de la sesión)

- Lecciones auto-generadas nacen **candidatas** (tier de baja confianza), no
  evangelio — anti-auto-envenenamiento.
- El "arnés" no es magia nueva: es componer los verificadores baratos
  existentes (UnifiedDiffVerifier + ASTGuard + sandbox) como gates obligatorios.
- El scout debe deduplicar contra propuestas abiertas (evitar pila de
  duplicados, como los 365 worktrees).
