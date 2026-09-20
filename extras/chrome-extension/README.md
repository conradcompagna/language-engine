# Language Engine Capture - Chrome extension

Captures the active web page and downloads it as a standalone `.html` file.

The extension injects a page freezer into the current HTTP(S) tab, serializes
the rendered DOM, inlines reachable page assets where possible, strips active
script behavior, and saves the result through Chrome's downloads API.

This is not derived from the GPL'd SingleFile codebase. It is a clean
implementation targeting this app's page-capture needs.

---

## Current behavior

When you click **Capture page** in the popup:

1. The background service worker checks that the active tab is an HTTP(S) page.
2. The extension injects `freeze.js` into the active page.
3. The freezer:
   - Materializes common lazy-load attributes.
   - Clones `document.documentElement`.
   - Removes scripts, inline event handlers, preload/prefetch links,
     `javascript:` URLs, and document CSP meta tags.
   - Resolves relative URLs to absolute URLs.
   - Inlines reachable stylesheets, CSS URL assets, images, and selected visual
     computed styles.
   - Converts readable iframe content where available and leaves blocked frames
     inert.
   - Adds capture metadata and freeze CSS.
4. The service worker downloads the serialized page as a local `.html` file.

There is no current upload/send-to-server flow in the extension UI.

---

## Installing for testing

1. Open Chrome and go to `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select this `chrome_extension/` folder, the folder containing
   `manifest.json`.
5. Pin **Language Engine Capture** from Chrome's extensions menu if desired.

Edge, Brave, and other Chromium browsers use the same unpacked-extension flow.

---

## Capturing a page

1. Browse to a normal `http://` or `https://` page.
2. Click the extension icon, or press `Ctrl+Shift+L`.
3. Click **Capture page**.
4. Chrome downloads the captured page as a `.html` file.

Chrome blocks extension injection on `chrome://`, `chrome-extension://`, Chrome
Web Store pages, and some browser-managed viewer pages.

---

## Keyboard shortcut

`Ctrl+Shift+L` opens the extension popup. You can rebind it at
`chrome://extensions/shortcuts`.

---

## Known limitations

- Cross-origin asset fetches use the browser's extension fetch path. If a site
  blocks an asset request, that asset may remain as an absolute URL in the
  captured HTML.
- Some iframes cannot be serialized because browser security boundaries block
  direct access to their contents.
- Dynamic application state that only exists in JavaScript runtime memory may
  not be fully preserved after scripts are stripped.
- Video and audio are made inert in the static capture.

---

## Files

```
chrome_extension/
  manifest.json
  background.js
  freeze.js
  popup.html / popup.css / popup.js
  options.html / options.css / options.js
  icons/
  README.md
```

No build step is required.
