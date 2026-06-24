"""
PropertyVerifier — Verificación estática de propiedades para auto-modificación.

ADR-040 extension: antes de que el Decider emita Allow para una acción
reversible, verifica estáticamente que el patch/code propuesto:
  1. Solo toca los paths declarados (no filesystem arbitrario)
  2. No ejecuta código en import time (no top-level side effects)
  3. No importa módulos de riesgo sin sandbox
  4. Preserva invariantes críticos del sistema (Merkle, Governance)

Esta es la base para "proof-carrying patches": cada propuesta de auto-
modificación puede venir con una prueba verificable de que preserva
propiedades específicas.

Limitación honesta: no resuelve el problema general de verificación de
programas (indecidible), pero pragmatiza un subconjunto útil de
modificaciones mecánicas-verificables.

Restricciones de governance (config/governance.json):
  - No modificar governance.json (hard block)
  - No desactivar AST Guard, Sandbox, SSRF Bridge o Thermal Watchdog
  - No ejecutar con privilegios elevados
  - No ejecutar código no validado por AST Guard fuera de sandbox
"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any


class PropertyCategory(Enum):
    """Categorías de propiedades verificables."""

    PATH_CONTAINMENT = auto()  # Solo toca paths permitidos
    NO_IMPORT_SIDE_EFFECTS = auto()  # No ejecuta código en import
    NO_RISKY_IMPORTS = auto()  # No importa módulos peligrosos
    MERKLE_PRESERVATION = auto()  # No toca el logger de Merkle
    GOVERNANCE_PRESERVATION = auto()  # No modifica governance.json
    NO_PRIVILEGE_ESCALATION = auto()  # No solicita privilegios elevados


class Severity(Enum):
    """Severidad de una violación."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class PropertyViolation:
    """Una violación de propiedad detectada."""

    category: PropertyCategory
    severity: Severity
    message: str
    line: int | None = None
    column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.name,
            "severity": self.severity.value,
            "message": self.message,
            "line": self.line,
            "column": self.column,
        }


@dataclass(frozen=True)
class PropertyVerification:
    """Resultado de verificar un patch contra propiedades."""

    passed: bool
    violations: tuple[PropertyViolation, ...]
    properties_checked: tuple[PropertyCategory, ...]
    proof_hash: str  # Hash del análisis para trazabilidad

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "properties_checked": [p.name for p in self.properties_checked],
            "proof_hash": self.proof_hash,
        }


# ---------------------------------------------------------------------------
# Analizadores AST por propiedad
# ---------------------------------------------------------------------------

class _PathContainmentVisitor(ast.NodeVisitor):
    """Detecta operaciones de filesystem que tocan paths fuera de los permitidos."""

    def __init__(self, allowed_paths: set[str]) -> None:
        self.allowed_paths = allowed_paths
        self.violations: list[PropertyViolation] = []
        self._current_call: ast.Call | None = None

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        self._current_call = node
        self.generic_visit(node)
        self._current_call = None

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        if isinstance(node.value, str) and self._is_path_like(node.value):
            if not self._is_allowed(node.value):
                self.violations.append(
                    PropertyViolation(
                        category=PropertyCategory.PATH_CONTAINMENT,
                        severity=Severity.ERROR,
                        message=f"Path '{node.value}' no está en allowed_paths",
                        line=getattr(node, "lineno", None),
                        column=getattr(node, "col_offset", None),
                    )
                )
        self.generic_visit(node)

    def _is_path_like(self, value: str) -> bool:
        """Heurística para detectar strings que son paths."""
        return "/" in value or "\\" in value or value.endswith((".py", ".json", ".txt", ".md"))

    def _is_allowed(self, path: str) -> bool:
        """Verifica si un path está contenido en alguno de los permitidos."""
        path_norm = Path(path).resolve()
        for allowed in self.allowed_paths:
            try:
                if path_norm.is_relative_to(Path(allowed).resolve()):
                    return True
            except (ValueError, OSError):
                continue
        return False


class _ImportSideEffectVisitor(ast.NodeVisitor):
    """Detecta código que ejecuta en import time (top-level no-definición)."""

    def __init__(self) -> None:
        self.violations: list[PropertyViolation] = []

    def visit_Module(self, node: ast.Module) -> None:  # noqa: N802
        for stmt in node.body:
            if isinstance(stmt, (ast.Expr, ast.Call, ast.Assign)):
                # Asignaciones simples de constantes están OK
                if isinstance(stmt, ast.Assign) and isinstance(
                    stmt.value, ast.Constant
                ):
                    continue
                # Todo lo demás en top-level es sospechoso
                if not isinstance(
                    stmt,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom),
                ):
                    self.violations.append(
                        PropertyViolation(
                            category=PropertyCategory.NO_IMPORT_SIDE_EFFECTS,
                            severity=Severity.WARNING,
                            message=f"Código ejecutable en top-level: {stmt.__class__.__name__}",
                            line=getattr(stmt, "lineno", None),
                        )
                    )
        self.generic_visit(node)


class _RiskyImportVisitor(ast.NodeVisitor):
    """Detecta imports de módulos considerados de riesgo."""

    _RISKY_MODULES = frozenset(
        {
            "subprocess",
            "ctypes",
            "mmap",
            "socket",
            "urllib.request",
            "http.client",
            "ftplib",
            "telnetlib",
            "pickle",
            "marshal",
            "compileall",
        }
    )

    def __init__(self) -> None:
        self.violations: list[PropertyViolation] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            if alias.name in self._RISKY_MODULES:
                self.violations.append(
                    PropertyViolation(
                        category=PropertyCategory.NO_RISKY_IMPORTS,
                        severity=Severity.ERROR,
                        message=f"Import de módulo riesgoso: {alias.name}",
                        line=getattr(node, "lineno", None),
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module in self._RISKY_MODULES:
            self.violations.append(
                PropertyViolation(
                    category=PropertyCategory.NO_RISKY_IMPORTS,
                    severity=Severity.ERROR,
                    message=f"Import from módulo riesgoso: {node.module}",
                    line=getattr(node, "lineno", None),
                )
            )
        self.generic_visit(node)


class _MerklePreservationVisitor(ast.NodeVisitor):
    """Detecta intentos de modificar el MerkleLogger o su cadena."""

    _MERKLE_PATTERNS = [
        re.compile(r"merkle", re.IGNORECASE),
        re.compile(r"hash_self|hash_prev|GENESIS_HASH", re.IGNORECASE),
    ]

    def __init__(self) -> None:
        self.violations: list[PropertyViolation] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        # Detecta asignaciones a atributos de merkle
        if isinstance(node.ctx, ast.Store):
            name = self._get_full_name(node)
            if name and any(p.search(name) for p in self._MERKLE_PATTERNS):
                self.violations.append(
                    PropertyViolation(
                        category=PropertyCategory.MERKLE_PRESERVATION,
                        severity=Severity.CRITICAL,
                        message=f"Intento de modificar atributo Merkle: {name}",
                        line=getattr(node, "lineno", None),
                    )
                )
        self.generic_visit(node)

    def _get_full_name(self, node: ast.AST) -> str | None:
        """Reconstruye el nombre completo de un atributo (a.b.c)."""
        parts = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        else:
            return None
        return ".".join(reversed(parts))


class _GovernancePreservationVisitor(ast.NodeVisitor):
    """Detecta intentos de modificar governance.json o desactivar protecciones."""

    _GOVERNANCE_PATTERNS = [
        re.compile(r"governance\.json", re.IGNORECASE),
        re.compile(r"ast.guard.*disable", re.IGNORECASE),
        re.compile(r"sandbox.*disable", re.IGNORECASE),
        re.compile(r"merkle.*logger.*disable", re.IGNORECASE),
    ]

    def __init__(self) -> None:
        self.violations: list[PropertyViolation] = []

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        if isinstance(node.value, str):
            for pattern in self._GOVERNANCE_PATTERNS:
                if pattern.search(node.value):
                    self.violations.append(
                        PropertyViolation(
                            category=PropertyCategory.GOVERNANCE_PRESERVATION,
                            severity=Severity.CRITICAL,
                            message=f"Posible intento de modificar governance o desactivar protecciones: {node.value[:50]}",
                            line=getattr(node, "lineno", None),
                        )
                    )
        self.generic_visit(node)


class _PrivilegeEscalationVisitor(ast.NodeVisitor):
    """Detecta intentos de escalar privilegios."""

    _PRIVILEGE_PATTERNS = [
        re.compile(r"\bsudo\b", re.IGNORECASE),
        re.compile(r"chmod\s+777", re.IGNORECASE),
        re.compile(r"setuid|setgid", re.IGNORECASE),
        re.compile(r"os\.setuid|os\.setgid", re.IGNORECASE),
    ]

    def __init__(self) -> None:
        self.violations: list[PropertyViolation] = []

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        if isinstance(node.value, str):
            for pattern in self._PRIVILEGE_PATTERNS:
                if pattern.search(node.value):
                    self.violations.append(
                        PropertyViolation(
                            category=PropertyCategory.NO_PRIVILEGE_ESCALATION,
                            severity=Severity.CRITICAL,
                            message=f"Posible escalada de privilegios detectada: {node.value[:50]}",
                            line=getattr(node, "lineno", None),
                        )
                    )
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# PropertyVerifier público
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PropertySpec:
    """Especificación de qué propiedades verificar para un patch."""

    allowed_paths: frozenset[str] = frozenset()
    check_import_side_effects: bool = True
    check_risky_imports: bool = True
    preserve_merkle: bool = True
    preserve_governance: bool = True
    no_privilege_escalation: bool = True

    @classmethod
    def from_codegen_target(cls, target: Any) -> "PropertySpec":
        """Crea spec desde un CodegenTarget (ADR-039)."""
        return cls(
            allowed_paths=frozenset({target.path}) if hasattr(target, "path") else frozenset(),
        )


class PropertyVerifier:
    """
    Verificador estático de propiedades para auto-modificación.

    No ejecuta el código: analiza el AST para detectar violaciones de
    propiedades declaradas. Esto permite al Decider rechazar propuestas
    peligrosas SIN necesidad de sandbox execution.

    Uso típico:
        verifier = PropertyVerifier()
        result = verifier.verify(patch_code, spec)
        if not result.passed:
            # Decider emite Deny o RequiresHuman
    """

    def __init__(self) -> None:
        self._visitors: dict[
            PropertyCategory,
            type[ast.NodeVisitor],
        ] = {
            PropertyCategory.PATH_CONTAINMENT: _PathContainmentVisitor,
            PropertyCategory.NO_IMPORT_SIDE_EFFECTS: _ImportSideEffectVisitor,
            PropertyCategory.NO_RISKY_IMPORTS: _RiskyImportVisitor,
            PropertyCategory.MERKLE_PRESERVATION: _MerklePreservationVisitor,
            PropertyCategory.GOVERNANCE_PRESERVATION: _GovernancePreservationVisitor,
            PropertyCategory.NO_PRIVILEGE_ESCALATION: _PrivilegeEscalationVisitor,
        }

    def verify(self, code: str, spec: PropertySpec | None = None) -> PropertyVerification:
        """
        Verifica un string de código Python contra las propiedades especificadas.

        Args:
            code: Código Python a verificar (string).
            spec: Qué propiedades verificar y con qué parámetros.
                  Si es None, usa defaults permisivos (solo checks seguros).

        Returns:
            PropertyVerification con passed=True si no hay violaciones ERROR/CRITICAL.
        """
        spec = spec or PropertySpec()
        violations: list[PropertyViolation] = []
        properties_checked: list[PropertyCategory] = []

        # Parsear AST
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as e:
            return PropertyVerification(
                passed=False,
                violations=(
                    PropertyViolation(
                        category=PropertyCategory.PATH_CONTAINMENT,
                        severity=Severity.CRITICAL,
                        message=f"SyntaxError: {e}",
                        line=e.lineno,
                        column=e.offset,
                    ),
                ),
                properties_checked=(),
                proof_hash="",
            )

        # Configurar visitors según spec
        visitor_map: dict[PropertyCategory, ast.NodeVisitor] = {}

        if spec.allowed_paths:
            visitor_map[PropertyCategory.PATH_CONTAINMENT] = _PathContainmentVisitor(
                set(spec.allowed_paths)
            )
        if spec.check_import_side_effects:
            visitor_map[PropertyCategory.NO_IMPORT_SIDE_EFFECTS] = _ImportSideEffectVisitor()
        if spec.check_risky_imports:
            visitor_map[PropertyCategory.NO_RISKY_IMPORTS] = _RiskyImportVisitor()
        if spec.preserve_merkle:
            visitor_map[PropertyCategory.MERKLE_PRESERVATION] = _MerklePreservationVisitor()
        if spec.preserve_governance:
            visitor_map[PropertyCategory.GOVERNANCE_PRESERVATION] = _GovernancePreservationVisitor()
        if spec.no_privilege_escalation:
            visitor_map[PropertyCategory.NO_PRIVILEGE_ESCALATION] = _PrivilegeEscalationVisitor()

        # Ejecutar visitors
        for category, visitor in visitor_map.items():
            # Reset tree para cada visitor (ast.parse es barato)
            tree = ast.parse(code, mode="exec")
            visitor.visit(tree)
            if hasattr(visitor, "violations"):
                violations.extend(visitor.violations)
            properties_checked.append(category)

        # Determinar si pasa: ERROR o CRITICAL bloquean
        passed = not any(
            v.severity in (Severity.ERROR, Severity.CRITICAL) for v in violations
        )

        # Calcular proof_hash para trazabilidad
        proof_input = f"{code}:{spec}:{passed}:{len(violations)}"
        proof_hash = hashlib.sha256(proof_input.encode()).hexdigest()

        return PropertyVerification(
            passed=passed,
            violations=tuple(violations),
            properties_checked=tuple(properties_checked),
            proof_hash=proof_hash,
        )
