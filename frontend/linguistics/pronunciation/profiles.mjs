import { analyzeAbugida } from './abugida-analysis.mjs';
import { abugidaTablesState } from './abugida-tables.state.mjs';
import { alphabetTablesState } from './alphabet-tables.state.mjs';
import { analyzeBySimpleMap, inferRole, partObject } from './codepoints.mjs';
import {
  analyzeGreek,
  analyzeHangul,
  analyzeJapanese,
  decomposeHangulString
} from './east-asian-analysis.mjs';
import { analyzeLatin } from './latin-analysis.mjs';
import { composeTurkish, composeVietnamese } from './latin-tables.mjs';
import { latinTablesState } from './latin-tables.state.mjs';
import { profilesState } from './profiles.state.mjs';
import { analyzeArabicScript, analyzeHebrew } from './semitic-analysis.mjs';
import { semiticTablesState } from './semitic-tables.state.mjs';
import { analyzeThai } from './thai-analysis.mjs';
import { thaiTablesState } from './thai-tables.state.mjs';
export function initializeProfiles() {
  profilesState.PHONOLOGY_PROFILES = {
    arabic: {
      id: 'arabic',
      script: 'Arabic',
      scriptFamily: 'arabic',
      baseLetters: semiticTablesState.ARABIC_BASE_LETTERS,
      codepointMap: {
        ...semiticTablesState.ARABIC_BASE_LETTERS,
        ...semiticTablesState.ARABIC_MARKS
      },
      spanMap: {
        ال: 'al',
        لل: 'lil',
        لا: 'lā',
        ﻻ: 'lā'
      },
      analyze: (unit, parts) => analyzeArabicScript(profilesState.PHONOLOGY_PROFILES['arabic'], unit, parts)
    },
    persian: {
      id: 'persian',
      script: 'Arabic',
      scriptFamily: 'arabic',
      baseLetters: {
        ...semiticTablesState.ARABIC_BASE_LETTERS,
        ...semiticTablesState.PERSIAN_BASE_OVERRIDES
      },
      codepointMap: {
        ...semiticTablesState.ARABIC_BASE_LETTERS,
        ...semiticTablesState.ARABIC_MARKS,
        ...semiticTablesState.PERSIAN_BASE_OVERRIDES
      },
      spanMap: {
        لا: 'lā'
      },
      analyze: (unit, parts) => analyzeArabicScript(profilesState.PHONOLOGY_PROFILES['persian'], unit, parts)
    },
    urdu: {
      id: 'urdu',
      script: 'Arabic',
      scriptFamily: 'arabic',
      baseLetters: {
        ...semiticTablesState.ARABIC_BASE_LETTERS,
        ...semiticTablesState.URDU_BASE_OVERRIDES
      },
      codepointMap: {
        ...semiticTablesState.ARABIC_BASE_LETTERS,
        ...semiticTablesState.ARABIC_MARKS,
        ...semiticTablesState.URDU_BASE_OVERRIDES
      },
      spanMap: {
        لا: 'lā'
      },
      analyze: (unit, parts) => analyzeArabicScript(profilesState.PHONOLOGY_PROFILES['urdu'], unit, parts)
    },
    hebrew: {
      id: 'hebrew',
      script: 'Hebrew',
      scriptFamily: 'hebrew',
      codepointMap: {
        ...semiticTablesState.HEBREW_LETTERS,
        ...semiticTablesState.HEBREW_MARKS
      },
      spanMap: {
        וו: 'v',
        יי: 'yy',
        וֹ: 'o',
        וּ: 'u'
      },
      analyze: (unit, parts, opts) =>
        analyzeHebrew(profilesState.PHONOLOGY_PROFILES['hebrew'], unit, parts, opts)
    },
    greek: {
      id: 'greek',
      script: 'Greek',
      scriptFamily: 'greek',
      caseInsensitive: true,
      codepointMap: alphabetTablesState.GREEK_MODERN,
      spanMap: alphabetTablesState.GREEK_MODERN_SPAN,
      analyze: (unit, parts) => analyzeGreek(profilesState.PHONOLOGY_PROFILES['greek'], unit, parts)
    },
    'ancient-greek': {
      id: 'ancient-greek',
      script: 'Greek',
      scriptFamily: 'greek',
      caseInsensitive: true,
      codepointMap: alphabetTablesState.GREEK_ANCIENT,
      spanMap: alphabetTablesState.GREEK_ANCIENT_SPAN,
      analyze: (unit, parts) => analyzeGreek(profilesState.PHONOLOGY_PROFILES['ancient-greek'], unit, parts)
    },
    russian: {
      id: 'russian',
      script: 'Cyrillic',
      scriptFamily: 'simple',
      caseInsensitive: true,
      codepointMap: alphabetTablesState.CYRILLIC_RUSSIAN,
      analyze: (unit, parts, options) =>
        analyzeBySimpleMap(profilesState.PHONOLOGY_PROFILES['russian'], unit.toLowerCase(), parts, options)
    },
    armenian: {
      id: 'armenian',
      script: 'Armenian',
      scriptFamily: 'simple',
      caseInsensitive: true,
      codepointMap: alphabetTablesState.ARMENIAN,
      spanMap: {
        ու: 'u',
        եւ: 'ev',
        և: 'ev'
      },
      analyze: (unit, parts, options) =>
        analyzeBySimpleMap(profilesState.PHONOLOGY_PROFILES['armenian'], unit.toLowerCase(), parts, options)
    },
    japanese: {
      id: 'japanese',
      script: 'Kana/Kanji',
      scriptFamily: 'japanese',
      decomposeCluster: (unit) => Array.from(unit.normalize('NFD')),
      analyze: (unit, parts) => analyzeJapanese(profilesState.PHONOLOGY_PROFILES['japanese'], unit, parts)
    },
    korean: {
      id: 'korean',
      script: 'Hangul',
      scriptFamily: 'hangul',
      decomposeCluster: (unit) => decomposeHangulString(unit).map((x) => x.char),
      analyze: (unit) => analyzeHangul(profilesState.PHONOLOGY_PROFILES['korean'], unit)
    },
    hindi: {
      id: 'hindi',
      script: 'Devanagari',
      scriptFamily: 'abugida',
      consonants: abugidaTablesState.DEVANAGARI_CONSONANTS,
      nuktaMap: abugidaTablesState.DEVANAGARI_NUKTA,
      independentVowels: abugidaTablesState.DEVANAGARI_INDEPENDENT,
      vowelSigns: abugidaTablesState.DEVANAGARI_VOWEL_SIGNS,
      marks: abugidaTablesState.DEVANAGARI_MARKS,
      virama: '्',
      inherentVowel: 'a',
      codepointMap: {
        ...abugidaTablesState.DEVANAGARI_CONSONANTS,
        ...abugidaTablesState.DEVANAGARI_INDEPENDENT,
        ...abugidaTablesState.DEVANAGARI_VOWEL_SIGNS,
        ...abugidaTablesState.DEVANAGARI_MARKS,
        '्': '',
        '़': ''
      },
      analyze: (unit, parts) => analyzeAbugida(profilesState.PHONOLOGY_PROFILES['hindi'], unit, parts)
    },
    bengali: {
      id: 'bengali',
      script: 'Bengali',
      scriptFamily: 'abugida',
      consonants: abugidaTablesState.BENGALI_CONSONANTS,
      nuktaMap: abugidaTablesState.BENGALI_NUKTA,
      independentVowels: abugidaTablesState.BENGALI_INDEPENDENT,
      vowelSigns: abugidaTablesState.BENGALI_VOWEL_SIGNS,
      marks: abugidaTablesState.BENGALI_MARKS,
      virama: '্',
      inherentVowel: 'ô',
      codepointMap: {
        ...abugidaTablesState.BENGALI_CONSONANTS,
        ...abugidaTablesState.BENGALI_INDEPENDENT,
        ...abugidaTablesState.BENGALI_VOWEL_SIGNS,
        ...abugidaTablesState.BENGALI_MARKS,
        '্': '',
        '়': ''
      },
      analyze: (unit, parts) => analyzeAbugida(profilesState.PHONOLOGY_PROFILES['bengali'], unit, parts)
    },
    punjabi: {
      id: 'punjabi',
      script: 'Gurmukhi',
      scriptFamily: 'abugida',
      consonants: abugidaTablesState.GURMUKHI_CONSONANTS,
      toneConsonants: abugidaTablesState.GURMUKHI_TONE_CONSONANTS,
      geminationMark: 'ੱ',
      nuktaMap: abugidaTablesState.GURMUKHI_NUKTA,
      independentVowels: abugidaTablesState.GURMUKHI_INDEPENDENT,
      vowelSigns: abugidaTablesState.GURMUKHI_VOWEL_SIGNS,
      marks: abugidaTablesState.GURMUKHI_MARKS,
      virama: '੍',
      inherentVowel: 'a',
      codepointMap: {
        ...abugidaTablesState.GURMUKHI_CONSONANTS,
        ...abugidaTablesState.GURMUKHI_INDEPENDENT,
        ...abugidaTablesState.GURMUKHI_VOWEL_SIGNS,
        ...abugidaTablesState.GURMUKHI_MARKS,
        '੍': '',
        '਼': ''
      },
      analyze: (unit, parts) => analyzeAbugida(profilesState.PHONOLOGY_PROFILES['punjabi'], unit, parts)
    },
    tamil: {
      id: 'tamil',
      script: 'Tamil',
      scriptFamily: 'abugida',
      consonants: abugidaTablesState.TAMIL_CONSONANTS,
      nuktaMap: {},
      independentVowels: abugidaTablesState.TAMIL_INDEPENDENT,
      vowelSigns: abugidaTablesState.TAMIL_VOWEL_SIGNS,
      marks: abugidaTablesState.TAMIL_MARKS,
      virama: '்',
      inherentVowel: 'a',
      codepointMap: {
        ...abugidaTablesState.TAMIL_CONSONANTS,
        ...abugidaTablesState.TAMIL_INDEPENDENT,
        ...abugidaTablesState.TAMIL_VOWEL_SIGNS,
        ...abugidaTablesState.TAMIL_MARKS,
        '்': ''
      },
      analyze: (unit, parts) => analyzeAbugida(profilesState.PHONOLOGY_PROFILES['tamil'], unit, parts)
    },
    thai: {
      id: 'thai',
      script: 'Thai',
      scriptFamily: 'thai',
      codepointMap: thaiTablesState.THAI_PART_MAP,
      analyze: (unit, parts) => analyzeThai(profilesState.PHONOLOGY_PROFILES['thai'], unit, parts)
    },
    vietnamese: {
      id: 'vietnamese',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        đ: 'd'
      },
      codepointMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        ...latinTablesState.VIETNAMESE_CODEPOINTS
      },
      spanMap: latinTablesState.VIETNAMESE_SPAN,
      composeLatin: composeVietnamese,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['vietnamese'], unit, parts)
    },
    turkish: {
      id: 'turkish',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        c: 'j',
        ç: 'ch',
        ğ: 'ğ',
        ı: 'ɯ',
        i: 'i',
        j: 'zh',
        ö: 'ø',
        ş: 'sh',
        ü: 'y'
      },
      codepointMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        ç: 'ch',
        ğ: 'ğ',
        ı: 'ɯ',
        ö: 'ø',
        ş: 'sh',
        ü: 'y'
      },
      spanMap: latinTablesState.TURKISH_SPAN,
      composeLatin: composeTurkish,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['turkish'], unit, parts)
    },
    indonesian: {
      id: 'indonesian',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        c: 'ch',
        e: 'ə/e',
        j: 'j',
        y: 'y'
      },
      codepointMap: {
        ...latinTablesState.LATIN_GENERIC_BASE
      },
      spanMap: latinTablesState.INDONESIAN_SPAN,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['indonesian'], unit, parts)
    },
    tagalog: {
      id: 'tagalog',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        c: 'k',
        f: 'p',
        j: 'h',
        q: 'k',
        v: 'b',
        x: 'ks',
        z: 's'
      },
      codepointMap: {
        ...latinTablesState.LATIN_GENERIC_BASE
      },
      spanMap: latinTablesState.TAGALOG_SPAN,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['tagalog'], unit, parts)
    },
    swahili: {
      id: 'swahili',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        c: 'ch',
        j: 'j',
        x: 'sh'
      },
      codepointMap: {
        ...latinTablesState.LATIN_GENERIC_BASE
      },
      spanMap: latinTablesState.SWAHILI_SPAN,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['swahili'], unit, parts)
    },
    latin: {
      id: 'latin',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        c: 'k',
        g: 'g',
        j: 'y',
        v: 'w',
        y: 'y',
        æ: 'ae',
        œ: 'oe'
      },
      codepointMap: {
        ...latinTablesState.LATIN_GENERIC_BASE
      },
      spanMap: latinTablesState.LATIN_SPAN,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['latin'], unit, parts)
    },
    french: {
      id: 'french',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        c: 'k/s',
        g: 'g/zh',
        j: 'zh',
        q: 'k',
        r: 'ʁ',
        u: 'y',
        w: 'w/v',
        y: 'i',
        ç: 's',
        œ: 'oe',
        æ: 'e'
      },
      codepointMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        ç: 's',
        œ: 'oe',
        æ: 'e'
      },
      spanMap: latinTablesState.FRENCH_SPAN,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['french'], unit, parts)
    },
    italian: {
      id: 'italian',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        c: 'k/ch',
        g: 'g/j',
        h: '',
        z: 'ts/dz'
      },
      codepointMap: {
        ...latinTablesState.LATIN_GENERIC_BASE
      },
      spanMap: latinTablesState.ITALIAN_SPAN,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['italian'], unit, parts)
    },
    spanish: {
      id: 'spanish',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        c: 'k/s',
        g: 'g/x',
        h: '',
        j: 'x',
        ñ: 'ny',
        q: 'k',
        v: 'b',
        y: 'y/i',
        z: 's'
      },
      codepointMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        ñ: 'ny',
        ü: 'u'
      },
      spanMap: latinTablesState.SPANISH_SPAN,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['spanish'], unit, parts)
    },
    german: {
      id: 'german',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        c: 'ts/k',
        j: 'y',
        q: 'k',
        v: 'f',
        w: 'v',
        x: 'ks',
        y: 'y/ü',
        z: 'ts',
        ä: 'ɛ',
        ö: 'ø',
        ü: 'y',
        ß: 'ss'
      },
      codepointMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        ä: 'ɛ',
        ö: 'ø',
        ü: 'y',
        ß: 'ss'
      },
      spanMap: latinTablesState.GERMAN_SPAN,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['german'], unit, parts)
    },
    dutch: {
      id: 'dutch',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        c: 'k/s',
        g: 'x',
        j: 'y',
        q: 'k',
        v: 'f/v',
        w: 'ʋ',
        x: 'ks',
        y: 'ij'
      },
      codepointMap: {
        ...latinTablesState.LATIN_GENERIC_BASE
      },
      spanMap: latinTablesState.DUTCH_SPAN,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['dutch'], unit, parts)
    },
    portuguese: {
      id: 'portuguese',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        c: 'k/s',
        g: 'g/zh',
        h: '',
        j: 'zh',
        q: 'k',
        r: 'ʁ/r',
        s: 's/z',
        x: 'sh/s/ks',
        ç: 's',
        ã: 'ã',
        õ: 'õ'
      },
      codepointMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        ç: 's',
        ã: 'ã',
        õ: 'õ'
      },
      spanMap: latinTablesState.PORTUGUESE_SPAN,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['portuguese'], unit, parts)
    },
    'old-english': {
      id: 'old-english',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        æ: 'æ',
        þ: 'th',
        ð: 'dh',
        ȝ: 'yogh',
        c: 'k/ch',
        g: 'g/y',
        ƿ: 'w'
      },
      codepointMap: {
        ...latinTablesState.LATIN_GENERIC_BASE,
        æ: 'æ',
        þ: 'th',
        ð: 'dh',
        ȝ: 'yogh',
        ƿ: 'w'
      },
      spanMap: latinTablesState.OLD_ENGLISH_SPAN,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['old-english'], unit, parts)
    },
    'generic-latin': {
      id: 'generic-latin',
      script: 'Latin',
      scriptFamily: 'latin',
      caseInsensitive: true,
      baseMap: latinTablesState.LATIN_GENERIC_BASE,
      codepointMap: latinTablesState.LATIN_GENERIC_BASE,
      analyze: (unit, parts) => analyzeLatin(profilesState.PHONOLOGY_PROFILES['generic-latin'], unit, parts)
    },
    han: {
      id: 'han',
      script: 'Han',
      scriptFamily: 'han',
      codepointMap: {},
      analyze: (unit, parts) => ({
        sound: '',
        parts: parts.map((ch) => partObject(ch, '', inferRole(ch))),
        notes: ['han-ignored']
      })
    }
  };
  return true;
}
