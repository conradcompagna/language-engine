import { clamp, post } from './bridge.mjs';
import { bridgeState } from './bridge.state.mjs';
export function updatePageBadge(pageNumber) {
  var n = clamp(Number(pageNumber) || 1, 1, Math.max(1, bridgeState.totalPages || 1));
  bridgeState.pageBadge.textContent =
    bridgeState.totalPages > 0 ? n + ' / ' + bridgeState.totalPages : String(n);
}
export function emitPageChange(pageNumber) {
  var n = clamp(Number(pageNumber) || 1, 1, Math.max(1, bridgeState.totalPages || 1));
  post('pdfjs-pagechange', {
    pageNumber: n,
    pageIndex: n - 1
  });
}
export function emitScroll(pageNumber) {
  var n = clamp(Number(pageNumber) || 1, 1, Math.max(1, bridgeState.totalPages || 1));
  post('pdfjs-scroll', {
    pageNumber: n,
    pageIndex: n - 1
  });
}
export function emitHover(pageNumber) {
  var n = clamp(Number(pageNumber) || 1, 1, Math.max(1, bridgeState.totalPages || 1));
  post('pdfjs-hover-page', {
    pageNumber: n,
    pageIndex: n - 1
  });
}
export function getCurrentPageView(pageNumber) {
  if (!bridgeState.pdfViewer || !bridgeState.pdfViewer.getPageView) return null;
  var idx = clamp((Number(pageNumber) || 1) - 1, 0, Math.max(0, bridgeState.totalPages - 1));
  return bridgeState.pdfViewer.getPageView(idx) || null;
}
export function emitDimensions(pageNumber) {
  var n = clamp(
    Number(pageNumber) || bridgeState.currentPageNumber || 1,
    1,
    Math.max(1, bridgeState.totalPages || 1)
  );
  var w = Math.ceil(bridgeState.pdfContainer.clientWidth || 0);
  var h = Math.ceil(bridgeState.pdfContainer.clientHeight || 0);
  var pageView = getCurrentPageView(n);
  if (pageView) {
    if (pageView.viewport && pageView.viewport.width && pageView.viewport.height) {
      w = Math.ceil(pageView.viewport.width);
      h = Math.ceil(pageView.viewport.height);
    } else if (pageView.div) {
      var r = pageView.div.getBoundingClientRect();
      w = Math.ceil(r.width || w);
      h = Math.ceil(r.height || h);
    }
  }
  post('pdfjs-dimensions', {
    pageNumber: n,
    pageIndex: n - 1,
    pageHeight: h,
    pageWidth: w,
    containerHeight: Math.ceil(bridgeState.pdfContainer.clientHeight || 0),
    containerWidth: Math.ceil(bridgeState.pdfContainer.clientWidth || 0)
  });
}
export function applyNativePageFit() {
  if (!bridgeState.pdfViewer) return;
  try {
    bridgeState.manualZoomEnabled = false;
    bridgeState.pdfViewer.currentScaleValue = 'page-fit';
  } catch (e) {
    // ignore
  }
}
export function getCurrentScaleValue() {
  var scale = Number(bridgeState.pdfViewer && bridgeState.pdfViewer.currentScale);
  if (!isFinite(scale) || scale <= 0) return 1;
  return scale;
}
export function emitState(extra) {
  var payload = {
    pageNumber: bridgeState.currentPageNumber || 1,
    pageIndex: Math.max(0, (bridgeState.currentPageNumber || 1) - 1),
    totalPages: bridgeState.totalPages || 0,
    searchLabel: bridgeState.searchCount ? String(bridgeState.searchCount.textContent || '0/0') : '0/0',
    interactionMode: bridgeState.interactionMode || 'highlight',
    sourceInspectorActive: !!bridgeState.sourceInspectorActive,
    scale: getCurrentScaleValue()
  };
  if (extra && typeof extra === 'object') {
    for (var k in extra) {
      if (Object.prototype.hasOwnProperty.call(extra, k)) payload[k] = extra[k];
    }
  }
  post('pdfjs-state', payload);
}
