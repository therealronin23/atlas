"""Tests for ASTGuard — SEC-5 hardening."""

from __future__ import annotations

import pytest

from atlas.security.ast_guard import ASTGuard, GuardResult


@pytest.fixture()
def guard() -> ASTGuard:
    return ASTGuard()


# ---------------------------------------------------------------------------
# Tests basicos (regresion — no deben romperse con SEC-5)
# ---------------------------------------------------------------------------


class TestASTGuardBasic:
    def test_clean_code_passes(self, guard: ASTGuard) -> None:
        result = guard.validate("x = 1 + 2\nprint(x)\n")
        assert result.passed

    def test_blocked_import_subprocess(self, guard: ASTGuard) -> None:
        result = guard.validate("import subprocess\n")
        assert not result.passed
        assert any("subprocess" in v for v in result.violations)

    def test_blocked_call_eval(self, guard: ASTGuard) -> None:
        result = guard.validate("eval('1+1')\n")
        assert not result.passed

    def test_blocked_call_exec(self, guard: ASTGuard) -> None:
        result = guard.validate("exec('x=1')\n")
        assert not result.passed

    def test_blocked_attr_globals(self, guard: ASTGuard) -> None:
        result = guard.validate("f.__globals__\n")
        assert not result.passed

    def test_syntax_error_rejected(self, guard: ASTGuard) -> None:
        result = guard.validate("def f(:\n")
        assert not result.passed

    def test_os_path_allowed_via_restricted(self, guard: ASTGuard) -> None:
        # os is in RESTRICTED_IMPORTS so 'import os' + os.path usage is allowed
        result = guard.validate("import os\nos.path.join('a','b')\n")
        # os.path is in the restricted-but-allowed list, so this passes
        assert result.passed

    def test_os_system_blocked_via_restricted(self, guard: ASTGuard) -> None:
        # os.system is NOT in the restricted allowed list
        result = guard.validate("import os\nos.system('ls')\n")
        assert not result.passed


# ---------------------------------------------------------------------------
# SEC-5: nuevas reglas — getattr/setattr/vars bloqueados
# ---------------------------------------------------------------------------


class TestBlockedReflection:
    def test_getattr_blocked(self, guard: ASTGuard) -> None:
        result = guard.validate("getattr(obj, 'attr')\n")
        assert not result.passed
        assert any("getattr" in v for v in result.violations)

    def test_setattr_blocked(self, guard: ASTGuard) -> None:
        result = guard.validate("setattr(obj, 'x', 1)\n")
        assert not result.passed
        assert any("setattr" in v for v in result.violations)

    def test_vars_blocked(self, guard: ASTGuard) -> None:
        result = guard.validate("vars(obj)\n")
        assert not result.passed
        assert any("vars" in v for v in result.violations)


# ---------------------------------------------------------------------------
# SEC-5: PoC del auditor — getattr(__builtins__, '__imp'+'ort__')('os')
# ---------------------------------------------------------------------------


class TestAuditorPoC:
    def test_getattr_builtins_import_blocked(self, guard: ASTGuard) -> None:
        """getattr bloqueado directamente; la cadena no llega a ejecutarse."""
        code = "getattr(__builtins__, '__imp'+'ort__')('os')\n"
        result = guard.validate(code)
        assert not result.passed, f"deberia ser rechazado: {result.violations}"

    def test_dunder_builtins_name_blocked(self, guard: ASTGuard) -> None:
        """Acceso directo a __builtins__ como nombre bloqueado."""
        code = "x = __builtins__\n"
        result = guard.validate(code)
        assert not result.passed

    def test_import_via_dunder_attr_blocked(self, guard: ASTGuard) -> None:
        """obj.__import__ como atributo bloqueado."""
        code = "obj.__import__('os')\n"
        result = guard.validate(code)
        assert not result.passed

    def test_string_concat_dunder_pattern_blocked(self, guard: ASTGuard) -> None:
        """'__imp' + 'ort__' detectado por patron de ofuscacion pre-parse."""
        code = "getattr(__builtins__, '__imp' + 'ort__')('os')\n"
        result = guard.validate(code)
        assert not result.passed

    def test_clean_arithmetic_not_blocked(self, guard: ASTGuard) -> None:
        """Concatenacion normal de strings no debe ser falso positivo."""
        code = "x = 'hello' + ' world'\n"
        result = guard.validate(code)
        assert result.passed, f"falso positivo: {result.violations}"

    def test_dunder_name_in_identifier_blocked(self, guard: ASTGuard) -> None:
        """Identificadores dunder como __class__ bloqueados."""
        code = "x = self.__class__\n"
        result = guard.validate(code)
        assert not result.passed
