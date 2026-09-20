# MWT System: End-to-End Data Flow

## 1. Trankit Output (raw)

Trankit runs NLP on the input text and returns a doc with `sentences[].tokens[]`. For languages like Arabic, French, Hebrew etc., Trankit performs **multi-word token expansion**: a surface token like `وعبيده` ("and his slaves") gets split into its morphological subwords.

Trankit represents this as a single token dict with:
- `id`: a range tuple like `(11, 13)` — indicating subwords 11, 12, 13
- `text`: the original surface form `"وعبيده"`
- `expanded`: a list of subword dicts, each with its own `id`, `text`, `upos`, `xpos`, `feats`, `head`, `deprel`, `lemma`, `span`, `dspan`, `ner`

Each subword is a fully independent syntactic word in UD terms. Each has its own dependency head (which may point inside or outside the MWT range) and its own morphological features.

## 2. MWT Adapter (`trankit_mwt_expansion.py` → `maybe_expand_mwt_doc`)

This module collapses the expanded subwords back onto the original surface tokens so the UI displays surface forms, not subword fragments.

**Pass 1** iterates the sentence tokens. For each MWT token:
- Stores the original surface text as the token text
- Saves the expanded children as `mwt_expanded_words` and `mwt_expanded_texts` on the parent
- Builds a `word_to_surface` map: subword ID → surface token index (1-based)
- Derives approximate character spans for each child from the parent's span

For non-MWT tokens, maps their ID to themselves.

**Pass 2** collapses word-level grammar back onto each surface token:
- **Head/deprel**: `_choose_representative_word` picks the subword whose `head` points outside the MWT range (or head=0 for root). That subword's head gets remapped to a surface index via `word_to_surface` and set as the parent's `head`. (Added recently: non-representative subwords whose heads also exit the MWT are saved as `mwt_extra_edges` on the parent.)
- **deprel, upos, xpos, feats, lemma**: `_collapse_value` joins all subword values with `+`. Internally it calls `_collect_unique_values`, which **deduplicates** — if two subwords share the same value string, only one copy survives.

### Known bugs in Pass 2

1. **Deduplication drops repeated tags.** `_collect_unique_values` deduplicates on the entire value string. If subword 1 has `deprel=nmod` and subword 2 also has `deprel=nmod`, the output is just `nmod` instead of `nmod+nmod`. This means the pill count in the UI doesn't match the subword count. Same issue for upos, xpos, and feats.

2. **Feats `_` values are silently dropped.** `_collect_unique_values` skips values that are `"_"` (the UD placeholder for no features). Many function-word subwords (ADP, CCONJ, SCONJ) have `feats=_`, so their bundle is simply absent. For a 3-subword MWT where the first subword has `_` feats, the output has only 2 bundles — misaligned with the 3 pills shown for UPoS/XPoS.

## 3. Pipeline Processing (`pipeline_common.py` → `process_lookup_nlp_only`)

After `maybe_expand_mwt_doc` returns the collapsed doc, `process_lookup_nlp_only` does two things with the surface tokens:

### `build_results_by_seg` (line 1336)
Iterates collapsed tokens, reads `upos`, `xpos`, `deprel`, `feats`, `lemma` from the surface token (these are the `+`-joined strings from Pass 2). Calls `_stringify_ud_feats(tok.get("feats"))` which, since feats is already a string, returns it as-is. Builds a result entry per segment with dictionary data + POS data:
- `entry["upos"]`, `entry["dep"]`, `entry["tag"]`, `entry["feats"]`, `entry["lemma"]` — all the `+`-joined strings

### `build_ud_overlay` (line 615)
Iterates the same collapsed tokens and builds the tree structure:
- `tokens[]`: one entry per segment with `i`, `text`, `upos`, `tag` (xpos), `dep` (deprel), `lemma`, `feats`, `head`
- `edges[]`: one edge per non-root token: `{from: head_global, to: global_idx, dep: deprel, upos: upos}`
- Recently added: also emits extra edges from `tok.mwt_extra_edges` (for the 15.55% of Arabic MWTs where multiple subwords' heads exit the range)
- `roots[]`, `sentences[]`, `ents[]`

**Only one main edge** is emitted per surface token — the representative subword's dependency arc. The `mwt_extra_edges` addition emits secondary arcs for multi-exit subwords, but these are new and untested.

## 4. JSON Response

The `/lookup` route returns (after JS hybrid interception adds dictionary data):
```
{
  results_by_seg: [...],   // per-segment dictionary + POS entries
  ud_overlay: {            // tree structure
    tokens: [...],
    edges: [...],
    roots: [...],
    sentences: [...],
    ents: [...]
  },
  segments: [...],
  ...
}
```

## 5. Frontend Rendering (`reader.js`)

### Grammar Popup (`buildGrammarPopupHtml`, line 2413)

Receives `posData` (from `resolveSegmentPosData`, which prefers `udTok` fields from the overlay then falls back to `res` fields from `results_by_seg`) and `udTok` (the overlay token).

For each field:
- **Dep** (line 2441): Splits `depLabel` on `+`, looks up each tag in `TRANKIT_TAGS.DEP` via `getDependencyHoverText`, renders as side-by-side pills.
- **UPoS** (line 2457): Splits on `+`, looks up color per tag, renders as colored pills.
- **XPoS** (line 2472): Splits on `+`, looks up each in `TRANKIT_TAGS.XPOS` via `getXposDescription`, renders as pills.
- **Feats** (line 2489): Splits on `+` first to get per-subword bundles, then each bundle splits on `|` for individual `Key=Val` features. Each feature is looked up in `TRANKIT_TAGS.FEATS` via `getFeatDescription`. One row per bundle.
- **Lemma** (line 2513): Displayed as-is (the `+`-joined string renders with `+` signs visible between subword lemmas).

### Dependency Tree Arcs

`ud_overlay.edges` drives the SVG arc drawing. Each edge becomes a curved line from `from` to `to` with the dep label shown on hover. Currently one arc per surface token (the representative's), plus any `mwt_extra_edges` arcs.

## 6. What 2-Subword Tokens Get Right (That 3+ Don't)

For a typical 2-subword Arabic MWT like `لتصنيع` (ل + تصنيع):
- Both subwords have different feats strings → dedup keeps both → 2 bundles in `+`-join
- Both subwords have different deprel/upos → dedup keeps both → correct pill count
- One subword's head is internal, one exits → representative chosen correctly → one arc

For a 3-subword MWT like `وعبيده` (و + عبيد + ه):
- CCONJ subword may have `feats=_` → dropped by `_collect_unique_values` → only 2 feats bundles for 3 subwords
- If two subwords share `deprel=nmod`, dedup collapses to one → 2 dep pills for 3 subwords
- Multiple subwords may exit the MWT range → only representative gets an arc (others need `mwt_extra_edges`)

The root cause of all display mismatches is `_collect_unique_values` deduplicating and skipping `_`.
