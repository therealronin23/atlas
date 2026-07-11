# ADR-065 — Primer conector real: Gmail read-only, cliente propio stdlib

- Estado: aceptado (2026-07-11)
- Contexto: hasta ahora `atlas.fabric.*` (ADR-060) solo describe conectores
  de forma declarativa — `RecipeEngine`/`ConnectorRegistry`/
  `ConnectionTestRunner` operan en mock/sandbox y `mode=real` responde
  siempre `BLOCKED_BY_MISSING_DEPENDENCY` (ningún conector real existía).
  El Cónclave decidió el diseño de este primer conector real antes de
  implementarlo; este ADR documenta esa decisión, no la re-litiga.

## Decisión

1. **Primer conector real de Atlas = Gmail, read-only**
   (`src/atlas/fabric/connectors/gmail.py`, `GmailReadOnlyConnector`).
   Alcance mínimo deliberado: `email.read` + `email.draft` (lectura y
   preparación), nunca `email.send`.
2. **Cliente propio, SOLO stdlib** — `os`, `json`, `urllib.request`,
   `urllib.parse`, `urllib.error`. Cero dependencia nueva. Esto es
   deliberado, no un descuido: por eso este ADR **no** es un ADR de
   dependencia (no hay ninguna que aprobar). Se descartó explícitamente
   añadir un cliente HTTP de terceros o el SDK oficial de Google para no
   introducir superficie nueva por un único endpoint GET.
3. **Autosuficiencia**: el Cónclave descartó la opción de enrutar este
   conector a través del MCP conducido por Claude por un hecho de
   arquitectura, no por preferencia — el bridge de eventos (7341,
   ADR-058) es **read-only** y JAMÁS puede invocar herramientas MCP (eso
   metería al Orchestrator dentro del bridge, rompiendo la garantía Merkle
   de ese componente). Un conector real de Atlas tiene que poder operar sin
   que Claude Code esté siquiera presente — consistente con
   "Claude Code es un plus, no una dependencia": si el token está
   disponible, Atlas debe poder usarlo por sí mismo.
4. **Credencial = referencia opaca de entorno**, mismo patrón que
   `AuthBroker` (`env:<VAR>`, por defecto `GMAIL_OAUTH_TOKEN`).
   `available()` solo comprueba `bool(os.environ.get(var))` — nunca lee el
   valor para nada más que construir el header `Authorization: Bearer` en
   el momento exacto de la llamada HTTP. El token no se persiste, no se
   devuelve en ninguna respuesta (éxito o error) y no aparece en ningún
   mensaje de log — verificado con test dedicado que simula un 401 y
   comprueba que el valor del token no aparece en la salida.
5. **`email.send` sigue excluido/hard-gated independientemente de este
   conector**: `capabilities()` devuelve solo `["email.read",
   "email.draft"]`. El invariante duro que impediría enviar
   (`pol_hard_personal_channel_send` en `atlas.fabric.policy`, capability
   `email.send` con risk `HIGH` en `atlas.fabric.capabilities`) vive en el
   PolicyEngine, no en este conector — que este conector nunca implemente
   `send()` es defensa en profundidad, no la única barrera.
6. **Real vs. bloqueado, siempre honesto**: sin token en entorno,
   `list_messages()` devuelve `BLOCKED_BY_MISSING_DEPENDENCY` con
   `real: False` y **no hace ninguna llamada de red** (verificado por
   test: el mock de `urlopen` no se invoca). Con token, hace la llamada
   real a `gmail.googleapis.com` y marca la respuesta `real: True` con
   `provenance: "gmail_api_readonly"` — nunca se finge un resultado.
7. **No-auto-ingesta a memoria**: el conector expone
   `WRITES_TO_MEMORY = False` como documentación ejecutable de la
   invariante — este módulo solo lee y devuelve datos con su provenance;
   la decisión de ingerir a memoria (si alguna vez se toma) vive en una
   capa distinta y explícita, nunca ocurre por defecto dentro de
   `atlas.fabric.connectors`.

## Consecuencias

- `src/atlas/fabric/connectors/` es el primer subpaquete de `fabric` con
  clientes que hacen red real (todo lo demás en `fabric/` es declarativo o
  simulado). Sigue prohibido importar `atlas.api.*` desde aquí (capa
  inferior no depende de capa superior, mismo invariante que ADR-060).
- `tests/test_os_gmail_connector.py` mockea `urllib.request.urlopen` en
  todos los casos — cero red real en CI. Cubre: bloqueo sin token sin
  tocar la red, llamada real con header Bearer verificado, exclusión de
  `email.send` de `capabilities()`, y no-filtración del token en salidas
  de éxito y de error (401 simulado).
- Este conector NO se conecta todavía a `ConnectionTestRunner`/
  `mode=real` (`src/atlas/fabric/testing.py`) — ese cableado (y decidir si
  `HealthMonitor` pasa a reportar `CONNECTED` real en vez de simulado)
  queda para una tarea posterior explícita, para no ampliar el alcance de
  esta pieza sensible más allá de lo que el Cónclave decidió.
