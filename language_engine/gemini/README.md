# Gemini services

`gemini_dict.py` preserves the existing function import paths for the router.
Implementations live here with explicit imports and no model loading on import.

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

The eight shadowed function definitions and an overwritten decomposition prompt
were consolidated to their effective final versions. All 57 effective function
bodies were preserved during extraction; regression fixtures retain pre-extraction
schema, language-policy and payload results. Mocked transport tests make no API
calls and require no private dictionary or trained model.

Set provider settings in `settings.py`; credentials remain in environment-backed
`config.py`. The facade exposes values for compatibility, but configuration should
be changed at its owning module rather than by assigning facade attributes.
