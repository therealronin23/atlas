# T5.2/T5.3 — Descubrimiento de proveedores, pre-vuelo barato y errores estructurados

Fecha: 2026-07-23
Nodo del plan maestro: `docs/design/atlas_master_plan.md` §5 → **T5** ("Cadena de
proveedores robusta — el cuello real de Atlas").
Estado T5.1 (contexto, ya cerrado 2026-07-17): `ProviderChainSmoke` camina
`DEFAULT_PROVIDERS` con una llamada mínima real (8 tokens) en aislamiento, cadencia
24h opt-in `ATLAS_PROVIDER_SMOKE=1`, persiste `workspace/self_build/provider_smoke_state.json`,
lo proyecta `atlas reality --json` → sección `provider_smoke`.

Este plan cubre lo que pidió el operador esta noche, en tres piezas:
1. **Descubrimiento en vivo** de qué modelos sirve cada proveedor (vs lista fija editada a mano).
2. **Pre-vuelo barato** que un loop pesado llama ANTES de iterar N veces (go/no-go, sin quemar tokens).
3. **Errores/límites estructurados** (rate limit vs modelo-no-encontrado; `Retry-After` real vs cooldown fijo).

---

## 0. Hechos verificados del código y de las APIs (no inventar)

### Código existente relevante
- `src/atlas/core/inference_hub.py`:
  - `DEFAULT_PROVIDERS: list[Provider]` (líneas 179-397). Cada `Provider` tiene
    `name, level, base_url, model_id, litellm_model, api_key_env, account_pool,
    context_tokens, rpm_limit, status, error_count, supports_tools, roles`.
  - `InferenceHub._call_provider_real` (683-821): llama `litellm.completion(...)`,
    captura excepciones y llama `_classify_error`.
  - `_classify_error` (849-860): HOY clasifica por **substring del nombre de la clase**
    de excepción (`"RateLimit" in name`, `"Authentication"`, else). Cooldown de rate-limit
    = constante fija `RATE_LIMIT_COOLDOWN_S = 60.0` (64). NO lee `Retry-After` ni
    `x-ratelimit-*`.
  - `_is_transient` (79-81) + `_TRANSIENT_MARKERS` (76): también por substring de nombre.
  - `InferenceResponse` (160-176): `error` es un **string plano**. No hay campo que
    distinga "reintentable / no reintentable / reset en Ns".
  - `probe_provider` (462-467): wrapper público que llama a UN provider sin caminar
    la cadena — lo usa el smoke.
- `src/atlas/core/self_maintenance/provider_smoke.py`: `ProviderChainSmoke.run()` →
  `list[ProviderSmokeResult]` con `outcome ∈ {ok, failed, skipped}`.
- `src/atlas/core/orchestrator_parts/maintenance_facade.py:542` `maintenance_provider_smoke_tick`:
  patrón de tick a copiar (opt-in por env, cadencia 24h vía fichero de estado, Merkle log,
  escribe `workspace/self_build/provider_smoke_state.json`).
- `src/atlas/core/reality.py:471` `_provider_smoke_state(root)`: patrón de proyección
  fail-honesta a copiar (lee el fichero de estado, nunca dispara red, nunca lanza).
  Cableado en `collect_reality` (línea 60).
- Tests espejo: `tests/test_provider_smoke.py`, `tests/test_reality.py`,
  `tests/test_inference_hub_real.py`.

### Endpoints de discovery reales (documentación pública, verificados 2026-07-23)
Son llamadas API estándar OpenAI-compatible `GET {base}/v1/models` — **NO scraping web**,
y **NO gastan tokens de inferencia**:
- **OpenRouter**: `GET https://openrouter.ai/api/v1/models` → `{data: [{id, name, pricing, context_length, ...}]}`.
  (`base_url` del Provider ya es `https://openrouter.ai/api/v1`).
- **Groq**: `GET https://api.groq.com/openai/v1/models` → `{data: [{id, ...}]}`. OJO: el
  `base_url` del Provider es `https://api.groq.com` (sin `/openai/v1`); la ruta de modelos
  es `/openai/v1/models`. Requiere resolver la ruta por proveedor (ver §1).
- **NVIDIA NIM**: `GET https://integrate.api.nvidia.com/v1/models` con `Authorization: Bearer`
  → `{data: [{id, ...}]}`. (`base_url` ya es `.../v1`). Importante: NIM **lista** modelos
  que su tier **no sirve** (caso histórico kimi-k2.6 en `/v1/models` pero 404 "Function not
  found for account" al invocar) → discovery reduce, no elimina, la necesidad del smoke.
- **Together**: `GET https://api.together.xyz/v1/models` → lista OpenAI-compatible.
- **Gemini**: **NO** OpenAI-compatible para listar. Endpoint nativo
  `GET https://generativelanguage.googleapis.com/v1beta/models?key=API_KEY` →
  `{models: [{name: "models/gemini-2.5-flash", supportedGenerationMethods, inputTokenLimit, ...}]}`.
  Forma distinta (prefijo `models/`, campo `models` no `data`). Adaptador propio.
- **Ollama local**: nativo `GET http://127.0.0.1:11434/api/tags` → `{models: [{name, ...}]}`.
  Adaptador propio.

### Errores estructurados de litellm (verificado en docs litellm 2026-07-23)
- Las excepciones litellm **heredan de las de OpenAI** y añaden 3 atributos documentados:
  `status_code` (int), `message`, `llm_provider`. Clases: `RateLimitError` (429),
  `NotFoundError` (404), `AuthenticationError` (401), `ServiceUnavailableError` (503),
  `Timeout`, `APIConnectionError`, `ContextWindowExceededError`, `BadRequestError`.
- Headers: al heredar de OpenAI, la excepción suele traer `.response` (objeto httpx) con
  `.response.headers`; algunas versiones litellm exponen además `litellm_response_headers`.
  **NO está garantizado** para todos los status (litellm preserva `Retry-After` de forma
  fiable solo en 429). Diseño: leer headers **defensivamente** (`getattr`), nunca asumir.
- **Groq** (verificado): en 429 devuelve header `retry-after` (segundos) + set de
  `x-ratelimit-limit-{requests,tokens}`, `x-ratelimit-remaining-{requests,tokens}`,
  `x-ratelimit-reset-{requests,tokens}`. En respuestas 200 NO garantiza `x-ratelimit-remaining`.

---

## 1. Diseño concreto (interfaces)

Tres módulos nuevos + ediciones aditivas al hub. Todo con HTTP inyectable para tests herméticos
(la suite es hermética: `PYTEST_CURRENT_TEST` fuerza stub; discovery/preflight deben aceptar
un `http_get` inyectado y NO tocar red en tests).

### 1.1 `src/atlas/core/provider_errors.py` (NUEVO) — clasificación estructurada

```python
from enum import Enum
from dataclasses import dataclass

class ErrorKind(str, Enum):
    RATE_LIMIT = "rate_limit"      # 429 — reintentable tras cooldown
    AUTH = "auth"                  # 401/403 — permanente, key muerta
    NOT_FOUND = "not_found"        # 404/410 — modelo decomisionado/renombrado, permanente
    CONTEXT_LENGTH = "context"     # 400 context window — permanente para ESTE request
    TIMEOUT = "timeout"            # transitorio
    SERVER = "server"              # 5xx — transitorio
    CONNECTION = "connection"      # APIConnection — transitorio
    UNKNOWN = "unknown"

@dataclass
class ProviderError:
    kind: ErrorKind
    retryable: bool
    status_code: int | None
    retry_after_s: float | None    # de header Retry-After o x-ratelimit-reset-*; None si no lo dice
    raw_message: str

def classify_provider_error(exc: BaseException) -> ProviderError: ...
def _extract_retry_after(exc: BaseException) -> float | None: ...  # lee headers defensivamente
```

Regla de clasificación (status_code primero, nombre de clase como respaldo):
`429→RATE_LIMIT(retryable)`, `401/403→AUTH(no)`, `404/410→NOT_FOUND(no)`,
`400+"context"→CONTEXT_LENGTH(no)`, `5xx/ServiceUnavailable/InternalServer→SERVER(retryable)`,
`Timeout→TIMEOUT(retryable)`, `APIConnection→CONNECTION(retryable)`, else `UNKNOWN(no)`.
`retry_after_s`: parsea `retry-after` (segundos), si no `x-ratelimit-reset-requests`/`-tokens`.

Esta función es la **única fuente de verdad** que sustituye al substring-matching disperso
de `_classify_error` y `_is_transient`.

### 1.2 Ediciones aditivas a `inference_hub.py`

- `InferenceResponse`: añadir campos con default (aditivo, no rompe callers):
  `error_kind: str = ""`, `retry_after_s: float | None = None`, `retryable: bool = False`.
- `_call_provider_real`: al capturar `last_exc`, construir `pe = classify_provider_error(exc)`;
  poblar los 3 campos nuevos en el `InferenceResponse` de fallo.
- `_classify_error(provider, exc)`: reimplementar sobre `classify_provider_error`. En
  `RATE_LIMIT`, usar `pe.retry_after_s` para el cooldown si viene (`self._rate_limited_until[name]
  = time.time() + pe.retry_after_s`), con fallback a `RATE_LIMIT_COOLDOWN_S`. En `AUTH`/`NOT_FOUND`
  → `ProviderStatus.DOWN` (permanente, no re-quemar). Comportamiento por defecto idéntico cuando
  no hay header.
- `_is_transient(exc)`: reimplementar como `classify_provider_error(exc).retryable`.

### 1.3 `src/atlas/core/provider_discovery.py` (NUEVO) — descubrimiento en vivo

```python
@dataclass
class DiscoveryResult:
    provider_name: str
    outcome: str                 # "ok" | "unreachable" | "auth_failed" | "skipped"
    model_ids: list[str]         # ids servidos por el proveedor AHORA (vacío si no ok)
    reason: str
    checked_at: str

def discovery_kind(provider: Provider) -> str:
    # "openai_models" (Groq/OpenRouter/NVIDIA/Together), "gemini_listmodels", "ollama_tags"

def models_url(provider: Provider) -> str:
    # resuelve la ruta real por proveedor (Groq: base + "/openai/v1/models";
    # openai-compat genérico: base + "/models"; gemini/ollama: nativo)

def discover_available_models(
    provider: Provider, *, timeout_s: float = 10.0,
    http_get: Callable[..., Any] | None = None,   # inyectable; default httpx/urllib
) -> DiscoveryResult: ...
```

3 adaptadores por forma de respuesta: `openai_models` (`data[].id`), `gemini_listmodels`
(`models[].name` sin prefijo `models/`), `ollama_tags` (`models[].name`). Sin key configurada
→ `skipped`. 401 → `auth_failed`. Timeout/conexión → `unreachable`. **Cero tokens de inferencia.**

### 1.4 `src/atlas/core/self_maintenance/model_catalog_drift.py` (NUEVO) — deriva lista↔realidad

```python
@dataclass
class CatalogDriftResult:
    provider_name: str
    configured_model: str
    present: bool | None          # True=servido, False=ausente(→404/410 futuro), None=no comprobable
    outcome: str                  # "present" | "missing" | "skipped"
    reason: str

class ModelCatalogDrift:
    def __init__(self, *, providers=DEFAULT_PROVIDERS, discover=discover_available_models): ...
    def run(self) -> list[CatalogDriftResult]: ...
```

Cruza `provider.model_id` (normalizado) contra `DiscoveryResult.model_ids`. `missing` = el modelo
configurado ya NO lo sirve el proveedor → predice el 404/410 ANTES de quemar la llamada (exactamente
la clase de fallo que ha mordido: qwen3-coder 410, kimi 404, deepseek decomisionado). Es el
complemento barato del smoke: discovery/drift no gasta ni 8 tokens.

### 1.5 `src/atlas/core/provider_preflight.py` (NUEVO) — pre-vuelo go/no-go barato

```python
@dataclass
class PreflightVerdict:
    ok: bool
    level: str
    reason: str
    live_providers: list[str]     # proveedores del nivel con señal de vida
    dead_providers: list[str]

def provider_preflight(
    level: InferenceLevel, *, root: Path,
    require_live_probe: bool = False,     # True = además golpea /v1/models (barato, sin tokens)
    discover=discover_available_models,
) -> PreflightVerdict: ...
```

Capas (de más barata a más cara, corta en la primera que decide):
- **Capa 0 (cero red):** lee `provider_smoke_state.json` + `provider_discovery_state.json`. Si hay
  ≥1 proveedor del `level` con `outcome=ok`/no-drift y fecha <24h → `ok=True` sin tocar red.
- **Capa 1 (red barata, cero tokens):** si `require_live_probe` o el estado está viejo/ausente,
  hace `GET /v1/models` (reusa `discover_available_models` como ping: 200=vivo+auth ok, 401=key
  muerta, timeout=caído). NO hace inferencia.

Uso: cualquier loop pesado (autobuild `SelfBuildRunner`, digestión masiva, Cónclave) llama
`provider_preflight(level)` ANTES de lanzar N iteraciones y aborta rápido y barato si no hay
proveedor vivo del nivel, en vez de descubrirlo a mitad de una tanda cara.

### 1.6 Tick + reality (espejo exacto del smoke)
- `maintenance_facade.maintenance_provider_discovery_tick`: opt-in `ATLAS_PROVIDER_DISCOVERY=1`,
  guardia `ATLAS_NESTED_TEST_RUN`, cadencia 24h por fichero, corre `ModelCatalogDrift`, escribe
  `workspace/self_build/provider_discovery_state.json`, Merkle log `self_maintenance.provider_discovery_tick`.
  Añadir a la lista de ciclos aislados junto a `_provider_smoke_cycle`.
- `reality._provider_discovery_state(root)`: proyección fail-honesta (fichero ausente→`never_ran`
  con razón; nunca lanza). Cablear en `collect_reality` como `"provider_discovery": _provider_discovery_state(root)`.

### 1.7 Fallbacks documentados (ser realista)
- **Gemini / Ollama**: no OpenAI-compat para listar → adaptadores nativos propios (ya en §1.3).
- **NIM lista-pero-no-sirve**: discovery puede reportar `present=True` y aun así el tier dar 404 al
  invocar → **el smoke sigue siendo necesario** como verificación de invocación real. Discovery+drift
  NO reemplaza al smoke; lo antecede y lo abarata (filtra los muertos-por-catálogo antes).
- **Proveedor sin endpoint de discovery / sin key**: `outcome=skipped`; el drift cae a la lista fija
  y se anota `last_manual_verification` (fecha) para ese proveedor. Los paid-gated por decisión del
  operador (p.ej. `hermes-4-405b` sin crédito) siguen siendo manuales — documentar, no automatizar.

---

## 2. Descomposición en tareas (TDD, orden por dependencia)

Ver el array JSON al final. Resumen de dependencias:
`T1 → T2` (errores → wiring hub); `T3` independiente; `T3 → T4 → T6 → T7` (discovery →
drift → tick → reality); `T3 → T5` (discovery → preflight); `T5 → T8` (preflight → cablear en autobuild).
T1 y T3 pueden ir en paralelo. Cada tarea escribe su test que falla primero.

Integración con lo existente: T2 **modifica** `inference_hub.py` y **refactoriza** `_classify_error`/
`_is_transient` (mantener comportamiento por defecto — los tests existentes de `test_inference_hub_real.py`
deben seguir verdes). T6/T7 **copian** el patrón de smoke tick + reality state (no reconstruir).
El smoke (T5.1) se queda tal cual; discovery es una capa nueva que lo antecede.

---

```json
[
  {
    "id": "T1",
    "titulo": "provider_errors.py: ErrorKind + ProviderError + classify_provider_error (lee status_code y Retry-After/x-ratelimit defensivamente)",
    "complejidad": "sustancial",
    "archivos": ["src/atlas/core/provider_errors.py", "tests/test_provider_errors.py"],
    "criterios_aceptacion": [
      "classify_provider_error mapea 429→RATE_LIMIT retryable=True, 401/403→AUTH retryable=False, 404/410→NOT_FOUND retryable=False, 5xx/ServiceUnavailable→SERVER retryable=True, Timeout→TIMEOUT retryable=True, APIConnection→CONNECTION retryable=True, 400+context→CONTEXT_LENGTH retryable=False",
      "usa exc.status_code cuando existe y cae al nombre de la clase como respaldo",
      "_extract_retry_after devuelve segundos del header 'retry-after' y, si falta, de 'x-ratelimit-reset-requests'/'-tokens', leyendo via getattr(exc,'response',None).headers y getattr(exc,'litellm_response_headers',None) sin lanzar si no existen",
      "una excepcion sin status_code ni headers → kind=UNKNOWN, retryable=False, retry_after_s=None (nunca lanza)",
      "tests usan excepciones falsas (dataclass/SimpleNamespace) con status_code y response.headers; cero red, cero litellm real"
    ],
    "depende_de": []
  },
  {
    "id": "T2",
    "titulo": "Cablear classify_provider_error en InferenceHub: campos error_kind/retry_after_s/retryable en InferenceResponse; cooldown honra Retry-After; _classify_error y _is_transient reimplementados",
    "complejidad": "sustancial",
    "archivos": ["src/atlas/core/inference_hub.py", "tests/test_inference_hub_real.py"],
    "criterios_aceptacion": [
      "InferenceResponse gana error_kind:str='', retry_after_s:float|None=None, retryable:bool=False (aditivo, defaults no rompen callers)",
      "_call_provider_real puebla esos 3 campos en el InferenceResponse de fallo desde classify_provider_error(last_exc)",
      "en RATE_LIMIT con retry_after_s presente, _rate_limited_until usa ese valor; sin header cae a RATE_LIMIT_COOLDOWN_S (comportamiento previo intacto)",
      "AUTH y NOT_FOUND ponen ProviderStatus.DOWN (no se re-queman)",
      "_is_transient(exc) == classify_provider_error(exc).retryable",
      "toda la suite test_inference_hub_real.py existente sigue verde (sin cambios de comportamiento por defecto)"
    ],
    "depende_de": ["T1"]
  },
  {
    "id": "T3",
    "titulo": "provider_discovery.py: discover_available_models con 3 adaptadores (openai_models/gemini_listmodels/ollama_tags), http_get inyectable, resolucion de ruta por proveedor, cero tokens",
    "complejidad": "sustancial",
    "archivos": ["src/atlas/core/provider_discovery.py", "tests/test_provider_discovery.py"],
    "criterios_aceptacion": [
      "discovery_kind() devuelve openai_models para Groq/OpenRouter/NVIDIA/Together, gemini_listmodels para Gemini, ollama_tags para ollama_local",
      "models_url() resuelve Groq→base+'/openai/v1/models', openai-compat generico→base+'/models', gemini→v1beta/models?key=, ollama→/api/tags",
      "discover_available_models con http_get inyectado que devuelve un payload data[].id extrae model_ids correctamente; forma gemini (models[].name) y ollama (models[].name) parseadas por su adaptador",
      "sin key configurada (api_key_env no en entorno y no ollama) → outcome='skipped'; http 401 → 'auth_failed'; timeout/conexion → 'unreachable'; nunca lanza",
      "ningun test toca red real (http_get siempre inyectado) ni llama a litellm.completion"
    ],
    "depende_de": []
  },
  {
    "id": "T4",
    "titulo": "model_catalog_drift.py: ModelCatalogDrift cruza model_id configurado vs catalogo descubierto (present/missing/skipped)",
    "complejidad": "sustancial",
    "archivos": ["src/atlas/core/self_maintenance/model_catalog_drift.py", "tests/test_model_catalog_drift.py"],
    "criterios_aceptacion": [
      "run() devuelve un CatalogDriftResult por proveedor con discover inyectado",
      "modelo configurado presente en model_ids → outcome='present'; ausente → 'missing' (predice 404/410); discovery skipped/unreachable → 'skipped' con reason",
      "normaliza el id para comparar (p.ej. sufijos ':free' de OpenRouter) sin falsos 'missing'",
      "un fixture con un provider cuyo model_id no esta en el catalogo produce exactamente un 'missing'"
    ],
    "depende_de": ["T3"]
  },
  {
    "id": "T5",
    "titulo": "provider_preflight.py: provider_preflight(level) go/no-go por capas (estado en disco → /v1/models barato), cero tokens de inferencia",
    "complejidad": "sustancial",
    "archivos": ["src/atlas/core/provider_preflight.py", "tests/test_provider_preflight.py"],
    "criterios_aceptacion": [
      "Capa 0: con provider_smoke_state.json que tiene ≥1 provider ok del nivel y fecha <24h, devuelve ok=True sin invocar discover (verificable con discover que lanzaria si se llama)",
      "Capa 1: con require_live_probe=True o estado ausente/viejo, usa discover_available_models como ping (200→vivo, 401→dead, timeout→dead) y jamas hace inferencia",
      "nivel sin ningun proveedor vivo → ok=False con reason y dead_providers poblado",
      "PreflightVerdict.live_providers/dead_providers reflejan los proveedores evaluados del nivel"
    ],
    "depende_de": ["T3"]
  },
  {
    "id": "T6",
    "titulo": "maintenance_provider_discovery_tick: opt-in ATLAS_PROVIDER_DISCOVERY=1, cadencia 24h, escribe provider_discovery_state.json, Merkle log, ciclo aislado (espejo del smoke tick)",
    "complejidad": "sustancial",
    "archivos": ["src/atlas/core/orchestrator_parts/maintenance_facade.py", "tests/test_maintenance_provider_discovery_tick.py"],
    "criterios_aceptacion": [
      "sin ATLAS_PROVIDER_DISCOVERY=1 → {'status':'disabled'}; con ATLAS_NESTED_TEST_RUN=1 → {'status':'nested_run_guard'}",
      "primera corrida del dia escribe workspace/self_build/provider_discovery_state.json con last_run_date y last_results (lista de CatalogDriftResult.to_dict())",
      "segunda corrida el mismo dia → {'status':'already_ran_today'} sin recomputar",
      "emite Merkle log action='self_maintenance.provider_discovery_tick' con missing/present/skipped",
      "se registra como ciclo aislado junto a _provider_smoke_cycle en el arranque de mantenimiento"
    ],
    "depende_de": ["T4"]
  },
  {
    "id": "T7",
    "titulo": "reality._provider_discovery_state(root): proyeccion fail-honesta cableada en collect_reality (espejo de _provider_smoke_state)",
    "complejidad": "sustancial",
    "archivos": ["src/atlas/core/reality.py", "tests/test_reality.py"],
    "criterios_aceptacion": [
      "collect_reality()['provider_discovery'] existe siempre",
      "fichero ausente → status='never_ran' con reason que menciona ATLAS_PROVIDER_DISCOVERY=1; fichero corrupto → never_ran con reason del error; nunca lanza",
      "con estado que tiene ≥1 'missing', el reason nombra los model_id ausentes (deriva accionable)",
      "atlas reality --json muestra la seccion sin tocar red"
    ],
    "depende_de": ["T6"]
  },
  {
    "id": "T8",
    "titulo": "Cablear provider_preflight en el loop pesado (SelfBuildRunner/autobuild) para abortar barato antes de N iteraciones",
    "complejidad": "trivial",
    "archivos": ["src/atlas/core/self_maintenance/self_build_runner.py", "tests/test_self_build_runner.py"],
    "criterios_aceptacion": [
      "el runner llama provider_preflight(level) antes de lanzar la tanda y, si ok=False, aborta con un resultado explicito (no arranca N iteraciones)",
      "preflight ok=True deja el flujo actual intacto (sin cambio de comportamiento cuando hay proveedor vivo)",
      "un test con preflight inyectado que devuelve ok=False verifica el corte temprano sin llamar a inferencia"
    ],
    "depende_de": ["T5"]
  }
]
```

Comandos de verificación (para el auditor): `uv run --frozen pytest tests/ -q -m "not computer_use"` · `uv run --frozen mypy src/atlas/` · `atlas reality --json` (comprobar la nueva sección `provider_discovery`)
