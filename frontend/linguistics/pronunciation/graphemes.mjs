import { aliasesState } from './aliases.state.mjs';
import { analyzeBySimpleMap } from './codepoints.mjs';
import { graphemesState } from './graphemes.state.mjs';
import { profilesState } from './profiles.state.mjs';
import { arabicBaseOfCluster } from './smoothing.mjs';
import { smoothingState } from './smoothing.state.mjs';
export function normalizeLanguageId(language) {
  const raw = String(language || '')
    .trim()
    .toLowerCase();
  return aliasesState.LANGUAGE_ALIASES[raw] || raw;
}
export function getLanguageProfile(language) {
  const id = normalizeLanguageId(language);
  if (graphemesState.DISABLED_PRONUNCIATION_LANGUAGE_IDS.has(id)) return null;
  return profilesState.PHONOLOGY_PROFILES[id] || null;
}
export function codePointHex(ch) {
  return 'U+' + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, '0');
}
export function splitClusterAroundWhitespace(cluster) {
  const raw = String(cluster ?? '');
  if (!raw) return [];
  if (!/\s/u.test(raw)) return [raw];
  const out = [];
  let current = '';
  for (const ch of Array.from(raw)) {
    if (/\s/u.test(ch)) {
      if (current) {
        out.push(current);
        current = '';
      }
      out.push(ch);
      continue;
    }
    current += ch;
  }
  if (current) out.push(current);
  return out;
}
export function separateWhitespaceClusters(clusters) {
  const src = Array.isArray(clusters) ? clusters : [];
  const out = [];
  for (const cluster of src) {
    out.push(...splitClusterAroundWhitespace(cluster));
  }
  return out;
}
export function splitGraphemeClusters(value, options = {}) {
  if (Array.isArray(options.clusters) && options.clusters.length) {
    return separateWhitespaceClusters(options.clusters.map((x) => String(x)));
  }
  const raw = String(value ?? '');
  if (!raw) return [];
  if (graphemesState.GRAPHEME_SEGMENTER) {
    return separateWhitespaceClusters(
      Array.from(graphemesState.GRAPHEME_SEGMENTER.segment(raw), (x) => x.segment)
    );
  }
  const fallback = raw.match(/\P{Mark}\p{Mark}*|\p{Mark}+|./gu);
  return separateWhitespaceClusters(fallback || Array.from(raw));
}
export function normalizeUnit(language, cluster, options = {}) {
  const raw = String(cluster ?? '');
  if (options.normalize === false) return raw;
  const compat = options.compatibility !== false;
  return compat ? raw.normalize('NFKC').normalize('NFC') : raw.normalize('NFC');
}
export function normalizeClusterSequence(language, clusters, options = {}) {
  if (typeof clusters === 'string') {
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
export function decomposeCluster(language, cluster, options = {}) {
  const profile = getLanguageProfile(language);
  const unit = normalizeUnit(language, cluster, options);
  if (!profile) return [];
  if (Array.isArray(options.parts) && options.parts.length) {
    return options.parts.map((x) => String(x));
  }
  if (profile.decomposeCluster) {
    return profile.decomposeCluster(unit, options);
  }
  return Array.from(unit.normalize(options.compatibility === false ? 'NFD' : 'NFKD'));
}
export function analyzeSingleCluster(language, cluster, options = {}) {
  const profile = getLanguageProfile(language);
  if (!profile) return null;
  const unit = normalizeUnit(profile.id, cluster, options);
  const parts = decomposeCluster(profile.id, unit, options);
  const analysis = profile.analyze
    ? profile.analyze(unit, parts, {
        ...graphemesState.DEFAULT_OPTIONS,
        ...options,
        profile
      })
    : analyzeBySimpleMap(profile, unit, parts, options);
  return {
    language: profile.id,
    script: profile.script,
    cluster: unit,
    sound: analysis.sound || '',
    romanization: analysis.sound || '',
    notes: analysis.notes || [],
    derivation: analysis.derivation || null,
    parts: (analysis.parts || []).map((part) => ({
      ...part,
      romanization: part.romanization ?? part.sound ?? ''
    }))
  };
}
export function cloneAnalysisItem(item) {
  return {
    ...item,
    sound: item.sound || '',
    romanization: item.romanization ?? item.sound ?? '',
    notes: Array.isArray(item.notes) ? [...item.notes] : [],
    parts: Array.isArray(item.parts)
      ? item.parts.map((part) => ({
          ...part,
          sound: part.sound || '',
          romanization: part.romanization ?? part.sound ?? ''
        }))
      : []
  };
}
export function buildSpanSequenceEntries(profile) {
  if (graphemesState.PROFILE_SPAN_SEQUENCE_CACHE.has(profile)) {
    return graphemesState.PROFILE_SPAN_SEQUENCE_CACHE.get(profile);
  }
  const entries = [];
  for (const [surface, sound] of Object.entries(profile.spanMap || {})) {
    const clusters = splitGraphemeClusters(surface);
    if (clusters.length <= 1) continue;
    entries.push({
      surface,
      sound,
      clusters: profile.caseInsensitive ? clusters.map((x) => x.toLowerCase()) : clusters,
      length: clusters.length
    });
  }
  entries.sort((a, b) => b.length - a.length || b.surface.length - a.surface.length);
  graphemesState.PROFILE_SPAN_SEQUENCE_CACHE.set(profile, entries);
  return entries;
}
export function applySpanSequenceRomanization(profile, clusters, items) {
  const sequences = buildSpanSequenceEntries(profile);
  if (!sequences.length) return items;
  const source = profile.caseInsensitive ? clusters.map((x) => x.toLowerCase()) : clusters.slice();
  let i = 0;
  while (i < source.length) {
    let matched = null;
    for (const entry of sequences) {
      if (i + entry.length > source.length) continue;
      if (profile.scriptFamily === 'arabic' && entry.surface === 'ال' && i + 2 < clusters.length) {
        const nextBase = arabicBaseOfCluster(clusters[i + 2]);
        if (smoothingState.ARABIC_SUN_LETTERS.has(nextBase)) continue;
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
      items[i + j].sound = '';
      items[i + j].romanization = '';
    }
    i += matched.length;
  }
  return items;
}
export function initializeGraphemes() {
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

  graphemesState.DEFAULT_OPTIONS = {
    normalize: true,
    decompose: true,
    preserveUnknown: false,
    compatibility: true
  };
  graphemesState.GRAPHEME_SEGMENTER =
    typeof Intl !== 'undefined' && typeof Intl.Segmenter === 'function'
      ? new Intl.Segmenter(undefined, {
          granularity: 'grapheme'
        })
      : null;
  graphemesState.PROFILE_SPAN_SEQUENCE_CACHE = new WeakMap();
  // Some legacy profile/data blocks still exist lower in this file; these ids are
  // intentionally disabled at runtime and should stay out unless explicitly revived.
  graphemesState.DISABLED_PRONUNCIATION_LANGUAGE_IDS = new Set([
    'vietnamese',
    'turkish',
    'indonesian',
    'tagalog',
    'swahili',
    'latin',
    'french',
    'italian',
    'spanish',
    'german',
    'dutch',
    'portuguese',
    'generic-latin',
    'han',
    'old-english'
  ]);
  return true;
}
