/* docrender/loader.js
 *
 * Narrow active loader contract:
 *   - TXT/raw text and DOCX return Foliate flow source sections.
 *   - Frozen Chrome-extension HTML uploads return deferred webSnapshot pages.
 *   - No URL loading, Markdown, HTML fragments, PDF, EPUB, or legacy canonical
 *     conversion is supported here.
 */
(function (global) {
  "use strict";

  function _requireParsers() {
    if (!global.DocRenderParsers) throw new Error("DocRenderParsers not loaded");
  }

  function _normalizeSizeOpts(sizeOpts) {
    sizeOpts = sizeOpts || {};
    return {
      width: Math.max(120, Math.floor(Number(sizeOpts.width) || 600)),
      height: Math.max(120, Math.floor(Number(sizeOpts.height) || 800))
    };
  }

  function _ensureSourcePages(parsed) {
    parsed = parsed || {};
    var meta = parsed.meta || {};
    var isFoliate = String(meta.sourceRenderer || "").toLowerCase() === "foliate";
    if (isFoliate) {
      return [{
        html: (parsed.flowSections && parsed.flowSections[0]) || parsed.richHtml || "",
        text: parsed._pageText || "",
        textMap: parsed._textMap || []
      }];
    }
    if (parsed.sourcePages && parsed.sourcePages.length && parsed.sourcePages[0].kind === "webSnapshot") {
      return parsed.sourcePages;
    }
    throw new Error("Unsupported document path. Use PDF, ebook, TXT, DOCX, or frozen extension HTML.");
  }

  function _finishParsed(parsed, sizeOpts) {
    var size = _normalizeSizeOpts(sizeOpts);
    var meta = (parsed && parsed.meta) || {};
    var sourcePages = _ensureSourcePages(parsed || {});
    var foliateSource = String(meta.sourceRenderer || "").toLowerCase() === "foliate";
    var webSnapshotSource = !!(sourcePages && sourcePages[0] && sourcePages[0].kind === "webSnapshot");
    if (!foliateSource && !webSnapshotSource) {
      throw new Error("Unsupported document path. Use PDF, ebook, TXT, DOCX, or frozen extension HTML.");
    }
    return {
      richHtml: (parsed && parsed.richHtml) || "",
      flowSections: (parsed && parsed.flowSections) || null,
      fullText: (parsed && parsed._pageText) || "",
      sourcePages: sourcePages,
      pages: sourcePages,
      canonicalDocument: null,
      canonicalDoc: null,
      meta: Object.assign({}, meta, {
        deferredCanonical: true,
        viewportWidth: size.width,
        viewportHeight: size.height
      })
    };
  }

  async function loadFile(file, sizeOpts) {
    _requireParsers();
    var parsed = await global.DocRenderParsers.parseFile(file);
    return _finishParsed(parsed, sizeOpts || { width: 600, height: 800 });
  }

  async function loadText(text, sizeOpts, fileName, direction) {
    _requireParsers();
    var parsed = global.DocRenderParsers.parseTxtString(text, direction);
    if (fileName) parsed.meta.fileName = fileName;
    return _finishParsed(parsed, sizeOpts || { width: 600, height: 800 });
  }

  global.DocRenderLoader = {
    loadFile: loadFile,
    loadText: loadText
  };
})(window);
