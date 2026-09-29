import { buildResolutionMeta, buildResolutionRouteStep } from './alignment-inputs.mjs';
import { normalizeVisibleComparisonText } from './core.mjs';
import {
  chooseEntry,
  cleanMorphDisplayTags,
  cloneHydratedEntryForAggregation,
  getEntryDisplayHeadword,
  normalizeCanonicalEntryRuntime
} from './entry-adapters.mjs';
import { buildFillResult, dedupeEntriesByIdentity } from './hydration.mjs';
import { applyFillRepresentativeEntry } from './lookup-payloads.mjs';
import { buildDebugEntryRefs } from './result-merging.mjs';
import {
  annotateSingleFillLemmaPromotion,
  collectEntriesMatchingLemmaHints,
  collectFillEntries
} from './surface-lookup.mjs';
export function buildWinnerRefWireKey(ref) {
  if (!ref || !ref._winner_ref) return '';
  var alias = String(ref.db_alias || '').trim();
  var entryId = parseInt(ref.entry_row_id, 10) || 0;
  if (!alias || !(entryId > 0)) return '';
  var sk =
    String(ref.storage_kind || 'sqlite')
      .trim()
      .toLowerCase() || 'sqlite';
  var formId = parseInt(ref.form_row_id, 10) || 0;
  if (formId > 0) return sk + '|' + alias + '|' + entryId + '|' + formId;
  return sk + '|' + alias + '|' + entryId;
}
export function hydrateLookupEntry(entry, entryStore, refToKey, formOverlays) {
  if (!entry || typeof entry !== 'object') return null;
  var wireKey = buildWinnerRefWireKey(entry);
  if (wireKey) {
    var storeKey = refToKey ? refToKey[wireKey] : '';
    if (!storeKey || !entryStore || !entryStore[storeKey]) return null;
    var cloned = cloneHydratedEntryForAggregation(normalizeCanonicalEntryRuntime(entryStore[storeKey]));
    // Apply form-specific overlay if one exists for this wire key
    if (formOverlays && formOverlays[wireKey]) {
      var ov = formOverlays[wireKey];
      cloned.ref_key = wireKey;
      if (ov.display_headword) {
        cloned.display_headword = ov.display_headword;
        cloned.headword = ov.display_headword;
        cloned.surface_form = ov.display_headword;
        cloned.head = ov.display_headword;
      }
      if (ov.display_reading !== undefined) {
        cloned.display_reading = ov.display_reading;
        cloned.reading = ov.display_reading;
        cloned.roman = ov.display_reading;
      }
      if (ov.match_kind)
        cloned.match_kind = String(ov.match_kind || '')
          .trim()
          .toLowerCase();
      if (ov._match_kind)
        cloned._match_kind = String(ov._match_kind || '')
          .trim()
          .toLowerCase();
      else if (cloned.match_kind) cloned._match_kind = cloned.match_kind;
      if (ov._match_source)
        cloned._match_source = String(ov._match_source || '')
          .trim()
          .toLowerCase();
      else if (cloned._match_kind) cloned._match_source = cloned._match_kind;
      if (ov.morph_info) {
        var cleanedOverlayMorphInfo = ov.morph_info
          .map(function (value) {
            return cleanMorphDisplayTags(value);
          })
          .filter(Boolean);
        if (cleanedOverlayMorphInfo.length) cloned.morph_info = cleanedOverlayMorphInfo;
        else if (Object.prototype.hasOwnProperty.call(cloned, 'morph_info')) delete cloned.morph_info;
      }
      if (ov.morph_base) cloned.morph_base = ov.morph_base;
      if (ov.is_alternate_match !== undefined) cloned.is_alternate_match = ov.is_alternate_match;
      if (ov.matched_form) {
        cloned.matched_form = ov.matched_form;
        cloned._matched_forms = [ov.matched_form];
      }
      if (ov._storage_form_row_id) cloned._storage_form_row_id = ov._storage_form_row_id;
    }
    return cloned;
  }
  return cloneHydratedEntryForAggregation(normalizeCanonicalEntryRuntime(entry));
}
export function markNormalizedMatch(entry, surfaceText) {
  if (!entry || typeof entry !== 'object') return entry;
  var surface = String(surfaceText || '').trim();
  if (!surface) {
    if (Object.prototype.hasOwnProperty.call(entry, 'normalized_match')) delete entry.normalized_match;
    return entry;
  }
  var head = String(
    getEntryDisplayHeadword(entry) ||
      entry.headword ||
      entry.display_headword ||
      entry.surface_form ||
      entry.head ||
      ''
  ).trim();
  if (head && head !== surface) entry.normalized_match = true;
  else if (Object.prototype.hasOwnProperty.call(entry, 'normalized_match')) delete entry.normalized_match;
  return entry;
}
export function applyLemmaSurfaceDisplayFlip(entries, surfaceText) {
  var list = Array.isArray(entries) ? entries : [];
  var surface = String(surfaceText || '').trim();
  if (!surface) return list;
  var surfaceNorm = normalizeVisibleComparisonText(surface);
  for (var i = 0; i < list.length; i++) {
    var entry = list[i];
    if (!entry || typeof entry !== 'object') continue;
    var baseHead = String(entry.display_headword || entry.headword || '').trim();
    var baseNorm = normalizeVisibleComparisonText(baseHead);
    if (baseHead && surfaceNorm !== baseNorm) {
      entry.display_headword = surface;
      entry.headword = surface;
      entry.surface_form = surface;
      entry.head = surface;
      if (!entry.morph_base) entry.morph_base = baseHead;
      if (!entry.lemma_headword) entry.lemma_headword = baseHead;
      if (Object.prototype.hasOwnProperty.call(entry, 'normalized_match')) delete entry.normalized_match;
    } else {
      if (!entry.surface_form) entry.surface_form = surface;
      if (!entry.head) entry.head = surface;
    }
  }
  return list;
}
export function hydrateLookupEntries(entries, entryStore, refToKey, surfaceText, formOverlays) {
  var out = [];
  var list = Array.isArray(entries) ? entries : [];
  for (var i = 0; i < list.length; i++) {
    var hydrated = hydrateLookupEntry(list[i], entryStore, refToKey, formOverlays);
    if (hydrated) out.push(hydrated);
  }
  out = dedupeEntriesByIdentity(out, surfaceText);
  for (var j = 0; j < out.length; j++) {
    markNormalizedMatch(out[j], surfaceText);
  }
  return out;
}
export function hydrateLookupFill(fill, entryStore, refToKey, engine, formOverlays) {
  var src = fill && typeof fill === 'object' ? fill : {};
  var out = {};
  for (var key in src) {
    if (Object.prototype.hasOwnProperty.call(src, key) && key !== 'fills') out[key] = src[key];
  }
  var rows = Array.isArray(src.fills) ? src.fills : [];
  out.fills = [];
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    if (!row || typeof row !== 'object') {
      out.fills.push(row);
      continue;
    }
    var clone = {};
    for (var rowKey in row) {
      if (Object.prototype.hasOwnProperty.call(row, rowKey)) clone[rowKey] = row[rowKey];
    }
    var fillSurface = String(row.head || row.text || '').trim();
    var hydratedEntries = hydrateLookupEntries(row.entries, entryStore, refToKey, fillSurface, formOverlays);
    if (!hydratedEntries.length && row._winner_ref) {
      var singleHydrated = hydrateLookupEntry(row._winner_ref, entryStore, refToKey, formOverlays);
      if (singleHydrated) hydratedEntries = [markNormalizedMatch(singleHydrated, fillSurface)];
    }
    clone.entries = hydratedEntries;

    // Decomps are keyed by the actual visible surface form — ALWAYS, not
    // just on lemma override. Stamp every hydrated entry with the surface
    // the user is looking at so the popup stores/retrieves the decomp under
    // that exact spelling (headword, forms-row variant, or OOV inflection).
    var _surfaceForDecomp = String(
      clone._mwt_child_text || clone.text || clone.head || fillSurface || ''
    ).trim();
    if (_surfaceForDecomp && hydratedEntries.length) {
      for (var _sfi = 0; _sfi < hydratedEntries.length; _sfi++) {
        var _sfe = hydratedEntries[_sfi];
        if (!_sfe) continue;
        _sfe._decomp_surface_form = _surfaceForDecomp;
      }
    }
    // Lemma override rows display the visible surface as the headword and
    // keep the underlying lemma/base in morph_base for reader_wikt.js.
    if (clone._lemma_override && hydratedEntries.length && _surfaceForDecomp) {
      applyLemmaSurfaceDisplayFlip(hydratedEntries, _surfaceForDecomp);
    }
    if (hydratedEntries.length) {
      var chosen = chooseEntry(String(clone.head || clone.text || ''), hydratedEntries, engine);
      if (chosen) applyFillRepresentativeEntry(clone, chosen, false);
    }

    // Also hydrate MWT child piece rows if present
    if (Array.isArray(clone._mwt_child_piece_rows) && clone._mwt_child_piece_rows.length) {
      var hydratedPieceRows = [];
      for (var pi = 0; pi < clone._mwt_child_piece_rows.length; pi++) {
        var pieceRow = clone._mwt_child_piece_rows[pi];
        if (!pieceRow || typeof pieceRow !== 'object') {
          hydratedPieceRows.push(pieceRow);
          continue;
        }
        var pieceClone = {};
        for (var pieceKey in pieceRow) {
          if (Object.prototype.hasOwnProperty.call(pieceRow, pieceKey))
            pieceClone[pieceKey] = pieceRow[pieceKey];
        }
        var pieceSurface = String(pieceRow.head || pieceRow.text || '').trim();
        var hydratedPieceEntries = hydrateLookupEntries(
          pieceRow.entries,
          entryStore,
          refToKey,
          pieceSurface,
          formOverlays
        );
        if (!hydratedPieceEntries.length && pieceRow._winner_ref) {
          var singlePieceHydrated = hydrateLookupEntry(
            pieceRow._winner_ref,
            entryStore,
            refToKey,
            formOverlays
          );
          if (singlePieceHydrated)
            hydratedPieceEntries = [markNormalizedMatch(singlePieceHydrated, pieceSurface)];
        }
        pieceClone.entries = hydratedPieceEntries;
        hydratedPieceRows.push(pieceClone);
      }
      clone._mwt_child_piece_rows = hydratedPieceRows;
    }
    out.fills.push(clone);
  }
  return out;
}
export function getHydratedLemmaHintObjectsForFillRow(row, lemmaHintObjects) {
  var hints = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
  if (!hints.length) return [];
  var partIndex = parseInt(row && row._mwt_part_index, 10);
  if (!isFinite(partIndex)) partIndex = parseInt(row && row._lemma_part_index, 10);
  if (isFinite(partIndex) && partIndex >= 0 && partIndex < hints.length) {
    return [hints[partIndex]];
  }
  return hints.slice();
}
export function recomputeHydratedLemmaMatchMetadata(surfaceLookup, engine) {
  var out = surfaceLookup && typeof surfaceLookup === 'object' ? surfaceLookup : null;
  if (!out) return out;
  var hintObjects =
    out.lemma_hint_data && Array.isArray(out.lemma_hint_data.lemma_hint_objects)
      ? out.lemma_hint_data.lemma_hint_objects
      : [];
  if (!hintObjects.length) return out;
  var meta = out.resolution_meta && typeof out.resolution_meta === 'object' ? out.resolution_meta : null;
  var category = String((meta && meta.category) || '')
    .trim()
    .toLowerCase();
  var resolvedVia =
    String(out.resolved_via || (meta && meta.resolved_via) || 'surface')
      .trim()
      .toLowerCase() || 'surface';
  var fillMode = String((out.fill && out.fill.mode) || (meta && meta.fill_mode) || '')
    .trim()
    .toLowerCase();
  var dictHead = String(out.dict_head || '').trim();
  if (Array.isArray(out.exact_entries) && out.exact_entries.length) {
    var exactMatchInfo = collectEntriesMatchingLemmaHints(out.exact_entries, hintObjects, engine);
    out.exact_lemma_match_count = exactMatchInfo.entries.length;
    if (exactMatchInfo.entries.length) {
      out.preferred_entries = exactMatchInfo.entries.slice();
      out.lemma_oracle_used = true;
      if (category === 'exact_match' || category === 'exact_lemma_match') {
        annotateSingleFillLemmaPromotion(out.fill, exactMatchInfo.matches[0], 'exact_lemma_promoted', '', '');
        out.lemma_oracle_outcome = 'exact_kept_with_lemma_promotion';
        out.resolution_meta = buildResolutionMeta(
          'exact_lemma_match',
          'surface_exact_lemma_match',
          [
            buildResolutionRouteStep('surface_exact_lookup', 'surface exact lookup matched'),
            buildResolutionRouteStep('lemma_check', 'lemma check found an underlying lemma match')
          ],
          resolvedVia || 'surface',
          String((out.fill && out.fill.mode) || fillMode || 'exact_lemma_promoted')
            .trim()
            .toLowerCase(),
          true,
          out.lemma_oracle_outcome
        );
        return out;
      }
    }
    if (!Array.isArray(out.preferred_entries) || !out.preferred_entries.length) {
      out.preferred_entries = out.exact_entries.slice();
    }
  }
  if (
    category === 'mwt_exact_parts' ||
    category === 'mwt_exact_partial_lemma_match' ||
    category === 'mwt_exact_lemma_match'
  ) {
    var rows = out.fill && Array.isArray(out.fill.fills) ? out.fill.fills : [];
    var matchedEntries = [];
    var matchedCount = 0;
    for (var ri = 0; ri < rows.length; ri++) {
      var row = rows[ri] || {};
      var rowEntries = Array.isArray(row.entries) ? row.entries : [];
      if (!rowEntries.length) continue;
      var rowHints = getHydratedLemmaHintObjectsForFillRow(row, hintObjects);
      if (!rowHints.length) continue;
      var rowMatchInfo = collectEntriesMatchingLemmaHints(rowEntries, rowHints, engine);
      if (!rowMatchInfo.matches.length) continue;
      annotateSingleFillLemmaPromotion(
        {
          fills: [row],
          has_known: true,
          has_unknown: false
        },
        rowMatchInfo.matches[0],
        'mwt_exact_lemma_promoted',
        String(row._lemma_upos_hint || ''),
        String(row._lemma_xpos_hint || '')
      );
      matchedCount += 1;
      for (var mei = 0; mei < rowMatchInfo.entries.length; mei++)
        matchedEntries.push(rowMatchInfo.entries[mei]);
    }
    out.exact_lemma_match_count = matchedCount;
    if (out.fill && typeof out.fill === 'object') {
      out.fill.has_lemma_promotion = matchedCount > 0;
    }
    if (matchedCount >= rows.length && matchedEntries.length) {
      out.preferred_entries = dedupeEntriesByIdentity(matchedEntries, dictHead);
      out.lemma_oracle_used = true;
      out.lemma_oracle_outcome = 'mwt_exact_parts_lemma_match';
      out.resolution_meta = buildResolutionMeta(
        'mwt_exact_lemma_match',
        'surface_no_match_then_mwt_exact_lemma_match',
        [
          buildResolutionRouteStep(
            'surface_exact_lookup',
            'whole-token exact lookup skipped for MWT part-first mode'
          ),
          buildResolutionRouteStep(
            'mwt_exact_parts',
            'Trankit MWT subword surface forms matched by exact lookup'
          ),
          buildResolutionRouteStep('lemma_check', 'lemma check found an underlying MWT exact-part match')
        ],
        resolvedVia || 'surface',
        String((out.fill && out.fill.mode) || fillMode || 'mwt_exact')
          .trim()
          .toLowerCase(),
        true,
        out.lemma_oracle_outcome
      );
    } else if (matchedCount > 0 && matchedEntries.length) {
      out.preferred_entries = dedupeEntriesByIdentity(matchedEntries, dictHead);
      out.lemma_oracle_used = true;
      out.lemma_oracle_outcome = 'mwt_exact_parts_partial_lemma_match';
      out.resolution_meta = buildResolutionMeta(
        'mwt_exact_partial_lemma_match',
        'surface_no_match_then_mwt_exact_partial_lemma_match',
        [
          buildResolutionRouteStep(
            'surface_exact_lookup',
            'whole-token exact lookup skipped for MWT part-first mode'
          ),
          buildResolutionRouteStep(
            'mwt_exact_parts',
            'Trankit MWT subword surface forms matched by exact lookup'
          ),
          buildResolutionRouteStep('lemma_check', 'lemma check matched some but not all MWT exact parts')
        ],
        resolvedVia || 'surface',
        String((out.fill && out.fill.mode) || fillMode || 'mwt_exact')
          .trim()
          .toLowerCase(),
        true,
        out.lemma_oracle_outcome
      );
    } else if (category === 'mwt_exact_lemma_match' || category === 'mwt_exact_partial_lemma_match') {
      out.resolution_meta = buildResolutionMeta(
        'mwt_exact_parts',
        'surface_no_match_then_mwt_exact_parts',
        [
          buildResolutionRouteStep(
            'surface_exact_lookup',
            'whole-token exact lookup skipped for MWT part-first mode'
          ),
          buildResolutionRouteStep(
            'mwt_exact_parts',
            'Trankit MWT subword surface forms matched by exact lookup'
          )
        ],
        resolvedVia || 'surface',
        String((out.fill && out.fill.mode) || fillMode || 'mwt_exact')
          .trim()
          .toLowerCase(),
        !!out.lemma_oracle_used,
        'mwt_exact_parts'
      );
      out.lemma_oracle_outcome = 'mwt_exact_parts';
    } else if (!out.lemma_oracle_outcome) {
      out.lemma_oracle_outcome = 'mwt_exact_parts';
    }
  }
  return out;
}
export function hydrateKoreanCompoundLemmaChildLookups(children, entryStore, refToKey, engine, formOverlays) {
  var list = Array.isArray(children) ? children : [];
  var out = [];
  for (var i = 0; i < list.length; i++) {
    var child = list[i] && typeof list[i] === 'object' ? list[i] : null;
    if (!child) continue;
    var clone = {};
    for (var key in child) {
      if (!Object.prototype.hasOwnProperty.call(child, key) || key === 'lookup') continue;
      clone[key] = child[key];
    }
    clone.lookup = hydrateSinglePassLookup(child.lookup, entryStore, refToKey, engine, formOverlays);
    out.push(clone);
  }
  return out;
}
export function hydrateSinglePassLookup(surfaceLookup, entryStore, refToKey, engine, formOverlays) {
  var src = surfaceLookup && typeof surfaceLookup === 'object' ? surfaceLookup : {};
  var out = {};
  for (var key in src) {
    if (
      Object.prototype.hasOwnProperty.call(src, key) &&
      key !== 'fill' &&
      key !== 'exact_entries' &&
      key !== 'all_entries' &&
      key !== 'preferred_entries'
    ) {
      out[key] = src[key];
    }
  }
  var dictHead = String(src.dict_head || '').trim();
  out.fill = hydrateLookupFill(src.fill, entryStore, refToKey, engine, formOverlays);
  out.exact_entries = hydrateLookupEntries(src.exact_entries, entryStore, refToKey, dictHead, formOverlays);
  out.all_entries = hydrateLookupEntries(src.all_entries, entryStore, refToKey, dictHead, formOverlays);
  if (!out.all_entries.length) out.all_entries = collectFillEntries(out.fill);
  out.preferred_entries = hydrateLookupEntries(
    src.preferred_entries,
    entryStore,
    refToKey,
    dictHead,
    formOverlays
  );
  if (!out.preferred_entries.length) out.preferred_entries = out.all_entries.slice();
  if (Array.isArray(src.ko_compound_lemma_children) && src.ko_compound_lemma_children.length) {
    out.ko_compound_lemma_children = hydrateKoreanCompoundLemmaChildLookups(
      src.ko_compound_lemma_children,
      entryStore,
      refToKey,
      engine,
      formOverlays
    );
  }
  return recomputeHydratedLemmaMatchMetadata(out, engine);
}
export function buildExactLookupDebugEvent(displayText, lookupText, lemmaHint, exactMode, entries, vetoInfo) {
  var list = Array.isArray(entries) ? entries : [];
  var info = vetoInfo || null;
  return {
    mode: String(exactMode || ''),
    display_text: String(displayText || lookupText || '').trim(),
    lookup_text: String(lookupText || '').trim(),
    lemma_text: String(lemmaHint || '').trim(),
    matched: !!list.length,
    vetoed: !!(info && info.vetoed),
    reason: info && info.vetoed ? String(info.reason || 'xpos_pos_mismatch') : '',
    xpos_tags: info && Array.isArray(info.xpos_tags) ? info.xpos_tags.slice() : [],
    allowed_pos: info && Array.isArray(info.allowed_pos) ? info.allowed_pos.slice() : [],
    entry_refs: buildDebugEntryRefs(list)
  };
}
export function pushLookupDebugEvent(options, event) {
  var opts = options || {};
  var store = opts._debug_lookup_events;
  var label = String(opts._debug_lookup_label || '').trim();
  if (!store || !label || !event || typeof event !== 'object') return;
  if (!Array.isArray(store[label])) store[label] = [];
  store[label].push(event);
}
export function resolveExactThenGreedy(
  displayText,
  lookupText,
  engine,
  upos,
  exactMode,
  greedyMode,
  lemmaHint,
  xposHint,
  options
) {
  options = options || {};
  var includeDebugTrace = !!options.debug_trace;
  var query = String(lookupText || '').trim();
  if (!query) return null;
  var entries = engine.lookup_all(query) || [];
  if (entries.length) {
    var exactVetoInfo = null;
    if (includeDebugTrace) {
      pushLookupDebugEvent(
        options,
        buildExactLookupDebugEvent(displayText || query, query, lemmaHint, exactMode, entries, exactVetoInfo)
      );
    }
    return buildFillResult(displayText || query, entries.slice(), exactMode);
  }
  var fillOpts = {
    allowExact: false,
    upos: upos || ''
  };
  if (includeDebugTrace) fillOpts.debug = true;
  var fill = engine.fill_token(query, fillOpts);
  if (fill && fill.has_known) {
    var allEntries = collectFillEntries(fill, engine);
    if (allEntries.length) {
      var fillOut = {};
      for (var k in fill) {
        if (Object.prototype.hasOwnProperty.call(fill, k)) fillOut[k] = fill[k];
      }
      fillOut.mode = greedyMode;
      return {
        entries: allEntries,
        fill: fillOut
      };
    }
  }
  return null;
}
