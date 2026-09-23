import { fuzzySearchState } from './fuzzy-search.state.mjs';
import { DictionaryEngine } from './model.mjs';
import { lookupKey, lookupKeys } from './normalization.mjs';
export // Bounded codepoint-level Levenshtein. Returns maxD+1 if distance exceeds maxD.
function _boundedCodepointEdit(a, b, maxD) {
  var la = a.length,
    lb = b.length;
  if (Math.abs(la - lb) > maxD) return maxD + 1;
  if (!la) return lb <= maxD ? lb : maxD + 1;
  if (!lb) return la <= maxD ? la : maxD + 1;
  var prev = new Array(lb + 1);
  var curr = new Array(lb + 1);
  for (var j = 0; j <= lb; j++) prev[j] = j;
  for (var i = 1; i <= la; i++) {
    for (var k = 0; k <= lb; k++) curr[k] = maxD + 1;
    curr[0] = i;
    var rowMin = curr[0];
    var jStart = Math.max(1, i - maxD);
    var jEnd = Math.min(lb, i + maxD);
    var ai = a[i - 1];
    for (var jj = jStart; jj <= jEnd; jj++) {
      var cost = ai === b[jj - 1] ? 0 : 1;
      var del = prev[jj] + 1;
      var ins = curr[jj - 1] + 1;
      var sub = prev[jj - 1] + cost;
      var v = del < ins ? del : ins;
      if (sub < v) v = sub;
      curr[jj] = v;
      if (v < rowMin) rowMin = v;
    }
    if (rowMin > maxD) return maxD + 1;
    var tmp = prev;
    prev = curr;
    curr = tmp;
  }
  return prev[lb];
}
export function _toCodepointsNFD(s) {
  return Array.from(String(s || '').normalize('NFD'));
}

/**
 * Tiered fuzzy search over the compact index (headword + form keys).
 * Works on codepoints after NFD decomposition, so diacritic differences
 * count as one edit per combining mark. Stops at the first tier (0..maxTier)
 * that yields any hits. Returns { tier, stubs } where stubs match the
 * shape produced by _lookup_all_raw(), so downstream hydration code is
 * unchanged. Tier 0 is exact (post-normalization) and is normally already
 * covered by the standard lookup path.
 *
 * @param {string} word  User query surface
 * @param {Object} [opts] { maxTier: number (default 3), maxStubs: number (default 50) }
 */
export function initializeFuzzySearch() {
  DictionaryEngine.prototype.fuzzyLookupKeysTiered = function (word, opts) {
    if (!this._compact_mode)
      return {
        tier: -1,
        stubs: []
      };
    opts = opts || {};
    var maxTier = typeof opts.maxTier === 'number' ? opts.maxTier : 3;
    var maxStubs = typeof opts.maxStubs === 'number' ? opts.maxStubs : 50;
    var surface = String(word || '').trim();
    if (!surface)
      return {
        tier: -1,
        stubs: []
      };
    var normQuery = lookupKey(surface, this._lang_code);
    if (!normQuery)
      return {
        tier: -1,
        stubs: []
      };
    var qCps = _toCodepointsNFD(normQuery);
    if (!qCps.length)
      return {
        tier: -1,
        stubs: []
      };
    var hw = this._hw_index;
    var fw = this._fw_index;
    var aliasMap = this._db_alias_map || Object.create(null);
    var hwKeys = Object.keys(hw);
    var fwKeys = Object.keys(fw);

    // Precompute NFD codepoints for index keys lazily per tier iteration.
    // For speed we cache as we go.
    var cpCache = Object.create(null);
    function getCps(k) {
      var c = cpCache[k];
      if (c) return c;
      c = _toCodepointsNFD(k);
      cpCache[k] = c;
      return c;
    }
    for (var tier = 0; tier <= maxTier; tier++) {
      var hitKeysHw = [];
      var hitKeysFw = [];
      var ki, key, d;
      for (ki = 0; ki < hwKeys.length; ki++) {
        key = hwKeys[ki];
        d = _boundedCodepointEdit(qCps, getCps(key), tier);
        if (d === tier) hitKeysHw.push(key);
      }
      for (ki = 0; ki < fwKeys.length; ki++) {
        key = fwKeys[ki];
        d = _boundedCodepointEdit(qCps, getCps(key), tier);
        if (d === tier) hitKeysFw.push(key);
      }
      if (!hitKeysHw.length && !hitKeysFw.length) continue;
      var stubs = [];
      var seen = Object.create(null);
      var i, hits, alias, eid, fid, uid;
      for (i = 0; i < hitKeysHw.length && stubs.length < maxStubs; i++) {
        key = hitKeysHw[i];
        hits = hw[key] || [];
        for (var hi = 0; hi < hits.length && stubs.length < maxStubs; hi++) {
          alias = hits[hi][0];
          eid = hits[hi][1];
          uid = 'hw:' + alias + ':' + eid;
          if (seen[uid]) continue;
          seen[uid] = true;
          stubs.push({
            _winner_ref: true,
            storage_kind: aliasMap[alias] === 'custom' || alias === 'customdb' ? 'custom' : 'sqlite',
            db_alias: alias,
            entry_row_id: eid,
            match_kind: 'headword',
            match_key: key,
            headword: key,
            fuzzy_tier: tier
          });
        }
      }
      for (i = 0; i < hitKeysFw.length && stubs.length < maxStubs; i++) {
        key = hitKeysFw[i];
        hits = fw[key] || [];
        for (var fi = 0; fi < hits.length && stubs.length < maxStubs; fi++) {
          alias = hits[fi][0];
          eid = hits[fi][1];
          fid = hits[fi][2];
          uid = 'fw:' + alias + ':' + eid + ':' + fid;
          if (seen[uid]) continue;
          seen[uid] = true;
          stubs.push({
            _winner_ref: true,
            storage_kind: aliasMap[alias] === 'custom' || alias === 'customdb' ? 'custom' : 'sqlite',
            db_alias: alias,
            entry_row_id: eid,
            form_row_id: fid,
            match_kind: 'form',
            match_key: key,
            headword: key,
            fuzzy_tier: tier
          });
        }
      }
      if (stubs.length)
        return {
          tier: tier,
          stubs: stubs
        };
    }
    return {
      tier: -1,
      stubs: []
    };
  };

  /**
   * Inject a custom/Gemini entry key into the compact headword index.
   * Call after creating/editing a Gemini entry so it participates in DP
   * immediately without requiring a full index re-fetch.
   * @param {string} normalizedKey  Pre-normalized lookup key
   * @param {number} entryId        SQLite row id of the custom entry
   * @param {string} [dbAlias]      Defaults to "customdb"
   * @param {string} [matchKind]    "headword" (default) or "form"
   */
  DictionaryEngine.prototype.injectGeminiKey = function (normalizedKey, entryId, dbAlias, matchKind) {
    if (!this._compact_mode) return;
    var key = String(normalizedKey || '');
    var eid = parseInt(entryId, 10);
    var alias = String(dbAlias || 'customdb');
    if (!key || !(eid > 0)) return;
    void matchKind; // currently only headword injection is needed
    if (!this._hw_index[key]) this._hw_index[key] = [];
    var existing = this._hw_index[key];
    for (var i = 0; i < existing.length; i++) {
      if (existing[i][0] === alias && existing[i][1] === eid) return; // already present
    }
    this._hw_index[key].push([alias, eid]);
  };

  /**
   * Remove a custom entry key from the compact headword index.
   * Call after deleting a Gemini entry.
   * @param {string} normalizedKey
   * @param {number} entryId
   */
  DictionaryEngine.prototype.removeCompactKey = function (normalizedKey, entryId) {
    if (!this._compact_mode) return;
    var key = String(normalizedKey || '');
    var eid = parseInt(entryId, 10);
    if (!key || !this._hw_index[key]) return;
    this._hw_index[key] = this._hw_index[key].filter(function (pair) {
      return pair[1] !== eid;
    });
    if (!this._hw_index[key].length) delete this._hw_index[key];
  };

  // Override _lookup_all_raw to use compact index when in compact mode.
  // Returns winner ref stubs rather than full entry objects.
  fuzzySearchState._origLookupAllRaw = DictionaryEngine.prototype._lookup_all_raw;
  DictionaryEngine.prototype._lookup_all_raw = function (word) {
    if (!this._compact_mode) return fuzzySearchState._origLookupAllRaw.call(this, word);
    var surface = String(word || '').trim();
    var keys = lookupKeys(surface, this._lang_code);
    var stubs = [];
    var seen = Object.create(null);
    for (var ki = 0; ki < keys.length; ki++) {
      var key = keys[ki];
      var hwHits = this._hw_index[key];
      if (hwHits) {
        for (var hi = 0; hi < hwHits.length; hi++) {
          var alias = hwHits[hi][0];
          var eid = hwHits[hi][1];
          var uid = 'hw:' + alias + ':' + eid;
          if (seen[uid]) continue;
          seen[uid] = true;
          stubs.push({
            _winner_ref: true,
            storage_kind:
              this._db_alias_map[alias] === 'custom' || alias === 'customdb' ? 'custom' : 'sqlite',
            db_alias: alias,
            entry_row_id: eid,
            match_kind: 'headword',
            match_key: key,
            headword: surface // placeholder so DP lemma checks don't crash
          });
        }
      }
      var fwHits = this._fw_index[key];
      if (fwHits) {
        for (var fi = 0; fi < fwHits.length; fi++) {
          var falias = fwHits[fi][0];
          var feid = fwHits[fi][1];
          var ffid = fwHits[fi][2];
          var fuid = 'fw:' + falias + ':' + feid + ':' + ffid;
          if (seen[fuid]) continue;
          seen[fuid] = true;
          stubs.push({
            _winner_ref: true,
            storage_kind:
              this._db_alias_map[falias] === 'custom' || falias === 'customdb' ? 'custom' : 'sqlite',
            db_alias: falias,
            entry_row_id: feid,
            form_row_id: ffid,
            match_kind: 'form',
            match_key: key,
            headword: surface // placeholder
          });
        }
      }
    }
    return stubs;
  };

  // Override _entry_to_fill to wrap winner ref stubs in compact mode.
  // The client extracts the _winner_ref from fills to build the hydrate request.
  fuzzySearchState._origEntryToFill = DictionaryEngine.prototype._entry_to_fill;
  return true;
}
