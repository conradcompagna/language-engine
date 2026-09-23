import { nativeFoliateStepPage, onDocxContinuousScroll, postPdfCommand } from './continuous-scroll.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { updateRenderedOutputBackground } from './document-import.mjs';
import { documentNavigationState } from './document-navigation.state.mjs';
import {
  applyFixedDocumentViewportHeight,
  shouldUseTrankitChunkLookup,
  showDocumentChrome,
  syncTrankitChunkLookupControls,
  updateDocumentNavigatorThumb
} from './document-search.mjs';
import { debounce } from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import {
  ensureCanonicalReaderController,
  requestMovementLookup,
  resetCanonicalDocument,
  setCanonicalDocument
} from './document-state.mjs';
import { documentState } from './document-state.state.mjs';
import { triggerUpdate } from './fill-slices.mjs';
import {
  buildEpubCanonicalPage,
  buildFoliateRectSliceState,
  currentFoliateFlowFormatLabel,
  extractEpubVisibleText,
  initFoliateEpub,
  makeFoliateFlowBook,
  normalizeFoliateFlowSections,
  setEpubCanonicalPage,
  updateFoliateEpubLocation,
  updateFoliateFlowLocation
} from './foliate-slices.mjs';
import {
  configureFoliateViewRenderer,
  currentFoliateFileFormatLabel,
  destroyEpubJs,
  ensureFoliateJs,
  foliateCurrentSectionIndex,
  foliateVisualPageIndex,
  getActiveWebSnapshotState,
  getFoliateEpubRenderer,
  isActiveEpubDocument,
  isActiveFoliateFlowDocument,
  isActiveWebSnapshotDocument,
  observeFoliateEpubResize,
  onWebSnapshotSelectionChange,
  resetFoliateFullPagination,
  setFoliateDocumentCapabilities,
  startFoliateFullPagination
} from './foliate-viewport.mjs';
import { clearChunkHighlight } from './gloss-requests.mjs';
import { stripNativeTitleTooltips } from './hover-layout.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { lookupProgressState } from './lookup-progress.state.mjs';
import { setLatestUdOverlay } from './mwt-context.mjs';
import { escapeHtml } from './presentation.mjs';
import { clearAllTokenLookupState } from './segment-rendering.mjs';
import {
  clearUdTokenIndex,
  hideNerHover,
  hideUdLines,
  invalidateUdRectCache,
  invalidateUiRectCache
} from './token-fragments.mjs';
import { tokenFragmentsState } from './token-fragments.state.mjs';
export function lookupCurrentFoliateRectSlice(extraMeta, globalPageIndex) {
  var state = buildFoliateRectSliceState(extraMeta);
  if (!state) {
    if (hoverLayoutState.statusText)
      hoverLayoutState.statusText.textContent = 'No visible ebook text in this viewport.';
    if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
    return true;
  }
  var doc = window.DocRenderWebSnapshotRenderer.extractVisibleCanonicalDocument(state);
  if (!doc) {
    if (hoverLayoutState.statusText)
      hoverLayoutState.statusText.textContent = 'No visible ebook text in this viewport.';
    if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
    return true;
  }
  var ctl = ensureCanonicalReaderController();
  if (!ctl) return false;
  documentState.canonicalDoc = doc;
  ctl.setDocument(doc, {
    pageIndex: 0,
    clearCache: true
  });
  var pageText = doc.pages && doc.pages[0] ? String(doc.pages[0].text || '') : '';
  var idx = Math.max(0, Math.floor(Number(globalPageIndex) || 0));
  documentState.pageLookupTextByIndex[idx] = pageText;
  documentState.lastLookupPageIndex = idx;
  syncTrankitChunkLookupControls();
  return ctl.lookupAndRenderPage(0, {
    useCache: true,
    chunkedLookup: shouldUseTrankitChunkLookup()
  });
}
export function lookupCurrentFoliateFlowPage() {
  if (!isActiveFoliateFlowDocument()) return false;
  updateFoliateFlowLocation();
  var globalPageIndex = Math.max(0, Math.floor(Number(documentState.activePageIndex) || 0));
  return lookupCurrentFoliateRectSlice(
    {
      sourceRenderer: 'foliate',
      parser: 'foliate-rect-slice',
      sourcePageIndex: globalPageIndex,
      sourceSectionIndex: foliateCurrentSectionIndex(),
      sourceSectionPageIndex: foliateVisualPageIndex()
    },
    globalPageIndex
  );
}
export function lookupCurrentFoliateEpubPage() {
  if (!isActiveEpubDocument()) return false;
  var pageNum = Math.max(0, Math.floor(Number(documentState.epubJsCurrentPageNum) || 0));
  return lookupCurrentFoliateRectSlice(
    {
      format: currentFoliateFileFormatLabel(),
      sourceRenderer: 'foliate',
      parser: 'foliate-rect-slice',
      sourcePageIndex: pageNum,
      sourceSectionIndex: foliateCurrentSectionIndex(),
      sourceSectionPageIndex: foliateVisualPageIndex()
    },
    pageNum
  );
}
export function openFoliateFlowDocument(result, size, opts) {
  opts = opts || {};
  result = result || {};
  var meta = Object.assign({}, result.meta || {}, {
    fileName:
      opts.fileName ||
      (documentState.currentFile && documentState.currentFile.name) ||
      (result.meta && result.meta.fileName) ||
      ''
  });
  var suppliedSections = Array.isArray(result.flowSections) ? result.flowSections : null;
  var richHtml = suppliedSections
    ? ''
    : String(
        result.richHtml || (result.sourcePages && result.sourcePages[0] && result.sourcePages[0].html) || ''
      );
  var sectionHtmls = normalizeFoliateFlowSections(suppliedSections, richHtml, meta);
  destroyEpubJs();
  var loadSeq = ++documentState.epubLoadSeq;
  documentState.foliateFlowActive = true;
  documentState.foliateFlowSections = sectionHtmls.slice();
  documentState.foliateFlowSectionPageCounts = new Array(Math.max(1, sectionHtmls.length)).fill(0);
  documentState.foliateFlowSectionStartPages = new Array(Math.max(1, sectionHtmls.length)).fill(0);
  documentState.foliateFlowTotalPages = 1;
  documentState.epubJsTotalPages = 1;
  documentState.inputMode = 'doc';
  documentState.currentFileType = opts.fileType || documentState.currentFileType || 'docrender';
  documentState.docrenderActive = true;
  documentState.docrenderMeta = Object.assign({}, meta, {
    sourceRenderer: 'foliate'
  });
  documentState.foliateFlowLabel = currentFoliateFlowFormatLabel();
  documentState.docPagerIsPaged = true;
  documentState.activePageIndex = 0;
  documentState.lastLookupPageIndex = -1;
  documentState.pendingPdfLookupPageIndex = -1;
  documentState.pageLookupTextByIndex = {};
  documentState.docPageScrollTopByIndex = {};
  documentState.docSourcePages = [];
  documentState.docPageRichHtml = [];
  documentState.docPageTextMaps = [];
  documentState.docPages = [''];
  documentState.docText = String(result.fullText || '');
  resetCanonicalDocument();
  if (hoverLayoutState.sourceText) {
    hoverLayoutState.sourceText.style.display = 'none';
    if (documentState.docText.length <= 200000)
      hoverLayoutState.sourceText.value = documentState.docText || hoverLayoutState.sourceText.value || '';
    else if (!hoverLayoutState.sourceText.value || documentState.currentFile)
      hoverLayoutState.sourceText.value = '';
  }
  showDocumentChrome(true);
  applyFixedDocumentViewportHeight(true);
  if (hoverLayoutState.sourcePager) {
    hoverLayoutState.sourcePager.innerHTML = '';
    hoverLayoutState.sourcePager.style.display = 'block';
    hoverLayoutState.sourcePager.classList.remove(
      'pdfjs-native-mode',
      'orig-view-mode',
      'docrender-source-active',
      'docrender-websnapshot-active',
      'docrender-docx-continuous-active',
      'docrender-foliate-flow-active'
    );
    hoverLayoutState.sourcePager.classList.add(
      'docrender-epub-foliate-active',
      'docrender-foliate-flow-active'
    );
  }
  if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Paginating document...';
  if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
  return ensureFoliateJs()
    .then(function () {
      if (loadSeq !== documentState.epubLoadSeq) return null;
      if (!window.customElements || !customElements.get('foliate-view')) {
        throw new Error('Foliate view component did not register');
      }
      var view = document.createElement('foliate-view');
      view.className = 'foliate-flow-view';
      documentState.epubJsRendition = view;
      var book = makeFoliateFlowBook(sectionHtmls, documentState.docrenderMeta);
      documentState.epubJsBook = book;
      resetFoliateFullPagination(true);
      setFoliateDocumentCapabilities('foliate-flow');
      if (hoverLayoutState.sourcePager) hoverLayoutState.sourcePager.appendChild(view);
      view.addEventListener('load', function () {
        configureFoliateViewRenderer(view);
      });
      view.addEventListener('relocate', function (ev) {
        updateFoliateFlowLocation(ev.detail || {});
      });
      return view.open(book).then(function () {
        if (loadSeq !== documentState.epubLoadSeq) return null;
        configureFoliateViewRenderer(view);
        observeFoliateEpubResize();
        return view.init({
          showTextStart: true
        });
      });
    })
    .then(function () {
      if (loadSeq !== documentState.epubLoadSeq) return null;
      configureFoliateViewRenderer(documentState.epubJsRendition);
      if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Ready.';
      startFoliateFullPagination('load');
      updateFoliateFlowLocation(
        (documentState.epubJsRendition && documentState.epubJsRendition.lastLocation) || {}
      );
      if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
      return null;
    })
    .then(function () {
      if (loadSeq !== documentState.epubLoadSeq) return;
      if (opts.triggerLookup) {
        if (typeof window.__LE_LOOKUP_ALLOWED !== 'undefined') window.__LE_LOOKUP_ALLOWED = true;
        triggerUpdate();
      }
    })
    .catch(function (err) {
      if (loadSeq !== documentState.epubLoadSeq) return;
      console.error('Foliate flow load failed:', err);
      documentState.foliateFlowActive = false;
      documentState.docrenderActive = false;
      resetCanonicalDocument();
      if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Document render failed.';
      if (hoverLayoutState.renderedText)
        hoverLayoutState.renderedText.innerHTML =
          '<div class="reader-output-placeholder">Could not paginate document: ' +
          escapeHtml(err && err.message ? err.message : 'unknown error') +
          '</div>';
    });
}
export function loadEpubWithEpubJs(file) {
  if (hoverLayoutState.statusText)
    hoverLayoutState.statusText.textContent = 'Loading ' + currentFoliateFileFormatLabel() + '...';
  if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
  destroyEpubJs();
  initFoliateEpub(file);
}

// ---- end Foliate EPUB integration ----
export function syncWebSnapshotInspectorControls() {
  var active = isTopSourceInspectorAvailable();
  if (hoverLayoutState.webDocControls)
    hoverLayoutState.webDocControls.style.display = active ? 'flex' : 'none';
  if (!active) {
    documentState.webSnapshotSelectedText = '';
    documentState.webSnapshotInspectorEnabled = false;
    clearLocalSourceInspectorOverlay();
    detachLocalSourceInspectorListeners();
  }
  if (hoverLayoutState.webInspectorButton) {
    hoverLayoutState.webInspectorButton.classList.toggle(
      'active',
      !!(active && documentState.webSnapshotInspectorEnabled)
    );
    hoverLayoutState.webInspectorButton.setAttribute(
      'aria-pressed',
      active && documentState.webSnapshotInspectorEnabled ? 'true' : 'false'
    );
    hoverLayoutState.webInspectorButton.disabled = !active;
  }
  if (hoverLayoutState.webInspectorStatus) {
    hoverLayoutState.webInspectorStatus.textContent = '';
  }
  syncTrankitChunkLookupControls();
  var state = getActiveWebSnapshotState();
  if (
    state &&
    window.DocRenderWebSnapshotRenderer &&
    window.DocRenderWebSnapshotRenderer.setInspectorEnabled
  ) {
    window.DocRenderWebSnapshotRenderer.setInspectorEnabled(
      state,
      !!(isActiveWebSnapshotDocument() && active && documentState.webSnapshotInspectorEnabled),
      {
        onSelectionChange: onWebSnapshotSelectionChange
      }
    );
  }
  if (documentState.inputMode === 'pdf') {
    var pdfInspectorEnabled = !!(active && documentState.webSnapshotInspectorEnabled);
    if (documentShellState.pdfSourceInspectorCommanded !== pdfInspectorEnabled) {
      documentShellState.pdfSourceInspectorCommanded = pdfInspectorEnabled;
      postPdfCommand('setSourceInspector', {
        enabled: pdfInspectorEnabled
      });
    }
  }
  if (active && documentState.webSnapshotInspectorEnabled && isLocalSourceInspectorAvailable()) {
    hoverLayoutState.sourcePager.classList.add('source-inspector-active');
    attachLocalSourceInspectorListeners();
    refreshLocalSourceInspectorFrameListeners();
    drawLocalSourceInspectorSelection();
    enforceLocalSourceSelectionPolicy(true);
  } else {
    if (hoverLayoutState.sourcePager)
      hoverLayoutState.sourcePager.classList.remove('source-inspector-active');
    detachLocalSourceInspectorListeners();
    enforceLocalSourceSelectionPolicy(false);
    clearLocalSourceInspectorOverlay();
  }
}
export function setWebSnapshotInspectorEnabled(enabled) {
  documentState.webSnapshotInspectorEnabled = !!enabled;
  syncWebSnapshotInspectorControls();
  if (hoverLayoutState.statusText && isTopSourceInspectorAvailable()) {
    hoverLayoutState.statusText.textContent = 'Ready.';
  }
}
export function clearWebSnapshotInspectorSelection() {
  documentState.webSnapshotSelectedText = '';
  clearLocalSourceInspectorOverlay();
  try {
    var mainSel = window.getSelection ? window.getSelection() : null;
    if (mainSel && typeof mainSel.removeAllRanges === 'function') mainSel.removeAllRanges();
  } catch (_se) {}
  if (hoverLayoutState.sourcePager) {
    Array.from(hoverLayoutState.sourcePager.querySelectorAll('iframe')).forEach(function (frame) {
      try {
        var win = frame.contentWindow;
        var sel = win && win.getSelection ? win.getSelection() : null;
        if (sel && typeof sel.removeAllRanges === 'function') sel.removeAllRanges();
      } catch (_ie) {}
    });
  }
  var state = getActiveWebSnapshotState();
  if (state && state.win) {
    try {
      var sel = state.win.getSelection ? state.win.getSelection() : null;
      if (sel && typeof sel.removeAllRanges === 'function') sel.removeAllRanges();
    } catch (_e) {}
  }
  if (
    state &&
    window.DocRenderWebSnapshotRenderer &&
    window.DocRenderWebSnapshotRenderer.clearSelectionOverlay
  ) {
    window.DocRenderWebSnapshotRenderer.clearSelectionOverlay(state);
  }
  try {
    var renderer = getFoliateEpubRenderer();
    var contents = renderer && typeof renderer.getContents === 'function' ? renderer.getContents() : null;
    (contents || []).forEach(function (content) {
      var win = content && content.doc && content.doc.defaultView;
      var sel = win && win.getSelection ? win.getSelection() : null;
      if (sel && typeof sel.removeAllRanges === 'function') sel.removeAllRanges();
    });
  } catch (_fe) {}
  syncWebSnapshotInspectorControls();
}
export function isLocalSourceInspectorAvailable() {
  if (!hoverLayoutState.sourcePager || isActiveWebSnapshotDocument()) return false;
  if (hoverLayoutState.sourcePager.style.display === 'none') return false;
  if (isActiveEpubDocument() || isActiveFoliateFlowDocument()) {
    try {
      var renderer = getFoliateEpubRenderer();
      var contents = renderer && typeof renderer.getContents === 'function' ? renderer.getContents() : null;
      if (contents && contents.length && contents[0].doc && contents[0].doc.body) return true;
    } catch (_e) {}
  }
  if (hoverLayoutState.sourcePager.querySelector('iframe')) return true;
  return !!String(hoverLayoutState.sourcePager.textContent || '').trim();
}
export function isTopSourceInspectorAvailable() {
  return isActiveWebSnapshotDocument() || isLocalSourceInspectorAvailable();
}
export function ensureLocalSourceInspectorOverlay() {
  if (!hoverLayoutState.sourcePager) return null;
  var overlay = hoverLayoutState.sourcePager.querySelector(':scope > .source-inspector-selection-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.className = 'source-inspector-selection-overlay';
    hoverLayoutState.sourcePager.appendChild(overlay);
  }
  return overlay;
}
export function clearLocalSourceInspectorOverlay() {
  if (!hoverLayoutState.sourcePager) return;
  var overlay = hoverLayoutState.sourcePager.querySelector(':scope > .source-inspector-selection-overlay');
  if (overlay) overlay.innerHTML = '';
}
export function selectionIntersectsSourcePager(sel) {
  if (!sel || !sel.rangeCount || !hoverLayoutState.sourcePager) return false;
  for (var i = 0; i < sel.rangeCount; i++) {
    var range = sel.getRangeAt(i);
    try {
      if (range && range.intersectsNode && range.intersectsNode(hoverLayoutState.sourcePager)) return true;
    } catch (_e) {
      var node = range && range.commonAncestorContainer;
      if (node && hoverLayoutState.sourcePager.contains(node.nodeType === 1 ? node : node.parentNode))
        return true;
    }
  }
  return false;
}
export function getSourceIframeSelectionContext() {
  if (!hoverLayoutState.sourcePager) return null;
  try {
    var renderer = getFoliateEpubRenderer();
    var contents = renderer && typeof renderer.getContents === 'function' ? renderer.getContents() : null;
    for (var fi = 0; fi < (contents || []).length; fi++) {
      var docF = contents[fi] && contents[fi].doc;
      var winF = docF && docF.defaultView;
      var selF = winF && winF.getSelection ? winF.getSelection() : null;
      if (!docF || !selF || !selF.rangeCount || selF.isCollapsed || !String(selF.toString() || '').trim())
        continue;
      return {
        type: 'iframe',
        frame: winF.frameElement || null,
        win: winF,
        doc: docF,
        sel: selF
      };
    }
  } catch (_fe) {}
  var frames = Array.from(hoverLayoutState.sourcePager.querySelectorAll('iframe'));
  for (var i = 0; i < frames.length; i++) {
    var frame = frames[i];
    try {
      var win = frame.contentWindow;
      var doc = frame.contentDocument || (win && win.document);
      var sel = win && win.getSelection ? win.getSelection() : null;
      if (!doc || !sel || !sel.rangeCount || sel.isCollapsed || !String(sel.toString() || '').trim())
        continue;
      return {
        type: 'iframe',
        frame: frame,
        win: win,
        doc: doc,
        sel: sel
      };
    } catch (_e) {}
  }
  return null;
}
export function getLocalSourceSelectionContext() {
  var sel = window.getSelection ? window.getSelection() : null;
  if (sel && sel.rangeCount && !sel.isCollapsed && selectionIntersectsSourcePager(sel)) {
    return {
      type: 'local',
      frame: null,
      win: window,
      doc: document,
      sel: sel
    };
  }
  return getSourceIframeSelectionContext();
}
export function setIframeInspectorNativeSelection(frameInfo, enabled) {
  try {
    var doc = frameInfo && frameInfo.doc;
    if (!doc) return;
    stripNativeTitleTooltips(doc);
    var id = 'le-source-inspector-selection-style';
    var existing = doc.getElementById(id);
    var style = existing || doc.createElement('style');
    style.id = id;
    style.textContent = enabled
      ? 'html,body,*{user-select:text!important;-webkit-user-select:text!important;}::selection{background:transparent!important;color:inherit!important;text-shadow:inherit!important;}::-moz-selection{background:transparent!important;color:inherit!important;text-shadow:inherit!important;}'
      : 'html,body,*{user-select:none!important;-webkit-user-select:none!important;}::selection{background:transparent!important;color:inherit!important;text-shadow:inherit!important;}::-moz-selection{background:transparent!important;color:inherit!important;text-shadow:inherit!important;}';
    if (!existing) (doc.head || doc.documentElement || doc.body).appendChild(style);
  } catch (_e) {}
}
export function getLocalSourceFrameInfos() {
  var out = [];
  var seen = [];
  function addInfo(info) {
    if (!info || !info.doc || seen.indexOf(info.doc) >= 0) return;
    seen.push(info.doc);
    out.push(info);
  }
  try {
    var renderer = getFoliateEpubRenderer();
    var contents = renderer && typeof renderer.getContents === 'function' ? renderer.getContents() : null;
    (contents || []).forEach(function (content) {
      var doc = content && content.doc;
      var win = doc && doc.defaultView;
      if (doc)
        addInfo({
          frame: (win && win.frameElement) || null,
          win: win,
          doc: doc
        });
    });
  } catch (_fe) {}
  if (hoverLayoutState.sourcePager) {
    Array.from(hoverLayoutState.sourcePager.querySelectorAll('iframe')).forEach(function (frame) {
      try {
        var win = frame.contentWindow;
        var doc = frame.contentDocument || (win && win.document);
        if (doc)
          addInfo({
            frame: frame,
            win: win,
            doc: doc
          });
      } catch (_e) {}
    });
  }
  return out;
}
export function enforceLocalSourceSelectionPolicy(enabled) {
  if (!hoverLayoutState.sourcePager || isActiveWebSnapshotDocument()) return;
  getLocalSourceFrameInfos().forEach(function (info) {
    setIframeInspectorNativeSelection(info, !!enabled);
  });
}
export function refreshLocalSourceInspectorFrameListeners() {
  if (!hoverLayoutState.sourcePager || !attachLocalSourceInspectorListeners._attached) return;
  var old = attachLocalSourceInspectorListeners._frames || [];
  for (var i = 0; i < old.length; i++) {
    try {
      if (old[i].doc) {
        old[i].doc.removeEventListener('selectionchange', drawLocalSourceInspectorSelection);
        old[i].doc.removeEventListener('mouseup', drawLocalSourceInspectorSelection);
        old[i].doc.removeEventListener('keyup', drawLocalSourceInspectorSelection);
        old[i].doc.removeEventListener('scroll', drawLocalSourceInspectorSelection, true);
      }
      setIframeInspectorNativeSelection(old[i], false);
    } catch (_e) {}
  }
  var next = [];
  try {
    var renderer = getFoliateEpubRenderer();
    var contents = renderer && typeof renderer.getContents === 'function' ? renderer.getContents() : null;
    (contents || []).forEach(function (content) {
      var doc = content && content.doc;
      var win = doc && doc.defaultView;
      if (!doc) return;
      var info = {
        frame: (win && win.frameElement) || null,
        win: win,
        doc: doc
      };
      doc.addEventListener('selectionchange', drawLocalSourceInspectorSelection);
      doc.addEventListener('mouseup', drawLocalSourceInspectorSelection);
      doc.addEventListener('keyup', drawLocalSourceInspectorSelection);
      doc.addEventListener('scroll', drawLocalSourceInspectorSelection, true);
      setIframeInspectorNativeSelection(info, true);
      next.push(info);
    });
  } catch (_fe) {}
  Array.from(hoverLayoutState.sourcePager.querySelectorAll('iframe')).forEach(function (frame) {
    try {
      var win = frame.contentWindow;
      var doc = frame.contentDocument || (win && win.document);
      if (!doc) return;
      var info = {
        frame: frame,
        win: win,
        doc: doc
      };
      doc.addEventListener('selectionchange', drawLocalSourceInspectorSelection);
      doc.addEventListener('mouseup', drawLocalSourceInspectorSelection);
      doc.addEventListener('keyup', drawLocalSourceInspectorSelection);
      doc.addEventListener('scroll', drawLocalSourceInspectorSelection, true);
      setIframeInspectorNativeSelection(info, true);
      next.push(info);
    } catch (_e) {}
  });
  attachLocalSourceInspectorListeners._frames = next;
}
export function drawLocalSourceInspectorSelection() {
  if (
    !documentState.webSnapshotInspectorEnabled ||
    !isLocalSourceInspectorAvailable() ||
    !window.getSelection
  ) {
    clearLocalSourceInspectorOverlay();
    return {
      text: '',
      rects: []
    };
  }
  var ctx = getLocalSourceSelectionContext();
  var sel = ctx && ctx.sel;
  if (!ctx || !sel || sel.isCollapsed) {
    clearLocalSourceInspectorOverlay();
    documentState.webSnapshotSelectedText = '';
    return {
      text: '',
      rects: []
    };
  }
  var overlay = ensureLocalSourceInspectorOverlay();
  if (!overlay)
    return {
      text: '',
      rects: []
    };
  overlay.innerHTML = '';
  var pagerRect = hoverLayoutState.sourcePager.getBoundingClientRect();
  var frameRect = ctx.frame ? ctx.frame.getBoundingClientRect() : null;
  var rectsOut = [];
  for (var i = 0; i < sel.rangeCount; i++) {
    var rects = Array.from(sel.getRangeAt(i).getClientRects ? sel.getRangeAt(i).getClientRects() : []);
    for (var rI = 0; rI < rects.length; rI++) {
      var r = rects[rI];
      if (!r || r.width <= 0.5 || r.height <= 0.5) continue;
      var absLeft = (frameRect ? frameRect.left : 0) + r.left;
      var absTop = (frameRect ? frameRect.top : 0) + r.top;
      var absRight = absLeft + r.width;
      var absBottom = absTop + r.height;
      if (
        absRight < pagerRect.left ||
        absLeft > pagerRect.right ||
        absBottom < pagerRect.top ||
        absTop > pagerRect.bottom
      )
        continue;
      var cell = document.createElement('div');
      cell.className = 'source-inspector-selection-cell';
      cell.style.left = absLeft - pagerRect.left + (hoverLayoutState.sourcePager.scrollLeft || 0) + 'px';
      cell.style.top = absTop - pagerRect.top + (hoverLayoutState.sourcePager.scrollTop || 0) + 'px';
      cell.style.width = r.width + 'px';
      cell.style.height = r.height + 'px';
      overlay.appendChild(cell);
      rectsOut.push(r);
    }
  }
  documentState.webSnapshotSelectedText = String(sel.toString() || '');
  if (hoverLayoutState.webInspectorStatus) hoverLayoutState.webInspectorStatus.textContent = '';
  return {
    text: documentState.webSnapshotSelectedText,
    rects: rectsOut
  };
}
export function attachLocalSourceInspectorListeners() {
  if (attachLocalSourceInspectorListeners._attached) return;
  attachLocalSourceInspectorListeners._attached = true;
  document.addEventListener('selectionchange', drawLocalSourceInspectorSelection);
  document.addEventListener('mouseup', drawLocalSourceInspectorSelection);
  document.addEventListener('keyup', drawLocalSourceInspectorSelection);
  refreshLocalSourceInspectorFrameListeners();
}
export function detachLocalSourceInspectorListeners() {
  if (!attachLocalSourceInspectorListeners._attached) return;
  attachLocalSourceInspectorListeners._attached = false;
  document.removeEventListener('selectionchange', drawLocalSourceInspectorSelection);
  document.removeEventListener('mouseup', drawLocalSourceInspectorSelection);
  document.removeEventListener('keyup', drawLocalSourceInspectorSelection);
  var frames = attachLocalSourceInspectorListeners._frames || [];
  for (var i = 0; i < frames.length; i++) {
    try {
      if (frames[i].doc) {
        frames[i].doc.removeEventListener('selectionchange', drawLocalSourceInspectorSelection);
        frames[i].doc.removeEventListener('mouseup', drawLocalSourceInspectorSelection);
        frames[i].doc.removeEventListener('keyup', drawLocalSourceInspectorSelection);
        frames[i].doc.removeEventListener('scroll', drawLocalSourceInspectorSelection, true);
      }
      setIframeInspectorNativeSelection(frames[i], false);
    } catch (_e) {}
  }
  attachLocalSourceInspectorListeners._frames = [];
}
export function getWebSnapshotScrollState() {
  var state = getActiveWebSnapshotState();
  if (!state || !window.DocRenderWebSnapshotRenderer || !window.DocRenderWebSnapshotRenderer.getScrollState)
    return null;
  return window.DocRenderWebSnapshotRenderer.getScrollState(state);
}
export function scrollWebSnapshotBy(delta, opts) {
  var state = getActiveWebSnapshotState();
  if (!state || !window.DocRenderWebSnapshotRenderer || !window.DocRenderWebSnapshotRenderer.scrollBy)
    return null;
  var info = window.DocRenderWebSnapshotRenderer.scrollBy(state, delta, opts || {});
  updateDocumentNavigatorThumb();
  return info;
}
export function scrollWebSnapshotByLine(direction) {
  var info = getWebSnapshotScrollState();
  var line = Math.max(8, Number(info && info.lineHeight) || 20);
  return scrollWebSnapshotBy((Number(direction) >= 0 ? 1 : -1) * line);
}
export function scrollWebSnapshotByViewport(direction) {
  var info = getWebSnapshotScrollState();
  var amount = Math.max(
    80,
    Math.round((Number(info && info.viewportHeight) || documentState.docViewportHeightPx || 640) * 0.9)
  );
  return scrollWebSnapshotBy((Number(direction) >= 0 ? 1 : -1) * amount);
}
export function scrollWebSnapshotToRatio(ratio) {
  var state = getActiveWebSnapshotState();
  if (!state || !window.DocRenderWebSnapshotRenderer || !window.DocRenderWebSnapshotRenderer.scrollToRatio)
    return null;
  var info = window.DocRenderWebSnapshotRenderer.scrollToRatio(state, ratio || 0);
  updateDocumentNavigatorThumb();
  return info;
}
export function cancelWebSnapshotVisibleCanonicalRefresh() {
  if (!documentState.webSnapshotVisibleCanonicalRefreshTimer) return;
  clearTimeout(documentState.webSnapshotVisibleCanonicalRefreshTimer);
  documentState.webSnapshotVisibleCanonicalRefreshTimer = null;
}
export function isWebSnapshotVisibleCanonicalDocument(doc) {
  if (!doc) return false;
  var srcKind = String((doc.source && doc.source.kind) || '');
  var page = (doc.pages && doc.pages[0]) || null;
  var pageKind = String((page && page.source && page.source.kind) || '');
  return srcKind === 'webSnapshotVisibleDom' || pageKind === 'webSnapshotVisibleDom';
}
export function clearLookupStateForWebSnapshotPreview(text) {
  hoverLayoutState.latestSeq += 1;
  hoverLayoutState.latestData = null;
  hoverLayoutState.latestSegments = [];
  lookupProgressState.latestOriginalText = String(text || '');
  lookupProgressState.latestFillsDict = {};
  latestSegmentOffsets = [];
  dependencyPopupState.latestChunks = [];
  try {
    setLatestUdOverlay(null);
  } catch (_e0) {}
  try {
    clearUdTokenIndex();
  } catch (_e1) {}
  try {
    invalidateUdRectCache();
  } catch (_e2) {}
  try {
    invalidateUiRectCache();
  } catch (_e3) {}
  try {
    clearAllTokenLookupState();
  } catch (_e4) {}
  try {
    hideUdLines();
  } catch (_e5) {}
  try {
    hideNerHover();
  } catch (_e6) {}
  try {
    clearChunkHighlight();
  } catch (_e7) {}
  tokenFragmentsState.hoverReticle = null;
  dependencyState.udSvgOverlay = null;
  if (
    !lookupProgressState.depTreeUseConllu &&
    lookupProgressState.depTreeController &&
    typeof lookupProgressState.depTreeController.setData === 'function'
  ) {
    lookupProgressState.depTreeController.setData({
      segments: [],
      udOverlay: null,
      originalText: lookupProgressState.latestOriginalText
    });
  }
}
export function renderWebSnapshotVisibleCanonicalPreview() {
  var state = getActiveWebSnapshotState();
  if (
    !state ||
    !window.DocRenderWebSnapshotRenderer ||
    !window.DocRenderWebSnapshotRenderer.extractVisibleCanonicalDocument
  )
    return false;
  var doc = window.DocRenderWebSnapshotRenderer.extractVisibleCanonicalDocument(state, {
    margin: 8
  });
  var page = (doc && doc.pages && doc.pages[0]) || null;
  if (!page || !String(page.text || '').trim()) return false;
  setCanonicalDocument(doc, {
    pageIndex: 0,
    clearCache: true
  });
  clearLookupStateForWebSnapshotPreview(page.text);
  if (window.CanonicalRenderer && hoverLayoutState.renderedText) {
    try {
      window.CanonicalRenderer.renderPage(page, hoverLayoutState.renderedText, {});
    } catch (err) {
      console.warn('Web snapshot visible preview render failed:', err);
      return false;
    }
  }
  if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Ready.';
  if (hoverLayoutState.statusCounts)
    hoverLayoutState.statusCounts.textContent = 'Visible web slice. Press Look Up to analyze.';
  try {
    updateRenderedOutputBackground();
  } catch (_e) {}
  return true;
}
export function scheduleWebSnapshotVisibleCanonicalRefresh() {
  if (!isActiveWebSnapshotDocument()) return;
  if (!isWebSnapshotVisibleCanonicalDocument(documentState.canonicalDoc)) return;
  if (documentState.webSnapshotInspectorEnabled || documentState.webSnapshotSelectedText) return;
  var seq = documentState.webSnapshotCanonicalSeq;
  cancelWebSnapshotVisibleCanonicalRefresh();
  documentState.webSnapshotVisibleCanonicalRefreshTimer = setTimeout(function () {
    documentState.webSnapshotVisibleCanonicalRefreshTimer = null;
    if (seq !== documentState.webSnapshotCanonicalSeq || !isActiveWebSnapshotDocument()) return;
    if (!isWebSnapshotVisibleCanonicalDocument(documentState.canonicalDoc)) return;
    renderWebSnapshotVisibleCanonicalPreview();
  }, 220);
}
export function onWebSnapshotScroll(info) {
  updateDocumentNavigatorThumb();
  if (hoverLayoutState.docNavPrev) hoverLayoutState.docNavPrev.disabled = !info || info.scrollTop <= 0;
  if (hoverLayoutState.docNavNext)
    hoverLayoutState.docNavNext.disabled = !info || info.scrollTop >= info.maxScroll - 1;
  cancelWebSnapshotVisibleCanonicalRefresh();
}
export function getEpubScrollState() {
  var total = Math.max(1, documentState.epubJsTotalPages || 1);
  var idx = Math.max(0, Math.min(total - 1, documentState.epubJsCurrentPageNum || 0));
  return {
    scrollTop: idx,
    scrollHeight: total,
    contentHeight: total,
    viewportHeight: 1,
    maxScroll: Math.max(0, total - 1),
    ratio: total > 1 ? idx / (total - 1) : 0,
    lineHeight: 1
  };
}
export function refreshEpubCanonicalSoon(delayMs) {
  if (documentState.epubJsScrollTimer) clearTimeout(documentState.epubJsScrollTimer);
  documentState.epubJsScrollTimer = setTimeout(
    function () {
      documentState.epubJsScrollTimer = null;
      extractEpubVisibleText();
      var canPage = buildEpubCanonicalPage();
      if (canPage) setEpubCanonicalPage(canPage);
    },
    Math.max(0, Number(delayMs) || 0)
  );
}
export function onEpubContinuousScroll() {
  updateFoliateEpubLocation(
    (documentState.epubJsRendition && documentState.epubJsRendition.lastLocation) || {}
  );
}
export function scrollEpubBy(delta) {
  nativeFoliateStepPage(Number(delta) >= 0 ? 1 : -1);
}
export function scrollEpubByLine(direction) {
  nativeFoliateStepPage(Number(direction) >= 0 ? 1 : -1);
}
export function scrollEpubByViewport(direction) {
  nativeFoliateStepPage(Number(direction) >= 0 ? 1 : -1);
}
export function scrollEpubToRatio(ratio) {
  if (documentState.epubJsRendition && typeof documentState.epubJsRendition.goToFraction === 'function') {
    return Promise.resolve(
      documentState.epubJsRendition.goToFraction(Math.max(0, Math.min(1, Number(ratio) || 0)))
    )
      .then(function () {
        if (isActiveFoliateFlowDocument())
          updateFoliateFlowLocation(
            (documentState.epubJsRendition && documentState.epubJsRendition.lastLocation) || {}
          );
        else if (isActiveEpubDocument())
          updateFoliateEpubLocation(
            (documentState.epubJsRendition && documentState.epubJsRendition.lastLocation) || {}
          );
        requestMovementLookup();
        return true;
      })
      .catch(function (err) {
        console.warn('Foliate native fraction navigation failed:', err);
        return false;
      });
  }
  return Promise.resolve(false);
}
export function isDocxContinuousActive() {
  return !!(
    documentState.docrenderActive &&
    String((documentState.docrenderMeta && documentState.docrenderMeta.format) || '').toLowerCase() ===
      'docx' &&
    hoverLayoutState.sourcePager &&
    hoverLayoutState.sourcePager.querySelector('.docx-preview-host')
  );
}
export function getDocxContinuousScrollState() {
  var inner =
    hoverLayoutState.sourcePager && hoverLayoutState.sourcePager.querySelector('.reader-page-inner');
  if (!inner) return null;
  var scrollTop = inner.scrollTop || 0;
  var scrollH = Math.max(1, inner.scrollHeight || 1);
  var clientH = Math.max(1, inner.clientHeight || 1);
  var maxScroll = Math.max(0, scrollH - clientH);
  var lineHeight = documentState.docLineHeight || 20;
  try {
    var host =
      hoverLayoutState.sourcePager && hoverLayoutState.sourcePager.querySelector('.docx-preview-host');
    var target = host && (host.querySelector('p, li, div, span') || host);
    var cs = target && window.getComputedStyle(target);
    var lh = cs ? parseFloat(cs.lineHeight) : 0;
    if (isFinite(lh) && lh > 0) lineHeight = lh;
    else {
      var fs = cs ? parseFloat(cs.fontSize) : 0;
      if (isFinite(fs) && fs > 0) lineHeight = fs * 1.25;
    }
  } catch (_e) {}
  return {
    scrollTop: scrollTop,
    contentHeight: scrollH,
    viewportHeight: clientH,
    maxScroll: maxScroll,
    ratio: maxScroll > 0 ? Math.max(0, Math.min(1, scrollTop / maxScroll)) : 0,
    lineHeight: Math.max(8, lineHeight || 20)
  };
}
export function scrollDocxContinuousBy(delta) {
  var inner =
    hoverLayoutState.sourcePager && hoverLayoutState.sourcePager.querySelector('.reader-page-inner');
  if (!inner) return;
  inner.scrollTop += delta;
  onDocxContinuousScroll();
}
export function scrollDocxContinuousByLine(dir) {
  var s = getDocxContinuousScrollState();
  var line = Math.max(8, Number(s && s.lineHeight) || 20);
  scrollDocxContinuousBy((Number(dir) >= 0 ? 1 : -1) * line);
}
export function scrollDocxContinuousByViewport(dir) {
  var s = getDocxContinuousScrollState();
  var amount = Math.max(
    80,
    Math.round(((s && s.viewportHeight) || documentState.docViewportHeightPx || 640) * 0.9)
  );
  scrollDocxContinuousBy((Number(dir) >= 0 ? 1 : -1) * amount);
}
export function scrollDocxContinuousToRatio(ratio) {
  var inner =
    hoverLayoutState.sourcePager && hoverLayoutState.sourcePager.querySelector('.reader-page-inner');
  if (!inner) return;
  var maxScroll = Math.max(0, inner.scrollHeight - inner.clientHeight);
  inner.scrollTop = Math.round(Math.max(0, Math.min(1, ratio || 0)) * maxScroll);
  onDocxContinuousScroll();
}
export function initializeDocumentNavigation() {
  documentNavigationState.updateFoliateFlowLocationDebounced = debounce(function () {
    if (!isActiveFoliateFlowDocument()) return;
    updateFoliateFlowLocation();
  }, 120);
  return true;
}
