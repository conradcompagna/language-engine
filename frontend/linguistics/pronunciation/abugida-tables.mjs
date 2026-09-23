import { abugidaTablesState } from './abugida-tables.state.mjs';
export function initializeAbugidaTables() {
  /* Abugidas: Devanagari, Bengali, Gurmukhi, Tamil */

  abugidaTablesState.DEVANAGARI_CONSONANTS = {
    क: 'k',
    ख: 'kh',
    ग: 'g',
    घ: 'gh',
    ङ: 'ṅ',
    च: 'c',
    छ: 'ch',
    ज: 'j',
    झ: 'jh',
    ञ: 'ñ',
    ट: 'ṭ',
    ठ: 'ṭh',
    ड: 'ḍ',
    ढ: 'ḍh',
    ण: 'ṇ',
    त: 't',
    थ: 'th',
    द: 'd',
    ध: 'dh',
    न: 'n',
    प: 'p',
    फ: 'ph',
    ब: 'b',
    भ: 'bh',
    म: 'm',
    य: 'y',
    र: 'r',
    ल: 'l',
    व: 'v',
    श: 'ś',
    ष: 'ṣ',
    स: 's',
    ह: 'h',
    ळ: 'ḷ',
    क़: 'q',
    ख़: 'x',
    ग़: 'ġ',
    ज़: 'z',
    ड़: 'ṛ',
    ढ़: 'ṛh',
    फ़: 'f',
    ऩ: 'n',
    ऱ: 'r',
    य़: 'ẏ',
    ऴ: 'ḻ'
  };
  abugidaTablesState.DEVANAGARI_NUKTA = {
    क: 'क़',
    ख: 'ख़',
    ग: 'ग़',
    ज: 'ज़',
    ड: 'ड़',
    ढ: 'ढ़',
    फ: 'फ़',
    य: 'य़'
  };
  abugidaTablesState.DEVANAGARI_INDEPENDENT = {
    अ: 'a',
    आ: 'ā',
    इ: 'i',
    ई: 'ī',
    उ: 'u',
    ऊ: 'ū',
    ऋ: 'ṛ',
    ॠ: 'ṝ',
    ऌ: 'ḷ',
    ॡ: 'ḹ',
    ए: 'e',
    ऐ: 'ai',
    ओ: 'o',
    औ: 'au',
    ऑ: 'ŏ',
    ऍ: 'ĕ'
  };
  abugidaTablesState.DEVANAGARI_VOWEL_SIGNS = {
    'ा': 'ā',
    'ि': 'i',
    'ी': 'ī',
    'ु': 'u',
    'ू': 'ū',
    'ृ': 'ṛ',
    'ॄ': 'ṝ',
    'ॢ': 'ḷ',
    'ॣ': 'ḹ',
    'े': 'e',
    'ै': 'ai',
    'ो': 'o',
    'ौ': 'au',
    'ॅ': 'ĕ',
    'ॉ': 'ŏ'
  };
  abugidaTablesState.DEVANAGARI_MARKS = {
    'ं': 'ṃ',
    'ः': 'ḥ',
    'ँ': '̃',
    ऽ: 'ʼ',
    '॑': '´',
    '॒': '`'
  };
  abugidaTablesState.BENGALI_CONSONANTS = {
    ক: 'k',
    খ: 'kh',
    গ: 'g',
    ঘ: 'gh',
    ঙ: 'ṅ',
    চ: 'c',
    ছ: 'ch',
    জ: 'j',
    ঝ: 'jh',
    ঞ: 'ñ',
    ট: 'ṭ',
    ঠ: 'ṭh',
    ড: 'ḍ',
    ঢ: 'ḍh',
    ণ: 'ṇ',
    ত: 't',
    থ: 'th',
    দ: 'd',
    ধ: 'dh',
    ন: 'n',
    প: 'p',
    ফ: 'ph/f',
    ব: 'b',
    ভ: 'bh',
    ম: 'm',
    য: 'y',
    র: 'r',
    ল: 'l',
    শ: 'sh',
    ষ: 'ṣ',
    স: 's',
    হ: 'h',
    ড়: 'ṛ',
    ঢ়: 'ṛh',
    য়: 'ẏ',
    ৎ: 't',
    ড়়: 'ṛ',
    ঢ়়: 'ṛh'
  };
  abugidaTablesState.BENGALI_NUKTA = {
    ড: 'ড়',
    ঢ: 'ঢ়',
    য: 'য়'
  };
  abugidaTablesState.BENGALI_INDEPENDENT = {
    অ: 'ô',
    আ: 'ā',
    ই: 'i',
    ঈ: 'ī',
    উ: 'u',
    ঊ: 'ū',
    ঋ: 'ri',
    এ: 'e',
    ঐ: 'oi',
    ও: 'o',
    ঔ: 'ou'
  };
  abugidaTablesState.BENGALI_VOWEL_SIGNS = {
    'া': 'ā',
    'ি': 'i',
    'ী': 'ī',
    'ু': 'u',
    'ূ': 'ū',
    'ৃ': 'ri',
    'ে': 'e',
    'ৈ': 'oi',
    'ো': 'o',
    'ৌ': 'ou'
  };
  abugidaTablesState.BENGALI_MARKS = {
    'ং': 'ng',
    'ঃ': 'ḥ',
    'ঁ': '̃'
  };
  abugidaTablesState.GURMUKHI_CONSONANTS = {
    ਕ: 'k',
    ਖ: 'kh',
    ਗ: 'g',
    ਘ: 'k',
    ਙ: 'ṅ',
    ਚ: 'c',
    ਛ: 'ch',
    ਜ: 'j',
    ਝ: 'c',
    ਞ: 'ñ',
    ਟ: 'ṭ',
    ਠ: 'ṭh',
    ਡ: 'ḍ',
    ਢ: 'ṭ',
    ਣ: 'ṇ',
    ਤ: 't',
    ਥ: 'th',
    ਦ: 'd',
    ਧ: 't',
    ਨ: 'n',
    ਪ: 'p',
    ਫ: 'ph/f',
    ਬ: 'b',
    ਭ: 'p',
    ਮ: 'm',
    ਯ: 'y',
    ਰ: 'r',
    ਲ: 'l',
    ਵ: 'v',
    ਸ਼: 'sh',
    ਸ: 's',
    ਹ: 'h',
    ੜ: 'ṛ',
    ਖ਼: 'x',
    ਗ਼: 'ġ',
    ਜ਼: 'z',
    ਫ਼: 'f',
    ਲ਼: 'ḷ'
  };
  abugidaTablesState.GURMUKHI_NUKTA = {
    ਸ: 'ਸ਼',
    ਖ: 'ਖ਼',
    ਗ: 'ਗ਼',
    ਜ: 'ਜ਼',
    ਫ: 'ਫ਼',
    ਲ: 'ਲ਼'
  };
  abugidaTablesState.GURMUKHI_TONE_CONSONANTS = {
    ਘ: '\u0300',
    ਝ: '\u0300',
    ਢ: '\u0300',
    ਧ: '\u0300',
    ਭ: '\u0300'
  };
  abugidaTablesState.GURMUKHI_INDEPENDENT = {
    ਅ: 'a',
    ਆ: 'ā',
    ਇ: 'i',
    ਈ: 'ī',
    ਉ: 'u',
    ਊ: 'ū',
    ਏ: 'e',
    ਐ: 'ai',
    ਓ: 'o',
    ਔ: 'au'
  };
  abugidaTablesState.GURMUKHI_VOWEL_SIGNS = {
    'ਾ': 'ā',
    'ਿ': 'i',
    'ੀ': 'ī',
    'ੁ': 'u',
    'ੂ': 'ū',
    'ੇ': 'e',
    'ੈ': 'ai',
    'ੋ': 'o',
    'ੌ': 'au'
  };
  abugidaTablesState.GURMUKHI_MARKS = {
    'ਂ': '̃',
    'ੰ': '̃',
    'ਃ': 'ḥ',
    'ੱ': '',
    '੍': '',
    '਼': ''
  };
  abugidaTablesState.TAMIL_CONSONANTS = {
    க: 'k',
    ங: 'ṅ',
    ச: 'c',
    ஞ: 'ñ',
    ட: 'ṭ',
    ண: 'ṇ',
    த: 't',
    ந: 'n',
    ப: 'p',
    ம: 'm',
    ய: 'y',
    ர: 'r',
    ல: 'l',
    வ: 'v',
    ழ: 'ḻ',
    ள: 'ḷ',
    ற: 'ṟ',
    ன: 'ṉ',
    ஜ: 'j',
    ஷ: 'ṣ',
    ஸ: 's',
    ஹ: 'h',
    க்ஷ: 'kṣ'
  };
  abugidaTablesState.TAMIL_INDEPENDENT = {
    அ: 'a',
    ஆ: 'ā',
    இ: 'i',
    ஈ: 'ī',
    உ: 'u',
    ஊ: 'ū',
    எ: 'e',
    ஏ: 'ē',
    ஐ: 'ai',
    ஒ: 'o',
    ஓ: 'ō',
    ஔ: 'au'
  };
  abugidaTablesState.TAMIL_VOWEL_SIGNS = {
    'ா': 'ā',
    'ி': 'i',
    'ீ': 'ī',
    'ு': 'u',
    'ூ': 'ū',
    'ெ': 'e',
    'ே': 'ē',
    'ை': 'ai',
    'ொ': 'o',
    'ோ': 'ō',
    'ௌ': 'au'
  };
  abugidaTablesState.TAMIL_MARKS = {
    'ஂ': 'ṃ',
    ஃ: 'ḥ'
  };

  /* Thai */
  return true;
}
