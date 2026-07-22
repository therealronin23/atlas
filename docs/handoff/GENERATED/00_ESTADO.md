<!-- GENERADO por atlas handoff 2026-07-22T16:03:33.985559+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **MAXIMUS Cycle 8 — conector google-workspace reconfigurado: secreto fuera
  de argv (2026-07-22 20:00)** — corrección de un hallazgo del propio audit
  de hoy: la memoria de PRIME Cycle 2 decía "OAuth rotado", pero verificado
  en vivo (`ps aux | grep GOCSPX`) el secreto VIEJO seguía embebido en el
  `--mcp-config` de 2 procesos Claude Code corriendo — solo se había
  completado el paso 2 del runbook (guardar el secreto nuevo a salvo en
  `~/.config/atlas/google-oauth.env`, client `228819788474-...`), nunca el
  paso 3 (reconfigurar el conector). El operador confirmó haber rotado el
  client ID en Google Cloud Console (paso 1, credencial suya) y pidió que el
  paso 3 (edición de config, no manejo de credenciales) lo hiciera yo.
  Localizado `~/.claude.json` (config MCP de Claude Code, fuera del repo,
  fichero de texto plano — no algo oculto en UI de Electron como se
  documentó en 2026-07-17) → proyecto `atlas-core` → `mcpServers.
  google-workspace`. Editado: `command`/`args` apuntan ahora a
  `scripts/google_workspace_mcp_wrapper.sh --tool-tier core`, `env: {}` —
  el wrapper inyecta el secreto vía `safe_dotenv.py` (nunca en argv).
  Verificado antes de tocar la config viva: wrapper probado en aislado con
  los args reales (arranca limpio, sin ERROR de precondición). Verificado
  después: JSON sigue válido, cero coincidencias de `GOCSPX`/
  `344051770277` en todo el fichero. Efectivo desde el próximo arranque del
  conector (las 2 sesiones ya vivas conservan el argv viejo hasta
  reiniciarse — reiniciarlas no es mío, mataría sesiones activas).
  **Pendiente, explícitamente del operador**: confirmar que el secreto
  expuesto quedó REVOCADO en Google Cloud Console (no solo sustituido en el
  fichero local) — sin eso, el secreto que ya estuvo en claro en argv sigue
  siendo válido aunque ya no se use. Runbook actualizado con el estado real.
  Memoria de PRIME Cycle 2 corregida (decía "resuelto", no lo estaba).
