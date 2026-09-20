# Dictionary SQLite Port Gap Report

Date: 2026-03-27

## Scope

This report compares the legacy browser-resident dictionary path in `static/dictionary_engine.js` and `static/dictionary_client.js` against the current SQLite-backed path in:

- `dict_lookup_sqlite.py`
- `sqlite_segmenter.py`
- `router.py`
- `static/dictionary_postprocessor.js`
- the live `dict_sqlite/*.sqlite` schema

I am only calling out logic that looks genuinely left behind in the active SQLite system. I am not counting browser-only concerns that are clearly retired on purpose, like gzip download, IndexedDB caching, worker assembly, or TSV progress UI.

## Executive Summary

The big ported pieces are in place: normalization, exact-vs-greedy segmentation, lemma-aware lookup, per-segment result construction, POS/XPOS post-filtering, and the Gemini create/edit compatibility bridge.

The confirmed misses I found are:

1. Korean language-specific form indexing from the old engine never got materialized into SQLite.
2. Korean synthetic `-da` stem indexing never got materialized into SQLite.
3. The debug lookup payload lost lemma-hint and exact-path event detail even though the debug UI still expects it.

There are also two lower-confidence / lower-severity leftovers:

4. Normalized-match decoration metadata was not recreated end-to-end.
5. The old Korean display-only supplemental-entry path is gone, although the current reader also no longer seems to consume it.

## Confirmed Gaps

### 1. Korean `eumhun` secondary form keys were not ported into SQLite

Legacy behavior:

- `getLanguageFormIndexTexts()` can rewrite one visible form into one or more lookup texts, and for Korean `eumhun` it indexes the final Hangul syllable rather than the full spaced label. See `static/dictionary_engine.js:654-668`.
- `_index_tsv_forms()` actually uses those derived texts when building the in-memory form index. See `static/dictionary_engine.js:1125-1163`.

Current behavior:

- `convert_tsv_to_sqlite.py` writes exactly one SQLite `forms` row per raw `form_text`, using only `_normalize_key_full(form_text, lang_code)`. It never expands `form_text` through the legacy language rule layer. See `convert_tsv_to_sqlite.py:157-177`.
- The same simplification exists for custom entries. `dict_lookup_sqlite._iter_normalized_custom_forms()` also emits exactly one normalized key per raw form text. See `dict_lookup_sqlite.py:573-604`.
- `sqlite_segmenter.py` still knows how to derive the Korean `eumhun` lookup text in `_get_language_form_index_texts()`, but that logic runs only after the entry has already been reached and hydrated. See `sqlite_segmenter.py:564-578` and `sqlite_segmenter.py:745-781`.

Why this matters:

- The old engine could retrieve some Korean entries by a derived `eumhun` key even when that key never appeared as a literal `form_text`.
- The SQLite path cannot do that, because the candidate prefetch only hits `forms.form_key`, and the auxiliary key was never written to SQLite.

Live repro:

```text
DB row:
  headword = \u72ac
  form_text = \uac1c \uacac
  morph_tags = eumhun

Legacy expectation:
  query \uacac should be able to reach headword \u72ac
  because the old engine indexes the final Hangul syllable for eumhun.

Current SQLite result:
  SQLiteDictionarySegmenter('ko').lookup_all('\uacac') -> 8 rows
  returned heads include:
    \u5e75
    \u6898
    \u7367
    \u774a
    \uacac
  but not:
    \u72ac
```

Impact:

- Real Korean lookups reachable in the legacy engine are unreachable in the SQLite path.
- This is not just presentation loss. It is lookup reachability loss.
- The same bug applies to custom Korean entries, because the custom form index uses the same one-key-per-form strategy.

Fix direction:

- Port the old `_index_tsv_forms()` expansion logic into the SQLite build/index path, not just the hydrated runtime path.
- That means the importer/custom indexer must emit all lookup keys produced by `getLanguageFormIndexTexts()`, not only the raw form text key.

### 2. Korean synthetic `-da` stem indexing was not ported into SQLite

Legacy behavior:

- `_index_tsv_forms()` added a synthetic lookup form for Korean verbs/adjectives ending in `\uB2E4`, indexing `lemma[:-1]` with morph tag `stem`. See `static/dictionary_engine.js:1167-1184`.

Current behavior:

- I found no equivalent in `convert_tsv_to_sqlite.py`, `dict_lookup_sqlite.py`, or `sqlite_segmenter.py`.
- The importer only stores explicit TSV forms. It does not synthesize the stem.

Live repro:

```text
Sample entry:
  headword = \ubc1c\uac1b\ub2e4
  pos = adj

Legacy expectation:
  query \ubc1c\uac1b should be able to reach \ubc1c\uac1b\ub2e4
  even if the TSV never listed that exact stem form.

Current SQLite result:
  SQLiteDictionarySegmenter('ko').lookup_all('\ubc1c\uac1b') -> 0 rows
```

Why this is a genuine port miss:

- This was not just a convenience helper in the browser shell. It changed lookup reachability.
- The old engine explicitly preserved this behavior even when Python supplied precomputed form keys; the code comments say to "still fall through for Korean stem indexing below." See `static/dictionary_engine.js:1114-1115`.

Impact:

- Korean verbs/adjectives that relied on the synthetic stem are now spottily missing.
- The bug is intermittent because some lemmas still work when the TSV happens to contain an explicit stem-like form. Others do not.

Fix direction:

- Materialize the synthetic Korean stem key during SQLite import and during custom form index rebuilds.
- This belongs in the index/build phase, not only the hydrated lookup phase.

### 3. Debug lookup trace parity is incomplete

Legacy behavior:

- `buildExactLookupDebugEvent()` and `pushLookupDebugEvent()` collected exact-path debug events. See `static/dictionary_client.js:1826-1850`.
- `buildDebugLemmaHintPreview()` cloned the lemma hint objects for debug output. See `static/dictionary_client.js:2494-2514`.
- `buildResultsBySeg()` attached all of that into `_debug_lookup_scoring`, including:
  - `lemma_hints`
  - `surface_exact_events`
  - `lemma_exact_events`
  See `static/dictionary_client.js:4343-4366`.

Current behavior:

- `router.py` now emits `_debug_lookup_scoring`, but only with the coarse summary fields. It does not include `lemma_hints`, `surface_exact_events`, or `lemma_exact_events`. See `router.py:1012-1029`.
- The debug UI still expects those keys. `debug_panel.py` reads them directly. See `debug_panel.py:2631-2637`.

Impact:

- The debug panel loses the old exact-path tables and the lemma-hint preview row.
- This is a real regression in tooling/debug observability, even though lookup correctness is mostly unaffected.

Fix direction:

- Restore those fields in the router debug payload.
- The simplest port is to mirror the old `buildResultsBySeg()` payload shape so `debug_panel.py` does not need special-case SQLite handling.

## Lower-Confidence / Lower-Severity Leftovers

### 4. Normalized-match decoration metadata was not recreated

Legacy behavior:

- `annotateNormalizedLookupEntry()` and `annotateLookupEntries()` could clone a match, tag it as `normalized`, set `surface_form` to the queried text, and backfill `morph_base` to the matched canonical text. See `static/dictionary_engine.js:451-486`.

Current behavior:

- The active SQLite path normalizes keys for reachability, but I do not see an equivalent result-decoration step in `dict_lookup_sqlite.py`, `sqlite_segmenter.py`, `router.py`, or `static/dictionary_postprocessor.js`.
- In `sqlite_segmenter._enrich_entry_for_lookup_text()`, a normalized headword-key match just returns `dict(entry)` with no normalization annotation. See `sqlite_segmenter.py:751-782`.

Why I am not ranking this as high as the Korean form-index misses:

- This looks like metadata/presentation parity loss, not lookup reachability loss.
- It matters if you still care about exposing "this matched only after normalization" in UI/debug metadata.
- It is less clear how much of the old normalization-probe behavior you still want, because the legacy JS had already been partially simplified once the server started owning normalization.

### 5. The old Korean display-only supplemental-entry path is gone

Legacy behavior:

- The old client/runtime had `_split_matchable_display_entries()`, `lookup_display_only()`, and `getKoreanDisplayOnlyEntries()` for Korean supplemental display rows. See:
  - `static/dictionary_engine.js:1196-1209`
  - `static/dictionary_engine.js:1257-1263`
  - `static/dictionary_client.js:2805-2859`

Current behavior:

- I do not see an active SQLite equivalent in `dict_lookup_sqlite.py`, `sqlite_segmenter.py`, `router.py`, or `static/dictionary_postprocessor.js`.
- I also do not see the current `reader.js` calling that path anymore.

Assessment:

- I am not counting this as a confirmed active regression because the current reader appears to have moved away from that API and now relies on ordinary entry groups plus `hanja_forms` / `hangeul_forms`.
- If you still want the old dedicated display-only Korean supplemental rows, though, that branch was not ported.

## Important Things I Checked And Do Not Count As Missing

These were legacy behaviors that do appear to be ported or deliberately replaced:

- Core lookup normalization is ported into `dict_lookup_sqlite._normalize_key()`, including NFKC, affix marker folding, and language-specific normalization.
- Lemma-aware exact lookup, greedy DP segmentation, lemma override, partial lemma alignment, and resolution metadata are ported into `sqlite_segmenter.py`.
- `buildUnknownResult`, `buildResultsBySeg`, `/lookup_dp_only`, and `/subsegments` moved into `router.py`.
- POS/XPOS filtering, hover split logic, fill-surface slicing, and live result decoration are ported into `static/dictionary_postprocessor.js`.
- Gemini create/edit/remove compatibility is present in the postprocessor compatibility bridge, and the current reader calls those compat functions.

## Bottom Line

If the goal is "what real logic from the old dictionary backend is still missing from the live SQLite stack", the highest-signal misses are:

1. Korean `eumhun` secondary form indexing.
2. Korean synthetic `-da` stem indexing.
3. Debug scoring payload parity (`lemma_hints`, `surface_exact_events`, `lemma_exact_events`).

Everything else I found is either:

- already ported,
- intentionally retired with the browser-engine removal, or
- a lower-severity metadata compatibility issue rather than a lookup correctness bug.
