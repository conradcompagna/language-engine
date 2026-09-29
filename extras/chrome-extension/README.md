# Web-page capture

A Manifest V3 Chrome extension that saves the current web page as a single static
HTML file, with its text, styling and images, for opening in the reader.

## Capture pipeline

1. The service worker selects the active HTTP(S) tab and injects the page freezer.
2. The freezer materializes common lazy-load attributes and clones the rendered DOM.
3. It removes scripts, inline event handlers, executable URLs and preload links,
   then resolves relative URLs against the source page.
4. It inlines reachable stylesheets, images and CSS assets, with selected computed
   styles preserving visual details that depend on the original page environment.
5. Frame snapshots are collected where browser access permits; inaccessible content
   remains inert, and assets that cannot be embedded retain their absolute URLs.
6. The worker serializes the result and saves it through Chrome's downloads API.

The output is a document snapshot: page text, styling and captured resources.
JavaScript application state is not part of that representation.

## Implementation

| Source | Responsibility |
|---|---|
| [background.js](background.js) | Tab selection, isolated resource-fetch bridge, frame coordination and download |
| [freeze.js](freeze.js) | DOM cloning, asset embedding, URL rewriting and static serialization |
| [popup.js](popup.js) | Capture interaction and progress |
| [manifest.json](manifest.json) | Manifest V3 service worker, permissions and extension entrypoints |
| `popup.html`, `popup.css` | Popup interface |
| `options.html`, `options.js`, `options.css` | Settings page |
