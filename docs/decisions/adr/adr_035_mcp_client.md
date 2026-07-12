# ADR-035 — Cliente MCP (Atlas como consumidor de servidores MCP)

- Status: **Accepted** (2026-05-31) — implementado
- Módulos: `src/atlas/mcp/{transport,registry,config}.py`, wiring en
  `src/atlas/core/orchestrator.py`
- Depende de: ADR-031/032/033 (loop agéntico + HITL), ADR-037 (frontera de
  contenido no confiable)
- Habilita: Calendar, n8n y cualquier servidor MCP stdio como tools del loop

## Contexto

El loop agéntico (ADR-031/032/033) expone un set fijo de tools internas
(git, fs, block-memory, editor, browser). Para que Atlas opere sobre el mundo
real del usuario (calendario, automatizaciones n8n, etc.) sin cablear cada
integración a mano, adoptamos **MCP** (Model Context Protocol): Atlas actúa de
**cliente** y descubre las tools que cada servidor declara.

El contenido que devuelven esos servidores es **externo y no controlado** →
entra de lleno en la amenaza de inyección indirecta de prompt que ADR-037
mitiga. Por eso este ADR y el 037 están acoplados por diseño.

## Decisión

| # | Decisión | Por qué |
|---|----------|---------|
| 1 | **Transporte stdio con stdlib** (`subprocess` + `json`), sin dep `mcp` | Regla 6 (stdlib > deps). Cubre los servers stdio actuales. |
| 2 | Interfaz `McpTransport` (Protocol) detrás de la cual vive `StdioTransport` | Deja entrar un `SdkTransport`/HTTP-SSE drop-in si algún día hace falta, sin tocar el registry. |
| 3 | Framing **JSON-RPC 2.0 line-delimited** (un mensaje por línea) | Suficiente para los servers MCP actuales; el framing LSP-style (`Content-Length`) cabe como variante futura. |
| 4 | Handshake `initialize` → `notifications/initialized` → `tools/list` | Contrato MCP estándar. Protocol version laxa hasta que aparezcan diferencias relevantes. |
| 5 | Namespacing **`mcp__<server>__<tool>`** | Evita colisiones entre servers y con tools internas; el prefijo `mcp__` es la señal de procedencia para ADR-037. |
| 6 | **Mutate-by-default**; lectura solo si el config la marca (`read_only_tools`) | Seguro por defecto: una tool desconocida puede tener efectos secundarios → HITL salvo prueba en contrario. |
| 7 | Secretos **nunca** en `mcp_servers.json`: se declaran nombres de env var (`env_passthrough`) que el loader copia del entorno del proceso | El JSON es commiteable; los secretos viven en el entorno. Env mínimo (PATH + extra + passthrough); var ausente → server **disabled** (fail-safe). El `env` resuelto **nunca se loggea**. |
| 8 | **Arranque perezoso**: `start_all()` es opt-in (`atlas serve`); CLI/tests no spawnean subprocesos | Registry vacío → 0 tools MCP. Atlas funciona sin MCP. |
| 9 | Servers que fallan al arrancar quedan **aislados** (se loggea, no se eleva) | Un server roto no tumba el resto ni el runtime. |
| 10 | Auditoría Merkle por call (tool + ok/fail + `chars=<n>`), **sin argumentos ni secretos**; resultados truncados | Trazabilidad sin contaminar la cadena con outputs grandes o datos sensibles. |

### Interacción con ADR-037 (la parte delicada)

La clasificación read/mutate (ADR-035 dec.6) decide **si se ejecuta inline o vía
HITL** — es el eje de *efectos secundarios*. NO es el eje de *confianza del
contenido*. Toda tool `mcp__*` es `untrusted` por procedencia, **mute o no**.

Por eso la envoltura de no-confianza (`_wrap_untrusted`) se aplica por
**provenance, no por kind**, en las tres rutas en que un resultado MCP entra al
contexto:

1. Lectura inline (tool read-only allowlisted).
2. Mutación auto-aprobada inline (ADR-033 #2).
3. Mutación aprobada por HITL en la reanudación (ADR-032).

Cualquiera de las tres marca el loop como *tainted* → la siguiente mutación
auto-aprobada cae a HITL. Atar la envoltura a `kind=='read'` (como estaba
inicialmente) dejaba un agujero: una tool MCP mutante devolvía datos externos
sin marca y sin taintear. Cerrado; ver
`tests/test_orchestrator_untrusted_boundary.py::test_mcp_mutation_executes_and_taints`.

Además, `_dispatch_agentic_mutation` enruta explícitamente `mcp__*` al registry:
sin ello, una mutación MCP aprobada nunca correría (el parsing por
`partition('_')` la mandaba a un tool inexistente).

## Configuración

`mcp_servers.json` (ruta: `$ATLAS_MCP_SERVERS` o `<workspace>/mcp_servers.json`),
un array de objetos. Plantilla en `mcp_servers.example.json`. El archivo real
está en `.gitignore`. Ejemplo:

```json
[
  {
    "name": "cal",
    "cmd": ["python3", "-m", "mcp_calendar"],
    "env_passthrough": ["GOOGLE_CALENDAR_TOKEN"],
    "read_only_tools": ["list_events", "get_event"],
    "timeout_seconds": 15.0
  }
]
```

## Consecuencias

- Atlas consume servidores MCP stdio sin deps nuevas y sin que el contenido
  externo escale privilegios silenciosamente (la muralla ADR-037 lo cubre).
- El default `mutate` puede ser conservador (pide HITL para lecturas no
  marcadas); el remedio es declararlas en `read_only_tools`, no relajar el
  default.

## Limitaciones conocidas (deuda explícita, no bloqueante)

- Solo stdio (no HTTP/SSE). Cubierto por la interfaz `McpTransport` para cuando
  haga falta.

## Deuda cerrada

- **`timeout_seconds` se aplica en la I/O** (2026-05-31): `_read_line` lee a
  nivel de fd con `os.read` + `select`, acotado por un deadline = `timeout_seconds`
  por línea de respuesta. Un server colgado ya no bloquea el thread del loop:
  lanza `McpProtocolError("server response timed out after Ns")`. Stdlib pura.
  Test: `test_stdio_transport_times_out_on_silent_server`.

## Tests

`tests/test_mcp_client.py` (14): handshake, skip de notificaciones out-of-band,
server muerto, resolución de secretos por env, namespacing, clasificación
read-only, dispatch echo/mutate/desconocida, aislamiento de server fallido.
Integración con la muralla en `tests/test_orchestrator_untrusted_boundary.py`.
