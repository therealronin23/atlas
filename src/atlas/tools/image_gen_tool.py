"""
Atlas Core — Image Generation Tool (absorbido de Hermes-Agent, 2026-07-18).

Capacidad genuinamente nueva: Atlas no tenía generación de imagen (ver
docs/design/absorption_master_plan.md, sección "Genuinely new"). Backend real:
fal.ai vía el SDK oficial ``fal_client`` (sin conflicto de dependencias,
verificado con pip dry-run antes de instalar — mismo patrón de precaución que
crawl4ai/computer-control-mcp). Misma disciplina de gobernanza que
StirlingPdfTool: output_path pasa por ExternalFsBridge antes de escribir,
requiere credencial explícita (FAL_KEY), audita cada llamada en Merkle. Nunca
se pasa por la lógica de aprobación propia de Hermes — solo por la de Atlas
(ver absorption_master_plan.md, "Governance gap").
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

DEFAULT_MODEL = "fal-ai/flux/dev"
VALID_ASPECT_RATIOS = ("landscape", "square", "portrait")


@dataclass(frozen=True)
class ImageGenResult:
    prompt: str
    model: str
    output_path: str
    success: bool
    image_url: str = ""
    bytes_written: int = 0
    error: str | None = None


class ImageGenTool:
    """Genera una imagen vía fal.ai y la guarda en output_path (gobernado)."""

    def __init__(
        self,
        fs_bridge: ExternalFsBridge,
        api_key_env: str = "FAL_KEY",
        merkle: MerkleLogger | None = None,
        timeout_s: float = 120.0,
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
        aspect_ratio: str = "landscape",
    ) -> ImageGenResult:
        out_decision = self._fs_bridge.check(output_path)
        if not out_decision.allowed:
            self._log(
                "image_gen.generate", "blocked", risk_level="high",
                payload={"model": model, "output_path": output_path, "reason": out_decision.reason},
            )
            raise PermissionError(f"ExternalFsBridge bloqueó output_path: {out_decision.reason}")

        if aspect_ratio not in VALID_ASPECT_RATIOS:
            error = f"aspect_ratio inválido: {aspect_ratio!r} (válidos: {VALID_ASPECT_RATIOS})"
            self._log("image_gen.generate", "failed", risk_level="safe", payload={"error": error})
            return ImageGenResult(
                prompt=prompt, model=model, output_path=output_path,
                success=False, error=error,
            )

        if self._api_key_env not in os.environ:
            error = f"{self._api_key_env} no está definida en el entorno"
            self._log(
                "image_gen.generate", "failed", risk_level="moderate",
                payload={"model": model, "error": error},
            )
            return ImageGenResult(
                prompt=prompt, model=model, output_path=output_path,
                success=False, error=error,
            )

        assert out_decision.resolved_path is not None
        start = time.perf_counter()
        try:
            image_url, bytes_written = self._call_and_save(
                prompt, model, aspect_ratio, out_decision.resolved_path,
            )
        except Exception as exc:  # noqa: BLE001 — el SDK/red no debe tumbar el loop
            error = f"{type(exc).__name__}: {exc}"
            self._log(
                "image_gen.generate", "failed", risk_level="moderate",
                payload={"model": model, "error": error,
                         "duration_ms": int((time.perf_counter() - start) * 1000)},
            )
            return ImageGenResult(
                prompt=prompt, model=model, output_path=output_path,
                success=False, error=error,
            )

        duration_ms = int((time.perf_counter() - start) * 1000)
        self._log(
            "image_gen.generate", "ok", risk_level="safe",
            payload={"model": model, "bytes_written": bytes_written, "duration_ms": duration_ms},
        )
        return ImageGenResult(
            prompt=prompt, model=model, output_path=output_path,
            success=True, image_url=image_url, bytes_written=bytes_written,
        )

    def _call_and_save(
        self, prompt: str, model: str, aspect_ratio: str, resolved_output_path: str,
    ) -> tuple[str, int]:
        """Llamada real al SDK fal_client + descarga del resultado. Aislado en
        su propio método para que los tests puedan monkeypatchear
        _fal_subscribe/_download sin tocar la lógica de gobernanza de arriba."""
        result = self._fal_subscribe(model, prompt, aspect_ratio)
        images = result.get("images") or []
        if not images:
            raise ValueError(f"fal.ai no devolvió imágenes: {result!r}"[:300])
        image_url = images[0].get("url", "")
        if not image_url:
            raise ValueError("fal.ai devolvió una imagen sin url")
        data = self._download(image_url)
        Path(resolved_output_path).write_bytes(data)
        return image_url, len(data)

    def _fal_subscribe(self, model: str, prompt: str, aspect_ratio: str) -> dict[str, Any]:
        import fal_client  # noqa: PLC0415 — import perezoso, solo al generar de verdad

        return fal_client.subscribe(
            model,
            arguments={"prompt": prompt, "aspect_ratio": aspect_ratio},
        )

    def _download(self, url: str) -> bytes:
        if url.startswith("data:"):
            # fal.ai puede devolver data URIs para imágenes pequeñas
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
            action=action, agent="image_gen.tool", result=result,
            risk_level=risk_level, payload=payload or {},
        )
