#!/usr/bin/env python3
"""
Smoke operativo end-to-end (Sesion A).

Uso:
    source .venv/bin/activate && source .env
    PYTHONPATH=src python scripts/operational_smoke.py

Opciones:
    --skip-cli-approval   No ejecuta ciclo editor write + approve en workspace temporal
    --skip-telegram       No envia mensaje outbound a Telegram
    --workspace PATH      Usar ATLAS_HOME existente (default: directorio temporal)

Comprueba:
  1) Variables HERMES_* presentes
  2) Orchestrator.status: governance + Merkle + Hermes reachable
  3) Hermes REST: health, enqueue, cancel
  4) (opcional) CLI approval: task -> pending -> approve -> done
  5) (opcional) Telegram outbound sendMessage
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from atlas.core.contracts import TaskStatus
from atlas.core.orchestrator import Orchestrator
from atlas.hermes.hermes import DelegationBuilder, HermesError, HermesRestAdapter
from atlas.interfaces.telegram_bot import TelegramAPIError, TelegramClient


def _check_env() -> dict[str, str]:
    base = os.environ.get("HERMES_BASE_URL", "").strip()
    secret = os.environ.get("HERMES_API_KEY", "").strip()
    if not base or not secret:
        print("ERROR: HERMES_BASE_URL y HERMES_API_KEY requeridos.")
        sys.exit(2)
    return {"HERMES_BASE_URL": base, "HERMES_API_KEY": "***"}


def _check_orchestrator_status(workspace: Path) -> dict:
    os.environ["ATLAS_HOME"] = str(workspace)
    os.environ.setdefault("ATLAS_PENDING_HMAC_KEY", os.environ.get("HERMES_API_KEY", "smoke-key"))
    orch = Orchestrator(workspace=workspace)
    st = orch.status()
    ok = st.chain_ok and st.governance_ok
    hermes = orch._hermes.health_check()
    result = {
        "chain_ok": st.chain_ok,
        "governance_ok": st.governance_ok,
        "hermes_mode": st.hermes_mode,
        "hermes_reachable": hermes.reachable,
        "queue_depth": st.queue_depth,
        "adapter_type": type(orch._hermes).__name__,
    }
    if not ok:
        print(f"ERROR status: {result}")
        sys.exit(1)
    if not hermes.reachable:
        print(f"ERROR Hermes no reachable: {result}")
        sys.exit(1)
    print(f"[2/5] orchestrator OK: {json.dumps(result)}")
    return result


def _check_hermes_rest() -> None:
    base = os.environ["HERMES_BASE_URL"].strip()
    secret = os.environ["HERMES_API_KEY"].strip()
    adapter = HermesRestAdapter(base_url=base, shared_secret=secret, max_retries=2)
    status = adapter.health_check()
    if not status.reachable:
        print("ERROR: Hermes health_check not reachable")
        sys.exit(1)
    payload = DelegationBuilder.build(
        task_id="operational-smoke",
        intent="operational smoke echo",
        priority=1,
    )
    try:
        receipt = adapter.enqueue_task(payload)
    except HermesError as exc:
        print(f"ERROR enqueue: {exc}")
        sys.exit(1)
    adapter.cancel_task(receipt.delegation_id)
    print(
        f"[3/5] hermes REST OK: mode={status.mode} "
        f"delegation_id={receipt.delegation_id}"
    )


def _check_cli_approval(workspace: Path) -> str:
    os.environ["ATLAS_HOME"] = str(workspace)
    os.environ.setdefault(
        "ATLAS_PENDING_HMAC_KEY",
        os.environ.get("ATLAS_PENDING_HMAC_KEY") or os.environ.get("HERMES_API_KEY", ""),
    )
    orch = Orchestrator(workspace=workspace)
    intent = "editor write projects/operational_smoke.txt :: hello operational"
    task = orch.handle_intent(intent)
    if task.status != TaskStatus.AWAITING_APPROVAL:
        print(f"ERROR: expected awaiting_approval, got {task.status.value}")
        sys.exit(1)
    pending_dir = workspace / "memory" / "pending_approvals"
    files = [p for p in pending_dir.glob("*.json") if ".executing" not in p.name]
    if not files:
        print("ERROR: no pending approval file written")
        sys.exit(1)
    result = orch.approve_pending(task.id, approved=True)
    if result.get("status") != "done":
        print(f"ERROR approve: {result}")
        sys.exit(1)
    out_file = workspace / "projects" / "operational_smoke.txt"
    if not out_file.exists() or "hello operational" not in out_file.read_text():
        print("ERROR: editor write did not create expected file")
        sys.exit(1)
    print(f"[4/5] CLI approval OK: task_id={task.id}")
    return task.id


def _check_telegram_outbound() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("[5/5] telegram SKIP (faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID)")
        return
    client = TelegramClient(token)
    try:
        client.send_message(
            chat_id=int(chat),
            text="Atlas operational_smoke.py OK",
        )
    except TelegramAPIError as exc:
        print(f"ERROR telegram: {exc}")
        sys.exit(1)
    print(f"[5/5] telegram outbound OK: chat_id={chat}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlas operational smoke")
    parser.add_argument("--skip-cli-approval", action="store_true")
    parser.add_argument("--skip-telegram", action="store_true")
    parser.add_argument("--workspace", type=Path, default=None)
    args = parser.parse_args()

    env_summary = _check_env()
    print(f"[1/5] env OK: {json.dumps(env_summary)}")

    if args.workspace is not None:
        workspace = args.workspace.expanduser().resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        tmp = tempfile.mkdtemp(prefix="atlas-op-smoke-")
        workspace = Path(tmp)
        cleanup = True

    try:
        _check_orchestrator_status(workspace)
        _check_hermes_rest()
        if not args.skip_cli_approval:
            _check_cli_approval(workspace)
        else:
            print("[4/5] CLI approval SKIP")
        if not args.skip_telegram:
            _check_telegram_outbound()
        else:
            print("[5/5] telegram SKIP")
    finally:
        if cleanup:
            import shutil
            shutil.rmtree(workspace, ignore_errors=True)

    print("=== Summary ===")
    print("  Operational smoke: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
