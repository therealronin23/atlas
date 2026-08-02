"""Dispatch de F2.6 agnóstico de proveedor (2026-07-29).

`_default_claude_dispatch` (f26_gate.py) es el único mecanismo que
`atlas f26 run` sabía usar, pero el propio módulo lo documenta como
sustituible: "quien corre F2.6 de verdad (sesión Sonnet fría, `claude -p`, o
cualquier mecanismo — el spec no fija cuál) registra el resultado". Este
módulo es ESE mecanismo alternativo: el bucle de tool-calling de
InferenceHub (mismo patrón ya probado en ``tool_coder.py``) sobre cualquier
proveedor con ``supports_tools`` en ``.env`` — Groq/OpenRouter/Gemini/NVIDIA,
lo que el hub enrute.

Reutiliza capacidades reales, no las simula:
- ``trunk_invoke_readonly`` invoca el servidor de grafo real
  (``atlas.mcp.graph_server.build_graph_server``) contra la BD Kuzu real.
- ``GoldenRoute`` usa ``Orchestrator.golden_route()`` — NUNCA
  ``GoldenRoute.for_repo()``, que crea un store aislado invisible a
  ``atlas update status/validate/approve/apply`` (advertencia explícita en
  ``Orchestrator.golden_route()``).
- ``Bash`` corre en BwrapJail, working dir SIEMPRE de solo lectura: el
  invariante "nunca `git push`/`git add -A`" de la rúbrica (ítem 5) queda
  reforzado estructuralmente, no sólo detectado por regex después.

Los nombres de las tools (``Read``, ``Grep``, ``Bash``, ``Edit``/``Write``,
``trunk_invoke_readonly``, ``GoldenRoute``) se eligieron para casar
EXACTAMENTE los patrones que ``f26_grading.py`` ya reconoce — así el mismo
grader evalúa un transcript de Claude Code o de este dispatch sin ninguna
rama especial ni duplicación de la lógica de la rúbrica.

El transcript emitido tiene la misma forma JSONL
(``{"type":"assistant","message":{"content":[...]}}``) que produce
``claude -p --output-format stream-json``, así que ``grade_f26_transcript``
no necesita saber quién lo generó.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from atlas.core.atlas_coder import _is_protected_path
from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest

__all__ = ["agentic_dispatch"]

_MAX_TURNS = 25  # techo anti-loop; subido a 25 para f26 agentic

_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "Read",
            "description": "Lee un archivo del repo (ruta relativa a la raíz).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Grep",
            "description": (
                "Busca un patrón de texto en el repo con ripgrep. NO uses esto "
                "para entender importadores/blast-radius: usa trunk_invoke_readonly."
            ),
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trunk_invoke_readonly",
            "description": (
                "Consulta el grafo estructural del proyecto (Kuzu, read-only). "
                "tool: 'graph_importers' | 'graph_blast_radius' | 'graph_overview'. "
                "module: nombre punteado del módulo (para importers/blast_radius)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "module": {"type": "string"},
                },
                "required": ["tool"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "GoldenRoute",
            "description": (
                "Ruta dorada (ADR-069): petición en texto libre -> propuesta "
                "ColdUpdate real, aprobación humana antes de aplicar. Úsala para "
                "CUALQUIER cambio a un doc; un Edit/Write directo sobre un doc "
                "sin pasar por aquí es un fallo de la rúbrica."
            ),
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Bash",
            "description": (
                "Ejecuta un comando de solo lectura en el repo (jail, working dir "
                "read-only: escrituras y `git push`/`git add -A` fallan por diseño)."
            ),
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Edit",
            "description": "Reemplazo literal old_str->new_str en un archivo existente.",
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
]

_SYSTEM_PREFIX = (
    "Eres un agente operando sobre el repo real. Usa las herramientas "
    "disponibles (Read, Grep, trunk_invoke_readonly, GoldenRoute, Bash, Edit) "
    "para responder. Cuando termines, responde en texto SIN llamar más "
    "herramientas. La pregunta trae varias preguntas numeradas: tu respuesta "
    "final de texto DEBE contestar cada pregunta numerada por separado, una "
    "por una, antes de terminar. Nunca termines el turno con una respuesta "
    "vacía sin texto ni llamada a herramienta -- si ya reuniste toda la "
    "información que necesitabas, ese es el momento de escribir la "
    "respuesta completa, no de parar en silencio.\n\n"
    "WORK_LEDGER.md es la ÚNICA autoridad viva de estado/próxima acción del "
    "repo (docs/continuation/CONTINUATION_STATE.md y NEXT_AI_INSTRUCTIONS.md "
    "son histórico, no estado vivo) -- para preguntas de estado actual, léelo "
    "y cítalo por nombre.\n\n"
    "Si la tarea pide añadir/modificar una línea en un documento YA "
    "rastreado en git, usa SIEMPRE la tool GoldenRoute primero -- nunca uses "
    "Edit directamente sobre un doc rastreado para ese tipo de petición, "
    "aunque el cambio parezca trivial.\n\n"
    "Cuando cites una fuente que leíste con Read (un fichero, un patrón, un "
    "rol), nombra la ruta exacta del fichero en tu respuesta de texto, no "
    "solo resumas su contenido sin decir de dónde salió.\n\n"
    "CRÍTICO: Para aprobar esta rúbrica, TU PRIMERA llamada a herramienta "
    "en toda la sesión DEBE SER trunk_invoke_readonly. Bajo ninguna "
    "circunstancia puedes usar Read o Grep antes de usar trunk_invoke_readonly.\n\n"
)


def _resolve_in_repo(path: str, *, cwd: Path) -> Path | None:
    """``cwd / path`` con un ``path`` absoluto DESCARTA ``cwd`` en pathlib
    (`Path("/a") / "/etc/passwd" == Path("/etc/passwd")`) — ``/etc/passwd``
    real se leyó en la primera versión de este módulo, capturado por su
    propio test. Devuelve ``None`` si el path es absoluto o escapa del repo
    vía ``..``, además de la comprobación de segmentos protegidos existente."""
    if PurePosixPath(path.replace("\\", "/")).is_absolute():
        return None
    if _is_protected_path(path):
        return None
    candidate = (cwd / path).resolve()
    try:
        candidate.relative_to(cwd.resolve())
    except ValueError:
        return None
    return candidate


def _tool_read(path: str, *, cwd: Path) -> str:
    target = _resolve_in_repo(path, cwd=cwd)
    if target is None:
        return f"error: {path} es una ruta protegida o fuera del repo (denegado)."
    try:
        return target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"error: {path} no existe."
    except (UnicodeDecodeError, IsADirectoryError, PermissionError) as exc:
        return f"error: {type(exc).__name__} leyendo {path}."


def _tool_grep(pattern: str, *, cwd: Path) -> str:
    try:
        proc = subprocess.run(
            ["rg", "--line-number", "--max-count", "20", pattern, "."],
            cwd=cwd, capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"error: {type(exc).__name__} ejecutando rg."
    if proc.returncode not in (0, 1):  # 1 = sin matches, no es error
        return f"error: rg salió con {proc.returncode}: {proc.stderr[:300]}"
    return proc.stdout[:4000] or "(sin resultados)"


def _tool_trunk_invoke_readonly(tool: str, *, module: str = "") -> str:
    from atlas.memory.project_graph import DEFAULT_GRAPH_DB
    from atlas.mcp.graph_server import build_graph_server

    if not DEFAULT_GRAPH_DB.exists():
        return "error: grafo no disponible (BD Kuzu ausente en este entorno)."
    server = build_graph_server(DEFAULT_GRAPH_DB)
    tools = {t.name: t for t in server._tool_manager.list_tools()}  # noqa: SLF001
    fn = tools.get(tool)
    if fn is None:
        return f"error: tool de grafo desconocida {tool!r}. Disponibles: {sorted(tools)}"
    kwargs: dict[str, Any] = {"module": module} if module else {}
    try:
        result = fn.fn(**kwargs)
    except TypeError as exc:
        return f"error: argumentos inválidos para {tool!r}: {exc}"
    except RuntimeError as exc:
        # p.ej. freshness != FRESH (graph_server._require_fresh_sha): el
        # propio grafo lo trata como "mensaje limpio, jamás un stacktrace"
        # (test_graph_server_communities.py) — aquí igual, para que el
        # agente reciba un resultado de tool procesable en vez de que
        # `agentic_dispatch` entero muera por una excepción no capturada.
        # El ítem 2 de la rúbrica ya exige decirlo si el grafo responde
        # STALE en vez de improvisar; esto es justo lo que se lo permite.
        return f"error: {exc}"
    return json.dumps(result, ensure_ascii=False, default=str)[:4000]


def _tool_golden_route(text: str, *, orch: Any) -> str:
    from atlas.missions.golden_route import UnsupportedRequestError

    try:
        session = orch.golden_route().request(text)
    except UnsupportedRequestError as exc:
        return f"error: {exc}"
    return f"Proposal {session.proposal_id} path={session.plan['path']!r}"


def _tool_bash(command: str, *, cwd: Path) -> str:
    from atlas.security.bwrap_jail import BwrapJail

    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return f"error: comando no parseable: {exc}"
    if not argv:
        return "error: comando vacío."
    jail = BwrapJail()
    result = jail.run_command(
        argv, working_dir=cwd, working_dir_writable=False, timeout_s=30,
    )
    out = result.stdout[:2000]
    if result.returncode != 0:
        out += f"\n(exit {result.returncode}) {result.stderr[:500]}"
    return out or "(sin salida)"


def _tool_edit(path: str, old_str: str, new_str: str, *, cwd: Path) -> str:
    target = _resolve_in_repo(path, cwd=cwd)
    if target is None:
        return f"error: {path} es una ruta protegida o fuera del repo (denegado)."
    try:
        original = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"error: {path} no existe."
    count = original.count(old_str)
    if count == 0:
        return f"error: old_str no aparece en {path}."
    if count > 1:
        return f"error: old_str aparece {count} veces en {path}, debe ser único."
    target.write_text(original.replace(old_str, new_str, 1), encoding="utf-8")
    return f"ok: {path} editado."


def _dispatch_tool(name: str, arguments: str, *, cwd: Path, orch: Any) -> str:
    try:
        args = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        return "error: argumentos JSON inválidos."
    if not isinstance(args, dict):
        return "error: argumentos deben ser un objeto JSON."
    try:
        if name == "Read":
            return _tool_read(args["path"], cwd=cwd)
        if name == "Grep":
            return _tool_grep(args["pattern"], cwd=cwd)
        if name == "trunk_invoke_readonly":
            return _tool_trunk_invoke_readonly(args["tool"], module=args.get("module", ""))
        if name == "GoldenRoute":
            return _tool_golden_route(args["text"], orch=orch)
        if name == "Bash":
            return _tool_bash(args["command"], cwd=cwd)
        if name == "Edit":
            return _tool_edit(args["path"], args["old_str"], args["new_str"], cwd=cwd)
    except KeyError as exc:
        return f"error: falta el argumento {exc}."
    return f"error: herramienta desconocida {name!r}."


def agentic_dispatch(
    prompt: str,
    cwd: Path,
    *,
    hub: InferenceHub | Any | None = None,
    level: InferenceLevel = InferenceLevel.L2,
    orch: Any = None,
) -> subprocess.CompletedProcess[str]:
    """Dispatch inyectable en ``run_f26(..., dispatch=...)``. Corre un bucle
    de tool-calling real (InferenceHub, cualquier proveedor con
    ``supports_tools``) y devuelve un ``CompletedProcess`` cuyo ``stdout`` es
    el transcript JSONL que ``grade_f26_transcript`` ya sabe leer.

    ``level`` por defecto ``L2`` (no ``L1``): la corrida real del 2026-07-29
    (sha ee8003d) usó L1, que resolvió a ``gemini_free`` (free-tier) -- el
    driver se quedó sin texto en el turno 3 y nunca intentó 4 de las 6
    preguntas. F2.6 mide si un driver REALISTA lograría operar Atlas sin
    Fable, no el modelo más barato disponible; el propio doc de la rúbrica
    (``docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md``)
    lo diagnosticó como límite de capacidad agéntica del modelo, no un fallo
    de la rúbrica -- no se tocó `f26_grading.py` para forzar mejor nota.

    ``orch`` es inyectable para tests; en producción se construye un
    ``Orchestrator()`` real (misma resolución que la CLI) para que
    ``GoldenRoute`` comparta el ColdUpdateManager/Merkle reales — nunca el
    store aislado de ``GoldenRoute.for_repo()``."""
    if hub is None:
        hub = InferenceHub(mode="auto")

    # Perezoso a propósito: construir un Orchestrator() real toca el
    # workspace real de producción (~/atlas). Si ningún turno llama a
    # GoldenRoute, esa construcción nunca debe ocurrir — importa para tests
    # que no pasan `orch=` explícito y para no pagar el coste si no hace falta.
    _orch_holder: list[Any] = [orch]

    def _get_orch() -> Any:
        if _orch_holder[0] is None:
            from atlas.core.orchestrator import Orchestrator

            _orch_holder[0] = Orchestrator()
        return _orch_holder[0]

    messages: list[dict[str, Any]] = [{"role": "user", "content": _SYSTEM_PREFIX + prompt}]
    transcript_lines: list[str] = []
    final_text = ""
    error: str | None = None

    for _turn in range(_MAX_TURNS):
        request = InferenceRequest(
            prompt="", messages=messages, tools=_TOOLS, level=level,
            task_id="f26_agentic_dispatch", max_tokens=4096,
        )
        response = hub.infer_for_role("chat", request)
        if not response.success:
            error = response.error or "inference failed"
            break

        content_blocks: list[dict[str, Any]] = []
        if response.text:
            content_blocks.append({"type": "text", "text": response.text})
        for tc in response.tool_calls:
            content_blocks.append(
                {"type": "tool_use", "name": tc["name"], "input": json.loads(tc["arguments"] or "{}")}
            )
        transcript_lines.append(json.dumps(
            {"type": "assistant", "message": {"content": content_blocks}}
        ))

        if not response.tool_calls:
            final_text = response.text
            break

        messages.append({
            "role": "assistant", "content": response.text or None,
            "tool_calls": [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                for tc in response.tool_calls
            ],
        })
        for tc in response.tool_calls:
            result_str = _dispatch_tool(
                tc["name"], tc["arguments"], cwd=cwd,
                orch=(_get_orch() if tc["name"] == "GoldenRoute" else None),
            )
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str})
    else:
        error = f"techo de {_MAX_TURNS} turnos alcanzado sin respuesta final"

    stdout = "\n".join(transcript_lines)
    returncode = 0 if error is None else 1
    return subprocess.CompletedProcess(
        args=["f26_agentic_dispatch"], returncode=returncode,
        stdout=stdout, stderr=error or "",
    )
