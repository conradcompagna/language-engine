# Gemini services

Contextual language tasks are organized into focused services with explicit
imports. The root `gemini_dict.py` facade exposes their public functions;
importing the services does not load a model.

| Module | Responsibility |
| --- | --- |
| `settings.py`, `morphology.py` | Provider settings and language policy |
| `prompts.py`, `transport.py` | Dictionary schema/prompt and HTTP response handling |
| `dictionary.py` | Entry generation, persistence and usage orchestration |
| `custom_entries.py` | Database entries, stable IDs, normalization and TSV streaming |
| `legacy_tsv.py`, `migration.py` | Historical TSV IO and explicit database migration |
| `notes.py`, `entry_decomposition.py` | Per-entry semantic notes and decomposition |
| `gloss.py`, `decomposition.py`, `orthography.py` | Contextual batch tasks |
| `ner.py`, `translation.py` | Entity spans and sentence translation |

Regression fixtures cover schemas, language policies, and request/response
payloads. Mocked transport tests exercise service behavior without API calls,
private dictionaries, or trained models.

Set provider settings in `settings.py`; credentials remain in environment-backed
`config.py`. The facade exposes values for compatibility, but configuration should
be changed at its owning module rather than by assigning facade attributes.
