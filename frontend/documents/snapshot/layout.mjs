import { num, str } from './frame-lifecycle.mjs';
import { frameLifecycleState } from './frame-lifecycle.state.mjs';
import {
  elementAncestry,
  getRangeRects,
  getWholeTextRects,
  graphemeBoundaries,
  nodePath,
  readRectTextStyle,
  rectFullyInsideViewport,
  rectIntersectsViewport,
  rectToViewportLocal,
  rectsShareLine,
  resolveVisibleViewport,
  textNodeIsVisible,
  unionRects
} from './search-overlay.mjs';
import { nodeFilterConst } from './text-extraction.mjs';
export function wordLikeSegmentRanges(text) {
  text = str(text).replace(/\u00a0/g, ' ');
  var ranges = [];
  if (!text) return ranges;
  if (frameLifecycleState.global.Intl && frameLifecycleState.global.Intl.Segmenter) {
    try {
      var segmenter = new frameLifecycleState.global.Intl.Segmenter(undefined, {
        granularity: 'word'
      });
      var iter = segmenter.segment(text);
      for (var item of iter) {
        var value = str(item && item.segment);
        if (!value) continue;
        ranges.push({
          start: item.index,
          end: item.index + value.length,
          text: value,
          whitespace: /^\s+$/.test(value)
        });
      }
      if (ranges.length) return ranges;
    } catch (_e) {}
  }
  var re = /\s+|\S+/g;
  var match;
  while ((match = re.exec(text))) {
    ranges.push({
      start: match.index,
      end: match.index + match[0].length,
      text: match[0],
      whitespace: /^\s+$/.test(match[0])
    });
  }
  return ranges;
}
export function rangeLineSlicesForTextNode(state, node, start, end, viewport) {
  var doc = state.doc;
  var text = str(node && node.nodeValue).replace(/\u00a0/g, ' ');
  start = Math.max(0, Math.min(text.length, Math.floor(num(start, 0))));
  end = Math.max(start, Math.min(text.length, Math.floor(num(end, start))));
  if (end <= start) return [];
  var clusters = graphemeBoundaries(text.slice(start, end));
  var lines = [];
  for (var i = 0; i < clusters.length; i++) {
    var g = clusters[i];
    if (!g || !g.text) continue;
    var gs = start + g.start;
    var ge = start + g.end;
    var rects = getRangeRects(doc, node, gs, ge).filter(function (r) {
      return rectFullyInsideViewport(r, viewport);
    });
    if (!rects.length) continue;
    for (var ri = 0; ri < rects.length; ri++) {
      var rect = rects[ri];
      var line = null;
      for (var li = 0; li < lines.length; li++) {
        if (rectsShareLine(lines[li].lineRect, rect)) {
          line = lines[li];
          break;
        }
      }
      if (!line) {
        line = {
          lineRect: rect,
          charRects: [],
          start: gs,
          end: ge
        };
        lines.push(line);
      }
      line.start = Math.min(line.start, gs);
      line.end = Math.max(line.end, ge);
      line.charRects.push(rect);
      line.lineRect = unionRects([line.lineRect, rect]) || rect;
    }
  }
  lines.sort(function (a, b) {
    return (
      num(a.lineRect.top, 0) - num(b.lineRect.top, 0) || num(a.lineRect.left, 0) - num(b.lineRect.left, 0)
    );
  });
  var out = [];
  for (var l = 0; l < lines.length; l++) {
    var info = lines[l];
    var lineRects = getRangeRects(doc, node, info.start, info.end).filter(function (r) {
      return rectFullyInsideViewport(r, viewport) && rectsShareLine(r, info.lineRect);
    });
    var rect = unionRects(lineRects.length ? lineRects : info.charRects);
    if (!rect) continue;
    out.push({
      start: info.start,
      end: info.end,
      rect: rect
    });
  }
  return out;
}
export function textFragmentsForTextNode(state, node, viewport) {
  var doc = state.doc;
  var win = state.win;
  var text = str(node && node.nodeValue).replace(/\u00a0/g, ' ');
  if (!text) return [];
  var wholeRects = getWholeTextRects(doc, node);
  if (
    !wholeRects.some(function (r) {
      return rectIntersectsViewport(r, viewport);
    })
  )
    return [];
  var parent = node.parentElement;
  var path = nodePath(node, doc);
  var style = readRectTextStyle(win, parent);
  var ancestry = elementAncestry(parent, doc);
  var ranges = wordLikeSegmentRanges(text);
  var out = [];
  for (var i = 0; i < ranges.length; i++) {
    var range = ranges[i];
    if (!range || range.end <= range.start) continue;
    if (range.whitespace) {
      out.push({
        id: 'web-rect-space-' + path.join('-') + '-' + range.start + '-' + range.end,
        text: range.text,
        nodeStart: range.start,
        nodeEnd: range.end,
        nodePath: path,
        hidden: true,
        sourceKind: 'webSnapshotWhitespace',
        parentTag: str(parent && parent.tagName).toLowerCase(),
        parentId: str(parent && parent.id).slice(0, 80),
        parentClass: str(parent && parent.className)
          .replace(/\s+/g, ' ')
          .trim()
          .slice(0, 160),
        domAncestorChain: ancestry.domAncestorChain,
        domDivPath: ancestry.domDivPath,
        domDivPathKey: ancestry.domDivPathKey,
        domParentPath: ancestry.domParentPath,
        domParentKey: ancestry.domParentKey,
        domBlockKey: ancestry.domBlockKey,
        domBlockPath: ancestry.domBlockPath,
        domContainerKey: ancestry.domContainerKey,
        domContainerPath: ancestry.domContainerPath,
        domSemanticKind: ancestry.domSemanticKind,
        rect: {
          left: 0,
          top: 0,
          right: 0,
          bottom: 0,
          width: 0,
          height: 0
        },
        documentRect: {
          left: 0,
          top: 0,
          right: 0,
          bottom: 0,
          width: 0,
          height: 0
        },
        style: style
      });
      continue;
    }
    var slices = rangeLineSlicesForTextNode(state, node, range.start, range.end, viewport);
    for (var si = 0; si < slices.length; si++) {
      var slice = slices[si];
      var sliceText = text.slice(slice.start, slice.end);
      if (!sliceText) continue;
      var viewportRect = rectToViewportLocal(slice.rect, viewport);
      out.push({
        id: 'web-rect-word-' + path.join('-') + '-' + slice.start + '-' + slice.end + '-' + si,
        text: sliceText,
        nodeStart: slice.start,
        nodeEnd: slice.end,
        nodePath: path,
        parentTag: str(parent && parent.tagName).toLowerCase(),
        parentId: str(parent && parent.id).slice(0, 80),
        parentClass: str(parent && parent.className)
          .replace(/\s+/g, ' ')
          .trim()
          .slice(0, 160),
        domAncestorChain: ancestry.domAncestorChain,
        domDivPath: ancestry.domDivPath,
        domDivPathKey: ancestry.domDivPathKey,
        domParentPath: ancestry.domParentPath,
        domParentKey: ancestry.domParentKey,
        domBlockKey: ancestry.domBlockKey,
        domBlockPath: ancestry.domBlockPath,
        domContainerKey: ancestry.domContainerKey,
        domContainerPath: ancestry.domContainerPath,
        domSemanticKind: ancestry.domSemanticKind,
        rect: viewportRect,
        documentRect: slice.rect,
        style: style,
        sourceKind: 'webSnapshotWordRect'
      });
    }
  }
  return out;
}
export function medianNumber(values) {
  var nums = (values || [])
    .filter(function (v) {
      return isFinite(Number(v)) && Number(v) > 0;
    })
    .map(function (v) {
      return Number(v);
    })
    .sort(function (a, b) {
      return a - b;
    });
  if (!nums.length) return 0;
  var mid = Math.floor(nums.length / 2);
  return nums.length % 2 ? nums[mid] : (nums[mid - 1] + nums[mid]) / 2;
}
export function fragmentLineAdvance(prev, curr) {
  var a = prev && prev.rect;
  var b = curr && curr.rect;
  if (!a || !b || rectsShareLine(a, b)) return 0;
  var ac = (num(a.top, 0) + num(a.bottom, num(a.top, 0))) / 2;
  var bc = (num(b.top, 0) + num(b.bottom, num(b.top, 0))) / 2;
  var advance = bc - ac;
  var minHeight = Math.max(1, Math.min(num(a.height, 0) || 1, num(b.height, 0) || 1));
  return advance > Math.max(2, minHeight * 0.35) ? advance : 0;
}
export function annotateFragmentSeparators(fragments, opts) {
  opts = opts || {};
  if (!fragments || !fragments.length) {
    return {
      medianLineAdvance: 0,
      paragraphBreaks: 0,
      paragraphGapFactor: 1.5
    };
  }
  var advances = [];
  var byIndex = [];
  for (var i = 1; i < fragments.length; i++) {
    var advance = fragmentLineAdvance(fragments[i - 1], fragments[i]);
    byIndex[i] = advance;
    if (advance > 0) advances.push(advance);
  }
  var medianAdvance = medianNumber(advances);
  var factor = num(opts.paragraphGapFactor, 1.5);
  if (!isFinite(factor) || factor < 1) factor = 1.5;
  var minExtraPx = Math.max(2, num(opts.paragraphGapMinExtraPx, 2));
  var threshold = medianAdvance > 0 ? medianAdvance * factor : Infinity;
  var paragraphBreaks = 0;
  fragments[0].separatorBefore = '';
  fragments[0].separatorKind = 'none';
  fragments[0].lineAdvanceFromPrevious = 0;
  fragments[0].medianLineAdvance = medianAdvance;
  for (var fi = 1; fi < fragments.length; fi++) {
    var gap = byIndex[fi] || 0;
    fragments[fi].separatorBefore = '';
    fragments[fi].separatorKind = 'visual-wrap';
    fragments[fi].lineAdvanceFromPrevious = gap;
    fragments[fi].medianLineAdvance = medianAdvance;
  }
  return {
    medianLineAdvance: medianAdvance,
    paragraphBreaks: paragraphBreaks,
    paragraphGapFactor: factor,
    paragraphGapThreshold: isFinite(threshold) ? threshold : 0
  };
}
export function collectVisibleRectFragments(state, opts) {
  opts = opts || {};
  var doc = state && state.doc;
  var win = state && state.win;
  if (!doc || !win || !doc.body) return null;
  var viewport = resolveVisibleViewport(state, opts);
  var walker = doc.createTreeWalker(doc.body, nodeFilterConst(win, 'SHOW_TEXT', 4), {
    acceptNode: function (node) {
      return textNodeIsVisible(node, win, doc)
        ? nodeFilterConst(win, 'FILTER_ACCEPT', 1)
        : nodeFilterConst(win, 'FILTER_REJECT', 2);
    }
  });
  var fragments = [];
  var node;
  while ((node = walker.nextNode())) {
    var nodeFragments = textFragmentsForTextNode(state, node, viewport);
    for (var i = 0; i < nodeFragments.length; i++) fragments.push(nodeFragments[i]);
  }
  fragments.sort(function (a, b) {
    var ap = (a.nodePath || []).join('.');
    var bp = (b.nodePath || []).join('.');
    return (
      ap.localeCompare(bp, undefined, {
        numeric: true
      }) ||
      num(a.nodeStart, 0) - num(b.nodeStart, 0) ||
      num(a.rect && a.rect.top, 0) - num(b.rect && b.rect.top, 0) ||
      num(a.rect && a.rect.left, 0) - num(b.rect && b.rect.left, 0)
    );
  });
  var separatorStats = annotateFragmentSeparators(fragments, opts);
  var text = '';
  for (var fi = 0; fi < fragments.length; fi++) {
    if (fi > 0) {
      var hasSeparator = Object.prototype.hasOwnProperty.call(fragments[fi], 'separatorBefore');
      var sep = hasSeparator ? str(fragments[fi].separatorBefore) : '\n';
      fragments[fi].separatorStart = text.length;
      if (sep) text += sep;
      fragments[fi].separatorEnd = text.length;
    }
    fragments[fi].lookupStart = text.length;
    text += fragments[fi].text;
    fragments[fi].lookupEnd = text.length;
  }
  return {
    viewport: viewport,
    fragments: fragments,
    text: text,
    separatorStats: separatorStats
  };
}
