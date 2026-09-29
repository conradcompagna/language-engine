import { thaiTablesState } from './thai-tables.state.mjs';
export function initializeThaiExtensions() {
  Object.assign(thaiTablesState.THAI_CONSONANTS, {
    ฤ: 'rue',
    ฦ: 'lue'
  });
  Object.assign(thaiTablesState.THAI_FINALS, {
    ฤ: 't',
    ฦ: 't',
    อ: '',
    ฮ: 'h'
  });
  Object.assign(thaiTablesState.THAI_VOWELS, {
    'ั': 'a',
    ๅ: 'ā',
    'ํา': 'am',
    '๎': '',
    'ัว': 'ua'
  });
  Object.assign(thaiTablesState.THAI_PART_MAP, {
    '฿': 'baht',
    '๏': '',
    '๚': '',
    '๛': '',
    '๐': '0',
    '๑': '1',
    '๒': '2',
    '๓': '3',
    '๔': '4',
    '๕': '5',
    '๖': '6',
    '๗': '7',
    '๘': '8',
    '๙': '9',
    ฤ: 'rue',
    ฦ: 'lue',
    ๅ: 'ā',
    'ํ': 'n'
  });
  Object.assign(thaiTablesState.THAI_PART_DETAIL_MAP, {
    '๏': {
      rawSound: 'bullet',
      detail: 'section marker'
    },
    '๚': {
      rawSound: 'end',
      detail: 'end mark'
    },
    '๛': {
      rawSound: 'end',
      detail: 'end mark'
    }
  });
  return true;
}
