import { getCanonicalSegIdx, getSentenceSpansFromSegments } from './dependency-geometry.mjs';
import { normalizeUdPartIndex } from './dependency-hover.mjs';
import { makeUdNodeId, normalizeUdSentenceSpans, resolveUdAtomicNodeId } from './dependency-state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { getLookupEntryFillMode, getLookupEntryResolvedVia } from './entry-editing.mjs';
import { appendUniqueFillIndexes, buildDictFillSlicesForToken } from './fill-slices.mjs';
import { uposColorForTag } from './gloss-requests.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { buildMwtPartRanges } from './mwt-anchors.mjs';
import { mwtContextState } from './mwt-context.state.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
import { isUnknownDictEntry } from './side-panel.mjs';
import { buildTokenMapGroupedFillEntry } from './token-map.mjs';
export function getLiveHoveredMwtPartIdx(segIdx) {
  var candidates = [
    segmentRenderingState.currentPopupAnchorEl,
    segmentRenderingState.currentFillHit,
    segmentRenderingState.currentSpan
  ];
  for (var i = 0; i < candidates.length; i++) {
    var el = candidates[i];
    if (!el || !el.dataset) continue;
    var partIdx = normalizeUdPartIndex(el.dataset.mwtPartIndex);
    if (partIdx === null) continue;
    var tokenEl = el.closest && el.closest('.reader-token') ? el.closest('.reader-token') : el;
    var tokenSeg = tokenEl && tokenEl.dataset ? parseInt(tokenEl.dataset.index || '-1', 10) : -1;
    if (tokenSeg === Number(segIdx)) return partIdx;
  }
  return null;
}
export function getUdAtomicHoverNodeId(segIdx, hoveredPartIdx) {
  var canonicalIdx = getCanonicalSegIdx(segIdx);
  var struct = dependencyState.latestUdStructure || {};
  var nodeMap = struct.atomicNodeMap || {};
  var normPart = normalizeUdPartIndex(hoveredPartIdx);
  if (getMwtPartsForSeg(canonicalIdx).length) {
    if (normPart === null) normPart = getLiveHoveredMwtPartIdx(canonicalIdx);
    if (normPart === null) return null;
    return resolveUdAtomicNodeId(nodeMap, canonicalIdx, normPart);
  }
  return resolveUdAtomicNodeId(nodeMap, canonicalIdx, null);
}
export function getUdAtomicSentenceNodeIds(segIdx) {
  var canonicalIdx = getCanonicalSegIdx(segIdx);
  var struct = dependencyState.latestUdStructure || {};
  var nodeMap = struct.atomicNodeMap || {};
  var nodeIds = Array.isArray(struct.atomicIds) ? struct.atomicIds.slice() : [];
  if (!nodeIds.length) return [];
  var sentences = normalizeUdSentenceSpans(
    (dependencyState.latestUdOverlay && dependencyState.latestUdOverlay.sentences) || []
  );
  if (!sentences.length) {
    if (Array.isArray(hoverLayoutState.latestSegments) && hoverLayoutState.latestSegments.length) {
      var fallbackSpans = getSentenceSpansFromSegments(hoverLayoutState.latestSegments);
      for (var fs = 0; fs < fallbackSpans.length; fs++) {
        sentences.push([fallbackSpans[fs].start, fallbackSpans[fs].end]);
      }
    } else {
      sentences.push([0, Number.MAX_SAFE_INTEGER]);
    }
  }
  var sentenceSpan = null;
  for (var si = 0; si < sentences.length; si++) {
    var span = sentences[si];
    if (canonicalIdx >= span[0] && canonicalIdx < span[1]) {
      sentenceSpan = span;
      break;
    }
  }
  if (sentenceSpan) {
    nodeIds = nodeIds.filter(function (nodeId) {
      var meta = nodeMap[nodeId];
      return !!(meta && meta.segIdx >= sentenceSpan[0] && meta.segIdx < sentenceSpan[1]);
    });
  }
  nodeIds.sort(function (a, b) {
    var metaA = nodeMap[a] || {};
    var metaB = nodeMap[b] || {};
    var posA =
      struct.atomicPosition && struct.atomicPosition[a] !== undefined
        ? struct.atomicPosition[a]
        : metaA.segIdx;
    var posB =
      struct.atomicPosition && struct.atomicPosition[b] !== undefined
        ? struct.atomicPosition[b]
        : metaB.segIdx;
    if (posA !== posB) return posA - posB;
    return String(a).localeCompare(String(b));
  });
  return nodeIds;
}
export function rebuildUdCaches(udOverlay) {
  dependencyState.latestUdTokenMap = {};
  dependencyState.latestCollapsedSpanInfo = {};
  dependencyState.latestUdStructure = null;
  if (!udOverlay || !Array.isArray(udOverlay.tokens)) return;
  var tokens = udOverlay.tokens;
  var tokenMap = {};
  var children = {};
  var parentOf = {};
  var tokenPosition = {};
  var tokenIds = [];
  var atomicNodeMap = {};
  var atomicChildren = {};
  var atomicParentOf = {};
  var atomicPosition = {};
  var atomicIds = [];
  for (var i = 0; i < tokens.length; i++) {
    var tok = tokens[i];
    if (!tok || typeof tok.i !== 'number') continue;
    tokenMap[tok.i] = tok;
    dependencyState.latestUdTokenMap[tok.i] = tok;
    children[tok.i] = [];
    tokenIds.push(tok.i);
    var pos = typeof tok.doc_i === 'number' && isFinite(tok.doc_i) ? tok.doc_i : i;
    tokenPosition[tok.i] = pos;
    if (tok.seg_span && Array.isArray(tok.seg_span) && tok.seg_span.length > 1) {
      var firstSeg = tok.seg_span[0];
      var lastSeg = tok.seg_span[tok.seg_span.length - 1];
      var combinedText = tok.text || '';
      for (var si = 0; si < tok.seg_span.length; si++) {
        var segIdx = tok.seg_span[si];
        dependencyState.latestCollapsedSpanInfo[segIdx] = {
          firstSeg: firstSeg,
          lastSeg: lastSeg,
          combinedText: combinedText,
          udTok: tok,
          isFirst: segIdx === firstSeg
        };
      }
    }
    var basePos = typeof tok.doc_i === 'number' && isFinite(tok.doc_i) ? tok.doc_i : i;
    var mwtParts = Array.isArray(tok.mwt_parts) ? tok.mwt_parts : [];
    if (mwtParts.length) {
      var surfaceText = String(tok.text || '');
      var partRanges = buildMwtPartRanges(surfaceText, mwtParts);
      var surfaceLen = Math.max(1, surfaceText.length);
      for (var pi = 0; pi < mwtParts.length; pi++) {
        var part = mwtParts[pi] || {};
        var nodeId = makeUdNodeId(tok.i, pi);
        var range = partRanges[pi] || null;
        var partCenter = (pi + 0.5) / Math.max(1, mwtParts.length);
        if (range) {
          var rangeStart = parseInt(range.start, 10);
          var rangeEnd = parseInt(range.end, 10);
          if (isFinite(rangeStart) && isFinite(rangeEnd) && rangeEnd > rangeStart) {
            partCenter = (rangeStart + rangeEnd) / 2 / surfaceLen;
          }
        }
        atomicNodeMap[nodeId] = {
          id: nodeId,
          segIdx: tok.i,
          partIdx: pi,
          token: tok,
          part: part
        };
        atomicChildren[nodeId] = [];
        atomicIds.push(nodeId);
        atomicPosition[nodeId] = basePos + Math.max(0, Math.min(0.999, partCenter));
      }
    } else {
      var plainNodeId = makeUdNodeId(tok.i, null);
      atomicNodeMap[plainNodeId] = {
        id: plainNodeId,
        segIdx: tok.i,
        partIdx: null,
        token: tok,
        part: null
      };
      atomicChildren[plainNodeId] = [];
      atomicIds.push(plainNodeId);
      atomicPosition[plainNodeId] = basePos;
    }
  }
  for (var j = 0; j < tokens.length; j++) {
    var t = tokens[j];
    if (!t || typeof t.i !== 'number') continue;
    if (Array.isArray(t.heads)) {
      // MWT multi-head token: register as child of every head
      var headsArr = [];
      for (var hi = 0; hi < t.heads.length; hi++) {
        var hIdx = t.heads[hi];
        if (hIdx !== undefined && hIdx !== t.i && tokenMap[hIdx]) {
          children[hIdx].push(t.i);
          headsArr.push(hIdx);
        }
      }
      parentOf[t.i] = headsArr.length ? headsArr : undefined;
    } else {
      var headIdx = t.head;
      if (headIdx !== undefined && headIdx !== t.i && tokenMap[headIdx]) {
        children[headIdx].push(t.i);
        parentOf[t.i] = headIdx;
      }
    }
  }
  var rawEdges = Array.isArray(udOverlay.edges) ? udOverlay.edges : [];
  for (var ei = 0; ei < rawEdges.length; ei++) {
    var edge = rawEdges[ei] || {};
    var fromNodeId = resolveUdAtomicNodeId(atomicNodeMap, edge.from, edge.from_part);
    var toNodeId = resolveUdAtomicNodeId(atomicNodeMap, edge.to, edge.to_part);
    if (!fromNodeId || !toNodeId || fromNodeId === toNodeId) continue;
    if (!atomicChildren[fromNodeId]) atomicChildren[fromNodeId] = [];
    if (atomicChildren[fromNodeId].indexOf(toNodeId) === -1) atomicChildren[fromNodeId].push(toNodeId);
    if (atomicParentOf[toNodeId] === undefined) {
      atomicParentOf[toNodeId] = fromNodeId;
    } else if (Array.isArray(atomicParentOf[toNodeId])) {
      if (atomicParentOf[toNodeId].indexOf(fromNodeId) === -1) atomicParentOf[toNodeId].push(fromNodeId);
    } else if (atomicParentOf[toNodeId] !== fromNodeId) {
      atomicParentOf[toNodeId] = [atomicParentOf[toNodeId], fromNodeId];
    }
  }
  var roots = [];
  for (var k = 0; k < tokenIds.length; k++) {
    var seg = tokenIds[k];
    if (parentOf[seg] === undefined) roots.push(seg);
  }
  var tokenDepths = {};
  var maxDepth = 0;
  var queue = roots.slice();
  for (var qi = 0; qi < queue.length; qi++) {
    var cur = queue[qi];
    tokenDepths[cur] = 0;
  }
  for (var q = 0; q < queue.length; q++) {
    var cur2 = queue[q];
    var ch = children[cur2] || [];
    for (var c = 0; c < ch.length; c++) {
      var child = ch[c];
      if (tokenDepths[child] === undefined) {
        tokenDepths[child] = tokenDepths[cur2] + 1;
        if (tokenDepths[child] > maxDepth) maxDepth = tokenDepths[child];
        queue.push(child);
      }
    }
  }
  var atomicRoots = [];
  for (var ak = 0; ak < atomicIds.length; ak++) {
    var atomicId = atomicIds[ak];
    if (atomicParentOf[atomicId] === undefined) atomicRoots.push(atomicId);
  }
  var atomicDepths = {};
  var atomicMaxDepth = 0;
  var atomicQueue = atomicRoots.slice();
  for (var aq = 0; aq < atomicQueue.length; aq++) {
    atomicDepths[atomicQueue[aq]] = 0;
  }
  for (var ar = 0; ar < atomicQueue.length; ar++) {
    var atomicCur = atomicQueue[ar];
    var atomicKids = atomicChildren[atomicCur] || [];
    for (var ac = 0; ac < atomicKids.length; ac++) {
      var atomicChild = atomicKids[ac];
      if (atomicDepths[atomicChild] === undefined) {
        atomicDepths[atomicChild] = atomicDepths[atomicCur] + 1;
        if (atomicDepths[atomicChild] > atomicMaxDepth) atomicMaxDepth = atomicDepths[atomicChild];
        atomicQueue.push(atomicChild);
      }
    }
  }
  dependencyState.latestUdStructure = {
    tokenMap: tokenMap,
    children: children,
    parentOf: parentOf,
    tokenPosition: tokenPosition,
    tokenDepths: tokenDepths,
    maxDepth: maxDepth,
    tokenIds: tokenIds,
    atomicNodeMap: atomicNodeMap,
    atomicChildren: atomicChildren,
    atomicParentOf: atomicParentOf,
    atomicPosition: atomicPosition,
    atomicDepths: atomicDepths,
    atomicMaxDepth: atomicMaxDepth,
    atomicIds: atomicIds
  };
}
export function setLatestUdOverlay(udOverlay) {
  dependencyState.latestUdOverlay = udOverlay || null;
  dependencyState.latestNerSpans =
    dependencyState.latestUdOverlay && Array.isArray(dependencyState.latestUdOverlay.ents)
      ? dependencyState.latestUdOverlay.ents
      : [];
  rebuildUdCaches(dependencyState.latestUdOverlay);
}
export function getMwtPartsForSeg(segIdx) {
  var tok = dependencyState.latestUdTokenMap && dependencyState.latestUdTokenMap[Number(segIdx)];
  return tok && Array.isArray(tok.mwt_parts) ? tok.mwt_parts : [];
}

// --- MWT expanded-text spawn box (persistent popup) -----------------------
// When a surface slice does not match the mwt child text (e.g. Sanskrit
// sandhi), hovering the synthetic anchor spawns a small white persistent
// box containing the unsandhied child text. That box is the hover surface
// for the real dictionary/grammar popups; click outside or drift outside
// the local anchor/spawn area to close.
export function _getMwtSpawnGraceCircle() {
  if (
    !mwtContextState._mwtSpawnActive ||
    !mwtContextState._mwtSpawnBox ||
    mwtContextState._mwtSpawnBox.style.display === 'none'
  )
    return null;
  var boxRect =
    mwtContextState._mwtSpawnBox && mwtContextState._mwtSpawnBox.getBoundingClientRect
      ? mwtContextState._mwtSpawnBox.getBoundingClientRect()
      : null;
  if (!boxRect) return null;
  var left = boxRect.left;
  var top = boxRect.top;
  var right = boxRect.right;
  var bottom = boxRect.bottom;
  var anchorEl = mwtContextState._mwtSpawnActive.anchorEl || null;
  if (anchorEl && anchorEl.getBoundingClientRect) {
    var anchorRect = anchorEl.getBoundingClientRect();
    if (anchorRect) {
      left = Math.min(left, anchorRect.left);
      top = Math.min(top, anchorRect.top);
      right = Math.max(right, anchorRect.right);
      bottom = Math.max(bottom, anchorRect.bottom);
    }
  }
  var width = Math.max(0, right - left);
  var height = Math.max(0, bottom - top);
  var cx = left + width / 2;
  var cy = top + height / 2;
  var radius = Math.sqrt(width * width + height * height) / 2;
  return {
    x: cx,
    y: cy,
    radius: radius
  };
}
export function _isPointInsideMwtSpawnBox(ev) {
  if (
    !mwtContextState._mwtSpawnActive ||
    !mwtContextState._mwtSpawnBox ||
    mwtContextState._mwtSpawnBox.style.display === 'none'
  )
    return false;
  if (!ev || !isFinite(Number(ev.clientX)) || !isFinite(Number(ev.clientY))) return false;
  var rect = mwtContextState._mwtSpawnBox.getBoundingClientRect
    ? mwtContextState._mwtSpawnBox.getBoundingClientRect()
    : null;
  return !!(
    rect &&
    rect.width > 0 &&
    rect.height > 0 &&
    Number(ev.clientX) >= rect.left &&
    Number(ev.clientX) <= rect.right &&
    Number(ev.clientY) >= rect.top &&
    Number(ev.clientY) <= rect.bottom
  );
}
export function _isPointInsideMwtSpawnGraceCircle(ev) {
  if (!ev || !isFinite(Number(ev.clientX)) || !isFinite(Number(ev.clientY))) return false;
  var graceCircle = _getMwtSpawnGraceCircle();
  if (!graceCircle) return false;
  var dx = Number(ev.clientX) - graceCircle.x;
  var dy = Number(ev.clientY) - graceCircle.y;
  return dx * dx + dy * dy <= graceCircle.radius * graceCircle.radius;
}
export function _isPointInsideMwtSpawnShield(ev) {
  if (
    !mwtContextState._mwtSpawnActive ||
    !mwtContextState._mwtSpawnShield ||
    mwtContextState._mwtSpawnShield.style.display === 'none'
  )
    return false;
  if (!ev || !isFinite(Number(ev.clientX)) || !isFinite(Number(ev.clientY))) return false;
  var rect = mwtContextState._mwtSpawnShield.getBoundingClientRect
    ? mwtContextState._mwtSpawnShield.getBoundingClientRect()
    : null;
  return !!(
    rect &&
    rect.width > 0 &&
    rect.height > 0 &&
    Number(ev.clientX) >= rect.left &&
    Number(ev.clientX) <= rect.right &&
    Number(ev.clientY) >= rect.top &&
    Number(ev.clientY) <= rect.bottom
  );
}
export function _updateMwtSpawnShield() {
  if (
    !mwtContextState._mwtSpawnShield ||
    !mwtContextState._mwtSpawnActive ||
    !mwtContextState._mwtSpawnBox ||
    mwtContextState._mwtSpawnBox.style.display === 'none'
  )
    return;
  var anchorEl = mwtContextState._mwtSpawnActive.anchorEl || null;
  if (!anchorEl || !anchorEl.getBoundingClientRect) {
    mwtContextState._mwtSpawnShield.style.display = 'none';
    return;
  }
  var boxRect = mwtContextState._mwtSpawnBox.getBoundingClientRect
    ? mwtContextState._mwtSpawnBox.getBoundingClientRect()
    : null;
  var anchorRect = anchorEl.getBoundingClientRect();
  if (!boxRect || !anchorRect) {
    mwtContextState._mwtSpawnShield.style.display = 'none';
    return;
  }
  var left = 0;
  var top = 0;
  var right = 0;
  var bottom = 0;
  if (boxRect.bottom <= anchorRect.top) {
    left = boxRect.left;
    right = boxRect.right;
    top = boxRect.bottom;
    bottom = anchorRect.top;
  } else if (anchorRect.bottom <= boxRect.top) {
    left = boxRect.left;
    right = boxRect.right;
    top = anchorRect.bottom;
    bottom = boxRect.top;
  } else if (boxRect.right <= anchorRect.left) {
    left = boxRect.right;
    right = anchorRect.left;
    top = Math.max(boxRect.top, anchorRect.top);
    bottom = Math.min(boxRect.bottom, anchorRect.bottom);
  } else if (anchorRect.right <= boxRect.left) {
    left = anchorRect.right;
    right = boxRect.left;
    top = Math.max(boxRect.top, anchorRect.top);
    bottom = Math.min(boxRect.bottom, anchorRect.bottom);
  } else {
    mwtContextState._mwtSpawnShield.style.display = 'none';
    return;
  }
  if (right <= left || bottom <= top) {
    mwtContextState._mwtSpawnShield.style.display = 'none';
    return;
  }
  var sx = window.pageXOffset || document.documentElement.scrollLeft || 0;
  var sy = window.pageYOffset || document.documentElement.scrollTop || 0;
  mwtContextState._mwtSpawnShield.style.display = 'block';
  mwtContextState._mwtSpawnShield.style.left = left + sx + 'px';
  mwtContextState._mwtSpawnShield.style.top = top + sy + 'px';
  mwtContextState._mwtSpawnShield.style.width = Math.max(0, right - left) + 'px';
  mwtContextState._mwtSpawnShield.style.height = Math.max(0, bottom - top) + 'px';
}
export function _installMwtSpawnOutsideHandler() {
  if (mwtContextState._mwtSpawnClickHandlerInstalled) return;
  mwtContextState._mwtSpawnClickHandlerInstalled = true;
  document.addEventListener(
    'mousemove',
    function (ev) {
      if (!mwtContextState._mwtSpawnActive || !mwtContextState._mwtSpawnBox) return;
      if (mwtContextState._mwtSpawnBox.contains(ev.target)) return;
      if (_isPointInsideMwtSpawnBox(ev)) return;
      if (
        mwtContextState._mwtSpawnShield &&
        mwtContextState._mwtSpawnShield.contains &&
        mwtContextState._mwtSpawnShield.contains(ev.target)
      )
        return;
      if (_isPointInsideMwtSpawnShield(ev)) return;
      var activeAnchor = mwtContextState._mwtSpawnActive.anchorEl || null;
      if (activeAnchor && activeAnchor.contains && activeAnchor.contains(ev.target)) return;
      var activeToken =
        activeAnchor && activeAnchor.closest && activeAnchor.closest('.reader-token')
          ? activeAnchor.closest('.reader-token')
          : activeAnchor;
      var hoveredToken = ev.target && ev.target.closest ? ev.target.closest('.reader-token') : null;
      if (hoveredToken && activeToken && hoveredToken !== activeToken) {
        hideMwtSpawnBox();
        return;
      }
      if (_isPointInsideMwtSpawnGraceCircle(ev)) return;
      hideMwtSpawnBox();
    },
    true
  );
}
export function _wireMwtSpawnToken(inner) {
  if (!inner || inner.__mwtSpawnWired) return inner;
  inner.__mwtSpawnWired = true;
  inner.addEventListener('mousemove', function (ev) {
    var hook = window.__mwtSpawnHoverHook;
    if (typeof hook === 'function') hook(ev, inner);
  });
  inner.addEventListener('click', function (ev) {
    var hook = window.__mwtSpawnClickHook;
    if (typeof hook === 'function') hook(ev, inner);
  });
  return inner;
}
export function _createMwtSpawnToken(text, context) {
  var inner = document.createElement('span');
  inner.className = 'mwt-spawn-token';
  inner.dataset.mwtSpawn = '1';
  inner.style.cssText = 'display:inline-block;cursor:pointer;';
  inner.textContent = String(text || '');
  if (context && typeof context === 'object') inner.__mwtSpawnContext = context;
  return _wireMwtSpawnToken(inner);
}
export function _getMwtSpawnContent(box) {
  if (!box || !box.querySelector) return null;
  var content = box.querySelector('.mwt-spawn-content');
  if (content) return content;
  content = document.createElement('span');
  content.className = 'mwt-spawn-content';
  content.style.cssText = 'display:inline-flex;align-items:center;gap:0;';
  box.appendChild(content);
  return content;
}
export function _clearMwtSpawnContent(box) {
  var content = _getMwtSpawnContent(box);
  if (!content) return null;
  var tokens = content.querySelectorAll ? content.querySelectorAll('.mwt-spawn-token') : [];
  for (var i = 0; i < tokens.length; i++) {
    if (tokens[i].__mwtSpawnContext) delete tokens[i].__mwtSpawnContext;
  }
  content.textContent = '';
  return content;
}
export function _positionMwtSpawnBox(box, anchorEl) {
  if (!box || !anchorEl || !anchorEl.getBoundingClientRect) return;
  box.style.display = 'block';
  box.style.left = '0px';
  box.style.top = '0px';
  var rect = anchorEl.getBoundingClientRect();
  var bw = box.offsetWidth,
    bh = box.offsetHeight;
  var sx = window.pageXOffset || document.documentElement.scrollLeft || 0;
  var sy = window.pageYOffset || document.documentElement.scrollTop || 0;
  var left = rect.left + sx + (rect.width - bw) / 2;
  var top = rect.top + sy - bh - 10;
  if (left < sx + 2) left = sx + 2;
  box.style.left = left + 'px';
  box.style.top = top + 'px';
}
export function _ensureMwtSpawnBox() {
  if (mwtContextState._mwtSpawnBox) return mwtContextState._mwtSpawnBox;
  if (typeof document === 'undefined') return null;
  var shield = document.createElement('div');
  shield.className = 'mwt-spawn-shield';
  shield.style.cssText =
    'position:absolute;z-index:1000002;background:transparent;display:none;pointer-events:auto;';
  var box = document.createElement('div');
  box.className = 'mwt-spawn-box';
  box.style.cssText =
    'position:absolute;z-index:1000004;background:#fff;border:1px solid #999;border-radius:4px;padding:3px 8px;box-shadow:0 2px 8px rgba(0,0,0,0.18);font-weight:600;color:#222;white-space:nowrap;display:none;pointer-events:auto;';
  var arrowOuter = document.createElement('div');
  arrowOuter.style.cssText =
    'position:absolute;bottom:-7px;left:50%;transform:translateX(-50%);width:0;height:0;border-left:7px solid transparent;border-right:7px solid transparent;border-top:7px solid #999;pointer-events:none;';
  var arrowInner = document.createElement('div');
  arrowInner.style.cssText =
    'position:absolute;bottom:-5px;left:50%;transform:translateX(-50%);width:0;height:0;border-left:6px solid transparent;border-right:6px solid transparent;border-top:6px solid #fff;pointer-events:none;';
  var inner = document.createElement('span');
  inner.className = 'mwt-spawn-token';
  inner.dataset.mwtSpawn = '1';
  inner.style.cssText = 'display:inline-block;cursor:pointer;';
  var content = document.createElement('span');
  content.className = 'mwt-spawn-content';
  content.style.cssText = 'display:inline-flex;align-items:center;gap:0;';
  content.appendChild(_wireMwtSpawnToken(inner));
  box.appendChild(arrowOuter);
  box.appendChild(arrowInner);
  box.appendChild(content);
  document.body.appendChild(shield);
  document.body.appendChild(box);
  mwtContextState._mwtSpawnShield = shield;
  mwtContextState._mwtSpawnBox = box;
  _installMwtSpawnOutsideHandler();

  // Route hover on the box into the existing popup pipeline by forwarding
  // to window.dispatchEvent-style reuse: we piggyback on the container
  // onmousemove handler, which resolves seg/mwtPartIdx via closest().
  // The inner span carries data-mwt-part-index and a synthetic
  // data-seg/data-index mirror so buildPopupForSpan can run on it.
  // We use a dedicated mousemove on the box that calls the shared hover
  // handler exposed on window.__mwtSpawnHoverHook if set.
  return box;
}
export function hideMwtSpawnBox() {
  var hadActiveSpawn = !!mwtContextState._mwtSpawnActive;
  if (mwtContextState._mwtSpawnBox) {
    var inners = mwtContextState._mwtSpawnBox.querySelectorAll
      ? mwtContextState._mwtSpawnBox.querySelectorAll('.mwt-spawn-token')
      : [];
    for (var mi = 0; mi < inners.length; mi++) {
      if (inners[mi].__mwtSpawnContext) delete inners[mi].__mwtSpawnContext;
    }
    mwtContextState._mwtSpawnBox.style.display = 'none';
    if (
      segmentRenderingState.currentPopupAnchorEl &&
      mwtContextState._mwtSpawnBox.contains(segmentRenderingState.currentPopupAnchorEl)
    ) {
      segmentRenderingState.currentPopupAnchorEl = null;
    }
    if (
      segmentRenderingState.currentSpan &&
      mwtContextState._mwtSpawnBox.contains(segmentRenderingState.currentSpan)
    )
      segmentRenderingState.currentSpan = null;
    if (
      segmentRenderingState.currentFillHit &&
      mwtContextState._mwtSpawnBox.contains(segmentRenderingState.currentFillHit)
    )
      segmentRenderingState.currentFillHit = null;
  }
  if (mwtContextState._mwtSpawnShield) mwtContextState._mwtSpawnShield.style.display = 'none';
  mwtContextState._mwtSpawnActive = null;
  if (hadActiveSpawn && typeof mwtContextState._mwtSpawnHoverVisualResetHook === 'function') {
    try {
      mwtContextState._mwtSpawnHoverVisualResetHook();
    } catch (err) {
      /* swallow */
    }
  }
}
export function _filterDictFillForMwtPart(dictFill, partIdx) {
  if (!Array.isArray(dictFill) || !dictFill.length)
    return {
      rows: [],
      origIndexes: []
    };
  var rows = [];
  var origIndexes = [];
  var anyTagged = false;
  for (var i = 0; i < dictFill.length; i++) {
    var row = dictFill[i] || {};
    var p = parseInt(row._mwt_part_index, 10);
    if (isFinite(p)) anyTagged = true;
    if (isFinite(p) && p === Number(partIdx)) {
      rows.push(row);
      origIndexes.push(i);
    }
  }
  if (!anyTagged) {
    return {
      rows: dictFill.slice(),
      origIndexes: dictFill.map(function (_, k) {
        return k;
      })
    };
  }
  return {
    rows: rows,
    origIndexes: origIndexes
  };
}
export function _cloneMwtSpawnFillRow(row) {
  var src = row && typeof row === 'object' ? row : {};
  var out = {};
  for (var key in src) {
    if (!Object.prototype.hasOwnProperty.call(src, key)) continue;
    var value = src[key];
    out[key] = Array.isArray(value) ? value.slice() : value;
  }
  return out;
}
export function _buildMwtSpawnFillSurfaceSlices(childText, rows) {
  var surface = String(childText || '');
  var fillRows = Array.isArray(rows) ? rows : [];
  if (!surface || !fillRows.length) return [];
  var slices = [];
  var pendingOrphans = [];
  for (var i = 0; i < fillRows.length; i++) {
    var row = fillRows[i] || {};
    var start = parseInt(row._surface_start, 10);
    var end = parseInt(row._surface_end, 10);
    if (!isFinite(start) || !isFinite(end) || end <= start) {
      pendingOrphans.push(i);
      continue;
    }
    if (start < 0) start = 0;
    if (end > surface.length) end = surface.length;
    if (end <= start) {
      pendingOrphans.push(i);
      continue;
    }
    var nextSlice = {
      start: start,
      end: end,
      fill_indexes: [i]
    };
    if (pendingOrphans.length) {
      nextSlice.fill_indexes = appendUniqueFillIndexes(pendingOrphans.slice(), nextSlice.fill_indexes);
      pendingOrphans = [];
    }
    if (slices.length && slices[slices.length - 1].start === start && slices[slices.length - 1].end === end) {
      appendUniqueFillIndexes(slices[slices.length - 1].fill_indexes, nextSlice.fill_indexes);
    } else {
      slices.push(nextSlice);
    }
  }
  var explicitSliceCount = slices.length;
  if (pendingOrphans.length) {
    if (slices.length) {
      appendUniqueFillIndexes(slices[slices.length - 1].fill_indexes, pendingOrphans);
    } else {
      slices.push({
        start: 0,
        end: surface.length,
        fill_indexes: pendingOrphans.slice()
      });
    }
  }
  if (explicitSliceCount > 1 || (explicitSliceCount === 1 && fillRows.length === 1)) {
    return slices;
  }
  if (fillRows.length > 1) {
    var inferred = buildDictFillSlicesForToken(surface, fillRows, null, {
      coalesceMarkOnly: true
    });
    if (Array.isArray(inferred) && inferred.length) {
      return inferred.map(function (slice) {
        return {
          start: parseInt(slice.start, 10) || 0,
          end: parseInt(slice.end, 10) || 0,
          fill_indexes: Array.isArray(slice.fillIndexes) ? slice.fillIndexes.slice() : []
        };
      });
    }
  }
  return slices;
}
export function _expandMwtSpawnSourceRows(rows, childText) {
  var sourceRows = Array.isArray(rows) ? rows : [];
  var surfaceText = String(childText || '');
  var out = [];
  for (var i = 0; i < sourceRows.length; i++) {
    var row = sourceRows[i] || {};
    var pieceRows = Array.isArray(row._mwt_child_piece_rows) ? row._mwt_child_piece_rows : [];
    if (!pieceRows.length) {
      out.push(row);
      continue;
    }
    for (var pi = 0; pi < pieceRows.length; pi++) {
      var pieceRow = pieceRows[pi] || {};
      var clone = _cloneMwtSpawnFillRow(pieceRow);
      if (!Object.prototype.hasOwnProperty.call(clone, '_mwt_part_index') && row._mwt_part_index != null) {
        clone._mwt_part_index = row._mwt_part_index;
      }
      if (
        !Object.prototype.hasOwnProperty.call(clone, '_mwt_child_resolution_category') &&
        row._mwt_child_resolution_category != null
      ) {
        clone._mwt_child_resolution_category = row._mwt_child_resolution_category;
      }
      if (!Object.prototype.hasOwnProperty.call(clone, '_lemma_upos_hint') && row._lemma_upos_hint != null) {
        clone._lemma_upos_hint = row._lemma_upos_hint;
      }
      if (!Object.prototype.hasOwnProperty.call(clone, '_lemma_xpos_hint') && row._lemma_xpos_hint != null) {
        clone._lemma_xpos_hint = row._lemma_xpos_hint;
      }
      if (!Object.prototype.hasOwnProperty.call(clone, '_lemma_promoted') && row._lemma_promoted) {
        clone._lemma_promoted = true;
      }
      if (!Object.prototype.hasOwnProperty.call(clone, '_lemma_override') && row._lemma_override) {
        clone._lemma_override = true;
      }
      var childLocalStart = parseInt(clone._surface_start, 10);
      var childLocalEnd = parseInt(clone._surface_end, 10);
      if (isFinite(childLocalStart) && isFinite(childLocalEnd) && childLocalEnd >= childLocalStart) {
        clone._mwt_child_local_start = childLocalStart;
        clone._mwt_child_local_end = childLocalEnd;
        if (!clone._mwt_child_text && childLocalEnd > childLocalStart) {
          clone._mwt_child_text = surfaceText.slice(childLocalStart, childLocalEnd);
        }
      } else if (!clone._mwt_child_text) {
        clone._mwt_child_text = String(clone.text || clone.surface_form || '');
      }
      out.push(clone);
    }
  }
  return out.length ? out : sourceRows.slice();
}
export function _buildMwtSpawnLookupContext(segIdx, partIdx, childText, parentResult) {
  var surfaceText = String(childText || '');
  var parentEntry = parentResult && typeof parentResult === 'object' ? parentResult : null;
  if (!surfaceText) return null;
  var parentFill = parentEntry && Array.isArray(parentEntry.dict_fill) ? parentEntry.dict_fill : [];
  var filtered = _filterDictFillForMwtPart(parentFill, partIdx);
  var sourceRows =
    Array.isArray(filtered.rows) && filtered.rows.length
      ? _expandMwtSpawnSourceRows(filtered.rows, surfaceText)
      : [
          {
            text: surfaceText,
            head: surfaceText,
            surface_form: surfaceText,
            senses: [],
            pos: 'unknown',
            source: 'UNKNOWN'
          }
        ];
  var localRows = [];
  var hasKnown = false;
  var hasUnknown = false;
  for (var i = 0; i < sourceRows.length; i++) {
    var srcRow = sourceRows[i] || {};
    var clone = _cloneMwtSpawnFillRow(srcRow);
    var localStart = parseInt(srcRow._mwt_child_local_start, 10);
    var localEnd = parseInt(srcRow._mwt_child_local_end, 10);
    var hintedSurface = String(srcRow._mwt_child_text || '');
    if ((!isFinite(localStart) || !isFinite(localEnd) || localEnd <= localStart) && sourceRows.length === 1) {
      localStart = 0;
      localEnd = surfaceText.length;
    }
    if (isFinite(localStart) && localStart < 0) localStart = 0;
    if (isFinite(localEnd) && localEnd > surfaceText.length) localEnd = surfaceText.length;
    var localSurface = '';
    if (isFinite(localStart) && isFinite(localEnd) && localEnd > localStart) {
      localSurface = surfaceText.slice(localStart, localEnd);
      clone._surface_start = localStart;
      clone._surface_end = localEnd;
    } else {
      delete clone._surface_start;
      delete clone._surface_end;
    }
    if (!localSurface && hintedSurface) localSurface = hintedSurface;
    if (!localSurface && sourceRows.length === 1) localSurface = surfaceText;
    if (localSurface) {
      clone.text = localSurface;
      clone.surface_form = localSurface;
    }
    localRows.push(clone);
    if (isUnknownDictEntry(clone)) hasUnknown = true;
    else hasKnown = true;
  }
  if (!localRows.length) return null;
  var localSlices = _buildMwtSpawnFillSurfaceSlices(surfaceText, localRows);
  var aggregateSource;
  if (localRows.length === 1) {
    aggregateSource = _cloneMwtSpawnFillRow(localRows[0]);
  } else {
    aggregateSource =
      buildTokenMapGroupedFillEntry(
        parentEntry || {},
        localRows.map(function (_row, idx) {
          return idx;
        }),
        surfaceText,
        localRows
      ) || {};
  }
  var result = _cloneMwtSpawnFillRow(aggregateSource);
  var partMetaList = getMwtPartsForSeg(segIdx);
  var partMeta =
    Array.isArray(partMetaList) && isFinite(Number(partIdx)) && partMetaList[Number(partIdx)]
      ? partMetaList[Number(partIdx)] || {}
      : {};
  var lemmaText =
    String(partMeta.lemma || result.lemma_form || result.lemma || surfaceText).trim() || surfaceText;
  var uposText = String(partMeta.upos || result.upos || (parentEntry && parentEntry.upos) || '').trim();
  var xposText = String(
    partMeta.tag || partMeta.xpos || result.tag || result.xpos || (parentEntry && parentEntry.tag) || ''
  ).trim();
  var depText = String((parentEntry && (parentEntry.dep_label || parentEntry.dep)) || '').trim();
  var resolvedVia = getLookupEntryResolvedVia(parentEntry || result);
  if (!resolvedVia) {
    resolvedVia = localRows.some(function (row) {
      return !!(row && (row._lemma_override || row._lemma_promoted));
    })
      ? 'lemma_promoted'
      : 'surface';
  }
  result.text = surfaceText;
  result.surface_form = surfaceText;
  if (!result.head && !result.display_headword && !result.headword) result.head = surfaceText;
  result.dict_fill = localRows.slice();
  result.inspect_fill = localRows.slice();
  result.inspect_fill_count = localRows.length;
  result.dict_fill_surface_slices = localSlices;
  result.dict_fill_mode = getLookupEntryFillMode(parentEntry || result);
  result.dict_fill_has_known = hasKnown;
  result.dict_fill_has_unknown = hasUnknown;
  result.dict_fill_has_lemma_promotion = localRows.some(function (row) {
    return !!(row && row._lemma_promoted);
  });
  result.upos = uposText;
  result.upos_label = uposText;
  result.upos_color = uposColorForTag(uposText);
  result.tag = xposText;
  result.xpos = xposText;
  result.lemma = lemmaText;
  result.lemma_form = lemmaText;
  result.lemma_raw = lemmaText;
  result.lemma_suffix = '';
  result.dep = depText;
  result.dep_label = depText;
  result.feats = '';
  result.seg_i = Number(segIdx);
  result.resolved_via = resolvedVia;
  result.mwt_parts = [];
  result.mwt_child_resolutions = [];
  var udTok = {
    i: Number(segIdx),
    text: surfaceText,
    lemma: lemmaText,
    lemma_raw: lemmaText,
    upos: uposText,
    tag: xposText,
    xpos: xposText,
    dep: depText,
    feats: '',
    mwt_parts: []
  };
  var posData = {
    upos: uposText,
    upos_label: uposText,
    upos_color: uposColorForTag(uposText),
    dep: depText,
    dep_label: depText,
    tag: xposText,
    lemma: lemmaText,
    lemma_raw: lemmaText,
    lemma_suffix: '',
    feats: ''
  };
  var liveState = {
    segIdx: Number(segIdx),
    surface: surfaceText,
    lemma: lemmaText,
    lemma_raw: lemmaText,
    lemma_suffix: '',
    posData: posData,
    udTok: udTok,
    entry: result,
    tokenEntry: result,
    dictFill: localRows.slice(),
    tokenDictFill: localRows.slice(),
    fillMode: result.dict_fill_mode || '',
    tokenFillMode: result.dict_fill_mode || '',
    resolvedVia: resolvedVia,
    tokenResolvedVia: resolvedVia,
    surfaceLookup: result,
    lemmaLookup: null,
    lemmaPartLookups: Object.create(null),
    surfaceLookupPromise: null,
    lemmaLookupPromise: null,
    lemmaPartLookupPromises: Object.create(null),
    headDecompByForm: null
  };
  return {
    segIdx: Number(segIdx),
    partIdx: Number(partIdx),
    childText: surfaceText,
    lookupResult: result,
    udTok: udTok,
    posData: posData,
    liveState: liveState
  };
}
export function initializeMwtContext() {
  mwtContextState._mwtSpawnBox = null;
  mwtContextState._mwtSpawnShield = null;
  mwtContextState._mwtSpawnActive = null;
  mwtContextState._mwtSpawnClickHandlerInstalled = false;
  mwtContextState._mwtSpawnHoverVisualResetHook = null;
  return true;
}
