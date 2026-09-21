import { alignmentInputsState } from './alignment-inputs.state.mjs';
import { getCurrentLanguage } from './core.mjs';
import { coreState } from './core.state.mjs';
import {
  buildDebugEntryRefs,
  entryDebugIdentity,
  resultMatchCount,
  toDebugLineNo
} from './result-merging.mjs';
export function buildDebugLemmaHintPreview(engine, preparedFills, lemmaHints) {
  void engine;
  void preparedFills;
  var out = [];
  var hintList = Array.isArray(lemmaHints) ? lemmaHints : [];
  for (var i = 0; i < hintList.length; i++) {
    var hint = hintList[i];
    if (hint && typeof hint === 'object' && !Array.isArray(hint)) {
      var cloned = {};
      for (var key in hint) {
        if (Object.prototype.hasOwnProperty.call(hint, key)) cloned[key] = hint[key];
      }
      out.push(cloned);
      continue;
    }
    var text = String(hint || '').trim();
    if (!text) continue;
    out.push({
      text: text
    });
  }
  return out;
}
export function annotateLiveLemmaLinkedFills(fills, resolvedVia) {
  var rows = Array.isArray(fills) ? fills : [];
  var path = String(resolvedVia || '')
    .trim()
    .toLowerCase();
  var wholeLemmaPath = path === 'lemma' || path === 'lemma_override';
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    if (!row || typeof row !== 'object') continue;
    var linked = !!(row._lemma_promoted || row.lemma_promoted || row._lemma_override || row.lemma_override);
    if (!linked && wholeLemmaPath && String(row.source || '').toUpperCase() !== 'UNKNOWN') {
      linked = true;
    }
    row.resolution_linked_to_lemma = linked;
    row.resolution_source = linked
      ? path === 'lemma_override' || row._lemma_override || row.lemma_override
        ? 'lemma_override'
        : wholeLemmaPath && !(row._lemma_promoted || row.lemma_promoted)
          ? 'lemma'
          : 'lemma_promoted'
      : 'surface';
  }
  return rows;
}
export function cloneResolutionRouteSteps(rawSteps) {
  var src = Array.isArray(rawSteps) ? rawSteps : [];
  var out = [];
  for (var i = 0; i < src.length; i++) {
    var step = src[i] || {};
    if (typeof step === 'string') {
      var text = String(step || '').trim();
      if (text)
        out.push({
          code: '',
          text: text,
          detail: ''
        });
      continue;
    }
    var cloned = {
      code: String(step.code || '').trim(),
      text: String(step.text || '').trim(),
      detail: String(step.detail || '').trim()
    };
    if (!cloned.text) continue;
    out.push(cloned);
  }
  return out;
}
export function buildResolutionRouteStep(code, text, detail) {
  return {
    code: String(code || '').trim(),
    text: String(text || '').trim(),
    detail: String(detail || '').trim()
  };
}
export function buildResolutionMeta(
  category,
  routeCode,
  routeSteps,
  resolvedVia,
  fillMode,
  lemmaOracleUsed,
  lemmaOracleOutcome,
  extra
) {
  var out = {
    category: String(category || '')
      .trim()
      .toLowerCase(),
    route_code: String(routeCode || '')
      .trim()
      .toLowerCase(),
    route_steps: cloneResolutionRouteSteps(routeSteps),
    resolved_via: String(resolvedVia || '')
      .trim()
      .toLowerCase(),
    fill_mode: String(fillMode || '')
      .trim()
      .toLowerCase(),
    lemma_oracle_used: !!lemmaOracleUsed,
    lemma_oracle_outcome: String(lemmaOracleOutcome || '')
      .trim()
      .toLowerCase()
  };
  var extras = extra && typeof extra === 'object' ? extra : null;
  if (extras) {
    for (var key in extras) {
      if (!Object.prototype.hasOwnProperty.call(extras, key)) continue;
      out[key] = extras[key];
    }
  }
  return out;
}
export function summarizeActualResolutionFills(fills) {
  var rows = Array.isArray(fills) ? fills : [];
  var knownFillCount = 0;
  var unknownFillCount = 0;
  var lemmaLinkedFillCount = 0;
  var lemmaLinkedFillIndexes = [];
  var lemmaLinkedDistinctKeys = Object.create(null);
  var lemmaLinkedDistinctCount = 0;
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    if (String(row.source || '').toUpperCase() === 'UNKNOWN') {
      unknownFillCount += 1;
    } else {
      knownFillCount += 1;
    }
    if (!row.resolution_linked_to_lemma) continue;
    lemmaLinkedFillCount += 1;
    lemmaLinkedFillIndexes.push(i);
    var lemmaKey = String(
      row._lemma_override || row._lemma_promoted || row.lemma_form || row.morph_base || ''
    ).trim();
    if (lemmaKey && !lemmaLinkedDistinctKeys[lemmaKey]) {
      lemmaLinkedDistinctKeys[lemmaKey] = true;
      lemmaLinkedDistinctCount += 1;
    }
  }
  return {
    total_piece_count: rows.length,
    known_piece_count: knownFillCount,
    unknown_piece_count: unknownFillCount,
    lemma_linked_piece_count: lemmaLinkedFillCount,
    lemma_linked_fill_indexes: lemmaLinkedFillIndexes,
    lemma_linked_distinct_count: lemmaLinkedDistinctCount
  };
}
export function buildResolutionRouteText(routeSteps) {
  var steps = cloneResolutionRouteSteps(routeSteps);
  if (!steps.length) return '';
  var out = [];
  for (var i = 0; i < steps.length; i++) {
    var step = steps[i] || {};
    var text = String(step.text || '').trim();
    var detail = String(step.detail || '').trim();
    if (!text) continue;
    if (detail) text += ' (' + detail + ')';
    out.push(text);
  }
  return out.join(' -> ');
}
export function buildResolutionFinalText(path, mode, fillSummary, exactLemmaMatchCount) {
  var bits = [];
  var resolvedPath = String(path || '')
    .trim()
    .toLowerCase();
  var fillMode = String(mode || '')
    .trim()
    .toLowerCase();
  var knownCount = parseInt(fillSummary && fillSummary.known_piece_count, 10);
  var unknownCount = parseInt(fillSummary && fillSummary.unknown_piece_count, 10);
  var totalCount = parseInt(fillSummary && fillSummary.total_piece_count, 10);
  var lemmaLinkedCount = parseInt(fillSummary && fillSummary.lemma_linked_piece_count, 10);
  var lemmaExactCount = parseInt(exactLemmaMatchCount, 10);
  if (!isFinite(knownCount) || knownCount < 0) knownCount = 0;
  if (!isFinite(unknownCount) || unknownCount < 0) unknownCount = 0;
  if (!isFinite(totalCount) || totalCount < 0) totalCount = 0;
  if (!isFinite(lemmaLinkedCount) || lemmaLinkedCount < 0) lemmaLinkedCount = 0;
  if (!isFinite(lemmaExactCount) || lemmaExactCount < 0) lemmaExactCount = 0;
  if (resolvedPath) bits.push('via=' + resolvedPath);
  if (fillMode) bits.push('mode=' + fillMode);
  bits.push('pieces=' + String(totalCount));
  bits.push('known=' + String(knownCount));
  if (unknownCount > 0) bits.push('unknown=' + String(unknownCount));
  if (lemmaLinkedCount > 0) bits.push('lemma-linked=' + String(lemmaLinkedCount));
  if (lemmaExactCount > 0) bits.push('lemma-exact=' + String(lemmaExactCount));
  return bits.join(' | ');
}
export function buildLiveResolutionInfo(resolutionMeta, fills, exactLemmaMatchCount) {
  var meta = resolutionMeta && typeof resolutionMeta === 'object' ? resolutionMeta : null;
  var fillSummary = summarizeActualResolutionFills(fills);
  var category = String((meta && meta.category) || '')
    .trim()
    .toLowerCase();
  var resolvedVia = String((meta && meta.resolved_via) || '')
    .trim()
    .toLowerCase();
  var fillMode = String((meta && meta.fill_mode) || '')
    .trim()
    .toLowerCase();
  var lemmaOracleUsed = !!(meta && meta.lemma_oracle_used);
  var lemmaOracleOutcome = String((meta && meta.lemma_oracle_outcome) || '')
    .trim()
    .toLowerCase();
  var lemmaExactCount = parseInt(exactLemmaMatchCount, 10);
  if (!isFinite(lemmaExactCount) || lemmaExactCount < 0) lemmaExactCount = 0;
  var compareKind = '';
  if (
    category === 'exact_lemma_match' ||
    category === 'mwt_exact_partial_lemma_match' ||
    category === 'mwt_exact_lemma_match' ||
    category === 'greedy_lemma_match' ||
    category === 'mwt_lemma_override' ||
    category === 'mwt_lemma_partial_override' ||
    category === 'lemma_override' ||
    category === 'lemma_partial_override' ||
    (category === 'mwt_exact_parts' && lemmaExactCount > 0)
  ) {
    compareKind = 'surface';
  } else if (lemmaOracleUsed) {
    compareKind = 'lemma';
  }
  var routeText = buildResolutionRouteText(meta && meta.route_steps);
  var finalText = buildResolutionFinalText(resolvedVia, fillMode, fillSummary, lemmaExactCount);
  if (!category && fillSummary.known_piece_count <= 0) {
    finalText = '';
  }
  return {
    category: category,
    label: category ? alignmentInputsState.ACTUAL_RESOLUTION_LABELS[category] || '' : '',
    route_code: String((meta && meta.route_code) || '')
      .trim()
      .toLowerCase(),
    route_steps: cloneResolutionRouteSteps(meta && meta.route_steps),
    route_text: routeText,
    final_text: finalText,
    compare_kind: compareKind,
    resolved_via: resolvedVia,
    fill_mode: fillMode,
    lemma_oracle_used: lemmaOracleUsed,
    lemma_oracle_outcome: lemmaOracleOutcome,
    exact_surface_match:
      category === 'exact_match' ||
      category === 'exact_lemma_match' ||
      category === 'mwt_exact_partial_lemma_match' ||
      category === 'mwt_exact_lemma_match',
    exact_matches_lemma:
      category === 'exact_lemma_match' ||
      category === 'mwt_exact_lemma_match' ||
      (category === 'mwt_exact_parts' && lemmaExactCount > 0),
    exact_lemma_match_count: lemmaExactCount,
    has_lemma_linked_fill: fillSummary.lemma_linked_piece_count > 0,
    lemma_linked_fill_indexes: fillSummary.lemma_linked_fill_indexes.slice(),
    lemma_linked_distinct_count: fillSummary.lemma_linked_distinct_count,
    final_result: {
      total_piece_count: fillSummary.total_piece_count,
      known_piece_count: fillSummary.known_piece_count,
      unknown_piece_count: fillSummary.unknown_piece_count,
      lemma_linked_piece_count: fillSummary.lemma_linked_piece_count
    }
  };
}
export function buildDebugFillPreview(fill) {
  var out = [];
  var rows = fill && Array.isArray(fill.fills) ? fill.fills : [];
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var dbgTrace = row && typeof row._debug_trace === 'object' ? row._debug_trace : {};
    out.push({
      text: String(row.text || ''),
      head: String(row.head || ''),
      source: String(row.source || ''),
      pos: String(row.pos || ''),
      surface_start: parseInt(row._surface_start, 10) || 0,
      surface_end: parseInt(row._surface_end, 10) || 0,
      xpos_hint: String(row._xpos_hint || ''),
      effective_upos: String(dbgTrace.effective_upos || dbgTrace.upos || ''),
      effective_xpos: String(dbgTrace.effective_xpos || dbgTrace.xpos || ''),
      lemma_upos_hint: String(row._lemma_upos_hint || ''),
      lemma_xpos_hint: String(row._lemma_xpos_hint || ''),
      lemma_promoted: String(row._lemma_promoted || ''),
      entry_refs: buildDebugEntryRefs(Array.isArray(row.entries) ? row.entries : [])
    });
  }
  return out;
}
export function summarizeLookupResultForDebug(label, result, lookupEvents) {
  var events = Array.isArray(lookupEvents) ? lookupEvents.slice() : [];
  if (!result || typeof result !== 'object') {
    if (!events.length) return null;
    return {
      label: String(label || ''),
      mode: '',
      has_known: false,
      has_unknown: false,
      match_count: 0,
      entry_refs: [],
      fills: [],
      dp_debug: null,
      exact_events: events
    };
  }
  var fill = result.fill || {};
  return {
    label: String(label || ''),
    mode: String(fill.mode || ''),
    has_known: !!fill.has_known,
    has_unknown: !!fill.has_unknown,
    match_count: resultMatchCount(result),
    entry_refs: buildDebugEntryRefs(Array.isArray(result.entries) ? result.entries : []),
    fills: buildDebugFillPreview(fill),
    dp_debug: fill.dp_debug && typeof fill.dp_debug === 'object' ? fill.dp_debug : null,
    exact_events: events
  };
}
export function isKoreanLanguageCode(langValue) {
  var lang = String(langValue || '')
    .trim()
    .toLowerCase();
  return lang === 'ko' || lang === 'korean' || lang.indexOf('ko-') === 0;
}

// Decompose a Korean Hangul syllable (AC00–D7A3) into its constituent jamo.
// Returns an array of 2 or 3 jamo characters (lead, vowel, optional tail).
// Non-Hangul syllable characters are returned as-is in a single-element array.
// Compatibility jamo (3130–318F) are also returned as-is.
export // includes 0 for no trailing consonant

function decomposeHangulSyllable(ch) {
  var code = ch.codePointAt(0);
  if (code < alignmentInputsState.HANGUL_BASE || code > alignmentInputsState.HANGUL_END) return [ch];
  var syllableIndex = code - alignmentInputsState.HANGUL_BASE;
  var leadIdx = Math.floor(
    syllableIndex / (alignmentInputsState.NUM_VOWELS * alignmentInputsState.NUM_TAILS)
  );
  var vowelIdx = Math.floor(
    (syllableIndex % (alignmentInputsState.NUM_VOWELS * alignmentInputsState.NUM_TAILS)) /
      alignmentInputsState.NUM_TAILS
  );
  var tailIdx = syllableIndex % alignmentInputsState.NUM_TAILS;
  var result = [
    String.fromCodePoint(alignmentInputsState.LEAD_BASE + leadIdx),
    String.fromCodePoint(alignmentInputsState.VOWEL_BASE + vowelIdx)
  ];
  if (tailIdx > 0) result.push(String.fromCodePoint(alignmentInputsState.TAIL_BASE + tailIdx));
  return result;
}

// Map compatibility jamo (U+3131–U+3163) to Hangul Jamo leading consonants
// (U+1100–U+1112) for NW comparison. This lets Trankit outputs like bare ㄴ
// (U+3134) match decomposed syllable jamo ᄂ (U+1102) / ᆫ (U+11AB).
// We normalize everything to leading consonant form for comparison only.
export // Normalize a jamo character to a canonical form for NW comparison.
// Maps compatibility jamo and trailing jamo to leading/vowel jamo equivalents.
function normalizeJamoForComparison(ch) {
  var code = ch.codePointAt(0);
  if (alignmentInputsState.COMPAT_CONSONANT_TO_LEAD[code])
    return String.fromCodePoint(alignmentInputsState.COMPAT_CONSONANT_TO_LEAD[code]);
  if (alignmentInputsState.TAIL_TO_LEAD[code])
    return String.fromCodePoint(alignmentInputsState.TAIL_TO_LEAD[code]);
  if (alignmentInputsState.COMPAT_VOWEL_TO_JAMO[code])
    return String.fromCodePoint(alignmentInputsState.COMPAT_VOWEL_TO_JAMO[code]);
  return ch;
}
export function isVietnameseLanguageCode(langValue) {
  var lang = String(langValue || '')
    .trim()
    .toLowerCase();
  return lang === 'vi' || lang === 'vietnamese' || lang.indexOf('vi-') === 0;
}
export function languageUsesXposFilter(langValue) {
  return isKoreanLanguageCode(langValue);
}
export function normalizeFilterXposTag(rawTag, langValue) {
  if (isKoreanLanguageCode(langValue)) return normalizeXposTag(rawTag);
  return String(rawTag || '').trim();
}
export function isKoreanEngine(engine) {
  var lang = String((engine && engine._lang_code) || '')
    .trim()
    .toLowerCase();
  return isKoreanLanguageCode(lang);
}
export function getKoreanDisplayOnlyEntries(engine, surface) {
  if (!isKoreanEngine(engine)) return [];
  var query = String(surface || '').trim();
  if (!query) return [];
  var fn = null;
  if (engine && typeof engine.lookup_display_only === 'function') fn = engine.lookup_display_only;
  else if (engine && typeof engine.lookupDisplayOnly === 'function') fn = engine.lookupDisplayOnly;
  if (!fn) return [];
  var out = fn.call(engine, query);
  if (!Array.isArray(out) || !out.length) return [];

  // Ensure display-only form-derived rows (notably eumhun) keep the full
  // form reading in UI while search still keys by stem/final character.
  var viaFn = null;
  if (engine && typeof engine.lookup_via_forms === 'function') viaFn = engine.lookup_via_forms;
  else if (engine && typeof engine.lookupViaForms === 'function') viaFn = engine.lookupViaForms;
  if (!viaFn) return out;
  var via = viaFn.call(engine, query);
  if (!Array.isArray(via) || !via.length) return out;
  var readingByKey = Object.create(null);
  for (var vi = 0; vi < via.length; vi++) {
    var vEntry = via[vi] || {};
    var vReading = String(vEntry.reading || '').trim();
    if (!vReading) continue;
    var vId = entryDebugIdentity(vEntry);
    var vLine = toDebugLineNo(vEntry.__line_no);
    var vKey = String(vLine || '') + '\t' + vId;
    if (!readingByKey[vKey] || vReading.length > String(readingByKey[vKey] || '').length) {
      readingByKey[vKey] = vReading;
    }
  }
  var enriched = [];
  for (var oi = 0; oi < out.length; oi++) {
    var src = out[oi] || {};
    var reading = String(src.reading || '').trim();
    var id = entryDebugIdentity(src);
    var line = toDebugLineNo(src.__line_no);
    var key = String(line || '') + '\t' + id;
    var mapped = String(readingByKey[key] || '').trim();
    if (mapped && mapped !== reading) {
      var clone = {};
      for (var k in src) {
        if (Object.prototype.hasOwnProperty.call(src, k)) clone[k] = src[k];
      }
      clone.reading = mapped;
      enriched.push(clone);
    } else {
      enriched.push(src);
    }
  }
  return enriched;
}
export function mergeUniqueEntries(baseEntries, extraEntries) {
  var out = [];
  var seen = Object.create(null);
  function pushOne(entry) {
    if (!entry || typeof entry !== 'object') return;
    var id = entryDebugIdentity(entry);
    var lineNo = toDebugLineNo(entry.__line_no);
    var key = String(lineNo || '') + '\t' + id;
    if (seen[key]) return;
    seen[key] = true;
    out.push(entry);
  }
  var base = Array.isArray(baseEntries) ? baseEntries : [];
  for (var i = 0; i < base.length; i++) pushOne(base[i]);
  var extra = Array.isArray(extraEntries) ? extraEntries : [];
  for (var j = 0; j < extra.length; j++) pushOne(extra[j]);
  return out;
}
export function splitCompoundTags(raw) {
  var text = String(raw || '').trim();
  if (!text) return [];
  return text
    .split(coreState.COMPOUND_LEMMA_SPLIT_RE)
    .map(function (part) {
      return part.trim();
    })
    .filter(Boolean);
}
export function normalizeCompoundParts(parts, normalizer) {
  var out = [];
  for (var i = 0; i < (parts || []).length; i++) {
    var raw = parts[i];
    var value = normalizer ? normalizer(raw) : String(raw || '').trim();
    if (!value) continue;
    out.push(value);
  }
  return out;
}
export function uniqueNormalizedTags(parts, normalizer) {
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < (parts || []).length; i++) {
    var raw = parts[i];
    var value = normalizer ? normalizer(raw) : String(raw || '').trim();
    if (!value || seen[value]) continue;
    seen[value] = true;
    out.push(value);
  }
  return out;
}
export function mergeCompoundTags(rawA, rawB, normalizer) {
  var combined = [];
  var partsA = splitCompoundTags(rawA);
  var partsB = splitCompoundTags(rawB);
  for (var i = 0; i < partsA.length; i++) combined.push(partsA[i]);
  for (var j = 0; j < partsB.length; j++) combined.push(partsB[j]);
  return uniqueNormalizedTags(combined, normalizer).join('+');
}
export function normalizeXposTag(rawTag) {
  var tag = String(rawTag || '')
    .trim()
    .toLowerCase();
  if (!tag) return '';
  // Handle parser artifacts like "ecs." / "jxc,".
  return tag.replace(/^[^a-z0-9_]+|[^a-z0-9_]+$/g, '');
}
export function collectKoreanLemmaSpecificXposTags(lemmaHintObjects, lemmaOverrideParts, langOverride) {
  var activeLang = String(
    (langOverride && langOverride._lang_code) || langOverride || getCurrentLanguage() || ''
  )
    .trim()
    .toLowerCase();
  if (!isKoreanLanguageCode(activeLang)) return [];
  var out = [];
  var seen = Object.create(null);
  function pushRaw(raw) {
    var parts = splitCompoundTags(raw);
    if (!parts.length) {
      var single = String(raw || '').trim();
      if (single) parts = [single];
    }
    for (var i = 0; i < parts.length; i++) {
      var tag = normalizeXposTag(parts[i]);
      if (!tag || seen[tag]) continue;
      seen[tag] = true;
      out.push(tag);
    }
  }
  var overrideList = Array.isArray(lemmaOverrideParts) ? lemmaOverrideParts : [];
  for (var oi = 0; oi < overrideList.length; oi++) {
    var part = overrideList[oi] || {};
    pushRaw(part.xpos);
  }
  var hintList = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
  for (var hi = 0; hi < hintList.length; hi++) {
    var hint = hintList[hi] || {};
    pushRaw(hint.xpos);
  }
  return out;
}
export function choosePreferredSenseFilterXpos(
  tokenXpos,
  lemmaHintObjects,
  lemmaOverrideParts,
  langOverride
) {
  var activeLang = String(
    (langOverride && langOverride._lang_code) || langOverride || getCurrentLanguage() || ''
  )
    .trim()
    .toLowerCase();
  if (!isKoreanLanguageCode(activeLang)) return String(tokenXpos || '');
  var lemmaTags = collectKoreanLemmaSpecificXposTags(lemmaHintObjects, lemmaOverrideParts, activeLang);
  if (lemmaTags.length) return lemmaTags.join('+');
  return String(tokenXpos || '');
}
export function formatUnicodeCodePoint(ch) {
  var text = String(ch || '');
  if (!text) return '';
  var code = text.codePointAt(0).toString(16).toUpperCase();
  while (code.length < 4) code = '0' + code;
  return 'U+' + code;
}
export function toUnicodeCodePointList(text) {
  var src = Array.from(String(text || ''));
  var out = [];
  for (var i = 0; i < src.length; i++) out.push(formatUnicodeCodePoint(src[i]));
  return out;
}
export function decomposeTextToAlignmentUnits(text, langCode) {
  var src = Array.from(String(text || ''));
  var korean = isKoreanLanguageCode(langCode);
  var out = [];
  for (var i = 0; i < src.length; i++) {
    var ch = src[i];
    if (korean) {
      var jamo = decomposeHangulSyllable(ch);
      for (var ji = 0; ji < jamo.length; ji++) {
        out.push(normalizeJamoForComparison(jamo[ji]));
      }
    } else {
      var unitText = ch;
      var unitChars = Array.from(String(unitText || ''));
      if (!unitChars.length) unitChars = [ch];
      for (var ui = 0; ui < unitChars.length; ui++) out.push(unitChars[ui]);
    }
  }
  return out;
}
export function buildSurfaceCodepointMap(text, langCode) {
  var src = Array.from(String(text || ''));
  var chars = [];
  var units = [];
  var unitToChar = [];
  var codeUnitOffset = 0;
  for (var i = 0; i < src.length; i++) {
    var ch = src[i];
    var unitChars = decomposeTextToAlignmentUnits(ch, langCode);
    if (!unitChars.length) unitChars = [ch];
    var startUnit = units.length;
    for (var ui = 0; ui < unitChars.length; ui++) {
      units.push(unitChars[ui]);
      unitToChar.push(i);
    }
    var offsetStart = codeUnitOffset;
    codeUnitOffset += ch.length;
    chars.push({
      index: i,
      offset_start: offsetStart,
      offset_end: codeUnitOffset,
      char: ch,
      unit_start: startUnit,
      unit_end: units.length,
      unit_text: unitChars.join(''),
      unit_codepoints: unitChars.map(formatUnicodeCodePoint)
    });
  }
  return {
    chars: chars,
    units: units,
    unit_to_char: unitToChar,
    text_length: String(text || '').length
  };
}

// Test whether a codepoint is a Unicode combining mark (Mn/Mc/Me) or a
// zero-width character that cannot stand alone in a hover span.
export function _isZeroWidthOrCombining(ch) {
  var code = ch.codePointAt(0);
  if (code === 0x200b || code === 0x200c || code === 0x200d || code === 0xfeff) return true; // ZWS, ZWNJ, ZWJ, BOM
  // Combining Diacritical Marks (U+0300–U+036F)
  if (code >= 0x0300 && code <= 0x036f) return true;
  // Combining Diacritical Marks Extended (U+1AB0–U+1AFF)
  if (code >= 0x1ab0 && code <= 0x1aff) return true;
  // Combining Diacritical Marks Supplement (U+1DC0–U+1DFF)
  if (code >= 0x1dc0 && code <= 0x1dff) return true;
  // Combining Diacritical Marks for Symbols (U+20D0–U+20FF)
  if (code >= 0x20d0 && code <= 0x20ff) return true;
  // Combining Half Marks (U+FE20–U+FE2F)
  if (code >= 0xfe20 && code <= 0xfe2f) return true;
  // Arabic combining marks (U+0610–U+061A, U+064B–U+065F, U+0670)
  if (code >= 0x0610 && code <= 0x061a) return true;
  if (code >= 0x064b && code <= 0x065f) return true;
  if (code === 0x0670) return true;
  // Hebrew points/marks (U+0591–U+05BD, U+05BF, U+05C1–U+05C2, U+05C4–U+05C5, U+05C7)
  if (code >= 0x0591 && code <= 0x05bd) return true;
  if (
    code === 0x05bf ||
    code === 0x05c1 ||
    code === 0x05c2 ||
    code === 0x05c4 ||
    code === 0x05c5 ||
    code === 0x05c7
  )
    return true;
  // Devanagari/Hindi combining marks (U+0900–U+0903, U+093A–U+094F, U+0951–U+0957, U+0962–U+0963)
  if (code >= 0x0900 && code <= 0x0903) return true;
  if (code >= 0x093a && code <= 0x094f) return true;
  if (code >= 0x0951 && code <= 0x0957) return true;
  if (code >= 0x0962 && code <= 0x0963) return true;
  // Thai combining marks (U+0E31, U+0E34–U+0E3A, U+0E47–U+0E4E)
  if (code === 0x0e31) return true;
  if (code >= 0x0e34 && code <= 0x0e3a) return true;
  if (code >= 0x0e47 && code <= 0x0e4e) return true;
  return false;
}

// Compute codepoint-unit overlap score between a lemma part and a set of
// surface characters. Returns the count of shared decomposed units (bag
// intersection). Used for fuzzy assignment of unplaced parts to gap chars.
export function initializeAlignmentInputs() {
  alignmentInputsState.ACTUAL_RESOLUTION_LABELS = {
    exact_match: 'Exact Match',
    exact_lemma_match: 'Exact Lemma Match',
    mwt_exact_parts: 'MWT Exact Match',
    mwt_exact_partial_lemma_match: 'MWT Partial Lemma Match',
    mwt_exact_lemma_match: 'MWT Exact Lemma Match',
    mwt_lemma_override: 'MWT Lemma Override',
    mwt_lemma_partial_override: 'Partial MWT Lemma Override',
    lemma_override: 'Lemma Override',
    lemma_partial_override: 'Partial Lemma Override',
    greedy_match: 'Greedy Segmentation',
    lemma_promotion: 'Greedy Segmentation + Lemma Scoring'
  };
  alignmentInputsState.HANGUL_BASE = 0xac00;
  alignmentInputsState.HANGUL_END = 0xd7a3;
  alignmentInputsState.LEAD_BASE = 0x1100; // Hangul Jamo leading consonants
  alignmentInputsState.VOWEL_BASE = 0x1161; // Hangul Jamo vowels
  alignmentInputsState.TAIL_BASE = 0x11a7; // Hangul Jamo trailing consonants (0 = no tail)
  alignmentInputsState.NUM_VOWELS = 21;
  alignmentInputsState.NUM_TAILS = 28;
  alignmentInputsState.COMPAT_CONSONANT_TO_LEAD = {};
  (function () {
    // compatibility jamo consonants → leading jamo codepoints
    var map = [
      [0x3131, 0x1100],
      // ㄱ → ᄀ
      [0x3132, 0x1101],
      // ㄲ → ᄁ
      [0x3134, 0x1102],
      // ㄴ → ᄂ
      [0x3137, 0x1103],
      // ㄷ → ᄃ
      [0x3138, 0x1104],
      // ㄸ → ᄄ
      [0x3139, 0x1105],
      // ㄹ → ᄅ
      [0x3141, 0x1106],
      // ㅁ → ᄆ
      [0x3142, 0x1107],
      // ㅂ → ᄇ
      [0x3143, 0x1108],
      // ㅃ → ᄈ
      [0x3145, 0x1109],
      // ㅅ → ᄉ
      [0x3146, 0x110a],
      // ㅆ → ᄊ
      [0x3147, 0x110b],
      // ㅇ → ᄋ
      [0x3148, 0x110c],
      // ㅈ → ᄌ
      [0x3149, 0x110d],
      // ㅉ → ᄍ
      [0x314a, 0x110e],
      // ㅊ → ᄎ
      [0x314b, 0x110f],
      // ㅋ → ᄏ
      [0x314c, 0x1110],
      // ㅌ → ᄐ
      [0x314d, 0x1111],
      // ㅍ → ᄑ
      [0x314e, 0x1112] // ㅎ → ᄒ
    ];
    for (var i = 0; i < map.length; i++) {
      alignmentInputsState.COMPAT_CONSONANT_TO_LEAD[map[i][0]] = map[i][1];
    }
  })();

  // Also map trailing jamo (U+11A8–U+11C2) to leading consonant equivalents
  alignmentInputsState.TAIL_TO_LEAD = {};
  (function () {
    var map = [
      [0x11a8, 0x1100],
      // ᆨ → ᄀ
      [0x11a9, 0x1101],
      // ᆩ → ᄁ
      [0x11ab, 0x1102],
      // ᆫ → ᄂ
      [0x11ae, 0x1103],
      // ᆮ → ᄃ
      [0x11af, 0x1105],
      // ᆯ → ᄅ
      [0x11b7, 0x1106],
      // ᆷ → ᄆ
      [0x11b8, 0x1107],
      // ᆸ → ᄇ
      [0x11ba, 0x1109],
      // ᆺ → ᄉ
      [0x11bb, 0x110a],
      // ᆻ → ᄊ
      [0x11bc, 0x110b],
      // ᆼ → ᄋ
      [0x11bd, 0x110c],
      // ᆽ → ᄌ
      [0x11be, 0x110e],
      // ᆾ → ᄎ
      [0x11bf, 0x110f],
      // ᆿ → ᄏ
      [0x11c0, 0x1110],
      // ᇀ → ᄐ
      [0x11c1, 0x1111],
      // ᇁ → ᄑ
      [0x11c2, 0x1112] // ᇂ → ᄒ
    ];
    for (var i = 0; i < map.length; i++) {
      alignmentInputsState.TAIL_TO_LEAD[map[i][0]] = map[i][1];
    }
  })();

  // Map compatibility vowels (U+314F–U+3163) to Hangul Jamo vowels (U+1161–U+1175)
  alignmentInputsState.COMPAT_VOWEL_TO_JAMO = {};
  (function () {
    // 21 vowels: ㅏ(314F)→ᅡ(1161), ㅐ(3150)→ᅢ(1162), ... ㅣ(3163)→ᅵ(1175)
    for (var v = 0; v < 21; v++) {
      alignmentInputsState.COMPAT_VOWEL_TO_JAMO[0x314f + v] = 0x1161 + v;
    }
  })();
  return true;
}
