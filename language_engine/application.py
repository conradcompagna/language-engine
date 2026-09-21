"""Construct the HTTP application; database and model setup are explicit steps."""

from flask import Flask
from flask_cors import CORS

from .http.settings import APP_DICT_VERSION, APP_ROOT


def _static_mtime(filename):
    try:
        return int((APP_ROOT / "static" / filename).stat().st_mtime)
    except OSError:
        return 0


def create_app(
    config=None,
    *,
    prepare_database=True,
    load_resources=True,
    resource_loader=None,
    nlp_runner=None,
):
    """Create an independent Flask app, optionally using fixture-only resources.

    Importing this module does not connect to a database or load a model.
    Production entrypoints use the defaults; tests supply an isolated database
    and disable model loading. A resource_loader callback can initialize an
    authorized model adapter without changing route registration.
    """
    import config as le_config
    from auth import auth_bp, login_manager
    from db import db
    from payments import payments_bp

    from .captures import init_captures
    from .http import register_routes

    app = Flask(
        "language_engine",
        root_path=str(APP_ROOT),
        template_folder=str(APP_ROOT / "templates"),
        static_folder=str(APP_ROOT / "static"),
    )
    app.config.update(
        JSON_AS_ASCII=False,
        SECRET_KEY=le_config.SECRET_KEY,
        SQLALCHEMY_DATABASE_URI=le_config.DATABASE_URL,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        REMEMBER_COOKIE_DURATION=60 * 60 * 24 * 30,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(le_config.IS_PRODUCTION),
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=bool(le_config.IS_PRODUCTION),
        PREFERRED_URL_SCHEME="https" if le_config.IS_PRODUCTION else "http",
        MAX_CONTENT_LENGTH=500 * 1024 * 1024,
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )
    if config is not None:
        app.config.update(config)
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
    app.jinja_env.globals.update(
        mtime=_static_mtime,
        app_dict_version=APP_DICT_VERSION,
        public_base_url=le_config.APP_BASE_URL,
    )
    db.init_app(app)
    login_manager.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(payments_bp)
    init_captures(app)
    register_routes(app)
    if nlp_runner is not None:
        app.extensions["language_engine.nlp_runner"] = nlp_runner

    if prepare_database:
        from .database import initialize_database

        initialize_database(app)
    if load_resources:
        if resource_loader is not None:
            resource_loader(app)
        else:
            from .http.startup import preload_startup_resources

            preload_startup_resources()
    return app
