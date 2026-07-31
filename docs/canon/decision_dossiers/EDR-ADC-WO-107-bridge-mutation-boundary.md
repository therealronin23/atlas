# EDR-ADC-WO-107 — Atlas API bridge (7341) mutation boundary

**Decision:** ADC-WO-107
**Program:** P08 (OS bridge / GOVERNANCE_KERNEL)
**Evidence state:** `PROVISIONAL`
**Decision disposition authority:** `docs/canon/decision_registry.jsonl`

## Question

ADR-058 y ADR-071 fijan el puerto 7341 como una proyección **read-only**
("JAMÁS Orchestrator dentro" — ver memoria de sesión
`atlas-os-foundation-2026-07-10.md`). El servidor real expone hoy 21 rutas
POST. ¿Se autoriza formalmente una API mutante gobernada, o se restaura el
límite read-only estricto retirando/reescribiendo las rutas que mutan?

## Constraints

- Golden Route preserva la aprobación humana antes de cualquier efecto.
- Alta sensibilidad exige humano o denegación, nunca auto-aprobación.
- El Orchestrator nunca debe instanciarse dentro del proceso del bridge
  (invariante explícito de ADR-058, reafirmado en `permissions_pending`:
  *"Nunca instancia ni importa nada bajo core/orchestrator_parts (OS-R1)"*).

## Evidencia observada — inventario medido de las 21 rutas POST

Medido leyendo cada handler, no inferido. Tres ficheros:
`src/atlas/api/server.py` (7), `src/atlas/api/product_routes.py` (13),
`src/atlas/api/coding_server.py` (1).

| Ruta | Fichero | Categoría | Evidencia |
|---|---|---|---|
| `/memory/import` | server.py | **MUTA estado real** | Escribe registros de memoria a disco, emite eventos con `simulated=False` explícito |
| `/intent` | server.py | Simulado | Pipeline entero marcado `simulated_pipeline: True`/`simulated: True`, solo emite eventos de traza |
| `/simulate` | server.py | Solo lectura | Reproduce un fixture `.jsonl` ya existente, no escribe nada nuevo |
| `/connectors/{id}/test` | server.py | Bajo riesgo | Solo emite un evento de log (`connector.connected`); sin mutación de estado gobernado |
| `/connectors/{id}/sync` | server.py | Bajo riesgo (stub) | Emite eventos start/finish; `"items": 0` hardcodeado — la sincronización real no está implementada |
| `/permissions/evaluate` | server.py | Bajo riesgo | Solo emite un evento de auditoría (`permission.evaluated`); no aprueba, deniega ni ejecuta nada |
| `/permissions/pending/{task_id}/approve` | server.py | **MUTA estado real — vía CLI aparte** | `subprocess.run([sys.executable, "-m", "atlas.interfaces.cli", "approve", task_id])` (línea 917), que internamente llama a `orch.approve_pending()`. Documentado explícitamente como el camino a real que sustituye un no-op previo. Al menos respeta la separación de proceso que exige ADR-058 |
| `/connections/plan` | product_routes.py | Solo lectura | Devuelve una receta ya existente vía `concierge.plan()`, no persiste nada |
| `/connections/test` | product_routes.py | Bajo riesgo | Prueba conectividad (posible efecto EXTERNO según `mode`), sin escritura de estado propio de Atlas visible |
| `/connections/credential-reference` | product_routes.py | **MUTA estado real (con guardas)** | `auth_broker.create_env_reference()` registra el NOMBRE de una variable de entorno, nunca el secreto — rechaza explícitamente cualquier valor con pinta de secreto (`SecretRejected`) |
| `/business/onboarding/start` | product_routes.py | **MUTA estado real** | `session_store.save(session)` |
| `/business/onboarding/answer` | product_routes.py | **MUTA estado real** | `session_store.save(session)` |
| `/business/onboarding/confirm_answer` | product_routes.py | **MUTA estado real** | `session_store.save(session)` |
| `/business/onboarding/skip` | product_routes.py | **MUTA estado real** | `session_store.save(session)` |
| `/business/onboarding/preview` | product_routes.py | **MUTA estado real** | `session_store.save(session)` (incluso una "preview" persiste) |
| `/business/onboarding/confirm` | product_routes.py | **MUTA estado real** | `session_store.save(session)` |
| `/business/core/draft` | product_routes.py | **MUTA estado real** | `business.create_draft(...)` |
| `/business/core/request-activation` | product_routes.py | **MUTA estado real** | `business.request_activation(...)` |
| `/business/core/activate` | product_routes.py | **MUTA estado real — SIN separación de proceso** | `business.approve_activation(req.business_core_id, _server_identity(request), ...)`. Es una acción de APROBACIÓN completa (identidad del aprobador incluida) ejecutada **directamente dentro del proceso del bridge**, sin la indirección vía CLI que sí tiene `/permissions/pending/.../approve`. Es el caso más severo del inventario: viola el invariante "Orchestrator/lógica de aprobación jamás dentro del bridge" sin ni siquiera la mitigación de separación de proceso |
| `/business/core/reject` | product_routes.py | **MUTA estado real — SIN separación de proceso** | Mismo patrón que `activate`, decisión de rechazo directa en proceso |
| `/v1/chat/completions` | coding_server.py | Compute passthrough | Llama a `InferenceHub.infer_for_role()` — un efecto externo real (coste de tokens, llamada de red a un proveedor), pero no muta estado gobernado propio de Atlas (task/mission/business) |

**Resumen del recuento:** de 21 rutas POST, **13 mutan estado real gobernado**
de forma persistente. De esas 13, **11 lo hacen directamente en el proceso del
bridge sin ninguna separación** (todas las de onboarding + business/core +
`credential-reference` + `memory/import`); solo **1** (`permissions/approve`)
respeta la separación de proceso vía CLI que ADR-058 exige como mitigación
mínima. **2 de las 13** (`business/core/activate` y `.../reject`) son además
acciones de **aprobación/gobernanza** ejecutadas sin esa separación — el caso
más grave: es justo el tipo de decisión (aprobar activación de un negocio, con
identidad del aprobador) que el invariante de ADR-058 nombra explícitamente
como prohibido dentro del bridge.

## Alternativas comparadas

1. **Autorizar formalmente una API mutante gobernada.** Reconoce el estado
   real (13/21 rutas ya mutan) y permite invertir el esfuerzo en cerrar las
   dos brechas de proceso (`business/core/activate`/`reject`) con la misma
   indirección que ya tiene `permissions/approve`, en vez de mantener una
   ficción de "read-only" que el propio código contradice. Costo: reescribir
   ADR-058/071 explícitamente, y decidir qué autenticación/auditoría exige
   cada ruta mutante (hoy ninguna tiene autenticación visible en el código
   leído).
2. **Restaurar el límite read-only estricto.** Retirar o mover fuera del
   bridge las 13 rutas mutantes (probablemente a un servicio aparte con su
   propia superficie de auth), dejando 7341 como proyección pura. Costo:
   romper el flujo de producto actual (onboarding, business core, aprobación
   de tasks) que ya depende de estas rutas — no es un cambio de documentación,
   es una migración de arquitectura real.

Sin recomendación de este dossier entre las dos: es exactamente la decisión de
apetito de riesgo que le corresponde al operador, no a mí.

## Decisión del operador — 2026-07-31 (ninguna de las dos alternativas tal cual)

Ni 1 ni 2 puros: una **tercera vía acotada**, registrada en ADR-080
(`docs/decisions/adr/adr_080_product_os_mutation_scoped_exception.md`).

Al preparar la alternativa 2 (restaurar read-only) para ejecutarla, la
lectura completa de `product_routes.py` mostró que las 13 rutas mutantes
NO son un añadido marginal: son la superficie completa del Product OS
(Fase 15) — retirarlas habría sido una regresión de producto real, no una
corrección de seguridad acotada. Ese hallazgo se corrigió en vivo con el
operador antes de tocar código (ver WORK_LEDGER.md 2026-07-31).

Decisión final: las 19 rutas que crean/actualizan estado de producto bajo
autenticación real (`authenticate_http`) quedan intactas — no son el
hallazgo que motivó ADC-WO-107. Se cierra exclusivamente el gap más grave
identificado arriba: `business/core/activate`/`reject` ejecutando una
aprobación gobernada sin la separación de proceso que
`permissions/approve` sí tiene. Como `BusinessCoreEngine` no es
Orchestrator, replicar el subproceso CLI textualmente no aplicaba (OS-R1
es específicamente sobre no doblar Orchestrator); en su lugar, ambas
rutas ahora escriben un receipt Merkle verificable en la misma cadena que
el resto de Atlas (`business_core.activated`,
`business_core.activation.rejected`), igualando la altura de auditoría
sin tocar el patrón de proceso.

Implementación: `src/atlas/api/server.py` (`create_app(merkle_dir=...)`),
`src/atlas/api/product_routes.py` (`register_product_routes(..., merkle=...)`),
TDD real (RED confirmado — `TypeError: unexpected keyword argument
'merkle_dir'` — antes de escribir producción),
`tests/test_os_product_api.py::test_business_core_activate_writes_merkle_receipt`
y `::test_business_core_reject_writes_merkle_receipt`, mypy limpio en los
3 ficheros tocados.

## Confidence and limits

**Confidence:** alta en el inventario (medido, no inferido — cada fila cita la
línea/función real). Media en el impacto de migrar: no medí cuántos clientes
reales (UI, tests, scripts) dependen hoy de las 13 rutas mutantes.

**Falsifier:** si se demuestra que ninguna de las 13 rutas mutantes está en el
camino de producción activo (todas detrás de flags apagados / solo usadas en
demos), la alternativa 2 (restaurar read-only) se vuelve mucho más barata de
lo que este dossier asume.

**Revisit triggers:** cualquier incidente de seguridad con el bridge expuesto
más allá de `127.0.0.1`; cualquier cambio que añada autenticación real a estas
rutas (cambiaría el cálculo de riesgo).

## Security and rollback

Ninguna ruta de las 21 fue tocada para producir este dossier — es puramente
observacional. Rollback: N/A (no hay cambio que revertir).

## Evidencia

Líneas citadas arriba, verificadas por lectura directa el 2026-07-31:
`src/atlas/api/server.py:611,673,704,720,733,763,897`,
`src/atlas/api/product_routes.py:252,259,263,311,320,332,342,352,362,374,403,413,428`,
`src/atlas/api/coding_server.py:81`.
