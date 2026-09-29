import {
  calculateDocLineHeight,
  getCompletedFoliateTotalPages,
  getFoliateNativeProgressRatio,
  postPdfCommand,
  setActiveDocumentPage
} from './continuous-scroll.mjs';
import { continuousScrollState } from './continuous-scroll.state.mjs';
import { getRawTextMetrics, measureRawTextHeight, setRawTextFoliateDocument } from './document-import.mjs';
import {
  getDocxContinuousScrollState,
  getWebSnapshotScrollState,
  isDocxContinuousActive
} from './document-navigation.mjs';
import { computeAveragePdfDimension, sanitizePdfDimension } from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import {
  countDocumentChars,
  getDocumentViewportWidth,
  hideRawTextPill,
  requestMovementLookup
} from './document-state.mjs';
import { documentState } from './document-state.state.mjs';
import {
  getActiveWebSnapshotState,
  isActiveEpubDocument,
  isActiveFoliateFlowDocument,
  isActiveWebSnapshotDocument,
  isFoliatePagedDocumentActive,
  syncDocumentChrome
} from './foliate-viewport.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { isShowingInitialInputGuidance } from './lookup-progress.mjs';
import { escapeHtml } from './presentation.mjs';
export function getEstimatedCharPxForLanguage(lang) {
  var code = String(lang || documentShellState.currentLanguage || '')
    .trim()
    .toLowerCase();
  if (code === 'zh' || code === 'ja' || code === 'lzh' || code === 'th') return 16;
  if (code === 'ko') return 13;
  if (code === 'ar' || code === 'fa' || code === 'he' || code === 'hbo' || code === 'ur') return 11;
  if (code === 'hi' || code === 'ta' || code === 'bn' || code === 'pa' || code === 'sa') return 12;
  return 8.5;
}
export function estimateArtificialPageAverageHeight(width) {
  if (!documentState.docPages || !documentState.docPages.length) return 0;
  var charPx = getEstimatedCharPxForLanguage(documentShellState.currentLanguage);
  var charsPerLine = Math.max(18, Math.floor(Math.max(220, width - 28) / Math.max(1, charPx)));
  var totalLines = 0;
  var countedPages = 0;
  for (var i = 0; i < documentState.docPages.length; i++) {
    var page = String(documentState.docPages[i] || '');
    if (!page) continue;
    var lines = page.split('\n');
    var visualLines = 0;
    for (var li = 0; li < lines.length; li++) {
      var counted = countDocumentChars(lines[li]);
      visualLines += Math.max(1, Math.ceil(counted / charsPerLine));
    }
    totalLines += Math.max(1, visualLines);
    countedPages++;
  }
  if (!countedPages) return 0;
  var avgLines = totalLines / countedPages;
  return Math.ceil(avgLines * 25.6 + 28);
}
export function estimatePdfPageHeight(width, pageIndex) {
  var idx = Math.max(0, Math.floor(Number(pageIndex) || 0));
  var dim =
    sanitizePdfDimension(documentShellState.pdfPageDimensions && documentShellState.pdfPageDimensions[idx]) ||
    sanitizePdfDimension(documentShellState.pdfAveragePageDimensions) ||
    computeAveragePdfDimension(documentShellState.pdfPageDimensions);
  if (!dim || !dim.width || !dim.height) return 0;
  return Math.ceil(width * (dim.height / dim.width));
}
export function computeFixedDocumentViewportHeight() {
  // Docrender pages are sized to the actual document page (PDF page when
  // dimensions are known, letter portrait otherwise) — no upper clamp.
  if (documentState.docrenderActive && documentState.docrenderPageHeightPx) {
    return Math.max(380, Math.round(documentState.docrenderPageHeightPx));
  }
  // PDF iframe: viewport matches the natural PDF page so the top pane shows
  // the full page without bottom-truncation. Page may scroll within the
  // surrounding container on short screens.
  if (documentState.inputMode === 'pdf') {
    var pdfH = estimatePdfPageHeight(getDocumentViewportWidth(), documentState.activePageIndex || 0);
    if (pdfH && isFinite(pdfH) && pdfH > 0) return Math.max(380, Math.round(pdfH));
  }
  var vh = window.innerHeight || 720;
  var width = getDocumentViewportWidth();
  var desired = 0;
  if (documentState.inputMode === 'doc') {
    desired = estimateArtificialPageAverageHeight(width);
  }
  if (!desired || !isFinite(desired) || desired <= 0) {
    desired = Math.round(width * 0.86);
  }
  var maxByViewport = Math.round(vh * 0.95);
  var maxH = Math.max(500, Math.min(1620, maxByViewport));
  return Math.max(380, Math.min(maxH, Math.round(desired)));
}
export function applyFixedDocumentViewportHeight(force) {
  if (!documentState.docViewportHeightPx || force) {
    documentState.docViewportHeightPx = computeFixedDocumentViewportHeight();
  }
  if (hoverLayoutState.sourcePager) {
    hoverLayoutState.sourcePager.style.height = documentState.docViewportHeightPx + 'px';
    hoverLayoutState.sourcePager.style.maxHeight = documentState.docViewportHeightPx + 'px';
    hoverLayoutState.sourcePager.style.overflow = 'hidden';
  }
  if (hoverLayoutState.docViewportWrap) {
    hoverLayoutState.docViewportWrap.style.minHeight = documentState.docViewportHeightPx + 'px';
  }
}
export function showDocumentChrome(show) {
  var visible = !!show;
  if (hoverLayoutState.docToolbar) hoverLayoutState.docToolbar.style.display = visible ? 'flex' : 'none';
  if (hoverLayoutState.docViewportWrap)
    hoverLayoutState.docViewportWrap.style.display = visible ? 'block' : 'none';
  if (hoverLayoutState.sourcePager) hoverLayoutState.sourcePager.style.display = visible ? 'block' : 'none';
}
export function restoreSourceTextHome() {
  if (!hoverLayoutState.sourceText) return;
  if (
    hoverLayoutState.sourceTextHomeMarker &&
    hoverLayoutState.sourceTextHomeMarker.parentNode &&
    hoverLayoutState.sourceText.parentNode !== hoverLayoutState.sourceTextHomeMarker.parentNode
  ) {
    hoverLayoutState.sourceTextHomeMarker.parentNode.insertBefore(
      hoverLayoutState.sourceText,
      hoverLayoutState.sourceTextHomeMarker.nextSibling
    );
  }
  hoverLayoutState.sourceText.classList.remove('raw-continuous-scroll', 'raw-continuous-readonly');
  hoverLayoutState.sourceText.style.removeProperty('max-height');
  hoverLayoutState.sourceText.style.removeProperty('overflow-y');
  hoverLayoutState.sourceText.disabled = false;
  hoverLayoutState.sourceText.readOnly = false;
}
export function computeFlowDocumentViewportHeight() {
  var vh = window.innerHeight || 720;
  var width = 0;
  if (hoverLayoutState.sourcePager) {
    var pr = hoverLayoutState.sourcePager.getBoundingClientRect();
    width = hoverLayoutState.sourcePager.clientWidth || pr.width || 0;
  }
  if (!width && hoverLayoutState.docViewportWrap) {
    var wr = hoverLayoutState.docViewportWrap.getBoundingClientRect();
    width = Math.max(0, (hoverLayoutState.docViewportWrap.clientWidth || wr.width || 0) - 32);
  }
  if (!width && hoverLayoutState.sourceText) {
    var tr = hoverLayoutState.sourceText.getBoundingClientRect();
    width = hoverLayoutState.sourceText.clientWidth || tr.width || 0;
  }
  width = Math.max(320, Math.floor(width || 620));
  var desired = Math.round(width * 0.86);
  var maxByViewport = Math.round(vh * 0.95);
  var maxH = Math.max(500, Math.min(1620, maxByViewport));
  return Math.max(380, Math.min(maxH, desired));
}
export function measureRawContinuousViewportHeight() {
  return computeFlowDocumentViewportHeight();
}
export function getRawContinuousScroller() {
  return hoverLayoutState.sourcePager || null;
}
export function getRawContinuousTextElement() {
  var scroller = getRawContinuousScroller();
  return scroller ? scroller.querySelector('.reader-doc-text') : null;
}
export function getRawContinuousTextNode() {
  var textEl = getRawContinuousTextElement();
  if (!textEl) return null;
  for (var i = 0; i < textEl.childNodes.length; i++) {
    if (textEl.childNodes[i].nodeType === Node.TEXT_NODE && textEl.childNodes[i].textContent.length > 0) {
      return textEl.childNodes[i];
    }
  }
  return null;
}
export function mountRawContinuousSourceText() {
  if (!hoverLayoutState.sourcePager || !hoverLayoutState.docViewportWrap) return;
  restoreSourceTextHome();
  var height = Math.max(240, Math.round(measureRawContinuousViewportHeight()));
  documentState.docViewportHeightPx = height;
  hoverLayoutState.docViewportWrap.style.minHeight = height + 'px';
  hoverLayoutState.sourcePager.style.display = 'block';
  hoverLayoutState.sourcePager.style.height = height + 'px';
  hoverLayoutState.sourcePager.style.maxHeight = height + 'px';
  hoverLayoutState.sourcePager.style.overflow = 'hidden';
  hoverLayoutState.sourcePager.classList.remove(
    'pdfjs-native-mode',
    'orig-view-mode',
    'docrender-source-active',
    'docrender-websnapshot-active',
    'docrender-docx-continuous-active',
    'docrender-epub-foliate-active',
    'docrender-foliate-flow-active'
  );
  hoverLayoutState.sourcePager.classList.add('raw-continuous-pager');
  if (hoverLayoutState.sourceText) {
    hoverLayoutState.sourceText.style.display = 'none';
    hoverLayoutState.sourceText.disabled = false;
    hoverLayoutState.sourceText.readOnly = false;
  }
  var existing = getRawContinuousTextElement();
  if (!existing || existing.textContent !== documentState.docText) {
    var oldScroll = hoverLayoutState.sourcePager.scrollTop || 0;
    hoverLayoutState.sourcePager.innerHTML = '';
    var textEl = document.createElement('div');
    textEl.className = 'reader-doc-text raw-continuous-text';
    textEl.textContent = documentState.docText || '';
    hoverLayoutState.sourcePager.appendChild(textEl);
    calculateDocLineHeight();
    hoverLayoutState.sourcePager.scrollTop = Math.max(
      0,
      Math.min(
        oldScroll,
        Math.max(0, hoverLayoutState.sourcePager.scrollHeight - hoverLayoutState.sourcePager.clientHeight)
      )
    );
  }
}
export function isRawContinuousActive() {
  return !!(
    documentState.inputMode === 'raw' &&
    hoverLayoutState.sourcePager &&
    (documentState.rawContinuousMode ||
      hoverLayoutState.sourcePager.classList.contains('raw-continuous-pager') ||
      getRawContinuousTextNode())
  );
}
export function getRawContinuousScrollState() {
  var scroller = getRawContinuousScroller();
  if (!scroller) return null;
  var viewportH = Math.max(
    1,
    scroller.clientHeight || scroller.getBoundingClientRect().height || documentState.docViewportHeightPx || 1
  );
  var contentH = Math.max(viewportH, scroller.scrollHeight || viewportH);
  var maxScroll = Math.max(0, contentH - viewportH);
  var scrollTop = Math.max(0, Math.min(maxScroll, scroller.scrollTop || 0));
  return {
    scrollTop: scrollTop,
    maxScroll: maxScroll,
    ratio: maxScroll > 0 ? scrollTop / maxScroll : 0,
    viewportHeight: viewportH,
    contentHeight: contentH,
    lineHeight: Math.max(8, Number(documentState.docLineHeight) || 20)
  };
}
export function onRawContinuousScroll() {
  var info = getRawContinuousScrollState();
  updateDocumentNavigatorThumb();
  if (hoverLayoutState.docNavPrev) hoverLayoutState.docNavPrev.disabled = !info || info.scrollTop <= 0;
  if (hoverLayoutState.docNavNext)
    hoverLayoutState.docNavNext.disabled = !info || info.scrollTop >= info.maxScroll - 1;
}
export function scrollRawContinuousBy(delta) {
  var scroller = getRawContinuousScroller();
  if (!scroller) return null;
  var info = getRawContinuousScrollState();
  if (!info) return null;
  var next = Math.max(0, Math.min(info.maxScroll, info.scrollTop + (Number(delta) || 0)));
  scroller.scrollTop = next;
  onRawContinuousScroll();
  return getRawContinuousScrollState();
}
export function scrollRawContinuousByLine(direction) {
  var info = getRawContinuousScrollState();
  var line = Math.max(8, Number(info && info.lineHeight) || 20);
  return scrollRawContinuousBy((Number(direction) >= 0 ? 1 : -1) * line);
}
export function scrollRawContinuousByViewport(direction) {
  var info = getRawContinuousScrollState();
  var amount = Math.max(
    80,
    Math.round((Number(info && info.viewportHeight) || documentState.docViewportHeightPx || 640) * 0.9)
  );
  return scrollRawContinuousBy((Number(direction) >= 0 ? 1 : -1) * amount);
}
export function scrollRawContinuousToRatio(ratio) {
  var scroller = getRawContinuousScroller();
  if (!scroller) return null;
  var info = getRawContinuousScrollState();
  if (!info) return null;
  var next = Math.max(
    0,
    Math.min(info.maxScroll, info.maxScroll * Math.max(0, Math.min(1, Number(ratio) || 0)))
  );
  scroller.scrollTop = next;
  onRawContinuousScroll();
  return getRawContinuousScrollState();
}
export function leaveRawContinuousMode() {
  documentState.rawContinuousMode = false;
  documentState.rawContinuousForce = false;
  documentState.rawContinuousReadOnly = false;
  restoreSourceTextHome();
  if (hoverLayoutState.sourceText) {
    hoverLayoutState.sourceText.style.display = 'block';
    hoverLayoutState.sourceText.style.removeProperty('height');
  }
  if (hoverLayoutState.sourcePager) {
    hoverLayoutState.sourcePager.classList.remove('raw-continuous-pager');
    hoverLayoutState.sourcePager.style.display = 'none';
    hoverLayoutState.sourcePager.innerHTML = '';
  }
  if (documentState.inputMode === 'raw') showDocumentChrome(false);
}
export function rawTextContentExceedsViewport() {
  if (!hoverLayoutState.sourceText || isShowingInitialInputGuidance()) return false;
  var value = hoverLayoutState.sourceText.value || '';
  if (!value.trim()) return false;
  var metrics = getRawTextMetrics();
  if (!metrics || !metrics.width) return false;
  var viewportH = measureRawContinuousViewportHeight();
  var contentH = hoverLayoutState.sourceText.scrollHeight || measureRawTextHeight(value, metrics);
  return contentH > viewportH + Math.max(2, (metrics.lineHeight || 20) * 0.5);
}
export function syncRawContinuousModeForSourceText(options) {
  var opts = options || {};
  if (!hoverLayoutState.sourceText || documentState.inputMode !== 'raw') return false;
  var wantContinuous =
    !!documentState.rawContinuousForce || documentState.rawContinuousMode || rawTextContentExceedsViewport();
  if (!wantContinuous) {
    if (documentState.rawContinuousMode) {
      leaveRawContinuousMode();
      if (!documentState.currentFile) hideRawTextPill();
    }
    return false;
  }
  setRawTextFoliateDocument(hoverLayoutState.sourceText.value || '', {
    readOnly: false,
    preserveCurrentFile: false,
    fileType: 'text',
    fileName: 'input.txt',
    triggerLookup: !!opts.triggerLookup
  });
  return true;
}
export function rememberCurrentPageScroll() {
  var inner = hoverLayoutState.sourcePager
    ? hoverLayoutState.sourcePager.querySelector('.reader-page-inner')
    : null;
  if (inner && documentState.inputMode === 'doc') {
    documentState.docPageScrollTopByIndex[documentState.activePageIndex || 0] = inner.scrollTop || 0;
  }
}
export function updateDocumentNavigatorThumb() {
  if (!hoverLayoutState.docNavThumb || !hoverLayoutState.docNavTrack) return;
  if (isRawContinuousActive()) {
    var rawInfo = getRawContinuousScrollState();
    var trackHRaw =
      hoverLayoutState.docNavTrack.clientHeight ||
      hoverLayoutState.docNavTrack.getBoundingClientRect().height ||
      0;
    if (!trackHRaw || !rawInfo) return;
    var rawContentH = Math.max(1, Number(rawInfo.contentHeight) || 1);
    var rawViewportH = Math.max(1, Number(rawInfo.viewportHeight) || trackHRaw);
    var rawThumbH = Math.max(24, Math.floor(trackHRaw * Math.min(1, rawViewportH / rawContentH)));
    rawThumbH = Math.min(trackHRaw, rawThumbH);
    var rawUsable = Math.max(0, trackHRaw - rawThumbH);
    var rawRatio = Math.max(0, Math.min(1, Number(rawInfo.ratio) || 0));
    hoverLayoutState.docNavThumb.style.height = rawThumbH + 'px';
    hoverLayoutState.docNavThumb.style.transform = 'translateY(' + Math.round(rawUsable * rawRatio) + 'px)';
    if (hoverLayoutState.docPageNavigator)
      hoverLayoutState.docPageNavigator.classList.add('doc-nav-scroll-mode');
    return;
  }
  if (isActiveWebSnapshotDocument()) {
    var info = getWebSnapshotScrollState();
    var trackHWeb =
      hoverLayoutState.docNavTrack.clientHeight ||
      hoverLayoutState.docNavTrack.getBoundingClientRect().height ||
      0;
    if (!trackHWeb || !info) return;
    var contentH = Math.max(1, Number(info.contentHeight) || 1);
    var viewportH = Math.max(1, Number(info.viewportHeight) || trackHWeb);
    var thumbHWeb = Math.max(24, Math.floor(trackHWeb * Math.min(1, viewportH / contentH)));
    thumbHWeb = Math.min(trackHWeb, thumbHWeb);
    var usableWeb = Math.max(0, trackHWeb - thumbHWeb);
    var ratioWeb = Math.max(0, Math.min(1, Number(info.ratio) || 0));
    hoverLayoutState.docNavThumb.style.height = thumbHWeb + 'px';
    hoverLayoutState.docNavThumb.style.transform = 'translateY(' + Math.round(usableWeb * ratioWeb) + 'px)';
    if (hoverLayoutState.docPageNavigator)
      hoverLayoutState.docPageNavigator.classList.add('doc-nav-scroll-mode');
    return;
  }
  if (isDocxContinuousActive()) {
    var docxInfo = getDocxContinuousScrollState();
    var trackHDocx =
      hoverLayoutState.docNavTrack.clientHeight ||
      hoverLayoutState.docNavTrack.getBoundingClientRect().height ||
      0;
    if (!trackHDocx || !docxInfo) return;
    var docxContentH = Math.max(1, Number(docxInfo.contentHeight) || 1);
    var docxViewH = Math.max(1, Number(docxInfo.viewportHeight) || trackHDocx);
    var docxThumbH = Math.max(24, Math.floor(trackHDocx * Math.min(1, docxViewH / docxContentH)));
    docxThumbH = Math.min(trackHDocx, docxThumbH);
    var docxUsable = Math.max(0, trackHDocx - docxThumbH);
    var docxRatio = Math.max(0, Math.min(1, Number(docxInfo.ratio) || 0));
    hoverLayoutState.docNavThumb.style.height = docxThumbH + 'px';
    hoverLayoutState.docNavThumb.style.transform = 'translateY(' + Math.round(docxUsable * docxRatio) + 'px)';
    if (hoverLayoutState.docPageNavigator)
      hoverLayoutState.docPageNavigator.classList.add('doc-nav-scroll-mode');
    return;
  }
  if (isFoliatePagedDocumentActive()) {
    if (hoverLayoutState.docPageNavigator)
      hoverLayoutState.docPageNavigator.classList.remove('doc-nav-scroll-mode');
    var foliateTotal = getCompletedFoliateTotalPages();
    var foliateTrackH =
      hoverLayoutState.docNavTrack.clientHeight ||
      hoverLayoutState.docNavTrack.getBoundingClientRect().height ||
      0;
    if (!foliateTrackH) return;
    if (!foliateTotal) {
      hoverLayoutState.docNavThumb.style.height = foliateTrackH + 'px';
      hoverLayoutState.docNavThumb.style.transform = 'translateY(0px)';
      return;
    }
    var foliateThumbH =
      foliateTotal > 1 ? Math.max(24, Math.floor(foliateTrackH / foliateTotal)) : foliateTrackH;
    foliateThumbH = Math.min(foliateTrackH, foliateThumbH);
    var foliateUsable = Math.max(0, foliateTrackH - foliateThumbH);
    var foliateRatio =
      continuousScrollState.docNavNativePreviewRatio != null
        ? continuousScrollState.docNavNativePreviewRatio
        : getFoliateNativeProgressRatio();
    foliateRatio = Math.max(0, Math.min(1, Number(foliateRatio) || 0));
    hoverLayoutState.docNavThumb.style.height = foliateThumbH + 'px';
    hoverLayoutState.docNavThumb.style.transform =
      'translateY(' + Math.round(foliateUsable * foliateRatio) + 'px)';
    return;
  }
  if (hoverLayoutState.docPageNavigator)
    hoverLayoutState.docPageNavigator.classList.remove('doc-nav-scroll-mode');
  var total = Math.max(1, documentState.docPages.length || 1);
  var trackH =
    hoverLayoutState.docNavTrack.clientHeight ||
    hoverLayoutState.docNavTrack.getBoundingClientRect().height ||
    0;
  if (!trackH) return;
  var thumbH = total > 1 ? Math.max(24, Math.floor(trackH / total)) : trackH;
  thumbH = Math.min(trackH, thumbH);
  var usable = Math.max(0, trackH - thumbH);
  var navIdx =
    continuousScrollState.docNavDragPreviewPageIndex != null
      ? continuousScrollState.docNavDragPreviewPageIndex
      : documentState.activePageIndex || 0;
  navIdx = Math.max(0, Math.min(total - 1, Math.floor(Number(navIdx) || 0)));
  var ratio = total > 1 ? navIdx / (total - 1) : 0;
  hoverLayoutState.docNavThumb.style.height = thumbH + 'px';
  hoverLayoutState.docNavThumb.style.transform = 'translateY(' + Math.round(usable * ratio) + 'px)';
}
export function flattenDocumentNavItems(items, kind, level, out) {
  out = out || [];
  var arr = Array.isArray(items) ? items : [];
  var baseLevel = Math.max(0, Math.floor(Number(level) || 0));
  for (var i = 0; i < arr.length; i++) {
    var item = arr[i] || {};
    var label = String(item.label || item.title || item.name || '').trim();
    var subitems = Array.isArray(item.subitems) ? item.subitems : Array.isArray(item.items) ? item.items : [];
    if (label || item.href || item.cfi || item.id || isFinite(Number(item.pageIndex))) {
      out.push({
        id: String(item.id || kind + '-' + out.length),
        label: label || 'Item ' + (out.length + 1),
        level: Math.max(0, Math.floor(Number(item.level) || baseLevel)),
        kind: String(item.kind || kind || 'toc'),
        href: item.href != null ? String(item.href) : '',
        cfi: item.cfi != null ? String(item.cfi) : '',
        pageIndex: isFinite(Number(item.pageIndex)) ? Math.max(0, Math.floor(Number(item.pageIndex))) : null
      });
    }
    if (subitems.length) flattenDocumentNavItems(subitems, kind, baseLevel + 1, out);
  }
  return out;
}
export function setDocumentCapabilities(cap) {
  cap = cap || {};
  documentState.documentCapabilities = {
    source: String(cap.source || ''),
    toc: flattenDocumentNavItems(cap.toc || [], 'toc', 0, []),
    pageList: flattenDocumentNavItems(cap.pageList || [], 'pageList', 0, [])
  };
  renderDocumentNavMenu();
  syncDocumentCapabilityControls();
}
export function resetDocumentCapabilities() {
  documentState.documentCapabilities = {
    source: '',
    toc: [],
    pageList: []
  };
  documentState.documentSearchResults = [];
  documentState.documentSearchActiveIndex = -1;
  documentState.documentSearchTotalCount = 0;
  documentState.documentSearchPending = false;
  documentState.documentSearchRunSeq += 1;
  if (hoverLayoutState.docSearchField) hoverLayoutState.docSearchField.value = '';
  if (hoverLayoutState.docSearchCountLabel) hoverLayoutState.docSearchCountLabel.textContent = '0/0';
  hideDocumentNavMenu();
  hideDocumentSearchMenu();
  renderDocumentNavMenu();
  renderDocumentSearchResults();
  syncDocumentCapabilityControls();
}
export function hasDocumentNavItems() {
  return !!(
    documentState.documentCapabilities &&
    documentState.documentCapabilities.toc &&
    documentState.documentCapabilities.toc.length
  );
}
export function setDocumentPageControl(label, pageIndex, totalPages, canNavigate) {
  var total = Math.max(1, Math.floor(Number(totalPages) || 1));
  var idx = Math.max(0, Math.min(total - 1, Math.floor(Number(pageIndex) || 0)));
  if (hoverLayoutState.docPageLabel)
    hoverLayoutState.docPageLabel.textContent = label || 'Page ' + (idx + 1) + ' / ' + total;
  if (!hoverLayoutState.docPageNumberInput) return;
  var enabled = !!canNavigate && total > 0;
  hoverLayoutState.docPageNumberInput.style.display = enabled ? 'inline-block' : 'none';
  hoverLayoutState.docPageNumberInput.disabled = !enabled;
  hoverLayoutState.docPageNumberInput.min = '1';
  hoverLayoutState.docPageNumberInput.max = String(total);
  hoverLayoutState.docPageNumberInput.setAttribute('aria-label', 'Go to page 1 through ' + total);
  hoverLayoutState.docPageNumberInput.title = 'Go to page 1-' + total;
  if (document.activeElement !== hoverLayoutState.docPageNumberInput) {
    hoverLayoutState.docPageNumberInput.value = String(idx + 1);
  }
}
export function setDocumentNonPageLabel(label) {
  if (hoverLayoutState.docPageLabel) hoverLayoutState.docPageLabel.textContent = label || '';
  if (hoverLayoutState.docPageNumberInput) {
    hoverLayoutState.docPageNumberInput.style.display = 'none';
    hoverLayoutState.docPageNumberInput.disabled = true;
    hoverLayoutState.docPageNumberInput.value = '';
  }
}
export function submitDocumentPageNumberInput() {
  if (!hoverLayoutState.docPageNumberInput || hoverLayoutState.docPageNumberInput.disabled) return;
  var total = Math.max(1, Math.floor(Number(hoverLayoutState.docPageNumberInput.max) || 1));
  var rawValue = String(hoverLayoutState.docPageNumberInput.value || '').trim();
  if (!rawValue) {
    syncDocumentChrome();
    return;
  }
  var value = Math.floor(Number(rawValue));
  if (!isFinite(value)) {
    syncDocumentChrome();
    return;
  }
  value = Math.max(1, Math.min(total, value));
  hoverLayoutState.docPageNumberInput.value = String(value);
  setActiveDocumentPage(value - 1, 'page-input');
}
export function isDocumentCapabilityActive() {
  return (
    documentState.inputMode === 'pdf' ||
    isActiveEpubDocument() ||
    isActiveFoliateFlowDocument() ||
    isActiveWebSnapshotDocument()
  );
}
export function isTrankitChunkLookupAvailable() {
  if (hoverLayoutState.TRANKIT_CHUNK_LOOKUP_DISABLED) return false;
  if (documentState.inputMode === 'pdf') return !!documentState.canonicalDoc;
  if (isActiveWebSnapshotDocument()) return true;
  if (isActiveEpubDocument() || isActiveFoliateFlowDocument()) return true;
  return !!(
    documentState.canonicalDoc &&
    documentState.inputMode === 'doc' &&
    !isDocxContinuousActive() &&
    !isRawContinuousActive()
  );
}
export function shouldUseTrankitChunkLookup() {
  if (hoverLayoutState.TRANKIT_CHUNK_LOOKUP_DISABLED) return false;
  return !!(documentState.trankitChunkLookupEnabled && isTrankitChunkLookupAvailable());
}
export function syncTrankitChunkLookupControls() {
  if (hoverLayoutState.TRANKIT_CHUNK_LOOKUP_DISABLED) {
    if (hoverLayoutState.trankitChunkLookupButton) {
      hoverLayoutState.trankitChunkLookupButton.style.display = 'none';
      hoverLayoutState.trankitChunkLookupButton.disabled = true;
      hoverLayoutState.trankitChunkLookupButton.classList.remove('active');
      hoverLayoutState.trankitChunkLookupButton.setAttribute('aria-pressed', 'false');
    }
    return;
  }
  var active = isTrankitChunkLookupAvailable();
  if (hoverLayoutState.trankitChunkLookupButton) {
    hoverLayoutState.trankitChunkLookupButton.style.display = active ? 'inline-flex' : 'none';
    hoverLayoutState.trankitChunkLookupButton.disabled = !active;
    hoverLayoutState.trankitChunkLookupButton.classList.toggle(
      'active',
      !!(active && documentState.trankitChunkLookupEnabled)
    );
    hoverLayoutState.trankitChunkLookupButton.setAttribute(
      'aria-pressed',
      active && documentState.trankitChunkLookupEnabled ? 'true' : 'false'
    );
  }
}
export function syncDocumentCapabilityControls() {
  var active = isDocumentCapabilityActive();
  if (hoverLayoutState.docCapabilityControls)
    hoverLayoutState.docCapabilityControls.style.display = active ? 'flex' : 'none';
  if (hoverLayoutState.docContentsButton) {
    var hasNav = active && hasDocumentNavItems();
    hoverLayoutState.docContentsButton.style.display = hasNav ? 'inline-flex' : 'none';
    hoverLayoutState.docContentsButton.disabled = !hasNav;
    hoverLayoutState.docContentsButton.setAttribute(
      'aria-expanded',
      hoverLayoutState.docContentsMenu && !hoverLayoutState.docContentsMenu.hidden ? 'true' : 'false'
    );
  }
  if (hoverLayoutState.docSearchField) {
    hoverLayoutState.docSearchField.disabled = !active;
    hoverLayoutState.docSearchField.placeholder = 'Search';
  }
  var hasQuery = !!(
    hoverLayoutState.docSearchField && String(hoverLayoutState.docSearchField.value || '').trim()
  );
  if (hoverLayoutState.docSearchPrevButton)
    hoverLayoutState.docSearchPrevButton.disabled =
      !active || (!hasQuery && !documentState.documentSearchResults.length);
  if (hoverLayoutState.docSearchNextButton)
    hoverLayoutState.docSearchNextButton.disabled =
      !active || (!hasQuery && !documentState.documentSearchResults.length);
  if (hoverLayoutState.docSearchClearButton)
    hoverLayoutState.docSearchClearButton.disabled = !active || !hasQuery;
  syncTrankitChunkLookupControls();
}
export function hideDocumentNavMenu() {
  if (hoverLayoutState.docContentsMenu) hoverLayoutState.docContentsMenu.hidden = true;
  if (hoverLayoutState.docContentsButton)
    hoverLayoutState.docContentsButton.setAttribute('aria-expanded', 'false');
}
export function hideDocumentSearchMenu() {
  if (hoverLayoutState.docSearchMenu) hoverLayoutState.docSearchMenu.hidden = true;
}
export function renderDocumentNavMenu() {
  var list = documentState.documentCapabilities.toc || [];
  if (hoverLayoutState.docNavMenuMeta) {
    hoverLayoutState.docNavMenuMeta.textContent = list.length
      ? list.length + ' content entries'
      : 'No contents';
  }
  if (!hoverLayoutState.docNavMenuList) return;
  if (!list.length) {
    hoverLayoutState.docNavMenuList.innerHTML =
      '<div class="doc-nav-item"><span class="doc-nav-item-label">No entries</span></div>';
    return;
  }
  hoverLayoutState.docNavMenuList.innerHTML = list
    .map(function (item) {
      var level = Math.max(0, Math.min(6, Number(item.level) || 0));
      return (
        '<button type="button" class="doc-nav-item" data-doc-nav-id="' +
        escapeHtml(item.id) +
        '" style="padding-left:' +
        (8 + level * 14) +
        'px;">' +
        '<span class="doc-nav-item-label">' +
        escapeHtml(item.label) +
        '</span>' +
        '</button>'
      );
    })
    .join('');
}
export function formatSearchExcerpt(excerpt) {
  if (!excerpt || typeof excerpt !== 'object') return '';
  var pre = escapeHtml(excerpt.pre || '');
  var match = escapeHtml(excerpt.match || '');
  var post = escapeHtml(excerpt.post || '');
  if (!pre && !match && !post) return '';
  return pre + (match ? '<mark>' + match + '</mark>' : '') + post;
}
export function renderDocumentSearchResults() {
  if (hoverLayoutState.docSearchCountLabel) {
    var totalCount = Math.max(
      documentState.documentSearchResults.length,
      Math.floor(Number(documentState.documentSearchTotalCount) || 0)
    );
    if (documentState.documentSearchPending) hoverLayoutState.docSearchCountLabel.textContent = '...';
    else if (documentState.documentSearchResults.length && documentState.documentSearchActiveIndex >= 0) {
      var activeItem = documentState.documentSearchResults[documentState.documentSearchActiveIndex] || null;
      var activeNumber =
        activeItem && isFinite(Number(activeItem.resultIndex))
          ? Number(activeItem.resultIndex) + 1
          : documentState.documentSearchActiveIndex + 1;
      hoverLayoutState.docSearchCountLabel.textContent = activeNumber + '/' + totalCount;
    } else {
      hoverLayoutState.docSearchCountLabel.textContent = totalCount ? '0/' + totalCount : '0/0';
    }
  }
  if (hoverLayoutState.docSearchMenuMeta) {
    var menuTotalCount = Math.max(
      documentState.documentSearchResults.length,
      Math.floor(Number(documentState.documentSearchTotalCount) || 0)
    );
    hoverLayoutState.docSearchMenuMeta.textContent = documentState.documentSearchPending
      ? 'Searching...'
      : menuTotalCount
        ? menuTotalCount + ' matches'
        : 'No matches';
  }
  if (!hoverLayoutState.docSearchMenuList) return;
  if (!documentState.documentSearchResults.length) {
    hoverLayoutState.docSearchMenuList.innerHTML =
      '<div class="doc-nav-item"><span class="doc-nav-item-label">' +
      (documentState.documentSearchPending ? 'Searching...' : 'No matches') +
      '</span></div>';
    return;
  }
  hoverLayoutState.docSearchMenuList.innerHTML = documentState.documentSearchResults
    .slice(0, 120)
    .map(function (item, idx) {
      var excerpt = formatSearchExcerpt(item.excerpt);
      return (
        '<button type="button" class="doc-nav-item' +
        (idx === documentState.documentSearchActiveIndex ? ' active' : '') +
        '" data-doc-search-index="' +
        idx +
        '">' +
        (excerpt
          ? '<span class="doc-nav-item-excerpt doc-search-result-excerpt">' + excerpt + '</span>'
          : '<span class="doc-nav-item-label">' + escapeHtml(item.label || 'Result') + '</span>') +
        '</button>'
      );
    })
    .join('');
}
export function goToDocumentNavItem(item) {
  if (!item) return;
  if (documentState.inputMode === 'pdf') {
    postPdfCommand('goToOutlineItem', {
      id: item.id
    });
    hideDocumentNavMenu();
    return;
  }
  if (documentState.epubJsRendition && typeof documentState.epubJsRendition.goTo === 'function') {
    Promise.resolve(documentState.epubJsRendition.goTo(item.href || item.cfi || item.id))
      .then(function () {
        requestMovementLookup();
        syncDocumentChrome();
      })
      .catch(function (e) {
        console.warn('Document navigation failed:', e);
      });
  }
  hideDocumentNavMenu();
}
export function goToDocumentSearchResult(index) {
  var idx = Math.max(
    0,
    Math.min(documentState.documentSearchResults.length - 1, Math.floor(Number(index) || 0))
  );
  var item = documentState.documentSearchResults[idx];
  if (!item) return;
  documentState.documentSearchActiveIndex = idx;
  renderDocumentSearchResults();
  if (documentState.inputMode === 'pdf') {
    postPdfCommand('goToSearchResult', {
      resultIndex: item.resultIndex != null ? item.resultIndex : idx
    });
    return;
  }
  if (isActiveWebSnapshotDocument()) {
    var state = getActiveWebSnapshotState();
    if (
      state &&
      window.DocRenderWebSnapshotRenderer &&
      window.DocRenderWebSnapshotRenderer.goToSearchResult
    ) {
      window.DocRenderWebSnapshotRenderer.goToSearchResult(
        state,
        item.resultIndex != null ? item.resultIndex : idx
      );
      updateDocumentNavigatorThumb();
      syncDocumentChrome();
    }
    return;
  }
  if (documentState.epubJsRendition && typeof documentState.epubJsRendition.goTo === 'function') {
    Promise.resolve(documentState.epubJsRendition.goTo(item.cfi))
      .then(function () {
        requestMovementLookup();
        syncDocumentChrome();
      })
      .catch(function (e) {
        console.warn('Search navigation failed:', e);
      });
  }
}
export function stepDocumentSearch(direction) {
  if (documentState.inputMode === 'pdf') {
    postPdfCommand(Number(direction) < 0 ? 'searchPrev' : 'searchNext');
    return;
  }
  if (!documentState.documentSearchResults.length) return;
  var next = documentState.documentSearchActiveIndex;
  if (next < 0) next = Number(direction) < 0 ? documentState.documentSearchResults.length - 1 : 0;
  else
    next =
      (next + (Number(direction) < 0 ? -1 : 1) + documentState.documentSearchResults.length) %
      documentState.documentSearchResults.length;
  goToDocumentSearchResult(next);
}
export function clearDocumentSearch() {
  documentState.documentSearchRunSeq += 1;
  documentState.documentSearchResults = [];
  documentState.documentSearchActiveIndex = -1;
  documentState.documentSearchTotalCount = 0;
  documentState.documentSearchPending = false;
  if (hoverLayoutState.docSearchField) hoverLayoutState.docSearchField.value = '';
  if (documentState.inputMode === 'pdf') postPdfCommand('searchClear');
  if (isActiveWebSnapshotDocument()) {
    var state = getActiveWebSnapshotState();
    if (state && window.DocRenderWebSnapshotRenderer && window.DocRenderWebSnapshotRenderer.clearSearch) {
      window.DocRenderWebSnapshotRenderer.clearSearch(state);
    }
  }
  if (documentState.epubJsRendition && typeof documentState.epubJsRendition.clearSearch === 'function') {
    try {
      documentState.epubJsRendition.clearSearch();
    } catch (_clearErr) {}
  }
  hideDocumentSearchMenu();
  renderDocumentSearchResults();
  syncDocumentCapabilityControls();
}
export function runFoliateDocumentSearch(query) {
  var q = String(query || '').trim();
  documentState.documentSearchRunSeq += 1;
  var seq = documentState.documentSearchRunSeq;
  documentState.documentSearchResults = [];
  documentState.documentSearchActiveIndex = -1;
  documentState.documentSearchTotalCount = 0;
  documentState.documentSearchPending = !!q;
  if (documentState.epubJsRendition && typeof documentState.epubJsRendition.clearSearch === 'function') {
    try {
      documentState.epubJsRendition.clearSearch();
    } catch (_clearErr) {}
  }
  renderDocumentSearchResults();
  if (!q || !documentState.epubJsRendition || typeof documentState.epubJsRendition.search !== 'function') {
    documentState.documentSearchPending = false;
    renderDocumentSearchResults();
    return;
  }
  if (hoverLayoutState.docSearchMenu) hoverLayoutState.docSearchMenu.hidden = false;
  (async function () {
    try {
      for await (var result of documentState.epubJsRendition.search({
        query: q,
        matchCase: false,
        matchDiacritics: false,
        matchWholeWords: false
      })) {
        if (seq !== documentState.documentSearchRunSeq) return;
        if (result === 'done') break;
        if (result && Array.isArray(result.subitems)) {
          var label = String(result.label || '').trim();
          result.subitems.forEach(function (subitem) {
            if (!subitem || !subitem.cfi) return;
            documentState.documentSearchResults.push({
              cfi: String(subitem.cfi),
              label: label || 'Match ' + (documentState.documentSearchResults.length + 1),
              excerpt: subitem.excerpt || null
            });
          });
        } else if (result && result.cfi) {
          documentState.documentSearchResults.push({
            cfi: String(result.cfi),
            label: 'Match ' + (documentState.documentSearchResults.length + 1),
            excerpt: result.excerpt || null
          });
        }
        renderDocumentSearchResults();
      }
    } catch (e) {
      console.warn('Foliate search failed:', e);
    } finally {
      if (seq === documentState.documentSearchRunSeq) {
        documentState.documentSearchPending = false;
        documentState.documentSearchTotalCount = documentState.documentSearchResults.length;
        documentState.documentSearchActiveIndex = -1;
        renderDocumentSearchResults();
      }
    }
  })();
}
