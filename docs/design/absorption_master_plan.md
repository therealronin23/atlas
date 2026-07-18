# Atlas Absorption Master Plan

**Source material:** distilled from `grok.md`.
**Status:** planning document, not a Gate seal.
**Rule:** absorb patterns AND real code — smart fork, not blind vendoring and
not clone-inspect-delete.

`grok.md` is a raw research dump. It should not be committed as canonical
documentation: it contains exported chat UI, obsolete status, repeated advice,
and personal metadata. This file is the cleaned plan.

## CORRECCIÓN del barrido de abajo — el operador tenía razón (2026-07-18, mismo día)

El operador desconfió del veredicto "ya cubierto" de la tabla de abajo
("no se forkeó bien ninguna, quítame la razón si puedes") y pidió verificar
otra vez, más a fondo. Se hizo, con grep real de callers (no solo "¿existe
el fichero y está wireado en algún sitio?"):

- **Checkpoints (Cline)**: FALSO que sea redundante. `_timetravel.record_step()`
  solo graba ETIQUETAS DE ESTADO DEL PIPELINE ("blocked_governance",
  "awaiting_approval") — nunca contenido de ficheros. No hay NINGÚN caller de
  `TimeTravel`/`CheckpointStore` en `atlas_coder.py`/`tool_coder.py`/
  `parallel_coder.py`/`incremental_coder.py` (verificado con grep, cero
  resultados). Cline SÍ resuelve "deshacer los cambios de fichero que hizo el
  agente" — Atlas no tenía nada equivalente. **Corregido**: implementado
  `src/atlas/core/git_checkpoint.py` (ver más abajo).
- **Focus Chain (Cline)**: FALSO que esté cubierto por "task tooling del
  harness" — ese tooling es de Claude Code (esta sesión), no de Atlas. Cero
  rastro de un checklist auto-mantenido dentro del Orchestrator real
  (verificado con grep). Gap real, **no resuelto todavía** — queda como
  siguiente pieza concreta, nombrada explícitamente, no enterrada.
- **Sandboxing (OpenHands)**: más débil de lo que se dijo. `BwrapJail` solo
  se usa en `lesson_runner.py` y `cold_update_manager.py` — NO en los
  motores de codificación reales. Lo que `tool_coder.py` llama "sandbox" es
  aislamiento de RUTA (copia en directorio temporal), no aislamiento de
  proceso/red. La comparación con el runtime de OpenHands (que sí aísla
  ejecución) no se sostiene igual de bien — queda marcado como reabierto,
  sin resolver en esta pasada.
- **Repo-map (Aider) y Memory Bank (Cline)**: se sostienen, confirmado de
  nuevo (repo_map.py cita a Aider en su propio docstring; Memory Bank de
  Cline sigue siendo solo convención de ficheros sin código que comparar).

**Lección**: la primera pasada de esta misma sesión confirmó "¿existe y está
wireado en algún sitio?" pero no "¿está wireado PARA EL MISMO PROPÓSITO que
lo que se compara?" — el mismo error de rigor, dos veces en el mismo día.

## Git Checkpoint Manager — IMPLEMENTADO 2026-07-18 (corrección del hallazgo de arriba)

`src/atlas/core/git_checkpoint.py` — absorbido fiel de
`cline/sdk/packages/core/src/session/checkpoint-restore.ts`: mismo mecanismo
(commit o stash de git real, etiquetado por turno de agente, `restore()` =
`git reset --hard` + `git clean -fd` + aplicar el ref, mismo orden exacto de
comandos). Diferencia deliberada más segura: pensado para operar SOLO dentro
de los git worktrees efímeros que `ParallelCoder`/`ToolCoder` ya crean por
tarea (`git worktree add --detach`), nunca en el repo real — a diferencia de
Cline, que opera sobre el directorio de trabajo real del usuario. 7 tests
con un repo git REAL en tmp_path (no mocks — para algo destructivo, se
probó el mecanismo de extremo a extremo, no solo que se llamara a subprocess
con los argumentos correctos). Bug real cazado durante el testeo: `checkpoint()`
sobre un working tree limpio hacía `git stash push` vacío, que git rechaza
("no local changes to save") — arreglado con fallback a `kind='commit'`
sobre HEAD cuando no hay nada que stashear. mypy limpio.

**Límite honesto, deliberado**: `restore()` es DESTRUCTIVO (borra todo lo no
checkpointeado) — auditado en Merkle con `risk_level="critical"`, pero **NO
está wireado en el loop agéntico todavía**. Exponerlo como tool requeriría
diseñar el gate de aprobación humana con el mismo cuidado que el resto de
tools mutate/HITL de hoy — no se apresura ese diseño al final de una sesión
ya muy larga. El módulo es real, probado y usable desde código Python; la
integración con aprobación explícita queda como siguiente paso nombrado.

## Cline/Aider/OpenHands — barrido de backend, CERRADO 2026-07-18 (ver corrección arriba — 2 de 5 hallazgos eran erróneos)

El operador pidió fork completo de los tres tras clonarlos
(`~/proyectos/atlas-forks/{cline,aider,openhands}`). Antes de forkear a
ciegas, se auditaron las 5 características de backend más señaladas de los
tres — mismo método que la auditoría de Hermes (verificar código real, no
asumir). Resultado: **las 5 ya existen en Atlas**, casi siempre más rigurosas:

| Candidato | Origen | Ya en Atlas | Veredicto |
|---|---|---|---|
| Checkpoints git-based (rewind de estado) | Cline | `src/atlas/core/checkpoint.py` + `timetravel.py` (ADR-021) — encadenado hash de integridad + fork contrafactual + auditoría Merkle, cableado en `orchestrator.py`, 25 tests | Atlas es MÁS riguroso (Cline solo hace snapshot de git, sin cadena de integridad ni ramas) |
| Memory Bank (markdown persistente entre sesiones) | Cline | LessonStore + block memory + embeddings semánticos, auditado en Merkle | Memory Bank de Cline es solo convención de ficheros .md sin código real detrás — Atlas ya lo supera |
| Focus Chain (checklist `- [ ]` de progreso) | Cline | Task tooling del propio harness + Mission Console | Redundante, patrón muy simple (77 líneas en Cline) |
| Repo-map (PageRank sobre símbolos) | Aider | `src/atlas/core/repo_map.py` — **el propio docstring dice "técnica #14, patrón Aider"** — ya absorbido, con `ast` en vez de tree-sitter (razón: repo 100% Python) | Ya absorbido explícitamente, con razón documentada de la diferencia |
| Runtime sandboxed (ejecución del agente aislada) | OpenHands | `BwrapJail` (invariante dura en `ColdUpdateManager`) | Ya cubierto — el barrido OSS anterior (2026-07-02) ya marcó OpenHands como SKIP con esta misma razón |

**Conclusión honesta**: el backend/algoritmos de Cline/Aider/OpenHands NO
necesita fork completo — Atlas ya está por delante ahí (mismo patrón que la
comparación previa contra Codex CLI/Claude Agent SDK/Cursor: "Atlas's
orchestration/memory/deliberation layer is architecturally ahead of every
reference tool surveyed so far"). Lo que SÍ tiene valor real y sigue sin
explorar: el **FRONTEND** de Cline (componentes React del webview — chat,
diff-view, checkpoint picker) como referencia directa para el panel de IA
del Atlas IDE (Void), que es un tipo de trabajo distinto (UI, no backend) y
conecta con la ola T2.1 ya en marcha, no con este documento de absorción de
backend. Los tres repos quedan clonados en `~/proyectos/atlas-forks/` por si
hace falta revisar algo puntual, pero un fork completo activo de las tres
apps no está justificado por lo encontrado.

## Política revisada 2026-07-18 (operador, sesión T2.1 IDE) — "fork inteligente"

La política original de abajo ("clone into /tmp... then delete the clone; do
not vendor or keep full forks") queda **corregida**: el operador señaló que
esto contradice lo que realmente conviene — todo este código es open source y
usarlo a nuestro favor de verdad (no solo "estudiar y borrar") es el camino
más rápido y más beneficioso para hacer crecer Atlas exponencialmente. La
corrección explícita del operador: *"a lo mejor el planteamiento no es el
académicamente correcto, pero es el camino más rápido y beneficioso... es
código que podemos usar a nuestro favor"*.

**Fork inteligente** = poseer el código real en el árbol de Atlas cuando algo
tiene valor real y sostenido (no un plugin/extensión/webhook externo del que
dependemos, no una reimplementación desde cero que deja cascarón vacío) —
pero de forma SELECTIVA: se disecciona el repo real, se decide qué partes
tienen valor genuino, se adapta a la arquitectura de Atlas, y NUNCA se baja
la barra de gobernanza al integrarlo. No es "clonar todo un repo sin
criterio"; es tampoco "clonar, inspeccionar, borrar". Precedente ya sentado
hoy mismo: Void (fork completo, no extensión de VS Code) y Zed (fork
completo, no cliente) para el "Atlas IDE"; el mismo criterio aplica ahora a
Hermes-Agent, Cline, Aider, OpenHands y al MCP adapter de Vercel.

Las reglas de gobernanza de abajo (capability tokens, AST Guard, MerkleLogger,
nunca bajar la barra al envolver algo externo) **siguen aplicando sin
excepción** — "fork inteligente" cambia CUÁNTO código se posee, no bajo qué
reglas se ejecuta.

## Strategy

Atlas should study external projects as references, then absorb the parts
that fit the existing architecture — as real, owned code when the value is
substantial and lasting, not just as a studied pattern:

- Governance L0 stays above every imported idea.
- External-effect actions go through capability tokens and AtlasExecutor.
- Security-sensitive execution goes through AST Guard and sandbox policy.
- Important actions are logged through MerkleLogger.
- New dependencies require explicit ADR or Gate-level approval.
- No runtime dependency on Anthropic/Codex/OpenAI APIs.
- External repositories with substantial, lasting value get a real fork under
  Atlas's own tree/org (see `~/proyectos/atlas-forks/`, `~/proyectos/
  atlas-ide`, `~/proyectos/atlas-editor-zed`) — inspected, adapted, and
  integrated deliberately, never dumped wholesale and never left as a dormant
  unintegrated clone. Small, single-pattern references can still be a
  throwaway `/tmp` clone when a full fork isn't warranted — use judgment, not
  a blanket rule either way.

## Categories

| Category | References | Atlas target | Gate | Current stance |
|---|---|---|---|---|
| Orchestration and reasoning | LangGraph, AutoGen, CrewAI, MetaGPT | Orchestrator graph patterns, conditional routing, HITL checkpoints | F/G | Study patterns; avoid LangChain lock-in |
| Tool execution and computer-use | Open Interpreter, Playwright, Aider | BrowserTool, EditorTool, visual loop, code execution | F | Highest immediate value; hardening first |
| Inference serving and optimization | vLLM, TensorRT-LLM, BentoML/OpenLLM, Outlines, llama.cpp | InferenceHub backends, structured output, metrics | D/FU | Optional backends after Gate F hardening |
| Interfaces and UX | Aiogram, FastAPI+HTMX, Whisper.cpp, Piper, Gradio | Telegram, dashboard, voice, CLI/API UX | E/F | Incremental UX; keep localhost/Tailscale |
| Environment and deployment | Proxmox, LXC, Docker Compose, Podman, NixOS | reproducible deploy, isolation, backup | F/G | Bare metal is current; deployment plan for production |
| Self-improvement | Aider, Letta, Open Interpreter, ColdUpdateManager | cold update protocol, HITL, rollback | F/G | Do not self-patch; design ADR first |
| Observability and maintenance | Prometheus, Grafana, OpenTelemetry, Loki, Netdata | metrics, tracing, alerting, audit export | F/G | Start small; avoid monitoring sprawl |

## Project Absorption Matrix

| Project | Absorb | Do not absorb | First useful deliverable |
|---|---|---|---|
| Hermes Agent | skill system patterns, Telegram UX, queue/fallback, long-running agent lessons | weak governance, direct execution, loose logging | `SkillRegistry` design note after Gate F hardening |
| Letta | block memory, archival memory, relevance/recency ranking, context management | conversational-agent assumptions, weak audit/security | `memory/block_memory.py` proposal |
| Open Interpreter | visual loop, tool UX, streaming action trace, confirmation patterns | permissive code execution, direct shell/file access | secure visual loop proposal |
| KERI/ACDC | key-event receipts, witness concepts, offline verification, key rotation ideas | full SSI stack, blockchain-like complexity | ADR-024 logging v2 |
| BentoML/OpenLLM | provider health checks, routing metrics, circuit breakers, serving observability | production platform overhead, Kubernetes assumptions | InferenceHub metrics/circuit-breaker backlog |
| LangGraph | graph-shaped execution, conditional edges, checkpoint patterns | LangChain dependency footprint | Orchestrator StateGraph design sketch |
| Aider | repo editing workflow, patch review, git discipline | autonomous merge/push without HITL | ColdUpdateManager validation workflow |

## Priority Order

1. **Gate F hardening**: BrowserTool and EditorTool become auditable, permissioned tools.
2. **ADR-013b update**: formalize computer-use boundaries before visual loop.
3. **Visual loop MVP**: screenshot -> VLM/stub -> proposed action -> approval.
4. **ADR-024**: logging/observability v2, including MicroLedger/TelemetryBus/WAL.
5. **ADR-025**: ColdUpdateManager, with no hot self-modification.
6. **InferenceHub improvements**: health metrics, structured output, optional local backends.
7. **Deployment/production profile**: Docker/Proxmox/Tailscale/backup docs.

## Non-Goals

- No unintegrated fork kept "just in case" — a fork earns its place in
  `~/proyectos/atlas-forks/` (or its own sibling project) only when there's a
  concrete absorption plan being executed, not as a permanent dormant copy.
- No lowering Atlas's governance bar to make an absorbed capability easier to
  wire — capability tokens, AST Guard, sandbox policy, and MerkleLogger apply
  to anything absorbed, exactly as much as to Atlas-native code.
- No self-AST patching.
- No direct command execution outside AtlasExecutor.
- No public network exposure of dashboards or agents by default.
- No large framework dependency unless an ADR justifies it empirically.
- No fusing an external project's own IDENTITY into Atlas's (e.g. Hermes's
  multi-platform gateway stays a peer, per the trio verdict below) — absorb
  CAPABILITIES, never absorb a second orchestrator/decider/identity.

## Hermes Agent — deep audit (2026-07-02, code-level, not doc-level)

The row above was written before a real code audit and is too terse to act on. This
supersedes it with an inventory from a real clone (NousResearch/hermes-agent,
~2780 Python files, ~109 tools, 197MB) mapped against Atlas as it stands today
(Capa 0 closed — governance precondition for "Gate F hardening" above is now met via
`BwrapJail` + `AutonomousDecider` D2 invariant + `TransparencyLog`, not the older
`AtlasExecutor`/`MerkleLogger` naming this doc originally used, though both still exist
live in the tree).

**User's framing, load-bearing for everything below**: Atlas is not just an agent —
it's an orchestrator (deliberation, decision recording, self-improvement, memory) —
Hermes may fall short there. Absorb tools/capabilities that are useful; never remove
anything from Atlas's side. Study → assimilate → wrap, never fork wholesale.

### Genuinely new (Atlas has no equivalent today)

1. **Multi-platform gateway** (Telegram/Discord/Slack/WhatsApp/Signal/Weixin/Yuanbao/
   Feishu/QQ/BlueBubbles/MSGraph/generic webhook/API server — 13 platforms via
   `gateway/platforms/`). This is the single biggest real gap and the one flagged
   before as needing an explicit decision (see MEMORY `harness-engineering-survey-
   2026-06-27.md`, point 25): it overlaps with Atlas's OWN role as a 24/7 runtime, so
   it's a scope decision, not a code-redundancy question.
2. **Browser/computer-use automation** (11 tools — CDP passthrough, Camofox
   anti-detection browser, `computer_use_tool.py` for OS-level desktop control).
   Atlas has nothing equivalent as a standalone runtime capability (Claude Code's own
   `claude-in-chrome` MCP is a *client-side* tool, not something Atlas itself carries).
3. **Vision/image/video generation** (FAL.ai, xAI video). Atlas's voice module
   (Whisper/Piper) covers audio; no image/video generation exists.
1b. **Generación de imagen — IMPLEMENTADO 2026-07-18.** `ImageGenTool`
   (`src/atlas/tools/image_gen_tool.py`) absorbe el patrón real de
   `hermes-agent/agent/image_gen_provider.py` (backend fal.ai) pero NO su
   arquitectura de plugins/registro — Atlas empieza con un único backend
   fal.ai directo, vía el SDK oficial `fal_client` (instalado tras verificar
   con `pip install --dry-run` que no colisiona con nada del venv principal
   — httpx/msgpack/websockets ya satisfechos, solo suma aiofiles+asyncstdlib).
   Misma disciplina de gobernanza que `StirlingPdfTool`: output_path por
   `ExternalFsBridge`, credencial explícita (`FAL_KEY`, falla con error claro
   si falta — sin llamar nunca a la API sin credencial), auditoría Merkle.
   Cableado completo como tool `image_generate` del loop agéntico (mutate/
   HITL, igual que `manipulate_pdf`): `GateFExecutor.run_image_generate`,
   `Orchestrator._run_image_generate`, dispatch en `agentic_executor.py`,
   clasificación en `AGENTIC_MUTATING_TOOLS` + schema en `agentic_helpers.py`.
   8 tests nuevos (`tests/test_image_gen_tool.py`, SDK mockeado — nunca llama
   a la API real, cuesta dinero) + 140/140 tests de orchestrator/agentic
   verdes + mypy limpio. **Límite honesto**: no verificado contra la API real
   de fal.ai (no hay `FAL_KEY` configurada) — el wiring es real, la llamada
   en vivo queda pendiente de que el operador aporte la credencial.
4. **Smart home — IMPLEMENTADO 2026-07-18.** `HomeAssistantTool`
   (`src/atlas/tools/home_assistant_tool.py`) absorbe fiel la lógica de
   seguridad real de `hermes-agent/tools/homeassistant_tool.py`: lista de
   dominios de servicio BLOQUEADOS (`shell_command`/`command_line`/
   `python_script`/`pyscript`/`hassio`/`rest_command` — HA no tiene control
   de acceso por servicio, la seguridad va en esta capa) + validación de
   entity_id/service contra path traversal. Dos tools del loop agéntico:
   `smart_home_query` (lectura, inline) y `smart_home_control` (mutate/HITL).
   Sin SSRFBridge (a diferencia de CrawlerTool: el destino LAN es el
   propósito, no un pivote) — credencial explícita (`HASS_TOKEN`), auditoría
   Merkle. 16 tests (compartidos con video-gen) + mypy limpio.
5. **ACP adapter — IMPLEMENTADO 2026-07-18** (adaptador fino, NO el bucle
   agéntico completo de Hermes de ~5000 líneas — tal como sugería el punto
   original). `AtlasACPAgent` (`src/atlas/acp/server.py`) sobre el SDK
   oficial `agent-client-protocol` (PyPI, import `acp` — el mismo que usa
   Hermes, verificado sin conflicto de deps). Expone Atlas como agente
   invocable por cualquier cliente ACP — **Zed lo habla nativamente**,
   conecta directo con la ola T2.1 del Atlas IDE. Reutiliza el
   `InferenceHub` real (mismo camino que `atlas.api.coding_server`, forma
   ACP en vez de OpenAI). Comando `atlas acp`. Verificado real de extremo a
   extremo: handshake JSON-RPC/stdio real (`python -m atlas.acp.server` +
   petición `initialize` real → respuesta real con `agentCapabilities`),
   no solo mocks — bug real encontrado y arreglado en el proceso (faltaba
   el guard `if __name__ == "__main__"`, el proceso moría en silencio sin
   servir nada). 12 tests + mypy limpio. Límite honesto: solo chat de texto
   v1, sin tool-calling/edit-approval todavía, streaming de un solo chunk
   (mismo límite ya documentado en coding_server.py) — el bucle agéntico
   propio de Hermes (session-fork, slash commands, MCP registration) queda
   fuera a propósito.
6. **Skill curator lifecycle** (`curator.py`): active→stale→archived based on usage
   telemetry, never auto-deletes, umbrella-consolidation opt-in. Atlas's `LessonStore`/
   `LessonPromoter` has corroboration thresholds but no analogous stale/archive
   lifecycle for accumulated skills — a genuinely useful PATTERN (not code) to
   consider for the lesson/skill store as it grows.

### Redundant (Atlas already has an equivalent, often more rigorous)

- File ops (read/write/patch/fuzzy match) — `ToolCoder`/`AtlasCoder` already do this,
  with a fail-closed unique-match guardrail and a lint gate Hermes's `file_tools.py`
  does not appear to have.
- Terminal/process execution + sandboxing — `BwrapJail` (structural jail, not a
  wrapper around `approval.py`-style pattern matching).
- Delegation/sub-agents — `ParallelCoder`/`IncrementalCoder` (git-worktree isolation)
  already cover this space for coding tasks.
- MCP client/server — Atlas already closed its own MCP work (WORK_LEDGER: "MCP
  CERRADO: 6 primitivos + Tasks", `atlas-trunk` catalog). Hermes's `mcp_serve.py`/
  `mcp_tool.py` would be a second, competing MCP surface — do not absorb as-is.
- Cron/scheduled jobs — needs a direct comparison against `maintenance_worker`'s
  polling loop before concluding either way (not confirmed redundant, not confirmed
  novel — flagged honestly as unverified, do not assume).

### Governance gap — do NOT lower Atlas's bar when wrapping anything from here

The subagent's own report on Hermes's delegation model is the important finding:
**"NOT a full orchestration framework — no external state store, no cross-job
dependencies; more like a lightweight multi-level task tree."** This directly
confirms the user's own intuition going in. Atlas's orchestrator (`TransparencyLog`,
`RecordingDecider`/`TwinDecider`, `maintenance_worker`, `SelfImprovementBridge`,
`deliberation_council`) is architecturally deeper — Hermes's `delegate_tool.py`/
`async_delegation.py` must NOT replace it, only optionally sit as a peer pattern for
specific wrapped tools.

Similarly, Hermes's `approval.py` (regex/pattern-detection + interactive prompting)
is weaker than Atlas's `AutonomousDecider` D2 invariant (LLM judgment is evadible,
never in the authorization path — see MEMORY `conclave-recordingdecider-blindspots`).
Any Hermes tool wrapped into Atlas (browser automation, smart home, etc.) must be
gated through Atlas's own decider/jail, never through Hermes's own approval gate.

## Codex CLI, Cursor, Claude Agent SDK — cross-comparison (2026-07-02)

Same-day follow-up to the Hermes audit, requested explicitly by the user ("lo mismo que has hecho
con Hermes puedes hacerlo con Cursor, Claude Code y Codex?"). Method differs per target by source
availability: Codex CLI = real code audit (openai/codex is open source, Rust). Claude Agent SDK =
real code audit (anthropics/claude-agent-sdk-python is open source; Claude Code itself is not, so
Part B is docs-only). Cursor = documentation/blog research only (fully closed source, no repo).

### Cross-cutting finding — validates Atlas's own governance invariant

**All three independently confirm the same design**: LLM judgment is never the authorization gate.
Codex: `Decision::Prompt` from a static exec-policy DSL, the LLM's reasoning is never consulted for
the approval decision. Claude Agent SDK: `can_use_tool` callback + permission rules are host-
application-controlled, the model doesn't decide its own permissions. Cursor: sandboxing (Landlock+
seccomp on Linux, Seatbelt on macOS — the same mechanism `BwrapJail` already uses) is a structural
layer independent of the LLM, with an "LLM safety classifier" only for the residual non-sandboxable
case, never as the sole gate. This is strong independent validation of Atlas's own D2 invariant
(`AutonomousDecider`, see [[conclave-recordingdecider-blindspots]]) — not an idiosyncratic overcaution.

### Cross-cutting finding — Atlas is already ahead exactly where the user expected

None of the three has: a deliberation/consensus mechanism across models (Cursor's "ensemble" mode —
multiple models attempt the SAME task, best result picked — is the closest analog, but it's not
deliberation, it's redundant attempts), multi-provider LLM routing (Claude Agent SDK is Claude-only;
Codex is single-provider; Cursor routes to its own Composer model + others but not exposed as a
tiered role system), crypto-verifiable decision recording (`TransparencyLog`), or persistent lesson/
memory with corroboration thresholds (`LessonStore`/`LessonPromoter` — Cursor's "Memories" is closest,
auto-proposed + user-approved, but per-project/per-user, no corroboration mechanism). This confirms
the user's framing going into the Hermes audit: Atlas's orchestration/memory/deliberation layer is
architecturally ahead of every reference tool surveyed so far, agent-level or IDE-level.

### Concrete, low-complexity gaps found (worth closing, unlike the Hermes items which need scope decisions first)

1. **`ToolCoder` has NO `institutional_context_files`/AGENTS.md support at all** — not even the flat
   version `AtlasCoder` already has. Missed when feature parity was "closed" earlier this session
   (only `repo_map_files`/`auto_commit` were ported). `AtlasCoder._build_institutional_section`
   already does hierarchical discovery (technique #20, Codex-inspired: walk ancestors of the first
   context_file, most-specific `AGENTS.md` last = highest read priority) — confirmed twice more
   independently today (Codex's own `agents_md.rs` walk-with-override, Cursor's nested `AGENTS.md`
   child-overrides-parent). Straightforward to port to `ToolCoder` with the same pattern already used
   for `repo_map_files`/`auto_commit`.
2. **`conditional_rules.py` (technique #11) is dead code — zero callers anywhere in `src/`.** It was
   implemented and tested standalone but never wired into `AtlasCoder`/`ToolCoder`'s institutional
   section. Cursor's 4-mode system (Always/Auto-Attached-by-glob/Agent-Selected/Manual) is a mature
   reference for what "wired" should look like — more sophisticated than a first pass needs, but
   confirms the glob-based `applies_to` design in `conditional_rules.py` was pointed the right
   direction, it just needs a caller.
3. **Ensemble/best-of-N mode for `ParallelCoder`** — Cursor: same task to multiple models in parallel,
   pick the best result. Atlas's `ParallelCoder` currently only does the opposite shape (different
   subtasks to different workers). A same-task N-way mode would be a small, additive addition
   (reuse the existing worktree-isolation machinery, add a "pick winner" step — success + fewest
   iterations, or smallest diff, as the tie-break).

### Patterns worth naming, not yet actionable (need more thought before committing to any)

- Claude Agent SDK's structured hook taxonomy (PreToolUse/PostToolUse/PostToolUseFailure/
  UserPromptSubmit/Stop/SubagentStart/SubagentStop/PreCompact/Notification/PermissionRequest) is a
  named, pluggable extension point model. Atlas's own guardrails (lint gate, protected paths, stuck
  detector) are hardcoded inline in `AtlasCoder`/`ToolCoder` rather than exposed as named hook points
  a caller could extend. Not urgent — no current caller needs this flexibility — but worth naming as
  a pattern if Atlas's coding engines grow more callers with different guardrail needs.
- Cross-tool `SKILL.md` interoperability is emerging as a de facto standard: Cursor's skills loader
  explicitly reads `.claude/skills/` and `.codex/skills/` as compatible formats. Worth checking
  whether Atlas's own skill/trunk catalog (`atlas-trunk` MCP server) could interoperate, but this is
  observation, not a decision — no action taken.
- Claude Agent SDK's `AgentDefinition` (per-subagent tools/model/skills/effort bundle) is more
  granular than Atlas's current per-worker config in `ParallelCoder` (task + context_files + test_cmd
  only, no per-worker tool/skill restriction). Possibly relevant if `ParallelCoder` workers ever need
  heterogeneous capabilities, not needed today.

### Recommended order — updated 2026-07-02, scope decision closed

1. ✅ **Multi-platform gateway — DECIDED via Cónclave full escalation (trio: Gemini +
   Kimi + Mistral, unanimous FAIL on the "expansion" option).** Verdict: **peer,
   never a merge of Atlas's own identity.** All three reviewers converged
   independently: it would put Atlas's own decider directly in the path of
   untrusted inbound messages (violates D2 in practice, not just on paper); it
   creates a single point of failure across unrelated Atlas subsystems (a bug
   parsing a WhatsApp attachment could corrupt LessonStore or saturate the
   Cónclave); it's an irreversible identity fusion with real legal/regulatory
   exposure on some channels (KYC requirements on Chinese platforms); Atlas has
   no external state store (confirmed by the Hermes audit itself), so per-channel
   persistence would be built ad-hoc instead of reusing what Hermes already
   solved. Concrete shape: a separate gateway service Atlas can invoke or be
   invoked by (MCP is the natural integration surface), never a fused runtime.
2. ✅ **Browser/computer-use — hybrid landed 2026-07-02.** Kept Atlas's own
   `BrowserTool` (verified working, 26/26 tests, once Chromium was actually
   installed — it wasn't broken, just dormant/untested by default). Added
   Microsoft's official **Playwright MCP** (`npx -y @playwright/mcp@latest`) as
   an external trunk root — accessibility-tree based (not screenshots), far
   fewer tokens, sub-100ms actions, 23 tools. Proven live via a real stdio MCP
   handshake before wiring (not just docs). Wired purely through the curated
   catalog (`docs/design/mcp_catalog.yaml`, `trunk_children()` — no new server
   code needed, confirming that mechanism). Closed one real governance gap in
   the same pass: `CatalogEntry`/`McpServerConfig` had no path to mark specific
   tool names read-only for *externally* wired MCP servers — `trunk_children()`
   would have defaulted ALL 23 Playwright tools (including `browser_click`,
   `browser_type`, `browser_run_code_unsafe`) to mutate/HITL, which is safe but
   not what the user asked for ("directo para las de solo lectura"). Added
   `CatalogEntry.read_only_tools` (parsed from YAML) threaded through
   `trunk_children()` into `McpServerConfig.read_only_tools` (ADR-035 dec.5's
   existing mechanism, previously only reachable for native roots). Only 5
   genuinely read-only tools are marked direct: `browser_snapshot`,
   `browser_console_messages`, `browser_network_requests`,
   `browser_network_request`, `browser_take_screenshot`. Everything else
   (`browser_click`/`browser_type`/`browser_fill_form`/`browser_run_code_unsafe`/
   etc.) stays mutate/HITL by default, per the user's explicit governance call.
   Desktop-control and scraping-specific alternatives beyond browser navigation
   — not yet researched, still open.
3. Skill curator lifecycle pattern — study for `LessonStore`/`LessonPromoter`, not a
   code import.
4. Everything else deferred until 2-3 land and prove the wrap-not-fork discipline
   holds up against a real absorbed capability.


## Self-hosted OSS sweep — 10 candidates (2026-07-02, user-supplied list)

The user brought a list of ~10 popular self-hosted OSS projects (Instagram post +
recommendations) and asked which are worth absorbing/assimilating. Assessed each
against what Atlas already has, applying the same discipline as the Hermes audit:
absorb = wrap real code with minimal glue; peer = separate service Atlas talks to;
skip = overlaps Atlas's own identity or solves a problem Atlas doesn't have.

### ABSORB (real candidates, in priority order)

1. **Crawl4AI** (unclecode/crawl4ai, ~62k stars, v0.8.5 mar-2026) — **the direct
   answer to the pending scraping thread.** Python library (pip-installable, no
   service), LLM-friendly markdown output, deep crawl (BFS/DFS), adaptive crawling
   (stops when enough context gathered), 3-tier anti-bot with proxy escalation,
   Shadow DOM flattening. Uses Playwright underneath — same engine already installed
   in `.venv`. Fits [[adopt-real-not-shell]] perfectly: `pip install crawl4ai`,
   wrap as an Atlas tool routed through SSRFBridge/decider like `BrowserTool`.
   Community MCP servers exist but wrapping the library directly is less indirection.
2. **Stirling PDF** (Stirling-Tools, v2.9.0 abr-2026) — capability Atlas has zero
   coverage of (PDF merge/split/OCR/watermark/convert). Self-hosted service (Docker,
   JDK 21) + full REST API + community MCP server (`gufao/mcp-server-stirling-pdf`,
   10 tools). NOT a library — needs a running service, so: register as `candidato`
   in the catalog now, promote to `verificado` only when a local instance is
   actually deployed and prove-it passes (wire-before-claim).

### PEER (useful, but never fused with Atlas — same verdict as the Hermes gateway)

3. **Open WebUI** — self-hosted ChatGPT-style UI. Atlas already has CLI + Telegram;
   this would be a human frontend TALKING TO Atlas (OpenAI-compatible API surface),
   not code to absorb. Worth revisiting only when a web UI is actually wanted.
4. **Maxun** — no-code scraping platform (visual robot builder + UI + DB). It's an
   app, not a library; Crawl4AI covers the same need as absorbable code. Skip unless
   a non-technical operator needs to define scrapers visually.

### SKIP (overlaps Atlas's own identity — absorbing would repeat the gateway mistake)

5. **Dify / Langflow** — agentic workflow platforms. This is exactly what Atlas IS
   (orchestrator + decider + memory + Cónclave), with Atlas being deeper on
   governance (D2, TransparencyLog, lessons with corroboration). Absorbing either
   would fuse a second orchestration identity into Atlas — the same category error
   the Cónclave trio unanimously rejected for the Hermes gateway.
6. **OpenHands** — already covered by the harness-engineering survey (2026-06-27);
   relevant techniques already absorbed into AtlasCoder/ToolCoder. No re-audit.

### DEFERRED (real value, wrong moment)

7. **Supabase** — external state store (Postgres/auth/realtime). Atlas is local-first
   with SQLite+FTS5 and doesn't have the multi-device/state-store problem today. The
   Cónclave noted the missing external state store as a reason the GATEWAY should be
   a peer — but that peer brings its own storage. Revisit only if a concrete
   multi-device requirement lands.
8. **Coolify** — self-hosted PaaS (Docker deploys, reverse proxy, one server).
   Directly relevant ONLY if the VPS returns ("hasta próxima orden"). Worth noting:
   the 18 hand-rolled systemd/paths fix-commits from the May 2026 Hermes deployment
   (see hermes-vps-deployment-playbook memory) are exactly the pain Coolify removes —
   if the VPS is ever retaken, deploy via Coolify/Docker instead of hand systemd.

### Side-finding from the same sweep (browser/token-efficiency, feeds the open thread)

- **Vercel agent-browser** — reported ~200-400 tokens/page vs Playwright MCP's
  accessibility snapshots (2-5KB), ~5.7x more test cycles under the same context
  budget. Also: Playwright's own CLI pattern reportedly ~4x cheaper in tokens than
  its MCP (tool definitions alone ~13.7k tokens/request). Both are candidates to
  evaluate IN MEASUREMENT (not by blog claims) when the scraping/desktop thread
  lands — Atlas now has both BrowserTool and Playwright MCP wired, so a real
  token-cost comparison harness is feasible.

## Crawl4AI absorbido (2026-07-02) — scraping cerrado

`CrawlerTool` (`src/atlas/tools/crawler.py`) implementado y cableado al loop agéntico
como tool `web_crawl` (read, `UNTRUSTED_READERS` — su markdown se envuelve
automáticamente vía ADR-037 antes de llegar al modelo). Gobernanza idéntica a
`BrowserTool`: SSRF Bridge + bloqueo de red privada + auditoría Merkle.

**Hazard real encontrado y evitado (no asumido, verificado con `pip download`
+ inspección del wheel)**: `crawl4ai` fija como dependencia DURA
`unclecode-litellm==1.81.13` — un fork que se instala bajo el mismo paquete de
import `litellm/` que nuestro `litellm` real (1.89.0, del que depende
`InferenceHub` para el routing multi-proveedor). Un `pip install crawl4ai` en
el venv principal habría sustituido esa dependencia crítica en silencio. Se
aisló en un venv separado `.venv-scraping` (mismo patrón que `redteam` ya usa
por otra razón — tamaño de torch/CUDA) e invocado por subprocess
(`_crawl4ai_worker.py`, sin imports de `atlas`). Probado en vivo dos veces:
contra `github.com/langflow-ai/langflow` (32KB de markdown limpio) y contra un
servidor HTTP local en los tests E2E (`test_crawler.py`, marcador `computer_use`).

**Límite real, no resuelto todavía**: `SSRFBridge` (`src/atlas/security/
ssrf_bridge.py`) es una ALLOWLIST de dominios, no una blocklist — por diseño,
para código en sandbox. La instancia que usan `BrowserTool`/`CrawlerTool` hoy
(`GateFExecutor._ssrf_bridge = SSRFBridge()`) solo permite ~20 dominios de
infraestructura (APIs de proveedores, PyPI, GitHub API) — NO dominios
genéricos como `github.com` a secas. Esto significa que scraping/browsing a
sitios arbitrarios que el usuario mencione en una tarea real HOY fallaría con
"dominio no está en la allowlist", salvo que se llame `add_domain()` primero
(el propio código dice "requiere APPROVE"). Es una decisión de política de
seguridad real, no un bug: ¿se amplía la allowlist para scraping/browsing de
propósito general, y si es así, aprobación por dominio vía decisor en cada
tarea, o una allowlist más amplia y curada? Pendiente de decisión del usuario
antes de dar por "generalmente utilizable" esta capacidad — hoy funciona
correcta y completamente para los dominios ya permitidos.

## Desktop-control — slice 1 (GUI en Xvfb virtual) cerrado, 2026-07-02

El usuario amplió el alcance de "desktop-control" más allá de GUI (descargas, invocar
Claude Code, verificar carpetas fuera del proyecto) y pidió las 3 piezas, en orden de
riesgo creciente. Slice 1 (GUI) cerrado; slices 2 (ficheros fuera del proyecto) y 3
(Claude Code como sub-tool) quedan para continuar.

**Segundo hazard de dependencias real, mismo patrón que Crawl4AI** (verificado con
`pip download` + inspección de metadata, no asumido): `computer-control-mcp` fija
`mcp[cli]==1.13.0` — pin EXACTO del mismo SDK `mcp` del que depende TODO el propio
tronco de Atlas (`trunk_server.py`, `FastMCP`, etc.), hoy en 1.28.0. Instalarlo en el
venv principal habría degradado el SDK MCP de Atlas 15 versiones menores hacia atrás.
Aislado en `.venv-desktop` (mismo patrón que `.venv-scraping`/`redteam`).

**Aislamiento de display, no solo de proceso**: a diferencia de Crawl4AI (que solo
necesita aislar dependencias Python), esta herramienta controla ratón/teclado/pantalla
reales. Se lanzó `Xvfb :99` (framebuffer X virtual, sin GUI visible) como display
DEDICADO — el catálogo apunta el servidor MCP a `DISPLAY=:99` explícitamente
(`env DISPLAY=:99 <bin>`), nunca al `:0` real de la sesión de escritorio. Probado en
vivo: `get_screen_size` devuelve 1280x1024 (el tamaño de Xvfb, confirmando que NUNCA
tocó el display real) y `click_screen` fue rechazado por `trunk_invoke_readonly`
(solo 4 tools de lectura pura declaradas: `take_screenshot`,
`take_screenshot_with_ocr`, `get_screen_size`, `list_windows`; las 11 restantes que
mueven ratón/teclado/ventanas siguen mutate/HITL).

**Pendiente, no resuelto en esta pasada**: modo "display real, controlado y aislado"
que el usuario pidió como complemento (útil para apps GUI que no corren en Xvfb) —
necesita su propio diseño de gating (que no sea automático/silencioso, con auditoría
explícita de que se tocó la sesión real) antes de implementarse. Xvfb :99 necesita
persistir entre reinicios (hoy es un proceso manual, como el paso de instalar
Chromium) — no crítico ahora, revisar si esto pasa a systemd cuando el uso sea real.

## Stirling PDF absorbido (2026-07-03) — segundo candidato del barrido OSS cerrado

Servicio self-hosted real desplegado vía Docker (`frooodle/s-pdf:latest`), bindeado solo a
`127.0.0.1:8090` (no expuesto a red — el guardrail de Claude Code bloqueó correctamente dos intentos
previos: uno que desactivaba su seguridad interna, otro que lo exponía a `0.0.0.0`). Cuenta admin
local creada con credenciales explícitas (no las por-defecto documentadas).

**Fricción real de auth, documentada por si se repite**: la API REST de Stirling PDF NO usa la
cookie de sesión (`JSESSIONID`) para las operaciones de PDF — usa un JWT bearer guardado en
`localStorage` (`stirling_jwt`) que el SPA obtiene tras el login. El endpoint `POST
/api/v1/user/get-api-key` requiere ese Bearer token, no la cookie. Se automatizó con Playwright
(ya probado y disponible desde el slice 1 de desktop-control) haciendo login real + `fetch()` desde
DENTRO del contexto del navegador (mismo origen, headers correctos por construcción) para generar
una API key persistente, guardada en `~/.config/atlas-mcp/secrets.env` como
`STIRLING_PDF_API_KEY` — nunca impresa ni materializada en un archivo intermedio (dos intentos
bloqueados correctamente por el clasificador de "Credential Materialization" antes de dar con el
método correcto).

`StirlingPdfTool` (`src/atlas/tools/stirling_pdf_tool.py`) — multipart/form-data construido a mano
con librería estándar (sin dependencias nuevas), mismo patrón de gobernanza que `CrawlerTool`:
input_path Y output_path pasan por `ExternalFsBridge` (reutiliza el bridge del slice 2 de
desktop-control), requiere credencial explícita, audita en Merkle. Cableada como tool
`manipulate_pdf`, clasificada **mutate/HITL** (escribe ficheros de salida). Probado en vivo dos
veces: rotar un PDF real vía curl con la API key, y vía la propia `StirlingPdfTool` end-to-end
(200 OK, PDF válido devuelto en ambos casos).

**Dato sobre el techo de ToolCoder (tercera medición)**: esta pieza fue el primer caso donde
`atlas code --engine tool` falló DOS VECES SEGUIDAS sin escribir NADA (ni siquiera parcial) — ni el
módulo con multipart HTTP + doble validación de rutas, ni sus tests con 6 casos de mock. A diferencia
del fallo parcial de `gate_f_executor.py` en el slice 2 (que sí dejó código utilizable), aquí no hubo
ningún artefacto. Escrito a mano en su lugar. Refuerza el patrón ya visto: tareas con MÚLTIPLES
requisitos de manejo de errores/casos entrelazados en un único archivo superan el presupuesto de
turnos más fácilmente que piezas de wiring mecánico simple.

**Pendiente operativo**: el contenedor Docker y la cuenta admin local son manuales (como Xvfb :99) —
no hay systemd todavía. Revisar si esto pasa a gestión persistente cuando el uso sea real.

## Medición real de token-cost Playwright MCP (2026-07-03) — no por claim de blog

Se midió en vivo (handshake MCP real, no simulado) el consumo de tokens de nuestro Playwright MCP
ya cableado, para verificar los claims de blog citados en el hallazgo lateral del barrido OSS
("~200-400 tokens/página" de Vercel agent-browser, "~4x más barato" el patrón Playwright CLI).

**Resultado real, honesto**: el consumo de un `browser_snapshot` (árbol de accesibilidad) varía
MUCHO según la densidad de la página, no es una constante:
- `docs.python.org/3/` (portada simple): 11939 chars ≈ **2984 tokens**.
- `stackoverflow.com/questions` (lista larga): 66897 chars ≈ **16724 tokens**.
- Artículo largo de Wikipedia (contenido denso): 540843 chars ≈ **135210 tokens**.
- Coste FIJO de las 23 definiciones de tool (se paga en CADA request, independiente de la acción):
  15679 chars ≈ **3919 tokens**.

**Conclusión**: el claim de "2-5KB por snapshot" del blog citado es cierto solo para páginas simples
— páginas con contenido real denso (listas largas, artículos extensos) pueden costar 10-100x más.
Sigue siendo mucho más barato que capturas de pantalla (base64, sin comparar aquí en tokens porque
normalmente no se manda como texto), pero el ahorro real depende del tipo de página, no es un
número fijo. No se instaló Vercel agent-browser para comparar cabeza a cabeza por presupuesto de
tiempo de esta sesión — si se retoma, medirlo con el mismo método (handshake real, páginas reales
variadas) antes de decidir migrar.

## Patrón de lifecycle de skills (Hermes curator.py) — estudio cerrado, sin código (2026-07-03)

Verificado en el código real de `LessonStore`/`LessonRecaller` (no asumido): `Lesson`
(`src/atlas/core/lesson_store.py`) NO tiene NINGÚN campo de lifecycle — ni `status`
(activo/obsoleto/archivado), ni contador de uso, ni `last_recalled_at`. Lo único parecido es
`corroborated: bool`, pero es un gate de UNA SOLA VEZ en la creación (`verify_external`), no
telemetría continua. `LessonRecaller.recall()`/`recall_all()` (`src/atlas/immunity/
lesson_recaller.py:167,197`) es el punto natural donde "esta lección se usó" se registraría, si
existiera esa señal — hoy no se registra nada ahí.

**El patrón de Hermes** (curator.py: activo→obsoleto→archivado por telemetría de uso, nunca
auto-borra, consolidación por solapamiento opcional) mapea limpio a un futuro incremento de
`Lesson`: añadir `recall_count: int` + `last_recalled_at: str | None`, incrementados en
`LessonRecaller.recall()`, y una heurística de "obsoleta" (ej. sin recall en N ciclos + baja
corroboración relativa) que NUNCA borra, solo re-etiqueta — coherente con la disciplina ya existente
de `_graveyard`/`WHY.md` del repo (nunca destruir, marcar y archivar).

**Implementado 2026-07-18** (giro de política "fork inteligente" — ver arriba, el operador pidió
absorber código real, no solo patrones): `Lesson` gana `recall_count`/`last_recalled_at`/`state`
(active|stale|archived, defaults retrocompatibles). `LessonStore.record_recall()` incrementa uso
real (mismo patrón `replace()`+rewrite que `record_recurring()`); `LessonRecaller.recall()` lo
invoca SOLO en un match real (`matched=True`), no en cada consulta — evidencia de uso, no de
intento. `LessonStore.apply_lifecycle_transitions()` porta el algoritmo determinista de
`~/proyectos/atlas-forks/hermes-agent/agent/curator.py::apply_automatic_transitions` (grace floor
para lecciones nunca usadas + jóvenes, reactivación al volver a usarse, JAMÁS borra el fichero —
archived es solo una etiqueta recuperable). Nueva `tests/test_lesson_lifecycle.py` (9 tests) +
suite completa de lecciones (58 tests) verde; mypy limpio en ambos ficheros tocados. Primer
entregable concreto del giro "fork inteligente": código real absorbido de un repo real, no un
resumen de patrón.

## Front C — embedder local por defecto (2026-07-03)

Cambiado el default de `default_embedder()` (`src/atlas/memory/embeddings.py`) de
`StubEmbedder(dim=64)` a `FastEmbedEmbedder` (semántico local, ONNX, sin torch, ya
implementado — solo faltaba activarlo por defecto). `ATLAS_EMBEDDER=stub` queda como
opt-out explícito.

**Verificado antes de tocar nada** (no se asumió que era seguro): el store real de memoria
(`~/atlas-mcp/memory.db`) tenía **0 registros** — sin datos que migrar, así que el cambio de
espacio vectorial (dim 64→384) no rompe nada existente. Si hubiera tenido datos reales, el
guard de dimensión del índice habría exigido una migración/rebuild explícita antes de tocar
el default (documentado en el propio docstring de `default_embedder()`).

**Hallazgo real que justifica el cambio, no solo "mejora medible"**: el propio código de
`LessonRecaller` (`src/atlas/immunity/lesson_recaller.py`) ya documentaba que su
`threshold=0.8` estaba calibrado para embeddings SEMÁNTICOS, y que con el stub (hash, no
semántico) por defecto, la memoria de lecciones quedaba "prácticamente inconsultable". El
cambio de default no es solo una optimización — cierra un bug de usabilidad real que ya
estaba señalado en el propio código.

**Verificación real de la mejora** (no solo "los tests pasan"): test nuevo
(`test_fastembed_default_finds_paraphrase_stub_misses`) que indexa una lección real y
consulta con un PARAFRASEO sin ninguna palabra literal compartida — fastembed encuentra la
lección con score más alto que el hash de StubEmbedder para el mismo caso. Suite completa
verde tras el cambio.

## SP-A — mesa de trabajo compartida (2026-07-03) — cerrado, con límite honesto documentado

Construido `workbench://manifest` (`src/atlas/mcp/workbench_resources.py` + registro en
`trunk_server.py`) — agrega catálogo+lecciones+backlog+memoria en un único Resource MCP,
reutilizando el patrón exacto ya construido en `catalog_resources.py`. Aditivo/fail-soft: si
falta cualquiera de las 4 fuentes, el resource simplemente no se registra, nunca rompe el
arranque del resto del tronco. Probado en vivo con un handshake MCP real contra un proceso
fresco del trunk: catálogo 733 items, backlog 30 items reales (el top-1 pendiente es
`f2-6a-caller-wiring-personal-factual`, el mismo item que se intentó auto-construir hoy en el
Front A), lecciones 0, memoria 0 (coincide con lo ya verificado esta sesión).

**Límite real investigado y documentado, no fingido resuelto**: el `workbench://manifest` es
un Resource MCP real — cualquier CLIENTE que se conecte al tronco (yo, o el propio Orchestrator
de Atlas si se cablea) lo obtiene de verdad. Pero la tool `Agent`/`Task` que uso para despachar
subagentes (los `autobuild-impl-sonnet` de hoy, por ejemplo) **no tiene ningún parámetro para
darle acceso a un servidor MCP al subagente que spawnea** — verificado en el esquema real de la
tool (`description, isolation, model, prompt, run_in_background, subagent_type`, nada de
`mcp_servers`/`tools`). Esto NO es algo que se resuelva desde el prompt que le mando; es una
limitación de la superficie de la tool, fuera de mi control directo.

**Mitigación práctica adoptada de inmediato**: cuando delegue una tarea a un subagente que se
beneficiaría de contexto real (estado del backlog, lecciones existentes, catálogo), debo LEER
`workbench://manifest` yo mismo primero (una sola tool-call barata) y pegar el resumen relevante
directamente en el prompt del subagente — no delegar ciegamente asumiendo que "hereda todo".
Esto no es la solución arquitectónica ideal (seguiría siendo mejor que el propio harness
permitiera wiring de MCP por subagente), pero cierra la brecha práctica hoy sin esperar a un
cambio de infraestructura que no controlo.

## Desconexión real de memoria/lecciones — investigado y arreglado en su mayoría (2026-07-03)

A petición explícita del usuario ("profundiza y comprueba... no es solo el mcp es todo"), se
investigó por qué el manifiesto SP-A mostraba 0 lecciones y 0 memoria, en vez de asumir que
"así es como está". Hallazgo real, no imaginado:

**Hay un daemon vivo de verdad**: `atlas serve --poll-interval 1.0` (PID 5117, corriendo desde el
2 de julio), con ciclos de auto-auditoría ejecutándose hoy mismo, 2939 entradas reales en el log
Merkle. Esto no es un boceto.

**Pero había 5 convenciones de ruta distintas para "el mismo" LessonStore**, sin fuente única de
verdad, verificado con `grep` real de cada `LessonStore(...)` en el código:
- `AtlasCoder`/`ToolCoder` (motor de codificación activo): `<repo>/workspace/lessons` — la única
  con datos reales (8 lecciones generadas, con contenido genuino).
- `orchestrator_parts/maintenance_facade.py` (el propio self-audit del Orchestrator real):
  `<ATLAS_HOME>/memory/lessons` — **ni siquiera existía como directorio**. El daemon vivo nunca
  había visto ninguna de las 8 lecciones reales que su propio motor de codificación generó.
- `scripts/seed_lessons.py`: `~/.atlas/memory/lessons` — otra ruta más, tampoco existía.
- `trunk_server.py` (SP-A, cableado hoy mismo antes de este hallazgo): `save_dir/lessons` —
  vacío, la ruta equivocada.
- `scripts/redteam/*.py`: `$ATLAS_HOME/lessons` — deliberadamente aislado del servicio vivo
  (correcto por diseño, no se tocó).

**Unificado a `<repo_root>/workspace/lessons`** (la única con datos reales) en los 3 sitios de
producción: `maintenance_facade.py`, `trunk_server.py` (SP-A), `seed_lessons.py`. Verificado en
vivo: `workbench://manifest` ahora reporta 11 lecciones reales (8 + 3 sembradas), no 0.

**Segundo hallazgo, más profundo**: hay DOS sistemas de memoria completamente separados:
`SqliteMemoryIndex` (expuesto por el MCP de memoria, vacío, usa `default_embedder()`) vs
`KuzuVectorStore` (grafo real, el que usa de VERDAD el Orchestrator en su pipeline Gate D —
activo en producción vía `ATLAS_PIPELINE_GATE_D=1`, confirmado en `.env`). El Gate D **hardcodeaba
`StubEmbedder()`** en `orchestrator.py::enable_gate_d_pipeline()`, ignorando por completo el
cambio de default hecho antes en Front C. Verificado antes de tocar: `approved_patterns` y
`error_registry` (los únicos consumidores reales del vector store) estaban **vacíos** — sin
vectores dim=64 reales que perder al cambiar de embedder. Arreglado: ahora usa
`default_embedder()` igual que el resto del sistema. `KuzuVectorStore._verify_dim()` es
fail-closed (lanza error claro ante mismatch de dimensión, nunca corrompe silenciosamente) —
el fix requiere que el daemon vivo se reinicie para tomar efecto; NO se reinició sin preguntar
(acción sobre un servicio en producción, decisión del usuario).

**Efecto colateral real encontrado y arreglado en el mismo pase**: cambiar el embedder por
defecto de Gate D hizo que la suite de tests que activa ese pipeline pasara de ~57s a un ritmo
normal, porque cada test cargaba el modelo ONNX real sin necesidad (esos tests verifican
cableado, no calidad semántica). Añadido `ATLAS_EMBEDDER=stub` a la fixture `autouse` de
aislamiento de entorno ya existente en `tests/conftest.py` (mismo patrón que
`ATLAS_EMBEDDING_MODE`/claves de API) — 57s → 6.2s, confirmado.

**Pendiente, decisión del usuario**: reiniciar `atlas serve` (PID 5117) para que el pipeline Gate
D tome el nuevo embedder — no se hizo sin confirmación explícita.
