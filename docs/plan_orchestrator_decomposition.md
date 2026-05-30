# Plan — Descomposición de `orchestrator.py` (god-object)

- Fecha: 2026-05-30
- Origen: H1 de la auditoría 2026-05-30 (P0).
- Estado actual: `orchestrator.py` = **3.120 LOC, 113 métodos** en una sola clase.
- Objetivo: dejar `Orchestrator` como **fachada delgada** (<800 LOC) que delega
  en colaboradores con responsabilidad única. Sin cambiar API pública ni
  comportamiento. Sin nuevos tests inicialmente — la red de seguridad son los
  **738 tests existentes**, que deben quedar verdes tras cada slice.

## Principios

1. **Extracción mecánica, no rediseño.** Mover métodos a una clase nueva con la
   misma firma; en `Orchestrator` queda un *thin delegate* (`return
   self._approvals.pending()`). API externa intacta.
2. **Un slice = un commit = un colaborador.** Cada slice se mergea solo si los
   738 tests siguen verdes y mypy queda en 0 errores. Rollback trivial.
3. **No tocar el loop agéntico hasta el final.** Es el más crítico y el último
   modificado (ADR-037). Extraerlo solo cuando los demás colaboradores ya
   estén estables.
4. **Compatibilidad de imports.** Los nuevos módulos viven en
   `src/atlas/core/orchestrator_parts/` para no contaminar el namespace público.
5. **Cero ADR nuevo.** Esto es refactor puro; se documenta como entrada en
   ROADMAP + referencia desde la auditoría.

## Mapa de clusters (auditado)

| Cluster | Métodos | LOC aprox | Líneas | Riesgo |
|---|---|---|---|---|
| **A. Persistencia de tasks/approvals** | `_serialize_task`, `_deserialize_task`, `_persist_pending_approval`, `_load_pending_approval`, `_load_persisted_pending_approvals`, `_delete_pending_approval`, `_acquire_pending_lock`, `_pending_summary` | ~8 / 200 | 1720-1835, 3015 | Bajo (puro I/O JSON) |
| **B. Gate F command parsing/routing** | `_parse_gate_f_command`, `_parse_browser_command`, `_parse_editor_command`, `_parse_vision_command`, `_split_payload`, `_route_gate_f_command`, `_execute_gate_f_task`, `_execute_browser/editor/vision_command`, `_execute_editor_run_command`, `_validate_generated_script_source`, `_execute_generated_editor_run`, `_resolve_gate_f_path` | ~14 / 470 | 1254-1720 | Bajo (autocontenido) |
| **C. Git/workspace read tools** | `_git_args`, `_with_repo_root`, `_run_git_status/log/diff`, `_list_workspace`, `_repo_root`, `_resolve_workspace` | ~8 / 100 | 2736-2828 | Muy bajo |
| **D. ApprovalManager** | `pending_approvals`, `approve_pending`, `_approve_pending_locked` | ~3 / 160 | 262-419 | Medio (concurrencia + lock) |
| **E. AgenticLoop** | `_agentic_tool_specs`, `_agentic_tool_kind`, `_agentic_tool_provenance`, `_wrap_untrusted`, `_loop_is_tainted`, `set_agentic_auto_approve`, `_is_agentic_auto_approved`, `_run_auto_approved_mutation`, `_emit_agentic_progress`, `sweep_expired_suspensions`, `_stringify_tool_result`, `_dispatch_agentic_tool`, `_drive_agentic_loop`, `_suspend_agentic_loop`, `_dispatch_agentic_mutation`, `_resume_agentic_loop` | ~16 / 620 | 2017-2637 | **Alto** (corazón ADR-031/033/037) |
| **F. Pipeline & classification** | `_run_pipeline`, `_run_pipeline_gate_d`, `_hybrid_classify`, `_execute_task`, `_execute_local_safe_via_inference`, `_record_inference_failure` | ~6 / 470 | 812-1996 | Medio |
| **G. Resto** (init, status, properties, bot, thermal, hermes, audit, defaults) | ~58 | ~1.100 | — | (queda en `Orchestrator`) |

**Total extraíble**: ~55 métodos / ~2.020 LOC. Lo que queda en `Orchestrator`
(~58 métodos / ~1.100 LOC) es ya razonable como fachada.

## Secuencia de slices

Orden elegido por **riesgo creciente** (lo más mecánico primero), para construir
confianza y dejar lo delicado para cuando el patrón esté rodado.

### Slice 1 — `TaskPersistence` (cluster A)
- Nuevo: `orchestrator_parts/task_persistence.py` con clase `TaskPersistence`.
- Estado: `pending_dir: Path`, `bus: EventBus`.
- En `Orchestrator`: `self._tasks = TaskPersistence(self._pending_dir, self._bus)`.
- Delegados thin: `_persist_pending_approval = self._tasks.persist`, etc.
- **Test**: 738 verde, mypy 0.

### Slice 2 — `GitReadTools` (cluster C)
- Nuevo: `orchestrator_parts/git_tools.py`.
- Estado: `workspace: Path`, `_repo_root_cached`.
- Migrar `_run_git_status/log/diff`, `_list_workspace`.
- Engancha al dispatch del loop agéntico vía `self._git.run_status(task)`.
- **Test**: 738 verde, mypy 0.

### Slice 3 — `GateFRouter` (cluster B)
- Nuevo: `orchestrator_parts/gate_f_router.py`.
- Estado: refs a `editor_tool`, `browser_tool`, `vision_loop`, `executor`.
- API: `parse(intent) -> GateFCommand | None`, `route(task, cmd)`,
  `execute(task)`.
- `Orchestrator` solo conserva el atajo público que ya tenía.
- **Test**: 738 verde, mypy 0.

### Slice 4 — `ApprovalManager` (cluster D)
- Nuevo: `orchestrator_parts/approvals.py`.
- Estado: `pending_lock`, `pending_dir`, `bus`, `serializer` (`TaskPersistence`).
- API: `pending() -> list[dict]`, `approve(task_id, decision) -> bool`,
  `_approve_locked(...)`.
- Coordina con `AgenticLoop` vía callback `on_resume: Callable[[Task], None]`
  inyectado por `Orchestrator` (rompe el ciclo).
- **Test**: 738 verde — atención al test de reanudación.

### Slice 5 — `PipelineRunner` (cluster F)
- Nuevo: `orchestrator_parts/pipeline.py`.
- Estado: refs a `inference_hub`, `executor`, `bus`, `gates`.
- Esto es el más entrelazado con el `Orchestrator` actual; se extrae solo después
  de que A/B/C/D estén estables y haya un patrón claro de inyección.
- **Test**: 738 verde.

### Slice 6 — `AgenticLoop` (cluster E) — el último, el más delicado
- Nuevo: `orchestrator_parts/agentic_loop.py`.
- Estado: refs a todos los anteriores (`tools`, `approvals`, `git`, `gate_f`).
- Migrar bloque completo ADR-031/032/033/037. **No tocar lógica**; solo mover.
- Suspensión y reanudación se siguen serializando con el mismo formato (compat
  con `agentic_state` persistido).
- **Test**: 738 verde — atención especial a:
  - `test_orchestrator_agentic_*`
  - `test_orchestrator_untrusted_boundary.py` (ADR-037)
  - `test_telegram_bot_*` (consume `sweep_expired_suspensions`).

### Slice 7 — Limpieza
- Eliminar imports muertos en `orchestrator.py`.
- Comprobar `__init__.py` no re-exporta nada ahora privado.
- `wc -l orchestrator.py` esperado: <800.
- `grep -c "def " orchestrator.py` esperado: <40.

## Criterios de aceptación por slice

Cada commit (uno por slice):

1. `python3 -m pytest` → 738 pasando, 25 deselected (igual que ahora).
2. `mypy src tests` → 0 errores.
3. `wc -l src/atlas/core/orchestrator.py` → decrece monotónicamente.
4. `git diff --stat` → solo movimientos + thin delegates; sin cambios de
   comportamiento.
5. Mensaje de commit: `refactor(orchestrator): extract <X> (slice N/6)`.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Romper la reanudación tras suspensión (estado serializado) | Slice 6 conserva firma de `_serialize_task`/`_deserialize_task`; el formato JSON no cambia |
| Ciclos de import entre partes | Inyección por constructor; `orchestrator_parts/__init__.py` no re-exporta nada |
| Tests acoplados a métodos internos | Si un test toca un `_method` movido, se conserva el thin delegate hasta que el test se actualice (otra sesión) |
| El AgenticLoop necesita acceso al `Orchestrator` para algo no obvio | Si aparece, exponer la dependencia mínima como callback en el constructor — nunca pasar `self` completo |

## Lo que NO se hace en este plan

- No se renombra API pública.
- No se cambia el modelo de eventos del bus.
- No se añaden nuevos tests (los 738 son la red).
- No se toca la persistencia Merkle ni la cadena de auditoría.
- No se introduce async donde antes era sync (ni viceversa).

## Estimación

~1 sesión por slice (1-6) + 1 sesión de limpieza = **~7 sesiones**. Los slices
1-3 son mecánicos y rápidos (probablemente 2 en una sola sesión).

## Punto de no retorno

Ninguno: cada slice es revertible con `git revert`. Por eso esta secuencia es
preferible a un refactor monolítico.
