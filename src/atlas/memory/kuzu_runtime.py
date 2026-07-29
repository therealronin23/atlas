"""One bounded Kuzu opening profile for Atlas-owned graphs and indexes.

Kuzu's upstream constructor defaults to an 8-TiB virtual database map and a
buffer pool sized from host memory.  Those defaults are unsafe for local-first
Atlas processes and incompatible with the bounded ColdUpdate candidate jail.
All Atlas call sites open embedded Kuzu through this module so the resource
contract is explicit, reviewable, and shared by production and tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import kuzu


DEFAULT_KUZU_MAX_DB_SIZE_BYTES: Final = 1 << 30
DEFAULT_KUZU_BUFFER_POOL_SIZE_BYTES: Final = 1 << 28


def open_kuzu_database(
    db_path: str | Path,
    *,
    read_only: bool = False,
    max_db_size: int = DEFAULT_KUZU_MAX_DB_SIZE_BYTES,
    buffer_pool_size: int = DEFAULT_KUZU_BUFFER_POOL_SIZE_BYTES,
) -> kuzu.Database:
    """Open an Atlas Kuzu database with explicit, bounded resource settings.

    Callers may select a lower or larger documented profile deliberately, but
    cannot fall through to Kuzu's implicit host-sized defaults.  Invalid
    limits fail before the native engine is started.
    """
    if isinstance(max_db_size, bool) or max_db_size <= 0:
        raise ValueError("max_db_size must be a positive byte count")
    if isinstance(buffer_pool_size, bool) or buffer_pool_size <= 0:
        raise ValueError("buffer_pool_size must be a positive byte count")
    return kuzu.Database(
        str(db_path),
        read_only=read_only,
        max_db_size=max_db_size,
        buffer_pool_size=buffer_pool_size,
    )
