"""Reader HTTP decompositions."""

from flask import (
    Blueprint,
    jsonify,
    request,
)
from flask_login import current_user

from db import db as le_db

bp = Blueprint("decompositions", __name__)


@bp.route("/api/entry_decomp/batch", methods=["POST"])
def entry_decomp_batch():
    """Fetch decomps for many surface forms at once.

    Request: {lang, surfaces: [str, ...]}
    Response: {ok: true, decomps: {surface_form: decomp_text, ...}}
    Surfaces with no stored decomp are simply absent from the response map.
    """
    from db import EntryDecomp

    data = request.get_json(silent=True) or {}
    lang = (data.get("lang") or "").strip()
    surfaces_in = data.get("surfaces") or []
    surfaces = sorted({str(s).strip() for s in surfaces_in if str(s).strip()})

    if not lang or not surfaces:
        return jsonify({"ok": True, "decomps": {}})

    out = {}
    # SQLite parameter limit is ~999; chunk to be safe.
    for i in range(0, len(surfaces), 500):
        chunk = surfaces[i : i + 500]
        rows = EntryDecomp.query.filter(
            EntryDecomp.language == lang,
            EntryDecomp.surface_form.in_(chunk),
        ).all()
        for r in rows:
            out[r.surface_form] = r.decomp
    return jsonify({"ok": True, "decomps": out})


@bp.route("/api/entry_decomp/get", methods=["GET"])
def entry_decomp_get():
    """Get the morpheme decomposition for a surface form.

    Decomps are keyed solely by (language, surface_form) — every spelling a
    user sees (headword, forms-row variant, lemma-override OOV) gets its own
    independent slot.
    """
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401

    from db import EntryDecomp

    lang = (request.args.get("lang") or "").strip()
    surface_form = (request.args.get("surface_form") or "").strip()

    if not lang or not surface_form:
        return jsonify({"ok": True, "decomp": ""})

    row = EntryDecomp.query.filter_by(language=lang, surface_form=surface_form).first()
    return jsonify({"ok": True, "decomp": row.decomp if row else ""})


@bp.route("/api/entry_decomp/save", methods=["POST"])
def entry_decomp_save():
    """Create or update the morpheme decomposition for a surface form."""
    from db import EntryDecomp

    data = request.get_json(silent=True) or {}
    lang = (data.get("lang") or "").strip()
    surface_form = (data.get("surface_form") or "").strip()
    decomp = (data.get("decomp") or "").strip()

    if not lang or not surface_form or not decomp:
        return jsonify({"ok": False, "error": "Missing required fields."}), 400

    existing = EntryDecomp.query.filter_by(
        language=lang, surface_form=surface_form
    ).first()
    if existing:
        existing.decomp = decomp
    else:
        row = EntryDecomp(
            language=lang,
            surface_form=surface_form,
            decomp=decomp,
        )
        le_db.session.add(row)

    le_db.session.commit()
    return jsonify({"ok": True})


@bp.route("/api/entry_decomp/delete", methods=["POST"])
def entry_decomp_delete():
    """Delete the morpheme decomposition for a surface form."""
    from db import EntryDecomp

    data = request.get_json(silent=True) or {}
    lang = (data.get("lang") or "").strip()
    surface_form = (data.get("surface_form") or "").strip()

    if not lang or not surface_form:
        return jsonify({"ok": False, "error": "Missing required fields."}), 400

    row = EntryDecomp.query.filter_by(language=lang, surface_form=surface_form).first()
    if not row:
        return jsonify({"ok": False, "error": "Not found."}), 404

    le_db.session.delete(row)
    le_db.session.commit()
    return jsonify({"ok": True})


@bp.route("/api/entry_decomp/generate", methods=["POST"])
def entry_decomp_generate():
    """Auto-generate a morpheme decomposition for a surface form via Gemini.

    The result is stored under (language, surface_form). `headword`, `pos`,
    and `glosses` are Gemini context only; they are not part of the storage
    key. The client should send the actual surface the user is looking at as
    both `surface_form` and `headword` (so Gemini analyzes that exact form).
    """
    from config import TIER_CAPS
    from db import ApiUsage, EntryDecomp
    from gemini_dict import generate_entry_decomp

    data = request.get_json(silent=True) or {}
    lang = (data.get("lang") or "").strip()
    surface_form = (data.get("surface_form") or "").strip()
    headword = (data.get("headword") or "").strip() or surface_form
    pos = (data.get("pos") or "").strip()
    glosses = [str(g).strip() for g in (data.get("glosses") or []) if str(g).strip()]
    trankit = data.get("trankit") if isinstance(data.get("trankit"), dict) else None

    if not lang or not surface_form:
        return jsonify({"ok": False, "error": "Missing required fields."}), 400

    usage = ApiUsage.query.filter_by(user_id=current_user.id).first()
    if not usage:
        usage = ApiUsage(user_id=current_user.id)
        le_db.session.add(usage)
    usage._maybe_reset(current_user)
    if not usage.can_use_llm(current_user):
        return jsonify({"ok": False, "error": "Monthly LLM budget reached."}), 429

    model = TIER_CAPS.get(current_user.tier, {}).get("gemini_model", "")
    result = generate_entry_decomp(
        lang,
        "",
        0,
        headword,
        pos=pos,
        model=model,
        glosses=glosses or None,
        trankit=trankit,
    )

    if not result.get("ok"):
        return jsonify({"ok": False, "error": result.get("error", "LLM error.")}), 500

    decomp_text = result["decomp"]

    usage_meta = result.get("usage_meta") or {}
    usage.record_llm(
        usage_meta.get("input_tokens", 0),
        usage_meta.get("output_tokens", 0),
    )
    le_db.session.commit()

    existing = EntryDecomp.query.filter_by(
        language=lang, surface_form=surface_form
    ).first()
    if existing:
        existing.decomp = decomp_text
    else:
        row = EntryDecomp(
            language=lang,
            surface_form=surface_form,
            decomp=decomp_text,
        )
        le_db.session.add(row)

    le_db.session.commit()
    return jsonify({"ok": True, "decomp": decomp_text})
