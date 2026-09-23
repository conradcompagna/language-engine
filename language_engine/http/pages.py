"""Reader HTTP pages."""

import secrets as _ext_secrets
from xml.sax.saxutils import escape as _xml_escape

from flask import (
    Blueprint,
    Response,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
)
from flask_login import current_user

import config as le_config

from .startup import _js_index_urls

bp = Blueprint("pages", __name__)

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


def _add_private_route_noindex(response):
    path = request.path.rstrip("/") or "/"
    if path in _NOINDEX_EXACT_PATHS or request.path.startswith(_NOINDEX_PREFIXES):
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@bp.route("/robots.txt")
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


@bp.route("/sitemap.xml")
def sitemap_xml():
    base = _xml_escape(_site_base_url())
    urls = [
        f"{base}/",
        f"{base}/chrome-extension",
    ]
    items = "\n".join(f"  <url><loc>{url}</loc></url>" for url in urls)
    body = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{items}\n</urlset>\n'
    return Response(body, mimetype="application/xml; charset=utf-8")


@bp.route("/")
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


@bp.route("/chrome-extension")
def chrome_extension_page():
    return redirect(
        "https://chromewebstore.google.com/detail/language-engine-capture/moljdhkmokgdglimghgkenhbeccpognn"
    )


@bp.route("/reader", methods=["GET"])
def reader_page():
    return render_template(
        "reader_jshybrid.html",
        js_index_urls=dict(_js_index_urls),
    )


@bp.route("/account")
def account_page():
    if not current_user.is_authenticated:
        return redirect("/")
    return render_template("account.html")


@bp.route("/about")
def about_page():
    if not current_user.is_authenticated:
        return redirect("/")
    return render_template("about.html")


@bp.route("/contact")
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


@bp.route("/admin/analytics")
def admin_analytics_page():
    if not _is_admin_user():
        return (
            redirect("/") if not current_user.is_authenticated else ("Forbidden", 403)
        )
    try:
        days = int(request.args.get("days") or 30)
    except (TypeError, ValueError):
        days = 30
    from analytics import admin_summary

    return render_template(
        "admin_analytics.html", analytics=admin_summary(days), days=days
    )


@bp.route("/admin/analytics.json")
def admin_analytics_json():
    if not _is_admin_user():
        return jsonify({"ok": False, "error": "Forbidden"}), 403
    try:
        days = int(request.args.get("days") or 30)
    except (TypeError, ValueError):
        days = 30
    from analytics import admin_summary

    return jsonify(admin_summary(days))
