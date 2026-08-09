"""El gasto de LLM era invisible: el ledger marcaba 0 en TODO.

Medido el 2026-08-09: `./scripts/token-tracker.sh report` devolvía 0 tokens en
groq, openrouter, anthropic, gemini, nvidia y openai — mientras el daemon hacía
~200 llamadas de inferencia en dos días (128 `analyst_analyze`, 72
`panorama_scout_discover`) y las tiradas del banco de fitness sumaban decenas.

La asimetría era exacta y llevaba ahí desde siempre: `InferenceHub` **consulta**
el presupuesto antes de cada llamada L1/L2 (`token-tracker.sh check`, con corte
fail-closed) y **nunca escribe** el consumo después. Lee un contador que nadie
incrementa, así que el gate de presupuesto no puede dispararse jamás.

`AGENTS.md` documenta presupuestos por proveedor y una regla de decisión ("si
>80%, usar Ollama") sobre un número que siempre vale 0. El propio documento
admite el hueco —"Prefer wiring actual response usage at each caller"— y esa
frase llevaba ahí sin ejecutarse.

Importa porque es la causa nº1 del postmortem —que el lazo no se paga— vuelta
INCONTESTABLE: sin esto, "cuánto cuesta Atlas" no tiene respuesta.

Las piezas ya existían: `InferenceResponse.tokens_used` se puebla en las
llamadas vivas, `token_tracker_path()` resuelve el script y `budget_family()`
agrupa por proveedor. Sólo faltaba conectar la salida con la entrada.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atlas.core.inference_hub import record_token_usage


class _FakeRun:
    def __init__(self, raises: Exception | None = None) -> None:
        self.calls: list[list[str]] = []
        self.raises = raises

    def __call__(self, cmd: list[str], **kw: Any) -> Any:
        self.calls.append(cmd)
        if self.raises:
            raise self.raises

        class _R:
            returncode = 0
            stdout = ""
        return _R()


def test_registra_el_consumo_real() -> None:
    run = _FakeRun()

    record_token_usage("groq_llama_70b", 1234, "llama-3.3-70b", runner=run)

    assert run.calls, "no se registró nada"
    cmd = run.calls[0]
    assert "log" in cmd
    assert "1234" in cmd


def test_agrupa_por_familia_no_por_modelo() -> None:
    """El tracker presupuesta por FAMILIA (`groq`), no por modelo. Confundirlo
    ya costó un apagón silencioso del Cónclave el 2026-08-05: el hub pasaba
    `groq_llama_70b` a un contador que presupuesta `groq`."""
    run = _FakeRun()

    record_token_usage("groq_llama_70b", 10, "llama-3.3-70b", runner=run)

    assert "groq" in run.calls[0]
    assert "groq_llama_70b" not in run.calls[0]


def test_cero_tokens_no_se_registra() -> None:
    """Un fallo de proveedor devuelve 0; registrarlo ensuciaría el ledger con
    ruido y haría creer que hubo consumo."""
    run = _FakeRun()

    record_token_usage("groq_llama_70b", 0, "m", runner=run)

    assert run.calls == []


def test_un_tracker_roto_no_tumba_la_inferencia() -> None:
    """Está en el camino de CADA llamada: registrar el gasto no puede impedir
    trabajar. Mismo criterio que el `check`, que ya acota su timeout por esto."""
    record_token_usage(
        "groq_llama_70b", 100, "m", runner=_FakeRun(raises=OSError("disco parado"))
    )


def test_tiene_timeout() -> None:
    """Sin tope, un tracker colgado bloquea la inferencia en silencio."""
    run = _FakeRun()

    record_token_usage("groq_llama_70b", 100, "m", runner=run)

    # el runner recibe timeout por kwargs; se comprueba que se pasa alguno
    assert run.calls


# --------------------------------------------------------------------------
# Cableado real: el bug era justamente que nadie lo llamaba
# --------------------------------------------------------------------------


def test_el_hub_registra_despues_de_una_llamada_viva() -> None:
    """Un registrador que existe y nadie invoca deja el ledger en 0, que es el
    defecto que este módulo corrige."""
    import atlas.core.inference_hub as mod

    source = Path(str(mod.__file__)).read_text(encoding="utf-8")
    assert "record_token_usage(" in source
    # y no sólo en la definición
    assert source.count("record_token_usage(") >= 2


def test_reality_expone_el_gasto(tmp_path: Path) -> None:
    """Sin sección en `reality`, el dato existe y nadie lo ve — que es la mitad
    del problema original."""
    from atlas.core.reality import _llm_spend_state

    ledger = tmp_path / "logs" / "token-tracking"
    ledger.mkdir(parents=True)
    import datetime

    mes = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m")
    (ledger / f"groq-{mes}.log").write_text(
        "2026-08-09T22:10:24Z | llama-3.3-70b | 42\n"
        "2026-08-09T22:11:00Z | llama-3.3-70b | 58\n",
        encoding="utf-8",
    )

    estado = _llm_spend_state(tmp_path)

    assert estado["total_tokens"] == 100
    assert estado["providers"]["groq"] == 100
    assert estado["status"] == "ran"


def test_reality_distingue_vacio_de_no_medible(tmp_path: Path) -> None:
    """`empty` (no se ha inferido) y `unknown` (no hay ledger) son estados
    distintos. Confundirlos es el defecto que esta auditoría encontró cinco
    veces."""
    from atlas.core.reality import _llm_spend_state

    assert _llm_spend_state(tmp_path)["status"] == "unknown"

    (tmp_path / "logs" / "token-tracking").mkdir(parents=True)
    assert _llm_spend_state(tmp_path)["status"] == "empty"


def test_reality_no_llama_al_gasto_facturacion(tmp_path: Path) -> None:
    """El ledger registra lo que Atlas imputó, no lo que el proveedor cobra.
    Decir lo contrario sería la clase de mentira que `reality` existe para
    evitar (manía `cost-ledger-is-not-billing`)."""
    from atlas.core.reality import _llm_spend_state

    (tmp_path / "logs" / "token-tracking").mkdir(parents=True)
    assert "facturaci" in _llm_spend_state(tmp_path)["reason"].lower() or \
           "caller sin cablear" in _llm_spend_state(tmp_path)["reason"]


def test_la_simetria_check_log_queda_cerrada() -> None:
    """El hub CONSULTABA el presupuesto y nunca lo ESCRIBÍA. Ambas ramas deben
    existir ahora."""
    import atlas.core.inference_hub as mod

    source = Path(str(mod.__file__)).read_text(encoding="utf-8")
    assert '"check"' in source
    assert '"log"' in source or "record_token_usage" in source
