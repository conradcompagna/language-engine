/*
 * freeze.js — DOM freezer / self-contained HTML serializer.
 *
 * Runs in the active tab's MAIN world. Produces a static, self-contained
 * HTML document that visually matches what the user is currently looking at.
 *
 * Design (PDF-style fidelity):
 *
 *   The captured HTML must look right even when re-rendered in a frame of a
 *   different size, with possibly missing CSS, with no JavaScript. The way
 *   to make that work is NOT to strip elements or pin viewports, but to
 *   *bake the visual state into inline styles* on every element. We walk
 *   the live DOM, read computedStyle for a fixed list of visual (non-layout)
 *   properties, and copy those values as inline `style="..."` on the
 *   captured clone. The result renders with the same colors, decorations,
 *   borders, shadows, opacity, and transforms regardless of what CSS rules
 *   the renderer ends up applying.
 *
 * Steps:
 *   1) Trigger lazy resources without scrolling by materializing lazy attrs,
 *      eager-loading media, and firing passive viewport events.
 *   2) Tag every live element with a temporary id so we can map clone→live.
 *   3) Capture the configured visual CSS properties for every live
 *      element plus live image and same-origin iframe state.
 *   4) Clone the document; un-tag the live DOM.
 *   5) On the clone: rewrite img/srcset using captured currentSrc + lazy-
 *      load `data-*` attribute fallbacks; resolve URL attrs to absolute;
 *      apply captured styles inline; strip scripts and inline event handlers;
 *      remove preload/prefetch/etc.; snapshot readable iframes when possible;
 *      convert anchors/forms/media to inert static material.
 *   6) Inline stylesheets (CSS @import + url() → data URIs) and images
 *      (img.src → data URIs) for offline portability.
 *   7) Stamp metadata, freeze CSS (animations/transitions/cursor), serialize.
 *
 * Independent implementation; not derived from any GPL source. The
 * "freeze computed visual styles" technique is inspired by an older
 * Playwright capture pipeline this app used to ship.
 */

(function () {
  const FREEZE_TIMEOUT_MS = 90000;
  const TMP_ID_ATTR = "data-le-tmp-id";

  const MAX_FRAME_SNAPSHOT_DEPTH = 3;
  const RESOURCE_FETCH_REQUEST_EVENT = "le:resource-fetch-request";
  const RESOURCE_FETCH_RESPONSE_EVENT = "le:resource-fetch-response";
  const RESOURCE_FETCH_BRIDGE_ATTR = "data-le-resource-fetch-bridge";
  const RESOURCE_FETCH_BRIDGE_TIMEOUT_MS = 12000;

  // Visual / cosmetic CSS properties to bake inline. Layout-affecting
  // properties (display, position, width, height, margin, padding, flex,
  // grid, font-size, font-family, line-height, white-space) are
  // intentionally excluded — they would over-constrain the snapshot and
  // cause visual artifacts when the renderer reflows.
  const FREEZE_VISUAL_PROPS = [
    "color",
    "background-color",
    "background-image",
    "background-position",
    "background-repeat",
    "background-size",
    "background-clip",
    "background-origin",
    "background-attachment",
    "text-decoration-line",
    "text-decoration-color",
    "text-decoration-style",
    "text-decoration-thickness",
    "text-shadow",
    "border-top-color",
    "border-right-color",
    "border-bottom-color",
    "border-left-color",
    "border-top-style",
    "border-right-style",
    "border-bottom-style",
    "border-left-style",
    "border-top-width",
    "border-right-width",
    "border-bottom-width",
    "border-left-width",
    "border-top-left-radius",
    "border-top-right-radius",
    "border-bottom-left-radius",
    "border-bottom-right-radius",
    "box-shadow",
    "outline-color",
    "outline-style",
    "outline-width",
    "outline-offset",
    "opacity",
    "filter",
    "backdrop-filter",
    "mix-blend-mode",
    "transform",
    "transform-origin",
    "list-style-type",
    "list-style-image",
    "list-style-position",
    "mask-image",
    "mask-position",
    "mask-repeat",
    "mask-size",
    "-webkit-mask-image",
    "-webkit-mask-position",
    "-webkit-mask-repeat",
    "-webkit-mask-size",
    "border-image-source",
    "border-image-slice",
    "border-image-width",
    "border-image-repeat",
    "clip-path",
    "object-fit",
    "object-position",
    "accent-color",
    "caret-color",
    "fill",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-dasharray",
    "stroke-dashoffset",
    "fill-rule",
    "clip-rule",
  ];

  // Property values that mean "default" — skip writing them to keep the
  // serialized HTML smaller without changing visual output.
  const SKIPPABLE_DEFAULTS = {
    "background-image": "none",
    "background-color": "rgba(0, 0, 0, 0)",
    "border-top-style": "none",
    "border-right-style": "none",
    "border-bottom-style": "none",
    "border-left-style": "none",
    "border-top-width": "0px",
    "border-right-width": "0px",
    "border-bottom-width": "0px",
    "border-left-width": "0px",
    "border-top-left-radius": "0px",
    "border-top-right-radius": "0px",
    "border-bottom-left-radius": "0px",
    "border-bottom-right-radius": "0px",
    "box-shadow": "none",
    "text-shadow": "none",
    "text-decoration-line": "none",
    "outline-style": "none",
    "outline-width": "0px",
    "outline-offset": "0px",
    "filter": "none",
    "backdrop-filter": "none",
    "transform": "none",
    "opacity": "1",
    "mix-blend-mode": "normal",
    "list-style-image": "none",
    "mask-image": "none",
    "-webkit-mask-image": "none",
    "border-image-source": "none",
    "clip-path": "none",
    "object-fit": "fill",
    "object-position": "50% 50%",
    "accent-color": "auto",
    "caret-color": "auto",
    "stroke-linecap": "butt",
    "stroke-linejoin": "miter",
    "stroke-dasharray": "none",
    "stroke-dashoffset": "0px",
    "fill-rule": "nonzero",
    "clip-rule": "nonzero",
  };

  const PSEUDO_CAPTURE_PROPS = [
    "display",
    "color",
    "background-color",
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "font-stretch",
    "font-variant",
    "line-height",
    "letter-spacing",
    "word-spacing",
    "text-transform",
    "text-decoration-line",
    "text-decoration-color",
    "text-decoration-style",
    "text-decoration-thickness",
    "text-shadow",
    "vertical-align",
    "white-space",
    "opacity",
    "filter",
    "transform",
    "transform-origin",
  ];

  // Lazy-load attribute names, ordered by preference.
  const LAZY_SRC_ATTRS = [
    "data-src",
    "data-original",
    "data-lazy-src",
    "data-url",
    "data-hi-res-src",
    "data-image",
    "data-full-src",
    "data-defer-src",
    "data-srcurl",
  ];
  const LAZY_SRCSET_ATTRS = ["data-srcset", "data-lazy-srcset"];
  const LAZY_BACKGROUND_ATTRS = [
    "data-bg",
    "data-background",
    "data-background-image",
    "data-lazy-background",
    "data-bg-src",
    "data-original-background",
  ];
  const LAZY_FRAME_SRC_ATTRS = ["data-src", "data-lazy-src", "data-url"];

  // Heuristic placeholder detector — if a src matches this, it's almost
  // certainly a tracking pixel or a lazy-load stub.
  const PLACEHOLDER_SRC_RE = /^(?:data:image\/gif|about:blank|#|\s*)$|placeholder|spacer|transparent|blank\.gif|1x1/i;

  // Resource fetch cache.
  const _resourceCache = new Map();

  // -- URL helpers ---------------------------------------------------------

  function _absoluteUrl(href, base) {
    try {
      if (!href) return null;
      const trimmed = String(href).trim();
      if (!trimmed) return null;
      if (/^(data:|blob:|mailto:|javascript:|tel:|#)/i.test(trimmed)) return trimmed;
      return new URL(trimmed, base || document.baseURI).toString();
    } catch (_) {
      return null;
    }
  }

  function _isSameOrigin(absUrl) {
    try {
      return new URL(absUrl, location.href).origin === location.origin;
    } catch (_) {
      return false;
    }
  }

  // -- Resource fetching --------------------------------------------------
  //
  // Cross-origin CDNs typically allow CORS only for *anonymous* requests
  // (Wikipedia's upload.wikimedia.org is one example). Same-origin requests
  // can benefit from cookies (paywalled assets). We try the most likely-
  // to-succeed credential mode first, fall back to the other.

  async function _fetchOnce(url, credentials) {
    try {
      const resp = await fetch(url, { credentials, redirect: "follow" });
      if (resp && resp.ok) {
        const contentType = resp.headers.get("content-type") || "";
        const blob = await resp.blob();
        const dataUrl = await _blobToDataUrl(blob);
        return { ok: true, contentType, dataUrl };
      }
    } catch (_) {}
    return { ok: false };
  }

  async function _fetchTextOnce(url, credentials) {
    try {
      const resp = await fetch(url, { credentials, redirect: "follow" });
      if (resp && resp.ok) return await resp.text();
    } catch (_) {}
    return null;
  }

  function _fetchViaExtensionBridge(url, responseType) {
    if (!url || /^blob:/i.test(url) || typeof document === "undefined" || typeof document.addEventListener !== "function") {
      return Promise.resolve(null);
    }
    if (!document.documentElement || !document.documentElement.hasAttribute(RESOURCE_FETCH_BRIDGE_ATTR)) {
      return Promise.resolve(null);
    }
    return new Promise((resolve) => {
      const id = "le-rsrc-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
      let settled = false;
      const cleanup = () => {
        try { document.removeEventListener(RESOURCE_FETCH_RESPONSE_EVENT, onResponse); } catch (_) {}
        clearTimeout(timer);
      };
      const finish = (value) => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve(value);
      };
      const onResponse = (event) => {
        const detail = event && event.detail;
        if (!detail || detail.id !== id) return;
        finish(detail);
      };
      const timer = setTimeout(() => finish(null), RESOURCE_FETCH_BRIDGE_TIMEOUT_MS);
      try { document.addEventListener(RESOURCE_FETCH_RESPONSE_EVENT, onResponse); } catch (_) { finish(null); return; }
      try {
        document.dispatchEvent(new CustomEvent(RESOURCE_FETCH_REQUEST_EVENT, {
          detail: { id, url, responseType: responseType || "dataUrl" },
        }));
      } catch (_) {
        finish(null);
      }
    });
  }

  async function _fetchResource(url) {
    if (!url) return { ok: false };
    if (/^(mailto:|javascript:|tel:|#)/i.test(url)) return { ok: false };
    if (/^data:/i.test(url)) return { ok: true, dataUrl: url, contentType: "image/*" };
    if (_resourceCache.has(url)) return _resourceCache.get(url);
    const order = _isSameOrigin(url) ? ["include", "omit"] : ["omit", "include"];
    let result = { ok: false };
    for (const credentials of order) {
      result = await _fetchOnce(url, credentials);
      if (result.ok) break;
    }
    if (!result.ok) {
      const bridged = await _fetchViaExtensionBridge(url, "dataUrl");
      if (bridged && bridged.ok && bridged.dataUrl) {
        result = { ok: true, dataUrl: bridged.dataUrl, contentType: bridged.contentType || "" };
      }
    }
    _resourceCache.set(url, result);
    return result;
  }

  function _blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(reader.error);
      reader.onload = () => resolve(String(reader.result || ""));
      reader.readAsDataURL(blob);
    });
  }

  async function _fetchTextResource(url) {
    if (!url) return null;
    const cacheKey = url + "::text";
    if (_resourceCache.has(cacheKey)) return _resourceCache.get(cacheKey);
    const order = _isSameOrigin(url) ? ["include", "omit"] : ["omit", "include"];
    let text = null;
    for (const credentials of order) {
      text = await _fetchTextOnce(url, credentials);
      if (text != null) break;
    }
    if (text == null) {
      const bridged = await _fetchViaExtensionBridge(url, "text");
      if (bridged && bridged.ok && typeof bridged.text === "string") text = bridged.text;
    }
    _resourceCache.set(cacheKey, text);
    return text;
  }

  // -- CSS rewriting -------------------------------------------------------

  async function _inlineCssUrls(cssText, cssBase) {
    if (!cssText) return "";
    // Resolve @import statements first.
    const importRe = /@import\s+(?:url\()?\s*(['"]?)([^'")\s]+)\1\s*\)?\s*([^;]*);/gi;
    let importsResolved = "";
    let lastIndex = 0;
    let m;
    while ((m = importRe.exec(cssText)) !== null) {
      importsResolved += cssText.slice(lastIndex, m.index);
      const importUrl = _absoluteUrl(m[2], cssBase);
      const mediaSuffix = (m[3] || "").trim();
      if (importUrl) {
        const importedCss = await _fetchTextResource(importUrl);
        if (importedCss) {
          const inlined = await _inlineCssUrls(importedCss, importUrl);
          importsResolved += mediaSuffix
            ? "@media " + mediaSuffix + " {\n" + inlined + "\n}\n"
            : inlined + "\n";
        }
      }
      lastIndex = importRe.lastIndex;
    }
    importsResolved += cssText.slice(lastIndex);

    // Rewrite url(...) references → data URIs.
    const urlRe = /url\(\s*(['"]?)([^'")]+)\1\s*\)/gi;
    const tasks = [];
    importsResolved.replace(urlRe, (full, _q, raw, offset) => {
      const abs = _absoluteUrl(raw, cssBase);
      tasks.push({ offset, length: full.length, abs });
      return full;
    });
    if (!tasks.length) return importsResolved;

    const replacements = await Promise.all(tasks.map(async (t) => {
      if (!t.abs || /^data:/i.test(t.abs)) return null;
      const res = await _fetchResource(t.abs);
      if (res && res.ok) return { ...t, dataUrl: res.dataUrl };
      return { ...t };
    }));

    let out = "";
    let cursor = 0;
    for (let i = 0; i < replacements.length; i++) {
      const r = replacements[i];
      if (!r) continue;
      out += importsResolved.slice(cursor, r.offset);
      const target = r.dataUrl || r.abs;
      out += "url(\"" + String(target).replace(/"/g, "%22") + "\")";
      cursor = r.offset + r.length;
    }
    out += importsResolved.slice(cursor);
    return out;
  }

  // -- Lazy-load triggering ------------------------------------------------
  //
  // Do not scroll or wait. The user decides when the visible page is ready;
  // this only materializes common lazy attrs and fires passive viewport events
  // so already-installed lazy loaders get one last chance before cloning.

  function _triggerLazyResources(rootDoc) {
    const doc = rootDoc || document;
    const base = doc.baseURI || location.href;

    Array.from(doc.querySelectorAll("img")).forEach((img) => {
      const lazySrc = _firstAttr(img, LAZY_SRC_ATTRS);
      const current = img.currentSrc || img.getAttribute("src") || "";
      if (lazySrc && (!current || _isPlaceholderSrc(current, img.naturalWidth || 0, img.naturalHeight || 0))) {
        const abs = _absoluteUrl(lazySrc, base);
        img.setAttribute("src", abs || lazySrc);
      }
      const lazySrcset = _firstAttr(img, LAZY_SRCSET_ATTRS);
      if (lazySrcset && !img.getAttribute("srcset")) img.setAttribute("srcset", lazySrcset);
      try { img.loading = "eager"; } catch (_) {}
      try { img.fetchPriority = "high"; } catch (_) {}
      try { img.decoding = "sync"; } catch (_) {}
    });

    Array.from(doc.querySelectorAll("picture source, source")).forEach((source) => {
      const lazySrcset = _firstAttr(source, LAZY_SRCSET_ATTRS);
      if (lazySrcset && !source.getAttribute("srcset")) source.setAttribute("srcset", lazySrcset);
      const lazySrc = _firstAttr(source, LAZY_SRC_ATTRS);
      if (lazySrc && !source.getAttribute("src")) source.setAttribute("src", lazySrc);
    });

    Array.from(doc.querySelectorAll("iframe, frame")).forEach((frame) => {
      const lazySrc = _firstAttr(frame, LAZY_FRAME_SRC_ATTRS);
      if (lazySrc && !frame.getAttribute("src")) {
        const abs = _absoluteUrl(lazySrc, base);
        frame.setAttribute("src", abs || lazySrc);
      }
      try { frame.loading = "eager"; } catch (_) {}
    });

    Array.from(doc.querySelectorAll(LAZY_BACKGROUND_ATTRS.map((a) => "[" + a + "]").join(","))).forEach((el) => {
      const bg = _firstAttr(el, LAZY_BACKGROUND_ATTRS);
      if (!bg) return;
      const abs = _absoluteUrl(bg, base) || bg;
      const style = el.getAttribute("style") || "";
      if (!/background(?:-image)?\s*:/i.test(style)) {
        el.setAttribute("style", style + (style && !style.trim().endsWith(";") ? ";" : "") + "background-image:url(\"" + String(abs).replace(/"/g, "%22") + "\");");
      }
    });

    const Ev = (doc.defaultView && doc.defaultView.Event) || Event;
    try { doc.defaultView && doc.defaultView.dispatchEvent(new Ev("resize")); } catch (_) {}
    try { doc.defaultView && doc.defaultView.dispatchEvent(new Ev("scroll")); } catch (_) {}
    try { doc.dispatchEvent(new Ev("scroll")); } catch (_) {}
    try { doc.dispatchEvent(new Ev("readystatechange")); } catch (_) {}
  }

  // -- Tagging the live DOM ------------------------------------------------

  function _collectComposedElements(rootDoc) {
    const doc = rootDoc || document;
    const root = doc && doc.documentElement;
    const out = [];
    const seen = new Set();

    function visitRoot(node) {
      if (!node || typeof node.querySelectorAll !== "function") return;
      const batch = [];
      if (node.nodeType === 1) batch.push(node);
      try {
        const found = node.querySelectorAll("*");
        for (let i = 0; i < found.length; i++) batch.push(found[i]);
      } catch (_) {}

      for (let i = 0; i < batch.length; i++) {
        const el = batch[i];
        if (!el || el.nodeType !== 1 || seen.has(el)) continue;
        seen.add(el);
        out.push(el);
        try {
          if (el.shadowRoot) visitRoot(el.shadowRoot);
        } catch (_) {}
      }
    }

    visitRoot(root);
    return out;
  }

  function _queryElementsInclusive(root, selector) {
    const out = [];
    if (!root) return out;
    try {
      if (root.nodeType === 1 && root.matches && root.matches(selector)) out.push(root);
    } catch (_) {}
    try {
      if (typeof root.querySelectorAll === "function") {
        const found = root.querySelectorAll(selector);
        for (let i = 0; i < found.length; i++) out.push(found[i]);
      }
    } catch (_) {}
    return out;
  }

  function _tagLiveDom(rootDoc) {
    const all = _collectComposedElements(rootDoc || document);
    let counter = 0;
    for (let i = 0; i < all.length; i++) {
      all[i].setAttribute(TMP_ID_ATTR, "le" + (counter++));
    }
    return all;
  }

  function _untagLiveDom(rootDoc, taggedElements) {
    const tagged = taggedElements || _collectComposedElements(rootDoc || document);
    for (let i = 0; i < tagged.length; i++) {
      try { tagged[i].removeAttribute(TMP_ID_ATTR); } catch (_) {}
    }
  }

  function _buildLiveElementMap(allLive) {
    const out = new Map();
    for (let i = 0; i < allLive.length; i++) {
      const el = allLive[i];
      const tmpId = el && el.getAttribute && el.getAttribute(TMP_ID_ATTR);
      if (tmpId) out.set(tmpId, el);
    }
    return out;
  }

  // -- Capture: per-img live state and per-element visual styles ----------

  function _captureLiveImageState(allLive) {
    const out = new Map();
    for (let i = 0; i < allLive.length; i++) {
      const el = allLive[i];
      if (!el || el.tagName !== "IMG") continue;
      const tmpId = el.getAttribute(TMP_ID_ATTR);
      if (!tmpId) continue;
      out.set(tmpId, {
        currentSrc: el.currentSrc || el.src || "",
        naturalWidth: el.naturalWidth || 0,
        naturalHeight: el.naturalHeight || 0,
      });
    }
    return out;
  }

  function _captureCanvasState(allLive) {
    const out = new Map();
    for (let i = 0; i < allLive.length; i++) {
      const el = allLive[i];
      if (!el || el.tagName !== "CANVAS") continue;
      const tmpId = el.getAttribute(TMP_ID_ATTR);
      if (!tmpId) continue;
      try {
        const dataUrl = el.toDataURL("image/png");
        if (dataUrl && /^data:image\/png/i.test(dataUrl)) {
          out.set(tmpId, {
            dataUrl,
            width: el.width || 0,
            height: el.height || 0,
            ariaLabel: el.getAttribute("aria-label") || el.getAttribute("title") || "",
          });
        }
      } catch (_) {}
    }
    return out;
  }

  function _cssContentToText(content) {
    content = String(content || "").trim();
    if (!content || content === "none" || content === "normal" || content === "''" || content === '""') return "";
    if (/^url\(/i.test(content) || /counter\(/i.test(content)) return "";
    if (content === "open-quote") return "\u201c";
    if (content === "close-quote") return "\u201d";
    if (content === "no-open-quote" || content === "no-close-quote") return "";

    let text = "";
    const re = /"((?:\\.|[^"\\])*)"|'((?:\\.|[^'\\])*)'/g;
    let m;
    while ((m = re.exec(content)) !== null) text += _unescapeCssString(m[1] != null ? m[1] : m[2]);
    if (text) return text;

    // Last resort for already-resolved plain text values. Avoid functional CSS.
    if (/^[a-z-]+\(/i.test(content)) return "";
    return content;
  }

  function _unescapeCssString(value) {
    return String(value || "").replace(/\\([0-9a-fA-F]{1,6}\s?|.)/g, (_m, esc) => {
      if (/^[0-9a-fA-F]/.test(esc)) {
        const cp = parseInt(esc.trim(), 16);
        if (!Number.isFinite(cp)) return "";
        try { return String.fromCodePoint(cp); } catch (_) { return ""; }
      }
      if (esc === "n") return "\n";
      if (esc === "r") return "\r";
      if (esc === "t") return "\t";
      return esc;
    });
  }

  function _serializePseudoStyle(cs) {
    let style = "";
    for (let i = 0; i < PSEUDO_CAPTURE_PROPS.length; i++) {
      const prop = PSEUDO_CAPTURE_PROPS[i];
      const value = cs.getPropertyValue(prop);
      if (!value) continue;
      const def = SKIPPABLE_DEFAULTS[prop];
      if (def !== undefined && value === def) continue;
      style += prop + ":" + value + " !important;";
    }
    style += "pointer-events:none !important;";
    return style;
  }

  function _capturePseudoElementText(allLive) {
    const out = new Map();
    const pseudos = ["before", "after", "marker"];
    for (let i = 0; i < allLive.length; i++) {
      const el = allLive[i];
      if (!el || el.nodeType !== 1) continue;
      if (el.closest && el.closest("head")) continue;
      const tmpId = el.getAttribute(TMP_ID_ATTR);
      if (!tmpId) continue;
      const view = (el.ownerDocument && el.ownerDocument.defaultView) || window;
      if (!view || typeof view.getComputedStyle !== "function") continue;
      let record = null;
      for (let p = 0; p < pseudos.length; p++) {
        const name = pseudos[p];
        let cs;
        try { cs = view.getComputedStyle(el, "::" + name); } catch (_) { continue; }
        if (!cs) continue;
        const text = _cssContentToText(cs.getPropertyValue("content"));
        if (!text) continue;
        if (cs.getPropertyValue("display") === "none" || cs.getPropertyValue("visibility") === "hidden") continue;
        if (!record) record = {};
        record[name] = { text, style: _serializePseudoStyle(cs) };
      }
      if (record) out.set(tmpId, record);
    }
    return out;
  }

  function _captureOpenShadowRoots(allLive, liveByTmpId) {
    const out = new Map();
    for (let i = 0; i < allLive.length; i++) {
      const host = allLive[i];
      if (!host || !host.getAttribute) continue;
      const tmpId = host.getAttribute(TMP_ID_ATTR);
      if (!tmpId) continue;
      let shadowRoot = null;
      try { shadowRoot = host.shadowRoot; } catch (_) { shadowRoot = null; }
      if (!shadowRoot) continue;
      const cloned = _cloneShadowRootForFlattening(host, shadowRoot, liveByTmpId);
      const adoptedCss = _readAdoptedStyleSheets(shadowRoot);
      if (cloned && adoptedCss) {
        try {
          const style = document.createElement("style");
          style.setAttribute("data-le-shadow-adopted-style", "1");
          style.textContent = adoptedCss;
          cloned.insertBefore(style, cloned.firstChild);
        } catch (_) {}
      }
      if (cloned && cloned.childNodes && cloned.childNodes.length) out.set(tmpId, cloned);
    }
    return out;
  }

  function _readAdoptedStyleSheets(root) {
    let css = "";
    try {
      const sheets = root && root.adoptedStyleSheets ? root.adoptedStyleSheets : [];
      for (let i = 0; i < sheets.length; i++) {
        try {
          const rules = sheets[i].cssRules || [];
          for (let r = 0; r < rules.length; r++) css += rules[r].cssText + "\n";
        } catch (_) {}
      }
    } catch (_) {}
    return css;
  }

  function _cloneShadowRootForFlattening(host, shadowRoot, liveByTmpId) {
    let cloned;
    try { cloned = shadowRoot.cloneNode(true); } catch (_) { return null; }
    const slots = Array.from(cloned.querySelectorAll ? cloned.querySelectorAll("slot") : []);
    for (let i = 0; i < slots.length; i++) {
      const slotClone = slots[i];
      const tmpId = slotClone.getAttribute(TMP_ID_ATTR);
      const liveSlot = tmpId ? liveByTmpId.get(tmpId) : null;
      let assigned = [];
      try {
        if (liveSlot && typeof liveSlot.assignedNodes === "function") {
          assigned = liveSlot.assignedNodes({ flatten: true }) || [];
        }
      } catch (_) { assigned = []; }

      const replacement = (host.ownerDocument || document).createDocumentFragment();
      if (assigned.length) {
        for (let n = 0; n < assigned.length; n++) {
          try { replacement.appendChild(assigned[n].cloneNode(true)); } catch (_) {}
        }
      } else {
        while (slotClone.firstChild) replacement.appendChild(slotClone.firstChild);
      }
      if (slotClone.parentNode) slotClone.parentNode.replaceChild(replacement, slotClone);
    }
    return cloned;
  }

  function _captureComputedVisuals(allLive) {
    // Build a Map: tmpId -> string serialized inline-style fragment.
    // The old element-count cap is gone, but the property list remains the
    // curated visual/cosmetic list above.
    const out = new Map();
    for (let i = 0; i < allLive.length; i++) {
      const el = allLive[i];
      if (!el || el.nodeType !== 1) continue;
      if (el.closest && el.closest("head")) continue;
      const view = (el.ownerDocument && el.ownerDocument.defaultView) || window;
      if (!view || typeof view.getComputedStyle !== "function") continue;
      let cs;
      try { cs = view.getComputedStyle(el); } catch (_) { continue; }
      if (!cs) continue;
      let styleFragment = "";
      for (let p = 0; p < FREEZE_VISUAL_PROPS.length; p++) {
        const prop = FREEZE_VISUAL_PROPS[p];
        const value = cs.getPropertyValue(prop);
        if (!value) continue;
        const def = SKIPPABLE_DEFAULTS[prop];
        if (def !== undefined && value === def) continue;
        styleFragment += prop + ":" + value + " !important;";
      }
      if (styleFragment) {
        const tmpId = el.getAttribute(TMP_ID_ATTR);
        if (tmpId) out.set(tmpId, styleFragment);
      }
    }
    return out;
  }

  // -- Mutations on the clone ---------------------------------------------

  function _firstAttr(el, names) {
    for (const name of names) {
      const value = el.getAttribute(name);
      if (value && value.trim()) return value.trim();
    }
    return "";
  }

  function _isPlaceholderSrc(src, naturalWidth, naturalHeight) {
    if (!src) return true;
    if (PLACEHOLDER_SRC_RE.test(src)) return true;
    // Tiny rendered images are very likely lazy-load stubs.
    if (naturalWidth && naturalHeight && naturalWidth <= 4 && naturalHeight <= 4) return true;
    return false;
  }

  function _normalizeImagesOnClone(cloneRoot, liveByTmpId) {
    const imgs = Array.from(cloneRoot.querySelectorAll("img"));
    for (const img of imgs) {
      const tmpId = img.getAttribute(TMP_ID_ATTR);
      const live = tmpId ? liveByTmpId.get(tmpId) : null;
      const liveSrc = live ? live.currentSrc : "";
      const liveW = live ? live.naturalWidth : 0;
      const liveH = live ? live.naturalHeight : 0;
      const cloneSrc = img.getAttribute("src") || "";

      // Decide the best src in priority order:
      //   1) live currentSrc if it's not a placeholder
      //   2) any data-* lazy attr
      //   3) the clone's own src/srcset
      let chosen = "";
      if (liveSrc && !_isPlaceholderSrc(liveSrc, liveW, liveH)) {
        chosen = liveSrc;
      } else {
        const lazySrc = _firstAttr(img, LAZY_SRC_ATTRS);
        if (lazySrc) chosen = lazySrc;
        else if (liveSrc) chosen = liveSrc;
        else chosen = cloneSrc;
      }
      if (chosen) img.setAttribute("src", chosen);

      // Fall back srcset to data-srcset variants if the regular srcset is empty.
      const lazySrcset = _firstAttr(img, LAZY_SRCSET_ATTRS);
      const srcset = img.getAttribute("srcset");
      if (!srcset && lazySrcset) img.setAttribute("srcset", lazySrcset);

      // We've fixed src; srcset+<picture><source> just confuse later
      // rendering of a snapshot at a different viewport. Drop them.
      img.removeAttribute("srcset");
      img.setAttribute("loading", "eager");
      img.removeAttribute("decoding");

      // Remove stale lazy-load attributes from the snapshot.
      for (const a of LAZY_SRC_ATTRS) img.removeAttribute(a);
      for (const a of LAZY_SRCSET_ATTRS) img.removeAttribute(a);

      if (live) {
        if (live.naturalWidth && !img.hasAttribute("width")) img.setAttribute("width", String(live.naturalWidth));
        if (live.naturalHeight && !img.hasAttribute("height")) img.setAttribute("height", String(live.naturalHeight));
      }
    }
    // Drop <picture><source>; the chosen <img src> is authoritative.
    Array.from(cloneRoot.querySelectorAll("picture source")).forEach((s) => {
      s.parentNode && s.parentNode.removeChild(s);
    });
  }

  async function _inlineImageSrcsAsDataUris(cloneRoot, baseUrl) {
    const imgs = Array.from(cloneRoot.querySelectorAll("img"));
    await Promise.all(imgs.map(async (img) => {
      const src = img.getAttribute("src");
      if (!src || /^data:/i.test(src)) return;
      const abs = _absoluteUrl(src, baseUrl);
      if (!abs) return;
      const res = await _fetchResource(abs);
      img.setAttribute("src", res && res.ok ? res.dataUrl : abs);
    }));

    // SVG <image> elements.
    const svgImages = Array.from(cloneRoot.querySelectorAll("image"));
    await Promise.all(svgImages.map(async (img) => {
      const href = img.getAttribute("xlink:href") || img.getAttribute("href");
      if (!href || /^data:/i.test(href)) return;
      const abs = _absoluteUrl(href, baseUrl);
      if (!abs) return;
      const res = await _fetchResource(abs);
      if (res && res.ok) {
        img.setAttribute("href", res.dataUrl);
        if (img.hasAttribute("xlink:href")) img.setAttribute("xlink:href", res.dataUrl);
      }
    }));

    // Inline-style background-image url(...) references.
    const styled = Array.from(cloneRoot.querySelectorAll("[style*='url(']"));
    await Promise.all(styled.map(async (el) => {
      const style = el.getAttribute("style") || "";
      const replaced = await _inlineCssUrls(style, baseUrl);
      el.setAttribute("style", replaced);
    }));
  }

  async function _inlineExternalSvgUseReferences(cloneRoot, baseUrl) {
    const uses = Array.from(cloneRoot.querySelectorAll("use"));
    if (!uses.length) return;

    await Promise.all(uses.map(async (useEl) => {
      const raw = useEl.getAttribute("href") || useEl.getAttribute("xlink:href") || "";
      if (!raw || raw.charAt(0) === "#") return;
      const hashIndex = raw.indexOf("#");
      if (hashIndex < 0) return;
      const urlPart = raw.slice(0, hashIndex);
      const idPart = raw.slice(hashIndex + 1);
      if (!urlPart || !idPart) return;
      const abs = _absoluteUrl(urlPart, baseUrl);
      if (!abs) return;
      const svgText = await _fetchTextResource(abs);
      if (!svgText) return;

      let parsed;
      try { parsed = new DOMParser().parseFromString(svgText, "image/svg+xml"); } catch (_) { return; }
      let refId = idPart;
      try { refId = decodeURIComponent(idPart); } catch (_) {}
      let referenced = null;
      try { referenced = parsed.getElementById(refId); } catch (_) { referenced = null; }
      if (!referenced) return;

      const doc = useEl.ownerDocument || document;
      const ns = "http://www.w3.org/2000/svg";
      const refName = (referenced.localName || referenced.nodeName || "").toLowerCase();
      let replacement;

      if (refName === "symbol") {
        replacement = doc.createElementNS(ns, "svg");
        for (const attr of ["viewBox", "preserveAspectRatio"]) {
          const value = referenced.getAttribute(attr);
          if (value) replacement.setAttribute(attr, value);
        }
        for (const attr of ["x", "y", "width", "height"]) {
          const value = useEl.getAttribute(attr);
          if (value) replacement.setAttribute(attr, value);
        }
        for (let i = 0; i < referenced.childNodes.length; i++) {
          replacement.appendChild(doc.importNode(referenced.childNodes[i], true));
        }
      } else {
        replacement = doc.importNode(referenced, true);
        const x = useEl.getAttribute("x");
        const y = useEl.getAttribute("y");
        if ((x || y) && !replacement.getAttribute("transform")) {
          replacement.setAttribute("transform", "translate(" + (x || "0") + " " + (y || "0") + ")");
        }
      }

      for (let i = 0; i < useEl.attributes.length; i++) {
        const a = useEl.attributes[i];
        if (/^(href|xlink:href)$/i.test(a.name)) continue;
        if (!replacement.hasAttribute(a.name)) replacement.setAttribute(a.name, a.value);
      }
      replacement.setAttribute("data-le-inlined-use", abs + "#" + refId);
      if (useEl.parentNode) useEl.parentNode.replaceChild(replacement, useEl);
    }));
  }

  // -- Stylesheet inlining ------------------------------------------------

  function _readSheetTextFromCssom(href, originalDoc) {
    try {
      const sheets = originalDoc.styleSheets || [];
      for (let i = 0; i < sheets.length; i++) {
        const sh = sheets[i];
        if (!sh) continue;
        if (sh.href === href) {
          let out = "";
          try {
            const rules = sh.cssRules || [];
            for (let r = 0; r < rules.length; r++) out += rules[r].cssText + "\n";
            return out;
          } catch (_) {
            return null;
          }
        }
      }
    } catch (_) {}
    return null;
  }

  async function _inlineStylesheets(cloneRoot, originalDoc, base) {
    const links = Array.from(cloneRoot.querySelectorAll(
      "link[rel~='stylesheet'], link[rel='alternate stylesheet']"
    ));
    for (const link of links) {
      const href = link.getAttribute("href");
      const abs = _absoluteUrl(href, base);
      if (!abs) {
        link.parentNode && link.parentNode.removeChild(link);
        continue;
      }
      let cssText = _readSheetTextFromCssom(abs, originalDoc);
      if (cssText == null) cssText = await _fetchTextResource(abs);
      if (cssText == null) cssText = "";
      const inlined = await _inlineCssUrls(cssText, abs);
      const styleEl = document.createElement("style");
      styleEl.setAttribute("data-frozen-from", abs);
      const media = link.getAttribute("media");
      if (media) styleEl.setAttribute("media", media);
      styleEl.textContent = inlined;
      link.parentNode.replaceChild(styleEl, link);
    }
    const styles = Array.from(cloneRoot.querySelectorAll("style"));
    for (const styleEl of styles) {
      const inlined = await _inlineCssUrls(styleEl.textContent || "", base);
      styleEl.textContent = inlined;
    }
  }

  // -- Cleanup -------------------------------------------------------------

  const ATTRS_WITH_URL = ["src", "href", "poster", "data", "action", "formaction", "background"];
  const EVENT_ATTR_RE = /^on[a-z]+/i;

  function _resolveUrlAttrs(el, base) {
    for (let i = 0; i < ATTRS_WITH_URL.length; i++) {
      const name = ATTRS_WITH_URL[i];
      if (el.hasAttribute(name)) {
        const v = el.getAttribute(name);
        if (v && !/^(data:|#|blob:|javascript:|mailto:|tel:)/i.test(v)) {
          const abs = _absoluteUrl(v, base);
          if (abs) el.setAttribute(name, abs);
        }
      }
    }
  }

  function _stripDangerousAttrs(el) {
    const attrs = el.attributes;
    if (!attrs) return;
    const toRemove = [];
    for (let i = 0; i < attrs.length; i++) {
      const a = attrs[i];
      const name = a.name;
      if (EVENT_ATTR_RE.test(name)) {
        toRemove.push(name);
        continue;
      }
      const value = a.value || "";
      if (/^(href|src|xlink:href|action|formaction)$/i.test(name) && /^\s*javascript:/i.test(value)) {
        toRemove.push(name);
      }
    }
    for (let i = 0; i < toRemove.length; i++) el.removeAttribute(toRemove[i]);
  }

  function _stripContentSecurityPolicyMeta(doc) {
    const metas = doc.querySelectorAll('meta[http-equiv]');
    metas.forEach((m) => {
      const eq = (m.getAttribute("http-equiv") || "").toLowerCase();
      if (eq === "content-security-policy" || eq === "x-content-security-policy") {
        m.parentNode && m.parentNode.removeChild(m);
      }
    });
  }

  function _unwrapUsefulNoscriptFallbacks(root) {
    const nodes = Array.from(root.querySelectorAll("noscript"));
    for (const noscript of nodes) {
      if (noscript.closest && noscript.closest("head")) continue;
      const raw = (noscript.textContent || "").trim();
      if (!raw) continue;

      const template = document.createElement("template");
      try { template.innerHTML = raw; } catch (_) { continue; }
      const text = (template.content.textContent || "").replace(/\s+/g, " ").trim();
      const hasUsefulMedia = !!template.content.querySelector("img,picture,source,svg,iframe,canvas,video");
      if (!hasUsefulMedia && text.length < 2) continue;

      const wrapper = document.createElement("div");
      wrapper.setAttribute("data-le-noscript-fallback", "1");
      wrapper.setAttribute("style", "display:contents !important;");
      wrapper.appendChild(template.content);
      noscript.parentNode && noscript.parentNode.replaceChild(wrapper, noscript);
    }
  }

  function _removeNonRenderingNodes(root) {
    // Strip scripts and resource hints. We keep <noscript> contents — they
    // often hold the no-JS image/markup fallback we WANT in a static snapshot.
    const banished = root.querySelectorAll(
      "script, link[rel~='preload'], link[rel~='prefetch'], link[rel~='dns-prefetch'], link[rel~='preconnect'], link[rel~='modulepreload'], link[rel~='manifest']"
    );
    banished.forEach((n) => n.parentNode && n.parentNode.removeChild(n));
  }

  async function _captureLiveFrameState(allLive, depth) {
    const out = new Map();
    if ((depth || 0) >= MAX_FRAME_SNAPSHOT_DEPTH) return out;
    for (let i = 0; i < allLive.length; i++) {
      const el = allLive[i];
      if (!el || (el.tagName !== "IFRAME" && el.tagName !== "FRAME")) continue;
      const tmpId = el.getAttribute(TMP_ID_ATTR);
      if (!tmpId) continue;
      const snap = await _snapshotAccessibleFrame(el, (depth || 0) + 1);
      if (snap) out.set(tmpId, snap);
    }
    return out;
  }

  async function _snapshotAccessibleFrame(frameEl, depth) {
    let frameDoc = null;
    try { frameDoc = frameEl.contentDocument || (frameEl.contentWindow && frameEl.contentWindow.document); } catch (_) { return null; }
    if (!frameDoc || !frameDoc.documentElement) return null;

    const frameBase = frameDoc.baseURI || frameEl.getAttribute("src") || document.baseURI || location.href;
    try { _triggerLazyResources(frameDoc); } catch (_) {}

    const allLive = _tagLiveDom(frameDoc);
    let cloneRoot;
    let liveByTmpId;
    let frameByTmpId;
    let computedByTmpId;
    let pseudoByTmpId;
    let canvasByTmpId;
    let shadowRootsByTmpId;
    try {
      const liveElementByTmpId = _buildLiveElementMap(allLive);
      liveByTmpId = _captureLiveImageState(allLive);
      frameByTmpId = await _captureLiveFrameState(allLive, depth);
      computedByTmpId = _captureComputedVisuals(allLive);
      pseudoByTmpId = _capturePseudoElementText(allLive);
      canvasByTmpId = _captureCanvasState(allLive);
      shadowRootsByTmpId = _captureOpenShadowRoots(allLive, liveElementByTmpId);
      cloneRoot = frameDoc.documentElement.cloneNode(true);
    } finally {
      _untagLiveDom(frameDoc, allLive);
    }

    await _prepareFrozenClone(cloneRoot, frameDoc, frameBase, liveByTmpId, frameByTmpId, computedByTmpId, pseudoByTmpId, canvasByTmpId, shadowRootsByTmpId, false);
    return {
      html: "<!doctype html>\n" + cloneRoot.outerHTML,
      url: frameDoc.location ? String(frameDoc.location.href || "") : String(frameBase || ""),
    };
  }

  function _takeExternalFrameSnapshot(frame, externalFrameSnapshotsByUrl, baseUrl) {
    if (!externalFrameSnapshotsByUrl) return null;
    const raw = frame.getAttribute("src") || frame.getAttribute("data-src") || frame.getAttribute("data-lazy-src") || "";
    const abs = _absoluteUrl(raw, baseUrl) || raw;
    const candidates = externalFrameSnapshotsByUrl[abs] || externalFrameSnapshotsByUrl[raw];
    if (!candidates) return null;
    if (Array.isArray(candidates)) return candidates.shift() || null;
    return candidates;
  }

  function _snapshotFramesOnClone(cloneRoot, frameByTmpId, externalFrameSnapshotsByUrl, baseUrl) {
    const frames = Array.from(cloneRoot.querySelectorAll("iframe, frame"));
    for (const frame of frames) {
      const tmpId = frame.getAttribute(TMP_ID_ATTR);
      let snap = tmpId ? frameByTmpId.get(tmpId) : null;
      if (!snap) snap = _takeExternalFrameSnapshot(frame, externalFrameSnapshotsByUrl, baseUrl);
      let target = frame;
      if (snap && snap.html) {
        target = frame.tagName === "FRAME" ? document.createElement("iframe") : frame;
        if (target !== frame) {
          for (let i = 0; i < frame.attributes.length; i++) {
            const a = frame.attributes[i];
            target.setAttribute(a.name, a.value);
          }
          frame.parentNode && frame.parentNode.replaceChild(target, frame);
        }
        target.removeAttribute("src");
        target.setAttribute("srcdoc", snap.html);
        target.setAttribute("sandbox", "");
        target.setAttribute("data-le-frame-snapshot", "1");
        if (snap.url) target.setAttribute("data-le-frame-source", snap.url);
      } else {
        target.setAttribute("sandbox", "");
        target.setAttribute("data-le-frame-live-sandboxed", "1");
      }
      target.removeAttribute("allow");
      target.removeAttribute("allowfullscreen");
      target.removeAttribute("referrerpolicy");
    }
  }

  function _restoreOpenShadowRootsOnClone(cloneRoot, shadowRootsByTmpId) {
    if (!shadowRootsByTmpId || !shadowRootsByTmpId.size) return 0;
    const restored = new Set();
    let restoredCount = 0;
    let changed = true;
    while (changed) {
      changed = false;
      const candidates = _queryElementsInclusive(cloneRoot, "[" + TMP_ID_ATTR + "]");
      for (let i = 0; i < candidates.length; i++) {
        const host = candidates[i];
        const tmpId = host.getAttribute(TMP_ID_ATTR);
        if (!tmpId || restored.has(tmpId) || !shadowRootsByTmpId.has(tmpId)) continue;
        const sourceFragment = shadowRootsByTmpId.get(tmpId);
        const doc = host.ownerDocument || document;
        const wrapper = doc.createElement("div");
        wrapper.setAttribute("data-le-shadow-root", "open-flattened");
        wrapper.setAttribute("style", "display:contents !important;");
        try { wrapper.appendChild(doc.importNode(sourceFragment, true)); } catch (_) { wrapper.appendChild(sourceFragment.cloneNode(true)); }
        while (host.firstChild) host.removeChild(host.firstChild);
        host.appendChild(wrapper);
        restored.add(tmpId);
        restoredCount++;
        changed = true;
      }
    }
    return restoredCount;
  }

  function _replaceCanvasesOnClone(cloneRoot, canvasByTmpId) {
    if (!canvasByTmpId || !canvasByTmpId.size) return;
    const canvases = Array.from(cloneRoot.querySelectorAll("canvas"));
    for (const canvas of canvases) {
      const tmpId = canvas.getAttribute(TMP_ID_ATTR);
      const snap = tmpId ? canvasByTmpId.get(tmpId) : null;
      if (!snap || !snap.dataUrl) continue;
      const doc = canvas.ownerDocument || document;
      const img = doc.createElement("img");
      for (let i = 0; i < canvas.attributes.length; i++) {
        const a = canvas.attributes[i];
        img.setAttribute(a.name, a.value);
      }
      img.setAttribute("src", snap.dataUrl);
      img.setAttribute("data-le-canvas-snapshot", "1");
      if (snap.width && !img.hasAttribute("width")) img.setAttribute("width", String(snap.width));
      if (snap.height && !img.hasAttribute("height")) img.setAttribute("height", String(snap.height));
      if (snap.ariaLabel && !img.hasAttribute("alt")) img.setAttribute("alt", snap.ariaLabel);
      else if (!img.hasAttribute("alt")) img.setAttribute("alt", "");
      canvas.parentNode && canvas.parentNode.replaceChild(img, canvas);
    }
  }

  function _makePseudoSpan(doc, kind, record) {
    const span = doc.createElement("span");
    span.setAttribute("data-le-pseudo", kind);
    if (record.style) span.setAttribute("style", record.style);
    span.textContent = record.text || "";
    return span;
  }

  function _insertPseudoTextOnClone(cloneRoot, pseudoByTmpId) {
    if (!pseudoByTmpId || !pseudoByTmpId.size) return;
    const tagged = _queryElementsInclusive(cloneRoot, "[" + TMP_ID_ATTR + "]");
    for (let i = 0; i < tagged.length; i++) {
      const el = tagged[i];
      if (/^(AREA|BASE|BR|COL|EMBED|HR|IMG|INPUT|LINK|META|PARAM|SOURCE|TRACK|WBR)$/i.test(el.tagName || "")) continue;
      const tmpId = el.getAttribute(TMP_ID_ATTR);
      const record = tmpId ? pseudoByTmpId.get(tmpId) : null;
      if (!record) continue;
      const doc = el.ownerDocument || document;
      const originalFirst = el.firstChild;
      if (record.marker) {
        el.setAttribute("data-le-pseudo-marker", "1");
        const existing = el.getAttribute("style") || "";
        const markerStyle = "list-style-type:none !important;list-style-image:none !important;";
        el.setAttribute("style", existing ? existing + ";" + markerStyle : markerStyle);
        el.insertBefore(_makePseudoSpan(doc, "marker", record.marker), originalFirst);
      }
      if (record.before) {
        el.setAttribute("data-le-pseudo-before", "1");
        el.insertBefore(_makePseudoSpan(doc, "before", record.before), originalFirst);
      }
      if (record.after) {
        el.setAttribute("data-le-pseudo-after", "1");
        el.appendChild(_makePseudoSpan(doc, "after", record.after));
      }
    }
  }

  function _neuterFormAndInteractive(root) {
    Array.from(root.querySelectorAll("a")).forEach((a) => {
      const href = a.getAttribute("href") || a.getAttribute("xlink:href");
      if (href) a.setAttribute("data-le-original-href", href);
      a.removeAttribute("href");
      a.removeAttribute("xlink:href");
      a.removeAttribute("target");
      a.removeAttribute("download");
      a.removeAttribute("ping");
    });
    Array.from(root.querySelectorAll("form")).forEach((form) => {
      form.setAttribute("data-le-frozen-form", "1");
      form.removeAttribute("action");
      form.removeAttribute("method");
      form.removeAttribute("target");
    });
    Array.from(root.querySelectorAll("button, input, select, textarea, summary, option")).forEach((el) => {
      el.setAttribute("tabindex", "-1");
      el.setAttribute("aria-disabled", "true");
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
        try { el.readOnly = true; } catch (_) {}
      }
    });
    Array.from(root.querySelectorAll("[contenteditable]")).forEach((el) => {
      el.setAttribute("contenteditable", "false");
    });
    Array.from(root.querySelectorAll("video, audio")).forEach((media) => {
      media.removeAttribute("autoplay");
      media.removeAttribute("loop");
      media.removeAttribute("controls");
      media.setAttribute("preload", "metadata");
      media.setAttribute("tabindex", "-1");
      media.setAttribute("aria-disabled", "true");
    });
  }

  // -- Apply captured visual styles to clone ------------------------------

  function _applyCapturedVisualStyles(cloneRoot, computedByTmpId) {
    const tagged = _queryElementsInclusive(cloneRoot, "[" + TMP_ID_ATTR + "]");
    for (let i = 0; i < tagged.length; i++) {
      const el = tagged[i];
      const tmpId = el.getAttribute(TMP_ID_ATTR);
      const fragment = computedByTmpId.get(tmpId);
      if (!fragment) continue;
      const existing = el.getAttribute("style") || "";
      // Append (so existing inline styles win over our frozen defaults
      // where they conflict — wait, we use !important in fragment, so
      // ours win regardless. Order doesn't matter for !important).
      el.setAttribute("style", existing ? existing + ";" + fragment : fragment);
    }
  }

  function _stripTmpIdsFromClone(cloneRoot) {
    const tagged = _queryElementsInclusive(cloneRoot, "[" + TMP_ID_ATTR + "]");
    for (let i = 0; i < tagged.length; i++) tagged[i].removeAttribute(TMP_ID_ATTR);
  }

  // -- Misc ---------------------------------------------------------------

  function _safeTitle() {
    const t = (document.title || "").trim();
    if (t) return t;
    return location.hostname || "Captured page";
  }

  function _ensureBase(head, baseUrl) {
    let baseEl = head.querySelector("base");
    if (!baseEl) {
      baseEl = document.createElement("base");
      head.insertBefore(baseEl, head.firstChild);
    }
    baseEl.setAttribute("href", baseUrl);
  }

  function _appendMeta(head, name, content) {
    const m = document.createElement("meta");
    m.setAttribute("name", name);
    m.setAttribute("content", content);
    head.appendChild(m);
  }

  function _appendFreezeStyle(head) {
    const styleEl = document.createElement("style");
    styleEl.setAttribute("data-le-freeze-style", "1");
    styleEl.textContent = [
      // Disable animations and transitions; we've already frozen the
      // visual state inline so any further motion would just diverge from
      // the captured frame.
      "html[data-le-frozen] *, html[data-le-frozen] *::before, html[data-le-frozen] *::after{",
      "  animation: none !important;",
      "  transition: none !important;",
      "  scroll-behavior: auto !important;",
      "}",
      // Hide media that won't play in a static snapshot.
      "html[data-le-frozen] video, html[data-le-frozen] audio{ display: none !important; }",
      // Make the snapshot inert — links and form controls don't navigate
      // or focus. Keep cursor as text so the user can select for lookup.
      "html[data-le-frozen] a, html[data-le-frozen] a:link, html[data-le-frozen] a:visited{",
      "  text-decoration: inherit;",
      "  color: inherit;",
      "  pointer-events: none !important;",
      "}",
      "html[data-le-frozen] [data-le-pseudo]{ user-select: text !important; }",
      "html[data-le-frozen] [data-le-pseudo-before]::before, html[data-le-frozen] [data-le-pseudo-after]::after{ content: none !important; }",
      "html[data-le-frozen] [data-le-pseudo-marker]::marker{ content: '' !important; }",
      "html[data-le-frozen] details > summary{ list-style: none !important; }",
      "html[data-le-frozen] details > summary::-webkit-details-marker{ display: none !important; }",
      "html[data-le-frozen] [contenteditable]{ -webkit-user-modify: read-only !important; user-modify: read-only !important; }",
    ].join("\n");
    head.appendChild(styleEl);
  }

  async function _prepareFrozenClone(cloneRoot, originalDoc, baseUrl, liveByTmpId, frameByTmpId, computedByTmpId, pseudoByTmpId, canvasByTmpId, shadowRootsByTmpId, includeMetadata, externalFrameSnapshotsByUrl) {
    let head = cloneRoot.querySelector(":scope > head");
    let body = cloneRoot.querySelector(":scope > body");
    if (!head) {
      head = document.createElement("head");
      cloneRoot.insertBefore(head, cloneRoot.firstChild);
    }
    if (!body) {
      body = document.createElement("body");
      cloneRoot.appendChild(body);
    }

    cloneRoot.removeAttribute(RESOURCE_FETCH_BRIDGE_ATTR);
    _restoreOpenShadowRootsOnClone(cloneRoot, shadowRootsByTmpId || new Map());
    _stripContentSecurityPolicyMeta(cloneRoot);
    _unwrapUsefulNoscriptFallbacks(cloneRoot);
    _removeNonRenderingNodes(cloneRoot);

    const all = _queryElementsInclusive(cloneRoot, "*");
    for (let i = 0; i < all.length; i++) {
      _resolveUrlAttrs(all[i], baseUrl);
      _stripDangerousAttrs(all[i]);
    }

    _snapshotFramesOnClone(cloneRoot, frameByTmpId || new Map(), externalFrameSnapshotsByUrl, baseUrl);
    _normalizeImagesOnClone(cloneRoot, liveByTmpId || new Map());
    _replaceCanvasesOnClone(cloneRoot, canvasByTmpId || new Map());
    _neuterFormAndInteractive(cloneRoot);
    _applyCapturedVisualStyles(cloneRoot, computedByTmpId || new Map());
    _insertPseudoTextOnClone(cloneRoot, pseudoByTmpId || new Map());
    _stripTmpIdsFromClone(cloneRoot);

    _ensureBase(head, baseUrl);
    await _inlineStylesheets(cloneRoot, originalDoc, baseUrl);
    await _inlineExternalSvgUseReferences(cloneRoot, baseUrl);
    await _inlineImageSrcsAsDataUris(cloneRoot, baseUrl);

    cloneRoot.setAttribute("data-le-frozen", "1");
    if (includeMetadata !== false) {
      _appendMeta(head, "language-engine-source", baseUrl);
      _appendMeta(head, "language-engine-title", _safeTitle());
      _appendMeta(head, "language-engine-captured-at", new Date().toISOString());
    }
    _appendFreezeStyle(head);
    return { head, body };
  }

  // -- Main pipeline -------------------------------------------------------

  async function freeze(options) {
    options = options || {};
    const baseUrl = document.baseURI || location.href;

    try { _triggerLazyResources(document); } catch (_) {}

    const allLive = _tagLiveDom(document);
    let cloneRoot;
    let liveByTmpId;
    let frameByTmpId;
    let computedByTmpId;
    let pseudoByTmpId;
    let canvasByTmpId;
    let shadowRootsByTmpId;
    try {
      const liveElementByTmpId = _buildLiveElementMap(allLive);
      liveByTmpId = _captureLiveImageState(allLive);
      frameByTmpId = await _captureLiveFrameState(allLive, 0);
      computedByTmpId = _captureComputedVisuals(allLive);
      pseudoByTmpId = _capturePseudoElementText(allLive);
      canvasByTmpId = _captureCanvasState(allLive);
      shadowRootsByTmpId = _captureOpenShadowRoots(allLive, liveElementByTmpId);
      cloneRoot = document.documentElement.cloneNode(true);
    } finally {
      _untagLiveDom(document, allLive);
    }

    await _prepareFrozenClone(cloneRoot, document, baseUrl, liveByTmpId, frameByTmpId, computedByTmpId, pseudoByTmpId, canvasByTmpId, shadowRootsByTmpId, true, options.frameSnapshotsByUrl || null);

    const html = "<!doctype html>\n" + cloneRoot.outerHTML;
    return {
      html,
      title: _safeTitle(),
      url: location.href,
      bytes: html.length,
      frozenElements: computedByTmpId.size,
      pseudoElements: pseudoByTmpId.size,
      canvasSnapshots: canvasByTmpId.size,
      shadowRoots: shadowRootsByTmpId.size,
      snapshottedFrames: frameByTmpId.size,
    };
  }

  function freezeWithTimeout(options) {
    return new Promise((resolve, reject) => {
      let done = false;
      const timer = setTimeout(() => {
        if (done) return;
        done = true;
        reject(new Error("Capture timed out after " + (FREEZE_TIMEOUT_MS / 1000) + "s"));
      }, FREEZE_TIMEOUT_MS);
      freeze(options).then((res) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve(res);
      }).catch((err) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        reject(err);
      });
    });
  }

  window.__languageEngineFreezeDom = async function (opts) {
    try {
      const result = await freezeWithTimeout(opts || {});
      return { ok: true, result };
    } catch (e) {
      try { _untagLiveDom(); } catch (_) {}
      return { ok: false, error: (e && e.message) || String(e) };
    }
  };
})();
