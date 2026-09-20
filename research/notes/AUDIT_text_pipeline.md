# Canonical Text Contract — Diagnosis & Proposed Architecture

## The contract (what the system is *supposed* to do)

1. Frontend builds a page's HTML slice and extracts **one** canonical text string from it.
2. That string is sent to `/lookup` as `q`.
3. Backend remembers `q` as `original_text`, runs NFKC + language filtering to produce `model_text`, runs Trankit on `model_text`, then remaps every offset back to `original_text` space before responding.
4. Frontend receives offsets that index `q` exactly, and decorates the slice DOM at those character positions.

If this holds, every other concern (NFKC compositions, Arabic diacritic stripping, astral strip, MWT, Trankit whitespace normalization) is internal to step 3 and invisible to the frontend.

---

## Where the contract is actually breaking

### 1. The canonical text is extracted from a *transient* DOM, not the mounted one
Parsers/paginator build a working DOM, run `_finalizePage` (inline flatten + block-separator `\n` insertion + `extractTextAndMap`), then serialize back to an HTML string via `wrap.innerHTML`. That string is later re-parsed into the live DOM when the page is mounted. The HTML parser normalizes whitespace text nodes between block elements — the inserted `\n` text nodes can be merged, repositioned, or dropped on the round-trip. Result: `page.text` (and the `path` indices in `page.textMap`) describe a DOM that no longer exactly matches the live mounted DOM.

### 2. The backend silently replaces `original_text` for Sanskrit
`build_preprocess_context` does `true_original = normalized` after Devanagari→IAST transliteration. The client sent Devanagari, the server's `original_text` is now IAST, and the response's `q`/`segments`/`segment_offsets` are in IAST space. The frontend's slice DOM is still Devanagari. Contract broken — offsets cannot land.

### 3. The frontend has its own normalization + remap layer
`buildFrontendLookupNormalizationMap` + `remapLookupResponseOffsetsToOriginalText` (`reader.js`) NFKC-normalize the slice text again, score offsets against both spaces, and may remap a second time. This duplicates the server's job and can double-remap when its heuristic misclassifies already-original offsets.

### 4. DOM is mutated *after* decoration is computed
`splitTokenSpanByLines` (DOCX line-wrap re-splitting) and any post-mount layout shifts (images loading, lazy resources) change the live tree. Path-based resolution in `buildCanonicalTextRunsFromMap` then resolves to the wrong nodes or returns null.

### 5. `offsetsAreValid` rejects valid Trankit output
The validator requires monotonic, non-overlapping `segment_offsets`. MWT children with shared/overlapping spans (French clitics, Arabic clitics) trip it and the entire decoration is silently skipped.

### 6. Path-based node resolution is brittle
`textMap` paths are sequences of `childNodes` indices. Any insertion of even one node before/inside the slice root (annotation overlay, ruler, debug element) shifts every path. The PDF builder hard-codes `[0, childIndex, 0]`, assuming a fixed wrapper depth.

---

## Proposed architecture: one canonical pair, captured from the live DOM

The fix is structural: produce the canonical text and the DOM mapping from the **same** DOM the user is looking at, at the moment of lookup, and never round-trip through an HTML string.

### Step-by-step

1. **Build the slice DOM** (parser per format, paginator if needed) — same as today, except *do not* call `_finalizePage` inside the working DOM and *do not* extract text yet.
2. **Mount the slice DOM directly into `#renderedText`** as a detached `DocumentFragment` or by `appendChild`-ing the actual nodes — never via `innerHTML = htmlString`. The nodes the user sees are the same nodes the parser built.
3. **Run `_finalizePage` on the mounted root** (inline flatten + block-separator insertion). This mutates the live tree once, before any extraction.
4. **Walk the mounted root once** with the `LOOKUP_NONTEXT_TAGS` filter and produce `(canonicalText, textRuns)` in a single pass:
   - `canonicalText` is the concatenated `nodeValue`s.
   - `textRuns` is an array of `{ node: <live Text node ref>, start, end }` — direct references, no paths.
5. **Send `canonicalText` to `/lookup` as `q`.**
6. **Backend** normalizes, runs NLP, remaps to `original_text == q`, returns offsets in `q` space — unchanged conceptually, but with two fixes:
   - For Sanskrit, do not overwrite `true_original`; build a `model_to_orig` map from IAST positions back to the original Devanagari positions (mirroring the per-char NFKC strategy already used for other languages). Either that, or move Sanskrit transliteration to the frontend so the client sends IAST itself.
   - Stop forcing `segments[i]` rebuild from offsets when offsets degenerate to zero-length — let the caller see the bug rather than masking it.
7. **Frontend decoration** uses `textRuns` directly:
   - Walk segments in order, advance through `textRuns` until each segment's `[start, end)` is located, split the live text node at those exact offsets, wrap in `<span class="reader-token">`. No path resolution, no second TreeWalker, no re-extraction.
8. **No client-side normalization or remap.** Delete `buildFrontendLookupNormalizationMap`, `remapLookupResponseOffsetsToOriginalText`, `normalizeFrontendLookupSlice`, and the `_frontend_offsets_*` flags. The server is the only authority.
9. **Replace `offsetsAreValid` with a permissive variant** that allows MWT-style overlapping spans (only require `0 ≤ start ≤ end ≤ q.length`). Accept that segments can share or overlap source ranges.
10. **Lock the slice DOM during decoration.** Defer `splitTokenSpanByLines` and any other post-decoration mutation until after `applyOffsetsAsTokenSpansOnDom` finishes registering spans, and re-derive line splits from the spans, never from the original text nodes.

### What this guarantees

- `q` is byte-identical to the textContent of the mounted DOM at lookup time.
- Every offset returned by the backend indexes a live node reference held in `textRuns`, so decoration is a pure offset-to-node mapping with zero pathwalking.
- All normalization (NFKC, astral strip, Arabic diacritics, punct strip, Devanagari→IAST) lives in exactly one place (the backend) and is invisible to the frontend because the contract is enforced.
- DOM mutations between mount and decoration cannot desync anything, because text nodes are referenced directly and `_finalizePage` is the *last* mutation before extraction.

### What to delete

- `page.html` as a serialized string round-trip — pages carry live DOM fragments instead.
- `_prefixTextMap`, `locateCanonicalTextNodeByPath`, `buildCanonicalTextRunsFromMap` (path-based resolution).
- The entire client-side normalization/remap layer in `reader.js`.
- The `true_original = normalized` line in Sanskrit handling.

### What to keep

- `_flattenInlineWrappers`, `_insertBlockSeparators`, `extractTextAndMap` walk logic — but invoked once on the mounted DOM, returning live node refs.
- Per-format parsers — but they return DOM fragments, not HTML strings.
- The backend `model_to_orig` machinery — it already does the right thing for every language except Sanskrit.
