# Private HTML captures

The optional server capture API accepts snapshots only from authenticated users.
The published Chrome extension downloads files locally and does not use this API.

An authenticated client first requests `GET /api/extension_capture_token`, then sends
the returned `csrfToken` in `X-CSRF-Token` with its session cookie when posting JSON
to `/api/extension_capture`. Reading either returned URL requires the same account;
an unguessable record URL is not an access credential.

Snapshots pass through an HTML5-parser allowlist before storage. Scripts, event
handlers, forms, nested documents, SVG/MathML, navigation links and external image
URLs are removed. Inline styles and stylesheets remain available for frozen layout;
the document content policy blocks external resources, connections and scripts.
Only embedded raster images are supported. Fonts must be embedded to load.

The direct viewer additionally uses a response-level CSP sandbox with an opaque
origin. The reader JSON response contains the same sanitized document and a CSP
meta element, and must still be displayed in the reader's script-disabled iframe.
These protections apply independently of the capture extension's own filtering.

Defaults are 16 MiB per sanitized capture, 64 MiB total, 16 records, a fixed one-hour
lifetime, and four attempted uploads per account per minute. JSON request size is
bounded before parsing; reads enforce expiry and do not extend it. The in-memory
store is per process, matching the current single-worker deployment template;
multi-worker hosting would require shared storage and a shared rate limiter.

These are source changes for a future release; they do not alter an existing live
deployment. Direct public snapshot links and anonymous server uploads are
intentionally unsupported by the secured API.
