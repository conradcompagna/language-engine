import { coreState } from './core.state.mjs';
import { buildDownloadProgressMessage, formatProgressMegabytes } from './index-cache.mjs';
import { lookupLangFromUrl } from './worker-transport.mjs';
export // API base for hybrid endpoints (/js/dict, /js/hydrate)
function getApiBase() {
  return '/js';
}

// Per-language compact index cache (in-memory, keyed by lang code)
export // Convert numeric pinyin only inside [...] brackets in gloss text,
// e.g. "see 拜拜[bai2 bai2]" → "see 拜拜[bài bài]"
function convertNumericPinyinInGloss(str) {
  if (!str || typeof str !== 'string') return str;
  return str.replace(/\[([^\]]+)\]/g, function (_, inside) {
    return '[' + convertNumericPinyin(inside) + ']';
  });
}
export function convertNumericPinyin(str) {
  if (!str || typeof str !== 'string') return str;
  // Process one syllable at a time (space-separated tokens).
  // A token like "gong1" has the tone digit after the last vowel in the
  // standard placement order: a/e first, then the last of i/o/u/ü/v.
  return str.replace(/([a-züvA-ZÜV]+)([1-5])/g, function (_, syllable, toneStr) {
    var tone = parseInt(toneStr, 10);
    if (tone === 5) return syllable; // neutral tone — strip the digit, no mark
    // Priority: a or e takes the mark; otherwise the last vowel in iouüv.
    var target = '';
    var targetIdx = -1;
    for (var i = 0; i < syllable.length; i++) {
      var ch = syllable[i];
      var lo = ch.toLowerCase();
      if (lo === 'a' || lo === 'e') {
        target = ch;
        targetIdx = i;
        break;
      }
      if (lo === 'o') {
        // o always beats i/u/v/ü — but keep scanning in case a comes later
        target = ch;
        targetIdx = i;
      } else if (lo === 'i' || lo === 'u' || lo === 'ü' || lo === 'v') {
        // only take this if we haven't already found o
        if (target.toLowerCase() !== 'o') {
          target = ch;
          targetIdx = i;
        }
      }
    }
    if (!target || !coreState._PINYIN_TONE_MAP[target + tone]) return syllable;
    return (
      syllable.slice(0, targetIdx) + coreState._PINYIN_TONE_MAP[target + tone] + syllable.slice(targetIdx + 1)
    );
  });
}
// ---------------------------------------------------------------------------
export function isTruthyFlag(v) {
  var t = String(v || '')
    .trim()
    .toLowerCase();
  return t === '1' || t === 'true' || t === 'yes' || t === 'raw' || t === 'exact';
}
export function toAbsoluteUrl(input) {
  try {
    return new URL(String(input || ''), window.location.origin);
  } catch (_e) {
    return null;
  }
}
export function jsonResponse(payload, statusCode) {
  return new Response(JSON.stringify(payload), {
    status: typeof statusCode === 'number' ? statusCode : 200,
    headers: {
      'Content-Type': 'application/json'
    }
  });
}
export function getCurrentLanguage() {
  if (coreState.ui.languageSelect) {
    return String(coreState.ui.languageSelect.value || '').toLowerCase();
  }
  return String(window.ReaderDefaultLanguage || '').toLowerCase();
}
export function getDictionaryNormalizationLayer() {
  return window.DictionaryNormalizationLayer || null;
}
export function isSanskritLookupLanguage(langCode) {
  var layer = getDictionaryNormalizationLayer();
  return !!(
    layer &&
    typeof layer.isSanskritLanguageCode === 'function' &&
    layer.isSanskritLanguageCode(langCode)
  );
}
export function buildSanskritLookupRewrite(parsedUrl) {
  if (!parsedUrl) return null;
  if (!isSanskritLookupLanguage(lookupLangFromUrl(parsedUrl))) return null;
  return null;
}
export function getDictSource() {
  if (!coreState.ui.dictSourceSelect) return '';
  return String(coreState.ui.dictSourceSelect.value || '');
}
export function cacheKey(langCode, source) {
  return String(langCode || '').toLowerCase() + '|' + String(source || '');
}
export function findEngineCacheKey(engine) {
  if (!engine) return '';
  var keys = Object.keys(coreState.state.engineByLangSource || {});
  for (var i = 0; i < keys.length; i++) {
    var k = keys[i];
    if (coreState.state.engineByLangSource[k] === engine) return k;
  }
  return '';
}
export function evictAllEnginesExcept(keepKey) {
  var keep = String(keepKey || '');
  var engineKeys = Object.keys(coreState.state.engineByLangSource || {});
  for (var i = 0; i < engineKeys.length; i++) {
    var key = engineKeys[i];
    if (keep && key === keep) continue;
    delete coreState.state.engineByLangSource[key];
  }
  var readyKeys = Object.keys(coreState.state.readyPromiseByLangSource || {});
  for (var j = 0; j < readyKeys.length; j++) {
    var rkey = readyKeys[j];
    if (keep && rkey === keep) continue;
    delete coreState.state.readyPromiseByLangSource[rkey];
  }
  // Terminate evicted workers
  var workerKeys = Object.keys(coreState.state.activeWorkers || {});
  for (var w = 0; w < workerKeys.length; w++) {
    var wkey = workerKeys[w];
    if (keep && wkey === keep) continue;
    var winfo = coreState.state.activeWorkers[wkey];
    if (winfo && winfo.worker) {
      try {
        winfo.worker.terminate();
      } catch (_e) {}
      if (winfo.blobUrl)
        try {
          URL.revokeObjectURL(winfo.blobUrl);
        } catch (_e2) {}
    }
    delete coreState.state.activeWorkers[wkey];
  }
}
export function evictBuiltinIndexMemoryExcept(keepCacheKeyStr) {
  var keep = String(keepCacheKeyStr || '');
  var indexKeys = Object.keys(coreState._hybridIndexByLang || {});
  for (var i = 0; i < indexKeys.length; i++) {
    var key = indexKeys[i];
    if (keep && key === keep) continue;
    delete coreState._hybridIndexByLang[key];
  }
  var promiseKeys = Object.keys(coreState._hybridIndexPromise || {});
  for (var j = 0; j < promiseKeys.length; j++) {
    var pkey = promiseKeys[j];
    if (keep && pkey === keep) continue;
    delete coreState._hybridIndexPromise[pkey];
  }
}
export function requestMatchesCurrentSelection(langCode, source) {
  var reqLang = String(langCode || '').toLowerCase();
  var reqSource = String(source || 'wiktionary');
  var currentLang = getCurrentLanguage();
  var currentSource = getDictSource();
  return reqLang === currentLang && reqSource === currentSource;
}
export function showDictProgress(pct, text) {
  if (coreState.ui.dictProgressWrap) coreState.ui.dictProgressWrap.style.display = 'flex';
  if (coreState.ui.dictProgressBar)
    coreState.ui.dictProgressBar.style.width = Math.min(100, Math.max(0, Number(pct) || 0)) + '%';
  if (coreState.ui.dictProgressText) coreState.ui.dictProgressText.textContent = text || '';
}
export function reportLookupProgress(text) {
  try {
    if (window.__LE_LOOKUP_ACTIVE && typeof window.__LE_lookupProgress === 'function') {
      window.__LE_lookupProgress(String(text || ''));
    } else if (typeof document !== 'undefined') {
      document.dispatchEvent(
        new CustomEvent('le:lookup-progress', {
          detail: {
            message: String(text || '')
          }
        })
      );
    }
  } catch (_e) {}
}
export function hideDictProgress() {
  if (coreState.ui.dictProgressWrap) coreState.ui.dictProgressWrap.style.display = 'none';
  if (coreState.ui.dictProgressBar) coreState.ui.dictProgressBar.style.width = '0%';
  if (coreState.ui.dictProgressText) coreState.ui.dictProgressText.textContent = '';
}
export function showTsvPill(name) {
  if (coreState.ui.tsvPill) coreState.ui.tsvPill.style.display = '';
  if (coreState.ui.tsvFileName) coreState.ui.tsvFileName.textContent = String(name || '');
}
export function hideTsvPill() {
  if (coreState.ui.tsvPill) coreState.ui.tsvPill.style.display = 'none';
  if (coreState.ui.tsvFileName) coreState.ui.tsvFileName.textContent = '';
}
export function setStatus(text) {
  if (coreState.ui.statusText) coreState.ui.statusText.textContent = String(text || '');
}
export function updateDictSourceUI() {
  var src = getDictSource();
  if (coreState.ui.tsvUploadLabel) coreState.ui.tsvUploadLabel.style.display = src === 'custom' ? '' : 'none';
}
export function populateDictSourceDropdown(langCode, resetSelection) {
  if (!coreState.ui.dictSourceSelect) return Promise.resolve();
  var code = String(langCode || '').toLowerCase();
  if (!code) {
    // No language selected — reset dict dropdown to disabled placeholder
    var sel = coreState.ui.dictSourceSelect;
    sel.innerHTML = '';
    var ph = document.createElement('option');
    ph.value = '';
    ph.textContent = '\u2014 select dictionary \u2014';
    ph.disabled = true;
    ph.selected = true;
    sel.appendChild(ph);
    sel.disabled = true;
    updateDictSourceUI();
    return Promise.resolve();
  }
  return loadLanguageMeta()
    .then(function (metaByCode) {
      var meta = metaByCode[code] || {};
      var ds = meta.dict_sources || null;
      var defaultSource = String(meta.default_dict_source || '');
      var sel = coreState.ui.dictSourceSelect;
      sel.disabled = false;
      var prevValue = resetSelection ? '' : sel.value;
      sel.innerHTML = '';

      // Placeholder shown on language change — forces user to pick a dictionary
      var placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = '\u2014 select dictionary \u2014';
      placeholder.disabled = true;
      sel.appendChild(placeholder);
      if (ds) {
        var keys = Object.keys(ds);
        for (var i = 0; i < keys.length; i++) {
          var opt = document.createElement('option');
          opt.value = keys[i];
          opt.textContent = ds[keys[i]].label || keys[i];
          sel.appendChild(opt);
        }
      } else {
        var defOpt = document.createElement('option');
        defOpt.value = 'wiktionary';
        defOpt.textContent = 'Wiktionary';
        sel.appendChild(defOpt);
      }

      // On language change (resetSelection): show placeholder, wait for user choice
      if (resetSelection) {
        sel.value = '';
        updateDictSourceUI();
        return;
      }
      // Restore previous selection if it still exists
      var found = false;
      for (var j = 0; j < sel.options.length; j++) {
        if (sel.options[j].value === prevValue && prevValue !== '') {
          found = true;
          break;
        }
      }
      if (found) {
        sel.value = prevValue;
      } else if (defaultSource) {
        var hasDefault = false;
        for (var k = 0; k < sel.options.length; k++) {
          if (sel.options[k].value === defaultSource) {
            hasDefault = true;
            break;
          }
        }
        sel.value = hasDefault ? defaultSource : '';
      } else {
        sel.value = '';
      }
      updateDictSourceUI();
    })
    .catch(function () {});
}
export function getCustomUploadRecord(langCode) {
  return coreState.state.customUploadByLang[String(langCode || '').toLowerCase()] || null;
}
export function setCustomUploadRecord(langCode, record) {
  var code = String(langCode || '').toLowerCase();
  if (!code) return;
  coreState.state.customUploadByLang[code] = record || null;
}
export function clearCustomUploadRecord(langCode) {
  var code = String(langCode || '').toLowerCase();
  if (!code) return;
  delete coreState.state.customUploadByLang[code];
}
export function customUploadLabel(record) {
  var rec = record || {};
  var label = String(rec.file_name || 'custom.tsv');
  var count = Number(rec.entry_count || 0);
  if (count > 0) label += ' (' + count + ')';
  return label;
}
export function evictEngineKeysWithPrefix(prefix) {
  var rawPrefix = String(prefix || '');
  if (!rawPrefix) return;
  var engineKeys = Object.keys(coreState.state.engineByLangSource || {});
  for (var i = 0; i < engineKeys.length; i++) {
    if (engineKeys[i].indexOf(rawPrefix) === 0) delete coreState.state.engineByLangSource[engineKeys[i]];
  }
  var readyKeys = Object.keys(coreState.state.readyPromiseByLangSource || {});
  for (var j = 0; j < readyKeys.length; j++) {
    if (readyKeys[j].indexOf(rawPrefix) === 0) delete coreState.state.readyPromiseByLangSource[readyKeys[j]];
  }
}
export function evictCustomEngineCache(langCode) {
  var code = String(langCode || '').toLowerCase();
  if (!code) return;
  evictEngineKeysWithPrefix(code + '|custom|');
}
export function openBuiltinDictDb() {
  return new Promise(function (resolve, reject) {
    var req = indexedDB.open(coreState.BUILTIN_DB_NAME, coreState.BUILTIN_DB_VERSION);
    req.onupgradeneeded = function (e) {
      var db = e.target.result;
      if (db.objectStoreNames.contains(coreState.BUILTIN_STORE_NAME)) {
        db.deleteObjectStore(coreState.BUILTIN_STORE_NAME);
      }
      if (!db.objectStoreNames.contains(coreState.BUILTIN_STORE_NAME)) {
        db.createObjectStore(coreState.BUILTIN_STORE_NAME, {
          keyPath: 'lang_code'
        });
      }
    };
    req.onsuccess = function (e) {
      resolve(e.target.result);
    };
    req.onerror = function (e) {
      reject(e.target.error);
    };
  });
}
export function builtinDbKey(langCode, source) {
  var key = String(langCode || '').toLowerCase();
  var src = String(source || '').toLowerCase();
  return src && src !== 'wiktionary' ? key + '|' + src : key;
}
export function saveBuiltinDict(langCode, gzBytes, version, source) {
  return openBuiltinDictDb().then(function (db) {
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(coreState.BUILTIN_STORE_NAME, 'readwrite');
      var store = tx.objectStore(coreState.BUILTIN_STORE_NAME);
      store.put({
        lang_code: builtinDbKey(langCode, source),
        gz: gzBytes,
        version: String(version || ''),
        timestamp: Date.now()
      });
      tx.oncomplete = function () {
        resolve();
      };
      tx.onerror = function (e) {
        reject(e.target.error);
      };
    });
  });
}
export function loadBuiltinDict(langCode, source) {
  return openBuiltinDictDb().then(function (db) {
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(coreState.BUILTIN_STORE_NAME, 'readonly');
      var store = tx.objectStore(coreState.BUILTIN_STORE_NAME);
      var req = store.get(builtinDbKey(langCode, source));
      req.onsuccess = function () {
        resolve(req.result || null);
      };
      req.onerror = function (e) {
        reject(e.target.error);
      };
    });
  });
}
export function parseTsvText(text) {
  var lines = String(text || '').split(/\r?\n/);
  if (!lines.length) return [];
  var headers = lines[0].split('\t');
  var rows = [];
  for (var i = 1; i < lines.length; i++) {
    var line = lines[i];
    if (!line || !line.trim()) continue;
    var fields = line.split('\t');
    var row = {
      __line_no: i + 1
    };
    for (var j = 0; j < headers.length; j++) {
      row[String(headers[j] || '').trim()] = j < fields.length ? fields[j] : '';
    }
    rows.push(row);
  }
  return rows;
}
export function gzipBytesToUint8(rawBytes) {
  if (typeof CompressionStream !== 'function') {
    return Promise.resolve(null);
  }
  var bytes = rawBytes instanceof Uint8Array ? rawBytes : new Uint8Array(rawBytes || 0);
  var cs = new CompressionStream('gzip');
  var writer = cs.writable.getWriter();
  return writer
    .write(bytes)
    .then(function () {
      return writer.close();
    })
    .then(function () {
      return new Response(cs.readable).arrayBuffer();
    })
    .then(function (buf) {
      return new Uint8Array(buf);
    })
    .catch(function (_err) {
      return null;
    });
}
export function gzipBlobToUint8(blob) {
  var src = blob || null;
  if (src && typeof src.stream === 'function' && typeof CompressionStream === 'function') {
    var cs = new CompressionStream('gzip');
    var stream = src.stream().pipeThrough(cs);
    return new Response(stream)
      .arrayBuffer()
      .then(function (buf) {
        return new Uint8Array(buf);
      })
      .catch(function (_err) {
        return null;
      });
  }
  if (!src || typeof src.arrayBuffer !== 'function') {
    return Promise.resolve(null);
  }
  return src
    .arrayBuffer()
    .then(function (buf) {
      return gzipBytesToUint8(new Uint8Array(buf));
    })
    .catch(function (_err) {
      return null;
    });
}
export function gunzipToText(gzBytes) {
  if (!gzBytes || !gzBytes.length) return Promise.resolve('');
  if (typeof DecompressionStream !== 'function') {
    return Promise.reject(new Error('DecompressionStream not available'));
  }
  var ds = new DecompressionStream('gzip');
  var blob = new Blob([gzBytes], {
    type: 'application/gzip'
  });
  var stream = blob.stream().pipeThrough(ds);
  return new Response(stream).text();
}
export function loadLanguageMeta(forceRefresh) {
  var now = Date.now();
  var isFresh =
    coreState.state.languageMetaPromise &&
    now - coreState.state.languageMetaLoadedAt < coreState.state.LANG_META_TTL_MS;
  if (!forceRefresh && isFresh) return coreState.state.languageMetaPromise;
  coreState.state.languageMetaPromise = fetch('/api/languages', {
    cache: 'no-store'
  })
    .then(function (r) {
      return r.json();
    })
    .then(function (data) {
      var out = {};
      var langs = data && data.languages && data.languages.length ? data.languages : [];
      for (var i = 0; i < langs.length; i++) {
        var item = langs[i] || {};
        var code = String(item.code || '').toLowerCase();
        if (!code) continue;
        out[code] = item;
      }
      coreState.state.languageMetaLoadedAt = Date.now();
      return out;
    })
    .catch(function (err) {
      coreState.state.languageMetaPromise = null;
      coreState.state.languageMetaLoadedAt = 0;
      throw err;
    });
  return coreState.state.languageMetaPromise;
}
export function _downloadGzipDict(langCode, onProgress, source) {
  var url = '/api/dict/' + encodeURIComponent(String(langCode || ''));
  var src = String(source || '').toLowerCase();
  if (src) url += '?source=' + encodeURIComponent(src);
  return fetch(url, {
    cache: 'no-store'
  }).then(function (r) {
    if (!r.ok) return null;
    var contentLength = parseInt(r.headers.get('Content-Length') || '0', 10);
    if (r.body && typeof r.body.getReader === 'function') {
      var reader = r.body.getReader();
      var chunks = [];
      var received = 0;
      if (typeof onProgress === 'function') {
        onProgress(0, contentLength);
      }
      function readChunk() {
        return reader.read().then(function (result) {
          if (result.done) {
            var totalLen = 0;
            for (var c = 0; c < chunks.length; c++) totalLen += chunks[c].length;
            var merged = new Uint8Array(totalLen);
            var off = 0;
            for (var c2 = 0; c2 < chunks.length; c2++) {
              merged.set(chunks[c2], off);
              off += chunks[c2].length;
            }
            return {
              gzBytes: merged
            };
          }
          chunks.push(result.value);
          received += result.value.length;
          if (typeof onProgress === 'function') {
            onProgress(received, contentLength);
          }
          // Yield to browser paint cycle so progress bar actually renders
          return new Promise(function (resolve) {
            setTimeout(resolve, 0);
          }).then(readChunk);
        });
      }
      return readChunk();
    }
    return r.arrayBuffer().then(function (buf) {
      var gzBytes = new Uint8Array(buf);
      if (typeof onProgress === 'function') {
        onProgress(gzBytes.length, gzBytes.length);
      }
      return {
        gzBytes: gzBytes
      };
    });
  });
}
export function fetchBuiltinDictGz(langCode, opts) {
  opts = opts || {};
  var showProgress = !!opts.showProgress;
  var source = String(opts.source || '');
  var inFlightKey = String(langCode || '').toLowerCase() + '|' + source;
  if (coreState.state.builtinFetchInFlight[inFlightKey]) {
    return coreState.state.builtinFetchInFlight[inFlightKey];
  }
  var promise = loadBuiltinDict(langCode, source).then(function (record) {
    if (record && record.gz && record.gz.length) {
      if (showProgress)
        showDictProgress(30, 'Loaded from cache \u2014 ' + formatProgressMegabytes(record.gz.length) + ' MB');
      return record.gz;
    }
    if (showProgress) showDictProgress(5, 'Downloading\u2026');
    var dlLastPaintAt = 0;
    return _downloadGzipDict(
      langCode,
      function (received, total) {
        if (!showProgress) return;
        var now = performance.now();
        if (now - dlLastPaintAt < 80) return; // throttle: max ~12 updates/sec so browser can paint
        dlLastPaintAt = now;
        var pct;
        if (total > 0) {
          pct = Math.min(30, 5 + Math.round((25 * received) / total));
        } else {
          pct = Math.min(28, 5 + Math.round((23 * received) / (received + 1048576)));
        }
        showDictProgress(pct, buildDownloadProgressMessage(received, total));
      },
      source
    ).then(function (payload) {
      var gzBytes = payload && payload.gzBytes;
      if (!gzBytes || !gzBytes.length) return null;
      if (showProgress)
        showDictProgress(32, 'Caching\u2026 ' + formatProgressMegabytes(gzBytes.length) + ' MB');
      return saveBuiltinDict(langCode, gzBytes, '', source).then(function () {
        return gzBytes;
      });
    });
  });
  coreState.state.builtinFetchInFlight[inFlightKey] = promise.then(
    function (result) {
      delete coreState.state.builtinFetchInFlight[inFlightKey];
      return result;
    },
    function (err) {
      delete coreState.state.builtinFetchInFlight[inFlightKey];
      throw err;
    }
  );
  return coreState.state.builtinFetchInFlight[inFlightKey];
}
export function normalizeLookupKey(engine, text) {
  var raw = String(text || '').trim();
  if (!raw) return '';
  var layer = window.DictionaryNormalizationLayer;
  return String(
    layer.normalizeLookupKeyText(raw, {
      langCode: String((engine && engine._lang_code) || getCurrentLanguage() || '')
        .trim()
        .toLowerCase(),
      phase: 'dictionary_client_fallback'
    }) || ''
  ).trim();
}
export function normalizeVisibleComparisonText(text) {
  var layer = window.DictionaryNormalizationLayer;
  return String(layer.normalizeVisibleComparisonText(String(text || '')) || '');
}
export function splitCompoundLemma(lemma) {
  var text = String(lemma || '').trim();
  if (!text || (text.indexOf('+') < 0 && text.indexOf('\uFF0B') < 0)) return [];
  var parts = text
    .split(coreState.COMPOUND_LEMMA_SPLIT_RE)
    .map(function (p) {
      return p.trim();
    })
    .filter(Boolean);
  return parts.length > 1 ? parts : [];
}
export function isPersianLanguageCode(langValue) {
  var lang = String(langValue || '')
    .trim()
    .toLowerCase();
  return lang === 'fa' || lang === 'persian' || lang.indexOf('fa-') === 0;
}
export function isSwahiliLanguageCode(langValue) {
  var lang = String(langValue || '')
    .trim()
    .toLowerCase();
  return lang === 'sw' || lang === 'swahili' || lang === 'kiswahili' || lang.indexOf('sw-') === 0;
}
export function stripSwahiliBracketMarkup(text, langValue) {
  var raw = String(text == null ? '' : text);
  if (!raw) return '';
  if (!isSwahiliLanguageCode(langValue || getCurrentLanguage())) return raw;
  var cleaned = raw.replace(/\[\[[\s\S]*?\]\]/g, ' ');
  cleaned = cleaned.replace(/(?:\s*\/\s*){2,}/g, ' / ');
  cleaned = cleaned.replace(/^\s*(?:\/+\s*)+/, '');
  cleaned = cleaned.replace(/\s*(?:\/+\s*)+$/, '');
  cleaned = cleaned.replace(/\s+([,;:.!?])/g, '$1');
  cleaned = cleaned.replace(/\s{2,}/g, ' ').trim();
  return cleaned;
}
export function splitPersianLemmaVariants(text) {
  var raw = String(text || '').trim();
  if (!raw || raw.indexOf('#') < 0) return [];
  var out = [];
  var seen = Object.create(null);
  var parts = raw
    .split('#')
    .map(function (part) {
      return String(part || '').trim();
    })
    .filter(Boolean);
  for (var i = 0; i < parts.length; i++) {
    var part = parts[i];
    if (seen[part]) continue;
    seen[part] = true;
    out.push(part);
  }
  return out.length > 1 ? out : [];
}
export function getLemmaHintCandidateTexts(rawHint, engine) {
  var lang = String((engine && engine._lang_code) || getCurrentLanguage() || '')
    .trim()
    .toLowerCase();
  var out = [];
  var seen = Object.create(null);
  function pushText(raw) {
    var txt = String(raw || '').trim();
    if (!txt || seen[txt]) return;
    seen[txt] = true;
    out.push(txt);
  }
  if (rawHint && typeof rawHint === 'object' && !Array.isArray(rawHint)) {
    var rawVariants = Array.isArray(rawHint.variants) ? rawHint.variants : [];
    for (var i = 0; i < rawVariants.length; i++) pushText(rawVariants[i]);
    if (!out.length && isPersianLanguageCode(lang)) {
      var splitVariants = splitPersianLemmaVariants(rawHint.text || rawHint.lemma || '');
      for (var j = 0; j < splitVariants.length; j++) pushText(splitVariants[j]);
    }
    if (!out.length) pushText(rawHint.text || rawHint.lemma || '');
    return out;
  }
  pushText(rawHint || '');
  return out;
}
export function initializeCore() {
  if (window.DictionaryClient) return false;
  coreState.UPOS_COLORS = {
    ADJ: '#fde68a',
    ADP: '#e0f2fe',
    ADV: '#fee2e2',
    AUX: '#e0e7ff',
    CCONJ: '#cffafe',
    DET: '#f1f5f9',
    INTJ: '#fcd34d',
    NOUN: '#bbf7d0',
    NUM: '#f5d0fe',
    PART: '#f4f4f5',
    PRON: '#e2e8f0',
    PROPN: '#c7d2fe',
    PUNCT: '#e5e7eb',
    SCONJ: '#bae6fd',
    SYM: '#f3e8ff',
    VERB: '#fda4af',
    X: '#d1d5db'
  };
  coreState.POS_ABBREV = {
    noun: 'n',
    verb: 'v',
    adj: 'adj',
    adv: 'adv',
    pron: 'pron',
    prep: 'prep',
    postp: 'postp',
    conj: 'conj',
    det: 'det',
    num: 'num',
    intj: 'intj',
    particle: 'ptcl',
    classifier: 'clf',
    prefix: 'pfx',
    suffix: 'sfx',
    affix: 'afx',
    infix: 'ifx',
    interfix: 'itfx',
    circumfix: 'circfx',
    combining_form: 'comb',
    contraction: 'contr',
    phrase: 'phr',
    proverb: 'prov',
    prep_phrase: 'pr.phr',
    character: 'char',
    name: 'name',
    romanization: 'rom',
    root: 'root',
    article: 'art',
    punct: 'punct',
    symbol: 'sym',
    counter: 'ctr',
    adnominal: 'adn',
    circumpos: 'cpos',
    syllable: 'syl',
    '[]': 'unk'
  };
  coreState.COMPOUND_LEMMA_SPLIT_RE = /\s*[+\uFF0B]\s*/;
  coreState.ENABLE_PARTIAL_EXACT_LEMMA_GAP_FILL = true;
  coreState.META_NF_RE = /^nf(\d+)$/;
  coreState.META_PRI_TAG_PERCENT = {
    ichi1: 80.0,
    news1: 70.0,
    ichi2: 50.0,
    gai1: 50.0,
    news2: 40.0,
    gai2: 25.0
  };
  coreState.state = {
    initialized: false,
    readyPromiseByLangSource: Object.create(null),
    engineByLangSource: Object.create(null),
    customUploadByLang: Object.create(null),
    languageMetaPromise: null,
    languageMetaLoadedAt: 0,
    LANG_META_TTL_MS: 15000,
    builtinFetchInFlight: Object.create(null),
    allBuiltinPrefetchStarted: false,
    activeWorkers: Object.create(null),
    workerCallbacks: Object.create(null),
    nextRequestId: 1
  };
  coreState.ui = {
    statusText: null,
    languageSelect: null,
    dictSourceSelect: null,
    tsvUploadLabel: null,
    tsvFileInput: null,
    tsvPill: null,
    tsvFileName: null,
    clearTsvBtn: null,
    dictProgressWrap: null,
    dictProgressBar: null,
    dictProgressText: null
  };
  coreState.BUILTIN_DB_NAME = 'NeuralReaderBuiltinDict';
  coreState.BUILTIN_DB_VERSION = 4;
  coreState.BUILTIN_STORE_NAME = 'dicts';
  coreState._hybridIndexByLang = Object.create(null); // {lang: {hw, fw, db_aliases, version}}
  coreState._hybridIndexPromise = Object.create(null); // in-flight fetch promises

  // ---------------------------------------------------------------------------
  // Pinyin numeric-tone → diacritic converter
  // CEDICT stores romanization as "gong1 yuan2"; convert to "gōng yuán".
  // ---------------------------------------------------------------------------
  coreState._PINYIN_TONE_MAP = (function () {
    // For each vowel group: [base, tone1, tone2, tone3, tone4]
    var rows = [
      ['a', 'ā', 'á', 'ǎ', 'à'],
      ['e', 'ē', 'é', 'ě', 'è'],
      ['i', 'ī', 'í', 'ǐ', 'ì'],
      ['o', 'ō', 'ó', 'ǒ', 'ò'],
      ['u', 'ū', 'ú', 'ǔ', 'ù'],
      ['ü', 'ǖ', 'ǘ', 'ǚ', 'ǜ'],
      ['v', 'ǖ', 'ǘ', 'ǚ', 'ǜ'],
      // CEDICT uses v for ü
      ['A', 'Ā', 'Á', 'Ǎ', 'À'],
      ['E', 'Ē', 'É', 'Ě', 'È'],
      ['I', 'Ī', 'Í', 'Ǐ', 'Ì'],
      ['O', 'Ō', 'Ó', 'Ǒ', 'Ò'],
      ['U', 'Ū', 'Ú', 'Ǔ', 'Ù']
    ];
    var map = {};
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      for (var t = 1; t <= 4; t++) map[r[0] + t] = r[t];
    }
    return map;
  })();
  return true;
}
