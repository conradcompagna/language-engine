import {
  _isZeroWidthOrCombining,
  buildSurfaceCodepointMap,
  decomposeTextToAlignmentUnits,
  isKoreanLanguageCode,
  toUnicodeCodePointList
} from './alignment-inputs.mjs';
import { _buildGroupsFromUnitPartIds, _buildProportionalAlignment } from './child-fill-slices.mjs';
import { getCurrentLanguage, getDictionaryNormalizationLayer } from './core.mjs';
export // Compute codepoint-unit overlap score between a lemma part and a set of
// surface characters. Returns the count of shared decomposed units (bag
// intersection). Used for fuzzy assignment of unplaced parts to gap chars.
function _codepointOverlapScore(partUnits, surfaceCharUnits) {
  // Build bag (unit → count) from surface char units
  var bag = Object.create(null);
  for (var si = 0; si < surfaceCharUnits.length; si++) {
    var u = surfaceCharUnits[si];
    bag[u] = (bag[u] || 0) + 1;
  }
  var score = 0;
  for (var pi = 0; pi < partUnits.length; pi++) {
    var pu = partUnits[pi];
    if (bag[pu] && bag[pu] > 0) {
      score++;
      bag[pu]--;
    }
  }
  return score;
}
export function buildGenericSurfacePartAlignment(surface, partTexts, opts) {
  var options = opts || {};
  var langCode = String(options.langCode || getCurrentLanguage() || '').toLowerCase();
  var normalizationLayer = getDictionaryNormalizationLayer();
  var debugTrace = !!options.debugTrace;
  var surfaceText = String(surface || '');
  if (!surfaceText) return null;
  var parts = Array.isArray(partTexts) ? partTexts.slice() : [];
  if (!parts.length) return null;
  var normalizedParts = [];
  for (var pi = 0; pi < parts.length; pi++) {
    var partText = String(parts[pi] || '');
    if (!partText) return null;
    normalizedParts.push(partText);
  }
  function clonePartIdList(rawIds) {
    var src = Array.isArray(rawIds) ? rawIds : [];
    var out = [];
    for (var i = 0; i < src.length; i++) {
      var pid = parseInt(src[i], 10);
      if (!isFinite(pid) || pid < 0) continue;
      out.push(pid);
    }
    return out;
  }
  function snapshotCharAssign(rawAssign, rawSurfaceChars) {
    var assign = Array.isArray(rawAssign) ? rawAssign : [];
    var chars = Array.isArray(rawSurfaceChars) ? rawSurfaceChars : [];
    var out = [];
    for (var i = 0; i < chars.length; i++) {
      var partIds = assign[i];
      out.push({
        char_index: i,
        char: String(chars[i] || ''),
        part_ids: Array.isArray(partIds) ? clonePartIdList(partIds) : []
      });
    }
    return out;
  }
  function cloneCodepointDebug(rawDebug) {
    if (!rawDebug || typeof rawDebug !== 'object') return null;
    var out = {};
    var surfaceChars = Array.isArray(rawDebug.surface_chars) ? rawDebug.surface_chars : [];
    if (surfaceChars.length) {
      out.surface_chars = surfaceChars.map(function (row) {
        return {
          index: parseInt(row && row.index, 10) || 0,
          char: String((row && row.char) || ''),
          unit_start: parseInt(row && row.unit_start, 10) || 0,
          unit_end: parseInt(row && row.unit_end, 10) || 0,
          unit_text: String((row && row.unit_text) || ''),
          unit_codepoints: Array.isArray(row && row.unit_codepoints) ? row.unit_codepoints.slice() : []
        };
      });
    }
    var debugParts = Array.isArray(rawDebug.parts) ? rawDebug.parts : [];
    if (debugParts.length) {
      out.parts = debugParts.map(function (row) {
        return {
          part_id: parseInt(row && row.part_id, 10) || 0,
          text: String((row && row.text) || ''),
          unit_text: String((row && row.unit_text) || ''),
          unit_codepoints: Array.isArray(row && row.unit_codepoints) ? row.unit_codepoints.slice() : []
        };
      });
    }
    return out;
  }
  var runtimeDebug = debugTrace
    ? {
        surface_text: surfaceText,
        lang_code: langCode,
        normalized_parts: normalizedParts.slice(),
        anchor_state: {},
        unplaced_parts: [],
        gaps: [],
        char_assign_before_null_fill: [],
        char_assign_final: [],
        null_fill_steps: []
      }
    : null;
  function attachRuntimeAlignmentDebug(result) {
    if (!debugTrace || !runtimeDebug || !result || typeof result !== 'object') return result;
    runtimeDebug.match_basis = String(result.match_basis || '');
    runtimeDebug.boundaries = Array.isArray(result.boundaries) ? result.boundaries.slice() : [];
    runtimeDebug.groups = Array.isArray(result.groups)
      ? result.groups.map(function (group) {
          return {
            start: parseInt(group && group.start, 10) || 0,
            end: parseInt(group && group.end, 10) || 0,
            part_ids: Array.isArray(group && group.part_ids) ? group.part_ids.slice() : [],
            part_count: parseInt(group && group.part_count, 10) || 0,
            unit_text: String((group && group.unit_text) || ''),
            unit_codepoints: Array.isArray(group && group.unit_codepoints)
              ? group.unit_codepoints.slice()
              : []
          };
        })
      : [];
    runtimeDebug.codepoint_debug = cloneCodepointDebug(result.codepoint_debug);
    result._debug_runtime_alignment = runtimeDebug;
    return result;
  }
  function getAssignedPartSpan(partId, excludeStart, excludeEnd) {
    var spanStart = -1;
    var spanEnd = -1;
    for (var i = 0; i < numSurfChars; i++) {
      if (i >= excludeStart && i < excludeEnd) continue;
      var assignedIds = charAssign[i];
      if (!Array.isArray(assignedIds) || assignedIds.indexOf(partId) < 0) continue;
      if (spanStart < 0) spanStart = i;
      spanEnd = i + 1;
    }
    if (spanStart < 0 || spanEnd <= spanStart) return null;
    return {
      start: spanStart,
      end: spanEnd,
      length: spanEnd - spanStart,
      midpoint: (spanStart + spanEnd - 1) / 2
    };
  }
  function getNearestGapNeighborPartId(gapStart, gapEnd, direction) {
    var idx = direction < 0 ? gapStart - 1 : gapEnd;
    while (idx >= 0 && idx < numSurfChars) {
      var ids = charAssign[idx];
      if (Array.isArray(ids) && ids.length) {
        return direction < 0 ? ids[ids.length - 1] : ids[0];
      }
      idx += direction;
    }
    return -1;
  }
  function chooseSurfaceOnlyGapNeighborPartId(gapStart, gapEnd) {
    var leftNeighborId = getNearestGapNeighborPartId(gapStart, gapEnd, -1);
    var rightNeighborId = getNearestGapNeighborPartId(gapStart, gapEnd, 1);
    if (!(
      normalizationLayer &&
      typeof normalizationLayer.isArabicLanguageCode === 'function' &&
      normalizationLayer.isArabicLanguageCode(langCode)
    )) {
      return leftNeighborId >= 0 ? leftNeighborId : rightNeighborId;
    }
    var candidateIds = [];
    if (leftNeighborId >= 0) candidateIds.push(leftNeighborId);
    if (rightNeighborId >= 0 && rightNeighborId !== leftNeighborId) candidateIds.push(rightNeighborId);
    if (!candidateIds.length) return -1;
    if (candidateIds.length === 1) return candidateIds[0];
    var tokenMidpoint = (numSurfChars - 1) / 2;
    var bestId = candidateIds[0];
    var bestCenterDist = Infinity;
    var bestEdgePenalty = Infinity;
    var bestSpanLen = -1;
    for (var ci = 0; ci < candidateIds.length; ci++) {
      var candidateId = candidateIds[ci];
      var span = getAssignedPartSpan(candidateId, gapStart, gapEnd);
      var centerDist = span ? Math.abs(span.midpoint - tokenMidpoint) : Infinity;
      var edgePenalty = candidateId === 0 || candidateId === normalizedParts.length - 1 ? 1 : 0;
      var spanLen = span ? span.length : 0;
      if (
        centerDist < bestCenterDist ||
        (centerDist === bestCenterDist && edgePenalty < bestEdgePenalty) ||
        (centerDist === bestCenterDist && edgePenalty === bestEdgePenalty && spanLen > bestSpanLen)
      ) {
        bestId = candidateId;
        bestCenterDist = centerDist;
        bestEdgePenalty = edgePenalty;
        bestSpanLen = spanLen;
      }
    }
    return bestId;
  }

  // Single part: trivially covers the whole surface, no alignment needed
  if (normalizedParts.length === 1) {
    return attachRuntimeAlignmentDebug({
      boundaries: [],
      groups: [
        {
          start: 0,
          end: surfaceText.length,
          part_ids: [0],
          part_count: 1
        }
      ],
      match_basis: 'single',
      codepoint_debug: null
    });
  }

  // --- Tier 1: exact concatenation match ---
  var joinedText = normalizedParts.join('');
  if (joinedText === surfaceText) {
    var exactGroups = [];
    var exactBounds = [];
    var exactCursor = 0;
    for (var ei = 0; ei < normalizedParts.length; ei++) {
      var nextCursor = exactCursor + normalizedParts[ei].length;
      exactGroups.push({
        start: exactCursor,
        end: nextCursor,
        part_ids: [ei],
        part_count: 1
      });
      exactCursor = nextCursor;
      if (ei < normalizedParts.length - 1) exactBounds.push(nextCursor);
    }
    return attachRuntimeAlignmentDebug({
      boundaries: exactBounds,
      groups: exactGroups,
      match_basis: 'surface',
      codepoint_debug: null
    });
  }

  // --- Decompose surface and lemma parts into alignment units ---
  var surfaceMap = buildSurfaceCodepointMap(surfaceText, langCode);
  if (!surfaceMap.units.length) return null;

  // Build flat lemma units, each tagged with its part_id
  var lemmaUnits = [];
  var lemmaUnitPartId = [];
  for (var pj = 0; pj < normalizedParts.length; pj++) {
    var pUnits = decomposeTextToAlignmentUnits(normalizedParts[pj], langCode);
    for (var pu = 0; pu < pUnits.length; pu++) {
      lemmaUnits.push(pUnits[pu]);
      lemmaUnitPartId.push(pj);
    }
  }

  // Check if decomposed units match exactly
  if (surfaceMap.units.length === lemmaUnits.length) {
    var allMatch = true;
    for (var cm = 0; cm < surfaceMap.units.length; cm++) {
      if (surfaceMap.units[cm] !== lemmaUnits[cm]) {
        allMatch = false;
        break;
      }
    }
    if (allMatch) {
      return attachRuntimeAlignmentDebug(
        _buildGroupsFromUnitPartIds(surfaceMap, lemmaUnitPartId, normalizedParts, langCode, 'codepoint')
      );
    }
  }

  // ===================================================================
  // Tier 2: Character-level anchor-and-residual alignment
  // ===================================================================
  // Work at the character level (Array.from). Anchor exact character
  // matches from both ends, then assign remaining surface chars to
  // remaining parts using codepoint-overlap scoring.
  //
  // Sub-character sharing (multiple parts → one surface char) is only
  // allowed for Korean, where Hangul syllable blocks can pack jamo from
  // different morphemes into a single Unicode character (e.g. 였 = 이+었).
  // All other languages get exactly one part per surface character.
  var allowSubCharSharing = isKoreanLanguageCode(langCode);
  var surfaceChars = Array.from(surfaceText);
  var numSurfChars = surfaceChars.length;

  // Decompose each part into its characters for character-level comparison.
  // Strip combining diacritics from lemma parts before comparison — lemmas
  // for Arabic/Hebrew often carry harakat/niqqud that are absent in surface text,
  // causing anchor failures (e.g. "فَوز" vs surface "فوز").
  var _stripFn =
    normalizationLayer && typeof normalizationLayer.stripLemmaAlignmentDiacritics === 'function'
      ? normalizationLayer.stripLemmaAlignmentDiacritics
      : null;
  var partChars = [];
  for (var pc = 0; pc < normalizedParts.length; pc++) {
    var pcText = _stripFn ? _stripFn(normalizedParts[pc], langCode) : normalizedParts[pc];
    partChars.push(Array.from(pcText));
  }

  // charAssign[i] = array of part_ids assigned to surface char i, or null
  var charAssign = new Array(numSurfChars);
  for (var ca = 0; ca < numSurfChars; ca++) charAssign[ca] = null;
  var partPlaced = new Array(normalizedParts.length);
  for (var pp = 0; pp < normalizedParts.length; pp++) partPlaced[pp] = false;

  // --- Left-to-right greedy character anchoring ---
  // Walk surface chars and consume lemma parts character-by-character.
  // A part is anchored when ALL its characters match consecutively.
  var sCursor = 0;
  var pCursor = 0;
  while (sCursor < numSurfChars && pCursor < normalizedParts.length) {
    var pChars = partChars[pCursor];
    if (sCursor + pChars.length > numSurfChars) break;
    var matched = true;
    for (var lc = 0; lc < pChars.length; lc++) {
      if (surfaceChars[sCursor + lc] !== pChars[lc]) {
        matched = false;
        break;
      }
    }
    if (matched) {
      for (var la = 0; la < pChars.length; la++) {
        charAssign[sCursor + la] = [pCursor];
      }
      partPlaced[pCursor] = true;
      sCursor += pChars.length;
      pCursor++;
    } else {
      break;
    }
  }
  var leftAnchorEnd = pCursor; // first unplaced part from left pass

  // --- Right-to-left greedy character anchoring ---
  var sEnd = numSurfChars - 1;
  var pEnd = normalizedParts.length - 1;
  while (sEnd >= sCursor && pEnd >= leftAnchorEnd) {
    var rpChars = partChars[pEnd];
    var rStart = sEnd - rpChars.length + 1;
    if (rStart < sCursor) break;
    var rMatched = true;
    for (var rc = 0; rc < rpChars.length; rc++) {
      if (surfaceChars[rStart + rc] !== rpChars[rc]) {
        rMatched = false;
        break;
      }
    }
    if (rMatched) {
      for (var ra = 0; ra < rpChars.length; ra++) {
        charAssign[rStart + ra] = [pEnd];
      }
      partPlaced[pEnd] = true;
      sEnd -= rpChars.length;
      pEnd--;
    } else {
      break;
    }
  }
  if (runtimeDebug) {
    runtimeDebug.anchor_state = {
      left_anchor_end: leftAnchorEnd,
      right_anchor_start: pEnd + 1
    };
  }

  // --- Collect gaps: contiguous runs of unassigned surface chars ---
  // Each gap sits between anchored regions. The unplaced parts that
  // positionally fall within this gap are determined by ordering.
  var gaps = []; // {charStart, charEnd, partIds: [...]}
  var unplacedParts = [];
  for (var up = 0; up < normalizedParts.length; up++) {
    if (!partPlaced[up]) unplacedParts.push(up);
  }
  if (unplacedParts.length > 0) {
    // Find contiguous unassigned char runs
    var gapRuns = [];
    var gi = 0;
    while (gi < numSurfChars) {
      if (charAssign[gi] !== null) {
        gi++;
        continue;
      }
      var gStart = gi;
      while (gi < numSurfChars && charAssign[gi] === null) gi++;
      gapRuns.push({
        charStart: gStart,
        charEnd: gi
      });
    }
    if (gapRuns.length === 0) {
      // All surface chars anchored but some parts unplaced.
      if (allowSubCharSharing) {
        // Korean: parts can share a surface char with their nearest neighbor.
        for (var ou = 0; ou < unplacedParts.length; ou++) {
          var orphanId = unplacedParts[ou];
          var bestChar = -1;
          var bestDist = Infinity;
          for (var bc = 0; bc < numSurfChars; bc++) {
            if (!charAssign[bc]) continue;
            for (var bci = 0; bci < charAssign[bc].length; bci++) {
              var dist = Math.abs(charAssign[bc][bci] - orphanId);
              if (dist < bestDist) {
                bestDist = dist;
                bestChar = bc;
              }
            }
          }
          if (bestChar >= 0) {
            if (charAssign[bestChar].indexOf(orphanId) < 0) {
              charAssign[bestChar].push(orphanId);
              charAssign[bestChar].sort(function (a, b) {
                return a - b;
              });
            }
          }
        }
      }
      // Non-Korean: no sharing allowed and no gap chars available.
      // Parts remain unplaced — they will be picked up by the safety
      // net in buildLemmaHintAlignmentState (orphan stitching).
    } else {
      // Distribute unplaced parts across gaps by positional order.
      // Each gap's parts are those whose part_id falls between the
      // anchored part_ids on either side of the gap.
      var upIdx = 0;
      for (var gri = 0; gri < gapRuns.length; gri++) {
        var gap = gapRuns[gri];
        // Find the bounding anchored part_ids
        var leftBound = -1;
        for (var lb = gap.charStart - 1; lb >= 0; lb--) {
          if (charAssign[lb]) {
            leftBound = Math.max.apply(null, charAssign[lb]);
            break;
          }
        }
        var rightBound = normalizedParts.length;
        for (var rb = gap.charEnd; rb < numSurfChars; rb++) {
          if (charAssign[rb]) {
            rightBound = Math.min.apply(null, charAssign[rb]);
            break;
          }
        }
        // Collect unplaced parts that belong in this gap
        var gapPartIds = [];
        while (
          upIdx < unplacedParts.length &&
          unplacedParts[upIdx] > leftBound &&
          unplacedParts[upIdx] < rightBound
        ) {
          gapPartIds.push(unplacedParts[upIdx]);
          upIdx++;
        }
        gaps.push({
          charStart: gap.charStart,
          charEnd: gap.charEnd,
          partIds: gapPartIds
        });
      }
    }
  }
  if (runtimeDebug) {
    runtimeDebug.unplaced_parts = unplacedParts.slice();
    runtimeDebug.gaps = gaps.map(function (gap) {
      return {
        char_start: parseInt(gap && gap.charStart, 10) || 0,
        char_end: parseInt(gap && gap.charEnd, 10) || 0,
        part_ids: Array.isArray(gap && gap.partIds) ? gap.partIds.slice() : []
      };
    });
  }

  // --- Assign gap chars to gap parts ---
  // Strategy: proportional partition by lemma-part length, refined by
  // codepoint overlap scoring. Sub-character sharing (multiple parts on
  // one char) is Korean-only.
  for (var gfi = 0; gfi < gaps.length; gfi++) {
    var gapInfo = gaps[gfi];
    var gCharStart = gapInfo.charStart;
    var gCharEnd = gapInfo.charEnd;
    var gPartIds = gapInfo.partIds;
    var gNumChars = gCharEnd - gCharStart;
    if (gPartIds.length === 0) {
      // No unplaced parts for this gap — attach chars to a neighboring slice.
      // Arabic prefers the more central anchored slice over an edge clitic.
      var neighborId = chooseSurfaceOnlyGapNeighborPartId(gCharStart, gCharEnd);
      if (neighborId >= 0) {
        for (var na = gCharStart; na < gCharEnd; na++) {
          charAssign[na] = [neighborId];
        }
      }
      continue;
    }
    if (gNumChars === 0) {
      // Zero-width gap — attach parts to nearest anchored char (Korean
      // only; non-Korean parts left for orphan safety net)
      if (allowSubCharSharing) {
        var anchorChar = gCharStart > 0 ? gCharStart - 1 : gCharEnd < numSurfChars ? gCharEnd : 0;
        if (charAssign[anchorChar]) {
          for (var zp = 0; zp < gPartIds.length; zp++) {
            if (charAssign[anchorChar].indexOf(gPartIds[zp]) < 0) {
              charAssign[anchorChar].push(gPartIds[zp]);
            }
          }
          charAssign[anchorChar].sort(function (a, b) {
            return a - b;
          });
        }
      }
      continue;
    }
    if (gPartIds.length === 1) {
      // Single part gets all gap chars
      for (var sp2 = gCharStart; sp2 < gCharEnd; sp2++) {
        charAssign[sp2] = [gPartIds[0]];
      }
      continue;
    }
    if (gNumChars === 1 && allowSubCharSharing) {
      // Korean: single char gets all gap parts (they hover together)
      charAssign[gCharStart] = gPartIds.slice();
      continue;
    }

    // --- Proportional partition: divide gap chars among parts by
    // relative lemma-part length, then refine with codepoint overlap ---

    // Pre-compute decomposed units for each gap surface char and part
    var gapCharUnits = [];
    for (var gcu = gCharStart; gcu < gCharEnd; gcu++) {
      gapCharUnits.push(decomposeTextToAlignmentUnits(surfaceChars[gcu], langCode));
    }
    var gapPartUnits = [];
    var gapPartLengths = [];
    var totalPartLen = 0;
    for (var gpu = 0; gpu < gPartIds.length; gpu++) {
      var gpUnits = decomposeTextToAlignmentUnits(normalizedParts[gPartIds[gpu]], langCode);
      gapPartUnits.push(gpUnits);
      var gpLen = Array.from(normalizedParts[gPartIds[gpu]]).length;
      gapPartLengths.push(gpLen);
      totalPartLen += gpLen;
    }

    // Build proportional partition: assign each part a consecutive run
    // of gap chars proportional to its lemma length.
    // partRuns[i] = {start, end} (indices into gap, 0-based)
    var partRuns = new Array(gPartIds.length);
    var runCursor = 0;
    if (!allowSubCharSharing) {
      // Non-Korean: every part MUST get at least 1 char.
      // If more parts than chars, we cannot satisfy this — fall back to
      // giving each char to one part round-robin, extras get no char and
      // are left for the orphan safety net.
      if (gPartIds.length > gNumChars) {
        for (var rc2 = 0; rc2 < gNumChars; rc2++) {
          charAssign[gCharStart + rc2] = [gPartIds[rc2]];
        }
        // Remaining parts (gPartIds[gNumChars..]) have no chars — they
        // are left unassigned and will be picked up by orphan stitching.
        continue;
      }
      // Distribute with minimum 1 char per part
      for (var pr = 0; pr < gPartIds.length; pr++) {
        var propShare = gapPartLengths[pr] / (totalPartLen || 1);
        var runLen;
        if (pr === gPartIds.length - 1) {
          runLen = gNumChars - runCursor;
        } else {
          runLen = Math.max(1, Math.round(gNumChars * propShare));
          // Ensure enough chars remain for subsequent parts
          var remaining = gPartIds.length - pr - 1;
          if (runCursor + runLen > gNumChars - remaining) {
            runLen = gNumChars - remaining - runCursor;
          }
          if (runLen < 1) runLen = 1;
        }
        partRuns[pr] = {
          start: runCursor,
          end: runCursor + runLen
        };
        runCursor += runLen;
      }
    } else {
      // Korean: when enough chars, each part gets at least 1 char.
      // Only allow 0-width runs when more parts than chars (true merging).
      var korMinRun = gNumChars >= gPartIds.length ? 1 : 0;
      for (var pr2 = 0; pr2 < gPartIds.length; pr2++) {
        var propShare2 = gapPartLengths[pr2] / (totalPartLen || 1);
        var runLen2;
        if (pr2 === gPartIds.length - 1) {
          runLen2 = gNumChars - runCursor;
        } else {
          runLen2 = Math.max(korMinRun, Math.round(gNumChars * propShare2));
          var remaining2 = gPartIds.length - pr2 - 1;
          if (korMinRun > 0 && runCursor + runLen2 > gNumChars - remaining2) {
            runLen2 = gNumChars - remaining2 - runCursor;
          }
          if (runLen2 < korMinRun) runLen2 = korMinRun;
          if (runCursor + runLen2 > gNumChars) runLen2 = gNumChars - runCursor;
        }
        if (runLen2 < 0) runLen2 = 0;
        partRuns[pr2] = {
          start: runCursor,
          end: runCursor + runLen2
        };
        runCursor += runLen2;
      }
    }

    // --- Refine boundaries using codepoint overlap scoring ---
    // Try shifting each boundary ±1 char and see if total overlap improves.
    // boundaries[i] = partRuns[i].end = partRuns[i+1].start (0-based gap index)
    var boundaries = new Array(gPartIds.length - 1);
    for (var bi = 0; bi < boundaries.length; bi++) {
      boundaries[bi] = partRuns[bi].end;
    }

    // Score a partition: sum of overlap(part, pooled units of its char run)
    var _scorePartition = function (bounds) {
      var total = 0;
      for (var sp3 = 0; sp3 < gPartIds.length; sp3++) {
        var rStart = sp3 === 0 ? 0 : bounds[sp3 - 1];
        var rEnd = sp3 < bounds.length ? bounds[sp3] : gNumChars;
        if (rEnd <= rStart) continue;
        // Pool all surface char units in this run
        var pooled = [];
        for (var pc2 = rStart; pc2 < rEnd; pc2++) {
          var units = gapCharUnits[pc2];
          for (var pu2 = 0; pu2 < units.length; pu2++) pooled.push(units[pu2]);
        }
        total += _codepointOverlapScore(gapPartUnits[sp3], pooled);
      }
      return total;
    };
    var bestBoundScore = _scorePartition(boundaries);
    var improved = true;
    // Min run size for boundary refinement: 1 char per part unless
    // Korean with genuinely more parts than chars (true sub-char merging)
    var minRunForRefine = allowSubCharSharing && gNumChars < gPartIds.length ? 0 : 1;
    // Iterate until no improvement (usually 1-2 passes for small gaps)
    while (improved) {
      improved = false;
      for (var bi2 = 0; bi2 < boundaries.length; bi2++) {
        // Try shifting this boundary left
        var leftMin = (bi2 > 0 ? boundaries[bi2 - 1] : 0) + minRunForRefine;
        if (boundaries[bi2] > leftMin) {
          var leftTry = boundaries.slice();
          leftTry[bi2]--;
          // Ensure the run to the right still has >= minRunForRefine chars
          var rightRunEnd = bi2 + 1 < boundaries.length ? leftTry[bi2 + 1] : gNumChars;
          if (rightRunEnd - leftTry[bi2] >= minRunForRefine) {
            var leftScore = _scorePartition(leftTry);
            if (leftScore > bestBoundScore) {
              boundaries = leftTry;
              bestBoundScore = leftScore;
              improved = true;
            }
          }
        }
        // Try shifting this boundary right
        var rightMax = (bi2 + 1 < boundaries.length ? boundaries[bi2 + 1] : gNumChars) - minRunForRefine;
        if (boundaries[bi2] < rightMax) {
          var rightTry = boundaries.slice();
          rightTry[bi2]++;
          // Ensure the run to the left still has >= minRunForRefine chars
          var leftRunStart = bi2 > 0 ? rightTry[bi2 - 1] : 0;
          if (rightTry[bi2] - leftRunStart >= minRunForRefine) {
            var rightScore = _scorePartition(rightTry);
            if (rightScore > bestBoundScore) {
              boundaries = rightTry;
              bestBoundScore = rightScore;
              improved = true;
            }
          }
        }
      }
    }

    // --- Assign chars to parts based on final partition ---
    for (var ai = 0; ai < gNumChars; ai++) {
      charAssign[gCharStart + ai] = [];
    }
    for (var fp3 = 0; fp3 < gPartIds.length; fp3++) {
      var fStart = fp3 === 0 ? 0 : boundaries[fp3 - 1];
      var fEnd = fp3 < boundaries.length ? boundaries[fp3] : gNumChars;
      for (var fc = fStart; fc < fEnd; fc++) {
        charAssign[gCharStart + fc].push(gPartIds[fp3]);
      }
    }

    // --- Korean only: spillover sharing ---
    // If a part also has codepoint overlap with chars in an adjacent
    // run, add it to those chars so they hover together.
    if (allowSubCharSharing) {
      for (var sp4 = 0; sp4 < gPartIds.length; sp4++) {
        var spStart = sp4 === 0 ? 0 : boundaries[sp4 - 1];
        var spEnd = sp4 < boundaries.length ? boundaries[sp4] : gNumChars;
        var currentRunLen = spEnd - spStart;
        var maxLen = gapPartLengths[sp4]; // cap reach at lemma char length
        if (currentRunLen >= maxLen) continue; // already at capacity
        // Check chars just outside this part's run
        // Left spillover: char at spStart-1
        if (spStart > 0) {
          var leftOverlap = _codepointOverlapScore(gapPartUnits[sp4], gapCharUnits[spStart - 1]);
          if (leftOverlap > 0 && charAssign[gCharStart + spStart - 1].indexOf(gPartIds[sp4]) < 0) {
            charAssign[gCharStart + spStart - 1].push(gPartIds[sp4]);
            charAssign[gCharStart + spStart - 1].sort(function (a, b) {
              return a - b;
            });
          }
        }
        // Right spillover: char at spEnd
        if (spEnd < gNumChars) {
          var rightOverlap = _codepointOverlapScore(gapPartUnits[sp4], gapCharUnits[spEnd]);
          if (rightOverlap > 0 && charAssign[gCharStart + spEnd].indexOf(gPartIds[sp4]) < 0) {
            charAssign[gCharStart + spEnd].push(gPartIds[sp4]);
            charAssign[gCharStart + spEnd].sort(function (a, b) {
              return a - b;
            });
          }
        }
      }
    }

    // Handle any gap chars that still got no parts (empty run in Korean)
    for (var fx = 0; fx < gNumChars; fx++) {
      if (charAssign[gCharStart + fx].length > 0) continue;
      var foundIds = null;
      for (var fl = fx - 1; fl >= 0; fl--) {
        if (charAssign[gCharStart + fl].length > 0) {
          foundIds = charAssign[gCharStart + fl];
          break;
        }
      }
      if (!foundIds) {
        for (var fr = fx + 1; fr < gNumChars; fr++) {
          if (charAssign[gCharStart + fr].length > 0) {
            foundIds = charAssign[gCharStart + fr];
            break;
          }
        }
      }
      if (foundIds) {
        charAssign[gCharStart + fx] = [foundIds[foundIds.length - 1]];
      }
    }
  }

  // --- Post-process: merge combining/zero-width chars into neighbors ---
  for (var zw = 0; zw < numSurfChars; zw++) {
    if (!_isZeroWidthOrCombining(surfaceChars[zw])) continue;
    // Find a host: prefer preceding char, then following
    var host = -1;
    if (zw > 0 && charAssign[zw - 1]) host = zw - 1;
    else if (zw + 1 < numSurfChars && charAssign[zw + 1]) host = zw + 1;
    if (host >= 0 && charAssign[host]) {
      charAssign[zw] = charAssign[host].slice();
    }
  }

  // --- Handle any still-null chars (safety) ---
  if (runtimeDebug) runtimeDebug.char_assign_before_null_fill = snapshotCharAssign(charAssign, surfaceChars);
  for (var sn = 0; sn < numSurfChars; sn++) {
    if (charAssign[sn] !== null && charAssign[sn].length > 0) continue;
    // Propagate from left
    if (sn > 0 && charAssign[sn - 1] && charAssign[sn - 1].length > 0) {
      charAssign[sn] = charAssign[sn - 1].slice();
      if (runtimeDebug) {
        runtimeDebug.null_fill_steps.push({
          char_index: sn,
          char: String(surfaceChars[sn] || ''),
          source: 'left',
          from_index: sn - 1,
          part_ids: clonePartIdList(charAssign[sn])
        });
      }
    }
  }
  for (var sn2 = numSurfChars - 1; sn2 >= 0; sn2--) {
    if (charAssign[sn2] !== null && charAssign[sn2].length > 0) continue;
    if (sn2 + 1 < numSurfChars && charAssign[sn2 + 1] && charAssign[sn2 + 1].length > 0) {
      charAssign[sn2] = charAssign[sn2 + 1].slice();
      if (runtimeDebug) {
        runtimeDebug.null_fill_steps.push({
          char_index: sn2,
          char: String(surfaceChars[sn2] || ''),
          source: 'right',
          from_index: sn2 + 1,
          part_ids: clonePartIdList(charAssign[sn2])
        });
      }
    }
  }
  if (runtimeDebug) runtimeDebug.char_assign_final = snapshotCharAssign(charAssign, surfaceChars);

  // If nothing could be assigned at all, fall back to proportional
  var anyAssigned = false;
  for (var chk = 0; chk < numSurfChars; chk++) {
    if (charAssign[chk] && charAssign[chk].length > 0) {
      anyAssigned = true;
      break;
    }
  }
  if (!anyAssigned) {
    return attachRuntimeAlignmentDebug(_buildProportionalAlignment(surfaceMap, normalizedParts, langCode));
  }

  // --- Build unit-level part_id array for _buildGroupsFromUnitPartIds ---
  // For each surface unit, take the part_ids of its parent character.
  // When a char has multiple part_ids, all its units get all those ids;
  // _buildGroupsFromUnitPartIds already handles multi-id chars by merging
  // them into groups with multiple part_ids.
  var unitPartIds = new Array(surfaceMap.units.length);
  for (var ub = 0; ub < surfaceMap.units.length; ub++) unitPartIds[ub] = -1;
  for (var ci2 = 0; ci2 < surfaceMap.chars.length; ci2++) {
    var charRow = surfaceMap.chars[ci2];
    var ids = charAssign[ci2];
    if (!ids || !ids.length) continue;
    // Use the first part_id as the primary for the unit array;
    // _buildGroupsFromUnitPartIds collects all part_ids per char via
    // the unit range, so we write each unit once per part_id by using
    // a per-char sweep in that function. But that function reads one
    // part_id per unit. To support multi-part chars we need to tag
    // units. Use a negative encoding? No — _buildGroupsFromUnitPartIds
    // already iterates unit_start..unit_end and collects unique pids.
    // We just need at least one unit per part_id to be tagged.
    // Distribute part_ids round-robin across units; if fewer units
    // than parts, tag the first unit with each part_id by writing
    // them all (the function dedupes).
    var numUnits = charRow.unit_end - charRow.unit_start;
    if (ids.length === 1) {
      for (var uw = charRow.unit_start; uw < charRow.unit_end; uw++) {
        unitPartIds[uw] = ids[0];
      }
    } else {
      // Multi-part char: we need _buildGroupsFromUnitPartIds to see all
      // part_ids. That function collects unique pids from each unit in
      // the char's range. So we distribute them: each unit gets one pid,
      // cycling through the ids. If numUnits < ids.length, some units
      // carry multiple — but the function only reads one per slot.
      // Instead, write each part_id to at least one unit.
      if (numUnits >= ids.length) {
        var idSlot = 0;
        for (var uw2 = charRow.unit_start; uw2 < charRow.unit_end; uw2++) {
          unitPartIds[uw2] = ids[idSlot % ids.length];
          idSlot++;
        }
      } else {
        // Fewer units than part_ids: we can only tag each unit with one
        // pid. The remaining pids won't be seen. To fix this, we augment
        // _buildGroupsFromUnitPartIds by passing extra info. But to avoid
        // changing that function, use a different approach: build the
        // charPartIds array directly and skip _buildGroupsFromUnitPartIds.
        // For now, tag what we can — we'll do a direct build below.
        for (var uw3 = charRow.unit_start; uw3 < charRow.unit_end; uw3++) {
          unitPartIds[uw3] = ids[Math.min(uw3 - charRow.unit_start, ids.length - 1)];
        }
      }
    }
  }

  // Check if any char has more part_ids than units — if so, the unit-level
  // approach can't represent all part_ids. Build groups directly from
  // charAssign instead.
  var needDirectBuild = false;
  for (var db = 0; db < surfaceMap.chars.length; db++) {
    var dbIds = charAssign[db];
    var dbRow = surfaceMap.chars[db];
    if (dbIds && dbIds.length > dbRow.unit_end - dbRow.unit_start) {
      needDirectBuild = true;
      break;
    }
  }
  if (needDirectBuild) {
    // Build groups directly from charAssign, same logic as
    // _buildGroupsFromUnitPartIds but reading from charAssign.
    var dGroups = [];
    var dBoundaries = [];
    var dGroupStart = 0;
    for (var dg = 0; dg < numSurfChars; dg++) {
      var sameAsPrev = false;
      if (dg > 0) {
        var prevIds = charAssign[dg - 1] || [];
        var currIds = charAssign[dg] || [];
        if (prevIds.length === currIds.length) {
          sameAsPrev = true;
          for (var dcmp = 0; dcmp < prevIds.length; dcmp++) {
            if (prevIds[dcmp] !== currIds[dcmp]) {
              sameAsPrev = false;
              break;
            }
          }
        }
      }
      if (!sameAsPrev && dg > 0) {
        var dpChar = surfaceMap.chars[dg - 1];
        var dsChar = surfaceMap.chars[dGroupStart];
        var dUnitText = surfaceMap.units.slice(dsChar.unit_start, dpChar.unit_end).join('');
        dGroups.push({
          start: dsChar.offset_start,
          end: dpChar.offset_end,
          part_ids: (charAssign[dg - 1] || []).slice(),
          part_count: (charAssign[dg - 1] || []).length,
          unit_start: dsChar.unit_start,
          unit_end: dpChar.unit_end,
          unit_text: dUnitText,
          unit_codepoints: toUnicodeCodePointList(dUnitText)
        });
        dBoundaries.push(dpChar.offset_end);
        dGroupStart = dg;
      }
    }
    // Close final group
    if (numSurfChars > 0) {
      var dlChar = surfaceMap.chars[numSurfChars - 1];
      var dfChar = surfaceMap.chars[dGroupStart];
      var dlUnitText = surfaceMap.units.slice(dfChar.unit_start, dlChar.unit_end).join('');
      dGroups.push({
        start: dfChar.offset_start,
        end: dlChar.offset_end,
        part_ids: (charAssign[numSurfChars - 1] || []).slice(),
        part_count: (charAssign[numSurfChars - 1] || []).length,
        unit_start: dfChar.unit_start,
        unit_end: dlChar.unit_end,
        unit_text: dlUnitText,
        unit_codepoints: toUnicodeCodePointList(dlUnitText)
      });
    }
    return attachRuntimeAlignmentDebug({
      boundaries: dBoundaries,
      groups: dGroups,
      match_basis: 'anchor_codepoint',
      codepoint_debug: {
        surface_chars: surfaceMap.chars.map(function (row) {
          return {
            index: row.index,
            char: row.char,
            unit_start: row.unit_start,
            unit_end: row.unit_end,
            unit_text: row.unit_text,
            unit_codepoints: Array.isArray(row.unit_codepoints) ? row.unit_codepoints.slice() : []
          };
        }),
        parts: normalizedParts.map(function (pt, idx) {
          var uText = decomposeTextToAlignmentUnits(pt, langCode).join('');
          return {
            part_id: idx,
            text: pt,
            unit_text: uText,
            unit_codepoints: toUnicodeCodePointList(uText)
          };
        })
      }
    });
  }
  return attachRuntimeAlignmentDebug(
    _buildGroupsFromUnitPartIds(surfaceMap, unitPartIds, normalizedParts, langCode, 'anchor_codepoint')
  );
}

// Build groups from per-unit part assignments, snapping boundaries to whole
// surface characters.
