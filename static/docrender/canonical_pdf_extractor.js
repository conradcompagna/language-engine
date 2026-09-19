/* canonical_pdf_extractor.js
 *
 * PDF.js text-content -> canonical fixed-layout textual skeleton.
 *
 * This is bottom-pane model construction only. The top pane should keep using
 * PDF.js canvas/text rendering. The bottom pane gets a fresh CanonicalDocument:
 * text and fixed text geometry are built together before lookup, then tokens
 * are rendered into this canonical model after /lookup returns.
 *
 * Browser global:
 *   window.CanonicalPdfExtractor
 */
(function(global) {
  'use strict';

  function requireDeps() {
    if (!global.CanonicalBuilder || !global.CanonicalModel || !global.CanonicalStyle) {
      throw new Error('CanonicalBuilder, CanonicalModel, and CanonicalStyle must be loaded before CanonicalPdfExtractor');
    }
  }

  function str(v) { return v == null ? '' : String(v); }
  function num(v, fallback) {
    var n = Number(v);
    return isFinite(n) ? n : (fallback || 0);
  }
  function clamp(v, lo, hi) {
    v = num(v, lo);
    return Math.max(lo, Math.min(hi, v));
  }
  function median(values, fallback) {
    var arr = (values || []).filter(function(v) { return isFinite(v) && v > 0; }).sort(function(a, b) { return a - b; });
    if (!arr.length) return fallback;
    return arr[Math.floor(arr.length / 2)];
  }

  function viewportScale(viewport) {
    var s = num(viewport && viewport.scale, 0);
    if (s > 0) return s;
    var tr = viewport && Array.isArray(viewport.transform) ? viewport.transform : null;
    if (!tr) return 1;
    return Math.max(1, Math.hypot(num(tr[0], 1), num(tr[1], 0)) || 1);
  }

  function transformedMatrix(viewport, item) {
    var raw = Array.isArray(item && item.transform) ? item.transform : [1, 0, 0, 1, 0, 0];
    if (viewport && Array.isArray(viewport.transform) && global.pdfjsLib && global.pdfjsLib.Util) {
      try {
        return global.pdfjsLib.Util.transform(viewport.transform, raw);
      } catch (_e) {}
    }
    return raw.slice();
  }

  function itemFontSize(item, matrix, scale) {
    var a = num(matrix && matrix[0], 0);
    var b = num(matrix && matrix[1], 0);
    var c = num(matrix && matrix[2], 0);
    var d = num(matrix && matrix[3], 0);
    var fromMatrix = Math.max(Math.hypot(c, d), Math.hypot(a, b));
    var fromItem = Math.abs(num(item && item.height, 0) * (scale || 1));
    return Math.max(1, fromMatrix || fromItem || 12);
  }

  function itemWidth(item, text, fontSize, scale) {
    var w = Math.abs(num(item && item.width, 0) * (scale || 1));
    if (w > 0) return w;
    return Math.max(1, str(text).length * fontSize * 0.52);
  }

  function normalizeItem(raw, idx, viewport, textStyles) {
    var text = str(raw && raw.str);
    if (!text) return null;
    var rawFontName = str(raw && raw.fontName);
    var fontInfo = rawFontName && textStyles ? (textStyles[rawFontName] || null) : null;
    var family = str(fontInfo && fontInfo.fontFamily) || rawFontName;
    var scale = viewportScale(viewport);
    var m = transformedMatrix(viewport, raw || {});
    var fontSize = itemFontSize(raw || {}, m, scale);
    var width = itemWidth(raw || {}, text, fontSize, scale);
    var height = Math.max(1, Math.abs(num(raw && raw.height, fontSize) * scale) || fontSize);
    var baselineX = num(m[4], 0);
    var baselineY = num(m[5], 0);
    var angle = Math.atan2(num(m[1], 0), num(m[0], 1));
    var rotate = Math.abs(angle) > 0.01 ? angle : 0;
    var top = baselineY - fontSize;
    var left = baselineX;
    return {
      index: idx,
      text: text,
      x: left,
      y: top,
      baselineX: baselineX,
      baselineY: baselineY,
      width: width,
      height: Math.max(height, fontSize),
      fontSize: fontSize,
      fontName: rawFontName,
      fontFamily: family,
      fontWeight: /bold|black|heavy|semibold/i.test(family + ' ' + rawFontName) ? '700' : '',
      fontStyle: /italic|oblique/i.test(family + ' ' + rawFontName) ? 'italic' : '',
      dir: str(raw && raw.dir) || 'ltr',
      hasEOL: !!(raw && raw.hasEOL),
      rotate: rotate,
      raw: raw || {}
    };
  }

  function sameLine(a, b, tolerance) {
    if (!a || !b) return false;
    var ay = a.baselineY != null ? a.baselineY : a.y;
    var by = b.baselineY != null ? b.baselineY : b.y;
    var tol = Math.max(tolerance || 3, Math.max(a.fontSize || 0, b.fontSize || 0, 12) * 0.36);
    return Math.abs(ay - by) <= tol;
  }

  function groupLines(items, opts) {
    opts = opts || {};
    var lineTol = num(opts.lineTolerance, 0) || 4;
    var sorted = (items || []).slice().sort(function(a, b) {
      var ay = a.baselineY != null ? a.baselineY : a.y;
      var by = b.baselineY != null ? b.baselineY : b.y;
      if (Math.abs(ay - by) > lineTol) return ay - by;
      return a.x - b.x;
    });
    var lines = [];
    sorted.forEach(function(item) {
      if (!item || !item.text) return;
      var placed = false;
      for (var i = lines.length - 1; i >= 0; i--) {
        var line = lines[i];
        if (!sameLine(line.anchor, item, lineTol)) continue;
        line.items.push(item);
        line.anchor.baselineY = (line.anchor.baselineY * (line.items.length - 1) + item.baselineY) / line.items.length;
        line.anchor.y = (line.anchor.y * (line.items.length - 1) + item.y) / line.items.length;
        placed = true;
        break;
      }
      if (!placed) {
        lines.push({
          anchor: Object.assign({}, item),
          items: [item]
        });
      }
    });

    lines.forEach(function(line) {
      line.items.sort(function(a, b) { return a.x - b.x; });
      reverseRtlRuns(line.items, lineTol);
      var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      var heights = [];
      line.items.forEach(function(it) {
        minX = Math.min(minX, it.x);
        minY = Math.min(minY, it.y);
        maxX = Math.max(maxX, it.x + it.width);
        maxY = Math.max(maxY, it.y + it.height);
        heights.push(it.height || it.fontSize || 0);
      });
      line.x = isFinite(minX) ? minX : 0;
      line.y = isFinite(minY) ? minY : 0;
      line.width = isFinite(maxX - minX) ? Math.max(0, maxX - minX) : 0;
      line.height = isFinite(maxY - minY) ? Math.max(1, maxY - minY) : median(heights, 12);
      line.baselineY = line.anchor.baselineY || line.y;
      line.avgHeight = median(heights, line.height || 12);
    });

    lines.sort(function(a, b) {
      if (Math.abs(a.y - b.y) > lineTol) return a.y - b.y;
      return a.x - b.x;
    });
    return lines;
  }

  function reverseRtlRuns(items, lineTol) {
    var i = 0;
    while (i < items.length) {
      if (!items[i] || items[i].dir !== 'rtl') {
        i++;
        continue;
      }
      var j = i + 1;
      while (j < items.length) {
        var cur = items[j];
        if (!cur || !sameLine(items[i], cur, lineTol)) break;
        var neutral = !cur.text.trim();
        if (cur.dir === 'rtl' || neutral) {
          j++;
          continue;
        }
        break;
      }
      var lo = i;
      var hi = j - 1;
      while (lo < hi) {
        var tmp = items[lo];
        items[lo] = items[hi];
        items[hi] = tmp;
        lo++;
        hi--;
      }
      i = j;
    }
  }

  function textEndsWithSpace(text) {
    return /\s$/.test(str(text));
  }
  function textStartsWithSpace(text) {
    return /^\s/.test(str(text));
  }

  function shouldInsertSpace(prev, cur, opts) {
    opts = opts || {};
    if (!prev || !cur) return false;
    if (textEndsWithSpace(prev.text) || textStartsWithSpace(cur.text)) return false;
    var gap = cur.x - (prev.x + prev.width);
    var size = Math.max(prev.fontSize || 0, cur.fontSize || 0, 12);
    var threshold = opts.wordGapThreshold != null ? Number(opts.wordGapThreshold) : Math.max(1.5, size * 0.22);
    return gap > threshold;
  }

  function lineSeparator(prevLine, curLine, metrics) {
    if (!prevLine || !curLine) return '';
    var prevLast = prevLine.items && prevLine.items.length ? prevLine.items[prevLine.items.length - 1] : null;
    var prevText = prevLast ? prevLast.text : '';
    if (prevLast && prevLast.hasEOL) return '\n';
    var gap = curLine.y - (prevLine.y + prevLine.height);
    var para = Math.max(metrics.medianLineGap * 1.25, metrics.medianHeight * 0.9);
    if (gap > para) return '\n';
    return textEndsWithSpace(prevText) ? '' : ' ';
  }

  function computeLineMetrics(lines) {
    var heights = [];
    var gaps = [];
    for (var i = 0; i < lines.length; i++) {
      heights.push(lines[i].avgHeight || lines[i].height || 0);
      if (i > 0) gaps.push(Math.max(0, lines[i].y - (lines[i - 1].y + lines[i - 1].height)));
    }
    return {
      medianHeight: median(heights, 12),
      medianLineGap: median(gaps, median(heights, 12) * 0.45)
    };
  }

  function addHiddenSeparator(builder, sep, pageIndex, reason) {
    if (!sep) return null;
    return builder.addRun(sep, {
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
      source: {
        synthetic: true,
        kind: 'pdf-separator',
        reason: reason || 'separator',
        sourcePageIndex: pageIndex
      },
      merge: false
    });
  }

  function visibleRunStyle(item) {
    return {
      fontFamily: item.fontFamily || item.fontName || '',
      fontSize: item.fontSize ? item.fontSize.toFixed(3) + 'px' : '',
      fontWeight: item.fontWeight || '',
      fontStyle: item.fontStyle || '',
      lineHeight: item.height ? item.height.toFixed(3) + 'px' : '',
      direction: item.dir || 'ltr',
      whiteSpace: 'pre'
    };
  }

  function addVisibleItem(builder, item, pageIndex) {
    var layout = {
      mode: 'fixed',
      x: item.x,
      y: item.y,
      width: Math.max(0.1, item.width || 0),
      height: Math.max(1, item.height || item.fontSize || 1),
      fitWidth: Math.max(0.1, item.width || 0)
    };
    if (item.rotate) layout.transform = 'rotate(' + item.rotate.toFixed(6) + 'rad)';
    return builder.addRun(item.text, {
      style: visibleRunStyle(item),
      rects: [{
        x: item.x,
        y: item.y,
        width: layout.width,
        height: layout.height
      }],
      layout: layout,
      source: {
        sourcePageIndex: pageIndex,
        textItemIndex: item.index,
        fontName: item.fontName || '',
        pdfjs: true
      },
      merge: false
    });
  }

  function pdfRunText(run) {
    return str(run && run.text);
  }

  function isVisiblePdfRun(run) {
    return !!(run &&
      run.layout &&
      run.layout.mode === 'fixed' &&
      !(run.source && run.source.synthetic) &&
      run.source &&
      run.source.pdfjs &&
      pdfRunText(run).trim());
  }

  function pdfRunBox(run) {
    var layout = run && run.layout || {};
    var x = num(layout.x, 0);
    var y = num(layout.y, 0);
    var width = Math.max(0, num(layout.width, 0));
    var height = Math.max(1, num(layout.height, 1));
    return {
      x: x,
      y: y,
      width: width,
      height: height,
      right: x + width,
      bottom: y + height,
      cy: y + height / 2
    };
  }

  function pdfRunsShareLine(a, b, opts) {
    if (!a || !b) return false;
    var factor = num(opts && opts.lineToleranceFactor, 0.55) || 0.55;
    return Math.abs(num(a.cy, 0) - num(b.cy, 0)) <= Math.max(2, Math.min(num(a.height, 0), num(b.height, 0)) * factor);
  }

  function pdfRunTransform(run) {
    return str(run && run.layout && run.layout.transform);
  }

  function pdfRunsCompatibleForMerge(a, b) {
    if (!a || !b) return false;
    return pdfRunTransform(a.run) === pdfRunTransform(b.run);
  }

  function pdfSeparatorBetween(runs, leftOrder, rightOrder) {
    var out = '';
    var hasLineBreak = false;
    var start = Math.min(leftOrder, rightOrder) + 1;
    var end = Math.max(leftOrder, rightOrder);
    for (var i = start; i < end; i++) {
      var run = runs[i];
      if (!run || !(run.source && run.source.synthetic)) continue;
      var kind = str(run.source && run.source.kind);
      if (!/separator/i.test(kind)) continue;
      out += pdfRunText(run);
      if (/\n/.test(pdfRunText(run))) hasLineBreak = true;
    }
    return { text: out, hasLineBreak: hasLineBreak };
  }

  function pdfBoundaryNeedsSpace(prevText, nextText, gap, separatorText, opts) {
    if (/\s/.test(str(separatorText))) {
      if (/\s$/.test(str(prevText)) || /^\s/.test(str(nextText))) return false;
      return true;
    }
    var insertGap = num(opts && opts.insertSpaceGapPx, 1.25);
    if (gap < insertGap) return false;
    if (/\s$/.test(str(prevText)) || /^\s/.test(str(nextText))) return false;
    if (/^[\u060C,.\u061B;:!?\]\)]/.test(str(nextText))) return false;
    if (/[\[\(]$/.test(str(prevText))) return false;
    return true;
  }

  function unionPdfRunBoxes(items) {
    var left = Infinity;
    var top = Infinity;
    var right = -Infinity;
    var bottom = -Infinity;
    for (var i = 0; i < items.length; i++) {
      var box = items[i] && items[i].box;
      if (!box) continue;
      left = Math.min(left, box.x);
      top = Math.min(top, box.y);
      right = Math.max(right, box.right);
      bottom = Math.max(bottom, box.bottom);
    }
    if (!isFinite(left) || !isFinite(top) || !isFinite(right) || !isFinite(bottom)) return null;
    return {
      x: left,
      y: top,
      width: Math.max(1, right - left),
      height: Math.max(1, bottom - top)
    };
  }

  function clonePdfRunSource(source) {
    return Object.assign({}, source || {});
  }

  function pdfWordRangesForText(text) {
    var out = [];
    var value = str(text).replace(/\u00a0/g, ' ');
    var re = /\S+/g;
    var match;
    while ((match = re.exec(value))) {
      out.push({ start: match.index, end: match.index + match[0].length, text: match[0] });
    }
    return out;
  }

  function pdfRunDirection(run) {
    return str(run && run.style && run.style.direction || '').toLowerCase();
  }

  function pdfWordBoxForRange(item, range) {
    var box = item && item.box;
    var run = item && item.run;
    if (!box || !range) return null;
    var text = pdfRunText(run).replace(/\u00a0/g, ' ');
    var total = Math.max(1, text.length);
    var start = clamp(range.start, 0, total);
    var end = clamp(range.end, start, total);
    var width = Math.max(0, num(box.width, 0));
    var wordWidth = Math.max(0.25, width * Math.max(0, end - start) / total);
    var rtl = /^rtl$/i.test(pdfRunDirection(run));
    var x = rtl
      ? num(box.x, 0) + width * Math.max(0, total - end) / total
      : num(box.x, 0) + width * start / total;
    return {
      x: x,
      y: num(box.y, 0),
      width: wordWidth,
      height: Math.max(1, num(box.height, 1)),
      right: x + wordWidth,
      bottom: num(box.y, 0) + Math.max(1, num(box.height, 1)),
      cy: num(box.y, 0) + Math.max(1, num(box.height, 1)) / 2
    };
  }

  function collectPdfWordBoxes(visible) {
    var words = [];
    for (var i = 0; i < (visible || []).length; i++) {
      var item = visible[i];
      var ranges = pdfWordRangesForText(pdfRunText(item && item.run));
      for (var ri = 0; ri < ranges.length; ri++) {
        var box = pdfWordBoxForRange(item, ranges[ri]);
        if (!box || box.width <= 0.25 || box.height <= 0.25) continue;
        words.push({
          text: ranges[ri].text,
          box: box,
          run: item.run,
          order: item.order,
          wordIndex: ri,
          textStart: ranges[ri].start,
          textEnd: ranges[ri].end
        });
      }
    }
    return words;
  }

  function estimatePdfWordGap(visible, opts) {
    var words = collectPdfWordBoxes(visible);
    if (words.length < 2) return 0;
    var sorted = words.slice().sort(function(a, b) {
      return num(a.box.y, 0) - num(b.box.y, 0) || num(a.box.x, 0) - num(b.box.x, 0);
    });
    var lines = [];
    for (var i = 0; i < sorted.length; i++) {
      var item = sorted[i];
      var line = null;
      for (var li = 0; li < lines.length; li++) {
        if (pdfRunsShareLine(lines[li].anchor.box, item.box, opts)) {
          line = lines[li];
          break;
        }
      }
      if (!line) {
        line = { anchor: item, items: [] };
        lines.push(line);
      }
      line.items.push(item);
    }

    var gaps = [];
    for (var l = 0; l < lines.length; l++) {
      var items = lines[l].items.slice().sort(function(a, b) {
        return num(a.box.x, 0) - num(b.box.x, 0);
      });
      for (var j = 1; j < items.length; j++) {
        var gap = Math.max(0, items[j].box.x - items[j - 1].box.right);
        if (gap > 0) gaps.push(gap);
      }
    }
    return median(gaps, 0);
  }

  function mergePdfRunCluster(cluster, opts, allRuns) {
    if (!cluster || cluster.length < 2) return cluster && cluster[0] ? cluster[0].run : null;
    var logical = cluster.slice().sort(function(a, b) {
      return num(a.order, 0) - num(b.order, 0);
    });
    var union = unionPdfRunBoxes(logical);
    if (!union) return logical[0].run;

    var text = '';
    var rects = [];
    var mergedFrom = [];
    for (var i = 0; i < logical.length; i++) {
      var item = logical[i];
      var run = item.run;
      if (i > 0) {
        var prev = logical[i - 1];
        var sep = pdfSeparatorBetween(allRuns, prev.order, item.order);
        var gap = Math.max(0, Math.max(item.box.x - prev.box.right, prev.box.x - item.box.right));
        if (pdfBoundaryNeedsSpace(text, run.text, gap, sep.text, opts)) text += ' ';
      }
      text += pdfRunText(run);
      if (Array.isArray(run.rects)) {
        for (var ri = 0; ri < run.rects.length; ri++) rects.push(Object.assign({}, run.rects[ri]));
      }
      mergedFrom.push({
        id: run.id || '',
        start: run.start,
        end: run.end,
        textLength: pdfRunText(run).length,
        source: clonePdfRunSource(run.source)
      });
    }

    var first = logical[0].run;
    var source = clonePdfRunSource(first.source);
    source.merged = true;
    source.mergedRunCount = logical.length;
    source.mergedFrom = mergedFrom;
    source.kind = source.kind || 'pdfMergedLineRun';
    source.pdfjs = true;

    return {
      id: 'pdf-line-merged-' + logical.map(function(item) {
        return item.run.id || item.order;
      }).join('--'),
      text: text,
      start: first.start,
      end: first.start + text.length,
      style: first.style || {},
      layout: {
        mode: 'fixed',
        x: union.x,
        y: union.y,
        width: union.width,
        height: union.height,
        fitWidth: union.width
      },
      rects: rects.length ? rects : [{
        x: union.x,
        y: union.y,
        width: union.width,
        height: union.height
      }],
      source: source
    };
  }

  function buildPdfRunClusters(visible, opts, allRuns) {
    visible.sort(function(a, b) {
      return num(a.box.y, 0) - num(b.box.y, 0) || num(a.box.x, 0) - num(b.box.x, 0);
    });
    var lines = [];
    for (var i = 0; i < visible.length; i++) {
      var item = visible[i];
      var line = null;
      for (var li = 0; li < lines.length; li++) {
        if (pdfRunsShareLine(lines[li].anchor.box, item.box, opts)) {
          line = lines[li];
          break;
        }
      }
      if (!line) {
        line = { anchor: item, items: [] };
        lines.push(line);
      }
      line.items.push(item);
    }

    var pageWordGap = num(opts && opts.wordGapPx, 0);
    if (!isFinite(pageWordGap) || pageWordGap <= 0) {
      pageWordGap = num(opts && opts.fallbackWordGapPx, 6) || 6;
    }
    var wordGapMultiplier = num(opts && opts.wordGapMultiplier, 1.5);
    if (!isFinite(wordGapMultiplier) || wordGapMultiplier <= 0) wordGapMultiplier = 1.5;
    var threshold = pageWordGap * wordGapMultiplier;
    if (opts) {
      opts.wordGapPx = pageWordGap;
      opts.wordGapMultiplier = wordGapMultiplier;
      opts.mergeGapThresholdPx = threshold;
    }

    var clusters = [];
    for (var l = 0; l < lines.length; l++) {
      var visual = lines[l].items.slice().sort(function(a, b) {
        return num(a.box.x, 0) - num(b.box.x, 0);
      });
      if (!visual.length) continue;
      var cluster = [visual[0]];
      for (var vi = 1; vi < visual.length; vi++) {
        var prev = visual[vi - 1];
        var cur = visual[vi];
        var gap = Math.max(0, cur.box.x - prev.box.right);
        var sep = pdfSeparatorBetween(allRuns, prev.order, cur.order);
        if (!sep.hasLineBreak && gap <= threshold && pdfRunsCompatibleForMerge(prev, cur)) {
          cluster.push(cur);
        } else {
          clusters.push(cluster);
          cluster = [cur];
        }
      }
      clusters.push(cluster);
    }
    return clusters;
  }

  function mergeNearbyPdfRunsOnLines(page, opts) {
    if (!page || !Array.isArray(page.blocks)) return { mergedCount: 0, mergeGapThresholdPx: 0 };
    opts = Object.assign({
      enabled: true,
      lineToleranceFactor: 0.55,
      insertSpaceGapPx: 1.25,
      fallbackWordGapPx: 6,
      wordGapMultiplier: 1.5
    }, opts && (opts.pdfRunMerge || opts.runMerge || {}));
    if (opts.enabled === false) return { mergedCount: 0, mergeGapThresholdPx: 0 };

    var totalMerged = 0;
    for (var bi = 0; bi < page.blocks.length; bi++) {
      var block = page.blocks[bi];
      var runs = Array.isArray(block && block.runs) ? block.runs : [];
      if (runs.length < 2) continue;
      var visible = [];
      var runToCluster = new Map();
      for (var i = 0; i < runs.length; i++) {
        if (!isVisiblePdfRun(runs[i])) continue;
        visible.push({ run: runs[i], order: i, box: pdfRunBox(runs[i]) });
      }
      if (visible.length < 2) continue;

      var mergeOpts = Object.assign({}, opts);
      var measuredWordGap = estimatePdfWordGap(visible, mergeOpts);
      mergeOpts.wordGapPx = measuredWordGap || num(mergeOpts.fallbackWordGapPx, 6) || 6;
      var clusters = buildPdfRunClusters(visible, mergeOpts, runs);
      var blockMerged = 0;
      for (var ci = 0; ci < clusters.length; ci++) {
        if (!clusters[ci] || clusters[ci].length < 2) continue;
        var mergedRun = mergePdfRunCluster(clusters[ci], mergeOpts, runs);
        if (!mergedRun) continue;
        blockMerged += clusters[ci].length - 1;
        var firstRun = clusters[ci].slice().sort(function(a, b) {
          return num(a.order, 0) - num(b.order, 0);
        })[0].run;
        for (var mi = 0; mi < clusters[ci].length; mi++) {
          runToCluster.set(clusters[ci][mi].run, {
            mergedRun: mergedRun,
            firstRun: firstRun
          });
        }
      }
      if (!blockMerged) continue;

      var out = [];
      for (var ri = 0; ri < runs.length; ri++) {
        var run = runs[ri];
        var info = runToCluster.get(run);
        if (info) {
          if (run === info.firstRun) out.push(info.mergedRun);
          continue;
        }
        if (run && run.source && run.source.synthetic) {
          var prevInfo = ri > 0 ? runToCluster.get(runs[ri - 1]) : null;
          var nextInfo = ri + 1 < runs.length ? runToCluster.get(runs[ri + 1]) : null;
          if (prevInfo && nextInfo && prevInfo.mergedRun === nextInfo.mergedRun) continue;
        }
        out.push(run);
      }
      block.runs = out;
      totalMerged += blockMerged;
      page.source = Object.assign({}, page.source || {}, {
        pdfMergedRunCount: (Number(page.source && page.source.pdfMergedRunCount) || 0) + blockMerged,
        pdfRunMergeGapThresholdPx: mergeOpts.mergeGapThresholdPx || 0,
        pdfRunMergeWordGapPx: mergeOpts.wordGapPx || 0
      });
    }
    if (totalMerged && global.CanonicalModel && typeof global.CanonicalModel.recomputePageText === 'function') {
      global.CanonicalModel.recomputePageText(page);
    }
    return {
      mergedCount: totalMerged,
      mergeGapThresholdPx: page.source && page.source.pdfRunMergeGapThresholdPx || 0
    };
  }

  function pageFromTextItems(items, pageIndex, viewport, opts) {
    requireDeps();
    opts = opts || {};
    var textStyles = opts.textStyles || opts.styles || {};
    var normalized = (items || []).map(function(it, idx) {
      return normalizeItem(it, idx, viewport, textStyles);
    }).filter(function(it) { return !!(it && it.text); });
    var lines = groupLines(normalized, opts);
    var metrics = computeLineMetrics(lines);
    var builder = new global.CanonicalBuilder.Builder(Object.assign({
      format: 'pdf',
      parser: 'canonical-pdfjs-extractor'
    }, opts.meta || {}));
    var pageWidth = Math.max(1, num(viewport && viewport.width, opts.pageWidth || 612));
    var pageHeight = Math.max(1, num(viewport && viewport.height, opts.pageHeight || 792));

    builder.startPage({
      layout: {
        mode: 'fixed',
        width: pageWidth,
        height: pageHeight,
        pageIndex: pageIndex
      },
      source: {
        extractor: 'canonical-pdfjs',
        sourcePageIndex: pageIndex
      }
    });
    builder.startBlock({
      type: 'pdfLayer',
      layout: {
        mode: 'fixed',
        x: 0,
        y: 0,
        width: pageWidth,
        height: pageHeight
      },
      style: {
        direction: 'ltr',
        textAlign: 'left',
        whiteSpace: 'normal'
      },
      source: {
        sourcePageIndex: pageIndex,
        kind: 'pdf-fixed-text-layer'
      }
    });

    for (var li = 0; li < lines.length; li++) {
      if (li > 0) addHiddenSeparator(builder, lineSeparator(lines[li - 1], lines[li], metrics), pageIndex, 'line');
      var line = lines[li];
      var prev = null;
      var explicitSpaceSincePrev = false;
      for (var ii = 0; ii < line.items.length; ii++) {
        var item = line.items[ii];
        if (!item || !item.text) continue;
        if (!item.text.trim()) {
          if (!textEndsWithSpace(builder.page && builder.page.text)) {
            addHiddenSeparator(builder, ' ', pageIndex, 'pdf-space-item');
          }
          explicitSpaceSincePrev = true;
          continue;
        }
        if (!explicitSpaceSincePrev && shouldInsertSpace(prev, item, opts)) {
          addHiddenSeparator(builder, ' ', pageIndex, 'word-gap');
        }
        addVisibleItem(builder, item, pageIndex);
        prev = item;
        explicitSpaceSincePrev = false;
      }
    }
    builder.endBlock();

    var doc = builder.finish();
    var page = doc.pages[0];
    var mergeInfo = mergeNearbyPdfRunsOnLines(page, opts);
    page.index = pageIndex;
    page.id = 'pdf-page-' + pageIndex;
    page.layout = Object.assign({}, page.layout || {}, {
      mode: 'fixed',
      width: pageWidth,
      height: pageHeight,
      pageIndex: pageIndex
    });
    page.source = Object.assign({}, page.source || {}, {
      extractor: 'canonical-pdfjs',
      textItemCount: normalized.length,
      lineCount: lines.length,
      mergedRunCount: mergeInfo.mergedCount || 0,
      runMergeGapThresholdPx: mergeInfo.mergeGapThresholdPx || 0
    });
    if (global.TrankitChunkDebugger &&
        typeof global.TrankitChunkDebugger.applyLookupChunkParagraphBreaks === 'function') {
      global.TrankitChunkDebugger.applyLookupChunkParagraphBreaks(page, {
        sourceKind: 'pdf-geometry-chunk-paragraph'
      });
    }
    global.CanonicalModel.assertPageInvariant(page, 'pdf page ' + pageIndex);
    return page;
  }

  async function pageFromPdfJsPage(pdfPage, pageIndex, opts) {
    opts = opts || {};
    if (!pdfPage) throw new Error('Invalid PDF.js page');
    var viewport = pdfPage.getViewport ? pdfPage.getViewport({ scale: opts.scale || 1 }) : null;
    var content = await pdfPage.getTextContent({
      normalizeWhitespace: false,
      disableCombineTextItems: false
    });
    var items = content && Array.isArray(content.items) ? content.items : [];
    return pageFromTextItems(items, pageIndex, viewport, Object.assign({}, opts, {
      textStyles: content && content.styles ? content.styles : {}
    }));
  }

  async function documentFromPdfJsDocument(pdfDoc, opts) {
    requireDeps();
    opts = opts || {};
    if (!pdfDoc || typeof pdfDoc.numPages !== 'number') throw new Error('Invalid PDF.js document');
    var doc = global.CanonicalModel.makeDocument({
      meta: Object.assign({
        format: 'pdf',
        parser: 'canonical-pdfjs-extractor',
        pageCount: pdfDoc.numPages
      }, opts.meta || {}),
      pages: [],
      source: {
        extractor: 'canonical-pdfjs',
        clientSide: true
      }
    });

    for (var pageNo = 1; pageNo <= pdfDoc.numPages; pageNo++) {
      if (typeof opts.onProgress === 'function') {
        opts.onProgress({ pageNumber: pageNo, pageIndex: pageNo - 1, pageCount: pdfDoc.numPages });
      }
      var pdfPage = await pdfDoc.getPage(pageNo);
      var page = await pageFromPdfJsPage(pdfPage, pageNo - 1, opts);
      doc.pages.push(page);
    }
    global.CanonicalModel.validateDocument(doc, { throwOnError: true });
    return doc;
  }

  function pageDimensions(doc) {
    var pages = doc && Array.isArray(doc.pages) ? doc.pages : [];
    return pages.map(function(page) {
      var layout = page && page.layout || {};
      return {
        width: clamp(layout.width, 1, 100000),
        height: clamp(layout.height, 1, 100000)
      };
    });
  }

  global.CanonicalPdfExtractor = {
    normalizeItem: normalizeItem,
    groupLines: groupLines,
    shouldInsertSpace: shouldInsertSpace,
    pageFromTextItems: pageFromTextItems,
    pageFromPdfJsPage: pageFromPdfJsPage,
    documentFromPdfJsDocument: documentFromPdfJsDocument,
    pageDimensions: pageDimensions
  };
})(window);
