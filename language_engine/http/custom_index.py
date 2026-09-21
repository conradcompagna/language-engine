"""Reader HTTP custom index."""

import json

from flask import Blueprint, Response, jsonify, stream_with_context

from language_registry import resolve_lang_code

bp = Blueprint("custom_index", __name__)


@bp.route("/js/dict/<lang_code>/custom_index")
def js_custom_index(lang_code: str):
    """
    Compact key index for custom/Gemini entries only — never cached to disk.
    Returns gzip-compressed JSON: {hw, fw, db_aliases} containing only customdb keys.
    Called by the client after loading the static index to inject user-created entries.
    """
    from dict_lookup_sqlite import APP_DB_PATH, build_compact_key_index

    resolved = resolve_lang_code(lang_code.strip().lower())
    if not resolved:
        return jsonify(
            {"ok": False, "error": f"Unsupported language: {lang_code}"}
        ), 400

    if not APP_DB_PATH.exists():
        # No custom DB at all — return empty index
        import gzip as _gz

        empty = {"hw": {}, "fw": {}, "db_aliases": {}, "count": 0}
        return Response(
            _gz.compress(json.dumps(empty, separators=(",", ":")).encode()),
            status=200,
            headers={"Content-Type": "application/gzip", "Cache-Control": "no-store"},
        )

    # Build custom-only index (no static sqlite files, just customdb)
    index = build_compact_key_index(resolved, db_paths=[], include_custom_entries=True)
    count = sum(len(v) for v in index.get("hw", {}).values())
    index["count"] = count

    import gzip as _gz

    compressed = _gz.compress(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        compresslevel=1,
    )
    return Response(
        compressed,
        status=200,
        headers={
            "Content-Type": "application/gzip",
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        },
    )


@bp.route("/api/dict/<lang_code>/gemini", methods=["GET"])
def get_gemini_dict(lang_code):
    """Stream SQLite-backed custom-entry overlay rows for a language as TSV."""

    lang = (lang_code or "").strip().lower()
    if not lang:
        return jsonify({"ok": False, "error": "Missing language."}), 400

    import gemini_dict

    return Response(
        stream_with_context(gemini_dict.iter_custom_entry_tsv_lines(lang)),
        mimetype="text/tab-separated-values",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
