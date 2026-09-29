"""Authenticated capture API; tokens identify records and do not grant access."""
import hmac
import secrets
from urllib.parse import urlsplit

from flask import Blueprint, Response, abort, current_app, jsonify, request, session, url_for
from flask_login import current_user

from .content import DOCUMENT_POLICY, sanitize_snapshot
from .store import CaptureTooLarge

capture_blueprint = Blueprint("captures", __name__)


def _owner():
    if not current_user.is_authenticated:
        abort(401)
    return str(current_user.get_id())


def _store():
    return current_app.extensions["captures"]


@capture_blueprint.after_request
def _private_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@capture_blueprint.get("/api/extension_capture_token")
def capture_token():
    _owner()
    if "capture_csrf" not in session:
        session["capture_csrf"] = secrets.token_urlsafe(32)
    return jsonify({"csrfToken": session["capture_csrf"]})


@capture_blueprint.route("/api/extension_capture", methods=["POST", "OPTIONS"])
def extension_capture_post():
    if request.method == "OPTIONS":
        return "", 204
    owner = _owner()
    expected = session.get("capture_csrf", "")
    provided = request.headers.get("X-CSRF-Token", "")
    if not expected or not hmac.compare_digest(expected, provided):
        abort(403)
    if not _store().allow_upload(owner):
        return jsonify({"ok": False, "error": "Capture upload rate exceeded"}), 429, {"Retry-After": "60"}
    # Enforce before parsing JSON, in addition to the decoded HTML limit.
    request.max_content_length = 2 * _store().max_bytes + 65536
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Expected a JSON object"}), 400
    html = payload.get("html")
    if not isinstance(html, str) or not html.strip():
        return jsonify({"ok": False, "error": "Missing 'html' field"}), 400
    if len(html.encode("utf-8")) > _store().max_bytes:
        return jsonify({"ok": False, "error": "Captured HTML exceeds the size limit"}), 413
    source = payload.get("url", "")
    source = source[:2048] if isinstance(source, str) else ""
    try:
        if urlsplit(source).scheme not in {"http", "https"}:
            source = ""
    except ValueError:
        source = ""
    title = payload.get("title", "Captured page")
    title = title[:512] if isinstance(title, str) else "Captured page"
    try:
        token = _store().put(owner, sanitize_snapshot(html), source, title)
    except CaptureTooLarge as exc:
        return jsonify({"ok": False, "error": str(exc)}), 413
    return jsonify({
        "ok": True, "token": token,
        "viewerUrl": url_for("captures.extension_snapshot_view", token=token, _external=True),
        "snapshotPayloadUrl": url_for("captures.extension_snapshot_payload", token=token, _external=True),
        "title": title, "url": source,
    })


def _record(token):
    record = _store().get(_owner(), token)
    if record is None:
        abort(404)
    return record


@capture_blueprint.get("/extension/snapshot/<token>")
def extension_snapshot_view(token):
    record = _record(token)
    response = Response(record.html, mimetype="text/html")
    response.headers["Content-Security-Policy"] = DOCUMENT_POLICY
    return response


@capture_blueprint.get("/api/extension_snapshot/<token>")
def extension_snapshot_payload(token):
    record = _record(token)
    return jsonify({"ok": True, "page": {
        "kind": "webSnapshot", "type": "webSnapshot", "html": record.html,
        "snapshot": {"requestedUrl": record.url, "finalUrl": record.url,
                     "title": record.title, "createdAt": record.created_at,
                     "htmlLength": len(record.html), "capture": "chrome-extension", "jsRendered": True},
    }})


@capture_blueprint.post("/api/monolith_snapshot")
def monolith_snapshot():
    return jsonify({"ok": False, "error": "URL snapshot capture is disabled"}), 410
