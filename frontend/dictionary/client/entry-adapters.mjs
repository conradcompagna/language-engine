import {
  convertNumericPinyin,
  convertNumericPinyinInGloss,
  getCurrentLanguage,
  normalizeLookupKey,
  stripSwahiliBracketMarkup
} from './core.mjs';
import { _ensureEntryHydrated } from './hydration.mjs';
import { _entryRefKey } from './lookup-payloads.mjs';
import { abbreviatePos } from './result-merging.mjs';
export function cloneLemmaHintObject(rawHint) {
  if (rawHint && typeof rawHint === 'object' && !Array.isArray(rawHint)) {
    var out = {};
    for (var key in rawHint) {
      if (!Object.prototype.hasOwnProperty.call(rawHint, key)) continue;
      if (key === 'variants' && Array.isArray(rawHint[key])) out[key] = rawHint[key].slice();
      else out[key] = rawHint[key];
    }
    return out;
  }
  var text = String(rawHint || '').trim();
  return text
    ? {
        text: text
      }
    : {};
}
export function chooseEntry(surface, entries, engine) {
  if (!entries || !entries.length) return null;
  if (!surface) return entries[0];
  var targetText = String(surface || '').trim();
  var targetKey = normalizeLookupKey(engine, targetText);
  var normalizedMatch = null;
  for (var i = 0; i < entries.length; i++) {
    var entry = entries[i];
    if (!entry) continue;
    var headword = getEntryDisplayHeadword(entry);
    var surfaceForm = String(entry.surface_form || '').trim();
    if (headword === targetText || (surfaceForm && surfaceForm === targetText)) return entry;
    if (!normalizedMatch && targetKey) {
      if (headword && normalizeLookupKey(engine, headword) === targetKey) normalizedMatch = entry;
      else if (surfaceForm && normalizeLookupKey(engine, surfaceForm) === targetKey) normalizedMatch = entry;
    }
  }
  return normalizedMatch || entries[0];
}
export function mergeWordLists() {
  var seen = Object.create(null);
  var out = [];
  for (var ai = 0; ai < arguments.length; ai++) {
    var list = arguments[ai] || [];
    for (var i = 0; i < list.length; i++) {
      var word = String(list[i] || '');
      if (!word || seen[word]) continue;
      seen[word] = true;
      out.push(word);
    }
  }
  return out;
}
export function dedupeTextList(values) {
  var out = [];
  var seen = Object.create(null);
  var list = Array.isArray(values) ? values : [];
  for (var i = 0; i < list.length; i++) {
    var text = String(list[i] || '').trim();
    if (!text || seen[text]) continue;
    seen[text] = true;
    out.push(text);
  }
  return out;
}
export function cleanMorphDisplayTags(text) {
  var raw = String(text == null ? '' : text).trim();
  if (!raw) return '';
  var parts = raw
    .split(';')
    .map(function (part) {
      return String(part || '').trim();
    })
    .filter(Boolean);
  if (!parts.length) return '';
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < parts.length; i++) {
    var part = parts[i];
    if (
      String(part || '')
        .trim()
        .toLowerCase() === 'error-unrecognized-form'
    )
      continue;
    if (seen[part]) continue;
    seen[part] = true;
    out.push(part);
  }
  return out.join(';');
}
export function buildStructuredSensesFromRaw(raw, langCode) {
  var source = raw;
  if (typeof source === 'string') {
    var text = String(source || '').trim();
    if (!text) return [];
    try {
      source = JSON.parse(text);
    } catch (_e) {
      text = stripSwahiliBracketMarkup(text, langCode);
      if (!text) return [];
      return text
        .split(';')
        .map(function (part) {
          return String(part || '').trim();
        })
        .filter(Boolean)
        .map(function (gloss) {
          return {
            glosses: [gloss]
          };
        });
    }
  }
  if (source && typeof source === 'object' && !Array.isArray(source)) source = [source];
  if (!Array.isArray(source)) return [];
  var out = [];
  for (var i = 0; i < source.length; i++) {
    var item = source[i];
    if (item && typeof item === 'object') {
      var glosses = Array.isArray(item.glosses)
        ? item.glosses
            .map(function (gloss) {
              return stripSwahiliBracketMarkup(gloss, langCode);
            })
            .map(function (gloss) {
              return String(gloss || '').trim();
            })
            .filter(Boolean)
        : [];
      if (!glosses.length) {
        var fallback = stripSwahiliBracketMarkup(item.gloss || item.text || '', langCode);
        fallback = String(fallback || '').trim();
        if (fallback) glosses = [fallback];
      }
      if (!glosses.length) continue;
      var sense = Object.assign({}, item);
      if (sense.qualifier != null) {
        var cleanedQualifier = stripSwahiliBracketMarkup(sense.qualifier, langCode);
        if (cleanedQualifier) sense.qualifier = cleanedQualifier;
        else delete sense.qualifier;
      }
      sense.glosses = glosses;
      out.push(sense);
      continue;
    }
    var textValue = String(stripSwahiliBracketMarkup(item || '', langCode) || '').trim();
    if (textValue)
      out.push({
        glosses: [textValue]
      });
  }
  return out;
}
export function flattenCanonicalSenses(rawSenses, langCode) {
  var list = Array.isArray(rawSenses) ? rawSenses : [];
  var flat = [];
  for (var i = 0; i < list.length; i++) {
    var sense = list[i];
    if (sense && typeof sense === 'object') {
      var glosses = Array.isArray(sense.glosses) ? sense.glosses : [];
      var cleaned = glosses
        .map(function (gloss) {
          return stripSwahiliBracketMarkup(gloss, langCode);
        })
        .map(function (gloss) {
          return String(gloss || '').trim();
        })
        .filter(Boolean);
      if (cleaned.length) flat.push(cleaned.join('; '));
      continue;
    }
    var text = String(stripSwahiliBracketMarkup(sense || '', langCode) || '').trim();
    if (text) flat.push(text);
  }
  return dedupeTextList(flat);
}
export function normalizeCanonicalFormRows(raw, langCode) {
  var rows = Array.isArray(raw) ? raw : [];
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    var word = '';
    var commentary = '';
    var romanization = '';
    if (Array.isArray(row)) {
      word = String(row[0] || '').trim();
      commentary = String(stripSwahiliBracketMarkup(row[1] || '', langCode) || '').trim();
      romanization = String(row[2] || '').trim();
    } else if (row && typeof row === 'object') {
      word = String(row.word || row.form || row.headword || row.form_text || row.display_text || '').trim();
      commentary = String(stripSwahiliBracketMarkup(row.commentary || row.tags || '', langCode) || '').trim();
      romanization = String(row.romanization || row.reading || row.form_roman || '').trim();
    } else {
      word = String(row || '').trim();
    }
    if (!word) continue;
    var key = word + '\t' + commentary + '\t' + romanization;
    if (seen[key]) continue;
    seen[key] = true;
    out.push([word, commentary, romanization]);
  }
  return out;
}
export function mergeUniqueTextList(baseValues, extraValues) {
  var out = [];
  var seen = Object.create(null);
  function pushOne(raw) {
    var text = String(raw || '').trim();
    if (!text || seen[text]) return;
    seen[text] = true;
    out.push(text);
  }
  var baseList = Array.isArray(baseValues) ? baseValues : baseValues ? [baseValues] : [];
  for (var i = 0; i < baseList.length; i++) pushOne(baseList[i]);
  var extraList = Array.isArray(extraValues) ? extraValues : extraValues ? [extraValues] : [];
  for (var j = 0; j < extraList.length; j++) pushOne(extraList[j]);
  return out;
}
export function getStableRuntimeEntryId(entry) {
  var e = entry && typeof entry === 'object' ? entry : {};
  var runtimeId = String(e.runtime_entry_id || '').trim();
  if (runtimeId) return runtimeId;
  var storageKind = String(e._storage_kind || '')
    .trim()
    .toLowerCase();
  var dbAlias = String(e._storage_db_alias || '').trim();
  var rowId = parseInt(e._storage_row_id || 0, 10) || 0;
  if (storageKind && dbAlias && rowId > 0) {
    return storageKind + '|' + dbAlias + '|' + rowId;
  }
  var explicit = String(e.entry_id || '').trim();
  if (explicit) return explicit;
  return '';
}
export function getBundledEntryKey(entry) {
  var e = entry && typeof entry === 'object' ? entry : null;
  if (!e) return '';

  // Compact-mode winner refs and hydrated sqlite rows
  var storageKind = String(e.storage_kind || e._storage_kind || 'sqlite')
    .trim()
    .toLowerCase();
  var dbAlias = String(e.db_alias || e._storage_db_alias || '').trim();
  var entryRowId = parseInt(e.entry_row_id || e._storage_row_id || 0, 10) || 0;
  var formRowId = parseInt(e.form_row_id || e._storage_form_row_id || 0, 10) || 0;
  if (dbAlias && entryRowId > 0) {
    return storageKind + '|' + dbAlias + '|' + entryRowId + (formRowId > 0 ? '|' + formRowId : '');
  }

  // Runtime/hydrated entry ids
  var runtimeId = String(e.runtime_entry_id || '').trim();
  if (runtimeId) return 'runtime|' + runtimeId;
  var refKey = String(e.ref_key || '').trim();
  if (refKey) return 'ref|' + refKey;
  var entryId = String(e.entry_id || '').trim();
  if (entryId) return 'entry|' + entryId;

  // Stable semantic fallback
  var headword = String(e.headword || e.display_headword || e.surface_form || e.head || '').trim();
  var posRaw = String(e.pos_raw || e.pos || '').trim();
  var lemma = String(e.lemma_headword || e.morph_base || '').trim();
  return 'fallback|' + headword + '|' + posRaw + '|' + lemma;
}
export function pushUniqueBundledEntry(out, seen, entry) {
  if (!entry) return;
  var key = getBundledEntryKey(entry);
  if (!key) {
    out.push(entry);
    return;
  }
  if (seen[key]) return;
  seen[key] = 1;
  out.push(entry);
}
export function getEntryMatchKind(entry) {
  var e = entry && typeof entry === 'object' ? entry : {};
  return String(e.match_kind || e._match_kind || e._match_source || '')
    .trim()
    .toLowerCase();
}
export function getEntryDisplayHeadword(entry) {
  var e = entry && typeof entry === 'object' ? entry : {};
  return String(e.display_headword || e.headword || e.surface_form || '').trim();
}
export function getEntryDisplayReading(entry) {
  var e = entry && typeof entry === 'object' ? entry : {};
  var displayReading = String(e.display_reading || e.reading || '').trim();
  if (displayReading) return displayReading;
  if (getEntryMatchKind(e) === 'form') return '';
  return String(e.pinyin || '').trim();
}
export function mergeEntryMorphInfo(target, incoming) {
  if (!target || typeof target !== 'object' || !incoming || typeof incoming !== 'object') return;
  var merged = mergeUniqueTextList(target.morph_info, incoming.morph_info);
  if (merged.length) target.morph_info = merged;
  else if (Object.prototype.hasOwnProperty.call(target, 'morph_info')) delete target.morph_info;
}
export function cloneHydratedEntryForAggregation(entry) {
  var out = {};
  var src = entry && typeof entry === 'object' ? entry : {};
  for (var key in src) {
    if (Object.prototype.hasOwnProperty.call(src, key)) out[key] = src[key];
  }
  if (Array.isArray(src.morph_info)) out.morph_info = src.morph_info.slice();
  if (Array.isArray(src.surface_forms)) out.surface_forms = src.surface_forms.slice();
  if (Array.isArray(src._matched_forms)) {
    out._matched_forms = src._matched_forms.map(function (row) {
      var copy = {};
      var raw = row && typeof row === 'object' ? row : {};
      for (var rowKey in raw) {
        if (!Object.prototype.hasOwnProperty.call(raw, rowKey)) continue;
        if (Array.isArray(raw[rowKey])) copy[rowKey] = raw[rowKey].slice();
        else copy[rowKey] = raw[rowKey];
      }
      return copy;
    });
  }
  if (src.forms && typeof src.forms === 'object' && !Array.isArray(src.forms)) {
    out.forms = Object.assign({}, src.forms);
    if (Array.isArray(src.forms.rows)) {
      out.forms.rows = normalizeCanonicalFormRows(src.forms.rows);
    }
  }
  return out;
}
export function normalizeCanonicalEntryRuntime(entry) {
  if (!entry || typeof entry !== 'object') return entry;
  if (entry._glosses_raw && window.DictionaryEngine && window.DictionaryEngine._hydrateEntry) {
    window.DictionaryEngine._hydrateEntry(entry);
  }
  var activeLang = String(entry.lang_code || entry.lang || entry._lang_code || getCurrentLanguage() || '')
    .trim()
    .toLowerCase();
  if (!entry.pos_raw && entry.pos) {
    entry.pos_raw = String(entry.pos || '');
  }
  if (!entry.pos && entry.pos_raw) {
    entry.pos = String(entry.pos_raw || '');
  }
  if (!entry.tag && entry.xpos) {
    entry.tag = String(entry.xpos || '');
  } else if (!entry.xpos && entry.tag) {
    entry.xpos = String(entry.tag || '');
  }
  if (entry.romanization) {
    entry.romanization = convertNumericPinyin(String(entry.romanization));
  }
  if (entry.display_reading) {
    entry.display_reading = convertNumericPinyin(String(entry.display_reading || ''));
  }
  if (entry.entry_reading) {
    entry.entry_reading = convertNumericPinyin(String(entry.entry_reading || ''));
  }
  if (!entry.reading && entry.romanization) {
    entry.reading = entry.romanization;
  } else if (entry.reading) {
    entry.reading = convertNumericPinyin(String(entry.reading));
  }
  if (!entry.roman && entry.reading) {
    entry.roman = String(entry.reading || '');
  } else if (entry.roman) {
    entry.roman = convertNumericPinyin(String(entry.roman));
  }
  if (!entry._source && entry.source) {
    entry._source = String(entry.source || '');
  }
  if (!entry.display_reading && entry.reading) {
    entry.display_reading = String(entry.reading || '');
  }
  if (!entry.entry_reading && entry.reading) {
    entry.entry_reading = String(entry.reading || '');
  }
  if (entry.display_headword) {
    entry.display_headword = String(entry.display_headword || '').trim();
    entry.headword = entry.display_headword;
    if (!entry.surface_form) entry.surface_form = entry.display_headword;
  }
  if (!entry.display_headword && entry.headword) {
    entry.display_headword = String(entry.headword || '').trim();
  }
  if (!entry.head && (entry.display_headword || entry.surface_form || entry.headword)) {
    entry.head = String(entry.display_headword || entry.surface_form || entry.headword || '');
  }
  if (!entry.match_kind && entry._match_kind) {
    entry.match_kind = String(entry._match_kind || '')
      .trim()
      .toLowerCase();
  }
  if (!entry._match_source && (entry.match_kind || entry._match_kind)) {
    entry._match_source = String(entry.match_kind || entry._match_kind || '')
      .trim()
      .toLowerCase();
  }
  var sourceTag = String(entry._source || entry.source || '')
    .trim()
    .toLowerCase();
  if (sourceTag === 'gemini') {
    var rawCommentary = String(entry._commentary || entry.commentary || '').trim();
    if (rawCommentary && entry._commentary === undefined) {
      entry._commentary = rawCommentary;
    }
    var rawLemma = String(entry._lemma || entry.lemma || entry.lemma_form || '').trim();
    if (rawLemma && entry._lemma === undefined) {
      entry._lemma = rawLemma;
    }
    if (!entry.morph_info && rawCommentary) {
      entry.morph_info = [rawCommentary];
    }
    if (!entry.morph_base && rawLemma) {
      entry.morph_base = rawLemma;
    }
  }
  if (entry.morph_info) {
    var initialMorphItems = Array.isArray(entry.morph_info) ? entry.morph_info : [entry.morph_info];
    entry.morph_info = mergeUniqueTextList(
      initialMorphItems.map(function (value) {
        return cleanMorphDisplayTags(value);
      }),
      []
    );
    if (!entry.morph_info.length) delete entry.morph_info;
  }
  if (entry.morph_base) {
    entry.morph_base = String(entry.morph_base || '').trim();
    if (!entry.morph_base) delete entry.morph_base;
  }
  var sensesFull = Array.isArray(entry.senses_full) ? entry.senses_full : [];
  var rawSenses = Array.isArray(entry.senses) ? entry.senses : [];
  if (!sensesFull.length && rawSenses.length && rawSenses[0] && typeof rawSenses[0] === 'object') {
    sensesFull = rawSenses.slice();
  }
  if (!sensesFull.length && entry.glosses != null) {
    sensesFull = buildStructuredSensesFromRaw(entry.glosses, activeLang);
  }
  if (sensesFull.length) {
    var dedupedSensesFull = [];
    var seenSenseKeys = Object.create(null);
    for (var sfi = 0; sfi < sensesFull.length; sfi++) {
      var sense = sensesFull[sfi];
      var senseKey = '';
      if (sense && typeof sense === 'object') {
        if (sense.qualifier != null) {
          var qualifier = String(stripSwahiliBracketMarkup(sense.qualifier, activeLang) || '').trim();
          if (qualifier) sense.qualifier = qualifier;
          else delete sense.qualifier;
        }
        if (Array.isArray(sense.glosses)) {
          var seenGlosses = Object.create(null);
          var dedupedGlosses = [];
          for (var gi = 0; gi < sense.glosses.length; gi++) {
            var gloss = String(stripSwahiliBracketMarkup(sense.glosses[gi] || '', activeLang) || '').trim();
            if (!gloss || seenGlosses[gloss]) continue;
            seenGlosses[gloss] = true;
            dedupedGlosses.push(gloss);
          }
          sense.glosses = dedupedGlosses;
          senseKey = dedupedGlosses.join('\u0001');
        } else {
          senseKey = String(
            stripSwahiliBracketMarkup(sense.gloss || sense.text || '', activeLang) || ''
          ).trim();
        }
      } else {
        senseKey = String(stripSwahiliBracketMarkup(sense || '', activeLang) || '').trim();
      }
      if (!senseKey || seenSenseKeys[senseKey]) continue;
      seenSenseKeys[senseKey] = true;
      dedupedSensesFull.push(sense);
    }
    sensesFull = dedupedSensesFull;
    entry.senses_full = sensesFull;
  }
  var flatSenses = sensesFull.length
    ? flattenCanonicalSenses(sensesFull, activeLang)
    : flattenCanonicalSenses(rawSenses, activeLang);
  if (flatSenses.length) {
    entry.senses = flatSenses;
  }
  if (entry.morph_info) {
    var morphItems = Array.isArray(entry.morph_info) ? entry.morph_info : [entry.morph_info];
    entry.morph_info = mergeUniqueTextList(
      morphItems.map(function (value) {
        return cleanMorphDisplayTags(stripSwahiliBracketMarkup(value, activeLang));
      }),
      []
    );
    if (!entry.morph_info.length) delete entry.morph_info;
  }
  if (entry.note != null) {
    var cleanedNote = String(stripSwahiliBracketMarkup(entry.note, activeLang) || '').trim();
    if (cleanedNote) entry.note = cleanedNote;
    else delete entry.note;
  }
  if (entry.etymology != null) {
    var cleanedEtymology = String(stripSwahiliBracketMarkup(entry.etymology, activeLang) || '').trim();
    if (cleanedEtymology) entry.etymology = cleanedEtymology;
    else delete entry.etymology;
  }
  if (entry.grammar != null) {
    var cleanedGrammar = String(stripSwahiliBracketMarkup(entry.grammar, activeLang) || '').trim();
    if (cleanedGrammar) entry.grammar = cleanedGrammar;
    else delete entry.grammar;
  }

  // Convert numeric pinyin inside gloss brackets for CC-CEDICT entries only.
  // e.g. "see 拜拜[bai2 bai2]" → "see 拜拜[bài bài]"
  var _entrySource = String(entry._source || entry.source || '').toLowerCase();
  if (_entrySource.indexOf('cc-cedict') !== -1 || _entrySource.indexOf('cedict') !== -1) {
    if (Array.isArray(entry.senses)) {
      for (var _si = 0; _si < entry.senses.length; _si++) {
        var _sense = entry.senses[_si];
        if (_sense && Array.isArray(_sense.glosses)) {
          for (var _gi = 0; _gi < _sense.glosses.length; _gi++) {
            _sense.glosses[_gi] = convertNumericPinyinInGloss(String(_sense.glosses[_gi] || ''));
          }
        } else if (typeof _sense === 'string') {
          entry.senses[_si] = convertNumericPinyinInGloss(_sense);
        }
      }
    }
    if (Array.isArray(entry.senses_full)) {
      for (var _sfi = 0; _sfi < entry.senses_full.length; _sfi++) {
        var _sfSense = entry.senses_full[_sfi];
        if (_sfSense && Array.isArray(_sfSense.glosses)) {
          for (var _sfgi = 0; _sfgi < _sfSense.glosses.length; _sfgi++) {
            _sfSense.glosses[_sfgi] = convertNumericPinyinInGloss(String(_sfSense.glosses[_sfgi] || ''));
          }
        }
      }
    }
  }
  var rawForms = entry.forms;
  var forms = rawForms && typeof rawForms === 'object' && !Array.isArray(rawForms) ? rawForms : {};
  var formRows = normalizeCanonicalFormRows(Array.isArray(rawForms) ? rawForms : forms.rows, activeLang);
  if (!formRows.length && entry._forms_raw) {
    try {
      formRows = normalizeCanonicalFormRows(JSON.parse(entry._forms_raw), activeLang);
    } catch (_) {}
  }
  if (!formRows.length && entry._forms_json) {
    try {
      formRows = normalizeCanonicalFormRows(JSON.parse(entry._forms_json), activeLang);
    } catch (_) {}
  }
  if (formRows.length) {
    forms.rows = formRows;
  }
  if (Object.keys(forms).length) {
    entry.forms = forms;
  }
  return entry;
}
export function normalizeCanonicalEntryStore(entryStore) {
  var keys = Object.keys(entryStore || {});
  for (var i = 0; i < keys.length; i++) {
    normalizeCanonicalEntryRuntime(entryStore[keys[i]]);
  }
  return entryStore;
}
export function getEntryHanjaFormsByRules(entry) {
  var e = entry || {};
  var forms = e.forms && typeof e.forms === 'object' && !Array.isArray(e.forms) ? e.forms : {};
  var rows = Array.isArray(forms.rows) ? forms.rows : [];
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    var word = Array.isArray(row) ? String(row[0] || '').trim() : String((row && row.word) || '').trim();
    var tagsStr = Array.isArray(row)
      ? String(row[1] || '')
      : String((row && (row.commentary || row.tags)) || '');
    if (!word || seen[word]) continue;
    var tags = tagsStr ? tagsStr.split(';') : [];
    for (var t = 0; t < tags.length; t++) {
      var tag = tags[t].trim().toLowerCase();
      if (tag === 'hanja' || tag === 'cjk' || tag === 'sinitic') {
        seen[word] = true;
        out.push(word);
        break;
      }
    }
  }
  return out;
}
export function getEntryHangeulFormsByRules(entry) {
  var e = entry || {};
  var forms = e.forms && typeof e.forms === 'object' && !Array.isArray(e.forms) ? e.forms : {};
  var rows = Array.isArray(forms.rows) ? forms.rows : [];
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    var word = Array.isArray(row) ? String(row[0] || '').trim() : String((row && row.word) || '').trim();
    var tagsStr = Array.isArray(row)
      ? String(row[1] || '')
      : String((row && (row.commentary || row.tags)) || '');
    if (!word || seen[word]) continue;
    var tags = tagsStr ? tagsStr.split(';') : [];
    for (var t = 0; t < tags.length; t++) {
      if (tags[t].trim().toLowerCase() === 'hangeul') {
        seen[word] = true;
        out.push(word);
        break;
      }
    }
  }
  return out;
}
export function etymKey(entry) {
  return window.DictionaryEngine && window.DictionaryEngine.etymKey
    ? window.DictionaryEngine.etymKey(entry || {})
    : 't:' + String((entry && entry.etymology) || '');
}
export function hasExplicitEtymology(entry) {
  var e = entry || {};
  var etymText = String(e.etymology || '').trim();
  var etymNum = Number(e.etymology_number || 0);
  return !!etymText || (isFinite(etymNum) && etymNum > 0);
}
export function buildEntryFallbackSignature(entry) {
  var e = entry || {};
  // Ensure lazy-parsed entries are hydrated before reading senses
  if (e._glosses_raw && window.DictionaryEngine && window.DictionaryEngine._hydrateEntry) {
    window.DictionaryEngine._hydrateEntry(e);
  }
  var head = String(e.headword || '').trim();
  var posRaw = String(e.pos_raw || e.pos || '').trim();
  var reading = String(e.reading || '').trim();
  var senses = Array.isArray(e.senses) ? e.senses : [];
  var firstSense = senses.length ? String(senses[0] || '').trim() : '';
  var sensesFull = Array.isArray(e.senses_full) ? e.senses_full : [];
  var firstSenseTags = '';
  if (sensesFull.length && sensesFull[0] && typeof sensesFull[0] === 'object') {
    var tags = sensesFull[0].tags;
    if (Array.isArray(tags) && tags.length) {
      firstSenseTags = tags
        .map(function (t) {
          return String(t || '').trim();
        })
        .filter(Boolean)
        .join('|');
    }
  }
  return [head, posRaw, reading, firstSense, firstSenseTags].join('\u241f');
}
export function entryGroupBucketKey(entry) {
  var base = etymKey(entry);
  // Language-agnostic fallback: compact TSV rows often have no explicit
  // etymology metadata (base = "t:"). Preserve row-level separation
  // so unrelated homographs do not collapse into one mixed entry block.
  if (base === 't:' && !hasExplicitEtymology(entry)) {
    return base + '|' + buildEntryFallbackSignature(entry);
  }
  return base;
}
export function attachWiktForms(target, surface, entries) {
  var chosen = entries && entries.length ? entries[0] : null;
  if (!chosen) return;
  // Ensure entries are hydrated (lazy gloss parse)
  for (var hi = 0; hi < entries.length; hi++) _ensureEntryHydrated(entries[hi]);
  var ipaVariants = chosen.ipa_variants || [];
  if (ipaVariants && ipaVariants.length) target.ipa_variants = ipaVariants;
  var audioUrls = chosen.audio_urls || [];
  if (audioUrls && audioUrls.length) target.audio_urls = audioUrls;
  var allGroups = [];
  var hasNormalizedMatch = !!target.normalized_match;
  for (var i = 0; i < (entries || []).length; i++) {
    var e = entries[i] || {};
    var sensesFull = Array.isArray(e.senses_full) ? e.senses_full : [];
    if (!sensesFull.length) continue;
    var rowHeadword = getEntryDisplayHeadword(e);
    var baseHeadword = String(e.lemma_headword || e.morph_base || '').trim();
    var rowReading = String(e.display_reading || e.reading || '').trim();
    var isFormMatch = getEntryMatchKind(e) === 'form';
    var pg = {
      headword: rowHeadword || baseHeadword || '',
      base_headword: baseHeadword,
      is_form_match: isFormMatch,
      reading: rowReading,
      pos: abbreviatePos(e.pos_raw || e.pos || ''),
      senses: sensesFull,
      normalized_match: !!e.normalized_match,
      // When the entry has _decomp_surface_form (lemma override match with a
      // flipped headword), store the entry object directly as the ref so that
      // reader_wikt.js receives the modified display_headword and
      // _decomp_surface_form fields — resolveEntryRef passes objects through
      // unchanged, bypassing the global entry store.
      _entryRef: e._decomp_surface_form ? e : _entryRefKey(e)
    };
    if (pg.normalized_match) hasNormalizedMatch = true;
    var pgMorphInfo = Array.isArray(e.morph_info)
      ? e.morph_info
          .slice()
          .map(function (v) {
            return String(v || '').trim();
          })
          .filter(Boolean)
      : e.morph_info
        ? [String(e.morph_info).trim()]
        : [];
    if (pgMorphInfo.length) {
      pg.morph_info = pgMorphInfo;
    }
    var pgMorphBase = String(e.morph_base || '').trim();
    if (pgMorphBase) {
      pg.morph_base = pgMorphBase;
    }
    if (e.grammar) {
      pg.grammar = String(e.grammar);
    }
    var hanjaForms = getEntryHanjaFormsByRules(e);
    if (hanjaForms.length) {
      pg.hanja_forms = hanjaForms;
    }
    var hangeulForms = getEntryHangeulFormsByRules(e);
    if (hangeulForms.length) {
      pg.hangeul_forms = hangeulForms;
    }
    var altForms = Array.isArray(e.alt_forms) ? e.alt_forms : [];
    if (altForms.length) {
      pg.alt_forms = altForms.slice();
    }
    var group = {
      headword: pg.headword || String(surface || '').trim() || '',
      reading: rowReading,
      etym_key: entryGroupBucketKey(e),
      pos_groups: [pg],
      _entryRef: e._decomp_surface_form ? e : _entryRefKey(e)
    };
    var etym = String(e.etymology || '');
    if (etym) group.etymology = etym;
    if (altForms.length) group.alt_forms = altForms.slice();
    if (Array.isArray(e.synonyms) && e.synonyms.length) group.synonyms = mergeWordLists(e.synonyms);
    if (Array.isArray(e.antonyms) && e.antonyms.length) group.antonyms = mergeWordLists(e.antonyms);
    if (Array.isArray(e.derived) && e.derived.length) group.derived = mergeWordLists(e.derived);
    if (Array.isArray(e.related) && e.related.length) group.related = mergeWordLists(e.related);
    allGroups.push(group);
  }
  if (allGroups.length) target.entry_groups = allGroups;
  if (chosen.senses_full) target.senses_full = chosen.senses_full;
  if (hasNormalizedMatch) target.normalized_match = true;
  else if (Object.prototype.hasOwnProperty.call(target, 'normalized_match')) delete target.normalized_match;
}
export function buildWiktG2P(word, engine, fallbackRoman) {
  var entry = engine ? engine.lookup(word) : null;
  var ipa = '';
  var ipaVariants = [];
  if (entry) {
    ipa = entry.reading || '';
    ipaVariants = entry.ipa_variants || [];
  }
  if (!ipa) ipa = String(fallbackRoman || '');
  return {
    overall_roman: ipa,
    syllables: [],
    ipa_variants: ipaVariants
  };
}
