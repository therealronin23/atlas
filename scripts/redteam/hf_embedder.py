"""Adaptador Embedder local (HuggingFace) para validación — SOLO dev/red-team.

NO es runtime del paquete `atlas`: vive en scripts/redteam y se carga perezosamente
desde `.venv-redteam-garak` (que ya trae transformers vía Garak). Permite
validar la curva de generalización con embeddings SEMÁNTICOS reales (no el
StubEmbedder léxico), sin clave API ni coste: modelo local all-MiniLM-L6-v2 (~90MB,
dim 384), descargado una vez y luego offline.

Implementa el Protocol atlas.memory.embeddings.Embedder (embed/embed_batch/dim).
Mean-pooling con máscara de atención + normalización L2 (uso estándar de MiniLM).
"""
from __future__ import annotations

import math

_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class HFLocalEmbedder:
    def __init__(self, model_name: str = _DEFAULT_MODEL, *, max_length: int = 128) -> None:
        from transformers import AutoModel, AutoTokenizer  # lazy: solo en venv redteam

        self._tok = AutoTokenizer.from_pretrained(model_name)
        self._mdl = AutoModel.from_pretrained(model_name)
        self._mdl.eval()
        self._max_length = max_length
        self._dim = int(self._mdl.config.hidden_size)

    @property
    def dim(self) -> int:
        return self._dim

    def _embed_batch_raw(self, texts: list[str]) -> list[list[float]]:
        import torch

        batch = self._tok(
            texts, return_tensors="pt", truncation=True,
            max_length=self._max_length, padding=True,
        )
        with torch.no_grad():
            out = self._mdl(**batch)
        # mean-pooling con máscara de atención
        mask = batch["attention_mask"].unsqueeze(-1).type_as(out.last_hidden_state)
        summed = (out.last_hidden_state * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1e-9)
        mean = summed / counts
        # normalización L2 (para coseno estable)
        normed = torch.nn.functional.normalize(mean, p=2, dim=1)
        return [row.tolist() for row in normed]

    def embed(self, text: str) -> list[float]:
        return self._embed_batch_raw([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed_batch_raw(texts)
