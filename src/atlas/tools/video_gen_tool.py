"""
Atlas Core — Video Generation Tool (absorbido de Hermes-Agent, 2026-07-18).

Hermana de ImageGenTool: capacidad genuinamente nueva (Atlas no tenía
generación de vídeo, ver docs/design/absorption_master_plan.md). Mismo
backend real (fal.ai vía ``fal_client``, ya instalado y sin conflicto), misma
disciplina de gobernanza (ExternalFsBridge + credencial explícita + Merkle).
Modelo por defecto tomado del catálogo real de Hermes
(``hermes-agent/plugins/video_gen/fal/*.py``) — ltx-2.3 es la familia más
ligera/barata, razonable como default sin que el operador tenga que elegir.
"""

from __future__ import annotations

import base64
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.external_fs_bridge import ExternalFsBridge

DEFAULT_MODEL = "fal-ai/ltx-2.3-22b/text-to-video"
VALID_ASPECT_RATIOS = ("16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3")


@dataclass(frozen=True)
class VideoGenResult:
    prompt: str
    model: str
    output_path: str
    success: bool
    video_url: str = ""
    bytes_written: int = 0
    error: str | None = None


class VideoGenTool:
    """Genera un vídeo vía fal.ai y lo guarda en output_path (gobernado)."""

    def __init__(
        self,
        fs_bridge: ExternalFsBridge,
        api_key_env: str = "FAL_KEY",
        merkle: MerkleLogger | None = None,
        timeout_s: float = 300.0,  # vídeo tarda mucho más que imagen
    ) -> None:
        self._fs_bridge = fs_bridge
        self._api_key_env = api_key_env
        self._merkle = merkle
        self._timeout_s = timeout_s

    def generate(
        self,
        prompt: str,
        output_path: str,
        *,
        model: str = DEFAULT_MODEL,
        aspect_ratio: str = "16:9",
    ) -> VideoGenResult:
        out_decision = self._fs_bridge.check(output_path)
        if not out_decision.allowed:
            self._log(
                "video_gen.generate", "blocked", risk_level="high",
                payload={"model": model, "output_path": output_path, "reason": out_decision.reason},
            )
            raise PermissionError(f"ExternalFsBridge bloqueó output_path: {out_decision.reason}")

        if aspect_ratio not in VALID_ASPECT_RATIOS:
            error = f"aspect_ratio inválido: {aspect_ratio!r} (válidos: {VALID_ASPECT_RATIOS})"
            self._log("video_gen.generate", "failed", risk_level="safe", payload={"error": error})
            return VideoGenResult(
                prompt=prompt, model=model, output_path=output_path,
                success=False, error=error,
            )

        if self._api_key_env not in os.environ:
            error = f"{self._api_key_env} no está definida en el entorno"
            self._log(
                "video_gen.generate", "failed", risk_level="moderate",
                payload={"model": model, "error": error},
            )
            return VideoGenResult(
                prompt=prompt, model=model, output_path=output_path,
                success=False, error=error,
            )

        assert out_decision.resolved_path is not None
        start = time.perf_counter()
        try:
            video_url, bytes_written = self._call_and_save(
                prompt, model, aspect_ratio, out_decision.resolved_path,
            )
        except Exception as exc:  # noqa: BLE001 — el SDK/red no debe tumbar el loop
            error = f"{type(exc).__name__}: {exc}"
            self._log(
                "video_gen.generate", "failed", risk_level="moderate",
                payload={"model": model, "error": error,
                         "duration_ms": int((time.perf_counter() - start) * 1000)},
            )
            return VideoGenResult(
                prompt=prompt, model=model, output_path=output_path,
                success=False, error=error,
            )

        duration_ms = int((time.perf_counter() - start) * 1000)
        self._log(
            "video_gen.generate", "ok", risk_level="safe",
            payload={"model": model, "bytes_written": bytes_written, "duration_ms": duration_ms},
        )
        return VideoGenResult(
            prompt=prompt, model=model, output_path=output_path,
            success=True, video_url=video_url, bytes_written=bytes_written,
        )

    def _call_and_save(
        self, prompt: str, model: str, aspect_ratio: str, resolved_output_path: str,
    ) -> tuple[str, int]:
        result = self._fal_subscribe(model, prompt, aspect_ratio)
        video = result.get("video") or {}
        video_url = video.get("url", "") if isinstance(video, dict) else ""
        if not video_url:
            raise ValueError(f"fal.ai no devolvió vídeo: {result!r}"[:300])
        data = self._download(video_url)
        Path(resolved_output_path).write_bytes(data)
        return video_url, len(data)

    def _fal_subscribe(self, model: str, prompt: str, aspect_ratio: str) -> dict[str, Any]:
        import fal_client  # noqa: PLC0415 — import perezoso, solo al generar de verdad

        return fal_client.subscribe(
            model,
            arguments={"prompt": prompt, "aspect_ratio": aspect_ratio},
        )

    def _download(self, url: str) -> bytes:
        if url.startswith("data:"):
            _, _, b64 = url.partition(",")
            return base64.b64decode(b64)
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
            data: bytes = resp.read()
            return data

    def _log(
        self, action: str, result: str, *,
        risk_level: str = "safe", payload: dict[str, Any] | None = None,
    ) -> None:
        if self._merkle is None:
            return
        self._merkle.log(
            action=action, agent="video_gen.tool", result=result,
            risk_level=risk_level, payload=payload or {},
        )
