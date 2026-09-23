"""Reader HTTP entry notes."""

from flask import (
    Blueprint,
    jsonify,
    request,
)
from flask_login import current_user

from db import db as le_db

bp = Blueprint("entry_notes", __name__)


@bp.route("/api/entry_note/get", methods=["GET"])
def entry_note_get():
    """Get the community note for a dictionary entry."""
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401

    from db import EntryNote

    lang = (request.args.get("lang") or "").strip()
    db_alias = (request.args.get("db_alias") or "").strip()
    entry_row_id = request.args.get("entry_row_id", type=int)

    if not lang or not db_alias or not entry_row_id:
        return jsonify({"ok": True, "note": ""})

    row = EntryNote.query.filter_by(
        language=lang, db_alias=db_alias, entry_row_id=entry_row_id
    ).first()

    return jsonify({"ok": True, "note": row.note if row else ""})


@bp.route("/api/entry_note/save", methods=["POST"])
def entry_note_save():
    """Create or update the community note for a dictionary entry."""
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    from db import EntryNote

    data = request.get_json(silent=True) or {}
    lang = (data.get("lang") or "").strip()
    db_alias = (data.get("db_alias") or "").strip()
    entry_row_id = data.get("entry_row_id")
    note = (data.get("note") or "").strip()

    if not lang or not db_alias or not entry_row_id or not note:
        return jsonify({"ok": False, "error": "Missing required fields."}), 400

    entry_row_id = int(entry_row_id)
    existing = EntryNote.query.filter_by(
        language=lang, db_alias=db_alias, entry_row_id=entry_row_id
    ).first()
    if existing:
        existing.note = note
    else:
        row = EntryNote(
            language=lang,
            db_alias=db_alias,
            entry_row_id=entry_row_id,
            note=note,
        )
        le_db.session.add(row)

    le_db.session.commit()
    return jsonify({"ok": True})


@bp.route("/api/entry_note/delete", methods=["POST"])
def entry_note_delete():
    """Delete the community note for a dictionary entry."""
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    from db import EntryNote

    data = request.get_json(silent=True) or {}
    lang = (data.get("lang") or "").strip()
    db_alias = (data.get("db_alias") or "").strip()
    entry_row_id = data.get("entry_row_id")

    if not lang or not db_alias or not entry_row_id:
        return jsonify({"ok": False, "error": "Missing required fields."}), 400

    entry_row_id = int(entry_row_id)
    row = EntryNote.query.filter_by(
        language=lang, db_alias=db_alias, entry_row_id=entry_row_id
    ).first()
    if not row:
        return jsonify({"ok": False, "error": "Not found."}), 404

    le_db.session.delete(row)
    le_db.session.commit()
    return jsonify({"ok": True})


@bp.route("/api/entry_note/generate", methods=["POST"])
def entry_note_generate():
    """Auto-generate an explanatory note for a dictionary entry via Gemini."""
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    from config import TIER_CAPS
    from db import ApiUsage, EntryNote
    from gemini_dict import generate_entry_note

    data = request.get_json(silent=True) or {}
    lang = (data.get("lang") or "").strip()
    db_alias = (data.get("db_alias") or "").strip()
    entry_row_id = data.get("entry_row_id")
    headword = (data.get("headword") or "").strip()
    pos = (data.get("pos") or "").strip()
    sentence_tokens = (
        data.get("sentence_tokens")
        if isinstance(data.get("sentence_tokens"), list)
        else None
    )
    fills = data.get("fills") if isinstance(data.get("fills"), list) else None

    if not lang or not db_alias or not entry_row_id or not headword:
        return jsonify({"ok": False, "error": "Missing required fields."}), 400

    entry_row_id = int(entry_row_id)

    # Budget check
    usage = ApiUsage.query.filter_by(user_id=current_user.id).first()
    if not usage:
        usage = ApiUsage(user_id=current_user.id)
        le_db.session.add(usage)
    usage._maybe_reset(current_user)
    if not usage.can_use_llm(current_user):
        return jsonify({"ok": False, "error": "Monthly LLM budget reached."}), 429

    model = TIER_CAPS.get(current_user.tier, {}).get("gemini_model", "")
    result = generate_entry_note(
        lang,
        db_alias,
        entry_row_id,
        headword,
        pos=pos,
        model=model,
        sentence_tokens=sentence_tokens,
        fills=fills,
    )

    if not result.get("ok"):
        return jsonify({"ok": False, "error": result.get("error", "LLM error.")}), 500

    note_text = result["note"]

    # Record usage
    usage_meta = result.get("usage_meta") or {}
    usage.record_llm(
        usage_meta.get("input_tokens", 0),
        usage_meta.get("output_tokens", 0),
    )
    le_db.session.commit()

    # Upsert note
    existing = EntryNote.query.filter_by(
        language=lang, db_alias=db_alias, entry_row_id=entry_row_id
    ).first()
    if existing:
        existing.note = note_text
    else:
        row = EntryNote(
            language=lang,
            db_alias=db_alias,
            entry_row_id=entry_row_id,
            note=note_text,
        )
        le_db.session.add(row)

    le_db.session.commit()
    return jsonify({"ok": True, "note": note_text})
