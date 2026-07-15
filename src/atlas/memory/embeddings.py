"""
Atlas Core — Embedding providers para memoria vectorial (Gate D/D4).

Define el protocolo Embedder y dos implementaciones:

- StubEmbedder: deterministico, in-process, sin red. Bag-of-words con hash
  SHA-256 distribuido en `dim` slots y normalizado L2. Suficiente para tests
  y para arrancar sin keys externas.

- LiteLLMEmbedder: wrapper sobre litellm.embedding. Soporta cualquier
  modelo de embeddings que LiteLLM enrute (OpenAI, Gemini, Together,
  Cohere, ...). Lee la key del entorno via env var configurable.

El modo "auto" (default) en LiteLLMEmbedder cae a stub durante pytest o
cuando no hay key del proveedor. Espeja la logica de InferenceHub para
mantener la suite hermetica.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

litellm: Any | None = None
_HAS_LITELLM = importlib.util.find_spec("litellm") is not None


def _litellm_module() -> Any:
    global litellm
    if litellm is None:
        if not _HAS_LITELLM:
            raise RuntimeError("litellm no instalado pero mode=live")
        litellm = importlib.import_module("litellm")
    return litellm


# ---------------------------------------------------------------------------
# Protocolo
# ---------------------------------------------------------------------------


@runtime_checkable
class Embedder(Protocol):
    """Embedding-space contract used by persistent vector stores.

    ``dim`` alone is insufficient: unrelated models routinely share a vector
    length. ``identity`` therefore names the declared producer space and
    ``fingerprint`` provides a compact integrity value for persistence. Local
    model implementations bind this to artifact bytes; hosted aliases can only
    identify the provider declaration unless the provider exposes a revision.
    """

    @property
    def dim(self) -> int: ...

    @property
    def identity(self) -> str: ...

    @property
    def fingerprint(self) -> str: ...

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


def embedding_identity_fingerprint(identity: str) -> str:
    """Return the stable digest persisted alongside an embedder identity."""
    return f"sha256:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


# ---------------------------------------------------------------------------
# Stub: hash-based bag-of-words, deterministico
# ---------------------------------------------------------------------------


class StubEmbedder:
    """
    Embeddings deterministicos basados en hash de palabras.

    No es semantico de verdad — pero textos que comparten palabras producen
    vectores similares, lo cual es suficiente para validar el pipeline y
    para tests. Salida normalizada L2.
    """

    def __init__(self, dim: int = 64) -> None:
        if dim <= 0:
            raise ValueError(f"dim debe ser positivo, recibido {dim}")
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def identity(self) -> str:
        # Bump v1 if tokenisation, hashing, signed-counting or normalisation changes.
        return (
            "atlas.stub.sha256-bow-signed-l2:v1;"
            f"dim={self._dim};tokenizer=unicode-lower-whitespace"
        )

    @property
    def fingerprint(self) -> str:
        return embedding_identity_fingerprint(self.identity)

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        tokens = text.lower().split() or [text.lower()]
        for token in tokens:
            h = hashlib.sha256(token.encode("utf-8")).digest()
            slot = int.from_bytes(h[:4], "big") % self._dim
            sign = 1.0 if h[4] & 1 else -1.0   # signed counter (reduce colisiones)
            vec[slot] += sign
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0.0:
            return vec
        return [x / norm for x in vec]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


# ---------------------------------------------------------------------------
# Live: LiteLLM
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiteLLMEmbedderConfig:
    """
    Configuracion de un proveedor de embeddings via LiteLLM.

    Ejemplos:
      OpenAI:  model="openai/text-embedding-3-small", dim=1536
      Gemini:  model="gemini/text-embedding-004",     dim=768
      Together:model="together_ai/togethercomputer/m2-bert-80M-8k-retrieval",
                                                       dim=768
    """

    model: str
    dim: int
    api_key_env: str | None = None  # None -> usa el default que sepa LiteLLM


class LiteLLMEmbedder:
    """
    Embedder real via LiteLLM. Modo auto/live/stub coherente con InferenceHub:
      - "auto": stub si pytest o sin key; live si litellm + key presentes.
      - "live": fuerza llamada real (falla si no hay key).
      - "stub": nunca llama al exterior.
    """

    def __init__(
        self,
        config: LiteLLMEmbedderConfig,
        mode: str = "auto",
        stub_fallback: StubEmbedder | None = None,
    ) -> None:
        self._config = config
        self._mode = os.environ.get("ATLAS_EMBEDDING_MODE", mode)
        if self._mode not in ("auto", "live", "stub"):
            raise ValueError(f"mode invalido: {self._mode}")
        self._stub = stub_fallback or StubEmbedder(dim=config.dim)
        if self._stub.dim != config.dim:
            raise ValueError(
                f"stub.dim ({self._stub.dim}) != config.dim ({config.dim})"
            )
        # Resolve auto exactly once. Changing credentials later must not switch
        # the vector space used by an already-open persistent store.
        self._effective_mode = self._resolve_effective_mode()

    @property
    def dim(self) -> int:
        return self._config.dim

    @property
    def model(self) -> str:
        return self._config.model

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def effective_mode(self) -> str:
        return self._effective_mode

    @property
    def identity(self) -> str:
        fallback = (
            f";fallback={self._stub.identity}"
            if self._effective_mode == "stub"
            else ""
        )
        return (
            "litellm.embedding:v1;"
            f"model={self._config.model};dim={self._config.dim};"
            f"effective_mode={self._effective_mode}{fallback}"
        )

    @property
    def fingerprint(self) -> str:
        return embedding_identity_fingerprint(self.identity)

    def embed(self, text: str) -> list[float]:
        if self._resolve_live():
            return self._embed_live([text])[0]
        return self._stub.embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._resolve_live():
            return self._embed_live(texts)
        return self._stub.embed_batch(texts)

    # ---------------------------------------------------------------------

    def _resolve_live(self) -> bool:
        return self._effective_mode == "live"

    def _resolve_effective_mode(self) -> str:
        if self._mode == "stub":
            return "stub"
        if self._mode == "live":
            return "live"
        # auto
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return "stub"
        if not _HAS_LITELLM:
            return "stub"
        if self._config.api_key_env is None:
            return "live"   # litellm puede tener key implicita
        return "live" if os.environ.get(self._config.api_key_env) else "stub"

    def _embed_live(self, texts: list[str]) -> list[list[float]]:
        if not _HAS_LITELLM:
            raise RuntimeError("litellm no instalado pero mode=live")
        llm = _litellm_module()
        api_key = (
            os.environ.get(self._config.api_key_env)
            if self._config.api_key_env
            else None
        )
        response = llm.embedding(
            model=self._config.model,
            input=texts,
            api_key=api_key,
        )
        # litellm.EmbeddingResponse: .data es una lista de {'embedding': [...]}
        out: list[list[float]] = []
        for item in response.data:
            if isinstance(item, dict):
                out.append(list(item["embedding"]))
            else:
                out.append(list(item.embedding))
        if len(out) != len(texts):
            raise RuntimeError(
                f"litellm.embedding devolvio {len(out)} vectores para {len(texts)} inputs"
            )
        # Verificar dim consistente
        for v in out:
            if len(v) != self._config.dim:
                raise RuntimeError(
                    f"dim inesperada: {len(v)} vs config {self._config.dim} "
                    f"(modelo {self._config.model})"
                )
        return out


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


PRESET_OPENAI_SMALL = LiteLLMEmbedderConfig(
    model="openai/text-embedding-3-small",
    dim=1536,
    api_key_env="OPENAI_API_KEY",
)
PRESET_GEMINI_004 = LiteLLMEmbedderConfig(
    model="gemini/text-embedding-004",
    dim=768,
    api_key_env="GEMINI_API_KEY",
)
PRESET_TOGETHER_M2_BERT = LiteLLMEmbedderConfig(
    model="together_ai/togethercomputer/m2-bert-80M-8k-retrieval",
    dim=768,
    api_key_env="TOGETHERAI_API_KEY",
)


# ---------------------------------------------------------------------------
# Local: fastembed (ONNX, SIN torch) — embeddings semánticos in-process, offline
# ---------------------------------------------------------------------------

# Modelo por defecto: multilingüe (la memoria de Atlas puede ser en español) y
# ligero (dim 384, cuantizado ONNX). fastembed descarga+cachea el modelo en el
# primer uso. Extra opcional `[embeddings]`; el núcleo sigue usable sin la dep.
FASTEMBED_DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
FASTEMBED_DEFAULT_DIM = 384


class FastEmbedEmbedder:
    """Embedder semántico LOCAL vía fastembed (ONNX, sin torch).

    A diferencia de `LiteLLMEmbedder` (API hospedada, lock-in + coste/llamada),
    corre in-process, sin proveedor por-llamada. Misma familia de modelos que
    sentence-transformers (BGE/E5/MiniLM) pero servidos por ONNX, sin los GBs de
    torch. `dim` debe coincidir con el modelo (e5-small/BGE-small = 384).

    HONESTIDAD (hallazgo del Cónclave, auditoría 2026-07-03): el PRIMER uso SÍ
    requiere red — `fastembed` descarga el modelo ONNX (~100MB) desde su hub
    remoto la primera vez que se instancia, sin pin de hash en este código (el
    propio paquete gestiona su caché en `~/.cache/fastembed`). Usos posteriores
    con el modelo ya cacheado son offline. Si el entorno no tiene red en el
    primer arranque (CI aislado, sandbox sin egress), usa
    `ATLAS_EMBEDDER=stub` para evitar la descarga.

    Fail-closed: si `fastembed` no está instalado, lanza RuntimeError explícito —
    NO cae a stub callado (mezclar vectores stub y reales corrompe el recall)."""

    # Cache de PROCESO del modelo ONNX por nombre (2026-07-10): cargar
    # TextEmbedding cuesta ~450-500MB de RSS que el allocator/onnxruntime NO
    # devuelve al SO ni tras liberar la instancia (verificado con gc: 0
    # instancias vivas y el RSS se queda). Cada FastEmbedEmbedder nuevo sin
    # cache sumaba ~500MB irreversibles — la suite acumulaba 7.5GB y earlyoom
    # la mataba (y el daemon pagaba lo mismo por cada índice que abría).
    # embed() de fastembed es stateless: compartir la instancia es seguro.
    _MODEL_CACHE: dict[str, Any] = {}
    _ARTIFACT_DIGEST_CACHE: dict[str, str] = {}

    def __init__(
        self, model_name: str = FASTEMBED_DEFAULT_MODEL, dim: int = FASTEMBED_DEFAULT_DIM
    ) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - depende de extra opcional
            raise RuntimeError(
                "fastembed no instalado: pip install 'atlas-core[embeddings]' "
                "(o quita ATLAS_EMBEDDER=fastembed para usar el stub)"
            ) from exc
        cached = self._MODEL_CACHE.get(model_name)
        if cached is None:
            cached = TextEmbedding(model_name=model_name)
            self._MODEL_CACHE[model_name] = cached
        self._model = cached
        self._dim = dim
        self._model_name = model_name
        metadata = importlib.import_module("importlib.metadata")
        try:
            self._implementation_version = metadata.version("fastembed")
        except metadata.PackageNotFoundError:  # pragma: no cover - dev shim
            module = importlib.import_module("fastembed")
            self._implementation_version = str(
                getattr(module, "__version__", "unversioned")
            )
        artifact_digest = self._ARTIFACT_DIGEST_CACHE.get(model_name)
        if artifact_digest is None:
            artifact_digest = self._artifact_digest(cached)
            self._ARTIFACT_DIGEST_CACHE[model_name] = artifact_digest
        self._artifact_sha256 = artifact_digest

    @staticmethod
    def _artifact_digest(model: Any) -> str:
        """Hash the exact local tokenizer/model artifacts used by FastEmbed.

        Model names and package versions are not sufficient: a remote model
        repository can move while retaining its alias. FastEmbed exposes the
        resolved snapshot directory on its concrete pooled model. If that
        directory cannot be established, persistent identity must fail closed.
        """
        concrete = getattr(model, "model", None)
        raw_dir = getattr(concrete, "_model_dir", None)
        if raw_dir is None:
            raise RuntimeError(
                "fastembed did not expose its resolved model artifact directory; "
                "cannot derive a persistent embedding identity"
            )
        root = Path(raw_dir)
        if not root.is_dir():
            raise RuntimeError(
                f"fastembed model artifact directory is unavailable: {root}"
            )
        manifest = hashlib.sha256()
        files = sorted(path for path in root.rglob("*") if path.is_file())
        if not files:
            raise RuntimeError(f"fastembed model artifact directory is empty: {root}")
        for path in files:
            relative = path.relative_to(root).as_posix().encode("utf-8")
            content_hash = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    content_hash.update(block)
            manifest.update(len(relative).to_bytes(4, "big"))
            manifest.update(relative)
            manifest.update(content_hash.digest())
        return manifest.hexdigest()

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def identity(self) -> str:
        return (
            "fastembed.onnx:v2;"
            f"model={self._model_name};dim={self._dim};"
            f"implementation_version={self._implementation_version};"
            f"artifact_sha256={self._artifact_sha256}"
        )

    @property
    def fingerprint(self) -> str:
        return embedding_identity_fingerprint(self.identity)

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out = [[float(x) for x in vec] for vec in self._model.embed(texts)]
        if len(out) != len(texts):
            raise RuntimeError(
                f"fastembed devolvió {len(out)} vectores para {len(texts)} inputs"
            )
        for v in out:
            if len(v) != self._dim:
                raise RuntimeError(
                    f"dim inesperada: {len(v)} vs {self._dim} (modelo {self._model_name})"
                )
        return out


def default_embedder() -> "Embedder":
    """Selector del embedder para la memoria del tronco, gobernado por env.

    - default (sin definir) / `ATLAS_EMBEDDER=fastembed` → `FastEmbedEmbedder`
      (semántico local, dim 384, ONNX sin torch — ya sin API hospedada de por
      medio, cero lock-in). Fail-closed: si la dep no está, propaga el
      RuntimeError (no cae a stub silenciosamente).
    - `ATLAS_EMBEDDER=stub` → `StubEmbedder(dim=64)` (hash, no semántico —
      opt-OUT explícito, para tests/CI que no quieran cargar el modelo ONNX).

    2026-07-03: se cambió el default de stub→fastembed (verificado: el store
    real de memoria en `~/atlas-mcp/memory.db` tenía 0 registros, sin datos que
    migrar). Cambiar de embedder cambia el espacio vectorial; un store existente
    con dim distinta dispara el guard de dimensión del índice (migración honesta
    = rebuild, no mezcla silenciosa) — revisar antes de tocar un store con datos
    reales."""
    choice = os.environ.get("ATLAS_EMBEDDER", "fastembed").strip().lower()
    if choice == "stub":
        return StubEmbedder(dim=64)
    return FastEmbedEmbedder()
