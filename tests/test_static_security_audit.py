"""Tests for the dependency-free static security audit."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from atlas.interfaces.cli import cli
from atlas.security.static_audit import audit_path


def test_static_audit_flags_high_signal_python_risks(tmp_path: Path) -> None:
    target = tmp_path / "bad.py"
    target.write_text(
        "import os, pickle, subprocess, yaml\n"
        "os.system('id')\n"
        "subprocess.run('id', shell=True)\n"
        "eval('1+1')\n"
        "pickle.loads(b'abc')\n"
        "yaml.load('a: 1')\n",
        encoding="utf-8",
    )

    findings = audit_path(target)
    rules = {f.rule for f in findings}

    assert "shell_execution" in rules
    assert "subprocess_shell_true" in rules
    assert "dynamic_code_execution" in rules
    assert "unsafe_deserialization" in rules
    assert "yaml_load_unsafe" in rules


def test_static_audit_does_not_flag_yaml_safe_load(tmp_path: Path) -> None:
    target = tmp_path / "safe.py"
    target.write_text(
        "import yaml\n"
        "yaml.safe_load('a: 1')\n"
        "yaml.load('a: 1', Loader=yaml.SafeLoader)\n",
        encoding="utf-8",
    )

    findings = audit_path(target)

    assert [f.rule for f in findings] == []


def test_security_audit_cli_json(tmp_path: Path) -> None:
    target = tmp_path / "bad.py"
    target.write_text("import subprocess\nsubprocess.run('x', shell=True)\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["security-audit", str(target), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0]["cwe"] == "CWE-78"
