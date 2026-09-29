/**
 * dictionary_normalization_layer.js - Modular dictionary lookup normalization.
 *
 * Shared by the hybrid client lookup path and by tools/normalize_keys.js,
 * which uses this exact file to precompute SQLite and compact-index keys.
 *
 * This file is still also loaded for:
 *   - normalizeVisibleComparisonText / stripInvisibleComparisonChars (display)
 *   - Language detection helpers (isArabicLanguageCode, etc.)
 *   - Sanskrit transliteration helpers
 *   - normalizeLookupAffixMarkers (display comparisons)
 */
(function() {
  "use strict";

  var ruleOrder = [];
  var ruleMap = Object.create(null);
  var enabledState = Object.create(null);
  var AFFIX_MARKER_EQUIVALENTS = "\uFEFF\u061C\u200E\u200F\u200C\u202A\u202B\u202C\u202D\u202E\u2066\u2067\u2068\u2069\u05BE\u05F3\u2012\u25CC'.^\u3320\u2810\u2818\u2830\u211E\u2205&(),\u00A9\u3030";
  var ANCIENT_GREEK_APOSTROPHE_EQUIVALENTS_RE = /[\u2018\u2019\u02BC\u02BD\u1FBD\u1FBF\uFF07]/g;
  var ANCIENT_GREEK_FINAL_SIGMA_RE = /\u03C2/g;
  var ANCIENT_GREEK_IOTA_SUBSCRIPT_RE = /[\u0345\u1FBE]/g;
  var ANCIENT_GREEK_STRIP_MARKS_RE = /[\u0300\u0301\u0313\u0314\u0342]/g;
  var ANCIENT_GREEK_EDITORIAL_MARKS_RE = /[\u0304\u0306]/g;
  var GREEK_DIAERESIS_RE = /\u0308/g;
  var GREEK_LUNATE_SIGMA_RE = /[\u03F2\u03F9]/g;
  var CJK_VARIATION_SELECTORS_RE = /[\uFE00-\uFE0F]|\uDB40[\uDD00-\uDDEF]/g;
  var ARABIC_STRIP_MARKS_RE = /[\u0610-\u061A\u0640\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E4\u06E7-\u06E8\u06EA-\u06ED\u08CA-\u08E1\u08E3-\u08FF]/g;
  var INVISIBLE_FORMAT_CONTROLS_RE = /[\u061C\u200E\u200F\u202A-\u202E\u2066-\u2069\uFEFF]/g;
  var LOOKUP_INVISIBLE_COMPARISON_RE = /[\u061C\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFE00-\uFE0F\uFEFF]|\uDB40[\uDD00-\uDDEF]/g;
  var HEBREW_STRIP_MARKS_RE = /[\u0591-\u05AF\u05B0-\u05BD\u05BF\u05C1\u05C2\u05C4\u05C5\u05C7]/g;
  var INDIC_ZERO_WIDTH_RE = /[\u200B\u200C\u200D]/g;
  var LATIN_COMBINING_MARKS_RE = /[\u0300-\u036F]/g;
  var THAI_ZWSP_RE = /\u200B/g;
  var URDU_JOIN_CONTROLS_RE = /[\u200C\u200D]/g;
  var ARABIC_FOLD_MAP = {
    "\u0623": "\u0627",
    "\u0625": "\u0627",
    "\u0622": "\u0627",
    "\u0671": "\u0627",
    "\u0649": "\u064A",
    "\u0629": "\u0647"
  };
  var PERSIAN_FOLD_MAP = {
    "\u06CC": "\u064A",
    "\u06D2": "\u064A",
    "\u06A9": "\u0643",
    "\u06C0": "\u0647",
    "\u06C1": "\u0647",
    "\u06C2": "\u0647"
  };
  var URDU_FOLD_MAP = {
    "\u06CC": "\u064A",
    "\u06A9": "\u0643"
  };
  var TURKISH_CASE_PREP_MAP = {
    "\u0130": "i",
    "I": "\u0131"
  };
  var SANSKRIT_SLP1_TO_IAST_MAP = {
    "A": "\u0101",
    "I": "\u012b",
    "U": "\u016b",
    "f": "\u1e5b",
    "F": "\u1e5d",
    "x": "\u1e37",
    "X": "\u1e39",
    "E": "ai",
    "O": "au",
    "K": "kh",
    "G": "gh",
    "N": "\u1e45",
    "C": "ch",
    "J": "jh",
    "Y": "\u00f1",
    "w": "\u1e6d",
    "W": "\u1e6dh",
    "q": "\u1e0d",
    "Q": "\u1e0dh",
    "R": "\u1e47",
    "T": "th",
    "D": "dh",
    "P": "ph",
    "B": "bh",
    "S": "\u015b",
    "z": "\u1e63",
    "M": "\u1e43",
    "H": "\u1e25",
    "~": "m\u0310",
    "'": "'"
  };
  var SANSKRIT_IAST_TO_SLP1_SEQUENCES = [
    ["k\u1e63", "kz"],
    ["j\u00f1", "jY"],
    ["\u015br", "Sr"],
    ["ai", "E"],
    ["au", "O"],
    ["kh", "K"],
    ["gh", "G"],
    ["ch", "C"],
    ["jh", "J"],
    ["\u1e6dh", "W"],
    ["\u1e0dh", "Q"],
    ["th", "T"],
    ["dh", "D"],
    ["ph", "P"],
    ["bh", "B"],
    ["m\u0310", "~"]
  ];
  // Multi-char Roman→IAST folds. Order matters — run first, before single-char map.
  var SANSKRIT_ROMAN_MULTI_FOLDS = [
    ["r\u0325\u0304", "\u1E5D"],  // ISO vocalic ṝ (r + combining ring + macron)
    ["r\u0325",        "\u1E5B"],  // ISO vocalic ṛ
    ["l\u0325\u0304", "\u1E39"],  // ISO vocalic ḹ
    ["l\u0325",        "\u1E37"],  // ISO vocalic ḷ
    ["m\u0310",        "\u1E43"],  // candrabindu on m → ṃ
    ["a\u00ED", "ai"], ["a\u00FA", "au"], ["a\u00EC", "ai"], ["a\u00F9", "au"]
  ];
  var SANSKRIT_ROMAN_SINGLE_FOLDS = {
    "\u1E41": "\u1E43",   // ṁ (ISO 15919 anusvāra) → ṃ
    "\u0113": "e",        // ē → e
    "\u014D": "o",        // ō → o
    "\u1E17": "e",        // ḗ → e
    "\u1E53": "o",        // ṓ → o
    "\u1E96": "\u1E25",   // ẖ jihvāmūlīya → ḥ
    "\u1CF5": "\u1E25",   // Vedic jihvāmūlīya
    "\u1CF6": "\u1E25",   // Vedic upadhmānīya
    "\u00E1": "a", "\u00E9": "e", "\u00ED": "i", "\u00F3": "o", "\u00FA": "u",
    "\u00E0": "a", "\u00E8": "e", "\u00EC": "i", "\u00F2": "o", "\u00F9": "u",
    "`": "'", "\u2018": "'", "\u2019": "'", "\u02BC": "'"
  };
  var SANSKRIT_SUPERSCRIPT_STRIP_RE = /[\u00B2\u00B3\u00B9\u2070-\u2079\u1D2C-\u1D6A\u1D9B-\u1DBF]/g;
  var SANSKRIT_COMBINING_STRIP_RE = /[\u0300-\u036F]/g;

  var SANSKRIT_ANUSVARA_PATTERNS = [
    [/\u1E45(?=[kg]h?)/g, "\u1E43"],  // ṅ before k/g → ṃ
    [/\u00F1(?=[cj]h?)/g, "\u1E43"],  // ñ before c/j → ṃ
    [/\u1E47(?=[\u1E6D\u1E0D]h?)/g, "\u1E43"],  // ṇ before ṭ/ḍ → ṃ
    [/n(?=[td]h?)/g, "\u1E43"],       // n before t/d → ṃ
    [/m(?=[pb]h?)/g, "\u1E43"]        // m before p/b → ṃ
  ];

  var SANSKRIT_IAST_TO_SLP1_CHAR_MAP = {
    "a": "a",
    "\u0101": "A",
    "i": "i",
    "\u012b": "I",
    "u": "u",
    "\u016b": "U",
    "\u1e5b": "f",
    "\u1e5d": "F",
    "\u1e37": "x",
    "\u1e39": "X",
    "e": "e",
    "o": "o",
    "\u1e43": "M",
    "\u1e41": "M",
    "\u1e25": "H",
    "'": "'",
    "\u2019": "'",
    "k": "k",
    "g": "g",
    "\u1e45": "N",
    "c": "c",
    "j": "j",
    "\u00f1": "Y",
    "\u1e6d": "w",
    "\u1e0d": "q",
    "\u1e47": "R",
    "t": "t",
    "d": "d",
    "n": "n",
    "p": "p",
    "b": "b",
    "m": "m",
    "y": "y",
    "r": "r",
    "l": "l",
    "v": "v",
    "\u015b": "S",
    "\u1e63": "z",
    "s": "s",
    "h": "h"
  };

  function normalizeLangCode(langValue) {
    return String(langValue || "").trim().toLowerCase();
  }

  function isArabicLanguageCode(langValue) {
    var lang = normalizeLangCode(langValue);
    return (
      lang === "ar" ||
      lang === "ara" ||
      lang === "arabic" ||
      lang.indexOf("ar-") === 0 ||
      lang.indexOf("ara-") === 0
    );
  }

  function isChineseLanguageCode(langValue) {
    var lang = normalizeLangCode(langValue);
    return (
      lang === "zh" ||
      lang === "chinese" ||
      lang === "zh-hant" ||
      lang === "traditional-chinese" ||
      lang.indexOf("zh-") === 0 ||
      lang === "lzh" ||
      lang === "classical" ||
      lang === "classical-chinese"
    );
  }

  function isJapaneseLanguageCode(langValue) {
    var lang = normalizeLangCode(langValue);
    return (
      lang === "ja" ||
      lang === "japanese" ||
      lang.indexOf("ja-") === 0
    );
  }

  function isPersianLanguageCode(langValue) {
    var lang = normalizeLangCode(langValue);
    return (
      lang === "fa" ||
      lang === "persian" ||
      lang.indexOf("fa-") === 0
    );
  }

  function isUrduLanguageCode(langValue) {
    var lang = normalizeLangCode(langValue);
    return (
      lang === "ur" ||
      lang === "urdu" ||
      lang.indexOf("ur-") === 0
    );
  }

  function isArabicScriptLanguageCode(langValue) {
    return (
      isArabicLanguageCode(langValue) ||
      isPersianLanguageCode(langValue) ||
      isUrduLanguageCode(langValue)
    );
  }

  function isHebrewLanguageCode(langValue) {
    var lang = normalizeLangCode(langValue);
    return (
      lang === "he" ||
      lang === "hebrew" ||
      lang.indexOf("he-") === 0
    );
  }

  function isOldEnglishLanguageCode(langValue) {
    var lang = normalizeLangCode(langValue);
    return (
      lang === "ang" ||
      lang === "old-english" ||
      lang === "oldenglish" ||
      lang.indexOf("ang-") === 0 ||
      lang.indexOf("old-english-") === 0 ||
      lang.indexOf("oldenglish-") === 0
    );
  }

  function isAncientGreekLanguageCode(langValue) {
    var lang = normalizeLangCode(langValue);
    return (
      lang === "grc" ||
      lang === "ancient-greek" ||
      lang === "ancientgreek" ||
      lang.indexOf("grc-") === 0 ||
      lang.indexOf("ancient-greek-") === 0 ||
      lang.indexOf("ancientgreek-") === 0
    );
  }

  function isModernGreekLanguageCode(langValue) {
    var lang = normalizeLangCode(langValue);
    return (
      lang === "el" ||
      lang === "ell" ||
      lang === "greek" ||
      lang === "modern-greek" ||
      lang === "moderngreek" ||
      lang.indexOf("el-") === 0 ||
      lang.indexOf("ell-") === 0 ||
      lang.indexOf("modern-greek-") === 0 ||
      lang.indexOf("moderngreek-") === 0
    );
  }

  function isIndicJoinControlLanguageCode(langValue) {
    var lang = normalizeLangCode(langValue);
    return (
      lang === "hi" ||
      lang === "hindi" ||
      lang.indexOf("hi-") === 0 ||
      lang === "mr" ||
      lang === "marathi" ||
      lang.indexOf("mr-") === 0 ||
      lang === "ta" ||
      lang === "tamil" ||
      lang.indexOf("ta-") === 0 ||
      lang === "te" ||
      lang === "telugu" ||
      lang.indexOf("te-") === 0
    );
  }

  function isTurkishLanguageCode(langValue) {
    var lang = normalizeLangCode(langValue);
    return (
      lang === "tr" ||
      lang === "turkish" ||
      lang.indexOf("tr-") === 0
    );
  }

  function isSanskritLanguageCode(langValue) {
    var lang = normalizeLangCode(langValue);
    return (
      lang === "sa" ||
      lang === "san" ||
      lang === "sanskrit" ||
      lang.indexOf("sa-") === 0 ||
      lang.indexOf("san-") === 0 ||
      lang.indexOf("sanskrit-") === 0
    );
  }

  function isThaiLanguageCode(langValue) {
    var lang = normalizeLangCode(langValue);
    return (
      lang === "th" ||
      lang === "thai" ||
      lang.indexOf("th-") === 0
    );
  }

  function foldLookupLetters(text, foldMap) {
    var src = String(text || "");
    var out = "";
    for (var i = 0; i < src.length; i++) {
      var ch = src.charAt(i);
      out += foldMap[ch] || ch;
    }
    return out;
  }

  function foldArabicLookupLetters(text) {
    return foldLookupLetters(text, ARABIC_FOLD_MAP);
  }

  function foldPersianLookupLetters(text) {
    return foldLookupLetters(text, PERSIAN_FOLD_MAP);
  }

  function foldUrduLookupLetters(text) {
    return foldLookupLetters(text, URDU_FOLD_MAP);
  }

  function prepareTurkishLookupCase(text) {
    return foldLookupLetters(text, TURKISH_CASE_PREP_MAP);
  }

  function foldSanskritAsciiFallback(text) {
    var value = String(text || "");
    value = value
      .replace(/[ṛṝṚṜ]/g, "f")
      .replace(/[ḷḹḶḸ]/g, "x")
      .replace(/[ñÑ]/g, "y")
      .replace(/[ṭṬ]/g, "w")
      .replace(/[ḍḌ]/g, "q")
      .replace(/[ṇṆ]/g, "r")
      .replace(/[ṣṢ]/g, "z");
    if (value.normalize) value = value.normalize("NFD");
    return value.replace(LATIN_COMBINING_MARKS_RE, "");
  }

  function transliterateSanskritSlp1ToIast(text) {
    var src = String(text || "");
    var out = "";
    for (var i = 0; i < src.length; i++) {
      var ch = src.charAt(i);
      out += SANSKRIT_SLP1_TO_IAST_MAP[ch] || ch;
    }
    if (out.normalize) out = out.normalize("NFC");
    return out;
  }

  function transliterateSanskritIastToSlp1(text) {
    var src = String(text || "");
    if (src.normalize) src = src.normalize("NFC");
    var lowered = src.toLowerCase();
    var out = "";
    var i = 0;

    while (i < lowered.length) {
      var matched = false;
      for (var si = 0; si < SANSKRIT_IAST_TO_SLP1_SEQUENCES.length; si++) {
        var seq = SANSKRIT_IAST_TO_SLP1_SEQUENCES[si];
        var key = seq[0];
        if (lowered.slice(i, i + key.length) !== key) continue;
        out += seq[1];
        i += key.length;
        matched = true;
        break;
      }
      if (matched) continue;

      var loweredCh = lowered.charAt(i);
      var mapped = SANSKRIT_IAST_TO_SLP1_CHAR_MAP[loweredCh];
      out += (mapped != null) ? mapped : src.charAt(i);
      i += 1;
    }

    return out;
  }

  function foldSanskritLookupText(text) {
    return transliterateSanskritSlp1ToIast(text);
  }

  function foldSanskritRomanToIast(text) {
    var value = String(text || "");
    if (!value) return value;
    if (value.normalize) value = value.normalize("NFC");
    for (var i = 0; i < SANSKRIT_ROMAN_MULTI_FOLDS.length; i++) {
      var pair = SANSKRIT_ROMAN_MULTI_FOLDS[i];
      value = value.split(pair[0]).join(pair[1]);
    }
    var out = "";
    for (var j = 0; j < value.length; j++) {
      var ch = value.charAt(j);
      var mapped = SANSKRIT_ROMAN_SINGLE_FOLDS[ch];
      out += (mapped != null) ? mapped : ch;
    }
    // Strip Vedic tone superscripts and any stray combining marks that
    // weren't handled by the named folds. Precomposed IAST codepoints
    // (ṛ, ṃ, ṇ, ṭ, ḍ, ś, ṣ, ḥ, ñ, ṅ, ḷ, etc.) are unaffected.
    return out.replace(SANSKRIT_SUPERSCRIPT_STRIP_RE, "").replace(SANSKRIT_COMBINING_STRIP_RE, "");
  }

  function canonicalizeSanskritAnusvara(text) {
    var value = String(text || "");
    if (!value) return value;
    for (var i = 0; i < SANSKRIT_ANUSVARA_PATTERNS.length; i++) {
      value = value.replace(SANSKRIT_ANUSVARA_PATTERNS[i][0], SANSKRIT_ANUSVARA_PATTERNS[i][1]);
    }
    return value;
  }

  function normalizeAncientGreekLookupApostrophes(text) {
    return String(text || "").replace(ANCIENT_GREEK_APOSTROPHE_EQUIVALENTS_RE, "'");
  }

  function stripAncientGreekBreathingsAndAccents(text) {
    var value = String(text || "");
    if (!value) return value;
    value = value.replace(/\u1FBE/g, "\u03B9");
    if (value.normalize) value = value.normalize("NFD");
    value = value.replace(ANCIENT_GREEK_STRIP_MARKS_RE, "");
    value = value.replace(ANCIENT_GREEK_IOTA_SUBSCRIPT_RE, "\u03B9");
    if (value.normalize) value = value.normalize("NFC");
    return value;
  }

  function foldGreekSigma(text) {
    return String(text || "")
      .replace(GREEK_LUNATE_SIGMA_RE, "\u03C3")
      .replace(ANCIENT_GREEK_FINAL_SIGMA_RE, "\u03C3");
  }

  function stripModernGreekMarks(text, options) {
    var value = String(text || "");
    if (!value) return value;
    if (value.normalize) value = value.normalize("NFD");
    value = value.replace(/\u0301/g, "");
    if (options && options.stripDiaeresis) {
      value = value.replace(GREEK_DIAERESIS_RE, "");
    }
    if (value.normalize) value = value.normalize("NFC");
    return value;
  }

  function stripAncientGreekExtraEditorialMarks(text, options) {
    var value = String(text || "");
    if (!value) return value;
    if (value.normalize) value = value.normalize("NFD");
    value = value.replace(ANCIENT_GREEK_EDITORIAL_MARKS_RE, "");
    if (options && options.stripDiaeresis) {
      value = value.replace(GREEK_DIAERESIS_RE, "");
    }
    if (value.normalize) value = value.normalize("NFC");
    return value;
  }

  var ANCIENT_GREEK_ELISION_MAP = Object.freeze({
    "ἀλλ'": "ἀλλά",
    "ἀνθ'": "ἀντί",
    "ἀπ'": "ἀπό",
    "ἀφ'": "ἀπό",
    "γ'": "γε",
    "γένοιτ'": "γένοιτο",
    "δ'": "δέ",
    "δεῦρ'": "δεῦρο",
    "δι'": "διά",
    "δύναιτ'": "δύναιτο",
    "εἶτ'": "εἶτα",
    "ἐπ'": "ἐπί",
    "ἔτ'": "ἔτι",
    "ἐφ'": "ἐπί",
    "ἡγοῖντ'": "ἡγοῖντο",
    "ἵν'": "ἵνα",
    "καθ'": "κατά",
    "κατ'": "κατά",
    "μ'": "με",
    "μεθ'": "μετά",
    "μετ'": "μετά",
    "μηδ'": "μηδέ",
    "μήδ'": "μηδέ",
    "ὅτ'": "ὅτε",
    "οὐδ'": "οὐδέ",
    "πάνθ'": "πάντα",
    "πάντ'": "πάντα",
    "παρ'": "παρά",
    "ποτ'": "ποτε",
    "σ'": "σε",
    "τ'": "τε",
    "ταῦθ'": "ταῦτα",
    "ταῦτ'": "ταῦτα",
    "τοῦτ'": "τοῦτο",
    "ὑπ'": "ὑπό",
    "ὑφ'": "ὑπό"
  });

  var ANCIENT_GREEK_MOVABLE_MAP = Object.freeze({
    "ἐξ": "ἐκ",
    "οὐκ": "οὐ",
    "οὐχ": "οὐ"
  });

  function expandAncientGreekPreLookupForms(text) {
    var value = String(text || "");
    if (!value) return value;
    if (ANCIENT_GREEK_ELISION_MAP[value]) return ANCIENT_GREEK_ELISION_MAP[value];
    if (ANCIENT_GREEK_MOVABLE_MAP[value]) return ANCIENT_GREEK_MOVABLE_MAP[value];
    return value;
  }

  function normalizeLookupAffixMarkers(text, options) {
    var src = String(text || "");
    var lang = normalizeLangCode(options && options.langCode);
    var preserveApostrophe = isSanskritLanguageCode(lang);
    var out = "";
    for (var i = 0; i < src.length; i++) {
      var ch = src.charAt(i);
      if (preserveApostrophe && ch === "'") {
        out += ch;
        continue;
      }
      out += (AFFIX_MARKER_EQUIVALENTS.indexOf(ch) >= 0) ? "-" : ch;
    }
    return out;
  }

  function stripInvisibleComparisonChars(text) {
    return String(text || "").replace(LOOKUP_INVISIBLE_COMPARISON_RE, "");
  }

  function stripLemmaAlignmentDiacritics(text, langCode) {
    var value = String(text || "");
    if (!value) return value;
    var lang = normalizeLangCode(langCode || "");
    if (isArabicScriptLanguageCode(lang)) {
      value = value.replace(ARABIC_STRIP_MARKS_RE, "");
    } else if (isHebrewLanguageCode(lang)) {
      value = value.replace(HEBREW_STRIP_MARKS_RE, "");
    } else if (isAncientGreekLanguageCode(lang)) {
      value = foldGreekSigma(
        stripAncientGreekExtraEditorialMarks(
          stripAncientGreekBreathingsAndAccents(value),
          { stripDiaeresis: true }
        )
      );
    } else if (isModernGreekLanguageCode(lang)) {
      value = foldGreekSigma(stripModernGreekMarks(value, { stripDiaeresis: true }));
    }
    return value;
  }

  function normalizeVisibleComparisonText(text) {
    var value = String(text || "");
    if (value.normalize) value = value.normalize("NFKC");
    return stripInvisibleComparisonChars(value).trim();
  }

  function registerRule(rule) {
    if (!rule || typeof rule.apply !== "function") return false;
    var id = String(rule.id || "").trim();
    if (!id) return false;
    if (!ruleMap[id]) ruleOrder.push(id);
    ruleMap[id] = rule;
    if (!Object.prototype.hasOwnProperty.call(enabledState, id)) {
      enabledState[id] = rule.enabled !== false;
    }
    return true;
  }

  function isRuleEnabled(ruleId) {
    var id = String(ruleId || "").trim();
    if (!id || !ruleMap[id]) return false;
    return enabledState[id] !== false;
  }

  function setRuleEnabled(ruleId, enabled) {
    var id = String(ruleId || "").trim();
    if (!id || !ruleMap[id]) return false;
    enabledState[id] = enabled !== false;
    return true;
  }

  function enableRule(ruleId) {
    return setRuleEnabled(ruleId, true);
  }

  function disableRule(ruleId) {
    return setRuleEnabled(ruleId, false);
  }

  function listRules() {
    var out = [];
    for (var i = 0; i < ruleOrder.length; i++) {
      var id = ruleOrder[i];
      var rule = ruleMap[id];
      if (!rule) continue;
      out.push({
        id: id,
        label: String(rule.label || id),
        enabled: isRuleEnabled(id)
      });
    }
    return out;
  }

  function normalizeLookupText(text, options) {
    var value = String(text || "");
    var ctx = options || {};
    for (var i = 0; i < ruleOrder.length; i++) {
      var id = ruleOrder[i];
      var rule = ruleMap[id];
      if (!rule || !isRuleEnabled(id)) continue;
      if (typeof rule.test === "function" && !rule.test(value, ctx)) continue;
      var next = rule.apply(value, ctx);
      if (next == null) continue;
      value = String(next);
    }
    return value;
  }

  function normalizeLookupKeyText(text, options) {
    var ctx = options || {};
    var langCode = normalizeLangCode(ctx.langCode || "");
    var value = String(text || "");
    // Greek koronis / curly apostrophes are not fully handled by NFKC.
    if (isAncientGreekLanguageCode(langCode)) {
      value = normalizeAncientGreekLookupApostrophes(value);
      value = expandAncientGreekPreLookupForms(value);
    }
    if (value.normalize) value = value.normalize("NFKC");
    value = value.trim();
    if (!value) return "";
    value = normalizeLookupAffixMarkers(value, { langCode: langCode });
    value = normalizeLookupText(value, {
      langCode: langCode,
      phase: String(ctx.phase || "lookup_key"),
      stripGreekDiaeresis: !!ctx.stripGreekDiaeresis
    });
    value = String(value || "").trim();
    if (!value) return "";
    return value.replace(/-/g, "").toLowerCase();
  }

  // DEBUG-ONLY: mirrors normalizeLookupKeyText but returns {text, norm_kinds} recording
  // every transformation step that actually changed the string.  Never called on the live
  // path — callers must check their own debug gate before invoking this.
  function normalizeLookupKeyTextWithTrace(text, options) {
    var ctx = options || {};
    var langCode = normalizeLangCode(ctx.langCode || "");
    var value = String(text || "");
    var kinds = [];

    function record(id, label, before, after) {
      if (before !== after) kinds.push({ id: id, label: label, before: before, after: after });
    }

    var before;

    if (isAncientGreekLanguageCode(langCode)) {
      before = value;
      value = normalizeAncientGreekLookupApostrophes(value);
      record("ancient_greek_apostrophes", "Ancient Greek koronis/apostrophe normalisation", before, value);
      before = value;
      value = expandAncientGreekPreLookupForms(value);
      record("ancient_greek_pre_lookup_expand", "Ancient Greek pre-lookup form expansion", before, value);
    }

    if (value.normalize) {
      before = value;
      value = value.normalize("NFKC");
      record("nfkc", "NFKC Unicode normalisation", before, value);
    }

    before = value;
    value = value.trim();
    record("trim", "Trim whitespace", before, value);

    if (!value) return { text: "", norm_kinds: kinds };

    before = value;
    value = normalizeLookupAffixMarkers(value, { langCode: langCode });
    record("affix_markers", "Affix marker normalisation (-/–/— → -)", before, value);

    // Run each registered rule individually so we can record per-rule changes.
    var phase = String(ctx.phase || "lookup_key");
    var ruleCtx = { langCode: langCode, phase: phase, stripGreekDiaeresis: !!ctx.stripGreekDiaeresis };
    for (var i = 0; i < ruleOrder.length; i++) {
      var id = ruleOrder[i];
      var rule = ruleMap[id];
      if (!rule || !isRuleEnabled(id)) continue;
      if (typeof rule.test === "function" && !rule.test(value, ruleCtx)) continue;
      before = value;
      var next = rule.apply(value, ruleCtx);
      if (next == null) continue;
      value = String(next);
      record(id, rule.label || id, before, value);
    }

    before = value;
    value = String(value || "").trim();
    record("final_trim", "Final trim", before, value);

    if (!value) return { text: "", norm_kinds: kinds };

    before = value;
    value = value.replace(/-/g, "").toLowerCase();
    record("lowercase_dehyphen", "Lowercase and strip hyphens", before, value);

    return { text: value, norm_kinds: kinds };
  }

  registerRule({
    id: "strip_invisible_format_controls",
    label: "Strip invisible format controls",
    enabled: true,
    apply: function(text) {
      return String(text || "").replace(INVISIBLE_FORMAT_CONTROLS_RE, "");
    }
  });

  registerRule({
    id: "ancient_greek_strip_marks",
    label: "Ancient Greek strip breathings/accents and fold sigma variants",
    enabled: true,
    test: function(_text, ctx) {
      return isAncientGreekLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text) {
      return foldGreekSigma(stripAncientGreekBreathingsAndAccents(text));
    }
  });

  registerRule({
    id: "ancient_greek_strip_editorial_marks",
    label: "Ancient Greek strip editorial quantity marks",
    enabled: true,
    test: function(_text, ctx) {
      return isAncientGreekLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text, ctx) {
      return stripAncientGreekExtraEditorialMarks(text, {
        stripDiaeresis: !!(ctx && ctx.stripGreekDiaeresis)
      });
    }
  });

  registerRule({
    id: "modern_greek_normalize",
    label: "Modern Greek strip tonos and fold sigma variants",
    enabled: true,
    test: function(_text, ctx) {
      return isModernGreekLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text, ctx) {
      return foldGreekSigma(stripModernGreekMarks(text, {
        stripDiaeresis: !!(ctx && ctx.stripGreekDiaeresis)
      }));
    }
  });

  registerRule({
    id: "cjk_strip_variation_selectors",
    label: "Strip CJK variation selectors",
    enabled: true,
    test: function(_text, ctx) {
      var lang = ctx && ctx.langCode;
      return isChineseLanguageCode(lang) || isJapaneseLanguageCode(lang);
    },
    apply: function(text) {
      return String(text || "").replace(CJK_VARIATION_SELECTORS_RE, "");
    }
  });

  registerRule({
    id: "arabic_script_strip_marks",
    label: "Arabic-script strip marks",
    enabled: true,
    test: function(_text, ctx) {
      return isArabicScriptLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text) {
      return String(text || "").replace(ARABIC_STRIP_MARKS_RE, "");
    }
  });

  registerRule({
    id: "arabic_fold_letters",
    label: "Arabic fold letter variants",
    enabled: true,
    test: function(_text, ctx) {
      return isArabicLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text) {
      return foldArabicLookupLetters(text);
    }
  });

  registerRule({
    id: "persian_fold_letters",
    label: "Persian fold letter variants",
    enabled: true,
    test: function(_text, ctx) {
      return isPersianLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text) {
      return foldPersianLookupLetters(text);
    }
  });

  registerRule({
    id: "urdu_strip_join_controls",
    label: "Urdu strip ZWNJ and ZWJ",
    enabled: true,
    test: function(_text, ctx) {
      return isUrduLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text) {
      return String(text || "").replace(URDU_JOIN_CONTROLS_RE, "");
    }
  });

  registerRule({
    id: "urdu_fold_letters",
    label: "Urdu fold letter variants",
    enabled: true,
    test: function(_text, ctx) {
      return isUrduLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text) {
      return foldUrduLookupLetters(text);
    }
  });

  registerRule({
    id: "hebrew_strip_marks",
    label: "Hebrew strip cantillation and niqqud",
    enabled: true,
    test: function(_text, ctx) {
      return isHebrewLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text) {
      return String(text || "").replace(HEBREW_STRIP_MARKS_RE, "");
    }
  });

  registerRule({
    id: "indic_strip_zero_width_controls",
    label: "Indic strip ZWSP/ZWNJ/ZWJ",
    enabled: true,
    test: function(_text, ctx) {
      return isIndicJoinControlLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text) {
      return String(text || "").replace(INDIC_ZERO_WIDTH_RE, "");
    }
  });

  // Disabled — SLP1→IAST transliteration was only needed for Monier-Williams
  // which uses Harvard-Kyoto/SLP1 encoding. DCS and other Sanskrit dicts use IAST natively.
  // registerRule({
  //   id: "sanskrit_ascii_fold",
  //   label: "Sanskrit SLP1 to IAST transliteration",
  //   enabled: true,
  //   test: function(_text, ctx) {
  //     return isSanskritLanguageCode(ctx && ctx.langCode);
  //   },
  //   apply: function(text) {
  //     return foldSanskritLookupText(text);
  //   }
  // });

  registerRule({
    id: "sanskrit_roman_iast_fold",
    label: "Sanskrit Roman→IAST fold (ISO long e/o, vocalic ṛ/ḷ, accent marks, superscripts)",
    enabled: true,
    test: function(_text, ctx) {
      return isSanskritLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text) {
      return foldSanskritRomanToIast(text);
    }
  });

  registerRule({
    id: "turkish_casefold_prep",
    label: "Turkish casefold preparation",
    enabled: true,
    test: function(_text, ctx) {
      return isTurkishLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text) {
      return prepareTurkishLookupCase(text);
    }
  });

  registerRule({
    id: "thai_strip_zwsp",
    label: "Thai strip ZWSP",
    enabled: true,
    test: function(_text, ctx) {
      return isThaiLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text) {
      return String(text || "").replace(THAI_ZWSP_RE, "");
    }
  });

  function normalizeOldEnglishKey(str) {
    if (!str) return "";
    return str
      .normalize("NFC")
      // long monophthongs
      .replace(/ā/g, "a")
      .replace(/ē/g, "e")
      .replace(/ī/g, "i")
      .replace(/ō/g, "o")
      .replace(/ū/g, "u")
      .replace(/ȳ/g, "y")
      .replace(/ǣ/g, "æ")
      // long diphthongs
      .replace(/ēa/g, "ea")
      .replace(/ēo/g, "eo")
      .replace(/īe/g, "ie")
      // thorn / eth
      .replace(/ð/g, "þ")
      // editorial palatal marks
      .replace(/ċ/g, "c")
      .replace(/ġ/g, "g")
      // manuscript letters
      .replace(/ƿ/g, "w")
      .replace(/[ᵹꝽꝿ]/g, "g");
  }

  registerRule({
    id: "old_english_normalize",
    label: "Old English fold macrons, eth→thorn, palatal marks, manuscript letters",
    enabled: true,
    test: function(_text, ctx) {
      return isOldEnglishLanguageCode(ctx && ctx.langCode);
    },
    apply: function(text) {
      return normalizeOldEnglishKey(text);
    }
  });

  window.DictionaryNormalizationLayer = {
    normalizeLookupText: normalizeLookupText,
    registerRule: registerRule,
    setRuleEnabled: setRuleEnabled,
    enableRule: enableRule,
    disableRule: disableRule,
    isRuleEnabled: isRuleEnabled,
    listRules: listRules,
    normalizeLangCode: normalizeLangCode,
    isArabicLanguageCode: isArabicLanguageCode,
    isChineseLanguageCode: isChineseLanguageCode,
    isJapaneseLanguageCode: isJapaneseLanguageCode,
    isPersianLanguageCode: isPersianLanguageCode,
    isUrduLanguageCode: isUrduLanguageCode,
    isHebrewLanguageCode: isHebrewLanguageCode,
    isAncientGreekLanguageCode: isAncientGreekLanguageCode,
    isModernGreekLanguageCode: isModernGreekLanguageCode,
    isOldEnglishLanguageCode: isOldEnglishLanguageCode,
    isSanskritLanguageCode: isSanskritLanguageCode,
    isTurkishLanguageCode: isTurkishLanguageCode,
    isThaiLanguageCode: isThaiLanguageCode,
    foldArabicLookupLetters: foldArabicLookupLetters,
    foldPersianLookupLetters: foldPersianLookupLetters,
    foldUrduLookupLetters: foldUrduLookupLetters,
    transliterateSanskritIastToSlp1: transliterateSanskritIastToSlp1,
    transliterateSanskritSlp1ToIast: transliterateSanskritSlp1ToIast,
    foldSanskritLookupText: foldSanskritLookupText,
    foldSanskritRomanToIast: foldSanskritRomanToIast,
    canonicalizeSanskritAnusvara: canonicalizeSanskritAnusvara,
    prepareTurkishLookupCase: prepareTurkishLookupCase,
    stripInvisibleComparisonChars: stripInvisibleComparisonChars,
    normalizeVisibleComparisonText: normalizeVisibleComparisonText,
    stripLemmaAlignmentDiacritics: stripLemmaAlignmentDiacritics,
    stripAncientGreekBreathingsAndAccents: stripAncientGreekBreathingsAndAccents,
    stripModernGreekMarks: stripModernGreekMarks,
    expandAncientGreekPreLookupForms: expandAncientGreekPreLookupForms,
    normalizeLookupKeyText: normalizeLookupKeyText,
    normalizeLookupKeyTextWithTrace: normalizeLookupKeyTextWithTrace
  };
})();
