"""
Atlas Core — ToolCoder: bucle de código agéntico por TOOL-CALLING.

Respuesta a la crítica medida del usuario (2026-06-28): AtlasCoder era un
arnés de COMPLETACIÓN DE TEXTO (un prompt → blob → regex), arquitectura que
obligaba a los modelos a emitir formato perfecto a pulso — y la corrupción de
delimitadores mató 8/9 tareas delegadas. Aquí el modelo LLAMA HERRAMIENTAS
con argumentos JSON validados a nivel de API (mismo patrón que Claude Code /
Codex / SWE-agent ACI): el formato lo garantiza la API, no la disciplina del
modelo. Reutiliza la infraestructura ADR-031 de InferenceHub (tools/messages/
tool_calls) que ya usaba AgenticExecutor — el motor existía, el bucle de
código no lo usaba.

Guardrails reutilizados de la sesión: rutas protegidas fail-closed, match
único fail-closed, linter bloqueante — pero aquí los rechazos vuelven al
modelo como RESULTADOS ESTRUCTURADOS de la tool (se corrige en el siguiente
turno), no como warnings de log que nadie lee.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from atlas.core.atlas_coder import (
    CoderResult,
    _is_protected_path,
)
from atlas.core.conditional_rules import load_conditional_rule
from atlas.core.git_autocommit import commit_changes
from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest
from atlas.core.orchestrator_parts.maintenance_facade import _build_avoid_section
from atlas.core.repo_map import build_repo_map

__all__ = ["ToolCoder"]

logger = logging.getLogger(__name__)

_MAX_TOOL_TURNS_DEFAULT = 30  # por iteración — guard anti-loop del bucle agéntico


def _max_tool_turns() -> int:
    """Techo de turnos de tools por iteración, configurable por entorno.

    2026-07-09: el techo fijo de 10 mató 4 delegaciones sobre specs densas —
    el modelo trabajaba bien pero no cabía. Los harnesses de referencia
    (encuesta 2026-06-27: SWE-agent/OpenHands/Aider) operan en 40-100+ turnos;
    30 es el nuevo default conservador y ``ATLAS_TOOL_MAX_TURNS`` permite
    ajustarlo por despliegue sin tocar código.
    """
    raw = os.environ.get("ATLAS_TOOL_MAX_TURNS", "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return _MAX_TOOL_TURNS_DEFAULT

_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lee el contenido completo de un archivo del repo.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "ruta relativa al repo"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "str_replace",
            "description": (
                "Reemplaza old_str por new_str en el archivo. old_str debe "
                "aparecer EXACTAMENTE UNA VEZ (copia las líneas literales del "
                "archivo). Devuelve error si no aparece o aparece varias veces."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_str": {"type": "string"},
                    "new_str": {"type": "string"},
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Crea (o sobrescribe) un archivo con el contenido dado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
]

_SYSTEM_TASK = """\
Eres un agente de programación. Resuelve esta tarea editando el repo con las
herramientas disponibles (read_file, str_replace, create_file):

{task}

{institutional_section}{avoid_section}{repo_map_section}## Archivos de contexto

{files_section}

Cuando termines todos los cambios, responde SIN llamar más herramientas.\
"""

_TEST_FAILURE_MSG = """\
Los tests fallaron tras tus cambios:

{test_output}

Corrige el problema usando las herramientas y termina cuando esté resuelto.\
"""


class ToolCoder:
    """Bucle agéntico de código: el modelo llama tools, los guardrails
    responden estructurado, los tests validan cada iteración."""

    def __init__(
        self,
        hub: InferenceHub,
        *,
        repo_root: Path | None = None,
        timeout_s: int | None = None,
        lesson_store: Any = None,
        lesson_recaller: Any = None,
        institutional_context_files: list[str] | None = None,
    ) -> None:
        self._hub = hub
        self._repo_root = repo_root or Path.cwd()
        # 2026-07-09: 120s fijos mataban toda misión self-build sin test_cmd
        # propio (el fallback es la suite completa, ~7 min) — el tick llegaba
        # a la fase de tests y moría por construcción. Env para despliegues
        # de lazo largo; default sigue 120s (interactivo).
        if timeout_s is None:
            raw = os.environ.get("ATLAS_TOOL_TEST_TIMEOUT_S", "").strip()
            try:
                timeout_s = max(1, int(raw)) if raw else 120
            except ValueError:
                timeout_s = 120
        self._timeout_s = timeout_s
        self._lesson_store = lesson_store
        self._lesson_recaller = lesson_recaller
        self._institutional_files = institutional_context_files

    @classmethod
    def with_default_lessons(
        cls,
        hub: InferenceHub,
        *,
        repo_root: Path | None = None,
        lessons_path: Path | None = None,
        **kwargs: Any,
    ) -> "ToolCoder":
        """Misma factoría-receta que AtlasCoder.with_default_lessons."""
        from atlas.core.lesson_store import LessonStore
        from atlas.immunity.lesson_recaller import LessonRecaller

        root = repo_root or Path.cwd()
        store = LessonStore(lessons_path or (root / "workspace" / "lessons"))
        recaller = LessonRecaller(store, threshold=0.35)
        return cls(
            hub, repo_root=root,
            lesson_store=store, lesson_recaller=recaller,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Tools — cada una devuelve un string que el modelo ve como resultado
    # ------------------------------------------------------------------

    def _tool_read_file(self, path: str) -> str:
        if _is_protected_path(path):
            return f"error: {path} es una ruta protegida (denegado)."
        try:
            return (self._repo_root / path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return f"error: {path} no existe."
        except UnicodeDecodeError:
            return f"error: {path} no es texto legible."
        except IsADirectoryError:
            return f"error: {path} es un directorio, no un archivo."

    def _tool_str_replace(
        self, path: str, old_str: str, new_str: str, changed: list[str]
    ) -> str:
        if _is_protected_path(path):
            return f"error: {path} es una ruta protegida (denegado)."
        abs_path = self._repo_root / path
        try:
            original = abs_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return f"error: {path} no existe. Usa create_file para archivos nuevos."
        count = original.count(old_str)
        if count == 0:
            return (
                f"error: old_str no aparece en {path}. Copia las líneas "
                "EXACTAS del archivo (usa read_file para verlas)."
            )
        if count > 1:
            return (
                f"error: old_str aparece {count} veces en {path} — debe ser "
                "único. Incluye más líneas de contexto para desambiguar."
            )
        new_content = original.replace(old_str, new_str, 1)
        if path.endswith(".py"):
            try:
                import ast as _ast
                _ast.parse(new_content)
            except SyntaxError as exc:
                return (
                    f"error: la edición produce SyntaxError ({exc.msg}, línea "
                    f"{exc.lineno}) — NO aplicada. Corrige y reintenta."
                )
        abs_path.write_text(new_content, encoding="utf-8")
        if path not in changed:
            changed.append(path)
        return f"ok: {path} actualizado."

    _MAX_TRIVIAL_OVERWRITE_LINES = 10  # técnica anti-borrado (2026-07-02)

    def _tool_create_file(self, path: str, content: str, changed: list[str]) -> str:
        if _is_protected_path(path):
            return f"error: {path} es una ruta protegida (denegado)."
        abs_path = self._repo_root / path
        if abs_path.exists():
            try:
                existing = abs_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                existing = ""
            existing_lines = existing.count("\n") + 1 if existing else 0
            if existing_lines > self._MAX_TRIVIAL_OVERWRITE_LINES:
                return (
                    f"error: {path} ya existe con contenido sustancial "
                    f"({existing_lines} líneas) — create_file lo SOBREESCRIBIRÍA "
                    "POR COMPLETO, perdiendo todo lo que no toca tu cambio. "
                    "Usa str_replace para editar sin borrar el resto del archivo."
                )
        if path.endswith(".py"):
            try:
                import ast as _ast
                _ast.parse(content)
            except SyntaxError as exc:
                return (
                    f"error: el contenido produce SyntaxError ({exc.msg}, línea "
                    f"{exc.lineno}) — archivo NO creado. Corrige y reintenta."
                )
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")
        if path not in changed:
            changed.append(path)
        return f"ok: {path} creado."

    def _build_institutional_section(
        self, context_files: list[str] | None = None
    ) -> str:
        """Mismo contrato que AtlasCoder._build_institutional_section, incluida
        la técnica #20 (descubrimiento jerárquico de AGENTS.md)."""
        files = list(
            self._institutional_files
            if self._institutional_files is not None
            else ["AGENTS.md", "WORK_LEDGER.md"]
        )
        if context_files:
            seen = set(files)
            first = context_files[0].replace("\\", "/")
            parts_dir = PurePosixPath(first).parent.parts
            for depth in range(1, len(parts_dir) + 1):
                candidate = "/".join(parts_dir[:depth]) + "/AGENTS.md"
                if candidate not in seen and (self._repo_root / candidate).is_file():
                    files.append(candidate)
                    seen.add(candidate)
        parts: list[str] = []
        for rel_path in files:
            abs_path = self._repo_root / rel_path
            content = load_conditional_rule(abs_path, context_files=context_files or [])
            if content is None:
                continue
            if len(content) > 3000:
                content = content[:3000] + "\n... [truncado]"
            parts.append(f"### {rel_path}\n{content}")
        if not parts:
            return ""
        return "## Contexto institucional del proyecto\n\n" + "\n\n".join(parts)

    def _create_sandbox(self) -> Path:
        """Técnica #6, mismo contrato que AtlasCoder._create_sandbox."""
        sandbox_dir = Path(tempfile.mkdtemp(prefix="tool_coder_sandbox_"))
        shutil.copytree(
            self._repo_root, sandbox_dir,
            ignore=shutil.ignore_patterns(
                ".git", ".venv", ".venv-redteam", "__pycache__",
                ".mypy_cache", ".pytest_cache", "node_modules",
                "data", "workspace", "*.pyc",
            ),
            dirs_exist_ok=True,
        )
        return sandbox_dir

    def _cleanup_sandbox(self, sandbox_dir: Path) -> None:
        try:
            shutil.rmtree(sandbox_dir, ignore_errors=True)
        except Exception:  # noqa: BLE001 — limpieza nunca debe romper el flujo
            pass

    def _sync_sandbox_back(
        self, sandbox_dir: Path, real_repo_root: Path, files_changed: list[str],
    ) -> None:
        for rel_path in files_changed:
            src = sandbox_dir / rel_path
            dst = real_repo_root / rel_path
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            else:
                dst.unlink(missing_ok=True)

    _STRING_ARGS: dict[str, tuple[str, ...]] = {
        "read_file": ("path",),
        "str_replace": ("path", "old_str", "new_str"),
        "create_file": ("path", "content"),
    }

    @staticmethod
    def _repair_json_arguments(raw: str) -> str:
        """Sanea argumentos de tool-call antes de guardarlos en el historial.

        Algunos modelos emiten JSON válido seguido de basura ("Extra data");
        litellm (p.ej. la plantilla de Ollama) hace json.loads sin defensa al
        reproducir el historial en el siguiente turno y crashea. Aquí tomamos
        el primer objeto JSON válido y descartamos el resto; si no hay nada
        parseable, devolvemos "{}" (el modelo verá el error de _dispatch_tool).
        """
        if not raw:
            return "{}"
        try:
            json.loads(raw)
            return raw
        except json.JSONDecodeError:
            pass
        try:
            obj, _end = json.JSONDecoder().raw_decode(raw.strip())
            return json.dumps(obj, ensure_ascii=False)
        except json.JSONDecodeError:
            return "{}"

    def _dispatch_tool(self, name: str, arguments: str, changed: list[str]) -> str:
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            return "error: argumentos JSON inválidos."
        try:
            for field in self._STRING_ARGS.get(name, ()):
                if not isinstance(args[field], str):
                    return (
                        f"error: el argumento {field!r} debe ser un string, "
                        f"recibido {type(args[field]).__name__}."
                    )
            if name == "read_file":
                return self._tool_read_file(args["path"])
            if name == "str_replace":
                return self._tool_str_replace(
                    args["path"], args["old_str"], args["new_str"], changed
                )
            if name == "create_file":
                return self._tool_create_file(args["path"], args["content"], changed)
        except KeyError as exc:
            return f"error: falta el argumento {exc}."
        return f"error: herramienta desconocida {name!r}."

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------

    def code(
        self,
        task: str,
        context_files: list[str],
        test_cmd: list[str],
        max_iterations: int = 3,
        level: InferenceLevel = InferenceLevel.L1,
        sandbox: bool = False,
        repo_map_files: list[str] | None = None,
        auto_commit: bool = False,
        institutional_context_files: list[str] | None = None,
    ) -> CoderResult:
        if not test_cmd:
            return CoderResult(
                success=False, iterations=0, files_changed=[],
                test_output="", error="test_cmd no puede ser vacío",
            )
        protected = [f for f in context_files if _is_protected_path(f)]
        if protected:
            return CoderResult(
                success=False, iterations=0, files_changed=[], test_output="",
                error=f"context_files incluye rutas protegidas: {protected}",
            )

        original_repo_root = self._repo_root
        sandbox_dir: Path | None = None
        if sandbox:
            sandbox_dir = self._create_sandbox()
            self._repo_root = sandbox_dir

        _saved_institutional = self._institutional_files
        if institutional_context_files is not None:
            self._institutional_files = institutional_context_files
        institutional_raw = self._build_institutional_section(context_files=context_files)
        self._institutional_files = _saved_institutional
        institutional_section = institutional_raw + "\n\n" if institutional_raw else ""

        avoid_raw = _build_avoid_section(self._lesson_recaller, self._lesson_store, task)
        avoid_section = avoid_raw.strip("\n") + "\n\n" if avoid_raw else ""

        # Repo-map (técnica #14), mismo contrato que AtlasCoder: una sola vez,
        # visión periférica de símbolos fuera de context_files, no la fuente
        # de verdad.
        repo_map_section = ""
        if repo_map_files:
            repo_map_text = build_repo_map(
                self._repo_root, all_files=repo_map_files, focus_files=context_files,
            )
            if repo_map_text:
                repo_map_section = repo_map_text + "\n\n"

        files_parts = []
        for rel_path in context_files:
            try:
                content = (self._repo_root / rel_path).read_text(encoding="utf-8")
            except FileNotFoundError:
                content = "(no existe)"
            files_parts.append(f"### {rel_path}\n```\n{content}\n```")
        files_section = "\n\n".join(files_parts) if files_parts else "(ninguno)"

        messages: list[dict[str, Any]] = [{
            "role": "user",
            "content": _SYSTEM_TASK.format(
                task=task, institutional_section=institutional_section,
                avoid_section=avoid_section,
                repo_map_section=repo_map_section, files_section=files_section,
            ),
        }]

        changed: list[str] = []
        test_output = ""

        def _cleanup_on_exit() -> None:
            if sandbox_dir is not None:
                self._repo_root = original_repo_root
                self._cleanup_sandbox(sandbox_dir)

        max_turns = _max_tool_turns()
        for iteration in range(1, max_iterations + 1):
            # Bucle de tools dentro de la iteración
            for _turn in range(max_turns):
                request = InferenceRequest(
                    prompt="",  # con messages, el prompt no se usa
                    messages=messages,
                    tools=_TOOLS,
                    level=level,
                    task_id="tool_coder",
                    max_tokens=4096,
                    # Lazo largo: esperar el cooldown de rate-limit (hasta 2
                    # re-caminatas del hub) antes que perder toda la tarea —
                    # 5 delegaciones muertas por all_failed el 2026-07-08.
                    wait_for_ratelimit=True,
                )
                response = self._hub.infer_for_role("edit", request)
                if not response.success:
                    _cleanup_on_exit()
                    return CoderResult(
                        success=False, iterations=iteration, files_changed=changed,
                        test_output=test_output, error=response.error,
                    )
                if not response.tool_calls:
                    break  # el modelo dio respuesta final — pasar a tests
                messages.append({
                    "role": "assistant",
                    "content": response.text or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": self._repair_json_arguments(tc["arguments"]),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                })
                for tc in response.tool_calls:
                    result_str = self._dispatch_tool(tc["name"], tc["arguments"], changed)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_str,
                    })
            else:
                # Techo de turnos alcanzado. Si hubo ediciones reales, correr
                # los tests con lo que hay en vez de descartar el trabajo
                # (2026-07-09: el corte terminal tiró progreso real 3 veces);
                # sin cambios no hay nada que probar — cortar como antes.
                if not changed:
                    _cleanup_on_exit()
                    return CoderResult(
                        success=False, iterations=iteration, files_changed=changed,
                        test_output=test_output,
                        error=f"Límite de {max_turns} turnos de tools alcanzado "
                              "sin respuesta final (posible loop).",
                    )

            # Correr tests
            try:
                result = subprocess.run(
                    test_cmd, cwd=self._repo_root, capture_output=True,
                    timeout=self._timeout_s, text=True,
                )
                test_output = result.stdout + result.stderr
            except subprocess.TimeoutExpired:
                _cleanup_on_exit()
                return CoderResult(
                    success=False, iterations=iteration, files_changed=changed,
                    test_output="", error=f"test_cmd superó {self._timeout_s}s",
                )
            except FileNotFoundError as exc:
                _cleanup_on_exit()
                return CoderResult(
                    success=False, iterations=iteration, files_changed=changed,
                    test_output="", error=f"test_cmd no encontrado: {exc}",
                )

            if result.returncode == 0:
                if sandbox_dir is not None:
                    self._sync_sandbox_back(sandbox_dir, original_repo_root, changed)
                _cleanup_on_exit()
                if auto_commit and changed:
                    commit_changes(self._repo_root, files_changed=changed, task=task)
                return CoderResult(
                    success=True, iterations=iteration, files_changed=changed,
                    test_output=test_output,
                    suspicious_no_op=not changed,
                )

            messages.append({
                "role": "user",
                "content": _TEST_FAILURE_MSG.format(test_output=test_output[-3000:]),
            })

        _cleanup_on_exit()
        return CoderResult(
            success=False, iterations=max_iterations, files_changed=changed,
            test_output=test_output,
            error=f"Tests no pasaron tras {max_iterations} iteraciones.",
        )
