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
- **[BUG — RESUELTO 2026-06-14] dep-bump autónomo creaba deriva floor>instalado.**
  El loop subía `fastapi>=0.110` → `>=0.136.3` con el entorno en 0.136.1: floor
  declarado MAYOR que la realidad, y la suite pasaba porque pytest no valida
  floors → deriva declarado-vs-real silenciosa. Revertido a mano el 2026-06-13;
  reapareció el 2026-06-14. **Causa raíz cerrada:** `DepProposer._effective_floor`
  ancla el piso a la versión instalada (`importlib.metadata`, sin red/subproceso)
  y nunca propone `>=latest` por encima de lo instalado; fail-closed si la dep no
  está instalada. Regresión en `tests/test_dep_scout.py`
  (`test_floor_never_exceeds_installed`, `test_not_installed_fail_closed`).
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
- **[HECHO 2026-06-14] `audit_sample` cableado a daemon.** `reverify_swarm_proposals`
  corre en un daemon in-process de `AtlasServiceRunner` (gate
  `ATLAS_AUDIT_SAMPLE_SCHEDULER`, off; cadencia `ATLAS_AUDIT_SAMPLE_POLL_S`=24h;
  fracción `ATLAS_AUDIT_SAMPLE_FRACTION`=0.2; patrón swarm, escritor único). Es el
  gate de evidencia para promoción a auto-apply. Commit `1f46742`.
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

- **[HECHO 2026-06-14] Rechazos con evidencia forense.** `ColdUpdateProposal.forensics`
  persiste pytest/mypy summary+exits+timestamp al fallar `validate()` (retrocompat
  vía setdefault en `_load`). Ya se puede distinguir fallo real de ambiental. Commit
  `1f46742`.
- **[HECHO 2026-06-14] HITL invertido (anomalías al decisor).** SUSPECT_FLAKY
  persistente se enruta al decisor (PDP intercambiable) con la forense en el context,
  en vez de descartarse: `_route_anomaly` → `decider.decide(DecisionAction(
  kind='cold_update_anomaly'), ...)`. HumanDecider→RequiresHuman (surfacea anomalía),
  AutonomousDecider→invariantes. Happy path fluye sin aprobación por merge. `decider`
  opcional (retrocompat). Commit `1f46742`.
- **[HECHO 2026-06-14] Reintento SUSPECT_FLAKY.** Si `pytest_exit!=0` pero el diff de
  tests base↔worktree es vacío, `validate()` revalida UNA vez (`_tests_diff_empty`
  con clean_git_env, fail-closed); pasa→validated, falla→failed conservando forense
  de ambos intentos. No reintenta si el diff de tests es no vacío ni si solo falla
  mypy. Commit `1f46742`.

## Operativo

- Instalar/arrancar la unidad systemd `atlas-audit-24h.service` (decisión del
  operador; no instalada por seguridad).
- **[HECHO 2026-06-14] `ColdUpdate.apply` con commit-con-evidencia.**
  `_commit_with_evidence` escribe un commit con verdict/exits/origin/proposal_id/
  intent (clean_git_env); root no-git lo omite; fallo de commit no revierte el patch
  validado. Los aplicados autónomos ya no quedan huérfanos. Commit `1f46742`.
- Disciplina de escritor único para dev humano: trabajar en worktree aislado o
  pausar el loop autónomo durante sesiones de desarrollo (la contención del
  2026-06-13 lo evidenció).

## Organismo de conocimiento (ADR-049)

**Visión correcta (aclaración 2026-06-14):** Atlas no busca solo CVEs.
Busca TODO lo que lo amplíe o mejore: plugins, skills, herramientas, APIs,
patrones de código, deps nuevas, feeds de conocimiento de cualquier dominio.
El primer conector fue CVE/OSV.dev porque era concreto y sin riesgo; la
arquitectura es genérica para cualquier señal exterior. Si algo mejora el
sistema → propuesta automática; si hay duda → escalar al decider (PDP
intercambiable). El humano no es el único decisor, solo una implementación.

### Slice 2 — Inmediato (version-range matching)

- **[PRÓXIMO] Version-range matching en `SelfImprovementBridge`** — comparar
  `installed_version` contra rangos OSV `affected[].ranges[].events[]` usando
  `packaging.version` (ya transitiva). Solo emitir `SelfRelevantFinding`
  cuando la versión instalada cae dentro de `[introduced, fixed)`. Elimina
  el ruido de CVEs históricos ya parcheados. Archivo:
  `src/atlas/knowledge/self_improvement.py`, función
  `_version_in_range(installed, ranges) -> bool`.

### Slice 3 — Cableado al loop de auto-mejora

- **Daemon hacia afuera** (`ATLAS_KNOWLEDGE_SCHEDULER`) — proceso en segundo
  plano que ejecuta misiones; mismo patrón que swarm/audit_sample.
- **Cableado vivo del SelfImprovementBridge** — `SelfRelevantFinding` →
  propuesta ColdUpdate (dep-bump con `fixed_version` conocida → automático si
  severidad alta; dudoso → decider). Cierra el ciclo: Atlas detecta que una
  dep suya tiene CVE → propone el bump solo, sin humano.
- **Reporte por Telegram** — twin Hermes notifica findings al operador.

### Slice 4 — MCP y skills autodescubribles

- **MCP como fuente de conocimiento** — cliente ADR-035 como `KnowledgeSource`;
  Atlas rastrea herramientas MCP del ecosistema y propone integrar las
  relevantes → se amplía solo.
- **Skills autodescubribles** — dominio "atlas/skills": lista de skills
  disponibles, comparar con instaladas, proponer incorporar las útiles.

### Slice 5 — Personas y conectores de dominio

- **Misiones concretas de dominio** — persona inmobiliario (idealista/fotocasa,
  alerta de precio) y persona ciberseguridad ofensiva (CVEs activos + exploits
  + advisories, vía ADR-043 grants). La columna ya las soporta.
- **Más conectores** — feeds RSS/Atom, NVD, EPSS, datos regulatorios,
  mercados; solo implementar el `KnowledgeSource` Protocol por conector.

### Slice 6 — KB como grounding de los productores (cierre del ciclo)

- KnowledgeBase acumulada como contexto vivo para ADR-048 (VerifiedProducer);
  cada artefacto generado referencia el fragmento de KB que lo fundamentó
  (trazabilidad fuente → generación → verificación).

## Horizonte largo

- `ArtifactKind.PROOF` + artefactos con prueba → puente a sustrato formal
  (seL4 como cambio de backend, no rewrite).
