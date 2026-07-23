# T1.5 Coding Territory — disección, medición y veredicto Cónclave (2026-07-23)

Cierra `docs/design/atlas_master_plan.md` §5, T1.5 (ADR-068 + enmienda 2026-07-17 del
operador). Ejecutado en sesión maratón autónoma, con Cónclave real convocado para el
veredicto (no decisión solitaria de la sesión).

## Proceso

1. **Disección adopt-real** de Aider (Apache-2.0) y OpenHands-SDK (MIT,
   `software-agent-sdk` — no el repo grande `All-Hands-AI/OpenHands`, que se
   repositionó como producto SaaS "Agent Canvas" que solo consume el SDK como
   dependencia). Informes completos:
   `docs/knowledge/t05b_paso3/` no aplica aquí — ver referencias abajo.
2. **Medición**: 3 tareas idénticas (TDD sintético, test ya escrito y en rojo) contra
   AtlasCoder (motor propio), Aider y OpenHands-SDK, en worktrees efímeros, verificadas
   con `pytest` independiente en cada caso.
3. **Veredicto Cónclave real**: `convene_for_decision()` (`src/atlas/core/deliberation_council.py`),
   trío vía `adversarial_panel`, `difficulty=HARD, risk="high", irreversible=True`.

## Resultado de la medición (3 tareas: clamp trivial, dedupe bug-fix, formatter diseño)

| Motor | Resultado | Coste total | Hallazgo real |
|---|---|---|---|
| AtlasCoder (propio) | 1/6 (search_replace 0/3, apply_patch 1/3) | ~$0 | Bug real en `_apply_edits`: descarta bloques SEARCH vacío para archivo nuevo pese a que el prompt lo promete |
| Aider | 3/3 | $0.0166 | Integración de proveedores sin adaptador (mismo LiteLLM/convención que InferenceHub) |
| OpenHands-SDK | 3/3 | ~$0.038 | Agotó cuota gratuita de Gemini a mitad de la comparación; tool-calling nativo falló con Groq en la disección previa |

**Limitación honesta de la medición**: ninguna de las 3 tareas activó el loop de
autocorrección por FALLO REAL de test en Aider/OpenHands — el modelo acertó a la
primera en ambos. El "3/3" mide que el LLM base acertó, no necesariamente el
diferencial real del motor. Esto es precisamente lo que el Cónclave señaló como
objeción central.

## Veredicto del Cónclave: **FAIL** a la absorción

2 de 3 revisores respondieron (linaje GLM vía NVIDIA, linaje Mistral vía NVIDIA; el
slot Gemini falló la llamada — panel con diversidad parcial, no completa). Ambos
coincidieron, independientemente, en objeciones MAJOR:

1. El 3/3 no prueba el mecanismo de autocorrección real de Aider/OpenHands — solo que
   el modelo acertó a la primera. AtlasCoder, aunque falló, sí expuso su loop de
   corrección; de los otros dos no hay evidencia de comportamiento bajo fallo real.
2. La colisión de `litellm` (ambos motores fijan una versión exacta incompatible con
   `atlas-core>=1.89.0`) obliga a aislamiento de proceso para el motor de código
   CENTRAL de Atlas — contradice la premisa de "órgano propio", no "dependencia
   externa aislada".
3. Fragilidad operativa real de OpenHands (cuota agotada, tool-calling malformado con
   Groq) — no hipotética, medida en esta misma sesión.
4. La alternativa barata (arreglar ~15 líneas conocidas de AtlasCoder) es
   dramáticamente más barata que absorber y mantener 20k-100k LOC ajenas.

**Decisión aceptada**: NO se absorbe Aider ni OpenHands-SDK para T1.5. Se repara el
bug real de AtlasCoder (`_apply_edits`, soporte de `search_text` vacío para creación
de archivo) como pieza de bajo coste, independiente del veredicto de absorción.

## Estado de T1.5 tras este cierre

- **Absorción de Aider/OpenHands**: descartada formalmente con evidencia (no "no se
  hizo por falta de tiempo" — se hizo la disección completa, la medición completa, y
  el Cónclave dijo que no).
- **AtlasCoder**: bug de `_apply_edits` reparado (ver commit correspondiente).
- **Pendiente real, si se quiere revisitar en el futuro**: para medir de verdad la
  capacidad de autocorrección-por-fallo-real-de-test (el diferencial que este
  experimento NO logró medir), haría falta una tarea con un bug más sutil (no
  inferible solo leyendo el test) o un modelo más débil que fuerce al menos una
  iteración real de fallo→lectura de traceback→fix. No se repite esta noche — sería
  gastar más presupuesto en un experimento cuyo diseño ya se sabe insuficiente para
  la pregunta que importa.

## Artefactos de la sesión (no permanentes, viven en /tmp — referencia si se revisita)

- `dissection_aider.md`, `dissection_openhands.md` — disecciones completas.
- `comparison_atlascoder.md`, `comparison_aider.md`, `comparison_openhands.md` —
  mediciones completas con diffs y tablas.
- Veredicto crudo del Cónclave (objeciones completas de los 2 revisores) preservado
  en este documento arriba, no en un fichero aparte de `/tmp`.

## Backlog relacionado (ya en `docs/backlog.yaml`)

Ningún ítem `t1-*` de Track B duplicaba este trabajo — se verificó explícitamente
durante la extracción de backlog que ADR-068/el dossier de OpenHands se dejaron sin
entrada nueva porque este mismo trabajo los cubría en vivo esa noche.

## CORRECCIÓN post-cierre (2026-07-23, sesión siguiente): el encuadre de este veredicto era el equivocado

El operador señaló, correctamente, que este Track A nunca debió plantearse como
"¿absorbemos Aider u OpenHands-SDK COMO MOTOR (dependencia instalada)?" — la intención
real (consistente con `atlas-coding-discipline` y la memoria `adopt-real-not-shell`)
era "¿qué técnicas concretas de Aider/OpenHands le faltan a AtlasCoder para igualar o
superarlos?". Bajo el encuadre equivocado que usé, la objeción #2 del Cónclave
("colisión real de litellm obliga a aislamiento de proceso") pesó como si fuéramos a
instalar el paquete completo en el venv de Atlas — algo que nunca fue necesario ni
se planteó hacer. Verificado además que esa objeción, tal como la escribí, estaba
mal fundamentada para OpenHands: su `pyproject.toml` real declara `litellm>=1.84.1`
(un suelo, NO un pin exacto), compatible con el suelo de atlas-core (`>=1.89.0`) — solo
Aider tiene un pin exacto (`litellm==1.82.3`) genuinamente incompatible. Detalle en
memoria `feedback-scope-adoption-as-extraction`.

**Esto NO invierte el veredicto de "no absorber el paquete entero"** — las objeciones
#1 (no se midió autocorrección real) y #3 (fragilidad operativa medida en vivo) siguen
siendo válidas y no dependen del encuadre. Pero SÍ deja abierta, sin cerrar, la
pregunta correcta que nunca se hizo: extraer como código nativo (sin nueva dependencia,
sin colisión posible) técnicas concretas ya identificadas en la disección real:

- De Aider (`aider/coders/base_coder.py`): el **bucle de autocorrección** (aplicar
  edición → lint/test → si falla, reintentar con el error en contexto) — la brecha
  que explica el 1/6 medido de AtlasCoder hoy.
- De OpenHands-SDK (`agent.py::step()`): manejo explícito de
  `LLMContextWindowExceedError`/`FunctionCallValidationError` con condensación/retry,
  más maduro que lo que tiene hoy InferenceHub/AtlasCoder.

**Corrección sobre repo-map**: al ir a crear un ítem de backlog para "portar el
repo-map con PageRank de Aider", verifiqué primero el código real de AtlasCoder
(disciplina que casi me salto por segunda vez en la misma tarde) y **ya existe**:
`src/atlas/core/repo_map.py` (211 líneas) implementa PageRank propio (sin networkx,
por iteración de potencias) sobre símbolos extraídos vía `ast` (sin tree-sitter,
decisión deliberada — Atlas es un proyecto Python puro), cableado en
`AtlasCoder.plan()` vía `repo_map_files`. No se crea ítem de backlog para esto —
ya está construido, con su propia implementación nativa, no un port de Aider.

Backlog creado en esta corrección: `t1-atlascoder-selfcorrect-loop` (el bucle de
autocorrección de Aider) y `t5-context-window-condensation-retry` (el manejo de
contexto excedido de OpenHands, que se apoya en `classify_provider_error` ya
construido en T5/Track D de la sesión anterior pero sin ningún consumidor que actúe
sobre `ErrorKind.CONTEXT_LENGTH` todavía).

## CORRECCIÓN #2 (2026-07-23, sesión siguiente): `t1-atlascoder-selfcorrect-loop`
también estaba mal encuadrado — el mecanismo ya existía

Al ir a implementar el ítem, la verificación de código real (misma disciplina que
salvó el caso repo-map arriba) mostró que `AtlasCoder.code()` ya tiene el loop
completo desde el commit FUNDACIONAL `6df920e` (el primer commit que introdujo
AtlasCoder, no algo añadido después): itera hasta `max_iterations`, aplica
ediciones, corre `test_cmd`, y si falla mete `test_output` en
`_ITERATION_ERROR_SECTION` para el prompt del siguiente intento
(`atlas_coder.py:487-488`). El "why" original del ítem afirmaba "AtlasCoder hoy no
tiene este loop" sin haber grepeado el código — la misma clase de error que casi
produjo un ítem duplicado para el repo-map, esta vez consumado en el propio
ítem de backlog en vez de detectado antes de crearlo.

Lo que sí faltaba, y es lo único que se entregó: un test que demuestre el
mecanismo end-to-end (nadie lo probaba — `test_code_iterates_on_test_failure`
solo comprueba que itera, no que el error llegue al segundo prompt).
`tests/test_atlas_coder.py::test_code_corrects_using_previous_test_error` usa un
hub mockeado que solo devuelve el fix correcto si ve el marcador del error de la
iteración anterior en el prompt; verificado además por mutación (comentar la
línea de inyección de `prev_error` hace fallar el test, confirmando que no es un
mock complaciente). Cero cambios en `atlas_coder.py`. El 1/6 medido en T1.5 no
viene de la ausencia del loop — viene de que el modelo no corrigió dado el error,
o de los bugs de `_apply_edits` ya reparados por separado.
