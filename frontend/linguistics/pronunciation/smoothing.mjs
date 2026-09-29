import { composeJapaneseSpan } from './east-asian-analysis.mjs';
import { applySpanSequenceRomanization, cloneAnalysisItem } from './graphemes.mjs';
import { japaneseSpansState } from './japanese-spans.state.mjs';
import { smoothingState } from './smoothing.state.mjs';
export function getInitialRomanConsonant(romanization) {
  const match = String(romanization || '').match(/^[^aeiouāēīōūəɨʉ]/i);
  return match ? match[0] : '';
}
export function getTrailingRomanVowel(romanization) {
  const match = String(romanization || '').match(/([aeiouāēīōūəɨʉ])$/i);
  return match ? match[1] : '';
}
export function applyJapaneseGraphemeSmoothing(clusters, items) {
  for (let i = 0; i < clusters.length; i += 1) {
    const cluster = clusters[i];
    if ((cluster === 'っ' || cluster === 'ッ') && i + 1 < items.length) {
      const onset = getInitialRomanConsonant(items[i + 1].romanization || items[i + 1].sound);
      items[i].sound = onset || 'Q';
      items[i].romanization = onset || 'Q';
      continue;
    }
    if (cluster === 'ー' && i > 0) {
      const vowel = getTrailingRomanVowel(items[i - 1].romanization || items[i - 1].sound);
      items[i].sound = vowel || '';
      items[i].romanization = vowel || '';
      continue;
    }
    if (
      (japaneseSpansState.JAPANESE_SMALL_Y[cluster] || japaneseSpansState.JAPANESE_SMALL_VOWEL[cluster]) &&
      i > 0
    ) {
      const prevCluster = clusters[i - 1];
      const pairSound = composeJapaneseSpan(prevCluster + cluster, [prevCluster, cluster]);
      const suffix =
        japaneseSpansState.JAPANESE_SMALL_Y[cluster] ||
        japaneseSpansState.JAPANESE_SMALL_VOWEL[cluster] ||
        '';
      if (pairSound && suffix && pairSound.length >= suffix.length) {
        const prefix = pairSound.slice(0, pairSound.length - suffix.length);
        items[i - 1].sound = prefix;
        items[i - 1].romanization = prefix;
        items[i].sound = suffix;
        items[i].romanization = suffix;
      }
      continue;
    }
    if ((cluster === 'ん' || cluster === 'ン') && i + 1 < items.length) {
      const next = items[i + 1].romanization || items[i + 1].sound;
      if (/^[bmp]/i.test(next)) {
        items[i].sound = 'm';
        items[i].romanization = 'm';
      } else if (/^[kg]/i.test(next)) {
        items[i].sound = 'ng';
        items[i].romanization = 'ng';
      }
    }
  }
  return items;
}

/* -------------------------------------------------------------------------- */
/* Arabic sun-letter assimilation                                             */
/* -------------------------------------------------------------------------- */
export function arabicBaseOfCluster(cluster) {
  if (!cluster) return '';
  const found = Array.from(String(cluster)).find((c) => !/\p{Mark}/u.test(c));
  return found || '';
}
export function applyArabicSunLetterSmoothing(clusters, items) {
  for (let i = 0; i + 2 < clusters.length; i++) {
    const base0 = arabicBaseOfCluster(clusters[i]);
    const base1 = arabicBaseOfCluster(clusters[i + 1]);
    const base2 = arabicBaseOfCluster(clusters[i + 2]);
    if (
      !smoothingState.ARABIC_ALIF_FORMS.has(base0) ||
      base1 !== 'ل' ||
      !smoothingState.ARABIC_SUN_LETTERS.has(base2)
    )
      continue;
    if (!items[i] || !items[i + 1] || !items[i + 2]) continue;
    const sunSound = items[i + 2].sound || items[i + 2].romanization || '';
    const onsetMatch = sunSound.match(/^[^aeiouāēīōūâêîôûəɨʉ]+/i);
    if (!onsetMatch) continue;
    items[i].sound = 'a';
    items[i].romanization = 'a';
    items[i + 1].sound = '-';
    items[i + 1].romanization = '-';
    items[i + 2].sound = onsetMatch[0] + sunSound;
    items[i + 2].romanization = onsetMatch[0] + sunSound;
  }
  return items;
}

/* -------------------------------------------------------------------------- */
/* Abugida smoothing: homorganic anusvara + word-final schwa deletion         */
/* -------------------------------------------------------------------------- */
export function computeHomorganicNasal(nextSound) {
  if (!nextSound) return null;
  if (/^(kh?|gh?)/.test(nextSound)) return 'ṅ';
  if (/^(ch?|jh?|ś)/.test(nextSound)) return 'ñ';
  if (/^(ṭh?|ḍh?|ṣ)/.test(nextSound)) return 'ṇ';
  if (/^(th?|dh?|n|s)/.test(nextSound)) return 'n';
  if (/^(ph?|bh?|m|v)/.test(nextSound)) return 'm';
  return null;
}
export function applyAbugidaGeminationSmoothing(profile, clusters, items) {
  if (!profile.geminationMark) return items;
  for (let i = 0; i + 1 < clusters.length; i++) {
    const cluster = String(clusters[i] || '');
    const next = items[i + 1];
    if (!cluster.includes(profile.geminationMark) || !next) continue;
    if (smoothingState.ABUGIDA_WORD_BOUNDARY_RE.test(String(clusters[i + 1] || ''))) continue;
    const nextSound = next.sound || next.romanization || '';
    const onsetMatch = nextSound.match(/^[^aeiouāēīōūâêîôûəɨʉ]+/i);
    if (!onsetMatch) continue;
    const geminated = onsetMatch[0] + nextSound;
    next.sound = geminated;
    next.romanization = geminated;
  }
  return items;
}
export function applyAbugidaAnusvaraHomorganic(clusters, items) {
  for (let i = 0; i + 1 < clusters.length; i++) {
    const item = items[i];
    const next = items[i + 1];
    if (!item || !next) continue;
    const sound = item.sound || item.romanization || '';
    if (!sound.endsWith('ṃ')) continue;
    if (smoothingState.ABUGIDA_WORD_BOUNDARY_RE.test(String(clusters[i + 1] || ''))) continue;
    const nextSound = next.sound || next.romanization || '';
    const replacement = computeHomorganicNasal(nextSound);
    if (!replacement) continue;
    const newSound = sound.slice(0, -1) + replacement;
    item.sound = newSound;
    item.romanization = newSound;
  }
  return items;
}
export function applyAbugidaSchwaDeletion(profile, clusters, items) {
  const inherent = profile.inherentVowel;
  if (!inherent) return items;
  for (let i = 0; i < clusters.length; i++) {
    const cluster = String(clusters[i] || '');
    if (!cluster || smoothingState.ABUGIDA_WORD_BOUNDARY_RE.test(cluster)) continue;
    const item = items[i];
    if (!item) continue;
    const sound = item.sound || item.romanization || '';
    if (!sound.endsWith(inherent)) continue;
    const isLast = i === clusters.length - 1;
    const nextIsBoundary =
      !isLast && smoothingState.ABUGIDA_WORD_BOUNDARY_RE.test(String(clusters[i + 1] || ''));
    if (!isLast && !nextIsBoundary) continue;
    const chars = Array.from(cluster);
    const hasExplicitVowel = chars.some(
      (c) =>
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
export function applyAbugidaSmoothing(profile, clusters, items) {
  applyAbugidaGeminationSmoothing(profile, clusters, items);
  applyAbugidaAnusvaraHomorganic(clusters, items);
  applyAbugidaSchwaDeletion(profile, clusters, items);
  return items;
}
export function smoothGraphemeItems(profile, clusters, items, options = {}) {
  const out = items.map((item) => cloneAnalysisItem(item));
  if (profile.scriptFamily === 'japanese') {
    applyJapaneseGraphemeSmoothing(clusters, out);
    return out;
  }
  if (profile.scriptFamily === 'arabic') {
    applyArabicSunLetterSmoothing(clusters, out);
  }
  if (profile.scriptFamily === 'abugida') {
    applyAbugidaSmoothing(profile, clusters, out);
  }
  if (profile.spanMap) {
    applySpanSequenceRomanization(profile, clusters, out);
  }
  return out;
}
export function initializeSmoothing() {
  smoothingState.ARABIC_SUN_LETTERS = new Set([
    'ت',
    'ث',
    'د',
    'ذ',
    'ر',
    'ز',
    'س',
    'ش',
    'ص',
    'ض',
    'ط',
    'ظ',
    'ل',
    'ن'
  ]);
  smoothingState.ARABIC_ALIF_FORMS = new Set(['ا', 'أ', 'إ', 'ٱ', 'آ']);
  smoothingState.ABUGIDA_WORD_BOUNDARY_RE = /^[\s।॥.,;:!?"'()\[\]{}\-–—]/u;
  return true;
}
