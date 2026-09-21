"""Reader HTTP contact."""

import re
import smtplib
from email.message import EmailMessage
from email.utils import formatdate
from typing import Any, Mapping

from flask import (
    Blueprint,
    jsonify,
    request,
)
from flask_login import current_user

import config as le_config

bp = Blueprint("contact", __name__)


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
    email["Subject"] = _contact_header(
        f"Language Engine contact: {contact_type} - {subject}"
    )
    if user_email:
        email["Reply-To"] = user_email
    email.set_content("\n".join(lines))

    with smtplib.SMTP(le_config.SMTP_HOST, le_config.SMTP_PORT, timeout=15) as smtp:
        if le_config.SMTP_USE_TLS:
            smtp.starttls()
        if le_config.SMTP_USERNAME:
            smtp.login(le_config.SMTP_USERNAME, le_config.SMTP_PASSWORD)
        smtp.send_message(email)


@bp.route("/api/contact", methods=["POST"])
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
