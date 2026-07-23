"""Tests de provider_preflight -- go/no-go barato por capas ANTES de una
tanda pesada de iteraciones.

Contexto (plan docs/superpowers/plans/2026-07-23-t5-provider-discovery-plan.md,
T5): pedido original del operador -- "antes de iterar a lo loco diga si el
proveedor está disponible". Dos capas, de más barata a más cara:

- Capa 0 (cero red): lee ``provider_smoke_state.json`` ya escrito por
  ``ProviderChainSmoke`` (T5.1, ya en producción). Si hay >=1 proveedor del
  nivel pedido con outcome="ok" y checked_at <24h -> ok=True SIN llamar a
  discovery en absoluto.
- Capa 1 (red barata, cero tokens): solo si Capa 0 no resuelve o se pide
  ``require_live_probe=True`` -- usa ``discover_available_models`` como ping.

``discover`` es inyectable a propósito: ningún test de este fichero toca
red real ni gasta una llamada de inferencia.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from atlas.core.inference_hub import InferenceLevel, Provider
from atlas.core.provider_discovery import DiscoveryResult
from atlas.core.provider_preflight import PreflightVerdict, provider_preflight


def _provider(name: str, level: InferenceLevel) -> Provider:
    return Provider(
        name=name,
        level=level,
        base_url=f"https://{name}.example",
        model_id=f"{name}-model",
        litellm_model=f"{name}/model",
        api_key_env=f"{name.upper()}_API_KEY",
    )


def _l1_providers() -> list[Provider]:
    return [
        _provider("prov_a", InferenceLevel.L1),
        _provider("prov_b", InferenceLevel.L1),
    ]


def _mixed_level_providers() -> list[Provider]:
    return [
        _provider("prov_a", InferenceLevel.L1),
        _provider("prov_b", InferenceLevel.L1),
        _provider("prov_other_level", InferenceLevel.L2),
    ]


def _write_smoke_state(
    root: Path, *, results: list[dict[str, Any]], last_run_date: str | None = None
) -> None:
    state_dir = root / "workspace" / "self_build"
    state_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "last_run_date": last_run_date or datetime.now(timezone.utc).date().isoformat(),
        "last_results": results,
    }
    (state_dir / "provider_smoke_state.json").write_text(json.dumps(state), encoding="utf-8")


def _raising_discover(provider: Provider) -> DiscoveryResult:
    raise AssertionError(
        f"discover_available_models no debe llamarse en Capa 0 (provider={provider.name})"
    )


# --- Capa 0: estado de smoke fresco resuelve sin tocar discovery ---------


def test_capa0_fresh_ok_smoke_resolves_without_calling_discover(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    _write_smoke_state(
        tmp_path,
        results=[
            {"provider_name": "prov_a", "level": "L1", "outcome": "ok", "checked_at": now},
            {"provider_name": "prov_b", "level": "L1", "outcome": "failed", "checked_at": now},
        ],
    )

    verdict = provider_preflight(
        InferenceLevel.L1,
        root=tmp_path,
        providers=_l1_providers(),
        discover=_raising_discover,
    )

    assert verdict.ok is True
    assert verdict.live_providers == ["prov_a"]
    assert verdict.dead_providers == ["prov_b"]
    assert isinstance(verdict, PreflightVerdict)
    assert verdict.level == "L1"


def test_capa0_ignores_ok_entries_of_other_levels(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    _write_smoke_state(
        tmp_path,
        results=[
            {"provider_name": "prov_a", "level": "L1", "outcome": "ok", "checked_at": now},
            {
                "provider_name": "prov_other_level",
                "level": "L2",
                "outcome": "ok",
                "checked_at": now,
            },
        ],
    )

    verdict = provider_preflight(
        InferenceLevel.L1,
        root=tmp_path,
        providers=_mixed_level_providers(),
        discover=_raising_discover,
    )

    assert verdict.ok is True
    assert verdict.live_providers == ["prov_a"]
    assert "prov_other_level" not in verdict.dead_providers
    assert "prov_other_level" not in verdict.live_providers


# --- Capa 0 no resuelve -> cae a Capa 1 ----------------------------------


def test_capa0_stale_smoke_falls_through_to_capa1(tmp_path: Path) -> None:
    stale = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    _write_smoke_state(
        tmp_path,
        results=[
            {"provider_name": "prov_a", "level": "L1", "outcome": "ok", "checked_at": stale},
        ],
        last_run_date="2020-01-01",
    )
    calls: list[str] = []

    def fake_discover(provider: Provider) -> DiscoveryResult:
        calls.append(provider.name)
        return DiscoveryResult(provider_name=provider.name, outcome="ok", model_ids=["m"])

    verdict = provider_preflight(
        InferenceLevel.L1, root=tmp_path, providers=_l1_providers(), discover=fake_discover
    )

    assert verdict.ok is True
    assert set(calls) == {"prov_a", "prov_b"}


def test_capa0_missing_state_file_falls_through_to_capa1(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_discover(provider: Provider) -> DiscoveryResult:
        calls.append(provider.name)
        return DiscoveryResult(provider_name=provider.name, outcome="ok", model_ids=["m"])

    verdict = provider_preflight(
        InferenceLevel.L1, root=tmp_path, providers=_l1_providers(), discover=fake_discover
    )

    assert verdict.ok is True
    assert len(calls) == 2


def test_require_live_probe_true_forces_capa1_even_with_fresh_smoke(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    _write_smoke_state(
        tmp_path,
        results=[
            {"provider_name": "prov_a", "level": "L1", "outcome": "ok", "checked_at": now},
        ],
    )
    calls: list[str] = []

    def fake_discover(provider: Provider) -> DiscoveryResult:
        calls.append(provider.name)
        return DiscoveryResult(provider_name=provider.name, outcome="ok", model_ids=["m"])

    verdict = provider_preflight(
        InferenceLevel.L1,
        root=tmp_path,
        providers=_l1_providers(),
        require_live_probe=True,
        discover=fake_discover,
    )

    assert verdict.ok is True
    assert set(calls) == {"prov_a", "prov_b"}


# --- Capa 1: 200/401/timeout se traducen a vivo/muerto -------------------


def test_capa1_auth_failed_counts_as_dead(tmp_path: Path) -> None:
    def fake_discover(provider: Provider) -> DiscoveryResult:
        return DiscoveryResult(provider_name=provider.name, outcome="auth_failed", reason="HTTP 401")

    verdict = provider_preflight(
        InferenceLevel.L1, root=tmp_path, providers=_l1_providers(), discover=fake_discover
    )

    assert verdict.ok is False
    assert set(verdict.dead_providers) == {"prov_a", "prov_b"}
    assert verdict.live_providers == []


def test_capa1_unreachable_timeout_counts_as_dead(tmp_path: Path) -> None:
    def fake_discover(provider: Provider) -> DiscoveryResult:
        return DiscoveryResult(provider_name=provider.name, outcome="unreachable", reason="timed out")

    verdict = provider_preflight(
        InferenceLevel.L1, root=tmp_path, providers=_l1_providers(), discover=fake_discover
    )

    assert verdict.ok is False
    assert set(verdict.dead_providers) == {"prov_a", "prov_b"}


def test_capa1_one_alive_is_enough_for_ok(tmp_path: Path) -> None:
    def fake_discover(provider: Provider) -> DiscoveryResult:
        outcome = "ok" if provider.name == "prov_b" else "unreachable"
        return DiscoveryResult(provider_name=provider.name, outcome=outcome)

    verdict = provider_preflight(
        InferenceLevel.L1, root=tmp_path, providers=_l1_providers(), discover=fake_discover
    )

    assert verdict.ok is True
    assert verdict.live_providers == ["prov_b"]
    assert verdict.dead_providers == ["prov_a"]


# --- Nivel sin ningún proveedor vivo tras ambas capas --------------------


def test_no_provider_alive_after_both_layers_is_no_go_with_reason(tmp_path: Path) -> None:
    def fake_discover(provider: Provider) -> DiscoveryResult:
        return DiscoveryResult(provider_name=provider.name, outcome="unreachable", reason="down")

    verdict = provider_preflight(
        InferenceLevel.L1, root=tmp_path, providers=_l1_providers(), discover=fake_discover
    )

    assert verdict.ok is False
    assert verdict.reason  # razón legible, no vacía
    assert set(verdict.dead_providers) == {"prov_a", "prov_b"}


def test_level_with_no_providers_configured_is_no_go(tmp_path: Path) -> None:
    verdict = provider_preflight(
        InferenceLevel.L_DET,
        root=tmp_path,
        providers=_l1_providers(),
        discover=_raising_discover,
    )

    assert verdict.ok is False
    assert verdict.live_providers == []
    assert verdict.dead_providers == []
    assert "L-det" in verdict.reason or "L_DET" in verdict.reason or verdict.level in verdict.reason


# --- live_providers/dead_providers reflejan solo el nivel evaluado -------


def test_verdict_only_reflects_providers_of_requested_level(tmp_path: Path) -> None:
    def fake_discover(provider: Provider) -> DiscoveryResult:
        return DiscoveryResult(provider_name=provider.name, outcome="unreachable", reason="down")

    verdict = provider_preflight(
        InferenceLevel.L1,
        root=tmp_path,
        providers=_mixed_level_providers(),
        discover=fake_discover,
    )

    assert "prov_other_level" not in verdict.dead_providers
    assert "prov_other_level" not in verdict.live_providers
    assert set(verdict.dead_providers) == {"prov_a", "prov_b"}


def test_corrupt_smoke_state_falls_through_to_capa1_without_raising(tmp_path: Path) -> None:
    state_dir = tmp_path / "workspace" / "self_build"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "provider_smoke_state.json").write_text("not json{{{", encoding="utf-8")

    def fake_discover(provider: Provider) -> DiscoveryResult:
        return DiscoveryResult(provider_name=provider.name, outcome="ok")

    verdict = provider_preflight(
        InferenceLevel.L1, root=tmp_path, providers=_l1_providers(), discover=fake_discover
    )

    assert verdict.ok is True


def test_preflight_verdict_to_dict() -> None:
    verdict = PreflightVerdict(
        ok=True, level="L1", reason="ok", live_providers=["a"], dead_providers=["b"]
    )
    d = verdict.to_dict()
    assert d == {
        "ok": True,
        "level": "L1",
        "reason": "ok",
        "live_providers": ["a"],
        "dead_providers": ["b"],
    }
