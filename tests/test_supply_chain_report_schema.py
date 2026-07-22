"""Paridad del reporte A1: JSON Schema canónico y espejo Pydantic cerrado."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError


REPO = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO / "schemas" / "supply_chain_report.schema.json"


def _api() -> tuple[Any, Any]:
    scanner_module = importlib.import_module("atlas.security.supply_chain")
    models_module = importlib.import_module("atlas.security.supply_chain_models")
    return scanner_module.SupplyChainScanner, models_module.SupplyChainReport


def _real_report(tmp_path: Path) -> Any:
    SupplyChainScanner, _ = _api()
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "requirements.txt").write_text("requests>=2\n", encoding="utf-8")
    return SupplyChainScanner().scan(root)


def test_supply_chain_schema_exists_and_is_valid_draft_2020_12() -> None:
    assert SCHEMA_PATH.exists()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"]["const"] == "1.0"
    assert schema["additionalProperties"] is False


def test_real_report_validates_against_json_schema_and_pydantic(tmp_path: Path) -> None:
    report = _real_report(tmp_path)
    _, SupplyChainReport = _api()
    payload = report.model_dump(mode="json")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    errors = list(Draft202012Validator(schema).iter_errors(payload))

    assert not errors, [error.message for error in errors]
    assert SupplyChainReport.model_validate(payload) == report
    assert set(schema["required"]) == {
        name for name, field in SupplyChainReport.model_fields.items() if field.is_required()
    }
    assert set(schema["properties"]) == set(SupplyChainReport.model_fields)


def test_json_schema_and_pydantic_reject_root_extra_fields(tmp_path: Path) -> None:
    report = _real_report(tmp_path)
    _, SupplyChainReport = _api()
    payload = report.model_dump(mode="json") | {"unexpected": True}
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert list(Draft202012Validator(schema).iter_errors(payload))
    with pytest.raises(ValidationError):
        SupplyChainReport.model_validate(payload)


def test_json_schema_and_pydantic_reject_nested_extra_fields(tmp_path: Path) -> None:
    report = _real_report(tmp_path)
    _, SupplyChainReport = _api()
    payload = report.model_dump(mode="json")
    payload["files"][0]["unexpected"] = True
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert list(Draft202012Validator(schema).iter_errors(payload))
    with pytest.raises(ValidationError):
        SupplyChainReport.model_validate(payload)

