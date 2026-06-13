# Backlog de trabajo diferido

Registro durable de todo lo diferido explícitamente, para que nada se pierda.
No es deuda oculta: cada ítem se dejó fuera de su iteración por una razón. El
estado vivo real siempre por `atlas reality`; esto es la cola de intención.

Actualizado: 2026-06-13.

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
  el floor (o anclar el floor a lo instalado). Revertido a mano el 2026-06-13.
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

- Cableado real de `WorktreeWorker.produce_diff` (cascada/transform) y
  `validate` (ValidationRunner en el worktree) — sigue inyectado.
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
