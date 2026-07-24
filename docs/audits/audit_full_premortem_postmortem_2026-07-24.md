# Auditoría completa — premortem + postmortem del trabajo sin commitear del 2026-07-24

Fecha: 2026-07-24. HEAD: `7682c2a` (working tree **sucio**: 59 paths + 9 ficheros
nuevos, 55 457 inserciones). Auditor: sesión Opus, solo lectura salvo esta doc.
Alcance: el trabajo de las **7 pasadas Sonnet de hoy**, ninguna commiteada —
ADR-074 (activación ShadowRouter/DriftTripwire), Sentinel capas 5/6, cierre de
t3-1, evolution gate, workbench-compliance, y el re-seed masivo del catálogo MCP.

## Verificación ejecutada (evidencia real, no claims del ledger)

- `atlas reality --json`: `status: ok`, `strict_failures: []`, Merkle OK
  (8446 registros). Señales: `graph.project` **DIRTY** (el grafo no refleja el
  working tree — no se puede consultar para este diff), `hermes` mock,
  `llm.inference` degraded (sin claves en *este* entorno; el daemon sí las tiene).
- **292 tests dirigidos verdes** sobre TODAS las áreas tocadas, en 2 tandas
  (138 + 154), sin OOM: transparency_gateway, live_loop, gate_d_lazy_init,
  sentinel_gate, sentinel_revet_tick, gate_f_executor_fs, workbench_compliance,
  capability_route_hook_workbench, mcp_trial_tick, cli_connections_credential,
  os_fabric, os_product_api, agentic_executor_gaps, desktop_tool,
  mcp_registry_seed, mcp_trunk_aggregator, router_telemetry, spawn_trial,
  workbench_resources, y el acceptance `test_t3_1_desktop_operator_e2e`.
- **mypy limpio** en los 8 módulos de producción tocados (sentinel_gate,
  live_loop, gateway, inference_hub, orchestrator, workbench_compliance,
  gate_f_executor, maintenance_facade).
- Verificación personal del falso-verde de ayer (#1 de la auditoría 07-23):
  fluxbox **corre de verdad** con Xvfb `:99` (pids 3445754/3445772/3445756);
  el test ahora tiene aserción real (`assert len(window_list) >= 2`, con
  `_extract_window_list` desempaquetando la respuesta MCP cruda) y pasa porque
  el WM existe, no por serialización trivial. Falso-verde **genuinamente cerrado**.
- Journal de `atlas-core.service` desde 00:00 de hoy: **cero** error/traceback/
  SIGABRT. Daemon sano.

## Postmortem — qué pasó hoy (y salió bien)

1. **t3-1 universal GUI operator CERRADO.** El bloqueante era el falso-verde de
   `list_windows`; se instaló fluxbox (ayer) y se reescribió la aserción del
   test para verificar contenido real. Verificado arriba: real, no cosmético.
2. **Sentinel capas 5/6 cableadas + suelo IOC.** `_INCIDENT_IOC_DOMAINS` pasó de
   vacío a un suelo no-anulable con procedencia real (`giftshop.club`, backdoor
   Postmark MCP sept-2025, ADR-036). Corrige un hallazgo real: la Capa 2 (IOC)
   estaba marcada ✅ en ADR-038 pero **no bloqueaba nada** en producción porque
   `orchestrator.py` construye `SentinelGate` sin `ioc_domains`. Ahora el suelo
   se UNE (nunca reemplaza) con lo que inyecte el caller.
3. **ADR-074 — activación de ShadowRouter/DriftTripwire/GatedLessonRecorder.**
   Promoción formal de la membrana OSM-042 al núcleo, precedida de un Cónclave
   real (Gemini + GLM; Mistral EU dio 410 Gone — modelo EOL, registrado aparte).
   El trío votó **FAIL** contra la activación sin matices; se incorporaron las 3
   objeciones accionables: (a) `session_id` scopeado por `task_id`, (b)
   `threshold_passive=0.80` en prod (no el 0.65 de tests), (c) verifier del juez
   fail-closed que desvía rechazos a `pending_review.jsonl` en vez de envenenar
   `LessonStore`. **Wiring verificado real en el camino de producción**:
   `orchestrator.enable_gate_d_pipeline()` (línea 1194+) construye los 4 objetos
   y los pasa al gateway; auto-invocado cuando `ATLAS_PIPELINE_GATE_D=1`, que
   **está en `.env`**. No es dormido en el código.
4. **Evolution gate + workbench-compliance hook + re-seed del catálogo** (50
   páginas del registro MCP oficial → ~57k líneas máquina-generadas, todo
   "candidato"; legítimo, ver `mcp_seed_registry.py` paginando).

El patrón del día es sano: cada activación grande pasó por Cónclave o por un
registro razonado, con las salvaguardas que salieron de las objeciones — no
"cablear en silencio". Los tests y mypy respaldan las claims.

## Premortem — dónde está el riesgo (escenario compuesto)

### [ALTO] El daemon vivo corre código STALE — la "activación" aún no es efectiva

El proceso `atlas serve` (pid 3438315) arrancó **jul 23 22:34:35**. Las ediciones
de activación de hoy son de **01:40–01:44 jul 24** (~3 h más nuevas). Python
importa los módulos al arrancar: el proceso vivo **no tiene cargado** el
ShadowRouter de ADR-074, ni Sentinel 5/6, ni los cambios de gate_f. Y como el
trabajo tampoco está commiteado, **HEAD (`7682c2a`) también carece de él** — los
worktrees efímeros del self-build (que hacen checkout de HEAD) tampoco lo ven.

Consecuencia: la frase de cabecera de ADR-074 —"primera vez que ShadowRouter
procesa tráfico real"— **todavía no es cierta en el proceso en ejecución**. Es
exactamente la misma familia que el hallazgo #2 de ayer ("código dormido
creyéndose activo"), un nivel más arriba: aquí el código no está dormido, pero
el *proceso* que debería ejercitarlo está corriendo la versión anterior. La
defensa que se activó hoy no está protegiendo nada hasta commit + reinicio del
daemon.

### [MEDIO] Un día entero de trabajo en un solo working tree sucio, sin commitear

59 paths + 9 ficheros nuevos, 7 pasadas. Un crash o un `git` mal dado pierde
todo. Además el diff está dominado por ~57k líneas de catálogo máquina-generado
que **entierran** los ~2k de código y seguridad reales (ADR-074, Sentinel) —
imposible de revisar como un commit único. El escenario peligroso: se commitea
todo junto, el catálogo esconde una regresión real en la revisión, y nadie la ve.

### [BAJO] Suelo IOC de comandos vacío (asimetría con dominios)

`_INCIDENT_IOC_COMMANDS = frozenset()` sigue vacío mientras el de dominios ya
tiene suelo. Defendible (no hay comando confirmado-malicioso que sembrar), pero
la asimetría conviene dejarla explícita para que no se lea como olvido.

### [SEÑAL VIVA] Presión de recursos (heredada de ayer)

Swap alto persiste (memoria `desktop-crashes-root-cause-2026-07-09`). No hay
crash-loop; se vigila, no se actúa.

## Escenario de fallo compuesto (el peligroso)

Se commitea el día entero en un commit gigante; el catálogo de 57k líneas oculta
en la revisión una regresión; el daemon nunca se reinicia, así que la "defensa
activa" de ADR-074 sigue sin ejercitar tráfico real; y si en ese hueco llega
contenido hostil por web/MCP (el modelo de amenaza real que anotó el juez del
Cónclave), no hay ni ShadowRouter escalando, ni Sentinel 5/6 vetando, ni rastro
en `pending_review.jsonl` — porque todo eso vive en un working tree que el
proceso en ejecución no ha cargado. Triple punto ciego repetido: la defensa
existe, pasa los tests, y aun así no está en línea.

## Recomendaciones (decisión del operador — nada tocado en silencio)

1. **Commit dividido**, no monolítico: (a) datos — re-seed del catálogo MCP;
   (b) seguridad/código — ADR-074 + Sentinel 5/6 + evolution gate; (c) docs —
   ledger/backlog/ecosystem. Así la revisión ve el código sin el ruido del YAML.
2. **Reiniciar `atlas-core.service`** tras commitear, para que la activación de
   ADR-074/Sentinel deje de ser stale y empiece a ejercitar tráfico real —
   condición necesaria para que la claim de cabecera del ADR sea verdad.
3. Anotar la asimetría del suelo IOC de comandos como decisión consciente.

## Estado

Trabajo de hoy: **sólido y verificado** (292 tests + mypy + falso-verde real
cerrado + wiring real confirmado en el camino de producción). El riesgo no está
en la *calidad* del código sino en su *liveness*: ni commiteado ni cargado en el
proceso vivo. Ninguna acción irreversible tomada por esta auditoría — solo esta
doc; commit y reinicio quedan para el operador.
