# Setup and external resources

This source release contains the application and its model/dictionary build infrastructure. To run your own instance, provision the NLP models and dictionaries below, then configure the application environment.

## Runtime

Use Python 3.12 and Node.js 22 or newer. From the repository root:

```sh
python -m venv .venv
python -m pip install -r requirements.txt
npm ci --ignore-scripts
npm run build
```

Activate `.venv` before installing or running commands. Copy `.env.example` to `.env` and supply your own configuration. Generate a session secret with `python -c "import secrets; print(secrets.token_hex(32))"`.

The browser sources are in [`frontend/`](../frontend/README.md); the build creates
the existing static script URLs. Run it again after browser changes. For a local
demo without models, dictionaries, credentials or production services, run
`node tests/browser/fixture-server.mjs` and open `http://127.0.0.1:8791`.

Required resources:

| Resource | Expected location / control |
|---|---|
| SQLite dictionaries | `dict_sqlite/*.sqlite` |
| Compressed shared encoder and adapter packs | `.trankit_compressed_runtime/`, including `manifest.json` |
| Japanese NER training output | `training/trankit_save_ja_ner_v2/` |
| Other model resources | Paths selected by `language_registry.py` and the compressed-runtime manifest |
| Account database | `LE_DATABASE_URL`; use a new database for your installation |

`tools/normalize_keys.js` is a runtime dependency; keep Node.js available. Python dependencies install packages, not the private dictionary/model artifacts.

On Linux, after supplying resources and configuring the environment:

```sh
gunicorn wsgi:app --bind 127.0.0.1:5000 --workers 1 --threads 4 --timeout 300
```

`deploy/` provides service and reverse-proxy templates. Set your own domain, paths, credentials, and operational settings. These are templates, not a deployment command to run against the original website.

Running the full application requires the external resources above. Account and billing features also require independently configured service credentials.
