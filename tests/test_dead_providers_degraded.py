"""
Degradar proveedores muertos en vez de borrarlos (2026-08-05).

El operador: *"Nvidia glm no funciona porque ese modelo no está... habrá que
degradarla de momento"*.

**Lo medido, que matiza el diagnóstico**: el fallo NO es un 404 "modelo
inexistente". El discovery (consulta de catálogo, cero tokens) los ve
LISTADOS; el smoke los mata con `TimeoutError: hard timeout tras 30.0s`. Es
el patrón de NVIDIA NIM que el propio docstring de `provider_discovery`
advierte: un proveedor puede listar un modelo que su tier no sirve. En efecto
son inservibles; el mecanismo es "listado y sin responder", no "ausente".

**El criterio de retirada no me lo invento**: lo fijó el propio código el
2026-07-23 en `provider_smoke.py` — *"si siguen apareciendo dead en el smoke
diario durante varios días seguidos (no solo un run), ESO sí es evidencia
suficiente"*. Cumplido, contado sobre el log Merkle:

    nvidia_glm             última vez vivo 2026-08-02, muerto 03/04/05
    nvidia_mistral_medium  última vez vivo 2026-08-01, muerto 02/03/04/05

Parpadean (funcionaron entre el 27-jul y el 2-ago), así que se DEGRADAN, no
se borran: `ProviderStatus.DOWN` los saca del pool del hub y basta cambiar una
palabra para devolverlos cuando NVIDIA arregle su lado. Borrarlos habría
roto además los tests que documentan su mapeo de modelo, perdiendo esa historia.

Consecuencia asumida y declarada: `nvidia_glm` era el ÚNICO proveedor de
linaje Zhipu del catálogo, así que el Cónclave pierde el asiento Expansionist
y baja a 4. Es una mejora, no una pérdida: ese asiento devolvía
`reachable=False` tras colgarse 30-120s, y su ausencia es justo lo que hacía
al Cónclave inutilizable. El linaje se puede recuperar cuando haya crédito:
OpenRouter sirve 12 modelos `z-ai/glm-*` (verificado en vivo), ninguno free.
"""

from __future__ import annotations

import pytest

from atlas.core.inference_hub import (
    DEFAULT_PROVIDERS,
    InferenceHub,
    InferenceLevel,
    InferenceRequest,
    Provider,
    ProviderStatus,
)

DEAD = ("nvidia_glm", "nvidia_mistral_medium")


class TestTheyAreDegradedNotDeleted:
    @pytest.mark.parametrize("name", DEAD)
    def test_still_in_the_catalog(self, name: str) -> None:
        """Se conservan: su mapeo de modelo es historia útil y volverlos a
        activar debe costar una palabra, no una arqueología."""
        assert any(p.name == name for p in DEFAULT_PROVIDERS)

    @pytest.mark.parametrize("name", DEAD)
    def test_marked_down(self, name: str) -> None:
        provider = next(p for p in DEFAULT_PROVIDERS if p.name == name)
        assert provider.status is ProviderStatus.DOWN


class TestTheHubSkipsThem:
    def test_a_down_provider_is_never_tried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lo que de verdad se gana: dejar de gastar 30-120s por intento en
        un proveedor que no va a contestar."""
        import litellm

        monkeypatch.setenv("NVIDIA_API_KEY", "test-nvidia")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-or")
        called: list[str] = []

        def spy(**kwargs):  # noqa: ANN003, ANN202
            called.append(kwargs.get("model", ""))
            msg = type("M", (), {"content": "ok"})()
            choice = type("C", (), {"message": msg})()
            return type("R", (), {"choices": [choice], "usage": None})()

        monkeypatch.setattr(litellm, "completion", spy)

        down = Provider(
            name="nvidia_glm", level=InferenceLevel.L2,
            base_url="https://integrate.api.nvidia.com/v1", model_id="glm",
            litellm_model="nvidia_nim/z-ai/glm-5.2", api_key_env="NVIDIA_API_KEY",
            status=ProviderStatus.DOWN,
        )
        alive = Provider(
            name="openrouter_hermes4_70b", level=InferenceLevel.L2,
            base_url="https://openrouter.ai/api/v1", model_id="h4",
            litellm_model="openrouter/h4", api_key_env="OPENROUTER_API_KEY",
        )

        response = InferenceHub([down, alive], mode="live").infer(
            InferenceRequest(prompt="hola", level=InferenceLevel.L2, max_tokens=8)
        )

        assert response.success is True
        assert not any("glm" in m for m in called), (
            f"se intentó un proveedor DOWN: {called}"
        )


class TestTheCouncilDropsTheHangingSeat:
    def test_no_seat_is_built_on_a_down_provider(self) -> None:
        from atlas.core.deliberation_council import build_council_reviewers

        council = build_council_reviewers()
        provs = {r.provider for r in council}

        for name in DEAD:
            assert name not in provs, (
                f"{name} sigue ocupando un asiento pese a estar DOWN: es el que "
                "colgaba la deliberación 30-120s para devolver reachable=False"
            )

    def test_the_council_still_has_enough_lineages_for_a_verdict(self) -> None:
        """Perder el asiento Zhipu no puede dejar al Cónclave por debajo del
        quórum: si lo dejara, la degradación habría cambiado un problema por
        otro peor."""
        from atlas.core.deliberation_council import (
            MIN_REACHABLE_LINEAGES,
            build_council_reviewers,
        )

        council = build_council_reviewers()
        assert len({r.provider for r in council}) >= MIN_REACHABLE_LINEAGES
