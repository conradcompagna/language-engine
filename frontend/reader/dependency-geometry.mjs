import { dependencyGeometryState } from './dependency-geometry.state.mjs';
import {
  buildUdEdgeDrawKey,
  getUdExplicitPartEdgeFlags,
  getUdHoverRelation,
  getUdHoveredEdgeStyle,
  getUdInfoForSegment,
  normalizeUdPartIndex,
  shouldIncludeUdEdgeForHoveredPart
} from './dependency-hover.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { glossRequestsState } from './gloss-requests.state.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { appendDepDescriptionForParentArrow } from './orthography.mjs';
import { ensureUdRectCache, ensureUdSvgOverlay, getUdAnchorRect, hideUdLines } from './token-fragments.mjs';
import { tokenFragmentsState } from './token-fragments.state.mjs';
export function drawUdLinesForClause(segIdx, hoveredPartIdx) {
  hideUdLines();
  if (!dependencyPopupState.latestChunks || !dependencyPopupState.latestChunks.clauseGroup) return;
  var svg = ensureUdSvgOverlay();
  ensureUdRectCache();
  var edges = dependencyState.latestUdOverlay.edges || [];

  // Get the clause group for the current token (clauseGroup is a Map)
  var clauseGroupId = dependencyPopupState.latestChunks.clauseGroup.get(segIdx);
  if (clauseGroupId === undefined || clauseGroupId === 0) return;

  // Build set of all tokens in this clause
  var clauseMembers = new Set();
  dependencyPopupState.latestChunks.clauseGroup.forEach(function (grp, seg) {
    if (grp === clauseGroupId) {
      clauseMembers.add(seg);
    }
  });

  // Determine which tokens are "highlighted" (connected edges shown vivid)
  var highlightedTokens = getUdLineHighlightSet(segIdx);
  var explicitPartFlags = getUdExplicitPartEdgeFlags(segIdx);
  var edgesToDraw = [];
  var drawnPairs = new Set();
  edges.forEach(function (edge) {
    var fromInClause = clauseMembers.has(edge.from);
    var toInClause = clauseMembers.has(edge.to);

    // Only draw edges that touch the clause
    if (!fromInClause && !toInClause) return;
    if (!shouldIncludeUdEdgeForHoveredPart(edge, segIdx, hoveredPartIdx, explicitPartFlags)) return;
    var pairKey = buildUdEdgeDrawKey(edge.from, edge.to, edge.from_part, edge.to_part);
    if (drawnPairs.has(pairKey)) return;

    // Determine color based on edge direction and relationship to hovered token
    // edge.from is parent, edge.to is child
    var isChildLine;
    var hoverRelation = getUdHoverRelation(edge, segIdx, hoveredPartIdx);
    if (edge.from === segIdx) {
      // Hovered token is the parent -> orange (child line)
      isChildLine = true;
    } else if (edge.to === segIdx) {
      // Hovered token is the child -> blue (parent line)
      isChildLine = false;
    } else if (fromInClause && toInClause) {
      // Internal edge not directly involving hovered token
      // Default to parent->child direction: orange
      isChildLine = true;
    } else if (fromInClause) {
      // Edge from clause (parent) to external (child) -> orange
      isChildLine = true;
    } else {
      // Edge from external (parent) to clause (child) -> blue
      isChildLine = false;
    }
    edgesToDraw.push({
      fromIdx: edge.from,
      toIdx: edge.to,
      fromPart: normalizeUdPartIndex(edge.from_part),
      toPart: normalizeUdPartIndex(edge.to_part),
      isChildLine: isChildLine,
      hoverRelation: hoverRelation,
      dep: String(edge.dep || '')
    });
    drawnPairs.add(pairKey);
  });

  // Draw all edges
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

    // Check if this edge is connected to highlighted tokens
    var isConnected = highlightedTokens.has(item.fromIdx) || highlightedTokens.has(item.toIdx);
    var isHoveredEdge = item.fromIdx === segIdx || item.toIdx === segIdx;
    var style = getUdHoveredEdgeStyle(item, segIdx, hoveredPartIdx, isConnected);
    var strokeColor = style.strokeColor;
    var strokeWidth = style.strokeWidth;
    var strokeOpacity = style.strokeOpacity;
    var arrowheadId = style.arrowheadId;

    // Use inline style to ensure it overrides CSS
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
export function getIslandSpanForSeg(segIdx) {
  if (!hoverLayoutState.latestData || !Array.isArray(hoverLayoutState.latestData.island_spans)) return null;
  for (var i = 0; i < hoverLayoutState.latestData.island_spans.length; i++) {
    var span = hoverLayoutState.latestData.island_spans[i];
    if (segIdx >= span[0] && segIdx < span[1]) return span;
  }
  return null;
}
export function areIslandsConnected(span1, span2) {
  // Check if any dependency edge connects tokens between two islands
  if (!dependencyState.latestUdOverlay || !dependencyState.latestUdOverlay.ok) return false;
  if (!span1 || !span2) return false;
  var edges = dependencyState.latestUdOverlay.edges || [];
  var members1 = new Set();
  var members2 = new Set();
  for (var i = span1[0]; i < span1[1]; i++) members1.add(i);
  for (var i = span2[0]; i < span2[1]; i++) members2.add(i);

  // Check if any edge connects the two islands (bidirectional)
  for (var i = 0; i < edges.length; i++) {
    var edge = edges[i];
    var fromIn1 = members1.has(edge.from);
    var fromIn2 = members2.has(edge.from);
    var toIn1 = members1.has(edge.to);
    var toIn2 = members2.has(edge.to);

    // Connection exists if edge goes from island1 to island2 or vice versa
    if ((fromIn1 && toIn2) || (fromIn2 && toIn1)) {
      return true;
    }
  }
  return false;
}
export function collectConnectedGroupMembers(allSpans, startIdx, endIdx) {
  var members = new Set();
  var maxSeg = -1;
  for (var i = startIdx; i <= endIdx; i++) {
    var span = allSpans[i];
    for (var j = span[0]; j < span[1]; j++) {
      members.add(j);
      if (j > maxSeg) maxSeg = j;
    }
  }
  return {
    members: members,
    maxSeg: maxSeg
  };
}
export function findLeadingOutEdge(members, maxSeg, sentEnd) {
  if (!dependencyState.latestUdOverlay || !dependencyState.latestUdOverlay.ok) return null;
  var tokens = dependencyState.latestUdOverlay.tokens || [];

  // Find the token in the group whose head is outside the group and to the right
  for (var i = 0; i < tokens.length; i++) {
    var tok = tokens[i];
    var tokIdx = tok.i;
    var headIdx = Array.isArray(tok.heads) ? tok.heads[0] : tok.head;

    // Token must be in the group
    if (!members.has(tokIdx)) continue;

    // Head must be outside the group
    if (members.has(headIdx)) continue;

    // Head must be to the right (leading edge goes rightward/downward)
    if (headIdx <= maxSeg) continue;

    // Head must be within sentence bounds
    if (typeof sentEnd === 'number' && headIdx >= sentEnd) continue;

    // Found the group's attachment point
    return {
      from: headIdx,
      // the external head
      to: tokIdx,
      // the token in the group
      dep: tok.dep,
      upos: tok.upos
    };
  }
  return null;
}
export function isVerbAclHead(segIdx) {
  var info = getUdInfoForSegment(segIdx);
  if (!info) return false;
  var upos = (info.upos || '').toUpperCase();
  var dep = (info.dep || '').toLowerCase();
  return upos === 'VERB' && dep === 'acl';
}
export function isRootSeg(segIdx) {
  if (!dependencyState.latestUdOverlay || !dependencyState.latestUdOverlay.ok) return false;
  if (!Array.isArray(dependencyState.latestUdOverlay.roots)) return false;
  if (dependencyState.latestUdOverlay.roots.indexOf(segIdx) !== -1) return true;
  var info = getUdInfoForSegment(segIdx);
  if (!info) return false;
  if (info.head === info.i) return true;
  var dep = (info.dep || '').toLowerCase();
  return dep === 'root';
}
export function getSentenceSpansFromSegments(segments) {
  var spans = [];
  if (!Array.isArray(segments) || !segments.length) return spans;
  var start = 0;
  for (var i = 0; i < segments.length; i++) {
    if (
      segments[i] === '\u104b' ||
      segments[i] === '\u3002' ||
      segments[i] === '\uff01' ||
      segments[i] === '\uff1f'
    ) {
      // sentence-ending punctuation (Myanmar/CJK)
      spans.push({
        start: start,
        end: i + 1
      });
      start = i + 1;
    }
  }
  if (start < segments.length)
    spans.push({
      start: start,
      end: segments.length
    });
  return spans;
}
export function buildConnectedIslandGroupsForSentence(allSpans, spanIndices) {
  var groups = [];
  if (!spanIndices.length) return groups;
  var startIdx = spanIndices[0];
  var prevIdx = spanIndices[0];
  for (var i = 1; i < spanIndices.length; i++) {
    var idx = spanIndices[i];
    if (!areIslandsConnected(allSpans[prevIdx], allSpans[idx])) {
      groups.push({
        startIdx: startIdx,
        endIdx: prevIdx
      });
      startIdx = idx;
    }
    prevIdx = idx;
  }
  groups.push({
    startIdx: startIdx,
    endIdx: prevIdx
  });
  return groups;
}
export function absorbStrayParticles(allSpans, groups, sentEnd) {
  // Absorb groups that are adjacent in island sequence, connect backward, and have no forward edge
  if (groups.length < 2) return groups;
  var tokens = (dependencyState.latestUdOverlay && dependencyState.latestUdOverlay.tokens) || [];
  var result = [groups[0]];
  for (var gi = 1; gi < groups.length; gi++) {
    var prevGroup = result[result.length - 1];
    var currGroup = groups[gi];
    // Check adjacency: current group's first island immediately follows prev group's last island
    if (currGroup.startIdx !== prevGroup.endIdx + 1) {
      result.push(currGroup);
      continue;
    }
    // Check if current group has no forward edges
    var currInfo = collectConnectedGroupMembers(allSpans, currGroup.startIdx, currGroup.endIdx);
    var forwardEdge = findLeadingOutEdge(currInfo.members, currInfo.maxSeg, sentEnd);
    if (forwardEdge) {
      result.push(currGroup);
      continue;
    }
    // Check if current group has backward connection to prev group
    var prevInfo = collectConnectedGroupMembers(allSpans, prevGroup.startIdx, prevGroup.endIdx);
    var hasBackwardEdge = false;
    for (var ti = 0; ti < tokens.length; ti++) {
      var tok = tokens[ti];
      if (!currInfo.members.has(tok.i)) continue;
      var tokHeadForCheck = Array.isArray(tok.heads) ? tok.heads[0] : tok.head;
      if (prevInfo.members.has(tokHeadForCheck)) {
        hasBackwardEdge = true;
        break;
      }
    }
    if (!hasBackwardEdge) {
      result.push(currGroup);
      continue;
    }
    // Absorb: extend prev group to include curr group
    result[result.length - 1] = {
      startIdx: prevGroup.startIdx,
      endIdx: currGroup.endIdx
    };
  }
  return result;
}
export function applyAclGatePostpass(allSpans, groups, sentEnd) {
  if (!dependencyPopupState.displaySettings.connectedIslandsAclGate) return groups;
  var merged = [];
  var gi = 0;
  while (gi < groups.length) {
    var mergedStart = groups[gi].startIdx;
    var mergedEnd = groups[gi].endIdx;
    var current = gi;
    while (true) {
      // Check the CURRENT (most recently added) group's leading edge
      var currInfo = collectConnectedGroupMembers(allSpans, groups[current].startIdx, groups[current].endIdx);
      var currLeadingEdge = findLeadingOutEdge(currInfo.members, currInfo.maxSeg, sentEnd);
      if (!currLeadingEdge) {
        // No forward edge - stop merging
        break;
      }
      var headSeg = currLeadingEdge.to;
      if (isRootSeg(headSeg) || isVerbAclHead(headSeg)) {
        // Current group is a clause boundary - stop merging
        break;
      }

      // Current group is NOT a clause boundary, merge with next group
      if (current + 1 >= groups.length) break;
      current += 1;
      mergedEnd = groups[current].endIdx;
      // Loop continues - will check the newly merged group's edge
    }
    merged.push({
      startIdx: mergedStart,
      endIdx: mergedEnd
    });
    gi = current + 1;
  }
  return merged;
}
export function rebuildConnectedIslandGroups() {
  dependencyGeometryState.latestConnectedIslandGroups = [];
  dependencyGeometryState.latestConnectedIslandGroupBySeg = new Map();
  if (!hoverLayoutState.latestData || !Array.isArray(hoverLayoutState.latestData.island_spans)) return;
  var allSpans = hoverLayoutState.latestData.island_spans;
  if (!allSpans.length) return;
  var segments = Array.isArray(hoverLayoutState.latestData.segments)
    ? hoverLayoutState.latestData.segments
    : [];
  var sentenceSpans = getSentenceSpansFromSegments(segments);
  if (!sentenceSpans.length) {
    sentenceSpans = [
      {
        start: 0,
        end: segments.length
      }
    ];
  }
  var spanIdx = 0;
  sentenceSpans.forEach(function (sent) {
    var spanIndices = [];
    while (spanIdx < allSpans.length && allSpans[spanIdx][0] < sent.end) {
      if (allSpans[spanIdx][0] >= sent.start) {
        spanIndices.push(spanIdx);
      }
      spanIdx++;
    }
    if (!spanIndices.length) return;
    var groups = buildConnectedIslandGroupsForSentence(allSpans, spanIndices);
    groups = absorbStrayParticles(allSpans, groups, sent.end);
    groups = applyAclGatePostpass(allSpans, groups, sent.end);
    groups.forEach(function (g) {
      var groupSpans = [];
      for (var i = g.startIdx; i <= g.endIdx; i++) {
        groupSpans.push(allSpans[i]);
      }
      var groupObj = {
        spans: groupSpans,
        startIdx: g.startIdx,
        endIdx: g.endIdx
      };
      dependencyGeometryState.latestConnectedIslandGroups.push(groupObj);
      var info = collectConnectedGroupMembers(allSpans, g.startIdx, g.endIdx);
      info.members.forEach(function (seg) {
        dependencyGeometryState.latestConnectedIslandGroupBySeg.set(seg, groupObj);
      });
    });
  });
}
export function getConnectedIslandGroup(segIdx) {
  // Returns a list of island spans that form a connected group
  if (!hoverLayoutState.latestData || !Array.isArray(hoverLayoutState.latestData.island_spans)) return null;
  if (!dependencyGeometryState.latestConnectedIslandGroupBySeg) rebuildConnectedIslandGroups();
  var group = dependencyGeometryState.latestConnectedIslandGroupBySeg
    ? dependencyGeometryState.latestConnectedIslandGroupBySeg.get(segIdx)
    : null;
  if (group && group.spans) return group.spans;
  var fallback = getIslandSpanForSeg(segIdx);
  return fallback ? [fallback] : null;
}
export function drawUdLinesForIsland(segIdx, hoveredPartIdx) {
  hideUdLines();
  if (!dependencyState.latestUdOverlay || !dependencyState.latestUdOverlay.ok) return;
  var span = getIslandSpanForSeg(segIdx);
  if (!span) return;
  var svg = ensureUdSvgOverlay();
  ensureUdRectCache();
  var edges = dependencyState.latestUdOverlay.edges || [];
  var islandMembers = new Set();
  for (var i = span[0]; i < span[1]; i++) {
    islandMembers.add(i);
  }
  var highlightedTokens = getUdLineHighlightSet(segIdx);
  var explicitPartFlags = getUdExplicitPartEdgeFlags(segIdx);
  var edgesToDraw = [];
  var drawnPairs = new Set();
  edges.forEach(function (edge) {
    var fromInIsland = islandMembers.has(edge.from);
    var toInIsland = islandMembers.has(edge.to);
    if (!fromInIsland && !toInIsland) return;
    if (!shouldIncludeUdEdgeForHoveredPart(edge, segIdx, hoveredPartIdx, explicitPartFlags)) return;
    var pairKey = buildUdEdgeDrawKey(edge.from, edge.to, edge.from_part, edge.to_part);
    if (drawnPairs.has(pairKey)) return;
    var isChildLine;
    var hoverRelation = getUdHoverRelation(edge, segIdx, hoveredPartIdx);
    if (edge.from === segIdx) {
      isChildLine = true;
    } else if (edge.to === segIdx) {
      isChildLine = false;
    } else if (fromInIsland && toInIsland) {
      isChildLine = true;
    } else if (fromInIsland) {
      isChildLine = true;
    } else {
      isChildLine = false;
    }
    edgesToDraw.push({
      fromIdx: edge.from,
      toIdx: edge.to,
      fromPart: normalizeUdPartIndex(edge.from_part),
      toPart: normalizeUdPartIndex(edge.to_part),
      isChildLine: isChildLine,
      hoverRelation: hoverRelation,
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
    var isConnected = highlightedTokens.has(item.fromIdx) || highlightedTokens.has(item.toIdx);
    var isHoveredEdge = item.fromIdx === segIdx || item.toIdx === segIdx;
    var style = getUdHoveredEdgeStyle(item, segIdx, hoveredPartIdx, isConnected);
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
export function drawUdLinesForConnectedIslands(segIdx, hoveredPartIdx) {
  hideUdLines();
  if (!dependencyState.latestUdOverlay || !dependencyState.latestUdOverlay.ok) return;
  var connectedSpans = getConnectedIslandGroup(segIdx);
  if (!connectedSpans || connectedSpans.length === 0) return;
  var svg = ensureUdSvgOverlay();
  ensureUdRectCache();
  var edges = dependencyState.latestUdOverlay.edges || [];

  // Build set of all tokens in connected island group
  var groupMembers = new Set();
  connectedSpans.forEach(function (span) {
    for (var i = span[0]; i < span[1]; i++) {
      groupMembers.add(i);
    }
  });
  var highlightedTokens = getUdLineHighlightSet(segIdx);
  var explicitPartFlags = getUdExplicitPartEdgeFlags(segIdx);
  var edgesToDraw = [];
  var drawnPairs = new Set();
  edges.forEach(function (edge) {
    var fromInGroup = groupMembers.has(edge.from);
    var toInGroup = groupMembers.has(edge.to);
    if (!fromInGroup && !toInGroup) return;
    if (!shouldIncludeUdEdgeForHoveredPart(edge, segIdx, hoveredPartIdx, explicitPartFlags)) return;
    var pairKey = buildUdEdgeDrawKey(edge.from, edge.to, edge.from_part, edge.to_part);
    if (drawnPairs.has(pairKey)) return;
    var isChildLine;
    var hoverRelation = getUdHoverRelation(edge, segIdx, hoveredPartIdx);
    if (edge.from === segIdx) {
      isChildLine = true;
    } else if (edge.to === segIdx) {
      isChildLine = false;
    } else if (fromInGroup && toInGroup) {
      isChildLine = true;
    } else if (fromInGroup) {
      isChildLine = true;
    } else {
      isChildLine = false;
    }
    edgesToDraw.push({
      fromIdx: edge.from,
      toIdx: edge.to,
      fromPart: normalizeUdPartIndex(edge.from_part),
      toPart: normalizeUdPartIndex(edge.to_part),
      isChildLine: isChildLine,
      hoverRelation: hoverRelation,
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
    var isConnected = highlightedTokens.has(item.fromIdx) || highlightedTokens.has(item.toIdx);
    var isHoveredEdge = item.fromIdx === segIdx || item.toIdx === segIdx;
    var style = getUdHoveredEdgeStyle(item, segIdx, hoveredPartIdx, isConnected);
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

// Helper: get the canonical segment index (first segment if part of collapsed NER span)
export function getCanonicalSegIdx(segIdx) {
  var info = dependencyState.latestCollapsedSpanInfo[segIdx];
  return info ? info.firstSeg : segIdx;
}

// Helper: expand a set of segment indices to include all segments in any collapsed spans
export function expandHighlightSetForCollapsedSpans(segSet) {
  var expanded = new Set(segSet);
  segSet.forEach(function (segIdx) {
    var info = dependencyState.latestCollapsedSpanInfo[segIdx];
    if (info && info.udTok && info.udTok.seg_span) {
      info.udTok.seg_span.forEach(function (si) {
        expanded.add(si);
      });
    }
  });
  return expanded;
}
export function getUdLineHighlightSet(segIdx) {
  // Use canonical segment index for lookup (first segment if part of collapsed span)
  var canonicalIdx = getCanonicalSegIdx(segIdx);
  var base =
    glossRequestsState.currentChunkHighlightTokens &&
    glossRequestsState.currentChunkHighlightTokens.has(canonicalIdx)
      ? new Set(glossRequestsState.currentChunkHighlightTokens)
      : new Set([canonicalIdx]);
  // Expand to include all segments in collapsed spans
  return expandHighlightSetForCollapsedSpans(base);
}

// Context Window algorithm - computes tokens to highlight based on tree-contiguous spans
// Highlight the dependency context around the selected token.
export function computeContextWindowTokens(segIdx) {
  // Use canonical segment index (first segment if part of collapsed NER span)
  var canonicalIdx = getCanonicalSegIdx(segIdx);
  if (!dependencyState.latestUdOverlay || !dependencyState.latestUdOverlay.ok)
    return expandHighlightSetForCollapsedSpans(new Set([canonicalIdx]));
  var count = parseInt(dependencyPopupState.displaySettings.contextWindowSize, 10);
  if (!isFinite(count) || count < 1) count = 1;
  var tokens = dependencyState.latestUdOverlay.tokens || [];
  var edges = dependencyState.latestUdOverlay.edges || [];
  function normalizeSentences(raw) {
    var out = [];
    if (!Array.isArray(raw)) return out;
    for (var i = 0; i < raw.length; i++) {
      var s = raw[i];
      if (Array.isArray(s) && s.length >= 2 && isFinite(s[0]) && isFinite(s[1])) {
        out.push([s[0], s[1]]);
        continue;
      }
      if (s && typeof s === 'object') {
        var start =
          typeof s.seg_start === 'number' ? s.seg_start : typeof s.start === 'number' ? s.start : null;
        var end = typeof s.seg_end === 'number' ? s.seg_end : typeof s.end === 'number' ? s.end : null;
        if (start !== null && end !== null) {
          out.push([start, end]);
        }
      }
    }
    return out;
  }
  var sentences = normalizeSentences(dependencyState.latestUdOverlay.sentences || []);
  if (!sentences.length) {
    if (Array.isArray(hoverLayoutState.latestSegments) && hoverLayoutState.latestSegments.length) {
      var fallbackSpans = getSentenceSpansFromSegments(hoverLayoutState.latestSegments);
      for (var fs = 0; fs < fallbackSpans.length; fs++) {
        sentences.push([fallbackSpans[fs].start, fallbackSpans[fs].end]);
      }
    } else if (tokens.length) {
      var maxSeg = -1;
      for (var tm = 0; tm < tokens.length; tm++) {
        var ti = tokens[tm] && typeof tokens[tm].i === 'number' ? tokens[tm].i : -1;
        if (ti > maxSeg) maxSeg = ti;
      }
      if (maxSeg >= 0) sentences.push([0, maxSeg + 1]);
    }
  }

  // Find which sentence this token belongs to
  var sentenceIdx = null;
  for (var si = 0; si < sentences.length; si++) {
    var sentSpan = sentences[si];
    if (canonicalIdx >= sentSpan[0] && canonicalIdx < sentSpan[1]) {
      sentenceIdx = si;
      break;
    }
  }
  if (sentenceIdx === null) return expandHighlightSetForCollapsedSpans(new Set([canonicalIdx]));

  // 1. Get all tokens in sentence, sorted by position
  var sentSpan = sentences[sentenceIdx];
  var nodesInSentence = [];
  for (var ti2 = 0; ti2 < tokens.length; ti2++) {
    var tok = tokens[ti2];
    if (!tok || typeof tok.i !== 'number') continue;
    if (tok.i >= sentSpan[0] && tok.i < sentSpan[1]) {
      nodesInSentence.push(tok.i);
    }
  }
  if (!nodesInSentence.length) return expandHighlightSetForCollapsedSpans(new Set([canonicalIdx]));
  nodesInSentence.sort(function (a, b) {
    return a - b;
  });
  var centerPos = nodesInSentence.indexOf(canonicalIdx);
  if (centerPos === -1) return expandHighlightSetForCollapsedSpans(new Set([canonicalIdx]));

  // Position lookup
  var posBySeg = {};
  for (var pi = 0; pi < nodesInSentence.length; pi++) {
    posBySeg[nodesInSentence[pi]] = pi;
  }

  // 2. Build tree adjacency map (bidirectional)
  var treeAdj = new Map();
  for (var ei = 0; ei < edges.length; ei++) {
    var edge = edges[ei];
    var head = edge.from;
    var child = edge.to;
    // Only include edges within this sentence
    if (posBySeg[head] === undefined || posBySeg[child] === undefined) continue;
    if (!treeAdj.has(head)) treeAdj.set(head, new Set());
    if (!treeAdj.has(child)) treeAdj.set(child, new Set());
    treeAdj.get(head).add(child);
    treeAdj.get(child).add(head);
  }

  // 3. Collect candidates: expand purely positionally (centered on hover)
  var left = centerPos;
  var right = centerPos;
  // Collect up to 2x count to have room for finding best span
  var targetCandidates = Math.min(nodesInSentence.length, count * 2);
  while (right - left + 1 < targetCandidates) {
    var expandedAny = false;
    if (left > 0) {
      left--;
      expandedAny = true;
    }
    if (right - left + 1 < targetCandidates && right < nodesInSentence.length - 1) {
      right++;
      expandedAny = true;
    }
    if (!expandedAny) break;
  }
  var candidates = nodesInSentence.slice(left, right + 1);
  var hoverIdxInCandidates = candidates.indexOf(canonicalIdx);

  // 4. Helper: check if a span is tree-contiguous (all tokens connected via tree edges within the span)
  function isTreeContiguous(spanTokens) {
    if (spanTokens.length <= 1) return true;
    var spanSet = new Set(spanTokens);
    var visited = new Set();
    var queue = [spanTokens[0]];
    visited.add(spanTokens[0]);
    while (queue.length > 0) {
      var curr = queue.shift();
      var neighbors = treeAdj.get(curr);
      if (neighbors) {
        neighbors.forEach(function (n) {
          if (spanSet.has(n) && !visited.has(n)) {
            visited.add(n);
            queue.push(n);
          }
        });
      }
    }
    return visited.size === spanTokens.length;
  }

  // 5. Find largest tree-contiguous span containing hover token
  // Priorities: 1) larger size, 2) more centered on hover, 3) slight rightward bias
  var bestSpan = [canonicalIdx];
  var bestSize = 1;
  var bestImbalance = 0;
  var bestRight = hoverIdxInCandidates;
  for (var L = 0; L <= hoverIdxInCandidates; L++) {
    for (var R = hoverIdxInCandidates; R < candidates.length; R++) {
      var spanSize = R - L + 1;
      if (spanSize > count) break;
      if (spanSize < bestSize) continue;
      var leftExtent = hoverIdxInCandidates - L;
      var rightExtent = R - hoverIdxInCandidates;
      var imbalance = Math.abs(leftExtent - rightExtent);
      var dominated = false;
      if (spanSize === bestSize) {
        if (imbalance > bestImbalance) {
          dominated = true;
        } else if (imbalance === bestImbalance && R <= bestRight) {
          dominated = true;
        }
      }
      if (dominated) continue;
      var span = candidates.slice(L, R + 1);
      if (isTreeContiguous(span)) {
        bestSpan = span;
        bestSize = spanSize;
        bestImbalance = imbalance;
        bestRight = R;
      }
    }
  }
  var highlightedTokens = new Set(bestSpan);

  // 6. Expand for whitespace islands (if latestData has island_spans)
  if (hoverLayoutState.latestData && Array.isArray(hoverLayoutState.latestData.island_spans)) {
    var islands = hoverLayoutState.latestData.island_spans;
    var islandBySeg = {};
    for (var ii = 0; ii < islands.length; ii++) {
      var island = islands[ii];
      for (var ij = island[0]; ij < island[1]; ij++) {
        islandBySeg[ij] = island;
      }
    }
    var toAdd = [];
    highlightedTokens.forEach(function (seg) {
      var island = islandBySeg[seg];
      if (island) {
        for (var ik = island[0]; ik < island[1]; ik++) {
          toAdd.push(ik);
        }
      }
    });
    for (var ti = 0; ti < toAdd.length; ti++) {
      highlightedTokens.add(toAdd[ti]);
    }
  }

  // 7. Roll in contiguous singleton leaf children
  var hasChild = {};
  for (var e = 0; e < edges.length; e++) {
    var edge2 = edges[e];
    if (posBySeg[edge2.from] !== undefined) {
      hasChild[edge2.from] = true;
    }
  }
  function isContiguousToHighlighted(seg) {
    var pos = posBySeg[seg];
    if (pos === undefined) return false;
    var leftN = pos > 0 ? nodesInSentence[pos - 1] : null;
    var rightN = pos < nodesInSentence.length - 1 ? nodesInSentence[pos + 1] : null;
    return (
      (leftN !== null && highlightedTokens.has(leftN)) || (rightN !== null && highlightedTokens.has(rightN))
    );
  }
  var added = true;
  while (added) {
    added = false;
    for (var le = 0; le < edges.length; le++) {
      var leafEdge = edges[le];
      var head3 = leafEdge.from;
      var child3 = leafEdge.to;
      if (!highlightedTokens.has(head3) || highlightedTokens.has(child3)) continue;
      if (hasChild[child3]) continue;
      if (posBySeg[child3] === undefined) continue;
      if (isContiguousToHighlighted(child3)) {
        highlightedTokens.add(child3);
        added = true;
      }
    }
  }

  // 8. Final validation: ensure tree-contiguous (BFS from hover, keep only reachable)
  var connected = new Set();
  var stack = [canonicalIdx];
  while (stack.length) {
    var cur = stack.pop();
    if (connected.has(cur)) continue;
    connected.add(cur);
    var neighbors = treeAdj.get(cur);
    if (neighbors) {
      neighbors.forEach(function (n) {
        if (highlightedTokens.has(n) && !connected.has(n)) {
          stack.push(n);
        }
      });
    }
  }

  // 9. Ensure positionally contiguous (find largest contiguous run containing hover)
  var connectedArray = Array.from(connected).sort(function (a, b) {
    return a - b;
  });
  if (connectedArray.length > 1) {
    var connectedSet = new Set(connectedArray);
    var hoverAllPos = posBySeg[canonicalIdx];
    var runLeft = hoverAllPos;
    var runRight = hoverAllPos;
    while (runLeft > 0 && connectedSet.has(nodesInSentence[runLeft - 1])) runLeft--;
    while (runRight < nodesInSentence.length - 1 && connectedSet.has(nodesInSentence[runRight + 1]))
      runRight++;
    var finalHighlighted = new Set();
    for (var ri = runLeft; ri <= runRight; ri++) {
      var seg = nodesInSentence[ri];
      if (connectedSet.has(seg)) {
        finalHighlighted.add(seg);
      }
    }
    highlightedTokens = finalHighlighted;
  } else {
    highlightedTokens = connected;
  }

  // Expand result to include all segments in collapsed NER spans
  return expandHighlightSetForCollapsedSpans(highlightedTokens);
}

// Cache for context window tokens to ensure sync between highlighting and lines
export function initializeDependencyGeometry() {
  dependencyGeometryState.latestConnectedIslandGroups = null;
  dependencyGeometryState.latestConnectedIslandGroupBySeg = null;
  dependencyGeometryState.cachedContextWindowTokens = null;
  dependencyGeometryState.cachedContextWindowSegIdx = -1;
  return true;
}
