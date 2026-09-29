"""Reader HTTP policy."""

from flask import jsonify, request
from flask_login import current_user

_PAID_FEATURE_ENDPOINTS = frozenset(
    [
        "user_dict_add",
        "user_dict_update",
        "user_dict_delete",
        "gemini_entry_update",
        "gemini_entry_delete",
        "gemini_entry_vote_delete",
        "gemini_entry_deletion_votes",
        "entry_note_save",
        "entry_note_delete",
        "entry_note_generate",
        "entry_decomp_save",
        "entry_decomp_delete",
        "entry_decomp_generate",
        "mt_gloss",
        "llm_glosses",
        "llm_decomps",
        "orth_breakdowns",
        "llm_translate_sentences",
    ]
)


def _enforce_paid_feature_gate():
    if str(request.endpoint or "").rsplit(".", 1)[-1] not in _PAID_FEATURE_ENDPOINTS:
        return None
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401
    if current_user.tier == "free":
        return jsonify(
            {"ok": False, "error": "Paid feature.", "upgrade_required": True}
        ), 403
    return None
