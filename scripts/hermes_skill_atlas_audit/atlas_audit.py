#!/usr/bin/env python3
"""
atlas_audit — Hermes-side client that records a Hermes action into Atlas's
append-only Merkle ledger (ADR-029, reverse twin direction).

Hermes-Agent runs unaudited natively. This posts a single action to Atlas's
`/api/exec/audit` endpoint so it gains a tamper-evident receipt (hash-chained
in Atlas). Stdlib only (urllib + hmac), so it runs on the VPS with no extra
install.

Auth mirrors the inbound /api/exec/* contract: HMAC-SHA256 over the raw body
with HERMES_API_KEY, plus an ISO-8601 timestamp header (replay window 300s).

Usage:
    atlas_audit.py --action skill.run --result success --risk moderate \\
        --payload '{"skill": "weather", "duration_ms": 812}'

Env:
    HERMES_API_KEY   shared secret (same key the inbound endpoints use)
    ATLAS_AUDIT_URL  override (default http://100.85.236.58:7331/api/exec/audit)
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_URL = "http://100.85.236.58:7331/api/exec/audit"  # Atlas over Tailscale


def main() -> int:
    ap = argparse.ArgumentParser(description="Record a Hermes action in Atlas's Merkle ledger.")
    ap.add_argument("--action", required=True, help="e.g. skill.run, cron.tick, telegram.reply")
    ap.add_argument("--result", default="success",
                    choices=["success", "failure", "blocked", "pending", "refused"])
    ap.add_argument("--risk", default="safe", dest="risk_level",
                    choices=["safe", "moderate", "high", "critical"])
    ap.add_argument("--payload", default="{}", help="JSON object of structured facts")
    ap.add_argument("--url", default=os.environ.get("ATLAS_AUDIT_URL", DEFAULT_URL))
    ap.add_argument("--timeout", type=float, default=10.0)
    args = ap.parse_args()

    secret = os.environ.get("HERMES_API_KEY", "").strip()
    if not secret:
        print("HERMES_API_KEY not set", file=sys.stderr)
        return 2

    try:
        payload_obj = json.loads(args.payload)
        if not isinstance(payload_obj, dict):
            raise ValueError("payload must be a JSON object")
    except ValueError as exc:
        print(f"bad --payload: {exc}", file=sys.stderr)
        return 2

    body = json.dumps({
        "action": args.action,
        "result": args.result,
        "risk_level": args.risk_level,
        "payload": payload_obj,
    }).encode("utf-8")

    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        args.url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Hermes-Signature": sig,
            "X-Hermes-Timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            out = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        print(f"atlas refused ({exc.code}): {exc.read().decode('utf-8', 'replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"atlas unreachable: {exc.reason}", file=sys.stderr)
        return 1

    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
