# ADR-044 — LessonStore (Capa 4)

Fecha: 2026-06-13 · Estado: aceptado (núcleo) · Contexto:
`docs/roadmap_mythos_2026-06-13.md`, `docs/audit_postmortem_2026-06-13.md`,
ADR-041, ADR-039 (self-maintenance).

## Decisión

`core/lesson_store.py`: una `Lesson` es un artefacto **duro** — heurística de
detección + patrón a evitar + una `Evidence` (tipo de capa 1) que prueba que la
lección es real. Ley de entrada (`LessonStore.add`): **sin `Evidence` con
verdict PASS, no entra**. Esa precondición de tipo es el antídoto contra
alimentarse de basura.

Verificador polimórfico por procedencia, siempre produciendo `Evidence`:

- `INTERNAL_FAILURE` → **prove-it**: el test de regresión falla contra el código
  de antes del fix y pasa contra el actual (rojo-antes/verde-ahora). Coste SUITE.
- `EXTERNAL_SOURCE` → **corroboración**: ≥1 fuente autoritativa corrobora (el
  gate fail-closed del MaintenanceAnalyst, que excluye tokens genéricos). Coste
  STATIC.

## Decisiones y porqués

| # | Decisión | Elegida | Porqué |
|---|---|---|---|
| 1 | Relación con ErrorRegistry | híbrido: ErrorRegistry queda blando (runtime), Lesson es el nivel duro; puente de promoción `FailureEntry → Lesson` + back-link `promoted_to_lesson_id` | densidad sin acoplar; dos niveles navegables (fallo observado → lección verificada) |
| 2 | Criterio de verificación | prove-it (interna) / corroboración (externa), ambos → `Evidence` capa 1 | "sin test, no hay lección"; unifica capa 4 con el lenguaje de capa 1 |
| 3 | El verificador no corre nada | recibe `ProveItResult`/corroboración ya capturados | testeable sin red ni subprocesos; el runner real se inyecta |
| 4 | Antídoto contra basura | ley de tipo en `add()` | el usuario pidió "que no se alimente de basura"; es una precondición, no un deseo |
| 5 | **Alcance de esta iteración** | **solo store + verificador; consumidores diferidos** | el audit 2026-06-13 mostró que codegen (consumidor) no es alcanzable hasta la capa 3; cablear consumidores ahora compondría el gap declarado-vs-real |
| 6 | Externa reusa scouts | la ingesta externa cablea la salida corroborada de CommunityScout/dep_scout/Analyst | no se construye egress nuevo; densidad sobre lo existente |

## Diferido explícitamente (no es deuda oculta)

- **Consumidores** (Analyst/codegen cargan `avoid_pattern` como restricción y
  `detection_heuristic` como check) → capa 3, donde codegen tendrá contexto de
  ejecución alcanzable.
- **Runner real de prove-it** (worktree en `fix_commit^` + pytest) → su propia
  pieza; hoy el `ProveItResult` se inyecta.
- **Seeding de las 3 lecciones reales** (matcher `7de8251`, doble escritor
  `fb44f46`, suite recursiva `4b9943a`) → requiere el runner real para
  capturar prove-it genuino; sembrar con Evidence sintética violaría la ley 4.

## Consumidores previstos

- Capa 3: workers de mantenimiento cargan lecciones de dominio antes de
  proponer; cada finding/patch rechazado se promociona a Lesson.
- ADR-043 (seguridad): cada `SECURITY_FINDING` reproducido se tipa como Lesson
  de defensa.
