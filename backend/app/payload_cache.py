"""Tiny versioned cache for expensive dashboard/ops aggregations.

Reads are served from the SQLite work-order cache (wo_cache), not Excel, but
recomputing the aggregations over 2,194 records on every request still cost
seconds. This cache keys every payload by a cheap data version, so:

- tab switches / repeat visits are served instantly,
- the moment any underlying data changes (sync, save, seed, handover note)
  the version changes and the next request recomputes once,
- a TTL bounds staleness even if some write path were missed.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

TTL_SECONDS = 20.0
_store: dict[str, tuple[float, str, Any]] = {}


def data_version() -> str:
    """Cheap fingerprint of everything the aggregations read: the cached
    work-order rows (SQLite), published handover notes, and the config file."""
    from . import database
    from .config import CONFIG_PATH

    wo_ver = database.wo_cache_version()
    hand_ver = database.handovers_version()
    try:
        cfg_mt = int(CONFIG_PATH.stat().st_mtime * 1000) if CONFIG_PATH.exists() else 0
    except OSError:
        cfg_mt = 0
    return f"{wo_ver}|{hand_ver}|{cfg_mt}"


def get_or_set(key: str, build: Callable[[], Any], ttl: float = TTL_SECONDS) -> Any:
    version = data_version()
    now = time.monotonic()
    hit = _store.get(key)
    if hit is not None and hit[1] == version and (now - hit[0]) < ttl:
        return hit[2]
    value = build()
    if len(_store) > 64:
        _store.clear()
    _store[key] = (now, version, value)
    return value


def peek(key: str) -> Optional[Any]:
    hit = _store.get(key)
    return hit[2] if hit else None


def invalidate() -> None:
    _store.clear()
