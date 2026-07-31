"""Detector de módulos dormidos por resolución REAL de imports (2026-07-31).

Sustituye la heurística de texto de ``scripts/sanitation_audit.py``, que
tenía un punto ciego demostrable. Su patrón era::

    import .*\\bmod\\b | from .*\\bmod\\b import | \\.mod\\b

La tercera rama convierte cualquier mención textual del nombre —un acceso a
atributo ``self.reproduction``, una cadena ``"diagnostics"``, un comentario—
en un "importador". Es un falso NEGATIVO, el sentido peligroso para un
radar: calla en vez de gritar. En este repo pasaba de verdad con
``engineering/reproduction.py`` (489 loc) y ``engineering/diagnostics.py``
(391 loc), los dos módulos dormidos más grandes, invisibles al radar porque
esas palabras aparecen como texto en ``logging/merkle_logger.py`` y
``core/doctor.py``.

Aquí los imports se resuelven con ``ast``: sólo cuentan nodos ``Import`` /
``ImportFrom`` reales. Tres decisiones que el regex no podía tomar:

- **Los tests NO son callers de producción.** Regla dura adoptada tras el
  fallo de ADC-WO-108: ``hypotheses.py`` y ``correction.py`` tenían tests en
  verde y cero cableado. Un módulo importado sólo desde ``tests/`` sigue
  dormido.
- **Los imports diferidos dentro de funciones SÍ cuentan.** ``ast.walk``
  los ve; un escáner "a nivel de módulo" no. Es el punto ciego que la tabla
  de clasificados documenta para ``immunity/live_loop.py`` (ADR-074).
- **``python -m atlas.x.y`` desde un hook/shell SÍ cuenta.** Es un caller de
  producción real e invisible a cualquier escaneo de imports — el caso de
  ``engineering/impacted_tests.py`` desde ``.githooks/pre-commit``.

Mismo principio que ``ecosystem_drift.py`` y ``component_wiring_drift.py``:
determinista, barato, nunca LLM/red, la lógica vive aquí con TDD real y
``sanitation_audit.py`` sólo importa y envuelve fail-open.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SKIP_DIRS = frozenset({
    ".git", ".venv", ".venv-redteam", ".venv-scraping", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "_graveyard", "graphify-out",
})

# 0 importadores estáticos es ESPERADO aquí: se invocan por CLI/ASGI/import
# de paquete, no por otro módulo.
ENTRYPOINT_STEMS = frozenset({
    "cli", "__main__", "__init__", "conftest", "app", "server", "asgi", "run",
})

# Dónde puede vivir un caller de producción. `tests/` está fuera A PROPÓSITO.
IMPORT_SCAN_ROOTS: tuple[str, ...] = ("src", "scripts")

# Ficheros NO-Python donde un `python -m atlas.x.y` es un caller real.
# Acotado a propósito: un `python -m ...` citado en `docs/` es documentación,
# no un caller, y contarlo reintroduciría falsos negativos por texto.
COMMAND_SCAN_ROOTS: tuple[str, ...] = (".githooks", "scripts", ".github", "Makefile")

_DASH_M = re.compile(r"-m\s+(atlas(?:\.[A-Za-z_][A-Za-z0-9_]*)+)")
_DOTTED = re.compile(r"^atlas(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """``id()`` de cada Constant que sea docstring. Documentar un módulo no
    es llamarlo: ``tools/computer_use/desktop_planner.py`` cita
    ``atlas.mcp.adapter_registry`` en su docstring y no lo usa."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            out.add(id(body[0].value))
    return out


def _dynamic_targets(tree: ast.AST) -> set[str]:
    """Módulos nombrados como CADENA en código de producción: registros que
    se spawnean con ``[exe, "-m", spec.module]`` (``mcp/trunk_server.py:86``),
    el mapa nativo de ``security/sentinel_gate.py``, ``import_module(...)``.

    Sólo cuenta la ruta punteada COMPLETA (``atlas.mcp.trunk_server``), nunca
    el stem suelto (``trunk_server``). Esa distinción es toda la diferencia
    con el regex viejo: ``"reproduction"`` suelto en una lista de tipos no
    convierte a ``engineering/reproduction.py`` en cableado."""
    skip = _docstring_nodes(tree)
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in skip:
            continue
        value = node.value.strip()
        if _DOTTED.match(value):
            out.add(value)
        for match in _DASH_M.finditer(node.value):
            out.add(match.group(1))
    return out


def _module_name(path: Path, src_root: Path) -> str:
    """``src/atlas/fabric/policy.py`` -> ``atlas.fabric.policy``."""
    rel = path.relative_to(src_root).with_suffix("")
    return ".".join(rel.parts)


def _package_of(module: str) -> str:
    """Paquete contenedor de un módulo, para resolver imports relativos.
    ``atlas.engineering.other`` -> ``atlas.engineering``. Para un
    ``__init__``, el propio paquete."""
    parts = module.split(".")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts[:-1])


def _resolve_relative(package: str, level: int, module: str | None) -> str | None:
    """``from ..review import X`` dentro de ``atlas.engineering.deep`` ->
    ``atlas.engineering.review``. ``None`` si el nivel sube por encima de la
    raíz (import roto; no inventamos un objetivo)."""
    parts = package.split(".") if package else []
    drop = level - 1
    if drop > len(parts):
        return None
    base = parts[: len(parts) - drop] if drop else parts
    tail = module.split(".") if module else []
    resolved = base + tail
    return ".".join(resolved) if resolved else None


def _imported_targets(tree: ast.AST, package: str) -> set[str]:
    """Todo nombre de módulo que este AST importa de verdad.

    Para ``from a.b import c`` se emiten ``a.b`` Y ``a.b.c``: sin mirar el
    disco no se sabe si ``c`` es un submódulo o un símbolo. El filtro contra
    el conjunto de módulos reales lo resuelve después, sin adivinar aquí."""
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = _resolve_relative(package, node.level, node.module)
            else:
                base = node.module
            if base is None:
                continue
            targets.add(base)
            for alias in node.names:
                if alias.name != "*":
                    targets.add(f"{base}.{alias.name}")
    return targets


def _iter_files(root: Path, suffix: str | None = None) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if set(path.parts) & SKIP_DIRS:
            continue
        if suffix is not None and path.suffix != suffix:
            continue
        out.append(path)
    return out


def importers_by_module(
    repo_root: Path,
    *,
    import_roots: tuple[str, ...] = IMPORT_SCAN_ROOTS,
    command_roots: tuple[str, ...] = COMMAND_SCAN_ROOTS,
) -> dict[str, set[str]]:
    """Índice ``módulo -> {ficheros que lo importan de verdad}``.

    Fail-honesto: un fichero que no parsea se salta como FUENTE de imports
    (no puede afirmar nada sobre él) pero no rompe el pase ni desaparece del
    censo de módulos."""
    src_root = repo_root / "src"
    index: dict[str, set[str]] = {}

    for root_name in import_roots:
        for path in _iter_files(repo_root / root_name, suffix=".py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, SyntaxError, ValueError):
                continue
            if path.is_relative_to(src_root):
                package = _package_of(_module_name(path, src_root))
            else:
                package = ""
            rel = str(path.relative_to(repo_root))
            for target in _imported_targets(tree, package) | _dynamic_targets(tree):
                index.setdefault(target, set()).add(rel)

    for root_name in command_roots:
        for path in _iter_files(repo_root / root_name):
            if path.suffix == ".py":
                continue  # ya cubierto por el pase de imports
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rel = str(path.relative_to(repo_root))
            for match in _DASH_M.finditer(text):
                index.setdefault(match.group(1), set()).add(rel)

    return index


def dormant_modules(
    repo_root: Path,
    *,
    classified: dict[str, str] | None = None,
    package_root: str = "atlas",
) -> list[str]:
    """Módulos de ``src/<package_root>/`` sin un solo caller de producción.

    Devuelve rutas relativas al repo, ordenadas. Nunca lanza: si el árbol no
    existe, la respuesta honesta es una lista vacía, no un error."""
    src_root = repo_root / "src"
    package_dir = src_root / package_root
    if not package_dir.is_dir():
        return []

    classified = classified or {}
    index = importers_by_module(repo_root)

    dormant: list[str] = []
    for path in sorted(_iter_files(package_dir, suffix=".py")):
        if path.stem in ENTRYPOINT_STEMS:
            continue
        rel = str(path.relative_to(repo_root))
        if rel in classified:
            continue
        module = _module_name(path, src_root)
        # Un módulo que se importa a sí mismo sigue dormido: no es un caller.
        callers = index.get(module, set()) - {rel}
        if not callers:
            dormant.append(rel)
    return dormant
