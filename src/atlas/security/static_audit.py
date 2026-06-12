"""Small defensive static security audit for Python code.

This is not a replacement for Bandit/Semgrep. It is a dependency-free first
pass that gives Atlas a native, auditable security lens.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StaticFinding:
    path: str
    line: int
    severity: str
    rule: str
    cwe: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_path(path: Path) -> list[StaticFinding]:
    """Audit a Python file or directory recursively."""
    target = path.expanduser().resolve()
    files = [target] if target.is_file() else sorted(target.rglob("*.py"))
    findings: list[StaticFinding] = []
    for file in files:
        findings.extend(_audit_file(file))
    return findings


def _audit_file(path: Path) -> list[StaticFinding]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, OSError, UnicodeDecodeError) as exc:
        return [
            StaticFinding(
                path=str(path),
                line=getattr(exc, "lineno", 1) or 1,
                severity="low",
                rule="parse_error",
                cwe="N/A",
                message=f"could not parse file: {type(exc).__name__}",
            )
        ]
    visitor = _SecurityVisitor(path)
    visitor.visit(tree)
    return visitor.findings


class _SecurityVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.findings: list[StaticFinding] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        name = _call_name(node.func)
        if name in {"eval", "exec"}:
            self._add(node, "high", "dynamic_code_execution", "CWE-94", f"{name}() executes dynamic code")
        if name in {"os.system", "os.popen"}:
            self._add(node, "high", "shell_execution", "CWE-78", f"{name}() executes through a shell")
        if name in {"subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_call", "subprocess.check_output"}:
            if _kw_bool(node, "shell") is True:
                self._add(node, "high", "subprocess_shell_true", "CWE-78", "subprocess with shell=True")
        if name in {"pickle.load", "pickle.loads", "dill.load", "dill.loads"}:
            self._add(node, "high", "unsafe_deserialization", "CWE-502", f"{name}() may deserialize untrusted data")
        if name == "yaml.load" and not _has_safe_yaml_loader(node):
            self._add(node, "medium", "yaml_load_unsafe", "CWE-502", "yaml.load without SafeLoader")
        self.generic_visit(node)

    def _add(
        self,
        node: ast.AST,
        severity: str,
        rule: str,
        cwe: str,
        message: str,
    ) -> None:
        self.findings.append(
            StaticFinding(
                path=str(self.path),
                line=getattr(node, "lineno", 1),
                severity=severity,
                rule=rule,
                cwe=cwe,
                message=message,
            )
        )


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _kw_bool(node: ast.Call, name: str) -> bool | None:
    for kw in node.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, bool):
            return kw.value.value
    return None


def _has_safe_yaml_loader(node: ast.Call) -> bool:
    for kw in node.keywords:
        if kw.arg in {"Loader", "loader"}:
            loader = _call_name(kw.value)
            if loader.endswith("SafeLoader") or loader.endswith("CSafeLoader"):
                return True
    return False
