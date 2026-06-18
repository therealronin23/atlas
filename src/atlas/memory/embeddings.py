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
