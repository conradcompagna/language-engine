/**
 * llm_assistant.js — Floating Gemini LLM assistant for Language Engine reader.
 *
 * Renders a floating icon (bottom-right corner) for paid users.
 * Clicking opens a small chat panel that sends user queries along with
 * the current parsed text from the reader pane to the Gemini API via
 * the backend /api/llm_query endpoint.
 *
 * The piped context is the rendered text from #renderedText, which
 * contains the parsed/tokenized output with dict entries — NOT the
 * raw input textarea.
 */
(function () {
  'use strict';

  var userTier = 'free';
  var panelOpen = false;
  var chatHistory = [];
  var requestInFlight = false;
  var uiCreated = false;
  var PANEL_STATE_STORAGE_KEY = 'le_llm_panel_state';
  var FAB_STATE_STORAGE_KEY = 'le_llm_fab_state';
  var PANEL_DEFAULT_WIDTH = 760;
  var PANEL_DEFAULT_HEIGHT = 560;
  var PANEL_MIN_WIDTH = 320;
  var PANEL_MIN_HEIGHT = 260;
  var PANEL_MARGIN = 12;

  // --- Chat exchange memory (verbatim rolling window, persisted in localStorage) ---
  var EXCHANGE_STORAGE_KEY = 'le_chat_exchanges';
  var MAX_EXCHANGE_TOKENS = 1000;
  var MAX_READER_CONTEXT_TOKENS = 1000;
  var MAX_TOKEN_CONTEXT_TOKENS = 800;
  var MAX_SENTENCE_CONTEXT_TOKENS = 800;

  // --- Token/Sentence/Reader context state (inline header checkboxes) ---
  var CONTEXT_CHECKBOX_STORAGE_KEY = 'le_llm_context_checkboxes_v2';
  var activeContext = {
    tokenText: '', sentenceText: '', readerText: '',
    tokenSurface: '', segIdx: -1
  };
  function loadContextCheckboxState() {
    try {
      var raw = localStorage.getItem(CONTEXT_CHECKBOX_STORAGE_KEY);
      if (!raw) return { token: true, sentence: false, reader: false };
      var p = JSON.parse(raw);
      if (!p || typeof p !== 'object') return { token: true, sentence: false, reader: false };
      return {
        token: !!p.token,
        sentence: !!p.sentence,
        reader: !!p.reader
      };
    } catch (_e) { return { token: true, sentence: false, reader: false }; }
  }
  function saveContextCheckboxState(state) {
    try { localStorage.setItem(CONTEXT_CHECKBOX_STORAGE_KEY, JSON.stringify(state || {})); } catch (_e) {}
  }

  function estimateTokenCount(text) {
    var raw = String(text || '').trim();
    if (!raw) return 0;
    return Math.max(1, Math.ceil(raw.length / 4));
  }

  function normalizeStoredExchanges(list) {
    var src = Array.isArray(list) ? list : [];
    var out = [];
    var totalTokens = 0;
    for (var i = 0; i < src.length; i++) {
      var item = src[i];
      if (!item || typeof item !== 'object') continue;
      var role = String(item.role || '').trim().toLowerCase();
      if (role !== 'user' && role !== 'assistant') continue;
      var text = String(item.text || '');
      if (!text.trim()) continue;
      out.push({ role: role, text: text });
      totalTokens += estimateTokenCount(text);
    }
    // Trim oldest pair at a time so we never send an orphaned user or assistant turn.
    while (out.length >= 2 && totalTokens > MAX_EXCHANGE_TOKENS) {
      totalTokens -= estimateTokenCount(out[0].text) + estimateTokenCount(out[1].text);
      out.splice(0, 2);
    }
    return out;
  }

  function loadExchanges() {
    try {
      var raw = localStorage.getItem(EXCHANGE_STORAGE_KEY);
      if (raw) return normalizeStoredExchanges(JSON.parse(raw));
    } catch (_e) {}
    return [];
  }

  function saveExchanges(list) {
    try { localStorage.setItem(EXCHANGE_STORAGE_KEY, JSON.stringify(normalizeStoredExchanges(list))); } catch (_e) {}
  }

  function truncateTextToApproxTokens(text, maxTokens) {
    var raw = String(text || '').trim();
    var limit = Math.max(0, Number(maxTokens) || 0);
    if (!raw || !limit) return '';
    var maxChars = limit * 4;
    if (raw.length <= maxChars) return raw;
    return raw.slice(0, maxChars).trim();
  }

  function loadPanelState() {
    try {
      var raw = localStorage.getItem(PANEL_STATE_STORAGE_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return {};
      var out = {};
      if (typeof parsed.left === 'number') out.left = parsed.left;
      if (typeof parsed.top === 'number') out.top = parsed.top;
      if (typeof parsed.width === 'number') out.width = parsed.width;
      if (typeof parsed.height === 'number') out.height = parsed.height;
      return out;
    } catch (_e) {}
    return {};
  }

  function savePanelState(patch) {
    try {
      var current = loadPanelState();
      var next = {
        left: current.left,
        top: current.top,
        width: current.width,
        height: current.height
      };
      if (patch && typeof patch === 'object') {
        ['left', 'top', 'width', 'height'].forEach(function (key) {
          if (Object.prototype.hasOwnProperty.call(patch, key)) {
            if (typeof patch[key] === 'number' && isFinite(patch[key])) next[key] = patch[key];
            else delete next[key];
          }
        });
      }
      localStorage.setItem(PANEL_STATE_STORAGE_KEY, JSON.stringify(next));
    } catch (_e) {}
  }

  function clearPanelState() {
    try { localStorage.removeItem(PANEL_STATE_STORAGE_KEY); } catch (_e) {}
  }

  function loadFabState() {
    try {
      var raw = localStorage.getItem(FAB_STATE_STORAGE_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return {};
      var out = {};
      if (typeof parsed.left === 'number') out.left = parsed.left;
      if (typeof parsed.top === 'number') out.top = parsed.top;
      return out;
    } catch (_e) {}
    return {};
  }

  function saveFabState(position) {
    try {
      var next = {};
      if (position && typeof position === 'object') {
        if (typeof position.left === 'number' && isFinite(position.left)) next.left = position.left;
        if (typeof position.top === 'number' && isFinite(position.top)) next.top = position.top;
      }
      localStorage.setItem(FAB_STATE_STORAGE_KEY, JSON.stringify(next));
    } catch (_e) {}
  }

  function clearFabState() {
    try { localStorage.removeItem(FAB_STATE_STORAGE_KEY); } catch (_e) {}
  }

  function recordChatExchange(userQuery, assistantReply) {
    var list = loadExchanges();
    list.push({ role: 'user', text: String(userQuery || '') });
    list.push({ role: 'assistant', text: String(assistantReply || '') });
    saveExchanges(list);
  }

  function getExchangeContext() {
    var list = loadExchanges();
    if (!list.length) return { history: '', last_exchange: '' };
    // Separate the last user+assistant pair from the older history
    var lastPairStart = list.length >= 2 ? list.length - 2 : 0;
    var olderList = list.slice(0, lastPairStart);
    var lastList = list.slice(lastPairStart);

    var historyParts = [];
    if (olderList.length) {
      historyParts.push('Earlier conversation history with this user:');
      for (var i = 0; i < olderList.length; i++) {
        var item = olderList[i];
        historyParts.push((item.role === 'assistant' ? 'Assistant' : 'User') + ':\n' + String(item.text || ''));
      }
    }

    var lastParts = [];
    if (lastList.length) {
      lastParts.push('Most recent exchange:');
      for (var j = 0; j < lastList.length; j++) {
        var litem = lastList[j];
        lastParts.push((litem.role === 'assistant' ? 'Assistant' : 'User') + ':\n' + String(litem.text || ''));
      }
    }

    return {
      history: historyParts.join('\n\n'),
      last_exchange: lastParts.join('\n\n')
    };
  }

  // Fetch tier
  fetch('/auth/me')
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.ok && d.user) {
        userTier = d.user.tier || 'free';
      }
    })
    .catch(function () {});

  createFloatingUI();

  function escapeHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function getRenderedText() {
    var el = document.getElementById('renderedText');
    if (!el) return '';
    return el.innerText || el.textContent || '';
  }

  function injectAssistantCtxStyles() {
    if (document.getElementById('le-llm-ctx-styles')) return;
    var css = [
      '.llm-ctx-row { display: flex; align-items: center; gap: 12px; padding: 6px 16px; border-bottom: 1px solid var(--le-slate-100, #f1f5f9); background: var(--le-white, #fff); flex-shrink: 0; }',
      '.llm-ctx-row-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--le-slate-500, #64748b); }',
      '.llm-ctx-hdr { display: inline-flex; align-items: center; gap: 10px; }',
      '.llm-ctx-hdr-cb { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 600; color: var(--le-slate-700, #334155); cursor: pointer; user-select: none; }',
      '.llm-ctx-hdr-cb input { margin: 0; cursor: pointer; accent-color: var(--le-green-700, #047857); }',
      '.llm-ctx-last { font-size: 11px; color: var(--le-slate-500, #64748b); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; min-width: 0; margin-left: auto; text-align: right; }',
      '.llm-ctx-last:empty { display: none; }',
      '.llm-ctx-last b { color: var(--le-slate-900, #0f172a); font-weight: 700; }'
    ].join('\n');
    var s = document.createElement('style');
    s.id = 'le-llm-ctx-styles';
    s.textContent = css;
    document.head.appendChild(s);
  }

  function createFloatingUI() {
    if (uiCreated) return;
    uiCreated = true;
    injectAssistantCtxStyles();
    // Floating button
    var btn = document.createElement('button');
    btn.id = 'llm-fab';
    btn.className = 'llm-fab';
    btn.setAttribute('data-native-tooltip', '');
    btn.setAttribute('aria-label', 'Language Assistant');
    btn.title = 'Language Assistant';
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24">'
      + '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'
      + '</svg>';
    document.body.appendChild(btn);

    // Chat panel
    var panel = document.createElement('div');
    panel.id = 'llm-panel';
    panel.className = 'llm-panel';
    panel.style.display = 'none';
    panel.innerHTML = ''
      + '<div class="llm-panel-header">'
      + '  <span class="llm-panel-title">Language Assistant</span>'
      + '  <button type="button" class="llm-panel-reset">Reset</button>'
      + '  <button type="button" class="llm-panel-close">&times;</button>'
      + '</div>'
      + '<div class="llm-ctx-row">'
      + '  <span class="llm-ctx-row-label" data-native-tooltip title="Select what context to send to Language Assistant; doc level context uses more tokens">Select context</span>'
      + '  <span class="llm-ctx-hdr">'
      + '    <label class="llm-ctx-hdr-cb" title="Include clicked token grammar + dictionary context"><input type="checkbox" data-ctx-cb="token">Tok</label>'
      + '    <label class="llm-ctx-hdr-cb" title="Include the clicked token sentence"><input type="checkbox" data-ctx-cb="sentence">Sent</label>'
      + '    <label class="llm-ctx-hdr-cb" title="Include the full reader text"><input type="checkbox" data-ctx-cb="reader">Doc</label>'
      + '  </span>'
      + '  <span class="llm-ctx-last" id="llmCtxLastToken"></span>'
      + '</div>'
      + '<div class="llm-panel-messages" id="llmMessages"></div>'
      + '<div class="llm-panel-input-row">'
      + '  <textarea id="llmInput" class="llm-input" rows="2" placeholder="Ask about the text..."></textarea>'
      + '  <button type="button" id="llmSendBtn" class="llm-send-btn">Send</button>'
      + '</div>';
    document.body.appendChild(panel);

    var panelHeader = panel.querySelector('.llm-panel-header');
    var lastTokenEl = panel.querySelector('#llmCtxLastToken');
    var dragState = null;
    var fabDragState = null;
    var fabIgnoreClickUntil = 0;
    var syncingPanelLayout = false;
    var panelHasCustomPosition = false;

    function clampPanelPosition(left, top) {
      var width = panel.offsetWidth || PANEL_DEFAULT_WIDTH;
      var height = panel.offsetHeight || PANEL_DEFAULT_HEIGHT;
      var maxLeft = Math.max(PANEL_MARGIN, window.innerWidth - width - PANEL_MARGIN);
      var maxTop = Math.max(PANEL_MARGIN, window.innerHeight - height - PANEL_MARGIN);
      return {
        left: Math.min(Math.max(PANEL_MARGIN, left), maxLeft),
        top: Math.min(Math.max(PANEL_MARGIN, top), maxTop)
      };
    }

    function clampPanelSize(width, height) {
      var hasCustomPosition = !!(panel.style.left && panel.style.top);
      var maxWidth = Math.max(280, window.innerWidth - (PANEL_MARGIN * 2));
      var maxHeight = hasCustomPosition
        ? Math.max(220, window.innerHeight - (PANEL_MARGIN * 2))
        : Math.max(220, window.innerHeight - 100);
      var minWidth = Math.min(PANEL_MIN_WIDTH, maxWidth);
      var minHeight = Math.min(PANEL_MIN_HEIGHT, maxHeight);
      return {
        width: Math.min(Math.max(minWidth, width || PANEL_DEFAULT_WIDTH), maxWidth),
        height: Math.min(Math.max(minHeight, height || PANEL_DEFAULT_HEIGHT), maxHeight)
      };
    }

    function setPanelPosition(left, top, persist) {
      var clamped = clampPanelPosition(left, top);
      panel.style.left = clamped.left + 'px';
      panel.style.top = clamped.top + 'px';
      panel.style.right = 'auto';
      panel.style.bottom = 'auto';
      if (persist) {
        panelHasCustomPosition = true;
        savePanelState(clamped);
      }
      return clamped;
    }

    function setPanelSize(width, height) {
      var clamped = clampPanelSize(width, height);
      panel.style.width = clamped.width + 'px';
      panel.style.height = clamped.height + 'px';
      savePanelState(clamped);
      return clamped;
    }

    function clampFabPosition(left, top) {
      var width = btn.offsetWidth || 52;
      var height = btn.offsetHeight || 52;
      var maxLeft = Math.max(PANEL_MARGIN, window.innerWidth - width - PANEL_MARGIN);
      var maxTop = Math.max(PANEL_MARGIN, window.innerHeight - height - PANEL_MARGIN);
      return {
        left: Math.min(Math.max(PANEL_MARGIN, left), maxLeft),
        top: Math.min(Math.max(PANEL_MARGIN, top), maxTop)
      };
    }

    function setFabPosition(left, top) {
      var clamped = clampFabPosition(left, top);
      btn.style.left = clamped.left + 'px';
      btn.style.top = clamped.top + 'px';
      btn.style.right = 'auto';
      btn.style.bottom = 'auto';
      saveFabState(clamped);
    }

    function resetPanelPosition() {
      panelHasCustomPosition = false;
      panel.style.left = '';
      panel.style.top = '';
      panel.style.right = '';
      panel.style.bottom = '';
      panel.style.width = '';
      panel.style.height = '';
      clearPanelState();
    }

    function restoreSavedPanelPosition() {
      var saved = loadPanelState();
      if (saved.width || saved.height) {
        setPanelSize(saved.width, saved.height);
      }
      if (typeof saved.left === 'number' && typeof saved.top === 'number') {
        panelHasCustomPosition = true;
        setPanelPosition(saved.left, saved.top, true);
      } else {
        panelHasCustomPosition = false;
        positionPanelNextToFab();
      }
    }

    function clearPanelPlacementState() {
      panelHasCustomPosition = false;
      savePanelState({ left: null, top: null });
    }

    function positionPanelNextToFab() {
      var rect = btn.getBoundingClientRect();
      var width = panel.offsetWidth || PANEL_DEFAULT_WIDTH;
      var height = panel.offsetHeight || PANEL_DEFAULT_HEIGHT;
      var placeRight = (rect.left + (rect.width / 2)) < (window.innerWidth / 2);
      var placeBelow = (rect.top + (rect.height / 2)) < (window.innerHeight / 2);
      var left = placeRight ? (rect.right + PANEL_MARGIN) : (rect.left - width - PANEL_MARGIN);
      var top = placeBelow ? (rect.bottom + PANEL_MARGIN) : (rect.top - height - PANEL_MARGIN);
      panelHasCustomPosition = false;
      setPanelPosition(left, top, false);
    }

    function resetFabPosition() {
      btn.style.left = '';
      btn.style.top = '';
      btn.style.right = '';
      btn.style.bottom = '';
      clearFabState();
    }

    function restoreSavedFabPosition() {
      var saved = loadFabState();
      if (typeof saved.left === 'number' && typeof saved.top === 'number') {
        setFabPosition(saved.left, saved.top);
      }
    }

    function syncPanelLayoutFromDom() {
      if (syncingPanelLayout || panel.style.display === 'none') return;
      syncingPanelLayout = true;
      try {
        var rect = panel.getBoundingClientRect();
        var clampedSize = clampPanelSize(rect.width, rect.height);
        if (Math.abs(clampedSize.width - rect.width) > 1) {
          panel.style.width = clampedSize.width + 'px';
        }
        if (Math.abs(clampedSize.height - rect.height) > 1) {
          panel.style.height = clampedSize.height + 'px';
        }
        savePanelState(clampedSize);
        if (panelHasCustomPosition && panel.style.left && panel.style.top) {
          setPanelPosition(rect.left, rect.top, true);
        } else {
          positionPanelNextToFab();
        }
      } finally {
        syncingPanelLayout = false;
      }
    }

    function syncFabLayoutFromDom() {
      if (!(btn.style.left && btn.style.top)) return;
      var rect = btn.getBoundingClientRect();
      setFabPosition(rect.left, rect.top);
    }

    function onDragMove(ev) {
      if (!dragState) return;
      setPanelPosition(ev.clientX - dragState.offsetX, ev.clientY - dragState.offsetY, true);
    }

    function stopDrag() {
      if (!dragState) return;
      dragState = null;
      document.removeEventListener('mousemove', onDragMove);
      document.removeEventListener('mouseup', stopDrag);
    }

    function onFabDragMove(ev) {
      if (!fabDragState) return;
      var deltaX = ev.clientX - fabDragState.startX;
      var deltaY = ev.clientY - fabDragState.startY;
      if (!fabDragState.dragged && Math.abs(deltaX) < 4 && Math.abs(deltaY) < 4) return;
      fabDragState.dragged = true;
      setFabPosition(ev.clientX - fabDragState.offsetX, ev.clientY - fabDragState.offsetY);
      ev.preventDefault();
    }

    function stopFabDrag() {
      if (!fabDragState) return;
      if (fabDragState.dragged) {
        fabIgnoreClickUntil = Date.now() + 250;
        clearPanelPlacementState();
      }
      fabDragState = null;
      document.removeEventListener('mousemove', onFabDragMove);
      document.removeEventListener('mouseup', stopFabDrag);
    }

    panelHeader.addEventListener('mousedown', function (ev) {
      if (ev.button !== 0) return;
      if (ev.target && ev.target.closest && ev.target.closest('.llm-panel-close, .llm-panel-reset')) return;
      if (panel.style.display === 'none') return;
      var rect = panel.getBoundingClientRect();
      setPanelPosition(rect.left, rect.top, false);
      var updatedRect = panel.getBoundingClientRect();
      dragState = {
        offsetX: ev.clientX - updatedRect.left,
        offsetY: ev.clientY - updatedRect.top
      };
      document.addEventListener('mousemove', onDragMove);
      document.addEventListener('mouseup', stopDrag);
      ev.preventDefault();
    });

    btn.addEventListener('mousedown', function (ev) {
      if (ev.button !== 0) return;
      var rect = btn.getBoundingClientRect();
      fabDragState = {
        startX: ev.clientX,
        startY: ev.clientY,
        offsetX: ev.clientX - rect.left,
        offsetY: ev.clientY - rect.top,
        dragged: false
      };
      document.addEventListener('mousemove', onFabDragMove);
      document.addEventListener('mouseup', stopFabDrag);
      ev.preventDefault();
    });

    restoreSavedFabPosition();

    window.addEventListener('resize', function () {
      syncFabLayoutFromDom();
      if (panel.style.display === 'none') return;
      syncPanelLayoutFromDom();
    });

    if (typeof ResizeObserver !== 'undefined') {
      var resizeObserver = new ResizeObserver(function () {
        syncPanelLayoutFromDom();
      });
      resizeObserver.observe(panel);
    }

    // Wiring
    btn.addEventListener('click', function () {
      if (Date.now() < fabIgnoreClickUntil) return;
      panelOpen = !panelOpen;
      panel.style.display = panelOpen ? 'flex' : 'none';
      btn.classList.toggle('active', panelOpen);
      if (panelOpen) {
        restoreSavedPanelPosition();
        syncPanelLayoutFromDom();
        document.getElementById('llmInput').focus();
      }
    });

    panel.querySelector('.llm-panel-reset').addEventListener('click', function () {
      resetPanelPosition();
      resetFabPosition();
    });

    panel.querySelector('.llm-panel-close').addEventListener('click', function () {
      panelOpen = false;
      panel.style.display = 'none';
      btn.classList.remove('active');
    });

    var sendBtn = document.getElementById('llmSendBtn');
    var input = document.getElementById('llmInput');

    sendBtn.addEventListener('click', doSend);
    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' && !ev.shiftKey) {
        ev.preventDefault();
        doSend();
      }
    });

    // --- Inline context checkbox wiring ---
    var ctxState = loadContextCheckboxState();
    function applyCheckboxState() {
      ['token', 'sentence', 'reader'].forEach(function (which) {
        var cb = panel.querySelector('[data-ctx-cb="' + which + '"]');
        if (cb) cb.checked = !!ctxState[which];
      });
    }
    applyCheckboxState();

    panel.addEventListener('change', function (ev) {
      var t = ev.target;
      if (!t || !t.matches || !t.matches('[data-ctx-cb]')) return;
      var which = t.getAttribute('data-ctx-cb');
      if (which === 'token' || which === 'sentence' || which === 'reader') {
        ctxState[which] = !!t.checked;
        saveContextCheckboxState(ctxState);
      }
    });

    function updateLastTokenLabel() {
      if (!lastTokenEl) return;
      var s = String(activeContext.tokenSurface || '').trim();
      lastTokenEl.innerHTML = s ? ('Last Token Clicked: <b>' + escapeHtml(s) + '</b>') : '';
      lastTokenEl.title = s ? ('Last Token Clicked: ' + s) : '';
    }
    updateLastTokenLabel();

    // Public API. reader.js calls updateContext on every token click.
    window.LEAssistant = window.LEAssistant || {};
    window.LEAssistant.updateContext = function (payload) {
      payload = payload || {};
      function unpack(slot) {
        if (!slot) return '';
        if (typeof slot === 'string') return slot;
        return String(slot.text || '');
      }
      activeContext.tokenText = unpack(payload.token);
      activeContext.sentenceText = unpack(payload.sentence);
      activeContext.readerText = unpack(payload.reader);
      activeContext.tokenSurface = String(payload.tokenSurface
        || (payload.token && payload.token.data && payload.token.data.surface)
        || '');
      activeContext.segIdx = isFinite(Number(payload.segIdx)) ? Number(payload.segIdx) : -1;
      updateLastTokenLabel();
    };
    // Back-compat shim (panel no longer auto-opens).
    window.LEAssistant.openWithContext = window.LEAssistant.updateContext;
    window.LEAssistant.getCheckboxState = function () {
      return { token: !!ctxState.token, sentence: !!ctxState.sentence, reader: !!ctxState.reader };
    };
    window.LEAssistant.clearHistory = function () {
      saveExchanges([]);
      chatHistory = [];
      var container = document.getElementById('llmMessages');
      if (container) container.innerHTML = '';
    };
  }


  function doSend() {
    if (requestInFlight) return;
    var input = document.getElementById('llmInput');
    var query = (input.value || '').trim();
    if (!query) return;

    input.value = '';
    appendMessage('user', query);

    // Build the attached-context string from the 3 checkboxes.
    var state = (window.LEAssistant && typeof window.LEAssistant.getCheckboxState === 'function')
      ? window.LEAssistant.getCheckboxState()
      : { token: false, sentence: false, reader: false };
    var parts = [];
    if (state.token && activeContext.tokenText) {
      parts.push(truncateTextToApproxTokens(activeContext.tokenText, MAX_TOKEN_CONTEXT_TOKENS));
    }
    if (state.sentence && activeContext.sentenceText) {
      parts.push(truncateTextToApproxTokens(activeContext.sentenceText, MAX_SENTENCE_CONTEXT_TOKENS));
    }
    if (state.reader) {
      // Prefer the pushed reader text (from the last token click); fall back to
      // the current rendered text so the "reader" checkbox works even when the
      // user never clicked a token this session.
      var readerText = activeContext.readerText;
      if (!readerText) {
        if (window.LEReaderAssistantBridge && typeof window.LEReaderAssistantBridge.getReaderCtx === 'function') {
          try {
            var _rd = window.LEReaderAssistantBridge.getReaderCtx();
            if (_rd) {
              if (typeof window.LEReaderAssistantBridge.serializeReader === 'function') {
                readerText = String(window.LEReaderAssistantBridge.serializeReader(_rd) || '');
              } else {
                readerText = String(_rd.text || '');
              }
            }
          } catch (_e) {}
        }
        if (!readerText) readerText = getRenderedText();
      }
      if (readerText) parts.push(truncateTextToApproxTokens(readerText, MAX_READER_CONTEXT_TOKENS));
    }
    var context = parts.join('\n\n');
    var includeReaderContext = parts.length > 0;
    requestInFlight = true;

    var sendBtn = document.getElementById('llmSendBtn');
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.textContent = '...';
    }

    var exchangeCtx = getExchangeContext();

    fetch('/api/llm_query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        context: context,
        include_reader_context: includeReaderContext,
        history: exchangeCtx.history,
        last_exchange: exchangeCtx.last_exchange,
        query: query,
        lang: (document.getElementById('languageSelect') || {}).value || window.ReaderDefaultLanguage || ''
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        requestInFlight = false;
        if (sendBtn) {
          sendBtn.disabled = false;
          sendBtn.textContent = 'Send';
        }
        if (d.ok) {
          appendMessage('assistant', d.response);
          recordChatExchange(query, d.response);
        } else if (d.upgrade || d.upgrade_required) {
          appendMessage('system', 'This feature requires a paid subscription. <a href="/account">Upgrade</a>');
        } else {
          appendMessage('system', d.error || 'Request failed.');
        }
      })
      .catch(function (err) {
        requestInFlight = false;
        if (sendBtn) {
          sendBtn.disabled = false;
          sendBtn.textContent = 'Send';
        }
        appendMessage('system', 'Network error.');
      });
  }

  function renderMarkdown(raw) {
    if (typeof marked !== 'undefined' && marked.parse) {
      return marked.parse(String(raw || ''));
    }
    // Fallback if marked didn't load
    return '<p>' + escapeHtml(raw).replace(/\n/g, '<br>') + '</p>';
  }

  function appendMessage(role, text) {
    chatHistory.push({ role: role, text: text });
    var container = document.getElementById('llmMessages');
    if (!container) return;

    var div = document.createElement('div');
    div.className = 'llm-msg llm-msg-' + role;
    if (role === 'system') {
      div.innerHTML = text;
    } else if (role === 'assistant') {
      div.innerHTML = renderMarkdown(text);
    } else {
      div.textContent = text;
    }
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }

  // --- SENT_XLATE begin ----------------------------------------------------
  // Sentence-level fluent translation bubble. Self-contained: one body-level
  // <div> + one header toggle button. Remove this block and the toggle button
  // HTML to fully revert.
  (function initSentenceTranslation() {
    var SENT_XL_STORAGE = 'le_sentxl_enabled';
    var SENT_XL_SHOW_XL_KEY = 'le_sentxl_show_xl';
    var enabled = false;
    var showTranslation = true;
    try { enabled = localStorage.getItem(SENT_XL_STORAGE) === '1'; } catch (_e) {}
    try {
      var rawXl = localStorage.getItem(SENT_XL_SHOW_XL_KEY);
      if (rawXl !== null) showTranslation = rawXl === '1';
    } catch (_e) {}
    var toggleSentenceTranslations = document.getElementById('toggleSentenceTranslations');

    function syncSentenceSettingsControls() {
      if (toggleSentenceTranslations) toggleSentenceTranslations.checked = !!showTranslation;
    }

    function bindSentenceSettingsControls() {
      syncSentenceSettingsControls();
      if (toggleSentenceTranslations) {
        toggleSentenceTranslations.addEventListener('change', function () {
          showTranslation = this.checked;
          try { localStorage.setItem(SENT_XL_SHOW_XL_KEY, showTranslation ? '1' : '0'); } catch (_e) {}
          renderSentenceTabletBubble();
          if (showTranslation) maybeAutoTranslateCurrentSentence();
        });
      }
    }

    // Fluent sentence translation cache.
    // Key = lang + '\u0001' + JSON.stringify(sentence.tokens) (exact token stream, no normalization).
    // Stored in sessionStorage.
    var SENT_XL_CACHE_KEY = 'le_sentxl_cache_v2';
    var cache = (function loadCache() {
      try {
        var raw = sessionStorage.getItem(SENT_XL_CACHE_KEY);
        if (raw) {
          var parsed = JSON.parse(raw);
          if (parsed && typeof parsed === 'object') return parsed;
        }
      } catch (_e) {}
      return Object.create(null);
    })();
    var cacheDirty = false;
    var requestErrors = Object.create(null);
    function persistCache() {
      if (!cacheDirty) return;
      cacheDirty = false;
      try { sessionStorage.setItem(SENT_XL_CACHE_KEY, JSON.stringify(cache)); }
      catch (_e) {
        try {
          var keys = Object.keys(cache);
          var drop = Math.max(1, Math.floor(keys.length * 0.2));
          for (var i = 0; i < drop; i++) delete cache[keys[i]];
          sessionStorage.setItem(SENT_XL_CACHE_KEY, JSON.stringify(cache));
        } catch (_e2) {}
      }
    }
    function sentCacheKey(lang, tokens) {
      try { return (lang || '') + '\u0001' + JSON.stringify(tokens); }
      catch (_e) { return null; }
    }
    var inFlight = Object.create(null); // sentence text -> true while pending
    var sentenceIndex = [];            // [{start, end, text}, ...] from last /lookup
    var currentLang = '';
    var currentSentenceText = '';
    var currentSentenceTokens = null;
    var bubble = null;
    var currentSentenceData = null;
    var currentSelectedSegIdx = -1;
    var sentenceTabletReflowRaf = null;

    function getSentenceBridge() {
      var bridge = window.LEReaderAssistantBridge;
      if (!bridge || typeof bridge.getSentenceTabletDataForSeg !== 'function') return null;
      return bridge;
    }
    function buildSentenceTextFromData(sentenceData) {
      if (!sentenceData || typeof sentenceData !== 'object') return '';
      if (sentenceData.sentenceText) return String(sentenceData.sentenceText || '');
      var tokens = Array.isArray(sentenceData.tokens) ? sentenceData.tokens : [];
      var parts = [];
      for (var i = 0; i < tokens.length; i++) {
        var tok = tokens[i] || {};
        var text = String(tok.token || '').trim();
        if (text) parts.push(text);
      }
      return parts.join(' ').replace(/\s+([,.;:!?\u3002\uff0c\u3001\uff1b\uff1a\uff01\uff1f])/g, '$1').trim();
    }
    function sentenceTabletCacheKey(sentenceData) {
      if (!sentenceData || !Array.isArray(sentenceData.tokens)) return null;
      try {
        return (sentenceData.lang || '')
          + '\u0001' + JSON.stringify(sentenceData.tokens.map(function (tok) { return String((tok && tok.token) || ''); }));
      } catch (_e) {
        return null;
      }
    }
    function loadSentenceDataForSeg(segIdx) {
      var bridge = getSentenceBridge();
      if (!bridge) return null;
      try {
        var data = bridge.getSentenceTabletDataForSeg(segIdx);
        if (data && data.ok) {
          currentSentenceData = data;
          currentSelectedSegIdx = Number(segIdx);
          currentLang = String(data.lang || currentLang || '');
          currentSentenceText = buildSentenceTextFromData(data);
          currentSentenceTokens = data.tokens.map(function (tok) { return String((tok && tok.token) || ''); });
          return data;
        }
      } catch (_e) {}
      return null;
    }
    function updateLocalSentenceTranslation(value) {
      if (!currentSentenceData) return;
      var cacheKey = sentenceTabletCacheKey(currentSentenceData);
      if (!cacheKey) return;
      var normalized = String(value || '').replace(/\u00a0/g, ' ').trim();
      if (normalized) cache[cacheKey] = normalized;
      else delete cache[cacheKey];
      cacheDirty = true;
      persistCache();
      delete requestErrors[cacheKey];
    }
    function scheduleSentenceTabletReflow(fullRerender) {
      if (sentenceTabletReflowRaf) window.cancelAnimationFrame(sentenceTabletReflowRaf);
      sentenceTabletReflowRaf = window.requestAnimationFrame(function () {
        sentenceTabletReflowRaf = null;
        if (fullRerender) {
          renderSentenceTabletBubble();
          return;
        }
        positionBubble();
      });
    }
    function getAllSentenceSpans() {
      var bridge = getSentenceBridge();
      if (!bridge || typeof bridge.getAllSentenceTabletData !== 'function') return [];
      try { return bridge.getAllSentenceTabletData() || []; } catch (_e) { return []; }
    }

    function maybeAutoTranslateCurrentSentence() {
      if (!showTranslation || !currentSentenceData) return;
      var cacheKey = sentenceTabletCacheKey(currentSentenceData);
      if (!cacheKey || inFlight[cacheKey] || cache[cacheKey]) return;
      requestTranslationForCurrentSentence();
    }

    function injectSentenceTabletStyles() {
      if (document.getElementById('le-sentxl-styles')) return;
      var css = [
        '.llm-xlate-card { display:flex; flex-direction:column; gap:8px; max-width:680px; }',
        '.llm-xlate-result-edit { display:inline-block; max-width:100%; min-height:14px; color:#f8fafc; white-space:normal; overflow-wrap:break-word; word-break:normal; line-height:1.4; outline:none; cursor:text; }',
        '.llm-xlate-result-edit:focus { text-decoration:underline; text-decoration-color:rgba(96,165,250,0.86); text-underline-offset:3px; }',
        '.llm-xlate-result-error { color:rgba(248,250,252,0.78); white-space:pre-wrap; word-break:break-word; line-height:1.4; }',
        '@media (max-width: 640px) { .llm-xlate-card { max-width:none; } }'
      ].join('\n');
      var style = document.createElement('style');
      style.id = 'le-sentxl-styles';
      style.textContent = css;
      document.head.appendChild(style);
    }
    function ensureBubble() {
      if (bubble && bubble.parentNode) return bubble;
      injectSentenceTabletStyles();
      bubble = document.createElement('div');
      bubble.id = 'llm-xlate-bubble';
      bubble.style.cssText = [
        'position:fixed',
        'z-index:9998',
        'display:none',
        'width:auto',
        'max-width:calc(100vw - 20px)',
        'overflow:visible',
        'padding:10px 11px',
        'background:rgba(30,41,59,0.82)',
        'color:#f8fafc',
        'border-radius:12px',
        'font-size:12px',
        'line-height:1.45',
        'font-family:Inter,system-ui,sans-serif',
        'box-shadow:0 10px 28px rgba(0,0,0,0.22)',
        'pointer-events:auto',
        'backdrop-filter:blur(4px)',
        '-webkit-backdrop-filter:blur(4px)'
      ].join(';');
      document.body.appendChild(bubble);
      return bubble;
    }

    function removeBubble() {
      if (bubble && bubble.parentNode) bubble.parentNode.removeChild(bubble);
      bubble = null;
    }

    // Standalone draggable FAB for this feature
    var XFAB_STATE_KEY = 'le_sentxl_fab_state';
    var XFAB_MARGIN = 4;
    var XFAB_SIZE = 40;
    var xfab = null;
    function loadXfabState() {
      try {
        var raw = localStorage.getItem(XFAB_STATE_KEY);
        if (!raw) return null;
        var p = JSON.parse(raw);
        if (p && isFinite(p.left) && isFinite(p.top)) return p;
      } catch (_e) {}
      return null;
    }
    function saveXfabState(left, top) {
      try { localStorage.setItem(XFAB_STATE_KEY, JSON.stringify({ left: left, top: top })); } catch (_e) {}
    }
    function clampXfabPosition(left, top) {
      var maxLeft = Math.max(XFAB_MARGIN, window.innerWidth - XFAB_SIZE - XFAB_MARGIN);
      var maxTop = Math.max(XFAB_MARGIN, window.innerHeight - XFAB_SIZE - XFAB_MARGIN);
      return {
        left: Math.min(Math.max(XFAB_MARGIN, left), maxLeft),
        top: Math.min(Math.max(XFAB_MARGIN, top), maxTop)
      };
    }
    function setXfabPosition(left, top, persist) {
      var clamped = clampXfabPosition(left, top);
      xfab.style.left = clamped.left + 'px';
      xfab.style.top = clamped.top + 'px';
      xfab.style.right = '';
      xfab.style.bottom = '';
      if (persist) saveXfabState(clamped.left, clamped.top);
      return clamped;
    }
    function syncXfabLayoutFromDom() {
      if (!xfab || !(xfab.style.left && xfab.style.top)) return;
      var rect = xfab.getBoundingClientRect();
      setXfabPosition(rect.left, rect.top, true);
    }
    function ensureXfab() {
      if (xfab && xfab.parentNode) return xfab;
      xfab = document.createElement('button');
      xfab.id = 'llm-xlate-fab';
      xfab.type = 'button';
      xfab.setAttribute('data-native-tooltip', '');
      xfab.title = 'Translation tablet';
      // Rosetta Stone glyph: rounded tablet with three script bands
      xfab.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M7 3 Q6 3 6 4 L5 20 Q5 21 6 21 L18 21 Q19 21 19 20 L18 4 Q18 3 17 3 Z"/>'
        + '<line x1="7" y1="9" x2="17" y2="9"/>'
        + '<line x1="7" y1="14" x2="17" y2="14"/>'
        + '<circle cx="8.5" cy="6" r="0.6" fill="currentColor"/>'
        + '<path d="M10.5 6 l1 -1 l1 1 l1 -1" />'
        + '<path d="M14.5 6 l1 1"/>'
        + '<path d="M8 11.5 h2 m1 0 h1.5 m1 0 h2"/>'
        + '<path d="M8 16.5 h1 m1.2 0 h1.2 m1.2 0 h1.2 m1.2 0 h1"/>'
        + '</svg>';
      xfab.style.cssText = [
        'position:fixed',
        'z-index:9997',
        'width:40px',
        'height:40px',
        'border-radius:50%',
        'border:none',
        'cursor:pointer',
        'font-size:13px',
        'font-weight:600',
        'font-family:Inter,system-ui,sans-serif',
        'box-shadow:0 3px 10px rgba(0,0,0,0.22)',
        'user-select:none',
        'display:flex',
        'align-items:center',
        'justify-content:center'
      ].join(';');
      var saved = loadXfabState();
      if (saved) {
        setXfabPosition(saved.left, saved.top, true);
      } else {
        xfab.style.right = '24px';
        xfab.style.bottom = '84px';
      }
      document.body.appendChild(xfab);
      wireXfabDrag();
      return xfab;
    }
    function updateXfabVisual() {
      if (!xfab) return;
      xfab.style.background = '#2563eb';
      xfab.style.color = '#fff';
      xfab.style.opacity = enabled ? '1' : '0.55';
    }
    function wireXfabDrag() {
      var dragging = false, moved = false, offX = 0, offY = 0;
      xfab.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return;
        var rect = xfab.getBoundingClientRect();
        offX = e.clientX - rect.left;
        offY = e.clientY - rect.top;
        dragging = true; moved = false;
        e.preventDefault();
      });
      document.addEventListener('mousemove', function (e) {
        if (!dragging) return;
        var left = e.clientX - offX;
        var top = e.clientY - offY;
        setXfabPosition(left, top, false);
        if (Math.abs(e.movementX) + Math.abs(e.movementY) > 0) moved = true;
        positionBubble();
      });
      document.addEventListener('mouseup', function (e) {
        if (!dragging) return;
        dragging = false;
        if (moved) {
          var r = xfab.getBoundingClientRect();
          saveXfabState(r.left, r.top);
        } else {
          setEnabled(!enabled);
        }
      });
    }

    function getAnchorRect() {
      if (xfab) return xfab.getBoundingClientRect();
      return null;
    }
    function positionBubble() {
      if (!bubble) return;
      var rect = getAnchorRect();
      if (!rect) return;
      var bw = bubble.offsetWidth || 360;
      var bh = bubble.offsetHeight || 180;
      var margin = 10;
      var placeLeft = (rect.left + rect.width / 2) > (window.innerWidth / 2);
      var placeAbove = (rect.top + rect.height / 2) > (window.innerHeight / 2);
      var left = placeLeft ? (rect.left - bw - margin) : (rect.right + margin);
      var top = placeAbove ? (rect.bottom - bh) : rect.top;
      left = Math.max(8, Math.min(left, window.innerWidth - bw - 8));
      top = Math.max(8, Math.min(top, window.innerHeight - bh - 8));
      bubble.style.left = left + 'px';
      bubble.style.top = top + 'px';
    }

    function renderSentenceTabletBubble() {
      ensureBubble();
      if (!enabled) {
        bubble.style.display = 'none';
        return;
      }

      bubble.style.width = 'auto';

      var lowerHtml = '';
      if (currentSentenceData && currentSentenceData.ok && Array.isArray(currentSentenceData.tokens) && currentSentenceData.tokens.length && showTranslation) {
        var cacheKey = sentenceTabletCacheKey(currentSentenceData);
        var translation = cacheKey ? String(cache[cacheKey] || '') : '';
        var requestError = cacheKey ? String(requestErrors[cacheKey] || '') : '';
        var resultHtml = translation
          ? '<div class="llm-xlate-result-edit" contenteditable="false" spellcheck="false" data-sentxl-translation-input="1">' + escapeHtml(translation) + '</div>'
          : (requestError ? '<div class="llm-xlate-result-error">' + escapeHtml(requestError) + '</div>' : '');
        if (resultHtml) {
          lowerHtml += resultHtml;
        }
      }

      if (!lowerHtml) {
        bubble.innerHTML = '';
        bubble.style.display = 'none';
        return;
      }

      bubble.innerHTML = ''
        + '<div class="llm-xlate-card">'
        +   lowerHtml
        + '</div>';
      bubble.style.display = 'block';
      positionBubble();
    }
    function requestTranslationForCurrentSentence() {
      if (!currentSentenceData) return;
      if (!showTranslation) return;
      var curKey = sentenceTabletCacheKey(currentSentenceData);
      if (!curKey) return;
      // Skip if already cached or in flight.
      if (cache[curKey] || inFlight[curKey]) {
        renderSentenceTabletBubble();
        return;
      }

      // Batch every sentence in the current lookup into one Gemini call so
      // the model has full discourse context. Each sentence still lands in
      // its own cache slot keyed by token list — so future hovers are hits.
      var bridge = getSentenceBridge();
      var allData = [];
      if (bridge && typeof bridge.getAllSentenceTabletData === 'function') {
        try { allData = bridge.getAllSentenceTabletData() || []; } catch (_e) { allData = []; }
      }
      // Fallback: if bridge method absent, just translate the current one.
      if (!allData.length) allData = [currentSentenceData];

      // Only include sentences that have no cached translation and aren't
      // already in flight. Mark in-flight up front so concurrent hovers
      // don't double-send.
      var pending = [];
      var pendingKeys = [];
      for (var i = 0; i < allData.length; i++) {
        var d = allData[i];
        var k = sentenceTabletCacheKey(d);
        if (!k) continue;
        if (cache[k] || inFlight[k]) continue;
        inFlight[k] = true;
        pending.push(d);
        pendingKeys.push(k);
      }
      if (!pending.length) {
        renderSentenceTabletBubble();
        return;
      }
      requestErrors[curKey] = '';
      renderSentenceTabletBubble();

      var requests = pending.map(function (d) {
        var tokens = Array.isArray(d.tokens) ? d.tokens.map(function (t) { return String((t && t.token) || ''); }) : [];
        return {
          tokens: tokens
        };
      });

      fetch('/api/llm_translate_sentences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lang: (currentSentenceData && currentSentenceData.lang) || '',
          requests: requests
        })
      }).then(function (r) { return r.json(); }).then(function (d) {
        for (var pi = 0; pi < pendingKeys.length; pi++) delete inFlight[pendingKeys[pi]];
        if (d && d.ok && Array.isArray(d.translations)) {
          for (var ti = 0; ti < pendingKeys.length && ti < d.translations.length; ti++) {
            cache[pendingKeys[ti]] = String(d.translations[ti] || '');
            requestErrors[pendingKeys[ti]] = '';
          }
          cacheDirty = true;
          persistCache();
        } else if (d && (d.upgrade || d.upgrade_required || d.error === 'upgrade_required')) {
          for (var ei = 0; ei < pendingKeys.length; ei++) requestErrors[pendingKeys[ei]] = 'Translation tablet requires a paid subscription.';
        } else {
          var msg = String((d && d.error) || 'Translation failed.');
          for (var ej = 0; ej < pendingKeys.length; ej++) requestErrors[pendingKeys[ej]] = msg;
        }
        renderSentenceTabletBubble();
      }).catch(function () {
        for (var ci = 0; ci < pendingKeys.length; ci++) {
          delete inFlight[pendingKeys[ci]];
          requestErrors[pendingKeys[ci]] = 'Network error.';
        }
        renderSentenceTabletBubble();
      });
    }

    function setEnabled(on) {
      enabled = !!on;
      try { localStorage.setItem(SENT_XL_STORAGE, enabled ? '1' : '0'); } catch (_e) {}
      updateXfabVisual();
      if (!enabled) {
        if (bubble) bubble.style.display = 'none';
      } else {
        if (!currentSentenceData) {
          try {
            var all = getAllSentenceSpans();
            if (all.length) loadSentenceDataForSeg(all[0].segStart);
          } catch (_e) {}
        }
        renderSentenceTabletBubble();
      }
    }

    function buildSentenceIndexFromLookup(payload) {
      try {
        var ud = payload && payload.ud_overlay;
        if (!ud) return;
        var sents = ud.sentences;
        var udTokens = ud.tokens || [];
        var doc2seg = ud.doc2seg || [];
        if (!Array.isArray(sents) || !sents.length) return;
        var built = [];
        for (var i = 0; i < sents.length; i++) {
          var rng = sents[i];
          if (!Array.isArray(rng) || rng.length < 2) continue;
          var docStart = rng[0] | 0, docEnd = rng[1] | 0;
          var pieces = [];
          var segIdxs = [];
          for (var j = docStart; j < docEnd && j < udTokens.length; j++) {
            var tok = udTokens[j] || {};
            var t = String(tok.text || '');
            if (t) pieces.push(t);
            var seg = (j < doc2seg.length) ? (doc2seg[j] | 0) : -1;
            if (seg >= 0) segIdxs.push(seg);
          }
          var text = pieces.join(' ').replace(/\s+([,.;:!?。，、；：！？])/g, '$1').trim();
          if (!text) continue;
          var segStart = segIdxs.length ? Math.min.apply(null, segIdxs) : -1;
          var segEnd = segIdxs.length ? (Math.max.apply(null, segIdxs) + 1) : -1;
          built.push({ segStart: segStart, segEnd: segEnd, text: text, tokens: pieces.slice() });
        }
        sentenceIndex = built;
        try { console.log('[sentxl] built', built.length, 'sentences'); } catch (_e) {}
      } catch (_e) {}
    }

    function requestTranslations(lang) {
      maybeAutoTranslateCurrentSentence();
    }

    function findSentenceForTokenIndex(idx) {
      for (var i = 0; i < sentenceIndex.length; i++) {
        var s = sentenceIndex[i];
        if (s.segStart >= 0 && idx >= s.segStart && idx < s.segEnd) return s;
      }
      return null;
    }

    function onTokenClick(ev) {
      if (!enabled) return;
      // Click-to-switch is disabled — sentence selection is driven either by
      // the prev/next arrows or hover.
      void ev;
      return;
    }
    function onTokenHover(ev) {
      var tok = ev.target && ev.target.closest && ev.target.closest('.reader-token');
      if (!tok) return;
      if (tok.classList && tok.classList.contains('reader-punct')) return;
      var raw = tok.dataset && tok.dataset.index;
      var idx = raw == null ? NaN : parseInt(raw, 10);
      if (!isFinite(idx)) return;
      // Skip if the token is already in the current sentence.
      if (currentSentenceData && isFinite(currentSentenceData.segStart) && isFinite(currentSentenceData.segEnd)
          && idx >= currentSentenceData.segStart && idx < currentSentenceData.segEnd) return;
      var next = loadSentenceDataForSeg(idx);
      if (!next) return;
      renderSentenceTabletBubble();
      maybeAutoTranslateCurrentSentence();
    }

    // Intercept /lookup responses by wrapping fetch (layered over any earlier wrap)
    var origFetch = window.fetch;
    window.fetch = function (input, init) {
      var p = origFetch.apply(this, arguments);
      try {
        var url = typeof input === 'string' ? input : (input && input.url) || '';
        if (url && url.indexOf('/lookup') !== -1 && url.indexOf('/api/') === -1) {
          // Extract lang from query string
          try {
            var m = url.match(/[?&]lang=([^&]+)/);
            if (m) currentLang = decodeURIComponent(m[1]);
          } catch (_e) {}
          p.then(function (resp) {
            if (!resp || !resp.clone) return;
            resp.clone().json().then(function (data) {
              buildSentenceIndexFromLookup(data);
              // Always snap back to the first sentence of the new lookup.
              setTimeout(function () {
                try {
                  var all = getAllSentenceSpans();
                  if (all.length) {
                    var first = loadSentenceDataForSeg(all[0].segStart);
                    if (first) renderSentenceTabletBubble();
                  }
                } catch (_e) {}
                requestTranslations(currentLang);
              }, 0);
            }).catch(function () {});
          }).catch(function () {});
        }
      } catch (_e) {}
      return p;
    };

    // Click delegation on the rendered text area
    function wireSentenceTabletClicks() {
      var root = document.getElementById('renderedText');
      if (!root) { setTimeout(wireSentenceTabletClicks, 500); return; }
      root.addEventListener('click', onTokenClick, true);
      root.addEventListener('mouseover', onTokenHover, true);
    }
    wireSentenceTabletClicks();

    window.addEventListener('resize', function () {
      syncXfabLayoutFromDom();
      if (!enabled) return;
      renderSentenceTabletBubble();
    });

    ensureXfab();
    ensureBubble();
    bindSentenceSettingsControls();
    updateXfabVisual();
    renderSentenceTabletBubble();
  })();
  // --- SENT_XLATE end ------------------------------------------------------
})();
