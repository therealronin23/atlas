# ADR-074 — Activación real de ShadowRouter + DriftTripwire + aprendizaje gateado por juez

- Estado: **Aceptado** (2026-07-24)
- Módulos: `src/atlas/security/shadow_model.py`, `src/atlas/security/drift.py`,
  `src/atlas/transparency/gateway.py`, `src/atlas/core/inference_hub.py`,
  `src/atlas/core/orchestrator.py` (`enable_gate_d_pipeline`),
  `src/atlas/immunity/live_loop.py`, `src/atlas/immunity/teacher_debate.py`
- Promueve: `docs/membrana/OSM-042_shadow_model_active_defense.md` (idea
  "Absorbida" 2026-06-18, nunca cableada — este ADR es la promoción formal
  que la membrana exige antes de tocar producción)
- Depende de: ADR-053/054 (protocolo de transparencia, `TransparencyGateway`)

## Disposición definitiva (2026-07-27)

El wiring existe detrás de `ATLAS_PIPELINE_GATE_D=1`. La observación de ese flag
en un proceso demuestra `RUNTIME_CONFIGURED`, no por sí sola eficacia del
tripwire, calidad del shadow model ni aprendizaje aceptado como producto. El
umbral y el judge gate permanecen fail-closed; cualquier claim live debe
vincular la comprobación fechada que lo observó.

## Contexto

`ShadowRouter`, `SessionStateStore`, `ShadowModel` (`shadow_model.py`) y
`DriftTripwire` (`drift.py`) estaban construidos y unit-testeados desde
2026-06-18, con soporte completo en `TransparencyGateway.call()`
(`shadow_router=`, `shadow_model=`, `confidence=`, `on_escalation=`) — pero
CERO callers de producción los pasaban. La auditoría 2026-07-23 lo diagnosticó
a fondo: nunca se promovió de "membrana" (idea) a ADR, así que nadie tomó la
decisión explícita de activarlo. `GatedLessonRecorder` (el lazo inmune que
cosecha lecciones desde escaladas reales, `live_loop.py`) tenía el mismo
problema — `docs/governance/CAPABILITIES.md` lo describía como "cableado y
probado" cuando en realidad `TransparencyGateway.call()` nunca recibía
`on_escalation` desde el único caller real (`InferenceHub._infer_transparent`).

## Decisión

Activar los tres mecanismos para producción real, con las salvaguardas que
salieron de un Cónclave real (trío `deliberation_council`, Gemini + GLM en
vivo — Mistral Large no disponible, ver hallazgo de infraestructura abajo)
convocado sobre la propuesta de activación completa sin matices.

### Veredicto del Cónclave (2026-07-24)

**FAIL/BLOCKING** contra la activación tal como se propuso originalmente.
Objeciones sustantivas (Gemini y GLM convergieron independientemente):

1. Activar `threshold_active` (sustitución silenciosa de la respuesta real)
   directamente contra tráfico de producción nunca antes ejercitado es
   temerario — un falso positivo durante una tarea real corrompería trabajo.
2. Cablear `GatedLessonRecorder` con el verifier permisivo por defecto
   (acepta cualquier `avoid_pattern` no vacío) desde el día uno envenenaría
   `LessonStore` con los propios prompts inusuales del operador.
3. Usar un `session_id` fijo por proceso en `ShadowRouter.route()` mezcla el
   contador de escalada de tareas no relacionadas.
4. (Descontado parcialmente por el juez — ver más abajo) "Es un sistema de
   un solo usuario, no hay adversario" — el juez humano de esta sesión anotó
   que esto malinterpreta el modelo de amenaza real (contenido hostil vía
   web/MCP/conectores, no el propio operador atacándose), pero los puntos
   1-3 ya bastaban para no activar todo de golpe.

### Diseño final (operador + juez, incorporando las 3 objeciones accionables)

| Objeción del Cónclave | Corrección aplicada |
|---|---|
| (3) session_id fijo mezcla tareas | `TransparencyGateway.call()` usa `task_id` (si se pasa) como `session_id` de `ShadowRouter.route()`, con fallback al `session_id` fijo del gateway solo si no hay `task_id` — compatibilidad preservada |
| (1) `threshold_active` nunca ejercitado, riesgo de corromper trabajo real | `threshold_passive=0.80` en producción (no el 0.65 de los tests unitarios) — la propia OSM-042 ya recomendaba "empezar con τ_passive alto (0.80+) y ajustar con datos reales"; `threshold_active` se deja en el 0.88 ya diseñado, pero el umbral passive alto reduce drásticamente la probabilidad de alcanzar active con tráfico legítimo |
| (2) envenena el aprendizaje | El verifier por defecto de `TeacherDebate` (acepta cualquier avoid_pattern) se sustituye, SOLO en el path de escalada en vivo, por `build_judge_verifier()` (`live_loop.py`) — una llamada LLM real que evalúa si el patrón escalado es hostil real o un falso positivo. Lo que el juez RECHAZA (o no puede evaluar — fail-closed) ya no desaparece: `GatedLessonRecorder` lo anota en `workspace/immunity/pending_review.jsonl` para que la próxima auditoría completa lo revise |

**Por qué no se gatea el swap de `threshold_active` con el propio juez**:
`DriftTripwire` es, por diseño, una heurística numérica barata y en tiempo
real (sin LLM en el loop) — meter una llamada síncrona a un juez antes de
decidir el swap añadiría latencia/coste real a CADA inferencia y rompería el
propósito mismo de un tripwire. El swap, si ocurre, sigue siendo inmediato y
heurístico; lo que se gatea con el juez es la capa de APRENDIZAJE
(persistir un patrón como "amenaza" permanente), que solo dispara en
escaladas reales (evento raro, coste asumible).

### Wiring real (no teórico)

- `DriftTripwire(embedder=emb)` — mismo embedder que el resto de Gate D, no
  el `StubEmbedder` por defecto.
- `ShadowRouter(SessionStateStore(), threshold_passive=0.80, threshold_active=0.88)`.
- `ShadowModel(backend=...)` — backend real vía un `InferenceHub` interno
  PLANO (sin `transparency=`), para no recursar sobre el mismo gateway que
  lo invoca. Igual para el juez de `build_judge_verifier()`.
- `InferenceHub._infer_transparent()` llama a `drift.observe(task_id, prompt)`
  y pasa `confidence`/`monitor_cause` reales a `gateway.call()`, y propaga
  `on_escalation=` al hook de `GatedLessonRecorder`.
- Todo esto se construye en `Orchestrator.enable_gate_d_pipeline()` — el
  mismo gate opt-in (`ATLAS_PIPELINE_GATE_D=1`) que ya gobierna el resto del
  pipeline integrado, sin flag adicional (el operador decidió activar, no
  añadir otra capa de "construido pero apagado").

## Hallazgo de infraestructura (no bloqueante, registrado aparte)

El linaje EU del trío (`nvidia_mistral_large`) devolvió HTTP 410 Gone durante
el Cónclave: el modelo llegó a su fin de vida el 2026-07-23. El veredicto se
sostuvo con 2/3 voces reales (Gemini + GLM, convergencia independiente
fuerte); el hueco de Mistral queda registrado como tarea de background
(reparar el fallback de linaje EU en `deliberation_council.py`), no re-litiga
este ADR.

## Consecuencias

- Primera vez que `ShadowRouter`/`DriftTripwire` procesan tráfico real de
  Atlas. `threshold_passive=0.80` es deliberadamente conservador para la
  primera exposición a datos reales — ajustar con evidencia, no con
  intuición, es el propio criterio de OSM-042.
- `LessonStore` puede seguir creciendo con lecciones ACEPTADAS por el juez
  (antes: por un verifier ciego). Los rechazos ya no son invisibles:
  `workspace/immunity/pending_review.jsonl` es la cola de auditoría.
- Riesgo residual honesto: el juez es una llamada LLM más, con su propia
  tasa de error; fail-closed (rechazo) en caso de fallo/respuesta ilegible,
  nunca fail-open hacia la persistencia.
- Tests: `tests/test_transparency_gateway.py` (scoping por task_id, drift→
  confidence real, on_escalation pass-through), `tests/test_live_loop.py`
  (pending_review.jsonl, judge verifier fail-closed), `tests/test_gate_d_lazy_init.py`
  (wiring real end-to-end vía `enable_gate_d_pipeline()` sin hub inyectado).
