# Mapa de autoridad — memoria: dueños, promoción y borrado

<!-- Doc interno de diseño. Cierra ADC-WO-103 (P04). -->

**Estado**: medido y vigilado en código el 2026-08-11.
**Ficha**: `ADC-WO-103` — *Decide memory ownership and promotion paths*.
**Decisión previa**: `EDR-ADR-057` (2026-07-31) acepta `GOVERNED_PROMOTION`.
**Guardia**: [`tests/test_authority_memory_owners.py`](../../tests/test_authority_memory_owners.py).
**Hermano**: [mapa de Mission/Task](authority_map_mission_task.md) (WO-102).

La ficha pide *"un dueño por clase de memoria"* y *"contratos explícitos de
promoción y borrado"*, con tres riesgos nombrados: `privacy leakage`,
`loss of provenance` y `dual authority`. Aquí está lo medido, no lo previsto.

## Corrección de partida: no eran ocho escritores

Yo había apuntado *"8 rutas de promoción en 6 ficheros sin dueño único"*.
Midiéndolas una por una, la cuenta era engañosa: no son ocho escritores
compitiendo por el mismo estado, son promociones de **clases distintas**, más
sus llamantes.

| Ruta | Clase | Qué es realmente |
|---|---|---|
| `LessonStore.promote_failure` | lecciones | **el escritor** |
| `LessonRunner.run_and_promote` | lecciones | llamante del anterior |
| `promote_if_fixed` | lecciones | fachada del anterior |
| `ErrorRegistry.mark_promoted` | registro de errores | back-link de trazabilidad, no promoción |
| `promote_after_trial` | catálogo MCP | función **pura**, sugiere estado, no escribe |
| `CoreEngine.promote_candidate` | entidades de negocio | escritor, con barrera humana |
| `gate_h → promote_if_valid` | herramientas generadas | escritor |

Consolidarlas "bajo un dueño único" habría fusionado cosas que no comparten
estado. La consolidación que **sí** hacía falta estaba en otro sitio y la
encontró este trabajo: el grafo. Ver §3.

## 1. Las clases y sus dueños

| Clase | Dueño | Sustrato | Vigilado |
|---|---|---|---|
| **Operacional** (fallos, patrones aprobados, snapshots de verdad, métricas de proveedor) | `ErrorRegistry`, `ApprovedPatternStore`, `TruthSnapshotStore`, `ProviderMetricsStore` (`memory/memory_system.py`) | ficheros JSON por entrada | — |
| **Bloques** (memoria siempre en contexto) | `BlockMemory` (`memory/block_memory.py`) | un único `blocks.json` | — |
| **Lecciones** | `LessonStore` (`core/lesson_store.py`) | `workspace/lessons/*.json` | sí (dos guardias) |
| **Grafo estructural** (Kuzu: FileVersion, Module, Symbol, CALLS, IMPORTS, ObsidianNote) | `build_project_graph` bajo `ProjectGraphWriterLock` | BD Kuzu | sí (tres guardias) |
| **Grafo semántico / vectores** | `KuzuVectorStore` (`memory/vector_store.py`) | BD Kuzu **aparte** | sí (apertura) |
| **Índice cifrado** | `MemoryIndex` (`memory/memory_index.py`) | SQLite con `secure_delete=ON` | — |
| **Evidencia** | `MerkleLogger` | JSONL encadenado | sí (en WO-102) |
| **Entidades de negocio** | `CoreEngine.promote_candidate` | store de negocio | sí (barrera humana) |
| **Herramientas generadas** | `gate_h` → `promote_if_valid` | registro de tools | — |

Las filas sin guardia no están desprotegidas por descuido: son clases con **un
solo módulo** que las toca, sin un segundo camino plausible hoy. Se anotan como
tales en vez de inventarles un test que no distinguiría nada.

## 2. Kuzu se abre por un solo sitio

Todas las aperturas pasan por `open_kuzu_database` (`memory/kuzu_runtime.py`),
que **acota memoria y tamaño explícitamente**. El constructor crudo de Kuzu
hereda defaults dimensionados al host — el mismo tipo de fallo que dejó 7,8 GB
de RAM del host accesibles desde el jail. El guardia impide que vuelva a
aparecer un `kuzu.Database(...)` suelto.

Nueve módulos abren la BD; **cinco** en `read_only=True` (API, MCP graph
server, `hypotheses`, `component_wiring_drift`, `project_graph`) y **cuatro**
para escritura.

## 3. El defecto: el lock protegía a un llamante, no al recurso

`graph-rebuild-single-writer` es una manía de `AGENTS.md` que ya se rompió una
vez: el 2026-08-08, dos ticks solapados dejaron el catálogo Kuzu a medias
(sobrevivieron `Symbol`/`CALLS`/`CONTAINS`, desaparecieron
`FileVersion`/`Module`/`IMPORTS`). El arreglo de aquel día fue
`ProjectGraphWriterLock`, y era correcto — pero se puso en
`maintenance_facade`, o sea **en el tick del daemon**.

El entrypoint `python -m atlas.memory.project_graph` escribe **la misma BD** y
no tomaba nada. Correrlo con el daemon vivo reproducía el incidente original
tal cual. Es la forma exacta de *"una aproximación de la puerta no es la
puerta"*: el invariante estaba protegido para un camino de los dos.

Arreglado el 2026-08-11: el entrypoint toma el lock y sale con
`grafo ocupado: …` si otro escritor lo tiene. El guardia comprueba que **todo
módulo que llame a una función escritora del grafo nombre el lock**, así que un
tercer camino futuro falla en rojo en vez de corromper la BD.

**Por qué el lock no se metió dentro de `build_project_graph`**, que sería lo
elegante: `flock` no es reentrante entre descriptores distintos del mismo
proceso, así que el daemon —que ya lo tiene tomado— chocaría consigo mismo.
Hacer el lock reentrante toca código de seguridad para arreglar un problema
que no existe; la alternativa barata (que cada entrypoint lo tome, vigilado
por un test) cubre el mismo riesgo sin ese coste. Queda dicho aquí para que
nadie lo "mejore" sin saber por qué está así.

## 4. Contratos de promoción

Regla común, en el orden en que se aplica:

1. **Nada se promueve sin evidencia.** `LessonStore` no guarda una lección cuyo
   `Evidence` no sea `PASS`; su `promote_failure` exige un `ProveItResult` —
   el test tiene que **fallar antes y pasar después**. Copias repetidas de una
   observación **no** son corroboración independiente.
2. **La procedencia viaja con el dato.** `ErrorRegistry.mark_promoted` cierra
   el back-link: la `FailureEntry` que originó una lección queda marcada con el
   id de la lección resultante. Sin eso, una lección es una afirmación sin
   origen.
3. **Lo que cruza a un humano necesita un humano.** `promote_candidate` exige
   `reviewed_by` no vacío y **lanza** si falta; `requires_review` es const
   `True` por contrato en el candidato.
4. **La promoción automática a las capas compartidas sigue SIN autorizar.**
   `EDR-ADR-057` aceptó la *dirección* `GOVERNED_PROMOTION`, no un promotor
   activo. La frontera mantenimiento/promotor separada del agente primario que
   la recomendación exige **está sin construir**. Este mapa no la da por hecha.

## 5. Contratos de borrado

| Clase | Borrado | Garantía |
|---|---|---|
| Índice cifrado | crypto-shred | `MemoryIndex` marca `shredded` y destruye la clave de contenido; SQLite con `PRAGMA secure_delete=ON` sobrescribe las páginas liberadas. El contenido queda irrecuperable, la fila queda como prueba de que existió. |
| Bloques | `BlockMemory.delete(label)` | Reescribe `blocks.json` completo; auditado en Merkle. |
| Lecciones | sin borrado | Se retiran por estado (`_set_state`), no se destruyen: perder una lección es perder la prueba de por qué existía la regla. |
| Evidencia (Merkle) | **no existe** | Append-only por diseño. Tocar una entrada impide arrancar el orquestador. |
| Sesiones de sombra | `delete_session` | Aislado por sesión. |

## 6. La frontera de privacidad

Lo privado se destila **antes** de entrar en nada compartible. `PIISurrogate`
redacta los resultados de herramienta antes de reinyectarlos al loop y antes de
persistir el estado agéntico — por eso `TaskPersistence` no guarda PII en
claro. El grafo estructural se construye de **git + AST**: rutas, símbolos e
imports, nunca contenido de conversación.

**Límite honesto**: no hay hoy un test que demuestre "ningún dato privado llega
al grafo compartible". Lo que hay es que el grafo se construye de fuentes que
no contienen datos privados, lo cual es más fuerte por construcción y más
débil como garantía verificable — si mañana alguien ingiere otra fuente, nada
lo detecta. Queda como el hueco conocido de este mapa.

## Lo que este mapa NO afirma

- No afirma que exista un promotor automático gobernado: no existe y no está
  autorizado.
- No afirma cobertura de privacidad verificable (§6).
- No afirma que las clases sin guardia sean inmunes: afirma que hoy tienen un
  solo escritor y que no hay un segundo camino plausible que un test pudiera
  distinguir.
- La medida de calidad de recuperación sigue siendo LongMemEval_S n=500,
  Recall@5 0,9300–0,9340 — una **línea base**, no un promotor activado.
