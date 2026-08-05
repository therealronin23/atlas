"""
Contrato entre `InferenceHub` y `scripts/token-tracker.sh` (2026-08-05).

Apagón real encontrado al convocar el Cónclave: devolvió UNKNOWN por
"diversidad insuficiente, 1 proveedor alcanzable de 3". No era ni la
credencial ni un modelo retirado. El hub llamaba al tracker con el **nombre
de entrada** del proveedor (`groq_llama_70b`) mientras el tracker presupuesta
por **familia de vendor** (`groq`), así que el gate contestaba
`unknown provider` → exit 64 → fail-closed.

Alcance medido del apagón: los 7 proveedores L1/L2 del catálogo caídos; los
3 que funcionaban eran L0, que se saltan el gate por diseño. Es decir, Atlas
llevaba sin NINGUNA inferencia L1/L2 y el síntoma visible era un Cónclave que
opinaba con un asiento.

Por qué no lo cazó nadie: `test_token_tracker.py` prueba el script (correcto)
y los tests del hub mockean litellm por debajo del gate. Nadie probaba la
FRONTERA. Esa es la que se prueba aquí, y a propósito contra el script real:
un test que se invente la lista de familias volvería a mentir en cuanto
alguien edite el script.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.core.inference_hub import (
    DEFAULT_PROVIDERS,
    InferenceLevel,
    budget_family,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TRACKER = REPO_ROOT / "scripts" / "token-tracker.sh"


def _tracker_check(identifier: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(TRACKER), "check", identifier],
        capture_output=True, text=True, timeout=30, cwd=REPO_ROOT,
    )


GATED = [p for p in DEFAULT_PROVIDERS
         if p.level not in (InferenceLevel.L0, InferenceLevel.L_DET)]


def test_the_catalog_actually_has_gated_providers() -> None:
    """Si un día todo cayera a L0, los tests de abajo pasarían vacíos y
    volverían a no probar nada."""
    assert GATED, "ningún proveedor pasa por el gate: el resto de tests sería vacío"


@pytest.mark.parametrize("provider", GATED, ids=lambda p: p.name)
def test_every_gated_provider_is_known_to_the_budget_tracker(provider) -> None:  # noqa: ANN001
    """El invariante que se rompió: lo que el hub pasa, el tracker lo conoce.
    Contra el script REAL, no contra una lista copiada aquí."""
    result = _tracker_check(budget_family(provider.name))
    assert result.returncode != 64, (
        f"{provider.name} -> familia {budget_family(provider.name)!r}: "
        f"el tracker no la conoce ({result.stderr.strip()}). "
        "El hub la daría por fail-closed y ese proveedor quedaría muerto."
    )


class TestBudgetFamily:
    def test_strips_the_model_suffix(self) -> None:
        assert budget_family("groq_llama_70b") == "groq"
        assert budget_family("openrouter_mistral_large") == "openrouter"
        assert budget_family("nvidia_glm") == "nvidia"

    def test_a_bare_vendor_name_is_its_own_family(self) -> None:
        assert budget_family("groq") == "groq"

    def test_empty_name_does_not_crash(self) -> None:
        assert budget_family("") == ""


class TestTheGateCannotHangForever:
    """2026-08-05, auditoría de fronteras — el gate corre en el camino
    caliente de CADA inferencia L1/L2 y es fail-closed. Sin `timeout=`, un
    tracker colgado (lock de fichero, disco parado, un `read` que nunca
    vuelve) no falla: cuelga a Atlas entero, en silencio y para siempre.
    Es el mismo patrón que ya mordió dos veces hoy — NVIDIA colgándose 120 s
    sin dar error, y el Cónclave agotando 10 minutos.

    El tope se fija con margen absurdo a propósito: el script real tarda
    12 ms de mediana y 13 ms el peor de 10 ejecuciones. 10 s es ~770x eso.
    No está para recortar nada, está para que exista un final."""

    def test_a_hanging_tracker_fails_closed_instead_of_hanging(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess as sp

        from atlas.core.inference_hub import (
            InferenceHub,
            InferenceRequest,
            Provider,
        )

        monkeypatch.setenv("GROQ_API_KEY", "test-groq")
        seen: dict[str, object] = {}

        def fake_run(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            seen.update(kwargs)
            raise sp.TimeoutExpired(cmd="token-tracker.sh", timeout=10)

        monkeypatch.setattr(sp, "run", fake_run)

        provider = Provider(
            name="groq_llama_70b", level=InferenceLevel.L1,
            base_url="https://api.groq.com", model_id="m",
            litellm_model="groq/m", api_key_env="GROQ_API_KEY",
        )
        hub = InferenceHub(providers=[provider], mode="live")
        response = hub.infer(InferenceRequest(prompt="hola", level=InferenceLevel.L1))

        assert response.success is False
        assert "presupuesto" in (response.error or "")

    def test_the_gate_actually_passes_a_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sin este, el test de arriba pasaría en vacío: `TimeoutExpired` sólo
        puede ocurrir si alguien pidió un timeout. Es la lección del test de
        gpgsign — comprobar el mecanismo, no la ausencia de síntoma."""
        import subprocess as sp

        from atlas.core.inference_hub import (
            InferenceHub,
            InferenceRequest,
            Provider,
        )

        monkeypatch.setenv("GROQ_API_KEY", "test-groq")
        captured: dict[str, object] = {}
        real_run = sp.run

        def spy_run(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            if args and isinstance(args[0], list) and "token-tracker.sh" in str(args[0]):
                captured.update(kwargs)
            return real_run(*args, **kwargs)

        monkeypatch.setattr(sp, "run", spy_run)

        provider = Provider(
            name="groq_llama_70b", level=InferenceLevel.L1,
            base_url="https://api.groq.com", model_id="m",
            litellm_model="groq/m", api_key_env="GROQ_API_KEY",
        )
        InferenceHub(providers=[provider], mode="live").infer(
            InferenceRequest(prompt="hola", level=InferenceLevel.L1)
        )

        assert "timeout" in captured, "el gate llama al tracker sin timeout: un cuelgue es eterno"
        assert isinstance(captured["timeout"], (int, float))
        assert captured["timeout"] > 0


class TestTrackerPathIsNotCwdDependent:
    """El call site usaba la ruta relativa `scripts/token-tracker.sh`. Hoy
    funciona porque el WorkingDirectory del servicio ES la raíz del repo —
    pero cualquier caller desde otro cwd caía en el `except Exception` y
    también fallaba cerrado, con un mensaje que no menciona el cwd. Es la
    misma clase de fallo latente, sólo que sin disparar todavía."""

    def test_the_hub_resolves_the_tracker_absolutely(self) -> None:
        from atlas.core.inference_hub import token_tracker_path

        path = token_tracker_path()
        assert path.is_absolute()
        assert path.exists(), f"{path} no existe"
