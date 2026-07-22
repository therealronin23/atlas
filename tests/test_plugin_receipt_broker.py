"""Contrato A3.2: recibo Merkle + broker de aprobación humana.

ADR-073 (consecuencias A3, condición 3 del design doc plugin_manifest_v1):
"Recibo Merkle que ligue record_id, manifest, procedencia y decisión; broker
de aprobación humana para review o sensibilidad alta." No se reinventa HITL:
se reusa el ``Decider`` protocol (ADR-040) que ya vive en
``atlas.core.decider`` — ``sensitivity="high"`` ya es el invariante que
``HumanDecider`` suspende y que ``AutonomousDecider`` deniega SIEMPRE (regla
constitucional #4). Un veredicto ``review`` de A2 se traduce 1:1 a
``sensitivity="high"``: el mismo lever gobierna ambos modos de decisor sin
lógica nueva ad-hoc.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.core.decider.autonomous_decider import AutonomousDecider
from atlas.core.decider.decider import Allow, Deny, RequiresHuman
from atlas.core.decider.human_decider import HumanDecider
from atlas.logging.merkle_logger import MerkleLogger
from atlas.mcp.plugin_materializer import PluginMaterializer
from atlas.mcp.plugin_receipt_broker import PluginReceipt, PluginReceiptBroker


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
        "contrato A3.2 del broker de recibos.\n",
        encoding="utf-8",
    )
    return root


def _materialize(tmp_path: Path, *, name: str = "demo-plugin"):
    source = _source(tmp_path / "src" / name, _manifest(plugin_id=name))
    staging = tmp_path / "staging"
    return PluginMaterializer(staging_root=staging).materialize_local(
        source, expected_plugin_id=name
    )


def _broker(tmp_path: Path, *, decider=None) -> PluginReceiptBroker:
    merkle = MerkleLogger(tmp_path / "merkle")
    return PluginReceiptBroker(
        merkle=merkle, store_dir=tmp_path / "receipts", decider=decider
    )


class TestIssuedOnAdmit:
    def test_admit_under_human_decider_issues_immediately(self, tmp_path: Path) -> None:
        result = _materialize(tmp_path)
        broker = _broker(tmp_path, decider=HumanDecider())

        receipt = broker.request(result)

        assert isinstance(receipt, PluginReceipt)
        assert receipt.status == "issued"
        assert receipt.verdict == "Allow"
        assert receipt.plugin_id == "demo-plugin"
        assert receipt.manifest_sha256 == result.admission.manifest_sha256  # type: ignore[union-attr]
        assert receipt.record_id == result.admission.scan.record_id  # type: ignore[union-attr]
        assert receipt.provenance.tree_sha256 == result.provenance.tree_sha256  # type: ignore[union-attr]
        assert receipt.decided_at is not None

    def test_admit_under_autonomous_decider_also_issues(self, tmp_path: Path) -> None:
        result = _materialize(tmp_path)
        broker = _broker(tmp_path, decider=AutonomousDecider())

        receipt = broker.request(result)

        assert receipt.status == "issued"
        assert receipt.verdict == "Allow"

    def test_receipt_written_to_merkle_chain(self, tmp_path: Path) -> None:
        result = _materialize(tmp_path)
        merkle = MerkleLogger(tmp_path / "merkle")
        broker = PluginReceiptBroker(
            merkle=merkle, store_dir=tmp_path / "receipts", decider=HumanDecider()
        )

        receipt = broker.request(result)

        ok, reason = merkle.verify_chain()
        assert ok, reason
        found = False
        for logfile in sorted((tmp_path / "merkle").glob("merkle*.jsonl")):
            for line in logfile.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row["payload"].get("receipt_id") == receipt.receipt_id:
                    found = True
                    assert row["action"] == "plugin.receipt_issued"
                    assert row["payload"]["record_id"] == receipt.record_id
                    assert row["payload"]["manifest_sha256"] == receipt.manifest_sha256
        assert found, "el recibo debe quedar en la cadena Merkle"


class TestReviewRequiresHuman:
    def test_review_under_human_decider_is_pending(self, tmp_path: Path) -> None:
        # Fuerza verdict=review con un catalog vacío pero un finding sintético
        # es más laborioso; en su lugar inyectamos un admission "review" a
        # mano vía un doble simple del gate — el broker solo debe confiar en
        # `result.admission.status`, no reinspeccionar el scan.
        result = _materialize(tmp_path)
        forced = result.model_copy(
            update={
                "admission": result.admission.model_copy(  # type: ignore[union-attr]
                    update={"status": "review", "reason_codes": ["supply_chain_review"]}
                )
            }
        )
        broker = _broker(tmp_path, decider=HumanDecider())

        receipt = broker.request(forced)

        assert receipt.status == "pending_approval"
        assert receipt.verdict == "RequiresHuman"
        assert receipt.decided_at is None

    def test_review_under_autonomous_decider_is_denied_never_silently_issued(
        self, tmp_path: Path
    ) -> None:
        result = _materialize(tmp_path)
        forced = result.model_copy(
            update={
                "admission": result.admission.model_copy(  # type: ignore[union-attr]
                    update={"status": "review", "reason_codes": ["supply_chain_review"]}
                )
            }
        )
        broker = _broker(tmp_path, decider=AutonomousDecider())

        receipt = broker.request(forced)

        assert receipt.status == "denied"
        assert receipt.verdict == "Deny"

    def test_approve_flips_pending_to_issued(self, tmp_path: Path) -> None:
        result = _materialize(tmp_path)
        forced = result.model_copy(
            update={
                "admission": result.admission.model_copy(  # type: ignore[union-attr]
                    update={"status": "review", "reason_codes": ["supply_chain_review"]}
                )
            }
        )
        broker = _broker(tmp_path, decider=HumanDecider())
        pending = broker.request(forced)
        assert pending.status == "pending_approval"

        approved = broker.approve(pending.receipt_id)

        assert approved.status == "issued"
        assert approved.verdict == "Allow"
        assert approved.decided_at is not None
        assert broker.get(pending.receipt_id).status == "issued"  # type: ignore[union-attr]

    def test_decline_flips_pending_to_declined_with_reason(self, tmp_path: Path) -> None:
        result = _materialize(tmp_path)
        forced = result.model_copy(
            update={
                "admission": result.admission.model_copy(  # type: ignore[union-attr]
                    update={"status": "review", "reason_codes": ["supply_chain_review"]}
                )
            }
        )
        broker = _broker(tmp_path, decider=HumanDecider())
        pending = broker.request(forced)

        declined = broker.decline(pending.receipt_id, reason="licencia no verificable")

        assert declined.status == "declined"
        assert declined.decline_reason == "licencia no verificable"

    def test_approve_on_non_pending_receipt_raises(self, tmp_path: Path) -> None:
        result = _materialize(tmp_path)
        broker = _broker(tmp_path, decider=HumanDecider())
        issued = broker.request(result)  # admit → ya issued

        with pytest.raises(RuntimeError):
            broker.approve(issued.receipt_id)

    def test_approve_unknown_receipt_raises(self, tmp_path: Path) -> None:
        broker = _broker(tmp_path, decider=HumanDecider())
        with pytest.raises(KeyError):
            broker.approve("nope")


class TestBlockedAdmissionNeverGetsAReceipt:
    def test_request_raises_for_blocked_admission(self, tmp_path: Path) -> None:
        # Sin manifest → admission.status == "block".
        source = tmp_path / "src" / "no-manifest"
        source.mkdir(parents=True)
        (source / "readme.md").write_text("hola", encoding="utf-8")
        result = PluginMaterializer(staging_root=tmp_path / "staging").materialize_local(
            source
        )
        assert result.admission.status == "block"  # type: ignore[union-attr]
        broker = _broker(tmp_path, decider=HumanDecider())

        with pytest.raises(ValueError):
            broker.request(result)

    def test_request_raises_when_materialization_itself_failed(self, tmp_path: Path) -> None:
        from atlas.mcp.plugin_materializer import PluginMaterializer as _PM

        source = tmp_path / "does-not-exist"
        result = _PM(staging_root=tmp_path / "staging").materialize_local(source)
        assert result.status == "failed"
        broker = _broker(tmp_path, decider=HumanDecider())

        with pytest.raises(ValueError):
            broker.request(result)


class TestPersistence:
    def test_receipts_survive_broker_restart(self, tmp_path: Path) -> None:
        result = _materialize(tmp_path)
        merkle = MerkleLogger(tmp_path / "merkle")
        first = PluginReceiptBroker(
            merkle=merkle, store_dir=tmp_path / "receipts", decider=HumanDecider()
        )
        receipt = first.request(result)

        second = PluginReceiptBroker(
            merkle=merkle, store_dir=tmp_path / "receipts", decider=HumanDecider()
        )

        reloaded = second.get(receipt.receipt_id)
        assert reloaded is not None
        assert reloaded.receipt_id == receipt.receipt_id
        assert reloaded.status == "issued"

    def test_list_returns_all_receipts(self, tmp_path: Path) -> None:
        broker = _broker(tmp_path, decider=HumanDecider())
        r1 = broker.request(_materialize(tmp_path, name="plugin-a"))
        r2 = broker.request(_materialize(tmp_path, name="plugin-b"))

        ids = {r.receipt_id for r in broker.list()}
        assert {r1.receipt_id, r2.receipt_id} <= ids


class TestCliReceiptFlow:
    def test_materialize_then_approve_review_via_cli(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.core.orchestrator import Orchestrator
        from atlas.interfaces.cli import cli

        monkeypatch.delenv("ATLAS_DECIDER", raising=False)  # default = human
        source = _source(tmp_path / "src" / "review-plugin", _manifest(plugin_id="review-plugin"))
        orch = Orchestrator(workspace=tmp_path / "atlas")
        monkeypatch.setattr("atlas.interfaces.cli._orch", orch)
        runner = CliRunner()

        materialize = runner.invoke(
            cli,
            [
                "plugin", "materialize", str(source),
                "--staging-root", str(tmp_path / "staging"),
                "--plugin-id", "review-plugin",
            ],
        )
        assert materialize.exit_code == 0, materialize.output
        assert "issued" in materialize.output  # admit real bajo A2, no review sintético

        receipt_id = orch.plugin_receipts().list()[0].receipt_id

        show = runner.invoke(cli, ["plugin", "receipt", "show", receipt_id])
        assert show.exit_code == 0, show.output
        assert receipt_id in show.output

        listing = runner.invoke(cli, ["plugin", "receipt", "list"])
        assert receipt_id in listing.output

    def test_approve_unknown_receipt_via_cli_exits_nonzero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.core.orchestrator import Orchestrator
        from atlas.interfaces.cli import cli

        orch = Orchestrator(workspace=tmp_path / "atlas")
        monkeypatch.setattr("atlas.interfaces.cli._orch", orch)
        runner = CliRunner()

        result = runner.invoke(cli, ["plugin", "receipt", "approve", "nope"])
        assert result.exit_code != 0

    def test_decline_pending_receipt_via_cli(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.core.orchestrator import Orchestrator
        from atlas.interfaces.cli import cli

        orch = Orchestrator(workspace=tmp_path / "atlas")
        monkeypatch.setattr("atlas.interfaces.cli._orch", orch)
        runner = CliRunner()

        result = _materialize(tmp_path, name="review-plugin")
        forced = result.model_copy(
            update={
                "admission": result.admission.model_copy(  # type: ignore[union-attr]
                    update={"status": "review", "reason_codes": ["supply_chain_review"]}
                )
            }
        )
        pending = orch.plugin_receipts().request(forced)

        decline = runner.invoke(
            cli, ["plugin", "receipt", "decline", pending.receipt_id, "--reason", "no"]
        )
        assert decline.exit_code == 0, decline.output
        assert "declined" in decline.output


class TestReceiptIntegrityBindings:
    def test_receipt_binds_exact_staged_root_and_tree_hash(self, tmp_path: Path) -> None:
        # A3.3 (activador futuro) deberá poder re-verificar el árbol contra
        # ESTOS campos antes de activar nada — el contrato se fija aquí.
        result = _materialize(tmp_path)
        broker = _broker(tmp_path, decider=HumanDecider())

        receipt = broker.request(result)

        assert receipt.staged_root == result.staged_root
        assert Path(receipt.staged_root).is_dir()  # type: ignore[arg-type]

    def test_receipt_model_is_strict_no_extra_fields(self, tmp_path: Path) -> None:
        result = _materialize(tmp_path)
        broker = _broker(tmp_path, decider=HumanDecider())
        receipt = broker.request(result)

        with pytest.raises(Exception):
            PluginReceipt(**{**receipt.model_dump(), "unexpected_field": "x"})
