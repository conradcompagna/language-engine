/* canonical_lookup.js
 *
 * Sends CanonicalPage.text to the existing /lookup pipeline.
 *
 * This module is endpoint-agnostic. Codex can pass buildLookupUrl from reader.js,
 * or pass a custom fetchLookup(page, options) implementation.
 *
 * Browser global:
 *   window.CanonicalLookup
 */
(function(global) {
  'use strict';

  function stableStringify(obj) {
    if (!obj || typeof obj !== 'object') return String(obj || '');
    var keys = Object.keys(obj).sort();
    var out = {};
    keys.forEach(function(k) { out[k] = obj[k]; });
    try { return JSON.stringify(out); } catch (_e) { return String(obj); }
  }

  function defaultCacheKey(doc, page, options) {
    options = options || {};
    return [
      doc && doc.id || 'doc',
      page && page.index || 0,
      options.language || options.lang || '',
      stableStringify(options.lookupSettings || {})
    ].join('::');
  }

  function LookupCache() {
    this.map = Object.create(null);
  }
  LookupCache.prototype.get = function(key) { return this.map[key] || null; };
  LookupCache.prototype.set = function(key, value) { this.map[key] = value; return value; };
  LookupCache.prototype.clear = function() { this.map = Object.create(null); };
  LookupCache.prototype.delete = function(key) { delete this.map[key]; };

  function buildQueryUrl(baseUrl, text) {
    var sep = baseUrl.indexOf('?') >= 0 ? '&' : '?';
    return baseUrl + sep + 'q=' + encodeURIComponent(text || '');
  }

  async function lookupCanonicalPage(page, options) {
    options = options || {};
    if (!page) throw new Error('lookupCanonicalPage requires a CanonicalPage');
    if (typeof options.fetchLookup === 'function') {
      return options.fetchLookup(page, options);
    }
    var url;
    if (typeof options.buildLookupUrl === 'function') {
      url = options.buildLookupUrl(page.text || '', page, options);
    } else {
      url = buildQueryUrl(options.lookupEndpoint || '/lookup', page.text || '');
    }
    var fetchImpl = options.fetch || global.fetch;
    if (!fetchImpl) throw new Error('fetch unavailable');
    var resp = await fetchImpl(url, options.fetchOptions || {});
    if (!resp.ok) throw new Error('lookup HTTP ' + resp.status);
    var data = await resp.json();
    if (data && data.ok === false) throw new Error(data.error || 'lookup failed');
    return data;
  }

  async function lookupWithCache(doc, page, options, cache) {
    cache = cache || new LookupCache();
    var key = (options && options.cacheKey) || defaultCacheKey(doc, page, options || {});
    var hit = cache.get(key);
    if (hit) return hit;
    var payload = await lookupCanonicalPage(page, options || {});
    cache.set(key, payload);
    return payload;
  }

  global.CanonicalLookup = {
    LookupCache: LookupCache,
    defaultCacheKey: defaultCacheKey,
    lookupCanonicalPage: lookupCanonicalPage,
    lookupWithCache: lookupWithCache,
    buildQueryUrl: buildQueryUrl
  };
})(window);
