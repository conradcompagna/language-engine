"""Reader HTTP diagnostics."""

import os as _os

from flask import Blueprint, jsonify, request

from .settings import APP_ROOT

bp = Blueprint("diagnostics", __name__)

_UNKNOWN_PHON_LOG = _os.path.join(str(APP_ROOT), "unknown_phon_marks.json")


_unknown_phon_lock = __import__("threading").Lock()


@bp.route("/api/log_unknown_phon_mark", methods=["POST"])
def log_unknown_phon_mark():
    data = request.get_json(silent=True) or {}
    char = str(data.get("char", "")).strip()
    lang = str(data.get("lang", "")).strip()
    if not char:
        return jsonify({"ok": False}), 400
    with _unknown_phon_lock:
        try:
            import json as _json

            if _os.path.exists(_UNKNOWN_PHON_LOG):
                with open(_UNKNOWN_PHON_LOG, "r", encoding="utf-8") as f:
                    log = _json.load(f)
            else:
                log = []
            # Deduplicate: skip if this (char, lang) pair already logged
            key = f"{lang}|{char}"
            existing_keys = {f"{e.get('lang', '')}|{e.get('char', '')}" for e in log}
            if key not in existing_keys:
                import unicodedata as _ud

                try:
                    name = _ud.name(char, "")
                except Exception:
                    name = ""
                log.append(
                    {
                        "char": char,
                        "codepoint": "U+" + format(ord(char), "04X")
                        if len(char) == 1
                        else "",
                        "name": name,
                        "lang": lang,
                    }
                )
                with open(_UNKNOWN_PHON_LOG, "w", encoding="utf-8") as f:
                    _json.dump(log, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return jsonify({"ok": True})
