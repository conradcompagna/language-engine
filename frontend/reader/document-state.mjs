import { normalizePages } from './continuous-scroll.mjs';
import { rebuildConnectedIslandGroups } from './dependency-geometry.mjs';
import { computeChunks } from './dependency-popup.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { updateRenderedOutputBackground } from './document-import.mjs';
import { cancelWebSnapshotVisibleCanonicalRefresh } from './document-navigation.mjs';
import { shouldUseTrankitChunkLookup, syncTrankitChunkLookupControls } from './document-search.mjs';
import { getPdfJsDocument } from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { documentState } from './document-state.state.mjs';
import { pushLookupResolverPayload } from './entry-editing.mjs';
import { buildTokenSpan } from './fill-rendering.mjs';
import { isCombiningMarkChar, triggerUpdate } from './fill-slices.mjs';
import { clearChunkHighlight } from './gloss-requests.mjs';
import { attachHoverHandlers, computeAndCacheRowBands } from './hover-interaction.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { _resetSentenceTabletGlossOverrides, startSegmentLookupFetch } from './lookup-progress.mjs';
import { lookupProgressState } from './lookup-progress.state.mjs';
import { setLatestUdOverlay } from './mwt-context.mjs';
import { buildLookupUrl, getSelectedDictSource } from './orthography.mjs';
import { clearAllTokenLookupState } from './segment-rendering.mjs';
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
export function isAbortError(err) {
  return err && err.name === 'AbortError';
}
export function showRawTextPill(label) {
  lookupProgressState.rawTextDocActive = true;
  if (hoverLayoutState.rawTextText) hoverLayoutState.rawTextText.textContent = label || 'Clear text';
  if (hoverLayoutState.rawTextPill) hoverLayoutState.rawTextPill.style.display = 'inline-flex';
}
export function hideRawTextPill() {
  lookupProgressState.rawTextDocActive = false;
  if (hoverLayoutState.rawTextPill) hoverLayoutState.rawTextPill.style.display = 'none';
  if (hoverLayoutState.rawTextText) hoverLayoutState.rawTextText.textContent = '';
}

// Original view toggle refs
export // bottom pane is rendered only by the canonical reader

function _debugShowPlainText(text) {
  if (!documentState.DEBUG_SHOW_PLAIN_TEXT || !hoverLayoutState.renderedText) return;
  hoverLayoutState.renderedText.innerHTML = '';
  hoverLayoutState.renderedText.style.height = '';
  hoverLayoutState.renderedText.style.maxHeight = '';
  var pre = document.createElement('pre');
  pre.style.cssText = 'white-space:pre-wrap;word-break:break-word;padding:8px;margin:0;font-size:13px;';
  pre.textContent = text || '';
  hoverLayoutState.renderedText.appendChild(pre);
}
export function _debugShowPdfSpans(idx) {
  if (!documentState.DEBUG_SHOW_PLAIN_TEXT || !hoverLayoutState.renderedText) return;
  var html = (documentState.docrenderPdfRichHtml && documentState.docrenderPdfRichHtml[idx]) || '';
  if (!html) return;
  hoverLayoutState.renderedText.innerHTML = '';
  hoverLayoutState.renderedText.style.height = '';
  hoverLayoutState.renderedText.style.maxHeight = '';
  var wrap = document.createElement('div');
  wrap.style.cssText = 'position:relative;overflow:auto;width:100%;height:100%;';
  wrap.innerHTML = html;
  hoverLayoutState.renderedText.appendChild(wrap);
}

// Legacy compatibility stubs (original view mode disabled)
export function cancelMovementLookupTimer() {
  if (!documentState.movementLookupTimer) return;
  clearTimeout(documentState.movementLookupTimer);
  documentState.movementLookupTimer = null;
}
export function requestMovementLookup() {
  cancelMovementLookupTimer();
  documentState.movementLookupTimer = setTimeout(function () {
    documentState.movementLookupTimer = null;
    triggerUpdate();
  }, documentState.MOVEMENT_LOOKUP_IDLE_MS);
}

// Original view state
export function shouldUsePdfjsTextLayer() {
  return false;
}
export function restoreLookupGateForDeferredPdfTextFetch() {
  if (typeof window.__LE_LOOKUP_ALLOWED !== 'undefined') {
    window.__LE_LOOKUP_ALLOWED = true;
  }
}
export function clearDeferredPdfLookupGate() {
  if (typeof window.__LE_LOOKUP_ALLOWED !== 'undefined') {
    window.__LE_LOOKUP_ALLOWED = false;
  }
}
export function resetCanonicalDocument() {
  cancelWebSnapshotVisibleCanonicalRefresh();
  documentState.canonicalDoc = null;
  if (
    documentState.canonicalReaderController &&
    typeof documentState.canonicalReaderController.clear === 'function'
  ) {
    documentState.canonicalReaderController.clear();
  }
  syncTrankitChunkLookupControls();
}
export function canonicalOffsetsAreValid(offsets, text, expectedCount) {
  if (!Array.isArray(offsets) || offsets.length !== expectedCount) return false;
  var lastEnd = 0;
  for (var i = 0; i < offsets.length; i++) {
    var off = offsets[i];
    if (!off || off.length < 2) return false;
    var st = Number(off[0]);
    var en = Number(off[1]);
    if (!isFinite(st) || !isFinite(en) || st < lastEnd || en < st || en > text.length) return false;
    lastEnd = en;
  }
  return true;
}
export function ensureCanonicalReaderController() {
  if (documentState.canonicalReaderController) return documentState.canonicalReaderController;
  if (!window.CanonicalReaderController) return null;
  documentState.canonicalReaderController = new window.CanonicalReaderController({
    bridge: {
      getTarget: function () {
        return hoverLayoutState.renderedText;
      },
      buildLookupUrl: function (text) {
        return buildLookupUrl(text);
      },
      fetchLookup: function (url) {
        return startSegmentLookupFetch(url).then(function (resp) {
          if (!resp.ok) throw new Error('HTTP ' + resp.status);
          return resp.json();
        });
      },
      fetchChunkedLookup: function (page, chunks) {
        // DISABLED: keep the bridge callback as a safe compatibility shim, but
        // do not send geometry chunks to Trankit. Paragraph breaks inserted in
        // the canonical page text now drive the normal lookup path.
        if (hoverLayoutState.TRANKIT_CHUNK_LOOKUP_DISABLED) {
          var normalUrl = buildLookupUrl(String((page && page.text) || ''));
          return startSegmentLookupFetch(normalUrl).then(function (resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
          });
        }
        var url = buildLookupUrl('');
        var body = {
          q: String((page && page.text) || ''),
          lang: String(documentShellState.currentLanguage || ''),
          trankit_chunked: true,
          chunks: (chunks || []).map(function (chunk, idx) {
            return {
              index: idx,
              start: Number(chunk && chunk.start) || 0,
              end: Number(chunk && chunk.end) || 0,
              text: String((chunk && chunk.text) || ''),
              offsetMap: Array.isArray(chunk && chunk.offsetMap) ? chunk.offsetMap : []
            };
          })
        };
        return startSegmentLookupFetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(body)
        }).then(function (resp) {
          if (!resp.ok) throw new Error('HTTP ' + resp.status);
          return resp.json();
        });
      },
      getLookupOptions: function (page) {
        return {
          language: String(documentShellState.currentLanguage || ''),
          dictSource: String(getSelectedDictSource ? getSelectedDictSource() || '' : ''),
          settingsKey: JSON.stringify({
            manualSentenceSegmentation: !!(
              dependencyPopupState.displaySettings &&
              dependencyPopupState.displaySettings.manualSentenceSegmentation
            ),
            stripPunctuation: !!(
              dependencyPopupState.displaySettings && dependencyPopupState.displaySettings.stripPunctuation
            ),
            pageLength: page && page.text ? page.text.length : 0
          })
        };
      },
      getLookupChunks: function (page) {
        if (hoverLayoutState.TRANKIT_CHUNK_LOOKUP_DISABLED) return null;
        if (!documentState.trankitChunkLookupEnabled) return null;
        if (!window.LookupChunks || typeof window.LookupChunks.buildLookupChunks !== 'function') {
          throw new Error('Trankit chunk lookup module is unavailable.');
        }
        return window.LookupChunks.buildLookupChunks(page, {
          drawRuns: false,
          drawLines: false,
          drawEdges: false
        });
      },
      onStatus: function (message, page) {
        if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = message || '';
        if (hoverLayoutState.statusCounts && documentState.canonicalDoc && documentState.canonicalDoc.pages) {
          hoverLayoutState.statusCounts.textContent =
            'Page ' + (((page && page.index) || 0) + 1) + ' / ' + documentState.canonicalDoc.pages.length;
        }
      },
      onEmptyPage: function (page) {
        if (hoverLayoutState.renderedText) hoverLayoutState.renderedText.innerHTML = '';
        if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Ready.';
        if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
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
      },
      onBeforeLookup: function (page) {
        documentState.pageLookupTextByIndex[(page && page.index) || 0] = String((page && page.text) || '');
        hoverLayoutState.latestSeq += 1;
        if (hoverLayoutState.renderedText) {
          hoverLayoutState.renderedText.classList.remove(
            'plain-text-mode',
            'docx-original-view',
            'orig-view-structured',
            'docrender-active'
          );
        }
      },
      onLookupPayload: function (data, page) {
        hoverLayoutState.latestData = data;
        try {
          _resetSentenceTabletGlossOverrides();
        } catch (e) {}
        try {
          pushLookupResolverPayload(data);
        } catch (e2) {}
        hoverLayoutState.latestSegments = Array.isArray(data && data.segments) ? data.segments : [];
        lookupProgressState.latestOriginalText = String((page && page.text) || '');
        setLatestUdOverlay(data && data.ud_overlay);
        var segmentOffsets = data && Array.isArray(data.segment_offsets) ? data.segment_offsets : [];
        latestSegmentOffsets = canonicalOffsetsAreValid(
          segmentOffsets,
          lookupProgressState.latestOriginalText,
          hoverLayoutState.latestSegments.length
        )
          ? segmentOffsets
          : [];
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
      },
      onAnnotatedPage: function (page, data) {
        lookupProgressState.latestFillsDict =
          window.CanonicalAnnotator && window.CanonicalAnnotator.buildFillsDict
            ? window.CanonicalAnnotator.buildFillsDict(page)
            : {};
        if (
          !lookupProgressState.depTreeUseConllu &&
          lookupProgressState.depTreeController &&
          typeof lookupProgressState.depTreeController.setData === 'function'
        ) {
          lookupProgressState.depTreeController.debugMode = false;
          lookupProgressState.depTreeController.changedTokens = null;
          lookupProgressState.depTreeController.changeDetails = null;
          lookupProgressState.depTreeController.fills = lookupProgressState.latestFillsDict;
          lookupProgressState.depTreeController.setData({
            segments: hoverLayoutState.latestSegments,
            udOverlay: dependencyState.latestUdOverlay,
            originalText: lookupProgressState.latestOriginalText
          });
        }
      },
      getRendererOptions: function (page, data) {
        var resultsBySeg = Array.isArray(data && data.results_by_seg) ? data.results_by_seg : [];
        var gramOverlay =
          data && data.grammar_overlay && Array.isArray(data.grammar_overlay.tokens)
            ? data.grammar_overlay.tokens
            : [];
        var udTokenMap = dependencyState.latestUdTokenMap || {};
        return {
          direction: hoverLayoutState.currentTextDirection || 'ltr',
          buildTokenElement: function (token, text, ctx) {
            if (!token || text !== token.text) return null;
            try {
              var built = buildTokenSpan(
                token.index,
                token.segment || text,
                gramOverlay,
                resultsBySeg,
                udTokenMap,
                {
                  noMwtSideEffects: !!(ctx && ctx.isTokenFragment)
                }
              );
              return built && built.span ? built.span : null;
            } catch (e) {
              return null;
            }
          }
        };
      },
      onRenderedPage: function (page, data, root) {
        var resultsBySeg = Array.isArray(data && data.results_by_seg) ? data.results_by_seg : [];
        var gramOverlay =
          data && data.grammar_overlay && Array.isArray(data.grammar_overlay.tokens)
            ? data.grammar_overlay.tokens
            : [];
        var scope = hoverLayoutState.renderedText || root || document;
        var tokenSpans = scope.querySelectorAll ? scope.querySelectorAll('.reader-token') : [];
        for (var ti = 0; ti < tokenSpans.length; ti++) {
          var sp = tokenSpans[ti];
          if (!sp || !sp.dataset) continue;
          var idxVal = parseInt(sp.dataset.index || '-1', 10);
          if (idxVal >= 0) registerTokenSpan(idxVal, sp);
        }
        try {
          attachHoverHandlers(hoverLayoutState.renderedText, resultsBySeg, gramOverlay);
        } catch (e) {}
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            try {
              computeAndCacheRowBands();
            } catch (e1) {}
            try {
              buildUdRectCache();
            } catch (e2) {}
          });
        });
        if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Ready.';
        if (hoverLayoutState.statusCounts)
          hoverLayoutState.statusCounts.textContent =
            'Segmented ' + hoverLayoutState.latestSegments.length + ' tokens.';
        try {
          updateRenderedOutputBackground();
        } catch (e3) {}
      },
      onError: function (err) {
        if (isAbortError && isAbortError(err)) return;
        console.error('Canonical document lookup/render failed:', err);
        if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Lookup failed.';
        if (hoverLayoutState.renderedText)
          hoverLayoutState.renderedText.innerHTML =
            '<div class="reader-output-placeholder">Lookup request failed.</div>';
        try {
          updateRenderedOutputBackground();
        } catch (e) {}
      }
    }
  });
  return documentState.canonicalReaderController;
}
export function setCanonicalDocument(doc, opts) {
  opts = opts || {};
  var ctl = ensureCanonicalReaderController();
  if (!ctl || !doc) return null;
  documentState.canonicalDoc = doc;
  ctl.setDocument(doc, {
    pageIndex: opts.pageIndex || 0,
    clearCache: opts.clearCache !== false
  });
  documentState.docPages = (doc.pages || []).map(function (p) {
    return String((p && p.text) || '');
  });
  documentState.docText = documentState.docPages.join('\n\n');
  documentState.activePageIndex = Math.max(
    0,
    Math.min((documentState.docPages.length || 1) - 1, opts.pageIndex || 0)
  );
  documentState.pageLookupTextByIndex = {};
  syncTrankitChunkLookupControls();
  return doc;
}
export function setCanonicalDocumentFromDocRenderPages(pages, meta, opts) {
  console.warn('DocRender canonical conversion is disabled for legacy page inputs.', pages, meta, opts);
  return null;
}
export function setCanonicalDocumentFromPlainPages(pages, meta, opts) {
  if (!window.CanonicalBuilder || typeof window.CanonicalBuilder.fromText !== 'function') return null;
  opts = opts || {};
  var text = normalizePages(pages || ['']).join('\n\n');
  var doc = window.CanonicalBuilder.fromText(text, {
    meta: meta || {
      format: 'text'
    }
  });
  return setCanonicalDocument(doc, opts);
}
export function lookupCurrentCanonicalPage() {
  var ctl = ensureCanonicalReaderController();
  if (!ctl || !documentState.canonicalDoc) return false;
  return ctl.lookupAndRenderPage(documentState.activePageIndex || 0, {
    useCache: true,
    chunkedLookup: shouldUseTrankitChunkLookup()
  });
}
export function lookupCurrentPdfCanonicalPage(pageIdx) {
  var idx = Math.max(0, Math.min((documentState.docPages.length || 1) - 1, Math.floor(Number(pageIdx) || 0)));
  return ensurePdfCanonicalPage(idx)
    .then(function (ok) {
      if (!ok) {
        if (hoverLayoutState.statusText)
          hoverLayoutState.statusText.textContent = 'PDF text is still loading.';
        if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
        if (hoverLayoutState.renderedText)
          hoverLayoutState.renderedText.innerHTML =
            '<div class="reader-output-placeholder">The browser PDF text layer is not ready yet.</div>';
        return true;
      }
      if (
        documentState.inputMode !== 'pdf' ||
        idx !==
          Math.max(0, Math.min((documentState.docPages.length || 1) - 1, documentState.activePageIndex || 0))
      ) {
        return true;
      }
      var lookupResult = lookupCurrentCanonicalPage();
      if (lookupResult) {
        documentState.lastLookupPageIndex = idx;
        documentState.pendingPdfLookupPageIndex = -1;
        return lookupResult;
      }
      return false;
    })
    .catch(function (err) {
      if (isAbortError && isAbortError(err)) return;
      console.error('PDF page extraction failed:', err);
      if (hoverLayoutState.statusText)
        hoverLayoutState.statusText.textContent = 'PDF text extraction failed.';
      if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
      if (hoverLayoutState.renderedText)
        hoverLayoutState.renderedText.innerHTML =
          '<div class="reader-output-placeholder">Could not extract text for this PDF page.</div>';
    });
}
export function warmPdfCanonicalPage(pageIdx, reason) {
  if (documentState.inputMode !== 'pdf') return Promise.resolve(false);
  var idx = Math.max(0, Math.min((documentState.docPages.length || 1) - 1, Math.floor(Number(pageIdx) || 0)));
  return ensurePdfCanonicalPage(idx, {
    silent: true,
    reason: reason || 'visual-page'
  })
    .then(function (ok) {
      return !!ok;
    })
    .catch(function (err) {
      if (!(isAbortError && isAbortError(err))) {
        console.warn('PDF page text warmup failed:', err);
      }
      return false;
    });
}
export function getPdfCanonicalMeta(extra) {
  return Object.assign(
    {
      format: 'pdf',
      parser: 'canonical-pdfjs-extractor',
      fileName:
        documentState.currentFile && documentState.currentFile.name ? documentState.currentFile.name : '',
      clientSide: true
    },
    extra || {}
  );
}
export function makeEmptyPdfCanonicalPage(pageIdx) {
  var idx = Math.max(0, Math.floor(Number(pageIdx) || 0));
  var dim =
    (documentShellState.pdfPageDimensions && documentShellState.pdfPageDimensions[idx]) ||
    documentShellState.pdfAveragePageDimensions ||
    {};
  var width = Number(dim && dim.width) || 612;
  var height = Number(dim && dim.height) || 792;
  var page =
    window.CanonicalModel && typeof window.CanonicalModel.makePage === 'function'
      ? window.CanonicalModel.makePage({
          id: 'pdf-page-' + idx,
          index: idx,
          text: '',
          blocks: [],
          tokens: [],
          layout: {
            mode: 'fixed',
            width: width,
            height: height,
            pageIndex: idx
          },
          source: {
            extractor: 'canonical-pdfjs',
            sourcePageIndex: idx,
            pdfjs: true,
            lazyPlaceholder: true,
            pdfTextLoaded: false
          }
        })
      : {
          id: 'pdf-page-' + idx,
          index: idx,
          text: '',
          blocks: [],
          tokens: [],
          layout: {
            mode: 'fixed',
            width: width,
            height: height,
            pageIndex: idx
          },
          source: {
            extractor: 'canonical-pdfjs',
            sourcePageIndex: idx,
            pdfjs: true,
            lazyPlaceholder: true,
            pdfTextLoaded: false
          }
        };
  return page;
}
export function createLazyPdfCanonicalDocument(pdfDoc) {
  if (!window.CanonicalModel || typeof window.CanonicalModel.makeDocument !== 'function') {
    throw new Error('CanonicalModel is not loaded');
  }
  var pageCount = Math.max(1, Math.floor(Number(pdfDoc && pdfDoc.numPages) || 1));
  var pages = [];
  for (var i = 0; i < pageCount; i++) {
    pages.push(makeEmptyPdfCanonicalPage(i));
  }
  return window.CanonicalModel.makeDocument({
    meta: getPdfCanonicalMeta({
      pageCount: pageCount,
      lazyTextExtraction: true
    }),
    pages: pages,
    source: {
      extractor: 'canonical-pdfjs',
      clientSide: true,
      lazyTextExtraction: true
    }
  });
}
export function ensureLazyPdfCanonicalDocument(pdfDoc) {
  var pageCount = Math.max(
    1,
    Math.floor(
      Number(pdfDoc && pdfDoc.numPages) || (documentState.docPages && documentState.docPages.length) || 1
    )
  );
  var existingPages =
    documentState.canonicalDoc && Array.isArray(documentState.canonicalDoc.pages)
      ? documentState.canonicalDoc.pages
      : null;
  if (
    existingPages &&
    existingPages.length === pageCount &&
    documentState.canonicalDoc.source &&
    documentState.canonicalDoc.source.extractor === 'canonical-pdfjs'
  ) {
    return documentState.canonicalDoc;
  }
  return setCanonicalDocument(
    createLazyPdfCanonicalDocument({
      numPages: pageCount
    }),
    {
      pageIndex: Math.max(0, Math.min(pageCount - 1, documentState.activePageIndex || 0)),
      clearCache: true
    }
  );
}
export function installPdfCanonicalPage(pageIdx, data) {
  var idx = Math.max(0, Math.floor(Number(pageIdx) || 0));
  var page =
    documentState.canonicalDoc && documentState.canonicalDoc.pages
      ? documentState.canonicalDoc.pages[idx]
      : null;
  return page ? String(page.text || '') : '';
}
export function ensurePdfCanonicalPage(pageIdx, options) {
  var opts = options || {};
  var idx = Math.max(0, Math.floor(Number(pageIdx) || 0));
  if (
    documentState.canonicalDoc &&
    documentState.canonicalDoc.pages &&
    documentState.canonicalDoc.pages[idx] &&
    documentState.canonicalDoc.pages[idx].source &&
    documentState.canonicalDoc.pages[idx].source.pdfTextLoaded
  ) {
    return Promise.resolve(true);
  }
  if (documentState.pdfCanonicalPageFetches && documentState.pdfCanonicalPageFetches[idx]) {
    if (!opts.silent && hoverLayoutState.statusText) {
      hoverLayoutState.statusText.textContent = 'Extracting PDF page ' + (idx + 1) + '...';
    }
    return documentState.pdfCanonicalPageFetches[idx];
  }
  if (!documentState.currentFile) return Promise.resolve(false);
  if (!window.CanonicalPdfExtractor || typeof window.CanonicalPdfExtractor.pageFromPdfJsPage !== 'function') {
    return Promise.reject(new Error('CanonicalPdfExtractor is not loaded'));
  }
  var seq = documentShellState.pdfOriginal.renderSeq;
  var promise = getPdfJsDocument(documentState.currentFile)
    .then(function (pdfDoc) {
      if (seq !== documentShellState.pdfOriginal.renderSeq || documentState.inputMode !== 'pdf') return false;
      ensureLazyPdfCanonicalDocument(pdfDoc);
      var pageCount = Math.max(1, Math.floor(Number(pdfDoc && pdfDoc.numPages) || 1));
      idx = Math.max(0, Math.min(pageCount - 1, idx));
      if (
        documentState.canonicalDoc &&
        documentState.canonicalDoc.pages &&
        documentState.canonicalDoc.pages[idx] &&
        documentState.canonicalDoc.pages[idx].source &&
        documentState.canonicalDoc.pages[idx].source.pdfTextLoaded
      ) {
        return true;
      }
      if (!opts.silent && hoverLayoutState.statusText)
        hoverLayoutState.statusText.textContent =
          'Extracting PDF page ' + (idx + 1) + ' / ' + pageCount + '...';
      if (!opts.silent && hoverLayoutState.statusCounts)
        hoverLayoutState.statusCounts.textContent = 'Page ' + (idx + 1) + ' / ' + pageCount;
      return pdfDoc
        .getPage(idx + 1)
        .then(function (pdfPage) {
          if (seq !== documentShellState.pdfOriginal.renderSeq || documentState.inputMode !== 'pdf')
            return false;
          return window.CanonicalPdfExtractor.pageFromPdfJsPage(pdfPage, idx, {
            scale: 1,
            meta: getPdfCanonicalMeta({
              lazyTextExtraction: true
            })
          });
        })
        .then(function (page) {
          if (!page || seq !== documentShellState.pdfOriginal.renderSeq || documentState.inputMode !== 'pdf')
            return false;
          page.source = Object.assign({}, page.source || {}, {
            pdfTextLoaded: true,
            lazyPlaceholder: false
          });
          if (!documentState.canonicalDoc || !documentState.canonicalDoc.pages)
            ensureLazyPdfCanonicalDocument(pdfDoc);
          documentState.canonicalDoc.pages[idx] = page;
          documentState.docPages[idx] = String(page.text || '');
          documentState.docText = documentState.docPages.join('\n\n');
          documentState.pdfRawPageTextLoaded[idx] = true;
          var ctl = ensureCanonicalReaderController();
          if (ctl && documentState.canonicalDoc) {
            ctl.setDocument(documentState.canonicalDoc, {
              pageIndex: idx,
              clearCache: false
            });
          }
          syncTrankitChunkLookupControls();
          return true;
        });
    })
    .finally(function () {
      if (documentState.pdfCanonicalPageFetches) delete documentState.pdfCanonicalPageFetches[idx];
    });
  documentState.pdfCanonicalPageFetches[idx] = promise;
  return promise;
}
export function getPageLimitProfile(lang) {
  return {
    target: 2000,
    hard: 2400,
    lineCap: 75
  };
}
export function normalizeDocumentText(text) {
  return String(text || '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n');
}
export function isDocCountedChar(ch) {
  if (!ch) return false;
  if (/\s/.test(ch)) return false;
  if (ch === '\u200b' || ch === '\ufeff') return false;
  return !isCombiningMarkChar(ch);
}
export function countDocumentChars(text) {
  var value = normalizeDocumentText(text);
  var count = 0;
  for (var i = 0; i < value.length;) {
    var cp = value.codePointAt(i);
    var ch = String.fromCodePoint(cp);
    if (isDocCountedChar(ch)) count++;
    i += ch.length;
  }
  return count;
}
export function exceedsRawDocumentThreshold(text, lang) {
  var profile = getPageLimitProfile(lang);
  return countDocumentChars(text) > profile.target;
}
export function classifyPageBreakChar(ch, nextCh) {
  if (!ch) return 0;
  if (ch === '\n' && nextCh === '\n') return 1;
  if (ch === '\n') return 2;
  if ('.!?。！？｡．؟।॥…'.indexOf(ch) >= 0) return 1;
  if (',;:，、；：،؛'.indexOf(ch) >= 0) return 3;
  if (/\s/.test(ch)) return 4;
  return 0;
}
export function chooseArtificialPageBreak(candidates, targetIndex, hardIndex) {
  if (!candidates.length) return hardIndex;
  var after = null;
  var before = null;
  for (var i = 0; i < candidates.length; i++) {
    var c = candidates[i];
    if (!c || c.index <= 0 || c.index > hardIndex) continue;
    if (c.index >= targetIndex) {
      if (
        !after ||
        c.rank < after.rank ||
        (c.rank === after.rank && Math.abs(c.index - targetIndex) < Math.abs(after.index - targetIndex))
      ) {
        after = c;
      }
    } else if (!before || c.rank < before.rank || (c.rank === before.rank && c.index > before.index)) {
      before = c;
    }
  }
  return (after || before || candidates[candidates.length - 1]).index || hardIndex;
}
export function buildArtificialPages(text, lang) {
  var value = normalizeDocumentText(text);
  if (!value) return [''];
  var profile = getPageLimitProfile(lang);
  var pages = [];
  var len = value.length;
  var start = 0;
  while (start < len) {
    while (start < len && /\s/.test(value.charAt(start))) start++;
    if (start >= len) break;
    var visible = 0;
    var lines = 1;
    var targetIndex = -1;
    var hardIndex = -1;
    var candidates = [];
    var minVisibleForBreak = Math.max(80, Math.floor(profile.target * 0.35));
    for (var i = start; i < len;) {
      var cp = value.codePointAt(i);
      var ch = String.fromCodePoint(cp);
      var next = i + ch.length;
      var nextCh = next < len ? value.charAt(next) : '';
      if (isDocCountedChar(ch)) visible++;
      if (ch === '\n') lines++;
      var rank = classifyPageBreakChar(ch, nextCh);
      if (rank && visible >= minVisibleForBreak) {
        candidates.push({
          index: next,
          rank: rank
        });
      }
      if (
        targetIndex < 0 &&
        (visible >= profile.target || lines >= Math.max(8, Math.floor(profile.lineCap * 0.82)))
      ) {
        targetIndex = next;
      }
      if (visible >= profile.hard || lines >= profile.lineCap) {
        hardIndex = next;
        break;
      }
      i = next;
    }
    if (hardIndex < 0) hardIndex = len;
    if (targetIndex < 0) targetIndex = hardIndex;
    var end = chooseArtificialPageBreak(candidates, targetIndex, hardIndex);
    if (end <= start) end = hardIndex;
    if (end <= start) end = Math.min(len, start + 1);
    var page = value.slice(start, end).replace(/^\s+/, '').replace(/\s+$/, '');
    if (page) pages.push(page);
    start = end;
  }
  return pages.length ? pages : [''];
}
export function getDocumentViewportWidth() {
  var width = 0;
  if (hoverLayoutState.sourcePager) {
    width =
      hoverLayoutState.sourcePager.getBoundingClientRect().width ||
      hoverLayoutState.sourcePager.clientWidth ||
      0;
  }
  if (!width && hoverLayoutState.docViewportWrap) {
    var wrapRect = hoverLayoutState.docViewportWrap.getBoundingClientRect();
    width = Math.max(0, (wrapRect.width || hoverLayoutState.docViewportWrap.clientWidth || 0) - 32);
  }
  return Math.max(320, Math.floor(width || 620));
}
export function initializeDocumentState() {
  documentState.origViewToggle = document.getElementById('origViewToggle');
  documentState.origViewCheckbox = document.getElementById('origViewCheckbox');
  // Toggle is permanently retired — every doc goes through the docrender
  // canonical-HTML pipeline. Hide once at startup; keep variables in scope
  // because legacy branches still reference them.
  if (documentState.origViewToggle) documentState.origViewToggle.style.display = 'none';
  if (documentState.origViewCheckbox) documentState.origViewCheckbox.checked = true;

  // ------------------------------
  // Document viewing (fixed paginated source viewport)
  // ------------------------------

  documentState.inputMode = 'raw';
  documentState.docText = ''; // Full document text (continuous source)
  documentState.WINDOWED_MAX_CHARS = 5000; // Legacy cap retained for compatibility guards
  documentState.DOC_LINES_EMPTY = 5;
  documentState.DOC_LINES_CONTENT = 60;
  documentState.docLineHeight = 20;
  documentState.DOC_LINE_VISIBILITY_THRESHOLD = 0.5;
  documentState.docPagerIsPaged = false;
  documentState.docViewportHeightPx = 0;
  documentState.docPageScrollTopByIndex = {};
  documentState.lastDocWheelPageAt = 0;
  documentState.rawContinuousMode = false;
  documentState.rawContinuousReadOnly = false;
  documentState.rawContinuousForce = false;
  documentState.rawTextFoliateLoadSeq = 0;
  documentState.DEBUG_SHOW_PLAIN_TEXT = false;
  documentState.docPages = [];
  documentState.activePageIndex = 0;
  documentState.lastLookupPageIndex = -1;
  documentState.trankitChunkLookupEnabled = false;
  documentState.pendingPdfLookupPageIndex = -1;
  documentState.pageLookupTextByIndex = {};
  documentState.MOVEMENT_LOOKUP_IDLE_MS = 1000;
  documentState.movementLookupTimer = null;
  documentState.currentFile = null; // Store the File object for re-fetching
  documentState.currentFileType = null; // 'pdf', 'docx', or 'text'
  documentState.pdfCacheId = null; // Legacy server PDF cache ID; active PDF path is browser-only.
  documentState.isOriginalView = false; // Toggle state (controls layout vs raw text for segmentation)
  documentState.originalLayoutCache = {}; // Cached layout text per page index
  documentState.pdfjsTextLayerCache = {}; // pageIndex -> { innerHTML, plainText, layerClass, layerStyle, computedScaleFactor, computedTotalScaleFactor, viewportWidth, viewportHeight }
  documentState.pdfRawPageTextLoaded = {}; // pageIndex -> true once client-side PDF text is available
  documentState.pdfCanonicalPageFetches = {}; // legacy placeholder; active PDF text is built up front in the browser
  documentState.renderedPageImages = {
    byIndex: {}
  }; // Per-page rendering data for output panel positioned view
  // ---- DocRender (client-side parsing + CSS-columns pagination + layout preservation) ----
  // Parallel to docPages. When non-null at a given index, the top pane renders this
  // rich HTML (preserving original source layout) and the bottom pane clones it and
  // weaves in reader-token spans via applyOffsetsAsTokenSpansOnDom — same machinery
  // the existing DOCX original-view path already uses.
  documentState.docSourcePages = [];
  documentState.docPageRichHtml = [];
  documentState.docPageTextMaps = [];
  documentState.docrenderMeta = null;
  documentState.docrenderActive = false;
  documentState.docrenderPageHeightPx = 0;
  documentState.docrenderPageWidthPx = 0;
  documentState.webSnapshotCanonicalSeq = 0;
  documentState.webSnapshotInspectorEnabled = false;
  documentState.webSnapshotSelectedText = '';
  documentState.webSnapshotVisibleCanonicalRefreshTimer = null;

  // EPUB renderer state (Foliate, with epub.js left only as an inert fallback asset)
  documentState.epubJsBook = null;
  documentState.epubJsRendition = null;
  documentState.epubJsCurrentText = '';
  documentState.epubJsCanGoPrev = false;
  documentState.epubJsCanGoNext = false;
  documentState.epubJsPageLabel = 'Ebook';
  documentState.epubJsCurrentPageNum = 0;
  documentState.epubJsTotalPages = 1;
  documentState.foliateModulePromise = null;
  documentState.epubVisibleRange = null;
  documentState.epubResizeObserver = null;
  documentState.epubLoadSeq = 0;
  documentState.epubJsScrollTimer = null;
  documentState.foliateFlowActive = false;
  documentState.foliateFlowCanonicalBuildSeq = 0;
  documentState.foliateFlowBuildingCanonical = false;
  documentState.foliateFlowLabel = 'Document';
  documentState.foliateFlowSections = [];
  documentState.foliateFlowSectionPageCounts = [];
  documentState.foliateFlowSectionStartPages = [];
  documentState.foliateFlowTotalPages = 1;
  documentState.foliateNativeMeasuredSectionPageCounts = [];
  documentState.foliateFullPaginationReady = false;
  documentState.foliateFullPaginationRunning = false;
  documentState.foliateFullPaginationSeq = 0;
  documentState.foliateFullPaginationError = null;
  documentState.documentCapabilities = {
    source: '',
    toc: [],
    pageList: []
  };
  documentState.documentSearchResults = [];
  documentState.documentSearchActiveIndex = -1;
  documentState.documentSearchTotalCount = 0;
  documentState.documentSearchRunSeq = 0;
  documentState.documentSearchPending = false;
  // PDF mode is hybrid: legacy pdfJsIframe shows the rendered PDF page (with
  // zoom/search controls) in the top pane, while the canonical PDF extractor
  // builds the bottom-pane document from PDF.js text geometry.
  documentState.docrenderPdfRichHtml = []; // pageIndex -> rich HTML string
  documentState.docrenderPdfText = []; // pageIndex -> canonical text matching DOM concat
  documentState.docrenderPdfTextMap = []; // pageIndex -> [{start,end,path}] mapping canonical text to PDF HTML text nodes

  // Canonical bottom-pane document. Top pane remains source/rich rendering;
  // bottom pane renders this styled textual skeleton with NLP annotations.
  documentState.canonicalDoc = null;
  documentState.canonicalReaderController = null;
  return true;
}
