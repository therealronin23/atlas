# Atlas Core — Guía de operación

Documento de referencia para operar Atlas Core en local. Asume que ya
has hecho el quick start del [README.md](../README.md).

---

## 1. Configuración inicial

### 1.1 Workspace

Atlas usa por defecto `~/atlas/` como workspace runtime (datos, audit
log, caches). Override via env var:

```bash
export ATLAS_HOME=~/atlas    # default
```

El workspace queda fuera del repo de código. Esto separa el código
(`~/proyectos/atlas-core/`) de los datos operacionales (`~/atlas/`).

Estructura del workspace cuando se crea (auto):
```
~/atlas/
├── config/
│   ├── governance.json       # constitución inmutable (ADR-006)
│   └── permissions.yaml      # mapa de permisos
├── memory/
│   ├── audit/                # MerkleLogger append-only
│   ├── checkpoints/          # TimeTravel (Gate D/D5)
│   ├── ghost_cache/          # GhostReplay (Gate D/D5)
│   ├── system_context/       # vision.md, rules.md, adr.md
│   ├── error_registry/       # FailureEntry JSON files
│   ├── approved_patterns/    # PatternEntry JSON files
│   └── performance/          # ProviderMetrics samples
├── projects/                 # tu trabajo
├── skills/                   # skill packs
└── tmp/                      # efímero
```

### 1.2 Variables de entorno

Copia `.env.example` a `.env` y rellena. Las relevantes:

| Variable | Gate | Descripción |
|---|---|---|
| `ATLAS_HOME` | — | Workspace root. Default `~/atlas`. |
| `HERMES_BASE_URL` | C | URL del Hermes REST-compatible: VPS (`100.x:8443`) o local (`127.0.0.1:8443`). |
| `HERMES_API_KEY` | C | Shared secret para HMAC-SHA256. Lo emite `install_hermes_vps.sh`. |
| `TELEGRAM_BOT_TOKEN` | C | Token de @BotFather para `atlas` bot. Opcional. |
| `TELEGRAM_CHAT_ID` | C | Chat ID autorizado. Solo este chat puede mandarle órdenes. |
| `GROQ_API_KEY` | D | Free tier, llama-3.3-70b y qwen3-32b. ~150ms. |
| `OPENROUTER_API_KEY` | D | Free tier, varios modelos open. Latencia variable. |
| `TOGETHERAI_API_KEY` | D | Opcional. Atlas no la pide; LiteLLM la usa si la encuentra. |
| `GEMINI_API_KEY` | D | Opcional. Idem. |
| `ATLAS_PIPELINE_GATE_D` | D | `1` para activar el pipeline integrado al construir Orchestrator. |
| `ATLAS_MEMORY_VECTOR` | D | `1` (default) con Gate D: Kuzu + distiller + registros. `0` desactiva Kuzu. |
| `ATLAS_PENDING_HMAC_KEY` | G | Firma HMAC de `pending_approvals/*.json`. Fallback: `HERMES_API_KEY`. |
| `ATLAS_INFERENCE_MODE` | D | `auto` (default) / `live` / `stub`. |
| `ATLAS_EMBEDDING_MODE` | D | Idem para embeddings (LiteLLMEmbedder). |
| `ATLAS_SLM_CLASSIFIER_MODE` | D | Idem para SLMClassifier. |
| `ATLAS_PII_SALT` | D | Salt para sustitución determinista de PII. Pon algo aleatorio largo. |

### 1.3 Verificar la instalación

```bash
PYTHONPATH=src python -m pytest tests/ --ignore=tests/test_browser.py -q
# suite core (~522+ passed; browser tests requieren Playwright)

MYPYPATH=src python -m mypy src/atlas/
# debe imprimir: Success
```

---

## 2. Comandos CLI

> Los comandos `atlas` requieren `pip install -e ".[dev]"` previo (entry-point
> definido en `pyproject.toml`). Equivalente sin entry-point:
> `PYTHONPATH=src python -m atlas.interfaces.cli <cmd>`.

### 2.1 `atlas status`

```bash
atlas status
```

Output:
```
Atlas Core v0.6
  Workspace:       /home/usuario/atlas
  Version:         0.6.0
  Uptime:          12.5s
  Governance:      OK
  Merkle chain:    OK
  Hermes mode:     mock         # o "live" si HERMES_BASE_URL configurado
  Queue depth:     0
  Tools:           N
  Audit records:   M
```

### 2.2 `atlas task`

Procesa una intención por el pipeline completo:

```bash
atlas task "git status"
```

Output:
```
Procesando: git status
  Status:   DONE
  Route:    deterministic_tool
  Tool:     git.status
  Task ID:  3a7f1b8c-...
Resultado:
  { "branch": "main", "ahead": 0, "behind": 0, ... }
```

Opciones:
- `--priority N` (1-5, default 3)
- `--source cli|api|internal` (default cli)

### 2.3 `atlas memory`

```bash
atlas memory --layer system_context
atlas memory --layer error_registry
atlas memory --layer approved_patterns
```

### 2.4 `atlas audit`

```bash
# últimas 20 entradas
atlas audit --tail 20

# verificar integridad de la cadena
atlas audit --verify
```

### 2.5 `atlas tools`

```bash
atlas tools
atlas tools --level L1
```

---

## 3. Pipeline Gate D — activación y uso

### 3.1 Qué hace cuando está activo

Cuando llamas a `orchestrator.handle_intent(intent)` con pipeline Gate
D activo, esto ocurre:

1. **TimeTravel** snapshot inicial (`received`).
2. **Governance L0** check (constitución inmutable).
3. **GhostReplay** lookup por `(intent, sensitivity, context_signature)`.
   Si hit → devuelve resultado cacheado en ~1-2ms.
4. **Hybrid classifier**:
   - Rule-based primero (regex, μs).
   - Si confidence < 1.0 (default LOCAL_SAFE 0.6), consulta al SLM
     vía InferenceHub.
   - SLM gana el empate si identifica una ruta más específica que
     LOCAL_SAFE.
5. **Route**:
   - `BLOCKED` → governance, no se ejecuta.
   - `DELEGATE_HERMES` → envía a Hermes-VPS.
   - `REQUIRES_APPROVAL` → entra a queue de aprobación (Telegram).
   - `DETERMINISTIC_TOOL` → git/fs/atlas tools, sin LLM.
   - `LOCAL_SAFE` con InferenceHub:
     - PIISurrogate.redact sobre intent + context.
     - MemoryDistiller.build_context (system context + chunks relevantes
       del KuzuVectorStore si está conectado).
     - InferenceHub.infer → fallback chain Groq → OpenRouter → ... → L0.
     - PIISurrogate.restore sobre la respuesta.
6. **GhostReplay** record (si la tarea terminó OK).
7. **TimeTravel** snapshot final (`done` / `blocked_governance` / etc.).

Todo queda en MerkleLogger con cadena SHA-256 verificable.

### 3.2 Activar el pipeline

**Opción A — env var (más sencilla):**
```bash
ATLAS_PIPELINE_GATE_D=1 atlas task "..."
```

Esto activa el pipeline pero **sin InferenceHub inyectado** — las
tareas LOCAL_SAFE caerán al passthrough con un mensaje informativo.

**Opción B — código (con InferenceHub real):**
```python
from atlas.core.orchestrator import Orchestrator
from atlas.core.inference_hub import InferenceHub

orch = Orchestrator()
orch.enable_gate_d_pipeline(
    inference_hub=InferenceHub(mode="auto"),
    ghost_ttl_s=24*3600,
    slm_mode="auto",
)

task = orch.handle_intent("explicame brevemente que es un Merkle tree")
# task.tool_name == "inference_hub.complete"
# task.result["text"] == "Un Merkle tree es ..."
# task.result["provider"] == "groq_llama"
# task.result["latency_ms"] == 1123
# task.result["tokens_used"] == 337
# task.result["pii_redacted"] == 0
```

### 3.3 Inspeccionar las piezas

```python
orch.executor          # AtlasExecutor (capability tokens)
orch.capability_issuer # CapabilityIssuer
orch.distiller         # MemoryDistiller (None si pipeline off)
orch.ghost_replay      # GhostReplay (None si pipeline off)
orch.slm_classifier    # SLMClassifier (None si pipeline off)
orch.timetravel        # TimeTravel (None si pipeline off)
orch.pii_surrogate     # PIISurrogate (siempre disponible)
orch.inference_hub     # InferenceHub (None si no inyectado)
orch.vector_store      # KuzuVectorStore (None si pipeline off o ATLAS_MEMORY_VECTOR=0)
```

### 3.4 Memoria vectorial (Kuzu)

Con `enable_gate_d_pipeline()` (o `ATLAS_PIPELINE_GATE_D=1`), por defecto
`ATLAS_MEMORY_VECTOR=1` crea `~/atlas/memory/kuzu/atlas.kuzu` y conecta
`MemoryDistiller`, `ErrorRegistry` y `ApprovedPatternStore`.

```bash
export ATLAS_PIPELINE_GATE_D=1
export ATLAS_MEMORY_VECTOR=1
atlas task "busca patrones similares a este error"
```

Desactivar Kuzu (tests ligeros o host sin dependencia):

```bash
export ATLAS_MEMORY_VECTOR=0
```

---

## 4. Smoke tests reales

Verificación contra infraestructura viva. Runbook completo:
[docs/operational_runbook.md](operational_runbook.md).

### 4.0 `operational_smoke.py` (recomendado)

Checklist operativo: env, `Orchestrator.status`, Hermes REST, ciclo CLI
approval (editor write), Telegram outbound opcional.

```bash
set -a && source .env && set +a
PYTHONPATH=src python scripts/operational_smoke.py
```

Con workspace real:

```bash
PYTHONPATH=src python scripts/operational_smoke.py --workspace ~/atlas
```

### 4.1 `hermes_smoke.py`

Prueba el adapter HermesRest contra Hermes-VPS por Tailscale.
Requiere `HERMES_BASE_URL` + `HERMES_API_KEY` en `.env`.

```bash
set -a && source .env && set +a
PYTHONPATH=src python scripts/hermes_smoke.py
```

Output esperado (4 pasos OK):
```
[1/4] health_check http://100.108.132.116:8443 ...
      reachable=True mode=live version=stub-0.1.0
[2/4] enqueue_task echo ...      accepted=True delegation_id=...
[3/4] get_queue_status ...       depth=1 next=...
[4/4] cancel_task ...             cancelled=True
OK
```

### 4.2 `inference_smoke.py`

Prueba cada proveedor LLM con key en entorno.

```bash
PYTHONPATH=src python scripts/inference_smoke.py
```

Output:
```
  - groq_llama            OK     180ms  Atlas operativo
  - groq_qwen             OK     190ms  <think> Okay, the user...
  - openrouter_nemotron   OK    12000ms  atlas operativo
  - openrouter_liquid     OK     339ms  atlas operativo
  - together_free         SKIP (sin key)
  - gemini_free           SKIP (sin key)
```

### 4.3 `pipeline_smoke.py`

End-to-end del pipeline Gate D completo, 5 intents.

```bash
PYTHONPATH=src python scripts/pipeline_smoke.py
```

Cada intent reporta `route`, `tool`, `classifier_path`, `ghost`,
`latency_ms`, `timetravel` steps. Si pasa por `inference_hub.complete`,
también muestra `provider`, `latency_hub`, `tokens`, `excerpt` y
`pii_redacted`.

Exit code 0 si los 5 cumplen su expectativa.

---

## 5. Troubleshooting

### 5.1 Tests fallan tras `git pull`

```bash
pip install -e ".[dev]"   # re-instalar por si hay nuevas deps
PYTHONPATH=src python -m pytest tests/ -q
```

### 5.2 mypy se queja de tipos

`tool.mypy` en `pyproject.toml` ya está calibrado para este codebase
(strict pero pragmático). Si ves errores tras editar:

```bash
MYPYPATH=src python -m mypy src/atlas/ 2>&1 | head -30
```

Las reglas relajadas están documentadas en el comentario de
`[tool.mypy]` en `pyproject.toml`.

### 5.3 Groq devuelve 401 Invalid API Key

La key fue compartida en chat o foro → el escáner de Groq la
auto-revocó. Genera nueva en https://console.groq.com/keys y actualiza
`.env`:

```bash
sed -i 's/^GROQ_API_KEY=.*/GROQ_API_KEY=gsk_nueva.../' .env
```

### 5.4 OpenRouter devuelve "No endpoints found"

El modelo concreto fue retirado. Lista de modelos free vigentes:

```bash
source .env && curl -sS https://openrouter.ai/api/v1/models \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  | python -c "import json,sys; print('\n'.join(m['id'] for m in json.load(sys.stdin)['data'] if ':free' in m['id']))"
```

Edita `DEFAULT_PROVIDERS` en `src/atlas/core/inference_hub.py` para
apuntar a uno vigente.

### 5.5 Hermes-VPS no responde

```bash
# verificar tailnet
tailscale status

# probar conectividad TCP al puerto 8443
nc -zv 100.108.132.116 8443

# si el VPS está vivo pero el agente no
ssh root@<ip-publica-vps>
docker ps | grep hermes
docker logs hermes-agent -n 50
```

Si el contenedor está caído:
```bash
ssh root@<ip-publica-vps> "cd /opt/hermes/agent && docker compose up -d"
```

### 5.6 KuzuDB dim mismatch al abrir VectorStore

Si cambias el embedder entre runs y el `dim` no coincide con el
almacenado en el `AtlasMeta` de la DB:

```python
KuzuVectorStore(db_path=..., embedder=..., recreate=True)
```

Eso borra la DB existente. Solo válido si los datos son índice
semántico (no verdad de record).

### 5.7 Pipeline Gate D activo pero `inference_hub.complete` no aparece

Causa probable: el InferenceHub no se inyectó. Comprueba:

```python
orch.inference_hub is None   # True = no inyectado, cae al passthrough
```

Solución: pasar `inference_hub=...` a `enable_gate_d_pipeline()`.

---

## 6. ADRs vigentes (lectura rápida)

Lista canónica en [memory/system_context/03_adr.md](../memory/system_context/03_adr.md).

Atajo:

| ADR | Tema | Estado |
|---|---|---|
| 000 | Atlas soberano local | sealed |
| 001 | EventBus in-process | resolved |
| 002 | Proxmox vs alternativas | **open** (Gate E) |
| 003 | Voice (Whisper + Piper) | **open** (Gate E) |
| 004 | First vertical: status+task | sealed |
| 005 | Permission levels | resolved |
| 006 | Workspace + blocked paths | resolved |
| 007 | Autonomy decision tree | resolved |
| 008 | KuzuDB vector + grafo | resolved (Gate D) |
| 009 | SKILL.md format | sealed |
| 010 | SLM classifier | resolved (Gate D) |
| 011 | REST + HMAC Atlas↔Hermes | resolved (Gate C) |
| 012 | Memory sync Hermes↔Atlas | **open** (Gate D→) |
| 013 | Telegram chat_id whitelist | resolved |
| 013b | Computer-use | resolved (Gate F) |
| 014 | Layered isolation | resolved |
| 016 | LiteLLM backend | resolved (Gate D) |
| 017 | Tailscale tunnel | resolved (Gate C) |
| 018 | MemoryDistiller | resolved (Gate D) |
| 019 | Statistical validation | **open** (Gate E) |
| 020 | Capability tokens | resolved (Gate D) |
| 021 | Time-Travel | resolved (Gate D) |
| 022 | Ghost Replay | resolved (Gate D) |
| 023 | PII Surrogate | resolved v1 (Gate D); v2-SLM diferido |
