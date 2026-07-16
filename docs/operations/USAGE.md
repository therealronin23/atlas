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
| `HERMES_API_KEY` | C | Secreto HMAC de al menos 32 bytes para el canal Hermes→Atlas. El wrapper seguro puede generarlo y guardarlo sin imprimirlo. |
| `ATLAS_DASHBOARD_URL` | C | Origen privado/Tailscale de Atlas que usa la skill `atlas-twin`; no admite credenciales, ruta, query ni fragmento. |
| `HERMES_MODEL_PROVIDER` / `HERMES_MODEL` | C | Proveedor y modelo explícitos para el Hermes oficial. El provisionador admite `custom:groq` u `openrouter`. |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_ALLOWED_USERS` | C | Bot y lista numérica de usuarios autorizados por Hermes. Configurarlos no prueba entrega viva. |
| `HERMES_KANBAN_TRANSPORT` / `HERMES_SSH_HOST` | C | Canal Atlas→Hermes (`local` o `ssh`); en SSH el destino debe ser `usuario@host` privado/Tailscale. |
| `HERMES_BASE_URL` | C | Solo compatibilidad con el antiguo `HermesRestAdapter`; no es el transporte nativo del Hermes-Agent oficial. |
| `TELEGRAM_CHAT_ID` | C | Chat autorizado para el bot propio de Atlas, distinto del bot gestionado por Hermes. |
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
PYTHONPATH=src python -m pytest tests/ -q
# Los tests marcados computer_use se ejecutan aparte cuando se desea validar navegador.

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
Atlas Core
  Workspace:       /home/usuario/atlas
  Version:         <versión instalada>
  Uptime:          12.5s
  Governance:      OK
  Merkle chain:    OK
  Hermes mode:     mock         # "configured" tampoco significa probado en vivo
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
   - `DELEGATE_HERMES` → usa el adapter Hermes configurado; si no está
     alcanzable, la ruta debe degradar sin fingir ejecución.
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

## 4. Verificación

El runbook actual está en
[operational_runbook.md](operational_runbook.md). Cada comando prueba una capa
distinta; no sumar sus conclusiones por intuición.

### 4.0 Estado local y suite

```bash
PYTHONPATH=src atlas reality --run-checks --json
```

Esto prueba estado local, suite core y mypy. Proveedores y servicios externos
siguen sin verificarse salvo que un smoke específico los llame realmente.

### 4.1 Contrato twin aislado

```bash
PYTHONPATH=src python scripts/twin_e2e_smoke.py
```

Verifica HMAC, nonce, grounding y Merkle dentro de un workspace temporal. No
prueba el VPS ni Telegram. El modo `--live` solo admite una URL Atlas privada o
Tailscale y reutiliza el cliente endurecido de la skill.

### 4.2 Pairing Hermes real

```bash
VPS_HOST=<tailscale-ip-o-nombre.ts.net> scripts/verify_twin_pairing.sh
```

Comprueba el servicio fijado y el canal firmado. Su propia salida recuerda que
no realiza inferencia ni envía Telegram; ambas requieren pruebas separadas.

### 4.3 Inferencia Atlas

```bash
PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- \
  .venv/bin/python scripts/inference_smoke.py
```

Solo los proveedores llamados con éxito quedan verificados para esa ejecución.
`hermes_smoke.py` y `operational_smoke.py` pertenecen al contrato REST legado y
no sirven como evidencia del Hermes-Agent oficial.

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
auto-revocó. Genera una nueva en https://console.groq.com/keys, edita `.env`
con un editor local que no la deje en argv/historial y conserva modo `0600`.

### 5.4 OpenRouter devuelve "No endpoints found"

El modelo concreto fue retirado. Lista de modelos free vigentes:

```bash
PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- \
  .venv/bin/python - <<'PY'
import json
import os
import urllib.request

request = urllib.request.Request(
    "https://openrouter.ai/api/v1/models",
    headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
)
with urllib.request.urlopen(request, timeout=20) as response:
    payload = json.load(response)
print("\n".join(model["id"] for model in payload["data"] if ":free" in model["id"]))
PY
```

Edita `DEFAULT_PROVIDERS` en `src/atlas/core/inference_hub.py` para
apuntar a uno vigente.

### 5.5 Hermes-Agent no responde

```bash
tailscale status
VPS_HOST=<tailscale-ip-o-nombre.ts.net> scripts/verify_twin_pairing.sh
ssh -o StrictHostKeyChecking=yes root@<tailscale-host> \
  'systemctl status hermes-agent.service --no-pager'
```

No usar IP pública, Docker ni rutas `/root/.hermes`: no pertenecen al
despliegue endurecido actual. Un pairing verde no demuestra proveedor o
Telegram; probarlos explícitamente antes de declararlos operativos.

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
