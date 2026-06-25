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
import math
import os
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

try:
    import litellm
    _HAS_LITELLM = True
except ImportError:  # pragma: no cover
    litellm = None  # type: ignore[assignment]
    _HAS_LITELLM = False


# ---------------------------------------------------------------------------
# Protocolo
# ---------------------------------------------------------------------------


@runtime_checkable
class Embedder(Protocol):
    """Protocolo minimo. La dim fija debe ser estable durante la vida del store."""

    @property
    def dim(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


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
        if mode not in ("auto", "live", "stub"):
            raise ValueError(f"mode invalido: {mode}")
        self._config = config
        self._mode = os.environ.get("ATLAS_EMBEDDING_MODE", mode)
        self._stub = stub_fallback or StubEmbedder(dim=config.dim)
        if self._stub.dim != config.dim:
            raise ValueError(
                f"stub.dim ({self._stub.dim}) != config.dim ({config.dim})"
            )

    @property
    def dim(self) -> int:
        return self._config.dim

    @property
    def model(self) -> str:
        return self._config.model

    @property
    def mode(self) -> str:
        return self._mode

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
        if self._mode == "stub":
            return False
        if self._mode == "live":
            return True
        # auto
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return False
        if not _HAS_LITELLM:
            return False
        if self._config.api_key_env is None:
            return True   # litellm puede tener key implicita
        return bool(os.environ.get(self._config.api_key_env))

    def _embed_live(self, texts: list[str]) -> list[list[float]]:
        if not _HAS_LITELLM:
            raise RuntimeError("litellm no instalado pero mode=live")
        assert litellm is not None
        api_key = (
            os.environ.get(self._config.api_key_env)
            if self._config.api_key_env
            else None
        )
        response = litellm.embedding(
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
    corre in-process y offline: ni red ni proveedor. Misma familia de modelos que
    sentence-transformers (BGE/E5/MiniLM) pero servidos por ONNX, sin los GBs de
    torch. `dim` debe coincidir con el modelo (e5-small/BGE-small = 384).

    Fail-closed: si `fastembed` no está instalado, lanza RuntimeError explícito —
    NO cae a stub callado (mezclar vectores stub y reales corrompe el recall)."""

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
        self._model = TextEmbedding(model_name=model_name)
        self._dim = dim
        self._model_name = model_name

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model(self) -> str:
        return self._model_name

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

    - `ATLAS_EMBEDDER=fastembed` → `FastEmbedEmbedder` (semántico local, dim 384).
      Fail-closed: si la dep no está, propaga el RuntimeError (no cae a stub).
    - cualquier otro valor / sin definir → `StubEmbedder(dim=64)` (default actual).

    Opt-in DELIBERADO: cambiar de embedder cambia el espacio vectorial; un store
    existente con dim distinta dispara el guard de dimensión del índice (migración
    honesta = rebuild, no mezcla silenciosa)."""
    choice = os.environ.get("ATLAS_EMBEDDER", "stub").strip().lower()
    if choice == "fastembed":
        return FastEmbedEmbedder()
    return StubEmbedder(dim=64)
