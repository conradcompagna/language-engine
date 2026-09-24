# Lookup normalization responsibilities

Dictionary indexing and query matching share a normalization contract so that
an indexed spelling remains reachable from a reader query. NLP normalization
and display formatting have separate responsibilities.

| Layer | Implementation | Responsibility |
|---|---|---|
| Shared dictionary keys | [dictionary_normalization_layer.js](../../../static/dictionary_normalization_layer.js) | Unicode and language-specific key rules |
| Index generation | [normalize_keys.js](../../../tools/normalize_keys.js), [dict_lookup_sqlite.py](../../../dict_lookup_sqlite.py) | Apply shared key rules to SQLite headwords and forms |
| Browser probes and matching | [engine normalization](../../../frontend/dictionary/engine/normalization.mjs), [client core](../../../frontend/dictionary/client/core.mjs) | Normalize lookup candidates and comparison strings |
| Model input and offset remapping | [universal_normalization.py](../../../universal_normalization.py) | Prepare inference text and relate model offsets to source text |
| Hydrated display fields | [serializers.py](../../../language_engine/http/serializers.py), [entry-adapters.mjs](../../../frontend/dictionary/client/entry-adapters.mjs) | Shape readings, morphology, and presentation fields |

Key rules cover script-specific equivalences such as Greek final sigma and
diacritics, Arabic-script marks, CJK variation selectors, and invisible format
controls. Their ordering is part of the contract. A key-rule change should be
exercised through both index construction and browser matching; presentation
changes are checked against the [hydration contract](../../notes/HYDRATION_FIRST_RENDERING_REFERENCE.md).

The [evaluation index](../README.md) links dictionary data audits and lookup
measurements. The [browser guide](../../../frontend/README.md) maps the source
modules for dictionary identity, form matching, segmentation and hydration.
