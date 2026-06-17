"""Tests para detect_evasion() y su integración en ShadowRouter (Tarea C2)."""

from __future__ import annotations

import pytest

from atlas.security.shadow_model import (
    ClassifierMetrics,
    RoutingDecision,
    SessionStateStore,
    ShadowMode,
    ShadowRouter,
    detect_evasion,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _metrics(
    embedding_distance: float = 1.0,
    confidence: float = 0.3,
    baseline_distance: float = 0.5,
) -> ClassifierMetrics:
    return ClassifierMetrics(
        embedding_distance=embedding_distance,
        confidence=confidence,
        baseline_distance=baseline_distance,
    )


# ---------------------------------------------------------------------------
# detect_evasion — función pura
# ---------------------------------------------------------------------------


def test_evasion_both_conditions_true() -> None:
    """Ambas condiciones cumplen → True."""
    # embedding_distance (1.0) > baseline (0.5) * (1 + 0.3) = 0.65 → True
    # confidence (0.3) < 0.5 → True
    assert detect_evasion(_metrics(1.0, 0.3, 0.5)) is True


def test_evasion_only_high_distance() -> None:
    """Solo distancia elevada, confianza OK → False (lógica AND)."""
    # embedding_distance elevada pero confidence >= 0.5
    assert detect_evasion(_metrics(1.0, 0.9, 0.5)) is False


def test_evasion_only_low_confidence() -> None:
    """Solo confianza baja, distancia normal → False."""
    # embedding_distance (0.5) == baseline (0.5) * 1.3 = 0.65 → NOT elevated
    assert detect_evasion(_metrics(0.5, 0.1, 0.5)) is False


def test_evasion_exact_boundary_distance() -> None:
    """Distancia exactamente en el límite (no estrictamente mayor) → False."""
    # embedding_distance == baseline * (1 + threshold) → NOT strictly greater
    baseline = 0.5
    threshold = 0.3
    exact = baseline * (1 + threshold)  # 0.65
    assert detect_evasion(_metrics(exact, 0.1, baseline), embedding_threshold=threshold) is False


def test_evasion_just_above_boundary() -> None:
    """Distancia justo sobre el límite → True (si confianza también baja)."""
    baseline = 0.5
    threshold = 0.3
    just_above = baseline * (1 + threshold) + 1e-9
    assert detect_evasion(_metrics(just_above, 0.1, baseline), embedding_threshold=threshold) is True


def test_evasion_custom_thresholds() -> None:
    """Parámetros custom: embedding_threshold=0.1, confidence_min=0.8."""
    m = _metrics(embedding_distance=1.1, confidence=0.7, baseline_distance=1.0)
    # distance: 1.1 > 1.0 * 1.1 = 1.1 → NOT strictly greater → False
    assert detect_evasion(m, embedding_threshold=0.1, confidence_min=0.8) is False


def test_evasion_custom_thresholds_true() -> None:
    m = _metrics(embedding_distance=1.11, confidence=0.7, baseline_distance=1.0)
    # distance: 1.11 > 1.1 → True; confidence: 0.7 < 0.8 → True
    assert detect_evasion(m, embedding_threshold=0.1, confidence_min=0.8) is True


def test_evasion_zero_baseline() -> None:
    """Baseline cero: cualquier distancia positiva es elevada."""
    m = _metrics(embedding_distance=0.01, confidence=0.1, baseline_distance=0.0)
    # 0.01 > 0 * 1.3 = 0 → True; confidence < 0.5 → True
    assert detect_evasion(m) is True


def test_evasion_deterministic() -> None:
    """Llamadas repetidas con mismas entradas → mismo resultado (pura)."""
    m = _metrics(1.0, 0.3, 0.5)
    results = [detect_evasion(m) for _ in range(100)]
    assert all(r == results[0] for r in results)


def test_evasion_no_side_effects() -> None:
    """detect_evasion no modifica la instancia de métricas."""
    m = _metrics(1.0, 0.3, 0.5)
    _ = detect_evasion(m)
    assert m.embedding_distance == 1.0
    assert m.confidence == 0.3
    assert m.baseline_distance == 0.5


# ---------------------------------------------------------------------------
# Integración con ShadowRouter.route()
# ---------------------------------------------------------------------------


def test_route_without_metrics_unchanged() -> None:
    """route() sin metrics mantiene comportamiento original (retrocompatible)."""
    store = SessionStateStore()
    router = ShadowRouter(store)
    dec = router.route("s1", 0.3)  # below threshold → NORMAL
    assert dec.mode == ShadowMode.NORMAL
    assert "[evasion-detected]" not in dec.cause


def test_route_evasion_forces_active() -> None:
    """Con métricas de evasión, route() fuerza ACTIVE aunque confidence sea baja."""
    store = SessionStateStore()
    router = ShadowRouter(store, threshold_passive=0.65, threshold_active=0.88)
    # confidence=0.3 → normalmente NORMAL, pero evasión detectada → ACTIVE
    m = _metrics(embedding_distance=1.0, confidence=0.3, baseline_distance=0.5)
    dec = router.route("s2", 0.3, metrics=m)
    assert dec.mode == ShadowMode.ACTIVE
    assert "[evasion-detected]" in dec.cause


def test_route_no_evasion_no_override() -> None:
    """Métricas sin evasión: no hay override del modo."""
    store = SessionStateStore()
    router = ShadowRouter(store, threshold_passive=0.65, threshold_active=0.88)
    # Confidence baja pero distancia NO elevada
    m = _metrics(embedding_distance=0.5, confidence=0.1, baseline_distance=0.5)
    dec = router.route("s3", 0.3, metrics=m)
    assert dec.mode == ShadowMode.NORMAL
    assert "[evasion-detected]" not in dec.cause


def test_route_evasion_state_persisted_as_active() -> None:
    """Estado en store queda como ACTIVE tras override por evasión."""
    store = SessionStateStore()
    router = ShadowRouter(store)
    m = _metrics(1.0, 0.3, 0.5)
    router.route("s4", 0.3, metrics=m)
    state = store.get("s4")
    assert state is not None
    assert state.mode == ShadowMode.ACTIVE


# ---------------------------------------------------------------------------
# detect_evasion — ramas adicionales
# ---------------------------------------------------------------------------


def test_evasion_true_high_distance_low_confidence() -> None:
    """Rama True: embedding_distance alto Y confidence bajo → evasión."""
    m = _metrics(embedding_distance=2.0, confidence=0.1, baseline_distance=0.5)
    assert detect_evasion(m) is True


def test_evasion_false_both_metrics_normal() -> None:
    """Rama False: ambas métricas normales → no evasión."""
    m = _metrics(embedding_distance=0.4, confidence=0.9, baseline_distance=0.5)
    assert detect_evasion(m) is False


def test_evasion_false_only_embedding_high() -> None:
    """Rama False: solo embedding alto (confidence normal) → no evasión (AND)."""
    m = _metrics(embedding_distance=2.0, confidence=0.9, baseline_distance=0.5)
    assert detect_evasion(m) is False


def test_evasion_false_only_confidence_low() -> None:
    """Rama False: solo confidence bajo (embedding normal) → no evasión (AND)."""
    m = _metrics(embedding_distance=0.4, confidence=0.1, baseline_distance=0.5)
    assert detect_evasion(m) is False


def test_evasion_default_thresholds_embedding_0_3_confidence_0_5() -> None:
    """Umbrales por defecto: embedding_threshold=0.3, confidence_min=0.5 respetados."""
    baseline = 1.0
    # Just at boundary: NOT elevated
    m_boundary = _metrics(
        embedding_distance=baseline * (1 + 0.3),
        confidence=0.4,
        baseline_distance=baseline,
    )
    assert detect_evasion(m_boundary) is False

    # Just above boundary: elevated, confidence < 0.5 → True
    m_above = _metrics(
        embedding_distance=baseline * (1 + 0.3) + 1e-9,
        confidence=0.4,
        baseline_distance=baseline,
    )
    assert detect_evasion(m_above) is True


# ---------------------------------------------------------------------------
# route() integración adicional
# ---------------------------------------------------------------------------


def test_route_terminated_raises_before_evaluating_evasion() -> None:
    """TERMINATED → RuntimeError incluso si se pasan métricas de evasión."""
    store = SessionStateStore()
    router = ShadowRouter(store)
    router.terminate("term-sess")
    m = _metrics(1.0, 0.1, 0.5)
    with pytest.raises(RuntimeError):
        router.route("term-sess", 0.9, metrics=m)


def test_route_without_metrics_no_evasion_annotation() -> None:
    """Sin metrics, route() nunca añade [evasion-detected] a la causa."""
    store = SessionStateStore()
    router = ShadowRouter(store)
    dec = router.route("no-evasion", 0.7)
    assert "[evasion-detected]" not in dec.cause


def test_route_evasion_cause_contains_suffix() -> None:
    """Evasión detectada → causa termina con ' [evasion-detected]'."""
    store = SessionStateStore()
    router = ShadowRouter(store)
    m = _metrics(1.0, 0.1, 0.5)
    dec = router.route("evasion-cause", 0.3, metrics=m)
    assert dec.cause.endswith("[evasion-detected]")


def test_route_normal_confidence_evasion_forces_active() -> None:
    """Aunque confidence=0.3 (NORMAL), evasión detectada fuerza ACTIVE."""
    store = SessionStateStore()
    router = ShadowRouter(store, threshold_passive=0.65, threshold_active=0.88)
    m = _metrics(embedding_distance=1.0, confidence=0.3, baseline_distance=0.5)
    dec = router.route("evasion-override", 0.3, metrics=m)
    assert dec.mode == ShadowMode.ACTIVE


def test_route_passive_no_evasion_stays_passive() -> None:
    """Métricas que no detectan evasión: PASSIVE queda como PASSIVE."""
    store = SessionStateStore()
    router = ShadowRouter(store, threshold_passive=0.65, threshold_active=0.88)
    # confidence=0.7 → PASSIVE; embedding no elevado → no evasión
    m = _metrics(embedding_distance=0.4, confidence=0.7, baseline_distance=0.5)
    dec = router.route("passive-ok", 0.7, metrics=m)
    assert dec.mode == ShadowMode.PASSIVE
    assert "[evasion-detected]" not in dec.cause


def test_route_evasion_logged_in_state_as_active() -> None:
    """Estado persistido como ACTIVE cuando evasión es detectada."""
    store = SessionStateStore()
    router = ShadowRouter(store)
    m = _metrics(1.0, 0.1, 0.5)
    router.route("evasion-persist", 0.3, metrics=m)
    state = store.get("evasion-persist")
    assert state is not None
    assert state.mode == ShadowMode.ACTIVE


def test_stub_backend_returns_bytes_no_real_deps() -> None:
    """_stub_backend() funciona sin deps externos; devuelve bytes."""
    from atlas.security.shadow_model import _stub_backend, ShadowModel

    result = _stub_backend("system", "user")
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_stub_backend_via_shadow_model_no_sleep() -> None:
    """ShadowModel con stub_backend y sleep=noop no bloquea ni lanza."""
    from atlas.security.shadow_model import ShadowModel

    model = ShadowModel()
    resp = model.respond(ShadowMode.PASSIVE, "hello", sleep=lambda _: None)
    assert isinstance(resp, bytes)


def test_confidence_only_vs_evasion_aware_same_signal() -> None:
    """Misma confidence=0.3 pero evasión detecta antes: route() con métricas → ACTIVE, sin métricas → NORMAL."""
    store_a = SessionStateStore()
    store_b = SessionStateStore()
    router_a = ShadowRouter(store_a, threshold_passive=0.65, threshold_active=0.88)
    router_b = ShadowRouter(store_b, threshold_passive=0.65, threshold_active=0.88)

    m_evasion = _metrics(1.0, 0.3, 0.5)

    dec_plain = router_a.route("plain", 0.3)          # sin métricas
    dec_evasion = router_b.route("evasion", 0.3, metrics=m_evasion)

    assert dec_plain.mode == ShadowMode.NORMAL         # confianza sola → NORMAL
    assert dec_evasion.mode == ShadowMode.ACTIVE       # evasión detectada → ACTIVE
