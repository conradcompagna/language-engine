import { clamp, normalizeSearchText, post } from './bridge.mjs';
import { bridgeState } from './bridge.state.mjs';
import {
  applyNativePageFit,
  emitDimensions,
  emitPageChange,
  emitScroll,
  emitState,
  getCurrentScaleValue,
  updatePageBadge
} from './lifecycle.mjs';
import { updateNavigator } from './pagination.mjs';
export function normalizePdfOutlineItems(items, level, out) {
  out = out || [];
  var arr = Array.isArray(items) ? items : [];
  var baseLevel = Math.max(0, Math.floor(Number(level) || 0));
  for (var i = 0; i < arr.length; i++) {
    var item = arr[i] || {};
    var label = normalizeSearchText(item.title || item.label || '');
    if (label && item.dest) {
      var id = 'pdf-outline-' + out.length;
      bridgeState.pdfOutlineDestById[id] = item.dest;
      out.push({
        id: id,
        label: label,
        level: baseLevel,
        kind: 'toc'
      });
    }
    if (Array.isArray(item.items) && item.items.length) {
      normalizePdfOutlineItems(item.items, baseLevel + 1, out);
    }
  }
  return out;
}
export function normalizePdfPageLabels(labels) {
  if (!Array.isArray(labels) || !labels.length) return [];
  return labels.map(function (label, idx) {
    return {
      id: 'pdf-page-label-' + idx,
      label: normalizeSearchText(label || 'Page ' + (idx + 1)),
      level: 0,
      kind: 'pageList',
      pageIndex: idx
    };
  });
}
export function publishPdfDocumentNav() {
  if (!bridgeState.pdfDoc) return;
  bridgeState.pdfOutlineDestById = {};
  Promise.all([
    (typeof bridgeState.pdfDoc.getOutline === 'function'
      ? bridgeState.pdfDoc.getOutline()
      : Promise.resolve(null)
    ).catch(function () {
      return null;
    }),
    (typeof bridgeState.pdfDoc.getPageLabels === 'function'
      ? bridgeState.pdfDoc.getPageLabels()
      : Promise.resolve(null)
    ).catch(function () {
      return null;
    })
  ])
    .then(function (values) {
      post('pdfjs-document-nav', {
        toc: normalizePdfOutlineItems(values[0] || [], 0, []),
        pageList: normalizePdfPageLabels(values[1] || [])
      });
    })
    .catch(function () {
      post('pdfjs-document-nav', {
        toc: [],
        pageList: []
      });
    });
}
export function goToOutlineItem(id) {
  var dest = bridgeState.pdfOutlineDestById[String(id || '')];
  if (
    !dest ||
    !bridgeState.pdfLinkService ||
    typeof bridgeState.pdfLinkService.goToDestination !== 'function'
  )
    return;
  Promise.resolve(bridgeState.pdfLinkService.goToDestination(dest))
    .then(function () {
      setTimeout(function () {
        bridgeState.currentPageNumber = bridgeState.pdfViewer
          ? bridgeState.pdfViewer.currentPageNumber || bridgeState.currentPageNumber || 1
          : bridgeState.currentPageNumber;
        updatePageBadge(bridgeState.currentPageNumber);
        updateNavigator();
        emitPageChange(bridgeState.currentPageNumber);
        emitScroll(bridgeState.currentPageNumber);
        emitDimensions(bridgeState.currentPageNumber);
        emitState();
      }, 80);
    })
    .catch(function (err) {
      post('pdfjs-error', {
        error: String((err && err.message) || err || 'outline_navigation_failed')
      });
    });
}
export function setManualZoom(nextScale) {
  if (!bridgeState.pdfViewer) return;
  var scale = clamp(Number(nextScale) || 1, bridgeState.ZOOM_MIN_SCALE, bridgeState.ZOOM_MAX_SCALE);
  try {
    bridgeState.manualZoomEnabled = true;
    bridgeState.pdfViewer.currentScale = scale;
    emitDimensions(bridgeState.currentPageNumber);
    emitState();
  } catch (e) {
    // ignore
  }
}
export function zoomIn() {
  setManualZoom(getCurrentScaleValue() * bridgeState.ZOOM_STEP_FACTOR);
}
export function zoomOut() {
  setManualZoom(getCurrentScaleValue() / bridgeState.ZOOM_STEP_FACTOR);
}
export function resetZoom() {
  applyNativePageFit();
  emitDimensions(bridgeState.currentPageNumber);
  emitState();
}
