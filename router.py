"""
router.py — Main Flask entry point for Language Engine (formerly Neural Reader).

Initializes Trankit as a shared multilingual transformer, loads language-specific
modules via language_registry, and routes requests to the generic pipeline.
"""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import gzip as _response_gzip
import json
import re
import smtplib
import threading
import time
import copy
import unicodedata
import os as _os
from email.message import EmailMessage
from email.utils import formatdate
from typing import Any, Mapping, Sequence
from xml.sax.saxutils import escape as _xml_escape

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    redirect,
    Response,
    send_from_directory,
    stream_with_context,
    make_response,
)
from flask_cors import CORS
from flask_login import current_user
from universal_normalization import (
    build_preprocess_context,
    run_with_universal_normalization,
)
from language_registry import (
    resolve_lang_code,
    get_folder_map,
    get_tsv_path,
    get_tokenizer_path,
    run_trankit,
    run_trankit_chunk_boundaries,
    init_all,
    LANGUAGE_REGISTRY,
)
from pipeline_common import (
    _build_jmdict_forms_meta_bundle,
    process_lookup_nlp_only,
)
from debug_panel import debug_bp
from debug_trace_runtime import (
    finish_trace,
    record_decoration_event,
    start_trace,
    stop_trace,
    trace_scope,
)
from debug_store import (
    get_debug_snapshot,
    is_debug_collection_enabled,
    store_debug_json_artifact,
    update_debug_snapshot,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

APP_ROOT = Path(__file__).resolve().parent

# URL snapshot capture is retired. Chrome-extension frozen HTML uploads remain
# supported through /api/extension_capture and /api/extension_snapshot/<token>.

app = Flask(__name__)


# Jinja2 helper: returns file mtime as an int so static files auto-bust cache on save.
# Usage in templates: ?v={{ mtime('reader.js') }}
def _static_mtime(filename):
    try:
        p = APP_ROOT / "static" / filename
        return int(_os.path.getmtime(p))
    except Exception:
        return 0


app.jinja_env.globals["mtime"] = _static_mtime
app.jinja_env.globals["is_debug_collection_enabled"] = is_debug_collection_enabled


def _inject_extension_snapshot_style(html: str) -> str:
    html = re.sub(r"<script\b[^>]*>[\s\S]*?</script\s*>", "", html, flags=re.I)
    html = re.sub(r"\s+on[a-zA-Z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html)
    html = re.sub(
        r"(?i)(href|src|xlink:href)\s*=\s*(['\"])\s*javascript:[\s\S]*?\2", r"\1=\"#\"", html
    )
    style = """
<style id="docrender-monolith-inert-style">
html[data-docrender-web-snapshot],html[data-docrender-web-snapshot] body{min-height:100%;scrollbar-width:none!important;overflow-x:hidden!important;}
html[data-docrender-web-snapshot]::-webkit-scrollbar,html[data-docrender-web-snapshot] body::-webkit-scrollbar{width:0!important;height:0!important;}
html[data-docrender-web-snapshot] *{animation:none!important;transition:none!important;scroll-behavior:auto!important;}
html[data-docrender-web-snapshot] a,html[data-docrender-web-snapshot] button,html[data-docrender-web-snapshot] input,html[data-docrender-web-snapshot] textarea,html[data-docrender-web-snapshot] select,html[data-docrender-web-snapshot] [role='button']{pointer-events:none!important;}
html[data-docrender-web-snapshot] video,html[data-docrender-web-snapshot] audio{display:none!important;}
</style>""".strip()
    marked = re.sub(r"<html\b", '<html data-docrender-web-snapshot="1"', html, count=1, flags=re.I)
    if marked == html and "data-docrender-web-snapshot" not in marked:
        marked = html.replace("<HTML", '<HTML data-docrender-web-snapshot="1"', 1)
    if re.search(r"</head\s*>", marked, re.I):
        return re.sub(r"</head\s*>", style + "\n</head>", marked, count=1, flags=re.I)
    return style + "\n" + marked


@app.route("/api/monolith_snapshot", methods=["POST"])
def monolith_snapshot():
    return jsonify(
        {
            "ok": False,
            "error": "URL snapshot capture is disabled. Upload frozen Chrome-extension HTML instead.",
        }
    ), 410


# ---------------------------------------------------------------------------
# Chrome Extension capture endpoints
#
# The browser extension freezes the live DOM of whatever page the user is
# viewing and POSTs the resulting self-contained HTML here. The captured HTML
# is held in an in-memory cache keyed by a token so the user can view it back
# in the browser, or so the reader can ingest it as a webSnapshot payload.
# ---------------------------------------------------------------------------

import secrets as _ext_secrets
from collections import OrderedDict as _ExtOrderedDict

_EXTENSION_CAPTURE_LOCK = threading.Lock()
_EXTENSION_CAPTURES: "_ExtOrderedDict[str, dict]" = _ExtOrderedDict()
_EXTENSION_CAPTURE_MAX = 64
_EXTENSION_CAPTURE_TTL_SECONDS = 6 * 60 * 60  # 6 hours
_EXTENSION_CAPTURE_MAX_BYTES = 64 * 1024 * 1024  # 64 MB


def _ext_prune_locked():
    now = time.time()
    stale = [
        tok
        for tok, rec in _EXTENSION_CAPTURES.items()
        if now - rec.get("ts", now) > _EXTENSION_CAPTURE_TTL_SECONDS
    ]
    for tok in stale:
        _EXTENSION_CAPTURES.pop(tok, None)
    while len(_EXTENSION_CAPTURES) > _EXTENSION_CAPTURE_MAX:
        _EXTENSION_CAPTURES.popitem(last=False)


def _ext_store(html: str, source_url: str, title: str) -> str:
    token = _ext_secrets.token_urlsafe(18)
    record = {
        "html": html,
        "url": source_url,
        "title": title,
        "ts": time.time(),
    }
    with _EXTENSION_CAPTURE_LOCK:
        _EXTENSION_CAPTURES[token] = record
        _ext_prune_locked()
    return token


def _ext_get(token: str) -> dict | None:
    with _EXTENSION_CAPTURE_LOCK:
        rec = _EXTENSION_CAPTURES.get(token)
        if rec is None:
            return None
        # Touch to keep recently used in front (LRU-ish).
        _EXTENSION_CAPTURES.move_to_end(token, last=True)
        return dict(rec)


@app.route("/api/extension_capture", methods=["POST", "OPTIONS"])
def extension_capture_post():
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    html = payload.get("html")
    if not isinstance(html, str) or not html.strip():
        return jsonify({"ok": False, "error": "Missing 'html' field."}), 400
    if len(html.encode("utf-8", "replace")) > _EXTENSION_CAPTURE_MAX_BYTES:
        return jsonify(
            {
                "ok": False,
                "error": f"Captured HTML exceeds {_EXTENSION_CAPTURE_MAX_BYTES // (1024 * 1024)} MB cap.",
            }
        ), 413
    source_url = str(payload.get("url") or "").strip()
    title = str(payload.get("title") or "").strip() or source_url or "Captured page"
    token = _ext_store(html, source_url, title)
    base = request.host_url.rstrip("/")
    return jsonify(
        {
            "ok": True,
            "token": token,
            "viewerUrl": f"{base}/extension/snapshot/{token}",
            "snapshotPayloadUrl": f"{base}/api/extension_snapshot/{token}",
            "title": title,
            "url": source_url,
        }
    )


@app.route("/extension/snapshot/<token>", methods=["GET"])
def extension_snapshot_view(token: str):
    """Serve the captured HTML directly so the user (or any URL fetcher) can view it."""
    rec = _ext_get(token)
    if rec is None:
        return ("Snapshot not found or expired.", 404)
    resp = Response(rec["html"], mimetype="text/html; charset=utf-8")
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["X-Extension-Snapshot-Source"] = rec.get("url", "")
    return resp


@app.route("/api/extension_snapshot/<token>", methods=["GET"])
def extension_snapshot_payload(token: str):
    """Return the captured HTML in the webSnapshot payload shape.

    The reader's docrender pipeline can consume this directly without URL
    capture.
    """
    rec = _ext_get(token)
    if rec is None:
        return jsonify({"ok": False, "error": "Snapshot not found or expired."}), 404
    html = _inject_extension_snapshot_style(rec["html"])
    return jsonify(
        {
            "ok": True,
            "page": {
                "kind": "webSnapshot",
                "type": "webSnapshot",
                "html": html,
                "snapshot": {
                    "requestedUrl": rec.get("url", ""),
                    "finalUrl": rec.get("url", ""),
                    "title": rec.get("title", ""),
                    "createdAt": datetime.fromtimestamp(rec["ts"], tz=timezone.utc).isoformat(),
                    "htmlLength": len(html),
                    "capture": "chrome-extension",
                    "jsRendered": True,
                },
            },
        }
    )


# Bump this string whenever you deploy updated dictionaries or client code.
# All users will have their IndexedDB index cache wiped on next page load.
APP_DICT_VERSION = "2026-04-10-1"
app.jinja_env.globals["app_dict_version"] = APP_DICT_VERSION

# ---- Language Engine: production config, database, auth, payments ----
import config as le_config

if le_config.TRUST_PROXY_HEADERS:
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

if le_config.IS_PRODUCTION:
    CORS(
        app,
        origins=[le_config.APP_BASE_URL or "https://language-engine.ai"],
        supports_credentials=True,
    )
else:
    CORS(app)
app.config["JSON_AS_ASCII"] = False

app.config["SECRET_KEY"] = le_config.SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = le_config.DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["REMEMBER_COOKIE_DURATION"] = 60 * 60 * 24 * 30  # 30 days
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(le_config.IS_PRODUCTION)
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_SECURE"] = bool(le_config.IS_PRODUCTION)
app.config["PREFERRED_URL_SCHEME"] = "https" if le_config.IS_PRODUCTION else "http"
app.jinja_env.globals["public_base_url"] = le_config.APP_BASE_URL

from db import db as le_db

le_db.init_app(app)

from auth import auth_bp, login_manager

login_manager.init_app(app)
app.register_blueprint(auth_bp)

from payments import payments_bp

app.register_blueprint(payments_bp)

with app.app_context():
    import sqlalchemy

    if str(le_config.DATABASE_URL or "").startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(le_db.engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
            finally:
                cursor.close()

    le_db.create_all()
    # Migrate: add Gemini token usage columns if missing
    for column_name in ("llm_tokens_used", "llm_prompt_tokens_used", "llm_output_tokens_used"):
        try:
            le_db.session.execute(sqlalchemy.text(f"SELECT {column_name} FROM api_usage LIMIT 1"))
        except Exception:
            le_db.session.rollback()
            try:
                le_db.session.execute(
                    sqlalchemy.text(
                        f"ALTER TABLE api_usage ADD COLUMN {column_name} INTEGER DEFAULT 0"
                    )
                )
                le_db.session.commit()
            except Exception:
                le_db.session.rollback()
    try:
        le_db.session.execute(sqlalchemy.text("SELECT password_length FROM users LIMIT 1"))
    except Exception:
        le_db.session.rollback()
        try:
            le_db.session.execute(
                sqlalchemy.text("ALTER TABLE users ADD COLUMN password_length INTEGER DEFAULT 8")
            )
            le_db.session.commit()
        except Exception:
            le_db.session.rollback()
    try:
        le_db.session.execute(sqlalchemy.text("SELECT email_verified_at FROM users LIMIT 1"))
    except Exception:
        le_db.session.rollback()
        try:
            le_db.session.execute(
                sqlalchemy.text("ALTER TABLE users ADD COLUMN email_verified_at DATETIME")
            )
            le_db.session.execute(
                sqlalchemy.text(
                    "UPDATE users SET email_verified_at = CURRENT_TIMESTAMP WHERE email_verified_at IS NULL"
                )
            )
            le_db.session.commit()
        except Exception:
            le_db.session.rollback()
    try:
        le_db.session.execute(
            sqlalchemy.text("SELECT cancel_at_period_end FROM subscriptions LIMIT 1")
        )
    except Exception:
        le_db.session.rollback()
        try:
            le_db.session.execute(
                sqlalchemy.text(
                    "ALTER TABLE subscriptions ADD COLUMN cancel_at_period_end BOOLEAN DEFAULT 0"
                )
            )
            le_db.session.commit()
        except Exception:
            le_db.session.rollback()
    # Migrate entry_decomps to surface-form-only keying. Decomps are keyed by
    # (language, surface_form); rows with NULL surface_form were written under
    # the base entry's row_id and are contaminated (inflected-form decomps
    # bleeding onto stem lookups), so we delete them — they regenerate on demand.
    try:
        le_db.session.execute(sqlalchemy.text("SELECT surface_form FROM entry_decomps LIMIT 1"))
    except Exception:
        le_db.session.rollback()
        try:
            le_db.session.execute(
                sqlalchemy.text(
                    "ALTER TABLE entry_decomps ADD COLUMN surface_form TEXT DEFAULT NULL"
                )
            )
            le_db.session.commit()
        except Exception:
            le_db.session.rollback()
    try:
        le_db.session.execute(
            sqlalchemy.text(
                "DELETE FROM entry_decomps WHERE surface_form IS NULL OR surface_form = ''"
            )
        )
        le_db.session.execute(
            sqlalchemy.text("DROP INDEX IF EXISTS uq_entry_decomp_lang_alias_row_surface")
        )
        le_db.session.execute(
            sqlalchemy.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_entry_decomp_lang_surface "
                "ON entry_decomps(language, surface_form)"
            )
        )
        le_db.session.commit()
    except Exception:
        le_db.session.rollback()
    try:
        import gemini_dict

        gemini_dict.migrate_legacy_custom_entries()
        gemini_dict.ensure_custom_form_index()
    except Exception as exc:
        print(f"[WARN] Custom-entry SQLite migration failed: {type(exc).__name__}: {exc}")
    try:

        def _table_exists(name: str) -> bool:
            return (
                le_db.session.execute(
                    sqlalchemy.text(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"
                    ),
                    {"name": name},
                ).first()
                is not None
            )

        def _column_exists(table: str, column: str) -> bool:
            if not _table_exists(table):
                return False
            rows = (
                le_db.session.execute(sqlalchemy.text(f"PRAGMA table_info({table})"))
                .mappings()
                .all()
            )
            return any(row.get("name") == column for row in rows)

        for table, required_column, sql in (
            (
                "custom_dict_entries",
                "owner_user_id",
                "UPDATE custom_dict_entries SET owner_user_id = NULL WHERE owner_user_id IS NOT NULL",
            ),
            (
                "entry_notes",
                "user_id",
                "UPDATE entry_notes SET user_id = NULL WHERE user_id IS NOT NULL",
            ),
            (
                "entry_decomps",
                "user_id",
                "UPDATE entry_decomps SET user_id = NULL WHERE user_id IS NOT NULL",
            ),
            ("custom_entry_deletion_votes", None, "DELETE FROM custom_entry_deletion_votes"),
            ("gemini_deletion_votes", None, "DELETE FROM gemini_deletion_votes"),
            ("gemini_entry_owners", None, "DELETE FROM gemini_entry_owners"),
            ("synthetic_annotations", None, "DELETE FROM synthetic_annotations"),
            ("user_annotations", None, "DELETE FROM user_annotations"),
        ):
            if _table_exists(table) and (
                not required_column or _column_exists(table, required_column)
            ):
                le_db.session.execute(sqlalchemy.text(sql))
        le_db.session.commit()
    except Exception as exc:
        le_db.session.rollback()
        print(f"[WARN] Account-content attribution cleanup failed: {type(exc).__name__}: {exc}")

if le_config.ENABLE_DEBUG_PANEL:
    app.register_blueprint(debug_bp)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

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


def _get_custom_dict_entry(
    entry_id: str = "", entry_row_id: int | str = 0, language: str = "", headword: str = ""
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
    removed = gemini_dict.remove_tsv_entry(entry.language, entry.headword, entry_id=entry.entry_id)
    if not removed:
        return False

    le_db.session.commit()
    _invalidate_sqlite_segmenter_cache(entry.language, lookup_texts)
    return True


# ---------------------------------------------------------------------------
# Central paid-feature gate
# ---------------------------------------------------------------------------

# Routes listed here require a paid tier. The @app.before_request hook
# checks incoming requests against this set and returns 403 for free users.
# To gate a new route, just add its endpoint name here.
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


@app.before_request
def _enforce_paid_feature_gate():
    if request.endpoint not in _PAID_FEATURE_ENDPOINTS:
        return None
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401
    if current_user.tier == "free":
        return jsonify({"ok": False, "error": "Paid feature.", "upgrade_required": True}), 403
    return None


# ---------------------------------------------------------------------------
# Language config cache
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Server-side SQLite dictionary segmentation
# ---------------------------------------------------------------------------

_LOOKUP_UPOS_COLORS = {
    "ADJ": "#fde68a",
    "ADP": "#e0f2fe",
    "ADV": "#fee2e2",
    "AUX": "#e0e7ff",
    "CCONJ": "#cffafe",
    "DET": "#f1f5f9",
    "INTJ": "#fcd34d",
    "NOUN": "#bbf7d0",
    "NUM": "#f5d0fe",
    "PART": "#f4f4f5",
    "PRON": "#e2e8f0",
    "PROPN": "#c7d2fe",
    "PUNCT": "#e5e7eb",
    "SCONJ": "#bae6fd",
    "SYM": "#f3e8ff",
    "VERB": "#fda4af",
    "X": "#d1d5db",
}

_ACTUAL_RESOLUTION_LABELS = {
    "exact_match": "exact match",
    "greedy_segmentation": "greedy segmentation",
    "exact_lemma_match": "exact lemma match",
    "greedy_lemma_match": "partial lemma match + greedy segmentation",
    "lemma_override": "lemma override",
    "lemma_partial_override": "exact lemma parts + greedy gaps",
}

_segmenter_cache: dict[tuple[str, tuple[str, ...], bool], Any] = {}
_segmenter_cache_lock = threading.Lock()


def _dedupe_text_list(values: Sequence[Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _normalize_selected_sources(
    raw_sources: Sequence[Any] | None, single_source: Any = ""
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in list(raw_sources or []):
        text = str(raw or "").strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    one = str(single_source or "").strip().lower()
    if one and one not in seen:
        out.append(one)
    return out


def _get_requested_sources(payload: dict[str, Any] | None = None) -> list[str]:
    data = payload or {}
    raw_sources = data.get("sources")
    query_sources = request.args.get("sources", "")
    source_list: list[str] = []
    if isinstance(raw_sources, (list, tuple)):
        source_list.extend(list(raw_sources))
    elif isinstance(raw_sources, str) and raw_sources.strip():
        source_list.extend([part.strip() for part in raw_sources.split(",") if part.strip()])
    if query_sources:
        source_list.extend([part.strip() for part in query_sources.split(",") if part.strip()])
    single_source = data.get("source") or request.args.get("source", "")
    return _normalize_selected_sources(source_list, single_source)


def _split_segmenter_sources(
    selected_sources: Sequence[str] | None,
) -> tuple[list[str], bool, bool]:
    selected = _normalize_selected_sources(selected_sources)
    if not selected:
        return [], True, False
    include_custom = "custom" in selected
    db_sources = [src for src in selected if src != "custom"]
    custom_only = include_custom and not db_sources
    return db_sources, include_custom, custom_only


def _get_sqlite_segmenter(lang_code: str, selected_sources: Sequence[str] | None):
    from sqlite_segmenter import SQLiteDictionarySegmenter

    lang = str(lang_code or "").strip().lower()
    if not lang:
        return None
    db_sources, include_custom, custom_only = _split_segmenter_sources(selected_sources)
    if custom_only:
        return None
    cache_key = (lang, tuple(db_sources), include_custom)
    with _segmenter_cache_lock:
        cached = _segmenter_cache.get(cache_key)
        if cached is not None:
            return cached
        segmenter = SQLiteDictionarySegmenter(
            lang,
            sources=db_sources or None,
            include_custom_entries=include_custom,
        )
        _segmenter_cache[cache_key] = segmenter
        return segmenter


def _collect_lookup_texts_for_entry(entry: dict[str, Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add_text(raw: Any) -> None:
        text = str(raw or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        out.append(text)

    if not isinstance(entry, dict):
        return out

    for key in ("headword", "surface_form", "head", "text", "lemma", "lemma_form", "morph_base"):
        add_text(entry.get(key))

    forms = entry.get("forms")
    if isinstance(forms, list):
        for form in forms:
            if isinstance(form, (list, tuple)) and form:
                add_text(form[0])
            elif isinstance(form, dict):
                add_text(form.get("word") or form.get("form") or form.get("headword"))

    return out


def _invalidate_sqlite_segmenter_cache(
    lang_code: str = "", lookup_texts: Sequence[str] | str | None = None
) -> None:
    lang = str(lang_code or "").strip().lower()
    texts = _dedupe_text_list(
        [lookup_texts] if isinstance(lookup_texts, str) else list(lookup_texts or [])
    )
    if not lang or not texts:
        return
    with _segmenter_cache_lock:
        for key, segmenter in list(_segmenter_cache.items()):
            if not key or key[0] != lang:
                continue
            if segmenter is not None and hasattr(segmenter, "invalidate_lookup_texts"):
                try:
                    segmenter.invalidate_lookup_texts(texts)
                except Exception:
                    pass


def _entry_source_tag(entry: dict[str, Any] | None) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("_source") or entry.get("source") or "").strip()


def _entry_reading(entry: dict[str, Any] | None) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(
        entry.get("reading") or entry.get("romanization") or entry.get("pinyin") or ""
    ).strip()


def _entry_pos(entry: dict[str, Any] | None) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("pos") or entry.get("pos_raw") or "").strip()


def _clone_entry_with_nlp(
    entry: dict[str, Any] | None, upos: str = "", xpos: str = ""
) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    clone = dict(entry)
    upos_value = str(upos or "").strip()
    xpos_value = str(xpos or "").strip()
    clone["upos"] = upos_value
    clone["xpos"] = xpos_value
    clone["tag"] = xpos_value
    if upos_value:
        clone["upos_label"] = upos_value
        clone["upos_color"] = _LOOKUP_UPOS_COLORS.get(upos_value, "#d1d5db")
    else:
        clone.pop("upos_label", None)
        clone.pop("upos_color", None)
    return clone


def _decorate_entries_with_nlp(
    entries: Sequence[dict[str, Any]] | None, upos: str = "", xpos: str = ""
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in entries or []:
        if not isinstance(raw, dict):
            continue
        out.append(_clone_entry_with_nlp(raw, upos, xpos))
    return out


def _fill_effective_upos(fill_row: Mapping[str, Any] | None, fallback_upos: str = "") -> str:
    if not isinstance(fill_row, Mapping):
        return str(fallback_upos or "").strip()
    return str(fill_row.get("_lemma_upos_hint") or fallback_upos or "").strip()


def _fill_effective_xpos(fill_row: Mapping[str, Any] | None, fallback_xpos: str = "") -> str:
    if not isinstance(fill_row, Mapping):
        return str(fallback_xpos or "").strip()
    return str(
        fill_row.get("_xpos_hint") or fill_row.get("_lemma_xpos_hint") or fallback_xpos or ""
    ).strip()


def _entry_senses_lines(entry: dict[str, Any] | None, fallback_head: str = "") -> list[str]:
    if not isinstance(entry, dict):
        return []
    senses = entry.get("senses") or []
    head = str(entry.get("surface_form") or entry.get("headword") or fallback_head or "")
    roman = _entry_reading(entry)
    pos = _entry_pos(entry)
    out: list[str] = []
    if isinstance(senses, list) and senses:
        first = senses[0]
        if isinstance(first, dict):
            for idx, sense in enumerate(senses):
                glosses = [
                    str(g or "").strip()
                    for g in list(sense.get("glosses") or [])
                    if str(g or "").strip()
                ]
                if not glosses:
                    continue
                line = "; ".join(glosses)
                if idx == 0:
                    out.append(f"{head}	{roman}	{pos}	{line}")
                else:
                    out.append(f"			{line}")
            return out
        for idx, sense in enumerate(senses):
            line = str(sense or "").strip()
            if not line:
                continue
            if "	" in line:
                out.append(line)
            elif idx == 0:
                out.append(f"{head}	{roman}	{pos}	{line}")
            else:
                out.append(f"			{line}")

        return out
    glosses = entry.get("glosses")
    if isinstance(glosses, list) and glosses:
        for idx, gloss in enumerate(glosses):
            line = str(gloss or "").strip()
            if not line:
                continue
            if idx == 0:
                out.append(f"{head}	{roman}	{pos}	{line}")
            else:
                out.append(f"			{line}")
    return out


def _merge_all_entries(head: str, entries: Sequence[dict[str, Any]] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for entry in entries or []:
        for line in _entry_senses_lines(entry, fallback_head=head):
            if not line or line in seen:
                continue
            seen.add(line)
            out.append(line)
    return out


def _build_entry_groups(
    entries: Sequence[dict[str, Any]] | None, surface: str
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for entry in entries or []:
        headword = str(entry.get("surface_form") or entry.get("headword") or surface or "").strip()
        base_headword = str(entry.get("headword") or "").strip()
        pos_group: dict[str, Any] = {
            "headword": headword,
            "base_headword": base_headword,
            "is_inflected_surface": bool(headword and base_headword and headword != base_headword),
            "reading": _entry_reading(entry),
            "pos": _entry_pos(entry),
            "senses": copy.deepcopy(entry.get("senses_full") or entry.get("senses") or []),
        }
        morph_info = _dedupe_text_list(
            entry.get("morph_info")
            if isinstance(entry.get("morph_info"), list)
            else [entry.get("morph_info")]
        )
        morph_base = str(entry.get("morph_base") or "").strip()
        grammar = str(entry.get("grammar") or "").strip()
        if morph_info:
            pos_group["morph_info"] = morph_info
        if morph_base:
            pos_group["morph_base"] = morph_base
        if grammar:
            pos_group["grammar"] = grammar
        for forms_key in ("hanja_forms", "hangeul_forms"):
            forms_val = entry.get(forms_key)
            if isinstance(forms_val, list) and forms_val:
                pos_group[forms_key] = copy.deepcopy(forms_val)
        group: dict[str, Any] = {
            "headword": headword,
            "reading": _entry_reading(entry),
            "pos_groups": [pos_group],
        }
        etymology = str(entry.get("etymology") or "")
        if etymology:
            group["etymology"] = etymology
        for list_key in ("alt_forms", "synonyms", "antonyms", "derived", "related"):
            list_val = entry.get(list_key)
            if isinstance(list_val, list) and list_val:
                group[list_key] = copy.deepcopy(list_val)
        groups.append(group)
    return groups


_NOUN_AFFIX_POS = (
    "suffix",
    "prefix",
    "affix",
    "infix",
    "interfix",
    "circumfix",
    "combining_form",
)

_UPOS_TO_KAIKKI_POS = {
    "NOUN": ["noun", "classifier", "name", "contraction", "counter", *_NOUN_AFFIX_POS],
    "VERB": ["verb"],
    "ADJ": ["adj", "adnominal"],
    "ADV": ["adv"],
    "PROPN": ["name", "noun"],
    "ADP": ["prep", "postp", "prep_phrase", "particle", "circumpos"],
    "AUX": ["verb"],
    "CCONJ": ["conj"],
    "SCONJ": ["conj"],
    "DET": ["det", "article", "adnominal"],
    "PRON": ["pron"],
    "NUM": ["num", "counter"],
    "PART": ["particle"],
    "INTJ": ["intj"],
    "PUNCT": ["punct", "symbol"],
    "SYM": ["symbol", "punct"],
    "X": ["syllable", "[]"],
}

_LANGUAGE_UPOS_EXTRA_POS = {
    "ja": {
        "AUX": ["suffix"],
        "CCONJ": ["suffix"],
        "SCONJ": ["suffix"],
    },
}

_FILTER_EXEMPT_POS = frozenset({"proverb", "phrase", "prep_phrase"})
_ALWAYS_FILTERED_POS = frozenset({"character", "romanization", "syllable", "punct", "symbol"})
_GREEDY_FILTER_MODES = frozenset(
    {"greedy", "lemma_greedy", "lemma_partial_greedy", "greedy_lemma_mismatch"}
)


def _split_upos_tags(raw_upos: Any) -> list[str]:
    text = str(raw_upos or "").strip()
    if not text:
        return []
    parts = (
        [text] if "+" not in text else [part.strip() for part in text.split("+") if part.strip()]
    )
    return [part.upper() for part in parts if part]


def _entry_etym_key(entry: dict[str, Any] | None) -> str:
    if not isinstance(entry, dict):
        return "t:"
    try:
        etym_num = int(entry.get("etymology_number") or 0)
    except Exception:
        etym_num = 0
    if etym_num > 0:
        return f"n:{etym_num}"
    return f"t:{str(entry.get('etymology') or '')}"


def _entry_filter_identity(entry: dict[str, Any] | None) -> tuple[str, ...]:
    if not isinstance(entry, dict):
        return ("",)
    return (
        str(entry.get("entry_id") or ""),
        str(entry.get("headword") or ""),
        str(entry.get("surface_form") or ""),
        str(entry.get("reading") or entry.get("romanization") or ""),
        str(entry.get("pos_raw") or entry.get("pos") or "").strip().lower(),
        str(entry.get("etymology_number") or ""),
        str(entry.get("etymology") or ""),
        str(entry.get("_source") or entry.get("source") or ""),
        str(entry.get("morph_base") or ""),
    )


def _dedupe_entry_list(entries: Sequence[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        ident = _entry_filter_identity(entry)
        if ident in seen:
            continue
        seen.add(ident)
        out.append(entry)
    return out


def _get_language_upos_extra_pos(lang_code: str, upos_tag: str) -> list[str]:
    lang = str(lang_code or "").strip().lower()
    tag = str(upos_tag or "").strip().upper()
    raw = (_LANGUAGE_UPOS_EXTRA_POS.get(lang) or {}).get(tag) or []
    return [str(item or "").strip().lower() for item in raw if str(item or "").strip()]


def _split_entries_by_upos(
    entries: Sequence[dict[str, Any]] | None,
    upos: str,
    *,
    lang_code: str = "",
    greedy_match: bool = False,
    greedy_multi_fill: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base_entries = [entry for entry in list(entries or []) if isinstance(entry, dict)]
    if not base_entries:
        return [], []

    greedy_mode = bool(greedy_match or greedy_multi_fill)
    affix_preferred = set(_NOUN_AFFIX_POS) if greedy_mode else set()
    active_always_filtered = set(_ALWAYS_FILTERED_POS)
    if greedy_mode:
        active_always_filtered.difference_update(affix_preferred)

    if len(base_entries) <= 1:
        only_pos = (
            str(base_entries[0].get("pos_raw") or base_entries[0].get("pos") or "").strip().lower()
        )
        if only_pos in active_always_filtered:
            return [], base_entries[:]
        return base_entries[:], []

    upos_tags = _split_upos_tags(upos)
    allowed: set[str] = set()
    recognized = False
    for tag in upos_tags:
        mapped = [
            str(item or "").strip().lower()
            for item in _UPOS_TO_KAIKKI_POS.get(tag, [])
            if str(item or "").strip()
        ]
        extra_mapped = _get_language_upos_extra_pos(lang_code, tag)
        combined = mapped + extra_mapped
        if not combined:
            continue
        recognized = True
        allowed.update(combined)

    if not upos_tags or not recognized or not allowed:
        pri: list[dict[str, Any]] = []
        oth: list[dict[str, Any]] = []
        has_affix_preferred = greedy_mode and any(
            str(entry.get("pos_raw") or entry.get("pos") or "").strip().lower() in affix_preferred
            for entry in base_entries
        )
        for entry in base_entries:
            pos_raw = str(entry.get("pos_raw") or entry.get("pos") or "").strip().lower()
            if has_affix_preferred:
                if pos_raw in affix_preferred:
                    pri.append(entry)
                else:
                    oth.append(entry)
                continue
            if pos_raw in active_always_filtered:
                oth.append(entry)
            else:
                pri.append(entry)
        return pri, oth

    etym_groups: dict[str, list[dict[str, Any]]] = {}
    etym_order: list[str] = []
    for entry in base_entries:
        key = _entry_etym_key(entry)
        if key not in etym_groups:
            etym_groups[key] = []
            etym_order.append(key)
        etym_groups[key].append(entry)

    primary: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for key in etym_order:
        group = etym_groups.get(key) or []
        group_primary: list[dict[str, Any]] = []
        group_other: list[dict[str, Any]] = []
        has_allowed_match = False
        for entry in group:
            pos_raw = str(entry.get("pos_raw") or entry.get("pos") or "").strip().lower()
            if pos_raw in active_always_filtered:
                group_other.append(entry)
                continue
            if pos_raw in allowed or pos_raw in affix_preferred:
                has_allowed_match = True
                group_primary.append(entry)
            elif pos_raw in _FILTER_EXEMPT_POS:
                group_primary.append(entry)
            else:
                group_other.append(entry)
        if has_allowed_match:
            primary.extend(group_primary)
            other.extend(group_other)
        elif group_primary:
            primary.extend(group_primary)
            other.extend(group_other)
        else:
            other.extend(group)

    if not primary:
        non_always_filtered: list[dict[str, Any]] = []
        always_filtered: list[dict[str, Any]] = []
        for entry in base_entries:
            pos_raw = str(entry.get("pos_raw") or entry.get("pos") or "").strip().lower()
            if pos_raw in active_always_filtered:
                always_filtered.append(entry)
            else:
                non_always_filtered.append(entry)
        if non_always_filtered and always_filtered:
            return non_always_filtered, always_filtered
        if always_filtered:
            return [], always_filtered
        return base_entries[:], []

    return primary, other


def _split_entries_for_display(
    entries: Sequence[dict[str, Any]] | None,
    *,
    lang_code: str = "",
    upos: str = "",
    fill_mode: str = "",
    greedy_multi_fill: bool = False,
    preferred_entries: Sequence[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base_entries = _dedupe_entry_list(entries)
    if not base_entries:
        return [], []

    preferred_idents = {
        _entry_filter_identity(entry)
        for entry in list(preferred_entries or [])
        if isinstance(entry, dict)
    }
    preferred_subset = [
        entry for entry in base_entries if _entry_filter_identity(entry) in preferred_idents
    ]
    use_preferred_subset = 0 < len(preferred_subset) < len(base_entries)
    candidate_entries = preferred_subset if use_preferred_subset else base_entries
    candidate_idents = {_entry_filter_identity(entry) for entry in candidate_entries}
    remainder_entries = [
        entry for entry in base_entries if _entry_filter_identity(entry) not in candidate_idents
    ]

    primary, other = _split_entries_by_upos(
        candidate_entries,
        upos,
        lang_code=lang_code,
        greedy_match=str(fill_mode or "").strip().lower() in _GREEDY_FILTER_MODES,
        greedy_multi_fill=greedy_multi_fill,
    )
    shown_entries = _dedupe_entry_list(primary or candidate_entries)
    shown_idents = {_entry_filter_identity(entry) for entry in shown_entries}
    combined_other = list(other or []) + remainder_entries
    hidden_entries = [
        entry
        for entry in _dedupe_entry_list(combined_other)
        if _entry_filter_identity(entry) not in shown_idents
    ]
    return shown_entries, hidden_entries


def _build_fill_surface_slices(
    surface: str, fills: Sequence[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    surface_text = str(surface or "")
    rows = list(fills or [])
    if not surface_text or len(rows) < 2:
        return []

    explicit_rows = 0
    explicit_valid = True
    explicit_slices: dict[tuple[int, int], dict[str, Any]] = {}
    for idx, row in enumerate(rows):
        start_raw = row.get("_surface_start")
        end_raw = row.get("_surface_end")
        if start_raw is None and end_raw is None:
            continue
        explicit_rows += 1
        try:
            start = int(start_raw)
            end = int(end_raw)
        except Exception:
            explicit_valid = False
            break
        if start < 0 or end <= start or end > len(surface_text):
            explicit_valid = False
            break
        explicit_slices.setdefault((start, end), {"start": start, "end": end, "fill_indexes": []})[
            "fill_indexes"
        ].append(idx)
    if explicit_rows == len(rows) and explicit_valid:
        ordered = sorted(explicit_slices.values(), key=lambda item: (item["start"], item["end"]))
        last_end = 0
        for item in ordered:
            if item["start"] < last_end:
                return []
            item["fill_indexes"].sort()
            last_end = item["end"]
        return ordered

    cursor = 0
    slices: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        piece = str(row.get("text") or row.get("head") or "")
        if not piece:
            return []
        if surface_text[cursor : cursor + len(piece)] != piece:
            return []
        slices.append({"start": cursor, "end": cursor + len(piece), "fill_indexes": [idx]})
        cursor += len(piece)
    if cursor != len(surface_text):
        return []
    return slices


def _safe_json_load(raw: Any) -> Any:
    if isinstance(raw, (list, dict)):
        return copy.deepcopy(raw)
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _list_text_values(raw: Any) -> list[str]:
    out: list[str] = []
    if isinstance(raw, (list, tuple, set)):
        for item in raw:
            text = str(item or "").strip()
            if text:
                out.append(text)
    else:
        text = str(raw or "").strip()
        if text:
            out.append(text)
    return out


def _normalize_entry_form_rows(raw: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    if isinstance(raw, str):
        raw = _safe_json_load(raw)
    if not isinstance(raw, list):
        return rows
    for item in raw:
        if isinstance(item, (list, tuple)):
            word = str(item[0] or "") if len(item) > 0 else ""
            commentary = str(item[1] or "") if len(item) > 1 else ""
            romanization = str(item[2] or "") if len(item) > 2 else ""
            rows.append([word, commentary, romanization])
        elif isinstance(item, dict):
            rows.append(
                [
                    str(
                        item.get("word")
                        or item.get("form")
                        or item.get("headword")
                        or item.get("form_text")
                        or item.get("display_text")
                        or ""
                    ),
                    str(item.get("commentary") or item.get("tags") or ""),
                    str(
                        item.get("romanization")
                        or item.get("reading")
                        or item.get("form_roman")
                        or ""
                    ),
                ]
            )
        else:
            rows.append([str(item or ""), "", ""])
    return rows


# Tags that indicate a form row is needed for upstream UI display (e.g.
# Chinese characters beside Korean/Vietnamese headwords).  Everything
# else is only useful for the full-forms panel which can lazy-load.
_HYDRATION_KEEP_FORM_TAGS = frozenset(
    {
        "hanja",
        "hangeul",
        "cjk",
        "sinitic",
        "hán-nôm",
        "han-nom",
        "hannom",
    }
)


_SPECIAL_DISPLAY_FORM_TAG_TO_BUCKET = {
    "hanja": "hanja",
    "hangeul": "hangeul",
    "cjk": "cjk",
    "sinitic": "cjk",
    "hán-nôm": "cjk",
    "han-nom": "cjk",
    "hannom": "cjk",
}


def _split_special_display_form_tags(raw_tags: Any) -> list[str]:
    text = str(raw_tags or "").strip().lower()
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw_part in re.split(r"[;|,\s]+", text):
        part = str(raw_part or "").strip()
        if not part:
            continue
        if part not in seen:
            seen.add(part)
            out.append(part)
        folded = unicodedata.normalize("NFKD", part)
        folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
        folded = folded.replace("đ", "d")
        if folded and folded not in seen:
            seen.add(folded)
            out.append(folded)
    return out


def _merge_entry_form_rows(*row_groups: Sequence[Sequence[str]] | None) -> list[list[str]]:
    out: list[list[str]] = []
    seen: set[tuple[str, str, str]] = set()
    for group in row_groups:
        for raw_row in list(group or []):
            row = [
                str(raw_row[0] or "") if len(raw_row) > 0 else "",
                str(raw_row[1] or "") if len(raw_row) > 1 else "",
                str(raw_row[2] or "") if len(raw_row) > 2 else "",
            ]
            row_key = tuple(row)
            if row_key in seen:
                continue
            seen.add(row_key)
            out.append(row)
    return out


def _normalize_special_display_form_rows(
    form_rows: Sequence[Sequence[str]] | None,
) -> tuple[list[list[str]], dict[str, list[str]]]:
    normalized_rows: list[list[str]] = []
    seen_rows: set[tuple[str, str, str]] = set()
    bucket_values: dict[str, list[str]] = {
        "hanja": [],
        "hangeul": [],
        "cjk": [],
    }
    seen_bucket_values: dict[str, set[str]] = {
        "hanja": set(),
        "hangeul": set(),
        "cjk": set(),
    }

    for raw_row in list(form_rows or []):
        word = str(raw_row[0] or "") if len(raw_row) > 0 else ""
        commentary = str(raw_row[1] or "") if len(raw_row) > 1 else ""
        romanization = str(raw_row[2] or "") if len(raw_row) > 2 else ""
        normalized_tags = _split_special_display_form_tags(commentary)
        appended_tags: list[str] = []
        for tag in normalized_tags:
            bucket = _SPECIAL_DISPLAY_FORM_TAG_TO_BUCKET.get(tag)
            if not bucket:
                continue
            if word and word not in seen_bucket_values[bucket]:
                seen_bucket_values[bucket].add(word)
                bucket_values[bucket].append(word)
            if bucket not in normalized_tags and bucket not in appended_tags:
                appended_tags.append(bucket)
        normalized_commentary = commentary
        if appended_tags:
            normalized_commentary += (";" if normalized_commentary else "") + ";".join(
                appended_tags
            )
        row = [word, normalized_commentary, romanization]
        row_key = tuple(row)
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)
        normalized_rows.append(row)

    return normalized_rows, bucket_values


def _build_entry_forms_payload(
    entry: Mapping[str, Any] | None, *, include_matched_rows: bool
) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        return {}
    out: dict[str, Any] = {}

    form_rows = _normalize_entry_form_rows(entry.get("forms"))
    if not form_rows:
        form_rows = _normalize_entry_form_rows(entry.get("_forms_raw") or entry.get("_forms_json"))
    if include_matched_rows:
        form_rows = _merge_entry_form_rows(
            form_rows, _normalize_entry_form_rows(entry.get("_matched_forms"))
        )

    normalized_rows, special_buckets = _normalize_special_display_form_rows(form_rows)
    if normalized_rows:
        out["rows"] = normalized_rows

    form_sources = (
        ("kanji", "kanji"),
        ("readings", "readings"),
        ("alt_forms", "alt"),
        ("korean_hanja_variants", "hanja"),
        ("korean_hangeul_variants", "hangeul"),
        ("vietnamese_cjk_variants", "cjk"),
    )
    for src_key, out_key in form_sources:
        values = _list_text_values(entry.get(src_key))
        if out_key in special_buckets:
            values += list(special_buckets[out_key])
        if values:
            out[out_key] = _dedupe_text_list(values)
    return out


def _canonical_entry_forms(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    return _build_entry_forms_payload(entry, include_matched_rows=True)


def _build_entry_spelling_header(entry: Mapping[str, Any] | None) -> str:
    if not isinstance(entry, Mapping):
        return ""
    existing = str(entry.get("spelling_header") or "").strip()
    if existing:
        return existing
    kanji = _list_text_values(entry.get("kanji"))
    readings = _list_text_values(entry.get("readings"))
    if kanji:
        head = "・".join(kanji)
        if readings:
            head += "【" + "・".join(readings) + "】"
        return head
    if readings:
        return "・".join(readings)
    return ""


def _canonical_entry_senses(entry: Mapping[str, Any] | None) -> list[Any]:
    if not isinstance(entry, Mapping):
        return []

    direct = entry.get("senses_full") or entry.get("senses") or []
    if isinstance(direct, list) and direct:
        return copy.deepcopy(direct)

    raw_glosses: Any = entry.get("glosses")
    if isinstance(raw_glosses, str):
        text = raw_glosses.strip()
        if not text:
            return []
        parsed = _safe_json_load(text)
        if parsed is not None:
            raw_glosses = parsed
        else:
            return [
                {"glosses": [part]} for part in (chunk.strip() for chunk in text.split(";")) if part
            ]

    if isinstance(raw_glosses, Mapping):
        raw_glosses = [raw_glosses]
    if not isinstance(raw_glosses, list):
        return []

    out: list[Any] = []
    for raw in raw_glosses:
        if isinstance(raw, Mapping):
            glosses = [
                str(item or "").strip()
                for item in list(raw.get("glosses") or [])
                if str(item or "").strip()
            ]
            if not glosses:
                fallback = str(raw.get("gloss") or raw.get("text") or "").strip()
                if fallback:
                    glosses = [fallback]
            if not glosses:
                continue
            sense = copy.deepcopy(dict(raw))
            sense["glosses"] = glosses
            out.append(sense)
            continue
        text = str(raw or "").strip()
        if text:
            out.append({"glosses": [text]})
    return out


def _canonical_entry_payload(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        return {}
    raw_entry_id = str(entry.get("entry_id") or "").strip()
    headword = str(entry.get("headword") or entry.get("surface_form") or "").strip()
    surface_form = str(entry.get("surface_form") or "").strip()
    # For form-index matches the server entry has no surface_form but does have
    # _matched_forms with the actual form text that triggered the match.
    if not surface_form and str(entry.get("_match_kind") or "").strip().lower() == "form":
        _mfs = entry.get("_matched_forms") or []
        if isinstance(_mfs, list) and _mfs:
            _form_match_key = str(entry.get("_form_match_key") or "").strip()
            _chosen = None
            if _form_match_key:
                for _mf in _mfs:
                    if _form_match_key in (_mf.get("index_keys") or []):
                        _chosen = _mf
                        break
            if _chosen is None:
                _chosen = _mfs[0]
            _ft = str(
                (_chosen or {}).get("display_text") or (_chosen or {}).get("form_text") or ""
            ).strip()
            if _ft and _ft != headword:
                surface_form = _ft
    reading = _entry_reading(dict(entry))
    pos = str(entry.get("pos") or "").strip()
    pos_raw = str(entry.get("pos_raw") or pos or "").strip()
    senses = _canonical_entry_senses(entry)
    forms = _canonical_entry_forms(entry)
    forms_meta = _build_jmdict_forms_meta_bundle(dict(entry))
    spelling_header = _build_entry_spelling_header(entry)
    source_tag = _entry_source_tag(dict(entry)) or str(entry.get("source") or "").strip()
    commentary = str(entry.get("_commentary") or entry.get("commentary") or "").strip()
    lemma = str(entry.get("_lemma") or entry.get("lemma") or entry.get("lemma_form") or "").strip()
    morph_info_raw = entry.get("morph_info")
    morph_info = (
        morph_info_raw
        if isinstance(morph_info_raw, list)
        else ([morph_info_raw] if morph_info_raw else [])
    )
    if not morph_info and commentary and source_tag in {"gemini", "user_created"}:
        morph_info = [commentary]
    # For form-index matches, morph tags live in _matched_forms[].tags and the
    # base word is the entry headword itself.  Pull them in when not already set.
    matched_forms = entry.get("_matched_forms") or []
    if not morph_info and isinstance(matched_forms, list):
        seen_tags: set[str] = set()
        collected: list[str] = []
        for mf in matched_forms:
            raw_tags = str(mf.get("tags") or "").strip() if isinstance(mf, dict) else ""
            if raw_tags and raw_tags not in seen_tags:
                seen_tags.add(raw_tags)
                collected.append(raw_tags)
        if collected:
            morph_info = collected

    out: dict[str, Any] = {
        "entry_id": raw_entry_id,
        "headword": headword,
        "source": source_tag,
        "senses": senses,
    }
    if raw_entry_id:
        out["_source_entry_id"] = raw_entry_id
    if surface_form and surface_form != headword:
        out["surface_form"] = surface_form
    if reading:
        out["reading"] = reading
    if pos:
        out["pos"] = pos
    if pos_raw:
        out["pos_raw"] = pos_raw
    if forms:
        out["forms"] = forms
    if forms_meta:
        out["forms_meta"] = forms_meta
    if spelling_header:
        out["spelling_header"] = spelling_header
    if commentary:
        out["commentary"] = commentary
        out["_commentary"] = commentary
    if lemma:
        out["lemma"] = lemma
        out["_lemma"] = lemma
    morph_base = str(entry.get("morph_base") or "").strip()
    if not morph_base and lemma and source_tag in {"gemini", "user_created"}:
        morph_base = lemma
    # For form-index matches, the entry headword is the canonical base form.
    if not morph_base and isinstance(matched_forms, list) and matched_forms:
        morph_base = headword
    if morph_base:
        out["morph_base"] = morph_base
    clean_morph_info = [str(item or "").strip() for item in morph_info if str(item or "").strip()]
    if clean_morph_info:
        out["morph_info"] = clean_morph_info
    clean_matched_forms = [copy.deepcopy(mf) for mf in matched_forms if isinstance(mf, Mapping)]
    if clean_matched_forms:
        out["_matched_forms"] = clean_matched_forms
    storage_kind = str(entry.get("_storage_kind") or "").strip().lower()
    if storage_kind:
        out["_storage_kind"] = storage_kind
    storage_db_alias = str(entry.get("_storage_db_alias") or "").strip()
    if storage_db_alias:
        out["_storage_db_alias"] = storage_db_alias
    storage_row_id = int(entry.get("_storage_row_id") or 0)
    if storage_row_id > 0:
        out["_storage_row_id"] = storage_row_id
    match_kind = str(entry.get("_match_kind") or "").strip().lower()
    if match_kind:
        out["_match_kind"] = match_kind
    form_match_key = str(entry.get("_form_match_key") or "").strip()
    if form_match_key:
        out["_form_match_key"] = form_match_key
    grammar = str(entry.get("grammar") or "").strip()
    if grammar:
        out["grammar"] = grammar
    return out


def _flatten_structured_senses(senses: Sequence[Any] | None) -> list[str]:
    out: list[str] = []
    for raw in senses or []:
        if isinstance(raw, Mapping):
            glosses = [
                str(item or "").strip()
                for item in list(raw.get("glosses") or [])
                if str(item or "").strip()
            ]
            if glosses:
                out.append("; ".join(glosses))
                continue
        text = str(raw or "").strip()
        if text:
            out.append(text)
    return out


_FORM_ALT_FILTER_TAGS = frozenset({"alternative", "redirect", "eumhun", "syllable"})


def _strict_entry_forms(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    return _build_entry_forms_payload(entry, include_matched_rows=True)


def _runtime_entry_id(entry: Mapping[str, Any] | None) -> str:
    if not isinstance(entry, Mapping):
        return ""
    storage_kind = str(entry.get("_storage_kind") or "").strip().lower()
    db_alias = str(entry.get("_storage_db_alias") or "").strip()
    try:
        row_id = int(entry.get("_storage_row_id") or 0)
    except Exception:
        row_id = 0
    if not storage_kind or not db_alias or row_id <= 0:
        return ""
    return f"{storage_kind}|{db_alias}|{row_id}"


def _hydrated_ref_key(entry: Mapping[str, Any] | None) -> str:
    if not isinstance(entry, Mapping):
        return ""
    storage_kind = str(entry.get("_storage_kind") or "").strip().lower()
    db_alias = str(entry.get("_storage_db_alias") or "").strip()
    try:
        row_id = int(entry.get("_storage_row_id") or 0)
    except Exception:
        row_id = 0
    try:
        form_row_id = int(entry.get("_storage_form_row_id") or 0)
    except Exception:
        form_row_id = 0
    if not storage_kind or not db_alias or row_id <= 0:
        return ""
    if form_row_id > 0:
        return f"{storage_kind}|{db_alias}|{row_id}|{form_row_id}"
    return f"{storage_kind}|{db_alias}|{row_id}"


def _split_form_tag_bundle(raw_tags: Any) -> list[str]:
    text = str(raw_tags or "").strip().lower()
    if not text:
        return []
    return [part for part in re.split(r"[;|,\s]+", text) if part]


def _has_alt_bucket_tag(raw_tags: Any) -> bool:
    for part in _split_form_tag_bundle(raw_tags):
        if part in _FORM_ALT_FILTER_TAGS:
            return True
    return False


def _select_triggering_matched_form(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        return {}
    matched_forms = entry.get("_matched_forms") or []
    if not isinstance(matched_forms, list) or not matched_forms:
        return {}
    form_match_key = str(entry.get("_form_match_key") or "").strip()
    if form_match_key:
        for raw in matched_forms:
            if not isinstance(raw, Mapping):
                continue
            if form_match_key in list(raw.get("index_keys") or []):
                return copy.deepcopy(dict(raw))
    for raw in matched_forms:
        if isinstance(raw, Mapping):
            return copy.deepcopy(dict(raw))
    return {}


def _build_hydrated_display_payload(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        return {}

    source_tag = _entry_source_tag(dict(entry)) or str(entry.get("source") or "").strip()
    match_kind = str(entry.get("_match_kind") or "headword").strip().lower() or "headword"
    runtime_entry_id = _runtime_entry_id(entry)
    ref_key = _hydrated_ref_key(entry)
    source_entry_id = str(entry.get("entry_id") or "").strip()
    lemma_headword = str(entry.get("headword") or "").strip()
    entry_reading = _entry_reading(dict(entry))
    display_headword = str(entry.get("display_headword") or "").strip() or lemma_headword
    display_reading = entry_reading
    raw_morph_info = entry.get("morph_info")
    morph_info = (
        raw_morph_info
        if isinstance(raw_morph_info, list)
        else ([raw_morph_info] if raw_morph_info else [])
    )
    morph_info = [str(item or "").strip() for item in morph_info if str(item or "").strip()]
    morph_base = str(entry.get("morph_base") or "").strip()
    is_alternate_match = False
    matched_form: dict[str, Any] = {}

    if match_kind == "form":
        matched_form = _select_triggering_matched_form(entry)
        form_text = str(
            matched_form.get("display_text") or matched_form.get("form_text") or ""
        ).strip()
        form_reading = str(matched_form.get("form_roman") or "").strip()
        raw_tags = str(matched_form.get("tags") or "").strip()
        display_reading = form_reading
        if form_text:
            display_headword = form_text
        if raw_tags and not morph_info:
            morph_info = [raw_tags]
        if lemma_headword and not morph_base:
            morph_base = lemma_headword
        is_alternate_match = _has_alt_bucket_tag(raw_tags)
    elif source_tag == "gemini":
        commentary = str(entry.get("commentary") or entry.get("_commentary") or "").strip()
        lemma = str(entry.get("lemma") or entry.get("_lemma") or "").strip()
        if commentary and not morph_info:
            morph_info = [commentary]
        if lemma and not morph_base:
            morph_base = lemma

    senses_full = _canonical_entry_senses(entry)
    senses = _flatten_structured_senses(senses_full)
    pos = str(entry.get("pos") or "").strip()
    pos_raw = str(entry.get("pos_raw") or pos or "").strip()
    forms = _strict_entry_forms(entry)

    out: dict[str, Any] = {
        "runtime_entry_id": runtime_entry_id,
        "ref_key": ref_key,
        "match_kind": match_kind,
        "_match_kind": match_kind,
        "_match_source": match_kind,
        "display_headword": display_headword,
        "lemma_headword": lemma_headword,
        "display_reading": display_reading,
        "entry_reading": entry_reading,
        "headword": display_headword,
        "surface_form": display_headword,
        "reading": display_reading,
        "roman": display_reading,
        "source": source_tag,
        "_source": source_tag,
        "senses": senses,
        "senses_full": senses_full,
        "is_alternate_match": bool(is_alternate_match),
    }
    if source_entry_id:
        out["entry_id"] = source_entry_id
        out["_source_entry_id"] = source_entry_id
    if pos:
        out["pos"] = pos
    if pos_raw:
        out["pos_raw"] = pos_raw
    if forms:
        out["forms"] = forms
    commentary = str(entry.get("commentary") or "").strip()
    if commentary:
        out["commentary"] = commentary
        out["_commentary"] = commentary
    lemma = str(entry.get("lemma") or "").strip()
    if lemma:
        out["lemma"] = lemma
        out["_lemma"] = lemma
    if morph_info:
        out["morph_info"] = morph_info
    if morph_base:
        out["morph_base"] = morph_base
    grammar = str(entry.get("grammar") or "").strip()
    if grammar:
        out["grammar"] = grammar

    passthrough_keys = (
        "etymology",
        "etymology_number",
        "synonyms",
        "antonyms",
        "derived",
        "related",
        "note",
        "decomp",
    )
    for key in passthrough_keys:
        value = entry.get(key)
        if value:
            out[key] = copy.deepcopy(value)

    for key in (
        "_storage_kind",
        "_storage_db_alias",
        "_storage_row_id",
        "_storage_form_row_id",
    ):
        value = entry.get(key)
        if value:
            out[key] = value

    if matched_form:
        out["matched_form"] = matched_form
        out["_matched_forms"] = [copy.deepcopy(matched_form)]
    return out


def _build_shared_base_payload(
    entry: Mapping[str, Any], match_key: str, lang_code: str
) -> dict[str, Any]:
    """Build the canonical shared payload for entry_store.

    The shared base payload must stay headword-shaped even when the same entry
    also has one or more matched form refs in this hydrate batch. Per-form
    display state belongs in form_overlays only.
    """
    base_entry = dict(entry or {})
    base_entry["_match_kind"] = "headword"
    if match_key:
        base_entry["_match_key"] = match_key
    else:
        base_entry.pop("_match_key", None)
    base_entry.pop("_form_match_key", None)
    base_entry.pop("matched_form", None)
    base_entry.pop("_storage_form_row_id", None)
    base_entry["_matched_forms"] = []
    _shape_korean_synthetic_stem_entry(base_entry, match_key, lang_code)
    payload = _build_hydrated_display_payload(base_entry)
    if payload:
        payload["match_kind"] = "headword"
        payload["_match_kind"] = "headword"
        payload["_match_source"] = "headword"
    return payload


def _extract_form_overlay(entry: Mapping[str, Any], matched_form: dict[str, Any]) -> dict[str, Any]:
    """Extract lightweight form-specific display fields for a matched form.

    Returns only the fields that differ per form_row_id, not the full entry.
    """
    overlay: dict[str, Any] = {}
    form_text = str(matched_form.get("display_text") or matched_form.get("form_text") or "").strip()
    form_reading = str(matched_form.get("form_roman") or "").strip()
    raw_tags = str(matched_form.get("tags") or "").strip()
    lemma_hw = str(entry.get("headword") or "").strip()
    if form_text:
        overlay["display_headword"] = form_text
    overlay["display_reading"] = form_reading
    if raw_tags:
        overlay["morph_info"] = [raw_tags]
    if lemma_hw:
        overlay["morph_base"] = lemma_hw
    overlay["match_kind"] = "form"
    overlay["_match_kind"] = "form"
    overlay["_match_source"] = "form"
    overlay["is_alternate_match"] = _has_alt_bucket_tag(raw_tags)
    overlay["matched_form"] = copy.deepcopy(matched_form)
    form_row_id = int(matched_form.get("_form_row_id") or 0)
    if form_row_id:
        overlay["_storage_form_row_id"] = form_row_id
    return overlay


def _shape_korean_synthetic_stem_entry(
    entry: dict[str, Any], match_key: str, lang_code: str
) -> None:
    if not isinstance(entry, dict):
        return
    lang = str(lang_code or "").strip().lower()
    if not (lang == "ko" or lang == "korean" or lang.startswith("ko-")):
        return
    if str(entry.get("_match_kind") or "").strip().lower() != "headword":
        return
    headword = str(entry.get("headword") or "").strip()
    pos = str(entry.get("pos") or "").strip().lower()
    if pos not in {"verb", "adj"}:
        return
    if not headword.endswith("다") or len(headword) <= 1:
        return
    stem_text = headword[:-1].strip()
    if not stem_text:
        return
    key = str(match_key or "").strip()
    if not key or key != stem_text:
        return
    entry["display_headword"] = stem_text
    entry["morph_info"] = ["stem"]
    entry["morph_base"] = headword


def _sqlite_runtime_entry_id(entry: Mapping[str, Any] | None) -> str:
    if not isinstance(entry, Mapping):
        return ""
    storage_kind = str(entry.get("_storage_kind") or "").strip().lower()
    if storage_kind != "sqlite":
        return ""
    db_alias = str(entry.get("_storage_db_alias") or "").strip()
    try:
        row_id = int(entry.get("_storage_row_id") or 0)
    except Exception:
        row_id = 0
    if not db_alias or row_id <= 0:
        return ""
    return f"sqlite|{db_alias}|{row_id}"


def _entry_store_key(entry: Mapping[str, Any] | None) -> str:
    canonical = _canonical_entry_payload(entry)
    sqlite_runtime_id = _sqlite_runtime_entry_id(canonical)
    if sqlite_runtime_id:
        return sqlite_runtime_id
    explicit = str(canonical.get("entry_id") or "").strip()
    if explicit:
        return explicit
    digest = hashlib.sha1(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return f"anon:{digest}"


def _intern_entry(entry_store: dict[str, dict[str, Any]], entry: Mapping[str, Any] | None) -> str:
    canonical = _canonical_entry_payload(entry)
    if not canonical:
        return ""
    key = _entry_store_key(entry)
    canonical["entry_id"] = key
    if key not in entry_store:
        entry_store[key] = canonical
        return key

    existing = entry_store[key]

    matched_forms: list[dict[str, Any]] = []
    for raw in list(existing.get("_matched_forms") or []):
        if isinstance(raw, Mapping):
            matched_forms.append(copy.deepcopy(dict(raw)))
    for raw in list(canonical.get("_matched_forms") or []):
        if not isinstance(raw, Mapping):
            continue
        cloned = copy.deepcopy(dict(raw))
        if cloned not in matched_forms:
            matched_forms.append(cloned)
    if matched_forms:
        existing["_matched_forms"] = matched_forms

    existing_forms = existing.get("forms")
    if isinstance(existing_forms, Mapping):
        merged_forms: dict[str, Any] = copy.deepcopy(dict(existing_forms))
    else:
        merged_forms = {}
    incoming_forms = canonical.get("forms")
    if isinstance(incoming_forms, Mapping):
        incoming_forms = dict(incoming_forms)
        merged_rows = _normalize_entry_form_rows(
            merged_forms.get("rows")
        ) + _normalize_entry_form_rows(incoming_forms.get("rows"))
        if matched_forms:
            merged_rows += _normalize_entry_form_rows(matched_forms)
        if merged_rows:
            seen_rows: set[tuple[str, str, str]] = set()
            deduped_rows: list[list[str]] = []
            for row in merged_rows:
                row_key = tuple(row)
                if row_key in seen_rows:
                    continue
                seen_rows.add(row_key)
                deduped_rows.append(row)
            merged_forms["rows"] = deduped_rows
        for form_key in ("kanji", "readings", "alt", "hanja", "hangeul", "cjk"):
            values = _list_text_values(merged_forms.get(form_key)) + _list_text_values(
                incoming_forms.get(form_key)
            )
            if values:
                deduped_values: list[str] = []
                seen_values: set[str] = set()
                for value in values:
                    if value in seen_values:
                        continue
                    seen_values.add(value)
                    deduped_values.append(value)
                merged_forms[form_key] = deduped_values
    elif matched_forms:
        merged_rows = _normalize_entry_form_rows(matched_forms)
        if merged_rows:
            merged_forms["rows"] = merged_rows
    if merged_forms:
        existing["forms"] = merged_forms

    merged_morph = _list_text_values(existing.get("morph_info")) + _list_text_values(
        canonical.get("morph_info")
    )
    if matched_forms:
        merged_morph += [
            str(mf.get("tags") or "").strip() for mf in matched_forms if isinstance(mf, Mapping)
        ]
    if merged_morph:
        deduped_morph: list[str] = []
        seen_morph: set[str] = set()
        for morph in merged_morph:
            if not morph or morph in seen_morph:
                continue
            seen_morph.add(morph)
            deduped_morph.append(morph)
        if deduped_morph:
            existing["morph_info"] = deduped_morph

    if not existing.get("morph_base") and canonical.get("morph_base"):
        existing["morph_base"] = canonical["morph_base"]
    if not existing.get("_storage_kind") and canonical.get("_storage_kind"):
        existing["_storage_kind"] = canonical["_storage_kind"]
    if not existing.get("_storage_db_alias") and canonical.get("_storage_db_alias"):
        existing["_storage_db_alias"] = canonical["_storage_db_alias"]
    if not existing.get("_storage_row_id") and canonical.get("_storage_row_id"):
        existing["_storage_row_id"] = canonical["_storage_row_id"]
    if not existing.get("_source_entry_id") and canonical.get("_source_entry_id"):
        existing["_source_entry_id"] = canonical["_source_entry_id"]
    if not existing.get("_match_kind") and canonical.get("_match_kind"):
        existing["_match_kind"] = canonical["_match_kind"]
    if not existing.get("_form_match_key") and canonical.get("_form_match_key"):
        existing["_form_match_key"] = canonical["_form_match_key"]
    return key


def _collect_interned_entry_ids(
    entry_store: dict[str, dict[str, Any]],
    entries: Sequence[Mapping[str, Any]] | None,
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for entry in entries or []:
        key = _intern_entry(entry_store, entry)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _build_resolution_payload(
    category: str,
    resolved_via: str,
    fill_mode: str,
    lemma_oracle_used: bool,
    lemma_oracle_outcome: str,
    fills: Sequence[dict[str, Any]] | None,
    exact_lemma_match_count: int,
    partial_gap_count: int = 0,
    partial_exact_lemma_count: int = 0,
    partial_missing_lemma_count: int = 0,
) -> dict[str, Any]:
    meta = _build_resolution_actual(
        category,
        resolved_via,
        fill_mode,
        lemma_oracle_used,
        lemma_oracle_outcome,
        fills,
        exact_lemma_match_count,
        partial_gap_count=partial_gap_count,
        partial_exact_lemma_count=partial_exact_lemma_count,
        partial_missing_lemma_count=partial_missing_lemma_count,
    )
    out = {
        "category": str(meta.get("category") or ""),
        "compare_kind": str(meta.get("compare_kind") or ""),
        "resolved_via": str(meta.get("resolved_via") or ""),
        "fill_mode": str(meta.get("fill_mode") or ""),
        "lemma_oracle_used": bool(meta.get("lemma_oracle_used")),
        "lemma_oracle_outcome": str(meta.get("lemma_oracle_outcome") or ""),
        "exact_surface_match": bool(meta.get("exact_surface_match")),
        "exact_matches_lemma": bool(meta.get("exact_matches_lemma")),
        "exact_lemma_match_count": int(meta.get("exact_lemma_match_count") or 0),
        "has_lemma_linked_fill": bool(meta.get("has_lemma_linked_fill")),
    }
    if partial_exact_lemma_count > 0:
        out["partial_exact_lemma_count"] = int(partial_exact_lemma_count)
    if partial_missing_lemma_count > 0:
        out["partial_missing_lemma_count"] = int(partial_missing_lemma_count)
    if partial_gap_count > 0:
        out["partial_gap_count"] = int(partial_gap_count)
    return out


def _build_canonical_fills(
    fills: Sequence[dict[str, Any]] | None,
    surface_text: str,
    resolved_via: str,
    entry_store: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    annotated = _annotate_fill_resolution_links(fills, resolved_via)
    slices = _build_fill_surface_slices(surface_text, annotated)
    slice_by_index: dict[int, tuple[int, int]] = {}
    for item in slices:
        try:
            start = int(item.get("start"))
            end = int(item.get("end"))
        except Exception:
            continue
        for raw_idx in list(item.get("fill_indexes") or []):
            try:
                fill_idx = int(raw_idx)
            except Exception:
                continue
            slice_by_index[fill_idx] = (start, end)

    out: list[dict[str, Any]] = []
    for idx, row in enumerate(annotated):
        raw_entries = _dedupe_entry_list(list(row.get("entries") or []))
        entry_ids = _collect_interned_entry_ids(entry_store, raw_entries)
        if not entry_ids:
            continue

        start = row.get("_surface_start")
        end = row.get("_surface_end")
        try:
            start_i = int(start)
            end_i = int(end)
        except Exception:
            start_i, end_i = slice_by_index.get(idx, (0, 0))
        if len(annotated) == 1 and (end_i <= start_i or end_i > len(surface_text)):
            start_i, end_i = 0, len(surface_text)

        fill_payload: dict[str, Any] = {
            "entry_ids": entry_ids,
            "start": max(0, start_i),
            "end": min(len(surface_text), end_i if end_i > start_i else len(surface_text)),
        }

        hint_fields = (
            ("_lemma_part_index", "lemma_part_index"),
            ("_lemma_upos_hint", "lemma_upos_hint"),
            ("_lemma_xpos_hint", "lemma_xpos_hint"),
            ("_xpos_hint", "xpos_hint"),
            ("_lemma_promoted", "lemma_promoted"),
            ("_lemma_override", "lemma_override"),
        )
        for raw_key, out_key in hint_fields:
            value = row.get(raw_key)
            if value not in (None, "", []):
                fill_payload[out_key] = copy.deepcopy(value)
        if row.get("resolution_linked_to_lemma"):
            fill_payload["resolution_linked_to_lemma"] = True
        resolution_source = str(row.get("resolution_source") or "").strip()
        if resolution_source:
            fill_payload["resolution_source"] = resolution_source
        out.append(fill_payload)
    return out, annotated


def _trim_grammar_overlay(grammar_overlay: Mapping[str, Any] | None) -> dict[str, Any]:
    overlay = grammar_overlay or {}
    return {"tokens": copy.deepcopy(list(overlay.get("tokens") or []))}


def _trim_ud_overlay(ud_overlay: Mapping[str, Any] | None) -> dict[str, Any]:
    overlay = ud_overlay or {}
    tokens: list[dict[str, Any]] = []
    allowed_token_keys = (
        "i",
        "doc_i",
        "head",
        "heads",
        "dep",
        "lemma",
        "lemma_raw",
        "lemma_suffix",
        "tag",
        "upos",
        "feats",
        "text",
        "seg_span",
        "mwt_parts",
    )
    for raw in list(overlay.get("tokens") or []):
        if not isinstance(raw, Mapping):
            continue
        token: dict[str, Any] = {}
        for key in allowed_token_keys:
            if key in raw:
                token[key] = copy.deepcopy(raw.get(key))
        tokens.append(token)
    return {
        "ok": bool(overlay.get("ok")),
        "tokens": tokens,
        "edges": copy.deepcopy(list(overlay.get("edges") or [])),
        "ents": copy.deepcopy(list(overlay.get("ents") or [])),
        "roots": copy.deepcopy(list(overlay.get("roots") or [])),
        "sentences": copy.deepcopy(list(overlay.get("sentences") or [])),
    }


def _build_lookup_payload_base(lookup_data: Mapping[str, Any] | None) -> dict[str, Any]:
    data = lookup_data or {}
    display_text = str(data.get("display_text") or data.get("q") or "")
    return {
        "ok": bool(data.get("ok", True)),
        "display_text": display_text,
        "segments": copy.deepcopy(list(data.get("segments") or [])),
        "segment_offsets": copy.deepcopy(list(data.get("segment_offsets") or [])),
        "grammar_overlay": _trim_grammar_overlay(data.get("grammar_overlay") or {}),
        "ud_overlay": _trim_ud_overlay(data.get("ud_overlay") or {}),
    }


def _client_accepts_gzip() -> bool:
    return "gzip" in str(request.headers.get("Accept-Encoding") or "").lower()


def _lookup_json_response(
    payload: Mapping[str, Any] | Sequence[Any],
    status: int = 200,
    extra_headers: Mapping[str, Any] | None = None,
) -> Response:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8", "Vary": "Accept-Encoding"}
    if isinstance(payload, Mapping):
        trace = payload.get("sqlite_debug_trace")
        if isinstance(trace, Mapping):
            try:
                total_ms = float(trace.get("total_ms") or 0.0)
            except Exception:
                total_ms = 0.0
            if total_ms > 0.0:
                headers["X-Debug-Server-Ms"] = f"{total_ms:.3f}"
            request_kind = str(trace.get("request_kind") or "").strip()
            if request_kind:
                headers["X-Debug-Request-Kind"] = request_kind
    if isinstance(extra_headers, Mapping):
        for key, value in extra_headers.items():
            if value is None:
                continue
            headers[str(key)] = str(value)
    if len(body) >= 512 and _client_accepts_gzip():
        body = _response_gzip.compress(body, compresslevel=6)
        headers["Content-Encoding"] = "gzip"
    return Response(body, status=status, headers=headers)


def _annotate_fill_resolution_links(
    fills: Sequence[dict[str, Any]] | None, resolved_via: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    path = str(resolved_via or "").strip().lower()
    whole_lemma_path = path in {"lemma", "lemma_override"}
    for raw in fills or []:
        row = dict(raw)
        linked = bool(
            row.get("_lemma_promoted")
            or row.get("lemma_promoted")
            or row.get("_lemma_override")
            or row.get("lemma_override")
        )
        if not linked and whole_lemma_path and str(row.get("source") or "").upper() != "UNKNOWN":
            linked = True
        row["resolution_linked_to_lemma"] = linked
        if linked:
            if path == "lemma_override" or row.get("_lemma_override") or row.get("lemma_override"):
                row["resolution_source"] = "lemma_override"
            elif whole_lemma_path and not (row.get("_lemma_promoted") or row.get("lemma_promoted")):
                row["resolution_source"] = "lemma"
            else:
                row["resolution_source"] = "lemma_promoted"
        else:
            row["resolution_source"] = "surface"
        rows.append(row)
    return rows


def _build_resolution_route_steps(
    category: str, lemma_oracle_used: bool, partial_gap_count: int = 0
) -> tuple[str, list[dict[str, str]]]:
    category_key = str(category or "").strip().lower()
    if category_key == "exact_lemma_match":
        return "surface_exact_lemma_match", [
            {"code": "surface_exact_lookup", "text": "surface exact lookup matched", "detail": ""},
            {
                "code": "lemma_check",
                "text": "lemma check found an underlying lemma match",
                "detail": "",
            },
        ]
    if category_key == "exact_match":
        steps = [
            {"code": "surface_exact_lookup", "text": "surface exact lookup matched", "detail": ""}
        ]
        if lemma_oracle_used:
            steps.append(
                {
                    "code": "lemma_check",
                    "text": "lemma check kept the surface exact result",
                    "detail": "",
                }
            )
            return "surface_exact_lemma_checked", steps
        return "surface_exact", steps
    if category_key == "lemma_partial_override":
        return "surface_no_match_then_partial_lemma_exact_then_gap_greedy", [
            {"code": "surface_exact_lookup", "text": "surface exact lookup missed", "detail": ""},
            {
                "code": "lemma_exact_parts",
                "text": "exact lemma parts were aligned onto the surface",
                "detail": "",
            },
            {
                "code": "lemma_gap_greedy",
                "text": "greedy DP filled the remaining uncovered spans"
                if partial_gap_count > 0
                else "no uncovered spans remained after exact lemma-part alignment",
                "detail": "",
            },
        ]
    if category_key == "lemma_override":
        return "surface_no_match_then_lemma_exact_parts", [
            {"code": "surface_exact_lookup", "text": "surface exact lookup missed", "detail": ""},
            {
                "code": "lemma_exact_parts",
                "text": "all lemma parts resolved by exact lookup",
                "detail": "",
            },
            {"code": "lemma_override", "text": "lemma exact-part alignment selected", "detail": ""},
        ]
    if category_key == "greedy_lemma_match":
        return "surface_greedy_lemma_match", [
            {"code": "surface_exact_lookup", "text": "surface exact lookup missed", "detail": ""},
            {
                "code": "lemma_greedy",
                "text": "lemma-aware greedy DP selected lemma-linked pieces",
                "detail": "",
            },
        ]
    if category_key == "greedy_segmentation":
        return "surface_greedy", [
            {"code": "surface_exact_lookup", "text": "surface exact lookup missed", "detail": ""},
            {
                "code": "lemma_greedy" if lemma_oracle_used else "surface_greedy",
                "text": "lemma-aware greedy DP selected a surface path"
                if lemma_oracle_used
                else "surface greedy DP selected the final path",
                "detail": "",
            },
        ]
    if lemma_oracle_used:
        return "surface_no_match_after_lemma_check", [
            {"code": "surface_exact_lookup", "text": "surface exact lookup missed", "detail": ""},
            {
                "code": "lemma_greedy",
                "text": "lemma-aware greedy DP found no known dictionary path",
                "detail": "",
            },
        ]
    return "surface_no_match", [
        {"code": "surface_exact_lookup", "text": "surface exact lookup missed", "detail": ""},
        {
            "code": "surface_greedy",
            "text": "surface greedy DP found no known dictionary path",
            "detail": "",
        },
    ]


def _build_resolution_route_text(route_steps: Sequence[Mapping[str, Any]] | None) -> str:
    out: list[str] = []
    for step in route_steps or []:
        text = str(step.get("text") or "").strip()
        detail = str(step.get("detail") or "").strip()
        if not text:
            continue
        out.append(f"{text} ({detail})" if detail else text)
    return " -> ".join(out)


def _build_resolution_actual(
    category: str,
    resolved_via: str,
    fill_mode: str,
    lemma_oracle_used: bool,
    lemma_oracle_outcome: str,
    fills: Sequence[dict[str, Any]] | None,
    exact_lemma_match_count: int,
    partial_gap_count: int = 0,
    partial_exact_lemma_count: int = 0,
    partial_missing_lemma_count: int = 0,
) -> dict[str, Any]:
    rows = list(fills or [])
    known_piece_count = 0
    unknown_piece_count = 0
    lemma_linked_fill_indexes: list[int] = []
    lemma_linked_keys: set[str] = set()
    for idx, row in enumerate(rows):
        if str(row.get("source") or "").upper() == "UNKNOWN":
            unknown_piece_count += 1
        else:
            known_piece_count += 1
        if row.get("resolution_linked_to_lemma"):
            lemma_linked_fill_indexes.append(idx)
            lemma_key = str(
                row.get("_lemma_override")
                or row.get("_lemma_promoted")
                or row.get("lemma_form")
                or row.get("morph_base")
                or ""
            ).strip()
            if lemma_key:
                lemma_linked_keys.add(lemma_key)
    final_text = ""
    if known_piece_count > 0:
        parts = [
            f"via={str(resolved_via or '').strip().lower()}",
            f"mode={str(fill_mode or '').strip().lower()}",
            f"pieces={len(rows)}",
            f"known={known_piece_count}",
        ]
        if unknown_piece_count > 0:
            parts.append(f"unknown={unknown_piece_count}")
        if lemma_linked_fill_indexes:
            parts.append(f"lemma-linked={len(lemma_linked_fill_indexes)}")
        if exact_lemma_match_count > 0:
            parts.append(f"lemma-exact={exact_lemma_match_count}")
        final_text = " | ".join(parts)
    category_key = str(category or "").strip().lower()
    route_code, route_steps = _build_resolution_route_steps(
        category_key, bool(lemma_oracle_used), int(partial_gap_count or 0)
    )
    out = {
        "category": category_key,
        "label": _ACTUAL_RESOLUTION_LABELS.get(category_key, "") if category_key else "",
        "route_code": route_code,
        "route_steps": route_steps,
        "route_text": _build_resolution_route_text(route_steps),
        "final_text": final_text,
        "compare_kind": "surface"
        if category_key
        in {"exact_lemma_match", "greedy_lemma_match", "lemma_override", "lemma_partial_override"}
        else ("lemma" if lemma_oracle_used else ""),
        "resolved_via": str(resolved_via or "").strip().lower(),
        "fill_mode": str(fill_mode or "").strip().lower(),
        "lemma_oracle_used": bool(lemma_oracle_used),
        "lemma_oracle_outcome": str(lemma_oracle_outcome or "").strip().lower(),
        "exact_surface_match": category_key in {"exact_match", "exact_lemma_match"},
        "exact_matches_lemma": category_key == "exact_lemma_match",
        "exact_lemma_match_count": int(exact_lemma_match_count or 0),
        "has_lemma_linked_fill": bool(lemma_linked_fill_indexes),
        "lemma_linked_fill_indexes": lemma_linked_fill_indexes,
        "lemma_linked_distinct_count": len(lemma_linked_keys),
        "final_result": {
            "total_piece_count": len(rows),
            "known_piece_count": known_piece_count,
            "unknown_piece_count": unknown_piece_count,
            "lemma_linked_piece_count": len(lemma_linked_fill_indexes),
        },
    }
    if partial_exact_lemma_count > 0:
        out["partial_exact_lemma_count"] = int(partial_exact_lemma_count)
    if partial_missing_lemma_count > 0:
        out["partial_missing_lemma_count"] = int(partial_missing_lemma_count)
    if partial_gap_count > 0:
        out["partial_gap_count"] = int(partial_gap_count)
    return out


def _infer_resolution_category(
    surface_lookup: dict[str, Any],
    fill: dict[str, Any] | None,
    all_entries: Sequence[dict[str, Any]] | None,
) -> str:
    resolved_via = str(surface_lookup.get("resolved_via") or "").strip().lower()
    exact_lemma_match_count = int(surface_lookup.get("exact_lemma_match_count") or 0)
    fill_mode = str((fill or {}).get("mode") or "").strip().lower()
    if surface_lookup.get("exact_entries"):
        if exact_lemma_match_count > 0:
            return "exact_lemma_match"
        return "exact_match"
    if resolved_via in {"lemma", "lemma_override"}:
        return "lemma_override"
    if resolved_via == "lemma_partial_override":
        return "lemma_partial_override"
    if fill and fill.get("has_lemma_promotion"):
        return "greedy_lemma_match"
    if all_entries:
        return "greedy_segmentation"
    return ""


def _prepare_fill_entries(
    fills: Sequence[dict[str, Any]] | None,
    surface_text: str,
    segmenter: Any,
    lang_code: str,
    upos: str,
    xpos: str,
    fill_mode: str,
    resolved_via: str,
    debug_trace: bool = False,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    known_fill_count = sum(
        1 for raw in list(fills or []) if str((raw or {}).get("source") or "").upper() != "UNKNOWN"
    )
    greedy_multi_fill = (
        str(fill_mode or "").strip().lower() in _GREEDY_FILTER_MODES and known_fill_count > 1
    )
    for raw in fills or []:
        row = dict(raw)
        effective_upos = _fill_effective_upos(row, upos)
        effective_xpos = _fill_effective_xpos(row, xpos)
        fill_entries = _decorate_entries_with_nlp(
            row.get("entries") or [], effective_upos, effective_xpos
        )
        lookup_head = str(row.get("head") or row.get("text") or surface_text or "")
        shown_entries, hidden_entries = _split_entries_for_display(
            fill_entries,
            lang_code=lang_code,
            upos=effective_upos,
            fill_mode=fill_mode,
            greedy_multi_fill=greedy_multi_fill,
        )
        row["senses_all"] = (
            _merge_all_entries(lookup_head, fill_entries)
            if fill_entries
            else list(row.get("senses") or [])
        )
        row["senses"] = (
            _merge_all_entries(lookup_head, shown_entries)
            if shown_entries
            else list(row["senses_all"])
        )
        row["senses_hover"] = list(row["senses"])
        row["senses_hover_other"] = (
            _merge_all_entries(lookup_head, hidden_entries) if hidden_entries else []
        )
        row["hover_has_alt_senses"] = bool(row["senses_hover_other"])
        row["entry_groups_all"] = (
            _build_entry_groups(fill_entries, lookup_head) if fill_entries else []
        )
        row["entry_groups"] = (
            _build_entry_groups(shown_entries or fill_entries, lookup_head)
            if (shown_entries or fill_entries)
            else []
        )
        if hidden_entries:
            row["entry_groups_hover"] = (
                _build_entry_groups(shown_entries, lookup_head) if shown_entries else []
            )
            row["entry_groups_other"] = _build_entry_groups(hidden_entries, lookup_head)
        row["entries"] = shown_entries or fill_entries
        row["all_entries"] = fill_entries
        chosen = (
            segmenter._choose_entry(lookup_head, shown_entries or fill_entries)
            if fill_entries
            else None
        )
        if chosen and not row.get("roman"):
            row["roman"] = _entry_reading(chosen)
        if shown_entries or fill_entries:
            src_tag = _entry_source_tag((shown_entries or fill_entries)[0])
            if src_tag:
                row["_dict_source"] = src_tag
        row["upos"] = effective_upos
        row["xpos"] = effective_xpos
        row["tag"] = effective_xpos
        if effective_upos:
            row["upos_label"] = effective_upos
            row["upos_color"] = _LOOKUP_UPOS_COLORS.get(effective_upos, "#d1d5db")
        if debug_trace:
            record_decoration_event(
                "fill_row",
                {
                    "surface_text": str(surface_text or ""),
                    "fill_mode": str(fill_mode or ""),
                    "resolved_via": str(resolved_via or ""),
                    "text": str(row.get("text") or ""),
                    "head": str(row.get("head") or ""),
                    "lemma_upos_hint": str(row.get("_lemma_upos_hint") or ""),
                    "lemma_xpos_hint": str(row.get("_lemma_xpos_hint") or ""),
                    "xpos_hint": str(row.get("_xpos_hint") or ""),
                    "effective_upos": effective_upos,
                    "effective_xpos": effective_xpos,
                    "entry_count": len(fill_entries),
                    "shown_entry_count": len(shown_entries or fill_entries),
                    "other_entry_count": len(hidden_entries),
                    "entries": [
                        {
                            "headword": str(ent.get("headword") or ent.get("surface_form") or ""),
                            "pos_raw": str(ent.get("pos_raw") or ent.get("pos") or ""),
                            "upos": str(ent.get("upos") or ""),
                            "xpos": str(ent.get("xpos") or ent.get("tag") or ""),
                            "tag": str(ent.get("tag") or ent.get("xpos") or ""),
                        }
                        for ent in fill_entries[:20]
                        if isinstance(ent, dict)
                    ],
                },
            )
        out.append(row)
    return _annotate_fill_resolution_links(out, resolved_via)


def _build_unknown_result(
    word: str,
    upos: str,
    xpos: str,
    deprel: str,
    lemma: str,
    feats: str,
    idx: int,
    lemma_raw: str,
    lemma_suffix: str,
) -> dict[str, Any]:
    entry = {
        "seg_i": idx,
        "surface_form": word,
        "upos": upos,
        "tag": xpos,
        "dep": deprel,
        "feats": feats or "",
        "fills": [],
        "resolution": {
            "category": "",
            "compare_kind": "",
            "resolved_via": "surface",
            "fill_mode": "greedy",
            "lemma_oracle_used": False,
            "lemma_oracle_outcome": "",
            "exact_surface_match": False,
            "exact_matches_lemma": False,
            "exact_lemma_match_count": 0,
            "has_lemma_linked_fill": False,
        },
    }
    if lemma:
        entry["lemma"] = lemma
    if lemma_raw:
        entry["lemma_raw"] = lemma_raw
    if lemma_suffix:
        entry["lemma_suffix"] = lemma_suffix
    return entry


def _extract_token_map(lookup_data: dict[str, Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    ud_overlay = lookup_data.get("ud_overlay") or {}
    for raw in list(ud_overlay.get("tokens") or []):
        try:
            idx = int(raw.get("i"))
        except Exception:
            continue
        if idx < 0:
            continue
        out[idx] = raw
    return out


def _build_segment_result(
    word: str,
    token: dict[str, Any],
    seg_idx: int,
    segmenter: Any,
    lang_code: str,
    entry_store: dict[str, dict[str, Any]],
    debug_trace: bool = False,
) -> dict[str, Any]:
    upos = str(token.get("upos") or "X")
    deprel = str(token.get("dep") or "dep")
    xpos = str(token.get("tag") or "")
    lemma = str(token.get("lemma") or "")
    lemma_raw = str(token.get("lemma_raw") or lemma or "")
    lemma_suffix = str(token.get("lemma_suffix") or "")
    feats = str(token.get("feats") or "")

    if segmenter is None:
        return _build_unknown_result(
            word, upos, xpos, deprel, lemma, feats, seg_idx, lemma_raw, lemma_suffix
        )

    if debug_trace:
        with trace_scope(
            "segment_result",
            label="Segment Result",
            token=word,
            seg_i=seg_idx,
            upos=upos,
            xpos=xpos,
            lemma=lemma,
        ):
            surface_lookup = segmenter.build_surface_lemma_aware_lookup(
                word, lemma, upos=upos, xpos=xpos, debug=debug_trace
            )
            fill = surface_lookup.get("fill") or {}
            all_entries = list(surface_lookup.get("all_entries") or [])
            preferred_entries = list(surface_lookup.get("preferred_entries") or all_entries)
            output_all_entries = _decorate_entries_with_nlp(all_entries, upos, xpos)
            output_preferred_entries = _decorate_entries_with_nlp(preferred_entries, upos, xpos)
            dict_head = str(surface_lookup.get("dict_head") or word)
            resolved_via = str(surface_lookup.get("resolved_via") or "surface")
            lemma_oracle_used = bool(surface_lookup.get("lemma_oracle_used"))
            lemma_oracle_outcome = str(surface_lookup.get("lemma_oracle_outcome") or "")
            fill_mode = str(fill.get("mode") or "greedy")
            exact_lemma_match_count = int(surface_lookup.get("exact_lemma_match_count") or 0)
            partial_exact_lemma_count = int(surface_lookup.get("partial_exact_lemma_count") or 0)
            partial_missing_lemma_count = int(
                surface_lookup.get("partial_missing_lemma_count") or 0
            )
            partial_gap_count = int(surface_lookup.get("partial_gap_count") or 0)
            lemma_override_parts = list(surface_lookup.get("lemma_override_parts") or [])
            shown_entries, other_entries = _split_entries_for_display(
                output_all_entries,
                lang_code=lang_code,
                upos=upos,
                fill_mode=fill_mode,
                preferred_entries=output_preferred_entries,
            )
            chosen_main = segmenter._choose_entry(
                dict_head, shown_entries or output_preferred_entries or output_all_entries
            )
    else:
        surface_lookup = segmenter.build_surface_lemma_aware_lookup(
            word, lemma, upos=upos, xpos=xpos, debug=False
        )
        fill = surface_lookup.get("fill") or {}
        all_entries = list(surface_lookup.get("all_entries") or [])
        preferred_entries = list(surface_lookup.get("preferred_entries") or all_entries)
        output_all_entries = _decorate_entries_with_nlp(all_entries, upos, xpos)
        output_preferred_entries = _decorate_entries_with_nlp(preferred_entries, upos, xpos)
        dict_head = str(surface_lookup.get("dict_head") or word)
        resolved_via = str(surface_lookup.get("resolved_via") or "surface")
        lemma_oracle_used = bool(surface_lookup.get("lemma_oracle_used"))
        lemma_oracle_outcome = str(surface_lookup.get("lemma_oracle_outcome") or "")
        fill_mode = str(fill.get("mode") or "greedy")
        exact_lemma_match_count = int(surface_lookup.get("exact_lemma_match_count") or 0)
        partial_exact_lemma_count = int(surface_lookup.get("partial_exact_lemma_count") or 0)
        partial_missing_lemma_count = int(surface_lookup.get("partial_missing_lemma_count") or 0)
        partial_gap_count = int(surface_lookup.get("partial_gap_count") or 0)
        lemma_override_parts = list(surface_lookup.get("lemma_override_parts") or [])
        shown_entries, other_entries = _split_entries_for_display(
            output_all_entries,
            lang_code=lang_code,
            upos=upos,
            fill_mode=fill_mode,
            preferred_entries=output_preferred_entries,
        )
        chosen_main = segmenter._choose_entry(
            dict_head, shown_entries or output_preferred_entries or output_all_entries
        )

    entry: dict[str, Any] = {
        "seg_i": seg_idx,
        "surface_form": word,
        "upos": upos,
        "tag": xpos,
        "dep": deprel,
        "feats": feats,
        "fills": [],
    }
    if lemma:
        entry["lemma"] = lemma
    if lemma_raw:
        entry["lemma_raw"] = lemma_raw
    if lemma_suffix:
        entry["lemma_suffix"] = lemma_suffix
    if token.get("g2p") is not None:
        entry["g2p"] = copy.deepcopy(token.get("g2p"))

    if chosen_main:
        primary_entry = _canonical_entry_payload(chosen_main)
        display_head = str(
            primary_entry.get("surface_form") or primary_entry.get("headword") or dict_head or word
        ).strip()
        if display_head:
            entry["head"] = display_head
        headword = str(primary_entry.get("headword") or "").strip()
        if headword:
            entry["headword"] = headword
        reading = str(primary_entry.get("reading") or "").strip()
        if reading:
            entry["reading"] = reading
        dict_pos = str(primary_entry.get("pos") or "").strip()
        if dict_pos:
            entry["pos"] = dict_pos
        dict_pos_raw = str(primary_entry.get("pos_raw") or "").strip()
        if dict_pos_raw:
            entry["pos_raw"] = dict_pos_raw
        source_tag = str(primary_entry.get("source") or "").strip()
        if source_tag:
            entry["source"] = source_tag
        structured_senses = copy.deepcopy(list(primary_entry.get("senses") or []))
        if structured_senses:
            entry["senses_full"] = structured_senses
            entry["senses"] = _flatten_structured_senses(structured_senses)
        for copy_key in ("forms", "forms_meta", "morph_base", "morph_info", "grammar"):
            if primary_entry.get(copy_key) not in (None, "", [], {}):
                entry[copy_key] = copy.deepcopy(primary_entry.get(copy_key))

    canonical_fills, resolution_rows = _build_canonical_fills(
        fill.get("fills") or [],
        word,
        resolved_via,
        entry_store,
    )
    if not canonical_fills and all_entries:
        fallback_entries = shown_entries or output_preferred_entries or output_all_entries
        entry_ids = _collect_interned_entry_ids(entry_store, _dedupe_entry_list(fallback_entries))
        if entry_ids:
            synthetic_fill: dict[str, Any] = {
                "start": 0,
                "end": len(word),
                "entry_ids": entry_ids,
            }
            whole_lemma_path = resolved_via in {"lemma", "lemma_override"}
            if whole_lemma_path:
                synthetic_fill["resolution_linked_to_lemma"] = True
                synthetic_fill["resolution_source"] = (
                    "lemma_override" if resolved_via == "lemma_override" else "lemma"
                )
            canonical_fills = [synthetic_fill]
            resolution_rows = [
                {
                    "text": word,
                    "source": "DICT",
                    "resolution_linked_to_lemma": bool(
                        synthetic_fill.get("resolution_linked_to_lemma")
                    ),
                    "resolution_source": str(synthetic_fill.get("resolution_source") or "surface"),
                }
            ]
    entry["fills"] = canonical_fills
    category = _infer_resolution_category(surface_lookup, fill, all_entries)
    if partial_gap_count > 0:
        entry["partial_gap_count"] = partial_gap_count
    if partial_missing_lemma_count > 0:
        entry["partial_missing_lemma_count"] = partial_missing_lemma_count
    if lemma_override_parts:
        entry["lemma_override_parts"] = lemma_override_parts
    entry["resolution"] = _build_resolution_payload(
        category,
        resolved_via,
        fill_mode,
        lemma_oracle_used,
        lemma_oracle_outcome,
        resolution_rows,
        exact_lemma_match_count,
        partial_gap_count=partial_gap_count,
        partial_exact_lemma_count=partial_exact_lemma_count,
        partial_missing_lemma_count=partial_missing_lemma_count,
    )
    if debug_trace:
        record_decoration_event(
            "segment_result",
            {
                "seg_i": seg_idx,
                "token": word,
                "upos": upos,
                "xpos": xpos,
                "lemma": lemma,
                "resolved_via": resolved_via,
                "fill_mode": fill_mode,
                "entry_count": len(output_all_entries),
                "shown_entry_count": len(shown_entries or output_all_entries),
                "other_entry_count": len(other_entries),
                "entries": [
                    {
                        "headword": str(ent.get("headword") or ent.get("surface_form") or ""),
                        "pos_raw": str(ent.get("pos_raw") or ent.get("pos") or ""),
                        "upos": str(ent.get("upos") or ""),
                        "xpos": str(ent.get("xpos") or ent.get("tag") or ""),
                        "tag": str(ent.get("tag") or ent.get("xpos") or ""),
                    }
                    for ent in output_all_entries[:20]
                    if isinstance(ent, dict)
                ],
                "fill_row_count": len(canonical_fills),
                "lemma_override_parts": copy.deepcopy(lemma_override_parts),
            },
        )

    if debug_trace:
        entry["_debug_lookup_scoring"] = {
            "token": word,
            "lemma_text": lemma,
            "resolved_via": resolved_via,
            "outcome": lemma_oracle_outcome,
            "fill_mode": fill_mode,
            "has_lemma_promotion": bool(fill.get("has_lemma_promotion")),
            "lemma_override_parts": lemma_override_parts,
            "lemma_oracle_used": lemma_oracle_used,
            "lemma_oracle_outcome": lemma_oracle_outcome,
            "partial_exact_lemma_count": partial_exact_lemma_count,
            "partial_missing_lemma_count": partial_missing_lemma_count,
            "partial_gap_count": partial_gap_count,
            "resolution": entry["resolution"],
        }
        if isinstance(fill.get("dp_debug"), dict):
            entry["_debug_greedy_main"] = fill.get("dp_debug")

    return entry


def _build_results_by_seg(
    lookup_data: dict[str, Any],
    lang_code: str,
    selected_sources: Sequence[str] | None,
    debug_trace: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    segments = list(lookup_data.get("segments") or [])
    token_map = _extract_token_map(lookup_data)
    segmenter = _get_sqlite_segmenter(lang_code, selected_sources)
    entry_store: dict[str, dict[str, Any]] = {}
    if debug_trace:
        with trace_scope(
            "build_results_by_seg",
            label="Build Results By Segment",
            language=lang_code,
            segment_count=len(segments),
        ):
            results: list[dict[str, Any]] = []
            for idx, raw_word in enumerate(segments):
                word = str(raw_word or "")
                token = token_map.get(idx) or {}
                results.append(
                    _build_segment_result(
                        word, token, idx, segmenter, lang_code, entry_store, debug_trace=debug_trace
                    )
                )
            return results, entry_store
    results: list[dict[str, Any]] = []
    for idx, raw_word in enumerate(segments):
        word = str(raw_word or "")
        token = token_map.get(idx) or {}
        results.append(
            _build_segment_result(
                word, token, idx, segmenter, lang_code, entry_store, debug_trace=False
            )
        )
    return results, entry_store


def _update_backend_debug_snapshot(
    *,
    capture_id: str,
    lang_code: str,
    query_text: str,
    merged_payload: Mapping[str, Any],
    sqlite_debug_trace: Mapping[str, Any] | None,
) -> None:
    snap = get_debug_snapshot()
    existing_trace = None
    if isinstance(snap, Mapping):
        current_capture_id = str(snap.get("debug_capture_id") or "").strip()
        if current_capture_id and current_capture_id == str(capture_id or "").strip():
            existing_trace = snap.get("sqlite_debug_trace")
    patch: dict[str, Any] = {
        "debug_capture_id": str(capture_id or "").strip(),
        "language": str(lang_code or "").strip().lower(),
        "q": str(query_text or ""),
        "results": copy.deepcopy(list(merged_payload.get("results") or [])),
        "results_by_seg": copy.deepcopy(list(merged_payload.get("results_by_seg") or [])),
        "segments": copy.deepcopy(list(merged_payload.get("segments") or [])),
        "segment_offsets": copy.deepcopy(list(merged_payload.get("segment_offsets") or [])),
        "ud_overlay": copy.deepcopy(merged_payload.get("ud_overlay") or {}),
        "grammar_overlay": copy.deepcopy(merged_payload.get("grammar_overlay") or {}),
    }
    if isinstance(sqlite_debug_trace, Mapping):
        patch["sqlite_debug_trace"] = _merge_debug_trace_payloads(
            existing_trace, sqlite_debug_trace
        )
    update_debug_snapshot(patch)


def _attach_sqlite_debug_trace_to_capture(
    *, capture_id: str, sqlite_debug_trace: Mapping[str, Any] | None
) -> None:
    capture = str(capture_id or "").strip()
    if not capture or not isinstance(sqlite_debug_trace, Mapping):
        return
    snap = get_debug_snapshot()
    if not isinstance(snap, Mapping):
        return
    current_capture_id = str(snap.get("debug_capture_id") or "").strip()
    if not current_capture_id or current_capture_id != capture:
        return
    update_debug_snapshot(
        {
            "sqlite_debug_trace": _merge_debug_trace_payloads(
                snap.get("sqlite_debug_trace"), sqlite_debug_trace
            ),
        }
    )


def _prepare_debug_trace_payload(
    trace_payload: Mapping[str, Any] | None,
    *,
    request_kind: str,
    label: str,
    payload_artifact: Mapping[str, Any] | None = None,
    drop_final_payload: bool = False,
) -> dict[str, Any] | None:
    if not isinstance(trace_payload, Mapping):
        return None
    out = copy.deepcopy(dict(trace_payload))
    if drop_final_payload:
        out.pop("final_payload", None)
    if isinstance(payload_artifact, Mapping):
        out["final_payload_artifact"] = copy.deepcopy(dict(payload_artifact))
    out["request_kind"] = str(request_kind or "").strip()
    root = out.get("timing_tree")
    if isinstance(root, Mapping):
        root_copy = copy.deepcopy(dict(root))
        root_copy["label"] = str(
            label or root_copy.get("label") or root_copy.get("name") or ""
        ).strip()
        meta = root_copy.get("meta")
        meta_copy = copy.deepcopy(dict(meta)) if isinstance(meta, Mapping) else {}
        meta_copy["request_kind"] = str(request_kind or "").strip()
        root_copy["meta"] = meta_copy
        out["timing_tree"] = root_copy
    return out


def _merge_debug_trace_payloads(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(existing, Mapping) and not isinstance(incoming, Mapping):
        return None
    if not isinstance(existing, Mapping):
        return copy.deepcopy(dict(incoming or {}))
    if not isinstance(incoming, Mapping):
        return copy.deepcopy(dict(existing))

    existing_copy = copy.deepcopy(dict(existing))
    incoming_copy = copy.deepcopy(dict(incoming))

    def _collect_trace_roots(trace: Mapping[str, Any]) -> list[dict[str, Any]]:
        root = trace.get("timing_tree")
        if not isinstance(root, Mapping):
            return []
        root_name = str(root.get("name") or "").strip()
        children = root.get("children")
        if root_name == "lookup_capture_aggregate" and isinstance(children, list):
            return [copy.deepcopy(dict(child)) for child in children if isinstance(child, Mapping)]
        return [copy.deepcopy(dict(root))]

    merged_children = _collect_trace_roots(existing_copy) + _collect_trace_roots(incoming_copy)
    total_ms = 0.0
    for child in merged_children:
        try:
            total_ms += float(child.get("duration_ms") or 0.0)
        except Exception:
            continue

    out = existing_copy
    out["debug_capture_id"] = str(
        incoming_copy.get("debug_capture_id") or existing_copy.get("debug_capture_id") or ""
    ).strip()
    out["language"] = (
        str(incoming_copy.get("language") or existing_copy.get("language") or "").strip().lower()
    )
    out["q"] = str(incoming_copy.get("q") or existing_copy.get("q") or "")
    try:
        started_existing = float(existing_copy.get("started_at") or 0.0)
    except Exception:
        started_existing = 0.0
    try:
        started_incoming = float(incoming_copy.get("started_at") or 0.0)
    except Exception:
        started_incoming = 0.0
    if started_existing > 0.0 and started_incoming > 0.0:
        out["started_at"] = min(started_existing, started_incoming)
    else:
        out["started_at"] = started_existing or started_incoming or 0.0
    out["total_ms"] = round(total_ms, 3)
    out["timing_tree"] = {
        "name": "lookup_capture_aggregate",
        "label": "Lookup Capture Requests",
        "meta": {"request_count": len(merged_children)},
        "started_ms": 0.0,
        "duration_ms": round(total_ms, 3),
        "children": merged_children,
    }
    for bucket in (
        "normalizations",
        "sqlite_queries",
        "retrievals",
        "segmenter_events",
        "decoration_events",
    ):
        merged_bucket = []
        for src in (existing_copy, incoming_copy):
            rows = src.get(bucket)
            if isinstance(rows, list):
                merged_bucket.extend(copy.deepcopy(rows))
        out[bucket] = merged_bucket
    if incoming_copy.get("final_payload") is not None:
        out["final_payload"] = copy.deepcopy(incoming_copy.get("final_payload"))
    elif existing_copy.get("final_payload") is not None:
        out["final_payload"] = copy.deepcopy(existing_copy.get("final_payload"))
    if incoming_copy.get("final_payload_artifact") is not None:
        out["final_payload_artifact"] = copy.deepcopy(incoming_copy.get("final_payload_artifact"))
    elif existing_copy.get("final_payload_artifact") is not None:
        out["final_payload_artifact"] = copy.deepcopy(existing_copy.get("final_payload_artifact"))
    return out


def _build_lookup_dp_only_payload(
    word: str,
    lang_code: str,
    selected_sources: Sequence[str] | None,
    lemma: str = "",
    upos: str = "",
    xpos: str = "",
    exact_only: bool = False,
    debug_trace: bool = False,
) -> dict[str, Any]:
    token = str(word or "")
    if not token.strip():
        return {"ok": False, "error": "empty"}
    upos_hint = str(upos or "").strip().upper()
    xpos_hint = str(xpos or "").strip()
    lookup_data = {
        "ok": True,
        "display_text": token,
        "segments": [token],
        "segment_offsets": [[0, len(token)]],
        "grammar_overlay": {"tokens": []},
        "ud_overlay": {
            "ok": False,
            "tokens": [
                {
                    "i": 0,
                    "doc_i": 0,
                    "head": 0,
                    "dep": "dep",
                    "text": token,
                    "upos": upos_hint or "X",
                    "tag": xpos_hint,
                    "lemma": str(lemma or ""),
                    "lemma_raw": str(lemma or ""),
                    "lemma_suffix": "",
                    "feats": "",
                }
            ],
            "edges": [],
            "roots": [],
            "ents": [],
            "sentences": [],
        },
    }
    results_by_seg, entry_store = _build_results_by_seg(
        lookup_data, lang_code, selected_sources, debug_trace=debug_trace
    )
    result = (
        results_by_seg[0]
        if results_by_seg
        else _build_unknown_result(
            token, upos_hint or "unknown", xpos_hint, "dep", lemma, "", 0, lemma, ""
        )
    )
    payload = _build_lookup_payload_base(lookup_data)
    payload["results_by_seg"] = [result]
    payload["entry_store"] = entry_store
    return payload


def _build_subsegments_payload(
    token: str, lang_code: str, selected_sources: Sequence[str] | None, decompose: bool = False
) -> dict[str, Any]:
    text = str(token or "")
    if not text.strip():
        return {"ok": False, "error": "empty"}
    segmenter = _get_sqlite_segmenter(lang_code, selected_sources)
    if segmenter is None:
        return {"ok": True, "token": text, "subsegments": [], "mode": "greedy"}
    fill = segmenter.fill_token(
        text, {"allowExact": not decompose, "excludeWhole": bool(decompose)}
    )
    mode = str(fill.get("mode") or "greedy")
    prepared = _prepare_fill_entries(
        fill.get("fills") or [], text, segmenter, lang_code, "", "", mode, "surface"
    )
    if decompose and text:
        prepared = [row for row in prepared if str(row.get("head") or "") != text]
    return {
        "ok": True,
        "token": text,
        "subsegments": prepared,
        "mode": mode,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

_NOINDEX_EXACT_PATHS = {
    "/reader",
    "/account",
    "/contact",
    "/about",
    "/lookup",
    "/lookup_dp_only",
    "/subsegments",
    "/lookup/gate",
}
_NOINDEX_PREFIXES = (
    "/auth/",
    "/payments/",
    "/api/",
    "/js/",
    "/extension/",
    "/dict-index/",
)


def _site_base_url() -> str:
    return le_config.APP_BASE_URL or request.host_url.rstrip("/")


@app.after_request
def _add_private_route_noindex(response):
    path = request.path.rstrip("/") or "/"
    if path in _NOINDEX_EXACT_PATHS or request.path.startswith(_NOINDEX_PREFIXES):
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.route("/robots.txt")
def robots_txt():
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /reader",
            "Disallow: /account",
            "Disallow: /contact",
            "Disallow: /about",
            "Disallow: /auth/",
            "Disallow: /payments/",
            "Disallow: /api/",
            "Disallow: /lookup",
            "Disallow: /lookup_dp_only",
            "Disallow: /subsegments",
            "Disallow: /js/",
            "Disallow: /extension/",
            f"Sitemap: {_site_base_url()}/sitemap.xml",
            "",
        ]
    )
    return Response(body, mimetype="text/plain; charset=utf-8")


@app.route("/sitemap.xml")
def sitemap_xml():
    base = _xml_escape(_site_base_url())
    urls = [
        f"{base}/",
        f"{base}/chrome-extension",
    ]
    items = "\n".join(f"  <url><loc>{url}</loc></url>" for url in urls)
    body = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{items}\n</urlset>\n'
    return Response(body, mimetype="application/xml; charset=utf-8")


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect("/reader")
    visitor_id = str(request.cookies.get("le_vid") or "").strip()
    new_visitor_cookie = False
    if not visitor_id:
        visitor_id = _ext_secrets.token_urlsafe(18)
        new_visitor_cookie = True
    try:
        from analytics import record_landing_visit

        record_landing_visit(visitor_id)
    except Exception:
        pass
    response = make_response(render_template("landing.html"))
    if new_visitor_cookie:
        response.set_cookie(
            "le_vid",
            visitor_id,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            secure=bool(le_config.IS_PRODUCTION),
            samesite="Lax",
        )
    return response


@app.route("/chrome-extension")
def chrome_extension_page():
    return redirect(
        "https://chromewebstore.google.com/detail/language-engine-capture/moljdhkmokgdglimghgkenhbeccpognn"
    )


@app.route("/reader", methods=["GET"])
def reader_page():
    return render_template(
        "reader_jshybrid.html",
        js_index_urls=dict(_js_index_urls),
    )


@app.route("/account")
def account_page():
    if not current_user.is_authenticated:
        return redirect("/")
    return render_template("account.html")


@app.route("/about")
def about_page():
    if not current_user.is_authenticated:
        return redirect("/")
    return render_template("about.html")


@app.route("/contact")
def contact_page():
    if not current_user.is_authenticated:
        return redirect("/")
    return render_template("contact.html")


def _is_admin_user() -> bool:
    if not current_user.is_authenticated:
        return False
    try:
        from db import User

        email = str(getattr(current_user, "email", "") or "").strip().lower()
        return bool(email and email in User.PREMIUM_EMAILS)
    except Exception:
        return False


@app.route("/admin/analytics")
def admin_analytics_page():
    if not _is_admin_user():
        return redirect("/") if not current_user.is_authenticated else ("Forbidden", 403)
    try:
        days = int(request.args.get("days") or 30)
    except (TypeError, ValueError):
        days = 30
    from analytics import admin_summary

    return render_template("admin_analytics.html", analytics=admin_summary(days), days=days)


@app.route("/admin/analytics.json")
def admin_analytics_json():
    if not _is_admin_user():
        return jsonify({"ok": False, "error": "Forbidden"}), 403
    try:
        days = int(request.args.get("days") or 30)
    except (TypeError, ValueError):
        days = 30
    from analytics import admin_summary

    return jsonify(admin_summary(days))


def _get_or_create_lookup_quota():
    from db import LookupQuota

    quota = LookupQuota.query.filter_by(user_id=current_user.id).first()
    if not quota:
        quota = LookupQuota(user_id=current_user.id)
        le_db.session.add(quota)
    quota.reset_if_new_day()
    return quota


def _lookup_quota_payload(quota=None, *, over_limit: bool | None = None) -> dict[str, Any]:
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
        (payload.get("ud_overlay") or {}) if isinstance(payload.get("ud_overlay"), Mapping) else {}
    ).get("tokens")
    if isinstance(ud_tokens, Sequence) and not isinstance(ud_tokens, (str, bytes, bytearray)):
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
    if isinstance(segments, Sequence) and not isinstance(segments, (str, bytes, bytearray)):
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


@app.route("/lookup/gate", methods=["POST"])
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


def _contact_field(value: Any, max_len: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."


def _contact_header(value: str) -> str:
    return re.sub(r"[\r\n]+", " ", value).strip()


def _send_contact_email(
    contact_type: str, subject: str, message: str, context: Mapping[str, Any]
) -> None:
    if not le_config.SMTP_HOST:
        raise RuntimeError("SMTP is not configured.")

    user_email = _contact_field(getattr(current_user, "email", ""), 255)
    user_id = _contact_field(getattr(current_user, "id", ""), 40)
    context = context if isinstance(context, Mapping) else {}

    lines = [
        f"Type: {contact_type}",
        f"Title: {subject}",
        f"User email: {user_email}",
        f"User ID: {user_id}",
        f"URL: {_contact_field(context.get('url'), 500)}",
        f"Language: {_contact_field(context.get('language_label'), 120)} ({_contact_field(context.get('language'), 40)})",
        f"Document: {_contact_field(context.get('document'), 300)}",
        f"Page: {_contact_field(context.get('page'), 120)}",
        f"Browser: {_contact_field(context.get('user_agent'), 500)}",
        "",
        "Selected text:",
        _contact_field(context.get("selected_text"), 1500),
        "",
        "Message:",
        message,
    ]

    email = EmailMessage()
    email["To"] = le_config.CONTACT_TO_EMAIL
    email["From"] = le_config.SMTP_FROM_EMAIL
    email["Date"] = formatdate(localtime=True)
    email["Subject"] = _contact_header(f"Language Engine contact: {contact_type} - {subject}")
    if user_email:
        email["Reply-To"] = user_email
    email.set_content("\n".join(lines))

    with smtplib.SMTP(le_config.SMTP_HOST, le_config.SMTP_PORT, timeout=15) as smtp:
        if le_config.SMTP_USE_TLS:
            smtp.starttls()
        if le_config.SMTP_USERNAME:
            smtp.login(le_config.SMTP_USERNAME, le_config.SMTP_PASSWORD)
        smtp.send_message(email)


@app.route("/api/contact", methods=["POST"])
def contact_message():
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401

    payload = request.get_json(silent=True) or {}
    contact_type = _contact_field(payload.get("contact_type"), 80) or "Question"
    subject = _contact_field(payload.get("subject"), 160)
    message = _contact_field(payload.get("message"), 5000)
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}

    if not subject:
        return jsonify({"ok": False, "error": "Title is required."}), 400
    if not message:
        return jsonify({"ok": False, "error": "Message is required."}), 400

    try:
        _send_contact_email(contact_type, subject, message, context)
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    except Exception as exc:
        print(f"[WARN] Contact email failed: {type(exc).__name__}: {exc}")
        return jsonify({"ok": False, "error": "Could not send message."}), 502

    return jsonify({"ok": True})


def _lookup_json_body() -> dict[str, Any]:
    if request.method != "POST":
        return {}
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _lookup_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clear_trankit_ner_tags(node: Any) -> Any:
    if isinstance(node, dict):
        node.pop("ner", None)
        for value in node.values():
            _clear_trankit_ner_tags(value)
    elif isinstance(node, list):
        for value in node:
            _clear_trankit_ner_tags(value)
    return node


def _replace_lookup_ner_with_gemini(payload: dict[str, Any], lang_code: str) -> None:
    overlay = payload.get("ud_overlay")
    if not isinstance(overlay, dict):
        return
    overlay["ents"] = []
    try:
        import gemini_dict

        result = gemini_dict.recognize_ner_mwe_for_overlay(
            list(payload.get("segments") or []),
            overlay,
            current_user,
            lang_code=lang_code,
        )
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "ents": []}

    ents = result.get("ents") if isinstance(result, Mapping) else []
    if isinstance(ents, list):
        overlay["ents"] = ents
    meta = result.get("meta") if isinstance(result, Mapping) else None
    overlay["gemini_ner"] = {
        "enabled": True,
        "ok": bool(result.get("ok")) if isinstance(result, Mapping) else False,
        "error": str(result.get("error") or "")
        if isinstance(result, Mapping)
        else "Gemini NER failed.",
        "tag_count": len(overlay.get("ents") or []),
        "meta": copy.deepcopy(meta) if isinstance(meta, Mapping) else {},
    }


@app.route("/lookup", methods=["GET", "POST"])
def lookup():
    """
    Main NLP + dictionary endpoint.
    Receives text, runs the NLP pipeline, then resolves dictionary segmentation
    fully on the server using the SQLite segmenter.
    """
    quota_response = _precheck_lookup_quota_response()
    if quota_response is not None:
        return quota_response

    json_body = _lookup_json_body()
    q = request.args.get("q", "")
    if not q and isinstance(json_body, Mapping):
        q = str(json_body.get("q") or "")
    raw_lang = str(request.args.get("lang") or json_body.get("lang") or "zh").strip().lower()
    use_raw = str(request.args.get("raw") or "").strip().lower() in {"1", "true", "yes", "raw"}
    exact_only = str(request.args.get("exact") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "exact",
    }
    raw_debug_capture = request.args.get("debug_capture")
    requested_debug_capture = (
        False if raw_debug_capture is None else _lookup_bool(raw_debug_capture)
    )
    enable_debug_capture = bool(requested_debug_capture and is_debug_collection_enabled())
    strip_punctuation = False
    manual_sentence_segmentation = _lookup_bool(request.args.get("manual_sentence_segmentation"))
    gemini_ner_requested = False
    trankit_override = request.args.get("trankit", "").strip()
    selected_sources = _get_requested_sources()

    if not q:
        return jsonify({"ok": False, "error": "empty"}), 400

    if len(q) > 20000:
        return jsonify({"ok": False, "error": "Input too long (max 20000 chars)."}), 400

    lang_code = resolve_lang_code(raw_lang)
    if not lang_code:
        return jsonify({"ok": False, "error": f"Unsupported language: {raw_lang}"}), 400

    manual_sentence_segmentation_post_strip = bool(
        manual_sentence_segmentation and strip_punctuation and lang_code in {"sa", "lzh"}
    )
    effective_strip_punctuation = bool(
        strip_punctuation and not manual_sentence_segmentation_post_strip
    )
    # DISABLED: the experimental chunked Trankit lookup path used geometry chunks
    # as hard tokenizer boundaries. Canonical PDF/HTML extraction now inserts
    # synthetic paragraph breaks instead, so the normal single lookup path gives
    # Trankit natural sentence/paragraph boundaries without multiple chunk passes.
    chunked_trankit_requested = False
    prepared_trankit_chunks: list[dict[str, Any]] = []

    if use_raw:
        trace_token = None
        trace_capture_id = ""
        trace_payload = None
        if enable_debug_capture:
            trace_token, trace_state = start_trace(language=lang_code, query=q)
            trace_capture_id = str(trace_state.get("debug_capture_id") or "")
        try:
            payload = _build_lookup_dp_only_payload(
                q,
                lang_code,
                selected_sources,
                lemma=request.args.get("lemma", ""),
                upos=request.args.get("upos", ""),
                xpos=request.args.get("xpos", ""),
                exact_only=exact_only,
                debug_trace=enable_debug_capture,
            )
            if enable_debug_capture and trace_capture_id:
                trace_payload = finish_trace(payload)
        finally:
            if trace_token is not None:
                stop_trace(trace_token)
        payload["language"] = lang_code
        payload = _attach_lookup_quota_after_success(payload)
        if bool(payload.get("ok", True)):
            try:
                from analytics import record_lookup

                record_lookup(lang_code, _lookup_token_count_from_payload(payload), dp_only=False)
            except Exception:
                pass
        if enable_debug_capture and trace_capture_id:
            payload["debug_capture_id"] = trace_capture_id
            if isinstance(trace_payload, Mapping):
                payload["sqlite_debug_trace"] = trace_payload
                _update_backend_debug_snapshot(
                    capture_id=trace_capture_id,
                    lang_code=lang_code,
                    query_text=q,
                    merged_payload=payload,
                    sqlite_debug_trace=trace_payload,
                )
        return _lookup_json_response(payload)

    trace_token = None
    trace_capture_id = ""
    trace_payload = None
    if enable_debug_capture:
        trace_token, trace_state = start_trace(language=lang_code, query=q)
        trace_capture_id = str(trace_state.get("debug_capture_id") or "")

    # NLP-only: JS client handles DP segmentation + hydration
    def _run_nlp(text, _dictionary, _hooks, trankit_lang):
        if enable_debug_capture:
            with trace_scope(
                "run_trankit",
                label="Run Trankit",
                language=trankit_lang,
                query_length=len(text or ""),
                chunk_count=len(prepared_trankit_chunks),
            ):
                if prepared_trankit_chunks:
                    trankit_doc = run_trankit_chunk_boundaries(
                        text,
                        prepared_trankit_chunks,
                        trankit_lang,
                        trankit_name_override=trankit_override,
                        manual_sentence_segmentation=manual_sentence_segmentation,
                        strip_punctuation_after_manual_sentence_segmentation=manual_sentence_segmentation_post_strip,
                    )
                else:
                    trankit_doc = run_trankit(
                        text,
                        trankit_lang,
                        trankit_name_override=trankit_override,
                        manual_sentence_segmentation=manual_sentence_segmentation,
                        strip_punctuation_after_manual_sentence_segmentation=manual_sentence_segmentation_post_strip,
                    )
                trankit_doc = _normalize_trankit_upos_doc(trankit_doc, trankit_lang)
                if gemini_ner_requested:
                    _clear_trankit_ner_tags(trankit_doc)
            with trace_scope(
                "process_lookup_nlp_only", label="Process NLP Only", language=trankit_lang
            ):
                payload = process_lookup_nlp_only(
                    text,
                    trankit_doc,
                    trankit_lang=trankit_lang,
                    enable_debug_capture=True,
                    debug_capture_id=trace_capture_id,
                )
                if prepared_trankit_chunks and isinstance(payload, dict):
                    payload["trankit_chunked_lookup"] = {
                        "enabled": True,
                        "mode": "boundary_tokenized",
                        "chunk_count": len(prepared_trankit_chunks),
                    }
                return payload
        if prepared_trankit_chunks:
            trankit_doc = run_trankit_chunk_boundaries(
                text,
                prepared_trankit_chunks,
                trankit_lang,
                trankit_name_override=trankit_override,
                manual_sentence_segmentation=manual_sentence_segmentation,
                strip_punctuation_after_manual_sentence_segmentation=manual_sentence_segmentation_post_strip,
            )
        else:
            trankit_doc = run_trankit(
                text,
                trankit_lang,
                trankit_name_override=trankit_override,
                manual_sentence_segmentation=manual_sentence_segmentation,
                strip_punctuation_after_manual_sentence_segmentation=manual_sentence_segmentation_post_strip,
            )
        trankit_doc = _normalize_trankit_upos_doc(trankit_doc, trankit_lang)
        if gemini_ner_requested:
            _clear_trankit_ner_tags(trankit_doc)
        payload = process_lookup_nlp_only(
            text,
            trankit_doc,
            trankit_lang=trankit_lang,
            enable_debug_capture=False,
        )
        if prepared_trankit_chunks and isinstance(payload, dict):
            payload["trankit_chunked_lookup"] = {
                "enabled": True,
                "mode": "boundary_tokenized",
                "chunk_count": len(prepared_trankit_chunks),
            }
        return payload

    try:
        if enable_debug_capture:
            with trace_scope(
                "run_with_universal_normalization",
                label="Universal Normalization",
                language=lang_code,
                strip_punctuation=effective_strip_punctuation,
                manual_sentence_segmentation=manual_sentence_segmentation,
                chunk_count=len(prepared_trankit_chunks),
            ):
                payload = run_with_universal_normalization(
                    q,
                    _run_nlp,
                    None,
                    None,
                    lang_code,
                    language=lang_code,
                    strip_punctuation=effective_strip_punctuation,
                )
            trace_payload = finish_trace(payload)
        else:
            payload = run_with_universal_normalization(
                q,
                _run_nlp,
                None,
                None,
                lang_code,
                language=lang_code,
                strip_punctuation=effective_strip_punctuation,
            )
    finally:
        if trace_token is not None:
            stop_trace(trace_token)

    if gemini_ner_requested and isinstance(payload, dict):
        _replace_lookup_ner_with_gemini(payload, lang_code)

    payload["language"] = lang_code
    payload = _attach_lookup_quota_after_success(payload)
    if bool(payload.get("ok", True)):
        try:
            from analytics import record_lookup

            record_lookup(lang_code, _lookup_token_count_from_payload(payload), dp_only=False)
        except Exception:
            pass
    if enable_debug_capture and trace_capture_id:
        payload["debug_capture_id"] = trace_capture_id
        prepared_trace = _prepare_debug_trace_payload(
            trace_payload,
            request_kind="lookup_nlp",
            label="Lookup NLP Request",
        )
        if isinstance(prepared_trace, Mapping):
            payload["sqlite_debug_trace"] = prepared_trace
            _update_backend_debug_snapshot(
                capture_id=trace_capture_id,
                lang_code=lang_code,
                query_text=q,
                merged_payload=payload,
                sqlite_debug_trace=prepared_trace,
            )
    return _lookup_json_response(payload)


@app.route("/lookup_dp_only")
def lookup_dp_only():
    """
    Server-side single-token dictionary lookup.
    Returns the same payload shape previously assembled in the browser.
    """
    quota_response = _precheck_lookup_quota_response()
    if quota_response is not None:
        return quota_response

    q = (request.args.get("q") or "").strip()
    raw_lang = (request.args.get("lang") or "").strip().lower()
    lang_code = resolve_lang_code(raw_lang) or raw_lang
    if not q or not lang_code:
        return jsonify({"ok": False, "error": "missing q or lang"}), 400
    payload = _build_lookup_dp_only_payload(
        q,
        lang_code,
        _get_requested_sources(),
        lemma=request.args.get("lemma", ""),
        upos=request.args.get("upos", ""),
        xpos=request.args.get("xpos", ""),
        exact_only=str(request.args.get("exact") or "").strip().lower()
        in {"1", "true", "yes", "exact"},
        debug_trace=str(request.args.get("debug_trace") or "").strip().lower()
        in {"1", "true", "yes", "on"},
    )
    payload["language"] = lang_code
    if bool(payload.get("ok", True)):
        try:
            from analytics import record_lookup

            record_lookup(lang_code, _lookup_token_count_from_payload(payload), dp_only=True)
        except Exception:
            pass
    return _lookup_json_response(payload)


@app.route("/subsegments")
def subsegments():
    """
    Server-side subsegment decomposition using the SQLite segmenter.
    """
    token = (request.args.get("token") or "").strip()
    raw_lang = (request.args.get("lang") or "").strip().lower()
    lang_code = resolve_lang_code(raw_lang) or raw_lang
    if not token or not lang_code:
        return jsonify({"ok": False, "error": "missing token or lang"}), 400
    decompose = str(request.args.get("decompose") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    payload = _build_subsegments_payload(
        token, lang_code, _get_requested_sources(), decompose=decompose
    )
    payload["language"] = lang_code
    return jsonify(payload)


@app.route("/annotation", methods=["GET", "POST"])
def annotation_endpoint():
    """
    Annotations placeholder — disabled until user accounts are implemented.
    """
    if request.method == "GET":
        head = (request.args.get("head") or "").strip()
        if not head:
            return jsonify({"ok": False, "error": "missing head"}), 400
        return jsonify({"ok": True, "head": head, "note": ""})
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# MT glossing — Gemini dict generation first, Google Translate fallback
# ---------------------------------------------------------------------------


# Gemini synthetic dictionary entry generation
@app.route("/api/mt_gloss", methods=["POST"])
def mt_gloss():
    """Generate a synthetic dictionary entry for one unknown token via Gemini.

    Writes result to gemini_generated_tsvs/{lang}.tsv (server copy).
    """
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    surface_form = (data.get("surface_form") or "").strip()
    target_word = (data.get("target_word") or "").strip()
    lang = (data.get("language") or "").strip()
    sentence = (data.get("sentence") or "").strip()
    lemma = (data.get("lemma") or "").strip()
    upos = (data.get("upos") or "").strip()
    xpos = (data.get("xpos") or "").strip()
    feats = (data.get("feats") or "").strip()
    dep = (data.get("dep") or "").strip()
    if not token or not lang:
        return jsonify({"ok": False, "error": "Missing token or language."}), 400

    import gemini_dict

    if not gemini_dict.is_enabled():
        return jsonify({"ok": False, "error": "Gemini dict not configured."}), 503

    entry = gemini_dict.generate_entry(
        token,
        sentence or token,
        lang,
        lemma_hint=lemma,
        upos=upos,
        xpos=xpos,
        feats=feats,
        dep=dep,
        surface_form=surface_form,
        target_word=target_word,
        user=current_user,
    )

    if not entry:
        return jsonify({"ok": False, "error": "Generation failed or budget exhausted."})

    return jsonify({"ok": True, "entry": entry})


@app.route("/js/dict/<lang_code>/custom_index")
def js_custom_index(lang_code: str):
    """
    Compact key index for custom/Gemini entries only — never cached to disk.
    Returns gzip-compressed JSON: {hw, fw, db_aliases} containing only customdb keys.
    Called by the client after loading the static index to inject user-created entries.
    """
    import hashlib as _hashlib
    from dict_lookup_sqlite import build_compact_key_index, APP_DB_PATH

    resolved = resolve_lang_code(lang_code.strip().lower())
    if not resolved:
        return jsonify({"ok": False, "error": f"Unsupported language: {lang_code}"}), 400

    if not APP_DB_PATH.exists():
        # No custom DB at all — return empty index
        import gzip as _gz

        empty = {"hw": {}, "fw": {}, "db_aliases": {}, "count": 0}
        return Response(
            _gz.compress(json.dumps(empty, separators=(",", ":")).encode()),
            status=200,
            headers={"Content-Type": "application/gzip", "Cache-Control": "no-store"},
        )

    # Build custom-only index (no static sqlite files, just customdb)
    index = build_compact_key_index(resolved, db_paths=[], include_custom_entries=True)
    count = sum(len(v) for v in index.get("hw", {}).values())
    index["count"] = count

    import gzip as _gz

    compressed = _gz.compress(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        compresslevel=1,
    )
    return Response(
        compressed,
        status=200,
        headers={
            "Content-Type": "application/gzip",
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        },
    )


@app.route("/api/dict/<lang_code>/gemini", methods=["GET"])
def get_gemini_dict(lang_code):
    """Stream SQLite-backed custom-entry overlay rows for a language as TSV."""

    lang = (lang_code or "").strip().lower()
    if not lang:
        return jsonify({"ok": False, "error": "Missing language."}), 400

    import gemini_dict

    return Response(
        stream_with_context(gemini_dict.iter_custom_entry_tsv_lines(lang)),
        mimetype="text/tab-separated-values",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# Legacy Google Translate synthetic-entry annotation path disabled.


# ---------------------------------------------------------------------------
# Gemini LLM assistant
# ---------------------------------------------------------------------------


@app.route("/api/llm_query", methods=["POST"])
def llm_query():
    """Send a user query + reader context to Gemini. Paid users only."""
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401

    from api_services import query_gemini

    data = request.get_json(silent=True) or {}
    context_text = (data.get("context") or "").strip()
    conversation_history = (data.get("history") or "").strip()
    last_exchange = (data.get("last_exchange") or "").strip()
    user_query = (data.get("query") or "").strip()
    lang_code = (data.get("lang") or "").strip()
    include_reader_context = bool(data.get("include_reader_context"))

    if not user_query:
        return jsonify({"ok": False, "error": "Empty query."}), 400

    result = query_gemini(
        context_text,
        user_query,
        current_user,
        lang_code=lang_code,
        include_reader_context=include_reader_context,
        conversation_history=conversation_history,
        last_exchange=last_exchange,
    )
    status = 200 if result.get("ok") else (403 if result.get("upgrade") else 429)
    return jsonify(result), status


@app.route("/api/llm_translate_sentences", methods=["POST"])
def llm_translate_sentences():
    """Batch translate per-sentence token lists to fluent English. Paid users only."""
    from gemini_dict import translate_sentences

    data = request.get_json(silent=True) or {}
    sentence_requests = data.get("requests") or []
    lang_code = (data.get("lang") or "").strip()
    if not isinstance(sentence_requests, list):
        return jsonify({"ok": False, "error": "requests must be a list."}), 400
    result = translate_sentences(
        [],
        current_user,
        lang_code=lang_code,
        sentence_requests=sentence_requests,
    )
    status = 200 if result.get("ok") else (403 if result.get("upgrade") else 429)
    return jsonify(result), status


@app.route("/api/llm_usage", methods=["GET"])
def llm_usage():
    """Return current LLM usage stats for the logged-in user."""
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401

    from db import ApiUsage
    from config import TIER_CAPS

    usage = ApiUsage.query.filter_by(user_id=current_user.id).first()
    tier = current_user.tier
    caps = TIER_CAPS.get(tier, {})

    if usage:
        usage._maybe_reset(current_user)
        le_db.session.commit()

    llm_budget_usd = (
        usage.llm_budget_usd(current_user)
        if usage
        else float(caps.get("llm_budget_usd_per_month", 0.0) or 0.0)
    )
    llm_cost_usd = usage.llm_cost_usd(current_user) if usage else 0.0
    llm_usage_pct = usage.llm_usage_percent(current_user) if usage else 0.0

    return jsonify(
        {
            "ok": True,
            "tier": tier,
            "mt_chars_used": usage.mt_chars_used if usage else 0,
            "mt_chars_cap": caps.get("mt_chars_per_month", 0),
            "llm_prompt_tokens_used": usage.llm_prompt_tokens_used if usage else 0,
            "llm_output_tokens_used": usage.llm_output_tokens_used if usage else 0,
            "llm_tokens_used": usage.llm_tokens_used if usage else 0,
            "llm_budget_usd": llm_budget_usd,
            "llm_cost_usd": llm_cost_usd,
            "llm_usage_pct": llm_usage_pct,
        }
    )


# ---------------------------------------------------------------------------
# User dictionary entries — community definitions
# ---------------------------------------------------------------------------


@app.route("/api/user_dict/add", methods=["POST"])
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
        return jsonify({"ok": False, "error": "An entry for this headword already exists."}), 409

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
    _invalidate_sqlite_segmenter_cache(language, _collect_lookup_texts_for_entry(entry_payload))

    return jsonify({"ok": True, "entry": entry_payload})


@app.route("/api/user_dict/update", methods=["POST"])
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
            data.get("romanization") if "romanization" in data else current_payload["romanization"]
        ),
        pos=(data.get("pos") if "pos" in data else current_payload["pos"]),
        glosses=(defs if defs is not None else current_payload["glosses"]),
        forms=(forms if forms is not None else current_payload["forms"]),
        commentary=(
            data.get("commentary") if "commentary" in data else current_payload["commentary"]
        ),
        lemma=(data.get("lemma") if "lemma" in data else current_payload["lemma"]),
        source="user_created",
        entry_id=entry.entry_id,
    )
    if not updated:
        return jsonify({"ok": False, "error": "Failed to update entry."}), 500
    updated_payload = _custom_entry_to_response(updated)
    _invalidate_sqlite_segmenter_cache(
        entry.language, _collect_lookup_texts_for_entry(updated_payload)
    )
    return jsonify({"ok": True, "entry": updated_payload})


@app.route("/api/user_dict/delete", methods=["POST"])
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

    removed = gemini_dict.remove_tsv_entry(entry.language, entry.headword, entry_id=entry.entry_id)
    if not removed:
        return jsonify({"ok": False, "error": "Entry not found."}), 404
    _invalidate_sqlite_segmenter_cache(
        entry.language, _collect_lookup_texts_for_entry(_custom_entry_to_response(entry))
    )
    return jsonify({"ok": True})


@app.route("/api/custom_entries/list", methods=["GET"])
def custom_entries_list():
    """Legacy ownership endpoint. Custom entries are shared app content now."""
    return jsonify({"ok": True, "entries": []})


@app.route("/api/community_entries", methods=["GET"])
def community_entries():
    """Legacy ownership endpoint. Custom entries are loaded through the shared index."""
    return jsonify({"ok": True, "entries": []})


# ---------------------------------------------------------------------------
# LLM per-token glosses (word-sense disambiguation aid)
# ---------------------------------------------------------------------------


@app.route("/api/llm_translate_sentences/cache_hit", methods=["POST"])
def llm_translate_sentences_cache_hit():
    """Debug endpoint: client reports that sentence translations were served
    from its in-browser session cache (no Gemini call made)."""
    data = request.get_json(silent=True) or {}
    lang = (data.get("lang") or "").strip()
    hits = data.get("hits") or []
    try:
        import gemini_log

        gemini_log.log_translation_cache_hit(
            caller="llm_translate_sentences",
            lang=lang,
            sentences=hits,
        )
    except Exception:
        pass
    return jsonify({"ok": True})


@app.route("/api/llm_glosses/cache_hit", methods=["POST"])
def llm_glosses_cache_hit():
    """Debug endpoint: client reports that glosses were served from its
    in-browser session cache (no Gemini call made)."""
    data = request.get_json(silent=True) or {}
    lang = (data.get("lang") or "").strip()
    hits = data.get("hits") or []
    try:
        import gemini_log

        for h in hits:
            gemini_log.log_gloss_cache_hit(
                caller="llm_glosses",
                lang=lang,
                tokens=h.get("tokens") or [],
            )
    except Exception:
        pass
    return jsonify({"ok": True})


@app.route("/api/llm_decomps/cache_hit", methods=["POST"])
def llm_decomps_cache_hit():
    """Debug endpoint: client reports that token decompositions were served from its
    in-browser session cache (no Gemini call made)."""
    data = request.get_json(silent=True) or {}
    lang = (data.get("lang") or "").strip()
    hits = data.get("hits") or []
    try:
        import gemini_log

        for h in hits:
            gemini_log.log_decomp_cache_hit(
                caller="llm_decomps",
                lang=lang,
                tokens=h.get("tokens") or [],
            )
    except Exception:
        pass
    return jsonify({"ok": True})


@app.route("/api/llm_glosses", methods=["POST"])
def llm_glosses():
    """Generate short contextual LLM glosses for each Trankit token, streamed as SSE.

    Expects JSON body:
        tokens: list of {text, lemmas} — one per Trankit token
        lang: str — language code

    Streams SSE lines:
        data: {"indices": [...], "glosses": [...]}   — one per chunk as it completes
        data: {"done": true}                          — final message
        data: {"error": "..."}                        — on failure
    """
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    data = request.get_json(silent=True) or {}
    chunks = data.get("chunks") or []
    lang = (data.get("lang") or "").strip()

    if not chunks or not lang:
        return jsonify({"ok": False, "error": "Missing chunks or lang."}), 400

    import gemini_dict
    from db import ApiUsage

    if not gemini_dict.is_enabled():
        return jsonify({"ok": False, "error": "LLM glosses not available."}), 503

    # Budget check
    usage = ApiUsage.query.filter_by(user_id=current_user.id).first()
    if not usage:
        usage = ApiUsage(user_id=current_user.id)
        le_db.session.add(usage)

    usage._maybe_reset(current_user)
    if not usage.can_use_llm(current_user):
        return jsonify({"ok": False, "error": "Monthly LLM budget reached."})

    user_id = current_user.id

    def generate():
        from db import ApiUsage as _ApiUsage
        from concurrent.futures import ThreadPoolExecutor, as_completed

        _usage = _ApiUsage.query.filter_by(user_id=user_id).first()
        try:
            valid_chunks = [c for c in chunks if c.get("tokens")]

            def _run_chunk(chunk_data):
                tokens = chunk_data.get("tokens") or []
                indices = chunk_data.get("indices") or []
                context = chunk_data.get("context") or ""
                sentences = chunk_data.get("sentences") or None
                # Convert client sentence payload (list of {tokens, indices})
                # into [start, end) spans over the flat chunk token list.
                sentence_spans = None
                if sentences:
                    sentence_spans = []
                    cursor = 0
                    for s in sentences:
                        n = len(s.get("tokens") or [])
                        if n > 0:
                            sentence_spans.append([cursor, cursor + n])
                            cursor += n
                g_chunk, usage_chunk = gemini_dict.call_gloss_chunk(
                    tokens,
                    lang,
                    context,
                    sentences=sentence_spans,
                )
                return indices, g_chunk, usage_chunk

            with ThreadPoolExecutor(max_workers=len(valid_chunks) or 1) as executor:
                futures = {executor.submit(_run_chunk, c): c for c in valid_chunks}
                for future in as_completed(futures):
                    try:
                        indices, g_chunk, usage_chunk = future.result()
                    except Exception as e:
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                        continue
                    if g_chunk is not None:
                        out_indices = []
                        out_glosses = []
                        for j, gi in enumerate(indices):
                            if j < len(g_chunk) and g_chunk[j] is not None:
                                out_indices.append(gi)
                                out_glosses.append(g_chunk[j])
                        if out_indices:
                            line = json.dumps(
                                {"indices": out_indices, "glosses": out_glosses}, ensure_ascii=False
                            )
                            yield f"data: {line}\n\n"
                    if (
                        _usage
                        and usage_chunk
                        and (usage_chunk.get("prompt_tokens") or usage_chunk.get("response_tokens"))
                    ):
                        _usage.record_llm(
                            usage_chunk.get("prompt_tokens", 0),
                            usage_chunk.get("response_tokens", 0),
                        )
                        le_db.session.commit()
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield 'data: {"done": true}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/llm_decomps", methods=["POST"])
def llm_decomps():
    """Generate inflectional morpheme decompositions for selected tokens, streamed as SSE."""

    data = request.get_json(silent=True) or {}
    chunks = data.get("chunks") or []
    lang = (data.get("lang") or "").strip()

    if not chunks or not lang:
        return jsonify({"ok": False, "error": "Missing chunks or lang."}), 400

    import gemini_dict
    from db import ApiUsage

    if not gemini_dict.is_enabled():
        return jsonify({"ok": False, "error": "LLM decompositions not available."}), 503

    usage = ApiUsage.query.filter_by(user_id=current_user.id).first()
    if not usage:
        usage = ApiUsage(user_id=current_user.id)
        le_db.session.add(usage)

    usage._maybe_reset(current_user)
    if not usage.can_use_llm(current_user):
        return jsonify({"ok": False, "error": "Monthly LLM budget reached."})

    user_id = current_user.id

    def generate():
        from db import ApiUsage as _ApiUsage
        from concurrent.futures import ThreadPoolExecutor, as_completed

        _usage = _ApiUsage.query.filter_by(user_id=user_id).first()
        try:
            valid_chunks = [c for c in chunks if c.get("tokens")]

            def _run_chunk(chunk_data):
                chunk_id = chunk_data.get("chunk_id")
                tokens = chunk_data.get("tokens") or []
                indices = chunk_data.get("indices") or []
                target_positions = chunk_data.get("target_positions") or []
                target_tokens = chunk_data.get("target_tokens") or []
                targets = []
                for i, token_text in enumerate(target_tokens):
                    sentence_index = target_positions[i] if i < len(target_positions) else i
                    targets.append(
                        {
                            "sentence_index": sentence_index,
                            "text": token_text,
                        }
                    )
                d_chunk, usage_chunk = gemini_dict.call_decomp_chunk(tokens, targets, lang)
                return chunk_id, indices, d_chunk, usage_chunk

            with ThreadPoolExecutor(max_workers=len(valid_chunks) or 1) as executor:
                futures = {executor.submit(_run_chunk, c): c for c in valid_chunks}
                for future in as_completed(futures):
                    try:
                        chunk_id, indices, d_chunk, usage_chunk = future.result()
                    except Exception as e:
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                        continue
                    if d_chunk is not None:
                        line = json.dumps(
                            {
                                "chunk_id": chunk_id,
                                "indices": indices,
                                "decomps": d_chunk,
                            },
                            ensure_ascii=False,
                        )
                        yield f"data: {line}\n\n"
                    if (
                        _usage
                        and usage_chunk
                        and (usage_chunk.get("prompt_tokens") or usage_chunk.get("response_tokens"))
                    ):
                        _usage.record_llm(
                            usage_chunk.get("prompt_tokens", 0),
                            usage_chunk.get("response_tokens", 0),
                        )
                        le_db.session.commit()
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield 'data: {"done": true}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/orth_breakdowns", methods=["POST"])
def orth_breakdowns():
    """Generate orthographic/pronunciation breakdowns for each token, streamed as SSE."""

    data = request.get_json(silent=True) or {}
    chunks = data.get("chunks") or []
    lang = (data.get("lang") or "").strip()

    if not chunks or not lang:
        return jsonify({"ok": False, "error": "Missing chunks or lang."}), 400

    import gemini_dict
    from db import ApiUsage

    if not gemini_dict.is_enabled():
        return jsonify({"ok": False, "error": "Orth breakdowns not available."}), 503

    usage = ApiUsage.query.filter_by(user_id=current_user.id).first()
    if not usage:
        usage = ApiUsage(user_id=current_user.id)
        le_db.session.add(usage)

    usage._maybe_reset(current_user)
    if not usage.can_use_llm(current_user):
        return jsonify({"ok": False, "error": "Monthly LLM budget reached."})

    user_id = current_user.id

    def generate():
        from db import ApiUsage as _ApiUsage
        from concurrent.futures import ThreadPoolExecutor, as_completed

        _usage = _ApiUsage.query.filter_by(user_id=user_id).first()
        try:
            valid_chunks = [c for c in chunks if c.get("tokens")]

            def _run_chunk(chunk_data):
                tokens = chunk_data.get("tokens") or []
                indices = chunk_data.get("indices") or []
                slot_counts = chunk_data.get("slot_counts") or None
                o_chunk, usage_chunk = gemini_dict.call_orth_chunk(
                    tokens, lang, slot_counts=slot_counts
                )
                return indices, o_chunk, usage_chunk

            with ThreadPoolExecutor(max_workers=len(valid_chunks) or 1) as executor:
                futures = {executor.submit(_run_chunk, c): c for c in valid_chunks}
                for future in as_completed(futures):
                    try:
                        indices, o_chunk, usage_chunk = future.result()
                    except Exception as e:
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                        continue
                    if o_chunk is not None:
                        out_indices = []
                        out_roms = []
                        for j, gi in enumerate(indices):
                            if j < len(o_chunk) and o_chunk[j] is not None:
                                out_indices.append(gi)
                                out_roms.append(o_chunk[j])
                        if out_indices:
                            line = json.dumps(
                                {"indices": out_indices, "roms": out_roms}, ensure_ascii=False
                            )
                            yield f"data: {line}\n\n"
                    if (
                        _usage
                        and usage_chunk
                        and (usage_chunk.get("prompt_tokens") or usage_chunk.get("response_tokens"))
                    ):
                        _usage.record_llm(
                            usage_chunk.get("prompt_tokens", 0),
                            usage_chunk.get("response_tokens", 0),
                        )
                        le_db.session.commit()
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield 'data: {"done": true}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Unknown phoneme mark logger
# ---------------------------------------------------------------------------

_UNKNOWN_PHON_LOG = _os.path.join(_os.path.dirname(__file__), "unknown_phon_marks.json")
_unknown_phon_lock = __import__("threading").Lock()


@app.route("/api/log_unknown_phon_mark", methods=["POST"])
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
                        "codepoint": "U+" + format(ord(char), "04X") if len(char) == 1 else "",
                        "name": name,
                        "lang": lang,
                    }
                )
                with open(_UNKNOWN_PHON_LOG, "w", encoding="utf-8") as f:
                    _json.dump(log, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Gemini/community entry editing & vote-based deletion
# ---------------------------------------------------------------------------


@app.route("/api/gemini_entry/get", methods=["GET"])
def gemini_entry_get():
    """Get a single SQLite-backed custom entry."""
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401

    entry_id = (request.args.get("entry_id") or "").strip()
    entry_row_id = request.args.get("entry_row_id") or 0
    headword = (request.args.get("headword") or "").strip()
    language = (request.args.get("language") or "").strip()
    entry = _get_custom_dict_entry(
        entry_id=entry_id, entry_row_id=entry_row_id, language=language, headword=headword
    )
    if not entry:
        return jsonify({"ok": False, "error": "Entry not found."}), 404
    return jsonify({"ok": True, "entry": _custom_entry_to_response(entry)})


@app.route("/api/gemini_entry/update", methods=["POST"])
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
        entry_id=entry_id, entry_row_id=entry_row_id, language=language, headword=headword
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
    _invalidate_sqlite_segmenter_cache(
        entry.language, _collect_lookup_texts_for_entry(updated_payload)
    )
    return jsonify({"ok": True, "entry": updated_payload})


@app.route("/api/gemini_entry/vote_delete", methods=["POST"])
def gemini_entry_vote_delete():
    """Deprecated compatibility alias for direct paid-user deletion."""
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    data = request.get_json(silent=True) or {}
    entry_id = (data.get("entry_id") or "").strip()
    entry_row_id = data.get("entry_row_id") or 0
    headword = (data.get("headword") or "").strip()
    language = (data.get("language") or "").strip()
    entry = _get_custom_dict_entry(
        entry_id=entry_id, entry_row_id=entry_row_id, language=language, headword=headword
    )
    if not entry:
        return jsonify({"ok": False, "error": "Entry not found."}), 404

    if not _delete_custom_entry(entry):
        return jsonify({"ok": False, "error": "Entry not found."}), 404

    return jsonify({"ok": True, "deleted": True, "deprecated": True})


@app.route("/api/gemini_entry/delete", methods=["POST"])
def gemini_entry_delete():
    """Delete a custom entry for any paid user."""
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    data = request.get_json(silent=True) or {}
    entry_id = (data.get("entry_id") or "").strip()
    entry_row_id = data.get("entry_row_id") or 0
    headword = (data.get("headword") or "").strip()
    language = (data.get("language") or "").strip()
    entry = _get_custom_dict_entry(
        entry_id=entry_id, entry_row_id=entry_row_id, language=language, headword=headword
    )
    if not entry:
        return jsonify({"ok": False, "error": "Entry not found."}), 404

    if not _delete_custom_entry(entry):
        return jsonify({"ok": False, "error": "Entry not found."}), 404

    return jsonify({"ok": True, "deleted": True})


@app.route("/api/gemini_entry/deletion_votes", methods=["GET"])
def gemini_entry_deletion_votes():
    """Deprecated compatibility endpoint for the old vote-delete UI."""
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401

    entry_id = (request.args.get("entry_id") or "").strip()
    entry_row_id = request.args.get("entry_row_id") or 0
    headword = (request.args.get("headword") or "").strip()
    language = (request.args.get("language") or "").strip()
    entry = _get_custom_dict_entry(
        entry_id=entry_id, entry_row_id=entry_row_id, language=language, headword=headword
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


# ---------------------------------------------------------------------------
# User annotations
# ---------------------------------------------------------------------------


@app.route("/api/entry_note/get", methods=["GET"])
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


@app.route("/api/entry_note/save", methods=["POST"])
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


@app.route("/api/entry_note/delete", methods=["POST"])
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


@app.route("/api/entry_note/generate", methods=["POST"])
def entry_note_generate():
    """Auto-generate an explanatory note for a dictionary entry via Gemini."""
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    from db import EntryNote, ApiUsage
    from gemini_dict import generate_entry_note
    from config import TIER_CAPS

    data = request.get_json(silent=True) or {}
    lang = (data.get("lang") or "").strip()
    db_alias = (data.get("db_alias") or "").strip()
    entry_row_id = data.get("entry_row_id")
    headword = (data.get("headword") or "").strip()
    pos = (data.get("pos") or "").strip()
    sentence_tokens = (
        data.get("sentence_tokens") if isinstance(data.get("sentence_tokens"), list) else None
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


# ---------------------------------------------------------------------------
# Entry morpheme decompositions — Leipzig-style breakdowns
# ---------------------------------------------------------------------------


@app.route("/api/entry_decomp/batch", methods=["POST"])
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


@app.route("/api/entry_decomp/get", methods=["GET"])
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


@app.route("/api/entry_decomp/save", methods=["POST"])
def entry_decomp_save():
    """Create or update the morpheme decomposition for a surface form."""
    from db import EntryDecomp

    data = request.get_json(silent=True) or {}
    lang = (data.get("lang") or "").strip()
    surface_form = (data.get("surface_form") or "").strip()
    decomp = (data.get("decomp") or "").strip()

    if not lang or not surface_form or not decomp:
        return jsonify({"ok": False, "error": "Missing required fields."}), 400

    existing = EntryDecomp.query.filter_by(language=lang, surface_form=surface_form).first()
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


@app.route("/api/entry_decomp/delete", methods=["POST"])
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


@app.route("/api/entry_decomp/generate", methods=["POST"])
def entry_decomp_generate():
    """Auto-generate a morpheme decomposition for a surface form via Gemini.

    The result is stored under (language, surface_form). `headword`, `pos`,
    and `glosses` are Gemini context only; they are not part of the storage
    key. The client should send the actual surface the user is looking at as
    both `surface_form` and `headword` (so Gemini analyzes that exact form).
    """
    from db import EntryDecomp, ApiUsage
    from gemini_dict import generate_entry_decomp
    from config import TIER_CAPS

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

    existing = EntryDecomp.query.filter_by(language=lang, surface_form=surface_form).first()
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


# ---------------------------------------------------------------------------
# User sharing preferences
# ---------------------------------------------------------------------------


@app.route("/api/user/preferences", methods=["GET", "POST"])
def user_preferences():
    """Legacy sharing-preferences endpoint. Content no longer has account ownership."""
    return jsonify({"ok": True})


@app.route("/api/lang_config")
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


# ---------------------------------------------------------------------------
# Serve gzipped TSV dictionaries to the client
# ---------------------------------------------------------------------------

import gzip as _gzip

# Cache gzipped TSV files in a separate runtime directory so we can stream
# prebuilt .gz payloads without touching the source TSVs.
_DICT_GZIP_CACHE_DIR = APP_ROOT / "runtime_cache" / "dict_gzip"
_DICT_GZIP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_DICT_GZIP_EVENT_LOG_PATH = _DICT_GZIP_CACHE_DIR / "gzip_cache_events.jsonl"
_gzipped_tsv_lock = threading.Lock()
_gzip_event_log_lock = threading.Lock()


def _log_gzip_event(event: str, **fields) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": str(event or "").strip(),
    }
    payload.update(fields)
    try:
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with _gzip_event_log_lock:
            with _DICT_GZIP_EVENT_LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception:
        pass


def _dict_version_from_path(tsv_path: Path) -> str:
    st = tsv_path.stat()
    return f"{int(st.st_mtime_ns)}-{int(st.st_size)}"


def _resolve_dict_tsv_path(lang_code: str, source: str = "") -> Path | None:
    tsv_path = None
    if source:
        info = LANGUAGE_REGISTRY.get(lang_code, {})
        ds = info.get("dict_sources", {})
        if source in ds and ds[source].get("dict_file"):
            p = APP_ROOT / ds[source]["dict_file"]
            if p.exists():
                tsv_path = p
    if not tsv_path:
        tsv_path = get_tsv_path(lang_code)
    return tsv_path


def _dict_gzip_cache_paths(
    tsv_path: Path, lang_code: str, source: str, version: str
) -> tuple[Path, Path]:
    src_path = str(tsv_path.resolve())
    raw_key = f"{lang_code}|{source}|{src_path}|{version}"
    digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:20]
    gz_path = _DICT_GZIP_CACHE_DIR / f"{lang_code}-{source or 'default'}-{digest}.tsv.gz"
    meta_path = _DICT_GZIP_CACHE_DIR / f"{lang_code}-{source or 'default'}-{digest}.json"
    return gz_path, meta_path


def _ensure_cached_gzip_tsv(lang_code: str, source: str = "") -> tuple[Path | None, str]:
    """Return (gz_path, version) for a language, writing a runtime .gz cache if needed.

    If source is given and matches a dict_sources key, serve that file instead.
    """
    started = time.perf_counter()
    tsv_path = _resolve_dict_tsv_path(lang_code, source=source)
    if not tsv_path:
        _log_gzip_event(
            "builtin_cache_missing_source",
            kind="builtin",
            lang=lang_code,
            source=source,
        )
        return None, ""

    version = _dict_version_from_path(tsv_path)
    gz_path, meta_path = _dict_gzip_cache_paths(tsv_path, lang_code, source, version)

    with _gzipped_tsv_lock:
        existing_meta = {}
        if gz_path.exists() and meta_path.exists():
            try:
                existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                existing_meta = {}
            if (
                existing_meta.get("version") == version
                and existing_meta.get("source_path") == str(tsv_path.resolve())
                and existing_meta.get("gz_size")
                and gz_path.stat().st_size == int(existing_meta.get("gz_size"))
            ):
                _log_gzip_event(
                    "builtin_cache_hit",
                    kind="builtin",
                    lang=lang_code,
                    source=source,
                    source_path=str(tsv_path.resolve()),
                    version=version,
                    gz_path=str(gz_path.resolve()),
                    gz_size=gz_path.stat().st_size,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
                return gz_path, version

        tmp_gz_path = gz_path.with_suffix(gz_path.suffix + ".tmp")
        tmp_meta_path = meta_path.with_suffix(meta_path.suffix + ".tmp")
        with tsv_path.open("rb") as src_fh, _gzip.open(tmp_gz_path, "wb", compresslevel=9) as gz_fh:
            while True:
                chunk = src_fh.read(1024 * 1024)
                if not chunk:
                    break
                gz_fh.write(chunk)
        gz_size = tmp_gz_path.stat().st_size
        tmp_meta_path.write_text(
            json.dumps(
                {
                    "version": version,
                    "source_path": str(tsv_path.resolve()),
                    "gz_size": gz_size,
                }
            ),
            encoding="utf-8",
        )
        tmp_gz_path.replace(gz_path)
        tmp_meta_path.replace(meta_path)
        _log_gzip_event(
            "builtin_cache_rebuild",
            kind="builtin",
            lang=lang_code,
            source=source,
            source_path=str(tsv_path.resolve()),
            version=version,
            previous_version=existing_meta.get("version", ""),
            gz_path=str(gz_path.resolve()),
            gz_size=gz_size,
            reason=(
                "missing_cache"
                if not existing_meta
                else (
                    "version_changed"
                    if existing_meta.get("version") != version
                    else "metadata_mismatch"
                )
            ),
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return gz_path, version


def _stream_gzip_file(gz_path: Path):
    chunk_size = 65536  # 64 KB chunks for visible streaming progress
    with gz_path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            yield chunk


def _build_gzip_response(gz_path: Path, filename: str) -> Response:
    total = gz_path.stat().st_size
    return Response(
        _stream_gzip_file(gz_path),
        mimetype="application/gzip",
        direct_passthrough=True,
        headers={
            "Content-Encoding": "identity",  # raw gzip bytes, not HTTP-level encoding
            "Content-Disposition": f"inline; filename={filename}",
            "Content-Length": str(total),
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.route("/api/dict/<lang_code>")
def serve_dict(lang_code):
    """Serve a gzipped TSV dictionary for client-side storage.

    Accepts optional ?source= to serve an alternative dictionary
    (e.g. ?source=jmdict, ?source=cc-cedict, ?source=monier-williams).
    """
    code = resolve_lang_code(lang_code) or lang_code
    source = request.args.get("source", "").strip()
    gz_path, _version = _ensure_cached_gzip_tsv(code, source=source)
    if not gz_path:
        return jsonify({"ok": False, "error": f"No dictionary for {lang_code}"}), 404
    fn = f"dict-{code}-{source}.tsv.gz" if source else f"dict-{code}.tsv.gz"
    _log_gzip_event(
        "builtin_cache_served",
        kind="builtin",
        lang=code,
        source=source,
        gz_path=str(gz_path.resolve()),
        gz_size=gz_path.stat().st_size,
        filename=fn,
    )
    return _build_gzip_response(gz_path, fn)


# ============================================================================
# DEFUNCT DO NOT TOUCH
# DEFUNCT DO NOT TOUCH
# DEFUNCT DO NOT TOUCH
# Legacy direct SQLite batch lookup endpoint.
# The live UI lookup flows now go through /lookup and /lookup_dp_only so the
# server can run the current segmenter/router pipeline and post-decoration path.
# Keep this only for old callers, debugging, or rollback archaeology.
# Do not append new lookup behavior here.
# ============================================================================


# ============================================================================
# DEFUNCT DO NOT TOUCH
# DEFUNCT DO NOT TOUCH
# DEFUNCT DO NOT TOUCH
# Legacy direct SQLite single-word lookup endpoint.
# The live UI single-token path now goes through /lookup_dp_only so it shares
# the same segment-result assembly and decoration path as the main lookup flow.
# Keep this only for old callers, debugging, or rollback archaeology.
# Do not append new lookup behavior here.
# ============================================================================


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


@app.route("/api/dict_sources/<lang_code>")
def dict_sources(lang_code):
    """List active SQLite dictionary sources for a registered language."""
    lang = resolve_lang_code(lang_code)
    if not lang:
        return jsonify({"ok": False, "error": f"Unsupported language: {lang_code}"}), 400
    return jsonify({"ok": True, "sources": _registered_dict_source_items(lang)})


@app.route("/api/languages")
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


# ---------------------------------------------------------------------------
# JS Hybrid Architecture Routes
# /js/lookup  — NLP-only payload (no SQLite segmentation)
# /js/hydrate — batch entry hydration from winner refs
# /js/dict/<lang>/index — compact key index for client-side DP
# /reader_js  — serves the hybrid reader template
# ---------------------------------------------------------------------------

_JS_INDEX_CACHE_DIR = APP_ROOT / "runtime_cache" / "js_index"
_JS_INDEX_ARTIFACT_DIR = APP_ROOT / "runtime_cache" / "dict_index_artifacts"
_JS_INDEX_SCHEMA_VERSION = 6


def _js_index_cache_path(lang_code: str, source: str = "") -> Path:
    if source:
        return _JS_INDEX_CACHE_DIR / f"{lang_code}-{source}.json.gz"
    return _JS_INDEX_CACHE_DIR / f"{lang_code}.json.gz"


def _js_index_artifact_name(lang_code: str, source: str, version: str) -> str:
    base = f"{lang_code}-{source}" if source else lang_code
    return f"{base}.{version}.json.gz"


def _js_index_cache_schema_version(cache_path: Path) -> int:
    try:
        import gzip as _gz

        raw = json.loads(_gz.decompress(cache_path.read_bytes()).decode("utf-8"))
        return int(raw.get("v") or 0)
    except Exception:
        return 0


def _js_index_cache_is_fresh(
    lang_code: str,
    cache_path: Path,
    db_paths: list,
    include_custom_entries: bool = True,
    expected_schema_version: int = _JS_INDEX_SCHEMA_VERSION,
) -> bool:
    """Return True if cache matches schema and is newer than all source .sqlite files."""
    if not cache_path.exists():
        return False
    if expected_schema_version and _js_index_cache_schema_version(cache_path) != int(
        expected_schema_version
    ):
        return False
    cache_mtime = cache_path.stat().st_mtime
    from dict_lookup_sqlite import APP_DB_PATH

    for p in db_paths:
        if p.stat().st_mtime > cache_mtime:
            return False
    if (
        include_custom_entries
        and APP_DB_PATH.exists()
        and APP_DB_PATH.stat().st_mtime > cache_mtime
    ):
        return False
    return True


@app.route("/js/hydrate", methods=["POST"])
def js_hydrate():
    """
    Batch entry hydration. Accepts winner_refs from JS DP segmentation,
    returns fully hydrated entry_store (same shape as /lookup output).
    """
    from dict_lookup_sqlite import hydrate_winner_refs as _hydrate

    data = request.get_json(silent=True) or {}
    raw_lang = str(data.get("lang") or "").strip().lower()
    lang_code = resolve_lang_code(raw_lang) or raw_lang
    if not lang_code:
        return jsonify({"ok": False, "error": "missing lang"}), 400
    if lang_code not in LANGUAGE_REGISTRY:
        return jsonify({"ok": False, "error": f"Unsupported language: {raw_lang}"}), 400
    debug_capture_id = str(data.get("debug_capture_id") or "").strip()
    enable_debug_trace = bool(debug_capture_id)

    winner_refs = list(data.get("winner_refs") or [])
    allowed_sqlite_aliases = _registered_sqlite_aliases_for_language(lang_code)

    # Remap JS wire format to the internal keys hydrate_winner_refs() expects
    candidates = []
    sqlite_stems: set[str] = set()
    match_keys_by_wire: dict[str, str] = {}
    for ref in winner_refs:
        storage_kind = str(ref.get("storage_kind") or "sqlite")
        db_alias = str(ref.get("db_alias") or "")
        entry_row_id = int(ref.get("entry_row_id") or 0)
        form_row_id = int(ref.get("form_row_id") or 0)
        c: dict[str, Any] = {
            "_storage_kind": storage_kind,
            "_storage_db_alias": db_alias,
            "_storage_row_id": entry_row_id,
            "_match_kind": str(ref.get("match_kind") or "headword"),
            "match_key": str(ref.get("match_key") or ""),
        }
        if form_row_id > 0:
            c["_form_row_id"] = form_row_id
            c["_matched_form_row_ids"] = [form_row_id]
        candidates.append(c)
        wire_key = f"{storage_kind}|{db_alias}|{entry_row_id}"
        if form_row_id > 0:
            wire_key += f"|{form_row_id}"
        match_keys_by_wire[wire_key] = str(ref.get("match_key") or "")
        # Collect sqlite db stems so we can pass the exact db_paths to hydration.
        # The alias is the file stem (e.g. "zh-cc-cedict"), so the path is
        # SQLITE_DIR / f"{alias}.sqlite".
        if storage_kind != "custom" and db_alias and db_alias != "customdb":
            if db_alias not in allowed_sqlite_aliases:
                return jsonify(
                    {"ok": False, "error": f"Unsupported dictionary source: {db_alias}"}
                ), 400
            sqlite_stems.add(db_alias)

    from dict_lookup_sqlite import SQLITE_DIR as _SQLITE_DIR

    db_paths: list[Any] | None = None
    if sqlite_stems:
        resolved_paths = [_SQLITE_DIR / f"{stem}.sqlite" for stem in sqlite_stems]
        resolved_paths = [p for p in resolved_paths if p.exists()]
        if resolved_paths:
            db_paths = resolved_paths

    trace_token = None
    trace_payload = None
    payload_artifact = None
    if enable_debug_trace:
        trace_token, trace_state = start_trace(language=lang_code, capture_id=debug_capture_id)
        debug_capture_id = str(trace_state.get("debug_capture_id") or debug_capture_id)
    try:
        with trace_scope("js_hydrate", label="JS Hydrate", winner_ref_count=len(winner_refs)):
            hydrated = _hydrate(candidates, lang_code, db_paths=db_paths, trace=enable_debug_trace)

        entry_store: dict[str, Any] = {}
        # ref_to_key lets the JS client map its winner refs back to entry_store keys
        ref_to_key: dict[str, str] = {}
        # form_overlays: lightweight per-form display overrides keyed by form wire key
        form_overlays: dict[str, dict[str, Any]] = {}

        for (storage_kind, db_alias, entry_row_id), entry in hydrated.items():
            # Ensure source is set to the db stem so the client can scope
            # source-specific post-processing (e.g. pinyin conversion for cc-cedict).
            if not entry.get("source") and db_alias and db_alias != "customdb":
                entry["source"] = db_alias
            base_wire = f"{storage_kind}|{db_alias}|{entry_row_id}"
            match_key = str(match_keys_by_wire.get(base_wire) or "").strip()

            matched_forms = list(entry.get("_matched_forms") or [])
            is_form_match = str(entry.get("_match_kind") or "").strip().lower() == "form"

            if is_form_match and matched_forms:
                # Build ONE base payload for the entry (shared data: senses, forms, etymology).
                # Per-form display differences go into form_overlays.
                base_payload = _build_shared_base_payload(entry, match_key, lang_code)
                if not base_payload:
                    continue
                base_payload["ref_key"] = base_wire
                base_payload["runtime_entry_id"] = base_wire
                entry_store[base_wire] = base_payload
                ref_to_key[base_wire] = base_wire

                for mf in matched_forms:
                    form_row_id = int(mf.get("_form_row_id") or 0)
                    if not form_row_id:
                        continue
                    form_wire = f"{base_wire}|{form_row_id}"
                    ref_to_key[form_wire] = base_wire
                    form_overlays[form_wire] = _extract_form_overlay(entry, mf)
            else:
                # Headword match — one payload per entry
                if match_key:
                    entry["_match_key"] = match_key
                _shape_korean_synthetic_stem_entry(entry, match_key, lang_code)
                payload = _build_hydrated_display_payload(entry)
                if not payload:
                    continue
                payload_key = str(payload.get("ref_key") or base_wire).strip() or base_wire
                entry_store[payload_key] = payload
                ref_to_key[base_wire] = payload_key

        # Map any remaining form-variant wire keys not yet covered
        for ref in winner_refs:
            sk = str(ref.get("storage_kind") or "sqlite")
            alias = str(ref.get("db_alias") or "")
            eid = int(ref.get("entry_row_id") or 0)
            fid = int(ref.get("form_row_id") or 0)
            wire = f"{sk}|{alias}|{eid}" + (f"|{fid}" if fid > 0 else "")
            if wire not in ref_to_key:
                # Fall back to the base entry or any form payload for this entry
                base = f"{sk}|{alias}|{eid}"
                pk = ref_to_key.get(base)
                if pk:
                    ref_to_key[wire] = pk

        response_payload = {
            "ok": True,
            "entry_store": entry_store,
            "ref_to_key": ref_to_key,
            "form_overlays": form_overlays,
        }
        if enable_debug_trace:
            payload_artifact = store_debug_json_artifact(
                debug_capture_id,
                "sqlite_payload",
                response_payload,
                filename=f"sqlite-payload-{lang_code or 'lookup'}-{debug_capture_id}.json",
            )
            trace_payload = _prepare_debug_trace_payload(
                finish_trace(),
                request_kind="js_hydrate",
                label="JS Hydrate Request",
                payload_artifact=payload_artifact,
                drop_final_payload=True,
            )
    finally:
        if trace_token is not None:
            stop_trace(trace_token)

    if enable_debug_trace and isinstance(trace_payload, Mapping):
        _attach_sqlite_debug_trace_to_capture(
            capture_id=debug_capture_id,
            sqlite_debug_trace=trace_payload,
        )

    extra_headers = None
    if enable_debug_trace and isinstance(trace_payload, Mapping):
        extra_headers = {
            "X-Debug-Server-Ms": f"{float(trace_payload.get('total_ms') or 0.0):.3f}",
            "X-Debug-Request-Kind": str(trace_payload.get("request_kind") or "js_hydrate"),
        }
    return _lookup_json_response(response_payload, extra_headers=extra_headers)


@app.route("/js/dict/<lang_code>/index")
def js_dict_index(lang_code: str):
    """
    Compact key index for client-side DP segmentation.
    Returns gzip-compressed JSON: {v, lang, version, db_aliases, hw, fw}
    Disk-cached in runtime_cache/js_index/{lang}.json.gz; rebuilt when
    source .sqlite files are newer than the cache.
    Custom/Gemini entries are NOT included in the static cache — they are
    fetched separately by the client via /api/gemini_entry and injected
    into the in-memory index via injectGeminiKey().
    """
    import hashlib as _hashlib
    from dict_lookup_sqlite import build_compact_key_index, _resolve_db_path, _resolve_all_db_paths

    resolved = resolve_lang_code(lang_code.strip().lower())
    if not resolved:
        return jsonify({"ok": False, "error": f"Unsupported language: {lang_code}"}), 400

    source = request.args.get("source", "").strip().lower()
    if source and source not in ("custom",) and not _is_registered_dict_source(resolved, source):
        return jsonify(
            {"ok": False, "error": f"Unsupported dictionary source for {resolved}: {source}"}
        ), 404

    # Each index covers exactly one SQLite file — never bundle multiple dbs.
    if source and source not in ("custom",):
        db_path = _resolve_db_path(resolved, source)
        if not db_path:
            return jsonify({"ok": False, "error": f"No database for {resolved}:{source}"}), 404
        db_paths = [db_path]
    else:
        # No source specified: use the single default db for this language.
        all_paths = _resolve_all_db_paths(resolved)
        default = [p for p in all_paths if p.stem == resolved]
        db_paths = default if default else (all_paths[:1] if all_paths else [])
        if not db_paths:
            return jsonify({"ok": False, "error": f"No database for {resolved}"}), 404

    _JS_INDEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _js_index_cache_path(resolved, source)
    version = ""

    if _js_index_cache_is_fresh(
        resolved,
        cache_path,
        db_paths,
        include_custom_entries=False,
        expected_schema_version=_JS_INDEX_SCHEMA_VERSION,
    ):
        compressed = cache_path.read_bytes()
        version = _extract_version_from_gz(cache_path)
    else:
        # Cache miss (first boot or sqlite updated) — build and cache without custom entries.
        # Custom entries are injected client-side via /api/dict/<lang>/gemini after load.
        index = build_compact_key_index(resolved, db_paths=db_paths, include_custom_entries=False)
        index["v"] = _JS_INDEX_SCHEMA_VERSION
        index["lang"] = resolved
        if source:
            index["source"] = source
        body_bytes = json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        version = _hashlib.sha1(body_bytes).hexdigest()[:16]
        index["version"] = version
        body_bytes = json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        import gzip as _gz

        compressed = _gz.compress(body_bytes, compresslevel=6)
        try:
            cache_path.write_bytes(compressed)
        except Exception:
            pass

    ver_key = f"{resolved}:{source}" if source else resolved
    if version:
        _js_index_versions[ver_key] = version
    else:
        version = _js_index_versions.get(ver_key) or ""

    request_version = request.args.get("v", "").strip()
    is_versioned_request = bool(version) and request_version == version

    headers = {
        "Content-Type": "application/gzip",
        "Cache-Control": "public, max-age=31536000, immutable"
        if is_versioned_request
        else "public, max-age=3600",
    }
    if version:
        headers["ETag"] = f'"{version}"'
    return Response(compressed, status=200, headers=headers)


@app.route("/dict-index/<path:filename>")
def serve_js_index_artifact(filename: str):
    response = send_from_directory(
        _JS_INDEX_ARTIFACT_DIR,
        filename,
        mimetype="application/gzip",
        max_age=31536000,
    )
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.route("/tools/legacy_dep_tree_view.js")
def serve_legacy_dep_tree_view_js():
    response = send_from_directory(
        app.root_path,
        "dep_tree_view.js",
        mimetype="application/javascript",
        max_age=0,
    )
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/ping")
def ping():
    return jsonify({"ok": True, "msg": "neural_reader alive"})


# ---------------------------------------------------------------------------
# Startup — load everything eagerly
# ---------------------------------------------------------------------------

_startup_preloaded = False


# In-memory version map populated at startup: {"ja:jmdict": "abc123", "ar": "def456", ...}
_js_index_versions: dict[str, str] = {}
_js_index_urls: dict[str, str] = {}


def _extract_version_from_gz(cache_path: Path) -> str:
    """Read version from a cached gzip index file without rebuilding."""
    try:
        import gzip as _gz

        raw = json.loads(_gz.decompress(cache_path.read_bytes()).decode("utf-8"))
        return str(raw.get("version") or "")
    except Exception:
        return ""


def _prebuild_js_index_cache() -> None:
    """Pre-build one compact JS key index per language × source (never bundled).

    Each source maps to exactly one SQLite file; the index alias equals the
    file stem so it stays consistent between build-time and hydration-time.
    Languages with no dict_sources get a single index from their default db.
    """
    import gzip as _gz
    import hashlib as _hashlib
    from dict_lookup_sqlite import build_compact_key_index, _resolve_db_path, _resolve_all_db_paths

    _JS_INDEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _JS_INDEX_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _js_index_versions.clear()
    _js_index_urls.clear()
    built = skipped = failed = 0
    for code, info in LANGUAGE_REGISTRY.items():
        raw_sources = list((info.get("dict_sources") or {}).keys())
        # Filter out "custom" — custom entries are injected client-side, never indexed here.
        db_sources = [s for s in raw_sources if s and s != "custom"]
        # Languages with no named sources: build a single index from the default db.
        if not db_sources:
            db_sources = [""]

        for source in db_sources:
            ver_key = f"{code}:{source}" if source else code
            label = ver_key
            try:
                if source:
                    db_path = _resolve_db_path(code, source)
                    if not db_path:
                        print(f"[WARN] JS index: no db found for {label}, skipping")
                        continue
                    db_paths = [db_path]
                else:
                    # No named source: use the single default db only (not all dbs).
                    all_paths = _resolve_all_db_paths(code)
                    default = [p for p in all_paths if p.stem == code]
                    db_paths = default if default else (all_paths[:1] if all_paths else [])
                    if not db_paths:
                        continue

                cache_path = _js_index_cache_path(code, source)
                if _js_index_cache_is_fresh(
                    code,
                    cache_path,
                    db_paths,
                    include_custom_entries=False,
                    expected_schema_version=_JS_INDEX_SCHEMA_VERSION,
                ):
                    compressed = cache_path.read_bytes()
                    version = _extract_version_from_gz(cache_path)
                    skipped += 1
                else:
                    index = build_compact_key_index(
                        code, db_paths=db_paths, include_custom_entries=False
                    )
                    index["v"] = _JS_INDEX_SCHEMA_VERSION
                    index["lang"] = code
                    if source:
                        index["source"] = source
                    body_bytes = json.dumps(
                        index, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8")
                    version = _hashlib.sha1(body_bytes).hexdigest()[:16]
                    index["version"] = version
                    body_bytes = json.dumps(
                        index, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8")
                    compressed = _gz.compress(body_bytes, compresslevel=6)
                    cache_path.write_bytes(compressed)
                    built += 1
                    print(f"[INFO] JS index built: {label} ({len(compressed) // 1024} KB)")

                if not version:
                    raise RuntimeError(f"Missing version for prebuilt index {label}")
                artifact_name = _js_index_artifact_name(code, source, version)
                artifact_path = _JS_INDEX_ARTIFACT_DIR / artifact_name
                if not artifact_path.exists() or artifact_path.stat().st_size != len(compressed):
                    artifact_path.write_bytes(compressed)
                _js_index_versions[ver_key] = version
                _js_index_urls[ver_key] = f"/dict-index/{artifact_name}"
            except Exception as exc:
                failed += 1
                print(f"[WARN] JS index build failed for {label}: {type(exc).__name__}: {exc}")
    print(f"[INFO] JS index cache ready: {built} built, {skipped} skipped, {failed} failed")


@app.route("/js/dict/versions")
def js_dict_versions():
    """Return in-memory version map for all prebuilt indexes. Pure memory read, no I/O."""
    response = jsonify(_js_index_versions)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/js/dict/<lang>/version")
def js_dict_lang_version(lang):
    """Return version string for a single language index. Pure memory read, no I/O."""
    lang = lang.lower().strip()
    source = request.args.get("source", "").lower().strip()
    ver_key = f"{lang}:{source}" if source else lang
    version = _js_index_versions.get(ver_key, "")
    response = jsonify({"version": version})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


def preload_startup_resources():
    """Load all shared resources once when the server process starts."""
    global _startup_preloaded
    if _startup_preloaded:
        return
    print("[INFO] Pre-loading all resources...")
    init_all()
    _arabic_tokenizer_path = get_tokenizer_path("ar")
    if _arabic_tokenizer_path == "native":
        _arabic_tokenizer_label = "native Trankit"
    elif _arabic_tokenizer_path == "cameltools":
        _arabic_tokenizer_label = "CAMeL Tools"
    else:
        _arabic_tokenizer_label = _arabic_tokenizer_path
    print(f"[INFO] Arabic tokenizer path locked to: {_arabic_tokenizer_label}")
    print("[INFO] Arabic MWT expander locked to: disabled")
    print("[INFO] Pre-building JS compact key index cache...")
    _prebuild_js_index_cache()
    _startup_preloaded = True


preload_startup_resources()


if __name__ == "__main__":
    preload_startup_resources()
    print("[INFO] Starting Neural Reader server...")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
