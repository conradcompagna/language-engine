import { documentShellState } from './document-shell.state.mjs';
import { _surfaceHasGlossableChar } from './gloss-entries.mjs';
import { getKoreanGlossLemmaParts, isKoreanCurrentLanguageForGloss } from './gloss-requests.mjs';
import { getHeadlineLemmaCueFillText } from './grammar-popup.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import {
  extractPanelEditGlosses,
  getDictSourceBadgeInfo,
  getEntryDisplayHead,
  getTrimmedDisplayText,
  hasDisplayText,
  hasSameVisibleComparisonText,
  isAggregateDictEntryContainer
} from './presentation.mjs';
import { displayDictEntry, isUnknownDictEntry } from './side-panel.mjs';
import { getTokenMapLemmaPartTexts } from './token-map.mjs';
export function extractPanelEditForms(entry) {
  if (!entry || typeof entry !== 'object') return [];
  if (entry.forms && typeof entry.forms === 'object' && Array.isArray(entry.forms.rows)) {
    return entry.forms.rows.map(function (form) {
      return [
        String((form && form[0]) || ''),
        String((form && form[1]) || ''),
        String((form && form[2]) || '')
      ];
    });
  }
  var raw = entry._forms_raw || entry._forms_json || '';
  if (!raw) return [];
  try {
    var parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    var forms = [];
    for (var i = 0; i < parsed.length; i++) {
      var form = parsed[i];
      if (!Array.isArray(form)) continue;
      forms.push([String(form[0] || ''), String(form[1] || ''), String(form[2] || '')]);
    }
    return forms;
  } catch (_e) {
    return [];
  }
}
export function clonePanelEditSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== 'object') return null;
  var forms = [];
  var sourceForms = Array.isArray(snapshot.forms) ? snapshot.forms : [];
  for (var i = 0; i < sourceForms.length; i++) {
    var form = sourceForms[i];
    if (!Array.isArray(form)) continue;
    forms.push([String(form[0] || ''), String(form[1] || ''), String(form[2] || '')]);
  }
  return {
    entry_id: String(snapshot.entry_id || ''),
    entry_row_id: parseInt(snapshot.entry_row_id || 0, 10) || 0,
    storage_kind: String(snapshot.storage_kind || ''),
    db_alias: String(snapshot.db_alias || ''),
    headword: String(snapshot.headword || ''),
    romanization: String(snapshot.romanization || ''),
    pos: String(snapshot.pos || ''),
    glosses: Array.isArray(snapshot.glosses) ? snapshot.glosses.slice() : [],
    forms: forms,
    commentary: String(snapshot.commentary || ''),
    lemma: String(snapshot.lemma || ''),
    source: String(snapshot.source || ''),
    lang: String(snapshot.lang || '')
  };
}
export function getPanelEditEntryRowId(entry) {
  if (!entry || typeof entry !== 'object') return 0;
  var rowId = parseInt(entry._storage_row_id || entry.entry_row_id || entry.id || 0, 10) || 0;
  if (rowId > 0) return rowId;
  var runtimeId = String(entry.runtime_entry_id || entry.ref_key || '').trim();
  if (!runtimeId) return 0;
  var parts = runtimeId.split('|');
  if (parts.length < 3) return 0;
  return parseInt(parts[2] || 0, 10) || 0;
}
export function getPanelEditStorageKind(entry, sourceTag) {
  var explicit = String((entry && (entry._storage_kind || entry.storage_kind)) || '')
    .trim()
    .toLowerCase();
  if (explicit) return explicit;
  var source = String(sourceTag || '')
    .trim()
    .toLowerCase();
  if (source === 'gemini' || source === 'user_created') return 'custom';
  return '';
}
export function getPanelEditDbAlias(entry, sourceTag) {
  var explicit = String((entry && (entry._storage_db_alias || entry.db_alias)) || '').trim();
  if (explicit) return explicit;
  var source = String(sourceTag || '')
    .trim()
    .toLowerCase();
  if (source === 'gemini' || source === 'user_created') return 'customdb';
  return '';
}
export function getPanelEditEntrySourceTag(entry) {
  if (!entry || typeof entry !== 'object') return '';
  if (isAggregateDictEntryContainer(entry)) return '';
  var badgeInfo = getDictSourceBadgeInfo(entry);
  return String((badgeInfo && badgeInfo.source) || entry._source || entry.source || '')
    .trim()
    .toLowerCase();
}
export function getPanelEditSourceEntry(entry) {
  if (!entry || typeof entry !== 'object') return null;
  if (isAggregateDictEntryContainer(entry)) return null;
  if (
    entry.entry_id ||
    entry._glosses_raw ||
    entry._forms_raw ||
    entry._forms_json ||
    entry.forms ||
    entry._commentary ||
    entry._lemma ||
    entry.reading
  ) {
    return entry;
  }
  return null;
}
export function buildPanelEditSnapshot(entry, fallbackHeadText, requestLang) {
  var sourceEntry = getPanelEditSourceEntry(entry);
  if (!sourceEntry) return null;
  var badgeInfo = getDictSourceBadgeInfo(sourceEntry);
  var source = String((badgeInfo && badgeInfo.source) || sourceEntry._source || sourceEntry.source || '')
    .trim()
    .toLowerCase();
  if (source !== 'gemini' && source !== 'user_created') return null;
  var morphInfo = Array.isArray(sourceEntry.morph_info)
    ? sourceEntry.morph_info.join(', ')
    : String(sourceEntry.morph_info || '');
  var headword = String(
    sourceEntry.headword || getEntryDisplayHead(sourceEntry, fallbackHeadText) || fallbackHeadText || ''
  ).trim();
  var entryRowId = getPanelEditEntryRowId(sourceEntry);
  if (!headword) return null;
  return {
    entry_id: String(sourceEntry.entry_id || '').trim(),
    entry_row_id: entryRowId,
    storage_kind: getPanelEditStorageKind(sourceEntry, source),
    db_alias: getPanelEditDbAlias(sourceEntry, source),
    headword: headword,
    romanization: String(sourceEntry.reading || sourceEntry.roman || '').trim(),
    pos: String(sourceEntry.pos_raw || sourceEntry.pos || '').trim(),
    glosses: extractPanelEditGlosses(sourceEntry),
    forms: extractPanelEditForms(sourceEntry),
    commentary: String(sourceEntry._commentary || sourceEntry.commentary || morphInfo || '').trim(),
    lemma: String(
      sourceEntry._lemma || sourceEntry.lemma || sourceEntry.morph_base || sourceEntry.lemma_form || ''
    ).trim(),
    source: source,
    lang: String(requestLang || documentShellState.currentLanguage || '').trim()
  };
}
export function registerPanelEditContext(entry, fallbackHeadText, requestLang) {
  var snapshot = buildPanelEditSnapshot(entry, fallbackHeadText, requestLang);
  if (!snapshot) return null;
  var key = 'panel-edit-' + ++hoverLayoutState.currentPanelEditContextSeq;
  hoverLayoutState.currentPanelEditContextByKey[key] = {
    key: key,
    snapshot: clonePanelEditSnapshot(snapshot),
    liveEntry: entry,
    returnState: hoverLayoutState.currentPanelDisplayState
      ? {
          res: hoverLayoutState.currentPanelDisplayState.res,
          originalToken: hoverLayoutState.currentPanelDisplayState.originalToken,
          fullData: hoverLayoutState.currentPanelDisplayState.fullData
        }
      : null
  };
  return hoverLayoutState.currentPanelEditContextByKey[key];
}
export function restorePanelDisplayState(returnState) {
  var state = returnState && returnState.res ? returnState : hoverLayoutState.currentPanelDisplayState;
  if (!state || !state.res) return false;
  displayDictEntry(state.res, state.originalToken, state.fullData);
  return true;
}
export function applyEditPayloadToLiveEntry(liveEntry, entryPayload, source) {
  if (!liveEntry || typeof liveEntry !== 'object' || !entryPayload || typeof entryPayload !== 'object')
    return;
  var sourceTag =
    String(entryPayload.source || source || liveEntry._source || liveEntry.source || 'gemini')
      .trim()
      .toLowerCase() || 'gemini';
  var glosses = Array.isArray(entryPayload.glosses) ? entryPayload.glosses : [];
  var senses = glosses.map(function (g) {
    return {
      glosses: [String(g)]
    };
  });
  if (sourceTag === 'user_created')
    senses.push({
      _source: 'user_created'
    });
  if (entryPayload.entry_id) liveEntry.entry_id = String(entryPayload.entry_id || '');
  liveEntry.headword = String(entryPayload.headword || liveEntry.headword || '');
  liveEntry._source = sourceTag;
  liveEntry.reading = String(entryPayload.romanization || '');
  liveEntry.pos_raw = String(entryPayload.pos || '');
  liveEntry.pos = String(entryPayload.pos || '').toLowerCase();
  liveEntry._glosses_raw = JSON.stringify(senses);
  delete liveEntry.senses;
  delete liveEntry.senses_full;
  delete liveEntry._hydrated;
  var forms = Array.isArray(entryPayload.forms) ? entryPayload.forms : [];
  liveEntry._forms_raw = JSON.stringify(forms);
  liveEntry._forms_json = JSON.stringify(forms);
  if (entryPayload.commentary !== undefined) {
    liveEntry._commentary = String(entryPayload.commentary || '');
    if (liveEntry._commentary) liveEntry.morph_info = [liveEntry._commentary];
    else delete liveEntry.morph_info;
  }
  if (entryPayload.lemma !== undefined) {
    liveEntry._lemma = String(entryPayload.lemma || '');
    if (liveEntry._lemma) liveEntry.morph_base = liveEntry._lemma;
    else delete liveEntry.morph_base;
  }
}
export function hasExactTokenLookupMatch(entry, expectedText) {
  var expected = String(expectedText || '').trim();
  if (!entry || !expected) return false;
  var displayHead = String(getEntryDisplayHead(entry, '') || '').trim();
  if (displayHead && hasSameVisibleComparisonText(displayHead, expected)) return true;
  var dictFill = Array.isArray(entry.dict_fill) ? entry.dict_fill : [];
  for (var i = 0; i < dictFill.length; i++) {
    var fillHead = String(getEntryDisplayHead(dictFill[i], '') || '').trim();
    if (fillHead && hasSameVisibleComparisonText(fillHead, expected)) return true;
  }
  return false;
}
export function getCanonicalTokenEntry(data) {
  if (!data || typeof data !== 'object') return null;
  if (data.tokenEntry && typeof data.tokenEntry === 'object') return data.tokenEntry;
  if (data.entry && typeof data.entry === 'object') return data.entry;
  return null;
}
export function getDictionaryRuntimeApi() {
  return window.DictionaryClient && typeof window.DictionaryClient === 'object'
    ? window.DictionaryClient
    : null;
}
export function getDictionaryLookupApi() {
  var api = getDictionaryRuntimeApi();
  return api && typeof api.lookupSingle === 'function' ? api : null;
}
export function pushLookupEntryStore(entryStore, refToKey, formOverlays) {
  if (
    (!entryStore || typeof entryStore !== 'object') &&
    (!refToKey || typeof refToKey !== 'object') &&
    (!formOverlays || typeof formOverlays !== 'object')
  ) {
    return;
  }
  if (typeof window._wiktSetEntryStore === 'function') {
    window._wiktSetEntryStore(entryStore || null, refToKey || null, formOverlays || null);
  }
}
export function pushLookupResolverPayload(payload) {
  if (!payload || typeof payload !== 'object') return;
  pushLookupEntryStore(
    payload.entry_store && typeof payload.entry_store === 'object' ? payload.entry_store : null,
    payload.ref_to_key && typeof payload.ref_to_key === 'object' ? payload.ref_to_key : null,
    payload.form_overlays && typeof payload.form_overlays === 'object' ? payload.form_overlays : null
  );
}
export function mergeLookupResolverPayload(targetPayload, sourcePayload) {
  var target = targetPayload && typeof targetPayload === 'object' ? targetPayload : null;
  var source = sourcePayload && typeof sourcePayload === 'object' ? sourcePayload : null;
  if (!target || !source) return;
  var buckets = ['entry_store', 'ref_to_key', 'form_overlays'];
  for (var bi = 0; bi < buckets.length; bi++) {
    var bucket = buckets[bi];
    var src = source[bucket] && typeof source[bucket] === 'object' ? source[bucket] : null;
    if (!src) continue;
    if (!target[bucket] || typeof target[bucket] !== 'object') {
      target[bucket] = {};
    }
    var keys = Object.keys(src);
    for (var ki = 0; ki < keys.length; ki++) {
      target[bucket][keys[ki]] = src[keys[ki]];
    }
  }
}
export function lookupSingleDictionary(word, langCode, opts) {
  var api = getDictionaryLookupApi();
  if (!api || typeof api.lookupSingle !== 'function') {
    return Promise.reject(new Error('lookupSingle unavailable'));
  }
  return api.lookupSingle(word, langCode, opts || {}).then(function (payload) {
    pushLookupResolverPayload(payload);
    return payload;
  });
}
export function getLookupPayloadResults(payload) {
  var api = getDictionaryRuntimeApi();
  if (api && typeof api.getLookupResults === 'function') {
    return api.getLookupResults(payload);
  }
  if (payload && Array.isArray(payload.results_by_seg)) return payload.results_by_seg;
  if (payload && Array.isArray(payload.results)) return payload.results;
  return [];
}
export function getLookupPayloadPrimaryResult(payload) {
  var api = getDictionaryRuntimeApi();
  if (api && typeof api.getPrimaryLookupResult === 'function') {
    return api.getPrimaryLookupResult(payload);
  }
  var results = getLookupPayloadResults(payload);
  return results.length ? results[0] : null;
}
export function getLookupEntryResolution(entry) {
  var api = getDictionaryRuntimeApi();
  if (api && typeof api.getLookupResultResolution === 'function') {
    return api.getLookupResultResolution(entry);
  }
  if (entry && entry.resolution && typeof entry.resolution === 'object') return entry.resolution;
  if (entry && entry.resolution_actual && typeof entry.resolution_actual === 'object')
    return entry.resolution_actual;
  return null;
}
export function getLookupEntryFills(entry) {
  var api = getDictionaryRuntimeApi();
  if (api && typeof api.getLookupResultFills === 'function') {
    return api.getLookupResultFills(entry);
  }
  if (entry && Array.isArray(entry.fills)) return entry.fills;
  if (entry && Array.isArray(entry.dict_fill)) return entry.dict_fill;
  return [];
}
export function getLookupEntryResolvedVia(entry) {
  var resolution = getLookupEntryResolution(entry);
  if (resolution && resolution.resolved_via != null) {
    return String(resolution.resolved_via || '')
      .trim()
      .toLowerCase();
  }
  return String((entry && entry.resolved_via) || '')
    .trim()
    .toLowerCase();
}
export function getLookupEntryFillMode(entry) {
  var resolution = getLookupEntryResolution(entry);
  if (resolution && resolution.fill_mode != null) {
    return String(resolution.fill_mode || '')
      .trim()
      .toLowerCase();
  }
  return String((entry && entry.dict_fill_mode) || '')
    .trim()
    .toLowerCase();
}
export function getCanonicalTokenSurfaceText(data) {
  var entry = getCanonicalTokenEntry(data);
  if (entry && hasDisplayText(entry.surface_form)) return String(entry.surface_form);
  return String((data && data.surface) || '');
}
export function getCanonicalTokenLemmaInfo(data) {
  var entry = getCanonicalTokenEntry(data);
  var posData = (data && data.posData) || {};
  var udTok = (data && data.udTok) || {};
  var lemma = '';
  var lemmaRaw = '';
  var lemmaSuffix = '';
  if (entry && hasDisplayText(entry.lemma_form)) lemma = String(entry.lemma_form);
  if (!lemma && entry && hasDisplayText(entry.lemma)) lemma = String(entry.lemma);
  if (!lemma && data && hasDisplayText(data.lemma)) lemma = String(data.lemma);
  if (!lemma && hasDisplayText(posData.lemma)) lemma = String(posData.lemma);
  if (!lemma && hasDisplayText(udTok.lemma)) lemma = String(udTok.lemma);
  if (entry && hasDisplayText(entry.lemma_raw)) lemmaRaw = String(entry.lemma_raw);
  if (!lemmaRaw && data && hasDisplayText(data.lemma_raw)) lemmaRaw = String(data.lemma_raw);
  if (!lemmaRaw && hasDisplayText(posData.lemma_raw)) lemmaRaw = String(posData.lemma_raw);
  if (!lemmaRaw && hasDisplayText(udTok.lemma_raw)) lemmaRaw = String(udTok.lemma_raw);
  if (!lemmaRaw) lemmaRaw = lemma;
  if (entry && hasDisplayText(entry.lemma_suffix)) lemmaSuffix = String(entry.lemma_suffix);
  if (!lemmaSuffix && data && hasDisplayText(data.lemma_suffix)) lemmaSuffix = String(data.lemma_suffix);
  if (!lemmaSuffix && hasDisplayText(posData.lemma_suffix)) lemmaSuffix = String(posData.lemma_suffix);
  if (!lemmaSuffix && hasDisplayText(udTok.lemma_suffix)) lemmaSuffix = String(udTok.lemma_suffix);
  return {
    lemma: lemma,
    raw: lemmaRaw,
    suffix: lemmaSuffix
  };
}
export function getTokenBannerSurfaceText(data) {
  if (!data || typeof data !== 'object') return '';
  return getTokenMapAnchorText(data) || getTrimmedDisplayText(data.surface || '');
}
export function getTokenMapAnchorText(data) {
  if (!data || typeof data !== 'object') return '';
  var raw = String(data.anchorText || data.mwtSurfaceSlice || '').trim();
  if (!raw) {
    var udAnchor = getUdTokenSurfaceAnchor(data.udTok);
    if (udAnchor && udAnchor.text) raw = String(udAnchor.text || '').trim();
  }
  if (!raw && data.entry && data.entry.surface_anchor) {
    var entryAnchor = getUdTokenSurfaceAnchor({
      surface_anchor: data.entry.surface_anchor
    });
    if (entryAnchor && entryAnchor.text) raw = String(entryAnchor.text || '').trim();
  }
  if (!raw && data.tokenEntry && data.tokenEntry.surface_anchor) {
    var tokenEntryAnchor = getUdTokenSurfaceAnchor({
      surface_anchor: data.tokenEntry.surface_anchor
    });
    if (tokenEntryAnchor && tokenEntryAnchor.text) raw = String(tokenEntryAnchor.text || '').trim();
  }
  if (!raw) raw = String(data.surface || '').trim();
  return getTrimmedDisplayText(raw);
}
export function getTokenMapLookupText(data) {
  if (!data || typeof data !== 'object') return '';
  var raw = String(data.lookupText || data.mwtChildText || '').trim();
  if (!raw && data.entry && data.entry.text != null) raw = String(data.entry.text || '').trim();
  if (!raw && data.tokenEntry && data.tokenEntry.text != null)
    raw = String(data.tokenEntry.text || '').trim();
  if (!raw) raw = String(data.surface || '').trim();
  return getTrimmedDisplayText(raw);
}
export function getUdTokenSurfaceAnchor(udTok) {
  if (!udTok || typeof udTok !== 'object') return null;
  var anchor = udTok.surface_anchor;
  if (!anchor || typeof anchor !== 'object') return null;
  var rawSlice = Array.isArray(anchor.slice) ? anchor.slice : null;
  if (!rawSlice || rawSlice.length < 2) return null;
  var start = parseInt(rawSlice[0], 10);
  var end = parseInt(rawSlice[1], 10);
  if (!isFinite(start) || !isFinite(end) || end < start) return null;
  return {
    text: String(anchor.text || '').trim(),
    slice: [start, end]
  };
}
export function clearSurfaceAnchorMismatchAttrs(tokenEl) {
  if (!tokenEl || !tokenEl.dataset) return;
  delete tokenEl.dataset.mwtAnchor;
  delete tokenEl.dataset.mwtPartIndex;
  delete tokenEl.dataset.mwtMismatch;
  delete tokenEl.dataset.mwtChildText;
  delete tokenEl.dataset.mwtSurfaceSlice;
  delete tokenEl.dataset.mwtPopupReason;
  delete tokenEl.dataset.koCompoundLemmaSpawn;
  delete tokenEl.dataset.koCompoundLemmaParts;
}
export function applySurfaceAnchorMismatchAttrs(tokenEl, segText, udTok) {
  if (!tokenEl || !tokenEl.dataset) return false;
  var anchor = getUdTokenSurfaceAnchor(udTok);
  var childText = String((udTok && udTok.text) || segText || '').trim();
  var surfaceText = anchor ? String(anchor.text || '').trim() : '';
  if (!surfaceText || !childText || hasSameVisibleComparisonText(surfaceText, childText)) {
    clearSurfaceAnchorMismatchAttrs(tokenEl);
    return false;
  }
  tokenEl.dataset.mwtAnchor = '1';
  tokenEl.dataset.mwtPartIndex = '0';
  tokenEl.dataset.mwtMismatch = '1';
  tokenEl.dataset.mwtChildText = childText;
  tokenEl.dataset.mwtSurfaceSlice = surfaceText;
  tokenEl.dataset.mwtPopupReason = 'surface_anchor';
  return true;
}
export function isSurfaceAnchorPopupOnlyToken(segText, udTok) {
  var anchor = getUdTokenSurfaceAnchor(udTok);
  if (!anchor || !anchor.text) return false;
  var childText = String((udTok && udTok.text) || segText || '').trim();
  var surfaceText = String(anchor.text || '').trim();
  if (!childText || !surfaceText) return false;
  return !hasSameVisibleComparisonText(childText, surfaceText);
}
export function getPrecomputedKoreanCompoundLemmaChildren(resultEntry) {
  var entry = resultEntry && typeof resultEntry === 'object' ? resultEntry : null;
  var children =
    entry && Array.isArray(entry.ko_compound_lemma_children) ? entry.ko_compound_lemma_children : [];
  return children.length ? children : [];
}
export function getPrecomputedKoreanCompoundLemmaPartTexts(resultEntry) {
  var children = getPrecomputedKoreanCompoundLemmaChildren(resultEntry);
  var out = [];
  for (var i = 0; i < children.length; i++) {
    var child = children[i] || {};
    var text = String(child.text || (child.lookup && child.lookup.text) || '').trim();
    if (text) out.push(text);
  }
  return out.length > 1 ? out : [];
}
export function getKoreanCompoundLemmaSpawnParts(segText, resultEntry, udTok) {
  if (!isKoreanCurrentLanguageForGloss()) return [];
  var surfaceText = String(segText || '').trim();
  if (!surfaceText) return [];
  if (udTok && Array.isArray(udTok.mwt_parts) && udTok.mwt_parts.length) return [];
  var precomputedParts = getPrecomputedKoreanCompoundLemmaPartTexts(resultEntry);
  if (precomputedParts.length > 1 && !hasSameVisibleComparisonText(precomputedParts.join(''), surfaceText)) {
    return precomputedParts;
  }
  return [];
}
export function applyKoreanCompoundLemmaSpawnAttrs(tokenEl, segText, resultEntry, udTok) {
  if (!tokenEl || !tokenEl.dataset) return false;
  var parts = getKoreanCompoundLemmaSpawnParts(segText, resultEntry, udTok);
  if (!parts.length) {
    delete tokenEl.dataset.koCompoundLemmaSpawn;
    delete tokenEl.dataset.koCompoundLemmaParts;
    return false;
  }
  tokenEl.dataset.koCompoundLemmaSpawn = '1';
  tokenEl.dataset.koCompoundLemmaParts = JSON.stringify(parts);
  return true;
}
export function getMwtPartSurfaceSliceText(surfaceText, udTok, partIndex, fallbackText) {
  var surface = String(surfaceText || '').trim();
  var parsedPartIndex = parseInt(partIndex, 10);
  if (
    surface &&
    isFinite(parsedPartIndex) &&
    udTok &&
    Array.isArray(udTok.mwt_parts) &&
    udTok.mwt_parts[parsedPartIndex] &&
    Array.isArray(udTok.mwt_parts[parsedPartIndex].surface_slice) &&
    udTok.mwt_parts[parsedPartIndex].surface_slice.length >= 2
  ) {
    var rawSlice = udTok.mwt_parts[parsedPartIndex].surface_slice;
    var start = parseInt(rawSlice[0], 10);
    var end = parseInt(rawSlice[1], 10);
    if (isFinite(start) && isFinite(end) && end > start && end <= surface.length) {
      return surface.slice(start, end);
    }
  }
  if (parsedPartIndex === 0) {
    var surfaceAnchor = getUdTokenSurfaceAnchor(udTok);
    if (surfaceAnchor && surfaceAnchor.text) return surfaceAnchor.text;
  }
  return String(fallbackText || '').trim();
}
export function getOrderedLemmaOverridePartTexts(entry, fallbackSurface) {
  var e = entry && typeof entry === 'object' ? entry : null;
  if (!e) return [];
  var surfaceText = getTrimmedDisplayText(fallbackSurface || '');
  var overrideParts = Array.isArray(e.lemma_override_parts) ? e.lemma_override_parts : [];
  var out = [];
  if (overrideParts.length) {
    for (var pi = 0; pi < overrideParts.length; pi++) {
      var part = overrideParts[pi] || {};
      if (part.matched === false) continue;
      var partText = getTrimmedDisplayText(part.text || part.source_text || '');
      if (!partText) continue;
      out.push(partText);
    }
    if (out.length > 1) return out;
  }
  var fillEntries = Array.isArray(e.dict_fill) ? e.dict_fill : [];
  if (fillEntries.length) {
    var orderedRows = [];
    var hasKnownFill = false;
    var allKnownOverride = true;
    for (var fi = 0; fi < fillEntries.length; fi++) {
      var fillEntry = fillEntries[fi] || {};
      if (isUnknownDictEntry(fillEntry)) continue;
      hasKnownFill = true;
      var fillResolutionSource = String(fillEntry.resolution_source || '')
        .trim()
        .toLowerCase();
      var isOverrideFill = !!(
        fillEntry._lemma_override ||
        fillEntry.lemma_override ||
        fillResolutionSource === 'lemma_override'
      );
      if (!isOverrideFill) {
        allKnownOverride = false;
        break;
      }
      var fillLemmaText = getHeadlineLemmaCueFillText(fillEntry);
      if (!fillLemmaText) continue;
      var fillPartIndex = parseInt(fillEntry._lemma_part_index, 10);
      orderedRows.push({
        text: fillLemmaText,
        partIndex: isFinite(fillPartIndex) ? fillPartIndex : fi,
        sourceIndex: fi
      });
    }
    if (hasKnownFill && allKnownOverride && orderedRows.length > 1) {
      orderedRows.sort(function (a, b) {
        if (a.partIndex !== b.partIndex) return a.partIndex - b.partIndex;
        return a.sourceIndex - b.sourceIndex;
      });
      out = [];
      for (var ri = 0; ri < orderedRows.length; ri++) {
        out.push(orderedRows[ri].text);
      }
      if (!(out.length === 1 && surfaceText && hasSameVisibleComparisonText(out[0], surfaceText))) {
        return out;
      }
    }
  }
  return [];
}
export function getOrderedCompoundLemmaTexts(fallbackSurface, sourceData) {
  var data = sourceData && typeof sourceData === 'object' ? sourceData : null;
  var entry = null;
  if (data) {
    if (data.tokenEntry && typeof data.tokenEntry === 'object') entry = data.tokenEntry;
    else if (data.entry && typeof data.entry === 'object') entry = data.entry;
    else if (
      Array.isArray(data.dict_fill) ||
      Array.isArray(data.lemma_override_parts) ||
      data.lemma_raw != null ||
      data.lemma_form != null ||
      data.lemma != null
    ) {
      entry = data;
    }
  }
  var posData = data && data.posData && typeof data.posData === 'object' ? data.posData : null;
  var udTok = data && data.udTok && typeof data.udTok === 'object' ? data.udTok : null;
  var candidates = [
    data ? data.lemma_raw : '',
    data ? data.lemma : '',
    entry ? entry.lemma_raw : '',
    entry ? entry.lemma_form || entry.lemma || '' : '',
    posData ? posData.lemma_raw : '',
    posData ? posData.lemma : '',
    udTok ? udTok.lemma_raw : '',
    udTok ? udTok.lemma : ''
  ];
  for (var ci = 0; ci < candidates.length; ci++) {
    var candidate = getTrimmedDisplayText(candidates[ci] || '');
    if (!candidate || !/[+\uFF0B]/.test(candidate)) continue;
    var candidateParts = getTokenMapLemmaPartTexts(candidate);
    if (candidateParts.length > 1) return candidateParts;
  }
  return getOrderedLemmaOverridePartTexts(entry, fallbackSurface);
}
export function tokenHasRealMwtParts(sourceData) {
  var data = sourceData && typeof sourceData === 'object' ? sourceData : null;
  var udTok = data && data.udTok && typeof data.udTok === 'object' ? data.udTok : null;
  var mwtParts = udTok && Array.isArray(udTok.mwt_parts) ? udTok.mwt_parts : [];
  return mwtParts.length > 1;
}
export function findLemmaGlossKeyForPart(glossMap, partText) {
  if (!glossMap || typeof glossMap !== 'object') return null;
  var target = String(partText || '')
    .replace(/_/g, ' ')
    .trim()
    .toLowerCase();
  if (!target) return null;
  var keys = Object.keys(glossMap);
  for (var ki = 0; ki < keys.length; ki++) {
    if (keys[ki].replace(/_/g, ' ').trim().toLowerCase() === target) return keys[ki];
  }
  return null;
}
export function buildKoreanCompoundGlossRender(glossEntry, fallbackSurface, sourceData) {
  var entry = glossEntry && typeof glossEntry === 'object' ? glossEntry : null;
  if (!entry || !isKoreanCurrentLanguageForGloss()) return null;
  var data = sourceData && typeof sourceData === 'object' ? sourceData : {};
  var compoundParts = getOrderedCompoundLemmaTexts(fallbackSurface, data);
  if (compoundParts.length < 2) {
    compoundParts = getKoreanGlossLemmaParts(
      fallbackSurface,
      (data && data.udTok) || null,
      (data && (data.tokenEntry || data.entry)) || null
    );
  }
  if (compoundParts.length < 2) return null;
  var glosses = [];
  function pushGloss(value) {
    var text = String(value || '').trim();
    if (text) glosses.push(text);
  }
  if (Array.isArray(entry._compound_part_glosses) && entry._compound_part_glosses.length) {
    for (var ai = 0; ai < entry._compound_part_glosses.length && ai < compoundParts.length; ai++) {
      pushGloss(entry._compound_part_glosses[ai]);
    }
  }
  if (glosses.length < compoundParts.length) {
    var flatGloss = String(entry.gloss || '').trim();
    if (flatGloss && flatGloss.indexOf(' + ') !== -1) {
      var flatParts = flatGloss.split(' + ');
      if (flatParts.length === compoundParts.length) {
        glosses = [];
        for (var fi = 0; fi < flatParts.length; fi++) pushGloss(flatParts[fi]);
      }
    }
  }
  if (
    glosses.length < compoundParts.length &&
    entry.lemma_glosses &&
    typeof entry.lemma_glosses === 'object'
  ) {
    var mapped = [];
    for (var pi = 0; pi < compoundParts.length; pi++) {
      var matchKey = findLemmaGlossKeyForPart(entry.lemma_glosses, compoundParts[pi]);
      mapped.push(matchKey ? String(entry.lemma_glosses[matchKey] || '').trim() : '');
    }
    var mappedNonEmpty = mapped.filter(function (x) {
      return !!String(x || '').trim();
    });
    if (mappedNonEmpty.length >= compoundParts.length) glosses = mappedNonEmpty;
  }
  if (!glosses.length)
    return {
      matched: true,
      rows: []
    };
  if (glosses.length < compoundParts.length) {
    var paddedGlosses = [];
    var gi2 = 0;
    for (var cpi = 0; cpi < compoundParts.length; cpi++) {
      var partText = String(compoundParts[cpi] || '').trim();
      if (partText && !_surfaceHasGlossableChar(partText)) {
        paddedGlosses.push(partText);
      } else if (gi2 < glosses.length) {
        paddedGlosses.push(glosses[gi2]);
        gi2 += 1;
      } else if (partText) {
        paddedGlosses.push(partText);
      }
    }
    glosses = paddedGlosses;
  }
  return {
    matched: true,
    rows: [
      {
        lemma: '',
        gloss: glosses.slice(0, compoundParts.length).join(' + ')
      }
    ]
  };
}
export function buildNonMwtCompoundGlossRows(glossEntry, fallbackSurface, sourceData) {
  var entry = glossEntry && typeof glossEntry === 'object' ? glossEntry : null;
  if (!entry || tokenHasRealMwtParts(sourceData)) return [];
  if (
    entry._korean_compound_gloss &&
    Array.isArray(entry._compound_part_glosses) &&
    entry._compound_part_glosses.length
  ) {
    var koCombined = [];
    for (var koi = 0; koi < entry._compound_part_glosses.length; koi++) {
      var koGloss = String(entry._compound_part_glosses[koi] || '').trim();
      if (koGloss) koCombined.push(koGloss);
    }
    if (koCombined.length)
      return [
        {
          lemma: '',
          gloss: koCombined.join(' + ')
        }
      ];
  }
  var compoundParts = getOrderedCompoundLemmaTexts(fallbackSurface, sourceData);
  if (compoundParts.length < 2) return [];
  var rows = [];
  var flatGloss = String(entry.gloss || '').trim();
  if (Array.isArray(entry._compound_part_glosses) && entry._compound_part_glosses.length) {
    var combinedArr = [];
    for (var ai = 0; ai < entry._compound_part_glosses.length && ai < compoundParts.length; ai++) {
      var arrGloss = String(entry._compound_part_glosses[ai] || '').trim();
      if (arrGloss) combinedArr.push(arrGloss);
    }
    if (combinedArr.length >= compoundParts.length)
      return [
        {
          lemma: '',
          gloss: combinedArr.join(' + ')
        }
      ];
  }
  if (flatGloss && flatGloss.indexOf(' + ') !== -1) {
    var glossParts = flatGloss.split(' + ');
    if (glossParts.length === compoundParts.length) {
      for (var gi = 0; gi < compoundParts.length; gi++) {
        var partGloss = String(glossParts[gi] || '').trim();
        if (!partGloss) continue;
        rows.push({
          lemma: compoundParts[gi],
          gloss: partGloss
        });
      }
      var combinedFlat = [];
      for (var rfi = 0; rfi < rows.length; rfi++) {
        var flatPartGloss = String((rows[rfi] && rows[rfi].gloss) || '').trim();
        if (flatPartGloss) combinedFlat.push(flatPartGloss);
      }
      if (combinedFlat.length)
        return [
          {
            lemma: '',
            gloss: combinedFlat.join(' + ')
          }
        ];
    }
  }
  if (Array.isArray(entry._compound_part_glosses) && entry._compound_part_glosses.length) {
    var partialArr = [];
    for (var pai = 0; pai < entry._compound_part_glosses.length && pai < compoundParts.length; pai++) {
      var partialGloss = String(entry._compound_part_glosses[pai] || '').trim();
      if (partialGloss) partialArr.push(partialGloss);
    }
    if (partialArr.length)
      return [
        {
          lemma: '',
          gloss: partialArr.join(' + ')
        }
      ];
  }
  rows = [];
  if (entry.lemma_glosses && typeof entry.lemma_glosses === 'object') {
    for (var pi = 0; pi < compoundParts.length; pi++) {
      var matchKey = findLemmaGlossKeyForPart(entry.lemma_glosses, compoundParts[pi]);
      if (!matchKey) continue;
      var glossVal = String(entry.lemma_glosses[matchKey] || '').trim();
      if (!glossVal) continue;
      rows.push({
        lemma: compoundParts[pi],
        gloss: glossVal
      });
    }
    if (rows.length) {
      var combinedMapped = [];
      for (var rmi = 0; rmi < rows.length; rmi++) {
        var mappedGloss = String((rows[rmi] && rows[rmi].gloss) || '').trim();
        if (mappedGloss) combinedMapped.push(mappedGloss);
      }
      if (combinedMapped.length)
        return [
          {
            lemma: '',
            gloss: combinedMapped.join(' + ')
          }
        ];
    }
  }
  return [];
}
export function getRenderableLlmGlossRows(glossEntry, fallbackSurface, sourceData, options) {
  var entry = glossEntry && typeof glossEntry === 'object' ? glossEntry : null;
  if (!entry) return [];
  var opts = options && typeof options === 'object' ? options : {};
  var isMwtChild = !!opts.isMwtChild;
  var partIdx = isFinite(Number(opts.partIndex)) ? Number(opts.partIndex) : -1;
  var childLemma = String(opts.childLemma || '')
    .trim()
    .toLowerCase();
  var koreanCompoundRender = buildKoreanCompoundGlossRender(entry, fallbackSurface, sourceData);
  if (koreanCompoundRender) return koreanCompoundRender.rows;
  if (!isMwtChild) {
    var compoundRows = buildNonMwtCompoundGlossRows(entry, fallbackSurface, sourceData);
    if (compoundRows.length) return compoundRows;
  }
  if (entry.lemma_glosses && typeof entry.lemma_glosses === 'object') {
    var keys = Object.keys(entry.lemma_glosses);
    if (isMwtChild && partIdx >= 0) {
      var matched = null;
      if (childLemma) {
        for (var ki = 0; ki < keys.length; ki++) {
          if (keys[ki].replace(/_/g, ' ').trim().toLowerCase() === childLemma) {
            matched = keys[ki];
            break;
          }
        }
      }
      if (!matched && partIdx < keys.length) matched = keys[partIdx];
      keys = matched ? [matched] : [];
    }
    var rows = [];
    for (var ri = 0; ri < keys.length; ri++) {
      var gloss = String(entry.lemma_glosses[keys[ri]] || '').trim();
      if (!gloss) continue;
      rows.push({
        lemma: keys[ri].replace(/_/g, ' '),
        gloss: gloss
      });
    }
    if (rows.length) return rows;
  }
  var flatGloss = String(entry.gloss || '').trim();
  if (!flatGloss) return [];
  if (isMwtChild && partIdx >= 0 && flatGloss.indexOf(' + ') !== -1) {
    var flatParts = flatGloss.split(' + ');
    flatGloss = partIdx < flatParts.length ? String(flatParts[partIdx] || '').trim() : '';
  }
  return flatGloss
    ? [
        {
          lemma: '',
          gloss: flatGloss
        }
      ]
    : [];
}
