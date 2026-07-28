# ADR-076 — Descubrimiento y vetting continuos de MCPs remotos; auto-adopción gobernada (C bloqueado por el Cónclave)

- Estado: **Parcial** — secciones A (re-siembra continua) y B (vetting
  continuo cursor-driven) **Aceptadas** (código real, TDD, mypy limpio,
  commiteadas). Sección C (auto-adopción real sin clic humano) **RECHAZADA,
  NO IMPLEMENTADA y AUSENTE** tras el bloqueo del Cónclave — ver veredicto
  íntegro más abajo. No existe
  hoy ningún código de auto-adopción en el repo; esta sección documenta por
  qué NO se construyó, no una feature apagada por flag.
- Extiende: **ADR-075** (pipeline de vetting MCP, Aceptado 2026-07-24). Este
  ADR es la continuación directa: convierte el pipeline manual de ADR-075
  (corrido a mano, produjo 904/2100 completados el 2026-07-24) en dos ticks
  del scheduler de mantenimiento, y evalúa la petición explícita del
  operador de sumar auto-adopción real.

## Disposición atómica definitiva (2026-07-27)

- **A**: `ACCEPTED`, código presente, activación opt-in.
- **B**: `ACCEPTED`, código presente, activación opt-in; cubre stage1/stage2
  acotado, no las etapas 3–6 completas de ADR-075.
- **C**: `REJECTED`, `NOT_IMPLEMENTED`, `ABSENT`; no hay flag dormido.
- La comprobación posterior es evidencia de B, no una capacidad autónoma nueva.

Una variable observada en el proceso solo acredita `RUNTIME_CONFIGURED`, nunca
`LIVE_VERIFIED`. Las cifras de 2026-07-24 son evidencia histórica.

## Contexto

ADR-075 construyó y ejercitó el pipeline manual acotado de vetting (etapa 1
pre-screen + partes de etapa 2A stdio y 2B http). La corrida real del
2026-07-24 sobre 2100 candidatos elegibles: 904 completados (192/229 stdio,
712/1871 http), 10.406 tools reales devueltas, 4 candidatos con hallazgo
MAJOR de semgrep. Todo esto corrió **a mano**, invocado por scripts uno a
uno.

El operador pidió que esto deje de ser manual — reseed y vetting como ticks
del scheduler — y, explícitamente confirmado (no asumido), que además se
sume **auto-adopción real** para lo que pase el pipeline completo limpio,
no solo una cola para revisión humana.

Esto último **no es aditivo**: ADR-075 tiene dos invariantes aceptados el
mismo día que esta petición contradice directamente —

> **I5** · admisión HITL por lotes vía el Decider A3 + receipt Merkle;
> activación reversible (A3.3). Cero auto-adopción de tipos remotos
> ejecutables. *(sección "Decisión — invariantes no negociables")*

> **I2-R** · para la pista remota (http, 1869 candidatos): admisión basada
> 100% en comportamiento observado + IOC, nunca en "hemos visto el
> código". Riesgo residual reconocido, no oculto (ver Consecuencias).
> *(misma sección)*

Y en código real (verificado antes de escribir una sola línea):
`Orchestrator.adopt_mcp_server` (`src/atlas/core/orchestrator.py:318`)
declara `sensitivity="high"`, y tanto `HumanDecider`
(`src/atlas/core/decider/human_decider.py:32-33`) como `AutonomousDecider`
(`src/atlas/core/decider/autonomous_decider.py:93-94`, "regla
constitucional #4" de `AGENTS.md`) fuerzan `RequiresHuman`/`Deny` sin
excepción para `sensitivity="high"`.

Por eso la auto-adopción se trató como **una enmienda a un invariante ya
aceptado**, no como una feature nueva: se convocó un Cónclave real
(`deliberation_council`) antes de escribir cualquier código de adopción,
con el plan bifurcándose según el veredicto.

## A — Tick de re-siembra continua (Aceptado)

`src/atlas/mcp/registry_seed.py::reseed_candidates()` — extraído de
`scripts/mcp_seed_registry.py::main()` (que pasa a wrapper delgado sobre
ella), importable e inyectable (fetcher vía `RegistrySource`).
`write_seeded_catalog()` centraliza el formato YAML compartido entre el
script y el tick.

`Orchestrator.maintenance_mcp_reseed_tick()` (delega a
`MaintenanceFacade`): guardia `ATLAS_NESTED_TEST_RUN`, opt-in
`ATLAS_MCP_RESEED=1`, autothrottle propio vía
`workspace/mcp/reseed_state.json` (gitignored) —
`ATLAS_MCP_RESEED_INTERVAL_S` (default 86400s) desde el último **éxito**;
un fallo de red no cuenta como éxito, el siguiente tick reintenta de
inmediato. Wired a `extra_cycles` del `MaintenanceScheduler`.

12 tests nuevos (`tests/test_registry_seed_reseed.py`,
`tests/test_mcp_reseed_tick.py`), mypy limpio.

## B — Tick de vetting continuo (Aceptado)

`src/atlas/mcp/candidate_stage2_cursor.py` — nuevo módulo:

- `classify_stage2_status(row) -> completed | terminal | retryable`,
  calibrado contra las razones REALES del reporte de hoy (2100 filas): HTTP
  401/403/404/405, DNS muerto, `registryType` no soportado, paquete/versión
  inexistente, entry point ambiguo/sin declarar → `terminal` (no cambia sin
  acción externa); 5xx, HTTP 0 (timeout/conexión real, ver
  `http_mcp_transport.py`), redirect no seguido, crash no anticipado →
  `retryable`. Razón no catalogada → `retryable` por defecto (fail-closed
  hacia "sigue intentando", I6). Verificado contra el reporte real completo:
  904 completed (exacto), 1098 terminal, 98 retryable, sin excepciones.
- `select_stage2_batch` — nuevos (no en el reporte previo) primero, luego
  `retryable`; nunca `terminal`/`completed`; límites independientes por
  pista.
- `merge_stage2_report` — pisa por nombre, preserva el resto intacto.

`Orchestrator.maintenance_mcp_vetting_tick()`: stage1 completo cada ciclo
(barato, read-only) + lote de stage2 (`_MCP_VETTING_STDIO_BATCH=5`,
`_MCP_VETTING_HTTP_BATCH=20`) vía el cursor de arriba; cada candidato en su
propio try/except (un crash no pierde el lote). El propio reporte fusionado
es el estado — **sin cursor de posición aparte** (ver D).

27 tests nuevos (`tests/test_candidate_stage2_cursor.py`,
`tests/test_mcp_vetting_tick.py`), mypy limpio.

## D — Barrido de lo ya existente (verificado, sin mecanismo aparte)

Consecuencia directa de B, no una pieza nueva. Verificación read-only sobre
datos reales (catálogo actual, 2114 candidatos; reporte de hoy, 2100
filas):

```
stage1 real recount:        {total: 2114, eligible: 2100, pending_review: 14,
                              track_stdio: 229, track_http: 1871, track_unknown: 14}
categorías del reporte real: {completed: 904, terminal: 1098, retryable: 98}
backlog recuperable (sin límite): stdio=1, http=97, total=98
nuevos (stage1 elegible sin fila en stage2): 0
```

**Hallazgo honesto que corrige una expectativa del plan de sesión**: el
plan estimaba "~1196 que fallaron hoy" + "14 de stage1 nunca alcanzados"
como el backlog a retomar. La cifra real es **98**, no ~1210 — porque
`terminal` (1098) nunca se reprocesa por diseño (I6: fail-closed no
significa "reintentar todo", significa "no descartar en silencio"; un
fallo determinista sigue siendo determinista al reintentarlo). Y los "14
nunca alcanzados" **no son** un hueco de cobertura: son las 14 entradas
`track_unknown` (transporte vacío/ambiguo), marcadas `pending_review` por
la etapa 1 y **correctamente excluidas** de stage2 por diseño (I1/I6) — no
candidatos elegibles a la espera, sino candidatos que requieren revisión
humana antes de siquiera intentar vetarlos. El mecanismo funciona como se
diseñó; la cifra citada en el plan de sesión anterior era una estimación
que no sobrevivió a la verificación fresca contra datos reales.

## C — Auto-adopción real: Cónclave convocado, resultado FAIL

### C.1 — Veredicto del Cónclave real

Convocado `deliberation_council.convene_for_decision` (
`scripts/council_mcp_auto_adopt_adr076.py`, red real vía `.env`,
`difficulty=Difficulty.HARD, risk="high", irreversible=True`) con el
contexto íntegro: cita verbatim de I5/I2-R arriba, el antecedente de que un
Cónclave real ya objetó ese mismo día forzando el diseño vigente de
ADR-075, el código real de los deciders, y la pregunta central **sin
prejuzgar**: ¿`mcp_auto_adopt_prevetted` debería mantener
`sensitivity="high"` (clic humano, con todo el escaneo ya hecho) o hace
falta bajarla?

**Trío real, 3/3 linajes distintos vivos** (`gemini_free`, `nvidia_glm`,
`nvidia_mistral_large` — sin el hueco EU que afectó al Cónclave previo de
ADR-075):

**VEREDICTO: FAIL** — las 3 voces objetan, sin excepción:

- **gemini_free** — `BLOCKING`: *"Esta propuesta es una afrenta directa a
  la gobernanza y la seguridad, un intento descarado de socavar decisiones
  recientes y principios fundamentales. Rompe la regla constitucional #4."*
- **nvidia_glm** — `MAJOR`: *"Rompe el invariante I5 ('Cero auto-adopción
  de tipos remotos ejecutables') y el principio de defensa en profundidad.
  Asume falsamente que un escaneo estático limpio (worst_severity=NONE)
  equivale a seguridad semántica probada. El antecedente del Cónclave del
  mismo día estableció explícitamente que el aislamiento de red no mitiga
  el tool-poisoning; un MCP ofuscado puede pasar el escaneo de metadatos y
  ejecutar lógica maliciosa en el sandbox, usando al LLM como canal
  encubierto. [...] Ignora el caso límite de dependencias dinámicas o
  living-off-the-land: un entry point con hash verificado y sin
  path-traversal puede invocar binarios del sistema legítimos de forma
  maliciosa, eludiendo el análisis estático. La exclusión propuesta para
  la pista http es cosmética; el riesgo semántico persiste intacto en la
  pista stdio."*
- **nvidia_mistral_large** — `MAJOR` (6 puntos, resumidos): rompe I5 y la
  regla constitucional #4 "por diseño" (la regla "no tiene cláusulas de
  escape"); el pipeline de vetting no es infalible (falsos negativos ante
  ofuscación avanzada, "limpio" ≠ "seguro"); caso límite de *race
  condition* entre auto-adopción y reversión manual de A3.3 sin analizar;
  la exclusión de http es arbitraria si I2-R aplica solo ahí; falta de
  diversidad geográfica de validación (mismo hueco EU señalado en
  ADR-075, ahora reformulado); flags opt-in son "notoriamente ignorados en
  producción" (cita Heartbleed/Log4j como precedente de defaults inseguros
  aceptados por conveniencia).

**Conclusión del panel** (síntesis, gemini_free): *"La propuesta socava
los invariantes no negociables de ADR-075 (I5, I2-R) y la regla
constitucional #4 sin una mitigación equivalente. [...] Requiere rediseño
para: mantener sensitivity='high' sin excepciones, o demostrar que los
riesgos residuales están cuantificados y aceptados por el Cónclave (no solo
por el pipeline actual)."*

Veredicto íntegro (JSON, las 3 voces completas) persistido en
`workspace/mcp/council_verdict_adr076.json` (gitignored, runtime) y
reproducible con `scripts/council_mcp_auto_adopt_adr076.py`.

### C.2 — Bifurcación aplicada

Por instrucción explícita del plan de sesión: objeción sustantiva
(BLOCKING + MAJOR + MAJOR, 3/3 voces) → **C se queda sin implementar**.

- **No existe** `adopt_mcp_server_prevetted` en el código — nunca se
  escribió, no hay nada que apagar por flag.
- **No existe** ningún criterio de "limpio" (`_is_clean_prevetted_stdio`)
  en producción.
- **No existe** cola de revisión `auto_adopt_pending_review.jsonl`.
- `adopt_mcp_server` (`orchestrator.py:318`) **no se tocó** —
  `sensitivity="high"` sigue siendo el único camino, sin excepción, exacto
  como antes de esta sesión.
- `ATLAS_MCP_AUTO_ADOPT` no es una variable de entorno leída por ningún
  código: no hay un flag "apagado por defecto" que documentar, porque la
  capacidad que gatearía simplemente no se construyó.

### C.3 — Objeciones concretas que cualquier reintento futuro debe resolver

Antes de volver a proponer esto, el reintento debe responder punto por
punto (no reformular la misma propuesta con distinto nombre):

1. `worst_severity=NONE` en análisis estático **no** implica ausencia de
   *tool-poisoning* semántico — el antecedente del Cónclave de ADR-075 ya
   estableció que el LLM vivo es un canal encubierto que ningún sandbox de
   red detiene.
2. Un entry point con hash verificado puede invocar binarios del sistema
   legítimos de forma maliciosa (*living-off-the-land*) — el análisis
   estático de fuente no cubre este caso.
3. La activación reversible (A3.3) no tiene análisis de *race condition*
   entre adopción automática y reversión humana — falta antes de asumir
   que "reversible" implica "seguro mientras tanto".
4. Excluir solo `http` de la auto-adopción mientras se permite `stdio` es
   arbitrario si el argumento es "el riesgo semántico no depende del
   transporte" — el panel señala que la distinción no está respaldada por
   evidencia técnica propia, más allá de "http no tiene fuente que leer".
5. Un flag opt-in por defecto apagado no es, por sí mismo, mitigación
   suficiente para una excepción a un invariante constitucional — el panel
   pide que cualquier rediseño futuro demuestre por qué el flag no
   degenera en "checkbox de compliance" bajo presión operativa.

## Consecuencias

- El operador tiene hoy re-siembra + vetting continuos reales (A+B), que es
  la mayor parte del valor pedido: el catálogo se mantiene solo y el
  backlog avanza en lotes sin intervención manual.
- La adopción de cualquier server MCP —incluso uno que pase el pipeline
  completo limpio— sigue exigiendo el mismo clic humano explícito que
  antes de esta sesión. Esto no es una limitación temporal a resolver en
  el próximo ciclo: es el resultado de someter la pregunta al mecanismo de
  gobernanza que el propio operador pidió usar, con un veredicto unánime
  y sin hueco de diversidad.
- Si en el futuro se quiere retomar C, el punto de partida no es "volver a
  convocar el Cónclave con el mismo contexto" (ya se hizo, con diversidad
  completa) sino resolver las 5 objeciones concretas de C.3 con diseño
  nuevo, o aceptar explícitamente el riesgo residual a nivel operador
  humano (fuera del alcance de cualquier Cónclave — esa decisión, a
  diferencia de esta, si el operador quisiera tomarla personalmente y por
  escrito, no requeriría nueva deliberación).
