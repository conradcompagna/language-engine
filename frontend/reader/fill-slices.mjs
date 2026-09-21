import { dependencyState } from './dependency-state.state.mjs';
import {
  getVisibleRawTextareaLookupText,
  setRawTextFoliateDocument,
  updateRenderedOutputBackground
} from './document-import.mjs';
import {
  cancelWebSnapshotVisibleCanonicalRefresh,
  drawLocalSourceInspectorSelection,
  isDocxContinuousActive,
  isLocalSourceInspectorAvailable,
  isTopSourceInspectorAvailable,
  lookupCurrentFoliateEpubPage,
  lookupCurrentFoliateFlowPage
} from './document-navigation.mjs';
import {
  isRawContinuousActive,
  rawTextContentExceedsViewport,
  syncRawContinuousModeForSourceText
} from './document-search.mjs';
import {
  cancelMovementLookupTimer,
  isAbortError,
  lookupCurrentCanonicalPage,
  lookupCurrentPdfCanonicalPage,
  normalizeDocumentText,
  setCanonicalDocument
} from './document-state.mjs';
import { documentState } from './document-state.state.mjs';
import { pushLookupResolverPayload } from './entry-editing.mjs';
import { buildExactDictFillSlicesForToken } from './fill-rendering.mjs';
import { fillSlicesState } from './fill-slices.state.mjs';
import {
  getActiveWebSnapshotState,
  isActiveEpubDocument,
  isActiveFoliateFlowDocument,
  isActiveWebSnapshotDocument
} from './foliate-viewport.mjs';
import { uposColorForTag } from './gloss-requests.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import {
  _resetSentenceTabletGlossOverrides,
  isShowingInitialInputGuidance,
  reportLookupProgress,
  startSegmentLookupFetch
} from './lookup-progress.mjs';
import { lookupProgressState } from './lookup-progress.state.mjs';
import {
  buildLookupUrl,
  clearLookupOutputForMissingLanguage,
  getSelectedDictSource,
  hasSelectedLanguage
} from './orthography.mjs';
import { escapeHtml, getEntryDisplayHead, stripZeroWidthJoiners } from './presentation.mjs';
import { renderSegments } from './segment-rendering.mjs';
import { getVisibleDocxSliceText } from './text-offsets.mjs';
import { getNerLabelForSeg, nerLabelToUpos } from './token-fragments.mjs';
export function lookupCurrentDocumentPage() {
  if (documentState.canonicalDoc) {
    var lookupResult = lookupCurrentCanonicalPage();
    if (lookupResult) return lookupResult;
  }
  console.error('Canonical document is missing; refusing legacy document DOM decoration path.');
  if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Document renderer unavailable.';
  if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
  if (hoverLayoutState.renderedText) {
    hoverLayoutState.renderedText.innerHTML =
      '<div class="reader-output-placeholder">Could not build the canonical lookup document for this page.</div>';
  }
  return true;
}
export function getWebSnapshotInspectorLookupText() {
  var state = getActiveWebSnapshotState();
  var text = '';
  if (
    isActiveWebSnapshotDocument() &&
    state &&
    window.DocRenderWebSnapshotRenderer &&
    window.DocRenderWebSnapshotRenderer.getSelectedText
  ) {
    text = window.DocRenderWebSnapshotRenderer.getSelectedText(state);
  } else if (isLocalSourceInspectorAvailable()) {
    drawLocalSourceInspectorSelection();
    text = documentState.webSnapshotSelectedText || '';
  }
  if (!text) text = documentState.webSnapshotSelectedText || '';
  var normalized = normalizeDocumentText(text).replace(/\u00a0/g, ' ');
  if (documentState.inputMode === 'pdf') {
    normalized = normalized
      .replace(/\n{2,}/g, '\x00')
      .replace(/\n/g, ' ')
      .replace(/\x00/g, '\n\n');
  }
  return normalized.trim();
}
export function getWebSnapshotVisibleSliceText() {
  var state = getActiveWebSnapshotState();
  var text = '';
  if (
    isActiveWebSnapshotDocument() &&
    state &&
    window.DocRenderWebSnapshotRenderer &&
    window.DocRenderWebSnapshotRenderer.extractVisibleText
  ) {
    text = window.DocRenderWebSnapshotRenderer.extractVisibleText(state, {
      margin: 8
    });
  }
  return normalizeDocumentText(text || '')
    .replace(/\u00a0/g, ' ')
    .trim();
}
export function lookupPlainTextToBottom(rawText, opts) {
  opts = opts || {};
  var text = normalizeDocumentText(rawText || '')
    .replace(/\u00a0/g, ' ')
    .trim();
  if (!text) {
    if (hoverLayoutState.statusText)
      hoverLayoutState.statusText.textContent = opts.emptyStatus || 'Select text to look up.';
    if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
    if (hoverLayoutState.renderedText) {
      hoverLayoutState.renderedText.innerHTML =
        '<div class="reader-output-placeholder">Select text in the source pane, then press Look Up.</div>';
    }
    return Promise.resolve(true);
  }
  var seq = ++hoverLayoutState.latestSeq;
  if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Segmenting...';
  if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
  documentState.pageLookupTextByIndex[documentState.activePageIndex || 0] = text;
  documentState.lastLookupPageIndex = documentState.activePageIndex || 0;
  return startSegmentLookupFetch(buildLookupUrl(text))
    .then(function (resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.json();
    })
    .then(function (data) {
      if (seq !== hoverLayoutState.latestSeq) return;
      if (!data || !data.ok) {
        if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Error from server.';
        if (hoverLayoutState.renderedText)
          hoverLayoutState.renderedText.innerHTML =
            '<div class="reader-output-placeholder">Error: ' +
            escapeHtml(data && data.error ? data.error : 'unknown') +
            '</div>';
        return;
      }
      hoverLayoutState.latestData = data;
      try {
        _resetSentenceTabletGlossOverrides();
      } catch (e) {}
      try {
        pushLookupResolverPayload(data);
      } catch (e2) {}
      reportLookupProgress('Rendering results');
      renderSegments(data, text);
      updateRenderedOutputBackground();
    })
    .catch(function (err) {
      if (seq !== hoverLayoutState.latestSeq) return;
      if (isAbortError(err)) return;
      console.error(err);
      if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Request failed.';
      if (hoverLayoutState.renderedText)
        hoverLayoutState.renderedText.innerHTML =
          '<div class="reader-output-placeholder">Could not contact /lookup endpoint.</div>';
      updateRenderedOutputBackground();
    });
}
export function lookupCurrentWebSnapshotVisibleCanonical() {
  cancelWebSnapshotVisibleCanonicalRefresh();
  var state = getActiveWebSnapshotState();
  var doc = null;
  if (
    isActiveWebSnapshotDocument() &&
    state &&
    window.DocRenderWebSnapshotRenderer &&
    window.DocRenderWebSnapshotRenderer.extractVisibleCanonicalDocument
  ) {
    doc = window.DocRenderWebSnapshotRenderer.extractVisibleCanonicalDocument(state, {
      margin: 8
    });
  }
  if (doc && doc.pages && doc.pages[0] && String(doc.pages[0].text || '').trim()) {
    setCanonicalDocument(doc, {
      pageIndex: 0,
      clearCache: true
    });
    return lookupCurrentCanonicalPage();
  }
  return lookupPlainTextToBottom(getWebSnapshotVisibleSliceText(), {
    emptyStatus: 'No visible web text in this viewport.'
  });
}
export function lookupCurrentWebSnapshotSelection() {
  if (!documentState.webSnapshotInspectorEnabled) {
    return lookupCurrentWebSnapshotVisibleCanonical();
  }
  return lookupPlainTextToBottom(getWebSnapshotInspectorLookupText(), {
    emptyStatus: 'Select source text.'
  });
}
export function lookupCurrentDocxVisibleSlice() {
  var sliceInfo = getVisibleDocxSliceText(hoverLayoutState.sourcePager);
  var text = sliceInfo && sliceInfo.text ? sliceInfo.text : '';
  return lookupPlainTextToBottom(text, {
    emptyStatus: 'No visible text in the DOCX viewport.'
  });
}
export function triggerUpdate() {
  cancelMovementLookupTimer();
  // ---- Language Engine: gate behind lookup button ----
  if (typeof window.__LE_LOOKUP_ALLOWED !== 'undefined' && !window.__LE_LOOKUP_ALLOWED) {
    return Promise.resolve(false); // blocked until user clicks "Look Up"
  }
  // Reset gate after allowing one lookup through
  if (typeof window.__LE_LOOKUP_ALLOWED !== 'undefined') {
    window.__LE_LOOKUP_ALLOWED = false;
  }
  // ---- end gate ----
  if (!hasSelectedLanguage()) {
    clearLookupOutputForMissingLanguage();
    return Promise.resolve(false);
  }
  if (!getSelectedDictSource()) {
    if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Select a dictionary.';
    return Promise.resolve(false);
  }
  // PDF.js source viewer stays in the top pane; the bottom pane uses the canonical textual skeleton.
  if (documentState.inputMode === 'pdf') {
    if (documentState.webSnapshotInspectorEnabled && isTopSourceInspectorAvailable()) {
      return lookupCurrentWebSnapshotSelection();
    }
    var idx = Math.max(
      0,
      Math.min((documentState.docPages.length || 1) - 1, documentState.activePageIndex || 0)
    );
    return lookupCurrentPdfCanonicalPage(idx);
  }

  // Document mode - use visible text from scrollable container
  if (documentState.inputMode === 'doc') {
    if (
      isActiveWebSnapshotDocument() ||
      (documentState.webSnapshotInspectorEnabled && isTopSourceInspectorAvailable())
    ) {
      return lookupCurrentWebSnapshotSelection();
    }
    if (isActiveEpubDocument() && !isActiveFoliateFlowDocument()) {
      return lookupCurrentFoliateEpubPage();
    }
    if (isActiveFoliateFlowDocument()) {
      return lookupCurrentFoliateFlowPage();
    }
    if (isDocxContinuousActive()) {
      return lookupCurrentDocxVisibleSlice();
    }
    return lookupCurrentDocumentPage();
  }

  // Raw mode - use textarea content
  if (isShowingInitialInputGuidance()) {
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
    return Promise.resolve(true);
  }
  if (
    syncRawContinuousModeForSourceText({
      triggerLookup: true
    })
  ) {
    return Promise.resolve(true);
  }
  var fullText = hoverLayoutState.sourceText.value || '';
  var trimmed = fullText.trim();
  if (!trimmed) {
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
    return Promise.resolve(true);
  }
  if (
    !isRawContinuousActive() &&
    (fullText.length > documentState.WINDOWED_MAX_CHARS || rawTextContentExceedsViewport())
  ) {
    setRawTextFoliateDocument(fullText, {
      readOnly: !!(documentState.currentFile && documentState.currentFileType === 'text'),
      preserveCurrentFile: !!documentState.currentFile,
      fileType: documentState.currentFileType || 'text',
      triggerLookup: true
    });
    return Promise.resolve(true);
  }
  if (isRawContinuousActive()) {
    if (documentState.webSnapshotInspectorEnabled && isTopSourceInspectorAvailable()) {
      return lookupCurrentWebSnapshotSelection();
    }
    var visibleRawText = getVisibleRawTextareaLookupText();
    return lookupPlainTextToBottom(visibleRawText, {
      emptyStatus: 'No visible text in the input viewport.'
    });
  }

  // Small text - segment directly
  var seq = ++hoverLayoutState.latestSeq;
  hoverLayoutState.statusText.textContent = 'Segmenting...';
  hoverLayoutState.statusCounts.textContent = '';
  return startSegmentLookupFetch(buildLookupUrl(trimmed))
    .then(function (resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.json();
    })
    .then(function (data) {
      if (seq !== hoverLayoutState.latestSeq) return;
      if (!data || !data.ok) {
        hoverLayoutState.statusText.textContent = 'Error from server.';
        hoverLayoutState.renderedText.innerHTML =
          '<div class="reader-output-placeholder">Error: ' +
          escapeHtml(data && data.error ? data.error : 'unknown') +
          '</div>';
        return;
      }
      hoverLayoutState.latestData = data;
      _resetSentenceTabletGlossOverrides();
      pushLookupResolverPayload(data);
      reportLookupProgress('Rendering results');
      renderSegments(data, fullText);
      updateRenderedOutputBackground();
    })
    .catch(function (err) {
      if (seq !== hoverLayoutState.latestSeq) return;
      if (isAbortError(err)) return;
      console.error(err);
      hoverLayoutState.statusText.textContent = 'Request failed.';
      hoverLayoutState.renderedText.innerHTML =
        '<div class="reader-output-placeholder">Could not contact /lookup endpoint.</div>';
      updateRenderedOutputBackground();
    });
}
export function buildDictIndex(results) {
  var map = new Map();
  if (!Array.isArray(results)) return map;
  for (var ri = 0; ri < results.length; ri++) {
    var res = results[ri];
    if (!res) continue;
    var head = getEntryDisplayHead(res, '');
    if (head && !map.has(head)) map.set(head, []);
    if (head) map.get(head).push(res);
  }
  return map;
}
export function resolveSegmentPosData(segIdx, res, udTok) {
  var collapsedInfo =
    dependencyState.latestCollapsedSpanInfo && dependencyState.latestCollapsedSpanInfo[segIdx]
      ? dependencyState.latestCollapsedSpanInfo[segIdx]
      : null;
  var resolvedUdTok = udTok;
  if (!resolvedUdTok && collapsedInfo && collapsedInfo.udTok) {
    resolvedUdTok = collapsedInfo.udTok;
  }
  var upos = resolvedUdTok && resolvedUdTok.upos ? resolvedUdTok.upos : res && res.upos ? res.upos : '';
  var uposLabel =
    resolvedUdTok && resolvedUdTok.upos
      ? resolvedUdTok.upos
      : res && res.upos_label
        ? res.upos_label
        : res && res.upos
          ? res.upos
          : '';
  var uposColor =
    resolvedUdTok && resolvedUdTok.upos
      ? uposColorForTag(resolvedUdTok.upos)
      : res && res.upos_color
        ? res.upos_color
        : '';
  var dep = resolvedUdTok && resolvedUdTok.dep ? resolvedUdTok.dep : res && res.dep ? res.dep : '';
  var depLabel =
    resolvedUdTok && resolvedUdTok.dep
      ? resolvedUdTok.dep
      : res && res.dep_label
        ? res.dep_label
        : res && res.dep
          ? res.dep
          : '';
  var tag =
    resolvedUdTok && (resolvedUdTok.tag || resolvedUdTok.xpos)
      ? resolvedUdTok.tag || resolvedUdTok.xpos
      : res && (res.tag || res.xpos)
        ? res.tag || res.xpos
        : '';
  var lemma = resolvedUdTok && resolvedUdTok.lemma ? resolvedUdTok.lemma : res && res.lemma ? res.lemma : '';
  var lemmaRaw =
    resolvedUdTok && resolvedUdTok.lemma_raw
      ? resolvedUdTok.lemma_raw
      : res && res.lemma_raw
        ? res.lemma_raw
        : lemma;
  var lemmaSuffix =
    resolvedUdTok && resolvedUdTok.lemma_suffix
      ? resolvedUdTok.lemma_suffix
      : res && res.lemma_suffix
        ? res.lemma_suffix
        : '';
  var feats = resolvedUdTok && resolvedUdTok.feats ? resolvedUdTok.feats : res && res.feats ? res.feats : '';
  var conjugation = res && res.conjugation ? res.conjugation : null;
  if (collapsedInfo && collapsedInfo.isFirst === false) {
    var spanNerLabel = getNerLabelForSeg(segIdx);
    var spanNerPos = nerLabelToUpos(spanNerLabel);
    if (spanNerPos) {
      upos = spanNerPos;
      uposLabel = spanNerPos;
      uposColor = uposColorForTag(spanNerPos);
    }
  } else if (!upos || String(upos).toUpperCase() === 'DEFAULT') {
    var nerLabel = getNerLabelForSeg(segIdx);
    var nerPos = nerLabelToUpos(nerLabel);
    if (nerPos) {
      upos = nerPos;
      uposLabel = nerPos;
      uposColor = uposColorForTag(nerPos);
    }
  }
  return {
    upos: upos,
    upos_label: uposLabel,
    upos_color: uposColor,
    dep: dep,
    dep_label: depLabel,
    tag: tag,
    xpos: tag,
    lemma: lemma,
    lemma_raw: lemmaRaw,
    lemma_suffix: lemmaSuffix,
    feats: feats,
    conjugation: conjugation
  };
}
export function getDictFillSurfaceText(fillEntry) {
  if (!fillEntry || typeof fillEntry !== 'object') return '';
  if (fillEntry.text != null) return String(fillEntry.text);
  if (fillEntry.head != null) return String(fillEntry.head);
  return '';
}
export function isCombiningMarkChar(ch) {
  var text = String(ch || '');
  if (!text) return false;
  var cp = text.codePointAt(0);
  return (
    (cp >= 0x0300 && cp <= 0x036f) ||
    (cp >= 0x1ab0 && cp <= 0x1aff) ||
    (cp >= 0x1dc0 && cp <= 0x1dff) ||
    (cp >= 0x20d0 && cp <= 0x20ff) ||
    (cp >= 0xfe20 && cp <= 0xfe2f) ||
    (cp >= 0xfe00 && cp <= 0xfe0f)
  );
}
export function isMarkOnlySliceText(text) {
  var value = String(text || '');
  if (!value) return false;
  if (fillSlicesState.combiningMarkOnlyRe) return fillSlicesState.combiningMarkOnlyRe.test(value);
  var chars = Array.from(value);
  if (!chars.length) return false;
  for (var i = 0; i < chars.length; i++) {
    if (chars[i] !== '\u200C' && chars[i] !== '\u200D' && !isCombiningMarkChar(chars[i])) return false;
  }
  return true;
}
export function appendUniqueFillIndexes(target, source) {
  var out = Array.isArray(target) ? target : [];
  var seen = Object.create(null);
  for (var i = 0; i < out.length; i++) seen[out[i]] = true;
  var src = Array.isArray(source) ? source : [];
  for (var j = 0; j < src.length; j++) {
    var idx = src[j];
    if (seen[idx]) continue;
    seen[idx] = true;
    out.push(idx);
  }
  return out;
}
export function coalesceMarkOnlyFillSlices(seg, slices) {
  if (!seg || !Array.isArray(slices) || slices.length < 2) return slices;
  var out = [];
  var pendingLeading = null;
  for (var i = 0; i < slices.length; i++) {
    var slice = slices[i] || {};
    var current = {
      start: parseInt(slice.start, 10) || 0,
      end: parseInt(slice.end, 10) || 0,
      fillIndexes: Array.isArray(slice.fillIndexes) ? slice.fillIndexes.slice() : []
    };
    var sliceText = seg.slice(current.start, current.end);
    if (isMarkOnlySliceText(sliceText)) {
      if (out.length) {
        out[out.length - 1].end = current.end;
        appendUniqueFillIndexes(out[out.length - 1].fillIndexes, current.fillIndexes);
      } else if (pendingLeading) {
        pendingLeading.end = current.end;
        appendUniqueFillIndexes(pendingLeading.fillIndexes, current.fillIndexes);
      } else {
        pendingLeading = current;
      }
      continue;
    }
    if (pendingLeading) {
      current.start = pendingLeading.start;
      current.fillIndexes = appendUniqueFillIndexes(pendingLeading.fillIndexes.slice(), current.fillIndexes);
      pendingLeading = null;
    }
    out.push(current);
  }
  if (pendingLeading) {
    if (out.length) {
      out[out.length - 1].end = pendingLeading.end;
      appendUniqueFillIndexes(out[out.length - 1].fillIndexes, pendingLeading.fillIndexes);
    } else {
      out.push(pendingLeading);
    }
  }
  return out;
}
export function buildSequentialDictFillSlices(seg, surfaces) {
  if (!seg || !Array.isArray(surfaces) || surfaces.length < 2) return null;
  var slices = [];
  var cursor = 0;
  for (var i = 0; i < surfaces.length; i++) {
    var surface = String(surfaces[i] || '');
    if (!surface) return null;
    var start = seg.indexOf(surface, cursor);
    if (start < 0) return null;
    var end = start + surface.length;
    if (end <= start) return null;
    slices.push({
      fillIndex: i,
      start: start,
      end: end
    });
    cursor = end;
  }
  return slices.length > 1 ? slices : null;
}
export function buildProjectedDictFillSlices(seg, surfaces) {
  if (!seg || !Array.isArray(surfaces) || surfaces.length < 2) return null;
  if (seg.length < surfaces.length) return null;
  var weights = [];
  var totalWeight = 0;
  for (var i = 0; i < surfaces.length; i++) {
    var s = String(surfaces[i] || '');
    var w = s.length;
    if (!(w > 0)) w = 1;
    weights.push(w);
    totalWeight += w;
  }
  if (!(totalWeight > 0)) return null;
  var slices = [];
  var cursor = 0;
  var remainingChars = seg.length;
  var remainingWeight = totalWeight;
  for (var pi = 0; pi < surfaces.length; pi++) {
    var start = cursor;
    var take = 0;
    var remainingBuckets = surfaces.length - pi;
    if (pi === surfaces.length - 1) {
      take = remainingChars;
    } else {
      var expected = Math.round((weights[pi] / remainingWeight) * remainingChars);
      var minTake = 1;
      var maxTake = remainingChars - (remainingBuckets - 1);
      if (maxTake < 1) return null;
      if (!isFinite(expected)) expected = minTake;
      take = expected;
      if (take < minTake) take = minTake;
      if (take > maxTake) take = maxTake;
    }
    var end = start + take;
    if (end <= start) return null;
    slices.push({
      fillIndex: pi,
      start: start,
      end: end
    });
    cursor = end;
    remainingChars = seg.length - cursor;
    remainingWeight -= weights[pi];
    if (remainingWeight < 1) remainingWeight = 1;
  }
  if (cursor !== seg.length) return null;
  return slices.length > 1 ? slices : null;
}
export function buildForcedProjectedDictFillSlices(seg, dictFill) {
  var token = String(seg || '');
  if (!token || !Array.isArray(dictFill) || dictFill.length < 2) return null;
  var segLen = token.length;
  if (segLen < 1) return null;
  var nonMarkFillIndexes = [];
  var nonMarkSurfaces = [];
  var markOnlyFillIndexes = [];
  for (var i = 0; i < dictFill.length; i++) {
    var rawText = getDictFillSurfaceText(dictFill[i]);
    if (isMarkOnlySliceText(rawText)) {
      markOnlyFillIndexes.push(i);
    } else {
      nonMarkFillIndexes.push(i);
      nonMarkSurfaces.push(String(rawText || 'x'));
    }
  }
  if (!nonMarkFillIndexes.length) {
    return [
      {
        start: 0,
        end: segLen,
        fillIndexes: dictFill.map(function (_entry, idx) {
          return idx;
        })
      }
    ];
  }
  var rawSlices = null;
  if (segLen >= nonMarkFillIndexes.length) {
    rawSlices = buildProjectedDictFillSlices(token, nonMarkSurfaces);
  }
  if (!rawSlices || !rawSlices.length) {
    rawSlices = [];
    for (var ri = 0; ri < nonMarkFillIndexes.length; ri++) {
      var start = Math.floor((ri * segLen) / nonMarkFillIndexes.length);
      if (start >= segLen) start = segLen - 1;
      if (start < 0) start = 0;
      var end = Math.floor(((ri + 1) * segLen) / nonMarkFillIndexes.length);
      if (end <= start) end = Math.min(segLen, start + 1);
      if (end <= start) end = segLen;
      rawSlices.push({
        start: start,
        end: end,
        fillIndex: ri
      });
    }
  }
  var out = [];
  for (var si = 0; si < rawSlices.length; si++) {
    var rawSlice = rawSlices[si] || {};
    var ordinal = parseInt(rawSlice.fillIndex, 10);
    if (!isFinite(ordinal)) ordinal = si;
    var actualFillIndex = nonMarkFillIndexes[ordinal];
    if (!isFinite(actualFillIndex)) continue;
    var sliceStart = Number(rawSlice.start || 0);
    var sliceEnd = Number(rawSlice.end || 0);
    if (sliceStart < 0) sliceStart = 0;
    if (sliceEnd > segLen) sliceEnd = segLen;
    if (sliceEnd <= sliceStart) sliceEnd = Math.min(segLen, sliceStart + 1);
    if (sliceEnd <= sliceStart) {
      sliceStart = Math.max(0, segLen - 1);
      sliceEnd = segLen;
    }
    out.push({
      start: sliceStart,
      end: sliceEnd,
      fillIndexes: [actualFillIndex]
    });
  }
  for (var mi = 0; mi < markOnlyFillIndexes.length; mi++) {
    var markFillIndex = markOnlyFillIndexes[mi];
    var attachAt = 0;
    for (var oi = 0; oi < out.length; oi++) {
      var existingFillIndex = out[oi].fillIndexes[0];
      if (existingFillIndex <= markFillIndex) attachAt = oi;
      else break;
    }
    appendUniqueFillIndexes(out[attachAt].fillIndexes, [markFillIndex]);
  }
  return out.length ? out : null;
}
export function collectDictFillSurfaces(entries) {
  if (!Array.isArray(entries) || !entries.length) return null;
  var out = [];
  for (var i = 0; i < entries.length; i++) {
    var surface = getDictFillSurfaceText(entries[i]);
    if (!surface) return null;
    out.push(surface);
  }
  return out.length ? out : null;
}
export function parseFillHitIndexes(fillHit, fillCount) {
  var max = parseInt(fillCount, 10);
  var out = [];
  var seen = Object.create(null);
  if (!fillHit || !fillHit.dataset) return out;
  var rawList = String(fillHit.dataset.fillIndexes || '').trim();
  if (!rawList && fillHit.dataset.fillIndex != null) rawList = String(fillHit.dataset.fillIndex);
  if (!rawList) return out;
  var parts = rawList.split(',');
  for (var i = 0; i < parts.length; i++) {
    var idx = parseInt(String(parts[i] || '').trim(), 10);
    if (!isFinite(idx) || idx < 0 || seen[idx]) continue;
    if (isFinite(max) && max >= 0 && idx >= max) continue;
    seen[idx] = true;
    out.push(idx);
  }
  return out;
}
export function buildDictFillSlicesForToken(seg, dictFill, providedSlices, options) {
  var opts = options || {};
  if (!seg || !Array.isArray(dictFill) || dictFill.length < 2) return null;
  if (Array.isArray(providedSlices) && providedSlices.length) {
    // Exact pipeline slices are authoritative. Do not re-bucket them in the
    // renderer by width or fill count.
    return buildExactDictFillSlicesForToken(seg, dictFill, providedSlices);
  }
  var segLen = seg.length;
  if (segLen < 1) return null;
  var hintWidthByFill = Object.create(null);
  var rawSlices = Array.isArray(providedSlices) ? providedSlices : [];
  for (var hi = 0; hi < rawSlices.length; hi++) {
    var raw = rawSlices[hi] || {};
    var start = parseInt(raw.start, 10);
    var end = parseInt(raw.end, 10);
    if (!isFinite(start) || !isFinite(end) || end <= start) continue;
    if (start < 0) start = 0;
    if (end > segLen) end = segLen;
    if (end <= start) continue;
    var width = end - start;
    var indexes = parseFillHitIndexes(
      {
        dataset: {
          fillIndexes: Array.isArray(raw.fill_indexes)
            ? raw.fill_indexes.join(',')
            : String(raw.fill_indexes || '')
        }
      },
      dictFill.length
    );
    if (!indexes.length && raw.fill_index != null) {
      indexes = parseFillHitIndexes(
        {
          dataset: {
            fillIndex: String(raw.fill_index)
          }
        },
        dictFill.length
      );
    }
    for (var ii = 0; ii < indexes.length; ii++) {
      var idx = indexes[ii];
      if (!(width > 0)) continue;
      if (!(hintWidthByFill[idx] > 0) || width > hintWidthByFill[idx]) {
        hintWidthByFill[idx] = width;
      }
    }
  }
  var nonMark = [];
  var markOnlyFillIndexes = [];
  for (var i = 0; i < dictFill.length; i++) {
    var fillSurface = getDictFillSurfaceText(dictFill[i]);
    if (isMarkOnlySliceText(fillSurface)) {
      markOnlyFillIndexes.push(i);
      continue;
    }
    var weight = Number(hintWidthByFill[i] || 0);
    if (!(weight > 0)) {
      var visibleSurface = stripZeroWidthJoiners(fillSurface);
      weight = String(visibleSurface || fillSurface || '').length;
    }
    if (!(weight > 0)) weight = 1;
    nonMark.push({
      fillIndex: i,
      weight: weight
    });
  }
  if (!nonMark.length) {
    return [
      {
        start: 0,
        end: segLen,
        fillIndexes: dictFill.map(function (_entry, idx) {
          return idx;
        })
      }
    ];
  }
  var slices = [];
  if (segLen >= nonMark.length) {
    var cursor = 0;
    var remainingChars = segLen;
    var remainingWeight = 0;
    for (var wi = 0; wi < nonMark.length; wi++) remainingWeight += nonMark[wi].weight;
    for (var ni = 0; ni < nonMark.length; ni++) {
      var start = cursor;
      var take = 0;
      var remainingBuckets = nonMark.length - ni;
      if (ni === nonMark.length - 1) {
        take = remainingChars;
      } else {
        var expected = Math.round((nonMark[ni].weight / remainingWeight) * remainingChars);
        var minTake = 1;
        var maxTake = remainingChars - (remainingBuckets - 1);
        if (!isFinite(expected)) expected = minTake;
        take = expected;
        if (take < minTake) take = minTake;
        if (take > maxTake) take = maxTake;
      }
      var end = start + take;
      if (end <= start) end = Math.min(segLen, start + 1);
      if (end <= start) end = segLen;
      slices.push({
        start: start,
        end: end,
        fillIndexes: [nonMark[ni].fillIndex]
      });
      cursor = end;
      remainingChars = segLen - cursor;
      remainingWeight -= nonMark[ni].weight;
      if (remainingWeight < 1) remainingWeight = 1;
    }
  } else {
    for (var pi = 0; pi < nonMark.length; pi++) {
      var pStart = Math.floor((pi * segLen) / nonMark.length);
      if (pStart >= segLen) pStart = segLen - 1;
      if (pStart < 0) pStart = 0;
      var pEnd = Math.floor(((pi + 1) * segLen) / nonMark.length);
      if (pEnd <= pStart) pEnd = Math.min(segLen, pStart + 1);
      if (pEnd <= pStart) pEnd = segLen;
      slices.push({
        start: pStart,
        end: pEnd,
        fillIndexes: [nonMark[pi].fillIndex]
      });
    }
  }
  for (var mi = 0; mi < markOnlyFillIndexes.length; mi++) {
    var markFillIndex = markOnlyFillIndexes[mi];
    var attachAt = 0;
    for (var si = 0; si < slices.length; si++) {
      var existingFillIndex = slices[si].fillIndexes[0];
      if (existingFillIndex <= markFillIndex) attachAt = si;
      else break;
    }
    appendUniqueFillIndexes(slices[attachAt].fillIndexes, [markFillIndex]);
  }
  if (opts.coalesceMarkOnly === true) {
    return slices.length ? slices : null;
  }
  return slices.length ? slices : null;
}
export function initializeFillSlices() {
  fillSlicesState.combiningMarkOnlyRe = (function () {
    try {
      return new RegExp('^[\\p{M}\\u200C\\u200D\\uFE00-\\uFE0F]+$', 'u');
    } catch (_e) {
      return null;
    }
  })();
  return true;
}
