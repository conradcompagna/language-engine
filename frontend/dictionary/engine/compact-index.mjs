import {
  applyMorphPosReclassificationToList,
  buildAlwaysFilteredPosMap,
  buildVietnameseAllowedPosMap,
  getLanguageRules,
  getLanguageUposExtraPos,
  normalizeVietnameseXposTags,
  splitEntriesByAlwaysFiltered
} from './entry-filters.mjs';
import { DictionaryEngine, ensureHydrated, etymKey, hydrateEntry, splitUposTags } from './model.mjs';
import { buildKoreanAllowedPosMap, lookupKey, lookupKeys } from './normalization.mjs';
import { normalizationState } from './normalization.state.mjs';
import { selectEntriesByPreferredPosRaw } from './selection.mjs';
export function initializeCompactIndex() {
  DictionaryEngine.prototype.fillToken = function (word, opts) {
    return this.fill_token(word, opts || {});
  };
  DictionaryEngine.prototype.filter_entries_by_upos = function (entries, upos, opts) {
    opts = opts || {};
    var baseEntries = entries ? entries.slice() : [];
    if (!baseEntries.length) return [[], []];
    var greedyMatch = !!opts.greedy_match;
    var greedyMultiFill = !!opts.greedy_multi_fill;
    var greedyMode = greedyMatch || greedyMultiFill;
    var affixPreferred = Object.create(null);
    if (greedyMode) {
      for (var axi = 0; axi < normalizationState.NOUN_AFFIX_POS.length; axi++) {
        affixPreferred[normalizationState.NOUN_AFFIX_POS[axi]] = true;
      }
    }
    var activeAlwaysFiltered = buildAlwaysFilteredPosMap(
      normalizationState.ALWAYS_FILTERED_POS,
      this._lang_code
    );
    if (greedyMode) {
      for (var ap in affixPreferred) {
        if (!Object.prototype.hasOwnProperty.call(affixPreferred, ap)) continue;
        delete activeAlwaysFiltered[ap];
      }
    }
    var alwaysFilteredSplit = splitEntriesByAlwaysFiltered(baseEntries, activeAlwaysFiltered);
    var filterBaseEntries = applyMorphPosReclassificationToList(alwaysFilteredSplit[0]);
    var alwaysFilteredEntries = alwaysFilteredSplit[1];
    if (!filterBaseEntries.length) return [[], alwaysFilteredEntries];
    if (filterBaseEntries.length <= 1) return [filterBaseEntries, alwaysFilteredEntries];
    if (Array.isArray(opts.force_pos_raws) && opts.force_pos_raws.length) {
      var forcedPosSplit = selectEntriesByPreferredPosRaw(filterBaseEntries, opts.force_pos_raws);
      if (forcedPosSplit.primary.length) {
        return [forcedPosSplit.primary, forcedPosSplit.other.concat(alwaysFilteredEntries)];
      }
    }
    var uposTags = splitUposTags(String(upos || ''));
    var allowed = Object.create(null);
    var recognized = false;
    for (var ti = 0; ti < uposTags.length; ti++) {
      var mapped = normalizationState.UPOS_TO_KAIKKI_POS[uposTags[ti]];
      var extraMapped = getLanguageUposExtraPos(this._lang_code, uposTags[ti]);
      var combined = [];
      if (Array.isArray(mapped)) combined = combined.concat(mapped);
      if (extraMapped.length) combined = combined.concat(extraMapped);
      if (!combined.length) continue;
      recognized = true;
      for (var mi = 0; mi < combined.length; mi++) {
        allowed[combined[mi]] = true;
      }
    }
    if (!uposTags.length || !recognized || !Object.keys(allowed).length) {
      var hasAffixPreferred = false;
      if (greedyMode) {
        for (var ae = 0; ae < filterBaseEntries.length; ae++) {
          if (affixPreferred[String(filterBaseEntries[ae].pos_raw || '')]) {
            hasAffixPreferred = true;
            break;
          }
        }
      }
      if (!hasAffixPreferred) {
        return [filterBaseEntries, alwaysFilteredEntries];
      }
      var pri = [];
      var oth = [];
      for (var e = 0; e < filterBaseEntries.length; e++) {
        var noGatePosRaw = String(filterBaseEntries[e].pos_raw || '');
        if (affixPreferred[noGatePosRaw]) pri.push(filterBaseEntries[e]);
        else oth.push(filterBaseEntries[e]);
      }
      return [pri, oth.concat(alwaysFilteredEntries)];
    }
    var etymGroups = [];
    var etymGroupMap = Object.create(null);
    for (var eg = 0; eg < filterBaseEntries.length; eg++) {
      var ekey = etymKey(filterBaseEntries[eg]);
      if (etymGroupMap[ekey] === undefined) {
        etymGroupMap[ekey] = etymGroups.length;
        etymGroups.push([]);
      }
      etymGroups[etymGroupMap[ekey]].push(filterBaseEntries[eg]);
    }
    var primary = [];
    var other = [];
    for (var gi = 0; gi < etymGroups.length; gi++) {
      var group = etymGroups[gi];
      var groupPrimary = [];
      var groupOther = [];
      var hasAllowedMatch = false;
      for (var ge = 0; ge < group.length; ge++) {
        var posRaw = String(group[ge].pos_raw || '');
        if (allowed[posRaw] || affixPreferred[posRaw]) {
          hasAllowedMatch = true;
          groupPrimary.push(group[ge]);
        } else if (normalizationState.FILTER_EXEMPT_POS[posRaw]) {
          groupPrimary.push(group[ge]);
        } else {
          groupOther.push(group[ge]);
        }
      }
      if (hasAllowedMatch) {
        for (var p = 0; p < groupPrimary.length; p++) primary.push(groupPrimary[p]);
        for (var o = 0; o < groupOther.length; o++) other.push(groupOther[o]);
      } else if (groupPrimary.length) {
        for (var p2 = 0; p2 < groupPrimary.length; p2++) primary.push(groupPrimary[p2]);
        for (var o2 = 0; o2 < groupOther.length; o2++) other.push(groupOther[o2]);
      } else {
        for (var g2 = 0; g2 < group.length; g2++) other.push(group[g2]);
      }
    }
    if (!primary.length) return [filterBaseEntries, alwaysFilteredEntries];
    return [primary, other.concat(alwaysFilteredEntries)];
  };
  DictionaryEngine.prototype.filterEntriesByUpos = function (entries, upos, opts) {
    var split = this.filter_entries_by_upos(entries, upos, opts || {});
    return {
      primary: split[0],
      other: split[1]
    };
  };
  DictionaryEngine.prototype.filter_entries_by_xpos = function (entries, xposTags) {
    var baseEntries = entries ? entries.slice() : [];
    if (!baseEntries.length) return [baseEntries, []];
    var lang = String(this._lang_code || '')
      .trim()
      .toLowerCase();
    if (lang === 'vi') {
      var viAlwaysFilteredSplit = splitEntriesByAlwaysFiltered(
        baseEntries,
        buildAlwaysFilteredPosMap(normalizationState.VIETNAMESE_XPOS_ALWAYS_FILTERED_POS, lang)
      );
      var viFilterBaseEntries = viAlwaysFilteredSplit[0];
      var viAlwaysFilteredEntries = viAlwaysFilteredSplit[1];
      if (!viFilterBaseEntries.length) return [[], viAlwaysFilteredEntries];
      if (viFilterBaseEntries.length <= 1) return [viFilterBaseEntries, viAlwaysFilteredEntries];
      var viTags = normalizeVietnameseXposTags(xposTags);
      if (!viTags.length) return [viFilterBaseEntries, viAlwaysFilteredEntries];
      var viAllowedInfo = buildVietnameseAllowedPosMap(viTags);
      if (!viAllowedInfo.has_mapped || !Object.keys(viAllowedInfo.allowed).length)
        return [viFilterBaseEntries, viAlwaysFilteredEntries];
      var etymGroups = [];
      var etymGroupMap = Object.create(null);
      for (var eg = 0; eg < viFilterBaseEntries.length; eg++) {
        var ekey = etymKey(viFilterBaseEntries[eg]);
        if (etymGroupMap[ekey] === undefined) {
          etymGroupMap[ekey] = etymGroups.length;
          etymGroups.push([]);
        }
        etymGroups[etymGroupMap[ekey]].push(viFilterBaseEntries[eg]);
      }
      var primary = [];
      var other = [];
      for (var gi = 0; gi < etymGroups.length; gi++) {
        var group = etymGroups[gi];
        var groupPrimary = [];
        var groupOther = [];
        var hasAllowedMatch = false;
        for (var ge = 0; ge < group.length; ge++) {
          var entry = group[ge] || {};
          var posRaw = String(entry.pos_raw || '')
            .trim()
            .toLowerCase();
          if (viAllowedInfo.allowed[posRaw]) {
            hasAllowedMatch = true;
            groupPrimary.push(entry);
          } else if (normalizationState.VIETNAMESE_XPOS_FILTER_EXEMPT_POS[posRaw]) {
            groupPrimary.push(entry);
          } else {
            groupOther.push(entry);
          }
        }
        if (hasAllowedMatch) {
          for (var p = 0; p < groupPrimary.length; p++) primary.push(groupPrimary[p]);
          for (var o = 0; o < groupOther.length; o++) other.push(groupOther[o]);
        } else if (groupPrimary.length) {
          for (var p2 = 0; p2 < groupPrimary.length; p2++) primary.push(groupPrimary[p2]);
          for (var o2 = 0; o2 < groupOther.length; o2++) other.push(groupOther[o2]);
        } else {
          for (var g2 = 0; g2 < group.length; g2++) other.push(group[g2]);
        }
      }
      if (!primary.length) return [viFilterBaseEntries, viAlwaysFilteredEntries];
      return [primary, other.concat(viAlwaysFilteredEntries)];
    }
    var koAlwaysFilteredSplit = splitEntriesByAlwaysFiltered(
      baseEntries,
      buildAlwaysFilteredPosMap(normalizationState.ALWAYS_FILTERED_POS, lang)
    );
    var koFilterBaseEntries = koAlwaysFilteredSplit[0];
    var koAlwaysFilteredEntries = koAlwaysFilteredSplit[1];
    if (!koFilterBaseEntries.length) return [[], koAlwaysFilteredEntries];
    if (koFilterBaseEntries.length <= 1) return [koFilterBaseEntries, koAlwaysFilteredEntries];
    if (!Array.isArray(xposTags) || !xposTags.length) return [koFilterBaseEntries, koAlwaysFilteredEntries];
    var allowedInfo = buildKoreanAllowedPosMap(xposTags);
    if (!allowedInfo.has_mapped || !Object.keys(allowedInfo.allowed).length)
      return [koFilterBaseEntries, koAlwaysFilteredEntries];
    function splitByAllowed(allowedMap) {
      if (!allowedMap || !Object.keys(allowedMap).length) return [[], koFilterBaseEntries.slice()];
      var primary = [];
      var other = [];
      for (var ei = 0; ei < koFilterBaseEntries.length; ei++) {
        var entry = koFilterBaseEntries[ei] || {};
        var posRaw = String(entry.pos_raw || '')
          .trim()
          .toLowerCase();
        if (normalizationState.KOREAN_XPOS_FILTER_EXEMPT_POS[posRaw]) {
          primary.push(entry);
          continue;
        }
        if (allowedMap[posRaw]) primary.push(entry);
        else other.push(entry);
      }
      return [primary, other];
    }
    var split = splitByAllowed(allowedInfo.allowed);
    if (!split[0].length) return [koFilterBaseEntries, koAlwaysFilteredEntries];
    return [split[0], split[1].concat(koAlwaysFilteredEntries)];
  };
  DictionaryEngine.prototype.filterEntriesByXpos = function (entries, xposTags) {
    var split = this.filter_entries_by_xpos(entries, xposTags || []);
    return {
      primary: split[0],
      other: split[1]
    };
  };
  DictionaryEngine.prototype.get_xpos_primary_match_info = function (entries, xposTags, opts) {
    var baseEntries = entries ? entries.slice() : [];
    var allowedInfo = buildKoreanAllowedPosMap(xposTags);
    var allowedPos = Object.keys(allowedInfo.allowed).sort();
    var hasMatch = false;
    if (!allowedInfo.has_mapped || !allowedPos.length) {
      hasMatch = true;
    } else {
      for (var ei = 0; ei < baseEntries.length; ei++) {
        var entry = baseEntries[ei] || {};
        var posRaw = String(entry.pos_raw || entry.pos || '')
          .trim()
          .toLowerCase();
        if (posRaw && allowedInfo.allowed[posRaw]) {
          hasMatch = true;
          break;
        }
      }
    }
    return {
      tags: Array.isArray(allowedInfo.tags) ? allowedInfo.tags.slice() : [],
      allowed_pos: allowedPos,
      has_mapped: !!allowedInfo.has_mapped,
      has_match: !!hasMatch,
      veto_reason: ''
    };
  };
  DictionaryEngine.prototype.has_xpos_primary_match = function (entries, xposTags) {
    return !!this.get_xpos_primary_match_info(entries, xposTags).has_match;
  };
  DictionaryEngine.lookupKey = lookupKey;
  DictionaryEngine.lookupKeys = lookupKeys;
  DictionaryEngine.etymKey = etymKey;
  DictionaryEngine.splitUposTags = splitUposTags;
  DictionaryEngine._hydrateEntry = hydrateEntry;
  DictionaryEngine._ensureHydrated = ensureHydrated;
  window.DictionaryLanguageRules = window.DictionaryLanguageRules || {};
  window.DictionaryLanguageRules.rules = normalizationState.LANGUAGE_SPECIFIC_RULES;
  window.DictionaryLanguageRules.getRules = getLanguageRules;

  // ── Hybrid / Compact-Index extensions ─────────────────────────────────────
  //
  // loadCompactIndex() switches the engine into "compact mode".
  // In compact mode:
  //   - lookup_all() returns winner ref stubs instead of full entry objects
  //   - _entry_to_fill() wraps stubs into minimal fill objects that carry
  //     the winner ref for extraction by dictionary_client_hybrid.js
  //   - The DP still runs normally; full entry hydration happens after DP
  //     via a POST to /js/hydrate
  //
  // Winner ref stub shape (also matches /js/hydrate wire format):
  //   { _winner_ref: true, db_alias, entry_row_id, match_kind, match_key,
  //     form_row_id?, headword }

  /**
   * Switch engine to compact-index mode.
   * @param {Object} hwObj   {normalized_key: [[db_alias, entry_row_id], ...]}
   * @param {Object} fwObj   {normalized_key: [[db_alias, entry_row_id, form_row_id], ...]}
   * @param {Object} dbAliasMap  {db_alias: label_string}
   */
  DictionaryEngine.prototype.loadCompactIndex = function (hwObj, fwObj, dbAliasMap) {
    this._compact_mode = true;
    this._hw_index = hwObj || Object.create(null);
    this._fw_index = fwObj || Object.create(null);
    this._db_alias_map = dbAliasMap || Object.create(null);
    // Keep standard indexes empty so non-compact paths return nothing
    this._by_word = Object.create(null);
    this._form_index = Object.create(null);
  };

  // Bounded codepoint-level Levenshtein. Returns maxD+1 if distance exceeds maxD.
  return true;
}
