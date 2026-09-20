/*
DevTools snippet: dictionary download probe

Paste into the browser console on the reader page.

What it does:
- intercepts real /api/dict/... fetches from the app
- logs response headers and every streamed chunk arrival
- watches the dictionary progress UI for text/bar/display changes
- lets you manually fetch a dictionary URL outside the app flow

Primary globals:
- __dictDownloadProbe.logs
- __dictDownloadProbe.report()
- __dictDownloadProbe.fetchOnce('/api/dict/ar?source=wiktionary')
- __dictDownloadProbe.stop()
*/
(function () {
  if (window.__dictDownloadProbe && typeof window.__dictDownloadProbe.stop === 'function') {
    try { window.__dictDownloadProbe.stop(); } catch (_e) {}
  }

  var state = {
    startedAt: performance.now(),
    originalFetch: window.fetch,
    logs: [],
    nextRequestId: 1,
    observers: [],
    lastUiSnapshot: null
  };

  function nowMs() {
    return Math.round(performance.now() - state.startedAt);
  }

  function cleanText(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function pushLog(tag, data) {
    var entry = Object.assign({ t: nowMs(), tag: tag }, data || {});
    state.logs.push(entry);
    console.log('[dict-download-probe]', entry);
    return entry;
  }

  function getUiSnapshot() {
    var wrap = document.getElementById('dictProgressWrap');
    var text = document.getElementById('dictProgressText');
    var bar = document.getElementById('dictProgressBar');
    var wrapStyle = wrap ? window.getComputedStyle(wrap) : null;
    return {
      wrap_exists: !!wrap,
      wrap_display: wrapStyle ? wrapStyle.display : '',
      wrap_visibility: wrapStyle ? wrapStyle.visibility : '',
      text_exists: !!text,
      text: text ? cleanText(text.textContent || '') : '',
      bar_exists: !!bar,
      bar_width_style: bar ? String(bar.style.width || '') : '',
      bar_width_px: bar ? Math.round(bar.getBoundingClientRect().width) : 0
    };
  }

  function maybeLogUi(reason) {
    var snap = getUiSnapshot();
    var prev = state.lastUiSnapshot;
    var changed = !prev || JSON.stringify(prev) !== JSON.stringify(snap);
    if (!changed) return;
    state.lastUiSnapshot = snap;
    pushLog('ui', Object.assign({ reason: reason || '' }, snap));
  }

  function observeNode(node, options, reason) {
    if (!node) return;
    var obs = new MutationObserver(function () {
      maybeLogUi(reason);
    });
    obs.observe(node, options);
    state.observers.push(obs);
  }

  function installUiObservers() {
    observeNode(document.getElementById('dictProgressWrap'), {
      attributes: true,
      attributeFilter: ['style', 'class']
    }, 'wrap-mutation');
    observeNode(document.getElementById('dictProgressText'), {
      childList: true,
      characterData: true,
      subtree: true
    }, 'text-mutation');
    observeNode(document.getElementById('dictProgressBar'), {
      attributes: true,
      attributeFilter: ['style', 'class']
    }, 'bar-mutation');
    maybeLogUi('probe-installed');
  }

  function isDictUrl(url) {
    return String(url || '').indexOf('/api/dict/') >= 0;
  }

  function describeHeaders(resp) {
    return {
      status: resp.status,
      ok: !!resp.ok,
      content_length: resp.headers.get('Content-Length') || '',
      content_type: resp.headers.get('Content-Type') || '',
      cache_control: resp.headers.get('Cache-Control') || '',
      content_encoding: resp.headers.get('Content-Encoding') || '',
      transfer_encoding: resp.headers.get('Transfer-Encoding') || ''
    };
  }

  function wrapStreamingResponse(resp, requestInfo) {
    if (!resp || !resp.body || typeof resp.body.getReader !== 'function') {
      pushLog('response-no-stream', Object.assign({}, requestInfo, describeHeaders(resp || { headers: { get: function () { return ''; } }, status: 0, ok: false })));
      return Promise.resolve(resp);
    }

    var reader = resp.body.getReader();
    var received = 0;
    var chunks = 0;
    var firstChunkAt = null;
    var lastChunkAt = null;

    pushLog('response-headers', Object.assign({}, requestInfo, describeHeaders(resp)));

    var stream = new ReadableStream({
      start: function (controller) {
        function pump() {
          return reader.read().then(function (result) {
            if (result.done) {
              pushLog('stream-done', Object.assign({}, requestInfo, {
                received_bytes: received,
                chunk_count: chunks,
                first_chunk_at: firstChunkAt,
                last_chunk_at: lastChunkAt
              }));
              controller.close();
              return;
            }
            var value = result.value;
            var size = value ? (value.byteLength || value.length || 0) : 0;
            received += size;
            chunks += 1;
            if (firstChunkAt == null) firstChunkAt = nowMs();
            lastChunkAt = nowMs();
            pushLog('stream-chunk', Object.assign({}, requestInfo, {
              chunk_index: chunks,
              chunk_size: size,
              received_bytes: received
            }));
            controller.enqueue(value);
            return pump();
          }).catch(function (err) {
            pushLog('stream-error', Object.assign({}, requestInfo, {
              message: String(err && err.message || err || 'stream error')
            }));
            controller.error(err);
          });
        }
        return pump();
      },
      cancel: function (reason) {
        pushLog('stream-cancel', Object.assign({}, requestInfo, {
          reason: String(reason || '')
        }));
        return reader.cancel(reason);
      }
    });

    return Promise.resolve(new Response(stream, {
      status: resp.status,
      statusText: resp.statusText,
      headers: new Headers(resp.headers)
    }));
  }

  window.fetch = function patchedFetch(input, init) {
    var url = (typeof input === 'string')
      ? input
      : (input && typeof input.url === 'string' ? input.url : '');

    if (!isDictUrl(url)) {
      return state.originalFetch.call(this, input, init);
    }

    var requestId = state.nextRequestId++;
    var info = {
      request_id: requestId,
      url: String(url || ''),
      mode: 'app'
    };

    pushLog('fetch-start', info);
    maybeLogUi('fetch-start');

    return state.originalFetch.call(this, input, init).then(function (resp) {
      return wrapStreamingResponse(resp, info);
    });
  };

  function fetchOnce(url) {
    var requestId = state.nextRequestId++;
    var info = {
      request_id: requestId,
      url: String(url || ''),
      mode: 'manual'
    };

    pushLog('manual-fetch-start', info);

    return state.originalFetch.call(window, String(url || ''), { cache: 'no-store' }).then(function (resp) {
      pushLog('manual-response-headers', Object.assign({}, info, describeHeaders(resp)));
      if (!resp.body || typeof resp.body.getReader !== 'function') {
        pushLog('manual-no-stream', info);
        return resp;
      }
      var reader = resp.body.getReader();
      var received = 0;
      var chunks = 0;
      var firstChunkAt = null;
      var lastChunkAt = null;

      function pump() {
        return reader.read().then(function (result) {
          if (result.done) {
            pushLog('manual-stream-done', Object.assign({}, info, {
              received_bytes: received,
              chunk_count: chunks,
              first_chunk_at: firstChunkAt,
              last_chunk_at: lastChunkAt
            }));
            return {
              ok: true,
              request_id: requestId,
              received_bytes: received,
              chunk_count: chunks
            };
          }
          var size = result.value ? (result.value.byteLength || result.value.length || 0) : 0;
          received += size;
          chunks += 1;
          if (firstChunkAt == null) firstChunkAt = nowMs();
          lastChunkAt = nowMs();
          pushLog('manual-stream-chunk', Object.assign({}, info, {
            chunk_index: chunks,
            chunk_size: size,
            received_bytes: received
          }));
          return pump();
        });
      }

      return pump();
    });
  }

  function report() {
    var dictLogs = state.logs.slice();
    var appRequests = {};
    var manualRequests = {};

    for (var i = 0; i < dictLogs.length; i++) {
      var log = dictLogs[i];
      var bucket = log.mode === 'manual' ? manualRequests : appRequests;
      var key = String(log.request_id || '');
      if (!key) continue;
      if (!bucket[key]) bucket[key] = [];
      bucket[key].push(log);
    }

    var summary = {
      total_logs: dictLogs.length,
      ui_events: dictLogs.filter(function (e) { return e.tag === 'ui'; }).length,
      app_requests: Object.keys(appRequests).map(function (id) {
        var rows = appRequests[id];
        var headers = rows.find(function (r) { return r.tag === 'response-headers'; }) || {};
        var done = rows.find(function (r) { return r.tag === 'stream-done'; }) || {};
        var chunks = rows.filter(function (r) { return r.tag === 'stream-chunk'; }).length;
        return {
          request_id: id,
          url: headers.url || (rows[0] && rows[0].url) || '',
          content_length: headers.content_length || '',
          chunk_count: chunks,
          received_bytes: done.received_bytes || 0,
          first_chunk_at: done.first_chunk_at != null ? done.first_chunk_at : null,
          last_chunk_at: done.last_chunk_at != null ? done.last_chunk_at : null
        };
      }),
      manual_requests: Object.keys(manualRequests).map(function (id) {
        var rows = manualRequests[id];
        var headers = rows.find(function (r) { return r.tag === 'manual-response-headers'; }) || {};
        var done = rows.find(function (r) { return r.tag === 'manual-stream-done'; }) || {};
        var chunks = rows.filter(function (r) { return r.tag === 'manual-stream-chunk'; }).length;
        return {
          request_id: id,
          url: headers.url || (rows[0] && rows[0].url) || '',
          content_length: headers.content_length || '',
          chunk_count: chunks,
          received_bytes: done.received_bytes || 0,
          first_chunk_at: done.first_chunk_at != null ? done.first_chunk_at : null,
          last_chunk_at: done.last_chunk_at != null ? done.last_chunk_at : null
        };
      }),
      ui_snapshots: dictLogs.filter(function (e) { return e.tag === 'ui'; })
    };

    console.log('[dict-download-probe][report]', summary);
    return summary;
  }

  function stop() {
    try { window.fetch = state.originalFetch; } catch (_e) {}
    for (var i = 0; i < state.observers.length; i++) {
      try { state.observers[i].disconnect(); } catch (_e2) {}
    }
    delete window.__dictDownloadProbe;
  }

  installUiObservers();

  window.__dictDownloadProbe = {
    logs: state.logs,
    report: report,
    fetchOnce: fetchOnce,
    stop: stop
  };

  console.log('[dict-download-probe] ready. Trigger a real dictionary download, or run __dictDownloadProbe.fetchOnce("/api/dict/ar?source=wiktionary").');
})();
