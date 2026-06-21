# Auditoría + postmortem — sustrato de memoria verificable (pre-merge, 2026-06-21)

Rama `feat/verifiable-memory-substrate` (1a–1d). Auditoría completa antes del merge a
`main`. Alcance: motor genérico (`record.py`, `memory_index.py`, `memory_abstractor.py`),
inquilino de seguridad (`lesson_index.py`, `pattern_abstractor.py`) y el cableado al
`TeacherDebate`. Método: lectura línea a línea, mypy strict, búsqueda de fugas/concurrencia,
comparación con patrones ya establecidos en el repo (`vector_store.py`).

## Hallazgos y resolución

| # | Sev | Hallazgo | Resolución |
|---|---|---|---|
| 1 | **MEDIO** | Reabrir el índice con un embedder de **otra dimensión** daba scores SILENCIOSAMENTE basura: `_cosine_similarity` hace `zip` y truncaba al vector más corto, sin error. Rompe la promesa central de persistencia (1a). | Tabla `meta` + `_guard_embedder_dim()`: persiste la dim en la 1ª apertura y lanza `ValueError` si una reapertura usa otra. Replica el patrón ya existente en `vector_store.py`. Test `TestDimGuard`. |
| 2 | BAJO-MED | Tras la migración suave (abrir una DB de esquema pre-1d), las filas viejas quedaban con `tier=NULL` → invisibles a `tier_counts()` y sin base de ocio para `apply_decay`. | Backfill en `_migrate_temporal`: `tier='hot'`, `access_count=0`, `last_access_ns=valid_from_ns` para las filas migradas. Test `TestMigrationBackfill` (construye el esquema pre-1d a mano). |
| 3 | BAJO | `supersede(old, new)` no verificaba nada: con `old_id` inexistente hacía un no-op silencioso (memoria nueva "supersede" a la nada); con un `new_id` ya existente, la rama `ON CONFLICT DO UPDATE` NO fijaba el lineage → supersesión perdida en silencio. | Guardas explícitas: `KeyError` si `old_id` no existe; `ValueError` si el nuevo id colisiona. Test `TestSupersedeGuards`. |
| 4 | BAJO | `recall_all` calculaba `_cosine_similarity` **dos veces** por fila (score y matched). Desperdicio (heredado del `LessonRecaller`). | Calcular una vez por fila. Sin cambio de comportamiento. |
| 5 | INFO | La conexión sqlite usa `check_same_thread=True` → no apta para uso concurrente entre hilos (igual que el `LessonRecaller` que sustituye). | Declarado como límite conocido en el docstring del motor. No se "arregla" porque no hay consumidor multihilo aún (el loop inmune no está ensamblado). A resolver cuando lo esté. |

## Lo que se revisó y está bien (sin cambios)

- **Inyección SQL:** los únicos `f-string` en SQL (`_migrate_temporal`) usan nombres de
  columna de una constante interna (`_TEMPORAL_COLUMNS`), no entrada de usuario. El resto
  son consultas parametrizadas. OK.
- **Paridad de scores** motor↔`LessonRecaller`: garantizada por reutilizar
  `_cosine_similarity` (testeada). OK.
- **Desacople motor/inquilino:** el motor no importa nada de seguridad; los inquilinos
  componen el motor. mypy strict limpio en los 13 módulos. OK.
- **Determinismo:** orden de inserción preservado para desempates; ids de patrón
  direccionados por contenido. OK.

## Postmortem — patrón a recordar

El fallo #1 es el de siempre y el más instructivo: **un test verde no prueba lo que no
ejercita.** Toda la suite de 1a pasaba porque ningún test reabría el índice con OTRO
embedder — exactamente el caso de uso real de un sustrato persistente. Lo destapó la
auditoría comparando con `vector_store.py`, que YA tenía el guard. Lección (coherente con
`feedback-convergence-discipline-verification`): cuando ya existe un patrón en el repo para
un problema (aquí, verificar la dim al reabrir), un módulo nuevo que lo ignora es sospechoso
por defecto. Buscar el prior-art interno antes de dar por bueno lo nuevo.

## Deuda declarada (NO bloquea el merge; anotada en `design_verifiable_memory.md`)

- Umbrales de tier/decay = política (parámetros), no aprendidos.
- `pending→retire tras grace` y `auto-touch` en recall: sin cablear (decisión explícita).
- El inquilino de seguridad no expone aún `supersede`/`retire`/tiers (solo delega recall).
- Concurrencia multihilo (hallazgo #5).
- Discriminación intención-vs-tema (1c): necesitaría contrastive, no coseno crudo.

## Veredicto

Suite **2053 verde**, mypy strict limpio. Los hallazgos con impacto en correctitud (#1–#3)
están corregidos con regresión. El resto es deuda declarada, no defecto oculto. **Apto para
merge a `main`.**
