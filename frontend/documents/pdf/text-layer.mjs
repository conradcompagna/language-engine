import { clamp, normalizeSearchText, post } from './bridge.mjs';
import { bridgeState } from './bridge.state.mjs';
import {
  applyNativePageFit,
  emitDimensions,
  emitPageChange,
  emitScroll,
  emitState,
  getCurrentPageView,
  updatePageBadge
} from './lifecycle.mjs';
import { updateNavigator } from './pagination.mjs';
import { syncSearchPositionToPage } from './search-results.mjs';
import { queueNativeHighlight, setSearchCountLabel } from './search-ui.mjs';
export function extractAndPostTextLayer(pageNum) {
  var n = clamp(
    Number(pageNum) || bridgeState.currentPageNumber || 1,
    1,
    Math.max(1, bridgeState.totalPages || 1)
  );
  var pageView = getCurrentPageView(n);
  var textLayerDiv = pageView && pageView.div ? pageView.div.querySelector('.textLayer') : null;
  if (textLayerDiv) {
    var spans = textLayerDiv.querySelectorAll('span');
    var parts = [];
    for (var i = 0; i < spans.length; i++) parts.push(spans[i].textContent || '');
    post('pdfjs-text-layer', {
      pageNumber: n,
      pageIndex: n - 1,
      plainText: parts.join(''),
      innerHTML: textLayerDiv.innerHTML || '',
      layerClass: textLayerDiv.className || 'textLayer',
      layerStyle: textLayerDiv.getAttribute('style') || '',
      computedScaleFactor: 1,
      computedTotalScaleFactor: 1,
      viewportWidth: pageView && pageView.viewport ? Number(pageView.viewport.width) || 0 : 0,
      viewportHeight: pageView && pageView.viewport ? Number(pageView.viewport.height) || 0 : 0
    });
    return;
  }
  if (!bridgeState.pdfDoc) {
    post('pdfjs-text-layer', {
      pageNumber: n,
      pageIndex: n - 1,
      error: 'text_layer_unavailable'
    });
    return;
  }
  bridgeState.pdfDoc
    .getPage(n)
    .then(function (page) {
      return page.getTextContent();
    })
    .then(function (textContent) {
      var items = Array.isArray(textContent.items) ? textContent.items : [];
      var plainText = items
        .map(function (it) {
          return it && it.str ? String(it.str) : '';
        })
        .join('');
      post('pdfjs-text-layer', {
        pageNumber: n,
        pageIndex: n - 1,
        plainText: plainText,
        innerHTML: '',
        layerClass: 'textLayer',
        layerStyle: '',
        computedScaleFactor: 1,
        computedTotalScaleFactor: 1,
        viewportWidth: 0,
        viewportHeight: 0
      });
    })
    .catch(function () {
      post('pdfjs-text-layer', {
        pageNumber: n,
        pageIndex: n - 1,
        error: 'text_layer_unavailable'
      });
    });
}
export function initializeTextLayer() {
  bridgeState.viewerEventBus.on('pagechanging', function (evt) {
    var n = clamp(Number(evt && evt.pageNumber) || 1, 1, Math.max(1, bridgeState.totalPages || 1));
    bridgeState.currentPageNumber = n;
    updatePageBadge(n);
    updateNavigator();
    emitPageChange(n);
    emitScroll(n);
    emitDimensions(n);
    emitState();
    if (
      normalizeSearchText(bridgeState.searchInput ? bridgeState.searchInput.value : '') &&
      bridgeState.searchResultsTotal > 0
    ) {
      var active =
        bridgeState.activeSearchResultIndex >= 0 &&
        bridgeState.activeSearchResultIndex < bridgeState.searchResults.length
          ? bridgeState.searchResults[bridgeState.activeSearchResultIndex]
          : null;
      if (!active || Number(active.pageNumber) !== n) {
        syncSearchPositionToPage(n);
      }
    }
    if (normalizeSearchText(bridgeState.searchInput ? bridgeState.searchInput.value : '')) {
      queueNativeHighlight(true, 18);
    }
  });
  bridgeState.viewerEventBus.on('textlayerrendered', function (evt) {
    if (!evt) return;
    var n = clamp(Number(evt.pageNumber) || 1, 1, Math.max(1, bridgeState.totalPages || 1));
    if (n !== bridgeState.currentPageNumber) return;
    if (!normalizeSearchText(bridgeState.searchInput ? bridgeState.searchInput.value : '')) return;
    queueNativeHighlight(true, 14);
  });
  bridgeState.viewerEventBus.on('pagesinit', function () {
    applyNativePageFit();
    emitDimensions(bridgeState.currentPageNumber || 1);
    emitState();
  });
  bridgeState.viewerEventBus.on('updatefindmatchescount', function (evt) {
    if (bridgeState.useExactSearch) return;
    var mc = evt && evt.matchesCount ? evt.matchesCount : {};
    setSearchCountLabel(mc.current, mc.total, mc.limit);
  });
  bridgeState.viewerEventBus.on('updatefindcontrolstate', function (evt) {
    if (bridgeState.useExactSearch) return;
    var state = Number(evt && evt.state);
    var mc = evt && evt.matchesCount ? evt.matchesCount : {};
    var findState = (window.pdfjsViewer && window.pdfjsViewer.FindState) || {};
    var NOT_FOUND = typeof findState.NOT_FOUND === 'number' ? findState.NOT_FOUND : 1;
    var PENDING = typeof findState.PENDING === 'number' ? findState.PENDING : 3;
    if (
      state === PENDING &&
      bridgeState.searchCount &&
      String((bridgeState.searchInput && bridgeState.searchInput.value) || '').trim()
    ) {
      bridgeState.searchCount.textContent = '...';
      bridgeState.searchCount.dataset.state = 'pending';
      return;
    }
    setSearchCountLabel(mc.current, mc.total, mc.limit);
    if (!bridgeState.searchCount) return;
    if (
      state === NOT_FOUND &&
      String((bridgeState.searchInput && bridgeState.searchInput.value) || '').trim()
    ) {
      bridgeState.searchCount.textContent = 'No matches';
      bridgeState.searchCount.dataset.state = 'no-results';
    }
  });
  return true;
}
