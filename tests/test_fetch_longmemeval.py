"""Tests para scripts/fetch_longmemeval.py — SIN red (fetcher fake/inyectado).

Cubre: idempotencia por tamaño exacto, --force re-descarga, orquestación
hf_hub->urllib de default_fetcher (con las descargas reales sustituidas), y
paridad de la ruta destino contra scripts/eval_longmemeval.py y
src/atlas/core/self_maintenance/benchmark_gate.py (ambos consumidores reales
del dataset), para que nunca diverjan en silencio.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import fetch_longmemeval as flm

_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Paridad de ruta destino contra los dos consumidores reales.
# ---------------------------------------------------------------------------


def test_default_dest_matches_eval_longmemeval_default() -> None:
    src = (_REPO_ROOT / "scripts" / "eval_longmemeval.py").read_text(encoding="utf-8")
    assert '"data/longmemeval/longmemeval_s_cleaned.json"' in src, (
        "scripts/eval_longmemeval.py:351 cambió su ruta default de dataset — "
        "actualiza fetch_longmemeval.DEFAULT_DEST en paralelo"
    )


def test_default_dest_matches_benchmark_gate_default() -> None:
    src = (
        _REPO_ROOT / "src" / "atlas" / "core" / "self_maintenance" / "benchmark_gate.py"
    ).read_text(encoding="utf-8")
    assert "data/longmemeval/longmemeval_s_cleaned.json" in src, (
        "benchmark_gate.py:73 cambió su ruta default de dataset — "
        "actualiza fetch_longmemeval.DEFAULT_DEST en paralelo"
    )


def test_default_dest_value() -> None:
    assert flm.DEFAULT_DEST == _REPO_ROOT / "data" / "longmemeval" / "longmemeval_s_cleaned.json"


def test_never_targets_m_variant() -> None:
    assert flm.FILENAME == "longmemeval_s_cleaned.json"
    assert "_m_cleaned" not in flm.FILENAME
    assert "_m_cleaned" not in flm.HF_RESOLVE_URL


# ---------------------------------------------------------------------------
# Idempotencia + --force (ensure_dataset, con fetcher fake).
# ---------------------------------------------------------------------------


def _fake_fetcher_factory():
    calls: list[Path] = []

    def _fetcher(dest: Path) -> None:
        calls.append(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x" * flm.EXPECTED_SIZE_BYTES)

    return _fetcher, calls


def test_idempotent_skips_when_size_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(flm, "EXPECTED_SIZE_BYTES", 5)
    dest = tmp_path / "longmemeval_s_cleaned.json"
    dest.write_bytes(b"x" * 5)

    fetcher, calls = _fake_fetcher_factory()
    downloaded = flm.ensure_dataset(dest, fetcher=fetcher)

    assert downloaded is False
    assert calls == []  # el fetcher NUNCA se invoca si ya está completo


def test_redownloads_when_size_mismatches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(flm, "EXPECTED_SIZE_BYTES", 5)
    dest = tmp_path / "longmemeval_s_cleaned.json"
    dest.write_bytes(b"x" * 3)  # tamaño distinto al esperado -> incompleto/corrupto

    fetcher, calls = _fake_fetcher_factory()
    downloaded = flm.ensure_dataset(dest, fetcher=fetcher)

    assert downloaded is True
    assert calls == [dest]


def test_force_redownloads_even_if_size_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(flm, "EXPECTED_SIZE_BYTES", 5)
    dest = tmp_path / "longmemeval_s_cleaned.json"
    dest.write_bytes(b"x" * 5)

    fetcher, calls = _fake_fetcher_factory()
    downloaded = flm.ensure_dataset(dest, force=True, fetcher=fetcher)

    assert downloaded is True
    assert calls == [dest]


def test_ensure_dataset_creates_dest_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(flm, "EXPECTED_SIZE_BYTES", 5)
    dest = tmp_path / "nested" / "longmemeval_s_cleaned.json"
    assert not dest.exists()

    fetcher, calls = _fake_fetcher_factory()
    downloaded = flm.ensure_dataset(dest, fetcher=fetcher)

    assert downloaded is True
    assert calls == [dest]


def test_fetcher_exception_propagates(tmp_path: Path) -> None:
    dest = tmp_path / "longmemeval_s_cleaned.json"

    def _boom(_dest: Path) -> None:
        raise RuntimeError("red caída")

    with pytest.raises(RuntimeError, match="red caída"):
        flm.ensure_dataset(dest, fetcher=_boom)


# ---------------------------------------------------------------------------
# default_fetcher: orquestación hf_hub -> urllib (con ambas ramas sustituidas,
# sin tocar red ni huggingface_hub real).
# ---------------------------------------------------------------------------


def test_default_fetcher_uses_hf_hub_when_it_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "longmemeval_s_cleaned.json"
    hf_calls: list[Path] = []
    urllib_calls: list[Path] = []

    monkeypatch.setattr(flm, "_fetch_via_hf_hub", lambda d: hf_calls.append(d))
    monkeypatch.setattr(flm, "_fetch_via_urllib", lambda d: urllib_calls.append(d))

    flm.default_fetcher(dest)

    assert hf_calls == [dest]
    assert urllib_calls == []


def test_default_fetcher_falls_back_to_urllib_on_hf_hub_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "longmemeval_s_cleaned.json"
    urllib_calls: list[Path] = []

    def _hf_boom(_dest: Path) -> None:
        raise RuntimeError("huggingface_hub no disponible")

    monkeypatch.setattr(flm, "_fetch_via_hf_hub", _hf_boom)
    monkeypatch.setattr(flm, "_fetch_via_urllib", lambda d: urllib_calls.append(d))

    flm.default_fetcher(dest)

    assert urllib_calls == [dest]


def test_fetch_via_urllib_wraps_network_failure_with_clear_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "longmemeval_s_cleaned.json"

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(flm.urllib.request, "urlretrieve", _boom)

    with pytest.raises(RuntimeError, match="fallo de red"):
        flm._fetch_via_urllib(dest)


# ---------------------------------------------------------------------------
# CLI (main): --dest y --force se propagan; fetcher inyectado vía monkeypatch
# del módulo (default_fetcher se resuelve en main() en tiempo de llamada, no
# como valor por defecto ligado en definición).
# ---------------------------------------------------------------------------


def test_main_returns_0_and_skips_when_already_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(flm, "EXPECTED_SIZE_BYTES", 5)
    dest = tmp_path / "longmemeval_s_cleaned.json"
    dest.write_bytes(b"x" * 5)

    calls: list[Path] = []
    monkeypatch.setattr(flm, "default_fetcher", lambda d: calls.append(d))

    exit_code = flm.main(["--dest", str(dest)])

    assert exit_code == 0
    assert calls == []


def test_main_force_invokes_fetcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(flm, "EXPECTED_SIZE_BYTES", 5)
    dest = tmp_path / "longmemeval_s_cleaned.json"
    dest.write_bytes(b"x" * 5)

    calls: list[Path] = []

    def _fetcher(d: Path) -> None:
        calls.append(d)
        d.write_bytes(b"x" * 5)

    monkeypatch.setattr(flm, "default_fetcher", _fetcher)

    exit_code = flm.main(["--dest", str(dest), "--force"])

    assert exit_code == 0
    assert calls == [dest]


def test_main_returns_1_and_prints_error_on_fetcher_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dest = tmp_path / "longmemeval_s_cleaned.json"

    def _boom(_dest: Path) -> None:
        raise RuntimeError("red caída de verdad")

    monkeypatch.setattr(flm, "default_fetcher", _boom)

    exit_code = flm.main(["--dest", str(dest)])

    assert exit_code == 1
    assert "red caída de verdad" in capsys.readouterr().err


def test_hf_fetcher_resolves_cache_symlinks(tmp_path, monkeypatch):
    """Bug real 2026-07-10: hf_hub_download devuelve un SYMLINK relativo a
    blobs/ dentro del cache; hardlinkearlo sin resolve() deja en dest un
    enlace roto y el eval muere con FileNotFoundError."""
    import sys
    import types

    blob = tmp_path / "cache" / "blobs" / "abc123"
    blob.parent.mkdir(parents=True)
    blob.write_text("contenido real", encoding="utf-8")
    snap = tmp_path / "cache" / "snapshots" / "rev"
    snap.mkdir(parents=True)
    link = snap / "longmemeval_s_cleaned.json"
    link.symlink_to(Path("..") / ".." / "blobs" / "abc123")

    fake_hub = types.ModuleType("huggingface_hub")
    fake_hub.hf_hub_download = lambda **kw: str(link)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)

    dest = tmp_path / "data" / "longmemeval_s_cleaned.json"
    flm._fetch_via_hf_hub(dest)
    assert not dest.is_symlink()
    assert dest.read_text(encoding="utf-8") == "contenido real"
