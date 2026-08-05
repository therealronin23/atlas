"""
Frontera ColdUpdate -> `patch(1)` (auditoría de fronteras, 2026-08-05).

`_apply_patch` intenta `git apply` y, si falla, cae a `patch -p1 -i`.
`_rollback_patch` usa `patch -p1 -R -i`. Los dos se lanzaban sin `timeout=` y
**sin cerrar stdin**.

Comportamiento REPRODUCIDO, no supuesto (GNU patch, este sistema): con stdin
conectado a un pipe abierto que nunca envía nada, `patch` se cuelga
indefinidamente —tanto si el fichero destino no existe como si el contexto no
casa— porque pregunta interactivamente por el fichero a parchear. Con
stdin=/dev/null aborta al instante (rc=1).

Por qué es grave justo aquí y no en cualquier sitio: `patch` es el FALLBACK de
`git apply`, así que sólo se ejecuta cuando el parche ya dio problemas — el
peor caso es también el único caso en el que corre. Y el proceso que lo hereda
puede tener stdin de un pipe: `POST /missions/{id}/approve` lanza
`atlas update apply` como subproceso, y stdin se hereda del servidor.

Dos capas, no una: `stdin=DEVNULL` es el arreglo estructural (patch recibe EOF
y aborta enseguida); el `timeout` es el cinturón por si algún día se invoca
otra herramienta que ignore el EOF.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.core.cold_update_manager import PATCH_TIMEOUT_S, ColdUpdateManager
from atlas.logging.merkle_logger import MerkleLogger

# Path bajo la allowlist de ColdUpdate (`src/`) para que pase el intake y el
# fallo ocurra DONDE se está probando: en `patch`, no en la validación previa.
# Primera versión de este test usaba `no_existe.txt` y "pasaba" con una
# PatchIntakeError que también casa con "Patch no aplicable" -- verde por la
# razón equivocada.
BAD_PATCH = """--- a/src/atlas/no_existe.py
+++ b/src/atlas/no_existe.py
@@ -1 +1 @@
-viejo
+nuevo
"""


@pytest.fixture()
def target(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    (work / "real.txt").write_text("contenido\n")
    return work


@pytest.fixture()
def bad_patch(tmp_path: Path) -> Path:
    path = tmp_path / "bad.patch"
    path.write_text(BAD_PATCH)
    return path


def _manager(tmp_path: Path) -> ColdUpdateManager:
    return ColdUpdateManager(
        tmp_path, MerkleLogger(log_dir=tmp_path / "audit"),
        store_dir=tmp_path / "store",
    )


def _spy(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []
    real = subprocess.run

    def spy_run(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        argv = args[0] if args else kwargs.get("args")
        if isinstance(argv, list) and argv and argv[0] == "patch":
            calls.append(dict(kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy_run)
    return calls


class TestApplyPatchBoundary:
    def test_patch_fallback_gets_a_closed_stdin_and_a_timeout(
        self, tmp_path: Path, target: Path, bad_patch: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls = _spy(monkeypatch)
        manager = _manager(tmp_path)

        with pytest.raises(RuntimeError, match="Patch no aplicable"):
            manager._apply_patch(target, bad_patch)

        assert calls, "el fallback a `patch` no llegó a ejecutarse"
        assert calls[0].get("stdin") is subprocess.DEVNULL, (
            "sin stdin cerrado, `patch` pregunta por el fichero y se cuelga"
        )
        assert calls[0].get("timeout") == PATCH_TIMEOUT_S


class TestRollbackPatchBoundary:
    def test_rollback_gets_a_closed_stdin_and_a_timeout(
        self, tmp_path: Path, target: Path, bad_patch: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls = _spy(monkeypatch)
        manager = _manager(tmp_path)

        manager._rollback_patch(target, bad_patch)  # no lanza: es best-effort

        assert calls, "el rollback no llegó a ejecutar `patch`"
        assert calls[0].get("stdin") is subprocess.DEVNULL
        assert calls[0].get("timeout") == PATCH_TIMEOUT_S


class TestItReallyDoesNotHang:
    def test_a_bad_patch_returns_promptly_instead_of_waiting_on_stdin(
        self, tmp_path: Path, target: Path, bad_patch: Path
    ) -> None:
        """Extremo a extremo con `patch` de verdad: sin el arreglo esto
        depende de qué haya en stdin; con él, termina siempre."""
        import time

        manager = _manager(tmp_path)
        started = time.perf_counter()
        with pytest.raises(RuntimeError, match="Patch no aplicable"):
            manager._apply_patch(target, bad_patch)
        assert time.perf_counter() - started < 10
