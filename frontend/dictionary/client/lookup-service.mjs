import {
  getApiBase,
  getCurrentLanguage,
  getDictSource,
  isTruthyFlag,
  jsonResponse,
  reportLookupProgress
} from './core.mjs';
import { coreState } from './core.state.mjs';
import { normalizeCanonicalEntryStore } from './entry-adapters.mjs';
import { buildFillResult } from './hydration.mjs';
import { _getActiveWorkerKey, _queryWorker } from './index-cache.mjs';
import {
  _entryRefKey,
  buildLookupDpOnlyPayload,
  buildResultsBySeg,
  buildUnknownResult,
  extractTokenBySeg
} from './lookup-payloads.mjs';
import { buildSinglePassSurfaceLookup, isMwtUdToken } from './surface-lookup.mjs';
import { hydrateSinglePassLookup } from './winner-references.mjs';
import {
  addTimingChild,
  attachNetworkBreakdown,
  createTimingNode,
  decorateLookupJson,
  ensureLanguageEngine,
  lookupLangFromUrl,
  parseDebugServerMs,
  perfNowMs
} from './worker-transport.mjs';
export function buildWinnerRefDebugUid(ref) {
  if (!ref || typeof ref !== 'object') return '';
  var storageKind =
    String(ref.storage_kind || 'sqlite')
      .trim()
      .toLowerCase() || 'sqlite';
  var dbAlias = String(ref.db_alias || '').trim();
  var entryRowId = parseInt(ref.entry_row_id, 10) || 0;
  if (!dbAlias || !(entryRowId > 0)) return '';
  var formRowId = parseInt(ref.form_row_id || 0, 10) || 0;
  return storageKind + '|' + dbAlias + '|' + entryRowId + (formRowId > 0 ? '|' + formRowId : '');
}
export function cloneWinnerRefForDebug(ref) {
  if (!ref || typeof ref !== 'object') return null;
  var entryRowId = parseInt(ref.entry_row_id, 10) || 0;
  if (!(entryRowId > 0)) return null;
  var out = {
    storage_kind:
      String(ref.storage_kind || 'sqlite')
        .trim()
        .toLowerCase() || 'sqlite',
    db_alias: String(ref.db_alias || '').trim(),
    entry_row_id: entryRowId,
    match_kind:
      String(ref.match_kind || 'headword')
        .trim()
        .toLowerCase() || 'headword',
    form_row_id: parseInt(ref.form_row_id || 0, 10) || 0,
    match_key: String(ref.match_key || '')
  };
  out.uid = buildWinnerRefDebugUid(out);
  return out;
}

// DEBUG-ONLY: annotate a cloned winner ref with normalization trace.
// Only called inside buildSqliteClientDebugCapture (already debug-gated).
// Returns the same object mutated in-place for convenience.
export function _annotateDebugRefNormKinds(clonedRef, langCode) {
  var layer = window.DictionaryNormalizationLayer;
  if (!layer || typeof layer.normalizeLookupKeyTextWithTrace !== 'function') return clonedRef;
  var rawKey = String(clonedRef.match_key || '');
  if (!rawKey) {
    clonedRef._norm_kinds = [];
    return clonedRef;
  }
  try {
    var result = layer.normalizeLookupKeyTextWithTrace(rawKey, {
      langCode: String(langCode || '')
        .trim()
        .toLowerCase(),
      phase: 'lookup_key'
    });
    clonedRef._norm_kinds = Array.isArray(result.norm_kinds) ? result.norm_kinds : [];
  } catch (_e) {
    clonedRef._norm_kinds = [];
  }
  return clonedRef;
}
export function parseLookupJsonBody(init) {
  if (!init || init.body == null) return null;
  if (typeof init.body === 'string') {
    try {
      var parsed = JSON.parse(init.body);
      return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (_e) {
      return null;
    }
  }
  return null;
}
export function buildSqliteClientDebugCapture(
  nlpData,
  langCode,
  segments,
  tokBySeg,
  lookupsBySegIdx,
  refsBySegIdx,
  allWinnerRefs,
  uniqueRefs
) {
  var rawRefs = Array.isArray(allWinnerRefs) ? allWinnerRefs : [];
  var dedupedRefs = Array.isArray(uniqueRefs) ? uniqueRefs : [];
  var tokenRows = Array.isArray(tokBySeg) ? tokBySeg : [];
  var lookupRows = Array.isArray(lookupsBySegIdx) ? lookupsBySegIdx : [];
  var rawRefsBySeg = Array.isArray(refsBySegIdx) ? refsBySegIdx : [];
  var segmentTexts = Array.isArray(segments) ? segments : [];
  var buckets = Object.create(null);
  var bucketOrder = [];
  var segmentWinners = [];
  function pushUniqueValue(target, rawValue) {
    if (!Array.isArray(target)) return;
    var value = String(rawValue || '');
    if (!value) return;
    for (var i = 0; i < target.length; i++) {
      if (String(target[i] || '') === value) return;
    }
    target.push(value);
  }
  function pushUniqueIndex(target, rawValue) {
    if (!Array.isArray(target)) return;
    var value = parseInt(rawValue, 10);
    if (!isFinite(value)) return;
    for (var i = 0; i < target.length; i++) {
      if (parseInt(target[i], 10) === value) return;
    }
    target.push(value);
  }
  for (var si = 0; si < segmentTexts.length; si++) {
    var word = String(segmentTexts[si] || '');
    var tok = tokenRows[si] || {};
    var surfaceLookup = lookupRows[si] || {};
    var refs = Array.isArray(rawRefsBySeg[si]) ? rawRefsBySeg[si] : [];
    var debugRefs = [];
    for (var ri = 0; ri < refs.length; ri++) {
      var clonedRef = cloneWinnerRefForDebug(refs[ri]);
      if (!clonedRef) continue;
      _annotateDebugRefNormKinds(clonedRef, langCode);
      debugRefs.push(clonedRef);
      var uid = String(clonedRef.uid || '');
      if (!uid) continue;
      var bucket = buckets[uid];
      if (!bucket) {
        bucket = {
          uid: uid,
          ref: clonedRef,
          raw_count: 0,
          segment_indexes: [],
          segment_texts: [],
          match_keys: []
        };
        buckets[uid] = bucket;
        bucketOrder.push(uid);
      }
      bucket.raw_count += 1;
      pushUniqueIndex(bucket.segment_indexes, si);
      pushUniqueValue(bucket.segment_texts, word);
      pushUniqueValue(bucket.match_keys, clonedRef.match_key);
    }
    var resolutionMeta =
      surfaceLookup && typeof surfaceLookup.resolution_meta === 'object' ? surfaceLookup.resolution_meta : {};
    segmentWinners.push({
      segment_index: si,
      segment_text: word,
      lemma: String(tok.lemma || ''),
      upos: String(tok.upos || ''),
      xpos: String(tok.tag || tok.xpos || ''),
      deprel: String(tok.dep || tok.deprel || ''),
      resolved_via: String(surfaceLookup.resolved_via || ''),
      fill_mode: String((surfaceLookup.fill && surfaceLookup.fill.mode) || '')
        .trim()
        .toLowerCase(),
      resolution_category: String(resolutionMeta.category || ''),
      resolution_route_code: String(resolutionMeta.route_code || ''),
      winner_ref_count: debugRefs.length,
      winner_refs: debugRefs
    });
  }
  var dedupeRows = [];
  for (var bi = 0; bi < bucketOrder.length; bi++) {
    var bucket = buckets[bucketOrder[bi]];
    if (!bucket) continue;
    dedupeRows.push({
      uid: bucket.uid,
      raw_count: Number(bucket.raw_count || 0),
      kept_after_dedupe: false,
      segment_indexes: Array.isArray(bucket.segment_indexes) ? bucket.segment_indexes.slice() : [],
      segment_texts: Array.isArray(bucket.segment_texts) ? bucket.segment_texts.slice() : [],
      match_keys: Array.isArray(bucket.match_keys) ? bucket.match_keys.slice() : [],
      ref: bucket.ref
    });
  }
  var rawWinnerRefs = [];
  for (var rwi = 0; rwi < rawRefs.length; rwi++) {
    var rawClone = cloneWinnerRefForDebug(rawRefs[rwi]);
    if (rawClone) {
      _annotateDebugRefNormKinds(rawClone, langCode);
      rawWinnerRefs.push(rawClone);
    }
  }
  var dedupedWinnerRefs = [];
  var keptByUid = Object.create(null);
  for (var dui = 0; dui < dedupedRefs.length; dui++) {
    var dedupedClone = cloneWinnerRefForDebug(dedupedRefs[dui]);
    if (!dedupedClone) continue;
    _annotateDebugRefNormKinds(dedupedClone, langCode);
    dedupedWinnerRefs.push(dedupedClone);
    if (dedupedClone.uid) keptByUid[dedupedClone.uid] = true;
  }
  for (var dri = 0; dri < dedupeRows.length; dri++) {
    var row = dedupeRows[dri];
    row.kept_after_dedupe = !!keptByUid[String(row.uid || '')];
  }
  dedupeRows.sort(function (a, b) {
    var aCount = Number(a.raw_count || 0);
    var bCount = Number(b.raw_count || 0);
    if (aCount !== bCount) return bCount - aCount;
    return String(a.uid || '').localeCompare(String(b.uid || ''));
  });
  return {
    debug_capture_id: String((nlpData && nlpData.debug_capture_id) || '').trim(),
    language: String(langCode || '')
      .trim()
      .toLowerCase(),
    q: String((nlpData && nlpData.q) || ''),
    display_text: String((nlpData && nlpData.display_text) || ''),
    raw_winner_ref_count: rawWinnerRefs.length,
    unique_winner_ref_count: dedupedWinnerRefs.length,
    segment_winners: segmentWinners,
    raw_winner_refs: rawWinnerRefs,
    deduped_winner_refs: dedupedWinnerRefs,
    dedupe_rows: dedupeRows,
    hydrate_request: {
      method: 'POST',
      path: '/js/hydrate',
      payload: {
        lang: String(langCode || '')
          .trim()
          .toLowerCase(),
        winner_refs: dedupedWinnerRefs
      }
    }
  };
}
export function maybeDecorateLookupResponse(response, parsedUrl) {
  if (!response || !response.ok) return Promise.resolve(response);
  var contentType = String(response.headers.get('Content-Type') || '');
  if (contentType.indexOf('application/json') < 0) return Promise.resolve(response);
  return response
    .clone()
    .json()
    .then(function (data) {
      if (!data || !data.ok) return response;
      var langCode = lookupLangFromUrl(parsedUrl) || String(data.language || '');
      var dictSource = getDictSource();
      return decorateLookupJson(data, langCode, dictSource, {
        debug_trace: !!(data && data.debug_capture_id)
      }).then(
        function (merged) {
          var captureId = String((merged && merged.debug_capture_id) || '').trim();
          if (captureId) {
            if (merged && Object.prototype.hasOwnProperty.call(merged, 'debug_ui_sqlite_capture')) {
              delete merged.debug_ui_sqlite_capture;
            }
          }
          return jsonResponse(merged, response.status);
        },
        function (err) {
          console.error('Dictionary lookup merge failed:', err);
          return jsonResponse(data, response.status);
        }
      );
    })
    .catch(function () {
      return response;
    });
}
export function handleLookupRawRequest(parsedUrl) {
  var q = String(parsedUrl.searchParams.get('q') || '').trim();
  var langCode = lookupLangFromUrl(parsedUrl);
  var lemma = String(parsedUrl.searchParams.get('lemma') || '');
  var upos = String(parsedUrl.searchParams.get('upos') || '');
  var xpos = String(parsedUrl.searchParams.get('xpos') || '');
  // Try worker path
  var wkey = _getActiveWorkerKey(langCode);
  if (wkey) {
    return _queryWorker(wkey, {
      type: 'lookup_dp_only',
      q: q,
      langCode: langCode,
      opts: {
        lemma: lemma,
        upos: upos,
        xpos: xpos
      }
    })
      .then(function (payload) {
        if (isTruthyFlag(parsedUrl.searchParams.get('exact'))) payload.exact = true;
        payload.language = langCode;
        return jsonResponse(payload, 200);
      })
      .catch(function (err) {
        console.error('Worker lookup raw error:', err);
        return jsonResponse(
          {
            ok: false,
            error: 'worker raw lookup failed'
          },
          500
        );
      });
  }
  // Main-thread fallback
  return ensureLanguageEngine(langCode, {
    source: getDictSource(),
    showProgress: false
  })
    .then(function (engine) {
      return hybridDpOnlyLookupWithEngine(q, engine, langCode, {
        lemma: lemma,
        upos: upos,
        xpos: xpos
      }).then(function (payload) {
        if (isTruthyFlag(parsedUrl.searchParams.get('exact'))) payload.exact = true;
        payload.language = langCode;
        return jsonResponse(payload, 200);
      });
    })
    .catch(function (err) {
      console.error('lookup raw client error:', err);
      return jsonResponse(
        {
          ok: false,
          error: 'client raw lookup failed'
        },
        500
      );
    });
}

// ── Hybrid lookup helpers ─────────────────────────────────────────────────
export function appendWinnerRef(refs, ref) {
  if (!ref || !ref._winner_ref) return;
  refs.push({
    storage_kind:
      String(ref.storage_kind || 'sqlite')
        .trim()
        .toLowerCase() || 'sqlite',
    db_alias: String(ref.db_alias || ''),
    entry_row_id: parseInt(ref.entry_row_id, 10) || 0,
    match_kind: String(ref.match_kind || 'headword'),
    form_row_id: parseInt(ref.form_row_id || 0, 10) || 0,
    match_key: String(ref.match_key || '')
  });
}

/**
 * Extract winner refs from a compact-mode fill result.
 * Exact whole-token matches can carry multiple compact refs on fill.entries;
 * hydrate all of them so same-surface entries are not collapsed to one row.
 * Returns array of {storage_kind, db_alias, entry_row_id, match_kind, form_row_id, match_key}
 */
export function extractWinnerRefs(fillResult) {
  var refs = [];
  var fills = (fillResult && fillResult.fills) || [];
  for (var i = 0; i < fills.length; i++) {
    var f = fills[i];
    if (!f || f.source === 'UNKNOWN') continue;
    var exactEntries = Array.isArray(f.entries) ? f.entries : [];
    if (exactEntries.length) {
      for (var ei = 0; ei < exactEntries.length; ei++) {
        appendWinnerRef(refs, exactEntries[ei]);
      }
      continue;
    }
    appendWinnerRef(refs, f._winner_ref);
  }
  return refs;
}
export function extractWinnerRefsFromSinglePassLookup(surfaceLookup) {
  var refs = extractWinnerRefs(surfaceLookup && surfaceLookup.fill);
  var children =
    surfaceLookup && Array.isArray(surfaceLookup.ko_compound_lemma_children)
      ? surfaceLookup.ko_compound_lemma_children
      : [];
  for (var i = 0; i < children.length; i++) {
    var childLookup = children[i] && children[i].lookup;
    if (!childLookup) continue;
    refs = refs.concat(extractWinnerRefsFromSinglePassLookup(childLookup));
  }
  return refs;
}

/**
 * Deduplicate winner refs by (storage_kind|db_alias|entry_row_id|form_row_id).
 * Form matches include form_row_id so two different forms of the same entry
 * are kept as separate refs and hydrated separately.
 */
export function deduplicateWinnerRefs(refs) {
  var seen = Object.create(null);
  var out = [];
  for (var i = 0; i < refs.length; i++) {
    var r = refs[i];
    if (!r.db_alias || !(r.entry_row_id > 0)) continue;
    var fid = parseInt(r.form_row_id, 10) || 0;
    var uid = r.storage_kind + '|' + r.db_alias + '|' + r.entry_row_id + (fid > 0 ? '|' + fid : '');
    if (seen[uid]) continue;
    seen[uid] = true;
    out.push(r);
  }
  return out;
}

/**
 * POST winner refs to /js/hydrate and return {entry_store, ref_to_key}.
 */
export function hydrateWinnerRefs(langCode, winnerRefs, options) {
  if (!winnerRefs.length)
    return Promise.resolve({
      entry_store: {},
      ref_to_key: {},
      form_overlays: {}
    });
  options = options || {};
  var apiBase = getApiBase();
  var captureId = String(options.debug_capture_id || '').trim();
  var timingNode =
    options.debug_timing_node && typeof options.debug_timing_node === 'object'
      ? options.debug_timing_node
      : null;
  var payload = {
    lang: langCode,
    winner_refs: winnerRefs
  };
  var requestStartedAt = timingNode ? perfNowMs() : 0;
  var networkNode = timingNode
    ? addTimingChild(
        timingNode,
        createTimingNode('hydrate_network', '/js/hydrate Network', {
          winner_ref_count: winnerRefs.length
        })
      )
    : null;
  var networkStartedAt = networkNode ? perfNowMs() : 0;
  return fetch(apiBase + '/hydrate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  })
    .then(function (resp) {
      if (networkNode)
        attachNetworkBreakdown(networkNode, perfNowMs() - networkStartedAt, parseDebugServerMs(resp));
      var jsonNode = timingNode
        ? addTimingChild(timingNode, createTimingNode('hydrate_json_parse', '/js/hydrate JSON Parse'))
        : null;
      var jsonStartedAt = jsonNode ? perfNowMs() : 0;
      return resp.json().then(function (data) {
        if (jsonNode) jsonNode.duration_ms = perfNowMs() - jsonStartedAt;
        if (timingNode) timingNode.duration_ms = perfNowMs() - requestStartedAt;
        return data;
      });
    })
    .then(function (data) {
      return {
        entry_store: data.entry_store || {},
        ref_to_key: data.ref_to_key || {},
        form_overlays: data.form_overlays || {}
      };
    });
}

/**
 * Run DP segmentation + hydrate for all segments in an NLP payload.
 * Returns a promise resolving to the full merged payload
 * (same shape as /lookup output).
 */
export function hybridSegmentAndHydrate(nlpData, engine, langCode, options) {
  options = options || {};
  var includeDebugTrace = !!options.debug_trace;
  var timingNode =
    options.debug_timing_node && typeof options.debug_timing_node === 'object'
      ? options.debug_timing_node
      : null;
  var hybridStartedAt = timingNode ? perfNowMs() : 0;
  var segments = Array.isArray(nlpData.segments) ? nlpData.segments : [];
  var tokBySeg = extractTokenBySeg(nlpData);
  var allWinnerRefs = [];
  var lookupsBySegIdx = [];
  var refsBySegIdx = includeDebugTrace ? [] : null;
  var surfaceLookupNode = timingNode
    ? addTimingChild(
        timingNode,
        createTimingNode('surface_lookups', 'Surface Lookups', {
          segment_count: segments.length
        })
      )
    : null;
  var surfaceLookupStartedAt = surfaceLookupNode ? perfNowMs() : 0;
  for (var i = 0; i < segments.length; i++) {
    var word = String(segments[i] || '');
    var tok = tokBySeg[i] || {};
    var upos = String(tok.upos || 'X');
    var lemma = String(tok.lemma || '');
    var xpos = String(tok.tag || '');
    var surfaceLookup = buildSinglePassSurfaceLookup(word, lemma, engine, upos, xpos, includeDebugTrace, {
      skipWholeSurfaceExact: isMwtUdToken(tok),
      mwt_parts: Array.isArray(tok.mwt_parts) ? tok.mwt_parts : []
    });
    var refs = extractWinnerRefsFromSinglePassLookup(surfaceLookup);
    lookupsBySegIdx.push(surfaceLookup);
    if (refsBySegIdx) refsBySegIdx.push(refs);
    allWinnerRefs = allWinnerRefs.concat(refs);
  }
  if (surfaceLookupNode) surfaceLookupNode.duration_ms = perfNowMs() - surfaceLookupStartedAt;
  reportLookupProgress('Dictionary matches found');
  var dedupeNode = timingNode
    ? addTimingChild(
        timingNode,
        createTimingNode('dedupe_winner_refs', 'Deduplicate Winner Refs', {
          raw_winner_ref_count: allWinnerRefs.length
        })
      )
    : null;
  var dedupeStartedAt = dedupeNode ? perfNowMs() : 0;
  var uniqueRefs = deduplicateWinnerRefs(allWinnerRefs);
  if (dedupeNode) {
    dedupeNode.duration_ms = perfNowMs() - dedupeStartedAt;
    dedupeNode.meta.unique_winner_ref_count = uniqueRefs.length;
  }
  var sqliteDebugCapture = includeDebugTrace
    ? buildSqliteClientDebugCapture(
        nlpData,
        langCode,
        segments,
        tokBySeg,
        lookupsBySegIdx,
        refsBySegIdx,
        allWinnerRefs,
        uniqueRefs
      )
    : null;
  var hydrateRequestNode = timingNode
    ? addTimingChild(
        timingNode,
        createTimingNode('hydrate_request', 'Hydrate Request', {
          winner_ref_count: uniqueRefs.length
        })
      )
    : null;
  reportLookupProgress('Loading dictionary entries');
  return hydrateWinnerRefs(langCode, uniqueRefs, {
    debug_capture_id: includeDebugTrace ? String(nlpData.debug_capture_id || '') : '',
    debug_timing_node: hydrateRequestNode
  }).then(function (hydrateResult) {
    var normalizeHydrateNode = timingNode
      ? addTimingChild(timingNode, createTimingNode('normalize_hydrate_payload', 'Normalize Hydrate Payload'))
      : null;
    var normalizeHydrateStartedAt = normalizeHydrateNode ? perfNowMs() : 0;
    var entryStore = normalizeCanonicalEntryStore(hydrateResult.entry_store || {});
    var formOverlays = hydrateResult.form_overlays || {};
    if (normalizeHydrateNode) normalizeHydrateNode.duration_ms = perfNowMs() - normalizeHydrateStartedAt;
    var hydrateLookupNode = timingNode
      ? addTimingChild(
          timingNode,
          createTimingNode('hydrate_surface_lookups', 'Hydrate Surface Lookups', {
            segment_count: lookupsBySegIdx.length
          })
        )
      : null;
    var hydrateLookupStartedAt = hydrateLookupNode ? perfNowMs() : 0;
    var hydratedLookups = [];
    for (var si = 0; si < lookupsBySegIdx.length; si++) {
      hydratedLookups.push(
        hydrateSinglePassLookup(
          lookupsBySegIdx[si],
          entryStore,
          hydrateResult.ref_to_key || {},
          engine,
          formOverlays
        )
      );
    }
    if (hydrateLookupNode) hydrateLookupNode.duration_ms = perfNowMs() - hydrateLookupStartedAt;
    var buildResultsNode = timingNode
      ? addTimingChild(
          timingNode,
          createTimingNode('build_results_by_seg', 'Build Results By Segment', {
            segment_count: segments.length
          })
        )
      : null;
    reportLookupProgress('Assembling results');
    var buildResultsStartedAt = buildResultsNode ? perfNowMs() : 0;
    var resultsBySeg = buildResultsBySeg(nlpData, engine, {
      debug_trace: includeDebugTrace,
      precomputed_surface_lookups: hydratedLookups
    });
    if (buildResultsNode) buildResultsNode.duration_ms = perfNowMs() - buildResultsStartedAt;
    var buildPayloadNode = timingNode
      ? addTimingChild(timingNode, createTimingNode('build_merged_payload', 'Build Merged Payload'))
      : null;
    var buildPayloadStartedAt = buildPayloadNode ? perfNowMs() : 0;
    var merged = {
      ok: true,
      display_text: nlpData.display_text || '',
      q: nlpData.q || '',
      debug_capture_id: String(nlpData.debug_capture_id || ''),
      segments: nlpData.segments,
      segment_offsets: nlpData.segment_offsets,
      ud_overlay: nlpData.ud_overlay,
      grammar_overlay: nlpData.grammar_overlay,
      results_by_seg: resultsBySeg,
      entry_store: entryStore,
      ref_to_key: hydrateResult.ref_to_key || {},
      form_overlays: formOverlays,
      language: langCode,
      lookup_quota: nlpData.lookup_quota || null
    };
    if (sqliteDebugCapture) merged.debug_ui_sqlite_capture = sqliteDebugCapture;
    if (buildPayloadNode) buildPayloadNode.duration_ms = perfNowMs() - buildPayloadStartedAt;

    // Set results[0] = first non-punct segment (for legacy compat)
    merged.results = [];
    for (var ri = 0; ri < resultsBySeg.length; ri++) {
      if (resultsBySeg[ri] && resultsBySeg[ri].source !== 'PUNCT') {
        merged.results.push(resultsBySeg[ri]);
        break;
      }
    }
    if (timingNode) timingNode.duration_ms = perfNowMs() - hybridStartedAt;
    return merged;
  });
}

/**
 * Build a single segment result object from a compact fill + hydrated entries.
 * This produces the same shape as buildResultsBySeg() in the original client.
 */
export function buildHybridSegResult(segInfo, entryStore, refToKey, langCode, nlpData, segIdx) {
  var fill = segInfo.fill;
  var refs = segInfo.refs;
  var word = segInfo.word;
  var tok = segInfo.tok || {};
  var upos = String(tok.upos || 'X');
  var xpos = String(tok.tag || '');
  var deprel = String(tok.dep || 'dep');
  var lemma = String(tok.lemma || word);
  var feats = String(tok.feats || '');
  var fills = (fill && fill.fills) || [];
  var uposColor = coreState.UPOS_COLORS[upos] || '#e5e7eb';
  if (!fills.length || (fills.length === 1 && fills[0].source === 'UNKNOWN')) {
    return buildUnknownResult(word, upos, xpos, deprel, lemma, feats, segIdx);
  }

  // Collect entry_ids for this segment from the hydrated entry_store
  var entryIds = [];
  var hydratedEntries = [];
  for (var i = 0; i < refs.length; i++) {
    var r = refs[i];
    var _rfid = parseInt(r.form_row_id, 10) || 0;
    var wireKey = r.storage_kind + '|' + r.db_alias + '|' + r.entry_row_id + (_rfid > 0 ? '|' + _rfid : '');
    var ekey = refToKey[wireKey];
    if (ekey && entryStore[ekey]) {
      entryIds.push(ekey);
      hydratedEntries.push(entryStore[ekey]);
    }
  }
  if (!hydratedEntries.length) {
    return buildUnknownResult(word, upos, xpos, deprel, lemma, feats, segIdx);
  }
  var primary = hydratedEntries[0];
  var senses = primary.senses || [];
  var reading = primary.reading || '';
  var pos = primary.pos || upos;
  var headword = primary.headword || word;

  // Helper to collect entry IDs from a fill row, with fallback chain
  function collectHybridFillEntryIds(fillRow, refToKey) {
    var row = fillRow && typeof fillRow === 'object' ? fillRow : {};
    var out = [];
    var seen = Object.create(null);
    function pushId(raw) {
      var id = String(raw || '').trim();
      if (!id || seen[id]) return;
      seen[id] = true;
      out.push(id);
    }

    // Preferred: prepared UI refs
    var directRefs = Array.isArray(row.entry_refs) ? row.entry_refs : [];
    for (var i = 0; i < directRefs.length; i++) pushId(directRefs[i]);
    var atomicHover = Array.isArray(row.atomic_entry_refs_hover) ? row.atomic_entry_refs_hover : [];
    for (var j = 0; j < atomicHover.length; j++) pushId(atomicHover[j]);
    var atomicAll = Array.isArray(row.atomic_entry_refs_all) ? row.atomic_entry_refs_all : [];
    for (var k = 0; k < atomicAll.length; k++) pushId(atomicAll[k]);

    // Fallback: raw hydrated entries still attached
    var entries = Array.isArray(row.entries) ? row.entries : [];
    for (var ei = 0; ei < entries.length; ei++) {
      pushId(_entryRefKey(entries[ei]));
    }

    // Last fallback: compact winner ref
    if (!out.length && row._winner_ref) {
      var ref = row._winner_ref;
      var _wkfid = parseInt(ref.form_row_id, 10) || 0;
      var wk =
        (String(ref.storage_kind || 'sqlite')
          .trim()
          .toLowerCase() || 'sqlite') +
        '|' +
        ref.db_alias +
        '|' +
        ref.entry_row_id +
        (_wkfid > 0 ? '|' + _wkfid : '');
      pushId(refToKey[wk] || '');
    }
    return out;
  }

  // Build fill objects referencing entry_store keys
  var fillObjs = [];
  for (var fi = 0; fi < fills.length; fi++) {
    var f = fills[fi] || {};
    if (!f || f.source === 'UNKNOWN') {
      fillObjs.push({
        text: f.text || word,
        source: 'UNKNOWN',
        entry_ids: []
      });
      continue;
    }
    var rowEntryIds = collectHybridFillEntryIds(f, refToKey);
    fillObjs.push({
      text: f.text || word,
      head: headword,
      source: rowEntryIds.length ? 'DICT' : 'UNKNOWN',
      entry_ids: rowEntryIds,
      start: f.start !== undefined ? f.start : null,
      end: f.end !== undefined ? f.end : null
    });
  }

  // Segment offsets for char positions
  var segOffsets = Array.isArray(nlpData.segment_offsets) ? nlpData.segment_offsets[segIdx] : null;
  return {
    text: word,
    head: headword,
    roman: reading,
    pos: pos,
    upos: upos,
    xpos: xpos,
    deprel: deprel,
    lemma: lemma,
    feats: feats,
    senses: senses,
    source: 'DICT',
    fills: fillObjs,
    entry_ids: entryIds,
    color: uposColor,
    start: segOffsets ? segOffsets[0] : null,
    end: segOffsets ? segOffsets[1] : null,
    resolution: {
      category: 'surface',
      resolved_via: 'surface',
      fill_mode: fill.mode || 'exact'
    }
  };
}

/**
 * Single-token hybrid lookup (for /lookup_dp_only intercept).
 * Does NOT call Trankit — lemma/upos/xpos come from URL params.
 */
export function hybridDpOnlyLookupWithEngine(word, engine, langCode, opts) {
  opts = opts || {};
  var lemma = String(opts.lemma || '');
  var upos = String(opts.upos || 'X')
    .trim()
    .toUpperCase();
  var xpos = String(opts.xpos || '');
  var mwtParts = Array.isArray(opts.mwt_parts) ? opts.mwt_parts : [];
  if (!engine) {
    return Promise.resolve({
      ok: false,
      error: 'no engine for ' + langCode
    });
  }

  // Fuzzy panel mode is a fully standalone path: no DP, no segmentation,
  // no lemma/exact side-channels. Tiered codepoint-level edit distance over
  // the compact index only. Tier 0 == exact.
  var surfaceLookup;
  if (opts.fuzzyPanel && engine && typeof engine.fuzzyLookupKeysTiered === 'function') {
    var fuzzy = engine.fuzzyLookupKeysTiered(word);
    var fuzzyStubs = fuzzy && fuzzy.stubs ? fuzzy.stubs : [];
    var fuzzyTier = fuzzy && typeof fuzzy.tier === 'number' ? fuzzy.tier : -1;
    if (fuzzyStubs.length) {
      var fuzzyFillResult = buildFillResult(word, fuzzyStubs, 'fuzzy_tier_' + fuzzyTier);
      surfaceLookup = {
        exact_entries: fuzzyStubs.slice(),
        fill: fuzzyFillResult.fill,
        all_entries: fuzzyStubs.slice(),
        preferred_entries: fuzzyStubs.slice(),
        dict_head: word,
        resolved_via: 'fuzzy',
        fuzzy_tier: fuzzyTier,
        lemma_hint_data: {
          lemma_hint_objects: [],
          lemma_differs_from_surface: false
        },
        lemma_oracle_used: false,
        lemma_oracle_outcome: 'fuzzy'
      };
    } else {
      surfaceLookup = {
        exact_entries: [],
        fill: {
          mode: 'fuzzy_miss',
          fills: [],
          has_known: false,
          has_unknown: true
        },
        all_entries: [],
        preferred_entries: [],
        dict_head: word,
        resolved_via: 'fuzzy',
        fuzzy_tier: -1,
        lemma_hint_data: {
          lemma_hint_objects: [],
          lemma_differs_from_surface: false
        },
        lemma_oracle_used: false,
        lemma_oracle_outcome: 'fuzzy_miss'
      };
    }
  } else {
    surfaceLookup = buildSinglePassSurfaceLookup(word, lemma, engine, upos, xpos, false, {
      skipWholeSurfaceExact: mwtParts.length > 1,
      mwt_parts: mwtParts
    });
  }
  var refs = extractWinnerRefsFromSinglePassLookup(surfaceLookup);
  var uniqueRefs = deduplicateWinnerRefs(refs);
  return hydrateWinnerRefs(langCode, uniqueRefs).then(function (hydrateResult) {
    var entryStore = normalizeCanonicalEntryStore(hydrateResult.entry_store || {});
    var formOverlays = hydrateResult.form_overlays || {};
    var hydratedLookup = hydrateSinglePassLookup(
      surfaceLookup,
      entryStore,
      hydrateResult.ref_to_key || {},
      engine,
      formOverlays
    );
    var payload = buildLookupDpOnlyPayload(word, engine, {
      lemma: lemma,
      upos: upos,
      xpos: xpos,
      mwt_parts: mwtParts,
      surface_lookup: hydratedLookup
    });
    payload.entry_store = entryStore;
    payload.ref_to_key = hydrateResult.ref_to_key || {};
    payload.form_overlays = formOverlays;
    payload.language = langCode;
    return payload;
  });
}
export function hybridDpOnlyLookup(word, langCode, opts) {
  return ensureLanguageEngine(langCode, {
    showProgress: false
  }).then(function (engine) {
    return hybridDpOnlyLookupWithEngine(word, engine, langCode, opts || {});
  });
}
export function lookupSingle(word, langCode, opts) {
  var q = String(word || '').trim();
  var code = String(langCode || getCurrentLanguage() || '')
    .trim()
    .toLowerCase();
  if (!q)
    return Promise.resolve({
      ok: false,
      error: 'empty'
    });
  if (!code)
    return Promise.resolve({
      ok: false,
      error: 'missing language'
    });
  return hybridDpOnlyLookup(q, code, opts || {});
}
