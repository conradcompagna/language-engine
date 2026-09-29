/*
DevTools snippet: edit-entry preload probe

Paste into the browser console on the reader page. After that:
- click one dictionary-entry Edit button
- wait about 1.5s
- the probe prints one verbose dump for that click

What it records:
- clicked Edit button metadata
- nearby rendered entry/badge context from the side panel
- every DictionaryClient.getRawGeminiEntry(...) call during that capture
- the resolved raw payload returned to the editor
- the rendered edit form field values after the panel updates

Primary globals:
- __editEntryProbe.logs
- __editEntryProbe.last()
- __editEntryProbe.dump()
- __editEntryProbe.snapshotForm()
- __editEntryProbe.stop()
*/
(function () {
  if (window.__editEntryProbe && typeof window.__editEntryProbe.stop === 'function') {
    try { window.__editEntryProbe.stop(); } catch (_e) {}
  }

  var CAPTURE_WINDOW_MS = 1500;

  var state = {
    startedAt: performance.now(),
    nextId: 1,
    captures: [],
    activeCapture: null,
    clickHandler: null,
    observer: null,
    dc: null,
    originalGetRaw: null,
    originalFetch: window.fetch,
    wrapTimer: null
  };

  function nowMs() {
    return Math.round(performance.now() - state.startedAt);
  }

  function cleanText(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function describeNode(node) {
    if (!node || !node.tagName) return '';
    var parts = [String(node.tagName || '').toLowerCase()];
    if (node.id) parts.push('#' + node.id);
    if (node.classList && node.classList.length) {
      parts.push('.' + Array.from(node.classList).join('.'));
    }
    return parts.join('');
  }

  function cloneDataset(node) {
    var out = {};
    if (!node || !node.dataset) return out;
    for (var key in node.dataset) {
      if (Object.prototype.hasOwnProperty.call(node.dataset, key)) {
        out[key] = node.dataset[key];
      }
    }
    return out;
  }

  function summarizeRaw(raw) {
    if (!raw || typeof raw !== 'object') return raw;
    return {
      headword: raw.headword || '',
      romanization: raw.romanization || '',
      pos: raw.pos || '',
      commentary: raw.commentary || '',
      lemma: raw.lemma || '',
      source: raw.source || '',
      glosses: Array.isArray(raw.glosses) ? raw.glosses.slice() : [],
      forms: Array.isArray(raw.forms) ? raw.forms.map(function (row) {
        return Array.isArray(row) ? row.slice() : row;
      }) : []
    };
  }

  function summarizeButton(btn) {
    if (!btn) return null;
    var part = btn.closest('.dict-entry-part');
    var panel = document.getElementById('panel-content');
    return {
      node: describeNode(btn),
      text: cleanText(btn.textContent),
      dataset: cloneDataset(btn),
      part_node: describeNode(part),
      part_text: cleanText(part ? part.textContent : ''),
      panel_text: cleanText(panel ? panel.textContent : '')
    };
  }

  function getGlossInputs(form) {
    return Array.from((form || document).querySelectorAll('.ef-gloss-input'));
  }

  function getFormRows(form) {
    return Array.from((form || document).querySelectorAll('.ef-form-row'));
  }

  function snapshotForm() {
    var form = document.getElementById('entry-form');
    if (!form) {
      return {
        exists: false
      };
    }
    var glossInputs = getGlossInputs(form);
    var formRows = getFormRows(form);
    return {
      exists: true,
      node: describeNode(form),
      form_class: form.className || '',
      headword: (document.getElementById('ef-headword') || {}).value || '',
      romanization: (document.getElementById('ef-roman') || {}).value || '',
      pos: (document.getElementById('ef-pos') || {}).value || '',
      commentary: ((document.getElementById('ef-commentary') || {}).value),
      lemma: ((document.getElementById('ef-lemma') || {}).value),
      glosses: glossInputs.map(function (input) { return String(input.value || ''); }),
      forms: formRows.map(function (row) {
        return {
          word: String((row.querySelector('.ef-form-word') || {}).value || ''),
          tags: String((row.querySelector('.ef-form-commentary') || {}).value || ''),
          roman: String((row.querySelector('.ef-form-pron') || {}).value || '')
        };
      }),
      save_text: cleanText((document.getElementById('ef-save-btn') || {}).textContent || ''),
      save_disabled: !!((document.getElementById('ef-save-btn') || {}).disabled),
      cancel_text: cleanText((document.getElementById('ef-cancel-btn') || {}).textContent || ''),
      delete_text: cleanText((document.getElementById('ef-delete-btn') || {}).textContent || ''),
      panel_text: cleanText((document.getElementById('panel-content') || {}).textContent || '')
    };
  }

  function capturePanelContext() {
    var panel = document.getElementById('panel-content');
    if (!panel) {
      return {
        exists: false
      };
    }
    var badgeNodes = panel.querySelectorAll('.dict-source-badge');
    var editNodes = panel.querySelectorAll('.dict-entry-edit-btn');
    var headlineNodes = panel.querySelectorAll('.popup-headline, .dict-entry-part-head');
    return {
      exists: true,
      node: describeNode(panel),
      text: cleanText(panel.textContent),
      badges: Array.from(badgeNodes).map(function (node) { return cleanText(node.textContent); }),
      edits: Array.from(editNodes).map(function (node) {
        return {
          text: cleanText(node.textContent),
          dataset: cloneDataset(node)
        };
      }),
      headlines: Array.from(headlineNodes).map(function (node) { return cleanText(node.textContent); }).filter(Boolean)
    };
  }

  function safeJson(value) {
    try {
      return JSON.stringify(value, null, 2);
    } catch (err) {
      return String(value);
    }
  }

  function dumpCapture(capture) {
    console.log('[edit-entry-probe] CLICK CAPTURE #' + capture.id);
    console.log('CLICKED EDIT BUTTON');
    console.log(safeJson(capture.button));
    console.log('PANEL CONTEXT AT CLICK');
    console.log(safeJson(capture.panelAtClick));
    console.log('GET RAW CALLS');
    console.log(safeJson(capture.getRawCalls));
    console.log('GEMINI ENTRY API CALLS');
    console.log(safeJson(capture.apiCalls));
    console.log('FORM SNAPSHOT');
    console.log(safeJson(capture.formSnapshot));
    console.log('DIAGNOSIS');
    console.log(safeJson({
      raw_call_count: capture.getRawCalls.length,
      deletion_status_call_count: capture.apiCalls.filter(function (call) {
        return String(call.url || '').indexOf('/api/gemini_entry/deletion_votes') >= 0;
      }).length,
      deletion_status_last: (function () {
        var matches = capture.apiCalls.filter(function (call) {
          return String(call.url || '').indexOf('/api/gemini_entry/deletion_votes') >= 0;
        });
        return matches.length ? matches[matches.length - 1].response : null;
      })(),
      raw_result_present: !!capture.rawResult,
      raw_has_headword: !!(capture.rawResult && capture.rawResult.headword),
      raw_has_pos: !!(capture.rawResult && capture.rawResult.pos),
      raw_has_glosses: !!(capture.rawResult && Array.isArray(capture.rawResult.glosses) && capture.rawResult.glosses.length),
      form_exists: !!(capture.formSnapshot && capture.formSnapshot.exists),
      form_headword: capture.formSnapshot ? capture.formSnapshot.headword : '',
      form_pos: capture.formSnapshot ? capture.formSnapshot.pos : '',
      form_gloss_count: (capture.formSnapshot && Array.isArray(capture.formSnapshot.glosses)) ? capture.formSnapshot.glosses.length : 0,
      form_commentary: capture.formSnapshot ? capture.formSnapshot.commentary : undefined,
      form_lemma: capture.formSnapshot ? capture.formSnapshot.lemma : undefined,
      likely_failure_stage: (
        !capture.getRawCalls.length ? 'edit-click-never-called-getRawGeminiEntry' :
        (!capture.rawResult ? 'getRawGeminiEntry-returned-null-or-never-resolved' :
        ((capture.rawResult.headword || capture.rawResult.pos || (capture.rawResult.glosses || []).length) &&
         capture.formSnapshot && capture.formSnapshot.exists &&
         !capture.formSnapshot.headword && !capture.formSnapshot.pos && !(capture.formSnapshot.glosses || []).join('').trim()
          ? 'raw-data-exists-but-form-rendered-blank'
          : (!capture.formSnapshot || !capture.formSnapshot.exists)
            ? 'raw-data-returned-but-form-did-not-open'
            : 'see-raw-vs-form-values')))
    }));
  }

  function finalizeCapture(capture, reason) {
    if (!capture || capture.finalized) return;
    capture.finalized = true;
    capture.finalizedAt = nowMs();
    capture.reason = reason || 'timeout';
    capture.formSnapshot = snapshotForm();
    dumpCapture(capture);
  }

  function scheduleFinalize(capture) {
    if (!capture) return;
    if (capture.timerId) clearTimeout(capture.timerId);
    capture.timerId = setTimeout(function () {
      finalizeCapture(capture, 'capture-window-finished');
      if (state.activeCapture === capture) state.activeCapture = null;
    }, CAPTURE_WINDOW_MS);
  }

  function startCapture(btn, ev) {
    var capture = {
      id: state.nextId++,
      startedAt: nowMs(),
      button: summarizeButton(btn),
      panelAtClick: capturePanelContext(),
      click: {
        x: ev && typeof ev.clientX === 'number' ? ev.clientX : null,
        y: ev && typeof ev.clientY === 'number' ? ev.clientY : null
      },
      getRawCalls: [],
      apiCalls: [],
      rawResult: null,
      formSnapshot: null,
      finalized: false,
      timerId: null
    };
    state.captures.push(capture);
    state.activeCapture = capture;
    scheduleFinalize(capture);
    return capture;
  }

  function installObserver() {
    var panel = document.getElementById('panel-content');
    var root = panel || document.body;
    if (!root || typeof MutationObserver !== 'function') return;
    state.observer = new MutationObserver(function () {
      var capture = state.activeCapture;
      if (!capture || capture.finalized) return;
      if (document.getElementById('entry-form')) {
        capture.formSnapshot = snapshotForm();
      }
    });
    state.observer.observe(root, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['value']
    });
  }

  function wrapDictionaryClient() {
    if (!window.DictionaryClient || typeof window.DictionaryClient.getRawGeminiEntry !== 'function') {
      return false;
    }
    if (state.originalGetRaw) return true;
    state.dc = window.DictionaryClient;
    state.originalGetRaw = state.dc.getRawGeminiEntry;
    state.dc.getRawGeminiEntry = function (langCode, headword) {
      var capture = state.activeCapture;
      var call = {
        t: nowMs(),
        langCode: String(langCode || ''),
        headword: String(headword || '')
      };
      if (capture) capture.getRawCalls.push(call);
      var out = state.originalGetRaw.apply(this, arguments);
      return Promise.resolve(out).then(function (raw) {
        call.resolvedAt = nowMs();
        call.result = summarizeRaw(raw);
        if (capture && !capture.rawResult) capture.rawResult = call.result;
        return raw;
      }, function (err) {
        call.resolvedAt = nowMs();
        call.error = String((err && (err.stack || err.message)) || err || '');
        throw err;
      });
    };
    state.dc.getRawGeminiEntry.__editProbeWrapped = true;
    return true;
  }

  function wrapFetch() {
    if (!state.originalFetch || window.fetch !== state.originalFetch) return true;
    window.fetch = function (input, init) {
      var requestUrl = '';
      try {
        requestUrl = typeof input === 'string' ? input : String((input && input.url) || '');
      } catch (_e) {}
      var capture = state.activeCapture;
      var shouldTrack = !!(capture && requestUrl.indexOf('/api/gemini_entry/') >= 0);
      var call = null;
      if (shouldTrack) {
        call = {
          t: nowMs(),
          url: requestUrl,
          method: String((init && init.method) || 'GET'),
          body: (init && typeof init.body === 'string') ? init.body : ''
        };
        capture.apiCalls.push(call);
      }
      return state.originalFetch.apply(this, arguments).then(function (resp) {
        if (!call) return resp;
        call.status = resp.status;
        call.ok = !!resp.ok;
        try {
          return resp.clone().json().then(function (data) {
            call.response = data;
            return resp;
          }).catch(function () {
            return resp.clone().text().then(function (text) {
              call.response_text = text;
              return resp;
            }).catch(function () {
              return resp;
            });
          });
        } catch (_e2) {
          return resp;
        }
      }, function (err) {
        if (call) call.error = String((err && (err.stack || err.message)) || err || '');
        throw err;
      });
    };
    return true;
  }

  function ensureWrapped() {
    wrapFetch();
    if (wrapDictionaryClient()) return;
    if (state.wrapTimer) clearInterval(state.wrapTimer);
    state.wrapTimer = setInterval(function () {
      if (wrapDictionaryClient()) {
        clearInterval(state.wrapTimer);
        state.wrapTimer = null;
        console.log('[edit-entry-probe] DictionaryClient hook installed.');
      }
    }, 250);
  }

  function handleClick(ev) {
    var btn = ev.target && ev.target.closest ? ev.target.closest('.dict-entry-edit-btn') : null;
    if (!btn) return;
    startCapture(btn, ev);
  }

  function stop() {
    if (state.clickHandler) {
      document.removeEventListener('click', state.clickHandler, true);
      state.clickHandler = null;
    }
    if (state.observer) {
      state.observer.disconnect();
      state.observer = null;
    }
    if (state.wrapTimer) {
      clearInterval(state.wrapTimer);
      state.wrapTimer = null;
    }
    if (state.originalFetch) {
      window.fetch = state.originalFetch;
    }
    if (state.dc && state.originalGetRaw) {
      state.dc.getRawGeminiEntry = state.originalGetRaw;
    }
  }

  state.clickHandler = handleClick;
  document.addEventListener('click', state.clickHandler, true);
  installObserver();
  ensureWrapped();

  window.__editEntryProbe = {
    logs: state.captures,
    last: function () {
      return state.captures.length ? state.captures[state.captures.length - 1] : null;
    },
    dump: function () {
      for (var i = 0; i < state.captures.length; i++) dumpCapture(state.captures[i]);
    },
    snapshotForm: snapshotForm,
    stop: stop
  };

  console.log('[edit-entry-probe] ready. Click one Edit button, wait about 1.5s, then inspect the console dump or run __editEntryProbe.last().');
})();
