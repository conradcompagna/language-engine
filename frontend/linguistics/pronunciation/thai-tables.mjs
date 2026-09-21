import { thaiTablesState } from './thai-tables.state.mjs';
export function initializeThaiTables() {
  /* Thai */

  thaiTablesState.THAI_CONSONANTS = {
    ก: 'k',
    ข: 'kh',
    ฃ: 'kh',
    ค: 'kh',
    ฅ: 'kh',
    ฆ: 'kh',
    ง: 'ng',
    จ: 'ch',
    ฉ: 'ch',
    ช: 'ch',
    ซ: 's',
    ฌ: 'ch',
    ญ: 'y',
    ฎ: 'd',
    ฏ: 't',
    ฐ: 'th',
    ฑ: 'th',
    ฒ: 'th',
    ณ: 'n',
    ด: 'd',
    ต: 't',
    ถ: 'th',
    ท: 'th',
    ธ: 'th',
    น: 'n',
    บ: 'b',
    ป: 'p',
    ผ: 'ph',
    ฝ: 'f',
    พ: 'ph',
    ฟ: 'f',
    ภ: 'ph',
    ม: 'm',
    ย: 'y',
    ร: 'r',
    ล: 'l',
    ว: 'w',
    ศ: 's',
    ษ: 's',
    ส: 's',
    ห: 'h',
    ฬ: 'l',
    อ: 'ʔ',
    ฮ: 'h'
  };
  thaiTablesState.THAI_CLASS = {
    ก: 'mid',
    จ: 'mid',
    ฎ: 'mid',
    ฏ: 'mid',
    ด: 'mid',
    ต: 'mid',
    บ: 'mid',
    ป: 'mid',
    อ: 'mid',
    ข: 'high',
    ฃ: 'high',
    ฉ: 'high',
    ฐ: 'high',
    ถ: 'high',
    ผ: 'high',
    ฝ: 'high',
    ศ: 'high',
    ษ: 'high',
    ส: 'high',
    ห: 'high',
    ค: 'low',
    ฅ: 'low',
    ฆ: 'low',
    ง: 'low',
    ช: 'low',
    ซ: 'low',
    ฌ: 'low',
    ญ: 'low',
    ฑ: 'low',
    ฒ: 'low',
    ณ: 'low',
    ท: 'low',
    ธ: 'low',
    น: 'low',
    พ: 'low',
    ฟ: 'low',
    ภ: 'low',
    ม: 'low',
    ย: 'low',
    ร: 'low',
    ล: 'low',
    ว: 'low',
    ฬ: 'low',
    ฮ: 'low'
  };
  thaiTablesState.THAI_SHORT_VOWEL_CHARS = new Set(['ะ', 'ั', 'ิ', 'ุ', 'ึ']);
  thaiTablesState.THAI_LONG_VOWEL_CHARS = new Set(['า', 'ี', 'ู', 'ื', 'ๅ', 'ำ']);
  thaiTablesState.THAI_FINALS = {
    ก: 'k',
    ข: 'k',
    ค: 'k',
    ฆ: 'k',
    ง: 'ng',
    จ: 't',
    ช: 't',
    ซ: 't',
    ฎ: 't',
    ฏ: 't',
    ฐ: 't',
    ฑ: 't',
    ฒ: 't',
    ด: 't',
    ต: 't',
    ถ: 't',
    ท: 't',
    ธ: 't',
    น: 'n',
    บ: 'p',
    ป: 'p',
    พ: 'p',
    ฟ: 'p',
    ภ: 'p',
    ม: 'm',
    ย: 'y',
    ร: 'n',
    ล: 'n',
    ว: 'w',
    ญ: 'n',
    ณ: 'n',
    ฬ: 'n',
    ส: 't',
    ศ: 't',
    ษ: 't',
    ห: 'h'
  };
  thaiTablesState.THAI_VOWELS = {
    ะ: 'a',
    'ั': 'a',
    า: 'ā',
    'ิ': 'i',
    'ี': 'ī',
    'ึ': 'ue',
    'ื': 'uee',
    'ุ': 'u',
    'ู': 'ū',
    เ: 'e',
    แ: 'ae',
    โ: 'o',
    ใ: 'ai',
    ไ: 'ai',
    ำ: 'am',
    ๅ: 'ā'
  };
  thaiTablesState.THAI_PREFIX_VOWELS = {
    เ: 'e',
    แ: 'ae',
    โ: 'o',
    ใ: 'ai',
    ไ: 'ai'
  };
  thaiTablesState.THAI_TONE_MARKS = {
    '่': 'low',
    '้': 'falling',
    '๊': 'high',
    '๋': 'rising'
  };
  thaiTablesState.THAI_TONE_COMBINING_MARKS = {
    low: '̀',
    falling: '̂',
    high: '́',
    rising: '̌'
  };
  thaiTablesState.THAI_PART_MAP = {
    ...thaiTablesState.THAI_CONSONANTS,
    ...thaiTablesState.THAI_VOWELS,
    '็': '',
    '่': '̀',
    '้': '̂',
    '๊': '́',
    '๋': '̌',
    '์': '',
    'ํ': 'n',
    'ฺ': '',
    ๆ: '',
    ฯ: ''
  };
  thaiTablesState.THAI_PART_DETAIL_MAP = {
    '็': {
      rawSound: 'short',
      detail: 'shortening mark'
    },
    '่': {
      rawSound: 'low-tone',
      detail: 'low tone'
    },
    '้': {
      rawSound: 'falling-tone',
      detail: 'falling tone'
    },
    '๊': {
      rawSound: 'high-tone',
      detail: 'high tone'
    },
    '๋': {
      rawSound: 'rising-tone',
      detail: 'rising tone'
    },
    '์': {
      rawSound: 'karan',
      detail: 'silent mark'
    },
    'ฺ': {
      rawSound: 'killer',
      detail: 'vowel killer'
    },
    ๆ: {
      rawSound: 'repeat',
      detail: 'repetition mark'
    },
    ฯ: {
      rawSound: 'abbrev',
      detail: 'abbreviation mark'
    }
  };
  thaiTablesState.THAI_SPAN_MAP = {
    อา: 'ā',
    อิ: 'i',
    อี: 'ī',
    อุ: 'u',
    อู: 'ū',
    เอ: 'e',
    โอ: 'o',
    ไอ: 'ai',
    ร์: 'r',
    น์: 'n',
    ต์: 't',
    ท์: 'th',
    ก์: 'k',
    ด์: 'd',
    ม์: 'm'
  };

  /* Latin family */
  return true;
}
