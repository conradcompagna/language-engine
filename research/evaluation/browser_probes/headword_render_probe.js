/*
DevTools snippet: click-scoped headword render probe

Paste into the browser console on the reader page. After that:
- click one token
- wait about 1.3s
- the probe prints one fully expanded dump for that click

What it records:
- clicked token metadata
- fetches started during the click window, including /lookup and /subsegments payloads
- side-panel DOM snapshot
- detailed headword-row analysis showing exact child-node order

Primary globals:
- __headwordProbe.logs
- __headwordProbe.last()
- __headwordProbe.dump()
- __headwordProbe.stop()
*/
(function () {
  if (window.__headwordProbe && typeof window.__headwordProbe.stop === 'function') {
    try { window.__headwordProbe.stop(); } catch (_e) {}
  }

  var CAPTURE_WINDOW_MS = 1300;

  var state = {
    startedAt: performance.now(),
    nextId: 1,
    logs: [],
    activeCapture: null,
    clickHandler: null,
    originalFetch: window.fetch
  };

  function nowMs() {
    return Math.round(performance.now() - state.startedAt);
  }

  function cleanText(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
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

  function describeNode(node) {
    if (!node || !node.tagName) return '';
    var parts = [String(node.tagName || '').toLowerCase()];
    if (node.id) parts.push('#' + node.id);
    if (node.classList && node.classList.length) {
      parts.push('.' + Array.from(node.classList).join('.'));
    }
    return parts.join('');
  }

  function summarizeEntry(entry, path) {
    var e = entry || {};
    return {
      path: path,
      headword: e.headword || '',
      head: e.head || '',
      text: e.text || '',
      surface_form: e.surface_form || '',
      pos: e.pos || '',
      source: e.source || '',
      _source: e._source || '',
      _dict_source: e._dict_source || '',
      reading: e.reading || '',
      senses_count: Array.isArray(e.senses) ? e.senses.length : 0,
      senses_hover_count: Array.isArray(e.senses_hover) ? e.senses_hover.length : 0,
      subsegments_count: Array.isArray(e.subsegments) ? e.subsegments.length : 0,
      dict_fill_count: Array.isArray(e.dict_fill) ? e.dict_fill.length : 0,
      dict_fill: Array.isArray(e.dict_fill) ? e.dict_fill.map(function (part, i) {
        return summarizeEntry(part, path + '.dict_fill[' + i + ']');
      }) : []
    };
  }

  function summarizeSubsegmentsPayload(data, url) {
    var subs = Array.isArray(data && data.subsegments) ? data.subsegments : [];
    return {
      t: nowMs(),
      kind: 'subsegments',
      url: String(url || ''),
      token: data && data.token || '',
      subsegments: subs.map(function (entry, i) {
        return summarizeEntry(entry, 'subsegments[' + i + ']');
      })
    };
  }

  function summarizeLookupPayload(data, url) {
    var results = Array.isArray(data && data.results) ? data.results : [];
    var resultsBySeg = Array.isArray(data && data.results_by_seg) ? data.results_by_seg : [];
    return {
      t: nowMs(),
      kind: 'lookup',
      url: String(url || ''),
      q: data && data.q || '',
      results: results.map(function (entry, i) {
        return summarizeEntry(entry, 'results[' + i + ']');
      }),
      results_by_seg: resultsBySeg.map(function (entry, i) {
        return summarizeEntry(entry, 'results_by_seg[' + i + ']');
      })
    };
  }

  function captureChildFlow(node) {
    return Array.from(node.childNodes || []).map(function (child, idx) {
      if (child.nodeType === Node.TEXT_NODE) {
        return {
          index: idx,
          type: 'text',
          text: child.textContent,
          clean_text: cleanText(child.textContent)
        };
      }
      var el = child;
      return {
        index: idx,
        type: 'element',
        node: describeNode(el),
        text: el.textContent,
        clean_text: cleanText(el.textContent),
        data_seg: el.getAttribute ? (el.getAttribute('data-seg') || '') : '',
        data_hover_mode: el.getAttribute ? (el.getAttribute('data-hover-mode') || '') : '',
        html: el.outerHTML
      };
    });
  }

  function summarizeHeadwordComponents(node) {
    return Array.from(node.querySelectorAll('.headword-component')).map(function (el, idx) {
      return {
        index: idx,
        text: el.textContent,
        clean_text: cleanText(el.textContent),
        data_seg: el.getAttribute('data-seg') || '',
        data_hover_mode: el.getAttribute('data-hover-mode') || '',
        html: el.outerHTML
      };
    });
  }

  function summarizeRows(container) {
    var selectors = [
      '.dict-entry-part-head .popup-headline',
      '.sense-head-inline',
      '.sense-head-inline-main',
      '.popup-headline'
    ];
    var seen = new Set();
    var rows = [];
    for (var si = 0; si < selectors.length; si++) {
      var nodes = container.querySelectorAll(selectors[si]);
      for (var ni = 0; ni < nodes.length; ni++) {
        var node = nodes[ni];
        if (seen.has(node)) continue;
        seen.add(node);
        rows.push({
          selector: selectors[si],
          node: describeNode(node),
          text: node.textContent,
          clean_text: cleanText(node.textContent),
          inner_html: node.innerHTML,
          child_flow: captureChildFlow(node),
          components: summarizeHeadwordComponents(node)
        });
      }
    }
    return rows;
  }

  function parsePanel() {
    var container = document.getElementById('panel-content');
    if (!container) {
      return { exists: false };
    }
    var style = window.getComputedStyle(container);
    return {
      t: nowMs(),
      exists: true,
      node: '#panel-content',
      display: style.display,
      visibility: style.visibility,
      opacity: style.opacity,
      text: cleanText(container.textContent || ''),
      inner_html: container.innerHTML,
      rows: summarizeRows(container)
    };
  }

  function printCapture(capture) {
    console.log('[headword-probe] CLICK CAPTURE #' + capture.id);
    console.log('CLICKED TOKEN');
    console.log(JSON.stringify(capture.click, null, 2));
    console.log('FETCHES');
    console.log(JSON.stringify(capture.fetches, null, 2));
    console.log('SIDE PANEL');
    console.log(JSON.stringify(capture.panel, null, 2));
  }

  function finalizeCapture(capture) {
    if (!capture || capture.finalized) return;
    capture.finalized = true;
    capture.finalized_at = nowMs();
    capture.panel = parsePanel();
    state.logs.push(capture);
    if (state.logs.length > 30) state.logs.shift();
    printCapture(capture);
  }

  window.fetch = function patchedFetch(input, init) {
    var url = (typeof input === 'string')
      ? input
      : (input && typeof input.url === 'string' ? input.url : '');
    return state.originalFetch.call(this, input, init).then(function (resp) {
      var active = state.activeCapture;
      if (!active || !url) return resp;
      var clone = resp.clone();
      clone.text().then(function (raw) {
        if (!raw) return;
        var data;
        try { data = JSON.parse(raw); } catch (_e) { return; }
        if (!active || active.finalized) return;
        if (url.indexOf('/lookup') >= 0 || url.indexOf('/lookup_dp_only') >= 0) {
          active.fetches.push(summarizeLookupPayload(data, url));
        } else if (url.indexOf('/subsegments') >= 0) {
          active.fetches.push(summarizeSubsegmentsPayload(data, url));
        }
      }).catch(function () {});
      return resp;
    });
  };

  state.clickHandler = function (ev) {
    var rawTarget = ev.target;
    var token = rawTarget && rawTarget.closest
      ? rawTarget.closest('.reader-token, .reader-token-fill-hit, .chunk-token, .hover-reticle-token')
      : null;
    if (!token) return;

    var capture = {
      id: state.nextId++,
      started_at: nowMs(),
      finalized: false,
      fetches: [],
      click: {
        token_node: describeNode(token),
        token_text: cleanText(token.textContent || ''),
        dataset: cloneDataset(token),
        clicked_dom_target: describeNode(rawTarget),
        clicked_dom_text: cleanText(rawTarget && rawTarget.textContent || ''),
        x: ev.clientX,
        y: ev.clientY
      }
    };

    state.activeCapture = capture;
    window.setTimeout(function () {
      if (state.activeCapture === capture) {
        finalizeCapture(capture);
        state.activeCapture = null;
      }
    }, CAPTURE_WINDOW_MS);
  };

  document.addEventListener('click', state.clickHandler, true);

  window.__headwordProbe = {
    logs: state.logs,
    last: function () {
      return state.logs.length ? state.logs[state.logs.length - 1] : null;
    },
    dump: function () {
      var last = this.last();
      if (!last) {
        console.log('[headword-probe] no captures yet');
        return null;
      }
      printCapture(last);
      return last;
    },
    stop: function () {
      try {
        document.removeEventListener('click', state.clickHandler, true);
      } catch (_e) {}
      try {
        window.fetch = state.originalFetch;
      } catch (_e2) {}
      delete window.__headwordProbe;
    }
  };

  console.log('[headword-probe] ready. Click one token, wait about 1.3s, then inspect the console dump or run __headwordProbe.last().');
})();
