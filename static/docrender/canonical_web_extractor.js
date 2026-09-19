/* canonical_web_extractor.js
 *
 * Builds canonical fixed-layout pages from the rendered text visible inside a
 * DocRender web snapshot iframe. The top iframe layout is the source of truth.
 *
 * Browser global:
 *   window.CanonicalWebExtractor
 */
(function(global) {
  'use strict';

  var ROOT_SELECTORS = [
    'main',
    '#content',
    '[role="main"]',
    'article',
    '#mw-content-text',
    '.mw-parser-output',
    'body'
  ];

  var IGNORE_SELECTOR = [
    'script',
    'style',
    'noscript',
    'template',
    'svg',
    'canvas',
    'iframe',
    'object',
    'embed',
    'input',
    'textarea',
    'select',
    'option',
    'button',
    '[hidden]',
    '[aria-hidden="true"]',
    '[role="navigation"]',
    '[role="button"]',
    'nav',
    'header',
    'footer',
    'aside',
    '.mw-editsection',
    '.mw-jump-link',
    '.vector-page-toolbar',
    '.vector-toc',
    '.vector-appearance',
    '.mw-portlet',
    '.noprint',
    '.metadata',
    '.ambox',
    '.navbox',
    '.catlinks'
  ].join(',');

  function requireDeps() {
    if (!global.CanonicalModel || !global.CanonicalStyle) {
      throw new Error('CanonicalModel and CanonicalStyle must be loaded before CanonicalWebExtractor');
    }
  }

  function str(v) {
    return v == null ? '' : String(v);
  }

  function num(v, fallback) {
    var n = Number(v);
    return isFinite(n) ? n : (fallback || 0);
  }

  function normalizedWhitespace(value) {
    if (!value) return '';
    return /\n/.test(value) ? '\n' : ' ';
  }

  function textSample(root) {
    return str(root && root.textContent).replace(/\s+/g, ' ').trim();
  }

  function chooseRoot(doc) {
    var best = doc.body || doc.documentElement;
    var bestLen = textSample(best).length;
    for (var i = 0; i < ROOT_SELECTORS.length; i++) {
      var el = doc.querySelector(ROOT_SELECTORS[i]);
      if (!el) continue;
      var len = textSample(el).length;
      if (len >= 80 || len >= bestLen * 0.35) return el;
      if (len > bestLen) {
        best = el;
        bestLen = len;
      }
    }
    return best;
  }

  function closestIgnored(el, root) {
    if (!el || el === root || !el.closest) return null;
    var ignored = el.closest(IGNORE_SELECTOR);
    if (!ignored || ignored === root) return null;
    return ignored;
  }

  function isVisibleElement(el, win) {
    if (!el || el.nodeType !== 1) return false;
    if (closestIgnored(el, null)) return false;
    var cs;
    try { cs = win.getComputedStyle(el); } catch (_e) { cs = null; }
    if (!cs) return true;
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse') return false;
    if (Number(cs.opacity) === 0) return false;
    return true;
  }

  function isReadableTextNode(node, root, win) {
    if (!node || node.nodeType !== 3) return false;
    if (!str(node.nodeValue).trim()) return false;
    var parent = node.parentElement;
    if (!parent || !root.contains(parent)) return false;
    if (closestIgnored(parent, root)) return false;
    var el = parent;
    while (el && el.nodeType === 1 && el !== root) {
      if (!isVisibleElement(el, win)) return false;
      el = el.parentElement;
    }
    return isVisibleElement(parent, win);
  }

  function makeSegments(text, lang) {
    var value = str(text);
    var out = [];
    if (!value) return out;
    if (global.Intl && global.Intl.Segmenter) {
      try {
        var segmenter = new global.Intl.Segmenter(lang || undefined, { granularity: 'word' });
        Array.from(segmenter.segment(value)).forEach(function(part) {
          out.push({
            text: part.segment,
            start: part.index,
            end: part.index + part.segment.length,
            whitespace: !str(part.segment).trim()
          });
        });
        return out;
      } catch (_e) {}
    }
    var re = /\s+|[^\s]+/g;
    var m;
    while ((m = re.exec(value))) {
      out.push({ text: m[0], start: m.index, end: m.index + m[0].length, whitespace: !m[0].trim() });
    }
    return out;
  }

  function graphemeSegments(text) {
    var value = str(text);
    if (!value) return [];
    if (global.Intl && global.Intl.Segmenter) {
      try {
        var segmenter = new global.Intl.Segmenter(undefined, { granularity: 'grapheme' });
        return Array.from(segmenter.segment(value)).map(function(part) {
          return { text: part.segment, start: part.index, end: part.index + part.segment.length };
        });
      } catch (_e) {}
    }
    var out = [];
    var cursor = 0;
    Array.from(value).forEach(function(ch) {
      out.push({ text: ch, start: cursor, end: cursor + ch.length });
      cursor += ch.length;
    });
    return out;
  }

  function rectsForRange(doc, node, start, end) {
    var range = doc.createRange();
    try {
      range.setStart(node, start);
      range.setEnd(node, end);
      return Array.from(range.getClientRects ? range.getClientRects() : []);
    } catch (_e) {
      return [];
    } finally {
      try { range.detach(); } catch (_ignore) {}
    }
  }

  function computedStyleForNode(node, win) {
    var el = node && node.parentElement;
    if (!global.CanonicalStyle || !global.CanonicalStyle.readComputedTextStyle) return {};
    return global.CanonicalStyle.readComputedTextStyle(el, {});
  }

  function rectIsUsable(rect) {
    return !!(rect && num(rect.width, 0) > 0.5 && num(rect.height, 0) > 0.5);
  }

  function addRectItem(items, state, node, text, rect, style, leadingWhitespace, sourceOrder) {
    var pageWidth = Math.max(1, num(state.pageWidth, 600));
    var pageHeight = Math.max(1, num(state.pageHeight, 800));
    var win = state.win;
    var scrollX = num(win && win.scrollX, 0);
    var scrollY = num(win && win.scrollY, 0);
    var absLeft = num(rect.left, 0) + scrollX;
    var absTop = num(rect.top, 0) + scrollY;
    var width = num(rect.width, 0);
    var height = num(rect.height, 0);
    if (absLeft + width < 0 || absLeft > pageWidth) return;
    var firstPage = Math.max(0, Math.floor(absTop / pageHeight));
    var lastPage = Math.max(firstPage, Math.floor(Math.max(absTop, absTop + height - 1) / pageHeight));
    for (var pageIndex = firstPage; pageIndex <= lastPage; pageIndex++) {
      var pageTop = pageIndex * pageHeight;
      var pageBottom = pageTop + pageHeight;
      if (absTop + height <= pageTop || absTop >= pageBottom) continue;
      items.push({
        pageIndex: pageIndex,
        text: text,
        x: Math.max(0, absLeft),
        y: Math.max(0, absTop - pageTop),
        absTop: absTop,
        width: width,
        height: height,
        lineHeight: parseFloat(style.lineHeight) || height,
        style: style,
        leadingWhitespace: leadingWhitespace,
        sourceOrder: sourceOrder,
        sourceNode: node
      });
    }
  }

  function collectItems(state, opts) {
    var doc = state.doc;
    var win = state.win || (doc && doc.defaultView) || global;
    var root = opts.root || chooseRoot(doc);
    var walker = doc.createTreeWalker(root, (win.NodeFilter && win.NodeFilter.SHOW_TEXT) || 4, {
      acceptNode: function(node) {
        return isReadableTextNode(node, root, win)
          ? ((win.NodeFilter && win.NodeFilter.FILTER_ACCEPT) || 1)
          : ((win.NodeFilter && win.NodeFilter.FILTER_REJECT) || 2);
      }
    });
    var items = [];
    var pendingWhitespace = '';
    var order = 0;
    var lang = opts.lang || doc.documentElement.getAttribute('lang') || '';
    var node;
    while ((node = walker.nextNode())) {
      var text = str(node.nodeValue);
      var style = computedStyleForNode(node, win);
      var segments = makeSegments(text, lang);
      for (var i = 0; i < segments.length; i++) {
        var seg = segments[i];
        if (seg.whitespace) {
          pendingWhitespace += seg.text;
          continue;
        }
        var rects = rectsForRange(doc, node, seg.start, seg.end).filter(rectIsUsable);
        if (rects.length > 1 && seg.text.length > 1) {
          var gs = graphemeSegments(seg.text);
          for (var gi = 0; gi < gs.length; gi++) {
            var g = gs[gi];
            var gRects = rectsForRange(doc, node, seg.start + g.start, seg.start + g.end).filter(rectIsUsable);
            for (var gri = 0; gri < gRects.length; gri++) {
              addRectItem(items, state, node, g.text, gRects[gri], style, pendingWhitespace, order++);
              pendingWhitespace = '';
            }
          }
        } else {
          for (var ri = 0; ri < rects.length; ri++) {
            addRectItem(items, state, node, seg.text, rects[ri], style, pendingWhitespace, order++);
            pendingWhitespace = '';
          }
        }
      }
    }
    return items;
  }

  function shouldInsertVisualSpace(prev, item) {
    if (!prev || !item) return false;
    var prevEnd = num(prev.x, 0) + num(prev.width, 0);
    var gap = num(item.x, 0) - prevEnd;
    if (gap < 3) return false;
    var a = str(prev.text).slice(-1);
    var b = str(item.text).charAt(0);
    return /[A-Za-z0-9]/.test(a) && /[A-Za-z0-9]/.test(b);
  }

  function separatorBetween(prev, item) {
    if (!prev) return '';
    var dy = Math.abs(num(item.y, 0) - num(prev.y, 0));
    var line = Math.max(8, num(prev.lineHeight, prev.height || 16) * 0.72);
    if (dy > line) return '\n';
    var fromSource = normalizedWhitespace(item.leadingWhitespace);
    if (fromSource) return fromSource;
    return shouldInsertVisualSpace(prev, item) ? ' ' : '';
  }

  function addSeparatorRun(runs, cursor, sep, pageIndex) {
    if (!sep) return cursor;
    var start = cursor;
    var end = start + sep.length;
    runs.push(global.CanonicalModel.makeRun({
      id: 'web-sep-' + pageIndex + '-' + runs.length,
      text: sep,
      start: start,
      end: end,
      style: { fontSize: '0px', lineHeight: '0' },
      layout: { mode: 'fixed', x: -99999, y: -99999, width: 0, height: 0 },
      source: { synthetic: true, kind: 'web-separator' }
    }));
    return end;
  }

  function buildPage(state, pageIndex, rawItems, opts) {
    var pageWidth = Math.max(1, num(state.pageWidth, 600));
    var pageHeight = Math.max(1, num(state.pageHeight, 800));
    var items = rawItems.slice().sort(function(a, b) {
      var ay = Math.round(num(a.y, 0) / 3) * 3;
      var by = Math.round(num(b.y, 0) / 3) * 3;
      return ay - by || num(a.x, 0) - num(b.x, 0) || num(a.sourceOrder, 0) - num(b.sourceOrder, 0);
    });
    var runs = [];
    var text = '';
    var prev = null;
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var sep = separatorBetween(prev, item);
      if (text && sep) {
        var sepStart = text.length;
        text += sep;
        addSeparatorRun(runs, sepStart, sep, pageIndex);
      }
      var start = text.length;
      text += item.text;
      runs.push(global.CanonicalModel.makeRun({
        id: 'web-run-' + pageIndex + '-' + i,
        text: item.text,
        start: start,
        end: text.length,
        style: item.style || {},
        layout: {
          mode: 'fixed',
          x: item.x,
          y: item.y,
          width: item.width,
          height: item.height,
          fitWidth: item.width
        },
        rects: [{ x: item.x, y: item.y, width: item.width, height: item.height }],
        source: {
          kind: 'webSnapshot',
          sourceOrder: item.sourceOrder
        }
      }));
      prev = item;
    }
    var block = global.CanonicalModel.makeBlock({
      id: 'web-block-' + pageIndex,
      type: 'webLayer',
      start: 0,
      end: text.length,
      layout: { mode: 'fixed', x: 0, y: 0, width: pageWidth, height: pageHeight },
      style: {},
      runs: runs,
      source: { kind: 'webSnapshot' }
    });
    return global.CanonicalModel.makePage({
      id: 'web-page-' + pageIndex,
      index: pageIndex,
      text: text,
      blocks: [block],
      layout: { mode: 'fixed', width: pageWidth, height: pageHeight },
      source: {
        kind: 'webSnapshot',
        pageTop: pageIndex * pageHeight,
        pageHeight: pageHeight,
        finalUrl: state.meta && state.meta.finalUrl || ''
      }
    });
  }

  function documentFromSnapshot(state, opts) {
    requireDeps();
    opts = opts || {};
    if (!state || !state.doc || !state.win) throw new Error('web snapshot iframe is not ready');
    if (global.DocRenderWebSnapshotRenderer && global.DocRenderWebSnapshotRenderer.recomputeMetrics) {
      global.DocRenderWebSnapshotRenderer.recomputeMetrics(state);
    }
    var pageCount = Math.max(1, Math.min(num(opts.maxPages, 160), num(state.pageCount, 1)));
    var buckets = [];
    for (var i = 0; i < pageCount; i++) buckets.push([]);
    var items = collectItems(state, opts);
    for (var j = 0; j < items.length; j++) {
      var idx = Math.max(0, Math.min(pageCount - 1, num(items[j].pageIndex, 0)));
      buckets[idx].push(items[j]);
    }
    var pages = [];
    for (var pi = 0; pi < pageCount; pi++) pages.push(buildPage(state, pi, buckets[pi], opts));
    var doc = global.CanonicalModel.makeDocument({
      id: 'webdoc-' + Date.now().toString(36),
      meta: Object.assign({
        format: 'Remote HTML',
        parser: 'canonical-web-visible-extractor',
        title: state.meta && state.meta.title || '',
        finalUrl: state.meta && state.meta.finalUrl || ''
      }, opts.meta || {}),
      pages: pages,
      source: { kind: 'webSnapshot' }
    });
    global.CanonicalModel.validateDocument(doc, { throwOnError: true });
    return doc;
  }

  global.CanonicalWebExtractor = {
    documentFromSnapshot: documentFromSnapshot,
    chooseRoot: chooseRoot,
    collectItems: collectItems
  };
})(window);
