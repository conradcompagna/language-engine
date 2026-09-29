import { getScrollLeft, getScrollTop, num, str } from './frame-lifecycle.mjs';
import { frameLifecycleState } from './frame-lifecycle.state.mjs';
import { ensureSearchOverlay, makeRange } from './text-extraction.mjs';
import { textExtractionState } from './text-extraction.state.mjs';
export function drawSearchOverlay(state, range) {
  var overlay = ensureSearchOverlay(state);
  if (!overlay || !range || !range.getClientRects) return;
  overlay.innerHTML = '';
  var rects = Array.from(range.getClientRects ? range.getClientRects() : []);
  for (var i = 0; i < rects.length; i++) {
    var r = rects[i];
    if (!r || r.width <= 0.5 || r.height <= 0.5) continue;
    var cell = state.doc.createElement('div');
    cell.className = 'docrender-websnapshot-search-cell';
    cell.style.left = Number(r.left || 0).toFixed(2) + 'px';
    cell.style.top = Number(r.top || 0).toFixed(2) + 'px';
    cell.style.width = Math.max(1, Number(r.width || 0)).toFixed(2) + 'px';
    cell.style.height = Math.max(1, Number(r.height || 0)).toFixed(2) + 'px';
    overlay.appendChild(cell);
  }
}
export function rectToObj(rect) {
  return {
    left: Number(rect.left || 0),
    top: Number(rect.top || 0),
    right: Number(rect.right || 0),
    bottom: Number(rect.bottom || 0),
    width: Number(rect.width || 0),
    height: Number(rect.height || 0)
  };
}
export function rectIntersectsViewport(rect, viewport) {
  if (!rect || rect.width <= 0.25 || rect.height <= 0.25) return false;
  return (
    rect.bottom >= viewport.top &&
    rect.top <= viewport.bottom &&
    rect.right >= viewport.left &&
    rect.left <= viewport.right
  );
}
export function rectFullyInsideViewport(rect, viewport) {
  if (!rect || rect.width <= 0.25 || rect.height <= 0.25) return false;
  var eps = 0.75;
  return (
    rect.top >= viewport.top - eps &&
    rect.bottom <= viewport.bottom + eps &&
    rect.left >= viewport.left - eps &&
    rect.right <= viewport.right + eps
  );
}
export function normalizeViewportClip(rawClip) {
  if (!rawClip || typeof rawClip !== 'object') return null;
  var left = num(rawClip.left, 0);
  var top = num(rawClip.top, 0);
  var right = rawClip.right != null ? num(rawClip.right, left) : left + num(rawClip.width, 0);
  var bottom = rawClip.bottom != null ? num(rawClip.bottom, top) : top + num(rawClip.height, 0);
  var width = Math.max(0, right - left);
  var height = Math.max(0, bottom - top);
  if (width <= 1 || height <= 1) return null;
  return {
    left: left,
    top: top,
    right: right,
    bottom: bottom,
    width: width,
    height: height
  };
}
export function resolveVisibleViewport(state, opts) {
  opts = opts || {};
  var explicit = normalizeViewportClip(
    opts.viewportClip || opts.clipRect || state.viewportClip || state.clipRect
  );
  if (explicit) {
    explicit.scrollLeft = getScrollLeft(state) + explicit.left;
    explicit.scrollTop = getScrollTop(state) + explicit.top;
    explicit.clipLeft = explicit.left;
    explicit.clipTop = explicit.top;
    return explicit;
  }
  var viewportWidth = Math.max(
    1,
    num(state.iframe && state.iframe.clientWidth, 0) || num(state.pageWidth, 640)
  );
  var viewportHeight = Math.max(
    1,
    num(state.iframe && state.iframe.clientHeight, 0) || num(state.pageHeight, 800)
  );
  return {
    left: 0,
    top: 0,
    right: viewportWidth,
    bottom: viewportHeight,
    width: viewportWidth,
    height: viewportHeight,
    scrollLeft: getScrollLeft(state),
    scrollTop: getScrollTop(state),
    clipLeft: 0,
    clipTop: 0
  };
}
export function rectToViewportLocal(rect, viewport) {
  var left = num(rect && rect.left, 0) - num(viewport && viewport.left, 0);
  var top = num(rect && rect.top, 0) - num(viewport && viewport.top, 0);
  var width = Math.max(0, num(rect && rect.width, 0));
  var height = Math.max(0, num(rect && rect.height, 0));
  return {
    left: left,
    top: top,
    right: left + width,
    bottom: top + height,
    width: width,
    height: height
  };
}
export function rectsShareLine(a, b) {
  if (!a || !b) return false;
  var ac = (num(a.top, 0) + num(a.bottom, num(a.top, 0))) / 2;
  var bc = (num(b.top, 0) + num(b.bottom, num(b.top, 0))) / 2;
  var ah = Math.max(1, num(a.height, 0));
  var bh = Math.max(1, num(b.height, 0));
  return Math.abs(ac - bc) <= Math.max(2, Math.min(ah, bh) * 0.45);
}
export function unionRects(rects) {
  var left = Infinity;
  var top = Infinity;
  var right = -Infinity;
  var bottom = -Infinity;
  for (var i = 0; i < rects.length; i++) {
    var r = rects[i];
    if (!r || r.width <= 0.25 || r.height <= 0.25) continue;
    left = Math.min(left, r.left);
    top = Math.min(top, r.top);
    right = Math.max(right, r.right);
    bottom = Math.max(bottom, r.bottom);
  }
  if (!isFinite(left) || !isFinite(top) || !isFinite(right) || !isFinite(bottom)) return null;
  return {
    left: left,
    top: top,
    right: right,
    bottom: bottom,
    width: right - left,
    height: bottom - top
  };
}
export function nodePath(node, doc) {
  var parts = [];
  var cur = node;
  while (cur && cur !== doc) {
    var parent = cur.parentNode;
    if (!parent) break;
    var kids = parent.childNodes || [];
    var idx = 0;
    for (; idx < kids.length; idx++) {
      if (kids[idx] === cur) break;
    }
    parts.push(idx);
    cur = parent;
  }
  return parts.reverse();
}
export function lowerTag(el) {
  return str(el && el.tagName).toLowerCase();
}
export function cleanClassName(value, limit) {
  return str(value)
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, limit || 160);
}
export function elementTypeIndex(el) {
  if (!el || !el.parentElement) return 1;
  var tag = lowerTag(el);
  var idx = 1;
  var cur = el.previousElementSibling;
  while (cur) {
    if (lowerTag(cur) === tag) idx += 1;
    cur = cur.previousElementSibling;
  }
  return idx;
}
export function firstUsefulClasses(value, maxCount) {
  return cleanClassName(value, 160)
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, maxCount || 2);
}
export function semanticKindForElement(el) {
  var tag = lowerTag(el);
  if (!tag) return '';
  if (/^h[1-6]$/.test(tag)) return 'heading';
  if (tag === 'p') return 'paragraph';
  if (tag === 'li') return 'list-item';
  if (tag === 'figcaption') return 'caption';
  if (tag === 'figure') return 'figure';
  if (tag === 'td' || tag === 'th') return 'table-cell';
  if (/^(table|thead|tbody|tfoot|tr)$/.test(tag)) return 'table';
  if (tag === 'blockquote') return 'quote';
  if (tag === 'pre') return 'pre';
  if (/^(article|section|main)$/.test(tag)) return 'section';
  if (/^(aside|nav|header|footer)$/.test(tag)) return tag;
  if (tag === 'div') return 'division';
  return tag;
}
export function elementStructureDescriptor(el, doc) {
  var tag = lowerTag(el);
  if (!tag) return null;
  var id = str(el && el.id).slice(0, 80);
  var classList = firstUsefulClasses(el && el.className, 2);
  var role = str(el && el.getAttribute && el.getAttribute('role')).slice(0, 80);
  var index = elementTypeIndex(el);
  var key = tag;
  if (id) key += '#' + id;
  else {
    if (classList.length) key += '.' + classList.join('.');
    key += ':nth(' + index + ')';
  }
  if (role) key += '[role=' + role + ']';
  return {
    tag: tag,
    id: id,
    className: cleanClassName(el && el.className, 160),
    role: role,
    index: index,
    key: key,
    path: nodePath(el, doc).join('.'),
    semanticKind: semanticKindForElement(el)
  };
}
export function isMeaningfulStructureElement(el) {
  return /^(article|section|main|aside|nav|header|footer|figure|figcaption|table|thead|tbody|tfoot|tr|td|th|ul|ol|li|blockquote|pre|p|div|h[1-6])$/.test(
    lowerTag(el)
  );
}
export function isBlockStructureElement(el) {
  return /^(p|li|figcaption|td|th|blockquote|pre|h[1-6])$/.test(lowerTag(el));
}
export function isContainerStructureElement(el) {
  return /^(article|section|main|aside|nav|header|footer|figure|table|ul|ol|div)$/.test(lowerTag(el));
}
export function elementAncestry(parent, doc) {
  var chain = [];
  var divPath = [];
  var nearestBlock = null;
  var nearestContainer = null;
  var cur = parent;
  while (cur && cur.nodeType === 1 && cur !== doc.documentElement) {
    if (isMeaningfulStructureElement(cur)) {
      var descriptor = elementStructureDescriptor(cur, doc);
      if (descriptor) {
        chain.push(descriptor);
        if (!nearestBlock && isBlockStructureElement(cur)) nearestBlock = descriptor;
        if (!nearestContainer && isContainerStructureElement(cur)) nearestContainer = descriptor;
        if (/^(div|article|section|main|aside|nav|figure|table)$/.test(descriptor.tag)) {
          divPath.push(descriptor.key);
        }
      }
    }
    cur = cur.parentElement;
  }
  chain.reverse();
  divPath.reverse();
  if (chain.length > 16) chain = chain.slice(chain.length - 16);
  if (divPath.length > 12) divPath = divPath.slice(divPath.length - 12);
  return {
    domAncestorChain: chain,
    domDivPath: divPath,
    domDivPathKey: divPath.join('>'),
    domParentPath: parent ? nodePath(parent, doc).join('.') : '',
    domParentKey: parent ? (elementStructureDescriptor(parent, doc) || {}).key || '' : '',
    domBlockKey: nearestBlock ? nearestBlock.key : '',
    domBlockPath: nearestBlock ? nearestBlock.path : '',
    domContainerKey: nearestContainer ? nearestContainer.key : '',
    domContainerPath: nearestContainer ? nearestContainer.path : '',
    domSemanticKind: nearestBlock
      ? nearestBlock.semanticKind
      : nearestContainer
        ? nearestContainer.semanticKind
        : ''
  };
}
export function graphemeBoundaries(text) {
  text = str(text);
  if (frameLifecycleState.global.Intl && frameLifecycleState.global.Intl.Segmenter) {
    try {
      var seg = new frameLifecycleState.global.Intl.Segmenter(undefined, {
        granularity: 'grapheme'
      });
      var out = [];
      var iter = seg.segment(text);
      for (var item of iter)
        out.push({
          start: item.index,
          end: item.index + item.segment.length,
          text: item.segment
        });
      return out;
    } catch (_e) {}
  }
  var fallback = [];
  var i = 0;
  Array.from(text).forEach(function (ch) {
    var start = i;
    i += ch.length;
    fallback.push({
      start: start,
      end: i,
      text: ch
    });
  });
  return fallback;
}
export function readRectTextStyle(win, el) {
  var cs = null;
  try {
    cs = win && win.getComputedStyle && el ? win.getComputedStyle(el) : null;
  } catch (_e) {}
  var style = cs
    ? {
        fontFamily: cs.fontFamily,
        fontSize: cs.fontSize,
        fontWeight: cs.fontWeight,
        fontStyle: cs.fontStyle,
        color: cs.color,
        textDecoration: cs.textDecorationLine || cs.textDecoration,
        lineHeight: cs.lineHeight,
        letterSpacing: cs.letterSpacing,
        wordSpacing: cs.wordSpacing,
        direction: cs.direction,
        writingMode: cs.writingMode,
        verticalAlign: cs.verticalAlign,
        whiteSpace: cs.whiteSpace
      }
    : {};
  if (
    frameLifecycleState.global.CanonicalStyle &&
    typeof frameLifecycleState.global.CanonicalStyle.normalizeTextStyle === 'function'
  ) {
    return frameLifecycleState.global.CanonicalStyle.normalizeTextStyle(style);
  }
  return style;
}
export function activeRectGeometryScale(state) {
  var scale = state && state.flatBitmap ? state.bitmapScale : state && state.htmlScale;
  scale = num(scale, 1);
  return isFinite(scale) && scale > 0 ? scale : 1;
}
export function scaleCssPx(value, scale) {
  value = str(value).trim();
  if (!value || !isFinite(scale) || scale <= 0 || Math.abs(scale - 1) < 0.0001) return value;
  var match = value.match(/^(-?\d+(?:\.\d+)?)px$/i);
  if (!match) return value;
  var scaled = Number(match[1]) * scale;
  if (!isFinite(scaled)) return value;
  return Math.round(scaled * 1000) / 1000 + 'px';
}
export function scaleRectTextStyleForGeometry(state, style) {
  var scale = activeRectGeometryScale(state);
  if (!style || Math.abs(scale - 1) < 0.0001) return style || {};
  var out = Object.assign({}, style);
  out.fontSize = scaleCssPx(out.fontSize, scale);
  out.lineHeight = scaleCssPx(out.lineHeight, scale);
  out.letterSpacing = scaleCssPx(out.letterSpacing, scale);
  out.wordSpacing = scaleCssPx(out.wordSpacing, scale);
  return out;
}
export function textNodeIsVisible(node, win, doc) {
  if (!node || node.nodeType !== 3 || !str(node.nodeValue)) return false;
  if (!str(node.nodeValue).trim()) {
    var whitespaceRects = getWholeTextRects(doc, node);
    if (
      !whitespaceRects.some(function (r) {
        return r && r.width > 0.1 && r.height > 0.1;
      })
    )
      return false;
  }
  var parent = node.parentElement;
  if (!parent || (parent.closest && parent.closest(textExtractionState.DOM_TEXT_IGNORE_SELECTOR)))
    return false;
  var el = parent;
  while (el && el.nodeType === 1 && el !== doc.documentElement) {
    var cs = null;
    try {
      cs = win.getComputedStyle(el);
    } catch (_e) {}
    if (!cs || cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse')
      return false;
    if (Number(cs.opacity) === 0) return false;
    el = el.parentElement;
  }
  return true;
}
export function getWholeTextRects(doc, node) {
  var text = str(node && node.nodeValue);
  if (!text.length) return [];
  var range = null;
  try {
    range = makeRange(doc, node, 0, text.length);
    return Array.from(range.getClientRects ? range.getClientRects() : []).map(rectToObj);
  } catch (_e) {
    return [];
  } finally {
    try {
      if (range && range.detach) range.detach();
    } catch (_e2) {}
  }
}
export function getRangeRects(doc, node, start, end) {
  var range = null;
  try {
    range = makeRange(doc, node, start, end);
    return Array.from(range.getClientRects ? range.getClientRects() : []).map(rectToObj);
  } catch (_e) {
    return [];
  } finally {
    try {
      if (range && range.detach) range.detach();
    } catch (_e2) {}
  }
}
export function lineFragmentsForTextNode(state, node, viewport) {
  var doc = state.doc;
  var win = state.win;
  var text = str(node && node.nodeValue).replace(/\u00a0/g, ' ');
  if (!text.trim()) return [];
  var wholeRects = getWholeTextRects(doc, node);
  if (
    !wholeRects.some(function (r) {
      return rectIntersectsViewport(r, viewport);
    })
  )
    return [];
  var clusters = graphemeBoundaries(text);
  var lines = [];
  for (var i = 0; i < clusters.length; i++) {
    var g = clusters[i];
    if (!g || !g.text) continue;
    var rects = getRangeRects(doc, node, g.start, g.end).filter(function (r) {
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
          start: g.start,
          end: g.end
        };
        lines.push(line);
      }
      line.start = Math.min(line.start, g.start);
      line.end = Math.max(line.end, g.end);
      line.charRects.push(rect);
      line.lineRect = unionRects([line.lineRect, rect]) || rect;
    }
  }
  if (!lines.length) return [];
  lines.sort(function (a, b) {
    return (
      num(a.lineRect.top, 0) - num(b.lineRect.top, 0) || num(a.lineRect.left, 0) - num(b.lineRect.left, 0)
    );
  });
  var parent = node.parentElement;
  var path = nodePath(node, doc);
  var style = scaleRectTextStyleForGeometry(state, readRectTextStyle(win, parent));
  var ancestry = elementAncestry(parent, doc);
  var out = [];
  for (var l = 0; l < lines.length; l++) {
    var lineInfo = lines[l];
    var lineText = text.slice(lineInfo.start, lineInfo.end);
    if (!lineText.trim()) continue;
    var lineRects = getRangeRects(doc, node, lineInfo.start, lineInfo.end).filter(function (r) {
      return rectFullyInsideViewport(r, viewport) && rectsShareLine(r, lineInfo.lineRect);
    });
    var rect = unionRects(lineRects.length ? lineRects : lineInfo.charRects);
    if (!rect) continue;
    var viewportRect = rectToViewportLocal(rect, viewport);
    out.push({
      id: 'web-rect-frag-' + path.join('-') + '-' + lineInfo.start + '-' + lineInfo.end + '-' + l,
      text: lineText,
      nodeStart: lineInfo.start,
      nodeEnd: lineInfo.end,
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
      documentRect: rect,
      style: style
    });
  }
  return out;
}
