"""
Atlas Core — AST Guard

AVISO: Este modulo es una defensa en profundidad (LINT-level), NO un jail de
seguridad. Bloquea patrones obvios de abuso en codigo no confiable pero NO
proporciona contencion real contra un atacante determinado. La contencion real
requiere aislamiento a nivel de OS (sandbox de proceso, seccomp, nspawn, etc.)
que esta diferido en la hoja de ruta. No confiar en ASTGuard como unica barrera
de seguridad en produccion.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------

BLOCKED_IMPORTS: frozenset[str] = frozenset({
    "asyncio", "concurrent", "ctypes", "ftplib", "http",
    "importlib", "marshal", "multiprocessing", "os", "pickle",
    "shelve", "signal", "socket", "subprocess", "tempfile",
    "threading", "tty", "termios", "pty", "shutil", "urllib",
    "webbrowser",
})

# Importaciones con acceso parcial permitido
RESTRICTED_IMPORTS: dict[str, frozenset[str]] = {
    "sys": frozenset({"version", "platform", "version_info"}),
    "os":  frozenset({"path"}),
}

BLOCKED_CALLS: frozenset[str] = frozenset({
    "eval", "exec", "compile", "__import__", "input",
    "breakpoint", "memoryview",
    # Reflexion peligrosa: permite escalar a cualquier builtin/objeto
    "getattr", "setattr", "vars",
})

BLOCKED_ATTRS: frozenset[str] = frozenset({
    "__class__", "__globals__", "__builtins__",
    "__code__", "__reduce__", "__subclasses__",
    "__mro__", "__base__", "__bases__",
    "__import__", "__loader__", "__spec__",
})

# Patrones de ofuscacion (en el codigo fuente como string, pre-parse)
OBFUSCATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"base64\.b64decode", re.IGNORECASE),
    re.compile(r"__builtins__\["),
    re.compile(r"chr\(\d+\)\s*\+"),        # chr() concatenation
    re.compile(r"\[::-1\]\s*\("),          # string reversal + call
    # Concatenacion de strings para reconstruir '__import__' u otros dunders
    re.compile(r"['\"]__\w*['\"\s]*\+"),   # '__imp' + 'ort__' style concat
    re.compile(r"\+\s*['\"]__\w*['\"]"),   # trailing piece of dunder concat
]


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GuardResult:
    passed: bool
    violations: tuple[str, ...]
    sanitized_reason: str

    @classmethod
    def ok(cls) -> "GuardResult":
        return cls(passed=True, violations=(), sanitized_reason="")

    @classmethod
    def fail(cls, violations: list[str]) -> "GuardResult":
        return cls(
            passed=False,
            violations=tuple(violations),
            sanitized_reason="; ".join(violations),
        )


# ---------------------------------------------------------------------------
# Visitor AST
# ---------------------------------------------------------------------------

class _ASTGuardVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[str] = []

    # Imports
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            mod = alias.name.split(".")[0]
            if mod in BLOCKED_IMPORTS and mod not in RESTRICTED_IMPORTS:
                self.violations.append(
                    f"Linea {node.lineno}: importacion bloqueada '{alias.name}'"
                )
            # Modulos en RESTRICTED_IMPORTS: permitir el import, verificar usos
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = (node.module or "").split(".")[0]
        if mod in BLOCKED_IMPORTS:
            if mod in RESTRICTED_IMPORTS:
                for alias in node.names:
                    if alias.name not in RESTRICTED_IMPORTS[mod]:
                        self.violations.append(
                            f"Linea {node.lineno}: "
                            f"importacion restringida '{mod}.{alias.name}'"
                        )
            else:
                self.violations.append(
                    f"Linea {node.lineno}: importacion bloqueada 'from {mod}'"
                )
        self.generic_visit(node)

    # Llamadas
    def visit_Call(self, node: ast.Call) -> None:
        # Nombre directo: eval(...)
        if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
            self.violations.append(
                f"Linea {node.lineno}: llamada bloqueada '{node.func.id}()'"
            )
        # Metodo: obj.exec(...)
        if isinstance(node.func, ast.Attribute) and node.func.attr in BLOCKED_CALLS:
            self.violations.append(
                f"Linea {node.lineno}: llamada bloqueada '...{node.func.attr}()'"
            )
        self.generic_visit(node)

    # Nombres de identificadores con dunder
    def visit_Name(self, node: ast.Name) -> None:
        name = node.id
        if name.startswith("__") and name.endswith("__") and name != "__name__":
            self.violations.append(
                f"Linea {node.lineno}: identificador dunder bloqueado '{name}'"
            )
        self.generic_visit(node)

    # Atributos
    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in BLOCKED_ATTRS:
            self.violations.append(
                f"Linea {node.lineno}: acceso a atributo bloqueado '{node.attr}'"
            )
        # Verificar uso de modulos restringidos: os.system → bloqueado, os.path → OK
        if isinstance(node.value, ast.Name):
            mod = node.value.id
            if mod in RESTRICTED_IMPORTS:
                allowed = RESTRICTED_IMPORTS[mod]
                # El primer nivel de atributo debe estar en la lista permitida
                if node.attr not in allowed:
                    self.violations.append(
                        f"Linea {node.lineno}: acceso restringido '{mod}.{node.attr}' "
                        f"(solo permitido: {sorted(allowed)})"
                    )
        self.generic_visit(node)

    # open() con rutas fuera del workspace — heuristica conservadora
    def visit_Call_open(self, node: ast.Call) -> None:  # llamado manualmente
        if not (isinstance(node.func, ast.Name) and node.func.id == "open"):
            return
        if node.args:
            arg = node.args[0]
            # Si el argumento es un string literal con path traversal
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                p = arg.value
                if ".." in p or p.startswith("/") or p.startswith("~"):
                    self.violations.append(
                        f"Linea {node.lineno}: open() con ruta sospechosa '{p}'"
                    )


# ---------------------------------------------------------------------------
# ASTGuard
# ---------------------------------------------------------------------------

class ASTGuard:
    """
    Analiza codigo Python estaticamente antes de pasarlo al sandbox.
    No ejecuta nada. Opera en microsegundos.

    AVISO: defensa en profundidad (LINT-level), NO un jail de seguridad.
    Contencion real requiere aislamiento a nivel de OS (deferido).
    """

    def validate(self, code: str) -> GuardResult:
        """
        Valida el codigo fuente Python.
        Retorna GuardResult con passed=True si el codigo es seguro.
        """
        violations: list[str] = []

        # 1. Patrones de ofuscacion (pre-parse, sobre el texto)
        for pat in OBFUSCATION_PATTERNS:
            if pat.search(code):
                violations.append(f"Patron de ofuscacion detectado: '{pat.pattern}'")

        # 2. Parse del AST
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return GuardResult.fail([f"Error de sintaxis: {e}"])

        # 3. Visita del AST
        visitor = _ASTGuardVisitor()
        visitor.visit(tree)

        # 4. Verificacion especial de open()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                visitor.visit_Call_open(node)

        violations.extend(visitor.violations)

        if violations:
            return GuardResult.fail(violations)
        return GuardResult.ok()

    def validate_or_raise(self, code: str) -> None:
        result = self.validate(code)
        if not result.passed:
            raise SecurityError(result.sanitized_reason)


class SecurityError(Exception):
    """Lanzada cuando el ASTGuard rechaza codigo."""
