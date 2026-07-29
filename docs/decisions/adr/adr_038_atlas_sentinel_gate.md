# ADR-038 — Gate de adopción "Atlas Sentinel" (muralla P0 de adopción)

- Status: **Accepted** (2026-05-31) — slice 1 implementado
- Módulo: `src/atlas/security/sentinel_gate.py`, enganchado en
  `src/atlas/mcp/registry.py`
- Depende de: ADR-035 (cliente MCP — trae la superficie de adopción), ADR-036
  (threat model), ADR-037 (frontera de contenido no confiable)
- Habilita: registro dinámico de MCP y, a futuro, el agente de
  auto-mantenimiento (que descubre/propone servers que este gate debe vetar)

## Disposición en ATLAS DEFINITIVE CANDIDATE (2026-07-27)

La decisión sigue aceptada. La tabla de capas describe capacidad de código, no
estado vivo universal: el suelo IOC no anulable corrige la antigua blocklist
vacía; `revet_all` está cableado pero su tick sigue siendo opt-in. La existencia
del gate no convierte un MCP remoto en admitido ni permite auto-adopción: siguen
mandando ADR-075 y el rechazo explícito de ADR-076 C.

## Contexto

ADR-035 trajo el cliente MCP: Atlas puede arrancar servers externos y exponer sus
tools al loop. La **adopción** de un server es la operación peligrosa de la cadena
de suministro: un server malicioso o un *update envenenado* (caso Postmark; estudio
ToxicSkills 36 %) inyecta tools que roban credenciales, hacen squatting de nombres,
o cambian de comportamiento tras ser aprobadas una vez ("registrations approved
once, not re-verified").

El proyecto `claude-mcp-sentinel` documenta la tesis correcta — **skills y MCP no
son confiables por defecto** — como hook de Claude Code. **No instalamos su código**
(sería, irónicamente, otra decisión de cadena de suministro y un hook fail-open que
no debe romper Claude Code). Robamos el *concepto* y lo construimos nativo y
**fail-closed para adopción**: aquí la operación peligrosa es adoptar, así que si no
se puede vetar, no se adopta.

## Decisión

Un `SentinelGate` veta cada `McpServerConfig` y su superficie de tools en el único
punto de adopción real que existe: `McpRegistry._start_one`, tras `tools/list` y
antes de registrar las tools en el loop. Implementación **por capas**, empezando por
las de mayor impacto/menor coste (stdlib, sin deps — regla 6), dejando las que
necesitan infra inexistente para slices posteriores.

| # | Capa | Qué hace | Estado |
|---|------|----------|--------|
| 1 | **Identidad criptográfica + snapshot (anti rug-pull)** | `sha256(name+description+inputSchema)` por tool. Primera adopción = TOFU: admite y graba snapshot en `memory/sentinel/<server>.json`. Después: hash distinto (drift) o tool nueva en server conocido ⇒ **bloqueado** hasta re-aprobación humana | ✅ |
| 2 | **IOC + coherencia de comando** | El `cmd` es argv (nunca shell, ADR-035): un token con metacaracteres de shell (`;`, `\|`, `$(`, …) es smuggling ⇒ veta el server. Blocklist inyectable de dominios/comandos veta tool o server. La excepción para módulos nativos exige la ruta léxica del intérprete del proceso Atlas, el checkout que contiene el Sentinel ya cargado (nunca `ATLAS_REPO_ROOT`), cwd/argumentos exactos y entorno hijo sin import-path editable; el nombre `python -m atlas...` por sí solo no concede autoridad | ✅ |
| 3 | **Tiering + bloqueo de credenciales** | Clasifica cada tool en read / write / shell_net / credential. Las de tier `credential` no se adoptan: una tool que dice manejar secretos no entra sin decisión humana | ✅ |
| 4 | **Coherencia AST profunda** | ¿lo que el tool *dice* (description) coincide con lo que *pide* (paths/endpoints/permisos del schema)? Patrón de `ast_guard` adaptado (no reuso directo — ver nota de investigación bajo `_vet_coherence`), cerrado 2026-07-23 (`t4-sentinel-tool-coherence`) | ✅ |
| 5 | **Egress IOC runtime** | `SentinelGate.vet_call(tool, args)` vetea CADA `tools/call` (no solo adopción), cableado en `McpRegistry.dispatch()`. Un IOC o un error interno del chequeo bloquean la llamada. Overhead medido: <5ms/llamada. Endurecido fail-closed por ATLAS DEFINITIVE CANDIDATE. | ✅ |
| 6 | **Re-vetting periódico** | `McpRegistry.revet_all()` + `maintenance_sentinel_revet_tick` (opt-in `ATLAS_SENTINEL_REVET=1`) re-corren `vet_tools` sobre servers ya adoptados contra su snapshot. Nunca reescribe el snapshot; ante error o drift revoca transporte/tools y pone el server en cuarentena hasta re-aprobación y reinicio. | ✅ |

### Postura: fail-closed

Al revés que el fail-open de un hook que no debe romper Claude Code: aquí la
adopción es peligrosa, así que lo que no se puede vetar **no se adopta**. Un server
vetado se cierra y no se registra ninguna de sus tools; una tool vetada no se
registra aunque el resto del server sí.

### Re-aprobación humana (HITL)

La re-aprobación de un drift/rug-pull en este slice es deliberadamente manual y
explícita: **borrar el snapshot del server** (`memory/sentinel/<server>.json`)
re-arma el TOFU en la siguiente adopción. Es fail-closed por defecto y no añade
superficie nueva; el botón de Telegram para re-vetar llega con el flujo ColdUpdate
(capa 6).

## Compatibilidad

- `McpRegistry` acepta `sentinel: SentinelGate | None = None`. Sin gate (default de
  los tests de transporte), comportamiento idéntico a ADR-035 — cero regresión.
- El `Orchestrator` construye un `SentinelGate` real con snapshot en
  `memory/sentinel/`. La primera vez que arranca un server, lo adopta (TOFU) y graba
  el snapshot; a partir de ahí vigila drift. Para una raíz MCP nativa el gate
  deriva el checkout de su propio módulo cargado y solo acepta una aserción del
  Orchestrator que coincide con él: una variable de grounding Git o un cwd
  controlado no puede redefinirlo. Si no puede probar ese contexto, también la
  ruta `python -m atlas.mcp.*` queda en cuarentena.
- No añade deps. No toca el modelo. El snapshot es JSON local, fuera de Merkle (no
  contiene secretos; sí se auditan los veredictos en Merkle).

## Addendum (2026-07-23) — re-minado de `claude-mcp-sentinel` (ahora v3.1.1)

El proyecto real pasó de v2.0 (referenciado arriba) a v3.1.1 (`CHANGELOG.md`,
GitHub `soy-rafa/claude-mcp-sentinel`, 184★, actualizado 2026-07-21). Mismo
método que la creación de este ADR: se roba el CONCEPTO, no el código. Dos
hallazgos concretos aplicados a `sentinel_gate.py`:

1. **Capa 2 estaba vacía en producción.** `Orchestrator` construye
   `SentinelGate` sin `ioc_domains`/`ioc_commands` — la blocklist "✅" de la
   tabla de arriba no bloqueaba nada real. Añadido un suelo no anulable
   (`_INCIDENT_IOC_DOMAINS`, unión con lo inyectado, nunca reemplazo) con
   `giftshop.club` (el mismo incidente Postmark de este ADR) — patrón
   "confirmed-malicious infra can't be allowlisted" de su v2.
2. **Hallazgo histórico, supersedido por la candidata:** `_load_snapshot`
   fallaba abierto. Un snapshot corrupto (no
   ausente) se trataba igual que "primera adopción" — TOFU se re-armaba sin
   ningún aviso. Una revisión posterior añadió aviso pero conservó el bypass.
   ATLAS DEFINITIVE CANDIDATE lo corrige definitivamente: JSON ilegible,
   raíz no-object o hashes inválidos vetan el server sin reescribir evidencia.

**Validación externa de las capas diferidas**: su v2 ya shippeaba en
producción real (20/20 regresión, ~30-80ms/llamada, cero coste LLM)
exactamente la Capa 5 de este ADR ("egress IOC runtime en cada tools/call")
— sube su prioridad, ya no es solo teórica. Su "scheduled monitoring"
(re-escaneo diario) valida el mismo patrón que la Capa 6 diferida
("re-vetting atado a ColdUpdate") — puede montarse sobre la misma
infraestructura de scheduler que el resto de ticks de `maintenance_facade.py`,
no requiere diseño nuevo. Ambas registradas en `docs/backlog.yaml`.

No adoptado (no aplica a este gate, que es adopción-time no runtime-per-call):
confianza adaptativa por sesión, capa de IA opcional, redacción de secretos
antes de IA — ninguno tiene equivalente en el alcance de `SentinelGate` hoy.

## Consecuencias

- Atlas no adopta una superficie MCP sin vetarla: para squatting/rug-pull, smuggling
  de shell en el `cmd`, y tools de credenciales.
- **No es defensa total**: existe un suelo IOC no anulable y puede ampliarse,
  pero no constituye un feed completo de amenazas. Opera en profundidad junto a la
  frontera P0 (ADR-037) y el HITL del dispatch. Esa es la postura, por diseño.
- El snapshot TOFU asume que la *primera* adopción es benigna: razonable para un
  nodo solo que añade servers a mano, y refinable con firma de fuente canónica
  (capa 4) cuando exista un registro de servers de confianza.
