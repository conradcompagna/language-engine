"""Reader HTTP preferences."""

from flask import Blueprint, jsonify

bp = Blueprint("preferences", __name__)


@bp.route("/api/user/preferences", methods=["GET", "POST"])
def user_preferences():
    """Legacy sharing-preferences endpoint. Content no longer has account ownership."""
    return jsonify({"ok": True})
