import { num, str } from './frame-lifecycle.mjs';
import { frameLifecycleState } from './frame-lifecycle.state.mjs';
import { collectVisibleRectFragments } from './layout.mjs';
import {
  buildWebRectRunClusters,
  collectVisibleWordBoxes,
  isVisibleWebRectRun,
  makeRectRun,
  makeSeparatorRun,
  medianRunGap,
  mergeWebRectRunCluster,
  recomputeRunOffsets,
  webRunBox,
  webRunsShareLine
} from './selection.mjs';
import { clearSearchOverlay, nodeFilterConst } from './text-extraction.mjs';
import { textExtractionState } from './text-extraction.state.mjs';
export function sameWordBoxLine(a, b, opts) {
  return webRunsShareLine(a && a.box, b && b.box, opts);
}
export function estimateVisibleWordGap(state, viewport, opts) {
  var words = collectVisibleWordBoxes(state, viewport);
  if (words.length < 2) return 0;
  words.sort(function (a, b) {
    return num(a.box.y, 0) - num(b.box.y, 0) || num(a.box.x, 0) - num(b.box.x, 0);
  });
  var lines = [];
  for (var i = 0; i < words.length; i++) {
    var word = words[i];
    var line = null;
    for (var li = 0; li < lines.length; li++) {
      if (sameWordBoxLine(lines[li].anchor, word, opts)) {
        line = lines[li];
        break;
      }
    }
    if (!line) {
      line = {
        anchor: word,
        items: []
      };
      lines.push(line);
    }
    line.items.push(word);
  }
  var gaps = [];
  for (var l = 0; l < lines.length; l++) {
    var visual = lines[l].items.slice().sort(function (a, b) {
      return num(a.box.x, 0) - num(b.box.x, 0);
    });
    for (var gi = 1; gi < visual.length; gi++) {
      var gap = Math.max(0, visual[gi].box.x - visual[gi - 1].box.right);
      if (gap > 0) gaps.push(gap);
    }
  }
  return medianRunGap(gaps);
}
export function mergeNearbyWebRectRuns(runs, opts) {
  opts = Object.assign(
    {
      lineToleranceFactor: 0.55,
      insertSpaceGapPx: 1.25,
      fallbackWordGapPx: 6,
      wordGapMultiplier: 1.5
    },
    opts || {}
  );
  var visible = [];
  var runToCluster = new Map();
  for (var i = 0; i < runs.length; i++) {
    if (!isVisibleWebRectRun(runs[i])) continue;
    visible.push({
      run: runs[i],
      order: i,
      box: webRunBox(runs[i])
    });
  }
  if (visible.length < 2) {
    return {
      runs: runs,
      text: recomputeRunOffsets(runs),
      mergedCount: 0,
      mergeGapThresholdPx: 0
    };
  }
  var clusters = buildWebRectRunClusters(visible, opts);
  var mergedCount = 0;
  for (var ci = 0; ci < clusters.length; ci++) {
    if (!clusters[ci] || clusters[ci].length < 2) continue;
    var mergedRun = mergeWebRectRunCluster(clusters[ci], opts);
    if (!mergedRun) continue;
    mergedCount += clusters[ci].length - 1;
    for (var mi = 0; mi < clusters[ci].length; mi++) {
      runToCluster.set(clusters[ci][mi].run, {
        cluster: clusters[ci],
        mergedRun: mergedRun,
        firstRun: clusters[ci].slice().sort(function (a, b) {
          return num(a.order, 0) - num(b.order, 0);
        })[0].run
      });
    }
  }
  if (!mergedCount) {
    return {
      runs: runs,
      text: recomputeRunOffsets(runs),
      mergedCount: 0,
      mergeGapThresholdPx: opts.mergeGapThresholdPx || 0
    };
  }
  var out = [];
  for (var ri = 0; ri < runs.length; ri++) {
    var run = runs[ri];
    var info = runToCluster.get(run);
    if (info) {
      if (run === info.firstRun) out.push(info.mergedRun);
      continue;
    }
    if (run.source && run.source.synthetic) {
      var prevInfo = ri > 0 ? runToCluster.get(runs[ri - 1]) : null;
      var nextInfo = ri + 1 < runs.length ? runToCluster.get(runs[ri + 1]) : null;
      if (prevInfo && nextInfo && prevInfo.mergedRun === nextInfo.mergedRun) continue;
    }
    out.push(run);
  }
  return {
    runs: out,
    text: recomputeRunOffsets(out),
    mergedCount: mergedCount,
    mergeGapThresholdPx: opts.mergeGapThresholdPx || 0
  };
}
export function extractVisibleCanonicalDocument(state, opts) {
  opts = opts || {};
  var result = collectVisibleRectFragments(state, opts);
  if (!result || !result.text || !result.text.trim()) return null;
  var viewport = result.viewport;
  var runs = [];
  for (var i = 0; i < result.fragments.length; i++) {
    var fragment = result.fragments[i];
    fragment.viewport = viewport;
    if (i > 0) {
      var hasSeparator = Object.prototype.hasOwnProperty.call(fragment, 'separatorBefore');
      var sep = hasSeparator ? str(fragment.separatorBefore) : '\n';
      var sepStart = isFinite(Number(fragment.separatorStart))
        ? Number(fragment.separatorStart)
        : fragment.lookupStart - sep.length;
      if (sep) runs.push(makeSeparatorRun(i, sepStart, sep, fragment.separatorKind));
    }
    runs.push(makeRectRun(fragment));
  }
  var mergeOpts = Object.assign({}, opts.runMerge || opts.webSnapshotRunMerge || {});
  var measuredWordGap = estimateVisibleWordGap(state, viewport, mergeOpts);
  mergeOpts.wordGapPx = measuredWordGap || num(mergeOpts.fallbackWordGapPx, 6) || 6;
  mergeOpts.wordGapMultiplier = num(mergeOpts.wordGapMultiplier, 1.5) || 1.5;
  var merged = {
    runs: runs,
    text: recomputeRunOffsets(runs),
    mergedCount: 0,
    mergeGapThresholdPx: 0
  };
  if (opts.enableRunMerge === true) {
    merged = mergeNearbyWebRectRuns(runs, mergeOpts);
    runs = merged.runs;
  }
  var pageText = merged.text;
  var block = {
    id: 'web-rect-slice-block-0',
    type: 'rect-slice',
    start: 0,
    end: pageText.length,
    style: {},
    layout: {
      mode: 'fixed',
      x: 0,
      y: 0,
      width: viewport.width,
      height: viewport.height
    },
    runs: runs,
    source: {
      kind: 'webSnapshotRectSlice'
    }
  };
  var meta = Object.assign({}, state.meta || {}, {
    format: 'Remote HTML',
    parser: 'web-rect-slice',
    visibleSlice: true,
    wordRectRuns: true,
    scrollTop: viewport.scrollTop,
    viewportHeight: viewport.height,
    viewportWidth: viewport.width,
    fragmentCount: result.fragments.length,
    mergedRunCount: merged.mergedCount || 0,
    wordGapPx: mergeOpts.wordGapPx,
    wordGapMultiplier: mergeOpts.wordGapMultiplier,
    mergeGapThresholdPx: merged.mergeGapThresholdPx || mergeOpts.mergeGapThresholdPx || 0,
    paragraphBreakCount: result.separatorStats ? result.separatorStats.paragraphBreaks : 0,
    medianLineAdvance: result.separatorStats ? result.separatorStats.medianLineAdvance : 0
  });
  var doc = {
    schemaVersion: 1,
    id: 'web-rect-doc-' + Date.now().toString(36),
    meta: meta,
    pages: [
      {
        id: 'web-rect-page-0',
        index: 0,
        text: pageText,
        blocks: [block],
        tokens: [],
        layout: {
          mode: 'fixed',
          width: viewport.width,
          height: viewport.height
        },
        source: {
          kind: 'webSnapshotRectSlice',
          scrollTop: viewport.scrollTop,
          scrollLeft: viewport.scrollLeft,
          viewportWidth: viewport.width,
          viewportHeight: viewport.height,
          fragmentCount: result.fragments.length,
          documentUrl: str((state.meta && (state.meta.finalUrl || state.meta.requestedUrl)) || '')
        }
      }
    ],
    flowBlocks: [],
    source: {
      kind: 'webSnapshotRectSlice'
    }
  };
  if (
    frameLifecycleState.global.LookupChunks &&
    typeof frameLifecycleState.global.LookupChunks.applyLookupChunkParagraphBreaks === 'function'
  ) {
    frameLifecycleState.global.LookupChunks.applyLookupChunkParagraphBreaks(doc.pages[0], {
      sourceKind: 'web-geometry-chunk-paragraph'
    });
    if (doc.pages[0] && doc.pages[0].source) {
      meta.trankitChunkParagraphBreakCount = doc.pages[0].source.trankitChunkParagraphBreakCount || 0;
      meta.trankitChunkParagraphChunkCount = doc.pages[0].source.trankitChunkParagraphChunkCount || 0;
    }
  }
  return doc;
}
export function extractVisibleText(state, opts) {
  var result = collectVisibleRectFragments(state, opts || {});
  return result && result.text ? result.text.trim() : '';
}
export function shouldSearchTextNode(node) {
  if (!node || node.nodeType !== 3) return false;
  var text = str(node.nodeValue || '');
  if (!text.trim()) return false;
  var parent = node.parentElement;
  if (!parent) return false;
  try {
    if (parent.closest && parent.closest(textExtractionState.DOM_TEXT_IGNORE_SELECTOR)) return false;
  } catch (_e) {}
  return true;
}
export function buildSearchTextIndex(state) {
  var doc = state && state.doc;
  var body = doc && doc.body;
  var win = (state && state.win) || frameLifecycleState.global;
  var showText = nodeFilterConst(win, 'SHOW_TEXT', 4);
  var accept = nodeFilterConst(win, 'FILTER_ACCEPT', 1);
  var reject = nodeFilterConst(win, 'FILTER_REJECT', 2);
  var text = '';
  var segments = [];
  if (!doc || !body || !doc.createTreeWalker)
    return {
      text: '',
      segments: []
    };
  var walker = doc.createTreeWalker(body, showText, {
    acceptNode: function (node) {
      return shouldSearchTextNode(node) ? accept : reject;
    }
  });
  var node;
  while ((node = walker.nextNode())) {
    var value = str(node.nodeValue || '');
    if (!value) continue;
    if (text) text += ' ';
    var start = text.length;
    text += value;
    segments.push({
      node: node,
      start: start,
      end: start + value.length
    });
  }
  return {
    text: text,
    segments: segments
  };
}
export function locateSearchTextPosition(segments, index) {
  if (!segments || !segments.length) return null;
  var pos = Math.max(0, Math.floor(num(index, 0)));
  for (var i = 0; i < segments.length; i++) {
    var seg = segments[i];
    if (pos < seg.start) {
      return {
        node: seg.node,
        offset: 0
      };
    }
    if (pos <= seg.end) {
      return {
        node: seg.node,
        offset: Math.max(0, Math.min(seg.end - seg.start, pos - seg.start))
      };
    }
  }
  var last = segments[segments.length - 1];
  return {
    node: last.node,
    offset: Math.max(0, last.end - last.start)
  };
}
export function makeSearchRange(doc, segments, start, length) {
  var startRef = locateSearchTextPosition(segments, start);
  var endRef = locateSearchTextPosition(segments, start + Math.max(1, length));
  if (!doc || !startRef || !endRef) return null;
  try {
    var range = doc.createRange();
    range.setStart(startRef.node, startRef.offset);
    range.setEnd(endRef.node, endRef.offset);
    return range;
  } catch (_e) {
    return null;
  }
}
export function buildSearchExcerptParts(text, start, length) {
  var source = str(text || '');
  var s = Math.max(0, Math.floor(num(start, 0)));
  var len = Math.max(1, Math.floor(num(length, 1)));
  var from = Math.max(0, s - 48);
  var to = Math.min(source.length, s + len + 64);
  return {
    pre: (from > 0 ? '...' : '') + source.slice(from, s),
    match: source.slice(s, s + len),
    post: source.slice(s + len, to) + (to < source.length ? '...' : '')
  };
}
export function serializeSearchResult(result) {
  return {
    id: result.id,
    resultIndex: result.resultIndex,
    label: result.label,
    excerpt: result.excerpt
  };
}
export function search(state, query) {
  var q = str(query || '').trim();
  clearSearchOverlay(state);
  if (!state || !state.doc || !q) {
    if (state) {
      state.webSearchResults = [];
      state.webSearchTotal = 0;
    }
    return {
      total: 0,
      results: []
    };
  }
  var index = buildSearchTextIndex(state);
  var text = index.text || '';
  var hay = text.toLocaleLowerCase();
  var needle = q.toLocaleLowerCase();
  var results = [];
  var total = 0;
  var from = 0;
  while (needle && from < hay.length) {
    var hit = hay.indexOf(needle, from);
    if (hit < 0) break;
    total += 1;
    if (results.length < textExtractionState.MAX_WEB_SNAPSHOT_SEARCH_RESULTS) {
      var range = makeSearchRange(state.doc, index.segments, hit, q.length);
      results.push({
        id: 'web-search-' + (total - 1),
        resultIndex: total - 1,
        label: 'Match ' + total,
        excerpt: buildSearchExcerptParts(text, hit, q.length),
        range: range,
        start: hit,
        length: q.length
      });
    }
    from = hit + Math.max(1, needle.length);
  }
  state.webSearchResults = results;
  state.webSearchTotal = total;
  return {
    total: total,
    results: results.map(serializeSearchResult)
  };
}
