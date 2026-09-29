"""Reader HTTP custom entries."""

from flask import (
    Blueprint,
    jsonify,
    request,
)
from flask_login import current_user

from db import db as le_db

from .serializers import _collect_lookup_texts_for_entry

bp = Blueprint("custom_entries", __name__)


def _get_custom_dict_entry(
    entry_id: str = "",
    entry_row_id: int | str = 0,
    language: str = "",
    headword: str = "",
):
    from db import CustomDictEntry

    try:
        row_id = int(entry_row_id or 0)
    except Exception:
        row_id = 0
    if row_id > 0:
        return CustomDictEntry.query.filter_by(id=row_id).first()

    eid = (entry_id or "").strip()
    if eid:
        return CustomDictEntry.query.filter_by(entry_id=eid).first()

    lang = (language or "").strip().lower()
    hw = (headword or "").strip()
    if not lang or not hw:
        return None
    return CustomDictEntry.query.filter_by(language=lang, headword=hw).first()


def _custom_entry_to_response(entry) -> dict:
    import gemini_dict

    payload = gemini_dict._entry_to_frontend(entry)
    payload["language"] = entry.language or ""
    return payload


def _delete_custom_entry(entry) -> bool:
    """Remove a custom entry."""
    if not entry:
        return False

    import gemini_dict

    lookup_texts = _collect_lookup_texts_for_entry(_custom_entry_to_response(entry))
    removed = gemini_dict.remove_tsv_entry(
        entry.language, entry.headword, entry_id=entry.entry_id
    )
    if not removed:
        return False

    le_db.session.commit()
    return True


@bp.route("/api/user_dict/add", methods=["POST"])
def user_dict_add():
    """Create a new user dictionary entry — written directly to the gemini TSV."""
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    import gemini_dict

    data = request.get_json(silent=True) or {}
    headword = (data.get("headword") or "").strip()
    if not headword:
        return jsonify({"ok": False, "error": "Headword is required."}), 400

    language = (data.get("language") or "").strip()
    if not language:
        return jsonify({"ok": False, "error": "Language is required."}), 400

    # Check for duplicate headword in gemini TSV
    if gemini_dict.headword_exists(language, headword):
        return jsonify(
            {"ok": False, "error": "An entry for this headword already exists."}
        ), 409

    glosses = data.get("glosses")  # list of strings
    if isinstance(glosses, list):
        glosses = [str(g).strip() for g in glosses if str(g).strip()]
    else:
        # Fallback: semicolon-separated string
        raw = data.get("definitions") or data.get("definition") or ""
        glosses = [d.strip() for d in str(raw).split(";") if d.strip()] if raw else []

    romanization = (data.get("romanization") or data.get("pronunciation") or "").strip()
    pos = (data.get("pos") or "").strip()

    forms = data.get("forms")  # list of [word, commentary, romanization]
    if isinstance(forms, list):
        forms = [f for f in forms if isinstance(f, list) and len(f) >= 2]
    else:
        forms = None

    entry = gemini_dict.append_user_entry(
        language,
        headword,
        romanization,
        pos,
        glosses,
        forms,
    )
    if not entry:
        return jsonify({"ok": False, "error": "Failed to create entry."}), 500

    entry_payload = gemini_dict._entry_to_frontend(entry)

    return jsonify({"ok": True, "entry": entry_payload})


@bp.route("/api/user_dict/update", methods=["POST"])
def user_dict_update():
    """Update an owned user-created custom entry (legacy compatibility route)."""
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    import gemini_dict
    from db import CustomDictEntry

    data = request.get_json(silent=True) or {}
    entry_id = (data.get("entry_id") or "").strip()
    legacy_id = data.get("id")
    entry = None
    if entry_id:
        entry = CustomDictEntry.query.filter_by(entry_id=entry_id).first()
    elif legacy_id:
        entry = CustomDictEntry.query.get(legacy_id)
    if not entry or entry.source != "user_created":
        return jsonify({"ok": False, "error": "Entry not found."}), 404

    headword = (data.get("headword") or entry.headword or "").strip()
    if not headword:
        return jsonify({"ok": False, "error": "Headword is required."}), 400

    defs = data.get("definitions")
    if defs is None:
        defs = data.get("definition")
    if isinstance(defs, str):
        defs = [d.strip() for d in defs.split(";") if d.strip()]
    elif not isinstance(defs, list):
        defs = None

    forms = data.get("forms")
    if forms is None:
        forms = data.get("morphological_forms")
    if not isinstance(forms, list):
        forms = None

    current_payload = _custom_entry_to_response(entry)
    updated = gemini_dict.upsert_custom_entry(
        lang_code=(data.get("language") or entry.language or "").strip(),
        headword=headword,
        romanization=(
            data.get("romanization")
            if "romanization" in data
            else current_payload["romanization"]
        ),
        pos=(data.get("pos") if "pos" in data else current_payload["pos"]),
        glosses=(defs if defs is not None else current_payload["glosses"]),
        forms=(forms if forms is not None else current_payload["forms"]),
        commentary=(
            data.get("commentary")
            if "commentary" in data
            else current_payload["commentary"]
        ),
        lemma=(data.get("lemma") if "lemma" in data else current_payload["lemma"]),
        source="user_created",
        entry_id=entry.entry_id,
    )
    if not updated:
        return jsonify({"ok": False, "error": "Failed to update entry."}), 500
    updated_payload = _custom_entry_to_response(updated)
    return jsonify({"ok": True, "entry": updated_payload})


@bp.route("/api/user_dict/delete", methods=["POST"])
def user_dict_delete():
    """Delete an owned user-created custom entry (legacy compatibility route)."""
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    import gemini_dict
    from db import CustomDictEntry

    data = request.get_json(silent=True) or {}
    entry_id = (data.get("entry_id") or "").strip()
    legacy_id = data.get("id")
    entry = None
    if entry_id:
        entry = CustomDictEntry.query.filter_by(entry_id=entry_id).first()
    elif legacy_id:
        entry = CustomDictEntry.query.get(legacy_id)
    if not entry or entry.source != "user_created":
        return jsonify({"ok": False, "error": "Entry not found."}), 404

    removed = gemini_dict.remove_tsv_entry(
        entry.language, entry.headword, entry_id=entry.entry_id
    )
    if not removed:
        return jsonify({"ok": False, "error": "Entry not found."}), 404
    return jsonify({"ok": True})


@bp.route("/api/custom_entries/list", methods=["GET"])
def custom_entries_list():
    """Legacy ownership endpoint. Custom entries are shared app content now."""
    return jsonify({"ok": True, "entries": []})


@bp.route("/api/community_entries", methods=["GET"])
def community_entries():
    """Legacy ownership endpoint. Custom entries are loaded through the shared index."""
    return jsonify({"ok": True, "entries": []})


@bp.route("/api/gemini_entry/get", methods=["GET"])
def gemini_entry_get():
    """Get a single SQLite-backed custom entry."""
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401

    entry_id = (request.args.get("entry_id") or "").strip()
    entry_row_id = request.args.get("entry_row_id") or 0
    headword = (request.args.get("headword") or "").strip()
    language = (request.args.get("language") or "").strip()
    entry = _get_custom_dict_entry(
        entry_id=entry_id,
        entry_row_id=entry_row_id,
        language=language,
        headword=headword,
    )
    if not entry:
        return jsonify({"ok": False, "error": "Entry not found."}), 404
    return jsonify({"ok": True, "entry": _custom_entry_to_response(entry)})


@bp.route("/api/gemini_entry/update", methods=["POST"])
def gemini_entry_update():
    """Update a SQLite-backed custom entry."""
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    import gemini_dict

    data = request.get_json(silent=True) or {}
    entry_id = (data.get("entry_id") or "").strip()
    entry_row_id = data.get("entry_row_id") or 0
    headword = (data.get("headword") or "").strip()
    language = (data.get("language") or "").strip()
    entry = _get_custom_dict_entry(
        entry_id=entry_id,
        entry_row_id=entry_row_id,
        language=language,
        headword=headword,
    )
    if not entry:
        return jsonify({"ok": False, "error": "Entry not found."}), 404

    new_romanization = data.get("romanization")
    new_pos = data.get("pos")
    new_glosses = data.get("glosses")  # list of strings
    if new_glosses is not None and isinstance(new_glosses, list):
        new_glosses = [str(g).strip() for g in new_glosses if str(g).strip()]
    else:
        new_glosses = None
    new_forms = data.get("forms")  # list of [word, commentary, romanization]
    if new_forms is not None and isinstance(new_forms, list):
        # Validate form triples
        new_forms = [f for f in new_forms if isinstance(f, list) and len(f) >= 2]
    else:
        new_forms = None
    new_commentary = data.get("commentary")
    if new_commentary is not None:
        new_commentary = str(new_commentary).strip()
    new_lemma = data.get("lemma")
    if new_lemma is not None:
        new_lemma = str(new_lemma).strip()

    updated = gemini_dict.update_tsv_entry(
        entry.language,
        entry.headword,
        new_romanization=new_romanization,
        new_pos=new_pos,
        new_glosses=new_glosses,
        new_forms=new_forms,
        new_commentary=new_commentary,
        new_lemma=new_lemma,
        entry_id=entry.entry_id,
    )
    if not updated:
        return jsonify({"ok": False, "error": "Entry not found."}), 404
    updated_payload = _custom_entry_to_response(updated)
    return jsonify({"ok": True, "entry": updated_payload})


@bp.route("/api/gemini_entry/vote_delete", methods=["POST"])
def gemini_entry_vote_delete():
    """Deprecated compatibility alias for direct paid-user deletion."""
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    data = request.get_json(silent=True) or {}
    entry_id = (data.get("entry_id") or "").strip()
    entry_row_id = data.get("entry_row_id") or 0
    headword = (data.get("headword") or "").strip()
    language = (data.get("language") or "").strip()
    entry = _get_custom_dict_entry(
        entry_id=entry_id,
        entry_row_id=entry_row_id,
        language=language,
        headword=headword,
    )
    if not entry:
        return jsonify({"ok": False, "error": "Entry not found."}), 404

    if not _delete_custom_entry(entry):
        return jsonify({"ok": False, "error": "Entry not found."}), 404

    return jsonify({"ok": True, "deleted": True, "deprecated": True})


@bp.route("/api/gemini_entry/delete", methods=["POST"])
def gemini_entry_delete():
    """Delete a custom entry for any paid user."""
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    data = request.get_json(silent=True) or {}
    entry_id = (data.get("entry_id") or "").strip()
    entry_row_id = data.get("entry_row_id") or 0
    headword = (data.get("headword") or "").strip()
    language = (data.get("language") or "").strip()
    entry = _get_custom_dict_entry(
        entry_id=entry_id,
        entry_row_id=entry_row_id,
        language=language,
        headword=headword,
    )
    if not entry:
        return jsonify({"ok": False, "error": "Entry not found."}), 404

    if not _delete_custom_entry(entry):
        return jsonify({"ok": False, "error": "Entry not found."}), 404

    return jsonify({"ok": True, "deleted": True})


@bp.route("/api/gemini_entry/deletion_votes", methods=["GET"])
def gemini_entry_deletion_votes():
    """Deprecated compatibility endpoint for the old vote-delete UI."""
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401

    entry_id = (request.args.get("entry_id") or "").strip()
    entry_row_id = request.args.get("entry_row_id") or 0
    headword = (request.args.get("headword") or "").strip()
    language = (request.args.get("language") or "").strip()
    entry = _get_custom_dict_entry(
        entry_id=entry_id,
        entry_row_id=entry_row_id,
        language=language,
        headword=headword,
    )
    return jsonify(
        {
            "ok": True,
            "deprecated": True,
            "entry_id": entry.entry_id if entry else "",
            "can_delete_directly": True,
            "votes": 0,
            "user_voted": False,
            "reason": "",
            "is_owner": False,
            "owner_source": entry.source if entry else "",
        }
    )
