# Architecture

## Reading and lookup

```mermaid
flowchart LR
    Text[Selected document text] --> NLP[Flask / Trankit]
    NLP --> DP[Browser DP segmentation]
    Index[Compact key index / IndexedDB] --> DP
    DP --> Hydrate[Batch SQLite hydration]
    Hydrate --> Reader[Dictionary and grammar overlays]
```

`templates/reader_jshybrid.html` loads the reader. `static/dictionary_client_hybrid.js` intercepts the main `/lookup` request, combines the server's NLP output with client-side segmentation, and requests selected entries from `/js/hydrate`. Side-panel lookup uses the same lexical engine without a new neural parse.

`dict_lookup_sqlite.py` builds compact indexes and retrieves dictionary rows. `tools/normalize_keys.js` supplies the JavaScript normalization used during indexing and is a runtime dependency. `sqlite_prune_policy.py` supplies the shared entry-pruning policy.

`pipeline_common.py` handles NLP results, including the alignment of expanded multi-word tokens back to the selected surface text. `language_registry.py` selects models and loads language display configurations from `wiktionary_general/`. Arabic uses Trankit's native tokenizer. Compressed encoder execution is implemented in `trankit_compressed_runtime.py` and `trankit_onnx_live_switch.py`.

## Application boundaries

`language_engine.application.create_app()` composes the Flask application; importing
the factory does not initialize a database or load a model. `router.py` and
`wsgi.py` retain the server entrypoints and use production initialization defaults.
`language_engine/database.py` contains the existing compatibility migrations.

`language_engine/http/` separates lookup, dictionary indexes/downloads, hydration
serializers, custom entries, notes/decomposition, quotas, pages and startup.
HTTP URLs and response shapes remain compatible; Flask endpoint names now include
their blueprint (for example, `pages.account_page`). The paid-feature gate checks
the endpoint's function name after removing that prefix.

Tests pass `prepare_database=False` and `load_resources=False`, create an isolated
SQLite database, and inject `nlp_runner` when exercising lookup. A `resource_loader`
callback can replace production initialization. The production language registry
and immutable dictionary index version maps remain process-wide shared caches;
factories are not a way to run incompatible model registries in one process.

`auth.py`, `payments.py`, and `db.py` implement identity, subscription state, and persistence. `api_services.py` and `gemini_dict.py` enforce usage budgets around contextual assistance and generated dictionary entries.

Dictionary-only lookups run in the browser through the shared hybrid engine; the server hydrates the selected entries.

## Repository layout

The root retains server compatibility entrypoints and existing focused services.
`language_engine/` owns HTTP composition, capture security and Gemini task services.
`frontend/` contains maintained browser modules and ordered stylesheets; `npm run
build` produces the existing public URLs in `static/`. `templates/` contains the
HTML interface; `deploy/` contains hosting templates. `tools/normalize_keys.js`
supplies runtime key normalization. Models and dictionary data are provisioned separately.

`static/foliate-js/` contains the ebook renderer and its browser dependencies. `static/docrender/lookup_chunks.js` groups page geometry into paragraph boundaries during PDF and web-snapshot extraction.
