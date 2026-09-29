"""Reader HTTP language config."""

import json
from typing import Any, Mapping

from flask import Blueprint, jsonify, request

from language_registry import get_folder_map

from .settings import APP_ROOT

bp = Blueprint("language_config", __name__)

_SWAHILI_UPOS_NORMALIZATION = {
    "COP": "AUX",
    "CONJ": "CCONJ",
    "PROP": "PROPN",
    "PROPNAME": "PROPN",
}


def _is_swahili_language_code(lang_code: str) -> bool:
    lang = str(lang_code or "").strip().lower()
    return lang in {"sw", "swahili", "kiswahili"} or lang.startswith("sw-")


def _normalize_trankit_upos_doc(doc: Any, lang_code: str) -> Any:
    if not _is_swahili_language_code(lang_code):
        return doc
    if not _SWAHILI_UPOS_NORMALIZATION:
        return doc

    def _walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key == "upos":
                    raw = str(value or "").strip().upper()
                    mapped = _SWAHILI_UPOS_NORMALIZATION.get(raw)
                    if mapped:
                        node[key] = mapped
                    continue
                _walk(value)
            return
        if isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(doc)
    return doc


_lang_configs = {}


def get_lang_config(lang: str) -> dict:
    if lang in _lang_configs:
        return _lang_configs[lang]
    # Check for explicit lang_config_file in registry first
    from language_registry import LANGUAGE_REGISTRY, resolve_lang_code

    resolved = resolve_lang_code(lang) or lang
    info = LANGUAGE_REGISTRY.get(resolved, {})
    if info.get("lang_config_file"):
        config_path = APP_ROOT / info["lang_config_file"]
    else:
        folder_map = get_folder_map()
        folder = folder_map.get(lang, lang)
        config_path = APP_ROOT / folder / "lang_config.json"
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
        _lang_configs[lang] = config
        return config
    return {}


@bp.route("/api/lang_config")
def lang_config_endpoint():
    """
    Serve language-specific config (NER labels, dep relations, font, etc.)
    for the frontend legend/UI.
    """
    lang = request.args.get("lang", "zh").strip().lower()
    config = get_lang_config(lang)
    if not config:
        return jsonify({"ok": False, "error": f"No config for language: {lang}"}), 404
    return jsonify({"ok": True, "config": config})
