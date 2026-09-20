# Document Capture Fidelity Suggestions

This is a documentation-only pass over the top lookup/source pane. The short version is that most non-web document paths are close to their practical fidelity ceiling, and the remaining useful gains are mostly navigation/search ergonomics. Website capture is the one path with real visual-fidelity headroom.

Local files inspected for this pass:

- `chrome_extension/freeze.js`
- `chrome_extension/background.js`
- `chrome_extension/popup.js`
- `chrome_extension/options.js`
- `chrome_extension/README.md`
- `SingleFile-master.zip`
- `static/foliate-js/search.js`
- `static/foliate-js/footnotes.js`
- `static/foliate-js/README.md`
- `static/reader.js`
- `static/docrender/parsers.js`

## Overall Take

The main improvement that should apply across formats is a unified top-pane navigation strip:

- Search field.
- Previous/next match controls.
- Match count.
- Optional results dropdown with excerpt and page/section target.
- Optional table-of-contents dropdown when the source format exposes one.

This is not really a layout-fidelity change, but it is the most valuable top-pane usability improvement for TXT, DOCX, Foliate ebooks, and frozen websites. PDF already has its own PDF.js search path, so PDF can stay separate unless you want a visually unified control shell.

For visual fidelity:

- Plain text has almost no remaining fidelity upside.
- TXT into Foliate has almost no remaining fidelity upside beyond search and basic generated headings.
- DOCX through Mammoth can improve semantically, but not become Word-layout-faithful without changing renderer strategy.
- Native ebooks through Foliate are probably near the practical limit, with search, TOC, page list, and footnote handling still worth exposing.
- PDF top rendering is already best handled by PDF.js.
- Frozen websites have the largest remaining gains.

## Plain Text And TXT Through Foliate

There is not much layout fidelity to capture here because plain text has little inherent layout. The app already turns text into flow sections and lets Foliate paginate it.

The useful gains are navigation features:

- Search across the whole text.
- Results shown as page/section ranges.
- Jump to result.
- Highlight current match in the top pane.
- Optional generated outline from simple heuristics, such as lines that look like headings.

The search implementation should not be PDF-specific. For Foliate-backed text, the natural model is section text search over the generated Foliate book sections, then `goTo` the section/range that contains the match.

## DOCX Through Mammoth Into Foliate

Mammoth is a semantic DOCX-to-HTML converter, not a Word layout engine. That means the best improvements are about preserving document structure and links, not exact page geometry.

High-value improvements:

- Hook DOCX into the same unified top-pane search as TXT and ebooks.
- Generate a TOC from DOCX headings after Mammoth conversion.
- Preserve and resolve internal anchors for headings, footnotes, endnotes, and cross references.
- Fix the current footnote-link behavior where clicking a note reference jumps to the first page.
- Add a footnote/endnote popover or side drawer instead of navigating away from the reading location.
- Preserve Mammoth conversion messages somewhere in debug diagnostics, since they often explain dropped content or unsupported Word constructs.
- Review Mammoth image handling to ensure embedded images are retained as data URLs or object URLs before Foliate sees the section HTML.
- Add a custom Mammoth style map for common Word styles that should become semantic HTML, especially headings, block quotes, verse, footnotes, and language-specific paragraph styles.

The footnote bug is probably not Mammoth itself. The current synthetic Foliate-flow book in `reader.js` creates section ids like `flow-section-0` and has a simple `resolveHref` that mainly understands those synthetic ids. If Mammoth emits a link like `#footnote-1`, the synthetic book likely does not map that anchor to the section containing the target id, so Foliate falls back to section zero. The fix is to build an id index across generated sections and resolve internal `#id` links to the correct section plus anchor.

If DOCX visual fidelity becomes a major goal, the bigger alternative is a separate top-pane DOCX renderer such as a Word-like renderer, while keeping Mammoth as the semantic text source for lookup. I would not start there. It adds another split between visual rendering and lookup text, and DOCX pagination is not stable without a real Word/LibreOffice layout engine.

## Native Foliate Ebooks

Foliate already exposes most of the useful structure:

- `book.sections`
- `book.toc`
- `book.pageList`
- `book.metadata`
- `resolveHref`
- `resolveCFI`
- `goTo`
- section `createDocument`
- bundled search helpers in `static/foliate-js/search.js`
- footnote handling in `static/foliate-js/footnotes.js`

The likely gains are:

- Search across all sections using Foliate's search utilities.
- TOC dropdown using `book.toc`.
- Page-list dropdown when `book.pageList` exists.
- Metadata display only if it helps navigation, not as a large info panel.
- Better internal-link handling, especially for footnotes, endnotes, gloss notes, bibliography notes, and TOC anchors.
- Optional "current chapter" label derived from TOC/progress.

For visual fidelity, Foliate is already doing the real rendering. The app should avoid trying to infer Foliate's internal page ranges for lookup; the current viewport-walk approach is the right direction. Search/TOC should call Foliate navigation primitives instead of trying to mirror its internal pagination model.

## PDF

PDF top-pane fidelity is already close to the ceiling because PDF.js is the right renderer for the source view. The remaining improvements are mostly polish:

- Keep PDF.js search as the source of truth for PDF search.
- Keep PDF.js zoom and page navigation.
- Avoid trying to re-render PDFs through DocRender for the top pane.
- Continue using the canonical PDF extractor for bottom lookup rendering.

The only realistic fidelity improvement would be to expose more PDF.js viewer controls if users need them, but the visual document rendering itself is already the right approach.

## Frozen Website Capture

Website capture has the most room for improvement. The current extension already does a lot:

- Clones the live DOM.
- Removes scripts and dangerous handlers.
- Inlines stylesheets and CSS `url(...)` resources.
- Converts images to data URLs when possible.
- Captures current image state through `currentSrc`.
- Stamps `data-le-frozen` and Language Engine metadata.
- Applies a curated set of computed visual styles.
- Attempts same-origin and injected-frame snapshots.
- Freezes links/forms/media into a static document.

The biggest remaining fidelity losses are probably from these areas:

- Responsive layout changes when the snapshot is opened in a different iframe width.
- Cross-origin resources that fail in page-context fetches.
- Lazy-loaded assets that were not loaded before capture.
- Shadow DOM and web component internals.
- Pseudo-elements and generated CSS content.
- Canvas/video content.
- Iframe mapping and sandboxed frame capture.
- CSS generated through adopted stylesheets or runtime-injected style systems.
- Fonts loading late or not being embedded.
- Layout-affecting computed styles intentionally not frozen.

## Website Capture Recommendations

### 1. Preserve The Captured Viewport Contract

This is probably the highest-value website fidelity improvement.

A lot of web pages are responsive. If the user captures a page at 1420px wide and the reader iframe later renders it at 760px wide, the page can reflow into a different layout. That is not a capture failure exactly, but it violates the user's expectation that "this is what I was looking at."

Recommendation:

- Store captured viewport width, height, device pixel ratio, and scroll position as metadata.
- In the reader, render the frozen snapshot at its captured layout width.
- Let the top pane scroll horizontally only if necessary, or scale the captured layout down while preserving its internal layout width.
- Make this a web-snapshot-specific rule, not a general document rule.

This preserves the layout decisions made by the original site at capture time.

### 2. Reconnect The Lazy-Load Option

The current extension settings UI still says "Scroll the page before capture", but the active `background.js` does not appear to read that option. The active `freeze.js` also says it does not scroll; it only materializes lazy attributes and fires passive events. A backup copy has the older progressive auto-scroll path.

Recommendation:

- Restore a deliberate "load full page before capture" option.
- Keep it optional because auto-scroll can change page state.
- After auto-scroll, return to the user's original scroll position before cloning.
- Record whether auto-scroll was used in capture metadata.

For long articles, this can materially improve image completeness.

### 3. Add A Background Fetch Bridge For Resources

The freezer currently fetches CSS, images, and fonts from page context. That can be blocked by CORS even though the extension has host permissions.

SingleFile uses a more robust fetch bridge: content code asks extension/background code to fetch resources when page-context fetch cannot. You do not need to copy SingleFile, but the architectural idea is useful.

Recommendation:

- Try page-context fetch first.
- If it fails, ask the extension service worker to fetch the resource using extension host permissions.
- Return bytes/content type to the freezer and inline as data URL.
- Record failed resources in a capture report.

This is likely the biggest improvement for pages where CSS backgrounds, fonts, or CDN images are missing.

### 4. Capture Shadow DOM

Modern sites often render meaningful content inside open shadow roots. A normal `cloneNode(true)` will not serialize shadow DOM internals.

Recommendation:

- During capture, walk elements with open `shadowRoot`.
- Serialize shadow content into declarative shadow DOM where possible.
- If browser support is inconsistent, inline the shadow children into a marked wrapper as a fallback.
- At minimum, detect and report closed shadow roots as fidelity warnings.

This matters for web components, embedded widgets, documentation sites, and modern UI libraries.

### 5. Capture Pseudo-Element Content

CSS `::before`, `::after`, and marker content can contain visible text, icons, bullets, numbering, labels, and quote marks. The DOM text walker cannot see it, and plain DOM cloning does not preserve generated content unless the CSS still applies perfectly.

Recommendation:

- Inspect computed styles for `::before`, `::after`, and `::marker`.
- If generated content is non-empty and not purely decorative, materialize it as real inert spans in the clone.
- Mark generated spans so lookup can optionally ignore or include them consistently.

This improves both visual fidelity and text capture fidelity for heavily styled sites.

### 6. Add Canvas And Video Poster Snapshots

SingleFile's known issues mention canvas and video snapshots as browser-security-sensitive. Your extension currently hides video/audio and does not appear to serialize canvas pixels.

Recommendation:

- For readable canvases, replace with an image generated from `canvas.toDataURL`.
- For videos, capture the current frame to a canvas when permitted, otherwise preserve poster image.
- If capture is blocked by taint/security, leave a marked placeholder and record a warning.

This helps charts, maps, diagrams, and math renderers that draw into canvas.

### 7. Improve Iframe Fidelity

The active extension injects into all frames and tries to match frame snapshots by URL. That is good, but URL matching is fragile when frames share URLs, use `about:blank`, use `srcdoc`, are sandboxed, or navigate dynamically.

Recommendation:

- Match frame snapshots by Chrome frame id when available, not only URL.
- Preserve frame viewport size and scroll position.
- Handle `srcdoc` and `about:blank` frames explicitly.
- For inaccessible frames, use a visual placeholder that includes source URL and dimensions, or optionally use a screenshot fallback.

For reading-focused capture, it is acceptable to skip ads, but not article embeds, code examples, math, or same-site content frames.

### 8. Capture Constructed Stylesheets

Some apps use `document.adoptedStyleSheets` or shadow-root adopted stylesheets. Those rules may not appear as ordinary `<style>` or `<link>` nodes.

Recommendation:

- Read `document.adoptedStyleSheets` and open shadow-root `adoptedStyleSheets`.
- Serialize accessible `cssRules` into frozen `<style>` nodes.
- Record inaccessible stylesheets in diagnostics.

This matters for web components and modern CSS-in-JS systems.

### 9. Add A More Exact Computed-Style Mode

The current freezer intentionally avoids layout-affecting properties like display, position, width, height, margin, padding, flex, grid, font size, font family, line height, and white space. That is a reasonable default because fully freezing layout can make documents brittle and huge.

But for pages where stylesheets fail or responsive layout changes are severe, a heavier "exact mode" could help.

Recommendation:

- Keep the current mode as default.
- Add an optional exact mode that freezes a broader computed-style set.
- Start by adding font properties, white-space, text-align, display, position, flex/grid properties, and dimensions only for elements whose layout differs after a validation render.
- Use capture diagnostics to decide when exact mode is needed.

This should be opt-in because file size and layout brittleness can grow quickly.

### 10. Wait For Fonts And Images To Settle

The active freezer materializes lazy resources but does not clearly wait for `document.fonts.ready` or image decode completion in the current file. A backup version mentions waiting for fonts/images.

Recommendation:

- Wait briefly for `document.fonts.ready`.
- Wait for visible images to decode, with a strict timeout.
- Prefer current rendered image state over original `srcset` after waiting.
- Record timeouts in capture diagnostics.

This reduces captures where text metrics or image boxes shift after serialization.

### 11. Add Capture Diagnostics

Right now a frozen HTML file is accepted if it has the required markers. It would be useful to know whether it is high fidelity.

Recommendation:

- Embed a small JSON diagnostics block in the HTML.
- Include counts for inlined stylesheets, failed stylesheets, inlined images, failed images, fonts, frames, canvases, shadow roots, pseudo-elements, and bytes.
- Show a warning in the app if capture quality is suspect.

This makes fidelity failures debuggable instead of mysterious.

### 12. Offer Two Website Capture Modes

A single capture strategy cannot be best for every site.

Recommended modes:

- Reading mode: preserve full article/page, load deferred content, keep flow layout, smaller output.
- Exact visual mode: preserve captured viewport width, freeze more layout style, capture canvas/video frames, larger output.

The app can default to reading mode and expose exact mode only in the extension.

## Unified Search And TOC Plan

A single top-pane search UI can still dispatch to format-specific engines:

- PDF: keep PDF.js search.
- Native Foliate ebooks: use Foliate section documents and search helpers.
- TXT through Foliate: search generated Foliate sections.
- DOCX through Foliate: search generated Foliate sections and show heading/footnote-aware results.
- Frozen websites: search the frozen iframe DOM text, scroll to the match, and draw a source-pane highlight overlay.

For TOC:

- PDF: optional, if PDF.js exposes outline data through the viewer.
- Native Foliate ebooks: use `book.toc` and `book.pageList`.
- TXT: generated outline only if useful.
- DOCX: generate outline from Mammoth heading output.
- Frozen websites: generate outline from headings and landmark elements in the frozen HTML.

## Priority Order

1. Unified search for Foliate-backed TXT/DOCX/ebooks and frozen websites.
2. TOC dropdown for native Foliate ebooks.
3. DOCX internal anchor/footnote resolver.
4. Website captured-viewport metadata plus reader-side layout-width preservation.
5. Website resource fetch bridge through the extension background worker.
6. Website lazy-load auto-scroll option wired back into the active extension.
7. Website capture diagnostics.
8. Website shadow DOM and adopted stylesheet capture.
9. Website pseudo-element materialization.
10. Website canvas/video snapshots.
11. Optional exact visual mode for hard websites.

## What I Would Not Standardize Yet

I would not try to force every format through one visual renderer. The convergence point should be navigation/search/lookup behavior, not source rendering.

The source renderers should remain specialized:

- PDF.js for PDFs.
- Foliate for ebooks and generated flow documents.
- Web snapshot iframe renderer for frozen websites.
- Plain `renderSegments()` for raw textarea and inspector lookups.

Trying to make these visually identical would likely reduce fidelity. The standardization target should be the user's controls and the lookup output contract.

## Appendix: Library Surfaces We Are Not Fully Using Yet

I checked the active Mammoth browser build loaded by `reader_jshybrid.html`, the vendored `static/foliate-js` modules, and the vendored PDF.js 3.11.174 bundles. This is not a proposal to build features beyond those libraries. It is a sweep of data and hooks they already expose that the app could tap more consistently.

### Mammoth DOCX Surface

Current app usage is narrow: `static/docrender/parsers.js` calls `mammoth.convertToHtml({ arrayBuffer }, { includeDefaultStyleMap: true })`, takes `result.value`, cleans it, wraps it, and feeds the result into the generated Foliate flow document. The app does not appear to keep `result.messages` or pass richer conversion options.

Useful Mammoth data/options not fully used:

- Conversion messages. `convertToHtml()` returns `{ value, messages }`. Messages would explain unsupported Word features, dropped content, unrecognized styles, and image failures. These should at least go into debug diagnostics for DOCX imports.
- Embedded/custom style maps. Mammoth supports `styleMap`, `includeEmbeddedStyleMap`, `includeDefaultStyleMap`, and `readEmbeddedStyleMap()`. This can expose author-defined headings/block semantics when the DOCX contains them. It is most useful for generating a DOCX TOC from converted headings and for preserving meaningful block roles.
- Generated IDs and internal links. Mammoth supports bookmarks, internal hyperlinks, footnotes, and endnotes, with `idPrefix` to keep generated IDs stable and collision-free. The app should preserve those IDs and make the generated Foliate book resolve internal `#id` links to the section containing the target.
- Footnotes and endnotes. Mammoth emits note references and backlinks by default. The earlier footnote bug is likely not that Mammoth lacks the data. It is more likely the synthetic Foliate book currently resolves unknown anchors to section zero.
- Comments. Mammoth ignores comments by default, but can include them if a `comment-reference` style mapping is supplied. This is optional; it may clutter reading, but it is available library data.
- Image metadata and conversion. Mammoth's default image converter embeds images as data URIs. A custom converter can see `contentType`, image bytes/base64, and alt text. The default is probably fine for rendering, but diagnostics could count/flag images.
- Existing inline/block semantics. Mammoth can emit tables, table header/body structure, row/column spans, line breaks, checkboxes, bookmarks, links, bold, italics, underline, strikethrough, superscript/subscript, and some highlighted/small-caps/all-caps data through style mappings.
- Raw text extraction. `extractRawText()` returns plain text with paragraph breaks. This should not replace the visual DOCX path, but it can be useful as a debug comparison when converted HTML looks suspicious.
- Document transforms. `transformDocument` exists but is explicitly unstable. I would avoid relying on it unless a specific class of DOCX files consistently needs a small pre-conversion normalization.

Things I would not use:

- `convertToMarkdown()`. Markdown support is deprecated upstream, and the app no longer supports Markdown as a document path.
- Mammoth as a fallback raw-text loader. DOCX should either convert through Mammoth/Foliate or fail clearly.

Highest-value Mammoth taps:

1. Preserve `result.messages` in debug/import diagnostics.
2. Add an ID index for generated Foliate DOCX sections so `#footnote`, `#endnote`, and bookmark links resolve correctly.
3. Generate a simple DOCX TOC/search scope from Mammoth heading output.
4. Consider `idPrefix` so generated note/bookmark IDs cannot collide with app IDs.

### Foliate E-Book Surface

Current app usage is mostly renderer-level: it imports `view.js`, creates `foliate-view`, calls `view.open(file)` or `view.open(book)`, listens for `load` and `relocate`, uses `prev()`, `next()`, `goTo()`, and then builds lookup content from the visible DOM slice. The generated TXT/DOCX Foliate book implements sections, metadata, `resolveHref`, `splitTOCHref`, and `getTOCFragment`, but it currently sets `toc: []` and its `resolveHref()` mainly understands synthetic `flow-section-N` ids.

Useful Foliate data/hooks not fully used:

- `book.toc`. Native EPUB/MOBI/FB2/CBZ books can expose a real table of contents. The app can use this for a top-pane TOC dropdown without inventing a new parser.
- `book.pageList`. EPUB page-list navigation is separate from rendered page count. If present, it can give real print-page labels or named page targets.
- `book.landmarks`. Foliate uses landmarks to choose a start location. The app could expose landmarks such as cover, bodymatter, title page, or notes when the book provides them.
- `book.metadata`. Foliate exposes title, language, author/creator-style fields, identifiers, and related metadata depending on format. The app uses only a minimal label today.
- `book.rendition` and `book.dir`. Foliate already uses these for fixed-layout/pre-paginated books and RTL/LTR progression. The app should keep reflecting those values in UI state and source-pane behavior rather than guessing.
- `view.lastLocation`. Foliate location data can include section progress, `tocItem`, `pageItem`, CFI, range, current, total, and fraction depending on book type. The app uses parts of this, but could surface TOC/page labels and store CFI-based return positions.
- `view.search(opts)` and `search.js`. Foliate has built-in incremental book/section search using DOM ranges, `Intl.Collator`, and `Intl.Segmenter`. This is the natural search path for native ebooks and for generated Foliate TXT/DOCX sections.
- CFI support. `view.getCFI()`, `view.resolveCFI()`, and EPUB parser CFIs are available for precise positions, bookmarks, search results, and returning to a lookup source location.
- `sections[].createDocument()`. Foliate exposes section documents for search and non-rendered inspection. This is already partly used by Foliate internally and is safer than trying to infer pages from app state.
- `create-overlayer` and `overlayer.js`. Foliate can attach SVG overlays to rendered book pages. This could support source-pane search highlights or lookup highlights without mutating book DOM.
- `FootnoteHandler`. Foliate has a helper for footnote handling that resolves footnote hrefs through the book interface. This may be useful for native ebooks, and the same idea applies to generated DOCX books once their `resolveHref()` is fixed.
- Media overlays and TTS. Foliate can expose media overlays and SSML-oriented TTS helpers. These are probably outside the core reading/lookup fidelity goal, but they are real library surfaces.
- `getCover()`. EPUB/MOBI/FB2/CBZ books can expose a cover blob. This is mostly useful for metadata display, not lookup.

Things I would not use:

- Foliate's dictionary module. The app already has its own dictionary/Trankit pipeline.
- Foliate OPDS/search-feed helpers. They are for remote catalog search, not local document reading.
- Foliate's experimental PDF adapter. The app already has a dedicated PDF.js path.

Highest-value Foliate taps:

1. Use `book.toc`, `book.pageList`, and `book.landmarks` for navigation controls when present.
2. Use `view.search(opts)` for the unified top-pane search path for Foliate-backed EPUB/MOBI/FB2/TXT/DOCX.
3. Store and navigate by CFI/search result targets where Foliate provides them.
4. For generated TXT/DOCX books, build a real internal anchor index and optional generated TOC instead of `toc: []`.
5. Use Foliate overlays for source-pane search/lookup highlights if DOM mutation causes layout drift.

### PDF.js Surface

Current app usage is already relatively strong: it loads PDF.js 3.11.174, embeds `PDFSinglePageViewer`, uses `PDFLinkService`, uses `PDFFindController`, renders text layers, calls `getDocument()`, `getPage()`, and `getTextContent()`, and keeps page dimensions for canonical extraction. In the iframe viewer, `annotationMode` is currently set to `0`, so PDF annotations are disabled in the rendered source pane.

Useful PDF.js data/hooks not fully used:

- Document outline/bookmarks. `pdfDoc.getOutline()` can expose the PDF outline for a top-pane TOC/sidebar.
- Page labels. `pdfDoc.getPageLabels()` can expose Roman numerals, front matter labels, or publisher page labels instead of only numeric page indexes.
- Metadata. `pdfDoc.getMetadata()` can expose title, author, subject, keywords, producer, creation/modification dates, and PDF info dictionary data.
- Attachments. `pdfDoc.getAttachments()` can expose embedded files. This is not central to lookup, but should be detectable for diagnostics.
- Viewer preferences, page mode, and page layout. `getViewerPreferences()`, `getPageMode()`, and `getPageLayout()` can tell whether a PDF requested outlines, thumbnails, two-page layout, or other initial viewing preferences.
- Permissions. `getPermissions()` can indicate copy/print/modify restrictions. The app may still choose its own behavior, but this is useful diagnostic data.
- Destinations and open action. `getDestinations()`, `getDestination()`, and `getOpenAction()` can support outline links, internal named destinations, and correct initial open positions.
- Optional content/layers. `getOptionalContentConfig()` exposes PDF layers. The current path renders the default view, but layer presence could be reported and eventually surfaced.
- Annotations. Page-level `getAnnotations()` and the viewer annotation layer can expose links, highlights, notes, form fields, and other annotations. Since `annotationMode` is disabled, the source pane is currently ignoring this fidelity layer.
- Structure tree. Page-level `getStructTree()` can expose tagged-PDF reading structure. This could help diagnose or improve text order when `getTextContent()` order is poor.
- XFA/forms. PDF.js exports XFA-related APIs. This is probably not worth expanding unless XFA documents are a known target, but the library surface exists.
- Operator lists. `getOperatorList()` is the low-level drawing instruction stream. It is useful for deep debugging visual/text mismatch, not for normal app flow.
- Find controller capabilities. `PDFFindController` already powers search, but it supports case sensitivity, whole-word behavior, diacritic matching, arrays of query strings, match counts, and highlight-all behavior. The UI can expose whichever of these matter.

Things I would not use:

- PDF.js annotation editors. The app is a reader/lookup tool, not a PDF editor.
- PDF JavaScript actions. `getJSActions()`/document JS should remain ignored or diagnostic-only.
- Foliate's experimental PDF path. Keep PDF.js as the dedicated PDF source renderer.

Highest-value PDF.js taps:

1. Add PDF outline and page-label awareness to the existing PDF navigation/search UI.
2. Capture `getMetadata()` and conversion diagnostics for import/debug display.
3. Consider enabling safe annotation/link rendering if source-pane fidelity needs clickable links and visible notes.
4. Use `getStructTree()` as a diagnostic or optional text-order aid for tagged PDFs where geometric text extraction gives poor reading order.

### Cross-Library Standardization Target

The shared layer should not be a shared renderer. The better target is a shared document capability object:

- `title`, `language`, `authors`, and source metadata.
- `toc` entries when the library exposes them.
- `pageLabels` or page-list entries when available.
- `search(query)` returning source locations plus excerpts.
- `goTo(location)` using native locations: PDF destinations/page labels, Foliate hrefs/CFIs, or generated Foliate section anchors.
- `diagnostics` for dropped content, unsupported features, missing resources, messages, annotations, attachments, and layer presence.

That lets PDF.js, Foliate, Mammoth, and the web snapshot renderer remain specialized while the top lookup pane gets the same search/navigation/diagnostic affordances across formats.
