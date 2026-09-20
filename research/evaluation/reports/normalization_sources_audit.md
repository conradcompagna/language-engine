# Normalization Sources Audit

Scope: I traced only code reachable from the active lookup/rendering chain described in `AGENTS.md`. I excluded `backup_quarantine/` and the many `*Copy*` mirrors unless they are the only surviving copy of a rule.

## Active Sources

`static/dictionary_normalization_layer.js` is the canonical lookup normalizer. `normalizeLookupKeyText()` runs NFKC, Ancient Greek apostrophe expansion, affix-marker folding, the registered rule pipeline, hyphen stripping, and lowercase normalization. The live rule table covers invisible format controls, Ancient and Modern Greek accent/sigma handling, CJK variation selectors, Arabic/Persian/Urdu mark and letter folding, Hebrew niqqud/cantillation stripping, Indic zero-width control stripping, Turkish casefold prep, and Thai ZWSP stripping. The important detail is that the rules run in a defined order and can be phase-sensitive, so the same surface text can normalize differently for `lookup_key`, `normalized_match_probe`, or display comparison. This is the shared source used by both the browser and the Node shim.

`tools/normalize_keys.js` is not a separate rule set; it is the active Node wrapper that loads the browser normalization layer so Python can batch-generate the same keys for SQLite and custom-form indexing.

`dict_lookup_sqlite.py` is still a live normalization source despite the stale “defunct” banner around `_normalize_key()`. Active SQL paths register `normkey_lang()` against `_normalize_key()`, and query-time lookups still call it directly in helper paths, so the database layer is not just consuming precomputed keys. The same file also uses `_normalize_keys_via_js()` for custom-entry form indexing, so both Python and JS participate in the current dictionary key path. In practice this means the SQLite layer remains a real normalization boundary for lookups, not a dead compatibility wrapper.

`universal_normalization.py` is the preprocessing gate for Trankit and offset remapping. It NFKC-normalizes, strips non-BMP characters, applies Arabic diacritic removal in model space, remaps model offsets back to original text, and post-processes Old English lemmas by splitting trailing commentary from the lemma proper. It also rewrites segment offsets and token text after remap, so this file is doing more than generic Unicode cleanup. This is the layer that preserves the one-map model-index-to-original-index contract, which is why it matters even when the final lookup result is coming from the dictionary stack.

`static/dictionary_client_hybrid.js` contains client-side canonicalization after lookup and hydration. Its active rules normalize lookup keys, visible comparison text, canonical entry rows, numeric-tone pinyin, Korean jamo comparison, Korean XPOS filtering, and hydrated entry payloads. This is a real normalization source, not just a cache helper. The pinyin converter is especially important because it rewrites CEDICT-style numeric tones into diacritics before render-time comparisons happen, and `normalizeCanonicalEntryRuntime()` then synchronizes the hydrated fields so the popup and side panel stay internally consistent.

`static/dictionary_engine_hybrid.js` normalizes the in-memory engine side. It folds lookup probes through NFKC plus affix-marker handling, dedupes gloss keys, normalizes Korean and Vietnamese XPOS tags, and normalizes Korean jamo for comparison. It also keeps preferred POS lists canonical.

`static/reader.js` adds UI-side normalization for visible comparison text, lookup cache keys, grammar meta blobs, dependency labels, text direction, page text, MWT anchor lists, sentence spans, and UD part indices. Most of this is presentation glue, but it still changes how values compare and render. The `normalizeLookupKey()` helper here is intentionally weaker than the shared lookup key rule set; it is only a cache key for the reader UI, not the canonical dictionary key definition.

`static/reader_wikt.js` normalizes morph-info lists and entry-group keys for popup rendering. It is the shared rendering adapter, so these normalizations are active even though the file is mostly UI code.

`router.py` normalizes entry form rows and special display form rows. `_split_special_display_form_tags()` does NFKD plus combining-mark stripping and buckets forms like hanja, hangeul, and CJK variants. That is a notable normalization layer outside the main dictionary stack. The server also uses these normalized rows when shaping the hydration payload, so this is not cosmetic only.

`pipeline_common.py` still has a conservative `_normalize_component_text()` used when composing compound lemma and XPOS hints.

`language_registry.py`, `xpos_definitions.py`, and `trankit_mwt_expansion.py` each normalize language aliases or spans. `resolve_lang_code()` is the base alias map, `normalize_xpos_lang_code()` resolves XPOS config keys, and the MWT adapter normalizes language keys plus span tuples. These helpers are small, but they prevent the larger normalization layers from having to special-case every alias or span shape.

One more active but secondary rule set lives in the rendering/alignment code: `dictionary_client_hybrid.js` includes combining-mark merging for alignment, and `reader.js` still performs NFD-based orthography decomposition in the display path.

## Dead Sources

`sqlite_segmenter.py` is dead, but it still contains normalization helpers such as `_normalize_cached()` and `_normalize_visible_comparison_text()`. Because the whole module is defunct, those helpers should be treated as legacy only.

`static/dictionary_postprocessor.js`, `static/dictionary_client.js`, and `static/dictionary_engine.js` are dead Phase 2 copies. They still contain the old `normalizeLookupKey`, `normalizeVisibleComparisonText`, `normalizeXposTag`, and `normalizeDedupKey` stacks, but none of them are on the current hybrid reader path. These files are useful as historical references, but they should not receive new rule changes.

`static/reader_ja.js`, `static/reader_ko.js`, `static/reader_zh.js`, `static/reader_lzh.js`, and `static/reader_vi.js` are dead language-specific adapters. They still carry legacy romanization and grouping normalizers, but `reader_wikt.js` replaced that architecture.

`wiktionary_general/pipeline.py` and `wiktionary_general/dictionary.py` are dead legacy normalization code from the pre-hybrid pipeline. The pipeline file still casefolds and NFKC-normalizes lookup keys, while the dictionary file still contains `_normalize_dedupe_key`, `_normalize_pos`, `_normalize_lookup_text`, and affix-marker folding. None of that is reachable from the current lookup chain, and it is safe to treat this package as archival unless you are resurrecting the old TSV pipeline.

I also found many backup copies of the same dead rules under `backup_quarantine/` and `*Copy*` filenames. I did not enumerate them individually because they are quarantined mirrors rather than distinct runtime sources.

## Bottom Line

The real current normalization surface is split across three tiers: the shared lookup layer in `static/dictionary_normalization_layer.js`, the Python/SQLite hydration layer in `dict_lookup_sqlite.py` plus `tools/normalize_keys.js`, and the universal preprocessing layer in `universal_normalization.py`. Everything else is either a smaller active UI/engine normalizer or a legacy dead copy.

If you change normalization semantics, the minimal safe update set is the shared JS rule layer, the Python/SQLite shim that mirrors it, and the specific consumer that depends on the changed phase. In other words: lookup semantics live in the shared layer, storage/index semantics live in the SQLite path, and text-offset semantics live in `universal_normalization.py`. Those three need to stay aligned.
