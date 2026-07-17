#!/usr/bin/env python3
"""Smoke operacional: estado del orchestrator, aprobación CLI y bot de Telegram.

ADR-070 retiró el canal REST legado de Hermes (HermesRestAdapter); este
script YA NO ejercita ningún contrato REST (ver
docs/decisions/adr/adr_070_retire_hermes_rest_adapter.md). El estado de
Hermes se sigue comprobando de forma generica sobre el adapter que este
configurado (kanban o mock).

NO prueba el Hermes-Agent oficial ni su Telegram. Puede aprobar una escritura
aislada y, si no se omite, enviar un mensaje real desde el bot propio de
Atlas. No se ejecuta desde la auditoría autónoma.

Uso:
    PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- \
      .venv/bin/python scripts/operational_smoke.py --skip-telegram

Opciones:
    --skip-cli-approval   No ejecuta ciclo editor write + approve en workspace temporal
    --send-telegram       Envia deliberadamente un mensaje real con el bot propio de Atlas
    --skip-telegram       Alias de compatibilidad; Telegram ya se omite por defecto
    --workspace PATH      Usar ATLAS_HOME existente (default: directorio temporal)

Comprueba:
  1) Orchestrator.status: governance + Merkle + Hermes reachable (adapter que
     este configurado — kanban o mock)
  2) (opcional) CLI approval: task -> pending -> approve -> done
  3) (opcional) Telegram outbound sendMessage
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
from atlas.interfaces.telegram_bot import TelegramAPIError, TelegramClient


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
    print(f"[1/3] orchestrator OK: {json.dumps(result)}")
    return result


def _check_cli_approval(workspace: Path) -> str:
    os.environ["ATLAS_HOME"] = str(workspace)
    os.environ.setdefault(
        "ATLAS_PENDING_HMAC_KEY",
        os.environ.get("ATLAS_PENDING_HMAC_KEY") or os.environ.get("HERMES_API_KEY", ""),
    )
    previous_decider = os.environ.get("ATLAS_DECIDER")
    try:
        # Este smoke valida el surface de pending approvals; si el entorno normal
        # está en modo autónomo, forzamos un decider humano solo para este subcheck.
        os.environ["ATLAS_DECIDER"] = "human"
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
        print(f"[2/3] CLI approval OK: task_id={task.id}")
        return task.id
    finally:
        if previous_decider is None:
            os.environ.pop("ATLAS_DECIDER", None)
        else:
            os.environ["ATLAS_DECIDER"] = previous_decider


def _check_telegram_outbound() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("[3/3] telegram SKIP (faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID)")
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
    print(f"[3/3] telegram outbound OK: chat_id={chat}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlas operational smoke")
    parser.add_argument("--skip-cli-approval", action="store_true")
    parser.add_argument("--skip-telegram", action="store_true")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--workspace", type=Path, default=None)
    args = parser.parse_args()

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
        if not args.skip_cli_approval:
            _check_cli_approval(workspace)
        else:
            print("[2/3] CLI approval SKIP")
        if args.send_telegram and not args.skip_telegram:
            _check_telegram_outbound()
        else:
            print("[3/3] telegram SKIP (use --send-telegram for an external message)")
    finally:
        if cleanup:
            import shutil
            shutil.rmtree(workspace, ignore_errors=True)

    print("=== Summary ===")
    print("  Operational smoke: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
