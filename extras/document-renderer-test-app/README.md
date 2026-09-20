# Canonical Document Renderer Test App

Prototype for an NLP-powered translation workbench renderer.

It demonstrates this pipeline:

```txt
PDF / EPUB / DOCX / TXT / HTML / Markdown / URL-imported web pages
→ format adapter
→ CanonicalDocument
→ canonical text + block/range map
→ paginated browser render
→ page text slice + token ranges + optional character boxes
```

## Run

```bash
cd document-renderer-test-app
npm test
npm run start
```

Then open:

```txt
http://localhost:4173
```

The URL importer uses the local Node dev server as a same-origin proxy at `/api/fetch-url?url=...`, so normal browser CORS rules do not block testing. Production should replace this with a hardened fetch service.

The browser app uses CDN builds of permissive/free libraries for parsing/rendering:

- JSZip for EPUB/DOCX container reading
- DOMPurify for HTML sanitation
- marked for Markdown
- mammoth and docx-preview for DOCX
- pdf.js for PDF text extraction

For a production app, vendor/pin these dependencies locally rather than relying on CDNs.

## Supported inputs in this prototype

| Format | Adapter behavior |
|---|---|
| TXT/raw text | Built-in parser preserves blank lines, indentation, headings, verse-like blocks |
| HTML/XHTML | Sanitized DOM to canonical blocks while keeping inner HTML |
| URL import | Local dev proxy fetches remote HTML, resolves relative links/images, strips scripts/viewer sludge, then uses the same HTML adapter |
| Markdown | Markdown to HTML, then HTML adapter |
| EPUB | Reads OPF spine with JSZip, converts XHTML spine items through HTML adapter |
| DOCX | Uses docx-preview for visual HTML when available; falls back to mammoth |
| PDF | Uses pdf.js textContent extraction into fixed-layout page objects |

## Canonical model

The core model is in `src/canonical.js`.

Important fields:

```ts
type CanonicalDocument = {
  title: string;
  sourceType: string;
  metadata: object;
  sections: CanonicalSection[];
  canonicalText: string;
  sourceMap: SourceMapEntry[];
  fixedLayoutPages?: FixedLayoutPage[];
};
```

Each block gets stable `canonicalStart` / `canonicalEnd` offsets. NLP tokens should attach to these offsets, not to the rendered DOM.

## Renderer model

The reflowable renderer uses CSS columns so the browser handles line breaking, fonts, bidi text, shaping, CJK wrapping, and pagination. It then uses DOM `Range.getClientRects()` to collect word and character boxes.

PDF uses a fixed-layout adapter in this prototype: each PDF page becomes a fixed HTML page with positioned text items and a canonical text slice.

## What this is

A serious test harness for the architecture:

```txt
canonical document model
+ browser pagination
+ text/range mapping
+ page-level NLP annotation plumbing
```

## What this is not yet

It is not a production-perfect GroupDocs/Aspose replacement. Full fidelity DOCX and PDF rendering requires deep layout engines. This prototype preserves practical reader structure and exposes the right data model so you can test whether this architecture is worth hardening.

## Next hardening steps

1. Vendor dependencies locally.
2. Add worker-based parsing for large books.
3. Add IndexedDB cache keyed by file hash + render options.
4. Split EPUB/DOCX chapters into lazy sections.
5. Add annotation overlay mode that does not mutate the text DOM.
6. Add robust PDF canvas background rendering beneath the text layer.
7. Add a deterministic alignment layer for page text ↔ canonical text.


## Geometry note

The reflowable renderer now paginates inside a content-column viewport rather than a padded whole-page strip. The hidden measuring flow and the visible page clone use the same explicit `contentWidth + columnGap` step, so next/previous navigation cannot drift between columns because of padding, margins, scrollbar width, or device-pixel rounding.

## URL reader sandbox patch

URL imports are converted into inert reader content before pagination. The renderer now:

- removes scripts/iframes/embedded objects;
- converts live `<a href>` links into inert `<span class="reader-inert-link" data-href="...">` nodes;
- removes form controls and replaces them with inert text placeholders;
- wraps rendered text runs in `<span class="reader-text-run" data-canonical-start="..." data-canonical-end="...">` so page text can be mapped back to canonical character offsets;
- automatically samples current-page character boxes in the right rail.

This is closer to the intended production architecture: imported URLs are not a browser surface, they are sandboxed reader documents with canonical offset metadata.
