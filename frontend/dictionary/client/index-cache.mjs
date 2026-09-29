import { cacheKey, getDictSource, gunzipToText, parseTsvText, showDictProgress } from './core.mjs';
import { coreState } from './core.state.mjs';
import { buildResultsBySeg, prepareFillEntries } from './lookup-payloads.mjs';
export function buildSubsegmentsPayload(token, engine, decompose) {
  // Dead decomposition path. Leave disconnected from active lookup flow.
  var tokenText = String(token || '');
  var fill = tokenText
    ? engine.fill_token(tokenText, {
        allowExact: !decompose,
        excludeWhole: !!decompose
      })
    : {
        fills: []
      };
  var prepared = prepareFillEntries(
    (fill && fill.fills) || [],
    engine,
    '',
    '',
    String((fill && fill.mode) || 'greedy')
  );
  var mode = String((fill && fill.mode) || 'greedy');
  if (decompose && tokenText) {
    prepared = prepared.filter(function (p) {
      return String((p || {}).head || '') !== tokenText;
    });
  }
  return {
    ok: true,
    token: tokenText,
    subsegments: prepared,
    mode: mode
  };
}
export function buildMergedLookupPayload(lookupData, engine, options) {
  var merged = {};
  for (var key in lookupData) {
    if (Object.prototype.hasOwnProperty.call(lookupData, key)) merged[key] = lookupData[key];
  }
  var resultsBySeg = buildResultsBySeg(lookupData, engine, options || {});
  merged.results_by_seg = resultsBySeg;
  merged.results = [];
  for (var i = 0; i < resultsBySeg.length; i++) {
    var entry = resultsBySeg[i];
    if (entry && entry.source !== 'PUNCT') {
      merged.results.push(entry);
      break;
    }
  }
  return merged;
}
export function buildEngineFromRows(langCode, rows) {
  if (!window.DictionaryEngine) {
    throw new Error('DictionaryEngine is not available');
  }
  var engine = new window.DictionaryEngine(langCode);
  engine.load_tsv_entries(rows || []);
  return engine;
}
export function cloneUint8Array(bytes) {
  if (!bytes || !bytes.length) return new Uint8Array(0);
  return bytes.slice ? bytes.slice(0) : new Uint8Array(bytes);
}
export function countEngineEntries(engine) {
  if (!engine || !engine._by_word) return 0;
  var keys = Object.keys(engine._by_word);
  var total = 0;
  for (var i = 0; i < keys.length; i++) {
    var bucket = engine._by_word[keys[i]];
    if (Array.isArray(bucket)) total += bucket.length;
  }
  return total;
}
export function buildDictProgressMessage(prefix, rows, bytes) {
  var msg = String(prefix || 'Building... ') + String(rows || 0) + ' entries';
  var kb = Math.round((Number(bytes) || 0) / 1024);
  if (kb > 1024) msg += ' (' + (kb / 1024).toFixed(1) + ' MB)';
  return msg;
}
export function formatProgressMegabytes(bytes) {
  var mb = Math.max(0, Number(bytes) || 0) / 1048576;
  return mb.toFixed(mb >= 100 ? 0 : 1);
}
export function formatProgressCount(value) {
  return Math.max(0, Math.round(Number(value) || 0)).toLocaleString();
}
export function buildDownloadProgressMessage(received, total) {
  var downloadedMb = formatProgressMegabytes(received);
  if (!(total > 0)) return 'Downloading\u2026 ' + downloadedMb + ' MB';
  var totalMb = formatProgressMegabytes(total);
  var remainingMb = formatProgressMegabytes(Math.max(0, total - received));
  return 'Downloading\u2026 ' + downloadedMb + ' / ' + totalMb + ' MB, ' + remainingMb + ' MB left';
}
export function buildIndexDownloadProgressMessage(received, total) {
  var loadedMb = formatProgressMegabytes(received);
  if (!(total > 0)) return 'Downloading index... ' + loadedMb + ' MB';
  var totalMb = formatProgressMegabytes(total);
  return 'Downloading index... ' + loadedMb + ' / ' + totalMb + ' MB';
}
export function buildIndexOpenProgressMessage(received, total) {
  var loadedMb = formatProgressMegabytes(received);
  if (!(total > 0)) return 'Opening index... ' + loadedMb + ' MB';
  var totalMb = formatProgressMegabytes(total);
  return 'Opening index... ' + loadedMb + ' / ' + totalMb + ' MB';
}
export function buildAssemblyProgressMessage(done, total, label) {
  var msg = 'Assembling\u2026 ';
  if (total > 0) {
    msg += formatProgressCount(done) + ' / ' + formatProgressCount(total) + ' items';
  } else {
    msg += formatProgressCount(done) + ' items';
  }
  if (label) msg += ' (' + String(label) + ')';
  return msg;
}
export function buildGeminiAdditionProgressMessage(processed, total, loaded) {
  var msg = 'Loading additions\u2026 ';
  if (total > 0) {
    msg += formatProgressCount(processed) + ' / ' + formatProgressCount(total) + ' rows';
  } else {
    msg += formatProgressCount(processed) + ' rows';
  }
  if (loaded > 0) msg += ' (' + formatProgressCount(loaded) + ' loaded)';
  return msg;
}
export function buildEngineFromGzipBytes(langCode, key, gzBytes, opts) {
  opts = opts || {};
  var code = String(langCode || '').toLowerCase();
  var bytes = opts.preserveSource ? cloneUint8Array(gzBytes) : gzBytes;
  if (!bytes || !bytes.length) return Promise.resolve(null);
  var showProgress = !!opts.showProgress;
  var progressBasePct = Number(opts.progressBasePct || 0);
  var progressSpanPct = Number(opts.progressSpanPct || 18);
  var progressPrefix = String(opts.progressPrefix || 'Building... ');
  var summary = opts.summary || null;
  // Estimate total decompressed size as ~10x gzip size for linear progress
  var estimatedTotalBytes = (bytes ? bytes.length : 0) * 10;
  var lastProgressPct = progressBasePct;
  if (showProgress) {
    showDictProgress(progressBasePct, String(progressPrefix || 'Building...').trim());
  }
  var progressCb = showProgress
    ? function (rows, parsedBytes, phase, progressMeta) {
        if (summary) {
          summary.rows = Number(rows || 0);
          summary.bytes = Number(parsedBytes || 0);
        }
        // Linear progress based on decompressed bytes vs estimated total
        var fraction =
          estimatedTotalBytes > 0
            ? Math.max(0, Math.min(0.98, (parsedBytes || 0) / estimatedTotalBytes))
            : Math.min(0.98, 1 - 1 / (1 + (rows || 0) / 5000));
        var pct = progressBasePct + Math.round(progressSpanPct * fraction);
        pct = Math.max(lastProgressPct, Math.min(progressBasePct + progressSpanPct - 1, pct));
        lastProgressPct = pct;
        showDictProgress(pct, buildDictProgressMessage(progressPrefix, rows, parsedBytes));
      }
    : null;
  return buildEngineStreaming(code, bytes, progressCb, key).then(function (engine) {
    if (!engine) return null;
    engine._dcCacheKey = key;
    coreState.state.engineByLangSource[key] = engine;
    return engine;
  });
}

/**
 * Discover the versioned script URLs for the normalization layer and engine
 * from the current page's <script> tags, so the Worker can importScripts them.
 */
export function _discoverEngineScriptUrls() {
  var scripts = document.getElementsByTagName('script');
  var normUrl = '';
  var engineUrl = '';
  var clientUrl = '';
  for (var i = 0; i < scripts.length; i++) {
    var src = scripts[i].src || '';
    if (!normUrl && src.indexOf('dictionary_normalization_layer') >= 0) normUrl = src;
    if (!engineUrl && src.indexOf('dictionary_engine') >= 0) engineUrl = src;
    if (!clientUrl && src.indexOf('dictionary_client') >= 0) clientUrl = src;
  }
  return {
    normUrl: normUrl,
    engineUrl: engineUrl,
    clientUrl: clientUrl
  };
}

/**
 * Build a dictionary engine in a Web Worker off the main thread.
 * Streams decompress → parse → build, posts progress to main thread.
 * Falls back to main-thread streaming if Workers or streaming APIs are unavailable.
 */
export function buildEngineStreaming(langCode, gzBytes, onProgress, engineKey) {
  if (!window.DictionaryEngine) {
    throw new Error('DictionaryEngine is not available');
  }

  // Try Worker path first — engine stays permanently in worker
  if (typeof Worker === 'function' && typeof DecompressionStream === 'function' && engineKey) {
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
export function _buildEngineMainThread(langCode, gzBytes, onProgress) {
  if (typeof DecompressionStream !== 'function' || typeof TextDecoderStream !== 'function') {
    // Classic pipeline
    return gunzipToText(gzBytes).then(function (tsvText) {
      var rows = parseTsvText(tsvText);
      tsvText = null;
      if (!rows.length) return null;
      var engine = buildEngineFromRows(langCode, rows);
      rows = null;
      return engine;
    });
  }
  var code = String(langCode || '').toLowerCase();
  var engine = new window.DictionaryEngine(code);
  var ds = new DecompressionStream('gzip');
  var blob = new Blob([gzBytes], {
    type: 'application/gzip'
  });
  var textStream = blob.stream().pipeThrough(ds).pipeThrough(new TextDecoderStream());
  var reader = textStream.getReader();
  var headers = null;
  var partial = '';
  var lineNo = 0;
  var totalLoaded = 0;
  var bytesRead = 0;
  var lastProgressAt = 0;
  function processLine(line) {
    if (!line.trim()) return;
    lineNo++;
    if (!headers) {
      headers = line.split('\t');
      return;
    }
    var fields = line.split('\t');
    var row = {};
    for (var j = 0; j < headers.length; j++) {
      row[String(headers[j] || '').trim()] = j < fields.length ? fields[j] : '';
    }
    if (engine._loadOneRow(row)) totalLoaded++;
  }
  function pump() {
    return reader.read().then(function (result) {
      if (result.done) {
        if (partial) {
          processLine(partial);
          partial = '';
        }
        return totalLoaded > 0 ? engine : null;
      }
      bytesRead += result.value.length;
      var chunk = partial + result.value;
      var lines = chunk.split(/\r?\n/);
      partial = lines[lines.length - 1];
      for (var i = 0; i < lines.length - 1; i++) {
        processLine(lines[i]);
      }
      if (typeof onProgress === 'function') {
        var now = Date.now();
        if (now - lastProgressAt > 80) {
          lastProgressAt = now;
          onProgress(totalLoaded, bytesRead, 'parsing');
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
export function _getWorkerCode(urls) {
  return [
    // Shim: Workers have no `window` or `document`
    'var window = self;',
    'var document = {',
    '  getElementById: function() { return null; },',
    '  addEventListener: function() {},',
    '  removeEventListener: function() {},',
    '  getElementsByTagName: function() { return []; },',
    '  querySelectorAll: function() { return []; },',
    '  createElement: function() { return { style: {} }; }',
    '};',
    '',
    // Import the scripts (normalization layer, engine, then client for payload builders)
    urls.normUrl ? 'importScripts(' + JSON.stringify(urls.normUrl) + ');' : '',
    'importScripts(' + JSON.stringify(urls.engineUrl) + ');',
    urls.clientUrl ? 'importScripts(' + JSON.stringify(urls.clientUrl) + ');' : '',
    '',
    // Global engine storage — shared between build handler and query handler
    'if (!self._workerEngines) self._workerEngines = {};',
    '',
    'self.onmessage = function(e) {',
    '  var data = e.data;',
    '',
    "  if (data.type === 'build_rows') {",
    "    var rCode = String(data.langCode || '').toLowerCase();",
    '    var rEngine = new self.DictionaryEngine(rCode);',
    '    var rRows = data.rows || [];',
    '    rEngine.load_tsv_entries(rRows);',
    '    self._workerEngines[data.engineKey || rCode] = rEngine;',
    "    self.postMessage({ type: 'done', langCode: rCode, rows: rRows.length, engineKey: data.engineKey || rCode });",
    '    return;',
    '  }',
    '',
    "  if (data.type !== 'build') return;",
    '  var langCode = data.langCode;',
    '  var gzBytes = data.gzBytes;',
    "  var engineKey = data.engineKey || '';",
    "  var code = String(langCode || '').toLowerCase();",
    '  var engine = new self.DictionaryEngine(code);',
    "  var ds = new DecompressionStream('gzip');",
    "  var blob = new Blob([gzBytes], { type: 'application/gzip' });",
    '  var textStream = blob.stream().pipeThrough(ds).pipeThrough(new TextDecoderStream());',
    '  var reader = textStream.getReader();',
    '  var headers = null;',
    "  var partial = '';",
    '  var lineNo = 0;',
    '  var totalLoaded = 0;',
    '  var lastProgressAt = 0;',
    '  var bytesRead = 0;',
    '',
    '  function processLine(line) {',
    '    if (!line.trim()) return;',
    '    lineNo++;',
    "    if (!headers) { headers = line.split('\\t'); return; }",
    "    var fields = line.split('\\t');",
    '    var row = {};',
    '    for (var j = 0; j < headers.length; j++) {',
    "      row[String(headers[j] || '').trim()] = (j < fields.length) ? fields[j] : '';",
    '    }',
    '    if (engine._loadOneRow(row)) totalLoaded++;',
    '  }',
    '',
    '  function sendProgress() {',
    '    var now = Date.now();',
    '    if (now - lastProgressAt < 80) return;',
    '    lastProgressAt = now;',
    "    self.postMessage({ type: 'progress', phase: 'parsing', rows: totalLoaded, bytes: bytesRead });",
    '  }',
    '',
    '  function pump() {',
    '    return reader.read().then(function(result) {',
    '      if (result.done) {',
    "        if (partial) { processLine(partial); partial = ''; }",
    '        if (totalLoaded === 0) {',
    "          self.postMessage({ type: 'done', langCode: code, rows: 0, engineKey: engineKey });",
    '          return;',
    '        }',
    '        // Store engine permanently in worker — no transfer to main thread',
    '        self._workerEngines[engineKey] = engine;',
    "        self.postMessage({ type: 'done', langCode: code, rows: totalLoaded, engineKey: engineKey });",
    '        return;',
    '      }',
    '      bytesRead += result.value.length;',
    '      var chunk = partial + result.value;',
    '      var lines = chunk.split(/\\r?\\n/);',
    '      partial = lines[lines.length - 1];',
    '      for (var i = 0; i < lines.length - 1; i++) {',
    '        processLine(lines[i]);',
    '      }',
    '      sendProgress();',
    '      return pump();',
    '    });',
    '  }',
    '',
    '  pump().catch(function(err) {',
    "    self.postMessage({ type: 'error', message: String(err.message || err) });",
    '  });',
    '};'
  ].join('\n');
}
export function _buildEngineInWorker(langCode, gzBytes, onProgress, engineKey) {
  var urls = _discoverEngineScriptUrls();
  if (!urls.engineUrl) {
    throw new Error('Cannot find engine script URL for Worker');
  }
  if (!urls.clientUrl) {
    throw new Error('Cannot find dictionary_client script URL for Worker');
  }
  var workerCode = _getWorkerCode(urls);
  var workerBlob = new Blob([workerCode], {
    type: 'application/javascript'
  });
  var workerUrl = URL.createObjectURL(workerBlob);
  var worker = new Worker(workerUrl);

  // Wire up the worker query handler for dictionary_client.js worker mode
  worker.addEventListener('message', function (e) {
    var msg = e.data;
    if (msg.type === 'query_result' && msg.requestId) {
      var cb = coreState.state.workerCallbacks[msg.requestId];
      if (cb) {
        delete coreState.state.workerCallbacks[msg.requestId];
        if (msg.error) {
          cb.reject(new Error(msg.error));
        } else {
          cb.resolve(msg.payload);
        }
      }
    }
  });
  return new Promise(function (resolve, reject) {
    worker.onmessage = function (e) {
      var msg = e.data;
      if (msg.type === 'progress') {
        if (typeof onProgress === 'function') {
          onProgress(msg.rows, msg.bytes, msg.phase || 'parsing', msg);
        }
        return;
      }
      if (msg.type === 'error') {
        worker.terminate();
        URL.revokeObjectURL(workerUrl);
        delete coreState.state.activeWorkers[engineKey];
        reject(new Error(msg.message || 'Worker build failed'));
        return;
      }
      if (msg.type === 'done') {
        if (msg.rows === 0) {
          worker.terminate();
          URL.revokeObjectURL(workerUrl);
          delete coreState.state.activeWorkers[engineKey];
          resolve(null);
          return;
        }
        // Worker keeps the engine — store worker reference, return proxy
        coreState.state.activeWorkers[engineKey] = {
          worker: worker,
          blobUrl: workerUrl
        };
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
    worker.onerror = function (err) {
      worker.terminate();
      URL.revokeObjectURL(workerUrl);
      delete coreState.state.activeWorkers[engineKey];
      reject(err);
    };
    // Transfer the ArrayBuffer (zero-copy)
    var buffer = gzBytes.buffer;
    worker.postMessage(
      {
        type: 'build',
        langCode: langCode,
        gzBytes: gzBytes,
        engineKey: engineKey
      },
      [buffer]
    );
  });
}
export function _queryWorker(engineKey, message) {
  var winfo = coreState.state.activeWorkers[engineKey];
  if (!winfo || !winfo.worker) {
    return Promise.reject(new Error('No active worker for key: ' + engineKey));
  }
  var requestId = coreState.state.nextRequestId++;
  message.requestId = requestId;
  message.engineKey = engineKey;
  return new Promise(function (resolve, reject) {
    coreState.state.workerCallbacks[requestId] = {
      resolve: resolve,
      reject: reject
    };
    winfo.worker.postMessage(message);
  });
}
export function _getActiveWorkerKey(langCode) {
  var source = getDictSource();
  var key = cacheKey(langCode, source);
  if (coreState.state.activeWorkers[key]) return key;
  // Check all keys for this language
  var prefix = String(langCode || '').toLowerCase() + '|';
  var keys = Object.keys(coreState.state.activeWorkers);
  for (var i = 0; i < keys.length; i++) {
    if (keys[i].indexOf(prefix) === 0) return keys[i];
  }
  return '';
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
