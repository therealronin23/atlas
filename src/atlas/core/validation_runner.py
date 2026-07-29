"""ADR-025 candidate validation inside a read-only OS jail.

Candidate tests import and execute code from a proposed patch.  They therefore
must not run with the host user's filesystem, network, or inherited
environment.  ``BwrapJail`` is the containment boundary; this runner only
supplies the bounded candidate tree and the interpreter runtime it needs.
"""

from __future__ import annotations

import os
import site
import sys
import sysconfig
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from atlas.security.bwrap_jail import BwrapJail


class _JailResultLike(Protocol):
    """The bounded result surface used by :class:`ValidationRunner`."""

    returncode: int
    stdout: str
    stderr: str


class _CommandJailLike(Protocol):
    """Minimal Bwrap seam retained solely for deterministic tests."""

    CPU_TIME_LIMIT_S: int
    RAM_LIMIT_BYTES: int

    def run_command(
        self,
        command: Sequence[str],
        *,
        working_dir: Path,
        working_dir_writable: bool = False,
        read_only_paths: Sequence[Path] = (),
        timeout_s: int | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> _JailResultLike: ...


_JAIL_ATLAS_HOME = "/tmp/atlas-validation-home"
_JAIL_HOME = "/tmp/atlas-validation-user"
_MAX_CANDIDATE_CPU_TIME_S = 120
# Kuzu 0.11 reserves a large *virtual* mmap window even for Atlas's small
# deterministic test stores.  The observed current suite needs just over
# 12.5 GiB of address space; 14 GiB is a fixed compatibility ceiling, not a
# claim that the jail has an equivalent physical-memory cgroup.
_MAX_CANDIDATE_RAM_BYTES = 14 * 1024 * 1024 * 1024
_PROTECTED_JAIL_ENV = frozenset(
    {
        "ATLAS_HOME",
        "HOME",
        "PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONSAFEPATH",
        "PYTEST_ADDOPTS",
        "PYTHONDONTWRITEBYTECODE",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "MYPYPATH",
        "MYPY_CACHE_DIR",
        "XDG_CACHE_HOME",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_COUNT",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_TERMINAL_PROMPT",
        "GIT_OPTIONAL_LOCKS",
        "ATLAS_CANDIDATE_VALIDATION",
    }
)


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
    """Run candidate quality gates in Bwrap, never directly on the host.

    The candidate worktree is mounted read-only and Bwrap supplies a new
    network-less namespace and ``/tmp``.  The runner deliberately does not
    copy ``os.environ``: only deterministic validation controls and explicitly
    supplied, non-protected variables reach the child.  ``ATLAS_HOME`` is
    always remapped to the jail's ephemeral ``/tmp`` so a caller cannot expose
    an ambient host workspace through this seam.
    """

    def __init__(
        self,
        project_root: Path,
        *,
        python: str | None = None,
        skip_browser: bool = True,
        extra_env: dict[str, str] | None = None,
        jail_factory: Callable[[], _CommandJailLike] | None = None,
    ) -> None:
        self._root = project_root.resolve()
        self._python = python or sys.executable
        self._skip_browser = skip_browser
        self._extra_env = dict(extra_env or {})
        self._jail_factory = jail_factory or BwrapJail

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
        runtime_paths = self._runtime_read_only_paths()
        env = self._jail_environment(runtime_paths)
        # Constructor lazy: an unavailable Bwrap implementation raises before
        # any candidate command is executed.  There is intentionally no host
        # subprocess fallback.
        jail = self._jail_factory()
        # A full pytest suite is legitimately larger than BwrapJail's default
        # 30-second one-command budget.  Keep it bounded independently from
        # the wall timeout so an untrusted candidate cannot claim arbitrary
        # CPU simply by supplying a larger timeout.
        jail.CPU_TIME_LIMIT_S = min(timeout_s, _MAX_CANDIDATE_CPU_TIME_S)
        # Kuzu's deterministic test store reserves a large virtual mmap range.
        # The generic 512 MiB command limit rejects it before candidate tests
        # run.  This remains a fixed validation-only address-space cap, not an
        # inherited host limit or a caller-controlled allocation.
        jail.RAM_LIMIT_BYTES = _MAX_CANDIDATE_RAM_BYTES

        pytest_cmd = [
            self._python,
            "-m",
            "pytest",
            "tests/",
            "-q",
            "--tb=line",
            # The candidate worktree is read-only.  Disabling pytest's cache
            # avoids a hidden write attempt to .pytest_cache.
            "-p",
            "no:cacheprovider",
        ]
        if self._skip_browser:
            pytest_cmd.extend(["-m", "not computer_use"])

        py_result = jail.run_command(
            pytest_cmd,
            working_dir=self._root,
            working_dir_writable=False,
            read_only_paths=runtime_paths,
            timeout_s=timeout_s,
            extra_env=env,
        )
        mypy_cmd = [
            self._python,
            "-m",
            "mypy",
            "src/atlas/",
        ]
        my_result = jail.run_command(
            mypy_cmd,
            working_dir=self._root,
            working_dir_writable=False,
            read_only_paths=runtime_paths,
            timeout_s=timeout_s,
            extra_env=env,
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

    def _runtime_read_only_paths(self) -> tuple[Path, ...]:
        """Return only the current interpreter runtime outside ``/usr``.

        ``BwrapJail`` already mounts ``/usr`` read-only.  Virtualenv/user-site
        installations live elsewhere, so they are mounted explicitly without
        mounting ``$HOME`` or a broad host directory.  The candidate root is
        already the jail working directory and is intentionally omitted.
        """

        candidates: list[Path] = [Path(sys.prefix), Path(sys.base_prefix)]
        try:
            candidates.append(Path(site.getusersitepackages()))
            candidates.extend(Path(item) for item in site.getsitepackages())
        except AttributeError:
            # Embedded Python implementations need not expose getsitepackages.
            pass
        for key in ("purelib", "platlib", "stdlib", "platstdlib"):
            value = sysconfig.get_paths().get(key)
            if value:
                candidates.append(Path(value))
        executable = Path(self._python).expanduser()
        if executable.is_absolute():
            candidates.append(executable)
        candidates.extend(self._linked_worktree_git_paths())

        resolved: list[Path] = []
        for candidate in candidates:
            try:
                path = candidate.resolve(strict=True)
            except OSError:
                continue
            if self._provided_by_base_jail(path) or self._provided_by_candidate(path):
                continue
            if path not in resolved:
                resolved.append(path)

        # A parent runtime mount already exposes descendants.  Avoid overlapping
        # bwrap binds, which are both unnecessary and platform-sensitive.
        minimal: list[Path] = []
        for path in sorted(resolved, key=lambda item: (len(item.parts), str(item))):
            if not any(existing == path or existing in path.parents for existing in minimal):
                minimal.append(path)
        return tuple(minimal)

    def _linked_worktree_git_paths(self) -> tuple[Path, ...]:
        """Expose only the Git metadata a linked candidate worktree needs.

        A Git worktree has a ``.git`` pointer whose target and common Git
        directory usually live outside the worktree mount.  Without these
        exact read-only inputs, an otherwise portable candidate test that
        invokes ``git rev-parse`` fails before exercising Atlas.  We accept
        only Git's normal ``.git/worktrees/<name>`` relation and deliberately
        omit the common ``config`` file: the child also receives a no-system,
        no-global Git environment.
        """

        pointer = self._root / ".git"
        if not pointer.is_file():
            return ()
        try:
            line = pointer.read_text(encoding="utf-8").strip()
        except OSError:
            return ()
        prefix = "gitdir: "
        if not line.startswith(prefix):
            return ()
        raw_git_dir = line[len(prefix):]
        if not raw_git_dir or "\x00" in raw_git_dir:
            return ()
        try:
            git_dir_value = Path(raw_git_dir)
            git_dir = (
                git_dir_value if git_dir_value.is_absolute() else self._root / git_dir_value
            ).resolve(strict=True)
            commondir_value = (git_dir / "commondir").read_text(encoding="utf-8").strip()
            if not commondir_value or "\x00" in commondir_value:
                return ()
            common_value = Path(commondir_value)
            common = (
                common_value if common_value.is_absolute() else git_dir / common_value
            ).resolve(strict=True)
        except OSError:
            return ()

        worktrees_dir = common / "worktrees"
        if (
            common.name != ".git"
            or not common.is_dir()
            or git_dir.parent != worktrees_dir
            or not worktrees_dir.is_dir()
        ):
            return ()

        paths = [git_dir]
        for name in ("objects", "refs", "info", "logs", "packed-refs", "shallow"):
            candidate = common / name
            if candidate.exists():
                paths.append(candidate)
        return tuple(paths)

    def _jail_environment(self, runtime_paths: Sequence[Path]) -> dict[str, str]:
        """Build the explicit child environment without inherited host state."""

        import_paths = [str(self._root / "src")]
        for path in runtime_paths:
            # Runtime prefixes can contain binaries/config; only package roots
            # belong on Python's import path.  Existing /usr sites are visible
            # through Bwrap's base mount and do not need to be repeated.
            if "site-packages" in path.parts or "dist-packages" in path.parts:
                import_paths.append(str(path))

        env = {
            "PYTHONPATH": os.pathsep.join(import_paths),
            "MYPYPATH": str(self._root / "src"),
            "MYPY_CACHE_DIR": "/tmp/atlas-mypy-cache",
            "XDG_CACHE_HOME": "/tmp/atlas-cache",
            # Override Bwrap's generic /tmp HOME with a distinct ephemeral
            # path. This keeps $HOME off the host while preserving test
            # portability checks that verify a home path is not a mount.
            "HOME": _JAIL_HOME,
            "ATLAS_HOME": _JAIL_ATLAS_HOME,
            "ATLAS_MEMORY_VECTOR": "0",
            # Tests running in this intentionally networkless jail use an
            # injected public-DNS fixture for fake fetchers.  This flag is a
            # test-profile signal only; it never grants egress to production
            # code or bypasses SSRFBridge outside pytest.
            "ATLAS_CANDIDATE_VALIDATION": "1",
            # Guardia anti-recursión (incidente 2026-07-09): la suite lanzada
            # por el lazo no puede volver a disparar ticks de mantenimiento.
            "ATLAS_NESTED_TEST_RUN": "1",
            # The jail has no network; this avoids expensive retry paths in
            # libraries that would otherwise attempt model/catalog access.
            "HF_HUB_OFFLINE": "1",
            # Do not read host/user Git configuration, credential helpers, or
            # prompt interactively if a test invokes the mounted worktree Git.
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
        }
        for key, value in self._extra_env.items():
            if key not in _PROTECTED_JAIL_ENV:
                env[key] = value
        return env

    @staticmethod
    def _provided_by_base_jail(path: Path) -> bool:
        return path == Path("/usr") or Path("/usr") in path.parents

    def _provided_by_candidate(self, path: Path) -> bool:
        return path == self._root or self._root in path.parents
