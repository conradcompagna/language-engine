import { bridgeState } from './bridge.state.mjs';
import { emitState } from './lifecycle.mjs';
export function isDragMode() {
  return bridgeState.interactionMode === 'drag';
}
export function endPanDrag(ev) {
  if (!bridgeState.panDragActive) return;
  bridgeState.panDragActive = false;
  bridgeState.panPointerId = null;
  bridgeState.pdfContainer.classList.remove('dragging');
  if (
    bridgeState.pdfContainer &&
    ev &&
    typeof bridgeState.pdfContainer.releasePointerCapture === 'function'
  ) {
    try {
      bridgeState.pdfContainer.releasePointerCapture(ev.pointerId);
    } catch (e) {}
  }
}
export function setInteractionMode(mode) {
  var m = bridgeState.sourceInspectorActive ? 'highlight' : 'drag';
  bridgeState.interactionMode = m;
  if (bridgeState.pdfContainer) {
    bridgeState.pdfContainer.classList.toggle('drag-mode', m === 'drag');
    if (m !== 'drag') {
      endPanDrag();
    }
  }
  if (bridgeState.modeToggleBtn) {
    bridgeState.modeToggleBtn.textContent = m === 'drag' ? '\u270B\uFE0E' : '\u270E';
    bridgeState.modeToggleBtn.setAttribute('aria-pressed', m === 'drag' ? 'true' : 'false');
    bridgeState.modeToggleBtn.setAttribute('aria-label', m === 'drag' ? 'Drag mode' : 'Highlighter mode');
  }
  emitState();
}
export function setSourceInspectorEnabled(enabled) {
  var next = !!enabled;
  if (bridgeState.sourceInspectorActive === next) {
    if (bridgeState.pdfContainer)
      bridgeState.pdfContainer.classList.toggle('source-inspector-active', bridgeState.sourceInspectorActive);
    return;
  }
  bridgeState.sourceInspectorActive = next;
  if (bridgeState.pdfContainer) {
    bridgeState.pdfContainer.classList.toggle('source-inspector-active', bridgeState.sourceInspectorActive);
  }
  if (bridgeState.sourceInspectorActive) {
    endPanDrag();
    setInteractionMode('highlight');
  } else {
    try {
      var sel = window.getSelection ? window.getSelection() : null;
      if (sel && typeof sel.removeAllRanges === 'function') sel.removeAllRanges();
    } catch (e) {}
    setInteractionMode('drag');
  }
}
export function beginPanDrag(ev) {
  if (!bridgeState.pdfContainer || !ev) return;
  if (bridgeState.sourceInspectorActive) return;
  if (!isDragMode()) return;
  if (ev.button !== 0) return;
  ev.preventDefault();
  bridgeState.panDragActive = true;
  bridgeState.panPointerId = ev.pointerId;
  bridgeState.panStartX = ev.clientX;
  bridgeState.panStartY = ev.clientY;
  bridgeState.panStartLeft = bridgeState.pdfContainer.scrollLeft;
  bridgeState.panStartTop = bridgeState.pdfContainer.scrollTop;
  bridgeState.pdfContainer.classList.add('dragging');
  if (typeof bridgeState.pdfContainer.setPointerCapture === 'function') {
    try {
      bridgeState.pdfContainer.setPointerCapture(ev.pointerId);
    } catch (e) {}
  }
}
export function movePanDrag(ev) {
  if (!bridgeState.panDragActive || !bridgeState.pdfContainer || !ev) return;
  if (bridgeState.panPointerId !== null && ev.pointerId !== bridgeState.panPointerId) return;
  ev.preventDefault();
  var dx = ev.clientX - bridgeState.panStartX;
  var dy = ev.clientY - bridgeState.panStartY;
  bridgeState.pdfContainer.scrollLeft = bridgeState.panStartLeft - dx;
  bridgeState.pdfContainer.scrollTop = bridgeState.panStartTop - dy;
}
