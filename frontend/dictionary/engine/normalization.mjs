import { splitMorphTags } from './entry-filters.mjs';
import { normalizationState } from './normalization.state.mjs';
export function internString(s) {
  if (!s) return normalizationState.EMPTY_STRING;
  var existing = normalizationState._internTable[s];
  if (existing !== undefined) return existing;
  normalizationState._internTable[s] = s;
  return s;
}

// Intern table for morph tag arrays — common patterns like ["stem"], ["plural"] etc.
export function internMorphArray(tags) {
  if (!tags || !tags.length) return normalizationState.EMPTY_ARRAY;
  var key = tags.join(';');
  var existing = normalizationState._morphArrayTable[key];
  if (existing !== undefined) return existing;
  // Intern individual tag strings too
  var interned = new Array(tags.length);
  for (var i = 0; i < tags.length; i++) {
    interned[i] = internString(tags[i]);
  }
  Object.freeze(interned);
  normalizationState._morphArrayTable[key] = interned;
  return interned;
}
export function normalizePos(raw) {
  return normalizationState.POS_LABELS[raw] || raw;
}
export function isPersianLanguageCode(langValue) {
  var lang = String(langValue || '')
    .trim()
    .toLowerCase();
  return lang === 'fa' || lang === 'persian' || lang.indexOf('fa-') === 0;
}
export function isKoreanLanguageCode(langValue) {
  var lang = String(langValue || '')
    .trim()
    .toLowerCase();
  return lang === 'ko' || lang === 'korean' || lang.indexOf('ko-') === 0;
}
export function getLemmaHintTexts(rawHint, langCode) {
  var out = [];
  var seen = Object.create(null);
  function pushText(raw) {
    var txt = String(raw || '').trim();
    if (!txt || seen[txt]) return;
    seen[txt] = true;
    out.push(txt);
  }
  if (rawHint && typeof rawHint === 'object' && !Array.isArray(rawHint)) {
    var rawVariants = Array.isArray(rawHint.variants) ? rawHint.variants : [];
    for (var i = 0; i < rawVariants.length; i++) pushText(rawVariants[i]);
    if (!out.length && isPersianLanguageCode(langCode)) {
      var rawText = String(rawHint.text || rawHint.lemma || '').trim();
      if (rawText && rawText.indexOf('#') >= 0) {
        var splitParts = rawText
          .split('#')
          .map(function (part) {
            return String(part || '').trim();
          })
          .filter(Boolean);
        for (var j = 0; j < splitParts.length; j++) pushText(splitParts[j]);
      }
    }
    if (!out.length) pushText(rawHint.text || rawHint.lemma || '');
    return out;
  }
  pushText(rawHint || '');
  return out;
}
export function normalizeAffixMarkers(text) {
  var result = '';
  for (var i = 0; i < text.length; i++) {
    if (normalizationState.AFFIX_MARKER_EQUIVALENTS.indexOf(text[i]) >= 0) {
      result += '-';
    } else {
      result += text[i];
    }
  }
  return result;
}
export function applyLookupNormalizationLayer(text, langCode, phase) {
  var norm = String(text || '');
  var layer = window.DictionaryNormalizationLayer;
  if (!layer || typeof layer.normalizeLookupText !== 'function') return norm;
  try {
    return String(
      layer.normalizeLookupText(norm, {
        langCode: String(langCode || '')
          .trim()
          .toLowerCase(),
        phase: String(phase || 'lookup_key')
      }) || ''
    );
  } catch (_e) {
    return norm;
  }
}
export function stripInvisibleComparisonChars(text) {
  var src = String(text || '');
  var layer = window.DictionaryNormalizationLayer;
  if (layer && typeof layer.stripInvisibleComparisonChars === 'function') {
    try {
      return String(layer.stripInvisibleComparisonChars(src) || '');
    } catch (_e) {}
  }
  return src.replace(normalizationState.LOOKUP_INVISIBLE_COMPARISON_RE, '');
}
export function entryHasMorphTag(entry, tagText) {
  var target = String(tagText || '')
    .trim()
    .toLowerCase();
  if (!target) return false;
  var tags = splitMorphTags(entry && entry.morph_info);
  for (var i = 0; i < tags.length; i++) {
    if (tags[i] === target) return true;
  }
  return false;
}
export function cloneEntryWithMorphTag(entry, tagText) {
  var tag = String(tagText || '').trim();
  if (!entry || !tag || entryHasMorphTag(entry, tag)) return entry;
  var clone = {};
  for (var k in entry) {
    if (Object.prototype.hasOwnProperty.call(entry, k)) clone[k] = entry[k];
  }
  var rawMorph = entry.morph_info;
  var morphInfo = Array.isArray(rawMorph) ? rawMorph.slice() : rawMorph ? [String(rawMorph)] : [];
  morphInfo.push(tag);
  clone.morph_info = morphInfo;
  return clone;
}
export function annotateLookupEntries(entries, queryText, langCode) {
  var src = Array.isArray(entries) ? entries : [];
  void queryText;
  void langCode;
  return src.length ? src.slice() : [];
}
export function lookupKey(text, langCode) {
  var raw = String(text || '').trim();
  if (!raw) return '';
  var layer = window.DictionaryNormalizationLayer;
  return String(
    layer.normalizeLookupKeyText(raw, {
      langCode: String(langCode || '')
        .trim()
        .toLowerCase(),
      phase: 'lookup_key'
    }) || ''
  ).trim();
}
export function lookupKeys(text, langCode) {
  var raw = String(text || '').trim();
  if (!raw) return [];
  var layer = window.DictionaryNormalizationLayer;
  var key = String(
    layer.normalizeLookupKeyText(raw, {
      langCode: String(langCode || '')
        .trim()
        .toLowerCase(),
      phase: 'lookup_keys'
    }) || ''
  ).trim();
  return key ? [key] : [];
}
export function buildGraphemeSpanTable(text) {
  var value = String(text || '');
  if (!value) {
    var emptyBoundaryMap = Object.create(null);
    emptyBoundaryMap[0] = 0;
    return {
      spans: [],
      boundary_to_index: emptyBoundaryMap
    };
  }
  var segmenter = new Intl.Segmenter(undefined, {
    granularity: 'grapheme'
  });
  var rows = Array.from(segmenter.segment(value));
  var spans = [];
  var boundaryToIndex = Object.create(null);
  boundaryToIndex[0] = 0;
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var segmentText = String(row.segment || '');
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
export function normalizeKoreanXposTag(rawTag) {
  var tag = String(rawTag || '')
    .trim()
    .toLowerCase();
  if (!tag) return '';
  // Handle parser artifacts like "ecs." or "jxc,".
  return tag.replace(/^[^a-z0-9_]+|[^a-z0-9_]+$/g, '');
}
export function normalizeKoreanXposTags(rawTags) {
  var out = [];
  var seen = Object.create(null);
  var src = Array.isArray(rawTags) ? rawTags : rawTags ? [rawTags] : [];
  for (var i = 0; i < src.length; i++) {
    var tag = normalizeKoreanXposTag(src[i]);
    if (!tag || seen[tag]) continue;
    seen[tag] = true;
    out.push(tag);
  }
  return out;
}
export function buildKoreanAllowedPosMap(rawTags) {
  var tags = normalizeKoreanXposTags(rawTags);
  var allowed = Object.create(null);
  var hasMapped = false;
  for (var i = 0; i < tags.length; i++) {
    var mapped = normalizationState.KOREAN_XPOS_TO_WIKT_POS[tags[i]];
    if (!mapped || !mapped.length) continue;
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
export function initializeNormalization() {
  // ── Memory optimization: shared singletons & interning ──
  normalizationState.EMPTY_ARRAY = Object.freeze([]);
  normalizationState.EMPTY_STRING = '';

  // Intern table for repeated short strings (POS labels, morph tags).
  // V8 already interns object keys, but these are used as *values*.
  normalizationState._internTable = Object.create(null);
  normalizationState._morphArrayTable = Object.create(null);
  normalizationState.POS_LABELS = {
    noun: 'n',
    verb: 'v',
    adj: 'adj',
    adv: 'adv',
    pron: 'pron',
    prep: 'prep',
    postp: 'postp',
    conj: 'conj',
    det: 'det',
    num: 'num',
    intj: 'intj',
    particle: 'ptcl',
    classifier: 'clf',
    prefix: 'pfx',
    suffix: 'sfx',
    affix: 'afx',
    infix: 'ifx',
    interfix: 'itfx',
    circumfix: 'circfx',
    combining_form: 'comb',
    contraction: 'contr',
    phrase: 'phr',
    proverb: 'prov',
    prep_phrase: 'prep.phr',
    character: 'char',
    name: 'name',
    romanization: 'rom',
    root: 'root',
    article: 'art',
    punct: 'punct',
    symbol: 'sym',
    counter: 'ctr',
    adnominal: 'adn',
    circumpos: 'cpos',
    syllable: 'syl',
    '[]': 'unk'
  };
  normalizationState.AFFIX_MARKER_EQUIVALENTS =
    "\uFEFF\u061C\u200E\u200F\u200C\u202A\u202B\u202C\u202D\u202E\u2066\u2067\u2068\u2069\u05BE\u05F3\u2012\u25CC'.^\u3320\u2810\u2818\u2830\u211E\u2205&(),\u00A9\u3030";
  normalizationState.LOOKUP_INVISIBLE_COMPARISON_RE =
    /[\u061C\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFE00-\uFE0F\uFEFF]|\uDB40[\uDD00-\uDDEF]/g;
  normalizationState.NOUN_AFFIX_POS = [
    'suffix',
    'prefix',
    'affix',
    'infix',
    'interfix',
    'circumfix',
    'combining_form'
  ];
  normalizationState.LANGUAGE_SPECIFIC_RULES = {
    ja: {
      upos_extra_pos: {
        // "AUX": ["suffix"],
        // "CCONJ": ["suffix"],
        // "SCONJ": ["suffix"]
      }
    },
    vi: {
      on_form_seen: function (entry, formText, tags) {
        var text = String(formText || '').trim();
        if (!text || !entry) return;
        var hasCjk = false;
        for (var i = 0; i < (tags || []).length; i++) {
          var tag = String(tags[i] || '')
            .trim()
            .toLowerCase();
          if (tag === 'cjk' || tag === 'sinitic') {
            hasCjk = true;
            break;
          }
        }
        if (!hasCjk) return;
        var existing = Array.isArray(entry.vietnamese_cjk_variants) ? entry.vietnamese_cjk_variants : [];
        if (!Array.isArray(entry.vietnamese_cjk_variants)) {
          entry.vietnamese_cjk_variants = existing;
        }
        if (existing.indexOf(text) < 0) existing.push(text);
      },
      get_entry_hanja_forms: function (entry) {
        var raw = (entry && entry.vietnamese_cjk_variants) || [];
        if (!Array.isArray(raw)) return [];
        var out = [];
        var seen = Object.create(null);
        for (var i = 0; i < raw.length; i++) {
          var txt = String(raw[i] || '').trim();
          if (!txt || seen[txt]) continue;
          seen[txt] = true;
          out.push(txt);
        }
        return out;
      }
    },
    ko: {
      get_form_index_texts: function (formText, tags) {
        var text = String(formText || '').trim();
        if (!text) return [];
        var isEumhun = false;
        for (var i = 0; i < (tags || []).length; i++) {
          var tag = String(tags[i] || '')
            .trim()
            .toLowerCase();
          if (tag === 'eumhun') {
            isEumhun = true;
            break;
          }
        }
        if (!isEumhun) return [text];

        // Eumhun forms are often strings like "폐할 폐".
        // Index the final Hangul syllable used in running text.
        for (var ci = text.length - 1; ci >= 0; ci--) {
          var code = text.charCodeAt(ci);
          if (code >= 0xac00 && code <= 0xd7a3) {
            return [text.charAt(ci)];
          }
        }
        for (var ti = text.length - 1; ti >= 0; ti--) {
          var tail = text.charAt(ti);
          if (tail.trim()) return [tail];
        }
        return [text];
      },
      on_form_seen: function (entry, formText, tags) {
        var text = String(formText || '').trim();
        if (!text || !entry) return;
        var hasHanja = false;
        var hasHangeul = false;
        for (var i = 0; i < (tags || []).length; i++) {
          var tag = String(tags[i] || '')
            .trim()
            .toLowerCase();
          if (tag === 'hanja') {
            hasHanja = true;
          } else if (tag === 'hangeul') {
            hasHangeul = true;
          }
        }
        if (hasHanja) {
          var existing = Array.isArray(entry.korean_hanja_variants) ? entry.korean_hanja_variants : [];
          if (!Array.isArray(entry.korean_hanja_variants)) {
            entry.korean_hanja_variants = existing;
          }
          if (existing.indexOf(text) < 0) existing.push(text);
        }
        if (hasHangeul) {
          var hExisting = Array.isArray(entry.korean_hangeul_variants) ? entry.korean_hangeul_variants : [];
          if (!Array.isArray(entry.korean_hangeul_variants)) {
            entry.korean_hangeul_variants = hExisting;
          }
          if (hExisting.indexOf(text) < 0) hExisting.push(text);
        }
      },
      get_entry_hanja_forms: function (entry) {
        var raw = (entry && entry.korean_hanja_variants) || [];
        if (!Array.isArray(raw)) return [];
        var out = [];
        var seen = Object.create(null);
        for (var i = 0; i < raw.length; i++) {
          var txt = String(raw[i] || '').trim();
          if (!txt || seen[txt]) continue;
          seen[txt] = true;
          out.push(txt);
        }
        return out;
      },
      get_entry_hangeul_forms: function (entry) {
        var raw = (entry && entry.korean_hangeul_variants) || [];
        if (!Array.isArray(raw)) return [];
        var out = [];
        var seen = Object.create(null);
        for (var i = 0; i < raw.length; i++) {
          var txt = String(raw[i] || '').trim();
          if (!txt || seen[txt]) continue;
          seen[txt] = true;
          out.push(txt);
        }
        return out;
      }
    }
  };
  normalizationState.UPOS_TO_KAIKKI_POS = {
    NOUN: ['noun', 'classifier', 'name', 'contraction', 'counter'].concat(normalizationState.NOUN_AFFIX_POS),
    VERB: ['verb'],
    ADJ: ['adj', 'adnominal'],
    ADV: ['adv'],
    PROPN: ['name', 'noun'].concat(normalizationState.NOUN_AFFIX_POS),
    ADP: ['prep', 'postp', 'prep_phrase', 'particle', 'circumpos'],
    AUX: ['verb'],
    CCONJ: ['conj'],
    SCONJ: ['conj'],
    DET: ['det', 'article', 'adnominal'],
    PRON: ['pron'],
    NUM: ['num', 'counter'],
    PART: ['particle'],
    INTJ: ['intj'],
    PUNCT: ['punct', 'symbol'],
    SYM: ['symbol', 'punct'],
    X: ['syllable', '[]']
  };
  normalizationState.FILTER_EXEMPT_POS = {
    proverb: true,
    phrase: true,
    prep_phrase: true
  };
  normalizationState.ALWAYS_FILTERED_POS = {
    character: true,
    romanization: true,
    root: true,
    syllable: true,
    punct: true,
    symbol: true
  };
  normalizationState.ALWAYS_FILTERED_MORPH_TAGS = {
    // "alternative": true,
    // "redirect": true,
    // "hangeul": true,
    // "eumhun": true,
    // "syllable": true,
    // "syl": true
  };
  normalizationState.CHARACTER_FILTER_EXEMPT_CJK_LANGS = {
    zh: true,
    'zh-hant': true,
    ja: true,
    ko: true,
    yue: true,
    wuu: true,
    lzh: true
  };

  // Korean KAIST XPOS -> allowed Wiktionary POS buckets.
  // Keys mirror the previous Korean-specific pipeline.
  normalizationState.KOREAN_XPOS_TO_WIKT_POS = {
    ncn: ['noun', 'name', 'suffix', 'counter'].concat(normalizationState.NOUN_AFFIX_POS),
    ncpa: ['noun', 'verb'],
    ncps: ['noun', 'adj', 'adv'],
    nbn: ['noun'],
    nbu: ['noun', 'counter'],
    nnc: ['num', 'counter'],
    nno: ['num', 'counter'],
    npd: ['pron'],
    npp: ['pron'],
    nq: ['name', 'noun'],
    pvg: ['verb'],
    pvd: ['verb'],
    paa: ['adj'],
    pad: ['det', 'adnominal'],
    px: ['verb', 'adj'],
    ecc: ['suffix', 'particle', 'conj'],
    ecs: ['suffix', 'particle'],
    ecx: ['suffix', 'particle'],
    ef: ['suffix', 'particle'],
    ep: ['suffix', 'particle'],
    etm: ['suffix', 'particle'],
    etn: ['suffix', 'particle'],
    jca: ['particle', 'postp', 'circumpos'],
    jcc: ['particle', 'postp', 'circumpos'],
    jcj: ['particle', 'postp', 'circumpos', 'conj'],
    jcm: ['particle', 'postp', 'circumpos'],
    jco: ['particle', 'postp', 'circumpos'],
    jcr: ['particle', 'postp', 'circumpos'],
    jcs: ['particle', 'postp', 'circumpos'],
    jct: ['particle', 'postp', 'circumpos'],
    jp: ['particle', 'postp', 'circumpos'],
    jcv: ['particle', 'postp', 'circumpos'],
    jxc: ['particle', 'postp', 'circumpos'],
    jxf: ['particle', 'postp', 'circumpos'],
    jxt: ['particle', 'postp', 'circumpos'],
    mad: ['adv'],
    mag: ['adv'],
    maj: ['adv', 'conj'],
    mma: ['det', 'adnominal'],
    mmd: ['det', 'adnominal'],
    xp: ['prefix', 'suffix', 'affix'],
    xsa: ['suffix', 'adj', 'affix'],
    xsm: ['suffix', 'adv', 'affix'],
    xsn: ['suffix', 'particle', 'affix'],
    xsv: ['suffix', 'verb', 'affix'],
    ii: ['intj'],
    sf: ['syllable', '[]', 'contraction'],
    sl: ['syllable', '[]', 'contraction'],
    sp: ['syllable', '[]', 'contraction'],
    sr: ['syllable', '[]', 'contraction'],
    su: ['syllable', '[]', 'contraction'],
    f: ['syllable', '[]', 'contraction'],
    _: ['syllable', '[]', 'contraction']
  };
  normalizationState.KOREAN_XPOS_FILTER_EXEMPT_POS = {
    phrase: true,
    proverb: true,
    prep_phrase: true
  };

  // Vietnamese XPOS -> allowed Wiktionary POS buckets.
  // Ported directly from vietnamese/dictionary.py.
  normalizationState.VIETNAMESE_XPOS_TO_WIKT_POS = {
    N: ['noun'],
    Np: ['name'],
    Nc: ['classifier'],
    Nu: ['classifier', 'noun'],
    Nb: ['noun'],
    Ny: ['name', 'noun'],
    V: ['verb'],
    A: ['adj'],
    P: ['pron'],
    R: ['adv'],
    L: ['det'],
    M: ['num'],
    E: ['prep'],
    C: ['conj'],
    CC: ['conj'],
    I: ['intj'],
    T: ['particle'],
    S: ['affix', 'prefix', 'suffix', 'combining_form'],
    Y: ['name', 'noun'],
    CH: ['punct', 'symbol'],
    X: [],
    _: []
  };
  normalizationState.VIETNAMESE_XPOS_FILTER_EXEMPT_POS = {
    proverb: true,
    phrase: true,
    punct: true,
    symbol: true
  };
  normalizationState.VIETNAMESE_XPOS_ALWAYS_FILTERED_POS = {
    character: true,
    romanization: true
  };
  return true;
}
