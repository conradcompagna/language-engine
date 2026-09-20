# Extras

Two complete applications that are neither part of the deployed service nor research
infrastructure. They are here because each stands on its own.

## `chrome-extension/`

A Manifest V3 Chrome extension that captures the current page and hands it to the
reader, preserving layout so lookups land on the right text. `freeze.js` is the capture
implementation.

## `document-renderer-test-app/`

A self-contained Node harness for the document ingestion layer, with one adapter per
format — PDF, EPUB, DOCX, HTML, Markdown, plain text, and live URL — plus the canonical
model, the annotator, the aligner and a smoke test. It runs without model weights or
dictionaries, which makes it the quickest way to see how documents become annotatable
text.

```sh
cd extras/document-renderer-test-app
npm install && node scripts/dev-server.mjs
node --test test/smoke.test.mjs
```
