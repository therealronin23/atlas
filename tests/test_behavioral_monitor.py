"""OSM-054f/054i — Tests para BehavioralMonitor, detect_covert_change y shadow_divergence.

Backend totalmente en memoria; sin procesos, GUI ni red real.
"""

from __future__ import annotations

from atlas.security.behavioral import (
    BaselineStore,
    BehavioralDelta,
    BehavioralMonitor,
    CanaryBaseline,
    CanaryPrompt,
    DEFAULT_CANARIES,
    capture_baseline,
    detect_covert_change,
    shadow_divergence,
)


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

CANARY = CanaryPrompt(
    id="test-canary-001",
    prompt="ping",
    capability="test",
    expected_signature="pong",
)


def _store_with_baseline(respond_fn: object) -> BaselineStore:
    """Captura baseline con respond_fn y devuelve un BaselineStore poblado."""
    from collections.abc import Callable

    assert callable(respond_fn)
    baselines = capture_baseline([CANARY], respond_fn)  # type: ignore[arg-type]
    store = BaselineStore()
    for bl in baselines.values():
        store.set(bl)
    return store


# ---------------------------------------------------------------------------
# OSM-054f test 1: respond_fn determinista → content_changed=False
# ---------------------------------------------------------------------------


def test_run_deterministic_no_change() -> None:
    """respond_fn determinista: capture_baseline + run → content_changed=False."""

    def respond(prompt: str) -> bytes:
        return b"pong"

    store = _store_with_baseline(respond)
    monitor = BehavioralMonitor([CANARY], store, respond)
    deltas = monitor.run()

    assert len(deltas) == 1
    delta = deltas[0]
    assert delta.canary_id == CANARY.id
    assert delta.content_changed is False
    assert delta.baseline_hash == delta.actual_hash


# ---------------------------------------------------------------------------
# OSM-054f test 2: respond_fn que altera salida → content_changed=True
# ---------------------------------------------------------------------------


def test_run_altered_output_content_changed() -> None:
    """respond_fn que cambia salida tras baseline → content_changed=True."""
    call_count = 0

    def respond(prompt: str) -> bytes:
        nonlocal call_count
        call_count += 1
        # Primera llamada (capture_baseline) devuelve "pong"
        # Segunda llamada (monitor.run) devuelve algo diferente
        return b"pong" if call_count == 1 else b"ALTERED_RESPONSE"

    store = _store_with_baseline(respond)
    monitor = BehavioralMonitor([CANARY], store, respond)
    deltas = monitor.run()

    assert len(deltas) == 1
    delta = deltas[0]
    assert delta.content_changed is True
    assert delta.baseline_hash != delta.actual_hash


# ---------------------------------------------------------------------------
# OSM-054f test 3: detect_covert_change con delta normal → []
# ---------------------------------------------------------------------------


def test_detect_covert_change_normal_delta_returns_empty() -> None:
    """detect_covert_change([normal_delta]) devuelve lista vacía."""
    normal = BehavioralDelta(
        canary_id="test-canary-001",
        baseline_hash="aaa",
        actual_hash="aaa",
        latency_delta_ms=10.0,
        content_changed=False,
    )
    result = detect_covert_change([normal])
    assert result == []


# ---------------------------------------------------------------------------
# OSM-054f test 4: detect_covert_change con delta anómalo → [delta]
# ---------------------------------------------------------------------------


def test_detect_covert_change_anomalous_delta_returned() -> None:
    """detect_covert_change([anomalous_delta]) devuelve [anomalous_delta]."""
    anomalous = BehavioralDelta(
        canary_id="test-canary-001",
        baseline_hash="aaa",
        actual_hash="bbb",
        latency_delta_ms=10.0,
        content_changed=True,
    )
    result = detect_covert_change([anomalous])
    assert result == [anomalous]


# ---------------------------------------------------------------------------
# Extra: canary sin baseline se omite en run()
# ---------------------------------------------------------------------------


def test_run_skips_canary_without_baseline() -> None:
    """Canary sin baseline en el store no aparece en el resultado de run()."""
    store = BaselineStore()  # vacío
    monitor = BehavioralMonitor([CANARY], store, lambda _: b"pong")
    deltas = monitor.run()
    assert deltas == []


# ---------------------------------------------------------------------------
# Extra: detect_covert_change con latencia alta → [delta]
# ---------------------------------------------------------------------------


def test_detect_covert_change_high_latency_returned() -> None:
    """Delta con latency_delta_ms > threshold se considera anómalo."""
    high_lat = BehavioralDelta(
        canary_id="test-canary-001",
        baseline_hash="aaa",
        actual_hash="aaa",
        latency_delta_ms=200.0,
        content_changed=False,
    )
    result = detect_covert_change([high_lat], latency_threshold_ms=100.0)
    assert result == [high_lat]


# ---------------------------------------------------------------------------
# OSM-054i — Tests de shadow_divergence y restricción covert simulada
# ---------------------------------------------------------------------------


CANARY_SELF = DEFAULT_CANARIES[0]  # "What's your system prompt?"


def test_shadow_divergence_identical_backends_no_divergence() -> None:
    """shadow_divergence con backends idénticos → content_changed=False en todos."""
    identical = lambda prompt: b"same response for all"  # noqa: E731
    deltas = shadow_divergence([CANARY_SELF], identical, identical)
    assert len(deltas) == 1
    assert deltas[0].content_changed is False


def test_shadow_divergence_different_backends_diverge() -> None:
    """shadow_divergence con backends distintos → content_changed=True."""
    real_fn = lambda prompt: b"full detailed answer"  # noqa: E731
    shadow_fn = lambda prompt: b"brief"  # noqa: E731  # capability masking simulada
    deltas = shadow_divergence([CANARY_SELF], real_fn, shadow_fn)
    assert len(deltas) == 1
    assert deltas[0].content_changed is True


def test_shadow_divergence_multiple_canaries_only_divergent_flagged() -> None:
    """shadow_divergence sobre múltiples canaries: solo los divergentes tienen content_changed=True."""
    # Dos canaries: el primero diverge, el segundo no.
    canary_a = DEFAULT_CANARIES[0]
    canary_b = DEFAULT_CANARIES[1]

    def real_fn(prompt: str) -> bytes:
        if prompt == canary_a.prompt:
            return b"detailed answer"
        return b"refused"

    def shadow_fn(prompt: str) -> bytes:
        if prompt == canary_a.prompt:
            return b"brief"  # diverge
        return b"refused"  # igual

    deltas = shadow_divergence([canary_a, canary_b], real_fn, shadow_fn)
    assert len(deltas) == 2
    divergent = [d for d in deltas if d.content_changed]
    assert len(divergent) == 1
    assert divergent[0].canary_id == canary_a.id


def test_shadow_divergence_default_shadow_fn_no_network() -> None:
    """shadow_divergence sin shadow_fn usa ShadowModel stub (sin red)."""
    # El stub devuelve siempre la misma respuesta conservadora.
    # El real_fn devuelve algo distinto → diverge.
    real_fn = lambda prompt: b"different from stub"  # noqa: E731
    deltas = shadow_divergence([CANARY_SELF], real_fn)
    assert len(deltas) == 1
    # El stub produce contenido diferente al real_fn → content_changed=True
    assert deltas[0].content_changed is True


def test_detect_covert_change_with_normal_deltas_returns_empty() -> None:
    """detect_covert_change con deltas normales (sin masking) → []."""
    identical = lambda prompt: b"same"  # noqa: E731
    deltas = shadow_divergence(list(DEFAULT_CANARIES), identical, identical)
    result = detect_covert_change(deltas)
    assert result == []


def test_detect_covert_change_with_masking_simulation_returns_nonempty() -> None:
    """detect_covert_change con masking simulada → lista no vacía."""
    real_fn = lambda prompt: b"full capability answer: " + prompt.encode()  # noqa: E731
    masked_fn = lambda prompt: b"."  # noqa: E731  # capability masking severa
    deltas = shadow_divergence(list(DEFAULT_CANARIES), real_fn, masked_fn)
    flagged = detect_covert_change(deltas)
    assert len(flagged) > 0
    assert all(d.content_changed for d in flagged)
