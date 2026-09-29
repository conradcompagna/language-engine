import { abugidaTablesState } from './abugida-tables.state.mjs';
export function initializeAbugidaExtensions() {
  Object.assign(abugidaTablesState.DEVANAGARI_INDEPENDENT, {
    ॲ: 'æ',
    ऎ: 'e',
    ऒ: 'o',
    ॳ: 'ḷ',
    ॴ: 'ḹ',
    ॵ: 'a',
    ॶ: 'u',
    ॷ: 'u',
    ॸ: 'um',
    ॹ: 'z'
  });
  Object.assign(abugidaTablesState.DEVANAGARI_VOWEL_SIGNS, {
    'ॆ': 'e',
    'ॊ': 'o',
    'ॏ': 'aw',
    'ॖ': 'ue',
    'ॗ': 'uue',
    ꣻ: 'ue',
    '꣼': 'uue'
  });
  Object.assign(abugidaTablesState.DEVANAGARI_MARKS, {
    'ऀ': 'n',
    'ॎ': 'prishthamatra-e',
    'ॕ': 'e',
    ॱ: '',
    ꣳ: 'ṃ',
    ꣴ: 'ḥ',
    '꣸': '',
    '꣹': '',
    '꣺': ''
  });
  Object.assign(abugidaTablesState.BENGALI_CONSONANTS, {
    ৰ: 'r',
    ৱ: 'w',
    '঱': 'r',
    '঴': 'ḷ',
    '৺': 'ru',
    '৘': 'e',
    '৙': 'e'
  });
  Object.assign(abugidaTablesState.BENGALI_INDEPENDENT, {
    ঌ: 'ḷ',
    ৡ: 'ḹ',
    ৠ: 'ṝ',
    '৲': 'r',
    '৳': 't',
    '৴': 'coin'
  });
  Object.assign(abugidaTablesState.BENGALI_VOWEL_SIGNS, {
    'ৢ': 'ḷ',
    'ৣ': 'ḹ',
    'ৗ': 'au'
  });
  Object.assign(abugidaTablesState.BENGALI_MARKS, {
    '়': '',
    '্': '',
    ঽ: 'ʼ'
  });
  Object.assign(abugidaTablesState.GURMUKHI_CONSONANTS, {
    ੲ: 'ʔ',
    ੳ: 'u/o',
    'ੵ': 'f',
    '੶': 'halant-y',
    '੷': 'uḍāt',
    '੸': 'uḍāt',
    '੹': 'i',
    '੺': 'ਖ',
    '੻': 'ਗ',
    '੼': 'ਜ',
    '੽': 'ਫ',
    '੾': 'ਯ'
  });
  Object.assign(abugidaTablesState.GURMUKHI_INDEPENDENT, {
    ੴ: 'ik-oankar'
  });
  Object.assign(abugidaTablesState.GURMUKHI_MARKS, {
    'ਁ': '̃',
    'ਃ': 'ḥ',
    '਼': '',
    '੍': '',
    'ੑ': 'udat',
    '੒': 'udat',
    'ੵ': 'f'
  });
  Object.assign(abugidaTablesState.TAMIL_CONSONANTS, {
    ஶ: 'ś',
    ஜ: 'j',
    ஷ: 'ṣ',
    ஸ: 's',
    ஹ: 'h',
    க்ஷ: 'kṣ',
    ஶ்ரீ: 'śrī',
    ஐ: 'ai'
  });
  Object.assign(abugidaTablesState.TAMIL_INDEPENDENT, {
    ஐ: 'ai',
    ஔ: 'au'
  });
  Object.assign(abugidaTablesState.TAMIL_MARKS, {
    '்': '',
    'ஂ': 'ṃ',
    ஃ: 'ḥ',
    'ௗ': 'au'
  });
  return true;
}
