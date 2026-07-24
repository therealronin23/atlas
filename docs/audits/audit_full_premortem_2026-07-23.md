# Audit + premortem — segunda pasada del día (post-cierre de los 14 hallazgos)

Fecha: 2026-07-23. HEAD al arrancar: `7682c2a` (limpio).
Nodo matrioska: código dormido/fallbacks silenciosos + drift documental +
infraestructura en vivo, transversal al repo.
Tipo: 2, foundational/correctness. Contexto: hoy mismo ya se cerró una
auditoría crítica con 14 hallazgos (ver `WORK_LEDGER.md`, doc drift,
StubEmbedder silencioso, timeout roto, Hermes mock, daemon SIGABRT, ramas
muertas, /tmp lleno). Esta auditoría es la segunda pasada del mismo día,
pedida explícitamente por el operador ("auditoría completa con premortem...
usa todo lo que te haga falta"), usando el tronco MCP, el grafo vivo del
proyecto y 3 agentes de exploración en paralelo — barriendo lo que la
primera pasada no cubrió, sin repetir hallazgos ya cerrados.

## Verificación ejecutada

- `atlas reality --json`: `status: ok`, `strict_failures: []`, Merkle OK
  (8277 registros), grafo `FRESH` (HEAD `7682c2a`), 302 ficheros fuente / 329
  de test.
- `trunk_invoke_readonly(graph_overview)`: 273 módulos, hubs por fan-in
  (`merkle_logger` 45, `inference_hub` 27, `contracts` 27, `verify` 19,
  `embeddings` 16, `events.schemas` 15, `ssrf_bridge` 15, `mcp.catalog` 14,
  `lesson_store` 13, `router.cascade` 12) — usados para priorizar dónde
  buscar código dormido.
- 3 agentes Explore en paralelo, solo lectura: (1) `docs/backlog.yaml` vs
  código real, (2) código dormido/fallbacks silenciosos en los hubs, (3)
  salud de infraestructura en vivo (systemd, daemon, /tmp, memoria).
- Verificación personal del hallazgo #1: re-ejecuté
  `Orchestrator.handle_intent("desktop windows")` contra Xvfb `:99` real con
  `xclock`+`xcalc` corriendo, y `wmctrl -l` sobre el mismo display.
- `pytest tests/acceptance/test_t3_1_desktop_operator_e2e.py -v` antes y
  después del fix: `3 passed` (falso-verde) → `2 passed, 1 xfailed` (honesto).
- `pytest tests/test_lesson_store.py tests/test_lesson_store_stats.py
  tests/test_merkle_logger_tail.py tests/test_merkle_logger_signing.py -q`:
  `40 passed` tras añadir logging.
- `mypy src/atlas/logging/merkle_logger.py src/atlas/core/lesson_store.py
  src/atlas/core/orchestrator_parts/maintenance_facade.py`: limpio.
- `yaml.safe_load(docs/backlog.yaml)`: válido, 75 ítems tras añadir 2 nuevos.

## Hallazgos principales (orden de severidad)

1. **[CRÍTICO] Claim falsa en el propio cierre de auditoría de hoy.**
   `WORK_LEDGER.md` (entrada de hoy, t3-1) afirma que `list_windows` "ve las
   2 apps" en Xvfb `:99`. Falso: re-ejecutando el mismo camino real, el
   resultado es `structuredContent.result = []` — lista vacía. Causa raíz:
   Xvfb `:99` no tiene gestor de ventanas; `computer-control-mcp` depende de
   `_NET_CLIENT_LIST`/EWMH (`wmctrl -l` confirma: "Cannot get client list
   properties"). El test
   `tests/acceptance/test_t3_1_desktop_operator_e2e.py::test_list_windows_sees_two_real_desktop_apps`
   pasaba con `assert len(str(windows)) > 0` — trivialmente cierto incluso
   para la lista vacía serializada. Es exactamente el tipo de falso-verde
   que una auditoría con premortem existe para cazar: el propio texto del
   test decía "si no ve ninguna ventana, el test debe fallar", y no fallaba.

2. **[ALTO] Subsistema de seguridad completo, implementado y dormido.**
   `DriftTripwire` (`src/atlas/security/drift.py:257`, docstring: "GATEA
   escalada al shadow router") y `ShadowRouter`
   (`src/atlas/security/shadow_model.py:177`) — con invariantes OSM-010/
   OSM-028 referenciados en el propio código — están completamente testeados
   (`tests/test_drift.py`, `tests/test_shadow_model.py`,
   `tests/test_transparency_gateway.py`) pero nunca instanciados en
   producción. El único `TransparencyGateway` real
   (`src/atlas/core/orchestrator.py:1267`) no pasa `shadow_router=`; el
   shadow routing en `gateway.py:184` es explícitamente opt-in
   (`if self._shadow_router is not None`) y ningún caller real calcula
   `confidence=`/`monitor_cause=`. Cero protección efectiva hoy.

3. **[MEDIO-ALTO] `EvolutionGate`/`run_item_with_evolution` dormido.** El
   ciclo real de mantenimiento (`maintenance_facade.py:441`) llama a
   `runner.run_item(item)` (ruta plana), nunca a
   `run_item_with_evolution()` (`self_build_runner.py:415`). El propio
   docstring de `evolution_gate.py:9-13` tiene un TODO desactualizado ("el
   cableado... es la SIGUIENTE tarea") que ya no es cierto — el cableado
   técnico existe, solo que nadie en el camino real lo invoca.

4. **[MEDIO] Fallback silencioso en el propio log de auditoría Merkle.**
   `src/atlas/logging/merkle_logger.py` no importaba `logging`; `read_all()`,
   `tail()` y `_load_last_hash()` tragaban excepciones (`except Exception:
   continue`) sin ningún log. `_load_last_hash()` corre al arrancar — si una
   línea está corrupta tras un crash (recordando el historial de SIGABRT ya
   documentado hoy), el cómputo de la cadena de hashes la ignoraba en
   silencio. Contraste: `verify_chain()` sí reportaba el fallo
   explícitamente — la asimetría era el problema.

5. **[MEDIO] Mismo patrón en `LessonStore`.**
   `src/atlas/core/lesson_store.py:208-209`, `all()`: `except Exception:
   continue` sin log — un fichero de lección corrupto desaparecía
   silenciosamente de `all()`/`by_provenance()`, incluyendo lecciones
   adversariales de seguridad.

6. **[BAJO-MEDIO] Doc drift no capturado en la primera pasada de hoy.**
   `docs/design/atlas_ecosystem_map.md` (fila "Desktop-control") seguía en
   `PENDIENTE` con evidencia vieja, sin reflejar el wiring real de hoy ni el
   hallazgo #1.

7. **[BAJO] Gap de gobernanza.** `src/atlas/mcp/adapter_registry.py`
   (backlog `t3-3-harness-adapter-contract-registry`, `done`) tiene 0
   callers de producción (solo tests) y no aparecía en la tabla
   "Zero-Importer Triage Snapshot" pese a que la regla operativa del propio
   documento lo exige.

8. **[BAJO] TODO desactualizado.** `maintenance_facade.py:308` describía un
   estado ("BenchmarkGate no cableado") que ya no era cierto desde el
   2026-07-10 (línea 1046 del mismo fichero ya lo documentaba cableado).

9. **[SEÑAL EN VIVO, no bug de código] Presión de recursos real durante
   esta sesión.** `free -h`: 6.3Gi/7.8Gi de swap en uso, load average 5.87 —
   el mismo patrón que causó cierres de escritorio en el pasado (memoria
   `desktop-crashes-root-cause-2026-07-09`). Ningún servicio en crash-loop:
   `atlas-xvfb.service`, `hermes-gateway.service`, `atlas-tmp-sweep.timer`
   todos sanos (`NRestarts=0`). El daemon de autoconstrucción no es un
   proceso separado: corre embebido en `atlas-core.service`
   (`ATLAS_SELF_BUILD=1`, `ATLAS_SELF_BUILD_LEVEL=L2`), 107 ticks con huella
   real hoy.

10. **[SIN RESOLVER, bajo impacto] Carpeta huérfana de /tmp del ledger.**
    `WORK_LEDGER.md` menciona una carpeta de 1.4G "de ayer" pendiente de OK
    del operador para borrar. No localizada hoy con ese tamaño/fecha exacto;
    `/tmp` está al 44% (1.8G/4G) tras el sweep automático de hoy (que bajó de
    90% a 44%). Puede haber sido barrida ya, o el path original ya no existe.
    No bloqueante — se deja constancia para que el operador confirme.

## Premortem

Escenario de fallo compuesto (el peligroso, no un bug aislado): dentro de
unas semanas, una sesión con comportamiento adversarial real dispara
`DriftTripwire` — pero como `ShadowRouter` nunca se conectó (#2), no hay
ninguna escalada real, solo el detector corriendo en el vacío. Al mismo
tiempo, el daemon sufre un crash (mismo patrón SIGABRT histórico, causa raíz
nunca cerrada al 100%) a media escritura del log Merkle — y como
`_load_last_hash()`/`read_all()` tragaban la línea corrupta en silencio (#4,
ya corregido en esta pasada), la cadena de auditoría habría perdido
exactamente la evidencia necesaria para reconstruir qué pasó. Si además el
incidente involucra el operador desktop (#1), un test "verde" daba falsa
confianza de que `list_windows` funciona cuando en realidad no ve nada — ni
se detecta el problema, ni queda rastro fiable, ni el test lo habría
atrapado. Es un triple punto ciego: la defensa no actúa, el log no lo
registra, y el test no lo habría revelado.

Riesgo secundario: seguir apilando features de auto-mejora (#3,
`run_item_with_evolution`) sin cablearlas invita a repetir el mismo patrón
de "código dormido creyéndose activo" que ya causó 2 de los 14 hallazgos de
la primera pasada de hoy (StubEmbedder, doc drift).

## Plan de recuperación

### Arreglado en esta misma pasada (pequeño, barato, sin riesgo arquitectónico)

1. **#1**: aserción del test corregida a verificación real de contenido
   (`_extract_window_list` + `assert len(window_list) >= 2`); marcado
   `@pytest.mark.xfail(strict=True)` con la causa raíz documentada en el
   propio test — falla honesto en vez de falso-verde, y si algún día empieza
   a pasar de verdad (WM instalado), `strict=True` lo señala como XPASS
   inesperado obligando a retirar el marcador.
2. **#4**: `logger.warning(..., exc_info=True)` añadido en los 3 puntos de
   `merkle_logger.py` que tragaban excepciones (import `logging` añadido).
3. **#5**: mismo tratamiento en `lesson_store.py:208-209`.
4. **#6**: fila "Desktop-control" de `atlas_ecosystem_map.md` actualizada con
   el estado real de hoy + el hallazgo #1.
5. **#7**: `mcp/adapter_registry.py` añadido a la tabla "Zero-Importer
   Triage Snapshot" (clasificado `PARK`).
6. **#8**: TODO desactualizado de `maintenance_facade.py:308` corregido para
   reflejar que `BenchmarkGate` ya está cableado.

Verificación agregada: `pytest` de los ficheros tocados (`40 passed` en
lesson_store/merkle_logger, `2 passed + 1 xfailed` en el acceptance de
desktop) + `mypy` limpio en los 3 ficheros de producción tocados +
`yaml.safe_load` limpio sobre `backlog.yaml`.

### Registrado para decisión del operador (grande, arquitectónico — no cableado en silencio)

- **#2**: nuevo ítem `t1-shadow-router-drift-wiring-decision` en
  `docs/backlog.yaml` (priority 1) — requiere Cónclave antes de tocar el
  camino de producción real (cambia el comportamiento de todas las
  sesiones).
- **#3**: nuevo ítem `t1-evolution-gate-wiring-decision` en
  `docs/backlog.yaml` (priority 2) — decisión de coste/beneficio, no
  requiere Cónclave completo pero sí registro razonado.
- **#9**: anotado en `WORK_LEDGER.md` como señal viva a vigilar, sin acción
  automática (no hay causa raíz nueva que arreglar hoy).
- **#10**: dejado anotado arriba como no resuelto; se pide al operador el
  path original si lo recuerda.

## Estado actual

Los 6 hallazgos "arreglar ahora" están cerrados con evidencia (tests +
mypy + yaml válido). Los 2 hallazgos arquitectónicos (#2, #3) están
registrados en `docs/backlog.yaml` como decisiones explícitas pendientes del
operador, no cableados en silencio — consistente con la política de este
proyecto de "arreglar si es pequeño, decidir si es grande"
(`feedback-detect-and-fix-dormant-vs-track`, memoria del operador). Las dos
señales operativas (#9 presión de recursos, #10 carpeta huérfana) quedan
documentadas sin acción automática, a la espera de que el operador las vea.

Ningún cambio de esta pasada tocó comportamiento de producción: son 3 fixes
de logging/test (sin cambiar rutas de ejecución), 2 correcciones de
documentación, y 2 registros de backlog puros.

## Addendum (misma tarde, tras revisar con el operador)

El operador pidió: diagnóstico completo del hallazgo #2, activación real del
#3, e instalación del WM para cerrar el #1. Resultado:

- **#2 diagnosticado a fondo** (no solo re-flaggeado): confirmado que sigue
  el proceso propio de "membrana" (`docs/membrana/OSM-000_membrana.md`) —
  nunca hubo promoción formal a ADR canónico, por eso nunca se instanció en
  producción. Cadena exacta: el commit `f377ea3` (2026-06-18) solo añadió el
  mecanismo opt-in dentro de `TransparencyGateway`; el único caller real
  (`orchestrator.py:1267`) nunca pasa `shadow_router=`, y el único invocador
  de `.call()` (`inference_hub.py:595`) nunca pasa `confidence=`. Dos wirings
  faltan, no uno. Sigue `pending`, ahora con el diagnóstico completo en
  `docs/backlog.yaml`.
- **#3 activado con Groq real**: `openevolve` instalado, `_build_evolution_gate()`
  nuevo en `maintenance_facade.py`, `run_item_with_evolution` ahora se invoca
  de verdad en el ciclo real cuando `GROQ_API_KEY` está presente. Daemon
  reiniciado. `t1-evolution-gate-wiring-decision` → `done`.
- **#1**: no pude instalar `fluxbox` yo mismo (sudo requiere TTY interactivo);
  operador debe correr `sudo apt-get install -y fluxbox`. El cambio del unit
  systemd (arrancar fluxbox junto a Xvfb) ya está preparado para aplicar en
  cuanto el paquete esté instalado.
- **#10 confirmado resuelto**: carpeta huérfana ya no existe bajo ningún
  tamaño/fecha compatible.
- **Verificación de completitud pedida por el operador**: corrí
  `scripts/sanitation_audit.py` (el radar propio del proyecto) en vez de
  fiarme solo del muestreo de los agentes Explore. Encontró 4 módulos
  genuinamente sin clasificar: `business/legacy.py`, `events/core_bridge.py`,
  `fabric/connectors/gmail.py` (posible candidato a retirar — quizás
  superado por el MCP `google-workspace` externo) y `security/node_identity.py`
  (ya documentado como standalone por diseño, solo faltaba en esta tabla).
  Los 4 clasificados; el radar corre ahora limpio (`✓ ningún módulo
  huérfano`). También detectó housekeeping menor NO atacado hoy por estar
  fuera de alcance (22 ADRs sin fila en el ecosystem map, 212 docs sin
  enlaces entrantes, wikilinks rotos en `docs/membrana/`, 2 cuarentenas
  vencidas) — nada de esto es correctness, es deuda documental rutinaria.

Detalle completo de esta ronda: `WORK_LEDGER.md` (entrada "3ª pasada del
día").
