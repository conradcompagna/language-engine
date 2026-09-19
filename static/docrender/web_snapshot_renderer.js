/* web_snapshot_renderer.js
 *
 * Top-pane renderer for remote HTML snapshots. It keeps the page as a whole
 * inert iframe and uses viewport slices as document pages.
 *
 * Browser global:
 *   window.DocRenderWebSnapshotRenderer
 */
(function(global) {
  'use strict';

  // Hidden performance toggle for frozen HTML snapshots. Set this to false if
  // content-visibility causes layout shifts or fidelity issues on captured pages.
  var HTML_SNAPSHOT_CONTENT_VISIBILITY_ENABLED = true;
  var HTML_SNAPSHOT_CONTENT_VISIBILITY_STYLE_ID = 'docrender-websnapshot-content-visibility-style';
  var HTML_SNAPSHOT_CONTENT_VISIBILITY_ATTR = 'data-le-cv-block';
  var HTML_SNAPSHOT_CONTENT_VISIBILITY_INTRINSIC_SIZE = 'auto 900px';
  var HTML_SNAPSHOT_CONTENT_VISIBILITY_MAX_BLOCKS = 1200;
  var HTML_SNAPSHOT_CONTENT_VISIBILITY_MIN_HEIGHT = 160;
  var HTML_SNAPSHOT_CONTENT_VISIBILITY_SELECTOR = [
    'article > *',
    'main > *',
    'section',
    'body > div:not(#docrender-html-scale-shell)',
    '#docrender-html-scale-root > div'
  ].join(',');

  function num(v, fallback) {
    var n = Number(v);
    return isFinite(n) ? n : (fallback || 0);
  }

  function str(v) {
    return v == null ? '' : String(v);
  }

  function isSnapshotPage(page) {
    return !!(page && (page.kind === 'webSnapshot' || page.type === 'webSnapshot'));
  }

  function snapshotKey(page) {
    var snap = page && page.snapshot || {};
    return str(page && (page.id || page.snapshotId)) ||
      [str(snap.finalUrl || snap.requestedUrl), str(snap.title), str(page && page.html).length].join('|');
  }

  function nextFrame(win) {
    return new Promise(function(resolve) {
      (win && win.requestAnimationFrame ? win.requestAnimationFrame.bind(win) : global.requestAnimationFrame)(function() {
        resolve();
      });
    });
  }

  function delay(ms) {
    return new Promise(function(resolve) { global.setTimeout(resolve, ms); });
  }

  async function waitForStableLayout(state) {
    if (state && state.flatBitmap) {
      await nextFrame(state.win || global);
      return;
    }
    var doc = state.doc;
    try {
      if (doc && doc.fonts && doc.fonts.ready) await doc.fonts.ready;
    } catch (_e) {}
    try {
      await waitForImages(doc, 900);
    } catch (_e2) {}
    await nextFrame(state.win || global);
    await nextFrame(state.win || global);
    await delay(180);
  }

  function waitForImages(doc, maxWait) {
    var images = Array.from(doc && doc.images ? doc.images : []).filter(function(img) {
      return img && !img.complete;
    });
    if (!images.length) return Promise.resolve();
    var done = new Promise(function(resolve) {
      var remaining = images.length;
      function oneDone() {
        remaining -= 1;
        if (remaining <= 0) resolve();
      }
      images.forEach(function(img) {
        img.addEventListener('load', oneDone, { once: true });
        img.addEventListener('error', oneDone, { once: true });
      });
    });
    return Promise.race([done, delay(maxWait || 900)]);
  }

  function recomputeMetrics(state) {
    var doc = state.doc;
    var docEl = doc && doc.documentElement;
    var body = doc && doc.body;
    var metrics = {};
    var scale = Math.max(0.001, num(state && state.bitmapScale, 1) || 1);
    var pageHeight = Math.max(1, num(state.pageHeight, 800));
    var pageWidth = Math.max(1, num(state.pageWidth, 600));
    var contentHeight = Math.max(
      pageHeight,
      num(metrics.documentHeight, 0) * scale,
      num(docEl && docEl.scrollHeight, 0),
      num(body && body.scrollHeight, 0),
      num(docEl && docEl.offsetHeight, 0),
      num(body && body.offsetHeight, 0)
    );
    var contentWidth = Math.max(
      pageWidth,
      num(metrics.documentWidth, 0) * scale,
      num(docEl && docEl.scrollWidth, 0),
      num(body && body.scrollWidth, 0),
      num(docEl && docEl.offsetWidth, 0),
      num(body && body.offsetWidth, 0)
    );
    state.contentHeight = contentHeight;
    state.contentWidth = contentWidth;
    state.pageCount = Math.max(1, Math.ceil(contentHeight / pageHeight));
    updateScrollState(state);
    return state;
  }

  function pushUnique(list, item) {
    if (!item) return;
    for (var i = 0; i < list.length; i++) {
      if (list[i] === item) return;
    }
    list.push(item);
  }

  function scrollElementCandidates(state) {
    var doc = state && state.doc;
    if (!doc) return null;
    var out = [];
    pushUnique(out, doc.scrollingElement);
    pushUnique(out, doc.documentElement);
    pushUnique(out, doc.body);
    return out;
  }

  function elementMaxScroll(el) {
    if (!el) return 0;
    return Math.max(0, num(el.scrollHeight, 0) - num(el.clientHeight, 0));
  }

  function getScrollElement(state) {
    var doc = state && state.doc;
    if (!doc) return null;
    var candidates = scrollElementCandidates(state) || [];
    var active = null;
    var activeTop = 0;
    for (var ai = 0; ai < candidates.length; ai++) {
      var cand = candidates[ai];
      var top = num(cand && cand.scrollTop, 0);
      if (elementMaxScroll(cand) > 1 && top > activeTop) {
        active = cand;
        activeTop = top;
      }
    }
    if (active) return active;

    var best = null;
    var bestMax = -1;
    for (var i = 0; i < candidates.length; i++) {
      var el = candidates[i];
      var max = elementMaxScroll(el);
      if (max > bestMax + 1) {
        best = el;
        bestMax = max;
      }
    }
    return best || doc.scrollingElement || doc.documentElement || doc.body || null;
  }

  function getScrollTop(state) {
    var scrollEl = getScrollElement(state);
    var top = scrollEl ? num(scrollEl.scrollTop, 0) : 0;
    if (!top && state && state.win) top = Math.max(top, num(state.win.scrollY, 0));
    return top;
  }

  function getScrollLeft(state) {
    var scrollEl = getScrollElement(state);
    var left = scrollEl ? num(scrollEl.scrollLeft, 0) : 0;
    if (!left && state && state.win) left = Math.max(left, num(state.win.scrollX, 0));
    return left;
  }

  function updateScrollState(state) {
    if (!state) return null;
    var pageHeight = Math.max(1, num(state.pageHeight, 800));
    var contentHeight = Math.max(pageHeight, num(state.contentHeight, pageHeight));
    var maxScroll = Math.max(0, contentHeight - pageHeight);
    var rawScrollTop = getScrollTop(state);
    var scrollTop = Math.max(0, Math.min(maxScroll, rawScrollTop));
    state.scrollTop = scrollTop;
    state.maxScroll = maxScroll;
    state.scrollRatio = maxScroll > 0 ? (scrollTop / maxScroll) : 0;
    return {
      scrollTop: scrollTop,
      maxScroll: maxScroll,
      ratio: state.scrollRatio,
      viewportHeight: pageHeight,
      contentHeight: contentHeight,
      pageHeight: pageHeight,
      lineHeight: getLineHeight(state)
    };
  }

  function getScrollState(state) {
    if (!state) return null;
    recomputeMetrics(state);
    return updateScrollState(state);
  }

  function getLineHeight(state) {
    var doc = state && state.doc;
    var win = state && state.win || global;
    var target = doc && (doc.body || doc.documentElement);
    var fallback = 20;
    if (!target || !win.getComputedStyle) return fallback;
    try {
      var cs = win.getComputedStyle(target);
      var lh = parseFloat(cs.lineHeight);
      if (isFinite(lh) && lh > 0) return Math.max(8, lh);
      var fs = parseFloat(cs.fontSize);
      if (isFinite(fs) && fs > 0) return Math.max(8, fs * 1.25);
    } catch (_e) {}
    return fallback;
  }

  function emitScroll(state) {
    var info = updateScrollState(state);
    if (state && state.webSearchActiveRange) {
      drawSearchOverlay(state, state.webSearchActiveRange);
    }
    if (state && state.inspectorEnabled) {
      var rafWin = state.win || global;
      if (!state._selectionRaf && rafWin && typeof rafWin.requestAnimationFrame === 'function') {
        state._selectionRaf = rafWin.requestAnimationFrame(function() {
          state._selectionRaf = 0;
          notifySelection(state);
        });
      }
    }
    if (typeof state.onScroll === 'function') state.onScroll(info, state);
    return info;
  }

  function scrollToY(state, y, opts) {
    if (!state) return null;
    opts = opts || {};
    recomputeMetrics(state);
    var maxScroll = Math.max(0, num(state.maxScroll, 0));
    var next = Math.max(0, Math.min(maxScroll, num(y, 0)));
    var scrollEl = getScrollElement(state);
    if (scrollEl) {
      scrollEl.scrollTop = next;
      if (Math.abs(num(scrollEl.scrollTop, 0) - next) > 1) {
        var candidates = scrollElementCandidates(state) || [];
        for (var i = 0; i < candidates.length; i++) {
          if (candidates[i] && candidates[i] !== scrollEl) candidates[i].scrollTop = next;
        }
      }
    }
    if (Math.abs(getScrollTop(state) - next) > 1 && state.win && typeof state.win.scrollTo === 'function') {
      try {
        state.win.scrollTo({ top: next, left: 0, behavior: opts.behavior || 'auto' });
      } catch (_e) {
        try { state.win.scrollTo(0, next); } catch (_e2) {}
      }
    }
    return emitScroll(state);
  }

  function scrollBy(state, delta, opts) {
    var current = updateScrollState(state);
    return scrollToY(state, num(current && current.scrollTop, 0) + num(delta, 0), opts || {});
  }

  function scrollToRatio(state, ratio, opts) {
    recomputeMetrics(state);
    var maxScroll = Math.max(0, num(state && state.maxScroll, 0));
    var r = Math.max(0, Math.min(1, num(ratio, 0)));
    return scrollToY(state, maxScroll * r, opts || {});
  }

  function scrollToPage(state, pageIndex) {
    var idx = Math.max(0, Math.min(Math.max(0, (state.pageCount || 1) - 1), Math.floor(num(pageIndex, 0))));
    state.pageIndex = idx;
    return scrollToY(state, idx * Math.max(1, num(state.pageHeight, 800)));
  }

  function applyViewportSize(state, opts) {
    opts = opts || {};
    var pageWidth = Math.max(320, Math.floor(num(opts.pageWidth || opts.width, state.pageWidth || 640)));
    var pageHeight = Math.max(320, Math.floor(num(opts.pageHeight || opts.height, state.pageHeight || 820)));
    state.pageWidth = pageWidth;
    state.pageHeight = pageHeight;
    if (state.shell) {
      state.shell.style.width = '100%';
      state.shell.style.height = pageHeight + 'px';
    }
    if (state.iframe) {
      state.iframe.style.width = '100%';
      state.iframe.style.height = pageHeight + 'px';
    }
    if (state.flatBitmap) applyFlatBitmapScale(state);
    else if (state.doc) applyHtmlShrinkToFit(state);
  }

  function invokeReady(state, opts) {
    if (opts && typeof opts.onReady === 'function') opts.onReady(state);
  }

  function injectInspectorCss(doc) {
    if (!doc || doc.getElementById('docrender-websnapshot-inspector-style')) return;
    var style = doc.createElement('style');
    style.id = 'docrender-websnapshot-inspector-style';
    style.textContent = [
      'html.docrender-websnapshot-inspector-active,html.docrender-websnapshot-inspector-active body{cursor:text!important;}',
      'html.docrender-websnapshot-inspector-active *{user-select:text!important;-webkit-user-select:text!important;}',
      'html.docrender-websnapshot-inspector-active ::selection{background:transparent!important;color:inherit!important;text-shadow:inherit!important;}',
      'html.docrender-websnapshot-inspector-active ::-moz-selection{background:transparent!important;color:inherit!important;text-shadow:inherit!important;}',
      '.docrender-websnapshot-selection-overlay{position:fixed!important;left:0!important;top:0!important;width:100vw!important;height:100vh!important;overflow:hidden!important;pointer-events:none!important;z-index:2147483647;}',
      '.docrender-websnapshot-selection-cell{position:absolute;box-sizing:border-box;border:1px dashed rgba(30,64,175,.95);background:repeating-linear-gradient(45deg,rgba(37,99,235,.22) 0,rgba(37,99,235,.22) 4px,rgba(16,185,129,.18) 4px,rgba(16,185,129,.18) 8px);box-shadow:0 0 0 1px rgba(255,255,255,.72) inset,0 0 0 1px rgba(30,64,175,.18);border-radius:2px;}'
    ].join('\n');
    (doc.head || doc.documentElement).appendChild(style);
  }

  function injectSnapshotScrollCss(doc) {
    if (!doc || doc.getElementById('docrender-websnapshot-scroll-style')) return;
    var style = doc.createElement('style');
    style.id = 'docrender-websnapshot-scroll-style';
    style.textContent = [
      'html,body{scrollbar-width:none!important;-ms-overflow-style:none!important;overflow-x:hidden!important;}',
      '*,*::before,*::after{scrollbar-width:none!important;-ms-overflow-style:none!important;}',
      'html,body,*{user-select:none!important;-webkit-user-select:none!important;}',
      'html::-webkit-scrollbar,body::-webkit-scrollbar,*::-webkit-scrollbar{width:0!important;height:0!important;display:none!important;}'
    ].join('\n');
    (doc.head || doc.documentElement).appendChild(style);
  }

  function contentVisibilityCssText() {
    return [
      HTML_SNAPSHOT_CONTENT_VISIBILITY_SELECTOR,
      ',[' + HTML_SNAPSHOT_CONTENT_VISIBILITY_ATTR + '="1"]{',
      'content-visibility:auto!important;',
      'contain-intrinsic-size:' + HTML_SNAPSHOT_CONTENT_VISIBILITY_INTRINSIC_SIZE + '!important;',
      '}'
    ].join('');
  }

  function htmlWithContentVisibilityBootstrap(html) {
    var raw = str(html || '');
    if (!HTML_SNAPSHOT_CONTENT_VISIBILITY_ENABLED || !raw) return raw;
    if (raw.indexOf(HTML_SNAPSHOT_CONTENT_VISIBILITY_STYLE_ID) >= 0) return raw;
    var style = '<style id="' + HTML_SNAPSHOT_CONTENT_VISIBILITY_STYLE_ID + '">' +
      contentVisibilityCssText() +
      '</style>';
    if (/<\/head\s*>/i.test(raw)) {
      return raw.replace(/<\/head\s*>/i, style + '\n</head>');
    }
    if (/<body\b/i.test(raw)) {
      return raw.replace(/<body\b/i, style + '\n<body');
    }
    return style + '\n' + raw;
  }

  function injectContentVisibilityCss(doc) {
    if (!HTML_SNAPSHOT_CONTENT_VISIBILITY_ENABLED) return;
    if (!doc || doc.getElementById(HTML_SNAPSHOT_CONTENT_VISIBILITY_STYLE_ID)) return;
    var style = doc.createElement('style');
    style.id = HTML_SNAPSHOT_CONTENT_VISIBILITY_STYLE_ID;
    style.textContent = contentVisibilityCssText();
    (doc.head || doc.documentElement).appendChild(style);
  }

  function isContentVisibilityExcludedElement(el, win) {
    if (!el || el.nodeType !== 1) return true;
    var tag = str(el.tagName).toLowerCase();
    if (!tag || /^(html|head|body|script|style|link|meta|title|template|svg|canvas|iframe|video|audio|picture|img)$/.test(tag)) return true;
    if (/^(header|nav|footer|aside|form|table|thead|tbody|tfoot|tr|td|th)$/.test(tag)) return true;
    if (el.id === HTML_SCALE_SHELL_ID || el.id === HTML_SCALE_ROOT_ID) return true;
    if (el.id === 'docrender-websnapshot-selection-overlay') return true;
    if (el.closest && el.closest('#docrender-websnapshot-selection-overlay,[data-le-static-control]')) return true;
    var cs = null;
    try { cs = win && win.getComputedStyle ? win.getComputedStyle(el) : null; } catch (_e) {}
    if (!cs) return true;
    var display = str(cs.display);
    if (!display || display === 'none' || display === 'contents' || /^inline/.test(display) || /^table/.test(display)) return true;
    var position = str(cs.position);
    if (/^(fixed|sticky|absolute)$/.test(position)) return true;
    var overflow = [cs.overflow, cs.overflowX, cs.overflowY].join(' ');
    if (/(auto|scroll|overlay)/i.test(overflow)) return true;
    return false;
  }

  function isContentVisibilityCandidate(el, win) {
    if (isContentVisibilityExcludedElement(el, win)) return false;
    var textLen = str(el.textContent).replace(/\s+/g, '').length;
    var childCount = el.children ? el.children.length : 0;
    if (textLen < 120 && childCount < 2) return false;
    var rect = null;
    try { rect = el.getBoundingClientRect(); } catch (_e) {}
    var h = num(rect && rect.height, 0) || num(el.scrollHeight, 0) || num(el.offsetHeight, 0);
    if (h < HTML_SNAPSHOT_CONTENT_VISIBILITY_MIN_HEIGHT && textLen < 450) return false;
    return true;
  }

  function applyContentVisibilityHints(state) {
    if (!HTML_SNAPSHOT_CONTENT_VISIBILITY_ENABLED) return;
    var doc = state && state.doc;
    var win = state && state.win;
    if (!doc || !doc.body || !win || state.flatBitmap) return;
    injectContentVisibilityCss(doc);
    var nodes = [];
    try {
      nodes = Array.from(doc.querySelectorAll(HTML_SNAPSHOT_CONTENT_VISIBILITY_SELECTOR));
    } catch (_e) {
      nodes = [];
    }
    var marked = 0;
    for (var i = 0; i < nodes.length && marked < HTML_SNAPSHOT_CONTENT_VISIBILITY_MAX_BLOCKS; i++) {
      var el = nodes[i];
      if (!isContentVisibilityCandidate(el, win)) continue;
      if (el.parentElement && el.parentElement.getAttribute &&
          el.parentElement.getAttribute(HTML_SNAPSHOT_CONTENT_VISIBILITY_ATTR) === '1') {
        continue;
      }
      el.setAttribute(HTML_SNAPSHOT_CONTENT_VISIBILITY_ATTR, '1');
      marked += 1;
    }
    state.contentVisibilityBlockCount = marked;
  }

  function stripNativeTitleTooltips(doc) {
    if (!doc || !doc.querySelectorAll) return;
    try {
      Array.from(doc.querySelectorAll('[title]')).forEach(function(el) {
        el.removeAttribute('title');
      });
    } catch (_e) {}
  }

  function flattenInternalScrollContainers(state) {
    var doc = state && state.doc;
    var win = state && state.win;
    if (!doc || !win || !doc.body || state.flatBitmap) return;
    var nodes = doc.body.querySelectorAll ? Array.from(doc.body.querySelectorAll('*')) : [];
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!el || el.id === 'docrender-websnapshot-selection-overlay') continue;
      var cs = null;
      try { cs = win.getComputedStyle(el); } catch (_e) {}
      if (!cs) continue;
      var overflowY = str(cs.overflowY || cs.overflow);
      if (!/(auto|scroll|overlay)/i.test(overflowY)) continue;
      var scrollH = num(el.scrollHeight, 0);
      var clientH = num(el.clientHeight, 0);
      if (scrollH <= clientH + 3 || clientH < 24) continue;
      try {
        el.scrollTop = 0;
        el.style.overflowY = 'visible';
        el.style.maxHeight = 'none';
        el.style.minHeight = Math.ceil(scrollH) + 'px';
        el.style.height = Math.ceil(scrollH) + 'px';
        el.setAttribute('data-docrender-flattened-scroll', '1');
      } catch (_e2) {}
    }
  }

  function ensureSelectionOverlay(state) {
    var doc = state && state.doc;
    if (!doc || !doc.body) return null;
    var overlay = doc.getElementById('docrender-websnapshot-selection-overlay');
    if (!overlay) {
      overlay = doc.createElement('div');
      overlay.id = 'docrender-websnapshot-selection-overlay';
      overlay.className = 'docrender-websnapshot-selection-overlay';
      doc.body.appendChild(overlay);
    }
    return overlay;
  }

  function clearSelectionOverlay(state) {
    var overlay = state && state.doc && state.doc.getElementById('docrender-websnapshot-selection-overlay');
    if (overlay) overlay.innerHTML = '';
  }

  function getSelectedText(state) {
    if (!state || !state.win || typeof state.win.getSelection !== 'function') return '';
    var sel = state.win.getSelection();
    return sel ? str(sel.toString()) : '';
  }

  function selectionRects(state) {
    var out = [];
    if (!state || !state.win || typeof state.win.getSelection !== 'function') return out;
    var sel = state.win.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return out;
    var scrollLeft = getScrollLeft(state);
    var scrollTop = getScrollTop(state);
    for (var i = 0; i < sel.rangeCount; i++) {
      var range = sel.getRangeAt(i);
      var rects = range && range.getClientRects ? Array.from(range.getClientRects()) : [];
      for (var ri = 0; ri < rects.length; ri++) {
        var r = rects[ri];
        if (!r || r.width <= 0.5 || r.height <= 0.5) continue;
        out.push({
          left: Number(r.left || 0),
          top: Number(r.top || 0),
          width: Number(r.width || 0),
          height: Number(r.height || 0),
          pageLeft: Number(r.left || 0) + scrollLeft,
          pageTop: Number(r.top || 0) + scrollTop
        });
      }
    }
    return out;
  }

  function applyFlatBitmapScale(state) {
    if (!state || !state.doc || !state.textLayer) return;
    var doc = state.doc;
    var metrics = state.textLayer.metrics || {};
    var sourceWidth = Math.max(1, num(metrics.documentWidth, 0));
    var sourceHeight = Math.max(1, num(metrics.documentHeight, 0));
    var viewportWidth = Math.max(1, num(state.pageWidth, 0) || num(state.iframe && state.iframe.clientWidth, 0) || sourceWidth);
    var scale = Math.min(1, viewportWidth / sourceWidth);
    var scaledWidth = Math.ceil(sourceWidth * scale);
    var scaledHeight = Math.ceil(sourceHeight * scale);
    state.bitmapScale = scale;
    state.scaledDocumentHeight = scaledHeight;
    state.scaledDocumentWidth = scaledWidth;

    var root = doc.getElementById('le-web-snapshot-root');
    var html = doc.documentElement;
    var body = doc.body;
    if (html) {
      html.style.width = scaledWidth + 'px';
      html.style.minWidth = scaledWidth + 'px';
      html.style.height = scaledHeight + 'px';
      html.style.minHeight = scaledHeight + 'px';
      html.style.overflowX = 'hidden';
      html.style.overflowY = 'auto';
      html.style.scrollbarWidth = 'none';
    }
    if (body) {
      body.style.width = scaledWidth + 'px';
      body.style.minWidth = scaledWidth + 'px';
      body.style.height = scaledHeight + 'px';
      body.style.minHeight = scaledHeight + 'px';
      body.style.overflowX = 'hidden';
      body.style.overflowY = 'auto';
      body.style.scrollbarWidth = 'none';
      body.style.margin = '0';
    }
    if (root) {
      root.style.transformOrigin = '0 0';
      root.style.transform = 'scale(' + scale + ')';
      root.style.width = sourceWidth + 'px';
      root.style.height = sourceHeight + 'px';
    }
    if (!doc.getElementById('docrender-flat-scrollbar-hide')) {
      var style = doc.createElement('style');
      style.id = 'docrender-flat-scrollbar-hide';
      style.textContent = 'html::-webkit-scrollbar,body::-webkit-scrollbar{width:0!important;height:0!important}html,body{scrollbar-width:none!important;overflow-x:hidden!important}';
      (doc.head || doc.documentElement).appendChild(style);
    }
  }

  var HTML_SCALE_SHELL_ID = 'docrender-html-scale-shell';
  var HTML_SCALE_ROOT_ID = 'docrender-html-scale-root';

  function resetElementStyle(el, css) {
    if (!el) return;
    el.style.cssText = css || '';
  }

  function ensureHtmlScaleRoot(state) {
    var doc = state && state.doc;
    if (!doc || !doc.body || state.flatBitmap) return null;
    var shell = doc.getElementById(HTML_SCALE_SHELL_ID);
    var root = doc.getElementById(HTML_SCALE_ROOT_ID);
    if (shell && root && shell.parentNode === doc.body) return { shell: shell, root: root };

    shell = doc.createElement('div');
    shell.id = HTML_SCALE_SHELL_ID;
    root = doc.createElement('div');
    root.id = HTML_SCALE_ROOT_ID;

    while (doc.body.firstChild) {
      root.appendChild(doc.body.firstChild);
    }
    shell.appendChild(root);
    doc.body.appendChild(shell);
    return { shell: shell, root: root };
  }

  function measureHtmlScaleSource(state, shell, root) {
    var doc = state && state.doc;
    var docEl = doc && doc.documentElement;
    var body = doc && doc.body;
    var viewportWidth = Math.max(1, num(state.iframe && state.iframe.clientWidth, 0) || num(state.pageWidth, 640));

    resetElementStyle(shell, 'display:block;position:relative;left:auto;top:auto;width:auto;min-width:0;height:auto;min-height:0;margin:0;padding:0;border:0;overflow:visible;');
    resetElementStyle(root, 'display:block;position:relative;left:auto;top:auto;width:auto;min-width:0;height:auto;min-height:0;margin:0;padding:0;border:0;overflow:visible;transform:none;transform-origin:0 0;');

    // Force one layout pass before reading scroll/offset sizes.
    try { root.getBoundingClientRect(); } catch (_e) {}

    var sourceWidth = Math.max(
      viewportWidth,
      num(root.scrollWidth, 0),
      num(root.offsetWidth, 0),
      num(shell.scrollWidth, 0),
      num(body && body.scrollWidth, 0),
      num(docEl && docEl.scrollWidth, 0),
      num(body && body.offsetWidth, 0),
      num(docEl && docEl.offsetWidth, 0)
    );
    var sourceHeight = Math.max(
      Math.max(1, num(state.pageHeight, 800)),
      num(root.scrollHeight, 0),
      num(root.offsetHeight, 0),
      num(shell.scrollHeight, 0),
      num(body && body.scrollHeight, 0),
      num(docEl && docEl.scrollHeight, 0),
      num(body && body.offsetHeight, 0),
      num(docEl && docEl.offsetHeight, 0)
    );

    return { width: Math.ceil(sourceWidth), height: Math.ceil(sourceHeight), viewportWidth: viewportWidth };
  }

  function applyHtmlShrinkToFit(state) {
    if (!state || !state.doc || !state.iframe || state.flatBitmap) return null;
    var doc = state.doc;
    var body = doc.body;
    var docEl = doc.documentElement;
    if (!body || !docEl) return null;

    var pair = ensureHtmlScaleRoot(state);
    if (!pair) return null;
    var shell = pair.shell;
    var root = pair.root;
    var measured = measureHtmlScaleSource(state, shell, root);
    var viewportWidth = Math.max(1, measured.viewportWidth || num(state.iframe.clientWidth, 0) || num(state.pageWidth, 640));
    var sourceWidth = Math.max(1, measured.width || viewportWidth);
    var sourceHeight = Math.max(1, measured.height || num(state.pageHeight, 800));
    var scale = Math.min(1, viewportWidth / sourceWidth);
    var scaledHeight = Math.max(1, Math.ceil(sourceHeight * scale));

    state.htmlScale = scale;
    state.htmlScaleSourceWidth = sourceWidth;
    state.htmlScaleSourceHeight = sourceHeight;
    state.htmlScaledHeight = scaledHeight;

    try {
      docEl.style.width = viewportWidth + 'px';
      docEl.style.minWidth = viewportWidth + 'px';
      docEl.style.maxWidth = viewportWidth + 'px';
      docEl.style.overflowX = 'hidden';
      docEl.style.overflowY = 'auto';
      body.style.width = viewportWidth + 'px';
      body.style.minWidth = viewportWidth + 'px';
      body.style.maxWidth = viewportWidth + 'px';
      body.style.height = scaledHeight + 'px';
      body.style.minHeight = scaledHeight + 'px';
      body.style.overflowX = 'hidden';
      body.style.overflowY = 'auto';
      body.style.margin = '0';
      shell.style.display = 'block';
      shell.style.position = 'relative';
      shell.style.left = '0';
      shell.style.top = '0';
      shell.style.width = viewportWidth + 'px';
      shell.style.minWidth = viewportWidth + 'px';
      shell.style.height = scaledHeight + 'px';
      shell.style.minHeight = scaledHeight + 'px';
      shell.style.margin = '0';
      shell.style.padding = '0';
      shell.style.border = '0';
      shell.style.overflow = 'visible';
      root.style.display = 'block';
      root.style.position = 'absolute';
      root.style.left = '0';
      root.style.top = '0';
      root.style.width = sourceWidth + 'px';
      root.style.minWidth = sourceWidth + 'px';
      root.style.height = sourceHeight + 'px';
      root.style.minHeight = sourceHeight + 'px';
      root.style.margin = '0';
      root.style.padding = '0';
      root.style.border = '0';
      root.style.overflow = 'visible';
      root.style.transformOrigin = '0 0';
      root.style.transform = 'scale(' + scale + ')';
      root.setAttribute('data-docrender-html-scale', String(scale));
      root.setAttribute('data-docrender-source-width', String(sourceWidth));
      root.setAttribute('data-docrender-source-height', String(sourceHeight));
    } catch (_e) {}
    return { scale: scale, sourceWidth: sourceWidth, sourceHeight: sourceHeight, scaledHeight: scaledHeight };
  }

  var DOM_TEXT_IGNORE_SELECTOR = 'script,style,noscript,template,svg,canvas,iframe,object,embed,input,textarea,select,option,button,[hidden],[aria-hidden="true"],#docrender-websnapshot-selection-overlay,#docrender-websnapshot-search-overlay';
  var MAX_WEB_SNAPSHOT_SEARCH_RESULTS = 200;

  function nodeFilterConst(win, key, fallback) {
    return win && win.NodeFilter && win.NodeFilter[key] || fallback;
  }

  function makeRange(doc, node, start, end) {
    var range = doc.createRange();
    range.setStart(node, Math.max(0, start));
    range.setEnd(node, Math.max(start, end));
    return range;
  }

  function injectSearchCss(doc) {
    if (!doc || doc.getElementById('docrender-websnapshot-search-style')) return;
    var style = doc.createElement('style');
    style.id = 'docrender-websnapshot-search-style';
    style.textContent = [
      '.docrender-websnapshot-search-overlay{position:fixed!important;left:0!important;top:0!important;width:100vw!important;height:100vh!important;overflow:hidden!important;pointer-events:none!important;z-index:2147483646;}',
      '.docrender-websnapshot-search-cell{position:absolute;box-sizing:border-box;border:1px solid rgba(180,83,9,.85);background:rgba(250,204,21,.34);box-shadow:0 0 0 1px rgba(255,255,255,.55) inset;border-radius:2px;}'
    ].join('\n');
    (doc.head || doc.documentElement).appendChild(style);
  }

  function ensureSearchOverlay(state) {
    var doc = state && state.doc;
    if (!doc || !doc.body) return null;
    injectSearchCss(doc);
    var overlay = doc.getElementById('docrender-websnapshot-search-overlay');
    if (!overlay) {
      overlay = doc.createElement('div');
      overlay.id = 'docrender-websnapshot-search-overlay';
      overlay.className = 'docrender-websnapshot-search-overlay';
      doc.body.appendChild(overlay);
    }
    return overlay;
  }

  function clearSearchOverlay(state) {
    var overlay = state && state.doc && state.doc.getElementById('docrender-websnapshot-search-overlay');
    if (overlay) overlay.innerHTML = '';
    if (state) state.webSearchActiveRange = null;
  }

  function drawSearchOverlay(state, range) {
    var overlay = ensureSearchOverlay(state);
    if (!overlay || !range || !range.getClientRects) return;
    overlay.innerHTML = '';
    var rects = Array.from(range.getClientRects ? range.getClientRects() : []);
    for (var i = 0; i < rects.length; i++) {
      var r = rects[i];
      if (!r || r.width <= 0.5 || r.height <= 0.5) continue;
      var cell = state.doc.createElement('div');
      cell.className = 'docrender-websnapshot-search-cell';
      cell.style.left = Number(r.left || 0).toFixed(2) + 'px';
      cell.style.top = Number(r.top || 0).toFixed(2) + 'px';
      cell.style.width = Math.max(1, Number(r.width || 0)).toFixed(2) + 'px';
      cell.style.height = Math.max(1, Number(r.height || 0)).toFixed(2) + 'px';
      overlay.appendChild(cell);
    }
  }

  function rectToObj(rect) {
    return {
      left: Number(rect.left || 0),
      top: Number(rect.top || 0),
      right: Number(rect.right || 0),
      bottom: Number(rect.bottom || 0),
      width: Number(rect.width || 0),
      height: Number(rect.height || 0)
    };
  }

  function rectIntersectsViewport(rect, viewport) {
    if (!rect || rect.width <= 0.25 || rect.height <= 0.25) return false;
    return rect.bottom >= viewport.top && rect.top <= viewport.bottom &&
      rect.right >= viewport.left && rect.left <= viewport.right;
  }

  function rectFullyInsideViewport(rect, viewport) {
    if (!rect || rect.width <= 0.25 || rect.height <= 0.25) return false;
    var eps = 0.75;
    return rect.top >= viewport.top - eps &&
      rect.bottom <= viewport.bottom + eps &&
      rect.left >= viewport.left - eps &&
      rect.right <= viewport.right + eps;
  }

  function normalizeViewportClip(rawClip) {
    if (!rawClip || typeof rawClip !== 'object') return null;
    var left = num(rawClip.left, 0);
    var top = num(rawClip.top, 0);
    var right = rawClip.right != null ? num(rawClip.right, left) : left + num(rawClip.width, 0);
    var bottom = rawClip.bottom != null ? num(rawClip.bottom, top) : top + num(rawClip.height, 0);
    var width = Math.max(0, right - left);
    var height = Math.max(0, bottom - top);
    if (width <= 1 || height <= 1) return null;
    return {
      left: left,
      top: top,
      right: right,
      bottom: bottom,
      width: width,
      height: height
    };
  }

  function resolveVisibleViewport(state, opts) {
    opts = opts || {};
    var explicit = normalizeViewportClip(opts.viewportClip || opts.clipRect || state.viewportClip || state.clipRect);
    if (explicit) {
      explicit.scrollLeft = getScrollLeft(state) + explicit.left;
      explicit.scrollTop = getScrollTop(state) + explicit.top;
      explicit.clipLeft = explicit.left;
      explicit.clipTop = explicit.top;
      return explicit;
    }
    var viewportWidth = Math.max(1, num(state.iframe && state.iframe.clientWidth, 0) || num(state.pageWidth, 640));
    var viewportHeight = Math.max(1, num(state.iframe && state.iframe.clientHeight, 0) || num(state.pageHeight, 800));
    return {
      left: 0,
      top: 0,
      right: viewportWidth,
      bottom: viewportHeight,
      width: viewportWidth,
      height: viewportHeight,
      scrollLeft: getScrollLeft(state),
      scrollTop: getScrollTop(state),
      clipLeft: 0,
      clipTop: 0
    };
  }

  function rectToViewportLocal(rect, viewport) {
    var left = num(rect && rect.left, 0) - num(viewport && viewport.left, 0);
    var top = num(rect && rect.top, 0) - num(viewport && viewport.top, 0);
    var width = Math.max(0, num(rect && rect.width, 0));
    var height = Math.max(0, num(rect && rect.height, 0));
    return {
      left: left,
      top: top,
      right: left + width,
      bottom: top + height,
      width: width,
      height: height
    };
  }

  function rectsShareLine(a, b) {
    if (!a || !b) return false;
    var ac = (num(a.top, 0) + num(a.bottom, num(a.top, 0))) / 2;
    var bc = (num(b.top, 0) + num(b.bottom, num(b.top, 0))) / 2;
    var ah = Math.max(1, num(a.height, 0));
    var bh = Math.max(1, num(b.height, 0));
    return Math.abs(ac - bc) <= Math.max(2, Math.min(ah, bh) * 0.45);
  }

  function unionRects(rects) {
    var left = Infinity;
    var top = Infinity;
    var right = -Infinity;
    var bottom = -Infinity;
    for (var i = 0; i < rects.length; i++) {
      var r = rects[i];
      if (!r || r.width <= 0.25 || r.height <= 0.25) continue;
      left = Math.min(left, r.left);
      top = Math.min(top, r.top);
      right = Math.max(right, r.right);
      bottom = Math.max(bottom, r.bottom);
    }
    if (!isFinite(left) || !isFinite(top) || !isFinite(right) || !isFinite(bottom)) return null;
    return { left: left, top: top, right: right, bottom: bottom, width: right - left, height: bottom - top };
  }

  function nodePath(node, doc) {
    var parts = [];
    var cur = node;
    while (cur && cur !== doc) {
      var parent = cur.parentNode;
      if (!parent) break;
      var kids = parent.childNodes || [];
      var idx = 0;
      for (; idx < kids.length; idx++) {
        if (kids[idx] === cur) break;
      }
      parts.push(idx);
      cur = parent;
    }
    return parts.reverse();
  }

  function lowerTag(el) {
    return str(el && el.tagName).toLowerCase();
  }

  function cleanClassName(value, limit) {
    return str(value).replace(/\s+/g, ' ').trim().slice(0, limit || 160);
  }

  function elementTypeIndex(el) {
    if (!el || !el.parentElement) return 1;
    var tag = lowerTag(el);
    var idx = 1;
    var cur = el.previousElementSibling;
    while (cur) {
      if (lowerTag(cur) === tag) idx += 1;
      cur = cur.previousElementSibling;
    }
    return idx;
  }

  function firstUsefulClasses(value, maxCount) {
    return cleanClassName(value, 160)
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, maxCount || 2);
  }

  function semanticKindForElement(el) {
    var tag = lowerTag(el);
    if (!tag) return '';
    if (/^h[1-6]$/.test(tag)) return 'heading';
    if (tag === 'p') return 'paragraph';
    if (tag === 'li') return 'list-item';
    if (tag === 'figcaption') return 'caption';
    if (tag === 'figure') return 'figure';
    if (tag === 'td' || tag === 'th') return 'table-cell';
    if (/^(table|thead|tbody|tfoot|tr)$/.test(tag)) return 'table';
    if (tag === 'blockquote') return 'quote';
    if (tag === 'pre') return 'pre';
    if (/^(article|section|main)$/.test(tag)) return 'section';
    if (/^(aside|nav|header|footer)$/.test(tag)) return tag;
    if (tag === 'div') return 'division';
    return tag;
  }

  function elementStructureDescriptor(el, doc) {
    var tag = lowerTag(el);
    if (!tag) return null;
    var id = str(el && el.id).slice(0, 80);
    var classList = firstUsefulClasses(el && el.className, 2);
    var role = str(el && el.getAttribute && el.getAttribute('role')).slice(0, 80);
    var index = elementTypeIndex(el);
    var key = tag;
    if (id) key += '#' + id;
    else {
      if (classList.length) key += '.' + classList.join('.');
      key += ':nth(' + index + ')';
    }
    if (role) key += '[role=' + role + ']';
    return {
      tag: tag,
      id: id,
      className: cleanClassName(el && el.className, 160),
      role: role,
      index: index,
      key: key,
      path: nodePath(el, doc).join('.'),
      semanticKind: semanticKindForElement(el)
    };
  }

  function isMeaningfulStructureElement(el) {
    return /^(article|section|main|aside|nav|header|footer|figure|figcaption|table|thead|tbody|tfoot|tr|td|th|ul|ol|li|blockquote|pre|p|div|h[1-6])$/.test(lowerTag(el));
  }

  function isBlockStructureElement(el) {
    return /^(p|li|figcaption|td|th|blockquote|pre|h[1-6])$/.test(lowerTag(el));
  }

  function isContainerStructureElement(el) {
    return /^(article|section|main|aside|nav|header|footer|figure|table|ul|ol|div)$/.test(lowerTag(el));
  }

  function elementAncestry(parent, doc) {
    var chain = [];
    var divPath = [];
    var nearestBlock = null;
    var nearestContainer = null;
    var cur = parent;
    while (cur && cur.nodeType === 1 && cur !== doc.documentElement) {
      if (isMeaningfulStructureElement(cur)) {
        var descriptor = elementStructureDescriptor(cur, doc);
        if (descriptor) {
          chain.push(descriptor);
          if (!nearestBlock && isBlockStructureElement(cur)) nearestBlock = descriptor;
          if (!nearestContainer && isContainerStructureElement(cur)) nearestContainer = descriptor;
          if (/^(div|article|section|main|aside|nav|figure|table)$/.test(descriptor.tag)) {
            divPath.push(descriptor.key);
          }
        }
      }
      cur = cur.parentElement;
    }
    chain.reverse();
    divPath.reverse();
    if (chain.length > 16) chain = chain.slice(chain.length - 16);
    if (divPath.length > 12) divPath = divPath.slice(divPath.length - 12);
    return {
      domAncestorChain: chain,
      domDivPath: divPath,
      domDivPathKey: divPath.join('>'),
      domParentPath: parent ? nodePath(parent, doc).join('.') : '',
      domParentKey: parent ? (elementStructureDescriptor(parent, doc) || {}).key || '' : '',
      domBlockKey: nearestBlock ? nearestBlock.key : '',
      domBlockPath: nearestBlock ? nearestBlock.path : '',
      domContainerKey: nearestContainer ? nearestContainer.key : '',
      domContainerPath: nearestContainer ? nearestContainer.path : '',
      domSemanticKind: nearestBlock ? nearestBlock.semanticKind : (nearestContainer ? nearestContainer.semanticKind : '')
    };
  }

  function graphemeBoundaries(text) {
    text = str(text);
    if (global.Intl && global.Intl.Segmenter) {
      try {
        var seg = new global.Intl.Segmenter(undefined, { granularity: 'grapheme' });
        var out = [];
        var iter = seg.segment(text);
        for (var item of iter) out.push({ start: item.index, end: item.index + item.segment.length, text: item.segment });
        return out;
      } catch (_e) {}
    }
    var fallback = [];
    var i = 0;
    Array.from(text).forEach(function(ch) {
      var start = i;
      i += ch.length;
      fallback.push({ start: start, end: i, text: ch });
    });
    return fallback;
  }

  function readRectTextStyle(win, el) {
    var cs = null;
    try { cs = win && win.getComputedStyle && el ? win.getComputedStyle(el) : null; } catch (_e) {}
    var style = cs ? {
      fontFamily: cs.fontFamily,
      fontSize: cs.fontSize,
      fontWeight: cs.fontWeight,
      fontStyle: cs.fontStyle,
      color: cs.color,
      textDecoration: cs.textDecorationLine || cs.textDecoration,
      lineHeight: cs.lineHeight,
      letterSpacing: cs.letterSpacing,
      wordSpacing: cs.wordSpacing,
      direction: cs.direction,
      writingMode: cs.writingMode,
      verticalAlign: cs.verticalAlign,
      whiteSpace: cs.whiteSpace
    } : {};
    if (global.CanonicalStyle && typeof global.CanonicalStyle.normalizeTextStyle === 'function') {
      return global.CanonicalStyle.normalizeTextStyle(style);
    }
    return style;
  }

  function activeRectGeometryScale(state) {
    var scale = state && state.flatBitmap ? state.bitmapScale : state && state.htmlScale;
    scale = num(scale, 1);
    return isFinite(scale) && scale > 0 ? scale : 1;
  }

  function scaleCssPx(value, scale) {
    value = str(value).trim();
    if (!value || !isFinite(scale) || scale <= 0 || Math.abs(scale - 1) < 0.0001) return value;
    var match = value.match(/^(-?\d+(?:\.\d+)?)px$/i);
    if (!match) return value;
    var scaled = Number(match[1]) * scale;
    if (!isFinite(scaled)) return value;
    return (Math.round(scaled * 1000) / 1000) + 'px';
  }

  function scaleRectTextStyleForGeometry(state, style) {
    var scale = activeRectGeometryScale(state);
    if (!style || Math.abs(scale - 1) < 0.0001) return style || {};
    var out = Object.assign({}, style);
    out.fontSize = scaleCssPx(out.fontSize, scale);
    out.lineHeight = scaleCssPx(out.lineHeight, scale);
    out.letterSpacing = scaleCssPx(out.letterSpacing, scale);
    out.wordSpacing = scaleCssPx(out.wordSpacing, scale);
    return out;
  }

  function textNodeIsVisible(node, win, doc) {
    if (!node || node.nodeType !== 3 || !str(node.nodeValue)) return false;
    if (!str(node.nodeValue).trim()) {
      var whitespaceRects = getWholeTextRects(doc, node);
      if (!whitespaceRects.some(function(r) { return r && r.width > 0.1 && r.height > 0.1; })) return false;
    }
    var parent = node.parentElement;
    if (!parent || (parent.closest && parent.closest(DOM_TEXT_IGNORE_SELECTOR))) return false;
    var el = parent;
    while (el && el.nodeType === 1 && el !== doc.documentElement) {
      var cs = null;
      try { cs = win.getComputedStyle(el); } catch (_e) {}
      if (!cs || cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse') return false;
      if (Number(cs.opacity) === 0) return false;
      el = el.parentElement;
    }
    return true;
  }

  function getWholeTextRects(doc, node) {
    var text = str(node && node.nodeValue);
    if (!text.length) return [];
    var range = null;
    try {
      range = makeRange(doc, node, 0, text.length);
      return Array.from(range.getClientRects ? range.getClientRects() : []).map(rectToObj);
    } catch (_e) {
      return [];
    } finally {
      try { if (range && range.detach) range.detach(); } catch (_e2) {}
    }
  }

  function getRangeRects(doc, node, start, end) {
    var range = null;
    try {
      range = makeRange(doc, node, start, end);
      return Array.from(range.getClientRects ? range.getClientRects() : []).map(rectToObj);
    } catch (_e) {
      return [];
    } finally {
      try { if (range && range.detach) range.detach(); } catch (_e2) {}
    }
  }

  function lineFragmentsForTextNode(state, node, viewport) {
    var doc = state.doc;
    var win = state.win;
    var text = str(node && node.nodeValue).replace(/\u00a0/g, ' ');
    if (!text.trim()) return [];

    var wholeRects = getWholeTextRects(doc, node);
    if (!wholeRects.some(function(r) { return rectIntersectsViewport(r, viewport); })) return [];

    var clusters = graphemeBoundaries(text);
    var lines = [];
    for (var i = 0; i < clusters.length; i++) {
      var g = clusters[i];
      if (!g || !g.text) continue;
      var rects = getRangeRects(doc, node, g.start, g.end).filter(function(r) {
        return rectFullyInsideViewport(r, viewport);
      });
      if (!rects.length) continue;
      for (var ri = 0; ri < rects.length; ri++) {
        var rect = rects[ri];
        var line = null;
        for (var li = 0; li < lines.length; li++) {
          if (rectsShareLine(lines[li].lineRect, rect)) {
            line = lines[li];
            break;
          }
        }
        if (!line) {
          line = { lineRect: rect, charRects: [], start: g.start, end: g.end };
          lines.push(line);
        }
        line.start = Math.min(line.start, g.start);
        line.end = Math.max(line.end, g.end);
        line.charRects.push(rect);
        line.lineRect = unionRects([line.lineRect, rect]) || rect;
      }
    }
    if (!lines.length) return [];

    lines.sort(function(a, b) {
      return num(a.lineRect.top, 0) - num(b.lineRect.top, 0) || num(a.lineRect.left, 0) - num(b.lineRect.left, 0);
    });

    var parent = node.parentElement;
    var path = nodePath(node, doc);
    var style = scaleRectTextStyleForGeometry(state, readRectTextStyle(win, parent));
    var ancestry = elementAncestry(parent, doc);
    var out = [];
    for (var l = 0; l < lines.length; l++) {
      var lineInfo = lines[l];
      var lineText = text.slice(lineInfo.start, lineInfo.end);
      if (!lineText.trim()) continue;
      var lineRects = getRangeRects(doc, node, lineInfo.start, lineInfo.end).filter(function(r) {
        return rectFullyInsideViewport(r, viewport) && rectsShareLine(r, lineInfo.lineRect);
      });
      var rect = unionRects(lineRects.length ? lineRects : lineInfo.charRects);
      if (!rect) continue;
      var viewportRect = rectToViewportLocal(rect, viewport);
      out.push({
        id: 'web-rect-frag-' + path.join('-') + '-' + lineInfo.start + '-' + lineInfo.end + '-' + l,
        text: lineText,
        nodeStart: lineInfo.start,
        nodeEnd: lineInfo.end,
        nodePath: path,
        parentTag: str(parent && parent.tagName).toLowerCase(),
        parentId: str(parent && parent.id).slice(0, 80),
        parentClass: str(parent && parent.className).replace(/\s+/g, ' ').trim().slice(0, 160),
        domAncestorChain: ancestry.domAncestorChain,
        domDivPath: ancestry.domDivPath,
        domDivPathKey: ancestry.domDivPathKey,
        domParentPath: ancestry.domParentPath,
        domParentKey: ancestry.domParentKey,
        domBlockKey: ancestry.domBlockKey,
        domBlockPath: ancestry.domBlockPath,
        domContainerKey: ancestry.domContainerKey,
        domContainerPath: ancestry.domContainerPath,
        domSemanticKind: ancestry.domSemanticKind,
        rect: viewportRect,
        documentRect: rect,
        style: style
      });
    }
    return out;
  }

  function wordLikeSegmentRanges(text) {
    text = str(text).replace(/\u00a0/g, ' ');
    var ranges = [];
    if (!text) return ranges;
    if (global.Intl && global.Intl.Segmenter) {
      try {
        var segmenter = new global.Intl.Segmenter(undefined, { granularity: 'word' });
        var iter = segmenter.segment(text);
        for (var item of iter) {
          var value = str(item && item.segment);
          if (!value) continue;
          ranges.push({
            start: item.index,
            end: item.index + value.length,
            text: value,
            whitespace: /^\s+$/.test(value)
          });
        }
        if (ranges.length) return ranges;
      } catch (_e) {}
    }
    var re = /\s+|\S+/g;
    var match;
    while ((match = re.exec(text))) {
      ranges.push({
        start: match.index,
        end: match.index + match[0].length,
        text: match[0],
        whitespace: /^\s+$/.test(match[0])
      });
    }
    return ranges;
  }

  function rangeLineSlicesForTextNode(state, node, start, end, viewport) {
    var doc = state.doc;
    var text = str(node && node.nodeValue).replace(/\u00a0/g, ' ');
    start = Math.max(0, Math.min(text.length, Math.floor(num(start, 0))));
    end = Math.max(start, Math.min(text.length, Math.floor(num(end, start))));
    if (end <= start) return [];

    var clusters = graphemeBoundaries(text.slice(start, end));
    var lines = [];
    for (var i = 0; i < clusters.length; i++) {
      var g = clusters[i];
      if (!g || !g.text) continue;
      var gs = start + g.start;
      var ge = start + g.end;
      var rects = getRangeRects(doc, node, gs, ge).filter(function(r) {
        return rectFullyInsideViewport(r, viewport);
      });
      if (!rects.length) continue;
      for (var ri = 0; ri < rects.length; ri++) {
        var rect = rects[ri];
        var line = null;
        for (var li = 0; li < lines.length; li++) {
          if (rectsShareLine(lines[li].lineRect, rect)) {
            line = lines[li];
            break;
          }
        }
        if (!line) {
          line = { lineRect: rect, charRects: [], start: gs, end: ge };
          lines.push(line);
        }
        line.start = Math.min(line.start, gs);
        line.end = Math.max(line.end, ge);
        line.charRects.push(rect);
        line.lineRect = unionRects([line.lineRect, rect]) || rect;
      }
    }
    lines.sort(function(a, b) {
      return num(a.lineRect.top, 0) - num(b.lineRect.top, 0) || num(a.lineRect.left, 0) - num(b.lineRect.left, 0);
    });
    var out = [];
    for (var l = 0; l < lines.length; l++) {
      var info = lines[l];
      var lineRects = getRangeRects(doc, node, info.start, info.end).filter(function(r) {
        return rectFullyInsideViewport(r, viewport) && rectsShareLine(r, info.lineRect);
      });
      var rect = unionRects(lineRects.length ? lineRects : info.charRects);
      if (!rect) continue;
      out.push({ start: info.start, end: info.end, rect: rect });
    }
    return out;
  }

  function textFragmentsForTextNode(state, node, viewport) {
    var doc = state.doc;
    var win = state.win;
    var text = str(node && node.nodeValue).replace(/\u00a0/g, ' ');
    if (!text) return [];

    var wholeRects = getWholeTextRects(doc, node);
    if (!wholeRects.some(function(r) { return rectIntersectsViewport(r, viewport); })) return [];

    var parent = node.parentElement;
    var path = nodePath(node, doc);
    var style = readRectTextStyle(win, parent);
    var ancestry = elementAncestry(parent, doc);
    var ranges = wordLikeSegmentRanges(text);
    var out = [];
    for (var i = 0; i < ranges.length; i++) {
      var range = ranges[i];
      if (!range || range.end <= range.start) continue;
      if (range.whitespace) {
        out.push({
          id: 'web-rect-space-' + path.join('-') + '-' + range.start + '-' + range.end,
          text: range.text,
          nodeStart: range.start,
          nodeEnd: range.end,
          nodePath: path,
          hidden: true,
          sourceKind: 'webSnapshotWhitespace',
          parentTag: str(parent && parent.tagName).toLowerCase(),
          parentId: str(parent && parent.id).slice(0, 80),
          parentClass: str(parent && parent.className).replace(/\s+/g, ' ').trim().slice(0, 160),
          domAncestorChain: ancestry.domAncestorChain,
          domDivPath: ancestry.domDivPath,
          domDivPathKey: ancestry.domDivPathKey,
          domParentPath: ancestry.domParentPath,
          domParentKey: ancestry.domParentKey,
          domBlockKey: ancestry.domBlockKey,
          domBlockPath: ancestry.domBlockPath,
          domContainerKey: ancestry.domContainerKey,
          domContainerPath: ancestry.domContainerPath,
          domSemanticKind: ancestry.domSemanticKind,
          rect: { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 },
          documentRect: { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 },
          style: style
        });
        continue;
      }

      var slices = rangeLineSlicesForTextNode(state, node, range.start, range.end, viewport);
      for (var si = 0; si < slices.length; si++) {
        var slice = slices[si];
        var sliceText = text.slice(slice.start, slice.end);
        if (!sliceText) continue;
        var viewportRect = rectToViewportLocal(slice.rect, viewport);
        out.push({
          id: 'web-rect-word-' + path.join('-') + '-' + slice.start + '-' + slice.end + '-' + si,
          text: sliceText,
          nodeStart: slice.start,
          nodeEnd: slice.end,
          nodePath: path,
          parentTag: str(parent && parent.tagName).toLowerCase(),
          parentId: str(parent && parent.id).slice(0, 80),
          parentClass: str(parent && parent.className).replace(/\s+/g, ' ').trim().slice(0, 160),
          domAncestorChain: ancestry.domAncestorChain,
          domDivPath: ancestry.domDivPath,
          domDivPathKey: ancestry.domDivPathKey,
          domParentPath: ancestry.domParentPath,
          domParentKey: ancestry.domParentKey,
          domBlockKey: ancestry.domBlockKey,
          domBlockPath: ancestry.domBlockPath,
          domContainerKey: ancestry.domContainerKey,
          domContainerPath: ancestry.domContainerPath,
          domSemanticKind: ancestry.domSemanticKind,
          rect: viewportRect,
          documentRect: slice.rect,
          style: style,
          sourceKind: 'webSnapshotWordRect'
        });
      }
    }
    return out;
  }

  function medianNumber(values) {
    var nums = (values || []).filter(function(v) {
      return isFinite(Number(v)) && Number(v) > 0;
    }).map(function(v) { return Number(v); }).sort(function(a, b) { return a - b; });
    if (!nums.length) return 0;
    var mid = Math.floor(nums.length / 2);
    return nums.length % 2 ? nums[mid] : ((nums[mid - 1] + nums[mid]) / 2);
  }

  function fragmentLineAdvance(prev, curr) {
    var a = prev && prev.rect;
    var b = curr && curr.rect;
    if (!a || !b || rectsShareLine(a, b)) return 0;
    var ac = (num(a.top, 0) + num(a.bottom, num(a.top, 0))) / 2;
    var bc = (num(b.top, 0) + num(b.bottom, num(b.top, 0))) / 2;
    var advance = bc - ac;
    var minHeight = Math.max(1, Math.min(num(a.height, 0) || 1, num(b.height, 0) || 1));
    return advance > Math.max(2, minHeight * 0.35) ? advance : 0;
  }

  function annotateFragmentSeparators(fragments, opts) {
    opts = opts || {};
    if (!fragments || !fragments.length) {
      return { medianLineAdvance: 0, paragraphBreaks: 0, paragraphGapFactor: 1.5 };
    }

    var advances = [];
    var byIndex = [];
    for (var i = 1; i < fragments.length; i++) {
      var advance = fragmentLineAdvance(fragments[i - 1], fragments[i]);
      byIndex[i] = advance;
      if (advance > 0) advances.push(advance);
    }

    var medianAdvance = medianNumber(advances);
    var factor = num(opts.paragraphGapFactor, 1.5);
    if (!isFinite(factor) || factor < 1) factor = 1.5;
    var minExtraPx = Math.max(2, num(opts.paragraphGapMinExtraPx, 2));
    var threshold = medianAdvance > 0 ? medianAdvance * factor : Infinity;
    var paragraphBreaks = 0;

    fragments[0].separatorBefore = '';
    fragments[0].separatorKind = 'none';
    fragments[0].lineAdvanceFromPrevious = 0;
    fragments[0].medianLineAdvance = medianAdvance;

    for (var fi = 1; fi < fragments.length; fi++) {
      var gap = byIndex[fi] || 0;
      fragments[fi].separatorBefore = '';
      fragments[fi].separatorKind = 'visual-wrap';
      fragments[fi].lineAdvanceFromPrevious = gap;
      fragments[fi].medianLineAdvance = medianAdvance;
    }

    return {
      medianLineAdvance: medianAdvance,
      paragraphBreaks: paragraphBreaks,
      paragraphGapFactor: factor,
      paragraphGapThreshold: isFinite(threshold) ? threshold : 0
    };
  }

  function collectVisibleRectFragments(state, opts) {
    opts = opts || {};
    var doc = state && state.doc;
    var win = state && state.win;
    if (!doc || !win || !doc.body) return null;
    var viewport = resolveVisibleViewport(state, opts);

    var walker = doc.createTreeWalker(doc.body, nodeFilterConst(win, 'SHOW_TEXT', 4), {
      acceptNode: function(node) {
        return textNodeIsVisible(node, win, doc)
          ? nodeFilterConst(win, 'FILTER_ACCEPT', 1)
          : nodeFilterConst(win, 'FILTER_REJECT', 2);
      }
    });

    var fragments = [];
    var node;
    while ((node = walker.nextNode())) {
      var nodeFragments = textFragmentsForTextNode(state, node, viewport);
      for (var i = 0; i < nodeFragments.length; i++) fragments.push(nodeFragments[i]);
    }

    fragments.sort(function(a, b) {
      var ap = (a.nodePath || []).join('.');
      var bp = (b.nodePath || []).join('.');
      return ap.localeCompare(bp, undefined, { numeric: true }) ||
        num(a.nodeStart, 0) - num(b.nodeStart, 0) ||
        num(a.rect && a.rect.top, 0) - num(b.rect && b.rect.top, 0) ||
        num(a.rect && a.rect.left, 0) - num(b.rect && b.rect.left, 0);
    });

    var separatorStats = annotateFragmentSeparators(fragments, opts);
    var text = '';
    for (var fi = 0; fi < fragments.length; fi++) {
      if (fi > 0) {
        var hasSeparator = Object.prototype.hasOwnProperty.call(fragments[fi], 'separatorBefore');
        var sep = hasSeparator ? str(fragments[fi].separatorBefore) : '\n';
        fragments[fi].separatorStart = text.length;
        if (sep) text += sep;
        fragments[fi].separatorEnd = text.length;
      }
      fragments[fi].lookupStart = text.length;
      text += fragments[fi].text;
      fragments[fi].lookupEnd = text.length;
    }

    return { viewport: viewport, fragments: fragments, text: text, separatorStats: separatorStats };
  }

  function percentRect(rect, viewport) {
    var w = Math.max(1, num(viewport && viewport.width, 1));
    var h = Math.max(1, num(viewport && viewport.height, 1));
    return {
      x: num(rect && rect.left, 0) / w,
      y: num(rect && rect.top, 0) / h,
      width: num(rect && rect.width, 0) / w,
      height: num(rect && rect.height, 0) / h
    };
  }

  function makeRectRun(fragment) {
    var rect = fragment.rect || {};
    if (fragment.hidden) {
      return {
        id: fragment.id,
        text: fragment.text,
        start: fragment.lookupStart,
        end: fragment.lookupEnd,
        style: {},
        layout: {
          mode: 'fixed',
          x: -99999,
          y: -99999,
          width: 0,
          height: 0,
          skipFitWidth: true
        },
        rects: [],
        source: {
          kind: fragment.sourceKind || 'webSnapshotWhitespace',
          synthetic: true,
          hidden: true,
          nodePath: fragment.nodePath,
          nodeStart: fragment.nodeStart,
          nodeEnd: fragment.nodeEnd,
          parentTag: fragment.parentTag,
          parentId: fragment.parentId,
          parentClass: fragment.parentClass,
          domAncestorChain: fragment.domAncestorChain || [],
          domDivPath: fragment.domDivPath || [],
          domDivPathKey: fragment.domDivPathKey || '',
          domParentPath: fragment.domParentPath || '',
          domParentKey: fragment.domParentKey || '',
          domBlockKey: fragment.domBlockKey || '',
          domBlockPath: fragment.domBlockPath || '',
          domContainerKey: fragment.domContainerKey || '',
          domContainerPath: fragment.domContainerPath || '',
          domSemanticKind: fragment.domSemanticKind || ''
        }
      };
    }
    return {
      id: fragment.id,
      text: fragment.text,
      start: fragment.lookupStart,
      end: fragment.lookupEnd,
      style: fragment.style || {},
      layout: {
        mode: 'fixed',
        x: num(rect.left, 0),
        y: num(rect.top, 0),
        width: Math.max(1, num(rect.width, 1)),
        height: Math.max(1, num(rect.height, 1))
      },
      rects: [{
        x: num(rect.left, 0),
        y: num(rect.top, 0),
        width: Math.max(1, num(rect.width, 1)),
        height: Math.max(1, num(rect.height, 1))
      }],
      source: {
        kind: 'webSnapshotRectSlice',
        exactWordRectRun: fragment.sourceKind === 'webSnapshotWordRect',
        nodePath: fragment.nodePath,
        nodeStart: fragment.nodeStart,
        nodeEnd: fragment.nodeEnd,
        parentTag: fragment.parentTag,
        parentId: fragment.parentId,
        parentClass: fragment.parentClass,
        domAncestorChain: fragment.domAncestorChain || [],
        domDivPath: fragment.domDivPath || [],
        domDivPathKey: fragment.domDivPathKey || '',
        domParentPath: fragment.domParentPath || '',
        domParentKey: fragment.domParentKey || '',
        domBlockKey: fragment.domBlockKey || '',
        domBlockPath: fragment.domBlockPath || '',
        domContainerKey: fragment.domContainerKey || '',
        domContainerPath: fragment.domContainerPath || '',
        domSemanticKind: fragment.domSemanticKind || '',
        viewportRect: rect,
        documentRect: fragment.documentRect || rect,
        percentRect: percentRect(rect, fragment.viewport)
      }
    };
  }

  function makeSeparatorRun(index, start, text, kind) {
    var sepText = text == null ? '\n' : str(text);
    if (!sepText) return null;
    return {
      id: 'web-rect-sep-' + index,
      text: sepText,
      start: start,
      end: start + sepText.length,
      style: {},
      layout: { mode: 'fixed', x: 0, y: 0, width: 0, height: 0 },
      rects: [],
      source: { kind: 'separator', separatorKind: kind || 'line', synthetic: true }
    };
  }

  function isVisibleWebRectRun(run) {
    return !!(run &&
      run.layout &&
      run.layout.mode === 'fixed' &&
      !(run.source && run.source.synthetic) &&
      String(run.source && run.source.kind || '') === 'webSnapshotRectSlice' &&
      str(run.text).trim());
  }

  function webRunBox(run) {
    var layout = run && run.layout || {};
    var x = num(layout.x, 0);
    var y = num(layout.y, 0);
    var width = Math.max(0, num(layout.width, 0));
    var height = Math.max(1, num(layout.height, 1));
    return {
      x: x,
      y: y,
      width: width,
      height: height,
      right: x + width,
      bottom: y + height,
      cy: y + height / 2
    };
  }

  function webRunsShareLine(a, b, opts) {
    if (!a || !b) return false;
    var factor = num(opts && opts.lineToleranceFactor, 0.55) || 0.55;
    return Math.abs(num(a.cy, 0) - num(b.cy, 0)) <= Math.max(2, Math.min(num(a.height, 0), num(b.height, 0)) * factor);
  }

  function webRunDomAncestrySignature(source) {
    var chain = Array.isArray(source && source.domAncestorChain) ? source.domAncestorChain : [];
    return chain.map(function(item) {
      return str(item && (item.path || item.key));
    }).filter(Boolean).join('>');
  }

  function webRunsShareAvailableDomAncestry(a, b) {
    var left = a && a.run && a.run.source || {};
    var right = b && b.run && b.run.source || {};
    var keys = ['domBlockPath', 'domContainerPath', 'domDivPathKey'];
    for (var i = 0; i < keys.length; i++) {
      var lv = str(left[keys[i]]);
      var rv = str(right[keys[i]]);
      if (lv && rv && lv !== rv) return false;
    }
    var leftSig = webRunDomAncestrySignature(left);
    var rightSig = webRunDomAncestrySignature(right);
    if (leftSig && rightSig && leftSig !== rightSig) return false;
    return true;
  }

  function medianRunGap(values) {
    var nums = (values || []).filter(function(v) {
      return isFinite(Number(v));
    }).map(function(v) {
      return Number(v);
    }).sort(function(a, b) {
      return a - b;
    });
    if (!nums.length) return 0;
    return nums[Math.floor(nums.length / 2)];
  }

  function webBoundaryNeedsSpace(prevText, nextText, gap, opts) {
    var insertGap = num(opts && opts.insertSpaceGapPx, 1.25);
    if (gap < insertGap) return false;
    if (/\s$/.test(str(prevText)) || /^\s/.test(str(nextText))) return false;
    if (/^[\u060C,.\u061B;:!?\]\)]/.test(str(nextText))) return false;
    if (/[\[\(]$/.test(str(prevText))) return false;
    return true;
  }

  function unionWebRunBoxes(items) {
    var left = Infinity;
    var top = Infinity;
    var right = -Infinity;
    var bottom = -Infinity;
    for (var i = 0; i < items.length; i++) {
      var box = items[i] && items[i].box;
      if (!box) continue;
      left = Math.min(left, box.x);
      top = Math.min(top, box.y);
      right = Math.max(right, box.right);
      bottom = Math.max(bottom, box.bottom);
    }
    if (!isFinite(left) || !isFinite(top) || !isFinite(right) || !isFinite(bottom)) return null;
    return {
      x: left,
      y: top,
      width: Math.max(1, right - left),
      height: Math.max(1, bottom - top)
    };
  }

  function cloneWebRunSource(source) {
    return Object.assign({}, source || {});
  }

  function mergeWebRectRunCluster(cluster, opts) {
    if (!cluster || cluster.length < 2) return cluster && cluster[0] ? cluster[0].run : null;
    var logical = cluster.slice().sort(function(a, b) {
      return num(a.order, 0) - num(b.order, 0);
    });
    var union = unionWebRunBoxes(logical);
    if (!union) return logical[0].run;

    var text = '';
    var rects = [];
    var mergedFrom = [];
    var styleSegments = [];
    for (var i = 0; i < logical.length; i++) {
      var item = logical[i];
      var run = item.run;
      if (i > 0) {
        var prev = logical[i - 1];
        var gap = Math.max(0, Math.max(item.box.x - prev.box.right, prev.box.x - item.box.right));
        if (webBoundaryNeedsSpace(text, run.text, gap, opts)) text += ' ';
      }
      var runText = str(run.text);
      var pieceStart = text.length;
      text += runText;
      var pieceEnd = text.length;
      if (pieceEnd > pieceStart) {
        styleSegments.push({
          start: pieceStart,
          end: pieceEnd,
          style: Object.assign({}, run.style || {})
        });
      }
      if (Array.isArray(run.rects)) {
        for (var ri = 0; ri < run.rects.length; ri++) rects.push(Object.assign({}, run.rects[ri]));
      }
      mergedFrom.push({
        id: run.id || '',
        start: run.start,
        end: run.end,
        localStart: pieceStart,
        localEnd: pieceEnd,
        textLength: runText.length,
        style: Object.assign({}, run.style || {}),
        source: cloneWebRunSource(run.source)
      });
    }

    var first = logical[0].run;
    var source = cloneWebRunSource(first.source);
    source.merged = true;
    source.mergedRunCount = logical.length;
    source.mergedFrom = mergedFrom;
    source.styleSegments = styleSegments.map(function(seg) {
      return {
        start: seg.start,
        end: seg.end,
        style: Object.assign({}, seg.style || {})
      };
    });
    source.viewportRect = {
      left: union.x,
      top: union.y,
      right: union.x + union.width,
      bottom: union.y + union.height,
      width: union.width,
      height: union.height
    };

    return {
      id: 'web-rect-merged-' + logical.map(function(item) {
        return item.run.id || item.order;
      }).join('--'),
      text: text,
      start: first.start,
      end: first.start + text.length,
      style: {},
      styleSegments: styleSegments,
      layout: {
        mode: 'fixed',
        x: union.x,
        y: union.y,
        width: union.width,
        height: union.height
      },
      rects: rects.length ? rects : [{
        x: union.x,
        y: union.y,
        width: union.width,
        height: union.height
      }],
      source: source
    };
  }

  function buildWebRectRunClusters(visible, opts) {
    var lines = [];
    visible.sort(function(a, b) {
      return num(a.box.y, 0) - num(b.box.y, 0) || num(a.box.x, 0) - num(b.box.x, 0);
    });
    for (var i = 0; i < visible.length; i++) {
      var item = visible[i];
      var line = null;
      for (var li = 0; li < lines.length; li++) {
        if (webRunsShareLine(lines[li].anchor.box, item.box, opts)) {
          line = lines[li];
          break;
        }
      }
      if (!line) {
        line = { anchor: item, items: [] };
        lines.push(line);
      }
      line.items.push(item);
    }

    var pageWordGap = num(opts && opts.wordGapPx, 0);
    if (!isFinite(pageWordGap) || pageWordGap <= 0) {
      pageWordGap = num(opts && opts.fallbackWordGapPx, 6) || 6;
    }
    var wordGapMultiplier = num(opts && opts.wordGapMultiplier, 1.5);
    if (!isFinite(wordGapMultiplier) || wordGapMultiplier <= 0) wordGapMultiplier = 1.5;
    var threshold = pageWordGap * wordGapMultiplier;
    if (opts) {
      opts.wordGapPx = pageWordGap;
      opts.wordGapMultiplier = wordGapMultiplier;
      opts.mergeGapThresholdPx = threshold;
    }

    var clusters = [];
    for (var l = 0; l < lines.length; l++) {
      var visual = lines[l].items.slice().sort(function(a, b) {
        return num(a.box.x, 0) - num(b.box.x, 0);
      });
      if (!visual.length) continue;

      var cluster = [visual[0]];
      for (var vi = 1; vi < visual.length; vi++) {
        var gap = Math.max(0, visual[vi].box.x - visual[vi - 1].box.right);
        if (gap <= threshold &&
            webRunsShareAvailableDomAncestry(visual[vi - 1], visual[vi])) {
          cluster.push(visual[vi]);
        } else {
          clusters.push(cluster);
          cluster = [visual[vi]];
        }
      }
      clusters.push(cluster);
    }
    return clusters;
  }

  function recomputeRunOffsets(runs) {
    var text = '';
    for (var i = 0; i < runs.length; i++) {
      runs[i].start = text.length;
      text += str(runs[i].text);
      runs[i].end = text.length;
    }
    return text;
  }

  function wordRangesForText(text) {
    var out = [];
    var re = /\S+/g;
    var value = str(text);
    var match;
    while ((match = re.exec(value))) {
      out.push({ start: match.index, end: match.index + match[0].length, text: match[0] });
    }
    return out;
  }

  function collectVisibleWordBoxes(state, viewport) {
    var doc = state && state.doc;
    var win = state && state.win;
    if (!doc || !win || !doc.body || !viewport) return [];
    var walker = doc.createTreeWalker(doc.body, nodeFilterConst(win, 'SHOW_TEXT', 4), {
      acceptNode: function(node) {
        return textNodeIsVisible(node, win, doc)
          ? nodeFilterConst(win, 'FILTER_ACCEPT', 1)
          : nodeFilterConst(win, 'FILTER_REJECT', 2);
      }
    });
    var words = [];
    var node;
    while ((node = walker.nextNode())) {
      var text = str(node && node.nodeValue).replace(/\u00a0/g, ' ');
      var ranges = wordRangesForText(text);
      for (var i = 0; i < ranges.length; i++) {
        var range = ranges[i];
        var rects = getRangeRects(doc, node, range.start, range.end).filter(function(r) {
          return rectFullyInsideViewport(r, viewport);
        });
        for (var ri = 0; ri < rects.length; ri++) {
          var rect = rectToViewportLocal(rects[ri], viewport);
          if (!rect || rect.width <= 0.25 || rect.height <= 0.25) continue;
          words.push({
            text: range.text,
            box: {
              x: rect.left,
              y: rect.top,
              width: rect.width,
              height: rect.height,
              right: rect.left + rect.width,
              bottom: rect.top + rect.height,
              cy: rect.top + rect.height / 2
            }
          });
        }
      }
    }
    return words;
  }

  function sameWordBoxLine(a, b, opts) {
    return webRunsShareLine(a && a.box, b && b.box, opts);
  }

  function estimateVisibleWordGap(state, viewport, opts) {
    var words = collectVisibleWordBoxes(state, viewport);
    if (words.length < 2) return 0;
    words.sort(function(a, b) {
      return num(a.box.y, 0) - num(b.box.y, 0) || num(a.box.x, 0) - num(b.box.x, 0);
    });
    var lines = [];
    for (var i = 0; i < words.length; i++) {
      var word = words[i];
      var line = null;
      for (var li = 0; li < lines.length; li++) {
        if (sameWordBoxLine(lines[li].anchor, word, opts)) {
          line = lines[li];
          break;
        }
      }
      if (!line) {
        line = { anchor: word, items: [] };
        lines.push(line);
      }
      line.items.push(word);
    }

    var gaps = [];
    for (var l = 0; l < lines.length; l++) {
      var visual = lines[l].items.slice().sort(function(a, b) {
        return num(a.box.x, 0) - num(b.box.x, 0);
      });
      for (var gi = 1; gi < visual.length; gi++) {
        var gap = Math.max(0, visual[gi].box.x - visual[gi - 1].box.right);
        if (gap > 0) gaps.push(gap);
      }
    }
    return medianRunGap(gaps);
  }

  function mergeNearbyWebRectRuns(runs, opts) {
    opts = Object.assign({
      lineToleranceFactor: 0.55,
      insertSpaceGapPx: 1.25,
      fallbackWordGapPx: 6,
      wordGapMultiplier: 1.5
    }, opts || {});

    var visible = [];
    var runToCluster = new Map();
    for (var i = 0; i < runs.length; i++) {
      if (!isVisibleWebRectRun(runs[i])) continue;
      visible.push({ run: runs[i], order: i, box: webRunBox(runs[i]) });
    }
    if (visible.length < 2) {
      return { runs: runs, text: recomputeRunOffsets(runs), mergedCount: 0, mergeGapThresholdPx: 0 };
    }

    var clusters = buildWebRectRunClusters(visible, opts);
    var mergedCount = 0;
    for (var ci = 0; ci < clusters.length; ci++) {
      if (!clusters[ci] || clusters[ci].length < 2) continue;
      var mergedRun = mergeWebRectRunCluster(clusters[ci], opts);
      if (!mergedRun) continue;
      mergedCount += clusters[ci].length - 1;
      for (var mi = 0; mi < clusters[ci].length; mi++) {
        runToCluster.set(clusters[ci][mi].run, {
          cluster: clusters[ci],
          mergedRun: mergedRun,
          firstRun: clusters[ci].slice().sort(function(a, b) {
            return num(a.order, 0) - num(b.order, 0);
          })[0].run
        });
      }
    }
    if (!mergedCount) {
      return { runs: runs, text: recomputeRunOffsets(runs), mergedCount: 0, mergeGapThresholdPx: opts.mergeGapThresholdPx || 0 };
    }

    var out = [];
    for (var ri = 0; ri < runs.length; ri++) {
      var run = runs[ri];
      var info = runToCluster.get(run);
      if (info) {
        if (run === info.firstRun) out.push(info.mergedRun);
        continue;
      }
      if (run.source && run.source.synthetic) {
        var prevInfo = ri > 0 ? runToCluster.get(runs[ri - 1]) : null;
        var nextInfo = ri + 1 < runs.length ? runToCluster.get(runs[ri + 1]) : null;
        if (prevInfo && nextInfo && prevInfo.mergedRun === nextInfo.mergedRun) continue;
      }
      out.push(run);
    }

    return {
      runs: out,
      text: recomputeRunOffsets(out),
      mergedCount: mergedCount,
      mergeGapThresholdPx: opts.mergeGapThresholdPx || 0
    };
  }

  function extractVisibleCanonicalDocument(state, opts) {
    opts = opts || {};
    var result = collectVisibleRectFragments(state, opts);
    if (!result || !result.text || !result.text.trim()) return null;
    var viewport = result.viewport;
    var runs = [];
    for (var i = 0; i < result.fragments.length; i++) {
      var fragment = result.fragments[i];
      fragment.viewport = viewport;
      if (i > 0) {
        var hasSeparator = Object.prototype.hasOwnProperty.call(fragment, 'separatorBefore');
        var sep = hasSeparator ? str(fragment.separatorBefore) : '\n';
        var sepStart = isFinite(Number(fragment.separatorStart)) ? Number(fragment.separatorStart) : (fragment.lookupStart - sep.length);
        if (sep) runs.push(makeSeparatorRun(i, sepStart, sep, fragment.separatorKind));
      }
      runs.push(makeRectRun(fragment));
    }
    var mergeOpts = Object.assign({}, opts.runMerge || opts.webSnapshotRunMerge || {});
    var measuredWordGap = estimateVisibleWordGap(state, viewport, mergeOpts);
    mergeOpts.wordGapPx = measuredWordGap || num(mergeOpts.fallbackWordGapPx, 6) || 6;
    mergeOpts.wordGapMultiplier = num(mergeOpts.wordGapMultiplier, 1.5) || 1.5;
    var merged = { runs: runs, text: recomputeRunOffsets(runs), mergedCount: 0, mergeGapThresholdPx: 0 };
    if (opts.enableRunMerge === true) {
      merged = mergeNearbyWebRectRuns(runs, mergeOpts);
      runs = merged.runs;
    }
    var pageText = merged.text;

    var block = {
      id: 'web-rect-slice-block-0',
      type: 'rect-slice',
      start: 0,
      end: pageText.length,
      style: {},
      layout: {
        mode: 'fixed',
        x: 0,
        y: 0,
        width: viewport.width,
        height: viewport.height
      },
      runs: runs,
      source: { kind: 'webSnapshotRectSlice' }
    };

    var meta = Object.assign({}, state.meta || {}, {
      format: 'Remote HTML',
      parser: 'web-rect-slice',
      visibleSlice: true,
      wordRectRuns: true,
      scrollTop: viewport.scrollTop,
      viewportHeight: viewport.height,
      viewportWidth: viewport.width,
      fragmentCount: result.fragments.length,
      mergedRunCount: merged.mergedCount || 0,
      wordGapPx: mergeOpts.wordGapPx,
      wordGapMultiplier: mergeOpts.wordGapMultiplier,
      mergeGapThresholdPx: merged.mergeGapThresholdPx || mergeOpts.mergeGapThresholdPx || 0,
      paragraphBreakCount: result.separatorStats ? result.separatorStats.paragraphBreaks : 0,
      medianLineAdvance: result.separatorStats ? result.separatorStats.medianLineAdvance : 0
    });

    var doc = {
      schemaVersion: 1,
      id: 'web-rect-doc-' + Date.now().toString(36),
      meta: meta,
      pages: [{
        id: 'web-rect-page-0',
        index: 0,
        text: pageText,
        blocks: [block],
        tokens: [],
        layout: { mode: 'fixed', width: viewport.width, height: viewport.height },
        source: {
          kind: 'webSnapshotRectSlice',
          scrollTop: viewport.scrollTop,
          scrollLeft: viewport.scrollLeft,
          viewportWidth: viewport.width,
          viewportHeight: viewport.height,
          fragmentCount: result.fragments.length,
          documentUrl: str((state.meta && (state.meta.finalUrl || state.meta.requestedUrl)) || '')
        }
      }],
      flowBlocks: [],
      source: { kind: 'webSnapshotRectSlice' }
    };
    if (global.LookupChunks &&
        typeof global.LookupChunks.applyLookupChunkParagraphBreaks === 'function') {
      global.LookupChunks.applyLookupChunkParagraphBreaks(doc.pages[0], {
        sourceKind: 'web-geometry-chunk-paragraph'
      });
      if (doc.pages[0] && doc.pages[0].source) {
        meta.trankitChunkParagraphBreakCount = doc.pages[0].source.trankitChunkParagraphBreakCount || 0;
        meta.trankitChunkParagraphChunkCount = doc.pages[0].source.trankitChunkParagraphChunkCount || 0;
      }
    }
    return doc;
  }

  function extractVisibleText(state, opts) {
    var result = collectVisibleRectFragments(state, opts || {});
    return result && result.text ? result.text.trim() : '';
  }

  function shouldSearchTextNode(node) {
    if (!node || node.nodeType !== 3) return false;
    var text = str(node.nodeValue || '');
    if (!text.trim()) return false;
    var parent = node.parentElement;
    if (!parent) return false;
    try {
      if (parent.closest && parent.closest(DOM_TEXT_IGNORE_SELECTOR)) return false;
    } catch (_e) {}
    return true;
  }

  function buildSearchTextIndex(state) {
    var doc = state && state.doc;
    var body = doc && doc.body;
    var win = state && state.win || global;
    var showText = nodeFilterConst(win, 'SHOW_TEXT', 4);
    var accept = nodeFilterConst(win, 'FILTER_ACCEPT', 1);
    var reject = nodeFilterConst(win, 'FILTER_REJECT', 2);
    var text = '';
    var segments = [];
    if (!doc || !body || !doc.createTreeWalker) return { text: '', segments: [] };
    var walker = doc.createTreeWalker(body, showText, {
      acceptNode: function(node) {
        return shouldSearchTextNode(node) ? accept : reject;
      }
    });
    var node;
    while ((node = walker.nextNode())) {
      var value = str(node.nodeValue || '');
      if (!value) continue;
      if (text) text += ' ';
      var start = text.length;
      text += value;
      segments.push({ node: node, start: start, end: start + value.length });
    }
    return { text: text, segments: segments };
  }

  function locateSearchTextPosition(segments, index) {
    if (!segments || !segments.length) return null;
    var pos = Math.max(0, Math.floor(num(index, 0)));
    for (var i = 0; i < segments.length; i++) {
      var seg = segments[i];
      if (pos < seg.start) {
        return { node: seg.node, offset: 0 };
      }
      if (pos <= seg.end) {
        return {
          node: seg.node,
          offset: Math.max(0, Math.min(seg.end - seg.start, pos - seg.start))
        };
      }
    }
    var last = segments[segments.length - 1];
    return { node: last.node, offset: Math.max(0, last.end - last.start) };
  }

  function makeSearchRange(doc, segments, start, length) {
    var startRef = locateSearchTextPosition(segments, start);
    var endRef = locateSearchTextPosition(segments, start + Math.max(1, length));
    if (!doc || !startRef || !endRef) return null;
    try {
      var range = doc.createRange();
      range.setStart(startRef.node, startRef.offset);
      range.setEnd(endRef.node, endRef.offset);
      return range;
    } catch (_e) {
      return null;
    }
  }

  function buildSearchExcerptParts(text, start, length) {
    var source = str(text || '');
    var s = Math.max(0, Math.floor(num(start, 0)));
    var len = Math.max(1, Math.floor(num(length, 1)));
    var from = Math.max(0, s - 48);
    var to = Math.min(source.length, s + len + 64);
    return {
      pre: (from > 0 ? '...' : '') + source.slice(from, s),
      match: source.slice(s, s + len),
      post: source.slice(s + len, to) + (to < source.length ? '...' : '')
    };
  }

  function serializeSearchResult(result) {
    return {
      id: result.id,
      resultIndex: result.resultIndex,
      label: result.label,
      excerpt: result.excerpt
    };
  }

  function search(state, query) {
    var q = str(query || '').trim();
    clearSearchOverlay(state);
    if (!state || !state.doc || !q) {
      if (state) {
        state.webSearchResults = [];
        state.webSearchTotal = 0;
      }
      return { total: 0, results: [] };
    }
    var index = buildSearchTextIndex(state);
    var text = index.text || '';
    var hay = text.toLocaleLowerCase();
    var needle = q.toLocaleLowerCase();
    var results = [];
    var total = 0;
    var from = 0;
    while (needle && from < hay.length) {
      var hit = hay.indexOf(needle, from);
      if (hit < 0) break;
      total += 1;
      if (results.length < MAX_WEB_SNAPSHOT_SEARCH_RESULTS) {
        var range = makeSearchRange(state.doc, index.segments, hit, q.length);
        results.push({
          id: 'web-search-' + (total - 1),
          resultIndex: total - 1,
          label: 'Match ' + total,
          excerpt: buildSearchExcerptParts(text, hit, q.length),
          range: range,
          start: hit,
          length: q.length
        });
      }
      from = hit + Math.max(1, needle.length);
    }
    state.webSearchResults = results;
    state.webSearchTotal = total;
    return {
      total: total,
      results: results.map(serializeSearchResult)
    };
  }

  function goToSearchResult(state, resultIndex, opts) {
    opts = opts || {};
    if (!state || !state.webSearchResults || !state.webSearchResults.length) return null;
    var idx = Math.max(0, Math.min(state.webSearchResults.length - 1, Math.floor(num(resultIndex, 0))));
    var result = state.webSearchResults[idx];
    var range = result && result.range;
    if (!range || !range.getClientRects) return null;
    state.webSearchActiveRange = range;
    var rects = Array.from(range.getClientRects ? range.getClientRects() : []).filter(function(r) {
      return r && r.width > 0.5 && r.height > 0.5;
    });
    var rect = rects[0] || (range.getBoundingClientRect ? range.getBoundingClientRect() : null);
    if (rect) {
      var centerY = getScrollTop(state) + num(rect.top, 0) + num(rect.height, 0) / 2;
      var targetY = centerY - Math.max(1, num(state.pageHeight, 800)) / 2;
      scrollToY(state, targetY, { behavior: opts.behavior || 'auto' });
    }
    drawSearchOverlay(state, range);
    try {
      (state.win || global).setTimeout(function() {
        drawSearchOverlay(state, range);
      }, 0);
    } catch (_e) {}
    return {
      resultIndex: idx,
      total: Math.max(num(state.webSearchTotal, 0), state.webSearchResults.length),
      result: serializeSearchResult(result)
    };
  }

  function drawSelectionOverlay(state) {
    var overlay = ensureSelectionOverlay(state);
    if (!overlay) return { text: '', rects: [] };
    overlay.innerHTML = '';
    var text = getSelectedText(state);
    var rects = selectionRects(state);
    for (var i = 0; i < rects.length; i++) {
      var r = rects[i];
      var cell = state.doc.createElement('div');
      cell.className = 'docrender-websnapshot-selection-cell';
      cell.style.left = r.left.toFixed(2) + 'px';
      cell.style.top = r.top.toFixed(2) + 'px';
      cell.style.width = Math.max(1, r.width).toFixed(2) + 'px';
      cell.style.height = Math.max(1, r.height).toFixed(2) + 'px';
      overlay.appendChild(cell);
    }
    return { text: text, rects: rects };
  }

  function notifySelection(state) {
    var info = drawSelectionOverlay(state);
    state.selectedText = info.text || '';
    state.selectedRects = info.rects || [];
    if (typeof state.onSelectionChange === 'function') state.onSelectionChange(info, state);
    return info;
  }

  function attachInspectorListeners(state) {
    if (!state || !state.doc || state._inspectorListenersAttached) return;
    var schedule = function() {
      if (state._selectionRaf) return;
      state._selectionRaf = (state.win || global).requestAnimationFrame(function() {
        state._selectionRaf = 0;
        notifySelection(state);
      });
    };
    state._selectionHandler = schedule;
    state.doc.addEventListener('selectionchange', schedule);
    state.doc.addEventListener('mouseup', schedule);
    state.doc.addEventListener('keyup', schedule);
    state._inspectorListenersAttached = true;
  }

  function detachInspectorListeners(state) {
    if (!state || !state.doc || !state._inspectorListenersAttached) return;
    var handler = state._selectionHandler;
    if (handler) {
      state.doc.removeEventListener('selectionchange', handler);
      state.doc.removeEventListener('mouseup', handler);
      state.doc.removeEventListener('keyup', handler);
    }
    state._selectionHandler = null;
    state._inspectorListenersAttached = false;
  }

  function setInspectorEnabled(state, enabled, opts) {
    if (!state || !state.iframe) return null;
    opts = opts || {};
    state.onSelectionChange = opts.onSelectionChange || state.onSelectionChange || null;
    state.inspectorEnabled = !!enabled;
    state.iframe.style.pointerEvents = state.inspectorEnabled ? 'auto' : 'none';
    if (state.shell) state.shell.classList.toggle('docrender-websnapshot-inspector-enabled', state.inspectorEnabled);
    if (!state.doc) return state;
    injectInspectorCss(state.doc);
    state.doc.documentElement.classList.toggle('docrender-websnapshot-inspector-active', state.inspectorEnabled);
    if (state.inspectorEnabled) {
      attachInspectorListeners(state);
      try { state.win.focus(); } catch (_e) {}
      notifySelection(state);
    } else {
      detachInspectorListeners(state);
      try {
        var sel = state.win && state.win.getSelection ? state.win.getSelection() : null;
        if (sel && typeof sel.removeAllRanges === 'function') sel.removeAllRanges();
      } catch (_e2) {}
      state.selectedText = '';
      state.selectedRects = [];
      clearSelectionOverlay(state);
      if (typeof state.onSelectionChange === 'function') {
        state.onSelectionChange({ text: '', rects: [] }, state);
      }
    }
    return state;
  }

  function attachScrollListener(state) {
    if (!state || state._scrollListenerAttached) return;
    state._scrollHandler = function() { emitScroll(state); };
    state._scrollTargets = [];
    pushUnique(state._scrollTargets, state.win);
    var candidates = scrollElementCandidates(state) || [];
    for (var i = 0; i < candidates.length; i++) pushUnique(state._scrollTargets, candidates[i]);
    for (var ti = 0; ti < state._scrollTargets.length; ti++) {
      var target = state._scrollTargets[ti];
      if (target && target.addEventListener) {
        target.addEventListener('scroll', state._scrollHandler, { passive: true });
      }
    }
    state._scrollListenerAttached = true;
  }

  function attachWheelGuard(state) {
    if (!state || !state.doc || state._wheelGuardAttached) return;
    state._wheelHandler = function(event) {
      if (event && event.__docrenderWheelHandled) return;
      if (event) event.__docrenderWheelHandled = true;
      var dy = num(event && event.deltaY, 0);
      if (!dy && event) dy = num(event.deltaX, 0);
      if (!dy) return;
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      if (event && typeof event.stopPropagation === 'function') event.stopPropagation();
      if (typeof state.onWheel === 'function') state.onWheel(dy, event, state);
      else scrollBy(state, dy);
    };
    state.doc.addEventListener('wheel', state._wheelHandler, { capture: true, passive: false });
    if (state.win && state.win.addEventListener) {
      state.win.addEventListener('wheel', state._wheelHandler, { capture: true, passive: false });
    }
    state._wheelGuardAttached = true;
  }

  function attachInertInteractionGuard(state) {
    if (!state || !state.doc || state._inertInteractionGuardAttached) return;
    var suppress = function(event) {
      if (!event || !event.target || !event.target.closest) return;
      var target = event.target.closest('a,button,input,select,textarea,label,summary,option,[role="button"],[role="link"],form');
      if (!target) return;
      // Do not block pointerdown/mousedown; text selection starts there.
      event.preventDefault();
      event.stopPropagation();
    };
    state._inertInteractionGuard = suppress;
    ['click','auxclick','dblclick','submit','dragstart','drop'].forEach(function(type) {
      state.doc.addEventListener(type, suppress, true);
    });
    state._inertInteractionGuardAttached = true;
  }

  function render(host, page, opts) {
    if (!host || !isSnapshotPage(page)) return null;
    opts = opts || {};
    var key = snapshotKey(page);
    var existing = host.__docrenderWebSnapshotState;
    if (existing && existing.key === key && existing.iframe && existing.iframe.parentNode) {
      existing.onSelectionChange = opts.onSelectionChange || existing.onSelectionChange || null;
      existing.onScroll = opts.onScroll || existing.onScroll || null;
      existing.onWheel = opts.onWheel || existing.onWheel || null;
      applyViewportSize(existing, opts);
      if (existing.flatBitmap) applyFlatBitmapScale(existing);
      recomputeMetrics(existing);
      if (!opts.continuousScroll) scrollToPage(existing, opts.pageIndex || 0);
      else emitScroll(existing);
      setInspectorEnabled(existing, !!opts.inspectorEnabled, opts);
      if (existing.readyDone) invokeReady(existing, opts);
      else existing.ready.then(function(state) { invokeReady(state, opts); });
      return existing;
    }

    host.__docrenderWebSnapshotState = null;
    host.innerHTML = '';
    host.classList.add('docrender-websnapshot-active');

    var shell = document.createElement('div');
    shell.className = 'reader-page-shell docrender-websnapshot-shell';
    var iframe = document.createElement('iframe');
    iframe.className = 'docrender-websnapshot-frame';
    iframe.setAttribute('title', str((page.snapshot && page.snapshot.title) || 'Web snapshot'));
    iframe.setAttribute('referrerpolicy', 'no-referrer');
    iframe.setAttribute('loading', 'eager');
    iframe.setAttribute('scrolling', 'no');
    iframe.setAttribute('sandbox', 'allow-same-origin');
    iframe.style.border = '0';
    iframe.style.display = 'block';
    iframe.style.pointerEvents = opts.inspectorEnabled ? 'auto' : 'none';
    shell.appendChild(iframe);
    host.appendChild(shell);

    var state = {
      key: key,
      page: page,
      iframe: iframe,
      shell: shell,
      win: null,
      doc: null,
      readyDone: false,
      pageIndex: Math.max(0, Math.floor(num(opts.pageIndex, 0))),
      pageWidth: Math.max(320, Math.floor(num(opts.pageWidth || opts.width, 640))),
      pageHeight: Math.max(320, Math.floor(num(opts.pageHeight || opts.height, 820))),
      contentHeight: 0,
      contentWidth: 0,
      pageCount: 1,
      inspectorEnabled: !!opts.inspectorEnabled,
      selectedText: '',
      selectedRects: [],
      onSelectionChange: opts.onSelectionChange || null,
      onScroll: opts.onScroll || null,
      onWheel: opts.onWheel || null,
      meta: Object.assign({}, page.snapshot || {})
    };
    applyViewportSize(state, opts);

    state.ready = new Promise(function(resolve, reject) {
      state._resolveReady = resolve;
      state._rejectReady = reject;
    });
    host.__docrenderWebSnapshotState = state;

    iframe.addEventListener('load', function() {
      try {
        state.win = iframe.contentWindow;
        state.doc = iframe.contentDocument || (state.win && state.win.document);
        state.flatBitmap = !!(state.doc && state.doc.documentElement && state.doc.documentElement.getAttribute('data-docrender-flat-bitmap'));
        state.textLayer = null;
        stripNativeTitleTooltips(state.doc);
        injectSnapshotScrollCss(state.doc);
        if (state.flatBitmap) applyFlatBitmapScale(state);
        waitForStableLayout(state).then(function() {
          if (state.flatBitmap) {
            applyFlatBitmapScale(state);
          } else {
            flattenInternalScrollContainers(state);
            applyHtmlShrinkToFit(state);
            applyContentVisibilityHints(state);
          }
          recomputeMetrics(state);
          attachScrollListener(state);
          attachWheelGuard(state);
          attachInertInteractionGuard(state);
          if (!opts.continuousScroll) scrollToPage(state, state.pageIndex);
          else emitScroll(state);
          setInspectorEnabled(state, state.inspectorEnabled, opts);
          state.readyDone = true;
          state._resolveReady(state);
          invokeReady(state, opts);
        }).catch(function(err) {
          state._rejectReady(err);
          if (opts && typeof opts.onError === 'function') opts.onError(err);
        });
      } catch (err) {
        state._rejectReady(err);
        if (opts && typeof opts.onError === 'function') opts.onError(err);
      }
    });
    iframe.srcdoc = htmlWithContentVisibilityBootstrap(page.html || '');
    return state;
  }

  global.DocRenderWebSnapshotRenderer = {
    isSnapshotPage: isSnapshotPage,
    render: render,
    scrollToPage: scrollToPage,
    recomputeMetrics: recomputeMetrics,
    setInspectorEnabled: setInspectorEnabled,
    getSelectedText: getSelectedText,
    extractVisibleText: extractVisibleText,
    search: search,
    goToSearchResult: goToSearchResult,
    clearSearch: clearSearchOverlay,
    extractVisibleCanonicalDocument: extractVisibleCanonicalDocument,
    drawSelectionOverlay: drawSelectionOverlay,
    clearSelectionOverlay: clearSelectionOverlay,
    getScrollState: getScrollState,
    scrollBy: scrollBy,
    scrollToY: scrollToY,
    scrollToRatio: scrollToRatio,
    getLineHeight: getLineHeight
  };
})(window);
