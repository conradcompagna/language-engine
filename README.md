# Language Engine

**A deployed multilingual reading platform combining document reading, neural language analysis, and interactive dictionaries.**

I built Language Engine to bring close reading and language research into one workspace: open a document, select a passage, and inspect its vocabulary, grammar, and named entities without losing the original context.

[Live application](https://language-engine.ai) · [Setup](docs/SETUP.md) · [Architecture](docs/ARCHITECTURE.md) · [Portfolio](https://github.com/conradcompagna)

## Engineering highlights

- **Hybrid search architecture:** browser-side dynamic programming over compact lexical indexes; batch SQLite hydration fetches full entries only after candidate selection. IndexedDB caches indexes between sessions.
- **Multilingual neural inference:** Trankit integration, multi-word-token alignment, and a shared dynamic-INT8 ONNX encoder with language/task adapter inputs.
- **A complete reading interface:** PDF, ebook, Word, and web-page ingestion; dictionary popups, dependency trees, entity overlays, annotations, pronunciation, and contextual language assistance.
- **Product infrastructure:** Flask authentication, Google sign-in, Stripe subscriptions, server-side quotas and usage budgets, account management, and Gunicorn/Nginx deployment configuration.

## Scope

The code includes **27 language display configurations and enabled NLP registry entries**, covering modern and historical languages. The deployment uses 42 SQLite dictionary files; dictionary contents and model weights remain external to this repository.

## Explore the code

| Area | Starting point |
|---|---|
| HTTP application and accounts | [router.py](router.py), [auth.py](auth.py), [payments.py](payments.py) |
| Browser segmentation and hydration | [dictionary_client_hybrid.js](static/dictionary_client_hybrid.js) |
| Lexical indexes and SQLite access | [dict_lookup_sqlite.py](dict_lookup_sqlite.py) |
| Neural inference and alignment | [language_registry.py](language_registry.py), [pipeline_common.py](pipeline_common.py), [trankit_compressed_runtime.py](trankit_compressed_runtime.py) |
| Deployment | [wsgi.py](wsgi.py), [deploy/](deploy/) |

Model weights, dictionaries, and account data are provisioned separately. See [setup](docs/SETUP.md) and [publication contents](docs/PUBLICATION.md).
