import { frameLifecycleState } from './frame-lifecycle.state.mjs';
import { notifySelection } from './public-api.mjs';
import { drawSearchOverlay } from './search-overlay.mjs';
import { applyFlatBitmapScale, applyHtmlShrinkToFit } from './text-extraction.mjs';
import { textExtractionState } from './text-extraction.state.mjs';
export function num(v, fallback) {
  var n = Number(v);
  return isFinite(n) ? n : fallback || 0;
}
export function str(v) {
  return v == null ? '' : String(v);
}
export function isSnapshotPage(page) {
  return !!(page && (page.kind === 'webSnapshot' || page.type === 'webSnapshot'));
}
export function snapshotKey(page) {
  var snap = (page && page.snapshot) || {};
  return (
    str(page && (page.id || page.snapshotId)) ||
    [str(snap.finalUrl || snap.requestedUrl), str(snap.title), str(page && page.html).length].join('|')
  );
}
export function nextFrame(win) {
  return new Promise(function (resolve) {
    (win && win.requestAnimationFrame
      ? win.requestAnimationFrame.bind(win)
      : frameLifecycleState.global.requestAnimationFrame)(function () {
      resolve();
    });
  });
}
export function delay(ms) {
  return new Promise(function (resolve) {
    frameLifecycleState.global.setTimeout(resolve, ms);
  });
}
export async function waitForStableLayout(state) {
  if (state && state.flatBitmap) {
    await nextFrame(state.win || frameLifecycleState.global);
    return;
  }
  var doc = state.doc;
  try {
    if (doc && doc.fonts && doc.fonts.ready) await doc.fonts.ready;
  } catch (_e) {}
  try {
    await waitForImages(doc, 900);
  } catch (_e2) {}
  await nextFrame(state.win || frameLifecycleState.global);
  await nextFrame(state.win || frameLifecycleState.global);
  await delay(180);
}
export function waitForImages(doc, maxWait) {
  var images = Array.from(doc && doc.images ? doc.images : []).filter(function (img) {
    return img && !img.complete;
  });
  if (!images.length) return Promise.resolve();
  var done = new Promise(function (resolve) {
    var remaining = images.length;
    function oneDone() {
      remaining -= 1;
      if (remaining <= 0) resolve();
    }
    images.forEach(function (img) {
      img.addEventListener('load', oneDone, {
        once: true
      });
      img.addEventListener('error', oneDone, {
        once: true
      });
    });
  });
  return Promise.race([done, delay(maxWait || 900)]);
}
export function recomputeMetrics(state) {
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
export function pushUnique(list, item) {
  if (!item) return;
  for (var i = 0; i < list.length; i++) {
    if (list[i] === item) return;
  }
  list.push(item);
}
export function scrollElementCandidates(state) {
  var doc = state && state.doc;
  if (!doc) return null;
  var out = [];
  pushUnique(out, doc.scrollingElement);
  pushUnique(out, doc.documentElement);
  pushUnique(out, doc.body);
  return out;
}
export function elementMaxScroll(el) {
  if (!el) return 0;
  return Math.max(0, num(el.scrollHeight, 0) - num(el.clientHeight, 0));
}
export function getScrollElement(state) {
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
export function getScrollTop(state) {
  var scrollEl = getScrollElement(state);
  var top = scrollEl ? num(scrollEl.scrollTop, 0) : 0;
  if (!top && state && state.win) top = Math.max(top, num(state.win.scrollY, 0));
  return top;
}
export function getScrollLeft(state) {
  var scrollEl = getScrollElement(state);
  var left = scrollEl ? num(scrollEl.scrollLeft, 0) : 0;
  if (!left && state && state.win) left = Math.max(left, num(state.win.scrollX, 0));
  return left;
}
export function updateScrollState(state) {
  if (!state) return null;
  var pageHeight = Math.max(1, num(state.pageHeight, 800));
  var contentHeight = Math.max(pageHeight, num(state.contentHeight, pageHeight));
  var maxScroll = Math.max(0, contentHeight - pageHeight);
  var rawScrollTop = getScrollTop(state);
  var scrollTop = Math.max(0, Math.min(maxScroll, rawScrollTop));
  state.scrollTop = scrollTop;
  state.maxScroll = maxScroll;
  state.scrollRatio = maxScroll > 0 ? scrollTop / maxScroll : 0;
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
export function getScrollState(state) {
  if (!state) return null;
  recomputeMetrics(state);
  return updateScrollState(state);
}
export function getLineHeight(state) {
  var doc = state && state.doc;
  var win = (state && state.win) || frameLifecycleState.global;
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
export function emitScroll(state) {
  var info = updateScrollState(state);
  if (state && state.webSearchActiveRange) {
    drawSearchOverlay(state, state.webSearchActiveRange);
  }
  if (state && state.inspectorEnabled) {
    var rafWin = state.win || frameLifecycleState.global;
    if (!state._selectionRaf && rafWin && typeof rafWin.requestAnimationFrame === 'function') {
      state._selectionRaf = rafWin.requestAnimationFrame(function () {
        state._selectionRaf = 0;
        notifySelection(state);
      });
    }
  }
  if (typeof state.onScroll === 'function') state.onScroll(info, state);
  return info;
}
export function scrollToY(state, y, opts) {
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
      state.win.scrollTo({
        top: next,
        left: 0,
        behavior: opts.behavior || 'auto'
      });
    } catch (_e) {
      try {
        state.win.scrollTo(0, next);
      } catch (_e2) {}
    }
  }
  return emitScroll(state);
}
export function scrollBy(state, delta, opts) {
  var current = updateScrollState(state);
  return scrollToY(state, num(current && current.scrollTop, 0) + num(delta, 0), opts || {});
}
export function scrollToRatio(state, ratio, opts) {
  recomputeMetrics(state);
  var maxScroll = Math.max(0, num(state && state.maxScroll, 0));
  var r = Math.max(0, Math.min(1, num(ratio, 0)));
  return scrollToY(state, maxScroll * r, opts || {});
}
export function scrollToPage(state, pageIndex) {
  var idx = Math.max(0, Math.min(Math.max(0, (state.pageCount || 1) - 1), Math.floor(num(pageIndex, 0))));
  state.pageIndex = idx;
  return scrollToY(state, idx * Math.max(1, num(state.pageHeight, 800)));
}
export function applyViewportSize(state, opts) {
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
export function invokeReady(state, opts) {
  if (opts && typeof opts.onReady === 'function') opts.onReady(state);
}
export function injectInspectorCss(doc) {
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
export function injectSnapshotScrollCss(doc) {
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
export function contentVisibilityCssText() {
  return [
    frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_SELECTOR,
    ',[' + frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_ATTR + '="1"]{',
    'content-visibility:auto!important;',
    'contain-intrinsic-size:' +
      frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_INTRINSIC_SIZE +
      '!important;',
    '}'
  ].join('');
}
export function htmlWithContentVisibilityBootstrap(html) {
  var raw = str(html || '');
  if (!frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_ENABLED || !raw) return raw;
  if (raw.indexOf(frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_STYLE_ID) >= 0) return raw;
  var style =
    '<style id="' +
    frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_STYLE_ID +
    '">' +
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
export function injectContentVisibilityCss(doc) {
  if (!frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_ENABLED) return;
  if (!doc || doc.getElementById(frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_STYLE_ID)) return;
  var style = doc.createElement('style');
  style.id = frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_STYLE_ID;
  style.textContent = contentVisibilityCssText();
  (doc.head || doc.documentElement).appendChild(style);
}
export function isContentVisibilityExcludedElement(el, win) {
  if (!el || el.nodeType !== 1) return true;
  var tag = str(el.tagName).toLowerCase();
  if (
    !tag ||
    /^(html|head|body|script|style|link|meta|title|template|svg|canvas|iframe|video|audio|picture|img)$/.test(
      tag
    )
  )
    return true;
  if (/^(header|nav|footer|aside|form|table|thead|tbody|tfoot|tr|td|th)$/.test(tag)) return true;
  if (el.id === textExtractionState.HTML_SCALE_SHELL_ID || el.id === textExtractionState.HTML_SCALE_ROOT_ID)
    return true;
  if (el.id === 'docrender-websnapshot-selection-overlay') return true;
  if (el.closest && el.closest('#docrender-websnapshot-selection-overlay,[data-le-static-control]'))
    return true;
  var cs = null;
  try {
    cs = win && win.getComputedStyle ? win.getComputedStyle(el) : null;
  } catch (_e) {}
  if (!cs) return true;
  var display = str(cs.display);
  if (
    !display ||
    display === 'none' ||
    display === 'contents' ||
    /^inline/.test(display) ||
    /^table/.test(display)
  )
    return true;
  var position = str(cs.position);
  if (/^(fixed|sticky|absolute)$/.test(position)) return true;
  var overflow = [cs.overflow, cs.overflowX, cs.overflowY].join(' ');
  if (/(auto|scroll|overlay)/i.test(overflow)) return true;
  return false;
}
export function isContentVisibilityCandidate(el, win) {
  if (isContentVisibilityExcludedElement(el, win)) return false;
  var textLen = str(el.textContent).replace(/\s+/g, '').length;
  var childCount = el.children ? el.children.length : 0;
  if (textLen < 120 && childCount < 2) return false;
  var rect = null;
  try {
    rect = el.getBoundingClientRect();
  } catch (_e) {}
  var h = num(rect && rect.height, 0) || num(el.scrollHeight, 0) || num(el.offsetHeight, 0);
  if (h < frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_MIN_HEIGHT && textLen < 450) return false;
  return true;
}
export function applyContentVisibilityHints(state) {
  if (!frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_ENABLED) return;
  var doc = state && state.doc;
  var win = state && state.win;
  if (!doc || !doc.body || !win || state.flatBitmap) return;
  injectContentVisibilityCss(doc);
  var nodes = [];
  try {
    nodes = Array.from(doc.querySelectorAll(frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_SELECTOR));
  } catch (_e) {
    nodes = [];
  }
  var marked = 0;
  for (
    var i = 0;
    i < nodes.length && marked < frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_MAX_BLOCKS;
    i++
  ) {
    var el = nodes[i];
    if (!isContentVisibilityCandidate(el, win)) continue;
    if (
      el.parentElement &&
      el.parentElement.getAttribute &&
      el.parentElement.getAttribute(frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_ATTR) === '1'
    ) {
      continue;
    }
    el.setAttribute(frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_ATTR, '1');
    marked += 1;
  }
  state.contentVisibilityBlockCount = marked;
}
export function stripNativeTitleTooltips(doc) {
  if (!doc || !doc.querySelectorAll) return;
  try {
    Array.from(doc.querySelectorAll('[title]')).forEach(function (el) {
      el.removeAttribute('title');
    });
  } catch (_e) {}
}
export function flattenInternalScrollContainers(state) {
  var doc = state && state.doc;
  var win = state && state.win;
  if (!doc || !win || !doc.body || state.flatBitmap) return;
  var nodes = doc.body.querySelectorAll ? Array.from(doc.body.querySelectorAll('*')) : [];
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    if (!el || el.id === 'docrender-websnapshot-selection-overlay') continue;
    var cs = null;
    try {
      cs = win.getComputedStyle(el);
    } catch (_e) {}
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
export function initializeFrameLifecycle() {
  frameLifecycleState.global = window;
  // Hidden performance toggle for frozen HTML snapshots. Set this to false if
  // content-visibility causes layout shifts or fidelity issues on captured pages.
  frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_ENABLED = true;
  frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_STYLE_ID =
    'docrender-websnapshot-content-visibility-style';
  frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_ATTR = 'data-le-cv-block';
  frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_INTRINSIC_SIZE = 'auto 900px';
  frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_MAX_BLOCKS = 1200;
  frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_MIN_HEIGHT = 160;
  frameLifecycleState.HTML_SNAPSHOT_CONTENT_VISIBILITY_SELECTOR = [
    'article > *',
    'main > *',
    'section',
    'body > div:not(#docrender-html-scale-shell)',
    '#docrender-html-scale-root > div'
  ].join(',');
  return true;
}
