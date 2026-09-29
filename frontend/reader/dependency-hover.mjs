import {
  computeContextWindowTokens,
  drawUdLinesForClause,
  drawUdLinesForConnectedIslands,
  drawUdLinesForIsland,
  getCanonicalSegIdx
} from './dependency-geometry.mjs';
import { dependencyGeometryState } from './dependency-geometry.state.mjs';
import { dependencyHoverState } from './dependency-hover.state.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { buildUdAtomicHighlightState, resolveUdAtomicNodeId } from './dependency-state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { getLiveHoveredMwtPartIdx, getMwtPartsForSeg, getUdAtomicHoverNodeId } from './mwt-context.mjs';
import { appendDepDescriptionForParentArrow } from './orthography.mjs';
import { ensureUdRectCache, ensureUdSvgOverlay, getUdAnchorRect, hideUdLines } from './token-fragments.mjs';
import { tokenFragmentsState } from './token-fragments.state.mjs';
export function getContextWindowTokens(segIdx) {
  // Return cached result if we already computed for this segIdx
  var canonicalIdx = getCanonicalSegIdx(segIdx);
  if (
    dependencyGeometryState.cachedContextWindowSegIdx === canonicalIdx &&
    dependencyGeometryState.cachedContextWindowTokens !== null
  ) {
    return dependencyGeometryState.cachedContextWindowTokens;
  }
  dependencyGeometryState.cachedContextWindowTokens = computeContextWindowTokens(canonicalIdx);
  dependencyGeometryState.cachedContextWindowSegIdx = canonicalIdx;
  return dependencyGeometryState.cachedContextWindowTokens;
}
export function clearContextWindowCache() {
  dependencyGeometryState.cachedContextWindowTokens = null;
  dependencyGeometryState.cachedContextWindowSegIdx = -1;
}

// Bottom-up highlighting works on atomic UD nodes:
// plain tokens are nodes; MWT children replace their parent surface token.
export function computeBottomUpChunkTokens(segIdx, hoveredPartIdx) {
  var canonicalIdx = getCanonicalSegIdx(segIdx);
  var hoverNodeId = getUdAtomicHoverNodeId(canonicalIdx, hoveredPartIdx);
  if (!dependencyState.latestUdOverlay || !dependencyState.latestUdOverlay.ok || !hoverNodeId) {
    return buildUdAtomicHighlightState(new Set(), hoverNodeId);
  }
  var threshold = parseInt(dependencyPopupState.displaySettings.bottomUpChunkThreshold, 10);
  if (!isFinite(threshold) || threshold < 1) threshold = 5;
  if (threshold > 10) threshold = 10;
  var struct = dependencyState.latestUdStructure || {};
  var nodeMap = struct.atomicNodeMap || {};
  var children = struct.atomicChildren || {};
  var parentOf = struct.atomicParentOf || {};
  var nodePosition = struct.atomicPosition || {};
  var nodeDepths = struct.atomicDepths || {};
  var maxDepth = struct.atomicMaxDepth || 0;
  var nodeIds = Array.isArray(struct.atomicIds) ? struct.atomicIds.slice() : [];
  if (!nodeIds.length || !nodeMap[hoverNodeId]) {
    return buildUdAtomicHighlightState(new Set([hoverNodeId]), hoverNodeId);
  }
  var chunkOf = {};
  for (var ni = 0; ni < nodeIds.length; ni++) {
    chunkOf[nodeIds[ni]] = nodeIds[ni];
  }
  function getChunkHead(nodeId) {
    if (chunkOf[nodeId] === nodeId) return nodeId;
    chunkOf[nodeId] = getChunkHead(chunkOf[nodeId]);
    return chunkOf[nodeId];
  }
  for (var depth = maxDepth; depth >= 1; depth--) {
    for (var idx = 0; idx < nodeIds.length; idx++) {
      var nodeId = nodeIds[idx];
      if (nodeDepths[nodeId] !== depth) continue;
      var parentRaw = parentOf[nodeId];
      if (parentRaw === undefined) continue;
      var parentNodeId = Array.isArray(parentRaw) ? parentRaw[0] : parentRaw;
      if (!parentNodeId || !nodeMap[parentNodeId]) continue;
      var nodePos = nodePosition[nodeId] !== undefined ? nodePosition[nodeId] : idx;
      var parentPos = nodePosition[parentNodeId] !== undefined ? nodePosition[parentNodeId] : idx;
      var distance = Math.abs(nodePos - parentPos);
      if (distance > threshold) continue;
      var nodeChunkHead = getChunkHead(nodeId);
      var parentChunkHead = getChunkHead(parentNodeId);
      if (nodeChunkHead !== parentChunkHead) {
        chunkOf[nodeChunkHead] = parentChunkHead;
      }
    }
  }
  var targetChunkHead = getChunkHead(hoverNodeId);
  var highlightedNodes = new Set();
  for (var hi = 0; hi < nodeIds.length; hi++) {
    var candidateNodeId = nodeIds[hi];
    if (getChunkHead(candidateNodeId) === targetChunkHead) {
      highlightedNodes.add(candidateNodeId);
    }
  }
  return buildUdAtomicHighlightState(highlightedNodes, hoverNodeId);
}

// Descendant cascade:
// 1) collect hovered atomic node + descendants
// 2) highlight every descendant, even when descendants are positionally discontiguous
export function computeBottomUpCascadeTokens(segIdx, hoveredPartIdx) {
  var canonicalIdx = getCanonicalSegIdx(segIdx);
  var hoverNodeId = getUdAtomicHoverNodeId(canonicalIdx, hoveredPartIdx);
  if (!dependencyState.latestUdOverlay || !dependencyState.latestUdOverlay.ok || !hoverNodeId) {
    return buildUdAtomicHighlightState(new Set(), hoverNodeId);
  }
  var struct = dependencyState.latestUdStructure || {};
  var nodeMap = struct.atomicNodeMap || {};
  var children = struct.atomicChildren || {};
  if (!nodeMap[hoverNodeId]) {
    return buildUdAtomicHighlightState(new Set([hoverNodeId]), hoverNodeId);
  }
  var descendantSet = new Set([hoverNodeId]);
  var stack = [hoverNodeId];
  while (stack.length) {
    var cur = stack.pop();
    var kids = children[cur] || [];
    for (var ki = 0; ki < kids.length; ki++) {
      var childNodeId = kids[ki];
      if (descendantSet.has(childNodeId)) continue;
      descendantSet.add(childNodeId);
      stack.push(childNodeId);
    }
  }
  return buildUdAtomicHighlightState(descendantSet, hoverNodeId);
}

// Caches for bottom-up token slices
export function buildUdHoverKey(segIdx, hoveredPartIdx) {
  var canonicalIdx = getCanonicalSegIdx(segIdx);
  var normPart = normalizeUdPartIndex(hoveredPartIdx);
  if (normPart === null && getMwtPartsForSeg(canonicalIdx).length) {
    normPart = getLiveHoveredMwtPartIdx(canonicalIdx);
  }
  return String(canonicalIdx) + ':' + (normPart !== null ? String(normPart) : '');
}
export function getBottomUpChunkTokens(segIdx, hoveredPartIdx) {
  var canonicalIdx = getCanonicalSegIdx(segIdx);
  var hoverKey = buildUdHoverKey(canonicalIdx, hoveredPartIdx);
  if (
    dependencyHoverState.cachedBottomUpChunkSegIdx === hoverKey &&
    dependencyHoverState.cachedBottomUpChunkTokens !== null
  ) {
    return dependencyHoverState.cachedBottomUpChunkTokens;
  }
  dependencyHoverState.cachedBottomUpChunkTokens = computeBottomUpChunkTokens(canonicalIdx, hoveredPartIdx);
  dependencyHoverState.cachedBottomUpChunkSegIdx = hoverKey;
  return dependencyHoverState.cachedBottomUpChunkTokens;
}
export function clearBottomUpChunkCache() {
  dependencyHoverState.cachedBottomUpChunkTokens = null;
  dependencyHoverState.cachedBottomUpChunkSegIdx = '';
}
export function getBottomUpCascadeTokens(segIdx, hoveredPartIdx) {
  var canonicalIdx = getCanonicalSegIdx(segIdx);
  var hoverKey = buildUdHoverKey(canonicalIdx, hoveredPartIdx);
  if (
    dependencyHoverState.cachedBottomUpCascadeSegIdx === hoverKey &&
    dependencyHoverState.cachedBottomUpCascadeTokens !== null
  ) {
    return dependencyHoverState.cachedBottomUpCascadeTokens;
  }
  dependencyHoverState.cachedBottomUpCascadeTokens = computeBottomUpCascadeTokens(
    canonicalIdx,
    hoveredPartIdx
  );
  dependencyHoverState.cachedBottomUpCascadeSegIdx = hoverKey;
  return dependencyHoverState.cachedBottomUpCascadeTokens;
}
export function clearBottomUpCascadeCache() {
  dependencyHoverState.cachedBottomUpCascadeTokens = null;
  dependencyHoverState.cachedBottomUpCascadeSegIdx = '';
}
export function getActiveBottomUpTokens(segIdx, hoveredPartIdx) {
  var canonicalIdx = getCanonicalSegIdx(segIdx);
  return getBottomUpCascadeTokens(canonicalIdx, hoveredPartIdx);
}
export function normalizeUdPartIndex(partIdx) {
  var parsed = parseInt(partIdx, 10);
  return isFinite(parsed) ? parsed : null;
}
export function buildUdEdgeDrawKey(fromIdx, toIdx, fromPart, toPart) {
  var key = String(fromIdx) + '-' + String(toIdx);
  var normFromPart = normalizeUdPartIndex(fromPart);
  var normToPart = normalizeUdPartIndex(toPart);
  if (normFromPart !== null) key += ':f' + String(normFromPart);
  if (normToPart !== null) key += ':t' + String(normToPart);
  return key;
}
export function getUdExplicitPartEdgeFlags(segIdx) {
  var flags = {
    from: false,
    to: false
  };
  var targetSeg = parseInt(segIdx, 10);
  if (
    !isFinite(targetSeg) ||
    !dependencyState.latestUdOverlay ||
    !Array.isArray(dependencyState.latestUdOverlay.edges)
  )
    return flags;
  var edges = dependencyState.latestUdOverlay.edges;
  for (var i = 0; i < edges.length; i++) {
    var edge = edges[i] || {};
    if (!flags.from && edge.from === targetSeg && normalizeUdPartIndex(edge.from_part) !== null) {
      flags.from = true;
    }
    if (!flags.to && edge.to === targetSeg && normalizeUdPartIndex(edge.to_part) !== null) {
      flags.to = true;
    }
    if (flags.from && flags.to) break;
  }
  return flags;
}
export function shouldIncludeUdEdgeForHoveredPart(edge, segIdx, hoveredPartIdx, explicitPartFlags) {
  var partIdx = normalizeUdPartIndex(hoveredPartIdx);
  if (partIdx === null) {
    return !getMwtPartsForSeg(segIdx).length;
  }
  var flags = explicitPartFlags || {
    from: false,
    to: false
  };
  var rawEdge = edge || {};
  if (rawEdge.from === segIdx && rawEdge.to === segIdx) {
    var fromMatch = !flags.from || normalizeUdPartIndex(rawEdge.from_part) === partIdx;
    var toMatch = !flags.to || normalizeUdPartIndex(rawEdge.to_part) === partIdx;
    return !!(fromMatch || toMatch);
  }
  if (rawEdge.from === segIdx && flags.from) {
    return normalizeUdPartIndex(rawEdge.from_part) === partIdx;
  }
  if (rawEdge.to === segIdx && flags.to) {
    return normalizeUdPartIndex(rawEdge.to_part) === partIdx;
  }
  return true;
}
export function getUdHoverRelation(edge, segIdx, hoveredPartIdx) {
  var rawEdge = edge || {};
  var partIdx = normalizeUdPartIndex(hoveredPartIdx);
  var hasMwtParts = partIdx !== null && getMwtPartsForSeg(segIdx).length > 0;
  var fromPart = normalizeUdPartIndex(rawEdge.from_part);
  var toPart = normalizeUdPartIndex(rawEdge.to_part);
  if (hasMwtParts) {
    if (rawEdge.from === segIdx && fromPart === partIdx && !(rawEdge.to === segIdx && toPart === partIdx)) {
      return 'outgoing';
    }
    if (rawEdge.to === segIdx && toPart === partIdx && !(rawEdge.from === segIdx && fromPart === partIdx)) {
      return 'incoming';
    }
    return null;
  }
  if (rawEdge.from === segIdx) return 'outgoing';
  if (rawEdge.to === segIdx) return 'incoming';
  return null;
}
export function getUdHoveredEdgeStyle(item, segIdx, hoveredPartIdx, isConnected) {
  var hoverRelation = item ? item.hoverRelation : null;
  var partIdx = normalizeUdPartIndex(hoveredPartIdx);
  var useMwtPartColors = partIdx !== null && getMwtPartsForSeg(segIdx).length > 0 && !!hoverRelation;
  if (isConnected) {
    if (useMwtPartColors) {
      return hoverRelation === 'incoming'
        ? {
            strokeColor: '#6366f1',
            strokeWidth: 1.75,
            strokeOpacity: 0.85,
            arrowheadId: 'ud-arrowhead'
          }
        : {
            strokeColor: '#e67e22',
            strokeWidth: 1.75,
            strokeOpacity: 0.85,
            arrowheadId: 'ud-arrowhead-child'
          };
    }
    return item && item.isChildLine
      ? {
          strokeColor: '#e67e22',
          strokeWidth: 1.75,
          strokeOpacity: 0.85,
          arrowheadId: 'ud-arrowhead-child'
        }
      : {
          strokeColor: '#6366f1',
          strokeWidth: 1.75,
          strokeOpacity: 0.85,
          arrowheadId: 'ud-arrowhead'
        };
  }
  return item && item.isChildLine
    ? {
        strokeColor: '#6b7280',
        strokeWidth: 1.4,
        strokeOpacity: 0.25,
        arrowheadId: 'ud-arrowhead-child-faded'
      }
    : {
        strokeColor: '#6b7280',
        strokeWidth: 1.4,
        strokeOpacity: 0.25,
        arrowheadId: 'ud-arrowhead-faded'
      };
}
export function appendHoveredMultiHeadEdges(segIdx, highlightedTokens, edgesToDraw, drawnPairs) {
  var udTok = getUdInfoForSegment(segIdx);
  if (!udTok || !Array.isArray(udTok.heads) || !udTok.heads.length) return;
  if (Array.isArray(udTok.mwt_parts) && udTok.mwt_parts.length) return;
  for (var hi = 0; hi < udTok.heads.length; hi++) {
    var headIdx = Number(udTok.heads[hi]);
    if (!isFinite(headIdx) || headIdx === segIdx) continue;
    if (!dependencyState.latestUdTokenMap || !dependencyState.latestUdTokenMap[headIdx]) continue;
    var pairKey = buildUdEdgeDrawKey(headIdx, segIdx, null, null);
    if (drawnPairs.has(pairKey)) continue;
    edgesToDraw.push({
      fromIdx: headIdx,
      toIdx: segIdx,
      fromPart: null,
      toPart: null,
      isChildLine: false,
      isInternal: !!(highlightedTokens && highlightedTokens.has(headIdx) && highlightedTokens.has(segIdx)),
      dep: String(udTok.dep || '')
    });
    drawnPairs.add(pairKey);
  }
}

// Draw UD lines for bottom-up chunk - reuses the context window rendering logic
export function drawUdLinesForBottomUpChunk(segIdx, hoveredPartIdx) {
  hideUdLines();
  if (!dependencyState.latestUdOverlay || !dependencyState.latestUdOverlay.ok) return;
  var highlightState = getActiveBottomUpTokens(segIdx, hoveredPartIdx);
  var highlightedNodes = highlightState && highlightState.nodeSet ? highlightState.nodeSet : null;
  var highlightedTokens = highlightState && highlightState.segSet ? highlightState.segSet : null;
  var hoverNodeId = highlightState ? highlightState.hoverNodeId : null;
  if (!highlightedNodes || highlightedNodes.size === 0 || !highlightedTokens || highlightedTokens.size === 0)
    return;
  var svg = ensureUdSvgOverlay();
  ensureUdRectCache();
  var edges = dependencyState.latestUdOverlay.edges || [];
  var edgesToDraw = [];
  var drawnPairs = new Set();
  var struct = dependencyState.latestUdStructure || {};
  var atomicNodeMap = struct.atomicNodeMap || {};
  edges.forEach(function (edge) {
    var fromPart = normalizeUdPartIndex(edge.from_part);
    var toPart = normalizeUdPartIndex(edge.to_part);
    var fromNodeId = resolveUdAtomicNodeId(atomicNodeMap, edge.from, fromPart);
    var toNodeId = resolveUdAtomicNodeId(atomicNodeMap, edge.to, toPart);
    var fromInChunk = !!(fromNodeId && highlightedNodes.has(fromNodeId));
    var toInChunk = !!(toNodeId && highlightedNodes.has(toNodeId));
    // Draw edges that are internal to chunk OR edges in/out of chunk (external connections)
    if (!fromInChunk && !toInChunk) return;
    var pairKey = buildUdEdgeDrawKey(edge.from, edge.to, edge.from_part, edge.to_part);
    if (drawnPairs.has(pairKey)) return;
    var isChildLine = true;
    if (toNodeId && toNodeId === hoverNodeId) {
      isChildLine = false;
    } else if (fromInChunk && !toInChunk) {
      isChildLine = true;
    } else if (!fromInChunk && toInChunk) {
      isChildLine = false;
    }
    var hoverRelation = getUdHoverRelation(edge, segIdx, hoveredPartIdx);
    edgesToDraw.push({
      fromIdx: edge.from,
      toIdx: edge.to,
      fromPart: fromPart,
      toPart: toPart,
      fromNodeId: fromNodeId,
      toNodeId: toNodeId,
      isChildLine: isChildLine,
      hoverRelation: hoverRelation,
      isInternal: fromInChunk && toInChunk,
      dep: String(edge.dep || '')
    });
    drawnPairs.add(pairKey);
  });

  // MWT parents can carry multiple incoming heads on the token record even when
  // the collapsed surface-edge list only exposes one of them. Ensure hover draws
  // every distinct incoming head for the hovered surface token.
  appendHoveredMultiHeadEdges(segIdx, highlightedTokens, edgesToDraw, drawnPairs);
  edgesToDraw.forEach(function (item) {
    var fromRect = getUdAnchorRect(item.fromIdx, item.fromPart);
    var toRect = getUdAnchorRect(item.toIdx, item.toPart);
    if (!fromRect || !toRect) return;
    var x1 = fromRect.cx;
    var y1 = fromRect.top;
    var x2 = toRect.cx;
    var y2 = toRect.top;
    var midX = (x1 + x2) / 2;
    var dist = Math.abs(x2 - x1);
    var arcHeight = Math.min(40, Math.max(20, dist * 0.3));
    var controlY = Math.min(y1, y2) - arcHeight;
    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('class', 'ud-dep-line');
    // Draw child -> parent (reversed flow) so arrowheads land at the parent endpoint.
    path.setAttribute('d', 'M ' + x2 + ' ' + y2 + ' Q ' + midX + ' ' + controlY + ' ' + x1 + ' ' + y1);
    path.setAttribute('data-from-idx', item.fromIdx);
    path.setAttribute('data-to-idx', item.toIdx);
    if (item.fromPart != null) path.setAttribute('data-from-part', item.fromPart);
    if (item.toPart != null) path.setAttribute('data-to-part', item.toPart);

    // ONLY color edges directly connected to the hovered token
    // All other edges (internal or external) are grey
    var isHoveredEdge = !!(hoverNodeId && (item.fromNodeId === hoverNodeId || item.toNodeId === hoverNodeId));
    var style = getUdHoveredEdgeStyle(item, segIdx, hoveredPartIdx, isHoveredEdge);
    var strokeColor = style.strokeColor;
    var strokeWidth = style.strokeWidth;
    var strokeOpacity = style.strokeOpacity;
    var arrowheadId = style.arrowheadId;
    path.setAttribute(
      'style',
      'stroke: ' +
        strokeColor +
        '; ' +
        'stroke-width: ' +
        strokeWidth +
        '; ' +
        'opacity: ' +
        strokeOpacity +
        '; ' +
        'fill: none;'
    );
    path.setAttribute('marker-end', 'url(#' + arrowheadId + ')');
    svg.appendChild(path);
    tokenFragmentsState.udActivePaths.push(path);
    if (isHoveredEdge) {
      appendDepDescriptionForParentArrow(svg, segIdx, item, x2, y2, controlY);
    }
  });
}
export function drawUdLinesForContextWindow(segIdx, hoveredPartIdx) {
  hideUdLines();
  if (!dependencyState.latestUdOverlay || !dependencyState.latestUdOverlay.ok) return;

  // Use cached tokens to stay in sync with applyChunkHighlight
  var highlightedTokens = getContextWindowTokens(segIdx);
  if (!highlightedTokens || highlightedTokens.size === 0) return;
  var svg = ensureUdSvgOverlay();
  ensureUdRectCache();
  var edges = dependencyState.latestUdOverlay.edges || [];
  var edgesToDraw = [];
  var drawnPairs = new Set();
  var explicitPartFlags = getUdExplicitPartEdgeFlags(segIdx);
  edges.forEach(function (edge) {
    var fromInChunk = highlightedTokens.has(edge.from);
    var toInChunk = highlightedTokens.has(edge.to);
    // Draw edges that are internal to chunk OR edges in/out of chunk (external connections)
    if (!fromInChunk && !toInChunk) return;
    if (!shouldIncludeUdEdgeForHoveredPart(edge, segIdx, hoveredPartIdx, explicitPartFlags)) return;
    var pairKey = buildUdEdgeDrawKey(edge.from, edge.to, edge.from_part, edge.to_part);
    if (drawnPairs.has(pairKey)) return;

    // Determine if this is a child line (arrow pointing to child)
    var isChildLine = edge.to !== segIdx;
    var hoverRelation = getUdHoverRelation(edge, segIdx, hoveredPartIdx);
    edgesToDraw.push({
      fromIdx: edge.from,
      toIdx: edge.to,
      fromPart: normalizeUdPartIndex(edge.from_part),
      toPart: normalizeUdPartIndex(edge.to_part),
      isChildLine: isChildLine,
      hoverRelation: hoverRelation,
      isInternal: fromInChunk && toInChunk,
      dep: String(edge.dep || '')
    });
    drawnPairs.add(pairKey);
  });
  edgesToDraw.forEach(function (item) {
    var fromRect = getUdAnchorRect(item.fromIdx, item.fromPart);
    var toRect = getUdAnchorRect(item.toIdx, item.toPart);
    if (!fromRect || !toRect) return;
    var x1 = fromRect.cx;
    var y1 = fromRect.top;
    var x2 = toRect.cx;
    var y2 = toRect.top;
    var midX = (x1 + x2) / 2;
    var dist = Math.abs(x2 - x1);
    var arcHeight = Math.min(40, Math.max(20, dist * 0.3));
    var controlY = Math.min(y1, y2) - arcHeight;
    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('class', 'ud-dep-line');
    // Draw child -> parent (reversed flow) so arrowheads land at the parent endpoint.
    path.setAttribute('d', 'M ' + x2 + ' ' + y2 + ' Q ' + midX + ' ' + controlY + ' ' + x1 + ' ' + y1);
    path.setAttribute('data-from-idx', item.fromIdx);
    path.setAttribute('data-to-idx', item.toIdx);
    if (item.fromPart != null) path.setAttribute('data-from-part', item.fromPart);
    if (item.toPart != null) path.setAttribute('data-to-part', item.toPart);

    // ONLY color edges directly connected to the hovered token
    // All other edges (internal or external) are grey
    var isHoveredEdge = item.fromIdx === segIdx || item.toIdx === segIdx;
    var style = getUdHoveredEdgeStyle(item, segIdx, hoveredPartIdx, isHoveredEdge);
    var strokeColor = style.strokeColor;
    var strokeWidth = style.strokeWidth;
    var strokeOpacity = style.strokeOpacity;
    var arrowheadId = style.arrowheadId;
    path.setAttribute(
      'style',
      'stroke: ' +
        strokeColor +
        '; ' +
        'stroke-width: ' +
        strokeWidth +
        '; ' +
        'opacity: ' +
        strokeOpacity +
        '; ' +
        'fill: none;'
    );
    path.setAttribute('marker-end', 'url(#' + arrowheadId + ')');
    svg.appendChild(path);
    tokenFragmentsState.udActivePaths.push(path);
    if (isHoveredEdge) {
      appendDepDescriptionForParentArrow(svg, segIdx, item, x2, y2, controlY);
    }
  });
}
export function drawUdLinesForToken(segIdx, hoveredPartIdx) {
  tokenFragmentsState.udGrammarAnchor = null;
  if (
    !dependencyPopupState.displaySettings.udOverlay ||
    !dependencyState.latestUdOverlay ||
    !dependencyState.latestUdOverlay.ok
  ) {
    hideUdLines();
    return;
  }
  var canonicalIdx = getCanonicalSegIdx(segIdx);
  if (getMwtPartsForSeg(canonicalIdx).length && normalizeUdPartIndex(hoveredPartIdx) === null) {
    hideUdLines();
    return;
  }
  if (dependencyPopupState.displaySettings.bottomUpChunk) {
    drawUdLinesForBottomUpChunk(canonicalIdx, hoveredPartIdx);
  } else if (dependencyPopupState.displaySettings.contextWindow) {
    drawUdLinesForContextWindow(canonicalIdx, hoveredPartIdx);
  } else if (dependencyPopupState.displaySettings.connectedIslands) {
    drawUdLinesForConnectedIslands(canonicalIdx, hoveredPartIdx);
  } else if (dependencyPopupState.displaySettings.islandDepTree) {
    drawUdLinesForIsland(canonicalIdx, hoveredPartIdx);
  } else {
    drawUdLinesForClause(canonicalIdx, hoveredPartIdx);
  }
}
export function getUdInfoForSegment(segIdx) {
  if (!dependencyState.latestUdOverlay || !dependencyState.latestUdOverlay.ok) return null;
  var canonicalIdx = getCanonicalSegIdx(segIdx);
  if (dependencyState.latestUdTokenMap && dependencyState.latestUdTokenMap[canonicalIdx])
    return dependencyState.latestUdTokenMap[canonicalIdx];
  return null;
}
export function getUdEdgesForSegment(segIdx) {
  if (!dependencyState.latestUdOverlay || !dependencyState.latestUdOverlay.ok) return [];
  var edges = dependencyState.latestUdOverlay.edges || [];
  return edges.filter(function (e) {
    return e.from === segIdx || e.to === segIdx;
  });
}
export function initializeDependencyHover() {
  dependencyHoverState.cachedBottomUpChunkTokens = null;
  dependencyHoverState.cachedBottomUpChunkSegIdx = '';
  dependencyHoverState.cachedBottomUpCascadeTokens = null;
  dependencyHoverState.cachedBottomUpCascadeSegIdx = '';
  return true;
}
