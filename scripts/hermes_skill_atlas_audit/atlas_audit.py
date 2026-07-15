#!/usr/bin/env python3
"""Compatibility entry point for the superseding atlas-twin skill client."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit


def _legacy_url_to_origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.path != "/api/exec/audit" or parsed.query or parsed.fragment:
        raise ValueError("legacy --url must end exactly in /api/exec/audit")
    return f"{parsed.scheme}://{parsed.netloc}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper for atlas-twin audit",
    )
    parser.add_argument("--action", required=True)
    parser.add_argument(
        "--result",
        default="success",
        choices=["success", "failure", "blocked", "pending", "refused"],
    )
    parser.add_argument(
        "--risk",
        default="safe",
        choices=["safe", "moderate", "high", "critical"],
    )
    parser.add_argument("--payload", default="{}")
    parser.add_argument("--url", default=os.environ.get("ATLAS_AUDIT_URL", ""))
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    hermes_home = Path(
        os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    ).expanduser()
    client = hermes_home / "skills" / "atlas-twin" / "atlas_twin.py"
    if client.is_symlink() or not client.is_file():
        print("atlas-twin skill is not installed", file=sys.stderr)
        return 2

    argv = [
        sys.executable,
        str(client),
        "--timeout",
        str(args.timeout),
    ]
    if args.url:
        try:
            origin = _legacy_url_to_origin(args.url)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        argv.extend(["--base-url", origin])
    argv.extend([
        "audit",
        args.action,
        "--result",
        args.result,
        "--risk",
        args.risk,
        "--payload",
        args.payload,
    ])
    os.execv(sys.executable, argv)
    return 1  # unreachable; keeps the return contract explicit for type checkers


if __name__ == "__main__":
    raise SystemExit(main())
