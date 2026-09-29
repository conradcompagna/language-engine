import { getScrollLeft, getScrollTop, num, str } from './frame-lifecycle.mjs';
import { textExtractionState } from './text-extraction.state.mjs';
export function ensureSelectionOverlay(state) {
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
export function clearSelectionOverlay(state) {
  var overlay = state && state.doc && state.doc.getElementById('docrender-websnapshot-selection-overlay');
  if (overlay) overlay.innerHTML = '';
}
export function getSelectedText(state) {
  if (!state || !state.win || typeof state.win.getSelection !== 'function') return '';
  var sel = state.win.getSelection();
  return sel ? str(sel.toString()) : '';
}
export function selectionRects(state) {
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
export function applyFlatBitmapScale(state) {
  if (!state || !state.doc || !state.textLayer) return;
  var doc = state.doc;
  var metrics = state.textLayer.metrics || {};
  var sourceWidth = Math.max(1, num(metrics.documentWidth, 0));
  var sourceHeight = Math.max(1, num(metrics.documentHeight, 0));
  var viewportWidth = Math.max(
    1,
    num(state.pageWidth, 0) || num(state.iframe && state.iframe.clientWidth, 0) || sourceWidth
  );
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
    style.textContent =
      'html::-webkit-scrollbar,body::-webkit-scrollbar{width:0!important;height:0!important}html,body{scrollbar-width:none!important;overflow-x:hidden!important}';
    (doc.head || doc.documentElement).appendChild(style);
  }
}
export function resetElementStyle(el, css) {
  if (!el) return;
  el.style.cssText = css || '';
}
export function ensureHtmlScaleRoot(state) {
  var doc = state && state.doc;
  if (!doc || !doc.body || state.flatBitmap) return null;
  var shell = doc.getElementById(textExtractionState.HTML_SCALE_SHELL_ID);
  var root = doc.getElementById(textExtractionState.HTML_SCALE_ROOT_ID);
  if (shell && root && shell.parentNode === doc.body)
    return {
      shell: shell,
      root: root
    };
  shell = doc.createElement('div');
  shell.id = textExtractionState.HTML_SCALE_SHELL_ID;
  root = doc.createElement('div');
  root.id = textExtractionState.HTML_SCALE_ROOT_ID;
  while (doc.body.firstChild) {
    root.appendChild(doc.body.firstChild);
  }
  shell.appendChild(root);
  doc.body.appendChild(shell);
  return {
    shell: shell,
    root: root
  };
}
export function measureHtmlScaleSource(state, shell, root) {
  var doc = state && state.doc;
  var docEl = doc && doc.documentElement;
  var body = doc && doc.body;
  var viewportWidth = Math.max(
    1,
    num(state.iframe && state.iframe.clientWidth, 0) || num(state.pageWidth, 640)
  );
  resetElementStyle(
    shell,
    'display:block;position:relative;left:auto;top:auto;width:auto;min-width:0;height:auto;min-height:0;margin:0;padding:0;border:0;overflow:visible;'
  );
  resetElementStyle(
    root,
    'display:block;position:relative;left:auto;top:auto;width:auto;min-width:0;height:auto;min-height:0;margin:0;padding:0;border:0;overflow:visible;transform:none;transform-origin:0 0;'
  );

  // Force one layout pass before reading scroll/offset sizes.
  try {
    root.getBoundingClientRect();
  } catch (_e) {}
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
  return {
    width: Math.ceil(sourceWidth),
    height: Math.ceil(sourceHeight),
    viewportWidth: viewportWidth
  };
}
export function applyHtmlShrinkToFit(state) {
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
  var viewportWidth = Math.max(
    1,
    measured.viewportWidth || num(state.iframe.clientWidth, 0) || num(state.pageWidth, 640)
  );
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
  return {
    scale: scale,
    sourceWidth: sourceWidth,
    sourceHeight: sourceHeight,
    scaledHeight: scaledHeight
  };
}
export function nodeFilterConst(win, key, fallback) {
  return (win && win.NodeFilter && win.NodeFilter[key]) || fallback;
}
export function makeRange(doc, node, start, end) {
  var range = doc.createRange();
  range.setStart(node, Math.max(0, start));
  range.setEnd(node, Math.max(start, end));
  return range;
}
export function injectSearchCss(doc) {
  if (!doc || doc.getElementById('docrender-websnapshot-search-style')) return;
  var style = doc.createElement('style');
  style.id = 'docrender-websnapshot-search-style';
  style.textContent = [
    '.docrender-websnapshot-search-overlay{position:fixed!important;left:0!important;top:0!important;width:100vw!important;height:100vh!important;overflow:hidden!important;pointer-events:none!important;z-index:2147483646;}',
    '.docrender-websnapshot-search-cell{position:absolute;box-sizing:border-box;border:1px solid rgba(180,83,9,.85);background:rgba(250,204,21,.34);box-shadow:0 0 0 1px rgba(255,255,255,.55) inset;border-radius:2px;}'
  ].join('\n');
  (doc.head || doc.documentElement).appendChild(style);
}
export function ensureSearchOverlay(state) {
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
export function clearSearchOverlay(state) {
  var overlay = state && state.doc && state.doc.getElementById('docrender-websnapshot-search-overlay');
  if (overlay) overlay.innerHTML = '';
  if (state) state.webSearchActiveRange = null;
}
export function initializeTextExtraction() {
  textExtractionState.HTML_SCALE_SHELL_ID = 'docrender-html-scale-shell';
  textExtractionState.HTML_SCALE_ROOT_ID = 'docrender-html-scale-root';
  textExtractionState.DOM_TEXT_IGNORE_SELECTOR =
    'script,style,noscript,template,svg,canvas,iframe,object,embed,input,textarea,select,option,button,[hidden],[aria-hidden="true"],#docrender-websnapshot-selection-overlay,#docrender-websnapshot-search-overlay';
  textExtractionState.MAX_WEB_SNAPSHOT_SEARCH_RESULTS = 200;
  return true;
}
