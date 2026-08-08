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

from atlas.engineering.impacted_tests import impacted_tests
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
    #: Etapa en la que terminó: "types" | "impacted" | "full". El ledger sólo
    #: registraba `pytest_exit`, así que 80 fallos de validación no decían en
    #: qué punto ni por qué se cayeron. Por defecto "full" para no romper los
    #: informes que se construyen a mano.
    stage: str = "full"

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "pytest_exit": self.pytest_exit,
            "mypy_exit": self.mypy_exit,
            "pytest_summary": self.pytest_summary,
            "mypy_summary": self.mypy_summary,
            "duration_s": self.duration_s,
            "errors": list(self.errors),
            "stage": self.stage,
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
        changed_files: Sequence[str] | None = None,
    ) -> None:
        self._root = project_root.resolve()
        self._python = python or sys.executable
        self._skip_browser = skip_browser
        self._extra_env = dict(extra_env or {})
        self._jail_factory = jail_factory or BwrapJail
        # Rutas repo-relativas del candidato. Con ellas se puede correr antes
        # el subconjunto impactado; sin ellas se va directo a la suite entera.
        self._changed_files = tuple(changed_files or ())

    def set_changed_files(self, paths: Sequence[str]) -> None:
        """Declara qué tocó el candidato, para poder correr antes su
        subconjunto impactado.

        Existe como setter y no sólo como parámetro del constructor porque los
        llamadores inyectan runners ya construidos (`_runner_factory` recibe
        únicamente el worktree); cambiar esa firma rompería los dobles de test
        de una decena de módulos para no ganar nada.
        """
        self._changed_files = tuple(paths)

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

        def _run(cmd: list[str]) -> Any:
            return jail.run_command(
                cmd,
                working_dir=self._root,
                working_dir_writable=False,
                read_only_paths=runtime_paths,
                timeout_s=timeout_s,
                extra_env=env,
            )

        def _tail(result: Any) -> str:
            return ((result.stdout or "") + (result.stderr or "")).strip()[-2000:]

        # --- Etapa 1: tipos. Medido en esta máquina: mypy 1,24 s frente a los
        # 396 s de la suite completa (320x). Iba SEGUNDO y se ejecutaba siempre,
        # incluso con pytest ya fallado: los 14 fallos mypy-solo del ledger
        # pagaron la suite entera para llegar a un veredicto de un segundo.
        my_result = _run([self._python, "-m", "mypy", "src/atlas/"])
        if my_result.returncode != 0:
            return ValidationReport(
                passed=False,
                pytest_exit=0,
                mypy_exit=my_result.returncode,
                mypy_summary=_tail(my_result),
                duration_s=round(time.monotonic() - start, 2),
                errors=["mypy failed"],
                stage="types",
            )

        # --- Etapa 2: tests impactados, si el candidato dice qué tocó. Sólo
        # puede RECHAZAR: son un subconjunto de la suite, así que un fallo aquí
        # es un fallo allí, pero un verde aquí no concluye nada.
        impacted = self._impacted_targets()
        if impacted:
            imp_result = _run(self._pytest_cmd(impacted))
            if imp_result.returncode != 0:
                return ValidationReport(
                    passed=False,
                    pytest_exit=imp_result.returncode,
                    mypy_exit=my_result.returncode,
                    pytest_summary=_tail(imp_result),
                    mypy_summary=_tail(my_result),
                    duration_s=round(time.monotonic() - start, 2),
                    errors=["pytest failed"],
                    stage="impacted",
                )

        # --- Etapa 3: la suite completa. ÚNICA etapa que puede aceptar.
        py_result = _run(self._pytest_cmd(["tests/"]))
        duration = time.monotonic() - start
        passed = py_result.returncode == 0 and my_result.returncode == 0
        errors: list[str] = []
        if py_result.returncode != 0:
            errors.append("pytest failed")
        if my_result.returncode != 0:
            errors.append("mypy failed")
        return ValidationReport(
            passed=passed,
            pytest_exit=py_result.returncode,
            mypy_exit=my_result.returncode,
            pytest_summary=_tail(py_result),
            mypy_summary=_tail(my_result),
            duration_s=round(duration, 2),
            errors=errors,
            stage="full",
        )

    def _pytest_cmd(self, targets: Sequence[str]) -> list[str]:
        cmd = [self._python, "-m", "pytest", *targets, "-q", "--tb=line",
               # The candidate worktree is read-only.  Disabling pytest's cache
               # avoids a hidden write attempt to .pytest_cache.
               "-p", "no:cacheprovider"]
        if self._skip_browser:
            cmd.extend(["-m", "not computer_use"])
        return cmd

    def _impacted_targets(self) -> list[str]:
        """Tests alcanzados por el diff, o lista vacía si no se puede saber.

        Vacío significa NO MEDIBLE, nunca "todo verde": saltarse la suite
        completa por un mapeo vacío sería aceptar sin evidencia. Y el mapeo es
        señal, no puerta — si revienta, se cae con elegancia a la suite entera.
        """
        if not self._changed_files:
            return []
        try:
            return list(impacted_tests(list(self._changed_files), root=self._root))
        except Exception:  # noqa: BLE001 — una heurística rota no cancela la validación
            return []

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
