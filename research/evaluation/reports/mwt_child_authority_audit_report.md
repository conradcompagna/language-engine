# MWT Child Authority Audit

Date: 2026-04-20

Scope: I audited the active MWT runtime only: `trankit_mwt_expansion.py`, `pipeline_common.py`, `static/dictionary_client_hybrid.js`, `static/reader.js`, `static/panel_segment_renderer.js`, and `static/reader_wikt.js`. I did search repo-wide for MWT-related logic, but the findings below are limited to active paths per `AGENTS.md`; dead phase-1/2/3 code is omitted unless an active file still depends on it.

## Confirmed Child-Authoritative Areas

`static/dictionary_client_hybrid.js:2326-2374` is already doing the right thing at the hint-construction layer: every MWT child gets its own hint object, and the child carries `surface_slice`.

`static/dictionary_client_hybrid.js:1895-1969` is also correct in the direct alignment layer: once the code is in MWT slice mode, `surface_slice` is mandatory and the code refuses cursor/substring fallback.

`static/dictionary_client_hybrid.js:3283-3302` is correctly blocking whole-surface greedy on MWT parents. I did not find an active path that intentionally re-enables whole-parent greedy once `mwt_parts.length > 1`.

## Findings

### 1. The canonical runtime identity is still the parent token, not the MWT child

Evidence: `trankit_mwt_expansion.py:502-509` explicitly says MWT-expanded grammar is collapsed back onto the original surface tokens. `pipeline_common.py:2524-2637` builds `segments` from the parent token text only. `pipeline_common.py:1094-1269` emits one UD token per parent and attaches children as `mwt_parts`. `static/dictionary_client_hybrid.js:7783-7792` then builds one `resultsBySeg[i]` per segment, and `static/dictionary_client_hybrid.js:7935-7985` stores `mwt_parts` on that parent result instead of promoting children to first-class `results_by_seg` entries.

Impact: every downstream cache, refresh, popup, and panel path starts from the parent token and must manually re-scope itself to the child; any place that forgets to do that falls back to whole-token behavior.

### 2. The merged MWT fill rows still use the surface anchor as their primary text payload

Evidence: in `static/dictionary_client_hybrid.js:2955-3118`, each child is looked up independently, but the merged row is rebuilt around `childSurfaceSlice`. The greedy bundled row is force-overwritten with `text/head/headword/surface_form = childSurfaceSlice` at `3075-3082`. Even the exact/lemma path is rebuilt through `buildFillPieceFromEntry(childSurfaceSlice, ...)` at `3100`. The actual child spelling survives only in `_mwt_child_text` at `3114`. Downstream consumers are surface-first: `static/dictionary_client_hybrid.js:6459-6463` and `static/reader.js:14699-14703` both return `fillEntry.text` before anything else.

Impact: once the child lookup result has been merged back into the parent token, many later consumers see the surface slice first and only see the real child spelling if they explicitly know to read `_mwt_child_text`.

### 3. Greedy child-piece explosion still drops pieces whose child chars collapse onto the same surface anchor

Evidence: `static/dictionary_client_hybrid.js:6592-6737` explodes bundled MWT greedy rows back into per-piece rows. The critical behavior is at `6673`: zero-width pieces are deliberately dropped after char-map remapping. If no char map exists, `6737` keeps the bundled row intact instead of preserving child-level atomic pieces.

Impact: this is the active place where a child-internal piece can disappear even though the backend realignment knew about it. Your `avalka -> valka` example fits this pattern exactly: if the deleted or assimilated child chars map to an anchor without positive width, the JS explosion pass drops that piece.

### 4. Part-scoped filtering silently falls back to the whole token when `_mwt_part_index` tags are missing

Evidence: `static/reader.js:7129-7140` filters `dict_fill` rows by `_mwt_part_index`, but if no rows are tagged it returns the entire `dictFill` unchanged. This helper is used in `cloneLookupEntryForScopedPart()` (`1533-1564`), the token banner (`20314-20331`), the grammar popup (`3055-3077`, `3123`), and the spawned child popup context (`7279`).

Impact: any path that loses `_mwt_part_index` immediately reverts child hover/click back to the parent token's full entry list instead of failing closed. That is one direct way the "whole token list appears after acting on one child" symptom can happen.

### 5. Child-specific UI state is stored in one global slot, and state reuse ignores `mwtPartIndex`

Evidence: `_activateTokenMapForClickContext()` writes one global `tokenMapData` object containing only one `mwtPartIndex`, one `mwtChildText`, and one `mwtSurfaceSlice` (`static/reader.js:16838-16842`). `isLiveTokenMapStateMatch()` only checks `segIdx` or surface text and does not include the MWT part index (`20783-20795`). `buildGrammarPopupTokenMapState()` reuses `tokenMapData` whenever that coarse match succeeds (`20845-20849`). `buildGrammarPopupHtml()` then prefers `(options.mwtSurfaceSlice || tokenMapState.mwtSurfaceSlice)` at `3040-3041`.

Impact: if child A was the last clicked child, then sibling child B can inherit child A's stored `mwtSurfaceSlice` whenever the popup render path reuses `tokenMapData` without an explicit new slice. This is the direct stale-state mechanism behind the "all other children now use the last child's surface slice" bug.

### 6. Exact child lookups in the panel/token-banner helpers are still token-scoped, not part-scoped

Evidence: `buildTokenMapLookupRequestOptions()` accepts `partIndex`, but for `role === 'surface'` it ignores that part index and always emits the token-level `upos/xpos` hints (`static/reader.js:20797, 20822-20824`). The side-panel exact-lookup cache key also ignores part identity (`static/reader.js:16238-16255`). On top of that, `static/panel_segment_renderer.js:29, 89, 107` caches by `lang|surface` only and performs `lookupSingle(surface, lang, { exact: true })` with no MWT child context.

Impact: the auxiliary exact-lookup layer treats an MWT child as a free-floating token string, not as a specific child of a specific parent token and slice, so sibling children share cache/lookup state whenever their surface text and token-level hints line up.

### 7. Panel-state restore still reconstructs from raw parent `dict_fill`, not from persistent child identity

Evidence: `getRenderableTokenMapDisplaySliceItems()` explicitly says it uses the literal backend `dict_fill` entries with "No slicing, decomposition, or async re-lookup" (`static/reader.js:21231-21240`). `restorePanelFromTokenMapState()` uses that raw list directly (`2346`) and, if it cannot reconstruct the previous focused fill, falls back to `tokenMapData.tokenEntry || tokenMapData.entry` (`2384-2386`). The click path stores only `_panelTokenSurface`, `_panelTokenLemma`, and `_panelTokenLemmaRaw` in `panelOptsBase` (`16881-16885`); it does not persist `_panelMwtPartIndex`, child text, or child slice.

Impact: once the panel needs to rebuild itself after a refresh, it can lose the child-specific scope and reopen the parent token payload instead. That matches the "create a synth entry on one child, then the whole token list comes back" behavior.

### 8. Custom-entry refresh is still segment-scoped, not child-scoped

Evidence: `refreshUiAfterCustomEntryMutation()` finds affected segment indexes and calls `dc.relookupOneSegment(lang, surface, seededExisting)` for the whole segment (`static/reader.js:2395-2420`). `relookupOneSegment()` then does one `hybridDpOnlyLookup(surface, ... { mwt_parts })` and returns one rebuilt segment result (`static/dictionary_client_hybrid.js:10714-10724`). `applyFreshSegmentResult()` writes that whole result back into `latestData.results_by_seg[targetIdx]` and caches it under the parent `targetSurface` (`static/reader.js:2296-2315`).

Impact: every synth/custom-entry mutation refresh is fundamentally replacing the parent segment object. The child-specific view survives only if the later restore path manually re-scopes it correctly; when that re-scope fails, the UI snaps back to the full parent token result.

### 9. The spawned child popup still has a surface-heuristic fallback if authoritative local slices are incomplete

Evidence: `_buildMwtSpawnFillSurfaceSlices()` falls back to `buildDictFillSlicesForToken(surface, fillRows, null, { coalesceMarkOnly: true })` when the local child rows do not carry enough explicit offsets (`static/reader.js:7157-7208`). `buildDictFillSlicesForToken()` is a width/proportional slicer when authoritative slices are absent (`14963-15110`).

Impact: the spawned unsandhied child popup is mostly child-authoritative when offsets survive, but once that metadata is incomplete the fallback logic re-derives fill ownership from surface width instead of from the child text or the backend realignment lattice.

### 10. The visible MWT anchor geometry still falls back to proportional surface ranges

Evidence: `buildMwtPartRanges()` prefers `surface_slice`, but if the slice data is missing or degenerate it falls back first to literal matching and then to a proportional split across the parent surface (`static/reader.js:7518-7565`). `registerMwtPartAnchors()` depends on those ranges to assign the clickable/hoverable child anchor wrappers and to compute each child's visible surface slice (`7764-7841`).

Impact: the anchor/hover ownership layer is still not strictly child-authoritative. Missing or bad `surface_slice` data pushes it back to surface heuristics, which can mis-assign hover/click area ownership even if the backend child decomposition was otherwise correct.

### 11. One bad offset row is enough to strip authoritative MWT fill slices from the live payload

Evidence: `buildMwtFillSurfaceSlicesFromOffsets()` returns `[]` as soon as any row has an invalid or zero-width `_surface_start/_surface_end` pair (`static/dictionary_client_hybrid.js:6957-6965`). `buildLiveLookupFillPayload()` uses that exact function for `mwt_child` fills (`7472-7502`) and does not repair the failure inside the MWT branch.

Impact: once the authoritative MWT slice array collapses to empty, later UI code has to infer slices on its own, which is how surface-width heuristics re-enter the active path even though the core MWT resolver was meant to stay offset-driven.

## Symptom Mapping

The "create synth entry on one child and then see the whole token list" bug is best explained by Findings 4, 7, and 8.

The "greedy segmented child drops one of its real child pieces when child text and surface slice differ" bug is best explained by Findings 2, 3, 9, and 11.

The "click one child and siblings start reusing that child's surface slice" bug is best explained by Findings 5 and 6.

## TLDR

1. The active runtime still treats the MWT parent as the canonical token object, with children attached as metadata rather than as first-class `results_by_seg` entries.

2. After independent child lookup, the merged fill rows still store the surface anchor as their main `text/surface_form`, so downstream code sees the surface slice unless it explicitly reads `_mwt_child_text`.

3. The greedy child-piece explosion pass still drops zero-width remapped pieces, so child chars that collapse onto the same surface anchor can disappear from fill-hit construction.

4. Any part-scoped UI that loses `_mwt_part_index` silently falls back to the entire parent `dict_fill`, which reintroduces whole-token entry lists under child interactions.

5. The reader keeps only one global `mwtPartIndex/mwtSurfaceSlice` in `tokenMapData`, and its state-reuse check ignores part identity, so stale child slices bleed into sibling children.

6. The panel/token-banner exact-lookup helpers and their caches are keyed as if an MWT child were just a plain token string, not a child of a specific parent slice.

7. Panel restore logic persists only the parent token identity and rebuilds from raw parent `dict_fill`, so child-specific focus is easy to lose after any rerender.

8. Custom-entry refresh is still whole-segment relookup plus whole-segment replacement, so child-specific UI survives only if a later manual re-scope succeeds.

9. The spawned unsandhied child popup still falls back to surface-width slicing when its local authoritative offsets are incomplete.

10. The DOM anchor geometry for MWT children still falls back to literal/proportional surface segmentation when `surface_slice` data is missing or degenerate.

11. A single invalid MWT offset row can erase the authoritative `dict_fill_surface_slices` array for the live payload and force later UI layers back onto heuristic surface slicing.
