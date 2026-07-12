# ADR-038 — Gate de adopción "Atlas Sentinel" (muralla P0 de adopción)

- Status: **Accepted** (2026-05-31) — slice 1 implementado
- Módulo: `src/atlas/security/sentinel_gate.py`, enganchado en
  `src/atlas/mcp/registry.py`
- Depende de: ADR-035 (cliente MCP — trae la superficie de adopción), ADR-036
  (threat model), ADR-037 (frontera de contenido no confiable)
- Habilita: registro dinámico de MCP y, a futuro, el agente de
  auto-mantenimiento (que descubre/propone servers que este gate debe vetar)

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
| 2 | **IOC + coherencia de comando** | El `cmd` es argv (nunca shell, ADR-035): un token con metacaracteres de shell (`;`, `\|`, `$(`, …) es smuggling ⇒ veta el server. Blocklist inyectable de dominios/comandos veta tool o server | ✅ |
| 3 | **Tiering + bloqueo de credenciales** | Clasifica cada tool en read / write / shell_net / credential. Las de tier `credential` no se adoptan: una tool que dice manejar secretos no entra sin decisión humana | ✅ |
| 4 | **Coherencia AST profunda** | ¿lo que el tool *dice* (description) coincide con lo que *pide* (paths/endpoints/permisos del schema)? Reusar `ast_guard` | ⏳ diferido |
| 5 | **Egress IOC runtime** | Blocklist de dominios/comandos antes de cada `tools/call` (no solo en adopción) | ⏳ diferido |
| 6 | **Re-vetting atado a ColdUpdate** | El snapshot+diff ya existe; falta cablear la re-verificación al flujo de update real cuando exista | ⏳ diferido |

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
  el snapshot; a partir de ahí vigila drift.
- No añade deps. No toca el modelo. El snapshot es JSON local, fuera de Merkle (no
  contiene secretos; sí se auditan los veredictos en Merkle).

## Consecuencias

- Atlas no adopta una superficie MCP sin vetarla: para squatting/rug-pull, smuggling
  de shell en el `cmd`, y tools de credenciales.
- **No es defensa total** (la blocklist IOC arranca vacía e inyectable; el feed lo
  alimentará el agente de auto-mantenimiento). Opera en profundidad junto a la
  frontera P0 (ADR-037) y el HITL del dispatch. Esa es la postura, por diseño.
- El snapshot TOFU asume que la *primera* adopción es benigna: razonable para un
  nodo solo que añade servers a mano, y refinable con firma de fuente canónica
  (capa 4) cuando exista un registro de servers de confianza.
