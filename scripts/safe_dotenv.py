#!/usr/bin/env python3
"""Execute a command with a secured dotenv file parsed strictly as data."""

from __future__ import annotations

import ast
import os
import re
import stat
import sys
from pathlib import Path


MAX_ENV_BYTES = 1_048_576
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DotenvError(RuntimeError):
    """A safe, value-free dotenv validation error."""


def _read_regular_private_file(path: Path) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise DotenvError("could not securely open dotenv file") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise DotenvError("dotenv file must be a regular non-symlink file")
        if metadata.st_uid != os.geteuid():
            raise DotenvError("dotenv file must be owned by the current user")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise DotenvError("dotenv permissions must deny group and other access")
        if metadata.st_size > MAX_ENV_BYTES:
            raise DotenvError("dotenv file is too large")
        with os.fdopen(fd, encoding="utf-8") as handle:
            fd = -1
            return handle.read(MAX_ENV_BYTES + 1)
    except UnicodeDecodeError as exc:
        raise DotenvError("dotenv file must be valid UTF-8") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def parse_dotenv(path: Path) -> dict[str, str]:
    raw = _read_regular_private_file(path)
    if len(raw.encode("utf-8")) > MAX_ENV_BYTES:
        raise DotenvError("dotenv file is too large")
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(raw.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, encoded_value = line.partition("=")
        key = key.strip()
        if not separator or not KEY_RE.fullmatch(key):
            raise DotenvError(f"unsupported dotenv syntax at line {line_number}")
        if key in values:
            raise DotenvError(f"duplicate dotenv key at line {line_number}")
        value = encoded_value.strip()
        if value[:1] in {"'", '"'}:
            try:
                decoded = ast.literal_eval(value)
            except (SyntaxError, ValueError) as exc:
                raise DotenvError(f"invalid quoted value at line {line_number}") from exc
            if not isinstance(decoded, str):
                raise DotenvError(f"non-string quoted value at line {line_number}")
            value = decoded
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        if "\x00" in value or "\n" in value or "\r" in value:
            raise DotenvError(f"dotenv value must be single-line at line {line_number}")
        values[key] = value
    return values


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3 or args[1] != "--":
        print("Usage: safe_dotenv.py ENV_FILE -- COMMAND [ARG ...]", file=sys.stderr)
        return 64
    path = Path(args[0]).expanduser()
    command = args[2:]
    try:
        values = parse_dotenv(path)
        environment = os.environ.copy()
        environment.update(values)
        os.execvpe(command[0], command, environment)
    except DotenvError as exc:
        print(f"safe_dotenv: ERROR: {exc}", file=sys.stderr)
        return 65
    except OSError as exc:
        print(f"safe_dotenv: ERROR: could not execute command ({type(exc).__name__})", file=sys.stderr)
        return 69
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
