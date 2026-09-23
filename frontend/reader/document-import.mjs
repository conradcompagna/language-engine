import { getDocRenderPageSize, setDocMode, setRawMode } from './continuous-scroll.mjs';
import { rebuildConnectedIslandGroups } from './dependency-geometry.mjs';
import { computeChunks } from './dependency-popup.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { documentImportState } from './document-import.state.mjs';
import { openFoliateFlowDocument } from './document-navigation.mjs';
import {
  applyFixedDocumentViewportHeight,
  getRawContinuousTextNode,
  isRawContinuousActive,
  leaveRawContinuousMode,
  onRawContinuousScroll,
  scrollRawContinuousBy,
  showDocumentChrome,
  syncRawContinuousModeForSourceText
} from './document-search.mjs';
import {
  collectPdfPageDimensions,
  computeAveragePdfDimension,
  createPdfBrowserObjectUrl,
  ensurePdfJsLoaded,
  getPdfJsDocument,
  mountPdfJsIframe,
  postPdfPageDimsCacheToIframe,
  revokePdfBrowserObjectUrl,
  sanitizePdfDimensionList
} from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import {
  _debugShowPlainText,
  createLazyPdfCanonicalDocument,
  normalizeDocumentText,
  setCanonicalDocument,
  showRawTextPill
} from './document-state.mjs';
import { documentState } from './document-state.state.mjs';
import { pushLookupResolverPayload } from './entry-editing.mjs';
import { loadFile } from './entry-forms.mjs';
import { triggerUpdate } from './fill-slices.mjs';
import { syncDocumentChrome } from './foliate-viewport.mjs';
import { clearChunkHighlight } from './gloss-requests.mjs';
import { attachHoverHandlers, computeAndCacheRowBands } from './hover-interaction.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import {
  _resetSentenceTabletGlossOverrides,
  clearInitialInputGuidanceIfNeeded,
  isShowingInitialInputGuidance,
  reportLookupProgress,
  startSegmentLookupFetch
} from './lookup-progress.mjs';
import { lookupProgressState } from './lookup-progress.state.mjs';
import { setLatestUdOverlay } from './mwt-context.mjs';
import { buildLookupUrl } from './orthography.mjs';
import { orthographyState } from './orthography.state.mjs';
import { escapeHtml } from './presentation.mjs';
import { clearAllTokenLookupState } from './segment-rendering.mjs';
import {
  applyOffsetsAsTokenSpansOnDom,
  buildVisibleDocxSliceFragment,
  getVisibleDocxSliceText
} from './text-offsets.mjs';
import {
  buildUdRectCache,
  clearUdTokenIndex,
  hideNerHover,
  hideUdLines,
  invalidateUdRectCache,
  invalidateUiRectCache,
  registerTokenSpan
} from './token-fragments.mjs';
import { tokenFragmentsState } from './token-fragments.state.mjs';
import { applyGlobalViewportClamp } from './viewport-clamping.mjs';
export function loadPdfInBrowser(file) {
  if (!file) return;
  leaveRawContinuousMode();
  if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Loading PDF...';
  if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
  var seq = ++documentShellState.pdfOriginal.renderSeq;
  documentState.pdfCacheId = null;
  documentState.inputMode = 'pdf';
  documentState.currentFileType = 'pdf';
  documentState.currentFile = file;
  documentState.docPagerIsPaged = true;
  documentState.activePageIndex = 0;
  documentState.lastLookupPageIndex = -1;
  documentState.pendingPdfLookupPageIndex = -1;
  documentState.pageLookupTextByIndex = {};
  documentState.pdfRawPageTextLoaded = {};
  documentState.pdfCanonicalPageFetches = {};
  documentState.originalLayoutCache = {};
  documentState.docrenderActive = false;
  documentState.webSnapshotCanonicalSeq += 1;
  documentState.webSnapshotInspectorEnabled = false;
  documentState.webSnapshotSelectedText = '';
  documentState.docSourcePages = [];
  documentState.docPageRichHtml = [];
  documentState.docPageTextMaps = [];
  documentState.docrenderPdfRichHtml = [];
  documentState.docrenderPdfText = [];
  documentState.docrenderPdfTextMap = [];
  if (hoverLayoutState.sourceText) {
    hoverLayoutState.sourceText.style.display = 'none';
    hoverLayoutState.sourceText.value = '';
  }
  if (hoverLayoutState.sourcePager) {
    hoverLayoutState.sourcePager.style.display = 'block';
    hoverLayoutState.sourcePager.classList.add('pdfjs-native-mode');
    hoverLayoutState.sourcePager.classList.remove(
      'orig-view-mode',
      'docrender-source-active',
      'docrender-websnapshot-active',
      'docrender-docx-continuous-active',
      'docrender-epub-foliate-active',
      'docrender-foliate-flow-active'
    );
    hoverLayoutState.sourcePager.innerHTML = '';
  }
  showDocumentChrome(true);
  applyFixedDocumentViewportHeight(true);
  ensurePdfJsLoaded()
    .then(function () {
      if (
        !window.CanonicalPdfExtractor ||
        typeof window.CanonicalPdfExtractor.pageFromPdfJsPage !== 'function'
      ) {
        throw new Error('CanonicalPdfExtractor is not loaded');
      }
      return getPdfJsDocument(file);
    })
    .then(function (pdfDoc) {
      if (seq !== documentShellState.pdfOriginal.renderSeq) return null;
      documentState.docPages = new Array(Math.max(1, pdfDoc.numPages || 1)).fill('');
      documentState.docText = '';
      if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Measuring PDF pages...';
      return collectPdfPageDimensions(pdfDoc).then(function (dims) {
        if (seq !== documentShellState.pdfOriginal.renderSeq) return null;
        documentShellState.pdfPageDimensions = sanitizePdfDimensionList(dims);
        documentShellState.pdfAveragePageDimensions = computeAveragePdfDimension(
          documentShellState.pdfPageDimensions
        );
        applyFixedDocumentViewportHeight(true);
        syncDocumentChrome();
        mountPdfJsIframe(null, createPdfBrowserObjectUrl(file));
        return createLazyPdfCanonicalDocument(pdfDoc);
      });
    })
    .then(function (doc) {
      if (!doc || seq !== documentShellState.pdfOriginal.renderSeq) return;
      setCanonicalDocument(doc, {
        pageIndex: 0,
        clearCache: true
      });
      documentState.inputMode = 'pdf';
      documentState.docPagerIsPaged = true;
      documentState.pdfRawPageTextLoaded = {};
      documentState.pdfCanonicalPageFetches = {};
      if (hoverLayoutState.sourceText) hoverLayoutState.sourceText.value = '';
      applyFixedDocumentViewportHeight(true);
      postPdfPageDimsCacheToIframe();
      dependencyState.rerenderPdfPagesOnResizeDebounced();
      syncDocumentChrome();
      if (hoverLayoutState.statusText)
        hoverLayoutState.statusText.textContent = 'Ready (' + (doc.pages.length || 0) + ' pages).';
      if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
    })
    .catch(function (err) {
      if (seq !== documentShellState.pdfOriginal.renderSeq) return;
      console.error(err);
      revokePdfBrowserObjectUrl();
      if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'PDF load failed.';
      if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
      if (hoverLayoutState.renderedText) {
        hoverLayoutState.renderedText.innerHTML =
          '<div class="reader-output-placeholder">Could not load PDF in the browser: ' +
          escapeHtml(err && err.message ? err.message : 'unknown error') +
          '</div>';
      }
    });
}
export function setRawTextFoliateDocument(text, options) {
  var opts = options || {};
  if (!window.DocRenderLoader) {
    if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Text renderer unavailable.';
    if (hoverLayoutState.renderedText)
      hoverLayoutState.renderedText.innerHTML =
        '<div class="reader-output-placeholder">Could not paginate text because DocRenderLoader is not loaded.</div>';
    return false;
  }
  var seq = ++documentState.rawTextFoliateLoadSeq;
  var normalized = normalizeDocumentText(text || '');
  if (documentState.origViewToggle) documentState.origViewToggle.style.display = 'none';
  if (documentState.origViewCheckbox) documentState.origViewCheckbox.checked = false;
  if (orthographyState.pdfTextSourceGroup) orthographyState.pdfTextSourceGroup.style.display = 'none';
  if (!opts.preserveCurrentFile) documentState.currentFile = null;
  documentState.currentFileType = opts.fileType || 'text';
  documentState.rawContinuousMode = false;
  documentState.rawContinuousForce = false;
  documentState.rawContinuousReadOnly = !!opts.readOnly;
  documentState.pdfCacheId = null;
  documentShellState.pdfPageDimensions = [];
  documentShellState.pdfAveragePageDimensions = null;
  documentState.isOriginalView = false;
  documentState.originalLayoutCache = {};
  documentState.docText = normalized;
  if (hoverLayoutState.sourceText) {
    if (hoverLayoutState.sourceText.value !== normalized && normalized.length <= 200000)
      hoverLayoutState.sourceText.value = normalized;
    else if (hoverLayoutState.sourceText.value !== normalized && !hoverLayoutState.sourceText.value)
      hoverLayoutState.sourceText.value = '';
    hoverLayoutState.sourceText.disabled = !!opts.readOnly;
    hoverLayoutState.sourceText.style.display = 'none';
  }
  if (!documentState.currentFile && normalized.trim()) showRawTextPill('Clear text');
  showDocumentChrome(true);
  documentState.docrenderPageHeightPx = 0;
  var size = getDocRenderPageSize();
  documentState.docrenderPageWidthPx = size.width;
  documentState.docrenderPageHeightPx = size.height;
  applyFixedDocumentViewportHeight(true);
  if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Paginating text...';
  if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
  window.DocRenderLoader.loadText(
    normalized,
    size,
    opts.fileName || 'input.txt',
    hoverLayoutState.currentTextDirection
  )
    .then(function (result) {
      if (seq !== documentState.rawTextFoliateLoadSeq) return null;
      if (result && result.meta) {
        result.meta.fileName = opts.fileName || result.meta.fileName || 'input.txt';
        result.meta.format = result.meta.format || 'TXT';
        result.meta.sourceRenderer = 'foliate';
      }
      return openFoliateFlowDocument(result, size, {
        fileName: opts.fileName || 'input.txt',
        fileType: opts.fileType || 'text',
        triggerLookup: !!opts.triggerLookup
      });
    })
    .catch(function (err) {
      if (seq !== documentState.rawTextFoliateLoadSeq) return;
      console.error('Text pagination failed:', err);
      if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Text pagination failed.';
      if (hoverLayoutState.renderedText)
        hoverLayoutState.renderedText.innerHTML =
          '<div class="reader-output-placeholder">Could not paginate text.</div>';
    });
  return true;
}
export function setRawTextContinuousDocument(text, options) {
  return setRawTextFoliateDocument(text, options || {});
}

// Compatibility wrapper: raw/text documents enter the Foliate flow path.
export function loadTextAsDoc(text, options) {
  var opts = options || {};
  setRawTextContinuousDocument(
    text || '',
    Object.assign(
      {
        readOnly: !!opts.readOnly,
        forceContinuous: true,
        triggerLookup: opts.triggerLookup !== false
      },
      opts
    )
  );
}
export // Build layout text from PDF word list
function shouldInsertSpace(word, wi) {
  if (wi <= 0) return false;
  if (word && typeof word.space_before === 'boolean') return word.space_before;
  return true;
}
export function buildLayoutTextFromWords(pageData) {
  // If we have structured_blocks, use them for proper document structure
  var blocks = Array.isArray(pageData.structured_blocks) ? pageData.structured_blocks : null;
  var words = Array.isArray(pageData.words) ? pageData.words : [];
  if (blocks && blocks.length > 0) {
    // Sort blocks by Y position (min_y) for proper vertical ordering
    var sortedBlocks = blocks.slice().sort(function (a, b) {
      return (a.min_y || 0) - (b.min_y || 0);
    });
    var text = '';
    for (var bi = 0; bi < sortedBlocks.length; bi++) {
      if (bi > 0) text += '\n\n'; // Paragraph break between blocks
      var block = sortedBlocks[bi];
      var lines = block.lines || [];
      for (var li = 0; li < lines.length; li++) {
        if (li > 0) text += '\n'; // Line break within block
        var lineWords = lines[li].words || [];
        // Sort words by X within line
        var sortedWords = lineWords.slice().sort(function (a, b) {
          return (a.x || 0) - (b.x || 0);
        });
        for (var wi = 0; wi < sortedWords.length; wi++) {
          var w = sortedWords[wi];
          if (!w || !w.text) continue;
          if (shouldInsertSpace(w, wi)) text += ' ';
          text += w.text;
        }
      }
    }
    return text;
  }

  // Fallback: group words by Y, sort by X within each line
  if (!words.length) return '';

  // Compute median height for line detection
  var medianH = 12;
  var allHeights = [];
  for (var wi = 0; wi < words.length; wi++) {
    if (words[wi] && words[wi].h > 0) allHeights.push(words[wi].h);
  }
  if (allHeights.length) {
    allHeights.sort(function (a, b) {
      return a - b;
    });
    var mid = Math.floor(allHeights.length / 2);
    medianH = allHeights.length % 2 ? allHeights[mid] : (allHeights[mid - 1] + allHeights[mid]) / 2;
  }

  // Group words into lines by Y
  var lineGroups = [];
  var currentLineY = -999;
  var currentLineWords = [];
  for (var wi = 0; wi < words.length; wi++) {
    var w = words[wi];
    if (!w || !w.text) continue;
    var y = typeof w.y === 'number' ? w.y : 0;
    var h = typeof w.h === 'number' && w.h > 0 ? w.h : medianH;
    if (currentLineY >= 0 && Math.abs(y - currentLineY) > h * 0.5) {
      if (currentLineWords.length > 0) {
        lineGroups.push({
          y: currentLineY,
          words: currentLineWords
        });
      }
      currentLineWords = [];
    }
    currentLineWords.push(w);
    currentLineY = y;
  }
  if (currentLineWords.length > 0) {
    lineGroups.push({
      y: currentLineY,
      words: currentLineWords
    });
  }

  // Sort lines by Y
  lineGroups.sort(function (a, b) {
    return a.y - b.y;
  });

  // Build text: lines separated by \n, words sorted by X and separated by space
  var text = '';
  for (var li = 0; li < lineGroups.length; li++) {
    if (li > 0) text += '\n';
    var lineWords = lineGroups[li].words;
    // Sort words by X within line
    lineWords.sort(function (a, b) {
      return (a.x || 0) - (b.x || 0);
    });
    for (var wi = 0; wi < lineWords.length; wi++) {
      var w = lineWords[wi];
      if (!w || !w.text) continue;
      if (shouldInsertSpace(w, wi)) text += ' ';
      text += w.text;
    }
  }
  return text;
}
export function getLayoutTextForPage(pageIdx, fallbackText) {
  if (!documentState.isOriginalView) return fallbackText;
  if (documentState.originalLayoutCache[pageIdx]) return documentState.originalLayoutCache[pageIdx];
  return fallbackText;
}
export function getLookupTextForPage(pageIdx) {
  if (documentState.pageLookupTextByIndex && documentState.pageLookupTextByIndex[pageIdx] != null) {
    return documentState.pageLookupTextByIndex[pageIdx];
  }
  var raw =
    documentState.docPages && documentState.docPages[pageIdx] != null
      ? String(documentState.docPages[pageIdx])
      : '';
  return (raw || '').trim();
}
export function buildWordOffsets(pageText, words) {
  if (!pageText || !words || !words.length) return [];
  var offsets = new Array(words.length);
  var cursor = 0;
  for (var i = 0; i < words.length; i++) {
    var w = words[i];
    var wtext = w && w.text != null ? String(w.text) : '';
    if (!wtext) {
      offsets[i] = null;
      continue;
    }
    var idx = pageText.indexOf(wtext, cursor);
    if (idx < 0 && wtext.indexOf('\u00a0') >= 0) {
      var norm = wtext.replace(/\u00a0/g, ' ');
      idx = pageText.indexOf(norm, cursor);
      if (idx >= 0) wtext = norm;
    }
    if (idx < 0) {
      offsets[i] = null;
      continue;
    }
    offsets[i] = [idx, idx + wtext.length];
    cursor = idx + wtext.length;
  }
  return offsets;
}

// Show dict panel for segment
export function showDictPanelForSegment(segIdx) {
  if (!hoverLayoutState.latestSegments) return;
  var seg = hoverLayoutState.latestSegments[segIdx];
  if (!seg) return;
  if (hoverLayoutState.dictSearch) hoverLayoutState.dictSearch.value = seg;
  if (!lookupProgressState.panelOpen && hoverLayoutState.panelToggle) hoverLayoutState.panelToggle.click();
  if (hoverLayoutState.searchBtn) hoverLayoutState.searchBtn.click();
}

// POS colors for JavaScript (mirror of Python POS_COLORS)
export // Update rendered output area with PDF page background when in original mode
function updateRenderedOutputBackground() {
  if (!hoverLayoutState.renderedText) return;
  hoverLayoutState.renderedText.classList.remove('orig-view-bg');
  hoverLayoutState.renderedText.style.backgroundImage = '';
}
export function ensureRawMeasureEl() {
  if (documentImportState.rawMeasureEl) return documentImportState.rawMeasureEl;
  documentImportState.rawMeasureEl = document.createElement('div');
  documentImportState.rawMeasureEl.style.position = 'absolute';
  documentImportState.rawMeasureEl.style.visibility = 'hidden';
  documentImportState.rawMeasureEl.style.left = '-9999px';
  documentImportState.rawMeasureEl.style.top = '0';
  documentImportState.rawMeasureEl.style.whiteSpace = 'pre-wrap';
  documentImportState.rawMeasureEl.style.wordWrap = 'break-word';
  documentImportState.rawMeasureEl.style.overflowWrap = 'break-word';
  documentImportState.rawMeasureEl.style.boxSizing = 'border-box';
  documentImportState.rawMeasureEl.style.border = '0';
  documentImportState.rawMeasureEl.style.margin = '0';
  documentImportState.rawMeasureEl.style.padding = '0';
  documentImportState.rawMeasureEl.style.height = 'auto';
  documentImportState.rawMeasureEl.style.minHeight = '0';
  documentImportState.rawMeasureEl.style.maxHeight = 'none';
  document.body.appendChild(documentImportState.rawMeasureEl);
  return documentImportState.rawMeasureEl;
}
export function getRawTextMetrics() {
  if (!hoverLayoutState.sourceText) return null;
  var cs = window.getComputedStyle(hoverLayoutState.sourceText);
  var fontSize = parseFloat(cs.fontSize) || 16;
  var lineHeight = parseFloat(cs.lineHeight);
  if (!isFinite(lineHeight)) lineHeight = fontSize * 1.6;
  return {
    font: cs.font,
    lineHeight: lineHeight,
    paddingTop: parseFloat(cs.paddingTop) || 0,
    paddingBottom: parseFloat(cs.paddingBottom) || 0,
    paddingLeft: parseFloat(cs.paddingLeft) || 0,
    paddingRight: parseFloat(cs.paddingRight) || 0,
    width:
      hoverLayoutState.sourceText.clientWidth ||
      hoverLayoutState.sourceText.getBoundingClientRect().width ||
      0,
    letterSpacing: cs.letterSpacing,
    wordSpacing: cs.wordSpacing
  };
}
export function getRawMaxHeightPx() {
  var metrics = getRawTextMetrics();
  if (!metrics) return 0;
  return Math.ceil(documentState.DOC_LINES_CONTENT * metrics.lineHeight);
}
export function getRawMinHeightPx() {
  var metrics = getRawTextMetrics();
  if (!metrics) return 0;
  return Math.ceil(documentState.DOC_LINES_EMPTY * metrics.lineHeight);
}
export function measureRawTextHeight(text, metrics) {
  if (!hoverLayoutState.sourceText) return 0;
  var info = metrics || getRawTextMetrics();
  if (!info || !info.width) return 0;
  var measurer = ensureRawMeasureEl();
  measurer.style.width = Math.max(0, info.width) + 'px';
  measurer.style.font = info.font;
  measurer.style.lineHeight = info.lineHeight + 'px';
  measurer.style.letterSpacing = info.letterSpacing || 'normal';
  measurer.style.wordSpacing = info.wordSpacing || 'normal';
  measurer.style.paddingTop = info.paddingTop + 'px';
  measurer.style.paddingBottom = info.paddingBottom + 'px';
  measurer.style.paddingLeft = info.paddingLeft + 'px';
  measurer.style.paddingRight = info.paddingRight + 'px';
  var normalized = (text || '').replace(/\r\n/g, '\n');
  if (normalized && normalized.charAt(normalized.length - 1) === '\n') {
    normalized += ' ';
  }
  measurer.textContent = normalized;
  return measurer.scrollHeight || measurer.getBoundingClientRect().height || 0;
}
export function findRawTextOffsetForHeight(text, targetY, metrics) {
  var value = String(text || '');
  var lo = 0;
  var hi = value.length;
  var target = Math.max(0, Number(targetY) || 0);
  while (lo < hi) {
    var mid = Math.floor((lo + hi) / 2);
    var h = measureRawTextHeight(value.slice(0, mid), metrics);
    if (h < target) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}
export function getVisibleRawTextareaSlice() {
  var value = normalizeDocumentText(
    documentState.docText || (hoverLayoutState.sourceText && hoverLayoutState.sourceText.value) || ''
  );
  if (!value)
    return {
      text: '',
      start: 0,
      end: 0
    };
  if (!isRawContinuousActive())
    return {
      text: value,
      start: 0,
      end: value.length
    };
  var textNode = getRawContinuousTextNode();
  if (!hoverLayoutState.sourcePager || !textNode)
    return {
      text: value.slice(0, documentState.WINDOWED_MAX_CHARS),
      start: 0,
      end: Math.min(value.length, documentState.WINDOWED_MAX_CHARS)
    };
  var textLength = textNode.textContent.length;
  if (!textLength)
    return {
      text: '',
      start: 0,
      end: 0
    };
  var rect = hoverLayoutState.sourcePager.getBoundingClientRect();
  var viewTop = rect.top;
  var viewBottom = rect.bottom;
  function charRect(index) {
    var range = document.createRange();
    var safe = Math.max(0, Math.min(index, textLength - 1));
    range.setStart(textNode, safe);
    range.setEnd(textNode, Math.min(safe + 1, textLength));
    var rects = range.getClientRects();
    return rects && rects.length ? rects[0] : range.getBoundingClientRect();
  }
  function top(index) {
    return charRect(index).top;
  }
  function bottom(index) {
    return charRect(index).bottom;
  }
  function firstVisible() {
    var lo = 0,
      hi = textLength - 1,
      out = 0;
    while (lo <= hi) {
      var mid = Math.floor((lo + hi) / 2);
      if (bottom(mid) < viewTop) lo = mid + 1;
      else {
        out = mid;
        hi = mid - 1;
      }
    }
    return out;
  }
  function lastVisible() {
    var lo = 0,
      hi = textLength - 1,
      out = textLength - 1;
    while (lo <= hi) {
      var mid = Math.floor((lo + hi) / 2);
      if (top(mid) > viewBottom) hi = mid - 1;
      else {
        out = mid;
        lo = mid + 1;
      }
    }
    return out;
  }
  var tol = Math.max(1, documentState.docLineHeight * 0.35);
  function lineStart(idx) {
    var target = top(idx) - tol,
      lo = 0,
      hi = idx,
      out = idx;
    while (lo <= hi) {
      var mid = Math.floor((lo + hi) / 2);
      if (top(mid) < target) lo = mid + 1;
      else {
        out = mid;
        hi = mid - 1;
      }
    }
    return out;
  }
  function lineEnd(idx) {
    var target = top(idx) + tol,
      lo = idx,
      hi = textLength - 1,
      out = idx;
    while (lo <= hi) {
      var mid = Math.floor((lo + hi) / 2);
      if (top(mid) > target) hi = mid - 1;
      else {
        out = mid;
        lo = mid + 1;
      }
    }
    return out + 1;
  }
  function bounds(idx) {
    return {
      start: lineStart(idx),
      end: lineEnd(idx)
    };
  }
  function ratio(b) {
    var endIdx = Math.max(b.start, Math.min(textLength - 1, b.end - 1));
    var t = top(b.start),
      bot = bottom(endIdx);
    return Math.max(0, Math.min(bot, viewBottom) - Math.max(t, viewTop)) / Math.max(1, bot - t);
  }
  var first = firstVisible(),
    last = lastVisible();
  if (first > last) last = first;
  var tb = bounds(first),
    bb = bounds(last);
  var tr = ratio(tb),
    br = ratio(bb);
  var start = tr < documentState.DOC_LINE_VISIBILITY_THRESHOLD ? tb.end : tb.start;
  var end = br < documentState.DOC_LINE_VISIBILITY_THRESHOLD ? bb.start : bb.end;
  if (start >= end) {
    if (tr >= br) {
      start = tb.start;
      end = tb.end;
    } else {
      start = bb.start;
      end = bb.end;
    }
  }
  var guard = 0;
  while (end - start > documentState.WINDOWED_MAX_CHARS && guard++ < 200) {
    var prev = lineStart(end - 1);
    if (prev <= start) break;
    end = prev;
  }
  end = Math.min(textLength, Math.max(start, end));
  return {
    text: textNode.textContent.slice(start, end),
    start: start,
    end: end
  };
}
export function getVisibleRawTextareaLookupText() {
  var slice = getVisibleRawTextareaSlice();
  var text = slice && slice.text ? slice.text : '';
  return text.length > documentState.WINDOWED_MAX_CHARS
    ? text.slice(0, documentState.WINDOWED_MAX_CHARS)
    : text;
}
export function autoResizeTextarea() {
  if (!hoverLayoutState.sourceText || documentState.inputMode !== 'raw' || documentState.rawContinuousMode)
    return;
  var maxHeight = getRawMaxHeightPx();
  var minHeight = Math.max(180, getRawMinHeightPx());
  if (maxHeight > 0) minHeight = Math.min(minHeight, maxHeight);
  // Collapse to 1px to get true content height
  hoverLayoutState.sourceText.style.height = '1px';
  var scrollH = hoverLayoutState.sourceText.scrollHeight;
  // Set height between min and max
  var newHeight = Math.max(minHeight, Math.min(scrollH, maxHeight));
  hoverLayoutState.sourceText.style.height = newHeight + 'px';
  if (maxHeight > 0 && scrollH > maxHeight + 1) {
    hoverLayoutState.sourceText.style.overflowY = 'auto';
  } else {
    hoverLayoutState.sourceText.style.overflowY = 'hidden';
  }
}

// Keep guidance visible on click/focus; clear only when user starts editing.
export function docxOriginalLookupNow() {
  if (!documentShellState.docxOriginal.rendered) {
    hoverLayoutState.statusText.textContent = 'Loading DOCX layout...';
    hoverLayoutState.statusCounts.textContent = '';
    return;
  }
  var sliceInfo = getVisibleDocxSliceText(hoverLayoutState.sourcePager);
  var sliceText = sliceInfo && sliceInfo.text ? sliceInfo.text : '';
  var sliceFragInfo = buildVisibleDocxSliceFragment(sliceInfo);
  var sliceRoot = sliceFragInfo ? sliceFragInfo.sliceRoot : null;
  if (!sliceText || !sliceRoot) {
    hoverLayoutState.renderedText.innerHTML = '';
    hoverLayoutState.statusText.textContent = 'Ready.';
    hoverLayoutState.statusCounts.textContent = '';
    if (
      !lookupProgressState.depTreeUseConllu &&
      lookupProgressState.depTreeController &&
      typeof lookupProgressState.depTreeController.setData === 'function'
    ) {
      lookupProgressState.depTreeController.setData({
        segments: [],
        udOverlay: null
      });
    }
    return;
  }
  var seqDocx = ++hoverLayoutState.latestSeq;
  hoverLayoutState.statusText.textContent = 'Segmenting...';
  hoverLayoutState.statusCounts.textContent = '';
  if (hoverLayoutState.renderedText) {
    hoverLayoutState.renderedText.classList.remove(
      'plain-text-mode',
      'docx-original-view',
      'orig-view-structured'
    );
  }
  hoverLayoutState.renderedText.innerHTML = '';
  hoverLayoutState.renderedText.appendChild(sliceRoot);
  return startSegmentLookupFetch(buildLookupUrl(sliceText))
    .then(function (resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.json();
    })
    .then(function (data) {
      if (seqDocx !== hoverLayoutState.latestSeq) return;
      if (!data || !data.ok) {
        hoverLayoutState.statusText.textContent = 'Error from server.';
        hoverLayoutState.renderedText.innerHTML =
          '<div class="reader-output-placeholder">Error: ' +
          escapeHtml(data && data.error ? data.error : 'unknown') +
          '</div>';
        return;
      }

      // Adopt lookup payload and map offsets onto the cloned visible slice DOM.
      // Canonical-text contract: server is the only authority on offsets.
      hoverLayoutState.latestData = data;
      _resetSentenceTabletGlossOverrides();
      pushLookupResolverPayload(data);
      reportLookupProgress('Rendering results');
      var segments = Array.isArray(data.segments) ? data.segments : [];
      var gramOverlay =
        data.grammar_overlay && Array.isArray(data.grammar_overlay.tokens) ? data.grammar_overlay.tokens : [];
      var resultsBySeg = Array.isArray(data.results_by_seg) ? data.results_by_seg : [];
      setLatestUdOverlay(data.ud_overlay);
      var udTokenMap = dependencyState.latestUdTokenMap || {};
      dependencyPopupState.latestChunks = computeChunks(
        dependencyState.latestUdOverlay,
        dependencyPopupState.displaySettings.chunkHighlight ? 100 : 0,
        dependencyPopupState.displaySettings.linearClauseSplit ||
          dependencyPopupState.displaySettings.udOverlay,
        dependencyPopupState.displaySettings.branchDepthMin,
        dependencyPopupState.displaySettings.clauseDepthDrop
      );
      rebuildConnectedIslandGroups();
      clearUdTokenIndex();
      invalidateUdRectCache();
      invalidateUiRectCache();
      clearAllTokenLookupState();
      hideUdLines();
      hideNerHover();
      clearChunkHighlight();
      tokenFragmentsState.hoverReticle = null;
      dependencyState.udSvgOverlay = null;
      var fillsDict = {};
      if (resultsBySeg && resultsBySeg.length) {
        resultsBySeg.forEach(function (res, idx) {
          if (res && res.dict_fill && res.dict_fill.length) {
            fillsDict[idx] = res.dict_fill;
          }
        });
      }
      hoverLayoutState.latestSegments = segments;
      lookupProgressState.latestOriginalText = sliceText;
      lookupProgressState.latestFillsDict = fillsDict;
      if (
        !lookupProgressState.depTreeUseConllu &&
        lookupProgressState.depTreeController &&
        typeof lookupProgressState.depTreeController.setData === 'function'
      ) {
        lookupProgressState.depTreeController.debugMode = false;
        lookupProgressState.depTreeController.changedTokens = null;
        lookupProgressState.depTreeController.changeDetails = null;
        lookupProgressState.depTreeController.fills = fillsDict;
        lookupProgressState.depTreeController.setData({
          segments: segments,
          udOverlay: dependencyState.latestUdOverlay,
          originalText: sliceText
        });
      }
      var segmentOffsets = data && Array.isArray(data.segment_offsets) ? data.segment_offsets : null;
      function offsetsAreValid(offsets, text, count) {
        if (!offsets || offsets.length !== count) return false;
        var lastEnd = 0;
        for (var oi = 0; oi < offsets.length; oi++) {
          var off = offsets[oi];
          if (!off || off.length < 2) return false;
          var start = Number(off[0]);
          var end = Number(off[1]);
          if (!isFinite(start) || !isFinite(end)) return false;
          if (start < lastEnd || end < start || end > text.length) return false;
          lastEnd = end;
        }
        return true;
      }
      latestSegmentOffsets = offsetsAreValid(segmentOffsets, sliceText, segments.length)
        ? segmentOffsets
        : [];
      applyOffsetsAsTokenSpansOnDom(sliceRoot, data);

      // Rebuild segment->DOM mapping for hover logic.
      var tokenSpans = sliceRoot.querySelectorAll('.reader-token');
      for (var ti = 0; ti < tokenSpans.length; ti++) {
        var span = tokenSpans[ti];
        if (!span || !span.dataset) continue;
        var idxVal = parseInt(span.dataset.index || '-1', 10);
        if (idxVal >= 0) registerTokenSpan(idxVal, span);
      }
      attachHoverHandlers(hoverLayoutState.renderedText, resultsBySeg, gramOverlay);
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          computeAndCacheRowBands();
          buildUdRectCache();
        });
      });
      hoverLayoutState.statusText.textContent = 'Ready.';
      hoverLayoutState.statusCounts.textContent = 'Segmented ' + segments.length + ' tokens.';
    })
    .catch(function (err) {
      if (seqDocx !== hoverLayoutState.latestSeq) return;
      console.error(err);
      hoverLayoutState.statusText.textContent = 'Lookup failed.';
      hoverLayoutState.renderedText.innerHTML =
        '<div class="reader-output-placeholder">Lookup request failed.</div>';
    });
}
export function initializeDocumentImport() {
  hoverLayoutState.dropZone.addEventListener('dragover', function (ev) {
    ev.preventDefault();
    hoverLayoutState.dropZone.classList.add('drag-over');
  });
  hoverLayoutState.dropZone.addEventListener('dragleave', function (ev) {
    if (ev.target === hoverLayoutState.dropZone || !hoverLayoutState.dropZone.contains(ev.relatedTarget))
      hoverLayoutState.dropZone.classList.remove('drag-over');
  });
  hoverLayoutState.dropZone.addEventListener('drop', function (ev) {
    ev.preventDefault();
    hoverLayoutState.dropZone.classList.remove('drag-over');
    var dt = ev.dataTransfer;
    if (dt && dt.files && dt.files.length) loadFile(dt.files[0]);
  });
  // ===================== ORIGINAL VIEW MODE =====================

  // Toggle between layout-aware and raw text for segmentation
  if (documentState.origViewCheckbox) {
    documentState.origViewCheckbox.addEventListener('change', function () {
      documentState.isOriginalView = documentState.origViewCheckbox.checked;
      if (documentState.inputMode === 'pdf') {
        // PDF mode: toggle only changes which text is sent for segmentation
        // PDF.js viewer stays visible regardless
        documentState.pageLookupTextByIndex = {};
        documentState.originalLayoutCache = {};
        documentState.lastLookupPageIndex = -1;
        documentState.pendingPdfLookupPageIndex = -1;
        hoverLayoutState.latestSeq += 1;
        triggerUpdate();
      } else if (documentState.currentFileType === 'docx') {
        documentState.isOriginalView = false;
        if (documentState.origViewCheckbox) documentState.origViewCheckbox.checked = false;
        setDocMode(
          documentState.docText ||
            (hoverLayoutState.sourceText ? hoverLayoutState.sourceText.value || '' : ''),
          {
            triggerLookup: false
          }
        );
        return;
      } else {
        // Other modes
        documentState.pageLookupTextByIndex = {};
        updateRenderedOutputBackground();
        triggerUpdate();
      }
    });
  }
  documentImportState.POS_COLORS_JS = {
    n: '#bbf7d0',
    v: '#fda4af',
    adj: '#fde68a',
    adv: '#fee2e2',
    part: '#e0e7ff',
    conj: '#cffafe',
    pron: '#e2e8f0',
    num: '#f5d0fe',
    int: '#fcd34d',
    post: '#bae6fd',
    punct: '#e5e7eb',
    fw: '#d1d5db',
    afx: '#fef3c7',
    ono: '#ddd6fe',
    unk: '#f3f4f6'
  };
  documentImportState.rawMeasureEl = null;
  hoverLayoutState.sourceText.addEventListener('beforeinput', function () {
    if (!isShowingInitialInputGuidance()) return;
    clearInitialInputGuidanceIfNeeded();
    autoResizeTextarea();
  });
  hoverLayoutState.sourceText.addEventListener(
    'wheel',
    function (ev) {
      if (!isRawContinuousActive()) return;
      var dy = ev && isFinite(ev.deltaY) ? ev.deltaY : 0;
      if (!dy) return;
      ev.preventDefault();
      scrollRawContinuousBy(dy);
    },
    {
      passive: false
    }
  );
  hoverLayoutState.sourceText.addEventListener('scroll', function () {
    if (isRawContinuousActive()) onRawContinuousScroll();
  });
  hoverLayoutState.sourceText.addEventListener('input', function () {
    if (lookupProgressState.initialInputGuidanceActive)
      lookupProgressState.initialInputGuidanceActive = false;
    if (documentState.inputMode !== 'raw') setRawMode();
    if (!documentState.rawContinuousMode) autoResizeTextarea();
    applyGlobalViewportClamp(false);
    var nextText = hoverLayoutState.sourceText.value || '';
    _debugShowPlainText(nextText);
    if (
      syncRawContinuousModeForSourceText({
        triggerLookup: false
      })
    ) {
      return;
    }
    if (!documentState.rawContinuousMode) autoResizeTextarea();
    triggerUpdate();
  });
  return true;
}
