import { hangulTablesState } from './hangul-tables.state.mjs';
export function initializeHangulExtensions() {
  Object.assign(hangulTablesState.HANGUL_JAMO_MAP, {
    ᅶ: 'yo-ya',
    ᅷ: 'yo-yae',
    ᅸ: 'yo-i',
    ᅹ: 'yu-yeo',
    ᅺ: 'yu-e',
    ᅻ: 'yu-i',
    ᅼ: 'eu-u',
    ᅽ: 'eu-eu',
    ᆪ: 'ks',
    ᆬ: 'nj',
    ᆭ: 'nh',
    ᆰ: 'lk',
    ᆱ: 'lm',
    ᆲ: 'lb',
    ᆳ: 'ls',
    ᆴ: 'lt',
    ᆵ: 'lp',
    ᆶ: 'lh',
    ᆹ: 'ps'
  });
  return true;
}
