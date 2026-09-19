/* docrender/parsers.js — per-format parsers.
 *
 * Each parser returns:
 *   {
 *     richHtml:    '<full document HTML>'
 *     naturalPages: [{html, text}, ...]   (optional, formats with real page breaks)
 *     meta: {format, title, ...}
 *   }
 *
 * INVARIANT (the whole point of this file):
 *   For every {html, text} pair we hand back, parsing `html` into a DOM and
 *   walking that DOM's text nodes (with the shared LOOKUP_TEXT_FILTER below)
 *   yields a string that is byte-for-byte equal to `text`. The reader can then
 *   send `text` to /lookup and decorate the matching DOM with the returned
 *   character offsets and they will line up with zero drift.
 *
 * To make this invariant hold:
 *   - For block-structured formats (TXT/DOCX), we insert literal
 *     "\n" text nodes between block-level elements after parsing. CSS collapses
 *     this whitespace between block boxes so it doesn't render visually, but
 *     textContent / TreeWalker still see it.
 *   - PDF and ebook files do not enter this parser. PDF uses the PDF.js reader
 *     path; ebooks use Foliate directly.
 *   - We do NOT strip invisible or compatibility characters here; backend
 *     Universal Normalization owns destructive character normalization.
 */
(function (global) {
  "use strict";

  // Tags whose descendants are not part of the flattened readable text
  // stream. Form controls are intentionally not listed here; any actual text
  // node in readable HTML should be sent to lookup.
  var LOOKUP_NONTEXT_TAGS = {
    IMG: 1, PICTURE: 1, SVG: 1, CANVAS: 1, VIDEO: 1, AUDIO: 1, IFRAME: 1,
    OBJECT: 1, EMBED: 1, SCRIPT: 1, STYLE: 1, TEMPLATE: 1, NOSCRIPT: 1
  };

  // Block-level tags that should be visually separated by a newline in the
  // extracted text. Adjacent block elements get a "\n" text node inserted
  // between them via _insertBlockSeparators().
  var BLOCK_TAGS = {
    ADDRESS: 1, ARTICLE: 1, ASIDE: 1, BLOCKQUOTE: 1, DD: 1, DETAILS: 1, DIALOG: 1,
    DIV: 1, DL: 1, DT: 1, FIELDSET: 1, FIGCAPTION: 1, FIGURE: 1, FOOTER: 1,
    FORM: 1, H1: 1, H2: 1, H3: 1, H4: 1, H5: 1, H6: 1, HEADER: 1, HGROUP: 1,
    HR: 1, LI: 1, MAIN: 1, NAV: 1, OL: 1, P: 1, PRE: 1, SECTION: 1, TABLE: 1,
    TBODY: 1, TD: 1, TFOOT: 1, TH: 1, THEAD: 1, TR: 1, UL: 1, BR: 1, CAPTION: 1,
    SUMMARY: 1, MENU: 1, COL: 1, COLGROUP: 1
  };

  function _isLookupTextNode(node) {
    if (!node || !node.nodeValue) return false;
    var p = node.parentNode;
    while (p && p.nodeType === 1) {
      if (LOOKUP_NONTEXT_TAGS[p.tagName]) return false;
      if (p.getAttribute && p.getAttribute("data-le-static-control")) return false;
      p = p.parentNode;
    }
    return true;
  }

  function _childIndex(node) {
    if (!node || !node.parentNode) return -1;
    var kids = node.parentNode.childNodes;
    for (var i = 0; i < kids.length; i++) {
      if (kids[i] === node) return i;
    }
    return -1;
  }

  function _nodePath(root, node) {
    var path = [];
    var cur = node;
    while (cur && cur !== root) {
      var idx = _childIndex(cur);
      if (idx < 0) return null;
      path.unshift(idx);
      cur = cur.parentNode;
    }
    return cur === root ? path : null;
  }

  function _prefixTextMap(map, prefix) {
    var src = Array.isArray(map) ? map : [];
    var pre = Array.isArray(prefix) ? prefix : [];
    return src.map(function (m) {
      return {
        start: Number(m && m.start) || 0,
        end: Number(m && m.end) || 0,
        path: pre.concat(Array.isArray(m && m.path) ? m.path : [])
      };
    });
  }

  /** Walk the DOM and concat the flattened readable text stream. */
  function extractText(root) {
    return extractTextAndMap(root).text;
  }

  /** Walk the DOM once and return both canonical page text and the DOM path map
   *  that ties each page-text offset range back to the source text node.
   */
  function extractTextAndMap(root) {
    if (!root) return { text: "", textMap: [] };
    var walker = root.ownerDocument.createTreeWalker(
      root, NodeFilter.SHOW_TEXT, {
        acceptNode: function (n) {
          return _isLookupTextNode(n) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        }
      }
    );
    var out = "";
    var map = [];
    var n;
    while ((n = walker.nextNode())) {
      var value = n.nodeValue || "";
      if (!value) continue;
      var path = _nodePath(root, n);
      if (!path) continue;
      var start = out.length;
      out += value;
      map.push({ start: start, end: out.length, path: path });
    }
    return { text: out, textMap: map };
  }

  /** Insert a "\n" text node after every block-level element so the extracted
   *  text has visual line/paragraph boundaries. Idempotent: a "\n" sibling
   *  already in place is left alone.
   */
  function _insertBlockSeparators(root) {
    if (!root) return;
    var doc = root.ownerDocument;
    // Snapshot first; we mutate during iteration.
    var blocks = [];
    var stack = [root];
    while (stack.length) {
      var cur = stack.pop();
      var kids = cur.childNodes;
      for (var i = kids.length - 1; i >= 0; i--) {
        var k = kids[i];
        if (k.nodeType !== 1) continue;
        if (LOOKUP_NONTEXT_TAGS[k.tagName]) continue;
        stack.push(k);
        if (BLOCK_TAGS[k.tagName]) blocks.push(k);
      }
    }
    for (var b = 0; b < blocks.length; b++) {
      var el = blocks[b];
      var next = el.nextSibling;
      // Skip if a leading-whitespace text node already follows.
      if (next && next.nodeType === 3 && /^\s/.test(next.nodeValue || "")) continue;
      var sep = doc.createTextNode("\n");
      if (next) el.parentNode.insertBefore(sep, next);
      else el.parentNode.appendChild(sep);
    }
  }

  // Inline elements whose wrappers we collapse to plain text so the reader
  // token span inserter can freely split and wrap any text node without hitting
  // inline element boundaries.
  var INLINE_FLATTEN_TAGS = {
    A: 1, SPAN: 1, STRONG: 1, EM: 1, B: 1, I: 1, U: 1, S: 1, STRIKE: 1,
    DEL: 1, INS: 1, MARK: 1, SMALL: 1, BIG: 1, ABBR: 1, CITE: 1,
    CODE: 1, KBD: 1, SAMP: 1, VAR: 1, TIME: 1, Q: 1, SUB: 1, SUP: 1,
    LABEL: 1, BDO: 1, BDI: 1, WBR: 1, FONT: 1
  };

  /** Replace every inline wrapper element with a single text node holding its
   *  textContent. Runs bottom-up so nested inlines collapse correctly.
   *  Block-level elements and non-text elements are left untouched.
   */
  function _flattenInlineWrappers(root) {
    if (!root) return;
    // Collect all inline elements depth-first, deepest first (reverse order).
    var inlines = [];
    var stack = [root];
    while (stack.length) {
      var cur = stack.pop();
      var kids = cur.childNodes;
      for (var i = kids.length - 1; i >= 0; i--) {
        var k = kids[i];
        if (k.nodeType === 1) stack.push(k);
      }
      if (cur !== root && cur.nodeType === 1 && INLINE_FLATTEN_TAGS[cur.tagName] && !LOOKUP_NONTEXT_TAGS[cur.tagName] && !(cur.getAttribute && cur.getAttribute("data-le-static-control"))) {
        inlines.push(cur);
      }
    }
    // Process deepest first so inner inlines are already collapsed when we
    // reach their parents.
    for (var j = 0; j < inlines.length; j++) {
      var el = inlines[j];
      if (!el.parentNode) continue;
      var text = el.textContent || "";
      var tn = el.ownerDocument.createTextNode(text);
      el.parentNode.replaceChild(tn, el);
    }
    // Normalize merges adjacent text nodes created by the replacements.
    root.normalize();
  }

  /** Build the canonical {html, text, textMap} page slice from a rich DOM. */
  function _finalizePage(root) {
    _flattenInlineWrappers(root);
    _insertBlockSeparators(root);
    var extracted = extractTextAndMap(root);
    return { html: root.innerHTML, text: extracted.text, textMap: extracted.textMap };
  }

  /** Canonical-text extraction from a LIVE mounted root.
   *
   *  Runs inline-flatten + block-separator insertion in place on the supplied
   *  root, then walks it once and returns the flattened text. Kept for
   *  callers that only need the text. Prefer extractCanonicalTextAndRuns for
   *  the lookup path so decoration can reuse the same live node refs.
   */
  function extractTextFromLiveRoot(root) {
    if (!root) return "";
    _flattenInlineWrappers(root);
    _insertBlockSeparators(root);
    return extractTextAndMap(root).text;
  }

  /** Single-pass canonical-text contract enforcer.
   *
   *  Walks the LIVE mounted root exactly once and produces:
   *    - text: the canonical text string sent to /lookup as `q`
   *    - textRuns: [{node, start, end}, …] live Text-node references covering
   *                the same character ranges.
   *
   *  By construction, text === concat of node.nodeValue for every run, and
   *  text.slice(run.start, run.end) === run.node.nodeValue. Decoration uses
   *  textRuns directly, so q (sent to backend) and the decoration target
   *  (live DOM nodes) come from the SAME walk — no race window between
   *  extraction and decoration. Idempotent (the inline-flatten and
   *  block-separator passes are idempotent).
   */
  function extractCanonicalTextAndRuns(root) {
    if (!root) return { text: "", textRuns: [] };
    _flattenInlineWrappers(root);
    _insertBlockSeparators(root);
    var walker = root.ownerDocument.createTreeWalker(
      root, NodeFilter.SHOW_TEXT, {
        acceptNode: function (n) {
          return _isLookupTextNode(n) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        }
      }
    );
    var text = "";
    var runs = [];
    var n;
    while ((n = walker.nextNode())) {
      var v = n.nodeValue || "";
      if (!v) continue;
      var s = text.length;
      text += v;
      runs.push({ node: n, start: s, end: text.length });
    }
    return { text: text, textRuns: runs };
  }

  function escapeHtml(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  function applyStaticControlBoxStyle(el, type, checked) {
    var isRadio = type === "radio";
    el.setAttribute("data-le-static-control", type || "control");
    el.setAttribute("aria-label", (checked ? "checked " : "unchecked ") + (isRadio ? "radio button" : "checkbox"));
    el.setAttribute("role", "img");
    el.setAttribute("style", [
      "display:inline-flex",
      "align-items:center",
      "justify-content:center",
      "box-sizing:border-box",
      "width:.95em",
      "height:.95em",
      "margin:0 .18em",
      "vertical-align:-.12em",
      "border:1.4px solid currentColor",
      "border-radius:" + (isRadio ? "50%" : ".16em"),
      "font:700 .72em/1 system-ui,sans-serif",
      "color:inherit",
      "background:" + (checked ? (isRadio ? "radial-gradient(circle,currentColor 0 42%,transparent 46%)" : "currentColor") : "transparent"),
      "pointer-events:none"
    ].join(";"));
    el.textContent = "";
  }

  function applyStaticInlineControlStyle(el, kind) {
    el.setAttribute("data-le-static-control", kind || "control");
    el.setAttribute("aria-hidden", "true");
    el.setAttribute("style", [
      "display:inline-block",
      "box-sizing:border-box",
      "min-width:5.5em",
      "min-height:1.05em",
      "padding:0 .22em",
      "margin:0 .12em",
      "vertical-align:-.12em",
      "border:1px solid currentColor",
      "border-radius:.16em",
      "color:inherit",
      "background:transparent",
      "pointer-events:none",
      "white-space:pre-wrap"
    ].join(";"));
  }

  function selectedOptionText(select) {
    if (!select || !select.querySelectorAll) return "";
    var selected = select.querySelector("option[selected]") || select.querySelector("option");
    return selected ? String(selected.textContent || "").trim() : "";
  }

  function freezeInteractiveControls(html) {
    var dom = new DOMParser().parseFromString("<!doctype html><body>" + String(html || "") + "</body>", "text/html");
    var body = dom.body || dom.documentElement;
    if (!body) return String(html || "");
    Array.prototype.slice.call(body.querySelectorAll("[contenteditable]")).forEach(function(el) {
      el.removeAttribute("contenteditable");
    });
    Array.prototype.slice.call(body.querySelectorAll("input")).forEach(function(input) {
      var type = String(input.getAttribute("type") || "text").toLowerCase();
      if (type === "hidden") {
        input.parentNode && input.parentNode.removeChild(input);
        return;
      }
      var span = dom.createElement("span");
      if (type === "checkbox" || type === "radio") {
        applyStaticControlBoxStyle(span, type, input.hasAttribute("checked") || input.checked);
      } else {
        applyStaticInlineControlStyle(span, type || "input");
        var value = input.getAttribute("value") || input.getAttribute("placeholder") || "";
        span.textContent = value || "\u00a0";
      }
      input.parentNode && input.parentNode.replaceChild(span, input);
    });
    Array.prototype.slice.call(body.querySelectorAll("textarea")).forEach(function(textarea) {
      var span = dom.createElement("span");
      applyStaticInlineControlStyle(span, "textarea");
      span.textContent = String(textarea.textContent || textarea.getAttribute("placeholder") || "") || "\u00a0";
      textarea.parentNode && textarea.parentNode.replaceChild(span, textarea);
    });
    Array.prototype.slice.call(body.querySelectorAll("select")).forEach(function(select) {
      var span = dom.createElement("span");
      applyStaticInlineControlStyle(span, "select");
      span.textContent = selectedOptionText(select) || "\u00a0";
      select.parentNode && select.parentNode.replaceChild(span, select);
    });
    Array.prototype.slice.call(body.querySelectorAll("button")).forEach(function(button) {
      var span = dom.createElement("span");
      applyStaticInlineControlStyle(span, "button");
      span.textContent = String(button.textContent || button.getAttribute("value") || "") || "\u00a0";
      button.parentNode && button.parentNode.replaceChild(span, button);
    });
    return body.innerHTML;
  }

  function cleanHtml(html, opts) {
    opts = opts || {};
    var cleaned;
    if (global.DOMPurify) {
      cleaned = global.DOMPurify.sanitize(html, {
        ADD_TAGS: opts.freezeInteractiveControls ? ["input", "textarea", "select", "option", "button"] : ["input"],
        ADD_ATTR: ["style", "class", "data-*", "aria-*", "id", "href", "name", "role", "colspan", "rowspan", "type", "checked", "value", "placeholder", "selected"],
        FORBID_TAGS: ["script","iframe","object","embed","style","noscript"],
        FORBID_ATTR: ["onclick","onerror","onload","onmouseover","onmouseout","onfocus","onblur"]
      });
    } else {
      cleaned = String(html).replace(/<script[\s\S]*?<\/script>/gi, "")
        .replace(/<style[\s\S]*?<\/style>/gi, "")
        .replace(/\son\w+="[^"]*"/gi, "");
    }
    return opts.freezeInteractiveControls ? freezeInteractiveControls(cleaned) : cleaned;
  }

  // ---- TXT ----
  // Convert to HTML so layout survives CSS-columns slicing. Per-paragraph <p>
  // tags (split on blank lines) encode structure in markup rather than relying
  // on white-space:pre-wrap, which is lost when Range.cloneContents() slices
  // the column fragments away from their wrapper div. Single newlines become
  // <br> within each paragraph.
  var TXT_FLOW_SECTION_CHAR_LIMIT = 18000;

  function splitPlainTextSegment(text, limit) {
    text = String(text || "");
    limit = Math.max(2000, Math.floor(Number(limit) || TXT_FLOW_SECTION_CHAR_LIMIT));
    if (text.length <= limit) return [text];
    var out = [];
    var start = 0;
    while (start < text.length) {
      var hard = Math.min(text.length, start + limit);
      var end = hard;
      if (hard < text.length) {
        var floor = start + Math.floor(limit * 0.55);
        var probe = text.lastIndexOf("\n", hard);
        if (probe < floor) probe = text.lastIndexOf(" ", hard);
        if (probe >= floor) end = probe + 1;
      }
      if (end <= start) end = hard;
      out.push(text.slice(start, end));
      start = end;
    }
    return out;
  }

  function paragraphHtml(para, dir) {
    var align = dir === 'rtl' ? 'right' : 'left';
    return '<p style="margin:0 0 0.75em 0;text-align:' + align + ';" dir="' + (dir || 'ltr') + '">' +
      escapeHtml(para).replace(/\n/g, '<br>') +
      '</p>';
  }

  function buildTxtFlowSections(text, limit, direction) {
    var dir = direction === 'rtl' ? 'rtl' : 'ltr';
    var align = dir === 'rtl' ? 'right' : 'left';
    var paragraphs = String(text || "").split(/\n{2,}/);
    var sections = [];
    var current = [];
    var currentLen = 0;
    function pushCurrent() {
      if (!current.length) return;
      sections.push('<div class="docrender-flow-doc docrender-txt" dir="' + dir + '" style="font-family:inherit;text-align:' + align + ';">' + current.join('') + '</div>');
      current = [];
      currentLen = 0;
    }
    for (var i = 0; i < paragraphs.length; i++) {
      var para = paragraphs[i];
      if (!para.trim()) continue;
      var pieces = splitPlainTextSegment(para, limit);
      for (var j = 0; j < pieces.length; j++) {
        var piece = pieces[j];
        if (!piece.trim()) continue;
        var html = paragraphHtml(piece, dir);
        var len = piece.length + 2;
        if (current.length && currentLen + len > limit) pushCurrent();
        current.push(html);
        currentLen += len;
      }
    }
    pushCurrent();
    if (!sections.length) sections.push('<div class="docrender-flow-doc docrender-txt" dir="' + dir + '" style="font-family:inherit;text-align:' + align + ';"><p></p></div>');
    return sections;
  }

  function parseTxtString(text, direction) {
    var t = String(text || "").replace(/\r\n?/g, "\n");
    var flowSections = buildTxtFlowSections(t, TXT_FLOW_SECTION_CHAR_LIMIT, direction);
    return {
      richHtml: flowSections.length === 1 ? flowSections[0] : "",
      flowSections: flowSections,
      _pageText: t,
      _textMap: t ? [{ start: 0, end: t.length, path: [0, 0] }] : [],
      meta: { format: "TXT", parser: "docrender txt", sourceRenderer: "foliate" }
    };
  }

  async function parseTxtFile(file) {
    return parseTxtString(await file.text());
  }

  // ---- Frozen HTML Upload ----

  // Mirrors Python _inject_extension_snapshot_style: stamps the html element and
  // injects inert/freeze CSS so the webSnapshot iframe path scrolls correctly.
  function _injectWebSnapshotStyle(text) {
    var style = '<style id="docrender-monolith-inert-style">' +
      'html[data-docrender-web-snapshot],html[data-docrender-web-snapshot] body{min-height:100%;scrollbar-width:none!important;overflow-x:hidden!important;overflow-y:auto!important;}' +
      'html[data-docrender-web-snapshot]::-webkit-scrollbar,html[data-docrender-web-snapshot] body::-webkit-scrollbar{width:0!important;height:0!important;}' +
      'html[data-docrender-web-snapshot] *{animation:none!important;transition:none!important;scroll-behavior:auto!important;}' +
      'html[data-docrender-web-snapshot] a,html[data-docrender-web-snapshot] button,html[data-docrender-web-snapshot] input,html[data-docrender-web-snapshot] textarea,html[data-docrender-web-snapshot] select,html[data-docrender-web-snapshot] [role=\'button\']{pointer-events:none!important;}' +
      'html[data-docrender-web-snapshot] video,html[data-docrender-web-snapshot] audio{display:none!important;}' +
      '</style>';
    var marked = /data-docrender-web-snapshot/.test(text)
      ? text
      : text.replace(/<html\b/i, '<html data-docrender-web-snapshot="1"');
    if (/<\/head\s*>/i.test(marked)) {
      return marked.replace(/<\/head\s*>/i, style + '\n</head>');
    }
    return style + '\n' + marked;
  }

  // Uploaded HTML is accepted only when it is a full frozen Chrome-extension
  // snapshot. Generic HTML, fragments, Markdown output, and URL captures are
  // intentionally unsupported.
  function _looksLikeFullHtmlDocument(text) {
    if (!text) return false;
    var head = String(text).slice(0, 2048).trimStart();
    return /^(<!doctype\s+html|<html[\s>])/i.test(head);
  }

  function _looksLikeExtensionFrozenHtml(text) {
    var s = String(text || "");
    return _looksLikeFullHtmlDocument(s) &&
      (
        /\sdata-le-frozen=(["'])1\1/i.test(s) ||
        /<meta\s+name=["']language-engine-source["']/i.test(s) ||
        /<meta\s+name=["']language-engine-captured-at["']/i.test(s)
      );
  }

  async function parseHtmlFile(file) {
    var text = await file.text();
    if (!_looksLikeExtensionFrozenHtml(text)) {
      throw new Error("Only frozen Chrome-extension HTML snapshots are supported.");
    }
    var titleMatch = text.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
    var sourceMetaMatch = text.match(/<meta\s+name=["']language-engine-source["']\s+content=["']([^"']+)["']/i);
    var titleMetaMatch = text.match(/<meta\s+name=["']language-engine-title["']\s+content=["']([^"']+)["']/i);
    var title = (titleMetaMatch && titleMetaMatch[1].trim()) || (titleMatch && titleMatch[1].trim()) || file.name;
    var sourceUrl = (sourceMetaMatch && sourceMetaMatch[1].trim()) || "";
    var enriched = _injectWebSnapshotStyle(text);
    return {
      richHtml: enriched,
      sourcePages: [{
        kind: "webSnapshot",
        html: enriched,
        text: "",
        textLayer: null,
        snapshot: {
          requestedUrl: sourceUrl,
          finalUrl: sourceUrl,
          title: title,
          capture: "chrome-extension-upload"
        }
      }],
      meta: {
        format: "Frozen HTML",
        parser: "docrender extension web snapshot",
        title: title,
        requestedUrl: sourceUrl,
        finalUrl: sourceUrl,
        deferredCanonical: true
      }
    };
  }


  // ---- EPUB ----
  function _xmlText(doc, sel) {
    var el = doc.querySelector(sel);
    return el && el.textContent ? el.textContent.trim() : "";
  }
  function _dirname(p) { var i = p.lastIndexOf("/"); return i === -1 ? "" : p.slice(0, i + 1); }
  function _joinPath(base, rel) {
    if (!base) return rel;
    if (/^[a-z]+:/i.test(rel)) return rel;
    var stack = base.split("/").filter(Boolean);
    var parts = rel.split("/");
    for (var i = 0; i < parts.length; i++) {
      var part = parts[i];
      if (!part || part === ".") continue;
      if (part === "..") stack.pop(); else stack.push(part);
    }
    return stack.join("/");
  }

  async function parseEpubFile(file) {
    if (!global.JSZip) throw new Error("EPUB needs JSZip (jszip.min.js).");
    var zip = await global.JSZip.loadAsync(await file.arrayBuffer());
    var containerXml = await zip.file("META-INF/container.xml").async("text");
    var container = new DOMParser().parseFromString(containerXml, "application/xml");
    var opfPath = container.querySelector("rootfile").getAttribute("full-path");
    var opfText = await zip.file(opfPath).async("text");
    var opf = new DOMParser().parseFromString(opfText, "application/xml");
    var base = _dirname(opfPath);
    var meta = {
      format: "EPUB", parser: "docrender epub",
      title: _xmlText(opf, "metadata > title") || _xmlText(opf, "dc\\:title") || file.name,
      creator: _xmlText(opf, "metadata > creator")
    };
    var manifest = new Map();
    Array.from(opf.querySelectorAll("manifest > item")).forEach(function (item) {
      manifest.set(item.getAttribute("id"), { href: item.getAttribute("href"), mediaType: item.getAttribute("media-type") });
    });
    var naturalPages = [];
    var spine = Array.from(opf.querySelectorAll("spine > itemref"));
    for (var s = 0; s < spine.length; s++) {
      var itemref = spine[s];
      var item = manifest.get(itemref.getAttribute("idref"));
      if (!item || !/html|xhtml/i.test(item.mediaType || item.href)) continue;
      var path = _joinPath(base, item.href);
      var f = zip.file(path);
      if (!f) continue;
      var raw = await f.async("text");
      var cleaned = cleanHtml(raw);
      var dom = new DOMParser().parseFromString(cleaned, "text/html");
      dom.querySelectorAll("a").forEach(function (a) { a.setAttribute("data-href", a.getAttribute("href") || ""); a.removeAttribute("href"); });
      var wrap = document.createElement("div");
      wrap.className = "docrender-epub-chapter";
      wrap.innerHTML = dom.body.innerHTML;
      var page = _finalizePage(wrap);
      naturalPages.push({ html: wrap.outerHTML, text: page.text, textMap: _prefixTextMap(page.textMap, [0]) });
    }
    return {
      richHtml: naturalPages.map(function (p) { return p.html; }).join(""),
      naturalPages: naturalPages,
      meta: meta
    };
  }

  // ---- DOCX ----
  async function _renderWithMammoth(arrayBuffer) {
    if (!global.mammoth || !global.mammoth.convertToHtml) {
      throw new Error("DOCX rendering needs Mammoth.");
    }
    var r = await global.mammoth.convertToHtml({ arrayBuffer: arrayBuffer }, {
      includeDefaultStyleMap: true,
      idPrefix: "le-docx-",
      styleMap: [
        "u => u",
        "highlight => mark",
        "all-caps => span.mammoth-all-caps",
        "small-caps => span.mammoth-small-caps"
      ]
    });
    return {
      value: r && r.value ? r.value : "",
      messages: Array.isArray(r && r.messages) ? r.messages.map(function (m) {
        return {
          type: String((m && m.type) || "message"),
          message: String((m && m.message) || m || "")
        };
      }).filter(function (m) { return !!m.message; }) : []
    };
  }

  async function parseDocxFile(file) {
    var ab = await file.arrayBuffer();
    var mammothResult = await _renderWithMammoth(ab);
    var html = cleanHtml(mammothResult.value, { freezeInteractiveControls: true });
    var wrap = document.createElement("div");
    wrap.className = "docrender-flow-doc docrender-docx mammoth-docx";
    wrap.innerHTML = html;
    var canonicalWrap = wrap.cloneNode(true);
    var page = _finalizePage(canonicalWrap);
    return {
      richHtml: wrap.outerHTML,
      _pageText: page.text,
      _textMap: _prefixTextMap(page.textMap, [0]),
      naturalPages: null,
      meta: {
        format: "DOCX",
        parser: "docrender docx",
        visualRenderer: "mammoth",
        sourceRenderer: "foliate",
        mammothMessages: mammothResult.messages
      }
    };
  }

  // ---- PDF ----
  // _buildPdfPage produces {html, text} from a single shared loop so the
  // text-node concat of the rendered HTML is byte-identical to the text we
  // send to /lookup.
  function _pdfNorm(items, viewport) {
    var vp = viewport || { width: 800, height: 1000, transform: null };
    var transform = Array.isArray(vp.transform) ? vp.transform : null;
    var util = global.pdfjsLib && global.pdfjsLib.Util;
    return (items || [])
      .filter(function (it) { return typeof it.str === "string" && Array.isArray(it.transform) && it.transform.length >= 6; })
      .map(function (item, idx) {
        var rawTx = item.transform;
        var tx = (transform && util && typeof util.transform === "function")
          ? util.transform(transform, rawTx)
          : rawTx;
        var fontSize = Math.max(6, Math.hypot(tx[2] || 0, tx[3] || 0) || Math.hypot(tx[0] || 0, tx[1] || 0) || Number(item.height) || 10);
        return { str: item.str, dir: item.dir, x: tx[4], y: tx[5], fontSize: fontSize,
          width: Number.isFinite(item.width) ? Math.abs(item.width * (viewport && viewport.scale ? viewport.scale : 1)) : Math.max(1, item.str.length * fontSize * 0.5),
          height: Number.isFinite(item.height) ? Math.abs(item.height * (viewport && viewport.scale ? viewport.scale : 1)) : Math.max(8, fontSize),
          hasEOL: !!item.hasEOL, originalIndex: idx };
      })
      .filter(function (it) { return Number.isFinite(it.x) && Number.isFinite(it.y); });
  }

  function _buildPdfPage(items, viewport) {
    var h = Math.max(1, Math.floor(viewport.height || 1000));
    var norm = _pdfNorm(items, viewport).slice().sort(function (a, b) {
      var dy = Math.round(a.y) - Math.round(b.y);
      return Math.abs(dy) > 4 ? dy : (a.x - b.x);
    });
    var maxRight = norm.reduce(function (mx, it) { return Math.max(mx, it.x + (it.width || 0)); }, viewport.width || 800);
    var w = Math.max(1, Math.ceil(maxRight));

    if (!norm.length) {
      var emptyHtml = '<div class="pdf-fixed-page docrender-pdf-page" data-page-width="' + w +
        '" data-page-height="' + h + '" style="position:relative;width:' + w + 'px;height:' + h + 'px">' +
        '<div class="pdf-empty-page" style="padding:24px;opacity:.6;font-style:italic;">No extractable text.</div>' +
        '</div>';
      return { html: emptyHtml, text: "" };
    }

    // Compute median y-gap (line spacing) and median x-gap (word spacing).
    var yGaps = [], xGaps = [];
    for (var gi = 1; gi < norm.length; gi++) {
      var gdy = Math.abs(Math.round(norm[gi].y) - Math.round(norm[gi - 1].y));
      if (gdy > 2) {
        yGaps.push(gdy);
      } else {
        // Same line — measure horizontal gap between end of previous item and start of this one.
        var gdx = norm[gi].x - norm[gi - 1].x;
        if (gdx > 1) xGaps.push(gdx);
      }
    }
    yGaps.sort(function(a, b) { return a - b; });
    xGaps.sort(function(a, b) { return a - b; });
    var medianLineGap = yGaps.length ? yGaps[Math.floor(yGaps.length / 2)] : 20;
    var medianWordGap = xGaps.length ? xGaps[Math.floor(xGaps.length / 2)] : 4;
    var paraGapThreshold = medianLineGap * 1.1;
    var tabGapThreshold = medianWordGap * 2;

    // RTL run reversal pass. Sorting items by ascending x lays them out in
    // visual L→R order on each line, which for RTL scripts (Arabic, Persian,
    // Urdu, Hebrew, Syriac, …) is the REVERSE of logical reading order — each
    // word's letters and the word order itself both end up backwards from
    // what trankit needs. We use the per-item `dir` flag pdf.js sets on every
    // item, so any RTL script is handled automatically without language
    // gating. Spaces and zero-width direction-change markers (always
    // `dir:'ltr'`) inside an RTL stretch are kept inside the reversed run so
    // word order on a pure-RTL line comes out logically correct as well.
    (function reverseRtlRuns() {
      var i = 0;
      while (i < norm.length) {
        if (norm[i].dir !== "rtl") { i++; continue; }
        var lineY = Math.round(norm[i].y);
        var j = i + 1;
        while (j < norm.length) {
          var nj = norm[j];
          if (Math.abs(Math.round(nj.y) - lineY) > 4) break;
          var isNeutral = nj.str === "" || (nj.str === " " && nj.dir === "ltr");
          if (nj.dir === "rtl" || isNeutral) { j++; continue; }
          break;
        }
        var lo = i, hi = j - 1;
        while (lo < hi) { var tmp = norm[lo]; norm[lo] = norm[hi]; norm[hi] = tmp; lo++; hi--; }
        i = j;
      }
    })();

    var htmlParts = [];
    var textParts = [];
    var textMap = [];
    var textLen = 0;
    var childIndex = 0;
    var lastY = null, lastX = null, lastItemX = null, lastHasEOL = false;

    // Word accumulator. We emit ONE positioned <span class="pdf-text-item"> per
    // word, sized to the LITERAL union of its glyphs' bounding boxes — no
    // heuristics, no estimation. After the slice is mounted, reader.js measures
    // each span's browser-shaped text width and applies CSS transform: scaleX()
    // to fit it into the original PDF intended width (data-iw). This is the
    // same scaleX trick Mozilla's stock TextLayer uses to make HTML-shaped text
    // align to canvas-rendered widths. One span per word means one .reader-token
    // per word naturally — no merge hacks required downstream.
    var wordRun = null;
    function flushWord() {
      if (!wordRun || !wordRun.strs.length) { wordRun = null; return; }
      var joined = wordRun.strs.join("");
      if (!joined) { wordRun = null; return; }
      var leftPx = Math.max(0, wordRun.leftX).toFixed(2);
      var topPx = Math.max(0, wordRun.topY).toFixed(2);
      var iwPx = Math.max(0.1, wordRun.rightX - wordRun.leftX).toFixed(2);
      var fs = wordRun.fontSize.toFixed(2);
      var dirAttr = wordRun.dir === "rtl" ? ' dir="rtl"' : '';
      htmlParts.push('<span class="pdf-text-item"' + dirAttr +
        ' data-iw="' + iwPx + '"' +
        ' style="left:' + leftPx + 'px;top:' + topPx +
        'px;font-size:' + fs + 'px">' + escapeHtml(joined) + '</span>');
      textParts.push(joined);
      textMap.push({ start: textLen, end: textLen + joined.length, path: [0, childIndex, 0] });
      textLen += joined.length;
      childIndex++;
      wordRun = null;
    }
    function emitSep(sep) {
      htmlParts.push('<span class="pdf-sep">' + escapeHtml(sep) + '</span>');
      textParts.push(sep);
      textMap.push({ start: textLen, end: textLen + sep.length, path: [0, childIndex, 0] });
      textLen += sep.length;
      childIndex++;
    }

    for (var i = 0; i < norm.length; i++) {
      var it = norm[i];
      if (!it.str) continue;
      // Keep the PDF item text intact; backend normalization owns character stripping.
      it.str = String(it.str == null ? "" : it.str);
      if (!it.str) continue;
      var y = Math.round(it.y);

      // Decide separator that goes BEFORE this item (none for the first one).
      // We rely on (a) explicit pdf.js space items and (b) synthesized seps for
      // line wraps / paragraph breaks as the only word-boundary signals — never
      // synthesize same-line spaces from geometry.
      var sep = "";
      if (lastY !== null) {
        var prevText = textParts.length ? textParts[textParts.length - 1] : "";
        var prevEnd = prevText.length ? prevText.charAt(prevText.length - 1) : "";
        var dy = Math.abs(y - lastY);
        if (dy > paraGapThreshold) {
          sep = "\n\n";
        } else if (dy > 4) {
          if (!/\s/.test(prevEnd)) sep = " ";
        }
      }
      lastHasEOL = !!it.hasEOL;
      if (sep) {
        flushWord();
        emitSep(sep);
      }

      if (it.str === " ") {
        flushWord();
        emitSep(" ");
        // Don't update lastY/lastItemX — zero-height space items shouldn't
        // influence the dy-based paragraph/line-wrap detection.
        continue;
      }

      // Accumulate this glyph's literal bounding box into the current word run.
      var glyphLeft = it.x;
      var glyphRight = it.x + (it.width || 0);
      var glyphTop = it.y - it.fontSize;
      if (!wordRun) {
        wordRun = {
          strs: [it.str],
          leftX: glyphLeft,
          rightX: glyphRight,
          topY: glyphTop,
          fontSize: it.fontSize,
          dir: it.dir
        };
      } else {
        wordRun.strs.push(it.str);
        if (glyphLeft < wordRun.leftX) wordRun.leftX = glyphLeft;
        if (glyphRight > wordRun.rightX) wordRun.rightX = glyphRight;
        if (glyphTop < wordRun.topY) wordRun.topY = glyphTop;
        if (it.fontSize > wordRun.fontSize) wordRun.fontSize = it.fontSize;
      }

      lastY = y;
      lastItemX = it.x;
      lastX = it.x + (it.width || 0);
    }
    flushWord();

    var html = '<div class="pdf-fixed-page docrender-pdf-page" data-page-width="' + w +
      '" data-page-height="' + h + '" style="position:relative;width:' + w + 'px;height:' + h + 'px">' +
      htmlParts.join("") + '</div>';
    return { html: html, text: textParts.join(""), textMap: textMap };
  }

  function _loadScript(src, id) {
    return new Promise(function (resolve, reject) {
      if (id && document.getElementById(id)) return resolve();
      var s = document.createElement("script");
      s.src = src; s.async = true; if (id) s.id = id;
      s.onload = function () { resolve(); };
      s.onerror = function () { reject(new Error("Failed to load " + src)); };
      document.head.appendChild(s);
    });
  }
  async function ensurePdfJs() {
    if (!global.pdfjsLib) {
      await _loadScript("https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.min.js", "pdfjs-lib");
    }
    if (!global.pdfjsLib) throw new Error("pdfjsLib missing after load");
    if (global.pdfjsLib.GlobalWorkerOptions && !global.pdfjsLib.GlobalWorkerOptions.workerSrc) {
      global.pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js";
    }
  }

  async function parsePdfFile(file) {
    await ensurePdfJs();
    var ab = await file.arrayBuffer();
    var pdf = await global.pdfjsLib.getDocument({ data: ab, useSystemFonts: true }).promise;
    var naturalPages = [];
    for (var n = 1; n <= pdf.numPages; n++) {
      try {
        var page = await pdf.getPage(n);
        var viewport = page.getViewport({ scale: 1.35 });
        var tc = await page.getTextContent({ includeMarkedContent: false });
        var built = _buildPdfPage(tc.items || [], viewport);
        naturalPages.push({ html: built.html, text: built.text, textMap: built.textMap || [] });
      } catch (err) { console.warn("PDF page " + n + " failed:", err); }
    }
    return {
      richHtml: naturalPages.map(function (p) { return p.html; }).join(""),
      naturalPages: naturalPages,
      meta: { format: "PDF", parser: "docrender pdf", pages: pdf.numPages }
    };
  }

  // ---- PDF word-span fit-to-intended-width pass (post-mount) ----
  // _buildPdfPage emits one .pdf-text-item per word, sized by the literal
  // union of its glyphs' bounding boxes (data-iw = intended width in px).
  // The browser shapes the joined text using its own font metrics, which
  // generally produces a different visible width than the original PDF
  // kerning. This pass measures each span's browser-shaped width and applies
  // CSS transform: scaleX so the rendered text fits exactly into the
  // PDF's intended width — same approach Mozilla's stock TextLayer uses
  // (per-item; we apply per-word). Idempotent; safe to re-run after layout.
  function fitPdfWordSpansToIntendedWidth(root) {
    if (!root || !root.querySelectorAll) return 0;
    var spans = root.querySelectorAll('.pdf-text-item[data-iw]');
    var count = 0;
    for (var i = 0; i < spans.length; i++) {
      var el = spans[i];
      var iw = parseFloat(el.getAttribute('data-iw'));
      if (!isFinite(iw) || iw <= 0) continue;
      // Reset any prior transform so the measurement reflects the natural width.
      var priorTransform = el.style.transform;
      if (priorTransform) el.style.transform = '';
      var mw = el.offsetWidth;
      if (!mw || mw <= 0) {
        if (priorTransform) el.style.transform = priorTransform;
        continue;
      }
      var s = iw / mw;
      // Skip imperceptible scale corrections to avoid sub-pixel shimmer.
      if (Math.abs(s - 1) < 0.01) {
        el.style.transform = '';
        continue;
      }
      el.style.transform = 'scaleX(' + s.toFixed(4) + ')';
      count++;
    }
    return count;
  }

  // ---- Public API ----
  function extOf(name) { return String(name || "").toLowerCase().split(".").pop(); }

  async function parseFile(file) {
    var ext = extOf(file.name);
    if (["txt","text"].includes(ext)) return parseTxtFile(file);
    if (["html","htm"].includes(ext)) return parseHtmlFile(file);
    if (ext === "docx") return parseDocxFile(file);
    if (["md","markdown"].includes(ext)) throw new Error("Markdown files are not supported.");
    if (ext === "xhtml") throw new Error("Only frozen Chrome-extension .html snapshots are supported.");
    if (ext === "pdf") throw new Error("PDF files use the PDF.js reader path, not DocRender.");
    if (["epub","mobi","azw3","fb2","fbz"].includes(ext)) throw new Error("Ebooks use the Foliate reader path, not DocRender.");
    throw new Error("Unsupported format: ." + ext);
  }

  global.DocRenderParsers = {
    parseFile: parseFile,
    parseTxtFile: parseTxtFile, parseTxtString: parseTxtString,
    parseHtmlFile: parseHtmlFile,
    parseDocxFile: parseDocxFile,
    cleanHtml: cleanHtml, escapeHtml: escapeHtml,
    extOf: extOf,
    extractText: extractText,
    extractTextAndMap: extractTextAndMap,
    extractTextFromLiveRoot: extractTextFromLiveRoot,
    extractCanonicalTextAndRuns: extractCanonicalTextAndRuns,
    prefixTextMap: _prefixTextMap,
    insertBlockSeparators: _insertBlockSeparators
  };
})(window);
