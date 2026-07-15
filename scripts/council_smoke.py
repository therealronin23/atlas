"""
Smoke en vivo del Cónclave: convoca el trío REAL (Gemini/Kimi/Mistral) sobre una
decisión de ejemplo y reporta el veredicto + qué proveedor respondió o falló.

Requiere secretos vivos (GEMINI_API_KEY + NVIDIA_API_KEY[_2]) y red. NO es un test
de la suite (patrón `inference_smoke.py`). Uso:

    PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- \
      .venv/bin/python scripts/council_smoke.py
"""

from __future__ import annotations

from atlas.core.deliberation_council import build_trio_reviewers, convene_for_decision
from atlas.router.cascade import Difficulty


def main() -> None:
    trio = build_trio_reviewers()
    print(f"trío ensamblado: {[r.provider for r in trio]}")
    ev = convene_for_decision(
        "¿UUID o BIGINT para los user IDs de un SaaS con 10M de usuarios?",
        context="decisión irreversible, afecta al producto durante años",
        difficulty=Difficulty.HARD,
        risk="high",
        reviewers=trio,
    )
    assert ev is not None, "el gating debió convocar (HARD + high)"
    print(f"\nVEREDICTO: {ev.verdict.name}")
    if ev.reason:
        print(f"razón: {ev.reason}")
    print("\nvoces (desacuerdo crudo, ANTES de síntesis):")
    for c in ev.checks:
        estado = "PASS" if c.passed else "OBJETA"
        print(f"  - {c.name}: {estado} | {c.detail[:160]}")


if __name__ == "__main__":
    main()
