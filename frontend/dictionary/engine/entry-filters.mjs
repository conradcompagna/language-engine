import { internString, normalizePos } from './normalization.mjs';
import { normalizationState } from './normalization.state.mjs';
export function normalizeVietnameseXposTag(rawTag) {
  return String(rawTag || '').trim();
}
export function splitVietnameseXposTags(rawXpos) {
  var text = String(rawXpos || '').trim();
  if (!text) return [];
  if (text.indexOf('+') < 0) return [text];
  var parts = text.split('+');
  var out = [];
  for (var i = 0; i < parts.length; i++) {
    var part = String(parts[i] || '').trim();
    if (part) out.push(part);
  }
  return out;
}
export function normalizeVietnameseXposTags(rawTags) {
  var out = [];
  var seen = Object.create(null);
  var src;
  if (Array.isArray(rawTags)) src = rawTags;
  else src = splitVietnameseXposTags(rawTags);
  for (var i = 0; i < src.length; i++) {
    var tag = normalizeVietnameseXposTag(src[i]);
    if (!tag || seen[tag]) continue;
    seen[tag] = true;
    out.push(tag);
  }
  return out;
}
export function buildVietnameseAllowedPosMap(rawTags) {
  var tags = normalizeVietnameseXposTags(rawTags);
  var allowed = Object.create(null);
  var hasMapped = false;
  for (var i = 0; i < tags.length; i++) {
    var mapped = normalizationState.VIETNAMESE_XPOS_TO_WIKT_POS[tags[i]];
    if (mapped === undefined) continue;
    hasMapped = true;
    for (var mi = 0; mi < mapped.length; mi++) {
      var pos = String(mapped[mi] || '')
        .trim()
        .toLowerCase();
      if (pos) allowed[pos] = true;
    }
  }
  return {
    tags: tags,
    allowed: allowed,
    has_mapped: hasMapped
  };
}
export function toEngineDebugLineNo(raw) {
  var n = parseInt(raw || 0, 10);
  if (!isFinite(n) || n <= 0) return 0;
  return n;
}
export function buildEngineDebugEntryRef(entry) {
  var e = entry || {};
  return {
    line_no: toEngineDebugLineNo(e.__line_no) || null,
    headword: String(e.headword || '').trim(),
    pos_raw: String(e.pos_raw || e.pos || '').trim(),
    reading: String(e.reading || e.pinyin || '').trim()
  };
}
export function buildEngineDebugEntryRefs(entries, limit) {
  var max = parseInt(limit, 10);
  if (!isFinite(max) || max <= 0) max = 12;
  var out = [];
  var seen = Object.create(null);
  var list = Array.isArray(entries) ? entries : [];
  for (var i = 0; i < list.length; i++) {
    var ref = buildEngineDebugEntryRef(list[i]);
    var key = String(ref.line_no || '') + '\t' + ref.headword + '\t' + ref.pos_raw + '\t' + ref.reading;
    if (!key.trim() || seen[key]) continue;
    seen[key] = true;
    if (out.length < max) out.push(ref);
  }
  return out;
}
export function getLanguageRules(langCode) {
  var lang = String(langCode || '')
    .trim()
    .toLowerCase();
  return normalizationState.LANGUAGE_SPECIFIC_RULES[lang] || null;
}
export function applyLanguageFormRules(langCode, entry, formText, tags) {
  var rules = getLanguageRules(langCode);
  if (!rules || typeof rules.on_form_seen !== 'function') return;
  rules.on_form_seen(entry, formText, tags);
}
export function getLanguageFormIndexTexts(langCode, formText, tags) {
  var base = String(formText || '').trim();
  if (!base) return [];
  var rules = getLanguageRules(langCode);
  if (!rules || typeof rules.get_form_index_texts !== 'function') return [base];
  var raw = rules.get_form_index_texts(base, tags || []);
  var list = Array.isArray(raw) ? raw : [raw];
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < list.length; i++) {
    var txt = String(list[i] || '').trim();
    if (!txt || seen[txt]) continue;
    seen[txt] = true;
    out.push(txt);
  }
  return out.length ? out : [base];
}
export function getLanguageUposExtraPos(langCode, uposTag) {
  var rules = getLanguageRules(langCode);
  if (!rules || !rules.upos_extra_pos) return [];
  var tag = String(uposTag || '')
    .trim()
    .toUpperCase();
  if (!tag) return [];
  var raw = rules.upos_extra_pos[tag];
  var list = Array.isArray(raw) ? raw : raw ? [raw] : [];
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < list.length; i++) {
    var txt = String(list[i] || '').trim();
    if (!txt || seen[txt]) continue;
    seen[txt] = true;
    out.push(txt);
  }
  return out;
}
export function splitMorphTags(rawMorph) {
  var out = [];
  var seen = Object.create(null);
  var src = Array.isArray(rawMorph) ? rawMorph : rawMorph ? [rawMorph] : [];
  for (var i = 0; i < src.length; i++) {
    var chunk = String(src[i] == null ? '' : src[i]).toLowerCase();
    if (!chunk) continue;
    var parts = chunk.split(/[;|,]/);
    for (var j = 0; j < parts.length; j++) {
      var tag = String(parts[j] || '').trim();
      if (!tag || seen[tag]) continue;
      seen[tag] = true;
      out.push(tag);
    }
  }
  return out;
}
export function buildAlwaysFilteredPosMap(baseMap, langCode) {
  var out = Object.create(null);
  var src = baseMap || normalizationState.ALWAYS_FILTERED_POS;
  for (var key in src) {
    if (!Object.prototype.hasOwnProperty.call(src, key)) continue;
    var tag = String(key || '')
      .trim()
      .toLowerCase();
    if (!tag) continue;
    out[tag] = !!src[key];
  }
  var lang = String(langCode || '')
    .trim()
    .toLowerCase();
  if (
    src === normalizationState.ALWAYS_FILTERED_POS &&
    normalizationState.CHARACTER_FILTER_EXEMPT_CJK_LANGS[lang]
  ) {
    delete out['character'];
  }
  return out;
}
export function hasAlwaysFilteredMorphTag(entry) {
  var morphTags = splitMorphTags(entry && entry.morph_info);
  for (var i = 0; i < morphTags.length; i++) {
    if (normalizationState.ALWAYS_FILTERED_MORPH_TAGS[morphTags[i]]) return true;
  }
  return false;
}

// Returns a shallow copy of the entry with pos_raw overridden if a morph tag
// indicates a derivational reclassification (e.g. "noun-from-verb" means the
// entry is a noun despite being stored under a verb headword).
export function applyMorphPosReclassification(entry) {
  var morphTags = splitMorphTags(entry && entry.morph_info);
  for (var i = 0; i < morphTags.length; i++) {
    var tag = morphTags[i];
    // "noun-from-verb", "noun from verb", "noun_from_verb", etc.
    if (/\bnoun\b.{0,10}\bverb\b/.test(tag)) {
      var copy = Object.assign({}, entry);
      copy.pos_raw = 'noun';
      copy._pos_reclassified = true;
      return copy;
    }
  }
  return entry;
}
export function applyMorphPosReclassificationToList(entries) {
  var out = [];
  for (var i = 0; i < entries.length; i++) {
    out.push(applyMorphPosReclassification(entries[i]));
  }
  return out;
}
export function splitEntriesByAlwaysFiltered(entries, alwaysFilteredPos) {
  var baseEntries = entries ? entries.slice() : [];
  if (!baseEntries.length) return [[], []];
  var posMap = alwaysFilteredPos || Object.create(null);
  var primary = [];
  var other = [];
  for (var i = 0; i < baseEntries.length; i++) {
    var entry = baseEntries[i] || {};
    var posRaw = String(entry.pos_raw || entry.pos || '')
      .trim()
      .toLowerCase();
    if (posMap[posRaw] || hasAlwaysFilteredMorphTag(entry)) other.push(baseEntries[i]);
    else primary.push(baseEntries[i]);
  }
  // Only show always-filtered entries if they are the ONLY entries — i.e. nothing
  // else exists to display. As soon as there is at least one non-filtered entry,
  // always-filtered entries remain hidden in the dropdown regardless of later
  // fallbacks in the POS filter.
  if (!primary.length) return [baseEntries, []];
  return [primary, other];
}
export function isKoreanHanjaDropdownEntry(entry) {
  if (!entry || typeof entry !== 'object') return false;
  var pos = String(entry.pos_raw || entry.pos || '')
    .trim()
    .toLowerCase();
  if (pos === 'syl' || pos === 'syllable') return true;
  var morphTags = splitMorphTags(entry.morph_info);
  for (var i = 0; i < morphTags.length; i++) {
    var tag = morphTags[i];
    if (tag === 'hangeul' || tag === 'eumhun' || tag === 'syl' || tag === 'syllable') {
      return true;
    }
  }
  return false;
}
export function normalizeDedupKey(text) {
  var norm = String(text || '');
  if (norm.normalize) norm = norm.normalize('NFKC');
  norm = norm.replace(/\s+/g, ' ').trim();
  return norm.toLowerCase();
}
export function dedupePreserveOrder(values) {
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < values.length; i++) {
    var text = String(values[i] || '').trim();
    if (!text) continue;
    var key = normalizeDedupKey(text);
    if (!key || seen[key]) continue;
    seen[key] = true;
    out.push(text);
  }
  return out;
}
export function dedupeSemicolonChunks(text) {
  var raw = String(text || '').trim();
  if (!raw || raw.indexOf(';') < 0) return raw;
  var chunks = raw.split(';').map(function (c) {
    return c.trim();
  });
  return dedupePreserveOrder(chunks).join('; ');
}
export function dedupeGlossList(glosses) {
  var cleaned = (glosses || []).map(function (g) {
    return dedupeSemicolonChunks(g);
  });
  return dedupePreserveOrder(cleaned);
}
export function repeatedLeadGlossKey(text) {
  var norm = String(text || '');
  if (norm.normalize) norm = norm.normalize('NFKC');
  norm = norm.replace(/\s+/g, ' ').trim();
  // Treat trailing colon variants as the same lead phrase.
  norm = norm.replace(/[:\uFF1A]\s*$/, '');
  return norm.toLowerCase();
}
export function dedupeSensesRuntime(flatSenses, sensesFull) {
  var outSensesFull = [];
  var seenSenseKeys = Object.create(null);
  var seenLeadGlossKeys = Object.create(null);
  var sfList = sensesFull || [];
  for (var i = 0; i < sfList.length; i++) {
    var sense = sfList[i];
    if (!sense || typeof sense !== 'object') continue;
    var glosses = sense.glosses;
    if (typeof glosses === 'string') glosses = [glosses];
    if (!Array.isArray(glosses)) continue;
    var dedupedGlosses = dedupeGlossList(glosses);
    if (!dedupedGlosses.length) continue;
    var leadGloss = dedupedGlosses[0];
    var leadKey = repeatedLeadGlossKey(leadGloss);
    // If a lead phrase repeats across senses, keep it only on first mention.
    if (leadKey && seenLeadGlossKeys[leadKey] && dedupedGlosses.length > 1) {
      dedupedGlosses = dedupedGlosses.slice(1);
    }
    if (leadKey && !seenLeadGlossKeys[leadKey]) {
      seenLeadGlossKeys[leadKey] = true;
    }
    if (!dedupedGlosses.length) continue;
    var senseCopy = {};
    for (var k in sense) {
      if (Object.prototype.hasOwnProperty.call(sense, k)) senseCopy[k] = sense[k];
    }
    senseCopy.glosses = dedupedGlosses;
    var senseKey = dedupedGlosses
      .map(function (g) {
        return normalizeDedupKey(g);
      })
      .join('\t');
    if (!senseKey || seenSenseKeys[senseKey]) continue;
    seenSenseKeys[senseKey] = true;
    outSensesFull.push(senseCopy);
  }
  if (outSensesFull.length) {
    var derivedFlat = [];
    for (var j = 0; j < outSensesFull.length; j++) {
      var gs = outSensesFull[j].glosses;
      if (Array.isArray(gs) && gs.length) derivedFlat.push(gs.join('; '));
    }
    return {
      flat: dedupeGlossList(derivedFlat),
      full: outSensesFull
    };
  }
  var outFlat = dedupeGlossList(flatSenses || []);
  return {
    flat: outFlat,
    full: outFlat.map(function (g) {
      return {
        glosses: [g]
      };
    })
  };
}
export function parseTsvRowCompact(row, headword, glossesRaw) {
  if (!glossesRaw) return null;
  var posRaw = internString((row.pos || row.pos_raw || '').trim());
  var pos = internString(normalizePos(posRaw));
  var reading = (row.romanization || '').trim();
  var etymology = (row.etymology || '').trim();
  var etymNumRaw = (row.etymology_number || '').trim();
  var etymologyNumber = /^\d+$/.test(etymNumRaw) ? parseInt(etymNumRaw, 10) : 0;
  // Lazy gloss parsing: store raw JSON string, parse on first access.
  // This avoids JSON.parse + dedupeSensesRuntime for entries never looked up.
  var entry = {
    headword: headword,
    pos: pos,
    pos_raw: posRaw,
    _glosses_raw: glossesRaw,
    // senses / senses_full are hydrated lazily via hydrateEntry()
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
