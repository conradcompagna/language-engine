# Multilingual inference and lexical search

The platform combines a shared multilingual NLP service with browser-side
dictionary matching and exact SQLite hydration. This design keeps large lexical
records on the server while making repeated matching and navigation interactive.

## Language and model integration

[language_registry.py](../../language_registry.py) connects language codes,
Trankit runtime names, display configuration, and dictionary sources. It manages
the shared inference pipeline, language-specific tokenization hooks, custom NER
routing, and compressed-runtime integration. [pipeline_common.py](../../pipeline_common.py)
turns model output into token spans, dependency edges, grammatical features,
and entity overlays for the reader.

The [normalization layer](../../universal_normalization.py) maps model-space
text and offsets to the reading surface. The [MWT guide](MWT_SYSTEM.md) explains
how expanded linguistic words retain their relationship to visible tokens.
[Training records](../STATUS.md) connect model configurations and corpus builds
to application assets; [model results](../models/README.md) show selected runs.

## Compact lexical indexes

The [dictionary pipeline](../pipeline/README.md#3-dictionaries) produces
SQLite entries and form tables. [dict_lookup_sqlite.py](../../dict_lookup_sqlite.py)
builds compact headword and form indexes that carry row references rather than
full glosses. Shared normalization and [pruning policy](../../sqlite_prune_policy.py)
keep index construction aligned with browser queries.

[Index-cache services](../../language_engine/http/index_cache.py) and
[startup services](../../language_engine/http/startup.py) prepare versioned gzip
artifacts. The [browser cache](../../frontend/dictionary/client/index-cache.mjs)
retains indexes between sessions; the [dictionary engine](../../frontend/dictionary/engine/)
uses them for candidate selection, segmentation, and fuzzy matching.

## Request flow

1. The [HTTP lookup service](../../language_engine/http/lookup.py) runs linguistic analysis.
2. [Browser lookup orchestration](../../frontend/dictionary/client/lookup-service.mjs) combines its output with dictionary candidates and surface spans.
3. The [hydration endpoint](../../language_engine/http/dictionary_index.py) validates dictionary sources and retrieves selected rows in batches.
4. [Display serializers](../../language_engine/http/serializers.py) attach explicit identity, morphology, and provenance fields.
5. [Reader modules](../../frontend/reader/) display the aligned results in document overlays and dictionary panels.

Side-panel lookups reuse compact matching and hydration without an additional
neural parse. [Custom-entry services](../../language_engine/gemini/README.md)
add user-authored and generated entries with persistence and usage accounting.

The [application architecture](../../docs/BUILD_PROCESS.md#runtime-architecture) maps service ownership;
the [evaluation guide](../evaluation/README.md) links measurements and regressions
behind the lookup and inference design.
