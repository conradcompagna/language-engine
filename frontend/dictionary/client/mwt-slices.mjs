import {
  annotateLiveLemmaLinkedFills,
  decomposeHangulSyllable,
  isKoreanLanguageCode,
  normalizeJamoForComparison
} from './alignment-inputs.mjs';
import {
  buildLocalizedMwtPartRows,
  explodeMwtChildGreedyRows,
  getFillPieceSurfaceText,
  remapLocalizedMwtPartSlices
} from './child-fill-slices.mjs';
import { getCurrentLanguage } from './core.mjs';
import { coreState } from './core.state.mjs';
import { prepareFillEntries } from './lookup-payloads.mjs';
export function buildMwtSurfaceSlicesFromParts(surface, fills, mwtParts) {
  var surfaceText = String(surface || '');
  var rows = Array.isArray(fills) ? fills : [];
  var parts = Array.isArray(mwtParts) ? mwtParts : [];
  if (!surfaceText || !rows.length || parts.length < 2) return [];
  var slices = [];
  var cursor = 0;
  var claimedFillIndexes = Object.create(null);
  for (var i = 0; i < parts.length; i++) {
    var part = parts[i] || {};
    var partText = String(part.text || '');
    var rawSlice = Array.isArray(part.surface_slice) ? part.surface_slice : null;
    var start = cursor;
    var end = cursor + partText.length;
    if (rawSlice && rawSlice.length >= 2) {
      start = parseInt(rawSlice[0], 10);
      end = parseInt(rawSlice[1], 10);
    } else {
      if (!partText) return [];
      if (surfaceText.slice(cursor, cursor + partText.length) !== partText) return [];
    }
    if (!isFinite(start) || start < 0) start = 0;
    if (!isFinite(end) || end < start) end = start;
    if (end > surfaceText.length) end = surfaceText.length;
    if (start < cursor) return [];
    var fillIndexes = [];
    for (var ri = 0; ri < rows.length; ri++) {
      if (claimedFillIndexes[ri]) continue;
      var mappedPart = parseInt(rows[ri] && rows[ri]._lemma_part_index, 10);
      if (isFinite(mappedPart) && mappedPart === i) fillIndexes.push(ri);
    }
    if (!fillIndexes.length) {
      for (var rj = 0; rj < rows.length; rj++) {
        if (claimedFillIndexes[rj]) continue;
        var row = rows[rj] || {};
        var rowStart = parseInt(row._surface_start, 10);
        var rowEnd = parseInt(row._surface_end, 10);
        if (!isFinite(rowStart) || !isFinite(rowEnd) || rowEnd <= rowStart) continue;
        if (rowEnd <= start || rowStart >= end) continue;
        fillIndexes.push(rj);
      }
    }
    if (!fillIndexes.length) return [];
    var localized = buildLocalizedMwtPartRows(rows, fillIndexes, start, end);
    var partSlices = [];
    if (localized.global_indexes.length === 1) {
      partSlices.push({
        start: start,
        end: end,
        fill_indexes: localized.global_indexes.slice()
      });
    } else if (localized.global_indexes.length > 1) {
      var localSurface = surfaceText.slice(start, end);
      var localRows = localized.rows;
      var localSlices = buildFillSurfaceSlicesFromExplicitOffsets(localSurface, localRows);
      if (!localSlices.length) {
        localSlices = buildFillSurfaceSlices(localSurface, localRows, getCurrentLanguage());
      }
      partSlices = remapLocalizedMwtPartSlices(localSlices, localized.global_indexes, start);
      if (!partSlices.length) {
        partSlices.push({
          start: start,
          end: end,
          fill_indexes: localized.global_indexes.slice()
        });
      }
    }
    if (!partSlices.length) return [];
    for (var psi = 0; psi < partSlices.length; psi++) {
      var ids = Array.isArray(partSlices[psi].fill_indexes) ? partSlices[psi].fill_indexes : [];
      for (var fi = 0; fi < ids.length; fi++) claimedFillIndexes[ids[fi]] = true;
      slices.push(partSlices[psi]);
    }
    cursor = end;
  }
  if (cursor !== surfaceText.length || !slices.length) return [];
  _attachOrphanFills(slices, rows.length);
  return slices;
}
export function applyMwtUiPosShading(rows, mwtParts, surfaceText) {
  var fillRows = Array.isArray(rows) ? rows : [];
  var parts = Array.isArray(mwtParts) ? mwtParts : [];
  var surface = String(surfaceText || '');
  if (!fillRows.length || parts.length < 2 || !surface) return fillRows;
  var partRanges = [];
  var cursor = 0;
  for (var i = 0; i < parts.length; i++) {
    var part = parts[i] || {};
    var partText = String(part.text || '');
    var rawSlice = Array.isArray(part.surface_slice) ? part.surface_slice : null;
    var start = cursor;
    var nextCursor = cursor + partText.length;
    if (rawSlice && rawSlice.length >= 2) {
      start = parseInt(rawSlice[0], 10);
      nextCursor = parseInt(rawSlice[1], 10);
    } else if (!partText) {
      return fillRows;
    }
    if (!isFinite(start) || start < 0) start = 0;
    if (!isFinite(nextCursor) || nextCursor < start) nextCursor = start;
    if (nextCursor > surface.length) nextCursor = surface.length;
    partRanges.push({
      index: i,
      start: start,
      end: nextCursor,
      upos: String(part.upos || '').trim(),
      xpos: String(part.tag || part.xpos || '').trim()
    });
    cursor = nextCursor;
  }
  for (var ri = 0; ri < fillRows.length; ri++) {
    var row = fillRows[ri] || {};
    if (!row || typeof row !== 'object') continue;
    var partIndex = parseInt(row._mwt_part_index, 10);
    if (!isFinite(partIndex)) partIndex = parseInt(row._lemma_part_index, 10);
    var matchedPart =
      isFinite(partIndex) && partIndex >= 0 && partIndex < partRanges.length ? partRanges[partIndex] : null;
    if (!matchedPart) {
      var rowStart = parseInt(row._surface_start, 10);
      var rowEnd = parseInt(row._surface_end, 10);
      if (isFinite(rowStart) && isFinite(rowEnd) && rowEnd > rowStart) {
        var bestPart = null;
        var bestOverlap = 0;
        for (var pi = 0; pi < partRanges.length; pi++) {
          var overlap = Math.min(rowEnd, partRanges[pi].end) - Math.max(rowStart, partRanges[pi].start);
          if (overlap > bestOverlap) {
            bestOverlap = overlap;
            bestPart = partRanges[pi];
          }
        }
        matchedPart = bestPart;
      }
    }
    if (!matchedPart) continue;
    if (matchedPart.upos) {
      row.upos = matchedPart.upos;
      row.upos_label = matchedPart.upos;
      row.upos_color = coreState.UPOS_COLORS[matchedPart.upos] || '#d1d5db';
    }
    if (matchedPart.xpos) {
      row.tag = matchedPart.xpos;
      row.xpos = matchedPart.xpos;
    }
  }
  return fillRows;
}

// Build fill surface slices for MWT tokens where each fill row already carries
// authoritative Trankit character offsets (_surface_start/_surface_end).
// No string matching — offsets are the sole source of truth.
export function buildMwtFillSurfaceSlicesFromOffsets(fills) {
  var rows = Array.isArray(fills) ? fills : [];
  if (!rows.length) return [];
  var slices = [];
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var start = parseInt(row._surface_start, 10);
    var end = parseInt(row._surface_end, 10);
    if (!isFinite(start) || !isFinite(end) || end <= start) return [];
    slices.push({
      start: start,
      end: end,
      fill_indexes: [i]
    });
  }
  return slices;
}
export function buildFillSurfaceSlicesFromExplicitOffsets(surface, fills) {
  var surfaceText = String(surface || '');
  var rows = Array.isArray(fills) ? fills : [];
  if (!surfaceText || rows.length < 2) return [];
  var slices = [];
  var alignableCount = 0;
  var prevStart = -1;
  var prevEnd = -1;
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var pieceText = getFillPieceSurfaceText(row);
    if (!pieceText) continue;
    alignableCount += 1;
    var start = parseInt(row._surface_start, 10);
    var end = parseInt(row._surface_end, 10);
    if (!isFinite(start) || !isFinite(end)) return [];
    if (start < 0 || end > surfaceText.length || end <= start) return [];
    var sameSpanAsPrev = start === prevStart && end === prevEnd;
    if (!sameSpanAsPrev && prevEnd >= 0 && start < prevEnd) return [];
    if (slices.length && slices[slices.length - 1].start === start && slices[slices.length - 1].end === end) {
      slices[slices.length - 1].fill_indexes.push(i);
    } else {
      slices.push({
        start: start,
        end: end,
        fill_indexes: [i]
      });
    }
    prevStart = start;
    prevEnd = end;
  }
  if (alignableCount < 2 || !slices.length) return [];
  _attachOrphanFills(slices, rows.length);
  return slices;
}
export function buildFillSurfaceSlices(surface, fills, langOverride) {
  var surfaceText = String(surface || '');
  var rows = Array.isArray(fills) ? fills : [];
  if (!surfaceText || rows.length < 2) return [];

  // When the lookup pipeline already attached explicit surface spans to each
  // fill row, those spans are the source of truth. Do not re-slice them here.
  var explicitSlices = buildFillSurfaceSlicesFromExplicitOffsets(surfaceText, rows);
  if (explicitSlices.length) return explicitSlices;
  var langCode = String(langOverride || getCurrentLanguage() || '').toLowerCase();

  // --- Step 1: extract surface text for each fill piece ---
  var alignableIndexes = [];
  var pieceTexts = [];
  for (var i = 0; i < rows.length; i++) {
    var pieceText = getFillPieceSurfaceText(rows[i]);
    if (pieceText) {
      alignableIndexes.push(i);
      pieceTexts.push(pieceText);
    }
  }
  if (!pieceTexts.length) return [];

  // Single alignable fill covers the whole surface
  if (pieceTexts.length === 1) {
    var allIds = [alignableIndexes[0]];
    for (var oi = 0; oi < rows.length; oi++) {
      if (oi !== alignableIndexes[0]) allIds.push(oi);
    }
    allIds.sort(function (a, b) {
      return a - b;
    });
    return [
      {
        start: 0,
        end: surfaceText.length,
        fill_indexes: allIds
      }
    ];
  }

  // --- Step 2: exact concatenation check ---
  var joined = pieceTexts.join('');
  if (joined === surfaceText) {
    var slices = [];
    var cursor = 0;
    for (var ei = 0; ei < pieceTexts.length; ei++) {
      var nextCursor = cursor + pieceTexts[ei].length;
      slices.push({
        start: cursor,
        end: nextCursor,
        fill_indexes: [alignableIndexes[ei]]
      });
      cursor = nextCursor;
    }
    _attachOrphanFills(slices, rows.length);
    return slices;
  }

  // --- Step 3: character-level trivial alignment ---
  // If the characters in the fills line up with the surface characters
  // in order (just spread across different piece boundaries), use that.
  var surfaceChars = Array.from(surfaceText);
  var trivialOk = true;
  var trivialSlices = [];
  var sIdx = 0;
  for (var ti = 0; ti < pieceTexts.length && trivialOk; ti++) {
    var pChars = Array.from(pieceTexts[ti]);
    var sliceStart = sIdx;
    for (var pc = 0; pc < pChars.length; pc++) {
      if (sIdx >= surfaceChars.length || pChars[pc] !== surfaceChars[sIdx]) {
        trivialOk = false;
        break;
      }
      sIdx++;
    }
    if (trivialOk) {
      // Convert character index back to string offset
      var offsetStart = 0;
      for (var os = 0; os < sliceStart; os++) offsetStart += surfaceChars[os].length;
      var offsetEnd = offsetStart;
      for (var oe = sliceStart; oe < sIdx; oe++) offsetEnd += surfaceChars[oe].length;
      trivialSlices.push({
        start: offsetStart,
        end: offsetEnd,
        fill_indexes: [alignableIndexes[ti]]
      });
    }
  }
  if (trivialOk && sIdx === surfaceChars.length) {
    _attachOrphanFills(trivialSlices, rows.length);
    return trivialSlices;
  }

  // --- Step 4: Needleman-Wunsch alignment ---
  // Run NW on fill piece characters against surface characters.
  // Pieces that match get frozen in place; unmatched pieces and
  // unmatched surface gaps are resolved in step 5.
  //
  // For Korean: decompose Hangul syllables into jamo for NW comparison,
  // then map jamo matches back to original surface character indices.

  var isKorean = isKoreanLanguageCode(langCode);

  // Build flat arrays for NW. For Korean, these are jamo units;
  // for other languages, plain characters.
  var surfaceNWUnits = []; // units used for NW comparison
  var surfaceNWToChar = []; // maps each NW unit index -> surfaceChars index
  for (var sci = 0; sci < surfaceChars.length; sci++) {
    if (isKorean) {
      var sJamo = decomposeHangulSyllable(surfaceChars[sci]);
      for (var sji = 0; sji < sJamo.length; sji++) {
        surfaceNWUnits.push(normalizeJamoForComparison(sJamo[sji]));
        surfaceNWToChar.push(sci);
      }
    } else {
      surfaceNWUnits.push(surfaceChars[sci]);
      surfaceNWToChar.push(sci);
    }
  }
  var fillNWUnits = [];
  var fillNWPieceIdx = []; // which pieceTexts index each NW unit belongs to
  for (var fi = 0; fi < pieceTexts.length; fi++) {
    var fChars = Array.from(pieceTexts[fi]);
    for (var fc = 0; fc < fChars.length; fc++) {
      if (isKorean) {
        var fJamo = decomposeHangulSyllable(fChars[fc]);
        for (var fji = 0; fji < fJamo.length; fji++) {
          fillNWUnits.push(normalizeJamoForComparison(fJamo[fji]));
          fillNWPieceIdx.push(fi);
        }
      } else {
        fillNWUnits.push(fChars[fc]);
        fillNWPieceIdx.push(fi);
      }
    }
  }
  var sLen = surfaceChars.length;
  var sNWLen = surfaceNWUnits.length;
  var fNWLen = fillNWUnits.length;

  // NW scoring
  var MATCH = 2,
    MISMATCH = -1,
    GAP = -1;
  var nwRows = sNWLen + 1;
  var nwCols = fNWLen + 1;
  var sc = new Array(nwRows);
  for (var si = 0; si < nwRows; si++) {
    sc[si] = new Array(nwCols);
    sc[si][0] = si * GAP;
  }
  for (var fj = 0; fj < nwCols; fj++) sc[0][fj] = fj * GAP;
  for (var si2 = 1; si2 < nwRows; si2++) {
    for (var fj2 = 1; fj2 < nwCols; fj2++) {
      var diag = sc[si2 - 1][fj2 - 1] + (surfaceNWUnits[si2 - 1] === fillNWUnits[fj2 - 1] ? MATCH : MISMATCH);
      var up = sc[si2 - 1][fj2] + GAP;
      var left = sc[si2][fj2 - 1] + GAP;
      sc[si2][fj2] = Math.max(diag, up, left);
    }
  }

  // Traceback: record which surface chars matched which piece index(es).
  // NW runs on jamo/units; we project matches back to surfaceChars indices.
  // For Korean, a single surface char (syllable) can span multiple pieces
  // when its jamo decomposition matches parts from different lemma pieces.
  var surfaceCharPieces = []; // array of arrays: piece indexes per surface char
  for (var sm = 0; sm < sLen; sm++) surfaceCharPieces.push([]);
  var pieceMatchCount = new Array(pieceTexts.length);
  for (var pm = 0; pm < pieceTexts.length; pm++) pieceMatchCount[pm] = 0;
  var tbi = sNWLen,
    tbj = fNWLen;
  while (tbi > 0 && tbj > 0) {
    var cur = sc[tbi][tbj];
    var diagVal =
      sc[tbi - 1][tbj - 1] + (surfaceNWUnits[tbi - 1] === fillNWUnits[tbj - 1] ? MATCH : MISMATCH);
    if (cur === diagVal) {
      if (surfaceNWUnits[tbi - 1] === fillNWUnits[tbj - 1]) {
        var origCharIdx = surfaceNWToChar[tbi - 1];
        var matchedPiece = fillNWPieceIdx[tbj - 1];
        if (surfaceCharPieces[origCharIdx].indexOf(matchedPiece) < 0) {
          surfaceCharPieces[origCharIdx].push(matchedPiece);
        }
        pieceMatchCount[matchedPiece]++;
      }
      tbi--;
      tbj--;
    } else if (cur === sc[tbi - 1][tbj] + GAP) {
      tbi--;
    } else {
      tbj--;
    }
  }

  // Identify frozen pieces (pieces with at least one NW match)
  var pieceFrozen = new Array(pieceTexts.length);
  for (var pf = 0; pf < pieceTexts.length; pf++) {
    pieceFrozen[pf] = pieceMatchCount[pf] > 0;
  }

  // For each frozen piece, find its surface char range (min..max matched)
  var pieceMinChar = new Array(pieceTexts.length);
  var pieceMaxChar = new Array(pieceTexts.length);
  for (var pr = 0; pr < pieceTexts.length; pr++) {
    pieceMinChar[pr] = sLen;
    pieceMaxChar[pr] = -1;
  }
  for (var sr = 0; sr < sLen; sr++) {
    var charPieces = surfaceCharPieces[sr];
    for (var cpi = 0; cpi < charPieces.length; cpi++) {
      var mp = charPieces[cpi];
      if (sr < pieceMinChar[mp]) pieceMinChar[mp] = sr;
      if (sr > pieceMaxChar[mp]) pieceMaxChar[mp] = sr;
    }
  }

  // Expand each frozen piece to cover its full matched range (fill interior gaps).
  // For Korean, a single char can belong to multiple pieces (jamo spanning pieces).
  // Use frozenAssign for the primary piece, and track multi-piece chars separately.
  var frozenAssign = new Array(sLen);
  for (var fa = 0; fa < sLen; fa++) frozenAssign[fa] = -1;
  for (var fp = 0; fp < pieceTexts.length; fp++) {
    if (!pieceFrozen[fp]) continue;
    for (var fx = pieceMinChar[fp]; fx <= pieceMaxChar[fp]; fx++) {
      if (frozenAssign[fx] < 0) frozenAssign[fx] = fp;
    }
  }

  // Build frozen slices from contiguous runs of the same piece.
  // When a surface char has multiple piece assignments (Korean jamo spanning),
  // merge those pieces into a single slice.
  var frozenSlices = []; // {start_char, end_char, piece_idx -or- piece_idxs}
  var gapRegions = []; // {start_char, end_char}
  var runStart = 0;
  while (runStart < sLen) {
    if (frozenAssign[runStart] >= 0) {
      var runPiece = frozenAssign[runStart];
      var runEnd = runStart + 1;
      while (runEnd < sLen && frozenAssign[runEnd] === runPiece) runEnd++;
      // Check if any char in this run has multiple pieces (jamo split)
      var allPieces = [runPiece];
      var seenPiece = {};
      seenPiece[runPiece] = true;
      for (var rci = runStart; rci < runEnd; rci++) {
        var rcPieces = surfaceCharPieces[rci];
        for (var rcj = 0; rcj < rcPieces.length; rcj++) {
          if (!seenPiece[rcPieces[rcj]]) {
            seenPiece[rcPieces[rcj]] = true;
            allPieces.push(rcPieces[rcj]);
          }
        }
      }
      allPieces.sort(function (a, b) {
        return a - b;
      });
      frozenSlices.push({
        start_char: runStart,
        end_char: runEnd,
        piece_idx: allPieces[0],
        piece_idxs: allPieces
      });
      runStart = runEnd;
    } else {
      var gapEnd = runStart + 1;
      while (gapEnd < sLen && frozenAssign[gapEnd] < 0) gapEnd++;
      gapRegions.push({
        start_char: runStart,
        end_char: gapEnd
      });
      runStart = gapEnd;
    }
  }

  // --- Step 5: assign unmatched pieces to gap regions ---
  // Unmatched pieces get placed into the gap region nearest their
  // expected position (between their neighboring frozen pieces).
  var unmatchedPieces = [];
  for (var up = 0; up < pieceTexts.length; up++) {
    if (!pieceFrozen[up]) unmatchedPieces.push(up);
  }

  // For each unmatched piece, find the gap it belongs in based on
  // its ordinal position among pieces.
  // Strategy: an unmatched piece between frozen piece A and frozen
  // piece B belongs in the gap between A's range and B's range.
  var gapAssignments = []; // parallel to gapRegions: array of piece indexes
  for (var ga = 0; ga < gapRegions.length; ga++) gapAssignments.push([]);
  for (var ui = 0; ui < unmatchedPieces.length; ui++) {
    var uPiece = unmatchedPieces[ui];
    // Find the frozen piece just before and just after this one
    var prevFrozen = -1,
      nextFrozen = -1;
    for (var pb = uPiece - 1; pb >= 0; pb--) {
      if (pieceFrozen[pb]) {
        prevFrozen = pb;
        break;
      }
    }
    for (var nb = uPiece + 1; nb < pieceTexts.length; nb++) {
      if (pieceFrozen[nb]) {
        nextFrozen = nb;
        break;
      }
    }

    // Find the gap region between prevFrozen's end and nextFrozen's start
    var bestGap = -1;
    var targetCharPos = 0;
    if (prevFrozen >= 0 && nextFrozen >= 0) {
      targetCharPos = pieceMaxChar[prevFrozen] + 1;
    } else if (prevFrozen >= 0) {
      targetCharPos = pieceMaxChar[prevFrozen] + 1;
    } else if (nextFrozen >= 0) {
      targetCharPos = pieceMinChar[nextFrozen] - 1;
    } else {
      targetCharPos = Math.floor(sLen / 2);
    }
    var bestDist = Infinity;
    for (var gj = 0; gj < gapRegions.length; gj++) {
      var gMid = (gapRegions[gj].start_char + gapRegions[gj].end_char) / 2;
      var d = Math.abs(gMid - targetCharPos);
      if (d < bestDist) {
        bestDist = d;
        bestGap = gj;
      }
    }
    if (bestGap >= 0) {
      gapAssignments[bestGap].push(uPiece);
    } else if (frozenSlices.length) {
      // No gap regions available — attach to nearest frozen slice
      var nearestFrozen = 0;
      var nearestFDist = Infinity;
      for (var nf = 0; nf < frozenSlices.length; nf++) {
        var fMid = (frozenSlices[nf].start_char + frozenSlices[nf].end_char) / 2;
        var fd = Math.abs(fMid - targetCharPos);
        if (fd < nearestFDist) {
          nearestFDist = fd;
          nearestFrozen = nf;
        }
      }
      // Mark for inclusion when building final slices
      if (!frozenSlices[nearestFrozen]._extra_pieces) frozenSlices[nearestFrozen]._extra_pieces = [];
      frozenSlices[nearestFrozen]._extra_pieces.push(uPiece);
    }
  }

  // --- Build final slices ---
  // Merge frozen slices and gap slices in surface order
  var finalSlices = [];

  // Convert frozen slices
  for (var fs = 0; fs < frozenSlices.length; fs++) {
    var fSlice = frozenSlices[fs];
    var fStart = 0;
    for (var co = 0; co < fSlice.start_char; co++) fStart += surfaceChars[co].length;
    var fEnd = fStart;
    for (var ce = fSlice.start_char; ce < fSlice.end_char; ce++) fEnd += surfaceChars[ce].length;
    // Use all piece indexes (includes jamo-spanning pieces for Korean)
    var fFillIds = [];
    var pIdxs = fSlice.piece_idxs || [fSlice.piece_idx];
    for (var pi = 0; pi < pIdxs.length; pi++) {
      fFillIds.push(alignableIndexes[pIdxs[pi]]);
    }
    if (fSlice._extra_pieces) {
      for (var ep = 0; ep < fSlice._extra_pieces.length; ep++) {
        fFillIds.push(alignableIndexes[fSlice._extra_pieces[ep]]);
      }
    }
    finalSlices.push({
      start: fStart,
      end: fEnd,
      fill_indexes: fFillIds,
      _char_start: fSlice.start_char,
      _char_end: fSlice.end_char
    });
  }

  // Convert gap slices (each gap gets all its assigned unmatched pieces)
  for (var gs = 0; gs < gapRegions.length; gs++) {
    if (!gapAssignments[gs].length) continue;
    var gRegion = gapRegions[gs];
    var gStart = 0;
    for (var go = 0; go < gRegion.start_char; go++) gStart += surfaceChars[go].length;
    var gEnd = gStart;
    for (var ge = gRegion.start_char; ge < gRegion.end_char; ge++) gEnd += surfaceChars[ge].length;
    var gIds = [];
    for (var gp = 0; gp < gapAssignments[gs].length; gp++) {
      gIds.push(alignableIndexes[gapAssignments[gs][gp]]);
    }
    finalSlices.push({
      start: gStart,
      end: gEnd,
      fill_indexes: gIds,
      _char_start: gRegion.start_char,
      _char_end: gRegion.end_char
    });
  }

  // Sort by surface position
  finalSlices.sort(function (a, b) {
    if (a.start !== b.start) return a.start - b.start;
    return a.end - b.end;
  });

  // Absorb any uncovered byte ranges into their nearest neighbour slice.
  // The NW aligner can leave gaps at the head, tail, or interior of the
  // surface when a piece only partially matches (e.g. "añc" matches "a"
  // in "aṁ", leaving "ṁ" as a gap region with no unmatched piece).
  // Without this pass such characters become bare text nodes whose hover
  // falls through to the parent token and shows all entries at once.
  if (finalSlices.length) {
    // Leading gap: extend first slice back to byte 0
    if (finalSlices[0].start > 0) {
      finalSlices[0].start = 0;
    }
    // Trailing gap: extend last slice to end of surface
    var surfaceByteLen = surfaceText.length;
    if (finalSlices[finalSlices.length - 1].end < surfaceByteLen) {
      finalSlices[finalSlices.length - 1].end = surfaceByteLen;
    }
    // Interior gaps: if slice[i].end < slice[i+1].start, split the gap
    // at the midpoint and give the left half to slice[i] and the right
    // half to slice[i+1].  Using the midpoint keeps display proportions
    // reasonable; any split point is better than a bare text node.
    for (var ig = 0; ig < finalSlices.length - 1; ig++) {
      var igEnd = finalSlices[ig].end;
      var igNextStart = finalSlices[ig + 1].start;
      if (igNextStart > igEnd) {
        var igMid = Math.ceil((igEnd + igNextStart) / 2);
        finalSlices[ig].end = igMid;
        finalSlices[ig + 1].start = igMid;
      }
    }
  }

  // Clean up temp fields
  for (var cl = 0; cl < finalSlices.length; cl++) {
    delete finalSlices[cl]._char_start;
    delete finalSlices[cl]._char_end;
  }

  // Attach orphan fills (fills without text that weren't placed)
  _attachOrphanFills(finalSlices, rows.length);
  return finalSlices;
}

// Attach fills that don't appear in any slice to the nearest slice
export function _attachOrphanFills(slices, totalRows) {
  if (!slices.length) return;
  var present = Object.create(null);
  for (var si = 0; si < slices.length; si++) {
    var ids = slices[si].fill_indexes;
    for (var sj = 0; sj < ids.length; sj++) present[ids[sj]] = true;
  }
  for (var ri = 0; ri < totalRows; ri++) {
    if (present[ri]) continue;
    var bestSlice = 0;
    var bestDist = Infinity;
    for (var si2 = 0; si2 < slices.length; si2++) {
      var fIds = slices[si2].fill_indexes;
      for (var fj = 0; fj < fIds.length; fj++) {
        var d = Math.abs(fIds[fj] - ri);
        if (d < bestDist) {
          bestDist = d;
          bestSlice = si2;
        }
      }
    }
    slices[bestSlice].fill_indexes.push(ri);
  }
  for (var fi = 0; fi < slices.length; fi++) {
    slices[fi].fill_indexes.sort(function (a, b) {
      return a - b;
    });
  }
}
export function deriveFillPieceXposHints(fills, lemma, xpos) {
  void lemma;
  void xpos;
  var out = [];
  for (var i = 0; i < (fills || []).length; i++) {
    var row = fills[i];
    if (row && typeof row === 'object') out.push(Object.assign({}, row));
    else out.push(row);
  }
  return out;
}
export function buildLiveLookupFillPayload(
  surfaceText,
  fill,
  lemmaText,
  uposText,
  xposText,
  preferredSenseFilterXpos,
  engine,
  resolvedVia,
  mwtParts,
  includeDebugTrace
) {
  var tokenSurface = String(surfaceText || '');
  var partList = Array.isArray(mwtParts) ? mwtParts : [];
  var fillRows = deriveFillPieceXposHints((fill && fill.fills) || [], lemmaText, xposText);
  var fillMode = String((fill && fill.mode) || 'greedy');

  // MWT child results carry authoritative child-local offset metadata on the
  // fill rows. Preserve that exact path here so main lookup rendering and
  // DP-only single-token refreshes rebuild the same slices.
  var isMwtChildFill = fillMode === 'mwt_child' || fillMode === 'mwt_lemma_promoted';
  if (isMwtChildFill) {
    fillRows = explodeMwtChildGreedyRows(tokenSurface, fillRows, getCurrentLanguage());
  }
  var rawFills = prepareFillEntries(
    fillRows,
    engine,
    uposText,
    preferredSenseFilterXpos,
    fillMode,
    includeDebugTrace
  );
  if (partList.length > 1) {
    applyMwtUiPosShading(rawFills, partList, tokenSurface);
  }
  annotateLiveLemmaLinkedFills(rawFills, resolvedVia);
  var fillSurfaceSlices;
  if (isMwtChildFill) {
    fillSurfaceSlices = buildMwtFillSurfaceSlicesFromOffsets(rawFills);
  } else {
    fillSurfaceSlices = buildMwtSurfaceSlicesFromParts(tokenSurface, rawFills, partList);
    if (!fillSurfaceSlices.length) {
      fillSurfaceSlices = buildFillSurfaceSlices(tokenSurface, rawFills, getCurrentLanguage());
    }
  }
  return {
    rawFills: rawFills,
    fillMode: fillMode,
    fillSurfaceSlices: Array.isArray(fillSurfaceSlices) ? fillSurfaceSlices : [],
    isMwtChildFill: isMwtChildFill
  };
}
