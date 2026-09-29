"""Reader HTTP startup."""

import json
from pathlib import Path

from flask import Blueprint, jsonify, request

from language_registry import LANGUAGE_REGISTRY, init_all

from .index_cache import (
    _JS_INDEX_ARTIFACT_DIR,
    _JS_INDEX_CACHE_DIR,
    _JS_INDEX_SCHEMA_VERSION,
    _js_index_artifact_name,
    _js_index_cache_is_fresh,
    _js_index_cache_path,
)

bp = Blueprint("startup", __name__)

_startup_preloaded = False


_js_index_versions: dict[str, str] = {}


_js_index_urls: dict[str, str] = {}


def _extract_version_from_gz(cache_path: Path) -> str:
    """Read version from a cached gzip index file without rebuilding."""
    try:
        import gzip as _gz

        raw = json.loads(_gz.decompress(cache_path.read_bytes()).decode("utf-8"))
        return str(raw.get("version") or "")
    except Exception:
        return ""


def _prebuild_js_index_cache() -> None:
    """Pre-build one compact JS key index per language × source (never bundled).

    Each source maps to exactly one SQLite file; the index alias equals the
    file stem so it stays consistent between build-time and hydration-time.
    Languages with no dict_sources get a single index from their default db.
    """
    import gzip as _gz
    import hashlib as _hashlib

    from dict_lookup_sqlite import (
        _resolve_all_db_paths,
        _resolve_db_path,
        build_compact_key_index,
    )

    _JS_INDEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _JS_INDEX_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _js_index_versions.clear()
    _js_index_urls.clear()
    built = skipped = failed = 0
    for code, info in LANGUAGE_REGISTRY.items():
        raw_sources = list((info.get("dict_sources") or {}).keys())
        # Filter out "custom" — custom entries are injected client-side, never indexed here.
        db_sources = [s for s in raw_sources if s and s != "custom"]
        # Languages with no named sources: build a single index from the default db.
        if not db_sources:
            db_sources = [""]

        for source in db_sources:
            ver_key = f"{code}:{source}" if source else code
            label = ver_key
            try:
                if source:
                    db_path = _resolve_db_path(code, source)
                    if not db_path:
                        print(f"[WARN] JS index: no db found for {label}, skipping")
                        continue
                    db_paths = [db_path]
                else:
                    # No named source: use the single default db only (not all dbs).
                    all_paths = _resolve_all_db_paths(code)
                    default = [p for p in all_paths if p.stem == code]
                    db_paths = (
                        default if default else (all_paths[:1] if all_paths else [])
                    )
                    if not db_paths:
                        continue

                cache_path = _js_index_cache_path(code, source)
                if _js_index_cache_is_fresh(
                    code,
                    cache_path,
                    db_paths,
                    include_custom_entries=False,
                    expected_schema_version=_JS_INDEX_SCHEMA_VERSION,
                ):
                    compressed = cache_path.read_bytes()
                    version = _extract_version_from_gz(cache_path)
                    skipped += 1
                else:
                    index = build_compact_key_index(
                        code, db_paths=db_paths, include_custom_entries=False
                    )
                    index["v"] = _JS_INDEX_SCHEMA_VERSION
                    index["lang"] = code
                    if source:
                        index["source"] = source
                    body_bytes = json.dumps(
                        index, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8")
                    version = _hashlib.sha1(body_bytes).hexdigest()[:16]
                    index["version"] = version
                    body_bytes = json.dumps(
                        index, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8")
                    compressed = _gz.compress(body_bytes, compresslevel=6)
                    cache_path.write_bytes(compressed)
                    built += 1
                    print(
                        f"[INFO] JS index built: {label} ({len(compressed) // 1024} KB)"
                    )

                if not version:
                    raise RuntimeError(f"Missing version for prebuilt index {label}")
                artifact_name = _js_index_artifact_name(code, source, version)
                artifact_path = _JS_INDEX_ARTIFACT_DIR / artifact_name
                if not artifact_path.exists() or artifact_path.stat().st_size != len(
                    compressed
                ):
                    artifact_path.write_bytes(compressed)
                _js_index_versions[ver_key] = version
                _js_index_urls[ver_key] = f"/dict-index/{artifact_name}"
            except Exception as exc:
                failed += 1
                print(
                    f"[WARN] JS index build failed for {label}: {type(exc).__name__}: {exc}"
                )
    print(
        f"[INFO] JS index cache ready: {built} built, {skipped} skipped, {failed} failed"
    )


@bp.route("/js/dict/versions")
def js_dict_versions():
    """Return in-memory version map for all prebuilt indexes. Pure memory read, no I/O."""
    response = jsonify(_js_index_versions)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@bp.route("/js/dict/<lang>/version")
def js_dict_lang_version(lang):
    """Return version string for a single language index. Pure memory read, no I/O."""
    lang = lang.lower().strip()
    source = request.args.get("source", "").lower().strip()
    ver_key = f"{lang}:{source}" if source else lang
    version = _js_index_versions.get(ver_key, "")
    response = jsonify({"version": version})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


def preload_startup_resources():
    """Load all shared resources once when the server process starts."""
    global _startup_preloaded
    if _startup_preloaded:
        return
    print("[INFO] Pre-loading all resources...")
    init_all()
    print("[INFO] Arabic tokenizer: native Trankit")
    print("[INFO] Arabic MWT expander locked to: disabled")
    print("[INFO] Pre-building JS compact key index cache...")
    _prebuild_js_index_cache()
    _startup_preloaded = True
