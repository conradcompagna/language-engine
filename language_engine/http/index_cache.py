"""Reader HTTP index cache."""

import json
from pathlib import Path

from .settings import APP_ROOT

_JS_INDEX_CACHE_DIR = APP_ROOT / "runtime_cache" / "js_index"


_JS_INDEX_ARTIFACT_DIR = APP_ROOT / "runtime_cache" / "dict_index_artifacts"


_JS_INDEX_SCHEMA_VERSION = 6


def _js_index_cache_path(lang_code: str, source: str = "") -> Path:
    if source:
        return _JS_INDEX_CACHE_DIR / f"{lang_code}-{source}.json.gz"
    return _JS_INDEX_CACHE_DIR / f"{lang_code}.json.gz"


def _js_index_artifact_name(lang_code: str, source: str, version: str) -> str:
    base = f"{lang_code}-{source}" if source else lang_code
    return f"{base}.{version}.json.gz"


def _js_index_cache_schema_version(cache_path: Path) -> int:
    try:
        import gzip as _gz

        raw = json.loads(_gz.decompress(cache_path.read_bytes()).decode("utf-8"))
        return int(raw.get("v") or 0)
    except Exception:
        return 0


def _js_index_cache_is_fresh(
    lang_code: str,
    cache_path: Path,
    db_paths: list,
    include_custom_entries: bool = True,
    expected_schema_version: int = _JS_INDEX_SCHEMA_VERSION,
) -> bool:
    """Return True if cache matches schema and is newer than all source .sqlite files."""
    if not cache_path.exists():
        return False
    if expected_schema_version and _js_index_cache_schema_version(cache_path) != int(
        expected_schema_version
    ):
        return False
    cache_mtime = cache_path.stat().st_mtime
    from dict_lookup_sqlite import APP_DB_PATH

    for p in db_paths:
        if p.stat().st_mtime > cache_mtime:
            return False
    if (
        include_custom_entries
        and APP_DB_PATH.exists()
        and APP_DB_PATH.stat().st_mtime > cache_mtime
    ):
        return False
    return True
