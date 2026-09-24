# Dictionary rendering architecture

The reader presents dictionary results in document popups and a persistent
side panel. Both consume hydrated entry data with explicit source, matched-form,
and lemma fields; [the hydration contract](HYDRATION_FIRST_RENDERING_REFERENCE.md)
defines those fields.

## Feature ownership

| Responsibility | Source |
|---|---|
| Popup construction and per-token result selection | [dictionary-popup.mjs](../../frontend/reader/dictionary-popup.mjs) |
| Dictionary template selection and side-panel presentation | [side-panel.mjs](../../frontend/reader/side-panel.mjs) |
| Sense lines, stacked entries, and annotation presentation | [annotations.mjs](../../frontend/reader/annotations.mjs) |
| Entry forms and editing | [entry-forms.mjs](../../frontend/reader/entry-forms.mjs), [entry-editing.mjs](../../frontend/reader/entry-editing.mjs) |
| Segment and fill presentation | [segment-rendering.mjs](../../frontend/reader/segment-rendering.mjs), [fill-rendering.mjs](../../frontend/reader/fill-rendering.mjs) |
| Shared Wiktionary-style dictionary adapter | [reader_wikt.js](../../static/reader_wikt.js) |
| Entry grouping and display normalization | [entry-adapters.mjs](../../frontend/dictionary/client/entry-adapters.mjs) |
| Hover positioning and events | [hover-layout.mjs](../../frontend/reader/hover-layout.mjs), [hover-interaction.mjs](../../frontend/reader/hover-interaction.mjs) |

## From lookup result to popup

`buildPopupForWord()` selects the relevant result and its fill entries for a
visible token. `renderDictTemplate()` selects the registered dictionary adapter
or the shared template. Sense rendering handles headings, readings, glosses,
morphology, and related forms; the surrounding reader modules manage hover
position, pinning, and side-panel navigation.

The source entry's `source` field travels through hydration and client entry
normalization. Segment and fill objects carry dictionary provenance alongside
their lexical content, allowing presentation to distinguish dictionary sources,
generated entries, and user-authored entries.

## State and validation

Feature modules import shared functions explicitly and store mutable state in
adjacent `*.state.mjs` modules. [reader/index.mjs](../../frontend/reader/index.mjs)
initializes the interface. The build produces the script URL used by the Flask
template; source maps connect browser behavior to the maintained modules.

[Browser fixtures](../../tests/browser/) exercise
rendering and document interaction with synthetic local responses. Dictionary
regressions check form selection, compact identity, and hydration independently
of neural model loading. The [document guide](LOOKUP_RENDERING_PIPELINE_MAP.md)
covers how source pages provide the text and geometry used by these overlays.
