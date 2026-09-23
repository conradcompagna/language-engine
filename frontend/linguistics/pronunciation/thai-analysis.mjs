import { applyThaiToneToRomanization } from './abugida-analysis.mjs';
import { inferRole, partObject } from './codepoints.mjs';
import { thaiTablesState } from './thai-tables.state.mjs';
export /* -------------------------------------------------------------------------- */
/* Thai                                                                        */
/* -------------------------------------------------------------------------- */

function analyzeThai(profile, unit, parts) {
  if (thaiTablesState.THAI_SPAN_MAP[unit] != null) {
    return {
      sound: thaiTablesState.THAI_SPAN_MAP[unit],
      parts: parts.map((ch) => thaiPartObject(ch)),
      notes: ['span-override'],
      derivation: {
        kind: 'thai-span-override',
        surface: unit,
        output: thaiTablesState.THAI_SPAN_MAP[unit]
      }
    };
  }
  const composed = composeThaiCluster(parts);
  const partObjs = parts.map((ch) => thaiPartObject(ch));
  return {
    sound: composed.sound,
    parts: partObjs,
    notes: composed.notes,
    derivation: composed.derivation
  };
}
export function thaiPartObject(ch) {
  return partObject(
    ch,
    thaiTablesState.THAI_PART_MAP[ch] ?? '',
    inferRole(ch),
    thaiTablesState.THAI_PART_DETAIL_MAP[ch]
      ? {
          rawSound: thaiTablesState.THAI_PART_DETAIL_MAP[ch].rawSound,
          detail: thaiTablesState.THAI_PART_DETAIL_MAP[ch].detail
        }
      : {}
  );
}
export function composeThaiCluster(parts) {
  const raw = parts.join('');
  if (thaiTablesState.THAI_SPAN_MAP[raw]) {
    return {
      sound: thaiTablesState.THAI_SPAN_MAP[raw],
      notes: ['span-override'],
      derivation: {
        kind: 'thai-span-override',
        surface: raw,
        output: thaiTablesState.THAI_SPAN_MAP[raw]
      }
    };
  }
  const onsetChars = [];
  const codaChars = [];
  let vowelPrefix = '';
  let vowelCore = '';
  let toneName = '';
  let silentMark = false;
  let shorteningMark = false;
  let hasShortVowelChar = false;
  let hasLongVowelChar = false;
  let hasMainVowelSeen = false;
  for (const ch of parts) {
    if (thaiTablesState.THAI_PREFIX_VOWELS[ch]) {
      vowelPrefix += thaiTablesState.THAI_PREFIX_VOWELS[ch];
      if (thaiTablesState.THAI_SHORT_VOWEL_CHARS.has(ch)) hasShortVowelChar = true;
      if (thaiTablesState.THAI_LONG_VOWEL_CHARS.has(ch)) hasLongVowelChar = true;
      continue;
    }
    if (thaiTablesState.THAI_VOWELS[ch] != null) {
      vowelCore += thaiTablesState.THAI_VOWELS[ch];
      hasMainVowelSeen = true;
      if (thaiTablesState.THAI_SHORT_VOWEL_CHARS.has(ch)) hasShortVowelChar = true;
      if (thaiTablesState.THAI_LONG_VOWEL_CHARS.has(ch)) hasLongVowelChar = true;
      continue;
    }
    if (ch === '์') {
      silentMark = true;
      continue;
    }
    if (ch === '็') {
      shorteningMark = true;
      hasShortVowelChar = true;
      continue;
    }
    if (thaiTablesState.THAI_TONE_MARKS[ch]) {
      toneName = thaiTablesState.THAI_TONE_MARKS[ch];
      continue;
    }
    if (thaiTablesState.THAI_CONSONANTS[ch]) {
      if (!hasMainVowelSeen) onsetChars.push(ch);
      else codaChars.push(ch);
    }
  }
  let effectiveClass = 'mid';
  let onsetCharsForOutput = onsetChars.slice();
  if (
    onsetChars.length >= 2 &&
    onsetChars[0] === 'ห' &&
    thaiTablesState.THAI_CLASS[onsetChars[1]] === 'low'
  ) {
    effectiveClass = 'high';
    onsetCharsForOutput = onsetChars.slice(1);
  } else if (onsetChars.length >= 2 && onsetChars[0] === 'อ' && onsetChars[1] === 'ย') {
    effectiveClass = 'mid';
    onsetCharsForOutput = onsetChars.slice(1);
  } else if (onsetChars.length >= 1) {
    effectiveClass = thaiTablesState.THAI_CLASS[onsetChars[0]] || 'mid';
    if (onsetChars[0] === 'อ' && onsetChars.length === 1 && (vowelPrefix || vowelCore || hasMainVowelSeen)) {
      onsetCharsForOutput = [];
    }
  }
  let onsetRom = '';
  for (const ch of onsetCharsForOutput) onsetRom += thaiTablesState.THAI_CONSONANTS[ch] || '';
  let codaRom = '';
  for (const ch of codaChars)
    codaRom += thaiTablesState.THAI_FINALS[ch] ?? thaiTablesState.THAI_CONSONANTS[ch] ?? '';
  if (silentMark && codaRom) codaRom = codaRom.slice(0, -1);
  const finalCodaChar = codaRom.slice(-1);
  const endsInStop = ['p', 't', 'k'].includes(finalCodaChar);
  const hasCoda = codaRom.length > 0;
  const isShort = hasShortVowelChar && !hasLongVowelChar;
  const isLong = hasLongVowelChar && !hasShortVowelChar;
  const isDeadSyllable = endsInStop || (!hasCoda && isShort);
  const vowelIsLong = isLong || /[āēīōūâêîôû]/.test(vowelCore);
  let computedTone = '';
  if (toneName) {
    if (toneName === 'low') {
      computedTone = effectiveClass === 'low' ? 'falling' : 'low';
    } else if (toneName === 'falling') {
      computedTone = effectiveClass === 'low' ? 'high' : 'falling';
    } else if (toneName === 'high') {
      computedTone = 'high';
    } else if (toneName === 'rising') {
      computedTone = 'rising';
    }
  } else {
    if (!isDeadSyllable) {
      if (effectiveClass === 'high') computedTone = 'rising';
    } else if (effectiveClass === 'low') {
      computedTone = vowelIsLong ? 'falling' : 'high';
    } else {
      computedTone = 'low';
    }
  }
  if (silentMark && !codaRom && !vowelPrefix && !vowelCore && onsetRom) {
    return {
      sound: onsetRom,
      notes: [],
      derivation: {
        kind: 'thai-cluster',
        surface: raw,
        onset: onsetRom,
        vowelPrefix: '',
        vowelCore: '',
        coda: '',
        tone: '',
        silentMark,
        shorteningMark,
        output: onsetRom
      }
    };
  }
  const body = !vowelPrefix && !vowelCore ? onsetRom + codaRom : onsetRom + vowelPrefix + vowelCore + codaRom;
  const sound = applyThaiToneToRomanization(body, computedTone);
  return {
    sound,
    notes: [],
    derivation: {
      kind: 'thai-cluster',
      surface: raw,
      onset: onsetRom,
      vowelPrefix,
      vowelCore,
      coda: codaRom,
      tone: computedTone,
      silentMark,
      shorteningMark,
      output: sound
    }
  };
}

/* -------------------------------------------------------------------------- */
/* Latin family (Old English only; modern Latin scripts intentionally removed) */
/* -------------------------------------------------------------------------- */
