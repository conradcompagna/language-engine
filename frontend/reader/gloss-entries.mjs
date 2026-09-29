import { normalizeUdPartIndex } from './dependency-hover.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { documentShellState } from './document-shell.state.mjs';
import {
  findLemmaGlossKeyForPart,
  getCanonicalTokenEntry,
  getCanonicalTokenLemmaInfo,
  getCanonicalTokenSurfaceText,
  getLookupEntryFills,
  getLookupEntryResolution,
  getLookupEntryResolvedVia,
  getOrderedCompoundLemmaTexts,
  getRenderableLlmGlossRows,
  hasExactTokenLookupMatch,
  tokenHasRealMwtParts
} from './entry-editing.mjs';
import { glossEntriesState } from './gloss-entries.state.mjs';
import { getKoreanGlossLemmaParts, isKoreanCurrentLanguageForGloss } from './gloss-requests.mjs';
import { getTokenLiveResolution } from './grammar-popup.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { _filterDictFillForMwtPart, getMwtPartsForSeg } from './mwt-context.mjs';
import { getEntryDisplayHead, getTrimmedDisplayText, hasSameVisibleComparisonText } from './presentation.mjs';
import { isUnknownDictEntry } from './side-panel.mjs';
import { getTokenMapLemmaPartLookup, getTokenMapLemmaPartTexts } from './token-map.mjs';
export function getLlmGlossEntryForSeg(segIdx, options) {
  var idx = Number(segIdx);
  if (!isFinite(idx) || idx < 0) return null;
  var opts = options && typeof options === 'object' ? options : {};
  if (
    !opts.originalOnly &&
    hoverLayoutState.latestLlmGlossOverrides &&
    Object.prototype.hasOwnProperty.call(hoverLayoutState.latestLlmGlossOverrides, String(idx))
  ) {
    var overrideText = String(hoverLayoutState.latestLlmGlossOverrides[String(idx)] || '').trim();
    if (overrideText) {
      return {
        gloss: overrideText,
        _manual_override: true
      };
    }
  }
  if (!Array.isArray(hoverLayoutState.latestLlmGlosses) || idx >= hoverLayoutState.latestLlmGlosses.length)
    return null;
  var entry = hoverLayoutState.latestLlmGlosses[idx];
  return entry && typeof entry === 'object' ? entry : null;
}
export function hasLlmGlossEntryForSeg(segIdx, options) {
  return !!getLlmGlossEntryForSeg(segIdx, options);
}
export function flattenRenderableLlmGlossRows(rows) {
  var list = Array.isArray(rows) ? rows : [];
  var parts = [];
  for (var i = 0; i < list.length; i++) {
    var row = list[i] || {};
    var lemma = String(row.lemma || '').trim();
    var gloss = String(row.gloss || '').trim();
    if (!gloss) continue;
    parts.push(lemma ? lemma + ': ' + gloss : gloss);
  }
  return parts.join(' | ');
}
export function shouldShowLlmGlossUpgradeMessage() {
  return !!(
    dependencyPopupState.displaySettings &&
    dependencyPopupState.displaySettings.llmGloss &&
    hoverLayoutState.latestLlmGlossUpgradeRequired
  );
}
export function buildLlmGlossUpgradeMessageHtml() {
  return '<span class="gp-desc" style="color:#92400e;">Upgrade for LLM glosses</span>';
}
export function getSentenceTabletGlossText(segIdx, surface, entry, udTok, options) {
  var glossEntry = getLlmGlossEntryForSeg(segIdx, options);
  if (!glossEntry) return '';
  try {
    var rows = getRenderableLlmGlossRows(
      glossEntry,
      surface,
      {
        entry: entry || null,
        udTok: udTok || null
      },
      null
    );
    var flat = flattenRenderableLlmGlossRows(rows);
    if (flat) return flat;
  } catch (_e) {}
  return String(glossEntry.gloss || '').trim();
}
export function extractCompoundGlossPartValues(glossEntry, compoundParts) {
  var entry = glossEntry && typeof glossEntry === 'object' ? glossEntry : null;
  var parts = Array.isArray(compoundParts) ? compoundParts : [];
  if (!entry || parts.length < 2) return [];
  var out = [];
  var flatGloss = String(entry.gloss || '').trim();
  if (flatGloss && flatGloss.indexOf(' + ') !== -1) {
    var flatParts = flatGloss.split(' + ');
    if (flatParts.length === parts.length) {
      for (var fi = 0; fi < flatParts.length; fi++) {
        var flatVal = String(flatParts[fi] || '').trim();
        if (!flatVal) continue;
        out.push(flatVal);
      }
      if (out.length) return out;
    }
  }
  if (Array.isArray(entry._compound_part_glosses) && entry._compound_part_glosses.length) {
    for (var ai = 0; ai < entry._compound_part_glosses.length && ai < parts.length; ai++) {
      var arrVal = String(entry._compound_part_glosses[ai] || '').trim();
      if (!arrVal) continue;
      out.push(arrVal);
    }
    if (out.length) return out;
  }
  if (entry.lemma_glosses && typeof entry.lemma_glosses === 'object') {
    for (var li = 0; li < parts.length; li++) {
      var matchKey = findLemmaGlossKeyForPart(entry.lemma_glosses, parts[li]);
      if (!matchKey) continue;
      var mapVal = String(entry.lemma_glosses[matchKey] || '').trim();
      if (!mapVal) continue;
      out.push(mapVal);
    }
    if (out.length) return out;
  }
  if (!flatGloss) return [];
  return [flatGloss];
}
export function buildCompoundLlmGlossEntry(compoundParts, partGlosses) {
  var parts = Array.isArray(compoundParts) ? compoundParts : [];
  var glosses = Array.isArray(partGlosses) ? partGlosses : [];
  var lemmaGlosses = {};
  var combinedParts = [];
  var cleanGlosses = [];
  for (var ci = 0; ci < glosses.length && ci < parts.length; ci++) {
    var glossVal = String(glosses[ci] || '').trim();
    if (!glossVal) continue;
    var label = String(parts[ci] || '').trim();
    if (label) lemmaGlosses[label] = glossVal;
    cleanGlosses.push(glossVal);
    combinedParts.push(glossVal);
  }
  if (!combinedParts.length) return null;
  return {
    gloss: combinedParts.join(' + '),
    lemma_glosses: lemmaGlosses,
    _compound_part_glosses: cleanGlosses,
    _compound_part_labels: parts.slice(0, cleanGlosses.length)
  };
}
export function splitFullGlossForCompoundParts(gloss, compoundParts) {
  var raw = String(gloss || '').trim();
  var parts = Array.isArray(compoundParts) ? compoundParts : [];
  if (!raw || parts.length < 2) return [];
  if (raw.indexOf(' + ') === -1) return [raw];
  var glossParts = raw.split(' + ');
  if (glossParts.length !== parts.length) return [raw];
  var out = [];
  for (var gi = 0; gi < glossParts.length; gi++) {
    var val = String(glossParts[gi] || '').trim();
    if (val) out.push(val);
  }
  return out;
}
export function mergeKoreanCompoundGlossEntry(existingEntry, incomingEntry, fallbackSurface, sourceData) {
  if (!isKoreanCurrentLanguageForGloss() || tokenHasRealMwtParts(sourceData)) return null;
  var data = sourceData && typeof sourceData === 'object' ? sourceData : {};
  var compoundParts = getKoreanGlossLemmaParts(fallbackSurface, data.udTok || null, data.entry || null);
  if (compoundParts.length < 2) return null;
  var existing = existingEntry && typeof existingEntry === 'object' ? existingEntry : null;
  var incoming = incomingEntry && typeof incomingEntry === 'object' ? incomingEntry : null;
  var incomingGloss = String((incoming && incoming.gloss) || '').trim();
  if (!incomingGloss) return existingEntry || incomingEntry || null;
  var collected = [];
  if (existing && Array.isArray(existing._compound_part_glosses)) {
    for (var ei = 0; ei < existing._compound_part_glosses.length && ei < compoundParts.length; ei++) {
      var oldVal = String(existing._compound_part_glosses[ei] || '').trim();
      if (oldVal) collected.push(oldVal);
    }
  } else if (existing && existing.gloss) {
    collected = splitFullGlossForCompoundParts(existing.gloss, compoundParts).slice(0, compoundParts.length);
  }
  var incomingParts = splitFullGlossForCompoundParts(incomingGloss, compoundParts);
  if (incomingParts.length >= compoundParts.length) {
    collected = incomingParts.slice(0, compoundParts.length);
  } else {
    for (var ii = 0; ii < incomingParts.length && collected.length < compoundParts.length; ii++) {
      var newVal = String(incomingParts[ii] || '').trim();
      if (newVal) collected.push(newVal);
    }
  }
  var merged = buildCompoundLlmGlossEntry(compoundParts, collected);
  if (merged) merged._korean_compound_gloss = true;
  return merged;
}
export function mergeLlmGlossEntries(existingEntry, incomingEntry, fallbackSurface, sourceData) {
  var incoming = incomingEntry && typeof incomingEntry === 'object' ? incomingEntry : null;
  if (!incoming) return existingEntry || incomingEntry;
  var incomingGloss = String(incoming.gloss || '').trim();
  if (!incomingGloss) return existingEntry || incomingEntry;
  var koreanMerged = mergeKoreanCompoundGlossEntry(existingEntry, incomingEntry, fallbackSurface, sourceData);
  if (koreanMerged) return koreanMerged;
  var compoundParts = tokenHasRealMwtParts(sourceData)
    ? []
    : getOrderedCompoundLemmaTexts(fallbackSurface, sourceData);
  if (compoundParts.length > 1) {
    var partGlosses = extractCompoundGlossPartValues(existingEntry, compoundParts);
    var incomingParts = extractCompoundGlossPartValues(incomingEntry, compoundParts);
    if (incomingParts.length >= compoundParts.length) {
      partGlosses = incomingParts.slice(0, compoundParts.length);
    } else if (!partGlosses.length) {
      partGlosses = incomingParts.slice(0, compoundParts.length);
    } else {
      for (var ii = 0; ii < incomingParts.length && partGlosses.length < compoundParts.length; ii++) {
        partGlosses.push(incomingParts[ii]);
      }
    }
    var trimmedGlosses = partGlosses.slice(0, compoundParts.length);
    var combinedEntry = buildCompoundLlmGlossEntry(compoundParts, trimmedGlosses);
    if (combinedEntry) return combinedEntry;
  }
  var existingGloss = String((existingEntry && existingEntry.gloss) || '').trim();
  if (existingGloss)
    return {
      gloss: existingGloss + ' + ' + incomingGloss
    };
  return incoming;
}
export function _parseLlmDecompFeatPairs(rawFeats) {
  var raw = String(rawFeats || '').trim();
  if (!raw) return [];
  var out = [];
  var parts = raw.split('|');
  for (var i = 0; i < parts.length; i++) {
    var part = String(parts[i] || '').trim();
    if (!part) continue;
    var eq = part.indexOf('=');
    if (eq > 0) out.push([part.slice(0, eq), part.slice(eq + 1)]);
    else out.push([part, '']);
  }
  return out;
}
export function _tokenHasEligibleLlmDecompFeats(rawFeats) {
  var pairs = _parseLlmDecompFeatPairs(rawFeats);
  for (var i = 0; i < pairs.length; i++) {
    if (glossEntriesState._LLM_DECOMP_FEATURE_KEYS[pairs[i][0]]) return true;
  }
  return false;
}
export function _cloneLlmDecompRow(row) {
  var src = row && typeof row === 'object' ? row : {};
  return {
    partIdx: isFinite(Number(src.partIdx)) ? Number(src.partIdx) : -1,
    surface: String(src.surface || '').trim(),
    lemma: String(src.lemma || '').trim(),
    decomp: String(src.decomp || '').trim()
  };
}
export function mergeLlmDecompEntries(existingEntry, incomingEntry) {
  var existingRows = existingEntry && Array.isArray(existingEntry.rows) ? existingEntry.rows : [];
  var incomingRows = incomingEntry && Array.isArray(incomingEntry.rows) ? incomingEntry.rows : [];
  var mergedRows = [];
  var seen = Object.create(null);
  function appendRows(rows) {
    for (var i = 0; i < rows.length; i++) {
      var cloned = _cloneLlmDecompRow(rows[i]);
      if (!cloned.decomp) continue;
      var key = [
        String(cloned.partIdx),
        cloned.surface.toLowerCase(),
        cloned.lemma.toLowerCase(),
        cloned.decomp
      ].join('|');
      if (seen[key]) continue;
      seen[key] = true;
      mergedRows.push(cloned);
    }
  }
  appendRows(existingRows);
  appendRows(incomingRows);
  if (!mergedRows.length) {
    var fallback = String(
      (incomingEntry && incomingEntry.decomp) || (existingEntry && existingEntry.decomp) || ''
    ).trim();
    return fallback
      ? {
          decomp: fallback,
          rows: []
        }
      : null;
  }
  return {
    rows: mergedRows
  };
}
export function getRenderableLlmDecompRows(decompEntry, options) {
  var entry = decompEntry && typeof decompEntry === 'object' ? decompEntry : null;
  if (!entry) return [];
  var opts = options && typeof options === 'object' ? options : {};
  var isMwtChild = !!opts.isMwtChild;
  var partIdx = isFinite(Number(opts.partIndex)) ? Number(opts.partIndex) : -1;
  var childLemma = String(opts.childLemma || '')
    .trim()
    .toLowerCase();
  var rows = Array.isArray(entry.rows) ? entry.rows.map(_cloneLlmDecompRow) : [];
  if (!rows.length) {
    var flat = String(entry.decomp || '').trim();
    return flat
      ? [
          {
            partIdx: -1,
            surface: '',
            lemma: '',
            decomp: flat
          }
        ]
      : [];
  }
  if (isMwtChild && partIdx >= 0) {
    var exact = [];
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].partIdx === partIdx) exact.push(rows[i]);
    }
    if (exact.length) return exact;
    if (childLemma) {
      var lemmaMatches = [];
      for (var j = 0; j < rows.length; j++) {
        if (
          String(rows[j].lemma || '')
            .trim()
            .toLowerCase() === childLemma
        )
          lemmaMatches.push(rows[j]);
      }
      if (lemmaMatches.length) return lemmaMatches;
    }
    if (partIdx < rows.length) return [rows[partIdx]];
  }
  return rows;
}
export function getTokenBannerLemmaInfo(data) {
  if (!data || typeof data !== 'object') {
    return {
      lemma: '',
      raw: '',
      suffix: ''
    };
  }
  var entry = getCanonicalTokenEntry(data);
  var posData = data.posData && typeof data.posData === 'object' ? data.posData : {};
  var udTok = data.udTok && typeof data.udTok === 'object' ? data.udTok : {};
  var lemma = getTrimmedDisplayText(
    data.lemma || (entry && (entry.lemma_form || entry.lemma || '')) || posData.lemma || udTok.lemma || ''
  );
  var raw = getTrimmedDisplayText(
    data.lemma_raw ||
      (entry && (entry.lemma_raw || entry.lemma_form || entry.lemma || '')) ||
      posData.lemma_raw ||
      udTok.lemma_raw ||
      ''
  );
  var suffix = String(
    data.lemma_suffix || (entry && entry.lemma_suffix) || posData.lemma_suffix || udTok.lemma_suffix || ''
  ).trim();
  var surface = getTrimmedDisplayText(data.surface || '');
  var orderedParts = getOrderedCompoundLemmaTexts(surface, data);
  if (orderedParts.length > 1) {
    var compoundText = orderedParts.join('+');
    if (!/[+\uFF0B]/.test(lemma)) lemma = compoundText;
    if (!/[+\uFF0B]/.test(raw)) raw = compoundText;
  }
  if (!lemma) lemma = raw;
  if (!raw) raw = lemma;
  return {
    lemma: lemma,
    raw: raw,
    suffix: suffix
  };
}
export function getCanonicalTokenResolvedVia(data) {
  var entry = getCanonicalTokenEntry(data);
  if (entry) return getLookupEntryResolvedVia(entry);
  if (data && Object.prototype.hasOwnProperty.call(data, 'tokenResolvedVia')) {
    return String(data.tokenResolvedVia || '')
      .trim()
      .toLowerCase();
  }
  return String((data && data.resolvedVia) || '')
    .trim()
    .toLowerCase();
}
export function getCanonicalTokenDictFill(data) {
  var entry = getCanonicalTokenEntry(data);
  if (entry) return getLookupEntryFills(entry);
  if (data && Array.isArray(data.tokenDictFill)) return data.tokenDictFill;
  if (data && Array.isArray(data.dictFill)) return data.dictFill;
  return [];
}
export function tokenStateHasExactWholeMatch(data, surfaceText) {
  var surface = String(surfaceText || getCanonicalTokenSurfaceText(data) || '').trim();
  if (!surface) return false;
  var entry = getCanonicalTokenEntry(data);
  if (!entry || isUnknownDictEntry(entry)) return false;
  var liveResolution = getTokenLiveResolution(entry);
  if (liveResolution) {
    if (liveResolution.exact_surface_match === true) return true;
    var category = String(liveResolution.category || '')
      .trim()
      .toLowerCase();
    if (category !== 'exact_match') return false;
  }
  if (
    String(entry.source || '')
      .trim()
      .toUpperCase() === 'COMPOSITE'
  )
    return false;
  var dictFill = getCanonicalTokenDictFill(data);
  if (dictFill.length === 1 && hasExactTokenLookupMatch(dictFill[0], surface)) return true;
  return hasExactTokenLookupMatch(entry, surface);
}
export function tokenStateHasExactLemmaCoverage(data) {
  var canonicalEntry = getCanonicalTokenEntry(data);
  var liveResolution = getTokenLiveResolution(canonicalEntry);
  if (liveResolution && liveResolution.exact_matches_lemma === true) return true;
  if (getCanonicalTokenResolvedVia(data) !== 'lemma_override') return false;
  var lemmaInfo = getCanonicalTokenLemmaInfo(data);
  var lemmaText = String(lemmaInfo.lemma || '').trim();
  if (!lemmaText) return false;
  if (!/[+\uFF0B]/.test(lemmaText)) {
    var tokenEntry = getCanonicalTokenEntry(data) || {};
    var tokenResolution = getLookupEntryResolution(tokenEntry) || {};
    var missingCount = Number(
      tokenResolution.partial_missing_lemma_count || tokenEntry.partial_missing_lemma_count || 0
    );
    var gapCount = Number(tokenResolution.partial_gap_count || tokenEntry.partial_gap_count || 0);
    return missingCount === 0 && gapCount === 0;
  }
  var parts = getTokenMapLemmaPartTexts(lemmaText);
  if (!parts.length) return false;
  for (var i = 0; i < parts.length; i++) {
    var partText = String(parts[i] || '').trim();
    if (!partText) continue;
    var partLookup = getTokenMapLemmaPartLookup(data, partText, i);
    if (!hasExactTokenLookupMatch(partLookup, partText)) return false;
  }
  return true;
}
export function getScopedMwtPartIndex(dictFill, explicitPartIndex) {
  var parsedExplicit = parseInt(explicitPartIndex, 10);
  if (isFinite(parsedExplicit)) return parsedExplicit;
  if (!Array.isArray(dictFill) || !dictFill.length) return null;
  var seen = Object.create(null);
  var found = [];
  for (var i = 0; i < dictFill.length; i++) {
    var row = dictFill[i] || {};
    var partIndex = parseInt(row._mwt_part_index, 10);
    if (!isFinite(partIndex) || seen[partIndex]) continue;
    seen[partIndex] = true;
    found.push(partIndex);
    if (found.length > 1) return null;
  }
  return found.length === 1 ? found[0] : null;
}
export function getScopedMwtChildResolutionCategory(entry, dictFill, explicitPartIndex) {
  if (!entry || typeof entry !== 'object') return '';
  var childResolutions = Array.isArray(entry.mwt_child_resolutions) ? entry.mwt_child_resolutions : [];
  if (!childResolutions.length) return '';
  var scopedPartIndex = getScopedMwtPartIndex(dictFill, explicitPartIndex);
  if (!isFinite(scopedPartIndex) || scopedPartIndex < 0 || scopedPartIndex >= childResolutions.length)
    return '';
  return String(childResolutions[scopedPartIndex] || '')
    .trim()
    .toLowerCase();
}
export function cloneLookupEntryForScopedPart(entry, dictFill, explicitPartIndex) {
  var src = entry && typeof entry === 'object' ? entry : null;
  var scopedFill = Array.isArray(dictFill) ? dictFill.slice() : [];
  var parsedPartIndex = parseInt(explicitPartIndex, 10);
  if (isFinite(parsedPartIndex)) {
    var filtered = _filterDictFillForMwtPart(scopedFill, parsedPartIndex);
    if (filtered && Array.isArray(filtered.rows) && filtered.rows.length) scopedFill = filtered.rows.slice();
  }
  if (!src) {
    return scopedFill.length
      ? {
          dict_fill: scopedFill.slice()
        }
      : src;
  }
  var clone = {};
  for (var key in src) {
    if (!Object.prototype.hasOwnProperty.call(src, key)) continue;
    clone[key] = src[key];
  }
  clone.dict_fill = scopedFill.slice();
  var childCategory = getScopedMwtChildResolutionCategory(src, scopedFill, parsedPartIndex);
  if (!childCategory) return clone;
  var scopedResolution = {};
  var baseResolution = getLookupEntryResolution(src);
  if (baseResolution && typeof baseResolution === 'object') {
    for (var resKey in baseResolution) {
      if (!Object.prototype.hasOwnProperty.call(baseResolution, resKey)) continue;
      scopedResolution[resKey] = baseResolution[resKey];
    }
  }
  scopedResolution.category = childCategory;
  scopedResolution.exact_surface_match =
    childCategory === 'exact_match' || childCategory === 'exact_lemma_match';
  scopedResolution.exact_matches_lemma = childCategory === 'exact_lemma_match';
  scopedResolution.resolved_via =
    childCategory === 'lemma_override' || childCategory === 'lemma_partial_override'
      ? 'lemma_override'
      : 'surface';
  clone.resolution = scopedResolution;
  clone.resolution_actual = scopedResolution;
  clone.resolution_live = scopedResolution;
  clone.resolved_via = scopedResolution.resolved_via;
  clone.mwt_child_resolutions = [childCategory];
  return clone;
}
// Shared predicate for the grammar-popup reminder. The main side-panel
// synthetic-entry button uses its own broader visibility rule.
// Works with both the full tokenMapData object (panel path) and a raw
// resultsBySeg entry (hover path) by wrapping the raw entry so
// getCanonicalTokenEntry finds it.
export function _surfaceHasGlossableChar(text) {
  // Mirrors Python _is_glossable_token: returns true if at least one letter exists.
  // Rejects pure punctuation, numbers, symbols, whitespace, etc.
  return /\p{L}/u.test(String(text || ''));
}
export function tokenShouldShowSynthHint(resOrData, surface) {
  if (!surface) return false;
  if (!_surfaceHasGlossableChar(surface)) return false;
  var data =
    resOrData && (resOrData.tokenEntry || resOrData.entry)
      ? resOrData
      : {
          entry: resOrData
        };
  var explicitPartIndex = data && isFinite(Number(data.mwtPartIndex)) ? Number(data.mwtPartIndex) : null;
  var entry = cloneLookupEntryForScopedPart(
    getCanonicalTokenEntry(data),
    getCanonicalTokenDictFill(data),
    explicitPartIndex
  );
  // Show hint for unknown tokens — no dictionary match at all.
  if (isUnknownDictEntry(entry)) return true;
  // Show hint when the segmenter used greedy segmentation (i.e. it broke the
  // token into pieces because no single entry covered it). MWT tokens that are
  // cleanly resolved (exact parts, lemma override, etc.) will have a non-greedy
  // category and will correctly not show the hint.
  var resolution = getLookupEntryResolution(entry);
  var category = String((resolution && resolution.category) || '')
    .trim()
    .toLowerCase();
  return category === 'greedy_match' || category === 'greedy_segmentation';
}
export function _hasOneExactHeadwordMatch(entry, expectedText) {
  // Returns true ONLY if the entry itself is a single exact headword match
  // for expectedText � not greedy fragments that happen to contain it.
  var expected = String(expectedText || '').trim();
  if (!entry || !expected) return false;
  var displayHead = String(getEntryDisplayHead(entry, '') || '').trim();
  if (displayHead && hasSameVisibleComparisonText(displayHead, expected)) {
    // Must not be a composite/greedy result � check no multi-piece dict_fill
    var dictFill = getLookupEntryFills(entry);
    if (dictFill.length <= 1) return true;
    // Multiple fill pieces means greedy fragmentation, not a single entry
    return false;
  }
  // Check if exactly one dict_fill piece is an exact match for the whole text
  var dictFill = getLookupEntryFills(entry);
  if (dictFill.length === 1) {
    var fillHead = String(getEntryDisplayHead(dictFill[0], '') || '').trim();
    if (fillHead && hasSameVisibleComparisonText(fillHead, expected)) return true;
  }
  return false;
}
export function getKoreanSyntheticCompoundLemmaParts(data, surfaceText) {
  if (!isKoreanCurrentLanguageForGloss()) return [];
  if (tokenHasRealMwtParts(data)) return [];
  var surface = String(surfaceText || (data && data.surface) || '').trim();
  var entry = data && (data.tokenEntry || data.entry || null);
  var posData = data && data.posData && typeof data.posData === 'object' ? data.posData : {};
  var udTok = data && data.udTok && typeof data.udTok === 'object' ? data.udTok : {};
  var out = [];
  var seen = Object.create(null);
  function addPart(rawText) {
    var partText = getTrimmedDisplayText(rawText || '');
    if (!partText || seen[partText]) return;
    seen[partText] = true;
    out.push(partText);
  }
  function addPlusParts(rawText) {
    var raw = getTrimmedDisplayText(rawText || '');
    if (!raw || !/[+\uFF0B]/.test(raw)) return;
    var parts = getTokenMapLemmaPartTexts(raw);
    for (var i = 0; i < parts.length; i++) addPart(parts[i]);
  }
  addPlusParts(data && data.lemma_raw);
  addPlusParts(data && data.lemma);
  addPlusParts(entry && entry.lemma_raw);
  addPlusParts(entry && (entry.lemma_form || entry.lemma));
  addPlusParts(posData.lemma_raw);
  addPlusParts(posData.lemma);
  addPlusParts(udTok.lemma_raw);
  addPlusParts(udTok.lemma);
  if (out.length < 2 && entry && Array.isArray(entry.lemma_override_parts)) {
    for (var oi = 0; oi < entry.lemma_override_parts.length; oi++) {
      var overridePart = entry.lemma_override_parts[oi] || {};
      addPart(overridePart.text || overridePart.source_text || '');
    }
  }
  return out.length > 1 ? out : [];
}
export function resolveSyntheticGenerationTargets(data, surfaceText) {
  var surface = String(surfaceText || (data && data.surface) || '').trim();
  if (!surface) return [];
  var popupChildText = getSyntheticEntryPopupChildText(data);
  if (popupChildText) return [popupChildText];
  var mwtParts = getSyntheticEntryMwtSurfaceTexts(data);
  if (mwtParts.length) return mwtParts;
  var koreanParts = getKoreanSyntheticCompoundLemmaParts(data, surface);
  if (koreanParts.length > 1) return koreanParts;
  var parts = getOrderedCompoundLemmaTexts(surface, data);
  if (parts.length > 1) {
    var uniqueParts = [];
    var seen = Object.create(null);
    for (var i = 0; i < parts.length; i++) {
      var partText = String(parts[i] || '').trim();
      if (!partText || seen[partText]) continue;
      seen[partText] = true;
      uniqueParts.push(partText);
    }
    if (uniqueParts.length) return uniqueParts;
  }
  return [surface];
}
export function hasSyntheticEntryMwtPartContext(data) {
  return !!(data && normalizeUdPartIndex(data.mwtPartIndex) !== null);
}
export function getSyntheticEntryPopupChildText(data) {
  if (!hasSyntheticEntryMwtPartContext(data)) return '';
  return String((data && data.mwtChildText) || '').trim();
}
export function getSyntheticEntryMwtSurfaceTexts(data) {
  var popupChildText = getSyntheticEntryPopupChildText(data);
  if (popupChildText) return [popupChildText];
  var mwtParts = [];
  if (data && Array.isArray(data.mwt_parts) && data.mwt_parts.length) {
    mwtParts = data.mwt_parts;
  } else if (data && data.udTok && Array.isArray(data.udTok.mwt_parts) && data.udTok.mwt_parts.length) {
    mwtParts = data.udTok.mwt_parts;
  } else if (data && isFinite(data.segIdx)) {
    mwtParts = getMwtPartsForSeg(data.segIdx);
  }
  if (!Array.isArray(mwtParts) || !mwtParts.length) return [];
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < mwtParts.length; i++) {
    var rawPart = mwtParts[i];
    var partText = String((rawPart && rawPart.text) || rawPart || '').trim();
    if (!partText || seen[partText]) continue;
    seen[partText] = true;
    out.push(partText);
  }
  return out;
}
export function buildSyntheticEntryChooserChoices(data, surfaceText) {
  var surface = String(surfaceText || (data && data.surface) || '').trim();
  if (!surface) return [];
  var lemmaInfo = getTokenBannerLemmaInfo(data);
  var compoundParts = getOrderedCompoundLemmaTexts(surface, data);
  var compoundText =
    compoundParts.length > 1
      ? compoundParts.join('+')
      : String(lemmaInfo.raw || lemmaInfo.lemma || '').trim();
  var choices = [];
  var seen = Object.create(null);
  function addChoice(text, label, kind) {
    var choiceText = String(text || '').trim();
    if (!choiceText || seen[choiceText]) return;
    seen[choiceText] = true;
    choices.push({
      text: choiceText,
      label: String(label || choiceText).trim() || choiceText,
      kind: String(kind || '').trim()
    });
  }
  var mwtParts = getSyntheticEntryMwtSurfaceTexts(data);
  if (mwtParts.length) {
    for (var mi = 0; mi < mwtParts.length; mi++) {
      addChoice(mwtParts[mi], mwtParts[mi], 'mwt-part');
    }
    return choices;
  }
  var koreanParts = getKoreanSyntheticCompoundLemmaParts(data, surface);
  if (koreanParts.length > 1) {
    addChoice(surface, surface, 'surface');
    for (var ki = 0; ki < koreanParts.length; ki++) {
      addChoice(koreanParts[ki], koreanParts[ki], 'lemma-part');
    }
    return choices;
  }
  if (compoundParts.length > 1 || /[+\uFF0B]/.test(compoundText)) {
    addChoice(surface, surface, 'surface');
    var parts = compoundParts.length > 1 ? compoundParts : resolveSyntheticGenerationTargets(data, surface);
    for (var i = 0; i < parts.length; i++) {
      addChoice(parts[i], parts[i], 'lemma-part');
    }
    return choices;
  }
  addChoice(surface, surface, 'surface');
  return choices;
}
export function getSyntheticEntryBarKey(data, surfaceText) {
  var surface = String(surfaceText || (data && data.surface) || '').trim();
  var lemmaInfo = getTokenBannerLemmaInfo(data);
  var lemma = String(lemmaInfo.lemma || '').trim();
  var lemmaRaw = String(lemmaInfo.raw || lemma || '').trim();
  var segIdx = data && typeof data.segIdx === 'number' && isFinite(data.segIdx) ? String(data.segIdx) : '';
  return [
    String(documentShellState.currentLanguage || '')
      .trim()
      .toLowerCase(),
    segIdx,
    surface,
    lemmaRaw || lemma
  ].join('|');
}
export function clearSyntheticEntryBarState() {
  hoverLayoutState._syntheticEntryBarState = null;
}
export function setExpandableBannerExpanded(container, toggleId, nextExpanded) {
  if (!container) return;
  container.classList.toggle('expanded', !!nextExpanded);
  var expandToggle = container.querySelector('#' + toggleId);
  if (expandToggle) expandToggle.setAttribute('aria-expanded', nextExpanded ? 'true' : 'false');
}
export function wireExpandableBannerToggle(container, toggleId, onToggle) {
  if (!container || typeof onToggle !== 'function') return;
  var expandToggle = container.querySelector('#' + toggleId);
  if (!expandToggle) return;
  expandToggle.addEventListener('click', function () {
    onToggle();
  });
  expandToggle.addEventListener('keydown', function (ev) {
    var key = String((ev && ev.key) || '');
    if (key !== 'Enter' && key !== ' ') return;
    ev.preventDefault();
    onToggle();
  });
}
export function ensureSyntheticEntryBarState(data, surfaceText) {
  var surface = String(surfaceText || (data && data.surface) || '').trim();
  if (!surface) return null;
  var key = getSyntheticEntryBarKey(data, surface);
  var lemmaInfo = getTokenBannerLemmaInfo(data);
  var choices = buildSyntheticEntryChooserChoices(data, surface);
  if (!choices.length)
    choices = [
      {
        text: surface,
        label: surface,
        kind: 'surface'
      }
    ];
  var state = hoverLayoutState._syntheticEntryBarState;
  if (!state || state.key !== key) {
    state = {
      mode: 'idle',
      key: key,
      surface: surface,
      lemma: String(lemmaInfo.lemma || '').trim(),
      lemmaRaw: String(lemmaInfo.raw || lemmaInfo.lemma || '').trim(),
      choices: choices,
      selected: Object.create(null),
      expanded: false,
      status: '',
      pendingTexts: []
    };
    hoverLayoutState._syntheticEntryBarState = state;
    return state;
  }
  var nextSelected = Object.create(null);
  var selectedFound = false;
  if (state.selected && typeof state.selected === 'object') {
    for (var i = 0; i < choices.length; i++) {
      var choice = choices[i] || {};
      var choiceText = String(choice.text || choice.value || choice.label || choice || '').trim();
      var choiceLabel = String(choice.label || choiceText).trim() || choiceText;
      if (!choiceText) continue;
      if (!selectedFound && (state.selected[choiceText] || state.selected[choiceLabel])) {
        nextSelected[choiceText] = true;
        selectedFound = true;
      }
    }
  }
  state.surface = surface;
  state.lemma = String(lemmaInfo.lemma || '').trim();
  state.lemmaRaw = String(lemmaInfo.raw || lemmaInfo.lemma || '').trim();
  state.choices = choices;
  state.selected = nextSelected;
  if (state.mode !== 'sending') {
    state.mode = 'idle';
    state.status = '';
    state.pendingTexts = [];
  }
  return state;
}
export function initializeGlossEntries() {
  glossEntriesState._LLM_DECOMP_FEATURE_KEYS = (function () {
    var names = [
      'Gender',
      'VerbForm',
      'Animacy',
      'Mood',
      'NounClass',
      'Tense',
      'Number',
      'Aspect',
      'Case',
      'Voice',
      'Definite',
      'Evident',
      'Deixis',
      'Polarity',
      'DeixisRef',
      'Person',
      'Degree',
      'Polite',
      'Clusivity'
    ];
    var out = Object.create(null);
    for (var i = 0; i < names.length; i++) out[names[i]] = true;
    return out;
  })();
  return true;
}
