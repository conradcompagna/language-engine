/**
 * dictionary_engine.js - Client-side dictionary lookup engine.
 *
 * Port of wiktionary_general/dictionary.py (TSV path + lookup/fill/filter API).
 * Keeps method names compatible with Python-facing call sites.
 */
(function() {
  "use strict";

  // ── Memory optimization: shared singletons & interning ──
  var EMPTY_ARRAY = Object.freeze([]);
  var EMPTY_STRING = "";

  // Intern table for repeated short strings (POS labels, morph tags).
  // V8 already interns object keys, but these are used as *values*.
  var _internTable = Object.create(null);
  function internString(s) {
    if (!s) return EMPTY_STRING;
    var existing = _internTable[s];
    if (existing !== undefined) return existing;
    _internTable[s] = s;
    return s;
  }

  // Intern table for morph tag arrays — common patterns like ["stem"], ["plural"] etc.
  var _morphArrayTable = Object.create(null);
  function internMorphArray(tags) {
    if (!tags || !tags.length) return EMPTY_ARRAY;
    var key = tags.join(";");
    var existing = _morphArrayTable[key];
    if (existing !== undefined) return existing;
    // Intern individual tag strings too
    var interned = new Array(tags.length);
    for (var i = 0; i < tags.length; i++) {
      interned[i] = internString(tags[i]);
    }
    Object.freeze(interned);
    _morphArrayTable[key] = interned;
    return interned;
  }

  var POS_LABELS = {
    "noun": "n", "verb": "v", "adj": "adj", "adv": "adv",
    "pron": "pron", "prep": "prep", "postp": "postp", "conj": "conj",
    "det": "det", "num": "num", "intj": "intj", "particle": "ptcl",
    "classifier": "clf", "prefix": "pfx", "suffix": "sfx", "affix": "afx",
    "infix": "ifx", "interfix": "itfx", "circumfix": "circfx",
    "combining_form": "comb", "contraction": "contr", "phrase": "phr",
    "proverb": "prov", "prep_phrase": "prep.phr", "character": "char",
    "name": "name", "romanization": "rom", "root": "root",
    "article": "art", "punct": "punct", "symbol": "sym",
    "counter": "ctr", "adnominal": "adn", "circumpos": "cpos",
    "syllable": "syl", "[]": "unk"
  };

  function normalizePos(raw) {
    return POS_LABELS[raw] || raw;
  }

  function isPersianLanguageCode(langValue) {
    var lang = String(langValue || "").trim().toLowerCase();
    return lang === "fa" || lang === "persian" || lang.indexOf("fa-") === 0;
  }

  function isKoreanLanguageCode(langValue) {
    var lang = String(langValue || "").trim().toLowerCase();
    return lang === "ko" || lang === "korean" || lang.indexOf("ko-") === 0;
  }

  function getLemmaHintTexts(rawHint, langCode) {
    var out = [];
    var seen = Object.create(null);
    function pushText(raw) {
      var txt = String(raw || "").trim();
      if (!txt || seen[txt]) return;
      seen[txt] = true;
      out.push(txt);
    }
    if (rawHint && typeof rawHint === "object" && !Array.isArray(rawHint)) {
      var rawVariants = Array.isArray(rawHint.variants) ? rawHint.variants : [];
      for (var i = 0; i < rawVariants.length; i++) pushText(rawVariants[i]);
      if (!out.length && isPersianLanguageCode(langCode)) {
        var rawText = String(rawHint.text || rawHint.lemma || "").trim();
        if (rawText && rawText.indexOf("#") >= 0) {
          var splitParts = rawText.split("#").map(function(part) { return String(part || "").trim(); }).filter(Boolean);
          for (var j = 0; j < splitParts.length; j++) pushText(splitParts[j]);
        }
      }
      if (!out.length) pushText(rawHint.text || rawHint.lemma || "");
      return out;
    }
    pushText(rawHint || "");
    return out;
  }

  var AFFIX_MARKER_EQUIVALENTS = "\uFEFF\u061C\u200E\u200F\u200C\u202A\u202B\u202C\u202D\u202E\u2066\u2067\u2068\u2069\u05BE\u05F3\u2012\u25CC'.^\u3320\u2810\u2818\u2830\u211E\u2205&(),\u00A9\u3030";
  var LOOKUP_INVISIBLE_COMPARISON_RE = /[\u061C\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFE00-\uFE0F\uFEFF]|\uDB40[\uDD00-\uDDEF]/g;

  var NOUN_AFFIX_POS = [
    "suffix",
    "prefix",
    "affix",
    "infix",
    "interfix",
    "circumfix",
    "combining_form"
  ];
  var LANGUAGE_SPECIFIC_RULES = {
    ja: {
      upos_extra_pos: {
        // "AUX": ["suffix"],
        // "CCONJ": ["suffix"],
        // "SCONJ": ["suffix"]
      }
    },
    vi: {
      on_form_seen: function(entry, formText, tags) {
        var text = String(formText || "").trim();
        if (!text || !entry) return;
        var hasCjk = false;
        for (var i = 0; i < (tags || []).length; i++) {
          var tag = String(tags[i] || "").trim().toLowerCase();
          if (tag === "cjk" || tag === "sinitic") {
            hasCjk = true;
            break;
          }
        }
        if (!hasCjk) return;
        var existing = Array.isArray(entry.vietnamese_cjk_variants)
          ? entry.vietnamese_cjk_variants
          : [];
        if (!Array.isArray(entry.vietnamese_cjk_variants)) {
          entry.vietnamese_cjk_variants = existing;
        }
        if (existing.indexOf(text) < 0) existing.push(text);
      },
      get_entry_hanja_forms: function(entry) {
        var raw = (entry && entry.vietnamese_cjk_variants) || [];
        if (!Array.isArray(raw)) return [];
        var out = [];
        var seen = Object.create(null);
        for (var i = 0; i < raw.length; i++) {
          var txt = String(raw[i] || "").trim();
          if (!txt || seen[txt]) continue;
          seen[txt] = true;
          out.push(txt);
        }
        return out;
      }
    },
    ko: {
      get_form_index_texts: function(formText, tags) {
        var text = String(formText || "").trim();
        if (!text) return [];
        var isEumhun = false;
        for (var i = 0; i < (tags || []).length; i++) {
          var tag = String(tags[i] || "").trim().toLowerCase();
          if (tag === "eumhun") {
            isEumhun = true;
            break;
          }
        }
        if (!isEumhun) return [text];

        // Eumhun forms are often strings like "폐할 폐".
        // Index the final Hangul syllable used in running text.
        for (var ci = text.length - 1; ci >= 0; ci--) {
          var code = text.charCodeAt(ci);
          if (code >= 0xAC00 && code <= 0xD7A3) {
            return [text.charAt(ci)];
          }
        }
        for (var ti = text.length - 1; ti >= 0; ti--) {
          var tail = text.charAt(ti);
          if (tail.trim()) return [tail];
        }
        return [text];
      },
      on_form_seen: function(entry, formText, tags) {
        var text = String(formText || "").trim();
        if (!text || !entry) return;
        var hasHanja = false;
        var hasHangeul = false;
        for (var i = 0; i < (tags || []).length; i++) {
          var tag = String(tags[i] || "").trim().toLowerCase();
          if (tag === "hanja") {
            hasHanja = true;
          } else if (tag === "hangeul") {
            hasHangeul = true;
          }
        }
        if (hasHanja) {
          var existing = Array.isArray(entry.korean_hanja_variants)
            ? entry.korean_hanja_variants
            : [];
          if (!Array.isArray(entry.korean_hanja_variants)) {
            entry.korean_hanja_variants = existing;
          }
          if (existing.indexOf(text) < 0) existing.push(text);
        }
        if (hasHangeul) {
          var hExisting = Array.isArray(entry.korean_hangeul_variants)
            ? entry.korean_hangeul_variants
            : [];
          if (!Array.isArray(entry.korean_hangeul_variants)) {
            entry.korean_hangeul_variants = hExisting;
          }
          if (hExisting.indexOf(text) < 0) hExisting.push(text);
        }
      },
      get_entry_hanja_forms: function(entry) {
        var raw = (entry && entry.korean_hanja_variants) || [];
        if (!Array.isArray(raw)) return [];
        var out = [];
        var seen = Object.create(null);
        for (var i = 0; i < raw.length; i++) {
          var txt = String(raw[i] || "").trim();
          if (!txt || seen[txt]) continue;
          seen[txt] = true;
          out.push(txt);
        }
        return out;
      },
      get_entry_hangeul_forms: function(entry) {
        var raw = (entry && entry.korean_hangeul_variants) || [];
        if (!Array.isArray(raw)) return [];
        var out = [];
        var seen = Object.create(null);
        for (var i = 0; i < raw.length; i++) {
          var txt = String(raw[i] || "").trim();
          if (!txt || seen[txt]) continue;
          seen[txt] = true;
          out.push(txt);
        }
        return out;
      }
    }
  };

  var UPOS_TO_KAIKKI_POS = {
    "NOUN":  ["noun", "classifier", "name", "contraction", "counter"].concat(NOUN_AFFIX_POS),
    "VERB":  ["verb"],
    "ADJ":   ["adj", "adnominal"],
    "ADV":   ["adv"],
    "PROPN": ["name", "noun"].concat(NOUN_AFFIX_POS),
    "ADP":   ["prep", "postp", "prep_phrase", "particle", "circumpos"],
    "AUX":   ["verb"],
    "CCONJ": ["conj"],
    "SCONJ": ["conj"],
    "DET":   ["det", "article", "adnominal"],
    "PRON":  ["pron"],
    "NUM":   ["num", "counter"],
    "PART":  ["particle"],
    "INTJ":  ["intj"],
    "PUNCT": ["punct", "symbol"],
    "SYM":   ["symbol", "punct"],
    "X":     ["syllable", "[]"]
  };

  var FILTER_EXEMPT_POS = { "proverb": true, "phrase": true, "prep_phrase": true };

  var ALWAYS_FILTERED_POS = {
    "character": true, "romanization": true, "root": true,
    "syllable": true,
    "punct": true, "symbol": true
  };

  var ALWAYS_FILTERED_MORPH_TAGS = {
    // "alternative": true,
    // "redirect": true,
    // "hangeul": true,
    // "eumhun": true,
    // "syllable": true,
    // "syl": true
  };

  var CHARACTER_FILTER_EXEMPT_CJK_LANGS = {
    "zh": true, "zh-hant": true, "ja": true, "ko": true,
    "yue": true, "wuu": true, "lzh": true
  };

  // Korean KAIST XPOS -> allowed Wiktionary POS buckets.
  // Keys mirror the previous Korean-specific pipeline.
  var KOREAN_XPOS_TO_WIKT_POS = {
    "ncn":  ["noun", "name", "suffix", "counter"].concat(NOUN_AFFIX_POS),
    "ncpa": ["noun", "verb"],
    "ncps": ["noun", "adj", "adv"],
    "nbn":  ["noun"],
    "nbu":  ["noun", "counter"],
    "nnc":  ["num", "counter"],
    "nno":  ["num", "counter"],
    "npd":  ["pron"],
    "npp":  ["pron"],
    "nq":   ["name", "noun"],
    "pvg":  ["verb"],
    "pvd":  ["verb"],
    "paa":  ["adj"],
    "pad":  ["det", "adnominal"],
    "px":   ["verb", "adj"],
    "ecc":  ["suffix", "particle", "conj"],
    "ecs":  ["suffix", "particle"],
    "ecx":  ["suffix", "particle"],
    "ef":   ["suffix", "particle"],
    "ep":   ["suffix", "particle"],
    "etm":  ["suffix", "particle"],
    "etn":  ["suffix", "particle"],
    "jca":  ["particle", "postp", "circumpos"],
    "jcc":  ["particle", "postp", "circumpos"],
    "jcj":  ["particle", "postp", "circumpos", "conj"],
    "jcm":  ["particle", "postp", "circumpos"],
    "jco":  ["particle", "postp", "circumpos"],
    "jcr":  ["particle", "postp", "circumpos"],
    "jcs":  ["particle", "postp", "circumpos"],
    "jct":  ["particle", "postp", "circumpos"],
    "jp":   ["particle", "postp", "circumpos"],
    "jcv":  ["particle", "postp", "circumpos"],
    "jxc":  ["particle", "postp", "circumpos"],
    "jxf":  ["particle", "postp", "circumpos"],
    "jxt":  ["particle", "postp", "circumpos"],
    "mad":  ["adv"],
    "mag":  ["adv"],
    "maj":  ["adv", "conj"],
    "mma":  ["det", "adnominal"],
    "mmd":  ["det", "adnominal"],
    "xp":   ["prefix", "suffix", "affix"],
    "xsa":  ["suffix", "adj", "affix"],
    "xsm":  ["suffix", "adv", "affix"],
    "xsn":  ["suffix", "particle", "affix"],
    "xsv":  ["suffix", "verb", "affix"],
    "ii":   ["intj"],
    "sf":   ["syllable", "[]", "contraction"],
    "sl":   ["syllable", "[]", "contraction"],
    "sp":   ["syllable", "[]", "contraction"],
    "sr":   ["syllable", "[]", "contraction"],
    "su":   ["syllable", "[]", "contraction"],
    "f":    ["syllable", "[]", "contraction"],
    "_":    ["syllable", "[]", "contraction"]
  };

  var KOREAN_XPOS_FILTER_EXEMPT_POS = {
    "phrase": true,
    "proverb": true,
    "prep_phrase": true
  };

  // Vietnamese XPOS -> allowed Wiktionary POS buckets.
  // Ported directly from vietnamese/dictionary.py.
  var VIETNAMESE_XPOS_TO_WIKT_POS = {
    "N":  ["noun"],
    "Np": ["name"],
    "Nc": ["classifier"],
    "Nu": ["classifier", "noun"],
    "Nb": ["noun"],
    "Ny": ["name", "noun"],
    "V":  ["verb"],
    "A":  ["adj"],
    "P":  ["pron"],
    "R":  ["adv"],
    "L":  ["det"],
    "M":  ["num"],
    "E":  ["prep"],
    "C":  ["conj"],
    "CC": ["conj"],
    "I":  ["intj"],
    "T":  ["particle"],
    "S":  ["affix", "prefix", "suffix", "combining_form"],
    "Y":  ["name", "noun"],
    "CH": ["punct", "symbol"],
    "X":  [],
    "_":  []
  };

  var VIETNAMESE_XPOS_FILTER_EXEMPT_POS = {
    "proverb": true,
    "phrase": true,
    "punct": true,
    "symbol": true
  };

  var VIETNAMESE_XPOS_ALWAYS_FILTERED_POS = {
    "character": true,
    "romanization": true
  };

  function normalizeAffixMarkers(text) {
    var result = "";
    for (var i = 0; i < text.length; i++) {
      if (AFFIX_MARKER_EQUIVALENTS.indexOf(text[i]) >= 0) {
        result += "-";
      } else {
        result += text[i];
      }
    }
    return result;
  }

  function applyLookupNormalizationLayer(text, langCode, phase) {
    var norm = String(text || "");
    var layer = window.DictionaryNormalizationLayer;
    if (!layer || typeof layer.normalizeLookupText !== "function") return norm;
    try {
      return String(layer.normalizeLookupText(norm, {
        langCode: String(langCode || "").trim().toLowerCase(),
        phase: String(phase || "lookup_key")
      }) || "");
    } catch (_e) {
      return norm;
    }
  }

  function stripInvisibleComparisonChars(text) {
    var src = String(text || "");
    var layer = window.DictionaryNormalizationLayer;
    if (layer && typeof layer.stripInvisibleComparisonChars === "function") {
      try {
        return String(layer.stripInvisibleComparisonChars(src) || "");
      } catch (_e) {}
    }
    return src.replace(LOOKUP_INVISIBLE_COMPARISON_RE, "");
  }

  function entryHasMorphTag(entry, tagText) {
    var target = String(tagText || "").trim().toLowerCase();
    if (!target) return false;
    var tags = splitMorphTags(entry && entry.morph_info);
    for (var i = 0; i < tags.length; i++) {
      if (tags[i] === target) return true;
    }
    return false;
  }

  function cloneEntryWithMorphTag(entry, tagText) {
    var tag = String(tagText || "").trim();
    if (!entry || !tag || entryHasMorphTag(entry, tag)) return entry;
    var clone = {};
    for (var k in entry) {
      if (Object.prototype.hasOwnProperty.call(entry, k)) clone[k] = entry[k];
    }
    var rawMorph = entry.morph_info;
    var morphInfo = Array.isArray(rawMorph) ? rawMorph.slice() : (rawMorph ? [String(rawMorph)] : []);
    morphInfo.push(tag);
    clone.morph_info = morphInfo;
    return clone;
  }

  function annotateLookupEntries(entries, queryText, langCode) {
    var src = Array.isArray(entries) ? entries : [];
    void queryText;
    void langCode;
    return src.length ? src.slice() : [];
  }

  function lookupKey(text, langCode) {
    var raw = String(text || "").trim();
    if (!raw) return "";
    var layer = window.DictionaryNormalizationLayer;
    return String(layer.normalizeLookupKeyText(raw, {
      langCode: String(langCode || "").trim().toLowerCase(),
      phase: "lookup_key"
    }) || "").trim();
  }

  function lookupKeys(text, langCode) {
    var raw = String(text || "").trim();
    if (!raw) return [];
    var layer = window.DictionaryNormalizationLayer;
    var key = String(layer.normalizeLookupKeyText(raw, {
      langCode: String(langCode || "").trim().toLowerCase(),
      phase: "lookup_keys"
    }) || "").trim();
    return key ? [key] : [];
  }

  function buildGraphemeSpanTable(text) {
    var value = String(text || "");
    if (!value) {
      var emptyBoundaryMap = Object.create(null);
      emptyBoundaryMap[0] = 0;
      return { spans: [], boundary_to_index: emptyBoundaryMap };
    }
    var segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
    var rows = Array.from(segmenter.segment(value));
    var spans = [];
    var boundaryToIndex = Object.create(null);
    boundaryToIndex[0] = 0;
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      var segmentText = String(row.segment || "");
      var start = parseInt(row.index, 10);
      if (!segmentText || !isFinite(start)) continue;
      var end = start + segmentText.length;
      var spanIndex = spans.length;
      boundaryToIndex[start] = spanIndex;
      spans.push({
        start: start,
        end: end,
        text: segmentText
      });
      boundaryToIndex[end] = spanIndex + 1;
    }
    boundaryToIndex[value.length] = spans.length;
    return {
      spans: spans,
      boundary_to_index: boundaryToIndex
    };
  }

  function normalizeKoreanXposTag(rawTag) {
    var tag = String(rawTag || "").trim().toLowerCase();
    if (!tag) return "";
    // Handle parser artifacts like "ecs." or "jxc,".
    return tag.replace(/^[^a-z0-9_]+|[^a-z0-9_]+$/g, "");
  }

  function normalizeKoreanXposTags(rawTags) {
    var out = [];
    var seen = Object.create(null);
    var src = Array.isArray(rawTags) ? rawTags : (rawTags ? [rawTags] : []);
    for (var i = 0; i < src.length; i++) {
      var tag = normalizeKoreanXposTag(src[i]);
      if (!tag || seen[tag]) continue;
      seen[tag] = true;
      out.push(tag);
    }
    return out;
  }

  function buildKoreanAllowedPosMap(rawTags) {
    var tags = normalizeKoreanXposTags(rawTags);
    var allowed = Object.create(null);
    var hasMapped = false;
    for (var i = 0; i < tags.length; i++) {
      var mapped = KOREAN_XPOS_TO_WIKT_POS[tags[i]];
      if (!mapped || !mapped.length) continue;
      hasMapped = true;
      for (var mi = 0; mi < mapped.length; mi++) {
        var pos = String(mapped[mi] || "").trim().toLowerCase();
        if (pos) allowed[pos] = true;
      }
    }
    return {
      tags: tags,
      allowed: allowed,
      has_mapped: hasMapped
    };
  }

  function normalizeVietnameseXposTag(rawTag) {
    return String(rawTag || "").trim();
  }

  function splitVietnameseXposTags(rawXpos) {
    var text = String(rawXpos || "").trim();
    if (!text) return [];
    if (text.indexOf("+") < 0) return [text];
    var parts = text.split("+");
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      var part = String(parts[i] || "").trim();
      if (part) out.push(part);
    }
    return out;
  }

  function normalizeVietnameseXposTags(rawTags) {
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

  function buildVietnameseAllowedPosMap(rawTags) {
    var tags = normalizeVietnameseXposTags(rawTags);
    var allowed = Object.create(null);
    var hasMapped = false;
    for (var i = 0; i < tags.length; i++) {
      var mapped = VIETNAMESE_XPOS_TO_WIKT_POS[tags[i]];
      if (mapped === undefined) continue;
      hasMapped = true;
      for (var mi = 0; mi < mapped.length; mi++) {
        var pos = String(mapped[mi] || "").trim().toLowerCase();
        if (pos) allowed[pos] = true;
      }
    }
    return {
      tags: tags,
      allowed: allowed,
      has_mapped: hasMapped
    };
  }

  function toEngineDebugLineNo(raw) {
    var n = parseInt(raw || 0, 10);
    if (!isFinite(n) || n <= 0) return 0;
    return n;
  }

  function buildEngineDebugEntryRef(entry) {
    var e = entry || {};
    return {
      line_no: toEngineDebugLineNo(e.__line_no) || null,
      headword: String(e.headword || "").trim(),
      pos_raw: String(e.pos_raw || e.pos || "").trim(),
      reading: String(e.reading || e.pinyin || "").trim()
    };
  }

  function buildEngineDebugEntryRefs(entries, limit) {
    var max = parseInt(limit, 10);
    if (!isFinite(max) || max <= 0) max = 12;
    var out = [];
    var seen = Object.create(null);
    var list = Array.isArray(entries) ? entries : [];
    for (var i = 0; i < list.length; i++) {
      var ref = buildEngineDebugEntryRef(list[i]);
      var key = String(ref.line_no || "") + "\t" + ref.headword + "\t" + ref.pos_raw + "\t" + ref.reading;
      if (!key.trim() || seen[key]) continue;
      seen[key] = true;
      if (out.length < max) out.push(ref);
    }
    return out;
  }

  function getLanguageRules(langCode) {
    var lang = String(langCode || "").trim().toLowerCase();
    return LANGUAGE_SPECIFIC_RULES[lang] || null;
  }

  function applyLanguageFormRules(langCode, entry, formText, tags) {
    var rules = getLanguageRules(langCode);
    if (!rules || typeof rules.on_form_seen !== "function") return;
    rules.on_form_seen(entry, formText, tags);
  }

  function getLanguageFormIndexTexts(langCode, formText, tags) {
    var base = String(formText || "").trim();
    if (!base) return [];
    var rules = getLanguageRules(langCode);
    if (!rules || typeof rules.get_form_index_texts !== "function") return [base];
    var raw = rules.get_form_index_texts(base, tags || []);
    var list = Array.isArray(raw) ? raw : [raw];
    var out = [];
    var seen = Object.create(null);
    for (var i = 0; i < list.length; i++) {
      var txt = String(list[i] || "").trim();
      if (!txt || seen[txt]) continue;
      seen[txt] = true;
      out.push(txt);
    }
    return out.length ? out : [base];
  }

  function getLanguageUposExtraPos(langCode, uposTag) {
    var rules = getLanguageRules(langCode);
    if (!rules || !rules.upos_extra_pos) return [];
    var tag = String(uposTag || "").trim().toUpperCase();
    if (!tag) return [];
    var raw = rules.upos_extra_pos[tag];
    var list = Array.isArray(raw) ? raw : (raw ? [raw] : []);
    var out = [];
    var seen = Object.create(null);
    for (var i = 0; i < list.length; i++) {
      var txt = String(list[i] || "").trim();
      if (!txt || seen[txt]) continue;
      seen[txt] = true;
      out.push(txt);
    }
    return out;
  }

  function splitMorphTags(rawMorph) {
    var out = [];
    var seen = Object.create(null);
    var src = Array.isArray(rawMorph) ? rawMorph : (rawMorph ? [rawMorph] : []);
    for (var i = 0; i < src.length; i++) {
      var chunk = String(src[i] == null ? "" : src[i]).toLowerCase();
      if (!chunk) continue;
      var parts = chunk.split(/[;|,]/);
      for (var j = 0; j < parts.length; j++) {
        var tag = String(parts[j] || "").trim();
        if (!tag || seen[tag]) continue;
        seen[tag] = true;
        out.push(tag);
      }
    }
    return out;
  }

  function buildAlwaysFilteredPosMap(baseMap, langCode) {
    var out = Object.create(null);
    var src = baseMap || ALWAYS_FILTERED_POS;
    for (var key in src) {
      if (!Object.prototype.hasOwnProperty.call(src, key)) continue;
      var tag = String(key || "").trim().toLowerCase();
      if (!tag) continue;
      out[tag] = !!src[key];
    }
    var lang = String(langCode || "").trim().toLowerCase();
    if (src === ALWAYS_FILTERED_POS && CHARACTER_FILTER_EXEMPT_CJK_LANGS[lang]) {
      delete out["character"];
    }
    return out;
  }

  function hasAlwaysFilteredMorphTag(entry) {
    var morphTags = splitMorphTags(entry && entry.morph_info);
    for (var i = 0; i < morphTags.length; i++) {
      if (ALWAYS_FILTERED_MORPH_TAGS[morphTags[i]]) return true;
    }
    return false;
  }

  // Returns a shallow copy of the entry with pos_raw overridden if a morph tag
  // indicates a derivational reclassification (e.g. "noun-from-verb" means the
  // entry is a noun despite being stored under a verb headword).
  function applyMorphPosReclassification(entry) {
    var morphTags = splitMorphTags(entry && entry.morph_info);
    for (var i = 0; i < morphTags.length; i++) {
      var tag = morphTags[i];
      // "noun-from-verb", "noun from verb", "noun_from_verb", etc.
      if (/\bnoun\b.{0,10}\bverb\b/.test(tag)) {
        var copy = Object.assign({}, entry);
        copy.pos_raw = "noun";
        copy._pos_reclassified = true;
        return copy;
      }
    }
    return entry;
  }

  function applyMorphPosReclassificationToList(entries) {
    var out = [];
    for (var i = 0; i < entries.length; i++) {
      out.push(applyMorphPosReclassification(entries[i]));
    }
    return out;
  }

  function splitEntriesByAlwaysFiltered(entries, alwaysFilteredPos) {
    var baseEntries = entries ? entries.slice() : [];
    if (!baseEntries.length) return [[], []];
    var posMap = alwaysFilteredPos || Object.create(null);
    var primary = [];
    var other = [];
    for (var i = 0; i < baseEntries.length; i++) {
      var entry = baseEntries[i] || {};
      var posRaw = String(entry.pos_raw || entry.pos || "").trim().toLowerCase();
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

  function isKoreanHanjaDropdownEntry(entry) {
    if (!entry || typeof entry !== "object") return false;
    var pos = String(entry.pos_raw || entry.pos || "").trim().toLowerCase();
    if (pos === "syl" || pos === "syllable") return true;

    var morphTags = splitMorphTags(entry.morph_info);
    for (var i = 0; i < morphTags.length; i++) {
      var tag = morphTags[i];
      if (tag === "hangeul" || tag === "eumhun" || tag === "syl" || tag === "syllable") {
        return true;
      }
    }
    return false;
  }

  function normalizeDedupKey(text) {
    var norm = String(text || "");
    if (norm.normalize) norm = norm.normalize("NFKC");
    norm = norm.replace(/\s+/g, " ").trim();
    return norm.toLowerCase();
  }

  function dedupePreserveOrder(values) {
    var out = [];
    var seen = Object.create(null);
    for (var i = 0; i < values.length; i++) {
      var text = String(values[i] || "").trim();
      if (!text) continue;
      var key = normalizeDedupKey(text);
      if (!key || seen[key]) continue;
      seen[key] = true;
      out.push(text);
    }
    return out;
  }

  function dedupeSemicolonChunks(text) {
    var raw = String(text || "").trim();
    if (!raw || raw.indexOf(";") < 0) return raw;
    var chunks = raw.split(";").map(function(c) { return c.trim(); });
    return dedupePreserveOrder(chunks).join("; ");
  }

  function dedupeGlossList(glosses) {
    var cleaned = (glosses || []).map(function(g) { return dedupeSemicolonChunks(g); });
    return dedupePreserveOrder(cleaned);
  }

  function repeatedLeadGlossKey(text) {
    var norm = String(text || "");
    if (norm.normalize) norm = norm.normalize("NFKC");
    norm = norm.replace(/\s+/g, " ").trim();
    // Treat trailing colon variants as the same lead phrase.
    norm = norm.replace(/[:\uFF1A]\s*$/, "");
    return norm.toLowerCase();
  }

  function dedupeSensesRuntime(flatSenses, sensesFull) {
    var outSensesFull = [];
    var seenSenseKeys = Object.create(null);
    var seenLeadGlossKeys = Object.create(null);
    var sfList = sensesFull || [];
    for (var i = 0; i < sfList.length; i++) {
      var sense = sfList[i];
      if (!sense || typeof sense !== "object") continue;
      var glosses = sense.glosses;
      if (typeof glosses === "string") glosses = [glosses];
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
      var senseKey = dedupedGlosses.map(function(g) { return normalizeDedupKey(g); }).join("\t");
      if (!senseKey || seenSenseKeys[senseKey]) continue;
      seenSenseKeys[senseKey] = true;
      outSensesFull.push(senseCopy);
    }
    if (outSensesFull.length) {
      var derivedFlat = [];
      for (var j = 0; j < outSensesFull.length; j++) {
        var gs = outSensesFull[j].glosses;
        if (Array.isArray(gs) && gs.length) derivedFlat.push(gs.join("; "));
      }
      return { flat: dedupeGlossList(derivedFlat), full: outSensesFull };
    }
    var outFlat = dedupeGlossList(flatSenses || []);
    return { flat: outFlat, full: outFlat.map(function(g) { return { glosses: [g] }; }) };
  }

  function parseTsvRowCompact(row, headword, glossesRaw) {
    if (!glossesRaw) return null;
    var posRaw = internString((row.pos || row.pos_raw || "").trim());
    var pos = internString(normalizePos(posRaw));
    var reading = (row.romanization || "").trim();
    var etymology = (row.etymology || "").trim();
    var etymNumRaw = (row.etymology_number || "").trim();
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
      etymology: etymology || EMPTY_STRING,
      etymology_number: etymologyNumber
    };
    var entryId = String(row.entry_id || "").trim();
    if (entryId) entry.entry_id = entryId;
    var explicitSource = String(row.source || row._source || "").trim();
    if (explicitSource) entry._source = explicitSource;
    var formsRaw = (row.forms || "").trim();
    if (formsRaw) entry._forms_json = formsRaw;
    return entry;
  }

  function parseTsvRowLegacy(row, headword, glossesRaw) {
    if (!glossesRaw) return null;
    var posRaw = internString((row.pos_raw || "").trim());
    var pos = internString(normalizePos(posRaw));
    var reading = (row.reading || "").trim();
    // Legacy format: store raw row data for lazy hydration
    var etymology = (row.etymology || "").trim();
    var etymNumRaw = (row.etymology_number || "").trim();
    var etymologyNumber = /^\d+$/.test(etymNumRaw) ? parseInt(etymNumRaw, 10) : 0;
    var entry = {
      headword: headword,
      pos: pos,
      pos_raw: posRaw,
      _glosses_raw: glossesRaw,
      _legacy_tags_raw: (row.tags || "").trim() || undefined,
      _legacy_row: row, // for splitList fields, hydrated lazily
      reading: reading,
      etymology: etymology || EMPTY_STRING,
      etymology_number: etymologyNumber
    };
    var entryId = String(row.entry_id || "").trim();
    if (entryId) entry.entry_id = entryId;
    var explicitSource = String(row.source || row._source || "").trim();
    if (explicitSource) entry._source = explicitSource;
    var formsRaw = (row.forms || "").trim();
    if (formsRaw) entry._forms_json = formsRaw;
    return entry;
  }

  function parseTsvRow(row) {
    var headword = (row.headword || "").trim();
    if (!headword) return null;
    var glossesRaw = (row.glosses || "").trim();
    var isNewFormat = ("romanization" in row) || (glossesRaw.charAt(0) === "[");
    return isNewFormat
      ? parseTsvRowCompact(row, headword, glossesRaw)
      : parseTsvRowLegacy(row, headword, glossesRaw);
  }

  function etymKey(entry) {
    var num = entry.etymology_number || 0;
    if (num && num > 0) return "n:" + num;
    return "t:" + (entry.etymology || "");
  }

  function splitUposTags(rawUpos) {
    var text = String(rawUpos || "").trim();
    if (!text) return [];
    if (text.indexOf("+") < 0) return [text];
    return text.split("+").map(function(p) { return p.trim(); }).filter(Boolean);
  }

  function entryIdentityKey(entry) {
    var head = String(entry.headword || "");
    var posRaw = String(entry.pos_raw || "");
    var etymNum = 0;
    try {
      etymNum = parseInt(entry.etymology_number || 0, 10) || 0;
    } catch (_e) {}
    return head + "\t" + posRaw + "\t" + etymNum + "\t" + (entry.etymology || "");
  }

  /**
   * Lazily hydrate an entry: parse glosses JSON, run dedup, populate senses/senses_full
   * and all optional array fields. Called on first lookup access.
   * After hydration, _glosses_raw is deleted so it's only paid once.
   */
  function hydrateEntry(entry) {
    if (!entry || !entry._glosses_raw) return entry; // already hydrated or empty
    var glossesRaw = entry._glosses_raw;
    var isLegacy = !!entry._legacy_row;
    var sensesFull = [];
    var flatSenses = [];

    if (isLegacy) {
      // Legacy format: glosses are semicolon-separated plain text
      var glossList = glossesRaw.split(";").map(function(g) { return g.trim(); }).filter(Boolean);
      if (!glossList.length) {
        // Mark as hydrated but empty
        entry._glosses_raw = undefined;
        entry.senses = EMPTY_ARRAY;
        entry.senses_full = EMPTY_ARRAY;
        return entry;
      }
      flatSenses = glossList;
      var tagsRaw = entry._legacy_tags_raw || "";
      var tagsPerSense = [];
      if (tagsRaw) {
        var groups = tagsRaw.split("|");
        for (var ti = 0; ti < groups.length; ti++) {
          tagsPerSense.push(groups[ti].split(";").map(function(t) { return t.trim(); }).filter(Boolean));
        }
      }
      for (var j = 0; j < glossList.length; j++) {
        var sense = { glosses: [glossList[j]] };
        if (j < tagsPerSense.length && tagsPerSense[j].length) sense.tags = tagsPerSense[j];
        sensesFull.push(sense);
      }
      // Populate legacy-specific fields from stored row
      var row = entry._legacy_row;
      function splitList(key) {
        var raw = (row[key] || "").trim();
        if (!raw) return EMPTY_ARRAY;
        return raw.split(";").map(function(v) { return v.trim(); }).filter(Boolean);
      }
      entry.alt_forms = splitList("alt_forms");
      if (!entry.alt_forms.length) entry.alt_forms = EMPTY_ARRAY;
      entry.ipa_variants = entry.reading ? [{ ipa: entry.reading, label: "" }] : EMPTY_ARRAY;
      entry.audio_urls = EMPTY_ARRAY;
      entry.synonyms = splitList("synonyms");
      if (!entry.synonyms.length) entry.synonyms = EMPTY_ARRAY;
      entry.antonyms = splitList("antonyms");
      if (!entry.antonyms.length) entry.antonyms = EMPTY_ARRAY;
      entry.derived = splitList("derived");
      if (!entry.derived.length) entry.derived = EMPTY_ARRAY;
      entry.related = splitList("related");
      if (!entry.related.length) entry.related = EMPTY_ARRAY;
      var grammar = (row.grammar || "").trim();
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
            if (gs && gs.length) flatSenses.push(gs.join("; "));
          }
        }
      } catch (_e) {}
      // Compact entries get empty singletons for optional fields
      entry.alt_forms = EMPTY_ARRAY;
      entry.ipa_variants = EMPTY_ARRAY;
      entry.audio_urls = EMPTY_ARRAY;
      entry.synonyms = EMPTY_ARRAY;
      entry.antonyms = EMPTY_ARRAY;
      entry.derived = EMPTY_ARRAY;
      entry.related = EMPTY_ARRAY;
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
  function ensureHydrated(entry) {
    if (entry && entry._glosses_raw) hydrateEntry(entry);
    return entry;
  }

  /**
   * Hydrate all entries in a bucket array. Used before returning lookup results.
   */
  function hydrateAll(entries) {
    if (!entries) return entries;
    for (var i = 0; i < entries.length; i++) {
      ensureHydrated(entries[i]);
    }
    return entries;
  }

  function mergeAdjacentUnknownFills(fills) {
    var rows = Array.isArray(fills) ? fills : [];
    if (!rows.length) return [];
    var out = [];
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      var source = String(row.source || "").toUpperCase();
      if (source !== "UNKNOWN") {
        out.push(row);
        continue;
      }
      var prev = out.length ? out[out.length - 1] : null;
      if (prev && String(prev.source || "").toUpperCase() === "UNKNOWN") {
        prev.text = String(prev.text || "") + String(row.text || "");
        prev.head = String(prev.head || prev.text || "") + String(row.text || "");
        continue;
      }
      out.push({
        text: String(row.text || ""),
        head: String(row.head || row.text || ""),
        roman: "",
        senses: [],
        pos: "",
        source: "UNKNOWN"
      });
    }
    return out;
  }

  function DictionaryEngine(langCode) {
    this._lang_code = String(langCode || "").trim().toLowerCase();
    this._by_word = Object.create(null);
    this._form_index = Object.create(null);
  }

  DictionaryEngine.prototype._lookup_key = function(text) {
    return lookupKey(text, this._lang_code);
  };

  DictionaryEngine.prototype._lookup_keys = function(text) {
    return lookupKeys(text, this._lang_code);
  };

  DictionaryEngine.prototype.loadFromRows = function(rows) {
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

  DictionaryEngine.prototype.load_tsv_entries = function(rows) {
    return this.loadFromRows(rows || []);
  };

  /** Load a single pre-parsed TSV row — avoids array allocation in streaming path. */
  DictionaryEngine.prototype._loadOneRow = function(row) {
    var entry = parseTsvRow(row);
    if (!entry) return false;
    var word = entry.headword;
    var foldKey = lookupKey(word, this._lang_code);
    if (!foldKey) return false;
    if (!this._by_word[foldKey]) this._by_word[foldKey] = [];
    this._by_word[foldKey].push(entry);
    this._index_tsv_forms(entry, word, foldKey);
    return true;
  };

  DictionaryEngine.prototype._index_tsv_forms = function(entry, word, foldKey) {
    var formsJson = entry._forms_json;
    delete entry._forms_json;
    var forms = [];
    if (formsJson) {
      try {
        var parsed = JSON.parse(formsJson);
        if (Array.isArray(parsed)) forms = parsed;
      } catch (_e) {}
    }
    for (var i = 0; i < forms.length; i++) {
      var f = forms[i];
      if (!Array.isArray(f) || f.length < 2) continue;
      var formText = String(f[0] || "").trim();
      if (!formText || formText === word) continue;
      var tagsStr = String(f[1] || "");
      var formRoman = String(f.length >= 3 ? (f[2] || "") : "").trim();
      var tags = tagsStr ? tagsStr.split(";").filter(Boolean) : [];
      applyLanguageFormRules(this._lang_code, entry, formText, tags);
      var internedMorph = internMorphArray(tags);
      var formTexts = getLanguageFormIndexTexts(this._lang_code, formText, tags);
      for (var ft = 0; ft < formTexts.length; ft++) {
        var indexFormText = String(formTexts[ft] || "").trim();
        if (!indexFormText || indexFormText === word) continue;
        var formKey = lookupKey(indexFormText, this._lang_code);
        if (!formKey || formKey === foldKey) continue;
        if (!this._form_index[formKey]) this._form_index[formKey] = [];
        // Compacted form hit: dropped entry_identity (use entry_ref object identity),
        // dropped lemma_key (derive from entry_ref.headword on demand),
        // dropped form_display_text when identical to form_text,
        // dropped form_roman when empty.
        var formHit = {
          lemma: word,
          form_text: indexFormText,
          morph: internedMorph,
          entry_ref: entry
        };
        if (formText !== indexFormText) formHit.form_display_text = formText;
        if (formRoman) formHit.form_roman = formRoman;
        this._form_index[formKey].push(formHit);
      }
    }

    // Korean infinitive stem indexing:
    // add "<lemma without final -da>" as a synthetic form with Morph: stem.
    var lang = String(this._lang_code || "").trim().toLowerCase();
    var isKorean = (lang === "ko" || lang === "korean" || lang.indexOf("ko-") === 0);
    var posRaw = String((entry && entry.pos_raw) || "").trim().toLowerCase();
    var canStem = (posRaw === "verb" || posRaw === "adj");
    var endsWithKoreanDa = (word.length > 1 && word.charCodeAt(word.length - 1) === 0xB2E4);
    if (isKorean && canStem && endsWithKoreanDa) {
      var stemText = String(word.slice(0, -1) || "").trim();
      if (stemText && stemText !== word) {
        var stemKey = lookupKey(stemText, this._lang_code);
        if (stemKey && stemKey !== foldKey) {
          if (!this._form_index[stemKey]) this._form_index[stemKey] = [];
          this._form_index[stemKey].push({
            lemma: word,
            form_text: stemText,
            morph: internMorphArray(["stem"]),
            entry_ref: entry
          });
        }
      }
    }
  };

  DictionaryEngine.prototype.lookup = function(word) {
    var entries = this.lookup_all(word);
    return entries.length ? entries[0] : null;
  };

  DictionaryEngine.prototype._split_matchable_display_entries = function(entries) {
    var src = Array.isArray(entries) ? entries : [];
    if (!src.length) return { matchable: [], display_only: [] };
    var lang = String(this._lang_code || "").trim().toLowerCase();
    if (!(lang === "ko" || lang === "korean" || lang.indexOf("ko-") === 0)) {
      return { matchable: src.slice(), display_only: [] };
    }
    var matchable = [];
    var displayOnly = [];
    for (var i = 0; i < src.length; i++) {
      if (isKoreanHanjaDropdownEntry(src[i])) displayOnly.push(src[i]);
      else matchable.push(src[i]);
    }
    return { matchable: matchable, display_only: displayOnly };
  };

  DictionaryEngine.prototype._lookup_all_raw = function(word) {
    var keys = lookupKeys(word, this._lang_code);
    var direct = [];
    var seenDirect = Object.create(null);
    for (var ki = 0; ki < keys.length; ki++) {
      var bucket = this._by_word[keys[ki]];
      if (!bucket) continue;
      for (var bi = 0; bi < bucket.length; bi++) {
        var eid = keys[ki] + ":" + bi;
        if (seenDirect[eid]) continue;
        seenDirect[eid] = true;
        direct.push(bucket[bi]);
      }
    }
    var formEntries = this.lookup_via_forms(word);
    if (!direct.length) {
      if (!formEntries.length) return [];
      hydrateAll(formEntries);
      for (var _fti = 0; _fti < formEntries.length; _fti++) {
        if (formEntries[_fti]) formEntries[_fti]._match_source = "form";
      }
      return annotateLookupEntries(formEntries, word, this._lang_code);
    }
    hydrateAll(direct);
    for (var _dti = 0; _dti < direct.length; _dti++) {
      if (direct[_dti]) direct[_dti]._match_source = "headword";
    }
    if (!formEntries.length) return annotateLookupEntries(direct, word, this._lang_code);
    var merged = direct.slice();
    var seenKeys = Object.create(null);
    for (var mi = 0; mi < merged.length; mi++) {
      seenKeys[entryIdentityKey(merged[mi])] = true;
    }
    for (var fi = 0; fi < formEntries.length; fi++) {
      ensureHydrated(formEntries[fi]);
      var k = entryIdentityKey(formEntries[fi]);
      if (seenKeys[k]) continue;
      seenKeys[k] = true;
      formEntries[fi]._match_source = "form";
      merged.push(formEntries[fi]);
    }
    return annotateLookupEntries(merged, word, this._lang_code);
  };

  DictionaryEngine.prototype.lookup_all = function(word) {
    return this._lookup_all_raw(word);
  };

  DictionaryEngine.prototype.lookupAll = function(word) {
    return this.lookup_all(word);
  };

  DictionaryEngine.prototype.lookup_display_only = function(word) {
    void word;
    return [];
  };

  DictionaryEngine.prototype.lookupDisplayOnly = function(word) {
    return this.lookup_display_only(word);
  };

  DictionaryEngine.prototype.lookup_via_forms = function(word) {
    function hasMorphTag(rawMorph, tagText) {
      var target = String(tagText || "").trim().toLowerCase();
      if (!target) return false;
      var src = Array.isArray(rawMorph) ? rawMorph : (rawMorph ? [rawMorph] : []);
      for (var i = 0; i < src.length; i++) {
        var one = String(src[i] || "").trim().toLowerCase();
        if (!one) continue;
        if (one === target) return true;
      }
      return false;
    }

    var keys = lookupKeys(word, this._lang_code);
    var formHits = [];
    for (var ki = 0; ki < keys.length; ki++) {
      var hits = this._form_index[keys[ki]];
      if (!hits) continue;
      for (var h = 0; h < hits.length; h++) formHits.push(hits[h]);
    }
    if (!formHits.length) return [];
    // Use a tag-on-object approach for dedup by entry_ref identity
    // (avoids building entryIdentityKey strings for every form hit).
    var dedupTag = "_fld_" + (Math.random().toString(36).slice(2, 8));
    var taggedObjects = [];
    var resultsByIdx = [];
    var resultCount = 0;
    function registerSurfaceForm(rec, rawSurface) {
      if (!rec || !rec.entry) return;
      var surface = String(rawSurface || "").trim();
      if (!surface) return;
      if (!rec.surfaceSeen[surface]) {
        rec.surfaceSeen[surface] = true;
        rec.surfaceForms.push(surface);
      }
      // Prefer the queried surface if present; otherwise keep first seen.
      if (!rec.entry.surface_form || surface === String(word || "").trim()) {
        rec.entry.surface_form = surface;
      }
    }
    for (var i = 0; i < formHits.length; i++) {
      var hit = formHits[i];
      var lemma = hit.lemma || "";
      var morph = hit.morph;
      var formRoman = String(hit.form_roman || "").trim();
      var formDisplayText = String(hit.form_display_text || hit.form_text || "").trim();
      var isEumhun = hasMorphTag(morph, "eumhun");
      var baseEntries = null;
      if (hit.entry_ref && typeof hit.entry_ref === "object") {
        baseEntries = [hit.entry_ref];
      } else {
        // Strict fallback: only resolve to exact lemma headword rows, never to
        // every entry sharing the normalized lookup key.
        var lemmaKey = lookupKey(lemma || "", this._lang_code);
        var bucket = this._by_word[lemmaKey] || [];
        var exactLemma = String(lemma || "");
        baseEntries = [];
        for (var bi = 0; bi < bucket.length; bi++) {
          var candidate = bucket[bi] || {};
          if (String(candidate.headword || "") === exactLemma) {
            baseEntries.push(candidate);
          }
        }
      }
      if (!baseEntries) continue;
      for (var b = 0; b < baseEntries.length; b++) {
        var base = baseEntries[b];
        if (!base || typeof base !== "object") continue;
        // Hydrate entry before cloning properties
        ensureHydrated(base);
        // Dedup by object identity using tag-on-object pattern
        var recIdx = base[dedupTag];
        var morphKey = "";
        if (Array.isArray(morph)) {
          var parts = [];
          for (var mi = 0; mi < morph.length; mi++) {
            var part = String(morph[mi] || "").trim();
            if (part) parts.push(part);
          }
          morphKey = parts.join(";");
        } else {
          morphKey = String(morph || "").trim();
        }

        var rec;
        if (recIdx === undefined) {
          var enriched = {};
          for (var k in base) {
            if (Object.prototype.hasOwnProperty.call(base, k) && k !== dedupTag) enriched[k] = base[k];
          }
          if (lemma) enriched.morph_base = lemma;
          // Seed morph_info from any existing tags on the base entry, then
          // form-hit tags will be appended below.  Without this the base
          // entry's own morph data (e.g. the morph tags on 不要 itself) was
          // silently wiped when 不要 appeared only via the forms index.
          var _existingMorphTags = splitMorphTags(base.morph_info);
          enriched.morph_info = _existingMorphTags.slice();
          var _initMorphSeen = Object.create(null);
          for (var _emi = 0; _emi < _existingMorphTags.length; _emi++) {
            _initMorphSeen[_existingMorphTags[_emi]] = true;
          }
          rec = {
            entry: enriched,
            morphSeen: _initMorphSeen,
            form_roman: formRoman,
            form_display_text: formDisplayText,
            has_eumhun: isEumhun,
            surfaceSeen: Object.create(null),
            surfaceForms: []
          };
          base[dedupTag] = resultCount;
          taggedObjects.push(base);
          resultsByIdx.push(rec);
          resultCount++;
        } else {
          rec = resultsByIdx[recIdx];
          if (formRoman) {
            // Prefer fuller eumhun readings when several form hits map to one entry.
            if (
              !rec.form_roman
              || ((rec.has_eumhun || isEumhun) && formRoman.length > String(rec.form_roman || "").length)
            ) {
              rec.form_roman = formRoman;
            }
          }
          if (!rec.form_display_text && formDisplayText) rec.form_display_text = formDisplayText;
          if (isEumhun) rec.has_eumhun = true;
          if (!rec.entry.morph_base && lemma) rec.entry.morph_base = lemma;
        }
        registerSurfaceForm(rec, hit.form_display_text || hit.form_text || word || "");

        if (morphKey && !rec.morphSeen[morphKey]) {
          rec.morphSeen[morphKey] = true;
          rec.entry.morph_info.push(morphKey);
        }
      }
    }
    // Cleanup dedup tags
    for (var ci = 0; ci < taggedObjects.length; ci++) {
      delete taggedObjects[ci][dedupTag];
    }

    var results = [];
    for (var ri = 0; ri < resultsByIdx.length; ri++) {
      var recOut = resultsByIdx[ri];
      var row = recOut.entry;
      if (recOut.form_roman) {
        row.reading = recOut.form_roman;
      } else if (recOut.has_eumhun && recOut.form_display_text) {
        // Keep the full eumhun reading text for display while lookup still uses
        // the indexed final character.
        row.reading = recOut.form_display_text;
      }
      if (!row.morph_info || !row.morph_info.length) delete row.morph_info;
      if (recOut.surfaceForms && recOut.surfaceForms.length > 1) {
        row.surface_forms = recOut.surfaceForms.slice();
      }
      results.push(row);
    }
    return annotateLookupEntries(results, word, this._lang_code);
  };

  DictionaryEngine.prototype.lookupViaForms = function(word) {
    return this.lookup_via_forms(word);
  };

  DictionaryEngine.prototype._filter_entries_for_greedy = function(entries) {
    var src = Array.isArray(entries) ? entries : [];
    if (!src.length) return [];
    return src.slice();
  };

  DictionaryEngine.prototype._entry_to_fill = function(entry, text) {
    ensureHydrated(entry);
    var surfaceText = String(text || "");
    var lemmaHead = String(entry.headword || "");
    var displayHead = surfaceText || lemmaHead;
    var fill = {
      text: surfaceText,
      head: displayHead,
      headword: lemmaHead || displayHead,
      roman: entry.reading || "",
      reading: entry.reading || "",
      senses: entry.senses || EMPTY_ARRAY,
      pos: entry.pos || "",
      pos_raw: entry.pos_raw || entry.pos || "",
      source: entry._source || entry.source || "KAIKKI",
      etymology: entry.etymology || "",
      senses_full: entry.senses_full || EMPTY_ARRAY,
      ipa_variants: entry.ipa_variants || EMPTY_ARRAY
    };
    var passthroughKeys = [
      "entry_id",
      "_source",
      "_glosses_raw",
      "_forms_raw",
      "_forms_json",
      "_commentary",
      "_lemma",
      "forms",
      "forms_meta",
      "spelling_header"
    ];
    for (var pk = 0; pk < passthroughKeys.length; pk++) {
      var key = passthroughKeys[pk];
      if (entry[key]) fill[key] = entry[key];
    }
    if (entry.morph_info) fill.morph_info = entry.morph_info;
    if (entry.morph_base) fill.morph_base = entry.morph_base;
    if (entry.grammar) fill.grammar = entry.grammar;
    if (lemmaHead && lemmaHead !== displayHead) {
      fill.surface_form = displayHead;
      fill.lemma_form = lemmaHead;
      if (!fill.morph_base) fill.morph_base = lemmaHead;
    }
    return fill;
  };

  function normalizePreferredPosList(rawList) {
    var src = Array.isArray(rawList) ? rawList : (rawList ? [rawList] : []);
    var out = [];
    var seen = Object.create(null);
    for (var i = 0; i < src.length; i++) {
      var pos = String(src[i] || "").trim().toLowerCase();
      if (!pos || seen[pos]) continue;
      seen[pos] = true;
      out.push(pos);
    }
    return out;
  }

  function selectEntriesByPreferredPosRaw(entries, preferredPosRaws) {
    var src = Array.isArray(entries) ? entries.slice() : [];
    var preferred = normalizePreferredPosList(preferredPosRaws);
    if (!preferred.length || !src.length) {
      return { primary: src, other: [], matched_pos_raw: "" };
    }
    for (var pi = 0; pi < preferred.length; pi++) {
      var wanted = preferred[pi];
      var primary = [];
      var other = [];
      for (var ei = 0; ei < src.length; ei++) {
        var entry = src[ei] || {};
        var posRaw = String(entry.pos_raw || entry.pos || "").trim().toLowerCase();
        if (posRaw === wanted) primary.push(entry);
        else other.push(entry);
      }
      if (primary.length) {
        return { primary: primary, other: other, matched_pos_raw: wanted };
      }
    }
    return { primary: [], other: src, matched_pos_raw: "" };
  }

  DictionaryEngine.prototype._greedy_fill_simple = function(word, excludeWhole, boundaries, _koreanGroups, debug, lemmaHints) {
    if (!word) {
      return { mode: "greedy", fills: [], has_known: false, has_unknown: false };
    }
    var engineLang = String(this._lang_code || "").trim().toLowerCase();
    var hintList = Array.isArray(lemmaHints) ? lemmaHints : [];
    var self = this;

    function dedupeExactEntryObjects(entries) {
      var src = Array.isArray(entries) ? entries : [];
      if (src.length <= 1) return src.slice();
      var dedupTag = "_exact_" + (Math.random().toString(36).slice(2, 8));
      var seenCompact = Object.create(null);
      var tagged = [];
      var out = [];
      for (var i = 0; i < src.length; i++) {
        var entry = src[i];
        if (!entry || typeof entry !== "object") continue;
        if (entry._winner_ref) {
          var compactKey = String(entry.storage_kind || "sqlite").trim().toLowerCase()
            + "|" + String(entry.db_alias || "").trim()
            + "|" + (parseInt(entry.entry_row_id, 10) || 0)
            + "|" + (parseInt(entry.form_row_id, 10) || 0);
          if (seenCompact[compactKey]) continue;
          seenCompact[compactKey] = true;
          out.push(entry);
          continue;
        }
        if (entry[dedupTag]) continue;
        entry[dedupTag] = true;
        tagged.push(entry);
        out.push(entry);
      }
      for (var ti = 0; ti < tagged.length; ti++) {
        delete tagged[ti][dedupTag];
      }
      return out;
    }

    function collectWholeTokenLemmaExactEntries() {
      if (!hintList.length) return [];
      if (isKoreanLanguageCode(engineLang) && hintList.length > 1) return [];
      if (hintList.length !== 1) return [];
      var out = [];
      var wordKey = lookupKey(word, engineLang);
      var hintTexts = getLemmaHintTexts(hintList[0], engineLang);
      for (var hi = 0; hi < hintTexts.length; hi++) {
        var hintText = hintTexts[hi];
        if (!hintText) continue;
        var hintKeys = lookupKeys(hintText, engineLang);
        for (var hki = 0; hki < hintKeys.length; hki++) {
          var hintKey = String(hintKeys[hki] || "").trim();
          if (!hintKey || hintKey === wordKey) continue;
          if (self._compact_mode && self._hw_index) {
            var hwHits = self._hw_index[hintKey] || [];
            for (var hwi = 0; hwi < hwHits.length; hwi++) {
              var alias = hwHits[hwi][0];
              var eid = hwHits[hwi][1];
              out.push({
                _winner_ref: true,
                storage_kind: (self._db_alias_map[alias] === "custom" || alias === "customdb") ? "custom" : "sqlite",
                db_alias: alias,
                entry_row_id: eid,
                match_kind: "headword",
                match_key: hintKey,
                headword: hintText
              });
            }
            continue;
          }
          var hintEntries = self._by_word[hintKey] || [];
          for (var ei = 0; ei < hintEntries.length; ei++) out.push(hintEntries[ei]);
        }
      }
      return dedupeExactEntryObjects(out);
    }

    // If the whole surface has an exact dictionary match and we're not
    // excluding whole-surface results, accept it immediately — no DP needed.
    // If lemma hints exist, check whether any hint matches and flag accordingly.
    if (!excludeWhole) {
      var exactEntries = dedupeExactEntryObjects((this.lookup_all(word) || []).concat(collectWholeTokenLemmaExactEntries()));
      if (exactEntries.length) {
        var exactFill = this._entry_to_fill(exactEntries[0], word);
        exactFill.entries = exactEntries;
        var promotedLemma = null;
        var promotedMeta = null;
        for (var ehi = 0; ehi < hintList.length; ehi++) {
          var ehRaw = hintList[ehi];
          var hintTexts = getLemmaHintTexts(ehRaw, engineLang);
          for (var ehti = 0; ehti < hintTexts.length; ehti++) {
            var ehText = hintTexts[ehti];
            if (!ehText) continue;
            var ehKey = lookupKey(ehText, engineLang);
            if (ehKey === lookupKey(word, engineLang)) {
              promotedLemma = ehText;
              promotedMeta = (ehRaw && typeof ehRaw === "object")
                ? { upos: String(ehRaw.upos || ""), xpos: String(ehRaw.xpos || "") }
                : null;
              break;
            }
            for (var eei = 0; eei < exactEntries.length; eei++) {
              var ehw = lookupKey(exactEntries[eei].headword || "", engineLang);
              if (ehw && ehw === ehKey) {
                promotedLemma = ehText;
                promotedMeta = (ehRaw && typeof ehRaw === "object")
                  ? { upos: String(ehRaw.upos || ""), xpos: String(ehRaw.xpos || "") }
                  : null;
                break;
              }
            }
            if (promotedLemma) break;
          }
          if (promotedLemma) break;
        }
        if (promotedLemma) {
          exactFill._lemma_promoted = promotedLemma;
          exactFill._lemma_promoted_headword = String(exactEntries[0].headword || "");
          var ehMeta = promotedMeta;
          if (ehMeta && ehMeta.upos) exactFill._lemma_upos_hint = ehMeta.upos;
          if (ehMeta && ehMeta.xpos) exactFill._lemma_xpos_hint = ehMeta.xpos;
        }
        return { mode: "greedy", fills: [exactFill], has_known: true, has_unknown: false, has_lemma_promotion: !!promotedLemma };
      }
    }

    // Global segmentation:
    // 1) If lemma hints are provided, candidates whose entries match a lemma
    //    hint get an unconditional promotion (hard override — they always win).
    // 2) Among non-promoted candidates: minimize unknown characters,
    //    then minimize total pieces, then maximize the longest span anywhere
    //    in the chosen path.
    var graphemeTable = buildGraphemeSpanTable(word);
    var graphemeSpans = graphemeTable.spans;
    var boundaryIndexByOffset = graphemeTable.boundary_to_index;
    var n = graphemeSpans.length;
    var wordCodeUnitLength = word.length;
    var inf = 1e9;
    var prefixStateCount = 1;
    var dpUnknown = new Array(prefixStateCount);
    var dpPieces = new Array(prefixStateCount);
    var dpPromoted = new Array(prefixStateCount);
    var dpMaxSpan = new Array(prefixStateCount);
    var dpUsedLemmaKeys = new Array(prefixStateCount);
    var choice = new Array(prefixStateCount);
    for (var ps = 0; ps < prefixStateCount; ps++) {
      dpUnknown[ps] = new Array(n + 1);
      dpPieces[ps] = new Array(n + 1);
      dpPromoted[ps] = new Array(n + 1);
      dpMaxSpan[ps] = new Array(n + 1);
      dpUsedLemmaKeys[ps] = new Array(n + 1);
      choice[ps] = new Array(n + 1);
    }
    var cache = Object.create(null);
    var boundarySet = null;
    var boundaryList = null;
    var traceEnabled = !!debug;
    var traceSteps = traceEnabled ? new Array(n) : null;

    function graphemeBoundaryOffset(index) {
      var idx = parseInt(index, 10);
      if (!isFinite(idx) || idx <= 0) return 0;
      if (idx >= n) return wordCodeUnitLength;
      return graphemeSpans[idx].start;
    }

    function sliceByGraphemeRange(start, end) {
      if (start < 0 || end <= start || end > n) return "";
      return word.slice(graphemeBoundaryOffset(start), graphemeBoundaryOffset(end));
    }

    // --- Lemma promotion setup ---
    // For each lemma hint, find the original entry objects it resolves to
    // (via direct headword lookup AND form index), and tag those original
    // objects. A candidate is promoted only if the actual object in the DP
    // was tagged — entries in different forms buckets that happen to share
    // headwords or identity keys are never cross-contaminated.
    var lemmaHintList = hintList;
    var lemmaHintMeta = Object.create(null);
    var lemmaHintLabels = Object.create(null);
    var hasLemmaPromotion = false;
    var lpTag = "_lp_" + (Math.random().toString(36).slice(2, 10));
    var lpTaggedObjects = [];
    function tagPromotedObject(entry, lemmaKey) {
      if (!entry || !lemmaKey) return;
      var tags = entry[lpTag];
      if (!tags) {
        entry[lpTag] = [lemmaKey];
        lpTaggedObjects.push(entry);
        return;
      }
      for (var ti = 0; ti < tags.length; ti++) {
        if (tags[ti] === lemmaKey) return;
      }
      tags.push(lemmaKey);
    }
    for (var lhi = 0; lhi < lemmaHintList.length; lhi++) {
      var rawHint = lemmaHintList[lhi];
      var hint, hintUpos, hintXpos;
      if (rawHint && typeof rawHint === "object" && !Array.isArray(rawHint)) {
        hint = String(rawHint.text || "").trim();
        hintUpos = String(rawHint.upos || "").trim();
        hintXpos = String(rawHint.xpos || "").trim();
      } else {
        hint = String(rawHint || "").trim();
        hintUpos = "";
        hintXpos = "";
      }
      if (!hint) continue;
      var hintTexts = getLemmaHintTexts(rawHint, engineLang);
      if (!hintTexts.length) continue;
      var lemmaKey = lookupKey(hint, engineLang) || lookupKey(hintTexts[0], engineLang) || hintTexts[0];
      if (!lemmaKey) continue;
      hasLemmaPromotion = true;
      if (!lemmaHintLabels[lemmaKey]) lemmaHintLabels[lemmaKey] = hint;
      if (hintUpos || hintXpos) {
        if (!lemmaHintMeta[lemmaKey]) {
          lemmaHintMeta[lemmaKey] = { upos: hintUpos, xpos: hintXpos };
        } else {
          if (hintUpos && !lemmaHintMeta[lemmaKey].upos) lemmaHintMeta[lemmaKey].upos = hintUpos;
          if (hintXpos && !lemmaHintMeta[lemmaKey].xpos) lemmaHintMeta[lemmaKey].xpos = hintXpos;
        }
      }
      for (var hti = 0; hti < hintTexts.length; hti++) {
        var hintText = hintTexts[hti];
        if (!hintText) continue;
        // Tag original entry objects reachable via direct headword lookup
        var hintKey = lookupKey(hintText, engineLang);
        var directBucket = hintKey ? (this._by_word[hintKey] || []) : [];
        for (var dbi = 0; dbi < directBucket.length; dbi++) {
          tagPromotedObject(directBucket[dbi], lemmaKey);
        }
        // Tag original entry objects reachable via forms index
        var formHits = hintKey ? (this._form_index[hintKey] || []) : [];
        for (var fhi = 0; fhi < formHits.length; fhi++) {
          if (formHits[fhi].entry_ref) {
            tagPromotedObject(formHits[fhi].entry_ref, lemmaKey);
          }
        }
      }
    }

    function getLemmaHintMeta(lemmaKey) {
      if (!lemmaKey) return null;
      return lemmaHintMeta[lemmaKey] || null;
    }

    function getPromotedLemmaKeys(entry) {
      if (!hasLemmaPromotion) return null;
      var hintVals = entry[lpTag];
      if (!hintVals || !hintVals.length) return null;
      return hintVals;
    }

    function cleanupLpTags() {
      for (var ci = 0; ci < lpTaggedObjects.length; ci++) {
        delete lpTaggedObjects[ci][lpTag];
      }
    }

    function filterEntriesForLemmaReuse(entries, usedLemmaKeys) {
      if (!entries || !entries.length) return [];
      if (!usedLemmaKeys) return entries.slice();
      var out = [];
      for (var ei = 0; ei < entries.length; ei++) {
        var entry = entries[ei];
        var lemmaKeys = getPromotedLemmaKeys(entry);
        if (!lemmaKeys || !lemmaKeys.length) {
          out.push(entry);
          continue;
        }
        for (var li = 0; li < lemmaKeys.length; li++) {
          if (!usedLemmaKeys[lemmaKeys[li]]) {
            out.push(entry);
            break;
          }
        }
      }
      return out;
    }

    function checkCandidatesForPromotion(entries, usedLemmaKeys) {
      if (!hasLemmaPromotion || !entries || !entries.length) return null;
      for (var ci = 0; ci < entries.length; ci++) {
        var matches = getPromotedLemmaKeys(entries[ci]);
        if (!matches || !matches.length) continue;
        for (var mi = 0; mi < matches.length; mi++) {
          var match = matches[mi];
          if (usedLemmaKeys && usedLemmaKeys[match]) continue;
          var meta = getLemmaHintMeta(match);
          return {
            index: ci,
            lemma: lemmaHintLabels[match] || match,
            lemma_key: match,
            entry: entries[ci],
            upos: meta ? meta.upos : "",
            xpos: meta ? meta.xpos : ""
          };
        }
      }
      return null;
    }

    function buildBoundaryData(rawBoundaries, forceWholeToken) {
      var src = Array.isArray(rawBoundaries) ? rawBoundaries : null;
      if (!src) return null;
      if (!src.length && !forceWholeToken) return null;
      var seen = Object.create(null);
      var list = [0, n];
      for (var bi = 0; bi < src.length; bi++) {
        var offset = parseInt(src[bi], 10);
        if (!isFinite(offset) || offset <= 0 || offset >= wordCodeUnitLength) continue;
        var boundaryIndex = boundaryIndexByOffset[offset];
        if (!isFinite(boundaryIndex) || boundaryIndex <= 0 || boundaryIndex >= n) continue;
        list.push(boundaryIndex);
      }
      list.sort(function(a, b) { return a - b; });
      var unique = [];
      for (var ui = 0; ui < list.length; ui++) {
        var value = list[ui];
        if (seen[value]) continue;
        seen[value] = true;
        unique.push(value);
      }
      if (unique.length < 2) return null;
      var set = Object.create(null);
      for (var si = 0; si < unique.length; si++) {
        set[unique[si]] = true;
      }
      return { list: unique, set: set };
    }

    // Auto-inject whitespace positions as boundaries so the DP cannot
    // fragment words across spaces.  A span that fully covers whole words
    // (start AND end both on boundaries) is still allowed — this handles
    // Vietnamese multi-syllable tokens like "hôm nay" where the dictionary
    // entry itself contains the space.
    var spaceBoundaries = [];
    for (var si = 0; si < n; si++) {
      var spaceSpan = graphemeSpans[si];
      if (!spaceSpan) continue;
      if (spaceSpan.text === " " || spaceSpan.text === "\t") {
        spaceBoundaries.push(spaceSpan.start);
        spaceBoundaries.push(spaceSpan.end);
      }
    }
    var mergedBoundaries = Array.isArray(boundaries) ? boundaries.slice() : [];
    for (var sbi = 0; sbi < spaceBoundaries.length; sbi++) {
      mergedBoundaries.push(spaceBoundaries[sbi]);
    }

    var boundaryData = buildBoundaryData(mergedBoundaries.length ? mergedBoundaries : null, false);
    if (boundaryData) {
      boundaryList = boundaryData.list;
      boundarySet = boundaryData.set;
    }

    function buildDpDebugPayload() {
      if (!traceEnabled) return null;
      var steps = [];
      for (var si = 0; si < (traceSteps || []).length; si++) {
        if (traceSteps[si]) steps.push(traceSteps[si]);
      }
      var boundaryOffsets = [];
      if (boundaryList) {
        for (var bi = 0; bi < boundaryList.length; bi++) {
          boundaryOffsets.push(graphemeBoundaryOffset(boundaryList[bi]));
        }
      }
      return {
        word: word,
        exclude_whole: !!excludeWhole,
        boundaries: boundaryOffsets,
        steps: steps
      };
    }

    for (var psInit = 0; psInit < prefixStateCount; psInit++) {
      for (var di = 0; di <= n; di++) {
        dpUnknown[psInit][di] = inf;
        dpPieces[psInit][di] = inf;
        dpPromoted[psInit][di] = 0;
        dpMaxSpan[psInit][di] = 0;
        dpUsedLemmaKeys[psInit][di] = null;
      }
      dpUnknown[psInit][n] = 0;
      dpPieces[psInit][n] = 0;
      dpPromoted[psInit][n] = 0;
      dpMaxSpan[psInit][n] = 0;
      dpUsedLemmaKeys[psInit][n] = null;
      choice[psInit][n] = null;
    }

    // Scoring: current promoted span > non-promoted span; when both current
    // spans are promoted, prefer the longer current span. Then prefer fewer
    // unknowns, fewer pieces, the largest span anywhere in the path, and
    // finally the longer current span as a deterministic last tie-break.
    function isBetter(cPromotedHere, cPromoted, cUnknown, cPieces, cMaxSpan, cSpanLen, bPromotedHere, bPromoted, bUnknown, bPieces, bMaxSpan, bSpanLen) {
      if (!!cPromotedHere !== !!bPromotedHere) return !!cPromotedHere;
      if (cPromotedHere && bPromotedHere && cSpanLen !== bSpanLen) return cSpanLen > bSpanLen;
      if (cUnknown !== bUnknown) return cUnknown < bUnknown;
      if (cPromoted !== bPromoted) return cPromoted > bPromoted;
      if (cPieces !== bPieces) return cPieces < bPieces;
      if (cMaxSpan !== bMaxSpan) return cMaxSpan > bMaxSpan;
      return cSpanLen > bSpanLen;
    }

    function crossesRestrictedBoundary(start, end) {
      if (!boundaryList || boundaryList.length <= 2) return false;
      if (start >= end) return false;
      if (boundarySet[start] && boundarySet[end]) return false;
      for (var bi = 0; bi < boundaryList.length; bi++) {
        var b = boundaryList[bi];
        if (b <= start) continue;
        if (b >= end) break;
        return true;
      }
      return false;
      // Disallow partial cross-boundary spans (e.g., 위+시).
    }

    function evaluateCandidate(self, start, end, prefixStage, bestState, stepTrace) {
      var piece = sliceByGraphemeRange(start, end);
      if (!piece) return bestState;
      if (excludeWhole && wordCodeUnitLength > 1 && start === 0 && end === n) return bestState;
      var startOffset = graphemeBoundaryOffset(start);
      var endOffset = graphemeBoundaryOffset(end);
      if (crossesRestrictedBoundary(start, end)) {
        if (stepTrace) {
          stepTrace.rejected.push({
            kind: "known",
            start: startOffset,
            end: endOffset,
            piece: piece,
            reason: "crosses_lemma_boundary",
            detail: "boundary_cross"
          });
        }
        return bestState;
      }
      var cacheKey = piece;
      var cached = cache[cacheKey];
      if (cached === undefined) {
        var candidateEntries = self._filter_entries_for_greedy(self.lookup_all(piece));
        cached = {
          entries: candidateEntries,
          xpos_hint: "",
          candidate_refs: traceEnabled ? buildEngineDebugEntryRefs(candidateEntries, 8) : [],
          rejected_pos_detail: null
        };
        cache[cacheKey] = cached;
      }
      if (!cached.entries || !cached.entries.length) return bestState;
      if (dpUnknown[0][end] >= inf) return bestState;
      var usedLemmaKeys = dpUsedLemmaKeys[0][end];
      var availableEntries = filterEntriesForLemmaReuse(cached.entries, usedLemmaKeys);
      if (!availableEntries.length) {
        if (stepTrace) {
          stepTrace.rejected.push({
            kind: "known",
            start: startOffset,
            end: endOffset,
            piece: piece,
            reason: "lemma_already_consumed",
            lemma_keys: Object.keys(usedLemmaKeys || {}),
            entry_refs: traceEnabled ? buildEngineDebugEntryRefs(cached.entries, 8) : []
          });
        }
        return bestState;
      }

      var cUnknown = dpUnknown[0][end];
      var cPieces = 1 + dpPieces[0][end];
      var spanLen = end - start;
      var cMaxSpan = Math.max(spanLen, dpMaxSpan[0][end] || 0);

      // --- Lemma promotion check ---
      var promotion = checkCandidatesForPromotion(availableEntries, usedLemmaKeys);
      var promotedHere = promotion ? 1 : 0;
      var cPromoted = dpPromoted[0][end] + promotedHere;
      var nextUsedLemmaKeys = usedLemmaKeys;
      if (promotion && promotion.lemma_key) {
        nextUsedLemmaKeys = Object.assign({}, usedLemmaKeys || {});
        nextUsedLemmaKeys[promotion.lemma_key] = true;
      }

      var acceptedTrace = null;
      if (stepTrace) {
        acceptedTrace = {
          kind: "known",
          start: startOffset,
          end: endOffset,
          piece: piece,
          xpos_tags: [],
          entry_count: availableEntries.length,
          entry_refs: traceEnabled ? buildEngineDebugEntryRefs(availableEntries, 8) : [],
          score_promoted_here: promotedHere,
          score_unknown: cUnknown,
          score_pieces: cPieces,
          score_max_span: cMaxSpan,
          score_promoted: cPromoted,
          lemma_promoted: promotion ? promotion.lemma : null,
          lemma_promoted_headword: promotion ? String(promotion.entry.headword || "") : null,
          lemma_promoted_upos: promotion ? (promotion.upos || "") : null,
          lemma_promoted_xpos: promotion ? (promotion.xpos || "") : null
        };
        stepTrace.accepted.push(acceptedTrace);
      }
      if (isBetter(promotedHere, cPromoted, cUnknown, cPieces, cMaxSpan, spanLen, bestState.promoted_here, bestState.promoted, bestState.unknown, bestState.pieces, bestState.max_span_len, bestState.span_len)) {
        bestState.promoted_here = promotedHere;
        bestState.promoted = cPromoted;
        bestState.unknown = cUnknown;
        bestState.pieces = cPieces;
        bestState.max_span_len = cMaxSpan;
        bestState.end = end;
        bestState.entries = availableEntries;
        bestState.kind = "known";
        bestState.span_len = spanLen;
        bestState.xpos_hint = cached.xpos_hint || "";
        bestState.trace = acceptedTrace;
        bestState.lemma_promotion = promotion;
        bestState.used_lemma_keys = nextUsedLemmaKeys;
      }
      return bestState;
    }

    for (var i = n - 1; i >= 0; i--) {
      for (var prefixStage = 0; prefixStage < prefixStateCount; prefixStage++) {
        var bestState = {
          promoted_here: 0,
          promoted: 0,
          unknown: inf,
          pieces: inf,
          max_span_len: 0,
          end: -1,
          entries: null,
          kind: "",
          span_len: 0,
          xpos_hint: "",
          trace: null,
          lemma_promotion: null,
          used_lemma_keys: null
        };
        var stepTrace = (traceEnabled && prefixStage === 0) ? {
          index: graphemeBoundaryOffset(i),
          accepted: [],
          rejected: [],
          unknown_fallback: null,
          selected: null
        } : null;

        for (var end2 = i + 1; end2 <= n; end2++) {
          bestState = evaluateCandidate(this, i, end2, prefixStage, bestState, stepTrace);
        }

        var unknownEnd = i + 1;
        if (unknownEnd > i && unknownEnd <= n && dpUnknown[0][unknownEnd] < inf) {
          var unknownSpan = unknownEnd - i;
          var uUnknown = unknownSpan + dpUnknown[0][unknownEnd];
          var uPieces = 1 + dpPieces[0][unknownEnd];
          var uPromoted = dpPromoted[0][unknownEnd];
          var uMaxSpan = Math.max(unknownSpan, dpMaxSpan[0][unknownEnd] || 0);
          var unknownTrace = stepTrace ? {
            kind: "unknown",
            start: graphemeBoundaryOffset(i),
            end: graphemeBoundaryOffset(unknownEnd),
            piece: sliceByGraphemeRange(i, unknownEnd),
            score_promoted_here: 0,
            score_unknown: uUnknown,
            score_pieces: uPieces,
            score_max_span: uMaxSpan,
            score_promoted: uPromoted
          } : null;
          if (stepTrace) stepTrace.unknown_fallback = unknownTrace;
          if (isBetter(0, uPromoted, uUnknown, uPieces, uMaxSpan, unknownSpan, bestState.promoted_here, bestState.promoted, bestState.unknown, bestState.pieces, bestState.max_span_len, bestState.span_len)) {
            bestState.promoted_here = 0;
            bestState.promoted = uPromoted;
            bestState.unknown = uUnknown;
            bestState.pieces = uPieces;
            bestState.max_span_len = uMaxSpan;
            bestState.end = unknownEnd;
            bestState.entries = null;
            bestState.kind = "unknown";
            bestState.span_len = unknownSpan;
            bestState.xpos_hint = "";
            bestState.trace = unknownTrace;
            bestState.lemma_promotion = null;
            bestState.used_lemma_keys = dpUsedLemmaKeys[0][unknownEnd];
          }
        }

        if (bestState.end >= 0 && bestState.kind) {
          dpUnknown[prefixStage][i] = bestState.unknown;
          dpPieces[prefixStage][i] = bestState.pieces;
          dpPromoted[prefixStage][i] = bestState.promoted;
          dpMaxSpan[prefixStage][i] = bestState.max_span_len;
          dpUsedLemmaKeys[prefixStage][i] = bestState.used_lemma_keys || null;
          choice[prefixStage][i] = {
            end: bestState.end,
            entries: bestState.entries,
            kind: bestState.kind,
            xpos_hint: bestState.xpos_hint,
            lemma_promotion: bestState.lemma_promotion || null
          };
          if (stepTrace) {
            var selectedTrace = {
              kind: bestState.kind,
              start: graphemeBoundaryOffset(i),
              end: graphemeBoundaryOffset(bestState.end),
              piece: sliceByGraphemeRange(i, bestState.end),
              score_promoted_here: bestState.promoted_here,
              score_unknown: bestState.unknown,
              score_pieces: bestState.pieces,
              score_max_span: bestState.max_span_len,
              score_promoted: bestState.promoted
            };
            if (bestState.kind === "known") {
              selectedTrace.entry_refs = (bestState.trace && Array.isArray(bestState.trace.entry_refs))
                ? bestState.trace.entry_refs.slice()
                : buildEngineDebugEntryRefs(bestState.entries, 8);
              selectedTrace.xpos_tags = (bestState.trace && Array.isArray(bestState.trace.xpos_tags))
                ? bestState.trace.xpos_tags.slice()
                : [];
              selectedTrace.xpos_hint = bestState.xpos_hint || "";
              if (bestState.lemma_promotion) {
                selectedTrace.lemma_promoted = bestState.lemma_promotion.lemma;
                selectedTrace.lemma_promoted_headword = String(bestState.lemma_promotion.entry.headword || "");
              }
            }
            stepTrace.selected = selectedTrace;
            traceSteps[i] = stepTrace;
          }
        }
      }
    }

    var fills = [];
    var hasAnyPromotion = false;
    var idx = 0;
    while (idx < n) {
      var step = choice[0][idx];
      if (!step || step.end <= idx) {
        var fallbackEnd = idx + 1;
        var fallbackText = sliceByGraphemeRange(idx, fallbackEnd);
        if (!fallbackText) break;
        fills.push({
          text: fallbackText,
          head: fallbackText,
          roman: "",
          senses: [],
          pos: "",
          source: "UNKNOWN"
        });
        idx = fallbackEnd;
        continue;
      }
      var segText = sliceByGraphemeRange(idx, step.end);
      if (step.kind === "known" && step.entries && step.entries.length) {
        var fill = this._entry_to_fill(step.entries[0], segText);
        fill.entries = step.entries;
        if (step.xpos_hint) fill._xpos_hint = step.xpos_hint;
        if (step.lemma_promotion) {
          hasAnyPromotion = true;
          fill._lemma_promoted = step.lemma_promotion.lemma;
          fill._lemma_promoted_headword = String(step.lemma_promotion.entry.headword || "");
          fill._lemma_promoted_pos = String(step.lemma_promotion.entry.pos_raw || "");
          if (step.lemma_promotion.upos) fill._lemma_upos_hint = String(step.lemma_promotion.upos);
          if (step.lemma_promotion.xpos) fill._lemma_xpos_hint = String(step.lemma_promotion.xpos);
        }
        fills.push(fill);
      } else {
        fills.push({
          text: segText,
          head: segText,
          roman: "",
          senses: [],
          pos: "",
          source: "UNKNOWN"
        });
      }
      idx = step.end;
    }

    var hasKnown = false;
    var hasUnknown = false;
    for (var mi = 0; mi < fills.length; mi++) {
      if ((fills[mi] || {}).source === "UNKNOWN") hasUnknown = true;
      else hasKnown = true;
    }

    var result = { mode: "greedy", fills: fills, has_known: hasKnown, has_unknown: hasUnknown, has_lemma_promotion: hasAnyPromotion };
    if (hasLemmaPromotion) result.lemma_hints = lemmaHintList.slice();
    var dpDebug = buildDpDebugPayload();
    if (dpDebug) result.dp_debug = dpDebug;
    cleanupLpTags();
    return result;
  };

  DictionaryEngine.prototype._greedy_fill = function(word, excludeWhole, upos, debug, boundaries, _koreanGroups, lemmaHints) {
    void upos;
    return this._greedy_fill_simple(word, !!excludeWhole, boundaries || null, null, !!debug, lemmaHints || null);
  };

  DictionaryEngine.prototype.fill_token = function(word, allowExactOrOpts, excludeWhole, upos, debug) {
    var opts;
    if (allowExactOrOpts && typeof allowExactOrOpts === "object" && !Array.isArray(allowExactOrOpts)) {
      opts = allowExactOrOpts;
    } else {
      opts = {
        allowExact: (allowExactOrOpts !== false),
        excludeWhole: !!excludeWhole,
        upos: upos || "",
        debug: !!debug
      };
    }
    var allowExact = opts.allowExact !== false;
    var exWhole = !!opts.excludeWhole;
    var uposValue = String(opts.upos || "");
    var debugValue = !!opts.debug;
    var boundariesValue = Array.isArray(opts.boundaries) ? opts.boundaries : null;
    var lemmaHintsValue = Array.isArray(opts.lemma_hints) ? opts.lemma_hints : null;
    if (allowExact && !exWhole) {
      var entries = this.lookup_all(word);
      if (entries.length) {
        var fill = this._entry_to_fill(entries[0], word);
        fill.entries = entries;
        var promotedLemma = null;
        var promotedMeta = null;
        var engineLang = String(this._lang_code || "").trim().toLowerCase();
        var hintList = Array.isArray(lemmaHintsValue) ? lemmaHintsValue : [];
        for (var hi = 0; hi < hintList.length; hi++) {
          var rawHint = hintList[hi];
          var hintTexts = getLemmaHintTexts(rawHint, engineLang);
          for (var hti = 0; hti < hintTexts.length; hti++) {
            var hintText = hintTexts[hti];
            if (!hintText) continue;
            var hintKey = lookupKey(hintText, engineLang);
            if (hintKey === lookupKey(word, engineLang)) {
              promotedLemma = hintText;
              promotedMeta = (rawHint && typeof rawHint === "object")
                ? { upos: String(rawHint.upos || ""), xpos: String(rawHint.xpos || "") }
                : null;
              break;
            }
            for (var ei = 0; ei < entries.length; ei++) {
              var headKey = lookupKey(entries[ei].headword || "", engineLang);
              if (headKey && headKey === hintKey) {
                promotedLemma = hintText;
                promotedMeta = (rawHint && typeof rawHint === "object")
                  ? { upos: String(rawHint.upos || ""), xpos: String(rawHint.xpos || "") }
                  : null;
                break;
              }
            }
            if (promotedLemma) break;
          }
          if (promotedLemma) break;
        }
        if (promotedLemma) {
          fill._lemma_promoted = promotedLemma;
          fill._lemma_promoted_headword = String(entries[0].headword || "");
          if (promotedMeta && promotedMeta.upos) fill._lemma_upos_hint = promotedMeta.upos;
          if (promotedMeta && promotedMeta.xpos) fill._lemma_xpos_hint = promotedMeta.xpos;
        }
        return {
          mode: promotedLemma ? "exact_lemma_promoted" : "exact",
          fills: [fill],
          has_known: true,
          has_unknown: false,
          has_lemma_promotion: !!promotedLemma
        };
      }
    }
    return this._greedy_fill(word, exWhole, uposValue, debugValue, boundariesValue, null, lemmaHintsValue);
  };

  DictionaryEngine.prototype.fillToken = function(word, opts) {
    return this.fill_token(word, opts || {});
  };

  DictionaryEngine.prototype.filter_entries_by_upos = function(entries, upos, opts) {
    opts = opts || {};
    var baseEntries = entries ? entries.slice() : [];
    if (!baseEntries.length) return [[], []];

    var greedyMatch = !!opts.greedy_match;
    var greedyMultiFill = !!opts.greedy_multi_fill;
    var greedyMode = greedyMatch || greedyMultiFill;
    var affixPreferred = Object.create(null);
    if (greedyMode) {
      for (var axi = 0; axi < NOUN_AFFIX_POS.length; axi++) {
        affixPreferred[NOUN_AFFIX_POS[axi]] = true;
      }
    }
    var activeAlwaysFiltered = buildAlwaysFilteredPosMap(ALWAYS_FILTERED_POS, this._lang_code);
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
    var uposTags = splitUposTags(String(upos || ""));
    var allowed = Object.create(null);
    var recognized = false;
    for (var ti = 0; ti < uposTags.length; ti++) {
      var mapped = UPOS_TO_KAIKKI_POS[uposTags[ti]];
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
          if (affixPreferred[String(filterBaseEntries[ae].pos_raw || "")]) {
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
        var noGatePosRaw = String(filterBaseEntries[e].pos_raw || "");
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
        var posRaw = String(group[ge].pos_raw || "");
        if (allowed[posRaw] || affixPreferred[posRaw]) {
          hasAllowedMatch = true;
          groupPrimary.push(group[ge]);
        } else if (FILTER_EXEMPT_POS[posRaw]) {
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

  DictionaryEngine.prototype.filterEntriesByUpos = function(entries, upos, opts) {
    var split = this.filter_entries_by_upos(entries, upos, opts || {});
    return { primary: split[0], other: split[1] };
  };

  DictionaryEngine.prototype.filter_entries_by_xpos = function(entries, xposTags) {
    var baseEntries = entries ? entries.slice() : [];
    if (!baseEntries.length) return [baseEntries, []];
    var lang = String(this._lang_code || "").trim().toLowerCase();
    if (lang === "vi") {
      var viAlwaysFilteredSplit = splitEntriesByAlwaysFiltered(baseEntries, buildAlwaysFilteredPosMap(VIETNAMESE_XPOS_ALWAYS_FILTERED_POS, lang));
      var viFilterBaseEntries = viAlwaysFilteredSplit[0];
      var viAlwaysFilteredEntries = viAlwaysFilteredSplit[1];
      if (!viFilterBaseEntries.length) return [[], viAlwaysFilteredEntries];
      if (viFilterBaseEntries.length <= 1) return [viFilterBaseEntries, viAlwaysFilteredEntries];
      var viTags = normalizeVietnameseXposTags(xposTags);
      if (!viTags.length) return [viFilterBaseEntries, viAlwaysFilteredEntries];
      var viAllowedInfo = buildVietnameseAllowedPosMap(viTags);
      if (!viAllowedInfo.has_mapped || !Object.keys(viAllowedInfo.allowed).length) return [viFilterBaseEntries, viAlwaysFilteredEntries];

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
          var posRaw = String(entry.pos_raw || "").trim().toLowerCase();
          if (viAllowedInfo.allowed[posRaw]) {
            hasAllowedMatch = true;
            groupPrimary.push(entry);
          } else if (VIETNAMESE_XPOS_FILTER_EXEMPT_POS[posRaw]) {
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

    var koAlwaysFilteredSplit = splitEntriesByAlwaysFiltered(baseEntries, buildAlwaysFilteredPosMap(ALWAYS_FILTERED_POS, lang));
    var koFilterBaseEntries = koAlwaysFilteredSplit[0];
    var koAlwaysFilteredEntries = koAlwaysFilteredSplit[1];
    if (!koFilterBaseEntries.length) return [[], koAlwaysFilteredEntries];
    if (koFilterBaseEntries.length <= 1) return [koFilterBaseEntries, koAlwaysFilteredEntries];
    if (!Array.isArray(xposTags) || !xposTags.length) return [koFilterBaseEntries, koAlwaysFilteredEntries];

    var allowedInfo = buildKoreanAllowedPosMap(xposTags);
    if (!allowedInfo.has_mapped || !Object.keys(allowedInfo.allowed).length) return [koFilterBaseEntries, koAlwaysFilteredEntries];

    function splitByAllowed(allowedMap) {
      if (!allowedMap || !Object.keys(allowedMap).length) return [[], koFilterBaseEntries.slice()];
      var primary = [];
      var other = [];
      for (var ei = 0; ei < koFilterBaseEntries.length; ei++) {
        var entry = koFilterBaseEntries[ei] || {};
        var posRaw = String(entry.pos_raw || "").trim().toLowerCase();
        if (KOREAN_XPOS_FILTER_EXEMPT_POS[posRaw]) {
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

  DictionaryEngine.prototype.filterEntriesByXpos = function(entries, xposTags) {
    var split = this.filter_entries_by_xpos(entries, xposTags || []);
    return { primary: split[0], other: split[1] };
  };

  DictionaryEngine.prototype.get_xpos_primary_match_info = function(entries, xposTags, opts) {
    var baseEntries = entries ? entries.slice() : [];
    var allowedInfo = buildKoreanAllowedPosMap(xposTags);
    var allowedPos = Object.keys(allowedInfo.allowed).sort();
    var hasMatch = false;
    if (!allowedInfo.has_mapped || !allowedPos.length) {
      hasMatch = true;
    } else {
      for (var ei = 0; ei < baseEntries.length; ei++) {
        var entry = baseEntries[ei] || {};
        var posRaw = String(entry.pos_raw || entry.pos || "").trim().toLowerCase();
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
      veto_reason: ""
    };
  };

  DictionaryEngine.prototype.has_xpos_primary_match = function(entries, xposTags) {
    return !!this.get_xpos_primary_match_info(entries, xposTags).has_match;
  };

  DictionaryEngine.lookupKey = lookupKey;
  DictionaryEngine.lookupKeys = lookupKeys;
  DictionaryEngine.etymKey = etymKey;
  DictionaryEngine.splitUposTags = splitUposTags;
  DictionaryEngine._hydrateEntry = hydrateEntry;
  DictionaryEngine._ensureHydrated = ensureHydrated;
  window.DictionaryLanguageRules = window.DictionaryLanguageRules || {};
  window.DictionaryLanguageRules.rules = LANGUAGE_SPECIFIC_RULES;
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
  DictionaryEngine.prototype.loadCompactIndex = function(hwObj, fwObj, dbAliasMap) {
    this._compact_mode = true;
    this._hw_index = hwObj || Object.create(null);
    this._fw_index = fwObj || Object.create(null);
    this._db_alias_map = dbAliasMap || Object.create(null);
    // Keep standard indexes empty so non-compact paths return nothing
    this._by_word = Object.create(null);
    this._form_index = Object.create(null);
  };

  // Bounded codepoint-level Levenshtein. Returns maxD+1 if distance exceeds maxD.
  function _boundedCodepointEdit(a, b, maxD) {
    var la = a.length, lb = b.length;
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
      var tmp = prev; prev = curr; curr = tmp;
    }
    return prev[lb];
  }

  function _toCodepointsNFD(s) {
    return Array.from(String(s || "").normalize("NFD"));
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
  DictionaryEngine.prototype.fuzzyLookupKeysTiered = function(word, opts) {
    if (!this._compact_mode) return { tier: -1, stubs: [] };
    opts = opts || {};
    var maxTier = typeof opts.maxTier === "number" ? opts.maxTier : 3;
    var maxStubs = typeof opts.maxStubs === "number" ? opts.maxStubs : 50;
    var surface = String(word || "").trim();
    if (!surface) return { tier: -1, stubs: [] };
    var normQuery = lookupKey(surface, this._lang_code);
    if (!normQuery) return { tier: -1, stubs: [] };
    var qCps = _toCodepointsNFD(normQuery);
    if (!qCps.length) return { tier: -1, stubs: [] };

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
          uid = "hw:" + alias + ":" + eid;
          if (seen[uid]) continue;
          seen[uid] = true;
          stubs.push({
            _winner_ref: true,
            storage_kind: (aliasMap[alias] === "custom" || alias === "customdb") ? "custom" : "sqlite",
            db_alias: alias,
            entry_row_id: eid,
            match_kind: "headword",
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
          uid = "fw:" + alias + ":" + eid + ":" + fid;
          if (seen[uid]) continue;
          seen[uid] = true;
          stubs.push({
            _winner_ref: true,
            storage_kind: (aliasMap[alias] === "custom" || alias === "customdb") ? "custom" : "sqlite",
            db_alias: alias,
            entry_row_id: eid,
            form_row_id: fid,
            match_kind: "form",
            match_key: key,
            headword: key,
            fuzzy_tier: tier
          });
        }
      }
      if (stubs.length) return { tier: tier, stubs: stubs };
    }
    return { tier: -1, stubs: [] };
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
  DictionaryEngine.prototype.injectGeminiKey = function(normalizedKey, entryId, dbAlias, matchKind) {
    if (!this._compact_mode) return;
    var key = String(normalizedKey || "");
    var eid = parseInt(entryId, 10);
    var alias = String(dbAlias || "customdb");
    if (!key || !(eid > 0)) return;
    void matchKind;  // currently only headword injection is needed
    if (!this._hw_index[key]) this._hw_index[key] = [];
    var existing = this._hw_index[key];
    for (var i = 0; i < existing.length; i++) {
      if (existing[i][0] === alias && existing[i][1] === eid) return;  // already present
    }
    this._hw_index[key].push([alias, eid]);
  };

  /**
   * Remove a custom entry key from the compact headword index.
   * Call after deleting a Gemini entry.
   * @param {string} normalizedKey
   * @param {number} entryId
   */
  DictionaryEngine.prototype.removeCompactKey = function(normalizedKey, entryId) {
    if (!this._compact_mode) return;
    var key = String(normalizedKey || "");
    var eid = parseInt(entryId, 10);
    if (!key || !this._hw_index[key]) return;
    this._hw_index[key] = this._hw_index[key].filter(function(pair) {
      return pair[1] !== eid;
    });
    if (!this._hw_index[key].length) delete this._hw_index[key];
  };

  // Override _lookup_all_raw to use compact index when in compact mode.
  // Returns winner ref stubs rather than full entry objects.
  var _origLookupAllRaw = DictionaryEngine.prototype._lookup_all_raw;
  DictionaryEngine.prototype._lookup_all_raw = function(word) {
    if (!this._compact_mode) return _origLookupAllRaw.call(this, word);
    var surface = String(word || "").trim();
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
          var uid = "hw:" + alias + ":" + eid;
          if (seen[uid]) continue;
          seen[uid] = true;
          stubs.push({
            _winner_ref: true,
            storage_kind: (this._db_alias_map[alias] === "custom" || alias === "customdb") ? "custom" : "sqlite",
            db_alias: alias,
            entry_row_id: eid,
            match_kind: "headword",
            match_key: key,
            headword: surface  // placeholder so DP lemma checks don't crash
          });
        }
      }
      var fwHits = this._fw_index[key];
      if (fwHits) {
        for (var fi = 0; fi < fwHits.length; fi++) {
          var falias = fwHits[fi][0];
          var feid = fwHits[fi][1];
          var ffid = fwHits[fi][2];
          var fuid = "fw:" + falias + ":" + feid + ":" + ffid;
          if (seen[fuid]) continue;
          seen[fuid] = true;
          stubs.push({
            _winner_ref: true,
            storage_kind: (this._db_alias_map[falias] === "custom" || falias === "customdb") ? "custom" : "sqlite",
            db_alias: falias,
            entry_row_id: feid,
            form_row_id: ffid,
            match_kind: "form",
            match_key: key,
            headword: surface  // placeholder
          });
        }
      }
    }
    return stubs;
  };

  // Override _entry_to_fill to wrap winner ref stubs in compact mode.
  // The client extracts the _winner_ref from fills to build the hydrate request.
  var _origEntryToFill = DictionaryEngine.prototype._entry_to_fill;
  DictionaryEngine.prototype._entry_to_fill = function(entry, text) {
    if (!this._compact_mode || !entry || !entry._winner_ref) {
      return _origEntryToFill.call(this, entry, text);
    }
    var surfaceText = String(text || "");
    return {
      text: surfaceText,
      head: surfaceText,
      roman: "",
      senses: EMPTY_ARRAY,
      pos: "",
      source: "KAIKKI",
      _winner_ref: entry  // full ref stub; extracted by client after hydration
    };
  };

  function collectHydratedVariantTexts(entry) {
    var out = [];
    var seen = Object.create(null);

    function add(raw) {
      var text = String(raw || "").trim();
      if (!text || seen[text]) return;
      seen[text] = true;
      out.push(text);
    }

    var forms = (entry && entry.forms && typeof entry.forms === "object") ? entry.forms : {};
    var formKeys = ["kanji", "readings", "alt", "hanja", "hangeul", "cjk"];
    for (var i = 0; i < formKeys.length; i++) {
      var values = forms[formKeys[i]];
      if (!Array.isArray(values)) continue;
      for (var j = 0; j < values.length; j++) add(values[j]);
    }

    var formsMeta = (entry && entry.forms_meta && typeof entry.forms_meta === "object") ? entry.forms_meta : {};
    var metaLists = ["kanji", "readings"];
    for (var li = 0; li < metaLists.length; li++) {
      var rows = formsMeta[metaLists[li]];
      if (!Array.isArray(rows)) continue;
      for (var ri = 0; ri < rows.length; ri++) {
        var row = rows[ri];
        if (row && typeof row === "object") add(row.form);
      }
    }

    var metaMaps = ["kanji_by_form", "readings_by_form"];
    for (var mi = 0; mi < metaMaps.length; mi++) {
      var mapping = formsMeta[metaMaps[mi]];
      if (!mapping || typeof mapping !== "object") continue;
      var mappingKeys = Object.keys(mapping);
      for (var mk = 0; mk < mappingKeys.length; mk++) add(mappingKeys[mk]);
    }

    return out;
  }

  function collectHydratedFormRows(entry) {
    var out = [];
    var seen = Object.create(null);

    function add(formText, tagsStr, formRoman, displayText) {
      var text = String(formText || "").trim();
      var commentary = String(tagsStr || "").trim();
      var roman = String(formRoman || "").trim();
      var display = String(displayText || text).trim() || text;
      if (!text) return;
      var key = text + "\t" + commentary + "\t" + roman + "\t" + display;
      if (seen[key]) return;
      seen[key] = true;
      out.push({
        form_text: text,
        tags: commentary,
        form_roman: roman,
        display_text: display
      });
    }

    var forms = (entry && entry.forms && typeof entry.forms === "object") ? entry.forms : {};
    var rows = Array.isArray(forms.rows) ? forms.rows : [];
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      if (Array.isArray(row)) {
        add(row[0], row[1], row[2], row[0]);
      } else if (row && typeof row === "object") {
        add(row.word || row.form || row.headword || row.form_text, row.commentary || row.tags, row.romanization || row.reading || row.form_roman, row.display_text || row.word || row.form || row.headword || row.form_text);
      }
    }

    var matchedForms = Array.isArray(entry && entry._matched_forms) ? entry._matched_forms : [];
    for (var j = 0; j < matchedForms.length; j++) {
      var matched = matchedForms[j];
      if (!matched || typeof matched !== "object") continue;
      add(matched.form_text || matched.display_text, matched.tags, matched.form_roman, matched.display_text || matched.form_text);
    }

    return out;
  }

  DictionaryEngine.prototype._index_hydrated_forms = function(entry, word, foldKey, byWord, formIndex) {
    var variantTexts = collectHydratedVariantTexts(entry);
    for (var vi = 0; vi < variantTexts.length; vi++) {
      var variant = variantTexts[vi];
      if (!variant || variant === word) continue;
      var variantKeys = lookupKeys(variant, this._lang_code);
      for (var vki = 0; vki < variantKeys.length; vki++) {
        var variantKey = variantKeys[vki];
        if (!variantKey || variantKey === foldKey) continue;
        if (!byWord[variantKey]) byWord[variantKey] = [];
        byWord[variantKey].push(entry);
      }
    }

    var formRows = collectHydratedFormRows(entry);
    for (var i = 0; i < formRows.length; i++) {
      var row = formRows[i];
      var formText = String(row.form_text || "").trim();
      if (!formText || formText === word) continue;
      var tagsStr = String(row.tags || "").trim();
      var formRoman = String(row.form_roman || "").trim();
      var tags = tagsStr ? tagsStr.split(";").filter(Boolean) : [];
      applyLanguageFormRules(this._lang_code, entry, formText, tags);
      var internedMorph = internMorphArray(tags);
      var formTexts = getLanguageFormIndexTexts(this._lang_code, formText, tags);
      for (var ft = 0; ft < formTexts.length; ft++) {
        var indexFormText = String(formTexts[ft] || "").trim();
        if (!indexFormText || indexFormText === word) continue;
        var formKeys = lookupKeys(indexFormText, this._lang_code);
        for (var fki = 0; fki < formKeys.length; fki++) {
          var formKey = formKeys[fki];
          if (!formKey || formKey === foldKey) continue;
          if (!formIndex[formKey]) formIndex[formKey] = [];
          var formHit = {
            lemma: word,
            form_text: indexFormText,
            morph: internedMorph,
            entry_ref: entry
          };
          var displayText = String(row.display_text || formText || indexFormText).trim();
          if (displayText && displayText !== indexFormText) formHit.form_display_text = displayText;
          if (formRoman) formHit.form_roman = formRoman;
          formIndex[formKey].push(formHit);
        }
      }
    }
  };

  /**
   * Legacy hydrated relookup substrate. The active hybrid flow no longer calls
   * this; keep it only for disconnected old paths.
   */
  DictionaryEngine.prototype.beginHydratedLookup = function(entryStore) {
    if (!this._compact_mode) return;
    this._compact_mode = false;
    this._saved_by_word = this._by_word;
    this._saved_form_index = this._form_index;
    var byWord = Object.create(null);
    var formIndex = Object.create(null);
    var keys = Object.keys(entryStore || {});
    for (var i = 0; i < keys.length; i++) {
      var entry = entryStore[keys[i]];
      if (!entry || typeof entry !== "object") continue;
      var hw = String(entry.headword || entry.head || "").trim();
      if (!hw) continue;
      var foldKey = lookupKey(hw, this._lang_code);
      var nkeys = lookupKeys(hw, this._lang_code);
      for (var ki = 0; ki < nkeys.length; ki++) {
        var nk = nkeys[ki];
        if (!byWord[nk]) byWord[nk] = [];
        byWord[nk].push(entry);
      }
      // Also index by surface_form if different
      var sf = String(entry.surface_form || "").trim();
      if (sf && sf !== hw) {
        var sfkeys = lookupKeys(sf, this._lang_code);
        for (var si = 0; si < sfkeys.length; si++) {
          if (!byWord[sfkeys[si]]) byWord[sfkeys[si]] = [];
          byWord[sfkeys[si]].push(entry);
        }
      }
      this._index_hydrated_forms(entry, hw, foldKey, byWord, formIndex);
    }
    this._by_word = byWord;
    this._form_index = formIndex;
  };

  DictionaryEngine.prototype.endHydratedLookup = function() {
    if (this._saved_by_word) {
      this._by_word = this._saved_by_word;
      this._form_index = this._saved_form_index;
      this._saved_by_word = null;
      this._saved_form_index = null;
      this._compact_mode = true;
    }
  };

  window.DictionaryEngine = DictionaryEngine;
})();
