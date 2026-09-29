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

Provider settings belong to `settings.py`, with credentials supplied through
environment-backed `config.py`. Each task service owns its prompt and response
handling; the facade preserves the application's public call interface.
