"""Tests mínimos de contracts.py — EventType nuevos (ver ADR de auto-auditoría)."""

from __future__ import annotations

from atlas.core.contracts import EventType


def test_cold_update_batch_ready_event_type_exists() -> None:
    assert EventType.COLD_UPDATE_BATCH_READY.value == "cold_update.batch_ready"
