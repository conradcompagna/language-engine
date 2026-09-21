import {
  buildResolutionMeta,
  buildResolutionRouteStep,
  isKoreanLanguageCode,
  splitCompoundTags
} from './alignment-inputs.mjs';
import {
  getCurrentLanguage,
  isPersianLanguageCode,
  normalizeLookupKey,
  normalizeVisibleComparisonText,
  splitCompoundLemma,
  splitPersianLemmaVariants
} from './core.mjs';
import { coreState } from './core.state.mjs';
import { getEntryDisplayHeadword, pushUniqueBundledEntry } from './entry-adapters.mjs';
import {
  buildDirectLemmaHintMappingState,
  buildFillPieceFromEntry,
  buildFillResult,
  buildKoreanCompoundLemmaChildLookupPayloads,
  buildKoreanCompoundLemmaSurfaceAnchorFill,
  buildLemmaHintAlignmentState,
  buildLemmaHintLookupPart,
  buildLemmaOverrideResultFromState,
  cloneMwtChildPieceRow,
  collectWholeTokenExactLemmaEntries,
  dedupeEntriesByIdentity,
  shouldBypassKoreanCompoundLemmaRealignment
} from './hydration.mjs';
import { surfaceLookupState } from './surface-lookup.state.mjs';
export // For MWT children the entire child surface is one atomic unit — the lemma
// maps onto [0, surface.length] with no alignment needed. This skips
// buildGenericSurfacePartAlignment (Needleman-Wunsch) entirely.
function buildMwtChildLemmaOverrideResult(
  surfaceText,
  lemmaHintObjects,
  engine,
  upos,
  xpos,
  includeDebugTrace
) {
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
  if (!parts.length || exactPartCount <= 0) return null;

  // Single group covering the entire child surface — no alignment required.
  var state = {
    surface: surface,
    parts: parts,
    alignment_groups: [
      {
        start: 0,
        end: surface.length,
        part_ids: parts.map(function (_, idx) {
          return idx;
        })
      }
    ],
    runtime_alignment_debug: includeDebugTrace
      ? {
          match_basis: 'mwt_child_direct'
        }
      : null,
    exact_part_count: exactPartCount,
    total_part_count: parts.length
  };
  return buildLemmaOverrideResultFromState(state, engine, upos, xpos, includeDebugTrace);
}
export function buildAlignedLemmaOverrideResult(
  surfaceText,
  lemmaHintObjects,
  engine,
  upos,
  xpos,
  includeDebugTrace
) {
  var state = buildLemmaHintAlignmentState(surfaceText, lemmaHintObjects, engine, includeDebugTrace);
  if (!state) return null;
  var usesExplicitMwtParts = !!(
    state.runtime_alignment_debug &&
    String(state.runtime_alignment_debug.match_basis || '')
      .trim()
      .toLowerCase() === 'mwt_parts'
  );
  if (state.exact_part_count <= 0 && !usesExplicitMwtParts) return null;
  if (
    state.exact_part_count < state.total_part_count &&
    !coreState.ENABLE_PARTIAL_EXACT_LEMMA_GAP_FILL &&
    !usesExplicitMwtParts
  )
    return null;
  return buildLemmaOverrideResultFromState(state, engine, upos, xpos, includeDebugTrace);
}
export function buildDirectLemmaOverrideResult(
  surfaceText,
  lemmaHintObjects,
  engine,
  upos,
  xpos,
  includeDebugTrace
) {
  var state = buildDirectLemmaHintMappingState(surfaceText, lemmaHintObjects, engine, includeDebugTrace);
  if (!state) return null;
  return buildLemmaOverrideResultFromState(state, engine, upos, xpos, includeDebugTrace);
}
export function collectFillEntries(fill) {
  var out = [];
  var rows = fill && fill.fills ? fill.fills : [];
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    if (String(row.source || '').toUpperCase() === 'UNKNOWN') continue;
    var entries = Array.isArray(row.entries) ? row.entries : [];
    for (var j = 0; j < entries.length; j++) out.push(entries[j]);
  }
  return out;
}
export function collectPromotedFillEntries(fill) {
  var out = [];
  var rows = fill && fill.fills ? fill.fills : [];
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    if (!row._lemma_promoted) continue;
    var entries = Array.isArray(row.entries) ? row.entries : [];
    for (var j = 0; j < entries.length; j++) out.push(entries[j]);
  }
  return out;
}
export function buildLemmaHintData(surfaceText, lemmaText, engine, upos, xpos, options) {
  var hintOptions = options || {};
  var surfaceValue = String(surfaceText || '').trim();
  var lemmaValue = String(lemmaText || '').trim();
  var lang = String((engine && engine._lang_code) || getCurrentLanguage() || '')
    .trim()
    .toLowerCase();
  var mwtParts = Array.isArray(hintOptions.mwt_parts) ? hintOptions.mwt_parts : [];
  if (mwtParts.length > 1) {
    var mwtHintObjects = [];
    var mwtLemmaDiffersFromSurface = false;
    var mwtAborted = false;
    for (var mi = 0; mi < mwtParts.length; mi++) {
      var mwtPart = mwtParts[mi] || {};
      var mwtSurfaceText = String(mwtPart.text || '');
      var mwtLemmaText = String(mwtPart.lemma || mwtPart.text || '').trim();
      if (!mwtSurfaceText) {
        mwtAborted = true;
        break;
      }
      if (!mwtLemmaText) mwtLemmaText = mwtSurfaceText;
      var mwtLemmaEqualsSurface =
        normalizeVisibleComparisonText(mwtLemmaText) === normalizeVisibleComparisonText(mwtSurfaceText);
      if (!mwtLemmaEqualsSurface) {
        mwtLemmaDiffersFromSurface = true;
      }
      // Every MWT child always gets a hint object so its Trankit surface_slice
      // is carried into alignment. When lemma == surface, we mark the hint as
      // ignored-for-segmentation so lemma-promotion logic skips it, but the
      // offsets must never be dropped.
      var mwtHint = {
        text: mwtLemmaText,
        surface_text: mwtSurfaceText,
        surface_slice: Array.isArray(mwtPart.surface_slice) ? mwtPart.surface_slice.slice(0, 2) : null,
        upos: String(mwtPart.upos || upos || '').trim(),
        xpos: String(mwtPart.tag || mwtPart.xpos || xpos || '').trim(),
        lemma_ignored_for_segmentation: mwtLemmaEqualsSurface
      };
      if (isPersianLanguageCode(lang)) {
        var mwtVariants = splitPersianLemmaVariants(mwtLemmaText);
        if (mwtVariants.length) mwtHint.variants = mwtVariants.slice();
      }
      mwtHintObjects.push(mwtHint);
    }
    if (!mwtAborted && mwtHintObjects.length > 1) {
      return {
        lemma_text: lemmaValue,
        lemma_differs_from_surface: mwtLemmaDiffersFromSurface,
        lemma_hint_parts_raw: mwtHintObjects.map(function (hint) {
          return hint ? String(hint.text || '').trim() : '';
        }),
        lemma_hint_objects: mwtHintObjects,
        hint_source: 'mwt_parts',
        mwt_has_slices: true
      };
    }
  }
  var differs =
    !!lemmaValue &&
    normalizeVisibleComparisonText(lemmaValue) !== normalizeVisibleComparisonText(surfaceValue);
  var rawParts = differs ? splitCompoundLemma(lemmaValue) : [];
  if (differs && !rawParts.length) rawParts = [lemmaValue];
  var uposParts = splitCompoundTags(upos);
  var xposParts = splitCompoundTags(xpos);
  var hasSplitUpos = uposParts.length === rawParts.length;
  var hasSplitXpos = xposParts.length === rawParts.length;
  var allowTokenLevelXposFallback = !isKoreanLanguageCode(lang);
  var hintObjects = rawParts.map(function (text, idx) {
    var hint = {
      text: text,
      upos: (hasSplitUpos ? uposParts[idx] : upos) || '',
      xpos: (hasSplitXpos ? xposParts[idx] : allowTokenLevelXposFallback ? xpos : '') || ''
    };
    if (isPersianLanguageCode(lang)) {
      var variants = splitPersianLemmaVariants(text);
      if (variants.length) hint.variants = variants.slice();
    }
    return hint;
  });
  return {
    lemma_text: lemmaValue,
    lemma_differs_from_surface: differs,
    lemma_hint_parts_raw: rawParts.slice(),
    lemma_hint_objects: hintObjects,
    hint_source: 'lemma_text'
  };
}
export function findLemmaHintMatchForEntry(entry, lemmaHintObjects, engine) {
  if (!entry || !lemmaHintObjects || !lemmaHintObjects.length) return null;
  var morphBase = entry.morph_base != null ? String(entry.morph_base) : '';
  var headword = String(
    entry.lemma_headword || entry.headword || getEntryDisplayHeadword(entry) || ''
  ).trim();
  var morphBaseKey = morphBase ? normalizeLookupKey(engine, morphBase) : '';
  var headwordKey = headword ? normalizeLookupKey(engine, headword) : '';
  for (var hi = 0; hi < lemmaHintObjects.length; hi++) {
    var rawHint = lemmaHintObjects[hi];
    var hintText = '';
    if (rawHint && typeof rawHint === 'object' && !Array.isArray(rawHint)) {
      if (rawHint.text != null) hintText = String(rawHint.text);
    } else if (rawHint != null) {
      hintText = String(rawHint);
    }
    if (!hintText) continue;
    var hintKey = normalizeLookupKey(engine, hintText);
    var morphMatches = morphBase
      ? morphBaseKey && hintKey
        ? morphBaseKey === hintKey
        : morphBase === hintText
      : false;
    var headwordMatches = headword
      ? headwordKey && hintKey
        ? headwordKey === hintKey
        : headword === hintText
      : false;
    if (!morphMatches && !headwordMatches) continue;
    return {
      text: hintText,
      source_text: hintText,
      upos: String((rawHint && rawHint.upos) || '').trim(),
      xpos: String((rawHint && rawHint.xpos) || '').trim()
    };
  }
  return null;
}
export function collectEntriesMatchingLemmaHints(entries, lemmaHintObjects, engine) {
  var matches = [];
  var matchedEntries = [];
  for (var i = 0; i < (entries || []).length; i++) {
    var entry = entries[i];
    var hintMatch = findLemmaHintMatchForEntry(entry, lemmaHintObjects, engine);
    if (!hintMatch) continue;
    matchedEntries.push(entry);
    matches.push({
      entry: entry,
      hint: hintMatch
    });
  }
  return {
    entries: matchedEntries,
    matches: matches
  };
}
export function isLemmaOverrideResolvedPath(resolvedVia) {
  var path = String(resolvedVia || '')
    .trim()
    .toLowerCase();
  return path === 'lemma_override' || path === 'lemma_partial_override';
}
export function shouldApplyStrictExactLemmaDisplayFilter(
  resolvedVia,
  exactLemmaMatchCount,
  preferredEntries
) {
  if (isLemmaOverrideResolvedPath(resolvedVia)) return false;
  if (
    String(resolvedVia || '')
      .trim()
      .toLowerCase() === 'lemma_promoted'
  ) {
    return Array.isArray(preferredEntries) && preferredEntries.length > 0;
  }
  var matchCount = parseInt(exactLemmaMatchCount, 10);
  if (!isFinite(matchCount) || matchCount <= 0) return false;
  return Array.isArray(preferredEntries) && preferredEntries.length > 0;
}
export function collectStrictLemmaEntriesForPromotedFillRow(entries, row, engine) {
  var fillEntries = Array.isArray(entries) ? entries : [];
  var fillRow = row && typeof row === 'object' ? row : null;
  if (!fillEntries.length || !fillRow) return [];
  if (fillRow._lemma_override || fillRow.lemma_override) return [];
  if (fillRow._lemma_promoted == null || fillRow._lemma_promoted === '') return [];
  var matchInfo = collectEntriesMatchingLemmaHints(
    fillEntries,
    [
      {
        text: String(fillRow._lemma_promoted),
        upos: String(fillRow._lemma_upos_hint || '').trim(),
        xpos: String(fillRow._lemma_xpos_hint || '').trim()
      }
    ],
    engine
  );
  return Array.isArray(matchInfo.entries) ? matchInfo.entries.slice() : [];
}
export function isWholeSurfaceKnownFill(fill, surfaceText) {
  if (!fill || !fill.has_known || fill.has_unknown) return false;
  var rows = Array.isArray(fill.fills) ? fill.fills : [];
  if (rows.length !== 1) return false;
  var row = rows[0] || {};
  if (String(row.source || '').toUpperCase() === 'UNKNOWN') return false;
  return String(row.text || row.head || '').trim() === String(surfaceText || '').trim();
}
export function annotateSingleFillLemmaPromotion(fill, matchRecord, mode, fallbackUpos, fallbackXpos) {
  if (!fill || !Array.isArray(fill.fills) || !fill.fills.length || !matchRecord) return fill;
  var row = fill.fills[0] || {};
  var entry = matchRecord.entry || {};
  var hint = matchRecord.hint || {};
  var lemmaText = String(hint.text || '').trim();
  if (!lemmaText) return fill;
  row._lemma_promoted = lemmaText;
  row._lemma_promoted_headword = String(entry.headword || '');
  row._lemma_promoted_pos = String(entry.pos_raw || entry.pos || '');
  var uposHint = String(hint.upos || fallbackUpos || '').trim();
  var xposHint = String(hint.xpos || fallbackXpos || '').trim();
  if (uposHint) row._lemma_upos_hint = uposHint;
  if (xposHint) row._lemma_xpos_hint = xposHint;
  fill.has_lemma_promotion = true;
  if (mode) fill.mode = String(mode);
  return fill;
}
export function isMwtUdToken(tok) {
  return !!(tok && typeof tok === 'object' && Array.isArray(tok.mwt_parts) && tok.mwt_parts.length > 1);
}

// Unicode categories that are "junk" — direct copy of gemini_dict.py _GLOSS_SKIP_CATEGORIES.
// If every character in a token falls into one of these categories the token has no lexical
// content and there is nothing to look up in the dictionary.
export function buildSinglePassSurfaceLookup(
  surfaceText,
  lemmaText,
  engine,
  upos,
  xpos,
  includeDebugTrace,
  options
) {
  var surface = String(surfaceText || '').trim();
  var lookupOpts = options || {};

  // Fast-path: purely punctuation / symbols / control chars — skip dictionary entirely.
  if (surface && !surfaceLookupState._hasLexicalContent(surface)) {
    return {
      exact_entries: [],
      fill: null,
      all_entries: [],
      preferred_entries: [],
      dict_head: surface,
      resolved_via: 'surface',
      lemma_hint_data: {
        lemma_hint_objects: [],
        lemma_differs_from_surface: false
      },
      lemma_oracle_used: false,
      lemma_oracle_outcome: 'punct_skip',
      exact_lemma_match_count: 0,
      resolution_meta: buildResolutionMeta(
        '',
        'punct_skip',
        [
          buildResolutionRouteStep(
            'punct_skip',
            'token is purely punctuation/symbols — skipped dictionary lookup'
          )
        ],
        'surface',
        'unknown',
        false,
        'punct_skip'
      )
    };
  }
  var skipWholeSurfaceExact = !!lookupOpts.skipWholeSurfaceExact;
  var mwtParts = Array.isArray(lookupOpts.mwt_parts) ? lookupOpts.mwt_parts : [];
  var isMwtToken = mwtParts.length > 1;
  var hintData = buildLemmaHintData(surface, lemmaText, engine, upos || '', xpos || '', lookupOpts);
  var lemmaHints = hintData.lemma_hint_objects;
  var lemmaOracleUsed = hintData.lemma_differs_from_surface && lemmaHints.length > 0;
  var koreanCompoundLemmaChildren = [];
  var skipKoreanCompoundLemmaRealignment = false;
  // For MWT tokens we must route through the slice-based direct mapping
  // regardless of whether any lemma differs from its child surface, because
  // Trankit offsets are the only authoritative source of child boundaries.
  var surfaceExactMissMessage = skipWholeSurfaceExact
    ? 'whole-token exact lookup skipped for MWT part-first mode'
    : 'surface exact lookup missed';
  var exactEntries = [];
  var surfaceExactEntries = [];
  var lemmaExactEntries = [];
  var exactMatchInfo = {
    entries: [],
    matches: []
  };
  var exactPreferredEntries = [];
  var fill = null;
  if (!skipWholeSurfaceExact && engine && typeof engine.lookup_all === 'function') {
    surfaceExactEntries = dedupeEntriesByIdentity(engine.lookup_all(surface) || [], surface);
    if (lemmaOracleUsed) {
      lemmaExactEntries = collectWholeTokenExactLemmaEntries(surface, lemmaHints, engine);
    }
    exactEntries = dedupeEntriesByIdentity(surfaceExactEntries.concat(lemmaExactEntries), surface);
    if (lemmaOracleUsed && exactEntries.length) {
      exactMatchInfo = collectEntriesMatchingLemmaHints(exactEntries, lemmaHints, engine);
    }
    exactPreferredEntries = exactMatchInfo.entries.length
      ? exactMatchInfo.entries.slice()
      : exactEntries.slice();
  }
  var routeSteps = [];
  var routeCode = '';
  var routeCategory = '';
  var outcome = '';
  if (exactEntries.length) {
    var exactLookupMatchedText = 'whole-token exact candidate pool matched';
    if (surfaceExactEntries.length && !lemmaExactEntries.length)
      exactLookupMatchedText = 'surface exact lookup matched';
    else if (!surfaceExactEntries.length && lemmaExactEntries.length)
      exactLookupMatchedText = 'lemma exact lookup matched';
    else if (surfaceExactEntries.length && lemmaExactEntries.length)
      exactLookupMatchedText = 'surface and lemma exact lookup matched';
    var exactMode = lemmaOracleUsed ? 'exact_lemma_checked' : 'exact';
    var exactResult = buildFillResult(surface, exactEntries, exactMode);
    var exactFill = exactResult.fill || {};
    var exactOutcome = lemmaOracleUsed ? 'exact_kept_after_lemma_check' : 'surface_exact';
    var exactFillMode = String((exactFill && exactFill.mode) || exactMode)
      .trim()
      .toLowerCase();
    if (lemmaOracleUsed && exactMatchInfo.matches.length) {
      annotateSingleFillLemmaPromotion(
        exactFill,
        exactMatchInfo.matches[0],
        'exact_lemma_promoted',
        upos,
        xpos
      );
      exactOutcome = 'exact_kept_with_lemma_promotion';
      exactFillMode = String((exactFill && exactFill.mode) || 'exact_lemma_promoted')
        .trim()
        .toLowerCase();
      return {
        exact_entries: exactEntries.slice(),
        fill: exactFill,
        all_entries: exactEntries.slice(),
        preferred_entries: exactPreferredEntries.slice(),
        dict_head: surface,
        resolved_via: 'surface',
        lemma_hint_data: hintData,
        lemma_oracle_used: true,
        lemma_oracle_outcome: exactOutcome,
        exact_lemma_match_count: exactMatchInfo.entries.length,
        resolution_meta: buildResolutionMeta(
          'exact_lemma_match',
          'surface_exact_lemma_match',
          [
            buildResolutionRouteStep('surface_exact_lookup', exactLookupMatchedText),
            buildResolutionRouteStep('lemma_check', 'lemma check found an underlying lemma match')
          ],
          'surface',
          exactFillMode,
          true,
          exactOutcome
        )
      };
    }
    var exactRouteSteps = [buildResolutionRouteStep('surface_exact_lookup', exactLookupMatchedText)];
    if (lemmaOracleUsed) {
      exactRouteSteps.push(
        buildResolutionRouteStep('lemma_check', 'lemma check kept the surface exact result')
      );
    }
    return {
      exact_entries: exactEntries.slice(),
      fill: exactFill,
      all_entries: exactEntries.slice(),
      preferred_entries: exactPreferredEntries.slice(),
      dict_head: surface,
      resolved_via: 'surface',
      lemma_hint_data: hintData,
      lemma_oracle_used: lemmaOracleUsed,
      lemma_oracle_outcome: exactOutcome,
      exact_lemma_match_count: exactMatchInfo.entries.length,
      resolution_meta: buildResolutionMeta(
        'exact_match',
        lemmaOracleUsed ? 'surface_exact_lemma_checked' : 'surface_exact',
        exactRouteSteps,
        'surface',
        exactFillMode,
        lemmaOracleUsed,
        exactOutcome
      )
    };
  }

  // MWT dispatch: just run the normal segmenter on each child independently,
  // then merge the children's fills with absolute offsets from surface_slice.
  // No MWT-specific segmenter logic, no parent-surface greedy.
  if (isMwtToken && engine) {
    var mergedChildFills = [];
    var mergedHasKnown = false;
    var mergedHasUnknown = false;
    var mergedHasLemmaPromotion = false;
    var mergedAllEntries = [];
    var mergedPreferredEntries = [];
    var childResultsOk = true;
    var childLemmaOverrideCount = 0; // children resolved via lemma override
    var childExactCount = 0; // children resolved via surface exact
    var childGreedyCount = 0; // children resolved via greedy
    var childResolutions = []; // per-child resolution category, in order
    for (var cpi = 0; cpi < mwtParts.length; cpi++) {
      var childPart = mwtParts[cpi] || {};
      var childSurfaceText = String(childPart.text || '');
      var childSliceArr = Array.isArray(childPart.surface_slice) ? childPart.surface_slice : null;
      if (!childSurfaceText || !childSliceArr || childSliceArr.length < 2) {
        childResultsOk = false;
        break;
      }
      var childSliceStart = parseInt(childSliceArr[0], 10);
      var childSliceEnd = parseInt(childSliceArr[1], 10);
      if (!isFinite(childSliceStart) || !isFinite(childSliceEnd)) {
        childResultsOk = false;
        break;
      }
      // Python-provided per-character lattice mapping child-local char index
      // → parent-relative surface offset. This is the sole substrate for
      // greedy-piece remapping; JS no longer does any char-aware alignment.
      var childCharMapRaw = Array.isArray(childPart.surface_char_map) ? childPart.surface_char_map : null;
      var childCharMap = null;
      if (childCharMapRaw && childCharMapRaw.length === childSurfaceText.length) {
        childCharMap = new Array(childCharMapRaw.length);
        var _cmOk = true;
        for (var _cmi = 0; _cmi < childCharMapRaw.length; _cmi++) {
          var _cmv = parseInt(childCharMapRaw[_cmi], 10);
          if (!isFinite(_cmv)) {
            _cmOk = false;
            break;
          }
          childCharMap[_cmi] = _cmv;
        }
        if (!_cmOk) childCharMap = null;
      }
      var childLemmaText = String(childPart.lemma || childPart.text || '');
      var childUpos = String(childPart.upos || '');
      var childXpos = String(childPart.tag || childPart.xpos || '');
      // Recursively run the normal (non-MWT) segmenter on the child.
      var childOptsForLookup = {};
      for (var ok in lookupOpts) {
        if (Object.prototype.hasOwnProperty.call(lookupOpts, ok)) childOptsForLookup[ok] = lookupOpts[ok];
      }
      childOptsForLookup.mwt_parts = [];
      childOptsForLookup.skipWholeSurfaceExact = false;
      // Tell the recursive call it is an MWT child: if the lemma differs
      // from the child surface, map the lemma directly onto [0, child.length]
      // instead of running Needleman-Wunsch alignment.
      childOptsForLookup.mwt_single_child = true;
      var childResult = buildSinglePassSurfaceLookup(
        childSurfaceText,
        childLemmaText,
        engine,
        childUpos,
        childXpos,
        includeDebugTrace,
        childOptsForLookup
      );
      if (!childResult) {
        childResultsOk = false;
        break;
      }
      // Tally per-child category to derive the aggregate resolution label.
      var childCat = String(
        (childResult.resolution_meta && childResult.resolution_meta.category) || ''
      ).toLowerCase();
      // For MWT children, disallow lemma_partial_override. Partial lemma matching only applies
      // to parent surface lookups. Children always have complete segmentation boundaries,
      // so partial lemma override becomes greedy (gaps filled greedily).
      if (childCat === 'lemma_partial_override') childCat = 'greedy_match';
      if (childCat === 'exact_match' || childCat === 'exact_lemma_match') childExactCount++;
      else if (childCat === 'lemma_override') childLemmaOverrideCount++;
      else childGreedyCount++;
      childResolutions.push(childCat || 'greedy_match');
      // Python has already produced the authoritative parent-relative
      // surface_slice for this child via _realign_mwt_children. JS does NOT
      // try to remap anything. One fill row per child, spanning the full
      // Python-allocated slice.
      //
      //   - exact / exact-lemma / lemma-override: ONE row with the child's
      //     single best entry (plus all_entries attached so hover shows
      //     alternates).
      //   - greedy (child got multiple pieces): ONE bundled row that
      //     aggregates ALL greedy pieces' entries. They hover together at
      //     the child's surface slice.
      var childAllEntries = Array.isArray(childResult.all_entries) ? childResult.all_entries : [];
      var childFillObj = childResult.fill;
      var childSurfaceSlice = surface.slice(childSliceStart, childSliceEnd);
      var childFillRows = childFillObj && Array.isArray(childFillObj.fills) ? childFillObj.fills : [];
      var childPreferredEntries = Array.isArray(childResult.preferred_entries)
        ? childResult.preferred_entries
        : [];
      var isGreedyChild =
        childCat !== 'exact_match' &&
        childCat !== 'exact_lemma_match' &&
        childCat !== 'lemma_override' &&
        childCat !== 'lemma_partial_override';
      var bundledRow;
      if (isGreedyChild && childFillRows.length > 0) {
        // Aggregate every greedy piece's entries into one bundled row.
        var bundledEntries = [];
        var seenEntryKeys = Object.create(null);
        for (var gfi = 0; gfi < childFillRows.length; gfi++) {
          var pieceRow = childFillRows[gfi] || {};
          var pieceEntries = Array.isArray(pieceRow.entries) ? pieceRow.entries : [];
          // Compact mode: fill pieces carry _winner_ref instead of entries array.
          if (!pieceEntries.length && pieceRow._winner_ref) {
            pieceEntries = [pieceRow._winner_ref];
          }
          for (var pei = 0; pei < pieceEntries.length; pei++) {
            pushUniqueBundledEntry(bundledEntries, seenEntryKeys, pieceEntries[pei]);
          }
        }
        // Also merge in whole-child all_entries as fallback.
        for (var cae = 0; cae < childAllEntries.length; cae++) {
          pushUniqueBundledEntry(bundledEntries, seenEntryKeys, childAllEntries[cae]);
        }
        if (bundledEntries.length) {
          bundledRow = buildFillPieceFromEntry(childSurfaceSlice, bundledEntries[0], bundledEntries);
          bundledRow.entries = bundledEntries.slice();

          // Force the bundled row to represent the full child slice, not the first piece
          bundledRow.text = childSurfaceSlice;
          bundledRow.head = childSurfaceSlice;
          bundledRow.headword = childSurfaceSlice;
          bundledRow.surface_form = childSurfaceSlice;

          // Preserve the original greedy child piece rows so we can remap them
          // back onto the authoritative child surface slice later.
          bundledRow._mwt_child_piece_rows = childFillRows.map(cloneMwtChildPieceRow);
          if (childCharMap) bundledRow._mwt_child_char_map = childCharMap.slice();
          mergedHasKnown = true;
        } else {
          bundledRow = {
            text: childSurfaceSlice,
            head: childSurfaceSlice,
            roman: '',
            senses: [],
            pos: '',
            source: 'UNKNOWN',
            entries: []
          };
          bundledRow._mwt_child_piece_rows = childFillRows.map(cloneMwtChildPieceRow);
          if (childCharMap) bundledRow._mwt_child_char_map = childCharMap.slice();
          mergedHasUnknown = true;
        }
      } else {
        // Exact / lemma path: single row using the child's best entry.
        var childBestEntries = childPreferredEntries.length ? childPreferredEntries : childAllEntries;
        if (childBestEntries.length) {
          bundledRow = buildFillPieceFromEntry(childSurfaceSlice, childBestEntries[0], childAllEntries);
          bundledRow.entries = childAllEntries.slice();
          mergedHasKnown = true;
        } else {
          bundledRow = {
            text: childSurfaceSlice,
            head: childSurfaceSlice,
            roman: '',
            senses: [],
            pos: '',
            source: 'UNKNOWN',
            entries: []
          };
          mergedHasUnknown = true;
        }
        // Propagate lemma-override flag so the golden border renders correctly.
        if (childCat === 'lemma_override' || childCat === 'lemma_partial_override') {
          bundledRow._lemma_override = true;
        }
      }
      bundledRow._surface_start = childSliceStart;
      bundledRow._surface_end = childSliceEnd;
      bundledRow._mwt_child_text = childSurfaceText;
      bundledRow._mwt_child_local_start = 0;
      bundledRow._mwt_child_local_end = childSurfaceText.length;
      bundledRow._mwt_part_index = cpi;
      bundledRow._mwt_child_resolution_category = childCat;
      if (childUpos) bundledRow._lemma_upos_hint = childUpos;
      if (childXpos) bundledRow._lemma_xpos_hint = childXpos;
      if (childFillObj && childFillObj.has_lemma_promotion) {
        bundledRow._lemma_promoted = true;
        mergedHasLemmaPromotion = true;
      }
      if (childFillObj && childFillObj.has_unknown) mergedHasUnknown = true;
      mergedChildFills.push(bundledRow);
      var childEntries = Array.isArray(childResult.all_entries) ? childResult.all_entries : [];
      for (var cei = 0; cei < childEntries.length; cei++) mergedAllEntries.push(childEntries[cei]);
      var childPreferred = Array.isArray(childResult.preferred_entries) ? childResult.preferred_entries : [];
      for (var cpei = 0; cpei < childPreferred.length; cpei++)
        mergedPreferredEntries.push(childPreferred[cpei]);
    }
    if (childResultsOk && mergedChildFills.length) {
      var totalChildren = mwtParts.length;
      // Derive a standard category from what the children actually resolved to.
      // Each child resolves independently, so the parent label reflects the mix.
      var mergedCategory;
      if (childExactCount === totalChildren) {
        mergedCategory = 'exact_match';
      } else if (childLemmaOverrideCount === totalChildren) {
        mergedCategory = 'lemma_override';
      } else if (childLemmaOverrideCount > 0 || mergedHasLemmaPromotion) {
        mergedCategory = 'lemma_partial_override';
      } else {
        mergedCategory = 'greedy_match';
      }
      var mergedFillObj = {
        mode: mergedHasLemmaPromotion ? 'mwt_lemma_promoted' : 'mwt_child',
        fills: mergedChildFills,
        has_known: mergedHasKnown,
        has_unknown: mergedHasUnknown,
        has_lemma_promotion: mergedHasLemmaPromotion
      };
      var mergedResolvedVia =
        childLemmaOverrideCount > 0 || mergedHasLemmaPromotion ? 'lemma_promoted' : 'surface';
      var mergedOutcome = mergedCategory;
      var routeDetail =
        'exact:' + childExactCount + ' lemma:' + childLemmaOverrideCount + ' greedy:' + childGreedyCount;
      return {
        exact_entries: [],
        fill: mergedFillObj,
        all_entries: mergedAllEntries.slice(),
        preferred_entries: (mergedPreferredEntries.length
          ? mergedPreferredEntries
          : mergedAllEntries
        ).slice(),
        dict_head: surface,
        resolved_via: mergedResolvedVia,
        lemma_hint_data: hintData,
        lemma_oracle_used: childLemmaOverrideCount > 0 || mergedHasLemmaPromotion || lemmaOracleUsed,
        lemma_oracle_outcome: mergedOutcome,
        exact_lemma_match_count: childLemmaOverrideCount,
        mwt_child_resolutions: childResolutions.slice(),
        resolution_meta: buildResolutionMeta(
          mergedCategory,
          'mwt_children_resolved_independently',
          [
            buildResolutionRouteStep('surface_exact_lookup', surfaceExactMissMessage),
            buildResolutionRouteStep(
              'mwt_children_independent',
              'MWT children resolved independently (' + routeDetail + ')'
            )
          ],
          mergedResolvedVia,
          mergedFillObj.mode,
          childLemmaOverrideCount > 0 || mergedHasLemmaPromotion || lemmaOracleUsed,
          mergedOutcome
        )
      };
    }
    // If we fail to produce any child fills, fall through to the generic
    // non-MWT path below — but it will be guarded against whole-surface
    // greedy since isMwtToken is still true.
  }
  if (lemmaOracleUsed) {
    var useDirectMwtLemmaMapping =
      String((hintData && hintData.hint_source) || '')
        .trim()
        .toLowerCase() === 'mwt_parts';
    var isMwtSingleChild = !!lookupOpts.mwt_single_child;
    skipKoreanCompoundLemmaRealignment = shouldBypassKoreanCompoundLemmaRealignment(
      surface,
      lemmaHints,
      engine,
      lookupOpts
    );
    if (skipKoreanCompoundLemmaRealignment) {
      koreanCompoundLemmaChildren = buildKoreanCompoundLemmaChildLookupPayloads(
        lemmaHints,
        engine,
        includeDebugTrace
      );
      if (!koreanCompoundLemmaChildren.length) skipKoreanCompoundLemmaRealignment = false;
    }
    if (!skipKoreanCompoundLemmaRealignment) {
      var alignedLemmaPartsResult = useDirectMwtLemmaMapping
        ? buildDirectLemmaOverrideResult(surface, lemmaHints, engine, upos, xpos, includeDebugTrace)
        : isMwtSingleChild
          ? buildMwtChildLemmaOverrideResult(surface, lemmaHints, engine, upos, xpos, includeDebugTrace)
          : buildAlignedLemmaOverrideResult(surface, lemmaHints, engine, upos, xpos, includeDebugTrace);
      var lemmaExactPartsStepText = useDirectMwtLemmaMapping
        ? 'lemma parts were mapped back to their Trankit MWT surface slices'
        : isMwtSingleChild
          ? 'MWT child lemma mapped directly onto child surface'
          : 'exact lemma parts were aligned onto the surface';
      var lemmaGapResolvedStepText = useDirectMwtLemmaMapping
        ? 'no uncovered spans remained after direct MWT slice mapping'
        : isMwtSingleChild
          ? 'MWT child lemma covered the entire child surface'
          : 'no uncovered spans remained after exact lemma-part alignment';
      var lemmaOverrideStepText = useDirectMwtLemmaMapping
        ? 'lemma exact-part mapping selected'
        : 'lemma exact-part alignment selected';
      if (alignedLemmaPartsResult) {
        var partialGapCount = Number(alignedLemmaPartsResult.partial_gap_count || 0);
        var partialExactCount = Number(alignedLemmaPartsResult.partial_exact_lemma_count || 0);
        var partialMissingCount = Number(alignedLemmaPartsResult.partial_missing_lemma_count || 0);
        var alignedResolvedVia = String(alignedLemmaPartsResult.resolved_via || '')
          .trim()
          .toLowerCase();
        alignedLemmaPartsResult.lemma_hint_data = hintData;
        if (alignedResolvedVia === 'lemma_partial_override') {
          alignedLemmaPartsResult.resolution_meta = buildResolutionMeta(
            useDirectMwtLemmaMapping ? 'mwt_lemma_partial_override' : 'lemma_partial_override',
            useDirectMwtLemmaMapping
              ? 'surface_no_match_then_mwt_partial_lemma_exact_then_gap_greedy'
              : 'surface_no_match_then_partial_lemma_exact_then_gap_greedy',
            partialGapCount > 0
              ? [
                  buildResolutionRouteStep('surface_exact_lookup', surfaceExactMissMessage),
                  buildResolutionRouteStep('lemma_exact_parts', lemmaExactPartsStepText),
                  buildResolutionRouteStep(
                    'lemma_gap_greedy',
                    'greedy DP filled the remaining uncovered spans'
                  )
                ]
              : [
                  buildResolutionRouteStep('surface_exact_lookup', surfaceExactMissMessage),
                  buildResolutionRouteStep('lemma_exact_parts', lemmaExactPartsStepText),
                  buildResolutionRouteStep('lemma_gap_greedy', lemmaGapResolvedStepText)
                ],
            'lemma_partial_override',
            String(
              (alignedLemmaPartsResult.fill && alignedLemmaPartsResult.fill.mode) || 'lemma_partial_greedy'
            )
              .trim()
              .toLowerCase(),
            true,
            String(
              alignedLemmaPartsResult.lemma_oracle_outcome ||
                (partialGapCount > 0 ? 'lemma_partial_exact_gaps' : 'lemma_partial_exact_only')
            )
              .trim()
              .toLowerCase(),
            {
              partial_exact_lemma_count: partialExactCount,
              partial_missing_lemma_count: partialMissingCount,
              partial_gap_count: partialGapCount,
              is_mwt: useDirectMwtLemmaMapping
            }
          );
        } else {
          alignedLemmaPartsResult.resolution_meta = buildResolutionMeta(
            useDirectMwtLemmaMapping ? 'mwt_lemma_override' : 'lemma_override',
            useDirectMwtLemmaMapping
              ? 'surface_no_match_then_mwt_lemma_exact_parts'
              : 'surface_no_match_then_lemma_exact_parts',
            [
              buildResolutionRouteStep('surface_exact_lookup', surfaceExactMissMessage),
              buildResolutionRouteStep('lemma_exact_parts', 'all lemma parts resolved by exact lookup'),
              buildResolutionRouteStep('lemma_override', lemmaOverrideStepText)
            ],
            'lemma_override',
            String((alignedLemmaPartsResult.fill && alignedLemmaPartsResult.fill.mode) || 'lemma_override')
              .trim()
              .toLowerCase(),
            true,
            'lemma_override_exact_parts',
            {
              is_mwt: useDirectMwtLemmaMapping
            }
          );
        }
        return alignedLemmaPartsResult;
      }
    }
  }

  // MWT tokens must never reach whole-surface greedy. If we're here with
  // an MWT token the child-loop above failed to produce any fills — that's
  // a hard error, not something to paper over. Return a no-match result
  // instead of greedily segmenting the parent surface.
  if (isMwtToken) {
    return {
      exact_entries: [],
      fill: null,
      all_entries: [],
      preferred_entries: [],
      dict_head: surface,
      resolved_via: 'surface',
      lemma_hint_data: hintData,
      lemma_oracle_used: lemmaOracleUsed,
      lemma_oracle_outcome: 'mwt_children_failed',
      exact_lemma_match_count: 0,
      resolution_meta: buildResolutionMeta(
        'no_match',
        'mwt_children_failed',
        [
          buildResolutionRouteStep(
            'mwt_children_independent',
            'per-child segmentation failed; refusing whole-surface greedy on MWT parent'
          )
        ],
        'surface',
        'none',
        lemmaOracleUsed,
        'mwt_children_failed'
      )
    };
  }
  var greedyFillOpts = {
    allowExact: false,
    excludeWhole: false,
    upos: upos || ''
  };
  if (skipKoreanCompoundLemmaRealignment && koreanCompoundLemmaChildren.length) {
    fill = buildKoreanCompoundLemmaSurfaceAnchorFill(surface);
  } else {
    if (includeDebugTrace) greedyFillOpts.debug = true;
    if (lemmaOracleUsed) greedyFillOpts.lemma_hints = lemmaHints.slice();
    fill = engine ? engine.fill_token(surface, greedyFillOpts) : null;
  }
  var allEntries = collectFillEntries(fill);
  var preferredEntries = collectPromotedFillEntries(fill);
  if (!preferredEntries.length) preferredEntries = allEntries.slice();
  var fillMode = String((fill && fill.mode) || 'greedy')
    .trim()
    .toLowerCase();
  var resolvedVia = fill && fill.has_lemma_promotion ? 'lemma_promoted' : 'surface';
  routeSteps = [];
  routeCode = '';
  routeCategory = '';
  outcome = '';
  if (skipKoreanCompoundLemmaRealignment && koreanCompoundLemmaChildren.length) {
    routeCategory = 'korean_compound_lemma_popup';
    routeCode = 'surface_no_match_then_korean_compound_lemma_popup';
    routeSteps.push(buildResolutionRouteStep('surface_exact_lookup', surfaceExactMissMessage));
    routeSteps.push(
      buildResolutionRouteStep(
        'korean_compound_lemma_popup',
        'compound lemma children precomputed; parent surface kept as a single popup anchor'
      )
    );
    outcome = 'korean_compound_lemma_popup';
  } else if (allEntries.length) {
    routeCategory = fill && fill.has_lemma_promotion ? 'lemma_promotion' : 'greedy_match';
    routeCode = fill && fill.has_lemma_promotion ? 'surface_greedy_lemma_promoted' : 'surface_greedy';
    routeSteps.push(buildResolutionRouteStep('surface_exact_lookup', surfaceExactMissMessage));
    routeSteps.push(
      buildResolutionRouteStep('surface_greedy', 'single-pass greedy DP selected the final fills')
    );
    if (fill && fill.has_lemma_promotion) {
      routeSteps.push(
        buildResolutionRouteStep('lemma_promotion', 'lemma-aware scoring promoted one or more chosen fills')
      );
    }
    outcome = fill && fill.has_lemma_promotion ? 'lemma_promoted' : 'surface_greedy';
  } else {
    routeCode = lemmaOracleUsed ? 'surface_no_match_after_lemma_check' : 'surface_no_match';
    routeSteps.push(buildResolutionRouteStep('surface_exact_lookup', surfaceExactMissMessage));
    routeSteps.push(
      buildResolutionRouteStep('surface_greedy', 'single-pass greedy DP found no known dictionary path')
    );
    outcome = lemmaOracleUsed ? 'no_lemma_match' : 'no_match';
  }
  var finalSurfaceResult = {
    exact_entries: exactEntries,
    fill: fill,
    all_entries: allEntries.slice(),
    preferred_entries: preferredEntries.slice(),
    dict_head: surface,
    resolved_via: resolvedVia,
    lemma_hint_data: hintData,
    lemma_oracle_used: lemmaOracleUsed,
    lemma_oracle_outcome: outcome,
    exact_lemma_match_count: 0,
    resolution_meta: buildResolutionMeta(
      routeCategory,
      routeCode,
      routeSteps,
      resolvedVia,
      fillMode,
      lemmaOracleUsed,
      outcome
    )
  };
  if (koreanCompoundLemmaChildren.length) {
    finalSurfaceResult.ko_compound_lemma_children = koreanCompoundLemmaChildren;
    finalSurfaceResult.ko_compound_lemma_bypass_realignment = true;
  }
  return finalSurfaceResult;
}
export function initializeSurfaceLookup() {
  surfaceLookupState._PUNCT_SKIP_CATEGORIES = (function () {
    var s = Object.create(null);
    var cats = [
      'Mn',
      'Mc',
      'Me',
      // Mark
      'Nd',
      'Nl',
      'No',
      // Number
      'Pc',
      'Pd',
      'Ps',
      'Pe',
      'Pi',
      'Pf',
      'Po',
      // Punctuation
      'Sm',
      'Sc',
      'Sk',
      'So',
      // Symbol
      'Zs',
      'Zl',
      'Zp',
      // Separator
      'Cc',
      'Cf',
      'Cs',
      'Co',
      'Cn' // Other / Control
    ];
    for (var i = 0; i < cats.length; i++) s[cats[i]] = true;
    return s;
  })();

  // Mirror of gemini_dict.py _is_glossable_token(): returns true if the string contains
  // at least one character whose Unicode general category is NOT in _PUNCT_SKIP_CATEGORIES.
  // Uses Intl.getCanonicalLocales-independent approach: iterate codepoints.
  // We leverage the ES2018 Unicode property escape \p{L}\p{M} to detect letter/mark chars;
  // if unavailable we fall back to checking each char via a regex built from the skip-set.
  surfaceLookupState._hasLexicalContent = (function () {
    // Try fast path: \p{L} (any letter) — covers Lu Ll Lt Lm Lo, i.e. every category
    // absent from _PUNCT_SKIP_CATEGORIES that carries lexical value.
    try {
      var _lexRe = new RegExp('[\\p{L}\\p{M}]', 'u');
      return function (str) {
        return str ? _lexRe.test(str) : false;
      };
    } catch (e) {
      // Fallback: iterate code-points and check each character's general category
      // using a two-char prefix lookup against the skip set.
      return function (str) {
        if (!str) return false;
        for (var i = 0; i < str.length; i++) {
          var cp = str.codePointAt(i);
          if (cp > 0xffff) i++; // surrogate pair — advance extra
          // We cannot get the Unicode category in plain ES5, so conservatively
          // assume any non-ASCII or ASCII letter has content.
          var ch = str[i];
          // ASCII printable non-symbol range: 0x41-0x5A (A-Z) 0x61-0x7A (a-z)
          var code = ch.charCodeAt(0);
          if ((code >= 0x41 && code <= 0x5a) || (code >= 0x61 && code <= 0x7a)) return true;
          // Non-ASCII: assume it has content (safe — we only skip on confirmed junk)
          if (code > 0x7e) return true;
        }
        return false;
      };
    }
  })();
  return true;
}
