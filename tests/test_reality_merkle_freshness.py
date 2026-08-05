"""
`reality` medía la integridad del Merkle pero no su vitalidad (2026-08-05).

Pregunta del operador: *"el merkle funciona o no? hace mucho que no escucho
saber de él"*. Sí funciona: `verify_chain()` OK sobre 24.404 entradas. Y
`reality` SÍ lo reportaba —dentro de `workspace.merkle`, no como sección
propia— con `status`, `record_count` y `reason`.

Lo que NO medía es si la cadena SIGUE VIVA. `verify_chain` sólo dice que los
hashes encadenan; una cadena que dejó de escribirse hace tres semanas encadena
perfectamente y sale `status: ok`. Es exactamente la ceguera que dejó al
daemon muerto 23 h sin que nadie lo notara: integridad e historia medidas,
presente no.

Umbral MEDIDO, no inventado: sobre las últimas 6000 entradas (desde el
2026-08-02) el hueco mediano entre escrituras es ~0 min, el p99 son 0,4 h y el
mayor hueco real observado son 1,7 h. Se toma 6 h — 3,5× el peor caso real:
suficiente para no gritar en una tarde tranquila, suficiente para enterarse el
mismo día de que el escritor murió.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from atlas.core.reality import MERKLE_STALE_AFTER_HOURS, _workspace_state
from atlas.logging.merkle_logger import MerkleLogger


def _workspace_with_log(tmp_path: Path) -> Path:
    audit = tmp_path / "memory" / "audit"
    audit.mkdir(parents=True)
    merkle = MerkleLogger(log_dir=audit)
    for i in range(3):
        merkle.log(action=f"probe.{i}", agent="test", result="ok", risk_level="safe")
    return tmp_path


class TestFreshness:
    def test_a_log_written_now_is_ok_and_reports_its_age(self, tmp_path: Path) -> None:
        state = _workspace_state(_workspace_with_log(tmp_path))["merkle"]

        assert state["status"] == "ok"
        assert state["last_entry_at"] is not None
        assert state["age_hours"] is not None
        assert state["age_hours"] < 1
        assert state["stale"] is False

    def test_an_intact_but_abandoned_chain_is_stale_not_ok(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        """El caso que importa: los hashes encadenan, pero nadie escribe.

        Se simula el PASO DEL TIEMPO, no se toca el log: reescribir un
        timestamp rompería el hash (el Merkle lo cubre) y saldría `corrupt`,
        que es otro caso distinto — lo comprobé al escribir esto."""
        workspace = _workspace_with_log(tmp_path)

        import atlas.core.reality as reality_mod

        real_datetime = reality_mod.datetime
        shift = timedelta(hours=MERKLE_STALE_AFTER_HOURS + 1)

        class _Later(real_datetime):  # type: ignore[misc,valid-type]
            @classmethod
            def now(cls, tz=None):  # noqa: ANN001, ANN206
                return real_datetime.now(tz) + shift

        monkeypatch.setattr(reality_mod, "datetime", _Later)

        state = _workspace_state(workspace)["merkle"]

        assert state["stale"] is True
        assert state["status"] == "stale"
        assert state["age_hours"] > MERKLE_STALE_AFTER_HOURS

    def test_a_corrupt_chain_still_wins_over_staleness(self, tmp_path: Path) -> None:
        """Una cadena rota es peor noticia que una parada: no se enmascara."""
        import json
        workspace = _workspace_with_log(tmp_path)
        log = workspace / "memory" / "audit" / "merkle.jsonl"
        lines = log.read_text().splitlines()
        record = json.loads(lines[1])
        record["action"] = "manipulado"
        lines[1] = json.dumps(record, ensure_ascii=False)
        log.write_text("\n".join(lines) + "\n")

        state = _workspace_state(workspace)["merkle"]

        assert state["status"] == "corrupt"

    def test_no_log_yet_is_unknown_not_stale(self, tmp_path: Path) -> None:
        """No medible != roto, la distinción que sostiene todo el informe."""
        state = _workspace_state(tmp_path)["merkle"]

        assert state["status"] == "unknown"
        assert state["stale"] is None
        assert state["age_hours"] is None


class TestHeadlineDegrades:
    def test_a_stale_merkle_degrades_the_headline(self) -> None:
        """Si el rastro de auditoría dejó de escribirse, el operador tiene que
        enterarse sin leer el JSON entero — igual que con el daemon caído.
        `_overall_status` ya degrada por `corrupt`; parar de escribir es la
        otra mitad del mismo problema y no estaba cubierta."""
        from atlas.core.reality import _overall_status

        report = {"workspace": {"merkle": {"status": "stale", "stale": True}}}
        assert _overall_status(report) == "degraded"

    def test_a_healthy_merkle_does_not_degrade_it(self) -> None:
        from atlas.core.reality import _overall_status

        report = {"workspace": {"merkle": {"status": "ok", "stale": False}}}
        assert _overall_status(report) != "degraded"
