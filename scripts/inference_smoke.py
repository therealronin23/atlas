#!/usr/bin/env python3
"""
Smoke test del InferenceHub en modo live.

Uso:
    set -a && source .env && set +a
    PYTHONPATH=src python scripts/inference_smoke.py

Pide una respuesta corta a cada proveedor configurado y reporta latencia,
exito/error y un fragmento del texto devuelto. Requiere al menos una key
en entorno (GROQ_API_KEY, OPENROUTER_API_KEY, TOGETHERAI_API_KEY o GEMINI_API_KEY).
"""

from __future__ import annotations

import os
import sys

from atlas.core.inference_hub import (
    DEFAULT_PROVIDERS,
    InferenceHub,
    InferenceLevel,
    InferenceRequest,
)


def main() -> int:
    keys_present = [
        p.api_key_env for p in DEFAULT_PROVIDERS
        if p.api_key_env and os.environ.get(p.api_key_env)
    ]
    if not keys_present:
        print("ERROR: No hay keys de proveedores en el entorno.")
        print("       Exporta al menos GROQ_API_KEY o OPENROUTER_API_KEY.")
        return 2

    print(f"Keys detectadas en entorno: {sorted(set(keys_present))}")
    hub = InferenceHub(mode="live")

    prompt = "Responde solo con dos palabras: 'atlas operativo'."
    print(f"\nPrompt: {prompt!r}\n")

    failures = 0
    for provider in DEFAULT_PROVIDERS:
        if provider.level != InferenceLevel.L1:
            continue
        if not provider.api_key_env or not os.environ.get(provider.api_key_env):
            print(f"  - {provider.name:20s}  SKIP (sin key)")
            continue

        # Hacer un hub aislado por proveedor para ver respuesta individual
        # (no fallback chain en el smoke; queremos diagnostico por separado).
        solo = InferenceHub(providers=[provider], mode="live")
        resp = solo.infer(InferenceRequest(prompt=prompt, level=InferenceLevel.L1, max_tokens=32))

        tag = "OK " if resp.success else "FAIL"
        snippet = (resp.text or resp.error or "").strip().replace("\n", " ")[:80]
        print(f"  - {provider.name:20s}  {tag}  {resp.latency_ms:5d}ms  {snippet}")
        if not resp.success:
            failures += 1

    print()
    if failures > 0:
        print(f"{failures} proveedor(es) fallaron.")
        return 1
    print("Todos los proveedores con key respondieron OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
