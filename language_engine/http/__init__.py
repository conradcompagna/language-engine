"""HTTP features registered explicitly by the application factory."""


def register_routes(app):
    from .language_config import bp as language_config_bp

    app.register_blueprint(language_config_bp)
    from .custom_entries import bp as custom_entries_bp

    app.register_blueprint(custom_entries_bp)
    from .pages import bp as pages_bp

    app.register_blueprint(pages_bp)
    from .quotas import bp as quotas_bp

    app.register_blueprint(quotas_bp)
    from .contact import bp as contact_bp

    app.register_blueprint(contact_bp)
    from .lookup import bp as lookup_bp

    app.register_blueprint(lookup_bp)
    from .llm import bp as llm_bp

    app.register_blueprint(llm_bp)
    from .custom_index import bp as custom_index_bp

    app.register_blueprint(custom_index_bp)
    from .diagnostics import bp as diagnostics_bp

    app.register_blueprint(diagnostics_bp)
    from .entry_notes import bp as entry_notes_bp

    app.register_blueprint(entry_notes_bp)
    from .decompositions import bp as decompositions_bp

    app.register_blueprint(decompositions_bp)
    from .preferences import bp as preferences_bp

    app.register_blueprint(preferences_bp)
    from .dictionary_downloads import bp as dictionary_downloads_bp

    app.register_blueprint(dictionary_downloads_bp)
    from .dictionary_sources import bp as dictionary_sources_bp

    app.register_blueprint(dictionary_sources_bp)
    from .dictionary_index import bp as dictionary_index_bp

    app.register_blueprint(dictionary_index_bp)
    from .health import bp as health_bp

    app.register_blueprint(health_bp)
    from .startup import bp as startup_bp

    app.register_blueprint(startup_bp)
    from .pages import _add_private_route_noindex
    from .policy import _enforce_paid_feature_gate

    app.before_request(_enforce_paid_feature_gate)
    app.after_request(_add_private_route_noindex)
