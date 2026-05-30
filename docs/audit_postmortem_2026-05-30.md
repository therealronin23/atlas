# Auditoría completa y postmortem — Atlas Core

- Fecha: 2026-05-30
- Alcance: todo el proyecto (código, tests, tipos, deuda, seguridad, git, docs)
- Versión auditada: HEAD en `main` (todas las métricas verificadas en disco)
- Veredicto global: **proyecto sano y maduro, con disciplina excepcional de tipos
  y tests; la deuda real es estructural (un god-object: `orchestrator.py`) y de
  higiene de versionado (pyproject vs. tags), no de calidad funcional.**

---

## 1. Métricas (verificadas)

| Métrica | Valor | Lectura |
|---|---|---|
| LOC src | 17.890 (71 archivos) | Proyecto mediano |
| LOC tests | 10.988 (52 archivos) | **Ratio test:src ≈ 0.61:1** — sólido |
| Tests | 738 recolectados/seleccionados, todos verdes | Verde total |
| mypy | **0 errores en 71 archivos** | Disciplina de tipos sobresaliente |
| Commits | 108 | Estilo conventional + ADR por feature |
| ADRs | 16 (`docs/adr_*.md`) | Documentación de decisiones alta |
| Docs | 40 archivos `.md` | Proporción razonable |
| Tags git | 14 (todos los gate-tags presentes) | Trazabilidad de hitos buena |
| `except` totales | 99 | Mayoría intencionales |
| `except: pass` (swallow) | 15 | A auditar (ver H3) |
| TODO/FIXME | 119 | Alto; muchos son stubs documentados |

### LOC por paquete
- `security/` 7.421 (7 archivos) — el corazón (AST Guard, governance, AI firewall, snapshots, distiller)
- `core/` 3.998 (6) — orchestrator + contracts + inference_hub
- `interfaces/` 2.730 (8) — CLI, dashboard, telegram
- `runtime/` 2.469 (7) — service_runner, cold_update_manager
- `hermes/` 1.144 (5) — twin bridge
- `cli/` 90 (4)

---

## 2. Fortalezas (lo que está muy bien)

1. **Disciplina de tipos total.** mypy limpio en los 71 archivos. Raro y valioso.
2. **Cobertura de tests amplia y en verde.** 738 tests, harness de dobles
   (`_ScriptedHub`, fakes) consistente entre módulos.
3. **Decisiones documentadas (16 ADRs).** Cada feature tiene su ADR con tabla de
   decisiones y razón. Esto permite retomar el proyecto sin perder contexto.
4. **Seguridad por capas real**, no decorativa: AST Guard, sandbox + hardening
   (ADR-034), Merkle audit, ColdUpdate con worktree aislado, PermissionProfile,
   AI firewall, y ahora frontera de contenido no confiable (ADR-037).
5. **Sin secretos en git.** Ningún `.env`, credencial, `.pem` o token trackeado.
6. **Hitos taggeados.** 14 tags, con los gate-tags C→I presentes en el repo.

---

## 3. Hallazgos por severidad

### P0 — Estructural (atacar pronto)

**H1. `orchestrator.py` es un god-object.** 3.120 líneas, **113 métodos** en una
sola clase. Concentra: routing, loop agéntico, dispatch de tools, gate checks
(F/H), aprobaciones, suspensión/reanudación, inference, MemGPT blocks. Es el mayor
riesgo de mantenibilidad y el punto donde un cambio puede romper algo lejano.
- *Síntoma*: cada ADR nuevo (031→037) añade métodos aquí.
- *Recomendación*: extraer colaboradores — `AgenticLoop`, `ToolDispatcher`,
  `ApprovalManager`, `Router` — manteniendo `Orchestrator` como fachada delgada.
  Refactor mecánico (mover métodos), cubierto por los 738 tests existentes.

### P1 — Higiene (rápido de arreglar)

**H2. Versión de `pyproject` desfasada.** `pyproject.toml` declara
`version = "0.9.0"`, pero existen tags `v0.10.0`, `v0.11.0`, `v0.12.0` y el
ROADMAP/MEMORY narran v0.12.0. La versión empaquetada no coincide con el estado
real del proyecto.
- *Impacto*: cualquier build/install reportaría 0.9.0; confusión de versionado.
- *Recomendación*: bumpear `pyproject` a `0.12.0` (o a la que corresponda) y, en
  adelante, atar el bump del pyproject al momento de taggear.

### P2 — Menor / aceptado

**H3. 99 `except Exception`, 15 que tragan con `pass`.** Muchos son intencionales
(devolver el error al modelo en el loop, preexec_fn tolerante a fallo en ADR-034).
Pero 15 `except: pass` silencian errores.
- *Recomendación*: auditar los 15 swallow puntualmente; loggear al menos a debug.

**H4. 119 TODO/FIXME + stubs conocidos.** OMEGA tier (Proxmox) y snapshot son
stubs documentados (ADR-002, bloqueados por hardware). Buena parte está rastreada,
pero el volumen conviene barrerlo periódicamente para distinguir deuda real de
ruido.

**H5. Deps pesadas vs regla 6.** `sentence-transformers` (arrastra torch), `kuzu`,
`numpy`, `litellm`, `fastapi`. Son fundacionales, pero son superficie de cadena
de suministro — justo la amenaza "modelo/deps supply chain" de ADR-036. No es un
bug; es deuda a vigilar (pin + checksum a futuro).

**H6. Identidad de autor.** Conviene un `.mailmap` para consolidar identidades de
commit si `git shortlog` muestra variantes del mismo autor con emails distintos.

---

## 4. Postmortem de la deriva de métricas en prosa

Las métricas (conteo de tests, versión, nº de ADRs) viven embebidas en prosa de
varios documentos. Cada feature obliga a editar esos números en N sitios → deriva
garantizada. Ejemplo concreto detectado en esta auditoría: **`pyproject` dice
0.9.0 mientras el resto del proyecto dice 0.12.0.**

**Causa raíz**: métricas mantenidas a mano en múltiples fuentes.
**Mitigación**: que el conteo de tests no se escriba en prosa (o se genere); que
la versión tenga una sola fuente de verdad; y que los hitos se taggeen *y bumpeen*
en el momento, no se narren después.

---

## 5. Salud de seguridad

| Capa | Estado |
|---|---|
| AST Guard (validación pre-ejecución) | ✅ sólido, con test de bypass f-string (ADR-031) |
| Sandbox NORMAL + hardening | ✅ ADR-034 (no-new-privs, rlimits, sesión aislada) |
| Merkle audit chain | 🟡 funciona; anclaje off-host pendiente (ADR-036 P1) |
| ColdUpdate (worktree aislado + HITL) | ✅ ADR-025 |
| Frontera contenido no confiable | 🟡 ADR-037 slice 1 (taint + envoltura); dual-LLM pendiente |
| Gate de adopción MCP/skills | ⏳ ADR-038 pendiente |
| Secretos | ✅ ninguno en git |
| seccomp / namespaces | ⏳ pendiente (dep/kernel) |

Postura: **defensa en profundidad correcta**, con las murallas P0/P1 del threat
model (ADR-036) en su mayoría aún por levantar — coherente con la fase del
proyecto (acabamos de escribir el plano).

---

## 6. Plan de acción recomendado (priorizado)

| # | Acción | Esfuerzo | Severidad |
|---|--------|----------|-----------|
| 1 | Bumpear `pyproject` a la versión real (0.12.0) | 2 min | P1 |
| 2 | Plan de descomposición de `orchestrator.py` (god-object) | 1 sesión | P0 |
| 3 | Auditar los 15 `except: pass` (loggear) | 30 min | P2 |
| 4 | Barrer los 119 TODO/FIXME y archivar lo muerto | 30 min | P2 |
| 5 | Añadir `.mailmap` si hay identidades fragmentadas | 10 min | P2 |
| 6 | Continuar la hoja de murallas (ADR-035 cliente MCP) | varias sesiones | roadmap |

**Lo barato (1) se puede hacer ya.** El refactor del orchestrator (2) es el único
trabajo estructural serio y conviene hacerlo *antes* de seguir apilando ADRs
encima (035/038 añadirán más métodos a esa clase).

---

## 7. Conclusión

Atlas Core está, objetivamente, **por encima de la media de proyectos de su
tamaño**: tipos limpios, tests abundantes y verdes, decisiones documentadas, sin
secretos filtrados, seguridad por capas real. No hay nada *roto*.

La deuda es la esperable de un proyecto que ha crecido rápido por features: **un
módulo central sobrecargado** (orchestrator) y **higiene de versionado floja**
(pyproject 0.9.0 vs. tags v0.12.0). Ninguna es urgente-funcional; la #2
(god-object) es la única que, si se ignora, encarecerá todo lo que venga después.

Recomendación de orden: **bumpear pyproject ahora**, **planificar el refactor del
orchestrator antes de ADR-035**, y luego seguir con la hoja de murallas.
