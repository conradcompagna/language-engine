(function() {
  'use strict';

  var hostEl = document.getElementById('legacyDepTreeHost');
  var treeInitialized = false;

  function ensureTreeReady() {
    if (treeInitialized) return !!window.DepTreeView;
    if (!hostEl || !window.DepTreeView || typeof window.DepTreeView.init !== 'function') {
      return false;
    }
    window.DepTreeView.init({
      container: hostEl,
      chunkHighlight: false,
      dictPopup: false,
      linearClauseSplit: false
    });
    if (typeof window.DepTreeView.setVisible === 'function') {
      window.DepTreeView.setVisible(true);
    }
    treeInitialized = true;
    return true;
  }

  function renderEmpty(message) {
    if (!ensureTreeReady()) return;
    document.title = 'Legacy Dep Tree Tool';
    if (typeof window.DepTreeView._renderEmpty === 'function') {
      window.DepTreeView._renderEmpty(message);
    } else {
      window.DepTreeView.setData(null);
    }
  }

  function buildLegacyTreeData(payload) {
    var srcTokens = (payload && Array.isArray(payload.tokens)) ? payload.tokens : [];
    if (!srcTokens.length) return null;

    var globalToLocal = {};
    var segments = [];
    var tokens = [];
    var edges = [];
    var roots = [];
    var doc2seg = [];
    var seg2doc = [];

    for (var i = 0; i < srcTokens.length; i++) {
      var src = srcTokens[i] || {};
      globalToLocal[src.segIdx] = i;
      segments.push(String(src.text || ''));
      doc2seg.push(i);
      seg2doc.push(i);
    }

    for (var ti = 0; ti < srcTokens.length; ti++) {
      var token = srcTokens[ti] || {};
      var localHead = -1;
      if (token.headSegIdx != null && Object.prototype.hasOwnProperty.call(globalToLocal, token.headSegIdx)) {
        localHead = globalToLocal[token.headSegIdx];
      }
      if (localHead === ti) localHead = -1;

      tokens.push({
        i: ti,
        doc_i: ti,
        text: String(token.text || ''),
        upos: String(token.upos || ''),
        head: localHead,
        dep: String(token.dep || ''),
        gloss: String(token.gloss || '')
      });

      if (localHead >= 0) {
        edges.push({
          from: localHead,
          to: ti,
          dep: String(token.dep || ''),
          upos: String(token.upos || '')
        });
      } else {
        roots.push(ti);
      }
    }

    return {
      segments: segments,
      udOverlay: {
        ok: true,
        tokens: tokens,
        edges: edges,
        roots: roots,
        ents: [],
        doc2seg: doc2seg,
        seg2doc: seg2doc,
        sentences: [[0, segments.length]]
      },
      originalText: segments.join(' ')
    };
  }

  function renderPayload(payload) {
    if (!payload || !payload.ok || !Array.isArray(payload.tokens) || !payload.tokens.length) {
      renderEmpty((payload && payload.message) || 'Hover a token in the reader to inspect its sentence. Press R to refresh.');
      return;
    }
    if (!ensureTreeReady()) {
      return;
    }

    var data = buildLegacyTreeData(payload);
    if (!data) {
      renderEmpty('No dependency data was available for this sentence.');
      return;
    }

    document.title =
      'Legacy Dep Tree Tool - sentence '
      + String((payload.sentenceIndex || 0) + 1)
      + ' of '
      + String(payload.sentenceCount || 1);

    window.DepTreeView.setData(data);
    if (typeof window.DepTreeView.refitView === 'function') {
      window.DepTreeView.refitView();
    }
  }

  function requestRefresh() {
    if (!window.opener || window.opener.closed) {
      renderEmpty('Open this tool from the reader, then hover a token to send its sentence here.');
      return;
    }
    try {
      window.opener.postMessage({ type: 'le:dep-tree-experiment-request-refresh' }, window.location.origin);
    } catch (_e) {}
  }

  window.addEventListener('message', function(event) {
    if (event.origin !== window.location.origin) return;
    var data = event.data || {};
    if (!data || typeof data !== 'object') return;
    if (data.type === 'le:dep-tree-experiment-payload') {
      renderPayload(data.payload || null);
    }
  });

  window.addEventListener('keydown', function(event) {
    if ((event.key || '').toLowerCase() === 'r') {
      requestRefresh();
    }
  });

  window.requestLegacyDepTreeRefresh = requestRefresh;

  ensureTreeReady();
  renderEmpty('Hover a token in the reader to inspect its sentence. Press R to refresh.');

  if (window.opener && !window.opener.closed) {
    try {
      window.opener.postMessage({ type: 'le:dep-tree-experiment-ready' }, window.location.origin);
    } catch (_e) {}
  }
})();
