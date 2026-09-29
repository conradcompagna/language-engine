import { semiticTablesState } from './semitic-tables.state.mjs';
export function initializeSemiticTables() {
  /* -------------------------------------------------------------------------- */
  /* Data tables                                                                 */
  /* -------------------------------------------------------------------------- */

  /* Arabic, Persian, Urdu */

  semiticTablesState.ARABIC_BASE_LETTERS = {
    ء: 'ʔ',
    آ: 'ʔā',
    أ: 'ʔa',
    ؤ: 'ʔu',
    إ: 'ʔi',
    ئ: 'ʔi',
    ـ: '',
    ا: 'ā',
    ب: 'b',
    ة: 'a',
    ت: 't',
    ث: 'th',
    ج: 'j',
    ح: 'ḥ',
    خ: 'kh',
    د: 'd',
    ذ: 'dh',
    ر: 'r',
    ز: 'z',
    س: 's',
    ش: 'sh',
    ص: 'ṣ',
    ض: 'ḍ',
    ط: 'ṭ',
    ظ: 'ẓ',
    ع: 'ʿ',
    غ: 'gh',
    ف: 'f',
    ق: 'q',
    ك: 'k',
    ل: 'l',
    م: 'm',
    ن: 'n',
    ه: 'h',
    و: 'w',
    ى: 'ā',
    ي: 'y',
    ٱ: 'a',
    لا: 'lā',
    ﻻ: 'lā'
  };
  semiticTablesState.ARABIC_MARKS = {
    'َ': 'a',
    'ً': 'an',
    'ُ': 'u',
    'ٌ': 'un',
    'ِ': 'i',
    'ٍ': 'in',
    'ْ': '',
    'ّ': '',
    'ٰ': 'ā',
    'ٔ': 'ʔ',
    'ٕ': 'ʔ'
  };
  semiticTablesState.PERSIAN_BASE_OVERRIDES = {
    پ: 'p',
    چ: 'ch',
    ژ: 'zh',
    گ: 'g',
    ک: 'k',
    ی: 'y',
    و: 'v',
    ا: 'â',
    آ: 'â',
    ۀ: 'e',
    ة: 'e'
  };
  semiticTablesState.URDU_BASE_OVERRIDES = {
    پ: 'p',
    ٹ: 'ṭ',
    ث: 's',
    ج: 'j',
    چ: 'ch',
    ح: 'h',
    خ: 'kh',
    د: 'd',
    ڈ: 'ḍ',
    ذ: 'z',
    ر: 'r',
    ڑ: 'ṛ',
    ز: 'z',
    ژ: 'zh',
    س: 's',
    ش: 'sh',
    ص: 's',
    ض: 'z',
    ط: 't',
    ظ: 'z',
    ع: 'ʿ',
    غ: 'gh',
    ف: 'f',
    ق: 'q',
    ک: 'k',
    گ: 'g',
    ل: 'l',
    م: 'm',
    ن: 'n',
    ں: '̃',
    و: 'v/u/o',
    ہ: 'h',
    ھ: 'h',
    ء: 'ʔ',
    ی: 'y/i',
    ے: 'e',
    ۓ: 'e'
  };

  /* Hebrew */

  semiticTablesState.HEBREW_LETTERS = {
    א: 'ʔ',
    ב: 'v',
    ג: 'g',
    ד: 'd',
    ה: 'h',
    ו: 'v',
    ז: 'z',
    ח: 'ḥ',
    ט: 'ṭ',
    י: 'y',
    כ: 'kh',
    ך: 'kh',
    ל: 'l',
    מ: 'm',
    ם: 'm',
    נ: 'n',
    ן: 'n',
    ס: 's',
    ע: 'ʿ',
    פ: 'f',
    ף: 'f',
    צ: 'ts',
    ץ: 'ts',
    ק: 'q',
    ר: 'r',
    ש: 'sh',
    ת: 't'
  };
  semiticTablesState.HEBREW_BEGADKEFAT_HARD = {
    ב: 'b',
    כ: 'k',
    ך: 'k',
    פ: 'p',
    ף: 'p',
    ת: 't'
  };
  semiticTablesState.HEBREW_MARKS = {
    '\u05B0': 'ə',
    '\u05B1': 'e',
    '\u05B2': 'a',
    '\u05B3': 'o',
    '\u05B4': 'i',
    '\u05B5': 'e',
    '\u05B6': 'e',
    '\u05B7': 'a',
    '\u05B8': 'a',
    '\u05B9': 'o',
    '\u05BA': 'o',
    '\u05BB': 'u',
    '\u05BC': '',
    '\u05BD': '',
    '\u05BF': '',
    '\u05C1': '',
    '\u05C2': '',
    '\u05C7': 'a'
  };

  /* Greek */
  return true;
}
