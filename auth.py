"""
auth.py — Flask blueprint for user authentication.

Endpoints:
  POST /auth/signup          — create account (email + password)
  POST /auth/login           — sign in
  POST /auth/forgot-password — email password reset link
  POST /auth/reset-password  — reset password from emailed token
  POST /auth/change-password — update password while signed in
  POST /auth/change-email/request — update account email while signed in
  GET  /auth/verify-email    — verify a new email/password account
  POST /auth/delete-account  — delete account and private account metadata
  POST /auth/logout          — sign out
  GET  /auth/me              — current user info (JSON)
  GET  /auth/google/login    — redirect to Google OAuth
  GET  /auth/google/callback — handle Google OAuth callback
"""

import datetime
import dns.resolver
import hashlib
import json
import secrets
import smtplib
from email.message import EmailMessage
from email.utils import formatdate
from urllib.parse import urlencode

from flask import Blueprint, request, jsonify, redirect, url_for, session
from flask_login import LoginManager, login_user, logout_user, current_user, login_required

from db import db, User, Subscription, LookupQuota, ApiUsage, AccountActionToken

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ---------------------------------------------------------------------------
# Flask-Login setup (called from router.py)
# ---------------------------------------------------------------------------
login_manager = LoginManager()
login_manager.login_view = "/"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Account email actions
# ---------------------------------------------------------------------------

PASSWORD_RESET_PURPOSE = "password_reset"
EMAIL_CHANGE_PURPOSE = "email_change"
EMAIL_VERIFY_PURPOSE = "email_verify"


def _utcnow():
    return datetime.datetime.utcnow()


def _token_hash(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _base_url():
    from config import APP_BASE_URL

    if APP_BASE_URL:
        return APP_BASE_URL
    return request.host_url.rstrip("/")


def _absolute_url(path):
    return _base_url() + path


def _email_domain_has_mx(email):
    parts = str(email or "").rsplit("@", 1)
    if len(parts) != 2:
        return False
    domain = parts[1].strip().strip(".").lower()
    if not domain:
        return False
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
    except Exception:
        return False
    return any(str(answer.exchange).strip().strip(".") for answer in answers)


def _create_action_token(user_id, purpose, payload=None, ttl_hours=2):
    raw = secrets.token_urlsafe(32)
    row = AccountActionToken(
        user_id=user_id,
        purpose=purpose,
        token_hash=_token_hash(raw),
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
        expires_at=_utcnow() + datetime.timedelta(hours=ttl_hours),
    )
    db.session.add(row)
    db.session.commit()
    return raw


def _load_action_token(raw_token, purpose):
    row = AccountActionToken.query.filter_by(
        token_hash=_token_hash(raw_token),
        purpose=purpose,
    ).first()
    if not row or row.used_at is not None or row.expires_at < _utcnow():
        return None, {}
    try:
        payload = json.loads(row.payload_json or "{}")
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return row, payload


def _send_account_email(to_email, subject, body):
    import config as le_config

    if not le_config.SMTP_HOST:
        raise RuntimeError("SMTP is not configured.")

    msg = EmailMessage()
    msg["To"] = to_email
    msg["From"] = le_config.SMTP_FROM_EMAIL
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(le_config.SMTP_HOST, le_config.SMTP_PORT, timeout=15) as smtp:
        if le_config.SMTP_USE_TLS:
            smtp.starttls()
        if le_config.SMTP_USERNAME:
            smtp.login(le_config.SMTP_USERNAME, le_config.SMTP_PASSWORD)
        smtp.send_message(msg)


def _send_verification_email(user, token):
    verify_url = _absolute_url("/auth/verify-email?" + urlencode({"token": token}))
    body = (
        "Verify your Language Engine email address with this link:\n\n"
        f"{verify_url}\n\n"
        "This link expires in 24 hours. If you did not create an account, you can ignore this email."
    )
    _send_account_email(user.email, "Verify your Language Engine email", body)


def _create_verification_token(user):
    raw_token = secrets.token_urlsafe(32)
    token_row = AccountActionToken(
        user_id=user.id,
        purpose=EMAIL_VERIFY_PURPOSE,
        token_hash=_token_hash(raw_token),
        payload_json="{}",
        expires_at=_utcnow() + datetime.timedelta(hours=24),
    )
    db.session.add(token_row)
    return raw_token


# ---------------------------------------------------------------------------
# Email / password auth
# ---------------------------------------------------------------------------


@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "Invalid email address."}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "error": "Password must be at least 8 characters."}), 400
    if not _email_domain_has_mx(email):
        return jsonify({"ok": False, "error": "Email domain cannot receive mail."}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"ok": False, "error": "An account with this email already exists."}), 409

    user = User(username=email, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    quota = LookupQuota(user_id=user.id)
    db.session.add(quota)
    raw_token = _create_verification_token(user)

    try:
        _send_verification_email(user, raw_token)
    except Exception as exc:
        db.session.rollback()
        return jsonify(
            {"ok": False, "error": f"Could not send verification email: {type(exc).__name__}"}
        ), 500

    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "message": "Check your email for a verification link.",
        }
    )


@auth_bp.route("/resend-verification", methods=["POST"])
def resend_verification():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "Invalid email address."}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.password_hash or user.email_verified_at:
        return jsonify(
            {"ok": True, "message": "If this account needs verification, a new link has been sent."}
        )

    raw_token = _create_verification_token(user)
    try:
        _send_verification_email(user, raw_token)
    except Exception as exc:
        db.session.rollback()
        return jsonify(
            {"ok": False, "error": f"Could not send verification email: {type(exc).__name__}"}
        ), 500
    db.session.commit()
    return jsonify({"ok": True, "message": "Verification email sent."})


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"ok": False, "error": "Invalid email or password."}), 401
    if user.password_hash and not user.email_verified_at:
        return jsonify(
            {"ok": False, "error": "Check your email to verify your account before signing in."}
        ), 403

    login_user(user, remember=True)
    return jsonify(
        {
            "ok": True,
            "user": {"id": user.id, "email": user.email},
        }
    )


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "Invalid email address."}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.password_hash:
        return jsonify({"ok": True})

    token = _create_action_token(user.id, PASSWORD_RESET_PURPOSE, ttl_hours=2)
    reset_url = _absolute_url("/?" + urlencode({"reset_token": token}))
    body = (
        "Reset your Language Engine password with this link:\n\n"
        f"{reset_url}\n\n"
        "This link expires in 2 hours. If you did not request it, you can ignore this email."
    )
    try:
        _send_account_email(user.email, "Reset your Language Engine password", body)
    except Exception as exc:
        return jsonify(
            {"ok": False, "error": f"Could not send reset email: {type(exc).__name__}"}
        ), 500
    return jsonify({"ok": True})


@auth_bp.route("/verify-email")
def verify_email():
    token = (request.args.get("token") or "").strip()
    row, _payload = _load_action_token(token, EMAIL_VERIFY_PURPOSE)
    if not row:
        return redirect("/?email_verify=invalid")

    user = db.session.get(User, row.user_id)
    if not user:
        return redirect("/?email_verify=invalid")

    user.email_verified_at = _utcnow()
    row.used_at = _utcnow()
    db.session.commit()
    return redirect("/?email_verified=1")


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    password = data.get("password") or ""
    if len(password) < 8:
        return jsonify({"ok": False, "error": "Password must be at least 8 characters."}), 400

    row, _payload = _load_action_token(token, PASSWORD_RESET_PURPOSE)
    if not row:
        return jsonify({"ok": False, "error": "This reset link is invalid or expired."}), 400

    user = db.session.get(User, row.user_id)
    if not user:
        return jsonify({"ok": False, "error": "This reset link is invalid or expired."}), 400

    user.set_password(password)
    row.used_at = _utcnow()
    db.session.commit()
    return jsonify({"ok": True})


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    if not current_user.password_hash:
        return jsonify({"ok": False, "error": "This account uses Google sign-in."}), 400

    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""
    if not current_user.check_password(current_password):
        return jsonify({"ok": False, "error": "Current password is incorrect."}), 400
    if len(new_password) < 8:
        return jsonify({"ok": False, "error": "New password must be at least 8 characters."}), 400

    current_user.set_password(new_password)
    db.session.commit()
    return jsonify({"ok": True})


@auth_bp.route("/change-email/request", methods=["POST"])
@login_required
def change_email_request():
    if not current_user.password_hash:
        return jsonify({"ok": False, "error": "This account uses Google sign-in."}), 400

    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or ""
    new_email = (data.get("new_email") or "").strip().lower()
    if not current_user.check_password(current_password):
        return jsonify({"ok": False, "error": "Current password is incorrect."}), 400
    if not new_email or "@" not in new_email:
        return jsonify({"ok": False, "error": "Invalid email address."}), 400
    if new_email == current_user.email:
        return jsonify({"ok": False, "error": "That is already your account email."}), 400
    if User.query.filter_by(email=new_email).first():
        return jsonify({"ok": False, "error": "An account with this email already exists."}), 409

    token = _create_action_token(
        current_user.id,
        EMAIL_CHANGE_PURPOSE,
        payload={"email": new_email},
        ttl_hours=24,
    )
    confirm_url = _absolute_url("/auth/change-email/confirm?" + urlencode({"token": token}))
    body = (
        "Confirm your new Language Engine email address with this link:\n\n"
        f"{confirm_url}\n\n"
        "This link expires in 24 hours. If you did not request it, you can ignore this email."
    )
    try:
        _send_account_email(new_email, "Confirm your Language Engine email", body)
    except Exception as exc:
        return jsonify(
            {"ok": False, "error": f"Could not send confirmation email: {type(exc).__name__}"}
        ), 500
    return jsonify({"ok": True})


@auth_bp.route("/change-email/confirm")
def change_email_confirm():
    token = (request.args.get("token") or "").strip()
    row, payload = _load_action_token(token, EMAIL_CHANGE_PURPOSE)
    new_email = (payload.get("email") or "").strip().lower()
    if not row or not new_email:
        return redirect("/account?email_change=invalid")

    user = db.session.get(User, row.user_id)
    if not user:
        return redirect("/account?email_change=invalid")
    existing = User.query.filter_by(email=new_email).first()
    if existing and existing.id != user.id:
        return redirect("/account?email_change=taken")

    user.email = new_email
    user.username = new_email
    row.used_at = _utcnow()
    db.session.commit()
    return redirect("/account?email_changed=1")


def _account_deletion_blocker(user):
    sub = user.subscription
    if not sub:
        return None
    live_billing_statuses = {"active", "trialing", "past_due", "unpaid", "incomplete"}
    if sub.status in live_billing_statuses and not sub.cancel_at_period_end:
        return "Cancel your subscription from Manage Subscription before deleting this account."
    return None


@auth_bp.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    data = request.get_json(silent=True) or {}
    confirm_email = (data.get("confirm_email") or "").strip().lower()
    current_password = data.get("current_password") or ""

    if confirm_email != (current_user.email or "").lower():
        return jsonify({"ok": False, "error": "Type your account email to confirm deletion."}), 400
    if current_user.password_hash and not current_user.check_password(current_password):
        return jsonify({"ok": False, "error": "Current password is incorrect."}), 400

    deletion_error = _account_deletion_blocker(current_user)
    if deletion_error:
        db.session.rollback()
        return jsonify({"ok": False, "error": deletion_error}), 400

    user_id = int(current_user.id)
    user = db.session.get(User, user_id)

    # Account rows are private metadata and should disappear with the account.
    LookupQuota.query.filter_by(user_id=user_id).delete()
    ApiUsage.query.filter_by(user_id=user_id).delete()
    Subscription.query.filter_by(user_id=user_id).delete()

    from sqlalchemy import text

    def table_exists(name):
        return (
            db.session.execute(
                text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
                {"name": name},
            ).first()
            is not None
        )

    def column_exists(table, column):
        if not table_exists(table):
            return False
        rows = db.session.execute(text(f"PRAGMA table_info({table})")).mappings().all()
        return any(row.get("name") == column for row in rows)

    def exec_sql(table, sql, required_column=None, **params):
        if not table_exists(table):
            return
        if required_column and not column_exists(table, required_column):
            return
        db.session.execute(text(sql), params)

    exec_sql(
        "account_action_tokens",
        "DELETE FROM account_action_tokens WHERE user_id = :user_id",
        user_id=user_id,
    )
    exec_sql(
        "custom_entry_deletion_votes",
        "DELETE FROM custom_entry_deletion_votes WHERE user_id = :user_id",
        user_id=user_id,
    )
    exec_sql(
        "gemini_deletion_votes",
        "DELETE FROM gemini_deletion_votes WHERE user_id = :user_id",
        user_id=user_id,
    )
    exec_sql(
        "gemini_entry_owners",
        "DELETE FROM gemini_entry_owners WHERE user_id = :user_id",
        user_id=user_id,
    )
    exec_sql(
        "synthetic_annotations",
        "DELETE FROM synthetic_annotations WHERE user_id = :user_id",
        user_id=user_id,
    )
    exec_sql(
        "user_annotations", "DELETE FROM user_annotations WHERE user_id = :user_id", user_id=user_id
    )
    exec_sql(
        "user_dict_entries",
        "DELETE FROM user_dict_entries WHERE user_id = :user_id",
        user_id=user_id,
    )

    # Shared app/community content stays, but any stale account attribution is removed.
    exec_sql(
        "custom_dict_entries",
        "UPDATE custom_dict_entries SET owner_user_id = NULL WHERE owner_user_id = :user_id",
        required_column="owner_user_id",
        user_id=user_id,
    )
    exec_sql(
        "entry_notes",
        "UPDATE entry_notes SET user_id = NULL WHERE user_id = :user_id",
        required_column="user_id",
        user_id=user_id,
    )
    exec_sql(
        "entry_decomps",
        "UPDATE entry_decomps SET user_id = NULL WHERE user_id = :user_id",
        required_column="user_id",
        user_id=user_id,
    )

    logout_user()
    if user:
        db.session.delete(user)
    db.session.commit()
    return jsonify({"ok": True})


@auth_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    return jsonify({"ok": True})


@auth_bp.route("/me")
def me():
    if current_user.is_authenticated:
        return jsonify(
            {
                "ok": True,
                "user": {
                    "id": current_user.id,
                    "email": current_user.email,
                    "is_subscribed": current_user.is_subscribed,
                    "tier": current_user.tier,
                    "has_password": bool(current_user.password_hash),
                    "password_length": current_user.password_length
                    if current_user.password_hash
                    else None,
                },
            }
        )
    return jsonify({"ok": False})


# ---------------------------------------------------------------------------
# Google OAuth
# Falls back gracefully if credentials aren't configured.
# ---------------------------------------------------------------------------

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


def _public_url(endpoint):
    from config import APP_BASE_URL

    if APP_BASE_URL:
        return APP_BASE_URL + url_for(endpoint)
    return url_for(endpoint, _external=True)


def _safe_next_url(value):
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return ""


@auth_bp.route("/google/login")
def google_login():
    from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return jsonify({"ok": False, "error": "Google OAuth is not configured."}), 501

    redirect_uri = _public_url("auth.google_callback")
    import requests as _req

    google_cfg = _req.get(GOOGLE_DISCOVERY_URL, timeout=10).json()
    auth_endpoint = google_cfg["authorization_endpoint"]

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    next_url = _safe_next_url(request.args.get("next", ""))
    if next_url:
        session["oauth_next"] = next_url
    authorization_url = (
        auth_endpoint
        + "?"
        + urlencode(
            {
                "client_id": GOOGLE_CLIENT_ID,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "prompt": "select_account",
            }
        )
    )
    return redirect(authorization_url)


@auth_bp.route("/google/callback")
def google_callback():
    from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return redirect("/")

    expected_state = session.pop("oauth_state", None)
    if not expected_state or request.args.get("state") != expected_state:
        return redirect("/")

    code = request.args.get("code")
    if not code:
        return redirect("/")

    import requests as _req

    redirect_uri = _public_url("auth.google_callback")

    google_cfg = _req.get(GOOGLE_DISCOVERY_URL, timeout=10).json()
    token_endpoint = google_cfg["token_endpoint"]

    token_resp = _req.post(
        token_endpoint,
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    token_resp.raise_for_status()
    access_token = token_resp.json().get("access_token")
    if not access_token:
        return redirect("/")

    userinfo_endpoint = google_cfg["userinfo_endpoint"]
    resp = _req.get(
        userinfo_endpoint,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    info = resp.json()

    google_id = info.get("sub")
    email = (info.get("email") or "").lower()

    # Find or create user
    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            # Link Google to existing email account
            user.google_id = google_id
            if not user.email_verified_at:
                user.email_verified_at = _utcnow()
        else:
            # New user
            user = User(
                username=email, email=email, google_id=google_id, email_verified_at=_utcnow()
            )
            db.session.add(user)
            db.session.flush()
            quota = LookupQuota(user_id=user.id)
            db.session.add(quota)

    db.session.commit()
    login_user(user, remember=True)
    return redirect(session.pop("oauth_next", None) or "/reader")
