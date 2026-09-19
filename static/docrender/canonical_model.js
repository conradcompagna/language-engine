/* canonical_model.js
 *
 * Plain data-model helpers for the canonical bottom-pane document.
 *
 * This model is deliberately not HTML. It is a styled textual skeleton:
 *   Document -> Pages -> Blocks -> Runs -> Tokens.
 *
 * The central invariant is always:
 *   page.text === page.blocks.flatMap(block => block.runs).map(run => run.text).join('')
 *
 * Browser global:
 *   window.CanonicalModel
 */
(function(global) {
  'use strict';

  var uidCounter = 0;

  function uid(prefix) {
    uidCounter += 1;
    return String(prefix || 'id') + '-' + Date.now().toString(36) + '-' + uidCounter.toString(36);
  }

  function str(v) {
    return v == null ? '' : String(v);
  }

  function num(v, fallback) {
    var n = Number(v);
    return isFinite(n) ? n : (fallback || 0);
  }

  function shallowClone(obj) {
    var out = {};
    obj = obj || {};
    Object.keys(obj).forEach(function(k) { out[k] = obj[k]; });
    return out;
  }

  function cloneJson(obj) {
    if (obj == null) return obj;
    return JSON.parse(JSON.stringify(obj));
  }

  function normalizeStyle(style) {
    if (global.CanonicalStyle && typeof global.CanonicalStyle.normalizeTextStyle === 'function') {
      return global.CanonicalStyle.normalizeTextStyle(style || {});
    }
    return shallowClone(style || {});
  }

  function makeDocument(opts) {
    opts = opts || {};
    return {
      schemaVersion: 1,
      id: str(opts.id) || uid('cdoc'),
      meta: shallowClone(opts.meta || {}),
      pages: Array.isArray(opts.pages) ? opts.pages : [],
      flowBlocks: Array.isArray(opts.flowBlocks) ? opts.flowBlocks : [],
      source: shallowClone(opts.source || {})
    };
  }

  function makePage(opts) {
    opts = opts || {};
    return {
      id: str(opts.id) || uid('cpage'),
      index: num(opts.index, 0),
      text: str(opts.text),
      blocks: Array.isArray(opts.blocks) ? opts.blocks : [],
      tokens: Array.isArray(opts.tokens) ? opts.tokens : [],
      layout: shallowClone(opts.layout || {}),
      source: shallowClone(opts.source || {})
    };
  }

  function makeBlock(opts) {
    opts = opts || {};
    return {
      id: str(opts.id) || uid('cblock'),
      type: str(opts.type) || 'paragraph',
      start: num(opts.start, 0),
      end: num(opts.end, 0),
      style: normalizeStyle(opts.style || {}),
      layout: shallowClone(opts.layout || {}),
      runs: Array.isArray(opts.runs) ? opts.runs : [],
      source: shallowClone(opts.source || {})
    };
  }

  function makeRun(opts) {
    opts = opts || {};
    return {
      id: str(opts.id) || uid('crun'),
      text: str(opts.text),
      start: num(opts.start, 0),
      end: num(opts.end, num(opts.start, 0) + str(opts.text).length),
      style: normalizeStyle(opts.style || {}),
      layout: shallowClone(opts.layout || {}),
      rects: Array.isArray(opts.rects) ? opts.rects.map(function(r) { return shallowClone(r); }) : [],
      source: shallowClone(opts.source || {})
    };
  }

  function makeToken(opts) {
    opts = opts || {};
    var start = num(opts.start, 0);
    var text = str(opts.text);
    return {
      id: str(opts.id) || uid('ctok'),
      index: num(opts.index, 0),
      start: start,
      end: num(opts.end, start + text.length),
      text: text,
      segment: str(opts.segment || text),
      lemma: str(opts.lemma),
      upos: str(opts.upos),
      xpos: str(opts.xpos),
      feats: opts.feats || null,
      dep: opts.dep || null,
      ner: opts.ner || null,
      dictEntry: opts.dictEntry || null,
      dictEntries: Array.isArray(opts.dictEntries) ? opts.dictEntries : [],
      fillHits: Array.isArray(opts.fillHits) ? opts.fillHits : [],
      grammar: opts.grammar || null,
      ud: opts.ud || null,
      raw: opts.raw || null
    };
  }

  function getRuns(pageOrBlock) {
    if (!pageOrBlock) return [];
    if (Array.isArray(pageOrBlock.runs)) return pageOrBlock.runs;
    var out = [];
    var blocks = Array.isArray(pageOrBlock.blocks) ? pageOrBlock.blocks : [];
    for (var i = 0; i < blocks.length; i++) {
      var runs = Array.isArray(blocks[i].runs) ? blocks[i].runs : [];
      for (var j = 0; j < runs.length; j++) out.push(runs[j]);
    }
    return out;
  }

  function recomputePageText(page) {
    if (!page) return '';
    var text = '';
    var blocks = Array.isArray(page.blocks) ? page.blocks : [];
    for (var bi = 0; bi < blocks.length; bi++) {
      var block = blocks[bi];
      block.start = text.length;
      var runs = Array.isArray(block.runs) ? block.runs : [];
      for (var ri = 0; ri < runs.length; ri++) {
        var run = runs[ri];
        run.text = str(run.text);
        run.start = text.length;
        text += run.text;
        run.end = text.length;
      }
      block.end = text.length;
    }
    page.text = text;
    return text;
  }

  function pageTextFromRuns(page) {
    if (!page) return '';
    return getRuns(page).map(function(r) { return str(r.text); }).join('');
  }

  function assertPageInvariant(page, label) {
    var expected = pageTextFromRuns(page);
    var actual = str(page && page.text);
    if (expected !== actual) {
      var err = new Error('Canonical page text invariant failed' + (label ? ' for ' + label : '') + ': page.text length ' + actual.length + ' !== runs length ' + expected.length);
      err.expectedText = expected;
      err.actualText = actual;
      throw err;
    }
    return true;
  }

  function validateDocument(doc, opts) {
    opts = opts || {};
    var errors = [];
    if (!doc || typeof doc !== 'object') errors.push('document missing');
    var pages = doc && Array.isArray(doc.pages) ? doc.pages : [];
    for (var pi = 0; pi < pages.length; pi++) {
      try { assertPageInvariant(pages[pi], 'page ' + pi); }
      catch (e) { errors.push(e.message); }
    }
    if (errors.length && opts.throwOnError) throw new Error(errors.join('\n'));
    return { ok: errors.length === 0, errors: errors };
  }

  function cloneDocument(doc) {
    return cloneJson(doc);
  }

  function findTokenAtOffset(page, offset) {
    var tokens = page && Array.isArray(page.tokens) ? page.tokens : [];
    var o = num(offset, 0);
    for (var i = 0; i < tokens.length; i++) {
      if (o >= tokens[i].start && o < tokens[i].end) return tokens[i];
    }
    return null;
  }

  function findRunIntersections(page, start, end) {
    var runs = getRuns(page);
    var s = num(start, 0);
    var e = num(end, s);
    var out = [];
    for (var i = 0; i < runs.length; i++) {
      var r = runs[i];
      if (r.end <= s || r.start >= e) continue;
      out.push({
        run: r,
        start: Math.max(s, r.start),
        end: Math.min(e, r.end),
        localStart: Math.max(s, r.start) - r.start,
        localEnd: Math.min(e, r.end) - r.start
      });
    }
    return out;
  }

  global.CanonicalModel = {
    uid: uid,
    makeDocument: makeDocument,
    makePage: makePage,
    makeBlock: makeBlock,
    makeRun: makeRun,
    makeToken: makeToken,
    getRuns: getRuns,
    recomputePageText: recomputePageText,
    pageTextFromRuns: pageTextFromRuns,
    assertPageInvariant: assertPageInvariant,
    validateDocument: validateDocument,
    cloneDocument: cloneDocument,
    findTokenAtOffset: findTokenAtOffset,
    findRunIntersections: findRunIntersections
  };
})(window);
