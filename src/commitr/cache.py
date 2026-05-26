"""On-disk cache for generated commit messages keyed by (diff, model, style)."""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


CACHE_DIR = Path(
    os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
) / "commitr"

# Hard cap so the cache doesn't grow without bound. LRU-by-mtime eviction.
MAX_ENTRIES = 200
# Default TTL: a week. Diffs older than this almost certainly don't apply
# anymore (rebased, force-pushed, restructured).
DEFAULT_TTL_SECONDS = 7 * 24 * 3600


@dataclass(frozen=True)
class CacheEntry:
    message: str
    model: str
    created_at: float


def _key(diff: str, model: str, style_signature: str) -> str:
    """Stable hash of inputs that should invalidate a cached message."""
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(style_signature.encode("utf-8"))
    h.update(b"\x00")
    h.update(diff.encode("utf-8"))
    return h.hexdigest()


def _path_for(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def lookup(
    diff: str,
    model: str,
    style_signature: str = "",
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> CacheEntry | None:
    """Return a fresh cached entry, or None on miss / stale / read error."""
    if not diff or not model:
        return None
    path = _path_for(_key(diff, model, style_signature))
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    created_at = float(data.get("created_at", 0))
    if ttl_seconds > 0 and time.time() - created_at > ttl_seconds:
        try:
            path.unlink()
        except OSError:
            pass
        return None
    # Touch atime/mtime so LRU eviction keeps the recently-used.
    try:
        os.utime(path, None)
    except OSError:
        pass
    return CacheEntry(
        message=str(data.get("message", "")),
        model=str(data.get("model", model)),
        created_at=created_at,
    )


def store(
    diff: str,
    model: str,
    message: str,
    style_signature: str = "",
) -> Path | None:
    """Write a cache entry. Returns the path or None if anything went wrong."""
    if not diff or not model or not message:
        return None
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    path = _path_for(_key(diff, model, style_signature))
    payload = {
        "message": message,
        "model": model,
        "created_at": time.time(),
    }
    try:
        path.write_text(json.dumps(payload))
    except OSError:
        return None
    _evict_if_needed()
    return path


def clear() -> int:
    """Delete every cache entry. Returns the number of files removed."""
    if not CACHE_DIR.exists():
        return 0
    count = 0
    for entry in CACHE_DIR.glob("*.json"):
        try:
            entry.unlink()
            count += 1
        except OSError:
            pass
    return count


def stats() -> dict[str, int]:
    """Return basic cache stats for inspection."""
    if not CACHE_DIR.exists():
        return {"entries": 0, "bytes": 0}
    total_bytes = 0
    count = 0
    for entry in CACHE_DIR.glob("*.json"):
        try:
            total_bytes += entry.stat().st_size
            count += 1
        except OSError:
            pass
    return {"entries": count, "bytes": total_bytes}


def _evict_if_needed() -> None:
    """Drop the oldest entries (by mtime) once we exceed MAX_ENTRIES."""
    if not CACHE_DIR.exists():
        return
    entries: list[tuple[float, Path]] = []
    for path in CACHE_DIR.glob("*.json"):
        try:
            entries.append((path.stat().st_mtime, path))
        except OSError:
            continue
    if len(entries) <= MAX_ENTRIES:
        return
    entries.sort(key=lambda item: item[0])  # oldest first
    for _, path in entries[: len(entries) - MAX_ENTRIES]:
        try:
            path.unlink()
        except OSError:
            pass
