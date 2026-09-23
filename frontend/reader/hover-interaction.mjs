import { drawUdLinesForToken, getUdInfoForSegment, normalizeUdPartIndex } from './dependency-hover.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { noteDepTreeExperimentHover } from './dependency-state.mjs';
import { buildPopupForSpan, positionPopup } from './dictionary-popup.mjs';
import { documentShellState } from './document-shell.state.mjs';
import {
  getLookupEntryFillMode,
  getLookupEntryResolvedVia,
  getMwtPartSurfaceSliceText,
  getTokenMapAnchorText,
  getTokenMapLookupText,
  getUdTokenSurfaceAnchor
} from './entry-editing.mjs';
import { parseFillHitIndexes, resolveSegmentPosData } from './fill-slices.mjs';
import { applyChunkHighlight, clearChunkHighlight } from './gloss-requests.mjs';
import { glossRequestsState } from './gloss-requests.state.mjs';
import { hoverInteractionState } from './hover-interaction.state.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import {
  _buildAssistantReaderCtx,
  _buildAssistantSentenceCtx,
  _buildAssistantTokenCtx,
  _buildExpandedCtxForSeg,
  _serializeAssistantReader,
  _serializeAssistantSentence,
  _serializeAssistantToken
} from './lookup-progress.mjs';
import {
  getKoreanCompoundLemmaSpawnPartsFromEl,
  showKoreanCompoundLemmaSpawnBox,
  showMwtSpawnBox
} from './mwt-anchors.mjs';
import { _isPointInsideMwtSpawnBox, _isPointInsideMwtSpawnShield, hideMwtSpawnBox } from './mwt-context.mjs';
import { mwtContextState } from './mwt-context.state.mjs';
import { getEntryDisplayHead, hasSameVisibleComparisonText } from './presentation.mjs';
import {
  _entryReferencesStorageId,
  clearTokenLookupStateField,
  getTokenLookupStateField,
  getTokenLookupStateRecord,
  hasTokenLookupStateField,
  normalizeLookupKey,
  setTokenLookupStateField
} from './segment-rendering.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
import { togglePanel } from './settings-panels.mjs';
import { displayDictEntry, hidePopup, isUnknownDictEntry, lookupAndDisplay } from './side-panel.mjs';
import { tokenBannerMenuState } from './token-banner-menu.state.mjs';
import {
  hideHoverReticle,
  hideNerHover,
  hideUdLines,
  renderNerHoverForToken,
  showHoverReticle
} from './token-fragments.mjs';
import { buildTokenMapGroupedFillEntry } from './token-map.mjs';
export function flushCachedEntriesByStorageId(dbAlias, rowId) {
  // Evict from tokenLookupStateCache any record whose stored entries reference
  // this specific (dbAlias, rowId) pair � handles greedy-segmented tokens
  // where the cache key is the surface, not the headword.
  var alias = String(dbAlias || '').trim();
  var id = parseInt(rowId || 0, 10) || 0;
  if (!alias || !id) return;
  var stateKeysToDelete = [];
  segmentRenderingState.tokenLookupStateCache.forEach(function (record, key) {
    if (!record || typeof record !== 'object') return;
    var fields = ['directEntry', 'tokenEntry', 'fragmentEntry'];
    for (var fi = 0; fi < fields.length; fi++) {
      if (_entryReferencesStorageId(record[fields[fi]], alias, id)) {
        stateKeysToDelete.push(key);
        return;
      }
    }
  });
  for (var i = 0; i < stateKeysToDelete.length; i++) {
    segmentRenderingState.tokenLookupStateCache.delete(stateKeysToDelete[i]);
  }
  // Evict from sidePanelLookupCache any entry referencing this storage ID
  var sidePanelKeysToDelete = [];
  segmentRenderingState.sidePanelLookupCache.forEach(function (entry, key) {
    if (_entryReferencesStorageId(entry, alias, id)) {
      sidePanelKeysToDelete.push(key);
    }
  });
  for (var j = 0; j < sidePanelKeysToDelete.length; j++) {
    segmentRenderingState.sidePanelLookupCache.delete(sidePanelKeysToDelete[j]);
  }
  var psrApi = window.PanelSegmentRenderer || null;
  if (psrApi && typeof psrApi.invalidateByStorageId === 'function') {
    psrApi.invalidateByStorageId(alias, id);
  }
}
export function normalizeSubsegKey(raw, langOverride) {
  return normalizeLookupKey(raw, langOverride);
}
export function getSubsegEntry(key, decomposeMode, langOverride) {
  return getTokenLookupStateField(key, decomposeMode ? 'subsegDecompose' : 'subsegSurface', langOverride);
}
export function setSubsegEntry(key, value, decomposeMode, langOverride) {
  setTokenLookupStateField(key, decomposeMode ? 'subsegDecompose' : 'subsegSurface', value, langOverride);
}
export // Minimum ms between hover updates (~120fps max)

// Fix zero-width reader tokens by applying min-width styling
function fixZeroWidthReaderTokens() {
  if (!hoverLayoutState.renderedText) return;
  // Defer until browser finishes layout
  requestAnimationFrame(function () {
    var tokens = hoverLayoutState.renderedText.querySelectorAll('.reader-token');
    tokens.forEach(function (tok) {
      var r = tok.getBoundingClientRect();
      if (r.width === 0) {
        tok.style.display = 'inline-block';
        tok.style.minWidth = '0.6em';
      }
    });
  });
}

// Compute and cache row bands from rendered text (call once after rendering)
export function computeAndCacheRowBands() {
  hoverInteractionState.cachedRowBands = null;
  hoverInteractionState.cachedRowSnapPoints = null;
  hoverInteractionState.cachedRowGapRanges = null;
  if (!hoverLayoutState.renderedText) return;
  try {
    var rowEls = hoverLayoutState.renderedText.querySelectorAll('.reader-token');
    if (!rowEls.length) return;
    var bands = [];
    var tol = 6;
    for (var i = 0; i < rowEls.length; i++) {
      var r = rowEls[i].getBoundingClientRect();
      if (!r || r.width <= 0 || r.height <= 0) continue;
      var match = null;
      for (var j = 0; j < bands.length; j++) {
        if (Math.abs(bands[j].top - r.top) <= tol) {
          match = bands[j];
          break;
        }
      }
      if (!match) {
        bands.push({
          top: r.top,
          bottom: r.bottom
        });
      } else {
        match.top = Math.min(match.top, r.top);
        match.bottom = Math.max(match.bottom, r.bottom);
      }
    }
    bands.sort(function (a, b) {
      return a.top - b.top;
    });
    hoverInteractionState.cachedRowBands = bands;
  } catch (e) {}
}

// Invalidate row band cache (call on resize/scroll)
export function invalidateRowBandCache() {
  hoverInteractionState.cachedRowBands = null;
  hoverInteractionState.cachedRowSnapPoints = null;
  hoverInteractionState.cachedRowGapRanges = null;
}
export function attachHoverHandlers(container, resultsBySeg, gramOverlay) {
  var lastHighlightedSegIdx = -2; // Track which clause is currently highlighted for static display
  var lastHighlightedHoverKey = '';
  mwtContextState._mwtSpawnHoverVisualResetHook = function () {
    if (hoverInteractionState.hoverRafId) {
      cancelAnimationFrame(hoverInteractionState.hoverRafId);
      hoverInteractionState.hoverRafId = null;
    }
    hoverInteractionState.pendingHoverEvent = null;
    hidePopup();
    hideUdLines();
    hideNerHover();
    hideHoverReticle();
    clearChunkHighlight();
    lastHighlightedSegIdx = -2;
    lastHighlightedHoverKey = '';
    glossRequestsState.lastUdHoverKey = '';
  };

  // In original PDF view, a single rendered span (one PDF "word" / island fragment) may correspond to
  // multiple Burmese segments. This resolver chooses the most plausible segIdx under the pointer.
  function resolveSegIdxForSpan(span, clientX) {
    if (!span) return -1;
    var idx = parseInt(span.dataset.index || '-1', 10);
    var segList = (span.dataset.segments || '')
      .split(',')
      .map(function (x) {
        return parseInt(x, 10);
      })
      .filter(function (n) {
        return isFinite(n) && n >= 0;
      });
    if (segList.length <= 1) return idx;

    // If we don't have offsets, fall back to the canonical earliest index.
    if (!latestSegmentOffsets || !Array.isArray(latestSegmentOffsets) || !latestSegmentOffsets.length) {
      return idx;
    }

    // Estimate a character position within the synthetic layout text based on pointer x within the span.
    var wStart = parseInt(span.dataset.wordStart || 'NaN', 10);
    var wEnd = parseInt(span.dataset.wordEnd || 'NaN', 10);
    if (!isFinite(wStart) || !isFinite(wEnd) || wEnd <= wStart) {
      // No word-span offsets - choose the smallest seg whose offsets overlap anything.
      segList.sort(function (a, b) {
        return a - b;
      });
      return segList[0];
    }
    var rect = span.getBoundingClientRect ? span.getBoundingClientRect() : null;
    var spanW = rect ? rect.width : 0;
    var t = 0.0;
    if (rect && spanW > 1) {
      t = (clientX - rect.left) / spanW;
    }
    if (t < 0) t = 0;
    if (t > 0.999) t = 0.999;
    var estChar = wStart + Math.floor(t * (wEnd - wStart));
    if (estChar < wStart) estChar = wStart;
    if (estChar >= wEnd) estChar = wEnd - 1;

    // Pick the segment whose offset range contains estChar; otherwise choose nearest.
    var best = idx;
    var bestDist = 1e18;
    for (var i = 0; i < segList.length; i++) {
      var si = segList[i];
      var off = latestSegmentOffsets[si];
      if (!off || off.length < 2) continue;
      var s0 = Number(off[0]),
        s1 = Number(off[1]);
      if (!isFinite(s0) || !isFinite(s1)) continue;
      if (estChar >= s0 && estChar < s1) {
        return si;
      }
      var dist = 0;
      if (estChar < s0) dist = s0 - estChar;
      else if (estChar >= s1) dist = estChar - (s1 - 1);
      if (dist < bestDist) {
        bestDist = dist;
        best = si;
      }
    }
    return best;
  }

  // Process deferred hover updates (called via RAF)
  function processHoverUpdate(data) {
    var segIdx = data.segIdx;
    var mwtPartIdx = normalizeUdPartIndex(data.mwtPartIdx);
    var clientX = data.clientX;
    var clientY = data.clientY;
    var highlightHoverKey = String(segIdx) + ':' + (mwtPartIdx !== null ? String(mwtPartIdx) : '');

    // Apply clause highlighting only when entering a different clause span
    // For context window mode, always recompute since the window is centered on each token
    if (segIdx >= 0) {
      var needsRecompute =
        !glossRequestsState.currentChunkHighlightTokens ||
        !glossRequestsState.currentChunkHighlightTokens.has(segIdx);
      // Context window mode: always recompute when moving to a different token
      if (
        dependencyPopupState.displaySettings.contextWindow &&
        highlightHoverKey !== lastHighlightedHoverKey
      ) {
        needsRecompute = true;
      }
      if (
        dependencyPopupState.displaySettings.bottomUpChunk &&
        highlightHoverKey !== lastHighlightedHoverKey
      ) {
        needsRecompute = true;
      }
      if (needsRecompute) {
        applyChunkHighlight(segIdx, mwtPartIdx);
        lastHighlightedSegIdx = segIdx;
        lastHighlightedHoverKey = highlightHoverKey;
      }
    } else if (segIdx < 0) {
      hideNerHover();
      clearChunkHighlight();
      lastHighlightedSegIdx = -2;
      lastHighlightedHoverKey = '';
      if (!segmentRenderingState.currentSpan) hideHoverReticle();
    }

    // Update UD lines and NER tags for the current token
    if (segIdx >= 0) {
      var udHoverKey = String(segIdx) + ':' + (mwtPartIdx !== null ? String(mwtPartIdx) : '');
      if (
        dependencyPopupState.displaySettings.udOverlay &&
        udHoverKey !== glossRequestsState.lastUdHoverKey
      ) {
        drawUdLinesForToken(segIdx, mwtPartIdx);
        glossRequestsState.lastUdHoverKey = udHoverKey;
      }
      renderNerHoverForToken(segIdx);
      noteDepTreeExperimentHover(segIdx, 'hover');
    } else {
      glossRequestsState.lastUdHoverKey = '';
      if (!segmentRenderingState.currentSpan) hideHoverReticle();
    }
    positionPopup(clientX, clientY);
  }
  container.onmousemove = function (ev) {
    if (_isPointInsideMwtSpawnShield(ev)) return;
    if (_isPointInsideMwtSpawnBox(ev)) return;
    var span = ev.target && ev.target.closest('.reader-token');
    if (!span) {
      if (mwtContextState._mwtSpawnActive) return;
      segmentRenderingState.currentSpan = null;
      segmentRenderingState.currentFillHit = null;
      segmentRenderingState.currentPopupAnchorEl = null;
      hidePopup();
      hideUdLines();
      hideNerHover();
      clearChunkHighlight();
      lastHighlightedSegIdx = -2;
      lastHighlightedHoverKey = '';
      hideHoverReticle();
      glossRequestsState.lastUdHoverKey = '';
      // Cancel any pending RAF
      if (hoverInteractionState.hoverRafId) {
        cancelAnimationFrame(hoverInteractionState.hoverRafId);
        hoverInteractionState.hoverRafId = null;
      }
      return;
    }
    if (mwtContextState._mwtSpawnActive && mwtContextState._mwtSpawnActive.anchorEl) {
      var activeSpawnToken =
        mwtContextState._mwtSpawnActive.anchorEl.closest &&
        mwtContextState._mwtSpawnActive.anchorEl.closest('.reader-token')
          ? mwtContextState._mwtSpawnActive.anchorEl.closest('.reader-token')
          : mwtContextState._mwtSpawnActive.anchorEl;
      if (activeSpawnToken && span !== activeSpawnToken) {
        hideMwtSpawnBox();
      }
    }
    if (span.classList.contains('reader-punct')) {
      segmentRenderingState.currentSpan = null;
      segmentRenderingState.currentFillHit = null;
      segmentRenderingState.currentPopupAnchorEl = null;
      hidePopup();
      hideUdLines();
      hideNerHover();
      clearChunkHighlight();
      lastHighlightedSegIdx = -2;
      lastHighlightedHoverKey = '';
      hideHoverReticle();
      glossRequestsState.lastUdHoverKey = '';
      // Cancel any pending RAF
      if (hoverInteractionState.hoverRafId) {
        cancelAnimationFrame(hoverInteractionState.hoverRafId);
        hoverInteractionState.hoverRafId = null;
      }
      return;
    }
    var hoverTarget = span;

    // Resolve the most plausible segment index under the pointer.
    var segIdx = resolveSegIdxForSpan(span, ev.clientX);

    // Keep the span's canonical index in sync with the current pointer-resolved seg,
    // so downstream UI code that reads span.dataset.index stays consistent during hover.
    if (segIdx >= 0 && span.dataset && String(span.dataset.index) !== String(segIdx)) {
      span.dataset.index = String(segIdx);
      if (hoverLayoutState.latestSegments && hoverLayoutState.latestSegments[segIdx])
        span.dataset.seg = String(hoverLayoutState.latestSegments[segIdx]);
    }

    // Detect which dict-fill hit zone the cursor is over (if any).
    var fillHit = ev.target && ev.target.closest ? ev.target.closest('.reader-token-fill-hit') : null;
    if (fillHit && !(span && span.contains(fillHit))) fillHit = null;
    var resForHover = resultsBySeg && segIdx >= 0 ? resultsBySeg[segIdx] : null;
    var dictFillForHover = resForHover && Array.isArray(resForHover.dict_fill) ? resForHover.dict_fill : [];
    var activeFillIndexes = fillHit ? parseFillHitIndexes(fillHit, dictFillForHover.length) : [];
    if (!activeFillIndexes.length) fillHit = null;
    var mwtPartEl = ev.target && ev.target.closest ? ev.target.closest('[data-mwt-part-index]') : null;
    if (mwtPartEl && !(span && span.contains(mwtPartEl))) mwtPartEl = null;
    if (
      mwtContextState._mwtSpawnActive &&
      mwtContextState._mwtSpawnActive.anchorEl &&
      mwtPartEl &&
      mwtContextState._mwtSpawnActive.anchorEl !== mwtPartEl
    ) {
      hideMwtSpawnBox();
    }
    var mwtPartIdx = mwtPartEl ? normalizeUdPartIndex(mwtPartEl.dataset.mwtPartIndex) : null;
    var popupAnchorTarget = fillHit || mwtPartEl || hoverTarget;

    // MWT sandhi redirect: if the mwt child text doesn't match the surface
    // slice it was remapped to (e.g. Sanskrit), spawn a persistent white box
    // above the anchor with the unsandhied child text. The surface anchor
    // itself is only a launcher: dict/grammar inspection happens only from
    // the spawned child text, not from the sandhied surface slice.
    var mwtRedirect = false;
    if (mwtPartEl && mwtPartEl.dataset && mwtPartEl.dataset.mwtMismatch === '1') {
      var _mwtChildText = String(mwtPartEl.dataset.mwtChildText || '');
      if (_mwtChildText) {
        var _segRes = resultsBySeg && segIdx >= 0 ? resultsBySeg[segIdx] : null;
        showMwtSpawnBox(mwtPartEl, segIdx, mwtPartIdx, _mwtChildText, _segRes);
        mwtRedirect = true;
      }
    }
    var koCompoundRedirect = false;
    if (!mwtRedirect && !mwtPartEl && span.dataset && span.dataset.koCompoundLemmaSpawn === '1') {
      var _koParts = getKoreanCompoundLemmaSpawnPartsFromEl(span);
      if (_koParts.length) {
        var _koSegRes = resultsBySeg && segIdx >= 0 ? resultsBySeg[segIdx] : null;
        showKoreanCompoundLemmaSpawnBox(span, segIdx, _koParts, _koSegRes);
        koCompoundRedirect = true;
      }
    }

    // Immediate updates: popup behavior is anchored to neural token.
    var spanChanged = hoverTarget !== segmentRenderingState.currentSpan;
    var fillChanged = fillHit !== segmentRenderingState.currentFillHit;
    var popupAnchorChanged = popupAnchorTarget !== segmentRenderingState.currentPopupAnchorEl;
    if (spanChanged) {
      segmentRenderingState.currentSpan = hoverTarget;
    }
    segmentRenderingState.currentPopupAnchorEl = popupAnchorTarget;
    if (mwtRedirect || koCompoundRedirect) {
      segmentRenderingState.currentFillHit = null;
      hidePopup();
    } else if (spanChanged || fillChanged) {
      segmentRenderingState.currentFillHit = fillHit;
      buildPopupForSpan(span, resultsBySeg, gramOverlay, activeFillIndexes, {
        hoverMwtPartIdx: isFinite(Number(mwtPartIdx)) ? Number(mwtPartIdx) : null,
        hoverMwtChildText: mwtPartEl && mwtPartEl.dataset ? String(mwtPartEl.dataset.mwtChildText || '') : '',
        hoverMwtSurfaceSlice:
          mwtPartEl && mwtPartEl.dataset ? String(mwtPartEl.dataset.mwtSurfaceSlice || '') : ''
      });
    }

    // Hover reticle targets the specific fill-hit span when available, else the whole token.
    var reticleTarget = popupAnchorTarget;
    showHoverReticle(reticleTarget);

    // Throttle expensive visual updates via RAF
    var now = performance.now();
    var timeSinceLastProcess = now - hoverInteractionState.lastHoverProcessTime;

    // Store pending data
    hoverInteractionState.pendingHoverEvent = {
      segIdx: segIdx,
      mwtPartIdx: mwtPartIdx,
      clientX: ev.clientX,
      clientY: ev.clientY
    };

    // If enough time has passed, process immediately; otherwise schedule RAF
    if (timeSinceLastProcess >= hoverInteractionState.hoverThrottleMs) {
      hoverInteractionState.lastHoverProcessTime = now;
      if (hoverInteractionState.hoverRafId) {
        cancelAnimationFrame(hoverInteractionState.hoverRafId);
        hoverInteractionState.hoverRafId = null;
      }
      processHoverUpdate(hoverInteractionState.pendingHoverEvent);
    } else if (!hoverInteractionState.hoverRafId) {
      hoverInteractionState.hoverRafId = requestAnimationFrame(function () {
        hoverInteractionState.hoverRafId = null;
        hoverInteractionState.lastHoverProcessTime = performance.now();
        if (hoverInteractionState.pendingHoverEvent) {
          processHoverUpdate(hoverInteractionState.pendingHoverEvent);
        }
      });
    }
  };

  // Hook so the MWT spawn box (appended to <body>, outside container) can
  // drive the normal dict/grammar popup pipeline when the user hovers the
  // unsandhied child text inside it.
  window.__mwtSpawnHoverHook = function (ev, spawnInner) {
    if (!spawnInner) return;
    try {
      var spawnContext =
        spawnInner.__mwtSpawnContext && typeof spawnInner.__mwtSpawnContext === 'object'
          ? spawnInner.__mwtSpawnContext
          : null;
      var isKoreanCompoundSpawn = !!(spawnContext && spawnContext.isKoreanCompoundLemmaSpawn);
      if (isKoreanCompoundSpawn) {
        segmentRenderingState.lastMouseX = ev.clientX;
        segmentRenderingState.lastMouseY = ev.clientY;
      }
      var segIdxHk =
        spawnContext && isFinite(Number(spawnContext.segIdx))
          ? Number(spawnContext.segIdx)
          : parseInt(spawnInner.dataset.index || '-1', 10);
      var partIdxHk =
        !isKoreanCompoundSpawn && spawnContext && isFinite(Number(spawnContext.partIdx))
          ? Number(spawnContext.partIdx)
          : !isKoreanCompoundSpawn
            ? normalizeUdPartIndex(spawnInner.dataset.mwtPartIndex)
            : null;
      var resHk = isKoreanCompoundSpawn
        ? spawnContext && spawnContext.lookupResult
          ? spawnContext.lookupResult
          : null
        : spawnContext && spawnContext.lookupResult
          ? spawnContext.lookupResult
          : resultsBySeg && segIdxHk >= 0
            ? resultsBySeg[segIdxHk]
            : null;
      var fillHk = resHk && Array.isArray(resHk.dict_fill) ? resHk.dict_fill : [];
      var spawnFillHit = ev.target && ev.target.closest ? ev.target.closest('.reader-token-fill-hit') : null;
      if (spawnFillHit && !spawnInner.contains(spawnFillHit)) spawnFillHit = null;
      var spawnHasInternalFillHits = spawnInner.dataset && spawnInner.dataset.hasFillHits === '1';
      if (spawnHasInternalFillHits && !spawnFillHit) {
        segmentRenderingState.currentSpan = null;
        segmentRenderingState.currentFillHit = null;
        segmentRenderingState.currentPopupAnchorEl = null;
        hideHoverReticle();
        hidePopup();
        return;
      }
      var activeFillIndexesHk = spawnFillHit ? parseFillHitIndexes(spawnFillHit, fillHk.length) : [];
      segmentRenderingState.currentSpan = spawnInner;
      segmentRenderingState.currentFillHit = spawnFillHit || null;
      segmentRenderingState.currentPopupAnchorEl =
        spawnFillHit || (spawnHasInternalFillHits ? null : spawnInner);
      showHoverReticle(segmentRenderingState.currentPopupAnchorEl);
      buildPopupForSpan(spawnInner, resultsBySeg, gramOverlay, activeFillIndexesHk);
      hoverInteractionState.pendingHoverEvent = {
        segIdx: segIdxHk,
        mwtPartIdx: isKoreanCompoundSpawn ? null : normalizeUdPartIndex(partIdxHk),
        clientX: ev.clientX,
        clientY: ev.clientY
      };
      if (hoverInteractionState.hoverRafId) {
        cancelAnimationFrame(hoverInteractionState.hoverRafId);
        hoverInteractionState.hoverRafId = null;
      }
      hoverInteractionState.lastHoverProcessTime = performance.now();
      processHoverUpdate(hoverInteractionState.pendingHoverEvent);
    } catch (err) {
      /* swallow — hover must never throw */
    }
  };
  function _buildClickContext(segIdx, surfaceText, entry, posData, udTok) {
    var tokenEntry = entry && typeof entry === 'object' ? entry : null;
    var tokenSurface = String(surfaceText || '').trim();
    var tokenPosData = posData && typeof posData === 'object' ? posData : {};
    var tokenUdTok = udTok && typeof udTok === 'object' ? udTok : null;
    var tokenAnchor =
      getUdTokenSurfaceAnchor(tokenUdTok) ||
      getUdTokenSurfaceAnchor({
        surface_anchor: tokenEntry && tokenEntry.surface_anchor
      });
    var tokenAnchorText = String((tokenAnchor && tokenAnchor.text) || tokenSurface || '').trim();
    var tokenLookupText = String(
      (tokenEntry && (tokenEntry.text || tokenEntry.head || tokenEntry.surface_form)) || tokenSurface || ''
    ).trim();
    var tokenPopupReason =
      tokenAnchor &&
      tokenAnchorText &&
      tokenLookupText &&
      !hasSameVisibleComparisonText(tokenAnchorText, tokenLookupText)
        ? 'surface_anchor'
        : '';
    var tokenDictFill = tokenEntry && Array.isArray(tokenEntry.dict_fill) ? tokenEntry.dict_fill.slice() : [];
    var tokenLemma =
      tokenEntry && tokenEntry.lemma != null
        ? String(tokenEntry.lemma || '')
        : String(tokenPosData.lemma || '');
    var tokenLemmaRaw =
      tokenPosData.lemma_raw != null
        ? String(tokenPosData.lemma_raw || '')
        : tokenEntry && tokenEntry.lemma_raw != null
          ? String(tokenEntry.lemma_raw || '')
          : tokenLemma;
    var tokenLemmaSuffix =
      tokenPosData.lemma_suffix != null
        ? String(tokenPosData.lemma_suffix || '')
        : tokenEntry && tokenEntry.lemma_suffix != null
          ? String(tokenEntry.lemma_suffix || '')
          : '';
    return {
      segIdx: segIdx,
      surface: tokenAnchorText || tokenSurface,
      anchorText: tokenAnchorText || tokenSurface,
      lookupText: tokenLookupText || tokenAnchorText || tokenSurface,
      mwtPopupReason: tokenPopupReason,
      entry: tokenEntry,
      posData: tokenPosData,
      udTok: tokenUdTok,
      lemma: tokenLemma,
      lemma_raw: tokenLemmaRaw,
      lemma_suffix: tokenLemmaSuffix,
      dictFill: tokenDictFill
    };
  }
  function _activateTokenMapForClickContext(context) {
    var ctx = context || {};
    var bannerCtx = ctx.bannerContext && typeof ctx.bannerContext === 'object' ? ctx.bannerContext : ctx;
    var forceParentTokenMap = !!(ctx.forceParentTokenMap || ctx.isKoreanCompoundLemmaSpawn);
    var entry = bannerCtx.entry && typeof bannerCtx.entry === 'object' ? bannerCtx.entry : null;
    var dictFill = Array.isArray(bannerCtx.dictFill)
      ? bannerCtx.dictFill.slice()
      : entry && Array.isArray(entry.dict_fill)
        ? entry.dict_fill.slice()
        : [];
    var panelEntry = ctx.entry && typeof ctx.entry === 'object' ? ctx.entry : null;
    var _ctxPartIdx = forceParentTokenMap ? null : normalizeUdPartIndex(ctx.mwtPartIndex);
    if (_ctxPartIdx === null) _ctxPartIdx = normalizeUdPartIndex(bannerCtx.mwtPartIndex);
    if (forceParentTokenMap) _ctxPartIdx = null;
    var _ctxPopupReason = forceParentTokenMap
      ? String(bannerCtx.mwtPopupReason || '').trim()
      : String(ctx.mwtPopupReason || bannerCtx.mwtPopupReason || '').trim();
    var _ctxLookupText = forceParentTokenMap
      ? String(bannerCtx.lookupText || bannerCtx.mwtChildText || '').trim()
      : String(
          ctx.lookupText || bannerCtx.lookupText || ctx.mwtChildText || bannerCtx.mwtChildText || ''
        ).trim();
    var _ctxAnchorText = forceParentTokenMap
      ? String(bannerCtx.anchorText || bannerCtx.mwtSurfaceSlice || '').trim()
      : String(
          ctx.anchorText || bannerCtx.anchorText || ctx.mwtSurfaceSlice || bannerCtx.mwtSurfaceSlice || ''
        ).trim();
    if (!_ctxAnchorText && _ctxPartIdx != null) {
      _ctxAnchorText = getMwtPartSurfaceSliceText(
        String(bannerCtx.surface || ''),
        bannerCtx.udTok && typeof bannerCtx.udTok === 'object' ? bannerCtx.udTok : null,
        _ctxPartIdx,
        ''
      );
    }
    if (!_ctxAnchorText) _ctxAnchorText = getTokenMapAnchorText(bannerCtx) || getTokenMapAnchorText(ctx);
    if (!_ctxLookupText) {
      _ctxLookupText = forceParentTokenMap
        ? getTokenMapLookupText(bannerCtx) || getTokenMapLookupText(ctx)
        : getTokenMapLookupText(ctx) || getTokenMapLookupText(bannerCtx);
    }
    var _ctxMwtChildText =
      _ctxPartIdx != null ? String(ctx.mwtChildText || bannerCtx.mwtChildText || '').trim() : '';
    hoverLayoutState.tokenMapData = {
      segIdx: isFinite(Number(bannerCtx.segIdx)) ? Number(bannerCtx.segIdx) : -1,
      mwtPartIndex: _ctxPartIdx != null ? _ctxPartIdx : undefined,
      mwtPopupReason: _ctxPopupReason,
      lookupText: _ctxLookupText,
      anchorText: _ctxAnchorText,
      mwtChildText: _ctxMwtChildText,
      mwtSurfaceSlice: _ctxAnchorText,
      surface: String(_ctxAnchorText || bannerCtx.surface || ''),
      lemma: String(bannerCtx.lemma || ''),
      lemma_raw: String(bannerCtx.lemma_raw || bannerCtx.lemma || ''),
      lemma_suffix: String(bannerCtx.lemma_suffix || ''),
      posData: bannerCtx.posData && typeof bannerCtx.posData === 'object' ? bannerCtx.posData : {},
      udTok: bannerCtx.udTok && typeof bannerCtx.udTok === 'object' ? bannerCtx.udTok : null,
      entry: entry,
      tokenEntry: entry,
      panelEntry: panelEntry,
      dictFill: dictFill.slice(),
      tokenDictFill: dictFill.slice(),
      fillMode: getLookupEntryFillMode(entry),
      tokenFillMode: getLookupEntryFillMode(entry),
      resolvedVia: getLookupEntryResolvedVia(entry),
      tokenResolvedVia: getLookupEntryResolvedVia(entry),
      surfaceLookup: null,
      lemmaLookup: null,
      lemmaPartLookups: Object.create(null),
      lemmaPartLookupsByIndex: Object.create(null),
      surfaceLookupPromise: null,
      lemmaLookupPromise: null,
      lemmaPartLookupPromises: Object.create(null),
      lemmaPartLookupPromisesByIndex: Object.create(null),
      headDecompByForm: null
    };
    hoverLayoutState.tokenMapVisible = false;
    tokenBannerMenuState._bannerActiveFillKey = null;
  }
  function _openSidePanelForClickContext(context, clickedFill) {
    var ctx = context || {};
    var entry = ctx.entry && typeof ctx.entry === 'object' ? ctx.entry : null;
    var surface = getTokenMapAnchorText(ctx) || String(ctx.surface || '').trim();
    var lookupText = getTokenMapLookupText(ctx) || surface;
    var segIdx = isFinite(Number(ctx.segIdx)) ? Number(ctx.segIdx) : -1;

    // Update sentence context so entry note generation has context
    hoverLayoutState._currentPopupSentenceCtx = _buildExpandedCtxForSeg(segIdx, surface);
    function _pushAssistantContext(panelEntry, panelSurface) {
      if (!window.LEAssistant || typeof window.LEAssistant.updateContext !== 'function') {
        return;
      }
      var _surface = panelSurface || surface;
      setTimeout(function () {
        try {
          var _tokObj = _buildAssistantTokenCtx(ctx, panelEntry, _surface);
          var _sentObj = _buildAssistantSentenceCtx(segIdx);
          var _readObj = _buildAssistantReaderCtx();
          window.LEAssistant.updateContext({
            tokenSurface: (_tokObj && _tokObj.surface) || _surface,
            segIdx: segIdx,
            token: {
              data: _tokObj,
              text: _serializeAssistantToken(_tokObj)
            },
            sentence: {
              data: _sentObj,
              text: _serializeAssistantSentence(_sentObj)
            },
            reader: {
              data: _readObj,
              text: _serializeAssistantReader(_readObj)
            }
          });
        } catch (_e) {}
      }, 0);
    }
    var dictFill = Array.isArray(ctx.dictFill)
      ? ctx.dictFill.slice()
      : entry && Array.isArray(entry.dict_fill)
        ? entry.dict_fill.slice()
        : [];
    var panelOptsBase = {
      _lookupLang: String(documentShellState.currentLanguage || ''),
      _panelTokenSurface: surface,
      _panelTokenLemma: String(ctx.lemma || ''),
      _panelTokenLemmaRaw: String(ctx.lemma_raw || ctx.lemma || '')
    };
    _activateTokenMapForClickContext(ctx);
    if (clickedFill && dictFill.length) {
      var clickedFillIndexes = parseFillHitIndexes(clickedFill, dictFill.length);
      if (clickedFillIndexes.length === 1) {
        var fillIndex = clickedFillIndexes[0];
        var fillEntry = dictFill[fillIndex];
        var fillHead = getEntryDisplayHead(fillEntry, clickedFill.dataset.fillText || surface || '');
        if (fillEntry && fillHead) {
          togglePanel(true);
          displayDictEntry(fillEntry, fillHead, panelOptsBase);
          _pushAssistantContext(fillEntry, fillHead);
          return true;
        }
      }
      if (clickedFillIndexes.length > 1 && entry) {
        var groupedPanelEntry = buildTokenMapGroupedFillEntry(
          entry,
          clickedFillIndexes,
          clickedFill.dataset.fillText || surface,
          dictFill
        );
        if (groupedPanelEntry) {
          togglePanel(true);
          displayDictEntry(
            groupedPanelEntry,
            String(clickedFill.dataset.fillText || surface || ''),
            panelOptsBase
          );
          _pushAssistantContext(groupedPanelEntry, String(clickedFill.dataset.fillText || surface || ''));
          return true;
        }
      }
    }
    var isUnknownMain = !!(entry && isUnknownDictEntry(entry));
    var segUpos = entry && entry.upos ? String(entry.upos) : String((ctx.posData && ctx.posData.upos) || '');
    var segXpos =
      entry && entry.tag
        ? String(entry.tag)
        : String((ctx.posData && (ctx.posData.tag || ctx.posData.xpos)) || '');
    togglePanel(true);
    if (entry) {
      displayDictEntry(entry, lookupText || surface, panelOptsBase);
      _pushAssistantContext(entry, surface);
    } else if (lookupText) {
      lookupAndDisplay(lookupText, {
        raw: true,
        exact: true,
        allowFuzzy: isUnknownMain,
        segIdx: segIdx,
        baseToken: lookupText,
        unknownPiece: isUnknownMain ? lookupText : '',
        clickedPiece: lookupText,
        lemma: String(ctx.lemma || ''),
        lemmaRaw: String(ctx.lemma_raw || ctx.lemma || ''),
        upos: segUpos,
        xpos: segXpos,
        onResolved: function (resolvedEntry) {
          _pushAssistantContext(resolvedEntry, surface);
        }
      });
    } else {
      return false;
    }
    return true;
  }
  window.__mwtSpawnClickHook = function (ev, spawnInner) {
    if (!spawnInner) return;
    try {
      var spawnContext =
        spawnInner.__mwtSpawnContext && typeof spawnInner.__mwtSpawnContext === 'object'
          ? spawnInner.__mwtSpawnContext
          : null;
      if (!spawnContext) return;
      var spawnFillHit = ev.target && ev.target.closest ? ev.target.closest('.reader-token-fill-hit') : null;
      if (spawnFillHit && !spawnInner.contains(spawnFillHit)) spawnFillHit = null;
      var spawnHasInternalFillHits = spawnInner.dataset && spawnInner.dataset.hasFillHits === '1';
      if (spawnHasInternalFillHits && !spawnFillHit) return;
      ev.preventDefault();
      ev.stopPropagation();
      var parentEntry =
        resultsBySeg && isFinite(Number(spawnContext.segIdx)) && Number(spawnContext.segIdx) >= 0
          ? resultsBySeg[Number(spawnContext.segIdx)] || null
          : null;
      var parentUdTok = getUdInfoForSegment(spawnContext.segIdx);
      var parentPosData = resolveSegmentPosData(spawnContext.segIdx, parentEntry, parentUdTok);
      var parentSurface = String(
        (parentEntry && parentEntry.surface_form) ||
          (hoverLayoutState.latestSegments && hoverLayoutState.latestSegments[Number(spawnContext.segIdx)]) ||
          ''
      ).trim();
      var parentSurfaceSlice = spawnContext.useChildAsClickSurface
        ? String(spawnContext.childText || '').trim()
        : String(spawnContext.anchorText || '').trim() ||
          getMwtPartSurfaceSliceText(parentSurface, parentUdTok, spawnContext.partIdx, '');
      var clickEntry = spawnContext.forceLookupOnClick ? null : spawnContext.lookupResult;
      var clickSurface = spawnContext.useChildAsClickSurface
        ? String(spawnContext.childText || '')
        : parentSurface || spawnContext.childText;
      var spawnClickContext = _buildClickContext(
        spawnContext.segIdx,
        clickSurface,
        clickEntry,
        spawnContext.posData,
        spawnContext.udTok
      );
      spawnClickContext.mwtSurfaceSlice = parentSurfaceSlice;
      spawnClickContext.anchorText = parentSurfaceSlice;
      if (spawnContext.isKoreanCompoundLemmaSpawn) {
        spawnClickContext.isKoreanCompoundLemmaSpawn = true;
        spawnClickContext.forceParentTokenMap = true;
      }
      if (
        parentEntry &&
        parentSurface &&
        (!spawnContext.useChildAsClickSurface || spawnContext.isKoreanCompoundLemmaSpawn)
      ) {
        spawnClickContext.bannerContext = _buildClickContext(
          spawnContext.segIdx,
          parentSurface,
          parentEntry,
          parentPosData,
          parentUdTok
        );
        var bannerSurfaceSlice = spawnContext.isKoreanCompoundLemmaSpawn ? parentSurface : parentSurfaceSlice;
        spawnClickContext.bannerContext.mwtSurfaceSlice = bannerSurfaceSlice;
        spawnClickContext.bannerContext.anchorText = bannerSurfaceSlice;
      }
      if (!spawnContext.isKoreanCompoundLemmaSpawn && isFinite(Number(spawnContext.partIdx))) {
        spawnClickContext.mwtPartIndex = Number(spawnContext.partIdx);
        spawnClickContext.mwtChildText = String(spawnContext.childText || '');
        spawnClickContext.lookupText = String(spawnContext.lookupText || spawnContext.childText || '');
        spawnClickContext.mwtPopupReason = String(spawnContext.popupReason || 'surface_anchor');
        if (spawnClickContext.bannerContext) {
          spawnClickContext.bannerContext.mwtPartIndex = Number(spawnContext.partIdx);
          spawnClickContext.bannerContext.mwtChildText = String(spawnContext.childText || '');
          spawnClickContext.bannerContext.lookupText = String(
            spawnContext.lookupText || spawnContext.childText || ''
          );
          spawnClickContext.bannerContext.mwtSurfaceSlice = parentSurfaceSlice;
          spawnClickContext.bannerContext.anchorText = parentSurfaceSlice;
          spawnClickContext.bannerContext.mwtPopupReason = String(
            spawnContext.popupReason || 'surface_anchor'
          );
        }
      }
      _openSidePanelForClickContext(spawnClickContext, spawnFillHit || null);
    } catch (err) {
      /* swallow — click must never throw */
    }
  };
  container.onmouseleave = function () {
    if (mwtContextState._mwtSpawnActive) return;
    segmentRenderingState.currentSpan = null;
    segmentRenderingState.currentFillHit = null;
    segmentRenderingState.currentPopupAnchorEl = null;
    // Don't hide the popup while the MWT spawn box is showing — the user
    // may be about to move into it.
    if (!mwtContextState._mwtSpawnActive) hidePopup();
    hideUdLines();
    hideNerHover();
    hideHoverReticle();
    clearChunkHighlight();
    lastHighlightedSegIdx = -2;
    lastHighlightedHoverKey = '';
    glossRequestsState.lastUdHoverKey = '';
    // Cancel any pending RAF
    if (hoverInteractionState.hoverRafId) {
      cancelAnimationFrame(hoverInteractionState.hoverRafId);
      hoverInteractionState.hoverRafId = null;
    }
    hoverInteractionState.pendingHoverEvent = null;
  };
  container.onclick = function (ev) {
    var span = ev.target && ev.target.closest('.reader-token');
    if (!span) return;
    if (span.classList.contains('reader-punct')) return;
    // Resolve the most plausible segment index for click location.
    var segIdx = resolveSegIdxForSpan(span, ev.clientX);
    if (segIdx >= 0 && span.dataset && String(span.dataset.index) !== String(segIdx)) {
      span.dataset.index = String(segIdx);
      if (hoverLayoutState.latestSegments && hoverLayoutState.latestSegments[segIdx])
        span.dataset.seg = String(hoverLayoutState.latestSegments[segIdx]);
    }
    var seg = '';
    if (segIdx >= 0 && hoverLayoutState.latestSegments && hoverLayoutState.latestSegments[segIdx]) {
      seg = String(hoverLayoutState.latestSegments[segIdx]);
      if (span.dataset) span.dataset.seg = seg;
    } else {
      seg = span.dataset.seg || '';
    }
    if (!seg) return;
    var clickedFill = ev.target && ev.target.closest ? ev.target.closest('.reader-token-fill-hit') : null;
    var resForSeg = resultsBySeg && segIdx >= 0 ? resultsBySeg[segIdx] : null;
    var clickMwtPartEl = ev.target && ev.target.closest ? ev.target.closest('[data-mwt-part-index]') : null;
    if (clickMwtPartEl && !(span && span.contains(clickMwtPartEl))) clickMwtPartEl = null;
    var clickMwtPartIdx = clickMwtPartEl ? normalizeUdPartIndex(clickMwtPartEl.dataset.mwtPartIndex) : null;
    var _tmUdTok = getUdInfoForSegment(segIdx);
    var _tmPosData = resolveSegmentPosData(segIdx, resForSeg, _tmUdTok);
    var clickContext = _buildClickContext(segIdx, seg, resForSeg, _tmPosData, _tmUdTok);
    if (isFinite(Number(clickMwtPartIdx))) {
      clickContext.mwtPartIndex = Number(clickMwtPartIdx);
      clickContext.mwtChildText =
        clickMwtPartEl && clickMwtPartEl.dataset ? String(clickMwtPartEl.dataset.mwtChildText || '') : '';
      clickContext.lookupText = clickContext.mwtChildText || clickContext.lookupText || '';
      clickContext.mwtSurfaceSlice =
        clickMwtPartEl && clickMwtPartEl.dataset && clickMwtPartEl.dataset.mwtSurfaceSlice
          ? String(clickMwtPartEl.dataset.mwtSurfaceSlice || '')
          : getMwtPartSurfaceSliceText(seg, _tmUdTok, clickMwtPartIdx, '');
      clickContext.anchorText =
        clickContext.mwtSurfaceSlice || clickContext.anchorText || clickContext.surface || '';
      clickContext.mwtPopupReason =
        clickMwtPartEl && clickMwtPartEl.dataset
          ? String(clickMwtPartEl.dataset.mwtPopupReason || '')
          : clickContext.mwtPopupReason;
    }
    if (clickMwtPartEl && clickMwtPartEl.dataset && clickMwtPartEl.dataset.mwtMismatch === '1') {
      return;
    }
    if (!clickMwtPartEl && span.dataset && span.dataset.koCompoundLemmaSpawn === '1') {
      return;
    }
    _openSidePanelForClickContext(
      clickContext,
      clickedFill && span.contains(clickedFill) ? clickedFill : null
    );
  };
}
export function initializeHoverInteraction() {
  hoverInteractionState.fuzzyCache = {
    has: function (key) {
      return hasTokenLookupStateField(key, 'fuzzy', '');
    },
    get: function (key) {
      return getTokenLookupStateField(key, 'fuzzy', '');
    },
    set: function (key, value) {
      setTokenLookupStateField(key, 'fuzzy', value, '');
    },
    delete: function (key) {
      var record = getTokenLookupStateRecord(key, '', false);
      if (record) record.fuzzy = null;
    },
    clear: function () {
      clearTokenLookupStateField('fuzzy');
    }
  };

  // === PERFORMANCE CACHES ===
  hoverInteractionState.cachedRowBands = null; // Row bands for popup positioning (computed once per render)
  hoverInteractionState.cachedRowSnapPoints = null; // Snap points derived from row bands
  hoverInteractionState.cachedRowGapRanges = null; // Gap ranges between rows
  hoverInteractionState.hoverRafId = null; // requestAnimationFrame ID for debouncing
  hoverInteractionState.pendingHoverEvent = null; // Pending hover event data
  hoverInteractionState.lastHoverProcessTime = 0; // Last time hover was processed (for throttling)
  hoverInteractionState.hoverThrottleMs = 8;
  return true;
}
