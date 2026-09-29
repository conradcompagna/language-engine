import { clamp } from './bridge.mjs';
import { bridgeState } from './bridge.state.mjs';
import { emitDimensions, emitPageChange, emitScroll, emitState, updatePageBadge } from './lifecycle.mjs';
import { stepSearchControls } from './search-results.mjs';
export function updateNavigatorButtons() {
  if (bridgeState.navPrev)
    bridgeState.navPrev.disabled = bridgeState.currentPageNumber <= 1 || bridgeState.totalPages <= 1;
  if (bridgeState.navNext)
    bridgeState.navNext.disabled =
      bridgeState.currentPageNumber >= bridgeState.totalPages || bridgeState.totalPages <= 1;
}
export function updateNavigatorThumb() {
  if (!bridgeState.navTrack || !bridgeState.navThumb) return;
  var pages = Math.max(1, bridgeState.totalPages || 1);
  var trackH = Math.max(1, Math.floor(bridgeState.navTrack.clientHeight || 1));
  var thumbH = Math.max(18, Math.min(56, Math.floor(trackH / pages)));
  var usable = Math.max(0, trackH - thumbH);
  var ratio = pages > 1 ? (bridgeState.currentPageNumber - 1) / (pages - 1) : 0;
  var top = Math.round(usable * ratio);
  bridgeState.navThumb.style.height = String(thumbH) + 'px';
  bridgeState.navThumb.style.transform = 'translateY(' + String(top) + 'px)';
  bridgeState.navThumb.dataset.thumbH = String(thumbH);
}
export function updateNavigator() {
  updateNavigatorButtons();
  updateNavigatorThumb();
}
export function goToPage(pageNumber, forceEmit) {
  if (!bridgeState.pdfViewer || !bridgeState.totalPages) return;
  var n = clamp(Number(pageNumber) || 1, 1, Math.max(1, bridgeState.totalPages || 1));
  if (bridgeState.pdfViewer.currentPageNumber !== n) {
    bridgeState.pdfViewer.currentPageNumber = n;
  }
  if (forceEmit) {
    bridgeState.currentPageNumber = n;
    updatePageBadge(n);
    updateNavigator();
    emitPageChange(n);
    emitScroll(n);
    emitDimensions(n);
    emitState();
  }
}
export function stepPage(delta) {
  var dir = Number(delta) >= 0 ? 1 : -1;
  goToPage(bridgeState.currentPageNumber + dir, false);
}
export function clearTrackHold() {
  bridgeState.trackHoldDirection = 0;
  if (bridgeState.trackHoldDelayTimer) {
    clearTimeout(bridgeState.trackHoldDelayTimer);
    bridgeState.trackHoldDelayTimer = 0;
  }
  if (bridgeState.trackHoldRepeatTimer) {
    clearInterval(bridgeState.trackHoldRepeatTimer);
    bridgeState.trackHoldRepeatTimer = 0;
  }
}
export function startTrackHold(direction) {
  clearTrackHold();
  var dir = Number(direction) >= 0 ? 1 : -1;
  bridgeState.trackHoldDirection = dir;
  stepPage(dir);
  bridgeState.trackHoldDelayTimer = setTimeout(function () {
    bridgeState.trackHoldDelayTimer = 0;
    bridgeState.trackHoldRepeatTimer = setInterval(function () {
      if (!bridgeState.trackHoldDirection) return;
      stepPage(bridgeState.trackHoldDirection);
    }, bridgeState.TRACK_HOLD_REPEAT_MS);
  }, bridgeState.TRACK_HOLD_DELAY_MS);
}
export function clearSearchArrowHoldTimers() {
  if (bridgeState.searchArrowHoldDelayTimer) {
    clearTimeout(bridgeState.searchArrowHoldDelayTimer);
    bridgeState.searchArrowHoldDelayTimer = 0;
  }
  if (bridgeState.searchArrowHoldRepeatTimer) {
    clearInterval(bridgeState.searchArrowHoldRepeatTimer);
    bridgeState.searchArrowHoldRepeatTimer = 0;
  }
}
export function startSearchArrowHold(direction, pointerId) {
  clearSearchArrowHoldTimers();
  bridgeState.searchArrowHoldDirection = Number(direction) >= 0 ? 1 : -1;
  bridgeState.searchArrowHoldPointerId = isFinite(pointerId) ? Number(pointerId) : null;
  bridgeState.searchArrowHoldDidRepeat = false;
  bridgeState.searchArrowHoldDelayTimer = setTimeout(function () {
    bridgeState.searchArrowHoldDelayTimer = 0;
    bridgeState.searchArrowHoldDidRepeat = true;
    bridgeState.searchArrowHoldRepeatTimer = setInterval(function () {
      if (!bridgeState.searchArrowHoldDirection) return;
      stepSearchControls(bridgeState.searchArrowHoldDirection);
    }, bridgeState.SEARCH_ARROW_HOLD_REPEAT_MS);
  }, bridgeState.SEARCH_ARROW_HOLD_DELAY_MS);
}
export function stopSearchArrowHold(pointerId) {
  var pid = isFinite(pointerId) ? Number(pointerId) : null;
  if (
    bridgeState.searchArrowHoldPointerId !== null &&
    pid !== null &&
    pid !== bridgeState.searchArrowHoldPointerId
  )
    return;
  if (bridgeState.searchArrowHoldDidRepeat) bridgeState.suppressSearchArrowClick = true;
  bridgeState.searchArrowHoldDirection = 0;
  bridgeState.searchArrowHoldPointerId = null;
  clearSearchArrowHoldTimers();
  bridgeState.searchArrowHoldDidRepeat = false;
}
export function beginThumbDrag(ev) {
  if (!ev) return;
  ev.preventDefault();
  clearTrackHold();
  var thumbRect = bridgeState.navThumb.getBoundingClientRect();
  bridgeState.thumbDragging = true;
  bridgeState.thumbDragOffsetY = ev.clientY - thumbRect.top;
  bridgeState.navThumb.classList.add('dragging');
  if (bridgeState.navTrack && typeof bridgeState.navTrack.setPointerCapture === 'function') {
    try {
      bridgeState.navTrack.setPointerCapture(ev.pointerId);
    } catch (e) {}
  }
}
export function moveThumbDrag(ev) {
  if (!bridgeState.thumbDragging || !ev) return;
  ev.preventDefault();
  var trackRect = bridgeState.navTrack.getBoundingClientRect();
  var thumbH = Number(bridgeState.navThumb.dataset.thumbH || 20);
  var usable = Math.max(1, Math.floor(trackRect.height - thumbH));
  var top = clamp(ev.clientY - trackRect.top - bridgeState.thumbDragOffsetY, 0, usable);
  var ratio = top / usable;
  var pages = Math.max(1, bridgeState.totalPages || 1);
  var target = pages <= 1 ? 1 : 1 + Math.round(ratio * (pages - 1));
  goToPage(target, false);
}
export function endThumbDrag(ev) {
  if (!bridgeState.thumbDragging) return;
  bridgeState.thumbDragging = false;
  bridgeState.navThumb.classList.remove('dragging');
  if (bridgeState.navTrack && ev && typeof bridgeState.navTrack.releasePointerCapture === 'function') {
    try {
      bridgeState.navTrack.releasePointerCapture(ev.pointerId);
    } catch (e) {}
  }
}
