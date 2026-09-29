import { postPdfCommand } from './continuous-scroll.mjs';
import {
  getDocxContinuousScrollState,
  getWebSnapshotScrollState,
  isDocxContinuousActive,
  syncWebSnapshotInspectorControls
} from './document-navigation.mjs';
import {
  applyFixedDocumentViewportHeight,
  getRawContinuousScrollState,
  goToDocumentSearchResult,
  isRawContinuousActive,
  mountRawContinuousSourceText,
  renderDocumentSearchResults,
  resetDocumentCapabilities,
  runFoliateDocumentSearch,
  setDocumentCapabilities,
  setDocumentNonPageLabel,
  setDocumentPageControl,
  showDocumentChrome,
  syncDocumentCapabilityControls,
  updateDocumentNavigatorThumb
} from './document-search.mjs';
import { debounce } from './document-shell.mjs';
import { documentState } from './document-state.state.mjs';
import { lookupPlainTextToBottom } from './fill-slices.mjs';
import { updateFoliateEpubLocation, updateFoliateFlowLocation } from './foliate-slices.mjs';
import { foliateViewportState } from './foliate-viewport.state.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
export function runWebSnapshotDocumentSearch(query) {
  var q = String(query || '').trim();
  documentState.documentSearchRunSeq += 1;
  var seq = documentState.documentSearchRunSeq;
  documentState.documentSearchResults = [];
  documentState.documentSearchActiveIndex = -1;
  documentState.documentSearchTotalCount = 0;
  documentState.documentSearchPending = !!q;
  renderDocumentSearchResults();
  if (!q) {
    documentState.documentSearchPending = false;
    var clearState = getActiveWebSnapshotState();
    if (
      clearState &&
      window.DocRenderWebSnapshotRenderer &&
      window.DocRenderWebSnapshotRenderer.clearSearch
    ) {
      window.DocRenderWebSnapshotRenderer.clearSearch(clearState);
    }
    renderDocumentSearchResults();
    return;
  }
  if (hoverLayoutState.docSearchMenu) hoverLayoutState.docSearchMenu.hidden = false;
  var state = getActiveWebSnapshotState();
  if (!state || !window.DocRenderWebSnapshotRenderer || !window.DocRenderWebSnapshotRenderer.search) {
    documentState.documentSearchPending = false;
    renderDocumentSearchResults();
    return;
  }
  Promise.resolve(state.ready || state)
    .then(function () {
      if (seq !== documentState.documentSearchRunSeq || !isActiveWebSnapshotDocument()) return;
      var result = window.DocRenderWebSnapshotRenderer.search(state, q) || {};
      if (seq !== documentState.documentSearchRunSeq) return;
      documentState.documentSearchResults = Array.isArray(result.results) ? result.results : [];
      documentState.documentSearchTotalCount = Math.max(
        0,
        Math.floor(Number(result.total) || documentState.documentSearchResults.length || 0)
      );
      documentState.documentSearchActiveIndex = documentState.documentSearchResults.length ? 0 : -1;
      documentState.documentSearchPending = false;
      renderDocumentSearchResults();
      if (documentState.documentSearchResults.length) {
        goToDocumentSearchResult(0);
      }
    })
    .catch(function (e) {
      if (seq !== documentState.documentSearchRunSeq) return;
      console.warn('Web capture search failed:', e);
      documentState.documentSearchPending = false;
      documentState.documentSearchResults = [];
      documentState.documentSearchTotalCount = 0;
      documentState.documentSearchActiveIndex = -1;
      renderDocumentSearchResults();
    });
}
export function setFoliateDocumentCapabilities(source) {
  var book =
    documentState.epubJsBook || (documentState.epubJsRendition && documentState.epubJsRendition.book) || null;
  setDocumentCapabilities({
    source: source || 'foliate',
    toc: book && Array.isArray(book.toc) ? book.toc : [],
    pageList: book && Array.isArray(book.pageList) ? book.pageList : []
  });
}
export function syncDocumentChrome() {
  var active =
    documentState.inputMode === 'doc' || documentState.inputMode === 'pdf' || isRawContinuousActive();
  showDocumentChrome(active);
  syncDocumentCapabilityControls();
  if (!active) return;
  if (isRawContinuousActive()) {
    mountRawContinuousSourceText();
    var rawInfo = getRawContinuousScrollState();
    setDocumentNonPageLabel('');
    if (hoverLayoutState.docNavPrev)
      hoverLayoutState.docNavPrev.disabled = !rawInfo || rawInfo.scrollTop <= 0;
    if (hoverLayoutState.docNavNext)
      hoverLayoutState.docNavNext.disabled = !rawInfo || rawInfo.scrollTop >= rawInfo.maxScroll - 1;
    if (hoverLayoutState.pdfDocControls) hoverLayoutState.pdfDocControls.style.display = 'none';
    syncWebSnapshotInspectorControls();
    updateDocumentNavigatorThumb();
    return;
  }
  applyFixedDocumentViewportHeight(false);
  if (isActiveWebSnapshotDocument()) {
    var webInfo = getWebSnapshotScrollState();
    setDocumentNonPageLabel('');
    if (hoverLayoutState.docNavPrev)
      hoverLayoutState.docNavPrev.disabled = !webInfo || webInfo.scrollTop <= 0;
    if (hoverLayoutState.docNavNext)
      hoverLayoutState.docNavNext.disabled = !webInfo || webInfo.scrollTop >= webInfo.maxScroll - 1;
    if (hoverLayoutState.pdfDocControls) hoverLayoutState.pdfDocControls.style.display = 'none';
    syncWebSnapshotInspectorControls();
    updateDocumentNavigatorThumb();
    return;
  }
  if (documentState.inputMode === 'doc' && documentState.foliateFlowActive) {
    var pendingFlowTotal = Math.floor(Number(documentState.foliateFlowTotalPages) || 0);
    var pendingFlowIdx = Math.max(
      0,
      Math.min(Math.max(0, pendingFlowTotal - 1), Math.floor(Number(documentState.activePageIndex) || 0))
    );
    if (documentState.foliateFullPaginationReady && pendingFlowTotal > 0) {
      setDocumentPageControl(
        'Page ' + (pendingFlowIdx + 1) + ' / ' + pendingFlowTotal,
        pendingFlowIdx,
        pendingFlowTotal,
        true
      );
    } else {
      setDocumentNonPageLabel('Paginating...');
    }
    if (hoverLayoutState.docNavPrev)
      hoverLayoutState.docNavPrev.disabled =
        !documentState.foliateFullPaginationReady || !documentState.epubJsCanGoPrev;
    if (hoverLayoutState.docNavNext)
      hoverLayoutState.docNavNext.disabled =
        !documentState.foliateFullPaginationReady || !documentState.epubJsCanGoNext;
    if (hoverLayoutState.pdfDocControls) hoverLayoutState.pdfDocControls.style.display = 'none';
    syncWebSnapshotInspectorControls();
    updateDocumentNavigatorThumb();
    return;
  }
  if (isActiveEpubDocument()) {
    var epubTotal = Math.floor(Number(documentState.foliateFlowTotalPages) || 0);
    var epubIdx = Math.max(
      0,
      Math.min(Math.max(0, epubTotal - 1), Math.floor(Number(documentState.epubJsCurrentPageNum) || 0))
    );
    if (documentState.foliateFullPaginationReady && epubTotal > 0) {
      setDocumentPageControl('Page ' + (epubIdx + 1) + ' / ' + epubTotal, epubIdx, epubTotal, true);
    } else {
      setDocumentNonPageLabel('Paginating...');
    }
    if (hoverLayoutState.docNavPrev)
      hoverLayoutState.docNavPrev.disabled =
        !documentState.foliateFullPaginationReady || !documentState.epubJsCanGoPrev;
    if (hoverLayoutState.docNavNext)
      hoverLayoutState.docNavNext.disabled =
        !documentState.foliateFullPaginationReady || !documentState.epubJsCanGoNext;
    if (hoverLayoutState.pdfDocControls) hoverLayoutState.pdfDocControls.style.display = 'none';
    syncWebSnapshotInspectorControls();
    updateDocumentNavigatorThumb();
    return;
  }
  if (isActiveFoliateFlowDocument()) {
    var flowTotal = Math.floor(Number(documentState.foliateFlowTotalPages) || 0);
    var flowIdx = Math.max(
      0,
      Math.min(Math.max(0, flowTotal - 1), Math.floor(Number(documentState.activePageIndex) || 0))
    );
    if (documentState.foliateFullPaginationReady && flowTotal > 0) {
      setDocumentPageControl('Page ' + (flowIdx + 1) + ' / ' + flowTotal, flowIdx, flowTotal, true);
    } else {
      setDocumentNonPageLabel('Paginating...');
    }
    if (hoverLayoutState.docNavPrev)
      hoverLayoutState.docNavPrev.disabled =
        !documentState.foliateFullPaginationReady || !documentState.epubJsCanGoPrev;
    if (hoverLayoutState.docNavNext)
      hoverLayoutState.docNavNext.disabled =
        !documentState.foliateFullPaginationReady || !documentState.epubJsCanGoNext;
    if (hoverLayoutState.pdfDocControls) hoverLayoutState.pdfDocControls.style.display = 'none';
    syncWebSnapshotInspectorControls();
    updateDocumentNavigatorThumb();
    return;
  }
  if (isDocxContinuousActive()) {
    var docxScrollInfo = getDocxContinuousScrollState();
    var docxPct = docxScrollInfo ? Math.round(100 * (docxScrollInfo.ratio || 0)) : 0;
    setDocumentNonPageLabel(docxPct + '%');
    if (hoverLayoutState.docNavPrev)
      hoverLayoutState.docNavPrev.disabled = !docxScrollInfo || docxScrollInfo.scrollTop <= 0;
    if (hoverLayoutState.docNavNext)
      hoverLayoutState.docNavNext.disabled =
        !docxScrollInfo || docxScrollInfo.scrollTop >= docxScrollInfo.maxScroll - 1;
    if (hoverLayoutState.pdfDocControls) hoverLayoutState.pdfDocControls.style.display = 'none';
    syncWebSnapshotInspectorControls();
    updateDocumentNavigatorThumb();
    return;
  }
  var total = Math.max(1, documentState.docPages.length || 1);
  var idx = Math.max(0, Math.min(total - 1, documentState.activePageIndex || 0));
  setDocumentPageControl('Page ' + (idx + 1) + ' / ' + total, idx, total, true);
  if (hoverLayoutState.docNavPrev) hoverLayoutState.docNavPrev.disabled = idx <= 0;
  if (hoverLayoutState.docNavNext) hoverLayoutState.docNavNext.disabled = idx >= total - 1;
  if (hoverLayoutState.pdfDocControls)
    hoverLayoutState.pdfDocControls.style.display = documentState.inputMode === 'pdf' ? 'flex' : 'none';
  syncWebSnapshotInspectorControls();
  updateDocumentNavigatorThumb();
}
export function hasActiveDocRenderPage(idx) {
  var pageIndex = Math.max(
    0,
    Math.min(
      (documentState.docPages && documentState.docPages.length ? documentState.docPages.length : 1) - 1,
      idx || 0
    )
  );
  var sourcePage =
    documentState.docSourcePages &&
    (documentState.docSourcePages[pageIndex] || documentState.docSourcePages[0]);
  if (
    sourcePage &&
    window.DocRenderWebSnapshotRenderer &&
    window.DocRenderWebSnapshotRenderer.isSnapshotPage(sourcePage)
  ) {
    return !!documentState.docrenderActive;
  }
  return !!(
    documentState.docrenderActive &&
    documentState.docPageRichHtml &&
    documentState.docPageRichHtml[pageIndex] != null
  );
}
export function getDocRenderSourcePage(idx) {
  var pageIndex = Math.max(0, Math.floor(Number(idx) || 0));
  return (
    (documentState.docSourcePages &&
      (documentState.docSourcePages[pageIndex] || documentState.docSourcePages[0])) ||
    null
  );
}
export function isWebSnapshotSourcePage(page) {
  return !!(
    page &&
    window.DocRenderWebSnapshotRenderer &&
    window.DocRenderWebSnapshotRenderer.isSnapshotPage(page)
  );
}
export function getActiveWebSnapshotState() {
  return hoverLayoutState.sourcePager ? hoverLayoutState.sourcePager.__docrenderWebSnapshotState : null;
}
export function isActiveWebSnapshotDocument() {
  return (
    documentState.inputMode === 'doc' &&
    isWebSnapshotSourcePage(getDocRenderSourcePage(documentState.activePageIndex || 0))
  );
}
export function isActiveEpubDocument() {
  return documentState.currentFileType === 'epub' && !!documentState.epubJsRendition;
}
export function isActiveFoliateFlowDocument() {
  return !!(
    documentState.inputMode === 'doc' &&
    documentState.foliateFlowActive &&
    documentState.epubJsRendition &&
    getFoliateEpubRenderer()
  );
}
export function currentFoliateFileFormatLabel() {
  var name = String((documentState.currentFile && documentState.currentFile.name) || '').toLowerCase();
  if (/\.fb2\.zip$/.test(name) || /\.fbz$/.test(name)) return 'FB2';
  if (/\.azw3$/.test(name)) return 'AZW3';
  if (/\.mobi$/.test(name)) return 'MOBI';
  if (/\.fb2$/.test(name)) return 'FB2';
  if (/\.epub$/.test(name)) return 'EPUB';
  if (/\.cbz$/.test(name)) return 'CBZ';
  return 'Ebook';
}
export function isFlowScrollDocumentActive() {
  return isRawContinuousActive() || isActiveWebSnapshotDocument() || isDocxContinuousActive();
}
export function isFoliatePagedDocumentActive() {
  return isActiveEpubDocument() || isActiveFoliateFlowDocument();
}
export function onWebSnapshotSelectionChange(info) {
  documentState.webSnapshotSelectedText = String((info && info.text) || '');
  if (hoverLayoutState.webInspectorStatus) hoverLayoutState.webInspectorStatus.textContent = '';
}
export function performWebSnapshotLookup() {
  if (!isActiveWebSnapshotDocument()) return;
  var state = getActiveWebSnapshotState();
  if (!state || !window.DocRenderWebSnapshotRenderer) return;
  var selected = String(window.DocRenderWebSnapshotRenderer.getSelectedText(state) || '').trim();
  if (!selected) {
    if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'No text selected.';
    return;
  }
  lookupPlainTextToBottom(selected, {
    emptyStatus: 'No text selected.'
  });
}

// ---- Foliate EPUB integration ----
export function destroyEpubJs() {
  documentState.epubLoadSeq += 1;
  documentState.foliateFlowCanonicalBuildSeq += 1;
  resetDocumentCapabilities();
  documentState.foliateFlowActive = false;
  documentState.foliateFlowBuildingCanonical = false;
  documentState.foliateFlowLabel = 'Document';
  documentState.foliateFlowSections = [];
  documentState.foliateFlowSectionPageCounts = [];
  documentState.foliateFlowSectionStartPages = [];
  documentState.foliateFlowTotalPages = 1;
  documentState.foliateNativeMeasuredSectionPageCounts = [];
  resetFoliateFullPagination(false);
  if (documentState.epubResizeObserver) {
    try {
      documentState.epubResizeObserver.disconnect();
    } catch (_e0) {}
    documentState.epubResizeObserver = null;
  }
  if (documentState.epubJsRendition) {
    try {
      if (typeof documentState.epubJsRendition.close === 'function') documentState.epubJsRendition.close();
      else if (typeof documentState.epubJsRendition.destroy === 'function')
        documentState.epubJsRendition.destroy();
    } catch (e) {}
    try {
      if (documentState.epubJsRendition.parentNode)
        documentState.epubJsRendition.parentNode.removeChild(documentState.epubJsRendition);
    } catch (_e1) {}
    documentState.epubJsRendition = null;
  }
  if (documentState.epubJsBook) {
    try {
      documentState.epubJsBook.destroy();
    } catch (e) {}
    documentState.epubJsBook = null;
  }
  documentState.epubJsCurrentText = '';
  documentState.epubVisibleRange = null;
  documentState.epubJsCanGoPrev = false;
  documentState.epubJsCanGoNext = false;
  documentState.epubJsPageLabel = 'Ebook';
  documentState.epubJsCurrentPageNum = 0;
  documentState.epubJsTotalPages = 1;
  if (documentState.epubJsScrollTimer) {
    clearTimeout(documentState.epubJsScrollTimer);
    documentState.epubJsScrollTimer = null;
  }
}
export function ensureFoliateJs() {
  if (window.customElements && customElements.get('foliate-view')) return Promise.resolve();
  if (!documentState.foliateModulePromise) {
    documentState.foliateModulePromise = import('/static/foliate-js/view.js');
  }
  return documentState.foliateModulePromise;
}
export function getEpubViewportSize() {
  var rect = hoverLayoutState.sourcePager ? hoverLayoutState.sourcePager.getBoundingClientRect() : null;
  var w =
    rect && rect.width
      ? rect.width
      : (hoverLayoutState.sourcePager && hoverLayoutState.sourcePager.clientWidth) || 600;
  var h =
    rect && rect.height
      ? rect.height
      : (hoverLayoutState.sourcePager && hoverLayoutState.sourcePager.clientHeight) ||
        documentState.docViewportHeightPx ||
        500;
  return {
    width: Math.max(320, Math.floor(w)),
    height: Math.max(240, Math.floor(h))
  };
}
export function getFoliateEpubRenderer() {
  return documentState.epubJsRendition && documentState.epubJsRendition.renderer
    ? documentState.epubJsRendition.renderer
    : null;
}
export function configureFoliateViewRenderer(view) {
  var renderer = view && view.renderer ? view.renderer : null;
  if (!view || !renderer) return;
  var size = getEpubViewportSize();
  view.style.display = 'block';
  view.style.width = '100%';
  view.style.height = '100%';
  renderer.setAttribute('flow', 'paginated');
  renderer.setAttribute('margin', '0px');
  renderer.setAttribute('gap', '0%');
  renderer.setAttribute('max-inline-size', size.width + 'px');
  renderer.setAttribute('max-block-size', size.height + 'px');
  renderer.setAttribute('max-column-count', '1');
}
export function configureFoliateEpubRenderer() {
  configureFoliateViewRenderer(documentState.epubJsRendition);
}
export function foliateVisualPageCount(fallbackTotal) {
  var renderer = getFoliateEpubRenderer();
  var raw = renderer ? Number(renderer.pages) : 0;
  var fallback = fallbackTotal != null ? fallbackTotal : documentState.epubJsTotalPages;
  if (!isFinite(raw) || raw <= 0) return Math.max(1, Math.floor(Number(fallback) || 1));
  return Math.max(1, Math.round(raw > 2 ? raw - 2 : raw));
}
export function foliateRendererTextPageCount(renderer, fallbackTotal) {
  var raw = renderer ? Number(renderer.pages) : 0;
  if (!isFinite(raw) || raw <= 0) return Math.max(1, Math.floor(Number(fallbackTotal) || 1));
  return Math.max(1, Math.round(raw > 2 ? raw - 2 : raw));
}
export function foliateVisualPageIndexForCount(totalPages) {
  var renderer = getFoliateEpubRenderer();
  var total = Math.max(1, Math.floor(Number(totalPages) || foliateVisualPageCount()));
  var raw = renderer ? Number(renderer.page) : 1;
  var idx = isFinite(raw) ? Math.round(raw - 1) : documentState.activePageIndex || 0;
  return Math.max(0, Math.min(total - 1, idx));
}
export function foliateVisualPageIndex() {
  return foliateVisualPageIndexForCount(foliateVisualPageCount());
}
export function resetFoliateFullPagination(clearCounts) {
  documentState.foliateFullPaginationSeq += 1;
  documentState.foliateFullPaginationReady = false;
  documentState.foliateFullPaginationRunning = false;
  documentState.foliateFullPaginationError = null;
  if (clearCounts) {
    var count = foliateSectionCount();
    documentState.foliateFlowSectionPageCounts = new Array(count).fill(0);
    documentState.foliateFlowSectionStartPages = new Array(count).fill(0);
    documentState.foliateFlowTotalPages = 1;
    documentState.epubJsTotalPages = 1;
    documentState.docPages = [''];
  }
}
export function nextAnimationFrame() {
  return new Promise(function (resolve) {
    requestAnimationFrame(function () {
      requestAnimationFrame(resolve);
    });
  });
}
export function waitForFoliateAssets(doc) {
  if (!doc || !doc.images || !doc.images.length) return Promise.resolve();
  var waits = Array.prototype.slice.call(doc.images, 0, 24).map(function (img) {
    if (!img || img.complete) return Promise.resolve();
    return new Promise(function (resolve) {
      var done = function () {
        img.removeEventListener('load', done);
        img.removeEventListener('error', done);
        resolve();
      };
      img.addEventListener('load', done, {
        once: true
      });
      img.addEventListener('error', done, {
        once: true
      });
    });
  });
  return Promise.race([
    Promise.all(waits),
    new Promise(function (resolve) {
      setTimeout(resolve, 1200);
    })
  ]).then(function () {});
}
export function waitForFoliateMeasuredPageCount(view, fallbackTotal) {
  var renderer = view && view.renderer ? view.renderer : null;
  if (!renderer) return Promise.resolve(Math.max(1, Math.floor(Number(fallbackTotal) || 1)));
  var lastPages = 0;
  var stable = 0;
  function sample(iter) {
    var contents = renderer.getContents && renderer.getContents();
    var doc = contents && contents.length ? contents[0].doc : null;
    var fontsReady =
      doc && doc.fonts && doc.fonts.ready ? doc.fonts.ready.catch(function () {}) : Promise.resolve();
    return fontsReady
      .then(function () {
        return waitForFoliateAssets(doc);
      })
      .then(nextAnimationFrame)
      .then(function () {
        var pages = foliateRendererTextPageCount(renderer, fallbackTotal);
        if (pages === lastPages) stable += 1;
        else stable = 0;
        lastPages = pages;
        if (stable >= 1 || iter >= 5) return pages;
        return sample(iter + 1);
      });
  }
  return sample(0);
}
export function applyFoliateFullPagination(counts) {
  var sectionCount = foliateSectionCount();
  var cleaned = new Array(sectionCount);
  for (var i = 0; i < sectionCount; i++) {
    cleaned[i] = Math.max(0, Math.floor(Number(counts && counts[i]) || 0));
  }
  documentState.foliateFlowSectionPageCounts = cleaned;
  var total = recomputeFoliateFlowSectionStarts();
  documentState.foliateFlowTotalPages = total;
  documentState.epubJsTotalPages = total;
  documentState.docPages = new Array(total).fill('');
  documentState.foliateFullPaginationReady = true;
  documentState.foliateFullPaginationRunning = false;
  documentState.foliateFullPaginationError = null;
}
export function startFoliateFullPagination(reason) {
  if (!documentState.epubJsBook || !documentState.epubJsRendition || !hoverLayoutState.sourcePager)
    return Promise.resolve(null);
  var sections = Array.isArray(documentState.epubJsBook.sections) ? documentState.epubJsBook.sections : [];
  if (!sections.length) return Promise.resolve(null);
  var loadSeq = documentState.epubLoadSeq;
  var seq = ++documentState.foliateFullPaginationSeq;
  documentState.foliateFullPaginationReady = false;
  documentState.foliateFullPaginationRunning = true;
  documentState.foliateFullPaginationError = null;
  documentState.epubJsPageLabel = 'Paginating...';
  syncDocumentChrome();
  if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Paginating document...';
  return ensureFoliateJs().then(function () {
    if (loadSeq !== documentState.epubLoadSeq || seq !== documentState.foliateFullPaginationSeq) return null;
    var size = getEpubViewportSize();
    var host = document.createElement('div');
    host.style.cssText = [
      'position:fixed',
      'left:-12000px',
      'top:0',
      'width:' + size.width + 'px',
      'height:' + size.height + 'px',
      'overflow:hidden',
      'opacity:0',
      'pointer-events:none',
      'z-index:-1'
    ].join(';');
    var measureView = document.createElement('foliate-view');
    host.appendChild(measureView);
    document.body.appendChild(host);
    var counts = new Array(sections.length).fill(0);
    var linearIndexes = [];
    for (var i = 0; i < sections.length; i++) {
      if (!sections[i] || sections[i].linear === 'no') continue;
      linearIndexes.push(i);
    }
    if (!linearIndexes.length) linearIndexes.push(0);
    function cleanup() {
      try {
        if (typeof measureView.close === 'function') measureView.close();
        else if (typeof measureView.destroy === 'function') measureView.destroy();
      } catch (_cleanupErr) {}
      try {
        if (host.parentNode) host.parentNode.removeChild(host);
      } catch (_removeErr) {}
    }
    return measureView
      .open(documentState.epubJsBook)
      .then(function () {
        configureFoliateViewRenderer(measureView);
        if (!measureView.renderer || measureView.renderer.localName !== 'foliate-paginator') {
          for (var fixedIdx = 0; fixedIdx < linearIndexes.length; fixedIdx++)
            counts[linearIndexes[fixedIdx]] = 1;
          return counts;
        }
        var chain = Promise.resolve();
        linearIndexes.forEach(function (sectionIndex, n) {
          chain = chain.then(function () {
            if (loadSeq !== documentState.epubLoadSeq || seq !== documentState.foliateFullPaginationSeq)
              return null;
            if (hoverLayoutState.statusText)
              hoverLayoutState.statusText.textContent =
                'Paginating document... ' + (n + 1) + ' / ' + linearIndexes.length;
            configureFoliateViewRenderer(measureView);
            return Promise.resolve(
              measureView.renderer.goTo({
                index: sectionIndex,
                anchor: 0
              })
            )
              .then(function () {
                return waitForFoliateMeasuredPageCount(measureView, 1);
              })
              .then(function (pageCount) {
                counts[sectionIndex] = Math.max(1, Math.floor(Number(pageCount) || 1));
                return null;
              });
          });
        });
        return chain.then(function () {
          return counts;
        });
      })
      .then(function (resultCounts) {
        cleanup();
        if (
          !resultCounts ||
          loadSeq !== documentState.epubLoadSeq ||
          seq !== documentState.foliateFullPaginationSeq
        )
          return null;
        applyFoliateFullPagination(resultCounts);
        if (isActiveFoliateFlowDocument())
          updateFoliateFlowLocation(
            (documentState.epubJsRendition && documentState.epubJsRendition.lastLocation) || {}
          );
        else if (isActiveEpubDocument())
          updateFoliateEpubLocation(
            (documentState.epubJsRendition && documentState.epubJsRendition.lastLocation) || {}
          );
        if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Ready.';
        syncDocumentChrome();
        return resultCounts;
      })
      .catch(function (err) {
        cleanup();
        if (loadSeq !== documentState.epubLoadSeq || seq !== documentState.foliateFullPaginationSeq)
          return null;
        documentState.foliateFullPaginationReady = false;
        documentState.foliateFullPaginationRunning = false;
        documentState.foliateFullPaginationError = err;
        documentState.epubJsPageLabel = 'Pagination failed';
        if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Pagination failed.';
        console.warn('Full Foliate pagination failed:', err);
        syncDocumentChrome();
        return null;
      });
  });
}
export function foliateSectionCount() {
  var sections =
    documentState.epubJsBook && Array.isArray(documentState.epubJsBook.sections)
      ? documentState.epubJsBook.sections
      : null;
  return Math.max(1, (sections && sections.length) || documentState.foliateFlowSections.length || 1);
}
export function foliateSectionSize(index) {
  var sections =
    documentState.epubJsBook && Array.isArray(documentState.epubJsBook.sections)
      ? documentState.epubJsBook.sections
      : [];
  var section = sections[Math.max(0, Math.floor(Number(index) || 0))] || null;
  var size = Number(section && section.size);
  return isFinite(size) && size > 0 ? size : 0;
}
export function resetFoliateNativePageCounts() {
  var count = foliateSectionCount();
  documentState.foliateNativeMeasuredSectionPageCounts = new Array(count).fill(0);
  documentState.foliateFlowSectionPageCounts = new Array(count).fill(0);
  documentState.foliateFlowSectionStartPages = new Array(count).fill(0);
  documentState.foliateFlowTotalPages = count;
  documentState.epubJsTotalPages = count;
  documentState.docPages = new Array(count).fill('');
}
export function updateFoliateNativePageEstimates(sectionIndex, sectionPageCount) {
  var sectionCount = foliateSectionCount();
  if (
    !documentState.foliateNativeMeasuredSectionPageCounts ||
    documentState.foliateNativeMeasuredSectionPageCounts.length !== sectionCount
  ) {
    documentState.foliateNativeMeasuredSectionPageCounts = new Array(sectionCount).fill(0);
  }
  var currentSection = Math.max(0, Math.min(sectionCount - 1, Math.floor(Number(sectionIndex) || 0)));
  var currentCount = Math.max(1, Math.floor(Number(sectionPageCount) || 1));
  documentState.foliateNativeMeasuredSectionPageCounts[currentSection] = currentCount;
  var knownSize = 0;
  var knownPages = 0;
  for (var i = 0; i < sectionCount; i++) {
    var measured = Math.floor(Number(documentState.foliateNativeMeasuredSectionPageCounts[i]) || 0);
    var size = foliateSectionSize(i);
    if (measured > 0 && size > 0) {
      knownSize += size;
      knownPages += measured;
    }
  }
  var sizePerPage = knownPages > 0 ? knownSize / knownPages : 0;
  if (!isFinite(sizePerPage) || sizePerPage < 600 || sizePerPage > 6000) sizePerPage = 1500;
  var counts = new Array(sectionCount);
  for (var j = 0; j < sectionCount; j++) {
    var known = Math.floor(Number(documentState.foliateNativeMeasuredSectionPageCounts[j]) || 0);
    if (known > 0) counts[j] = known;
    else {
      var sectionSize = foliateSectionSize(j);
      counts[j] = sectionSize > 0 ? Math.max(1, Math.ceil(sectionSize / sizePerPage)) : 1;
    }
  }
  documentState.foliateFlowSectionPageCounts = counts;
  return recomputeFoliateFlowSectionStarts();
}
export function foliateCurrentSectionIndex() {
  var renderer = getFoliateEpubRenderer();
  var contents = renderer && typeof renderer.getContents === 'function' ? renderer.getContents() : null;
  var idx = contents && contents.length ? Number(contents[0].index) : 0;
  if (!isFinite(idx)) idx = 0;
  var max = Math.max(
    0,
    ((documentState.epubJsBook &&
      documentState.epubJsBook.sections &&
      documentState.epubJsBook.sections.length) ||
      documentState.foliateFlowSections.length ||
      1) - 1
  );
  return Math.max(0, Math.min(max, Math.floor(idx)));
}
export function recomputeFoliateFlowSectionStarts() {
  var sectionCount = Math.max(
    1,
    (documentState.epubJsBook &&
      documentState.epubJsBook.sections &&
      documentState.epubJsBook.sections.length) ||
      documentState.foliateFlowSections.length ||
      1
  );
  var starts = new Array(sectionCount);
  var total = 0;
  for (var i = 0; i < sectionCount; i++) {
    starts[i] = total;
    var count = Math.floor(Number(documentState.foliateFlowSectionPageCounts[i]) || 0);
    total += Math.max(0, count);
  }
  documentState.foliateFlowSectionStartPages = starts;
  documentState.foliateFlowTotalPages = Math.max(1, total);
  return documentState.foliateFlowTotalPages;
}
export function foliateFlowGlobalPageIndex(sectionIndex, sectionPageIndex) {
  recomputeFoliateFlowSectionStarts();
  var s = Math.max(0, Math.floor(Number(sectionIndex) || 0));
  var p = Math.max(0, Math.floor(Number(sectionPageIndex) || 0));
  return Math.max(
    0,
    Math.min(
      documentState.foliateFlowTotalPages - 1,
      (documentState.foliateFlowSectionStartPages[s] || 0) + p
    )
  );
}
export function foliateFlowResolvePageIndex(pageIndex) {
  recomputeFoliateFlowSectionStarts();
  var idx = Math.max(
    0,
    Math.min(documentState.foliateFlowTotalPages - 1, Math.floor(Number(pageIndex) || 0))
  );
  for (var s = documentState.foliateFlowSectionStartPages.length - 1; s >= 0; s--) {
    var start = documentState.foliateFlowSectionStartPages[s] || 0;
    var count = Math.max(0, Math.floor(Number(documentState.foliateFlowSectionPageCounts[s]) || 0));
    if (count <= 0) continue;
    if (idx >= start) {
      return {
        sectionIndex: s,
        sectionPageIndex: Math.max(0, Math.min(count - 1, idx - start)),
        sectionPageCount: count
      };
    }
  }
  return {
    sectionIndex: 0,
    sectionPageIndex: 0,
    sectionPageCount: Math.max(1, foliateVisualPageCount())
  };
}
export function scheduleFoliateEpubResize() {
  if (documentState.epubJsScrollTimer) clearTimeout(documentState.epubJsScrollTimer);
  documentState.epubJsScrollTimer = setTimeout(function () {
    documentState.epubJsScrollTimer = null;
    configureFoliateEpubRenderer();
    if (isActiveFoliateFlowDocument()) {
      resetFoliateFullPagination(true);
      updateFoliateFlowLocation();
      startFoliateFullPagination('resize');
    } else if (isActiveEpubDocument()) {
      resetFoliateFullPagination(true);
      updateFoliateEpubLocation(
        (documentState.epubJsRendition && documentState.epubJsRendition.lastLocation) || {}
      );
      startFoliateFullPagination('resize');
    }
    syncDocumentChrome();
  }, 80);
}
export function observeFoliateEpubResize() {
  if (!hoverLayoutState.sourcePager || typeof ResizeObserver !== 'function') return;
  if (documentState.epubResizeObserver) {
    try {
      documentState.epubResizeObserver.disconnect();
    } catch (_e2) {}
  }
  documentState.epubResizeObserver = new ResizeObserver(scheduleFoliateEpubResize);
  documentState.epubResizeObserver.observe(hoverLayoutState.sourcePager);
}
export function getFoliateVisibleRange() {
  if (
    documentState.epubVisibleRange &&
    documentState.epubVisibleRange.startContainer &&
    documentState.epubVisibleRange.endContainer
  ) {
    return documentState.epubVisibleRange;
  }
  return null;
}
export function epubVisibleCharSlice(textNode, iframeDoc, scrollLeft, pageW) {
  var text = textNode.textContent;
  var len = text.length;
  if (!len) return '';
  var fullRange = iframeDoc.createRange();
  fullRange.selectNode(textNode);
  var crs = fullRange.getClientRects();
  var anyOverlap = false;
  for (var ri = 0; ri < crs.length; ri++) {
    if (crs[ri].right > scrollLeft && crs[ri].left < scrollLeft + pageW) {
      anyOverlap = true;
      break;
    }
  }
  if (!anyOverlap) return '';
  function charRect(idx) {
    var r = iframeDoc.createRange();
    r.setStart(textNode, idx);
    r.setEnd(textNode, idx + 1);
    return r.getBoundingClientRect();
  }
  var lo = 0,
    hi = len - 1,
    mid,
    r,
    lastVis = -1;
  while (lo <= hi) {
    mid = Math.floor((lo + hi) / 2);
    r = charRect(mid);
    if (r && r.left < scrollLeft + pageW) {
      lastVis = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  if (lastVis < 0) return '';
  lo = 0;
  hi = lastVis;
  var firstVis = lastVis + 1;
  while (lo <= hi) {
    mid = Math.floor((lo + hi) / 2);
    r = charRect(mid);
    if (r && r.left >= scrollLeft) {
      firstVis = mid;
      hi = mid - 1;
    } else lo = mid + 1;
  }
  return firstVis <= lastVis ? text.slice(firstVis, lastVis + 1) : '';
}
export function getFoliateViewportClipForDoc(doc) {
  if (
    !doc ||
    !doc.body ||
    !hoverLayoutState.sourcePager ||
    typeof hoverLayoutState.sourcePager.getBoundingClientRect !== 'function'
  )
    return null;
  var win = doc.defaultView || null;
  var frame = null;
  try {
    frame = win && win.frameElement;
  } catch (_frameErr) {
    frame = null;
  }
  if (!frame || typeof frame.getBoundingClientRect !== 'function') return null;
  var pagerRect = hoverLayoutState.sourcePager.getBoundingClientRect();
  var frameRect = frame.getBoundingClientRect();
  if (!pagerRect || !frameRect || frameRect.width <= 1 || frameRect.height <= 1) return null;
  var absLeft = Math.max(pagerRect.left, frameRect.left);
  var absTop = Math.max(pagerRect.top, frameRect.top);
  var absRight = Math.min(pagerRect.right, frameRect.right);
  var absBottom = Math.min(pagerRect.bottom, frameRect.bottom);
  if (absRight <= absLeft + 1 || absBottom <= absTop + 1) return null;
  var contentW = Math.max(1, frame.clientWidth || frameRect.width || 1);
  var contentH = Math.max(1, frame.clientHeight || frameRect.height || 1);
  var scaleX = contentW / Math.max(1, frameRect.width || 1);
  var scaleY = contentH / Math.max(1, frameRect.height || 1);
  var left = Math.max(0, (absLeft - frameRect.left) * scaleX);
  var top = Math.max(0, (absTop - frameRect.top) * scaleY);
  var right = Math.min(contentW, (absRight - frameRect.left) * scaleX);
  var bottom = Math.min(contentH, (absBottom - frameRect.top) * scaleY);
  var width = Math.max(0, right - left);
  var height = Math.max(0, bottom - top);
  if (width <= 1 || height <= 1) return null;
  return {
    left: left,
    top: top,
    right: right,
    bottom: bottom,
    width: width,
    height: height,
    area: width * height,
    frame: frame
  };
}
export function initializeFoliateViewport() {
  foliateViewportState.runSharedDocumentSearch = debounce(function () {
    var q = hoverLayoutState.docSearchField ? String(hoverLayoutState.docSearchField.value || '') : '';
    if (documentState.inputMode === 'pdf') {
      documentState.documentSearchResults = [];
      documentState.documentSearchActiveIndex = -1;
      documentState.documentSearchTotalCount = 0;
      documentState.documentSearchPending = !!String(q || '').trim();
      renderDocumentSearchResults();
      if (hoverLayoutState.docSearchMenu && documentState.documentSearchPending)
        hoverLayoutState.docSearchMenu.hidden = false;
      postPdfCommand('search', {
        query: q
      });
      syncDocumentCapabilityControls();
      return;
    }
    if (isActiveWebSnapshotDocument()) {
      runWebSnapshotDocumentSearch(q);
      syncDocumentCapabilityControls();
      return;
    }
    runFoliateDocumentSearch(q);
    syncDocumentCapabilityControls();
  }, 140);
  return true;
}
