import { num, str } from './frame-lifecycle.mjs';
import {
  getRangeRects,
  rectFullyInsideViewport,
  rectToViewportLocal,
  textNodeIsVisible
} from './search-overlay.mjs';
import { nodeFilterConst } from './text-extraction.mjs';
export function percentRect(rect, viewport) {
  var w = Math.max(1, num(viewport && viewport.width, 1));
  var h = Math.max(1, num(viewport && viewport.height, 1));
  return {
    x: num(rect && rect.left, 0) / w,
    y: num(rect && rect.top, 0) / h,
    width: num(rect && rect.width, 0) / w,
    height: num(rect && rect.height, 0) / h
  };
}
export function makeRectRun(fragment) {
  var rect = fragment.rect || {};
  if (fragment.hidden) {
    return {
      id: fragment.id,
      text: fragment.text,
      start: fragment.lookupStart,
      end: fragment.lookupEnd,
      style: {},
      layout: {
        mode: 'fixed',
        x: -99999,
        y: -99999,
        width: 0,
        height: 0,
        skipFitWidth: true
      },
      rects: [],
      source: {
        kind: fragment.sourceKind || 'webSnapshotWhitespace',
        synthetic: true,
        hidden: true,
        nodePath: fragment.nodePath,
        nodeStart: fragment.nodeStart,
        nodeEnd: fragment.nodeEnd,
        parentTag: fragment.parentTag,
        parentId: fragment.parentId,
        parentClass: fragment.parentClass,
        domAncestorChain: fragment.domAncestorChain || [],
        domDivPath: fragment.domDivPath || [],
        domDivPathKey: fragment.domDivPathKey || '',
        domParentPath: fragment.domParentPath || '',
        domParentKey: fragment.domParentKey || '',
        domBlockKey: fragment.domBlockKey || '',
        domBlockPath: fragment.domBlockPath || '',
        domContainerKey: fragment.domContainerKey || '',
        domContainerPath: fragment.domContainerPath || '',
        domSemanticKind: fragment.domSemanticKind || ''
      }
    };
  }
  return {
    id: fragment.id,
    text: fragment.text,
    start: fragment.lookupStart,
    end: fragment.lookupEnd,
    style: fragment.style || {},
    layout: {
      mode: 'fixed',
      x: num(rect.left, 0),
      y: num(rect.top, 0),
      width: Math.max(1, num(rect.width, 1)),
      height: Math.max(1, num(rect.height, 1))
    },
    rects: [
      {
        x: num(rect.left, 0),
        y: num(rect.top, 0),
        width: Math.max(1, num(rect.width, 1)),
        height: Math.max(1, num(rect.height, 1))
      }
    ],
    source: {
      kind: 'webSnapshotRectSlice',
      exactWordRectRun: fragment.sourceKind === 'webSnapshotWordRect',
      nodePath: fragment.nodePath,
      nodeStart: fragment.nodeStart,
      nodeEnd: fragment.nodeEnd,
      parentTag: fragment.parentTag,
      parentId: fragment.parentId,
      parentClass: fragment.parentClass,
      domAncestorChain: fragment.domAncestorChain || [],
      domDivPath: fragment.domDivPath || [],
      domDivPathKey: fragment.domDivPathKey || '',
      domParentPath: fragment.domParentPath || '',
      domParentKey: fragment.domParentKey || '',
      domBlockKey: fragment.domBlockKey || '',
      domBlockPath: fragment.domBlockPath || '',
      domContainerKey: fragment.domContainerKey || '',
      domContainerPath: fragment.domContainerPath || '',
      domSemanticKind: fragment.domSemanticKind || '',
      viewportRect: rect,
      documentRect: fragment.documentRect || rect,
      percentRect: percentRect(rect, fragment.viewport)
    }
  };
}
export function makeSeparatorRun(index, start, text, kind) {
  var sepText = text == null ? '\n' : str(text);
  if (!sepText) return null;
  return {
    id: 'web-rect-sep-' + index,
    text: sepText,
    start: start,
    end: start + sepText.length,
    style: {},
    layout: {
      mode: 'fixed',
      x: 0,
      y: 0,
      width: 0,
      height: 0
    },
    rects: [],
    source: {
      kind: 'separator',
      separatorKind: kind || 'line',
      synthetic: true
    }
  };
}
export function isVisibleWebRectRun(run) {
  return !!(
    run &&
    run.layout &&
    run.layout.mode === 'fixed' &&
    !(run.source && run.source.synthetic) &&
    String((run.source && run.source.kind) || '') === 'webSnapshotRectSlice' &&
    str(run.text).trim()
  );
}
export function webRunBox(run) {
  var layout = (run && run.layout) || {};
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
export function webRunsShareLine(a, b, opts) {
  if (!a || !b) return false;
  var factor = num(opts && opts.lineToleranceFactor, 0.55) || 0.55;
  return (
    Math.abs(num(a.cy, 0) - num(b.cy, 0)) <=
    Math.max(2, Math.min(num(a.height, 0), num(b.height, 0)) * factor)
  );
}
export function webRunDomAncestrySignature(source) {
  var chain = Array.isArray(source && source.domAncestorChain) ? source.domAncestorChain : [];
  return chain
    .map(function (item) {
      return str(item && (item.path || item.key));
    })
    .filter(Boolean)
    .join('>');
}
export function webRunsShareAvailableDomAncestry(a, b) {
  var left = (a && a.run && a.run.source) || {};
  var right = (b && b.run && b.run.source) || {};
  var keys = ['domBlockPath', 'domContainerPath', 'domDivPathKey'];
  for (var i = 0; i < keys.length; i++) {
    var lv = str(left[keys[i]]);
    var rv = str(right[keys[i]]);
    if (lv && rv && lv !== rv) return false;
  }
  var leftSig = webRunDomAncestrySignature(left);
  var rightSig = webRunDomAncestrySignature(right);
  if (leftSig && rightSig && leftSig !== rightSig) return false;
  return true;
}
export function medianRunGap(values) {
  var nums = (values || [])
    .filter(function (v) {
      return isFinite(Number(v));
    })
    .map(function (v) {
      return Number(v);
    })
    .sort(function (a, b) {
      return a - b;
    });
  if (!nums.length) return 0;
  return nums[Math.floor(nums.length / 2)];
}
export function webBoundaryNeedsSpace(prevText, nextText, gap, opts) {
  var insertGap = num(opts && opts.insertSpaceGapPx, 1.25);
  if (gap < insertGap) return false;
  if (/\s$/.test(str(prevText)) || /^\s/.test(str(nextText))) return false;
  if (/^[\u060C,.\u061B;:!?\]\)]/.test(str(nextText))) return false;
  if (/[\[\(]$/.test(str(prevText))) return false;
  return true;
}
export function unionWebRunBoxes(items) {
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
export function cloneWebRunSource(source) {
  return Object.assign({}, source || {});
}
export function mergeWebRectRunCluster(cluster, opts) {
  if (!cluster || cluster.length < 2) return cluster && cluster[0] ? cluster[0].run : null;
  var logical = cluster.slice().sort(function (a, b) {
    return num(a.order, 0) - num(b.order, 0);
  });
  var union = unionWebRunBoxes(logical);
  if (!union) return logical[0].run;
  var text = '';
  var rects = [];
  var mergedFrom = [];
  var styleSegments = [];
  for (var i = 0; i < logical.length; i++) {
    var item = logical[i];
    var run = item.run;
    if (i > 0) {
      var prev = logical[i - 1];
      var gap = Math.max(0, Math.max(item.box.x - prev.box.right, prev.box.x - item.box.right));
      if (webBoundaryNeedsSpace(text, run.text, gap, opts)) text += ' ';
    }
    var runText = str(run.text);
    var pieceStart = text.length;
    text += runText;
    var pieceEnd = text.length;
    if (pieceEnd > pieceStart) {
      styleSegments.push({
        start: pieceStart,
        end: pieceEnd,
        style: Object.assign({}, run.style || {})
      });
    }
    if (Array.isArray(run.rects)) {
      for (var ri = 0; ri < run.rects.length; ri++) rects.push(Object.assign({}, run.rects[ri]));
    }
    mergedFrom.push({
      id: run.id || '',
      start: run.start,
      end: run.end,
      localStart: pieceStart,
      localEnd: pieceEnd,
      textLength: runText.length,
      style: Object.assign({}, run.style || {}),
      source: cloneWebRunSource(run.source)
    });
  }
  var first = logical[0].run;
  var source = cloneWebRunSource(first.source);
  source.merged = true;
  source.mergedRunCount = logical.length;
  source.mergedFrom = mergedFrom;
  source.styleSegments = styleSegments.map(function (seg) {
    return {
      start: seg.start,
      end: seg.end,
      style: Object.assign({}, seg.style || {})
    };
  });
  source.viewportRect = {
    left: union.x,
    top: union.y,
    right: union.x + union.width,
    bottom: union.y + union.height,
    width: union.width,
    height: union.height
  };
  return {
    id:
      'web-rect-merged-' +
      logical
        .map(function (item) {
          return item.run.id || item.order;
        })
        .join('--'),
    text: text,
    start: first.start,
    end: first.start + text.length,
    style: {},
    styleSegments: styleSegments,
    layout: {
      mode: 'fixed',
      x: union.x,
      y: union.y,
      width: union.width,
      height: union.height
    },
    rects: rects.length
      ? rects
      : [
          {
            x: union.x,
            y: union.y,
            width: union.width,
            height: union.height
          }
        ],
    source: source
  };
}
export function buildWebRectRunClusters(visible, opts) {
  var lines = [];
  visible.sort(function (a, b) {
    return num(a.box.y, 0) - num(b.box.y, 0) || num(a.box.x, 0) - num(b.box.x, 0);
  });
  for (var i = 0; i < visible.length; i++) {
    var item = visible[i];
    var line = null;
    for (var li = 0; li < lines.length; li++) {
      if (webRunsShareLine(lines[li].anchor.box, item.box, opts)) {
        line = lines[li];
        break;
      }
    }
    if (!line) {
      line = {
        anchor: item,
        items: []
      };
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
    var visual = lines[l].items.slice().sort(function (a, b) {
      return num(a.box.x, 0) - num(b.box.x, 0);
    });
    if (!visual.length) continue;
    var cluster = [visual[0]];
    for (var vi = 1; vi < visual.length; vi++) {
      var gap = Math.max(0, visual[vi].box.x - visual[vi - 1].box.right);
      if (gap <= threshold && webRunsShareAvailableDomAncestry(visual[vi - 1], visual[vi])) {
        cluster.push(visual[vi]);
      } else {
        clusters.push(cluster);
        cluster = [visual[vi]];
      }
    }
    clusters.push(cluster);
  }
  return clusters;
}
export function recomputeRunOffsets(runs) {
  var text = '';
  for (var i = 0; i < runs.length; i++) {
    runs[i].start = text.length;
    text += str(runs[i].text);
    runs[i].end = text.length;
  }
  return text;
}
export function wordRangesForText(text) {
  var out = [];
  var re = /\S+/g;
  var value = str(text);
  var match;
  while ((match = re.exec(value))) {
    out.push({
      start: match.index,
      end: match.index + match[0].length,
      text: match[0]
    });
  }
  return out;
}
export function collectVisibleWordBoxes(state, viewport) {
  var doc = state && state.doc;
  var win = state && state.win;
  if (!doc || !win || !doc.body || !viewport) return [];
  var walker = doc.createTreeWalker(doc.body, nodeFilterConst(win, 'SHOW_TEXT', 4), {
    acceptNode: function (node) {
      return textNodeIsVisible(node, win, doc)
        ? nodeFilterConst(win, 'FILTER_ACCEPT', 1)
        : nodeFilterConst(win, 'FILTER_REJECT', 2);
    }
  });
  var words = [];
  var node;
  while ((node = walker.nextNode())) {
    var text = str(node && node.nodeValue).replace(/\u00a0/g, ' ');
    var ranges = wordRangesForText(text);
    for (var i = 0; i < ranges.length; i++) {
      var range = ranges[i];
      var rects = getRangeRects(doc, node, range.start, range.end).filter(function (r) {
        return rectFullyInsideViewport(r, viewport);
      });
      for (var ri = 0; ri < rects.length; ri++) {
        var rect = rectToViewportLocal(rects[ri], viewport);
        if (!rect || rect.width <= 0.25 || rect.height <= 0.25) continue;
        words.push({
          text: range.text,
          box: {
            x: rect.left,
            y: rect.top,
            width: rect.width,
            height: rect.height,
            right: rect.left + rect.width,
            bottom: rect.top + rect.height,
            cy: rect.top + rect.height / 2
          }
        });
      }
    }
  }
  return words;
}
