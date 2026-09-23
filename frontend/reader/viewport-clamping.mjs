import {
  cancelFoliateNavigatorDrag,
  commitFoliateNavigatorDrag,
  currentFoliateGlobalPageIndex,
  getCompletedFoliateTotalPages,
  navigateFoliateNavigatorPage,
  pageIndexFromNavigatorEvent,
  postPdfCommand,
  runFoliatePageHoldStep,
  setActiveDocumentPage,
  stepDocumentPage,
  webSnapshotRatioFromNavigatorEvent
} from './continuous-scroll.mjs';
import { continuousScrollState } from './continuous-scroll.state.mjs';
import { getRawMaxHeightPx, getRawMinHeightPx } from './document-import.mjs';
import {
  isDocxContinuousActive,
  isTopSourceInspectorAvailable,
  scrollDocxContinuousByLine,
  scrollDocxContinuousByViewport,
  scrollDocxContinuousToRatio,
  scrollEpubByLine,
  scrollEpubByViewport,
  scrollEpubToRatio,
  scrollWebSnapshotByLine,
  scrollWebSnapshotByViewport,
  scrollWebSnapshotToRatio,
  setWebSnapshotInspectorEnabled
} from './document-navigation.mjs';
import {
  applyFixedDocumentViewportHeight,
  clearDocumentSearch,
  goToDocumentNavItem,
  goToDocumentSearchResult,
  hasDocumentNavItems,
  hideDocumentNavMenu,
  hideDocumentSearchMenu,
  isRawContinuousActive,
  isTrankitChunkLookupAvailable,
  measureRawContinuousViewportHeight,
  renderDocumentSearchResults,
  scrollRawContinuousByLine,
  scrollRawContinuousByViewport,
  scrollRawContinuousToRatio,
  setDocumentCapabilities,
  stepDocumentSearch,
  submitDocumentPageNumberInput,
  syncDocumentCapabilityControls,
  syncTrankitChunkLookupControls,
  updateDocumentNavigatorThumb
} from './document-search.mjs';
import { debounce, postPdfPageDimsCacheToIframe } from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { requestMovementLookup, shouldUsePdfjsTextLayer, warmPdfCanonicalPage } from './document-state.mjs';
import { documentState } from './document-state.state.mjs';
import { triggerUpdate } from './fill-slices.mjs';
import {
  isActiveEpubDocument,
  isActiveFoliateFlowDocument,
  isActiveWebSnapshotDocument,
  isFlowScrollDocumentActive,
  isFoliatePagedDocumentActive,
  syncDocumentChrome
} from './foliate-viewport.mjs';
import { foliateViewportState } from './foliate-viewport.state.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { escapeHtml } from './presentation.mjs';
import { getVisibleDocxSliceText, locateDomPos } from './text-offsets.mjs';
import { viewportClampingState } from './viewport-clamping.state.mjs';
export function finishFoliateNavigatorPreviewIfIdle() {
  if (
    continuousScrollState.docNavFoliateInteractionActive ||
    continuousScrollState.docNavFoliateRenderInFlight ||
    continuousScrollState.docNavFoliateRenderTargetPage != null
  )
    return;
  if (continuousScrollState.docNavDragPreviewPageIndex != null) {
    var current = currentFoliateGlobalPageIndex();
    if (
      Math.floor(Number(current) || 0) ===
      Math.floor(Number(continuousScrollState.docNavDragPreviewPageIndex) || 0)
    ) {
      continuousScrollState.docNavDragPreviewPageIndex = null;
      syncDocumentChrome();
    }
  }
}
export function pumpFoliateNavigatorRender() {
  continuousScrollState.docNavFoliateRenderFrame = 0;
  if (
    continuousScrollState.docNavFoliateRenderInFlight ||
    continuousScrollState.docNavFoliateRenderTargetPage == null
  )
    return;
  var target = continuousScrollState.docNavFoliateRenderTargetPage;
  continuousScrollState.docNavFoliateRenderTargetPage = null;
  if (Math.floor(Number(target) || 0) === Math.floor(Number(currentFoliateGlobalPageIndex()) || 0)) {
    finishFoliateNavigatorPreviewIfIdle();
    if (continuousScrollState.docNavFoliateRenderTargetPage != null) scheduleFoliateNavigatorRenderPump();
    return;
  }
  continuousScrollState.docNavFoliateRenderInFlight = true;
  navigateFoliateNavigatorPage(target)
    .then(function () {
      requestMovementLookup();
    })
    .catch(function (err) {
      console.warn('Foliate navigator render failed:', err);
    })
    .then(function () {
      continuousScrollState.docNavFoliateRenderInFlight = false;
      if (continuousScrollState.docNavFoliateRenderTargetPage != null) scheduleFoliateNavigatorRenderPump();
      else finishFoliateNavigatorPreviewIfIdle();
    });
}
export function scheduleFoliateNavigatorRenderPump() {
  if (continuousScrollState.docNavFoliateRenderFrame || continuousScrollState.docNavFoliateRenderInFlight)
    return;
  continuousScrollState.docNavFoliateRenderFrame = requestAnimationFrame(pumpFoliateNavigatorRender);
}
export function requestFoliateNavigatorRender(index) {
  if (!isFoliatePagedDocumentActive() || !documentState.foliateFullPaginationReady) return;
  var total = getCompletedFoliateTotalPages();
  if (!total) return;
  continuousScrollState.docNavFoliateRenderTargetPage = Math.max(
    0,
    Math.min(total - 1, Math.floor(Number(index) || 0))
  );
  scheduleFoliateNavigatorRenderPump();
}
export function startFoliatePageHold(direction, pointerId) {
  var dir = Number(direction) >= 0 ? 1 : -1;
  clearDocumentPageHold();
  continuousScrollState.docNavFoliateInteractionActive = true;
  continuousScrollState.docNavHoldDirection = dir;
  continuousScrollState.docNavHoldUnit = 'page';
  continuousScrollState.docNavHoldPointerId = isFinite(pointerId) ? Number(pointerId) : null;
  continuousScrollState.docNavHoldDidRepeat = false;
  continuousScrollState.docNavDragPreviewPageIndex = null;
  runFoliatePageHoldStep();
  continuousScrollState.docNavHoldDelayTimer = setTimeout(function () {
    continuousScrollState.docNavHoldDelayTimer = 0;
    continuousScrollState.docNavHoldDidRepeat = true;
    continuousScrollState.docNavHoldRepeatTimer = setInterval(runFoliatePageHoldStep, 80);
  }, 260);
}
export function clearDocumentPageHold() {
  continuousScrollState.docNavHoldDirection = 0;
  continuousScrollState.docNavHoldUnit = 'page';
  continuousScrollState.docNavHoldPointerId = null;
  if (continuousScrollState.docNavHoldDelayTimer) {
    clearTimeout(continuousScrollState.docNavHoldDelayTimer);
    continuousScrollState.docNavHoldDelayTimer = 0;
  }
  if (continuousScrollState.docNavHoldRepeatTimer) {
    clearInterval(continuousScrollState.docNavHoldRepeatTimer);
    continuousScrollState.docNavHoldRepeatTimer = 0;
  }
}
export function startDocumentPageHold(direction, pointerId) {
  var dir = Number(direction) >= 0 ? 1 : -1;
  clearDocumentPageHold();
  continuousScrollState.docNavHoldDirection = dir;
  continuousScrollState.docNavHoldUnit = 'page';
  continuousScrollState.docNavHoldPointerId = isFinite(pointerId) ? Number(pointerId) : null;
  continuousScrollState.docNavHoldDidRepeat = false;
  stepDocumentPage(dir);
  continuousScrollState.docNavHoldDelayTimer = setTimeout(function () {
    continuousScrollState.docNavHoldDelayTimer = 0;
    continuousScrollState.docNavHoldDidRepeat = true;
    continuousScrollState.docNavHoldRepeatTimer = setInterval(function () {
      if (!continuousScrollState.docNavHoldDirection) return;
      stepDocumentPage(continuousScrollState.docNavHoldDirection);
    }, 80);
  }, 260);
}
export function runWebSnapshotScrollHoldStep() {
  if (!continuousScrollState.docNavHoldDirection) return;
  if (isRawContinuousActive()) {
    if (continuousScrollState.docNavHoldUnit === 'line')
      scrollRawContinuousByLine(continuousScrollState.docNavHoldDirection);
    else scrollRawContinuousByViewport(continuousScrollState.docNavHoldDirection);
    return;
  }
  if (isActiveEpubDocument()) {
    if (continuousScrollState.docNavHoldUnit === 'line')
      scrollEpubByLine(continuousScrollState.docNavHoldDirection);
    else scrollEpubByViewport(continuousScrollState.docNavHoldDirection);
    return;
  }
  if (isDocxContinuousActive()) {
    if (continuousScrollState.docNavHoldUnit === 'line')
      scrollDocxContinuousByLine(continuousScrollState.docNavHoldDirection);
    else scrollDocxContinuousByViewport(continuousScrollState.docNavHoldDirection);
    return;
  }
  if (continuousScrollState.docNavHoldUnit === 'line')
    scrollWebSnapshotByLine(continuousScrollState.docNavHoldDirection);
  else scrollWebSnapshotByViewport(continuousScrollState.docNavHoldDirection);
}
export function startWebSnapshotScrollHold(direction, unit, pointerId) {
  var dir = Number(direction) >= 0 ? 1 : -1;
  clearDocumentPageHold();
  continuousScrollState.docNavHoldDirection = dir;
  continuousScrollState.docNavHoldUnit = unit === 'line' ? 'line' : 'page';
  continuousScrollState.docNavHoldPointerId = isFinite(pointerId) ? Number(pointerId) : null;
  continuousScrollState.docNavHoldDidRepeat = false;
  runWebSnapshotScrollHoldStep();
  continuousScrollState.docNavHoldDelayTimer = setTimeout(function () {
    continuousScrollState.docNavHoldDelayTimer = 0;
    continuousScrollState.docNavHoldDidRepeat = true;
    continuousScrollState.docNavHoldRepeatTimer = setInterval(
      runWebSnapshotScrollHoldStep,
      continuousScrollState.docNavHoldUnit === 'line' ? 55 : 140
    );
  }, 260);
}
export function stopDocumentPageHold(pointerId) {
  var pid = isFinite(pointerId) ? Number(pointerId) : null;
  if (
    continuousScrollState.docNavHoldPointerId !== null &&
    pid !== null &&
    pid !== continuousScrollState.docNavHoldPointerId
  )
    return;
  clearDocumentPageHold();
}
export function beginDocumentNavButtonHold(ev, direction) {
  if (!ev || ev.button !== 0) return;
  ev.preventDefault();
  if (isFoliatePagedDocumentActive()) startFoliatePageHold(direction, ev.pointerId);
  else if (isFlowScrollDocumentActive()) startWebSnapshotScrollHold(direction, 'line', ev.pointerId);
  else startDocumentPageHold(direction, ev.pointerId);
  var target = ev.currentTarget;
  if (target && typeof target.setPointerCapture === 'function') {
    try {
      target.setPointerCapture(ev.pointerId);
    } catch (_e) {}
  }
}
export function endDocumentNavButtonHold(ev) {
  var target = ev && ev.currentTarget;
  if (target && typeof target.releasePointerCapture === 'function') {
    try {
      target.releasePointerCapture(ev.pointerId);
    } catch (_e2) {}
  }
  var shouldCommitFoliateHold =
    isFoliatePagedDocumentActive() && continuousScrollState.docNavDragPreviewPageIndex != null;
  stopDocumentPageHold(ev && ev.pointerId);
  if (shouldCommitFoliateHold) commitFoliateNavigatorDrag();
}
export function cancelDocumentNavButtonHold(ev) {
  var target = ev && ev.currentTarget;
  if (target && typeof target.releasePointerCapture === 'function') {
    try {
      target.releasePointerCapture(ev.pointerId);
    } catch (_cancelReleaseErr) {}
  }
  var shouldCancelFoliateHold =
    isFoliatePagedDocumentActive() && continuousScrollState.docNavDragPreviewPageIndex != null;
  stopDocumentPageHold(ev && ev.pointerId);
  if (shouldCancelFoliateHold) cancelFoliateNavigatorDrag();
}
export function snapToLine() {
  if (!hoverLayoutState.sourcePager || !documentState.docText || documentState.inputMode !== 'doc') return;
  var textEl = hoverLayoutState.sourcePager.querySelector('.reader-doc-text');
  if (!textEl) return false;
  var textNode = null;
  for (var i = 0; i < textEl.childNodes.length; i++) {
    if (textEl.childNodes[i].nodeType === Node.TEXT_NODE && textEl.childNodes[i].textContent.length > 0) {
      textNode = textEl.childNodes[i];
      break;
    }
  }
  if (!textNode) return false;
  var textLength = textNode.textContent.length;
  if (textLength === 0) return false;
  var containerRect = hoverLayoutState.sourcePager.getBoundingClientRect();
  var viewTop = containerRect.top;
  var viewBottom = containerRect.bottom;
  function getCharRect(index) {
    var range = document.createRange();
    var safeIndex = Math.max(0, Math.min(index, textLength - 1));
    range.setStart(textNode, safeIndex);
    range.setEnd(textNode, Math.min(safeIndex + 1, textLength));
    var rects = range.getClientRects();
    if (rects && rects.length) return rects[0];
    return range.getBoundingClientRect();
  }
  function getCharTop(index) {
    return getCharRect(index).top;
  }
  function getCharBottom(index) {
    return getCharRect(index).bottom;
  }
  function findFirstPartiallyVisible() {
    var lo = 0,
      hi = textLength - 1;
    var result = 0;
    while (lo <= hi) {
      var mid = Math.floor((lo + hi) / 2);
      var y = getCharBottom(mid);
      if (y < viewTop) {
        lo = mid + 1;
      } else {
        result = mid;
        hi = mid - 1;
      }
    }
    return result;
  }
  function findLastPartiallyVisible() {
    var lo = 0,
      hi = textLength - 1;
    var result = textLength - 1;
    while (lo <= hi) {
      var mid = Math.floor((lo + hi) / 2);
      var y = getCharTop(mid);
      if (y > viewBottom) {
        hi = mid - 1;
      } else {
        result = mid;
        lo = mid + 1;
      }
    }
    return result;
  }
  var startIdx = findFirstPartiallyVisible();
  var endIdx = findLastPartiallyVisible();
  if (startIdx > endIdx) endIdx = startIdx;
  var range = document.createRange();
  range.setStart(textNode, startIdx);
  range.setEnd(textNode, Math.min(endIdx + 1, textLength));
  var rects = range.getClientRects();
  if (!rects || !rects.length) {
    var singleRect = getCharRect(startIdx);
    if (!singleRect || !isFinite(singleRect.top)) return false;
    rects = [singleRect];
  }
  var lineTops = [];
  var lastTop = null;
  for (var r = 0; r < rects.length; r++) {
    var rect = rects[r];
    if (!rect || rect.height <= 0) continue;
    var top = rect.top;
    if (lastTop === null || Math.abs(top - lastTop) > 0.5) {
      lineTops.push(top);
      lastTop = top;
    }
  }
  if (!lineTops.length) return false;
  var scrollTop = hoverLayoutState.sourcePager.scrollTop;
  var bestScroll = null;
  var bestDist = Infinity;
  for (var t = 0; t < lineTops.length; t++) {
    var targetScroll = scrollTop + (lineTops[t] - containerRect.top);
    var dist = Math.abs(targetScroll - scrollTop);
    if (dist < bestDist) {
      bestDist = dist;
      bestScroll = targetScroll;
    }
  }
  if (bestScroll == null) return false;
  if (Math.abs(bestScroll - scrollTop) > 1) {
    var maxScroll = Math.max(
      0,
      hoverLayoutState.sourcePager.scrollHeight - hoverLayoutState.sourcePager.clientHeight
    );
    var clamped = Math.max(0, Math.min(Math.round(bestScroll), maxScroll));
    if (Math.abs(clamped - scrollTop) <= 1) return false;
    hoverLayoutState.sourcePager.scrollTo({
      top: clamped,
      behavior: 'smooth'
    });
    return true;
  }
  return false;
}
export function snapDocxToLine() {
  if (
    !hoverLayoutState.sourcePager ||
    documentState.inputMode !== 'doc' ||
    !documentState.isOriginalView ||
    documentState.currentFileType !== 'docx'
  )
    return false;
  var host = hoverLayoutState.sourcePager.querySelector('.docx-preview-host');
  if (!host) return false;
  var sliceInfo = getVisibleDocxSliceText(hoverLayoutState.sourcePager);
  if (!sliceInfo || !sliceInfo.model || !sliceInfo.model.text) return false;
  var startIdx = Math.max(0, sliceInfo.start || 0);
  var endIdx = Math.max(startIdx, sliceInfo.end || 0);
  if (endIdx <= startIdx) endIdx = Math.min(startIdx + 1, sliceInfo.model.text.length);
  var containerRect = hoverLayoutState.sourcePager.getBoundingClientRect();
  var scrollTop = hoverLayoutState.sourcePager.scrollTop;
  try {
    var a = locateDomPos(sliceInfo.model, startIdx);
    var b = locateDomPos(sliceInfo.model, endIdx);
    if (!a || !b) return false;
    var range = document.createRange();
    range.setStart(a.node, a.offset);
    range.setEnd(b.node, b.offset);
    var rects = range.getClientRects();
    if (!rects || !rects.length) {
      var a2 = locateDomPos(sliceInfo.model, startIdx);
      if (!a2 || !a2.node) return false;
      var nodeLen2 = a2.node.nodeValue ? a2.node.nodeValue.length : 0;
      if (!nodeLen2) return false;
      var range2 = document.createRange();
      range2.setStart(a2.node, a2.offset);
      range2.setEnd(a2.node, Math.min(a2.offset + 1, nodeLen2));
      var rects2 = range2.getClientRects();
      if (!rects2 || !rects2.length) return false;
      rects = rects2;
    }
    var lineTops = [];
    var lastTop = null;
    for (var r = 0; r < rects.length; r++) {
      var rect = rects[r];
      if (!rect || rect.height <= 0) continue;
      var top = rect.top;
      if (lastTop === null || Math.abs(top - lastTop) > 0.5) {
        lineTops.push(top);
        lastTop = top;
      }
    }
    if (!lineTops.length) return false;
    var bestScroll = null;
    var bestDist = Infinity;
    for (var t = 0; t < lineTops.length; t++) {
      var targetScroll = scrollTop + (lineTops[t] - containerRect.top);
      var dist = Math.abs(targetScroll - scrollTop);
      if (dist < bestDist) {
        bestDist = dist;
        bestScroll = targetScroll;
      }
    }
    if (bestScroll == null) return false;
    if (Math.abs(bestScroll - scrollTop) > 1) {
      var maxScroll = Math.max(
        0,
        hoverLayoutState.sourcePager.scrollHeight - hoverLayoutState.sourcePager.clientHeight
      );
      var clamped = Math.max(0, Math.min(Math.round(bestScroll), maxScroll));
      if (Math.abs(clamped - scrollTop) <= 1) return false;
      hoverLayoutState.sourcePager.scrollTo({
        top: clamped,
        behavior: 'smooth'
      });
      return true;
    }
  } catch (e) {
    return false;
  }
  return false;
}
export function computePageMaxHeightPx() {
  var baseEl = hoverLayoutState.sourcePager || hoverLayoutState.sourceText;
  var w = baseEl ? baseEl.getBoundingClientRect().width || 0 : 0;

  // Default: A4-ish aspect ratio (1.414)
  var aspect = 1.414;
  if (w > 0) {
    return Math.ceil(w * aspect);
  }
  return Math.ceil(window.innerHeight * 0.5);
}
export function applyGlobalViewportClamp(forceCollapse) {
  var h = computePageMaxHeightPx();
  if (isFinite(h) && h > 0) viewportClampingState.lastPageHeightPx = h;
  var pagerMin = 180;
  var textMin = 180;
  var textMax = h;
  if (hoverLayoutState.sourcePager) {
    hoverLayoutState.sourcePager.style.setProperty('--pageMaxH', h + 'px');
    hoverLayoutState.sourcePager.style.setProperty('--pageH', h + 'px');
    if (documentState.inputMode === 'pdf' || documentState.inputMode === 'doc') {
      applyFixedDocumentViewportHeight(false);
    } else {
      hoverLayoutState.sourcePager.style.maxHeight = h + 'px';
      if (forceCollapse) {
        hoverLayoutState.sourcePager.style.height = pagerMin + 'px';
      }
    }
  }
  if (hoverLayoutState.sourceText) {
    if (documentState.rawContinuousMode) {
      var rawViewportH = Math.max(240, measureRawContinuousViewportHeight());
      documentState.docViewportHeightPx = rawViewportH;
      if (hoverLayoutState.sourcePager) {
        hoverLayoutState.sourcePager.style.setProperty('--pageMaxH', rawViewportH + 'px');
        hoverLayoutState.sourcePager.style.setProperty('--pageH', rawViewportH + 'px');
        hoverLayoutState.sourcePager.style.height = rawViewportH + 'px';
        hoverLayoutState.sourcePager.style.maxHeight = rawViewportH + 'px';
      }
      if (hoverLayoutState.docViewportWrap)
        hoverLayoutState.docViewportWrap.style.minHeight = rawViewportH + 'px';
      return;
    }
    if (documentState.inputMode === 'raw') {
      var rawMax = getRawMaxHeightPx();
      if (rawMax > 0) {
        textMax = Math.max(h, rawMax);
        var rawMin = getRawMinHeightPx();
        if (rawMin > 0) textMin = Math.max(textMin, rawMin);
        if (textMin > textMax) textMin = textMax;
      }
    }
    hoverLayoutState.sourceText.style.setProperty('--pageMaxH', textMax + 'px');
    hoverLayoutState.sourceText.style.setProperty('--pageH', textMax + 'px');
    hoverLayoutState.sourceText.style.maxHeight = textMax + 'px';
    if (forceCollapse) {
      hoverLayoutState.sourceText.style.height = textMin + 'px';
    }
  }
}

// ---- PDF.js iframe bridge (movement/page events -> active page) ----
export function initializeViewportClamping() {
  if (hoverLayoutState.docNavPrev) {
    hoverLayoutState.docNavPrev.addEventListener('pointerdown', function (ev) {
      beginDocumentNavButtonHold(ev, -1);
    });
    hoverLayoutState.docNavPrev.addEventListener('pointerup', endDocumentNavButtonHold);
    hoverLayoutState.docNavPrev.addEventListener('pointercancel', cancelDocumentNavButtonHold);
    hoverLayoutState.docNavPrev.addEventListener('click', function (ev) {
      ev.preventDefault();
    });
  }
  if (hoverLayoutState.docNavNext) {
    hoverLayoutState.docNavNext.addEventListener('pointerdown', function (ev) {
      beginDocumentNavButtonHold(ev, 1);
    });
    hoverLayoutState.docNavNext.addEventListener('pointerup', endDocumentNavButtonHold);
    hoverLayoutState.docNavNext.addEventListener('pointercancel', cancelDocumentNavButtonHold);
    hoverLayoutState.docNavNext.addEventListener('click', function (ev) {
      ev.preventDefault();
    });
  }
  if (hoverLayoutState.docNavTrack) {
    hoverLayoutState.docNavTrack.addEventListener('pointerdown', function (ev) {
      if (!ev || ev.button !== 0) return;
      ev.preventDefault();
      clearDocumentPageHold();
      var isThumb = hoverLayoutState.docNavThumb && ev.target === hoverLayoutState.docNavThumb;
      if (isThumb) {
        continuousScrollState.docNavDragging = true;
        continuousScrollState.docNavDragOffsetY = 0;
        continuousScrollState.docNavDragPreviewPageIndex = null;
        continuousScrollState.docNavNativePreviewRatio = null;
        if (hoverLayoutState.docNavThumb) {
          var activeThumbRect = hoverLayoutState.docNavThumb.getBoundingClientRect();
          continuousScrollState.docNavDragOffsetY = Math.max(0, ev.clientY - activeThumbRect.top);
        }
        if (hoverLayoutState.docNavThumb) hoverLayoutState.docNavThumb.classList.add('dragging');
      } else {
        var dir = 1;
        if (hoverLayoutState.docNavThumb) {
          var thumbRect = hoverLayoutState.docNavThumb.getBoundingClientRect();
          dir = ev.clientY < thumbRect.top ? -1 : 1;
        }
        if (isFoliatePagedDocumentActive()) startFoliatePageHold(dir, ev.pointerId);
        else if (isFlowScrollDocumentActive()) startWebSnapshotScrollHold(dir, 'page', ev.pointerId);
        else startDocumentPageHold(dir, ev.pointerId);
      }
      if (typeof hoverLayoutState.docNavTrack.setPointerCapture === 'function') {
        try {
          hoverLayoutState.docNavTrack.setPointerCapture(ev.pointerId);
        } catch (_e) {}
      }
    });
    hoverLayoutState.docNavTrack.addEventListener('pointermove', function (ev) {
      if (!continuousScrollState.docNavDragging) return;
      ev.preventDefault();
      if (isRawContinuousActive()) {
        scrollRawContinuousToRatio(webSnapshotRatioFromNavigatorEvent(ev));
      } else if (isActiveWebSnapshotDocument()) {
        scrollWebSnapshotToRatio(webSnapshotRatioFromNavigatorEvent(ev));
      } else if (isActiveEpubDocument()) {
        continuousScrollState.docNavNativePreviewRatio = webSnapshotRatioFromNavigatorEvent(ev);
        updateDocumentNavigatorThumb();
        scrollEpubToRatio(continuousScrollState.docNavNativePreviewRatio);
      } else if (isActiveFoliateFlowDocument()) {
        continuousScrollState.docNavNativePreviewRatio = webSnapshotRatioFromNavigatorEvent(ev);
        updateDocumentNavigatorThumb();
        scrollEpubToRatio(continuousScrollState.docNavNativePreviewRatio);
      } else if (isDocxContinuousActive()) {
        scrollDocxContinuousToRatio(webSnapshotRatioFromNavigatorEvent(ev));
      } else {
        setActiveDocumentPage(pageIndexFromNavigatorEvent(ev), 'drag');
      }
    });
    hoverLayoutState.docNavTrack.addEventListener('pointerup', function (ev) {
      var finalFoliateRatio =
        isFoliatePagedDocumentActive() && continuousScrollState.docNavNativePreviewRatio != null
          ? continuousScrollState.docNavNativePreviewRatio
          : null;
      stopDocumentPageHold(ev && ev.pointerId);
      continuousScrollState.docNavDragging = false;
      continuousScrollState.docNavDragOffsetY = 0;
      if (hoverLayoutState.docNavThumb) hoverLayoutState.docNavThumb.classList.remove('dragging');
      if (typeof hoverLayoutState.docNavTrack.releasePointerCapture === 'function') {
        try {
          hoverLayoutState.docNavTrack.releasePointerCapture(ev.pointerId);
        } catch (_e2) {}
      }
      if (finalFoliateRatio != null) {
        scrollEpubToRatio(finalFoliateRatio).then(function () {
          continuousScrollState.docNavNativePreviewRatio = null;
          updateDocumentNavigatorThumb();
        });
      }
    });
    hoverLayoutState.docNavTrack.addEventListener('pointercancel', function (ev) {
      stopDocumentPageHold(ev && ev.pointerId);
      continuousScrollState.docNavDragging = false;
      continuousScrollState.docNavDragOffsetY = 0;
      continuousScrollState.docNavNativePreviewRatio = null;
      if (hoverLayoutState.docNavThumb) hoverLayoutState.docNavThumb.classList.remove('dragging');
      if (typeof hoverLayoutState.docNavTrack.releasePointerCapture === 'function') {
        try {
          hoverLayoutState.docNavTrack.releasePointerCapture(ev.pointerId);
        } catch (_e3) {}
      }
      updateDocumentNavigatorThumb();
    });
  }
  if (hoverLayoutState.pdfZoomInButton)
    hoverLayoutState.pdfZoomInButton.addEventListener('click', function () {
      postPdfCommand('zoomIn');
    });
  if (hoverLayoutState.pdfZoomOutButton)
    hoverLayoutState.pdfZoomOutButton.addEventListener('click', function () {
      postPdfCommand('zoomOut');
    });
  if (hoverLayoutState.pdfZoomResetButton)
    hoverLayoutState.pdfZoomResetButton.addEventListener('click', function () {
      postPdfCommand('zoomReset');
    });
  if (hoverLayoutState.pdfModeButton)
    hoverLayoutState.pdfModeButton.addEventListener('click', function () {
      postPdfCommand('toggleMode');
    });
  if (hoverLayoutState.webInspectorButton) {
    hoverLayoutState.webInspectorButton.addEventListener('click', function () {
      if (!isTopSourceInspectorAvailable()) return;
      setWebSnapshotInspectorEnabled(!documentState.webSnapshotInspectorEnabled);
    });
  }
  if (hoverLayoutState.trankitChunkLookupButton) {
    hoverLayoutState.trankitChunkLookupButton.addEventListener('click', function () {
      if (hoverLayoutState.TRANKIT_CHUNK_LOOKUP_DISABLED) return;
      if (!isTrankitChunkLookupAvailable()) return;
      documentState.trankitChunkLookupEnabled = !documentState.trankitChunkLookupEnabled;
      if (
        documentState.canonicalReaderController &&
        documentState.canonicalReaderController.cache &&
        typeof documentState.canonicalReaderController.cache.clear === 'function'
      ) {
        documentState.canonicalReaderController.cache.clear();
      }
      syncTrankitChunkLookupControls();
    });
  }
  if (hoverLayoutState.docContentsButton) {
    hoverLayoutState.docContentsButton.addEventListener('click', function (ev) {
      ev.preventDefault();
      if (!hasDocumentNavItems()) return;
      if (hoverLayoutState.docContentsMenu) {
        hoverLayoutState.docContentsMenu.hidden = !hoverLayoutState.docContentsMenu.hidden;
        if (!hoverLayoutState.docContentsMenu.hidden) hideDocumentSearchMenu();
      }
      syncDocumentCapabilityControls();
    });
  }
  if (hoverLayoutState.docNavMenuList) {
    hoverLayoutState.docNavMenuList.addEventListener('click', function (ev) {
      var btn = ev.target && ev.target.closest ? ev.target.closest('[data-doc-nav-id]') : null;
      if (!btn) return;
      var id = String(btn.getAttribute('data-doc-nav-id') || '');
      var list = documentState.documentCapabilities.toc || [];
      var item = (list || []).find(function (x) {
        return x && x.id === id;
      });
      goToDocumentNavItem(item);
    });
  }
  if (hoverLayoutState.docPageNumberInput) {
    hoverLayoutState.docPageNumberInput.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        submitDocumentPageNumberInput();
        try {
          hoverLayoutState.docPageNumberInput.blur();
        } catch (_blurErr) {}
      } else if (ev.key === 'Escape') {
        ev.preventDefault();
        syncDocumentChrome();
        try {
          hoverLayoutState.docPageNumberInput.blur();
        } catch (_escBlurErr) {}
      }
    });
    hoverLayoutState.docPageNumberInput.addEventListener('blur', function () {
      submitDocumentPageNumberInput();
      syncDocumentChrome();
    });
  }
  if (hoverLayoutState.docSearchField) {
    hoverLayoutState.docSearchField.addEventListener('input', function () {
      var q = String(hoverLayoutState.docSearchField.value || '').trim();
      if (!q) {
        clearDocumentSearch();
        return;
      }
      if (hoverLayoutState.docSearchMenu) hoverLayoutState.docSearchMenu.hidden = false;
      foliateViewportState.runSharedDocumentSearch();
    });
    hoverLayoutState.docSearchField.addEventListener('focus', function () {
      if (documentState.documentSearchResults.length && hoverLayoutState.docSearchMenu)
        hoverLayoutState.docSearchMenu.hidden = false;
    });
    hoverLayoutState.docSearchField.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        stepDocumentSearch(ev.shiftKey ? -1 : 1);
      } else if (ev.key === 'Escape') {
        hideDocumentSearchMenu();
      }
    });
  }
  if (hoverLayoutState.docSearchPrevButton)
    hoverLayoutState.docSearchPrevButton.addEventListener('click', function () {
      stepDocumentSearch(-1);
    });
  if (hoverLayoutState.docSearchNextButton)
    hoverLayoutState.docSearchNextButton.addEventListener('click', function () {
      stepDocumentSearch(1);
    });
  if (hoverLayoutState.docSearchClearButton)
    hoverLayoutState.docSearchClearButton.addEventListener('click', function () {
      clearDocumentSearch();
    });
  if (hoverLayoutState.docSearchMenuList) {
    hoverLayoutState.docSearchMenuList.addEventListener('click', function (ev) {
      var btn = ev.target && ev.target.closest ? ev.target.closest('[data-doc-search-index]') : null;
      if (!btn) return;
      goToDocumentSearchResult(Number(btn.getAttribute('data-doc-search-index')) || 0);
    });
  }
  document.addEventListener('click', function (ev) {
    var target = ev.target;
    if (
      hoverLayoutState.docContentsMenu &&
      hoverLayoutState.docContentsButton &&
      !hoverLayoutState.docContentsMenu.hidden
    ) {
      if (
        !hoverLayoutState.docContentsMenu.contains(target) &&
        !hoverLayoutState.docContentsButton.contains(target)
      )
        hideDocumentNavMenu();
    }
    if (
      hoverLayoutState.docSearchMenu &&
      hoverLayoutState.docSearchField &&
      !hoverLayoutState.docSearchMenu.hidden
    ) {
      if (
        !hoverLayoutState.docSearchMenu.contains(target) &&
        !hoverLayoutState.docSearchField.contains(target)
      )
        hideDocumentSearchMenu();
    }
  });
  if (hoverLayoutState.pdfSearchPrevButton)
    hoverLayoutState.pdfSearchPrevButton.addEventListener('click', function () {
      postPdfCommand('searchPrev');
    });
  if (hoverLayoutState.pdfSearchNextButton)
    hoverLayoutState.pdfSearchNextButton.addEventListener('click', function () {
      postPdfCommand('searchNext');
    });
  if (hoverLayoutState.pdfSearchClearButton)
    hoverLayoutState.pdfSearchClearButton.addEventListener('click', function () {
      if (hoverLayoutState.pdfSearchField) hoverLayoutState.pdfSearchField.value = '';
      if (hoverLayoutState.pdfSearchCountLabel) hoverLayoutState.pdfSearchCountLabel.textContent = '0/0';
      postPdfCommand('searchClear');
    });
  if (hoverLayoutState.pdfSearchField) {
    hoverLayoutState.pdfSearchField.addEventListener(
      'input',
      debounce(function () {
        postPdfCommand('search', {
          query: hoverLayoutState.pdfSearchField.value || ''
        });
      }, 120)
    );
    hoverLayoutState.pdfSearchField.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        postPdfCommand(ev.shiftKey ? 'searchPrev' : 'searchNext');
      }
    });
  }
  viewportClampingState.lastPageHeightPx = 0;
  window.addEventListener('message', function (event) {
    if (event.origin !== window.location.origin) return;
    var data = event.data || {};
    if (!data || data.source !== 'pdfjs-iframe') return;
    if (String(data.sessionId || '') !== String(documentShellState.pdfJsSessionId)) return;
    if (documentState.inputMode !== 'pdf') return;
    if (data.type === 'pdfjs-error') {
      hoverLayoutState.statusText.textContent = 'Failed to load PDF viewer.';
      if (hoverLayoutState.renderedText) {
        hoverLayoutState.renderedText.innerHTML =
          '<div class="reader-output-placeholder">PDF.js iframe error: ' +
          escapeHtml(String(data.error || 'unknown')) +
          '</div>';
      }
      return;
    }
    if (data.type === 'pdfjs-ready') {
      hoverLayoutState.statusText.textContent = 'Ready (' + (documentState.docPages.length || 0) + ' pages).';
      documentShellState.pdfSourceInspectorCommanded = null;
      postPdfPageDimsCacheToIframe();
      syncDocumentChrome();
      return;
    }
    if (data.type === 'pdfjs-document-nav') {
      setDocumentCapabilities({
        source: 'pdf',
        toc: Array.isArray(data.toc) ? data.toc : [],
        pageList: Array.isArray(data.pageList) ? data.pageList : []
      });
      syncDocumentChrome();
      return;
    }
    if (data.type === 'pdfjs-search-results') {
      var pdfResults = Array.isArray(data.results) ? data.results : [];
      documentState.documentSearchPending = !!data.pending;
      documentState.documentSearchTotalCount = Math.max(
        0,
        Math.floor(Number(data.total) || pdfResults.length || 0)
      );
      documentState.documentSearchResults = pdfResults.map(function (item, idx) {
        item = item || {};
        return {
          resultIndex: item.resultIndex != null ? Number(item.resultIndex) : idx,
          label: String(item.label || 'Match ' + (idx + 1)),
          excerpt: item.excerpt || null,
          pageIndex: item.pageIndex != null ? Number(item.pageIndex) : null
        };
      });
      var activePdfSearchIndex = Number(data.activeIndex);
      documentState.documentSearchActiveIndex = isFinite(activePdfSearchIndex) ? activePdfSearchIndex : -1;
      renderDocumentSearchResults();
      if (
        hoverLayoutState.docSearchMenu &&
        hoverLayoutState.docSearchField &&
        String(hoverLayoutState.docSearchField.value || '').trim()
      ) {
        hoverLayoutState.docSearchMenu.hidden = false;
      }
      syncDocumentCapabilityControls();
      return;
    }
    if (data.type === 'pdfjs-dimensions') {
      applyFixedDocumentViewportHeight(true);
      syncDocumentChrome();
      return;
    }
    if (data.type === 'pdfjs-scroll') {
      requestMovementLookup();
      return;
    }
    if (data.type === 'pdfjs-state') {
      var statePage = Number(data.pageIndex);
      if (isFinite(statePage) && statePage >= 0)
        documentState.activePageIndex = Math.min(
          Math.max(0, statePage),
          Math.max(0, (documentState.docPages.length || 1) - 1)
        );
      if (hoverLayoutState.pdfSearchCountLabel && typeof data.searchLabel === 'string')
        hoverLayoutState.pdfSearchCountLabel.textContent = data.searchLabel || '0/0';
      if (hoverLayoutState.docSearchCountLabel && typeof data.searchLabel === 'string')
        hoverLayoutState.docSearchCountLabel.textContent = data.searchLabel || '0/0';
      if (hoverLayoutState.pdfModeButton && typeof data.interactionMode === 'string') {
        hoverLayoutState.pdfModeButton.innerHTML = data.interactionMode === 'drag' ? '&#9995;' : '&#9998;';
        hoverLayoutState.pdfModeButton.setAttribute(
          'aria-label',
          data.interactionMode === 'drag' ? 'Drag mode' : 'Highlight mode'
        );
      }
      syncDocumentChrome();
      return;
    }
    if (data.type === 'pdfjs-text-layer') {
      if (data.error) {
        console.warn('PDF.js text layer error:', data.error);
        return;
      }
      var tlIdx = Number(data.pageIndex);
      if (isFinite(tlIdx) && tlIdx >= 0) {
        documentState.pdfjsTextLayerCache[tlIdx] = {
          innerHTML: typeof data.innerHTML === 'string' ? data.innerHTML : '',
          plainText: typeof data.plainText === 'string' ? data.plainText : '',
          layerClass: typeof data.layerClass === 'string' ? data.layerClass : 'textLayer',
          layerStyle: typeof data.layerStyle === 'string' ? data.layerStyle : '',
          computedScaleFactor: Number(data.computedScaleFactor) || 1,
          computedTotalScaleFactor:
            Number(data.computedTotalScaleFactor) || Number(data.computedScaleFactor) || 1,
          viewportWidth: Number(data.viewportWidth) || 0,
          viewportHeight: Number(data.viewportHeight) || 0
        };
        if (shouldUsePdfjsTextLayer()) triggerUpdate();
      }
      return;
    }
    if (data.type !== 'pdfjs-pagechange') return;
    var idx = Number(data.pageIndex);
    if (!isFinite(idx)) return;
    idx = Math.floor(idx);
    if (idx < 0) return;
    var maxIdx = Math.max(0, (documentState.docPages.length || 1) - 1);
    if (idx > maxIdx) idx = maxIdx;
    warmPdfCanonicalPage(idx, 'pdfjs-pagechange');
    if (idx === documentState.activePageIndex) return;
    documentState.activePageIndex = idx;
    syncDocumentChrome();
    requestMovementLookup();
  });
  return true;
}
