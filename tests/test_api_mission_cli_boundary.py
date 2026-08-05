"""
Frontera HTTP -> CLI de las misiones (auditoría de fronteras, 2026-08-05).

`POST /missions/{id}/approve|reject` no ejecutan nada por sí mismos: lanzan
`python -m atlas.interfaces.cli update ...` como subproceso. Ese subproceso
puede aplicar un ColdUpdate real, que corre una suite entera dentro de un
worktree aislado — minutos, no segundos.

El defecto: se lanzaban **sin `timeout=`**. Un `apply` que se atasca (una
suite colgada, un `git` esperando `index.lock`, un jail que no vuelve) no
falla nunca: retiene el worker de FastAPI para siempre, y el operador ve el
navegador girando sin ninguna información. Es exactamente la forma de los
tres defectos encontrados hoy — no código incompleto, sino una frontera cuyo
contrato nadie comprobaba.

El tope se elige por lo que el proceso hace de verdad (ColdUpdate = validar
en worktree), no por lo que tarda una llamada normal. Al agotarse, la
respuesta es 504 con el motivo, que es información honesta: "no sé si
terminó", distinto de "falló".
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atlas.api.server import MISSION_CLI_TIMEOUT_S, create_app
from atlas.events.store import OsEventStore

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            store=OsEventStore(tmp_path / "events.jsonl"),
            fixtures_dir=REPO / "fixtures",
            business_core_path=tmp_path / "business_core.json",
        ),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )


def _hanging_run(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
    """Lo que produce un subproceso colgado cuando SÍ se pidió un tope."""
    raise subprocess.TimeoutExpired(cmd=args[0] if args else "cli", timeout=1)


class TestApproveBoundary:
    def test_a_hanging_cli_returns_504_instead_of_holding_the_worker(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _hanging_run)

        response = client.post("/missions/mission-abc/approve")

        assert response.status_code == 504
        assert "mission-abc" in response.json()["detail"]

    def test_it_actually_passes_a_timeout(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sin esto el test de arriba pasaría en vacío: `TimeoutExpired` sólo
        ocurre si alguien pidió un tope."""
        captured: list[dict] = []
        real_run = subprocess.run

        def spy(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            captured.append(dict(kwargs))
            raise subprocess.TimeoutExpired(cmd="cli", timeout=1)

        monkeypatch.setattr(subprocess, "run", spy)
        client.post("/missions/mission-abc/approve")

        assert captured, "el endpoint no llegó a lanzar el subproceso"
        assert captured[0].get("timeout") == MISSION_CLI_TIMEOUT_S


class TestRejectBoundary:
    def test_a_hanging_cli_returns_504(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _hanging_run)

        response = client.post("/missions/mission-xyz/reject")

        assert response.status_code == 504
        assert "mission-xyz" in response.json()["detail"]


class TestTheTimeoutIsGenerousEnoughForRealWork:
    def test_it_leaves_room_for_a_coldupdate_validation(self) -> None:
        """Un tope tan corto que aborte trabajo legítimo es peor que no
        tenerlo: convierte un ColdUpdate normal en un 504 y empuja a
        quitarlo. Validar en worktree son minutos."""
        assert MISSION_CLI_TIMEOUT_S >= 600
