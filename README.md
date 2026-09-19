# Language Engine

**A deployed multilingual reading platform combining document reading, neural language analysis, and interactive dictionaries.**

I built Language Engine to bring close reading and language research into one workspace: open a document, select a passage, and inspect its vocabulary, grammar, and named entities without losing the original context.

[Live application](https://language-engine.ai) · [Setup](docs/SETUP.md) · [Architecture](docs/ARCHITECTURE.md) · [Portfolio](https://github.com/conradcompagna)

[![Checks](https://github.com/conradcompagna/language-engine/actions/workflows/checks.yml/badge.svg)](https://github.com/conradcompagna/language-engine/actions/workflows/checks.yml)

## Engineering highlights

- **Hybrid search architecture:** browser-side dynamic programming over compact lexical indexes; batch SQLite hydration fetches full entries only after candidate selection. IndexedDB caches indexes between sessions.
- **Multilingual neural inference:** Trankit integration, multi-word-token alignment, and a shared dynamic-INT8 ONNX encoder with language/task adapter inputs.
- **A complete reading interface:** PDF, ebook, Word, and web-page ingestion; dictionary popups, dependency trees, entity overlays, annotations, pronunciation, and contextual language assistance.
- **Product infrastructure:** Flask authentication, Google sign-in, Stripe subscriptions, server-side quotas and usage budgets, account management, and Gunicorn/Nginx deployment configuration.

## Scope

The code includes **34 language display configurations and 27 enabled NLP registry entries**, covering modern and historical languages. The deployment uses 42 SQLite dictionary files; dictionary contents and model weights remain external to this repository.

## Explore the code

| Area | Starting point |
|---|---|
| HTTP application and accounts | [router.py](router.py), [auth.py](auth.py), [payments.py](payments.py) |
| Browser segmentation and hydration | [dictionary_client_hybrid.js](static/dictionary_client_hybrid.js) |
| Lexical indexes and SQLite access | [dict_lookup_sqlite.py](dict_lookup_sqlite.py) |
| Neural inference and alignment | [language_registry.py](language_registry.py), [pipeline_common.py](pipeline_common.py), [trankit_compressed_runtime.py](trankit_compressed_runtime.py) |
| Runtime regression checks | [tests/](tests/) |
| Deployment | [wsgi.py](wsgi.py), [deploy/](deploy/) |

## Run the lightweight checks

```sh
python -m tests.test_mwt_realign_dp
```

This regression runs without model weights or dictionaries. CI also checks Python formatting, undefined names, and JavaScript syntax. See [setup](docs/SETUP.md) for the resources required to run the application and [publication contents](docs/PUBLICATION.md) for the data boundary.
