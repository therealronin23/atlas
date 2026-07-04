"""Worker STANDALONE para Crawl4AI — se ejecuta con el intérprete de un venv
AISLADO (``.venv-scraping``), nunca con el venv principal de Atlas.

Por qué aislado: ``crawl4ai`` fija una dependencia dura ``unclecode-litellm==
1.81.13`` que se instala bajo el MISMO nombre de import que nuestro ``litellm``
real (usado por ``InferenceHub`` para el routing multi-proveedor). Instalarlo
en el venv principal sustituiría silenciosamente esa librería crítica por un
fork ajeno y desactualizado. Este script no importa NADA de ``atlas`` — vive
fuera de ``sys.path`` del venv principal a propósito.

Uso: python3 _crawl4ai_worker.py <url> [max_chars]
Salida: una línea JSON por stdout — {success, status_code, markdown, error}.
"""

from __future__ import annotations

import asyncio
import json
import sys


async def _crawl(url: str, max_chars: int) -> dict[str, object]:
    from crawl4ai import AsyncWebCrawler  # noqa: PLC0415 — solo existe en este venv

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        markdown = ""
        if result.markdown:
            markdown = result.markdown.raw_markdown[:max_chars]
        return {
            "success": bool(result.success),
            "status_code": result.status_code,
            "markdown": markdown,
            "error": None if result.success else str(getattr(result, "error_message", "") or ""),
        }


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "status_code": None, "markdown": "", "error": "uso: worker.py <url> [max_chars]"}))
        return 1
    url = sys.argv[1]
    max_chars = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
    try:
        out = asyncio.run(_crawl(url, max_chars))
    except Exception as exc:  # noqa: BLE001 — el resultado se comunica como JSON, no como traceback
        out = {"success": False, "status_code": None, "markdown": "", "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(out))
    return 0 if out["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
