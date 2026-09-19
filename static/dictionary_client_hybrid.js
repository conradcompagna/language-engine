/**
 * dictionary_client_hybrid.js
 *
 * Hybrid JS/SQLite dictionary runtime:
 * - Loads a compact key index (~1MB gzip) from /js/dict/<lang>/index
 *   instead of full entry TSVs. Keys only — no entry data in browser.
 * - Intercepts /js/lookup: runs DP segmentation against the compact index,
 *   collects winner refs, calls /js/hydrate for full entry data.
 * - Intercepts /lookup_dp_only: same compact-index DP + hydrate flow,
 *   no server NLP call (lemma/upos/xpos passed as URL params).
 * - Gemini CRUD still uses /api/gemini_entry/* for persistence;
 *   injectGeminiKey() / removeCompactKey() update the in-memory index.
 * - reader.js consumes the same results_by_seg + entry_store shape
 *   as the original /lookup endpoint — zero changes needed downstream.
 */
(function() {
  "use strict";

  if (window.DictionaryClient) return;

  var UPOS_COLORS = {
    "ADJ": "#fde68a",
    "ADP": "#e0f2fe",
    "ADV": "#fee2e2",
    "AUX": "#e0e7ff",
    "CCONJ": "#cffafe",
    "DET": "#f1f5f9",
    "INTJ": "#fcd34d",
    "NOUN": "#bbf7d0",
    "NUM": "#f5d0fe",
    "PART": "#f4f4f5",
    "PRON": "#e2e8f0",
    "PROPN": "#c7d2fe",
    "PUNCT": "#e5e7eb",
    "SCONJ": "#bae6fd",
    "SYM": "#f3e8ff",
    "VERB": "#fda4af",
    "X": "#d1d5db"
  };

  var POS_ABBREV = {
    "noun": "n", "verb": "v", "adj": "adj", "adv": "adv",
    "pron": "pron", "prep": "prep", "postp": "postp", "conj": "conj",
    "det": "det", "num": "num", "intj": "intj", "particle": "ptcl",
    "classifier": "clf", "prefix": "pfx", "suffix": "sfx", "affix": "afx",
    "infix": "ifx", "interfix": "itfx", "circumfix": "circfx",
    "combining_form": "comb", "contraction": "contr", "phrase": "phr",
    "proverb": "prov", "prep_phrase": "pr.phr", "character": "char",
    "name": "name", "romanization": "rom", "root": "root",
    "article": "art", "punct": "punct", "symbol": "sym",
    "counter": "ctr", "adnominal": "adn", "circumpos": "cpos",
    "syllable": "syl", "[]": "unk"
  };

  var COMPOUND_LEMMA_SPLIT_RE = /\s*[+\uFF0B]\s*/;
  var ENABLE_PARTIAL_EXACT_LEMMA_GAP_FILL = true;
  var META_NF_RE = /^nf(\d+)$/;
  var META_PRI_TAG_PERCENT = {
    ichi1: 80.0,
    news1: 70.0,
    ichi2: 50.0,
    gai1: 50.0,
    news2: 40.0,
    gai2: 25.0
  };

  var state = {
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

  var ui = {
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

  var BUILTIN_DB_NAME = "NeuralReaderBuiltinDict";
  var BUILTIN_DB_VERSION = 4;
  var BUILTIN_STORE_NAME = "dicts";

  // API base for hybrid endpoints (/js/dict, /js/hydrate)
  function getApiBase() { return "/js"; }

  // Per-language compact index cache (in-memory, keyed by lang code)
  var _hybridIndexByLang = Object.create(null);  // {lang: {hw, fw, db_aliases, version}}
  var _hybridIndexPromise = Object.create(null); // in-flight fetch promises

  // ---------------------------------------------------------------------------
  // Pinyin numeric-tone → diacritic converter
  // CEDICT stores romanization as "gong1 yuan2"; convert to "gōng yuán".
  // ---------------------------------------------------------------------------
  var _PINYIN_TONE_MAP = (function() {
    // For each vowel group: [base, tone1, tone2, tone3, tone4]
    var rows = [
      ["a",  "ā","á","ǎ","à"],
      ["e",  "ē","é","ě","è"],
      ["i",  "ī","í","ǐ","ì"],
      ["o",  "ō","ó","ǒ","ò"],
      ["u",  "ū","ú","ǔ","ù"],
      ["ü",  "ǖ","ǘ","ǚ","ǜ"],
      ["v",  "ǖ","ǘ","ǚ","ǜ"],  // CEDICT uses v for ü
      ["A",  "Ā","Á","Ǎ","À"],
      ["E",  "Ē","É","Ě","È"],
      ["I",  "Ī","Í","Ǐ","Ì"],
      ["O",  "Ō","Ó","Ǒ","Ò"],
      ["U",  "Ū","Ú","Ǔ","Ù"],
    ];
    var map = {};
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      for (var t = 1; t <= 4; t++) map[r[0] + t] = r[t];
    }
    return map;
  }());

  // Convert numeric pinyin only inside [...] brackets in gloss text,
  // e.g. "see 拜拜[bai2 bai2]" → "see 拜拜[bài bài]"
  function convertNumericPinyinInGloss(str) {
    if (!str || typeof str !== "string") return str;
    return str.replace(/\[([^\]]+)\]/g, function(_, inside) {
      return "[" + convertNumericPinyin(inside) + "]";
    });
  }

  function convertNumericPinyin(str) {
    if (!str || typeof str !== "string") return str;
    // Process one syllable at a time (space-separated tokens).
    // A token like "gong1" has the tone digit after the last vowel in the
    // standard placement order: a/e first, then the last of i/o/u/ü/v.
    return str.replace(/([a-züvA-ZÜV]+)([1-5])/g, function(_, syllable, toneStr) {
      var tone = parseInt(toneStr, 10);
      if (tone === 5) return syllable; // neutral tone — strip the digit, no mark
      // Priority: a or e takes the mark; otherwise the last vowel in iouüv.
      var target = "";
      var targetIdx = -1;
      for (var i = 0; i < syllable.length; i++) {
        var ch = syllable[i];
        var lo = ch.toLowerCase();
        if (lo === "a" || lo === "e") { target = ch; targetIdx = i; break; }
        if (lo === "o") {
          // o always beats i/u/v/ü — but keep scanning in case a comes later
          target = ch; targetIdx = i;
        } else if (lo === "i" || lo === "u" || lo === "ü" || lo === "v") {
          // only take this if we haven't already found o
          if (target.toLowerCase() !== "o") { target = ch; targetIdx = i; }
        }
      }
      if (!target || !_PINYIN_TONE_MAP[target + tone]) return syllable;
      return syllable.slice(0, targetIdx) + _PINYIN_TONE_MAP[target + tone] + syllable.slice(targetIdx + 1);
    });
  }
  // ---------------------------------------------------------------------------

  function isTruthyFlag(v) {
    var t = String(v || "").trim().toLowerCase();
    return t === "1" || t === "true" || t === "yes" || t === "raw" || t === "exact";
  }

  function toAbsoluteUrl(input) {
    try {
      return new URL(String(input || ""), window.location.origin);
    } catch (_e) {
      return null;
    }
  }

  function jsonResponse(payload, statusCode) {
    return new Response(JSON.stringify(payload), {
      status: typeof statusCode === "number" ? statusCode : 200,
      headers: {
        "Content-Type": "application/json"
      }
    });
  }

  function getCurrentLanguage() {
    if (ui.languageSelect) {
      return String(ui.languageSelect.value || "").toLowerCase();
    }
    return String(window.ReaderDefaultLanguage || "").toLowerCase();
  }

  function getDictionaryNormalizationLayer() {
    return window.DictionaryNormalizationLayer || null;
  }

  function isSanskritLookupLanguage(langCode) {
    var layer = getDictionaryNormalizationLayer();
    return !!(
      layer &&
      typeof layer.isSanskritLanguageCode === "function" &&
      layer.isSanskritLanguageCode(langCode)
    );
  }

  function buildSanskritLookupRewrite(parsedUrl) {
    if (!parsedUrl) return null;
    if (!isSanskritLookupLanguage(lookupLangFromUrl(parsedUrl))) return null;
    return null;
  }

  function getDictSource() {
    if (!ui.dictSourceSelect) return "";
    return String(ui.dictSourceSelect.value || "");
  }

  function cacheKey(langCode, source) {
    return String(langCode || "").toLowerCase() + "|" + String(source || "");
  }

  function findEngineCacheKey(engine) {
    if (!engine) return "";
    var keys = Object.keys(state.engineByLangSource || {});
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (state.engineByLangSource[k] === engine) return k;
    }
    return "";
  }

  function evictAllEnginesExcept(keepKey) {
    var keep = String(keepKey || "");
    var engineKeys = Object.keys(state.engineByLangSource || {});
    for (var i = 0; i < engineKeys.length; i++) {
      var key = engineKeys[i];
      if (keep && key === keep) continue;
      delete state.engineByLangSource[key];
    }
    var readyKeys = Object.keys(state.readyPromiseByLangSource || {});
    for (var j = 0; j < readyKeys.length; j++) {
      var rkey = readyKeys[j];
      if (keep && rkey === keep) continue;
      delete state.readyPromiseByLangSource[rkey];
    }
    // Terminate evicted workers
    var workerKeys = Object.keys(state.activeWorkers || {});
    for (var w = 0; w < workerKeys.length; w++) {
      var wkey = workerKeys[w];
      if (keep && wkey === keep) continue;
      var winfo = state.activeWorkers[wkey];
      if (winfo && winfo.worker) {
        try { winfo.worker.terminate(); } catch (_e) {}
        if (winfo.blobUrl) try { URL.revokeObjectURL(winfo.blobUrl); } catch (_e2) {}
      }
      delete state.activeWorkers[wkey];
    }
  }

  function evictBuiltinIndexMemoryExcept(keepCacheKeyStr) {
    var keep = String(keepCacheKeyStr || "");
    var indexKeys = Object.keys(_hybridIndexByLang || {});
    for (var i = 0; i < indexKeys.length; i++) {
      var key = indexKeys[i];
      if (keep && key === keep) continue;
      delete _hybridIndexByLang[key];
    }
    var promiseKeys = Object.keys(_hybridIndexPromise || {});
    for (var j = 0; j < promiseKeys.length; j++) {
      var pkey = promiseKeys[j];
      if (keep && pkey === keep) continue;
      delete _hybridIndexPromise[pkey];
    }
  }

  function requestMatchesCurrentSelection(langCode, source) {
    var reqLang = String(langCode || "").toLowerCase();
    var reqSource = String(source || "wiktionary");
    var currentLang = getCurrentLanguage();
    var currentSource = getDictSource();
    return reqLang === currentLang && reqSource === currentSource;
  }

  function showDictProgress(pct, text) {
    if (ui.dictProgressWrap) ui.dictProgressWrap.style.display = "flex";
    if (ui.dictProgressBar) ui.dictProgressBar.style.width = Math.min(100, Math.max(0, Number(pct) || 0)) + "%";
    if (ui.dictProgressText) ui.dictProgressText.textContent = text || "";
  }

  function reportLookupProgress(text) {
    try {
      if (window.__LE_LOOKUP_ACTIVE && typeof window.__LE_lookupProgress === "function") {
        window.__LE_lookupProgress(String(text || ""));
      } else if (typeof document !== "undefined") {
        document.dispatchEvent(new CustomEvent("le:lookup-progress", {
          detail: { message: String(text || "") }
        }));
      }
    } catch (_e) {}
  }

  function hideDictProgress() {
    if (ui.dictProgressWrap) ui.dictProgressWrap.style.display = "none";
    if (ui.dictProgressBar) ui.dictProgressBar.style.width = "0%";
    if (ui.dictProgressText) ui.dictProgressText.textContent = "";
  }

  function showTsvPill(name) {
    if (ui.tsvPill) ui.tsvPill.style.display = "";
    if (ui.tsvFileName) ui.tsvFileName.textContent = String(name || "");
  }

  function hideTsvPill() {
    if (ui.tsvPill) ui.tsvPill.style.display = "none";
    if (ui.tsvFileName) ui.tsvFileName.textContent = "";
  }

  function setStatus(text) {
    if (ui.statusText) ui.statusText.textContent = String(text || "");
  }

  function updateDictSourceUI() {
    var src = getDictSource();
    if (ui.tsvUploadLabel) ui.tsvUploadLabel.style.display = (src === "custom") ? "" : "none";
  }

  function populateDictSourceDropdown(langCode, resetSelection) {
    if (!ui.dictSourceSelect) return Promise.resolve();
    var code = String(langCode || "").toLowerCase();
    if (!code) {
      // No language selected — reset dict dropdown to disabled placeholder
      var sel = ui.dictSourceSelect;
      sel.innerHTML = "";
      var ph = document.createElement("option");
      ph.value = ""; ph.textContent = "\u2014 select dictionary \u2014"; ph.disabled = true; ph.selected = true;
      sel.appendChild(ph);
      sel.disabled = true;
      updateDictSourceUI();
      return Promise.resolve();
    }
    return loadLanguageMeta().then(function(metaByCode) {
      var meta = metaByCode[code] || {};
      var ds = meta.dict_sources || null;
      var defaultSource = String(meta.default_dict_source || "");
      var sel = ui.dictSourceSelect;
      sel.disabled = false;
      var prevValue = resetSelection ? "" : sel.value;
      sel.innerHTML = "";

      // Placeholder shown on language change — forces user to pick a dictionary
      var placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "\u2014 select dictionary \u2014";
      placeholder.disabled = true;
      sel.appendChild(placeholder);

      if (ds) {
        var keys = Object.keys(ds);
        for (var i = 0; i < keys.length; i++) {
          var opt = document.createElement("option");
          opt.value = keys[i];
          opt.textContent = ds[keys[i]].label || keys[i];
          sel.appendChild(opt);
        }
      } else {
        var defOpt = document.createElement("option");
        defOpt.value = "wiktionary";
        defOpt.textContent = "Wiktionary";
        sel.appendChild(defOpt);
      }

      // On language change (resetSelection): show placeholder, wait for user choice
      if (resetSelection) {
        sel.value = "";
        updateDictSourceUI();
        return;
      }
      // Restore previous selection if it still exists
      var found = false;
      for (var j = 0; j < sel.options.length; j++) {
        if (sel.options[j].value === prevValue && prevValue !== "") { found = true; break; }
      }
      if (found) {
        sel.value = prevValue;
      } else if (defaultSource) {
        var hasDefault = false;
        for (var k = 0; k < sel.options.length; k++) {
          if (sel.options[k].value === defaultSource) { hasDefault = true; break; }
        }
        sel.value = hasDefault ? defaultSource : "";
      } else {
        sel.value = "";
      }
      updateDictSourceUI();
    }).catch(function() {});
  }

  function getCustomUploadRecord(langCode) {
    return state.customUploadByLang[String(langCode || "").toLowerCase()] || null;
  }

  function setCustomUploadRecord(langCode, record) {
    var code = String(langCode || "").toLowerCase();
    if (!code) return;
    state.customUploadByLang[code] = record || null;
  }

  function clearCustomUploadRecord(langCode) {
    var code = String(langCode || "").toLowerCase();
    if (!code) return;
    delete state.customUploadByLang[code];
  }

  function customUploadLabel(record) {
    var rec = record || {};
    var label = String(rec.file_name || "custom.tsv");
    var count = Number(rec.entry_count || 0);
    if (count > 0) label += " (" + count + ")";
    return label;
  }

  function evictEngineKeysWithPrefix(prefix) {
    var rawPrefix = String(prefix || "");
    if (!rawPrefix) return;
    var engineKeys = Object.keys(state.engineByLangSource || {});
    for (var i = 0; i < engineKeys.length; i++) {
      if (engineKeys[i].indexOf(rawPrefix) === 0) delete state.engineByLangSource[engineKeys[i]];
    }
    var readyKeys = Object.keys(state.readyPromiseByLangSource || {});
    for (var j = 0; j < readyKeys.length; j++) {
      if (readyKeys[j].indexOf(rawPrefix) === 0) delete state.readyPromiseByLangSource[readyKeys[j]];
    }
  }

  function evictCustomEngineCache(langCode) {
    var code = String(langCode || "").toLowerCase();
    if (!code) return;
    evictEngineKeysWithPrefix(code + "|custom|");
  }

  function openBuiltinDictDb() {
    return new Promise(function(resolve, reject) {
      var req = indexedDB.open(BUILTIN_DB_NAME, BUILTIN_DB_VERSION);
      req.onupgradeneeded = function(e) {
        var db = e.target.result;
        if (db.objectStoreNames.contains(BUILTIN_STORE_NAME)) {
          db.deleteObjectStore(BUILTIN_STORE_NAME);
        }
        if (!db.objectStoreNames.contains(BUILTIN_STORE_NAME)) {
          db.createObjectStore(BUILTIN_STORE_NAME, { keyPath: "lang_code" });
        }
      };
      req.onsuccess = function(e) { resolve(e.target.result); };
      req.onerror = function(e) { reject(e.target.error); };
    });
  }

  function builtinDbKey(langCode, source) {
    var key = String(langCode || "").toLowerCase();
    var src = String(source || "").toLowerCase();
    return src && src !== "wiktionary" ? key + "|" + src : key;
  }

  function saveBuiltinDict(langCode, gzBytes, version, source) {
    return openBuiltinDictDb().then(function(db) {
      return new Promise(function(resolve, reject) {
        var tx = db.transaction(BUILTIN_STORE_NAME, "readwrite");
        var store = tx.objectStore(BUILTIN_STORE_NAME);
        store.put({
          lang_code: builtinDbKey(langCode, source),
          gz: gzBytes,
          version: String(version || ""),
          timestamp: Date.now()
        });
        tx.oncomplete = function() { resolve(); };
        tx.onerror = function(e) { reject(e.target.error); };
      });
    });
  }

  function loadBuiltinDict(langCode, source) {
    return openBuiltinDictDb().then(function(db) {
      return new Promise(function(resolve, reject) {
        var tx = db.transaction(BUILTIN_STORE_NAME, "readonly");
        var store = tx.objectStore(BUILTIN_STORE_NAME);
        var req = store.get(builtinDbKey(langCode, source));
        req.onsuccess = function() { resolve(req.result || null); };
        req.onerror = function(e) { reject(e.target.error); };
      });
    });
  }

  function parseTsvText(text) {
    var lines = String(text || "").split(/\r?\n/);
    if (!lines.length) return [];
    var headers = lines[0].split("\t");
    var rows = [];
    for (var i = 1; i < lines.length; i++) {
      var line = lines[i];
      if (!line || !line.trim()) continue;
      var fields = line.split("\t");
      var row = { __line_no: i + 1 };
      for (var j = 0; j < headers.length; j++) {
        row[String(headers[j] || "").trim()] = (j < fields.length) ? fields[j] : "";
      }
      rows.push(row);
    }
    return rows;
  }

  function gzipBytesToUint8(rawBytes) {
    if (typeof CompressionStream !== "function") {
      return Promise.resolve(null);
    }
    var bytes = rawBytes instanceof Uint8Array ? rawBytes : new Uint8Array(rawBytes || 0);
    var cs = new CompressionStream("gzip");
    var writer = cs.writable.getWriter();
    return writer.write(bytes).then(function() {
      return writer.close();
    }).then(function() {
      return new Response(cs.readable).arrayBuffer();
    }).then(function(buf) {
      return new Uint8Array(buf);
    }).catch(function(_err) {
      return null;
    });
  }

  function gzipBlobToUint8(blob) {
    var src = blob || null;
    if (src && typeof src.stream === "function" && typeof CompressionStream === "function") {
      var cs = new CompressionStream("gzip");
      var stream = src.stream().pipeThrough(cs);
      return new Response(stream).arrayBuffer().then(function(buf) {
        return new Uint8Array(buf);
      }).catch(function(_err) {
        return null;
      });
    }
    if (!src || typeof src.arrayBuffer !== "function") {
      return Promise.resolve(null);
    }
    return src.arrayBuffer().then(function(buf) {
      return gzipBytesToUint8(new Uint8Array(buf));
    }).catch(function(_err) {
      return null;
    });
  }

  function gunzipToText(gzBytes) {
    if (!gzBytes || !gzBytes.length) return Promise.resolve("");
    if (typeof DecompressionStream !== "function") {
      return Promise.reject(new Error("DecompressionStream not available"));
    }
    var ds = new DecompressionStream("gzip");
    var blob = new Blob([gzBytes], { type: "application/gzip" });
    var stream = blob.stream().pipeThrough(ds);
    return new Response(stream).text();
  }

  function loadLanguageMeta(forceRefresh) {
    var now = Date.now();
    var isFresh = state.languageMetaPromise && ((now - state.languageMetaLoadedAt) < state.LANG_META_TTL_MS);
    if (!forceRefresh && isFresh) return state.languageMetaPromise;
    state.languageMetaPromise = fetch("/api/languages", { cache: "no-store" }).then(function(r) {
      return r.json();
    }).then(function(data) {
      var out = {};
      var langs = (data && data.languages && data.languages.length) ? data.languages : [];
      for (var i = 0; i < langs.length; i++) {
        var item = langs[i] || {};
        var code = String(item.code || "").toLowerCase();
        if (!code) continue;
        out[code] = item;
      }
      state.languageMetaLoadedAt = Date.now();
      return out;
    }).catch(function(err) {
      state.languageMetaPromise = null;
      state.languageMetaLoadedAt = 0;
      throw err;
    });
    return state.languageMetaPromise;
  }

  function _downloadGzipDict(langCode, onProgress, source) {
    var url = "/api/dict/" + encodeURIComponent(String(langCode || ""));
    var src = String(source || "").toLowerCase();
    if (src) url += "?source=" + encodeURIComponent(src);
    return fetch(url, { cache: "no-store" }).then(function(r) {
      if (!r.ok) return null;
      var contentLength = parseInt(r.headers.get("Content-Length") || "0", 10);
      if (r.body && typeof r.body.getReader === "function") {
        var reader = r.body.getReader();
        var chunks = [];
        var received = 0;
        if (typeof onProgress === "function") {
          onProgress(0, contentLength);
        }
        function readChunk() {
          return reader.read().then(function(result) {
            if (result.done) {
              var totalLen = 0;
              for (var c = 0; c < chunks.length; c++) totalLen += chunks[c].length;
              var merged = new Uint8Array(totalLen);
              var off = 0;
              for (var c2 = 0; c2 < chunks.length; c2++) {
                merged.set(chunks[c2], off);
                off += chunks[c2].length;
              }
              return { gzBytes: merged };
            }
            chunks.push(result.value);
            received += result.value.length;
            if (typeof onProgress === "function") {
              onProgress(received, contentLength);
            }
            // Yield to browser paint cycle so progress bar actually renders
            return new Promise(function(resolve) { setTimeout(resolve, 0); }).then(readChunk);
          });
        }
        return readChunk();
      }
      return r.arrayBuffer().then(function(buf) {
        var gzBytes = new Uint8Array(buf);
        if (typeof onProgress === "function") {
          onProgress(gzBytes.length, gzBytes.length);
        }
        return { gzBytes: gzBytes };
      });
    });
  }

  function fetchBuiltinDictGz(langCode, opts) {
    opts = opts || {};
    var showProgress = !!opts.showProgress;
    var source = String(opts.source || "");
    var inFlightKey = String(langCode || "").toLowerCase() + "|" + source;
    if (state.builtinFetchInFlight[inFlightKey]) {
      return state.builtinFetchInFlight[inFlightKey];
    }
    var promise = loadBuiltinDict(langCode, source).then(function(record) {
      if (record && record.gz && record.gz.length) {
        if (showProgress) showDictProgress(30, "Loaded from cache \u2014 " + formatProgressMegabytes(record.gz.length) + " MB");
        return record.gz;
      }
      if (showProgress) showDictProgress(5, "Downloading\u2026");
      var dlLastPaintAt = 0;
      return _downloadGzipDict(langCode, function(received, total) {
        if (!showProgress) return;
        var now = performance.now();
        if (now - dlLastPaintAt < 80) return; // throttle: max ~12 updates/sec so browser can paint
        dlLastPaintAt = now;
        var pct;
        if (total > 0) {
          pct = Math.min(30, 5 + Math.round((25 * received) / total));
        } else {
          pct = Math.min(28, 5 + Math.round(23 * received / (received + 1048576)));
        }
        showDictProgress(pct, buildDownloadProgressMessage(received, total));
      }, source).then(function(payload) {
        var gzBytes = payload && payload.gzBytes;
        if (!gzBytes || !gzBytes.length) return null;
        if (showProgress) showDictProgress(32, "Caching\u2026 " + formatProgressMegabytes(gzBytes.length) + " MB");
        return saveBuiltinDict(langCode, gzBytes, "", source).then(function() {
          return gzBytes;
        });
      });
    });
    state.builtinFetchInFlight[inFlightKey] = promise.then(function(result) {
      delete state.builtinFetchInFlight[inFlightKey];
      return result;
    }, function(err) {
      delete state.builtinFetchInFlight[inFlightKey];
      throw err;
    });
    return state.builtinFetchInFlight[inFlightKey];
  }

  function normalizeLookupKey(engine, text) {
    var raw = String(text || "").trim();
    if (!raw) return "";
    var layer = window.DictionaryNormalizationLayer;
    return String(layer.normalizeLookupKeyText(raw, {
      langCode: String((engine && engine._lang_code) || getCurrentLanguage() || "").trim().toLowerCase(),
      phase: "dictionary_client_fallback"
    }) || "").trim();
  }

  function normalizeVisibleComparisonText(text) {
    var layer = window.DictionaryNormalizationLayer;
    return String(layer.normalizeVisibleComparisonText(String(text || "")) || "");
  }

  function splitCompoundLemma(lemma) {
    var text = String(lemma || "").trim();
    if (!text || (text.indexOf("+") < 0 && text.indexOf("\uFF0B") < 0)) return [];
    var parts = text.split(COMPOUND_LEMMA_SPLIT_RE).map(function(p) { return p.trim(); }).filter(Boolean);
    return parts.length > 1 ? parts : [];
  }

  function isPersianLanguageCode(langValue) {
    var lang = String(langValue || "").trim().toLowerCase();
    return lang === "fa" || lang === "persian" || lang.indexOf("fa-") === 0;
  }

  function isSwahiliLanguageCode(langValue) {
    var lang = String(langValue || "").trim().toLowerCase();
    return lang === "sw" || lang === "swahili" || lang === "kiswahili" || lang.indexOf("sw-") === 0;
  }

  function stripSwahiliBracketMarkup(text, langValue) {
    var raw = String(text == null ? "" : text);
    if (!raw) return "";
    if (!isSwahiliLanguageCode(langValue || getCurrentLanguage())) return raw;
    var cleaned = raw.replace(/\[\[[\s\S]*?\]\]/g, " ");
    cleaned = cleaned.replace(/(?:\s*\/\s*){2,}/g, " / ");
    cleaned = cleaned.replace(/^\s*(?:\/+\s*)+/, "");
    cleaned = cleaned.replace(/\s*(?:\/+\s*)+$/, "");
    cleaned = cleaned.replace(/\s+([,;:.!?])/g, "$1");
    cleaned = cleaned.replace(/\s{2,}/g, " ").trim();
    return cleaned;
  }

  function splitPersianLemmaVariants(text) {
    var raw = String(text || "").trim();
    if (!raw || raw.indexOf("#") < 0) return [];
    var out = [];
    var seen = Object.create(null);
    var parts = raw.split("#").map(function(part) { return String(part || "").trim(); }).filter(Boolean);
    for (var i = 0; i < parts.length; i++) {
      var part = parts[i];
      if (seen[part]) continue;
      seen[part] = true;
      out.push(part);
    }
    return out.length > 1 ? out : [];
  }

  function getLemmaHintCandidateTexts(rawHint, engine) {
    var lang = String((engine && engine._lang_code) || getCurrentLanguage() || "").trim().toLowerCase();
    var out = [];
    var seen = Object.create(null);
    function pushText(raw) {
      var txt = String(raw || "").trim();
      if (!txt || seen[txt]) return;
      seen[txt] = true;
      out.push(txt);
    }
    if (rawHint && typeof rawHint === "object" && !Array.isArray(rawHint)) {
      var rawVariants = Array.isArray(rawHint.variants) ? rawHint.variants : [];
      for (var i = 0; i < rawVariants.length; i++) pushText(rawVariants[i]);
      if (!out.length && isPersianLanguageCode(lang)) {
        var splitVariants = splitPersianLemmaVariants(rawHint.text || rawHint.lemma || "");
        for (var j = 0; j < splitVariants.length; j++) pushText(splitVariants[j]);
      }
      if (!out.length) pushText(rawHint.text || rawHint.lemma || "");
      return out;
    }
    pushText(rawHint || "");
    return out;
  }

  function cloneLemmaHintObject(rawHint) {
    if (rawHint && typeof rawHint === "object" && !Array.isArray(rawHint)) {
      var out = {};
      for (var key in rawHint) {
        if (!Object.prototype.hasOwnProperty.call(rawHint, key)) continue;
        if (key === "variants" && Array.isArray(rawHint[key])) out[key] = rawHint[key].slice();
        else out[key] = rawHint[key];
      }
      return out;
    }
    var text = String(rawHint || "").trim();
    return text ? { text: text } : {};
  }

  function chooseEntry(surface, entries, engine) {
    if (!entries || !entries.length) return null;
    if (!surface) return entries[0];
    var targetText = String(surface || "").trim();
    var targetKey = normalizeLookupKey(engine, targetText);
    var normalizedMatch = null;
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i];
      if (!entry) continue;
      var headword = getEntryDisplayHeadword(entry);
      var surfaceForm = String(entry.surface_form || "").trim();
      if (headword === targetText || (surfaceForm && surfaceForm === targetText)) return entry;
      if (!normalizedMatch && targetKey) {
        if (headword && normalizeLookupKey(engine, headword) === targetKey) normalizedMatch = entry;
        else if (surfaceForm && normalizeLookupKey(engine, surfaceForm) === targetKey) normalizedMatch = entry;
      }
    }
    return normalizedMatch || entries[0];
  }

  function mergeWordLists() {
    var seen = Object.create(null);
    var out = [];
    for (var ai = 0; ai < arguments.length; ai++) {
      var list = arguments[ai] || [];
      for (var i = 0; i < list.length; i++) {
        var word = String(list[i] || "");
        if (!word || seen[word]) continue;
        seen[word] = true;
        out.push(word);
      }
    }
    return out;
  }

  function dedupeTextList(values) {
    var out = [];
    var seen = Object.create(null);
    var list = Array.isArray(values) ? values : [];
    for (var i = 0; i < list.length; i++) {
      var text = String(list[i] || "").trim();
      if (!text || seen[text]) continue;
      seen[text] = true;
      out.push(text);
    }
    return out;
  }

  function cleanMorphDisplayTags(text) {
    var raw = String(text == null ? "" : text).trim();
    if (!raw) return "";
    var parts = raw.split(";").map(function(part) {
      return String(part || "").trim();
    }).filter(Boolean);
    if (!parts.length) return "";
    var out = [];
    var seen = Object.create(null);
    for (var i = 0; i < parts.length; i++) {
      var part = parts[i];
      if (String(part || "").trim().toLowerCase() === "error-unrecognized-form") continue;
      if (seen[part]) continue;
      seen[part] = true;
      out.push(part);
    }
    return out.join(";");
  }

  function buildStructuredSensesFromRaw(raw, langCode) {
    var source = raw;
    if (typeof source === "string") {
      var text = String(source || "").trim();
      if (!text) return [];
      try {
        source = JSON.parse(text);
      } catch (_e) {
        text = stripSwahiliBracketMarkup(text, langCode);
        if (!text) return [];
        return text.split(";").map(function(part) { return String(part || "").trim(); }).filter(Boolean).map(function(gloss) {
          return { glosses: [gloss] };
        });
      }
    }
    if (source && typeof source === "object" && !Array.isArray(source)) source = [source];
    if (!Array.isArray(source)) return [];

    var out = [];
    for (var i = 0; i < source.length; i++) {
      var item = source[i];
      if (item && typeof item === "object") {
        var glosses = Array.isArray(item.glosses)
          ? item.glosses.map(function(gloss) {
              return stripSwahiliBracketMarkup(gloss, langCode);
            }).map(function(gloss) { return String(gloss || "").trim(); }).filter(Boolean)
          : [];
        if (!glosses.length) {
          var fallback = stripSwahiliBracketMarkup(item.gloss || item.text || "", langCode);
          fallback = String(fallback || "").trim();
          if (fallback) glosses = [fallback];
        }
        if (!glosses.length) continue;
        var sense = Object.assign({}, item);
        if (sense.qualifier != null) {
          var cleanedQualifier = stripSwahiliBracketMarkup(sense.qualifier, langCode);
          if (cleanedQualifier) sense.qualifier = cleanedQualifier;
          else delete sense.qualifier;
        }
        sense.glosses = glosses;
        out.push(sense);
        continue;
      }
      var textValue = String(stripSwahiliBracketMarkup(item || "", langCode) || "").trim();
      if (textValue) out.push({ glosses: [textValue] });
    }
    return out;
  }

  function flattenCanonicalSenses(rawSenses, langCode) {
    var list = Array.isArray(rawSenses) ? rawSenses : [];
    var flat = [];
    for (var i = 0; i < list.length; i++) {
      var sense = list[i];
      if (sense && typeof sense === "object") {
        var glosses = Array.isArray(sense.glosses) ? sense.glosses : [];
        var cleaned = glosses.map(function(gloss) {
          return stripSwahiliBracketMarkup(gloss, langCode);
        }).map(function(gloss) { return String(gloss || "").trim(); }).filter(Boolean);
        if (cleaned.length) flat.push(cleaned.join("; "));
        continue;
      }
      var text = String(stripSwahiliBracketMarkup(sense || "", langCode) || "").trim();
      if (text) flat.push(text);
    }
    return dedupeTextList(flat);
  }

  function normalizeCanonicalFormRows(raw, langCode) {
    var rows = Array.isArray(raw) ? raw : [];
    var out = [];
    var seen = Object.create(null);
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var word = "";
      var commentary = "";
      var romanization = "";
      if (Array.isArray(row)) {
        word = String(row[0] || "").trim();
        commentary = String(stripSwahiliBracketMarkup(row[1] || "", langCode) || "").trim();
        romanization = String(row[2] || "").trim();
      } else if (row && typeof row === "object") {
        word = String(row.word || row.form || row.headword || row.form_text || row.display_text || "").trim();
        commentary = String(stripSwahiliBracketMarkup(row.commentary || row.tags || "", langCode) || "").trim();
        romanization = String(row.romanization || row.reading || row.form_roman || "").trim();
      } else {
        word = String(row || "").trim();
      }
      if (!word) continue;
      var key = word + "\t" + commentary + "\t" + romanization;
      if (seen[key]) continue;
      seen[key] = true;
      out.push([word, commentary, romanization]);
    }
    return out;
  }

  function mergeUniqueTextList(baseValues, extraValues) {
    var out = [];
    var seen = Object.create(null);

    function pushOne(raw) {
      var text = String(raw || "").trim();
      if (!text || seen[text]) return;
      seen[text] = true;
      out.push(text);
    }

    var baseList = Array.isArray(baseValues) ? baseValues : (baseValues ? [baseValues] : []);
    for (var i = 0; i < baseList.length; i++) pushOne(baseList[i]);
    var extraList = Array.isArray(extraValues) ? extraValues : (extraValues ? [extraValues] : []);
    for (var j = 0; j < extraList.length; j++) pushOne(extraList[j]);
    return out;
  }

  function getStableRuntimeEntryId(entry) {
    var e = (entry && typeof entry === "object") ? entry : {};
    var runtimeId = String(e.runtime_entry_id || "").trim();
    if (runtimeId) return runtimeId;
    var storageKind = String(e._storage_kind || "").trim().toLowerCase();
    var dbAlias = String(e._storage_db_alias || "").trim();
    var rowId = parseInt(e._storage_row_id || 0, 10) || 0;
    if (storageKind && dbAlias && rowId > 0) {
      return storageKind + "|" + dbAlias + "|" + rowId;
    }
    var explicit = String(e.entry_id || "").trim();
    if (explicit) return explicit;
    return "";
  }

  function getBundledEntryKey(entry) {
    var e = (entry && typeof entry === "object") ? entry : null;
    if (!e) return "";

    // Compact-mode winner refs and hydrated sqlite rows
    var storageKind = String(e.storage_kind || e._storage_kind || "sqlite").trim().toLowerCase();
    var dbAlias = String(e.db_alias || e._storage_db_alias || "").trim();
    var entryRowId = parseInt(e.entry_row_id || e._storage_row_id || 0, 10) || 0;
    var formRowId = parseInt(e.form_row_id || e._storage_form_row_id || 0, 10) || 0;
    if (dbAlias && entryRowId > 0) {
      return storageKind + "|" + dbAlias + "|" + entryRowId + (formRowId > 0 ? "|" + formRowId : "");
    }

    // Runtime/hydrated entry ids
    var runtimeId = String(e.runtime_entry_id || "").trim();
    if (runtimeId) return "runtime|" + runtimeId;

    var refKey = String(e.ref_key || "").trim();
    if (refKey) return "ref|" + refKey;

    var entryId = String(e.entry_id || "").trim();
    if (entryId) return "entry|" + entryId;

    // Stable semantic fallback
    var headword = String(e.headword || e.display_headword || e.surface_form || e.head || "").trim();
    var posRaw = String(e.pos_raw || e.pos || "").trim();
    var lemma = String(e.lemma_headword || e.morph_base || "").trim();
    return "fallback|" + headword + "|" + posRaw + "|" + lemma;
  }

  function pushUniqueBundledEntry(out, seen, entry) {
    if (!entry) return;
    var key = getBundledEntryKey(entry);
    if (!key) {
      out.push(entry);
      return;
    }
    if (seen[key]) return;
    seen[key] = 1;
    out.push(entry);
  }

  function getEntryMatchKind(entry) {
    var e = (entry && typeof entry === "object") ? entry : {};
    return String(e.match_kind || e._match_kind || e._match_source || "").trim().toLowerCase();
  }

  function getEntryDisplayHeadword(entry) {
    var e = (entry && typeof entry === "object") ? entry : {};
    return String(e.display_headword || e.headword || e.surface_form || "").trim();
  }

  function getEntryDisplayReading(entry) {
    var e = (entry && typeof entry === "object") ? entry : {};
    var displayReading = String(e.display_reading || e.reading || "").trim();
    if (displayReading) return displayReading;
    if (getEntryMatchKind(e) === "form") return "";
    return String(e.pinyin || "").trim();
  }

  function mergeEntryMorphInfo(target, incoming) {
    if (!target || typeof target !== "object" || !incoming || typeof incoming !== "object") return;
    var merged = mergeUniqueTextList(target.morph_info, incoming.morph_info);
    if (merged.length) target.morph_info = merged;
    else if (Object.prototype.hasOwnProperty.call(target, "morph_info")) delete target.morph_info;
  }

  function cloneHydratedEntryForAggregation(entry) {
    var out = {};
    var src = (entry && typeof entry === "object") ? entry : {};
    for (var key in src) {
      if (Object.prototype.hasOwnProperty.call(src, key)) out[key] = src[key];
    }
    if (Array.isArray(src.morph_info)) out.morph_info = src.morph_info.slice();
    if (Array.isArray(src.surface_forms)) out.surface_forms = src.surface_forms.slice();
    if (Array.isArray(src._matched_forms)) {
      out._matched_forms = src._matched_forms.map(function(row) {
        var copy = {};
        var raw = (row && typeof row === "object") ? row : {};
        for (var rowKey in raw) {
          if (!Object.prototype.hasOwnProperty.call(raw, rowKey)) continue;
          if (Array.isArray(raw[rowKey])) copy[rowKey] = raw[rowKey].slice();
          else copy[rowKey] = raw[rowKey];
        }
        return copy;
      });
    }
    if (src.forms && typeof src.forms === "object" && !Array.isArray(src.forms)) {
      out.forms = Object.assign({}, src.forms);
      if (Array.isArray(src.forms.rows)) {
        out.forms.rows = normalizeCanonicalFormRows(src.forms.rows);
      }
    }
    return out;
  }

  function normalizeCanonicalEntryRuntime(entry) {
    if (!entry || typeof entry !== "object") return entry;
    if (entry._glosses_raw && window.DictionaryEngine && window.DictionaryEngine._hydrateEntry) {
      window.DictionaryEngine._hydrateEntry(entry);
    }
    var activeLang = String(entry.lang_code || entry.lang || entry._lang_code || getCurrentLanguage() || "").trim().toLowerCase();

    if (!entry.pos_raw && entry.pos) {
      entry.pos_raw = String(entry.pos || "");
    }
    if (!entry.pos && entry.pos_raw) {
      entry.pos = String(entry.pos_raw || "");
    }
    if (!entry.tag && entry.xpos) {
      entry.tag = String(entry.xpos || "");
    } else if (!entry.xpos && entry.tag) {
      entry.xpos = String(entry.tag || "");
    }
    if (entry.romanization) {
      entry.romanization = convertNumericPinyin(String(entry.romanization));
    }
    if (entry.display_reading) {
      entry.display_reading = convertNumericPinyin(String(entry.display_reading || ""));
    }
    if (entry.entry_reading) {
      entry.entry_reading = convertNumericPinyin(String(entry.entry_reading || ""));
    }
    if (!entry.reading && entry.romanization) {
      entry.reading = entry.romanization;
    } else if (entry.reading) {
      entry.reading = convertNumericPinyin(String(entry.reading));
    }
    if (!entry.roman && entry.reading) {
      entry.roman = String(entry.reading || "");
    } else if (entry.roman) {
      entry.roman = convertNumericPinyin(String(entry.roman));
    }
    if (!entry._source && entry.source) {
      entry._source = String(entry.source || "");
    }
    if (!entry.display_reading && entry.reading) {
      entry.display_reading = String(entry.reading || "");
    }
    if (!entry.entry_reading && entry.reading) {
      entry.entry_reading = String(entry.reading || "");
    }
    if (entry.display_headword) {
      entry.display_headword = String(entry.display_headword || "").trim();
      entry.headword = entry.display_headword;
      if (!entry.surface_form) entry.surface_form = entry.display_headword;
    }
    if (!entry.display_headword && entry.headword) {
      entry.display_headword = String(entry.headword || "").trim();
    }
    if (!entry.head && (entry.display_headword || entry.surface_form || entry.headword)) {
      entry.head = String(entry.display_headword || entry.surface_form || entry.headword || "");
    }
    if (!entry.match_kind && entry._match_kind) {
      entry.match_kind = String(entry._match_kind || "").trim().toLowerCase();
    }
    if (!entry._match_source && (entry.match_kind || entry._match_kind)) {
      entry._match_source = String(entry.match_kind || entry._match_kind || "").trim().toLowerCase();
    }

    var sourceTag = String(entry._source || entry.source || "").trim().toLowerCase();
    if (sourceTag === "gemini") {
      var rawCommentary = String(entry._commentary || entry.commentary || "").trim();
      if (rawCommentary && entry._commentary === undefined) {
        entry._commentary = rawCommentary;
      }
      var rawLemma = String(entry._lemma || entry.lemma || entry.lemma_form || "").trim();
      if (rawLemma && entry._lemma === undefined) {
        entry._lemma = rawLemma;
      }
      if (!entry.morph_info && rawCommentary) {
        entry.morph_info = [rawCommentary];
      }
      if (!entry.morph_base && rawLemma) {
        entry.morph_base = rawLemma;
      }
    }

    if (entry.morph_info) {
      var initialMorphItems = Array.isArray(entry.morph_info) ? entry.morph_info : [entry.morph_info];
      entry.morph_info = mergeUniqueTextList(initialMorphItems.map(function(value) {
        return cleanMorphDisplayTags(value);
      }), []);
      if (!entry.morph_info.length) delete entry.morph_info;
    }
    if (entry.morph_base) {
      entry.morph_base = String(entry.morph_base || "").trim();
      if (!entry.morph_base) delete entry.morph_base;
    }

    var sensesFull = Array.isArray(entry.senses_full) ? entry.senses_full : [];
    var rawSenses = Array.isArray(entry.senses) ? entry.senses : [];
    if (!sensesFull.length && rawSenses.length && rawSenses[0] && typeof rawSenses[0] === "object") {
      sensesFull = rawSenses.slice();
    }
    if (!sensesFull.length && entry.glosses != null) {
      sensesFull = buildStructuredSensesFromRaw(entry.glosses, activeLang);
    }
    if (sensesFull.length) {
      var dedupedSensesFull = [];
      var seenSenseKeys = Object.create(null);
      for (var sfi = 0; sfi < sensesFull.length; sfi++) {
        var sense = sensesFull[sfi];
        var senseKey = "";
        if (sense && typeof sense === "object") {
          if (sense.qualifier != null) {
            var qualifier = String(stripSwahiliBracketMarkup(sense.qualifier, activeLang) || "").trim();
            if (qualifier) sense.qualifier = qualifier;
            else delete sense.qualifier;
          }
          if (Array.isArray(sense.glosses)) {
            var seenGlosses = Object.create(null);
            var dedupedGlosses = [];
            for (var gi = 0; gi < sense.glosses.length; gi++) {
              var gloss = String(stripSwahiliBracketMarkup(sense.glosses[gi] || "", activeLang) || "").trim();
              if (!gloss || seenGlosses[gloss]) continue;
              seenGlosses[gloss] = true;
              dedupedGlosses.push(gloss);
            }
            sense.glosses = dedupedGlosses;
            senseKey = dedupedGlosses.join("\u0001");
          } else {
            senseKey = String(stripSwahiliBracketMarkup(sense.gloss || sense.text || "", activeLang) || "").trim();
          }
        } else {
          senseKey = String(stripSwahiliBracketMarkup(sense || "", activeLang) || "").trim();
        }
        if (!senseKey || seenSenseKeys[senseKey]) continue;
        seenSenseKeys[senseKey] = true;
        dedupedSensesFull.push(sense);
      }
      sensesFull = dedupedSensesFull;
      entry.senses_full = sensesFull;
    }

    var flatSenses = sensesFull.length ? flattenCanonicalSenses(sensesFull, activeLang) : flattenCanonicalSenses(rawSenses, activeLang);
    if (flatSenses.length) {
      entry.senses = flatSenses;
    }

    if (entry.morph_info) {
      var morphItems = Array.isArray(entry.morph_info) ? entry.morph_info : [entry.morph_info];
      entry.morph_info = mergeUniqueTextList(morphItems.map(function(value) {
        return cleanMorphDisplayTags(stripSwahiliBracketMarkup(value, activeLang));
      }), []);
      if (!entry.morph_info.length) delete entry.morph_info;
    }
    if (entry.note != null) {
      var cleanedNote = String(stripSwahiliBracketMarkup(entry.note, activeLang) || "").trim();
      if (cleanedNote) entry.note = cleanedNote;
      else delete entry.note;
    }
    if (entry.etymology != null) {
      var cleanedEtymology = String(stripSwahiliBracketMarkup(entry.etymology, activeLang) || "").trim();
      if (cleanedEtymology) entry.etymology = cleanedEtymology;
      else delete entry.etymology;
    }
    if (entry.grammar != null) {
      var cleanedGrammar = String(stripSwahiliBracketMarkup(entry.grammar, activeLang) || "").trim();
      if (cleanedGrammar) entry.grammar = cleanedGrammar;
      else delete entry.grammar;
    }

    // Convert numeric pinyin inside gloss brackets for CC-CEDICT entries only.
    // e.g. "see 拜拜[bai2 bai2]" → "see 拜拜[bài bài]"
    var _entrySource = String(entry._source || entry.source || "").toLowerCase();
    if (_entrySource.indexOf("cc-cedict") !== -1 || _entrySource.indexOf("cedict") !== -1) {
      if (Array.isArray(entry.senses)) {
        for (var _si = 0; _si < entry.senses.length; _si++) {
          var _sense = entry.senses[_si];
          if (_sense && Array.isArray(_sense.glosses)) {
            for (var _gi = 0; _gi < _sense.glosses.length; _gi++) {
              _sense.glosses[_gi] = convertNumericPinyinInGloss(String(_sense.glosses[_gi] || ""));
            }
          } else if (typeof _sense === "string") {
            entry.senses[_si] = convertNumericPinyinInGloss(_sense);
          }
        }
      }
      if (Array.isArray(entry.senses_full)) {
        for (var _sfi = 0; _sfi < entry.senses_full.length; _sfi++) {
          var _sfSense = entry.senses_full[_sfi];
          if (_sfSense && Array.isArray(_sfSense.glosses)) {
            for (var _sfgi = 0; _sfgi < _sfSense.glosses.length; _sfgi++) {
              _sfSense.glosses[_sfgi] = convertNumericPinyinInGloss(String(_sfSense.glosses[_sfgi] || ""));
            }
          }
        }
      }
    }

    var rawForms = entry.forms;
    var forms = (rawForms && typeof rawForms === "object" && !Array.isArray(rawForms)) ? rawForms : {};
    var formRows = normalizeCanonicalFormRows(Array.isArray(rawForms) ? rawForms : forms.rows, activeLang);
    if (!formRows.length && entry._forms_raw) {
      try { formRows = normalizeCanonicalFormRows(JSON.parse(entry._forms_raw), activeLang); } catch (_) {}
    }
    if (!formRows.length && entry._forms_json) {
      try { formRows = normalizeCanonicalFormRows(JSON.parse(entry._forms_json), activeLang); } catch (_) {}
    }
    if (formRows.length) {
      forms.rows = formRows;
    }
    if (Object.keys(forms).length) {
      entry.forms = forms;
    }

    return entry;
  }

  function normalizeCanonicalEntryStore(entryStore) {
    var keys = Object.keys(entryStore || {});
    for (var i = 0; i < keys.length; i++) {
      normalizeCanonicalEntryRuntime(entryStore[keys[i]]);
    }
    return entryStore;
  }


  function getEntryHanjaFormsByRules(entry) {
    var e = entry || {};
    var forms = (e.forms && typeof e.forms === "object" && !Array.isArray(e.forms)) ? e.forms : {};
    var rows = Array.isArray(forms.rows) ? forms.rows : [];
    var out = [];
    var seen = Object.create(null);
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var word = Array.isArray(row) ? String(row[0] || "").trim() : String((row && row.word) || "").trim();
      var tagsStr = Array.isArray(row) ? String(row[1] || "") : String((row && (row.commentary || row.tags)) || "");
      if (!word || seen[word]) continue;
      var tags = tagsStr ? tagsStr.split(";") : [];
      for (var t = 0; t < tags.length; t++) {
        var tag = tags[t].trim().toLowerCase();
        if (tag === "hanja" || tag === "cjk" || tag === "sinitic") {
          seen[word] = true;
          out.push(word);
          break;
        }
      }
    }
    return out;
  }

  function getEntryHangeulFormsByRules(entry) {
    var e = entry || {};
    var forms = (e.forms && typeof e.forms === "object" && !Array.isArray(e.forms)) ? e.forms : {};
    var rows = Array.isArray(forms.rows) ? forms.rows : [];
    var out = [];
    var seen = Object.create(null);
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var word = Array.isArray(row) ? String(row[0] || "").trim() : String((row && row.word) || "").trim();
      var tagsStr = Array.isArray(row) ? String(row[1] || "") : String((row && (row.commentary || row.tags)) || "");
      if (!word || seen[word]) continue;
      var tags = tagsStr ? tagsStr.split(";") : [];
      for (var t = 0; t < tags.length; t++) {
        if (tags[t].trim().toLowerCase() === "hangeul") {
          seen[word] = true;
          out.push(word);
          break;
        }
      }
    }
    return out;
  }

  function etymKey(entry) {
    return (window.DictionaryEngine && window.DictionaryEngine.etymKey)
      ? window.DictionaryEngine.etymKey(entry || {})
      : ("t:" + String((entry && entry.etymology) || ""));
  }

  function hasExplicitEtymology(entry) {
    var e = entry || {};
    var etymText = String(e.etymology || "").trim();
    var etymNum = Number(e.etymology_number || 0);
    return !!etymText || (isFinite(etymNum) && etymNum > 0);
  }

  function buildEntryFallbackSignature(entry) {
    var e = entry || {};
    // Ensure lazy-parsed entries are hydrated before reading senses
    if (e._glosses_raw && window.DictionaryEngine && window.DictionaryEngine._hydrateEntry) {
      window.DictionaryEngine._hydrateEntry(e);
    }
    var head = String(e.headword || "").trim();
    var posRaw = String(e.pos_raw || e.pos || "").trim();
    var reading = String(e.reading || "").trim();
    var senses = Array.isArray(e.senses) ? e.senses : [];
    var firstSense = senses.length ? String(senses[0] || "").trim() : "";
    var sensesFull = Array.isArray(e.senses_full) ? e.senses_full : [];
    var firstSenseTags = "";
    if (sensesFull.length && sensesFull[0] && typeof sensesFull[0] === "object") {
      var tags = sensesFull[0].tags;
      if (Array.isArray(tags) && tags.length) {
        firstSenseTags = tags.map(function(t) { return String(t || "").trim(); }).filter(Boolean).join("|");
      }
    }
    return [
      head,
      posRaw,
      reading,
      firstSense,
      firstSenseTags
    ].join("\u241f");
  }

  function entryGroupBucketKey(entry) {
    var base = etymKey(entry);
    // Language-agnostic fallback: compact TSV rows often have no explicit
    // etymology metadata (base = "t:"). Preserve row-level separation
    // so unrelated homographs do not collapse into one mixed entry block.
    if (base === "t:" && !hasExplicitEtymology(entry)) {
      return base + "|" + buildEntryFallbackSignature(entry);
    }
    return base;
  }

  function attachWiktForms(target, surface, entries) {
    var chosen = entries && entries.length ? entries[0] : null;
    if (!chosen) return;
    // Ensure entries are hydrated (lazy gloss parse)
    for (var hi = 0; hi < entries.length; hi++) _ensureEntryHydrated(entries[hi]);

    var ipaVariants = chosen.ipa_variants || [];
    if (ipaVariants && ipaVariants.length) target.ipa_variants = ipaVariants;

    var audioUrls = chosen.audio_urls || [];
    if (audioUrls && audioUrls.length) target.audio_urls = audioUrls;

    var allGroups = [];
    var hasNormalizedMatch = !!target.normalized_match;
    for (var i = 0; i < (entries || []).length; i++) {
      var e = entries[i] || {};
      var sensesFull = Array.isArray(e.senses_full) ? e.senses_full : [];
      if (!sensesFull.length) continue;

      var rowHeadword = getEntryDisplayHeadword(e);
      var baseHeadword = String(e.lemma_headword || e.morph_base || "").trim();
      var rowReading = String(e.display_reading || e.reading || "").trim();
      var isFormMatch = (getEntryMatchKind(e) === "form");
      var pg = {
        headword: rowHeadword || baseHeadword || "",
        base_headword: baseHeadword,
        is_form_match: isFormMatch,
        reading: rowReading,
        pos: abbreviatePos(e.pos_raw || e.pos || ""),
        senses: sensesFull,
        normalized_match: !!e.normalized_match,
        // When the entry has _decomp_surface_form (lemma override match with a
        // flipped headword), store the entry object directly as the ref so that
        // reader_wikt.js receives the modified display_headword and
        // _decomp_surface_form fields — resolveEntryRef passes objects through
        // unchanged, bypassing the global entry store.
        _entryRef: e._decomp_surface_form ? e : _entryRefKey(e)
      };
      if (pg.normalized_match) hasNormalizedMatch = true;
      var pgMorphInfo = Array.isArray(e.morph_info)
        ? e.morph_info.slice().map(function(v) { return String(v || "").trim(); }).filter(Boolean)
        : (e.morph_info ? [String(e.morph_info).trim()] : []);
      if (pgMorphInfo.length) {
        pg.morph_info = pgMorphInfo;
      }
      var pgMorphBase = String(e.morph_base || "").trim();
      if (pgMorphBase) {
        pg.morph_base = pgMorphBase;
      }
      if (e.grammar) {
        pg.grammar = String(e.grammar);
      }
      var hanjaForms = getEntryHanjaFormsByRules(e);
      if (hanjaForms.length) {
        pg.hanja_forms = hanjaForms;
      }
      var hangeulForms = getEntryHangeulFormsByRules(e);
      if (hangeulForms.length) {
        pg.hangeul_forms = hangeulForms;
      }
      var altForms = Array.isArray(e.alt_forms) ? e.alt_forms : [];
      if (altForms.length) {
        pg.alt_forms = altForms.slice();
      }

      var group = {
        headword: pg.headword || String(surface || "").trim() || "",
        reading: rowReading,
        etym_key: entryGroupBucketKey(e),
        pos_groups: [pg],
        _entryRef: e._decomp_surface_form ? e : _entryRefKey(e)
      };
      var etym = String(e.etymology || "");
      if (etym) group.etymology = etym;
      if (altForms.length) group.alt_forms = altForms.slice();
      if (Array.isArray(e.synonyms) && e.synonyms.length) group.synonyms = mergeWordLists(e.synonyms);
      if (Array.isArray(e.antonyms) && e.antonyms.length) group.antonyms = mergeWordLists(e.antonyms);
      if (Array.isArray(e.derived) && e.derived.length) group.derived = mergeWordLists(e.derived);
      if (Array.isArray(e.related) && e.related.length) group.related = mergeWordLists(e.related);

      allGroups.push(group);
    }
    if (allGroups.length) target.entry_groups = allGroups;
    if (chosen.senses_full) target.senses_full = chosen.senses_full;
    if (hasNormalizedMatch) target.normalized_match = true;
    else if (Object.prototype.hasOwnProperty.call(target, "normalized_match")) delete target.normalized_match;
  }

  function buildWiktG2P(word, engine, fallbackRoman) {
    var entry = engine ? engine.lookup(word) : null;
    var ipa = "";
    var ipaVariants = [];
    if (entry) {
      ipa = entry.reading || "";
      ipaVariants = entry.ipa_variants || [];
    }
    if (!ipa) ipa = String(fallbackRoman || "");
    return {
      overall_roman: ipa,
      syllables: [],
      ipa_variants: ipaVariants
    };
  }

  function _ensureEntryHydrated(entry) {
    return normalizeCanonicalEntryRuntime(entry);
  }

  // DEBUG MAP: creates the intermediate dict_fill piece object.
  // Provenance is NOT attached here initially; source propagation happens later.
  function buildFillPieceFromEntry(surfaceText, entry, allEntries) {
    _ensureEntryHydrated(entry);
    var surface = String(surfaceText || "");
    var displayHead = getEntryDisplayHeadword(entry) || surface;
    var lemmaHead = String((entry && entry.lemma_headword) || "").trim();
    var displayReading = getEntryDisplayReading(entry);
    var fill = {
      text: surface,
      head: displayHead || surface,
      headword: displayHead || surface,
      roman: displayReading,
      reading: displayReading,
      senses: (entry && entry.senses) || [],
      pos: (entry && entry.pos) || "",
      pos_raw: (entry && entry.pos_raw) || (entry && entry.pos) || "",
      source: (entry && (entry._source || entry.source)) || "KAIKKI",
      entries: Array.isArray(allEntries) ? allEntries.slice() : []
    };
    var keys = [
      "entry_id",
      "_source",
      "_glosses_raw",
      "_forms_raw",
      "_forms_json",
      "_commentary",
      "_lemma",
      "etymology",
      "senses_full",
      "ipa_variants",
      "ref_key",
      "match_kind",
      "runtime_entry_id",
      "display_headword",
      "lemma_headword",
      "display_reading",
      "entry_reading",
      "is_alternate_match",
      "grammar",
      "morph_info",
      "morph_base",
      "forms",
      "forms_meta",
      "spelling_header"
    ];
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      var v = entry ? entry[k] : null;
      if (v) fill[k] = v;
    }
    applyFillRepresentativeEntry(fill, entry, true);
    if (surface) {
      fill.surface_form = surface;
    }
    if (lemmaHead) {
      fill.lemma_form = lemmaHead;
      if (!fill.morph_base && getEntryMatchKind(entry) === "form") fill.morph_base = lemmaHead;
    }
    return fill;
  }

  function cloneMwtChildPieceRow(row) {
    var src = (row && typeof row === "object") ? row : {};
    var out = {};
    for (var key in src) {
      if (!Object.prototype.hasOwnProperty.call(src, key)) continue;
      var val = src[key];
      if (Array.isArray(val)) out[key] = val.slice();
      else out[key] = val;
    }

    if (Array.isArray(src.entries)) out.entries = src.entries.slice();
    if (Array.isArray(src.morph_info)) out.morph_info = src.morph_info.slice();

    return out;
  }

  function buildFillResult(text, entries, mode) {
    var best = entries[0];
    var fillEntry = buildFillPieceFromEntry(text, best, entries);
    return {
      entries: entries.slice(),
      fill: {
        mode: mode,
        fills: [fillEntry],
        has_known: true,
        has_unknown: false
      }
    };
  }

  function buildKoreanCompoundLemmaSurfaceAnchorFill(surfaceText) {
    var surface = String(surfaceText || "").trim();
    if (!surface) return null;
    return {
      mode: "ko_compound_lemma_anchor",
      fills: [{
        text: surface,
        head: surface,
        headword: surface,
        surface_form: surface,
        roman: "",
        reading: "",
        senses: [],
        pos: "",
        pos_raw: "",
        source: "COMPOSITE",
        entries: [],
        _korean_compound_lemma_anchor: true
      }],
      has_known: true,
      has_unknown: false,
      has_lemma_promotion: false,
      has_korean_compound_lemma_anchor: true
    };
  }

  function _charDiff(a, b) {
    // Count characters in a not present in b (simple bag difference)
    var longer = a.length > b.length ? a : b;
    var shorter = a.length > b.length ? b : a;
    return longer.length - shorter.length + (function() {
      var diff = 0;
      for (var i = 0; i < shorter.length; i++) {
        if (longer.indexOf(shorter[i]) === -1) diff++;
      }
      return diff;
    }());
  }

  function _pickClosestToSurface(entries, surfaceText) {
    // Returns the entry whose display_headword is the closest match to surfaceText.
    // Exact match wins; otherwise least character difference; ties go to first.
    var surface = String(surfaceText || "").trim();
    var best = entries[0];
    if (!surface) return best;
    var bestHead = getEntryDisplayHeadword(best);
    if (bestHead === surface) return best;
    var bestDiff = _charDiff(bestHead, surface);
    for (var i = 1; i < entries.length; i++) {
      var head = getEntryDisplayHeadword(entries[i]);
      if (head === surface) return entries[i];
      var diff = _charDiff(head, surface);
      if (diff < bestDiff) {
        best = entries[i];
        bestDiff = diff;
        bestHead = head;
      }
    }
    return best;
  }

  function dedupeEntriesByIdentity(entries, surfaceText) {
    var out = [];
    var grouped = Object.create(null);
    var order = [];
    var list = Array.isArray(entries) ? entries : [];
    for (var i = 0; i < list.length; i++) {
      var entry = list[i];
      if (!entry || typeof entry !== "object") continue;
      var runtimeId = getStableRuntimeEntryId(entry);
      var key = runtimeId || ("anon:" + i);
      if (!grouped[key]) {
        grouped[key] = [];
        order.push(key);
      }
      grouped[key].push(entry);
    }

    for (var oi = 0; oi < order.length; oi++) {
      var group = grouped[order[oi]] || [];
      if (group.length === 1) {
        out.push(group[0]);
        continue;
      }
      // Hard-dedup by entry id: pick the representative closest to the surface
      // token, then merge all other morph_info into it.
      var winner = _pickClosestToSurface(group, surfaceText);
      for (var gi = 0; gi < group.length; gi++) {
        if (group[gi] !== winner) mergeEntryMorphInfo(winner, group[gi]);
      }
      out.push(winner);
    }
    return out;
  }

  function collectRecoveredLemmaHintIndexes(fill, lemmaHintObjects, engine) {
    var rows = (fill && Array.isArray(fill.fills)) ? fill.fills : [];
    var hints = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
    var matched = [];
    for (var hi = 0; hi < hints.length; hi++) matched.push(false);
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      if (String(row.source || "").toUpperCase() === "UNKNOWN") continue;
      var rowEntries = Array.isArray(row.entries) ? row.entries : [];
      for (var hi2 = 0; hi2 < hints.length; hi2++) {
        if (matched[hi2]) continue;
        var hint = hints[hi2];
        for (var ei = 0; ei < rowEntries.length; ei++) {
          if (findLemmaHintMatchForEntry(rowEntries[ei], [hint], engine)) {
            matched[hi2] = true;
            break;
          }
        }
      }
    }
    var out = [];
    for (var mi = 0; mi < matched.length; mi++) {
      if (matched[mi]) out.push(mi);
    }
    return out;
  }

  function lookupExactEntriesForText(queryText, engine) {
    var query = String(queryText || "").trim();
    if (!query || !engine || typeof engine.lookup_all !== "function") return [];
    var entries = engine.lookup_all(query) || [];
    return Array.isArray(entries) ? entries.slice() : [];
  }

  function lookupExactHeadwordEntriesForText(queryText, engine) {
    var query = String(queryText || "").trim();
    if (!query || !engine) return [];
    var out = [];
    var seen = Object.create(null);
    var keys = (engine && typeof engine._lookup_keys === "function")
      ? engine._lookup_keys(query)
      : [normalizeLookupKey(engine, query)];

    if (engine._compact_mode && engine._hw_index) {
      for (var ki = 0; ki < keys.length; ki++) {
        var key = String(keys[ki] || "").trim();
        if (!key) continue;
        var hwHits = engine._hw_index[key];
        if (!hwHits) continue;
        for (var hi = 0; hi < hwHits.length; hi++) {
          var alias = hwHits[hi][0];
          var eid = hwHits[hi][1];
          var storageKind = (engine._db_alias_map && (engine._db_alias_map[alias] === "custom" || alias === "customdb"))
            ? "custom"
            : "sqlite";
          pushUniqueBundledEntry(out, seen, {
            _winner_ref: true,
            storage_kind: storageKind,
            db_alias: alias,
            entry_row_id: eid,
            match_kind: "headword",
            match_key: key,
            headword: query
          });
        }
      }
      return out;
    }

    if (!engine._by_word) return [];
    for (var bi = 0; bi < keys.length; bi++) {
      var bucketKey = String(keys[bi] || "").trim();
      if (!bucketKey) continue;
      var bucket = engine._by_word[bucketKey];
      if (!bucket) continue;
      for (var ei = 0; ei < bucket.length; ei++) {
        pushUniqueBundledEntry(out, seen, bucket[ei]);
      }
    }
    return out;
  }

  function collectWholeTokenExactLemmaEntries(surfaceText, lemmaHintObjects, engine) {
    var surface = String(surfaceText || "").trim();
    var hints = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
    if (!surface || !hints.length || !engine || typeof engine.lookup_all !== "function") return [];
    var lang = String((engine && engine._lang_code) || getCurrentLanguage() || "").trim().toLowerCase();
    if (isKoreanLanguageCode(lang) && hints.length > 1) return [];
    if (hints.length !== 1) return [];

    var out = [];
    var surfaceKey = normalizeVisibleComparisonText(surface);
    var hintTexts = getLemmaHintCandidateTexts(hints[0], engine);
    for (var i = 0; i < hintTexts.length; i++) {
      var hintText = String(hintTexts[i] || "").trim();
      if (!hintText) continue;
      if (surfaceKey && normalizeVisibleComparisonText(hintText) === surfaceKey) continue;
      var entries = lookupExactHeadwordEntriesForText(hintText, engine);
      for (var ei = 0; ei < entries.length; ei++) out.push(entries[ei]);
    }
    return dedupeEntriesByIdentity(out, surface);
  }

  function buildLemmaHintLookupPart(rawHint, engine) {
    var hint = cloneLemmaHintObject(rawHint);
    var rawHintText = String(hint.text || hint.lemma || "").trim();
    var hintTexts = getLemmaHintCandidateTexts(hint, engine);
    var matchedText = "";
    var matchedEntries = [];
    for (var hti = 0; hti < hintTexts.length; hti++) {
      var candidateText = hintTexts[hti];
      if (!candidateText) continue;
      var candidateEntries = lookupExactEntriesForText(candidateText, engine);
      if (!candidateEntries.length) continue;
      matchedText = candidateText;
      matchedEntries = candidateEntries;
      break;
    }
    var partText = matchedText || rawHintText;
    if (!partText) return null;
    return {
      text: partText,
      source_text: rawHintText || partText,
      surface_text: String(hint.surface_text || ""),
      surface_slice: Array.isArray(hint.surface_slice) ? hint.surface_slice.slice(0, 2) : null,
      upos: String(hint.upos || "").trim(),
      xpos: String(hint.xpos || "").trim(),
      entries: matchedEntries,
      exact: !!(matchedText && matchedEntries.length),
      hint_object: hint
    };
  }

  function shouldBypassKoreanCompoundLemmaRealignment(surfaceText, lemmaHintObjects, engine, options) {
    var lookupOpts = options || {};
    if (lookupOpts.korean_compound_child_lookup) return false;
    if (lookupOpts.mwt_single_child) return false;
    if (Array.isArray(lookupOpts.mwt_parts) && lookupOpts.mwt_parts.length > 1) return false;
    var lang = String((engine && engine._lang_code) || getCurrentLanguage() || "").trim().toLowerCase();
    if (!isKoreanLanguageCode(lang)) return false;
    var surface = String(surfaceText || "").trim();
    var hints = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
    if (!surface || hints.length <= 1) return false;
    var parts = [];
    for (var i = 0; i < hints.length; i++) {
      var text = String((hints[i] && (hints[i].text || hints[i].lemma)) || "").trim();
      if (text) parts.push(text);
    }
    if (parts.length <= 1) return false;
    return normalizeVisibleComparisonText(parts.join("")) !== normalizeVisibleComparisonText(surface);
  }

  function buildKoreanCompoundLemmaChildLookupPayloads(lemmaHintObjects, engine, includeDebugTrace) {
    var hints = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
    var out = [];
    if (!engine || hints.length <= 1) return out;
    for (var i = 0; i < hints.length; i++) {
      var hint = hints[i] || {};
      var childText = String(hint.text || hint.lemma || "").trim();
      if (!childText) continue;
      var childUpos = String(hint.upos || "").trim();
      var childXpos = String(hint.xpos || "").trim();
      var childLookup = buildSinglePassSurfaceLookup(
        childText,
        childText,
        engine,
        childUpos,
        childXpos,
        includeDebugTrace,
        {
          skipWholeSurfaceExact: false,
          mwt_parts: [],
          korean_compound_child_lookup: true
        }
      );
      out.push({
        text: childText,
        source_text: String(hint.source_text || hint.text || hint.lemma || "").trim(),
        part_index: i,
        upos: childUpos,
        xpos: childXpos,
        lookup: childLookup
      });
    }
    return out.length > 1 ? out : [];
  }

  function buildExplicitLemmaHintAlignmentState(surfaceText, parts, includeDebugTrace) {
    var surface = String(surfaceText || "").trim();
    var hintParts = Array.isArray(parts) ? parts : [];
    if (!surface || !hintParts.length) return null;

    var groups = [];
    var boundaries = [];
    var cursor = 0;
    var usedExplicitSlices = false;
    // If any part carries a Trankit surface_slice, ALL parts must carry one —
    // offset-based alignment is the single source of truth and we never mix
    // it with cursor/substring matching.
    var anyHasSlice = false;
    for (var ai = 0; ai < hintParts.length; ai++) {
      var ap = hintParts[ai] || {};
      if (Array.isArray(ap.surface_slice) && ap.surface_slice.length >= 2) {
        anyHasSlice = true;
        break;
      }
    }
    for (var i = 0; i < hintParts.length; i++) {
      var part = hintParts[i] || {};
      var partSurface = String(part.surface_text || "");
      var rawSlice = Array.isArray(part.surface_slice) ? part.surface_slice : null;
      var nextCursor = cursor + partSurface.length;
      if (rawSlice && rawSlice.length >= 2) {
        var sliceStart = parseInt(rawSlice[0], 10);
        var sliceEnd = parseInt(rawSlice[1], 10);
        if (!isFinite(sliceStart) || !isFinite(sliceEnd)) return null;
        if (sliceStart < 0 || sliceEnd < sliceStart || sliceEnd > surface.length) return null;
        if (sliceStart < cursor) return null;
        cursor = sliceStart;
        nextCursor = sliceEnd;
        usedExplicitSlices = true;
      } else if (anyHasSlice) {
        // MWT/slice mode: every part must have an authoritative slice. Missing
        // one is a hard error — we refuse to fall back to substring matching.
        return null;
      } else {
        if (!partSurface) return null;
        if (surface.slice(cursor, cursor + partSurface.length) !== partSurface) return null;
        nextCursor = cursor + partSurface.length;
      }
      groups.push({
        start: cursor,
        end: nextCursor,
        part_ids: [i]
      });
      cursor = nextCursor;
      if (i < hintParts.length - 1) boundaries.push(cursor);
    }
    if (!usedExplicitSlices && cursor !== surface.length) return null;
    if (usedExplicitSlices && groups.length && groups[groups.length - 1].end !== surface.length) return null;

    var runtimeDebug = null;
    if (includeDebugTrace) {
      runtimeDebug = {
        surface_text: surface,
        lang_code: String(getCurrentLanguage() || "").toLowerCase(),
        normalized_parts: hintParts.map(function(part) { return String(part.text || ""); }),
        explicit_surface_parts: hintParts.map(function(part) {
          return {
            index: parseInt(part.index, 10) || 0,
            surface_text: String(part.surface_text || ""),
            surface_slice: Array.isArray(part.surface_slice) ? part.surface_slice.slice(0, 2) : null,
            text: String(part.text || ""),
            source_text: String(part.source_text || "")
          };
        }),
        match_basis: usedExplicitSlices ? "mwt_parts_slice" : "mwt_parts",
        boundaries: boundaries.slice(),
        groups: groups.map(function(group) {
          return {
            start: parseInt(group.start, 10) || 0,
            end: parseInt(group.end, 10) || 0,
            part_ids: Array.isArray(group.part_ids) ? group.part_ids.slice() : []
          };
        })
      };
    }

    return {
      alignment_groups: groups,
      runtime_alignment_debug: runtimeDebug
    };
  }

  function buildLemmaHintAlignmentState(surfaceText, lemmaHintObjects, engine, includeDebugTrace) {
    var surface = String(surfaceText || "").trim();
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
    if (!parts.length) return null;

    var explicitState = buildExplicitLemmaHintAlignmentState(surface, parts, includeDebugTrace);
    if (explicitState && Array.isArray(explicitState.alignment_groups) && explicitState.alignment_groups.length) {
      return {
        surface: surface,
        parts: parts,
        alignment_groups: explicitState.alignment_groups,
        runtime_alignment_debug: explicitState.runtime_alignment_debug,
        exact_part_count: exactPartCount,
        total_part_count: parts.length
      };
    }

    var alignment = buildGenericSurfacePartAlignment(surface, parts.map(function(part) { return part.text; }), {
      langCode: String(getCurrentLanguage() || "").toLowerCase(),
      debugTrace: !!includeDebugTrace
    });
    if (!alignment || !Array.isArray(alignment.groups) || !alignment.groups.length) return null;

    var alignmentGroups = alignment.groups.map(function(group) {
      return {
        start: parseInt(group && group.start, 10) || 0,
        end: parseInt(group && group.end, 10) || 0,
        part_ids: Array.isArray(group && group.part_ids) ? group.part_ids.slice() : []
      };
    });
    var presentPartIds = Object.create(null);
    for (var agi = 0; agi < alignmentGroups.length; agi++) {
      var presentIds = alignmentGroups[agi].part_ids;
      for (var api = 0; api < presentIds.length; api++) {
        var presentId = parseInt(presentIds[api], 10);
        if (!isFinite(presentId) || presentId < 0 || presentId >= parts.length) continue;
        presentPartIds[presentId] = true;
      }
    }
    for (var mpi = 0; mpi < parts.length; mpi++) {
      if (presentPartIds[mpi]) continue;
      var bestGroupIndex = -1;
      var bestDistance = Infinity;
      for (var bgi = 0; bgi < alignmentGroups.length; bgi++) {
        var candidateIds = alignmentGroups[bgi].part_ids;
        if (!candidateIds.length) continue;
        for (var cpi = 0; cpi < candidateIds.length; cpi++) {
          var candidateId = parseInt(candidateIds[cpi], 10);
          if (!isFinite(candidateId) || candidateId < 0) continue;
          var distance = Math.abs(candidateId - mpi);
          if (distance < bestDistance) {
            bestDistance = distance;
            bestGroupIndex = bgi;
          }
        }
      }
      if (bestGroupIndex >= 0) {
        alignmentGroups[bestGroupIndex].part_ids.push(mpi);
        alignmentGroups[bestGroupIndex].part_ids.sort(function(a, b) { return a - b; });
        presentPartIds[mpi] = true;
      }
    }

    return {
      surface: surface,
      parts: parts,
      alignment_groups: alignmentGroups,
      runtime_alignment_debug: (alignment && alignment._debug_runtime_alignment && typeof alignment._debug_runtime_alignment === "object")
        ? alignment._debug_runtime_alignment
        : null,
      exact_part_count: exactPartCount,
      total_part_count: parts.length
    };
  }

  function buildDirectLemmaHintMappingState(surfaceText, lemmaHintObjects, engine, includeDebugTrace) {
    var surface = String(surfaceText || "").trim();
    var hints = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
    if (!surface || !hints.length || !engine) return null;

    var parts = [];
    var groups = [];
    var boundaries = [];
    var cursor = 0;
    var exactPartCount = 0;
    var usedExplicitSlices = true;
    for (var i = 0; i < hints.length; i++) {
      var srcHint = hints[i];
      // Every MWT hint carries a surface_slice. Null hints are no longer
      // allowed here — buildLemmaHintData keeps a hint for every child.
      if (!srcHint) return null;
      var part = buildLemmaHintLookupPart(srcHint, engine);
      if (!part) {
        // Child had no dictionary hits under the lemma — synthesize a minimal
        // part record so its Trankit offsets are preserved and the gap gets
        // filled by per-child greedy downstream.
        part = {
          text: String(srcHint.surface_text || srcHint.text || ""),
          source_text: String(srcHint.text || srcHint.surface_text || ""),
          surface_text: String(srcHint.surface_text || ""),
          surface_slice: Array.isArray(srcHint.surface_slice) ? srcHint.surface_slice.slice(0, 2) : null,
          upos: String(srcHint.upos || ""),
          xpos: String(srcHint.xpos || ""),
          entries: [],
          exact: false,
          hint_object: srcHint
        };
      }
      var partSurface = String(part.surface_text || "");
      if (!partSurface) return null;
      part.index = i;
      if (part.exact) exactPartCount += 1;
      var rawSlice = Array.isArray(part.surface_slice) ? part.surface_slice : null;
      // surface_slice is mandatory. No cursor/length fallback permitted.
      if (!rawSlice || rawSlice.length < 2) return null;
      var sliceStart = parseInt(rawSlice[0], 10);
      var sliceEnd = parseInt(rawSlice[1], 10);
      if (!isFinite(sliceStart) || !isFinite(sliceEnd)) return null;
      if (sliceStart < 0 || sliceEnd < sliceStart || sliceEnd > surface.length) return null;
      if (sliceStart < cursor) return null;
      cursor = sliceStart;
      var nextCursor = sliceEnd;
      parts.push(part);
      groups.push({
        start: cursor,
        end: nextCursor,
        part_ids: [i]
      });
      cursor = nextCursor;
      if (i < hints.length - 1) boundaries.push(cursor);
    }
    if (groups.length && groups[groups.length - 1].end !== surface.length) return null;
    var forcedCoverage = false;

    var runtimeDebug = null;
    if (includeDebugTrace) {
      runtimeDebug = {
        surface_text: surface,
        lang_code: String(getCurrentLanguage() || "").toLowerCase(),
        normalized_parts: parts.map(function(part) { return String(part.text || ""); }),
        explicit_surface_parts: parts.map(function(part) {
          return {
            index: parseInt(part.index, 10) || 0,
            surface_text: String(part.surface_text || ""),
            surface_slice: Array.isArray(part.surface_slice) ? part.surface_slice.slice(0, 2) : null,
            text: String(part.text || ""),
            source_text: String(part.source_text || "")
          };
        }),
        match_basis: usedExplicitSlices ? "mwt_parts_slice_direct" : "mwt_parts_direct",
        forced_surface_coverage: !!forcedCoverage,
        boundaries: boundaries.slice(),
        groups: groups.map(function(group) {
          return {
            start: parseInt(group.start, 10) || 0,
            end: parseInt(group.end, 10) || 0,
            part_ids: Array.isArray(group.part_ids) ? group.part_ids.slice() : []
          };
        })
      };
    }

    return {
      surface: surface,
      parts: parts,
      alignment_groups: groups,
      runtime_alignment_debug: runtimeDebug,
      exact_part_count: exactPartCount,
      total_part_count: parts.length
    };
  }

  function cloneFillRowsWithSurfaceOffsets(fills, expectedText, startOffset) {
    var rows = Array.isArray(fills) ? fills : [];
    var surfaceText = String(expectedText || "");
    var offsetBase = parseInt(startOffset, 10) || 0;
    var cursor = 0;
    var out = [];
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      var pieceText = getFillPieceSurfaceText(row);
      if (!pieceText) return null;
      if (surfaceText.slice(cursor, cursor + pieceText.length) !== pieceText) return null;
      var clone = {};
      for (var key in row) {
        if (Object.prototype.hasOwnProperty.call(row, key)) clone[key] = row[key];
      }
      clone._surface_start = offsetBase + cursor;
      cursor += pieceText.length;
      clone._surface_end = offsetBase + cursor;
      out.push(clone);
    }
    if (cursor !== surfaceText.length) return null;
    return out;
  }

  // REMOVED: buildExactMwtPartLookupResult and buildMwtPartwiseFallbackLookupResult
  // These were a bespoke MWT segmenter that duplicated logic from the main
  // segmenter (buildSinglePassSurfaceLookup) and introduced cursor/substring
  // heuristics that broke sandhi tokens. MWT children are now each fed
  // directly into buildSinglePassSurfaceLookup (with mwt_parts:[]) and the
  // resulting fills are rebased onto the parent surface via Trankit surface_slice.

  function buildLemmaOverrideResultFromState(state, engine, upos, xpos, includeDebugTrace) {
    void xpos;
    if (!state || !engine) return null;
    var fillRows = [];
    var gapSegments = [];
    for (var gi = 0; gi < state.alignment_groups.length; gi++) {
      var group = state.alignment_groups[gi] || {};
      var start = parseInt(group.start, 10);
      var end = parseInt(group.end, 10);
      if (!isFinite(start) || start < 0) start = 0;
      if (!isFinite(end) || end < start) end = start;
      var surfaceSlice = state.surface.slice(start, end);
      var rawIds = Array.isArray(group.part_ids) ? group.part_ids : [];
      var partIds = [];
      var seenPartIds = Object.create(null);
      for (var pi = 0; pi < rawIds.length; pi++) {
        var pid = parseInt(rawIds[pi], 10);
        if (!isFinite(pid) || pid < 0 || pid >= state.parts.length || seenPartIds[pid]) continue;
        seenPartIds[pid] = true;
        partIds.push(pid);
      }
      if (!partIds.length) continue;

      var exactPartIds = [];
      var gapHintObjects = [];
      for (var pj = 0; pj < partIds.length; pj++) {
        var part = state.parts[partIds[pj]];
        if (!part) continue;
        if (part.exact && Array.isArray(part.entries) && part.entries.length) {
          exactPartIds.push(partIds[pj]);
        } else {
          gapHintObjects.push(cloneLemmaHintObject(part.hint_object || {
            text: part.text,
            upos: part.upos,
            xpos: part.xpos
          }));
        }
      }

      if (exactPartIds.length) {
        for (var pk = 0; pk < exactPartIds.length; pk++) {
          var partId = exactPartIds[pk];
          var exactPart = state.parts[partId];
          if (!exactPart) continue;
          var partEntries = Array.isArray(exactPart.entries) ? exactPart.entries.slice() : [];
          if (!partEntries.length) continue;
          var best = chooseEntry(surfaceSlice || exactPart.text, partEntries, engine) || partEntries[0];
          var fillRow = buildFillPieceFromEntry(surfaceSlice, best, partEntries);
          if (exactPart.text) fillRow.head = exactPart.text;
          fillRow._lemma_override = exactPart.text;
          fillRow._lemma_override_part_count = 1;
          fillRow._lemma_part_index = exactPart.index;
          fillRow._surface_start = start;
          fillRow._surface_end = end;
          if (exactPart.upos) fillRow._lemma_upos_hint = exactPart.upos;
          if (exactPart.xpos) fillRow._lemma_xpos_hint = exactPart.xpos;
          fillRows.push(fillRow);
        }
      } else if (surfaceSlice) {
        gapSegments.push({
          start: start,
          end: end,
          text: surfaceSlice,
          part_ids: partIds.slice(),
          hint_objects: gapHintObjects.slice(),
          part_index: partIds.length === 1 ? partIds[0] : null
        });
      }
    }
    if (!fillRows.length && !gapSegments.length) return null;

    var gapDebug = [];
    for (var gsi = 0; gsi < gapSegments.length; gsi++) {
      var gap = gapSegments[gsi] || {};
      var gapText = String(gap.text || "");
      if (!gapText) continue;
      var singleGapHint = (Array.isArray(gap.hint_objects) && gap.hint_objects.length === 1)
        ? (gap.hint_objects[0] || null)
        : null;
      var gapFillOpts = {
        allowExact: false,
        upos: (singleGapHint && singleGapHint.upos) ? String(singleGapHint.upos || "") : (upos || "")
      };
      if (includeDebugTrace) gapFillOpts.debug = true;
      if (Array.isArray(gap.hint_objects) && gap.hint_objects.length) gapFillOpts.lemma_hints = gap.hint_objects.slice();
      var gapFill = engine.fill_token(gapText, gapFillOpts);
      var gapRowsSrc = (gapFill && Array.isArray(gapFill.fills) && gapFill.fills.length)
        ? gapFill.fills
        : [{
            text: gapText,
            head: gapText,
            roman: "",
            senses: [],
            pos: "",
            source: "UNKNOWN"
          }];
      var offsetRows = cloneFillRowsWithSurfaceOffsets(gapRowsSrc, gapText, gap.start);
      if (!offsetRows || !offsetRows.length) return null;
      var gapPartIndex = parseInt(gap.part_index, 10);
      if (!isFinite(gapPartIndex)) gapPartIndex = null;
      for (var gri = 0; gri < offsetRows.length; gri++) {
        var offsetRow = offsetRows[gri] || {};
        if (gapPartIndex !== null) offsetRow._lemma_part_index = gapPartIndex;
        if (singleGapHint) {
          if (singleGapHint.upos) offsetRow._lemma_upos_hint = String(singleGapHint.upos || "");
          if (singleGapHint.xpos) offsetRow._lemma_xpos_hint = String(singleGapHint.xpos || "");
        }
        fillRows.push(offsetRow);
      }
      if (includeDebugTrace) {
        gapDebug.push({
          start: parseInt(gap.start, 10) || 0,
          end: parseInt(gap.end, 10) || 0,
          text: gapText,
          part_ids: Array.isArray(gap.part_ids) ? gap.part_ids.slice() : [],
          mode: String((gapFill && gapFill.mode) || "greedy"),
          has_known: !!(gapFill && gapFill.has_known),
          has_unknown: !!(gapFill && gapFill.has_unknown),
          fills: buildDebugFillPreview({ fills: gapRowsSrc }),
          dp_debug: (gapFill && gapFill.dp_debug && typeof gapFill.dp_debug === "object") ? gapFill.dp_debug : null
        });
      }
    }

    fillRows.sort(function(a, b) {
      var aStart = parseInt(a && a._surface_start, 10);
      var bStart = parseInt(b && b._surface_start, 10);
      if (!isFinite(aStart)) aStart = 0;
      if (!isFinite(bStart)) bStart = 0;
      if (aStart !== bStart) return aStart - bStart;
      var aEnd = parseInt(a && a._surface_end, 10);
      var bEnd = parseInt(b && b._surface_end, 10);
      if (!isFinite(aEnd)) aEnd = aStart;
      if (!isFinite(bEnd)) bEnd = bStart;
      if (aEnd !== bEnd) return aEnd - bEnd;
      var aPart = parseInt(a && a._lemma_part_index, 10);
      var bPart = parseInt(b && b._lemma_part_index, 10);
      if (!isFinite(aPart)) aPart = 1e9;
      if (!isFinite(bPart)) bPart = 1e9;
      return aPart - bPart;
    });

    var isPartial = state.exact_part_count < state.total_part_count;
    var fillMode = isPartial ? "lemma_partial_greedy" : "lemma_override";
    var mergedFill = {
      mode: fillMode,
      fills: fillRows,
      has_known: false,
      has_unknown: false,
      has_lemma_override: true,
      has_lemma_promotion: false
    };
    for (var fi = 0; fi < fillRows.length; fi++) {
      var fillRow0 = fillRows[fi] || {};
      if (String(fillRow0.source || "").toUpperCase() === "UNKNOWN") mergedFill.has_unknown = true;
      else mergedFill.has_known = true;
      if (fillRow0._lemma_promoted) mergedFill.has_lemma_promotion = true;
    }
    if (gapDebug.length) {
      mergedFill.dp_debug = {
        mode: fillMode,
        exact_part_count: state.exact_part_count,
        total_part_count: state.total_part_count,
        gap_count: gapSegments.length,
        gaps: gapDebug
      };
    }

    var allEntries = collectFillEntries(mergedFill);
    if (!allEntries.length && !mergedFill.has_unknown) return null;

    var result = {
      exact_entries: [],
      fill: mergedFill,
      all_entries: allEntries.slice(),
      preferred_entries: allEntries.slice(),
      dict_head: state.surface,
      resolved_via: isPartial ? "lemma_partial_override" : "lemma_override",
      lemma_oracle_used: true,
      lemma_oracle_outcome: isPartial
        ? (gapSegments.length ? "lemma_partial_exact_gaps" : "lemma_partial_exact_only")
        : "lemma_override_exact_parts",
      exact_lemma_match_count: state.exact_part_count,
      lemma_override_parts: state.parts.map(function(part) {
        var out = {
          text: part.text,
          source_text: part.source_text,
          upos: part.upos,
          xpos: part.xpos,
          entry_refs: buildDebugEntryRefs(part.entries || [])
        };
        if (isPartial) out.matched = !!part.exact;
        return out;
      })
    };
    if (isPartial) {
      result.partial_exact_lemma_count = state.exact_part_count;
      result.partial_missing_lemma_count = state.total_part_count - state.exact_part_count;
      result.partial_gap_count = gapSegments.length;
    }
    if (includeDebugTrace && state.runtime_alignment_debug && typeof state.runtime_alignment_debug === "object") {
      var runtimeAlignmentDebug = {};
      for (var debugKey in state.runtime_alignment_debug) {
        if (!Object.prototype.hasOwnProperty.call(state.runtime_alignment_debug, debugKey)) continue;
        runtimeAlignmentDebug[debugKey] = state.runtime_alignment_debug[debugKey];
      }
      runtimeAlignmentDebug.hint_parts = state.parts.map(function(part) {
        return {
          index: parseInt(part.index, 10) || 0,
          text: String(part.text || ""),
          source_text: String(part.source_text || ""),
          upos: String(part.upos || ""),
          xpos: String(part.xpos || ""),
          exact: !!part.exact
        };
      });
      runtimeAlignmentDebug.selected_groups = state.alignment_groups.map(function(group) {
        return {
          start: parseInt(group && group.start, 10) || 0,
          end: parseInt(group && group.end, 10) || 0,
          part_ids: Array.isArray(group && group.part_ids) ? group.part_ids.slice() : []
        };
      });
      runtimeAlignmentDebug.exact_part_count = parseInt(state.exact_part_count, 10) || 0;
      runtimeAlignmentDebug.total_part_count = parseInt(state.total_part_count, 10) || 0;
      result._debug_runtime_lemma_alignment = runtimeAlignmentDebug;
    }
    return result;
  }

  // For MWT children the entire child surface is one atomic unit — the lemma
  // maps onto [0, surface.length] with no alignment needed. This skips
  // buildGenericSurfacePartAlignment (Needleman-Wunsch) entirely.
  function buildMwtChildLemmaOverrideResult(surfaceText, lemmaHintObjects, engine, upos, xpos, includeDebugTrace) {
    var surface = String(surfaceText || "").trim();
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
      alignment_groups: [{ start: 0, end: surface.length, part_ids: parts.map(function(_, idx) { return idx; }) }],
      runtime_alignment_debug: includeDebugTrace ? { match_basis: "mwt_child_direct" } : null,
      exact_part_count: exactPartCount,
      total_part_count: parts.length
    };
    return buildLemmaOverrideResultFromState(state, engine, upos, xpos, includeDebugTrace);
  }

  function buildAlignedLemmaOverrideResult(surfaceText, lemmaHintObjects, engine, upos, xpos, includeDebugTrace) {
    var state = buildLemmaHintAlignmentState(surfaceText, lemmaHintObjects, engine, includeDebugTrace);
    if (!state) return null;
    var usesExplicitMwtParts = !!(
      state.runtime_alignment_debug &&
      String(state.runtime_alignment_debug.match_basis || "").trim().toLowerCase() === "mwt_parts"
    );
    if (state.exact_part_count <= 0 && !usesExplicitMwtParts) return null;
    if (state.exact_part_count < state.total_part_count && !ENABLE_PARTIAL_EXACT_LEMMA_GAP_FILL && !usesExplicitMwtParts) return null;
    return buildLemmaOverrideResultFromState(state, engine, upos, xpos, includeDebugTrace);
  }

  function buildDirectLemmaOverrideResult(surfaceText, lemmaHintObjects, engine, upos, xpos, includeDebugTrace) {
    var state = buildDirectLemmaHintMappingState(surfaceText, lemmaHintObjects, engine, includeDebugTrace);
    if (!state) return null;
    return buildLemmaOverrideResultFromState(state, engine, upos, xpos, includeDebugTrace);
  }

  function collectFillEntries(fill) {
    var out = [];
    var rows = (fill && fill.fills) ? fill.fills : [];
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      if (String(row.source || "").toUpperCase() === "UNKNOWN") continue;
      var entries = Array.isArray(row.entries) ? row.entries : [];
      for (var j = 0; j < entries.length; j++) out.push(entries[j]);
    }
    return out;
  }

  function collectPromotedFillEntries(fill) {
    var out = [];
    var rows = (fill && fill.fills) ? fill.fills : [];
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      if (!row._lemma_promoted) continue;
      var entries = Array.isArray(row.entries) ? row.entries : [];
      for (var j = 0; j < entries.length; j++) out.push(entries[j]);
    }
    return out;
  }

  function buildLemmaHintData(surfaceText, lemmaText, engine, upos, xpos, options) {
    var hintOptions = options || {};
    var surfaceValue = String(surfaceText || "").trim();
    var lemmaValue = String(lemmaText || "").trim();
    var lang = String((engine && engine._lang_code) || getCurrentLanguage() || "").trim().toLowerCase();
    var mwtParts = Array.isArray(hintOptions.mwt_parts) ? hintOptions.mwt_parts : [];

    if (mwtParts.length > 1) {
      var mwtHintObjects = [];
      var mwtLemmaDiffersFromSurface = false;
      var mwtAborted = false;
      for (var mi = 0; mi < mwtParts.length; mi++) {
        var mwtPart = mwtParts[mi] || {};
        var mwtSurfaceText = String(mwtPart.text || "");
        var mwtLemmaText = String(mwtPart.lemma || mwtPart.text || "").trim();
        if (!mwtSurfaceText) {
          mwtAborted = true;
          break;
        }
        if (!mwtLemmaText) mwtLemmaText = mwtSurfaceText;
        var mwtLemmaEqualsSurface = normalizeVisibleComparisonText(mwtLemmaText) === normalizeVisibleComparisonText(mwtSurfaceText);
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
          upos: String(mwtPart.upos || upos || "").trim(),
          xpos: String(mwtPart.tag || mwtPart.xpos || xpos || "").trim(),
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
          lemma_hint_parts_raw: mwtHintObjects.map(function(hint) { return hint ? String(hint.text || "").trim() : ""; }),
          lemma_hint_objects: mwtHintObjects,
          hint_source: "mwt_parts",
          mwt_has_slices: true
        };
      }
    }

    var differs = !!lemmaValue && (
      normalizeVisibleComparisonText(lemmaValue) !== normalizeVisibleComparisonText(surfaceValue)
    );
    var rawParts = differs ? splitCompoundLemma(lemmaValue) : [];
    if (differs && !rawParts.length) rawParts = [lemmaValue];
    var uposParts = splitCompoundTags(upos);
    var xposParts = splitCompoundTags(xpos);
    var hasSplitUpos = uposParts.length === rawParts.length;
    var hasSplitXpos = xposParts.length === rawParts.length;
    var allowTokenLevelXposFallback = !isKoreanLanguageCode(lang);
    var hintObjects = rawParts.map(function(text, idx) {
      var hint = {
        text: text,
        upos: (hasSplitUpos ? uposParts[idx] : upos) || "",
        xpos: (hasSplitXpos ? xposParts[idx] : (allowTokenLevelXposFallback ? xpos : "")) || ""
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
      hint_source: "lemma_text"
    };
  }

  function findLemmaHintMatchForEntry(entry, lemmaHintObjects, engine) {
    if (!entry || !lemmaHintObjects || !lemmaHintObjects.length) return null;
    var morphBase = entry.morph_base != null ? String(entry.morph_base) : "";
    var headword = String(entry.lemma_headword || entry.headword || getEntryDisplayHeadword(entry) || "").trim();
    var morphBaseKey = morphBase ? normalizeLookupKey(engine, morphBase) : "";
    var headwordKey = headword ? normalizeLookupKey(engine, headword) : "";

    for (var hi = 0; hi < lemmaHintObjects.length; hi++) {
      var rawHint = lemmaHintObjects[hi];
      var hintText = "";
      if (rawHint && typeof rawHint === "object" && !Array.isArray(rawHint)) {
        if (rawHint.text != null) hintText = String(rawHint.text);
      } else if (rawHint != null) {
        hintText = String(rawHint);
      }
      if (!hintText) continue;
      var hintKey = normalizeLookupKey(engine, hintText);
      var morphMatches = morphBase
        ? ((morphBaseKey && hintKey) ? morphBaseKey === hintKey : morphBase === hintText)
        : false;
      var headwordMatches = headword
        ? ((headwordKey && hintKey) ? headwordKey === hintKey : headword === hintText)
        : false;
      if (!morphMatches && !headwordMatches) continue;
      return {
        text: hintText,
        source_text: hintText,
        upos: String((rawHint && rawHint.upos) || "").trim(),
        xpos: String((rawHint && rawHint.xpos) || "").trim()
      };
    }
    return null;
  }

  function collectEntriesMatchingLemmaHints(entries, lemmaHintObjects, engine) {
    var matches = [];
    var matchedEntries = [];
    for (var i = 0; i < (entries || []).length; i++) {
      var entry = entries[i];
      var hintMatch = findLemmaHintMatchForEntry(entry, lemmaHintObjects, engine);
      if (!hintMatch) continue;
      matchedEntries.push(entry);
      matches.push({ entry: entry, hint: hintMatch });
    }
    return {
      entries: matchedEntries,
      matches: matches
    };
  }

  function isLemmaOverrideResolvedPath(resolvedVia) {
    var path = String(resolvedVia || "").trim().toLowerCase();
    return path === "lemma_override" || path === "lemma_partial_override";
  }

  function shouldApplyStrictExactLemmaDisplayFilter(resolvedVia, exactLemmaMatchCount, preferredEntries) {
    if (isLemmaOverrideResolvedPath(resolvedVia)) return false;
    if (String(resolvedVia || "").trim().toLowerCase() === "lemma_promoted") {
      return Array.isArray(preferredEntries) && preferredEntries.length > 0;
    }
    var matchCount = parseInt(exactLemmaMatchCount, 10);
    if (!isFinite(matchCount) || matchCount <= 0) return false;
    return Array.isArray(preferredEntries) && preferredEntries.length > 0;
  }

  function collectStrictLemmaEntriesForPromotedFillRow(entries, row, engine) {
    var fillEntries = Array.isArray(entries) ? entries : [];
    var fillRow = (row && typeof row === "object") ? row : null;
    if (!fillEntries.length || !fillRow) return [];
    if (fillRow._lemma_override || fillRow.lemma_override) return [];
    if (fillRow._lemma_promoted == null || fillRow._lemma_promoted === "") return [];
    var matchInfo = collectEntriesMatchingLemmaHints(fillEntries, [{
      text: String(fillRow._lemma_promoted),
      upos: String(fillRow._lemma_upos_hint || "").trim(),
      xpos: String(fillRow._lemma_xpos_hint || "").trim()
    }], engine);
    return Array.isArray(matchInfo.entries) ? matchInfo.entries.slice() : [];
  }

  function isWholeSurfaceKnownFill(fill, surfaceText) {
    if (!fill || !fill.has_known || fill.has_unknown) return false;
    var rows = Array.isArray(fill.fills) ? fill.fills : [];
    if (rows.length !== 1) return false;
    var row = rows[0] || {};
    if (String(row.source || "").toUpperCase() === "UNKNOWN") return false;
    return String(row.text || row.head || "").trim() === String(surfaceText || "").trim();
  }

  function annotateSingleFillLemmaPromotion(fill, matchRecord, mode, fallbackUpos, fallbackXpos) {
    if (!fill || !Array.isArray(fill.fills) || !fill.fills.length || !matchRecord) return fill;
    var row = fill.fills[0] || {};
    var entry = matchRecord.entry || {};
    var hint = matchRecord.hint || {};
    var lemmaText = String(hint.text || "").trim();
    if (!lemmaText) return fill;
    row._lemma_promoted = lemmaText;
    row._lemma_promoted_headword = String(entry.headword || "");
    row._lemma_promoted_pos = String(entry.pos_raw || entry.pos || "");
    var uposHint = String(hint.upos || fallbackUpos || "").trim();
    var xposHint = String(hint.xpos || fallbackXpos || "").trim();
    if (uposHint) row._lemma_upos_hint = uposHint;
    if (xposHint) row._lemma_xpos_hint = xposHint;
    fill.has_lemma_promotion = true;
    if (mode) fill.mode = String(mode);
    return fill;
  }


  function isMwtUdToken(tok) {
    return !!(
      tok &&
      typeof tok === "object" &&
      Array.isArray(tok.mwt_parts) &&
      tok.mwt_parts.length > 1
    );
  }

  // Unicode categories that are "junk" — direct copy of gemini_dict.py _GLOSS_SKIP_CATEGORIES.
  // If every character in a token falls into one of these categories the token has no lexical
  // content and there is nothing to look up in the dictionary.
  var _PUNCT_SKIP_CATEGORIES = (function() {
    var s = Object.create(null);
    var cats = [
      "Mn", "Mc", "Me",                          // Mark
      "Nd", "Nl", "No",                          // Number
      "Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po", // Punctuation
      "Sm", "Sc", "Sk", "So",                    // Symbol
      "Zs", "Zl", "Zp",                          // Separator
      "Cc", "Cf", "Cs", "Co", "Cn"               // Other / Control
    ];
    for (var i = 0; i < cats.length; i++) s[cats[i]] = true;
    return s;
  }());

  // Mirror of gemini_dict.py _is_glossable_token(): returns true if the string contains
  // at least one character whose Unicode general category is NOT in _PUNCT_SKIP_CATEGORIES.
  // Uses Intl.getCanonicalLocales-independent approach: iterate codepoints.
  // We leverage the ES2018 Unicode property escape \p{L}\p{M} to detect letter/mark chars;
  // if unavailable we fall back to checking each char via a regex built from the skip-set.
  var _hasLexicalContent = (function() {
    // Try fast path: \p{L} (any letter) — covers Lu Ll Lt Lm Lo, i.e. every category
    // absent from _PUNCT_SKIP_CATEGORIES that carries lexical value.
    try {
      var _lexRe = new RegExp("[\\p{L}\\p{M}]", "u");
      return function(str) { return str ? _lexRe.test(str) : false; };
    } catch (e) {
      // Fallback: iterate code-points and check each character's general category
      // using a two-char prefix lookup against the skip set.
      return function(str) {
        if (!str) return false;
        for (var i = 0; i < str.length; i++) {
          var cp = str.codePointAt(i);
          if (cp > 0xffff) i++; // surrogate pair — advance extra
          // We cannot get the Unicode category in plain ES5, so conservatively
          // assume any non-ASCII or ASCII letter has content.
          var ch = str[i];
          // ASCII printable non-symbol range: 0x41-0x5A (A-Z) 0x61-0x7A (a-z)
          var code = ch.charCodeAt(0);
          if ((code >= 0x41 && code <= 0x5A) || (code >= 0x61 && code <= 0x7A)) return true;
          // Non-ASCII: assume it has content (safe — we only skip on confirmed junk)
          if (code > 0x7E) return true;
        }
        return false;
      };
    }
  }());

  function buildSinglePassSurfaceLookup(surfaceText, lemmaText, engine, upos, xpos, includeDebugTrace, options) {
    var surface = String(surfaceText || "").trim();
    var lookupOpts = options || {};

    // Fast-path: purely punctuation / symbols / control chars — skip dictionary entirely.
    if (surface && !_hasLexicalContent(surface)) {
      return {
        exact_entries: [],
        fill: null,
        all_entries: [],
        preferred_entries: [],
        dict_head: surface,
        resolved_via: "surface",
        lemma_hint_data: { lemma_hint_objects: [], lemma_differs_from_surface: false },
        lemma_oracle_used: false,
        lemma_oracle_outcome: "punct_skip",
        exact_lemma_match_count: 0,
        resolution_meta: buildResolutionMeta(
          "",
          "punct_skip",
          [buildResolutionRouteStep("punct_skip", "token is purely punctuation/symbols — skipped dictionary lookup")],
          "surface",
          "unknown",
          false,
          "punct_skip"
        )
      };
    }
    var skipWholeSurfaceExact = !!lookupOpts.skipWholeSurfaceExact;
    var mwtParts = Array.isArray(lookupOpts.mwt_parts) ? lookupOpts.mwt_parts : [];
    var isMwtToken = mwtParts.length > 1;
    var hintData = buildLemmaHintData(surface, lemmaText, engine, upos || "", xpos || "", lookupOpts);
    var lemmaHints = hintData.lemma_hint_objects;
    var lemmaOracleUsed = hintData.lemma_differs_from_surface && lemmaHints.length > 0;
    var koreanCompoundLemmaChildren = [];
    var skipKoreanCompoundLemmaRealignment = false;
    // For MWT tokens we must route through the slice-based direct mapping
    // regardless of whether any lemma differs from its child surface, because
    // Trankit offsets are the only authoritative source of child boundaries.
    var surfaceExactMissMessage = skipWholeSurfaceExact
      ? "whole-token exact lookup skipped for MWT part-first mode"
      : "surface exact lookup missed";
    var exactEntries = [];
    var surfaceExactEntries = [];
    var lemmaExactEntries = [];
    var exactMatchInfo = { entries: [], matches: [] };
    var exactPreferredEntries = [];
    var fill = null;
    if (!skipWholeSurfaceExact && engine && typeof engine.lookup_all === "function") {
      surfaceExactEntries = dedupeEntriesByIdentity(engine.lookup_all(surface) || [], surface);
      if (lemmaOracleUsed) {
        lemmaExactEntries = collectWholeTokenExactLemmaEntries(surface, lemmaHints, engine);
      }
      exactEntries = dedupeEntriesByIdentity(surfaceExactEntries.concat(lemmaExactEntries), surface);
      if (lemmaOracleUsed && exactEntries.length) {
        exactMatchInfo = collectEntriesMatchingLemmaHints(exactEntries, lemmaHints, engine);
      }
      exactPreferredEntries = exactMatchInfo.entries.length ? exactMatchInfo.entries.slice() : exactEntries.slice();
    }
    var routeSteps = [];
    var routeCode = "";
    var routeCategory = "";
    var outcome = "";

    if (exactEntries.length) {
      var exactLookupMatchedText = "whole-token exact candidate pool matched";
      if (surfaceExactEntries.length && !lemmaExactEntries.length) exactLookupMatchedText = "surface exact lookup matched";
      else if (!surfaceExactEntries.length && lemmaExactEntries.length) exactLookupMatchedText = "lemma exact lookup matched";
      else if (surfaceExactEntries.length && lemmaExactEntries.length) exactLookupMatchedText = "surface and lemma exact lookup matched";
      var exactMode = lemmaOracleUsed ? "exact_lemma_checked" : "exact";
      var exactResult = buildFillResult(surface, exactEntries, exactMode);
      var exactFill = exactResult.fill || {};
      var exactOutcome = lemmaOracleUsed ? "exact_kept_after_lemma_check" : "surface_exact";
      var exactFillMode = String((exactFill && exactFill.mode) || exactMode).trim().toLowerCase();

      if (lemmaOracleUsed && exactMatchInfo.matches.length) {
        annotateSingleFillLemmaPromotion(exactFill, exactMatchInfo.matches[0], "exact_lemma_promoted", upos, xpos);
        exactOutcome = "exact_kept_with_lemma_promotion";
        exactFillMode = String((exactFill && exactFill.mode) || "exact_lemma_promoted").trim().toLowerCase();
        return {
          exact_entries: exactEntries.slice(),
          fill: exactFill,
          all_entries: exactEntries.slice(),
          preferred_entries: exactPreferredEntries.slice(),
          dict_head: surface,
          resolved_via: "surface",
          lemma_hint_data: hintData,
          lemma_oracle_used: true,
          lemma_oracle_outcome: exactOutcome,
          exact_lemma_match_count: exactMatchInfo.entries.length,
          resolution_meta: buildResolutionMeta(
            "exact_lemma_match",
            "surface_exact_lemma_match",
            [
              buildResolutionRouteStep("surface_exact_lookup", exactLookupMatchedText),
              buildResolutionRouteStep("lemma_check", "lemma check found an underlying lemma match")
            ],
            "surface",
            exactFillMode,
            true,
            exactOutcome
          )
        };
      }

      var exactRouteSteps = [
        buildResolutionRouteStep("surface_exact_lookup", exactLookupMatchedText)
      ];
      if (lemmaOracleUsed) {
        exactRouteSteps.push(
          buildResolutionRouteStep("lemma_check", "lemma check kept the surface exact result")
        );
      }
      return {
        exact_entries: exactEntries.slice(),
        fill: exactFill,
        all_entries: exactEntries.slice(),
        preferred_entries: exactPreferredEntries.slice(),
        dict_head: surface,
        resolved_via: "surface",
        lemma_hint_data: hintData,
        lemma_oracle_used: lemmaOracleUsed,
        lemma_oracle_outcome: exactOutcome,
        exact_lemma_match_count: exactMatchInfo.entries.length,
        resolution_meta: buildResolutionMeta(
          "exact_match",
          lemmaOracleUsed ? "surface_exact_lemma_checked" : "surface_exact",
          exactRouteSteps,
          "surface",
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
      var childLemmaOverrideCount = 0;    // children resolved via lemma override
      var childExactCount = 0;            // children resolved via surface exact
      var childGreedyCount = 0;           // children resolved via greedy
      var childResolutions = [];          // per-child resolution category, in order
      for (var cpi = 0; cpi < mwtParts.length; cpi++) {
        var childPart = mwtParts[cpi] || {};
        var childSurfaceText = String(childPart.text || "");
        var childSliceArr = Array.isArray(childPart.surface_slice) ? childPart.surface_slice : null;
        if (!childSurfaceText || !childSliceArr || childSliceArr.length < 2) {
          childResultsOk = false; break;
        }
        var childSliceStart = parseInt(childSliceArr[0], 10);
        var childSliceEnd = parseInt(childSliceArr[1], 10);
        if (!isFinite(childSliceStart) || !isFinite(childSliceEnd)) {
          childResultsOk = false; break;
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
            if (!isFinite(_cmv)) { _cmOk = false; break; }
            childCharMap[_cmi] = _cmv;
          }
          if (!_cmOk) childCharMap = null;
        }
        var childLemmaText = String(childPart.lemma || childPart.text || "");
        var childUpos = String(childPart.upos || "");
        var childXpos = String(childPart.tag || childPart.xpos || "");
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
        if (!childResult) { childResultsOk = false; break; }
        // Tally per-child category to derive the aggregate resolution label.
        var childCat = String((childResult.resolution_meta && childResult.resolution_meta.category) || "").toLowerCase();
        // For MWT children, disallow lemma_partial_override. Partial lemma matching only applies
        // to parent surface lookups. Children always have complete segmentation boundaries,
        // so partial lemma override becomes greedy (gaps filled greedily).
        if (childCat === "lemma_partial_override") childCat = "greedy_match";
        if (childCat === "exact_match" || childCat === "exact_lemma_match") childExactCount++;
        else if (childCat === "lemma_override") childLemmaOverrideCount++;
        else childGreedyCount++;
        childResolutions.push(childCat || "greedy_match");
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
        var childFillRows = (childFillObj && Array.isArray(childFillObj.fills)) ? childFillObj.fills : [];
        var childPreferredEntries = Array.isArray(childResult.preferred_entries) ? childResult.preferred_entries : [];
        var isGreedyChild = (
          childCat !== "exact_match" &&
          childCat !== "exact_lemma_match" &&
          childCat !== "lemma_override" &&
          childCat !== "lemma_partial_override"
        );

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
            bundledRow = { text: childSurfaceSlice, head: childSurfaceSlice, roman: "", senses: [], pos: "", source: "UNKNOWN", entries: [] };
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
            bundledRow = { text: childSurfaceSlice, head: childSurfaceSlice, roman: "", senses: [], pos: "", source: "UNKNOWN", entries: [] };
            mergedHasUnknown = true;
          }
          // Propagate lemma-override flag so the golden border renders correctly.
          if (childCat === "lemma_override" || childCat === "lemma_partial_override") {
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
        for (var cpei = 0; cpei < childPreferred.length; cpei++) mergedPreferredEntries.push(childPreferred[cpei]);
      }
      if (childResultsOk && mergedChildFills.length) {
        var totalChildren = mwtParts.length;
        // Derive a standard category from what the children actually resolved to.
        // Each child resolves independently, so the parent label reflects the mix.
        var mergedCategory;
        if (childExactCount === totalChildren) {
          mergedCategory = "exact_match";
        } else if (childLemmaOverrideCount === totalChildren) {
          mergedCategory = "lemma_override";
        } else if (childLemmaOverrideCount > 0 || mergedHasLemmaPromotion) {
          mergedCategory = "lemma_partial_override";
        } else {
          mergedCategory = "greedy_match";
        }
        var mergedFillObj = {
          mode: mergedHasLemmaPromotion ? "mwt_lemma_promoted" : "mwt_child",
          fills: mergedChildFills,
          has_known: mergedHasKnown,
          has_unknown: mergedHasUnknown,
          has_lemma_promotion: mergedHasLemmaPromotion
        };
        var mergedResolvedVia = (childLemmaOverrideCount > 0 || mergedHasLemmaPromotion) ? "lemma_promoted" : "surface";
        var mergedOutcome = mergedCategory;
        var routeDetail = "exact:" + childExactCount + " lemma:" + childLemmaOverrideCount + " greedy:" + childGreedyCount;
        return {
          exact_entries: [],
          fill: mergedFillObj,
          all_entries: mergedAllEntries.slice(),
          preferred_entries: (mergedPreferredEntries.length ? mergedPreferredEntries : mergedAllEntries).slice(),
          dict_head: surface,
          resolved_via: mergedResolvedVia,
          lemma_hint_data: hintData,
          lemma_oracle_used: childLemmaOverrideCount > 0 || mergedHasLemmaPromotion || lemmaOracleUsed,
          lemma_oracle_outcome: mergedOutcome,
          exact_lemma_match_count: childLemmaOverrideCount,
          mwt_child_resolutions: childResolutions.slice(),
          resolution_meta: buildResolutionMeta(
            mergedCategory,
            "mwt_children_resolved_independently",
            [
              buildResolutionRouteStep("surface_exact_lookup", surfaceExactMissMessage),
              buildResolutionRouteStep("mwt_children_independent", "MWT children resolved independently (" + routeDetail + ")")
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
      var useDirectMwtLemmaMapping = String((hintData && hintData.hint_source) || "").trim().toLowerCase() === "mwt_parts";
      var isMwtSingleChild = !!lookupOpts.mwt_single_child;
      skipKoreanCompoundLemmaRealignment = shouldBypassKoreanCompoundLemmaRealignment(surface, lemmaHints, engine, lookupOpts);
      if (skipKoreanCompoundLemmaRealignment) {
        koreanCompoundLemmaChildren = buildKoreanCompoundLemmaChildLookupPayloads(lemmaHints, engine, includeDebugTrace);
        if (!koreanCompoundLemmaChildren.length) skipKoreanCompoundLemmaRealignment = false;
      }
      if (!skipKoreanCompoundLemmaRealignment) {
        var alignedLemmaPartsResult = useDirectMwtLemmaMapping
          ? buildDirectLemmaOverrideResult(
              surface,
              lemmaHints,
              engine,
              upos,
              xpos,
              includeDebugTrace
            )
          : (isMwtSingleChild
            ? buildMwtChildLemmaOverrideResult(
                surface,
                lemmaHints,
                engine,
                upos,
                xpos,
                includeDebugTrace
              )
            : buildAlignedLemmaOverrideResult(
                surface,
                lemmaHints,
                engine,
                upos,
                xpos,
                includeDebugTrace
              ));
        var lemmaExactPartsStepText = useDirectMwtLemmaMapping
          ? "lemma parts were mapped back to their Trankit MWT surface slices"
          : (isMwtSingleChild ? "MWT child lemma mapped directly onto child surface" : "exact lemma parts were aligned onto the surface");
        var lemmaGapResolvedStepText = useDirectMwtLemmaMapping
          ? "no uncovered spans remained after direct MWT slice mapping"
          : (isMwtSingleChild ? "MWT child lemma covered the entire child surface" : "no uncovered spans remained after exact lemma-part alignment");
        var lemmaOverrideStepText = useDirectMwtLemmaMapping
          ? "lemma exact-part mapping selected"
          : "lemma exact-part alignment selected";
        if (alignedLemmaPartsResult) {
          var partialGapCount = Number(alignedLemmaPartsResult.partial_gap_count || 0);
          var partialExactCount = Number(alignedLemmaPartsResult.partial_exact_lemma_count || 0);
          var partialMissingCount = Number(alignedLemmaPartsResult.partial_missing_lemma_count || 0);
          var alignedResolvedVia = String(alignedLemmaPartsResult.resolved_via || "").trim().toLowerCase();
          alignedLemmaPartsResult.lemma_hint_data = hintData;
          if (alignedResolvedVia === "lemma_partial_override") {
            alignedLemmaPartsResult.resolution_meta = buildResolutionMeta(
              useDirectMwtLemmaMapping ? "mwt_lemma_partial_override" : "lemma_partial_override",
              useDirectMwtLemmaMapping
                ? "surface_no_match_then_mwt_partial_lemma_exact_then_gap_greedy"
                : "surface_no_match_then_partial_lemma_exact_then_gap_greedy",
              partialGapCount > 0
                ? [
                    buildResolutionRouteStep("surface_exact_lookup", surfaceExactMissMessage),
                    buildResolutionRouteStep("lemma_exact_parts", lemmaExactPartsStepText),
                    buildResolutionRouteStep("lemma_gap_greedy", "greedy DP filled the remaining uncovered spans")
                  ]
                : [
                    buildResolutionRouteStep("surface_exact_lookup", surfaceExactMissMessage),
                    buildResolutionRouteStep("lemma_exact_parts", lemmaExactPartsStepText),
                    buildResolutionRouteStep("lemma_gap_greedy", lemmaGapResolvedStepText)
                  ],
              "lemma_partial_override",
              String((alignedLemmaPartsResult.fill && alignedLemmaPartsResult.fill.mode) || "lemma_partial_greedy").trim().toLowerCase(),
              true,
              String(alignedLemmaPartsResult.lemma_oracle_outcome || (partialGapCount > 0 ? "lemma_partial_exact_gaps" : "lemma_partial_exact_only")).trim().toLowerCase(),
              {
                partial_exact_lemma_count: partialExactCount,
                partial_missing_lemma_count: partialMissingCount,
                partial_gap_count: partialGapCount,
                is_mwt: useDirectMwtLemmaMapping
              }
            );
          } else {
            alignedLemmaPartsResult.resolution_meta = buildResolutionMeta(
              useDirectMwtLemmaMapping ? "mwt_lemma_override" : "lemma_override",
              useDirectMwtLemmaMapping
                ? "surface_no_match_then_mwt_lemma_exact_parts"
                : "surface_no_match_then_lemma_exact_parts",
              [
                buildResolutionRouteStep("surface_exact_lookup", surfaceExactMissMessage),
                buildResolutionRouteStep("lemma_exact_parts", "all lemma parts resolved by exact lookup"),
                buildResolutionRouteStep("lemma_override", lemmaOverrideStepText)
              ],
              "lemma_override",
              String((alignedLemmaPartsResult.fill && alignedLemmaPartsResult.fill.mode) || "lemma_override").trim().toLowerCase(),
              true,
              "lemma_override_exact_parts",
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
        resolved_via: "surface",
        lemma_hint_data: hintData,
        lemma_oracle_used: lemmaOracleUsed,
        lemma_oracle_outcome: "mwt_children_failed",
        exact_lemma_match_count: 0,
        resolution_meta: buildResolutionMeta(
          "no_match",
          "mwt_children_failed",
          [buildResolutionRouteStep("mwt_children_independent", "per-child segmentation failed; refusing whole-surface greedy on MWT parent")],
          "surface",
          "none",
          lemmaOracleUsed,
          "mwt_children_failed"
        )
      };
    }

    var greedyFillOpts = {
      allowExact: false,
      excludeWhole: false,
      upos: upos || ""
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
    var fillMode = String((fill && fill.mode) || "greedy").trim().toLowerCase();
    var resolvedVia = (fill && fill.has_lemma_promotion) ? "lemma_promoted" : "surface";
    routeSteps = [];
    routeCode = "";
    routeCategory = "";
    outcome = "";

    if (skipKoreanCompoundLemmaRealignment && koreanCompoundLemmaChildren.length) {
      routeCategory = "korean_compound_lemma_popup";
      routeCode = "surface_no_match_then_korean_compound_lemma_popup";
      routeSteps.push(buildResolutionRouteStep("surface_exact_lookup", surfaceExactMissMessage));
      routeSteps.push(buildResolutionRouteStep("korean_compound_lemma_popup", "compound lemma children precomputed; parent surface kept as a single popup anchor"));
      outcome = "korean_compound_lemma_popup";
    } else if (allEntries.length) {
      routeCategory = (fill && fill.has_lemma_promotion) ? "lemma_promotion" : "greedy_match";
      routeCode = (fill && fill.has_lemma_promotion) ? "surface_greedy_lemma_promoted" : "surface_greedy";
      routeSteps.push(buildResolutionRouteStep("surface_exact_lookup", surfaceExactMissMessage));
      routeSteps.push(buildResolutionRouteStep("surface_greedy", "single-pass greedy DP selected the final fills"));
      if (fill && fill.has_lemma_promotion) {
        routeSteps.push(buildResolutionRouteStep("lemma_promotion", "lemma-aware scoring promoted one or more chosen fills"));
      }
      outcome = (fill && fill.has_lemma_promotion) ? "lemma_promoted" : "surface_greedy";
    } else {
      routeCode = lemmaOracleUsed ? "surface_no_match_after_lemma_check" : "surface_no_match";
      routeSteps.push(buildResolutionRouteStep("surface_exact_lookup", surfaceExactMissMessage));
      routeSteps.push(buildResolutionRouteStep("surface_greedy", "single-pass greedy DP found no known dictionary path"));
      outcome = lemmaOracleUsed ? "no_lemma_match" : "no_match";
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

  function buildWinnerRefWireKey(ref) {
    if (!ref || !ref._winner_ref) return "";
    var alias = String(ref.db_alias || "").trim();
    var entryId = parseInt(ref.entry_row_id, 10) || 0;
    if (!alias || !(entryId > 0)) return "";
    var sk = String(ref.storage_kind || "sqlite").trim().toLowerCase() || "sqlite";
    var formId = parseInt(ref.form_row_id, 10) || 0;
    if (formId > 0) return sk + "|" + alias + "|" + entryId + "|" + formId;
    return sk + "|" + alias + "|" + entryId;
  }

  function hydrateLookupEntry(entry, entryStore, refToKey, formOverlays) {
    if (!entry || typeof entry !== "object") return null;
    var wireKey = buildWinnerRefWireKey(entry);
    if (wireKey) {
      var storeKey = refToKey ? refToKey[wireKey] : "";
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
        if (ov.match_kind) cloned.match_kind = String(ov.match_kind || "").trim().toLowerCase();
        if (ov._match_kind) cloned._match_kind = String(ov._match_kind || "").trim().toLowerCase();
        else if (cloned.match_kind) cloned._match_kind = cloned.match_kind;
        if (ov._match_source) cloned._match_source = String(ov._match_source || "").trim().toLowerCase();
        else if (cloned._match_kind) cloned._match_source = cloned._match_kind;
        if (ov.morph_info) {
          var cleanedOverlayMorphInfo = ov.morph_info.map(function(value) {
            return cleanMorphDisplayTags(value);
          }).filter(Boolean);
          if (cleanedOverlayMorphInfo.length) cloned.morph_info = cleanedOverlayMorphInfo;
          else if (Object.prototype.hasOwnProperty.call(cloned, "morph_info")) delete cloned.morph_info;
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

  function markNormalizedMatch(entry, surfaceText) {
    if (!entry || typeof entry !== "object") return entry;
    var surface = String(surfaceText || "").trim();
    if (!surface) {
      if (Object.prototype.hasOwnProperty.call(entry, "normalized_match")) delete entry.normalized_match;
      return entry;
    }
    var head = String(getEntryDisplayHeadword(entry) || entry.headword || entry.display_headword || entry.surface_form || entry.head || "").trim();
    if (head && head !== surface) entry.normalized_match = true;
    else if (Object.prototype.hasOwnProperty.call(entry, "normalized_match")) delete entry.normalized_match;
    return entry;
  }

  function applyLemmaSurfaceDisplayFlip(entries, surfaceText) {
    var list = Array.isArray(entries) ? entries : [];
    var surface = String(surfaceText || "").trim();
    if (!surface) return list;
    var surfaceNorm = normalizeVisibleComparisonText(surface);
    for (var i = 0; i < list.length; i++) {
      var entry = list[i];
      if (!entry || typeof entry !== "object") continue;
      var baseHead = String(entry.display_headword || entry.headword || "").trim();
      var baseNorm = normalizeVisibleComparisonText(baseHead);
      if (baseHead && surfaceNorm !== baseNorm) {
        entry.display_headword = surface;
        entry.headword = surface;
        entry.surface_form = surface;
        entry.head = surface;
        if (!entry.morph_base) entry.morph_base = baseHead;
        if (!entry.lemma_headword) entry.lemma_headword = baseHead;
        if (Object.prototype.hasOwnProperty.call(entry, "normalized_match")) delete entry.normalized_match;
      } else {
        if (!entry.surface_form) entry.surface_form = surface;
        if (!entry.head) entry.head = surface;
      }
    }
    return list;
  }

  function hydrateLookupEntries(entries, entryStore, refToKey, surfaceText, formOverlays) {
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

  function hydrateLookupFill(fill, entryStore, refToKey, engine, formOverlays) {
    var src = (fill && typeof fill === "object") ? fill : {};
    var out = {};
    for (var key in src) {
      if (Object.prototype.hasOwnProperty.call(src, key) && key !== "fills") out[key] = src[key];
    }
    var rows = Array.isArray(src.fills) ? src.fills : [];
    out.fills = [];
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      if (!row || typeof row !== "object") {
        out.fills.push(row);
        continue;
      }
      var clone = {};
      for (var rowKey in row) {
        if (Object.prototype.hasOwnProperty.call(row, rowKey)) clone[rowKey] = row[rowKey];
      }
      var fillSurface = String(row.head || row.text || "").trim();
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
        clone._mwt_child_text || clone.text || clone.head || fillSurface || ""
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
        var chosen = chooseEntry(String(clone.head || clone.text || ""), hydratedEntries, engine);
        if (chosen) applyFillRepresentativeEntry(clone, chosen, false);
      }

      // Also hydrate MWT child piece rows if present
      if (Array.isArray(clone._mwt_child_piece_rows) && clone._mwt_child_piece_rows.length) {
        var hydratedPieceRows = [];
        for (var pi = 0; pi < clone._mwt_child_piece_rows.length; pi++) {
          var pieceRow = clone._mwt_child_piece_rows[pi];
          if (!pieceRow || typeof pieceRow !== "object") {
            hydratedPieceRows.push(pieceRow);
            continue;
          }
          var pieceClone = {};
          for (var pieceKey in pieceRow) {
            if (Object.prototype.hasOwnProperty.call(pieceRow, pieceKey)) pieceClone[pieceKey] = pieceRow[pieceKey];
          }
          var pieceSurface = String(pieceRow.head || pieceRow.text || "").trim();
          var hydratedPieceEntries = hydrateLookupEntries(pieceRow.entries, entryStore, refToKey, pieceSurface, formOverlays);
          if (!hydratedPieceEntries.length && pieceRow._winner_ref) {
            var singlePieceHydrated = hydrateLookupEntry(pieceRow._winner_ref, entryStore, refToKey, formOverlays);
            if (singlePieceHydrated) hydratedPieceEntries = [markNormalizedMatch(singlePieceHydrated, pieceSurface)];
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

  function getHydratedLemmaHintObjectsForFillRow(row, lemmaHintObjects) {
    var hints = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
    if (!hints.length) return [];
    var partIndex = parseInt((row && row._mwt_part_index), 10);
    if (!isFinite(partIndex)) partIndex = parseInt((row && row._lemma_part_index), 10);
    if (isFinite(partIndex) && partIndex >= 0 && partIndex < hints.length) {
      return [hints[partIndex]];
    }
    return hints.slice();
  }

  function recomputeHydratedLemmaMatchMetadata(surfaceLookup, engine) {
    var out = (surfaceLookup && typeof surfaceLookup === "object") ? surfaceLookup : null;
    if (!out) return out;
    var hintObjects = (
      out.lemma_hint_data &&
      Array.isArray(out.lemma_hint_data.lemma_hint_objects)
    ) ? out.lemma_hint_data.lemma_hint_objects : [];
    if (!hintObjects.length) return out;

    var meta = (out.resolution_meta && typeof out.resolution_meta === "object")
      ? out.resolution_meta
      : null;
    var category = String((meta && meta.category) || "").trim().toLowerCase();
    var resolvedVia = String(out.resolved_via || (meta && meta.resolved_via) || "surface").trim().toLowerCase() || "surface";
    var fillMode = String(((out.fill && out.fill.mode) || (meta && meta.fill_mode) || "")).trim().toLowerCase();
    var dictHead = String(out.dict_head || "").trim();

    if (Array.isArray(out.exact_entries) && out.exact_entries.length) {
      var exactMatchInfo = collectEntriesMatchingLemmaHints(out.exact_entries, hintObjects, engine);
      out.exact_lemma_match_count = exactMatchInfo.entries.length;
      if (exactMatchInfo.entries.length) {
        out.preferred_entries = exactMatchInfo.entries.slice();
        out.lemma_oracle_used = true;
        if (category === "exact_match" || category === "exact_lemma_match") {
          annotateSingleFillLemmaPromotion(out.fill, exactMatchInfo.matches[0], "exact_lemma_promoted", "", "");
          out.lemma_oracle_outcome = "exact_kept_with_lemma_promotion";
          out.resolution_meta = buildResolutionMeta(
            "exact_lemma_match",
            "surface_exact_lemma_match",
            [
              buildResolutionRouteStep("surface_exact_lookup", "surface exact lookup matched"),
              buildResolutionRouteStep("lemma_check", "lemma check found an underlying lemma match")
            ],
            resolvedVia || "surface",
            String(((out.fill && out.fill.mode) || fillMode || "exact_lemma_promoted")).trim().toLowerCase(),
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
      category === "mwt_exact_parts" ||
      category === "mwt_exact_partial_lemma_match" ||
      category === "mwt_exact_lemma_match"
    ) {
      var rows = (out.fill && Array.isArray(out.fill.fills)) ? out.fill.fills : [];
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
          { fills: [row], has_known: true, has_unknown: false },
          rowMatchInfo.matches[0],
          "mwt_exact_lemma_promoted",
          String(row._lemma_upos_hint || ""),
          String(row._lemma_xpos_hint || "")
        );
        matchedCount += 1;
        for (var mei = 0; mei < rowMatchInfo.entries.length; mei++) matchedEntries.push(rowMatchInfo.entries[mei]);
      }
      out.exact_lemma_match_count = matchedCount;
      if (out.fill && typeof out.fill === "object") {
        out.fill.has_lemma_promotion = matchedCount > 0;
      }
      if (matchedCount >= rows.length && matchedEntries.length) {
        out.preferred_entries = dedupeEntriesByIdentity(matchedEntries, dictHead);
        out.lemma_oracle_used = true;
        out.lemma_oracle_outcome = "mwt_exact_parts_lemma_match";
        out.resolution_meta = buildResolutionMeta(
          "mwt_exact_lemma_match",
          "surface_no_match_then_mwt_exact_lemma_match",
          [
            buildResolutionRouteStep("surface_exact_lookup", "whole-token exact lookup skipped for MWT part-first mode"),
            buildResolutionRouteStep("mwt_exact_parts", "Trankit MWT subword surface forms matched by exact lookup"),
            buildResolutionRouteStep("lemma_check", "lemma check found an underlying MWT exact-part match")
          ],
          resolvedVia || "surface",
          String(((out.fill && out.fill.mode) || fillMode || "mwt_exact")).trim().toLowerCase(),
          true,
          out.lemma_oracle_outcome
        );
      } else if (matchedCount > 0 && matchedEntries.length) {
        out.preferred_entries = dedupeEntriesByIdentity(matchedEntries, dictHead);
        out.lemma_oracle_used = true;
        out.lemma_oracle_outcome = "mwt_exact_parts_partial_lemma_match";
        out.resolution_meta = buildResolutionMeta(
          "mwt_exact_partial_lemma_match",
          "surface_no_match_then_mwt_exact_partial_lemma_match",
          [
            buildResolutionRouteStep("surface_exact_lookup", "whole-token exact lookup skipped for MWT part-first mode"),
            buildResolutionRouteStep("mwt_exact_parts", "Trankit MWT subword surface forms matched by exact lookup"),
            buildResolutionRouteStep("lemma_check", "lemma check matched some but not all MWT exact parts")
          ],
          resolvedVia || "surface",
          String(((out.fill && out.fill.mode) || fillMode || "mwt_exact")).trim().toLowerCase(),
          true,
          out.lemma_oracle_outcome
        );
      } else if (
        category === "mwt_exact_lemma_match" ||
        category === "mwt_exact_partial_lemma_match"
      ) {
        out.resolution_meta = buildResolutionMeta(
          "mwt_exact_parts",
          "surface_no_match_then_mwt_exact_parts",
          [
            buildResolutionRouteStep("surface_exact_lookup", "whole-token exact lookup skipped for MWT part-first mode"),
            buildResolutionRouteStep("mwt_exact_parts", "Trankit MWT subword surface forms matched by exact lookup")
          ],
          resolvedVia || "surface",
          String(((out.fill && out.fill.mode) || fillMode || "mwt_exact")).trim().toLowerCase(),
          !!out.lemma_oracle_used,
          "mwt_exact_parts"
        );
        out.lemma_oracle_outcome = "mwt_exact_parts";
      } else if (!out.lemma_oracle_outcome) {
        out.lemma_oracle_outcome = "mwt_exact_parts";
      }
    }

    return out;
  }

  function hydrateKoreanCompoundLemmaChildLookups(children, entryStore, refToKey, engine, formOverlays) {
    var list = Array.isArray(children) ? children : [];
    var out = [];
    for (var i = 0; i < list.length; i++) {
      var child = (list[i] && typeof list[i] === "object") ? list[i] : null;
      if (!child) continue;
      var clone = {};
      for (var key in child) {
        if (!Object.prototype.hasOwnProperty.call(child, key) || key === "lookup") continue;
        clone[key] = child[key];
      }
      clone.lookup = hydrateSinglePassLookup(child.lookup, entryStore, refToKey, engine, formOverlays);
      out.push(clone);
    }
    return out;
  }

  function hydrateSinglePassLookup(surfaceLookup, entryStore, refToKey, engine, formOverlays) {
    var src = (surfaceLookup && typeof surfaceLookup === "object") ? surfaceLookup : {};
    var out = {};
    for (var key in src) {
      if (Object.prototype.hasOwnProperty.call(src, key) && key !== "fill" && key !== "exact_entries" && key !== "all_entries" && key !== "preferred_entries") {
        out[key] = src[key];
      }
    }
    var dictHead = String(src.dict_head || "").trim();
    out.fill = hydrateLookupFill(src.fill, entryStore, refToKey, engine, formOverlays);
    out.exact_entries = hydrateLookupEntries(src.exact_entries, entryStore, refToKey, dictHead, formOverlays);
    out.all_entries = hydrateLookupEntries(src.all_entries, entryStore, refToKey, dictHead, formOverlays);
    if (!out.all_entries.length) out.all_entries = collectFillEntries(out.fill);
    out.preferred_entries = hydrateLookupEntries(src.preferred_entries, entryStore, refToKey, dictHead, formOverlays);
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

  function buildExactLookupDebugEvent(displayText, lookupText, lemmaHint, exactMode, entries, vetoInfo) {
    var list = Array.isArray(entries) ? entries : [];
    var info = vetoInfo || null;
    return {
      mode: String(exactMode || ""),
      display_text: String(displayText || lookupText || "").trim(),
      lookup_text: String(lookupText || "").trim(),
      lemma_text: String(lemmaHint || "").trim(),
      matched: !!list.length,
      vetoed: !!(info && info.vetoed),
      reason: (info && info.vetoed) ? String(info.reason || "xpos_pos_mismatch") : "",
      xpos_tags: (info && Array.isArray(info.xpos_tags)) ? info.xpos_tags.slice() : [],
      allowed_pos: (info && Array.isArray(info.allowed_pos)) ? info.allowed_pos.slice() : [],
      entry_refs: buildDebugEntryRefs(list)
    };
  }

  function pushLookupDebugEvent(options, event) {
    var opts = options || {};
    var store = opts._debug_lookup_events;
    var label = String(opts._debug_lookup_label || "").trim();
    if (!store || !label || !event || typeof event !== "object") return;
    if (!Array.isArray(store[label])) store[label] = [];
    store[label].push(event);
  }

  function resolveExactThenGreedy(displayText, lookupText, engine, upos, exactMode, greedyMode, lemmaHint, xposHint, options) {
    options = options || {};
    var includeDebugTrace = !!options.debug_trace;
    var query = String(lookupText || "").trim();
    if (!query) return null;
    var entries = engine.lookup_all(query) || [];
    if (entries.length) {
      var exactVetoInfo = null;
      if (includeDebugTrace) {
        pushLookupDebugEvent(options, buildExactLookupDebugEvent(
          displayText || query,
          query,
          lemmaHint,
          exactMode,
          entries,
          exactVetoInfo
        ));
      }
      return buildFillResult(displayText || query, entries.slice(), exactMode);
    }
    var fillOpts = { allowExact: false, upos: upos || "" };
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
        return { entries: allEntries, fill: fillOut };
      }
    }
    return null;
  }

  function mergeLookupResults(results, mode) {
    var mergedEntries = [];
    var mergedFills = [];
    var hasKnown = false;
    var hasUnknown = false;
    var mergedDpDebugParts = [];
    for (var i = 0; i < (results || []).length; i++) {
      var result = results[i];
      if (!result || typeof result !== "object") continue;
      var ents = result.entries || [];
      for (var e = 0; e < ents.length; e++) mergedEntries.push(ents[e]);
      var fill = result.fill || {};
      var fills = fill.fills || [];
      for (var f = 0; f < fills.length; f++) mergedFills.push(fills[f]);
      hasKnown = hasKnown || !!fill.has_known;
      hasUnknown = hasUnknown || !!fill.has_unknown;
      if (fill.dp_debug && typeof fill.dp_debug === "object") {
        mergedDpDebugParts.push({
          index: i,
          mode: String(fill.mode || ""),
          fills: buildDebugFillPreview(fill),
          dp_debug: fill.dp_debug
        });
      }
    }
    if (!mergedEntries.length) return null;
    var mergedFill = {
      mode: mode,
      fills: mergedFills,
      has_known: hasKnown || !!mergedEntries.length,
      has_unknown: hasUnknown
    };
    if (mergedDpDebugParts.length) {
      mergedFill.dp_debug = {
        kind: "merged",
        mode: mode,
        parts: mergedDpDebugParts
      };
    }
    return {
      entries: mergedEntries,
      fill: mergedFill
    };
  }

  function resultMatchCount(result) {
    if (!result || typeof result !== "object") return 0;
    var fill = result.fill || {};
    var fills = Array.isArray(fill.fills) ? fill.fills : [];
    if (fills.length) return fills.length;
    return Array.isArray(result.entries) ? result.entries.length : 0;
  }

  function resolveLemmaOverride(surface, lemmaText, engine, upos, xpos, options) {
    options = options || {};
    var lemmaValue = String(lemmaText || "").trim();
    if (!lemmaValue) return null;
    var parts = splitCompoundLemma(lemmaValue);
    var lookupTarget = parts.length ? parts.join("") : lemmaValue;
    if (!lookupTarget) return null;

    var resolved = resolveExactThenGreedy(
      surface,
      lookupTarget,
      engine,
      upos || "",
      "lemma_override",
      "lemma_greedy",
      lemmaValue,
      String(xpos || "").trim().toLowerCase(),
      options
    );
    return resolved;
  }

  function wiktLookup(word, lemma, engine, xpos, upos, options) {
    options = options || {};
    var includeDebugTrace = !!options.debug_trace;
    var surface = String(word || "").trim();
    var lemmaText = String(lemma || "").trim();
    if (!surface) return null;
    var lemmaResult = null;
    var debugLookupEvents = includeDebugTrace ? { surface: [], lemma: [] } : null;

    function makeLookupOptions(pathLabel) {
      if (!includeDebugTrace) return options;
      var out = {};
      for (var key in options) {
        if (Object.prototype.hasOwnProperty.call(options, key)) out[key] = options[key];
      }
      out._debug_lookup_events = debugLookupEvents;
      out._debug_lookup_label = String(pathLabel || "");
      return out;
    }

    var surfaceLookupOptions = makeLookupOptions("surface");
    var lemmaLookupOptions = makeLookupOptions("lemma");

    function finishLookupResult(result, chosenPath, reason) {
      if (includeDebugTrace && result && typeof result === "object") {
        result._debug_lookup_scoring = {
          token: surface,
          lemma_text: lemmaText,
          chosen_path: String(chosenPath || ""),
          selection_reason: String(reason || ""),
          surface_exact_events: debugLookupEvents && Array.isArray(debugLookupEvents.surface)
            ? debugLookupEvents.surface.slice()
            : [],
          lemma_exact_events: debugLookupEvents && Array.isArray(debugLookupEvents.lemma)
            ? debugLookupEvents.lemma.slice()
            : []
        };
      }
      if (result && typeof result === "object") {
        result.resolved_via = String(chosenPath || "");
      }
      return result;
    }

    var surfaceResult = options.surface_result || null;
    if (!surfaceResult) {
      surfaceResult = resolveExactThenGreedy(
        surface,
        surface,
        engine,
        upos || "",
        "exact",
        "greedy",
        lemmaText || surface,
        xpos || "",
        surfaceLookupOptions
      );
    }

    if (!lemmaText || normalizeVisibleComparisonText(lemmaText) === normalizeVisibleComparisonText(surface)) {
      return finishLookupResult(surfaceResult, "surface", "lemma_same_as_surface");
    }

    lemmaResult = resolveLemmaOverride(
      surface,
      lemmaText,
      engine,
      upos || "",
      xpos || "",
      lemmaLookupOptions
    );
    if (lemmaResult == null) return finishLookupResult(surfaceResult, "surface", "lemma_unresolved");
    if (surfaceResult == null) return finishLookupResult(lemmaResult, "lemma", "surface_unresolved");

    var surfaceHasUnknown = !!(surfaceResult.fill && surfaceResult.fill.has_unknown);
    var lemmaHasUnknown = !!(lemmaResult.fill && lemmaResult.fill.has_unknown);
    if (surfaceHasUnknown !== lemmaHasUnknown) {
      if (surfaceHasUnknown) return finishLookupResult(lemmaResult, "lemma", "surface_has_unknown");
      return finishLookupResult(surfaceResult, "surface", "lemma_has_unknown");
    }

    var lemmaCount = resultMatchCount(lemmaResult);
    var surfaceCount = resultMatchCount(surfaceResult);
    if (lemmaCount < surfaceCount) {
      return finishLookupResult(lemmaResult, "lemma", "lemma_has_fewer_matches");
    }
    if (lemmaCount === surfaceCount) {
      var surfaceMode = String((surfaceResult.fill && surfaceResult.fill.mode) || "").toLowerCase();
      // If surface is an exact match, preserve it on ties.
      if (surfaceMode === "exact") return finishLookupResult(surfaceResult, "surface", "tie_prefers_surface_exact");
      // Otherwise (greedy surface path), lemma wins ties.
      return finishLookupResult(lemmaResult, "lemma", "tie_prefers_lemma");
    }
    return finishLookupResult(surfaceResult, "surface", "surface_has_fewer_matches");
  }

  function dedupeMergedSenseLines(lines) {
    var out = [];
    var seen = Object.create(null);
    var seenSenseSegments = Object.create(null);
    var seenSenseTexts = Object.create(null);
    for (var i = 0; i < (lines || []).length; i++) {
      var line = String(lines[i] || "");
      if (!line) continue;
      if (line.charAt(0) === "\x1E") {
        seenSenseSegments = Object.create(null);
        seenSenseTexts = Object.create(null);
        out.push(line);
        continue;
      }
      var senseText = "";
      var prefix = "";
      var resetOverlap = line.charAt(0) !== "\t";
      var parts = line.split("\t");
      if (parts.length > 1) {
        senseText = String(parts[parts.length - 1] || "").trim();
        prefix = line.slice(0, line.length - String(parts[parts.length - 1] || "").length);
      }
      if (resetOverlap) {
        seenSenseSegments = Object.create(null);
        seenSenseTexts = Object.create(null);
      }
      if (senseText) {
        if (seenSenseTexts[senseText]) continue;
        var trimmedSenseText = trimSeenGlossOverlap(senseText, seenSenseSegments);
        if (!trimmedSenseText) continue;
        line = prefix + trimmedSenseText;
      }
      if (seen[line]) continue;
      seen[line] = true;
      out.push(line);
      if (senseText) {
        var emittedSenseText = String(line.slice(prefix.length) || "").trim();
        if (emittedSenseText) seenSenseTexts[emittedSenseText] = true;
        seenSenseTexts[senseText] = true;
        var visibleSegments = splitGlossDedupeSegments(emittedSenseText);
        for (var ssi = 0; ssi < visibleSegments.length; ssi++) {
          seenSenseSegments[visibleSegments[ssi]] = true;
        }
      }
    }
    return out;
  }

  function splitGlossDedupeSegments(text) {
    return String(text || "")
      .split(";")
      .map(function(part) { return String(part || "").trim(); })
      .filter(Boolean);
  }

  // Strip previously shown semicolon-delimited gloss parts from later sense rows.
  function trimSeenGlossOverlap(text, seenSegments) {
    var original = String(text || "").trim();
    if (!original) return "";
    var segments = splitGlossDedupeSegments(original);
    if (!segments.length) return "";
    if (!seenSegments || typeof seenSegments !== "object") return original;

    var kept = [];
    for (var i = 0; i < segments.length; i++) {
      if (seenSegments[segments[i]]) continue;
      kept.push(segments[i]);
    }
    return kept.join("; ").trim();
  }

  function listTexts(raw) {
    var out = [];
    if (Array.isArray(raw)) {
      for (var i = 0; i < raw.length; i++) {
        var txt = String(raw[i] || "").trim();
        if (txt) out.push(txt);
      }
    } else {
      var one = String(raw || "").trim();
      if (one) out.push(one);
    }
    return out;
  }

  function buildEntrySpellingsHead(entry) {
    var direct = String((entry && entry.spelling_header) || "").trim();
    if (direct) return direct;
    var forms = (entry && entry.forms && typeof entry.forms === "object") ? entry.forms : {};
    var kanjiForms = Array.isArray(forms.kanji) ? forms.kanji : ((entry && entry.kanji) ? entry.kanji : []);
    var readings = Array.isArray(forms.readings) ? forms.readings : ((entry && entry.readings) ? entry.readings : []);
    if (kanjiForms && kanjiForms.length) {
      var header = kanjiForms.join("\u30fb");
      if (readings && readings.length) header += "\u3010" + readings.join("\u30fb") + "\u3011";
      return header;
    }
    return (readings && readings.length) ? readings.join("\u30fb") : "";
  }

  function abbreviatePos(posText) {
    if (!posText) return "";
    var lower = String(posText).toLowerCase().trim();
    if (Object.prototype.hasOwnProperty.call(POS_ABBREV, lower)) return POS_ABBREV[lower];
    for (var full in POS_ABBREV) {
      if (!Object.prototype.hasOwnProperty.call(POS_ABBREV, full)) continue;
      if (String(full).toLowerCase() === lower) return POS_ABBREV[full];
    }
    var fallback = String(posText || "").trim();
    if (fallback.length > 6) fallback = fallback.slice(0, 6);
    return fallback.trim().replace(/,+$/, "");
  }

  function formatStructuredSenses(senses) {
    if (!senses || !senses.length) return [];

    var dictSenses = [];
    for (var i = 0; i < senses.length; i++) {
      if (senses[i] && typeof senses[i] === "object" && senses[i].glosses) dictSenses.push(senses[i]);
    }
    var commonMisc = Object.create(null);
    if (dictSenses.length) {
      var firstMisc = dictSenses[0].misc || [];
      for (var fm = 0; fm < firstMisc.length; fm++) commonMisc[String(firstMisc[fm] || "")] = true;
      for (var ds = 1; ds < dictSenses.length; ds++) {
        var set = Object.create(null);
        var cur = dictSenses[ds].misc || [];
        for (var cm = 0; cm < cur.length; cm++) set[String(cur[cm] || "")] = true;
        var nextCommon = Object.create(null);
        for (var key in commonMisc) {
          if (Object.prototype.hasOwnProperty.call(commonMisc, key) && set[key]) nextCommon[key] = true;
        }
        commonMisc = nextCommon;
      }
    }

    var formatted = [];
    var prevPosKey = "";
    for (var si = 0; si < senses.length; si++) {
      var sense = senses[si];
      if (!sense || typeof sense !== "object") {
        formatted.push("\t" + String(sense || ""));
        continue;
      }
      var glosses = Array.isArray(sense.glosses) ? sense.glosses : [];
      if (!glosses.length) continue;

      var posList = Array.isArray(sense.pos) ? sense.pos : [];
      var misc = Array.isArray(sense.misc) ? sense.misc : [];
      var sInf = String(sense.s_inf || "");
      var field = Array.isArray(sense.field) ? sense.field : [];
      var stagk = Array.isArray(sense.stagk) ? sense.stagk : [];
      var stagr = Array.isArray(sense.stagr) ? sense.stagr : [];
      var xref = Array.isArray(sense.xref) ? sense.xref : [];
      var ant = Array.isArray(sense.ant) ? sense.ant : [];
      var dial = Array.isArray(sense.dial) ? sense.dial : [];
      var lsource = Array.isArray(sense.lsource) ? sense.lsource : [];

      var posParts = [];
      for (var p = 0; p < posList.length; p++) {
        var part = abbreviatePos(posList[p]);
        part = part.split(/\s+/).join(" ").trim().replace(/,+$/, "");
        if (part) posParts.push(part);
      }
      var posLabel = posParts.join(", ");
      var posKey = posList.join("|");

      var senseText = glosses.join("; ");
      var annotations = [];
      for (var m = 0; m < misc.length; m++) {
        var mv = String(misc[m] || "");
        if (!mv || commonMisc[mv]) continue;
        annotations.push(mv);
      }
      for (var f = 0; f < field.length; f++) annotations.push(String(field[f] || ""));
      for (var d = 0; d < dial.length; d++) annotations.push(String(dial[d] || ""));
      if (stagk.length) annotations.push("kanji: " + stagk.join(", "));
      if (stagr.length) annotations.push("reading: " + stagr.join(", "));
      if (lsource.length) annotations.push("source: " + lsource.join(", "));
      if (annotations.length) senseText += " [" + annotations.join("; ") + "]";
      if (xref.length) senseText += " [cf. " + xref.join(", ") + "]";
      if (ant.length) senseText += " [ant. " + ant.join(", ") + "]";
      if (sInf) senseText += "\x1F(" + sInf + ")";

      if (!formatted.length || (posKey !== prevPosKey && posLabel)) {
        formatted.push("\t\t" + posLabel + "\t" + senseText);
      } else {
        formatted.push("\t" + senseText);
      }
      if (posKey) prevPosKey = posKey;
    }

    var commonMiscKeys = Object.keys(commonMisc).sort();
    if (commonMiscKeys.length) {
      formatted.push("\t[" + commonMiscKeys.join("; ") + "]");
    }
    return formatted;
  }

  function formatSenses(head, roman, rawSenses, pos) {
    if (!rawSenses || !rawSenses.length) return [];
    var formatted = [];
    for (var i = 0; i < rawSenses.length; i++) {
      var sense = rawSenses[i];
      if (i === 0) formatted.push(String(head || "") + "\t" + String(roman || "") + "\t" + String(pos || "") + "\t" + String(sense || ""));
      else formatted.push("\t\t\t" + String(sense || ""));
    }
    return formatted;
  }

  function mergeAllEntries(head, entries) {
    var formatted = [];
    for (var i = 0; i < (entries || []).length; i++) {
      var entry = entries[i] || {};
      _ensureEntryHydrated(entry);
      var roman = getEntryDisplayReading(entry);
      var pos = entry.pos || "";
      var sensesFull = Array.isArray(entry.senses_full) ? entry.senses_full : [];
      var senses = Array.isArray(entry.senses) ? entry.senses : [];
      if (sensesFull.length || (senses.length && typeof senses[0] === "object")) {
        var entryHead = buildEntrySpellingsHead(entry);
        if (entryHead) formatted.push("\x1E" + entryHead);
        var structured = formatStructuredSenses(sensesFull.length ? sensesFull : senses);
        for (var s = 0; s < structured.length; s++) formatted.push(structured[s]);
      } else {
        var displayHead = String(entry.headword || head || "");
        var lines = formatSenses(displayHead, roman, senses, pos);
        for (var l = 0; l < lines.length; l++) formatted.push(lines[l]);
      }
    }
    return dedupeMergedSenseLines(formatted);
  }

  function computeMetaSpecTag(tags) {
    var rawTags = listTexts(tags);
    var tagSet = Object.create(null);
    for (var i = 0; i < rawTags.length; i++) tagSet[rawTags[i]] = true;
    if (tagSet.spec1) return "spec1";
    if (tagSet.spec2) return "spec2";
    return "";
  }

  function metaNfPercent(nfBand) {
    var band = Math.max(1, Math.min(48, Number(nfBand) || 1));
    var pct = ((49 - band) / 48.0) * 100.0;
    if (pct < 0.0) return 0.0;
    if (pct > 100.0) return 100.0;
    return pct;
  }

  function computeMetaPriScoreDetails(tags) {
    var rawTags = listTexts(tags);
    var bestNf = null;
    for (var i = 0; i < rawTags.length; i++) {
      var m = META_NF_RE.exec(rawTags[i]);
      if (!m) continue;
      var nfBand = parseInt(m[1], 10);
      if (!isFinite(nfBand)) continue;
      if (bestNf == null || nfBand < bestNf) bestNf = nfBand;
    }
    if (bestNf != null) return [metaNfPercent(bestNf), "nf" + String(bestNf).padStart(2, "0")];

    var bestScore = 0.0;
    var bestTag = "";
    for (var j = 0; j < rawTags.length; j++) {
      var pct = META_PRI_TAG_PERCENT[rawTags[j]];
      if (pct == null) continue;
      if (pct > bestScore) {
        bestScore = pct;
        bestTag = rawTags[j];
      }
    }
    if (bestScore < 0.0) bestScore = 0.0;
    if (bestScore > 100.0) bestScore = 100.0;
    return [bestScore, bestTag];
  }

  function buildJmdictFormsMetaBundle(entry) {
    if (!entry || typeof entry !== "object") return {};
    if (entry.forms_meta && typeof entry.forms_meta === "object") {
      return Object.assign({}, entry.forms_meta);
    }
    var kanjiInfo = entry.kanji_info || {};
    var kanjiPri = entry.kanji_pri || {};
    var readingInfo = entry.reading_info || {};
    var readingPri = entry.reading_pri || {};
    var readingRestr = entry.reading_restr || {};
    var readingNokanji = entry.reading_nokanji || {};

    var kanjiRows = [];
    var kanjiByForm = {};
    var kanjiList = listTexts(entry.kanji || []);
    for (var i = 0; i < kanjiList.length; i++) {
      var kForm = kanjiList[i];
      var kPriTags = listTexts(kanjiPri[kForm] || []);
      var kInfoTags = listTexts(kanjiInfo[kForm] || []);
      var kScore = computeMetaPriScoreDetails(kPriTags);
      var kSpecTag = computeMetaSpecTag(kPriTags);
      var kRow = {
        form: kForm,
        kind: "kanji",
        info_tags: kInfoTags,
        priority_tags: kPriTags,
        priority_score: kScore[0],
        priority_basis_tag: kScore[1],
        spec_priority_tag: kSpecTag
      };
      kanjiRows.push(kRow);
      kanjiByForm[kForm] = Object.assign({}, kRow);
    }

    var readingRows = [];
    var readingByForm = {};
    var readingList = listTexts(entry.readings || []);
    for (var j = 0; j < readingList.length; j++) {
      var rForm = readingList[j];
      var rPriTags = listTexts(readingPri[rForm] || []);
      var rInfoTags = listTexts(readingInfo[rForm] || []);
      var restricted = listTexts(readingRestr[rForm] || []);
      var noKanji = !!readingNokanji[rForm];
      var rScore = computeMetaPriScoreDetails(rPriTags);
      var rSpecTag = computeMetaSpecTag(rPriTags);
      var rRow = {
        form: rForm,
        kind: "reading",
        info_tags: rInfoTags,
        priority_tags: rPriTags,
        priority_score: rScore[0],
        priority_basis_tag: rScore[1],
        spec_priority_tag: rSpecTag,
        no_kanji: noKanji,
        restricted_to_kanji: restricted,
        is_restricted: !!restricted.length
      };
      readingRows.push(rRow);
      readingByForm[rForm] = Object.assign({}, rRow);
    }

    return {
      kanji: kanjiRows,
      readings: readingRows,
      kanji_by_form: kanjiByForm,
      readings_by_form: readingByForm
    };
  }

  function buildJmdictFormsMetaByHeader(entries) {
    var out = {};
    for (var i = 0; i < (entries || []).length; i++) {
      var entry = entries[i];
      if (!entry || typeof entry !== "object") continue;
      var header = buildEntrySpellingsHead(entry);
      if (!header || out[header]) continue;
      var bundle = buildJmdictFormsMetaBundle(entry);
      if (!bundle || !Object.keys(bundle).length) continue;
      bundle.header = header;
      out[header] = bundle;
    }
    return out;
  }

  function splitEntriesForHover(entries, upos, engine, xpos, filterKwargs) {
    var baseEntries = Array.isArray(entries) ? entries.slice() : [];
    if (!baseEntries.length) return [baseEntries, []];

    var callKw = Object.assign({}, filterKwargs || {});
    var strictLemmaEntries = Array.isArray(callKw.strict_exact_lemma_entries)
      ? callKw.strict_exact_lemma_entries.slice()
      : [];
    if (Object.prototype.hasOwnProperty.call(callKw, "strict_exact_lemma_entries")) {
      delete callKw.strict_exact_lemma_entries;
    }
    function splitStrictLemmaEntries(inputEntries) {
      var sourceEntries = Array.isArray(inputEntries) ? inputEntries.slice() : [];
      if (!sourceEntries.length || !strictLemmaEntries.length) return null;
      var strictEntryIds = Object.create(null);
      var strictFallback = [];
      for (var sei = 0; sei < strictLemmaEntries.length; sei++) {
        var strictEntry = strictLemmaEntries[sei];
        var strictEntryId = getStableRuntimeEntryId(strictEntry);
        if (strictEntryId) strictEntryIds[strictEntryId] = true;
        else strictFallback.push(strictEntry);
      }
      var strictPrimary = [];
      var strictAlternate = [];
      for (var sbi = 0; sbi < sourceEntries.length; sbi++) {
        var baseEntry = sourceEntries[sbi];
        var baseEntryId = getStableRuntimeEntryId(baseEntry);
        var isStrict = !!(baseEntryId && strictEntryIds[baseEntryId]);
        if (!isStrict && !baseEntryId && strictFallback.indexOf(baseEntry) >= 0) isStrict = true;
        if (isStrict) strictPrimary.push(baseEntry);
        else strictAlternate.push(baseEntry);
      }
      return strictPrimary.length ? [strictPrimary, strictAlternate] : null;
    }

    var explicitAlternate = [];
    var posFilterInput = [];
    for (var bei = 0; bei < baseEntries.length; bei++) {
      var baseEntry = baseEntries[bei];
      if (baseEntry && baseEntry.is_alternate_match) explicitAlternate.push(baseEntry);
      else posFilterInput.push(baseEntry);
    }
    if (!posFilterInput.length) {
      return [baseEntries.slice(), []];
    }

    var strictLemmaSplit = splitStrictLemmaEntries(posFilterInput);
    var lemmaFilterInput = strictLemmaSplit ? strictLemmaSplit[0] : null;
    var nonLemmaEntries = strictLemmaSplit ? strictLemmaSplit[1] : [];

    function runCorePosFilter(inputEntries) {
      var filterInput = Array.isArray(inputEntries) ? inputEntries.slice() : [];
      if (!filterInput.length) return [[], []];
      var result;
      try {
        var activeLang = getCurrentLanguage();
        if (
          languageUsesXposFilter(activeLang)
          && engine
          && typeof engine.filter_entries_by_xpos === "function"
        ) {
          result = engine.filter_entries_by_xpos(
            filterInput,
            splitCompoundTags(xpos).map(function(t) {
              return normalizeFilterXposTag(t, activeLang);
            }).filter(Boolean)
          );
        } else if (engine && typeof engine.filter_entries_by_upos === "function") {
          var filterKw = Object.assign({}, callKw);
          if (xpos && !Object.prototype.hasOwnProperty.call(filterKw, "xpos")) {
            filterKw.xpos = xpos;
          }
          result = engine.filter_entries_by_upos(filterInput, upos, filterKw);
        } else {
          result = [filterInput, []];
        }
      } catch (_e) {
        result = [filterInput, []];
      }
      if (Array.isArray(result) && result.length === 2) {
        return [
          Array.isArray(result[0]) ? result[0] : [],
          Array.isArray(result[1]) ? result[1] : []
        ];
      }
      var filtered = Array.isArray(result) ? result.slice() : [];
      var alternate = [];
      for (var j = 0; j < filterInput.length; j++) {
        if (filtered.indexOf(filterInput[j]) < 0) alternate.push(filterInput[j]);
      }
      return [filtered, alternate];
    }

    function appendExplicitAlternate(alternate) {
      var alt = Array.isArray(alternate) ? alternate.slice() : [];
      for (var i = 0; i < explicitAlternate.length; i++) {
        if (alt.indexOf(explicitAlternate[i]) < 0) alt.push(explicitAlternate[i]);
      }
      return alt;
    }

    // Try to run POS filter on explicitAlternate entries so we can promote them
    // when no non-alt entries survive POS filtering.
    function posFilterAlternates() {
      if (!explicitAlternate.length) return null;
      try {
        var altResult = runCorePosFilter(explicitAlternate);
        return altResult[0].length ? altResult : null;
      } catch (_e2) {
        return null;
      }
    }

    if (lemmaFilterInput && lemmaFilterInput.length) {
      var lemmaResult = runCorePosFilter(lemmaFilterInput);
      var lemmaPrimary = Array.isArray(lemmaResult[0]) ? lemmaResult[0] : [];
      var lemmaAlternate = Array.isArray(lemmaResult[1]) ? lemmaResult[1] : [];
      if (lemmaPrimary.length) {
        var lemmaCombinedAlternate = nonLemmaEntries.slice();
        for (var lai = 0; lai < lemmaAlternate.length; lai++) {
          if (lemmaCombinedAlternate.indexOf(lemmaAlternate[lai]) < 0) lemmaCombinedAlternate.push(lemmaAlternate[lai]);
        }
        return [lemmaPrimary, appendExplicitAlternate(lemmaCombinedAlternate)];
      }
      return [lemmaFilterInput.slice(), appendExplicitAlternate(nonLemmaEntries)];
    }

    var result = runCorePosFilter(posFilterInput);
    if (Array.isArray(result) && result.length === 2) {
      var primary = Array.isArray(result[0]) ? result[0] : [];
      var alternate = Array.isArray(result[1]) ? result[1] : [];
      var combinedAlternate = appendExplicitAlternate(alternate);
      if (!primary.length && combinedAlternate.length) {
        // No non-alt entry survived POS filtering. Try promoting alt entries that
        // actually match the POS tag rather than blindly returning everything.
        var altFiltered = posFilterAlternates();
        if (altFiltered) {
          // At least one alt matches — promote the matching alts to primary.
          var altPrimary = Array.isArray(altFiltered[0]) ? altFiltered[0] : [];
          var altSecondary = Array.isArray(altFiltered[1]) ? altFiltered[1] : [];
          // Non-alt entries that failed POS filter go to secondary as well.
          var nonAltFailed = alternate.slice(); // these already failed POS filter
          var secondaryMerged = altSecondary.slice();
          for (var k = 0; k < nonAltFailed.length; k++) {
            if (secondaryMerged.indexOf(nonAltFailed[k]) < 0) secondaryMerged.push(nonAltFailed[k]);
          }
          return [altPrimary, secondaryMerged];
        }
        // No alt matches POS either — fall back to showing everything as primary.
        return [baseEntries.slice(), []];
      }
      if (!primary.length && !combinedAlternate.length) return [posFilterInput.slice(), explicitAlternate.slice()];
      return [primary, combinedAlternate];
    }

    var filtered = Array.isArray(result) ? result.slice() : [];
    if (!filtered.length) return [baseEntries.slice(), []];
    var alternateFlat = [];
    for (var j = 0; j < posFilterInput.length; j++) {
      if (filtered.indexOf(posFilterInput[j]) < 0) alternateFlat.push(posFilterInput[j]);
    }
    return [filtered, appendExplicitAlternate(alternateFlat)];
  }

  function toDebugLineNo(raw) {
    var n = parseInt(raw || 0, 10);
    if (!isFinite(n) || n <= 0) return 0;
    return n;
  }

  function entryDebugIdentity(entry) {
    var e = entry || {};
    var head = String(e.headword || "").trim();
    var posRaw = String(e.pos_raw || e.pos || "").trim();
    var etymNum = parseInt(e.etymology_number || 0, 10);
    if (!isFinite(etymNum) || etymNum < 0) etymNum = 0;
    var etymText = String(e.etymology || "");
    var eid = getStableRuntimeEntryId(e);
    return head + "\t" + posRaw + "\t" + etymNum + "\t" + etymText + "\t" + eid;
  }

  function buildDebugEntryRef(entry) {
    var e = entry || {};
    var lineNo = toDebugLineNo(e.__line_no);
    var morphInfo = Array.isArray(e.morph_info)
      ? e.morph_info.slice().map(function(v) { return String(v || "").trim(); }).filter(Boolean)
      : [];
    return {
      line_no: lineNo || null,
      headword: String(e.headword || "").trim(),
      pos_raw: String(e.pos_raw || e.pos || "").trim(),
      reading: getEntryDisplayReading(e),
      etymology_number: (function() {
        var n = parseInt(e.etymology_number || 0, 10);
        return (isFinite(n) && n > 0) ? n : 0;
      })(),
      etymology: String(e.etymology || ""),
      identity: entryDebugIdentity(e),
      morph_base: String(e.morph_base || "").trim(),
      morph_info: morphInfo
    };
  }

  function buildDebugEntryRefs(entries) {
    var out = [];
    var seen = Object.create(null);
    var list = Array.isArray(entries) ? entries : [];
    for (var i = 0; i < list.length; i++) {
      var ref = buildDebugEntryRef(list[i]);
      var key = String(ref.line_no || "") + "\t" + String(ref.identity || "");
      if (!key.trim() || seen[key]) continue;
      seen[key] = true;
      out.push(ref);
    }
    return out;
  }

  function buildDebugLemmaHintPreview(engine, preparedFills, lemmaHints) {
    void engine;
    void preparedFills;
    var out = [];
    var hintList = Array.isArray(lemmaHints) ? lemmaHints : [];
    for (var i = 0; i < hintList.length; i++) {
      var hint = hintList[i];
      if (hint && typeof hint === "object" && !Array.isArray(hint)) {
        var cloned = {};
        for (var key in hint) {
          if (Object.prototype.hasOwnProperty.call(hint, key)) cloned[key] = hint[key];
        }
        out.push(cloned);
        continue;
      }
      var text = String(hint || "").trim();
      if (!text) continue;
      out.push({ text: text });
    }
    return out;
  }

  function annotateLiveLemmaLinkedFills(fills, resolvedVia) {
    var rows = Array.isArray(fills) ? fills : [];
    var path = String(resolvedVia || "").trim().toLowerCase();
    var wholeLemmaPath = (path === "lemma" || path === "lemma_override");
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      if (!row || typeof row !== "object") continue;
      var linked = !!(
        row._lemma_promoted ||
        row.lemma_promoted ||
        row._lemma_override ||
        row.lemma_override
      );
      if (!linked && wholeLemmaPath && String(row.source || "").toUpperCase() !== "UNKNOWN") {
        linked = true;
      }
      row.resolution_linked_to_lemma = linked;
      row.resolution_source = linked
        ? ((path === "lemma_override" || row._lemma_override || row.lemma_override)
            ? "lemma_override"
            : (wholeLemmaPath && !(row._lemma_promoted || row.lemma_promoted) ? "lemma" : "lemma_promoted"))
        : "surface";
    }
    return rows;
  }

  var ACTUAL_RESOLUTION_LABELS = {
    exact_match: "Exact Match",
    exact_lemma_match: "Exact Lemma Match",
    mwt_exact_parts: "MWT Exact Match",
    mwt_exact_partial_lemma_match: "MWT Partial Lemma Match",
    mwt_exact_lemma_match: "MWT Exact Lemma Match",
    mwt_lemma_override: "MWT Lemma Override",
    mwt_lemma_partial_override: "Partial MWT Lemma Override",
    lemma_override: "Lemma Override",
    lemma_partial_override: "Partial Lemma Override",
    greedy_match: "Greedy Segmentation",
    lemma_promotion: "Greedy Segmentation + Lemma Scoring"
  };

  function cloneResolutionRouteSteps(rawSteps) {
    var src = Array.isArray(rawSteps) ? rawSteps : [];
    var out = [];
    for (var i = 0; i < src.length; i++) {
      var step = src[i] || {};
      if (typeof step === "string") {
        var text = String(step || "").trim();
        if (text) out.push({ code: "", text: text, detail: "" });
        continue;
      }
      var cloned = {
        code: String(step.code || "").trim(),
        text: String(step.text || "").trim(),
        detail: String(step.detail || "").trim()
      };
      if (!cloned.text) continue;
      out.push(cloned);
    }
    return out;
  }

  function buildResolutionRouteStep(code, text, detail) {
    return {
      code: String(code || "").trim(),
      text: String(text || "").trim(),
      detail: String(detail || "").trim()
    };
  }

  function buildResolutionMeta(category, routeCode, routeSteps, resolvedVia, fillMode, lemmaOracleUsed, lemmaOracleOutcome, extra) {
    var out = {
      category: String(category || "").trim().toLowerCase(),
      route_code: String(routeCode || "").trim().toLowerCase(),
      route_steps: cloneResolutionRouteSteps(routeSteps),
      resolved_via: String(resolvedVia || "").trim().toLowerCase(),
      fill_mode: String(fillMode || "").trim().toLowerCase(),
      lemma_oracle_used: !!lemmaOracleUsed,
      lemma_oracle_outcome: String(lemmaOracleOutcome || "").trim().toLowerCase()
    };
    var extras = (extra && typeof extra === "object") ? extra : null;
    if (extras) {
      for (var key in extras) {
        if (!Object.prototype.hasOwnProperty.call(extras, key)) continue;
        out[key] = extras[key];
      }
    }
    return out;
  }

  function summarizeActualResolutionFills(fills) {
    var rows = Array.isArray(fills) ? fills : [];
    var knownFillCount = 0;
    var unknownFillCount = 0;
    var lemmaLinkedFillCount = 0;
    var lemmaLinkedFillIndexes = [];
    var lemmaLinkedDistinctKeys = Object.create(null);
    var lemmaLinkedDistinctCount = 0;
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      if (String(row.source || "").toUpperCase() === "UNKNOWN") {
        unknownFillCount += 1;
      } else {
        knownFillCount += 1;
      }
      if (!row.resolution_linked_to_lemma) continue;
      lemmaLinkedFillCount += 1;
      lemmaLinkedFillIndexes.push(i);
      var lemmaKey = String(
        row._lemma_override || row._lemma_promoted || row.lemma_form || row.morph_base || ""
      ).trim();
      if (lemmaKey && !lemmaLinkedDistinctKeys[lemmaKey]) {
        lemmaLinkedDistinctKeys[lemmaKey] = true;
        lemmaLinkedDistinctCount += 1;
      }
    }
    return {
      total_piece_count: rows.length,
      known_piece_count: knownFillCount,
      unknown_piece_count: unknownFillCount,
      lemma_linked_piece_count: lemmaLinkedFillCount,
      lemma_linked_fill_indexes: lemmaLinkedFillIndexes,
      lemma_linked_distinct_count: lemmaLinkedDistinctCount
    };
  }

  function buildResolutionRouteText(routeSteps) {
    var steps = cloneResolutionRouteSteps(routeSteps);
    if (!steps.length) return "";
    var out = [];
    for (var i = 0; i < steps.length; i++) {
      var step = steps[i] || {};
      var text = String(step.text || "").trim();
      var detail = String(step.detail || "").trim();
      if (!text) continue;
      if (detail) text += " (" + detail + ")";
      out.push(text);
    }
    return out.join(" -> ");
  }

  function buildResolutionFinalText(path, mode, fillSummary, exactLemmaMatchCount) {
    var bits = [];
    var resolvedPath = String(path || "").trim().toLowerCase();
    var fillMode = String(mode || "").trim().toLowerCase();
    var knownCount = parseInt(fillSummary && fillSummary.known_piece_count, 10);
    var unknownCount = parseInt(fillSummary && fillSummary.unknown_piece_count, 10);
    var totalCount = parseInt(fillSummary && fillSummary.total_piece_count, 10);
    var lemmaLinkedCount = parseInt(fillSummary && fillSummary.lemma_linked_piece_count, 10);
    var lemmaExactCount = parseInt(exactLemmaMatchCount, 10);
    if (!isFinite(knownCount) || knownCount < 0) knownCount = 0;
    if (!isFinite(unknownCount) || unknownCount < 0) unknownCount = 0;
    if (!isFinite(totalCount) || totalCount < 0) totalCount = 0;
    if (!isFinite(lemmaLinkedCount) || lemmaLinkedCount < 0) lemmaLinkedCount = 0;
    if (!isFinite(lemmaExactCount) || lemmaExactCount < 0) lemmaExactCount = 0;
    if (resolvedPath) bits.push("via=" + resolvedPath);
    if (fillMode) bits.push("mode=" + fillMode);
    bits.push("pieces=" + String(totalCount));
    bits.push("known=" + String(knownCount));
    if (unknownCount > 0) bits.push("unknown=" + String(unknownCount));
    if (lemmaLinkedCount > 0) bits.push("lemma-linked=" + String(lemmaLinkedCount));
    if (lemmaExactCount > 0) bits.push("lemma-exact=" + String(lemmaExactCount));
    return bits.join(" | ");
  }

  function buildLiveResolutionInfo(resolutionMeta, fills, exactLemmaMatchCount) {
    var meta = (resolutionMeta && typeof resolutionMeta === "object") ? resolutionMeta : null;
    var fillSummary = summarizeActualResolutionFills(fills);
    var category = String((meta && meta.category) || "").trim().toLowerCase();
    var resolvedVia = String((meta && meta.resolved_via) || "").trim().toLowerCase();
    var fillMode = String((meta && meta.fill_mode) || "").trim().toLowerCase();
    var lemmaOracleUsed = !!(meta && meta.lemma_oracle_used);
    var lemmaOracleOutcome = String((meta && meta.lemma_oracle_outcome) || "").trim().toLowerCase();
    var lemmaExactCount = parseInt(exactLemmaMatchCount, 10);
    if (!isFinite(lemmaExactCount) || lemmaExactCount < 0) lemmaExactCount = 0;

    var compareKind = "";
    if (
      category === "exact_lemma_match" ||
      category === "mwt_exact_partial_lemma_match" ||
      category === "mwt_exact_lemma_match" ||
      category === "greedy_lemma_match" ||
      category === "mwt_lemma_override" ||
      category === "mwt_lemma_partial_override" ||
      category === "lemma_override" ||
      category === "lemma_partial_override" ||
      (category === "mwt_exact_parts" && lemmaExactCount > 0)
    ) {
      compareKind = "surface";
    } else if (lemmaOracleUsed) {
      compareKind = "lemma";
    }

    var routeText = buildResolutionRouteText(meta && meta.route_steps);
    var finalText = buildResolutionFinalText(resolvedVia, fillMode, fillSummary, lemmaExactCount);
    if (!category && fillSummary.known_piece_count <= 0) {
      finalText = "";
    }

    return {
      category: category,
      label: category ? (ACTUAL_RESOLUTION_LABELS[category] || "") : "",
      route_code: String((meta && meta.route_code) || "").trim().toLowerCase(),
      route_steps: cloneResolutionRouteSteps(meta && meta.route_steps),
      route_text: routeText,
      final_text: finalText,
      compare_kind: compareKind,
      resolved_via: resolvedVia,
      fill_mode: fillMode,
      lemma_oracle_used: lemmaOracleUsed,
      lemma_oracle_outcome: lemmaOracleOutcome,
      exact_surface_match: category === "exact_match" || category === "exact_lemma_match" || category === "mwt_exact_partial_lemma_match" || category === "mwt_exact_lemma_match",
      exact_matches_lemma: category === "exact_lemma_match" || category === "mwt_exact_lemma_match" || (category === "mwt_exact_parts" && lemmaExactCount > 0),
      exact_lemma_match_count: lemmaExactCount,
      has_lemma_linked_fill: fillSummary.lemma_linked_piece_count > 0,
      lemma_linked_fill_indexes: fillSummary.lemma_linked_fill_indexes.slice(),
      lemma_linked_distinct_count: fillSummary.lemma_linked_distinct_count,
      final_result: {
        total_piece_count: fillSummary.total_piece_count,
        known_piece_count: fillSummary.known_piece_count,
        unknown_piece_count: fillSummary.unknown_piece_count,
        lemma_linked_piece_count: fillSummary.lemma_linked_piece_count
      }
    };
  }

  function buildDebugFillPreview(fill) {
    var out = [];
    var rows = (fill && Array.isArray(fill.fills)) ? fill.fills : [];
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      var dbgTrace = (row && typeof row._debug_trace === "object") ? row._debug_trace : {};
      out.push({
        text: String(row.text || ""),
        head: String(row.head || ""),
        source: String(row.source || ""),
        pos: String(row.pos || ""),
        surface_start: parseInt(row._surface_start, 10) || 0,
        surface_end: parseInt(row._surface_end, 10) || 0,
        xpos_hint: String(row._xpos_hint || ""),
        effective_upos: String(dbgTrace.effective_upos || dbgTrace.upos || ""),
        effective_xpos: String(dbgTrace.effective_xpos || dbgTrace.xpos || ""),
        lemma_upos_hint: String(row._lemma_upos_hint || ""),
        lemma_xpos_hint: String(row._lemma_xpos_hint || ""),
        lemma_promoted: String(row._lemma_promoted || ""),
        entry_refs: buildDebugEntryRefs(Array.isArray(row.entries) ? row.entries : [])
      });
    }
    return out;
  }

  function summarizeLookupResultForDebug(label, result, lookupEvents) {
    var events = Array.isArray(lookupEvents) ? lookupEvents.slice() : [];
    if (!result || typeof result !== "object") {
      if (!events.length) return null;
      return {
        label: String(label || ""),
        mode: "",
        has_known: false,
        has_unknown: false,
        match_count: 0,
        entry_refs: [],
        fills: [],
        dp_debug: null,
        exact_events: events
      };
    }
    var fill = result.fill || {};
    return {
      label: String(label || ""),
      mode: String(fill.mode || ""),
      has_known: !!fill.has_known,
      has_unknown: !!fill.has_unknown,
      match_count: resultMatchCount(result),
      entry_refs: buildDebugEntryRefs(Array.isArray(result.entries) ? result.entries : []),
      fills: buildDebugFillPreview(fill),
      dp_debug: (fill.dp_debug && typeof fill.dp_debug === "object") ? fill.dp_debug : null,
      exact_events: events
    };
  }

  function isKoreanLanguageCode(langValue) {
    var lang = String(langValue || "").trim().toLowerCase();
    return lang === "ko" || lang === "korean" || lang.indexOf("ko-") === 0;
  }

  // Decompose a Korean Hangul syllable (AC00–D7A3) into its constituent jamo.
  // Returns an array of 2 or 3 jamo characters (lead, vowel, optional tail).
  // Non-Hangul syllable characters are returned as-is in a single-element array.
  // Compatibility jamo (3130–318F) are also returned as-is.
  var HANGUL_BASE = 0xAC00;
  var HANGUL_END  = 0xD7A3;
  var LEAD_BASE   = 0x1100;  // Hangul Jamo leading consonants
  var VOWEL_BASE  = 0x1161;  // Hangul Jamo vowels
  var TAIL_BASE   = 0x11A7;  // Hangul Jamo trailing consonants (0 = no tail)
  var NUM_VOWELS  = 21;
  var NUM_TAILS   = 28;      // includes 0 for no trailing consonant

  function decomposeHangulSyllable(ch) {
    var code = ch.codePointAt(0);
    if (code < HANGUL_BASE || code > HANGUL_END) return [ch];
    var syllableIndex = code - HANGUL_BASE;
    var leadIdx  = Math.floor(syllableIndex / (NUM_VOWELS * NUM_TAILS));
    var vowelIdx = Math.floor((syllableIndex % (NUM_VOWELS * NUM_TAILS)) / NUM_TAILS);
    var tailIdx  = syllableIndex % NUM_TAILS;
    var result = [
      String.fromCodePoint(LEAD_BASE + leadIdx),
      String.fromCodePoint(VOWEL_BASE + vowelIdx)
    ];
    if (tailIdx > 0) result.push(String.fromCodePoint(TAIL_BASE + tailIdx));
    return result;
  }

  // Map compatibility jamo (U+3131–U+3163) to Hangul Jamo leading consonants
  // (U+1100–U+1112) for NW comparison. This lets Trankit outputs like bare ㄴ
  // (U+3134) match decomposed syllable jamo ᄂ (U+1102) / ᆫ (U+11AB).
  // We normalize everything to leading consonant form for comparison only.
  var COMPAT_CONSONANT_TO_LEAD = {};
  (function() {
    // compatibility jamo consonants → leading jamo codepoints
    var map = [
      [0x3131, 0x1100], // ㄱ → ᄀ
      [0x3132, 0x1101], // ㄲ → ᄁ
      [0x3134, 0x1102], // ㄴ → ᄂ
      [0x3137, 0x1103], // ㄷ → ᄃ
      [0x3138, 0x1104], // ㄸ → ᄄ
      [0x3139, 0x1105], // ㄹ → ᄅ
      [0x3141, 0x1106], // ㅁ → ᄆ
      [0x3142, 0x1107], // ㅂ → ᄇ
      [0x3143, 0x1108], // ㅃ → ᄈ
      [0x3145, 0x1109], // ㅅ → ᄉ
      [0x3146, 0x110A], // ㅆ → ᄊ
      [0x3147, 0x110B], // ㅇ → ᄋ
      [0x3148, 0x110C], // ㅈ → ᄌ
      [0x3149, 0x110D], // ㅉ → ᄍ
      [0x314A, 0x110E], // ㅊ → ᄎ
      [0x314B, 0x110F], // ㅋ → ᄏ
      [0x314C, 0x1110], // ㅌ → ᄐ
      [0x314D, 0x1111], // ㅍ → ᄑ
      [0x314E, 0x1112]  // ㅎ → ᄒ
    ];
    for (var i = 0; i < map.length; i++) {
      COMPAT_CONSONANT_TO_LEAD[map[i][0]] = map[i][1];
    }
  })();

  // Also map trailing jamo (U+11A8–U+11C2) to leading consonant equivalents
  var TAIL_TO_LEAD = {};
  (function() {
    var map = [
      [0x11A8, 0x1100], // ᆨ → ᄀ
      [0x11A9, 0x1101], // ᆩ → ᄁ
      [0x11AB, 0x1102], // ᆫ → ᄂ
      [0x11AE, 0x1103], // ᆮ → ᄃ
      [0x11AF, 0x1105], // ᆯ → ᄅ
      [0x11B7, 0x1106], // ᆷ → ᄆ
      [0x11B8, 0x1107], // ᆸ → ᄇ
      [0x11BA, 0x1109], // ᆺ → ᄉ
      [0x11BB, 0x110A], // ᆻ → ᄊ
      [0x11BC, 0x110B], // ᆼ → ᄋ
      [0x11BD, 0x110C], // ᆽ → ᄌ
      [0x11BE, 0x110E], // ᆾ → ᄎ
      [0x11BF, 0x110F], // ᆿ → ᄏ
      [0x11C0, 0x1110], // ᇀ → ᄐ
      [0x11C1, 0x1111], // ᇁ → ᄑ
      [0x11C2, 0x1112]  // ᇂ → ᄒ
    ];
    for (var i = 0; i < map.length; i++) {
      TAIL_TO_LEAD[map[i][0]] = map[i][1];
    }
  })();

  // Map compatibility vowels (U+314F–U+3163) to Hangul Jamo vowels (U+1161–U+1175)
  var COMPAT_VOWEL_TO_JAMO = {};
  (function() {
    // 21 vowels: ㅏ(314F)→ᅡ(1161), ㅐ(3150)→ᅢ(1162), ... ㅣ(3163)→ᅵ(1175)
    for (var v = 0; v < 21; v++) {
      COMPAT_VOWEL_TO_JAMO[0x314F + v] = 0x1161 + v;
    }
  })();

  // Normalize a jamo character to a canonical form for NW comparison.
  // Maps compatibility jamo and trailing jamo to leading/vowel jamo equivalents.
  function normalizeJamoForComparison(ch) {
    var code = ch.codePointAt(0);
    if (COMPAT_CONSONANT_TO_LEAD[code]) return String.fromCodePoint(COMPAT_CONSONANT_TO_LEAD[code]);
    if (TAIL_TO_LEAD[code]) return String.fromCodePoint(TAIL_TO_LEAD[code]);
    if (COMPAT_VOWEL_TO_JAMO[code]) return String.fromCodePoint(COMPAT_VOWEL_TO_JAMO[code]);
    return ch;
  }

  function isVietnameseLanguageCode(langValue) {
    var lang = String(langValue || "").trim().toLowerCase();
    return lang === "vi" || lang === "vietnamese" || lang.indexOf("vi-") === 0;
  }

  function languageUsesXposFilter(langValue) {
    return isKoreanLanguageCode(langValue);
  }

  function normalizeFilterXposTag(rawTag, langValue) {
    if (isKoreanLanguageCode(langValue)) return normalizeXposTag(rawTag);
    return String(rawTag || "").trim();
  }

  function isKoreanEngine(engine) {
    var lang = String((engine && engine._lang_code) || "").trim().toLowerCase();
    return isKoreanLanguageCode(lang);
  }

  function getKoreanDisplayOnlyEntries(engine, surface) {
    if (!isKoreanEngine(engine)) return [];
    var query = String(surface || "").trim();
    if (!query) return [];
    var fn = null;
    if (engine && typeof engine.lookup_display_only === "function") fn = engine.lookup_display_only;
    else if (engine && typeof engine.lookupDisplayOnly === "function") fn = engine.lookupDisplayOnly;
    if (!fn) return [];
    var out = fn.call(engine, query);
    if (!Array.isArray(out) || !out.length) return [];

    // Ensure display-only form-derived rows (notably eumhun) keep the full
    // form reading in UI while search still keys by stem/final character.
    var viaFn = null;
    if (engine && typeof engine.lookup_via_forms === "function") viaFn = engine.lookup_via_forms;
    else if (engine && typeof engine.lookupViaForms === "function") viaFn = engine.lookupViaForms;
    if (!viaFn) return out;

    var via = viaFn.call(engine, query);
    if (!Array.isArray(via) || !via.length) return out;

    var readingByKey = Object.create(null);
    for (var vi = 0; vi < via.length; vi++) {
      var vEntry = via[vi] || {};
      var vReading = String(vEntry.reading || "").trim();
      if (!vReading) continue;
      var vId = entryDebugIdentity(vEntry);
      var vLine = toDebugLineNo(vEntry.__line_no);
      var vKey = String(vLine || "") + "\t" + vId;
      if (!readingByKey[vKey] || vReading.length > String(readingByKey[vKey] || "").length) {
        readingByKey[vKey] = vReading;
      }
    }

    var enriched = [];
    for (var oi = 0; oi < out.length; oi++) {
      var src = out[oi] || {};
      var reading = String(src.reading || "").trim();
      var id = entryDebugIdentity(src);
      var line = toDebugLineNo(src.__line_no);
      var key = String(line || "") + "\t" + id;
      var mapped = String(readingByKey[key] || "").trim();
      if (mapped && mapped !== reading) {
        var clone = {};
        for (var k in src) {
          if (Object.prototype.hasOwnProperty.call(src, k)) clone[k] = src[k];
        }
        clone.reading = mapped;
        enriched.push(clone);
      } else {
        enriched.push(src);
      }
    }
    return enriched;
  }

  function mergeUniqueEntries(baseEntries, extraEntries) {
    var out = [];
    var seen = Object.create(null);
    function pushOne(entry) {
      if (!entry || typeof entry !== "object") return;
      var id = entryDebugIdentity(entry);
      var lineNo = toDebugLineNo(entry.__line_no);
      var key = String(lineNo || "") + "\t" + id;
      if (seen[key]) return;
      seen[key] = true;
      out.push(entry);
    }
    var base = Array.isArray(baseEntries) ? baseEntries : [];
    for (var i = 0; i < base.length; i++) pushOne(base[i]);
    var extra = Array.isArray(extraEntries) ? extraEntries : [];
    for (var j = 0; j < extra.length; j++) pushOne(extra[j]);
    return out;
  }

  function splitCompoundTags(raw) {
    var text = String(raw || "").trim();
    if (!text) return [];
    return text.split(COMPOUND_LEMMA_SPLIT_RE).map(function(part) { return part.trim(); }).filter(Boolean);
  }

  function normalizeCompoundParts(parts, normalizer) {
    var out = [];
    for (var i = 0; i < (parts || []).length; i++) {
      var raw = parts[i];
      var value = normalizer ? normalizer(raw) : String(raw || "").trim();
      if (!value) continue;
      out.push(value);
    }
    return out;
  }

  function uniqueNormalizedTags(parts, normalizer) {
    var out = [];
    var seen = Object.create(null);
    for (var i = 0; i < (parts || []).length; i++) {
      var raw = parts[i];
      var value = normalizer ? normalizer(raw) : String(raw || "").trim();
      if (!value || seen[value]) continue;
      seen[value] = true;
      out.push(value);
    }
    return out;
  }

  function mergeCompoundTags(rawA, rawB, normalizer) {
    var combined = [];
    var partsA = splitCompoundTags(rawA);
    var partsB = splitCompoundTags(rawB);
    for (var i = 0; i < partsA.length; i++) combined.push(partsA[i]);
    for (var j = 0; j < partsB.length; j++) combined.push(partsB[j]);
    return uniqueNormalizedTags(combined, normalizer).join('+');
  }

  function normalizeXposTag(rawTag) {
    var tag = String(rawTag || "").trim().toLowerCase();
    if (!tag) return "";
    // Handle parser artifacts like "ecs." / "jxc,".
    return tag.replace(/^[^a-z0-9_]+|[^a-z0-9_]+$/g, "");
  }

  function collectKoreanLemmaSpecificXposTags(lemmaHintObjects, lemmaOverrideParts, langOverride) {
    var activeLang = String((langOverride && langOverride._lang_code) || langOverride || getCurrentLanguage() || "").trim().toLowerCase();
    if (!isKoreanLanguageCode(activeLang)) return [];
    var out = [];
    var seen = Object.create(null);

    function pushRaw(raw) {
      var parts = splitCompoundTags(raw);
      if (!parts.length) {
        var single = String(raw || "").trim();
        if (single) parts = [single];
      }
      for (var i = 0; i < parts.length; i++) {
        var tag = normalizeXposTag(parts[i]);
        if (!tag || seen[tag]) continue;
        seen[tag] = true;
        out.push(tag);
      }
    }

    var overrideList = Array.isArray(lemmaOverrideParts) ? lemmaOverrideParts : [];
    for (var oi = 0; oi < overrideList.length; oi++) {
      var part = overrideList[oi] || {};
      pushRaw(part.xpos);
    }
    var hintList = Array.isArray(lemmaHintObjects) ? lemmaHintObjects : [];
    for (var hi = 0; hi < hintList.length; hi++) {
      var hint = hintList[hi] || {};
      pushRaw(hint.xpos);
    }
    return out;
  }

  function choosePreferredSenseFilterXpos(tokenXpos, lemmaHintObjects, lemmaOverrideParts, langOverride) {
    var activeLang = String((langOverride && langOverride._lang_code) || langOverride || getCurrentLanguage() || "").trim().toLowerCase();
    if (!isKoreanLanguageCode(activeLang)) return String(tokenXpos || "");
    var lemmaTags = collectKoreanLemmaSpecificXposTags(lemmaHintObjects, lemmaOverrideParts, activeLang);
    if (lemmaTags.length) return lemmaTags.join("+");
    return String(tokenXpos || "");
  }

  function formatUnicodeCodePoint(ch) {
    var text = String(ch || "");
    if (!text) return "";
    var code = text.codePointAt(0).toString(16).toUpperCase();
    while (code.length < 4) code = "0" + code;
    return "U+" + code;
  }

  function toUnicodeCodePointList(text) {
    var src = Array.from(String(text || ""));
    var out = [];
    for (var i = 0; i < src.length; i++) out.push(formatUnicodeCodePoint(src[i]));
    return out;
  }

  function decomposeTextToAlignmentUnits(text, langCode) {
    var src = Array.from(String(text || ""));
    var korean = isKoreanLanguageCode(langCode);
    var out = [];
    for (var i = 0; i < src.length; i++) {
      var ch = src[i];
      if (korean) {
        var jamo = decomposeHangulSyllable(ch);
        for (var ji = 0; ji < jamo.length; ji++) {
          out.push(normalizeJamoForComparison(jamo[ji]));
        }
      } else {
        var unitText = ch;
        var unitChars = Array.from(String(unitText || ""));
        if (!unitChars.length) unitChars = [ch];
        for (var ui = 0; ui < unitChars.length; ui++) out.push(unitChars[ui]);
      }
    }
    return out;
  }

  function buildSurfaceCodepointMap(text, langCode) {
    var src = Array.from(String(text || ""));
    var chars = [];
    var units = [];
    var unitToChar = [];
    var codeUnitOffset = 0;
    for (var i = 0; i < src.length; i++) {
      var ch = src[i];
      var unitChars = decomposeTextToAlignmentUnits(ch, langCode);
      if (!unitChars.length) unitChars = [ch];
      var startUnit = units.length;
      for (var ui = 0; ui < unitChars.length; ui++) {
        units.push(unitChars[ui]);
        unitToChar.push(i);
      }
      var offsetStart = codeUnitOffset;
      codeUnitOffset += ch.length;
      chars.push({
        index: i,
        offset_start: offsetStart,
        offset_end: codeUnitOffset,
        char: ch,
        unit_start: startUnit,
        unit_end: units.length,
        unit_text: unitChars.join(""),
        unit_codepoints: unitChars.map(formatUnicodeCodePoint)
      });
    }
    return {
      chars: chars,
      units: units,
      unit_to_char: unitToChar,
      text_length: String(text || "").length
    };
  }

  // Test whether a codepoint is a Unicode combining mark (Mn/Mc/Me) or a
  // zero-width character that cannot stand alone in a hover span.
  function _isZeroWidthOrCombining(ch) {
    var code = ch.codePointAt(0);
    if (code === 0x200B || code === 0x200C || code === 0x200D || code === 0xFEFF) return true; // ZWS, ZWNJ, ZWJ, BOM
    // Combining Diacritical Marks (U+0300–U+036F)
    if (code >= 0x0300 && code <= 0x036F) return true;
    // Combining Diacritical Marks Extended (U+1AB0–U+1AFF)
    if (code >= 0x1AB0 && code <= 0x1AFF) return true;
    // Combining Diacritical Marks Supplement (U+1DC0–U+1DFF)
    if (code >= 0x1DC0 && code <= 0x1DFF) return true;
    // Combining Diacritical Marks for Symbols (U+20D0–U+20FF)
    if (code >= 0x20D0 && code <= 0x20FF) return true;
    // Combining Half Marks (U+FE20–U+FE2F)
    if (code >= 0xFE20 && code <= 0xFE2F) return true;
    // Arabic combining marks (U+0610–U+061A, U+064B–U+065F, U+0670)
    if (code >= 0x0610 && code <= 0x061A) return true;
    if (code >= 0x064B && code <= 0x065F) return true;
    if (code === 0x0670) return true;
    // Hebrew points/marks (U+0591–U+05BD, U+05BF, U+05C1–U+05C2, U+05C4–U+05C5, U+05C7)
    if (code >= 0x0591 && code <= 0x05BD) return true;
    if (code === 0x05BF || code === 0x05C1 || code === 0x05C2 ||
        code === 0x05C4 || code === 0x05C5 || code === 0x05C7) return true;
    // Devanagari/Hindi combining marks (U+0900–U+0903, U+093A–U+094F, U+0951–U+0957, U+0962–U+0963)
    if (code >= 0x0900 && code <= 0x0903) return true;
    if (code >= 0x093A && code <= 0x094F) return true;
    if (code >= 0x0951 && code <= 0x0957) return true;
    if (code >= 0x0962 && code <= 0x0963) return true;
    // Thai combining marks (U+0E31, U+0E34–U+0E3A, U+0E47–U+0E4E)
    if (code === 0x0E31) return true;
    if (code >= 0x0E34 && code <= 0x0E3A) return true;
    if (code >= 0x0E47 && code <= 0x0E4E) return true;
    return false;
  }

  // Compute codepoint-unit overlap score between a lemma part and a set of
  // surface characters. Returns the count of shared decomposed units (bag
  // intersection). Used for fuzzy assignment of unplaced parts to gap chars.
  function _codepointOverlapScore(partUnits, surfaceCharUnits) {
    // Build bag (unit → count) from surface char units
    var bag = Object.create(null);
    for (var si = 0; si < surfaceCharUnits.length; si++) {
      var u = surfaceCharUnits[si];
      bag[u] = (bag[u] || 0) + 1;
    }
    var score = 0;
    for (var pi = 0; pi < partUnits.length; pi++) {
      var pu = partUnits[pi];
      if (bag[pu] && bag[pu] > 0) {
        score++;
        bag[pu]--;
      }
    }
    return score;
  }

  function buildGenericSurfacePartAlignment(surface, partTexts, opts) {
    var options = opts || {};
    var langCode = String(options.langCode || getCurrentLanguage() || "").toLowerCase();
    var normalizationLayer = getDictionaryNormalizationLayer();
    var debugTrace = !!options.debugTrace;
    var surfaceText = String(surface || "");
    if (!surfaceText) return null;
    var parts = Array.isArray(partTexts) ? partTexts.slice() : [];
    if (!parts.length) return null;

    var normalizedParts = [];
    for (var pi = 0; pi < parts.length; pi++) {
      var partText = String(parts[pi] || "");
      if (!partText) return null;
      normalizedParts.push(partText);
    }

    function clonePartIdList(rawIds) {
      var src = Array.isArray(rawIds) ? rawIds : [];
      var out = [];
      for (var i = 0; i < src.length; i++) {
        var pid = parseInt(src[i], 10);
        if (!isFinite(pid) || pid < 0) continue;
        out.push(pid);
      }
      return out;
    }

    function snapshotCharAssign(rawAssign, rawSurfaceChars) {
      var assign = Array.isArray(rawAssign) ? rawAssign : [];
      var chars = Array.isArray(rawSurfaceChars) ? rawSurfaceChars : [];
      var out = [];
      for (var i = 0; i < chars.length; i++) {
        var partIds = assign[i];
        out.push({
          char_index: i,
          char: String(chars[i] || ""),
          part_ids: Array.isArray(partIds) ? clonePartIdList(partIds) : []
        });
      }
      return out;
    }

    function cloneCodepointDebug(rawDebug) {
      if (!rawDebug || typeof rawDebug !== "object") return null;
      var out = {};
      var surfaceChars = Array.isArray(rawDebug.surface_chars) ? rawDebug.surface_chars : [];
      if (surfaceChars.length) {
        out.surface_chars = surfaceChars.map(function(row) {
          return {
            index: parseInt(row && row.index, 10) || 0,
            char: String((row && row.char) || ""),
            unit_start: parseInt(row && row.unit_start, 10) || 0,
            unit_end: parseInt(row && row.unit_end, 10) || 0,
            unit_text: String((row && row.unit_text) || ""),
            unit_codepoints: Array.isArray(row && row.unit_codepoints) ? row.unit_codepoints.slice() : []
          };
        });
      }
      var debugParts = Array.isArray(rawDebug.parts) ? rawDebug.parts : [];
      if (debugParts.length) {
        out.parts = debugParts.map(function(row) {
          return {
            part_id: parseInt(row && row.part_id, 10) || 0,
            text: String((row && row.text) || ""),
            unit_text: String((row && row.unit_text) || ""),
            unit_codepoints: Array.isArray(row && row.unit_codepoints) ? row.unit_codepoints.slice() : []
          };
        });
      }
      return out;
    }

    var runtimeDebug = debugTrace ? {
      surface_text: surfaceText,
      lang_code: langCode,
      normalized_parts: normalizedParts.slice(),
      anchor_state: {},
      unplaced_parts: [],
      gaps: [],
      char_assign_before_null_fill: [],
      char_assign_final: [],
      null_fill_steps: []
    } : null;

    function attachRuntimeAlignmentDebug(result) {
      if (!debugTrace || !runtimeDebug || !result || typeof result !== "object") return result;
      runtimeDebug.match_basis = String(result.match_basis || "");
      runtimeDebug.boundaries = Array.isArray(result.boundaries) ? result.boundaries.slice() : [];
      runtimeDebug.groups = Array.isArray(result.groups) ? result.groups.map(function(group) {
        return {
          start: parseInt(group && group.start, 10) || 0,
          end: parseInt(group && group.end, 10) || 0,
          part_ids: Array.isArray(group && group.part_ids) ? group.part_ids.slice() : [],
          part_count: parseInt(group && group.part_count, 10) || 0,
          unit_text: String((group && group.unit_text) || ""),
          unit_codepoints: Array.isArray(group && group.unit_codepoints) ? group.unit_codepoints.slice() : []
        };
      }) : [];
      runtimeDebug.codepoint_debug = cloneCodepointDebug(result.codepoint_debug);
      result._debug_runtime_alignment = runtimeDebug;
      return result;
    }

    function getAssignedPartSpan(partId, excludeStart, excludeEnd) {
      var spanStart = -1;
      var spanEnd = -1;
      for (var i = 0; i < numSurfChars; i++) {
        if (i >= excludeStart && i < excludeEnd) continue;
        var assignedIds = charAssign[i];
        if (!Array.isArray(assignedIds) || assignedIds.indexOf(partId) < 0) continue;
        if (spanStart < 0) spanStart = i;
        spanEnd = i + 1;
      }
      if (spanStart < 0 || spanEnd <= spanStart) return null;
      return {
        start: spanStart,
        end: spanEnd,
        length: spanEnd - spanStart,
        midpoint: (spanStart + spanEnd - 1) / 2
      };
    }

    function getNearestGapNeighborPartId(gapStart, gapEnd, direction) {
      var idx = direction < 0 ? gapStart - 1 : gapEnd;
      while (idx >= 0 && idx < numSurfChars) {
        var ids = charAssign[idx];
        if (Array.isArray(ids) && ids.length) {
          return direction < 0 ? ids[ids.length - 1] : ids[0];
        }
        idx += direction;
      }
      return -1;
    }

    function chooseSurfaceOnlyGapNeighborPartId(gapStart, gapEnd) {
      var leftNeighborId = getNearestGapNeighborPartId(gapStart, gapEnd, -1);
      var rightNeighborId = getNearestGapNeighborPartId(gapStart, gapEnd, 1);
      if (
        !(
          normalizationLayer &&
          typeof normalizationLayer.isArabicLanguageCode === "function" &&
          normalizationLayer.isArabicLanguageCode(langCode)
        )
      ) {
        return leftNeighborId >= 0 ? leftNeighborId : rightNeighborId;
      }

      var candidateIds = [];
      if (leftNeighborId >= 0) candidateIds.push(leftNeighborId);
      if (rightNeighborId >= 0 && rightNeighborId !== leftNeighborId) candidateIds.push(rightNeighborId);
      if (!candidateIds.length) return -1;
      if (candidateIds.length === 1) return candidateIds[0];

      var tokenMidpoint = (numSurfChars - 1) / 2;
      var bestId = candidateIds[0];
      var bestCenterDist = Infinity;
      var bestEdgePenalty = Infinity;
      var bestSpanLen = -1;
      for (var ci = 0; ci < candidateIds.length; ci++) {
        var candidateId = candidateIds[ci];
        var span = getAssignedPartSpan(candidateId, gapStart, gapEnd);
        var centerDist = span ? Math.abs(span.midpoint - tokenMidpoint) : Infinity;
        var edgePenalty = (candidateId === 0 || candidateId === normalizedParts.length - 1) ? 1 : 0;
        var spanLen = span ? span.length : 0;
        if (
          centerDist < bestCenterDist ||
          (centerDist === bestCenterDist && edgePenalty < bestEdgePenalty) ||
          (centerDist === bestCenterDist && edgePenalty === bestEdgePenalty && spanLen > bestSpanLen)
        ) {
          bestId = candidateId;
          bestCenterDist = centerDist;
          bestEdgePenalty = edgePenalty;
          bestSpanLen = spanLen;
        }
      }
      return bestId;
    }

    // Single part: trivially covers the whole surface, no alignment needed
    if (normalizedParts.length === 1) {
      return attachRuntimeAlignmentDebug({
        boundaries: [],
        groups: [{
          start: 0,
          end: surfaceText.length,
          part_ids: [0],
          part_count: 1
        }],
        match_basis: "single",
        codepoint_debug: null
      });
    }

    // --- Tier 1: exact concatenation match ---
    var joinedText = normalizedParts.join("");
    if (joinedText === surfaceText) {
      var exactGroups = [];
      var exactBounds = [];
      var exactCursor = 0;
      for (var ei = 0; ei < normalizedParts.length; ei++) {
        var nextCursor = exactCursor + normalizedParts[ei].length;
        exactGroups.push({
          start: exactCursor,
          end: nextCursor,
          part_ids: [ei],
          part_count: 1
        });
        exactCursor = nextCursor;
        if (ei < normalizedParts.length - 1) exactBounds.push(nextCursor);
      }
      return attachRuntimeAlignmentDebug({
        boundaries: exactBounds,
        groups: exactGroups,
        match_basis: "surface",
        codepoint_debug: null
      });
    }

    // --- Decompose surface and lemma parts into alignment units ---
    var surfaceMap = buildSurfaceCodepointMap(surfaceText, langCode);
    if (!surfaceMap.units.length) return null;

    // Build flat lemma units, each tagged with its part_id
    var lemmaUnits = [];
    var lemmaUnitPartId = [];
    for (var pj = 0; pj < normalizedParts.length; pj++) {
      var pUnits = decomposeTextToAlignmentUnits(normalizedParts[pj], langCode);
      for (var pu = 0; pu < pUnits.length; pu++) {
        lemmaUnits.push(pUnits[pu]);
        lemmaUnitPartId.push(pj);
      }
    }

    // Check if decomposed units match exactly
    if (surfaceMap.units.length === lemmaUnits.length) {
      var allMatch = true;
      for (var cm = 0; cm < surfaceMap.units.length; cm++) {
        if (surfaceMap.units[cm] !== lemmaUnits[cm]) { allMatch = false; break; }
      }
      if (allMatch) {
        return attachRuntimeAlignmentDebug(_buildGroupsFromUnitPartIds(surfaceMap, lemmaUnitPartId, normalizedParts, langCode, "codepoint"));
      }
    }

    // ===================================================================
    // Tier 2: Character-level anchor-and-residual alignment
    // ===================================================================
    // Work at the character level (Array.from). Anchor exact character
    // matches from both ends, then assign remaining surface chars to
    // remaining parts using codepoint-overlap scoring.
    //
    // Sub-character sharing (multiple parts → one surface char) is only
    // allowed for Korean, where Hangul syllable blocks can pack jamo from
    // different morphemes into a single Unicode character (e.g. 였 = 이+었).
    // All other languages get exactly one part per surface character.
    var allowSubCharSharing = isKoreanLanguageCode(langCode);

    var surfaceChars = Array.from(surfaceText);
    var numSurfChars = surfaceChars.length;

    // Decompose each part into its characters for character-level comparison.
    // Strip combining diacritics from lemma parts before comparison — lemmas
    // for Arabic/Hebrew often carry harakat/niqqud that are absent in surface text,
    // causing anchor failures (e.g. "فَوز" vs surface "فوز").
    var _stripFn = normalizationLayer && typeof normalizationLayer.stripLemmaAlignmentDiacritics === "function"
      ? normalizationLayer.stripLemmaAlignmentDiacritics : null;
    var partChars = [];
    for (var pc = 0; pc < normalizedParts.length; pc++) {
      var pcText = _stripFn ? _stripFn(normalizedParts[pc], langCode) : normalizedParts[pc];
      partChars.push(Array.from(pcText));
    }

    // charAssign[i] = array of part_ids assigned to surface char i, or null
    var charAssign = new Array(numSurfChars);
    for (var ca = 0; ca < numSurfChars; ca++) charAssign[ca] = null;
    var partPlaced = new Array(normalizedParts.length);
    for (var pp = 0; pp < normalizedParts.length; pp++) partPlaced[pp] = false;

    // --- Left-to-right greedy character anchoring ---
    // Walk surface chars and consume lemma parts character-by-character.
    // A part is anchored when ALL its characters match consecutively.
    var sCursor = 0;
    var pCursor = 0;
    while (sCursor < numSurfChars && pCursor < normalizedParts.length) {
      var pChars = partChars[pCursor];
      if (sCursor + pChars.length > numSurfChars) break;
      var matched = true;
      for (var lc = 0; lc < pChars.length; lc++) {
        if (surfaceChars[sCursor + lc] !== pChars[lc]) { matched = false; break; }
      }
      if (matched) {
        for (var la = 0; la < pChars.length; la++) {
          charAssign[sCursor + la] = [pCursor];
        }
        partPlaced[pCursor] = true;
        sCursor += pChars.length;
        pCursor++;
      } else {
        break;
      }
    }
    var leftAnchorEnd = pCursor; // first unplaced part from left pass

    // --- Right-to-left greedy character anchoring ---
    var sEnd = numSurfChars - 1;
    var pEnd = normalizedParts.length - 1;
    while (sEnd >= sCursor && pEnd >= leftAnchorEnd) {
      var rpChars = partChars[pEnd];
      var rStart = sEnd - rpChars.length + 1;
      if (rStart < sCursor) break;
      var rMatched = true;
      for (var rc = 0; rc < rpChars.length; rc++) {
        if (surfaceChars[rStart + rc] !== rpChars[rc]) { rMatched = false; break; }
      }
      if (rMatched) {
        for (var ra = 0; ra < rpChars.length; ra++) {
          charAssign[rStart + ra] = [pEnd];
        }
        partPlaced[pEnd] = true;
        sEnd -= rpChars.length;
        pEnd--;
      } else {
        break;
      }
    }
    if (runtimeDebug) {
      runtimeDebug.anchor_state = {
        left_anchor_end: leftAnchorEnd,
        right_anchor_start: pEnd + 1
      };
    }

    // --- Collect gaps: contiguous runs of unassigned surface chars ---
    // Each gap sits between anchored regions. The unplaced parts that
    // positionally fall within this gap are determined by ordering.
    var gaps = []; // {charStart, charEnd, partIds: [...]}
    var unplacedParts = [];
    for (var up = 0; up < normalizedParts.length; up++) {
      if (!partPlaced[up]) unplacedParts.push(up);
    }

    if (unplacedParts.length > 0) {
      // Find contiguous unassigned char runs
      var gapRuns = [];
      var gi = 0;
      while (gi < numSurfChars) {
        if (charAssign[gi] !== null) { gi++; continue; }
        var gStart = gi;
        while (gi < numSurfChars && charAssign[gi] === null) gi++;
        gapRuns.push({ charStart: gStart, charEnd: gi });
      }

      if (gapRuns.length === 0) {
        // All surface chars anchored but some parts unplaced.
        if (allowSubCharSharing) {
          // Korean: parts can share a surface char with their nearest neighbor.
          for (var ou = 0; ou < unplacedParts.length; ou++) {
            var orphanId = unplacedParts[ou];
            var bestChar = -1;
            var bestDist = Infinity;
            for (var bc = 0; bc < numSurfChars; bc++) {
              if (!charAssign[bc]) continue;
              for (var bci = 0; bci < charAssign[bc].length; bci++) {
                var dist = Math.abs(charAssign[bc][bci] - orphanId);
                if (dist < bestDist) { bestDist = dist; bestChar = bc; }
              }
            }
            if (bestChar >= 0) {
              if (charAssign[bestChar].indexOf(orphanId) < 0) {
                charAssign[bestChar].push(orphanId);
                charAssign[bestChar].sort(function(a, b) { return a - b; });
              }
            }
          }
        }
        // Non-Korean: no sharing allowed and no gap chars available.
        // Parts remain unplaced — they will be picked up by the safety
        // net in buildLemmaHintAlignmentState (orphan stitching).
      } else {
        // Distribute unplaced parts across gaps by positional order.
        // Each gap's parts are those whose part_id falls between the
        // anchored part_ids on either side of the gap.
        var upIdx = 0;
        for (var gri = 0; gri < gapRuns.length; gri++) {
          var gap = gapRuns[gri];
          // Find the bounding anchored part_ids
          var leftBound = -1;
          for (var lb = gap.charStart - 1; lb >= 0; lb--) {
            if (charAssign[lb]) { leftBound = Math.max.apply(null, charAssign[lb]); break; }
          }
          var rightBound = normalizedParts.length;
          for (var rb = gap.charEnd; rb < numSurfChars; rb++) {
            if (charAssign[rb]) { rightBound = Math.min.apply(null, charAssign[rb]); break; }
          }
          // Collect unplaced parts that belong in this gap
          var gapPartIds = [];
          while (upIdx < unplacedParts.length && unplacedParts[upIdx] > leftBound &&
                 unplacedParts[upIdx] < rightBound) {
            gapPartIds.push(unplacedParts[upIdx]);
            upIdx++;
          }
          gaps.push({
            charStart: gap.charStart,
            charEnd: gap.charEnd,
            partIds: gapPartIds
          });
        }
      }
    }
    if (runtimeDebug) {
      runtimeDebug.unplaced_parts = unplacedParts.slice();
      runtimeDebug.gaps = gaps.map(function(gap) {
        return {
          char_start: parseInt(gap && gap.charStart, 10) || 0,
          char_end: parseInt(gap && gap.charEnd, 10) || 0,
          part_ids: Array.isArray(gap && gap.partIds) ? gap.partIds.slice() : []
        };
      });
    }

    // --- Assign gap chars to gap parts ---
    // Strategy: proportional partition by lemma-part length, refined by
    // codepoint overlap scoring. Sub-character sharing (multiple parts on
    // one char) is Korean-only.
    for (var gfi = 0; gfi < gaps.length; gfi++) {
      var gapInfo = gaps[gfi];
      var gCharStart = gapInfo.charStart;
      var gCharEnd = gapInfo.charEnd;
      var gPartIds = gapInfo.partIds;
      var gNumChars = gCharEnd - gCharStart;

      if (gPartIds.length === 0) {
        // No unplaced parts for this gap — attach chars to a neighboring slice.
        // Arabic prefers the more central anchored slice over an edge clitic.
        var neighborId = chooseSurfaceOnlyGapNeighborPartId(gCharStart, gCharEnd);
        if (neighborId >= 0) {
          for (var na = gCharStart; na < gCharEnd; na++) {
            charAssign[na] = [neighborId];
          }
        }
        continue;
      }

      if (gNumChars === 0) {
        // Zero-width gap — attach parts to nearest anchored char (Korean
        // only; non-Korean parts left for orphan safety net)
        if (allowSubCharSharing) {
          var anchorChar = gCharStart > 0 ? gCharStart - 1 : gCharEnd < numSurfChars ? gCharEnd : 0;
          if (charAssign[anchorChar]) {
            for (var zp = 0; zp < gPartIds.length; zp++) {
              if (charAssign[anchorChar].indexOf(gPartIds[zp]) < 0) {
                charAssign[anchorChar].push(gPartIds[zp]);
              }
            }
            charAssign[anchorChar].sort(function(a, b) { return a - b; });
          }
        }
        continue;
      }

      if (gPartIds.length === 1) {
        // Single part gets all gap chars
        for (var sp2 = gCharStart; sp2 < gCharEnd; sp2++) {
          charAssign[sp2] = [gPartIds[0]];
        }
        continue;
      }

      if (gNumChars === 1 && allowSubCharSharing) {
        // Korean: single char gets all gap parts (they hover together)
        charAssign[gCharStart] = gPartIds.slice();
        continue;
      }

      // --- Proportional partition: divide gap chars among parts by
      // relative lemma-part length, then refine with codepoint overlap ---

      // Pre-compute decomposed units for each gap surface char and part
      var gapCharUnits = [];
      for (var gcu = gCharStart; gcu < gCharEnd; gcu++) {
        gapCharUnits.push(decomposeTextToAlignmentUnits(surfaceChars[gcu], langCode));
      }
      var gapPartUnits = [];
      var gapPartLengths = [];
      var totalPartLen = 0;
      for (var gpu = 0; gpu < gPartIds.length; gpu++) {
        var gpUnits = decomposeTextToAlignmentUnits(normalizedParts[gPartIds[gpu]], langCode);
        gapPartUnits.push(gpUnits);
        var gpLen = Array.from(normalizedParts[gPartIds[gpu]]).length;
        gapPartLengths.push(gpLen);
        totalPartLen += gpLen;
      }

      // Build proportional partition: assign each part a consecutive run
      // of gap chars proportional to its lemma length.
      // partRuns[i] = {start, end} (indices into gap, 0-based)
      var partRuns = new Array(gPartIds.length);
      var runCursor = 0;

      if (!allowSubCharSharing) {
        // Non-Korean: every part MUST get at least 1 char.
        // If more parts than chars, we cannot satisfy this — fall back to
        // giving each char to one part round-robin, extras get no char and
        // are left for the orphan safety net.
        if (gPartIds.length > gNumChars) {
          for (var rc2 = 0; rc2 < gNumChars; rc2++) {
            charAssign[gCharStart + rc2] = [gPartIds[rc2]];
          }
          // Remaining parts (gPartIds[gNumChars..]) have no chars — they
          // are left unassigned and will be picked up by orphan stitching.
          continue;
        }
        // Distribute with minimum 1 char per part
        for (var pr = 0; pr < gPartIds.length; pr++) {
          var propShare = gapPartLengths[pr] / (totalPartLen || 1);
          var runLen;
          if (pr === gPartIds.length - 1) {
            runLen = gNumChars - runCursor;
          } else {
            runLen = Math.max(1, Math.round(gNumChars * propShare));
            // Ensure enough chars remain for subsequent parts
            var remaining = gPartIds.length - pr - 1;
            if (runCursor + runLen > gNumChars - remaining) {
              runLen = gNumChars - remaining - runCursor;
            }
            if (runLen < 1) runLen = 1;
          }
          partRuns[pr] = { start: runCursor, end: runCursor + runLen };
          runCursor += runLen;
        }
      } else {
        // Korean: when enough chars, each part gets at least 1 char.
        // Only allow 0-width runs when more parts than chars (true merging).
        var korMinRun = gNumChars >= gPartIds.length ? 1 : 0;
        for (var pr2 = 0; pr2 < gPartIds.length; pr2++) {
          var propShare2 = gapPartLengths[pr2] / (totalPartLen || 1);
          var runLen2;
          if (pr2 === gPartIds.length - 1) {
            runLen2 = gNumChars - runCursor;
          } else {
            runLen2 = Math.max(korMinRun, Math.round(gNumChars * propShare2));
            var remaining2 = gPartIds.length - pr2 - 1;
            if (korMinRun > 0 && runCursor + runLen2 > gNumChars - remaining2) {
              runLen2 = gNumChars - remaining2 - runCursor;
            }
            if (runLen2 < korMinRun) runLen2 = korMinRun;
            if (runCursor + runLen2 > gNumChars) runLen2 = gNumChars - runCursor;
          }
          if (runLen2 < 0) runLen2 = 0;
          partRuns[pr2] = { start: runCursor, end: runCursor + runLen2 };
          runCursor += runLen2;
        }
      }

      // --- Refine boundaries using codepoint overlap scoring ---
      // Try shifting each boundary ±1 char and see if total overlap improves.
      // boundaries[i] = partRuns[i].end = partRuns[i+1].start (0-based gap index)
      var boundaries = new Array(gPartIds.length - 1);
      for (var bi = 0; bi < boundaries.length; bi++) {
        boundaries[bi] = partRuns[bi].end;
      }

      // Score a partition: sum of overlap(part, pooled units of its char run)
      var _scorePartition = function(bounds) {
        var total = 0;
        for (var sp3 = 0; sp3 < gPartIds.length; sp3++) {
          var rStart = sp3 === 0 ? 0 : bounds[sp3 - 1];
          var rEnd = sp3 < bounds.length ? bounds[sp3] : gNumChars;
          if (rEnd <= rStart) continue;
          // Pool all surface char units in this run
          var pooled = [];
          for (var pc2 = rStart; pc2 < rEnd; pc2++) {
            var units = gapCharUnits[pc2];
            for (var pu2 = 0; pu2 < units.length; pu2++) pooled.push(units[pu2]);
          }
          total += _codepointOverlapScore(gapPartUnits[sp3], pooled);
        }
        return total;
      };

      var bestBoundScore = _scorePartition(boundaries);
      var improved = true;
      // Min run size for boundary refinement: 1 char per part unless
      // Korean with genuinely more parts than chars (true sub-char merging)
      var minRunForRefine = (allowSubCharSharing && gNumChars < gPartIds.length) ? 0 : 1;
      // Iterate until no improvement (usually 1-2 passes for small gaps)
      while (improved) {
        improved = false;
        for (var bi2 = 0; bi2 < boundaries.length; bi2++) {
          // Try shifting this boundary left
          var leftMin = (bi2 > 0 ? boundaries[bi2 - 1] : 0) + minRunForRefine;
          if (boundaries[bi2] > leftMin) {
            var leftTry = boundaries.slice();
            leftTry[bi2]--;
            // Ensure the run to the right still has >= minRunForRefine chars
            var rightRunEnd = bi2 + 1 < boundaries.length ? leftTry[bi2 + 1] : gNumChars;
            if (rightRunEnd - leftTry[bi2] >= minRunForRefine) {
              var leftScore = _scorePartition(leftTry);
              if (leftScore > bestBoundScore) {
                boundaries = leftTry;
                bestBoundScore = leftScore;
                improved = true;
              }
            }
          }
          // Try shifting this boundary right
          var rightMax = (bi2 + 1 < boundaries.length ? boundaries[bi2 + 1] : gNumChars) - minRunForRefine;
          if (boundaries[bi2] < rightMax) {
            var rightTry = boundaries.slice();
            rightTry[bi2]++;
            // Ensure the run to the left still has >= minRunForRefine chars
            var leftRunStart = bi2 > 0 ? rightTry[bi2 - 1] : 0;
            if (rightTry[bi2] - leftRunStart >= minRunForRefine) {
              var rightScore = _scorePartition(rightTry);
              if (rightScore > bestBoundScore) {
                boundaries = rightTry;
                bestBoundScore = rightScore;
                improved = true;
              }
            }
          }
        }
      }

      // --- Assign chars to parts based on final partition ---
      for (var ai = 0; ai < gNumChars; ai++) {
        charAssign[gCharStart + ai] = [];
      }
      for (var fp3 = 0; fp3 < gPartIds.length; fp3++) {
        var fStart = fp3 === 0 ? 0 : boundaries[fp3 - 1];
        var fEnd = fp3 < boundaries.length ? boundaries[fp3] : gNumChars;
        for (var fc = fStart; fc < fEnd; fc++) {
          charAssign[gCharStart + fc].push(gPartIds[fp3]);
        }
      }

      // --- Korean only: spillover sharing ---
      // If a part also has codepoint overlap with chars in an adjacent
      // run, add it to those chars so they hover together.
      if (allowSubCharSharing) {
        for (var sp4 = 0; sp4 < gPartIds.length; sp4++) {
          var spStart = sp4 === 0 ? 0 : boundaries[sp4 - 1];
          var spEnd = sp4 < boundaries.length ? boundaries[sp4] : gNumChars;
          var currentRunLen = spEnd - spStart;
          var maxLen = gapPartLengths[sp4]; // cap reach at lemma char length
          if (currentRunLen >= maxLen) continue; // already at capacity
          // Check chars just outside this part's run
          // Left spillover: char at spStart-1
          if (spStart > 0) {
            var leftOverlap = _codepointOverlapScore(gapPartUnits[sp4], gapCharUnits[spStart - 1]);
            if (leftOverlap > 0 && charAssign[gCharStart + spStart - 1].indexOf(gPartIds[sp4]) < 0) {
              charAssign[gCharStart + spStart - 1].push(gPartIds[sp4]);
              charAssign[gCharStart + spStart - 1].sort(function(a, b) { return a - b; });
            }
          }
          // Right spillover: char at spEnd
          if (spEnd < gNumChars) {
            var rightOverlap = _codepointOverlapScore(gapPartUnits[sp4], gapCharUnits[spEnd]);
            if (rightOverlap > 0 && charAssign[gCharStart + spEnd].indexOf(gPartIds[sp4]) < 0) {
              charAssign[gCharStart + spEnd].push(gPartIds[sp4]);
              charAssign[gCharStart + spEnd].sort(function(a, b) { return a - b; });
            }
          }
        }
      }

      // Handle any gap chars that still got no parts (empty run in Korean)
      for (var fx = 0; fx < gNumChars; fx++) {
        if (charAssign[gCharStart + fx].length > 0) continue;
        var foundIds = null;
        for (var fl = fx - 1; fl >= 0; fl--) {
          if (charAssign[gCharStart + fl].length > 0) {
            foundIds = charAssign[gCharStart + fl];
            break;
          }
        }
        if (!foundIds) {
          for (var fr = fx + 1; fr < gNumChars; fr++) {
            if (charAssign[gCharStart + fr].length > 0) {
              foundIds = charAssign[gCharStart + fr];
              break;
            }
          }
        }
        if (foundIds) {
          charAssign[gCharStart + fx] = [foundIds[foundIds.length - 1]];
        }
      }
    }

    // --- Post-process: merge combining/zero-width chars into neighbors ---
    for (var zw = 0; zw < numSurfChars; zw++) {
      if (!_isZeroWidthOrCombining(surfaceChars[zw])) continue;
      // Find a host: prefer preceding char, then following
      var host = -1;
      if (zw > 0 && charAssign[zw - 1]) host = zw - 1;
      else if (zw + 1 < numSurfChars && charAssign[zw + 1]) host = zw + 1;
      if (host >= 0 && charAssign[host]) {
        charAssign[zw] = charAssign[host].slice();
      }
    }

    // --- Handle any still-null chars (safety) ---
    if (runtimeDebug) runtimeDebug.char_assign_before_null_fill = snapshotCharAssign(charAssign, surfaceChars);
    for (var sn = 0; sn < numSurfChars; sn++) {
      if (charAssign[sn] !== null && charAssign[sn].length > 0) continue;
      // Propagate from left
      if (sn > 0 && charAssign[sn - 1] && charAssign[sn - 1].length > 0) {
        charAssign[sn] = charAssign[sn - 1].slice();
        if (runtimeDebug) {
          runtimeDebug.null_fill_steps.push({
            char_index: sn,
            char: String(surfaceChars[sn] || ""),
            source: "left",
            from_index: sn - 1,
            part_ids: clonePartIdList(charAssign[sn])
          });
        }
      }
    }
    for (var sn2 = numSurfChars - 1; sn2 >= 0; sn2--) {
      if (charAssign[sn2] !== null && charAssign[sn2].length > 0) continue;
      if (sn2 + 1 < numSurfChars && charAssign[sn2 + 1] && charAssign[sn2 + 1].length > 0) {
        charAssign[sn2] = charAssign[sn2 + 1].slice();
        if (runtimeDebug) {
          runtimeDebug.null_fill_steps.push({
            char_index: sn2,
            char: String(surfaceChars[sn2] || ""),
            source: "right",
            from_index: sn2 + 1,
            part_ids: clonePartIdList(charAssign[sn2])
          });
        }
      }
    }
    if (runtimeDebug) runtimeDebug.char_assign_final = snapshotCharAssign(charAssign, surfaceChars);

    // If nothing could be assigned at all, fall back to proportional
    var anyAssigned = false;
    for (var chk = 0; chk < numSurfChars; chk++) {
      if (charAssign[chk] && charAssign[chk].length > 0) { anyAssigned = true; break; }
    }
    if (!anyAssigned) {
      return attachRuntimeAlignmentDebug(_buildProportionalAlignment(surfaceMap, normalizedParts, langCode));
    }

    // --- Build unit-level part_id array for _buildGroupsFromUnitPartIds ---
    // For each surface unit, take the part_ids of its parent character.
    // When a char has multiple part_ids, all its units get all those ids;
    // _buildGroupsFromUnitPartIds already handles multi-id chars by merging
    // them into groups with multiple part_ids.
    var unitPartIds = new Array(surfaceMap.units.length);
    for (var ub = 0; ub < surfaceMap.units.length; ub++) unitPartIds[ub] = -1;
    for (var ci2 = 0; ci2 < surfaceMap.chars.length; ci2++) {
      var charRow = surfaceMap.chars[ci2];
      var ids = charAssign[ci2];
      if (!ids || !ids.length) continue;
      // Use the first part_id as the primary for the unit array;
      // _buildGroupsFromUnitPartIds collects all part_ids per char via
      // the unit range, so we write each unit once per part_id by using
      // a per-char sweep in that function. But that function reads one
      // part_id per unit. To support multi-part chars we need to tag
      // units. Use a negative encoding? No — _buildGroupsFromUnitPartIds
      // already iterates unit_start..unit_end and collects unique pids.
      // We just need at least one unit per part_id to be tagged.
      // Distribute part_ids round-robin across units; if fewer units
      // than parts, tag the first unit with each part_id by writing
      // them all (the function dedupes).
      var numUnits = charRow.unit_end - charRow.unit_start;
      if (ids.length === 1) {
        for (var uw = charRow.unit_start; uw < charRow.unit_end; uw++) {
          unitPartIds[uw] = ids[0];
        }
      } else {
        // Multi-part char: we need _buildGroupsFromUnitPartIds to see all
        // part_ids. That function collects unique pids from each unit in
        // the char's range. So we distribute them: each unit gets one pid,
        // cycling through the ids. If numUnits < ids.length, some units
        // carry multiple — but the function only reads one per slot.
        // Instead, write each part_id to at least one unit.
        if (numUnits >= ids.length) {
          var idSlot = 0;
          for (var uw2 = charRow.unit_start; uw2 < charRow.unit_end; uw2++) {
            unitPartIds[uw2] = ids[idSlot % ids.length];
            idSlot++;
          }
        } else {
          // Fewer units than part_ids: we can only tag each unit with one
          // pid. The remaining pids won't be seen. To fix this, we augment
          // _buildGroupsFromUnitPartIds by passing extra info. But to avoid
          // changing that function, use a different approach: build the
          // charPartIds array directly and skip _buildGroupsFromUnitPartIds.
          // For now, tag what we can — we'll do a direct build below.
          for (var uw3 = charRow.unit_start; uw3 < charRow.unit_end; uw3++) {
            unitPartIds[uw3] = ids[Math.min(uw3 - charRow.unit_start, ids.length - 1)];
          }
        }
      }
    }

    // Check if any char has more part_ids than units — if so, the unit-level
    // approach can't represent all part_ids. Build groups directly from
    // charAssign instead.
    var needDirectBuild = false;
    for (var db = 0; db < surfaceMap.chars.length; db++) {
      var dbIds = charAssign[db];
      var dbRow = surfaceMap.chars[db];
      if (dbIds && dbIds.length > (dbRow.unit_end - dbRow.unit_start)) {
        needDirectBuild = true;
        break;
      }
    }

    if (needDirectBuild) {
      // Build groups directly from charAssign, same logic as
      // _buildGroupsFromUnitPartIds but reading from charAssign.
      var dGroups = [];
      var dBoundaries = [];
      var dGroupStart = 0;
      for (var dg = 0; dg < numSurfChars; dg++) {
        var sameAsPrev = false;
        if (dg > 0) {
          var prevIds = charAssign[dg - 1] || [];
          var currIds = charAssign[dg] || [];
          if (prevIds.length === currIds.length) {
            sameAsPrev = true;
            for (var dcmp = 0; dcmp < prevIds.length; dcmp++) {
              if (prevIds[dcmp] !== currIds[dcmp]) { sameAsPrev = false; break; }
            }
          }
        }
        if (!sameAsPrev && dg > 0) {
          var dpChar = surfaceMap.chars[dg - 1];
          var dsChar = surfaceMap.chars[dGroupStart];
          var dUnitText = surfaceMap.units.slice(dsChar.unit_start, dpChar.unit_end).join("");
          dGroups.push({
            start: dsChar.offset_start,
            end: dpChar.offset_end,
            part_ids: (charAssign[dg - 1] || []).slice(),
            part_count: (charAssign[dg - 1] || []).length,
            unit_start: dsChar.unit_start,
            unit_end: dpChar.unit_end,
            unit_text: dUnitText,
            unit_codepoints: toUnicodeCodePointList(dUnitText)
          });
          dBoundaries.push(dpChar.offset_end);
          dGroupStart = dg;
        }
      }
      // Close final group
      if (numSurfChars > 0) {
        var dlChar = surfaceMap.chars[numSurfChars - 1];
        var dfChar = surfaceMap.chars[dGroupStart];
        var dlUnitText = surfaceMap.units.slice(dfChar.unit_start, dlChar.unit_end).join("");
        dGroups.push({
          start: dfChar.offset_start,
          end: dlChar.offset_end,
          part_ids: (charAssign[numSurfChars - 1] || []).slice(),
          part_count: (charAssign[numSurfChars - 1] || []).length,
          unit_start: dfChar.unit_start,
          unit_end: dlChar.unit_end,
          unit_text: dlUnitText,
          unit_codepoints: toUnicodeCodePointList(dlUnitText)
        });
      }

      return attachRuntimeAlignmentDebug({
        boundaries: dBoundaries,
        groups: dGroups,
        match_basis: "anchor_codepoint",
        codepoint_debug: {
          surface_chars: surfaceMap.chars.map(function(row) {
            return {
              index: row.index,
              char: row.char,
              unit_start: row.unit_start,
              unit_end: row.unit_end,
              unit_text: row.unit_text,
              unit_codepoints: Array.isArray(row.unit_codepoints) ? row.unit_codepoints.slice() : []
            };
          }),
          parts: normalizedParts.map(function(pt, idx) {
            var uText = decomposeTextToAlignmentUnits(pt, langCode).join("");
            return {
              part_id: idx,
              text: pt,
              unit_text: uText,
              unit_codepoints: toUnicodeCodePointList(uText)
            };
          })
        }
      });
    }

    return attachRuntimeAlignmentDebug(_buildGroupsFromUnitPartIds(surfaceMap, unitPartIds, normalizedParts, langCode, "anchor_codepoint"));
  }

  // Build groups from per-unit part assignments, snapping boundaries to whole
  // surface characters.
  function _buildGroupsFromUnitPartIds(surfaceMap, unitPartIds, normalizedParts, langCode, matchBasis) {
    // For each surface character, collect all part_ids its units belong to
    var charPartIds = []; // array of arrays
    for (var ci = 0; ci < surfaceMap.chars.length; ci++) {
      var charRow = surfaceMap.chars[ci];
      var ids = [];
      var idSeen = Object.create(null);
      for (var cu = charRow.unit_start; cu < charRow.unit_end; cu++) {
        var pid = unitPartIds[cu];
        if (pid >= 0 && !idSeen[pid]) {
          idSeen[pid] = true;
          ids.push(pid);
        }
      }
      // Sort part_ids for consistent comparison
      ids.sort(function(a, b) { return a - b; });
      charPartIds.push(ids);
    }

    // Merge consecutive characters with identical part_id sets into groups
    var groups = [];
    var boundaries = [];
    var groupStart = 0;
    for (var gi = 0; gi < charPartIds.length; gi++) {
      var sameAsPrev = false;
      if (gi > 0) {
        var prev = charPartIds[gi - 1];
        var curr = charPartIds[gi];
        if (prev.length === curr.length) {
          sameAsPrev = true;
          for (var cmp = 0; cmp < prev.length; cmp++) {
            if (prev[cmp] !== curr[cmp]) { sameAsPrev = false; break; }
          }
        }
      }
      if (!sameAsPrev && gi > 0) {
        // Close previous group
        var prevChar = surfaceMap.chars[gi - 1];
        var startChar = surfaceMap.chars[groupStart];
        var unitText = surfaceMap.units.slice(startChar.unit_start, prevChar.unit_end).join("");
        groups.push({
          start: startChar.offset_start,
          end: prevChar.offset_end,
          part_ids: charPartIds[gi - 1].slice(),
          part_count: charPartIds[gi - 1].length,
          unit_start: startChar.unit_start,
          unit_end: prevChar.unit_end,
          unit_text: unitText,
          unit_codepoints: toUnicodeCodePointList(unitText)
        });
        boundaries.push(prevChar.offset_end);
        groupStart = gi;
      }
    }
    // Close final group
    if (surfaceMap.chars.length > 0) {
      var lastChar = surfaceMap.chars[surfaceMap.chars.length - 1];
      var firstChar = surfaceMap.chars[groupStart];
      var lastUnitText = surfaceMap.units.slice(firstChar.unit_start, lastChar.unit_end).join("");
      groups.push({
        start: firstChar.offset_start,
        end: lastChar.offset_end,
        part_ids: charPartIds[charPartIds.length - 1].slice(),
        part_count: charPartIds[charPartIds.length - 1].length,
        unit_start: firstChar.unit_start,
        unit_end: lastChar.unit_end,
        unit_text: lastUnitText,
        unit_codepoints: toUnicodeCodePointList(lastUnitText)
      });
    }

    return {
      boundaries: boundaries,
      groups: groups,
      match_basis: matchBasis || "codepoint",
      codepoint_debug: {
        surface_chars: surfaceMap.chars.map(function(row) {
          return {
            index: row.index,
            char: row.char,
            unit_start: row.unit_start,
            unit_end: row.unit_end,
            unit_text: row.unit_text,
            unit_codepoints: Array.isArray(row.unit_codepoints) ? row.unit_codepoints.slice() : []
          };
        }),
        parts: normalizedParts.map(function(pt, idx) {
          var uText = decomposeTextToAlignmentUnits(pt, langCode).join("");
          return {
            part_id: idx,
            text: pt,
            unit_text: uText,
            unit_codepoints: toUnicodeCodePointList(uText)
          };
        })
      }
    };
  }

  // Tier 3 fallback: split surface proportionally by lemma part lengths,
  // snapping to character boundaries. Never returns null.
  function _buildProportionalAlignment(surfaceMap, normalizedParts, langCode) {
    var totalLemmaLen = 0;
    for (var tl = 0; tl < normalizedParts.length; tl++) {
      totalLemmaLen += normalizedParts[tl].length;
    }
    var numChars = surfaceMap.chars.length;
    var unitPartIds = new Array(surfaceMap.units.length);

    // Assign each character to a part proportionally
    var charCursor = 0;
    for (var pp = 0; pp < normalizedParts.length; pp++) {
      var share = normalizedParts[pp].length;
      var charCount;
      if (pp === normalizedParts.length - 1) {
        charCount = numChars - charCursor;
      } else {
        charCount = Math.max(1, Math.round(numChars * share / (totalLemmaLen || 1)));
        if (charCursor + charCount > numChars) charCount = numChars - charCursor;
      }
      // Assign all units of these characters to this part
      for (var ac = charCursor; ac < charCursor + charCount && ac < numChars; ac++) {
        var charRow = surfaceMap.chars[ac];
        for (var au = charRow.unit_start; au < charRow.unit_end; au++) {
          unitPartIds[au] = pp;
        }
      }
      charCursor += charCount;
    }

    // Fill any remaining unassigned units (shouldn't happen, but safety)
    var lastPart = normalizedParts.length - 1;
    for (var fu = 0; fu < unitPartIds.length; fu++) {
      if (unitPartIds[fu] === undefined || unitPartIds[fu] < 0) {
        unitPartIds[fu] = lastPart;
      }
    }

    return _buildGroupsFromUnitPartIds(surfaceMap, unitPartIds, normalizedParts, langCode, "proportional");
  }

  function buildKoreanLemmaXposAlignment(surface, lemma, xpos, langOverride) {
    var activeLang = String(langOverride || getCurrentLanguage() || "").toLowerCase();
    if (!isKoreanLanguageCode(activeLang)) return null;
    var surfaceText = String(surface || "").trim();
    if (!surfaceText) return null;
    var lemmaParts = normalizeCompoundParts(splitCompoundTags(lemma), function(part) {
      return String(part || "").trim();
    });
    var xposParts = normalizeCompoundParts(splitCompoundTags(xpos), normalizeXposTag);
    if (!lemmaParts.length || !xposParts.length) return null;
    // Single-part lemmas should not constrain greedy decomposition. The Korean
    // grouping/filter rules only apply when Trankit gives an actual multi-part
    // lemma/XPOS analysis.
    if (lemmaParts.length <= 1) return null;
    var sharedXposGuard = lemmaParts.length !== xposParts.length;
    var sharedXposTags = uniqueNormalizedTags(xposParts, normalizeXposTag);

    function normalizedPartIds(partIds) {
      var ids = [];
      var idSeen = Object.create(null);
      for (var pi = 0; pi < (partIds || []).length; pi++) {
        var rawId = parseInt(partIds[pi], 10);
        if (!isFinite(rawId) || rawId < 0 || rawId >= lemmaParts.length || idSeen[rawId]) continue;
        idSeen[rawId] = true;
        ids.push(rawId);
      }
      return ids;
    }

    function xposTagsForPartIds(partIds) {
      var ids = normalizedPartIds(partIds);
      if (!ids.length) return null;
      if (sharedXposGuard) {
        return {
          ids: ids,
          tags: sharedXposTags.slice()
        };
      }
      var tags = [];
      for (var ti = 0; ti < ids.length; ti++) tags.push(xposParts[ids[ti]]);
      return {
        ids: ids,
        tags: uniqueNormalizedTags(tags, normalizeXposTag)
      };
    }

    var baseAlignment = buildGenericSurfacePartAlignment(surfaceText, lemmaParts, {
      langCode: activeLang,
      literalFallbackReason: "syllable-fallback"
    });
    if (!baseAlignment || !baseAlignment.groups || !baseAlignment.groups.length) return null;

    var groups = [];
    for (var gi = 0; gi < baseAlignment.groups.length; gi++) {
      var baseGroup = baseAlignment.groups[gi] || {};
      var meta = xposTagsForPartIds(baseGroup.part_ids || []);
      if (!meta) return null;
      groups.push(Object.assign({}, baseGroup, {
        xpos_tags: meta.tags,
        part_ids: meta.ids,
        part_count: meta.ids.length,
        shared_xpos_guard: sharedXposGuard,
        unit_codepoints: Array.isArray(baseGroup.unit_codepoints) ? baseGroup.unit_codepoints.slice() : []
      }));
    }

    var codepointDebug = null;
    if (baseAlignment.codepoint_debug && typeof baseAlignment.codepoint_debug === "object") {
      var debugParts = Array.isArray(baseAlignment.codepoint_debug.parts) ? baseAlignment.codepoint_debug.parts : [];
      codepointDebug = {
        shared_xpos_guard: sharedXposGuard,
        shared_xpos_tags: sharedXposTags.slice(),
        surface_chars: Array.isArray(baseAlignment.codepoint_debug.surface_chars)
          ? baseAlignment.codepoint_debug.surface_chars.slice()
          : [],
        lemma_parts: debugParts.map(function(row, idx) {
          return {
            part_id: idx,
            text: lemmaParts[idx],
            xpos: xposParts[idx] || "",
            unit_text: String((row && row.unit_text) || ""),
            unit_codepoints: Array.isArray(row && row.unit_codepoints) ? row.unit_codepoints.slice() : []
          };
        })
      };
    }

    return {
      boundaries: Array.isArray(baseAlignment.boundaries) ? baseAlignment.boundaries.slice() : [],
      groups: groups,
      match_basis: String(baseAlignment.match_basis || ""),
      shared_xpos_guard: sharedXposGuard,
      codepoint_debug: codepointDebug
    };
  }

  function buildDebugLemmaAlignment(surface, lemma, xpos, langOverride) {
    var activeLang = String(langOverride || getCurrentLanguage() || "").toLowerCase();
    var surfaceText = String(surface || "").trim();
    if (!surfaceText) return null;
    var lemmaParts = normalizeCompoundParts(splitCompoundTags(lemma), function(part) {
      return String(part || "").trim();
    });
    if (!lemmaParts.length) return null;
    // Single-part lemma: the whole surface maps to it, no alignment needed
    if (lemmaParts.length <= 1) return null;

    function normalizeDebugXposTag(rawTag) {
      return normalizeFilterXposTag(rawTag, activeLang);
    }

    var xposParts = normalizeCompoundParts(splitCompoundTags(xpos), normalizeDebugXposTag);
    var sharedXposGuard = xposParts.length > 0 && lemmaParts.length !== xposParts.length;
    var sharedXposTags = uniqueNormalizedTags(xposParts, normalizeDebugXposTag);

    function normalizedPartIds(partIds) {
      var ids = [];
      var seen = Object.create(null);
      for (var pi = 0; pi < (partIds || []).length; pi++) {
        var rawId = parseInt(partIds[pi], 10);
        if (!isFinite(rawId) || rawId < 0 || rawId >= lemmaParts.length || seen[rawId]) continue;
        seen[rawId] = true;
        ids.push(rawId);
      }
      return ids;
    }

    function xposTagsForPartIds(partIds) {
      var ids = normalizedPartIds(partIds);
      if (!ids.length) return [];
      if (!xposParts.length) return [];
      if (sharedXposGuard) return sharedXposTags.slice();
      var tags = [];
      for (var ti = 0; ti < ids.length; ti++) {
        var tag = String(xposParts[ids[ti]] || "").trim();
        if (tag) tags.push(tag);
      }
      return uniqueNormalizedTags(tags, normalizeDebugXposTag);
    }

    var baseAlignment = buildGenericSurfacePartAlignment(surfaceText, lemmaParts, {
      langCode: activeLang,
      literalFallbackReason: "literal-fallback"
    });
    if (!baseAlignment || !Array.isArray(baseAlignment.groups) || !baseAlignment.groups.length) return null;

    var groups = [];
    for (var gi = 0; gi < baseAlignment.groups.length; gi++) {
      var baseGroup = baseAlignment.groups[gi] || {};
      var partIds = normalizedPartIds(baseGroup.part_ids || []);
      groups.push(Object.assign({}, baseGroup, {
        part_ids: partIds,
        part_count: partIds.length,
        xpos_tags: xposTagsForPartIds(partIds),
        shared_xpos_guard: sharedXposGuard,
        unit_codepoints: Array.isArray(baseGroup.unit_codepoints) ? baseGroup.unit_codepoints.slice() : []
      }));
    }

    var codepointDebug = null;
    if (baseAlignment.codepoint_debug && typeof baseAlignment.codepoint_debug === "object") {
      var debugParts = Array.isArray(baseAlignment.codepoint_debug.parts) ? baseAlignment.codepoint_debug.parts : [];
      codepointDebug = {
        shared_xpos_guard: sharedXposGuard,
        shared_xpos_tags: sharedXposTags.slice(),
        surface_chars: Array.isArray(baseAlignment.codepoint_debug.surface_chars)
          ? baseAlignment.codepoint_debug.surface_chars.slice()
          : [],
        lemma_parts: debugParts.map(function(row, idx) {
          return {
            part_id: idx,
            text: lemmaParts[idx],
            xpos: xposParts[idx] || "",
            unit_text: String((row && row.unit_text) || ""),
            unit_codepoints: Array.isArray(row && row.unit_codepoints) ? row.unit_codepoints.slice() : []
          };
        })
      };
    }

    return {
      boundaries: Array.isArray(baseAlignment.boundaries) ? baseAlignment.boundaries.slice() : [],
      groups: groups,
      match_basis: String(baseAlignment.match_basis || ""),
      shared_xpos_guard: sharedXposGuard,
      codepoint_debug: codepointDebug
    };
  }

  function getFillPieceSurfaceText(fillEntry) {
    if (!fillEntry || typeof fillEntry !== "object") return "";
    if (fillEntry.text != null) return String(fillEntry.text);
    if (fillEntry.head != null) return String(fillEntry.head);
    return "";
  }

  function buildLocalizedMwtPartRows(rows, fillIndexes, partStart, partEnd) {
    var srcRows = Array.isArray(rows) ? rows : [];
    var srcIndexes = Array.isArray(fillIndexes) ? fillIndexes : [];
    var localizedRows = [];
    var globalIndexes = [];

    for (var i = 0; i < srcIndexes.length; i++) {
      var globalIdx = parseInt(srcIndexes[i], 10);
      if (!isFinite(globalIdx) || globalIdx < 0 || globalIdx >= srcRows.length) continue;
      var row = srcRows[globalIdx] || {};
      var clone = {};
      for (var key in row) {
        if (Object.prototype.hasOwnProperty.call(row, key)) clone[key] = row[key];
      }
      var rowStart = parseInt(row._surface_start, 10);
      var rowEnd = parseInt(row._surface_end, 10);
      if (
        isFinite(rowStart) &&
        isFinite(rowEnd) &&
        rowEnd > rowStart &&
        rowStart >= partStart &&
        rowEnd <= partEnd
      ) {
        clone._surface_start = rowStart - partStart;
        clone._surface_end = rowEnd - partStart;
      } else {
        if (Object.prototype.hasOwnProperty.call(clone, "_surface_start")) delete clone._surface_start;
        if (Object.prototype.hasOwnProperty.call(clone, "_surface_end")) delete clone._surface_end;
      }
      localizedRows.push(clone);
      globalIndexes.push(globalIdx);
    }

    return {
      rows: localizedRows,
      global_indexes: globalIndexes
    };
  }

  function remapLocalizedMwtPartSlices(localSlices, globalIndexes, partStart) {
    var slices = Array.isArray(localSlices) ? localSlices : [];
    var mappedIndexes = Array.isArray(globalIndexes) ? globalIndexes : [];
    var out = [];

    for (var i = 0; i < slices.length; i++) {
      var localSlice = slices[i] || {};
      var start = parseInt(localSlice.start, 10);
      var end = parseInt(localSlice.end, 10);
      if (!isFinite(start) || !isFinite(end) || end <= start) continue;
      var rawIds = Array.isArray(localSlice.fill_indexes)
        ? localSlice.fill_indexes
        : (Array.isArray(localSlice.fillIndexes) ? localSlice.fillIndexes : []);
      var fillIndexes = [];
      var seen = Object.create(null);
      for (var j = 0; j < rawIds.length; j++) {
        var localIdx = parseInt(rawIds[j], 10);
        if (!isFinite(localIdx) || localIdx < 0 || localIdx >= mappedIndexes.length) continue;
        var globalIdx = mappedIndexes[localIdx];
        if (!isFinite(globalIdx) || globalIdx < 0 || seen[globalIdx]) continue;
        seen[globalIdx] = true;
        fillIndexes.push(globalIdx);
      }
      if (!fillIndexes.length) continue;
      out.push({
        start: partStart + start,
        end: partStart + end,
        fill_indexes: fillIndexes
      });
    }

    return out;
  }

  function collectSyntheticSliceEntries(rows) {
    var src = Array.isArray(rows) ? rows : [];
    var out = [];
    var seen = Object.create(null);

    for (var i = 0; i < src.length; i++) {
      var row = src[i] || {};
      var rowEntries = Array.isArray(row.entries) ? row.entries : [];
      if (!rowEntries.length && row._winner_ref) rowEntries = [row._winner_ref];

      for (var ei = 0; ei < rowEntries.length; ei++) {
        var entry = rowEntries[ei];
        if (!entry) continue;
        var key = getBundledEntryKey(entry) || ("anon|" + i + "|" + ei);
        if (seen[key]) continue;
        seen[key] = 1;
        out.push(entry);
      }
    }

    return out;
  }

  function buildSyntheticMwtChildSliceRow(surfaceText, groupedRows) {
    var rows = Array.isArray(groupedRows) ? groupedRows : [];
    var base = rows.length ? rows[0] : {};
    var out = {};

    for (var key in base) {
      if (Object.prototype.hasOwnProperty.call(base, key)) out[key] = base[key];
    }

    var groupedEntries = collectSyntheticSliceEntries(rows);

    out.text = String(surfaceText || "");
    out.surface_form = String(surfaceText || "");
    out.entries = groupedEntries;

    // If this synthetic slice is really just one original piece row,
    // preserve the original compact winner ref too.
    if (rows.length === 1 && rows[0] && rows[0]._winner_ref) {
      out._winner_ref = rows[0]._winner_ref;
    }

    // Keep lexical display info from the representative piece row.
    // Do NOT overwrite head/headword unless they are blank.
    if (!out.head && out.text) out.head = out.text;
    if (!out.headword && out.head) out.headword = out.head;

    delete out._mwt_child_piece_rows;
    return out;
  }

  function explodeMwtChildGreedyRows(surfaceText, fillRows, langCode) {
    var surface = String(surfaceText || "");
    var rows = Array.isArray(fillRows) ? fillRows : [];
    if (!surface || !rows.length) return rows.slice();

    var out = [];

    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      var pieceRows = Array.isArray(row._mwt_child_piece_rows) ? row._mwt_child_piece_rows : null;

      var rowStart = parseInt(row._surface_start, 10);
      var rowEnd = parseInt(row._surface_end, 10);
      var isGreedyChild = (
        row._mwt_child_resolution_category &&
        row._mwt_child_resolution_category !== "exact_match" &&
        row._mwt_child_resolution_category !== "exact_lemma_match" &&
        row._mwt_child_resolution_category !== "lemma_override" &&
        row._mwt_child_resolution_category !== "lemma_partial_override"
      );

      if (
        !isGreedyChild ||
        !pieceRows ||
        !pieceRows.length ||
        !isFinite(rowStart) ||
        !isFinite(rowEnd) ||
        rowEnd <= rowStart
      ) {
        out.push(row);
        continue;
      }

      var localSurface = surface.slice(rowStart, rowEnd);
      if (!localSurface) {
        out.push(row);
        continue;
      }

      // Child piece rows are aligned inside the child slice only.
      var localRows = pieceRows.map(cloneMwtChildPieceRow);

      // Python supplies the authoritative child-local → parent-relative char
      // lattice in row._mwt_child_char_map. If it's present and every piece
      // carries valid child-local offsets, remap each piece directly using
      // the lattice — no JS char-aware alignment, no proportional math.
      var charMap = Array.isArray(row._mwt_child_char_map) ? row._mwt_child_char_map : null;
      var childLocalSurface = null;
      if (charMap && charMap.length) {
        // Reconstruct the unsandhied child surface by walking piece offsets.
        // The lattice is keyed to child-local char indices, so its length is
        // len(child_surface_text). We still need that length to validate.
        childLocalSurface = "";
        for (var _plri = 0; _plri < localRows.length; _plri++) {
          var _plrRow = localRows[_plri] || {};
          var _plrText = typeof _plrRow.text === "string" ? _plrRow.text : "";
          childLocalSurface += _plrText;
        }
      }

      var usedCharMap = false;
      if (charMap && charMap.length && childLocalSurface && charMap.length >= childLocalSurface.length) {
        // Pass 1: compute raw [gStart, gEnd] for each non-empty piece via the lattice.
        var piecePlan = [];
        var cursorCM = 0;
        for (var pci = 0; pci < localRows.length; pci++) {
          var pcRow = localRows[pci] || {};
          var pcText = typeof pcRow.text === "string" ? pcRow.text : "";
          if (!pcText) { continue; }
          var lo = cursorCM;
          var hi = cursorCM + pcText.length;
          cursorCM = hi;
          if (hi > charMap.length) break;
          var gStart = charMap[lo];
          var gEnd = charMap[hi - 1] + 1;
          if (!isFinite(gStart) || !isFinite(gEnd)) continue;
          if (gStart < rowStart) gStart = rowStart;
          if (gEnd > rowEnd) gEnd = rowEnd;
          if (gEnd < gStart) gEnd = gStart;
          piecePlan.push({ row: pcRow, start: gStart, end: gEnd });
        }
        // Pass 2: drop zero-width pieces (they'd otherwise hover with the whole
        // token because no surface char belongs to them), then tile so the
        // remaining pieces fully cover [rowStart, rowEnd] with no gaps. Every
        // surface character must belong to exactly one piece.
        var nonEmpty = [];
        for (var ppi = 0; ppi < piecePlan.length; ppi++) {
          if (piecePlan[ppi].end > piecePlan[ppi].start) nonEmpty.push(piecePlan[ppi]);
        }
        if (nonEmpty.length) {
          // Monotonicity: each piece starts no earlier than its predecessor.
          for (var mi = 1; mi < nonEmpty.length; mi++) {
            if (nonEmpty[mi].start < nonEmpty[mi - 1].start) {
              nonEmpty[mi].start = nonEmpty[mi - 1].start;
              if (nonEmpty[mi].end < nonEmpty[mi].start) nonEmpty[mi].end = nonEmpty[mi].start;
            }
          }
          // First piece claims from rowStart; each piece extends to the next
          // piece's start; the last piece extends to rowEnd.
          nonEmpty[0].start = rowStart;
          for (var ti = 0; ti < nonEmpty.length - 1; ti++) {
            nonEmpty[ti].end = nonEmpty[ti + 1].start;
            if (nonEmpty[ti].end < nonEmpty[ti].start) nonEmpty[ti].end = nonEmpty[ti].start;
          }
          nonEmpty[nonEmpty.length - 1].end = rowEnd;

          for (var ei = 0; ei < nonEmpty.length; ei++) {
            var piece = nonEmpty[ei];
            if (piece.end <= piece.start) continue;
            var synthSurface = surface.slice(piece.start, piece.end);
            var synthRow = buildSyntheticMwtChildSliceRow(synthSurface, [piece.row]);
            var pieceLocalStart = parseInt(piece.row && piece.row._surface_start, 10);
            var pieceLocalEnd = parseInt(piece.row && piece.row._surface_end, 10);
            var pieceLocalText = typeof (piece.row && piece.row.text) === "string"
              ? String(piece.row.text || "")
              : String((piece.row && piece.row.surface_form) || "");
            if (
              (!pieceLocalText) &&
              childLocalSurface &&
              isFinite(pieceLocalStart) &&
              isFinite(pieceLocalEnd) &&
              pieceLocalEnd > pieceLocalStart
            ) {
              pieceLocalText = childLocalSurface.slice(pieceLocalStart, pieceLocalEnd);
            }
            synthRow._surface_start = piece.start;
            synthRow._surface_end = piece.end;
            if (pieceLocalText) synthRow._mwt_child_text = pieceLocalText;
            if (isFinite(pieceLocalStart) && isFinite(pieceLocalEnd) && pieceLocalEnd >= pieceLocalStart) {
              synthRow._mwt_child_local_start = pieceLocalStart;
              synthRow._mwt_child_local_end = pieceLocalEnd;
            }
            synthRow._mwt_part_index = row._mwt_part_index;
            synthRow._mwt_child_resolution_category = row._mwt_child_resolution_category;
            if (row._lemma_upos_hint) synthRow._lemma_upos_hint = row._lemma_upos_hint;
            if (row._lemma_xpos_hint) synthRow._lemma_xpos_hint = row._lemma_xpos_hint;
            if (row._lemma_promoted) synthRow._lemma_promoted = true;
            if (row._lemma_override) synthRow._lemma_override = true;
            out.push(synthRow);
          }
          usedCharMap = true;
        }
      }
      if (usedCharMap) continue;

      // Fallback (no char_map available): keep the bundled row intact. No JS
      // proportional alignment — spec forbids it.
      out.push(row);
    }

    return out;
  }

  function _buildPerChildFillSlices(surface, fills, mwtParts) {
    var surfaceText = String(surface || "");
    var rows = Array.isArray(fills) ? fills : [];
    var parts = Array.isArray(mwtParts) ? mwtParts : [];
    if (!surfaceText || !rows.length || parts.length < 2) return [];

    // Group fill indexes by _mwt_part_index.
    var fillsByPart = {};
    var anyTagged = false;
    for (var ri = 0; ri < rows.length; ri++) {
      var pi = parseInt((rows[ri] && rows[ri]._mwt_part_index), 10);
      if (isFinite(pi)) {
        anyTagged = true;
        if (!fillsByPart[pi]) fillsByPart[pi] = [];
        fillsByPart[pi].push(ri);
      }
    }
    if (!anyTagged) return [];

    var allSlices = [];
    for (var ci = 0; ci < parts.length; ci++) {
      var part = parts[ci] || {};
      var childText = String(part.text || "");
      if (!childText) continue;
      var childFillIdxs = fillsByPart[ci];
      if (!childFillIdxs || !childFillIdxs.length) continue;

      // Use the Python-computed surface_slice directly.  The MWT per-child
      // branch produces exactly one bundled fill per child whose
      // _surface_start/_surface_end match the part's surface_slice.  Never
      // re-derive from child text length — sandhi means the child text and
      // the surface slice can differ in width.
      var rawSlice = Array.isArray(part.surface_slice) ? part.surface_slice : null;
      var partStart = 0;
      var partEnd = childText.length;
      if (rawSlice && rawSlice.length >= 2) {
        partStart = parseInt(rawSlice[0], 10) || 0;
        partEnd = parseInt(rawSlice[1], 10) || (partStart + childText.length);
      }
      allSlices.push({
        start: partStart,
        end: partEnd,
        fill_indexes: childFillIdxs.slice()
      });
    }

    return allSlices;
  }

  function buildMwtSurfaceSlicesFromParts(surface, fills, mwtParts) {
    var surfaceText = String(surface || "");
    var rows = Array.isArray(fills) ? fills : [];
    var parts = Array.isArray(mwtParts) ? mwtParts : [];
    if (!surfaceText || !rows.length || parts.length < 2) return [];

    var slices = [];
    var cursor = 0;
    var claimedFillIndexes = Object.create(null);
    for (var i = 0; i < parts.length; i++) {
      var part = parts[i] || {};
      var partText = String(part.text || "");
      var rawSlice = Array.isArray(part.surface_slice) ? part.surface_slice : null;
      var start = cursor;
      var end = cursor + partText.length;
      if (rawSlice && rawSlice.length >= 2) {
        start = parseInt(rawSlice[0], 10);
        end = parseInt(rawSlice[1], 10);
      } else {
        if (!partText) return [];
        if (surfaceText.slice(cursor, cursor + partText.length) !== partText) return [];
      }
      if (!isFinite(start) || start < 0) start = 0;
      if (!isFinite(end) || end < start) end = start;
      if (end > surfaceText.length) end = surfaceText.length;
      if (start < cursor) return [];
      var fillIndexes = [];

      for (var ri = 0; ri < rows.length; ri++) {
        if (claimedFillIndexes[ri]) continue;
        var mappedPart = parseInt((rows[ri] && rows[ri]._lemma_part_index), 10);
        if (isFinite(mappedPart) && mappedPart === i) fillIndexes.push(ri);
      }

      if (!fillIndexes.length) {
        for (var rj = 0; rj < rows.length; rj++) {
          if (claimedFillIndexes[rj]) continue;
          var row = rows[rj] || {};
          var rowStart = parseInt(row._surface_start, 10);
          var rowEnd = parseInt(row._surface_end, 10);
          if (!isFinite(rowStart) || !isFinite(rowEnd) || rowEnd <= rowStart) continue;
          if (rowEnd <= start || rowStart >= end) continue;
          fillIndexes.push(rj);
        }
      }

      if (!fillIndexes.length) return [];

      var localized = buildLocalizedMwtPartRows(rows, fillIndexes, start, end);
      var partSlices = [];
      if (localized.global_indexes.length === 1) {
        partSlices.push({
          start: start,
          end: end,
          fill_indexes: localized.global_indexes.slice()
        });
      } else if (localized.global_indexes.length > 1) {
        var localSurface = surfaceText.slice(start, end);
        var localRows = localized.rows;
        var localSlices = buildFillSurfaceSlicesFromExplicitOffsets(localSurface, localRows);
        if (!localSlices.length) {
          localSlices = buildFillSurfaceSlices(localSurface, localRows, getCurrentLanguage());
        }
        partSlices = remapLocalizedMwtPartSlices(localSlices, localized.global_indexes, start);
        if (!partSlices.length) {
          partSlices.push({
            start: start,
            end: end,
            fill_indexes: localized.global_indexes.slice()
          });
        }
      }

      if (!partSlices.length) return [];
      for (var psi = 0; psi < partSlices.length; psi++) {
        var ids = Array.isArray(partSlices[psi].fill_indexes) ? partSlices[psi].fill_indexes : [];
        for (var fi = 0; fi < ids.length; fi++) claimedFillIndexes[ids[fi]] = true;
        slices.push(partSlices[psi]);
      }
      cursor = end;
    }

    if (cursor !== surfaceText.length || !slices.length) return [];
    _attachOrphanFills(slices, rows.length);
    return slices;
  }

  function applyMwtUiPosShading(rows, mwtParts, surfaceText) {
    var fillRows = Array.isArray(rows) ? rows : [];
    var parts = Array.isArray(mwtParts) ? mwtParts : [];
    var surface = String(surfaceText || "");
    if (!fillRows.length || parts.length < 2 || !surface) return fillRows;

    var partRanges = [];
    var cursor = 0;
    for (var i = 0; i < parts.length; i++) {
      var part = parts[i] || {};
      var partText = String(part.text || "");
      var rawSlice = Array.isArray(part.surface_slice) ? part.surface_slice : null;
      var start = cursor;
      var nextCursor = cursor + partText.length;
      if (rawSlice && rawSlice.length >= 2) {
        start = parseInt(rawSlice[0], 10);
        nextCursor = parseInt(rawSlice[1], 10);
      } else if (!partText) {
        return fillRows;
      }
      if (!isFinite(start) || start < 0) start = 0;
      if (!isFinite(nextCursor) || nextCursor < start) nextCursor = start;
      if (nextCursor > surface.length) nextCursor = surface.length;
      partRanges.push({
        index: i,
        start: start,
        end: nextCursor,
        upos: String(part.upos || "").trim(),
        xpos: String(part.tag || part.xpos || "").trim()
      });
      cursor = nextCursor;
    }

    for (var ri = 0; ri < fillRows.length; ri++) {
      var row = fillRows[ri] || {};
      if (!row || typeof row !== "object") continue;
      var partIndex = parseInt(row._mwt_part_index, 10);
      if (!isFinite(partIndex)) partIndex = parseInt(row._lemma_part_index, 10);
      var matchedPart = (isFinite(partIndex) && partIndex >= 0 && partIndex < partRanges.length)
        ? partRanges[partIndex]
        : null;

      if (!matchedPart) {
        var rowStart = parseInt(row._surface_start, 10);
        var rowEnd = parseInt(row._surface_end, 10);
        if (isFinite(rowStart) && isFinite(rowEnd) && rowEnd > rowStart) {
          var bestPart = null;
          var bestOverlap = 0;
          for (var pi = 0; pi < partRanges.length; pi++) {
            var overlap = Math.min(rowEnd, partRanges[pi].end) - Math.max(rowStart, partRanges[pi].start);
            if (overlap > bestOverlap) {
              bestOverlap = overlap;
              bestPart = partRanges[pi];
            }
          }
          matchedPart = bestPart;
        }
      }

      if (!matchedPart) continue;
      if (matchedPart.upos) {
        row.upos = matchedPart.upos;
        row.upos_label = matchedPart.upos;
        row.upos_color = UPOS_COLORS[matchedPart.upos] || "#d1d5db";
      }
      if (matchedPart.xpos) {
        row.tag = matchedPart.xpos;
        row.xpos = matchedPart.xpos;
      }
    }
    return fillRows;
  }

  // Build fill surface slices for MWT tokens where each fill row already carries
  // authoritative Trankit character offsets (_surface_start/_surface_end).
  // No string matching — offsets are the sole source of truth.
  function buildMwtFillSurfaceSlicesFromOffsets(fills) {
    var rows = Array.isArray(fills) ? fills : [];
    if (!rows.length) return [];
    var slices = [];
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      var start = parseInt(row._surface_start, 10);
      var end = parseInt(row._surface_end, 10);
      if (!isFinite(start) || !isFinite(end) || end <= start) return [];
      slices.push({ start: start, end: end, fill_indexes: [i] });
    }
    return slices;
  }

  function buildFillSurfaceSlicesFromExplicitOffsets(surface, fills) {
    var surfaceText = String(surface || "");
    var rows = Array.isArray(fills) ? fills : [];
    if (!surfaceText || rows.length < 2) return [];

    var slices = [];
    var alignableCount = 0;
    var prevStart = -1;
    var prevEnd = -1;

    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      var pieceText = getFillPieceSurfaceText(row);
      if (!pieceText) continue;
      alignableCount += 1;

      var start = parseInt(row._surface_start, 10);
      var end = parseInt(row._surface_end, 10);
      if (!isFinite(start) || !isFinite(end)) return [];
      if (start < 0 || end > surfaceText.length || end <= start) return [];

      var sameSpanAsPrev = (start === prevStart && end === prevEnd);
      if (!sameSpanAsPrev && prevEnd >= 0 && start < prevEnd) return [];

      if (slices.length && slices[slices.length - 1].start === start && slices[slices.length - 1].end === end) {
        slices[slices.length - 1].fill_indexes.push(i);
      } else {
        slices.push({
          start: start,
          end: end,
          fill_indexes: [i]
        });
      }
      prevStart = start;
      prevEnd = end;
    }

    if (alignableCount < 2 || !slices.length) return [];
    _attachOrphanFills(slices, rows.length);
    return slices;
  }

  function buildFillSurfaceSlices(surface, fills, langOverride) {
    var surfaceText = String(surface || "");
    var rows = Array.isArray(fills) ? fills : [];
    if (!surfaceText || rows.length < 2) return [];

    // When the lookup pipeline already attached explicit surface spans to each
    // fill row, those spans are the source of truth. Do not re-slice them here.
    var explicitSlices = buildFillSurfaceSlicesFromExplicitOffsets(surfaceText, rows);
    if (explicitSlices.length) return explicitSlices;

    var langCode = String(langOverride || getCurrentLanguage() || "").toLowerCase();

    // --- Step 1: extract surface text for each fill piece ---
    var alignableIndexes = [];
    var pieceTexts = [];
    for (var i = 0; i < rows.length; i++) {
      var pieceText = getFillPieceSurfaceText(rows[i]);
      if (pieceText) {
        alignableIndexes.push(i);
        pieceTexts.push(pieceText);
      }
    }
    if (!pieceTexts.length) return [];

    // Single alignable fill covers the whole surface
    if (pieceTexts.length === 1) {
      var allIds = [alignableIndexes[0]];
      for (var oi = 0; oi < rows.length; oi++) {
        if (oi !== alignableIndexes[0]) allIds.push(oi);
      }
      allIds.sort(function(a, b) { return a - b; });
      return [{ start: 0, end: surfaceText.length, fill_indexes: allIds }];
    }

    // --- Step 2: exact concatenation check ---
    var joined = pieceTexts.join("");
    if (joined === surfaceText) {
      var slices = [];
      var cursor = 0;
      for (var ei = 0; ei < pieceTexts.length; ei++) {
        var nextCursor = cursor + pieceTexts[ei].length;
        slices.push({
          start: cursor,
          end: nextCursor,
          fill_indexes: [alignableIndexes[ei]]
        });
        cursor = nextCursor;
      }
      _attachOrphanFills(slices, rows.length);
      return slices;
    }

    // --- Step 3: character-level trivial alignment ---
    // If the characters in the fills line up with the surface characters
    // in order (just spread across different piece boundaries), use that.
    var surfaceChars = Array.from(surfaceText);
    var trivialOk = true;
    var trivialSlices = [];
    var sIdx = 0;
    for (var ti = 0; ti < pieceTexts.length && trivialOk; ti++) {
      var pChars = Array.from(pieceTexts[ti]);
      var sliceStart = sIdx;
      for (var pc = 0; pc < pChars.length; pc++) {
        if (sIdx >= surfaceChars.length || pChars[pc] !== surfaceChars[sIdx]) {
          trivialOk = false;
          break;
        }
        sIdx++;
      }
      if (trivialOk) {
        // Convert character index back to string offset
        var offsetStart = 0;
        for (var os = 0; os < sliceStart; os++) offsetStart += surfaceChars[os].length;
        var offsetEnd = offsetStart;
        for (var oe = sliceStart; oe < sIdx; oe++) offsetEnd += surfaceChars[oe].length;
        trivialSlices.push({
          start: offsetStart,
          end: offsetEnd,
          fill_indexes: [alignableIndexes[ti]]
        });
      }
    }
    if (trivialOk && sIdx === surfaceChars.length) {
      _attachOrphanFills(trivialSlices, rows.length);
      return trivialSlices;
    }

    // --- Step 4: Needleman-Wunsch alignment ---
    // Run NW on fill piece characters against surface characters.
    // Pieces that match get frozen in place; unmatched pieces and
    // unmatched surface gaps are resolved in step 5.
    //
    // For Korean: decompose Hangul syllables into jamo for NW comparison,
    // then map jamo matches back to original surface character indices.

    var isKorean = isKoreanLanguageCode(langCode);

    // Build flat arrays for NW. For Korean, these are jamo units;
    // for other languages, plain characters.
    var surfaceNWUnits = [];     // units used for NW comparison
    var surfaceNWToChar = [];    // maps each NW unit index -> surfaceChars index
    for (var sci = 0; sci < surfaceChars.length; sci++) {
      if (isKorean) {
        var sJamo = decomposeHangulSyllable(surfaceChars[sci]);
        for (var sji = 0; sji < sJamo.length; sji++) {
          surfaceNWUnits.push(normalizeJamoForComparison(sJamo[sji]));
          surfaceNWToChar.push(sci);
        }
      } else {
        surfaceNWUnits.push(surfaceChars[sci]);
        surfaceNWToChar.push(sci);
      }
    }

    var fillNWUnits = [];
    var fillNWPieceIdx = [];  // which pieceTexts index each NW unit belongs to
    for (var fi = 0; fi < pieceTexts.length; fi++) {
      var fChars = Array.from(pieceTexts[fi]);
      for (var fc = 0; fc < fChars.length; fc++) {
        if (isKorean) {
          var fJamo = decomposeHangulSyllable(fChars[fc]);
          for (var fji = 0; fji < fJamo.length; fji++) {
            fillNWUnits.push(normalizeJamoForComparison(fJamo[fji]));
            fillNWPieceIdx.push(fi);
          }
        } else {
          fillNWUnits.push(fChars[fc]);
          fillNWPieceIdx.push(fi);
        }
      }
    }

    var sLen = surfaceChars.length;
    var sNWLen = surfaceNWUnits.length;
    var fNWLen = fillNWUnits.length;

    // NW scoring
    var MATCH = 2, MISMATCH = -1, GAP = -1;
    var nwRows = sNWLen + 1;
    var nwCols = fNWLen + 1;
    var sc = new Array(nwRows);
    for (var si = 0; si < nwRows; si++) {
      sc[si] = new Array(nwCols);
      sc[si][0] = si * GAP;
    }
    for (var fj = 0; fj < nwCols; fj++) sc[0][fj] = fj * GAP;
    for (var si2 = 1; si2 < nwRows; si2++) {
      for (var fj2 = 1; fj2 < nwCols; fj2++) {
        var diag = sc[si2 - 1][fj2 - 1] +
          (surfaceNWUnits[si2 - 1] === fillNWUnits[fj2 - 1] ? MATCH : MISMATCH);
        var up = sc[si2 - 1][fj2] + GAP;
        var left = sc[si2][fj2 - 1] + GAP;
        sc[si2][fj2] = Math.max(diag, up, left);
      }
    }

    // Traceback: record which surface chars matched which piece index(es).
    // NW runs on jamo/units; we project matches back to surfaceChars indices.
    // For Korean, a single surface char (syllable) can span multiple pieces
    // when its jamo decomposition matches parts from different lemma pieces.
    var surfaceCharPieces = [];  // array of arrays: piece indexes per surface char
    for (var sm = 0; sm < sLen; sm++) surfaceCharPieces.push([]);
    var pieceMatchCount = new Array(pieceTexts.length);
    for (var pm = 0; pm < pieceTexts.length; pm++) pieceMatchCount[pm] = 0;

    var tbi = sNWLen, tbj = fNWLen;
    while (tbi > 0 && tbj > 0) {
      var cur = sc[tbi][tbj];
      var diagVal = sc[tbi - 1][tbj - 1] +
        (surfaceNWUnits[tbi - 1] === fillNWUnits[tbj - 1] ? MATCH : MISMATCH);
      if (cur === diagVal) {
        if (surfaceNWUnits[tbi - 1] === fillNWUnits[tbj - 1]) {
          var origCharIdx = surfaceNWToChar[tbi - 1];
          var matchedPiece = fillNWPieceIdx[tbj - 1];
          if (surfaceCharPieces[origCharIdx].indexOf(matchedPiece) < 0) {
            surfaceCharPieces[origCharIdx].push(matchedPiece);
          }
          pieceMatchCount[matchedPiece]++;
        }
        tbi--;
        tbj--;
      } else if (cur === sc[tbi - 1][tbj] + GAP) {
        tbi--;
      } else {
        tbj--;
      }
    }

    // Identify frozen pieces (pieces with at least one NW match)
    var pieceFrozen = new Array(pieceTexts.length);
    for (var pf = 0; pf < pieceTexts.length; pf++) {
      pieceFrozen[pf] = pieceMatchCount[pf] > 0;
    }

    // For each frozen piece, find its surface char range (min..max matched)
    var pieceMinChar = new Array(pieceTexts.length);
    var pieceMaxChar = new Array(pieceTexts.length);
    for (var pr = 0; pr < pieceTexts.length; pr++) {
      pieceMinChar[pr] = sLen;
      pieceMaxChar[pr] = -1;
    }
    for (var sr = 0; sr < sLen; sr++) {
      var charPieces = surfaceCharPieces[sr];
      for (var cpi = 0; cpi < charPieces.length; cpi++) {
        var mp = charPieces[cpi];
        if (sr < pieceMinChar[mp]) pieceMinChar[mp] = sr;
        if (sr > pieceMaxChar[mp]) pieceMaxChar[mp] = sr;
      }
    }

    // Expand each frozen piece to cover its full matched range (fill interior gaps).
    // For Korean, a single char can belong to multiple pieces (jamo spanning pieces).
    // Use frozenAssign for the primary piece, and track multi-piece chars separately.
    var frozenAssign = new Array(sLen);
    for (var fa = 0; fa < sLen; fa++) frozenAssign[fa] = -1;
    for (var fp = 0; fp < pieceTexts.length; fp++) {
      if (!pieceFrozen[fp]) continue;
      for (var fx = pieceMinChar[fp]; fx <= pieceMaxChar[fp]; fx++) {
        if (frozenAssign[fx] < 0) frozenAssign[fx] = fp;
      }
    }

    // Build frozen slices from contiguous runs of the same piece.
    // When a surface char has multiple piece assignments (Korean jamo spanning),
    // merge those pieces into a single slice.
    var frozenSlices = [];  // {start_char, end_char, piece_idx -or- piece_idxs}
    var gapRegions = [];    // {start_char, end_char}
    var runStart = 0;
    while (runStart < sLen) {
      if (frozenAssign[runStart] >= 0) {
        var runPiece = frozenAssign[runStart];
        var runEnd = runStart + 1;
        while (runEnd < sLen && frozenAssign[runEnd] === runPiece) runEnd++;
        // Check if any char in this run has multiple pieces (jamo split)
        var allPieces = [runPiece];
        var seenPiece = {};
        seenPiece[runPiece] = true;
        for (var rci = runStart; rci < runEnd; rci++) {
          var rcPieces = surfaceCharPieces[rci];
          for (var rcj = 0; rcj < rcPieces.length; rcj++) {
            if (!seenPiece[rcPieces[rcj]]) {
              seenPiece[rcPieces[rcj]] = true;
              allPieces.push(rcPieces[rcj]);
            }
          }
        }
        allPieces.sort(function(a, b) { return a - b; });
        frozenSlices.push({ start_char: runStart, end_char: runEnd, piece_idx: allPieces[0], piece_idxs: allPieces });
        runStart = runEnd;
      } else {
        var gapEnd = runStart + 1;
        while (gapEnd < sLen && frozenAssign[gapEnd] < 0) gapEnd++;
        gapRegions.push({ start_char: runStart, end_char: gapEnd });
        runStart = gapEnd;
      }
    }

    // --- Step 5: assign unmatched pieces to gap regions ---
    // Unmatched pieces get placed into the gap region nearest their
    // expected position (between their neighboring frozen pieces).
    var unmatchedPieces = [];
    for (var up = 0; up < pieceTexts.length; up++) {
      if (!pieceFrozen[up]) unmatchedPieces.push(up);
    }

    // For each unmatched piece, find the gap it belongs in based on
    // its ordinal position among pieces.
    // Strategy: an unmatched piece between frozen piece A and frozen
    // piece B belongs in the gap between A's range and B's range.
    var gapAssignments = [];  // parallel to gapRegions: array of piece indexes
    for (var ga = 0; ga < gapRegions.length; ga++) gapAssignments.push([]);

    for (var ui = 0; ui < unmatchedPieces.length; ui++) {
      var uPiece = unmatchedPieces[ui];
      // Find the frozen piece just before and just after this one
      var prevFrozen = -1, nextFrozen = -1;
      for (var pb = uPiece - 1; pb >= 0; pb--) {
        if (pieceFrozen[pb]) { prevFrozen = pb; break; }
      }
      for (var nb = uPiece + 1; nb < pieceTexts.length; nb++) {
        if (pieceFrozen[nb]) { nextFrozen = nb; break; }
      }

      // Find the gap region between prevFrozen's end and nextFrozen's start
      var bestGap = -1;
      var targetCharPos = 0;
      if (prevFrozen >= 0 && nextFrozen >= 0) {
        targetCharPos = pieceMaxChar[prevFrozen] + 1;
      } else if (prevFrozen >= 0) {
        targetCharPos = pieceMaxChar[prevFrozen] + 1;
      } else if (nextFrozen >= 0) {
        targetCharPos = pieceMinChar[nextFrozen] - 1;
      } else {
        targetCharPos = Math.floor(sLen / 2);
      }

      var bestDist = Infinity;
      for (var gj = 0; gj < gapRegions.length; gj++) {
        var gMid = (gapRegions[gj].start_char + gapRegions[gj].end_char) / 2;
        var d = Math.abs(gMid - targetCharPos);
        if (d < bestDist) { bestDist = d; bestGap = gj; }
      }

      if (bestGap >= 0) {
        gapAssignments[bestGap].push(uPiece);
      } else if (frozenSlices.length) {
        // No gap regions available — attach to nearest frozen slice
        var nearestFrozen = 0;
        var nearestFDist = Infinity;
        for (var nf = 0; nf < frozenSlices.length; nf++) {
          var fMid = (frozenSlices[nf].start_char + frozenSlices[nf].end_char) / 2;
          var fd = Math.abs(fMid - targetCharPos);
          if (fd < nearestFDist) { nearestFDist = fd; nearestFrozen = nf; }
        }
        // Mark for inclusion when building final slices
        if (!frozenSlices[nearestFrozen]._extra_pieces) frozenSlices[nearestFrozen]._extra_pieces = [];
        frozenSlices[nearestFrozen]._extra_pieces.push(uPiece);
      }
    }

    // --- Build final slices ---
    // Merge frozen slices and gap slices in surface order
    var finalSlices = [];

    // Convert frozen slices
    for (var fs = 0; fs < frozenSlices.length; fs++) {
      var fSlice = frozenSlices[fs];
      var fStart = 0;
      for (var co = 0; co < fSlice.start_char; co++) fStart += surfaceChars[co].length;
      var fEnd = fStart;
      for (var ce = fSlice.start_char; ce < fSlice.end_char; ce++) fEnd += surfaceChars[ce].length;
      // Use all piece indexes (includes jamo-spanning pieces for Korean)
      var fFillIds = [];
      var pIdxs = fSlice.piece_idxs || [fSlice.piece_idx];
      for (var pi = 0; pi < pIdxs.length; pi++) {
        fFillIds.push(alignableIndexes[pIdxs[pi]]);
      }
      if (fSlice._extra_pieces) {
        for (var ep = 0; ep < fSlice._extra_pieces.length; ep++) {
          fFillIds.push(alignableIndexes[fSlice._extra_pieces[ep]]);
        }
      }
      finalSlices.push({
        start: fStart,
        end: fEnd,
        fill_indexes: fFillIds,
        _char_start: fSlice.start_char,
        _char_end: fSlice.end_char
      });
    }

    // Convert gap slices (each gap gets all its assigned unmatched pieces)
    for (var gs = 0; gs < gapRegions.length; gs++) {
      if (!gapAssignments[gs].length) continue;
      var gRegion = gapRegions[gs];
      var gStart = 0;
      for (var go = 0; go < gRegion.start_char; go++) gStart += surfaceChars[go].length;
      var gEnd = gStart;
      for (var ge = gRegion.start_char; ge < gRegion.end_char; ge++) gEnd += surfaceChars[ge].length;
      var gIds = [];
      for (var gp = 0; gp < gapAssignments[gs].length; gp++) {
        gIds.push(alignableIndexes[gapAssignments[gs][gp]]);
      }
      finalSlices.push({
        start: gStart,
        end: gEnd,
        fill_indexes: gIds,
        _char_start: gRegion.start_char,
        _char_end: gRegion.end_char
      });
    }

    // Sort by surface position
    finalSlices.sort(function(a, b) {
      if (a.start !== b.start) return a.start - b.start;
      return a.end - b.end;
    });

    // Absorb any uncovered byte ranges into their nearest neighbour slice.
    // The NW aligner can leave gaps at the head, tail, or interior of the
    // surface when a piece only partially matches (e.g. "añc" matches "a"
    // in "aṁ", leaving "ṁ" as a gap region with no unmatched piece).
    // Without this pass such characters become bare text nodes whose hover
    // falls through to the parent token and shows all entries at once.
    if (finalSlices.length) {
      // Leading gap: extend first slice back to byte 0
      if (finalSlices[0].start > 0) {
        finalSlices[0].start = 0;
      }
      // Trailing gap: extend last slice to end of surface
      var surfaceByteLen = surfaceText.length;
      if (finalSlices[finalSlices.length - 1].end < surfaceByteLen) {
        finalSlices[finalSlices.length - 1].end = surfaceByteLen;
      }
      // Interior gaps: if slice[i].end < slice[i+1].start, split the gap
      // at the midpoint and give the left half to slice[i] and the right
      // half to slice[i+1].  Using the midpoint keeps display proportions
      // reasonable; any split point is better than a bare text node.
      for (var ig = 0; ig < finalSlices.length - 1; ig++) {
        var igEnd = finalSlices[ig].end;
        var igNextStart = finalSlices[ig + 1].start;
        if (igNextStart > igEnd) {
          var igMid = Math.ceil((igEnd + igNextStart) / 2);
          finalSlices[ig].end = igMid;
          finalSlices[ig + 1].start = igMid;
        }
      }
    }

    // Clean up temp fields
    for (var cl = 0; cl < finalSlices.length; cl++) {
      delete finalSlices[cl]._char_start;
      delete finalSlices[cl]._char_end;
    }

    // Attach orphan fills (fills without text that weren't placed)
    _attachOrphanFills(finalSlices, rows.length);

    return finalSlices;
  }

  // Attach fills that don't appear in any slice to the nearest slice
  function _attachOrphanFills(slices, totalRows) {
    if (!slices.length) return;
    var present = Object.create(null);
    for (var si = 0; si < slices.length; si++) {
      var ids = slices[si].fill_indexes;
      for (var sj = 0; sj < ids.length; sj++) present[ids[sj]] = true;
    }
    for (var ri = 0; ri < totalRows; ri++) {
      if (present[ri]) continue;
      var bestSlice = 0;
      var bestDist = Infinity;
      for (var si2 = 0; si2 < slices.length; si2++) {
        var fIds = slices[si2].fill_indexes;
        for (var fj = 0; fj < fIds.length; fj++) {
          var d = Math.abs(fIds[fj] - ri);
          if (d < bestDist) { bestDist = d; bestSlice = si2; }
        }
      }
      slices[bestSlice].fill_indexes.push(ri);
    }
    for (var fi = 0; fi < slices.length; fi++) {
      slices[fi].fill_indexes.sort(function(a, b) { return a - b; });
    }
  }

  function deriveFillPieceXposHints(fills, lemma, xpos) {
    void lemma;
    void xpos;
    var out = [];
    for (var i = 0; i < (fills || []).length; i++) {
      var row = fills[i];
      if (row && typeof row === "object") out.push(Object.assign({}, row));
      else out.push(row);
    }
    return out;
  }

  function buildLiveLookupFillPayload(surfaceText, fill, lemmaText, uposText, xposText, preferredSenseFilterXpos, engine, resolvedVia, mwtParts, includeDebugTrace) {
    var tokenSurface = String(surfaceText || "");
    var partList = Array.isArray(mwtParts) ? mwtParts : [];
    var fillRows = deriveFillPieceXposHints((fill && fill.fills) || [], lemmaText, xposText);
    var fillMode = String((fill && fill.mode) || "greedy");

    // MWT child results carry authoritative child-local offset metadata on the
    // fill rows. Preserve that exact path here so main lookup rendering and
    // DP-only single-token refreshes rebuild the same slices.
    var isMwtChildFill = (fillMode === "mwt_child" || fillMode === "mwt_lemma_promoted");
    if (isMwtChildFill) {
      fillRows = explodeMwtChildGreedyRows(tokenSurface, fillRows, getCurrentLanguage());
    }

    var rawFills = prepareFillEntries(
      fillRows,
      engine,
      uposText,
      preferredSenseFilterXpos,
      fillMode,
      includeDebugTrace
    );

    if (partList.length > 1) {
      applyMwtUiPosShading(rawFills, partList, tokenSurface);
    }
    annotateLiveLemmaLinkedFills(rawFills, resolvedVia);

    var fillSurfaceSlices;
    if (isMwtChildFill) {
      fillSurfaceSlices = buildMwtFillSurfaceSlicesFromOffsets(rawFills);
    } else {
      fillSurfaceSlices = buildMwtSurfaceSlicesFromParts(tokenSurface, rawFills, partList);
      if (!fillSurfaceSlices.length) {
        fillSurfaceSlices = buildFillSurfaceSlices(tokenSurface, rawFills, getCurrentLanguage());
      }
    }

    return {
      rawFills: rawFills,
      fillMode: fillMode,
      fillSurfaceSlices: Array.isArray(fillSurfaceSlices) ? fillSurfaceSlices : [],
      isMwtChildFill: isMwtChildFill
    };
  }

  function applyFillRepresentativeEntry(target, entry, forceDisplayFields) {
    if (!target || typeof target !== "object" || !entry || typeof entry !== "object") return;
    var forceDisplay = !!forceDisplayFields;
    var displayHeadword = String(entry.display_headword || entry.headword || "").trim();
    var lemmaHeadword = String(entry.lemma_headword || "").trim();
    var displayReading = getEntryDisplayReading(entry);
    if (entry.entry_id) target.entry_id = String(entry.entry_id || "");
    if (entry.ref_key) target.ref_key = String(entry.ref_key || "");
    if (entry.runtime_entry_id) target.runtime_entry_id = String(entry.runtime_entry_id || "");
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
      if (!target.entry_reading && entry.entry_reading) target.entry_reading = String(entry.entry_reading || "");
    }
    if (entry.match_kind) target.match_kind = String(entry.match_kind || "").trim().toLowerCase();
    if (entry._source) target._source = String(entry._source || "");
    else if (entry.source && !target._source) target._source = String(entry.source || "");
    if (forceDisplay || !target.roman) target.roman = displayReading;
    if (forceDisplay || !target.reading) target.reading = displayReading;
    if (forceDisplay || !target.pos) target.pos = String(entry.pos || entry.pos_raw || "");
    if (forceDisplay || !target.pos_raw) target.pos_raw = String(entry.pos_raw || entry.pos || "");
    if (entry.morph_info) {
      target.morph_info = Array.isArray(entry.morph_info)
        ? entry.morph_info.slice()
        : [String(entry.morph_info || "")];
    } else if (forceDisplay && Object.prototype.hasOwnProperty.call(target, "morph_info")) {
      delete target.morph_info;
    }
    if (entry.morph_base) {
      target.morph_base = String(entry.morph_base || "");
    } else if (forceDisplay && Object.prototype.hasOwnProperty.call(target, "morph_base")) {
      delete target.morph_base;
    }
    if (entry.grammar) {
      target.grammar = String(entry.grammar || "");
    } else if (forceDisplay && Object.prototype.hasOwnProperty.call(target, "grammar")) {
      delete target.grammar;
    }
    if (entry._commentary !== undefined) target._commentary = String(entry._commentary || "");
    if (entry._lemma !== undefined) target._lemma = String(entry._lemma || "");
    if (entry.is_alternate_match !== undefined) target.is_alternate_match = !!entry.is_alternate_match;
  }

  function _entryRefKey(entry) {
    if (!entry || typeof entry !== "object") return "";
    return String(entry.ref_key || entry.runtime_entry_id || "").trim();
  }

  function _entryRefKeys(entries) {
    var out = [];
    var list = Array.isArray(entries) ? entries : [];
    for (var i = 0; i < list.length; i++) {
      var k = _entryRefKey(list[i]);
      if (k) out.push(k);
    }
    return out;
  }

  function setAtomicRenderEntries(target, allEntries, hoverEntries, otherEntries) {
    if (!target || typeof target !== "object") return;
    var allKeys = _entryRefKeys(allEntries);
    var hoverKeys = _entryRefKeys(hoverEntries);
    var otherKeys = _entryRefKeys(otherEntries);
    if (allKeys.length) target.atomic_entry_refs_all = allKeys;
    else if (Object.prototype.hasOwnProperty.call(target, "atomic_entry_refs_all")) delete target.atomic_entry_refs_all;
    if (hoverKeys.length) target.atomic_entry_refs_hover = hoverKeys;
    else if (Object.prototype.hasOwnProperty.call(target, "atomic_entry_refs_hover")) delete target.atomic_entry_refs_hover;
    if (otherKeys.length) target.atomic_entry_refs_other = otherKeys;
    else if (Object.prototype.hasOwnProperty.call(target, "atomic_entry_refs_other")) delete target.atomic_entry_refs_other;
    // Remove old full-object arrays if present
    delete target.atomic_entries_all;
    delete target.atomic_entries_hover;
    delete target.atomic_entries_other;
    if (Object.prototype.hasOwnProperty.call(target, "_dict_source")) delete target._dict_source;
  }

  function prepareFillEntries(fills, engine, upos, xpos, fillMode, includeDebugTrace) {
    var out = (fills || []).slice();
    var includeTrace = !!includeDebugTrace;
    var mode = String(fillMode || "").trim().toLowerCase();
    var greedyMatchMode = (mode === "greedy" || mode === "lemma_greedy" || mode === "lemma_partial_greedy" || mode === "greedy_lemma_mismatch");
    var knownFillPieceCount = 0;
    for (var k = 0; k < out.length; k++) {
      if (String((out[k] || {}).source || "").toUpperCase() !== "UNKNOWN") knownFillPieceCount += 1;
    }
    var greedyMultiFill = greedyMatchMode && knownFillPieceCount > 1;

    for (var i = 0; i < out.length; i++) {
      var f = out[i] || {};
      var fillHead = String(f.head || "");
      var fillText = String(f.text || "");
      var displayHead = fillText || fillHead;
      var lookupHead = fillHead || displayHead;
      if (displayHead) f.head = displayHead;
      var fillXposHint = String(f._xpos_hint || "");

      var fillEntries = (f.entries && f.entries.length) ? f.entries : [];
      var hoverEntries = (fillEntries && fillEntries.length) ? fillEntries.slice() : [];
      var otherEntries = [];

      var fullFormsMetaByHeader = {};
      var hoverFormsMetaByHeader = {};
      var otherFormsMetaByHeader = {};

      var fullSenses = [];
      if (fillEntries && fillEntries.length) {
        fullSenses = mergeAllEntries(displayHead || lookupHead, fillEntries);
        fullFormsMetaByHeader = buildJmdictFormsMetaByHeader(fillEntries);
      } else if (f.senses && f.senses.length) {
        fullSenses = formatSenses(displayHead || lookupHead, f.roman || "", f.senses);
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
        var effectiveUpos = String(f._lemma_upos_hint || upos || "").trim();
        var effectiveXpos = String(fillXposHint || f._lemma_xpos_hint || xpos || "");
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
          upos: String(upos || ""),
          xpos: String(fillXposHint || xpos || ""),
          effective_upos: effectiveUpos,
          effective_xpos: effectiveXpos,
          force_pos_raws: Array.isArray(f._force_pos_raws) ? f._force_pos_raws.slice() : [],
          lemma_upos_hint: String(f._lemma_upos_hint || ""),
          lemma_xpos_hint: String(f._lemma_xpos_hint || ""),
          greedy_match_mode: !!greedyMatchMode,
          greedy_multi_fill: !!greedyMultiFill,
          lemma_promoted: f._lemma_promoted || null,
          lemma_promoted_headword: f._lemma_promoted_headword || null,
          lemma_promoted_pos: f._lemma_promoted_pos || null
        };
      } else {
        if (Object.prototype.hasOwnProperty.call(f, "_debug_entry_refs_all")) delete f._debug_entry_refs_all;
        if (Object.prototype.hasOwnProperty.call(f, "_debug_entry_refs_shown")) delete f._debug_entry_refs_shown;
        if (Object.prototype.hasOwnProperty.call(f, "_debug_entry_refs_filtered")) delete f._debug_entry_refs_filtered;
        if (Object.prototype.hasOwnProperty.call(f, "_debug_trace")) delete f._debug_trace;
      }

      f.senses_hover = hoverSenses;
      f.senses_hover_other = otherSenses;
      f.hover_has_alt_senses = !!otherSenses.length;

      if (Object.prototype.hasOwnProperty.call(f, "_xpos_hint")) delete f._xpos_hint;
      if (Object.prototype.hasOwnProperty.call(f, "_force_pos_raws")) delete f._force_pos_raws;
      if (Object.prototype.hasOwnProperty.call(f, "_lemma_upos_hint")) delete f._lemma_upos_hint;
      if (Object.prototype.hasOwnProperty.call(f, "_lemma_xpos_hint")) delete f._lemma_xpos_hint;

      if (Object.keys(fullFormsMetaByHeader).length) f.senses_form_meta_by_header = fullFormsMetaByHeader;
      if (Object.keys(hoverFormsMetaByHeader).length) f.senses_hover_form_meta_by_header = hoverFormsMetaByHeader;
      if (Object.keys(otherFormsMetaByHeader).length) f.senses_hover_other_form_meta_by_header = otherFormsMetaByHeader;

      setAtomicRenderEntries(f, fillEntries, hoverEntries, otherEntries);
      var chosenFill = chooseEntry(lookupHead, hoverEntries.length ? hoverEntries : (fillEntries || []), engine);
      if (chosenFill) {
        applyFillRepresentativeEntry(f, chosenFill, false);
      }

      // Primary display should use the filtered "hover" entries so forced
      // alternate/redirect rows stay behind the other-definitions expander.
      attachWiktForms(f, displayHead || lookupHead, hoverEntries.length ? hoverEntries : (fillEntries || []));
      if (Object.prototype.hasOwnProperty.call(f, "g2p")) delete f.g2p;
      // Replace full entry objects with ref keys to avoid serialization bloat
      f.entry_refs = _entryRefKeys(fillEntries);
      delete f.entries;
    }
    return out;
  }

  function cloneSurfaceAnchor(anchor) {
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

  function isPopupOnlySurfaceAnchorToken(tokenText, surfaceText, surfaceAnchor) {
    var anchor = cloneSurfaceAnchor(surfaceAnchor);
    if (!anchor) return false;
    var childText = String(tokenText || '').trim();
    var visibleSurface = String(surfaceText || anchor.text || '').trim();
    if (!childText || !visibleSurface) return false;
    return normalizeVisibleComparisonText(childText) !== normalizeVisibleComparisonText(visibleSurface);
  }

  function buildUnknownResult(word, upos, xpos, deprel, lemma, feats, idx, lemmaRaw, lemmaSuffix, surfaceForm, surfaceAnchor) {
    var tokenText = String(word || "");
    var surfaceText = String(surfaceForm || tokenText);
    var entry = {
      text: tokenText,
      token_text: tokenText,
      head: tokenText,
      roman: "",
      pos: upos,
      meta_pos: "unknown",
      senses: [],
      source: "UNKNOWN",
      dict_fill: [],
      dict_fill_subwords: [],
      dict_fill_surface_slices: [],
      inspect_fill: [],
      dict_fill_mode: "greedy",
      dict_fill_has_known: false,
      dict_fill_has_unknown: true,
      seg_i: idx,
      g2p: null,
      upos: upos,
      upos_label: upos,
      upos_color: UPOS_COLORS[upos] || "#d1d5db",
      dep: deprel,
      dep_label: deprel,
      tag: xpos,
      lemma: lemma || "",
      feats: feats || "",
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

  function buildKoreanCompoundLemmaChildResult(childPayload, engine, includeDebugTrace) {
    var child = (childPayload && typeof childPayload === "object") ? childPayload : null;
    if (!child) return null;
    var token = String(child.text || "").trim();
    if (!token) return null;
    var surfaceLookup = (child.lookup && typeof child.lookup === "object") ? child.lookup : {};
    var upos = String(child.upos || "").trim();
    var xpos = String(child.xpos || "").trim();
    var fill = surfaceLookup.fill || null;
    var allEntries = Array.isArray(surfaceLookup.all_entries) ? surfaceLookup.all_entries : [];
    var preferredEntries = Array.isArray(surfaceLookup.preferred_entries) && surfaceLookup.preferred_entries.length
      ? surfaceLookup.preferred_entries
      : allEntries;
    var dictHead = String(surfaceLookup.dict_head || token);
    var resolvedVia = String(surfaceLookup.resolved_via || "surface");
    var lemmaHintObjects = (
      surfaceLookup.lemma_hint_data &&
      Array.isArray(surfaceLookup.lemma_hint_data.lemma_hint_objects)
    ) ? surfaceLookup.lemma_hint_data.lemma_hint_objects : [];
    var lemmaOverrideParts = Array.isArray(surfaceLookup.lemma_override_parts)
      ? surfaceLookup.lemma_override_parts
      : [];
    var exactLemmaMatchCount = Number(surfaceLookup.exact_lemma_match_count || 0);
    var preferredSenseFilterXpos = choosePreferredSenseFilterXpos(xpos, lemmaHintObjects, lemmaOverrideParts, engine);
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
      rawFills = [{
        text: token,
        head: token,
        surface_form: token,
        senses: [],
        pos: upos || "unknown",
        source: "UNKNOWN"
      }];
      fillSurfaceSlices = [];
    }

    var hasKnownFill = rawFills.some(function(row) {
      return !!(row && String(row.source || "").toUpperCase() !== "UNKNOWN");
    });
    var hasUnknownFill = rawFills.some(function(row) {
      return !row || String(row.source || "").toUpperCase() === "UNKNOWN";
    });
    var result;
    if (allEntries.length) {
      var entryFilterKw = {};
      var fillModeLower = String(fillMode || "").trim().toLowerCase();
      if (fillModeLower === "greedy" || fillModeLower === "lemma_greedy" || fillModeLower === "lemma_partial_greedy" || fillModeLower === "greedy_lemma_mismatch") {
        entryFilterKw.greedy_match = true;
      }
      if (shouldApplyStrictExactLemmaDisplayFilter(resolvedVia, exactLemmaMatchCount, preferredEntries)) {
        entryFilterKw.strict_exact_lemma_entries = preferredEntries.slice();
      }
      var split = splitEntriesForHover(allEntries, upos || "", engine, preferredSenseFilterXpos, entryFilterKw);
      var hoverEntries = split[0];
      var otherEntries = split[1];
      var primaryPool = hoverEntries.length ? hoverEntries : preferredEntries;
      var best = chooseEntry(dictHead, primaryPool || [], engine) || (primaryPool && primaryPool.length ? primaryPool[0] : allEntries[0]);
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
        pos: upos || "",
        meta_pos: upos || "",
        lemma: token,
        lemma_form: token,
        feats: "",
        senses: mergedSenses,
        source: "DICT",
        senses_hover: hoverSenses,
        senses_hover_other: hoverOtherSenses,
        hover_has_alt_senses: !!hoverOtherSenses.length
      };
      if (Object.keys(formsMetaByHeader).length) result.senses_form_meta_by_header = formsMetaByHeader;
      if (Object.keys(hoverFormsMetaByHeader).length) result.senses_hover_form_meta_by_header = hoverFormsMetaByHeader;
      if (Object.keys(otherFormsMetaByHeader).length) result.senses_hover_other_form_meta_by_header = otherFormsMetaByHeader;
      if (best) applyFillRepresentativeEntry(result, best, false);
      setAtomicRenderEntries(result, allEntries, hoverEntries, otherEntries);
      attachWiktForms(result, dictHead, hoverEntries.length ? hoverEntries : allEntries);
    } else {
      result = {
        text: token,
        token_text: token,
        head: token,
        roman: "",
        pos: upos || "unknown",
        meta_pos: (fill && fill.has_known && !fill.has_unknown) ? "composite" : "unknown",
        lemma: token,
        lemma_form: token,
        feats: "",
        senses: [],
        source: (fill && fill.has_known && !fill.has_unknown) ? "COMPOSITE" : "UNKNOWN",
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
    result.upos_color = UPOS_COLORS[upos] || "#d1d5db";
    result.tag = xpos;
    result.xpos = xpos;
    result.seg_i = 0;
    result._korean_compound_child_precomputed = true;
    var childPartIndex = parseInt(child.part_index, 10);
    result._korean_compound_part_index = isFinite(childPartIndex) ? childPartIndex : 0;
    result._korean_compound_child_internal_fill = rawFills.length > 1;
    result.resolution_actual = buildLiveResolutionInfo(surfaceLookup.resolution_meta || null, rawFills, exactLemmaMatchCount);
    result.resolution_live = result.resolution_actual;
    if (lemmaOverrideParts.length) result.lemma_override_parts = lemmaOverrideParts.slice();
    return result;
  }

  function buildKoreanCompoundLemmaChildResults(childPayloads, engine, includeDebugTrace) {
    var children = Array.isArray(childPayloads) ? childPayloads : [];
    var out = [];
    for (var i = 0; i < children.length; i++) {
      var childResult = buildKoreanCompoundLemmaChildResult(children[i], engine, includeDebugTrace);
      if (!childResult) continue;
      out.push({
        text: String(children[i].text || childResult.text || "").trim(),
        source_text: String(children[i].source_text || children[i].text || childResult.text || "").trim(),
        part_index: isFinite(parseInt(children[i].part_index, 10)) ? parseInt(children[i].part_index, 10) : i,
        upos: String(children[i].upos || childResult.upos || "").trim(),
        xpos: String(children[i].xpos || childResult.xpos || "").trim(),
        lookup: childResult
      });
    }
    return out.length > 1 ? out : [];
  }

  function extractTokenBySeg(lookupData) {
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

  function buildResultsBySeg(lookupData, engine, options) {
    options = options || {};
    var includeDebugTrace = !!options.debug_trace;
    var precomputedSurfaceLookups = Array.isArray(options.precomputed_surface_lookups)
      ? options.precomputed_surface_lookups
      : null;
    var segments = Array.isArray(lookupData && lookupData.segments) ? lookupData.segments : [];
    var originalText = String(lookupData && lookupData.display_text || "");
    var segOffsets = Array.isArray(lookupData && lookupData.segment_offsets) ? lookupData.segment_offsets : null;
    var resultsBySeg = new Array(segments.length);
    var tokBySeg = extractTokenBySeg(lookupData);

    for (var i = 0; i < segments.length; i++) {
      var word = String(segments[i] || "");
      // Use original text slice for surface display when offsets are available
      var originalSlice = "";
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
      var upos = String(tok.upos || "X");
      var deprel = String(tok.dep || "dep");
      var xpos = String(tok.tag || "");
      var lemma = String(tok.lemma || "");
      var lemmaRaw = String(tok.lemma_raw || lemma || "");
      var lemmaSuffix = String(tok.lemma_suffix || "");
      var feats = String(tok.feats || "");

      if (!engine) {
        resultsBySeg[i] = buildUnknownResult(word, upos, xpos, deprel, lemma, feats, i, lemmaRaw, lemmaSuffix, surfaceWord, surfaceAnchor);
        continue;
      }

      // STAY AWAY DEAD CODE: active hybrid lookup precomputes surface lookups
      // in hybridSegmentAndHydrate() and passes them in via precomputed_surface_lookups.
      var surfaceLookup = precomputedSurfaceLookups && precomputedSurfaceLookups[i]
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
      if (includeDebugTrace && surfaceLookup && typeof surfaceLookup._debug_lookup_scoring === "object") {
        lookupScoring = {};
        for (var lookupKey in surfaceLookup._debug_lookup_scoring) {
          if (!Object.prototype.hasOwnProperty.call(surfaceLookup._debug_lookup_scoring, lookupKey)) continue;
          lookupScoring[lookupKey] = surfaceLookup._debug_lookup_scoring[lookupKey];
        }
      }
      var resolvedVia = String(surfaceLookup.resolved_via || "surface");
      var lemmaOracleUsed = !!surfaceLookup.lemma_oracle_used;
      var lemmaOracleOutcome = String(surfaceLookup.lemma_oracle_outcome || "");
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
      var preferredSenseFilterXpos = choosePreferredSenseFilterXpos(xpos, lemmaHintObjects, lemmaOverrideParts, engine);

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

        var entryFilterMode = String((fill && fill.mode) || "").trim().toLowerCase();
        var entryFilterKw = {};
        if (entryFilterMode === "greedy" || entryFilterMode === "lemma_greedy" || entryFilterMode === "lemma_partial_greedy" || entryFilterMode === "greedy_lemma_mismatch") {
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
          source: "DICT",
          senses_hover: hoverSenses,
          senses_hover_other: hoverOtherSenses,
          hover_has_alt_senses: !!hoverOtherSenses.length
        };

        if (Object.keys(formsMetaByHeader).length) entry.senses_form_meta_by_header = formsMetaByHeader;
        if (Object.keys(hoverFormsMetaByHeader).length) entry.senses_hover_form_meta_by_header = hoverFormsMetaByHeader;
        if (Object.keys(otherFormsMetaByHeader).length) entry.senses_hover_other_form_meta_by_header = otherFormsMetaByHeader;
      } else if (fill && fill.has_known && !fill.has_unknown) {
        entry = {
          head: word,
          roman: "",
          pos: upos,
          meta_pos: "composite",
          senses: [],
          source: "COMPOSITE",
          senses_hover: [],
          senses_hover_other: [],
          hover_has_alt_senses: false
        };
      } else {
        entry = {
          head: word,
          roman: "",
          pos: upos,
          meta_pos: "unknown",
          senses: [],
          source: "UNKNOWN",
          senses_hover: [],
          senses_hover_other: [],
          hover_has_alt_senses: false
        };
      }

      var primaryPool = hoverEntries.length ? hoverEntries : (preferredEntries || allEntries || []);
      var primaryEntry = chooseEntry(dictHead, primaryPool, engine) || (primaryPool.length ? primaryPool[0] : null);
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

      attachWiktForms(entry, dictHead, hoverEntries.length ? hoverEntries : (allEntries || []));
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
      entry.upos_color = UPOS_COLORS[upos] || "#d1d5db";
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
      entry.resolution_actual = buildLiveResolutionInfo(surfaceLookup.resolution_meta || null, rawFills, exactLemmaMatchCount);
      entry.resolution_live = entry.resolution_actual;
      if (includeDebugTrace) {
        if (surfaceLookup && surfaceLookup._debug_runtime_lemma_alignment && typeof surfaceLookup._debug_runtime_lemma_alignment === "object") {
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
        if (entry._debug_runtime_lemma_alignment && typeof entry._debug_runtime_lemma_alignment === "object") {
          scoringPatch.lemma_runtime_alignment = entry._debug_runtime_lemma_alignment;
        }
        if (!lookupScoring || typeof lookupScoring !== "object") lookupScoring = {};
        for (var scoringKey in scoringPatch) {
          if (!Object.prototype.hasOwnProperty.call(scoringPatch, scoringKey)) continue;
          lookupScoring[scoringKey] = scoringPatch[scoringKey];
        }
        entry._debug_lookup_scoring = lookupScoring;
        if (fill && fill.dp_debug && typeof fill.dp_debug === "object") {
          entry._debug_greedy_main = fill.dp_debug;
        }
      }

      resultsBySeg[i] = entry;
    }

    return resultsBySeg;
  }

  function buildLookupDpOnlyPayload(word, engine, options) {
    options = options || {};
    var lemmaHint = String(options.lemma || "");
    var uposHint = String(options.upos || "").trim().toUpperCase();
    var xposHint = String(options.xpos || "").trim();
    var mwtParts = Array.isArray(options.mwt_parts) ? options.mwt_parts : [];

    if (!word || !String(word).trim()) return { ok: false, error: "empty" };

    if (!engine) {
      var unknown = buildUnknownResult(String(word), uposHint || "unknown", xposHint, "dep", lemmaHint, "", 0);
      unknown.pos = "unknown";
      unknown.meta_pos = "unknown";
      return {
        ok: true,
        display_text: String(word),
        q: String(word),
        segments: [String(word)],
        segment_offsets: [[0, String(word).length]],
        results: [unknown],
        results_by_seg: [unknown],
        grammar_overlay: { tokens: [], links: [] },
        ud_overlay: {
          ok: false,
          tokens: [],
          edges: [],
          roots: [],
          ents: [],
          sentences: [],
          doc2seg: [],
          seg2doc: [-1],
          error: "dp_only"
        }
      };
    }

    var token = String(word);
    // STAY AWAY DEAD CODE: active hybrid dp-only lookup precomputes the
    // surface lookup in hybridDpOnlyLookupWithEngine() and passes it here.
    var surfaceLookup = options.surface_lookup || buildSinglePassSurfaceLookup(token, lemmaHint, engine, uposHint, xposHint, false, {
      skipWholeSurfaceExact: mwtParts.length > 1,
      mwt_parts: mwtParts
    });
    var fill = surfaceLookup.fill || null;
    var allEntries = surfaceLookup.all_entries || [];
    var preferredEntries = surfaceLookup.preferred_entries || allEntries;
    var dictHead = String(surfaceLookup.dict_head || token);
    var resolvedVia = String(surfaceLookup.resolved_via || "surface");
    var dpLemmaHints = (surfaceLookup.lemma_hint_data && surfaceLookup.lemma_hint_data.lemma_hint_objects) || [];
    var lemmaOracleUsed = !!surfaceLookup.lemma_oracle_used;
    var lemmaOracleOutcome = String(surfaceLookup.lemma_oracle_outcome || "");
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
    var preferredSenseFilterXpos = choosePreferredSenseFilterXpos(xposHint, dpLemmaHints, lemmaOverrideParts, engine);

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
      if (fillMode === "greedy" || fillMode === "lemma_greedy" || fillMode === "lemma_partial_greedy" || fillMode === "greedy_lemma_mismatch") {
        entryFilterKw.greedy_match = true;
      }
      if (shouldApplyStrictExactLemmaDisplayFilter(resolvedVia, exactLemmaMatchCount, preferredEntries)) {
        entryFilterKw.strict_exact_lemma_entries = preferredEntries.slice();
      }
      {
        var split = splitEntriesForHover(allEntries, uposHint || "", engine, preferredSenseFilterXpos, entryFilterKw);
        hoverEntries = split[0];
        otherEntries = split[1];
        hoverSenses = mergeAllEntries(dictHead, hoverEntries);
        hoverFormsMetaByHeader = buildJmdictFormsMetaByHeader(hoverEntries);
      }
      var primaryPool = hoverEntries.length ? hoverEntries : (preferredEntries || allEntries || []);
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
        pos: uposHint || "",
        meta_pos: uposHint || "",
        lemma: lemmaHint || "",
        feats: "",
        senses: mergedSenses,
        source: "DICT",
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
      if (Object.keys(hoverFormsMetaByHeader).length) result.senses_hover_form_meta_by_header = hoverFormsMetaByHeader;
      if (Object.keys(otherFormsMetaByHeader).length) result.senses_hover_other_form_meta_by_header = otherFormsMetaByHeader;
      if (Object.keys(formsMetaByHeader).length) result.senses_form_meta_by_header = formsMetaByHeader;
      result.resolved_via = resolvedVia;
      if (resolvedVia === "lemma_promoted" && !result.lemma_form) result.lemma_form = lemmaHint;
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
      result.resolution_actual = buildLiveResolutionInfo(surfaceLookup.resolution_meta || null, rawFills, exactLemmaMatchCount);
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
        roman: "",
        pos: "unknown",
        meta_pos: "unknown",
        lemma: lemmaHint || "",
        feats: "",
        senses: [],
        source: "UNKNOWN",
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
      result.resolution_actual = buildLiveResolutionInfo(surfaceLookup.resolution_meta || null, rawFills, exactLemmaMatchCount);
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
      grammar_overlay: { tokens: [], links: [] },
      ud_overlay: {
        ok: false,
        tokens: mwtParts.length ? [{
          i: 0,
          doc_i: 0,
          text: token,
          upos: uposHint || "X",
          tag: xposHint,
          dep: "dep",
          lemma: lemmaHint || "",
          lemma_raw: lemmaHint || "",
          lemma_suffix: "",
          feats: "",
          mwt_parts: mwtParts.slice()
        }] : [],
        edges: [],
        roots: [],
        ents: [],
        sentences: [],
        doc2seg: [],
        seg2doc: [-1],
        error: "dp_only"
      }
    };
  }

  function buildSubsegmentsPayload(token, engine, decompose) {
    // Dead decomposition path. Leave disconnected from active lookup flow.
    var tokenText = String(token || "");
    var fill = tokenText
      ? engine.fill_token(tokenText, { allowExact: !decompose, excludeWhole: !!decompose })
      : { fills: [] };
    var prepared = prepareFillEntries((fill && fill.fills) || [], engine, "", "", String((fill && fill.mode) || "greedy"));
    var mode = String((fill && fill.mode) || "greedy");

    if (decompose && tokenText) {
      prepared = prepared.filter(function(p) {
        return String((p || {}).head || "") !== tokenText;
      });
    }
    return {
      ok: true,
      token: tokenText,
      subsegments: prepared,
      mode: mode
    };
  }

  function buildMergedLookupPayload(lookupData, engine, options) {
    var merged = {};
    for (var key in lookupData) {
      if (Object.prototype.hasOwnProperty.call(lookupData, key)) merged[key] = lookupData[key];
    }
    var resultsBySeg = buildResultsBySeg(lookupData, engine, options || {});
    merged.results_by_seg = resultsBySeg;
    merged.results = [];
    for (var i = 0; i < resultsBySeg.length; i++) {
      var entry = resultsBySeg[i];
      if (entry && entry.source !== "PUNCT") {
        merged.results.push(entry);
        break;
      }
    }
    return merged;
  }

  function buildEngineFromRows(langCode, rows) {
    if (!window.DictionaryEngine) {
      throw new Error("DictionaryEngine is not available");
    }
    var engine = new window.DictionaryEngine(langCode);
    engine.load_tsv_entries(rows || []);
    return engine;
  }

  function cloneUint8Array(bytes) {
    if (!bytes || !bytes.length) return new Uint8Array(0);
    return bytes.slice ? bytes.slice(0) : new Uint8Array(bytes);
  }

  function countEngineEntries(engine) {
    if (!engine || !engine._by_word) return 0;
    var keys = Object.keys(engine._by_word);
    var total = 0;
    for (var i = 0; i < keys.length; i++) {
      var bucket = engine._by_word[keys[i]];
      if (Array.isArray(bucket)) total += bucket.length;
    }
    return total;
  }

  function buildDictProgressMessage(prefix, rows, bytes) {
    var msg = String(prefix || "Building... ") + String(rows || 0) + " entries";
    var kb = Math.round((Number(bytes) || 0) / 1024);
    if (kb > 1024) msg += " (" + (kb / 1024).toFixed(1) + " MB)";
    return msg;
  }

  function formatProgressMegabytes(bytes) {
    var mb = Math.max(0, Number(bytes) || 0) / 1048576;
    return mb.toFixed(mb >= 100 ? 0 : 1);
  }

  function formatProgressCount(value) {
    return Math.max(0, Math.round(Number(value) || 0)).toLocaleString();
  }

  function buildDownloadProgressMessage(received, total) {
    var downloadedMb = formatProgressMegabytes(received);
    if (!(total > 0)) return "Downloading\u2026 " + downloadedMb + " MB";
    var totalMb = formatProgressMegabytes(total);
    var remainingMb = formatProgressMegabytes(Math.max(0, total - received));
    return "Downloading\u2026 " + downloadedMb + " / " + totalMb + " MB, " + remainingMb + " MB left";
  }

  function buildIndexDownloadProgressMessage(received, total) {
    var loadedMb = formatProgressMegabytes(received);
    if (!(total > 0)) return "Downloading index... " + loadedMb + " MB";
    var totalMb = formatProgressMegabytes(total);
    return "Downloading index... " + loadedMb + " / " + totalMb + " MB";
  }

  function buildIndexOpenProgressMessage(received, total) {
    var loadedMb = formatProgressMegabytes(received);
    if (!(total > 0)) return "Opening index... " + loadedMb + " MB";
    var totalMb = formatProgressMegabytes(total);
    return "Opening index... " + loadedMb + " / " + totalMb + " MB";
  }

  function buildAssemblyProgressMessage(done, total, label) {
    var msg = "Assembling\u2026 ";
    if (total > 0) {
      msg += formatProgressCount(done) + " / " + formatProgressCount(total) + " items";
    } else {
      msg += formatProgressCount(done) + " items";
    }
    if (label) msg += " (" + String(label) + ")";
    return msg;
  }

  function buildGeminiAdditionProgressMessage(processed, total, loaded) {
    var msg = "Loading additions\u2026 ";
    if (total > 0) {
      msg += formatProgressCount(processed) + " / " + formatProgressCount(total) + " rows";
    } else {
      msg += formatProgressCount(processed) + " rows";
    }
    if (loaded > 0) msg += " (" + formatProgressCount(loaded) + " loaded)";
    return msg;
  }

  function buildEngineFromGzipBytes(langCode, key, gzBytes, opts) {
    opts = opts || {};
    var code = String(langCode || "").toLowerCase();
    var bytes = opts.preserveSource ? cloneUint8Array(gzBytes) : gzBytes;
    if (!bytes || !bytes.length) return Promise.resolve(null);

    var showProgress = !!opts.showProgress;
    var progressBasePct = Number(opts.progressBasePct || 0);
    var progressSpanPct = Number(opts.progressSpanPct || 18);
    var progressPrefix = String(opts.progressPrefix || "Building... ");
    var summary = opts.summary || null;
    // Estimate total decompressed size as ~10x gzip size for linear progress
    var estimatedTotalBytes = (bytes ? bytes.length : 0) * 10;
    var lastProgressPct = progressBasePct;

    if (showProgress) {
      showDictProgress(progressBasePct, String(progressPrefix || "Building...").trim());
    }

    var progressCb = showProgress ? function(rows, parsedBytes, phase, progressMeta) {
      if (summary) {
        summary.rows = Number(rows || 0);
        summary.bytes = Number(parsedBytes || 0);
      }
      // Linear progress based on decompressed bytes vs estimated total
      var fraction = estimatedTotalBytes > 0
        ? Math.max(0, Math.min(0.98, (parsedBytes || 0) / estimatedTotalBytes))
        : Math.min(0.98, 1 - 1 / (1 + (rows || 0) / 5000));
      var pct = progressBasePct + Math.round(progressSpanPct * fraction);
      pct = Math.max(lastProgressPct, Math.min(progressBasePct + progressSpanPct - 1, pct));
      lastProgressPct = pct;
      showDictProgress(pct, buildDictProgressMessage(progressPrefix, rows, parsedBytes));
    } : null;

    return buildEngineStreaming(code, bytes, progressCb, key).then(function(engine) {
      if (!engine) return null;
      engine._dcCacheKey = key;
      state.engineByLangSource[key] = engine;
      return engine;
    });
  }

  /**
   * Discover the versioned script URLs for the normalization layer and engine
   * from the current page's <script> tags, so the Worker can importScripts them.
   */
  function _discoverEngineScriptUrls() {
    var scripts = document.getElementsByTagName("script");
    var normUrl = "";
    var engineUrl = "";
    var clientUrl = "";
    for (var i = 0; i < scripts.length; i++) {
      var src = scripts[i].src || "";
      if (!normUrl && src.indexOf("dictionary_normalization_layer") >= 0) normUrl = src;
      if (!engineUrl && src.indexOf("dictionary_engine") >= 0) engineUrl = src;
      if (!clientUrl && src.indexOf("dictionary_client") >= 0) clientUrl = src;
    }
    return { normUrl: normUrl, engineUrl: engineUrl, clientUrl: clientUrl };
  }

  /**
   * Build a dictionary engine in a Web Worker off the main thread.
   * Streams decompress → parse → build, posts progress to main thread.
   * Falls back to main-thread streaming if Workers or streaming APIs are unavailable.
   */
  function buildEngineStreaming(langCode, gzBytes, onProgress, engineKey) {
    if (!window.DictionaryEngine) {
      throw new Error("DictionaryEngine is not available");
    }

    // Try Worker path first — engine stays permanently in worker
    if (typeof Worker === "function" && typeof DecompressionStream === "function" && engineKey) {
      try {
        return _buildEngineInWorker(langCode, gzBytes, onProgress, engineKey);
      } catch (_e) {
        // Worker creation failed (CSP, etc.) — fall through to main-thread
      }
    }

    // Main-thread fallback: streaming if available, else classic
    return _buildEngineMainThread(langCode, gzBytes, onProgress);
  }

  /**
   * Main-thread streaming fallback (no Worker).
   */
  function _buildEngineMainThread(langCode, gzBytes, onProgress) {
    if (typeof DecompressionStream !== "function" || typeof TextDecoderStream !== "function") {
      // Classic pipeline
      return gunzipToText(gzBytes).then(function(tsvText) {
        var rows = parseTsvText(tsvText);
        tsvText = null;
        if (!rows.length) return null;
        var engine = buildEngineFromRows(langCode, rows);
        rows = null;
        return engine;
      });
    }
    var code = String(langCode || "").toLowerCase();
    var engine = new window.DictionaryEngine(code);
    var ds = new DecompressionStream("gzip");
    var blob = new Blob([gzBytes], { type: "application/gzip" });
    var textStream = blob.stream().pipeThrough(ds).pipeThrough(new TextDecoderStream());
    var reader = textStream.getReader();
    var headers = null;
    var partial = "";
    var lineNo = 0;
    var totalLoaded = 0;
    var bytesRead = 0;
    var lastProgressAt = 0;

    function processLine(line) {
      if (!line.trim()) return;
      lineNo++;
      if (!headers) {
        headers = line.split("\t");
        return;
      }
      var fields = line.split("\t");
      var row = {};
      for (var j = 0; j < headers.length; j++) {
        row[String(headers[j] || "").trim()] = (j < fields.length) ? fields[j] : "";
      }
      if (engine._loadOneRow(row)) totalLoaded++;
    }

    function pump() {
      return reader.read().then(function(result) {
        if (result.done) {
          if (partial) { processLine(partial); partial = ""; }
          return totalLoaded > 0 ? engine : null;
        }
        bytesRead += result.value.length;
        var chunk = partial + result.value;
        var lines = chunk.split(/\r?\n/);
        partial = lines[lines.length - 1];
        for (var i = 0; i < lines.length - 1; i++) {
          processLine(lines[i]);
        }
        if (typeof onProgress === "function") {
          var now = Date.now();
          if (now - lastProgressAt > 80) {
            lastProgressAt = now;
            onProgress(totalLoaded, bytesRead, "parsing");
          }
        }
        return pump();
      });
    }

    return pump();
  }

  /**
   * Generate the Worker inline JS source. Shared by gz-build and row-build paths.
   */
  function _getWorkerCode(urls) {
    return [
      // Shim: Workers have no `window` or `document`
      "var window = self;",
      "var document = {",
      "  getElementById: function() { return null; },",
      "  addEventListener: function() {},",
      "  removeEventListener: function() {},",
      "  getElementsByTagName: function() { return []; },",
      "  querySelectorAll: function() { return []; },",
      "  createElement: function() { return { style: {} }; }",
      "};",
      "",
      // Import the scripts (normalization layer, engine, then client for payload builders)
      urls.normUrl ? ("importScripts(" + JSON.stringify(urls.normUrl) + ");") : "",
      "importScripts(" + JSON.stringify(urls.engineUrl) + ");",
      urls.clientUrl ? ("importScripts(" + JSON.stringify(urls.clientUrl) + ");") : "",
      "",
      // Global engine storage — shared between build handler and query handler
      "if (!self._workerEngines) self._workerEngines = {};",
      "",
      "self.onmessage = function(e) {",
      "  var data = e.data;",
      "",
      "  if (data.type === 'build_rows') {",
      "    var rCode = String(data.langCode || '').toLowerCase();",
      "    var rEngine = new self.DictionaryEngine(rCode);",
      "    var rRows = data.rows || [];",
      "    rEngine.load_tsv_entries(rRows);",
      "    self._workerEngines[data.engineKey || rCode] = rEngine;",
      "    self.postMessage({ type: 'done', langCode: rCode, rows: rRows.length, engineKey: data.engineKey || rCode });",
      "    return;",
      "  }",
      "",
      "  if (data.type !== 'build') return;",
      "  var langCode = data.langCode;",
      "  var gzBytes = data.gzBytes;",
      "  var engineKey = data.engineKey || '';",
      "  var code = String(langCode || '').toLowerCase();",
      "  var engine = new self.DictionaryEngine(code);",
      "  var ds = new DecompressionStream('gzip');",
      "  var blob = new Blob([gzBytes], { type: 'application/gzip' });",
      "  var textStream = blob.stream().pipeThrough(ds).pipeThrough(new TextDecoderStream());",
      "  var reader = textStream.getReader();",
      "  var headers = null;",
      "  var partial = '';",
      "  var lineNo = 0;",
      "  var totalLoaded = 0;",
      "  var lastProgressAt = 0;",
      "  var bytesRead = 0;",
      "",
      "  function processLine(line) {",
      "    if (!line.trim()) return;",
      "    lineNo++;",
      "    if (!headers) { headers = line.split('\\t'); return; }",
      "    var fields = line.split('\\t');",
      "    var row = {};",
      "    for (var j = 0; j < headers.length; j++) {",
      "      row[String(headers[j] || '').trim()] = (j < fields.length) ? fields[j] : '';",
      "    }",
      "    if (engine._loadOneRow(row)) totalLoaded++;",
      "  }",
      "",
      "  function sendProgress() {",
      "    var now = Date.now();",
      "    if (now - lastProgressAt < 80) return;",
      "    lastProgressAt = now;",
      "    self.postMessage({ type: 'progress', phase: 'parsing', rows: totalLoaded, bytes: bytesRead });",
      "  }",
      "",
      "  function pump() {",
      "    return reader.read().then(function(result) {",
      "      if (result.done) {",
      "        if (partial) { processLine(partial); partial = ''; }",
      "        if (totalLoaded === 0) {",
      "          self.postMessage({ type: 'done', langCode: code, rows: 0, engineKey: engineKey });",
      "          return;",
      "        }",
      "        // Store engine permanently in worker — no transfer to main thread",
      "        self._workerEngines[engineKey] = engine;",
      "        self.postMessage({ type: 'done', langCode: code, rows: totalLoaded, engineKey: engineKey });",
      "        return;",
      "      }",
      "      bytesRead += result.value.length;",
      "      var chunk = partial + result.value;",
      "      var lines = chunk.split(/\\r?\\n/);",
      "      partial = lines[lines.length - 1];",
      "      for (var i = 0; i < lines.length - 1; i++) {",
      "        processLine(lines[i]);",
      "      }",
      "      sendProgress();",
      "      return pump();",
      "    });",
      "  }",
      "",
      "  pump().catch(function(err) {",
      "    self.postMessage({ type: 'error', message: String(err.message || err) });",
      "  });",
      "};"
    ].join("\n");
  }

  function _buildEngineInWorker(langCode, gzBytes, onProgress, engineKey) {
    var urls = _discoverEngineScriptUrls();
    if (!urls.engineUrl) {
      throw new Error("Cannot find engine script URL for Worker");
    }
    if (!urls.clientUrl) {
      throw new Error("Cannot find dictionary_client script URL for Worker");
    }

    var workerCode = _getWorkerCode(urls);
    var workerBlob = new Blob([workerCode], { type: "application/javascript" });
    var workerUrl = URL.createObjectURL(workerBlob);
    var worker = new Worker(workerUrl);

    // Wire up the worker query handler for dictionary_client.js worker mode
    worker.addEventListener("message", function(e) {
      var msg = e.data;
      if (msg.type === "query_result" && msg.requestId) {
        var cb = state.workerCallbacks[msg.requestId];
        if (cb) {
          delete state.workerCallbacks[msg.requestId];
          if (msg.error) {
            cb.reject(new Error(msg.error));
          } else {
            cb.resolve(msg.payload);
          }
        }
      }
    });

    return new Promise(function(resolve, reject) {
      worker.onmessage = function(e) {
        var msg = e.data;
        if (msg.type === "progress") {
          if (typeof onProgress === "function") {
            onProgress(msg.rows, msg.bytes, msg.phase || "parsing", msg);
          }
          return;
        }
        if (msg.type === "error") {
          worker.terminate();
          URL.revokeObjectURL(workerUrl);
          delete state.activeWorkers[engineKey];
          reject(new Error(msg.message || "Worker build failed"));
          return;
        }
        if (msg.type === "done") {
          if (msg.rows === 0) {
            worker.terminate();
            URL.revokeObjectURL(workerUrl);
            delete state.activeWorkers[engineKey];
            resolve(null);
            return;
          }
          // Worker keeps the engine — store worker reference, return proxy
          state.activeWorkers[engineKey] = { worker: worker, blobUrl: workerUrl };
          var proxy = {
            _isWorkerProxy: true,
            _workerKey: engineKey,
            _dcCacheKey: engineKey,
            _lang_code: langCode
          };
          resolve(proxy);
          return;
        }
      };
      worker.onerror = function(err) {
        worker.terminate();
        URL.revokeObjectURL(workerUrl);
        delete state.activeWorkers[engineKey];
        reject(err);
      };
      // Transfer the ArrayBuffer (zero-copy)
      var buffer = gzBytes.buffer;
      worker.postMessage(
        { type: "build", langCode: langCode, gzBytes: gzBytes, engineKey: engineKey },
        [buffer]
      );
    });
  }

  function _queryWorker(engineKey, message) {
    var winfo = state.activeWorkers[engineKey];
    if (!winfo || !winfo.worker) {
      return Promise.reject(new Error("No active worker for key: " + engineKey));
    }
    var requestId = state.nextRequestId++;
    message.requestId = requestId;
    message.engineKey = engineKey;
    return new Promise(function(resolve, reject) {
      state.workerCallbacks[requestId] = { resolve: resolve, reject: reject };
      winfo.worker.postMessage(message);
    });
  }

  function _getActiveWorkerKey(langCode) {
    var source = getDictSource();
    var key = cacheKey(langCode, source);
    if (state.activeWorkers[key]) return key;
    // Check all keys for this language
    var prefix = String(langCode || "").toLowerCase() + "|";
    var keys = Object.keys(state.activeWorkers);
    for (var i = 0; i < keys.length; i++) {
      if (keys[i].indexOf(prefix) === 0) return keys[i];
    }
    return "";
  }

  /**
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

  function _reconstructEngineFromWorkerData(langCode, byWord, formIndex) {
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

  function filterAugmentEntriesByEngine(entries, builtinEngine) {
    var src = Array.isArray(entries) ? entries : [];
    if (!builtinEngine || !builtinEngine._by_word) return src;
    var lookupKeyFn = window.DictionaryEngine && window.DictionaryEngine.lookupKey;
    var langCode = builtinEngine._lang_code || "";
    var out = [];
    for (var i = 0; i < src.length; i++) {
      var entry = src[i] || {};
      var head = String(entry.headword || "");
      if (head) {
        // On-demand headword check via _by_word hash lookup — O(1), no pre-built set
        var key = lookupKeyFn ? lookupKeyFn(head, langCode) : head.toLowerCase();
        var bucket = builtinEngine._by_word[key];
        if (bucket) {
          // Verify exact headword match (not just key collision)
          var found = false;
          for (var bi = 0; bi < bucket.length; bi++) {
            if (String((bucket[bi] || {}).headword || "") === head) { found = true; break; }
          }
          if (found) continue;
        }
      }
      out.push(entry);
    }
    return out;
  }

  function buildAugmentedBrowserEngine(langCode, builtinEngine, customEngine) {
    if (!builtinEngine && !customEngine) return null;
    if (builtinEngine && !customEngine) return builtinEngine;
    if (!builtinEngine && customEngine) return customEngine;

    var code = String(langCode || "").toLowerCase();
    var merged = new window.DictionaryEngine(code);

    function mergeEntriesFromMethod(methodName, word) {
      var primary = [];
      var extra = [];
      if (builtinEngine && typeof builtinEngine[methodName] === "function") {
        primary = builtinEngine[methodName](word) || [];
      }
      if (customEngine && typeof customEngine[methodName] === "function") {
        extra = filterAugmentEntriesByEngine(customEngine[methodName](word) || [], builtinEngine);
      }
      if (!extra.length) return Array.isArray(primary) ? primary : [];
      return (Array.isArray(primary) ? primary.slice() : []).concat(extra);
    }

    merged.lookup_all = function(word) {
      return mergeEntriesFromMethod("lookup_all", word);
    };
    merged.lookupAll = function(word) {
      return merged.lookup_all(word);
    };
    merged.lookup_display_only = function(word) {
      return mergeEntriesFromMethod("lookup_display_only", word);
    };
    merged.lookupDisplayOnly = function(word) {
      return merged.lookup_display_only(word);
    };
    merged.lookup_via_forms = function(word) {
      return mergeEntriesFromMethod("lookup_via_forms", word);
    };
    merged.lookupViaForms = function(word) {
      return merged.lookup_via_forms(word);
    };
    return merged;
  }

  function resolveLanguageMetaItem(langCode) {
    return loadLanguageMeta().then(function(metaByCode) {
      return metaByCode[String(langCode || "").toLowerCase()] || {};
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

  function getCompactIndexUrl(langCode, source) {
    var code = String(langCode || "").toLowerCase();
    var src = String(source || "").toLowerCase();
    var urls = window.APP_DICT_INDEX_URLS || null;
    var key = code + (src ? ":" + src : "");
    var url = urls && typeof urls === "object" ? String(urls[key] || "") : "";
    if (!url && (src === "wiktionary" || src === "default")) {
      url = urls && typeof urls === "object" ? String(urls[code] || "") : "";
    }
    return url;
  }

  function getGzipUncompressedSize(gzBytes) {
    if (!gzBytes || gzBytes.length < 4) return 0;
    var len = gzBytes.length;
    return (
      (gzBytes[len - 4]) |
      (gzBytes[len - 3] << 8) |
      (gzBytes[len - 2] << 16) |
      (gzBytes[len - 1] << 24)
    ) >>> 0;
  }

  // Decompress gzip bytes to JSON string, firing onProgress(bytesOut, totalOut) per chunk.
  function _decompressGzWithProgress(gzBytes, onProgress) {
    var totalOut = getGzipUncompressedSize(gzBytes);
    if (typeof DecompressionStream === "function") {
      var ds = new DecompressionStream("gzip");
      var blob = new Blob([gzBytes], { type: "application/gzip" });
      var textStream = blob.stream().pipeThrough(ds).pipeThrough(new TextDecoderStream());
      var reader = textStream.getReader();
      var parts = [];
      var bytesOut = 0;
      function readChunk() {
        return reader.read().then(function(r) {
          if (r.done) return parts.join("");
          parts.push(r.value);
          bytesOut += r.value.length;
          if (typeof onProgress === "function") onProgress(bytesOut, totalOut);
          return new Promise(function(res) { setTimeout(res, 0); }).then(readChunk);
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
  function fetchCompactIndex(langCode, source, onDownloadProgress, onDecompressProgress) {
    var code = String(langCode || "").toLowerCase();
    var src = String(source || "").toLowerCase();
    var cacheKeyStr = code + (src ? ":" + src : "");
    if (_hybridIndexPromise[cacheKeyStr]) return _hybridIndexPromise[cacheKeyStr];

    var url = getCompactIndexUrl(code, src);
    if (!url) {
      throw new Error("Missing prebuilt index artifact for " + (cacheKeyStr || code));
    }

    function _loadIndexGz() {
      return fetch(url).then(function(resp) {
        if (!resp.ok) throw new Error("index fetch failed: " + resp.status);
        var contentLength = parseInt(resp.headers.get("Content-Length") || "0", 10) || 0;
        var received = 0;
        if (typeof onDownloadProgress === "function") onDownloadProgress(0, contentLength);
        if (!resp.body || typeof resp.body.getReader !== "function") {
          return resp.arrayBuffer().then(function(buf) {
            var merged = new Uint8Array(buf);
            if (typeof onDownloadProgress === "function") onDownloadProgress(merged.length, merged.length);
            return merged;
          });
        }
        var reader = resp.body.getReader();
        var chunks = [];
        function readChunk() {
          return reader.read().then(function(result) {
            if (result.done) {
              var totalLen = 0;
              for (var i = 0; i < chunks.length; i++) totalLen += chunks[i].length;
              var merged = new Uint8Array(totalLen);
              var off = 0;
              for (var i = 0; i < chunks.length; i++) { merged.set(chunks[i], off); off += chunks[i].length; }
              return merged;
            }
            chunks.push(result.value);
            received += result.value.length;
            if (typeof onDownloadProgress === "function") onDownloadProgress(received, contentLength);
            return new Promise(function(res) { setTimeout(res, 0); }).then(readChunk);
          });
        }
        return readChunk();
      });
    }

    function _parseGz(gzBytes) {
      return _decompressGzWithProgress(gzBytes, onDecompressProgress).then(function(text) {
        return JSON.parse(text);
      });
    }

    var promise = Promise.resolve().then(function() {
      var cachedIndex = _hybridIndexByLang[cacheKeyStr] || null;
      if (cachedIndex) return cachedIndex;
      return _loadIndexGz().then(function(gzBytes) { return _parseGz(gzBytes); });
    });

    _hybridIndexPromise[cacheKeyStr] = promise.then(function(index) {
      delete _hybridIndexPromise[cacheKeyStr];
      _hybridIndexByLang[cacheKeyStr] = index;
      return index;
    }, function(err) {
      delete _hybridIndexPromise[cacheKeyStr];
      throw err;
    });
    return _hybridIndexPromise[cacheKeyStr];
  }

  /**
   * Ensure a compact-mode DictionaryEngine is loaded for langCode.
   * Returns Promise<engine>.
   */
  function ensureBuiltinEngine(langCode, opts) {
    opts = opts || {};
    var code = String(langCode || "").toLowerCase();
    var src = String(opts.source || "").toLowerCase();
    var key = cacheKey(code, src || "hybrid");
    if (state.readyPromiseByLangSource[key]) return state.readyPromiseByLangSource[key];

    var showP = !!opts.showProgress;

    function loadFreshEngine() {
      // Progress ranges:
      //   0%->70%  Downloading the prebuilt artifact bytes
      //  70%->94%  Opening the artifact in memory
      //  94%->99%  Injecting custom entries (ticked per entry)
      // 100%       Ready

      if (showP) showDictProgress(0, buildIndexDownloadProgressMessage(0, 0));

      var dlLastPaintAt = 0;
      var downloadProgressCb = showP ? function(received, total) {
        var now = Date.now();
        if (now - dlLastPaintAt < 80 && received !== total) return;
        dlLastPaintAt = now;
        var pct = total > 0
          ? Math.min(70, Math.round(70 * received / total))
          : Math.min(70, Math.round(70 * received / (received + 524288)));
        showDictProgress(pct, buildIndexDownloadProgressMessage(received, total));
      } : null;

      var decompLastPaintAt = 0;
      var lastOpenBytesOut = 0;
      var lastOpenTotalOut = 0;
      var decompProgressCb = showP ? function(bytesOut, totalOut) {
        var now = Date.now();
        if (now - decompLastPaintAt < 80) return;
        decompLastPaintAt = now;
        lastOpenBytesOut = bytesOut;
        lastOpenTotalOut = totalOut;
        var pct = totalOut > 0
          ? Math.min(94, 70 + Math.round(24 * bytesOut / totalOut))
          : Math.min(94, 70 + Math.round(24 * bytesOut / (bytesOut + 524288)));
        showDictProgress(pct, buildIndexOpenProgressMessage(bytesOut, totalOut));
      } : null;

      var promise = fetchCompactIndex(code, src, downloadProgressCb, decompProgressCb).then(function(index) {
        if (!index) throw new Error("No compact index for " + code);
        if (!window.DictionaryEngine) throw new Error("DictionaryEngine not loaded");

        if (showP) showDictProgress(94, buildIndexOpenProgressMessage(lastOpenBytesOut, lastOpenTotalOut));
        var engine = new window.DictionaryEngine(code);
        engine.loadCompactIndex(index.hw || {}, index.fw || {}, index.db_aliases || {});
        engine._dcCacheKey = key;
        engine._hybridLang = code;
        engine._dcIndexVersion = String(index.version || "");
        state.engineByLangSource[key] = engine;

        if (!showP) return engine;

        if (showP) showDictProgress(94, buildGeminiAdditionProgressMessage(0, 0, 0));
        return _injectGeminiAdditions(engine, code, function(processed, total, loaded) {
          if (total <= 0) return;
          var pct = Math.min(99, 94 + Math.round(5 * processed / total));
          showDictProgress(pct, buildGeminiAdditionProgressMessage(processed, total, loaded));
        }).then(function() { return engine; });

      }).finally(function() {
        if (showP) {
          showDictProgress(100, "Ready");
          setTimeout(hideDictProgress, 1000);
        }
      });

      state.readyPromiseByLangSource[key] = promise.then(function(engine) {
        delete state.readyPromiseByLangSource[key];
        return engine;
      }, function(err) {
        delete state.readyPromiseByLangSource[key];
        throw err;
      });
      return state.readyPromiseByLangSource[key];
    }

    var existingEngine = state.engineByLangSource[key];
    if (existingEngine) {
      // Engine already exists in tab memory.
      return Promise.resolve(existingEngine);
    }

    var cacheKeyStr = code + (src ? ":" + src : "");
    var currentIndex = _hybridIndexByLang[cacheKeyStr];
    if (currentIndex && state.engineByLangSource[key]) {
      var currentIndexVersion = String(currentIndex.version || "");
      var engineVersion = String(state.engineByLangSource[key]._dcIndexVersion || "");
      if (!currentIndexVersion || currentIndexVersion === engineVersion) {
        return Promise.resolve(state.engineByLangSource[key]);
      }
    }

    return loadFreshEngine();
  }

  function ensureCustomEngine(langCode, opts) {
    opts = opts || {};
    var code = String(langCode || "").toLowerCase();
    var record = getCustomUploadRecord(code);
    if (!record || !record.gz || !record.gz.length) return Promise.resolve(null);
    var key = cacheKey(code, "custom");
    if (state.engineByLangSource[key]) {
      state.engineByLangSource[key]._dcCacheKey = key;
      return Promise.resolve(state.engineByLangSource[key]);
    }
    if (state.readyPromiseByLangSource[key]) return state.readyPromiseByLangSource[key];

    var summary = { rows: 0, bytes: 0 };
    var promise = Promise.resolve().then(function() {
      return buildEngineFromGzipBytes(code, key, record.gz, {
        showProgress: !!opts.showProgress,
        progressBasePct: 20,
        progressSpanPct: 78,
        progressPrefix: "Building... ",
        preserveSource: true,
        summary: summary
      });
    }).then(function(engine) {
      if (engine) {
        record.entry_count = summary.rows > 0 ? summary.rows : countEngineEntries(engine);
      }
      return engine;
    }).finally(function() {
      if (opts.showProgress) {
        showDictProgress(100, "Ready");
        setTimeout(hideDictProgress, 1000);
      }
    });

    state.readyPromiseByLangSource[key] = promise.then(function(engine) {
      delete state.readyPromiseByLangSource[key];
      return engine;
    }, function(err) {
      delete state.readyPromiseByLangSource[key];
      throw err;
    });
    return state.readyPromiseByLangSource[key];
  }

  function ensureAugmentedCustomEngine(langCode, opts) {
    opts = opts || {};
    var code = String(langCode || "").toLowerCase();
    if (!code) return Promise.resolve(null);
    var record = getCustomUploadRecord(code);
    if (!record || !record.gz || !record.gz.length) return Promise.resolve(null);
    return resolveLanguageMetaItem(code).then(function(meta) {
      void meta;
      var key = cacheKey(code, "custom_augmented");
      if (state.engineByLangSource[key]) {
        state.engineByLangSource[key]._dcCacheKey = key;
        return state.engineByLangSource[key];
      }
      if (state.readyPromiseByLangSource[key]) return state.readyPromiseByLangSource[key];

      var promise = Promise.all([
        ensureBuiltinEngine(code, { showProgress: false }),
        ensureCustomEngine(code, { showProgress: !!opts.showProgress })
      ]).then(function(parts) {
          var engine = buildAugmentedBrowserEngine(code, parts[0], parts[1]);
          if (engine) {
            engine._dcCacheKey = key;
            state.engineByLangSource[key] = engine;
          }
          return engine;
      });

      state.readyPromiseByLangSource[key] = promise.then(function(engine) {
        delete state.readyPromiseByLangSource[key];
        return engine;
      }, function(err) {
        delete state.readyPromiseByLangSource[key];
        throw err;
      });
      return state.readyPromiseByLangSource[key];
    });
  }

  function ensureLanguageEngine(langCode, opts) {
    opts = opts || {};
    var source = opts.source || getDictSource();
    var code = String(langCode || "").toLowerCase();
    if (!code) return Promise.resolve(null);
    var loader = (source === "custom")
      ? ensureCustomEngine(code, { showProgress: !!opts.showProgress })
      : ensureBuiltinEngine(code, { showProgress: !!opts.showProgress, source: source });
    return Promise.resolve(loader).then(function(engine) {
      if (requestMatchesCurrentSelection(code, source)) {
        var keepKey = String((engine && engine._dcCacheKey) || findEngineCacheKey(engine) || "");
        evictAllEnginesExcept(keepKey);
      }
      return engine;
    });
  }

  function onLanguageDictSync(langCode) {
    var code = String(langCode || "").toLowerCase();
    if (!code) return Promise.resolve(null);
    hideTsvPill();
    var source = getDictSource();
    if (!source) {
      hideDictProgress();
      setStatus("");
      return Promise.resolve(null);
    }
    if (source === "custom") {
      hideDictProgress();
      var record = getCustomUploadRecord(code);
      if (record && record.gz && record.gz.length) {
        showTsvPill(customUploadLabel(record));
        return ensureLanguageEngine(code, { source: "custom", showProgress: true });
      }
      evictAllEnginesExcept("");
      evictBuiltinIndexMemoryExcept("");
      setStatus("No custom dictionary loaded.");
      return Promise.resolve(null);
    }
    var targetEngineKey = cacheKey(code, String(source || "").toLowerCase() || "hybrid");
    var targetIndexKey = code + (source ? ":" + String(source || "").toLowerCase() : "");
    evictAllEnginesExcept(targetEngineKey);
    evictBuiltinIndexMemoryExcept(targetIndexKey);
    return ensureLanguageEngine(code, { source: source, showProgress: true }).then(function(engine) {
      evictAllEnginesExcept(targetEngineKey);
      evictBuiltinIndexMemoryExcept(targetIndexKey);
      if (!engine) setStatus("No dictionary available for this language.");
      return engine;
    }).catch(function(err) {
      console.error("ensureBuiltinEngine error for " + code + ":", err);
      hideDictProgress();
      if (err && typeof err.message === "string" && err.message.indexOf("Missing prebuilt index artifact") >= 0) {
        setStatus(err.message);
      } else {
        setStatus("Dictionary load error.");
      }
      return null;
    });
  }

  function handleCustomUploadFile(file) {
    var lang = getCurrentLanguage();
    if (!lang) return Promise.resolve();
    showTsvPill(String(file && file.name ? file.name : "custom.tsv"));
    showDictProgress(10, "Compressing upload...");
    return gzipBlobToUint8(file).then(function(gzBytes) {
      if (!gzBytes || !gzBytes.length) throw new Error("Could not compress TSV file.");
      setCustomUploadRecord(lang, {
        file_name: String(file && file.name ? file.name : "custom.tsv"),
        gz: gzBytes,
        uploaded_at: Date.now(),
        source_size: Number((file && file.size) || 0),
        entry_count: 0
      });
      evictCustomEngineCache(lang);
      return ensureLanguageEngine(lang, { source: "custom", showProgress: true }).then(function() {
        var record = getCustomUploadRecord(lang);
        if (record) showTsvPill(customUploadLabel(record));
        setStatus("Custom TSV active.");
      });
    }).catch(function(err) {
      clearCustomUploadRecord(lang);
      evictCustomEngineCache(lang);
      hideTsvPill();
      hideDictProgress();
      console.error("TSV load error:", err);
      setStatus("Error loading TSV dictionary.");
      throw err;
    });
  }

  function resetCustomForCurrentLanguage() {
    var lang = getCurrentLanguage();
    hideTsvPill();
    if (!lang) return Promise.resolve();
    clearCustomUploadRecord(lang);
    evictCustomEngineCache(lang);
    if (getDictSource() === "custom") {
      evictAllEnginesExcept("");
    }
    setStatus("Custom dictionary cleared.");
    return Promise.resolve();
  }

  function prefetchAllBuiltinDicts() {
    // Disabled — dictionaries are now downloaded on-demand when user selects a source.
    return Promise.resolve();
  }

  function bindUi() {
    ui.statusText = document.getElementById("statusText");
    ui.languageSelect = document.getElementById("languageSelect");
    ui.dictSourceSelect = document.getElementById("dictSourceSelect");
    ui.tsvUploadLabel = document.getElementById("tsvUploadLabel");
    ui.tsvFileInput = document.getElementById("tsvFileInput");
    ui.tsvPill = document.getElementById("tsvPill");
    ui.tsvFileName = document.getElementById("tsvFileName");
    ui.clearTsvBtn = document.getElementById("clearTsvBtn");
    ui.dictProgressWrap = document.getElementById("dictProgressWrap");
    ui.dictProgressBar = document.getElementById("dictProgressBar");
    ui.dictProgressText = document.getElementById("dictProgressText");

    updateDictSourceUI();

    if (ui.tsvFileInput) {
      ui.tsvFileInput.addEventListener("change", function() {
        var file = ui.tsvFileInput.files && ui.tsvFileInput.files[0];
        if (!file) return;
        handleCustomUploadFile(file).catch(function() {});
        ui.tsvFileInput.value = "";
      });
    }

    if (ui.clearTsvBtn) {
      ui.clearTsvBtn.addEventListener("click", function() {
        resetCustomForCurrentLanguage().catch(function() {});
      });
    }

    if (ui.dictSourceSelect) {
      ui.dictSourceSelect.addEventListener("change", function() {
        updateDictSourceUI();
        if (getDictSource()) setStatus("");
        onLanguageDictSync(getCurrentLanguage()).catch(function() {});
      });
    }

    if (ui.languageSelect) {
      ui.languageSelect.addEventListener("change", function() {
        populateDictSourceDropdown(getCurrentLanguage(), true).then(function() {
          // Only sync if a source is already selected (e.g. cached from previous session)
          var source = getDictSource();
          if (source) onLanguageDictSync(getCurrentLanguage()).catch(function() {});
        });
      });
    }
  }

  function lookupLangFromUrl(parsedUrl) {
    if (!parsedUrl) return getCurrentLanguage();
    var raw = String(parsedUrl.searchParams.get("lang") || "").trim().toLowerCase();
    return raw || getCurrentLanguage();
  }

  function decorateLookupJson(lookupJson, langCode, source, options) {
    // Try worker path
    var wkey = _getActiveWorkerKey(langCode);
    if (wkey) {
      return _queryWorker(wkey, {
        type: "merged_lookup",
        lookupData: lookupJson,
        langCode: langCode,
        opts: options || {}
      });
    }
    // Main-thread fallback
    return ensureLanguageEngine(langCode, { source: source || getDictSource(), showProgress: false }).then(function(engine) {
      return hybridSegmentAndHydrate(lookupJson, engine, langCode, options || {});
    });
  }

  function perfNowMs() {
    if (typeof performance !== "undefined" && performance && typeof performance.now === "function") {
      return performance.now();
    }
    return Date.now();
  }

  function roundTimingMs(value) {
    var n = Number(value || 0);
    if (!isFinite(n)) return 0;
    return Math.round(n * 1000) / 1000;
  }

  function parseDebugServerMs(resp) {
    if (!resp || !resp.headers || typeof resp.headers.get !== "function") return 0;
    var raw = resp.headers.get("X-Debug-Server-Ms");
    var n = Number(raw || 0);
    return isFinite(n) && n > 0 ? n : 0;
  }

  function attachNetworkBreakdown(networkNode, totalMs, serverMs) {
    if (!networkNode || typeof networkNode !== "object") return;
    var total = roundTimingMs(totalMs);
    var server = roundTimingMs(Math.max(0, Math.min(total, Number(serverMs || 0))));
    networkNode.duration_ms = total;
    if (server > 0) {
      addTimingChild(networkNode, {
        name: "server_processing",
        label: "Server Processing",
        meta: {},
        duration_ms: server,
        children: []
      });
    }
    var residual = roundTimingMs(total - server);
    if (residual > 0.25) {
      addTimingChild(networkNode, {
        name: "transport_and_wait",
        label: "Transport + Wait",
        meta: {},
        duration_ms: residual,
        children: []
      });
    }
  }

  function createTimingNode(name, label, meta) {
    return {
      name: String(name || "").trim(),
      label: String(label || name || "").trim(),
      meta: (meta && typeof meta === "object") ? Object.assign({}, meta) : {},
      duration_ms: 0,
      children: []
    };
  }

  function addTimingChild(parent, child) {
    if (!parent || typeof parent !== "object" || !child || typeof child !== "object") return child;
    if (!Array.isArray(parent.children)) parent.children = [];
    parent.children.push(child);
    return child;
  }

  function finalizeTimingNode(node) {
    if (!node || typeof node !== "object") return null;
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
        name: "unattributed",
        label: "Unattributed",
        meta: { logged_child_ms: roundTimingMs(childSum) },
        duration_ms: unattributed,
        children: []
      });
    }
    return node;
  }

  function buildLookupTimingTrace(root, captureId, langCode, queryText) {
    if (!root || typeof root !== "object") return null;
    var finalizedRoot = finalizeTimingNode(root);
    if (!finalizedRoot) return null;
    var loggedMs = roundTimingMs(finalizedRoot.logged_child_ms || 0);
    var totalMs = roundTimingMs(finalizedRoot.duration_ms || 0);
    return {
      debug_capture_id: String(captureId || "").trim(),
      current_language: String(langCode || "").trim().toLowerCase(),
      q: String(queryText || ""),
      total_ms: totalMs,
      logged_ms: loggedMs,
      unattributed_ms: roundTimingMs(totalMs - loggedMs),
      timing_tree: finalizedRoot,
      updated_at: Date.now()
    };
  }

  function buildWinnerRefDebugUid(ref) {
    if (!ref || typeof ref !== "object") return "";
    var storageKind = String(ref.storage_kind || "sqlite").trim().toLowerCase() || "sqlite";
    var dbAlias = String(ref.db_alias || "").trim();
    var entryRowId = parseInt(ref.entry_row_id, 10) || 0;
    if (!dbAlias || !(entryRowId > 0)) return "";
    var formRowId = parseInt(ref.form_row_id || 0, 10) || 0;
    return storageKind + "|" + dbAlias + "|" + entryRowId + (formRowId > 0 ? "|" + formRowId : "");
  }

  function cloneWinnerRefForDebug(ref) {
    if (!ref || typeof ref !== "object") return null;
    var entryRowId = parseInt(ref.entry_row_id, 10) || 0;
    if (!(entryRowId > 0)) return null;
    var out = {
      storage_kind: String(ref.storage_kind || "sqlite").trim().toLowerCase() || "sqlite",
      db_alias: String(ref.db_alias || "").trim(),
      entry_row_id: entryRowId,
      match_kind: String(ref.match_kind || "headword").trim().toLowerCase() || "headword",
      form_row_id: parseInt(ref.form_row_id || 0, 10) || 0,
      match_key: String(ref.match_key || "")
    };
    out.uid = buildWinnerRefDebugUid(out);
    return out;
  }

  // DEBUG-ONLY: annotate a cloned winner ref with normalization trace.
  // Only called inside buildSqliteClientDebugCapture (already debug-gated).
  // Returns the same object mutated in-place for convenience.
  function _annotateDebugRefNormKinds(clonedRef, langCode) {
    var layer = window.DictionaryNormalizationLayer;
    if (!layer || typeof layer.normalizeLookupKeyTextWithTrace !== "function") return clonedRef;
    var rawKey = String(clonedRef.match_key || "");
    if (!rawKey) { clonedRef._norm_kinds = []; return clonedRef; }
    try {
      var result = layer.normalizeLookupKeyTextWithTrace(rawKey, {
        langCode: String(langCode || "").trim().toLowerCase(),
        phase: "lookup_key"
      });
      clonedRef._norm_kinds = Array.isArray(result.norm_kinds) ? result.norm_kinds : [];
    } catch (_e) {
      clonedRef._norm_kinds = [];
    }
    return clonedRef;
  }

  function parseLookupJsonBody(init) {
    if (!init || init.body == null) return null;
    if (typeof init.body === "string") {
      try {
        var parsed = JSON.parse(init.body);
        return parsed && typeof parsed === "object" ? parsed : null;
      } catch (_e) {
        return null;
      }
    }
    return null;
  }

  function buildSqliteClientDebugCapture(nlpData, langCode, segments, tokBySeg, lookupsBySegIdx, refsBySegIdx, allWinnerRefs, uniqueRefs) {
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
      var value = String(rawValue || "");
      if (!value) return;
      for (var i = 0; i < target.length; i++) {
        if (String(target[i] || "") === value) return;
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
      var word = String(segmentTexts[si] || "");
      var tok = tokenRows[si] || {};
      var surfaceLookup = lookupRows[si] || {};
      var refs = Array.isArray(rawRefsBySeg[si]) ? rawRefsBySeg[si] : [];
      var debugRefs = [];
      for (var ri = 0; ri < refs.length; ri++) {
        var clonedRef = cloneWinnerRefForDebug(refs[ri]);
        if (!clonedRef) continue;
        _annotateDebugRefNormKinds(clonedRef, langCode);
        debugRefs.push(clonedRef);
        var uid = String(clonedRef.uid || "");
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
      var resolutionMeta = (surfaceLookup && typeof surfaceLookup.resolution_meta === "object")
        ? surfaceLookup.resolution_meta
        : {};
      segmentWinners.push({
        segment_index: si,
        segment_text: word,
        lemma: String(tok.lemma || ""),
        upos: String(tok.upos || ""),
        xpos: String(tok.tag || tok.xpos || ""),
        deprel: String(tok.dep || tok.deprel || ""),
        resolved_via: String(surfaceLookup.resolved_via || ""),
        fill_mode: String(((surfaceLookup.fill && surfaceLookup.fill.mode) || "")).trim().toLowerCase(),
        resolution_category: String(resolutionMeta.category || ""),
        resolution_route_code: String(resolutionMeta.route_code || ""),
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
      if (rawClone) { _annotateDebugRefNormKinds(rawClone, langCode); rawWinnerRefs.push(rawClone); }
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
      row.kept_after_dedupe = !!keptByUid[String(row.uid || "")];
    }
    dedupeRows.sort(function(a, b) {
      var aCount = Number(a.raw_count || 0);
      var bCount = Number(b.raw_count || 0);
      if (aCount !== bCount) return bCount - aCount;
      return String(a.uid || "").localeCompare(String(b.uid || ""));
    });

    return {
      debug_capture_id: String((nlpData && nlpData.debug_capture_id) || "").trim(),
      language: String(langCode || "").trim().toLowerCase(),
      q: String((nlpData && nlpData.q) || ""),
      display_text: String((nlpData && nlpData.display_text) || ""),
      raw_winner_ref_count: rawWinnerRefs.length,
      unique_winner_ref_count: dedupedWinnerRefs.length,
      segment_winners: segmentWinners,
      raw_winner_refs: rawWinnerRefs,
      deduped_winner_refs: dedupedWinnerRefs,
      dedupe_rows: dedupeRows,
      hydrate_request: {
        method: "POST",
        path: "/js/hydrate",
        payload: {
          lang: String(langCode || "").trim().toLowerCase(),
          winner_refs: dedupedWinnerRefs
        }
      }
    };
  }

  function maybeDecorateLookupResponse(response, parsedUrl) {
    if (!response || !response.ok) return Promise.resolve(response);
    var contentType = String(response.headers.get("Content-Type") || "");
    if (contentType.indexOf("application/json") < 0) return Promise.resolve(response);
    return response.clone().json().then(function(data) {
      if (!data || !data.ok) return response;
      var langCode = lookupLangFromUrl(parsedUrl) || String(data.language || "");
      var dictSource = getDictSource();
      return decorateLookupJson(data, langCode, dictSource, {
        debug_trace: !!(data && data.debug_capture_id)
      }).then(function(merged) {
        var captureId = String((merged && merged.debug_capture_id) || "").trim();
        if (captureId) {
          if (merged && Object.prototype.hasOwnProperty.call(merged, "debug_ui_sqlite_capture")) {
            delete merged.debug_ui_sqlite_capture;
          }
        }
        return jsonResponse(merged, response.status);
      }, function(err) {
        console.error("Dictionary lookup merge failed:", err);
        return jsonResponse(data, response.status);
      });
    }).catch(function() {
      return response;
    });
  }

  function handleLookupDpOnlyRequest(parsedUrl) {
    // Hybrid version: compact index DP + /js/hydrate. No Trankit needed.
    var q = String(parsedUrl.searchParams.get("q") || "").trim();
    var langCode = lookupLangFromUrl(parsedUrl);
    var lemma = String(parsedUrl.searchParams.get("lemma") || "");
    var upos = String(parsedUrl.searchParams.get("upos") || "");
    var xpos = String(parsedUrl.searchParams.get("xpos") || "");
    if (!q || !langCode) return Promise.resolve(jsonResponse({ ok: false, error: "empty" }, 400));
    return hybridDpOnlyLookup(q, langCode, { lemma: lemma, upos: upos, xpos: xpos }).then(function(payload) {
      payload.language = langCode;
      return jsonResponse(payload, 200);
    }).catch(function(err) {
      console.error("[hybrid] lookup_dp_only error:", err);
      return jsonResponse({ ok: false, error: "hybrid lookup_dp_only failed" }, 500);
    });
  }

  function handleSubsegmentsRequest(parsedUrl) {
    var token = String(parsedUrl.searchParams.get("token") || "").trim();
    var langCode = lookupLangFromUrl(parsedUrl);
    var decompose = isTruthyFlag(parsedUrl.searchParams.get("decompose") || "0");
    if (!token) return Promise.resolve(jsonResponse({ ok: false, error: "empty" }, 400));
    // Try worker path
    var wkey = _getActiveWorkerKey(langCode);
    if (wkey) {
      return _queryWorker(wkey, {
        type: "subsegments",
        token: token,
        langCode: langCode,
        decompose: decompose
      }).then(function(payload) {
        payload.language = langCode;
        return jsonResponse(payload, 200);
      }).catch(function(err) {
        console.error("Worker subsegments error:", err);
        return jsonResponse({ ok: false, error: "worker subsegments failed" }, 500);
      });
    }
    // Main-thread fallback
    return ensureLanguageEngine(langCode, { source: getDictSource(), showProgress: false }).then(function(engine) {
      if (!engine) return jsonResponse({ ok: false, error: "no dictionary loaded" }, 400);
      var payload = buildSubsegmentsPayload(token, engine, decompose);
      payload.language = langCode;
      return jsonResponse(payload, 200);
    }).catch(function(err) {
      console.error("subsegments client error:", err);
      return jsonResponse({ ok: false, error: "client subsegments failed" }, 500);
    });
  }

  function handleLookupRawRequest(parsedUrl) {
    var q = String(parsedUrl.searchParams.get("q") || "").trim();
    var langCode = lookupLangFromUrl(parsedUrl);
    var lemma = String(parsedUrl.searchParams.get("lemma") || "");
    var upos = String(parsedUrl.searchParams.get("upos") || "");
    var xpos = String(parsedUrl.searchParams.get("xpos") || "");
    // Try worker path
    var wkey = _getActiveWorkerKey(langCode);
    if (wkey) {
      return _queryWorker(wkey, {
        type: "lookup_dp_only",
        q: q,
        langCode: langCode,
        opts: { lemma: lemma, upos: upos, xpos: xpos }
      }).then(function(payload) {
        if (isTruthyFlag(parsedUrl.searchParams.get("exact"))) payload.exact = true;
        payload.language = langCode;
        return jsonResponse(payload, 200);
      }).catch(function(err) {
        console.error("Worker lookup raw error:", err);
        return jsonResponse({ ok: false, error: "worker raw lookup failed" }, 500);
      });
    }
    // Main-thread fallback
    return ensureLanguageEngine(langCode, { source: getDictSource(), showProgress: false }).then(function(engine) {
      return hybridDpOnlyLookupWithEngine(q, engine, langCode, {
        lemma: lemma,
        upos: upos,
        xpos: xpos
      }).then(function(payload) {
        if (isTruthyFlag(parsedUrl.searchParams.get("exact"))) payload.exact = true;
        payload.language = langCode;
        return jsonResponse(payload, 200);
      });
    }).catch(function(err) {
      console.error("lookup raw client error:", err);
      return jsonResponse({ ok: false, error: "client raw lookup failed" }, 500);
    });
  }

  // ── Hybrid lookup helpers ─────────────────────────────────────────────────

  function appendWinnerRef(refs, ref) {
    if (!ref || !ref._winner_ref) return;
    refs.push({
      storage_kind: String(ref.storage_kind || "sqlite").trim().toLowerCase() || "sqlite",
      db_alias: String(ref.db_alias || ""),
      entry_row_id: parseInt(ref.entry_row_id, 10) || 0,
      match_kind: String(ref.match_kind || "headword"),
      form_row_id: parseInt(ref.form_row_id || 0, 10) || 0,
      match_key: String(ref.match_key || "")
    });
  }

  /**
   * Extract winner refs from a compact-mode fill result.
   * Exact whole-token matches can carry multiple compact refs on fill.entries;
   * hydrate all of them so same-surface entries are not collapsed to one row.
   * Returns array of {storage_kind, db_alias, entry_row_id, match_kind, form_row_id, match_key}
   */
  function extractWinnerRefs(fillResult) {
    var refs = [];
    var fills = (fillResult && fillResult.fills) || [];
    for (var i = 0; i < fills.length; i++) {
      var f = fills[i];
      if (!f || f.source === "UNKNOWN") continue;
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

  function extractWinnerRefsFromSinglePassLookup(surfaceLookup) {
    var refs = extractWinnerRefs(surfaceLookup && surfaceLookup.fill);
    var children = (surfaceLookup && Array.isArray(surfaceLookup.ko_compound_lemma_children))
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
  function deduplicateWinnerRefs(refs) {
    var seen = Object.create(null);
    var out = [];
    for (var i = 0; i < refs.length; i++) {
      var r = refs[i];
      if (!r.db_alias || !(r.entry_row_id > 0)) continue;
      var fid = parseInt(r.form_row_id, 10) || 0;
      var uid = r.storage_kind + "|" + r.db_alias + "|" + r.entry_row_id + (fid > 0 ? "|" + fid : "");
      if (seen[uid]) continue;
      seen[uid] = true;
      out.push(r);
    }
    return out;
  }

  /**
   * POST winner refs to /js/hydrate and return {entry_store, ref_to_key}.
   */
  function hydrateWinnerRefs(langCode, winnerRefs, options) {
    if (!winnerRefs.length) return Promise.resolve({ entry_store: {}, ref_to_key: {}, form_overlays: {} });
    options = options || {};
    var apiBase = getApiBase();
    var captureId = String(options.debug_capture_id || "").trim();
    var timingNode = (options.debug_timing_node && typeof options.debug_timing_node === "object") ? options.debug_timing_node : null;
    var payload = { lang: langCode, winner_refs: winnerRefs };
    if (captureId) payload.debug_capture_id = captureId;
    var requestStartedAt = timingNode ? perfNowMs() : 0;
    var networkNode = timingNode ? addTimingChild(timingNode, createTimingNode("hydrate_network", "/js/hydrate Network", {
      winner_ref_count: winnerRefs.length
    })) : null;
    var networkStartedAt = networkNode ? perfNowMs() : 0;
    return fetch(apiBase + "/hydrate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function(resp) {
      if (networkNode) attachNetworkBreakdown(networkNode, perfNowMs() - networkStartedAt, parseDebugServerMs(resp));
      var jsonNode = timingNode ? addTimingChild(timingNode, createTimingNode("hydrate_json_parse", "/js/hydrate JSON Parse")) : null;
      var jsonStartedAt = jsonNode ? perfNowMs() : 0;
      return resp.json().then(function(data) {
        if (jsonNode) jsonNode.duration_ms = perfNowMs() - jsonStartedAt;
        if (timingNode) timingNode.duration_ms = perfNowMs() - requestStartedAt;
        return data;
      });
    })
    .then(function(data) {
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
  function hybridSegmentAndHydrate(nlpData, engine, langCode, options) {
    options = options || {};
    var includeDebugTrace = !!options.debug_trace;
    var timingNode = (options.debug_timing_node && typeof options.debug_timing_node === "object") ? options.debug_timing_node : null;
    var hybridStartedAt = timingNode ? perfNowMs() : 0;
    var segments = Array.isArray(nlpData.segments) ? nlpData.segments : [];
    var tokBySeg = extractTokenBySeg(nlpData);
    var allWinnerRefs = [];
    var lookupsBySegIdx = [];
    var refsBySegIdx = includeDebugTrace ? [] : null;
    var surfaceLookupNode = timingNode ? addTimingChild(timingNode, createTimingNode("surface_lookups", "Surface Lookups", {
      segment_count: segments.length
    })) : null;
    var surfaceLookupStartedAt = surfaceLookupNode ? perfNowMs() : 0;

    for (var i = 0; i < segments.length; i++) {
      var word = String(segments[i] || "");
      var tok = tokBySeg[i] || {};
      var upos = String(tok.upos || "X");
      var lemma = String(tok.lemma || "");
      var xpos = String(tok.tag || "");

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
    reportLookupProgress("Dictionary matches found");

    var dedupeNode = timingNode ? addTimingChild(timingNode, createTimingNode("dedupe_winner_refs", "Deduplicate Winner Refs", {
      raw_winner_ref_count: allWinnerRefs.length
    })) : null;
    var dedupeStartedAt = dedupeNode ? perfNowMs() : 0;
    var uniqueRefs = deduplicateWinnerRefs(allWinnerRefs);
    if (dedupeNode) {
      dedupeNode.duration_ms = perfNowMs() - dedupeStartedAt;
      dedupeNode.meta.unique_winner_ref_count = uniqueRefs.length;
    }
    var sqliteDebugCapture = includeDebugTrace
      ? buildSqliteClientDebugCapture(nlpData, langCode, segments, tokBySeg, lookupsBySegIdx, refsBySegIdx, allWinnerRefs, uniqueRefs)
      : null;

    var hydrateRequestNode = timingNode ? addTimingChild(timingNode, createTimingNode("hydrate_request", "Hydrate Request", {
      winner_ref_count: uniqueRefs.length
    })) : null;
    reportLookupProgress("Loading dictionary entries");
    return hydrateWinnerRefs(langCode, uniqueRefs, {
      debug_capture_id: includeDebugTrace ? String(nlpData.debug_capture_id || "") : "",
      debug_timing_node: hydrateRequestNode
    }).then(function(hydrateResult) {
      var normalizeHydrateNode = timingNode ? addTimingChild(timingNode, createTimingNode("normalize_hydrate_payload", "Normalize Hydrate Payload")) : null;
      var normalizeHydrateStartedAt = normalizeHydrateNode ? perfNowMs() : 0;
      var entryStore = normalizeCanonicalEntryStore(hydrateResult.entry_store || {});
      var formOverlays = hydrateResult.form_overlays || {};
      if (normalizeHydrateNode) normalizeHydrateNode.duration_ms = perfNowMs() - normalizeHydrateStartedAt;

      var hydrateLookupNode = timingNode ? addTimingChild(timingNode, createTimingNode("hydrate_surface_lookups", "Hydrate Surface Lookups", {
        segment_count: lookupsBySegIdx.length
      })) : null;
      var hydrateLookupStartedAt = hydrateLookupNode ? perfNowMs() : 0;
      var hydratedLookups = [];
      for (var si = 0; si < lookupsBySegIdx.length; si++) {
        hydratedLookups.push(hydrateSinglePassLookup(
          lookupsBySegIdx[si],
          entryStore,
          hydrateResult.ref_to_key || {},
          engine,
          formOverlays
        ));
      }
      if (hydrateLookupNode) hydrateLookupNode.duration_ms = perfNowMs() - hydrateLookupStartedAt;

      var buildResultsNode = timingNode ? addTimingChild(timingNode, createTimingNode("build_results_by_seg", "Build Results By Segment", {
        segment_count: segments.length
      })) : null;
      reportLookupProgress("Assembling results");
      var buildResultsStartedAt = buildResultsNode ? perfNowMs() : 0;
      var resultsBySeg = buildResultsBySeg(nlpData, engine, {
        debug_trace: includeDebugTrace,
        precomputed_surface_lookups: hydratedLookups
      });
      if (buildResultsNode) buildResultsNode.duration_ms = perfNowMs() - buildResultsStartedAt;

      var buildPayloadNode = timingNode ? addTimingChild(timingNode, createTimingNode("build_merged_payload", "Build Merged Payload")) : null;
      var buildPayloadStartedAt = buildPayloadNode ? perfNowMs() : 0;

      var merged = {
        ok: true,
        display_text: nlpData.display_text || "",
        q: nlpData.q || "",
        debug_capture_id: String(nlpData.debug_capture_id || ""),
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
        if (resultsBySeg[ri] && resultsBySeg[ri].source !== "PUNCT") {
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
  function buildHybridSegResult(segInfo, entryStore, refToKey, langCode, nlpData, segIdx) {
    var fill = segInfo.fill;
    var refs = segInfo.refs;
    var word = segInfo.word;
    var tok = segInfo.tok || {};
    var upos = String(tok.upos || "X");
    var xpos = String(tok.tag || "");
    var deprel = String(tok.dep || "dep");
    var lemma = String(tok.lemma || word);
    var feats = String(tok.feats || "");
    var fills = (fill && fill.fills) || [];
    var uposColor = UPOS_COLORS[upos] || "#e5e7eb";

    if (!fills.length || (fills.length === 1 && fills[0].source === "UNKNOWN")) {
      return buildUnknownResult(word, upos, xpos, deprel, lemma, feats, segIdx);
    }

    // Collect entry_ids for this segment from the hydrated entry_store
    var entryIds = [];
    var hydratedEntries = [];
    for (var i = 0; i < refs.length; i++) {
      var r = refs[i];
      var _rfid = parseInt(r.form_row_id, 10) || 0;
      var wireKey = r.storage_kind + "|" + r.db_alias + "|" + r.entry_row_id + (_rfid > 0 ? "|" + _rfid : "");
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
    var reading = primary.reading || "";
    var pos = primary.pos || upos;
    var headword = primary.headword || word;

    // Helper to collect entry IDs from a fill row, with fallback chain
    function collectHybridFillEntryIds(fillRow, refToKey) {
      var row = (fillRow && typeof fillRow === "object") ? fillRow : {};
      var out = [];
      var seen = Object.create(null);

      function pushId(raw) {
        var id = String(raw || "").trim();
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
          (String(ref.storage_kind || "sqlite").trim().toLowerCase() || "sqlite") +
          "|" + ref.db_alias +
          "|" + ref.entry_row_id +
          (_wkfid > 0 ? "|" + _wkfid : "");
        pushId(refToKey[wk] || "");
      }

      return out;
    }

    // Build fill objects referencing entry_store keys
    var fillObjs = [];
    for (var fi = 0; fi < fills.length; fi++) {
      var f = fills[fi] || {};
      if (!f || f.source === "UNKNOWN") {
        fillObjs.push({ text: f.text || word, source: "UNKNOWN", entry_ids: [] });
        continue;
      }

      var rowEntryIds = collectHybridFillEntryIds(f, refToKey);
      fillObjs.push({
        text: f.text || word,
        head: headword,
        source: rowEntryIds.length ? "DICT" : "UNKNOWN",
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
      source: "DICT",
      fills: fillObjs,
      entry_ids: entryIds,
      color: uposColor,
      start: segOffsets ? segOffsets[0] : null,
      end: segOffsets ? segOffsets[1] : null,
      resolution: {
        category: "surface",
        resolved_via: "surface",
        fill_mode: fill.mode || "exact"
      }
    };
  }

  /**
   * Single-token hybrid lookup (for /lookup_dp_only intercept).
   * Does NOT call Trankit — lemma/upos/xpos come from URL params.
   */
  function hybridDpOnlyLookupWithEngine(word, engine, langCode, opts) {
    opts = opts || {};
    var lemma = String(opts.lemma || "");
    var upos = String(opts.upos || "X").trim().toUpperCase();
    var xpos = String(opts.xpos || "");
    var mwtParts = Array.isArray(opts.mwt_parts) ? opts.mwt_parts : [];
    if (!engine) {
      return Promise.resolve({ ok: false, error: "no engine for " + langCode });
    }

    // Fuzzy panel mode is a fully standalone path: no DP, no segmentation,
    // no lemma/exact side-channels. Tiered codepoint-level edit distance over
    // the compact index only. Tier 0 == exact.
    var surfaceLookup;
    if (opts.fuzzyPanel && engine && typeof engine.fuzzyLookupKeysTiered === "function") {
      var fuzzy = engine.fuzzyLookupKeysTiered(word);
      var fuzzyStubs = (fuzzy && fuzzy.stubs) ? fuzzy.stubs : [];
      var fuzzyTier = (fuzzy && typeof fuzzy.tier === "number") ? fuzzy.tier : -1;
      if (fuzzyStubs.length) {
        var fuzzyFillResult = buildFillResult(word, fuzzyStubs, "fuzzy_tier_" + fuzzyTier);
        surfaceLookup = {
          exact_entries: fuzzyStubs.slice(),
          fill: fuzzyFillResult.fill,
          all_entries: fuzzyStubs.slice(),
          preferred_entries: fuzzyStubs.slice(),
          dict_head: word,
          resolved_via: "fuzzy",
          fuzzy_tier: fuzzyTier,
          lemma_hint_data: { lemma_hint_objects: [], lemma_differs_from_surface: false },
          lemma_oracle_used: false,
          lemma_oracle_outcome: "fuzzy"
        };
      } else {
        surfaceLookup = {
          exact_entries: [],
          fill: { mode: "fuzzy_miss", fills: [], has_known: false, has_unknown: true },
          all_entries: [],
          preferred_entries: [],
          dict_head: word,
          resolved_via: "fuzzy",
          fuzzy_tier: -1,
          lemma_hint_data: { lemma_hint_objects: [], lemma_differs_from_surface: false },
          lemma_oracle_used: false,
          lemma_oracle_outcome: "fuzzy_miss"
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

    return hydrateWinnerRefs(langCode, uniqueRefs).then(function(hydrateResult) {
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

  function hybridDpOnlyLookup(word, langCode, opts) {
    return ensureLanguageEngine(langCode, { showProgress: false }).then(function(engine) {
      return hybridDpOnlyLookupWithEngine(word, engine, langCode, opts || {});
    });
  }

  function lookupSingle(word, langCode, opts) {
    var q = String(word || "").trim();
    var code = String(langCode || getCurrentLanguage() || "").trim().toLowerCase();
    if (!q) return Promise.resolve({ ok: false, error: "empty" });
    if (!code) return Promise.resolve({ ok: false, error: "missing language" });
    return hybridDpOnlyLookup(q, code, opts || {});
  }

  function wrapFetch(origFetch) {
    return function(input, init) {
      var rawUrl = (typeof input === "string")
        ? input
        : ((input && input.url) ? input.url : "");
      var parsed = toAbsoluteUrl(rawUrl);
      if (!parsed) return origFetch(input, init);

      var path = parsed.pathname;

      // Intercept /lookup_dp_only — side-panel single token, no Trankit
      if (path === "/lookup_dp_only") {
        var q = String(parsed.searchParams.get("q") || "").trim();
        var dpLang = lookupLangFromUrl(parsed);
        if (!q || !dpLang) return origFetch(input, init);
        return hybridDpOnlyLookup(q, dpLang, {
          lemma: parsed.searchParams.get("lemma") || "",
          upos: parsed.searchParams.get("upos") || "",
          xpos: parsed.searchParams.get("xpos") || ""
        }).then(function(payload) {
          return jsonResponse(payload, 200);
        }).catch(function(err) {
          console.error("[hybrid] lookup_dp_only error:", err);
          return origFetch(input, init);
        });
      }

      // Intercept /subsegments — pass through to server (unchanged)
      if (path === "/subsegments") {
        return origFetch(input, init);
      }

      // Intercept /lookup — server now returns NLP-only, we do DP + hydrate
      if (path === "/lookup") {
        var requestMethod = String(
          (init && init.method) ||
          (input && input.method) ||
          "GET"
        ).toUpperCase();
        var lookupJsonBody = requestMethod === "GET" ? null : parseLookupJsonBody(init || {});
        var jsQ = String(parsed.searchParams.get("q") || (lookupJsonBody && lookupJsonBody.q) || "").trim();
        var jsLang = lookupLangFromUrl(parsed);
        if (!String(parsed.searchParams.get("lang") || "").trim() && lookupJsonBody && lookupJsonBody.lang) {
          jsLang = String(lookupJsonBody.lang || "").trim().toLowerCase();
        }
        if (!jsQ || !jsLang) {
          return origFetch(input, init).then(function(resp) {
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
        var debugTimingRequested = !!(
          window.LE_DEBUG_COLLECTION_ENABLED &&
          isTruthyFlag(requestParsed.searchParams.get("debug_capture") || "0")
        );
        var lookupTimingRoot = debugTimingRequested ? createTimingNode("lookup_total", "Lookup Total", {
          language: jsLang,
          query_length: jsQ.length
        }) : null;
        var lookupStartedAt = lookupTimingRoot ? perfNowMs() : 0;
        var ensureEngineNode = lookupTimingRoot ? addTimingChild(lookupTimingRoot, createTimingNode("ensure_language_engine", "Ensure Language Engine", {
          language: jsLang
        })) : null;
        var ensureEngineStartedAt = ensureEngineNode ? perfNowMs() : 0;
        reportLookupProgress("Loading dictionary");
        return ensureLanguageEngine(jsLang, { showProgress: true }).then(function(engine) {
          if (ensureEngineNode) ensureEngineNode.duration_ms = perfNowMs() - ensureEngineStartedAt;
          var lookupRequestNode = lookupTimingRoot ? addTimingChild(lookupTimingRoot, createTimingNode("lookup_request", "/lookup Request")) : null;
          var lookupRequestStartedAt = lookupRequestNode ? perfNowMs() : 0;
          var lookupNetworkNode = lookupRequestNode ? addTimingChild(lookupRequestNode, createTimingNode("lookup_network", "/lookup Network")) : null;
          var lookupNetworkStartedAt = lookupNetworkNode ? perfNowMs() : 0;
          reportLookupProgress("Analyzing text");
          return origFetch(requestInput, init).then(function(resp) {
            if (lookupNetworkNode) attachNetworkBreakdown(lookupNetworkNode, perfNowMs() - lookupNetworkStartedAt, parseDebugServerMs(resp));
            if (!resp.ok) return resp;
            var lookupJsonNode = lookupRequestNode ? addTimingChild(lookupRequestNode, createTimingNode("lookup_json_parse", "/lookup JSON Parse")) : null;
            var lookupJsonStartedAt = lookupJsonNode ? perfNowMs() : 0;
            return resp.json().then(function(nlpData) {
              if (lookupJsonNode) lookupJsonNode.duration_ms = perfNowMs() - lookupJsonStartedAt;
              if (lookupRequestNode) lookupRequestNode.duration_ms = perfNowMs() - lookupRequestStartedAt;
              if (!nlpData || !nlpData.ok || !engine) {
                return maybeDecorateLookupResponse(
                  new Response(JSON.stringify(nlpData), { status: 200, headers: { "Content-Type": "application/json" } }),
                  requestParsed
                );
              }
              reportLookupProgress("Model analysis complete");
              // Fire LLM gloss request immediately using Trankit data, before hydration
              if (window._fireLlmGlossRequest) {
                try { window._fireLlmGlossRequest(nlpData); } catch(e) {}
              }
              // Fire inflectional token decomposition alongside gloss
              if (window._fireLlmDecompRequest) {
                try { window._fireLlmDecompRequest(nlpData); } catch(e) {}
              }
              // Fire orth breakdown request alongside gloss
              if (window._fireOrthBreakdownRequest) {
                try { window._fireOrthBreakdownRequest(nlpData); } catch(e) {}
              }
              var hybridNode = lookupTimingRoot ? addTimingChild(lookupTimingRoot, createTimingNode("hybrid_segment_and_hydrate", "Hybrid Segment + Hydrate", {
                segment_count: Array.isArray(nlpData.segments) ? nlpData.segments.length : 0
              })) : null;
              reportLookupProgress("Building dictionary payload");
              return hybridSegmentAndHydrate(nlpData, engine, jsLang, {
                debug_trace: !!(nlpData && nlpData.debug_capture_id),
                debug_timing_node: hybridNode
              }).then(function(merged) {
                if (lookupTimingRoot && merged && merged.debug_capture_id) {
                  lookupTimingRoot.duration_ms = perfNowMs() - lookupStartedAt;
                  merged.debug_ui_lookup_timing = buildLookupTimingTrace(
                    lookupTimingRoot,
                    String(merged.debug_capture_id || ""),
                    jsLang,
                    jsQ
                  );
                }
                if (merged && Object.prototype.hasOwnProperty.call(merged, "debug_ui_sqlite_capture")) {
                  delete merged.debug_ui_sqlite_capture;
                }
                reportLookupProgress("Dictionary payload ready");
                return jsonResponse(merged, 200);
              });
            });
          });
        }).catch(function(err) {
          console.error("[hybrid] /lookup error:", err);
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
  function _injectGeminiAdditions(engine, langCode, onProgress) {
    var code = String(langCode || "").toLowerCase();
    var url = "/js/dict/" + encodeURIComponent(code) + "/custom_index";
    return fetch(url).then(function(resp) {
      if (!resp.ok) return;
      // Response is gzip JSON — decompress client-side
      return resp.arrayBuffer().then(function(buf) {
        var gzBytes = new Uint8Array(buf);
        if (typeof DecompressionStream === "function") {
          var ds = new DecompressionStream("gzip");
          var blob = new Blob([gzBytes], { type: "application/gzip" });
          var textStream = blob.stream().pipeThrough(ds).pipeThrough(new TextDecoderStream());
          var reader = textStream.getReader();
          var parts = [];
          function readText() {
            return reader.read().then(function(r) {
              if (r.done) return parts.join("");
              parts.push(r.value);
              return readText();
            });
          }
          return readText().then(function(text) { return JSON.parse(text); });
        }
        return gunzipToText(gzBytes).then(function(text) { return JSON.parse(text); });
      });
    }).then(function(index) {
      if (!index || typeof engine.injectGeminiKey !== "function") return;
      var hw = index.hw || {};
      var keys = Object.keys(hw);
      var total = keys.length;
      if (!total) return;
      if (typeof onProgress === "function") onProgress(0, total, 0);
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
          var alias = String((ref && ref[0]) || "customdb");
          var eid = parseInt((ref && ref[1]) || 0, 10);
          if (eid > 0) {
            engine.injectGeminiKey(normKey, eid, alias, "headword");
            loaded++;
          }
        }
        if (typeof onProgress === "function") {
          var now = Date.now();
          if (i === keys.length - 1 || (now - lastProgressAt) > 80) {
            lastProgressAt = now;
            onProgress(i + 1, total, loaded);
          }
        }
      }
      if (loaded > 0) {
        console.log("[dict-client] Injected " + loaded + " custom entries for " + code);
      }
    }).catch(function(err) {
      console.warn("[dict-client] Failed to load custom index for " + langCode + ":", err);
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
  function injectGeminiEntry(langCode, entry) {
    var code = String(langCode || "").toLowerCase();
    var hw = String(entry.headword || "");
    var eid = parseInt(entry.entry_row_id || entry.id || "0", 10) || 0;
    var alias = String(entry.db_alias || "customdb");
    if (!hw || !(eid > 0)) return Promise.resolve();

    return ensureLanguageEngine(code, { showProgress: false }).then(function(engine) {
      if (!engine || typeof engine.injectGeminiKey !== "function") return;
      // Normalize the headword key the same way the engine does
      var normKey = hw;
      var layer = window.DictionaryNormalizationLayer;
      if (layer && typeof layer.normalizeLookupKeyText === "function") {
        try {
          normKey = String(layer.normalizeLookupKeyText(hw, { langCode: code }) || hw);
        } catch (_e) {}
      }
      engine.injectGeminiKey(normKey, eid, alias, "headword");
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
  function relookupOneSegment(langCode, surface, existingSegResult) {
    var code = String(langCode || "").toLowerCase();
    var seg = existingSegResult || {};
    return hybridDpOnlyLookup(surface, code, {
      lemma: seg.lemma || surface,
      upos: seg.upos || "X",
      xpos: seg.xpos || seg.tag || "",
      mwt_parts: Array.isArray(seg.mwt_parts) ? seg.mwt_parts : []
    }).then(function(payload) {
      return payload || existingSegResult;
    }).catch(function() {
      return existingSegResult;
    });
  }

  function init() {
    if (state.initialized) return;
    state.initialized = true;
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
  function getRawGeminiEntry(langCode, headword) {
    var code = String(langCode || "").toLowerCase();
    var url = "/api/gemini_entry/get?language=" + encodeURIComponent(code) + "&headword=" + encodeURIComponent(String(headword || ""));
    return fetch(url).then(function(resp) {
      if (!resp.ok) return null;
      return resp.json().then(function(data) {
        if (!data || !data.ok || !data.entry) return null;
        var e = data.entry;
        // Normalize to the shape caller expects
        var glosses = [];
        if (Array.isArray(e.senses)) {
          for (var i = 0; i < e.senses.length; i++) {
            var sense = e.senses[i];
            if (sense && Array.isArray(sense.glosses)) {
              for (var j = 0; j < sense.glosses.length; j++) glosses.push(sense.glosses[j]);
            } else if (typeof sense === "string") {
              glosses.push(sense);
            }
          }
        }
        return {
          headword: String(e.headword || ""),
          romanization: String(e.reading || e.romanization || ""),
          pos: String(e.pos || ""),
          glosses: glosses,
          forms: Array.isArray(e.forms) ? e.forms : [],
          commentary: String(e.commentary || ""),
          lemma: String(e.lemma || ""),
          source: String(e.source || "gemini"),
          entry_id: String(e.entry_id || "")
        };
      });
    }).catch(function() { return null; });
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
  function updateGeminiEntry(langCode, entry) {
    var code = String(langCode || "").toLowerCase();
    // Invalidate in-memory index so next load re-injects from DB
    delete _hybridIndexByLang[code];
    // The key in the compact index doesn't change; hydrate will return updated data
    // automatically on next /js/hydrate call. Nothing else to do here.
    return Promise.resolve();
  }

  /**
   * Remove a Gemini entry from the compact engine index.
   * entryId is the integer SQLite id from custom_dict_entries.
   * headword is used to compute the normalized key for removeCompactKey().
   */
  function removeGeminiEntry(langCode, headwordOrEntry, entryId) {
    var code = String(langCode || "").toLowerCase();
    var payload = (headwordOrEntry && typeof headwordOrEntry === "object") ? headwordOrEntry : null;
    var hw = String(payload ? (payload.headword || "") : (headwordOrEntry || ""));
    var eid = parseInt(
      payload ? (payload.entry_row_id || payload.entry_id || payload.id || "0") : (entryId || "0"),
      10
    ) || 0;
    if (!code || !hw || !(eid > 0)) return Promise.resolve();

    return ensureLanguageEngine(code, { showProgress: false }).then(function(engine) {
      if (!engine || typeof engine.removeCompactKey !== "function") return;
      var normKey = hw;
      var layer = window.DictionaryNormalizationLayer;
      if (layer && typeof layer.normalizeLookupKeyText === "function") {
        try {
          normKey = String(layer.normalizeLookupKeyText(hw, { langCode: code }) || hw);
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
  if (typeof importScripts === "function") {
    self.addEventListener("message", function(e) {
      var data = e.data;
      if (!data || !data.requestId) return;
      var engine = (self._workerEngines && self._workerEngines[data.engineKey]) || null;

      function reply(payload) {
        self.postMessage({ type: "query_result", requestId: data.requestId, payload: payload });
      }
      function replyError(msg) {
        self.postMessage({ type: "query_result", requestId: data.requestId, error: String(msg) });
      }

      try {
        // Set language for getCurrentLanguage() fallback in worker
        if (data.langCode) self.ReaderDefaultLanguage = data.langCode;

        if (data.type === "lookup_dp_only") {
          if (!engine) return replyError("no engine for " + data.engineKey);
          hybridDpOnlyLookupWithEngine(data.q, engine, data.langCode || "", data.opts || {}).then(function(payload) {
            payload.language = data.langCode || "";
            reply(payload);
          }).catch(replyError);
          return;
        }

        if (data.type === "subsegments") {
          if (!engine) return replyError("no engine for " + data.engineKey);
          var token = String(data.token || "");
          var decompose = !!data.decompose;
          var payload = buildSubsegmentsPayload(token, engine, decompose);
          payload.language = data.langCode || "";
          return reply(payload);
        }

        if (data.type === "merged_lookup") {
          if (!engine) return replyError("no engine for " + data.engineKey);
          hybridSegmentAndHydrate(data.lookupData, engine, data.langCode || "", data.opts || {}).then(reply).catch(replyError);
          return;
        }

        if (data.type === "results_by_seg") {
          if (!engine) return replyError("no engine for " + data.engineKey);
          hybridSegmentAndHydrate(data.lookupData, engine, data.langCode || "", data.opts || {}).then(function(payload) {
            reply((payload && payload.results_by_seg) || []);
          }).catch(replyError);
          return;
        }

        if (data.type === "inject_rows") {
          if (!engine) return replyError("no engine for " + data.engineKey);
          var rows = data.rows || [];
          var loaded = 0;
          for (var i = 0; i < rows.length; i++) {
            if (engine._loadOneRow(rows[i], data.source || "gemini")) loaded++;
          }
          return reply({ loaded: loaded });
        }

        if (data.type === "inject_one_row") {
          if (!engine) return replyError("no engine for " + data.engineKey);
          engine._loadOneRow(data.row, data.source || "gemini");
          return reply({ ok: true });
        }

        if (data.type === "has_word") {
          var found = false;
          var prefix = String(data.langCode || "").toLowerCase() + "|";
          var eKeys = Object.keys(self._workerEngines || {});
          for (var i = 0; i < eKeys.length; i++) {
            if (eKeys[i].indexOf(prefix) !== 0) continue;
            var eng = self._workerEngines[eKeys[i]];
            if (!eng) continue;
            if (eng.lookup(String(data.word || ""))) { found = true; break; }
            if (typeof eng.lookup_via_forms === "function") {
              var vf = eng.lookup_via_forms(String(data.word || ""));
              if (vf && vf.length) { found = true; break; }
            }
          }
          return reply({ found: found });
        }

        if (data.type === "get_raw_gemini") {
          var prefix = String(data.langCode || "").toLowerCase() + "|";
          var eKeys = Object.keys(self._workerEngines || {});
          var result = null;
          for (var i = 0; i < eKeys.length; i++) {
            if (eKeys[i].indexOf(prefix) !== 0) continue;
            var eng = self._workerEngines[eKeys[i]];
            if (!eng || typeof eng.lookup_all !== "function") continue;
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
                try { var pf = JSON.parse(ent._forms_raw); if (Array.isArray(pf)) forms = pf; } catch (_) {}
              }
              result = {
                headword: ent.headword,
                romanization: ent.reading || "",
                pos: ent.pos_raw || ent.pos || "",
                glosses: glosses,
                forms: forms,
                commentary: ent._commentary || "",
                lemma: ent._lemma || "",
                source: ent._source || "gemini"
              };
              break;
            }
            if (result) break;
          }
          return reply(result);
        }

        if (data.type === "update_entry") {
          var prefix = String(data.langCode || "").toLowerCase() + "|";
          var eKeys = Object.keys(self._workerEngines || {});
          var hw = String(data.entry.headword || "");
          for (var i = 0; i < eKeys.length; i++) {
            if (eKeys[i].indexOf(prefix) !== 0) continue;
            var eng = self._workerEngines[eKeys[i]];
            if (!eng || typeof eng.lookup_all !== "function") continue;
            var all = eng.lookup_all(hw);
            for (var j = 0; j < all.length; j++) {
              var ent = all[j];
              if (!ent || !ent._source || ent.headword !== hw) continue;
              ent.reading = convertNumericPinyin(String(data.entry.romanization || ""));
              ent.pos_raw = String(data.entry.pos || "");
              ent.pos = String(data.entry.pos || "").toLowerCase();
              var glosses = Array.isArray(data.entry.glosses) ? data.entry.glosses : [];
              var senses = glosses.map(function(g) { return { glosses: [String(g)] }; });
              if (ent._source === "user_created") senses.push({ _source: "user_created" });
              ent._glosses_raw = JSON.stringify(senses);
              delete ent.senses; delete ent.senses_full; delete ent._hydrated;
              var forms = Array.isArray(data.entry.forms) ? data.entry.forms : [];
              ent._forms_raw = JSON.stringify(forms);
              ent._forms_json = JSON.stringify(forms);
              if (data.entry.commentary !== undefined) ent._commentary = String(data.entry.commentary || "");
              if (data.entry.lemma !== undefined) ent._lemma = String(data.entry.lemma || "");
              var byWord = eng._by_word;
              var foldKey = null;
              var bwKeys = Object.keys(byWord);
              for (var k = 0; k < bwKeys.length; k++) {
                var bucket = byWord[bwKeys[k]];
                for (var b = 0; b < bucket.length; b++) {
                  if (bucket[b] === ent) { foldKey = bwKeys[k]; break; }
                }
                if (foldKey) break;
              }
              if (foldKey) eng._index_tsv_forms(ent, hw, foldKey);
              break;
            }
            break;
          }
          return reply({ ok: true });
        }

        if (data.type === "remove_entry") {
          var prefix = String(data.langCode || "").toLowerCase() + "|";
          var eKeys = Object.keys(self._workerEngines || {});
          var hw = String(data.headword || "");
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
          return reply({ ok: true });
        }

        if (data.type === "relookup_segment") {
          if (!engine) return replyError("no engine for " + data.engineKey);
          var seg = data.existingSegResult || {};
          hybridDpOnlyLookupWithEngine(data.surface, engine, data.langCode || "", {
            lemma: seg.lemma || data.surface,
            upos: seg.upos || "X",
            xpos: seg.xpos || seg.tag || "",
            mwt_parts: Array.isArray(seg.mwt_parts) ? seg.mwt_parts : []
          }).then(function(payload) {
            reply(payload || data.existingSegResult);
          }).catch(replyError);
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
    hasWord: function(langCode, word) {
      // Returns Promise<boolean> — checks if word exists in any engine for this language.
      var code = String(langCode || "").toLowerCase();
      var wkey = _getActiveWorkerKey(code);
      if (wkey) {
        return _queryWorker(wkey, {
          type: "has_word",
          langCode: code,
          word: word
        }).then(function(result) {
          return !!(result && result.found);
        });
      }
      // Main-thread fallback (sync result wrapped in Promise)
      var prefix = code + "|";
      var keys = Object.keys(state.engineByLangSource || {});
      for (var i = 0; i < keys.length; i++) {
        if (keys[i].indexOf(prefix) !== 0) continue;
        var engine = state.engineByLangSource[keys[i]];
        if (!engine) continue;
        if (engine.lookup(String(word || ""))) return Promise.resolve(true);
        if (typeof engine.lookup_via_forms === "function") {
          var viaForms = engine.lookup_via_forms(String(word || ""));
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
    debugBuildLemmaAlignment: function(surface, lemma, xpos, langCode) {
      return buildDebugLemmaAlignment(surface, lemma, xpos, langCode || getCurrentLanguage() || "");
    },
    debugBuildKoreanLemmaXposAlignment: function(surface, lemma, xpos, langCode) {
      return buildKoreanLemmaXposAlignment(surface, lemma, xpos, langCode || "ko");
    },
    getDictSource: getDictSource,
    isEngineReady: function(langCode) {
      var code = String(langCode || getCurrentLanguage() || "").toLowerCase();
      if (!code) return false;
      // Check for active worker
      if (_getActiveWorkerKey(code)) return true;
      // Check for main-thread engine
      var prefix = code + "|";
      var keys = Object.keys(state.engineByLangSource || {});
      for (var i = 0; i < keys.length; i++) {
        if (keys[i].indexOf(prefix) === 0 && state.engineByLangSource[keys[i]]) return true;
      }
      return false;
    }
  };
})();
