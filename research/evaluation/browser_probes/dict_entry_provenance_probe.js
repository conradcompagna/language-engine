/*
DevTools snippet: click-scoped dictionary provenance / edit probe

Paste into the browser console on the reader page. After that:
- click one token
- wait about a second
- the probe prints one verbose, fully expanded text dump for that click
- click another token to get another dump

What it records for each click:
- clicked token metadata
- fetch payloads initiated during that click window
- rendered side-panel dictionary DOM snapshot
- rendered hover-popup DOM snapshot
- simple diagnosis fields for provenance badge / edit-button presence

Primary globals:
- __dictEntryProbe.logs
- __dictEntryProbe.last()
- __dictEntryProbe.dump()
- __dictEntryProbe.stop()
*/
(function () {
  if (window.__dictEntryProbe && typeof window.__dictEntryProbe.stop === 'function') {
    try { window.__dictEntryProbe.stop(); } catch (_e) {}
  }

  var CAPTURE_WINDOW_MS = 1200;

  var state = {
    startedAt: performance.now(),
    nextId: 1,
    captures: [],
    captureById: Object.create(null),
    activeCapture: null,
    originalFetch: window.fetch,
    clickHandler: null
  };

  function nowMs() {
    return Math.round(performance.now() - state.startedAt);
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

  function cleanText(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function getTokenTarget(rawTarget) {
    if (!rawTarget || !rawTarget.closest) return null;
    return rawTarget.closest('.reader-token, .reader-token-fill-hit, .panel-token, .headword-component');
  }

  function summarizeFillEntry(entry, path) {
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
      senses_count: Array.isArray(e.senses) ? e.senses.length : 0,
      senses_hover_count: Array.isArray(e.senses_hover) ? e.senses_hover.length : 0
    };
  }

  function summarizeEntry(entry, path) {
    var e = entry || {};
    var fill = Array.isArray(e.dict_fill) ? e.dict_fill : [];
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
      senses_count: Array.isArray(e.senses) ? e.senses.length : 0,
      senses_hover_count: Array.isArray(e.senses_hover) ? e.senses_hover.length : 0,
      dict_fill_count: fill.length,
      dict_fill: fill.map(function (part, i) {
        return summarizeFillEntry(part, path + '.dict_fill[' + i + ']');
      })
    };
  }

  function summarizeLookupPayload(data, url) {
    var results = Array.isArray(data && data.results) ? data.results : [];
    var resultsBySeg = Array.isArray(data && data.results_by_seg) ? data.results_by_seg : [];
    return {
      t: nowMs(),
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

  function parseRender(kind) {
    var container = kind === 'panel'
      ? document.getElementById('panel-content')
      : document.getElementById('hoverPopup');
    if (!container) {
      return {
        kind: kind,
        exists: false
      };
    }
    var style = window.getComputedStyle(container);
    return {
      t: nowMs(),
      kind: kind,
      exists: true,
      node: '#' + (container.id || container.className || kind),
      connected: !!container.isConnected,
      display: style.display,
      visibility: style.visibility,
      opacity: style.opacity,
      html_length: container.innerHTML.length,
      text: cleanText(container.textContent || ''),
      plain_headlines: Array.from(container.querySelectorAll('.popup-headline')).map(function (node) {
        return cleanText(node.textContent || '');
      }),
      part_heads: Array.from(container.querySelectorAll('.dict-entry-part-head .popup-headline')).map(function (node) {
        return cleanText(node.textContent || '');
      }),
      sense_meta_rows: Array.from(container.querySelectorAll('.sense-head-inline')).map(function (row, idx) {
        return {
          index: idx,
          text: cleanText(row.textContent || ''),
          main: cleanText((row.querySelector('.sense-head-inline-main') || row).textContent || ''),
          badges: Array.from(row.querySelectorAll('.dict-source-badge')).map(function (badge) {
            return cleanText(badge.textContent || '');
          }),
          edits: Array.from(row.querySelectorAll('.dict-entry-edit-btn')).map(function (btn) {
            return {
              text: cleanText(btn.textContent || ''),
              data_headword: btn.getAttribute('data-headword') || '',
              data_source: btn.getAttribute('data-source') || '',
              data_lang: btn.getAttribute('data-lang') || ''
            };
          })
        };
      }),
      badges_anywhere: Array.from(container.querySelectorAll('.dict-source-badge')).map(function (badge, idx) {
        return {
          index: idx,
          text: cleanText(badge.textContent || ''),
          classes: String(badge.className || ''),
          parent_text: cleanText((badge.parentElement && badge.parentElement.textContent) || '')
        };
      }),
      edits_anywhere: Array.from(container.querySelectorAll('.dict-entry-edit-btn')).map(function (btn, idx) {
        return {
          index: idx,
          text: cleanText(btn.textContent || ''),
          classes: String(btn.className || ''),
          data_headword: btn.getAttribute('data-headword') || '',
          data_source: btn.getAttribute('data-source') || '',
          data_lang: btn.getAttribute('data-lang') || '',
          parent_text: cleanText((btn.parentElement && btn.parentElement.textContent) || '')
        };
      }),
      inner_html: container.innerHTML
    };
  }

  function payloadHasSource(fetches) {
    return (fetches || []).some(function (summary) {
      var buckets = []
        .concat(summary.results || [])
        .concat(summary.results_by_seg || []);
      return buckets.some(function (entry) {
        if (entry._dict_source || entry._source || entry.source) return true;
        return (entry.dict_fill || []).some(function (fill) {
          return !!(fill._dict_source || fill._source || fill.source);
        });
      });
    });
  }

  function buildDiagnosis(capture) {
    var panel = capture.panel || {};
    var popup = capture.popup || {};
    return {
      click_token_text: capture.click && capture.click.token_text || '',
      click_token_seg: capture.click && capture.click.dataset && capture.click.dataset.seg || '',
      fetch_count: (capture.fetches || []).length,
      payload_has_source: payloadHasSource(capture.fetches),
      panel_has_badges: !!(panel.badges_anywhere && panel.badges_anywhere.length),
      panel_has_edit: !!(panel.edits_anywhere && panel.edits_anywhere.length),
      panel_has_plain_part_head: !!(panel.part_heads && panel.part_heads.length),
      panel_has_sense_meta_rows: !!(panel.sense_meta_rows && panel.sense_meta_rows.length),
      popup_has_badges: !!(popup.badges_anywhere && popup.badges_anywhere.length),
      popup_has_edit: !!(popup.edits_anywhere && popup.edits_anywhere.length),
      popup_has_sense_meta_rows: !!(popup.sense_meta_rows && popup.sense_meta_rows.length)
    };
  }

  function formatCapture(capture) {
    var lines = [];
    lines.push('[dict-entry-probe] CLICK CAPTURE #' + capture.id);
    lines.push('');
    lines.push('CLICKED TOKEN');
    lines.push(JSON.stringify(capture.click, null, 2));
    lines.push('');
    lines.push('FETCH PAYLOADS STARTED DURING THIS CLICK WINDOW');
    lines.push(JSON.stringify(capture.fetches, null, 2));
    lines.push('');
    lines.push('SIDE PANEL SNAPSHOT');
    lines.push(JSON.stringify(capture.panel, null, 2));
    lines.push('');
    lines.push('HOVER POPUP SNAPSHOT');
    lines.push(JSON.stringify(capture.popup, null, 2));
    lines.push('');
    lines.push('DIAGNOSIS');
    lines.push(JSON.stringify(capture.diagnosis, null, 2));
    return lines.join('\n');
  }

  function finalizeCapture(capture) {
    if (!capture || capture.finalized) return;
    capture.finalized = true;
    capture.finalized_at = nowMs();
    capture.panel = parseRender('panel');
    capture.popup = parseRender('popup');
    capture.diagnosis = buildDiagnosis(capture);
    state.captures.push(capture);
    if (state.captures.length > 50) state.captures.shift();
    console.log(formatCapture(capture));
    if (state.activeCapture && state.activeCapture.id === capture.id) {
      state.activeCapture = null;
    }
  }

  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : ((input && input.url) || '');
    var captureIdAtRequest = state.activeCapture ? state.activeCapture.id : null;
    return state.originalFetch.call(this, input, init).then(function (response) {
      var interesting = /\/lookup(?:\?|$)|\/lookup_dp_only(?:\?|$)|\/subsegments(?:\?|$)/.test(String(url || ''));
      var contentType = String(response.headers.get('Content-Type') || '');
      if (interesting && contentType.indexOf('application/json') >= 0) {
        response.clone().json().then(function (data) {
          var summary = summarizeLookupPayload(data, url);
          var capture = captureIdAtRequest ? state.captureById[captureIdAtRequest] : null;
          if (capture) {
            capture.fetches.push(summary);
          }
        }).catch(function (err) {
          console.warn('[dict-entry-probe] failed to read JSON', url, err);
        });
      }
      return response;
    });
  };

  function onClick(ev) {
    var token = getTokenTarget(ev.target);
    if (!token) return;

    var capture = {
      id: state.nextId++,
      started_at: nowMs(),
      click: {
        token_node: describeNode(token),
        token_text: cleanText(token.textContent || ''),
        dataset: cloneDataset(token),
        clicked_dom_target: describeNode(ev.target),
        clicked_dom_text: cleanText((ev.target && ev.target.textContent) || ''),
        x: ev.clientX,
        y: ev.clientY
      },
      fetches: [],
      panel: null,
      popup: null,
      diagnosis: null,
      finalized: false
    };

    state.captureById[capture.id] = capture;
    state.activeCapture = capture;

    setTimeout(function () {
      finalizeCapture(capture);
    }, CAPTURE_WINDOW_MS);
  }

  state.clickHandler = onClick;
  document.addEventListener('click', state.clickHandler, true);

  window.__dictEntryProbe = {
    logs: state.captures,
    state: state,
    last: function () {
      return state.captures.length ? state.captures[state.captures.length - 1] : null;
    },
    dump: function (index) {
      var capture;
      if (typeof index === 'number') {
        capture = state.captures[index] || null;
      } else {
        capture = state.captures.length ? state.captures[state.captures.length - 1] : null;
      }
      if (!capture) return '[dict-entry-probe] no captures yet';
      var text = formatCapture(capture);
      console.log(text);
      return text;
    },
    stop: function () {
      window.fetch = state.originalFetch;
      if (state.clickHandler) {
        document.removeEventListener('click', state.clickHandler, true);
      }
      console.log('[dict-entry-probe] stopped');
    }
  };

  console.log('[dict-entry-probe] ready. Click a token. One verbose capture will be printed for each click.');
})();
