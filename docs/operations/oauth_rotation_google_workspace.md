---
title: "Runbook — rotar el client secret OAuth de Google Workspace y relanzar sin secreto en argv"
status: vigente
date: 2026-07-17
verify_by: 2026-07-31
---

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
   GOOGLE_OAUTH_CLIENT_ID=344051770277-6o3jecctk43ev0hb6u43dvihhdgo2usc.apps.googleusercontent.com
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
