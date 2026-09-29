"""Reader HTTP dictionary index."""

import json
from typing import Any

from flask import Blueprint, Response, jsonify, request, send_from_directory

from language_registry import LANGUAGE_REGISTRY, resolve_lang_code

from .dictionary_sources import (
    _is_registered_dict_source,
    _registered_sqlite_aliases_for_language,
)
from .index_cache import (
    _JS_INDEX_ARTIFACT_DIR,
    _JS_INDEX_CACHE_DIR,
    _JS_INDEX_SCHEMA_VERSION,
    _js_index_cache_is_fresh,
    _js_index_cache_path,
)
from .responses import _lookup_json_response
from .serializers import (
    _build_hydrated_display_payload,
    _build_shared_base_payload,
    _extract_form_overlay,
    _shape_korean_synthetic_stem_entry,
)
from .startup import _extract_version_from_gz, _js_index_versions

bp = Blueprint("dictionary_index", __name__)


@bp.route("/js/hydrate", methods=["POST"])
def js_hydrate():
    """
    Batch entry hydration. Accepts winner_refs from JS DP segmentation,
    returns fully hydrated entry_store (same shape as /lookup output).
    """
    from dict_lookup_sqlite import hydrate_winner_refs as _hydrate

    data = request.get_json(silent=True) or {}
    raw_lang = str(data.get("lang") or "").strip().lower()
    lang_code = resolve_lang_code(raw_lang) or raw_lang
    if not lang_code:
        return jsonify({"ok": False, "error": "missing lang"}), 400
    if lang_code not in LANGUAGE_REGISTRY:
        return jsonify({"ok": False, "error": f"Unsupported language: {raw_lang}"}), 400

    winner_refs = list(data.get("winner_refs") or [])
    allowed_sqlite_aliases = _registered_sqlite_aliases_for_language(lang_code)

    # Remap JS wire format to the internal keys hydrate_winner_refs() expects
    candidates = []
    sqlite_stems: set[str] = set()
    match_keys_by_wire: dict[str, str] = {}
    for ref in winner_refs:
        storage_kind = str(ref.get("storage_kind") or "sqlite")
        db_alias = str(ref.get("db_alias") or "")
        entry_row_id = int(ref.get("entry_row_id") or 0)
        form_row_id = int(ref.get("form_row_id") or 0)
        c: dict[str, Any] = {
            "_storage_kind": storage_kind,
            "_storage_db_alias": db_alias,
            "_storage_row_id": entry_row_id,
            "_match_kind": str(ref.get("match_kind") or "headword"),
            "match_key": str(ref.get("match_key") or ""),
        }
        if form_row_id > 0:
            c["_form_row_id"] = form_row_id
            c["_matched_form_row_ids"] = [form_row_id]
        candidates.append(c)
        wire_key = f"{storage_kind}|{db_alias}|{entry_row_id}"
        if form_row_id > 0:
            wire_key += f"|{form_row_id}"
        match_keys_by_wire[wire_key] = str(ref.get("match_key") or "")
        # Collect sqlite db stems so we can pass the exact db_paths to hydration.
        # The alias is the file stem (e.g. "zh-cc-cedict"), so the path is
        # SQLITE_DIR / f"{alias}.sqlite".
        if storage_kind != "custom" and db_alias and db_alias != "customdb":
            if db_alias not in allowed_sqlite_aliases:
                return jsonify(
                    {"ok": False, "error": f"Unsupported dictionary source: {db_alias}"}
                ), 400
            sqlite_stems.add(db_alias)

    from dict_lookup_sqlite import SQLITE_DIR as _SQLITE_DIR

    db_paths: list[Any] | None = None
    if sqlite_stems:
        resolved_paths = [_SQLITE_DIR / f"{stem}.sqlite" for stem in sqlite_stems]
        resolved_paths = [p for p in resolved_paths if p.exists()]
        if resolved_paths:
            db_paths = resolved_paths
    hydrated = _hydrate(
        candidates,
        lang_code,
        db_paths=db_paths,
    )

    entry_store: dict[str, Any] = {}
    # ref_to_key lets the JS client map its winner refs back to entry_store keys
    ref_to_key: dict[str, str] = {}
    # form_overlays: lightweight per-form display overrides keyed by form wire key
    form_overlays: dict[str, dict[str, Any]] = {}

    for (storage_kind, db_alias, entry_row_id), entry in hydrated.items():
        # Ensure source is set to the db stem so the client can scope
        # source-specific post-processing (e.g. pinyin conversion for cc-cedict).
        if not entry.get("source") and db_alias and db_alias != "customdb":
            entry["source"] = db_alias
        base_wire = f"{storage_kind}|{db_alias}|{entry_row_id}"
        match_key = str(match_keys_by_wire.get(base_wire) or "").strip()

        matched_forms = list(entry.get("_matched_forms") or [])
        is_form_match = str(entry.get("_match_kind") or "").strip().lower() == "form"

        if is_form_match and matched_forms:
            # Build ONE base payload for the entry (shared data: senses, forms, etymology).
            # Per-form display differences go into form_overlays.
            base_payload = _build_shared_base_payload(entry, match_key, lang_code)
            if not base_payload:
                continue
            base_payload["ref_key"] = base_wire
            base_payload["runtime_entry_id"] = base_wire
            entry_store[base_wire] = base_payload
            ref_to_key[base_wire] = base_wire

            for mf in matched_forms:
                form_row_id = int(mf.get("_form_row_id") or 0)
                if not form_row_id:
                    continue
                form_wire = f"{base_wire}|{form_row_id}"
                ref_to_key[form_wire] = base_wire
                form_overlays[form_wire] = _extract_form_overlay(entry, mf)
        else:
            # Headword match — one payload per entry
            if match_key:
                entry["_match_key"] = match_key
            _shape_korean_synthetic_stem_entry(entry, match_key, lang_code)
            payload = _build_hydrated_display_payload(entry)
            if not payload:
                continue
            payload_key = str(payload.get("ref_key") or base_wire).strip() or base_wire
            entry_store[payload_key] = payload
            ref_to_key[base_wire] = payload_key

    # Map any remaining form-variant wire keys not yet covered
    for ref in winner_refs:
        sk = str(ref.get("storage_kind") or "sqlite")
        alias = str(ref.get("db_alias") or "")
        eid = int(ref.get("entry_row_id") or 0)
        fid = int(ref.get("form_row_id") or 0)
        wire = f"{sk}|{alias}|{eid}" + (f"|{fid}" if fid > 0 else "")
        if wire not in ref_to_key:
            # Fall back to the base entry or any form payload for this entry
            base = f"{sk}|{alias}|{eid}"
            pk = ref_to_key.get(base)
            if pk:
                ref_to_key[wire] = pk

    response_payload = {
        "ok": True,
        "entry_store": entry_store,
        "ref_to_key": ref_to_key,
        "form_overlays": form_overlays,
    }

    extra_headers = None
    return _lookup_json_response(response_payload, extra_headers=extra_headers)


@bp.route("/js/dict/<lang_code>/index")
def js_dict_index(lang_code: str):
    """
    Compact key index for client-side DP segmentation.
    Returns gzip-compressed JSON: {v, lang, version, db_aliases, hw, fw}
    Disk-cached in runtime_cache/js_index/{lang}.json.gz; rebuilt when
    source .sqlite files are newer than the cache.
    Custom/Gemini entries are NOT included in the static cache — they are
    fetched separately by the client via /api/gemini_entry and injected
    into the in-memory index via injectGeminiKey().
    """
    import hashlib as _hashlib

    from dict_lookup_sqlite import (
        _resolve_all_db_paths,
        _resolve_db_path,
        build_compact_key_index,
    )

    resolved = resolve_lang_code(lang_code.strip().lower())
    if not resolved:
        return jsonify(
            {"ok": False, "error": f"Unsupported language: {lang_code}"}
        ), 400

    source = request.args.get("source", "").strip().lower()
    if (
        source
        and source not in ("custom",)
        and not _is_registered_dict_source(resolved, source)
    ):
        return jsonify(
            {
                "ok": False,
                "error": f"Unsupported dictionary source for {resolved}: {source}",
            }
        ), 404

    # Each index covers exactly one SQLite file — never bundle multiple dbs.
    if source and source not in ("custom",):
        db_path = _resolve_db_path(resolved, source)
        if not db_path:
            return jsonify(
                {"ok": False, "error": f"No database for {resolved}:{source}"}
            ), 404
        db_paths = [db_path]
    else:
        # No source specified: use the single default db for this language.
        all_paths = _resolve_all_db_paths(resolved)
        default = [p for p in all_paths if p.stem == resolved]
        db_paths = default if default else (all_paths[:1] if all_paths else [])
        if not db_paths:
            return jsonify({"ok": False, "error": f"No database for {resolved}"}), 404

    _JS_INDEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _js_index_cache_path(resolved, source)
    version = ""

    if _js_index_cache_is_fresh(
        resolved,
        cache_path,
        db_paths,
        include_custom_entries=False,
        expected_schema_version=_JS_INDEX_SCHEMA_VERSION,
    ):
        compressed = cache_path.read_bytes()
        version = _extract_version_from_gz(cache_path)
    else:
        # Cache miss (first boot or sqlite updated) — build and cache without custom entries.
        # Custom entries are injected client-side via /api/dict/<lang>/gemini after load.
        index = build_compact_key_index(
            resolved, db_paths=db_paths, include_custom_entries=False
        )
        index["v"] = _JS_INDEX_SCHEMA_VERSION
        index["lang"] = resolved
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
        import gzip as _gz

        compressed = _gz.compress(body_bytes, compresslevel=6)
        try:
            cache_path.write_bytes(compressed)
        except Exception:
            pass

    ver_key = f"{resolved}:{source}" if source else resolved
    if version:
        _js_index_versions[ver_key] = version
    else:
        version = _js_index_versions.get(ver_key) or ""

    request_version = request.args.get("v", "").strip()
    is_versioned_request = bool(version) and request_version == version

    headers = {
        "Content-Type": "application/gzip",
        "Cache-Control": "public, max-age=31536000, immutable"
        if is_versioned_request
        else "public, max-age=3600",
    }
    if version:
        headers["ETag"] = f'"{version}"'
    return Response(compressed, status=200, headers=headers)


@bp.route("/dict-index/<path:filename>")
def serve_js_index_artifact(filename: str):
    response = send_from_directory(
        _JS_INDEX_ARTIFACT_DIR,
        filename,
        mimetype="application/gzip",
        max_age=31536000,
    )
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response
