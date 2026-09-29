import { documentShellState } from './document-shell.state.mjs';
import {
  getCanonicalTokenSurfaceText,
  getLookupEntryFills,
  getLookupPayloadPrimaryResult,
  getLookupPayloadResults,
  hasExactTokenLookupMatch,
  lookupSingleDictionary
} from './entry-editing.mjs';
import { buildDictFillSlicesForToken, getDictFillSurfaceText, parseFillHitIndexes } from './fill-slices.mjs';
import {
  getCanonicalTokenDictFill,
  getCanonicalTokenResolvedVia,
  getScopedMwtChildResolutionCategory
} from './gloss-entries.mjs';
import { getTokenLiveResolution } from './grammar-popup.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import {
  escapeHtml,
  getEntryDisplayHead,
  getTrimmedDisplayText,
  hasSameVisibleComparisonText,
  isUiRenderDebugEnabled,
  stripZeroWidthJoiners,
  summarizeUiRenderDebugLookupEntry,
  traceUiRenderEvent
} from './presentation.mjs';
import {
  buildSidePanelLookupCacheKey,
  getExactSidePanelLookupEntry,
  setExactSidePanelLookupEntry
} from './segment-rendering.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
import { isUnknownDictEntry } from './side-panel.mjs';
import {
  buildAggregateLookupEntry,
  buildTokenMapLookupRequestOptions,
  getTokenMapSurfaceLookupEntry,
  isTokenMapCompoundSeparator,
  splitTokenMapCompoundHintTags,
  splitTokenMapCompoundText
} from './token-banner.mjs';
import { tokenMapState } from './token-map.state.mjs';
export function getTokenMapLemmaPartTexts(text) {
  var rawParts = splitTokenMapCompoundText(text);
  var out = [];
  for (var i = 0; i < rawParts.length; i++) {
    var rawPart = String(rawParts[i] || '');
    var partText = rawPart.trim();
    if (!partText || /^\s+$/.test(rawPart) || isTokenMapCompoundSeparator(rawPart)) continue;
    out.push(partText);
  }
  return out;
}
export function getTokenMapLemmaPartHintRows(data) {
  if (!data) return [];
  var lemmaCandidates = [
    data.lemma,
    data.lemma_raw,
    data.posData && data.posData.lemma,
    data.posData && data.posData.lemma_raw,
    data.udTok && data.udTok.lemma,
    data.udTok && data.udTok.lemma_raw
  ];
  var lemmaText = '';
  for (var lci = 0; lci < lemmaCandidates.length; lci++) {
    var candidate = String(lemmaCandidates[lci] || '').trim();
    if (candidate && /[+\uFF0B]/.test(candidate)) {
      lemmaText = candidate;
      break;
    }
    if (!lemmaText && candidate) lemmaText = candidate;
  }
  if (!lemmaText || !/[+\uFF0B]/.test(lemmaText)) return [];
  var partTexts = getTokenMapLemmaPartTexts(lemmaText);
  if (!partTexts.length) return [];
  var tokenEntry = data.tokenEntry || data.entry || null;
  var overrideParts =
    tokenEntry && Array.isArray(tokenEntry.lemma_override_parts) ? tokenEntry.lemma_override_parts : [];
  if (overrideParts.length === partTexts.length) {
    return partTexts.map(function (partText, index) {
      var part = overrideParts[index] || {};
      return {
        text: partText,
        upos: String(part.upos || '').trim(),
        xpos: String(part.xpos || '').trim()
      };
    });
  }
  var uposHint = String(
    (data.posData && (data.posData.upos || data.posData.upos_label)) ||
      (data.udTok && data.udTok.upos) ||
      (tokenEntry && tokenEntry.upos) ||
      ''
  ).trim();
  var xposHint = String(
    (data.posData && (data.posData.tag || data.posData.xpos)) ||
      (data.udTok && (data.udTok.tag || data.udTok.xpos)) ||
      (tokenEntry && tokenEntry.tag) ||
      ''
  ).trim();
  var uposParts = splitTokenMapCompoundHintTags(uposHint);
  var xposParts = splitTokenMapCompoundHintTags(xposHint);
  if (uposParts.length !== partTexts.length && xposParts.length !== partTexts.length) return [];
  return partTexts.map(function (partText, index) {
    return {
      text: partText,
      upos: uposParts.length === partTexts.length ? uposParts[index] : '',
      xpos: xposParts.length === partTexts.length ? xposParts[index] : ''
    };
  });
}
export function getTokenMapPreferredLemmaLookupXpos(data, fallbackXpos) {
  var lang = String(documentShellState.currentLanguage || '')
    .trim()
    .toLowerCase();
  if (!(lang === 'ko' || lang === 'korean' || lang.indexOf('ko-') === 0)) {
    return String(fallbackXpos || '').trim();
  }
  var hintRows = getTokenMapLemmaPartHintRows(data);
  var tags = [];
  var seen = Object.create(null);
  for (var i = 0; i < hintRows.length; i++) {
    var row = hintRows[i] || {};
    var parts = splitTokenMapCompoundHintTags(row.xpos);
    if (!parts.length) {
      var single = String(row.xpos || '').trim();
      if (single) parts = [single];
    }
    for (var j = 0; j < parts.length; j++) {
      var tag = String(parts[j] || '').trim();
      if (!tag || seen[tag]) continue;
      seen[tag] = true;
      tags.push(tag);
    }
  }
  if (tags.length) return tags.join('+');
  return String(fallbackXpos || '').trim();
}
export function getTokenMapLemmaPartLookup(data, partText, partIndex) {
  var key = String(partText || '').trim();
  if (!key) return null;
  var indexKey = isFinite(partIndex) ? String(parseInt(partIndex, 10)) : '';
  var hintRows = getTokenMapLemmaPartHintRows(data);
  var partHint = indexKey ? hintRows[parseInt(indexKey, 10)] || null : null;
  var hasPartSpecificFilters = !!(
    String((partHint && partHint.upos) || '').trim() || String((partHint && partHint.xpos) || '').trim()
  );
  if (indexKey && data && data.lemmaPartLookupsByIndex && data.lemmaPartLookupsByIndex[indexKey]) {
    return data.lemmaPartLookupsByIndex[indexKey];
  }
  if (hasPartSpecificFilters) return null;
  if (data && data.lemmaPartLookups && data.lemmaPartLookups[key]) return data.lemmaPartLookups[key];
  return getExactSidePanelLookupEntry(
    key,
    documentShellState.currentLanguage || '',
    buildTokenMapLookupRequestOptions('lemma-part', data, partIndex)
  );
}
export function resolveTokenMapLookupEntry(role, data, text, partIndex) {
  var liveData = data || hoverLayoutState.tokenMapData || null;
  var roleKey = String(role || 'surface').toLowerCase();
  var expectedText = String(text || '').trim();
  if (!liveData) {
    traceUiRenderEvent(
      'resolve_token_map_lookup',
      {
        role: roleKey,
        expected_text: expectedText,
        part_index: isFinite(partIndex) ? parseInt(partIndex, 10) : null,
        source: 'no_live_data'
      },
      {
        scope: 'token-map-lookup'
      }
    );
    return null;
  }
  if (roleKey === 'lemma-part') {
    var lemmaPartLookup = getTokenMapLemmaPartLookup(liveData, expectedText, partIndex);
    traceUiRenderEvent(
      'resolve_token_map_lookup',
      {
        role: roleKey,
        expected_text: expectedText,
        part_index: isFinite(partIndex) ? parseInt(partIndex, 10) : null,
        source: 'lemma_part_lookup',
        lookup_entry: summarizeUiRenderDebugLookupEntry(lemmaPartLookup)
      },
      {
        scope: 'token-map-lookup'
      }
    );
    return lemmaPartLookup;
  }
  if (roleKey === 'lemma') {
    var lemmaLookup = liveData.lemmaLookup || null;
    if (lemmaLookup && (!expectedText || hasExactTokenLookupMatch(lemmaLookup, expectedText))) {
      traceUiRenderEvent(
        'resolve_token_map_lookup',
        {
          role: roleKey,
          expected_text: expectedText,
          source: 'live_lemma_lookup',
          lookup_entry: summarizeUiRenderDebugLookupEntry(lemmaLookup)
        },
        {
          scope: 'token-map-lookup'
        }
      );
      return lemmaLookup;
    }
    if (expectedText) {
      var cachedLemma = getExactSidePanelLookupEntry(
        expectedText,
        documentShellState.currentLanguage || '',
        buildTokenMapLookupRequestOptions('lemma', liveData, partIndex)
      );
      if (cachedLemma && hasExactTokenLookupMatch(cachedLemma, expectedText)) {
        traceUiRenderEvent(
          'resolve_token_map_lookup',
          {
            role: roleKey,
            expected_text: expectedText,
            source: 'cached_lemma_lookup',
            lookup_entry: summarizeUiRenderDebugLookupEntry(cachedLemma)
          },
          {
            scope: 'token-map-lookup'
          }
        );
        return cachedLemma;
      }
    }
    traceUiRenderEvent(
      'resolve_token_map_lookup',
      {
        role: roleKey,
        expected_text: expectedText,
        source: lemmaLookup ? 'lemma_lookup_non_exact_discarded' : 'no_lemma_lookup',
        lookup_entry: summarizeUiRenderDebugLookupEntry(lemmaLookup)
      },
      {
        scope: 'token-map-lookup'
      }
    );
    return null;
  }
  var surfaceLookup = liveData.surfaceLookup || null;
  if (surfaceLookup && (!expectedText || hasExactTokenLookupMatch(surfaceLookup, expectedText))) {
    traceUiRenderEvent(
      'resolve_token_map_lookup',
      {
        role: roleKey,
        expected_text: expectedText,
        source: 'live_surface_lookup',
        lookup_entry: summarizeUiRenderDebugLookupEntry(surfaceLookup)
      },
      {
        scope: 'token-map-lookup'
      }
    );
    return surfaceLookup;
  }
  if (expectedText) {
    var cachedSurface = getExactSidePanelLookupEntry(
      expectedText,
      documentShellState.currentLanguage || '',
      buildTokenMapLookupRequestOptions('surface', liveData, partIndex)
    );
    if (cachedSurface && hasExactTokenLookupMatch(cachedSurface, expectedText)) {
      traceUiRenderEvent(
        'resolve_token_map_lookup',
        {
          role: roleKey,
          expected_text: expectedText,
          source: 'cached_surface_lookup',
          lookup_entry: summarizeUiRenderDebugLookupEntry(cachedSurface)
        },
        {
          scope: 'token-map-lookup'
        }
      );
      return cachedSurface;
    }
  }
  traceUiRenderEvent(
    'resolve_token_map_lookup',
    {
      role: roleKey,
      expected_text: expectedText,
      source: surfaceLookup ? 'non_exact_surface_discarded' : 'no_lookup_entry',
      lookup_entry: summarizeUiRenderDebugLookupEntry(surfaceLookup || null)
    },
    {
      scope: 'token-map-lookup'
    }
  );
  return null;
}
export function getTokenMapLookupEntryForRole(role, text, partIndex, data) {
  return resolveTokenMapLookupEntry(role, data || hoverLayoutState.tokenMapData, text, partIndex);
}
export function getTokenMapDictFill(data) {
  return getCanonicalTokenDictFill(data);
}
export function getTokenMapResolvedVia(data) {
  return getCanonicalTokenResolvedVia(data);
}
export function getResolutionDisplayInfo(cat, fallbackLabel) {
  var c = String(cat || '')
    .trim()
    .toLowerCase();
  var mapped = c ? tokenMapState.RESOLUTION_DISPLAY_INFO_BY_CATEGORY[c] : null;
  var label = mapped ? mapped.label : String(fallbackLabel || '').trim();
  return {
    category: mapped ? mapped.category : c,
    label: label || String(fallbackLabel || '').trim()
  };
}
export function getTokenResolutionInfo(surfaceText, lemmaText, tokenEntry, dictFill, resolvedVia) {
  void surfaceText;
  void lemmaText;
  void dictFill;
  void resolvedVia;
  var liveResolution = getTokenLiveResolution(tokenEntry);
  var category = liveResolution
    ? String(liveResolution.category || '')
        .trim()
        .toLowerCase()
    : '';
  var label = liveResolution ? String(liveResolution.label || '').trim() : '';
  var scopedChildCategory = getScopedMwtChildResolutionCategory(tokenEntry, dictFill, null);
  if (scopedChildCategory) {
    category = scopedChildCategory;
    label = '';
  }
  var displayInfo = getResolutionDisplayInfo(category, label);
  category = displayInfo.category;
  label = displayInfo.label;
  // Per-child MWT: join child categories with ' + ' (UI convention).
  var childRes =
    tokenEntry && Array.isArray(tokenEntry.mwt_child_resolutions) ? tokenEntry.mwt_child_resolutions : null;
  if (!scopedChildCategory && childRes && childRes.length >= 2) {
    var parts = [];
    for (var i = 0; i < childRes.length; i++) {
      var childInfo = getResolutionDisplayInfo(childRes[i], '');
      parts.push(childInfo.label || String(childRes[i] || '').trim());
    }
    label = parts.join(' + ');
  }
  var info = {
    category: category,
    primary: label,
    secondary: '',
    note: ''
  };
  return info;
}
export function buildTokenResolutionHtml(info, renderPill, renderNote) {
  void renderNote;
  if (!info || !info.primary) return '';
  var html = '<span style="display:inline-flex;flex-direction:column;align-items:flex-start;gap:4px;">';
  html += renderPill(info.primary, 'primary');
  html += '</span>';
  return html;
}
export function buildTokenMapSliceItemsForEntry(surfaceText, dictFill, providedSlices) {
  if (!surfaceText || !Array.isArray(dictFill) || !dictFill.length) return [];
  var slices = buildDictFillSlicesForToken(surfaceText, dictFill, providedSlices, {
    coalesceMarkOnly: true
  });
  var items = [];
  if (slices && slices.length) {
    for (var i = 0; i < slices.length; i++) {
      var slice = slices[i];
      var fillIndexes = Array.isArray(slice.fillIndexes) ? slice.fillIndexes.slice() : [];
      if (!fillIndexes.length) continue;
      items.push({
        text: surfaceText.slice(slice.start, slice.end),
        fillIndexes: fillIndexes
      });
    }
    if (items.length) return items;
  }
  // Fallback: no slices provided. Build items from fill texts,
  // folding empty-text fills into their nearest neighbor.
  var pendingOrphans = [];
  for (var fi = 0; fi < dictFill.length; fi++) {
    var fillEntry = dictFill[fi] || {};
    var fillText = getDictFillSurfaceText(fillEntry);
    if (!fillText) {
      pendingOrphans.push(fi);
      continue;
    }
    // Attach any preceding orphans to this item
    var itemIndexes = pendingOrphans.slice();
    pendingOrphans = [];
    itemIndexes.push(fi);
    items.push({
      text: fillText,
      fillIndexes: itemIndexes
    });
  }
  // Trailing orphans: attach to last item
  if (pendingOrphans.length && items.length) {
    var lastItem = items[items.length - 1];
    for (var oi = 0; oi < pendingOrphans.length; oi++) {
      lastItem.fillIndexes.push(pendingOrphans[oi]);
    }
  }
  return items;
}
export function attachTokenMapSliceItemSource(items, lookupEntry, dictFill, role) {
  var src = Array.isArray(items) ? items : [];
  var fill = Array.isArray(dictFill) ? dictFill : [];
  var out = [];
  for (var i = 0; i < src.length; i++) {
    var item = src[i] || {};
    out.push({
      text: String(item.text || ''),
      fillIndexes: Array.isArray(item.fillIndexes) ? item.fillIndexes.slice() : [],
      lookupEntry: lookupEntry || null,
      dictFill: fill,
      sourceRole: String(role || '')
    });
  }
  return out;
}
export function getRenderableTokenMapDisplaySliceItems(data) {
  // Use the actual dict_fill entries from the backend lookup directly.
  // No slicing, decomposition, or async re-lookup � just the literal entries
  // that were appended to the token during dictionary lookup.
  var dictFill = getTokenMapDictFill(data);
  if (!Array.isArray(dictFill) || !dictFill.length) return [];
  var out = [];
  for (var i = 0; i < dictFill.length; i++) {
    var fillEntry = dictFill[i] || {};
    var itemText = getTrimmedDisplayText(getDictFillSurfaceText(fillEntry));
    if (!itemText) continue;
    if (isTokenMapCompoundSeparator(itemText)) continue;
    out.push({
      text: itemText,
      fillIndexes: [i],
      lookupEntry: null,
      dictFill: dictFill,
      sourceRole: '',
      isUnknown: isUnknownDictEntry(fillEntry),
      isLemmaDerived: isLemmaLinkedFillEntry(fillEntry)
    });
  }
  return out;
}
export function getTokenMapSurfaceSliceItems(data) {
  var surfaceText = String((data && data.surface) || '');
  var dictFill = getTokenMapDictFill(data);
  if (!surfaceText || !Array.isArray(dictFill) || !dictFill.length) return [];
  var lookupEntry = getTokenMapSurfaceLookupEntry(data);
  var providedSlices =
    lookupEntry && Array.isArray(lookupEntry.dict_fill_surface_slices)
      ? lookupEntry.dict_fill_surface_slices
      : null;
  return buildTokenMapSliceItemsForEntry(surfaceText, dictFill, providedSlices);
}
export function getTokenMapDisplaySliceItems(data) {
  var resolvedVia = getTokenMapResolvedVia(data);
  if (resolvedVia === 'lemma_override') {
    var lemmaLookup = data && data.lemmaLookup ? data.lemmaLookup : null;
    var lemmaText = String((data && data.lemma) || '').trim();
    var lemmaFill = getLookupEntryFills(lemmaLookup);
    if (lemmaText && lemmaFill.length) {
      var lemmaItems = buildTokenMapSliceItemsForEntry(lemmaText, lemmaFill, null);
      if (lemmaItems.length) {
        return attachTokenMapSliceItemSource(lemmaItems, lemmaLookup, lemmaFill, 'lemma_headword_dp');
      }
    }
    if (data && data.lemmaLookupPromise) return [];
  }
  var surfaceItems = getTokenMapSurfaceSliceItems(data);
  return attachTokenMapSliceItemSource(
    surfaceItems,
    getTokenMapSurfaceLookupEntry(data),
    getTokenMapDictFill(data),
    'surface'
  );
}
export function getTokenMapFillIndexesFromRaw(rawIndexes, fillCount) {
  return parseFillHitIndexes(
    {
      dataset: {
        fillIndexes: String(rawIndexes || '')
      }
    },
    fillCount
  );
}
export function isUnknownTokenMapFillSlice(dictFill, fillIndexes) {
  if (!Array.isArray(dictFill) || !dictFill.length) return false;
  var hasKnown = false;
  var hasUnknown = false;
  for (var i = 0; i < fillIndexes.length; i++) {
    var idx = fillIndexes[i];
    if (!isFinite(idx) || idx < 0 || idx >= dictFill.length) continue;
    if (isUnknownDictEntry(dictFill[idx])) hasUnknown = true;
    else hasKnown = true;
  }
  if (hasUnknown && !hasKnown) return true;
  return false;
}
export function isLemmaLinkedFillEntry(fillEntry) {
  if (!fillEntry || typeof fillEntry !== 'object') return false;
  return !!(
    fillEntry.resolution_linked_to_lemma === true ||
    fillEntry._lemma_promoted ||
    fillEntry.lemma_promoted ||
    fillEntry._lemma_override ||
    fillEntry.lemma_override
  );
}
export function isLemmaDerivedTokenMapFillSlice(dictFill, fillIndexes) {
  if (!Array.isArray(dictFill) || !dictFill.length) return false;
  for (var i = 0; i < fillIndexes.length; i++) {
    var idx = fillIndexes[i];
    if (!isFinite(idx) || idx < 0 || idx >= dictFill.length) continue;
    var fillEntry = dictFill[idx] || {};
    if (isLemmaLinkedFillEntry(fillEntry)) return true;
  }
  return false;
}
export function fetchExactSidePanelLookupEntry(text, langOverride, options) {
  var token = String(text || '').trim();
  if (!token) return Promise.resolve(null);
  var opts = options || {};
  var requestLang = String(langOverride || documentShellState.currentLanguage || '');
  var shouldCache = opts.cacheResult !== false;
  var cached = getExactSidePanelLookupEntry(token, requestLang, opts);
  if (cached) return Promise.resolve(cached);
  var promiseKey = buildSidePanelLookupCacheKey(token, requestLang, opts);
  if (promiseKey && segmentRenderingState.sidePanelLookupPromiseCache.has(promiseKey)) {
    return segmentRenderingState.sidePanelLookupPromiseCache.get(promiseKey);
  }
  var requestPromise = lookupSingleDictionary(token, requestLang, {
    lemma: String(opts.lemma || ''),
    upos: String(opts.upos || ''),
    xpos: String(opts.xpos || ''),
    exact: true
  }).then(
    function (data) {
      var lookupResults = getLookupPayloadResults(data);
      if (!(data && data.ok && lookupResults.length)) return null;
      var entry = getLookupPayloadPrimaryResult(data) || buildAggregateLookupEntry(lookupResults, token);
      if (entry && shouldCache) {
        setExactSidePanelLookupEntry(token, entry, requestLang, opts);
      }
      return entry || null;
    },
    function () {
      return null;
    }
  );
  if (promiseKey) segmentRenderingState.sidePanelLookupPromiseCache.set(promiseKey, requestPromise);
  return requestPromise.then(
    function (entry) {
      if (promiseKey) segmentRenderingState.sidePanelLookupPromiseCache.delete(promiseKey);
      return entry;
    },
    function (err) {
      if (promiseKey) segmentRenderingState.sidePanelLookupPromiseCache.delete(promiseKey);
      throw err;
    }
  );
}
export function fetchTokenMapLookupEntry(text, options) {
  return fetchExactSidePanelLookupEntry(text, documentShellState.currentLanguage || '', options || {});
}
export function ensureTokenMapLookupEntries(data) {
  if (!data) return Promise.resolve(false);
  var changed = false;
  var surfaceText = String(data.surface || '');
  var lemmaText = String(
    data.lemma || (data.posData && data.posData.lemma) || (data.udTok && data.udTok.lemma) || ''
  ).trim();
  var uposHint = String(
    (data.posData && (data.posData.upos || data.posData.upos_label)) ||
      (data.udTok && data.udTok.upos) ||
      (data.tokenEntry && data.tokenEntry.upos) ||
      ''
  );
  var xposHint = String(
    (data.posData && (data.posData.tag || data.posData.xpos)) ||
      (data.udTok && (data.udTok.tag || data.udTok.xpos)) ||
      (data.tokenEntry && data.tokenEntry.tag) ||
      ''
  );
  var lemmaLookupXposHint = getTokenMapPreferredLemmaLookupXpos(data, xposHint);
  var pending = [];
  var surfaceLookupOpts = buildTokenMapLookupRequestOptions('surface', data, null);
  var lemmaLookupOpts = buildTokenMapLookupRequestOptions('lemma', data, null);
  if (!data.surfaceLookup && surfaceText) {
    var cachedSurfaceLookup = getExactSidePanelLookupEntry(
      surfaceText,
      documentShellState.currentLanguage || '',
      surfaceLookupOpts
    );
    if (cachedSurfaceLookup) {
      data.surfaceLookup = cachedSurfaceLookup;
      changed = true;
    }
  }
  if (lemmaText && lemmaText !== surfaceText && !data.lemmaLookup) {
    var cachedLemmaLookup = getExactSidePanelLookupEntry(
      lemmaText,
      documentShellState.currentLanguage || '',
      lemmaLookupOpts
    );
    if (cachedLemmaLookup) {
      data.lemmaLookup = cachedLemmaLookup;
      changed = true;
    }
  }
  if (!data.surfaceLookup && surfaceText) {
    if (!data.surfaceLookupPromise) {
      data.surfaceLookupPromise = fetchTokenMapLookupEntry(surfaceText, {
        lemma: '',
        upos: surfaceLookupOpts.upos || uposHint,
        xpos: surfaceLookupOpts.xpos || xposHint
      }).then(
        function (entry) {
          data.surfaceLookupPromise = null;
          if (entry) {
            data.surfaceLookup = entry;
            return true;
          }
          return false;
        },
        function () {
          data.surfaceLookupPromise = null;
          return false;
        }
      );
    }
    pending.push(data.surfaceLookupPromise);
  }
  if (lemmaText && lemmaText !== surfaceText && !data.lemmaLookup) {
    if (!data.lemmaLookupPromise) {
      data.lemmaLookupPromise = fetchTokenMapLookupEntry(lemmaText, {
        upos: lemmaLookupOpts.upos || uposHint,
        xpos: lemmaLookupOpts.xpos || lemmaLookupXposHint
      }).then(
        function (entry) {
          data.lemmaLookupPromise = null;
          if (entry) {
            data.lemmaLookup = entry;
            return true;
          }
          return false;
        },
        function () {
          data.lemmaLookupPromise = null;
          return false;
        }
      );
    }
    pending.push(data.lemmaLookupPromise);
  }
  if (lemmaText && /[+\uFF0B]/.test(lemmaText)) {
    if (!data.lemmaPartLookups) data.lemmaPartLookups = Object.create(null);
    if (!data.lemmaPartLookupsByIndex) data.lemmaPartLookupsByIndex = Object.create(null);
    if (!data.lemmaPartLookupPromises) data.lemmaPartLookupPromises = Object.create(null);
    if (!data.lemmaPartLookupPromisesByIndex) data.lemmaPartLookupPromisesByIndex = Object.create(null);
    var lemmaParts = splitTokenMapCompoundText(lemmaText);
    var lemmaPartHintRows = getTokenMapLemmaPartHintRows(data);
    var lemmaPartIndex = 0;
    for (var pi = 0; pi < lemmaParts.length; pi++) {
      var rawPart = String(lemmaParts[pi] || '');
      var partText = rawPart.trim();
      if (!partText || /^\s+$/.test(rawPart) || isTokenMapCompoundSeparator(rawPart)) continue;
      var partIndex = lemmaPartIndex++;
      var partIndexKey = String(partIndex);
      var partHint = lemmaPartHintRows[partIndex] || null;
      var partUpos = String((partHint && partHint.upos) || '').trim();
      var partXpos = String((partHint && partHint.xpos) || '').trim();
      var hasPartSpecificFilters = !!(partUpos || partXpos);
      if (data.lemmaPartLookupsByIndex[partIndexKey]) continue;
      if (!hasPartSpecificFilters && data.lemmaPartLookups[partText]) {
        data.lemmaPartLookupsByIndex[partIndexKey] = data.lemmaPartLookups[partText];
        changed = true;
        continue;
      }
      if (!hasPartSpecificFilters) {
        var cachedPart = getExactSidePanelLookupEntry(
          partText,
          documentShellState.currentLanguage || '',
          buildTokenMapLookupRequestOptions('lemma-part', data, partIndex)
        );
        if (cachedPart) {
          data.lemmaPartLookups[partText] = cachedPart;
          data.lemmaPartLookupsByIndex[partIndexKey] = cachedPart;
          changed = true;
          continue;
        }
        if (!data.lemmaPartLookupPromises[partText]) {
          (function (partKey) {
            data.lemmaPartLookupPromises[partKey] = fetchTokenMapLookupEntry(partKey, {
              cacheResult: true
            }).then(
              function (entry) {
                delete data.lemmaPartLookupPromises[partKey];
                if (entry) {
                  data.lemmaPartLookups[partKey] = entry;
                  return true;
                }
                return false;
              },
              function () {
                delete data.lemmaPartLookupPromises[partKey];
                return false;
              }
            );
          })(partText);
        }
        pending.push(data.lemmaPartLookupPromises[partText]);
        continue;
      }
      if (!data.lemmaPartLookupPromisesByIndex[partIndexKey]) {
        (function (partKey, indexKey, lookupUpos, lookupXpos) {
          data.lemmaPartLookupPromisesByIndex[indexKey] = fetchTokenMapLookupEntry(partKey, {
            upos: lookupUpos,
            xpos: lookupXpos,
            cacheResult: false
          }).then(
            function (entry) {
              delete data.lemmaPartLookupPromisesByIndex[indexKey];
              if (entry) {
                data.lemmaPartLookupsByIndex[indexKey] = entry;
                return true;
              }
              return false;
            },
            function () {
              delete data.lemmaPartLookupPromisesByIndex[indexKey];
              return false;
            }
          );
        })(partText, partIndexKey, partUpos, partXpos);
      }
      pending.push(data.lemmaPartLookupPromisesByIndex[partIndexKey]);
    }
  }
  if (!pending.length) return Promise.resolve(changed);
  return Promise.all(pending).then(function (results) {
    if (changed) return true;
    for (var i = 0; i < results.length; i++) {
      if (results[i]) return true;
    }
    return false;
  });
}
export function buildTokenMapGroupedFillEntry(baseEntry, fillIndexes, surfaceText, sourceFill) {
  var fill = Array.isArray(sourceFill)
    ? sourceFill
    : baseEntry && Array.isArray(baseEntry.dict_fill)
      ? baseEntry.dict_fill
      : [];
  if (!fill.length || !Array.isArray(fillIndexes) || !fillIndexes.length) return null;
  var groupedFills = [];
  var groupedHasKnown = false;
  var groupedHasUnknown = false;
  for (var i = 0; i < fillIndexes.length; i++) {
    var idx = fillIndexes[i];
    if (!isFinite(idx) || idx < 0 || idx >= fill.length) continue;
    var fillEntry = fill[idx];
    if (!fillEntry) continue;
    groupedFills.push(fillEntry);
    if (isUnknownDictEntry(fillEntry)) groupedHasUnknown = true;
    else groupedHasKnown = true;
  }
  if (!groupedFills.length) return null;
  if (groupedFills.length === 1) return groupedFills[0];
  var pieceText = String(
    surfaceText || baseEntry.surface_form || getEntryDisplayHead(baseEntry, '') || ''
  ).trim();
  return Object.assign({}, baseEntry, {
    text: pieceText,
    head: pieceText,
    surface_form: pieceText,
    fills: groupedFills.slice(),
    dict_fill: groupedFills.slice(),
    dict_fill_has_known: groupedHasKnown,
    dict_fill_has_unknown: groupedHasUnknown
  });
}
export function buildTokenMapCompoundLookupHtml(text, role, data) {
  var parts = splitTokenMapCompoundText(text);
  var html = '';
  var partIndex = 0;
  for (var i = 0; i < parts.length; i++) {
    var rawPart = String(parts[i] || '');
    if (!rawPart) continue;
    if (/^\s+$/.test(rawPart)) {
      html += '<span aria-hidden="true" style="white-space:pre;">' + escapeHtml(rawPart) + '</span>';
      continue;
    }
    if (isTokenMapCompoundSeparator(rawPart)) {
      html +=
        '<span aria-hidden="true" style="opacity:0.65;pointer-events:none;">' +
        escapeHtml(rawPart) +
        '</span>';
      continue;
    }
    var currentPartIndex = partIndex++;
    var lookupEntry =
      String(role || '').toLowerCase() === 'lemma'
        ? resolveTokenMapLookupEntry('lemma-part', data, rawPart, currentPartIndex)
        : getExactSidePanelLookupEntry(
            rawPart,
            documentShellState.currentLanguage || '',
            buildTokenMapLookupRequestOptions('lemma-part', data, currentPartIndex)
          );
    html += buildTokenMapLookupHtml(lookupEntry, rawPart, 'lemma-part', {
      suppressCache: true,
      tokenMapPartIndex: currentPartIndex,
      tokenMapData: data,
      forceTokenMapFallback: true
    });
  }
  return html;
}
export function buildTokenMapLookupHtml(lookupEntry, text, role, options) {
  var tokenText = String(text || '');
  var tokenDisplay = stripZeroWidthJoiners(tokenText);
  var opts = options || {};
  var uiRenderDebugEnabled = isUiRenderDebugEnabled();
  var renderTrace = uiRenderDebugEnabled
    ? {
        role: String(role || 'surface'),
        token_text: tokenText,
        token_display: tokenDisplay,
        options: {
          suppress_cache: !!opts.suppressCache,
          force_token_map_fallback: !!opts.forceTokenMapFallback,
          has_token_map_data: !!opts.tokenMapData,
          token_map_part_index: isFinite(opts.tokenMapPartIndex) ? parseInt(opts.tokenMapPartIndex, 10) : null
        }
      }
    : null;
  if (!tokenText || !tokenDisplay.trim()) {
    if (uiRenderDebugEnabled) {
      renderTrace.result = 'empty';
      renderTrace.reason = 'blank_text';
      traceUiRenderEvent('token_map_render', renderTrace, {
        scope: 'token-map-render'
      });
    }
    return '';
  }
  var effectiveLookupEntry = lookupEntry || null;
  if (uiRenderDebugEnabled) {
    renderTrace.initial_lookup = summarizeUiRenderDebugLookupEntry(effectiveLookupEntry);
  }
  if (uiRenderDebugEnabled) {
    renderTrace.effective_lookup = summarizeUiRenderDebugLookupEntry(effectiveLookupEntry);
  }
  var psrApi = window.PanelSegmentRenderer || null;
  var html = '';
  if (uiRenderDebugEnabled) {
    var dictFill =
      effectiveLookupEntry && Array.isArray(effectiveLookupEntry.dict_fill)
        ? effectiveLookupEntry.dict_fill
        : [];
    var surfaceSlices =
      effectiveLookupEntry && Array.isArray(effectiveLookupEntry.dict_fill_surface_slices)
        ? effectiveLookupEntry.dict_fill_surface_slices
        : [];
    renderTrace.dict_fill_count = dictFill.length;
    renderTrace.provided_surface_slice_count = surfaceSlices.length;
  }
  if (psrApi && typeof psrApi.renderLookupSpanHtml === 'function') {
    html = psrApi.renderLookupSpanHtml(tokenText, {
      displayText: tokenDisplay,
      panelToken: true,
      extraClasses: ['panel-token', 'panel-' + String(role || 'surface').trim() + '-token'],
      extraData: {
        panel_head_role: String(role || 'surface').trim() || 'surface',
        token_map_lookup: String(role || 'surface').trim() || 'surface',
        token_map_lookup_key: tokenText,
        token_map_part_index: isFinite(opts.tokenMapPartIndex) ? parseInt(opts.tokenMapPartIndex, 10) : ''
      }
    });
    if (uiRenderDebugEnabled) {
      renderTrace.slice_strategy = 'psr_lookup_span';
      renderTrace.result = html ? 'rendered_via_psr_span' : 'empty';
    }
  }
  if (!html) {
    if (uiRenderDebugEnabled) renderTrace.slice_strategy = 'psr_span_unavailable';
    html = '<span dir="auto" style="white-space:pre-wrap;">' + escapeHtml(tokenDisplay) + '</span>';
  }
  if (uiRenderDebugEnabled && !renderTrace.result) {
    renderTrace.result = 'flat_token';
    renderTrace.reason = 'psr_lookup_span';
  }
  if (uiRenderDebugEnabled) {
    traceUiRenderEvent('token_map_render', renderTrace, {
      scope: 'token-map-render'
    });
  }
  return html;
}
export function getCurrentPanelSurfaceLookupEntry(text) {
  var surfaceText = String(text || '').trim();
  if (!surfaceText || !hoverLayoutState.tokenMapData) return null;
  var liveSurface = String(getCanonicalTokenSurfaceText(hoverLayoutState.tokenMapData) || '').trim();
  if (!liveSurface) return null;
  if (!hasSameVisibleComparisonText(surfaceText, liveSurface)) return null;
  return resolveTokenMapLookupEntry('surface', hoverLayoutState.tokenMapData, liveSurface) || null;
}
export function buildPendingPanelSurfaceTokenHtml(surfaceText, role) {
  var text = String(surfaceText || '').trim();
  if (!text) return '';
  var roleClass = String(role || 'surface').trim() || 'surface';
  traceUiRenderEvent(
    'panel_surface_pending',
    {
      text: text,
      role: roleClass
    },
    {
      scope: 'panel-surface'
    }
  );
  var psrApi = window.PanelSegmentRenderer || null;
  if (psrApi && typeof psrApi.renderLookupSpanHtml === 'function') {
    return psrApi.renderLookupSpanHtml(text, {
      panelToken: true,
      hoverMode: 'disabled',
      extraClasses: ['panel-' + roleClass + '-token'],
      extraData: {
        panel_surface_seg: text,
        panel_head_role: roleClass
      }
    });
  }
  return escapeHtml(text);
}
export function initializeTokenMap() {
  tokenMapState.RESOLUTION_DISPLAY_INFO_BY_CATEGORY = {
    exact_match: {
      category: 'exact_match',
      label: 'Exact Match'
    },
    exact_lemma_match: {
      category: 'exact_lemma_match',
      label: 'Exact Lemma Match'
    },
    mwt_exact_parts: {
      category: 'exact_match',
      label: 'Exact Match'
    },
    mwt_exact_partial_lemma_match: {
      category: 'exact_match',
      label: 'Exact Match'
    },
    mwt_exact_lemma_match: {
      category: 'exact_lemma_match',
      label: 'Exact Lemma Match'
    },
    lemma_override: {
      category: 'lemma_override',
      label: 'Lemma Override'
    },
    lemma_partial_override: {
      category: 'lemma_partial_override',
      label: 'Partial Lemma Override'
    },
    mwt_lemma_override: {
      category: 'lemma_override',
      label: 'Lemma Override'
    },
    mwt_lemma_partial_override: {
      category: 'lemma_partial_override',
      label: 'Partial Lemma Override'
    },
    greedy_match: {
      category: 'greedy_match',
      label: 'Greedy Segmentation'
    },
    greedy_segmentation: {
      category: 'greedy_match',
      label: 'Greedy Segmentation'
    },
    greedy: {
      category: 'greedy_match',
      label: 'Greedy Segmentation'
    }
  };
  tokenMapState._pendingPanelSurfaceLookupPromises = Object.create(null);
  return true;
}
