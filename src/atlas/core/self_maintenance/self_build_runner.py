"""
Atlas Core — SelfBuildRunner: pegamento entre backlog, ToolCoder y ColdUpdateManager.

Toma un BacklogItem pendiente, deriva un test_cmd razonable, delega la
codificación real a ToolCoder (bucle agéntico de tool-calling ya existente),
y si los tests pasan genera un patch real y lo PROPONE a ColdUpdateManager
con origin="self_audit". Por invariante CVE-HITL (G0.8), origin="self_audit"
NUNCA dispara tier1_auto_apply — toda propuesta de self-build requiere
aprobación humana explícita (approve_pending()/approve() aparte de este
runner). Este módulo solo PROPONE, nunca aplica ni marca items como "done".

Toda ejecución (ToolCoder, evaluación evolutiva, generación de patch) ocurre
en worktrees git efímeros: el árbol de trabajo VIVO del repo nunca se toca,
así que trabajo concurrente sin commitear de un humano u otro agente sobrevive
intacto a cualquier run (incidente "9 YAML regenerados", RootCauseClassifier).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

from atlas.core.cold_update_manager import ColdUpdateManager, ColdUpdateProposal
from atlas.core.git_env import clean_git_env
from atlas.core.inference_hub import InferenceHub, InferenceLevel
from atlas.core.self_maintenance.backlog import BacklogItem
from atlas.core.tool_coder import ToolCoder

__all__ = ["SelfBuildRunner"]

logger = logging.getLogger(__name__)


def _self_build_level() -> InferenceLevel:
    """Nivel de inferencia para autoconstrucción, configurable por entorno.

    2026-07-09: el runner heredaba el default L1 de ToolCoder.code() — el
    tier gratis más débil — sin forma de subirlo; las misiones densas no
    convergían por modelo, no por lazo. ``ATLAS_SELF_BUILD_LEVEL=L2`` sube
    el escalón por despliegue; default L1 (conservador en coste).
    """
    raw = os.environ.get("ATLAS_SELF_BUILD_LEVEL", "").strip().upper()
    if raw and hasattr(InferenceLevel, raw):
        return getattr(InferenceLevel, raw)  # type: ignore[no-any-return]
    return InferenceLevel.L1


# openevolve._prepare_evaluator() extrae el CÓDIGO FUENTE de un evaluator
# callable (inspect.getsource) y lo re-ejecuta en un módulo aislado sin
# closures ni imports externos — un método/closure de SelfBuildRunner (que
# captura self/target_rel/test_cmd/base_ref) es incompatible con ese
# mecanismo (confirmado en vivo: "name 'Any' is not defined" al extraer una
# anotación de tipo sin su import). openevolve SÍ soporta pasar una ruta de
# fichero .py autocontenida directamente (mismo módulo, rama
# isinstance(evaluator, (str, Path))) — por eso este evaluador se escribe a
# disco como texto plano con los valores baked-in, no como función Python.
_WORKTREE_EVALUATOR_TEMPLATE = '''\
import os
import shutil
import subprocess
import uuid
from pathlib import Path

_REPO_ROOT = Path({repo_root!r})
_TARGET_REL = {target_rel!r}
_TEST_CMD = {test_cmd!r}
_BASE_REF = {base_ref!r}
_GIT_HOOK_ENV_VARS = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_PREFIX", "GIT_COMMON_DIR")


def _clean_git_env():
    env = os.environ.copy()
    for var in _GIT_HOOK_ENV_VARS:
        env.pop(var, None)
    return env


def _remove_worktree_path(path):
    if not path.exists():
        return
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(path)],
            cwd=_REPO_ROOT, env=_clean_git_env(), capture_output=True, text=True, check=False,
        )
        if path.exists() and path.resolve() != _REPO_ROOT.resolve():
            shutil.rmtree(path, ignore_errors=True)
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=_REPO_ROOT, env=_clean_git_env(), capture_output=True, text=True, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def evaluate(program_path):
    with open(program_path, encoding="utf-8") as f:
        candidate_code = f.read()

    worktree_path = _REPO_ROOT.parent / f"self-build-evo-{{uuid.uuid4().hex[:12]}}"
    try:
        try:
            create_result = subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_path), _BASE_REF],
                cwd=_REPO_ROOT, env=_clean_git_env(), capture_output=True, text=True, check=False,
            )
            if create_result.returncode != 0:
                return {{"score": 0.0}}

            candidate_target = worktree_path / _TARGET_REL
            candidate_target.parent.mkdir(parents=True, exist_ok=True)
            candidate_target.write_text(candidate_code, encoding="utf-8")

            # Guardia anti-recursión (incidente 2026-07-09): la suite lanzada
            # por el lazo no puede volver a disparar el lazo.
            test_env = _clean_git_env()
            test_env["ATLAS_NESTED_TEST_RUN"] = "1"
            test_result = subprocess.run(
                _TEST_CMD, cwd=worktree_path, env=test_env,
                capture_output=True, text=True, check=False,
            )
            if test_result.returncode == 0:
                return {{"score": 1.0}}
            return {{"score": 0.0}}
        except (OSError, subprocess.SubprocessError):
            return {{"score": 0.0}}
    finally:
        _remove_worktree_path(worktree_path)
'''


def _write_worktree_evaluator_file(
    repo_root: Path, target_rel: str, test_cmd: list[str], base_ref: str,
) -> Path:
    """Escribe a un fichero temporal un evaluador openevolve autocontenido
    (sin closures, con sus propios imports) que evalúa un candidato en un
    worktree git efímero — ver nota de ``_WORKTREE_EVALUATOR_TEMPLATE``
    sobre por qué no puede ser un callable/closure."""
    source = _WORKTREE_EVALUATOR_TEMPLATE.format(
        repo_root=str(repo_root),
        target_rel=target_rel,
        test_cmd=list(test_cmd),
        base_ref=base_ref,
    )
    fd, raw_path = tempfile.mkstemp(prefix="self_build_evaluator_", suffix=".py")
    path = Path(raw_path)
    with open(fd, "w", encoding="utf-8") as f:
        f.write(source)
    return path


class SelfBuildRunner:
    """Conecta backlog -> ToolCoder -> ColdUpdateManager (self_audit, siempre HITL)."""

    def __init__(
        self,
        repo_root: Path,
        hub: InferenceHub,
        cold_update_manager: ColdUpdateManager,
        backlog_path: Path = Path("docs/backlog.yaml"),
        *,
        tool_coder_factory: Callable[..., ToolCoder] = ToolCoder,
    ) -> None:
        self._repo_root = repo_root
        self._hub = hub
        self._cold_update = cold_update_manager
        self._backlog_path = backlog_path
        self._tool_coder_factory = tool_coder_factory

    # ------------------------------------------------------------------
    # derive_test_cmd
    # ------------------------------------------------------------------

    def derive_test_cmd(self, item: BacklogItem) -> list[str]:
        """Deriva el comando de test para un BacklogItem.

        Prioridad: 1) campo test_cmd explícito del item; 2) heurística simple
        de nombre de archivo (NO es NLP, solo un glob por convención de
        nombres: tests/test_{id con '-' -> '_'}*.py); 2.5) mapeo por
        item.targets (2026-07-10: entre el glob por id y el fallback, para
        que items sin id-match pero con targets concretos no caigan a la
        suite completa — ver _tests_from_targets); unión ordenada y
        deduplicada de 2 y 2.5; 3) fallback a la suite completa (`pytest -q`),
        SOLO si ni el id ni los targets producen ningún match.
        """
        if item.test_cmd:
            return list(item.test_cmd)

        slug = item.id.replace("-", "_")
        tests_dir = self._repo_root / "tests"
        id_matches: list[Path] = []
        if tests_dir.is_dir():
            id_matches = sorted(tests_dir.glob(f"test_{slug}*.py"))

        target_matches = self._tests_from_targets(item.targets)

        combined: list[Path] = []
        seen: set[Path] = set()
        for candidate in [*id_matches, *target_matches]:
            if candidate not in seen:
                seen.add(candidate)
                combined.append(candidate)

        if combined:
            # sys.executable -m pytest, NUNCA "pytest" a pelo: la invocación
            # descubierta 2026-07-09 — `pytest -q` desde la raíz revienta en
            # la COLECCIÓN (tests/benchmarks importa `scripts`, que solo es
            # importable con cwd en sys.path, cosa que hace `python -m`). El
            # pre-commit usa `python -m pytest tests/ -q`; el runner debe
            # medir con el MISMO gate o toda misión sin test_cmd muere por
            # construcción.
            rels = [str(p.relative_to(self._repo_root)) for p in combined]
            return [sys.executable, "-m", "pytest", *rels, "-q"]

        return [sys.executable, "-m", "pytest", "tests/", "-q"]

    def _tests_from_targets(self, targets: tuple[str, ...]) -> list[Path]:
        """Mapea item.targets (rutas de código, fichero o directorio con '/'
        final) a tests probables por convención de nombres. Reutiliza
        _expand_targets para el mismo criterio de directorio-no-recursivo ya
        usado en el resto del runner. Tope defensivo de 20 ficheros de test
        (un item mal etiquetado con un target enorme no debe generar un
        comando pytest gigante)."""
        tests_dir = self._repo_root / "tests"
        if not tests_dir.is_dir():
            return []

        matches: list[Path] = []
        for rel in self._expand_targets(targets):
            if not rel.endswith(".py"):
                continue
            stem = Path(rel).stem
            matches.extend(sorted(tests_dir.glob(f"test_{stem}*.py")))
            if len(matches) >= 20:
                break

        seen: set[Path] = set()
        deduped: list[Path] = []
        for candidate in matches:
            if candidate not in seen:
                seen.add(candidate)
                deduped.append(candidate)
        return deduped[:20]

    # ------------------------------------------------------------------
    # run_item
    # ------------------------------------------------------------------

    def run_item(self, item: BacklogItem, *, max_iterations: int = 3) -> dict[str, Any]:
        """Ejecuta ToolCoder sobre el item y, si los tests pasan, PROPONE el
        patch a ColdUpdateManager (origin="self_audit" -> requiere HITL).

        ToolCoder corre en un worktree git efímero (nunca sobre el árbol de
        trabajo vivo) y el patch se genera desde ese worktree: trabajo
        concurrente sin commitear de un humano u otro agente en el árbol vivo
        es intocable, tanto en éxito como en fracaso.

        Nunca marca el item como "done": eso requiere aprobación humana del
        proposal, fuera del alcance de este método.
        """
        test_cmd = self.derive_test_cmd(item)
        task = f"{item.title}\n\n{item.why}\n\nCriterio de aceptación:\n{item.acceptance}"

        worktree_path = self._create_ephemeral_worktree("HEAD")
        if worktree_path is None:
            return {
                "item_id": item.id,
                "proposal_id": None,
                "status": "failed",
                "detail": "no se pudo crear el worktree efímero (git worktree add falló)",
            }
        try:
            coder = self._tool_coder_factory(self._hub, repo_root=worktree_path)
            coder_result = coder.code(
                task,
                context_files=self._expand_targets(item.targets),
                test_cmd=test_cmd,
                max_iterations=max_iterations,
                level=_self_build_level(),
                # Visión periférica automática (patrón Aider): sin esto el modelo
                # solo ve los targets del item y reinventa símbolos que ya existen.
                repo_map_files=self._tracked_py_files(),
                # Planning antes de editar (patrón nº1 de la matriz de harnesses).
                plan=True,
            )

            if not coder_result.success:
                # error + evidencia útil del test_output: "Tests no pasaron tras N
                # iteraciones" sin las líneas FAILED ni los ficheros tocados es
                # indiagnosticable a posteriori (el worktree ya se destruye al salir).
                detail = coder_result.error or "sin detalle"
                if coder_result.test_output:
                    failed_lines = [
                        ln for ln in coder_result.test_output.splitlines()
                        if "FAILED" in ln or "ERROR" in ln or ln.startswith("E ")
                    ]
                    evidence = "\n".join(failed_lines[:12]) or coder_result.test_output[-600:]
                    detail = f"{detail}\n--- evidencia tests ---\n{evidence[:1200]}"
                return {
                    "item_id": item.id,
                    "proposal_id": None,
                    "status": "failed",
                    "detail": detail,
                    "files_changed": list(coder_result.files_changed),
                }

            patch_path = self._write_patch(worktree_path)
        finally:
            self._remove_worktree_path(worktree_path)

        if patch_path is None:
            return {
                "item_id": item.id,
                "proposal_id": None,
                "status": "failed",
                "detail": "tests pasaron pero no se pudo generar diff (sin cambios detectables en git)",
            }

        cycle_summary = {
            "success": coder_result.success,
            "iterations": coder_result.iterations,
            "files_changed": list(coder_result.files_changed),
            "suspicious_no_op": getattr(coder_result, "suspicious_no_op", False),
        }

        proposal: ColdUpdateProposal = self._cold_update.propose(
            intent=item.title,
            patch_path=patch_path,
            origin="self_audit",
            risk="medium",
            evidence={
                "backlog_item_id": item.id,
                "cycle_result": cycle_summary,
            },
        )

        return {
            "item_id": item.id,
            "proposal_id": proposal.id,
            "status": "proposed",
            "detail": cycle_summary,
        }

    # ------------------------------------------------------------------
    # run_item_with_evolution
    # ------------------------------------------------------------------

    def run_item_with_evolution(
        self,
        item: BacklogItem,
        *,
        evolution_gate: Any,
        max_iterations: int = 3,
        base_ref: str = "HEAD",
    ) -> dict[str, Any]:
        """Variante de run_item() para items donde vale la pena generar y
        puntuar VARIAS variantes reales (selección evolutiva vía openevolve,
        EvolutionGate) en vez de un solo intento de ToolCoder. Evoluciona el
        PRIMER target del item, evaluando cada candidato en un worktree git
        efímero real (aplica el candidato, corre el test_cmd real del item,
        puntúa 1.0/0.0 según pase o no). Si la evolución no produce una
        variante mejor que la actual (best_score <= 0 o no succeeded), o el
        item no tiene un target de fichero válido, cae al camino normal de
        run_item() (mismo comportamiento de siempre, ToolCoder). Nunca aplica
        nada a la rama real: solo prueba en worktrees efímeros, igual que
        ColdUpdateBatcher. El resultado final, si la evolución SÍ mejora algo,
        se propone a ColdUpdateManager exactamente igual que run_item()
        (origin='self_audit', HITL intacto)."""
        targets = self._expand_targets(item.targets)
        if not targets:
            return self.run_item(item, max_iterations=max_iterations)

        target_rel = targets[0]
        target_path = self._repo_root / target_rel
        if not target_path.is_file():
            return self.run_item(item, max_iterations=max_iterations)

        test_cmd = self.derive_test_cmd(item)
        initial_code = target_path.read_text(encoding="utf-8")

        evaluator_path = _write_worktree_evaluator_file(
            self._repo_root, target_rel, test_cmd, base_ref,
        )
        try:
            outcome = evolution_gate.evolve(
                initial_code=initial_code, evaluator=str(evaluator_path),
            )
        finally:
            evaluator_path.unlink(missing_ok=True)

        if not outcome.succeeded or outcome.best_score <= 0.0:
            return self.run_item(item, max_iterations=max_iterations)

        # El patch se genera en un worktree efímero: el árbol de trabajo vivo
        # no se toca nunca, ni siquiera en el camino exitoso.
        worktree_path = self._create_ephemeral_worktree(base_ref)
        if worktree_path is None:
            return {
                "item_id": item.id,
                "proposal_id": None,
                "status": "failed",
                "detail": "evolución mejoró la puntuación pero no se pudo crear "
                          "el worktree efímero para generar el diff",
            }
        try:
            candidate_target = worktree_path / target_rel
            candidate_target.parent.mkdir(parents=True, exist_ok=True)
            candidate_target.write_text(outcome.best_code, encoding="utf-8")
            patch_path = self._write_patch(worktree_path)
        finally:
            self._remove_worktree_path(worktree_path)

        if patch_path is None:
            return {
                "item_id": item.id,
                "proposal_id": None,
                "status": "failed",
                "detail": "evolución mejoró la puntuación pero no se pudo generar diff",
            }

        proposal: ColdUpdateProposal = self._cold_update.propose(
            intent=item.title,
            patch_path=patch_path,
            origin="self_audit",
            risk="medium",
            evidence={
                "backlog_item_id": item.id,
                "evolution_score": outcome.best_score,
                "method": "evolution_gate",
            },
        )
        return {
            "item_id": item.id,
            "proposal_id": proposal.id,
            "status": "proposed",
            "detail": {"evolution_score": outcome.best_score, "method": "evolution_gate"},
        }

    def _evaluate_candidate_in_worktree(
        self,
        target_rel: str,
        candidate_code: str,
        test_cmd: list[str],
        base_ref: str,
    ) -> dict[str, Any]:
        """Crea un worktree git efímero desde base_ref, sobreescribe target_rel
        con candidate_code, corre test_cmd en ese worktree (subprocess,
        check=False), puntúa {'score': 1.0} si returncode==0 y {'score': 0.0}
        en cualquier otro caso (incluida excepción del propio subprocess —
        fail-closed, nunca puntúa alto por error). SIEMPRE limpia el worktree
        (try/finally), incluso si algo falla a mitad."""
        worktree_path = self._repo_root.parent / f"self-build-evo-{uuid.uuid4().hex[:12]}"
        try:
            try:
                create_result = subprocess.run(
                    ["git", "worktree", "add", "--detach", str(worktree_path), base_ref],
                    cwd=self._repo_root,
                    env=clean_git_env(),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if create_result.returncode != 0:
                    return {"score": 0.0}

                candidate_target = worktree_path / target_rel
                candidate_target.parent.mkdir(parents=True, exist_ok=True)
                candidate_target.write_text(candidate_code, encoding="utf-8")

                test_result = subprocess.run(
                    test_cmd,
                    cwd=worktree_path,
                    env=clean_git_env(),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if test_result.returncode == 0:
                    return {"score": 1.0}
                return {"score": 0.0}
            except (OSError, subprocess.SubprocessError):
                return {"score": 0.0}
        finally:
            self._remove_worktree_path(worktree_path)

    def _remove_worktree_path(self, path: Path) -> None:
        """Elimina un worktree efímero creado por _evaluate_candidate_in_worktree.
        Nunca lanza — es limpieza de mejor esfuerzo tras evaluar un candidato."""
        if not path.exists():
            return
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(path)],
                cwd=self._repo_root,
                env=clean_git_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            if path.exists() and path.resolve() != self._repo_root.resolve():
                shutil.rmtree(path, ignore_errors=True)
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=self._repo_root,
                env=clean_git_env(),
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def _tracked_py_files(self) -> list[str]:
        """Todos los .py trackeados del repo — alimenta el repo-map del coder
        (firmas AST, no contenido; barato incluso con ~200 módulos). Lista
        vacía si git falla: el repo-map es opcional, nunca bloquea el tick."""
        try:
            result = subprocess.run(
                ["git", "ls-files", "*.py"],
                cwd=self._repo_root, capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                return []
            return result.stdout.split()
        except (OSError, subprocess.SubprocessError):
            return []

    def _expand_targets(self, targets: tuple[str, ...] | list[str]) -> list[str]:
        """Expande targets que son directorios (terminan en '/') a los .py
        que contienen (no recursivo — un target de directorio en el backlog
        describe un módulo plano, no un árbol completo). Los targets que ya
        son ficheros pasan intactos."""
        out: list[str] = []
        for target in targets:
            if target.endswith("/"):
                abs_dir = self._repo_root / target
                if abs_dir.is_dir():
                    out.extend(
                        str(p.relative_to(self._repo_root))
                        for p in sorted(abs_dir.glob("*.py"))
                    )
                continue
            out.append(target)
        return out

    def _create_ephemeral_worktree(self, base_ref: str) -> Path | None:
        """Crea un worktree git efímero desde base_ref donde ToolCoder y la
        generación del patch pueden operar libremente — el árbol de trabajo
        VIVO (con posible trabajo concurrente sin commitear de un humano u
        otro agente) nunca se toca. Devuelve None si git falla (fail-closed:
        sin worktree no hay run)."""
        worktree_path = self._repo_root.parent / f"self-build-item-{uuid.uuid4().hex[:12]}"
        try:
            result = subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_path), base_ref],
                cwd=self._repo_root,
                env=clean_git_env(),
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return worktree_path

    def _write_patch(self, worktree_root: Path) -> Path | None:
        """Genera un .patch con `git diff HEAD` desde un worktree efímero.

        Hace `git add -A` primero — seguro SOLO porque el worktree es efímero
        y se destruye después — para que los ficheros NUEVOS creados por
        ToolCoder entren también en el diff. Devuelve None si no hay diff
        (nada que proponer) o si git falla.
        """
        try:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=worktree_root,
                env=clean_git_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            result = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=worktree_root,
                env=clean_git_env(),
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("SelfBuildRunner: git diff falló (%s)", exc)
            return None

        if result.returncode != 0 or not result.stdout.strip():
            return None

        tmp_dir = Path(tempfile.mkdtemp(prefix="self_build_patch_"))
        patch_path = tmp_dir / "change.patch"
        patch_path.write_text(result.stdout, encoding="utf-8")
        return patch_path

    # ------------------------------------------------------------------
    # update_backlog_status
    # ------------------------------------------------------------------

    def update_backlog_status(self, item_id: str, new_status: str) -> None:
        """Reescribe SOLO el campo `status` del item `item_id` en el YAML.

        Manipulación de texto línea a línea (no ruamel: el proyecto ya usa
        yaml.safe_load/safe_dump en otros sitios, p.ej. backlog.py) para NO
        reordenar ni reformatear el resto del archivo — solo se toca la
        línea `status: <valor>` dentro del bloque del item indicado.
        """
        text = self._backlog_path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)

        id_re = re.compile(r'^\s*-?\s*id:\s*["\']?' + re.escape(item_id) + r'["\']?\s*$')
        status_re = re.compile(r"^(\s*status:\s*)(\S+)(.*)$")

        in_target_item = False
        out_lines: list[str] = []
        for line in lines:
            if re.match(r"^\s*-\s*id:\s*", line):
                in_target_item = bool(id_re.match(line.rstrip("\n")))
            if in_target_item:
                m = status_re.match(line.rstrip("\n"))
                if m:
                    newline = "\n" if line.endswith("\n") else ""
                    out_lines.append(f"{m.group(1)}{new_status}{m.group(3)}{newline}")
                    in_target_item = False
                    continue
            out_lines.append(line)

        self._backlog_path.write_text("".join(out_lines), encoding="utf-8")
