import { continuousScrollState } from './continuous-scroll.state.mjs';
import {
  clearWebSnapshotInspectorSelection,
  getDocxContinuousScrollState,
  isDocxContinuousActive,
  onWebSnapshotScroll,
  openFoliateFlowDocument,
  scrollWebSnapshotBy,
  syncWebSnapshotInspectorControls
} from './document-navigation.mjs';
import {
  applyFixedDocumentViewportHeight,
  computeFixedDocumentViewportHeight,
  leaveRawContinuousMode,
  rememberCurrentPageScroll,
  setDocumentNonPageLabel,
  setDocumentPageControl,
  showDocumentChrome,
  updateDocumentNavigatorThumb
} from './document-search.mjs';
import { loadPdfIntoViewer, scrollPdfJsSourcePageIntoView } from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import {
  buildArtificialPages,
  cancelMovementLookupTimer,
  getDocumentViewportWidth,
  hideRawTextPill,
  normalizeDocumentText,
  requestMovementLookup,
  resetCanonicalDocument,
  setCanonicalDocumentFromPlainPages
} from './document-state.mjs';
import { documentState } from './document-state.state.mjs';
import { triggerUpdate } from './fill-slices.mjs';
import {
  foliateFlowGoToPage,
  foliateFlowStepPage,
  foliateNativeGoToPage,
  foliateNativeStepPage
} from './foliate-slices.mjs';
import {
  destroyEpubJs,
  getActiveWebSnapshotState,
  getDocRenderSourcePage,
  hasActiveDocRenderPage,
  isActiveEpubDocument,
  isActiveFoliateFlowDocument,
  isActiveWebSnapshotDocument,
  isFoliatePagedDocumentActive,
  isWebSnapshotSourcePage,
  onWebSnapshotSelectionChange,
  syncDocumentChrome
} from './foliate-viewport.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { orthographyState } from './orthography.state.mjs';
import { escapeHtml } from './presentation.mjs';
import { resizePagerToFitPdfPage } from './text-offsets.mjs';
import {
  applyGlobalViewportClamp,
  finishFoliateNavigatorPreviewIfIdle,
  requestFoliateNavigatorRender
} from './viewport-clamping.mjs';
export function onDocxContinuousScroll() {
  updateDocumentNavigatorThumb();
  var s = getDocxContinuousScrollState();
  if (hoverLayoutState.docNavPrev) hoverLayoutState.docNavPrev.disabled = !s || s.scrollTop <= 0;
  if (hoverLayoutState.docNavNext)
    hoverLayoutState.docNavNext.disabled = !s || s.scrollTop >= s.maxScroll - 1;
  if (s) setDocumentNonPageLabel(Math.round(100 * (s.ratio || 0)) + '%');
}
export function repeatWebSnapshotSourcePages(sourcePage, count) {
  var total = Math.max(1, Math.floor(Number(count) || 1));
  var out = [];
  for (var i = 0; i < total; i++) {
    out.push(
      Object.assign({}, sourcePage, {
        pageIndex: i
      })
    );
  }
  return out;
}
export function syncWebSnapshotDocumentPages(state, sourcePage, requestedPageIndex, seq) {
  if (
    !state ||
    !sourcePage ||
    seq !== documentState.webSnapshotCanonicalSeq ||
    documentState.inputMode !== 'doc'
  )
    return;
  var key = [
    state.key || '',
    Math.round(Number(state.pageWidth) || 0),
    Math.round(Number(state.pageHeight) || 0),
    Math.round(Number(state.contentHeight) || 0),
    Number(state.pageCount) || 1
  ].join('|');
  if (state.__docPagesKey === key) {
    syncDocumentChrome();
    return;
  }
  state.__docPagesKey = key;
  var requestedNum = Number(requestedPageIndex);
  var pageIndex = Math.max(
    0,
    Math.floor(isFinite(requestedNum) ? requestedNum : documentState.activePageIndex || 0)
  );
  var total = 1;
  documentState.docSourcePages = repeatWebSnapshotSourcePages(sourcePage, total);
  documentState.docPageRichHtml = documentState.docSourcePages.map(function (p) {
    return String((p && p.html) || '');
  });
  documentState.docPages = documentState.docSourcePages.map(function () {
    return '';
  });
  documentState.docText = '';
  documentState.activePageIndex = 0;
  documentState.docrenderPageWidthPx = Math.max(
    320,
    Math.floor(Number(state.pageWidth) || documentState.docrenderPageWidthPx || getDocumentViewportWidth())
  );
  documentState.docrenderPageHeightPx = Math.max(
    320,
    Math.floor(
      Number(state.pageHeight) || documentState.docrenderPageHeightPx || getDocRenderPageSize().height
    )
  );
  documentState.docViewportHeightPx = documentState.docrenderPageHeightPx;
  resetCanonicalDocument();
  syncWebSnapshotInspectorControls();
  syncDocumentChrome();
  if (hoverLayoutState.renderedText && !documentState.webSnapshotSelectedText) {
    hoverLayoutState.renderedText.innerHTML = '';
    hoverLayoutState.renderedText.style.height = '';
    hoverLayoutState.renderedText.style.maxHeight = '';
    hoverLayoutState.renderedText.classList.remove(
      'docrender-active',
      'plain-text-mode',
      'docx-original-view'
    );
  }
  if (hoverLayoutState.statusText)
    hoverLayoutState.statusText.textContent = documentState.webSnapshotInspectorEnabled
      ? 'Select web text.'
      : 'Ready.';
}
export function renderCurrentWebSnapshotPage(sourcePage, idx) {
  if (!hoverLayoutState.sourcePager || !sourcePage || !window.DocRenderWebSnapshotRenderer) return false;
  var existingState = getActiveWebSnapshotState();
  if (existingState && existingState.pageIndex !== Math.max(0, Math.floor(Number(idx) || 0))) {
    clearWebSnapshotInspectorSelection();
  }
  hoverLayoutState.sourcePager.classList.remove(
    'pdfjs-native-mode',
    'docrender-docx-continuous-active',
    'docrender-epub-foliate-active',
    'docrender-foliate-flow-active'
  );
  hoverLayoutState.sourcePager.classList.add('docrender-source-active', 'docrender-websnapshot-active');
  applyFixedDocumentViewportHeight(false);
  var seq = documentState.webSnapshotCanonicalSeq;
  var state = window.DocRenderWebSnapshotRenderer.render(hoverLayoutState.sourcePager, sourcePage, {
    pageIndex: 0,
    pageWidth: documentState.docrenderPageWidthPx || getDocumentViewportWidth(),
    pageHeight: documentState.docrenderPageHeightPx || getDocRenderPageSize().height,
    continuousScroll: true,
    inspectorEnabled: documentState.webSnapshotInspectorEnabled,
    onSelectionChange: onWebSnapshotSelectionChange,
    onScroll: onWebSnapshotScroll,
    onWheel: function (delta) {
      scrollWebSnapshotBy(delta);
    },
    onReady: function (readyState) {
      syncWebSnapshotDocumentPages(readyState, sourcePage, 0, seq);
    },
    onError: function (err) {
      console.error('Web snapshot render failed:', err);
      if (hoverLayoutState.statusText)
        hoverLayoutState.statusText.textContent = 'Web snapshot render failed.';
    }
  });
  syncWebSnapshotInspectorControls();
  if (hoverLayoutState.renderedText && !documentState.webSnapshotSelectedText) {
    hoverLayoutState.renderedText.innerHTML = '';
    hoverLayoutState.renderedText.style.height = '';
    hoverLayoutState.renderedText.style.maxHeight = '';
    hoverLayoutState.renderedText.classList.remove(
      'docrender-active',
      'plain-text-mode',
      'docx-original-view'
    );
  }
  return !!state;
}
export function measureTopDocumentViewportHeight() {
  // The document viewport replaces the textarea, so the textarea's natural
  // rendered height is the best proxy for the available page height.
  var h = 0;
  if (hoverLayoutState.sourceText) {
    var oldDisplay = hoverLayoutState.sourceText.style.display;
    var oldVisibility = hoverLayoutState.sourceText.style.visibility;
    var oldPointerEvents = hoverLayoutState.sourceText.style.pointerEvents;
    hoverLayoutState.sourceText.style.display = 'block';
    hoverLayoutState.sourceText.style.visibility = 'hidden';
    hoverLayoutState.sourceText.style.pointerEvents = 'none';
    var tr = hoverLayoutState.sourceText.getBoundingClientRect();
    h = Math.floor(hoverLayoutState.sourceText.clientHeight || tr.height || 0);
    hoverLayoutState.sourceText.style.display = oldDisplay;
    hoverLayoutState.sourceText.style.visibility = oldVisibility;
    hoverLayoutState.sourceText.style.pointerEvents = oldPointerEvents;
  }
  if (h >= 240) return h;

  // Fallback: measure the input container minus its chrome rows.
  var container = document.getElementById('dropZone') || document.querySelector('.reader-input-container');
  if (container) {
    var cr = container.getBoundingClientRect();
    var topRow = container.querySelector('.reader-control-top');
    var botRow = container.querySelector('.reader-control-bottom');
    var topH = topRow ? topRow.getBoundingClientRect().height || topRow.clientHeight || 0 : 0;
    var botH = botRow ? botRow.getBoundingClientRect().height || botRow.clientHeight || 0 : 0;
    var toolbarH =
      hoverLayoutState.docToolbar && hoverLayoutState.docToolbar.style.display !== 'none'
        ? hoverLayoutState.docToolbar.getBoundingClientRect().height ||
          hoverLayoutState.docToolbar.clientHeight ||
          0
        : 0;
    h = Math.floor((cr.height || container.clientHeight || 0) - topH - botH - toolbarH);
  }
  return Math.max(240, h || 480);
}
export function getDocRenderPageSize() {
  // Width  = sourcePager clientWidth.
  // Height = computeFixedDocumentViewportHeight() with docrenderPageHeightPx
  // zeroed so it computes a fresh value (width*0.86 capped by vh*0.95) rather
  // than echoing back whatever was last stored. Callers must zero
  // docrenderPageHeightPx before calling this.
  var width = getDocumentViewportWidth();
  if (hoverLayoutState.sourcePager) {
    var r = hoverLayoutState.sourcePager.getBoundingClientRect();
    width = Math.max(320, Math.floor(hoverLayoutState.sourcePager.clientWidth || r.width || width || 620));
  }
  var height = Math.max(240, computeFixedDocumentViewportHeight());
  return {
    width: width,
    height: height
  };
}
export function getDocRenderLookupRoot() {
  return hoverLayoutState.renderedText
    ? hoverLayoutState.renderedText.querySelector('.docrender-bottom-page')
    : null;
}
export function parsePxValue(raw) {
  var n = parseFloat(String(raw || '').replace('px', ''));
  return isFinite(n) && n > 0 ? n : 0;
}
export function getFixedPageSizeFromHtml(html) {
  if (!html) return null;
  var tmp = document.createElement('div');
  tmp.innerHTML = String(html || '');
  var el = tmp.querySelector('.pdf-fixed-page, .docrender-pdf-page, [data-page-width][data-page-height]');
  if (!el) return null;
  var w =
    parsePxValue(el.getAttribute('data-page-width')) ||
    parsePxValue(el.style && el.style.width) ||
    parsePxValue(el.getAttribute('width'));
  var h =
    parsePxValue(el.getAttribute('data-page-height')) ||
    parsePxValue(el.style && el.style.height) ||
    parsePxValue(el.getAttribute('height'));
  return w && h
    ? {
        width: w,
        height: h
      }
    : null;
}
export function fitFixedPageToCanonicalViewport(pageEl) {
  if (!pageEl) return;
  var fixed = pageEl.querySelector(
    ':scope > .pdf-fixed-page, :scope > .docrender-pdf-page, .pdf-fixed-page, .docrender-pdf-page'
  );
  if (!fixed) return;
  var w =
    parsePxValue(fixed.getAttribute('data-page-width')) ||
    parsePxValue(fixed.style && fixed.style.width) ||
    fixed.offsetWidth ||
    0;
  var h =
    parsePxValue(fixed.getAttribute('data-page-height')) ||
    parsePxValue(fixed.style && fixed.style.height) ||
    fixed.offsetHeight ||
    0;
  if (!w || !h) return;

  // pageEl is the viewport. The fixed PDF child is scaled and inset inside it.
  // Do not shrink pageEl to the transformed page size, because then a full-width
  // RTL output pane leaves the scaled PDF glued to the left edge.
  pageEl.classList.add('docrender-fixed-page-viewport');
  pageEl.style.setProperty('position', 'relative', 'important');
  pageEl.style.setProperty('width', '100%', 'important');
  pageEl.style.setProperty('height', '100%', 'important');
  pageEl.style.setProperty('overflow', 'hidden', 'important');
  pageEl.style.setProperty('direction', 'ltr', 'important');
  pageEl.style.setProperty('text-align', 'left', 'important');
  pageEl.style.setProperty('unicode-bidi', 'isolate', 'important');
  var rect = pageEl.getBoundingClientRect();
  var targetW = rect.width || pageEl.clientWidth || 0;
  var targetH = rect.height || pageEl.clientHeight || 0;
  if ((!targetW || !targetH) && pageEl.parentElement) {
    var parentRect = pageEl.parentElement.getBoundingClientRect();
    targetW = targetW || parentRect.width || pageEl.parentElement.clientWidth || 0;
    targetH = targetH || parentRect.height || pageEl.parentElement.clientHeight || 0;
  }
  if (!targetW || !targetH) {
    var retryCount = parseInt(pageEl.getAttribute('data-fit-retry-count') || '0', 10) || 0;
    if (retryCount < 2) {
      pageEl.setAttribute('data-fit-retry-count', String(retryCount + 1));
      requestAnimationFrame(function () {
        fitFixedPageToCanonicalViewport(pageEl);
      });
    }
    return;
  }
  pageEl.removeAttribute('data-fit-retry-count');
  var scaleW = targetW / w;
  var scaleH = targetH / h;
  var scale = Math.min(scaleW, scaleH);
  if (!isFinite(scale) || scale <= 0) return;
  var finalW = w * scale;
  var finalH = h * scale;
  var offsetX = Math.max(0, Math.floor((targetW - finalW) / 2));
  var offsetY = 0;
  fixed.style.setProperty('position', 'absolute', 'important');
  fixed.style.setProperty('left', offsetX.toFixed(2) + 'px', 'important');
  fixed.style.setProperty('top', offsetY.toFixed(2) + 'px', 'important');
  fixed.style.setProperty('right', 'auto', 'important');
  fixed.style.setProperty('bottom', 'auto', 'important');
  fixed.style.setProperty('width', w + 'px', 'important');
  fixed.style.setProperty('height', h + 'px', 'important');
  fixed.style.setProperty('transform-origin', '0 0', 'important');
  fixed.style.setProperty('transform', 'scale(' + scale + ')', 'important');
  fixed.style.setProperty('margin', '0', 'important');
  fixed.style.setProperty('direction', 'ltr', 'important');
  fixed.style.setProperty('text-align', 'left', 'important');
  fixed.style.setProperty('unicode-bidi', 'isolate', 'important');
  pageEl.setAttribute('data-fit-target-width', targetW.toFixed(2));
  pageEl.setAttribute('data-fit-target-height', targetH.toFixed(2));
  pageEl.setAttribute('data-fit-page-width', w.toFixed(2));
  pageEl.setAttribute('data-fit-page-height', h.toFixed(2));
  pageEl.setAttribute('data-fit-scale', scale.toFixed(6));
  pageEl.setAttribute('data-fit-offset-x', offsetX.toFixed(2));
  pageEl.setAttribute('data-fit-offset-y', offsetY.toFixed(2));
}
export function renderCurrentDocRenderPage() {
  if (!hoverLayoutState.sourcePager || !hasActiveDocRenderPage(documentState.activePageIndex || 0))
    return false;
  var idx = Math.max(
    0,
    Math.min(documentState.docPageRichHtml.length - 1, documentState.activePageIndex || 0)
  );
  var sourcePage = getDocRenderSourcePage(documentState.activePageIndex || 0);
  if (isWebSnapshotSourcePage(sourcePage)) {
    return renderCurrentWebSnapshotPage(sourcePage, documentState.activePageIndex || 0);
  }
  hoverLayoutState.sourcePager.classList.remove('docrender-websnapshot-active');
  hoverLayoutState.sourcePager.classList.remove(
    'docrender-docx-continuous-active',
    'docrender-epub-foliate-active',
    'docrender-foliate-flow-active'
  );
  hoverLayoutState.sourcePager.classList.remove(
    'pdfjs-native-mode',
    'docrender-docx-continuous-active',
    'docrender-epub-foliate-active',
    'docrender-foliate-flow-active'
  );
  hoverLayoutState.sourcePager.classList.add('docrender-source-active');
  hoverLayoutState.sourcePager.innerHTML = '';
  applyFixedDocumentViewportHeight(false);
  if (hoverLayoutState.renderedText) {
    hoverLayoutState.renderedText.innerHTML = '';
    hoverLayoutState.renderedText.style.height = '';
    hoverLayoutState.renderedText.style.maxHeight = '';
    hoverLayoutState.renderedText.classList.remove(
      'docrender-active',
      'plain-text-mode',
      'docx-original-view'
    );
  }
  var shell = document.createElement('div');
  shell.className = 'reader-page-shell docrender-canonical-shell';
  var inner = document.createElement('div');
  inner.className = 'reader-page-inner docrender-canonical-viewport';
  var topPage = document.createElement('div');
  topPage.className = 'docrender-canonical-page docrender-top-page';
  topPage.innerHTML = documentState.docPageRichHtml[idx] || '';
  inner.appendChild(topPage);
  shell.appendChild(inner);
  hoverLayoutState.sourcePager.appendChild(shell);
  fitFixedPageToCanonicalViewport(topPage);
  return true;
}
export function setDocRenderPages(pages, meta, options) {
  var opts = options || {};
  var src =
    Array.isArray(pages) && pages.length
      ? pages
      : [
          {
            html: '',
            text: ''
          }
        ];
  var isWebSnapshot = isWebSnapshotSourcePage(src[0]);
  documentState.docrenderActive = true;
  documentState.docrenderMeta = meta || {};
  documentState.webSnapshotCanonicalSeq += 1;
  documentState.webSnapshotInspectorEnabled = false;
  documentState.webSnapshotSelectedText = '';
  documentState.docSourcePages = src.slice();
  documentState.docPageRichHtml = src.map(function (p) {
    return String((p && p.html) || '');
  });
  documentState.docPages = src.map(function (p) {
    return String((p && p.text) || '');
  });
  documentState.docPageTextMaps = [];
  documentState.docText = documentState.docPages.join('\n\n');
  if (isWebSnapshot) {
    resetCanonicalDocument();
  } else {
    console.warn(
      'Unsupported DocRender page source; only web snapshots are active here.',
      documentState.docrenderMeta
    );
    resetCanonicalDocument();
  }
  documentState.inputMode = 'doc';
  documentState.docPagerIsPaged = !isWebSnapshot;
  documentState.activePageIndex = Math.max(
    0,
    Math.min(documentState.docPages.length - 1, opts.pageIndex || 0)
  );
  documentState.lastLookupPageIndex = -1;
  documentState.pendingPdfLookupPageIndex = -1;
  documentState.pageLookupTextByIndex = {};
  documentState.docPageScrollTopByIndex = {};
  documentState.docrenderPageWidthPx =
    opts.width || documentState.docrenderPageWidthPx || getDocumentViewportWidth();
  var fixedSize = getFixedPageSizeFromHtml(
    documentState.docPageRichHtml[documentState.activePageIndex] || documentState.docPageRichHtml[0] || ''
  );
  if (fixedSize && fixedSize.width && fixedSize.height) {
    var scale = documentState.docrenderPageWidthPx / fixedSize.width;
    documentState.docrenderPageHeightPx = Math.max(1, Math.ceil(fixedSize.height * scale));
  } else {
    // Flow documents (TXT/HTML/MD/EPUB/DOCX/URL/web snapshot): page height =
    // measured viewport height passed in from the load call, not an aspect ratio.
    documentState.docrenderPageHeightPx = Math.max(
      240,
      Math.floor(opts.height || documentState.docrenderPageHeightPx || getDocRenderPageSize().height)
    );
  }
  documentState.docViewportHeightPx = documentState.docrenderPageHeightPx;
  if (hoverLayoutState.sourceText) {
    hoverLayoutState.sourceText.style.display = 'none';
    hoverLayoutState.sourceText.value = documentState.docText;
  }
  if (documentState.origViewToggle) documentState.origViewToggle.style.display = 'none';
  if (orthographyState.pdfTextSourceGroup) orthographyState.pdfTextSourceGroup.style.display = 'none';
  showDocumentChrome(true);
  applyFixedDocumentViewportHeight(true);
  renderCurrentDocumentPage();
  syncDocumentChrome();
  if (hoverLayoutState.statusText) {
    hoverLayoutState.statusText.textContent = isWebSnapshot
      ? 'Rendering web snapshot...'
      : documentState.docPages.length > 1
        ? 'Ready (' + documentState.docPages.length + ' pages).'
        : 'Ready.';
  }
}
export function loadFileViaDocRender(file) {
  if (!window.DocRenderLoader || !file) return false;
  leaveRawContinuousMode();
  var name = String(file.name || '').toLowerCase();
  if (!/\.(txt|text|html|docx)$/i.test(name)) return false;
  documentState.currentFile = file;
  documentState.currentFileType = name.endsWith('.docx')
    ? 'docx'
    : /\.(txt|text)$/i.test(name)
      ? 'text'
      : 'html';
  documentState.pdfCacheId = null;
  documentShellState.pdfPageDimensions = [];
  documentShellState.pdfAveragePageDimensions = null;
  documentState.docrenderActive = true;
  documentState.docrenderPageHeightPx = 0;
  documentState.docSourcePages = [];
  documentState.docPageRichHtml = [];
  documentState.docPageTextMaps = [];
  documentState.docrenderMeta = {
    fileName: file.name || ''
  };
  documentState.activePageIndex = 0;
  showDocumentChrome(true);
  var size = getDocRenderPageSize();
  if (hoverLayoutState.sourceText) hoverLayoutState.sourceText.style.display = 'none';
  documentState.docrenderPageWidthPx = size.width;
  documentState.docrenderPageHeightPx = size.height;
  applyFixedDocumentViewportHeight(true);
  if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Parsing document...';
  if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
  window.DocRenderLoader.loadFile(file, size)
    .then(function (result) {
      if (result && result.meta && String(result.meta.sourceRenderer || '').toLowerCase() === 'foliate') {
        openFoliateFlowDocument(result, size, {
          fileName: file.name || '',
          fileType: documentState.currentFileType
        });
        return;
      }
      setDocRenderPages(result.sourcePages || result.pages || [], result.meta || {}, {
        width: size.width,
        height: size.height,
        pageIndex: 0,
        canonicalDocument: result.canonicalDocument || result.canonicalDoc || null
      });
    })
    .catch(function (err) {
      console.error('DocRender load failed:', err);
      documentState.docrenderActive = false;
      documentState.webSnapshotInspectorEnabled = false;
      documentState.webSnapshotSelectedText = '';
      documentState.docSourcePages = [];
      documentState.docPageRichHtml = [];
      documentState.docPageTextMaps = [];
      if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Document render failed.';
      if (hoverLayoutState.renderedText)
        hoverLayoutState.renderedText.innerHTML =
          '<div class="reader-output-placeholder">Could not render document: ' +
          escapeHtml(err && err.message ? err.message : 'unknown error') +
          '</div>';
    });
  return true;
}
export function renderCurrentDocumentPage() {
  if (!hoverLayoutState.sourcePager || documentState.inputMode !== 'doc') return;
  if (isActiveEpubDocument()) return; // Foliate owns sourcePager
  if (isActiveFoliateFlowDocument()) return; // Foliate owns sourcePager
  if (hasActiveDocRenderPage(documentState.activePageIndex || 0)) {
    renderCurrentDocRenderPage();
    return;
  }
  if (hoverLayoutState.renderedText) {
    hoverLayoutState.renderedText.classList.remove('docrender-active', 'docx-original-view');
    hoverLayoutState.renderedText.style.height = '';
    hoverLayoutState.renderedText.style.maxHeight = '';
  }
  hoverLayoutState.sourcePager.classList.remove(
    'pdfjs-native-mode',
    'orig-view-mode',
    'docrender-source-active',
    'docrender-websnapshot-active',
    'docrender-docx-continuous-active',
    'docrender-epub-foliate-active',
    'docrender-foliate-flow-active'
  );
  hoverLayoutState.sourcePager.innerHTML = '';
  applyFixedDocumentViewportHeight(false);
  var shell = document.createElement('div');
  shell.className = 'reader-page-shell';
  var inner = document.createElement('div');
  inner.className = 'reader-page-inner';
  var textEl = document.createElement('div');
  textEl.className = 'reader-doc-text';
  textEl.textContent =
    documentState.docPages && documentState.docPages[documentState.activePageIndex]
      ? documentState.docPages[documentState.activePageIndex]
      : '';
  inner.appendChild(textEl);
  shell.appendChild(inner);
  hoverLayoutState.sourcePager.appendChild(shell);
  requestAnimationFrame(function () {
    var saved = documentState.docPageScrollTopByIndex[documentState.activePageIndex || 0] || 0;
    if (inner.scrollHeight > inner.clientHeight + 1) inner.classList.add('page-overflow');
    else inner.classList.remove('page-overflow');
    inner.scrollTop = saved;
  });
}
export function setDocumentPages(pages, options) {
  var opts = options || {};
  leaveRawContinuousMode();
  destroyEpubJs();
  documentState.docrenderActive = false;
  documentState.webSnapshotCanonicalSeq += 1;
  documentState.webSnapshotInspectorEnabled = false;
  documentState.webSnapshotSelectedText = '';
  documentState.docSourcePages = [];
  documentState.docPageRichHtml = [];
  documentState.docPageTextMaps = [];
  documentState.docrenderMeta = null;
  documentState.docrenderPageHeightPx = 0;
  documentState.docrenderPageWidthPx = 0;
  documentState.inputMode = 'doc';
  documentState.docPagerIsPaged = true;
  documentState.docText = normalizeDocumentText(opts.text != null ? opts.text : documentState.docText || '');
  documentState.docPages = normalizePages(pages || ['']);
  documentState.activePageIndex = Math.max(
    0,
    Math.min(documentState.docPages.length - 1, opts.pageIndex || 0)
  );
  try {
    setCanonicalDocumentFromPlainPages(
      documentState.docPages,
      {
        format: 'text',
        parser: 'reader-setDocumentPages'
      },
      {
        pageIndex: documentState.activePageIndex
      }
    );
  } catch (canonErr) {
    console.warn('Canonical plain document conversion failed:', canonErr);
    resetCanonicalDocument();
  }
  documentState.lastLookupPageIndex = -1;
  documentState.pendingPdfLookupPageIndex = -1;
  documentState.pageLookupTextByIndex = {};
  documentState.docPageScrollTopByIndex = {};
  if (hoverLayoutState.sourceText) hoverLayoutState.sourceText.style.display = 'none';
  showDocumentChrome(true);
  applyFixedDocumentViewportHeight(true);
  renderCurrentDocumentPage();
  syncDocumentChrome();
  if (hoverLayoutState.statusText)
    hoverLayoutState.statusText.textContent =
      documentState.docPages.length > 1 ? 'Ready (' + documentState.docPages.length + ' pages).' : 'Ready.';
  if (opts.triggerLookup) triggerUpdate();
}
export function setRawMode() {
  cancelMovementLookupTimer();
  documentState.rawTextFoliateLoadSeq += 1;
  leaveRawContinuousMode();
  destroyEpubJs();
  documentShellState.pdfJsSessionId += 1;
  documentShellState.pdfJsIframe = null;
  documentState.inputMode = 'raw';
  documentState.docText = '';
  documentState.docPagerIsPaged = false;
  documentState.docPages = [];
  documentState.docViewportHeightPx = 0;
  documentState.docPageScrollTopByIndex = {};
  documentState.docrenderActive = false;
  documentState.webSnapshotCanonicalSeq += 1;
  documentState.webSnapshotInspectorEnabled = false;
  documentState.webSnapshotSelectedText = '';
  documentState.docSourcePages = [];
  documentState.docPageRichHtml = [];
  documentState.docPageTextMaps = [];
  documentState.docrenderMeta = null;
  documentState.docrenderPageHeightPx = 0;
  documentState.docrenderPageWidthPx = 0;
  documentState.docrenderPdfRichHtml = [];
  documentState.docrenderPdfText = [];
  documentState.docrenderPdfTextMap = [];
  resetCanonicalDocument();
  documentShellState.pdfPageDimensions = [];
  documentShellState.pdfAveragePageDimensions = null;
  documentState.activePageIndex = 0;
  documentState.lastLookupPageIndex = -1;
  documentState.pendingPdfLookupPageIndex = -1;
  documentState.pageLookupTextByIndex = {};
  documentState.pdfRawPageTextLoaded = {};
  documentState.pdfCanonicalPageFetches = {};
  documentState.pdfjsTextLayerCache = {};
  hideRawTextPill();
  if (orthographyState.pdfTextSourceGroup) orthographyState.pdfTextSourceGroup.style.display = 'none';
  if (hoverLayoutState.sourcePager) {
    hoverLayoutState.sourcePager.classList.remove(
      'orig-view-mode',
      'docrender-source-active',
      'docrender-websnapshot-active',
      'docrender-docx-continuous-active',
      'docrender-epub-foliate-active',
      'docrender-foliate-flow-active'
    );
    hoverLayoutState.sourcePager.style.display = 'none';
    hoverLayoutState.sourcePager.innerHTML = '';
  }
  showDocumentChrome(false);
  if (hoverLayoutState.renderedText) {
    hoverLayoutState.renderedText.classList.remove('docrender-active', 'docx-original-view');
    hoverLayoutState.renderedText.style.height = '';
    hoverLayoutState.renderedText.style.maxHeight = '';
  }
  if (hoverLayoutState.sourceText) {
    hoverLayoutState.sourceText.style.display = 'block';
    hoverLayoutState.sourceText.disabled = false;
    hoverLayoutState.sourceText.readOnly = false;
  }
  applyGlobalViewportClamp(true);
}
export function setDocMode(text, options) {
  var normalized = normalizeDocumentText(text || '');
  documentState.docText = normalized;
  var pages = buildArtificialPages(normalized, documentShellState.currentLanguage);
  setDocumentPages(
    pages,
    Object.assign({}, options || {}, {
      text: normalized
    })
  );
}
export function setPagedMode(pages) {
  if (documentState.currentFileType === 'pdf' && documentState.pdfCacheId) {
    loadPdfIntoViewer(documentState.pdfCacheId, pages);
    return;
  }
  setDocumentPages(pages || [''], {
    text: normalizePages(pages || ['']).join('\n\n')
  });
}
export function normalizePages(pages) {
  var out = [];
  if (!Array.isArray(pages) || !pages.length) return [''];
  for (var i = 0; i < pages.length; i++) {
    var p = pages[i] || '';
    p = p.replace(/\r\n/g, '\n');
    out.push(p);
  }
  return out.length ? out : [''];
}
export function calculateDocLineHeight() {
  if (!hoverLayoutState.sourcePager) return;
  var textEl = hoverLayoutState.sourcePager.querySelector('.reader-doc-text');
  if (!textEl) return;
  // Create a temporary single-line element to measure line height
  var measurer = document.createElement('div');
  measurer.style.cssText = 'position:absolute;visibility:hidden;white-space:pre;';
  measurer.textContent = 'M';
  textEl.appendChild(measurer);
  var h = measurer.getBoundingClientRect().height;
  textEl.removeChild(measurer);
  if (h > 0) documentState.docLineHeight = h;
}
export function applyDocPagerHeight() {
  applyFixedDocumentViewportHeight(false);
}
export function getDocVisibleText() {
  if (!documentState.docPages || !documentState.docPages.length) return '';
  var idx = Math.max(0, Math.min(documentState.docPages.length - 1, documentState.activePageIndex || 0));
  return String(documentState.docPages[idx] || '');
}
export function postPdfCommand(action, payload) {
  if (!documentShellState.pdfJsIframe || !documentShellState.pdfJsIframe.contentWindow) return;
  var msg = {
    source: 'reader-parent',
    type: 'pdfjs-command',
    sessionId: String(documentShellState.pdfJsSessionId),
    action: String(action || '')
  };
  var extra = payload || {};
  for (var k in extra) {
    if (Object.prototype.hasOwnProperty.call(extra, k)) msg[k] = extra[k];
  }
  try {
    documentShellState.pdfJsIframe.contentWindow.postMessage(msg, window.location.origin);
  } catch (e) {
    // ignore stale iframe
  }
}
export function setActiveDocumentPage(index, reason) {
  if (isActiveWebSnapshotDocument()) {
    return;
  }
  if (isActiveEpubDocument()) {
    if (!documentState.foliateFullPaginationReady) return;
    var requestedPage = Math.floor(Number(index) || 0);
    var currentPage = documentState.epubJsCurrentPageNum || 0;
    var requestedDir = requestedPage > currentPage ? 1 : requestedPage < currentPage ? -1 : 0;
    var targetPage = Math.max(0, Math.min(Math.max(0, documentState.epubJsTotalPages - 1), requestedPage));
    var delta = targetPage - (documentState.epubJsCurrentPageNum || 0);
    if (delta === 0 && reason !== 'drag' && !requestedDir) return;
    var navPromise =
      reason !== 'drag' && Math.abs(requestedPage - currentPage) === 1 && requestedDir
        ? foliateNativeStepPage(requestedDir)
        : foliateNativeGoToPage(targetPage);
    Promise.resolve(navPromise)
      .then(function () {
        requestMovementLookup();
      })
      .catch(function (e) {
        console.warn('EPUB page navigation failed:', e);
      });
    return;
  }
  if (isActiveFoliateFlowDocument()) {
    if (!documentState.foliateFullPaginationReady) return;
    var requestedFlowPage = Math.floor(Number(index) || 0);
    var flowDelta = requestedFlowPage - (documentState.activePageIndex || 0);
    if (flowDelta === 0) return;
    var navPromise =
      reason !== 'drag' && Math.abs(flowDelta) === 1
        ? foliateFlowStepPage(flowDelta)
        : foliateFlowGoToPage(requestedFlowPage);
    Promise.resolve(navPromise).then(function () {
      requestMovementLookup();
    });
    return;
  }
  if (isDocxContinuousActive()) {
    return; // docx uses scroll-based navigation
  }
  var total = Math.max(1, documentState.docPages.length || 1);
  var next = Math.max(0, Math.min(total - 1, Math.floor(Number(index) || 0)));
  if (documentState.inputMode === 'pdf') {
    documentState.activePageIndex = next;
    resizePagerToFitPdfPage();
    syncDocumentChrome();
    if (documentShellState.pdfJsIframe) {
      postPdfCommand('goToPage', {
        pageNumber: next + 1,
        reason: reason || 'nav'
      });
    } else {
      scrollPdfJsSourcePageIntoView(next);
    }
    requestMovementLookup();
    return;
  }
  if (documentState.inputMode !== 'doc') return;
  if (next === documentState.activePageIndex) return;
  rememberCurrentPageScroll();
  documentState.activePageIndex = next;
  renderCurrentDocumentPage();
  syncDocumentChrome();
  requestMovementLookup();
}
export function stepDocumentPage(delta) {
  setActiveDocumentPage((documentState.activePageIndex || 0) + (Number(delta) || 0), 'step');
}
export function pageIndexFromNavigatorEvent(ev) {
  if (!hoverLayoutState.docNavTrack || !ev) return documentState.activePageIndex || 0;
  var total = Math.max(1, documentState.docPages.length || 1);
  var rect = hoverLayoutState.docNavTrack.getBoundingClientRect();
  var trackH = Math.max(1, rect.height || 1);
  var thumbH = hoverLayoutState.docNavThumb
    ? hoverLayoutState.docNavThumb.getBoundingClientRect().height ||
      hoverLayoutState.docNavThumb.clientHeight ||
      24
    : 24;
  var usable = Math.max(1, trackH - Math.min(trackH, thumbH));
  var y =
    ev.clientY -
    rect.top -
    (continuousScrollState.docNavDragging ? continuousScrollState.docNavDragOffsetY : 0);
  y = Math.max(0, Math.min(usable, y));
  if (total <= 1 || trackH <= 0) return 0;
  return Math.round((y / usable) * (total - 1));
}
export function webSnapshotRatioFromNavigatorEvent(ev) {
  if (!hoverLayoutState.docNavTrack || !ev) return 0;
  var rect = hoverLayoutState.docNavTrack.getBoundingClientRect();
  var trackH = Math.max(1, rect.height || 1);
  var thumbH = hoverLayoutState.docNavThumb
    ? hoverLayoutState.docNavThumb.getBoundingClientRect().height ||
      hoverLayoutState.docNavThumb.clientHeight ||
      24
    : 24;
  var usable = Math.max(1, trackH - thumbH);
  var y = ev.clientY - rect.top - continuousScrollState.docNavDragOffsetY;
  return Math.max(0, Math.min(1, y / usable));
}
export function previewFoliateNavigatorPage(index) {
  var total = getCompletedFoliateTotalPages();
  if (!total) return;
  var idx = Math.max(0, Math.min(total - 1, Math.floor(Number(index) || 0)));
  continuousScrollState.docNavDragPreviewPageIndex = idx;
  setDocumentPageControl('Page ' + (idx + 1) + ' / ' + total, idx, total, true);
  updateDocumentNavigatorThumb();
  requestFoliateNavigatorRender(idx);
}
export function commitFoliateNavigatorDrag() {
  var idx = continuousScrollState.docNavDragPreviewPageIndex;
  continuousScrollState.docNavFoliateInteractionActive = false;
  if (idx == null || !isFoliatePagedDocumentActive()) {
    updateDocumentNavigatorThumb();
    return;
  }
  requestFoliateNavigatorRender(idx);
  finishFoliateNavigatorPreviewIfIdle();
}
export function cancelFoliateNavigatorDrag() {
  continuousScrollState.docNavFoliateInteractionActive = false;
  continuousScrollState.docNavFoliateRenderTargetPage = null;
  if (continuousScrollState.docNavFoliateRenderFrame) {
    cancelAnimationFrame(continuousScrollState.docNavFoliateRenderFrame);
    continuousScrollState.docNavFoliateRenderFrame = 0;
  }
  continuousScrollState.docNavDragPreviewPageIndex = null;
  syncDocumentChrome();
}
export function currentFoliateGlobalPageIndex() {
  return isActiveFoliateFlowDocument()
    ? documentState.activePageIndex || 0
    : documentState.epubJsCurrentPageNum || 0;
}
export function getCompletedFoliateTotalPages() {
  if (!documentState.foliateFullPaginationReady) return 0;
  var total = Math.floor(Number(documentState.foliateFlowTotalPages) || 0);
  return total > 0 ? total : 0;
}
export function getFoliateNativeProgressRatio() {
  var total = getCompletedFoliateTotalPages();
  if (!total) return 0;
  var idx = Math.max(0, Math.min(total - 1, currentFoliateGlobalPageIndex()));
  return total > 1 ? idx / (total - 1) : 0;
}
export function runFoliatePageHoldStep() {
  if (
    !continuousScrollState.docNavHoldDirection ||
    !isFoliatePagedDocumentActive() ||
    !documentState.foliateFullPaginationReady
  )
    return;
  nativeFoliateStepPage(continuousScrollState.docNavHoldDirection);
}
export function nativeFoliateStepPage(direction) {
  var dir = Number(direction) >= 0 ? 1 : -1;
  var promise = isActiveFoliateFlowDocument() ? foliateFlowStepPage(dir) : foliateNativeStepPage(dir);
  return Promise.resolve(promise)
    .then(function () {
      requestMovementLookup();
      updateDocumentNavigatorThumb();
      return true;
    })
    .catch(function (err) {
      console.warn('Foliate native page step failed:', err);
      return false;
    });
}
export function navigateFoliateNavigatorPage(index) {
  if (!isFoliatePagedDocumentActive() || !documentState.foliateFullPaginationReady)
    return Promise.resolve(false);
  var total = getCompletedFoliateTotalPages();
  if (!total) return Promise.resolve(false);
  var target = Math.max(0, Math.min(total - 1, Math.floor(Number(index) || 0)));
  if (isActiveEpubDocument()) return foliateNativeGoToPage(target);
  if (isActiveFoliateFlowDocument()) return foliateFlowGoToPage(target);
  return Promise.resolve(false);
}
export function initializeContinuousScroll() {
  continuousScrollState.docNavDragging = false;
  continuousScrollState.docNavHoldDirection = 0;
  continuousScrollState.docNavHoldUnit = 'page';
  continuousScrollState.docNavHoldDelayTimer = 0;
  continuousScrollState.docNavHoldRepeatTimer = 0;
  continuousScrollState.docNavHoldDidRepeat = false;
  continuousScrollState.docNavHoldPointerId = null;
  continuousScrollState.docNavDragOffsetY = 0;
  continuousScrollState.docNavDragPreviewPageIndex = null;
  continuousScrollState.docNavNativePreviewRatio = null;
  continuousScrollState.docNavFoliateInteractionActive = false;
  continuousScrollState.docNavFoliateRenderInFlight = false;
  continuousScrollState.docNavFoliateRenderTargetPage = null;
  continuousScrollState.docNavFoliateRenderFrame = 0;
  return true;
}
