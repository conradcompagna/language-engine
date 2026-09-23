import { buildUdEdgeDrawKey } from './dependency-hover.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { documentState } from './document-state.state.mjs';
import { glossRequestsState } from './gloss-requests.state.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { normalizeMwtAnchorElements } from './mwt-anchors.mjs';
import { getMwtPartsForSeg } from './mwt-context.mjs';
import { mwtContextState } from './mwt-context.state.mjs';
import { tokenFragmentsState } from './token-fragments.state.mjs';
export function getRegisteredMwtPartTargets(segIdx) {
  var partMap = dependencyState.udMwtPartAnchors.get(Number(segIdx));
  var mwtParts = getMwtPartsForSeg(segIdx);
  if (!partMap || !mwtParts.length || partMap.size !== mwtParts.length) return null;
  var ordered = [];
  for (var i = 0; i < mwtParts.length; i++) {
    var els = normalizeMwtAnchorElements(partMap.get(i));
    if (!els.length) return null;
    ordered.push({
      el: els[0],
      elements: els,
      partIndex: i,
      part: mwtParts[i] || {}
    });
  }
  return ordered;
}
export function getHighlightTargetsForSeg(segIdx) {
  var mwtTargets = getRegisteredMwtPartTargets(segIdx);
  if (mwtTargets && mwtTargets.length) return mwtTargets;
  var spans = getTokenSpanList(segIdx);
  var out = [];
  for (var i = 0; i < spans.length; i++) {
    if (!spans[i]) continue;
    out.push({
      el: spans[i],
      partIndex: null,
      part: null
    });
  }
  return out;
}
export function isDocxOriginalActive() {
  return !!(documentState.isOriginalView && documentState.currentFileType === 'docx');
}
export function shouldTrackTokenFragments(span) {
  if (isDocxOriginalActive()) return true;
  return !!(span && span.classList && span.classList.contains('canonical-token'));
}
export function registerTokenSpan(segIdx, span) {
  if (segIdx == null || segIdx < 0 || !span) return;
  var segKey = Number(segIdx);
  if (!isFinite(segKey) || segKey < 0) return;
  if (!shouldTrackTokenFragments(span)) {
    // A single-span refresh replaces any old canonical fragment registrations.
    dependencyState.udTokenFragments.delete(segKey);
    dependencyState.udTokenIndex.set(segKey, span);
    return;
  }
  var isFirstFragment = !!(span.dataset && span.dataset.tokenFragmentRole === 'first');
  if (!dependencyState.udTokenIndex.has(segKey) || isFirstFragment) {
    dependencyState.udTokenIndex.set(segKey, span);
  }
  var list = dependencyState.udTokenFragments.get(segKey);
  if (!list) {
    list = [];
    dependencyState.udTokenFragments.set(segKey, list);
  }
  if (list.indexOf(span) === -1) {
    list.push(span);
  }
}
export function clearUdTokenIndex() {
  dependencyState.udTokenIndex.clear();
  dependencyState.udTokenFragments.clear();
  dependencyState.udMwtPartAnchors.clear();
}
export function getTokenSpanList(segIdx) {
  var list = dependencyState.udTokenFragments.get(segIdx);
  if (list && list.length) return list;
  var single = dependencyState.udTokenIndex.get(segIdx);
  return single ? [single] : [];
}
// === UD GEOMETRY / CLEANUP CACHES ===
export function ensureUdSvgOverlay() {
  if (dependencyState.udSvgOverlay) return dependencyState.udSvgOverlay;
  dependencyState.udSvgOverlay = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  dependencyState.udSvgOverlay.id = 'ud-svg-overlay';
  dependencyState.udSvgOverlay.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  dependencyState.udSvgOverlay.setAttribute('overflow', 'visible');
  dependencyState.udSvgOverlay.style.overflow = 'visible';
  // Add arrow marker definition
  var defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
  var marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
  marker.setAttribute('id', 'ud-arrowhead');
  marker.setAttribute('markerWidth', '8');
  marker.setAttribute('markerHeight', '6');
  marker.setAttribute('refX', '7');
  marker.setAttribute('refY', '3');
  marker.setAttribute('orient', 'auto');
  var polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
  polygon.setAttribute('points', '0 0, 8 3, 0 6');
  polygon.setAttribute('class', 'ud-dep-arrow');
  marker.appendChild(polygon);
  defs.appendChild(marker);
  // Root arrow marker
  var rootMarker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
  rootMarker.setAttribute('id', 'ud-arrowhead-root');
  rootMarker.setAttribute('markerWidth', '8');
  rootMarker.setAttribute('markerHeight', '6');
  rootMarker.setAttribute('refX', '7');
  rootMarker.setAttribute('refY', '3');
  rootMarker.setAttribute('orient', 'auto');
  var rootPolygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
  rootPolygon.setAttribute('points', '0 0, 8 3, 0 6');
  rootPolygon.setAttribute('class', 'ud-dep-arrow root-arrow');
  rootMarker.appendChild(rootPolygon);
  defs.appendChild(rootMarker);
  // Child arrow marker (same direction as blue, just orange color)
  var childMarker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
  childMarker.setAttribute('id', 'ud-arrowhead-child');
  childMarker.setAttribute('markerWidth', '8');
  childMarker.setAttribute('markerHeight', '6');
  childMarker.setAttribute('refX', '7');
  childMarker.setAttribute('refY', '3');
  childMarker.setAttribute('orient', 'auto');
  var childPolygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
  childPolygon.setAttribute('points', '0 0, 8 3, 0 6');
  childPolygon.setAttribute('class', 'ud-dep-arrow child-arrow');
  childMarker.appendChild(childPolygon);
  defs.appendChild(childMarker);
  // Context-stroke arrow marker (matches line color)
  var contextMarker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
  contextMarker.setAttribute('id', 'ud-arrowhead-context');
  contextMarker.setAttribute('markerWidth', '8');
  contextMarker.setAttribute('markerHeight', '6');
  contextMarker.setAttribute('refX', '7');
  contextMarker.setAttribute('refY', '3');
  contextMarker.setAttribute('orient', 'auto');
  var contextPolygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
  contextPolygon.setAttribute('points', '0 0, 8 3, 0 6');
  contextPolygon.setAttribute('fill', 'context-stroke');
  contextPolygon.setAttribute('stroke', 'context-stroke');
  contextMarker.appendChild(contextPolygon);
  defs.appendChild(contextMarker);
  // Faded arrow markers for clause mode (same colors, reduced opacity)
  var fadedMarker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
  fadedMarker.setAttribute('id', 'ud-arrowhead-faded');
  fadedMarker.setAttribute('markerWidth', '8');
  fadedMarker.setAttribute('markerHeight', '6');
  fadedMarker.setAttribute('refX', '7');
  fadedMarker.setAttribute('refY', '3');
  fadedMarker.setAttribute('orient', 'auto');
  var fadedPolygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
  fadedPolygon.setAttribute('points', '0 0, 8 3, 0 6');
  fadedPolygon.setAttribute('fill', '#6366f1');
  fadedPolygon.setAttribute('opacity', '0.25');
  fadedMarker.appendChild(fadedPolygon);
  defs.appendChild(fadedMarker);
  var fadedChildMarker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
  fadedChildMarker.setAttribute('id', 'ud-arrowhead-child-faded');
  fadedChildMarker.setAttribute('markerWidth', '8');
  fadedChildMarker.setAttribute('markerHeight', '6');
  fadedChildMarker.setAttribute('refX', '7');
  fadedChildMarker.setAttribute('refY', '3');
  fadedChildMarker.setAttribute('orient', 'auto');
  var fadedChildPolygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
  fadedChildPolygon.setAttribute('points', '0 0, 8 3, 0 6');
  fadedChildPolygon.setAttribute('fill', '#e67e22');
  fadedChildPolygon.setAttribute('opacity', '0.25');
  fadedChildMarker.appendChild(fadedChildPolygon);
  defs.appendChild(fadedChildMarker);
  dependencyState.udSvgOverlay.appendChild(defs);
  hoverLayoutState.renderedText.appendChild(dependencyState.udSvgOverlay);
  return dependencyState.udSvgOverlay;
}

// --- UD rect caching (avoid per-hover layout queries) ---
export function invalidateUdRectCache() {
  tokenFragmentsState.udTokenRectCache.clear();
  tokenFragmentsState.udMwtPartRectCache.clear();
  tokenFragmentsState.udContainerRect = null;
}
export function buildMwtPartRectCacheKey(segIdx, partIdx) {
  return String(segIdx) + ':' + String(partIdx);
}
export function getUdAnchorRect(segIdx, partIdx) {
  var keyPart = parseInt(partIdx, 10);
  if (isFinite(keyPart)) {
    var partRect = tokenFragmentsState.udMwtPartRectCache.get(buildMwtPartRectCacheKey(segIdx, keyPart));
    if (partRect) return partRect;
  }
  if (getMwtPartsForSeg(segIdx).length) return null;
  return tokenFragmentsState.udTokenRectCache.get(Number(segIdx)) || null;
}
export function buildUdRectCache() {
  tokenFragmentsState.udTokenRectCache.clear();
  tokenFragmentsState.udMwtPartRectCache.clear();
  if (!hoverLayoutState.renderedText) {
    tokenFragmentsState.udContainerRect = null;
    return;
  }
  tokenFragmentsState.udContainerRect = hoverLayoutState.renderedText.getBoundingClientRect();
  if (!tokenFragmentsState.udContainerRect) return;
  dependencyState.udTokenIndex.forEach(function (spanEl, segIdx) {
    if (!spanEl || typeof spanEl.getBoundingClientRect !== 'function') return;
    var r = spanEl.getBoundingClientRect();
    if (!r) return;
    var left = r.left - tokenFragmentsState.udContainerRect.left;
    var top = r.top - tokenFragmentsState.udContainerRect.top;
    tokenFragmentsState.udTokenRectCache.set(Number(segIdx), {
      left: left,
      top: top,
      width: r.width,
      height: r.height,
      right: left + r.width,
      bottom: top + r.height,
      cx: left + r.width / 2,
      cy: top + r.height / 2
    });
  });
  dependencyState.udMwtPartAnchors.forEach(function (partMap, segIdx) {
    if (!partMap || typeof partMap.forEach !== 'function') return;
    partMap.forEach(function (spanEls, partIdx) {
      var elements = normalizeMwtAnchorElements(spanEls);
      if (!elements.length) return;
      var left = Infinity;
      var top = Infinity;
      var right = -Infinity;
      var bottom = -Infinity;
      for (var i = 0; i < elements.length; i++) {
        var spanEl = elements[i];
        if (!spanEl || typeof spanEl.getBoundingClientRect !== 'function') continue;
        var r = spanEl.getBoundingClientRect();
        if (!r) continue;
        left = Math.min(left, r.left - tokenFragmentsState.udContainerRect.left);
        top = Math.min(top, r.top - tokenFragmentsState.udContainerRect.top);
        right = Math.max(right, r.right - tokenFragmentsState.udContainerRect.left);
        bottom = Math.max(bottom, r.bottom - tokenFragmentsState.udContainerRect.top);
      }
      if (
        !isFinite(left) ||
        !isFinite(top) ||
        !isFinite(right) ||
        !isFinite(bottom) ||
        right <= left ||
        bottom <= top
      )
        return;
      tokenFragmentsState.udMwtPartRectCache.set(buildMwtPartRectCacheKey(segIdx, partIdx), {
        left: left,
        top: top,
        width: right - left,
        height: bottom - top,
        right: right,
        bottom: bottom,
        cx: left + (right - left) / 2,
        cy: top + (bottom - top) / 2
      });
    });
  });
}
export function ensureUdRectCache() {
  if (!tokenFragmentsState.udContainerRect || tokenFragmentsState.udTokenRectCache.size === 0)
    buildUdRectCache();
}

// === UI RECT CACHE (POPUPS / CHIPS / NON-TOKEN ELEMENTS) ===
// These caches are separate from the token geometry cache (udTokenRectCache).
// They primarily exist to avoid repeated layout reads (getBoundingClientRect) across hot paths like
// hover popups and NER chips, while being conservatively invalidated on layout changes.
export function invalidateUiRectCache() {
  tokenFragmentsState.uiRectCache = new WeakMap();
  tokenFragmentsState.uiRectCacheEpoch++;
}
export function invalidateUiRectFor(el) {
  try {
    if (tokenFragmentsState.uiRectCache && el) tokenFragmentsState.uiRectCache.delete(el);
  } catch (e) {}
}
export function _rectObjFromDomRect(r) {
  if (!r) return null;
  return {
    left: r.left,
    top: r.top,
    right: r.right,
    bottom: r.bottom,
    width: r.width,
    height: r.height
  };
}
export function getUiRect(el) {
  if (!el || typeof el.getBoundingClientRect !== 'function') return null;
  var rec = null;
  try {
    rec = tokenFragmentsState.uiRectCache.get(el);
  } catch (e) {
    rec = null;
  }
  if (rec && rec.epoch === tokenFragmentsState.uiRectCacheEpoch && rec.rect) return rec.rect;
  var r = null;
  try {
    r = el.getBoundingClientRect();
  } catch (e2) {
    r = null;
  }
  if (!r) return null;
  var obj = _rectObjFromDomRect(r);
  try {
    tokenFragmentsState.uiRectCache.set(el, {
      epoch: tokenFragmentsState.uiRectCacheEpoch,
      rect: obj
    });
  } catch (e3) {}
  return obj;
}

// Prefer UD token geometry cache for .reader-token spans (fast + stable). Falls back to UI rect cache.
export function getViewportRectForTokenSpan(spanEl) {
  if (!spanEl) return null;
  var segIdx = parseInt(spanEl.dataset && spanEl.dataset.index ? spanEl.dataset.index : '-1', 10);
  if (isFinite(segIdx) && segIdx >= 0) {
    ensureUdRectCache();
    var t = tokenFragmentsState.udTokenRectCache.get(segIdx);
    if (
      t &&
      tokenFragmentsState.udContainerRect &&
      isFinite(tokenFragmentsState.udContainerRect.left) &&
      isFinite(tokenFragmentsState.udContainerRect.top)
    ) {
      var L = tokenFragmentsState.udContainerRect.left + t.left;
      var T = tokenFragmentsState.udContainerRect.top + t.top;
      var R = tokenFragmentsState.udContainerRect.left + t.right;
      var B = tokenFragmentsState.udContainerRect.top + t.bottom;
      return {
        left: L,
        top: T,
        right: R,
        bottom: B,
        width: R - L,
        height: B - T
      };
    }
  }
  return getUiRect(spanEl);
}
export function hideUdLines() {
  tokenFragmentsState.udGrammarAnchor = null;
  // Remove active SVG elements without DOM-wide queries
  if (tokenFragmentsState.udActivePaths && tokenFragmentsState.udActivePaths.length) {
    for (var i = 0; i < tokenFragmentsState.udActivePaths.length; i++) {
      var p = tokenFragmentsState.udActivePaths[i];
      if (p && p.parentNode) p.remove();
    }
    tokenFragmentsState.udActivePaths.length = 0;
  }

  // Clear any tracked highlighted elements
  if (tokenFragmentsState.udActiveHighlights && tokenFragmentsState.udActiveHighlights.length) {
    for (var j = 0; j < tokenFragmentsState.udActiveHighlights.length; j++) {
      var el = tokenFragmentsState.udActiveHighlights[j];
      if (!el || !el.classList) continue;
      el.classList.remove('ud-highlight', 'ud-highlight-parent', 'ud-highlight-child', 'ud-root-highlight');
    }
    tokenFragmentsState.udActiveHighlights.length = 0;
  }
  clearPosTagHighlights();
}
export function clearPosTagHighlights() {
  glossRequestsState.chunkPosTags.forEach(function (tag) {
    // Reset to default styling
    tag.style.backgroundColor = '';
    tag.style.color = '';
    tag.style.fontWeight = '';
    tag.style.boxShadow = '';
    tag.style.transform = '';
  });
}
export function ensureNerHoverOverlay() {
  if (!hoverLayoutState.renderedText) return;
  if (
    tokenFragmentsState.nerHoverOverlay &&
    tokenFragmentsState.nerHoverOverlay.parentNode !== hoverLayoutState.renderedText
  ) {
    hoverLayoutState.renderedText.appendChild(tokenFragmentsState.nerHoverOverlay);
  }
  if (tokenFragmentsState.nerHoverOverlay) return;
  tokenFragmentsState.nerHoverOverlay = document.createElement('div');
  tokenFragmentsState.nerHoverOverlay.id = 'ner-hover-overlay';
  hoverLayoutState.renderedText.appendChild(tokenFragmentsState.nerHoverOverlay);
}
export function hideNerHover() {
  if (!tokenFragmentsState.nerHoverOverlay) return;
  tokenFragmentsState.nerHoverOverlay.innerHTML = '';
}
export function showHoverReticle(target) {
  if (!target || !hoverLayoutState.renderedText) return;
  if (target === tokenFragmentsState.lastHoverReticleTarget) return;
  var segIdx = parseInt(
    target.dataset && target.dataset.index
      ? target.dataset.index
      : target.closest && target.closest('.reader-token')
        ? target.closest('.reader-token').dataset.index
        : '-1',
    10
  );
  if (tokenFragmentsState.lastHoverReticleTarget && tokenFragmentsState.lastHoverReticleTarget !== target) {
    tokenFragmentsState.lastHoverReticleTarget.classList.remove('hover-reticle-token');
  }
  target.classList.add('hover-reticle-token');
  tokenFragmentsState.lastHoverReticleSegIdx = segIdx;
  tokenFragmentsState.lastHoverReticleTarget = target;
}
export function hideHoverReticle() {
  if (tokenFragmentsState.lastHoverReticleTarget) {
    tokenFragmentsState.lastHoverReticleTarget.classList.remove('hover-reticle-token');
  }
  tokenFragmentsState.lastHoverReticleSegIdx = -1;
  tokenFragmentsState.lastHoverReticleTarget = null;
}
export function nerLabelToClass(label) {
  var lab = (label || '').toUpperCase();
  if (lab === 'PERSON' || lab === 'PER') return 'ner-label-person';
  if (lab === 'PLACE' || lab === 'LOC' || lab === 'GPE') return 'ner-label-place';
  if (lab === 'ORG' || lab === 'ORGANIZATION') return 'ner-label-org';
  if (lab === 'DATE') return 'ner-label-date';
  return 'ner-label-misc';
}
export function formatNerLabel(label) {
  var lab = (label || '').toUpperCase().trim();
  if (!lab) return 'ENT';
  if (lab === 'PERSON' || lab === 'PER' || lab === 'PNAME') return 'PERSON';
  if (lab === 'PLACE' || lab === 'LOC' || lab === 'GPE') return 'PLACE';
  if (lab === 'ORG' || lab === 'ORGANIZATION') return 'ORG';
  if (lab === 'DATE') return 'DATE';
  return lab;
}
export function getNerLabelForSeg(segIdx) {
  if (!dependencyState.latestNerSpans || !dependencyState.latestNerSpans.length) return '';
  for (var i = 0; i < dependencyState.latestNerSpans.length; i++) {
    var ent = dependencyState.latestNerSpans[i];
    if (!ent || typeof ent.start !== 'number' || typeof ent.end !== 'number') continue;
    if (segIdx >= ent.start && segIdx < ent.end) return ent.label || '';
  }
  return '';
}
export function nerLabelToUpos(label) {
  var lab = (label || '').toUpperCase();
  if (!lab) return '';
  if (lab === 'PNAME' || lab === 'PERSON' || lab === 'PER' || lab === 'NE') return 'PROPN';
  if (lab === 'LOC' || lab === 'PLACE' || lab === 'GPE') return 'PROPN';
  if (lab === 'ORG' || lab === 'ORGANIZATION') return 'PROPN';
  if (lab === 'RACE') return 'PROPN';
  if (lab === 'TIME' || lab === 'DATE') return 'NOUN';
  if (lab === 'NUM') return 'NUM';
  return '';
}
export function renderNerHoverForToken(segIdx) {
  ensureNerHoverOverlay();
  tokenFragmentsState.nerHoverOverlay.innerHTML = '';
  if (!dependencyPopupState.displaySettings.nerOverlay) return;
  if (!dependencyState.latestNerSpans || !dependencyState.latestNerSpans.length) return;
  var hits = dependencyState.latestNerSpans.filter(function (ent) {
    return (
      ent &&
      typeof ent.start === 'number' &&
      typeof ent.end === 'number' &&
      segIdx >= ent.start &&
      segIdx < ent.end
    );
  });
  if (!hits.length) return;
  ensureUdRectCache();
  // Always measure a FRESH container rect so NER chips are positioned correctly
  // even after scrolling, resizing, or font loading changes the layout.
  // The stale cached udContainerRect was the root cause of chips landing inside tokens.
  var containerRect = hoverLayoutState.renderedText.getBoundingClientRect();
  if (!containerRect) return;
  function rectFromDomRect(r) {
    return {
      left: r.left - containerRect.left,
      top: r.top - containerRect.top,
      width: r.width,
      height: r.height,
      right: r.left - containerRect.left + r.width,
      bottom: r.top - containerRect.top + r.height
    };
  }
  function getRectsForSeg(seg) {
    var rects = [];
    var spans = getTokenSpanList(seg);
    if (spans && spans.length) {
      for (var i = 0; i < spans.length; i++) {
        var el = spans[i];
        if (!el || typeof el.getBoundingClientRect !== 'function') continue;
        var r = el.getBoundingClientRect();
        if (!r || r.width <= 0 || r.height <= 0) continue;
        rects.push(rectFromDomRect(r));
      }
    }
    if (!rects.length) {
      // Fallback: use cached rect but re-anchor to fresh containerRect
      var cached = tokenFragmentsState.udTokenRectCache.get(seg);
      if (cached && tokenFragmentsState.udContainerRect) {
        var absLeft = tokenFragmentsState.udContainerRect.left + cached.left;
        var absTop = tokenFragmentsState.udContainerRect.top + cached.top;
        rects.push({
          left: absLeft - containerRect.left,
          top: absTop - containerRect.top,
          width: cached.width,
          height: cached.height,
          right: absLeft - containerRect.left + cached.width,
          bottom: absTop - containerRect.top + cached.height
        });
      }
    }
    return rects;
  }

  // Pre-compute all UD line obstacles once (avoid repeated querySelectorAll and path sampling)
  var allLineObstaclesByEdge = new Map(); // key: "fromIdx-toIdx", value: array of obstacle rects
  if (
    dependencyPopupState.displaySettings.udOverlay &&
    tokenFragmentsState.udActivePaths &&
    tokenFragmentsState.udActivePaths.length
  ) {
    try {
      var els = tokenFragmentsState.udActivePaths;
      for (var ei = 0; ei < els.length; ei++) {
        var el = els[ei];
        if (!el || !el.classList || !el.classList.contains('ud-dep-line')) continue;
        var fromIdx = parseInt(el.getAttribute('data-from-idx'), 10);
        var toIdx = parseInt(el.getAttribute('data-to-idx'), 10);
        if (!isFinite(fromIdx) || !isFinite(toIdx)) continue;
        var fromPartAttr = el.getAttribute('data-from-part');
        var toPartAttr = el.getAttribute('data-to-part');
        var edgeKey = buildUdEdgeDrawKey(fromIdx, toIdx, fromPartAttr, toPartAttr);
        var edgeObstacles = [];
        if (typeof el.getTotalLength === 'function' && typeof el.getPointAtLength === 'function') {
          var total = el.getTotalLength();
          if (total && isFinite(total)) {
            var samples = Math.max(6, Math.min(24, Math.ceil(total / 40)));
            var step = total / samples;
            for (var s = 0; s <= samples; s++) {
              var pt = el.getPointAtLength(s * step);
              if (!pt) continue;
              var pad = 2;
              edgeObstacles.push({
                left: pt.x - pad,
                top: pt.y - pad,
                right: pt.x + pad,
                bottom: pt.y + pad
              });
            }
          }
        } else {
          try {
            var b = el.getBBox();
            if (b && b.width > 0 && b.height > 0) {
              var pad = 2;
              edgeObstacles.push({
                left: b.x - pad,
                top: b.y - pad,
                right: b.x + b.width + pad,
                bottom: b.y + b.height + pad
              });
            }
          } catch (e2) {}
        }
        if (edgeObstacles.length) {
          allLineObstaclesByEdge.set(edgeKey, {
            fromIdx: fromIdx,
            toIdx: toIdx,
            obstacles: edgeObstacles
          });
        }
      }
    } catch (e) {}
  }

  // Collect obstacles for a specific entity span (uses pre-computed data)
  function collectLineObstaclesForEnt(ent) {
    var obstacles = [];
    if (!allLineObstaclesByEdge.size) return obstacles;
    if (!ent || typeof ent.start !== 'number' || typeof ent.end !== 'number') return obstacles;
    allLineObstaclesByEdge.forEach(function (data) {
      var touchesSpan =
        (data.fromIdx >= ent.start && data.fromIdx < ent.end) ||
        (data.toIdx >= ent.start && data.toIdx < ent.end);
      if (touchesSpan) {
        for (var oi = 0; oi < data.obstacles.length; oi++) {
          obstacles.push(data.obstacles[oi]);
        }
      }
    });
    return obstacles;
  }
  function getMwtSpawnBoxObstacle() {
    if (!mwtContextState._mwtSpawnBox || mwtContextState._mwtSpawnBox.style.display === 'none') return null;
    var rect = mwtContextState._mwtSpawnBox.getBoundingClientRect
      ? mwtContextState._mwtSpawnBox.getBoundingClientRect()
      : null;
    if (!rect || rect.width <= 0 || rect.height <= 0) return null;
    var obstacle = rectFromDomRect(rect);
    var pad = 4;
    return {
      left: obstacle.left - pad,
      top: obstacle.top - pad,
      right: obstacle.right + pad,
      bottom: obstacle.bottom + pad
    };
  }
  var mwtSpawnObstacle = getMwtSpawnBoxObstacle();
  var placed = [];
  hits.forEach(function (ent) {
    var lineObstacles = collectLineObstaclesForEnt(ent);
    if (mwtSpawnObstacle) lineObstacles.push(mwtSpawnObstacle);
    var startRects = getRectsForSeg(ent.start);
    var endRects = getRectsForSeg(ent.end - 1);
    var startRect = startRects && startRects.length ? startRects[0] : null;
    var endRect = endRects && endRects.length ? endRects[0] : null;
    if (!startRect || !endRect) return;
    var startTop = startRect.top;

    // Collect ALL segment rects first, then derive visual bounds from them.
    // This is critical for RTL scripts (Arabic etc.) where the "start" segment
    // is visually on the right � using startRect.left / endRect.right directly
    // would produce a negative-width caliper that the browser collapses to nothing.
    var segRects = [];
    for (var si3 = ent.start; si3 < ent.end; si3++) {
      var rectList = getRectsForSeg(si3);
      for (var ri = 0; ri < rectList.length; ri++) {
        var r = rectList[ri];
        if (!r) continue;
        segRects.push({
          left: r.left,
          right: r.right,
          top: r.top,
          bottom: r.bottom
        });
      }
    }
    segRects.sort(function (a, b) {
      if (a.top === b.top) return a.left - b.left;
      return a.top - b.top;
    });
    var lineRects = [];
    var lineTol = 4;
    for (var ri = 0; ri < segRects.length; ri++) {
      var rr = segRects[ri];
      var lastLine = lineRects.length ? lineRects[lineRects.length - 1] : null;
      if (lastLine && Math.abs(rr.top - lastLine.top) <= lineTol) {
        lastLine.left = Math.min(lastLine.left, rr.left);
        lastLine.right = Math.max(lastLine.right, rr.right);
        lastLine.top = Math.min(lastLine.top, rr.top);
        lastLine.bottom = Math.max(lastLine.bottom, rr.bottom);
      } else {
        lineRects.push({
          left: rr.left,
          right: rr.right,
          top: rr.top,
          bottom: rr.bottom
        });
      }
    }

    // Derive visual bounds from lineRects (direction-safe)
    var spanLeft = Infinity,
      spanRight = -Infinity,
      spanTop = Infinity;
    for (var lri = 0; lri < lineRects.length; lri++) {
      if (lineRects[lri].left < spanLeft) spanLeft = lineRects[lri].left;
      if (lineRects[lri].right > spanRight) spanRight = lineRects[lri].right;
      if (lineRects[lri].top < spanTop) spanTop = lineRects[lri].top;
    }
    if (!isFinite(spanLeft)) spanLeft = Math.min(startRect.left, endRect.left);
    if (!isFinite(spanRight)) spanRight = Math.max(startRect.right, endRect.right);
    if (!isFinite(spanTop)) spanTop = Math.min(startRect.top, endRect.top);
    var left = spanLeft;
    var right = spanRight;
    var anchorTop = spanTop;
    var anchorCenter = (left + right) / 2;
    var center = anchorCenter;
    if (lineRects.length > 1) {
      // Multi-line: anchor chip to the first line's center
      anchorCenter = (lineRects[0].left + lineRects[0].right) / 2;
      center = anchorCenter;
      anchorTop = lineRects[0].top;
    }
    var chip = document.createElement('div');
    var labelText = formatNerLabel(ent.label);
    chip.className = 'ner-label ' + nerLabelToClass(ent.label);
    chip.style.left = center + 'px';
    chip.style.top = '0px';
    chip.textContent = labelText;
    chip.setAttribute('data-ner-label', labelText);
    chip.title = ent.note ? (ent.text || labelText) + ': ' + ent.note : ent.text || '';
    tokenFragmentsState.nerHoverOverlay.appendChild(chip);
    invalidateUiRectFor(chip);
    var chipRect = getUiRect(chip);
    var chipW = chipRect.width;
    var chipH = chipRect.height;
    var chipColor = window.getComputedStyle(chip).backgroundColor;
    var halfW = chipW / 2;
    var padX = 6;
    var containerW = containerRect.width || 0;
    if (containerW > 0 && padX * 2 + chipW <= containerW) {
      var minCenter = padX + halfW;
      var maxCenter = containerW - padX - halfW;
      if (center < minCenter) center = minCenter;
      if (center > maxCenter) center = maxCenter;
    }
    chip.style.left = center + 'px';
    var leftPx = center - halfW;
    var rightPx = center + halfW;
    var tailSize = 7;
    var gap = 1;
    var top = anchorTop - chipH - tailSize;
    function overlapsHoriz(ob) {
      return !(rightPx < ob.left || leftPx > ob.right);
    }
    lineObstacles.forEach(function (ob) {
      if (!overlapsHoriz(ob)) return;
      var candidate = ob.top - chipH - tailSize - gap;
      if (candidate < top) top = candidate;
    });
    placed.forEach(function (ob) {
      if (!overlapsHoriz(ob)) return;
      var candidate = ob.top - chipH - gap;
      if (candidate < top) top = candidate;
    });
    var minTop = -tokenFragmentsState.READER_EFFECT_OVERFLOW_PX;
    if (hoverLayoutState.dropZone && typeof hoverLayoutState.dropZone.getBoundingClientRect === 'function') {
      var inputRect = getUiRect(hoverLayoutState.dropZone);
      if (inputRect && isFinite(inputRect.bottom)) {
        var safePad = 4;
        var allowedTop = inputRect.bottom + safePad - containerRect.top;
        if (allowedTop < minTop) minTop = allowedTop;
      }
    }
    if (top < minTop) top = minTop;
    chip.style.top = top + 'px';
    var tailH = Math.max(tailSize, anchorTop - (top + chipH));
    chip.style.setProperty('--ner-tail-h', tailH + 'px');
    var tailX = anchorCenter - leftPx;
    var tailPad = 4;
    if (tailX < tailPad) tailX = tailPad;
    if (tailX > chipW - tailPad) tailX = chipW - tailPad;
    chip.style.setProperty('--ner-tail-x', tailX + 'px');

    // Add caliper bracket for any NER span
    if (ent.end > ent.start) {
      if (lineRects.length <= 1) {
        var caliper = document.createElement('div');
        caliper.className = 'ner-caliper';
        caliper.style.left = left - 1 + 'px';
        caliper.style.width = right - left + 2 + 'px';
        caliper.style.top = anchorTop - 4 + 'px';
        caliper.style.height = '3px';
        if (chipColor) {
          caliper.style.borderColor = chipColor;
        }
        tokenFragmentsState.nerHoverOverlay.appendChild(caliper);
      } else {
        for (var li = 0; li < lineRects.length; li++) {
          var lineRect = lineRects[li];
          var caliperLine = document.createElement('div');
          caliperLine.className = 'ner-caliper';
          caliperLine.style.left = lineRect.left - 1 + 'px';
          caliperLine.style.width = lineRect.right - lineRect.left + 2 + 'px';
          caliperLine.style.top = lineRect.top - 4 + 'px';
          caliperLine.style.height = '3px';
          if (chipColor) {
            caliperLine.style.borderColor = chipColor;
          }
          tokenFragmentsState.nerHoverOverlay.appendChild(caliperLine);
        }
      }
    }
    placed.push({
      left: leftPx,
      right: rightPx,
      top: top,
      bottom: top + chipH
    });
  });
}
export function initializeTokenFragments() {
  tokenFragmentsState.udTokenRectCache = new Map(); // segIdx -> {left, top, width, height, right, bottom, cx, cy}
  tokenFragmentsState.udMwtPartRectCache = new Map(); // "segIdx:partIdx" -> rect
  tokenFragmentsState.udContainerRect = null; // Cached renderedText bounding rect at cache build time
  tokenFragmentsState.udActivePaths = []; // Track SVG elements created for fast cleanup
  tokenFragmentsState.udActiveHighlights = []; // Track highlighted elements for fast cleanup
  tokenFragmentsState.udGrammarAnchor = null; // Anchor for DEP grammar popup near parent arrow tip
  tokenFragmentsState.nerHoverOverlay = null;
  tokenFragmentsState.hoverReticle = null;
  tokenFragmentsState.lastHoverReticleSegIdx = -1;
  tokenFragmentsState.lastHoverReticleTarget = null;
  tokenFragmentsState.READER_EFFECT_OVERFLOW_PX = 72;
  tokenFragmentsState.uiRectCache = new WeakMap(); // element -> { epoch, rect:{left,top,right,bottom,width,height} }
  tokenFragmentsState.uiRectCacheEpoch = 1;
  return true;
}
