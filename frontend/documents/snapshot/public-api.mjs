import {
  applyContentVisibilityHints,
  applyViewportSize,
  emitScroll,
  flattenInternalScrollContainers,
  getLineHeight,
  getScrollState,
  getScrollTop,
  htmlWithContentVisibilityBootstrap,
  injectInspectorCss,
  injectSnapshotScrollCss,
  invokeReady,
  isSnapshotPage,
  num,
  pushUnique,
  recomputeMetrics,
  scrollBy,
  scrollElementCandidates,
  scrollToPage,
  scrollToRatio,
  scrollToY,
  snapshotKey,
  str,
  stripNativeTitleTooltips,
  waitForStableLayout
} from './frame-lifecycle.mjs';
import { frameLifecycleState } from './frame-lifecycle.state.mjs';
import {
  extractVisibleCanonicalDocument,
  extractVisibleText,
  search,
  serializeSearchResult
} from './pagination.mjs';
import { drawSearchOverlay } from './search-overlay.mjs';
import {
  applyFlatBitmapScale,
  applyHtmlShrinkToFit,
  clearSearchOverlay,
  clearSelectionOverlay,
  ensureSelectionOverlay,
  getSelectedText,
  selectionRects
} from './text-extraction.mjs';
export function goToSearchResult(state, resultIndex, opts) {
  opts = opts || {};
  if (!state || !state.webSearchResults || !state.webSearchResults.length) return null;
  var idx = Math.max(0, Math.min(state.webSearchResults.length - 1, Math.floor(num(resultIndex, 0))));
  var result = state.webSearchResults[idx];
  var range = result && result.range;
  if (!range || !range.getClientRects) return null;
  state.webSearchActiveRange = range;
  var rects = Array.from(range.getClientRects ? range.getClientRects() : []).filter(function (r) {
    return r && r.width > 0.5 && r.height > 0.5;
  });
  var rect = rects[0] || (range.getBoundingClientRect ? range.getBoundingClientRect() : null);
  if (rect) {
    var centerY = getScrollTop(state) + num(rect.top, 0) + num(rect.height, 0) / 2;
    var targetY = centerY - Math.max(1, num(state.pageHeight, 800)) / 2;
    scrollToY(state, targetY, {
      behavior: opts.behavior || 'auto'
    });
  }
  drawSearchOverlay(state, range);
  try {
    (state.win || frameLifecycleState.global).setTimeout(function () {
      drawSearchOverlay(state, range);
    }, 0);
  } catch (_e) {}
  return {
    resultIndex: idx,
    total: Math.max(num(state.webSearchTotal, 0), state.webSearchResults.length),
    result: serializeSearchResult(result)
  };
}
export function drawSelectionOverlay(state) {
  var overlay = ensureSelectionOverlay(state);
  if (!overlay)
    return {
      text: '',
      rects: []
    };
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
  return {
    text: text,
    rects: rects
  };
}
export function notifySelection(state) {
  var info = drawSelectionOverlay(state);
  state.selectedText = info.text || '';
  state.selectedRects = info.rects || [];
  if (typeof state.onSelectionChange === 'function') state.onSelectionChange(info, state);
  return info;
}
export function attachInspectorListeners(state) {
  if (!state || !state.doc || state._inspectorListenersAttached) return;
  var schedule = function () {
    if (state._selectionRaf) return;
    state._selectionRaf = (state.win || frameLifecycleState.global).requestAnimationFrame(function () {
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
export function detachInspectorListeners(state) {
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
export function setInspectorEnabled(state, enabled, opts) {
  if (!state || !state.iframe) return null;
  opts = opts || {};
  state.onSelectionChange = opts.onSelectionChange || state.onSelectionChange || null;
  state.inspectorEnabled = !!enabled;
  state.iframe.style.pointerEvents = state.inspectorEnabled ? 'auto' : 'none';
  if (state.shell)
    state.shell.classList.toggle('docrender-websnapshot-inspector-enabled', state.inspectorEnabled);
  if (!state.doc) return state;
  injectInspectorCss(state.doc);
  state.doc.documentElement.classList.toggle(
    'docrender-websnapshot-inspector-active',
    state.inspectorEnabled
  );
  if (state.inspectorEnabled) {
    attachInspectorListeners(state);
    try {
      state.win.focus();
    } catch (_e) {}
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
      state.onSelectionChange(
        {
          text: '',
          rects: []
        },
        state
      );
    }
  }
  return state;
}
export function attachScrollListener(state) {
  if (!state || state._scrollListenerAttached) return;
  state._scrollHandler = function () {
    emitScroll(state);
  };
  state._scrollTargets = [];
  pushUnique(state._scrollTargets, state.win);
  var candidates = scrollElementCandidates(state) || [];
  for (var i = 0; i < candidates.length; i++) pushUnique(state._scrollTargets, candidates[i]);
  for (var ti = 0; ti < state._scrollTargets.length; ti++) {
    var target = state._scrollTargets[ti];
    if (target && target.addEventListener) {
      target.addEventListener('scroll', state._scrollHandler, {
        passive: true
      });
    }
  }
  state._scrollListenerAttached = true;
}
export function attachWheelGuard(state) {
  if (!state || !state.doc || state._wheelGuardAttached) return;
  state._wheelHandler = function (event) {
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
  state.doc.addEventListener('wheel', state._wheelHandler, {
    capture: true,
    passive: false
  });
  if (state.win && state.win.addEventListener) {
    state.win.addEventListener('wheel', state._wheelHandler, {
      capture: true,
      passive: false
    });
  }
  state._wheelGuardAttached = true;
}
export function attachInertInteractionGuard(state) {
  if (!state || !state.doc || state._inertInteractionGuardAttached) return;
  var suppress = function (event) {
    if (!event || !event.target || !event.target.closest) return;
    var target = event.target.closest(
      'a,button,input,select,textarea,label,summary,option,[role="button"],[role="link"],form'
    );
    if (!target) return;
    // Do not block pointerdown/mousedown; text selection starts there.
    event.preventDefault();
    event.stopPropagation();
  };
  state._inertInteractionGuard = suppress;
  ['click', 'auxclick', 'dblclick', 'submit', 'dragstart', 'drop'].forEach(function (type) {
    state.doc.addEventListener(type, suppress, true);
  });
  state._inertInteractionGuardAttached = true;
}
export function render(host, page, opts) {
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
    else
      existing.ready.then(function (state) {
        invokeReady(state, opts);
      });
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
  state.ready = new Promise(function (resolve, reject) {
    state._resolveReady = resolve;
    state._rejectReady = reject;
  });
  host.__docrenderWebSnapshotState = state;
  iframe.addEventListener('load', function () {
    try {
      state.win = iframe.contentWindow;
      state.doc = iframe.contentDocument || (state.win && state.win.document);
      state.flatBitmap = !!(
        state.doc &&
        state.doc.documentElement &&
        state.doc.documentElement.getAttribute('data-docrender-flat-bitmap')
      );
      state.textLayer = null;
      stripNativeTitleTooltips(state.doc);
      injectSnapshotScrollCss(state.doc);
      if (state.flatBitmap) applyFlatBitmapScale(state);
      waitForStableLayout(state)
        .then(function () {
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
        })
        .catch(function (err) {
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
export function initializePublicApi() {
  frameLifecycleState.global.DocRenderWebSnapshotRenderer = {
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
  return true;
}
