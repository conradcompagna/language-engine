"""Reader HTTP quotas."""

from typing import Any, Mapping, Sequence

from flask import (
    Blueprint,
    jsonify,
)
from flask_login import current_user

import config as le_config
from db import db as le_db

bp = Blueprint("quotas", __name__)


def _get_or_create_lookup_quota():
    from db import LookupQuota

    quota = LookupQuota.query.filter_by(user_id=current_user.id).first()
    if not quota:
        quota = LookupQuota(user_id=current_user.id)
        le_db.session.add(quota)
    quota.reset_if_new_day()
    return quota


def _lookup_quota_payload(
    quota=None, *, over_limit: bool | None = None
) -> dict[str, Any]:
    if current_user.is_subscribed:
        return {
            "ok": True,
            "remaining": None,
            "limit": None,
            "tokens_used": None,
            "tokens_remaining": None,
            "tokens_limit": None,
            "over_limit": False,
            "upgrade": False,
        }
    if quota is None:
        quota = _get_or_create_lookup_quota()
    limit = le_config.FREE_LOOKUP_TOKENS_PER_DAY
    used = int(quota.count or 0)
    remaining = quota.remaining
    exhausted = used >= limit if over_limit is None else bool(over_limit)
    return {
        "ok": not exhausted,
        "remaining": remaining,
        "limit": limit,
        "tokens_used": used,
        "tokens_remaining": remaining,
        "tokens_limit": limit,
        "over_limit": exhausted,
        "upgrade": exhausted,
    }


def _precheck_lookup_quota_response():
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401
    if current_user.is_subscribed:
        return None
    quota = _get_or_create_lookup_quota()
    limit = le_config.FREE_LOOKUP_TOKENS_PER_DAY
    used = int(quota.count or 0)
    if used >= limit:
        le_db.session.commit()
        payload = _lookup_quota_payload(quota, over_limit=True)
        payload["error"] = "Daily lookup token limit reached."
        return jsonify(payload), 429
    le_db.session.commit()
    return None


def _lookup_token_count_from_payload(payload: Mapping[str, Any]) -> int:
    ud_tokens = (
        (payload.get("ud_overlay") or {})
        if isinstance(payload.get("ud_overlay"), Mapping)
        else {}
    ).get("tokens")
    if isinstance(ud_tokens, Sequence) and not isinstance(
        ud_tokens, (str, bytes, bytearray)
    ):
        return len(ud_tokens)
    grammar_tokens = (
        (payload.get("grammar_overlay") or {})
        if isinstance(payload.get("grammar_overlay"), Mapping)
        else {}
    ).get("tokens")
    if isinstance(grammar_tokens, Sequence) and not isinstance(
        grammar_tokens, (str, bytes, bytearray)
    ):
        return len(grammar_tokens)
    segments = payload.get("segments")
    if isinstance(segments, Sequence) and not isinstance(
        segments, (str, bytes, bytearray)
    ):
        return len(segments)
    return 0


def _attach_lookup_quota_after_success(payload: dict[str, Any]) -> dict[str, Any]:
    if not current_user.is_authenticated:
        return payload
    if current_user.is_subscribed:
        payload["lookup_quota"] = _lookup_quota_payload()
        return payload
    quota = _get_or_create_lookup_quota()
    if bool(payload.get("ok", True)):
        token_count = _lookup_token_count_from_payload(payload)
        if token_count > 0:
            quota.increment(token_count)
    le_db.session.commit()
    payload["lookup_quota"] = _lookup_quota_payload(quota)
    return payload


@bp.route("/lookup/gate", methods=["POST"])
def lookup_gate():
    """
    Called by the frontend Look Up button to check the daily free-token quota.
    Actual successful lookup usage is recorded by /lookup.
    """
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401

    if current_user.is_subscribed:
        le_db.session.commit()
        return jsonify(
            {
                "ok": True,
                "remaining": None,
                "limit": None,
                "tokens_used": None,
                "tokens_remaining": None,
                "tokens_limit": None,
            }
        )

    quota = _get_or_create_lookup_quota()
    limit = le_config.FREE_LOOKUP_TOKENS_PER_DAY
    used = int(quota.count or 0)
    if used >= limit:
        le_db.session.commit()
        return jsonify(
            {
                "ok": False,
                "upgrade": True,
                "error": "Daily lookup token limit reached.",
                "remaining": 0,
                "limit": limit,
                "tokens_used": used,
                "tokens_remaining": 0,
                "tokens_limit": limit,
                "over_limit": True,
            }
        ), 429

    le_db.session.commit()
    return jsonify(
        {
            "ok": True,
            "remaining": quota.remaining,
            "limit": limit,
            "tokens_used": used,
            "tokens_remaining": quota.remaining,
            "tokens_limit": limit,
            "over_limit": False,
        }
    )
