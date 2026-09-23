import { dependencyState } from './dependency-state.state.mjs';
import {
  appendPdfPageHeader,
  applyPdfPageShellSize,
  getPdfTargetPageSize,
  needsDottedCircle,
  sanitizePdfDimension
} from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { documentState } from './document-state.state.mjs';
import { buildTokenSpan } from './fill-rendering.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { registerTokenSpan } from './token-fragments.mjs';
export function getPdfPageDimensionsFor(pageNum, fallbackWidth, fallbackHeight) {
  var idx = Math.max(0, (pageNum | 0) - 1);
  var dim = sanitizePdfDimension(documentShellState.pdfPageDimensions[idx]);
  if (dim) return dim;
  dim = sanitizePdfDimension(documentShellState.pdfAveragePageDimensions);
  if (dim) return dim;
  dim = sanitizePdfDimension({
    width: fallbackWidth,
    height: fallbackHeight
  });
  if (dim) return dim;
  return {
    width: 1,
    height: 1
  };
}
export function resizePagerToFitPdfPage() {
  if (!hoverLayoutState.sourcePager || documentState.inputMode !== 'pdf') return;
  var pageSize = getPdfTargetPageSize((documentState.activePageIndex || 0) + 1);
  documentState.docViewportHeightPx = pageSize.height;
  hoverLayoutState.sourcePager.style.height = pageSize.height + 'px';
  hoverLayoutState.sourcePager.style.maxHeight = pageSize.height + 'px';
  if (hoverLayoutState.docViewportWrap) {
    hoverLayoutState.docViewportWrap.style.minHeight = pageSize.height + 'px';
  }
}
export function renderSinglePdfPage(pdfDoc, pageNum, pageDiv) {
  pdfDoc.getPage(pageNum).then(function (page) {
    var baseViewport = page.getViewport({
      scale: 1.0
    });
    var pageSize = getPdfTargetPageSize(pageNum);
    applyPdfPageShellSize(pageDiv, pageSize);
    var pageRect = pageDiv.getBoundingClientRect();
    var targetW = Math.max(1, Math.floor(pageRect.width || pageSize.width));
    var targetH = Math.max(1, Math.floor(pageRect.height || pageSize.height));
    var inputDim = getPdfPageDimensionsFor(pageNum, baseViewport.width, baseViewport.height);
    var fitRatio = Math.min(targetW / Math.max(1, inputDim.width), targetH / Math.max(1, inputDim.height));
    if (!isFinite(fitRatio) || fitRatio <= 0) {
      fitRatio = Math.min(
        targetW / Math.max(1, baseViewport.width),
        targetH / Math.max(1, baseViewport.height)
      );
    }
    if (!isFinite(fitRatio) || fitRatio <= 0) fitRatio = 1.0;
    var desiredW = Math.max(1, Math.round(inputDim.width * fitRatio));
    var desiredH = Math.max(1, Math.round(inputDim.height * fitRatio));
    var scaleW = desiredW / Math.max(1, baseViewport.width);
    var scaleH = desiredH / Math.max(1, baseViewport.height);
    var renderScale = scaleW;
    if (!isFinite(renderScale) || renderScale <= 0) renderScale = scaleH;
    if (!isFinite(renderScale) || renderScale <= 0) renderScale = fitRatio;
    if (!isFinite(renderScale) || renderScale <= 0) renderScale = 1.0;
    var scaledViewport = page.getViewport({
      scale: renderScale
    });
    var renderW = Math.max(1, Math.floor(scaledViewport.width));
    var renderH = Math.max(1, Math.floor(scaledViewport.height));
    var offsetX = Math.max(0, Math.floor((targetW - renderW) / 2));
    var offsetY = Math.max(0, Math.floor((targetH - renderH) / 2));
    pageDiv.innerHTML = '';
    pageDiv.style.background = '';
    pageDiv.style.position = 'relative';
    applyPdfPageShellSize(pageDiv, pageSize);
    var numPages = pdfDoc.numPages;
    appendPdfPageHeader(pageDiv, pageNum, numPages);
    var canvas = document.createElement('canvas');
    canvas.className = 'pdfjs-page-canvas';
    canvas.width = renderW;
    canvas.height = renderH;
    canvas.style.position = 'absolute';
    canvas.style.left = offsetX + 'px';
    canvas.style.top = offsetY + 'px';
    canvas.style.width = renderW + 'px';
    canvas.style.height = renderH + 'px';
    pageDiv.appendChild(canvas);
    var ctx = canvas.getContext('2d');
    page
      .render({
        canvasContext: ctx,
        viewport: scaledViewport
      })
      .promise.then(function () {
        return page.getTextContent();
      })
      .then(function (textContent) {
        if (window.pdfjsLib && window.pdfjsLib.renderTextLayer) {
          var textLayer = document.createElement('div');
          textLayer.className = 'textLayer';
          textLayer.style.position = 'absolute';
          textLayer.style.left = offsetX + 'px';
          textLayer.style.top = offsetY + 'px';
          textLayer.style.right = 'auto';
          textLayer.style.bottom = 'auto';
          textLayer.style.width = renderW + 'px';
          textLayer.style.height = renderH + 'px';
          pageDiv.appendChild(textLayer);
          window.pdfjsLib.renderTextLayer({
            textContent: textContent,
            container: textLayer,
            viewport: scaledViewport,
            textDivs: []
          });
        }
      })
      .catch(function (err) {
        console.error('PDF.js page render error:', err);
      });
  });
}
export function fetchPageLayoutText(pageIdx) {
  console.warn('Server PDF page extraction is disabled; PDF text is built client-side from PDF.js.', pageIdx);
}
export function fetchPdfPageRawText(pageIdx) {
  console.warn(
    'Server PDF raw-text extraction is disabled; PDF text is built client-side from PDF.js.',
    pageIdx
  );
}
export function fetchPdfjsTextLayer(pageIdx) {
  if (!documentShellState.pdfJsIframe || !documentShellState.pdfJsIframe.contentWindow) return;
  documentShellState.pdfJsIframe.contentWindow.postMessage(
    {
      source: 'reader-parent',
      type: 'pdfjs-get-text-layer',
      sessionId: String(documentShellState.pdfJsSessionId),
      pageNumber: pageIdx + 1
    },
    window.location.origin
  );
}
export function renderDocxPreviewInto(containerEl, arrayBuffer) {
  if (!containerEl) return Promise.resolve();
  containerEl.innerHTML = '';
  var wrap = document.createElement('div');
  wrap.className = 'docx-preview-host';
  containerEl.appendChild(wrap);
  return window.docx.renderAsync(arrayBuffer, wrap, null, {
    className: 'docx',
    ignoreWidth: false,
    ignoreHeight: false,
    ignoreFonts: false,
    breakPages: false,
    renderHeaders: true,
    renderFooters: true,
    renderFootnotes: true
  });
}
export function buildDomTextModel(root) {
  var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: function (n) {
      if (!n || !n.nodeValue) return NodeFilter.FILTER_REJECT;
      var p = n.parentElement;
      if (p) {
        var tag = (p.tagName || '').toLowerCase();
        if (tag === 'script' || tag === 'style') return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    }
  });
  var index = [];
  var text = '';
  while (walker.nextNode()) {
    var node = walker.currentNode;
    var start = text.length;
    var s = node.nodeValue;
    text += s;
    index.push({
      node: node,
      start: start,
      len: s.length
    });
  }
  return {
    text: text,
    index: index,
    root: root
  };
}
export function locateDomPos(model, globalOffset) {
  var idx = model.index;
  var lo = 0,
    hi = idx.length - 1;
  while (lo <= hi) {
    var mid = (lo + hi) >> 1;
    var it = idx[mid];
    if (globalOffset < it.start) hi = mid - 1;
    else if (globalOffset >= it.start + it.len) lo = mid + 1;
    else
      return {
        node: it.node,
        offset: globalOffset - it.start
      };
  }
  if (globalOffset === model.text.length && idx.length) {
    var last = idx[idx.length - 1];
    return {
      node: last.node,
      offset: last.len
    };
  }
  throw new Error('Offset out of bounds: ' + globalOffset);
}
export function getVisibleDocxSliceClone(sourcePagerEl) {
  var host = sourcePagerEl ? sourcePagerEl.querySelector('.docx-preview-host') : null;
  if (!host)
    return {
      fragment: document.createDocumentFragment(),
      sliceRoot: null,
      sliceText: ''
    };
  var blocks = host.querySelectorAll('p, li, h1, h2, h3, h4, h5, h6, table');
  var pagerRect = sourcePagerEl.getBoundingClientRect();
  var overscanPx = 120;
  var topY = pagerRect.top - overscanPx;
  var botY = pagerRect.bottom + overscanPx;
  var frag = document.createDocumentFragment();
  var sliceWrap = document.createElement('div');
  sliceWrap.className = 'docx-slice-wrap';
  var kept = 0;
  for (var i = 0; i < blocks.length; i++) {
    var b = blocks[i];
    var r = b.getBoundingClientRect();
    if (r.bottom < topY) continue;
    if (r.top > botY) break;
    sliceWrap.appendChild(b.cloneNode(true));
    kept++;
  }
  if (!kept) sliceWrap.appendChild(host.cloneNode(true));
  frag.appendChild(sliceWrap);
  var model = buildDomTextModel(sliceWrap);
  return {
    fragment: frag,
    sliceRoot: sliceWrap,
    sliceText: model.text
  };
}

// Compute the visible text slice directly from the live docx-preview DOM (no clones).
export function getVisibleDocxSliceText(sourcePagerEl) {
  var host = sourcePagerEl ? sourcePagerEl.querySelector('.docx-preview-host') : null;
  if (!host)
    return {
      text: '',
      start: 0,
      end: 0,
      model: null
    };
  var model = buildDomTextModel(host);
  if (!model || !model.text)
    return {
      text: '',
      start: 0,
      end: 0,
      model: model
    };
  var textLength = model.text.length;
  if (!textLength)
    return {
      text: '',
      start: 0,
      end: 0,
      model: model
    };
  var containerRect = sourcePagerEl.getBoundingClientRect();
  var viewTop = containerRect.top;
  var viewBottom = containerRect.bottom;
  function getCharRect(globalIndex) {
    var safeIndex = Math.max(0, Math.min(globalIndex, textLength - 1));
    var pos = locateDomPos(model, safeIndex);
    if (!pos || !pos.node) return null;
    var nodeLen = pos.node.nodeValue ? pos.node.nodeValue.length : 0;
    if (!nodeLen) return null;
    var range = document.createRange();
    range.setStart(pos.node, pos.offset);
    range.setEnd(pos.node, Math.min(pos.offset + 1, nodeLen));
    var rects = range.getClientRects();
    if (rects && rects.length) return rects[0];
    return range.getBoundingClientRect();
  }
  function getCharTop(globalIndex) {
    var r = getCharRect(globalIndex);
    return r ? r.top : viewTop;
  }
  function getCharBottom(globalIndex) {
    var r = getCharRect(globalIndex);
    return r ? r.bottom : viewTop;
  }
  function findFirstPartiallyVisible() {
    var lo = 0,
      hi = textLength - 1;
    var result = 0;
    while (lo <= hi) {
      var mid = Math.floor((lo + hi) / 2);
      var y = getCharBottom(mid);
      if (y < viewTop) {
        lo = mid + 1;
      } else {
        result = mid;
        hi = mid - 1;
      }
    }
    return result;
  }
  function findLastPartiallyVisible() {
    var lo = 0,
      hi = textLength - 1;
    var result = textLength - 1;
    while (lo <= hi) {
      var mid = Math.floor((lo + hi) / 2);
      var y = getCharTop(mid);
      if (y > viewBottom) {
        hi = mid - 1;
      } else {
        result = mid;
        lo = mid + 1;
      }
    }
    return result;
  }
  function lineTolForIndex(idx) {
    var r = getCharRect(idx);
    var h = r && r.height ? r.height : 14;
    return Math.max(1, h * 0.35);
  }
  function findLineStart(idx) {
    var lineY = getCharTop(idx);
    var target = lineY - lineTolForIndex(idx);
    var lo = 0,
      hi = idx;
    var result = idx;
    while (lo <= hi) {
      var mid = Math.floor((lo + hi) / 2);
      var y = getCharTop(mid);
      if (y < target) {
        lo = mid + 1;
      } else {
        result = mid;
        hi = mid - 1;
      }
    }
    return result;
  }
  function findLineEnd(idx) {
    var lineY = getCharTop(idx);
    var target = lineY + lineTolForIndex(idx);
    var lo = idx,
      hi = textLength - 1;
    var result = idx;
    while (lo <= hi) {
      var mid = Math.floor((lo + hi) / 2);
      var y = getCharTop(mid);
      if (y > target) {
        hi = mid - 1;
      } else {
        result = mid;
        lo = mid + 1;
      }
    }
    return result + 1;
  }
  function getLineBounds(idx) {
    return {
      start: findLineStart(idx),
      end: findLineEnd(idx)
    };
  }
  function getLineVisibilityRatio(bounds) {
    if (!bounds) return 0;
    var start = bounds.start;
    var end = bounds.end;
    var endIdx = Math.max(start, Math.min(textLength - 1, end - 1));
    var lineTop = getCharTop(start);
    var lineBottom = getCharBottom(endIdx);
    var visibleTop = Math.max(lineTop, viewTop);
    var visibleBottom = Math.min(lineBottom, viewBottom);
    var visible = Math.max(0, visibleBottom - visibleTop);
    var height = Math.max(1, lineBottom - lineTop);
    return visible / height;
  }
  var firstPartial = findFirstPartiallyVisible();
  var lastPartial = findLastPartiallyVisible();
  if (firstPartial > lastPartial) {
    var fallback = Math.max(0, Math.min(textLength - 1, lastPartial));
    if (!isFinite(fallback) || fallback < 0 || fallback >= textLength) {
      fallback = Math.max(0, Math.min(textLength - 1, firstPartial));
    }
    firstPartial = fallback;
    lastPartial = fallback;
  }
  var topBounds = getLineBounds(firstPartial);
  var bottomBounds = getLineBounds(lastPartial);
  var topRatio = getLineVisibilityRatio(topBounds);
  var bottomRatio = getLineVisibilityRatio(bottomBounds);
  var startIdx = topBounds.start;
  var endIdx = bottomBounds.end;
  if (topRatio < documentState.DOC_LINE_VISIBILITY_THRESHOLD) startIdx = topBounds.end;
  if (bottomRatio < documentState.DOC_LINE_VISIBILITY_THRESHOLD) endIdx = bottomBounds.start;
  if (startIdx >= endIdx) {
    if (topRatio >= bottomRatio) {
      startIdx = topBounds.start;
      endIdx = topBounds.end;
    } else {
      startIdx = bottomBounds.start;
      endIdx = bottomBounds.end;
    }
  }
  var maxChars = documentState.WINDOWED_MAX_CHARS;
  var guard = 0;
  while (endIdx - startIdx > maxChars && guard < 200) {
    var prevLineStart = findLineStart(endIdx - 1);
    if (prevLineStart <= startIdx) break;
    endIdx = prevLineStart;
    guard++;
  }
  var visibleText = model.text.slice(startIdx, endIdx);
  if (visibleText.length > maxChars) visibleText = visibleText.slice(0, maxChars);
  return {
    text: visibleText,
    start: startIdx,
    end: endIdx,
    model: model
  };
}
export function buildVisibleDocxSliceFragment(sliceInfo) {
  if (!sliceInfo || !sliceInfo.model) {
    return {
      sliceRoot: null
    };
  }
  var model = sliceInfo.model;
  var start = Math.max(0, sliceInfo.start || 0);
  var end = Math.max(start, sliceInfo.end || 0);
  if (!model.text || !model.text.length || end <= start) {
    return {
      sliceRoot: null
    };
  }
  var wrap = document.createElement('div');
  // Preserve docx-preview styling in the lookup pane.
  wrap.className = 'docx-preview-host docx';
  try {
    var a = locateDomPos(model, start);
    var b = locateDomPos(model, end);
    var r = document.createRange();
    r.setStart(a.node, a.offset);
    r.setEnd(b.node, b.offset);
    var frag = r.cloneContents();
    wrap.appendChild(frag);
  } catch (e) {
    return {
      sliceRoot: null
    };
  }
  return {
    sliceRoot: wrap
  };
}

// ============================================================================
// DEFUNCT (canonical-text contract): the functions in this block — path-based
// node resolution and the client-side normalization/remap layer — are no
// longer called from any active code path. The live mounted DOM is now the
// single source of truth (canonical text is extracted post-mount via
// DocRenderParsers.extractTextFromLiveRoot) and offset remapping happens only
// on the server. Definitions retained as no-op bookkeeping for any external
// reference; do not call from new code.
// ============================================================================
export function normalizeCanonicalTextMap(rawMap) {
  var src = Array.isArray(rawMap) ? rawMap : [];
  var out = [];
  for (var i = 0; i < src.length; i++) {
    var m = src[i] || {};
    var start = Number(m.start);
    var end = Number(m.end);
    var path = Array.isArray(m.path) ? m.path : [];
    if (!isFinite(start) || !isFinite(end) || end <= start || !path.length) continue;
    out.push({
      start: start,
      end: end,
      path: path.map(function (v) {
        return parseInt(v, 10) || 0;
      })
    });
  }
  out.sort(function (a, b) {
    return a.start - b.start || a.end - b.end;
  });
  return out;
}
export function locateCanonicalTextNodeByPath(root, path) {
  var cur = root;
  if (!cur || !Array.isArray(path)) return null;
  for (var i = 0; i < path.length; i++) {
    if (!cur || !cur.childNodes) return null;
    cur = cur.childNodes[path[i]];
  }
  return cur && cur.nodeType === Node.TEXT_NODE ? cur : null;
}
export function buildCanonicalTextRunsFromMap(sliceRoot, textMap) {
  var map = normalizeCanonicalTextMap(textMap);
  var runs = [];
  for (var i = 0; i < map.length; i++) {
    var m = map[i];
    var node = locateCanonicalTextNodeByPath(sliceRoot, m.path);
    if (!node) continue;
    runs.push({
      node: node,
      start: m.start,
      end: m.end
    });
  }
  return runs;
}
export function isFrontendArabicDiacriticChar(ch) {
  if (!ch) return false;
  return /[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]/.test(ch);
}
export function getFrontendLookupTextClusters(rawText) {
  var text = String(rawText == null ? '' : rawText);
  var clusters = [];
  if (typeof Intl !== 'undefined' && Intl.Segmenter) {
    try {
      var seg = new Intl.Segmenter(undefined, {
        granularity: 'grapheme'
      });
      var iter = seg.segment(text);
      iter.forEach(function (part) {
        clusters.push({
          text: String(part.segment || ''),
          start: Number(part.index) || 0,
          end: (Number(part.index) || 0) + String(part.segment || '').length
        });
      });
      if (clusters.length || !text) return clusters;
    } catch (_e) {}
  }
  for (var i = 0; i < text.length;) {
    var cp = text.codePointAt(i);
    var len = cp > 0xffff ? 2 : 1;
    clusters.push({
      text: text.slice(i, i + len),
      start: i,
      end: i + len
    });
    i += len;
  }
  return clusters;
}
export function buildFrontendLookupNormalizationMap(rawText, langOverride) {
  var raw = String(rawText == null ? '' : rawText);
  var lang = String(langOverride || documentShellState.currentLanguage || '').toLowerCase();
  var stripArabic = lang === 'ar' || lang === 'arabic' || lang.indexOf('ar-') === 0;
  var clusters = getFrontendLookupTextClusters(raw);
  var model = '';
  var charToRawStart = [];
  var charToRawEnd = [];
  for (var ci = 0; ci < clusters.length; ci++) {
    var cl = clusters[ci];
    var piece = String(cl.text || '');
    var norm = piece && piece.normalize ? piece.normalize('NFKC') : piece;
    for (var ni = 0; ni < norm.length;) {
      var cp = norm.codePointAt(ni);
      var clen = cp > 0xffff ? 2 : 1;
      var ch = norm.slice(ni, ni + clen);
      ni += clen;
      if (cp > 0xffff) continue;
      if (stripArabic && isFrontendArabicDiacriticChar(ch)) continue;
      var outStart = model.length;
      model += ch;
      for (var ui = outStart; ui < model.length; ui++) {
        charToRawStart[ui] = cl.start;
        charToRawEnd[ui] = cl.end;
      }
    }
  }
  return {
    rawText: raw,
    modelText: model,
    charToRawStart: charToRawStart,
    charToRawEnd: charToRawEnd,
    changed: model !== raw
  };
}
export function normalizeFrontendLookupSlice(rawText, langOverride) {
  return buildFrontendLookupNormalizationMap(rawText, langOverride).modelText;
}
export function mapFrontendModelRangeToRaw(pair, normMap) {
  if (!pair || pair.length < 2 || !normMap) return null;
  var modelText = String(normMap.modelText || '');
  var rawText = String(normMap.rawText || '');
  var modelLen = modelText.length;
  var rawLen = rawText.length;
  var s = Math.trunc(Number(pair[0]));
  var e = Math.trunc(Number(pair[1]));
  if (!isFinite(s) || !isFinite(e)) return null;
  if (s < 0) s = 0;
  if (e < s) e = s;
  if (s > modelLen) s = modelLen;
  if (e > modelLen) e = modelLen;
  if (modelLen === 0) return [0, 0];
  if (s === e) {
    var rawPoint =
      s >= modelLen ? rawLen : normMap.charToRawStart[s] != null ? normMap.charToRawStart[s] : rawLen;
    return [rawPoint, rawPoint];
  }
  var rawStart = s >= modelLen ? rawLen : normMap.charToRawStart[s];
  var rawEnd = e <= 0 ? rawStart : normMap.charToRawEnd[e - 1];
  if (rawStart == null) rawStart = rawLen;
  if (rawEnd == null) rawEnd = rawStart;
  return [rawStart, rawEnd];
}
export function scoreOffsetsAgainstTextSpace(offsets, segments, text, options) {
  var score = 0;
  var checked = 0;
  var opts = options || {};
  if (!Array.isArray(offsets) || !Array.isArray(segments))
    return {
      score: 0,
      checked: 0,
      maxEnd: 0
    };
  var limit = Math.min(offsets.length, segments.length, 1000);
  var maxEnd = 0;
  for (var i = 0; i < limit; i++) {
    var off = offsets[i];
    if (!off || off.length < 2) continue;
    var s = Math.trunc(Number(off[0]));
    var e = Math.trunc(Number(off[1]));
    if (!isFinite(s) || !isFinite(e)) continue;
    maxEnd = Math.max(maxEnd, e);
    if (s < 0 || e < s || e > text.length) continue;
    var slice = text.slice(s, e);
    if (opts.normalizeSlice) slice = normalizeFrontendLookupSlice(slice, opts.lang);
    if (slice === String(segments[i] || '')) score++;
    checked++;
  }
  return {
    score: score,
    checked: checked,
    maxEnd: maxEnd
  };
}
export function remapLookupResponseOffsetsToOriginalText(data, rawText, langOverride) {
  if (!data || typeof data !== 'object') return data;
  if (!Array.isArray(data.segment_offsets) || !Array.isArray(data.segments)) return data;
  var raw = String(rawText == null ? '' : rawText);
  if (data._frontend_offsets_remapped_to_original && data._frontend_offsets_remap_raw_len === raw.length)
    return data;
  var normMap = buildFrontendLookupNormalizationMap(raw, langOverride);
  if (!normMap.changed) {
    data._frontend_offsets_remapped_to_original = true;
    data._frontend_offsets_remap_raw_len = raw.length;
    data._frontend_offset_space = 'original_identity';
    return data;
  }
  var offsets = data.segment_offsets;
  var segments = data.segments;
  var rawScore = scoreOffsetsAgainstTextSpace(offsets, segments, raw, {
    normalizeSlice: true,
    lang: langOverride
  });
  var modelScore = scoreOffsetsAgainstTextSpace(offsets, segments, normMap.modelText, {
    normalizeSlice: false,
    lang: langOverride
  });
  var shouldRemap = false;
  if (modelScore.maxEnd > raw.length && modelScore.maxEnd <= normMap.modelText.length) {
    shouldRemap = true;
  } else if (modelScore.score > rawScore.score) {
    shouldRemap = true;
  }
  if (!shouldRemap) {
    data._frontend_offsets_remapped_to_original = true;
    data._frontend_offsets_remap_raw_len = raw.length;
    data._frontend_offset_space = 'original_detected';
    data._frontend_offset_remap_summary = {
      raw_len: raw.length,
      normalized_len: normMap.modelText.length,
      raw_score: rawScore.score,
      normalized_score: modelScore.score,
      remapped: false
    };
    return data;
  }
  var rawOffsets = [];
  for (var i = 0; i < offsets.length; i++) {
    rawOffsets.push(mapFrontendModelRangeToRaw(offsets[i], normMap) || offsets[i]);
  }
  data.segment_offsets_normalized = offsets.map(function (off) {
    return Array.isArray(off) ? off.slice(0, 2) : off;
  });
  data.segment_offsets = rawOffsets;
  data._frontend_offsets_remapped_to_original = true;
  data._frontend_offsets_remap_raw_len = raw.length;
  data._frontend_offset_space = 'original_from_normalized';
  data._frontend_offset_remap_summary = {
    raw_len: raw.length,
    normalized_len: normMap.modelText.length,
    raw_score: rawScore.score,
    normalized_score: modelScore.score,
    remapped: true
  };
  return data;
}
export function applyOffsetsAsTokenSpansOnDom(sliceRoot, data, preWalkedTextRuns) {
  if (!sliceRoot) return;
  var segments = Array.isArray(data.segments) ? data.segments : [];
  var gramOverlay =
    data.grammar_overlay && Array.isArray(data.grammar_overlay.tokens) ? data.grammar_overlay.tokens : [];
  var resultsBySeg = Array.isArray(data.results_by_seg) ? data.results_by_seg : [];
  var udTokenMap = dependencyState.latestUdTokenMap || {};
  var offsets = data && Array.isArray(data.segment_offsets) ? data.segment_offsets : null;
  if (!offsets || offsets.length !== segments.length) return;
  function splitTokenSpanByLines(span, segIdx) {
    if (!span || !span.parentNode) return;
    if (!(documentState.isOriginalView && documentState.currentFileType === 'docx')) return;
    if (!span.firstChild || span.childNodes.length !== 1 || span.firstChild.nodeType !== Node.TEXT_NODE)
      return;
    var rects = span.getClientRects ? span.getClientRects() : null;
    if (!rects || rects.length <= 1) return;
    var textNode = span.firstChild;
    var text = textNode.nodeValue || '';
    if (!text || text.length < 2) return;
    var range = document.createRange();
    var lastTop = null;
    var breakIdxs = [];
    for (var i = 0; i < text.length; i++) {
      range.setStart(textNode, i);
      range.setEnd(textNode, Math.min(i + 1, text.length));
      var rlist = range.getClientRects();
      var r = rlist && rlist.length ? rlist[0] : range.getBoundingClientRect();
      if (!r || !isFinite(r.top)) continue;
      if (lastTop == null) {
        lastTop = r.top;
      } else if (Math.abs(r.top - lastTop) > 0.5) {
        breakIdxs.push(i);
        lastTop = r.top;
      }
    }
    if (!breakIdxs.length) return;
    var pieces = [];
    var start = 0;
    for (var bi = 0; bi < breakIdxs.length; bi++) {
      var idx = breakIdxs[bi];
      if (idx > start) pieces.push(text.slice(start, idx));
      start = idx;
    }
    if (start < text.length) pieces.push(text.slice(start));
    if (!pieces.length) return;
    span.textContent = pieces[0];
    registerTokenSpan(segIdx, span);
    var parent = span.parentNode;
    var ref = span;
    for (var pi = 1; pi < pieces.length; pi++) {
      var piece = pieces[pi];
      if (!piece) continue;
      var clone = span.cloneNode(false);
      clone.textContent = piece;
      parent.insertBefore(clone, ref.nextSibling);
      ref = clone;
      registerTokenSpan(segIdx, clone);
    }
  }
  function forceTokenColor(el, color) {
    if (!el || !el.style) return;
    try {
      el.style.setProperty('color', color, 'important');
    } catch (e) {}
    var kids = el.querySelectorAll ? el.querySelectorAll('*') : [];
    for (var i = 0; i < kids.length; i++) {
      try {
        kids[i].style.setProperty('color', color, 'important');
      } catch (e2) {}
    }
  }
  function isDecoratableLookupTextNode(node) {
    if (!node || !node.nodeValue) return false;
    var nonTextTags = {
      IMG: 1,
      PICTURE: 1,
      SVG: 1,
      CANVAS: 1,
      VIDEO: 1,
      AUDIO: 1,
      IFRAME: 1,
      OBJECT: 1,
      EMBED: 1,
      SCRIPT: 1,
      STYLE: 1,
      TEMPLATE: 1,
      NOSCRIPT: 1
    };
    var p = node.parentNode;
    while (p && p.nodeType === 1) {
      if (nonTextTags[p.tagName]) return false;
      p = p.parentNode;
    }
    return true;
  }

  // Canonical-text contract: prefer textRuns produced by the SAME walk that
  // built `q` (zero-race window). Fall back to a fresh walk only for legacy
  // call sites that don't supply runs.
  var textRuns;
  if (
    Array.isArray(preWalkedTextRuns) &&
    preWalkedTextRuns.length &&
    preWalkedTextRuns[0] &&
    preWalkedTextRuns[0].node
  ) {
    textRuns = preWalkedTextRuns;
  } else {
    textRuns = [];
    var walker = document.createTreeWalker(sliceRoot, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        return isDecoratableLookupTextNode(node) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    var tn = walker.nextNode();
    var globalPos = 0;
    while (tn) {
      var value = tn.nodeValue || '';
      var start = globalPos;
      var end = start + value.length;
      textRuns.push({
        node: tn,
        start: start,
        end: end
      });
      globalPos = end;
      tn = walker.nextNode();
    }
  }
  var segIdx = 0;
  var segCount = segments.length;

  // Defer DOCX line-wrap re-splitting until after every text run has been
  // decorated and every span is registered, so the per-line clones do not
  // perturb the live DOM mid-iteration (canonical-text contract step 10).
  var pendingDocxLineSplits = [];
  for (var ni = 0; ni < textRuns.length; ni++) {
    var run = textRuns[ni];
    var node = run.node;
    var text = node && node.nodeValue ? node.nodeValue : '';
    var nodeStart = Number(run.start) || 0;
    var nodeEnd = Number(run.end) || nodeStart + text.length;
    if (!text.length) continue;

    // Advance past segments that end before this node.
    while (segIdx < segCount) {
      var offSkip = offsets[segIdx];
      if (!offSkip || offSkip.length < 2) {
        segIdx++;
        continue;
      }
      var endSkip = Number(offSkip[1]);
      if (!isFinite(endSkip) || endSkip <= nodeStart) {
        segIdx++;
        continue;
      }
      break;
    }
    if (segIdx >= segCount) break;
    var firstOff = offsets[segIdx];
    if (!firstOff || firstOff.length < 2) continue;
    var firstStart = Number(firstOff[0]);
    if (!isFinite(firstStart) || firstStart >= nodeEnd) {
      continue; // No segment starts in this node
    }
    var frag = document.createDocumentFragment();
    var spansToSplit = [];
    var cursor = 0;
    var localSegIdx = segIdx;
    var didChange = false;
    while (localSegIdx < segCount) {
      var off = offsets[localSegIdx];
      if (!off || off.length < 2) {
        localSegIdx++;
        segIdx = localSegIdx;
        continue;
      }
      var segStart = Number(off[0]);
      var segEnd = Number(off[1]);
      if (!isFinite(segStart) || !isFinite(segEnd) || segEnd <= segStart) {
        localSegIdx++;
        segIdx = localSegIdx;
        continue;
      }
      if (segStart >= nodeEnd) break;
      var localStart = Math.max(segStart, nodeStart) - nodeStart;
      var localEnd = Math.min(segEnd, nodeEnd) - nodeStart;
      if (localEnd <= localStart) {
        if (segEnd <= nodeStart) {
          localSegIdx++;
          segIdx = localSegIdx;
          continue;
        }
        break;
      }
      if (localStart > cursor) {
        frag.appendChild(document.createTextNode(text.slice(cursor, localStart)));
      }
      var piece = text.slice(localStart, localEnd);
      if (piece.length) {
        var tokInfo = buildTokenSpan(
          localSegIdx,
          segments[localSegIdx],
          gramOverlay,
          resultsBySeg,
          udTokenMap,
          {
            lightweight: false
          }
        );
        var span = tokInfo && tokInfo.span ? tokInfo.span : null;
        if (span) {
          var fullSegText = String(segments[localSegIdx] || '');
          var needsDotted = needsDottedCircle(fullSegText);
          var isFirstPart = segStart >= nodeStart;
          // Preserve buildTokenSpan() output when the NLP segment maps to this
          // whole DOM text run. That output contains .reader-token-fill-hit
          // targets for greedy/dict-fill segmentation. Only fall back to raw
          // piece text when a segment is physically split across DOM text nodes.
          if (piece !== fullSegText) {
            span.innerHTML = '';
            span.textContent = needsDotted && isFirstPart ? documentShellState.DOTTED_CIRCLE + piece : piece;
          }
          if (tokInfo && tokInfo.isUnknown) {
            span.dataset.hasUnknown = '1';
            if (
              documentState.isOriginalView &&
              documentState.currentFileType === 'docx' &&
              !span.classList.contains('unknown-token')
            ) {
              span.classList.add('unknown-token');
            }
          }
          frag.appendChild(span);
          registerTokenSpan(localSegIdx, span);
          spansToSplit.push({
            span: span,
            segIdx: localSegIdx
          });
        } else {
          frag.appendChild(document.createTextNode(piece));
        }
        didChange = true;
      }
      cursor = localEnd;
      if (segEnd <= nodeEnd) {
        localSegIdx++;
        segIdx = localSegIdx;
      } else {
        // Segment continues into next text node
        segIdx = localSegIdx;
        break;
      }
    }
    if (cursor < text.length) {
      frag.appendChild(document.createTextNode(text.slice(cursor)));
    }
    if (didChange && node.parentNode) {
      node.parentNode.replaceChild(frag, node);
      if (spansToSplit.length && documentState.isOriginalView && documentState.currentFileType === 'docx') {
        for (var si = 0; si < spansToSplit.length; si++) {
          pendingDocxLineSplits.push(spansToSplit[si]);
        }
      }
    }
  }

  // All decoration is now in place; safe to run line-wrap re-splitting.
  if (
    pendingDocxLineSplits.length &&
    documentState.isOriginalView &&
    documentState.currentFileType === 'docx'
  ) {
    for (var pi = 0; pi < pendingDocxLineSplits.length; pi++) {
      var item = pendingDocxLineSplits[pi];
      splitTokenSpanByLines(item.span, item.segIdx);
    }
  }
}
