"""Private, inert HTML captures with bounded per-process storage."""
from .routes import capture_blueprint
from .store import CaptureStore


def init_captures(app):
    app.config.setdefault("CAPTURE_MAX_BYTES", 16 * 1024 * 1024)
    app.config.setdefault("CAPTURE_TOTAL_BYTES", 64 * 1024 * 1024)
    app.config.setdefault("CAPTURE_MAX_ITEMS", 16)
    app.config.setdefault("CAPTURE_TTL_SECONDS", 3600)
    app.config.setdefault("CAPTURE_UPLOADS_PER_MINUTE", 4)
    app.extensions["captures"] = CaptureStore(
        max_bytes=app.config["CAPTURE_MAX_BYTES"],
        total_bytes=app.config["CAPTURE_TOTAL_BYTES"],
        max_items=app.config["CAPTURE_MAX_ITEMS"],
        ttl=app.config["CAPTURE_TTL_SECONDS"],
        uploads_per_minute=app.config["CAPTURE_UPLOADS_PER_MINUTE"],
    )
    app.register_blueprint(capture_blueprint)
