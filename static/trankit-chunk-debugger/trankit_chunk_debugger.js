/* Trankit chunk debugger.
 *
 * Geometry/style visualizer for proposed Trankit lookup chunks. It reads a
 * canonical page through window.__LE_getChunkDebugPage(), uses existing run
 * client rects as geometry units, flood-fills similar neighboring renderer runs,
 * and draws raw run boxes and final geometry chunks. It does not
 * mutate document layout, canonical text, lookup state, or rendered tokens.
 */
(function(global) {
  'use strict';

  var COLORS = [
    '#ef4444', '#2563eb', '#f97316', '#a855f7', '#0891b2',
    '#db2777', '#7c3aed', '#ca8a04', '#0f766e', '#4f46e5'
  ];
  var DEFAULT_OPTIONS = {
    drawRuns: true,
    drawWords: true,
    drawLines: false,
    drawEdges: false,
    linePairScore: 0.60
  };

  var enabled = false;
  var overlay = null;
  var button = null;
  var wordButton = null;
  var raf = 0;
  var refreshTimer = 0;
  var lastDebug = null;
  var debugOptions = cloneOptions(DEFAULT_OPTIONS);
  var overlayAnchorState = null;
  var overlayPositionRaf = 0;

  function str(v) { return v == null ? '' : String(v); }
  function num(v, fallback) {
    var n = Number(v);
    return isFinite(n) ? n : (fallback || 0);
  }
  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }
  function parsePx(v, fallback) {
    var n = parseFloat(str(v).replace(/px$/i, ''));
    return isFinite(n) && n > 0 ? n : (fallback || 0);
  }
  function normalizeFontFamily(v) {
    var raw = str(v).trim();
    if (!raw) return '';
    var first = raw.split(',')[0] || '';
    return first.replace(/^['"]+|['"]+$/g, '').trim().toLowerCase();
  }
  function fontFamilyFromStyle(style, source) {
    style = style || {};
    source = source || {};
    var family = style.fontFamily || source.fontFamily || '';
    if (family) return normalizeFontFamily(family);
    var shorthand = str(style.font || source.font || '');
    var m = shorthand.match(/(?:^|\s)(?:xx-small|x-small|small|medium|large|x-large|xx-large|smaller|larger|[\d.]+(?:px|pt|em|rem|%))(?:\s*\/\s*[\w.\-()%]+)?\s+(.+)$/i);
    return normalizeFontFamily(m ? m[1] : shorthand);
  }
  function cloneOptions(src) {
    var out = {};
    src = src || {};
    for (var k in src) if (Object.prototype.hasOwnProperty.call(src, k)) out[k] = src[k];
    return out;
  }
  function mergeOptions(base, extra) {
    var out = cloneOptions(base || DEFAULT_OPTIONS);
    extra = extra || {};
    for (var k in extra) if (Object.prototype.hasOwnProperty.call(extra, k)) out[k] = extra[k];
    return out;
  }
  function median(values, fallback) {
    var nums = (values || []).map(Number).filter(function(v) {
      return isFinite(v) && v > 0;
    }).sort(function(a, b) { return a - b; });
    if (!nums.length) return fallback || 0;
    var mid = Math.floor(nums.length / 2);
    return nums.length % 2 ? nums[mid] : ((nums[mid - 1] + nums[mid]) / 2);
  }
  function rectFromParts(left, top, width, height) {
    left = num(left, 0);
    top = num(top, 0);
    width = Math.max(0, num(width, 0));
    height = Math.max(0, num(height, 0));
    return {
      left: left,
      top: top,
      right: left + width,
      bottom: top + height,
      width: width,
      height: height,
      cx: left + width / 2,
      cy: top + height / 2
    };
  }
  function unionRect(rects) {
    var good = (rects || []).filter(function(r) {
      return r && isFinite(r.left) && isFinite(r.top) && r.width > 0 && r.height > 0;
    });
    if (!good.length) return null;
    var left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
    for (var i = 0; i < good.length; i++) {
      left = Math.min(left, good[i].left);
      top = Math.min(top, good[i].top);
      right = Math.max(right, good[i].right);
      bottom = Math.max(bottom, good[i].bottom);
    }
    return rectFromParts(left, top, right - left, bottom - top);
  }
  function overlapX(a, b) {
    if (!a || !b) return 0;
    return Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
  }
  function overlapY(a, b) {
    if (!a || !b) return 0;
    return Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  }
  function gapX(a, b) {
    if (!a || !b) return Infinity;
    if (a.right <= b.left) return b.left - a.right;
    if (b.right <= a.left) return a.left - b.right;
    return 0;
  }
  function gapY(a, b) {
    if (!a || !b) return Infinity;
    if (a.bottom <= b.top) return b.top - a.bottom;
    if (b.bottom <= a.top) return a.top - b.bottom;
    return 0;
  }
  function rectFromRawBox(r) {
    r = r || {};
    return rectFromParts(
      r.left != null ? r.left : r.x,
      r.top != null ? r.top : r.y,
      r.width,
      r.height
    );
  }
  function expCloseness(distance, scale) {
    scale = Math.max(1, num(scale, 1));
    return Math.exp(-Math.max(0, distance) / scale);
  }
  function dominant(values, fallback) {
    var counts = Object.create(null);
    var best = fallback || '';
    var bestCount = 0;
    for (var i = 0; i < (values || []).length; i++) {
      var key = str(values[i]).trim();
      if (!key) continue;
      counts[key] = (counts[key] || 0) + 1;
      if (counts[key] > bestCount) {
        best = key;
        bestCount = counts[key];
      }
    }
    return best;
  }
  function readingSort(a, b) {
    return a.rect.top - b.rect.top || a.rect.left - b.rect.left || a.sourceOrder - b.sourceOrder;
  }
  function visualUnitSort(units, direction) {
    var copy = (units || []).slice();
    var rtl = str(direction).toLowerCase() === 'rtl';
    copy.sort(function(a, b) {
      if (Math.abs(a.rect.cy - b.rect.cy) > Math.max(2, Math.min(a.rect.height, b.rect.height) * 0.45)) {
        return a.rect.top - b.rect.top || a.rect.left - b.rect.left;
      }
      return rtl ? (b.rect.right - a.rect.right || a.sourceOrder - b.sourceOrder) :
        (a.rect.left - b.rect.left || a.sourceOrder - b.sourceOrder);
    });
    return copy;
  }

  function isSyntheticRun(run) {
    var source = run && run.source || {};
    return !!(source.synthetic || /separator/i.test(str(source.kind || source.reason || '')));
  }
  function runClientRects(run) {
    var layout = run && run.layout || {};
    if (layout && layout.mode === 'fixed') {
      var w = num(layout.width != null ? layout.width : layout.fitWidth, 0);
      var h = num(layout.height, 0);
      if (w > 0 && h > 0) return [rectFromParts(layout.x, layout.y, w, h)];
    }
    var rects = [];
    var raw = Array.isArray(run && run.rects) ? run.rects : [];
    for (var i = 0; i < raw.length; i++) {
      var rect = rectFromRawBox(raw[i]);
      if (rect.width > 0.5 && rect.height > 0.5) rects.push(rect);
    }
    return rects;
  }
  function rawRunClientRects(run) {
    var rects = [];
    var raw = Array.isArray(run && run.rects) ? run.rects : [];
    for (var i = 0; i < raw.length; i++) {
      var rect = rectFromRawBox(raw[i]);
      if (rect.width > 0.5 && rect.height > 0.5) rects.push(rect);
    }
    return rects;
  }

  function wordRangesForText(text) {
    text = str(text).replace(/\u00a0/g, ' ');
    var ranges = [];
    var re = /\S+/g;
    var match;
    while ((match = re.exec(text))) {
      ranges.push({
        start: match.index,
        end: match.index + match[0].length,
        text: match[0]
      });
    }
    return ranges;
  }
  function rangeRectWithinBaseRect(base, start, end, total, direction) {
    if (!base) return null;
    total = Math.max(1, num(total, 1));
    start = clamp(num(start, 0), 0, total);
    end = clamp(num(end, start), start, total);
    if (end <= start) return null;
    var leftRatio = start / total;
    var rightRatio = end / total;
    var left = /^rtl$/i.test(str(direction))
      ? base.right - base.width * rightRatio
      : base.left + base.width * leftRatio;
    var right = /^rtl$/i.test(str(direction))
      ? base.right - base.width * leftRatio
      : base.left + base.width * rightRatio;
    return rectFromParts(left, base.top, Math.max(0.25, right - left), base.height);
  }
  function mergedRunTextSegments(run, rects) {
    var source = run && run.source || {};
    var mergedFrom = Array.isArray(source.mergedFrom) ? source.mergedFrom : [];
    if (!mergedFrom.length || !Array.isArray(rects) || rects.length !== mergedFrom.length) return null;
    var text = str(run && run.text).replace(/\u00a0/g, ' ');
    var cursor = 0;
    var segments = [];
    for (var i = 0; i < mergedFrom.length; i++) {
      var len = Math.max(0, Math.floor(num(mergedFrom[i] && mergedFrom[i].textLength, 0)));
      while (cursor < text.length && /\s/.test(text.charAt(cursor))) cursor++;
      if (!len) continue;
      var start = cursor;
      var end = Math.min(text.length, start + len);
      if (end <= start) return null;
      segments.push({
        start: start,
        end: end,
        rect: rects[i]
      });
      cursor = end;
    }
    return segments.length ? segments : null;
  }
  function wordRectFromMergedSegments(range, segments, direction) {
    if (!range || !segments || !segments.length) return null;
    var pieces = [];
    for (var i = 0; i < segments.length; i++) {
      var seg = segments[i];
      var start = Math.max(range.start, seg.start);
      var end = Math.min(range.end, seg.end);
      if (end <= start) continue;
      var piece = rangeRectWithinBaseRect(
        seg.rect,
        start - seg.start,
        end - seg.start,
        seg.end - seg.start,
        direction
      );
      if (piece) pieces.push(piece);
    }
    return unionRect(pieces);
  }
  function collectWordUnits(runUnits) {
    var words = [];
    var wordId = 0;
    for (var i = 0; i < (runUnits || []).length; i++) {
      var unit = runUnits[i];
      var ranges = wordRangesForText(unit && unit.text);
      if (!ranges.length) continue;
      var rects = rawRunClientRects(unit.run);
      if (!rects.length) rects = Array.isArray(unit.rects) && unit.rects.length ? unit.rects : [unit.rect];
      var mergedSegments = mergedRunTextSegments(unit.run, rects);
      var total = Math.max(1, str(unit.text).replace(/\u00a0/g, ' ').length);
      for (var ri = 0; ri < ranges.length; ri++) {
        var range = ranges[ri];
        var rect = wordRectFromMergedSegments(range, mergedSegments, unit.direction);
        if (!rect) rect = rangeRectWithinBaseRect(unit.rect, range.start, range.end, total, unit.direction);
        if (!rect || rect.width <= 0.25 || rect.height <= 0.25) continue;
        words.push({
          id: 'word-' + wordId,
          index: wordId,
          parentRunId: unit.id,
          run: unit.run,
          text: range.text,
          start: num(unit.start, 0) + range.start,
          end: num(unit.start, 0) + range.end,
          sourceOrder: num(unit.sourceOrder, i) + (range.start / Math.max(1, total + 1)),
          rect: rect,
          rects: [rect],
          fontSize: unit.fontSize,
          fontFamily: unit.fontFamily,
          fontWeight: unit.fontWeight,
          fontStyle: unit.fontStyle,
          direction: unit.direction,
          parentTag: unit.parentTag,
          parentId: unit.parentId,
          parentClass: unit.parentClass,
          domParentPath: unit.domParentPath,
          domParentKey: unit.domParentKey,
          domBlockKey: unit.domBlockKey,
          domBlockPath: unit.domBlockPath,
          domContainerKey: unit.domContainerKey,
          domContainerPath: unit.domContainerPath,
          domDivPathKey: unit.domDivPathKey,
          sourceKind: unit.sourceKind
        });
        wordId++;
      }
    }
    words.sort(readingSort);
    for (var wi = 0; wi < words.length; wi++) words[wi].index = wi;
    return words;
  }
  function collectRunUnits(page) {
    var units = [];
    var blocks = Array.isArray(page && page.blocks) ? page.blocks : [];
    var unitId = 0;
    for (var bi = 0; bi < blocks.length; bi++) {
      var blockRuns = Array.isArray(blocks[bi].runs) ? blocks[bi].runs : [];
      for (var ri = 0; ri < blockRuns.length; ri++) {
        var run = blockRuns[ri];
        if (!run || isSyntheticRun(run) || !str(run.text).trim()) continue;
        var style = run.style || {};
        var source = run.source || {};
        var direction = str(style.direction || source.direction || '').toLowerCase();
        if (direction !== 'rtl') direction = 'ltr';
        var rects = runClientRects(run);
        if (!rects.length) continue;
        var baseStart = num(run.start, 0);
        var rect = unionRect(rects);
        if (!rect || rect.width <= 0.5 || rect.height <= 0.5) continue;
        var rectHeight = median(rects.map(function(r) { return r.height; }), rect.height || 12);
        var text = str(run.text);
        units.push({
          id: 'run-' + unitId,
          index: unitId,
          run: run,
          block: blocks[bi],
          text: text,
          start: baseStart,
          end: num(run.end, baseStart + text.length),
          localStart: 0,
          localEnd: text.length,
          sourceOrder: unitId,
          blockIndex: bi,
          runIndex: ri,
          rectIndex: 0,
          rect: rect,
          rects: rects,
          fontSize: parsePx(style.fontSize, rectHeight || 12),
          fontFamily: fontFamilyFromStyle(style, source),
          fontWeight: str(style.fontWeight || source.fontWeight || ''),
          fontStyle: str(style.fontStyle || source.fontStyle || ''),
          direction: direction,
          parentTag: str(source.parentTag || source.sourceTag || '').toLowerCase(),
          parentId: str(source.parentId || ''),
          parentClass: str(source.parentClass || ''),
          domParentPath: str(source.domParentPath || ''),
          domParentKey: str(source.domParentKey || ''),
          domBlockKey: str(source.domBlockKey || ''),
          domBlockPath: str(source.domBlockPath || ''),
          domContainerKey: str(source.domContainerKey || ''),
          domContainerPath: str(source.domContainerPath || ''),
          domDivPathKey: str(source.domDivPathKey || (Array.isArray(source.domDivPath) ? source.domDivPath.join('>') : '')),
          sourceKind: str(source.kind || blocks[bi] && blocks[bi].source && blocks[bi].source.kind || '')
        });
        unitId++;
      }
    }
    units.sort(readingSort);
    for (var i = 0; i < units.length; i++) units[i].index = i;
    return units;
  }

  function groupRoughRows(units, medianHeight) {
    var rows = [];
    var sorted = (units || []).slice().sort(readingSort);
    var tol = Math.max(3, medianHeight * 0.45);
    for (var i = 0; i < sorted.length; i++) {
      var w = sorted[i];
      var best = null;
      var bestDelta = Infinity;
      for (var ri = 0; ri < rows.length; ri++) {
        var row = rows[ri];
        var delta = Math.abs(w.rect.cy - row.rect.cy);
        var yOverlap = overlapY(w.rect, row.rect);
        if (delta <= tol || yOverlap >= Math.min(w.rect.height, row.rect.height) * 0.50) {
          if (delta < bestDelta) {
            best = row;
            bestDelta = delta;
          }
        }
      }
      if (!best) {
        best = { units: [], rect: w.rect };
        rows.push(best);
      }
      best.units.push(w);
      best.rect = unionRect(best.units.map(function(x) { return x.rect; }));
    }
    rows.sort(function(a, b) { return a.rect.top - b.rect.top || a.rect.left - b.rect.left; });
    return rows;
  }
  function medianInlineGapFromWords(wordUnits, medianHeight) {
    var words = (wordUnits || []).filter(function(w) {
      return w && w.rect && w.rect.width > 0.25 && w.rect.height > 0.25;
    });
    if (words.length < 2) {
      return {
        inlineGap: Math.max(4, medianHeight * 0.35),
        medianWordWidth: 0,
        medianWordHeight: 0,
        wordGapCount: 0
      };
    }
    var wordHeights = words.map(function(x) { return x.rect.height; });
    var wordWidths = words.map(function(x) { return x.rect.width; });
    var medianWordHeight = median(wordHeights, medianHeight || 14);
    var medianWordWidth = median(wordWidths, Math.max(8, medianWordHeight * 2.5));
    var rows = groupRoughRows(words, medianWordHeight);
    var gaps = [];
    for (var ri = 0; ri < rows.length; ri++) {
      var rowWords = rows[ri].units.slice().sort(function(a, b) { return a.rect.left - b.rect.left; });
      for (var wi = 1; wi < rowWords.length; wi++) {
        var gap = rowWords[wi].rect.left - rowWords[wi - 1].rect.right;
        if (gap > 0 && gap <= Math.max(medianWordHeight * 5, medianWordWidth * 1.5)) gaps.push(gap);
      }
    }
    return {
      inlineGap: median(gaps, Math.max(4, medianWordHeight * 0.35)),
      medianWordWidth: medianWordWidth,
      medianWordHeight: medianWordHeight,
      wordGapCount: gaps.length
    };
  }

  function computeMetrics(units, wordUnits) {
    var heights = units.map(function(x) { return x.rect.height; });
    var widths = units.map(function(x) { return x.rect.width; });
    var medianHeight = median(heights, 14);
    var medianWidth = median(widths, Math.max(14, medianHeight * 2.5));
    var roughRows = groupRoughRows(units, medianHeight);
    var advances = [];
    for (var ri = 0; ri < roughRows.length; ri++) {
      if (ri > 0) {
        var adv = roughRows[ri].rect.top - roughRows[ri - 1].rect.top;
        if (adv > 2) advances.push(adv);
      }
    }
    var inlineStats = medianInlineGapFromWords(wordUnits, medianHeight);
    var inlineGap = inlineStats.inlineGap;
    var lineAdvance = median(advances, medianHeight * 1.25);
    var lineGap = Math.max(2, lineAdvance - medianHeight);
    var lineSplitGap = inlineGap * 1.5;
    var maxVerticalGap = Math.max(lineGap * 1.85, medianHeight * 1.45);
    var maxLineAdvance = Math.max(lineAdvance * 1.45, medianHeight * 1.9);
    return {
      medianHeight: medianHeight,
      medianRunWidth: medianWidth,
      medianWordWidth: inlineStats.medianWordWidth || medianWidth,
      medianWordHeight: inlineStats.medianWordHeight || medianHeight,
      medianLineAdvance: lineAdvance,
      medianLineGap: lineGap,
      medianInlineGap: inlineGap,
      inlineGapSource: 'word',
      inlineGapWordCount: (wordUnits || []).length,
      inlineGapSampleCount: inlineStats.wordGapCount || 0,
      lineSplitGap: lineSplitGap,
      maxVerticalGap: maxVerticalGap,
      maxLineAdvance: maxLineAdvance
    };
  }

  function hardDomBoundaryKey(item) {
    item = item || {};
    var divPath = str(item.domDivPathKey || '');
    if (divPath) return 'div:' + divPath;
    var containerPath = str(item.domContainerPath || item.domContainerKey || '');
    if (containerPath) return 'container:' + containerPath;
    return '';
  }
  function crossesHardDomBoundary(a, b) {
    var ak = hardDomBoundaryKey(a);
    var bk = hardDomBoundaryKey(b);
    return !!(ak && bk && ak !== bk);
  }

  function makeUnionFind(n) {
    var parent = [];
    var rank = [];
    for (var i = 0; i < n; i++) {
      parent[i] = i;
      rank[i] = 0;
    }
    function find(x) {
      while (parent[x] !== x) {
        parent[x] = parent[parent[x]];
        x = parent[x];
      }
      return x;
    }
    function unite(a, b) {
      var ra = find(a);
      var rb = find(b);
      if (ra === rb) return ra;
      if (rank[ra] < rank[rb]) {
        parent[ra] = rb;
        return rb;
      }
      if (rank[ra] > rank[rb]) {
        parent[rb] = ra;
        return ra;
      }
      parent[rb] = ra;
      rank[ra]++;
      return ra;
    }
    return { find: find, unite: unite };
  }
  function sameVisualRow(a, b, metrics) {
    if (!a || !b) return false;
    var minH = Math.max(1, Math.min(a.rect.height, b.rect.height));
    var yOverlap = overlapY(a.rect, b.rect) / minH;
    var cyDelta = Math.abs(a.rect.cy - b.rect.cy);
    return yOverlap >= 0.45 || cyDelta <= Math.max(2, metrics.medianHeight * 0.45);
  }

  function fontSizeSimilarity(a, b, metrics) {
    var fallback = metrics && metrics.medianHeight || 12;
    var as = parsePx(a && a.fontSize, fallback);
    var bs = parsePx(b && b.fontSize, fallback);
    var diff = Math.abs(as - bs);
    if (diff <= Math.max(0.75, fallback * 0.045)) return 1;
    var base = Math.max(1, Math.min(as || fallback, bs || fallback, fallback || 12));
    return clamp(1 - (diff / base) * 1.8, 0.25, 1);
  }

  function runPairScore(a, b, metrics) {
    if (crossesHardDomBoundary(a, b)) return 0;
    var fontScore = fontSizeSimilarity(a, b, metrics);
    if (sameVisualRow(a, b, metrics)) {
      var sameRowGap = gapX(a.rect, b.rect);
      if (sameRowGap > metrics.lineSplitGap) return 0;
      var hScore = expCloseness(sameRowGap, Math.max(1, metrics.medianInlineGap + metrics.medianHeight * 0.45));
      return hScore * 0.75 + fontScore * 0.25;
    }
    var verticalGap = b.rect.top - a.rect.bottom;
    var lineAdvance = b.rect.top - a.rect.top;
    var minWidth = Math.max(1, Math.min(a.rect.width, b.rect.width));
    if ((overlapX(a.rect, b.rect) / minWidth) < 0.10) return 0;
    if (verticalGap < -metrics.medianHeight * 0.25) return 0;
    if (verticalGap > metrics.maxVerticalGap) return 0;
    if (lineAdvance > metrics.maxLineAdvance) return 0;
    var vDistance = Math.abs(Math.max(0, verticalGap) - metrics.medianLineGap);
    var verticalScore = expCloseness(vDistance, Math.max(1, metrics.medianLineGap + metrics.medianHeight * 0.55));
    if (verticalGap < 0) verticalScore *= 0.8;
    return verticalScore * 0.75 + fontScore * 0.25;
  }

  function floodFillRuns(runs, metrics, opts) {
    runs = (runs || []).slice().sort(readingSort);
    for (var ri = 0; ri < runs.length; ri++) runs[ri].index = ri;
    var uf = makeUnionFind(runs.length);
    var edges = [];
    function addEdge(kind, a, b, score) {
      if (!a || !b || a.index == null || b.index == null || a.index === b.index) return;
      uf.unite(a.index, b.index);
      edges.push({ kind: kind, from: a.id, to: b.id, score: score });
    }

    for (var ai = 0; ai < runs.length; ai++) {
      var aLine = runs[ai];
      for (var bi = ai + 1; bi < runs.length; bi++) {
        var bLine = runs[bi];
        var lineAdvance = bLine.rect.top - aLine.rect.top;
        if (lineAdvance > metrics.maxLineAdvance) break;
        var ls = runPairScore(aLine, bLine, metrics);
        if (ls < opts.linePairScore) continue;
        addEdge('run', aLine, bLine, ls);
      }
    }

    var groups = Object.create(null);
    for (var i = 0; i < runs.length; i++) {
      var root = uf.find(i);
      if (!groups[root]) groups[root] = [];
      groups[root].push(runs[i]);
    }
    var components = [];
    var keys = Object.keys(groups);
    for (var ki = 0; ki < keys.length; ki++) {
      var rs = groups[keys[ki]];
      var rect = unionRect(rs.map(function(r) { return r.rect; }));
      components.push({ root: keys[ki], runs: rs, lines: rs, rect: rect });
    }
    components.sort(function(a, b) { return a.rect.top - b.rect.top || a.rect.left - b.rect.left; });
    return { components: components, edges: edges };
  }

  function isCjkLike(s) {
    return /[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]/.test(str(s));
  }
  function shouldSpaceBetween(a, b) {
    a = str(a);
    b = str(b);
    if (!a || !b) return '';
    if (isCjkLike(a.slice(-1)) || isCjkLike(b.charAt(0))) return '';
    if (/^[,.;:!?%)\]\}»”’、。？！；：]/.test(b)) return '';
    if (/[([\{«“‘]$/.test(a)) return '';
    return ' ';
  }
  function joinUnits(units, direction) {
    var sorted = visualUnitSort(units || [], direction || dominant((units || []).map(function(w) { return w.direction; }), 'ltr'));
    var out = '';
    for (var i = 0; i < sorted.length; i++) {
      if (i) out += shouldSpaceBetween(sorted[i - 1].text, sorted[i].text);
      out += str(sorted[i].text);
    }
    return out;
  }

  function sortedComponentRuns(component) {
    return (component && (component.runs || component.lines) || []).slice().sort(function(a, b) {
      return a.rect.top - b.rect.top || a.rect.left - b.rect.left || a.index - b.index;
    });
  }

  function unsafeInternalJump(prev, cur, metrics) {
    if (!prev || !cur) return false;
    if (crossesHardDomBoundary(prev, cur)) return true;
    var verticalGap = cur.rect.top - prev.rect.bottom;
    var lineAdvance = cur.rect.top - prev.rect.top;
    if (verticalGap > Math.max(metrics.maxVerticalGap * 1.15, metrics.medianHeight * 1.9)) return true;
    if (lineAdvance > metrics.maxLineAdvance * 1.05) return true;
    return false;
  }

  function chunkTextFromRuns(runs, metrics) {
    runs = (runs || []).slice().sort(readingSort);
    var out = '';
    for (var i = 0; i < runs.length; i++) {
      if (i) out += sameVisualRow(runs[i - 1], runs[i], metrics) ? shouldSpaceBetween(runs[i - 1].text, runs[i].text) : '\n';
      out += str(runs[i].text);
    }
    return out;
  }

  function makeChunkFromRuns(runs, id, kind, metrics) {
    runs = (runs || []).slice().sort(function(a, b) { return a.sourceOrder - b.sourceOrder; });
    var rect = unionRect(runs.map(function(l) { return l.rect; }));
    var starts = runs.map(function(w) { return w.start; });
    var ends = runs.map(function(w) { return w.end; });
    return {
      id: id,
      kind: kind || 'geometry',
      lines: runs,
      units: runs,
      words: runs,
      runs: runs,
      rect: rect,
      start: starts.length ? Math.min.apply(null, starts) : 0,
      end: ends.length ? Math.max.apply(null, ends) : 0,
      text: chunkTextFromRuns(runs, metrics),
      runCount: runs.length,
      wordCount: runs.length
    };
  }

  function chunksFromComponents(components, metrics) {
    var chunks = [];
    for (var ci = 0; ci < components.length; ci++) {
      var runs = sortedComponentRuns(components[ci]);
      if (!runs.length) continue;
      var current = [];
      for (var li = 0; li < runs.length; li++) {
        if (current.length && unsafeInternalJump(current[current.length - 1], runs[li], metrics)) {
          chunks.push(makeChunkFromRuns(current, 'chunk-pending', 'geometry', metrics));
          current = [];
        }
        current.push(runs[li]);
      }
      if (current.length) chunks.push(makeChunkFromRuns(current, 'chunk-pending', 'geometry', metrics));
    }
    chunks.sort(function(a, b) { return a.rect.top - b.rect.top || a.rect.left - b.rect.left; });
    for (var i = 0; i < chunks.length; i++) chunks[i].id = 'chunk-' + i;
    return chunks;
  }
  function annotateAssignments(chunks, wordUnits) {
    var runToChunk = Object.create(null);
    var wordToChunk = Object.create(null);
    var lineToChunk = Object.create(null);
    for (var ci = 0; ci < chunks.length; ci++) {
      var chunk = chunks[ci];
      for (var wi = 0; wi < (chunk.runs || chunk.units || []).length; wi++) {
        var unit = (chunk.runs || chunk.units)[wi];
        unit.chunkId = chunk.id;
        unit.chunkIndex = ci;
        runToChunk[unit.id] = ci;
      }
      for (var li = 0; li < (chunk.lines || []).length; li++) {
        chunk.lines[li].chunkId = chunk.id;
        chunk.lines[li].chunkIndex = ci;
        lineToChunk[chunk.lines[li].id] = ci;
      }
    }
    for (var wci = 0; wci < (wordUnits || []).length; wci++) {
      var word = wordUnits[wci];
      var chunkIndex = runToChunk[word && word.parentRunId];
      if (chunkIndex == null) continue;
      word.chunkId = chunks[chunkIndex] && chunks[chunkIndex].id;
      word.chunkIndex = chunkIndex;
      wordToChunk[word.id] = chunkIndex;
    }
    return { runToChunk: runToChunk, wordToChunk: wordToChunk, lineToChunk: lineToChunk };
  }

  function buildChunks(page, opts) {
    opts = mergeOptions(debugOptions, opts || {});
    var runUnits = collectRunUnits(page);
    var wordUnits = collectWordUnits(runUnits);
    var metrics = computeMetrics(runUnits, wordUnits);
    var graph = floodFillRuns(runUnits, metrics, opts);
    var chunks = chunksFromComponents(graph.components, metrics);
    var assignments = annotateAssignments(chunks, wordUnits);
    return {
      runUnits: runUnits,
      wordRects: wordUnits,
      words: wordUnits,
      runs: runUnits,
      visualLines: runUnits,
      lines: runUnits,
      lineRuns: runUnits,
      edges: graph.edges,
      components: graph.components,
      chunks: chunks,
      runToChunk: assignments.runToChunk,
      wordToChunk: assignments.wordToChunk,
      lineToChunk: assignments.lineToChunk,
      metrics: metrics,
      options: opts
    };
  }

  function appendMappedText(target, text, startOffset) {
    text = str(text);
    startOffset = Number(startOffset);
    for (var i = 0; i < text.length; i++) {
      target.text += text.charAt(i);
      target.offsetMap.push(isFinite(startOffset) ? startOffset + i : null);
    }
  }

  function appendUnmappedText(target, text) {
    text = str(text);
    for (var i = 0; i < text.length; i++) {
      target.text += text.charAt(i);
      target.offsetMap.push(null);
    }
  }

  function lookupChunkFromRuns(page, chunk, metrics) {
    var pageText = str(page && page.text);
    var runs = (chunk && (chunk.runs || chunk.units || chunk.lines) || []).slice().sort(function(a, b) {
      return a.sourceOrder - b.sourceOrder || a.start - b.start || a.rect.top - b.rect.top;
    });
    var out = { text: '', offsetMap: [] };
    var prev = null;
    var prevEnd = null;
    for (var i = 0; i < runs.length; i++) {
      var run = runs[i];
      var start = Math.max(0, Math.min(pageText.length, Math.floor(num(run.start, 0))));
      var end = Math.max(start, Math.min(pageText.length, Math.floor(num(run.end, start + str(run.text).length))));
      if (prev && prevEnd != null) {
        var gapLen = start - prevEnd;
        if (gapLen >= 0 && gapLen <= Math.max(80, metrics.medianHeight * 12)) {
          appendMappedText(out, pageText.slice(prevEnd, start), prevEnd);
        } else {
          appendUnmappedText(out, sameVisualRow(prev, run, metrics) ? shouldSpaceBetween(prev.text, run.text) : '\n');
        }
      }
      var piece = pageText.slice(start, end);
      if (piece) appendMappedText(out, piece, start);
      else appendMappedText(out, str(run.text), start);
      prev = run;
      prevEnd = end;
    }
    return {
      id: chunk.id,
      kind: chunk.kind || 'geometry',
      start: runs.length ? Math.min.apply(null, runs.map(function(r) { return num(r.start, 0); })) : 0,
      end: runs.length ? Math.max.apply(null, runs.map(function(r) { return num(r.end, 0); })) : 0,
      text: out.text,
      offsetMap: out.offsetMap,
      runCount: runs.length,
      rect: chunk.rect || null
    };
  }

  function buildLookupChunks(page, opts) {
    var result = buildChunks(page, opts || {});
    var chunks = [];
    for (var i = 0; i < result.chunks.length; i++) {
      var lookupChunk = lookupChunkFromRuns(page, result.chunks[i], result.metrics);
      if (str(lookupChunk.text).trim()) chunks.push(lookupChunk);
    }
    chunks.sort(function(a, b) { return num(a.start, 0) - num(b.start, 0) || num(a.end, 0) - num(b.end, 0); });
    return {
      chunks: chunks,
      debug: result,
      metrics: result.metrics,
      options: result.options
    };
  }

  function hasParagraphBreak(text) {
    return /\n[ \t\r\f\v]*\n/.test(str(text));
  }

  function runHasParagraphBreak(run) {
    if (!run) return false;
    if (hasParagraphBreak(run.text)) return true;
    var source = run.source || {};
    return str(source.separatorKind).toLowerCase() === 'paragraph' ||
      /paragraph/i.test(str(source.kind || source.reason || ''));
  }

  function promoteTrailingSyntheticSeparator(runs, seq, opts) {
    if (!Array.isArray(runs) || !runs.length) return '';
    for (var i = runs.length - 1; i >= 0; i--) {
      var run = runs[i];
      if (!run) continue;
      if (!isSyntheticRun(run)) return '';
      var text = str(run.text);
      if (!text) continue;
      if (text.trim()) return '';
      if (runHasParagraphBreak(run)) return 'exists';
      var sourceKind = str(opts && opts.sourceKind || 'geometry-chunk-paragraph');
      var source = Object.assign({}, run.source || {});
      source.synthetic = true;
      source.kind = sourceKind;
      source.separatorKind = 'paragraph';
      source.reason = 'trankit-geometry-chunk-boundary';
      source.promotedFromSeparator = true;
      run.id = run.id || ('tcdb-paragraph-sep-' + seq);
      run.text = '\n\n';
      run.end = num(run.start, 0) + 2;
      run.source = source;
      return 'promoted';
    }
    return '';
  }

  function makeLookupParagraphSeparatorRun(seq, start, opts) {
    opts = opts || {};
    var sourceKind = str(opts.sourceKind || 'geometry-chunk-paragraph');
    return {
      id: 'tcdb-paragraph-sep-' + seq,
      text: '\n\n',
      start: start,
      end: start + 2,
      style: {
        fontSize: '0px',
        lineHeight: '0px',
        opacity: '0'
      },
      layout: {
        mode: 'fixed',
        x: -99999,
        y: -99999,
        width: 0,
        height: 0
      },
      rects: [],
      source: {
        synthetic: true,
        kind: sourceKind,
        separatorKind: 'paragraph',
        reason: 'trankit-geometry-chunk-boundary'
      }
    };
  }

  function applyLookupChunkParagraphBreaks(page, opts) {
    opts = opts || {};
    if (!page || !Array.isArray(page.blocks)) return page;
    page.source = page.source || {};
    if (page.source.trankitChunkParagraphBreaksApplied) return page;
    if (!global.CanonicalModel || typeof global.CanonicalModel.recomputePageText !== 'function') return page;

    var chunkResult = buildLookupChunks(page, opts.chunkOptions || {
      drawRuns: false,
      drawLines: false,
      drawEdges: false
    });
    var chunks = (chunkResult && Array.isArray(chunkResult.chunks) ? chunkResult.chunks : [])
      .filter(function(chunk) { return chunk && str(chunk.text).trim(); })
      .sort(function(a, b) { return num(a.start, 0) - num(b.start, 0) || num(a.end, 0) - num(b.end, 0); });
    if (chunks.length < 2) return page;

    var pageText = str(page.text);
    var boundaryByStart = Object.create(null);
    var boundaryCount = 0;
    for (var i = 1; i < chunks.length; i++) {
      var prev = chunks[i - 1];
      var cur = chunks[i];
      var prevEnd = Math.max(0, Math.min(pageText.length, Math.floor(num(prev.end, 0))));
      var curStart = Math.max(0, Math.min(pageText.length, Math.floor(num(cur.start, 0))));
      if (curStart <= 0 || curStart < prevEnd) continue;
      if (hasParagraphBreak(pageText.slice(prevEnd, curStart))) continue;
      boundaryByStart[String(curStart)] = true;
      boundaryCount += 1;
    }
    if (!boundaryCount) return page;

    var inserted = 0;
    for (var bi = 0; bi < page.blocks.length; bi++) {
      var block = page.blocks[bi];
      var runs = Array.isArray(block && block.runs) ? block.runs : [];
      if (!runs.length) continue;
      var nextRuns = [];
      for (var ri = 0; ri < runs.length; ri++) {
        var run = runs[ri];
        var startKey = String(Math.max(0, Math.floor(num(run && run.start, 0))));
        if (boundaryByStart[startKey] && !isSyntheticRun(run)) {
          var promoted = promoteTrailingSyntheticSeparator(nextRuns, inserted, opts);
          if (!promoted) {
            nextRuns.push(makeLookupParagraphSeparatorRun(inserted, num(run.start, 0), opts));
            inserted += 1;
          } else if (promoted === 'promoted') {
            inserted += 1;
          }
          delete boundaryByStart[startKey];
        }
        nextRuns.push(run);
      }
      block.runs = nextRuns;
    }
    if (!inserted) return page;

    global.CanonicalModel.recomputePageText(page);
    page.source.trankitChunkParagraphBreaksApplied = true;
    page.source.trankitChunkParagraphBreakCount = inserted;
    page.source.trankitChunkParagraphChunkCount = chunks.length;
    return page;
  }

  function ensureButton() {
    return null;
  }
  function ensureWordButton() {
    return null;
  }
  function ensureControls() {
    updateControlState();
  }
  function updateControlState() {
    if (button) {
      button.classList.toggle('tcdb-active', enabled);
      button.setAttribute('aria-pressed', enabled ? 'true' : 'false');
    }
    if (wordButton) {
      var drawWords = !!debugOptions.drawWords;
      wordButton.classList.toggle('tcdb-visible', enabled);
      wordButton.classList.toggle('tcdb-active', drawWords);
      wordButton.disabled = !enabled;
      wordButton.setAttribute('aria-hidden', enabled ? 'false' : 'true');
      wordButton.setAttribute('aria-pressed', drawWords ? 'true' : 'false');
    }
  }
  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'trankitChunkOverlay';
    document.body.appendChild(overlay);
    return overlay;
  }
  function clearOverlay() {
    unbindOverlayPositionSync();
    if (overlay) overlay.innerHTML = '';
  }

  function visibleRect(el) {
    if (!el || !el.getBoundingClientRect) return null;
    var r = el.getBoundingClientRect();
    if (!r || r.width <= 1 || r.height <= 1) return null;
    return r;
  }
  function renderedCanonicalAnchor(page) {
    var roots = document.querySelectorAll('#renderedText .canonical-page');
    var pageId = str(page && page.id);
    var pageIndex = str(page && page.index);
    var fallback = null;
    for (var i = 0; i < roots.length; i++) {
      var r = visibleRect(roots[i]);
      if (!r) continue;
      if (!fallback) fallback = { el: roots[i], rect: r };
      if ((pageId && roots[i].dataset.pageId === pageId) || roots[i].dataset.pageIndex === pageIndex) {
        return { el: roots[i], rect: r, kind: 'rendered' };
      }
    }
    return fallback ? { el: fallback.el, rect: fallback.rect, kind: 'rendered' } : null;
  }
  function sourcePagerAnchor(page) {
    var el = document.getElementById('sourcePager');
    var rect = visibleRect(el);
    if (!rect) return null;
    var layout = page && page.layout || {};
    if (!layout.width || !layout.height) return null;
    return { el: el, rect: rect, kind: 'source' };
  }
  function findAnchor(page, mode, source) {
    return sourcePagerAnchor(page);
  }
  function getInnerScrollElement(el) {
    if (!el || !el.querySelector) return null;
    var frame = el.querySelector('iframe.pdfjs-host-iframe') || el.querySelector('iframe');
    if (!frame) return null;
    try {
      var doc = frame.contentDocument;
      if (!doc) return null;
      var pdfContainer = doc.getElementById && doc.getElementById('pdfContainer');
      var scroller = pdfContainer || doc.scrollingElement || doc.documentElement || doc.body;
      if (!scroller) return null;
      return scroller;
    } catch (_e) {
      return null;
    }
  }
  function anchorScrollTargets(anchor) {
    var out = [];
    if (anchor && anchor.el) out.push(anchor.el);
    var inner = getInnerScrollElement(anchor && anchor.el);
    if (inner && out.indexOf(inner) < 0) out.push(inner);
    return out;
  }
  function readAnchorScroll(anchor) {
    var left = 0;
    var top = 0;
    var targets = anchorScrollTargets(anchor);
    for (var i = 0; i < targets.length; i++) {
      left += num(targets[i] && targets[i].scrollLeft, 0);
      top += num(targets[i] && targets[i].scrollTop, 0);
    }
    return { left: left, top: top };
  }
  function setStageRect(stage, rect) {
    if (!stage || !rect) return;
    stage.style.left = rect.left + 'px';
    stage.style.top = rect.top + 'px';
    stage.style.width = Math.max(1, rect.width) + 'px';
    stage.style.height = Math.max(1, rect.height) + 'px';
  }
  function createOverlayStage(root, anchor, opts) {
    opts = opts || {};
    unbindOverlayPositionSync();
    var stage = document.createElement('div');
    stage.className = 'tcdb-stage';
    setStageRect(stage, anchor.rect);
    var content = document.createElement('div');
    content.className = 'tcdb-stage-content';
    stage.appendChild(content);
    root.appendChild(stage);
    overlayAnchorState = {
      anchor: anchor,
      stage: stage,
      content: content,
      rect: anchor.rect,
      scroll: readAnchorScroll(anchor),
      targets: anchorScrollTargets(anchor),
      fullContentCoordinates: !!opts.fullContentCoordinates,
      recomputeOnScroll: !!opts.recomputeOnScroll
    };
    bindOverlayPositionSync();
    syncOverlayPosition();
    return content;
  }
  function syncOverlayPosition() {
    overlayPositionRaf = 0;
    var state = overlayAnchorState;
    if (!state || !state.anchor || !state.stage || !state.content) return;
    var rect = visibleRect(state.anchor.el);
    if (!rect) return;
    setStageRect(state.stage, rect);
    var scroll = readAnchorScroll(state.anchor);
    var dx = state.fullContentCoordinates ? -scroll.left : (state.scroll.left - scroll.left);
    var dy = state.fullContentCoordinates ? -scroll.top : (state.scroll.top - scroll.top);
    state.content.style.transform = 'translate(' + dx + 'px,' + dy + 'px)';
  }
  function scheduleOverlayPositionSync() {
    if (!overlayAnchorState || overlayPositionRaf) return;
    if (overlayAnchorState.recomputeOnScroll) {
      scheduleRefresh();
      return;
    }
    overlayPositionRaf = global.requestAnimationFrame(syncOverlayPosition);
  }
  function bindOverlayPositionSync() {
    var state = overlayAnchorState;
    if (!state) return;
    state.targets = anchorScrollTargets(state.anchor);
    for (var i = 0; i < state.targets.length; i++) {
      try { state.targets[i].addEventListener('scroll', scheduleOverlayPositionSync, true); } catch (_e) {}
    }
    global.addEventListener('resize', scheduleOverlayPositionSync, true);
    global.addEventListener('scroll', scheduleOverlayPositionSync, true);
    document.addEventListener('scroll', scheduleOverlayPositionSync, true);
  }
  function unbindOverlayPositionSync() {
    var state = overlayAnchorState;
    if (state && Array.isArray(state.targets)) {
      for (var i = 0; i < state.targets.length; i++) {
        try { state.targets[i].removeEventListener('scroll', scheduleOverlayPositionSync, true); } catch (_e) {}
      }
    }
    global.removeEventListener('resize', scheduleOverlayPositionSync, true);
    global.removeEventListener('scroll', scheduleOverlayPositionSync, true);
    document.removeEventListener('scroll', scheduleOverlayPositionSync, true);
    if (overlayPositionRaf) global.cancelAnimationFrame(overlayPositionRaf);
    overlayPositionRaf = 0;
    overlayAnchorState = null;
  }
  function mappedRect(r, anchor, scaleX, scaleY) {
    return rectFromParts(
      r.left * scaleX,
      r.top * scaleY,
      Math.max(1, r.width * scaleX),
      Math.max(1, r.height * scaleY)
    );
  }
  function appendFixedBox(parent, className, rect, anchor, scaleX, scaleY, color) {
    var m = mappedRect(rect, anchor, scaleX, scaleY);
    var box = document.createElement('div');
    box.className = className;
    if (color) box.style.color = color;
    box.style.left = m.left + 'px';
    box.style.top = m.top + 'px';
    box.style.width = Math.max(1, m.width) + 'px';
    box.style.height = Math.max(1, m.height) + 'px';
    parent.appendChild(box);
    return box;
  }
  function colorForIndex(i) {
    return COLORS[(Math.max(0, i) || 0) % COLORS.length];
  }
  function drawEdges(root, result, anchor, scaleX, scaleY) {
    var nodeById = Object.create(null);
    for (var li = 0; li < result.visualLines.length; li++) nodeById[result.visualLines[li].id] = result.visualLines[li];
    for (var wi = 0; wi < result.wordRects.length; wi++) nodeById[result.wordRects[wi].id] = result.wordRects[wi];
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.classList.add('tcdb-edge-svg');
    root.appendChild(svg);
    for (var ei = 0; ei < result.edges.length; ei++) {
      var edge = result.edges[ei];
      var a = nodeById[edge.from];
      var b = nodeById[edge.to];
      if (!a || !b) continue;
      var ai = result.lineToChunk[a.id] == null
        ? (result.wordToChunk[a.id] == null ? 0 : result.wordToChunk[a.id])
        : result.lineToChunk[a.id];
      var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', String(a.rect.cx * scaleX));
      line.setAttribute('y1', String(a.rect.cy * scaleY));
      line.setAttribute('x2', String(b.rect.cx * scaleX));
      line.setAttribute('y2', String(b.rect.cy * scaleY));
      line.setAttribute('stroke', colorForIndex(ai));
      line.setAttribute('data-kind', edge.kind);
      line.setAttribute('data-score', String(Math.round(edge.score * 1000) / 1000));
      line.classList.add('tcdb-edge');
      svg.appendChild(line);
    }
  }
  function draw(result, page, mode, source) {
    var root = ensureOverlay();
    root.innerHTML = '';
    var anchor = findAnchor(page, mode, source);
    if (!anchor) return false;
    var isPdfSource = mode === 'pdf' || /canonical-pdf/i.test(str(source));
    var isVisibleHtmlSource = mode === 'html' || /web-visible-slice|foliate-visible-slice/i.test(str(source));
    var stage = createOverlayStage(root, anchor, {
      fullContentCoordinates: isPdfSource,
      recomputeOnScroll: isVisibleHtmlSource
    });
    var layout = page && page.layout || {};
    var pageW = Math.max(1, num(layout.width, anchor.rect.width));
    var pageH = Math.max(1, num(layout.height, anchor.rect.height));
    var scaleX = anchor.rect.width / pageW;
    var scaleY = anchor.rect.height / pageH;

    if (result.options.drawEdges) drawEdges(stage, result, anchor, scaleX, scaleY);

    var runLayer = document.createElement('div');
    runLayer.className = 'tcdb-layer tcdb-run-layer';
    stage.appendChild(runLayer);
    var wordLayer = document.createElement('div');
    wordLayer.className = 'tcdb-layer tcdb-word-layer';
    stage.appendChild(wordLayer);
    var lineLayer = document.createElement('div');
    lineLayer.className = 'tcdb-layer tcdb-line-layer';
    stage.appendChild(lineLayer);
    var chunkLayer = document.createElement('div');
    chunkLayer.className = 'tcdb-layer tcdb-chunk-layer';
    stage.appendChild(chunkLayer);

    if (result.options.drawRuns !== false) {
      for (var rui = 0; rui < result.runUnits.length; rui++) {
        var rawRun = result.runUnits[rui];
        var chunkIndex = result.runToChunk[rawRun.id] == null ? 0 : result.runToChunk[rawRun.id];
        var runColor = colorForIndex(chunkIndex);
        var runBox = appendFixedBox(runLayer, 'tcdb-run', rawRun.rect, anchor, scaleX, scaleY, runColor);
        runBox.dataset.runId = rawRun.id;
        runBox.dataset.rect = 'union';
        runBox.dataset.chunk = String(chunkIndex + 1);
      }
    }

    if (result.options.drawWords) {
      for (var wui = 0; wui < result.wordRects.length; wui++) {
        var word = result.wordRects[wui];
        var wordChunkIndex = result.wordToChunk[word.id] == null ? 0 : result.wordToChunk[word.id];
        var wordBox = appendFixedBox(wordLayer, 'tcdb-word', word.rect, anchor, scaleX, scaleY, colorForIndex(wordChunkIndex));
        wordBox.dataset.wordId = word.id;
        wordBox.dataset.parentRunId = word.parentRunId || '';
        wordBox.dataset.chunk = String(wordChunkIndex + 1);
      }
    }

    if (result.options.drawLines) {
      for (var c1 = 0; c1 < result.chunks.length; c1++) {
        var chunkForLines = result.chunks[c1];
        var lineColor = colorForIndex(c1);
        for (var li = 0; li < (chunkForLines.lines || []).length; li++) {
          var lineObj = chunkForLines.lines[li];
          var lineBox = appendFixedBox(lineLayer, 'tcdb-line', lineObj.rect, anchor, scaleX, scaleY, lineColor);
          lineBox.dataset.lineId = lineObj.id;
          lineBox.dataset.chunk = String(c1 + 1);
        }
      }
    }

    for (var i = 0; i < result.chunks.length; i++) {
      var chunk = result.chunks[i];
      var r = chunk.rect;
      if (!r || r.width <= 1 || r.height <= 1) continue;
      var box = appendFixedBox(chunkLayer, 'tcdb-box', r, anchor, scaleX, scaleY, colorForIndex(i));
      box.dataset.kind = chunk.kind || 'geometry';
      box.dataset.chunk = String(i + 1);
    }
    return true;
  }

  function refresh() {
    if (!enabled) return;
    var btn = ensureButton();
    if (btn) btn.classList.remove('tcdb-empty');
    clearOverlay();
    if (typeof global.__LE_getChunkDebugPage !== 'function') {
      if (btn) btn.classList.add('tcdb-empty');
      lastDebug = { ok: false, error: 'Reader bridge unavailable.' };
      return;
    }
    var payload = null;
    try { payload = global.__LE_getChunkDebugPage(); } catch (err) {
      payload = { ok: false, error: String(err && err.message || err) };
    }
    if (!payload || !payload.ok || !payload.page) {
      if (btn) btn.classList.add('tcdb-empty');
      lastDebug = payload || { ok: false };
      return;
    }
    var result = buildChunks(payload.page, debugOptions);
    var ok = draw(result, payload.page, payload.mode, payload.source);
    if (!ok && btn) btn.classList.add('tcdb-empty');
    lastDebug = {
      ok: ok,
      payload: payload,
      chunks: result.chunks,
      runUnits: result.runUnits,
      wordRects: result.wordRects,
      words: result.wordRects,
      visualLines: result.visualLines,
      lines: result.visualLines,
      edges: result.edges,
      components: result.components,
      metrics: result.metrics,
      options: result.options
    };
    if (btn) btn.dataset.count = String(result.chunks.length || 0);
  }
  function scheduleRefresh() {
    if (!enabled || raf) return;
    raf = global.requestAnimationFrame(function() {
      raf = 0;
      refresh();
    });
  }
  function bindLiveRefresh() {
    refresh();
  }
  function unbindLiveRefresh() {
    if (refreshTimer) global.clearInterval(refreshTimer);
    refreshTimer = 0;
    if (raf) global.cancelAnimationFrame(raf);
    raf = 0;
  }
  function setEnabled(next) {
    enabled = !!next;
    ensureControls();
    if (enabled) {
      ensureOverlay();
      bindLiveRefresh();
    } else {
      unbindLiveRefresh();
      clearOverlay();
      if (button) button.classList.remove('tcdb-empty');
    }
    updateControlState();
  }
  function setOptions(opts) {
    debugOptions = mergeOptions(debugOptions, opts || {});
    updateControlState();
    scheduleRefresh();
    return cloneOptions(debugOptions);
  }
  function init() {
    if (document.body) ensureControls();
    else document.addEventListener('DOMContentLoaded', ensureControls, { once: true });
  }

  global.TrankitChunkDebugger = {
    buildChunks: buildChunks,
    buildLookupChunks: buildLookupChunks,
    applyLookupChunkParagraphBreaks: applyLookupChunkParagraphBreaks,
    refresh: refresh,
    setEnabled: setEnabled,
    setOptions: setOptions,
    isEnabled: function() { return enabled; },
    getOptions: function() { return cloneOptions(debugOptions); },
    getLastDebug: function() { return lastDebug; }
  };

  init();
})(window);
