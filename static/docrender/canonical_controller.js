/* canonical_controller.js
 *
 * Orchestrates the new bottom-pane canonical document flow:
 *   CanonicalDocument -> page.text -> /lookup -> page.tokens -> CanonicalRenderer.
 *
 * The host reader supplies bridge callbacks for private reader.js functions
 * such as buildLookupUrl(), startSegmentLookupFetch(), attachHoverHandlers(),
 * registerTokenSpan(), etc. This keeps most new logic outside reader.js while
 * still letting the existing popup/UD/grammar UI attach to canonical tokens.
 *
 * Browser global:
 *   window.CanonicalReaderController
 */
(function(global) {
  'use strict';

  function requireDeps() {
    if (!global.CanonicalModel || !global.CanonicalAnnotator || !global.CanonicalRenderer) {
      throw new Error('CanonicalModel, CanonicalAnnotator, and CanonicalRenderer must be loaded before CanonicalReaderController');
    }
  }

  function noop() {}
  function str(v) { return v == null ? '' : String(v); }
  function num(v, fallback) { var n = Number(v); return isFinite(n) ? n : (fallback || 0); }
  function cloneJson(v) {
    if (v == null) return v;
    try { return JSON.parse(JSON.stringify(v)); } catch (_e) { return v; }
  }

  function shiftNumber(value, offset) {
    var n = Number(value);
    return isFinite(n) ? n + offset : value;
  }

  function shiftIndexFields(obj, fields, offset) {
    if (!obj || typeof obj !== 'object') return obj;
    fields.forEach(function(field) {
      if (typeof obj[field] === 'number' && isFinite(obj[field])) obj[field] += offset;
    });
    return obj;
  }

  function shiftUdToken(raw, offset) {
    var tok = cloneJson(raw || {});
    shiftIndexFields(tok, ['i', 'doc_i', 'head'], offset);
    if (Array.isArray(tok.heads)) tok.heads = tok.heads.map(function(v) { return shiftNumber(v, offset); });
    if (Array.isArray(tok.seg_span)) tok.seg_span = tok.seg_span.map(function(v) { return shiftNumber(v, offset); });
    return tok;
  }

  function shiftUdEdge(raw, offset) {
    var edge = cloneJson(raw || {});
    shiftIndexFields(edge, ['from', 'to'], offset);
    return edge;
  }

  function shiftUdEntity(raw, offset) {
    var ent = cloneJson(raw || {});
    shiftIndexFields(ent, ['start', 'end'], offset);
    return ent;
  }

  function shiftSentenceSpan(raw, offset) {
    if (!Array.isArray(raw) || raw.length < 2) return raw;
    return [shiftNumber(raw[0], offset), shiftNumber(raw[1], offset)];
  }

  function shiftGrammarToken(raw, offset) {
    var tok = cloneJson(raw || {});
    shiftIndexFields(tok, ['i', 'index', 'doc_i', 'head', 'head_index', 'seg_idx', 'segIndex'], offset);
    if (Array.isArray(tok.heads)) tok.heads = tok.heads.map(function(v) { return shiftNumber(v, offset); });
    return tok;
  }

  function mappedChunkOffset(chunk, pos, preferEnd) {
    var map = Array.isArray(chunk && chunk.offsetMap) ? chunk.offsetMap : null;
    var p = Math.max(0, Math.floor(num(pos, 0)));
    if (!map || !map.length) return num(chunk && chunk.start, 0) + p;
    if (preferEnd) {
      for (var i = Math.min(map.length - 1, p - 1); i >= 0; i--) {
        if (typeof map[i] === 'number' && isFinite(map[i])) return map[i] + 1;
      }
      return mappedChunkOffset(chunk, p, false);
    }
    for (var j = Math.min(map.length - 1, p); j < map.length; j++) {
      if (typeof map[j] === 'number' && isFinite(map[j])) return map[j];
    }
    return num(chunk && chunk.start, 0) + p;
  }

  function mapSegmentOffset(chunk, rawOffset, fallbackStart, fallbackText, pageTextLength) {
    var start = fallbackStart;
    var end = fallbackStart + str(fallbackText).length;
    if (rawOffset && typeof rawOffset === 'object') {
      start = num(rawOffset.start != null ? rawOffset.start : rawOffset[0], start);
      end = num(rawOffset.end != null ? rawOffset.end : rawOffset[1], end);
    }
    start = Math.max(0, start);
    end = Math.max(start, end);
    var mappedStart = mappedChunkOffset(chunk, start, false);
    var mappedEnd = mappedChunkOffset(chunk, end, true);
    var limit = Math.max(0, num(pageTextLength, 0));
    mappedStart = Math.max(0, Math.min(limit, mappedStart));
    mappedEnd = Math.max(mappedStart, Math.min(limit, mappedEnd));
    return [mappedStart, mappedEnd];
  }

  function shiftResultOffsets(raw, mappedOffset) {
    var result = cloneJson(raw || null);
    if (result && typeof result === 'object' && Array.isArray(mappedOffset)) {
      result.start = mappedOffset[0];
      result.end = mappedOffset[1];
    }
    return result;
  }

  function mergeChunkLookupPayloads(page, chunks, payloads) {
    var merged = {
      ok: true,
      display_text: str(page && page.text),
      q: str(page && page.text),
      debug_capture_id: '',
      segments: [],
      segment_offsets: [],
      ud_overlay: {
        ok: true,
        tokens: [],
        edges: [],
        roots: [],
        ents: [],
        sentences: [],
        doc2seg: [],
        seg2doc: [],
        error: null
      },
      grammar_overlay: { tokens: [], links: [] },
      results_by_seg: [],
      entry_store: {},
      ref_to_key: {},
      form_overlays: {},
      results: []
    };
    var segmentBase = 0;
    var pageTextLength = str(page && page.text).length;

    for (var ci = 0; ci < payloads.length; ci++) {
      var payload = payloads[ci] || {};
      var chunk = chunks[ci] || {};
      var segments = Array.isArray(payload.segments) ? payload.segments : [];
      var offsets = Array.isArray(payload.segment_offsets) ? payload.segment_offsets : [];
      var results = Array.isArray(payload.results_by_seg) ? payload.results_by_seg : [];
      for (var si = 0; si < segments.length; si++) {
        var segText = str(segments[si]);
        var mapped = mapSegmentOffset(chunk, offsets[si], 0, segText, pageTextLength);
        merged.segments.push(segText);
        merged.segment_offsets.push(mapped);
        merged.results_by_seg.push(shiftResultOffsets(results[si], mapped));
      }

      var ud = payload.ud_overlay || {};
      if (Array.isArray(ud.tokens)) {
        ud.tokens.forEach(function(tok) { merged.ud_overlay.tokens.push(shiftUdToken(tok, segmentBase)); });
      }
      if (Array.isArray(ud.edges)) {
        ud.edges.forEach(function(edge) { merged.ud_overlay.edges.push(shiftUdEdge(edge, segmentBase)); });
      }
      if (Array.isArray(ud.roots)) {
        ud.roots.forEach(function(root) { merged.ud_overlay.roots.push(shiftNumber(root, segmentBase)); });
      }
      if (Array.isArray(ud.ents)) {
        ud.ents.forEach(function(ent) { merged.ud_overlay.ents.push(shiftUdEntity(ent, segmentBase)); });
      }
      if (Array.isArray(ud.sentences)) {
        ud.sentences.forEach(function(span) { merged.ud_overlay.sentences.push(shiftSentenceSpan(span, segmentBase)); });
      }

      var grammar = payload.grammar_overlay || {};
      if (Array.isArray(grammar.tokens)) {
        grammar.tokens.forEach(function(tok) { merged.grammar_overlay.tokens.push(shiftGrammarToken(tok, segmentBase)); });
      }
      if (Array.isArray(grammar.links)) {
        grammar.links.forEach(function(link) { merged.grammar_overlay.links.push(cloneJson(link)); });
      }

      Object.assign(merged.entry_store, payload.entry_store || {});
      Object.assign(merged.ref_to_key, payload.ref_to_key || {});
      Object.assign(merged.form_overlays, payload.form_overlays || {});
      if (!merged.debug_capture_id && payload.debug_capture_id) merged.debug_capture_id = str(payload.debug_capture_id);
      if (!merged.language && payload.language) merged.language = payload.language;
      segmentBase += segments.length;
    }

    for (var i = 0; i < merged.segments.length; i++) {
      merged.ud_overlay.doc2seg.push(i);
      merged.ud_overlay.seg2doc.push(i);
      var res = merged.results_by_seg[i];
      if (res && res.source !== 'PUNCT') {
        merged.results.push(res);
        break;
      }
    }
    return merged;
  }

  function defaultBridge() {
    function buildLookupPostRequest(url) {
      var rawUrl = String(url || '');
      try {
        var parsed = new URL(rawUrl, window.location.origin);
        if (parsed.pathname !== '/lookup' || !parsed.searchParams.has('q')) {
          return { url: url, init: undefined };
        }
        var q = String(parsed.searchParams.get('q') || '');
        parsed.searchParams.delete('q');
        var body = { q: q };
        if (parsed.searchParams.get('lang')) {
          body.lang = String(parsed.searchParams.get('lang') || '');
        }
        return {
          url: parsed.pathname + parsed.search + parsed.hash,
          init: {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
          }
        };
      } catch (_err) {
        return { url: url, init: undefined };
      }
    }

    return {
      getTarget: function() { return document.getElementById('renderedText'); },
      buildLookupUrl: function(text) { return '/lookup?q=' + encodeURIComponent(text || ''); },
      fetchLookup: async function(url) {
        var request = buildLookupPostRequest(url);
        var resp = await fetch(request.url, request.init);
        if (!resp.ok) throw new Error('lookup HTTP ' + resp.status);
        return resp.json();
      },
      fetchChunkedLookup: null,
      getLookupOptions: function() { return {}; },
      getLookupChunks: null,
      getRendererOptions: function() { return {}; },
      onStatus: noop,
      onEmptyPage: noop,
      onBeforeLookup: noop,
      onLookupPayload: noop,
      onAnnotatedPage: noop,
      onRenderedPage: noop,
      onError: function(err) { console.error(err); }
    };
  }

  function Controller(opts) {
    requireDeps();
    opts = opts || {};
    this.bridge = Object.assign(defaultBridge(), opts.bridge || {});
    this.doc = null;
    this.activePageIndex = 0;
    this.cache = new Map();
    this.seq = 0;
  }

  Controller.prototype.setDocument = function(doc, opts) {
    opts = opts || {};
    if (!doc || !Array.isArray(doc.pages)) throw new Error('setDocument requires a CanonicalDocument with pages[]');
    global.CanonicalModel.validateDocument(doc, { throwOnError: true });
    this.doc = doc;
    this.activePageIndex = Math.max(0, Math.min(doc.pages.length - 1, num(opts.pageIndex, 0)));
    if (opts.clearCache !== false) this.cache.clear();
    if (typeof this.bridge.onDocumentSet === 'function') this.bridge.onDocumentSet(doc, opts);
    return doc;
  };

  Controller.prototype.clear = function() {
    this.doc = null;
    this.activePageIndex = 0;
    this.cache.clear();
    this.seq += 1;
  };

  Controller.prototype.hasDocument = function() {
    return !!(this.doc && Array.isArray(this.doc.pages) && this.doc.pages.length);
  };

  Controller.prototype.getPage = function(index) {
    if (!this.hasDocument()) return null;
    var i = Math.max(0, Math.min(this.doc.pages.length - 1, num(index, this.activePageIndex)));
    return this.doc.pages[i] || null;
  };

  Controller.prototype.cacheKey = function(page, lookupOpts) {
    lookupOpts = lookupOpts || {};
    var docId = this.doc && this.doc.id || 'doc';
    var lang = lookupOpts.language || lookupOpts.lang || '';
    var dict = lookupOpts.dictionary || lookupOpts.dict || lookupOpts.dictSource || '';
    var settings = lookupOpts.settingsKey || lookupOpts.normalizationKey || '';
    return [docId, page && page.id || page && page.index || 0, lang, dict, settings, str(page && page.text).length].join('|');
  };

  Controller.prototype.lookupPage = async function(page, opts) {
    opts = opts || {};
    var lookupOpts = Object.assign({}, this.bridge.getLookupOptions(page) || {}, opts.lookupOptions || {});
    var chunkedLookup = !!opts.chunkedLookup;
    var chunks = null;
    if (chunkedLookup && typeof this.bridge.getLookupChunks === 'function') {
      var chunkResult = this.bridge.getLookupChunks(page, lookupOpts, opts) || null;
      chunks = Array.isArray(chunkResult) ? chunkResult : (chunkResult && Array.isArray(chunkResult.chunks) ? chunkResult.chunks : null);
      chunks = (chunks || []).filter(function(chunk) { return chunk && str(chunk.text).trim(); });
      chunks.sort(function(a, b) { return num(a.start, 0) - num(b.start, 0) || num(a.end, 0) - num(b.end, 0); });
      if (chunks.length < 2) chunks = null;
    }
    var key = opts.cacheKey || this.cacheKey(page, lookupOpts);
    if (chunks) {
      key += '|chunked:' + chunks.map(function(chunk) {
        return [num(chunk.start, 0), num(chunk.end, 0), str(chunk.text).length].join('-');
      }).join(',');
    }
    if (opts.useCache !== false && this.cache.has(key)) return this.cache.get(key);
    var payload;
    if (chunks && typeof this.bridge.fetchChunkedLookup === 'function') {
      payload = await this.bridge.fetchChunkedLookup(page, chunks, lookupOpts, opts);
    } else if (chunks) {
      var payloads = [];
      for (var i = 0; i < chunks.length; i++) {
        var chunkLookupOpts = Object.assign({}, lookupOpts, {
          chunkedLookup: true,
          chunkIndex: i,
          chunkCount: chunks.length,
          chunkStart: num(chunks[i].start, 0),
          chunkEnd: num(chunks[i].end, 0)
        });
        var chunkUrl = chunkLookupOpts.url || this.bridge.buildLookupUrl(chunks[i].text, page, chunkLookupOpts);
        var chunkPayload = await this.bridge.fetchLookup(chunkUrl, page, chunkLookupOpts);
        if (!chunkPayload || chunkPayload.ok === false) {
          throw new Error(chunkPayload && chunkPayload.error ? chunkPayload.error : 'lookup failed');
        }
        payloads.push(chunkPayload);
      }
      payload = mergeChunkLookupPayloads(page, chunks, payloads);
      payload.trankit_chunked_lookup = {
        enabled: true,
        chunk_count: chunks.length,
        chunks: chunks.map(function(chunk, idx) {
          return { index: idx, start: num(chunk.start, 0), end: num(chunk.end, 0), textLength: str(chunk.text).length };
        })
      };
    } else {
      var url = lookupOpts.url || this.bridge.buildLookupUrl(page.text, page, lookupOpts);
      payload = await this.bridge.fetchLookup(url, page, lookupOpts);
    }
    if (!payload || payload.ok === false) throw new Error(payload && payload.error ? payload.error : 'lookup failed');
    this.cache.set(key, payload);
    return payload;
  };

  Controller.prototype.lookupAndRenderPage = async function(index, opts) {
    opts = opts || {};
    if (!this.hasDocument()) return false;
    var page = this.getPage(index);
    if (!page) return false;
    this.activePageIndex = page.index || 0;
    var runSeq = ++this.seq;

    if (!page.text || !String(page.text).trim()) {
      this.bridge.onEmptyPage(page, this.doc);
      return true;
    }

    try {
      this.bridge.onBeforeLookup(page, this.doc);
      this.bridge.onStatus('Segmenting...', page, this.doc);
      var payload = await this.lookupPage(page, opts);
      if (runSeq !== this.seq) return true;
      this.bridge.onLookupPayload(payload, page, this.doc);
      global.CanonicalAnnotator.annotatePage(page, payload, { keepPayload: opts.keepPayload !== false });
      this.bridge.onAnnotatedPage(page, payload, this.doc);
      var target = this.bridge.getTarget(page, this.doc);
      var rendererOpts = Object.assign({}, this.bridge.getRendererOptions(page, payload, this.doc) || {}, opts.rendererOptions || {});
      var root = global.CanonicalRenderer.renderPage(page, target, rendererOpts);
      this.bridge.onRenderedPage(page, payload, root, this.doc);
      return true;
    } catch (err) {
      if (runSeq !== this.seq) return true;
      this.bridge.onError(err, page, this.doc);
      return false;
    }
  };

  Controller.prototype.renderCachedAnnotatedPage = function(index, opts) {
    opts = opts || {};
    if (!this.hasDocument()) return false;
    var page = this.getPage(index);
    if (!page) return false;
    var target = this.bridge.getTarget(page, this.doc);
    var payload = page.lookupPayload || null;
    var rendererOpts = Object.assign({}, this.bridge.getRendererOptions(page, payload, this.doc) || {}, opts.rendererOptions || {});
    var root = global.CanonicalRenderer.renderPage(page, target, rendererOpts);
    this.bridge.onRenderedPage(page, payload, root, this.doc);
    return true;
  };

  Controller.prototype.setFromDocRenderResult = function(result, opts) {
    if (!global.CanonicalLegacyAdapter) throw new Error('CanonicalLegacyAdapter missing');
    var doc = global.CanonicalLegacyAdapter.fromDocRenderResult(result, opts || {});
    return this.setDocument(doc, opts || {});
  };

  Controller.prototype.setFromText = function(text, opts) {
    opts = opts || {};
    var doc;
    if (global.CanonicalBuilder && typeof global.CanonicalBuilder.fromText === 'function') {
      doc = global.CanonicalBuilder.fromText(text || '', { meta: Object.assign({ format: 'text' }, opts.meta || {}) });
    } else {
      throw new Error('CanonicalBuilder missing');
    }
    if (opts.paginate && global.CanonicalPaginator) doc = global.CanonicalPaginator.paginateFlowDocument(doc, opts.pageSize || {});
    return this.setDocument(doc, opts);
  };

  global.CanonicalReaderController = Controller;
})(window);
