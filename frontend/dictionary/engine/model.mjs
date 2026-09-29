import { dedupeSensesRuntime, parseTsvRowCompact } from './entry-filters.mjs';
import { internString, lookupKey, lookupKeys, normalizePos } from './normalization.mjs';
import { normalizationState } from './normalization.state.mjs';
export function parseTsvRowLegacy(row, headword, glossesRaw) {
  if (!glossesRaw) return null;
  var posRaw = internString((row.pos_raw || '').trim());
  var pos = internString(normalizePos(posRaw));
  var reading = (row.reading || '').trim();
  // Legacy format: store raw row data for lazy hydration
  var etymology = (row.etymology || '').trim();
  var etymNumRaw = (row.etymology_number || '').trim();
  var etymologyNumber = /^\d+$/.test(etymNumRaw) ? parseInt(etymNumRaw, 10) : 0;
  var entry = {
    headword: headword,
    pos: pos,
    pos_raw: posRaw,
    _glosses_raw: glossesRaw,
    _legacy_tags_raw: (row.tags || '').trim() || undefined,
    _legacy_row: row,
    // for splitList fields, hydrated lazily
    reading: reading,
    etymology: etymology || normalizationState.EMPTY_STRING,
    etymology_number: etymologyNumber
  };
  var entryId = String(row.entry_id || '').trim();
  if (entryId) entry.entry_id = entryId;
  var explicitSource = String(row.source || row._source || '').trim();
  if (explicitSource) entry._source = explicitSource;
  var formsRaw = (row.forms || '').trim();
  if (formsRaw) entry._forms_json = formsRaw;
  return entry;
}
export function parseTsvRow(row) {
  var headword = (row.headword || '').trim();
  if (!headword) return null;
  var glossesRaw = (row.glosses || '').trim();
  var isNewFormat = 'romanization' in row || glossesRaw.charAt(0) === '[';
  return isNewFormat
    ? parseTsvRowCompact(row, headword, glossesRaw)
    : parseTsvRowLegacy(row, headword, glossesRaw);
}
export function etymKey(entry) {
  var num = entry.etymology_number || 0;
  if (num && num > 0) return 'n:' + num;
  return 't:' + (entry.etymology || '');
}
export function splitUposTags(rawUpos) {
  var text = String(rawUpos || '').trim();
  if (!text) return [];
  if (text.indexOf('+') < 0) return [text];
  return text
    .split('+')
    .map(function (p) {
      return p.trim();
    })
    .filter(Boolean);
}
export function entryIdentityKey(entry) {
  var head = String(entry.headword || '');
  var posRaw = String(entry.pos_raw || '');
  var etymNum = 0;
  try {
    etymNum = parseInt(entry.etymology_number || 0, 10) || 0;
  } catch (_e) {}
  return head + '\t' + posRaw + '\t' + etymNum + '\t' + (entry.etymology || '');
}

/**
 * Lazily hydrate an entry: parse glosses JSON, run dedup, populate senses/senses_full
 * and all optional array fields. Called on first lookup access.
 * After hydration, _glosses_raw is deleted so it's only paid once.
 */
export function hydrateEntry(entry) {
  if (!entry || !entry._glosses_raw) return entry; // already hydrated or empty
  var glossesRaw = entry._glosses_raw;
  var isLegacy = !!entry._legacy_row;
  var sensesFull = [];
  var flatSenses = [];
  if (isLegacy) {
    // Legacy format: glosses are semicolon-separated plain text
    var glossList = glossesRaw
      .split(';')
      .map(function (g) {
        return g.trim();
      })
      .filter(Boolean);
    if (!glossList.length) {
      // Mark as hydrated but empty
      entry._glosses_raw = undefined;
      entry.senses = normalizationState.EMPTY_ARRAY;
      entry.senses_full = normalizationState.EMPTY_ARRAY;
      return entry;
    }
    flatSenses = glossList;
    var tagsRaw = entry._legacy_tags_raw || '';
    var tagsPerSense = [];
    if (tagsRaw) {
      var groups = tagsRaw.split('|');
      for (var ti = 0; ti < groups.length; ti++) {
        tagsPerSense.push(
          groups[ti]
            .split(';')
            .map(function (t) {
              return t.trim();
            })
            .filter(Boolean)
        );
      }
    }
    for (var j = 0; j < glossList.length; j++) {
      var sense = {
        glosses: [glossList[j]]
      };
      if (j < tagsPerSense.length && tagsPerSense[j].length) sense.tags = tagsPerSense[j];
      sensesFull.push(sense);
    }
    // Populate legacy-specific fields from stored row
    var row = entry._legacy_row;
    function splitList(key) {
      var raw = (row[key] || '').trim();
      if (!raw) return normalizationState.EMPTY_ARRAY;
      return raw
        .split(';')
        .map(function (v) {
          return v.trim();
        })
        .filter(Boolean);
    }
    entry.alt_forms = splitList('alt_forms');
    if (!entry.alt_forms.length) entry.alt_forms = normalizationState.EMPTY_ARRAY;
    entry.ipa_variants = entry.reading
      ? [
          {
            ipa: entry.reading,
            label: ''
          }
        ]
      : normalizationState.EMPTY_ARRAY;
    entry.audio_urls = normalizationState.EMPTY_ARRAY;
    entry.synonyms = splitList('synonyms');
    if (!entry.synonyms.length) entry.synonyms = normalizationState.EMPTY_ARRAY;
    entry.antonyms = splitList('antonyms');
    if (!entry.antonyms.length) entry.antonyms = normalizationState.EMPTY_ARRAY;
    entry.derived = splitList('derived');
    if (!entry.derived.length) entry.derived = normalizationState.EMPTY_ARRAY;
    entry.related = splitList('related');
    if (!entry.related.length) entry.related = normalizationState.EMPTY_ARRAY;
    var grammar = (row.grammar || '').trim();
    if (grammar) entry.grammar = grammar;
    // Release the row reference
    delete entry._legacy_row;
    delete entry._legacy_tags_raw;
  } else {
    // Compact format: glosses are JSON
    try {
      var parsed = JSON.parse(glossesRaw);
      if (Array.isArray(parsed)) {
        sensesFull = parsed;
        for (var i = 0; i < sensesFull.length; i++) {
          var gs = sensesFull[i].glosses;
          if (gs && gs.length) flatSenses.push(gs.join('; '));
        }
      }
    } catch (_e) {}
    // Compact entries get empty singletons for optional fields
    entry.alt_forms = normalizationState.EMPTY_ARRAY;
    entry.ipa_variants = normalizationState.EMPTY_ARRAY;
    entry.audio_urls = normalizationState.EMPTY_ARRAY;
    entry.synonyms = normalizationState.EMPTY_ARRAY;
    entry.antonyms = normalizationState.EMPTY_ARRAY;
    entry.derived = normalizationState.EMPTY_ARRAY;
    entry.related = normalizationState.EMPTY_ARRAY;
  }
  var deduped = dedupeSensesRuntime(flatSenses, sensesFull);
  entry.senses_full = deduped.full;
  // Derive flat senses from senses_full on demand — but for backward compat,
  // store it once during hydration so all consumers see it immediately.
  entry.senses = deduped.flat;
  // Release raw glosses
  delete entry._glosses_raw;
  return entry;
}

/**
 * Ensure an entry is hydrated before returning it to consumers.
 * Safe to call multiple times — no-op if already hydrated.
 */
export function ensureHydrated(entry) {
  if (entry && entry._glosses_raw) hydrateEntry(entry);
  return entry;
}

/**
 * Hydrate all entries in a bucket array. Used before returning lookup results.
 */
export function hydrateAll(entries) {
  if (!entries) return entries;
  for (var i = 0; i < entries.length; i++) {
    ensureHydrated(entries[i]);
  }
  return entries;
}
export function mergeAdjacentUnknownFills(fills) {
  var rows = Array.isArray(fills) ? fills : [];
  if (!rows.length) return [];
  var out = [];
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var source = String(row.source || '').toUpperCase();
    if (source !== 'UNKNOWN') {
      out.push(row);
      continue;
    }
    var prev = out.length ? out[out.length - 1] : null;
    if (prev && String(prev.source || '').toUpperCase() === 'UNKNOWN') {
      prev.text = String(prev.text || '') + String(row.text || '');
      prev.head = String(prev.head || prev.text || '') + String(row.text || '');
      continue;
    }
    out.push({
      text: String(row.text || ''),
      head: String(row.head || row.text || ''),
      roman: '',
      senses: [],
      pos: '',
      source: 'UNKNOWN'
    });
  }
  return out;
}
export function DictionaryEngine(langCode) {
  this._lang_code = String(langCode || '')
    .trim()
    .toLowerCase();
  this._by_word = Object.create(null);
  this._form_index = Object.create(null);
}
export function initializeModel() {
  DictionaryEngine.prototype._lookup_key = function (text) {
    return lookupKey(text, this._lang_code);
  };
  DictionaryEngine.prototype._lookup_keys = function (text) {
    return lookupKeys(text, this._lang_code);
  };
  DictionaryEngine.prototype.loadFromRows = function (rows) {
    var total = 0;
    for (var i = 0; i < rows.length; i++) {
      var entry = parseTsvRow(rows[i]);
      if (!entry) continue;
      var word = entry.headword;
      var foldKey = lookupKey(word, this._lang_code);
      if (!foldKey) continue;
      if (!this._by_word[foldKey]) this._by_word[foldKey] = [];
      this._by_word[foldKey].push(entry);
      total += 1;
      this._index_tsv_forms(entry, word, foldKey);
    }
    return total;
  };
  return true;
}
