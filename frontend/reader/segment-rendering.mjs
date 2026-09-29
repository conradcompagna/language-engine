import {
  matchTokenWithInvisibleChars,
  normalizeBlockFontSizes,
  normalizeLinePositions
} from './annotations.mjs';
import { rebuildConnectedIslandGroups } from './dependency-geometry.mjs';
import { computeChunks } from './dependency-popup.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { syncInlineDepTree } from './dependency-state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { shouldInsertSpace } from './document-import.mjs';
import { isMyanmarChar } from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { shouldUsePdfjsTextLayer } from './document-state.mjs';
import { documentState } from './document-state.state.mjs';
import { annotatePdfJsTextLayerSpans, annotateRawWordSpans, buildTokenSpan } from './fill-rendering.mjs';
import { clearChunkHighlight } from './gloss-requests.mjs';
import { attachHoverHandlers, computeAndCacheRowBands } from './hover-interaction.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { lookupProgressState } from './lookup-progress.state.mjs';
import { setLatestUdOverlay } from './mwt-context.mjs';
import { getEntryDisplayHead } from './presentation.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
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
export function renderSegments(data, rawText) {
  if (hoverLayoutState.renderedText) {
    hoverLayoutState.renderedText.classList.remove('plain-text-mode', 'docx-original-view');
  }
  var segments = Array.isArray(data.segments) ? data.segments : [];
  var gramOverlay =
    data.grammar_overlay && Array.isArray(data.grammar_overlay.tokens) ? data.grammar_overlay.tokens : [];
  var resultsBySeg = Array.isArray(data.results_by_seg) ? data.results_by_seg : [];
  // Store UD overlay for dependency visualization
  setLatestUdOverlay(data.ud_overlay);
  var udTokenMap = dependencyState.latestUdTokenMap || {};
  function shouldPreventTokenWrap() {
    return (
      !documentState.isOriginalView &&
      (lookupProgressState.rawTextDocActive ||
        documentState.inputMode === 'raw' ||
        documentState.currentFileType === 'text' ||
        documentState.currentFileType === 'docx' ||
        documentState.currentFileType === 'pdf')
    );
  }
  function applyPlainTextNoWrap(span) {
    if (!span || !shouldPreventTokenWrap()) return;
    span.style.whiteSpace = 'nowrap';
    span.style.overflowWrap = 'normal';
    span.style.wordBreak = 'normal';
  }
  // Collapsed span info + UD token map already rebuilt via setLatestUdOverlay()
  // Compute chunks from UD overlay (use max depth 100 when enabled)
  dependencyPopupState.latestChunks = computeChunks(
    dependencyState.latestUdOverlay,
    dependencyPopupState.displaySettings.chunkHighlight ? 100 : 0,
    dependencyPopupState.displaySettings.linearClauseSplit || dependencyPopupState.displaySettings.udOverlay,
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
  tokenFragmentsState.hoverReticle = null; // Reset hover reticle overlay
  dependencyState.udSvgOverlay = null; // Reset SVG overlay
  var n = segments.length;
  if (!n) {
    hoverLayoutState.renderedText.innerHTML =
      '<div class="reader-output-placeholder">No segments found.</div>';
    hoverLayoutState.statusText.textContent = 'No segments.';
    hoverLayoutState.statusCounts.textContent = '';
    syncInlineDepTree('no-segments');
    return;
  }
  var text =
    data && data.display_text
      ? data.display_text
      : rawText != null
        ? rawText
        : hoverLayoutState.sourceText.value || '';
  if (shouldUsePdfjsTextLayer() && documentState.isOriginalView && rawText != null) {
    text = String(rawText);
  }
  // Build fills dict for dictionary popups (dict_fill contains the entries)
  var fillsDict = {};
  if (resultsBySeg && resultsBySeg.length) {
    resultsBySeg.forEach(function (res, idx) {
      if (res && res.dict_fill && res.dict_fill.length) {
        fillsDict[idx] = res.dict_fill;
      }
    });
  }
  // Canonical-text contract: server is the only authority on offsets.
  hoverLayoutState.latestSegments = segments;
  lookupProgressState.latestOriginalText = text;
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
      originalText: text
    });
  }
  syncInlineDepTree('render-segments');
  var frag = document.createDocumentFragment();
  var segmentOffsets = data && Array.isArray(data.segment_offsets) ? data.segment_offsets : null;
  var grammarCount = 0,
    unknownCount = 0;
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
  if (offsetsAreValid(segmentOffsets, text, n)) {
    latestSegmentOffsets = segmentOffsets;

    // ---- PDF.js text layer rendering path ----
    var tlCacheEntry =
      shouldUsePdfjsTextLayer() && documentState.isOriginalView
        ? documentState.pdfjsTextLayerCache[documentState.lastLookupPageIndex]
        : null;
    if (shouldUsePdfjsTextLayer() && documentState.isOriginalView && tlCacheEntry && tlCacheEntry.innerHTML) {
      var tlOuter = document.createElement('div');
      tlOuter.className = 'pdfjs-textlayer-container';
      var tlHost = document.createElement('div');
      tlHost.className = 'pdfjs-textlayer-host';
      var vpW = Number(tlCacheEntry.viewportWidth) || 0;
      var vpH = Number(tlCacheEntry.viewportHeight) || 0;
      var panelW =
        hoverLayoutState.renderedText.clientWidth || hoverLayoutState.renderedText.offsetWidth || 0;
      var fitScale = 1;
      if (vpW > 0 && panelW > 0) {
        fitScale = panelW / vpW;
        tlHost.style.width = panelW + 'px';
        if (vpH > 0) tlHost.style.height = Math.max(1, Math.round(panelW * (vpH / vpW))) + 'px';
      } else {
        if (vpW > 0) tlHost.style.width = vpW + 'px';
        if (vpH > 0) tlHost.style.height = vpH + 'px';
      }
      var tlLayer = document.createElement('div');
      tlLayer.className = (tlCacheEntry.layerClass || 'textLayer') + ' pdfjs-textlayer-clone';
      if (tlCacheEntry.layerStyle) {
        tlLayer.setAttribute('style', String(tlCacheEntry.layerStyle));
      }
      var baseScale =
        Number(tlCacheEntry.computedScaleFactor) ||
        parseFloat(tlLayer.style.getPropertyValue('--scale-factor')) ||
        1;
      var baseTotalScale =
        Number(tlCacheEntry.computedTotalScaleFactor) ||
        parseFloat(tlLayer.style.getPropertyValue('--total-scale-factor')) ||
        baseScale;
      tlLayer.style.setProperty('--scale-factor', String(baseScale * fitScale));
      tlLayer.style.setProperty('--total-scale-factor', String(baseTotalScale * fitScale));
      tlLayer.innerHTML = String(tlCacheEntry.innerHTML || '');
      tlHost.appendChild(tlLayer);
      tlOuter.appendChild(tlHost);
      frag.appendChild(tlOuter);
      var tlWordSpans = tlLayer.querySelectorAll('span');
      annotatePdfJsTextLayerSpans(
        tlWordSpans,
        segments,
        segmentOffsets,
        resultsBySeg,
        gramOverlay,
        udTokenMap
      );
      var _dbgSlice = tlLayer;
      var _dbgAllTokens = _dbgSlice.querySelectorAll('.reader-token');
      var _dbgFillHits = _dbgSlice.querySelectorAll('.reader-token-fill-hit');
      var _dbgFragmented = 0;
      var _dbgSeenIdx = {};
      for (var _di = 0; _di < _dbgAllTokens.length; _di++) {
        var _dt = _dbgAllTokens[_di];
        var _didx = _dt && _dt.dataset && _dt.dataset.index;
        if (_didx != null) {
          if (_dbgSeenIdx[_didx]) _dbgFragmented++;
          else _dbgSeenIdx[_didx] = 1;
        }
      }
      window.__LE_pdfWordSpanDebug = {
        wordSpanCount: tlWordSpans.length,
        segmentCount: segments.length,
        readerTokenCount: _dbgAllTokens.length,
        fillHitCount: _dbgFillHits.length,
        fragmentedTokenGroups: _dbgFragmented,
        unmatchedSegments: segments.length - Object.keys(_dbgSeenIdx).length
      };
      hoverLayoutState.renderedText.innerHTML = '';
      hoverLayoutState.renderedText.appendChild(frag);
      hideNerHover();
      attachHoverHandlers(hoverLayoutState.renderedText, resultsBySeg, gramOverlay);
      hoverLayoutState.statusText.textContent = 'Segmented ' + n + ' tokens (PDF.js text layer).';
      hoverLayoutState.statusCounts.textContent = documentState.docPages.length
        ? 'Page ' + (documentState.lastLookupPageIndex + 1) + ' / ' + documentState.docPages.length
        : '';
      requestAnimationFrame(function () {
        computeAndCacheRowBands();
      });
      requestAnimationFrame(function () {
        buildUdRectCache();
      });
      return;
    }

    // Check if in original view with PDF positioning data
    var pageData =
      documentState.isOriginalView &&
      documentState.renderedPageImages &&
      documentState.renderedPageImages.byIndex
        ? documentState.renderedPageImages.byIndex[documentState.lastLookupPageIndex]
        : null;
    if (documentState.isOriginalView && pageData && pageData.words && pageData.words.length > 0) {
      // Render structured flowing text layout - each word positioned by its actual X coordinate
      var structuredBlocks = pageData.structured_blocks || [];
      var words = pageData.words || [];

      // Create container
      var container = document.createElement('div');
      container.className = 'structured-text-container';
      container.style.cssText =
        'position:relative;background:#fff;border:1px solid #e5e7eb;border-radius:4px;box-sizing:border-box;overflow:hidden;';
      var containerWidth =
        hoverLayoutState.renderedText.clientWidth || hoverLayoutState.renderedText.offsetWidth || 0;
      var scaleFactor = containerWidth > 0 && pageData.width > 0 ? containerWidth / pageData.width : 1;
      if (containerWidth > 0 && pageData.width > 0) {
        var containerHeight = containerWidth * (pageData.height / pageData.width);
        container.style.height = containerHeight + 'px';
      }

      // Global word spans array for annotation mapping
      var allWordSpans = [];
      var pageFontSizes = [];
      var fontCounts = {};
      if (structuredBlocks.length > 0) {
        for (var bi = 0; bi < structuredBlocks.length; bi++) {
          var bl = structuredBlocks[bi].lines || [];
          for (var li = 0; li < bl.length; li++) {
            var bw = bl[li].words || [];
            for (var wi = 0; wi < bw.length; wi++) {
              var pfs = bw[wi] && Number(bw[wi].fontSize);
              if (pfs && isFinite(pfs) && pfs > 0) pageFontSizes.push(pfs);
              var fontName = bw[wi] && bw[wi].font;
              if (fontName) {
                fontCounts[fontName] = (fontCounts[fontName] || 0) + 1;
              }
            }
          }
        }
      } else {
        for (var wi = 0; wi < words.length; wi++) {
          var pfs2 = words[wi] && Number(words[wi].fontSize);
          if (pfs2 && isFinite(pfs2) && pfs2 > 0) pageFontSizes.push(pfs2);
          var fontName2 = words[wi] && words[wi].font;
          if (fontName2) {
            fontCounts[fontName2] = (fontCounts[fontName2] || 0) + 1;
          }
        }
      }
      var pageFontMedian = 0;
      if (pageFontSizes.length) {
        pageFontSizes.sort(function (a, b) {
          return a - b;
        });
        var midAll = Math.floor(pageFontSizes.length / 2);
        pageFontMedian =
          pageFontSizes.length % 2
            ? pageFontSizes[midAll]
            : (pageFontSizes[midAll - 1] + pageFontSizes[midAll]) / 2;
      }
      // Find most common font
      var mostCommonFont = null;
      var maxFontCount = 0;
      for (var fn in fontCounts) {
        if (fontCounts[fn] > maxFontCount) {
          maxFontCount = fontCounts[fn];
          mostCommonFont = fn;
        }
      }

      // Helper: emit a hidden separator span carrying the same character(s)
      // that buildLayoutTextFromWords inserts into the canonical text. The
      // .pdf-sep style hides them visually but TreeWalker / textContent
      // still see them, so renderedText.textContent === canonical text. Used
      // by both the structured-blocks and the flat-words render branches.
      var _emitPdfSep = function (sepStr) {
        if (!sepStr) return;
        var sep = document.createElement('span');
        sep.className = 'pdf-sep';
        sep.textContent = sepStr;
        container.appendChild(sep);
      };
      if (structuredBlocks.length > 0) {
        // Sort blocks by Y position (min_y) for proper vertical ordering
        var sortedBlocks = structuredBlocks.slice().sort(function (a, b) {
          return (a.min_y || 0) - (b.min_y || 0);
        });

        // Render using structured blocks - absolute-position each run by X/Y.
        // Iteration order MUST match buildLayoutTextFromWords: blocks sorted
        // by min_y (already done), words within each line sorted by X, with
        // \n\n between blocks, \n between lines, and a space (per
        // shouldInsertSpace) between same-line words.
        for (var bi = 0; bi < sortedBlocks.length; bi++) {
          if (bi > 0) _emitPdfSep('\n\n');
          var block = sortedBlocks[bi];
          var lines = block.lines || [];
          for (var li = 0; li < lines.length; li++) {
            if (li > 0) _emitPdfSep('\n');
            var lineWordsRaw = lines[li].words || [];
            var lineWords = lineWordsRaw.slice().sort(function (a, b) {
              return (a.x || 0) - (b.x || 0);
            });
            for (var wi = 0; wi < lineWords.length; wi++) {
              var w = lineWords[wi];
              if (!w || !w.text) continue;
              if (shouldInsertSpace(w, wi)) _emitPdfSep(' ');
              var wordSpan = document.createElement('span');
              wordSpan.className = 'pdf-raw-word';
              wordSpan.textContent = w.text;
              wordSpan.dataset.wordIdx = String(w.word_idx != null ? w.word_idx : allWordSpans.length);
              wordSpan.dataset.block = String(bi);
              wordSpan.dataset.line = String(li);
              wordSpan.dataset.bboxX = String(w.x || 0);
              wordSpan.dataset.bboxY = String(w.y || 0);
              wordSpan.dataset.bboxW = String(w.w || 0);
              wordSpan.dataset.bboxH = String(w.h || 0);
              var leftPct = ((w.x || 0) / pageData.width) * 100;
              var topPct = ((w.y || 0) / pageData.height) * 100;
              wordSpan.style.cssText =
                'position:absolute;left:' + leftPct + '%;top:' + topPct + '%;white-space:nowrap;';
              // Font family: toggle OFF uses the literal per-word `w.font`
              // (no fallback). Toggle ON falls back to the page's most-common
              // font when the word itself has no font name.
              var perWordFont = w.font ? String(w.font).replace(/"/g, '') : '';
              var fontFamilyToUse = perWordFont
                ? perWordFont
                : dependencyPopupState.displaySettings.pdfOcrCleanup && mostCommonFont
                  ? String(mostCommonFont).replace(/"/g, '')
                  : '';
              if (fontFamilyToUse) wordSpan.style.fontFamily = '"' + fontFamilyToUse + '", inherit';
              // Font size: toggle OFF uses the literal per-word `w.fontSize`
              // (even when 0, rare). Toggle ON falls back to the page-median
              // fontSize when the word's own size is missing.
              var rawFs = Number(w.fontSize) || 0;
              var useFontSize =
                rawFs > 0
                  ? rawFs
                  : dependencyPopupState.displaySettings.pdfOcrCleanup
                    ? pageFontMedian
                    : rawFs;
              if (useFontSize && scaleFactor > 0) {
                wordSpan.style.fontSize = Number(useFontSize) * scaleFactor + 'px';
              }
              container.appendChild(wordSpan);
              allWordSpans.push(wordSpan);
            }
          }
        }
      } else {
        // Fallback: render flat word list grouped by Y, each word positioned individually
        // First, group words by Y coordinate (lines)
        var lineGroups = [];
        var currentLineY = -999;
        var currentLineWords = [];
        var medianH = 12;

        // Compute median height
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
        for (var wi = 0; wi < words.length; wi++) {
          var w = words[wi];
          if (!w || !w.text) continue;
          var y = typeof w.y === 'number' ? w.y : 0;
          var h = typeof w.h === 'number' && w.h > 0 ? w.h : medianH;

          // Check for new line
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

        // Render each line with individually positioned words. Iteration
        // order MUST match buildLayoutTextFromWords' fallback branch: lines
        // sorted by Y (above), words within each line sorted by X, with \n
        // between lines and a space (per shouldInsertSpace) between same-line
        // words. Mirror those separators into the DOM via .pdf-sep so
        // textContent matches the canonical text sent to /lookup.
        var fallbackFontMedian = pageFontMedian;
        for (var li = 0; li < lineGroups.length; li++) {
          if (li > 0) _emitPdfSep('\n');
          var lineWords = lineGroups[li].words.slice().sort(function (a, b) {
            return (a.x || 0) - (b.x || 0);
          });
          for (var wi = 0; wi < lineWords.length; wi++) {
            var w = lineWords[wi];
            if (!w || !w.text) continue;
            if (shouldInsertSpace(w, wi)) _emitPdfSep(' ');
            var wordSpan = document.createElement('span');
            wordSpan.className = 'pdf-raw-word';
            wordSpan.textContent = w.text;
            wordSpan.dataset.wordIdx = String(w.word_idx != null ? w.word_idx : allWordSpans.length);
            wordSpan.dataset.block = '0';
            wordSpan.dataset.line = String(li);
            wordSpan.dataset.bboxX = String(w.x || 0);
            wordSpan.dataset.bboxY = String(w.y || 0);
            wordSpan.dataset.bboxW = String(w.w || 0);
            wordSpan.dataset.bboxH = String(w.h || 0);

            // Position each word by its actual X coordinate
            var leftPct = ((w.x || 0) / pageData.width) * 100;
            var topPct = ((w.y || 0) / pageData.height) * 100;
            wordSpan.style.cssText =
              'position:absolute;left:' + leftPct + '%;top:' + topPct + '%;white-space:nowrap;';
            // Font family: toggle OFF uses the literal per-word `w.font`.
            // Toggle ON falls back to the page's most-common font when the
            // word itself has no font name.
            var perWordFont2 = w.font ? String(w.font).replace(/"/g, '') : '';
            var fontFamilyToUse2 = perWordFont2
              ? perWordFont2
              : dependencyPopupState.displaySettings.pdfOcrCleanup && mostCommonFont
                ? String(mostCommonFont).replace(/"/g, '')
                : '';
            if (fontFamilyToUse2) wordSpan.style.fontFamily = '"' + fontFamilyToUse2 + '", inherit';
            // Font size: toggle OFF uses the literal per-word `w.fontSize`.
            // Toggle ON falls back to the page-median fontSize when the
            // word's own size is missing.
            var rawFs2 = Number(w.fontSize) || 0;
            var useFontSize2 =
              rawFs2 > 0
                ? rawFs2
                : dependencyPopupState.displaySettings.pdfOcrCleanup
                  ? fallbackFontMedian
                  : rawFs2;
            if (useFontSize2 && scaleFactor > 0) {
              wordSpan.style.fontSize = Number(useFontSize2) * scaleFactor + 'px';
            }
            container.appendChild(wordSpan);
            allWordSpans.push(wordSpan);
          }
        }
      }

      // Store reference to raw word spans for later annotation
      lookupProgressState.latestRawWordSpans = allWordSpans;
      lookupProgressState.latestRawPageData = pageData; // Store page data for annotation
      window.latestRawPageData = pageData;
      frag.appendChild(container);
      hoverLayoutState.renderedText.classList.add('orig-view-structured');

      // Now render the raw layout and annotate it from the existing lookup payload.
      hoverLayoutState.renderedText.innerHTML = '';
      hoverLayoutState.renderedText.appendChild(frag);
      hideNerHover();
      if (dependencyPopupState.displaySettings.pdfOcrCleanup) {
        (function () {
          var basePx = pageFontMedian && scaleFactor > 0 ? pageFontMedian * scaleFactor : 0;
          var runNormalize = function () {
            normalizeBlockFontSizes(container, basePx);
            normalizeLinePositions(container);
          };
          if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(function () {
              requestAnimationFrame(runNormalize);
            });
          } else {
            requestAnimationFrame(runNormalize);
          }
        })();
      }

      // Reuse the single lookup payload for this page; do not trigger a second /lookup.
      if (segments.length && segmentOffsets.length) {
        clearUdTokenIndex();
        invalidateUdRectCache();
        invalidateUiRectCache();

        // Annotate positioned word spans using the already-fetched segment payload.
        annotateRawWordSpans(
          lookupProgressState.latestRawWordSpans,
          pageData.words,
          segments,
          segmentOffsets,
          resultsBySeg,
          gramOverlay,
          udTokenMap,
          pageData
        );
        attachHoverHandlers(hoverLayoutState.renderedText, resultsBySeg, gramOverlay);
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            computeAndCacheRowBands();
            buildUdRectCache();
          });
        });
        hoverLayoutState.statusText.textContent = 'Segmented ' + segments.length + ' tokens.';
        hoverLayoutState.statusCounts.textContent = documentState.docPages.length
          ? 'Page ' + (documentState.lastLookupPageIndex + 1) + ' / ' + documentState.docPages.length
          : '';
      } else {
        hoverLayoutState.statusText.textContent = 'Segmented ' + n + ' tokens.';
        hoverLayoutState.statusCounts.textContent = '';
      }
      return;
    } else {
      // Standard text rendering (not original view)
      var cursor = 0;
      for (var oi = 0; oi < n; oi++) {
        var start = Number(segmentOffsets[oi][0]);
        var end = Number(segmentOffsets[oi][1]);
        if (start > cursor) {
          frag.appendChild(document.createTextNode(text.slice(cursor, start)));
        }
        // Render each token individually for dictionary inspection
        var built = buildTokenSpan(oi, text.slice(start, end), gramOverlay, resultsBySeg, udTokenMap);
        applyPlainTextNoWrap(built.span);
        frag.appendChild(built.span);
        if (built.hasGrammar) grammarCount++;
        if (built.isUnknown) unknownCount++;
        cursor = end;
        // Map each segment to its own element (NER spans are expanded later for highlighting).
        registerTokenSpan(oi, built.span);
      }
      if (cursor < text.length) {
        frag.appendChild(document.createTextNode(text.slice(cursor)));
      }
    }
    hoverLayoutState.renderedText.innerHTML = '';
    hoverLayoutState.renderedText.appendChild(frag);
    hideNerHover();
    hoverLayoutState.statusText.textContent = 'Segmented ' + n + ' tokens.';
    attachHoverHandlers(hoverLayoutState.renderedText, resultsBySeg, gramOverlay);
    // Defer row band caching to avoid blocking render
    requestAnimationFrame(function () {
      computeAndCacheRowBands();
    });
    requestAnimationFrame(function () {
      buildUdRectCache();
    });
    return;
  }
  var buffer = '';
  function flushBuffer() {
    if (buffer) {
      frag.appendChild(document.createTextNode(buffer));
      buffer = '';
    }
  }
  var segIndex = 0,
    len = text.length;
  for (var i = 0; i < len; i++) {
    var ch = text[i];
    if (isMyanmarChar(ch) && segIndex < n) {
      var token = segments[segIndex];
      if (token) {
        var match = matchTokenWithInvisibleChars(text, i, token);
        if (match) {
          flushBuffer();
          // Render each token individually for dictionary inspection
          var built = buildTokenSpan(segIndex, token, gramOverlay, resultsBySeg, udTokenMap);
          applyPlainTextNoWrap(built.span);
          frag.appendChild(built.span);
          if (built.hasGrammar) grammarCount++;
          if (built.isUnknown) unknownCount++;
          // Map each segment to its own element (NER spans are expanded later for highlighting).
          registerTokenSpan(segIndex, built.span);
          i = match.end;
          segIndex++;
          continue;
        }
      }
    }
    buffer += ch;
  }
  flushBuffer();
  hoverLayoutState.renderedText.innerHTML = '';
  hoverLayoutState.renderedText.appendChild(frag);
  hideNerHover();
  hoverLayoutState.statusText.textContent = 'Segmented ' + n + ' tokens.';
  attachHoverHandlers(hoverLayoutState.renderedText, resultsBySeg, gramOverlay);
  // Defer row band caching to avoid blocking render
  requestAnimationFrame(function () {
    computeAndCacheRowBands();
  });
  requestAnimationFrame(function () {
    buildUdRectCache();
  });
}
export function normalizeLookupKey(raw, langOverride) {
  // Language-specific normalization now handled server-side in Python.
  // Cache key just needs basic NFKC + lowercase for consistency.
  var lang = String(langOverride || documentShellState.currentLanguage || '').toLowerCase();
  var token = String(raw || '').trim();
  if (!token) return '';
  if (token.normalize) token = token.normalize('NFKC');
  token = token.trim();
  if (!token) return '';
  return lang + '::' + token.toLowerCase();
}
export function buildSidePanelLookupCacheKey(raw, langOverride, options) {
  var base = normalizeLookupKey(raw, langOverride);
  if (!base) return '';
  var opts = options || {};
  var lemma = String(opts.lemma || '')
    .trim()
    .toLowerCase();
  var upos = String(opts.upos || '')
    .trim()
    .toLowerCase();
  var xpos = String(opts.xpos || '')
    .trim()
    .toLowerCase();
  return [base, lemma, upos, xpos].join('||');
}
export function getExactSidePanelLookupEntry(raw, langOverride, options) {
  var key = buildSidePanelLookupCacheKey(raw, langOverride, options);
  if (!key) return null;
  return segmentRenderingState.sidePanelLookupCache.get(key) || null;
}
export function setExactSidePanelLookupEntry(raw, entry, langOverride, options) {
  var key = buildSidePanelLookupCacheKey(raw, langOverride, options);
  if (!key || !entry) return;
  segmentRenderingState.sidePanelLookupCache.set(key, entry);
}
export function getTokenLookupStateRecord(raw, langOverride, createIfMissing) {
  var k = normalizeLookupKey(raw, langOverride);
  if (!k) return null;
  var record = segmentRenderingState.tokenLookupStateCache.get(k) || null;
  if (!record && createIfMissing) {
    record = {
      directEntry: null,
      tokenEntry: null,
      fragmentEntry: null,
      subsegSurface: null,
      subsegDecompose: null,
      fuzzy: null
    };
    segmentRenderingState.tokenLookupStateCache.set(k, record);
  }
  return record;
}
export function setTokenLookupStateField(raw, fieldName, value, langOverride) {
  var record = getTokenLookupStateRecord(raw, langOverride, true);
  if (!record) return;
  record[fieldName] = value;
}
export function getTokenLookupStateField(raw, fieldName, langOverride) {
  var record = getTokenLookupStateRecord(raw, langOverride, false);
  if (!record) return null;
  return record[fieldName] || null;
}
export function hasTokenLookupStateField(raw, fieldName, langOverride) {
  var record = getTokenLookupStateRecord(raw, langOverride, false);
  return !!(record && record[fieldName]);
}
export function clearTokenLookupStateField(fieldName) {
  segmentRenderingState.tokenLookupStateCache.forEach(function (record) {
    if (!record || typeof record !== 'object') return;
    record[fieldName] = null;
  });
}
export function clearAllTokenLookupState() {
  segmentRenderingState.tokenLookupStateCache.clear();
}
export function setLookupDpEntry(entry, aliasKey, langOverride) {
  if (!entry) return;
  var headText = getEntryDisplayHead(entry, '');
  if (headText) setTokenLookupStateField(headText, 'directEntry', entry, langOverride);
  if (aliasKey) setTokenLookupStateField(aliasKey, 'directEntry', entry, langOverride);
}
export function getLookupDpEntry(key, langOverride) {
  return getTokenLookupStateField(key, 'directEntry', langOverride);
}
export function hasLookupDpEntry(key, langOverride) {
  return hasTokenLookupStateField(key, 'directEntry', langOverride);
}
export function setLookupTokenEntry(entry, aliasKey, langOverride) {
  if (!entry) return;
  var headText = getEntryDisplayHead(entry, '');
  if (headText) setTokenLookupStateField(headText, 'tokenEntry', entry, langOverride);
  if (aliasKey) setTokenLookupStateField(aliasKey, 'tokenEntry', entry, langOverride);
}
export function getLookupTokenEntry(key, langOverride) {
  return getTokenLookupStateField(key, 'tokenEntry', langOverride);
}
export function setLookupFragmentEntry(entry, aliasKey, langOverride) {
  if (!entry) return;
  var headText = getEntryDisplayHead(entry, '');
  if (headText) setTokenLookupStateField(headText, 'fragmentEntry', entry, langOverride);
  if (aliasKey) setTokenLookupStateField(aliasKey, 'fragmentEntry', entry, langOverride);
}
export function getLookupFragmentEntry(key, langOverride) {
  return getTokenLookupStateField(key, 'fragmentEntry', langOverride);
}
export function flushLookupCachesForToken(surface, langOverride) {
  var k = normalizeLookupKey(surface, langOverride);
  if (!k) return;
  segmentRenderingState.tokenLookupStateCache.delete(k);
  var prefix = k + '||';
  var sidePanelKeysToDelete = [];
  segmentRenderingState.sidePanelLookupCache.forEach(function (_entry, key) {
    var skey = String(key || '');
    if (skey === k || skey.indexOf(prefix) === 0) sidePanelKeysToDelete.push(skey);
  });
  for (var si = 0; si < sidePanelKeysToDelete.length; si++) {
    segmentRenderingState.sidePanelLookupCache.delete(sidePanelKeysToDelete[si]);
  }
  var sidePanelPromiseKeysToDelete = [];
  segmentRenderingState.sidePanelLookupPromiseCache.forEach(function (_promise, key) {
    var pkey = String(key || '');
    if (pkey === k || pkey.indexOf(prefix) === 0) sidePanelPromiseKeysToDelete.push(pkey);
  });
  for (var pi = 0; pi < sidePanelPromiseKeysToDelete.length; pi++) {
    segmentRenderingState.sidePanelLookupPromiseCache.delete(sidePanelPromiseKeysToDelete[pi]);
  }
  var psrApi = window.PanelSegmentRenderer || null;
  if (psrApi && typeof psrApi.invalidateLookup === 'function') {
    psrApi.invalidateLookup(surface, langOverride || documentShellState.currentLanguage || '');
  }
}
export function _entryReferencesStorageId(entry, dbAlias, rowId) {
  // Check a single entry object (and its fill pieces) for a matching storage ID.
  if (!entry || typeof entry !== 'object') return false;
  var checkOne = function (e) {
    if (!e || typeof e !== 'object') return false;
    var a = String(e._storage_db_alias || '').trim();
    var r = parseInt(e._storage_row_id || 0, 10) || 0;
    return a === dbAlias && r === rowId;
  };
  if (checkOne(entry)) return true;
  var fills = Array.isArray(entry.dict_fill) ? entry.dict_fill : [];
  for (var i = 0; i < fills.length; i++) {
    if (checkOne(fills[i])) return true;
    // fills may themselves contain entries arrays
    var inner = Array.isArray(fills[i] && fills[i].entries) ? fills[i].entries : [];
    for (var j = 0; j < inner.length; j++) {
      if (checkOne(inner[j])) return true;
    }
    // Also check entry_refs (ref key strings) by parsing the key format: "storage_kind|db_alias|row_id"
    var refKeys = Array.isArray(fills[i] && fills[i].entry_refs) ? fills[i].entry_refs : [];
    for (var rk = 0; rk < refKeys.length; rk++) {
      var parts = String(refKeys[rk] || '').split('|');
      if (parts.length >= 3 && parts[1] === dbAlias && (parseInt(parts[2], 10) || 0) === rowId) return true;
    }
  }
  var koChildren = Array.isArray(entry.ko_compound_lemma_children) ? entry.ko_compound_lemma_children : [];
  for (var ki = 0; ki < koChildren.length; ki++) {
    var child = koChildren[ki] || {};
    if (child.lookup && _entryReferencesStorageId(child.lookup, dbAlias, rowId)) return true;
  }
  return false;
}
export function initializeSegmentRendering() {
  segmentRenderingState.currentSpan = null;
  segmentRenderingState.currentFillHit = null; // Currently hovered .reader-token-fill-hit within a multi-fill token
  segmentRenderingState.currentPopupAnchorEl = null; // Concrete hover target used for popup anchoring/obstacle avoidance
  segmentRenderingState.panelHoverToken = null;
  segmentRenderingState.panelHoverType = null;
  // Unified per-language token cache for all token-related lookup state.
  segmentRenderingState.tokenLookupStateCache = new Map();
  // Dedicated exact-lookup cache for side-panel/banner targets.
  segmentRenderingState.sidePanelLookupCache = new Map();
  segmentRenderingState.sidePanelLookupPromiseCache = new Map();
  ((segmentRenderingState.lastMouseX = 0), (segmentRenderingState.lastMouseY = 0));
  /* NEW: annotation state */
  segmentRenderingState.noteCache = new Map();
  segmentRenderingState.currentPopupHead = null;
  return true;
}
