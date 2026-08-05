"""El vigilante sabe ver "muerto"; no sabía ver "vivo e inútil".

`service_probe` pregunta `systemctl is-active`. Una unidad en crash-loop
responde `active` la mayor parte del ciclo, así que el 2026-08-02 el daemon
se reinició 4.872 veces en 23 h y esa sonda habría dicho "activo" en cada
pasada. El vigilante se escribió el 2026-07-31 precisamente por una caída de
23 h; dos días después ocurrió la misma duración de indisponibilidad efectiva
bajo un estado que no sabe mirar.

systemd ya publica la señal: `NRestarts`. Esta sonda la lee.

Se respeta la regla del operador ("sólo lo grave, nada de ruido"): un reinicio
suelto —un `systemctl restart` a mano, un despliegue— no es una emergencia.
Sólo lo es un ritmo de reinicios sostenido.
"""

from __future__ import annotations

import subprocess

import pytest

from atlas.runtime.watchdog import Check, flapping_probe


class _FakeRun:
    """Sustituye `subprocess.run` devolviendo lo que systemd devolvería."""

    def __init__(self, stdout: str = "", returncode: int = 0, raises: Exception | None = None):
        self.stdout = stdout
        self.returncode = returncode
        self.raises = raises
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(cmd)
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, "")


def _patch(monkeypatch: pytest.MonkeyPatch, fake: _FakeRun) -> None:
    monkeypatch.setattr("atlas.runtime.watchdog.subprocess.run", fake)


def test_sin_reinicios_esta_bien(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeRun("NRestarts=0\n"))

    check = flapping_probe()

    assert check.ok is True
    assert "0" in check.detail


def test_un_reinicio_suelto_no_alarma(monkeypatch: pytest.MonkeyPatch) -> None:
    """"Sólo lo grave": un restart manual no puede despertar a nadie."""
    _patch(monkeypatch, _FakeRun("NRestarts=2\n"))

    assert flapping_probe(threshold=5).ok is True


def test_crash_loop_dispara(monkeypatch: pytest.MonkeyPatch) -> None:
    """El caso del 02-ago: 4.872 reinicios y `is-active` diciendo 'active'."""
    _patch(monkeypatch, _FakeRun("NRestarts=4872\n"))

    check = flapping_probe(threshold=5)

    assert check.ok is False
    assert "4872" in check.detail


def test_justo_en_el_umbral_dispara(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeRun("NRestarts=5\n"))

    assert flapping_probe(threshold=5).ok is False


def test_systemctl_ausente_no_es_fallo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regla del módulo: no poder medir es `ok=None`, nunca `ok=False`.
    Confundir "no sé" con "roto" enseña al operador a ignorar el canal."""
    _patch(monkeypatch, _FakeRun(raises=FileNotFoundError("systemctl")))

    check = flapping_probe()

    assert check.ok is None


def test_salida_ininteligible_no_es_fallo(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeRun("NRestarts=\n"))

    assert flapping_probe().ok is None

    _patch(monkeypatch, _FakeRun("basura\n"))

    assert flapping_probe().ok is None


def test_consulta_la_unidad_correcta(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRun("NRestarts=0\n")
    _patch(monkeypatch, fake)

    flapping_probe(unit="otra.service")

    assert fake.calls[0][:3] == ["systemctl", "--user", "show"]
    assert "otra.service" in fake.calls[0]
    assert "NRestarts" in " ".join(fake.calls[0])


def test_esta_en_las_sondas_por_defecto() -> None:
    """Una sonda que existe pero nadie corre es exactamente el bug que
    este módulo documenta."""
    from atlas.runtime.watchdog import default_probes

    nombres = []
    for probe in default_probes():
        try:
            nombres.append(probe().name)
        except Exception:  # noqa: BLE001 — aquí sólo interesa el inventario
            continue
    assert any("reinicio" in n or "flapping" in n for n in nombres)


def test_devuelve_un_check() -> None:
    assert isinstance(flapping_probe(unit="inexistente.service"), Check)
