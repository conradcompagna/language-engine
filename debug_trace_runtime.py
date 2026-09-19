import copy
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Mapping, Sequence

_ACTIVE_TRACE: ContextVar[dict[str, Any] | None] = ContextVar("active_debug_trace", default=None)


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _ensure_list_limit(items: list[Any], limit: int) -> None:
    if limit > 0 and len(items) > limit:
        del items[limit:]


def start_trace(
    *, language: str = "", query: str = "", capture_id: str = ""
) -> tuple[Any, dict[str, Any]]:
    trace_id = str(capture_id or uuid.uuid4().hex).strip()
    started_wall = time.time()
    started_ms = _now_ms()
    root = {
        "name": "lookup",
        "label": "Lookup",
        "meta": {
            "language": str(language or "").strip().lower(),
            "query": str(query or ""),
        },
        "started_ms": started_ms,
        "duration_ms": 0.0,
        "children": [],
    }
    state: dict[str, Any] = {
        "debug_capture_id": trace_id,
        "language": str(language or "").strip().lower(),
        "q": str(query or ""),
        "started_at": started_wall,
        "started_ms": started_ms,
        "root": root,
        "stack": [root],
        "normalizations": [],
        "sqlite_queries": [],
        "retrievals": [],
        "segmenter_events": [],
        "decoration_events": [],
        "final_payload": None,
    }
    token = _ACTIVE_TRACE.set(state)
    return token, state


def finish_trace(result_payload: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    state = _ACTIVE_TRACE.get()
    if not isinstance(state, dict):
        return None
    root = state.get("root") or {}
    root["duration_ms"] = max(
        0.0, _now_ms() - float(root.get("started_ms") or state.get("started_ms") or 0.0)
    )
    total_ms = float(root.get("duration_ms") or 0.0)
    if result_payload is not None:
        try:
            state["final_payload"] = copy.deepcopy(dict(result_payload))
        except Exception:
            state["final_payload"] = {"error": "payload_copy_failed"}
    for item in list(state.get("sqlite_queries") or []):
        if total_ms > 0:
            item["pct_total"] = round((float(item.get("duration_ms") or 0.0) / total_ms) * 100.0, 2)
    return {
        "debug_capture_id": state.get("debug_capture_id"),
        "language": state.get("language"),
        "q": state.get("q"),
        "started_at": state.get("started_at"),
        "total_ms": round(total_ms, 3),
        "timing_tree": copy.deepcopy(root),
        "normalizations": copy.deepcopy(list(state.get("normalizations") or [])),
        "sqlite_queries": copy.deepcopy(list(state.get("sqlite_queries") or [])),
        "retrievals": copy.deepcopy(list(state.get("retrievals") or [])),
        "segmenter_events": copy.deepcopy(list(state.get("segmenter_events") or [])),
        "decoration_events": copy.deepcopy(list(state.get("decoration_events") or [])),
        "final_payload": copy.deepcopy(state.get("final_payload")),
    }


def stop_trace(token: Any) -> None:
    try:
        _ACTIVE_TRACE.reset(token)
    except Exception:
        pass


def is_trace_active() -> bool:
    return isinstance(_ACTIVE_TRACE.get(), dict)


def _current_scope_name() -> str:
    state = _ACTIVE_TRACE.get()
    if not isinstance(state, dict):
        return ""
    stack = list(state.get("stack") or [])
    current = stack[-1] if stack else None
    if not isinstance(current, dict):
        return ""
    return str(current.get("name") or "").strip()


def _append_trace_item(bucket: str, item: dict[str, Any], *, limit: int = 400) -> None:
    state = _ACTIVE_TRACE.get()
    if not isinstance(state, dict):
        return
    entries = state.setdefault(bucket, [])
    if not isinstance(entries, list):
        return
    entries.append(item)
    _ensure_list_limit(entries, limit)


@contextmanager
def trace_scope(name: str, **meta: Any):
    state = _ACTIVE_TRACE.get()
    if not isinstance(state, dict):
        yield None
        return
    parent_stack = state.setdefault("stack", [])
    parent = parent_stack[-1] if parent_stack else state.get("root")
    node = {
        "name": str(name or "").strip(),
        "label": str(meta.pop("label", name or "")).strip(),
        "meta": dict(meta or {}),
        "started_ms": _now_ms(),
        "duration_ms": 0.0,
        "children": [],
    }
    if isinstance(parent, dict):
        parent.setdefault("children", []).append(node)
    parent_stack.append(node)
    try:
        yield node
    finally:
        node["duration_ms"] = max(0.0, _now_ms() - float(node.get("started_ms") or 0.0))
        try:
            parent_stack.pop()
        except Exception:
            pass


def record_normalization(
    *,
    raw_text: str,
    normalized_key: str,
    lang_code: str,
    kind: str = "",
    note: str = "",
    extra: Mapping[str, Any] | None = None,
) -> None:
    raw = str(raw_text or "")
    norm = str(normalized_key or "")
    item = {
        "scope": _current_scope_name(),
        "kind": str(kind or "").strip(),
        "lang": str(lang_code or "").strip().lower(),
        "raw_text": raw,
        "normalized_key": norm,
        "changed": raw != norm,
        "note": str(note or "").strip(),
    }
    if isinstance(extra, Mapping):
        item.update(dict(extra))
    _append_trace_item("normalizations", item, limit=1200)


def record_sqlite_query(
    *,
    sql: str,
    params: Sequence[Any] | None = None,
    duration_ms: float,
    row_count: int = 0,
    db_path: str = "",
    query_kind: str = "",
    extra: Mapping[str, Any] | None = None,
) -> None:
    item = {
        "scope": _current_scope_name(),
        "query_kind": str(query_kind or "").strip(),
        "db_path": str(db_path or "").strip(),
        "sql": " ".join(str(sql or "").split()),
        "params": [str(p) for p in list(params or [])],
        "param_count": len(list(params or [])),
        "row_count": int(row_count or 0),
        "duration_ms": round(float(duration_ms or 0.0), 3),
    }
    if isinstance(extra, Mapping):
        item.update(dict(extra))
    _append_trace_item("sqlite_queries", item, limit=1200)


def record_retrieval(
    *,
    normalized_key: str,
    entries: Sequence[Mapping[str, Any]] | None,
    source: str = "",
    extra: Mapping[str, Any] | None = None,
) -> None:
    preview = []
    for entry in list(entries or [])[:50]:
        if not isinstance(entry, Mapping):
            continue
        preview.append(
            {
                "headword": str(entry.get("headword") or ""),
                "pos_raw": str(entry.get("pos_raw") or entry.get("pos") or ""),
                "source": str(entry.get("source") or ""),
                "entry_id": str(entry.get("entry_id") or ""),
                "match_kind": str(entry.get("_match_kind") or ""),
                "matched_forms": copy.deepcopy(list(entry.get("_matched_forms") or [])),
            }
        )
    item = {
        "scope": _current_scope_name(),
        "normalized_key": str(normalized_key or "").strip(),
        "source": str(source or "").strip(),
        "entry_count": len(list(entries or [])),
        "entries": preview,
    }
    if isinstance(extra, Mapping):
        item.update(dict(extra))
    _append_trace_item("retrievals", item, limit=600)


def record_segmenter_event(kind: str, data: Mapping[str, Any] | None = None) -> None:
    item = {
        "scope": _current_scope_name(),
        "kind": str(kind or "").strip(),
    }
    if isinstance(data, Mapping):
        item.update(copy.deepcopy(dict(data)))
    _append_trace_item("segmenter_events", item, limit=800)


def record_decoration_event(kind: str, data: Mapping[str, Any] | None = None) -> None:
    item = {
        "scope": _current_scope_name(),
        "kind": str(kind or "").strip(),
    }
    if isinstance(data, Mapping):
        item.update(copy.deepcopy(dict(data)))
    _append_trace_item("decoration_events", item, limit=800)
