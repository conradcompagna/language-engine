## Compatibility exports phased out of dictionary_client.js

These names were exported on `window.DictionaryClient` rather than declared as top-level `function` statements. The standalone `dictionary_postprocessor.js` now recreates them as a compatibility bridge so the app can stop loading `dictionary_client.js` and `dictionary_engine.js`.

| Name | Included | Note |
|---|:---:|---|
| `lookupSingle` | yes | Recreated in `dictionary_postprocessor.js`; fetches `/lookup_dp_only` and decorates the server payload. |
| `isEngineReady` | yes | Recreated as a compatibility constant returning `true` for the always-server-backed SQLite runtime. |
| `setSqliteMode` | yes | Recreated as a no-op compatibility shim. |
| `isSqliteMode` | yes | Recreated as a compatibility constant returning `true`. |
| `onLanguageDictSync` | yes | Recreated as a lightweight Promise-based compatibility shim. |
| `buildMergedLookupPayload` | yes | Recreated only as a throwing guard that tells the caller the server owns merged lookup payloads now. |
| `hasWord` | yes | Recreated using the SQLite `/api/lookup_single` endpoint instead of browser-memory engines. |
| `relookupOneSegment` | yes | Recreated via `lookupSingle` so callers can refresh a live segment without the old client file. |
| `debugBuildLemmaAlignment` | yes | Exposed through the compatibility object and backed by the standalone postprocessor implementation. |
| `debugBuildKoreanLemmaXposAlignment` | yes | Exposed through the compatibility object and backed by the standalone postprocessor implementation. |
| `getDictSource` | yes | Recreated in the compatibility bridge. |
| `getSelectedDictSources` | yes | Recreated in the compatibility bridge. |

# Dictionary postprocessor function inventory

Grounded in the actual `dictionary_engine.js` and `dictionary_client.js` files in this archive. `Included` means the function name is present in the new `dictionary_postprocessor.js`. `Not included` means the behavior stayed in Python or in legacy app/runtime glue.

## dictionary_engine.js

| Name | Line | Included | Note |
|---|---:|:---:|---|
| `internString` | 17 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `internMorphArray` | 27 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `normalizePos` | 56 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `isPersianLanguageCode` | 60 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `getLemmaHintTexts` | 65 | yes | Included because postprocessing still needs hydrated entries and lemma-linked metadata. |
| `pushText` | 68 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `normalizeAffixMarkers` | 371 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `applyLookupNormalizationLayer` | 383 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `stripInvisibleComparisonChars` | 397 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `normalizeLookupBaseProbeText` | 408 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `normalizeLookupProbeText` | 418 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `entryHasMorphTag` | 427 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `cloneEntryWithMorphTag` | 437 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `annotateNormalizedLookupEntry` | 451 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `annotateLookupEntries` | 479 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `lookupKey` | 489 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `lookupKeys` | 505 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `normalizeKoreanXposTag` | 519 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `normalizeKoreanXposTags` | 526 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `buildKoreanAllowedPosMap` | 539 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `normalizeVietnameseXposTag` | 559 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `splitVietnameseXposTags` | 563 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `normalizeVietnameseXposTags` | 576 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `buildVietnameseAllowedPosMap` | 591 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `toEngineDebugLineNo` | 611 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `buildEngineDebugEntryRef` | 617 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `buildEngineDebugEntryRefs` | 627 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `getLanguageRules` | 643 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `applyLanguageFormRules` | 648 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `getLanguageFormIndexTexts` | 654 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `getLanguageUposExtraPos` | 672 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `splitMorphTags` | 690 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `isKoreanHanjaDropdownEntry` | 708 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `normalizeDedupKey` | 723 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `dedupePreserveOrder` | 730 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `dedupeSemicolonChunks` | 744 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `dedupeGlossList` | 751 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `repeatedLeadGlossKey` | 756 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `dedupeSensesRuntime` | 765 | yes | Included for entry grouping, sense formatting, and hover/UI rendering. |
| `parseTsvRowCompact` | 810 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `parseTsvRowLegacy` | 866 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `parseTsvRow` | 895 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `etymKey` | 905 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `splitUposTags` | 911 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `entryIdentityKey` | 918 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `hydrateEntry` | 933 | yes | Included because postprocessing still needs hydrated entries and lemma-linked metadata. |
| `splitList` | 966 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `ensureHydrated` | 1024 | yes | Included because postprocessing still needs hydrated entries and lemma-linked metadata. |
| `hydrateAll` | 1032 | yes | Included because postprocessing still needs hydrated entries and lemma-linked metadata. |
| `DictionaryEngine` | 1040 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `hasMorphTag` | 1267 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `registerSurfaceForm` | 1293 | no | Not included. This belongs to lookup/index plumbing, not final postprocessing. |
| `tagPromotedObject` | 1542 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `getLemmaHintMeta` | 1601 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `getPromotedLemmaKeys` | 1606 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `cleanupLpTags` | 1613 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `filterEntriesForLemmaReuse` | 1619 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `checkCandidatesForPromotion` | 1640 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `buildBoundaryData` | 1662 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `buildDpDebugPayload` | 1695 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `isBetter` | 1724 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `crossesRestrictedBoundary` | 1733 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `evaluateCandidate` | 1747 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `splitByAllowed` | 2261 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `_lookup_key` (proto) | 1046 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `_lookup_keys` (proto) | 1050 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `loadFromRows` (proto) | 1054 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `load_tsv_entries` (proto) | 1070 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `_loadOneRow` (proto) | 1075 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `_index_tsv_forms` (proto) | 1089 | no | Not included. This belongs to lookup/index plumbing, not final postprocessing. |
| `lookup` (proto) | 1191 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `_split_matchable_display_entries` (proto) | 1196 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `_lookup_all_raw` (proto) | 1212 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `lookup_all` (proto) | 1249 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `lookupAll` (proto) | 1253 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `lookup_display_only` (proto) | 1257 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `lookupDisplayOnly` (proto) | 1262 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `lookup_via_forms` (proto) | 1266 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `lookupViaForms` (proto) | 1419 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `_filter_entries_for_greedy` (proto) | 1423 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `_entry_to_fill` (proto) | 1429 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `_greedy_fill_simple` (proto) | 1456 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `_greedy_fill` (proto) | 2015 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `fill_token` (proto) | 2020 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `fillToken` (proto) | 2049 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `filter_entries_by_upos` (proto) | 2053 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `filterEntriesByUpos` (proto) | 2180 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `filter_entries_by_xpos` (proto) | 2185 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `filterEntriesByXpos` (proto) | 2283 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `get_xpos_primary_match_info` (proto) | 2288 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `has_xpos_primary_match` (proto) | 2314 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |

## dictionary_client.js

| Name | Line | Included | Note |
|---|---:|:---:|---|
| `isTruthyFlag` | 131 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `toAbsoluteUrl` | 136 | yes | Included in the phase-out pass because the standalone postprocessor now owns the lightweight fetch/URL bridge used to decorate server responses. |
| `jsonResponse` | 144 | yes | Included in the phase-out pass as lightweight Response rebuilding for decorated JSON payloads. |
| `appendSelectedSourcesToUrl` | 154 | yes | Included in the phase-out pass because selected dictionary sources still need to be appended to lookup URLs after client/engine removal. |
| `rewriteFetchInputWithSelectedSources` | 170 | yes | Included in the phase-out pass as part of the standalone fetch-decoration bridge. |
| `getCurrentLanguage` | 184 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `getDictionaryNormalizationLayer` | 191 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `isSanskritLookupLanguage` | 195 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `buildSanskritLookupRewrite` | 204 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `getDictSource` | 210 | yes | Included in the phase-out pass because the standalone postprocessor now exposes DictionaryClient-compatible source selection helpers. |
| `getSelectedDictSources` | 216 | yes | Included in the phase-out pass because the standalone postprocessor now exposes DictionaryClient-compatible source selection helpers. |
| `cacheKey` | 227 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `findEngineCacheKey` | 231 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `evictAllEnginesExcept` | 241 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `requestMatchesCurrentSelection` | 269 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `showDictProgress` | 277 | no | Not included. This is app-shell UI, fetch interception, or upload plumbing. |
| `hideDictProgress` | 283 | no | Not included. This is app-shell UI, fetch interception, or upload plumbing. |
| `showTsvPill` | 289 | no | Not included. This is app-shell UI, fetch interception, or upload plumbing. |
| `hideTsvPill` | 294 | no | Not included. This is app-shell UI, fetch interception, or upload plumbing. |
| `setStatus` | 299 | no | Not included. This is app-shell UI, fetch interception, or upload plumbing. |
| `updateDictSourceUI` | 303 | no | Not included. This is app-shell UI, fetch interception, or upload plumbing. |
| `populateDictSourceDropdown` | 307 | no | Not included. This is app-shell UI, fetch interception, or upload plumbing. |
| `setDictSourceSelectPlaceholder` | 311 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `_updateDictSelectLabel` | 323 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `populateDictSourceCheckboxes` | 348 | no | Not included. This is app-shell UI, fetch interception, or upload plumbing. |
| `getCustomUploadRecord` | 406 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `setCustomUploadRecord` | 410 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `clearCustomUploadRecord` | 416 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `customUploadLabel` | 422 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `evictEngineKeysWithPrefix` | 430 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `evictCustomEngineCache` | 443 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `openBuiltinDictDb` | 449 | no | Not included. This is app-shell UI, fetch interception, or upload plumbing. |
| `builtinDbKey` | 466 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `saveBuiltinDict` | 472 | no | Not included. This is app-shell UI, fetch interception, or upload plumbing. |
| `loadBuiltinDict` | 489 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `parseTsvText` | 501 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `gzipBytesToUint8` | 519 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `gzipBlobToUint8` | 537 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `gunzipToText` | 558 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `loadLanguageMeta` | 569 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `_downloadGzipUrl` | 594 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `readChunk` | 605 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `_downloadGzipDict` | 639 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `fetchBuiltinDictGz` | 646 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `normalizeLookupKey` | 692 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `normalizeVisibleComparisonText` | 708 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `splitCompoundLemma` | 725 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `isPersianLanguageCode` | 732 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `splitPersianLemmaVariants` | 737 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `getLemmaHintCandidateTexts` | 752 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `pushText` | 756 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `cloneLemmaHintObject` | 776 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `chooseEntry` | 790 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `mergeWordLists` | 810 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `getCurrentLanguageRules` | 825 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `getEntryHanjaFormsByRules` | 835 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `getEntryHangeulFormsByRules` | 847 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `etymKey` | 859 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `hasExplicitEtymology` | 865 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `buildEntryFallbackSignature` | 872 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `entryGroupBucketKey` | 900 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `attachWiktForms` | 911 | yes | Included for entry grouping, sense formatting, and hover/UI rendering. |
| `buildWiktG2P` | 988 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `_ensureEntryHydrated` | 1004 | yes | Included because postprocessing still needs hydrated entries and lemma-linked metadata. |
| `buildFillPieceFromEntry` | 1012 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `buildFillResult` | 1057 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `dedupeEntriesByIdentity` | 1071 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `collectRecoveredLemmaHintIndexes` | 1087 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `lookupExactEntriesForText` | 1114 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `buildLemmaHintLookupPart` | 1121 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `buildLemmaHintAlignmentState` | 1149 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `cloneFillRowsWithSurfaceOffsets` | 1219 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `buildAlignedLemmaOverrideResult` | 1243 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `collectFillEntries` | 1433 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `collectPromotedFillEntries` | 1445 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `buildLemmaHintData` | 1457 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `findLemmaHintMatchForEntry` | 1491 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `pushCandidate` | 1495 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `collectEntriesMatchingLemmaHints` | 1539 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `isWholeSurfaceKnownFill` | 1555 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `annotateSingleFillLemmaPromotion` | 1564 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `buildSurfaceLemmaAwareLookup` | 1583 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `getLemmaOracleFill` | 1595 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `buildExactLookupDebugEvent` | 1826 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `pushLookupDebugEvent` | 1843 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `resolveExactThenGreedy` | 1852 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `mergeLookupResults` | 1889 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `resultMatchCount` | 1934 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `resolveLemmaOverride` | 1942 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `wiktLookup` | 1964 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `makeLookupOptions` | 1973 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `finishLookupResult` | 1987 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `dedupeMergedSenseLines` | 2060 | yes | Included for entry grouping, sense formatting, and hover/UI rendering. |
| `listTexts` | 2077 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `buildEntrySpellingsHead` | 2091 | yes | Included for entry grouping, sense formatting, and hover/UI rendering. |
| `abbreviatePos` | 2102 | yes | Included for entry grouping, sense formatting, and hover/UI rendering. |
| `formatStructuredSenses` | 2115 | yes | Included for entry grouping, sense formatting, and hover/UI rendering. |
| `formatSenses` | 2201 | yes | Included for entry grouping, sense formatting, and hover/UI rendering. |
| `mergeAllEntries` | 2212 | yes | Included for entry grouping, sense formatting, and hover/UI rendering. |
| `computeMetaSpecTag` | 2234 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `metaNfPercent` | 2243 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `computeMetaPriScoreDetails` | 2251 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `buildJmdictFormsMetaBundle` | 2278 | yes | Included for entry grouping, sense formatting, and hover/UI rendering. |
| `buildJmdictFormsMetaByHeader` | 2344 | yes | Included for entry grouping, sense formatting, and hover/UI rendering. |
| `splitEntriesForHover` | 2359 | yes | Included to preserve alternate-sense splitting and post-segmentation filtering. |
| `hasForcedAlternateMorphTag` | 2363 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `applyForcedAlternateSplit` | 2383 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `toDebugLineNo` | 2442 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `entryDebugIdentity` | 2448 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `buildDebugEntryRef` | 2458 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `buildDebugEntryRefs` | 2480 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `buildDebugLemmaHintPreview` | 2494 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `annotateLiveLemmaLinkedFills` | 2516 | yes | Included because postprocessing still needs hydrated entries and lemma-linked metadata. |
| `cloneResolutionRouteSteps` | 2551 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `buildResolutionRouteStep` | 2572 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `buildResolutionMeta` | 2580 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `summarizeActualResolutionFills` | 2600 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `buildResolutionRouteText` | 2636 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `buildResolutionFinalText` | 2651 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `buildLiveResolutionInfo` | 2675 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `buildDebugFillPreview` | 2726 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `summarizeLookupResultForDebug` | 2751 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `isKoreanLanguageCode` | 2781 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `isVietnameseLanguageCode` | 2786 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `languageUsesXposFilter` | 2791 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `normalizeFilterXposTag` | 2795 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `isKoreanEngine` | 2800 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `getKoreanDisplayOnlyEntries` | 2805 | no | Not included. This belongs to lookup/index plumbing, not final postprocessing. |
| `mergeUniqueEntries` | 2861 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `pushOne` | 2864 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `collectMorphMetaFromEntries` | 2880 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `splitCompoundTags` | 2924 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `normalizeCompoundParts` | 2930 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `uniqueNormalizedTags` | 2941 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `mergeCompoundTags` | 2954 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `normalizeXposTag` | 2963 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `collectScopedLemmaSpecificXposTags` | 2970 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `pushRaw` | 2976 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `choosePreferredSenseFilterXpos` | 3003 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `choosePreferredFillFilterXpos` | 3017 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `formatUnicodeCodePoint` | 3030 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `toUnicodeCodePointList` | 3038 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `decomposeTextToAlignmentUnits` | 3045 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `buildSurfaceCodepointMap` | 3058 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `buildGenericSurfacePartAlignment` | 3095 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `_buildGroupsFromUnitPartIds` | 3384 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `_buildProportionalAlignment` | 3485 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `buildKoreanLemmaXposAlignment` | 3525 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `normalizedPartIds` | 3542 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `xposTagsForPartIds` | 3554 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `buildDebugLemmaAlignment` | 3621 | yes | Included for resolution/debug metadata that lives after segmentation. |
| `normalizeDebugXposTag` | 3632 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `normalizedPartIds` | 3640 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `xposTagsForPartIds` | 3652 | yes | Included for POS/XPOS normalization, filtering, or tag scoping after segmentation. |
| `getFillPieceSurfaceText` | 3714 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `buildFillSurfaceSlices` | 3721 | yes | Included as a standalone postprocessing entry point. |
| `deriveFillPieceXposHints` | 3860 | yes | Included as a standalone postprocessing entry point. |
| `collectTagsForSpan` | 3924 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `cloneFillRowsForOutput` | 3958 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `prepareFillEntries` | 3984 | yes | Included as a standalone postprocessing entry point. |
| `buildUnknownResult` | 4106 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `extractTokenBySeg` | 4141 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `buildResultsBySeg` | 4154 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `buildLookupDpOnlyPayload` | 4377 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `buildSubsegmentsPayload` | 4474 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `buildMergedLookupPayload` | 4495 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `buildEngineFromRows` | 4513 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `cloneUint8Array` | 4522 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `countEngineEntries` | 4527 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `buildDictProgressMessage` | 4538 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `formatProgressMegabytes` | 4545 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `formatProgressCount` | 4550 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `buildDownloadProgressMessage` | 4554 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `buildAssemblyProgressMessage` | 4562 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `buildGeminiAdditionProgressMessage` | 4573 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `buildEngineFromGzipBytes` | 4584 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `_discoverEngineScriptUrls` | 4630 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `buildEngineStreaming` | 4649 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `_buildEngineMainThread` | 4670 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `processLine` | 4695 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `pump` | 4710 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `_getWorkerCode` | 4740 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `processLine` | 4791 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `sendProgress` | 4803 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `pump` | 4810 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `_buildEngineInWorker` | 4842 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `_queryWorker` | 4923 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `_getActiveWorkerKey` | 4937 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `buildEngineFromRowsOffThread` | 4959 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `_reconstructEngineFromWorkerData` | 5001 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `filterAugmentEntriesByEngine` | 5026 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `buildAugmentedBrowserEngine` | 5053 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `mergeEntriesFromMethod` | 5061 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `resolveLanguageMetaItem` | 5095 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `ensureBuiltinEngine` | 5101 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `ensureCustomEngine` | 5149 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `ensureAugmentedCustomEngine` | 5193 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `ensureLanguageEngine` | 5231 | yes | Included only as a compatibility no-op Promise so existing app call sites can survive after dictionary_client.js is removed. |
| `onLanguageDictSync` | 5248 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `handleCustomUploadFile` | 5280 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `resetCustomForCurrentLanguage` | 5311 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `prefetchAllBuiltinDicts` | 5324 | no | Not included. This is dictionary loading, worker assembly, or old browser-engine runtime. |
| `bindUi` | 5329 | no | Not included. This is app-shell UI, fetch interception, or upload plumbing. |
| `lookupLangFromUrl` | 5382 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `_decorateResultWithPosFilter` | 5388 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `_decorateFillsWithPosFilter` | 5424 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `_backfillLiveResultFillHints` | 5468 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `_decorateLookupResultObject` | 5482 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `decorateLookupJson` | 5516 | yes | Included as a standalone postprocessing entry point. |
| `decorateList` | 5533 | yes | Included in dictionary_postprocessor.js because it still participates in post-segmentation decoration. |
| `buildDebugUiDictMeta` | 5550 | yes | Included in lightweight form so live lookup debug captures can still be posted after phasing out dictionary_client.js. |
| `syncLiveDebugLookupCapture` | 5570 | yes | Included in the phase-out pass so decorated /lookup payloads can still mirror live debug capture behavior without dictionary_client.js. |
| `decorateSubsegmentsJson` | 5598 | yes | Included as a standalone postprocessing entry point. |
| `maybeDecorateJsonResponse` | 5620 | yes | Included in the phase-out pass because standalone fetch decoration is now required when dictionary_client.js is not loaded. |
| `handleLookupDpOnlyRequest` | 5650 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `handleSubsegmentsRequest` | 5697 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `handleLookupRawRequest` | 5740 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `_sqliteBuildMiniEngine` | 5792 | no | Not included. This is transport or debug-capture glue for the legacy client wrapper. |
| `_sqliteFetchBatchEntries` | 5799 | no | Not included. This is transport or debug-capture glue for the legacy client wrapper. |
| `_sqliteFetchSingleEntries` | 5829 | no | Not included. This is transport or debug-capture glue for the legacy client wrapper. |
| `_sqliteDecorateLookup` | 5842 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `_sqliteHandleLookupDpOnly` | 5849 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `_sqliteHandleSubsegments` | 5863 | no | Not included. This is transport or debug-capture glue for the legacy client wrapper. |
| `wrapFetch` | 5874 | yes | Included in the phase-out pass as the standalone fetch interceptor used by the compatibility DictionaryClient export. |
| `_injectGeminiAdditions` | 5896 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `injectNextBatch` | 5914 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `injectGeminiEntry` | 5967 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `relookupOneSegment` | 6012 | no | Not included. Python now owns lookup selection, exact/greedy resolution, and segmentation. |
| `init` | 6027 | yes | Included in lightweight compatibility form. It now sets language state and installs the fetch interceptor instead of binding the old TSV/engine UI. |
| `getEditableGeminiSourceTag` | 6034 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `getEditableGeminiEntryId` | 6040 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `getEditableGeminiHead` | 6045 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `matchesEditableGeminiEntry` | 6056 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `getRawGeminiEntry` | 6074 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `updateGeminiEntry` | 6113 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `removeGeminiEntry` | 6129 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `reply` | 6163 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
| `replyError` | 6166 | no | Not included because it belongs to the old engine/client runtime rather than standalone post-segmentation decoration. |
