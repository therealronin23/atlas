# Backlog de trabajo diferido

Registro durable de todo lo diferido explícitamente, para que nada se pierda.
No es deuda oculta: cada ítem se dejó fuera de su iteración por una razón. El
estado vivo real siempre por `atlas reality`; esto es la cola de intención.

Actualizado: 2026-06-14.

## Bugs reales encontrados (prioridad)

- **[CAUSA RAÍZ identificada 2026-06-13] Secuestro por env git de hooks.**
  Bajo un hook git (pre-commit), git exporta `GIT_DIR`/`GIT_INDEX_FILE`/etc.
  Cualquier código que lance `git` sin limpiar esas vars se redirige al repo
  del hook en vez del worktree objetivo. Esto generó los **365 worktrees
  huérfanos** (código de worktree corriendo bajo hooks → repo real) Y la
  flakiness del pre-commit. **Arreglado en `WorktreeManager`** (capa 3) con
  `_clean_git_env()` + test de regresión `test_immune_to_ambient_git_env`.
- **[HECHO 2026-06-13] env-hijack en ColdUpdate.** `clean_git_env()`
  factorizado a `core/git_env.py` y aplicado a `_create_worktree`,
  `_apply_patch` y `_diff_stat`. Contrato testeado (`test_git_env.py`).
- **[HECHO 2026-06-13] ColdUpdate teardown del worktree en estado terminal.**
  El patch ahora vive en el store root (no en el worktree) → `_remove_worktree`
  en applied/failed/rejected/rolled_back sin romper `rollback_applied`. Tests:
  patch fuera del worktree, apply destruye worktree+conserva patch+rollback OK,
  reject destruye worktree. Frena la acumulación de worktrees a futuro.
- **[BUG] dep-bump autónomo crea deriva floor>instalado.** El loop subió
  `fastapi>=0.110` → `>=0.136.3` pero el entorno tiene 0.136.1 instalado: el
  floor declarado es MAYOR que la realidad. La suite pasa porque pytest no
  valida floors → deriva declarado-vs-real silenciosa. Fix: el dep-proposer
  debe instalar + re-validar la versión nueva en el entorno antes de proponer
  el floor (o anclar el floor a lo instalado). Revertido a mano el 2026-06-13;
  **REAPARECIÓ sin commitear el 2026-06-14** (`fastapi>=0.136.3` en el working
  tree otra vez) → tarea aparte para revert + causa raíz. El proposer lo reintroduce.
- **[LIMPIEZA HECHA 2026-06-13] 365 worktrees huérfanos** en
  `<repo>.parent/atlas-cold-updates/...` (anidamiento patológico
  `atlas-cold-updates/atlas-cold-updates/...`). `git worktree prune` solo
  quita metadata muerta; estos tienen dir → requieren `git worktree remove`
  o borrado del store. Coordinar con el servicio vivo antes.

## Capa 1 — Verificador universal

- Verificador de `CLAIM` (grounding contra `reality`) — desbloquearía cablear
  el path conversacional por la cascada (hoy frontera, ADR-042).
- `ArtifactKind` de densidad: WASM (validación módulo + WASI), BINARY, CONFIG
  (schema/lint). Cada uno = kind + verificador.

## Capa 2 — Cascada con routing

- **Sin entrypoint de producción** (audit 2026-06-13): codegen no tiene CLI ni
  trigger autónomo; el consumidor real es la capa 3. No hay `cascade.route`
  autónomo hasta entonces.
- Rung FRONTIER: añadir cuando exista un provider L2 configurado (hoy el tier
  existe pero ningún provider lo usa).

## Capa 3 — Enjambre

- **[NÚCLEO HECHO 2026-06-13] VerifiedProducer (ADR-048).** Hechas A-F:
  A panel (`adversarial_panel.py`), B lazo (`verified_producer.py`),
  C `DeterministicProducer` (`deterministic_producer.py`, transforms+invariante
  AST), D `LLMProducer` (`llm_producer.py`, restricciones de lección+allowed_paths),
  E `RepoMaintenanceScout` (`maintenance_scout.py`, dedup por firma),
  F composición (`maintenance_worker.py`, `build_maintenance_producer`+adapter).
- **[CAPA 3 EJECUTABLE 2026-06-14]** (commits 524b51d/7e0d44e/134fbfd). Cableado
  `produce_diff`/`validate` reales → blackboard → reconciler → ColdUpdate, vía
  `SwarmCycle` (`swarm_cycle.py`) + daemon in-process en `AtlasServiceRunner`
  (gate `ATLAS_SWARM_SCHEDULER=1`, off; cadencia `ATLAS_SWARM_POLL_S`=6h). Escritor
  único = merkle del orquestador. **Auto-apply OFF (propuesta-solo).** Humo aislado
  OK: produce diff real → ColdUpdate.propose(origin=swarm) + dedup en 2º ciclo.
  Decisión auditada: el `validate` del worker es BARATO (`swarm_validate.worktree_validate`:
  git apply --check + ast.parse), NO corre la suite — la suite ya vive en
  `ColdUpdate.validate` (gate del decider). El techo de cadencia/alcance ya no es
  la suite sino el tope de propuestas abiertas (`cap_open`) sin decisor que las drene.
- **Más transforms del arnés** (`deterministic_producer.py`): hoy whitespace,
  newline final, colapso EOF. Candidatos AST verificables: orden de imports,
  imports muertos (con cuidado: requiere análisis de uso real), normalización de
  comillas de docstring. Cada uno = `Transform` + su invariante.
- **[HECHO 2026-06-14] El scout lee disco real**: `head_file_provider` lee blobs
  de HEAD (F4: no el disco vivo, inmune a cambios sin commitear) y alimenta
  `scan(...)` con `open_signatures` derivadas de propuestas swarm abiertas (F6/F7).
- **[HECHO 2026-06-14] `validate` real del worker** — cableado como `worktree_validate`
  (barato, ver arriba); la suite completa no se duplica en el worker.
- **[BUG menor] `SwarmCoordinator.run_round` no envuelve `worker.produce(task)`**:
  un worker tóxico (p.ej. git falla creando worktree) aborta el resto de tareas del
  ciclo. El daemon lo contiene (no muere) pero degrada de "una tarea falla" a "se
  pierden las restantes del ciclo". Envolver por-worker como se hizo con `on_accepted`.
- **Transforms newline/EOF**: hoy solo `strip_trailing_whitespace` por worker (los
  de newline/EOF producen diffs que `git apply` rechaza por falta del marcador
  "\ No newline at end of file"). Robustecer el apply antes de añadirlos.
- **[HECHO 2026-06-13] Reconciliación enjambre → ColdUpdate.**
  `ColdUpdateReconciler` (hook `on_accepted` del coordinador): artefacto
  ACEPTADO → propuesta ColdUpdate (origin="swarm", nuevo origen permitido) →
  seam del decider. **Auto-apply apagado**: solo propone, nunca aplica. Tests
  con manager fake + integración con ColdUpdateManager real.
- `audit_sample` que **re-ejecuta** la suite sobre la muestra (hoy solo
  selecciona la muestra; falta la re-verificación real).
- **Primer enjambre operativo**: 3 workers de mantenimiento, una semana sin
  intervención — el listón falsable (dirección §3). Decisión operativa.
- Cableado a la **entrada general de tareas** (`handle_intent`/decider), para
  que las capas sirvan a todo Atlas y no solo a self-maintenance. Toca el path
  vivo: con cuidado.

## Capa 4 — LessonStore

- **Consumidores**: Analyst/codegen cargan `avoid_pattern` como restricción y
  `detection_heuristic` como check antes de producir. (Bloqueado: codegen no
  alcanzable hasta capa 3.)
- **Runner real de prove-it**: worktree en `fix_commit^` + pytest, para
  capturar rojo-antes/verde-ahora real (hoy el `ProveItResult` se inyecta).
- **Seeding de las 3 lecciones reales**: matcher (`7de8251`), doble escritor
  Merkle (`fb44f46`), suite recursiva (`4b9943a`). Necesita el runner real;
  sembrar con Evidence sintética violaría la ley de entrada.
- Cableado `ErrorRegistry` → `LessonPromoter` (quién setea
  `promoted_to_lesson_id`).

## Seguridad (ADR-043, propuesto)

- `AuthorizationGrant` firmado (target × capacidad × expiración) +
  `AuthorizationVerifier` (gate PDP).
- `SECURITY_FINDING` ArtifactKind + verificador por reproducción del PoC en
  sandbox.
- Harness de fuzzing/PoC en sandbox contra targets autorizados.
- Firma stdlib HMAC primero; ed25519 (`cryptography`) solo si grants
  multi-parte.

## Criterio de rechazo y pérdida de candidatos

- **[BUG] Rechazos sin evidencia forense.** Cuando un worktree falla (`pytest_exit=1`
  o `mypy_exit=1`), el ColdUpdate queda en `rejected` pero sin el output exacto
  guardado. Si el fallo es ambiental (test flaky, dep transitiva no instalada, env
  diferente) el candidato se pierde para siempre y no hay forma de distinguirlo de
  un fallo real. Fix: persistir el stdout/stderr del worktree en el store al rechazar.
- **[DISEÑO] HITL para rechazos, no para aprobaciones.** El modelo actual pide
  aprobación humana para aplicar; el modelo deseable es el inverso: los candidatos
  que pasan la criba fluyen solos, pero los rechazados (especialmente si el diff
  de test está vacío — ningún test nuevo falló) se presentan al operador con la
  evidencia para decidir si reintentar o descartar. Encaja con ADR-040/047: el
  humano revisa anomalías, no guarda la puerta de cada merge.
- **[DISEÑO] Reintento inteligente.** Si `pytest_exit=1` pero el diff de tests
  entre base y worktree es vacío (no se añadió ni modificó ningún test), marcar el
  rechazo como `SUSPECT_FLAKY` y reintentarlo una vez antes de descartar. Reduce
  falsos negativos sin abrir la puerta a que código roto se aplique.

## Operativo

- Instalar/arrancar la unidad systemd `atlas-audit-24h.service` (decisión del
  operador; no instalada por seguridad).
- `ColdUpdate.apply` con commit-con-evidencia, para que los aplicados
  autónomos no queden huérfanos en el árbol (como el bump de `rich`).
- Disciplina de escritor único para dev humano: trabajar en worktree aislado o
  pausar el loop autónomo durante sesiones de desarrollo (la contención del
  2026-06-13 lo evidenció).

## Horizonte largo

- `ArtifactKind.PROOF` + artefactos con prueba → puente a sustrato formal
  (seL4 como cambio de backend, no rewrite).
