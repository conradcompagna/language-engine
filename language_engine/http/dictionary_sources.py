"""Reader HTTP dictionary sources."""

from typing import Mapping

from flask import Blueprint, jsonify

from language_registry import LANGUAGE_REGISTRY, get_tsv_path, resolve_lang_code

bp = Blueprint("dictionary_sources", __name__)


def _registered_dict_source_items(lang_code: str) -> list[dict[str, str]]:
    info = LANGUAGE_REGISTRY.get(lang_code) or {}
    if not info:
        return []
    sources = []
    dict_sources = info.get("dict_sources") or {}
    if dict_sources:
        for raw_key, raw_meta in dict_sources.items():
            key = str(raw_key or "").strip().lower()
            if not key or key in {"custom", "lsj"}:
                continue
            meta = raw_meta if isinstance(raw_meta, Mapping) else {}
            sources.append({"key": key, "label": str(meta.get("label") or raw_key)})
        return sources
    return [{"key": "wiktionary", "label": "Wiktionary"}]


def _registered_dict_source_keys(lang_code: str) -> set[str]:
    return {src["key"] for src in _registered_dict_source_items(lang_code)}


def _is_registered_dict_source(lang_code: str, source: str) -> bool:
    src = str(source or "").strip().lower()
    if not src or src == "custom":
        return True
    if src == "default":
        return bool(LANGUAGE_REGISTRY.get(lang_code))
    return src in _registered_dict_source_keys(lang_code)


def _registered_sqlite_aliases_for_language(lang_code: str) -> set[str]:
    if lang_code not in LANGUAGE_REGISTRY:
        return set()
    from dict_lookup_sqlite import _resolve_db_path

    aliases: set[str] = set()
    default_path = _resolve_db_path(lang_code, "")
    if default_path:
        aliases.add(default_path.stem)
    for source in _registered_dict_source_keys(lang_code):
        if source in {"custom", "default"}:
            continue
        db_path = _resolve_db_path(lang_code, source)
        if db_path:
            aliases.add(db_path.stem)
    return aliases


@bp.route("/api/dict_sources/<lang_code>")
def dict_sources(lang_code):
    """List active SQLite dictionary sources for a registered language."""
    lang = resolve_lang_code(lang_code)
    if not lang:
        return jsonify(
            {"ok": False, "error": f"Unsupported language: {lang_code}"}
        ), 400
    return jsonify({"ok": True, "sources": _registered_dict_source_items(lang)})


@bp.route("/api/languages")
def list_languages():
    """Return all supported language codes and their display names."""
    langs = []
    for code, info in LANGUAGE_REGISTRY.items():
        tsv_path = get_tsv_path(code)
        entry = {
            "code": code,
            "aliases": info.get("aliases", []),
            "has_dict": tsv_path is not None,
        }
        # Include dict_sources if the language has alternative dictionaries
        ds = info.get("dict_sources")
        if ds:
            entry["dict_sources"] = {k: {"label": v["label"]} for k, v in ds.items()}
        default_source = info.get("default_dict_source")
        if default_source:
            entry["default_dict_source"] = str(default_source)
        langs.append(entry)
    response = jsonify({"ok": True, "languages": langs})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
