# Mapa de autoridad — Mission, Task, Orchestrator, Policy, Evidence

<!-- Doc interno de diseño. Cierra ADC-WO-102 (P03). -->

**Estado**: medido y vigilado en código el 2026-08-11.
**Ficha**: `ADC-WO-102` — *Decide durable Mission, Task, and orchestration authority*.
**Decisión previa**: `EDR-ADR-069` (2026-07-31) acepta `SELECTIVE_DURABLE_HISTORY`.
**Guardia**: [`tests/test_authority_single_writer.py`](../../tests/test_authority_single_writer.py).

La ficha pide *"un dueño por estado mutable"* y nombra tres riesgos: `dual
writers`, `bypassed approval gates` e `incompatible persisted state`. Este
documento dice quién es el dueño de cada estado **medido sobre el código**, no
sobre la intención. Lo que aquí se afirma tiene un test que falla si deja de
ser verdad; lo que no se puede vigilar en código está marcado como tal.

## Resumen: seis estados mutables, seis dueños

| Estado mutable | Dueño | Vigilado por |
|---|---|---|
| `Task.status` (en memoria) | `Task.transition()` — `core/contracts.py:112` | `test_solo_transition_escribe_el_estado_de_un_task` |
| Sobre HMAC del pendiente (contenido) | `TaskPersistence.persist()` | `test_solo_task_persistence_construye_el_sobre_hmac` |
| Directorio de la cola HITL (entradas) | `TaskPersistence` | `test_solo_task_persistence_muta_ficheros_de_la_cola` + `..._no_tiene_vocabulario_de_ficheros` |
| Reserva de ejecución (`<id>.executing.json`) | `TaskPersistence.reserve_execution/release_execution` | idem |
| Registro en memoria de pendientes | `ApprovalManager._pending` (bajo `threading.Lock`) | — (interno a la clase) |
| Clearance `task:<id>` | `PermissionProfile` — concedido en **dos** sitios declarados | `test_el_clearance_de_una_tarea_solo_lo_conceden_los_dos_declarados` |

## 1. `Task.status` — la máquina de estados es el único camino

`Task` (`core/contracts.py`) declara `VALID_TRANSITIONS` y expone
`transition(new_status)`, que **rechaza** cualquier salto no declarado. Medido
sobre todo `src/atlas`: no existe ni una asignación directa a `task.status`
fuera de dos sitios.

| Sitio | Por qué es legítimo |
|---|---|
| `Task.transition()` — `contracts.py:119` | Es la máquina de estados. |
| `TaskPersistence.deserialize()` | **Rehidratar no es transicionar.** El estado ya ocurrió antes de que el proceso muriera; pasarlo por `transition()` lo rechazaría, porque el objeto recién construido está en `PENDING`. Es la única excepción y está nombrada, no escondida. |

Los 31 puntos de transición del pipeline (`orchestrator.py`,
`pipeline_runner.py`, `approvals.py`, `agentic_executor.py`) llaman todos a
`transition()`. Eso es lo que hace que "estado persistido incompatible" sea
detectable: un estado imposible no puede escribirse en primer lugar.

**Nota de instrumento:** un `grep` de `.status =` marca `provider.status`
(`inference_hub`), `proposal.status` (`cold_update_manager`) y `report.status`
(`self_audit`) — tres estados con otros dueños. El guardia usa AST y distingue
el objeto y el valor asignado; con `grep` la regla mentiría.

## 2. El estado persistido — un solo escritor, y ahora también un solo dueño del directorio

Hay **dos** cosas distintas que se suelen confundir:

- **el contenido del sobre**: `TaskPersistence.persist()` es el único que llama
  a `wrap_task_payload()`. Un segundo fabricante podría producir ficheros que
  `load()` aceptara como legítimos sin haber pasado nunca por aquí — de ahí que
  esté vigilado.
- **las entradas del directorio**: aquí es donde la ficha **no se cumplía**.

### Lo que estaba mal, y se arregló hoy

`ApprovalManager` construía a mano las rutas del directorio de
`TaskPersistence` y hacía el baile de la reserva:

```python
pending_path   = self._dir / f"{task_id}.json"
executing_path = self._dir / f"{task_id}.executing.json"
pending_path.replace(executing_path)     # reservar
executing_path.unlink(missing_ok=True)   # soltar
pending_path.unlink(missing_ok=True)     # descartar
```

Dos módulos manipulando las mismas rutas es exactamente `dual writers`, aunque
el sobre lo escribiera uno solo: el segundo escritor podía dejar el directorio
en un estado que el primero no sabe producir ni reparar.

Ahora `TaskPersistence` expone la operación por su nombre —
`is_executing()`, `has_pending()`, `reserve_execution()`,
`release_execution()`, `release_lock()` — y `ApprovalManager` **no importa
`os`, `fcntl` ni `pathlib`**. No es que no deba tocar disco: es que no tiene
con qué.

La semántica no cambió. El renombrado sigue siendo la operación atómica que
impide que dos procesos ejecuten el mismo task, y el `OSError` sigue
devolviendo el mismo `"no se pudo reservar ejecucion: …"` al llamante.

### La excepción declarada: `api/server.py`

El bridge OS lee la cola en `GET /permissions/pending` sin importar nada bajo
`core/orchestrator_parts` (regla OS-R1) — parsea los sobres con la utilidad
pura `unwrap_task_payload`. **Es un lector, nunca un escritor**, y las
decisiones humanas las enruta ejecutando `atlas approve` como proceso aparte
(ADR-058), no tocando ficheros. Por eso es uno de los dos únicos módulos que
puede construir la ruta `…/memory/pending_approvals`.

## 3. La frontera Mission ↔ Task

- **`Task`** es la unidad **durable**: tiene máquina de estados, se serializa
  con sobre HMAC y sobrevive a la muerte del proceso
  (`tests/test_task_persistence_recovery.py` lo demuestra cruzando una frontera
  de proceso real).
- **`Mission`** es la unidad **semántica** de agrupación, y es la que ve el
  operador en la Mission Console.
- La frontera: **una Mission no tiene estado durable propio que pueda
  contradecir al de sus Tasks**. Su estado se deriva del de los Tasks que la
  componen. No hay un segundo almacén que pueda desincronizarse, porque no hay
  segundo almacén.

**Límite honesto:** la recuperación de Mission a través de una frontera de
proceso y el rendimiento con escritores concurrentes **siguen sin medirse**.
La ficha lo decía en su `current_state` y sigue siendo cierto. Este mapa no lo
tapa: lo hereda.

## 4. Approval gates — dos otorgantes, y sólo dos

Conceder el clearance **es** la aprobación: `AtlasExecutor` exige
`is_confirmed_this_session("task:<id>")` antes de ejecutar una mutación (ADR-032
dec.8). Quien llame a `mark_confirmed(f"task:{id}")` está aprobando, tenga o no
un humano delante.

| Otorgante | Vía | Salvaguardas |
|---|---|---|
| `ApprovalManager._approve_locked` | Humana (`atlas approve`, Telegram, Mission Console) | Lock exclusivo por task; el `deny` no concede nada; se audita `task.approval`. |
| `AgenticExecutor._run_auto_approved_mutation` | Auto-aprobada (ADR-033 #2) | Requiere **las tres**: la tool está en la allowlist explícita de `set_agentic_auto_approve()`, el loop **no** está contaminado (ADR-037), y el decisor devuelve `Allow` (ADR-040). Se audita como `task.auto_approved` con `risk_level=high`. |

La segunda vía es una excepción **de diseño**, no un agujero: existe para que
el lazo autónomo pueda avanzar en lo que el operador ya declaró seguro, y deja
recibo. Lo que no puede haber es un tercero silencioso — por eso el guardia
compara el conjunto exacto, y falla tanto si aparece uno nuevo como si
desaparece uno de los dos (un guardia que sólo detecta lo que sobra se queda
mudo cuando lo que falla es que la aprobación dejó de concederse).

`pipeline_runner.py:362` menciona `mark_confirmed` **en un comentario**, al
explicar por qué la reanudación no vuelve a pedirlo: el clearance ya se
concedió al aprobar. El guardia mira llamadas, no texto.

## 5. Policy y Evidence

| Estado | Dueño | Nota |
|---|---|---|
| **Policy** — permisos, allowlists, confirmaciones de sesión | `PermissionProfile` (`governance/permission_profile.py`) | Único almacén de `_confirmed_this_session`. La allowlist agéntica vive en el runtime (`set_agentic_auto_approve`), **no** en `governance.json` — deliberado: es política operativa, no constitución. |
| **Evidence** — el recibo | `MerkleLogger` | Append-only encadenado. Medido el 2026-08-09: manipular una entrada **impide arrancar el orquestador** (`RuntimeError: Merkle chain corrupta al arrancar`), no sólo que un comando se queje. Es la garantía más fuerte de este mapa y la que sostiene el "recibo" del E2E. |

## 6. Política de migración y compatibilidad

La ficha exige *"migration and compatibility policy accepted"*. La política
vigente, medida sobre el código:

1. **El formato con sobre HMAC es obligatorio.** `is_legacy_pending_file()`
   detecta el formato v1 sin sobre; no se migra en silencio: se **rechaza**, se
   audita `approval.legacy_rejected` y el fichero va a `_quarantine/`.
2. **Un sobre que no valida no se lee.** MAC incorrecto → `approval.tamper_detected`
   (`risk_level=critical`) y cuarentena. Nunca se intenta "reparar".
3. **La cuarentena no borra.** Los ficheros se renombran, con desempate por
   marca de tiempo si ya existe uno con ese nombre. Un incidente se puede
   investigar después.
4. **Ningún cambio de esquema sin ADR aceptado** (`rollback` de la propia
   ficha). Añadir un campo a `Task` es compatible hacia atrás porque
   `deserialize()` usa `data.get(...)` con defecto para todo lo opcional;
   quitar o renombrar uno **no lo es** y necesita ADR.

## Lo que este mapa NO afirma

- No afirma que Mission tenga recuperación probada: no se ha medido.
- No afirma nada sobre escritores concurrentes más allá del lock por task
  (`flock` no bloqueante) y el renombrado atómico.
- No afirma que los seis dueños sean los correctos para siempre: afirma que
  hoy son seis, distintos, y que ninguno puede aparecer un séptimo sin que
  falle un test.
