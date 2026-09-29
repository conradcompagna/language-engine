import { buildDebugLemmaAlignment, buildKoreanLemmaXposAlignment } from './child-fill-slices.mjs';
import {
  buildSanskritLookupRewrite,
  convertNumericPinyin,
  getCurrentLanguage,
  getDictSource,
  gunzipToText,
  jsonResponse,
  parseTsvText,
  populateDictSourceDropdown,
  reportLookupProgress,
  toAbsoluteUrl
} from './core.mjs';
import { coreState } from './core.state.mjs';
import {
  _getActiveWorkerKey,
  _queryWorker,
  buildMergedLookupPayload,
  buildSubsegmentsPayload
} from './index-cache.mjs';
import {
  hybridDpOnlyLookup,
  hybridDpOnlyLookupWithEngine,
  hybridSegmentAndHydrate,
  lookupSingle,
  maybeDecorateLookupResponse,
  parseLookupJsonBody
} from './lookup-service.mjs';
import { buildFillSurfaceSlices } from './mwt-slices.mjs';
import {
  addTimingChild,
  attachNetworkBreakdown,
  bindUi,
  buildLookupTimingTrace,
  createTimingNode,
  ensureLanguageEngine,
  lookupLangFromUrl,
  onLanguageDictSync,
  parseDebugServerMs,
  perfNowMs
} from './worker-transport.mjs';
export function wrapFetch(origFetch) {
  return function (input, init) {
    var rawUrl = typeof input === 'string' ? input : input && input.url ? input.url : '';
    var parsed = toAbsoluteUrl(rawUrl);
    if (!parsed) return origFetch(input, init);
    var path = parsed.pathname;

    // Intercept /lookup_dp_only — side-panel single token, no Trankit
    if (path === '/lookup_dp_only') {
      var q = String(parsed.searchParams.get('q') || '').trim();
      var dpLang = lookupLangFromUrl(parsed);
      if (!q || !dpLang) return origFetch(input, init);
      return hybridDpOnlyLookup(q, dpLang, {
        lemma: parsed.searchParams.get('lemma') || '',
        upos: parsed.searchParams.get('upos') || '',
        xpos: parsed.searchParams.get('xpos') || ''
      }).then(function (payload) {
        return jsonResponse(payload, 200);
      });
    }

    // Intercept /lookup — server now returns NLP-only, we do DP + hydrate
    if (path === '/lookup') {
      var requestMethod = String((init && init.method) || (input && input.method) || 'GET').toUpperCase();
      var lookupJsonBody = requestMethod === 'GET' ? null : parseLookupJsonBody(init || {});
      var jsQ = String(parsed.searchParams.get('q') || (lookupJsonBody && lookupJsonBody.q) || '').trim();
      var jsLang = lookupLangFromUrl(parsed);
      if (!String(parsed.searchParams.get('lang') || '').trim() && lookupJsonBody && lookupJsonBody.lang) {
        jsLang = String(lookupJsonBody.lang || '')
          .trim()
          .toLowerCase();
      }
      if (!jsQ || !jsLang) {
        return origFetch(input, init).then(function (resp) {
          return maybeDecorateLookupResponse(resp, parsed);
        });
      }
      var requestInput = input;
      var requestParsed = parsed;
      var sanskritRewrite = buildSanskritLookupRewrite(parsed);
      if (sanskritRewrite && sanskritRewrite.url) {
        requestParsed = sanskritRewrite.parsedUrl || parsed;
        requestInput = sanskritRewrite.url;
      }
      var debugTimingRequested = false;
      var lookupTimingRoot = debugTimingRequested
        ? createTimingNode('lookup_total', 'Lookup Total', {
            language: jsLang,
            query_length: jsQ.length
          })
        : null;
      var lookupStartedAt = lookupTimingRoot ? perfNowMs() : 0;
      var ensureEngineNode = lookupTimingRoot
        ? addTimingChild(
            lookupTimingRoot,
            createTimingNode('ensure_language_engine', 'Ensure Language Engine', {
              language: jsLang
            })
          )
        : null;
      var ensureEngineStartedAt = ensureEngineNode ? perfNowMs() : 0;
      reportLookupProgress('Loading dictionary');
      return ensureLanguageEngine(jsLang, {
        showProgress: true
      })
        .then(function (engine) {
          if (ensureEngineNode) ensureEngineNode.duration_ms = perfNowMs() - ensureEngineStartedAt;
          var lookupRequestNode = lookupTimingRoot
            ? addTimingChild(lookupTimingRoot, createTimingNode('lookup_request', '/lookup Request'))
            : null;
          var lookupRequestStartedAt = lookupRequestNode ? perfNowMs() : 0;
          var lookupNetworkNode = lookupRequestNode
            ? addTimingChild(lookupRequestNode, createTimingNode('lookup_network', '/lookup Network'))
            : null;
          var lookupNetworkStartedAt = lookupNetworkNode ? perfNowMs() : 0;
          reportLookupProgress('Analyzing text');
          return origFetch(requestInput, init).then(function (resp) {
            if (lookupNetworkNode)
              attachNetworkBreakdown(
                lookupNetworkNode,
                perfNowMs() - lookupNetworkStartedAt,
                parseDebugServerMs(resp)
              );
            if (!resp.ok) return resp;
            var lookupJsonNode = lookupRequestNode
              ? addTimingChild(lookupRequestNode, createTimingNode('lookup_json_parse', '/lookup JSON Parse'))
              : null;
            var lookupJsonStartedAt = lookupJsonNode ? perfNowMs() : 0;
            return resp.json().then(function (nlpData) {
              if (lookupJsonNode) lookupJsonNode.duration_ms = perfNowMs() - lookupJsonStartedAt;
              if (lookupRequestNode) lookupRequestNode.duration_ms = perfNowMs() - lookupRequestStartedAt;
              if (!nlpData || !nlpData.ok || !engine) {
                return maybeDecorateLookupResponse(
                  new Response(JSON.stringify(nlpData), {
                    status: 200,
                    headers: {
                      'Content-Type': 'application/json'
                    }
                  }),
                  requestParsed
                );
              }
              reportLookupProgress('Model analysis complete');
              // Fire LLM gloss request immediately using Trankit data, before hydration
              if (window._fireLlmGlossRequest) {
                try {
                  window._fireLlmGlossRequest(nlpData);
                } catch (e) {}
              }
              // Fire inflectional token decomposition alongside gloss
              if (window._fireLlmDecompRequest) {
                try {
                  window._fireLlmDecompRequest(nlpData);
                } catch (e) {}
              }
              // Fire orth breakdown request alongside gloss
              if (window._fireOrthBreakdownRequest) {
                try {
                  window._fireOrthBreakdownRequest(nlpData);
                } catch (e) {}
              }
              var hybridNode = lookupTimingRoot
                ? addTimingChild(
                    lookupTimingRoot,
                    createTimingNode('hybrid_segment_and_hydrate', 'Hybrid Segment + Hydrate', {
                      segment_count: Array.isArray(nlpData.segments) ? nlpData.segments.length : 0
                    })
                  )
                : null;
              reportLookupProgress('Building dictionary payload');
              return hybridSegmentAndHydrate(nlpData, engine, jsLang, {
                debug_trace: !!(nlpData && nlpData.debug_capture_id),
                debug_timing_node: hybridNode
              }).then(function (merged) {
                if (lookupTimingRoot && merged && merged.debug_capture_id) {
                  lookupTimingRoot.duration_ms = perfNowMs() - lookupStartedAt;
                  merged.debug_ui_lookup_timing = buildLookupTimingTrace(
                    lookupTimingRoot,
                    String(merged.debug_capture_id || ''),
                    jsLang,
                    jsQ
                  );
                }
                if (merged && Object.prototype.hasOwnProperty.call(merged, 'debug_ui_sqlite_capture')) {
                  delete merged.debug_ui_sqlite_capture;
                }
                reportLookupProgress('Dictionary payload ready');
                return jsonResponse(merged, 200);
              });
            });
          });
        })
        .catch(function (err) {
          console.error('[hybrid] /lookup error:', err);
          return origFetch(requestInput, init);
        });
    }

    // All other requests pass through unchanged
    return origFetch(input, init);
  };
}

/**
 * Fetch the custom/Gemini entry compact index for a language and inject
 * keys into the live engine via injectGeminiKey().
 * Uses /js/dict/<lang>/custom_index which queries the SQLite custom_dict_entries
 * table and returns a compact {hw, fw, db_aliases} index (gzip JSON, never cached).
 * onProgress(processed, total, loaded) called per key injected.
 */
export function _injectGeminiAdditions(engine, langCode, onProgress) {
  var code = String(langCode || '').toLowerCase();
  var url = '/js/dict/' + encodeURIComponent(code) + '/custom_index';
  return fetch(url)
    .then(function (resp) {
      if (!resp.ok) return;
      // Response is gzip JSON — decompress client-side
      return resp.arrayBuffer().then(function (buf) {
        var gzBytes = new Uint8Array(buf);
        if (typeof DecompressionStream === 'function') {
          var ds = new DecompressionStream('gzip');
          var blob = new Blob([gzBytes], {
            type: 'application/gzip'
          });
          var textStream = blob.stream().pipeThrough(ds).pipeThrough(new TextDecoderStream());
          var reader = textStream.getReader();
          var parts = [];
          function readText() {
            return reader.read().then(function (r) {
              if (r.done) return parts.join('');
              parts.push(r.value);
              return readText();
            });
          }
          return readText().then(function (text) {
            return JSON.parse(text);
          });
        }
        return gunzipToText(gzBytes).then(function (text) {
          return JSON.parse(text);
        });
      });
    })
    .then(function (index) {
      if (!index || typeof engine.injectGeminiKey !== 'function') return;
      var hw = index.hw || {};
      var keys = Object.keys(hw);
      var total = keys.length;
      if (!total) return;
      if (typeof onProgress === 'function') onProgress(0, total, 0);
      var loaded = 0;
      var lastProgressAt = 0;
      var layer = window.DictionaryNormalizationLayer;
      for (var i = 0; i < keys.length; i++) {
        var normKey = keys[i];
        var refs = hw[normKey];
        if (!Array.isArray(refs)) continue;
        for (var j = 0; j < refs.length; j++) {
          var ref = refs[j];
          // ref is [db_alias, entry_row_id]
          var alias = String((ref && ref[0]) || 'customdb');
          var eid = parseInt((ref && ref[1]) || 0, 10);
          if (eid > 0) {
            engine.injectGeminiKey(normKey, eid, alias, 'headword');
            loaded++;
          }
        }
        if (typeof onProgress === 'function') {
          var now = Date.now();
          if (i === keys.length - 1 || now - lastProgressAt > 80) {
            lastProgressAt = now;
            onProgress(i + 1, total, loaded);
          }
        }
      }
      if (loaded > 0) {
        console.log('[dict-client] Injected ' + loaded + ' custom entries for ' + code);
      }
    })
    .catch(function (err) {
      console.warn('[dict-client] Failed to load custom index for ' + langCode + ':', err);
    });
}

/**
 * Inject a single Gemini-generated entry into the live engine for langCode.
 * Also appends to the engine's TSV text store so it persists within the session.
 * entry: {headword, pos, romanization, glosses: [str], forms: [[form,label,note]]}
 * Returns Promise<void>.
 */
/**
 * Inject a newly created/persisted Gemini entry key into the compact engine.
 * entry must include {headword, entry_row_id (integer SQLite id), [db_alias]}.
 * After injection, triggers relookup of any segments containing the headword.
 */
export function injectGeminiEntry(langCode, entry) {
  var code = String(langCode || '').toLowerCase();
  var hw = String(entry.headword || '');
  var eid = parseInt(entry.entry_row_id || entry.id || '0', 10) || 0;
  var alias = String(entry.db_alias || 'customdb');
  if (!hw || !(eid > 0)) return Promise.resolve();
  return ensureLanguageEngine(code, {
    showProgress: false
  }).then(function (engine) {
    if (!engine || typeof engine.injectGeminiKey !== 'function') return;
    // Normalize the headword key the same way the engine does
    var normKey = hw;
    var layer = window.DictionaryNormalizationLayer;
    if (layer && typeof layer.normalizeLookupKeyText === 'function') {
      try {
        normKey = String(
          layer.normalizeLookupKeyText(hw, {
            langCode: code
          }) || hw
        );
      } catch (_e) {}
    }
    engine.injectGeminiKey(normKey, eid, alias, 'headword');
  });
}

/**
 * Re-run the dictionary engine lookup for a single segment, using the NLP data
 * already in existingSegResult (upos, lemma, feats, etc.).
 * Returns Promise<freshSegResult> — a fully rebuilt result object.
 */
/**
 * Re-run hybrid lookup for a single segment using existing NLP data.
 * Used after Gemini create/delete/update to update a single visible token.
 */
export function relookupOneSegment(langCode, surface, existingSegResult) {
  var code = String(langCode || '').toLowerCase();
  var seg = existingSegResult || {};
  return hybridDpOnlyLookup(surface, code, {
    lemma: seg.lemma || surface,
    upos: seg.upos || 'X',
    xpos: seg.xpos || seg.tag || '',
    mwt_parts: Array.isArray(seg.mwt_parts) ? seg.mwt_parts : []
  })
    .then(function (payload) {
      return payload || existingSegResult;
    })
    .catch(function () {
      return existingSegResult;
    });
}
export function init() {
  if (coreState.state.initialized) return;
  coreState.state.initialized = true;
  bindUi();
  populateDictSourceDropdown(getCurrentLanguage());
}

/**
 * Get raw entry data for a gemini/user-created entry from the live engine.
 * Uses engine.lookup_all() for correct key folding.
 * Returns { headword, romanization, pos, glosses: [str], forms: [[w,tag,pron]], source } or null.
 */
/**
 * Get raw Gemini entry data for editing. In hybrid mode, entries live in SQLite;
 * we fetch from /api/gemini_entry/get which queries the DB directly.
 */
export function getRawGeminiEntry(langCode, headword) {
  var code = String(langCode || '').toLowerCase();
  var url =
    '/api/gemini_entry/get?language=' +
    encodeURIComponent(code) +
    '&headword=' +
    encodeURIComponent(String(headword || ''));
  return fetch(url)
    .then(function (resp) {
      if (!resp.ok) return null;
      return resp.json().then(function (data) {
        if (!data || !data.ok || !data.entry) return null;
        var e = data.entry;
        // Normalize to the shape caller expects
        var glosses = [];
        if (Array.isArray(e.senses)) {
          for (var i = 0; i < e.senses.length; i++) {
            var sense = e.senses[i];
            if (sense && Array.isArray(sense.glosses)) {
              for (var j = 0; j < sense.glosses.length; j++) glosses.push(sense.glosses[j]);
            } else if (typeof sense === 'string') {
              glosses.push(sense);
            }
          }
        }
        return {
          headword: String(e.headword || ''),
          romanization: String(e.reading || e.romanization || ''),
          pos: String(e.pos || ''),
          glosses: glosses,
          forms: Array.isArray(e.forms) ? e.forms : [],
          commentary: String(e.commentary || ''),
          lemma: String(e.lemma || ''),
          source: String(e.source || 'gemini'),
          entry_id: String(e.entry_id || '')
        };
      });
    })
    .catch(function () {
      return null;
    });
}

/**
 * Update an existing gemini/user-created entry in the live engine.
 * Replaces the entry's fields in-place so lookups immediately reflect changes.
 * entry: { headword, romanization, pos, glosses: [str], forms: [[w,tag,pron]] }
 */
/**
 * Update a Gemini entry in-place. In hybrid mode, the entry data lives in
 * SQLite; the caller has already called /api/gemini_entry/update. The compact
 * index key doesn't change on update (same headword, same SQLite id), but we
 * invalidate the in-memory compact index so the next relookup fetches fresh
 * entry data from /js/hydrate.
 */
export function updateGeminiEntry(langCode, entry) {
  var code = String(langCode || '').toLowerCase();
  // Invalidate in-memory index so next load re-injects from DB
  delete coreState._hybridIndexByLang[code];
  // The key in the compact index doesn't change; hydrate will return updated data
  // automatically on next /js/hydrate call. Nothing else to do here.
  return Promise.resolve();
}

/**
 * Remove a Gemini entry from the compact engine index.
 * entryId is the integer SQLite id from custom_dict_entries.
 * headword is used to compute the normalized key for removeCompactKey().
 */
export function removeGeminiEntry(langCode, headwordOrEntry, entryId) {
  var code = String(langCode || '').toLowerCase();
  var payload = headwordOrEntry && typeof headwordOrEntry === 'object' ? headwordOrEntry : null;
  var hw = String(payload ? payload.headword || '' : headwordOrEntry || '');
  var eid =
    parseInt(payload ? payload.entry_row_id || payload.entry_id || payload.id || '0' : entryId || '0', 10) ||
    0;
  if (!code || !hw || !(eid > 0)) return Promise.resolve();
  return ensureLanguageEngine(code, {
    showProgress: false
  }).then(function (engine) {
    if (!engine || typeof engine.removeCompactKey !== 'function') return;
    var normKey = hw;
    var layer = window.DictionaryNormalizationLayer;
    if (layer && typeof layer.normalizeLookupKeyText === 'function') {
      try {
        normKey = String(
          layer.normalizeLookupKeyText(hw, {
            langCode: code
          }) || hw
        );
      } catch (_e) {}
    }
    engine.removeCompactKey(normKey, eid);
  });
}

// ── Worker-mode query handler ──────────────────────────────────────
// When dictionary_client.js is imported inside a Web Worker (via importScripts),
// this section sets up message handlers so the worker can run payload-building
// functions on the engine it owns. The main thread sends query messages and
// receives completed payloads back.
export function initializePublicApi() {
  if (typeof importScripts === 'function') {
    self.addEventListener('message', function (e) {
      var data = e.data;
      if (!data || !data.requestId) return;
      var engine = (self._workerEngines && self._workerEngines[data.engineKey]) || null;
      function reply(payload) {
        self.postMessage({
          type: 'query_result',
          requestId: data.requestId,
          payload: payload
        });
      }
      function replyError(msg) {
        self.postMessage({
          type: 'query_result',
          requestId: data.requestId,
          error: String(msg)
        });
      }
      try {
        // Set language for getCurrentLanguage() fallback in worker
        if (data.langCode) self.ReaderDefaultLanguage = data.langCode;
        if (data.type === 'lookup_dp_only') {
          if (!engine) return replyError('no engine for ' + data.engineKey);
          hybridDpOnlyLookupWithEngine(data.q, engine, data.langCode || '', data.opts || {})
            .then(function (payload) {
              payload.language = data.langCode || '';
              reply(payload);
            })
            .catch(replyError);
          return;
        }
        if (data.type === 'subsegments') {
          if (!engine) return replyError('no engine for ' + data.engineKey);
          var token = String(data.token || '');
          var decompose = !!data.decompose;
          var payload = buildSubsegmentsPayload(token, engine, decompose);
          payload.language = data.langCode || '';
          return reply(payload);
        }
        if (data.type === 'merged_lookup') {
          if (!engine) return replyError('no engine for ' + data.engineKey);
          hybridSegmentAndHydrate(data.lookupData, engine, data.langCode || '', data.opts || {})
            .then(reply)
            .catch(replyError);
          return;
        }
        if (data.type === 'results_by_seg') {
          if (!engine) return replyError('no engine for ' + data.engineKey);
          hybridSegmentAndHydrate(data.lookupData, engine, data.langCode || '', data.opts || {})
            .then(function (payload) {
              reply((payload && payload.results_by_seg) || []);
            })
            .catch(replyError);
          return;
        }
        if (data.type === 'inject_rows') {
          if (!engine) return replyError('no engine for ' + data.engineKey);
          var rows = data.rows || [];
          var loaded = 0;
          for (var i = 0; i < rows.length; i++) {
            if (engine._loadOneRow(rows[i], data.source || 'gemini')) loaded++;
          }
          return reply({
            loaded: loaded
          });
        }
        if (data.type === 'inject_one_row') {
          if (!engine) return replyError('no engine for ' + data.engineKey);
          engine._loadOneRow(data.row, data.source || 'gemini');
          return reply({
            ok: true
          });
        }
        if (data.type === 'has_word') {
          var found = false;
          var prefix = String(data.langCode || '').toLowerCase() + '|';
          var eKeys = Object.keys(self._workerEngines || {});
          for (var i = 0; i < eKeys.length; i++) {
            if (eKeys[i].indexOf(prefix) !== 0) continue;
            var eng = self._workerEngines[eKeys[i]];
            if (!eng) continue;
            if (eng.lookup(String(data.word || ''))) {
              found = true;
              break;
            }
            if (typeof eng.lookup_via_forms === 'function') {
              var vf = eng.lookup_via_forms(String(data.word || ''));
              if (vf && vf.length) {
                found = true;
                break;
              }
            }
          }
          return reply({
            found: found
          });
        }
        if (data.type === 'get_raw_gemini') {
          var prefix = String(data.langCode || '').toLowerCase() + '|';
          var eKeys = Object.keys(self._workerEngines || {});
          var result = null;
          for (var i = 0; i < eKeys.length; i++) {
            if (eKeys[i].indexOf(prefix) !== 0) continue;
            var eng = self._workerEngines[eKeys[i]];
            if (!eng || typeof eng.lookup_all !== 'function') continue;
            var all = eng.lookup_all(data.headword);
            for (var j = 0; j < all.length; j++) {
              var ent = all[j];
              if (!ent || !ent._source) continue;
              var glosses = [];
              if (ent._glosses_raw) {
                try {
                  var parsed = JSON.parse(ent._glosses_raw);
                  if (Array.isArray(parsed)) {
                    for (var s = 0; s < parsed.length; s++) {
                      if (parsed[s] && parsed[s].glosses) {
                        for (var g = 0; g < parsed[s].glosses.length; g++) glosses.push(parsed[s].glosses[g]);
                      }
                    }
                  }
                } catch (_) {}
              } else if (Array.isArray(ent.senses_full)) {
                for (var sf = 0; sf < ent.senses_full.length; sf++) {
                  var sense = ent.senses_full[sf];
                  if (sense && Array.isArray(sense.glosses)) {
                    for (var sg = 0; sg < sense.glosses.length; sg++) glosses.push(sense.glosses[sg]);
                  }
                }
              } else if (Array.isArray(ent.senses)) {
                for (var fs = 0; fs < ent.senses.length; fs++) {
                  if (ent.senses[fs]) glosses.push(String(ent.senses[fs]));
                }
              }
              var forms = [];
              if (ent._forms_raw) {
                try {
                  var pf = JSON.parse(ent._forms_raw);
                  if (Array.isArray(pf)) forms = pf;
                } catch (_) {}
              }
              result = {
                headword: ent.headword,
                romanization: ent.reading || '',
                pos: ent.pos_raw || ent.pos || '',
                glosses: glosses,
                forms: forms,
                commentary: ent._commentary || '',
                lemma: ent._lemma || '',
                source: ent._source || 'gemini'
              };
              break;
            }
            if (result) break;
          }
          return reply(result);
        }
        if (data.type === 'update_entry') {
          var prefix = String(data.langCode || '').toLowerCase() + '|';
          var eKeys = Object.keys(self._workerEngines || {});
          var hw = String(data.entry.headword || '');
          for (var i = 0; i < eKeys.length; i++) {
            if (eKeys[i].indexOf(prefix) !== 0) continue;
            var eng = self._workerEngines[eKeys[i]];
            if (!eng || typeof eng.lookup_all !== 'function') continue;
            var all = eng.lookup_all(hw);
            for (var j = 0; j < all.length; j++) {
              var ent = all[j];
              if (!ent || !ent._source || ent.headword !== hw) continue;
              ent.reading = convertNumericPinyin(String(data.entry.romanization || ''));
              ent.pos_raw = String(data.entry.pos || '');
              ent.pos = String(data.entry.pos || '').toLowerCase();
              var glosses = Array.isArray(data.entry.glosses) ? data.entry.glosses : [];
              var senses = glosses.map(function (g) {
                return {
                  glosses: [String(g)]
                };
              });
              if (ent._source === 'user_created')
                senses.push({
                  _source: 'user_created'
                });
              ent._glosses_raw = JSON.stringify(senses);
              delete ent.senses;
              delete ent.senses_full;
              delete ent._hydrated;
              var forms = Array.isArray(data.entry.forms) ? data.entry.forms : [];
              ent._forms_raw = JSON.stringify(forms);
              ent._forms_json = JSON.stringify(forms);
              if (data.entry.commentary !== undefined) ent._commentary = String(data.entry.commentary || '');
              if (data.entry.lemma !== undefined) ent._lemma = String(data.entry.lemma || '');
              var byWord = eng._by_word;
              var foldKey = null;
              var bwKeys = Object.keys(byWord);
              for (var k = 0; k < bwKeys.length; k++) {
                var bucket = byWord[bwKeys[k]];
                for (var b = 0; b < bucket.length; b++) {
                  if (bucket[b] === ent) {
                    foldKey = bwKeys[k];
                    break;
                  }
                }
                if (foldKey) break;
              }
              if (foldKey) eng._index_tsv_forms(ent, hw, foldKey);
              break;
            }
            break;
          }
          return reply({
            ok: true
          });
        }
        if (data.type === 'remove_entry') {
          var prefix = String(data.langCode || '').toLowerCase() + '|';
          var eKeys = Object.keys(self._workerEngines || {});
          var hw = String(data.headword || '');
          for (var i = 0; i < eKeys.length; i++) {
            if (eKeys[i].indexOf(prefix) !== 0) continue;
            var eng = self._workerEngines[eKeys[i]];
            if (!eng || !eng._by_word || !eng._form_index) continue;
            var removedEntries = [];
            var bucketKeys = Object.keys(eng._by_word);
            for (var bi = 0; bi < bucketKeys.length; bi++) {
              var bk = bucketKeys[bi];
              var bucket = Array.isArray(eng._by_word[bk]) ? eng._by_word[bk] : [];
              var kept = [];
              for (var bj = 0; bj < bucket.length; bj++) {
                var entry = bucket[bj];
                if (entry && entry.headword === hw && entry._source) {
                  removedEntries.push(entry);
                  continue;
                }
                kept.push(entry);
              }
              if (kept.length) eng._by_word[bk] = kept;
              else delete eng._by_word[bk];
            }
            if (!removedEntries.length) continue;
            var removedSet = new Set(removedEntries);
            var formKeys = Object.keys(eng._form_index);
            for (var fi = 0; fi < formKeys.length; fi++) {
              var fk = formKeys[fi];
              var hits = Array.isArray(eng._form_index[fk]) ? eng._form_index[fk] : [];
              var keptHits = [];
              for (var hi = 0; hi < hits.length; hi++) {
                var hit = hits[hi];
                if (hit && hit.entry_ref && removedSet.has(hit.entry_ref)) continue;
                keptHits.push(hit);
              }
              if (keptHits.length) eng._form_index[fk] = keptHits;
              else delete eng._form_index[fk];
            }
          }
          return reply({
            ok: true
          });
        }
        if (data.type === 'relookup_segment') {
          if (!engine) return replyError('no engine for ' + data.engineKey);
          var seg = data.existingSegResult || {};
          hybridDpOnlyLookupWithEngine(data.surface, engine, data.langCode || '', {
            lemma: seg.lemma || data.surface,
            upos: seg.upos || 'X',
            xpos: seg.xpos || seg.tag || '',
            mwt_parts: Array.isArray(seg.mwt_parts) ? seg.mwt_parts : []
          })
            .then(function (payload) {
              reply(payload || data.existingSegResult);
            })
            .catch(replyError);
          return;
        }
      } catch (err) {
        replyError(String(err.message || err));
      }
    });
  }
  window.DictionaryClient = {
    init: init,
    wrapFetch: wrapFetch,
    lookupSingle: lookupSingle,
    buildFillSurfaceSlices: buildFillSurfaceSlices,
    parseTsvText: parseTsvText,
    onLanguageDictSync: onLanguageDictSync,
    ensureLanguageEngine: ensureLanguageEngine,
    buildMergedLookupPayload: buildMergedLookupPayload,
    hasWord: function (langCode, word) {
      // Returns Promise<boolean> — checks if word exists in any engine for this language.
      var code = String(langCode || '').toLowerCase();
      var wkey = _getActiveWorkerKey(code);
      if (wkey) {
        return _queryWorker(wkey, {
          type: 'has_word',
          langCode: code,
          word: word
        }).then(function (result) {
          return !!(result && result.found);
        });
      }
      // Main-thread fallback (sync result wrapped in Promise)
      var prefix = code + '|';
      var keys = Object.keys(coreState.state.engineByLangSource || {});
      for (var i = 0; i < keys.length; i++) {
        if (keys[i].indexOf(prefix) !== 0) continue;
        var engine = coreState.state.engineByLangSource[keys[i]];
        if (!engine) continue;
        if (engine.lookup(String(word || ''))) return Promise.resolve(true);
        if (typeof engine.lookup_via_forms === 'function') {
          var viaForms = engine.lookup_via_forms(String(word || ''));
          if (viaForms && viaForms.length) return Promise.resolve(true);
        }
      }
      return Promise.resolve(false);
    },
    injectGeminiEntry: injectGeminiEntry,
    getRawGeminiEntry: getRawGeminiEntry,
    updateGeminiEntry: updateGeminiEntry,
    removeGeminiEntry: removeGeminiEntry,
    relookupOneSegment: relookupOneSegment,
    debugBuildLemmaAlignment: function (surface, lemma, xpos, langCode) {
      return buildDebugLemmaAlignment(surface, lemma, xpos, langCode || getCurrentLanguage() || '');
    },
    debugBuildKoreanLemmaXposAlignment: function (surface, lemma, xpos, langCode) {
      return buildKoreanLemmaXposAlignment(surface, lemma, xpos, langCode || 'ko');
    },
    getDictSource: getDictSource,
    isEngineReady: function (langCode) {
      var code = String(langCode || getCurrentLanguage() || '').toLowerCase();
      if (!code) return false;
      // Check for active worker
      if (_getActiveWorkerKey(code)) return true;
      // Check for main-thread engine
      var prefix = code + '|';
      var keys = Object.keys(coreState.state.engineByLangSource || {});
      for (var i = 0; i < keys.length; i++) {
        if (keys[i].indexOf(prefix) === 0 && coreState.state.engineByLangSource[keys[i]]) return true;
      }
      return false;
    }
  };
  return true;
}
