#!/usr/bin/env python3
"""Smoke de compatibilidad del HermesRestAdapter legado.

NO prueba el Hermes-Agent oficial, la skill atlas-twin, un proveedor ni
Telegram. Este script muta la cola REST creando y cancelando una tarea.

Uso:
    PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- \
      .venv/bin/python scripts/hermes_smoke.py

Comprueba:
  1) health_check responde
  2) enqueue_task acepta una tarea trivial
  3) get_queue_status devuelve depth coherente
  4) cancel_task limpia la tarea creada
"""

from __future__ import annotations

import os
import sys

from atlas.hermes.hermes import DelegationBuilder, HermesError, HermesRestAdapter


def main() -> int:
    base_url = os.environ.get("HERMES_BASE_URL")
    secret = os.environ.get("HERMES_API_KEY")
    if not base_url or not secret:
        print("ERROR: HERMES_BASE_URL y HERMES_API_KEY deben estar en el entorno.")
        return 2

    adapter = HermesRestAdapter(base_url=base_url, shared_secret=secret, max_retries=2)

    print(f"[1/4] health_check {base_url} ...")
    status = adapter.health_check()
    print(f"      reachable={status.reachable} mode={status.mode} version={status.version}")
    if not status.reachable:
        print("ERROR: Hermes no es alcanzable.")
        return 1

    print("[2/4] enqueue_task echo ...")
    payload = DelegationBuilder.build(task_id="smoke-1", intent="echo smoke", priority=1)
    try:
        receipt = adapter.enqueue_task(payload)
    except HermesError as exc:
        print(f"ERROR enqueue: {exc}")
        return 1
    print(f"      accepted={receipt.accepted} delegation_id={receipt.delegation_id}")

    print("[3/4] get_queue_status ...")
    qs = adapter.get_queue_status()
    print(f"      depth={qs.depth} next={qs.next_task_id}")

    print("[4/4] cancel_task ...")
    ok = adapter.cancel_task(receipt.delegation_id)
    print(f"      cancelled={ok}")

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
