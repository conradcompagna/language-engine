import { buildDebugFillPreview, isKoreanLanguageCode } from './alignment-inputs.mjs';
import { getFillPieceSurfaceText } from './child-fill-slices.mjs';
import {
  getCurrentLanguage,
  getLemmaHintCandidateTexts,
  normalizeLookupKey,
  normalizeVisibleComparisonText
} from './core.mjs';
import {
  chooseEntry,
  cloneLemmaHintObject,
  getEntryDisplayHeadword,
  getEntryDisplayReading,
  getEntryMatchKind,
  getStableRuntimeEntryId,
  mergeEntryMorphInfo,
  normalizeCanonicalEntryRuntime,
  pushUniqueBundledEntry
} from './entry-adapters.mjs';
import { applyFillRepresentativeEntry } from './lookup-payloads.mjs';
import { buildDebugEntryRefs } from './result-merging.mjs';
import { buildGenericSurfacePartAlignment } from './surface-alignment.mjs';
import {
  buildSinglePassSurfaceLookup,
  collectFillEntries,
  findLemmaHintMatchForEntry
} from './surface-lookup.mjs';
export function _ensureEntryHydrated(entry) {
  return normalizeCanonicalEntryRuntime(entry);
}

// DEBUG MAP: creates the intermediate dict_fill piece object.
// Provenance is NOT attached here initially; source propagation happens later.
export function buildFillPieceFromEntry(surfaceText, entry, allEntries) {
  _ensureEntryHydrated(entry);
  var surface = String(surfaceText || '');
  var displayHead = getEntryDisplayHeadword(entry) || surface;
  var lemmaHead = String((entry && entry.lemma_headword) || '').trim();
  var displayReading = getEntryDisplayReading(entry);
  var fill = {
    text: surface,
    head: displayHead || surface,
    headword: displayHead || surface,
    roman: displayReading,
    reading: displayReading,
    senses: (entry && entry.senses) || [],
    pos: (entry && entry.pos) || '',
    pos_raw: (entry && entry.pos_raw) || (entry && entry.pos) || '',
    source: (entry && (entry._source || entry.source)) || 'KAIKKI',
    entries: Array.isArray(allEntries) ? allEntries.slice() : []
  };
  var keys = [
    'entry_id',
    '_source',
    '_glosses_raw',
    '_forms_raw',
    '_forms_json',
    '_commentary',
    '_lemma',
    'etymology',
    'senses_full',
    'ipa_variants',
    'ref_key',
    'match_kind',
    'runtime_entry_id',
    'display_headword',
    'lemma_headword',
    'display_reading',
    'entry_reading',
    'is_alternate_match',
    'grammar',
    'morph_info',
    'morph_base',
    'forms',
    'forms_meta',
    'spelling_header'
  ];
  for (var i = 0; i < keys.length; i++) {
    var k = keys[i];
    var v = entry ? entry[k] : null;
    if (v) fill[k] = v;
  }
  applyFillRepresentativeEntry(fill, entry, true);
  if (surface) {
    fill.surface_form = surface;
  }
  if (lemmaHead) {
    fill.lemma_form = lemmaHead;
    if (!fill.morph_base && getEntryMatchKind(entry) === 'form') fill.morph_base = lemmaHead;
  }
  return fill;
}
export function cloneMwtChildPieceRow(row) {
  var src = row && typeof row === 'object' ? row : {};
  var out = {};
  for (var key in src) {
    if (!Object.prototype.hasOwnProperty.call(src, key)) continue;
    var val = src[key];
    if (Array.isArray(val)) out[key] = val.slice();
    else out[key] = val;
  }
  if (Array.isArray(src.entries)) out.entries = src.entries.slice();
  if (Array.isArray(src.morph_info)) out.morph_info = src.morph_info.slice();
  return out;
}
export function buildFillResult(text, entries, mode) {
  var best = entries[0];
  var fillEntry = buildFillPieceFromEntry(text, best, entries);
  return {
    entries: entries.slice(),
    fill: {
      mode: mode,
      fills: [fillEntry],
      has_known: true,
      has_unknown: false
    }
  };
}
export function buildKoreanCompoundLemmaSurfaceAnchorFill(surfaceText) {
  var surface = String(surfaceText || '').trim();
  if (!surface) return null;
  return {
    mode: 'ko_compound_lemma_anchor',
    fills: [
      {
        text: surface,
        head: surface,
        headword: surface,
        surface_form: surface,
        roman: '',
        reading: '',
        senses: [],
        pos: '',
        pos_raw: '',
        source: 'COMPOSITE',
        entries: [],
        _korean_compound_lemma_anchor: true
      }
    ],
    has_known: true,
    has_unknown: false,
    has_lemma_promotion: false,
    has_korean_compound_lemma_anchor: true
  };
}
export function _charDiff(a, b) {
  // Count characters in a not present in b (simple bag difference)
  var longer = a.length > b.length ? a : b;
  var shorter = a.length > b.length ? b : a;
  return (
    longer.length -
    shorter.length +
    (function () {
      var diff = 0;
      for (var i = 0; i < shorter.length; i++) {
        if (longer.indexOf(shorter[i]) === -1) diff++;
      }
      return diff;
    })()
  );
}
export function _pickClosestToSurface(entries, surfaceText) {
  // Returns the entry whose display_headword is the closest match to surfaceText.
  // Exact match wins; otherwise least character difference; ties go to first.
  var surface = String(surfaceText || '').trim();
  var best = entries[0];
  if (!surface) return best;
  var bestHead = getEntryDisplayHeadword(best);
  if (bestHead === surface) return best;
  var bestDiff = _charDiff(bestHead, surface);
  for (var i = 1; i < entries.length; i++) {
    var head = getEntryDisplayHeadword(entries[i]);
    if (head === surface) return entries[i];
    var diff = _charDiff(head, surface);
    if (diff < bestDiff) {
      best = entries[i];
      bestDiff = diff;
      bestHead = head;
    }
  }
  return best;
}
export function dedupeEntriesByIdentity(entries, surfaceText) {
  var out = [];
  var grouped = Object.create(null);
  var order = [];
  var list = Array.isArray(entries) ? entries : [];
  for (var i = 0; i < list.length; i++) {
    var entry = list[i];
    if (!entry || typeof entry !== 'object') continue;
    var runtimeId = getStableRuntimeEntryId(entry);
    var key = runtimeId || 'anon:' + i;
    if (!grouped[key]) {
      grouped[key] = [];
      order.push(key);
    }
    grouped[key].push(entry);
  }
  for (var oi = 0; oi < order.length; oi++) {
    var group = grouped[order[oi]] || [];
    if (group.length === 1) {
      out.push(group[0]);
      continue;
    }
    // Hard-dedup by entry id: pick the representative closest to the surface
    // token, then merge all other morph_info into it.
    var winner = _pickClosestToSurface(group, surfaceText);
    for (var gi = 0; gi < group.length; gi++) {
      if (group[gi] !== winner) mergeEntryMorphInfo(winner, group[gi]);
    }
    out.push(winner);
  }
  return out;
}
export function collectRecoveredLemmaHintIndexes(fill, lemmaHintObjects, engine) {
  var rows = fill && Array.isArray(fill.fills) ? fill.fills : [];
  var hints = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
  var matched = [];
  for (var hi = 0; hi < hints.length; hi++) matched.push(false);
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    if (String(row.source || '').toUpperCase() === 'UNKNOWN') continue;
    var rowEntries = Array.isArray(row.entries) ? row.entries : [];
    for (var hi2 = 0; hi2 < hints.length; hi2++) {
      if (matched[hi2]) continue;
      var hint = hints[hi2];
      for (var ei = 0; ei < rowEntries.length; ei++) {
        if (findLemmaHintMatchForEntry(rowEntries[ei], [hint], engine)) {
          matched[hi2] = true;
          break;
        }
      }
    }
  }
  var out = [];
  for (var mi = 0; mi < matched.length; mi++) {
    if (matched[mi]) out.push(mi);
  }
  return out;
}
export function lookupExactEntriesForText(queryText, engine) {
  var query = String(queryText || '').trim();
  if (!query || !engine || typeof engine.lookup_all !== 'function') return [];
  var entries = engine.lookup_all(query) || [];
  return Array.isArray(entries) ? entries.slice() : [];
}
export function lookupExactHeadwordEntriesForText(queryText, engine) {
  var query = String(queryText || '').trim();
  if (!query || !engine) return [];
  var out = [];
  var seen = Object.create(null);
  var keys =
    engine && typeof engine._lookup_keys === 'function'
      ? engine._lookup_keys(query)
      : [normalizeLookupKey(engine, query)];
  if (engine._compact_mode && engine._hw_index) {
    for (var ki = 0; ki < keys.length; ki++) {
      var key = String(keys[ki] || '').trim();
      if (!key) continue;
      var hwHits = engine._hw_index[key];
      if (!hwHits) continue;
      for (var hi = 0; hi < hwHits.length; hi++) {
        var alias = hwHits[hi][0];
        var eid = hwHits[hi][1];
        var storageKind =
          engine._db_alias_map && (engine._db_alias_map[alias] === 'custom' || alias === 'customdb')
            ? 'custom'
            : 'sqlite';
        pushUniqueBundledEntry(out, seen, {
          _winner_ref: true,
          storage_kind: storageKind,
          db_alias: alias,
          entry_row_id: eid,
          match_kind: 'headword',
          match_key: key,
          headword: query
        });
      }
    }
    return out;
  }
  if (!engine._by_word) return [];
  for (var bi = 0; bi < keys.length; bi++) {
    var bucketKey = String(keys[bi] || '').trim();
    if (!bucketKey) continue;
    var bucket = engine._by_word[bucketKey];
    if (!bucket) continue;
    for (var ei = 0; ei < bucket.length; ei++) {
      pushUniqueBundledEntry(out, seen, bucket[ei]);
    }
  }
  return out;
}
export function collectWholeTokenExactLemmaEntries(surfaceText, lemmaHintObjects, engine) {
  var surface = String(surfaceText || '').trim();
  var hints = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
  if (!surface || !hints.length || !engine || typeof engine.lookup_all !== 'function') return [];
  var lang = String((engine && engine._lang_code) || getCurrentLanguage() || '')
    .trim()
    .toLowerCase();
  if (isKoreanLanguageCode(lang) && hints.length > 1) return [];
  if (hints.length !== 1) return [];
  var out = [];
  var surfaceKey = normalizeVisibleComparisonText(surface);
  var hintTexts = getLemmaHintCandidateTexts(hints[0], engine);
  for (var i = 0; i < hintTexts.length; i++) {
    var hintText = String(hintTexts[i] || '').trim();
    if (!hintText) continue;
    if (surfaceKey && normalizeVisibleComparisonText(hintText) === surfaceKey) continue;
    var entries = lookupExactHeadwordEntriesForText(hintText, engine);
    for (var ei = 0; ei < entries.length; ei++) out.push(entries[ei]);
  }
  return dedupeEntriesByIdentity(out, surface);
}
export function buildLemmaHintLookupPart(rawHint, engine) {
  var hint = cloneLemmaHintObject(rawHint);
  var rawHintText = String(hint.text || hint.lemma || '').trim();
  var hintTexts = getLemmaHintCandidateTexts(hint, engine);
  var matchedText = '';
  var matchedEntries = [];
  for (var hti = 0; hti < hintTexts.length; hti++) {
    var candidateText = hintTexts[hti];
    if (!candidateText) continue;
    var candidateEntries = lookupExactEntriesForText(candidateText, engine);
    if (!candidateEntries.length) continue;
    matchedText = candidateText;
    matchedEntries = candidateEntries;
    break;
  }
  var partText = matchedText || rawHintText;
  if (!partText) return null;
  return {
    text: partText,
    source_text: rawHintText || partText,
    surface_text: String(hint.surface_text || ''),
    surface_slice: Array.isArray(hint.surface_slice) ? hint.surface_slice.slice(0, 2) : null,
    upos: String(hint.upos || '').trim(),
    xpos: String(hint.xpos || '').trim(),
    entries: matchedEntries,
    exact: !!(matchedText && matchedEntries.length),
    hint_object: hint
  };
}
export function shouldBypassKoreanCompoundLemmaRealignment(surfaceText, lemmaHintObjects, engine, options) {
  var lookupOpts = options || {};
  if (lookupOpts.korean_compound_child_lookup) return false;
  if (lookupOpts.mwt_single_child) return false;
  if (Array.isArray(lookupOpts.mwt_parts) && lookupOpts.mwt_parts.length > 1) return false;
  var lang = String((engine && engine._lang_code) || getCurrentLanguage() || '')
    .trim()
    .toLowerCase();
  if (!isKoreanLanguageCode(lang)) return false;
  var surface = String(surfaceText || '').trim();
  var hints = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
  if (!surface || hints.length <= 1) return false;
  var parts = [];
  for (var i = 0; i < hints.length; i++) {
    var text = String((hints[i] && (hints[i].text || hints[i].lemma)) || '').trim();
    if (text) parts.push(text);
  }
  if (parts.length <= 1) return false;
  return normalizeVisibleComparisonText(parts.join('')) !== normalizeVisibleComparisonText(surface);
}
export function buildKoreanCompoundLemmaChildLookupPayloads(lemmaHintObjects, engine, includeDebugTrace) {
  var hints = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
  var out = [];
  if (!engine || hints.length <= 1) return out;
  for (var i = 0; i < hints.length; i++) {
    var hint = hints[i] || {};
    var childText = String(hint.text || hint.lemma || '').trim();
    if (!childText) continue;
    var childUpos = String(hint.upos || '').trim();
    var childXpos = String(hint.xpos || '').trim();
    var childLookup = buildSinglePassSurfaceLookup(
      childText,
      childText,
      engine,
      childUpos,
      childXpos,
      includeDebugTrace,
      {
        skipWholeSurfaceExact: false,
        mwt_parts: [],
        korean_compound_child_lookup: true
      }
    );
    out.push({
      text: childText,
      source_text: String(hint.source_text || hint.text || hint.lemma || '').trim(),
      part_index: i,
      upos: childUpos,
      xpos: childXpos,
      lookup: childLookup
    });
  }
  return out.length > 1 ? out : [];
}
export function buildExplicitLemmaHintAlignmentState(surfaceText, parts, includeDebugTrace) {
  var surface = String(surfaceText || '').trim();
  var hintParts = Array.isArray(parts) ? parts : [];
  if (!surface || !hintParts.length) return null;
  var groups = [];
  var boundaries = [];
  var cursor = 0;
  var usedExplicitSlices = false;
  // If any part carries a Trankit surface_slice, ALL parts must carry one —
  // offset-based alignment is the single source of truth and we never mix
  // it with cursor/substring matching.
  var anyHasSlice = false;
  for (var ai = 0; ai < hintParts.length; ai++) {
    var ap = hintParts[ai] || {};
    if (Array.isArray(ap.surface_slice) && ap.surface_slice.length >= 2) {
      anyHasSlice = true;
      break;
    }
  }
  for (var i = 0; i < hintParts.length; i++) {
    var part = hintParts[i] || {};
    var partSurface = String(part.surface_text || '');
    var rawSlice = Array.isArray(part.surface_slice) ? part.surface_slice : null;
    var nextCursor = cursor + partSurface.length;
    if (rawSlice && rawSlice.length >= 2) {
      var sliceStart = parseInt(rawSlice[0], 10);
      var sliceEnd = parseInt(rawSlice[1], 10);
      if (!isFinite(sliceStart) || !isFinite(sliceEnd)) return null;
      if (sliceStart < 0 || sliceEnd < sliceStart || sliceEnd > surface.length) return null;
      if (sliceStart < cursor) return null;
      cursor = sliceStart;
      nextCursor = sliceEnd;
      usedExplicitSlices = true;
    } else if (anyHasSlice) {
      // MWT/slice mode: every part must have an authoritative slice. Missing
      // one is a hard error — we refuse to fall back to substring matching.
      return null;
    } else {
      if (!partSurface) return null;
      if (surface.slice(cursor, cursor + partSurface.length) !== partSurface) return null;
      nextCursor = cursor + partSurface.length;
    }
    groups.push({
      start: cursor,
      end: nextCursor,
      part_ids: [i]
    });
    cursor = nextCursor;
    if (i < hintParts.length - 1) boundaries.push(cursor);
  }
  if (!usedExplicitSlices && cursor !== surface.length) return null;
  if (usedExplicitSlices && groups.length && groups[groups.length - 1].end !== surface.length) return null;
  var runtimeDebug = null;
  if (includeDebugTrace) {
    runtimeDebug = {
      surface_text: surface,
      lang_code: String(getCurrentLanguage() || '').toLowerCase(),
      normalized_parts: hintParts.map(function (part) {
        return String(part.text || '');
      }),
      explicit_surface_parts: hintParts.map(function (part) {
        return {
          index: parseInt(part.index, 10) || 0,
          surface_text: String(part.surface_text || ''),
          surface_slice: Array.isArray(part.surface_slice) ? part.surface_slice.slice(0, 2) : null,
          text: String(part.text || ''),
          source_text: String(part.source_text || '')
        };
      }),
      match_basis: usedExplicitSlices ? 'mwt_parts_slice' : 'mwt_parts',
      boundaries: boundaries.slice(),
      groups: groups.map(function (group) {
        return {
          start: parseInt(group.start, 10) || 0,
          end: parseInt(group.end, 10) || 0,
          part_ids: Array.isArray(group.part_ids) ? group.part_ids.slice() : []
        };
      })
    };
  }
  return {
    alignment_groups: groups,
    runtime_alignment_debug: runtimeDebug
  };
}
export function buildLemmaHintAlignmentState(surfaceText, lemmaHintObjects, engine, includeDebugTrace) {
  var surface = String(surfaceText || '').trim();
  var hints = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
  if (!surface || !hints.length || !engine) return null;
  var parts = [];
  var exactPartCount = 0;
  for (var i = 0; i < hints.length; i++) {
    var part = buildLemmaHintLookupPart(hints[i], engine);
    if (!part) return null;
    part.index = i;
    if (part.exact) exactPartCount += 1;
    parts.push(part);
  }
  if (!parts.length) return null;
  var explicitState = buildExplicitLemmaHintAlignmentState(surface, parts, includeDebugTrace);
  if (
    explicitState &&
    Array.isArray(explicitState.alignment_groups) &&
    explicitState.alignment_groups.length
  ) {
    return {
      surface: surface,
      parts: parts,
      alignment_groups: explicitState.alignment_groups,
      runtime_alignment_debug: explicitState.runtime_alignment_debug,
      exact_part_count: exactPartCount,
      total_part_count: parts.length
    };
  }
  var alignment = buildGenericSurfacePartAlignment(
    surface,
    parts.map(function (part) {
      return part.text;
    }),
    {
      langCode: String(getCurrentLanguage() || '').toLowerCase(),
      debugTrace: !!includeDebugTrace
    }
  );
  if (!alignment || !Array.isArray(alignment.groups) || !alignment.groups.length) return null;
  var alignmentGroups = alignment.groups.map(function (group) {
    return {
      start: parseInt(group && group.start, 10) || 0,
      end: parseInt(group && group.end, 10) || 0,
      part_ids: Array.isArray(group && group.part_ids) ? group.part_ids.slice() : []
    };
  });
  var presentPartIds = Object.create(null);
  for (var agi = 0; agi < alignmentGroups.length; agi++) {
    var presentIds = alignmentGroups[agi].part_ids;
    for (var api = 0; api < presentIds.length; api++) {
      var presentId = parseInt(presentIds[api], 10);
      if (!isFinite(presentId) || presentId < 0 || presentId >= parts.length) continue;
      presentPartIds[presentId] = true;
    }
  }
  for (var mpi = 0; mpi < parts.length; mpi++) {
    if (presentPartIds[mpi]) continue;
    var bestGroupIndex = -1;
    var bestDistance = Infinity;
    for (var bgi = 0; bgi < alignmentGroups.length; bgi++) {
      var candidateIds = alignmentGroups[bgi].part_ids;
      if (!candidateIds.length) continue;
      for (var cpi = 0; cpi < candidateIds.length; cpi++) {
        var candidateId = parseInt(candidateIds[cpi], 10);
        if (!isFinite(candidateId) || candidateId < 0) continue;
        var distance = Math.abs(candidateId - mpi);
        if (distance < bestDistance) {
          bestDistance = distance;
          bestGroupIndex = bgi;
        }
      }
    }
    if (bestGroupIndex >= 0) {
      alignmentGroups[bestGroupIndex].part_ids.push(mpi);
      alignmentGroups[bestGroupIndex].part_ids.sort(function (a, b) {
        return a - b;
      });
      presentPartIds[mpi] = true;
    }
  }
  return {
    surface: surface,
    parts: parts,
    alignment_groups: alignmentGroups,
    runtime_alignment_debug:
      alignment &&
      alignment._debug_runtime_alignment &&
      typeof alignment._debug_runtime_alignment === 'object'
        ? alignment._debug_runtime_alignment
        : null,
    exact_part_count: exactPartCount,
    total_part_count: parts.length
  };
}
export function buildDirectLemmaHintMappingState(surfaceText, lemmaHintObjects, engine, includeDebugTrace) {
  var surface = String(surfaceText || '').trim();
  var hints = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
  if (!surface || !hints.length || !engine) return null;
  var parts = [];
  var groups = [];
  var boundaries = [];
  var cursor = 0;
  var exactPartCount = 0;
  var usedExplicitSlices = true;
  for (var i = 0; i < hints.length; i++) {
    var srcHint = hints[i];
    // Every MWT hint carries a surface_slice. Null hints are no longer
    // allowed here — buildLemmaHintData keeps a hint for every child.
    if (!srcHint) return null;
    var part = buildLemmaHintLookupPart(srcHint, engine);
    if (!part) {
      // Child had no dictionary hits under the lemma — synthesize a minimal
      // part record so its Trankit offsets are preserved and the gap gets
      // filled by per-child greedy downstream.
      part = {
        text: String(srcHint.surface_text || srcHint.text || ''),
        source_text: String(srcHint.text || srcHint.surface_text || ''),
        surface_text: String(srcHint.surface_text || ''),
        surface_slice: Array.isArray(srcHint.surface_slice) ? srcHint.surface_slice.slice(0, 2) : null,
        upos: String(srcHint.upos || ''),
        xpos: String(srcHint.xpos || ''),
        entries: [],
        exact: false,
        hint_object: srcHint
      };
    }
    var partSurface = String(part.surface_text || '');
    if (!partSurface) return null;
    part.index = i;
    if (part.exact) exactPartCount += 1;
    var rawSlice = Array.isArray(part.surface_slice) ? part.surface_slice : null;
    // surface_slice is mandatory. No cursor/length fallback permitted.
    if (!rawSlice || rawSlice.length < 2) return null;
    var sliceStart = parseInt(rawSlice[0], 10);
    var sliceEnd = parseInt(rawSlice[1], 10);
    if (!isFinite(sliceStart) || !isFinite(sliceEnd)) return null;
    if (sliceStart < 0 || sliceEnd < sliceStart || sliceEnd > surface.length) return null;
    if (sliceStart < cursor) return null;
    cursor = sliceStart;
    var nextCursor = sliceEnd;
    parts.push(part);
    groups.push({
      start: cursor,
      end: nextCursor,
      part_ids: [i]
    });
    cursor = nextCursor;
    if (i < hints.length - 1) boundaries.push(cursor);
  }
  if (groups.length && groups[groups.length - 1].end !== surface.length) return null;
  var forcedCoverage = false;
  var runtimeDebug = null;
  if (includeDebugTrace) {
    runtimeDebug = {
      surface_text: surface,
      lang_code: String(getCurrentLanguage() || '').toLowerCase(),
      normalized_parts: parts.map(function (part) {
        return String(part.text || '');
      }),
      explicit_surface_parts: parts.map(function (part) {
        return {
          index: parseInt(part.index, 10) || 0,
          surface_text: String(part.surface_text || ''),
          surface_slice: Array.isArray(part.surface_slice) ? part.surface_slice.slice(0, 2) : null,
          text: String(part.text || ''),
          source_text: String(part.source_text || '')
        };
      }),
      match_basis: usedExplicitSlices ? 'mwt_parts_slice_direct' : 'mwt_parts_direct',
      forced_surface_coverage: !!forcedCoverage,
      boundaries: boundaries.slice(),
      groups: groups.map(function (group) {
        return {
          start: parseInt(group.start, 10) || 0,
          end: parseInt(group.end, 10) || 0,
          part_ids: Array.isArray(group.part_ids) ? group.part_ids.slice() : []
        };
      })
    };
  }
  return {
    surface: surface,
    parts: parts,
    alignment_groups: groups,
    runtime_alignment_debug: runtimeDebug,
    exact_part_count: exactPartCount,
    total_part_count: parts.length
  };
}
export function cloneFillRowsWithSurfaceOffsets(fills, expectedText, startOffset) {
  var rows = Array.isArray(fills) ? fills : [];
  var surfaceText = String(expectedText || '');
  var offsetBase = parseInt(startOffset, 10) || 0;
  var cursor = 0;
  var out = [];
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var pieceText = getFillPieceSurfaceText(row);
    if (!pieceText) return null;
    if (surfaceText.slice(cursor, cursor + pieceText.length) !== pieceText) return null;
    var clone = {};
    for (var key in row) {
      if (Object.prototype.hasOwnProperty.call(row, key)) clone[key] = row[key];
    }
    clone._surface_start = offsetBase + cursor;
    cursor += pieceText.length;
    clone._surface_end = offsetBase + cursor;
    out.push(clone);
  }
  if (cursor !== surfaceText.length) return null;
  return out;
}

// REMOVED: buildExactMwtPartLookupResult and buildMwtPartwiseFallbackLookupResult
// These were a bespoke MWT segmenter that duplicated logic from the main
// segmenter (buildSinglePassSurfaceLookup) and introduced cursor/substring
// heuristics that broke sandhi tokens. MWT children are now each fed
// directly into buildSinglePassSurfaceLookup (with mwt_parts:[]) and the
// resulting fills are rebased onto the parent surface via Trankit surface_slice.
export function buildLemmaOverrideResultFromState(state, engine, upos, xpos, includeDebugTrace) {
  void xpos;
  if (!state || !engine) return null;
  var fillRows = [];
  var gapSegments = [];
  for (var gi = 0; gi < state.alignment_groups.length; gi++) {
    var group = state.alignment_groups[gi] || {};
    var start = parseInt(group.start, 10);
    var end = parseInt(group.end, 10);
    if (!isFinite(start) || start < 0) start = 0;
    if (!isFinite(end) || end < start) end = start;
    var surfaceSlice = state.surface.slice(start, end);
    var rawIds = Array.isArray(group.part_ids) ? group.part_ids : [];
    var partIds = [];
    var seenPartIds = Object.create(null);
    for (var pi = 0; pi < rawIds.length; pi++) {
      var pid = parseInt(rawIds[pi], 10);
      if (!isFinite(pid) || pid < 0 || pid >= state.parts.length || seenPartIds[pid]) continue;
      seenPartIds[pid] = true;
      partIds.push(pid);
    }
    if (!partIds.length) continue;
    var exactPartIds = [];
    var gapHintObjects = [];
    for (var pj = 0; pj < partIds.length; pj++) {
      var part = state.parts[partIds[pj]];
      if (!part) continue;
      if (part.exact && Array.isArray(part.entries) && part.entries.length) {
        exactPartIds.push(partIds[pj]);
      } else {
        gapHintObjects.push(
          cloneLemmaHintObject(
            part.hint_object || {
              text: part.text,
              upos: part.upos,
              xpos: part.xpos
            }
          )
        );
      }
    }
    if (exactPartIds.length) {
      for (var pk = 0; pk < exactPartIds.length; pk++) {
        var partId = exactPartIds[pk];
        var exactPart = state.parts[partId];
        if (!exactPart) continue;
        var partEntries = Array.isArray(exactPart.entries) ? exactPart.entries.slice() : [];
        if (!partEntries.length) continue;
        var best = chooseEntry(surfaceSlice || exactPart.text, partEntries, engine) || partEntries[0];
        var fillRow = buildFillPieceFromEntry(surfaceSlice, best, partEntries);
        if (exactPart.text) fillRow.head = exactPart.text;
        fillRow._lemma_override = exactPart.text;
        fillRow._lemma_override_part_count = 1;
        fillRow._lemma_part_index = exactPart.index;
        fillRow._surface_start = start;
        fillRow._surface_end = end;
        if (exactPart.upos) fillRow._lemma_upos_hint = exactPart.upos;
        if (exactPart.xpos) fillRow._lemma_xpos_hint = exactPart.xpos;
        fillRows.push(fillRow);
      }
    } else if (surfaceSlice) {
      gapSegments.push({
        start: start,
        end: end,
        text: surfaceSlice,
        part_ids: partIds.slice(),
        hint_objects: gapHintObjects.slice(),
        part_index: partIds.length === 1 ? partIds[0] : null
      });
    }
  }
  if (!fillRows.length && !gapSegments.length) return null;
  var gapDebug = [];
  for (var gsi = 0; gsi < gapSegments.length; gsi++) {
    var gap = gapSegments[gsi] || {};
    var gapText = String(gap.text || '');
    if (!gapText) continue;
    var singleGapHint =
      Array.isArray(gap.hint_objects) && gap.hint_objects.length === 1 ? gap.hint_objects[0] || null : null;
    var gapFillOpts = {
      allowExact: false,
      upos: singleGapHint && singleGapHint.upos ? String(singleGapHint.upos || '') : upos || ''
    };
    if (includeDebugTrace) gapFillOpts.debug = true;
    if (Array.isArray(gap.hint_objects) && gap.hint_objects.length)
      gapFillOpts.lemma_hints = gap.hint_objects.slice();
    var gapFill = engine.fill_token(gapText, gapFillOpts);
    var gapRowsSrc =
      gapFill && Array.isArray(gapFill.fills) && gapFill.fills.length
        ? gapFill.fills
        : [
            {
              text: gapText,
              head: gapText,
              roman: '',
              senses: [],
              pos: '',
              source: 'UNKNOWN'
            }
          ];
    var offsetRows = cloneFillRowsWithSurfaceOffsets(gapRowsSrc, gapText, gap.start);
    if (!offsetRows || !offsetRows.length) return null;
    var gapPartIndex = parseInt(gap.part_index, 10);
    if (!isFinite(gapPartIndex)) gapPartIndex = null;
    for (var gri = 0; gri < offsetRows.length; gri++) {
      var offsetRow = offsetRows[gri] || {};
      if (gapPartIndex !== null) offsetRow._lemma_part_index = gapPartIndex;
      if (singleGapHint) {
        if (singleGapHint.upos) offsetRow._lemma_upos_hint = String(singleGapHint.upos || '');
        if (singleGapHint.xpos) offsetRow._lemma_xpos_hint = String(singleGapHint.xpos || '');
      }
      fillRows.push(offsetRow);
    }
    if (includeDebugTrace) {
      gapDebug.push({
        start: parseInt(gap.start, 10) || 0,
        end: parseInt(gap.end, 10) || 0,
        text: gapText,
        part_ids: Array.isArray(gap.part_ids) ? gap.part_ids.slice() : [],
        mode: String((gapFill && gapFill.mode) || 'greedy'),
        has_known: !!(gapFill && gapFill.has_known),
        has_unknown: !!(gapFill && gapFill.has_unknown),
        fills: buildDebugFillPreview({
          fills: gapRowsSrc
        }),
        dp_debug:
          gapFill && gapFill.dp_debug && typeof gapFill.dp_debug === 'object' ? gapFill.dp_debug : null
      });
    }
  }
  fillRows.sort(function (a, b) {
    var aStart = parseInt(a && a._surface_start, 10);
    var bStart = parseInt(b && b._surface_start, 10);
    if (!isFinite(aStart)) aStart = 0;
    if (!isFinite(bStart)) bStart = 0;
    if (aStart !== bStart) return aStart - bStart;
    var aEnd = parseInt(a && a._surface_end, 10);
    var bEnd = parseInt(b && b._surface_end, 10);
    if (!isFinite(aEnd)) aEnd = aStart;
    if (!isFinite(bEnd)) bEnd = bStart;
    if (aEnd !== bEnd) return aEnd - bEnd;
    var aPart = parseInt(a && a._lemma_part_index, 10);
    var bPart = parseInt(b && b._lemma_part_index, 10);
    if (!isFinite(aPart)) aPart = 1e9;
    if (!isFinite(bPart)) bPart = 1e9;
    return aPart - bPart;
  });
  var isPartial = state.exact_part_count < state.total_part_count;
  var fillMode = isPartial ? 'lemma_partial_greedy' : 'lemma_override';
  var mergedFill = {
    mode: fillMode,
    fills: fillRows,
    has_known: false,
    has_unknown: false,
    has_lemma_override: true,
    has_lemma_promotion: false
  };
  for (var fi = 0; fi < fillRows.length; fi++) {
    var fillRow0 = fillRows[fi] || {};
    if (String(fillRow0.source || '').toUpperCase() === 'UNKNOWN') mergedFill.has_unknown = true;
    else mergedFill.has_known = true;
    if (fillRow0._lemma_promoted) mergedFill.has_lemma_promotion = true;
  }
  if (gapDebug.length) {
    mergedFill.dp_debug = {
      mode: fillMode,
      exact_part_count: state.exact_part_count,
      total_part_count: state.total_part_count,
      gap_count: gapSegments.length,
      gaps: gapDebug
    };
  }
  var allEntries = collectFillEntries(mergedFill);
  if (!allEntries.length && !mergedFill.has_unknown) return null;
  var result = {
    exact_entries: [],
    fill: mergedFill,
    all_entries: allEntries.slice(),
    preferred_entries: allEntries.slice(),
    dict_head: state.surface,
    resolved_via: isPartial ? 'lemma_partial_override' : 'lemma_override',
    lemma_oracle_used: true,
    lemma_oracle_outcome: isPartial
      ? gapSegments.length
        ? 'lemma_partial_exact_gaps'
        : 'lemma_partial_exact_only'
      : 'lemma_override_exact_parts',
    exact_lemma_match_count: state.exact_part_count,
    lemma_override_parts: state.parts.map(function (part) {
      var out = {
        text: part.text,
        source_text: part.source_text,
        upos: part.upos,
        xpos: part.xpos,
        entry_refs: buildDebugEntryRefs(part.entries || [])
      };
      if (isPartial) out.matched = !!part.exact;
      return out;
    })
  };
  if (isPartial) {
    result.partial_exact_lemma_count = state.exact_part_count;
    result.partial_missing_lemma_count = state.total_part_count - state.exact_part_count;
    result.partial_gap_count = gapSegments.length;
  }
  if (
    includeDebugTrace &&
    state.runtime_alignment_debug &&
    typeof state.runtime_alignment_debug === 'object'
  ) {
    var runtimeAlignmentDebug = {};
    for (var debugKey in state.runtime_alignment_debug) {
      if (!Object.prototype.hasOwnProperty.call(state.runtime_alignment_debug, debugKey)) continue;
      runtimeAlignmentDebug[debugKey] = state.runtime_alignment_debug[debugKey];
    }
    runtimeAlignmentDebug.hint_parts = state.parts.map(function (part) {
      return {
        index: parseInt(part.index, 10) || 0,
        text: String(part.text || ''),
        source_text: String(part.source_text || ''),
        upos: String(part.upos || ''),
        xpos: String(part.xpos || ''),
        exact: !!part.exact
      };
    });
    runtimeAlignmentDebug.selected_groups = state.alignment_groups.map(function (group) {
      return {
        start: parseInt(group && group.start, 10) || 0,
        end: parseInt(group && group.end, 10) || 0,
        part_ids: Array.isArray(group && group.part_ids) ? group.part_ids.slice() : []
      };
    });
    runtimeAlignmentDebug.exact_part_count = parseInt(state.exact_part_count, 10) || 0;
    runtimeAlignmentDebug.total_part_count = parseInt(state.total_part_count, 10) || 0;
    result._debug_runtime_lemma_alignment = runtimeAlignmentDebug;
  }
  return result;
}

// For MWT children the entire child surface is one atomic unit — the lemma
// maps onto [0, surface.length] with no alignment needed. This skips
// buildGenericSurfacePartAlignment (Needleman-Wunsch) entirely.
