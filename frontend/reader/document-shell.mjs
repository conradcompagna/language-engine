import { normalizePages } from './continuous-scroll.mjs';
import { syncWebSnapshotInspectorControls } from './document-navigation.mjs';
import {
  applyFixedDocumentViewportHeight,
  resetDocumentCapabilities,
  showDocumentChrome
} from './document-search.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { requestMovementLookup } from './document-state.mjs';
import { documentState } from './document-state.state.mjs';
import { triggerUpdate } from './fill-slices.mjs';
import { syncDocumentChrome } from './foliate-viewport.mjs';
import { buildGrammarPopupHtml } from './grammar-popup.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import {
  buildPopupEntryMetaHtmlForEntry,
  filterRenderableFillEntries,
  getRenderableFillLabel
} from './presentation.mjs';
import { renderDictTemplate } from './side-panel.mjs';
import { getPdfPageDimensionsFor, renderSinglePdfPage, resizePagerToFitPdfPage } from './text-offsets.mjs';
import { computePageMaxHeightPx } from './viewport-clamping.mjs';
export function buildHeadwordGrammarLineHtml(posData, udTok) {
  // Kept as a no-op � grammar now lives in the separate grammar popup
  return '';
}
export function hideSeparateGrammarPopup() {
  if (!hoverLayoutState.grammarPopup) return;
  hoverLayoutState.grammarPopup.style.display = 'none';
  hoverLayoutState.grammarPopup.style.left = '0px';
  hoverLayoutState.grammarPopup.style.top = '0px';
  hoverLayoutState.grammarPopup.innerHTML = '';
}
export function setSeparateGrammarPopup(grammarHtml) {
  hideSeparateGrammarPopup();
  if (!hoverLayoutState.grammarPopup || !grammarHtml) return false;
  hoverLayoutState.grammarPopup.innerHTML = grammarHtml;
  hoverLayoutState.grammarPopup.style.display = 'block';
  return true;
}
export function _cloneGrammarPopupOptions(options) {
  var src = options && typeof options === 'object' ? options : {};
  var out = {};
  for (var key in src) {
    if (!Object.prototype.hasOwnProperty.call(src, key)) continue;
    out[key] = src[key];
  }
  return out;
}
export function showSeparateGrammarPopupForToken(posData, udTok, tokenText, tokenEntry, options) {
  hoverLayoutState.latestGrammarPopupState = {
    posData: posData || null,
    udTok: udTok || null,
    tokenText: String(tokenText || ''),
    tokenEntry: tokenEntry || null,
    options: _cloneGrammarPopupOptions(options)
  };
  return setSeparateGrammarPopup(buildGrammarPopupHtml(posData, udTok, tokenText, tokenEntry, options));
}
export function refreshSeparateGrammarPopup() {
  if (
    !hoverLayoutState.grammarPopup ||
    hoverLayoutState.grammarPopup.style.display === 'none' ||
    !hoverLayoutState.latestGrammarPopupState
  )
    return false;
  var state = hoverLayoutState.latestGrammarPopupState;
  return setSeparateGrammarPopup(
    buildGrammarPopupHtml(state.posData, state.udTok, state.tokenText, state.tokenEntry, state.options)
  );
}
export function buildConcatenatedFillEntriesHtml(fillEntries, fallbackHead, options) {
  var fill = filterRenderableFillEntries(fillEntries);
  if (!fill.length) return '';
  var opts = options || {};
  var parts = [];
  for (var i = 0; i < fill.length; i++) {
    var part = fill[i] || {};
    var partHead = getRenderableFillLabel(part, fallbackHead);
    if (!partHead) continue;
    var block = renderDictTemplate(part, partHead, {
      showHead: false,
      showRomanUnknown: true,
      showSensesKnown: true,
      showEmpty: true,
      sensesKey: opts.sensesKey,
      showFilteredNote: !!opts.showFilteredNote,
      showOtherDefsDropdown: !!opts.showOtherDefsDropdown,
      _buildEntryMetaForRow: buildPopupEntryMetaHtmlForEntry,
      forceSenseHead: true
    });
    if (block && block.html) parts.push('<div class="popup-fill-entry">' + block.html + '</div>');
  }
  if (!parts.length) return '';
  return '<div class="popup-fill-list">' + parts.join('<div class="popup-fill-separator"></div>') + '</div>';
}
// ---------------------------------------------------------------------------
// Language-agnostic character detection utilities
// ---------------------------------------------------------------------------
// These replace the former Myanmar-specific functions. They detect whether
// a character/token is "content" (part of the target language text) vs
// punctuation/whitespace. Since the backend handles all language-specific
// filtering, these are intentionally broad.
export function isContentChar(ch) {
  // Disabled: frontend no longer decides what is content vs punctuation.
  // Always return true so no character is excluded from interaction.
  if (!ch) return false;
  return true;
}

// Legacy aliases � many call sites reference these names
export function isMyanmarChar(ch) {
  return isContentChar(ch);
}
export function isPunctToken(tok) {
  // Disabled: frontend no longer classifies tokens as punctuation.
  // Always return false so every token is treated as interactable.
  if (!tok) return true;
  return false;
}

// Legacy alias
export function isMyanmarPunctToken(tok) {
  return isPunctToken(tok);
}
export function hasContentChars(str) {
  // Disabled: always return true so no string is excluded.
  if (!str) return false;
  return true;
}

// Legacy alias
export function hasMyanmarChars(str) {
  return hasContentChars(str);
}

// needsDottedCircle: no longer needed for non-Myanmar languages; always returns false
export function needsDottedCircle(tok) {
  return false;
}
export function debounce(fn, delay) {
  var t = null;
  return function () {
    var args = arguments,
      ctx = this;
    clearTimeout(t);
    t = setTimeout(function () {
      fn.apply(ctx, args);
    }, delay);
  };
}

// ------------------------------
// DOCX Original View (docx-preview) - Frontend-only
// ------------------------------
export // {width,height} from client-side PDF.js

function getDocxFileToken(file) {
  if (!file) return '';
  return [file.name || '', file.size || 0, file.lastModified || 0].join(':');
}
export function sanitizePdfDimension(dim) {
  if (!dim || typeof dim !== 'object') return null;
  var w = Number(dim.width);
  var h = Number(dim.height);
  if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) return null;
  return {
    width: w,
    height: h
  };
}
export function sanitizePdfDimensionList(list) {
  if (!Array.isArray(list)) return [];
  var out = [];
  for (var i = 0; i < list.length; i++) {
    var dim = sanitizePdfDimension(list[i]);
    out.push(
      dim || {
        width: 0,
        height: 0
      }
    );
  }
  return out;
}
export function computeAveragePdfDimension(list) {
  if (!Array.isArray(list) || !list.length) return null;
  var sumW = 0;
  var sumH = 0;
  var n = 0;
  for (var i = 0; i < list.length; i++) {
    var dim = sanitizePdfDimension(list[i]);
    if (!dim) continue;
    sumW += dim.width;
    sumH += dim.height;
    n++;
  }
  if (!n) return null;
  return {
    width: sumW / n,
    height: sumH / n
  };
}
export function ensureDocxPreviewLoaded() {
  return Promise.reject(new Error('DOCX original view is disabled; DOCX uses plain text pagination.'));
}
export function ensurePdfJsLoaded() {
  function loadCssOnce(href, id) {
    if (id && document.getElementById(id)) return;
    var link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    if (id) link.id = id;
    document.head.appendChild(link);
  }
  function loadScriptOnce(src, id) {
    return new Promise(function (resolve, reject) {
      if (id && document.getElementById(id)) return resolve();
      if (src.indexOf('pdf.min.js') >= 0 && window.pdfjsLib) return resolve();
      var s = document.createElement('script');
      s.src = src;
      if (id) s.id = id;
      s.async = true;
      s.onload = function () {
        resolve();
      };
      s.onerror = function () {
        reject(new Error('Failed to load ' + src));
      };
      document.head.appendChild(s);
    });
  }
  loadCssOnce('/static/vendor/pdfjs/pdf_viewer.min.css', 'pdfjs-viewer-css');
  return loadScriptOnce('/static/vendor/pdfjs/pdf.min.js', 'pdfjs-lib').then(function () {
    if (!window.pdfjsLib) {
      throw new Error('pdfjsLib missing after load');
    }
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.js';
  });
}
export function getPdfFileToken(file) {
  if (!file) return '';
  return [file.name || '', file.size || 0, file.lastModified || 0].join(':');
}
export function getPdfJsDocument(file) {
  if (!file) return Promise.reject(new Error('no file'));
  var token = getPdfFileToken(file);
  if (documentShellState.pdfOriginal.doc && documentShellState.pdfOriginal.fileToken === token)
    return Promise.resolve(documentShellState.pdfOriginal.doc);
  if (documentShellState.pdfOriginal.docPromise && documentShellState.pdfOriginal.fileToken === token)
    return documentShellState.pdfOriginal.docPromise;
  documentShellState.pdfOriginal.fileToken = token;
  documentShellState.pdfOriginal.doc = null;
  documentShellState.pdfOriginal.docPromise = file
    .arrayBuffer()
    .then(function (buf) {
      return window.pdfjsLib.getDocument({
        data: buf
      }).promise;
    })
    .then(function (doc) {
      if (documentShellState.pdfOriginal.fileToken !== token) {
        try {
          doc.destroy();
        } catch (_e) {}
        throw new Error('stale PDF load');
      }
      documentShellState.pdfOriginal.doc = doc;
      return doc;
    });
  return documentShellState.pdfOriginal.docPromise;
}

// ---- PDF.js full viewer embedding ----
export // blob: URL for the current in-browser PDF source

function revokePdfBrowserObjectUrl() {
  if (
    documentShellState.pdfBrowserObjectUrl &&
    window.URL &&
    typeof window.URL.revokeObjectURL === 'function'
  ) {
    try {
      window.URL.revokeObjectURL(documentShellState.pdfBrowserObjectUrl);
    } catch (_e) {}
  }
  documentShellState.pdfBrowserObjectUrl = null;
}
export function createPdfBrowserObjectUrl(file) {
  revokePdfBrowserObjectUrl();
  if (!file || !window.URL || typeof window.URL.createObjectURL !== 'function') return '';
  documentShellState.pdfBrowserObjectUrl = window.URL.createObjectURL(file);
  return documentShellState.pdfBrowserObjectUrl;
}
export function buildPdfJsIframeSrc(cacheId, sessionId, browserUrl) {
  var parts = ['session_id=' + encodeURIComponent(String(sessionId || '')), 'chrome=0'];
  if (browserUrl) {
    parts.push('pdf_url=' + encodeURIComponent(String(browserUrl)));
  } else {
    parts.push('cache_id=' + encodeURIComponent(cacheId || ''));
  }
  var qs = '?' + parts.join('&');
  return '/static/pdfjs_iframe_viewer.html' + qs;
}
export function mountPdfJsIframe(cacheId, browserUrl) {
  if (!hoverLayoutState.sourcePager) return;
  hoverLayoutState.sourcePager.innerHTML = '';
  var iframe = document.createElement('iframe');
  iframe.className = 'pdfjs-host-iframe';
  iframe.setAttribute('aria-label', 'PDF viewer');
  iframe.src = buildPdfJsIframeSrc(cacheId, documentShellState.pdfJsSessionId, browserUrl || '');
  iframe.setAttribute('allow', 'clipboard-read; clipboard-write');
  iframe.addEventListener('load', function () {
    documentShellState.pdfSourceInspectorCommanded = null;
    postPdfPageDimsCacheToIframe();
    syncWebSnapshotInspectorControls();
  });
  hoverLayoutState.sourcePager.appendChild(iframe);
  documentShellState.pdfJsIframe = iframe;
}
export function postPdfPageDimsCacheToIframe() {
  if (!documentShellState.pdfJsIframe || !documentShellState.pdfJsIframe.contentWindow) return;
  if (!documentShellState.pdfPageDimensions || !documentShellState.pdfPageDimensions.length) return;
  try {
    documentShellState.pdfJsIframe.contentWindow.postMessage(
      {
        source: 'reader-parent',
        type: 'pdfjs-set-page-dims-cache',
        sessionId: String(documentShellState.pdfJsSessionId),
        pageDims: documentShellState.pdfPageDimensions
      },
      window.location.origin
    );
  } catch (e) {
    // ignore
  }
}
export function loadPdfIntoViewer(cacheId, pages) {
  resetDocumentCapabilities();
  documentState.docPages = normalizePages(pages || []);
  documentState.pdfCacheId = cacheId;
  documentState.activePageIndex = 0;
  documentState.lastLookupPageIndex = -1;
  documentState.pendingPdfLookupPageIndex = -1;
  documentState.pageLookupTextByIndex = {};
  documentState.pdfRawPageTextLoaded = {};
  documentState.pdfCanonicalPageFetches = {};
  documentState.pdfjsTextLayerCache = {};
  documentState.originalLayoutCache = {};
  if (!documentShellState.pdfAveragePageDimensions) {
    documentShellState.pdfAveragePageDimensions = computeAveragePdfDimension(
      documentShellState.pdfPageDimensions
    );
  }
  documentState.inputMode = 'pdf';
  documentState.docPagerIsPaged = true;
  if (hoverLayoutState.sourceText) hoverLayoutState.sourceText.style.display = 'none';
  if (hoverLayoutState.sourcePager) {
    hoverLayoutState.sourcePager.style.display = 'block';
    hoverLayoutState.sourcePager.classList.add('pdfjs-native-mode');
    hoverLayoutState.sourcePager.classList.remove('orig-view-mode');
    hoverLayoutState.sourcePager.innerHTML = '';
    showDocumentChrome(true);
    applyFixedDocumentViewportHeight(true);
  }
  hoverLayoutState.statusText.textContent = 'Loading PDF viewer...';
  documentShellState.pdfJsSessionId += 1;
  documentShellState.pdfSourceInspectorCommanded = null;
  documentState.pdfjsTextLayerCache = {};
  mountPdfJsIframe(cacheId);
  syncDocumentChrome();
  requestAnimationFrame(function () {
    syncDocumentChrome();
    triggerUpdate();
  });
}
export function renderAllPdfPages(pdfDoc) {
  if (!hoverLayoutState.sourcePager) return;
  hoverLayoutState.sourcePager.innerHTML = '';
  documentShellState.pdfJsRenderedPages = {};
  resizePagerToFitPdfPage();
  var container = document.createElement('div');
  container.className = 'pdfjs-pages-container';
  hoverLayoutState.sourcePager.appendChild(container);
  var numPages = pdfDoc.numPages;
  for (var i = 1; i <= numPages; i++) {
    var pageSize = getPdfTargetPageSize(i);
    var pageDiv = document.createElement('div');
    pageDiv.className = 'pdfjs-page';
    pageDiv.dataset.pageNum = String(i);
    applyPdfPageShellSize(pageDiv, pageSize);
    pageDiv.style.background = '#e5e7eb';
    appendPdfPageHeader(pageDiv, i, numPages);
    container.appendChild(pageDiv);
  }

  // Clean up previous observer
  if (documentShellState.pdfJsObserver) {
    documentShellState.pdfJsObserver.disconnect();
    documentShellState.pdfJsObserver = null;
  }

  // Use IntersectionObserver for lazy rendering
  documentShellState.pdfJsObserver = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var pageNum = parseInt(entry.target.dataset.pageNum);
          if (!documentShellState.pdfJsRenderedPages[pageNum]) {
            documentShellState.pdfJsRenderedPages[pageNum] = true;
            renderSinglePdfPage(pdfDoc, pageNum, entry.target);
          }
        }
      });
    },
    {
      root: hoverLayoutState.sourcePager,
      rootMargin: '400px'
    }
  );
  var allPages = container.querySelectorAll('.pdfjs-page');
  for (var j = 0; j < allPages.length; j++) {
    documentShellState.pdfJsObserver.observe(allPages[j]);
  }
}
export function collectPdfPageDimensions(pdfDoc) {
  if (!pdfDoc || !pdfDoc.numPages) return Promise.resolve([]);
  var dims = [];
  var chain = Promise.resolve();
  for (var pageNo = 1; pageNo <= pdfDoc.numPages; pageNo++) {
    (function (n) {
      chain = chain.then(function () {
        return pdfDoc.getPage(n).then(function (page) {
          var viewport =
            page && page.getViewport
              ? page.getViewport({
                  scale: 1.0
                })
              : null;
          dims[n - 1] = sanitizePdfDimension({
            width: viewport && viewport.width,
            height: viewport && viewport.height
          }) || {
            width: 0,
            height: 0
          };
        });
      });
    })(pageNo);
  }
  return chain.then(function () {
    return dims;
  });
}
export function scrollPdfJsSourcePageIntoView(pageIndex) {
  if (!hoverLayoutState.sourcePager || documentShellState.pdfJsIframe) return;
  var pageNum = Math.max(1, Math.floor(Number(pageIndex) || 0) + 1);
  var pageEl = hoverLayoutState.sourcePager.querySelector('.pdfjs-page[data-page-num="' + pageNum + '"]');
  if (!pageEl) return;
  var top = pageEl.offsetTop || 0;
  hoverLayoutState.sourcePager.scrollTo({
    top: top,
    behavior: 'smooth'
  });
}
export function updateActivePdfPageFromSourceScroll() {
  if (!hoverLayoutState.sourcePager || documentState.inputMode !== 'pdf' || documentShellState.pdfJsIframe)
    return;
  var pages = hoverLayoutState.sourcePager.querySelectorAll('.pdfjs-page[data-page-num]');
  if (!pages.length) return;
  var center =
    (hoverLayoutState.sourcePager.scrollTop || 0) + (hoverLayoutState.sourcePager.clientHeight || 0) / 2;
  var best = null;
  var bestDist = Infinity;
  for (var i = 0; i < pages.length; i++) {
    var el = pages[i];
    var mid = (el.offsetTop || 0) + (el.offsetHeight || 0) / 2;
    var dist = Math.abs(center - mid);
    if (dist < bestDist) {
      bestDist = dist;
      best = el;
    }
  }
  if (!best) return;
  var idx = Math.max(0, (parseInt(best.dataset.pageNum || '1', 10) || 1) - 1);
  var maxIdx = Math.max(0, (documentState.docPages.length || 1) - 1);
  idx = Math.min(idx, maxIdx);
  if (idx === documentState.activePageIndex) return;
  documentState.activePageIndex = idx;
  resizePagerToFitPdfPage();
  syncDocumentChrome();
  requestMovementLookup();
}
export function getPdfTargetPageSize(pageNum) {
  var width = 0;
  if (hoverLayoutState.sourcePager) {
    var rect = hoverLayoutState.sourcePager.getBoundingClientRect();
    width = Math.floor(hoverLayoutState.sourcePager.clientWidth || rect.width || 0);
  }
  if (!isFinite(width) || width <= 0) width = 600;
  var dim = getPdfPageDimensionsFor(pageNum || (documentState.activePageIndex || 0) + 1, 0, 0);
  var height =
    dim && dim.width && dim.height ? Math.ceil(width * (dim.height / dim.width)) : computePageMaxHeightPx();
  if (!isFinite(height) || height <= 0) {
    height = Math.ceil(width * 1.414);
  }
  return {
    width: Math.max(1, width),
    height: Math.max(180, Math.floor(height))
  };
}
export function applyPdfPageShellSize(pageDiv, pageSize) {
  if (!pageDiv || !pageSize) return;
  pageDiv.style.width = '100%';
  pageDiv.style.height = pageSize.height + 'px';
  pageDiv.style.minHeight = pageSize.height + 'px';
}
export function appendPdfPageHeader(pageDiv, pageNum, numPages) {
  var pageHeader = document.createElement('div');
  pageHeader.className = 'pdfjs-page-header';
  pageHeader.textContent = 'Page ' + pageNum + ' / ' + numPages;
  pageDiv.appendChild(pageHeader);
}
export function initializeDocumentShell() {
  documentShellState.currentLanguage = String(window.ReaderDefaultLanguage || '')
    .trim()
    .toLowerCase();
  documentShellState.currentTrankitOverride = '';
  documentShellState.DOTTED_CIRCLE = '\u25CC';
  documentShellState.docxOriginal = {
    buf: null,
    // ArrayBuffer of current DOCX
    fileToken: null,
    // cache key for current DOCX
    rendered: false,
    // rendered into sourcePager
    renderSeq: 0 // cancellation token
  };
  documentShellState.pdfOriginal = {
    doc: null,
    // pdfjsLib document
    docPromise: null,
    // in-flight load promise
    fileToken: null,
    // cache key for current file
    renderSeq: 0 // cancellation token
  };
  documentShellState.pdfPageDimensions = []; // [{width,height}] from client-side PDF.js
  documentShellState.pdfAveragePageDimensions = null;
  documentShellState.pdfJsRenderedPages = {}; // pageNum -> true (tracks which pages have been rendered)
  documentShellState.pdfJsObserver = null; // IntersectionObserver for lazy page rendering
  documentShellState.pdfJsIframe = null; // iframe host for actual PDF.js viewer
  documentShellState.pdfJsSessionId = 0; // increments on each PDF load to ignore stale iframe events
  documentShellState.pdfSourceInspectorCommanded = null; // last inspector state sent to the iframe
  documentShellState.pdfBrowserObjectUrl = null;
  return true;
}
