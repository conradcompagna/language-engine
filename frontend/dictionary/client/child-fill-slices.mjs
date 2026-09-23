import {
  decomposeTextToAlignmentUnits,
  isKoreanLanguageCode,
  normalizeCompoundParts,
  normalizeFilterXposTag,
  normalizeXposTag,
  splitCompoundTags,
  toUnicodeCodePointList,
  uniqueNormalizedTags
} from './alignment-inputs.mjs';
import { getCurrentLanguage } from './core.mjs';
import { getBundledEntryKey } from './entry-adapters.mjs';
import { cloneMwtChildPieceRow } from './hydration.mjs';
import { buildGenericSurfacePartAlignment } from './surface-alignment.mjs';
export // Build groups from per-unit part assignments, snapping boundaries to whole
// surface characters.
function _buildGroupsFromUnitPartIds(surfaceMap, unitPartIds, normalizedParts, langCode, matchBasis) {
  // For each surface character, collect all part_ids its units belong to
  var charPartIds = []; // array of arrays
  for (var ci = 0; ci < surfaceMap.chars.length; ci++) {
    var charRow = surfaceMap.chars[ci];
    var ids = [];
    var idSeen = Object.create(null);
    for (var cu = charRow.unit_start; cu < charRow.unit_end; cu++) {
      var pid = unitPartIds[cu];
      if (pid >= 0 && !idSeen[pid]) {
        idSeen[pid] = true;
        ids.push(pid);
      }
    }
    // Sort part_ids for consistent comparison
    ids.sort(function (a, b) {
      return a - b;
    });
    charPartIds.push(ids);
  }

  // Merge consecutive characters with identical part_id sets into groups
  var groups = [];
  var boundaries = [];
  var groupStart = 0;
  for (var gi = 0; gi < charPartIds.length; gi++) {
    var sameAsPrev = false;
    if (gi > 0) {
      var prev = charPartIds[gi - 1];
      var curr = charPartIds[gi];
      if (prev.length === curr.length) {
        sameAsPrev = true;
        for (var cmp = 0; cmp < prev.length; cmp++) {
          if (prev[cmp] !== curr[cmp]) {
            sameAsPrev = false;
            break;
          }
        }
      }
    }
    if (!sameAsPrev && gi > 0) {
      // Close previous group
      var prevChar = surfaceMap.chars[gi - 1];
      var startChar = surfaceMap.chars[groupStart];
      var unitText = surfaceMap.units.slice(startChar.unit_start, prevChar.unit_end).join('');
      groups.push({
        start: startChar.offset_start,
        end: prevChar.offset_end,
        part_ids: charPartIds[gi - 1].slice(),
        part_count: charPartIds[gi - 1].length,
        unit_start: startChar.unit_start,
        unit_end: prevChar.unit_end,
        unit_text: unitText,
        unit_codepoints: toUnicodeCodePointList(unitText)
      });
      boundaries.push(prevChar.offset_end);
      groupStart = gi;
    }
  }
  // Close final group
  if (surfaceMap.chars.length > 0) {
    var lastChar = surfaceMap.chars[surfaceMap.chars.length - 1];
    var firstChar = surfaceMap.chars[groupStart];
    var lastUnitText = surfaceMap.units.slice(firstChar.unit_start, lastChar.unit_end).join('');
    groups.push({
      start: firstChar.offset_start,
      end: lastChar.offset_end,
      part_ids: charPartIds[charPartIds.length - 1].slice(),
      part_count: charPartIds[charPartIds.length - 1].length,
      unit_start: firstChar.unit_start,
      unit_end: lastChar.unit_end,
      unit_text: lastUnitText,
      unit_codepoints: toUnicodeCodePointList(lastUnitText)
    });
  }
  return {
    boundaries: boundaries,
    groups: groups,
    match_basis: matchBasis || 'codepoint',
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
  };
}

// Tier 3 fallback: split surface proportionally by lemma part lengths,
// snapping to character boundaries. Never returns null.
export function _buildProportionalAlignment(surfaceMap, normalizedParts, langCode) {
  var totalLemmaLen = 0;
  for (var tl = 0; tl < normalizedParts.length; tl++) {
    totalLemmaLen += normalizedParts[tl].length;
  }
  var numChars = surfaceMap.chars.length;
  var unitPartIds = new Array(surfaceMap.units.length);

  // Assign each character to a part proportionally
  var charCursor = 0;
  for (var pp = 0; pp < normalizedParts.length; pp++) {
    var share = normalizedParts[pp].length;
    var charCount;
    if (pp === normalizedParts.length - 1) {
      charCount = numChars - charCursor;
    } else {
      charCount = Math.max(1, Math.round((numChars * share) / (totalLemmaLen || 1)));
      if (charCursor + charCount > numChars) charCount = numChars - charCursor;
    }
    // Assign all units of these characters to this part
    for (var ac = charCursor; ac < charCursor + charCount && ac < numChars; ac++) {
      var charRow = surfaceMap.chars[ac];
      for (var au = charRow.unit_start; au < charRow.unit_end; au++) {
        unitPartIds[au] = pp;
      }
    }
    charCursor += charCount;
  }

  // Fill any remaining unassigned units (shouldn't happen, but safety)
  var lastPart = normalizedParts.length - 1;
  for (var fu = 0; fu < unitPartIds.length; fu++) {
    if (unitPartIds[fu] === undefined || unitPartIds[fu] < 0) {
      unitPartIds[fu] = lastPart;
    }
  }
  return _buildGroupsFromUnitPartIds(surfaceMap, unitPartIds, normalizedParts, langCode, 'proportional');
}
export function buildKoreanLemmaXposAlignment(surface, lemma, xpos, langOverride) {
  var activeLang = String(langOverride || getCurrentLanguage() || '').toLowerCase();
  if (!isKoreanLanguageCode(activeLang)) return null;
  var surfaceText = String(surface || '').trim();
  if (!surfaceText) return null;
  var lemmaParts = normalizeCompoundParts(splitCompoundTags(lemma), function (part) {
    return String(part || '').trim();
  });
  var xposParts = normalizeCompoundParts(splitCompoundTags(xpos), normalizeXposTag);
  if (!lemmaParts.length || !xposParts.length) return null;
  // Single-part lemmas should not constrain greedy decomposition. The Korean
  // grouping/filter rules only apply when Trankit gives an actual multi-part
  // lemma/XPOS analysis.
  if (lemmaParts.length <= 1) return null;
  var sharedXposGuard = lemmaParts.length !== xposParts.length;
  var sharedXposTags = uniqueNormalizedTags(xposParts, normalizeXposTag);
  function normalizedPartIds(partIds) {
    var ids = [];
    var idSeen = Object.create(null);
    for (var pi = 0; pi < (partIds || []).length; pi++) {
      var rawId = parseInt(partIds[pi], 10);
      if (!isFinite(rawId) || rawId < 0 || rawId >= lemmaParts.length || idSeen[rawId]) continue;
      idSeen[rawId] = true;
      ids.push(rawId);
    }
    return ids;
  }
  function xposTagsForPartIds(partIds) {
    var ids = normalizedPartIds(partIds);
    if (!ids.length) return null;
    if (sharedXposGuard) {
      return {
        ids: ids,
        tags: sharedXposTags.slice()
      };
    }
    var tags = [];
    for (var ti = 0; ti < ids.length; ti++) tags.push(xposParts[ids[ti]]);
    return {
      ids: ids,
      tags: uniqueNormalizedTags(tags, normalizeXposTag)
    };
  }
  var baseAlignment = buildGenericSurfacePartAlignment(surfaceText, lemmaParts, {
    langCode: activeLang,
    literalFallbackReason: 'syllable-fallback'
  });
  if (!baseAlignment || !baseAlignment.groups || !baseAlignment.groups.length) return null;
  var groups = [];
  for (var gi = 0; gi < baseAlignment.groups.length; gi++) {
    var baseGroup = baseAlignment.groups[gi] || {};
    var meta = xposTagsForPartIds(baseGroup.part_ids || []);
    if (!meta) return null;
    groups.push(
      Object.assign({}, baseGroup, {
        xpos_tags: meta.tags,
        part_ids: meta.ids,
        part_count: meta.ids.length,
        shared_xpos_guard: sharedXposGuard,
        unit_codepoints: Array.isArray(baseGroup.unit_codepoints) ? baseGroup.unit_codepoints.slice() : []
      })
    );
  }
  var codepointDebug = null;
  if (baseAlignment.codepoint_debug && typeof baseAlignment.codepoint_debug === 'object') {
    var debugParts = Array.isArray(baseAlignment.codepoint_debug.parts)
      ? baseAlignment.codepoint_debug.parts
      : [];
    codepointDebug = {
      shared_xpos_guard: sharedXposGuard,
      shared_xpos_tags: sharedXposTags.slice(),
      surface_chars: Array.isArray(baseAlignment.codepoint_debug.surface_chars)
        ? baseAlignment.codepoint_debug.surface_chars.slice()
        : [],
      lemma_parts: debugParts.map(function (row, idx) {
        return {
          part_id: idx,
          text: lemmaParts[idx],
          xpos: xposParts[idx] || '',
          unit_text: String((row && row.unit_text) || ''),
          unit_codepoints: Array.isArray(row && row.unit_codepoints) ? row.unit_codepoints.slice() : []
        };
      })
    };
  }
  return {
    boundaries: Array.isArray(baseAlignment.boundaries) ? baseAlignment.boundaries.slice() : [],
    groups: groups,
    match_basis: String(baseAlignment.match_basis || ''),
    shared_xpos_guard: sharedXposGuard,
    codepoint_debug: codepointDebug
  };
}
export function buildDebugLemmaAlignment(surface, lemma, xpos, langOverride) {
  var activeLang = String(langOverride || getCurrentLanguage() || '').toLowerCase();
  var surfaceText = String(surface || '').trim();
  if (!surfaceText) return null;
  var lemmaParts = normalizeCompoundParts(splitCompoundTags(lemma), function (part) {
    return String(part || '').trim();
  });
  if (!lemmaParts.length) return null;
  // Single-part lemma: the whole surface maps to it, no alignment needed
  if (lemmaParts.length <= 1) return null;
  function normalizeDebugXposTag(rawTag) {
    return normalizeFilterXposTag(rawTag, activeLang);
  }
  var xposParts = normalizeCompoundParts(splitCompoundTags(xpos), normalizeDebugXposTag);
  var sharedXposGuard = xposParts.length > 0 && lemmaParts.length !== xposParts.length;
  var sharedXposTags = uniqueNormalizedTags(xposParts, normalizeDebugXposTag);
  function normalizedPartIds(partIds) {
    var ids = [];
    var seen = Object.create(null);
    for (var pi = 0; pi < (partIds || []).length; pi++) {
      var rawId = parseInt(partIds[pi], 10);
      if (!isFinite(rawId) || rawId < 0 || rawId >= lemmaParts.length || seen[rawId]) continue;
      seen[rawId] = true;
      ids.push(rawId);
    }
    return ids;
  }
  function xposTagsForPartIds(partIds) {
    var ids = normalizedPartIds(partIds);
    if (!ids.length) return [];
    if (!xposParts.length) return [];
    if (sharedXposGuard) return sharedXposTags.slice();
    var tags = [];
    for (var ti = 0; ti < ids.length; ti++) {
      var tag = String(xposParts[ids[ti]] || '').trim();
      if (tag) tags.push(tag);
    }
    return uniqueNormalizedTags(tags, normalizeDebugXposTag);
  }
  var baseAlignment = buildGenericSurfacePartAlignment(surfaceText, lemmaParts, {
    langCode: activeLang,
    literalFallbackReason: 'literal-fallback'
  });
  if (!baseAlignment || !Array.isArray(baseAlignment.groups) || !baseAlignment.groups.length) return null;
  var groups = [];
  for (var gi = 0; gi < baseAlignment.groups.length; gi++) {
    var baseGroup = baseAlignment.groups[gi] || {};
    var partIds = normalizedPartIds(baseGroup.part_ids || []);
    groups.push(
      Object.assign({}, baseGroup, {
        part_ids: partIds,
        part_count: partIds.length,
        xpos_tags: xposTagsForPartIds(partIds),
        shared_xpos_guard: sharedXposGuard,
        unit_codepoints: Array.isArray(baseGroup.unit_codepoints) ? baseGroup.unit_codepoints.slice() : []
      })
    );
  }
  var codepointDebug = null;
  if (baseAlignment.codepoint_debug && typeof baseAlignment.codepoint_debug === 'object') {
    var debugParts = Array.isArray(baseAlignment.codepoint_debug.parts)
      ? baseAlignment.codepoint_debug.parts
      : [];
    codepointDebug = {
      shared_xpos_guard: sharedXposGuard,
      shared_xpos_tags: sharedXposTags.slice(),
      surface_chars: Array.isArray(baseAlignment.codepoint_debug.surface_chars)
        ? baseAlignment.codepoint_debug.surface_chars.slice()
        : [],
      lemma_parts: debugParts.map(function (row, idx) {
        return {
          part_id: idx,
          text: lemmaParts[idx],
          xpos: xposParts[idx] || '',
          unit_text: String((row && row.unit_text) || ''),
          unit_codepoints: Array.isArray(row && row.unit_codepoints) ? row.unit_codepoints.slice() : []
        };
      })
    };
  }
  return {
    boundaries: Array.isArray(baseAlignment.boundaries) ? baseAlignment.boundaries.slice() : [],
    groups: groups,
    match_basis: String(baseAlignment.match_basis || ''),
    shared_xpos_guard: sharedXposGuard,
    codepoint_debug: codepointDebug
  };
}
export function getFillPieceSurfaceText(fillEntry) {
  if (!fillEntry || typeof fillEntry !== 'object') return '';
  if (fillEntry.text != null) return String(fillEntry.text);
  if (fillEntry.head != null) return String(fillEntry.head);
  return '';
}
export function buildLocalizedMwtPartRows(rows, fillIndexes, partStart, partEnd) {
  var srcRows = Array.isArray(rows) ? rows : [];
  var srcIndexes = Array.isArray(fillIndexes) ? fillIndexes : [];
  var localizedRows = [];
  var globalIndexes = [];
  for (var i = 0; i < srcIndexes.length; i++) {
    var globalIdx = parseInt(srcIndexes[i], 10);
    if (!isFinite(globalIdx) || globalIdx < 0 || globalIdx >= srcRows.length) continue;
    var row = srcRows[globalIdx] || {};
    var clone = {};
    for (var key in row) {
      if (Object.prototype.hasOwnProperty.call(row, key)) clone[key] = row[key];
    }
    var rowStart = parseInt(row._surface_start, 10);
    var rowEnd = parseInt(row._surface_end, 10);
    if (
      isFinite(rowStart) &&
      isFinite(rowEnd) &&
      rowEnd > rowStart &&
      rowStart >= partStart &&
      rowEnd <= partEnd
    ) {
      clone._surface_start = rowStart - partStart;
      clone._surface_end = rowEnd - partStart;
    } else {
      if (Object.prototype.hasOwnProperty.call(clone, '_surface_start')) delete clone._surface_start;
      if (Object.prototype.hasOwnProperty.call(clone, '_surface_end')) delete clone._surface_end;
    }
    localizedRows.push(clone);
    globalIndexes.push(globalIdx);
  }
  return {
    rows: localizedRows,
    global_indexes: globalIndexes
  };
}
export function remapLocalizedMwtPartSlices(localSlices, globalIndexes, partStart) {
  var slices = Array.isArray(localSlices) ? localSlices : [];
  var mappedIndexes = Array.isArray(globalIndexes) ? globalIndexes : [];
  var out = [];
  for (var i = 0; i < slices.length; i++) {
    var localSlice = slices[i] || {};
    var start = parseInt(localSlice.start, 10);
    var end = parseInt(localSlice.end, 10);
    if (!isFinite(start) || !isFinite(end) || end <= start) continue;
    var rawIds = Array.isArray(localSlice.fill_indexes)
      ? localSlice.fill_indexes
      : Array.isArray(localSlice.fillIndexes)
        ? localSlice.fillIndexes
        : [];
    var fillIndexes = [];
    var seen = Object.create(null);
    for (var j = 0; j < rawIds.length; j++) {
      var localIdx = parseInt(rawIds[j], 10);
      if (!isFinite(localIdx) || localIdx < 0 || localIdx >= mappedIndexes.length) continue;
      var globalIdx = mappedIndexes[localIdx];
      if (!isFinite(globalIdx) || globalIdx < 0 || seen[globalIdx]) continue;
      seen[globalIdx] = true;
      fillIndexes.push(globalIdx);
    }
    if (!fillIndexes.length) continue;
    out.push({
      start: partStart + start,
      end: partStart + end,
      fill_indexes: fillIndexes
    });
  }
  return out;
}
export function collectSyntheticSliceEntries(rows) {
  var src = Array.isArray(rows) ? rows : [];
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < src.length; i++) {
    var row = src[i] || {};
    var rowEntries = Array.isArray(row.entries) ? row.entries : [];
    if (!rowEntries.length && row._winner_ref) rowEntries = [row._winner_ref];
    for (var ei = 0; ei < rowEntries.length; ei++) {
      var entry = rowEntries[ei];
      if (!entry) continue;
      var key = getBundledEntryKey(entry) || 'anon|' + i + '|' + ei;
      if (seen[key]) continue;
      seen[key] = 1;
      out.push(entry);
    }
  }
  return out;
}
export function buildSyntheticMwtChildSliceRow(surfaceText, groupedRows) {
  var rows = Array.isArray(groupedRows) ? groupedRows : [];
  var base = rows.length ? rows[0] : {};
  var out = {};
  for (var key in base) {
    if (Object.prototype.hasOwnProperty.call(base, key)) out[key] = base[key];
  }
  var groupedEntries = collectSyntheticSliceEntries(rows);
  out.text = String(surfaceText || '');
  out.surface_form = String(surfaceText || '');
  out.entries = groupedEntries;

  // If this synthetic slice is really just one original piece row,
  // preserve the original compact winner ref too.
  if (rows.length === 1 && rows[0] && rows[0]._winner_ref) {
    out._winner_ref = rows[0]._winner_ref;
  }

  // Keep lexical display info from the representative piece row.
  // Do NOT overwrite head/headword unless they are blank.
  if (!out.head && out.text) out.head = out.text;
  if (!out.headword && out.head) out.headword = out.head;
  delete out._mwt_child_piece_rows;
  return out;
}
export function explodeMwtChildGreedyRows(surfaceText, fillRows, langCode) {
  var surface = String(surfaceText || '');
  var rows = Array.isArray(fillRows) ? fillRows : [];
  if (!surface || !rows.length) return rows.slice();
  var out = [];
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var pieceRows = Array.isArray(row._mwt_child_piece_rows) ? row._mwt_child_piece_rows : null;
    var rowStart = parseInt(row._surface_start, 10);
    var rowEnd = parseInt(row._surface_end, 10);
    var isGreedyChild =
      row._mwt_child_resolution_category &&
      row._mwt_child_resolution_category !== 'exact_match' &&
      row._mwt_child_resolution_category !== 'exact_lemma_match' &&
      row._mwt_child_resolution_category !== 'lemma_override' &&
      row._mwt_child_resolution_category !== 'lemma_partial_override';
    if (
      !isGreedyChild ||
      !pieceRows ||
      !pieceRows.length ||
      !isFinite(rowStart) ||
      !isFinite(rowEnd) ||
      rowEnd <= rowStart
    ) {
      out.push(row);
      continue;
    }
    var localSurface = surface.slice(rowStart, rowEnd);
    if (!localSurface) {
      out.push(row);
      continue;
    }

    // Child piece rows are aligned inside the child slice only.
    var localRows = pieceRows.map(cloneMwtChildPieceRow);

    // Python supplies the authoritative child-local → parent-relative char
    // lattice in row._mwt_child_char_map. If it's present and every piece
    // carries valid child-local offsets, remap each piece directly using
    // the lattice — no JS char-aware alignment, no proportional math.
    var charMap = Array.isArray(row._mwt_child_char_map) ? row._mwt_child_char_map : null;
    var childLocalSurface = null;
    if (charMap && charMap.length) {
      // Reconstruct the unsandhied child surface by walking piece offsets.
      // The lattice is keyed to child-local char indices, so its length is
      // len(child_surface_text). We still need that length to validate.
      childLocalSurface = '';
      for (var _plri = 0; _plri < localRows.length; _plri++) {
        var _plrRow = localRows[_plri] || {};
        var _plrText = typeof _plrRow.text === 'string' ? _plrRow.text : '';
        childLocalSurface += _plrText;
      }
    }
    var usedCharMap = false;
    if (charMap && charMap.length && childLocalSurface && charMap.length >= childLocalSurface.length) {
      // Pass 1: compute raw [gStart, gEnd] for each non-empty piece via the lattice.
      var piecePlan = [];
      var cursorCM = 0;
      for (var pci = 0; pci < localRows.length; pci++) {
        var pcRow = localRows[pci] || {};
        var pcText = typeof pcRow.text === 'string' ? pcRow.text : '';
        if (!pcText) {
          continue;
        }
        var lo = cursorCM;
        var hi = cursorCM + pcText.length;
        cursorCM = hi;
        if (hi > charMap.length) break;
        var gStart = charMap[lo];
        var gEnd = charMap[hi - 1] + 1;
        if (!isFinite(gStart) || !isFinite(gEnd)) continue;
        if (gStart < rowStart) gStart = rowStart;
        if (gEnd > rowEnd) gEnd = rowEnd;
        if (gEnd < gStart) gEnd = gStart;
        piecePlan.push({
          row: pcRow,
          start: gStart,
          end: gEnd
        });
      }
      // Pass 2: drop zero-width pieces (they'd otherwise hover with the whole
      // token because no surface char belongs to them), then tile so the
      // remaining pieces fully cover [rowStart, rowEnd] with no gaps. Every
      // surface character must belong to exactly one piece.
      var nonEmpty = [];
      for (var ppi = 0; ppi < piecePlan.length; ppi++) {
        if (piecePlan[ppi].end > piecePlan[ppi].start) nonEmpty.push(piecePlan[ppi]);
      }
      if (nonEmpty.length) {
        // Monotonicity: each piece starts no earlier than its predecessor.
        for (var mi = 1; mi < nonEmpty.length; mi++) {
          if (nonEmpty[mi].start < nonEmpty[mi - 1].start) {
            nonEmpty[mi].start = nonEmpty[mi - 1].start;
            if (nonEmpty[mi].end < nonEmpty[mi].start) nonEmpty[mi].end = nonEmpty[mi].start;
          }
        }
        // First piece claims from rowStart; each piece extends to the next
        // piece's start; the last piece extends to rowEnd.
        nonEmpty[0].start = rowStart;
        for (var ti = 0; ti < nonEmpty.length - 1; ti++) {
          nonEmpty[ti].end = nonEmpty[ti + 1].start;
          if (nonEmpty[ti].end < nonEmpty[ti].start) nonEmpty[ti].end = nonEmpty[ti].start;
        }
        nonEmpty[nonEmpty.length - 1].end = rowEnd;
        for (var ei = 0; ei < nonEmpty.length; ei++) {
          var piece = nonEmpty[ei];
          if (piece.end <= piece.start) continue;
          var synthSurface = surface.slice(piece.start, piece.end);
          var synthRow = buildSyntheticMwtChildSliceRow(synthSurface, [piece.row]);
          var pieceLocalStart = parseInt(piece.row && piece.row._surface_start, 10);
          var pieceLocalEnd = parseInt(piece.row && piece.row._surface_end, 10);
          var pieceLocalText =
            typeof (piece.row && piece.row.text) === 'string'
              ? String(piece.row.text || '')
              : String((piece.row && piece.row.surface_form) || '');
          if (
            !pieceLocalText &&
            childLocalSurface &&
            isFinite(pieceLocalStart) &&
            isFinite(pieceLocalEnd) &&
            pieceLocalEnd > pieceLocalStart
          ) {
            pieceLocalText = childLocalSurface.slice(pieceLocalStart, pieceLocalEnd);
          }
          synthRow._surface_start = piece.start;
          synthRow._surface_end = piece.end;
          if (pieceLocalText) synthRow._mwt_child_text = pieceLocalText;
          if (isFinite(pieceLocalStart) && isFinite(pieceLocalEnd) && pieceLocalEnd >= pieceLocalStart) {
            synthRow._mwt_child_local_start = pieceLocalStart;
            synthRow._mwt_child_local_end = pieceLocalEnd;
          }
          synthRow._mwt_part_index = row._mwt_part_index;
          synthRow._mwt_child_resolution_category = row._mwt_child_resolution_category;
          if (row._lemma_upos_hint) synthRow._lemma_upos_hint = row._lemma_upos_hint;
          if (row._lemma_xpos_hint) synthRow._lemma_xpos_hint = row._lemma_xpos_hint;
          if (row._lemma_promoted) synthRow._lemma_promoted = true;
          if (row._lemma_override) synthRow._lemma_override = true;
          out.push(synthRow);
        }
        usedCharMap = true;
      }
    }
    if (usedCharMap) continue;

    // Fallback (no char_map available): keep the bundled row intact. No JS
    // proportional alignment — spec forbids it.
    out.push(row);
  }
  return out;
}
export function _buildPerChildFillSlices(surface, fills, mwtParts) {
  var surfaceText = String(surface || '');
  var rows = Array.isArray(fills) ? fills : [];
  var parts = Array.isArray(mwtParts) ? mwtParts : [];
  if (!surfaceText || !rows.length || parts.length < 2) return [];

  // Group fill indexes by _mwt_part_index.
  var fillsByPart = {};
  var anyTagged = false;
  for (var ri = 0; ri < rows.length; ri++) {
    var pi = parseInt(rows[ri] && rows[ri]._mwt_part_index, 10);
    if (isFinite(pi)) {
      anyTagged = true;
      if (!fillsByPart[pi]) fillsByPart[pi] = [];
      fillsByPart[pi].push(ri);
    }
  }
  if (!anyTagged) return [];
  var allSlices = [];
  for (var ci = 0; ci < parts.length; ci++) {
    var part = parts[ci] || {};
    var childText = String(part.text || '');
    if (!childText) continue;
    var childFillIdxs = fillsByPart[ci];
    if (!childFillIdxs || !childFillIdxs.length) continue;

    // Use the Python-computed surface_slice directly.  The MWT per-child
    // branch produces exactly one bundled fill per child whose
    // _surface_start/_surface_end match the part's surface_slice.  Never
    // re-derive from child text length — sandhi means the child text and
    // the surface slice can differ in width.
    var rawSlice = Array.isArray(part.surface_slice) ? part.surface_slice : null;
    var partStart = 0;
    var partEnd = childText.length;
    if (rawSlice && rawSlice.length >= 2) {
      partStart = parseInt(rawSlice[0], 10) || 0;
      partEnd = parseInt(rawSlice[1], 10) || partStart + childText.length;
    }
    allSlices.push({
      start: partStart,
      end: partEnd,
      fill_indexes: childFillIdxs.slice()
    });
  }
  return allSlices;
}
