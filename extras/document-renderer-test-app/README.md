# Document rendering and annotation geometry

I built this development application to work through a central reading-interface
problem: keeping annotations attached to source text as documents change format,
page size and layout. It separates format parsing, canonical text, browser geometry
and annotation placement.

```text
PDF / EPUB / DOCX / HTML / Markdown / plain text / captured URL
  → format adapter
  → canonical sections, blocks and source offsets
  → reflowable columns or fixed-layout pages
  → visible text ranges and character boxes
```

## One text model across formats

Each adapter produces a `CanonicalDocument` with sections, blocks, `canonicalText`
and a `sourceMap`. Blocks carry `canonicalStart` and `canonicalEnd` offsets, so
annotation identity can be expressed independently of page breaks and DOM nodes.

| Input | Conversion |
|---|---|
| Plain text | Preserves blank lines, indentation, headings and verse-like blocks |
| HTML and captured URLs | Sanitizes markup and converts document structure into canonical blocks |
| Markdown | Converts Markdown to HTML before using the HTML adapter |
| EPUB | Reads the OPF spine through JSZip and converts its XHTML sections in reading order |
| DOCX | Uses docx-preview for visual HTML, with a Mammoth conversion fallback |
| PDF | Uses PDF.js text extraction to build fixed-layout pages with positioned text items |

The [format adapters](src/adapters/) feed the common
[canonical model](src/canonical.js). Format-specific parsing ends at that boundary;
pagination and annotation operate on the shared representation.

## Pagination and source alignment

The reflowable renderer uses CSS columns for browser text shaping, bidirectional
layout and line breaking. Its measuring flow and visible pages share an explicit
`contentWidth + columnGap` step, keeping navigation aligned with the measured columns.
PDF pages instead retain fixed positions and their own canonical text slices.

Text-run spans carry source offsets. DOM ranges provide word and character boxes
for connecting visible text to those offsets, and the annotation layer selects
tokens by intersection with each page's canonical range. The separate alignment
utility compares normalized text when locating a page slice.

## Imported-page handling

Before pagination, the renderer removes scripts, frames and embedded objects,
converts navigation links into inert spans, and replaces form controls with text
placeholders. That gives imported content the same document interactions as the
other formats.

| Source | Responsibility |
|---|---|
| [canonical.js](src/canonical.js) | Sections, blocks, canonical offsets and source maps |
| [renderer.js](src/renderer.js) | Page geometry, inert content, text-run mapping and character boxes |
| [align.js](src/align.js) | Normalized text alignment and development token fixtures |
| [annotator.js](src/annotator.js) | Range selection and token markup |

This study records the document and layout mechanisms. The integrated reader's
neural analysis and lexical lookup are described in the
[application construction guide](../../docs/BUILD_PROCESS.md).
