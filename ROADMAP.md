# ATLAS — Hoja de Ruta Completa con Claude Code
# De hoy hasta Atlas completo — instrucciones sesión por sesión

---

## ANTES DE EMPEZAR — Setup único (hacer una sola vez)

### Prerrequisitos en tu HP Omen

```bash
# 1. Instalar Python 3.11+
# Windows: https://www.python.org/downloads/
# Linux/WSL: sudo apt install python3.11 python3.11-venv python3-pip

# 2. Instalar Node.js 18+ (para Claude Code)
# https://nodejs.org/

# 3. Instalar Git
# https://git-scm.com/

# 4. Instalar Claude Code
npm install -g @anthropic-ai/claude-code

# 5. Autenticar Claude Code con tu cuenta Pro
claude login
# → Selecciona "Claude.ai account" → Autoriza en el navegador

# 6. Descargar todos los archivos del chat a ~/Downloads/
# (los 25 archivos que generamos)

# 7. Ejecutar el script de setup
bash ~/Downloads/setup_atlas.sh

# 8. Verificar que todo está bien
cd ~/atlas-core
PYTHONPATH=src python -m pytest tests/ -q
# Debe mostrar: 102 passed (baseline Gate B). Tras Gate C parcial: 129 passed.
```

---

## CÓMO TRABAJAR CON CLAUDE CODE — Reglas generales

### Iniciar una sesión

```bash
cd ~/atlas-core
source .venv/bin/activate
claude
```

Claude Code lee CLAUDE.md automáticamente al arrancar. Tiene el contexto completo.

### Estructura de cada sesión

1. **Siempre empieza con:** `"Lee CLAUDE.md y el estado actual del proyecto"`
2. **Da una tarea concreta** — no pidas "hacer todo", pide una cosa
3. **Deja que ejecute** — Claude Code corre tests solo, los corrige solo
4. **Al terminar:** `"Haz git commit con mensaje descriptivo"`
5. **Límite de ventana:** si te dice que se acercó al límite, guarda el progreso antes

### MCPs a configurar (una vez)

```bash
# En ~/.claude/config.json — Claude Code los carga automáticamente

# GitHub MCP — gestión de repositorio, PRs, issues
claude mcp add github --token TU_GITHUB_TOKEN

# Context7 MCP — documentación de librerías en tiempo real
claude mcp add context7

# Filesystem MCP — ya viene integrado en Claude Code
# Bash/Terminal — ya viene integrado en Claude Code
```

### Cuándo usar Claude Code vs este chat

| Situación | Dónde |
|-----------|-------|
| Implementar código, tests, corregir bugs | Claude Code |
| Decisiones de arquitectura, revisar diseño | Este chat |
| ADRs nuevos, cambios de visión | Este chat |
| Instalar dependencias, git, bash | Claude Code |
| "¿Qué debo hacer ahora?" | Este chat |

---

## FASE 0 — Verificación inicial (1 sesión, 30 min)

**Cuándo:** Justo después de ejecutar setup_atlas.sh

**Prompt de inicio:**
```
Lee CLAUDE.md completo. Luego ejecuta los tests y dame un resumen
del estado del proyecto: qué funciona, qué es stub, qué falta para Gate C.
```

**Lo que Claude Code hará:**
- Leer toda la estructura del proyecto
- Ejecutar 102 tests
- Listar qué componentes son stubs vs implementados
- Darte un resumen honesto del estado

**Criterio de éxito:** 102 tests pasan, entiendes el estado real

---

## GATE C — Hermes real + Telegram + Tailscale
### Duración estimada: 3-6 semanas (sesiones de 2h, 2-3 veces/semana)

### Estado (2026-05-22) — 129/129 tests passing

| Sub | Estado | Commit | Notas |
|---|---|---|---|
| C1 | **DONE (parte código)** | `e4250f3` | Script + stub listos. Falta ejecutar en un VPS real. |
| C2 | PENDIENTE | — | Bloqueado: Tailscale auth key + acceso al VPS. |
| C3 | **DONE** | `b9e45ef` | HermesRestAdapter + 11 tests + smoke script. |
| C4 sesión 1 | **DONE** | `e9ca05a` | Bot skeleton + 16 tests. Sin dep nueva (stdlib urllib). |
| C4 sesión 2 | PENDIENTE | — | Integrar con Orchestrator + approval buttons + hooks Thermal/Offline. |
| C5 | PENDIENTE | — | Bloqueado por C2 y C4 sesión 2. |

### Para desbloquear C2 / C5

1. VPS Ubuntu 22.04+ disponible.
2. `curl -fsSL https://raw.githubusercontent.com/therealronin23/atlas/main/scripts/install_hermes_vps.sh | sudo bash` en el VPS. Anotar `HERMES_API_KEY` impreso.
3. Tailscale instalado en VPS y HP Omen; anotar IPs Tailscale.
4. Pasar a la siguiente sesión: IP Tailscale del VPS + `HERMES_API_KEY` + Telegram bot token + chat_id.

---

### C1 — Desplegar Hermes Agent en VPS (1-2 sesiones)

**Estado:** código DONE (`e4250f3`). Ejecución en VPS PENDIENTE.

**Entregado:**
- `scripts/install_hermes_vps.sh` — instala Docker, crea usuario `hermes`, estructura `/opt/hermes/`, genera `.env` con `HERMES_API_KEY` aleatorio, despliega el stub vía docker-compose, configura systemd, verifica puerto. Idempotente.
- `scripts/hermes_agent_stub/` — Dockerfile + `agent.py` (HTTP server stdlib con verificación HMAC-SHA256 y ventana antirreplay 300s) + docker-compose.yml. Implementa el contrato REST que espera `HermesRestAdapter`. **No** ejecuta tareas reales; devuelve respuestas simuladas. Sustitución real en Gate D.
- Decisión: HTTP plano (sin TLS) porque Tailscale provee transporte cifrado (ADR-017).
- Nota ROADMAP: la línea "Hermes Agent (Nous Research)" no se materializa — Nous publica modelos, no un agente. Hermes en Atlas es el agente-VPS propio.


**Prerequisito:** Tener un VPS (Hetzner CX11 €4/mes o similar)

**Prompt sesión 1:**
```
Necesito desplegar Hermes Agent en mi VPS. El VPS tiene:
- IP: [TU_IP_VPS]
- SO: Ubuntu 22.04
- Acceso SSH: ssh root@[IP]

Crea un script de instalación que:
1. Instale Docker y Docker Compose
2. Clone o instale Hermes Agent (Nous Research)
3. Configure el entorno mínimo
4. Verifique que arranca correctamente

Primero verifica si Hermes Agent existe en GitHub con una búsqueda,
luego adapta el script a lo que realmente existe.
```

**Prompt sesión 2:**
```
El VPS tiene Docker instalado. Necesito:
1. Configurar el bot de Telegram para Atlas:
   - Crear bot con @BotFather y obtener TELEGRAM_BOT_TOKEN
   - Configurar webhook o polling
2. Hacer que el bot responda /status con el estado de Atlas Core
3. Añadir el chat_id autorizado a permissions.yaml

Variables disponibles:
TELEGRAM_BOT_TOKEN=[TOKEN]
TELEGRAM_CHAT_ID=[TU_CHAT_ID]
```

---

### C2 — Tailscale tunnel (1 sesión)

**Estado:** PENDIENTE. Requiere acceso simultáneo a VPS y HP Omen + Tailscale auth key.

**Prompt:**
```
Necesito conectar mi HP Omen con el VPS de Hermes usando Tailscale.
Ambas máquinas tienen Ubuntu/Linux.

1. Instala Tailscale en ambas máquinas (dame los comandos)
2. Configura la red para que Atlas Core pueda hablar con Hermes-VPS
   usando la IP de Tailscale (no la IP pública)
3. Verifica la conexión
4. Actualiza el archivo .env con HERMES_BASE_URL apuntando a la IP Tailscale

La clave de auth de Tailscale es: TAILSCALE_AUTH_KEY=[KEY]
```

---

### C3 — HermesRestAdapter real (1-2 sesiones)

**Estado sesión 1:** DONE (`b9e45ef`). **Estado sesión 2:** PENDIENTE.

**Entregado sesión 1:**
- `HermesRestAdapter` en `src/atlas/hermes/hermes.py`. REST + HMAC-SHA256 + retry exponencial (1s, 2s, 4s). Cliente stdlib `urllib` (sin nuevas deps).
- Tras 3 fallos en `enqueue_task` → cae en `OfflineQueue` + raise `HermesUnreachable`.
- Excepciones tipadas: `HermesError`, `HermesUnreachable`, `HermesAuthError`, `HermesBadResponse`.
- `tests/test_hermes_rest_adapter.py` — 11 tests con servidor HTTP mock local.
- `scripts/hermes_smoke.py` — end-to-end contra un `HERMES_BASE_URL` real.

**Pendiente sesión 2** (necesita Orchestrator integrado y bot Telegram activo):
1. OfflineFallbackMode real disparando alerta a Telegram tras 15min sin ping.
2. Drain de OfflineQueue al reconectar.
3. CLI `atlas hermes status`.

**Prompt sesión 1:**
```
Lee hermes.py. Necesito implementar HermesRestAdapter — la versión real
que sustituye a HermesMockAdapter.

El adaptador debe:
1. Conectar a HERMES_BASE_URL via REST HTTPS
2. Autenticar con HMAC-SHA256 en cada request (X-Atlas-Signature + X-Atlas-Timestamp)
3. Implementar todos los métodos de HermesAdapter: health_check, enqueue_task,
   get_task_result, get_queue_status, cancel_task
4. Tener retry automático (3 intentos, backoff exponencial)
5. Si falla 3 veces: activar modo offline, encolar en OfflineQueue
6. Tests de integración con mock del servidor

Crea también un script simple de smoke test para verificar la conexión real.
```

**Prompt sesión 2:**
```
El HermesRestAdapter está implementado. Ahora necesito:
1. Integrar el OfflineFallbackMode real: si no hay ping en 15 minutos,
   Hermes envía mensaje a Telegram avisando que Atlas está offline
2. Implementar el drain de la OfflineQueue cuando Atlas reconecta:
   al arrancar el orchestrator, si hay tareas en la cola, enviarlas a Hermes
3. Añadir comando CLI: atlas hermes status
4. Tests para todo esto
```

---

### C4 — Telegram bot completo (1-2 sesiones)

**Estado sesión 1:** DONE (`e9ca05a`). **Estado sesión 2:** PENDIENTE.

**Entregado sesión 1** (`src/atlas/interfaces/telegram_bot.py`):
- `TelegramClient` (stdlib urllib, sin dep nueva — desvío respecto al prompt original que sugería `python-telegram-bot`).
- `TelegramAuthorizer` con whitelist `chat_id`, construible desde `PermissionProfile.telegram_config()`.
- `TelegramBot` dispatcher de `/status /task /audit /tools /triage`, tolerante a updates malformados y errores de handler.
- Protocolo `AtlasOps` que el Orchestrator implementará en sesión 2 — frontera limpia para testear ambos lados por separado.
- Logging de accesos no autorizados vía `MerkleLogger` inyectado.
- 16 tests con cliente y ops mockeados.

**Pendiente sesión 2:**
1. Implementar `AtlasOps` en el Orchestrator y arrancar el bot como hilo background.
2. Botones inline Sí/No para `REQUIRES_APPROVAL` (callbacks ya recibidos por el dispatcher; falta el flujo de approval).
3. Hook `ThermalWatchdog` → notificación Telegram automática.
4. Hook `OfflineFallbackMode` → alerta a los 15min sin ping.
5. Notificación de arranque "Atlas Core vX online — N tareas pendientes".

**Prompt sesión 1:**
```
Necesito implementar src/atlas/interfaces/telegram_bot.py

El bot debe:
1. Escuchar mensajes del chat_id autorizado (en permissions.yaml)
2. Comandos:
   /status → atlas status completo
   /task [intent] → procesar tarea y responder con resultado
   /audit [n] → últimas N entradas del Merkle Logger
   /tools → lista de herramientas disponibles
   /triage → modo Alfa/Omega actual + temperatura + RAM
3. Rechazar mensajes de chat_id no autorizados (registrar en Merkle Logger)
4. Para tareas con REQUIRES_APPROVAL: enviar botones Sí/No inline
5. Para DELEGATE_HERMES: confirmar que se encoló + ID de delegación

Usar python-telegram-bot o aiogram (elige el más simple).
TELEGRAM_BOT_TOKEN está en variables de entorno.
```

**Prompt sesión 2:**
```
El bot de Telegram está implementado. Necesito:
1. Que el orchestrator se conecte al bot al arrancar (modo background)
2. Que las alertas del ThermalWatchdog se envíen por Telegram automáticamente
3. Que el OfflineFallbackMode envíe alerta cuando Atlas Core lleva 15 min offline
4. Notificación al arrancar Atlas: "Atlas Core v0.1 online — X tareas pendientes en cola"
5. Tests de integración con bot simulado
```

---

### C5 — Cierre Gate C (1 sesión)

**Estado:** PENDIENTE. Bloqueado por C2 (Tailscale) y C4 sesión 2 (integración con Orchestrator).

**Prompt:**
```
Gate C debe estar completo. Necesito verificar los criterios de éxito:

1. "atlas status" por CLI funciona y devuelve datos reales
2. Enviar /status por Telegram recibe respuesta en < 5 segundos
3. Enviar /task "git status" por Telegram ejecuta la tarea y responde
4. Si Atlas se apaga, Hermes envía alerta por Telegram en < 15 minutos
5. Las tareas encoladas mientras Atlas estuvo offline se procesan al reconectar
6. La cadena Merkle es válida después de 10 tareas por Telegram

Ejecuta todos los tests, genera un report de Gate C y haz git tag v0.2-gate-c.
```

---

## GATE D — Inteligencia real
### Duración estimada: 4-8 semanas

---

### D1 — InferenceHub con LiteLLM real (1-2 sesiones)

**Prompt sesión 1:**
```
inference_hub.py tiene stubs. Necesito implementar el hub real con LiteLLM.

1. Instala litellm
2. Reemplaza _call_provider_stub por llamadas reales a litellm.completion()
3. Configura los proveedores del pool:
   - Groq (GROQ_API_KEY): llama-3.3-70b, qwen-qwq-32b
   - OpenRouter (OPENROUTER_API_KEY): meta-llama/llama-3.1-8b:free
   - Together AI (TOGETHER_API_KEY): meta-llama/Llama-3-8b
   - Gemini (GEMINI_API_KEY): gemini-1.5-flash
4. El fallback chain: Groq → OpenRouter → Together → Gemini → L0 local
5. Si todos fallan: delegar a Hermes
6. Registrar cada llamada en Performance Ledger
7. Tests con llamadas reales (necesito las API keys)

API keys disponibles:
GROQ_API_KEY=[KEY]
OPENROUTER_API_KEY=[KEY]
```

**Prompt sesión 2:**
```
El InferenceHub real está funcionando. Ahora:
1. Conectar el InferenceHub al Orchestrator:
   para tareas LOCAL_SAFE, en vez del stub, llamar a InferenceHub.infer()
2. Implementar el pool multi-cuenta:
   si Groq falla por rate limit, rotar a la segunda cuenta de Groq
   (las cuentas se configuran en config/providers.yaml)
3. Implementar el Performance Ledger real:
   registrar latencia, proveedor, tokens y éxito de cada llamada
   para optimizar el routing automáticamente
4. Añadir comando CLI: atlas providers
```

---

### D2 — SLM clasificador (reemplazar rule-based) (1 sesión)

**Prompt:**
```
El clasificador actual es rule-based (classifier.py). Gate B especificó
que en Gate D se reemplaza por un SLM real.

El SLM candidato: Qwen-2.5-Coder-7B via Ollama (local, gratuito)

1. Instala Ollama si no está instalado
2. Descarga qwen2.5-coder:7b
3. Crea src/atlas/router/slm_classifier.py que:
   - Mantiene la interfaz de Classifier (retorna ClassificationResult)
   - Usa el SLM para clasificar tareas ambiguas que el rule-based no resuelve
   - El rule-based sigue siendo la primera capa (más rápido)
   - El SLM solo interviene cuando el rule-based retorna LOCAL_SAFE sin confianza alta
4. Si el SLM no está disponible: fallback silencioso al rule-based
5. JIT Loader: el modelo se carga solo cuando se necesita, se desactiva en modo OMEGA
```

---

### D3 — Capability tokens + AtlasExecutor (1 sesión)

**Prompt:**
```
Lee ADR-020 en memory/system_context/03_adr.md.
Crea src/atlas/security/capabilities.py con: AtlasToken (base frozen),
ReadToken, WriteToken, NetworkToken, ExecToken — todos Pydantic frozen=True
con field_validator que bloquea rutas fuera de workspace.
Crea src/atlas/security/executor.py con AtlasExecutor que solo acepta tokens tipados.
Tests: intentar instanciar ReadToken con path=/etc/passwd debe fallar.
Sin cambios al orchestrator todavía — solo los módulos y sus tests.
```

### D4 — Memoria vectorial con KuzuDB (1-2 sesiones)

**Prompt sesión 1:**
```
ADR-008 cerrado: KuzuDB (embedded, Cypher + vector + FTS5).

1. Instala kuzu (pip install kuzu)
2. Crea src/atlas/memory/vector_store.py:
   - Indexa automáticamente las entradas de Failure Atlas y Pattern Library
   - Búsqueda semántica: dado un error o tarea, encuentra el patrón más similar
   - Actualización incremental (no re-indexa todo cada vez)
3. Integra en el Orchestrator:
   antes de ejecutar una tarea, buscar si hay un patrón similar en memoria
   si existe: incluir el patrón como contexto adicional
4. Comando CLI: atlas memory search "descripción de problema"
```

**Prompt sesión 2:**
```
La memoria vectorial funciona. Necesito:
1. Auto-generación de SKILL.md cuando Atlas resuelve un problema nuevo:
   al completar una tarea con éxito, generar un archivo SKILL.md en ~/atlas/skills/
   con el patrón documentado (input→proceso→output→lecciones)
2. Indexar automáticamente las skills de Hermes Agent en ~/atlas/skills/hermes/
3. La próxima vez que venga una tarea similar, Atlas carga el SKILL.md como contexto
4. Comando CLI: atlas skills list / atlas skills search [query]
```

---

### D5 — Time-Travel Debugging y Ghost Replay (2 sesiones)

**Prompt sesión 1 — ADR-021:**
```
Lee ADR-021 en memory/system_context/03_adr.md.
Implementa src/atlas/core/checkpoint.py:
- Clase Checkpoint: id, task_id, step_id, state_dict, timestamp, parent_id
- CheckpointStore: serializacion JSON ACID en ~/atlas/memory/checkpoints/
- Integracion con Orchestrator: snapshot automatico en cada paso significativo
Implementa src/atlas/core/timetravel.py:
- resume_from(checkpoint_id): restaura estado y continua ejecucion
- branch_from(checkpoint_id, mutation): crea task_id nuevo con linaje
Tests: 6 tests minimo cubriendo creacion, restauracion, branching, ACID.
```

**Prompt sesión 2 — ADR-022:**
```
Lee ADR-022. Implementa src/atlas/core/ghost_replay.py:
- Cache key: SHA-256(task.intent + task.sensitivity + context_hash)
- Cache store: SQLite local en ~/atlas/memory/ghost_replay.db
- Hook en Orchestrator: consultar Ghost Replay ANTES de InferenceHub
- TTL configurable, purga automatica en OperationalMode.DEGRADED
Tests: cache hit/miss, invalidacion, comportamiento bajo presion de memoria.
```

### D6 — PII Surrogate (1 sesión)

**Prompt:**
```
Lee ADR-023. Implementa src/atlas/security/pii_surrogate.py:
- Detector de PII basado en regex + NER local (spaCy es-core-news-sm)
- Surrogate generator: SLM local con temperature=0 y seed fija
- Mapping bidireccional en memoria (nunca persistido, nunca enviado fuera)
- Hook en InferenceHub: substituir PII antes de llamadas L1/L2,
  revertir surrogates en respuesta antes de devolver al usuario
Tests: nombres, direcciones, IBANs, telefonos. Determinismo: misma entrada
debe producir mismo surrogate dentro de una sesion.
```

### D7 — Cierre Gate D (1 sesión)

**Prompt:**
```
Verificar criterios de éxito Gate D:

1. "atlas task 'explica qué hace este código'" devuelve respuesta real de un LLM gratis
2. El proveedor se elige automáticamente (no hardcoded)
3. Si Groq falla, el fallback ocurre < 3 segundos
4. Una tarea con patrón conocido en memoria vectorial se resuelve más rápido
5. Las skills generadas son legibles y reutilizables
6. Performance Ledger tiene métricas reales de latencia por proveedor

Ejecuta todos los tests, actualiza CLAUDE.md con el estado nuevo,
y haz git tag v0.3-gate-d.
```

---

## GATE E — Entorno local definitivo + Dashboard + Voz
### Duración estimada: 6-12 semanas

---

### E1 — Proxmox (si decides instalarlo) (2-3 sesiones)

**Prompt sesión 1:**
```
ADR-002: decidir entorno local. Las opciones son:
A) Proxmox VE — Type 1 hypervisor, mejor aislamiento
B) Docker Desktop — más simple, menos overhead
C) WSL2 + Docker — si estás en Windows

Para tomar la decisión empírica, necesito:
1. Ver las especificaciones reales del HP Omen (CPU, RAM, disco)
2. Evaluar si el Proxmox cabe bien en ese hardware
3. Dame una comparativa honesta para este hardware específico

Ejecuta: lscpu, free -h, df -h, uname -a
y dame tu recomendación basada en los resultados reales.
```

---

### E2 — Dashboard de telemetría (1-2 sesiones)

**Prompt:**
```
Necesito un dashboard web local para Atlas. Simple, funcional, sin florituras.

1. Usa FastAPI + Jinja2 (ya está en las dependencias)
2. Crea src/atlas/interfaces/dashboard.py
3. Pantallas:
   - / → estado general (governance, merkle chain, triage mode, temperatura, RAM)
   - /tasks → últimas 20 tareas con estado y duración
   - /audit → Merkle Logger paginado con verificación de integridad
   - /memory → contenido de SystemContextLoader y stats de cada capa de memoria
   - /tools → Tool Registry completo
   - /providers → estado de InferenceHub y Performance Ledger
4. Se actualiza cada 30 segundos (polling simple, sin websockets por ahora)
5. Solo accesible desde localhost (no exponer al exterior sin Tailscale)
6. Comando CLI: atlas dashboard (arranca en localhost:7331)
```

---

### E3 — Voz: Whisper + Piper (1-2 sesiones)

**Prompt sesión 1:**
```
ADR-003: voz como módulo. Implementar si el hardware lo permite.

1. Verifica que el HP Omen tiene micrófono y que soundcard funciona
2. Instala whisper.cpp (más eficiente que whisperpy en CPU)
   o faster-whisper si prefieres Python puro
3. Crea src/atlas/interfaces/voice.py:
   - STT: escucha micrófono → texto (Whisper, modelo small.en o medium)
   - TTS: texto → audio (Piper o Kokoro, voz local)
   - Latencia objetivo: < 500ms para STT, < 200ms para TTS
4. Modo de activación: palabra clave "Atlas" o tecla dedicada
5. Solo activo en modo ALFA, se desactiva en OMEGA para ahorrar RAM
```

---

## GATE F — Computer-use + Cursor + Frontend
### Duración estimada: 8-16 semanas

---

### F1 — Computer-use con Playwright (2-3 sesiones)

**Prompt sesión 1:**
```
ADR-013b: implementar computer-use.

Capa 1: Browser automation con Playwright
1. Instala playwright y chromium
2. Crea src/atlas/tools/browser.py:
   - Herramienta L1: navegar a URL, extraer texto, hacer screenshots
   - Herramienta L1: rellenar formularios, hacer click
   - Todo pasa por SSRF Bridge antes de navegar
   - Screenshots se guardan en ~/atlas/tmp/ con nombre timestamp
3. Tests con páginas estáticas locales (sin internet real en tests)
4. Añadir al Tool Registry con PermissionLevel.CONFIRM
```

**Prompt sesión 2:**
```
Playwright funciona. Ahora necesito el loop visual:
1. Atlas hace screenshot de la pantalla completa o de una ventana
2. Envía el screenshot al VLM (usar Gemini free o LLaVA local)
3. El VLM describe qué ve: "hay un formulario con campos X, Y, Z"
4. Atlas decide la siguiente acción basado en la descripción
5. Crea src/atlas/tools/screen.py para capturas de pantalla locales
6. Tests que simulan el loop completo con screenshot de prueba
```

---

### F2 — Integración Cursor/VS Code (1-2 sesiones)

### F3 — eBPF: capa final de seguridad a nivel kernel (2-3 sesiones)

**Prerequisito:** Atlas debe ser estable y autónomo (Gate E completo)

**Prompt sesión 1:**
```
ADR-Gate-F — eBPF como capa de seguridad final.
El objetivo es compilar restricciones de syscalls directamente en el kernel de Linux
para que ningún proceso del sandbox pueda hacer sys_connect o sys_execve fuera de
los límites aunque evite el AST Guard y los capability tokens.

1. Investiga la librería bcc o libbpf para Python
2. Crea un programa eBPF mínimo que intercepte sys_connect y lo bloquee
   si el destino no está en SSRFBridge.allowed_domains
3. Verifica que funciona en WSL2 (algunas versiones no soportan eBPF completo)
4. Si WSL2 no lo soporta, documenta la alternativa: seccomp profiles con Docker
```

### F4 — ColdUpdateManager (self-improvement protocol) (3-4 sesiones)

**Prompt sesión 1:**
```
Implementar el protocolo de evolución fría (ADR Gate F — ColdUpdateManager).
1. Atlas entra en modo hibernate: solo lectura, no acepta tareas nuevas
2. Toma snapshot completo del estado (Git tag + backup de ~/atlas/)
3. Genera una versión N+1 del componente objetivo en un directorio aislado
4. Ejecuta la batería completa de tests contra N+1
5. Si todos los tests pasan Y hay mejora medible en ProviderMetricsStore:
   propone el swap vía Telegram (HITL — confirmación humana obligatoria)
6. Si falla: restaura el snapshot automáticamente
Empezar solo con el componente más simple: el classifier.
```

**Prompt:**
```
El objetivo es que Atlas pueda abrir Cursor en un proyecto y trabajar con él.

1. Detecta si Cursor o VS Code está instalado (code --version o cursor --version)
2. Crea src/atlas/tools/editor.py:
   - open_project(path): abre el proyecto en Cursor/VS Code
   - apply_diff(file, diff): aplica un diff usando la CLI
   - run_task(task_name): ejecuta una tarea del workspace
3. Flujo de trabajo:
   atlas task "crea un componente React para gestión de tareas en ~/proyectos/app"
   → Atlas planifica → genera código → lo aplica via editor.py → abre Cursor
4. Tests con proyecto de ejemplo vacío
```

---

## RESUMEN VISUAL DE FASES

```
HOY
 │
 ├─ FASE 0 (1 sesión)    → Setup + verificar 102 tests
 │
 ├─ GATE C (3-6 semanas) → Atlas responde por Telegram 📱
 │   ├─ C1: Hermes Agent en VPS
 │   ├─ C2: Tailscale tunnel
 │   ├─ C3: HermesRestAdapter real
 │   ├─ C4: Telegram bot completo
 │   └─ C5: Cierre + git tag v0.2
 │
 ├─ GATE D (4-8 semanas) → Atlas razona con LLMs gratis 🧠
 │   ├─ D1: InferenceHub LiteLLM real
 │   ├─ D2: SLM clasificador (Qwen local)
 │   ├─ D3: ChromaDB + SKILL.md auto
 │   └─ D4: Cierre + git tag v0.3
 │
 ├─ GATE E (6-12 semanas) → Atlas vive en su entorno 🖥️
 │   ├─ E1: Proxmox (si aplica)
 │   ├─ E2: Dashboard local
 │   └─ E3: Voz (Whisper + Piper)
 │
 └─ GATE F (8-16 semanas) → Atlas = Jarvis completo 🤖
     ├─ F1: Computer-use (Playwright + VLM)
     └─ F2: Cursor/VS Code integration

TOTAL REALISTA (con turnos rotativos, hijo, ~5-10h/semana):
  Atlas útil por Telegram:     1-2 meses
  Atlas con LLMs gratis:       2-4 meses
  Atlas con entorno completo:  4-6 meses
  Atlas Jarvis completo:       8-12 meses
```

---

## TIPS PARA MAXIMIZAR CLAUDE CODE CON PRO ($20/mes)

1. **Una tarea por sesión** — no pidas todo a la vez, agota el contexto
2. **Empieza siempre con:** `"Lee CLAUDE.md y ejecuta los tests"`
3. **Antes del límite:** `"Haz commit de todo y dame un resumen del estado"`
4. **Sesiones de 90 min** son el punto óptimo para Pro (no agotas la ventana)
5. **Usa `/clear` en Claude Code** para liberar contexto si va lento
6. **Guarda el output** de cada sesión en docs/session_YYYY-MM-DD.md
7. **Si falla algo raro:** `"Ejecuta los tests, muéstrame los errores exactos"`

---

## PRIMERA SESIÓN DE CLAUDE CODE — Copiar y pegar esto

```
Lee CLAUDE.md completo. Luego:

1. Ejecuta todos los tests: PYTHONPATH=src python -m pytest tests/ -v
2. Lista los archivos que existen en cada módulo
3. Identifica qué componentes son stubs vs implementados
4. Dime honestamente: ¿qué falta para que pueda ejecutar "atlas status"
   en mi máquina con resultado real?
5. Crea un plan de las 3 cosas más importantes a implementar ahora
   para llegar a Gate C lo antes posible.

No hagas nada todavía. Solo analiza y planifica.
```
