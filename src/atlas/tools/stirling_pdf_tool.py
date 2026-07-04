"""
Atlas Core — Stirling PDF Tool (manipulación de PDF self-hosted).

Llama a un servicio Stirling PDF REST self-hosted (Docker, localhost) para
operaciones de PDF (rotar, unir, dividir, OCR, etc.). Misma disciplina de
gobernanza que CrawlerTool: input_path Y output_path pasan por
ExternalFsBridge antes de tocar el filesystem, requiere credencial explícita
(API key vía env var), y audita cada llamada en Merkle.

Sin dependencias nuevas: multipart/form-data construido a mano con
email.mime + urllib.request (librería estándar).
"""

from __future__ import annotations

import mimetypes
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.external_fs_bridge import ExternalFsBridge


@dataclass(frozen=True)
class StirlingPdfResult:
    operation: str
    input_path: str
    output_path: str
    success: bool
    bytes_written: int
    error: str | None = None


def _build_multipart(
    fields: dict[str, str], file_field: str, file_path: Path
) -> tuple[bytes, str]:
    """Construye un cuerpo multipart/form-data a mano (sin deps nuevas)."""
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )
    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{file_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(file_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), boundary


class StirlingPdfTool:
    """Manipulación de PDF gobernada vía un servicio Stirling PDF self-hosted."""

    def __init__(
        self,
        fs_bridge: ExternalFsBridge,
        base_url: str = "http://127.0.0.1:8090",
        api_key_env: str = "STIRLING_PDF_API_KEY",
        merkle: MerkleLogger | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self._fs_bridge = fs_bridge
        self._base_url = base_url.rstrip("/")
        self._api_key_env = api_key_env
        self._merkle = merkle
        self._timeout_s = timeout_s

    def run_operation(
        self, operation: str, input_path: str, output_path: str, **params: str
    ) -> StirlingPdfResult:
        in_decision = self._fs_bridge.check(input_path)
        if not in_decision.allowed:
            self._log(
                "stirling_pdf.run_operation", "blocked", risk_level="high",
                payload={"operation": operation, "input_path": input_path, "reason": in_decision.reason},
            )
            raise PermissionError(f"ExternalFsBridge bloqueó input_path: {in_decision.reason}")

        out_decision = self._fs_bridge.check(output_path)
        if not out_decision.allowed:
            self._log(
                "stirling_pdf.run_operation", "blocked", risk_level="high",
                payload={"operation": operation, "output_path": output_path, "reason": out_decision.reason},
            )
            raise PermissionError(f"ExternalFsBridge bloqueó output_path: {out_decision.reason}")

        if self._api_key_env not in os.environ:
            error = f"{self._api_key_env} no está definida en el entorno"
            self._log(
                "stirling_pdf.run_operation", "failed", risk_level="moderate",
                payload={"operation": operation, "error": error},
            )
            return StirlingPdfResult(
                operation=operation, input_path=input_path, output_path=output_path,
                success=False, bytes_written=0, error=error,
            )

        assert in_decision.resolved_path is not None
        assert out_decision.resolved_path is not None
        body, boundary = _build_multipart(params, "fileInput", Path(in_decision.resolved_path))

        req = urllib.request.Request(
            f"{self._base_url}/api/v1/{operation}",
            data=body,
            method="POST",
            headers={
                "X-API-KEY": os.environ[self._api_key_env],
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )

        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                status = resp.status
                data = resp.read()
        except urllib.error.HTTPError as exc:
            error = f"HTTP {exc.code}: {exc.read()[:300].decode('utf-8', 'replace')}"
            self._log(
                "stirling_pdf.run_operation", "failed", risk_level="moderate",
                payload={"operation": operation, "error": error,
                         "duration_ms": int((time.perf_counter() - start) * 1000)},
            )
            return StirlingPdfResult(
                operation=operation, input_path=input_path, output_path=output_path,
                success=False, bytes_written=0, error=error,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            error = f"{type(exc).__name__}: {exc}"
            self._log(
                "stirling_pdf.run_operation", "failed", risk_level="moderate",
                payload={"operation": operation, "error": error,
                         "duration_ms": int((time.perf_counter() - start) * 1000)},
            )
            return StirlingPdfResult(
                operation=operation, input_path=input_path, output_path=output_path,
                success=False, bytes_written=0, error=error,
            )

        duration_ms = int((time.perf_counter() - start) * 1000)
        if status != 200:
            error = f"HTTP {status} inesperado"
            self._log(
                "stirling_pdf.run_operation", "failed", risk_level="moderate",
                payload={"operation": operation, "error": error, "duration_ms": duration_ms},
            )
            return StirlingPdfResult(
                operation=operation, input_path=input_path, output_path=output_path,
                success=False, bytes_written=0, error=error,
            )

        Path(out_decision.resolved_path).write_bytes(data)
        self._log(
            "stirling_pdf.run_operation", "ok", risk_level="safe",
            payload={"operation": operation, "bytes_written": len(data), "duration_ms": duration_ms},
        )
        return StirlingPdfResult(
            operation=operation, input_path=input_path, output_path=output_path,
            success=True, bytes_written=len(data), error=None,
        )

    def _log(
        self, action: str, result: str, *,
        risk_level: str = "safe", payload: dict[str, Any] | None = None,
    ) -> None:
        if self._merkle is None:
            return
        self._merkle.log(
            action=action, agent="stirling_pdf.tool", result=result,
            risk_level=risk_level, payload=payload or {},
        )
