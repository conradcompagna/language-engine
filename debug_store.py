"""
Shared debug data store.

Any pipeline can write to `last_lookup` after processing.
The debug panel reads from it to display raw transformer output.
"""

import json
import os
import threading
import time

_lock = threading.Lock()

last_lookup = None  # Dict with debug snapshot, or None
_json_artifacts = {}  # {(capture_id, slug): {"text": str, "meta": dict}}
_MAX_JSON_ARTIFACTS = 1

def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on"}


_ENV_NAME = (os.environ.get("LE_ENV") or os.environ.get("FLASK_ENV") or "").strip().lower()
_IS_PRODUCTION = _ENV_NAME in {"production", "prod"}

# Master switch for debug-data collection.
DEBUG_COLLECTION_ENABLED = _env_bool("LE_DEBUG_COLLECTION", default=not _IS_PRODUCTION)

# MWT realigner traces piggyback on the master DEBUG_COLLECTION_ENABLED flag.
# When that master switch is off, _realign_mwt_children takes ZERO debug
# actions — no dict allocation, no list appends, no opcode recording.
_mwt_realign_traces = []  # list of per-parent trace dicts (most recent first)
_MAX_MWT_REALIGN_TRACES = 64


def is_debug_collection_enabled() -> bool:
    return bool(DEBUG_COLLECTION_ENABLED)


def is_mwt_realign_debug_enabled() -> bool:
    # Tied to the master flag — no separate toggle.
    return bool(DEBUG_COLLECTION_ENABLED)


def push_mwt_realign_trace(entry: dict) -> None:
    """Record a realigner trace. No-op when master debug collection is off."""
    if not DEBUG_COLLECTION_ENABLED:
        return
    with _lock:
        _mwt_realign_traces.insert(0, dict(entry or {}))
        if len(_mwt_realign_traces) > _MAX_MWT_REALIGN_TRACES:
            del _mwt_realign_traces[_MAX_MWT_REALIGN_TRACES:]


def get_mwt_realign_traces() -> list:
    if not DEBUG_COLLECTION_ENABLED:
        return []
    with _lock:
        return [dict(e) for e in _mwt_realign_traces]


def clear_mwt_realign_traces() -> None:
    with _lock:
        _mwt_realign_traces.clear()


def store_debug_snapshot(snapshot: dict):
    global last_lookup
    if not DEBUG_COLLECTION_ENABLED:
        return
    snap = dict(snapshot or {})
    snap["_timestamp"] = time.time()
    with _lock:
        last_lookup = snap


def update_debug_snapshot(patch: dict):
    """Merge fields into the latest snapshot and refresh its timestamp."""
    global last_lookup
    if not DEBUG_COLLECTION_ENABLED:
        return
    with _lock:
        base = dict(last_lookup) if isinstance(last_lookup, dict) else {}
        base.update(dict(patch or {}))
        base["_timestamp"] = time.time()
        last_lookup = base


def get_debug_snapshot() -> dict | None:
    if not DEBUG_COLLECTION_ENABLED:
        return None
    with _lock:
        return last_lookup


def store_debug_json_artifact(
    capture_id: str,
    slug: str,
    payload,
    *,
    filename: str = "",
    content_type: str = "application/json; charset=utf-8",
):
    if not DEBUG_COLLECTION_ENABLED:
        return None
    capture = str(capture_id or "").strip()
    artifact_slug = str(slug or "").strip()
    if not capture or not artifact_slug:
        return None
    try:
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception:
        text = json.dumps(
            {"ok": False, "error": "artifact_serialization_failed"},
            ensure_ascii=False,
            indent=2,
        )
    payload_bytes = len(text.encode("utf-8"))
    now = time.time()
    safe_filename = str(filename or "").strip() or f"{capture}-{artifact_slug}.json"
    meta = {
        "capture_id": capture,
        "slug": artifact_slug,
        "filename": safe_filename,
        "content_type": str(content_type or "application/json; charset=utf-8"),
        "size_bytes": payload_bytes,
        "created_at": now,
    }
    with _lock:
        _json_artifacts[(capture, artifact_slug)] = {
            "text": text,
            "meta": dict(meta),
        }
        if len(_json_artifacts) > _MAX_JSON_ARTIFACTS:
            ordered = sorted(
                _json_artifacts.items(),
                key=lambda item: float((item[1] or {}).get("meta", {}).get("created_at") or 0.0),
                reverse=True,
            )
            keep = {key for key, _value in ordered[:_MAX_JSON_ARTIFACTS]}
            stale = [key for key in list(_json_artifacts.keys()) if key not in keep]
            for key in stale:
                _json_artifacts.pop(key, None)
    return dict(meta)


def get_debug_json_artifact(capture_id: str, slug: str):
    if not DEBUG_COLLECTION_ENABLED:
        return None
    capture = str(capture_id or "").strip()
    artifact_slug = str(slug or "").strip()
    if not capture or not artifact_slug:
        return None
    with _lock:
        entry = _json_artifacts.get((capture, artifact_slug))
        if not isinstance(entry, dict):
            return None
        meta = entry.get("meta")
        return {
            "text": entry.get("text", ""),
            "meta": dict(meta) if isinstance(meta, dict) else {},
        }


def get_debug_json_artifact_meta(capture_id: str, slug: str):
    entry = get_debug_json_artifact(capture_id, slug)
    if not isinstance(entry, dict):
        return None
    meta = entry.get("meta")
    return dict(meta) if isinstance(meta, dict) else None
