import { alphabetTablesState } from './alphabet-tables.state.mjs';
import { foldProfileText, inferRole, mapCodepoint, partObject } from './codepoints.mjs';
import { hangulTablesState } from './hangul-tables.state.mjs';
import { japaneseSpansState } from './japanese-spans.state.mjs';
import { japaneseTablesState } from './japanese-tables.state.mjs';
export /* -------------------------------------------------------------------------- */
/* Greek                                                                       */
/* -------------------------------------------------------------------------- */

function analyzeGreek(profile, unit, parts) {
  const raw = foldProfileText(profile, unit);
  if (profile.spanMap && profile.spanMap[raw] != null) {
    return {
      sound: profile.spanMap[raw],
      parts: parts.map((ch) => partObject(ch, mapCodepoint(profile, ch))),
      notes: ['span-override']
    };
  }
  const mapped = parts.map((ch) => partObject(ch, mapCodepoint(profile, ch)));
  const baseLetters = parts.filter((ch) => !/\p{Mark}/u.test(ch));
  let sound = baseLetters.map((ch) => mapCodepoint(profile, ch)).join('');
  if (parts.some((x) => alphabetTablesState.GREEK_ROUGH_BREATHING.has(x)) && sound) sound = 'h' + sound;
  if (parts.some((x) => x === '\u0345')) sound += 'i';
  return {
    sound,
    parts: mapped,
    notes: []
  };
}

/* -------------------------------------------------------------------------- */
/* Japanese                                                                    */
/* -------------------------------------------------------------------------- */
export function analyzeJapanese(profile, unit, parts) {
  if (/\p{Script=Han}/u.test(unit)) {
    return {
      sound: '',
      parts: parts.map((ch) => partObject(ch, '', inferRole(ch))),
      notes: ['han-ignored']
    };
  }
  if (japaneseTablesState.JAPANESE_SPAN_MAP[unit] != null) {
    return {
      sound: japaneseTablesState.JAPANESE_SPAN_MAP[unit],
      parts: parts.map((ch) =>
        partObject(ch, japaneseTablesState.JAPANESE_PART_MAP[ch] ?? '', inferRole(ch))
      ),
      notes: ['span-override']
    };
  }
  const baseLetters = parts.filter((ch) => !/\p{Mark}/u.test(ch));
  let sound = '';
  if (baseLetters.length === 1) {
    const base = baseLetters[0];
    sound = japaneseTablesState.JAPANESE_BASE_MAP[base] ?? '';
    if (parts.includes('\u3099')) sound = japaneseTablesState.JAPANESE_VOICED_OVERRIDES[sound] || sound;
    if (parts.includes('\u309A')) sound = japaneseTablesState.JAPANESE_SEMIVOICED_OVERRIDES[sound] || sound;
    if (base === 'っ' || base === 'ッ') sound = '';
    if (base === 'ー') sound = '';
  } else {
    sound = composeJapaneseSpan(unit, baseLetters);
  }
  const partObjs = parts.map((ch) =>
    partObject(ch, japaneseTablesState.JAPANESE_PART_MAP[ch] ?? '', inferRole(ch))
  );
  return {
    sound,
    parts: partObjs,
    notes: []
  };
}
export function composeJapaneseSpan(unit, baseLetters) {
  if (japaneseTablesState.JAPANESE_SPAN_MAP[unit]) return japaneseTablesState.JAPANESE_SPAN_MAP[unit];
  const raw = baseLetters.join('');
  if (japaneseTablesState.JAPANESE_SPAN_MAP[raw]) return japaneseTablesState.JAPANESE_SPAN_MAP[raw];
  if (baseLetters.length === 2) {
    const [a, b] = baseLetters;
    const first = japaneseTablesState.JAPANESE_BASE_MAP[a] ?? '';
    const second = japaneseTablesState.JAPANESE_BASE_MAP[b] ?? '';
    if (japaneseSpansState.JAPANESE_SMALL_Y[b]) {
      const stem = first.replace(/[aeiou]$/, '');
      const special = japaneseSpansState.JAPANESE_YOON_STEMS[first] || stem;
      return special + japaneseSpansState.JAPANESE_SMALL_Y[b];
    }
    if (japaneseSpansState.JAPANESE_SMALL_VOWEL[b]) {
      const prefix = japaneseSpansState.JAPANESE_FOREIGN_STEMS[first] || first.replace(/[aeiou]$/, '');
      return prefix + japaneseSpansState.JAPANESE_SMALL_VOWEL[b];
    }
    if ((a === 'っ' || a === 'ッ') && second) {
      return second[0] + second;
    }
  }
  if (baseLetters.length > 1) {
    let out = '';
    for (let i = 0; i < baseLetters.length; i += 1) {
      const ch = baseLetters[i];
      if ((ch === 'っ' || ch === 'ッ') && i + 1 < baseLetters.length) {
        const next = composeJapaneseSpan(baseLetters.slice(i + 1).join(''), baseLetters.slice(i + 1));
        out += next ? next[0] : 'Q';
        continue;
      }
      out += japaneseTablesState.JAPANESE_BASE_MAP[ch] ?? '';
    }
    return out;
  }
  return raw
    .split('')
    .map((ch) => japaneseTablesState.JAPANESE_BASE_MAP[ch] ?? '')
    .join('');
}

/* -------------------------------------------------------------------------- */
/* Hangul                                                                      */
/* -------------------------------------------------------------------------- */
export function analyzeHangul(profile, unit) {
  const parts = decomposeHangulString(unit);
  const objs = parts.map((x) => partObject(x.char, x.sound, x.role));
  return {
    sound: parts.map((x) => x.sound).join(''),
    parts: objs,
    notes: ['algorithmic-hangul']
  };
}
export function decomposeHangulString(unit) {
  const out = [];
  for (const ch of Array.from(unit)) {
    const cp = ch.codePointAt(0);
    if (cp >= 0xac00 && cp <= 0xd7a3) {
      const SBase = 0xac00;
      const LBase = 0x1100;
      const VBase = 0x1161;
      const TBase = 0x11a7;
      const VCount = 21;
      const TCount = 28;
      const NCount = VCount * TCount;
      const sIndex = cp - SBase;
      const lIndex = Math.floor(sIndex / NCount);
      const vIndex = Math.floor((sIndex % NCount) / TCount);
      const tIndex = sIndex % TCount;
      const L = String.fromCodePoint(LBase + lIndex);
      const V = String.fromCodePoint(VBase + vIndex);
      out.push({
        char: L,
        sound: hangulTablesState.HANGUL_CHO[lIndex],
        role: 'choseong'
      });
      out.push({
        char: V,
        sound: hangulTablesState.HANGUL_JUNG[vIndex],
        role: 'jungseong'
      });
      if (tIndex > 0) {
        const T = String.fromCodePoint(TBase + tIndex);
        out.push({
          char: T,
          sound: hangulTablesState.HANGUL_JONG[tIndex],
          role: 'jongseong'
        });
      }
      continue;
    }
    for (const p of Array.from(ch.normalize('NFD'))) {
      out.push({
        char: p,
        sound: hangulTablesState.HANGUL_JAMO_MAP[p] || '',
        role: 'jamo'
      });
    }
  }
  return out;
}

/* -------------------------------------------------------------------------- */
/* Brahmic / abugida family                                                    */
/* -------------------------------------------------------------------------- */
