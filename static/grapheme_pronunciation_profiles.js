
/**
 * grapheme_pronunciation_profiles.js
 *
 * DONT BOTHER WITH LATIN SCRIPTS.
 * DONT BOTHER WITH HAN / CHINESE EITHER.
 * This engine is intentionally limited to scripts where orthography can be
 * mapped mechanically to pronunciation and where that mapping is genuinely
 * useful for an English speaker. `old-english` is the only Latin-script
 * exception still kept for now.
 *
 * Deterministic grapheme-cluster / codepoint-to-sound mapper.
 *
 * Purpose:
 * - Take an already segmented grapheme cluster or short span
 * - Decompose it into constituent codepoints or jamo when needed
 * - Return a rough pronunciation value for the cluster and its parts
 *
 * This module is intentionally centered on pronunciation rules, not segmentation.
 * Unsupported language/script families are intentionally skipped.
 */

/* -------------------------------------------------------------------------- */
/* Core API                                                                    */
/* -------------------------------------------------------------------------- */

const DEFAULT_OPTIONS = {
  normalize: true,
  decompose: true,
  preserveUnknown: false,
  compatibility: true,
};

const GRAPHEME_SEGMENTER =
  typeof Intl !== "undefined" && typeof Intl.Segmenter === "function"
    ? new Intl.Segmenter(undefined, { granularity: "grapheme" })
    : null;

const PROFILE_SPAN_SEQUENCE_CACHE = new WeakMap();
// Some legacy profile/data blocks still exist lower in this file; these ids are
// intentionally disabled at runtime and should stay out unless explicitly revived.
const DISABLED_PRONUNCIATION_LANGUAGE_IDS = new Set([
  "vietnamese",
  "turkish",
  "indonesian",
  "tagalog",
  "swahili",
  "latin",
  "french",
  "italian",
  "spanish",
  "german",
  "dutch",
  "portuguese",
  "generic-latin",
  "han",
  "old-english",
]);

function normalizeLanguageId(language) {
  const raw = String(language || "").trim().toLowerCase();
  return LANGUAGE_ALIASES[raw] || raw;
}

function getLanguageProfile(language) {
  const id = normalizeLanguageId(language);
  if (DISABLED_PRONUNCIATION_LANGUAGE_IDS.has(id)) return null;
  return PHONOLOGY_PROFILES[id] || null;
}

function codePointHex(ch) {
  return "U+" + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, "0");
}

function splitClusterAroundWhitespace(cluster) {
  const raw = String(cluster ?? "");
  if (!raw) return [];
  if (!/\s/u.test(raw)) return [raw];

  const out = [];
  let current = "";
  for (const ch of Array.from(raw)) {
    if (/\s/u.test(ch)) {
      if (current) {
        out.push(current);
        current = "";
      }
      out.push(ch);
      continue;
    }
    current += ch;
  }
  if (current) out.push(current);
  return out;
}

function separateWhitespaceClusters(clusters) {
  const src = Array.isArray(clusters) ? clusters : [];
  const out = [];
  for (const cluster of src) {
    out.push(...splitClusterAroundWhitespace(cluster));
  }
  return out;
}

function splitGraphemeClusters(value, options = {}) {
  if (Array.isArray(options.clusters) && options.clusters.length) {
    return separateWhitespaceClusters(options.clusters.map((x) => String(x)));
  }

  const raw = String(value ?? "");
  if (!raw) return [];

  if (GRAPHEME_SEGMENTER) {
    return separateWhitespaceClusters(Array.from(GRAPHEME_SEGMENTER.segment(raw), (x) => x.segment));
  }

  const fallback = raw.match(/\P{Mark}\p{Mark}*|\p{Mark}+|./gu);
  return separateWhitespaceClusters(fallback || Array.from(raw));
}

function normalizeUnit(language, cluster, options = {}) {
  const raw = String(cluster ?? "");
  if (options.normalize === false) return raw;
  const compat = options.compatibility !== false;
  return compat ? raw.normalize("NFKC").normalize("NFC") : raw.normalize("NFC");
}

function normalizeClusterSequence(language, clusters, options = {}) {
  if (typeof clusters === "string") {
    const normalized = normalizeUnit(language, clusters, options);
    return splitGraphemeClusters(normalized);
  }

  const out = [];
  for (const cluster of Array.from(clusters || [])) {
    const normalized = normalizeUnit(language, cluster, options);
    if (!normalized) continue;
    if (options.splitItems === false) {
      out.push(normalized);
      continue;
    }
    out.push(...splitGraphemeClusters(normalized));
  }
  return out;
}

function decomposeCluster(language, cluster, options = {}) {
  const profile = getLanguageProfile(language);
  const unit = normalizeUnit(language, cluster, options);
  if (!profile) return [];

  if (Array.isArray(options.parts) && options.parts.length) {
    return options.parts.map((x) => String(x));
  }

  if (profile.decomposeCluster) {
    return profile.decomposeCluster(unit, options);
  }

  return Array.from(unit.normalize(options.compatibility === false ? "NFD" : "NFKD"));
}

function analyzeSingleCluster(language, cluster, options = {}) {
  const profile = getLanguageProfile(language);
  if (!profile) return null;
  const unit = normalizeUnit(profile.id, cluster, options);
  const parts = decomposeCluster(profile.id, unit, options);

  const analysis = profile.analyze
    ? profile.analyze(unit, parts, { ...DEFAULT_OPTIONS, ...options, profile })
    : analyzeBySimpleMap(profile, unit, parts, options);

  return {
    language: profile.id,
    script: profile.script,
    cluster: unit,
    sound: analysis.sound || "",
    romanization: analysis.sound || "",
    notes: analysis.notes || [],
    derivation: analysis.derivation || null,
    parts: (analysis.parts || []).map((part) => ({
      ...part,
      romanization: part.romanization ?? part.sound ?? "",
    })),
  };
}

function cloneAnalysisItem(item) {
  return {
    ...item,
    sound: item.sound || "",
    romanization: item.romanization ?? item.sound ?? "",
    notes: Array.isArray(item.notes) ? [...item.notes] : [],
    parts: Array.isArray(item.parts)
      ? item.parts.map((part) => ({
          ...part,
          sound: part.sound || "",
          romanization: part.romanization ?? part.sound ?? "",
        }))
      : [],
  };
}

function buildSpanSequenceEntries(profile) {
  if (PROFILE_SPAN_SEQUENCE_CACHE.has(profile)) {
    return PROFILE_SPAN_SEQUENCE_CACHE.get(profile);
  }

  const entries = [];
  for (const [surface, sound] of Object.entries(profile.spanMap || {})) {
    const clusters = splitGraphemeClusters(surface);
    if (clusters.length <= 1) continue;
    entries.push({
      surface,
      sound,
      clusters: profile.caseInsensitive ? clusters.map((x) => x.toLowerCase()) : clusters,
      length: clusters.length,
    });
  }

  entries.sort((a, b) => b.length - a.length || b.surface.length - a.surface.length);
  PROFILE_SPAN_SEQUENCE_CACHE.set(profile, entries);
  return entries;
}

function applySpanSequenceRomanization(profile, clusters, items) {
  const sequences = buildSpanSequenceEntries(profile);
  if (!sequences.length) return items;

  const source = profile.caseInsensitive ? clusters.map((x) => x.toLowerCase()) : clusters.slice();
  let i = 0;
  while (i < source.length) {
    let matched = null;
    for (const entry of sequences) {
      if (i + entry.length > source.length) continue;
      if (profile.scriptFamily === "arabic" && entry.surface === "ال" && i + 2 < clusters.length) {
        const nextBase = arabicBaseOfCluster(clusters[i + 2]);
        if (ARABIC_SUN_LETTERS.has(nextBase)) continue;
      }
      let ok = true;
      for (let j = 0; j < entry.length; j += 1) {
        if (source[i + j] !== entry.clusters[j]) {
          ok = false;
          break;
        }
      }
      if (ok) {
        matched = entry;
        break;
      }
    }

    if (!matched) {
      i += 1;
      continue;
    }

    items[i].sound = matched.sound;
    items[i].romanization = matched.sound;
    for (let j = 1; j < matched.length; j += 1) {
      items[i + j].sound = "";
      items[i + j].romanization = "";
    }
    i += matched.length;
  }

  return items;
}

function getInitialRomanConsonant(romanization) {
  const match = String(romanization || "").match(/^[^aeiouāēīōūəɨʉ]/i);
  return match ? match[0] : "";
}

function getTrailingRomanVowel(romanization) {
  const match = String(romanization || "").match(/([aeiouāēīōūəɨʉ])$/i);
  return match ? match[1] : "";
}

function applyJapaneseGraphemeSmoothing(clusters, items) {
  for (let i = 0; i < clusters.length; i += 1) {
    const cluster = clusters[i];

    if ((cluster === "っ" || cluster === "ッ") && i + 1 < items.length) {
      const onset = getInitialRomanConsonant(items[i + 1].romanization || items[i + 1].sound);
      items[i].sound = onset || "Q";
      items[i].romanization = onset || "Q";
      continue;
    }

    if (cluster === "ー" && i > 0) {
      const vowel = getTrailingRomanVowel(items[i - 1].romanization || items[i - 1].sound);
      items[i].sound = vowel || "";
      items[i].romanization = vowel || "";
      continue;
    }

    if ((JAPANESE_SMALL_Y[cluster] || JAPANESE_SMALL_VOWEL[cluster]) && i > 0) {
      const prevCluster = clusters[i - 1];
      const pairSound = composeJapaneseSpan(prevCluster + cluster, [prevCluster, cluster]);
      const suffix = JAPANESE_SMALL_Y[cluster] || JAPANESE_SMALL_VOWEL[cluster] || "";
      if (pairSound && suffix && pairSound.length >= suffix.length) {
        const prefix = pairSound.slice(0, pairSound.length - suffix.length);
        items[i - 1].sound = prefix;
        items[i - 1].romanization = prefix;
        items[i].sound = suffix;
        items[i].romanization = suffix;
      }
      continue;
    }

    if ((cluster === "ん" || cluster === "ン") && i + 1 < items.length) {
      const next = items[i + 1].romanization || items[i + 1].sound;
      if (/^[bmp]/i.test(next)) {
        items[i].sound = "m";
        items[i].romanization = "m";
      } else if (/^[kg]/i.test(next)) {
        items[i].sound = "ng";
        items[i].romanization = "ng";
      }
    }
  }

  return items;
}

/* -------------------------------------------------------------------------- */
/* Arabic sun-letter assimilation                                             */
/* -------------------------------------------------------------------------- */

const ARABIC_SUN_LETTERS = new Set(["ت","ث","د","ذ","ر","ز","س","ش","ص","ض","ط","ظ","ل","ن"]);
const ARABIC_ALIF_FORMS = new Set(["ا","أ","إ","ٱ","آ"]);

function arabicBaseOfCluster(cluster) {
  if (!cluster) return "";
  const found = Array.from(String(cluster)).find((c) => !/\p{Mark}/u.test(c));
  return found || "";
}

function applyArabicSunLetterSmoothing(clusters, items) {
  for (let i = 0; i + 2 < clusters.length; i++) {
    const base0 = arabicBaseOfCluster(clusters[i]);
    const base1 = arabicBaseOfCluster(clusters[i + 1]);
    const base2 = arabicBaseOfCluster(clusters[i + 2]);
    if (!ARABIC_ALIF_FORMS.has(base0) || base1 !== "ل" || !ARABIC_SUN_LETTERS.has(base2)) continue;
    if (!items[i] || !items[i + 1] || !items[i + 2]) continue;

    const sunSound = items[i + 2].sound || items[i + 2].romanization || "";
    const onsetMatch = sunSound.match(/^[^aeiouāēīōūâêîôûəɨʉ]+/i);
    if (!onsetMatch) continue;

    items[i].sound = "a";
    items[i].romanization = "a";
    items[i + 1].sound = "-";
    items[i + 1].romanization = "-";
    items[i + 2].sound = onsetMatch[0] + sunSound;
    items[i + 2].romanization = onsetMatch[0] + sunSound;
  }
  return items;
}

/* -------------------------------------------------------------------------- */
/* Abugida smoothing: homorganic anusvara + word-final schwa deletion         */
/* -------------------------------------------------------------------------- */

const ABUGIDA_WORD_BOUNDARY_RE = /^[\s।॥.,;:!?"'()\[\]{}\-–—]/u;

function computeHomorganicNasal(nextSound) {
  if (!nextSound) return null;
  if (/^(kh?|gh?)/.test(nextSound)) return "ṅ";
  if (/^(ch?|jh?|ś)/.test(nextSound)) return "ñ";
  if (/^(ṭh?|ḍh?|ṣ)/.test(nextSound)) return "ṇ";
  if (/^(th?|dh?|n|s)/.test(nextSound)) return "n";
  if (/^(ph?|bh?|m|v)/.test(nextSound)) return "m";
  return null;
}

function applyAbugidaGeminationSmoothing(profile, clusters, items) {
  if (!profile.geminationMark) return items;

  for (let i = 0; i + 1 < clusters.length; i++) {
    const cluster = String(clusters[i] || "");
    const next = items[i + 1];
    if (!cluster.includes(profile.geminationMark) || !next) continue;
    if (ABUGIDA_WORD_BOUNDARY_RE.test(String(clusters[i + 1] || ""))) continue;

    const nextSound = next.sound || next.romanization || "";
    const onsetMatch = nextSound.match(/^[^aeiouāēīōūâêîôûəɨʉ]+/i);
    if (!onsetMatch) continue;

    const geminated = onsetMatch[0] + nextSound;
    next.sound = geminated;
    next.romanization = geminated;
  }

  return items;
}

function applyAbugidaAnusvaraHomorganic(clusters, items) {
  for (let i = 0; i + 1 < clusters.length; i++) {
    const item = items[i];
    const next = items[i + 1];
    if (!item || !next) continue;
    const sound = item.sound || item.romanization || "";
    if (!sound.endsWith("ṃ")) continue;
    if (ABUGIDA_WORD_BOUNDARY_RE.test(String(clusters[i + 1] || ""))) continue;
    const nextSound = next.sound || next.romanization || "";
    const replacement = computeHomorganicNasal(nextSound);
    if (!replacement) continue;
    const newSound = sound.slice(0, -1) + replacement;
    item.sound = newSound;
    item.romanization = newSound;
  }
  return items;
}

function applyAbugidaSchwaDeletion(profile, clusters, items) {
  const inherent = profile.inherentVowel;
  if (!inherent) return items;

  for (let i = 0; i < clusters.length; i++) {
    const cluster = String(clusters[i] || "");
    if (!cluster || ABUGIDA_WORD_BOUNDARY_RE.test(cluster)) continue;
    const item = items[i];
    if (!item) continue;
    const sound = item.sound || item.romanization || "";
    if (!sound.endsWith(inherent)) continue;

    const isLast = i === clusters.length - 1;
    const nextIsBoundary = !isLast && ABUGIDA_WORD_BOUNDARY_RE.test(String(clusters[i + 1] || ""));
    if (!isLast && !nextIsBoundary) continue;

    const chars = Array.from(cluster);
    const hasExplicitVowel = chars.some((c) =>
      (profile.vowelSigns && profile.vowelSigns[c] != null) ||
      (profile.independentVowels && profile.independentVowels[c] != null)
    );
    const hasVirama = profile.virama && chars.includes(profile.virama);
    const hasConsonant = chars.some((c) => profile.consonants && profile.consonants[c] != null);
    if (hasExplicitVowel || hasVirama || !hasConsonant) continue;

    const trimmed = sound.slice(0, sound.length - inherent.length);
    item.sound = trimmed;
    item.romanization = trimmed;
  }
  return items;
}

function applyAbugidaSmoothing(profile, clusters, items) {
  applyAbugidaGeminationSmoothing(profile, clusters, items);
  applyAbugidaAnusvaraHomorganic(clusters, items);
  applyAbugidaSchwaDeletion(profile, clusters, items);
  return items;
}

function smoothGraphemeItems(profile, clusters, items, options = {}) {
  const out = items.map((item) => cloneAnalysisItem(item));

  if (profile.scriptFamily === "japanese") {
    applyJapaneseGraphemeSmoothing(clusters, out);
    return out;
  }

  if (profile.scriptFamily === "arabic") {
    applyArabicSunLetterSmoothing(clusters, out);
  }

  if (profile.scriptFamily === "abugida") {
    applyAbugidaSmoothing(profile, clusters, out);
  }

  if (profile.spanMap) {
    applySpanSequenceRomanization(profile, clusters, out);
  }

  return out;
}

function analyzeGraphemeStream(language, clusters, options = {}) {
  const profile = getLanguageProfile(language);
  if (!profile) return null;
  const units = normalizeClusterSequence(profile.id, clusters, options);
  const baseItems = [];
  for (const cluster of units) {
    const item = analyzeSingleCluster(profile.id, cluster, {
      ...options,
      normalize: false,
      forceSingleCluster: true,
    });
    if (!item) return null;
    baseItems.push(item);
  }
  const items = smoothGraphemeItems(profile, units, baseItems, options);
  const joinedRomanization = items.map((item) => item.romanization || item.sound || "").join("");

  return {
    language: profile.id,
    script: profile.script,
    items,
    clusters: units,
    joinedSound: joinedRomanization,
    joinedRomanization,
  };
}

function analyzeCluster(language, cluster, options = {}) {
  const profile = getLanguageProfile(language);
  if (!profile) return null;
  const unit = normalizeUnit(profile.id, cluster, options);
  const graphemes = splitGraphemeClusters(unit);

  if (options.forceSingleCluster !== true && graphemes.length > 1) {
    const stream = analyzeGraphemeStream(profile.id, graphemes, { ...options, normalize: false, forceSingleCluster: true });
    return {
      language: profile.id,
      script: profile.script,
      cluster: unit,
      sound: stream.joinedRomanization,
      romanization: stream.joinedRomanization,
      notes: [],
      parts: stream.items.flatMap((item, clusterIndex) =>
        item.parts.map((part) => ({ ...part, cluster: item.cluster, clusterIndex }))
      ),
      graphemes: stream.items,
    };
  }

  const analysis = analyzeSingleCluster(profile.id, unit, { ...options, normalize: false, forceSingleCluster: true });
  return {
    ...analysis,
    graphemes: [cloneAnalysisItem(analysis)],
  };
}

function analyzeParts(language, parts, options = {}) {
  const arr = Array.isArray(parts) ? parts.map((x) => String(x)) : [];
  const cluster = arr.join("").normalize("NFC");
  return analyzeCluster(language, cluster, { ...options, parts: arr, normalize: false });
}

function analyzeMany(language, clusters, options = {}) {
  return analyzeGraphemeStream(language, clusters, options);
}

function normalizePronunciationComponent(part) {
  const ch = String(part && part.char != null ? part.char : "");
  const sound = String(part && (part.romanization != null ? part.romanization : part.sound) || "");
  const codePoint = String(part && part.codePoint != null ? part.codePoint : (ch ? codePointHex(ch) : ""));
  const role = String(part && part.role != null ? part.role : inferRole(ch));
  return {
    ch,
    roman: sound,
    sound,
    label: role,
    meta: codePoint,
    role,
    codePoint,
    emphasis: role === "base" || role === "letter" || role === "choseong" || role === "jungseong" || role === "jongseong",
  };
}

function buildPronunciationAnalysis(language, text, options = {}) {
  const profile = getLanguageProfile(language);
  if (!profile) return null;

  const rawText = String(text || "");
  if (!rawText) return null;

  const clusters = splitGraphemeClusters(rawText, options);
  if (!clusters.length) return null;

  const syllables = [];
  const syllableClusterIndex = [];
  let lastClusterIdx = -1;
  for (let ci = clusters.length - 1; ci >= 0; ci--) {
    if (String(clusters[ci] || "")) { lastClusterIdx = ci; break; }
  }
  for (let ci = 0; ci < clusters.length; ci++) {
    const cluster = clusters[ci];
    const surface = String(cluster || "");
    if (!surface) continue;

    const analysis = analyzeCluster(profile.id, surface, {
      ...DEFAULT_OPTIONS,
      ...options,
      normalize: options.normalize !== false,
      decompose: true,
      compatibility: options.compatibility !== false,
      preserveUnknown: !!options.preserveUnknown,
      forceSingleCluster: true,
      isFinal: ci === lastClusterIdx,
    });
    if (!analysis) continue;

    const clusterRoman = String(analysis.romanization || analysis.sound || "");
    const components = [{
      ch: surface,
      roman: clusterRoman,
      sound: String(analysis.sound || ""),
      label: "cluster",
      meta: surface ? codePointHex(surface) : "",
      role: "cluster",
      codePoint: surface ? codePointHex(surface) : "",
      emphasis: true,
    }];
    syllables.push({
      orth: surface,
      roman: clusterRoman,
      sound: String(analysis.sound || ""),
      notes: Array.isArray(analysis.notes) ? [...analysis.notes] : [],
      components,
      part_count: 1,
      has_decomposition: false,
    });
    syllableClusterIndex.push(ci);
  }

  if (syllables.length) {
    const itemView = syllables.map((s) => ({
      sound: s.sound || s.roman || "",
      romanization: s.roman || s.sound || "",
    }));
    const surfaceClusters = syllableClusterIndex.map((ci) => String(clusters[ci] || ""));

    if (profile.scriptFamily === "japanese") {
      applyJapaneseGraphemeSmoothing(surfaceClusters, itemView);
    } else {
      if (profile.scriptFamily === "arabic" || profile.scriptFamily === "abugida") {
        const effectiveClusters = surfaceClusters.slice();
        for (let idx = 0; idx + 1 < syllableClusterIndex.length; idx++) {
          const here = syllableClusterIndex[idx];
          const next = syllableClusterIndex[idx + 1];
          if (next - here > 1) {
            const gap = clusters.slice(here + 1, next).join("");
            if (gap) effectiveClusters[idx + 1] = gap + effectiveClusters[idx + 1];
          }
        }

        if (profile.scriptFamily === "arabic") {
          applyArabicSunLetterSmoothing(effectiveClusters, itemView);
        }
        if (profile.scriptFamily === "abugida") {
          applyAbugidaSmoothing(profile, effectiveClusters, itemView);
        }
      }

      if (profile.spanMap) {
        applySpanSequenceRomanization(profile, surfaceClusters, itemView);
      }
    }

    for (let i = 0; i < syllables.length; i++) {
      syllables[i].roman = itemView[i].romanization || itemView[i].sound || "";
      syllables[i].sound = itemView[i].sound || itemView[i].romanization || "";
      syllables[i].components[0].roman = syllables[i].roman;
      syllables[i].components[0].sound = syllables[i].sound;
    }
  }

  const romanParts = [];
  for (const s of syllables) if (s.roman) romanParts.push(s.roman);

  return {
    language: profile.id,
    script: profile.script,
    text: rawText,
    clusters,
    syllables,
    overallRomanization: romanParts.join(" "),
    overallSound: romanParts.join(" "),
    notes: [],
  };
}

function explainCluster(language, cluster, options = {}) {
  const x = analyzeCluster(language, cluster, options);
  if (!x) return "";

  if (options.verbose === true) {
    const lines = [`${x.cluster} -> ${x.romanization || x.sound}`];
    for (const part of x.parts) {
      lines.push(`  ${part.char} (${part.codePoint}) [${part.role}] -> ${part.romanization || part.sound}`);
    }
    if (x.notes.length) lines.push(`notes: ${x.notes.join(", ")}`);
    return lines.join("\n");
  }

  return x.romanization || x.sound || "";
}

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

function partObject(ch, sound = "", role = inferRole(ch), extra = {}) {
  return {
    char: ch,
    codePoint: codePointHex(ch),
    sound,
    role,
    ...extra,
  };
}

function inferRole(ch) {
  if (/\p{Mark}/u.test(ch)) return "mark";
  if (/\p{Letter}/u.test(ch)) return "letter";
  if (/\p{Number}/u.test(ch)) return "number";
  if (isJamo(ch)) return "jamo";
  return "other";
}

function isJamo(ch) {
  const cp = ch.codePointAt(0);
  return (
    (cp >= 0x1100 && cp <= 0x11FF) ||
    (cp >= 0x3130 && cp <= 0x318F) ||
    (cp >= 0xA960 && cp <= 0xA97F) ||
    (cp >= 0xD7B0 && cp <= 0xD7FF)
  );
}

function stripCombining(str) {
  return str.normalize("NFD").replace(/\p{Mark}+/gu, "");
}

function foldProfileText(profile, text) {
  return profile && profile.caseInsensitive ? String(text || "").toLowerCase() : String(text || "");
}

const COMMON_PUNCTUATION = {
  "-":"-","‐":"-","‑":"-","–":"-","—":"-","/":"/","\\":"\\",".":".",",":",",":":":",";":";","?":"?","!":"!","'":"'","’":"'","ʻ":"'",
  "،":",","؛":";","؟":"?","־":"-","׳":"'",'״':'"',"׃":":","।":".","॥":"..","৽":"..","ੴ":"ik-oankar","ๆ":"repeat","ฯ":"abbrev","。":".","、":","
};

const COMMON_DIGITS = {
  "٠":"0","١":"1","٢":"2","٣":"3","٤":"4","٥":"5","٦":"6","٧":"7","٨":"8","٩":"9",
  "۰":"0","۱":"1","۲":"2","۳":"3","۴":"4","۵":"5","۶":"6","۷":"7","۸":"8","۹":"9",
  "०":"0","१":"1","२":"2","३":"3","४":"4","५":"5","६":"6","७":"7","८":"8","९":"9",
  "০":"0","১":"1","২":"2","৩":"3","৪":"4","৫":"5","৬":"6","৭":"7","৮":"8","৯":"9",
  "੦":"0","੧":"1","੨":"2","੩":"3","੪":"4","੫":"5","੬":"6","੭":"7","੮":"8","੯":"9",
  "௦":"0","௧":"1","௨":"2","௩":"3","௪":"4","௫":"5","௬":"6","௭":"7","௮":"8","௯":"9",
  "๐":"0","๑":"1","๒":"2","๓":"3","๔":"4","๕":"5","๖":"6","๗":"7","๘":"8","๙":"9",
};

function mapCodepoint(profile, ch) {
  if (!ch) return "";
  if (profile.codepointMap && profile.codepointMap[ch] != null) return profile.codepointMap[ch];

  const lower = foldProfileText(profile, ch);
  if (profile.codepointMap && profile.codepointMap[lower] != null) return profile.codepointMap[lower];
  if (profile.baseMap && profile.baseMap[lower] != null) return profile.baseMap[lower];
  if (LATIN_COMBINING_MARKS[ch] != null) return LATIN_COMBINING_MARKS[ch];
  if (COMMON_DIGITS[ch] != null) return COMMON_DIGITS[ch];
  if (COMMON_PUNCTUATION[ch] != null) return COMMON_PUNCTUATION[ch];

  const decomp = ch.normalize("NFKD");
  if (decomp !== ch) {
    const recursive = Array.from(decomp).map((p) => mapCodepoint(profile, p)).join("");
    if (recursive) return recursive;
  }

  if (/\p{Mark}/u.test(ch)) return "";
  if (/\p{Script=Latin}/u.test(ch)) {
    const base = stripCombining(ch.toLowerCase());
    if (LATIN_GENERIC_BASE[base] != null) return LATIN_GENERIC_BASE[base];
  }

  return "";
}

function combineNukta(base, nuktaMap, next) {
  if (next !== "़" && next !== "়" && next !== "਼") return null;
  return nuktaMap[base] || null;
}

function analyzeBySimpleMap(profile, unit, parts, options = {}) {
  const raw = foldProfileText(profile, unit);
  if (profile.spanMap && profile.spanMap[raw] != null) {
    return {
      sound: profile.spanMap[raw],
      parts: parts.map((ch) => partObject(ch, mapCodepoint(profile, ch))),
      notes: ["span-override"],
    };
  }

  const mapped = parts.map((ch) => partObject(
    ch,
    mapCodepoint(profile, ch),
    inferRole(ch)
  ));

  let sound = mapped.map((x) => x.sound).join("");
  if (!sound && options.preserveUnknown) sound = unit;

  return { sound, parts: mapped, notes: [] };
}

/* -------------------------------------------------------------------------- */
/* Arabic-script family                                                        */
/* -------------------------------------------------------------------------- */

function analyzeArabicScript(profile, unit, parts) {
  if (profile.spanMap && profile.spanMap[unit] != null) {
    return {
      sound: profile.spanMap[unit],
      parts: parts.map((ch) => partObject(ch, mapCodepoint(profile, ch))),
      notes: ["span-override"],
    };
  }

  const bases = parts.filter((ch) => !ARABIC_MARKS[ch]);
  if (bases.length === 1) {
    const base = bases[0];
    const marks = parts.filter((ch) => ARABIC_MARKS[ch]);
    const { sound, partSounds } = composeArabicBase(profile, base, marks);
    return {
      sound,
      parts: parts.map((ch) => partObject(ch, partSounds[ch] ?? mapCodepoint(profile, ch), inferRole(ch))),
      notes: marks.length ? ["base+marks"] : [],
    };
  }

  const partObjs = [];
  let out = "";
  for (const ch of parts) {
    const s = mapCodepoint(profile, ch);
    partObjs.push(partObject(ch, s));
    out += s;
  }
  return { sound: out, parts: partObjs, notes: [] };
}

function composeArabicBase(profile, base, marks) {
  let baseSound = profile.baseLetters[base] ?? mapCodepoint(profile, base);
  const markSoundMap = {};
  const vowels = [];
  let geminated = false;

  const hasHamzaAbove = marks.includes("ٔ");
  const hasHamzaBelow = marks.includes("ٕ");

  if (base === "ا" && (hasHamzaAbove || hasHamzaBelow)) {
    baseSound = "ʔ";
  }
  if (base === "و" && hasHamzaAbove) {
    baseSound = "ʔ";
  }
  if ((base === "ي" || base === "ى") && hasHamzaAbove) {
    baseSound = "ʔ";
  }

  // ta marbuta behaves differently when vocalized
  if (base === "ة" && marks.length) {
    baseSound = "t";
  }

  for (const mark of marks) {
    const v = ARABIC_MARKS[mark] ?? "";
    if (mark === "ّ") {
      geminated = true;
      markSoundMap[mark] = "geminate";
      continue;
    }
    if (mark === "ٔ" || mark === "ٕ") {
      markSoundMap[mark] = "hamza";
      continue;
    }
    vowels.push(v);
    markSoundMap[mark] = v;
  }

  let sound = geminated ? (baseSound + baseSound) : baseSound;
  sound += vowels.join("");

  // long-vowel / mater hints for Persian and Urdu
  // Letters that are inherently vowels or hamza carriers in Persian — no synthetic
  // vowel appended to these even in unvocalized text.
  const PERSIAN_MATER_OR_CARRIER = new Set(["ا","آ","و","ی","ئ","ء","أ","ؤ","إ","ة","ۀ"]);

  if (!marks.length) {
    if (profile.id === "persian") {
      if (base === "ا" || base === "آ") sound = "â";
      if (base === "و") sound = "v";
      if (base === "ی") sound = "y";
      if (base === "ه") sound = "h/e";
    }
    if (profile.id === "urdu") {
      if (base === "و") sound = "v/u/o";
      if (base === "ی") sound = "y/i/e";
      if (base === "ے") sound = "e";
      if (base === "ں") sound = "̃";
    }
  }

  const partSounds = { [base]: baseSound, ...markSoundMap };
  return { sound, partSounds };
}

/* -------------------------------------------------------------------------- */
/* Hebrew                                                                      */
/* -------------------------------------------------------------------------- */

// Letters that are inherently silent or act as vowel carriers — no synthetic
// vowel appended to these even in unvocalized text.
const HEBREW_SILENT_OR_MATER = new Set(["א", "ה", "ע", "ו", "י", "ן", "ם", "ף", "ך", "ץ"]);

function analyzeHebrew(profile, unit, parts, options = {}) {
  if (profile.spanMap && profile.spanMap[unit] != null) {
    return {
      sound: profile.spanMap[unit],
      parts: parts.map((ch) => partObject(ch, mapCodepoint(profile, ch))),
      notes: ["span-override"],
    };
  }

  const bases = parts.filter((ch) => !HEBREW_MARKS[ch]);
  if (bases.length === 1) {
    const base = bases[0];
    const marks = parts.filter((ch) => HEBREW_MARKS[ch]);
    const isFinal = !!options.isFinal;
    const { sound, partSounds } = composeHebrewBase(base, marks, isFinal);
    return {
      sound,
      parts: parts.map((ch) => partObject(ch, partSounds[ch] ?? mapCodepoint(profile, ch), inferRole(ch))),
      notes: marks.length ? ["base+niqqud"] : (sound !== (HEBREW_LETTERS[base] ?? "") ? ["synth-vowel"] : []),
    };
  }

  const mapped = parts.map((ch) => partObject(ch, mapCodepoint(profile, ch)));
  return { sound: mapped.map((x) => x.sound).join(""), parts: mapped, notes: [] };
}

function composeHebrewBase(base, marks, isFinal) {
  let baseSound = HEBREW_LETTERS[base] ?? "";
  const partSounds = { [base]: baseSound };

  const hasDagesh = marks.includes("\u05BC");
  const hasShinDot = marks.includes("\u05C1");
  const hasSinDot = marks.includes("\u05C2");
  const hasHolam = marks.includes("\u05B9") || marks.includes("\u05BA");
  const hasShuruk = base === "ו" && hasDagesh;
  const hasAnyVowelMark = marks.some((m) => HEBREW_MARKS[m] && m !== "\u05BC" && m !== "\u05C1" && m !== "\u05C2");

  if (hasDagesh && HEBREW_BEGADKEFAT_HARD[base]) {
    baseSound = HEBREW_BEGADKEFAT_HARD[base];
    partSounds["\u05BC"] = "hard";
  }
  if (base === "ש") {
    if (hasSinDot) {
      baseSound = "s";
      partSounds["\u05C2"] = "sin";
    } else if (hasShinDot) {
      baseSound = "sh";
      partSounds["\u05C1"] = "shin";
    }
  }
  if (base === "ו" && hasShuruk) {
    return {
      sound: "u",
      partSounds: { [base]: "u", "\u05BC": "u" },
    };
  }
  if (base === "ו" && hasHolam) {
    const partSounds2 = { [base]: "o" };
    for (const m of marks) partSounds2[m] = HEBREW_MARKS[m] ?? "";
    return { sound: "o", partSounds: partSounds2 };
  }

  let vowel = "";
  for (const mark of marks) {
    if (mark === "\u05BC" || mark === "\u05C1" || mark === "\u05C2") continue;
    vowel += HEBREW_MARKS[mark] ?? "";
    partSounds[mark] = HEBREW_MARKS[mark] ?? "";
  }

  // Synthetic default vowel for unvocalized text: insert short "a" after
  // consonants that carry no niqqud, unless word-final or silent/mater lectionis.
  if (!hasAnyVowelMark && !vowel && baseSound && !isFinal && !HEBREW_SILENT_OR_MATER.has(base)) {
    vowel = "a";
  }

  partSounds[base] = baseSound;
  return { sound: baseSound + vowel, partSounds };
}

/* -------------------------------------------------------------------------- */
/* Greek                                                                       */
/* -------------------------------------------------------------------------- */

function analyzeGreek(profile, unit, parts) {
  const raw = foldProfileText(profile, unit);

  if (profile.spanMap && profile.spanMap[raw] != null) {
    return {
      sound: profile.spanMap[raw],
      parts: parts.map((ch) => partObject(ch, mapCodepoint(profile, ch))),
      notes: ["span-override"],
    };
  }

  const mapped = parts.map((ch) => partObject(ch, mapCodepoint(profile, ch)));
  const baseLetters = parts.filter((ch) => !/\p{Mark}/u.test(ch));
  let sound = baseLetters.map((ch) => mapCodepoint(profile, ch)).join("");

  if (parts.some((x) => GREEK_ROUGH_BREATHING.has(x)) && sound) sound = "h" + sound;
  if (parts.some((x) => x === "\u0345")) sound += "i";

  return { sound, parts: mapped, notes: [] };
}

/* -------------------------------------------------------------------------- */
/* Japanese                                                                    */
/* -------------------------------------------------------------------------- */

function analyzeJapanese(profile, unit, parts) {
  if (/\p{Script=Han}/u.test(unit)) {
    return {
      sound: "",
      parts: parts.map((ch) => partObject(ch, "", inferRole(ch))),
      notes: ["han-ignored"],
    };
  }

  if (JAPANESE_SPAN_MAP[unit] != null) {
    return {
      sound: JAPANESE_SPAN_MAP[unit],
      parts: parts.map((ch) => partObject(ch, JAPANESE_PART_MAP[ch] ?? "", inferRole(ch))),
      notes: ["span-override"],
    };
  }

  const baseLetters = parts.filter((ch) => !/\p{Mark}/u.test(ch));
  let sound = "";

  if (baseLetters.length === 1) {
    const base = baseLetters[0];
    sound = JAPANESE_BASE_MAP[base] ?? "";
    if (parts.includes("\u3099")) sound = JAPANESE_VOICED_OVERRIDES[sound] || sound;
    if (parts.includes("\u309A")) sound = JAPANESE_SEMIVOICED_OVERRIDES[sound] || sound;
    if (base === "っ" || base === "ッ") sound = "";
    if (base === "ー") sound = "";
  } else {
    sound = composeJapaneseSpan(unit, baseLetters);
  }

  const partObjs = parts.map((ch) => partObject(ch, JAPANESE_PART_MAP[ch] ?? "", inferRole(ch)));
  return { sound, parts: partObjs, notes: [] };
}

function composeJapaneseSpan(unit, baseLetters) {
  if (JAPANESE_SPAN_MAP[unit]) return JAPANESE_SPAN_MAP[unit];

  const raw = baseLetters.join("");
  if (JAPANESE_SPAN_MAP[raw]) return JAPANESE_SPAN_MAP[raw];

  if (baseLetters.length === 2) {
    const [a, b] = baseLetters;
    const first = JAPANESE_BASE_MAP[a] ?? "";
    const second = JAPANESE_BASE_MAP[b] ?? "";
    if (JAPANESE_SMALL_Y[b]) {
      const stem = first.replace(/[aeiou]$/, "");
      const special = JAPANESE_YOON_STEMS[first] || stem;
      return special + JAPANESE_SMALL_Y[b];
    }
    if (JAPANESE_SMALL_VOWEL[b]) {
      const prefix = JAPANESE_FOREIGN_STEMS[first] || first.replace(/[aeiou]$/, "");
      return prefix + JAPANESE_SMALL_VOWEL[b];
    }
    if ((a === "っ" || a === "ッ") && second) {
      return second[0] + second;
    }
  }

  if (baseLetters.length > 1) {
    let out = "";
    for (let i = 0; i < baseLetters.length; i += 1) {
      const ch = baseLetters[i];
      if ((ch === "っ" || ch === "ッ") && i + 1 < baseLetters.length) {
        const next = composeJapaneseSpan(baseLetters.slice(i + 1).join(""), baseLetters.slice(i + 1));
        out += next ? next[0] : "Q";
        continue;
      }
      out += JAPANESE_BASE_MAP[ch] ?? "";
    }
    return out;
  }

  return raw.split("").map((ch) => JAPANESE_BASE_MAP[ch] ?? "").join("");
}

/* -------------------------------------------------------------------------- */
/* Hangul                                                                      */
/* -------------------------------------------------------------------------- */

function analyzeHangul(profile, unit) {
  const parts = decomposeHangulString(unit);
  const objs = parts.map((x) => partObject(x.char, x.sound, x.role));
  return {
    sound: parts.map((x) => x.sound).join(""),
    parts: objs,
    notes: ["algorithmic-hangul"],
  };
}

function decomposeHangulString(unit) {
  const out = [];
  for (const ch of Array.from(unit)) {
    const cp = ch.codePointAt(0);
    if (cp >= 0xAC00 && cp <= 0xD7A3) {
      const SBase = 0xAC00;
      const LBase = 0x1100;
      const VBase = 0x1161;
      const TBase = 0x11A7;
      const VCount = 21;
      const TCount = 28;
      const NCount = VCount * TCount;
      const sIndex = cp - SBase;
      const lIndex = Math.floor(sIndex / NCount);
      const vIndex = Math.floor((sIndex % NCount) / TCount);
      const tIndex = sIndex % TCount;

      const L = String.fromCodePoint(LBase + lIndex);
      const V = String.fromCodePoint(VBase + vIndex);
      out.push({ char: L, sound: HANGUL_CHO[lIndex], role: "choseong" });
      out.push({ char: V, sound: HANGUL_JUNG[vIndex], role: "jungseong" });
      if (tIndex > 0) {
        const T = String.fromCodePoint(TBase + tIndex);
        out.push({ char: T, sound: HANGUL_JONG[tIndex], role: "jongseong" });
      }
      continue;
    }

    for (const p of Array.from(ch.normalize("NFD"))) {
      out.push({ char: p, sound: HANGUL_JAMO_MAP[p] || "", role: "jamo" });
    }
  }
  return out;
}

/* -------------------------------------------------------------------------- */
/* Brahmic / abugida family                                                    */
/* -------------------------------------------------------------------------- */

function analyzeAbugida(profile, unit, parts) {
  if (profile.spanMap && profile.spanMap[unit] != null) {
    return {
      sound: profile.spanMap[unit],
      parts: parts.map((ch) => partObject(ch, mapCodepoint(profile, ch))),
      notes: ["span-override"],
    };
  }

  const partObjs = parts.map((ch) => partObject(
    ch,
    profile.codepointMap?.[ch] ??
      profile.independentVowels?.[ch] ??
      profile.vowelSigns?.[ch] ??
      profile.consonants?.[ch] ??
      profile.marks?.[ch] ??
      ""
  ));

  const sound = composeAbugida(profile, parts);
  return { sound, parts: partObjs, notes: [] };
}

function findLastRomanVowelIndex(value) {
  const chars = Array.from(String(value || ""));
  for (let i = chars.length - 1; i >= 0; i -= 1) {
    if (/[aeiouyāēīōūăâêôơưəɨʉ]/i.test(chars[i])) {
      return i;
    }
  }
  return -1;
}

function applyRomanCombiningMark(value, combiningMark) {
  const chars = Array.from(String(value || ""));
  if (!chars.length || !combiningMark) return String(value || "");

  const index = findLastRomanVowelIndex(chars.join(""));
  if (index >= 0) {
    chars[index] = (chars[index] + combiningMark).normalize("NFC");
    return chars.join("");
  }

  return chars.join("") + combiningMark;
}

function applyThaiToneToRomanization(value, toneName) {
  const roman = String(value || "");
  if (!roman || !toneName) return roman;

  const combiningMark = THAI_TONE_COMBINING_MARKS[toneName];
  if (!combiningMark) return roman;
  return applyRomanCombiningMark(roman, combiningMark);
}

function composeAbugida(profile, parts) {
  let out = "";
  let i = 0;
  let pendingGeminate = false;

  while (i < parts.length) {
    const ch = parts[i];

    if (profile.geminationMark && ch === profile.geminationMark) {
      pendingGeminate = true;
      i += 1;
      continue;
    }

    if (profile.independentVowels[ch]) {
      out += profile.independentVowels[ch];
      i += 1;
      continue;
    }

    if (profile.marks[ch]) {
      out += profile.marks[ch];
      i += 1;
      continue;
    }

    let combined = ch;
    const nuktaCombined = combineNukta(ch, profile.nuktaMap || {}, parts[i + 1]);
    let consumedNukta = false;
    if (nuktaCombined) {
      combined = nuktaCombined;
      consumedNukta = true;
    }

    if (profile.consonants[combined]) {
      let consonantSound = profile.consonants[combined];
      if (pendingGeminate) {
        const onsetMatch = consonantSound.match(/^[^aeiouāēīōūâêîôû]+/i);
        if (onsetMatch) consonantSound = onsetMatch[0] + consonantSound;
        pendingGeminate = false;
      }
      out += consonantSound;

      const toneMark = profile.toneConsonants && profile.toneConsonants[combined];
      let vowel = profile.inherentVowel || "";
      let finals = "";
      let j = i + 1 + (consumedNukta ? 1 : 0);

      while (j < parts.length) {
        const next = parts[j];

        if (profile.virama && next === profile.virama) {
          vowel = "";
          j += 1;
          break;
        }

        if (profile.vowelSigns[next]) {
          vowel = profile.vowelSigns[next];
          j += 1;
          continue;
        }

        if (profile.marks[next]) {
          finals += profile.marks[next];
          j += 1;
          continue;
        }

        if (profile.nuktaMap && (next === "़" || next === "়" || next === "਼")) {
          j += 1;
          continue;
        }

        break;
      }

      if (toneMark && vowel) vowel = applyRomanCombiningMark(vowel, toneMark);

      out += vowel + finals;
      i = j;
      continue;
    }

    if (profile.vowelSigns[ch]) {
      out += profile.vowelSigns[ch];
      i += 1;
      continue;
    }

    i += 1;
  }

  return out;
}

/* -------------------------------------------------------------------------- */
/* Thai                                                                        */
/* -------------------------------------------------------------------------- */

function analyzeThai(profile, unit, parts) {
  if (THAI_SPAN_MAP[unit] != null) {
    return {
      sound: THAI_SPAN_MAP[unit],
      parts: parts.map((ch) => thaiPartObject(ch)),
      notes: ["span-override"],
      derivation: {
        kind: "thai-span-override",
        surface: unit,
        output: THAI_SPAN_MAP[unit],
      },
    };
  }

  const composed = composeThaiCluster(parts);
  const partObjs = parts.map((ch) => thaiPartObject(ch));
  return {
    sound: composed.sound,
    parts: partObjs,
    notes: composed.notes,
    derivation: composed.derivation,
  };
}

function thaiPartObject(ch) {
  return partObject(
    ch,
    THAI_PART_MAP[ch] ?? "",
    inferRole(ch),
    THAI_PART_DETAIL_MAP[ch]
      ? {
          rawSound: THAI_PART_DETAIL_MAP[ch].rawSound,
          detail: THAI_PART_DETAIL_MAP[ch].detail,
        }
      : {}
  );
}

function composeThaiCluster(parts) {
  const raw = parts.join("");
  if (THAI_SPAN_MAP[raw]) {
    return {
      sound: THAI_SPAN_MAP[raw],
      notes: ["span-override"],
      derivation: {
        kind: "thai-span-override",
        surface: raw,
        output: THAI_SPAN_MAP[raw],
      },
    };
  }

  const onsetChars = [];
  const codaChars = [];
  let vowelPrefix = "";
  let vowelCore = "";
  let toneName = "";
  let silentMark = false;
  let shorteningMark = false;
  let hasShortVowelChar = false;
  let hasLongVowelChar = false;
  let hasMainVowelSeen = false;

  for (const ch of parts) {
    if (THAI_PREFIX_VOWELS[ch]) {
      vowelPrefix += THAI_PREFIX_VOWELS[ch];
      if (THAI_SHORT_VOWEL_CHARS.has(ch)) hasShortVowelChar = true;
      if (THAI_LONG_VOWEL_CHARS.has(ch)) hasLongVowelChar = true;
      continue;
    }
    if (THAI_VOWELS[ch] != null) {
      vowelCore += THAI_VOWELS[ch];
      hasMainVowelSeen = true;
      if (THAI_SHORT_VOWEL_CHARS.has(ch)) hasShortVowelChar = true;
      if (THAI_LONG_VOWEL_CHARS.has(ch)) hasLongVowelChar = true;
      continue;
    }
    if (ch === "์") { silentMark = true; continue; }
    if (ch === "็") { shorteningMark = true; hasShortVowelChar = true; continue; }
    if (THAI_TONE_MARKS[ch]) { toneName = THAI_TONE_MARKS[ch]; continue; }
    if (THAI_CONSONANTS[ch]) {
      if (!hasMainVowelSeen) onsetChars.push(ch);
      else codaChars.push(ch);
    }
  }

  let effectiveClass = "mid";
  let onsetCharsForOutput = onsetChars.slice();

  if (onsetChars.length >= 2 && onsetChars[0] === "ห" && THAI_CLASS[onsetChars[1]] === "low") {
    effectiveClass = "high";
    onsetCharsForOutput = onsetChars.slice(1);
  } else if (onsetChars.length >= 2 && onsetChars[0] === "อ" && onsetChars[1] === "ย") {
    effectiveClass = "mid";
    onsetCharsForOutput = onsetChars.slice(1);
  } else if (onsetChars.length >= 1) {
    effectiveClass = THAI_CLASS[onsetChars[0]] || "mid";
    if (onsetChars[0] === "อ" && onsetChars.length === 1 && (vowelPrefix || vowelCore || hasMainVowelSeen)) {
      onsetCharsForOutput = [];
    }
  }

  let onsetRom = "";
  for (const ch of onsetCharsForOutput) onsetRom += THAI_CONSONANTS[ch] || "";

  let codaRom = "";
  for (const ch of codaChars) codaRom += THAI_FINALS[ch] ?? THAI_CONSONANTS[ch] ?? "";

  if (silentMark && codaRom) codaRom = codaRom.slice(0, -1);

  const finalCodaChar = codaRom.slice(-1);
  const endsInStop = ["p","t","k"].includes(finalCodaChar);
  const hasCoda = codaRom.length > 0;
  const isShort = hasShortVowelChar && !hasLongVowelChar;
  const isLong = hasLongVowelChar && !hasShortVowelChar;
  const isDeadSyllable = endsInStop || (!hasCoda && isShort);
  const vowelIsLong = isLong || /[āēīōūâêîôû]/.test(vowelCore);

  let computedTone = "";
  if (toneName) {
    if (toneName === "low") {
      computedTone = (effectiveClass === "low") ? "falling" : "low";
    } else if (toneName === "falling") {
      computedTone = (effectiveClass === "low") ? "high" : "falling";
    } else if (toneName === "high") {
      computedTone = "high";
    } else if (toneName === "rising") {
      computedTone = "rising";
    }
  } else {
    if (!isDeadSyllable) {
      if (effectiveClass === "high") computedTone = "rising";
    } else if (effectiveClass === "low") {
      computedTone = vowelIsLong ? "falling" : "high";
    } else {
      computedTone = "low";
    }
  }

  if (silentMark && !codaRom && !vowelPrefix && !vowelCore && onsetRom) {
    return {
      sound: onsetRom,
      notes: [],
      derivation: {
        kind: "thai-cluster",
        surface: raw,
        onset: onsetRom,
        vowelPrefix: "",
        vowelCore: "",
        coda: "",
        tone: "",
        silentMark,
        shorteningMark,
        output: onsetRom,
      },
    };
  }

  const body = (!vowelPrefix && !vowelCore) ? onsetRom + codaRom : onsetRom + vowelPrefix + vowelCore + codaRom;
  const sound = applyThaiToneToRomanization(body, computedTone);

  return {
    sound,
    notes: [],
    derivation: {
      kind: "thai-cluster",
      surface: raw,
      onset: onsetRom,
      vowelPrefix,
      vowelCore,
      coda: codaRom,
      tone: computedTone,
      silentMark,
      shorteningMark,
      output: sound,
    },
  };
}

/* -------------------------------------------------------------------------- */
/* Latin family (Old English only; modern Latin scripts intentionally removed) */
/* -------------------------------------------------------------------------- */

function analyzeLatin(profile, unit, parts) {
  const raw = profile.caseInsensitive ? unit.toLowerCase() : unit;
  if (profile.spanMap && profile.spanMap[raw] != null) {
    return {
      sound: profile.spanMap[raw],
      parts: parts.map((ch) => partObject(ch, latinPartSound(profile, ch), inferRole(ch))),
      notes: ["span-override"],
    };
  }

  const mapped = parts.map((ch) => partObject(ch, latinPartSound(profile, ch), inferRole(ch)));
  let sound = composeLatin(profile, raw, parts);

  if (!sound) sound = mapped.map((x) => x.sound).join("");
  return { sound, parts: mapped, notes: [] };
}

function latinPartSound(profile, ch) {
  return mapCodepoint(profile, ch);
}

function longestSpanCompose(raw, spanMap, fallbackCharFn) {
  if (!raw) return "";
  let i = 0;
  let out = "";
  while (i < raw.length) {
    let matched = null;
    const maxLen = Math.min(5, raw.length - i);
    for (let len = maxLen; len >= 1; len -= 1) {
      const slice = raw.slice(i, i + len);
      if (spanMap && spanMap[slice] != null) {
        matched = { len, sound: spanMap[slice] };
        break;
      }
    }
    if (matched) {
      out += matched.sound;
      i += matched.len;
      continue;
    }
    out += fallbackCharFn(raw[i]);
    i += 1;
  }
  return out;
}

function composeLatin(profile, raw, parts) {
  if (profile.composeLatin) {
    const v = profile.composeLatin(raw, parts);
    if (v != null) return v;
  }

  const bare = stripCombining(raw);
  const direct = longestSpanCompose(raw, profile.spanMap || {}, (ch) => latinPartSound(profile, ch));
  if (direct) return direct;
  return longestSpanCompose(bare, profile.spanMap || {}, (ch) => latinPartSound(profile, ch));
}

/* -------------------------------------------------------------------------- */
/* Data tables                                                                 */
/* -------------------------------------------------------------------------- */

/* Arabic, Persian, Urdu */

const ARABIC_BASE_LETTERS = {
  "ء": "ʔ", "آ": "ʔā", "أ": "ʔa", "ؤ": "ʔu", "إ": "ʔi", "ئ": "ʔi", "ـ": "",
  "ا": "ā", "ب": "b", "ة": "a", "ت": "t", "ث": "th", "ج": "j", "ح": "ḥ",
  "خ": "kh", "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh",
  "ص": "ṣ", "ض": "ḍ", "ط": "ṭ", "ظ": "ẓ", "ع": "ʿ", "غ": "gh", "ف": "f",
  "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w",
  "ى": "ā", "ي": "y", "ٱ": "a", "لا": "lā", "ﻻ": "lā",
};

const ARABIC_MARKS = {
  "َ": "a", "ً": "an", "ُ": "u", "ٌ": "un", "ِ": "i", "ٍ": "in",
  "ْ": "", "ّ": "", "ٰ": "ā", "ٔ": "ʔ", "ٕ": "ʔ",
};

const PERSIAN_BASE_OVERRIDES = {
  "پ": "p", "چ": "ch", "ژ": "zh", "گ": "g", "ک": "k", "ی": "y",
  "و": "v", "ا": "â", "آ": "â", "ۀ": "e", "ة": "e",
};

const URDU_BASE_OVERRIDES = {
  "پ": "p", "ٹ": "ṭ", "ث": "s", "ج": "j", "چ": "ch", "ح": "h", "خ": "kh",
  "د": "d", "ڈ": "ḍ", "ذ": "z", "ر": "r", "ڑ": "ṛ", "ز": "z", "ژ": "zh",
  "س": "s", "ش": "sh", "ص": "s", "ض": "z", "ط": "t", "ظ": "z", "ع": "ʿ",
  "غ": "gh", "ف": "f", "ق": "q", "ک": "k", "گ": "g", "ل": "l", "م": "m",
  "ن": "n", "ں": "̃", "و": "v/u/o", "ہ": "h", "ھ": "h", "ء": "ʔ",
  "ی": "y/i", "ے": "e", "ۓ": "e",
};

/* Hebrew */

const HEBREW_LETTERS = {
  "א": "ʔ", "ב": "v", "ג": "g", "ד": "d", "ה": "h", "ו": "v", "ז": "z",
  "ח": "ḥ", "ט": "ṭ", "י": "y", "כ": "kh", "ך": "kh", "ל": "l", "מ": "m",
  "ם": "m", "נ": "n", "ן": "n", "ס": "s", "ע": "ʿ", "פ": "f", "ף": "f",
  "צ": "ts", "ץ": "ts", "ק": "q", "ר": "r", "ש": "sh", "ת": "t",
};

const HEBREW_BEGADKEFAT_HARD = {
  "ב": "b", "כ": "k", "ך": "k", "פ": "p", "ף": "p", "ת": "t",
};

const HEBREW_MARKS = {
  "\u05B0": "ə", "\u05B1": "e", "\u05B2": "a", "\u05B3": "o",
  "\u05B4": "i", "\u05B5": "e", "\u05B6": "e", "\u05B7": "a",
  "\u05B8": "a", "\u05B9": "o", "\u05BA": "o", "\u05BB": "u",
  "\u05BC": "", "\u05BD": "", "\u05BF": "", "\u05C1": "", "\u05C2": "",
  "\u05C7": "a",
};

/* Greek */

const GREEK_MARKS = {
  "\u0313": "", "\u0314": "h", "\u0300": "", "\u0301": "", "\u0342": "", "\u0345": "i",
};

const GREEK_ROUGH_BREATHING = new Set(["\u0314"]);

const GREEK_MODERN = {
  "α": "a", "β": "v", "γ": "g", "δ": "dh", "ε": "e", "ζ": "z", "η": "i",
  "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
  "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "i",
  "φ": "f", "χ": "kh", "ψ": "ps", "ω": "o",
};

const GREEK_ANCIENT = {
  "α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "zd", "η": "ē",
  "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "ks",
  "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y",
  "φ": "ph", "χ": "kh", "ψ": "ps", "ω": "ō",
};

const GREEK_MODERN_SPAN = {
  "αι": "e", "ει": "i", "οι": "i", "ου": "u", "αυ": "av/af", "ευ": "ev/ef", "ηυ": "iv/if",
  "γκ": "gk", "μπ": "b", "ντ": "d", "τσ": "ts", "τζ": "dz",
};

const GREEK_ANCIENT_SPAN = {
  "αι": "ai", "ει": "ei", "οι": "oi", "ου": "ou", "αυ": "au", "ευ": "eu", "ηυ": "ēu",
  "γγ": "ng", "γκ": "nk", "γχ": "nkh",
};

/* Cyrillic / Armenian */

const CYRILLIC_RUSSIAN = {
  "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e/ye","ё":"yo","ж":"zh","з":"z",
  "и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r",
  "с":"s","т":"t","у":"u","ф":"f","х":"kh","ц":"ts","ч":"ch","ш":"sh","щ":"shch",
  "ъ":"ʺ","ы":"y","ь":"ʹ","э":"e","ю":"yu","я":"ya",
};

const ARMENIAN = {
  "ա":"a","բ":"b","գ":"g","դ":"d","ե":"e","զ":"z","է":"ē","ը":"ə","թ":"tʿ","ժ":"zh",
  "ի":"i","լ":"l","խ":"kh","ծ":"ts","կ":"k","հ":"h","ձ":"dz","ղ":"gh","ճ":"č","մ":"m",
  "յ":"y","ն":"n","շ":"sh","ո":"o/vo","չ":"chʿ","պ":"p","ջ":"j","ռ":"ṙ","ս":"s",
  "վ":"v","տ":"t","ր":"r","ց":"cʿ","ւ":"w","փ":"pʿ","ք":"kʿ","օ":"ō","ֆ":"f",
};

/* Japanese */

const JAPANESE_BASE_MAP = {
  // Hiragana
  "あ":"a","い":"i","う":"u","え":"e","お":"o",
  "か":"ka","き":"ki","く":"ku","け":"ke","こ":"ko",
  "さ":"sa","し":"shi","す":"su","せ":"se","そ":"so",
  "た":"ta","ち":"chi","つ":"tsu","て":"te","と":"to",
  "な":"na","に":"ni","ぬ":"nu","ね":"ne","の":"no",
  "は":"ha","ひ":"hi","ふ":"fu","へ":"he","ほ":"ho",
  "ま":"ma","み":"mi","む":"mu","め":"me","も":"mo",
  "や":"ya","ゆ":"yu","よ":"yo",
  "ら":"ra","り":"ri","る":"ru","れ":"re","ろ":"ro",
  "わ":"wa","ゐ":"wi","ゑ":"we","を":"o","ん":"n",
  "が":"ga","ぎ":"gi","ぐ":"gu","げ":"ge","ご":"go",
  "ざ":"za","じ":"ji","ず":"zu","ぜ":"ze","ぞ":"zo",
  "だ":"da","ぢ":"ji","づ":"zu","で":"de","ど":"do",
  "ば":"ba","び":"bi","ぶ":"bu","べ":"be","ぼ":"bo",
  "ぱ":"pa","ぴ":"pi","ぷ":"pu","ぺ":"pe","ぽ":"po",
  "ゔ":"vu",
  "ぁ":"a","ぃ":"i","ぅ":"u","ぇ":"e","ぉ":"o",
  "ゃ":"ya","ゅ":"yu","ょ":"yo","ゎ":"wa","っ":"Q","ー":"ː",
  // Katakana
  "ア":"a","イ":"i","ウ":"u","エ":"e","オ":"o",
  "カ":"ka","キ":"ki","ク":"ku","ケ":"ke","コ":"ko",
  "サ":"sa","シ":"shi","ス":"su","セ":"se","ソ":"so",
  "タ":"ta","チ":"chi","ツ":"tsu","テ":"te","ト":"to",
  "ナ":"na","ニ":"ni","ヌ":"nu","ネ":"ne","ノ":"no",
  "ハ":"ha","ヒ":"hi","フ":"fu","ヘ":"he","ホ":"ho",
  "マ":"ma","ミ":"mi","ム":"mu","メ":"me","モ":"mo",
  "ヤ":"ya","ユ":"yu","ヨ":"yo",
  "ラ":"ra","リ":"ri","ル":"ru","レ":"re","ロ":"ro",
  "ワ":"wa","ヰ":"wi","ヱ":"we","ヲ":"o","ン":"n",
  "ガ":"ga","ギ":"gi","グ":"gu","ゲ":"ge","ゴ":"go",
  "ザ":"za","ジ":"ji","ズ":"zu","ゼ":"ze","ゾ":"zo",
  "ダ":"da","ヂ":"ji","ヅ":"zu","デ":"de","ド":"do",
  "バ":"ba","ビ":"bi","ブ":"bu","ベ":"be","ボ":"bo",
  "パ":"pa","ピ":"pi","プ":"pu","ペ":"pe","ポ":"po",
  "ヴ":"vu",
  "ァ":"a","ィ":"i","ゥ":"u","ェ":"e","ォ":"o",
  "ャ":"ya","ュ":"yu","ョ":"yo","ヮ":"wa","ッ":"Q",
};

const JAPANESE_PART_MAP = {
  ...JAPANESE_BASE_MAP,
  "\u3099": "dakuten",
  "\u309A": "handakuten",
};

const JAPANESE_VOICED_OVERRIDES = {
  "ka":"ga","ki":"gi","ku":"gu","ke":"ge","ko":"go",
  "sa":"za","shi":"ji","su":"zu","se":"ze","so":"zo",
  "ta":"da","chi":"ji","tsu":"zu","te":"de","to":"do",
  "ha":"ba","hi":"bi","fu":"bu","he":"be","ho":"bo",
  "u":"vu",
};

const JAPANESE_SEMIVOICED_OVERRIDES = {
  "ha":"pa","hi":"pi","fu":"pu","he":"pe","ho":"po",
};

const JAPANESE_SPAN_MAP = {
  "きゃ":"kya","きゅ":"kyu","きょ":"kyo","ぎゃ":"gya","ぎゅ":"gyu","ぎょ":"gyo",
  "しゃ":"sha","しゅ":"shu","しょ":"sho","じゃ":"ja","じゅ":"ju","じょ":"jo",
  "ちゃ":"cha","ちゅ":"chu","ちょ":"cho","にゃ":"nya","にゅ":"nyu","にょ":"nyo",
  "ひゃ":"hya","ひゅ":"hyu","ひょ":"hyo","びゃ":"bya","びゅ":"byu","びょ":"byo",
  "ぴゃ":"pya","ぴゅ":"pyu","ぴょ":"pyo","みゃ":"mya","みゅ":"myu","みょ":"myo",
  "りゃ":"rya","りゅ":"ryu","りょ":"ryo",
  "キャ":"kya","キュ":"kyu","キョ":"kyo","ギャ":"gya","ギュ":"gyu","ギョ":"gyo",
  "シャ":"sha","シュ":"shu","ショ":"sho","ジャ":"ja","ジュ":"ju","ジョ":"jo",
  "チャ":"cha","チュ":"chu","チョ":"cho","ニャ":"nya","ニュ":"nyu","ニョ":"nyo",
  "ヒャ":"hya","ヒュ":"hyu","ヒョ":"hyo","ビャ":"bya","ビュ":"byu","ビョ":"byo",
  "ピャ":"pya","ピュ":"pyu","ピョ":"pyo","ミャ":"mya","ミュ":"myu","ミョ":"myo",
  "リャ":"rya","リュ":"ryu","リョ":"ryo",
  // foreign-sound katakana
  "ティ":"ti","ディ":"di","トゥ":"tu","ドゥ":"du","チェ":"che","シェ":"she","ジェ":"je",
  "ファ":"fa","フィ":"fi","フェ":"fe","フォ":"fo","ウィ":"wi","ウェ":"we","ウォ":"wo",
  "ツァ":"tsa","ツィ":"tsi","ツェ":"tse","ツォ":"tso",
};

/* Hangul */

const HANGUL_CHO = [
  "g","kk","n","d","tt","r","m","b","pp","s","ss","", "j","jj","ch","k","t","p","h"
];
const HANGUL_JUNG = [
  "a","ae","ya","yae","eo","e","yeo","ye","o","wa","wae","oe","yo","u","wo","we","wi","yu","eu","ui","i"
];
const HANGUL_JONG = [
  "", "k","k","ks","n","nj","nh","t","l","lk","lm","lb","ls","lt","lp","lh","m","p","ps","t","t","ng","t","t","k","t","p","h"
];
const HANGUL_JAMO_MAP = {
  "ᄀ":"g","ᄁ":"kk","ᄂ":"n","ᄃ":"d","ᄄ":"tt","ᄅ":"r","ᄆ":"m","ᄇ":"b","ᄈ":"pp",
  "ᄉ":"s","ᄊ":"ss","ᄋ":"","ᄌ":"j","ᄍ":"jj","ᄎ":"ch","ᄏ":"k","ᄐ":"t","ᄑ":"p","ᄒ":"h",
  "ᅡ":"a","ᅢ":"ae","ᅣ":"ya","ᅤ":"yae","ᅥ":"eo","ᅦ":"e","ᅧ":"yeo","ᅨ":"ye",
  "ᅩ":"o","ᅪ":"wa","ᅫ":"wae","ᅬ":"oe","ᅭ":"yo","ᅮ":"u","ᅯ":"wo","ᅰ":"we",
  "ᅱ":"wi","ᅲ":"yu","ᅳ":"eu","ᅴ":"ui","ᅵ":"i",
  "ᆨ":"k","ᆩ":"k","ᆪ":"ks","ᆫ":"n","ᆬ":"nj","ᆭ":"nh","ᆮ":"t","ᆯ":"l","ᆰ":"lk",
  "ᆱ":"lm","ᆲ":"lb","ᆳ":"ls","ᆴ":"lt","ᆵ":"lp","ᆶ":"lh","ᆷ":"m","ᆸ":"p","ᆹ":"ps",
  "ᆺ":"t","ᆻ":"t","ᆼ":"ng","ᆽ":"t","ᆾ":"t","ᆿ":"k","ᇀ":"t","ᇁ":"p","ᇂ":"h",
  "ㄱ":"g","ㄲ":"kk","ㄴ":"n","ㄷ":"d","ㄸ":"tt","ㄹ":"r","ㅁ":"m","ㅂ":"b","ㅃ":"pp",
  "ㅅ":"s","ㅆ":"ss","ㅇ":"ng","ㅈ":"j","ㅉ":"jj","ㅊ":"ch","ㅋ":"k","ㅌ":"t","ㅍ":"p","ㅎ":"h",
  "ㅏ":"a","ㅐ":"ae","ㅑ":"ya","ㅒ":"yae","ㅓ":"eo","ㅔ":"e","ㅕ":"yeo","ㅖ":"ye","ㅗ":"o",
  "ㅘ":"wa","ㅙ":"wae","ㅚ":"oe","ㅛ":"yo","ㅜ":"u","ㅝ":"wo","ㅞ":"we","ㅟ":"wi","ㅠ":"yu",
  "ㅡ":"eu","ㅢ":"ui","ㅣ":"i",
};

/* Abugidas: Devanagari, Bengali, Gurmukhi, Tamil */

const DEVANAGARI_CONSONANTS = {
  "क":"k","ख":"kh","ग":"g","घ":"gh","ङ":"ṅ","च":"c","छ":"ch","ज":"j","झ":"jh","ञ":"ñ",
  "ट":"ṭ","ठ":"ṭh","ड":"ḍ","ढ":"ḍh","ण":"ṇ","त":"t","थ":"th","द":"d","ध":"dh","न":"n",
  "प":"p","फ":"ph","ब":"b","भ":"bh","म":"m","य":"y","र":"r","ल":"l","व":"v","श":"ś",
  "ष":"ṣ","स":"s","ह":"h","ळ":"ḷ","क़":"q","ख़":"x","ग़":"ġ","ज़":"z","ड़":"ṛ","ढ़":"ṛh",
  "फ़":"f","ऩ":"n","ऱ":"r","य़":"ẏ","ऴ":"ḻ",
};
const DEVANAGARI_NUKTA = {
  "क":"क़","ख":"ख़","ग":"ग़","ज":"ज़","ड":"ड़","ढ":"ढ़","फ":"फ़","य":"य़",
};
const DEVANAGARI_INDEPENDENT = {
  "अ":"a","आ":"ā","इ":"i","ई":"ī","उ":"u","ऊ":"ū","ऋ":"ṛ","ॠ":"ṝ","ऌ":"ḷ","ॡ":"ḹ",
  "ए":"e","ऐ":"ai","ओ":"o","औ":"au","ऑ":"ŏ","ऍ":"ĕ",
};
const DEVANAGARI_VOWEL_SIGNS = {
  "ा":"ā","ि":"i","ी":"ī","ु":"u","ू":"ū","ृ":"ṛ","ॄ":"ṝ","ॢ":"ḷ","ॣ":"ḹ","े":"e","ै":"ai","ो":"o","ौ":"au",
  "ॅ":"ĕ","ॉ":"ŏ",
};
const DEVANAGARI_MARKS = {
  "ं":"ṃ","ः":"ḥ","ँ":"̃","ऽ":"ʼ","॑":"´","॒":"`",
};

const BENGALI_CONSONANTS = {
  "ক":"k","খ":"kh","গ":"g","ঘ":"gh","ঙ":"ṅ","চ":"c","ছ":"ch","জ":"j","ঝ":"jh","ঞ":"ñ",
  "ট":"ṭ","ঠ":"ṭh","ড":"ḍ","ঢ":"ḍh","ণ":"ṇ","ত":"t","থ":"th","দ":"d","ধ":"dh","ন":"n",
  "প":"p","ফ":"ph/f","ব":"b","ভ":"bh","ম":"m","য":"y","র":"r","ল":"l","শ":"sh","ষ":"ṣ","স":"s","হ":"h",
  "ড়":"ṛ","ঢ়":"ṛh","য়":"ẏ","ৎ":"t","ড়়":"ṛ","ঢ়়":"ṛh",
};
const BENGALI_NUKTA = {
  "ড":"ড়","ঢ":"ঢ়","য":"য়",
};
const BENGALI_INDEPENDENT = {
  "অ":"ô","আ":"ā","ই":"i","ঈ":"ī","উ":"u","ঊ":"ū","ঋ":"ri","এ":"e","ঐ":"oi","ও":"o","ঔ":"ou",
};
const BENGALI_VOWEL_SIGNS = {
  "া":"ā","ি":"i","ী":"ī","ু":"u","ূ":"ū","ৃ":"ri","ে":"e","ৈ":"oi","ো":"o","ৌ":"ou",
};
const BENGALI_MARKS = {
  "ং":"ng","ঃ":"ḥ","ঁ":"̃",
};

const GURMUKHI_CONSONANTS = {
  "ਕ":"k","ਖ":"kh","ਗ":"g","ਘ":"k","ਙ":"ṅ","ਚ":"c","ਛ":"ch","ਜ":"j","ਝ":"c","ਞ":"ñ",
  "ਟ":"ṭ","ਠ":"ṭh","ਡ":"ḍ","ਢ":"ṭ","ਣ":"ṇ","ਤ":"t","ਥ":"th","ਦ":"d","ਧ":"t","ਨ":"n",
  "ਪ":"p","ਫ":"ph/f","ਬ":"b","ਭ":"p","ਮ":"m","ਯ":"y","ਰ":"r","ਲ":"l","ਵ":"v",
  "ਸ਼":"sh","ਸ":"s","ਹ":"h","ੜ":"ṛ","ਖ਼":"x","ਗ਼":"ġ","ਜ਼":"z","ਫ਼":"f","ਲ਼":"ḷ",
};
const GURMUKHI_NUKTA = {
  "ਸ":"ਸ਼","ਖ":"ਖ਼","ਗ":"ਗ਼","ਜ":"ਜ਼","ਫ":"ਫ਼","ਲ":"ਲ਼",
};
const GURMUKHI_TONE_CONSONANTS = {
  "ਘ":"\u0300","ਝ":"\u0300","ਢ":"\u0300","ਧ":"\u0300","ਭ":"\u0300",
};
const GURMUKHI_INDEPENDENT = {
  "ਅ":"a","ਆ":"ā","ਇ":"i","ਈ":"ī","ਉ":"u","ਊ":"ū","ਏ":"e","ਐ":"ai","ਓ":"o","ਔ":"au",
};
const GURMUKHI_VOWEL_SIGNS = {
  "ਾ":"ā","ਿ":"i","ੀ":"ī","ੁ":"u","ੂ":"ū","ੇ":"e","ੈ":"ai","ੋ":"o","ੌ":"au",
};
const GURMUKHI_MARKS = {
  "ਂ":"̃","ੰ":"̃","ਃ":"ḥ","ੱ":"","੍":"", "਼":"",
};

const TAMIL_CONSONANTS = {
  "க":"k","ங":"ṅ","ச":"c","ஞ":"ñ","ட":"ṭ","ண":"ṇ","த":"t","ந":"n","ப":"p","ம":"m",
  "ய":"y","ர":"r","ல":"l","வ":"v","ழ":"ḻ","ள":"ḷ","ற":"ṟ","ன":"ṉ","ஜ":"j","ஷ":"ṣ","ஸ":"s","ஹ":"h",
  "க்ஷ":"kṣ",
};
const TAMIL_INDEPENDENT = {
  "அ":"a","ஆ":"ā","இ":"i","ஈ":"ī","உ":"u","ஊ":"ū","எ":"e","ஏ":"ē","ஐ":"ai","ஒ":"o","ஓ":"ō","ஔ":"au",
};
const TAMIL_VOWEL_SIGNS = {
  "ா":"ā","ி":"i","ீ":"ī","ு":"u","ூ":"ū","ெ":"e","ே":"ē","ை":"ai","ொ":"o","ோ":"ō","ௌ":"au",
};
const TAMIL_MARKS = {
  "ஂ":"ṃ","ஃ":"ḥ",
};

/* Thai */

const THAI_CONSONANTS = {
  "ก":"k","ข":"kh","ฃ":"kh","ค":"kh","ฅ":"kh","ฆ":"kh","ง":"ng","จ":"ch","ฉ":"ch","ช":"ch",
  "ซ":"s","ฌ":"ch","ญ":"y","ฎ":"d","ฏ":"t","ฐ":"th","ฑ":"th","ฒ":"th","ณ":"n","ด":"d",
  "ต":"t","ถ":"th","ท":"th","ธ":"th","น":"n","บ":"b","ป":"p","ผ":"ph","ฝ":"f","พ":"ph",
  "ฟ":"f","ภ":"ph","ม":"m","ย":"y","ร":"r","ล":"l","ว":"w","ศ":"s","ษ":"s","ส":"s",
  "ห":"h","ฬ":"l","อ":"ʔ","ฮ":"h",
};
const THAI_CLASS = {
  "ก":"mid","จ":"mid","ฎ":"mid","ฏ":"mid","ด":"mid","ต":"mid","บ":"mid","ป":"mid","อ":"mid",
  "ข":"high","ฃ":"high","ฉ":"high","ฐ":"high","ถ":"high","ผ":"high","ฝ":"high","ศ":"high","ษ":"high","ส":"high","ห":"high",
  "ค":"low","ฅ":"low","ฆ":"low","ง":"low","ช":"low","ซ":"low","ฌ":"low","ญ":"low","ฑ":"low","ฒ":"low","ณ":"low","ท":"low","ธ":"low","น":"low","พ":"low","ฟ":"low","ภ":"low","ม":"low","ย":"low","ร":"low","ล":"low","ว":"low","ฬ":"low","ฮ":"low",
};
const THAI_SHORT_VOWEL_CHARS = new Set(["ะ","ั","ิ","ุ","ึ"]);
const THAI_LONG_VOWEL_CHARS = new Set(["า","ี","ู","ื","ๅ","ำ"]);
const THAI_FINALS = {
  "ก":"k","ข":"k","ค":"k","ฆ":"k","ง":"ng","จ":"t","ช":"t","ซ":"t","ฎ":"t","ฏ":"t","ฐ":"t",
  "ฑ":"t","ฒ":"t","ด":"t","ต":"t","ถ":"t","ท":"t","ธ":"t","น":"n","บ":"p","ป":"p","พ":"p","ฟ":"p","ภ":"p",
  "ม":"m","ย":"y","ร":"n","ล":"n","ว":"w","ญ":"n","ณ":"n","ฬ":"n","ส":"t","ศ":"t","ษ":"t","ห":"h",
};
const THAI_VOWELS = {
  "ะ":"a","ั":"a","า":"ā","ิ":"i","ี":"ī","ึ":"ue","ื":"uee","ุ":"u","ู":"ū","เ":"e","แ":"ae","โ":"o","ใ":"ai","ไ":"ai","ำ":"am","ๅ":"ā",
};
const THAI_PREFIX_VOWELS = {
  "เ":"e","แ":"ae","โ":"o","ใ":"ai","ไ":"ai",
};
const THAI_TONE_MARKS = { "่":"low","้":"falling","๊":"high","๋":"rising" };
const THAI_TONE_COMBINING_MARKS = { "low":"̀", "falling":"̂", "high":"́", "rising":"̌" };
const THAI_PART_MAP = {
  ...THAI_CONSONANTS,
  ...THAI_VOWELS,
  "็":"","่":"̀","้":"̂","๊":"́","๋":"̌","์":"","ํ":"n","ฺ":"","ๆ":"","ฯ":"",
};
const THAI_PART_DETAIL_MAP = {
  "็": { rawSound: "short", detail: "shortening mark" },
  "่": { rawSound: "low-tone", detail: "low tone" },
  "้": { rawSound: "falling-tone", detail: "falling tone" },
  "๊": { rawSound: "high-tone", detail: "high tone" },
  "๋": { rawSound: "rising-tone", detail: "rising tone" },
  "์": { rawSound: "karan", detail: "silent mark" },
  "ฺ": { rawSound: "killer", detail: "vowel killer" },
  "ๆ": { rawSound: "repeat", detail: "repetition mark" },
  "ฯ": { rawSound: "abbrev", detail: "abbreviation mark" },
};
const THAI_SPAN_MAP = {
  "อา":"ā",
  "อิ":"i","อี":"ī","อุ":"u","อู":"ū","เอ":"e","โอ":"o","ไอ":"ai",
  "ร์":"r","น์":"n","ต์":"t","ท์":"th","ก์":"k","ด์":"d","ม์":"m",
};

/* Latin family */

const LATIN_COMBINING_MARKS = {
  "\u0300":"", "\u0301":"", "\u0302":"", "\u0303":"", "\u0304":"", "\u0306":"",
  "\u0307":"", "\u0308":"", "\u0309":"", "\u030A":"", "\u030B":"", "\u030C":"",
  "\u031B":"", "\u0323":"", "\u0327":"", "\u0328":"", "\u0335":"", "\u0336":"",
};

const LATIN_GENERIC_BASE = {
  "a":"a","b":"b","c":"k","d":"d","e":"e","f":"f","g":"g","h":"h","i":"i","j":"j","k":"k","l":"l",
  "m":"m","n":"n","o":"o","p":"p","q":"k","r":"r","s":"s","t":"t","u":"u","v":"v","w":"w","x":"x","y":"y","z":"z",
  "æ":"ae","œ":"oe","þ":"th","ð":"dh","ȝ":"gh","ə":"ə","ß":"ss","ł":"w","ñ":"ny","ç":"s",
  "á":"a","à":"a","â":"a","ä":"a","ã":"a","å":"a","ā":"a","ă":"a","ą":"a",
  "é":"e","è":"e","ê":"e","ë":"e","ē":"e","ĕ":"e","ė":"e","ę":"e",
  "í":"i","ì":"i","î":"i","ï":"i","ī":"i","į":"i","ı":"i",
  "ó":"o","ò":"o","ô":"o","ö":"o","õ":"o","ō":"o","ő":"o","ø":"o",
  "ú":"u","ù":"u","û":"u","ü":"u","ū":"u","ů":"u","ű":"u","ư":"u",
  "ý":"y","ÿ":"y","č":"ch","š":"sh","ž":"zh","ğ":"gh","đ":"d","ł":"w","ř":"rzh","ť":"ty","ď":"dy","ň":"ny",
};

const VIETNAMESE_CODEPOINTS = {
  "ă":"ă","â":"â","đ":"đ","ê":"ê","ô":"ô","ơ":"ơ","ư":"ư",
  "Ă":"ă","Â":"â","Đ":"đ","Ê":"ê","Ô":"ô","Ơ":"ơ","Ư":"ư",
};

function composeVietnamese(raw, parts) {
  if (VIETNAMESE_SPAN[raw] != null) return VIETNAMESE_SPAN[raw];
  if (VIETNAMESE_CODEPOINTS[raw] != null) return VIETNAMESE_CODEPOINTS[raw];

  const base = stripCombining(raw);
  const hasBreve = parts.includes("\u0306");
  const hasCirc = parts.includes("\u0302");
  const hasHorn = parts.includes("\u031B");
  if (base === "a" && hasBreve) return "ă";
  if (base === "a" && hasCirc) return "â";
  if (base === "e" && hasCirc) return "ê";
  if (base === "o" && hasCirc) return "ô";
  if (base === "o" && hasHorn) return "ơ";
  if (base === "u" && hasHorn) return "ư";
  if (base === "d" && parts.some((x) => x === "\u0335" || x === "\u0336")) return "đ";
  return null;
}

const VIETNAMESE_SPAN = {
  "ch":"ch","gh":"g","gi":"zi/ji","kh":"kh","ng":"ng","ngh":"ng","nh":"ny","ph":"f","qu":"kw","th":"th","tr":"tr","đ":"d",
};

function composeTurkish(raw) {
  return TURKISH_SPAN[raw] ?? null;
}
const TURKISH_SPAN = {
  "ç":"ch","ğ":"ğ","ı":"ı","i":"i","ö":"ö","ş":"sh","ü":"ü",
};

const INDONESIAN_SPAN = {
  "ng":"ng","ny":"ny","sy":"sh","kh":"kh","ai":"ai","au":"au","oi":"oi",
};

const TAGALOG_SPAN = {
  "ng":"ng","mga":"mga","ts":"ts","dy":"dy","sy":"sh",
};

const SWAHILI_SPAN = {
  "ch":"ch","dh":"dh","gh":"gh","kh":"kh","ng":"ng","ng'":"ng","ny":"ny","sh":"sh","th":"th",
};

const LATIN_SPAN = {
  "ae":"ae","oe":"oe","au":"au","eu":"eu","qu":"kw",
};

const FRENCH_SPAN = {
  "eau":"o","au":"o","ai":"e","ei":"e","oi":"wa","ou":"u","ch":"sh","gn":"ny","ph":"f",
  "an":"ã","am":"ã","en":"ã","em":"ã","in":"ɛ̃","im":"ɛ̃","ain":"ɛ̃","ein":"ɛ̃","on":"õ","om":"õ","un":"œ̃","um":"œ̃",
  "ill":"iy","œ":"oe","ç":"s",
};

const ITALIAN_SPAN = {
  "ch":"k","gh":"g","ci":"chi","ce":"che","gi":"ji","ge":"je","gli":"lyi","gn":"ny","sc":"sk/sh","sce":"she","sci":"shi","qu":"kw",
};

const SPANISH_SPAN = {
  "ch":"ch","ll":"y","rr":"rr","qu":"k","gue":"ge","gui":"gi","güe":"gwe","güi":"gwi",
  "ce":"se","ci":"si","ge":"xe","gi":"xi","ñ":"ny",
};

const GERMAN_SPAN = {
  "sch":"sh","tsch":"ch","ch":"kh/ç","ei":"ai","ie":"i","eu":"oi","äu":"oi","sp":"shp","st":"sht","z":"ts","ß":"ss",
};

const DUTCH_SPAN = {
  "ij":"ei","oe":"u","eu":"ø","ui":"œy","ou":"au","au":"au","sch":"sx","ch":"x",
};

const PORTUGUESE_SPAN = {
  "nh":"ny","lh":"ly","ch":"sh","ss":"s","rr":"h/r","qu":"k","gu":"g","ão":"ãw","ãe":"ãi","õe":"õi",
  "am":"ã","an":"ã","em":"ẽ","en":"ẽ","im":"ĩ","in":"ĩ","om":"õ","on":"õ","um":"ũ","un":"ũ","ç":"s",
};

const OLD_ENGLISH_SPAN = {
  "sc":"sh","cg":"j","hw":"hw","hl":"hl","hn":"hn","hr":"hr","ng":"ng","ea":"æɑ","eo":"eo","ie":"ie",
};

/* -------------------------------------------------------------------------- */
/* Language aliases and profiles                                               */
/* -------------------------------------------------------------------------- */


/* -------------------------------------------------------------------------- */
/* Coverage extensions and no-gap fallbacks                                    */
/* -------------------------------------------------------------------------- */

Object.assign(ARABIC_BASE_LETTERS, {
  "ٮ":"b","ٹ":"ṭ","ٺ":"t","ٻ":"b","ټ":"t","ٽ":"ṭ","ٿ":"th","ڀ":"bh","ځ":"dz","ڃ":"ny","ڄ":"j","چ":"ch","ڇ":"chh",
  "ڈ":"ḍ","ډ":"d","ڊ":"ḍ","ڌ":"dh","ڍ":"ḍh","ڎ":"d","ڑ":"ṛ","ڒ":"r","ړ":"ṛ","ڔ":"r","ڕ":"r","ږ":"zh",
  "ڗ":"zh","ژ":"zh","ڙ":"ṛ","ښ":"sh","ڛ":"s","ڜ":"sh","ڝ":"ṣ","ڞ":"ḍ","ڟ":"ṭ","ڠ":"ng","ڡ":"f","ڢ":"f","ڣ":"f",
  "ڤ":"v","ڥ":"v","ڦ":"ph","ڧ":"q","ڨ":"q","ک":"k","ڪ":"k","ګ":"g","ڬ":"g","ڭ":"ng","ڮ":"g","گ":"g","ڰ":"g",
  "ڱ":"ng","ڲ":"g","ڳ":"gh","ڴ":"g","ڵ":"l","ڶ":"l","ڷ":"l","ڸ":"l","ڹ":"n","ں":"ñ","ڻ":"ṇ","ڼ":"n","ڽ":"ny","ھ":"h",
  "ڿ":"ch","ۀ":"e","ہ":"h","ۂ":"e","ۃ":"t","ێ":"ê","ې":"e","ۑ":"e","ے":"e","ۓ":"e","ە":"e","ہ":"h","ہٕ":"eh","ی":"y","ۍ":"y","ێ":"ê",
  "ۏ":"o","ې":"e","ۯ":"r","ݐ":"t","ݑ":"t","ݒ":"ph","ݓ":"v","ݔ":"g","ݕ":"gw","ݖ":"ng","ݗ":"q","ݘ":"ng","ݙ":"d","ݚ":"d","ݛ":"r","ݜ":"sh",
  "ݝ":"s","ݞ":"d","ݟ":"ṭ","ݠ":"gh","ݡ":"f","ݢ":"g","ݣ":"g","ݤ":"v","ݥ":"n","ݦ":"r","ݧ":"l","ݨ":"ny","ݩ":"k","ݪ":"k","ݫ":"k","ݬ":"g",
  "ݭ":"ng","ݮ":"ny","ݯ":"d","ݰ":"d","ݱ":"j","ݲ":"z","ݳ":"s","ݴ":"sh","ݵ":"f","ݶ":"b","ݷ":"q","ݸ":"q","ݹ":"k","ݺ":"n","ݻ":"r","ݼ":"ch",
  "ݽ":"tt","ݾ":"bh","ݿ":"dh"
});

Object.assign(ARABIC_MARKS, {
  "ؐ":"","ؑ":"","ؒ":"","ؓ":"","ؔ":"","ؕ":"","ؖ":"","ؗ":"","ؘ":"","ؙ":"","ؚ":"","ۖ":"","ۗ":"","ۘ":"","ۙ":"","ۚ":"","ۛ":"",
  "ۜ":"","۟":"","۠":"","ۡ":"","ۢ":"","ۣ":"","ۤ":"","ۧ":"","ۨ":"","۪":"","۫":"","۬":"","ۭ":"","ࣰ":"","ࣱ":"","ࣲ":"","ࣳ":"",
  "ࣴ":"","ࣵ":"","ࣶ":"","ࣷ":"","ࣸ":"","ࣹ":"","ࣺ":"","ࣻ":"","ࣼ":"","ࣽ":"","ࣾ":"","ࣿ":"","ـ":"","ٓ":"ā","ٖ":"i","ٗ":"u","٘":"i","ٙ":"a","ٚ":""
});

Object.assign(HEBREW_MARKS, {
  "\u0591":"","\u0592":"","\u0593":"","\u0594":"","\u0595":"","\u0596":"","\u0597":"","\u0598":"","\u0599":"","\u059A":"",
  "\u059B":"","\u059C":"","\u059D":"","\u059E":"","\u059F":"","\u05A0":"","\u05A1":"","\u05A2":"","\u05A3":"","\u05A4":"",
  "\u05A5":"","\u05A6":"","\u05A7":"","\u05A8":"","\u05A9":"","\u05AA":"","\u05AB":"","\u05AC":"","\u05AD":"","\u05AE":"",
  "\u05AF":"","\u05BD":"","\u05BF":"","\u05C1":"","\u05C2":"","\u05C4":"","\u05C5":"","\u05C7":"a"
});

Object.assign(GREEK_MODERN, {
  "ϊ":"i","ΐ":"i","ϋ":"i","ΰ":"i","ά":"a","έ":"e","ή":"i","ί":"i","ό":"o","ύ":"i","ώ":"o",
  "ϐ":"v","ϑ":"th","ϒ":"i","ϓ":"y","ϔ":"y","ϕ":"f","ϖ":"p","ϗ":"kai","ϛ":"st","Ϝ":"w","ϝ":"w","ϟ":"q","ϡ":"sampi"
});
Object.assign(GREEK_ANCIENT, {
  "ϊ":"i","ΐ":"i","ϋ":"y","ΰ":"y","ά":"a","έ":"e","ή":"ē","ί":"i","ό":"o","ύ":"y","ώ":"ō",
  "ϐ":"b","ϑ":"th","ϕ":"ph","ϖ":"p","ϛ":"st","Ϝ":"w","ϝ":"w","ϟ":"q","ϡ":"s"
});

Object.assign(CYRILLIC_RUSSIAN, {
  "ѐ":"e","ѓ":"g","є":"e","ѕ":"dz","і":"i","ї":"yi","ј":"j","љ":"ly","њ":"ny","ћ":"ć","ќ":"ḱ","ѝ":"i","ў":"u","џ":"dzh",
  "А":"a","Б":"b","В":"v","Г":"g","Д":"d","Е":"e/ye","Ё":"yo","Ж":"zh","З":"z","И":"i","Й":"y","К":"k","Л":"l","М":"m","Н":"n","О":"o",
  "П":"p","Р":"r","С":"s","Т":"t","У":"u","Ф":"f","Х":"kh","Ц":"ts","Ч":"ch","Ш":"sh","Щ":"shch","Ъ":"ʺ","Ы":"y","Ь":"ʹ","Э":"e","Ю":"yu","Я":"ya"
});

Object.assign(ARMENIAN, {
  "Ա":"a","Բ":"b","Գ":"g","Դ":"d","Ե":"e","Զ":"z","Է":"ē","Ը":"ə","Թ":"tʿ","Ժ":"zh","Ի":"i","Լ":"l","Խ":"kh","Ծ":"ts","Կ":"k","Հ":"h",
  "Ձ":"dz","Ղ":"gh","Ճ":"č","Մ":"m","Յ":"y","Ն":"n","Շ":"sh","Ո":"o/vo","Չ":"chʿ","Պ":"p","Ջ":"j","Ռ":"ṙ","Ս":"s","Վ":"v","Տ":"t",
  "Ր":"r","Ց":"cʿ","Ւ":"w","Փ":"pʿ","Ք":"kʿ","Օ":"ō","Ֆ":"f","և":"ev","ֈ":"ew"
});

Object.assign(JAPANESE_BASE_MAP, {
  "ゕ":"ka","ゖ":"ke","ゝ":"","ゞ":"","ゟ":"yori",
  "ヵ":"ka","ヶ":"ke","ヽ":"","ヾ":"","ヷ":"va","ヸ":"vi","ヹ":"ve","ヺ":"vo",
  "ㇰ":"k","ㇱ":"sh","ㇲ":"s","ㇳ":"t","ㇴ":"n","ㇵ":"h","ㇶ":"hi","ㇷ":"f","ㇸ":"he","ㇹ":"ho","ㇺ":"m","ㇻ":"ra","ㇼ":"ri","ㇽ":"ru","ㇾ":"re","ㇿ":"ro",
  "ㇷ゚":"p","ヰ":"wi","ヱ":"we","ゔぁ":"va","ゔぃ":"vi","ゔぇ":"ve","ゔぉ":"vo","ゔゅ":"vyu"
});

const JAPANESE_SMALL_Y = { "ゃ":"ya","ゅ":"yu","ょ":"yo","ャ":"ya","ュ":"yu","ョ":"yo" };
const JAPANESE_SMALL_VOWEL = { "ぁ":"a","ぃ":"i","ぅ":"u","ぇ":"e","ぉ":"o","ァ":"a","ィ":"i","ゥ":"u","ェ":"e","ォ":"o","ゎ":"wa","ヮ":"wa" };
const JAPANESE_YOON_STEMS = {
  "shi":"sh","chi":"ch","ji":"j","di":"dy","ti":"ty","ni":"ny","hi":"hy","bi":"by","pi":"py","mi":"my","ri":"ry","ki":"ky","gi":"gy","i":"y","fu":"fy","vu":"vy"
};
const JAPANESE_FOREIGN_STEMS = {
  "shi":"sh","chi":"ch","ji":"j","di":"d","ti":"t","fu":"f","vu":"v","u":"w","tsu":"ts","tu":"t","du":"d"
};

Object.assign(JAPANESE_SPAN_MAP, {
  "いぇ":"ye","うぁ":"wa","うぃ":"wi","うぇ":"we","うぉ":"wo","ゔぁ":"va","ゔぃ":"vi","ゔぇ":"ve","ゔぉ":"vo","ゔゅ":"vyu",
  "イェ":"ye","ウァ":"wa","ウィ":"wi","ウェ":"we","ウォ":"wo","ヴァ":"va","ヴィ":"vi","ヴェ":"ve","ヴォ":"vo","ヴュ":"vyu",
  "スィ":"si","ズィ":"zi","テュ":"tyu","デュ":"dyu","フュ":"fyu","クァ":"kwa","クィ":"kwi","クェ":"kwe","クォ":"kwo","グァ":"gwa","グィ":"gwi","グェ":"gwe","グォ":"gwo",
  "しぇ":"she","ちぇ":"che","じぇ":"je","ふぁ":"fa","ふぃ":"fi","ふぇ":"fe","ふぉ":"fo","てぃ":"ti","でぃ":"di","とぅ":"tu","どぅ":"du","つぁ":"tsa","つぃ":"tsi","つぇ":"tse","つぉ":"tso"
});

Object.assign(HANGUL_JAMO_MAP, {
  "ᅶ":"yo-ya","ᅷ":"yo-yae","ᅸ":"yo-i","ᅹ":"yu-yeo","ᅺ":"yu-e","ᅻ":"yu-i","ᅼ":"eu-u","ᅽ":"eu-eu","ᆪ":"ks","ᆬ":"nj","ᆭ":"nh","ᆰ":"lk","ᆱ":"lm","ᆲ":"lb","ᆳ":"ls","ᆴ":"lt","ᆵ":"lp","ᆶ":"lh","ᆹ":"ps"
});

Object.assign(DEVANAGARI_INDEPENDENT, { "ॲ":"æ","ऎ":"e","ऒ":"o","ॳ":"ḷ","ॴ":"ḹ","ॵ":"a","ॶ":"u","ॷ":"u","ॸ":"um","ॹ":"z" });
Object.assign(DEVANAGARI_VOWEL_SIGNS, { "ॆ":"e","ॊ":"o","ॏ":"aw","ॖ":"ue","ॗ":"uue","ꣻ":"ue","꣼":"uue" });
Object.assign(DEVANAGARI_MARKS, { "ऀ":"n","ॎ":"prishthamatra-e","ॕ":"e","ॱ":"","ꣳ":"ṃ","ꣴ":"ḥ","꣸":"","꣹":"","꣺":"" });

Object.assign(BENGALI_CONSONANTS, { "ৰ":"r","ৱ":"w","঱":"r","঴":"ḷ","৺":"ru", "৘":"e","৙":"e" });
Object.assign(BENGALI_INDEPENDENT, { "ঌ":"ḷ","ৡ":"ḹ","ৠ":"ṝ","৲":"r","৳":"t","৴":"coin" });
Object.assign(BENGALI_VOWEL_SIGNS, { "ৢ":"ḷ","ৣ":"ḹ","ৗ":"au" });
Object.assign(BENGALI_MARKS, { "়":"","্":"","ঽ":"ʼ" });

Object.assign(GURMUKHI_CONSONANTS, { "ੲ":"ʔ","ੳ":"u/o","ੵ":"f","੶":"halant-y","੷":"uḍāt","੸":"uḍāt","੹":"i","੺":"ਖ","੻":"ਗ","੼":"ਜ","੽":"ਫ","੾":"ਯ" });
Object.assign(GURMUKHI_INDEPENDENT, { "ੴ":"ik-oankar" });
Object.assign(GURMUKHI_MARKS, { "ਁ":"̃","ਃ":"ḥ","਼":"","੍":"", "ੑ":"udat","੒":"udat","ੵ":"f" });

Object.assign(TAMIL_CONSONANTS, { "ஶ":"ś","ஜ":"j","ஷ":"ṣ","ஸ":"s","ஹ":"h","க்ஷ":"kṣ","ஶ்ரீ":"śrī","ஐ":"ai" });
Object.assign(TAMIL_INDEPENDENT, { "ஐ":"ai","ஔ":"au" });
Object.assign(TAMIL_MARKS, { "்":"", "ஂ":"ṃ","ஃ":"ḥ","ௗ":"au" });

Object.assign(THAI_CONSONANTS, { "ฤ":"rue","ฦ":"lue" });
Object.assign(THAI_FINALS, { "ฤ":"t","ฦ":"t","อ":"", "ฮ":"h" });
Object.assign(THAI_VOWELS, { "ั":"a","ๅ":"ā","ํา":"am","๎":"","ัว":"ua" });
Object.assign(THAI_PART_MAP, {
  "฿":"baht","๏":"","๚":"","๛":"","๐":"0","๑":"1","๒":"2","๓":"3","๔":"4","๕":"5","๖":"6","๗":"7","๘":"8","๙":"9",
  "ฤ":"rue","ฦ":"lue","ๅ":"ā","ํ":"n"
});
Object.assign(THAI_PART_DETAIL_MAP, {
  "๏": { rawSound: "bullet", detail: "section marker" },
  "๚": { rawSound: "end", detail: "end mark" },
  "๛": { rawSound: "end", detail: "end mark" }
});

Object.assign(LATIN_GENERIC_BASE, {
  "ă":"a","ắ":"a","ằ":"a","ẳ":"a","ẵ":"a","ặ":"a","ấ":"a","ầ":"a","ẩ":"a","ẫ":"a","ậ":"a","ắ":"a","ầ":"a","ẵ":"a",
  "ế":"e","ề":"e","ể":"e","ễ":"e","ệ":"e","ố":"o","ồ":"o","ổ":"o","ỗ":"o","ộ":"o","ớ":"o","ờ":"o","ở":"o","ỡ":"o","ợ":"o",
  "ứ":"u","ừ":"u","ử":"u","ữ":"u","ự":"u","ỳ":"y","ỵ":"y","ỷ":"y","ỹ":"y","ạ":"a","ả":"a","ã":"a","ạ":"a","ẹ":"e","ẻ":"e","ẽ":"e","ẹ":"e",
  "ị":"i","ỉ":"i","ĩ":"i","ọ":"o","ỏ":"o","õ":"o","ụ":"u","ủ":"u","ũ":"u","ơ":"o","ư":"u","ă":"a","â":"a","ê":"e","ô":"o","đ":"d"
});

Object.assign(VIETNAMESE_SPAN, {
  "gh":"g","ng":"ng","ngh":"ng","nh":"nh","th":"th","tr":"tr","ph":"f","kh":"kh","gi":"z","qu":"kw","uy":"uy","ươ":"ươ","ưa":"ưa","iê":"iê","yê":"yê"
});

Object.assign(TURKISH_SPAN, {
  "ch":"ç","sh":"ş","ğ":"ğ","ı":"ı","ö":"ö","ü":"ü"
});
Object.assign(INDONESIAN_SPAN, { "dj":"j","tj":"c","sj":"sy","nj":"ny","oe":"u" });
Object.assign(TAGALOG_SPAN, { "ng":"ng","mga":"mga","sy":"sy","dy":"dy","ly":"ly","ry":"ry" });
Object.assign(SWAHILI_SPAN, { "kw":"kw","mw":"mw","nd":"nd","ng":"ng","ny":"ny","sh":"sh","th":"th","dh":"dh","gh":"gh","kh":"kh" });
Object.assign(FRENCH_SPAN, { "eux":"ø","eux ":"ø","ill":"iy","oin":"wɛ̃","ien":"yɛ̃","ienn":"yɛn","eu":"ø/œ","œu":"ø/œ","ui":"ɥi","gn":"ny","qu":"k" });
Object.assign(ITALIAN_SPAN, { "gli":"ʎi","gn":"ɲ","sci":"shi","sce":"she","ci":"chi","ce":"che","gi":"ji","ge":"je","zz":"tts/ddz" });
Object.assign(SPANISH_SPAN, { "ll":"y","rr":"rr","qu":"k","gue":"ge","gui":"gi","güe":"gwe","güi":"gwi","ch":"ch","ñ":"ny","ce":"se","ci":"si","ge":"xe","gi":"xi" });
Object.assign(GERMAN_SPAN, { "sch":"sh","tsch":"ch","sp":"shp","st":"sht","ch":"kh/ç","ei":"ai","ie":"i","eu":"oi","äu":"oi","z":"ts" });
Object.assign(DUTCH_SPAN, { "ij":"ei","oe":"u","eu":"ø","ui":"œy","ou":"au","au":"au","sch":"sx","ch":"x" });
Object.assign(PORTUGUESE_SPAN, { "nh":"ny","lh":"ly","ch":"sh","ss":"s","rr":"h/r","qu":"k","gu":"g","ção":"sãw","ções":"sõys","ão":"ãw","ãe":"ãi","õe":"õi" });
Object.assign(OLD_ENGLISH_SPAN, { "sc":"sh","cg":"j","hw":"hw","hl":"hl","hn":"hn","hr":"hr","ng":"ng","ea":"æɑ","eo":"eo","ie":"ie","þ":"th","ð":"dh","æ":"ae" });

const LANGUAGE_ALIASES = {
  "ar":"arabic",
  "arabic":"arabic",
  "fa":"persian",
  "persian":"persian",
  "farsi":"persian",
  "ur":"urdu",
  "urdu":"urdu",
  "hi":"hindi",
  "hindi":"hindi",
  "id":"indonesian",
  "indonesian":"indonesian",
  "bahasa indonesia":"indonesian",
  "ta":"tamil",
  "tamil":"tamil",
  "th":"thai",
  "thai":"thai",
  "tr":"turkish",
  "turkish":"turkish",
  "ang":"old-english",
  "old english":"old-english",
  "grc":"ancient-greek",
  "ancient greek":"ancient-greek",
  "classical greek":"ancient-greek",
  "he":"hebrew",
  "hebrew":"hebrew",
  "fr":"french",
  "french":"french",
  "it":"italian",
  "italian":"italian",
  "ru":"russian",
  "russian":"russian",
  "es":"spanish",
  "spanish":"spanish",
  "de":"german",
  "german":"german",
  "nl":"dutch",
  "dutch":"dutch",
  "pt":"portuguese",
  "portuguese":"portuguese",
  "la":"latin",
  "latin":"latin",
  "el":"greek",
  "greek":"greek",
  "modern greek":"greek",
  "hy":"armenian",
  "armenian":"armenian",
  "tl":"tagalog",
  "tagalog":"tagalog",
  "sw":"swahili",
  "swahili":"swahili",
  "bn":"bengali",
  "bengali":"bengali",
  "pa":"punjabi",
  "punjabi":"punjabi",
  "gurmukhi":"punjabi",
  "ja":"japanese",
  "japanese":"japanese",
  "ko":"korean",
  "korean":"korean",
  "vi":"vietnamese",
  "vietnamese":"vietnamese",
  "zh":"han",
  "zh-hant":"han",
  "lzh":"han",
  "chinese (simplified)":"han",
  "chinese simplified":"han",
  "chinese (traditional)":"han",
  "chinese traditional":"han",
  "traditional-chinese":"han",
  "classical":"han",
  "classical chinese":"han",
  "classical-chinese":"han",
};

const PHONOLOGY_PROFILES = {
  "arabic": {
    id: "arabic",
    script: "Arabic",
    scriptFamily: "arabic",
    baseLetters: ARABIC_BASE_LETTERS,
    codepointMap: { ...ARABIC_BASE_LETTERS, ...ARABIC_MARKS },
    spanMap: { "ال":"al", "لل":"lil", "لا":"lā", "ﻻ":"lā" },
    analyze: (unit, parts) => analyzeArabicScript(PHONOLOGY_PROFILES["arabic"], unit, parts),
  },
  "persian": {
    id: "persian",
    script: "Arabic",
    scriptFamily: "arabic",
    baseLetters: { ...ARABIC_BASE_LETTERS, ...PERSIAN_BASE_OVERRIDES },
    codepointMap: { ...ARABIC_BASE_LETTERS, ...ARABIC_MARKS, ...PERSIAN_BASE_OVERRIDES },
    spanMap: { "لا":"lā" },
    analyze: (unit, parts) => analyzeArabicScript(PHONOLOGY_PROFILES["persian"], unit, parts),
  },
  "urdu": {
    id: "urdu",
    script: "Arabic",
    scriptFamily: "arabic",
    baseLetters: { ...ARABIC_BASE_LETTERS, ...URDU_BASE_OVERRIDES },
    codepointMap: { ...ARABIC_BASE_LETTERS, ...ARABIC_MARKS, ...URDU_BASE_OVERRIDES },
    spanMap: { "لا":"lā" },
    analyze: (unit, parts) => analyzeArabicScript(PHONOLOGY_PROFILES["urdu"], unit, parts),
  },
  "hebrew": {
    id: "hebrew",
    script: "Hebrew",
    scriptFamily: "hebrew",
    codepointMap: { ...HEBREW_LETTERS, ...HEBREW_MARKS },
    spanMap: { "וו":"v","יי":"yy","וֹ":"o","וּ":"u" },
    analyze: (unit, parts, opts) => analyzeHebrew(PHONOLOGY_PROFILES["hebrew"], unit, parts, opts),
  },
  "greek": {
    id: "greek",
    script: "Greek",
    scriptFamily: "greek",
    caseInsensitive: true,
    codepointMap: GREEK_MODERN,
    spanMap: GREEK_MODERN_SPAN,
    analyze: (unit, parts) => analyzeGreek(PHONOLOGY_PROFILES["greek"], unit, parts),
  },
  "ancient-greek": {
    id: "ancient-greek",
    script: "Greek",
    scriptFamily: "greek",
    caseInsensitive: true,
    codepointMap: GREEK_ANCIENT,
    spanMap: GREEK_ANCIENT_SPAN,
    analyze: (unit, parts) => analyzeGreek(PHONOLOGY_PROFILES["ancient-greek"], unit, parts),
  },
  "russian": {
    id: "russian",
    script: "Cyrillic",
    scriptFamily: "simple",
    caseInsensitive: true,
    codepointMap: CYRILLIC_RUSSIAN,
    analyze: (unit, parts, options) => analyzeBySimpleMap(PHONOLOGY_PROFILES["russian"], unit.toLowerCase(), parts, options),
  },
  "armenian": {
    id: "armenian",
    script: "Armenian",
    scriptFamily: "simple",
    caseInsensitive: true,
    codepointMap: ARMENIAN,
    spanMap: { "ու":"u","եւ":"ev","և":"ev" },
    analyze: (unit, parts, options) => analyzeBySimpleMap(PHONOLOGY_PROFILES["armenian"], unit.toLowerCase(), parts, options),
  },
  "japanese": {
    id: "japanese",
    script: "Kana/Kanji",
    scriptFamily: "japanese",
    decomposeCluster: (unit) => Array.from(unit.normalize("NFD")),
    analyze: (unit, parts) => analyzeJapanese(PHONOLOGY_PROFILES["japanese"], unit, parts),
  },
  "korean": {
    id: "korean",
    script: "Hangul",
    scriptFamily: "hangul",
    decomposeCluster: (unit) => decomposeHangulString(unit).map((x) => x.char),
    analyze: (unit) => analyzeHangul(PHONOLOGY_PROFILES["korean"], unit),
  },
  "hindi": {
    id: "hindi",
    script: "Devanagari",
    scriptFamily: "abugida",
    consonants: DEVANAGARI_CONSONANTS,
    nuktaMap: DEVANAGARI_NUKTA,
    independentVowels: DEVANAGARI_INDEPENDENT,
    vowelSigns: DEVANAGARI_VOWEL_SIGNS,
    marks: DEVANAGARI_MARKS,
    virama: "्",
    inherentVowel: "a",
    codepointMap: { ...DEVANAGARI_CONSONANTS, ...DEVANAGARI_INDEPENDENT, ...DEVANAGARI_VOWEL_SIGNS, ...DEVANAGARI_MARKS, "्":"", "़":"" },
    analyze: (unit, parts) => analyzeAbugida(PHONOLOGY_PROFILES["hindi"], unit, parts),
  },
  "bengali": {
    id: "bengali",
    script: "Bengali",
    scriptFamily: "abugida",
    consonants: BENGALI_CONSONANTS,
    nuktaMap: BENGALI_NUKTA,
    independentVowels: BENGALI_INDEPENDENT,
    vowelSigns: BENGALI_VOWEL_SIGNS,
    marks: BENGALI_MARKS,
    virama: "্",
    inherentVowel: "ô",
    codepointMap: { ...BENGALI_CONSONANTS, ...BENGALI_INDEPENDENT, ...BENGALI_VOWEL_SIGNS, ...BENGALI_MARKS, "্":"", "়":"" },
    analyze: (unit, parts) => analyzeAbugida(PHONOLOGY_PROFILES["bengali"], unit, parts),
  },
  "punjabi": {
    id: "punjabi",
    script: "Gurmukhi",
    scriptFamily: "abugida",
    consonants: GURMUKHI_CONSONANTS,
    toneConsonants: GURMUKHI_TONE_CONSONANTS,
    geminationMark: "ੱ",
    nuktaMap: GURMUKHI_NUKTA,
    independentVowels: GURMUKHI_INDEPENDENT,
    vowelSigns: GURMUKHI_VOWEL_SIGNS,
    marks: GURMUKHI_MARKS,
    virama: "੍",
    inherentVowel: "a",
    codepointMap: { ...GURMUKHI_CONSONANTS, ...GURMUKHI_INDEPENDENT, ...GURMUKHI_VOWEL_SIGNS, ...GURMUKHI_MARKS, "੍":"", "਼":"" },
    analyze: (unit, parts) => analyzeAbugida(PHONOLOGY_PROFILES["punjabi"], unit, parts),
  },
  "tamil": {
    id: "tamil",
    script: "Tamil",
    scriptFamily: "abugida",
    consonants: TAMIL_CONSONANTS,
    nuktaMap: {},
    independentVowels: TAMIL_INDEPENDENT,
    vowelSigns: TAMIL_VOWEL_SIGNS,
    marks: TAMIL_MARKS,
    virama: "்",
    inherentVowel: "a",
    codepointMap: { ...TAMIL_CONSONANTS, ...TAMIL_INDEPENDENT, ...TAMIL_VOWEL_SIGNS, ...TAMIL_MARKS, "்":"" },
    analyze: (unit, parts) => analyzeAbugida(PHONOLOGY_PROFILES["tamil"], unit, parts),
  },
  "thai": {
    id: "thai",
    script: "Thai",
    scriptFamily: "thai",
    codepointMap: THAI_PART_MAP,
    analyze: (unit, parts) => analyzeThai(PHONOLOGY_PROFILES["thai"], unit, parts),
  },
  "vietnamese": {
    id: "vietnamese",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: { ...LATIN_GENERIC_BASE, "đ":"d" },
    codepointMap: { ...LATIN_GENERIC_BASE, ...VIETNAMESE_CODEPOINTS },
    spanMap: VIETNAMESE_SPAN,
    composeLatin: composeVietnamese,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["vietnamese"], unit, parts),
  },
  "turkish": {
    id: "turkish",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: { ...LATIN_GENERIC_BASE, "c":"j","ç":"ch","ğ":"ğ","ı":"ɯ","i":"i","j":"zh","ö":"ø","ş":"sh","ü":"y" },
    codepointMap: { ...LATIN_GENERIC_BASE, "ç":"ch","ğ":"ğ","ı":"ɯ","ö":"ø","ş":"sh","ü":"y" },
    spanMap: TURKISH_SPAN,
    composeLatin: composeTurkish,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["turkish"], unit, parts),
  },
  "indonesian": {
    id: "indonesian",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: { ...LATIN_GENERIC_BASE, "c":"ch","e":"ə/e","j":"j","y":"y" },
    codepointMap: { ...LATIN_GENERIC_BASE },
    spanMap: INDONESIAN_SPAN,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["indonesian"], unit, parts),
  },
  "tagalog": {
    id: "tagalog",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: { ...LATIN_GENERIC_BASE, "c":"k","f":"p","j":"h","q":"k","v":"b","x":"ks","z":"s" },
    codepointMap: { ...LATIN_GENERIC_BASE },
    spanMap: TAGALOG_SPAN,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["tagalog"], unit, parts),
  },
  "swahili": {
    id: "swahili",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: { ...LATIN_GENERIC_BASE, "c":"ch","j":"j","x":"sh" },
    codepointMap: { ...LATIN_GENERIC_BASE },
    spanMap: SWAHILI_SPAN,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["swahili"], unit, parts),
  },
  "latin": {
    id: "latin",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: { ...LATIN_GENERIC_BASE, "c":"k","g":"g","j":"y","v":"w","y":"y","æ":"ae","œ":"oe" },
    codepointMap: { ...LATIN_GENERIC_BASE },
    spanMap: LATIN_SPAN,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["latin"], unit, parts),
  },
  "french": {
    id: "french",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: { ...LATIN_GENERIC_BASE, "c":"k/s","g":"g/zh","j":"zh","q":"k","r":"ʁ","u":"y","w":"w/v","y":"i", "ç":"s","œ":"oe","æ":"e" },
    codepointMap: { ...LATIN_GENERIC_BASE, "ç":"s","œ":"oe","æ":"e" },
    spanMap: FRENCH_SPAN,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["french"], unit, parts),
  },
  "italian": {
    id: "italian",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: { ...LATIN_GENERIC_BASE, "c":"k/ch","g":"g/j","h":"","z":"ts/dz" },
    codepointMap: { ...LATIN_GENERIC_BASE },
    spanMap: ITALIAN_SPAN,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["italian"], unit, parts),
  },
  "spanish": {
    id: "spanish",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: { ...LATIN_GENERIC_BASE, "c":"k/s","g":"g/x","h":"","j":"x","ñ":"ny","q":"k","v":"b","y":"y/i","z":"s" },
    codepointMap: { ...LATIN_GENERIC_BASE, "ñ":"ny", "ü":"u" },
    spanMap: SPANISH_SPAN,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["spanish"], unit, parts),
  },
  "german": {
    id: "german",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: { ...LATIN_GENERIC_BASE, "c":"ts/k","j":"y","q":"k","v":"f","w":"v","x":"ks","y":"y/ü","z":"ts","ä":"ɛ","ö":"ø","ü":"y","ß":"ss" },
    codepointMap: { ...LATIN_GENERIC_BASE, "ä":"ɛ","ö":"ø","ü":"y","ß":"ss" },
    spanMap: GERMAN_SPAN,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["german"], unit, parts),
  },
  "dutch": {
    id: "dutch",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: { ...LATIN_GENERIC_BASE, "c":"k/s","g":"x","j":"y","q":"k","v":"f/v","w":"ʋ","x":"ks","y":"ij" },
    codepointMap: { ...LATIN_GENERIC_BASE },
    spanMap: DUTCH_SPAN,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["dutch"], unit, parts),
  },
  "portuguese": {
    id: "portuguese",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: { ...LATIN_GENERIC_BASE, "c":"k/s","g":"g/zh","h":"","j":"zh","q":"k","r":"ʁ/r","s":"s/z","x":"sh/s/ks","ç":"s","ã":"ã","õ":"õ" },
    codepointMap: { ...LATIN_GENERIC_BASE, "ç":"s","ã":"ã","õ":"õ" },
    spanMap: PORTUGUESE_SPAN,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["portuguese"], unit, parts),
  },
  "old-english": {
    id: "old-english",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: { ...LATIN_GENERIC_BASE, "æ":"æ","þ":"th","ð":"dh","ȝ":"yogh","c":"k/ch","g":"g/y","ƿ":"w" },
    codepointMap: { ...LATIN_GENERIC_BASE, "æ":"æ","þ":"th","ð":"dh","ȝ":"yogh","ƿ":"w" },
    spanMap: OLD_ENGLISH_SPAN,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["old-english"], unit, parts),
  },
  "generic-latin": {
    id: "generic-latin",
    script: "Latin",
    scriptFamily: "latin",
    caseInsensitive: true,
    baseMap: LATIN_GENERIC_BASE,
    codepointMap: LATIN_GENERIC_BASE,
    analyze: (unit, parts) => analyzeLatin(PHONOLOGY_PROFILES["generic-latin"], unit, parts),
  },
  "han": {
    id: "han",
    script: "Han",
    scriptFamily: "han",
    codepointMap: {},
    analyze: (unit, parts) => ({
      sound: "",
      parts: parts.map((ch) => partObject(ch, "", inferRole(ch))),
      notes: ["han-ignored"],
    }),
  },
};

const GraphemePronunciationProfiles = {
  analyzeCluster,
  analyzeParts,
  analyzeMany,
  analyzeGraphemeStream,
  analyzeText: buildPronunciationAnalysis,
  buildPronunciationAnalysis,
  decomposeCluster,
  explainCluster,
  getLanguageProfile,
  normalizeLanguageId,
  splitGraphemeClusters,
  codePointHex,
  PHONOLOGY_PROFILES,
  LANGUAGE_ALIASES,
};

if (typeof globalThis !== "undefined") {
  globalThis.GraphemePronunciationProfiles = GraphemePronunciationProfiles;
  globalThis.grapheme_pronunciation_profiles = GraphemePronunciationProfiles;
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = GraphemePronunciationProfiles;
}

Object.assign(PHONOLOGY_PROFILES["arabic"].spanMap, { "و":"wa","ف":"fa","ب":"bi","ك":"ka","ل":"li","س":"sa","ت":"ta","ن":"na","م":"ma","ه":"ha","ي":"ya","ى":"ā","إ":"ʔi","أ":"ʔa","آ":"ʔā" });
Object.assign(PHONOLOGY_PROFILES["persian"].spanMap, { "و":"v","در":"dar","به":"be","می":"mi" });
Object.assign(PHONOLOGY_PROFILES["urdu"].spanMap, { "و":"vo/u","ب":"ba","ک":"ka","ل":"li","م":"ma","ہ":"ha","ے":"e" });
