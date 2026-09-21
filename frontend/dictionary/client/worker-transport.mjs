import {
  cacheKey,
  clearCustomUploadRecord,
  customUploadLabel,
  evictAllEnginesExcept,
  evictBuiltinIndexMemoryExcept,
  evictCustomEngineCache,
  findEngineCacheKey,
  getCurrentLanguage,
  getCustomUploadRecord,
  getDictSource,
  gunzipToText,
  gzipBlobToUint8,
  hideDictProgress,
  hideTsvPill,
  loadLanguageMeta,
  populateDictSourceDropdown,
  requestMatchesCurrentSelection,
  setCustomUploadRecord,
  setStatus,
  showDictProgress,
  showTsvPill,
  updateDictSourceUI
} from './core.mjs';
import { coreState } from './core.state.mjs';
import {
  _getActiveWorkerKey,
  _queryWorker,
  buildEngineFromGzipBytes,
  buildEngineFromRows,
  buildGeminiAdditionProgressMessage,
  buildIndexDownloadProgressMessage,
  buildIndexOpenProgressMessage,
  countEngineEntries
} from './index-cache.mjs';
import { hybridSegmentAndHydrate } from './lookup-service.mjs';
import { _injectGeminiAdditions } from './public-api.mjs';
export /**
 * Reconstruct a DictionaryEngine from the raw _by_word and _form_index
 * maps transferred from the Worker. Resolves entry_ref pointers in
 * form hits from [foldKey, bucketIdx] tuples back to object references.
 */
/**
 * Build a dictionary engine from pre-parsed rows in a Worker.
 * Falls back to main-thread buildEngineFromRows if Workers unavailable.
 */
function buildEngineFromRowsOffThread(langCode, rows) {
  // Custom engines are small — always build on main thread to keep things simple.
  // The permanent worker architecture is for the large builtin dictionaries.
  return Promise.resolve(buildEngineFromRows(langCode, rows));
  /* Legacy off-thread build (disabled — worker no longer returns engine data):
  if (typeof Worker !== "function") {
    return Promise.resolve(buildEngineFromRows(langCode, rows));
  }
  try {
    var urls = _discoverEngineScriptUrls();
    if (!urls.engineUrl) return Promise.resolve(buildEngineFromRows(langCode, rows));
     var workerBlob = new Blob([_getWorkerCode(urls)], { type: "application/javascript" });
    var workerUrl = URL.createObjectURL(workerBlob);
    var worker = new Worker(workerUrl);
     return new Promise(function(resolve, reject) {
      worker.onmessage = function(e) {
        var msg = e.data;
        if (msg.type === "error") {
          worker.terminate(); URL.revokeObjectURL(workerUrl);
          reject(new Error(msg.message || "Worker build failed"));
          return;
        }
        if (msg.type === "done") {
          worker.terminate(); URL.revokeObjectURL(workerUrl);
          if (!msg.byWord) { resolve(null); return; }
          resolve(_reconstructEngineFromWorkerData(msg.langCode, msg.byWord, msg.formIndex));
        }
      };
      worker.onerror = function(err) {
        worker.terminate(); URL.revokeObjectURL(workerUrl);
        reject(err);
      };
      worker.postMessage({ type: "build_rows", langCode: langCode, rows: rows });
    });
  } catch (_e) {
    return Promise.resolve(buildEngineFromRows(langCode, rows));
  }
  */
}
export function _reconstructEngineFromWorkerData(langCode, byWord, formIndex) {
  var engine = new window.DictionaryEngine(langCode);
  engine._by_word = byWord;
  engine._form_index = formIndex;

  // Resolve _entry_ref_key tuples → object references
  var fiKeys = Object.keys(formIndex);
  for (var fi = 0; fi < fiKeys.length; fi++) {
    var hits = formIndex[fiKeys[fi]];
    for (var hi = 0; hi < hits.length; hi++) {
      var hit = hits[hi];
      if (hit._entry_ref_key) {
        var refKey = hit._entry_ref_key;
        var bucket = byWord[refKey[0]];
        if (bucket && refKey[1] < bucket.length) {
          hit.entry_ref = bucket[refKey[1]];
        }
        delete hit._entry_ref_key;
      }
    }
  }
  return engine;
}
export function filterAugmentEntriesByEngine(entries, builtinEngine) {
  var src = Array.isArray(entries) ? entries : [];
  if (!builtinEngine || !builtinEngine._by_word) return src;
  var lookupKeyFn = window.DictionaryEngine && window.DictionaryEngine.lookupKey;
  var langCode = builtinEngine._lang_code || '';
  var out = [];
  for (var i = 0; i < src.length; i++) {
    var entry = src[i] || {};
    var head = String(entry.headword || '');
    if (head) {
      // On-demand headword check via _by_word hash lookup — O(1), no pre-built set
      var key = lookupKeyFn ? lookupKeyFn(head, langCode) : head.toLowerCase();
      var bucket = builtinEngine._by_word[key];
      if (bucket) {
        // Verify exact headword match (not just key collision)
        var found = false;
        for (var bi = 0; bi < bucket.length; bi++) {
          if (String((bucket[bi] || {}).headword || '') === head) {
            found = true;
            break;
          }
        }
        if (found) continue;
      }
    }
    out.push(entry);
  }
  return out;
}
export function buildAugmentedBrowserEngine(langCode, builtinEngine, customEngine) {
  if (!builtinEngine && !customEngine) return null;
  if (builtinEngine && !customEngine) return builtinEngine;
  if (!builtinEngine && customEngine) return customEngine;
  var code = String(langCode || '').toLowerCase();
  var merged = new window.DictionaryEngine(code);
  function mergeEntriesFromMethod(methodName, word) {
    var primary = [];
    var extra = [];
    if (builtinEngine && typeof builtinEngine[methodName] === 'function') {
      primary = builtinEngine[methodName](word) || [];
    }
    if (customEngine && typeof customEngine[methodName] === 'function') {
      extra = filterAugmentEntriesByEngine(customEngine[methodName](word) || [], builtinEngine);
    }
    if (!extra.length) return Array.isArray(primary) ? primary : [];
    return (Array.isArray(primary) ? primary.slice() : []).concat(extra);
  }
  merged.lookup_all = function (word) {
    return mergeEntriesFromMethod('lookup_all', word);
  };
  merged.lookupAll = function (word) {
    return merged.lookup_all(word);
  };
  merged.lookup_display_only = function (word) {
    return mergeEntriesFromMethod('lookup_display_only', word);
  };
  merged.lookupDisplayOnly = function (word) {
    return merged.lookup_display_only(word);
  };
  merged.lookup_via_forms = function (word) {
    return mergeEntriesFromMethod('lookup_via_forms', word);
  };
  merged.lookupViaForms = function (word) {
    return merged.lookup_via_forms(word);
  };
  return merged;
}
export function resolveLanguageMetaItem(langCode) {
  return loadLanguageMeta().then(function (metaByCode) {
    return metaByCode[String(langCode || '').toLowerCase()] || {};
  });
}

// ── Hybrid compact-index engine loading ──────────────────────────────────
//
// Compact indexes live in two places only:
//   1. in-memory for this tab after they have been built once
//   2. the browser's normal HTTP cache via versioned /js/dict/.../index URLs
//
// There is intentionally no IndexedDB/localStorage preflight here. On a miss
// we request the real index URL immediately and let the browser decide
// whether that resolves from HTTP cache or from the network.
export function getCompactIndexUrl(langCode, source) {
  var code = String(langCode || '').toLowerCase();
  var src = String(source || '').toLowerCase();
  var urls = window.APP_DICT_INDEX_URLS || null;
  var key = code + (src ? ':' + src : '');
  var url = urls && typeof urls === 'object' ? String(urls[key] || '') : '';
  if (!url && (src === 'wiktionary' || src === 'default')) {
    url = urls && typeof urls === 'object' ? String(urls[code] || '') : '';
  }
  return url;
}
export function getGzipUncompressedSize(gzBytes) {
  if (!gzBytes || gzBytes.length < 4) return 0;
  var len = gzBytes.length;
  return (
    (gzBytes[len - 4] | (gzBytes[len - 3] << 8) | (gzBytes[len - 2] << 16) | (gzBytes[len - 1] << 24)) >>> 0
  );
}

// Decompress gzip bytes to JSON string, firing onProgress(bytesOut, totalOut) per chunk.
export function _decompressGzWithProgress(gzBytes, onProgress) {
  var totalOut = getGzipUncompressedSize(gzBytes);
  if (typeof DecompressionStream === 'function') {
    var ds = new DecompressionStream('gzip');
    var blob = new Blob([gzBytes], {
      type: 'application/gzip'
    });
    var textStream = blob.stream().pipeThrough(ds).pipeThrough(new TextDecoderStream());
    var reader = textStream.getReader();
    var parts = [];
    var bytesOut = 0;
    function readChunk() {
      return reader.read().then(function (r) {
        if (r.done) return parts.join('');
        parts.push(r.value);
        bytesOut += r.value.length;
        if (typeof onProgress === 'function') onProgress(bytesOut, totalOut);
        return new Promise(function (res) {
          setTimeout(res, 0);
        }).then(readChunk);
      });
    }
    return readChunk();
  }
  return gunzipToText(gzBytes);
}

/**
 * Fetch the compact key index for a language from its exact immutable URL.
 *
 * Progress callbacks:
 *   onDownloadProgress(received, total)  — while reading response bytes
 *   onDecompressProgress(bytesOut, totalOut) — during decompression
 */
export function fetchCompactIndex(langCode, source, onDownloadProgress, onDecompressProgress) {
  var code = String(langCode || '').toLowerCase();
  var src = String(source || '').toLowerCase();
  var cacheKeyStr = code + (src ? ':' + src : '');
  if (coreState._hybridIndexPromise[cacheKeyStr]) return coreState._hybridIndexPromise[cacheKeyStr];
  var url = getCompactIndexUrl(code, src);
  if (!url) {
    throw new Error('Missing prebuilt index artifact for ' + (cacheKeyStr || code));
  }
  function _loadIndexGz() {
    return fetch(url).then(function (resp) {
      if (!resp.ok) throw new Error('index fetch failed: ' + resp.status);
      var contentLength = parseInt(resp.headers.get('Content-Length') || '0', 10) || 0;
      var received = 0;
      if (typeof onDownloadProgress === 'function') onDownloadProgress(0, contentLength);
      if (!resp.body || typeof resp.body.getReader !== 'function') {
        return resp.arrayBuffer().then(function (buf) {
          var merged = new Uint8Array(buf);
          if (typeof onDownloadProgress === 'function') onDownloadProgress(merged.length, merged.length);
          return merged;
        });
      }
      var reader = resp.body.getReader();
      var chunks = [];
      function readChunk() {
        return reader.read().then(function (result) {
          if (result.done) {
            var totalLen = 0;
            for (var i = 0; i < chunks.length; i++) totalLen += chunks[i].length;
            var merged = new Uint8Array(totalLen);
            var off = 0;
            for (var i = 0; i < chunks.length; i++) {
              merged.set(chunks[i], off);
              off += chunks[i].length;
            }
            return merged;
          }
          chunks.push(result.value);
          received += result.value.length;
          if (typeof onDownloadProgress === 'function') onDownloadProgress(received, contentLength);
          return new Promise(function (res) {
            setTimeout(res, 0);
          }).then(readChunk);
        });
      }
      return readChunk();
    });
  }
  function _parseGz(gzBytes) {
    return _decompressGzWithProgress(gzBytes, onDecompressProgress).then(function (text) {
      return JSON.parse(text);
    });
  }
  var promise = Promise.resolve().then(function () {
    var cachedIndex = coreState._hybridIndexByLang[cacheKeyStr] || null;
    if (cachedIndex) return cachedIndex;
    return _loadIndexGz().then(function (gzBytes) {
      return _parseGz(gzBytes);
    });
  });
  coreState._hybridIndexPromise[cacheKeyStr] = promise.then(
    function (index) {
      delete coreState._hybridIndexPromise[cacheKeyStr];
      coreState._hybridIndexByLang[cacheKeyStr] = index;
      return index;
    },
    function (err) {
      delete coreState._hybridIndexPromise[cacheKeyStr];
      throw err;
    }
  );
  return coreState._hybridIndexPromise[cacheKeyStr];
}

/**
 * Ensure a compact-mode DictionaryEngine is loaded for langCode.
 * Returns Promise<engine>.
 */
export function ensureBuiltinEngine(langCode, opts) {
  opts = opts || {};
  var code = String(langCode || '').toLowerCase();
  var src = String(opts.source || '').toLowerCase();
  var key = cacheKey(code, src || 'hybrid');
  if (coreState.state.readyPromiseByLangSource[key]) return coreState.state.readyPromiseByLangSource[key];
  var showP = !!opts.showProgress;
  function loadFreshEngine() {
    // Progress ranges:
    //   0%->70%  Downloading the prebuilt artifact bytes
    //  70%->94%  Opening the artifact in memory
    //  94%->99%  Injecting custom entries (ticked per entry)
    // 100%       Ready

    if (showP) showDictProgress(0, buildIndexDownloadProgressMessage(0, 0));
    var dlLastPaintAt = 0;
    var downloadProgressCb = showP
      ? function (received, total) {
          var now = Date.now();
          if (now - dlLastPaintAt < 80 && received !== total) return;
          dlLastPaintAt = now;
          var pct =
            total > 0
              ? Math.min(70, Math.round((70 * received) / total))
              : Math.min(70, Math.round((70 * received) / (received + 524288)));
          showDictProgress(pct, buildIndexDownloadProgressMessage(received, total));
        }
      : null;
    var decompLastPaintAt = 0;
    var lastOpenBytesOut = 0;
    var lastOpenTotalOut = 0;
    var decompProgressCb = showP
      ? function (bytesOut, totalOut) {
          var now = Date.now();
          if (now - decompLastPaintAt < 80) return;
          decompLastPaintAt = now;
          lastOpenBytesOut = bytesOut;
          lastOpenTotalOut = totalOut;
          var pct =
            totalOut > 0
              ? Math.min(94, 70 + Math.round((24 * bytesOut) / totalOut))
              : Math.min(94, 70 + Math.round((24 * bytesOut) / (bytesOut + 524288)));
          showDictProgress(pct, buildIndexOpenProgressMessage(bytesOut, totalOut));
        }
      : null;
    var promise = fetchCompactIndex(code, src, downloadProgressCb, decompProgressCb)
      .then(function (index) {
        if (!index) throw new Error('No compact index for ' + code);
        if (!window.DictionaryEngine) throw new Error('DictionaryEngine not loaded');
        if (showP) showDictProgress(94, buildIndexOpenProgressMessage(lastOpenBytesOut, lastOpenTotalOut));
        var engine = new window.DictionaryEngine(code);
        engine.loadCompactIndex(index.hw || {}, index.fw || {}, index.db_aliases || {});
        engine._dcCacheKey = key;
        engine._hybridLang = code;
        engine._dcIndexVersion = String(index.version || '');
        coreState.state.engineByLangSource[key] = engine;
        if (!showP) return engine;
        if (showP) showDictProgress(94, buildGeminiAdditionProgressMessage(0, 0, 0));
        return _injectGeminiAdditions(engine, code, function (processed, total, loaded) {
          if (total <= 0) return;
          var pct = Math.min(99, 94 + Math.round((5 * processed) / total));
          showDictProgress(pct, buildGeminiAdditionProgressMessage(processed, total, loaded));
        }).then(function () {
          return engine;
        });
      })
      .finally(function () {
        if (showP) {
          showDictProgress(100, 'Ready');
          setTimeout(hideDictProgress, 1000);
        }
      });
    coreState.state.readyPromiseByLangSource[key] = promise.then(
      function (engine) {
        delete coreState.state.readyPromiseByLangSource[key];
        return engine;
      },
      function (err) {
        delete coreState.state.readyPromiseByLangSource[key];
        throw err;
      }
    );
    return coreState.state.readyPromiseByLangSource[key];
  }
  var existingEngine = coreState.state.engineByLangSource[key];
  if (existingEngine) {
    // Engine already exists in tab memory.
    return Promise.resolve(existingEngine);
  }
  var cacheKeyStr = code + (src ? ':' + src : '');
  var currentIndex = coreState._hybridIndexByLang[cacheKeyStr];
  if (currentIndex && coreState.state.engineByLangSource[key]) {
    var currentIndexVersion = String(currentIndex.version || '');
    var engineVersion = String(coreState.state.engineByLangSource[key]._dcIndexVersion || '');
    if (!currentIndexVersion || currentIndexVersion === engineVersion) {
      return Promise.resolve(coreState.state.engineByLangSource[key]);
    }
  }
  return loadFreshEngine();
}
export function ensureCustomEngine(langCode, opts) {
  opts = opts || {};
  var code = String(langCode || '').toLowerCase();
  var record = getCustomUploadRecord(code);
  if (!record || !record.gz || !record.gz.length) return Promise.resolve(null);
  var key = cacheKey(code, 'custom');
  if (coreState.state.engineByLangSource[key]) {
    coreState.state.engineByLangSource[key]._dcCacheKey = key;
    return Promise.resolve(coreState.state.engineByLangSource[key]);
  }
  if (coreState.state.readyPromiseByLangSource[key]) return coreState.state.readyPromiseByLangSource[key];
  var summary = {
    rows: 0,
    bytes: 0
  };
  var promise = Promise.resolve()
    .then(function () {
      return buildEngineFromGzipBytes(code, key, record.gz, {
        showProgress: !!opts.showProgress,
        progressBasePct: 20,
        progressSpanPct: 78,
        progressPrefix: 'Building... ',
        preserveSource: true,
        summary: summary
      });
    })
    .then(function (engine) {
      if (engine) {
        record.entry_count = summary.rows > 0 ? summary.rows : countEngineEntries(engine);
      }
      return engine;
    })
    .finally(function () {
      if (opts.showProgress) {
        showDictProgress(100, 'Ready');
        setTimeout(hideDictProgress, 1000);
      }
    });
  coreState.state.readyPromiseByLangSource[key] = promise.then(
    function (engine) {
      delete coreState.state.readyPromiseByLangSource[key];
      return engine;
    },
    function (err) {
      delete coreState.state.readyPromiseByLangSource[key];
      throw err;
    }
  );
  return coreState.state.readyPromiseByLangSource[key];
}
export function ensureAugmentedCustomEngine(langCode, opts) {
  opts = opts || {};
  var code = String(langCode || '').toLowerCase();
  if (!code) return Promise.resolve(null);
  var record = getCustomUploadRecord(code);
  if (!record || !record.gz || !record.gz.length) return Promise.resolve(null);
  return resolveLanguageMetaItem(code).then(function (meta) {
    void meta;
    var key = cacheKey(code, 'custom_augmented');
    if (coreState.state.engineByLangSource[key]) {
      coreState.state.engineByLangSource[key]._dcCacheKey = key;
      return coreState.state.engineByLangSource[key];
    }
    if (coreState.state.readyPromiseByLangSource[key]) return coreState.state.readyPromiseByLangSource[key];
    var promise = Promise.all([
      ensureBuiltinEngine(code, {
        showProgress: false
      }),
      ensureCustomEngine(code, {
        showProgress: !!opts.showProgress
      })
    ]).then(function (parts) {
      var engine = buildAugmentedBrowserEngine(code, parts[0], parts[1]);
      if (engine) {
        engine._dcCacheKey = key;
        coreState.state.engineByLangSource[key] = engine;
      }
      return engine;
    });
    coreState.state.readyPromiseByLangSource[key] = promise.then(
      function (engine) {
        delete coreState.state.readyPromiseByLangSource[key];
        return engine;
      },
      function (err) {
        delete coreState.state.readyPromiseByLangSource[key];
        throw err;
      }
    );
    return coreState.state.readyPromiseByLangSource[key];
  });
}
export function ensureLanguageEngine(langCode, opts) {
  opts = opts || {};
  var source = opts.source || getDictSource();
  var code = String(langCode || '').toLowerCase();
  if (!code) return Promise.resolve(null);
  var loader =
    source === 'custom'
      ? ensureCustomEngine(code, {
          showProgress: !!opts.showProgress
        })
      : ensureBuiltinEngine(code, {
          showProgress: !!opts.showProgress,
          source: source
        });
  return Promise.resolve(loader).then(function (engine) {
    if (requestMatchesCurrentSelection(code, source)) {
      var keepKey = String((engine && engine._dcCacheKey) || findEngineCacheKey(engine) || '');
      evictAllEnginesExcept(keepKey);
    }
    return engine;
  });
}
export function onLanguageDictSync(langCode) {
  var code = String(langCode || '').toLowerCase();
  if (!code) return Promise.resolve(null);
  hideTsvPill();
  var source = getDictSource();
  if (!source) {
    hideDictProgress();
    setStatus('');
    return Promise.resolve(null);
  }
  if (source === 'custom') {
    hideDictProgress();
    var record = getCustomUploadRecord(code);
    if (record && record.gz && record.gz.length) {
      showTsvPill(customUploadLabel(record));
      return ensureLanguageEngine(code, {
        source: 'custom',
        showProgress: true
      });
    }
    evictAllEnginesExcept('');
    evictBuiltinIndexMemoryExcept('');
    setStatus('No custom dictionary loaded.');
    return Promise.resolve(null);
  }
  var targetEngineKey = cacheKey(code, String(source || '').toLowerCase() || 'hybrid');
  var targetIndexKey = code + (source ? ':' + String(source || '').toLowerCase() : '');
  evictAllEnginesExcept(targetEngineKey);
  evictBuiltinIndexMemoryExcept(targetIndexKey);
  return ensureLanguageEngine(code, {
    source: source,
    showProgress: true
  })
    .then(function (engine) {
      evictAllEnginesExcept(targetEngineKey);
      evictBuiltinIndexMemoryExcept(targetIndexKey);
      if (!engine) setStatus('No dictionary available for this language.');
      return engine;
    })
    .catch(function (err) {
      console.error('ensureBuiltinEngine error for ' + code + ':', err);
      hideDictProgress();
      if (
        err &&
        typeof err.message === 'string' &&
        err.message.indexOf('Missing prebuilt index artifact') >= 0
      ) {
        setStatus(err.message);
      } else {
        setStatus('Dictionary load error.');
      }
      return null;
    });
}
export function handleCustomUploadFile(file) {
  var lang = getCurrentLanguage();
  if (!lang) return Promise.resolve();
  showTsvPill(String(file && file.name ? file.name : 'custom.tsv'));
  showDictProgress(10, 'Compressing upload...');
  return gzipBlobToUint8(file)
    .then(function (gzBytes) {
      if (!gzBytes || !gzBytes.length) throw new Error('Could not compress TSV file.');
      setCustomUploadRecord(lang, {
        file_name: String(file && file.name ? file.name : 'custom.tsv'),
        gz: gzBytes,
        uploaded_at: Date.now(),
        source_size: Number((file && file.size) || 0),
        entry_count: 0
      });
      evictCustomEngineCache(lang);
      return ensureLanguageEngine(lang, {
        source: 'custom',
        showProgress: true
      }).then(function () {
        var record = getCustomUploadRecord(lang);
        if (record) showTsvPill(customUploadLabel(record));
        setStatus('Custom TSV active.');
      });
    })
    .catch(function (err) {
      clearCustomUploadRecord(lang);
      evictCustomEngineCache(lang);
      hideTsvPill();
      hideDictProgress();
      console.error('TSV load error:', err);
      setStatus('Error loading TSV dictionary.');
      throw err;
    });
}
export function resetCustomForCurrentLanguage() {
  var lang = getCurrentLanguage();
  hideTsvPill();
  if (!lang) return Promise.resolve();
  clearCustomUploadRecord(lang);
  evictCustomEngineCache(lang);
  if (getDictSource() === 'custom') {
    evictAllEnginesExcept('');
  }
  setStatus('Custom dictionary cleared.');
  return Promise.resolve();
}
export function prefetchAllBuiltinDicts() {
  // Disabled — dictionaries are now downloaded on-demand when user selects a source.
  return Promise.resolve();
}
export function bindUi() {
  coreState.ui.statusText = document.getElementById('statusText');
  coreState.ui.languageSelect = document.getElementById('languageSelect');
  coreState.ui.dictSourceSelect = document.getElementById('dictSourceSelect');
  coreState.ui.tsvUploadLabel = document.getElementById('tsvUploadLabel');
  coreState.ui.tsvFileInput = document.getElementById('tsvFileInput');
  coreState.ui.tsvPill = document.getElementById('tsvPill');
  coreState.ui.tsvFileName = document.getElementById('tsvFileName');
  coreState.ui.clearTsvBtn = document.getElementById('clearTsvBtn');
  coreState.ui.dictProgressWrap = document.getElementById('dictProgressWrap');
  coreState.ui.dictProgressBar = document.getElementById('dictProgressBar');
  coreState.ui.dictProgressText = document.getElementById('dictProgressText');
  updateDictSourceUI();
  if (coreState.ui.tsvFileInput) {
    coreState.ui.tsvFileInput.addEventListener('change', function () {
      var file = coreState.ui.tsvFileInput.files && coreState.ui.tsvFileInput.files[0];
      if (!file) return;
      handleCustomUploadFile(file).catch(function () {});
      coreState.ui.tsvFileInput.value = '';
    });
  }
  if (coreState.ui.clearTsvBtn) {
    coreState.ui.clearTsvBtn.addEventListener('click', function () {
      resetCustomForCurrentLanguage().catch(function () {});
    });
  }
  if (coreState.ui.dictSourceSelect) {
    coreState.ui.dictSourceSelect.addEventListener('change', function () {
      updateDictSourceUI();
      if (getDictSource()) setStatus('');
      onLanguageDictSync(getCurrentLanguage()).catch(function () {});
    });
  }
  if (coreState.ui.languageSelect) {
    coreState.ui.languageSelect.addEventListener('change', function () {
      populateDictSourceDropdown(getCurrentLanguage(), true).then(function () {
        // Only sync if a source is already selected (e.g. cached from previous session)
        var source = getDictSource();
        if (source) onLanguageDictSync(getCurrentLanguage()).catch(function () {});
      });
    });
  }
}
export function lookupLangFromUrl(parsedUrl) {
  if (!parsedUrl) return getCurrentLanguage();
  var raw = String(parsedUrl.searchParams.get('lang') || '')
    .trim()
    .toLowerCase();
  return raw || getCurrentLanguage();
}
export function decorateLookupJson(lookupJson, langCode, source, options) {
  // Try worker path
  var wkey = _getActiveWorkerKey(langCode);
  if (wkey) {
    return _queryWorker(wkey, {
      type: 'merged_lookup',
      lookupData: lookupJson,
      langCode: langCode,
      opts: options || {}
    });
  }
  // Main-thread fallback
  return ensureLanguageEngine(langCode, {
    source: source || getDictSource(),
    showProgress: false
  }).then(function (engine) {
    return hybridSegmentAndHydrate(lookupJson, engine, langCode, options || {});
  });
}
export function perfNowMs() {
  if (typeof performance !== 'undefined' && performance && typeof performance.now === 'function') {
    return performance.now();
  }
  return Date.now();
}
export function roundTimingMs(value) {
  var n = Number(value || 0);
  if (!isFinite(n)) return 0;
  return Math.round(n * 1000) / 1000;
}
export function parseDebugServerMs(resp) {
  if (!resp || !resp.headers || typeof resp.headers.get !== 'function') return 0;
  var raw = resp.headers.get('X-Debug-Server-Ms');
  var n = Number(raw || 0);
  return isFinite(n) && n > 0 ? n : 0;
}
export function attachNetworkBreakdown(networkNode, totalMs, serverMs) {
  if (!networkNode || typeof networkNode !== 'object') return;
  var total = roundTimingMs(totalMs);
  var server = roundTimingMs(Math.max(0, Math.min(total, Number(serverMs || 0))));
  networkNode.duration_ms = total;
  if (server > 0) {
    addTimingChild(networkNode, {
      name: 'server_processing',
      label: 'Server Processing',
      meta: {},
      duration_ms: server,
      children: []
    });
  }
  var residual = roundTimingMs(total - server);
  if (residual > 0.25) {
    addTimingChild(networkNode, {
      name: 'transport_and_wait',
      label: 'Transport + Wait',
      meta: {},
      duration_ms: residual,
      children: []
    });
  }
}
export function createTimingNode(name, label, meta) {
  return {
    name: String(name || '').trim(),
    label: String(label || name || '').trim(),
    meta: meta && typeof meta === 'object' ? Object.assign({}, meta) : {},
    duration_ms: 0,
    children: []
  };
}
export function addTimingChild(parent, child) {
  if (!parent || typeof parent !== 'object' || !child || typeof child !== 'object') return child;
  if (!Array.isArray(parent.children)) parent.children = [];
  parent.children.push(child);
  return child;
}
export function finalizeTimingNode(node) {
  if (!node || typeof node !== 'object') return null;
  var children = Array.isArray(node.children) ? node.children : [];
  var childSum = 0;
  var finalizedChildren = [];
  for (var i = 0; i < children.length; i++) {
    var finalizedChild = finalizeTimingNode(children[i]);
    if (!finalizedChild) continue;
    finalizedChildren.push(finalizedChild);
    childSum += Number(finalizedChild.duration_ms || 0);
  }
  node.children = finalizedChildren;
  node.duration_ms = roundTimingMs(node.duration_ms);
  node.logged_child_ms = roundTimingMs(childSum);
  var unattributed = roundTimingMs(node.duration_ms - childSum);
  if (finalizedChildren.length > 0 && unattributed > 0.25) {
    node.children.push({
      name: 'unattributed',
      label: 'Unattributed',
      meta: {
        logged_child_ms: roundTimingMs(childSum)
      },
      duration_ms: unattributed,
      children: []
    });
  }
  return node;
}
export function buildLookupTimingTrace(root, captureId, langCode, queryText) {
  if (!root || typeof root !== 'object') return null;
  var finalizedRoot = finalizeTimingNode(root);
  if (!finalizedRoot) return null;
  var loggedMs = roundTimingMs(finalizedRoot.logged_child_ms || 0);
  var totalMs = roundTimingMs(finalizedRoot.duration_ms || 0);
  return {
    debug_capture_id: String(captureId || '').trim(),
    current_language: String(langCode || '')
      .trim()
      .toLowerCase(),
    q: String(queryText || ''),
    total_ms: totalMs,
    logged_ms: loggedMs,
    unattributed_ms: roundTimingMs(totalMs - loggedMs),
    timing_tree: finalizedRoot,
    updated_at: Date.now()
  };
}
