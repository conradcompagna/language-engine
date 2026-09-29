import { onDocxContinuousScroll, stepDocumentPage } from './continuous-scroll.mjs';
import { expandHighlightSetForCollapsedSpans, getSentenceSpansFromSegments } from './dependency-geometry.mjs';
import { normalizeUdPartIndex } from './dependency-hover.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { positionPopup } from './dictionary-popup.mjs';
import {
  drawLocalSourceInspectorSelection,
  isDocxContinuousActive,
  isLocalSourceInspectorAvailable,
  scrollDocxContinuousBy,
  scrollWebSnapshotBy
} from './document-navigation.mjs';
import {
  applyFixedDocumentViewportHeight,
  isRawContinuousActive,
  onRawContinuousScroll,
  scrollRawContinuousBy,
  updateDocumentNavigatorThumb
} from './document-search.mjs';
import {
  debounce,
  renderAllPdfPages,
  scrollPdfJsSourcePageIntoView,
  updateActivePdfPageFromSourceScroll
} from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { requestMovementLookup } from './document-state.mjs';
import { documentState } from './document-state.state.mjs';
import {
  isActiveEpubDocument,
  isActiveFoliateFlowDocument,
  isActiveWebSnapshotDocument,
  isFlowScrollDocumentActive,
  syncDocumentChrome
} from './foliate-viewport.mjs';
import { getSentenceTabletGlossText } from './gloss-entries.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { lookupProgressState } from './lookup-progress.state.mjs';
import { orthographyState } from './orthography.state.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
import { hidePopup, positionSidePanelPopup } from './side-panel.mjs';
import { invalidateUdRectCache, invalidateUiRectCache } from './token-fragments.mjs';
import { applyGlobalViewportClamp, snapDocxToLine, snapToLine } from './viewport-clamping.mjs';
export function handlePagerScrollStop() {
  if (documentState.inputMode === 'pdf') {
    if (!documentShellState.pdfJsIframe) updateActivePdfPageFromSourceScroll();
    return;
  }
  if (documentState.inputMode !== 'doc') return;
  if (isFlowScrollDocumentActive()) return;
  if (documentState.isOriginalView && documentState.currentFileType === 'docx') {
    snapDocxToLine();
  } else {
    snapToLine();
  }
}
export // Map segIdx -> Map(partIdx -> fill-hit element)

function makeUdNodeId(segIdx, partIdx) {
  var seg = parseInt(segIdx, 10);
  if (!isFinite(seg)) return null;
  var part = normalizeUdPartIndex(partIdx);
  return part !== null ? String(seg) + ':' + String(part) : String(seg);
}
export function resolveUdAtomicNodeId(nodeMap, segIdx, partIdx) {
  var rawSeg = parseInt(segIdx, 10);
  if (!isFinite(rawSeg)) return null;
  var rawPart = normalizeUdPartIndex(partIdx);
  var exactId = makeUdNodeId(rawSeg, rawPart);
  if (exactId && nodeMap && nodeMap[exactId]) return exactId;
  var fallbackId = makeUdNodeId(rawSeg, null);
  if (fallbackId && nodeMap && nodeMap[fallbackId]) return fallbackId;
  return null;
}
export function buildUdAtomicHighlightState(nodeSet, hoverNodeId) {
  var struct = dependencyState.latestUdStructure || {};
  var nodeMap = struct.atomicNodeMap || {};
  var atomicNodes = new Set();
  var segSet = new Set();
  var partsBySeg = new Map();
  if (nodeSet && typeof nodeSet.forEach === 'function') {
    nodeSet.forEach(function (nodeId) {
      var meta = nodeMap[nodeId];
      if (!meta) return;
      atomicNodes.add(nodeId);
      segSet.add(meta.segIdx);
      if (meta.partIdx !== null) {
        var partSet = partsBySeg.get(meta.segIdx);
        if (!partSet) {
          partSet = new Set();
          partsBySeg.set(meta.segIdx, partSet);
        }
        partSet.add(meta.partIdx);
      }
    });
  }
  if (hoverNodeId && nodeMap[hoverNodeId]) {
    atomicNodes.add(hoverNodeId);
    segSet.add(nodeMap[hoverNodeId].segIdx);
    if (nodeMap[hoverNodeId].partIdx !== null) {
      var hoverPartSet = partsBySeg.get(nodeMap[hoverNodeId].segIdx);
      if (!hoverPartSet) {
        hoverPartSet = new Set();
        partsBySeg.set(nodeMap[hoverNodeId].segIdx, hoverPartSet);
      }
      hoverPartSet.add(nodeMap[hoverNodeId].partIdx);
    }
  }
  return {
    nodeSet: atomicNodes,
    segSet: expandHighlightSetForCollapsedSpans(segSet),
    partsBySeg: partsBySeg,
    hoverNodeId: hoverNodeId || null
  };
}
export function normalizeUdSentenceSpans(raw) {
  var out = [];
  if (!Array.isArray(raw)) return out;
  for (var i = 0; i < raw.length; i++) {
    var s = raw[i];
    if (Array.isArray(s) && s.length >= 2 && isFinite(s[0]) && isFinite(s[1])) {
      out.push([s[0], s[1]]);
      continue;
    }
    if (s && typeof s === 'object') {
      var start =
        typeof s.seg_start === 'number' ? s.seg_start : typeof s.start === 'number' ? s.start : null;
      var end = typeof s.seg_end === 'number' ? s.seg_end : typeof s.end === 'number' ? s.end : null;
      if (start !== null && end !== null) out.push([start, end]);
    }
  }
  return out;
}
export function getDepTreeExperimentSentenceSpans() {
  var spans = [];
  if (!Array.isArray(hoverLayoutState.latestSegments) || !hoverLayoutState.latestSegments.length)
    return spans;
  var raw =
    dependencyState.latestUdOverlay && Array.isArray(dependencyState.latestUdOverlay.sentences)
      ? dependencyState.latestUdOverlay.sentences
      : [];
  var doc2seg =
    dependencyState.latestUdOverlay && Array.isArray(dependencyState.latestUdOverlay.doc2seg)
      ? dependencyState.latestUdOverlay.doc2seg
      : [];
  for (var i = 0; i < raw.length; i++) {
    var sentence = raw[i];
    if (sentence && typeof sentence === 'object') {
      var segStart = typeof sentence.seg_start === 'number' ? sentence.seg_start : null;
      var segEnd = typeof sentence.seg_end === 'number' ? sentence.seg_end : null;
      if (segStart !== null && segEnd !== null && segEnd > segStart) {
        spans.push({
          start: segStart,
          end: segEnd
        });
        continue;
      }
    }
    if (Array.isArray(sentence) && sentence.length >= 2 && doc2seg.length) {
      var docStart = Math.max(0, parseInt(sentence[0], 10) || 0);
      var docEnd = Math.min(doc2seg.length, parseInt(sentence[1], 10) || 0);
      var minSeg = Number.MAX_SAFE_INTEGER;
      var maxSeg = -1;
      for (var di = docStart; di < docEnd; di++) {
        var segIdx = parseInt(doc2seg[di], 10);
        if (!isFinite(segIdx) || segIdx < 0) continue;
        if (segIdx < minSeg) minSeg = segIdx;
        if (segIdx > maxSeg) maxSeg = segIdx;
      }
      if (maxSeg >= minSeg && minSeg >= 0) {
        spans.push({
          start: minSeg,
          end: maxSeg + 1
        });
        continue;
      }
    }
    if (Array.isArray(sentence) && sentence.length >= 2) {
      var start = parseInt(sentence[0], 10);
      var end = parseInt(sentence[1], 10);
      if (
        isFinite(start) &&
        isFinite(end) &&
        start >= 0 &&
        end > start &&
        end <= hoverLayoutState.latestSegments.length
      ) {
        spans.push({
          start: start,
          end: end
        });
      }
    }
  }
  if (!spans.length) {
    var fallback = getSentenceSpansFromSegments(hoverLayoutState.latestSegments);
    for (var fi = 0; fi < fallback.length; fi++) {
      spans.push({
        start: fallback[fi].start,
        end: fallback[fi].end
      });
    }
  }
  return spans;
}
export function getDepTreeExperimentGlossText(segIdx, surface, entry, udTok) {
  return getSentenceTabletGlossText(segIdx, surface, entry, udTok, null);
}
export function buildDepTreeExperimentSentencePayload(segIdx) {
  var spans = getDepTreeExperimentSentenceSpans();
  if (!spans.length) {
    return {
      ok: false,
      reason: 'no-segmentation',
      message: 'Run a lookup first.'
    };
  }
  var hoveredSegIdx = isFinite(Number(segIdx)) ? Number(segIdx) : -1;
  var sentenceInfo = null;
  for (var i = 0; i < spans.length; i++) {
    if (hoveredSegIdx >= spans[i].start && hoveredSegIdx < spans[i].end) {
      sentenceInfo = {
        index: i,
        start: spans[i].start,
        end: spans[i].end
      };
      break;
    }
  }
  if (!sentenceInfo && spans.length === 1) {
    sentenceInfo = {
      index: 0,
      start: spans[0].start,
      end: spans[0].end
    };
  }
  if (!sentenceInfo) {
    return {
      ok: false,
      reason: 'hover-needed',
      message: 'Hover a token in the reader to choose a sentence.',
      sentenceCount: spans.length
    };
  }
  var resultsBySeg =
    hoverLayoutState.latestData && Array.isArray(hoverLayoutState.latestData.results_by_seg)
      ? hoverLayoutState.latestData.results_by_seg
      : [];
  var tokens = [];
  for (var seg = sentenceInfo.start; seg < sentenceInfo.end; seg++) {
    var surface = String(
      (hoverLayoutState.latestSegments && hoverLayoutState.latestSegments[seg]) || ''
    ).trim();
    var udTok =
      dependencyState.latestUdTokenMap && dependencyState.latestUdTokenMap[seg]
        ? dependencyState.latestUdTokenMap[seg]
        : null;
    var entry = seg >= 0 && seg < resultsBySeg.length ? resultsBySeg[seg] || null : null;
    var headSegIdx = null;
    if (udTok) {
      var rawHead = Array.isArray(udTok.heads) ? udTok.heads[0] : udTok.head;
      if (isFinite(Number(rawHead))) headSegIdx = Number(rawHead);
    }
    if (
      String((udTok && (udTok.dep || udTok.deprel)) || '')
        .trim()
        .toLowerCase() === 'root'
    ) {
      headSegIdx = null;
    }
    if (headSegIdx === seg) headSegIdx = null;
    tokens.push({
      segIdx: seg,
      text: surface || String((udTok && (udTok.text || udTok.form)) || ''),
      dep: String((udTok && (udTok.dep || udTok.deprel)) || '').trim(),
      upos: String((udTok && udTok.upos) || '').trim(),
      headSegIdx: headSegIdx,
      gloss: getDepTreeExperimentGlossText(seg, surface, entry, udTok)
    });
  }
  return {
    ok: true,
    lang: String(documentShellState.currentLanguage || ''),
    sentenceIndex: sentenceInfo.index,
    sentenceCount: spans.length,
    startSeg: sentenceInfo.start,
    endSeg: sentenceInfo.end,
    hoverSegIdx: hoveredSegIdx >= 0 ? hoveredSegIdx : null,
    tokens: tokens
  };
}
export function buildDepTreeExperimentLegacyData(payload) {
  var srcTokens = payload && Array.isArray(payload.tokens) ? payload.tokens : [];
  if (!srcTokens.length) return null;
  var globalToLocal = {};
  var segments = [];
  var tokens = [];
  var edges = [];
  var roots = [];
  var doc2seg = [];
  var seg2doc = [];
  for (var i = 0; i < srcTokens.length; i++) {
    var src = srcTokens[i] || {};
    globalToLocal[src.segIdx] = i;
    segments.push(String(src.text || ''));
    doc2seg.push(i);
    seg2doc.push(i);
  }
  for (var ti = 0; ti < srcTokens.length; ti++) {
    var token = srcTokens[ti] || {};
    var localHead = -1;
    if (token.headSegIdx != null && Object.prototype.hasOwnProperty.call(globalToLocal, token.headSegIdx)) {
      localHead = globalToLocal[token.headSegIdx];
    }
    if (localHead === ti) localHead = -1;
    tokens.push({
      i: ti,
      doc_i: ti,
      text: String(token.text || ''),
      upos: String(token.upos || ''),
      head: localHead,
      dep: String(token.dep || ''),
      gloss: String(token.gloss || '')
    });
    if (localHead >= 0) {
      edges.push({
        from: localHead,
        to: ti,
        dep: String(token.dep || ''),
        upos: String(token.upos || '')
      });
    } else {
      roots.push(ti);
    }
  }
  return {
    segments: segments,
    udOverlay: {
      ok: true,
      tokens: tokens,
      edges: edges,
      roots: roots,
      ents: [],
      doc2seg: doc2seg,
      seg2doc: seg2doc,
      sentences: [[0, segments.length]]
    },
    originalText: segments.join(' ')
  };
}
export function loadInlineDepTreeFabState() {
  try {
    var raw = localStorage.getItem(hoverLayoutState.depTreeInlineFabStateKey);
    if (!raw) return null;
    var parsed = JSON.parse(raw);
    if (parsed && typeof parsed.left === 'number' && typeof parsed.top === 'number') {
      return parsed;
    }
  } catch (_e) {}
  return null;
}
export function saveInlineDepTreeFabState(left, top) {
  try {
    localStorage.setItem(
      hoverLayoutState.depTreeInlineFabStateKey,
      JSON.stringify({
        left: Number(left) || 0,
        top: Number(top) || 0
      })
    );
  } catch (_e) {}
}
export function clampInlineDepTreeFabPosition(left, top) {
  if (!orthographyState.depTreeInlineToggleBtn) {
    return {
      left: hoverLayoutState.DEP_TREE_INLINE_MARGIN,
      top: hoverLayoutState.DEP_TREE_INLINE_MARGIN
    };
  }
  var width = orthographyState.depTreeInlineToggleBtn.offsetWidth || 46;
  var height = orthographyState.depTreeInlineToggleBtn.offsetHeight || 46;
  var maxLeft = Math.max(
    hoverLayoutState.DEP_TREE_INLINE_MARGIN,
    window.innerWidth - width - hoverLayoutState.DEP_TREE_INLINE_MARGIN
  );
  var maxTop = Math.max(
    hoverLayoutState.DEP_TREE_INLINE_MARGIN,
    window.innerHeight - height - hoverLayoutState.DEP_TREE_INLINE_MARGIN
  );
  return {
    left: Math.min(
      Math.max(
        hoverLayoutState.DEP_TREE_INLINE_MARGIN,
        Number(left) || hoverLayoutState.DEP_TREE_INLINE_MARGIN
      ),
      maxLeft
    ),
    top: Math.min(
      Math.max(
        hoverLayoutState.DEP_TREE_INLINE_MARGIN,
        Number(top) || hoverLayoutState.DEP_TREE_INLINE_MARGIN
      ),
      maxTop
    )
  };
}
export function setInlineDepTreeFabPosition(left, top, persist) {
  if (!orthographyState.depTreeInlineToggleBtn) return null;
  var clamped = clampInlineDepTreeFabPosition(left, top);
  orthographyState.depTreeInlineToggleBtn.style.left = clamped.left + 'px';
  orthographyState.depTreeInlineToggleBtn.style.top = clamped.top + 'px';
  orthographyState.depTreeInlineToggleBtn.style.right = 'auto';
  orthographyState.depTreeInlineToggleBtn.style.bottom = 'auto';
  if (persist !== false) {
    saveInlineDepTreeFabState(clamped.left, clamped.top);
  }
  if (isInlineDepTreeOpen()) {
    positionInlineDepTreePanel();
  }
  return clamped;
}
export function restoreInlineDepTreeFabPosition() {
  if (!orthographyState.depTreeInlineToggleBtn) return null;
  var saved = loadInlineDepTreeFabState();
  if (saved) {
    return setInlineDepTreeFabPosition(saved.left, saved.top, true);
  }
  var rect = orthographyState.depTreeInlineToggleBtn.getBoundingClientRect();
  if (!rect || !rect.width || !rect.height) return null;
  return setInlineDepTreeFabPosition(rect.left, rect.top, true);
}
export function getInlineDepTreePlacementOrder(rect) {
  var horizontal = rect.left + rect.width / 2 < window.innerWidth / 2 ? ['right', 'left'] : ['left', 'right'];
  var vertical =
    rect.top + rect.height / 2 < window.innerHeight / 2 ? ['below', 'above'] : ['above', 'below'];
  return horizontal.concat(vertical);
}
export function buildInlineDepTreePanelCandidate(side, rect) {
  var viewportWidth = Math.max(0, window.innerWidth - hoverLayoutState.DEP_TREE_INLINE_MARGIN * 2);
  var viewportHeight = Math.max(0, window.innerHeight - hoverLayoutState.DEP_TREE_INLINE_MARGIN * 2);
  var width = 0;
  var height = 0;
  var left = hoverLayoutState.DEP_TREE_INLINE_MARGIN;
  var top = hoverLayoutState.DEP_TREE_INLINE_MARGIN;
  if (side === 'left' || side === 'right') {
    var availableWidth =
      side === 'right'
        ? Math.max(
            0,
            window.innerWidth -
              rect.right -
              hoverLayoutState.DEP_TREE_INLINE_GAP -
              hoverLayoutState.DEP_TREE_INLINE_MARGIN
          )
        : Math.max(
            0,
            rect.left - hoverLayoutState.DEP_TREE_INLINE_GAP - hoverLayoutState.DEP_TREE_INLINE_MARGIN
          );
    width = Math.min(hoverLayoutState.DEP_TREE_INLINE_PREF_WIDTH, availableWidth);
    height = Math.min(lookupProgressState.DEP_TREE_INLINE_PREF_HEIGHT, viewportHeight);
    left =
      side === 'right'
        ? rect.right + hoverLayoutState.DEP_TREE_INLINE_GAP
        : rect.left - hoverLayoutState.DEP_TREE_INLINE_GAP - width;
    top = rect.top + rect.height / 2 - height / 2;
    top = Math.min(
      Math.max(hoverLayoutState.DEP_TREE_INLINE_MARGIN, top),
      Math.max(
        hoverLayoutState.DEP_TREE_INLINE_MARGIN,
        window.innerHeight - height - hoverLayoutState.DEP_TREE_INLINE_MARGIN
      )
    );
  } else {
    var availableHeight =
      side === 'below'
        ? Math.max(
            0,
            window.innerHeight -
              rect.bottom -
              hoverLayoutState.DEP_TREE_INLINE_GAP -
              hoverLayoutState.DEP_TREE_INLINE_MARGIN
          )
        : Math.max(
            0,
            rect.top - hoverLayoutState.DEP_TREE_INLINE_GAP - hoverLayoutState.DEP_TREE_INLINE_MARGIN
          );
    width = Math.min(lookupProgressState.DEP_TREE_INLINE_PREF_WIDTH_WIDE, viewportWidth);
    height = Math.min(lookupProgressState.DEP_TREE_INLINE_PREF_HEIGHT, availableHeight);
    left = rect.left + rect.width / 2 - width / 2;
    left = Math.min(
      Math.max(hoverLayoutState.DEP_TREE_INLINE_MARGIN, left),
      Math.max(
        hoverLayoutState.DEP_TREE_INLINE_MARGIN,
        window.innerWidth - width - hoverLayoutState.DEP_TREE_INLINE_MARGIN
      )
    );
    top =
      side === 'below'
        ? rect.bottom + hoverLayoutState.DEP_TREE_INLINE_GAP
        : rect.top - hoverLayoutState.DEP_TREE_INLINE_GAP - height;
  }
  width = Math.max(0, Math.floor(width));
  height = Math.max(0, Math.floor(height));
  return {
    side: side,
    left: Math.round(left),
    top: Math.round(top),
    width: width,
    height: height,
    fits:
      width >= hoverLayoutState.DEP_TREE_INLINE_MIN_WIDTH &&
      height >= hoverLayoutState.DEP_TREE_INLINE_MIN_HEIGHT,
    area: width * height
  };
}
export function positionInlineDepTreePanel() {
  if (!orthographyState.depTreeInlinePanelEl || !orthographyState.depTreeInlineToggleBtn) return null;
  var rect = orthographyState.depTreeInlineToggleBtn.getBoundingClientRect();
  if (!rect || !rect.width || !rect.height) return null;
  var orderedSides = getInlineDepTreePlacementOrder(rect);
  var best = null;
  for (var i = 0; i < orderedSides.length; i++) {
    var candidate = buildInlineDepTreePanelCandidate(orderedSides[i], rect);
    if (!best || candidate.area > best.area) {
      best = candidate;
    }
    if (candidate.fits) {
      best = candidate;
      break;
    }
  }
  if (!best) return null;
  orthographyState.depTreeInlinePanelEl.style.left = best.left + 'px';
  orthographyState.depTreeInlinePanelEl.style.top = best.top + 'px';
  orthographyState.depTreeInlinePanelEl.style.width = best.width + 'px';
  orthographyState.depTreeInlinePanelEl.style.height = best.height + 'px';
  orthographyState.depTreeInlinePanelEl.dataset.side = best.side;
  return best;
}
export function syncInlineDepTreeButtonState(open) {
  if (!orthographyState.depTreeInlineToggleBtn) return;
  var isOpen = !!open;
  orthographyState.depTreeInlineToggleBtn.classList.toggle('active', isOpen);
  orthographyState.depTreeInlineToggleBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  orthographyState.depTreeInlineToggleBtn.setAttribute(
    'title',
    isOpen ? 'Hide dependency tree' : 'Show dependency tree'
  );
}
export function refitInlineDepTreeSoon() {
  if (!isInlineDepTreeOpen()) return;
  window.requestAnimationFrame(function () {
    positionInlineDepTreePanel();
    if (
      hoverLayoutState.depTreeInlineController &&
      typeof hoverLayoutState.depTreeInlineController.refitView === 'function'
    ) {
      hoverLayoutState.depTreeInlineController.refitView();
    }
  });
}
export function ensureInlineDepTreeReady() {
  if (hoverLayoutState.depTreeInlineInitialized) return !!hoverLayoutState.depTreeInlineController;
  if (
    !orthographyState.depTreeInlineHostEl ||
    !window.DepTreeView ||
    typeof window.DepTreeView.init !== 'function'
  ) {
    return false;
  }
  hoverLayoutState.depTreeInlineController = window.DepTreeView;
  hoverLayoutState.depTreeInlineController.init({
    container: orthographyState.depTreeInlineHostEl,
    chunkHighlight: false,
    dictPopup: false,
    linearClauseSplit: false
  });
  if (typeof hoverLayoutState.depTreeInlineController.setVisible === 'function') {
    hoverLayoutState.depTreeInlineController.setVisible(false);
  }
  hoverLayoutState.depTreeInlineInitialized = true;
  return true;
}
export function isInlineDepTreeOpen() {
  return !!(
    orthographyState.depTreeInlinePanelEl && orthographyState.depTreeInlinePanelEl.classList.contains('open')
  );
}
export function renderInlineDepTreePayload(payload) {
  if (!ensureInlineDepTreeReady() || !hoverLayoutState.depTreeInlineController) return false;
  if (!payload || !payload.ok || !Array.isArray(payload.tokens) || !payload.tokens.length) {
    if (typeof hoverLayoutState.depTreeInlineController._renderEmpty === 'function') {
      hoverLayoutState.depTreeInlineController._renderEmpty(
        (payload && payload.message) || 'Hover a token in the reader to choose a sentence.'
      );
    } else {
      hoverLayoutState.depTreeInlineController.setData({
        segments: [],
        udOverlay: null
      });
    }
    refitInlineDepTreeSoon();
    return true;
  }
  var data = buildDepTreeExperimentLegacyData(payload);
  if (!data) {
    if (typeof hoverLayoutState.depTreeInlineController._renderEmpty === 'function') {
      hoverLayoutState.depTreeInlineController._renderEmpty(
        'No dependency data was available for this sentence.'
      );
    }
    refitInlineDepTreeSoon();
    return true;
  }
  hoverLayoutState.depTreeInlineController.setData(data);
  refitInlineDepTreeSoon();
  return true;
}
export function syncInlineDepTree(reason) {
  if (!isInlineDepTreeOpen()) return false;
  return renderInlineDepTreePayload(
    buildDepTreeExperimentSentencePayload(hoverLayoutState.depTreeExperimentLastHoveredSegIdx)
  );
}
export function setInlineDepTreeOpen(open) {
  if (!orthographyState.depTreeInlinePanelEl || !orthographyState.depTreeInlineToggleBtn) return false;
  var nextOpen = !!open;
  orthographyState.depTreeInlinePanelEl.classList.toggle('open', nextOpen);
  orthographyState.depTreeInlinePanelEl.setAttribute('aria-hidden', nextOpen ? 'false' : 'true');
  syncInlineDepTreeButtonState(nextOpen);
  if (nextOpen) {
    positionInlineDepTreePanel();
  }
  if (
    ensureInlineDepTreeReady() &&
    hoverLayoutState.depTreeInlineController &&
    typeof hoverLayoutState.depTreeInlineController.setVisible === 'function'
  ) {
    hoverLayoutState.depTreeInlineController.setVisible(nextOpen);
  }
  if (nextOpen) {
    hidePopup();
    syncInlineDepTree('open');
    refitInlineDepTreeSoon();
  }
  return nextOpen;
}
export function openInlineDepTreeTool() {
  setInlineDepTreeOpen(true);
  return orthographyState.depTreeInlinePanelEl;
}
export function closeInlineDepTreeTool() {
  setInlineDepTreeOpen(false);
}
export function toggleInlineDepTreeTool() {
  setInlineDepTreeOpen(!isInlineDepTreeOpen());
}
export function onInlineDepTreeFabDragMove(event) {
  if (!hoverLayoutState.depTreeInlineFabDragState) return;
  var deltaX = event.clientX - hoverLayoutState.depTreeInlineFabDragState.startX;
  var deltaY = event.clientY - hoverLayoutState.depTreeInlineFabDragState.startY;
  if (!hoverLayoutState.depTreeInlineFabDragState.dragged && Math.abs(deltaX) < 4 && Math.abs(deltaY) < 4)
    return;
  hoverLayoutState.depTreeInlineFabDragState.dragged = true;
  setInlineDepTreeFabPosition(
    event.clientX - hoverLayoutState.depTreeInlineFabDragState.offsetX,
    event.clientY - hoverLayoutState.depTreeInlineFabDragState.offsetY,
    true
  );
  event.preventDefault();
}
export function stopInlineDepTreeFabDrag() {
  if (!hoverLayoutState.depTreeInlineFabDragState) return;
  if (hoverLayoutState.depTreeInlineFabDragState.dragged) {
    hoverLayoutState.depTreeInlineFabIgnoreClickUntil = Date.now() + 250;
    positionInlineDepTreePanel();
  }
  hoverLayoutState.depTreeInlineFabDragState = null;
  document.removeEventListener('mousemove', onInlineDepTreeFabDragMove);
  document.removeEventListener('mouseup', stopInlineDepTreeFabDrag);
}
export function startInlineDepTreeFabDrag(event) {
  if (event.button !== 0 || !orthographyState.depTreeInlineToggleBtn) return;
  var rect = orthographyState.depTreeInlineToggleBtn.getBoundingClientRect();
  hoverLayoutState.depTreeInlineFabDragState = {
    startX: event.clientX,
    startY: event.clientY,
    offsetX: event.clientX - rect.left,
    offsetY: event.clientY - rect.top,
    dragged: false
  };
  document.addEventListener('mousemove', onInlineDepTreeFabDragMove);
  document.addEventListener('mouseup', stopInlineDepTreeFabDrag);
  event.preventDefault();
}
export function noteDepTreeExperimentHover(segIdx, reason) {
  if (!isFinite(Number(segIdx)) || Number(segIdx) < 0) return false;
  hoverLayoutState.depTreeExperimentLastHoveredSegIdx = Number(segIdx);
  return syncInlineDepTree(reason || 'hover');
}
export function initializeDependencyState() {
  dependencyState.pagerPointerDown = false;
  dependencyState.pagerScrollPending = false;
  if (hoverLayoutState.sourcePager) {
    hoverLayoutState.sourcePager.addEventListener('mousedown', function (ev) {
      if (ev && ev.button === 0) dependencyState.pagerPointerDown = true;
    });
    hoverLayoutState.sourcePager.addEventListener(
      'touchstart',
      function () {
        dependencyState.pagerPointerDown = true;
      },
      {
        passive: true
      }
    );
  }
  window.addEventListener('mouseup', function () {
    if (!dependencyState.pagerPointerDown) return;
    dependencyState.pagerPointerDown = false;
    if (dependencyState.pagerScrollPending) {
      dependencyState.pagerScrollPending = false;
      handlePagerScrollStop();
    }
  });
  window.addEventListener('touchend', function () {
    if (!dependencyState.pagerPointerDown) return;
    dependencyState.pagerPointerDown = false;
    if (dependencyState.pagerScrollPending) {
      dependencyState.pagerScrollPending = false;
      handlePagerScrollStop();
    }
  });
  if (hoverLayoutState.sourcePager) {
    hoverLayoutState.sourcePager.addEventListener(
      'wheel',
      function (ev) {
        var dy = ev && isFinite(ev.deltaY) ? ev.deltaY : 0;
        if (!dy) return;
        if (isRawContinuousActive()) {
          ev.preventDefault();
          scrollRawContinuousBy(dy);
          return;
        }
        if (documentState.inputMode !== 'doc') return;
        if (isActiveWebSnapshotDocument()) {
          ev.preventDefault();
          scrollWebSnapshotBy(dy);
          return;
        }
        if (isActiveEpubDocument()) {
          ev.preventDefault();
          stepDocumentPage(dy > 0 ? 1 : -1);
          return;
        }
        if (isActiveFoliateFlowDocument()) {
          ev.preventDefault();
          stepDocumentPage(dy > 0 ? 1 : -1);
          return;
        }
        if (isDocxContinuousActive()) {
          ev.preventDefault();
          scrollDocxContinuousBy(dy);
          return;
        }
        var inner = hoverLayoutState.sourcePager.querySelector('.reader-page-inner');
        if (inner && inner.scrollHeight > inner.clientHeight + 1) {
          var atTop = inner.scrollTop <= 0;
          var atBottom = inner.scrollTop + inner.clientHeight >= inner.scrollHeight - 1;
          if ((dy < 0 && !atTop) || (dy > 0 && !atBottom)) return;
        }
        var now = Date.now();
        if (now - documentState.lastDocWheelPageAt < 180) {
          ev.preventDefault();
          return;
        }
        documentState.lastDocWheelPageAt = now;
        ev.preventDefault();
        stepDocumentPage(dy > 0 ? 1 : -1);
      },
      {
        passive: false
      }
    );
    hoverLayoutState.sourcePager.addEventListener('scroll', function () {
      if (documentState.webSnapshotInspectorEnabled && isLocalSourceInspectorAvailable()) {
        drawLocalSourceInspectorSelection();
      }
      if (isRawContinuousActive()) {
        onRawContinuousScroll();
        return;
      }
      if (documentState.inputMode === 'pdf') {
        if (!documentShellState.pdfJsIframe) updateActivePdfPageFromSourceScroll();
        return;
      }
      if (documentState.inputMode !== 'doc') return;
      if (isActiveWebSnapshotDocument()) {
        updateDocumentNavigatorThumb();
        return;
      }
      if (isDocxContinuousActive()) {
        onDocxContinuousScroll();
        return;
      }
      if (dependencyState.pagerPointerDown) dependencyState.pagerScrollPending = true;
      requestMovementLookup();
    });
  }
  dependencyState.rerenderPdfPagesOnResizeDebounced = debounce(function () {
    if (documentState.inputMode !== 'pdf') return;
    if (!documentShellState.pdfJsIframe) {
      if (documentShellState.pdfOriginal.doc) {
        renderAllPdfPages(documentShellState.pdfOriginal.doc);
        scrollPdfJsSourcePageIntoView(documentState.activePageIndex || 0);
      }
      return;
    }
    if (!documentShellState.pdfJsIframe.contentWindow) return;
    try {
      documentShellState.pdfJsIframe.contentWindow.postMessage(
        {
          source: 'reader-parent',
          type: 'pdfjs-parent-resize',
          sessionId: String(documentShellState.pdfJsSessionId)
        },
        window.location.origin
      );
    } catch (e) {
      // ignore
    }
  }, 120);
  window.addEventListener('resize', function () {
    if (documentState.inputMode === 'doc' || documentState.inputMode === 'pdf') {
      applyFixedDocumentViewportHeight(true);
      syncDocumentChrome();
    }
    applyGlobalViewportClamp(false);
    invalidateUdRectCache();
    invalidateUiRectCache();
    if (
      hoverLayoutState.hoverPopupContainer &&
      hoverLayoutState.hoverPopupContainer.style.display === 'flex'
    ) {
      if (segmentRenderingState.panelHoverToken) {
        positionSidePanelPopup(
          hoverLayoutState.hoverPopupContainer,
          segmentRenderingState.lastMouseX,
          segmentRenderingState.lastMouseY
        );
      } else {
        positionPopup(segmentRenderingState.lastMouseX, segmentRenderingState.lastMouseY);
      }
    }
    dependencyState.rerenderPdfPagesOnResizeDebounced();
  });
  applyGlobalViewportClamp(true);

  // ===================== UD DEPENDENCY VISUALIZATION =====================
  dependencyState.udSvgOverlay = null;
  dependencyState.latestUdOverlay = null;
  dependencyState.latestNerSpans = [];
  dependencyState.latestCollapsedSpanInfo = {}; // Map segIdx -> { firstSeg, lastSeg, combinedText, udTok, isFirst }
  dependencyState.latestUdTokenMap = {}; // Map segIdx -> UD token
  dependencyState.latestUdStructure = null; // Cached UD structural maps for chunking
  dependencyState.udTokenIndex = new Map(); // Map from segment index to first token span element
  dependencyState.udTokenFragments = new Map(); // Map from segment index to ALL token span fragments
  dependencyState.udMwtPartAnchors = new Map();
  try {
    window.DepTreeExperimentBridge = {
      open: openInlineDepTreeTool,
      sync: function () {
        return syncInlineDepTree('manual');
      },
      getCurrentSentence: function () {
        return buildDepTreeExperimentSentencePayload(hoverLayoutState.depTreeExperimentLastHoveredSegIdx);
      },
      getSentenceForSeg: function (segIdx) {
        return buildDepTreeExperimentSentencePayload(segIdx);
      }
    };
    window.openLegacyDepTreeTool = openInlineDepTreeTool;
    window.openDepTreeViewTestApp = openInlineDepTreeTool;
  } catch (_e) {}
  return true;
}
