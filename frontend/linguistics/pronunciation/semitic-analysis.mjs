import { inferRole, mapCodepoint, partObject } from './codepoints.mjs';
import { semiticAnalysisState } from './semitic-analysis.state.mjs';
import { semiticTablesState } from './semitic-tables.state.mjs';
export /* -------------------------------------------------------------------------- */
/* Arabic-script family                                                        */
/* -------------------------------------------------------------------------- */

function analyzeArabicScript(profile, unit, parts) {
  if (profile.spanMap && profile.spanMap[unit] != null) {
    return {
      sound: profile.spanMap[unit],
      parts: parts.map((ch) => partObject(ch, mapCodepoint(profile, ch))),
      notes: ['span-override']
    };
  }
  const bases = parts.filter((ch) => !semiticTablesState.ARABIC_MARKS[ch]);
  if (bases.length === 1) {
    const base = bases[0];
    const marks = parts.filter((ch) => semiticTablesState.ARABIC_MARKS[ch]);
    const { sound, partSounds } = composeArabicBase(profile, base, marks);
    return {
      sound,
      parts: parts.map((ch) => partObject(ch, partSounds[ch] ?? mapCodepoint(profile, ch), inferRole(ch))),
      notes: marks.length ? ['base+marks'] : []
    };
  }
  const partObjs = [];
  let out = '';
  for (const ch of parts) {
    const s = mapCodepoint(profile, ch);
    partObjs.push(partObject(ch, s));
    out += s;
  }
  return {
    sound: out,
    parts: partObjs,
    notes: []
  };
}
export function composeArabicBase(profile, base, marks) {
  let baseSound = profile.baseLetters[base] ?? mapCodepoint(profile, base);
  const markSoundMap = {};
  const vowels = [];
  let geminated = false;
  const hasHamzaAbove = marks.includes('ٔ');
  const hasHamzaBelow = marks.includes('ٕ');
  if (base === 'ا' && (hasHamzaAbove || hasHamzaBelow)) {
    baseSound = 'ʔ';
  }
  if (base === 'و' && hasHamzaAbove) {
    baseSound = 'ʔ';
  }
  if ((base === 'ي' || base === 'ى') && hasHamzaAbove) {
    baseSound = 'ʔ';
  }

  // ta marbuta behaves differently when vocalized
  if (base === 'ة' && marks.length) {
    baseSound = 't';
  }
  for (const mark of marks) {
    const v = semiticTablesState.ARABIC_MARKS[mark] ?? '';
    if (mark === 'ّ') {
      geminated = true;
      markSoundMap[mark] = 'geminate';
      continue;
    }
    if (mark === 'ٔ' || mark === 'ٕ') {
      markSoundMap[mark] = 'hamza';
      continue;
    }
    vowels.push(v);
    markSoundMap[mark] = v;
  }
  let sound = geminated ? baseSound + baseSound : baseSound;
  sound += vowels.join('');

  // long-vowel / mater hints for Persian and Urdu
  // Letters that are inherently vowels or hamza carriers in Persian — no synthetic
  // vowel appended to these even in unvocalized text.
  const PERSIAN_MATER_OR_CARRIER = new Set(['ا', 'آ', 'و', 'ی', 'ئ', 'ء', 'أ', 'ؤ', 'إ', 'ة', 'ۀ']);
  if (!marks.length) {
    if (profile.id === 'persian') {
      if (base === 'ا' || base === 'آ') sound = 'â';
      if (base === 'و') sound = 'v';
      if (base === 'ی') sound = 'y';
      if (base === 'ه') sound = 'h/e';
    }
    if (profile.id === 'urdu') {
      if (base === 'و') sound = 'v/u/o';
      if (base === 'ی') sound = 'y/i/e';
      if (base === 'ے') sound = 'e';
      if (base === 'ں') sound = '̃';
    }
  }
  const partSounds = {
    [base]: baseSound,
    ...markSoundMap
  };
  return {
    sound,
    partSounds
  };
}

/* -------------------------------------------------------------------------- */
/* Hebrew                                                                      */
/* -------------------------------------------------------------------------- */

// Letters that are inherently silent or act as vowel carriers — no synthetic
// vowel appended to these even in unvocalized text.
export function analyzeHebrew(profile, unit, parts, options = {}) {
  if (profile.spanMap && profile.spanMap[unit] != null) {
    return {
      sound: profile.spanMap[unit],
      parts: parts.map((ch) => partObject(ch, mapCodepoint(profile, ch))),
      notes: ['span-override']
    };
  }
  const bases = parts.filter((ch) => !semiticTablesState.HEBREW_MARKS[ch]);
  if (bases.length === 1) {
    const base = bases[0];
    const marks = parts.filter((ch) => semiticTablesState.HEBREW_MARKS[ch]);
    const isFinal = !!options.isFinal;
    const { sound, partSounds } = composeHebrewBase(base, marks, isFinal);
    return {
      sound,
      parts: parts.map((ch) => partObject(ch, partSounds[ch] ?? mapCodepoint(profile, ch), inferRole(ch))),
      notes: marks.length
        ? ['base+niqqud']
        : sound !== (semiticTablesState.HEBREW_LETTERS[base] ?? '')
          ? ['synth-vowel']
          : []
    };
  }
  const mapped = parts.map((ch) => partObject(ch, mapCodepoint(profile, ch)));
  return {
    sound: mapped.map((x) => x.sound).join(''),
    parts: mapped,
    notes: []
  };
}
export function composeHebrewBase(base, marks, isFinal) {
  let baseSound = semiticTablesState.HEBREW_LETTERS[base] ?? '';
  const partSounds = {
    [base]: baseSound
  };
  const hasDagesh = marks.includes('\u05BC');
  const hasShinDot = marks.includes('\u05C1');
  const hasSinDot = marks.includes('\u05C2');
  const hasHolam = marks.includes('\u05B9') || marks.includes('\u05BA');
  const hasShuruk = base === 'ו' && hasDagesh;
  const hasAnyVowelMark = marks.some(
    (m) => semiticTablesState.HEBREW_MARKS[m] && m !== '\u05BC' && m !== '\u05C1' && m !== '\u05C2'
  );
  if (hasDagesh && semiticTablesState.HEBREW_BEGADKEFAT_HARD[base]) {
    baseSound = semiticTablesState.HEBREW_BEGADKEFAT_HARD[base];
    partSounds['\u05BC'] = 'hard';
  }
  if (base === 'ש') {
    if (hasSinDot) {
      baseSound = 's';
      partSounds['\u05C2'] = 'sin';
    } else if (hasShinDot) {
      baseSound = 'sh';
      partSounds['\u05C1'] = 'shin';
    }
  }
  if (base === 'ו' && hasShuruk) {
    return {
      sound: 'u',
      partSounds: {
        [base]: 'u',
        '\u05BC': 'u'
      }
    };
  }
  if (base === 'ו' && hasHolam) {
    const partSounds2 = {
      [base]: 'o'
    };
    for (const m of marks) partSounds2[m] = semiticTablesState.HEBREW_MARKS[m] ?? '';
    return {
      sound: 'o',
      partSounds: partSounds2
    };
  }
  let vowel = '';
  for (const mark of marks) {
    if (mark === '\u05BC' || mark === '\u05C1' || mark === '\u05C2') continue;
    vowel += semiticTablesState.HEBREW_MARKS[mark] ?? '';
    partSounds[mark] = semiticTablesState.HEBREW_MARKS[mark] ?? '';
  }

  // Synthetic default vowel for unvocalized text: insert short "a" after
  // consonants that carry no niqqud, unless word-final or silent/mater lectionis.
  if (
    !hasAnyVowelMark &&
    !vowel &&
    baseSound &&
    !isFinal &&
    !semiticAnalysisState.HEBREW_SILENT_OR_MATER.has(base)
  ) {
    vowel = 'a';
  }
  partSounds[base] = baseSound;
  return {
    sound: baseSound + vowel,
    partSounds
  };
}

/* -------------------------------------------------------------------------- */
/* Greek                                                                       */
/* -------------------------------------------------------------------------- */
export function initializeSemiticAnalysis() {
  semiticAnalysisState.HEBREW_SILENT_OR_MATER = new Set(['א', 'ה', 'ע', 'ו', 'י', 'ן', 'ם', 'ף', 'ך', 'ץ']);
  return true;
}
