import { stripCombining } from './codepoints.mjs';
import { latinTablesState } from './latin-tables.state.mjs';
export function composeVietnamese(raw, parts) {
  if (latinTablesState.VIETNAMESE_SPAN[raw] != null) return latinTablesState.VIETNAMESE_SPAN[raw];
  if (latinTablesState.VIETNAMESE_CODEPOINTS[raw] != null) return latinTablesState.VIETNAMESE_CODEPOINTS[raw];
  const base = stripCombining(raw);
  const hasBreve = parts.includes('\u0306');
  const hasCirc = parts.includes('\u0302');
  const hasHorn = parts.includes('\u031B');
  if (base === 'a' && hasBreve) return 'ă';
  if (base === 'a' && hasCirc) return 'â';
  if (base === 'e' && hasCirc) return 'ê';
  if (base === 'o' && hasCirc) return 'ô';
  if (base === 'o' && hasHorn) return 'ơ';
  if (base === 'u' && hasHorn) return 'ư';
  if (base === 'd' && parts.some((x) => x === '\u0335' || x === '\u0336')) return 'đ';
  return null;
}
export function composeTurkish(raw) {
  return latinTablesState.TURKISH_SPAN[raw] ?? null;
}
export function initializeLatinTables() {
  /* Latin family */

  latinTablesState.LATIN_COMBINING_MARKS = {
    '\u0300': '',
    '\u0301': '',
    '\u0302': '',
    '\u0303': '',
    '\u0304': '',
    '\u0306': '',
    '\u0307': '',
    '\u0308': '',
    '\u0309': '',
    '\u030A': '',
    '\u030B': '',
    '\u030C': '',
    '\u031B': '',
    '\u0323': '',
    '\u0327': '',
    '\u0328': '',
    '\u0335': '',
    '\u0336': ''
  };
  latinTablesState.LATIN_GENERIC_BASE = {
    a: 'a',
    b: 'b',
    c: 'k',
    d: 'd',
    e: 'e',
    f: 'f',
    g: 'g',
    h: 'h',
    i: 'i',
    j: 'j',
    k: 'k',
    l: 'l',
    m: 'm',
    n: 'n',
    o: 'o',
    p: 'p',
    q: 'k',
    r: 'r',
    s: 's',
    t: 't',
    u: 'u',
    v: 'v',
    w: 'w',
    x: 'x',
    y: 'y',
    z: 'z',
    æ: 'ae',
    œ: 'oe',
    þ: 'th',
    ð: 'dh',
    ȝ: 'gh',
    ə: 'ə',
    ß: 'ss',
    ł: 'w',
    ñ: 'ny',
    ç: 's',
    á: 'a',
    à: 'a',
    â: 'a',
    ä: 'a',
    ã: 'a',
    å: 'a',
    ā: 'a',
    ă: 'a',
    ą: 'a',
    é: 'e',
    è: 'e',
    ê: 'e',
    ë: 'e',
    ē: 'e',
    ĕ: 'e',
    ė: 'e',
    ę: 'e',
    í: 'i',
    ì: 'i',
    î: 'i',
    ï: 'i',
    ī: 'i',
    į: 'i',
    ı: 'i',
    ó: 'o',
    ò: 'o',
    ô: 'o',
    ö: 'o',
    õ: 'o',
    ō: 'o',
    ő: 'o',
    ø: 'o',
    ú: 'u',
    ù: 'u',
    û: 'u',
    ü: 'u',
    ū: 'u',
    ů: 'u',
    ű: 'u',
    ư: 'u',
    ý: 'y',
    ÿ: 'y',
    č: 'ch',
    š: 'sh',
    ž: 'zh',
    ğ: 'gh',
    đ: 'd',
    ř: 'rzh',
    ť: 'ty',
    ď: 'dy',
    ň: 'ny'
  };
  latinTablesState.VIETNAMESE_CODEPOINTS = {
    ă: 'ă',
    â: 'â',
    đ: 'đ',
    ê: 'ê',
    ô: 'ô',
    ơ: 'ơ',
    ư: 'ư',
    Ă: 'ă',
    Â: 'â',
    Đ: 'đ',
    Ê: 'ê',
    Ô: 'ô',
    Ơ: 'ơ',
    Ư: 'ư'
  };
  latinTablesState.VIETNAMESE_SPAN = {
    ch: 'ch',
    gh: 'g',
    gi: 'zi/ji',
    kh: 'kh',
    ng: 'ng',
    ngh: 'ng',
    nh: 'ny',
    ph: 'f',
    qu: 'kw',
    th: 'th',
    tr: 'tr',
    đ: 'd'
  };
  latinTablesState.TURKISH_SPAN = {
    ç: 'ch',
    ğ: 'ğ',
    ı: 'ı',
    i: 'i',
    ö: 'ö',
    ş: 'sh',
    ü: 'ü'
  };
  latinTablesState.INDONESIAN_SPAN = {
    ng: 'ng',
    ny: 'ny',
    sy: 'sh',
    kh: 'kh',
    ai: 'ai',
    au: 'au',
    oi: 'oi'
  };
  latinTablesState.TAGALOG_SPAN = {
    ng: 'ng',
    mga: 'mga',
    ts: 'ts',
    dy: 'dy',
    sy: 'sh'
  };
  latinTablesState.SWAHILI_SPAN = {
    ch: 'ch',
    dh: 'dh',
    gh: 'gh',
    kh: 'kh',
    ng: 'ng',
    "ng'": 'ng',
    ny: 'ny',
    sh: 'sh',
    th: 'th'
  };
  latinTablesState.LATIN_SPAN = {
    ae: 'ae',
    oe: 'oe',
    au: 'au',
    eu: 'eu',
    qu: 'kw'
  };
  latinTablesState.FRENCH_SPAN = {
    eau: 'o',
    au: 'o',
    ai: 'e',
    ei: 'e',
    oi: 'wa',
    ou: 'u',
    ch: 'sh',
    gn: 'ny',
    ph: 'f',
    an: 'ã',
    am: 'ã',
    en: 'ã',
    em: 'ã',
    in: 'ɛ̃',
    im: 'ɛ̃',
    ain: 'ɛ̃',
    ein: 'ɛ̃',
    on: 'õ',
    om: 'õ',
    un: 'œ̃',
    um: 'œ̃',
    ill: 'iy',
    œ: 'oe',
    ç: 's'
  };
  latinTablesState.ITALIAN_SPAN = {
    ch: 'k',
    gh: 'g',
    ci: 'chi',
    ce: 'che',
    gi: 'ji',
    ge: 'je',
    gli: 'lyi',
    gn: 'ny',
    sc: 'sk/sh',
    sce: 'she',
    sci: 'shi',
    qu: 'kw'
  };
  latinTablesState.SPANISH_SPAN = {
    ch: 'ch',
    ll: 'y',
    rr: 'rr',
    qu: 'k',
    gue: 'ge',
    gui: 'gi',
    güe: 'gwe',
    güi: 'gwi',
    ce: 'se',
    ci: 'si',
    ge: 'xe',
    gi: 'xi',
    ñ: 'ny'
  };
  latinTablesState.GERMAN_SPAN = {
    sch: 'sh',
    tsch: 'ch',
    ch: 'kh/ç',
    ei: 'ai',
    ie: 'i',
    eu: 'oi',
    äu: 'oi',
    sp: 'shp',
    st: 'sht',
    z: 'ts',
    ß: 'ss'
  };
  latinTablesState.DUTCH_SPAN = {
    ij: 'ei',
    oe: 'u',
    eu: 'ø',
    ui: 'œy',
    ou: 'au',
    au: 'au',
    sch: 'sx',
    ch: 'x'
  };
  latinTablesState.PORTUGUESE_SPAN = {
    nh: 'ny',
    lh: 'ly',
    ch: 'sh',
    ss: 's',
    rr: 'h/r',
    qu: 'k',
    gu: 'g',
    ão: 'ãw',
    ãe: 'ãi',
    õe: 'õi',
    am: 'ã',
    an: 'ã',
    em: 'ẽ',
    en: 'ẽ',
    im: 'ĩ',
    in: 'ĩ',
    om: 'õ',
    on: 'õ',
    um: 'ũ',
    un: 'ũ',
    ç: 's'
  };
  latinTablesState.OLD_ENGLISH_SPAN = {
    sc: 'sh',
    cg: 'j',
    hw: 'hw',
    hl: 'hl',
    hn: 'hn',
    hr: 'hr',
    ng: 'ng',
    ea: 'æɑ',
    eo: 'eo',
    ie: 'ie'
  };

  /* -------------------------------------------------------------------------- */
  /* Language aliases and profiles                                               */
  /* -------------------------------------------------------------------------- */

  /* -------------------------------------------------------------------------- */
  /* Coverage extensions and no-gap fallbacks                                    */
  /* -------------------------------------------------------------------------- */
  return true;
}
