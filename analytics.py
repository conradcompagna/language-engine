"""
Local analytics counters for Language Engine.

This module stores aggregate operational metrics in SQLite. It intentionally
does not log raw IP addresses, user agents, request URLs, or per-request bodies.
"""

from __future__ import annotations

import datetime
import hashlib
from typing import Any

from flask import has_app_context
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

import config
from db import (
    AnalyticsDaily,
    AnalyticsLanguageDaily,
    AnalyticsVisitorDay,
    Subscription,
    User,
    db,
)


def _enabled() -> bool:
    return bool(getattr(config, "ANALYTICS_ENABLED", True)) and has_app_context()


def _today() -> datetime.date:
    return datetime.date.today()


def _to_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _daily(day: datetime.date | None = None) -> AnalyticsDaily:
    day = day or _today()
    row = AnalyticsDaily.query.filter_by(date=day).first()
    if row is None:
        row = AnalyticsDaily(date=day)
        db.session.add(row)
        db.session.flush()
    return row


def _language_daily(language: str, day: datetime.date | None = None) -> AnalyticsLanguageDaily:
    day = day or _today()
    lang = str(language or "").strip().lower()[:20] or "unknown"
    row = AnalyticsLanguageDaily.query.filter_by(date=day, language=lang).first()
    if row is None:
        row = AnalyticsLanguageDaily(date=day, language=lang)
        db.session.add(row)
        db.session.flush()
    return row


def record_landing_visit(visitor_id: str) -> None:
    if not _enabled():
        return
    day = _today()
    try:
        row = _daily(day)
        row.landing_visits = _to_int(row.landing_visits) + 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        return

    visitor = str(visitor_id or "").strip()
    if not visitor:
        return
    visitor_hash = hashlib.sha256(visitor.encode("utf-8", "ignore")).hexdigest()
    try:
        db.session.add(AnalyticsVisitorDay(date=day, visitor_hash=visitor_hash))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return
    except Exception:
        db.session.rollback()
        return

    try:
        row = _daily(day)
        row.landing_unique_visitors = _to_int(row.landing_unique_visitors) + 1
        db.session.commit()
    except Exception:
        db.session.rollback()


def record_lookup(language: str, token_count: int = 0, dp_only: bool = False) -> None:
    if not _enabled():
        return
    tokens = _to_int(token_count)
    try:
        row = _daily()
        lang_row = _language_daily(language)
        if dp_only:
            row.lookup_dp_only_requests = _to_int(row.lookup_dp_only_requests) + 1
            lang_row.lookup_dp_only_requests = _to_int(lang_row.lookup_dp_only_requests) + 1
        else:
            row.lookup_requests = _to_int(row.lookup_requests) + 1
            row.lookup_tokens = _to_int(row.lookup_tokens) + tokens
            lang_row.lookup_requests = _to_int(lang_row.lookup_requests) + 1
            lang_row.lookup_tokens = _to_int(lang_row.lookup_tokens) + tokens
        db.session.commit()
    except Exception:
        db.session.rollback()


def record_checkout_attempt() -> None:
    if not _enabled():
        return
    try:
        row = _daily()
        row.checkout_attempts = _to_int(row.checkout_attempts) + 1
        db.session.commit()
    except Exception:
        db.session.rollback()


def record_trankit_timing(language: str, wait_ms: float, run_ms: float) -> None:
    if not _enabled():
        return
    wait = _to_int(round(float(wait_ms or 0.0)))
    run = _to_int(round(float(run_ms or 0.0)))
    try:
        row = _daily()
        row.trankit_run_count = _to_int(row.trankit_run_count) + 1
        row.trankit_run_ms_total = _to_int(row.trankit_run_ms_total) + run
        if wait >= 1:
            row.trankit_wait_count = _to_int(row.trankit_wait_count) + 1
            row.trankit_wait_ms_total = _to_int(row.trankit_wait_ms_total) + wait
            row.trankit_wait_ms_max = max(_to_int(row.trankit_wait_ms_max), wait)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _date_key(value: Any) -> str:
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value or "")


def admin_summary(days: int = 30) -> dict[str, Any]:
    days = max(1, min(_to_int(days) or 30, 365))
    today = _today()
    start = today - datetime.timedelta(days=days - 1)

    daily_rows = (
        AnalyticsDaily.query.filter(AnalyticsDaily.date >= start)
        .order_by(AnalyticsDaily.date.asc())
        .all()
    )
    language_rows = (
        AnalyticsLanguageDaily.query.filter(AnalyticsLanguageDaily.date >= start)
        .order_by(
            AnalyticsLanguageDaily.lookup_requests.desc(),
            AnalyticsLanguageDaily.lookup_tokens.desc(),
        )
        .all()
    )
    account_rows = (
        db.session.query(func.date(User.created_at), func.count(User.id))
        .filter(User.created_at >= datetime.datetime.combine(start, datetime.time.min))
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at).asc())
        .all()
    )

    active_paid_statuses = ("active", "trialing")
    totals = {
        "accounts": User.query.count(),
        "paid_subscriptions": Subscription.query.filter(
            Subscription.status.in_(active_paid_statuses)
        ).count(),
        "landing_visits": sum(_to_int(row.landing_visits) for row in daily_rows),
        "landing_unique_visitors": sum(_to_int(row.landing_unique_visitors) for row in daily_rows),
        "lookup_requests": sum(_to_int(row.lookup_requests) for row in daily_rows),
        "lookup_tokens": sum(_to_int(row.lookup_tokens) for row in daily_rows),
        "lookup_dp_only_requests": sum(_to_int(row.lookup_dp_only_requests) for row in daily_rows),
        "checkout_attempts": sum(_to_int(row.checkout_attempts) for row in daily_rows),
        "trankit_wait_count": sum(_to_int(row.trankit_wait_count) for row in daily_rows),
        "trankit_wait_ms_total": sum(_to_int(row.trankit_wait_ms_total) for row in daily_rows),
        "trankit_run_count": sum(_to_int(row.trankit_run_count) for row in daily_rows),
        "trankit_run_ms_total": sum(_to_int(row.trankit_run_ms_total) for row in daily_rows),
        "trankit_wait_ms_max": max([_to_int(row.trankit_wait_ms_max) for row in daily_rows] or [0]),
    }
    totals["trankit_avg_wait_ms"] = (
        round(totals["trankit_wait_ms_total"] / totals["trankit_wait_count"], 1)
        if totals["trankit_wait_count"]
        else 0
    )
    totals["trankit_avg_run_ms"] = (
        round(totals["trankit_run_ms_total"] / totals["trankit_run_count"], 1)
        if totals["trankit_run_count"]
        else 0
    )

    by_language: dict[str, dict[str, Any]] = {}
    for row in language_rows:
        lang = row.language or "unknown"
        bucket = by_language.setdefault(
            lang,
            {
                "language": lang,
                "lookup_requests": 0,
                "lookup_tokens": 0,
                "lookup_dp_only_requests": 0,
            },
        )
        bucket["lookup_requests"] += _to_int(row.lookup_requests)
        bucket["lookup_tokens"] += _to_int(row.lookup_tokens)
        bucket["lookup_dp_only_requests"] += _to_int(row.lookup_dp_only_requests)

    return {
        "ok": True,
        "days": days,
        "start": start.isoformat(),
        "end": today.isoformat(),
        "totals": totals,
        "daily": [
            {
                "date": row.date.isoformat(),
                "landing_visits": _to_int(row.landing_visits),
                "landing_unique_visitors": _to_int(row.landing_unique_visitors),
                "checkout_attempts": _to_int(row.checkout_attempts),
                "lookup_requests": _to_int(row.lookup_requests),
                "lookup_tokens": _to_int(row.lookup_tokens),
                "lookup_dp_only_requests": _to_int(row.lookup_dp_only_requests),
                "trankit_run_count": _to_int(row.trankit_run_count),
                "trankit_wait_count": _to_int(row.trankit_wait_count),
                "trankit_avg_wait_ms": (
                    round(_to_int(row.trankit_wait_ms_total) / _to_int(row.trankit_wait_count), 1)
                    if _to_int(row.trankit_wait_count)
                    else 0
                ),
                "trankit_max_wait_ms": _to_int(row.trankit_wait_ms_max),
            }
            for row in daily_rows
        ],
        "accounts_by_day": [
            {"date": _date_key(day), "new_accounts": _to_int(count)} for day, count in account_rows
        ],
        "languages": sorted(
            by_language.values(),
            key=lambda item: (
                item["lookup_requests"],
                item["lookup_tokens"],
                item["lookup_dp_only_requests"],
            ),
            reverse=True,
        ),
    }
