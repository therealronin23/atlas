---
title: "Runbook — rotar el client secret OAuth de Google Workspace y relanzar sin secreto en argv"
status: vigente
date: 2026-07-17
verify_by: 2026-07-31
---

## Estado (2026-07-30) — CERRADO

Paso 1 **CERRADO**: el operador confirma explícitamente que el secreto expuesto
del client `344051770277-...` quedó **REVOCADO** en Google Cloud Console. Esto es
evidencia *reportada por el operador*, no verificable por máquina desde este
repo: ninguna sesión puede consultar el estado de la consola de Google.

Paso 3 **CERRADO en las dos superficies**. `~/.claude.json` se reconfiguró el
2026-07-22 (ver histórico abajo). La superficie **Codex se había quedado fuera** y
se corrigió el 2026-07-30: `.codex/config.toml` seguía fijando el client
**viejo/expuesto** `344051770277-...` con el secreto **inline** en
`[mcp_servers.google-workspace.env]` — exactamente la forma que el paso 3 manda
eliminar. Ahora es:

```toml
[mcp_servers.google-workspace]
command = "/home/ronin/proyectos/atlas-core/scripts/google_workspace_mcp_wrapper.sh"
args = ["--tool-tier", "core"]
```

Verificado en vivo antes de retirar las credenciales viejas: `safe_dotenv.py`
inyecta el par **rotado** (client `228819788474-...`); handshake MCP real
`initialize` → `serverInfo {name: google_workspace, version: 3.4.5}`,
`protocolVersion 2024-11-05`, exit 0; y escaneo de argv de todo el árbol hijo
(`uv` → `python`) durante el handshake: **cero** procesos con el secreto en argv.
Tras el cambio: TOML parsea, `GOCSPX` y `344051770277` ausentes, bloque
`atlas-trunk` y sus cinco `approval_mode` intactos, `sandbox_mode` preservado,
permisos `0600`.

Barrido final de las tres superficies de cliente — `~/.claude.json`,
`.codex/config.toml`, `.cursor/mcp.json`: cero coincidencias de `GOCSPX` y cero
referencias al client viejo. `.cursor/mcp.json` nunca tuvo el defecto (solo
registra `atlas-trunk`).

Lección: este runbook razonaba por *credencial*, pero la mitigación hay que
aplicarla por *cliente*. Hay ≥3 superficies MCP dadas de alta y arreglar una no
arregla las otras; `.codex/config.toml` además está gitignored
(`.gitignore:52`), así que ni CI, ni el pre-commit, ni `sanitation_audit` lo ven.
Al cerrar un hallazgo de credencial: enumerar TODAS las superficies y verificar
cada una por hash, no por "ya lo cambié".

Corrección al paso 4 de abajo: `ps aux | grep -c GOCSPX` **no puede dar 0** —
el argv del propio shell contiene el patrón del comando. Dio 2 en un sistema
limpio sin nada filtrando. El check debe escanear `/proc/*/cmdline` excluyendo
el propio PID y sus ancestros.

### Histórico (2026-07-22)

Paso 3 EJECUTADO: `~/.claude.json` (proyecto `atlas-core`, conector
`google-workspace`) reconfigurado para lanzar via
`scripts/google_workspace_mcp_wrapper.sh --tool-tier core` con `env: {}` —
verificado: cero coincidencias de `GOCSPX`/`344051770277` en el fichero tras
el cambio; wrapper probado en aislado (secreto se inyecta vía
`safe_dotenv.py`, nunca en argv). Efectivo desde el PRÓXIMO arranque del
conector (las sesiones ya vivas siguen con el argv viejo hasta reiniciarse).

Paso 1 (revocar el secreto viejo en Google Cloud Console): el operador
reporta haber cambiado el client ID — pendiente de confirmación explícita
de que el secreto expuesto (`GOCSPX-[REDACTED-2026-07-22-scrubbed-from-history]`,
client `344051770277-...`) quedó invalidado en la consola, no solo
sustituido en `~/.config/atlas/google-oauth.env` (que ya tiene el par nuevo,
client `228819788474-...`, permisos 0600 correctos).
**Cerrado el 2026-07-30** — ver arriba.

# Rotación del secreto OAuth de Google Workspace (hallazgo abierto del audit 2026-07-16)

## Qué pasó (verificado en vivo 2026-07-17 08:2x)

El proceso del cliente Claude (Claude Code lanzado por Claude Desktop) recibe
la configuración MCP entera como **argumento de línea de comandos**
(`--mcp-config {json}`), y ese JSON contiene `GOOGLE_OAUTH_CLIENT_SECRET`
inline. `/proc/<pid>/cmdline` es legible en Linux, así que el secreto del
client OAuth `344051770277-…apps.googleusercontent.com` está expuesto a
cualquier proceso local mientras esa sesión viva. El servidor `workspace-mcp`
en sí NO expone nada (recibe el secreto por env): el vector es la config del
conector serializada en argv por el cliente.

## Pasos (1 y 3 son solo del operador — credenciales, N3)

1. **Rotar** (Google Cloud Console → APIs & Services → Credentials → el
   OAuth 2.0 Client `344051770277-…` → *Reset secret*). El secreto expuesto
   queda revocado en ese momento; los refresh tokens de usuario sobreviven a
   la rotación del client secret (no hay que re-consentir).
2. **Guardar el secreto NUEVO fuera de toda config**: crea
   `~/.config/atlas/google-oauth.env` con permisos 0600:

   ```
   GOOGLE_OAUTH_CLIENT_ID=[REDACTED-CLIENT-ID-2026-07-22-scrubbed-from-history].apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=<el secreto nuevo>
   ```

   ```bash
   mkdir -p ~/.config/atlas && touch ~/.config/atlas/google-oauth.env \
     && chmod 600 ~/.config/atlas/google-oauth.env
   ```
3. **Reconfigurar el conector** google-workspace en el cliente Claude
   (donde lo diste de alta): sustituir `command: uvx, args: [workspace-mcp,…],
   env: {…SECRET…}` por:

   ```
   command: /home/ronin/proyectos/atlas-core/scripts/google_workspace_mcp_wrapper.sh
   args: ["--tool-tier", "core"]
   env: {}
   ```

   El wrapper inyecta el secreto al hijo vía `safe_dotenv.py` (mecanismo
   bendecido del repo) — la config del conector ya no contiene NINGÚN secreto,
   así que el argv del cliente queda limpio aunque siga serializando la config.
4. **Relanzar y verificar** (cualquier driver puede hacerlo):

   ```bash
   ps aux | grep -c GOCSPX   # debe ser 0 (solo el grep se contará a sí mismo)
   ```

## Por qué no lo hizo la sesión autónoma

La rotación exige la consola de Google (credencial del operador) y la
reconfiguración del conector vive en la UI del cliente Claude, no en un
fichero del repo. El wrapper y este runbook dejan el trabajo reducido a esos
dos gestos.
