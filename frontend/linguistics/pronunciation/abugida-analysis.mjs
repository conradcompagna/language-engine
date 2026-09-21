import { combineNukta, mapCodepoint, partObject } from './codepoints.mjs';
import { thaiTablesState } from './thai-tables.state.mjs';
export /* -------------------------------------------------------------------------- */
/* Brahmic / abugida family                                                    */
/* -------------------------------------------------------------------------- */

function analyzeAbugida(profile, unit, parts) {
  if (profile.spanMap && profile.spanMap[unit] != null) {
    return {
      sound: profile.spanMap[unit],
      parts: parts.map((ch) => partObject(ch, mapCodepoint(profile, ch))),
      notes: ['span-override']
    };
  }
  const partObjs = parts.map((ch) =>
    partObject(
      ch,
      profile.codepointMap?.[ch] ??
        profile.independentVowels?.[ch] ??
        profile.vowelSigns?.[ch] ??
        profile.consonants?.[ch] ??
        profile.marks?.[ch] ??
        ''
    )
  );
  const sound = composeAbugida(profile, parts);
  return {
    sound,
    parts: partObjs,
    notes: []
  };
}
export function findLastRomanVowelIndex(value) {
  const chars = Array.from(String(value || ''));
  for (let i = chars.length - 1; i >= 0; i -= 1) {
    if (/[aeiouyāēīōūăâêôơưəɨʉ]/i.test(chars[i])) {
      return i;
    }
  }
  return -1;
}
export function applyRomanCombiningMark(value, combiningMark) {
  const chars = Array.from(String(value || ''));
  if (!chars.length || !combiningMark) return String(value || '');
  const index = findLastRomanVowelIndex(chars.join(''));
  if (index >= 0) {
    chars[index] = (chars[index] + combiningMark).normalize('NFC');
    return chars.join('');
  }
  return chars.join('') + combiningMark;
}
export function applyThaiToneToRomanization(value, toneName) {
  const roman = String(value || '');
  if (!roman || !toneName) return roman;
  const combiningMark = thaiTablesState.THAI_TONE_COMBINING_MARKS[toneName];
  if (!combiningMark) return roman;
  return applyRomanCombiningMark(roman, combiningMark);
}
export function composeAbugida(profile, parts) {
  let out = '';
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
      let vowel = profile.inherentVowel || '';
      let finals = '';
      let j = i + 1 + (consumedNukta ? 1 : 0);
      while (j < parts.length) {
        const next = parts[j];
        if (profile.virama && next === profile.virama) {
          vowel = '';
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
        if (profile.nuktaMap && (next === '़' || next === '়' || next === '਼')) {
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
