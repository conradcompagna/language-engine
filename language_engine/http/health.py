"""Reader HTTP health."""

from flask import Blueprint, jsonify

bp = Blueprint("health", __name__)


@bp.route("/ping")
def ping():
    return jsonify({"ok": True, "msg": "neural_reader alive"})
