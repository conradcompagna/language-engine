# Preparation and operations

Run Python tools as modules from the repository root so imports resolve against the application.

| Directory | Role |
|---|---|
| `dictionaries/` | TSV/JSONL/XML conversion, SQLite construction, normalization, and dictionary audits |
| `models/` | Trankit setup, patch application, compressed ONNX artifacts, and session tuning |
| `operations/` | Explicit account-quota maintenance |

For example, `python -m tools.dictionaries.convert_tsv_to_sqlite ja` imports the configured Japanese TSV into `dict_sqlite/`. Supply the input file configured by `language_registry.py` first. Importers and maintenance commands write local data; inspect their arguments and selected paths before running them.

`normalize_keys.js` is used by the running dictionary system and must ship with the application. It is not an offline conversion script.
