"""
ADR-025 — ValidationRunner: pytest + mypy in an isolated directory.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path


@dataclass
class ValidationReport:
    passed: bool
    pytest_exit: int
    mypy_exit: int
    pytest_summary: str = ""
    mypy_summary: str = ""
    duration_s: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "pytest_exit": self.pytest_exit,
            "mypy_exit": self.mypy_exit,
            "pytest_summary": self.pytest_summary,
            "mypy_summary": self.mypy_summary,
            "duration_s": self.duration_s,
            "errors": list(self.errors),
        }


class ValidationRunner:
    """Runs quality gates without shell=True."""

    def __init__(
        self,
        project_root: Path,
        *,
        python: str | None = None,
        skip_browser: bool = True,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self._root = project_root.resolve()
        self._python = python or sys.executable
        self._skip_browser = skip_browser
        self._extra_env = extra_env

    def run(self, timeout_s: int = 600) -> ValidationReport:
        import time

        # Guard anti-recursión (2026-06-12): un test que filtre validación real
        # lanza la suite completa DENTRO de la suite → recursión infinita (la
        # suite hija contiene el test que filtra). Fallar ruidoso convierte una
        # fuga silenciosa de aislamiento en un error inmediato y localizable.
        if "PYTEST_CURRENT_TEST" in os.environ:
            raise RuntimeError(
                "ValidationRunner.run() invocado desde dentro de pytest: un test "
                "ha filtrado validación real (suite recursiva). Mockea el runner "
                "o inyecta un scout/proposer falso."
            )

        start = time.monotonic()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self._root / "src")
        env.setdefault("ATLAS_MEMORY_VECTOR", "0")
        env.update(self._extra_env or {})

        pytest_cmd = [
            self._python,
            "-m",
            "pytest",
            "tests/",
            "-q",
            "--tb=line",
        ]
        if self._skip_browser:
            pytest_cmd.extend(["-m", "not computer_use"])

        py_result = subprocess.run(
            pytest_cmd,
            cwd=self._root,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        mypy_cmd = [
            self._python,
            "-m",
            "mypy",
            "src/atlas/",
        ]
        my_env = {**env, "MYPYPATH": str(self._root / "src")}
        my_result = subprocess.run(
            mypy_cmd,
            cwd=self._root,
            env=my_env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        duration = time.monotonic() - start
        passed = py_result.returncode == 0 and my_result.returncode == 0
        errors: list[str] = []
        if py_result.returncode != 0:
            errors.append("pytest failed")
        if my_result.returncode != 0:
            errors.append("mypy failed")
        tail_py = (py_result.stdout or "") + (py_result.stderr or "")
        tail_my = (my_result.stdout or "") + (my_result.stderr or "")
        return ValidationReport(
            passed=passed,
            pytest_exit=py_result.returncode,
            mypy_exit=my_result.returncode,
            pytest_summary=tail_py.strip()[-2000:],
            mypy_summary=tail_my.strip()[-2000:],
            duration_s=round(duration, 2),
            errors=errors,
        )
