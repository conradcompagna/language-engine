/*
DevTools snippet: edit-cancel restore-path probe

Paste into the browser console on the reader page. Then:
- click an Edit button on the problematic entry
- click Cancel
- wait about 1.5s

It will print one capture showing:
- which entry launched Edit
- what closeEntryFormPanel(...) was called with
- whether lookupAndDisplay(...) was used on cancel
- what displayDictEntry(...) finally rendered after cancel
- tokenMapData / panelEntry context before and after

Primary globals:
- __cancelRestoreProbe.logs
- __cancelRestoreProbe.last()
- __cancelRestoreProbe.dump()
- __cancelRestoreProbe.stop()
*/
(function () {
  if (window.__cancelRestoreProbe && typeof window.__cancelRestoreProbe.stop === 'function') {
    try { window.__cancelRestoreProbe.stop(); } catch (_e) {}
  }

  var CAPTURE_WINDOW_MS = 1500;

  var state = {
    startedAt: performance.now(),
    nextId: 1,
    captures: [],
    activeCapture: null,
    originalFns: {},
    clickHandler: null,
    observer: null
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

  function summarizeEntry(entry) {
    if (!entry || typeof entry !== 'object') return null;
    var fill = Array.isArray(entry.dict_fill) ? entry.dict_fill : [];
    return {
      headword: entry.headword || '',
      head: entry.head || '',
      text: entry.text || '',
      surface_form: entry.surface_form || '',
      pos: entry.pos || '',
      _source: entry._source || '',
      _dict_source: entry._dict_source || '',
      dict_fill: fill.map(function (part) {
        return {
          headword: part && part.headword || '',
          head: part && part.head || '',
          text: part && part.text || '',
          surface_form: part && part.surface_form || '',
          pos: part && part.pos || '',
          _source: part && part._source || '',
          _dict_source: part && part._dict_source || ''
        };
      })
    };
  }

  function summarizeTokenMap() {
    var data = window.tokenMapData;
    if (!data || typeof data !== 'object') return null;
    return {
      surface: data.surface || '',
      lemma: data.lemma || '',
      segIdx: data.segIdx,
      panelEntry: summarizeEntry(data.panelEntry),
      tokenEntry: summarizeEntry(data.tokenEntry || data.entry)
    };
  }

  function summarizePanel() {
    var panel = document.getElementById('panel-content');
    if (!panel) {
      return { exists: false };
    }
    return {
      exists: true,
      node: describeNode(panel),
      text: cleanText(panel.textContent),
      editButtons: Array.from(panel.querySelectorAll('.dict-entry-edit-btn')).map(function (btn) {
        return {
          text: cleanText(btn.textContent),
          dataset: cloneDataset(btn)
        };
      }),
      headlines: Array.from(panel.querySelectorAll('.popup-headline, .dict-entry-part-head')).map(function (node) {
        return cleanText(node.textContent);
      }).filter(Boolean)
    };
  }

  function safeJson(value) {
    try {
      return JSON.stringify(value, null, 2);
    } catch (_e) {
      return String(value);
    }
  }

  function finalizeCapture(capture, reason) {
    if (!capture || capture.finalized) return;
    capture.finalized = true;
    capture.finalizedAt = nowMs();
    capture.reason = reason || 'timeout';
    capture.afterTokenMap = summarizeTokenMap();
    capture.afterPanel = summarizePanel();
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

  function dumpCapture(capture) {
    console.log('[cancel-restore-probe] CAPTURE #' + capture.id);
    console.log('EDIT CLICK');
    console.log(safeJson(capture.editClick));
    console.log('TOKEN MAP / PANEL BEFORE');
    console.log(safeJson({
      beforeTokenMap: capture.beforeTokenMap,
      beforePanel: capture.beforePanel
    }));
    console.log('FUNCTION CALLS');
    console.log(safeJson(capture.calls));
    console.log('TOKEN MAP / PANEL AFTER');
    console.log(safeJson({
      afterTokenMap: capture.afterTokenMap,
      afterPanel: capture.afterPanel
    }));
    console.log('DIAGNOSIS');
    var closeCalls = capture.calls.filter(function (call) { return call.fn === 'closeEntryFormPanel'; });
    var lookupCalls = capture.calls.filter(function (call) { return call.fn === 'lookupAndDisplay'; });
    var displayCalls = capture.calls.filter(function (call) { return call.fn === 'displayDictEntry'; });
    console.log(safeJson({
      close_call_count: closeCalls.length,
      close_last: closeCalls.length ? closeCalls[closeCalls.length - 1] : null,
      lookup_call_count: lookupCalls.length,
      lookup_last: lookupCalls.length ? lookupCalls[lookupCalls.length - 1] : null,
      display_call_count: displayCalls.length,
      display_last: displayCalls.length ? displayCalls[displayCalls.length - 1] : null,
      likely_issue: (
        closeCalls.length && lookupCalls.length
          ? 'cancel-is-doing-fresh-lookupAndDisplay-instead-of-restoring-existing-panel-entry'
          : closeCalls.length
            ? 'closeEntryFormPanel-fired-but-no-lookup-observed'
            : 'inspect-call-sequence'
      )
    }));
  }

  function startCapture(btn, ev) {
    var capture = {
      id: state.nextId++,
      startedAt: nowMs(),
      editClick: {
        node: describeNode(btn),
        text: cleanText(btn.textContent),
        dataset: cloneDataset(btn),
        x: ev && typeof ev.clientX === 'number' ? ev.clientX : null,
        y: ev && typeof ev.clientY === 'number' ? ev.clientY : null
      },
      beforeTokenMap: summarizeTokenMap(),
      beforePanel: summarizePanel(),
      calls: [],
      afterTokenMap: null,
      afterPanel: null,
      finalized: false,
      timerId: null
    };
    state.captures.push(capture);
    state.activeCapture = capture;
    scheduleFinalize(capture);
    return capture;
  }

  function recordCall(fnName, payload) {
    var capture = state.activeCapture;
    if (!capture || capture.finalized) return;
    capture.calls.push({
      t: nowMs(),
      fn: fnName,
      payload: payload || null
    });
  }

  function wrapFunction(name, summarizer) {
    var original = window[name];
    if (typeof original !== 'function') return;
    state.originalFns[name] = original;
    window[name] = function () {
      try {
        recordCall(name, summarizer ? summarizer(arguments) : null);
      } catch (_e) {}
      return original.apply(this, arguments);
    };
    window[name].__cancelRestoreProbeWrapped = true;
  }

  function installWrappers() {
    wrapFunction('showGeminiEditPanel', function (args) {
      return {
        headword: String(args[0] || ''),
        lang: String(args[1] || ''),
        source: String(args[2] || '')
      };
    });
    wrapFunction('closeEntryFormPanel', function (args) {
      return {
        preferredHeadword: String(args[0] || ''),
        tokenMap: summarizeTokenMap()
      };
    });
    wrapFunction('lookupAndDisplay', function (args) {
      return {
        token: String(args[0] || ''),
        options: args[1] || null
      };
    });
    wrapFunction('displayDictEntry', function (args) {
      return {
        originalToken: String(args[1] || ''),
        entry: summarizeEntry(args[0]),
        fullData: args[2] || null
      };
    });
  }

  function installObserver() {
    var root = document.getElementById('panel-content') || document.body;
    if (!root || typeof MutationObserver !== 'function') return;
    state.observer = new MutationObserver(function () {
      var capture = state.activeCapture;
      if (!capture || capture.finalized) return;
      capture.afterPanel = summarizePanel();
    });
    state.observer.observe(root, {
      childList: true,
      subtree: true
    });
  }

  function handleClick(ev) {
    var editBtn = ev.target && ev.target.closest ? ev.target.closest('.dict-entry-edit-btn') : null;
    if (editBtn) {
      startCapture(editBtn, ev);
      return;
    }
    var cancelBtn = ev.target && ev.target.closest ? ev.target.closest('#ef-cancel-btn') : null;
    if (cancelBtn && state.activeCapture) {
      recordCall('cancel-click', {
        node: describeNode(cancelBtn),
        text: cleanText(cancelBtn.textContent)
      });
      scheduleFinalize(state.activeCapture);
    }
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
    Object.keys(state.originalFns).forEach(function (name) {
      window[name] = state.originalFns[name];
    });
  }

  installWrappers();
  installObserver();
  state.clickHandler = handleClick;
  document.addEventListener('click', state.clickHandler, true);

  window.__cancelRestoreProbe = {
    logs: state.captures,
    last: function () {
      return state.captures.length ? state.captures[state.captures.length - 1] : null;
    },
    dump: function () {
      for (var i = 0; i < state.captures.length; i++) dumpCapture(state.captures[i]);
    },
    stop: stop
  };

  console.log('[cancel-restore-probe] ready. Click Edit, then Cancel, then inspect the console dump or run __cancelRestoreProbe.last().');
})();
