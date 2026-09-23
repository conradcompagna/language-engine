import { getUdInfoForSegment } from './dependency-hover.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import {
  getLookupEntryFillMode,
  getLookupEntryResolution,
  getPrecomputedKoreanCompoundLemmaChildren
} from './entry-editing.mjs';
import { applyInvisibleDictFillHitTargets } from './fill-rendering.mjs';
import { resolveSegmentPosData } from './fill-slices.mjs';
import { uposColorForTag } from './gloss-requests.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import {
  _buildMwtSpawnLookupContext,
  _clearMwtSpawnContent,
  _cloneMwtSpawnFillRow,
  _createMwtSpawnToken,
  _ensureMwtSpawnBox,
  _positionMwtSpawnBox,
  _updateMwtSpawnShield
} from './mwt-context.mjs';
import { mwtContextState } from './mwt-context.state.mjs';
import { hasSameVisibleComparisonText } from './presentation.mjs';
import { buildTokenMapLookupRequestOptions } from './token-banner.mjs';
export function _remapSpawnFillHitIndexes(inner, origIndexes) {
  if (!inner || !inner.querySelectorAll || !Array.isArray(origIndexes) || !origIndexes.length) return;
  var hits = inner.querySelectorAll('.reader-token-fill-hit');
  for (var i = 0; i < hits.length; i++) {
    var hit = hits[i];
    var raw = String(hit.dataset.fillIndexes || '');
    if (!raw) continue;
    var mapped = raw
      .split(',')
      .map(function (s) {
        var n = parseInt(s, 10);
        if (!isFinite(n) || n < 0 || n >= origIndexes.length) return '';
        return String(origIndexes[n]);
      })
      .filter(function (s) {
        return s !== '';
      });
    hit.dataset.fillIndexes = mapped.join(',');
    if (mapped.length === 1) hit.dataset.fillIndex = mapped[0];
    else delete hit.dataset.fillIndex;
  }
}
export function showMwtSpawnBox(anchorEl, segIdx, partIdx, childText, parentResult) {
  var box = _ensureMwtSpawnBox();
  if (!box || !anchorEl) return;
  var key = String(segIdx) + ':' + String(partIdx);
  if (
    mwtContextState._mwtSpawnActive &&
    mwtContextState._mwtSpawnActive.key === key &&
    box.style.display !== 'none'
  ) {
    _updateMwtSpawnShield();
    return; // already showing for this anchor
  }
  var content = _clearMwtSpawnContent(box);
  if (!content) return;
  var inner = _createMwtSpawnToken(childText, null);
  content.appendChild(inner);
  inner.textContent = childText;
  inner.dataset.seg = childText;
  inner.dataset.index = String(segIdx);
  inner.dataset.mwtPartIndex = String(partIdx);
  inner.dataset.mwtSurfaceSlice = String(
    (anchorEl && anchorEl.dataset && anchorEl.dataset.mwtSurfaceSlice) || ''
  ).trim();
  delete inner.dataset.hasFillHits;
  delete inner.__mwtSpawnContext;

  // Build dict-fill hit zones over the child text (not the surface).
  var spawnContext = _buildMwtSpawnLookupContext(segIdx, partIdx, childText, parentResult);
  if (spawnContext) {
    spawnContext.anchorText = String(
      (anchorEl && anchorEl.dataset && anchorEl.dataset.mwtSurfaceSlice) || ''
    ).trim();
    spawnContext.lookupText = String(childText || '').trim();
    spawnContext.popupReason = String(
      (anchorEl && anchorEl.dataset && anchorEl.dataset.mwtPopupReason) || ''
    ).trim();
    inner.__mwtSpawnContext = spawnContext;
    try {
      applyInvisibleDictFillHitTargets(
        inner,
        childText,
        Array.isArray(spawnContext.lookupResult && spawnContext.lookupResult.dict_fill)
          ? spawnContext.lookupResult.dict_fill
          : [],
        Array.isArray(spawnContext.lookupResult && spawnContext.lookupResult.dict_fill_surface_slices)
          ? spawnContext.lookupResult.dict_fill_surface_slices
          : null
      );
    } catch (err) {
      /* keep box usable even if fill-hit build fails */
    }
  }
  _positionMwtSpawnBox(box, anchorEl);
  mwtContextState._mwtSpawnActive = {
    key: key,
    segIdx: Number(segIdx),
    partIdx: Number(partIdx),
    childText: childText,
    anchorEl: anchorEl
  };
  _updateMwtSpawnShield();
}
export function _cloneKoreanCompoundPrecomputedLookupResult(lookup, childText, partIdx) {
  var src = lookup && typeof lookup === 'object' ? lookup : null;
  var child = String(childText || '').trim();
  if (!src || !child) return null;
  var out = {};
  for (var key in src) {
    if (!Object.prototype.hasOwnProperty.call(src, key)) continue;
    var value = src[key];
    out[key] = Array.isArray(value) ? value.slice() : value;
  }
  if (Array.isArray(src.dict_fill)) {
    out.dict_fill = src.dict_fill.map(function (row) {
      return _cloneMwtSpawnFillRow(row);
    });
  }
  if (Array.isArray(src.inspect_fill)) {
    out.inspect_fill = src.inspect_fill.map(function (row) {
      return _cloneMwtSpawnFillRow(row);
    });
  } else if (Array.isArray(out.dict_fill)) {
    out.inspect_fill = out.dict_fill.slice();
  }
  if (Array.isArray(src.dict_fill_surface_slices)) {
    out.dict_fill_surface_slices = src.dict_fill_surface_slices.map(function (slice) {
      var clone = {};
      var source = slice && typeof slice === 'object' ? slice : {};
      for (var sk in source) {
        if (!Object.prototype.hasOwnProperty.call(source, sk)) continue;
        clone[sk] = Array.isArray(source[sk]) ? source[sk].slice() : source[sk];
      }
      return clone;
    });
  }
  out.text = child;
  out.token_text = child;
  out.surface_form = child;
  if (!out.head) out.head = child;
  out.lookup_text = child;
  out._korean_compound_child_precomputed = true;
  if (isFinite(Number(partIdx))) out._korean_compound_part_index = Number(partIdx);
  return out;
}
export function _getPrecomputedKoreanCompoundLemmaChildLookup(partIdx, childText, parentResult) {
  var children = getPrecomputedKoreanCompoundLemmaChildren(parentResult);
  if (!children.length) return null;
  var wanted = Number(partIdx);
  var child = String(childText || '').trim();
  var fallback = null;
  for (var i = 0; i < children.length; i++) {
    var item = children[i] || {};
    var lookup = item.lookup || item.result || null;
    if (!lookup && (Array.isArray(item.dict_fill) || item.text != null)) lookup = item;
    if (!lookup) continue;
    var itemText = String(item.text || lookup.text || '').trim();
    var itemPartIdx = parseInt(item.part_index, 10);
    if (isFinite(wanted) && isFinite(itemPartIdx) && itemPartIdx === wanted) {
      return _cloneKoreanCompoundPrecomputedLookupResult(lookup, child || itemText, wanted);
    }
    if (!fallback && child && itemText && hasSameVisibleComparisonText(itemText, child)) {
      fallback = _cloneKoreanCompoundPrecomputedLookupResult(
        lookup,
        child,
        isFinite(wanted) ? wanted : itemPartIdx
      );
    }
  }
  return fallback;
}
export function _buildKoreanCompoundLemmaChildLookupResult(partIdx, childText, parentResult) {
  var surfaceText = String(childText || '').trim();
  var parentEntry = parentResult && typeof parentResult === 'object' ? parentResult : null;
  if (!surfaceText) return null;
  var precomputed = _getPrecomputedKoreanCompoundLemmaChildLookup(partIdx, surfaceText, parentEntry);
  return precomputed || null;
}
export function _buildKoreanCompoundLemmaSpawnContext(
  segIdx,
  partIdx,
  partText,
  parentResult,
  parentUdTok,
  parentSurface
) {
  var childText = String(partText || '').trim();
  if (!childText) return null;
  var parentPosData = resolveSegmentPosData(segIdx, parentResult, parentUdTok);
  var parentState = {
    segIdx: Number(segIdx),
    surface: String(parentSurface || '').trim(),
    lemma: String(
      (parentPosData && parentPosData.lemma) ||
        (parentResult && (parentResult.lemma_form || parentResult.lemma)) ||
        ''
    ),
    lemma_raw: String(
      (parentPosData && parentPosData.lemma_raw) || (parentResult && parentResult.lemma_raw) || ''
    ),
    posData: parentPosData || {},
    udTok: parentUdTok || null,
    entry: parentResult || null,
    tokenEntry: parentResult || null
  };
  var lookupOptions = buildTokenMapLookupRequestOptions('lemma-part', parentState, partIdx);
  var childPosData = {
    upos: String(lookupOptions.upos || ''),
    upos_label: String(lookupOptions.upos || ''),
    upos_color: uposColorForTag(String(lookupOptions.upos || '')),
    dep: '',
    dep_label: '',
    tag: String(lookupOptions.xpos || ''),
    xpos: String(lookupOptions.xpos || ''),
    lemma: childText,
    lemma_raw: childText,
    lemma_suffix: '',
    feats: ''
  };
  var childLookupResult = _buildKoreanCompoundLemmaChildLookupResult(partIdx, childText, parentResult);
  if (!childLookupResult) return null;
  return {
    segIdx: Number(segIdx),
    partIdx: Number(partIdx),
    childText: childText,
    lookupText: childText,
    anchorText: childText,
    parentSurface: String(parentSurface || '').trim(),
    popupReason: 'korean_compound_lemma',
    lookupResult: childLookupResult || null,
    lookupPending: false,
    lookupResolved: true,
    forceLookupOnClick: false,
    useChildAsClickSurface: true,
    isKoreanCompoundLemmaSpawn: true,
    parentResult: parentResult || null,
    parentState: parentState,
    lookupOptions: lookupOptions,
    posData: childPosData
  };
}
export function resetKoreanCompoundSpawnToken(inner, tokenText) {
  if (!inner) return;
  inner.textContent = String(tokenText || '');
  if (inner.dataset) delete inner.dataset.hasFillHits;
}
export function isKoreanCompoundSpawnInternalFill(entry, providedSlices) {
  if (!entry || typeof entry !== 'object') return false;
  var dictFill = Array.isArray(entry.dict_fill) ? entry.dict_fill : [];
  if (dictFill.length <= 1) return false;
  if (entry._korean_compound_child_internal_fill) return true;
  return Array.isArray(providedSlices) && providedSlices.length > 1;
}
export function getKoreanCompoundSpawnFillHitAtPoint(inner, clientX, clientY) {
  if (!inner || !inner.dataset || inner.dataset.hasFillHits !== '1') return null;
  if (!isFinite(Number(clientX)) || !isFinite(Number(clientY))) return null;
  var el = null;
  try {
    el = document.elementFromPoint(Number(clientX), Number(clientY));
  } catch (_err) {
    el = null;
  }
  var hit = el && el.closest ? el.closest('.reader-token-fill-hit') : null;
  return hit && inner.contains(hit) ? hit : null;
}
export function isKoreanCompoundSynthGreedyEntry(entry) {
  if (!entry || typeof entry !== 'object') return false;
  if (entry._korean_compound_child_internal_fill) return true;
  var resolution = getLookupEntryResolution(entry) || {};
  var category = String((resolution && resolution.category) || '')
    .trim()
    .toLowerCase();
  if (category.indexOf('greedy') >= 0) return true;
  var mode = getLookupEntryFillMode(entry);
  return !!(
    (mode === 'greedy' ||
      mode === 'lemma_greedy' ||
      mode === 'lemma_partial_greedy' ||
      mode === 'greedy_lemma_mismatch') &&
    Array.isArray(entry.dict_fill) &&
    entry.dict_fill.length > 1
  );
}
export function koreanCompoundSynthGroupHasGreedy(group) {
  var ctxs = group && Array.isArray(group.contexts) ? group.contexts : [];
  var hasGreedy = false;
  for (var i = 0; i < ctxs.length; i++) {
    var ctx = ctxs[i] || {};
    if (isKoreanCompoundSynthGreedyEntry(ctx.lookupResult)) {
      hasGreedy = true;
      break;
    }
  }
  if (group) group.hasGreedySynthHint = hasGreedy;
  return hasGreedy;
}
export function applyKoreanCompoundSpawnFillHitTargets(inner, lookupEntry, tokenText) {
  if (!inner || !lookupEntry || typeof lookupEntry !== 'object') return false;
  var token = String(tokenText || '');
  resetKoreanCompoundSpawnToken(inner, token);
  var dictFill = Array.isArray(lookupEntry.dict_fill) ? lookupEntry.dict_fill : [];
  if (dictFill.length <= 1) return false;
  var providedSlices = Array.isArray(lookupEntry.dict_fill_surface_slices)
    ? lookupEntry.dict_fill_surface_slices
    : null;
  if (!isKoreanCompoundSpawnInternalFill(lookupEntry, providedSlices)) return false;
  return applyInvisibleDictFillHitTargets(
    inner,
    tokenText,
    dictFill,
    Array.isArray(providedSlices) && providedSlices.length ? providedSlices : null
  );
}
export function showKoreanCompoundLemmaSpawnBox(anchorEl, segIdx, parts, parentResult) {
  var box = _ensureMwtSpawnBox();
  if (!box || !anchorEl || !Array.isArray(parts) || !parts.length) return;
  var cleanParts = [];
  for (var i = 0; i < parts.length; i++) {
    var part = String(parts[i] || '').trim();
    if (part) cleanParts.push(part);
  }
  if (!cleanParts.length) return;
  var key = 'ko:' + String(segIdx) + ':' + cleanParts.join('+');
  if (
    mwtContextState._mwtSpawnActive &&
    mwtContextState._mwtSpawnActive.key === key &&
    box.style.display !== 'none'
  ) {
    _updateMwtSpawnShield();
    return;
  }
  var content = _clearMwtSpawnContent(box);
  if (!content) return;
  var synthGroup = {
    key: key,
    contexts: [],
    hasGreedySynthHint: false
  };
  var parentUdTok = getUdInfoForSegment(segIdx);
  var parentSurface = String(
    (parentResult && parentResult.surface_form) ||
      (hoverLayoutState.latestSegments && hoverLayoutState.latestSegments[Number(segIdx)]) ||
      (anchorEl && anchorEl.dataset && anchorEl.dataset.seg) ||
      ''
  ).trim();
  for (var pi = 0; pi < cleanParts.length; pi++) {
    if (pi > 0) {
      var sep = document.createElement('span');
      sep.className = 'mwt-spawn-separator';
      sep.textContent = ' + ';
      sep.style.cssText = 'display:inline-block;color:#777;font-weight:500;pointer-events:none;';
      content.appendChild(sep);
    }
    var ctx = _buildKoreanCompoundLemmaSpawnContext(
      segIdx,
      pi,
      cleanParts[pi],
      parentResult,
      parentUdTok,
      parentSurface
    );
    var child = _createMwtSpawnToken(cleanParts[pi], ctx);
    child.dataset.seg = cleanParts[pi];
    child.dataset.index = String(segIdx);
    child.dataset.koCompoundPartIndex = String(pi);
    if (ctx) {
      ctx.synthGroup = synthGroup;
      ctx.element = child;
      synthGroup.contexts.push(ctx);
    }
    if (ctx && ctx.lookupResult) {
      try {
        applyKoreanCompoundSpawnFillHitTargets(child, ctx.lookupResult, cleanParts[pi]);
      } catch (_err) {
        /* keep spawn token usable */
      }
    }
    content.appendChild(child);
  }
  koreanCompoundSynthGroupHasGreedy(synthGroup);
  _positionMwtSpawnBox(box, anchorEl);
  mwtContextState._mwtSpawnActive = {
    key: key,
    segIdx: Number(segIdx),
    partIdx: 0,
    childText: cleanParts.join('+'),
    anchorEl: anchorEl,
    koreanCompoundLemma: true,
    synthGroup: synthGroup
  };
  _updateMwtSpawnShield();
}
export function getKoreanCompoundLemmaSpawnPartsFromEl(el) {
  if (!el || !el.dataset || el.dataset.koCompoundLemmaSpawn !== '1') return [];
  try {
    var parsed = JSON.parse(String(el.dataset.koCompoundLemmaParts || '[]'));
    if (!Array.isArray(parsed)) return [];
    var out = [];
    for (var i = 0; i < parsed.length; i++) {
      var part = String(parsed[i] || '').trim();
      if (part) out.push(part);
    }
    return out;
  } catch (_e) {
    return [];
  }
}
// --- end MWT spawn box ----------------------------------------------------
export function clearMwtPartAnchors(segIdx) {
  if (segIdx == null || segIdx < 0) return;
  dependencyState.udMwtPartAnchors.delete(Number(segIdx));
}
export function buildMwtPartRanges(surfaceText, mwtParts) {
  var surface = String(surfaceText || '');
  var parts = Array.isArray(mwtParts) ? mwtParts : [];
  if (!surface || !parts.length) return [];
  var ranges = [];

  // Check whether all parts have a server-provided surface_slice.
  var allHaveSlice = parts.every(function (p) {
    return p && Array.isArray(p.surface_slice) && p.surface_slice.length >= 2;
  });
  if (allHaveSlice) {
    // Use server-computed byte slices directly — these come from Trankit dspan offsets.
    // Don't require full coverage of surface; just clamp and keep order.
    var cursor = 0;
    for (var i = 0; i < parts.length; i++) {
      var part = parts[i] || {};
      var rawSlice = part.surface_slice;
      var start = parseInt(rawSlice[0], 10);
      var end = parseInt(rawSlice[1], 10);
      if (!isFinite(start) || start < 0) start = cursor;
      if (!isFinite(end) || end <= start) end = start + 1;
      if (end > surface.length) end = surface.length;
      if (start < cursor) start = cursor;
      if (start >= surface.length && i < parts.length - 1) continue; // degenerate slice, skip
      ranges.push({
        partIndex: i,
        start: start,
        end: end
      });
      cursor = end;
    }
    if (ranges.length === parts.length) return ranges;
    // Fall through to proportional split if slices degenerate
    ranges = [];
  }

  // Try literal text match first (works when Trankit expanded parts appear verbatim in surface).
  var cursor2 = 0;
  var literalOk = true;
  var literalRanges = [];
  for (var j = 0; j < parts.length; j++) {
    var partJ = parts[j] || {};
    var partTextJ = String(partJ.text || '');
    if (!partTextJ) {
      literalOk = false;
      break;
    }
    if (surface.slice(cursor2, cursor2 + partTextJ.length) !== partTextJ) {
      literalOk = false;
      break;
    }
    literalRanges.push({
      partIndex: j,
      start: cursor2,
      end: cursor2 + partTextJ.length
    });
    cursor2 += partTextJ.length;
  }
  if (literalOk && cursor2 === surface.length) return literalRanges;

  // Proportional fallback: divide the surface evenly among parts by their text lengths.
  // Used when MWT expanded forms don't appear verbatim (e.g. Italian "del" → "di"+"il").
  var totalPartLen = 0;
  for (var k = 0; k < parts.length; k++) {
    totalPartLen += String((parts[k] && parts[k].text) || '').length || 1;
  }
  var propCursor = 0;
  for (var m = 0; m < parts.length; m++) {
    var partLen = String((parts[m] && parts[m].text) || '').length || 1;
    var propStart = propCursor;
    var propEnd =
      m === parts.length - 1
        ? surface.length
        : Math.round((surface.length * (propCursor + partLen)) / totalPartLen);
    if (propEnd <= propStart) propEnd = propStart + 1;
    if (propEnd > surface.length) propEnd = surface.length;
    ranges.push({
      partIndex: m,
      start: propStart,
      end: propEnd
    });
    propCursor = propEnd;
  }
  return ranges;
}
export function pickMwtPartIndexForSlice(slice, partRanges) {
  var raw = slice || {};
  var ranges = Array.isArray(partRanges) ? partRanges : [];
  var start = parseInt(raw.start, 10);
  var end = parseInt(raw.end, 10);
  if (!isFinite(start) || !isFinite(end) || end <= start || !ranges.length) return null;
  for (var i = 0; i < ranges.length; i++) {
    var range = ranges[i];
    if (start >= range.start && end <= range.end) return range.partIndex;
  }
  var bestPartIndex = null;
  var bestOverlap = 0;
  for (var j = 0; j < ranges.length; j++) {
    var candidate = ranges[j];
    var overlap = Math.min(end, candidate.end) - Math.max(start, candidate.start);
    if (overlap > bestOverlap) {
      bestOverlap = overlap;
      bestPartIndex = candidate.partIndex;
    }
  }
  if (bestPartIndex !== null) return bestPartIndex;
  var mid = start + (end - start) / 2;
  for (var k = 0; k < ranges.length; k++) {
    var fallback = ranges[k];
    if (mid >= fallback.start && mid <= fallback.end) return fallback.partIndex;
  }
  return null;
}
export function normalizeMwtAnchorElements(rawValue) {
  if (Array.isArray(rawValue)) {
    var out = [];
    for (var i = 0; i < rawValue.length; i++) {
      if (rawValue[i]) out.push(rawValue[i]);
    }
    return out;
  }
  return rawValue ? [rawValue] : [];
}
export function unwrapMwtAnchorWrappers(tokenSpan) {
  if (!tokenSpan || !tokenSpan.querySelectorAll) return;
  var wrappers = tokenSpan.querySelectorAll('[data-mwt-anchor="1"]');
  for (var i = wrappers.length - 1; i >= 0; i--) {
    var wrapper = wrappers[i];
    var parent = wrapper && wrapper.parentNode;
    if (!parent) continue;
    while (wrapper.firstChild) parent.insertBefore(wrapper.firstChild, wrapper);
    parent.removeChild(wrapper);
  }
}
export function pruneEmptyTopLevelMwtNodes(tokenSpan) {
  if (!tokenSpan || !tokenSpan.childNodes) return;
  var children = Array.prototype.slice.call(tokenSpan.childNodes);
  for (var i = 0; i < children.length; i++) {
    var child = children[i];
    if (!child || !child.parentNode) continue;
    if (child.nodeType === Node.TEXT_NODE) {
      if (!String(child.nodeValue || '').length) child.parentNode.removeChild(child);
      continue;
    }
    if (child.nodeType !== Node.ELEMENT_NODE) continue;
    if (!String(child.textContent || '').length) {
      child.parentNode.removeChild(child);
    }
  }
}
export function buildMwtAnchorWrappers(tokenSpan, partRanges) {
  if (!tokenSpan || !Array.isArray(partRanges) || !partRanges.length) return null;
  if (typeof document === 'undefined') return null;
  unwrapMwtAnchorWrappers(tokenSpan);
  pruneEmptyTopLevelMwtNodes(tokenSpan);
  var children = [];
  var cursor = 0;
  var rawChildren = Array.prototype.slice.call(tokenSpan.childNodes || []);
  for (var ci = 0; ci < rawChildren.length; ci++) {
    var child = rawChildren[ci];
    if (!child) continue;
    var childText =
      child.nodeType === Node.TEXT_NODE ? String(child.nodeValue || '') : String(child.textContent || '');
    if (!childText.length) continue;
    children.push({
      node: child,
      start: cursor,
      end: cursor + childText.length
    });
    cursor += childText.length;
  }
  if (!children.length) return null;
  var partMap = new Map();
  var childCursor = 0;
  for (var i = 0; i < partRanges.length; i++) {
    var rangeInfo = partRanges[i] || {};
    var partIndex = parseInt(rangeInfo.partIndex, 10);
    var start = parseInt(rangeInfo.start, 10);
    var end = parseInt(rangeInfo.end, 10);
    if (!isFinite(partIndex) || partIndex < 0) return null;
    if (!isFinite(start) || !isFinite(end) || end <= start) return null;
    var partNodes = [];
    while (childCursor < children.length && children[childCursor].end <= start) {
      childCursor += 1;
    }
    while (childCursor < children.length && children[childCursor].start < end) {
      var item = children[childCursor];
      if (item.start < start || item.end > end) return null;
      partNodes.push(item.node);
      childCursor += 1;
    }
    if (!partNodes.length) return null;
    var firstNode = partNodes[0];
    var firstParent = firstNode && firstNode.parentNode;
    if (!firstParent) return null;
    var wrapper = document.createElement('span');
    wrapper.dataset.mwtAnchor = '1';
    wrapper.dataset.mwtPartIndex = String(partIndex);
    firstParent.insertBefore(wrapper, firstNode);
    for (var ni = 0; ni < partNodes.length; ni++) {
      wrapper.appendChild(partNodes[ni]);
    }
    partMap.set(partIndex, [wrapper]);
  }
  pruneEmptyTopLevelMwtNodes(tokenSpan);
  return partMap;
}
export function buildDirectMwtAnchorWrappers(tokenSpan, surfaceText, partRanges) {
  if (!tokenSpan || !Array.isArray(partRanges) || !partRanges.length) return null;
  if (typeof document === 'undefined') return null;
  var surface = String(surfaceText || '');
  if (!surface) return null;
  tokenSpan.textContent = '';
  var partMap = new Map();
  var cursor = 0;
  for (var i = 0; i < partRanges.length; i++) {
    var rangeInfo = partRanges[i] || {};
    var partIndex = parseInt(rangeInfo.partIndex, 10);
    var start = parseInt(rangeInfo.start, 10);
    var end = parseInt(rangeInfo.end, 10);
    if (!isFinite(partIndex) || partIndex < 0) return null;
    if (!isFinite(start) || !isFinite(end) || end <= start) return null;
    if (start > cursor) {
      tokenSpan.appendChild(document.createTextNode(surface.slice(cursor, start)));
    }
    var wrapper = document.createElement('span');
    wrapper.dataset.mwtAnchor = '1';
    wrapper.dataset.mwtPartIndex = String(partIndex);
    wrapper.textContent = surface.slice(start, end);
    tokenSpan.appendChild(wrapper);
    partMap.set(partIndex, [wrapper]);
    cursor = end;
  }
  if (cursor < surface.length) {
    tokenSpan.appendChild(document.createTextNode(surface.slice(cursor)));
  }
  pruneEmptyTopLevelMwtNodes(tokenSpan);
  return partMap;
}
export function registerMwtPartAnchors(segIdx, tokenSpan, lookupEntry, udTok) {
  clearMwtPartAnchors(segIdx);
  if (segIdx == null || segIdx < 0 || !tokenSpan || !lookupEntry || !udTok) return false;
  var mwtParts = Array.isArray(udTok.mwt_parts) ? udTok.mwt_parts : [];
  if (!mwtParts.length) return false;
  var surfaceText = String(
    (tokenSpan.dataset && tokenSpan.dataset.seg) ||
      lookupEntry.surface_form ||
      lookupEntry.text ||
      udTok.text ||
      ''
  );
  var partRanges = buildMwtPartRanges(surfaceText, mwtParts);
  if (!partRanges.length) return false;
  var partMap = buildMwtAnchorWrappers(tokenSpan, partRanges);
  if ((!partMap || !partMap.size) && !(tokenSpan.dataset && tokenSpan.dataset.hasFillHits === '1')) {
    partMap = buildDirectMwtAnchorWrappers(tokenSpan, surfaceText, partRanges);
  }
  if (!partMap || !partMap.size) return false;

  // Build partIndex -> range lookup for mismatch detection.
  var partRangeByIdx = {};
  for (var pri = 0; pri < partRanges.length; pri++) {
    var pr = partRanges[pri] || {};
    var prIdx = parseInt(pr.partIndex, 10);
    if (isFinite(prIdx)) partRangeByIdx[prIdx] = pr;
  }
  for (var pj = 0; pj < mwtParts.length; pj++) {
    var part = mwtParts[pj] || {};
    var partEls = normalizeMwtAnchorElements(partMap.get(pj));
    if (!partEls.length) return false;
    var childText = String(part.text || part.lemma || '').trim();
    var rangeForPart = partRangeByIdx[pj];
    var sliceText = '';
    if (rangeForPart) {
      var sStart = parseInt(rangeForPart.start, 10);
      var sEnd = parseInt(rangeForPart.end, 10);
      if (isFinite(sStart) && isFinite(sEnd)) sliceText = surfaceText.slice(sStart, sEnd);
    }
    var isMismatch = !!(childText && sliceText && !hasSameVisibleComparisonText(childText, sliceText));
    var useChildPopupForPart = !!(isMismatch && childText);
    for (var pei = 0; pei < partEls.length; pei++) {
      var partEl = partEls[pei];
      partEl.dataset.mwtPartIndex = String(pj);
      if (part.upos != null) partEl.dataset.mwtUpos = String(part.upos || '');
      else delete partEl.dataset.mwtUpos;
      if (part.dep != null) partEl.dataset.mwtDep = String(part.dep || '');
      else delete partEl.dataset.mwtDep;
      if (useChildPopupForPart) {
        partEl.dataset.mwtMismatch = '1';
        partEl.dataset.mwtChildText = childText;
        partEl.dataset.mwtPopupReason = 'mismatch';
        // Only the individual child whose expanded text diverges from its
        // surface slice routes through the spawned child popup. Matching
        // children keep their normal surface-side fill-hit/hover behavior.
        if (partEl.querySelectorAll) {
          var _fhits = partEl.querySelectorAll('.reader-token-fill-hit');
          for (var _fi = _fhits.length - 1; _fi >= 0; _fi--) {
            var _fh = _fhits[_fi];
            var _fhp = _fh && _fh.parentNode;
            if (!_fhp) continue;
            while (_fh.firstChild) _fhp.insertBefore(_fh.firstChild, _fh);
            _fhp.removeChild(_fh);
          }
        }
      } else {
        delete partEl.dataset.mwtMismatch;
        delete partEl.dataset.mwtChildText;
        delete partEl.dataset.mwtPopupReason;
      }
    }
    partMap.set(pj, partEls);
  }
  dependencyState.udMwtPartAnchors.set(Number(segIdx), partMap);
  return true;
}
