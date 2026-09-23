"""Gemini dictionary service."""

from .custom_entries import _entry_to_frontend, _store_generated_entry_db
from .settings import is_enabled, log
from .transport import _call_gemini


def generate_entry(
    token: str,
    sentence: str,
    lang_code: str,
    lemma_hint: str = "",
    upos: str = "",
    xpos: str = "",
    feats: str = "",
    dep: str = "",
    surface_form: str = "",
    target_word: str = "",
    user=None,
) -> dict | None:
    """Generate a dictionary entry for one token via Gemini.

    Each surface token is stored as its own singleton row.  The canonical
    form and commentary are stored in dedicated columns.

    Returns frontend-compatible entry dict or None.
    Budget-tracks if user is provided.
    """
    if not is_enabled():
        return None

    # Budget check
    if user is not None:
        from db import db, ApiUsage

        usage = ApiUsage.query.filter_by(user_id=user.id).first()
        if not usage:
            usage = ApiUsage(user_id=user.id)
            db.session.add(usage)
            db.session.commit()
        if not usage.can_use_llm(user):
            log.info("Gemini dict: budget exhausted for user %s", user.id)
            return None

    try:
        entry, usage_counts = _call_gemini(
            token,
            sentence,
            lang_code,
            lemma_hint=lemma_hint,
            upos=upos,
            xpos=xpos,
            feats=feats,
            dep=dep,
            surface_form=surface_form,
            target_word=target_word,
        )
    except Exception as e:
        log.warning("Gemini dict: API call failed: %s", e)
        return None

    if not entry:
        return None

    # Write to TSV — may merge into existing canonical row
    stored_entry = _store_generated_entry_db(lang_code, entry)

    # Record usage
    if user is not None:
        from db import db, ApiUsage

        usage = ApiUsage.query.filter_by(user_id=user.id).first()
        if usage:
            usage.record_llm(
                usage_counts.get("prompt_tokens", 0),
                usage_counts.get("response_tokens", 0),
            )
            db.session.commit()

    return _entry_to_frontend(stored_entry or entry)
