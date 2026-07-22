"""Contrato A3.3: activador reversible que consume SOLO un recibo `issued`.

ADR-073 (consecuencias A3, condición 4 de docs/design/plugin_manifest_v1.md):
"Activador reversible que consuma sólo ese recibo, aplique contribuciones
declarativas y permita revocar/borrar staging sin tocar el árbol principal."

Dos defensas TOCTOU que este contrato fija con tests, no solo con comentarios:
1. El árbol staged se re-hashea en el momento de activar (y de novo en
   approve_activation) contra `receipt.provenance.tree_sha256` — un recibo
   `issued` hace días no es un cheque en blanco si algo tocó staging después.
2. El manifest se re-lee y re-hashea contra `receipt.manifest_sha256` antes
   de confiar en sus contribuciones — el recibo liga bytes exactos, no un
   plugin_id genérico.

Igual que A3.2: NO se reinventa HITL. La activación consulta el MISMO
`Decider` protocol; `requires_approval=True` fuerza `RequiresHuman` bajo
`HumanDecider` siempre — un `admit` de A2 fue evidencia, nunca permiso de
instalación (dicho explícitamente en la CLI de A3.1); activar es su propia
decisión, separada de emitir el recibo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.core.decider.autonomous_decider import AutonomousDecider
from atlas.core.decider.human_decider import HumanDecider
from atlas.logging.merkle_logger import MerkleLogger
from atlas.mcp.plugin_activator import ActivationRecord, PluginActivator
from atlas.mcp.plugin_materializer import PluginMaterializer
from atlas.mcp.plugin_receipt_broker import PluginReceiptBroker


def _manifest(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": "1.0",
        "plugin_id": "demo-plugin",
        "display_name": "Demo plugin",
        "version": "1.0.0",
        "source": {
            "origin": "local://test/demo-plugin",
            "revision": "fixture-1",
            "license": "Apache-2.0",
        },
        "activation": "declarative",
        "permissions": [],
        "contributions": [
            {"contribution_id": "demo-skill", "kind": "skill", "path": "skills/demo.md"}
        ],
    }
    document.update(overrides)
    return document


def _source(root: Path, manifest: dict[str, object] | None = None) -> Path:
    root.mkdir(parents=True)
    (root / "atlas-plugin.json").write_text(
        json.dumps(manifest or _manifest()), encoding="utf-8"
    )
    (root / "skills").mkdir()
    (root / "skills" / "demo.md").write_text(
        "# Demo skill\n\nUna skill declarativa de demostracion para el "
        "contrato A3.3 del activador.\n",
        encoding="utf-8",
    )
    return root


def _rig(tmp_path: Path, *, decider=None, name: str = "demo-plugin"):
    """Devuelve (broker, activator, receipt) con un recibo `issued` real."""
    source = _source(tmp_path / "src" / name, _manifest(plugin_id=name))
    materialized = PluginMaterializer(staging_root=tmp_path / "staging").materialize_local(
        source, expected_plugin_id=name
    )
    merkle = MerkleLogger(tmp_path / "merkle")
    broker = PluginReceiptBroker(
        merkle=merkle, store_dir=tmp_path / "receipts", decider=HumanDecider()
    )
    receipt = broker.request(materialized)
    assert receipt.status == "issued"
    activator = PluginActivator(
        broker=broker,
        merkle=merkle,
        active_root=tmp_path / "active",
        store_dir=tmp_path / "activations",
        decider=decider if decider is not None else HumanDecider(),
    )
    return broker, activator, receipt


class TestApplyOnAllow:
    def test_activate_under_autonomous_decider_applies_immediately(
        self, tmp_path: Path
    ) -> None:
        _broker, activator, receipt = _rig(tmp_path, decider=AutonomousDecider())

        record = activator.activate(receipt.receipt_id)

        assert isinstance(record, ActivationRecord)
        assert record.status == "activated"
        assert record.verdict == "Allow"
        assert record.active_root is not None
        active = Path(record.active_root)
        assert active.is_dir()
        assert len(record.applied) == 1
        applied = record.applied[0]
        assert applied.contribution_id == "demo-skill"
        assert applied.kind == "skill"
        link = Path(applied.active_path)
        assert link.is_symlink()
        assert link.read_text(encoding="utf-8").startswith("# Demo skill")
        # fuente única: el symlink apunta AL árbol staged, no a una copia.
        assert link.resolve() == (Path(receipt.staged_root) / "skills" / "demo.md").resolve()

    def test_merkle_records_activation(self, tmp_path: Path) -> None:
        broker = None  # noqa: F841 — silencia unused si no se usa
        _b, activator, receipt = _rig(tmp_path, decider=AutonomousDecider())
        merkle = activator._merkle  # type: ignore[attr-defined]

        record = activator.activate(receipt.receipt_id)

        found = False
        for logfile in sorted((tmp_path / "merkle").glob("merkle*.jsonl")):
            for line in logfile.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row["payload"].get("activation_id") == record.activation_id:
                    found = True
                    assert row["action"] == "plugin.activated"
        assert found
        ok, reason = merkle.verify_chain()
        assert ok, reason


class TestRequiresHumanApproval:
    def test_activate_under_human_decider_is_pending(self, tmp_path: Path) -> None:
        _broker, activator, receipt = _rig(tmp_path, decider=HumanDecider())

        record = activator.activate(receipt.receipt_id)

        assert record.status == "pending_approval"
        assert record.verdict == "RequiresHuman"
        assert record.active_root is None
        assert record.applied == []
        # Nada tocó el filesystem todavía.
        assert not (tmp_path / "active").exists() or list((tmp_path / "active").iterdir()) == []

    def test_approve_activation_applies_and_reverifies_tree(self, tmp_path: Path) -> None:
        _broker, activator, receipt = _rig(tmp_path, decider=HumanDecider())
        pending = activator.activate(receipt.receipt_id)
        assert pending.status == "pending_approval"

        approved = activator.approve_activation(pending.activation_id)

        assert approved.status == "activated"
        assert approved.active_root is not None
        assert len(approved.applied) == 1
        assert activator.get(pending.activation_id).status == "activated"  # type: ignore[union-attr]

    def test_approve_activation_fails_closed_if_staging_mutated_meanwhile(
        self, tmp_path: Path
    ) -> None:
        _broker, activator, receipt = _rig(tmp_path, decider=HumanDecider())
        pending = activator.activate(receipt.receipt_id)

        # TOCTOU: alguien (o algo) tocó staging entre el request y el approve.
        tampered = Path(receipt.staged_root) / "skills" / "demo.md"
        tampered.write_text("# Hackeado\n", encoding="utf-8")

        result = activator.approve_activation(pending.activation_id)

        assert result.status == "failed"
        assert "staged_tree_mutated_since_receipt" in result.reason_codes
        assert not Path(tmp_path / "active" / receipt.plugin_id).exists()

    def test_activate_fails_closed_if_staging_mutated_before_first_request(
        self, tmp_path: Path
    ) -> None:
        _broker, activator, receipt = _rig(tmp_path, decider=AutonomousDecider())
        tampered = Path(receipt.staged_root) / "skills" / "demo.md"
        tampered.write_text("# Hackeado\n", encoding="utf-8")

        record = activator.activate(receipt.receipt_id)

        assert record.status == "failed"
        assert "staged_tree_mutated_since_receipt" in record.reason_codes


class TestDenied:
    def test_deny_verdict_never_touches_filesystem(self, tmp_path: Path) -> None:
        class AlwaysDeny:
            def decide(self, action, sanctioned_intent, context):  # type: ignore[no-untyped-def]
                from atlas.core.decider.decider import Deny

                return Deny(reason="test")

        _broker, activator, receipt = _rig(tmp_path, decider=AlwaysDeny())

        record = activator.activate(receipt.receipt_id)

        assert record.status == "denied"
        assert record.active_root is None
        assert not (tmp_path / "active").exists()


class TestReceiptGating:
    def test_activate_rejects_non_issued_receipt(self, tmp_path: Path) -> None:
        source = _source(tmp_path / "src" / "review-plugin", _manifest(plugin_id="review-plugin"))
        materialized = PluginMaterializer(staging_root=tmp_path / "staging").materialize_local(
            source, expected_plugin_id="review-plugin"
        )
        merkle = MerkleLogger(tmp_path / "merkle")
        broker = PluginReceiptBroker(
            merkle=merkle, store_dir=tmp_path / "receipts", decider=HumanDecider()
        )
        forced = materialized.model_copy(
            update={
                "admission": materialized.admission.model_copy(  # type: ignore[union-attr]
                    update={"status": "review", "reason_codes": ["supply_chain_review"]}
                )
            }
        )
        pending_receipt = broker.request(forced)
        assert pending_receipt.status == "pending_approval"
        activator = PluginActivator(
            broker=broker,
            merkle=merkle,
            active_root=tmp_path / "active",
            store_dir=tmp_path / "activations",
            decider=HumanDecider(),
        )

        with pytest.raises(ValueError):
            activator.activate(pending_receipt.receipt_id)

    def test_activate_unknown_receipt_raises(self, tmp_path: Path) -> None:
        merkle = MerkleLogger(tmp_path / "merkle")
        broker = PluginReceiptBroker(
            merkle=merkle, store_dir=tmp_path / "receipts", decider=HumanDecider()
        )
        activator = PluginActivator(
            broker=broker,
            merkle=merkle,
            active_root=tmp_path / "active",
            store_dir=tmp_path / "activations",
            decider=HumanDecider(),
        )

        with pytest.raises(KeyError):
            activator.activate("nope")


class TestConflicts:
    def test_double_activation_of_same_plugin_id_fails_closed(self, tmp_path: Path) -> None:
        _broker, activator, receipt = _rig(tmp_path, decider=AutonomousDecider())
        first = activator.activate(receipt.receipt_id)
        assert first.status == "activated"

        second = activator.activate(receipt.receipt_id)

        assert second.status == "failed"
        assert "plugin_already_active" in second.reason_codes


class TestRevoke:
    def test_revoke_removes_active_tree_and_staging_by_default(self, tmp_path: Path) -> None:
        _broker, activator, receipt = _rig(tmp_path, decider=AutonomousDecider())
        activated = activator.activate(receipt.receipt_id)
        active_root = Path(activated.active_root)  # type: ignore[arg-type]
        staged_root = Path(receipt.staged_root)
        assert active_root.exists() and staged_root.exists()

        revoked = activator.revoke(activated.activation_id)

        assert revoked.status == "revoked"
        assert not active_root.exists()
        assert not staged_root.exists()  # ADR-073: "permita ... borrar staging"

    def test_revoke_can_keep_staging(self, tmp_path: Path) -> None:
        _broker, activator, receipt = _rig(tmp_path, decider=AutonomousDecider())
        activated = activator.activate(receipt.receipt_id)
        staged_root = Path(receipt.staged_root)

        activator.revoke(activated.activation_id, keep_staging=True)

        assert staged_root.exists()

    def test_revoke_never_touches_main_tree(self, tmp_path: Path) -> None:
        # "sin tocar el árbol principal" — revoke() solo conoce active_root
        # y staged_root, nunca el repo real; este test fija el contrato con
        # un canario fuera de ambos árboles.
        canary = tmp_path / "canary.txt"
        canary.write_text("no me toques", encoding="utf-8")
        _broker, activator, receipt = _rig(tmp_path, decider=AutonomousDecider())
        activated = activator.activate(receipt.receipt_id)

        activator.revoke(activated.activation_id)

        assert canary.read_text(encoding="utf-8") == "no me toques"

    def test_revoke_non_activated_record_raises(self, tmp_path: Path) -> None:
        _broker, activator, receipt = _rig(tmp_path, decider=HumanDecider())
        pending = activator.activate(receipt.receipt_id)
        assert pending.status == "pending_approval"

        with pytest.raises(RuntimeError):
            activator.revoke(pending.activation_id)

    def test_revoke_unknown_activation_raises(self, tmp_path: Path) -> None:
        _broker, activator, _receipt = _rig(tmp_path, decider=AutonomousDecider())
        with pytest.raises(KeyError):
            activator.revoke("nope")

    def test_reactivation_after_revoke_succeeds(self, tmp_path: Path) -> None:
        # revoke() borra staging por defecto, así que una reactivación real
        # necesita materializar+emitir recibo de nuevo — pero el active_root
        # debe quedar libre para un plugin_id reutilizado.
        _broker, activator, receipt = _rig(tmp_path, decider=AutonomousDecider(), name="reused")
        first = activator.activate(receipt.receipt_id)
        activator.revoke(first.activation_id)

        source2 = _source(tmp_path / "src2" / "reused", _manifest(plugin_id="reused"))
        materialized2 = PluginMaterializer(staging_root=tmp_path / "staging2").materialize_local(
            source2, expected_plugin_id="reused"
        )
        receipt2 = _broker.request(materialized2)
        second = activator.activate(receipt2.receipt_id)

        assert second.status == "activated"


class TestPersistence:
    def test_activations_survive_activator_restart(self, tmp_path: Path) -> None:
        broker, activator, receipt = _rig(tmp_path, decider=AutonomousDecider())
        record = activator.activate(receipt.receipt_id)

        restarted = PluginActivator(
            broker=broker,
            merkle=activator._merkle,  # type: ignore[attr-defined]
            active_root=tmp_path / "active",
            store_dir=tmp_path / "activations",
            decider=AutonomousDecider(),
        )

        reloaded = restarted.get(record.activation_id)
        assert reloaded is not None
        assert reloaded.status == "activated"

    def test_list_returns_all_activations(self, tmp_path: Path) -> None:
        _broker, activator, receipt = _rig(tmp_path, decider=AutonomousDecider())
        record = activator.activate(receipt.receipt_id)

        ids = {r.activation_id for r in activator.list()}
        assert record.activation_id in ids


class TestCliActivationFlow:
    def test_materialize_activate_approve_revoke_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.core.orchestrator import Orchestrator
        from atlas.interfaces.cli import cli

        monkeypatch.delenv("ATLAS_DECIDER", raising=False)  # default = human
        source = _source(tmp_path / "src" / "cli-plugin", _manifest(plugin_id="cli-plugin"))
        orch = Orchestrator(workspace=tmp_path / "atlas")
        monkeypatch.setattr("atlas.interfaces.cli._orch", orch)
        runner = CliRunner()

        materialize = runner.invoke(
            cli,
            [
                "plugin", "materialize", str(source),
                "--staging-root", str(tmp_path / "staging"),
                "--plugin-id", "cli-plugin",
            ],
        )
        assert materialize.exit_code == 0, materialize.output
        receipt_id = orch.plugin_receipts().list()[0].receipt_id

        activate = runner.invoke(cli, ["plugin", "activate", receipt_id])
        assert activate.exit_code == 0, activate.output
        assert "pending_approval" in activate.output  # HumanDecider por defecto

        activation_id = orch.plugin_activator().list()[0].activation_id

        approve = runner.invoke(cli, ["plugin", "activation", "approve", activation_id])
        assert approve.exit_code == 0, approve.output
        assert "activated" in approve.output

        show = runner.invoke(cli, ["plugin", "activation", "show", activation_id])
        assert activation_id in show.output

        listing = runner.invoke(cli, ["plugin", "activation", "list"])
        assert activation_id in listing.output

        revoke = runner.invoke(cli, ["plugin", "activation", "revoke", activation_id])
        assert revoke.exit_code == 0, revoke.output
        assert "revoked" in revoke.output

    def test_activate_unknown_receipt_via_cli_exits_nonzero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.core.orchestrator import Orchestrator
        from atlas.interfaces.cli import cli

        orch = Orchestrator(workspace=tmp_path / "atlas")
        monkeypatch.setattr("atlas.interfaces.cli._orch", orch)
        runner = CliRunner()

        result = runner.invoke(cli, ["plugin", "activate", "nope"])
        assert result.exit_code != 0


def test_module_has_no_network_or_process_surface() -> None:
    import re

    import atlas.mcp.plugin_activator as module

    text = Path(module.__file__).read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_.]+)", text, re.M)
    forbidden = {"subprocess", "socket", "urllib", "http", "requests", "asyncio"}
    assert not (set(imports) & forbidden), f"imports prohibidos: {set(imports) & forbidden}"
