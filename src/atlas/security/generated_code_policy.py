"""
Gate H5 — Meta-governance checks for generated Python source.
Complements AST Guard with governance-specific rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from atlas.security.ast_guard import ASTGuard, GuardResult


_GOVERNANCE_PATTERNS = (
    re.compile(r"governance\.json", re.IGNORECASE),
    re.compile(r"GovernanceL0", re.IGNORECASE),
    re.compile(r"modify.*governance", re.IGNORECASE),
)

_LOGGING_DISABLE_PATTERNS = (
    re.compile(r"MerkleLogger\s*\.\s*disable", re.IGNORECASE),
    re.compile(r"merkle.*=\s*None", re.IGNORECASE),
    re.compile(r"logging\.disable\s*\(", re.IGNORECASE),
)

_UNSAFE_OPEN_PATTERNS = (
    re.compile(r'open\s*\(\s*["\']/etc/', re.IGNORECASE),
    re.compile(r'open\s*\(\s*["\']/root/', re.IGNORECASE),
    re.compile(r'open\s*\(\s*["\'].*\.ssh', re.IGNORECASE),
)


@dataclass(frozen=True)
class GeneratedCodePolicyResult:
    passed: bool
    violations: tuple[str, ...]
    ast_result: GuardResult

    @property
    def reason(self) -> str:
        return "; ".join(self.violations)


class GeneratedCodePolicy:
    """AST Guard + extra rules for synthesized/host-generated code."""

    def __init__(self, ast_guard: ASTGuard | None = None) -> None:
        self._ast = ast_guard or ASTGuard()

    def check_generated_source(self, code: str) -> GeneratedCodePolicyResult:
        violations: list[str] = []
        ast_result = self._ast.validate(code)
        if not ast_result.passed:
            violations.extend(list(ast_result.violations))

        for pattern in _GOVERNANCE_PATTERNS:
            if pattern.search(code):
                violations.append("referencia a governance inmutable prohibida")
                break

        for pattern in _LOGGING_DISABLE_PATTERNS:
            if pattern.search(code):
                violations.append("intento de deshabilitar auditoria Merkle/logging")
                break

        for pattern in _UNSAFE_OPEN_PATTERNS:
            if pattern.search(code):
                violations.append("open() a ruta de sistema prohibida")
                break

        return GeneratedCodePolicyResult(
            passed=len(violations) == 0,
            violations=tuple(violations),
            ast_result=ast_result,
        )
