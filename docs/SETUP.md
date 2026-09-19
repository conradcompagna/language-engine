# Setup and external resources

This is a source publication of a deployed application. A fresh clone does not include the trained NLP models or dictionary contents needed for lookup.

## Runtime

Use Python 3.12 and Node.js. From the repository root:

```sh
python -m venv .venv
python -m pip install -r requirements.txt
```

Activate `.venv` before installing or running commands. Copy `.env.example` to `.env` and supply your own configuration. Generate a session secret with `python -c "import secrets; print(secrets.token_hex(32))"`.

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

## Preparation and validation

`tools/dictionaries/convert_tsv_to_sqlite.py` contains the dictionary importer. Run it from the repository root as `python -m tools.dictionaries.convert_tsv_to_sqlite <language>` after providing the configured input TSV. `training/` contains corpus conversion, model training, evaluation, and upstream-patch infrastructure. The ONNX builders require their training resources plus ONNX tooling; the runtime requirements alone do not provide every research dependency.

Run the model-free regression with `python -m tests.test_mwt_realign_dp`. For the same authored-code checks as CI, install `ruff==0.16.8`, then run `ruff check .` and `ruff format --check .`. The linter selects undefined names and invalid exports; it is not a full security audit.

Full NLP, document, authentication, and billing integration checks require external resources and independently configured test services. No account records, model weights, or dictionary data are bundled.
