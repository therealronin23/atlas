"""
Atlas Core — AtlasCoder
Agente de codificación autónomo con bucle infer → editar → test.

Usa InferenceHub para generar ediciones en formato SEARCH/REPLACE y
las aplica iterativamente hasta que los tests pasan o se agota max_iterations.
"""

from __future__ import annotations

import ast
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any

from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest
from atlas.core.orchestrator_parts.maintenance_facade import _build_avoid_section
from atlas.core.patch_format import (
    AddFileOp,
    DeleteFileOp,
    UpdateFileOp,
    apply_update_hunk,
    parse_patch_envelope,
)
from atlas.core.conditional_rules import load_conditional_rule
from atlas.core.git_autocommit import commit_changes
from atlas.core.repo_map import build_repo_map
from atlas.core.trunk_preflight import build_trunk_preflight_section

VERSION = '1.0.0'

__all__ = ["AtlasCoder", "CoderResult", "CodingStrategy"]

logger = logging.getLogger(__name__)

# Técnica #12/#19 (harness survey — Codex CLI rutas protegidas / Cline "comandos
# destructivos siempre piden aprobación"): AtlasCoder no ejecuta shell arbitrario
# (solo test_cmd fijo del llamador), así que el riesgo real es EDITAR donde no
# debe. Fail-closed: ningún context_file puede tocar estas rutas, sin excepción
# ni auto-approve posible — se verifica ANTES de llamar al modelo.
PROTECTED_PATH_SEGMENTS: frozenset[str] = frozenset({
    ".git", ".env", ".ssh", "secrets.env", ".aws", ".gnupg",
})


def _is_protected_path(rel_path: str) -> bool:
    parts = PurePosixPath(rel_path.replace("\\", "/")).parts
    return any(seg in PROTECTED_PATH_SEGMENTS for seg in parts)


class CodingStrategy(str, Enum):
    FAST = "fast"        # L1: mejor modelo disponible; InferenceHub cae a L0 si hay rate limit
    STANDARD = "standard"  # L1: igual que FAST, sin restricciones de iteración
    COUNCIL = "council"  # L2 si disponible (NIM 405B), L1 como fallback; Cónclave delibera el plan


_COUNCIL_KEYWORDS = frozenset({
    "refactor", "rediseña", "migra", "arquitectura", "reestructura",
    "redesign", "migrate", "architecture", "restructure",
})


def _classify_task(task: str) -> CodingStrategy:
    """Heurística simple: keywords arquitectónicos → COUNCIL, texto largo → STANDARD, resto → FAST."""
    lower = task.lower()
    if any(kw in lower for kw in _COUNCIL_KEYWORDS):
        return CodingStrategy.COUNCIL
    if len(task) > 300:
        return CodingStrategy.STANDARD
    return CodingStrategy.FAST

_SEARCH_REPLACE_RE = re.compile(
    r"<{7} SEARCH\s*(.*?)\s*={7}\s*(.*?)\s*>{7}(?:\s*(?:REPLACE|END))?",
    re.DOTALL,
)

# Eliminar fences de código que algunos modelos añaden alrededor de los bloques
_CODE_FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
# Eliminar bloques <think>...</think> de modelos razonadores (DeepSeek-R1, Qwen3)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_fences(text: str) -> str:
    """Limpia la respuesta del modelo: elimina thinking tokens y fences de código."""
    text = _THINK_RE.sub("", text)
    parts = _CODE_FENCE_RE.findall(text)
    return "\n".join(parts) + "\n" + _CODE_FENCE_RE.sub("", text) if parts else text

_PROMPT_BASE = """\
Eres un asistente de programación. Tu tarea es modificar el código para resolver:

{task}

{institutional_section}{avoid_section}## Archivos de contexto

{files_section}

{repo_map_section}## Instrucciones de formato

{instructions_section}\
"""

_INSTRUCTIONS_SEARCH_REPLACE = """\
Para cada cambio, usa EXACTAMENTE este formato (los textos entre <angulares>
son PLACEHOLDERS que debes sustituir por código real del archivo — nunca los
copies literalmente):
<<<<<<< SEARCH
<líneas EXACTAS copiadas del archivo de contexto, incluyendo indentación>
=======
<las mismas líneas ya modificadas>
>>>>>>> REPLACE

Si necesitas crear un archivo nuevo, usa SEARCH vacío:
<<<<<<< SEARCH
=======
<contenido completo del archivo nuevo>
>>>>>>> REPLACE

Reglas estrictas:
- El bloque SEARCH debe ser una copia EXACTA de líneas que existen en uno de
  los archivos de contexto — cópialas de ahí, no las inventes.
- Un bloque pequeño y único es mejor que uno grande: incluye solo las líneas
  que cambian más 1-2 líneas de contexto si hace falta para que sea único.
- Solo incluye los bloques SEARCH/REPLACE. No expliques los cambios.\
"""

# Técnica #18 (patrón OpenAI Codex CLI / Cline SDK): envelope orientado a
# archivo en vez de SEARCH/REPLACE — cada operación es explícita, sin
# heurísticas de matching difuso. El "@@" ancla el hunk; las líneas de
# contexto (" ") y eliminadas ("-") deben aparecer EXACTAMENTE una vez en
# el archivo (mismo fail-closed que SEARCH/REPLACE, técnica #3).
_INSTRUCTIONS_APPLY_PATCH = """\
Usa EXACTAMENTE este formato para todos los cambios:

*** Begin Patch
*** Add File: ruta/al/archivo_nuevo.py
+contenido del archivo nuevo, línea a línea
+con el prefijo + en cada línea
*** Update File: ruta/al/archivo_existente.py
@@
 línea de contexto sin cambios (prefijo espacio)
-línea que se elimina (prefijo guion)
+línea que se añade (prefijo más)
 línea de contexto sin cambios
*** Delete File: ruta/al/archivo_a_borrar.py
*** End Patch

Reglas:
- Las líneas de contexto y las eliminadas deben coincidir EXACTAMENTE
  (incluyendo indentación) con el contenido real del archivo.
- Puedes usar varios bloques "@@" dentro de un mismo "Update File" para
  varios cambios no contiguos.
- No expliques los cambios, solo el envelope entre Begin Patch y End Patch.\
"""

_APPLY_MODEL_PROMPT = """\
Un modelo de razonamiento intentó aplicar un cambio a este archivo pero el \
bloque SEARCH no calzó exactamente (posible desajuste menor). Tu tarea es \
mecánica: aplica la INTENCIÓN del cambio directamente sobre el archivo real \
y devuelve el archivo COMPLETO corregido, sin explicaciones ni fences.

## Archivo real ({rel_path})
```
{original}
```

## Cambio pretendido (puede no calzar exacto, aplica la intención)
SEARCH (aproximado):
{search_text}

REPLACE:
{replace_text}

Devuelve SOLO el contenido completo del archivo con el cambio aplicado.\
"""

_ITERATION_ERROR_SECTION = """\

## Error de tests en iteración anterior

{test_output}

Corrige el error anterior.\
"""


@dataclass
class CoderResult:
    success: bool
    iterations: int
    files_changed: list[str]
    test_output: str
    error: str | None = None
    blocks_parsed: int = 0
    blocks_applied: int = 0
    # Alarma de falso positivo (lección del lote A-D, 2026-06-28): success=True
    # con files_changed vacío es sospechoso — el test pasó sin que se aplicara
    # ningún cambio real (bloque no ancló, o el test ya pasaba de antes). No es
    # necesariamente un error (a veces es legítimo), pero merece revisión.
    suspicious_no_op: bool = False


class AtlasCoder:
    """
    Agente de codificación que cicla infer → parsear ediciones → aplicar → test
    hasta que los tests pasan o se alcanza max_iterations.
    """

    def __init__(
        self,
        hub: InferenceHub,
        *,
        repo_root: Path | None = None,
        timeout_s: int = 120,
        strategy: CodingStrategy | None = None,
        institutional_context_files: list[str] | None = None,
        lesson_store: Any = None,
        lesson_recaller: Any = None,
        # lesson_recaller: construir con threshold explícito (ej. ~0.35 con
        # embedder semántico), NO el default 0.8 de LessonRecaller — ese 0.8
        # está calibrado para su caso de uso original (detección de
        # casi-duplicados de ataques, similitud muy exigente), no para
        # "relevancia temática de una lección frente a una tarea de código"
        # (medido en vivo 2026-06-28: la lección más relevante a una tarea
        # real puntuó 0.71 con FastEmbedEmbedder — 0.8 la habría descartado).
    ) -> None:
        self._hub = hub
        self._repo_root = repo_root or Path.cwd()
        self._timeout_s = timeout_s
        self._strategy = strategy  # None = auto-clasificar por tarea
        # Archivos de contexto institucional leídos una vez al inicio del bucle.
        # Por defecto: AGENTS.md + WORK_LEDGER.md si existen.
        self._institutional_files = institutional_context_files
        # Cierra el hueco de "memoria consultada solo DESPUÉS de fallar": si se
        # inyectan store+recaller, cada tarea consulta LessonStore ANTES de
        # generar código (mismo _build_avoid_section que ya usa codegen).
        self._lesson_store = lesson_store
        self._lesson_recaller = lesson_recaller

    @classmethod
    def with_default_lessons(
        cls,
        hub: InferenceHub,
        *,
        repo_root: Path | None = None,
        lessons_path: Path | None = None,
        **kwargs: Any,
    ) -> "AtlasCoder":
        """Factoría con la receta completa: LessonStore + LessonRecaller ya
        cableados, para que ninguna delegación pueda olvidarlos (error medido
        en el enjambre 2026-06-28: la consulta de lecciones existía pero las
        delegaciones construían AtlasCoder sin ella). threshold=0.35 = caso de
        uso "relevancia temática lección↔tarea", no el 0.8 de casi-duplicados."""
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
    # Interfaz pública
    # ------------------------------------------------------------------

    def code(
        self,
        task: str,
        context_files: list[str],
        test_cmd: list[str],
        max_iterations: int = 3,
        strategy: CodingStrategy | None = None,
        institutional_context_files: list[str] | None = None,  # override por-llamada
        revert_on_failure: bool = True,
        repo_map_files: list[str] | None = None,
        edit_format: str = "search_replace",
        use_apply_model: bool = False,
        sandbox: bool = False,
        auto_commit: bool = False,
    ) -> CoderResult:
        """
        Ejecuta el bucle infer→editar→test.

        Parámetros
        ----------
        task:
            Descripción en lenguaje natural de lo que se debe implementar.
        context_files:
            Rutas relativas a repo_root de los archivos que el modelo verá y
            podrá editar.
        test_cmd:
            Comando a ejecutar para validar los cambios (ej. ["pytest", "-x"]).
        max_iterations:
            Número máximo de ciclos de corrección.
        edit_format:
            Técnica #18: "search_replace" (default, bloques SEARCH/REPLACE) o
            "apply_patch" (envelope orientado a archivo, patrón OpenAI Codex
            CLI / Cline SDK — más fiable para modelos que fallan con matching
            difuso). Aditivo: el default no cambia comportamiento existente.
        institutional_context_files:
            Override por-llamada de los archivos institucionales. Si se pasa,
            reemplaza el valor configurado en el constructor para esta llamada.
        repo_map_files:
            Técnica #14 (patrón Aider): rutas .py adicionales del repo (fuera
            de context_files) a considerar para el repo-map — firmas de
            símbolos rankeadas por PageRank respecto a context_files, sin
            enviar su contenido completo. None (default) = sin repo-map,
            opt-in explícito para no escanear el repo entero sin que se pida.
        use_apply_model:
            Técnica #4 (patrón Cursor/Continue/Aider architect/Cline Plan-Act):
            si un bloque SEARCH/REPLACE falla en aplicarse mecánicamente,
            delega en un modelo barato con rol "apply" que reescribe el
            archivo completo dada la intención. Solo aplica con
            edit_format="search_replace" y exactamente 1 context_file
            (evita ambigüedad de a qué archivo pertenece el bloque fallido).
            Default False: comportamiento idéntico al anterior si no se pide.
        revert_on_failure:
            Si el resultado final es fallo (tests nunca pasaron o se abortó por
            stuck-detector), restaura context_files a su contenido original
            (checkpoint tipo shadow-git, patrón Cline). Evita dejar el repo en
            un estado a medio editar tras un run fallido.
        sandbox:
            Técnica #6 replanteada (allowlist→sandbox, sin clasificador LLM —
            violaría la invariante D2 de AutonomousDecider): aplica TODO el
            bucle sobre una copia aislada de repo_root en un directorio
            temporal; test_cmd corre ahí. Solo si el resultado final es
            success=True se sincronizan los archivos de files_changed de
            vuelta al repo_root real. Si falla, el repo real nunca se toca
            (más fuerte que revert_on_failure, que sí necesita revertir
            porque escribe directo). El directorio temporal se limpia siempre
            (éxito o fallo). Default False: comportamiento idéntico al
            anterior si no se pide.
        auto_commit:
            Técnica #16 (patrón Aider): si el resultado final es success=True,
            commitea files_changed automáticamente con mensaje "[atlas-coder]
            <task>" (marcador de autoría — permite distinguir commits propios
            de humanos para un /undo seguro, vía git_autocommit.is_atlas_commit).
            Solo commitea si hubo cambios reales. Default False: sin cambio de
            comportamiento si no se pide.
        """
        if not test_cmd:
            return CoderResult(
                success=False,
                iterations=0,
                files_changed=[],
                test_output="",
                error="test_cmd no puede ser vacío",
            )

        if edit_format not in ("search_replace", "apply_patch"):
            return CoderResult(
                success=False,
                iterations=0,
                files_changed=[],
                test_output="",
                error=f"edit_format inválido: {edit_format!r}",
            )

        protected = [f for f in context_files if _is_protected_path(f)]
        if protected:
            return CoderResult(
                success=False,
                iterations=0,
                files_changed=[],
                test_output="",
                error=(
                    f"context_files incluye rutas protegidas (fail-closed, sin "
                    f"excepción): {protected}"
                ),
            )

        # Técnica #6 (sandbox): a partir de aquí, si sandbox=True, self._repo_root
        # apunta a una copia aislada — todo lo que sigue (lectura/escritura de
        # archivos, test_cmd) opera sobre ella sin tocar el repo real.
        original_repo_root = self._repo_root
        sandbox_dir: Path | None = None
        if sandbox:
            sandbox_dir = self._create_sandbox()
            self._repo_root = sandbox_dir

        effective_strategy = strategy or self._strategy or _classify_task(task)
        # Siempre pedir el mejor modelo disponible; InferenceHub hace fallback si hay rate limit.
        # COUNCIL → L2 (NIM 405B si hay crédito); FAST/STANDARD → L1 (Llama 70B / Qwen 32B).
        level = InferenceLevel.L2 if effective_strategy == CodingStrategy.COUNCIL else InferenceLevel.L1

        if effective_strategy == CodingStrategy.COUNCIL:
            plan_context = self._build_files_section(context_files)
            council_result = self._run_council(task, plan_context)
            if council_result is not None:
                # Enriquecer el task con el veredicto del Cónclave
                task = task + f"\n\n## Plan revisado por Cónclave\n{council_result}"

        # Construir sección institucional una sola vez antes del bucle
        _saved = self._institutional_files
        if institutional_context_files is not None:
            self._institutional_files = institutional_context_files
        institutional_section = self._build_institutional_section(context_files=context_files)
        self._institutional_files = _saved
        # Añadir separador solo si hay contenido
        institutional_section_in_prompt = (
            institutional_section + "\n\n" if institutional_section else ""
        )

        # Lecciones relevantes a la tarea, consultadas ANTES de generar código
        # (cierra el hueco de "memoria solo escrita tras fallar, nunca leída
        # antes del siguiente intento" — reusa _build_avoid_section, mismo
        # mecanismo que codegen). Opt-in: sin lesson_store/recaller, sección
        # vacía, cero cambio de comportamiento.
        avoid_raw = _build_avoid_section(self._lesson_recaller, self._lesson_store, task)
        avoid_section_in_prompt = avoid_raw.strip("\n") + "\n\n" if avoid_raw else ""
        trunk_preflight_section = build_trunk_preflight_section(self._repo_root, task)

        # Repo-map (técnica #14): se construye una sola vez, no por iteración
        # (misma economía que institutional_section — es visión periférica,
        # no la fuente de verdad; context_files se relee completo cada turno).
        repo_map_section = ""
        if repo_map_files:
            repo_map_text = build_repo_map(
                self._repo_root, all_files=repo_map_files, focus_files=context_files,
            )
            if repo_map_text:
                repo_map_section = repo_map_text + "\n\n"

        files_changed: list[str] = []
        test_output = ""
        prev_error: str | None = None
        no_progress_streak = 0
        self._lint_rejections: list[str] = []

        # Checkpoint pre-run (patrón Cline shadow-git): snapshot del contenido
        # original de cada archivo de contexto, para poder revertir un run
        # fallido sin dejar el repo en un estado a medio editar.
        snapshot: dict[str, str | None] = {}
        for rel_path in context_files:
            abs_path = self._repo_root / rel_path
            try:
                snapshot[rel_path] = abs_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                snapshot[rel_path] = None

        def _failure(iteration: int, error: str | None, output: str = "") -> CoderResult:
            # Con sandbox activo, el repo real nunca se tocó — no hay nada que
            # revertir ahí (más fuerte que revert_on_failure, que sí lo necesita
            # porque escribe directo). Solo se restaura si NO hay sandbox.
            if revert_on_failure and sandbox_dir is None:
                self._restore_snapshot(snapshot)
            if sandbox_dir is not None:
                self._repo_root = original_repo_root
                self._cleanup_sandbox(sandbox_dir)
            return CoderResult(
                success=False,
                iterations=iteration,
                files_changed=files_changed,
                test_output=output,
                error=error,
            )

        for iteration in range(1, max_iterations + 1):
            logger.debug("AtlasCoder — iteración %d/%d", iteration, max_iterations)

            # 1. Leer contenido actual de los archivos de contexto
            files_section = self._build_files_section(context_files)

            # 2. Construir prompt
            instructions_section = (
                _INSTRUCTIONS_APPLY_PATCH if edit_format == "apply_patch"
                else _INSTRUCTIONS_SEARCH_REPLACE
            )
            prompt = _PROMPT_BASE.format(
                task=task,
                files_section=files_section,
                institutional_section=institutional_section_in_prompt,
                avoid_section=trunk_preflight_section + avoid_section_in_prompt,
                repo_map_section=repo_map_section,
                instructions_section=instructions_section,
            )
            if prev_error is not None:
                prompt += _ITERATION_ERROR_SECTION.format(test_output=prev_error)

            # 3. Llamar al hub de inferencia
            request = InferenceRequest(
                prompt=prompt,
                level=level,
                task_id="atlas_coder",
                max_tokens=4096,
            )
            # Lazo 4: routing por rol "edit" (soft-preference, cae a infer()
            # normal si ningún provider del nivel pedido está etiquetado).
            response = self._hub.infer_for_role("edit", request)

            if not response.success:
                return _failure(iteration, response.error, test_output)

            # 4. Parsear y aplicar las ediciones (formato seleccionado)
            if edit_format == "apply_patch":
                changed = self._apply_patch_format_edits(response.text, context_files)
            else:
                changed = self._apply_edits(
                    response.text, context_files, use_apply_model=use_apply_model,
                )
            for f in changed:
                if f not in files_changed:
                    files_changed.append(f)

            # Stuck detector (lección de OpenHands/SWE-agent): si dos
            # iteraciones seguidas no aplican NINGUNA edición, el modelo está
            # dando vueltas sin progreso — abortar antes de agotar
            # max_iterations en vez de seguir gastando cómputo en un loop
            # condenado (SWE-agent midió 89% de fallo tras >=10 repeticiones;
            # cortamos mucho antes).
            if not changed:
                no_progress_streak += 1
            else:
                no_progress_streak = 0
            if no_progress_streak >= 2:
                return _failure(
                    iteration,
                    f"Abortado tras {no_progress_streak} iteraciones consecutivas "
                    "sin ediciones aplicadas (stuck detector).",
                    test_output,
                )

            # 5. Correr tests
            try:
                # Con sandbox activo, PYTHONPATH del sandbox debe ganar a la
                # instalación editable del repo real (site-packages apunta al
                # repo real → sin esto, los tests importarían el código SIN
                # las ediciones del sandbox y siempre fallarían). PYTHONPATH
                # precede a site-packages en sys.path.
                import os as _os
                test_env = dict(_os.environ)
                if sandbox_dir is not None:
                    sandbox_paths = [str(sandbox_dir / "src"), str(sandbox_dir)]
                    existing = test_env.get("PYTHONPATH", "")
                    test_env["PYTHONPATH"] = _os.pathsep.join(
                        sandbox_paths + ([existing] if existing else [])
                    )
                # Guardia anti-recursión (ver tool_coder.py, incidente 2026-07-09):
                # la suite lanzada por el lazo no puede volver a disparar el lazo.
                test_env["ATLAS_NESTED_TEST_RUN"] = "1"
                result = subprocess.run(
                    test_cmd,
                    cwd=self._repo_root,
                    capture_output=True,
                    timeout=self._timeout_s,
                    text=True,
                    env=test_env,
                )
                test_output = result.stdout + result.stderr
            except subprocess.TimeoutExpired:
                return _failure(iteration, f"test_cmd superó el timeout de {self._timeout_s}s")
            except FileNotFoundError as exc:
                return _failure(iteration, f"test_cmd no encontrado: {exc}")

            if result.returncode == 0:
                if sandbox_dir is not None:
                    self._sync_sandbox_back(sandbox_dir, original_repo_root, files_changed)
                    self._repo_root = original_repo_root
                    self._cleanup_sandbox(sandbox_dir)
                no_op = not files_changed
                if no_op:
                    logger.warning(
                        "AtlasCoder: success=True pero files_changed=[] — "
                        "posible falso positivo (test pasó sin cambios reales); "
                        "revisar si la tarea realmente se cumplió."
                    )
                if auto_commit and files_changed:
                    commit_changes(
                        self._repo_root, files_changed=files_changed, task=task,
                    )
                return CoderResult(
                    success=True,
                    iterations=iteration,
                    files_changed=files_changed,
                    test_output=test_output,
                    blocks_parsed=getattr(self, '_last_blocks_parsed', 0),
                    blocks_applied=getattr(self, '_last_blocks_applied', 0),
                    suspicious_no_op=no_op,
                )

            # Tests fallaron: preparar para siguiente iteración
            prev_error = test_output
            if self._lint_rejections:
                prev_error += (
                    "\n\n## Ediciones rechazadas por el linter\n"
                    + "\n".join(self._lint_rejections)
                )
                self._lint_rejections = []
            logger.debug("Tests fallaron en iteración %d; reintentando.\n%s", iteration, test_output[:500])

        # Se agotaron las iteraciones
        return _failure(
            max_iterations,
            f"Tests no pasaron tras {max_iterations} iteraciones.",
            test_output,
        )

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _build_institutional_section(
        self, context_files: list[str] | None = None
    ) -> str:
        """Lee los archivos de contexto institucional y construye la sección del prompt.

        Técnica #20 (Codex CLI): descubrimiento jerárquico — además de los
        archivos raíz, se incluyen los AGENTS.md que existan en los directorios
        ancestros del primer context_file (raíz→específico; el más específico
        queda al final, mayor prioridad de lectura para el modelo).
        """
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
            # Técnica #11 cableada (2026-07-02): load_conditional_rule filtra
            # el frontmatter 'applies_to: [globs]' — sin frontmatter, devuelve
            # el archivo completo (mismo comportamiento de siempre); archivo
            # inexistente -> None (se omite, igual que el FileNotFoundError
            # que reemplaza).
            content = load_conditional_rule(abs_path, context_files=context_files or [])
            if content is None:
                continue
            # Truncar a 3000 chars para no saturar el contexto del modelo
            if len(content) > 3000:
                content = content[:3000] + "\n... [truncado]"
            parts.append(f"### {rel_path}\n{content}")
        if not parts:
            return ""
        return "## Contexto institucional del proyecto\n\n" + "\n\n".join(parts)

    def _run_council(self, task: str, context: str) -> str | None:
        """Convoca el Cónclave para decisiones arquitectónicas. Devuelve síntesis o None si no procede."""
        try:
            from atlas.core.deliberation_council import (
                LessonSynthesisRecorder, convene_for_decision,
            )
            from atlas.router.cascade import Difficulty
            recorder = (
                LessonSynthesisRecorder(self._lesson_store)
                if self._lesson_store is not None else None
            )
            evidence = convene_for_decision(
                decision=task,
                context=context[:2000],  # limitar contexto para el Cónclave
                difficulty=Difficulty.HARD,
                risk="modificación de código de producción",
                irreversible=False,
                synthesis_recorder=recorder,
            )
            if evidence is None:
                return None
            # Extraer síntesis de las objeciones
            checks_summary = "; ".join(
                f"{c.name}: {c.detail}" for c in evidence.checks if c.detail
            )
            return f"Veredicto: {evidence.verdict.value}. {checks_summary}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cónclave no disponible: %s — continuando sin deliberación", exc)
            return None

    @staticmethod
    def _reindent_tolerant_match(
        original: str, search_text: str, replace_text: str
    ) -> str | None:
        """Fallback de match tolerante a reindentado (técnica Aider, cascada tras
        match exacto). Compara línea a línea ignorando el whitespace inicial; si
        hay EXACTAMENTE una ventana que calza, reaplica el delta de indentación
        real del archivo sobre replace_text (para no romper el estilo existente).
        Fail-closed: 0 o >1 coincidencias → None (no aplicar a ciegas).
        """
        search_lines = search_text.splitlines()
        if not search_lines:
            return None
        original_lines = original.splitlines(keepends=True)
        stripped_search = [ln.strip() for ln in search_lines]

        matches: list[int] = []
        n = len(search_lines)
        for i in range(len(original_lines) - n + 1):
            window = original_lines[i : i + n]
            if [ln.rstrip("\n").strip() for ln in window] == stripped_search:
                matches.append(i)
        if len(matches) != 1:
            return None

        start = matches[0]
        window = original_lines[start : start + n]
        # Delta de indentación: la del primer línea real de la ventana en disco.
        first_real = window[0]
        real_indent = first_real[: len(first_real) - len(first_real.lstrip(" "))]
        replace_lines = replace_text.splitlines()
        reindented = [
            (real_indent + ln.lstrip(" ")) if ln.strip() else ln
            for ln in replace_lines
        ]
        newline = "\n" if window[0].endswith("\n") else ""
        replacement_block = "\n".join(reindented) + (newline if reindented else "")

        return (
            "".join(original_lines[:start])
            + replacement_block
            + "".join(original_lines[start + n :])
        )

    @staticmethod
    def _is_valid_syntax(rel_path: str, content: str) -> bool:
        """Linter bloqueante (técnica #1, patrón SWE-agent str_replace_editor):
        antes de aceptar una edición Python, verifica que el resultado siga
        siendo sintácticamente válido. Archivos no-.py no se verifican (True)."""
        if not rel_path.endswith(".py"):
            return True
        try:
            ast.parse(content)
            return True
        except SyntaxError:
            return False

    def _write_with_lint_gate(
        self, abs_path: Path, rel_path: str, new_content: str
    ) -> bool:
        """Escribe *new_content* solo si pasa el linter bloqueante; si no,
        NO escribe (auto-revierte esta edición puntual) y loggea. Devuelve si
        se escribió."""
        if not self._is_valid_syntax(rel_path, new_content):
            logger.warning(
                "AtlasCoder: edición de %s produce SyntaxError — no aplicada "
                "(linter bloqueante, patrón SWE-agent).", rel_path,
            )
            # Técnica #15 (Aider): el rechazo se acumula para retroalimentarlo
            # al modelo en la siguiente iteración, no solo loggearlo.
            if not hasattr(self, "_lint_rejections"):
                self._lint_rejections = []
            self._lint_rejections.append(
                f"La edición a {rel_path} fue RECHAZADA: produce SyntaxError. "
                "Revisa paréntesis/comillas/indentación y reenvía la edición corregida."
            )
            return False
        abs_path.write_text(new_content, encoding="utf-8")
        return True

    def _restore_snapshot(self, snapshot: dict[str, str | None]) -> None:
        """Restaura context_files a su contenido pre-run (checkpoint shadow-git)."""
        for rel_path, content in snapshot.items():
            abs_path = self._repo_root / rel_path
            if content is None:
                abs_path.unlink(missing_ok=True)
            else:
                abs_path.write_text(content, encoding="utf-8")

    def _sweep_stale_sandboxes(self, *, max_age_seconds: float = 3600.0) -> None:
        """Barre sandboxes huérfanos de ejecuciones anteriores muertas por
        SIGKILL/crash (finally nunca corre en ese caso — mismo patrón que el
        fix de worktree leak: limpieza al entrar, no solo al salir). Encontrado
        2026-07-09: 7 sandboxes huérfanos (~487M c/u) llenaron el tmpfs de 4G
        de /tmp y contribuyeron a cierres de sesión de escritorio repetidos."""
        import time

        base = Path(tempfile.gettempdir())
        now = time.time()
        try:
            for entry in base.glob("atlas_coder_sandbox_*"):
                try:
                    if now - entry.stat().st_mtime > max_age_seconds:
                        shutil.rmtree(entry, ignore_errors=True)
                except OSError:
                    continue
        except OSError:
            pass

    def _create_sandbox(self) -> Path:
        """Técnica #6: copia repo_root a un directorio temporal aislado, sin
        directorios pesados/irrelevantes. El bucle de code() opera sobre esta
        copia hasta que el resultado final se conoce."""
        self._sweep_stale_sandboxes()
        sandbox_dir = Path(tempfile.mkdtemp(prefix="atlas_coder_sandbox_"))
        shutil.copytree(
            self._repo_root, sandbox_dir,
            ignore=shutil.ignore_patterns(
                ".git", ".venv", ".venv-redteam", "__pycache__",
                ".mypy_cache", ".pytest_cache", "node_modules",
                ".claude", ".cursor", "data", "workspace", "*.pyc",
            ),
            dirs_exist_ok=True,
        )
        return sandbox_dir

    def _cleanup_sandbox(self, sandbox_dir: Path) -> None:
        """Borra el directorio sandbox. Best-effort: nunca lanza excepción."""
        try:
            shutil.rmtree(sandbox_dir, ignore_errors=True)
        except Exception:  # noqa: BLE001 — limpieza nunca debe romper el flujo
            pass

    def _sync_sandbox_back(
        self, sandbox_dir: Path, real_repo_root: Path, files_changed: list[str],
    ) -> None:
        """Sincroniza SOLO los archivos de *files_changed* desde el sandbox al
        repo real. Solo se llama tras success=True. Un archivo ausente en el
        sandbox significa que se borró ahí (DeleteFileOp) — se borra también
        en el repo real."""
        for rel_path in files_changed:
            src = sandbox_dir / rel_path
            dst = real_repo_root / rel_path
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            else:
                dst.unlink(missing_ok=True)

    def _build_files_section(self, context_files: list[str]) -> str:
        parts: list[str] = []
        for rel_path in context_files:
            abs_path = self._repo_root / rel_path
            try:
                content = abs_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                content = ""
            parts.append(f"### {rel_path}\n```\n{content}\n```")
        return "\n\n".join(parts)

    def _try_apply_model_fallback(
        self, search_text: str, replace_text: str, context_files: list[str]
    ) -> str | None:
        """Técnica #4 (apply-model separado, patrón Cursor/Continue/Aider
        architect — CUATRO fuentes independientes lo validan): cuando un
        bloque SEARCH falla en aplicarse mecánicamente, delega en un modelo
        barato con rol "apply" que reescribe el archivo completo dada la
        intención del cambio, en vez de gastar otra iteración completa del
        modelo caro. Acotado a UN solo context_file (evita explosión
        combinatoria de llamadas si hay ambigüedad sobre a cuál archivo
        pertenece el bloque fallido). Devuelve el archivo modificado o None.
        """
        if len(context_files) != 1:
            return None
        rel_path = context_files[0]
        abs_path = self._repo_root / rel_path
        try:
            original = abs_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

        prompt = _APPLY_MODEL_PROMPT.format(
            rel_path=rel_path, original=original,
            search_text=search_text, replace_text=replace_text,
        )
        request = InferenceRequest(
            prompt=prompt, level=InferenceLevel.L1,
            task_id="atlas_coder_apply", max_tokens=4096,
        )
        response = self._hub.infer_for_role("apply", request)
        if not response.success:
            return None

        new_content = _strip_fences(response.text).strip("\n") + "\n"
        if new_content == original:
            return None  # el modelo apply no hizo ningún cambio real
        if not self._write_with_lint_gate(abs_path, rel_path, new_content):
            return None
        return rel_path

    def _apply_edits(
        self, model_text: str, context_files: list[str], *, use_apply_model: bool = False,
    ) -> list[str]:
        """
        Parsea todos los bloques SEARCH/REPLACE de *model_text* y los aplica
        a los archivos de *context_files*.

        Devuelve la lista de archivos que fueron modificados.
        """
        blocks = _SEARCH_REPLACE_RE.findall(_strip_fences(model_text))
        changed: list[str] = []
        self._last_blocks_parsed = len(blocks)
        self._last_blocks_applied = 0

        for search_text, replace_text in blocks:
            if search_text == "":
                # Bloque de creación de archivo nuevo: no hay forma de saber
                # a qué archivo pertenece sin más contexto; se ignora con warning.
                logger.warning(
                    "AtlasCoder: bloque SEARCH vacío (creación de archivo) "
                    "ignorado — no se puede determinar el destino."
                )
                continue

            applied = False
            rejected = False
            for rel_path in context_files:
                abs_path = self._repo_root / rel_path
                try:
                    original = abs_path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    continue

                count = original.count(search_text)
                if count == 0:
                    tolerant = self._reindent_tolerant_match(
                        original, search_text, replace_text
                    )
                    if tolerant is not None:
                        if self._write_with_lint_gate(abs_path, rel_path, tolerant):
                            if rel_path not in changed:
                                changed.append(rel_path)
                            applied = True
                            self._last_blocks_applied += 1
                        else:
                            rejected = True  # encontrado pero rechazado (linter); no es "not found"
                        break
                    continue
                if count > 1:
                    # Verificación pre-apply (lección SWE-agent str_replace_editor):
                    # un match no-único es tan peligroso como uno ausente — podría
                    # aplicarse al bloque equivocado. Fail-closed: no aplicar.
                    rejected = True
                    logger.warning(
                        "AtlasCoder: bloque SEARCH ambiguo (%d ocurrencias en %s) "
                        "— no aplicado (fail-closed, evita editar el bloque "
                        "equivocado).\nSEARCH=%r",
                        count, rel_path, search_text[:120],
                    )
                    break

                new_content = original.replace(search_text, replace_text, 1)
                if self._write_with_lint_gate(abs_path, rel_path, new_content):
                    if rel_path not in changed:
                        changed.append(rel_path)
                    applied = True
                    self._last_blocks_applied += 1
                else:
                    rejected = True  # encontrado pero rechazado (linter); no es "not found"
                break

            if not applied and not rejected:
                fallback_path = None
                if use_apply_model:
                    fallback_path = self._try_apply_model_fallback(
                        search_text, replace_text, context_files
                    )
                if fallback_path is not None:
                    if fallback_path not in changed:
                        changed.append(fallback_path)
                    self._last_blocks_applied += 1
                else:
                    logger.warning(
                        "AtlasCoder: bloque SEARCH no encontrado en ningún archivo "
                        "de contexto — bloque ignorado.\nSEARCH=%r", search_text[:120]
                    )

        return changed

        for search_text, replace_text in blocks:
            if search_text == "":
                # Bloque de creación de archivo nuevo: no hay forma de saber
                # a qué archivo pertenece sin más contexto; se ignora con warning.
                logger.warning(
                    "AtlasCoder: bloque SEARCH vacío (creación de archivo) "
                    "ignorado — no se puede determinar el destino."
                )
                continue

            applied = False
            rejected = False
            for rel_path in context_files:
                abs_path = self._repo_root / rel_path
                try:
                    original = abs_path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    continue

                count = original.count(search_text)
                if count == 0:
                    tolerant = self._reindent_tolerant_match(
                        original, search_text, replace_text
                    )
                    if tolerant is not None:
                        if self._write_with_lint_gate(abs_path, rel_path, tolerant):
                            if rel_path not in changed:
                                changed.append(rel_path)
                            applied = True
                        else:
                            rejected = True  # encontrado pero rechazado (linter); no es "not found"
                        break
                    continue
                if count > 1:
                    # Verificación pre-apply (lección SWE-agent str_replace_editor):
                    # un match no-único es tan peligroso como uno ausente — podría
                    # aplicarse al bloque equivocado. Fail-closed: no aplicar.
                    rejected = True
                    logger.warning(
                        "AtlasCoder: bloque SEARCH ambiguo (%d ocurrencias en %s) "
                        "— no aplicado (fail-closed, evita editar el bloque "
                        "equivocado).\nSEARCH=%r",
                        count, rel_path, search_text[:120],
                    )
                    break

                new_content = original.replace(search_text, replace_text, 1)
                if self._write_with_lint_gate(abs_path, rel_path, new_content):
                    if rel_path not in changed:
                        changed.append(rel_path)
                    applied = True
                else:
                    rejected = True  # encontrado pero rechazado (linter); no es "not found"
                break

            if not applied and not rejected:
                fallback_path = None
                if use_apply_model:
                    fallback_path = self._try_apply_model_fallback(
                        search_text, replace_text, context_files
                    )
                if fallback_path is not None:
                    if fallback_path not in changed:
                        changed.append(fallback_path)
                else:
                    logger.warning(
                        "AtlasCoder: bloque SEARCH no encontrado en ningún archivo "
                        "de contexto — bloque ignorado.\nSEARCH=%r", search_text[:120]
                    )

        return changed

    def _apply_patch_format_edits(
        self, model_text: str, context_files: list[str]
    ) -> list[str]:
        """Técnica #18: parsea y aplica el envelope apply_patch (Add/Delete/
        Update File). Reutiliza las mismas protecciones que _apply_edits:
        rutas protegidas fail-closed, linter bloqueante en .py, match único
        fail-closed por hunk (vía patch_format.apply_update_hunk).

        Devuelve la lista de archivos modificados (igual contrato que
        _apply_edits, para que el stuck-detector y el checkpoint funcionen
        igual sin importar el formato de edición.
        """
        ops = parse_patch_envelope(_strip_fences(model_text))
        changed: list[str] = []

        for op in ops:
            if _is_protected_path(op.path):
                logger.warning(
                    "AtlasCoder: operación sobre ruta protegida %r ignorada "
                    "(fail-closed).", op.path,
                )
                continue

            if isinstance(op, AddFileOp):
                abs_path = self._repo_root / op.path
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                if self._write_with_lint_gate(abs_path, op.path, op.content):
                    if op.path not in changed:
                        changed.append(op.path)

            elif isinstance(op, DeleteFileOp):
                abs_path = self._repo_root / op.path
                if abs_path.is_file():
                    abs_path.unlink()
                    if op.path not in changed:
                        changed.append(op.path)
                else:
                    logger.warning(
                        "AtlasCoder: Delete File sobre ruta inexistente %r "
                        "ignorado.", op.path,
                    )

            elif isinstance(op, UpdateFileOp):
                if op.move_to is not None and _is_protected_path(op.move_to):
                    logger.warning(
                        "AtlasCoder: Move to ruta protegida %r ignorado "
                        "(fail-closed).", op.move_to,
                    )
                    continue
                abs_path = self._repo_root / op.path
                try:
                    content = abs_path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    logger.warning(
                        "AtlasCoder: Update File sobre ruta inexistente %r "
                        "ignorado.", op.path,
                    )
                    continue

                any_hunk_applied = False
                for hunk in op.hunks:
                    new_content = apply_update_hunk(content, hunk)
                    if new_content is None:
                        logger.warning(
                            "AtlasCoder: hunk no aplicado en %r (ancla no "
                            "encontrada o ambigua, fail-closed).", op.path,
                        )
                        continue
                    content = new_content
                    any_hunk_applied = True

                if not any_hunk_applied:
                    continue

                target_path = op.move_to if op.move_to is not None else op.path
                target_abs = self._repo_root / target_path
                target_abs.parent.mkdir(parents=True, exist_ok=True)
                if self._write_with_lint_gate(target_abs, target_path, content):
                    if op.move_to is not None and op.move_to != op.path:
                        abs_path.unlink(missing_ok=True)
                        if op.path in changed:
                            changed.remove(op.path)
                    if target_path not in changed:
                        changed.append(target_path)

        return changed
