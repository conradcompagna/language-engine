"""Compatibility entrypoint for Language Engine's application factory."""
from language_engine.application import create_app
from language_engine.http.startup import preload_startup_resources

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
