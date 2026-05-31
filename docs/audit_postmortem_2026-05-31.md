# Auditoría completa y postmortem — Atlas Core

- Fecha: 2026-05-31
- Alcance: código, tests, tipos, deuda, seguridad, git, docs, CI, incidente de freeze
- Versión auditada: HEAD en `main` (`6b016e8`), árbol limpio. Todas las métricas
  verificadas en disco, no estimadas.
- Veredicto global: **proyecto sano y maduro. Disciplina de tipos y tests
  excepcional (mypy 0 / 754 verdes). La deuda real es un único god-object
  (`orchestrator.py`, decomposición a medias) y un puñado de swallows silenciosos.
  La higiene de versionado que la auditoría anterior marcó como P1 (pyproject vs
  tags) está RESUELTA.**

---

## 1. Métricas (verificadas en disco)

| Métrica | Valor | Lectura |
|---|---|---|
| LOC src | 18.760 (81 archivos) | Proyecto mediano |
| LOC tests | 11.436 (54 archivos) | **Ratio test:src ≈ 0.61:1** — sólido |
| Tests | **754 verdes** + 25 deseleccionados (computer_use), 27.7 s | Verde total |
| mypy | **0 errores en 81 archivos** (`mypy src`) | Disciplina de tipos sobresaliente |
| Commits | 117 | Conventional + ADR por feature |
| ADRs | 17 (`adr_013b`…`adr_037`) | Documentación de decisiones alta |
| Docs | 43 archivos `.md` | Proporción razonable |
| Tags git | 14 (último `v0.12.0`) | Trazabilidad de hitos buena |
| Versión pyproject | **0.12.0** = tag | ✅ deuda de versionado cerrada |
| TODO/FIXME src | **6** | Mínimo; casi todos son maquinaria de self-audit |
| `except` handlers | 214 | Mayoría intencionales |
| `except …: pass` (swallow) | ~21 | A auditar (ver §5 H1) |
| `except:` desnudo | **0** | Excelente — nunca se traga todo |
| CI | `.github/workflows/ci.yml` | pytest + mypy + browser opt-in |

### Módulos > 500 LOC (candidatos a god-object)
| Archivo | LOC | Estado |
|---|---|---|
| `core/orchestrator.py` | **2.272** (~100 métodos) | Núcleo de ejecución cohesivo — decomposición mecánica cerrada (ver §2) |
| `interfaces/cli.py` | 748 | Aceptable (muchos subcomandos planos) |
| `interfaces/telegram_bot.py` | 635 | Vigilar |
| `tools/editor.py` | 557 | Aceptable |
| `security/pii_surrogate.py` | 552 | Aceptable (regex + SLM) |
| `hermes/hermes.py` | 546 | Aceptable |
| `core/inference_hub.py` | 543 | Vigilar (router multi-nivel) |
| `interfaces/exec_api.py` | 520 | Aceptable |

---

## 2. Estado de la decomposición del orchestrator

Plan: `docs/plan_orchestrator_decomposition.md`.

- Colaboradores extraídos: **7** — TaskPersistence, GitReadTools, gate_f_parser,
  agentic_helpers, GateFExecutor, **ApprovalManager** (slice 5, `0e5d6a7`),
  **HybridClassifier** (slice 6, `820f8c1`).
- Tamaño: **3.120 → 2.272 LOC** (**−848 LOC, −27 %**).
- **Parada deliberada.** Lo que queda (`_execute_task` + pipeline + loop agéntico
  ADR-031/032/033/037) es un **núcleo de ejecución mutuamente recursivo**, no dos
  colaboradores separables. Su extracción como `AgenticExecutor` exige inyectar
  ~20 dependencias y toca la frontera ADR-037 (seguridad P0): trabajo de sesión
  dedicada, no de barrido mecánico. Documentado en el plan + tarea DEFERRED. El
  núcleo queda como responsabilidad central explícita del Orchestrator.

---

## 3. Seguridad (postura)

- **Frontera de contenido no confiable (ADR-037)** — implementada. Procedencia
  `mcp__` = no confiable, `wrap_untrusted`, taint del loop. Es la muralla P0.
- **Cliente MCP (ADR-035)** — stdio + registry + timeouts forzados (`da81b1e`).
  Mutate-by-default con allowlist read-only. Sin dep `mcp` (regla 6 respetada).
  `resolve_env` NUNCA propaga el entorno completo del host (mitiga robo de
  credenciales); plantilla `mcp_servers.example.json` con secretos fuera de git.
- **Endurecimiento de subprocess (ADR-034)** — no-new-privs, rlimits
  FSIZE/NPROC/NOFILE, sesión aislada.
- **Threat model (ADR-036)** — documentado.
- **Cadena Merkle** — íntegra; verificada en vivo en el sello E2E del twin.

---

## 4. Postmortem — Freeze de la máquina durante la suite (2026-05-31)

### Síntoma
La máquina se congeló justo al ejecutar la suite de tests. El usuario observó
además que **Cursor se abría cada vez que se corrían los tests**.

### Causa raíz
El test `test_open_creates_process` (`tests/test_editor.py`) invocaba el
`subprocess.Popen([cursor, ruta])` **real** de `EditorTool.open_project`, sin
mockear. Como el hook de pre-commit corre la **suite completa** en cada commit,
**cada intento de commit lanzaba una ventana de Cursor real**. La acumulación de
procesos/ventanas GUI agotó recursos y congeló el equipo.

### Detección
Reporte del usuario (Cursor abriéndose + freeze coincidente con la suite).

### Corrección
Commit `5c724e9` ("test(editor): mock subprocess in open_project test — stop
launching real Cursor"): el test ahora hace `monkeypatch.setattr(subprocess,
"Popen", _fake_popen)`. Ya está en `main`.

### Verificación
- `pytest tests/test_editor.py` → **28 passed**, sin abrir Cursor.
- Suite completa → **754 passed en 27.7 s**, sin freeze, sin GUI.

### Lecciones
1. **Ningún test puede lanzar un proceso/GUI real.** Mockear `subprocess` en la
   frontera. (Ya en memoria: `feedback-no-gui-in-tests.md`.)
2. El pre-commit que corre la suite entera **amplifica** cualquier fuga de
   proceso: una sola llamada no-mockeada se ejecuta en cada commit.
3. No es un bug del producto: `open_project` lanzando Cursor es comportamiento
   *correcto* en runtime (acción de host, gateada por approval vía
   `gate_f_executor.py:196`). El fallo era exclusivamente del test.

### Nota sobre el incidente Merkle previo
El postmortem 2026-05-29 (corrupción de cadena Merkle por correr el CLI contra el
workspace vivo) está cerrado y reflejado en memoria
(`feedback-no-cli-against-live-workspace.md`). No se reabrió en esta auditoría.

---

## 5. Hallazgos abiertos (priorizados)

| # | Sev | Hallazgo | Acción |
|---|---|---|---|
| H1 | ✅ | ~30 `except …: pass` | **Auditado: no es deuda.** Todos best-effort legítimos: cleanup de `unlink`, lecturas de `/proc` con fallback, aislamiento de subscribers pub/sub, notificaciones Telegram que no deben tumbar el bot. Ninguno oculta un bug. Sin cambio de código |
| H2 | P2 | `orchestrator.py` 2.272 LOC (núcleo de ejecución cohesivo) | Extraer `AgenticExecutor` en sesión dedicada (alto riesgo, ADR-037). Ya no es P1: −27 % y 7 colaboradores fuera |
| H3 | P3 | Sin cobertura medida (no hay `pytest-cov`) | Opcional: añadir cobertura puntual para mapear zonas frías |
| H4 | P3 | `sandbox.py:241` TODO Gate E (qm snapshot) | Deuda documentada; depende de infra Proxmox |

Sin hallazgos P0 abiertos.

---

## 6. Veredicto

Proyecto en muy buen estado: tipos impecables, suite verde y rápida, CI real,
seguridad con murallas explícitas y ADRs por decisión. La única deuda estructural
viva es el god-object a medio desmontar. El incidente de freeze está
diagnosticado, corregido y verificado.
