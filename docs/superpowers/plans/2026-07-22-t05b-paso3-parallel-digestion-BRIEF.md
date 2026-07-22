# T0.5b paso 3 — digestión paralela del corpus por proveedor (BRIEF para sesión fresca)

Estado: **redactado, NO ejecutado**. El operador pidió explícitamente posponer
esta pieza a una sesión nueva ("evidentemente no sería para esta... dejarlo
todo redactado para que en la siguiente sesión que estuviera fresca con un
prompt que me dieras tú, lo empezaría de cero"). Este documento es ese
prompt + el diseño completo — no requiere releer el resto de la sesión
MAXIMUS 2026-07-22 para poder arrancar.

## Por qué existe esto

`atlas_master_plan.md` §T0.5.b pide, sobre los 707 docs del repo:
1. Clasificación completa (alimenta_item / candidata / histórico / GAP).
2. Lista de GAPS (temas que el plan no cubre pero el corpus sí pide).
3. Lista de CONTRADICCIONES (docs que se contradicen entre sí o con el plan).
4. Un "plan v2 con fuentes citadas" y una lista explícita de "revisado y
   descartado".

Ya hecho (no repetir):
- **Paso 1** (PRIME Cycle 4, 2026-07-22): inventario heurístico por ruta —
  `atlas corpus-inventory` → `docs/knowledge/corpus_inventory.json`.
- **Paso 2** (MAXIMUS Cycle 6, 2026-07-22): clasificación semántica del
  bucket `sin_clasificar` contra las 7 secciones T0-T6 de
  `atlas_master_plan.md §5`, coseno contra `fastembed` local, umbral 0.5.
  Resultado medido en vivo: `sin_clasificar` 86%→65% (604→461 de 707 docs).
  Mecanismo: `atlas.knowledge.corpus_semantic_classifier.classify_corpus_semantically()`,
  invocable vía `atlas corpus-inventory --semantic`.

**Falta el paso 3**: síntesis real — gaps, contradicciones, plan v2. Esto es
juicio, no mecánico; por eso quedó fuera del alcance de Cycle 6 y por eso el
operador propuso paralelizarlo entre proveedores en vez de hacerlo uno a uno
en una sola sesión (~707 docs es demasiado para leer secuencialmente sin
perder calidad ni gastar de más).

## El diseño del operador (traducido a plan ejecutable)

Petición literal: dividir el trabajo de digestión entre los ~4 proveedores
configurados (Groq, NVIDIA, OpenRouter, Gemini) — **más las cuentas/modelos
que haya DENTRO de cada proveedor** — y que un agente auditor por división
revise el resultado de esa división, para ahorrar tokens y no perder calidad
gestionando todo a mano.

Providers reales ya cableados en `src/atlas/core/inference_hub.py`
(`DEFAULT_PROVIDERS`, verificar que siguen vivos con
`atlas.core.self_maintenance.provider_smoke` antes de arrancar — providers
mueren/rotan con frecuencia, ver comentarios `RETIRADO` en ese fichero):

| División | Proveedor | Modelos disponibles dentro (pool real) |
|---|---|---|
| A | Groq | `groq_llama_70b`, `groq_compound`, `groq_qwen3` |
| B | OpenRouter | `openrouter_nemotron`, `openrouter_nemotron_ultra`, `openrouter_hermes4_70b` |
| C | NVIDIA NIM | `nvidia_llama_large`, `nvidia_glm`, `nvidia_mistral_large`, `nvidia_mistral_medium` |
| D | Gemini | `gemini_free` |

Todos son tiers gratis (ver comentarios en `DEFAULT_PROVIDERS`) — el coste
real de esta pieza es tiempo/rate-limit, no dinero. Usar
`InferenceRequest(wait_for_ratelimit=True)` para lotes largos (lección de la
absorción 2026-07-08: sin esto, un 429 tira todo el lote en vez de esperar
al cooldown).

### Asignación de divisiones (por coherencia de plan-tramo, no chunking arbitrario)

Dividir por tramo del plan maestro produce mejor detección de contradicciones
que trocear alfabéticamente — cada división lee un cluster temático completo:

- **División A (Groq)** — docs clasificados T0/T1 (sucesión + autoconstrucción).
  Es el tramo EN CURSO — máxima prioridad si el tiempo aprieta.
- **División B (OpenRouter)** — docs clasificados T2/T3 (UI/UX + capacidad
  universal).
- **División C (NVIDIA)** — docs clasificados T4/T5/T6 + bucket `historico`
  completo (48 docs) — NVIDIA tiene el pool de modelos más grande, encaja con
  el volumen mayor de este grupo.
- **División D (Gemini)** — el bucket `sin_clasificar` restante (461 docs,
  65% del corpus) — es el más difícil (la clasificación semántica ya falló en
  distinguirlos) y Gemini tiene la ventana de contexto más grande del pool,
  lo que ayuda con la limitación YA CONOCIDA de Cycle 6: docs largos enteros
  diluyen la señal de coseno (~0.45) — un LLM leyendo el doc completo no
  tiene ese problema.

Fuente para la asignación real por doc: `docs/knowledge/corpus_inventory.json`
(regenerar primero con `atlas corpus-inventory --semantic --json` para tener
el estado más fresco — puede haber cambiado desde 2026-07-22).

### Tarea de digestión (misma spec para las 4 divisiones)

Por cada doc de su lote, cada división produce un registro:

```json
{
  "path": "docs/...",
  "verdict": "alimenta_item | candidata | historico | gap",
  "plan_section_cited": "T0.3 | ... | null",
  "contradiction_flag": false,
  "contradiction_note": "",
  "confidence": "alta | media | baja"
}
```

`gap` = el doc describe algo real y vigente que NINGUNA sección T0-T6 cubre
hoy — es la señal que alimenta el "plan v2". `contradiction_flag` = el doc
afirma algo que choca con otro doc ya visto o con el plan mismo — anotar
CUÁL en `contradiction_note`, nunca dejarlo implícito.

### Auditoría por división (pieza que pidió el operador explícitamente)

Un agente auditor **por división, con un proveedor DISTINTO al que hizo la
digestión** (evita sesgo de autoevaluación — el mismo patrón que ya usa
`autobuild-auditor` en este repo: el planificador/implementador y el auditor
nunca son el mismo modelo). El auditor:
1. Revisa el 100% de los registros con `contradiction_flag=true` o
   `verdict=gap` contra el doc real (no contra el resumen del digestor).
2. Muestrea ~15% del resto (`verdict` alimenta_item/candidata/historico) para
   detectar degradación sistemática de un digestor concreto.
3. Corrige o confirma cada veredicto muestreado; produce un informe QA por
   división (cuántos corregidos, patrones de error si los hay).

Rotación sugerida proveedor-digestor → proveedor-auditor (ninguno se audita
a sí mismo): A→C, B→D, C→A, D→B.

### Síntesis final (NO delegar — juicio real de la sesión orquestadora)

Con las 4 divisiones + sus 4 auditorías en mano, la sesión que orquesta este
trabajo (Sonnet/Fable, la que lanzó las 8 dispatches) hace la síntesis real:
lista de gaps consolidada, lista de contradicciones consolidada, y el
borrador de "plan v2" citando fuentes — esto es exactamente lo que
`atlas_master_plan.md §T0.5.b` pide y es trabajo de juicio, no mecanizable
más allá de este punto. Esta pieza NO se paraleliza.

## Cómo ejecutarlo (mecánica concreta)

Cada división = una dispatch del tool `Agent` (subagente), prompt
autocontenido con: (a) la lista de paths de su lote (extraída de
`corpus_inventory.json`), (b) la spec de digestión de arriba, (c) qué
provider/modelo usar si el subagente tiene forma de fijar el proveedor de
inferencia (si no, usar el modelo por defecto del subagente — el interés
aquí es paralelizar TRABAJO, no necesariamente forzar el proveedor exacto
del hub Atlas dentro del propio Claude Code). Si se quiere usar el
`InferenceHub` de Atlas de verdad (proveedores reales de la tabla arriba,
no los modelos de Claude Code), la alternativa es un script Python que
invoque `InferenceHub().infer(InferenceRequest(...))` por doc, corrido
DIRECTAMENTE (no vía subagente Claude Code) — más barato, más fiel a "usar
las cuentas que tenemos", pero sin el juicio de un LLM agente completo para
casos ambiguos. Decisión de diseño abierta para la sesión que ejecute esto:
**cuál de las dos vías usar** — no está prejuzgado aquí porque depende del
presupuesto/tiempo disponible ese día.

## Prompt listo para la sesión fresca

```
Lee docs/superpowers/plans/2026-07-22-t05b-paso3-parallel-digestion-BRIEF.md
completo. Es el diseño ya cerrado de T0.5b paso 3 (síntesis del corpus:
gaps + contradicciones + plan v2 citado) del master plan. Ejecuta el plan
tal cual está escrito: 4 divisiones por proveedor (Groq/OpenRouter/NVIDIA/
Gemini) sobre docs/knowledge/corpus_inventory.json, un auditor cruzado por
división (rotación A→C, B→D, C→A, D→B), y tú haces la síntesis final
(gaps + contradicciones + plan v2 con fuentes citadas) — esa última pieza
no se delega. Antes de arrancar: regenera corpus_inventory.json con
`atlas corpus-inventory --semantic --json` (puede haber cambiado) y corre
`atlas.core.self_maintenance.provider_smoke` para confirmar que los 4
proveedores de la tabla siguen vivos (mueren/rotan con frecuencia — hay
comentarios RETIRADO en inference_hub.py de proveedores ya muertos). Decide
tú, con la información de presupuesto/tiempo de esa sesión, si las 4
divisiones corren como subagentes Claude Code o como llamadas directas a
InferenceHub — el brief documenta ambas vías sin prejuzgar cuál. Al acabar:
el borrador de plan v2 va a un fichero nuevo bajo docs/design/ (nunca edites
atlas_master_plan.md directamente — es terreno del operador, mismo criterio
que Cycle 6), y la entrada del WORK_LEDGER debe declarar honestamente si
T0.5b quedó cerrado del todo o parcial.
```
