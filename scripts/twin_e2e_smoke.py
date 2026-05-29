#!/usr/bin/env python3
"""
Smoke E2E del twin Hermes -> Atlas (ADR-027 + ADR-031).

Sella el circuito reverso: Hermes (VPS) delega un intent a Atlas via
POST /api/exec/intent (HMAC), Atlas lo resuelve con grounding real (git_log,
no alucinacion) y devuelve el resultado auditado.

Dos modos:

  LOCAL (por defecto) — in-process, sin servicios vivos:
      PYTHONPATH=src python scripts/twin_e2e_smoke.py
    Levanta un Orchestrator sobre un ATLAS_HOME aislado que es un repo git
    real con commits conocidos, monta el router /api/exec via TestClient y
    verifica que el intent "dame los ultimos commits" devuelve esos commits
    EXACTOS (grounding) y que el Merkle registro el circuito. No toca el
    workspace vivo (~/atlas), asi que es seguro con el servicio corriendo.

  LIVE — contra un Atlas que ya esta sirviendo /api/exec:
      HERMES_API_KEY=<secret> \
      PYTHONPATH=src python scripts/twin_e2e_smoke.py --live https://atlas.tail-xxxx.ts.net
    Firma y envia el POST por red, igual que haria Hermes desde el VPS.

Sale 0 si el circuito esta sellado, !=0 si algo falla.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HEADER_SIGNATURE = "X-Hermes-Signature"
HEADER_TIMESTAMP = "X-Hermes-Timestamp"

# Commits sembrados en el repo aislado; el intent debe devolverlos tal cual.
SEED_COMMITS = ("twin smoke: segundo commit", "twin smoke: primer commit")
INTENT = "dame los ultimos commits"


def _sign(secret: str, body: bytes) -> dict[str, str]:
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {
        HEADER_SIGNATURE: sig,
        HEADER_TIMESTAMP: datetime.now(timezone.utc).isoformat(),
    }


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "twin-smoke",
            "GIT_AUTHOR_EMAIL": "twin@atlas.local",
            "GIT_COMMITTER_NAME": "twin-smoke",
            "GIT_COMMITTER_EMAIL": "twin@atlas.local",
        },
    )


def _seed_repo(repo: Path) -> None:
    """Convierte `repo` en un git repo con dos commits conocidos."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("atlas twin smoke\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", SEED_COMMITS[1])
    (repo / "README.md").write_text("atlas twin smoke v2\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", SEED_COMMITS[0])


def _check_response(data: dict) -> int:
    print(f"      ok={data.get('ok')} status={data.get('status')} "
          f"route={data.get('route')} tool={data.get('tool')}")
    result = data.get("result")
    blob = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    grounded = all(subject in blob for subject in SEED_COMMITS)
    if not grounded:
        print("ERROR: la respuesta NO contiene los commits reales sembrados.")
        print(f"       esperaba: {SEED_COMMITS}")
        print(f"       recibido: {blob[:400]}")
        return 1
    print("      grounding OK: la respuesta contiene los commits reales (sin alucinacion).")
    return 0


def run_local() -> int:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from atlas.core.contracts import TaskSource  # noqa: F401  (sanity import)
    from atlas.core.orchestrator import Orchestrator
    from atlas.interfaces.exec_api import build_router

    secret = os.environ.get("HERMES_API_KEY", "twin-e2e-smoke-secret")

    with tempfile.TemporaryDirectory(prefix="atlas-twin-smoke-") as td:
        workspace = Path(td) / "atlas"
        os.environ["ATLAS_HOME"] = str(workspace)
        os.environ["HERMES_API_KEY"] = secret

        print(f"[1/4] sembrando repo git aislado en {workspace} ...")
        _seed_repo(workspace)

        print("[2/4] arrancando Orchestrator + router /api/exec (in-process) ...")
        orch = Orchestrator(workspace=workspace)
        # El repo se siembra ANTES de _init_dirs? Orchestrator ya creo subdirs;
        # reaseguramos que .git sigue ahi (init_dirs no lo borra).
        assert (workspace / ".git").exists(), ".git desaparecio tras init del orquestador"
        app = FastAPI()
        app.include_router(build_router(lambda: orch))
        client = TestClient(app)

        print(f"[3/4] POST /api/exec/intent  intent={INTENT!r} (firmado HMAC) ...")
        body = json.dumps({"intent": INTENT}).encode()
        r = client.post("/api/exec/intent", content=body, headers=_sign(secret, body))
        if r.status_code != 200:
            print(f"ERROR: status HTTP {r.status_code}: {r.text}")
            return 1
        rc = _check_response(r.json())
        if rc != 0:
            return rc

        print("[4/4] verificando cadena Merkle del circuito ...")
        recent = orch._merkle.tail(12)
        actions = [rec.action for rec in recent]
        via_hermes = [a for a in actions if a == "exec.intent.via_hermes"]
        if not via_hermes:
            print(f"ERROR: no se registro exec.intent.via_hermes. acciones={actions}")
            return 1
        print(f"      Merkle OK: exec.intent.via_hermes presente. recientes={actions[-6:]}")

    print("OK — circuito twin Hermes->Atlas sellado (grounding + auditoria).")
    return 0


def run_live(base_url: str) -> int:
    import urllib.request

    secret = os.environ.get("HERMES_API_KEY")
    if not secret:
        print("ERROR: HERMES_API_KEY requerido en modo --live.")
        return 2

    url = base_url.rstrip("/") + "/api/exec/intent"
    body = json.dumps({"intent": INTENT}).encode()
    headers = {"Content-Type": "application/json", **_sign(secret, body)}
    print(f"[live] POST {url}  intent={INTENT!r} ...")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: peticion fallo: {exc}")
        return 1

    # En modo live no controlamos los commits del repo destino; basta con que
    # el intent se resuelva (done) y devuelva contenido de git.
    print(f"      ok={data.get('ok')} status={data.get('status')} "
          f"route={data.get('route')} tool={data.get('tool')}")
    if data.get("status") != "done":
        print(f"ERROR: el intent no termino en 'done': {data}")
        return 1
    print("OK — Atlas vivo resolvio el intent delegado via HMAC.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke E2E twin Hermes->Atlas")
    parser.add_argument(
        "--live", metavar="BASE_URL", default=None,
        help="URL base de un Atlas vivo (modo red). Por defecto: in-process.",
    )
    ns = parser.parse_args()
    if ns.live:
        return run_live(ns.live)
    return run_local()


if __name__ == "__main__":
    sys.exit(main())
