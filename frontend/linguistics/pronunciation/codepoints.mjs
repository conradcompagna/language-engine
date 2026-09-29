import { codepointsState } from './codepoints.state.mjs';
import { codePointHex } from './graphemes.mjs';
import { latinTablesState } from './latin-tables.state.mjs';
export /* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

function partObject(ch, sound = '', role = inferRole(ch), extra = {}) {
  return {
    char: ch,
    codePoint: codePointHex(ch),
    sound,
    role,
    ...extra
  };
}
export function inferRole(ch) {
  if (/\p{Mark}/u.test(ch)) return 'mark';
  if (/\p{Letter}/u.test(ch)) return 'letter';
  if (/\p{Number}/u.test(ch)) return 'number';
  if (isJamo(ch)) return 'jamo';
  return 'other';
}
export function isJamo(ch) {
  const cp = ch.codePointAt(0);
  return (
    (cp >= 0x1100 && cp <= 0x11ff) ||
    (cp >= 0x3130 && cp <= 0x318f) ||
    (cp >= 0xa960 && cp <= 0xa97f) ||
    (cp >= 0xd7b0 && cp <= 0xd7ff)
  );
}
export function stripCombining(str) {
  return str.normalize('NFD').replace(/\p{Mark}+/gu, '');
}
export function foldProfileText(profile, text) {
  return profile && profile.caseInsensitive ? String(text || '').toLowerCase() : String(text || '');
}
export function mapCodepoint(profile, ch) {
  if (!ch) return '';
  if (profile.codepointMap && profile.codepointMap[ch] != null) return profile.codepointMap[ch];
  const lower = foldProfileText(profile, ch);
  if (profile.codepointMap && profile.codepointMap[lower] != null) return profile.codepointMap[lower];
  if (profile.baseMap && profile.baseMap[lower] != null) return profile.baseMap[lower];
  if (latinTablesState.LATIN_COMBINING_MARKS[ch] != null) return latinTablesState.LATIN_COMBINING_MARKS[ch];
  if (codepointsState.COMMON_DIGITS[ch] != null) return codepointsState.COMMON_DIGITS[ch];
  if (codepointsState.COMMON_PUNCTUATION[ch] != null) return codepointsState.COMMON_PUNCTUATION[ch];
  const decomp = ch.normalize('NFKD');
  if (decomp !== ch) {
    const recursive = Array.from(decomp)
      .map((p) => mapCodepoint(profile, p))
      .join('');
    if (recursive) return recursive;
  }
  if (/\p{Mark}/u.test(ch)) return '';
  if (/\p{Script=Latin}/u.test(ch)) {
    const base = stripCombining(ch.toLowerCase());
    if (latinTablesState.LATIN_GENERIC_BASE[base] != null) return latinTablesState.LATIN_GENERIC_BASE[base];
  }
  return '';
}
export function combineNukta(base, nuktaMap, next) {
  if (next !== '़' && next !== '়' && next !== '਼') return null;
  return nuktaMap[base] || null;
}
export function analyzeBySimpleMap(profile, unit, parts, options = {}) {
  const raw = foldProfileText(profile, unit);
  if (profile.spanMap && profile.spanMap[raw] != null) {
    return {
      sound: profile.spanMap[raw],
      parts: parts.map((ch) => partObject(ch, mapCodepoint(profile, ch))),
      notes: ['span-override']
    };
  }
  const mapped = parts.map((ch) => partObject(ch, mapCodepoint(profile, ch), inferRole(ch)));
  let sound = mapped.map((x) => x.sound).join('');
  if (!sound && options.preserveUnknown) sound = unit;
  return {
    sound,
    parts: mapped,
    notes: []
  };
}

/* -------------------------------------------------------------------------- */
/* Arabic-script family                                                        */
/* -------------------------------------------------------------------------- */
export function initializeCodepoints() {
  codepointsState.COMMON_PUNCTUATION = {
    '-': '-',
    '‐': '-',
    '‑': '-',
    '–': '-',
    '—': '-',
    '/': '/',
    '\\': '\\',
    '.': '.',
    ',': ',',
    ':': ':',
    ';': ';',
    '?': '?',
    '!': '!',
    "'": "'",
    '’': "'",
    ʻ: "'",
    '،': ',',
    '؛': ';',
    '؟': '?',
    '־': '-',
    '׳': "'",
    '״': '"',
    '׃': ':',
    '।': '.',
    '॥': '..',
    '৽': '..',
    ੴ: 'ik-oankar',
    ๆ: 'repeat',
    ฯ: 'abbrev',
    '。': '.',
    '、': ','
  };
  codepointsState.COMMON_DIGITS = {
    '٠': '0',
    '١': '1',
    '٢': '2',
    '٣': '3',
    '٤': '4',
    '٥': '5',
    '٦': '6',
    '٧': '7',
    '٨': '8',
    '٩': '9',
    '۰': '0',
    '۱': '1',
    '۲': '2',
    '۳': '3',
    '۴': '4',
    '۵': '5',
    '۶': '6',
    '۷': '7',
    '۸': '8',
    '۹': '9',
    '०': '0',
    '१': '1',
    '२': '2',
    '३': '3',
    '४': '4',
    '५': '5',
    '६': '6',
    '७': '7',
    '८': '8',
    '९': '9',
    '০': '0',
    '১': '1',
    '২': '2',
    '৩': '3',
    '৪': '4',
    '৫': '5',
    '৬': '6',
    '৭': '7',
    '৮': '8',
    '৯': '9',
    '੦': '0',
    '੧': '1',
    '੨': '2',
    '੩': '3',
    '੪': '4',
    '੫': '5',
    '੬': '6',
    '੭': '7',
    '੮': '8',
    '੯': '9',
    '௦': '0',
    '௧': '1',
    '௨': '2',
    '௩': '3',
    '௪': '4',
    '௫': '5',
    '௬': '6',
    '௭': '7',
    '௮': '8',
    '௯': '9',
    '๐': '0',
    '๑': '1',
    '๒': '2',
    '๓': '3',
    '๔': '4',
    '๕': '5',
    '๖': '6',
    '๗': '7',
    '๘': '8',
    '๙': '9'
  };
  return true;
}
