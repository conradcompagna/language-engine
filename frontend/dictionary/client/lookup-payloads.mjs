import {
  buildDebugLemmaHintPreview,
  buildLiveResolutionInfo,
  choosePreferredSenseFilterXpos
} from './alignment-inputs.mjs';
import { normalizeVisibleComparisonText } from './core.mjs';
import { coreState } from './core.state.mjs';
import { attachWiktForms, chooseEntry, getEntryDisplayReading } from './entry-adapters.mjs';
import { buildLiveLookupFillPayload } from './mwt-slices.mjs';
import {
  buildDebugEntryRefs,
  buildJmdictFormsMetaByHeader,
  formatSenses,
  mergeAllEntries,
  splitEntriesForHover
} from './result-merging.mjs';
import {
  buildSinglePassSurfaceLookup,
  collectStrictLemmaEntriesForPromotedFillRow,
  isMwtUdToken,
  shouldApplyStrictExactLemmaDisplayFilter
} from './surface-lookup.mjs';
export function applyFillRepresentativeEntry(target, entry, forceDisplayFields) {
  if (!target || typeof target !== 'object' || !entry || typeof entry !== 'object') return;
  var forceDisplay = !!forceDisplayFields;
  var displayHeadword = String(entry.display_headword || entry.headword || '').trim();
  var lemmaHeadword = String(entry.lemma_headword || '').trim();
  var displayReading = getEntryDisplayReading(entry);
  if (entry.entry_id) target.entry_id = String(entry.entry_id || '');
  if (entry.ref_key) target.ref_key = String(entry.ref_key || '');
  if (entry.runtime_entry_id) target.runtime_entry_id = String(entry.runtime_entry_id || '');
  if (lemmaHeadword) {
    target.lemma_headword = lemmaHeadword;
    if (forceDisplay || !target.lemma_form) target.lemma_form = lemmaHeadword;
  }
  if (displayHeadword) {
    target.display_headword = displayHeadword;
    target.headword = displayHeadword;
  }
  if (displayReading) {
    target.display_reading = displayReading;
    if (!target.entry_reading && entry.entry_reading)
      target.entry_reading = String(entry.entry_reading || '');
  }
  if (entry.match_kind)
    target.match_kind = String(entry.match_kind || '')
      .trim()
      .toLowerCase();
  if (entry._source) target._source = String(entry._source || '');
  else if (entry.source && !target._source) target._source = String(entry.source || '');
  if (forceDisplay || !target.roman) target.roman = displayReading;
  if (forceDisplay || !target.reading) target.reading = displayReading;
  if (forceDisplay || !target.pos) target.pos = String(entry.pos || entry.pos_raw || '');
  if (forceDisplay || !target.pos_raw) target.pos_raw = String(entry.pos_raw || entry.pos || '');
  if (entry.morph_info) {
    target.morph_info = Array.isArray(entry.morph_info)
      ? entry.morph_info.slice()
      : [String(entry.morph_info || '')];
  } else if (forceDisplay && Object.prototype.hasOwnProperty.call(target, 'morph_info')) {
    delete target.morph_info;
  }
  if (entry.morph_base) {
    target.morph_base = String(entry.morph_base || '');
  } else if (forceDisplay && Object.prototype.hasOwnProperty.call(target, 'morph_base')) {
    delete target.morph_base;
  }
  if (entry.grammar) {
    target.grammar = String(entry.grammar || '');
  } else if (forceDisplay && Object.prototype.hasOwnProperty.call(target, 'grammar')) {
    delete target.grammar;
  }
  if (entry._commentary !== undefined) target._commentary = String(entry._commentary || '');
  if (entry._lemma !== undefined) target._lemma = String(entry._lemma || '');
  if (entry.is_alternate_match !== undefined) target.is_alternate_match = !!entry.is_alternate_match;
}
export function _entryRefKey(entry) {
  if (!entry || typeof entry !== 'object') return '';
  return String(entry.ref_key || entry.runtime_entry_id || '').trim();
}
export function _entryRefKeys(entries) {
  var out = [];
  var list = Array.isArray(entries) ? entries : [];
  for (var i = 0; i < list.length; i++) {
    var k = _entryRefKey(list[i]);
    if (k) out.push(k);
  }
  return out;
}
export function setAtomicRenderEntries(target, allEntries, hoverEntries, otherEntries) {
  if (!target || typeof target !== 'object') return;
  var allKeys = _entryRefKeys(allEntries);
  var hoverKeys = _entryRefKeys(hoverEntries);
  var otherKeys = _entryRefKeys(otherEntries);
  if (allKeys.length) target.atomic_entry_refs_all = allKeys;
  else if (Object.prototype.hasOwnProperty.call(target, 'atomic_entry_refs_all'))
    delete target.atomic_entry_refs_all;
  if (hoverKeys.length) target.atomic_entry_refs_hover = hoverKeys;
  else if (Object.prototype.hasOwnProperty.call(target, 'atomic_entry_refs_hover'))
    delete target.atomic_entry_refs_hover;
  if (otherKeys.length) target.atomic_entry_refs_other = otherKeys;
  else if (Object.prototype.hasOwnProperty.call(target, 'atomic_entry_refs_other'))
    delete target.atomic_entry_refs_other;
  // Remove old full-object arrays if present
  delete target.atomic_entries_all;
  delete target.atomic_entries_hover;
  delete target.atomic_entries_other;
  if (Object.prototype.hasOwnProperty.call(target, '_dict_source')) delete target._dict_source;
}
export function prepareFillEntries(fills, engine, upos, xpos, fillMode, includeDebugTrace) {
  var out = (fills || []).slice();
  var includeTrace = !!includeDebugTrace;
  var mode = String(fillMode || '')
    .trim()
    .toLowerCase();
  var greedyMatchMode =
    mode === 'greedy' ||
    mode === 'lemma_greedy' ||
    mode === 'lemma_partial_greedy' ||
    mode === 'greedy_lemma_mismatch';
  var knownFillPieceCount = 0;
  for (var k = 0; k < out.length; k++) {
    if (String((out[k] || {}).source || '').toUpperCase() !== 'UNKNOWN') knownFillPieceCount += 1;
  }
  var greedyMultiFill = greedyMatchMode && knownFillPieceCount > 1;
  for (var i = 0; i < out.length; i++) {
    var f = out[i] || {};
    var fillHead = String(f.head || '');
    var fillText = String(f.text || '');
    var displayHead = fillText || fillHead;
    var lookupHead = fillHead || displayHead;
    if (displayHead) f.head = displayHead;
    var fillXposHint = String(f._xpos_hint || '');
    var fillEntries = f.entries && f.entries.length ? f.entries : [];
    var hoverEntries = fillEntries && fillEntries.length ? fillEntries.slice() : [];
    var otherEntries = [];
    var fullFormsMetaByHeader = {};
    var hoverFormsMetaByHeader = {};
    var otherFormsMetaByHeader = {};
    var fullSenses = [];
    if (fillEntries && fillEntries.length) {
      fullSenses = mergeAllEntries(displayHead || lookupHead, fillEntries);
      fullFormsMetaByHeader = buildJmdictFormsMetaByHeader(fillEntries);
    } else if (f.senses && f.senses.length) {
      fullSenses = formatSenses(displayHead || lookupHead, f.roman || '', f.senses);
    }
    f.senses = fullSenses;
    var hoverSenses = fullSenses.slice();
    var otherSenses = [];
    if (fillEntries && fillEntries.length) {
      var splitKw = {};
      if (greedyMatchMode) splitKw.greedy_match = true;
      if (greedyMultiFill) splitKw.greedy_multi_fill = true;
      if (Array.isArray(f._force_pos_raws) && f._force_pos_raws.length) {
        splitKw.force_pos_raws = f._force_pos_raws.slice();
      }
      var strictLemmaEntries = collectStrictLemmaEntriesForPromotedFillRow(fillEntries, f, engine);
      if (strictLemmaEntries.length) {
        splitKw.strict_exact_lemma_entries = strictLemmaEntries;
      }
      // Frozen lemma-linked fill rows correspond to a specific component,
      // so their per-row UPOS hint must override the whole-token UPOS.
      var effectiveUpos = String(f._lemma_upos_hint || upos || '').trim();
      var effectiveXpos = String(fillXposHint || f._lemma_xpos_hint || xpos || '');
      var split = splitEntriesForHover(fillEntries, effectiveUpos, engine, effectiveXpos, splitKw);
      hoverEntries = split[0];
      otherEntries = split[1];
      hoverSenses = mergeAllEntries(displayHead || lookupHead, hoverEntries);
      if (otherEntries && otherEntries.length) {
        otherSenses = mergeAllEntries(displayHead || lookupHead, otherEntries);
      }
      hoverFormsMetaByHeader = buildJmdictFormsMetaByHeader(hoverEntries);
      if (otherEntries && otherEntries.length) {
        otherFormsMetaByHeader = buildJmdictFormsMetaByHeader(otherEntries);
      }
      if (hoverEntries && hoverEntries.length) {
        var hoverTmp = {};
        attachWiktForms(hoverTmp, displayHead || lookupHead, hoverEntries);
        if (hoverTmp.entry_groups) f.entry_groups_hover = hoverTmp.entry_groups;
      }
      if (otherEntries && otherEntries.length) {
        var otherTmp = {};
        attachWiktForms(otherTmp, displayHead || lookupHead, otherEntries);
        if (otherTmp.entry_groups) f.entry_groups_other = otherTmp.entry_groups;
      }
    }
    if (includeTrace) {
      f._debug_entry_refs_all = buildDebugEntryRefs(fillEntries || []);
      f._debug_entry_refs_shown = buildDebugEntryRefs(hoverEntries || []);
      f._debug_entry_refs_filtered = buildDebugEntryRefs(otherEntries || []);
      f._debug_trace = {
        mode: mode,
        upos: String(upos || ''),
        xpos: String(fillXposHint || xpos || ''),
        effective_upos: effectiveUpos,
        effective_xpos: effectiveXpos,
        force_pos_raws: Array.isArray(f._force_pos_raws) ? f._force_pos_raws.slice() : [],
        lemma_upos_hint: String(f._lemma_upos_hint || ''),
        lemma_xpos_hint: String(f._lemma_xpos_hint || ''),
        greedy_match_mode: !!greedyMatchMode,
        greedy_multi_fill: !!greedyMultiFill,
        lemma_promoted: f._lemma_promoted || null,
        lemma_promoted_headword: f._lemma_promoted_headword || null,
        lemma_promoted_pos: f._lemma_promoted_pos || null
      };
    } else {
      if (Object.prototype.hasOwnProperty.call(f, '_debug_entry_refs_all')) delete f._debug_entry_refs_all;
      if (Object.prototype.hasOwnProperty.call(f, '_debug_entry_refs_shown'))
        delete f._debug_entry_refs_shown;
      if (Object.prototype.hasOwnProperty.call(f, '_debug_entry_refs_filtered'))
        delete f._debug_entry_refs_filtered;
      if (Object.prototype.hasOwnProperty.call(f, '_debug_trace')) delete f._debug_trace;
    }
    f.senses_hover = hoverSenses;
    f.senses_hover_other = otherSenses;
    f.hover_has_alt_senses = !!otherSenses.length;
    if (Object.prototype.hasOwnProperty.call(f, '_xpos_hint')) delete f._xpos_hint;
    if (Object.prototype.hasOwnProperty.call(f, '_force_pos_raws')) delete f._force_pos_raws;
    if (Object.prototype.hasOwnProperty.call(f, '_lemma_upos_hint')) delete f._lemma_upos_hint;
    if (Object.prototype.hasOwnProperty.call(f, '_lemma_xpos_hint')) delete f._lemma_xpos_hint;
    if (Object.keys(fullFormsMetaByHeader).length) f.senses_form_meta_by_header = fullFormsMetaByHeader;
    if (Object.keys(hoverFormsMetaByHeader).length)
      f.senses_hover_form_meta_by_header = hoverFormsMetaByHeader;
    if (Object.keys(otherFormsMetaByHeader).length)
      f.senses_hover_other_form_meta_by_header = otherFormsMetaByHeader;
    setAtomicRenderEntries(f, fillEntries, hoverEntries, otherEntries);
    var chosenFill = chooseEntry(lookupHead, hoverEntries.length ? hoverEntries : fillEntries || [], engine);
    if (chosenFill) {
      applyFillRepresentativeEntry(f, chosenFill, false);
    }

    // Primary display should use the filtered "hover" entries so forced
    // alternate/redirect rows stay behind the other-definitions expander.
    attachWiktForms(f, displayHead || lookupHead, hoverEntries.length ? hoverEntries : fillEntries || []);
    if (Object.prototype.hasOwnProperty.call(f, 'g2p')) delete f.g2p;
    // Replace full entry objects with ref keys to avoid serialization bloat
    f.entry_refs = _entryRefKeys(fillEntries);
    delete f.entries;
  }
  return out;
}
export function cloneSurfaceAnchor(anchor) {
  if (!anchor || typeof anchor !== 'object') return null;
  var rawSlice = Array.isArray(anchor.slice) ? anchor.slice : null;
  if (!rawSlice || rawSlice.length < 2) return null;
  var start = Number(rawSlice[0]);
  var end = Number(rawSlice[1]);
  if (!isFinite(start) || !isFinite(end) || end < start) return null;
  return {
    text: String(anchor.text || ''),
    slice: [start, end]
  };
}
export function isPopupOnlySurfaceAnchorToken(tokenText, surfaceText, surfaceAnchor) {
  var anchor = cloneSurfaceAnchor(surfaceAnchor);
  if (!anchor) return false;
  var childText = String(tokenText || '').trim();
  var visibleSurface = String(surfaceText || anchor.text || '').trim();
  if (!childText || !visibleSurface) return false;
  return normalizeVisibleComparisonText(childText) !== normalizeVisibleComparisonText(visibleSurface);
}
export function buildUnknownResult(
  word,
  upos,
  xpos,
  deprel,
  lemma,
  feats,
  idx,
  lemmaRaw,
  lemmaSuffix,
  surfaceForm,
  surfaceAnchor
) {
  var tokenText = String(word || '');
  var surfaceText = String(surfaceForm || tokenText);
  var entry = {
    text: tokenText,
    token_text: tokenText,
    head: tokenText,
    roman: '',
    pos: upos,
    meta_pos: 'unknown',
    senses: [],
    source: 'UNKNOWN',
    dict_fill: [],
    dict_fill_subwords: [],
    dict_fill_surface_slices: [],
    inspect_fill: [],
    dict_fill_mode: 'greedy',
    dict_fill_has_known: false,
    dict_fill_has_unknown: true,
    seg_i: idx,
    g2p: null,
    upos: upos,
    upos_label: upos,
    upos_color: coreState.UPOS_COLORS[upos] || '#d1d5db',
    dep: deprel,
    dep_label: deprel,
    tag: xpos,
    lemma: lemma || '',
    feats: feats || '',
    surface_form: surfaceText
  };
  if (lemma) entry.lemma_form = lemma;
  if (lemmaRaw) entry.lemma_raw = lemmaRaw;
  if (lemmaSuffix) entry.lemma_suffix = lemmaSuffix;
  var copiedSurfaceAnchor = cloneSurfaceAnchor(surfaceAnchor);
  if (copiedSurfaceAnchor) entry.surface_anchor = copiedSurfaceAnchor;
  entry.resolution_actual = buildLiveResolutionInfo(null, [], 0);
  entry.resolution_live = entry.resolution_actual;
  return entry;
}
export function buildKoreanCompoundLemmaChildResult(childPayload, engine, includeDebugTrace) {
  var child = childPayload && typeof childPayload === 'object' ? childPayload : null;
  if (!child) return null;
  var token = String(child.text || '').trim();
  if (!token) return null;
  var surfaceLookup = child.lookup && typeof child.lookup === 'object' ? child.lookup : {};
  var upos = String(child.upos || '').trim();
  var xpos = String(child.xpos || '').trim();
  var fill = surfaceLookup.fill || null;
  var allEntries = Array.isArray(surfaceLookup.all_entries) ? surfaceLookup.all_entries : [];
  var preferredEntries =
    Array.isArray(surfaceLookup.preferred_entries) && surfaceLookup.preferred_entries.length
      ? surfaceLookup.preferred_entries
      : allEntries;
  var dictHead = String(surfaceLookup.dict_head || token);
  var resolvedVia = String(surfaceLookup.resolved_via || 'surface');
  var lemmaHintObjects =
    surfaceLookup.lemma_hint_data && Array.isArray(surfaceLookup.lemma_hint_data.lemma_hint_objects)
      ? surfaceLookup.lemma_hint_data.lemma_hint_objects
      : [];
  var lemmaOverrideParts = Array.isArray(surfaceLookup.lemma_override_parts)
    ? surfaceLookup.lemma_override_parts
    : [];
  var exactLemmaMatchCount = Number(surfaceLookup.exact_lemma_match_count || 0);
  var preferredSenseFilterXpos = choosePreferredSenseFilterXpos(
    xpos,
    lemmaHintObjects,
    lemmaOverrideParts,
    engine
  );
  var fillPayload = buildLiveLookupFillPayload(
    token,
    fill,
    token,
    upos,
    xpos,
    preferredSenseFilterXpos,
    engine,
    resolvedVia,
    [],
    includeDebugTrace
  );
  var rawFills = fillPayload.rawFills;
  var fillMode = fillPayload.fillMode;
  var fillSurfaceSlices = fillPayload.fillSurfaceSlices;
  if (!rawFills.length) {
    rawFills = [
      {
        text: token,
        head: token,
        surface_form: token,
        senses: [],
        pos: upos || 'unknown',
        source: 'UNKNOWN'
      }
    ];
    fillSurfaceSlices = [];
  }
  var hasKnownFill = rawFills.some(function (row) {
    return !!(row && String(row.source || '').toUpperCase() !== 'UNKNOWN');
  });
  var hasUnknownFill = rawFills.some(function (row) {
    return !row || String(row.source || '').toUpperCase() === 'UNKNOWN';
  });
  var result;
  if (allEntries.length) {
    var entryFilterKw = {};
    var fillModeLower = String(fillMode || '')
      .trim()
      .toLowerCase();
    if (
      fillModeLower === 'greedy' ||
      fillModeLower === 'lemma_greedy' ||
      fillModeLower === 'lemma_partial_greedy' ||
      fillModeLower === 'greedy_lemma_mismatch'
    ) {
      entryFilterKw.greedy_match = true;
    }
    if (shouldApplyStrictExactLemmaDisplayFilter(resolvedVia, exactLemmaMatchCount, preferredEntries)) {
      entryFilterKw.strict_exact_lemma_entries = preferredEntries.slice();
    }
    var split = splitEntriesForHover(allEntries, upos || '', engine, preferredSenseFilterXpos, entryFilterKw);
    var hoverEntries = split[0];
    var otherEntries = split[1];
    var primaryPool = hoverEntries.length ? hoverEntries : preferredEntries;
    var best =
      chooseEntry(dictHead, primaryPool || [], engine) ||
      (primaryPool && primaryPool.length ? primaryPool[0] : allEntries[0]);
    var mergedSenses = mergeAllEntries(dictHead, allEntries);
    var hoverSenses = mergeAllEntries(dictHead, hoverEntries);
    var hoverOtherSenses = otherEntries.length ? mergeAllEntries(dictHead, otherEntries) : [];
    var formsMetaByHeader = buildJmdictFormsMetaByHeader(allEntries);
    var hoverFormsMetaByHeader = buildJmdictFormsMetaByHeader(hoverEntries);
    var otherFormsMetaByHeader = otherEntries.length ? buildJmdictFormsMetaByHeader(otherEntries) : {};
    result = {
      text: token,
      token_text: token,
      head: dictHead,
      roman: getEntryDisplayReading(best),
      pos: upos || '',
      meta_pos: upos || '',
      lemma: token,
      lemma_form: token,
      feats: '',
      senses: mergedSenses,
      source: 'DICT',
      senses_hover: hoverSenses,
      senses_hover_other: hoverOtherSenses,
      hover_has_alt_senses: !!hoverOtherSenses.length
    };
    if (Object.keys(formsMetaByHeader).length) result.senses_form_meta_by_header = formsMetaByHeader;
    if (Object.keys(hoverFormsMetaByHeader).length)
      result.senses_hover_form_meta_by_header = hoverFormsMetaByHeader;
    if (Object.keys(otherFormsMetaByHeader).length)
      result.senses_hover_other_form_meta_by_header = otherFormsMetaByHeader;
    if (best) applyFillRepresentativeEntry(result, best, false);
    setAtomicRenderEntries(result, allEntries, hoverEntries, otherEntries);
    attachWiktForms(result, dictHead, hoverEntries.length ? hoverEntries : allEntries);
  } else {
    result = {
      text: token,
      token_text: token,
      head: token,
      roman: '',
      pos: upos || 'unknown',
      meta_pos: fill && fill.has_known && !fill.has_unknown ? 'composite' : 'unknown',
      lemma: token,
      lemma_form: token,
      feats: '',
      senses: [],
      source: fill && fill.has_known && !fill.has_unknown ? 'COMPOSITE' : 'UNKNOWN',
      senses_hover: [],
      senses_hover_other: [],
      hover_has_alt_senses: false
    };
    attachWiktForms(result, token, []);
  }
  result.surface_form = token;
  result.dict_fill = rawFills;
  result.inspect_fill = rawFills;
  result.inspect_fill_count = rawFills.length;
  result.dict_fill_subwords = [];
  result.dict_fill_surface_slices = Array.isArray(fillSurfaceSlices) ? fillSurfaceSlices : [];
  result.dict_fill_mode = fillMode;
  result.dict_fill_has_known = hasKnownFill || !!(fill && fill.has_known);
  result.dict_fill_has_unknown = hasUnknownFill || !!(fill && fill.has_unknown);
  result.dict_fill_has_lemma_promotion = !!(fill && fill.has_lemma_promotion);
  result.resolved_via = resolvedVia;
  result.upos = upos;
  result.upos_label = upos;
  result.upos_color = coreState.UPOS_COLORS[upos] || '#d1d5db';
  result.tag = xpos;
  result.xpos = xpos;
  result.seg_i = 0;
  result._korean_compound_child_precomputed = true;
  var childPartIndex = parseInt(child.part_index, 10);
  result._korean_compound_part_index = isFinite(childPartIndex) ? childPartIndex : 0;
  result._korean_compound_child_internal_fill = rawFills.length > 1;
  result.resolution_actual = buildLiveResolutionInfo(
    surfaceLookup.resolution_meta || null,
    rawFills,
    exactLemmaMatchCount
  );
  result.resolution_live = result.resolution_actual;
  if (lemmaOverrideParts.length) result.lemma_override_parts = lemmaOverrideParts.slice();
  return result;
}
export function buildKoreanCompoundLemmaChildResults(childPayloads, engine, includeDebugTrace) {
  var children = Array.isArray(childPayloads) ? childPayloads : [];
  var out = [];
  for (var i = 0; i < children.length; i++) {
    var childResult = buildKoreanCompoundLemmaChildResult(children[i], engine, includeDebugTrace);
    if (!childResult) continue;
    out.push({
      text: String(children[i].text || childResult.text || '').trim(),
      source_text: String(children[i].source_text || children[i].text || childResult.text || '').trim(),
      part_index: isFinite(parseInt(children[i].part_index, 10)) ? parseInt(children[i].part_index, 10) : i,
      upos: String(children[i].upos || childResult.upos || '').trim(),
      xpos: String(children[i].xpos || childResult.xpos || '').trim(),
      lookup: childResult
    });
  }
  return out.length > 1 ? out : [];
}
export function extractTokenBySeg(lookupData) {
  var map = [];
  var udOverlay = (lookupData && lookupData.ud_overlay) || {};
  var tokens = Array.isArray(udOverlay.tokens) ? udOverlay.tokens : [];
  for (var i = 0; i < tokens.length; i++) {
    var tok = tokens[i] || {};
    var idx = Number(tok.i);
    if (!isFinite(idx) || idx < 0) continue;
    map[idx] = tok;
  }
  return map;
}
export function buildResultsBySeg(lookupData, engine, options) {
  options = options || {};
  var includeDebugTrace = !!options.debug_trace;
  var precomputedSurfaceLookups = Array.isArray(options.precomputed_surface_lookups)
    ? options.precomputed_surface_lookups
    : null;
  var segments = Array.isArray(lookupData && lookupData.segments) ? lookupData.segments : [];
  var originalText = String((lookupData && lookupData.display_text) || '');
  var segOffsets = Array.isArray(lookupData && lookupData.segment_offsets)
    ? lookupData.segment_offsets
    : null;
  var resultsBySeg = new Array(segments.length);
  var tokBySeg = extractTokenBySeg(lookupData);
  for (var i = 0; i < segments.length; i++) {
    var word = String(segments[i] || '');
    // Use original text slice for surface display when offsets are available
    var originalSlice = '';
    if (segOffsets && segOffsets[i] && originalText) {
      var oStart = Number(segOffsets[i][0]);
      var oEnd = Number(segOffsets[i][1]);
      if (isFinite(oStart) && isFinite(oEnd) && oStart >= 0 && oEnd <= originalText.length) {
        originalSlice = originalText.slice(oStart, oEnd);
      }
    }
    var surfaceWord = originalSlice || word;
    var tok = tokBySeg[i] || {};
    var surfaceAnchor = cloneSurfaceAnchor(tok.surface_anchor);
    if (!originalSlice && surfaceAnchor && surfaceAnchor.text) {
      surfaceWord = String(surfaceAnchor.text || word);
    }
    var upos = String(tok.upos || 'X');
    var deprel = String(tok.dep || 'dep');
    var xpos = String(tok.tag || '');
    var lemma = String(tok.lemma || '');
    var lemmaRaw = String(tok.lemma_raw || lemma || '');
    var lemmaSuffix = String(tok.lemma_suffix || '');
    var feats = String(tok.feats || '');
    if (!engine) {
      resultsBySeg[i] = buildUnknownResult(
        word,
        upos,
        xpos,
        deprel,
        lemma,
        feats,
        i,
        lemmaRaw,
        lemmaSuffix,
        surfaceWord,
        surfaceAnchor
      );
      continue;
    }

    // STAY AWAY DEAD CODE: active hybrid lookup precomputes surface lookups
    // in hybridSegmentAndHydrate() and passes them in via precomputed_surface_lookups.
    var surfaceLookup =
      precomputedSurfaceLookups && precomputedSurfaceLookups[i]
        ? precomputedSurfaceLookups[i]
        : buildSinglePassSurfaceLookup(word, lemma, engine, upos, xpos, includeDebugTrace, {
            skipWholeSurfaceExact: isMwtUdToken(tok),
            mwt_parts: Array.isArray(tok.mwt_parts) ? tok.mwt_parts : []
          });
    var lemmaHintObjects = surfaceLookup.lemma_hint_data.lemma_hint_objects;
    var exactEntries = surfaceLookup.exact_entries || [];
    var fill = surfaceLookup.fill || null;
    var allEntries = surfaceLookup.all_entries || [];
    var preferredEntries = surfaceLookup.preferred_entries || allEntries;
    var dictHead = String(surfaceLookup.dict_head || word);
    var lookupScoring = null;
    if (includeDebugTrace && surfaceLookup && typeof surfaceLookup._debug_lookup_scoring === 'object') {
      lookupScoring = {};
      for (var lookupKey in surfaceLookup._debug_lookup_scoring) {
        if (!Object.prototype.hasOwnProperty.call(surfaceLookup._debug_lookup_scoring, lookupKey)) continue;
        lookupScoring[lookupKey] = surfaceLookup._debug_lookup_scoring[lookupKey];
      }
    }
    var resolvedVia = String(surfaceLookup.resolved_via || 'surface');
    var lemmaOracleUsed = !!surfaceLookup.lemma_oracle_used;
    var lemmaOracleOutcome = String(surfaceLookup.lemma_oracle_outcome || '');
    var exactLemmaMatchCount = Number(surfaceLookup.exact_lemma_match_count || 0);
    var partialExactLemmaCount = Number(surfaceLookup.partial_exact_lemma_count || 0);
    var partialMissingLemmaCount = Number(surfaceLookup.partial_missing_lemma_count || 0);
    var partialGapCount = Number(surfaceLookup.partial_gap_count || 0);
    var lemmaOverrideParts = Array.isArray(surfaceLookup.lemma_override_parts)
      ? surfaceLookup.lemma_override_parts.slice()
      : [];
    var koCompoundLemmaChildren = buildKoreanCompoundLemmaChildResults(
      surfaceLookup.ko_compound_lemma_children,
      engine,
      includeDebugTrace
    );
    var preferredSenseFilterXpos = choosePreferredSenseFilterXpos(
      xpos,
      lemmaHintObjects,
      lemmaOverrideParts,
      engine
    );
    var chosenMain = chooseEntry(dictHead, preferredEntries || allEntries || [], engine);
    var hoverEntries = (allEntries || []).slice();
    var otherEntries = [];
    var entry;
    if (allEntries && allEntries.length) {
      var hoverSenses = [];
      var hoverOtherSenses = [];
      var formsMetaByHeader = buildJmdictFormsMetaByHeader(allEntries);
      var hoverFormsMetaByHeader = {};
      var otherFormsMetaByHeader = {};
      var entryFilterMode = String((fill && fill.mode) || '')
        .trim()
        .toLowerCase();
      var entryFilterKw = {};
      if (
        entryFilterMode === 'greedy' ||
        entryFilterMode === 'lemma_greedy' ||
        entryFilterMode === 'lemma_partial_greedy' ||
        entryFilterMode === 'greedy_lemma_mismatch'
      ) {
        entryFilterKw.greedy_match = true;
      }
      if (shouldApplyStrictExactLemmaDisplayFilter(resolvedVia, exactLemmaMatchCount, preferredEntries)) {
        entryFilterKw.strict_exact_lemma_entries = preferredEntries.slice();
      }
      var split = splitEntriesForHover(allEntries, upos, engine, preferredSenseFilterXpos, entryFilterKw);
      hoverEntries = split[0];
      otherEntries = split[1];
      hoverSenses = mergeAllEntries(dictHead, hoverEntries);
      if (otherEntries.length) hoverOtherSenses = mergeAllEntries(dictHead, otherEntries);
      hoverFormsMetaByHeader = buildJmdictFormsMetaByHeader(hoverEntries);
      if (otherEntries.length) otherFormsMetaByHeader = buildJmdictFormsMetaByHeader(otherEntries);
      var mergedSenses = mergeAllEntries(dictHead, allEntries);
      var best = chosenMain || allEntries[0];
      var roman = getEntryDisplayReading(best);
      entry = {
        head: dictHead,
        roman: roman,
        pos: upos,
        meta_pos: upos,
        senses: mergedSenses,
        source: 'DICT',
        senses_hover: hoverSenses,
        senses_hover_other: hoverOtherSenses,
        hover_has_alt_senses: !!hoverOtherSenses.length
      };
      if (Object.keys(formsMetaByHeader).length) entry.senses_form_meta_by_header = formsMetaByHeader;
      if (Object.keys(hoverFormsMetaByHeader).length)
        entry.senses_hover_form_meta_by_header = hoverFormsMetaByHeader;
      if (Object.keys(otherFormsMetaByHeader).length)
        entry.senses_hover_other_form_meta_by_header = otherFormsMetaByHeader;
    } else if (fill && fill.has_known && !fill.has_unknown) {
      entry = {
        head: word,
        roman: '',
        pos: upos,
        meta_pos: 'composite',
        senses: [],
        source: 'COMPOSITE',
        senses_hover: [],
        senses_hover_other: [],
        hover_has_alt_senses: false
      };
    } else {
      entry = {
        head: word,
        roman: '',
        pos: upos,
        meta_pos: 'unknown',
        senses: [],
        source: 'UNKNOWN',
        senses_hover: [],
        senses_hover_other: [],
        hover_has_alt_senses: false
      };
    }
    var primaryPool = hoverEntries.length ? hoverEntries : preferredEntries || allEntries || [];
    var primaryEntry =
      chooseEntry(dictHead, primaryPool, engine) || (primaryPool.length ? primaryPool[0] : null);
    if (primaryEntry) {
      applyFillRepresentativeEntry(entry, primaryEntry, false);
    }
    setAtomicRenderEntries(entry, allEntries, hoverEntries, otherEntries);
    entry.text = word;
    entry.token_text = word;
    entry.surface_form = surfaceWord;
    if (surfaceAnchor) entry.surface_anchor = surfaceAnchor;
    if (!entry.lemma_form && lemma) entry.lemma_form = lemma;
    if (lemmaRaw) entry.lemma_raw = lemmaRaw;
    if (lemmaSuffix) entry.lemma_suffix = lemmaSuffix;
    entry.resolved_via = resolvedVia;
    attachWiktForms(entry, dictHead, hoverEntries.length ? hoverEntries : allEntries || []);
    if (otherEntries.length) {
      var hoverTmp = {};
      attachWiktForms(hoverTmp, dictHead, hoverEntries || []);
      if (hoverTmp.entry_groups) entry.entry_groups_hover = hoverTmp.entry_groups;
      var otherTmp = {};
      attachWiktForms(otherTmp, dictHead, otherEntries || []);
      if (otherTmp.entry_groups) entry.entry_groups_other = otherTmp.entry_groups;
    }
    var fillPayload = buildLiveLookupFillPayload(
      surfaceWord,
      fill,
      lemma,
      upos,
      xpos,
      preferredSenseFilterXpos,
      engine,
      resolvedVia,
      Array.isArray(tok.mwt_parts) ? tok.mwt_parts : [],
      includeDebugTrace
    );
    var rawFills = fillPayload.rawFills;
    var fillMode = fillPayload.fillMode;
    var fillSurfaceSlices = fillPayload.fillSurfaceSlices;
    if (isPopupOnlySurfaceAnchorToken(word, surfaceWord, surfaceAnchor)) {
      fillSurfaceSlices = [];
    }
    entry.dict_fill = rawFills;
    entry.dict_fill_surface_slices = fillSurfaceSlices;
    entry.inspect_fill_count = rawFills.length;
    entry.dict_fill_mode = fillMode;
    entry.dict_fill_has_known = !!(fill && fill.has_known);
    entry.dict_fill_has_unknown = !!(fill && fill.has_unknown);
    entry.dict_fill_has_lemma_promotion = !!(fill && fill.has_lemma_promotion);
    entry.seg_i = i;
    entry.upos = upos;
    entry.upos_label = upos;
    entry.upos_color = coreState.UPOS_COLORS[upos] || '#d1d5db';
    entry.dep = deprel;
    entry.dep_label = deprel;
    entry.tag = xpos;
    entry.lemma = lemma;
    entry.feats = feats;
    if (Array.isArray(tok.mwt_parts) && tok.mwt_parts.length) entry.mwt_parts = tok.mwt_parts.slice();
    if (Array.isArray(surfaceLookup.mwt_child_resolutions) && surfaceLookup.mwt_child_resolutions.length) {
      entry.mwt_child_resolutions = surfaceLookup.mwt_child_resolutions.slice();
    }
    entry.lemma_oracle_used = lemmaOracleUsed;
    entry.lemma_oracle_outcome = lemmaOracleOutcome;
    entry.exact_lemma_match_count = exactLemmaMatchCount;
    if (partialExactLemmaCount > 0) entry.partial_exact_lemma_count = partialExactLemmaCount;
    if (partialMissingLemmaCount > 0) entry.partial_missing_lemma_count = partialMissingLemmaCount;
    if (partialGapCount > 0) entry.partial_gap_count = partialGapCount;
    if (lemmaOverrideParts.length) entry.lemma_override_parts = lemmaOverrideParts;
    if (koCompoundLemmaChildren.length) {
      entry.ko_compound_lemma_children = koCompoundLemmaChildren;
      entry.ko_compound_lemma_bypass_realignment = true;
    }
    entry.resolution_actual = buildLiveResolutionInfo(
      surfaceLookup.resolution_meta || null,
      rawFills,
      exactLemmaMatchCount
    );
    entry.resolution_live = entry.resolution_actual;
    if (includeDebugTrace) {
      if (
        surfaceLookup &&
        surfaceLookup._debug_runtime_lemma_alignment &&
        typeof surfaceLookup._debug_runtime_lemma_alignment === 'object'
      ) {
        entry._debug_runtime_lemma_alignment = surfaceLookup._debug_runtime_lemma_alignment;
      }
      var scoringPatch = {
        token: word,
        lemma_text: lemma,
        lemma_hints: buildDebugLemmaHintPreview(engine, rawFills, lemmaHintObjects),
        resolved_via: resolvedVia,
        outcome: lemmaOracleOutcome,
        fill_mode: fillMode,
        has_lemma_promotion: !!(fill && fill.has_lemma_promotion),
        lemma_override_parts: lemmaOverrideParts,
        lemma_oracle_used: lemmaOracleUsed,
        lemma_oracle_outcome: lemmaOracleOutcome,
        partial_exact_lemma_count: partialExactLemmaCount,
        partial_missing_lemma_count: partialMissingLemmaCount,
        partial_gap_count: partialGapCount,
        resolution_actual: entry.resolution_actual
      };
      if (entry._debug_runtime_lemma_alignment && typeof entry._debug_runtime_lemma_alignment === 'object') {
        scoringPatch.lemma_runtime_alignment = entry._debug_runtime_lemma_alignment;
      }
      if (!lookupScoring || typeof lookupScoring !== 'object') lookupScoring = {};
      for (var scoringKey in scoringPatch) {
        if (!Object.prototype.hasOwnProperty.call(scoringPatch, scoringKey)) continue;
        lookupScoring[scoringKey] = scoringPatch[scoringKey];
      }
      entry._debug_lookup_scoring = lookupScoring;
      if (fill && fill.dp_debug && typeof fill.dp_debug === 'object') {
        entry._debug_greedy_main = fill.dp_debug;
      }
    }
    resultsBySeg[i] = entry;
  }
  return resultsBySeg;
}
export function buildLookupDpOnlyPayload(word, engine, options) {
  options = options || {};
  var lemmaHint = String(options.lemma || '');
  var uposHint = String(options.upos || '')
    .trim()
    .toUpperCase();
  var xposHint = String(options.xpos || '').trim();
  var mwtParts = Array.isArray(options.mwt_parts) ? options.mwt_parts : [];
  if (!word || !String(word).trim())
    return {
      ok: false,
      error: 'empty'
    };
  if (!engine) {
    var unknown = buildUnknownResult(String(word), uposHint || 'unknown', xposHint, 'dep', lemmaHint, '', 0);
    unknown.pos = 'unknown';
    unknown.meta_pos = 'unknown';
    return {
      ok: true,
      display_text: String(word),
      q: String(word),
      segments: [String(word)],
      segment_offsets: [[0, String(word).length]],
      results: [unknown],
      results_by_seg: [unknown],
      grammar_overlay: {
        tokens: [],
        links: []
      },
      ud_overlay: {
        ok: false,
        tokens: [],
        edges: [],
        roots: [],
        ents: [],
        sentences: [],
        doc2seg: [],
        seg2doc: [-1],
        error: 'dp_only'
      }
    };
  }
  var token = String(word);
  // STAY AWAY DEAD CODE: active hybrid dp-only lookup precomputes the
  // surface lookup in hybridDpOnlyLookupWithEngine() and passes it here.
  var surfaceLookup =
    options.surface_lookup ||
    buildSinglePassSurfaceLookup(token, lemmaHint, engine, uposHint, xposHint, false, {
      skipWholeSurfaceExact: mwtParts.length > 1,
      mwt_parts: mwtParts
    });
  var fill = surfaceLookup.fill || null;
  var allEntries = surfaceLookup.all_entries || [];
  var preferredEntries = surfaceLookup.preferred_entries || allEntries;
  var dictHead = String(surfaceLookup.dict_head || token);
  var resolvedVia = String(surfaceLookup.resolved_via || 'surface');
  var dpLemmaHints =
    (surfaceLookup.lemma_hint_data && surfaceLookup.lemma_hint_data.lemma_hint_objects) || [];
  var lemmaOracleUsed = !!surfaceLookup.lemma_oracle_used;
  var lemmaOracleOutcome = String(surfaceLookup.lemma_oracle_outcome || '');
  var exactLemmaMatchCount = Number(surfaceLookup.exact_lemma_match_count || 0);
  var partialExactLemmaCount = Number(surfaceLookup.partial_exact_lemma_count || 0);
  var partialMissingLemmaCount = Number(surfaceLookup.partial_missing_lemma_count || 0);
  var partialGapCount = Number(surfaceLookup.partial_gap_count || 0);
  var lemmaOverrideParts = Array.isArray(surfaceLookup.lemma_override_parts)
    ? surfaceLookup.lemma_override_parts.slice()
    : [];
  var koCompoundLemmaChildren = buildKoreanCompoundLemmaChildResults(
    surfaceLookup.ko_compound_lemma_children,
    engine,
    false
  );
  var preferredSenseFilterXpos = choosePreferredSenseFilterXpos(
    xposHint,
    dpLemmaHints,
    lemmaOverrideParts,
    engine
  );
  var chosenMain = chooseEntry(dictHead, preferredEntries || allEntries || [], engine);
  var fillPayload = buildLiveLookupFillPayload(
    token,
    fill,
    lemmaHint,
    uposHint,
    xposHint,
    preferredSenseFilterXpos,
    engine,
    resolvedVia,
    mwtParts,
    false
  );
  var rawFills = fillPayload.rawFills;
  var fillMode = fillPayload.fillMode;
  var fillSurfaceSlices = fillPayload.fillSurfaceSlices;
  var result;
  if (allEntries && allEntries.length) {
    var best = null;
    var roman = getEntryDisplayReading(best);
    var mergedSenses = mergeAllEntries(dictHead, allEntries);
    var formsMetaByHeader = buildJmdictFormsMetaByHeader(allEntries);
    var hoverSenses = mergedSenses.slice();
    var hoverOtherSenses = [];
    var hoverFormsMetaByHeader = formsMetaByHeader;
    var otherFormsMetaByHeader = {};
    var hoverEntries = allEntries.slice();
    var otherEntries = [];
    var entryFilterKw = {};
    if (
      fillMode === 'greedy' ||
      fillMode === 'lemma_greedy' ||
      fillMode === 'lemma_partial_greedy' ||
      fillMode === 'greedy_lemma_mismatch'
    ) {
      entryFilterKw.greedy_match = true;
    }
    if (shouldApplyStrictExactLemmaDisplayFilter(resolvedVia, exactLemmaMatchCount, preferredEntries)) {
      entryFilterKw.strict_exact_lemma_entries = preferredEntries.slice();
    }
    {
      var split = splitEntriesForHover(
        allEntries,
        uposHint || '',
        engine,
        preferredSenseFilterXpos,
        entryFilterKw
      );
      hoverEntries = split[0];
      otherEntries = split[1];
      hoverSenses = mergeAllEntries(dictHead, hoverEntries);
      hoverFormsMetaByHeader = buildJmdictFormsMetaByHeader(hoverEntries);
    }
    var primaryPool = hoverEntries.length ? hoverEntries : preferredEntries || allEntries || [];
    best = chooseEntry(dictHead, primaryPool, engine) || (primaryPool.length ? primaryPool[0] : null);
    roman = getEntryDisplayReading(best);
    if (otherEntries && otherEntries.length) {
      hoverOtherSenses = mergeAllEntries(dictHead, otherEntries);
      otherFormsMetaByHeader = buildJmdictFormsMetaByHeader(otherEntries);
    }
    result = {
      text: token,
      head: dictHead,
      roman: roman,
      pos: uposHint || '',
      meta_pos: uposHint || '',
      lemma: lemmaHint || '',
      feats: '',
      senses: mergedSenses,
      source: 'DICT',
      dict_fill: rawFills,
      dict_fill_subwords: [],
      dict_fill_surface_slices: fillSurfaceSlices,
      inspect_fill: rawFills,
      dict_fill_mode: fillMode,
      dict_fill_has_known: !!(fill && fill.has_known),
      dict_fill_has_unknown: !!(fill && fill.has_unknown),
      seg_i: 0,
      surface_form: token,
      lemma_oracle_used: lemmaOracleUsed,
      lemma_oracle_outcome: lemmaOracleOutcome
    };
    if (mwtParts.length) result.mwt_parts = mwtParts.slice();
    if (Array.isArray(surfaceLookup.mwt_child_resolutions) && surfaceLookup.mwt_child_resolutions.length) {
      result.mwt_child_resolutions = surfaceLookup.mwt_child_resolutions.slice();
    }
    if (best) {
      applyFillRepresentativeEntry(result, best, false);
    }
    setAtomicRenderEntries(result, allEntries, hoverEntries, otherEntries);
    result.senses_hover = hoverSenses;
    result.senses_hover_other = hoverOtherSenses;
    result.hover_has_alt_senses = !!hoverOtherSenses.length;
    if (Object.keys(hoverFormsMetaByHeader).length)
      result.senses_hover_form_meta_by_header = hoverFormsMetaByHeader;
    if (Object.keys(otherFormsMetaByHeader).length)
      result.senses_hover_other_form_meta_by_header = otherFormsMetaByHeader;
    if (Object.keys(formsMetaByHeader).length) result.senses_form_meta_by_header = formsMetaByHeader;
    result.resolved_via = resolvedVia;
    if (resolvedVia === 'lemma_promoted' && !result.lemma_form) result.lemma_form = lemmaHint;
    result.dict_fill_has_lemma_promotion = !!(fill && fill.has_lemma_promotion);
    result.exact_lemma_match_count = exactLemmaMatchCount;
    if (partialExactLemmaCount > 0) result.partial_exact_lemma_count = partialExactLemmaCount;
    if (partialMissingLemmaCount > 0) result.partial_missing_lemma_count = partialMissingLemmaCount;
    if (partialGapCount > 0) result.partial_gap_count = partialGapCount;
    if (lemmaOverrideParts.length) result.lemma_override_parts = lemmaOverrideParts;
    if (koCompoundLemmaChildren.length) {
      result.ko_compound_lemma_children = koCompoundLemmaChildren;
      result.ko_compound_lemma_bypass_realignment = true;
    }
    result.resolution_actual = buildLiveResolutionInfo(
      surfaceLookup.resolution_meta || null,
      rawFills,
      exactLemmaMatchCount
    );
    result.resolution_live = result.resolution_actual;

    // Keep the primary render on the filtered primary entries; alternates
    // are already attached separately via senses_hover_other / entry_groups_other.
    attachWiktForms(result, dictHead, hoverEntries.length ? hoverEntries : allEntries);
    if (otherEntries.length) {
      var hoverTmp = {};
      attachWiktForms(hoverTmp, dictHead, hoverEntries || []);
      if (hoverTmp.entry_groups) result.entry_groups_hover = hoverTmp.entry_groups;
      var otherTmp = {};
      attachWiktForms(otherTmp, dictHead, otherEntries || []);
      if (otherTmp.entry_groups) result.entry_groups_other = otherTmp.entry_groups;
    }
  } else {
    result = {
      text: token,
      head: token,
      roman: '',
      pos: 'unknown',
      meta_pos: 'unknown',
      lemma: lemmaHint || '',
      feats: '',
      senses: [],
      source: 'UNKNOWN',
      dict_fill: rawFills,
      dict_fill_subwords: [],
      dict_fill_surface_slices: fillSurfaceSlices,
      inspect_fill: rawFills,
      dict_fill_mode: fillMode,
      dict_fill_has_known: !!(fill && fill.has_known),
      dict_fill_has_unknown: !!(fill && fill.has_unknown),
      seg_i: 0,
      surface_form: token,
      resolved_via: resolvedVia,
      lemma_oracle_used: lemmaOracleUsed,
      lemma_oracle_outcome: lemmaOracleOutcome,
      exact_lemma_match_count: exactLemmaMatchCount
    };
    if (mwtParts.length) result.mwt_parts = mwtParts.slice();
    if (Array.isArray(surfaceLookup.mwt_child_resolutions) && surfaceLookup.mwt_child_resolutions.length) {
      result.mwt_child_resolutions = surfaceLookup.mwt_child_resolutions.slice();
    }
    if (partialExactLemmaCount > 0) result.partial_exact_lemma_count = partialExactLemmaCount;
    if (partialMissingLemmaCount > 0) result.partial_missing_lemma_count = partialMissingLemmaCount;
    if (partialGapCount > 0) result.partial_gap_count = partialGapCount;
    if (lemmaOverrideParts.length) result.lemma_override_parts = lemmaOverrideParts;
    if (koCompoundLemmaChildren.length) {
      result.ko_compound_lemma_children = koCompoundLemmaChildren;
      result.ko_compound_lemma_bypass_realignment = true;
    }
    result.resolution_actual = buildLiveResolutionInfo(
      surfaceLookup.resolution_meta || null,
      rawFills,
      exactLemmaMatchCount
    );
    result.resolution_live = result.resolution_actual;
    attachWiktForms(result, token, allEntries || []);
  }
  return {
    ok: true,
    display_text: token,
    q: token,
    segments: [token],
    segment_offsets: [[0, token.length]],
    results: [result],
    results_by_seg: [result],
    grammar_overlay: {
      tokens: [],
      links: []
    },
    ud_overlay: {
      ok: false,
      tokens: mwtParts.length
        ? [
            {
              i: 0,
              doc_i: 0,
              text: token,
              upos: uposHint || 'X',
              tag: xposHint,
              dep: 'dep',
              lemma: lemmaHint || '',
              lemma_raw: lemmaHint || '',
              lemma_suffix: '',
              feats: '',
              mwt_parts: mwtParts.slice()
            }
          ]
        : [],
      edges: [],
      roots: [],
      ents: [],
      sentences: [],
      doc2seg: [],
      seg2doc: [-1],
      error: 'dp_only'
    }
  };
}
