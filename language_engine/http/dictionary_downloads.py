"""Reader HTTP dictionary downloads."""

import gzip as _gzip
import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
)

from language_registry import (
    LANGUAGE_REGISTRY,
    get_tsv_path,
    resolve_lang_code,
)

from .settings import APP_ROOT

bp = Blueprint("dictionary_downloads", __name__)

_DICT_GZIP_CACHE_DIR = APP_ROOT / "runtime_cache" / "dict_gzip"


_DICT_GZIP_EVENT_LOG_PATH = _DICT_GZIP_CACHE_DIR / "gzip_cache_events.jsonl"


_gzipped_tsv_lock = threading.Lock()


_gzip_event_log_lock = threading.Lock()


def _log_gzip_event(event: str, **fields) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": str(event or "").strip(),
    }
    payload.update(fields)
    try:
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with _gzip_event_log_lock:
            with _DICT_GZIP_EVENT_LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception:
        pass


def _dict_version_from_path(tsv_path: Path) -> str:
    st = tsv_path.stat()
    return f"{int(st.st_mtime_ns)}-{int(st.st_size)}"


def _resolve_dict_tsv_path(lang_code: str, source: str = "") -> Path | None:
    tsv_path = None
    if source:
        info = LANGUAGE_REGISTRY.get(lang_code, {})
        ds = info.get("dict_sources", {})
        if source in ds and ds[source].get("dict_file"):
            p = APP_ROOT / ds[source]["dict_file"]
            if p.exists():
                tsv_path = p
    if not tsv_path:
        tsv_path = get_tsv_path(lang_code)
    return tsv_path


def _dict_gzip_cache_paths(
    tsv_path: Path, lang_code: str, source: str, version: str
) -> tuple[Path, Path]:
    src_path = str(tsv_path.resolve())
    raw_key = f"{lang_code}|{source}|{src_path}|{version}"
    digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:20]
    gz_path = (
        _DICT_GZIP_CACHE_DIR / f"{lang_code}-{source or 'default'}-{digest}.tsv.gz"
    )
    meta_path = (
        _DICT_GZIP_CACHE_DIR / f"{lang_code}-{source or 'default'}-{digest}.json"
    )
    return gz_path, meta_path


def _ensure_cached_gzip_tsv(
    lang_code: str, source: str = ""
) -> tuple[Path | None, str]:
    """Return (gz_path, version) for a language, writing a runtime .gz cache if needed.

    If source is given and matches a dict_sources key, serve that file instead.
    """
    started = time.perf_counter()
    _DICT_GZIP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tsv_path = _resolve_dict_tsv_path(lang_code, source=source)
    if not tsv_path:
        _log_gzip_event(
            "builtin_cache_missing_source",
            kind="builtin",
            lang=lang_code,
            source=source,
        )
        return None, ""

    version = _dict_version_from_path(tsv_path)
    gz_path, meta_path = _dict_gzip_cache_paths(tsv_path, lang_code, source, version)

    with _gzipped_tsv_lock:
        existing_meta = {}
        if gz_path.exists() and meta_path.exists():
            try:
                existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                existing_meta = {}
            if (
                existing_meta.get("version") == version
                and existing_meta.get("source_path") == str(tsv_path.resolve())
                and existing_meta.get("gz_size")
                and gz_path.stat().st_size == int(existing_meta.get("gz_size"))
            ):
                _log_gzip_event(
                    "builtin_cache_hit",
                    kind="builtin",
                    lang=lang_code,
                    source=source,
                    source_path=str(tsv_path.resolve()),
                    version=version,
                    gz_path=str(gz_path.resolve()),
                    gz_size=gz_path.stat().st_size,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
                return gz_path, version

        tmp_gz_path = gz_path.with_suffix(gz_path.suffix + ".tmp")
        tmp_meta_path = meta_path.with_suffix(meta_path.suffix + ".tmp")
        with (
            tsv_path.open("rb") as src_fh,
            _gzip.open(tmp_gz_path, "wb", compresslevel=9) as gz_fh,
        ):
            while True:
                chunk = src_fh.read(1024 * 1024)
                if not chunk:
                    break
                gz_fh.write(chunk)
        gz_size = tmp_gz_path.stat().st_size
        tmp_meta_path.write_text(
            json.dumps(
                {
                    "version": version,
                    "source_path": str(tsv_path.resolve()),
                    "gz_size": gz_size,
                }
            ),
            encoding="utf-8",
        )
        tmp_gz_path.replace(gz_path)
        tmp_meta_path.replace(meta_path)
        _log_gzip_event(
            "builtin_cache_rebuild",
            kind="builtin",
            lang=lang_code,
            source=source,
            source_path=str(tsv_path.resolve()),
            version=version,
            previous_version=existing_meta.get("version", ""),
            gz_path=str(gz_path.resolve()),
            gz_size=gz_size,
            reason=(
                "missing_cache"
                if not existing_meta
                else (
                    "version_changed"
                    if existing_meta.get("version") != version
                    else "metadata_mismatch"
                )
            ),
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return gz_path, version


def _stream_gzip_file(gz_path: Path):
    chunk_size = 65536  # 64 KB chunks for visible streaming progress
    with gz_path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            yield chunk


def _build_gzip_response(gz_path: Path, filename: str) -> Response:
    total = gz_path.stat().st_size
    return Response(
        _stream_gzip_file(gz_path),
        mimetype="application/gzip",
        direct_passthrough=True,
        headers={
            "Content-Encoding": "identity",  # raw gzip bytes, not HTTP-level encoding
            "Content-Disposition": f"inline; filename={filename}",
            "Content-Length": str(total),
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@bp.route("/api/dict/<lang_code>")
def serve_dict(lang_code):
    """Serve a gzipped TSV dictionary for client-side storage.

    Accepts optional ?source= to serve an alternative dictionary
    (e.g. ?source=jmdict, ?source=cc-cedict, ?source=monier-williams).
    """
    code = resolve_lang_code(lang_code) or lang_code
    source = request.args.get("source", "").strip()
    gz_path, _version = _ensure_cached_gzip_tsv(code, source=source)
    if not gz_path:
        return jsonify({"ok": False, "error": f"No dictionary for {lang_code}"}), 404
    fn = f"dict-{code}-{source}.tsv.gz" if source else f"dict-{code}.tsv.gz"
    _log_gzip_event(
        "builtin_cache_served",
        kind="builtin",
        lang=code,
        source=source,
        gz_path=str(gz_path.resolve()),
        gz_size=gz_path.stat().st_size,
        filename=fn,
    )
    return _build_gzip_response(gz_path, fn)
