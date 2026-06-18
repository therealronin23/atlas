"""Tests for MerkleLogger signing — SEC-4."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from atlas.logging.merkle_logger import AuditRecord, MerkleLogger
from atlas.security.authorization import HMACSigner


def _make_signer() -> HMACSigner:
    return HMACSigner(b"test-secret-key-32-bytes-xxxxxx!")


# ---------------------------------------------------------------------------
# Retrocompat: sin firma — comportamiento existente
# ---------------------------------------------------------------------------


class TestMerkleLoggerUnsigned:
    def test_append_and_verify_unsigned(self, tmp_path: Path) -> None:
        logger = MerkleLogger(tmp_path)
        logger.log("task.created", "test-agent", "success")
        logger.log("task.completed", "test-agent", "success")
        ok, msg = logger.verify_chain()
        assert ok, msg

    def test_tamper_detected_unsigned(self, tmp_path: Path) -> None:
        """Sin firma: la corrupcion del hash_self se detecta igual."""
        logger = MerkleLogger(tmp_path)
        logger.log("task.created", "agent", "success")
        logger.log("task.completed", "agent", "success")

        log_file = tmp_path / "merkle.jsonl"
        lines = log_file.read_text().splitlines()
        data = json.loads(lines[0])
        data["action"] = "TAMPERED"
        # hash_self no se actualiza, queda invalido
        lines[0] = json.dumps(data)
        log_file.write_text("\n".join(lines) + "\n")

        logger2 = MerkleLogger(tmp_path)
        ok, msg = logger2.verify_chain()
        assert not ok
        assert "hash_self invalido" in msg

    def test_no_signature_field_in_unsigned_records(self, tmp_path: Path) -> None:
        logger = MerkleLogger(tmp_path)
        logger.log("task.created", "agent", "success")
        log_file = tmp_path / "merkle.jsonl"
        data = json.loads(log_file.read_text().strip())
        assert "signature" not in data


# ---------------------------------------------------------------------------
# Con firma: SEC-4
# ---------------------------------------------------------------------------


class TestMerkleLoggerSigned:
    def test_append_and_verify_signed(self, tmp_path: Path) -> None:
        signer = _make_signer()
        logger = MerkleLogger(tmp_path, signer=signer)
        logger.log("task.created", "agent", "success")
        logger.log("task.completed", "agent", "success")
        ok, msg = logger.verify_chain()
        assert ok, msg

    def test_signature_field_present_in_signed_records(self, tmp_path: Path) -> None:
        signer = _make_signer()
        logger = MerkleLogger(tmp_path, signer=signer)
        logger.log("task.created", "agent", "success")
        log_file = tmp_path / "merkle.jsonl"
        data = json.loads(log_file.read_text().strip())
        assert "signature" in data
        assert "sig_algo" in data

    def test_tamper_intermediate_record_detected_with_signer(self, tmp_path: Path) -> None:
        """Mutar un AuditRecord intermedio → verify_chain falla con signer."""
        signer = _make_signer()
        logger = MerkleLogger(tmp_path, signer=signer)
        logger.log("task.created", "agent", "success")
        logger.log("task.approved", "agent", "success")
        logger.log("task.completed", "agent", "success")

        log_file = tmp_path / "merkle.jsonl"
        lines = log_file.read_text().splitlines()

        # Mutar el registro intermedio (index 1): cambiar action pero MANTENER hash_self
        # (el atacante que intenta pasar la verificacion de hash_self deberia recalcular,
        # pero la firma sigue siendo de los datos originales)
        data = json.loads(lines[1])
        original_hash_self = data["hash_self"]
        data["action"] = "governance.violation"
        # Recalcular hash_self para que la verificacion de hash pase, pero la firma falle
        import hashlib, json as _json
        payload = {
            "id": data["id"],
            "action": data["action"],
            "agent": data["agent"],
            "result": data["result"],
            "risk_level": data["risk_level"],
            "payload": data["payload"],
            "task_id": data["task_id"],
            "hash_prev": data["hash_prev"],
            "timestamp": data["timestamp"],
        }
        data["hash_self"] = hashlib.sha256(
            _json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        # Dejar la firma original (que era del hash_self anterior) — firma invalida
        lines[1] = _json.dumps(data)
        log_file.write_text("\n".join(lines) + "\n")

        logger2 = MerkleLogger(tmp_path, signer=signer)
        ok, msg = logger2.verify_chain()
        assert not ok, "Deberia detectar la manipulacion via firma invalida o hash_prev roto"

    def test_missing_signature_detected(self, tmp_path: Path) -> None:
        """Registro sin firma cuando el logger espera firma → fallo."""
        # Primero escribir sin firma
        logger_unsigned = MerkleLogger(tmp_path)
        logger_unsigned.log("task.created", "agent", "success")

        # Luego verificar con signer — el registro no tiene firma
        signer = _make_signer()
        logger_signed = MerkleLogger(tmp_path, signer=signer)
        ok, msg = logger_signed.verify_chain()
        assert not ok
        assert "firma ausente" in msg

    def test_read_all_works_with_signed_log(self, tmp_path: Path) -> None:
        signer = _make_signer()
        logger = MerkleLogger(tmp_path, signer=signer)
        logger.log("task.created", "agent", "success")
        logger.log("task.completed", "agent", "success")
        records = logger.read_all()
        assert len(records) == 2
        assert all(isinstance(r, AuditRecord) for r in records)

    def test_signed_logger_retrocompat_signature(self, tmp_path: Path) -> None:
        """Constructor nuevo (signer=None) sigue aceptando positional arg."""
        logger = MerkleLogger(tmp_path, None)
        logger.log("session.started", "agent", "success")
        ok, msg = logger.verify_chain()
        assert ok, msg
