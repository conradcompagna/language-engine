import vm from 'node:vm';

/** Isolated classic-script host; no network, filesystem or production globals. */
export function scriptHost(sources) {
  const host = { console, URL, TextDecoder, TextEncoder, Intl };
  host.window = host;
  host.self = host;
  vm.createContext(host);
  for (const [name, text] of Object.entries(sources)) vm.runInContext(text, host, { filename: name });
  return host;
}

export function dictionaryContract(host) {
  const Engine = host.DictionaryEngine;
  const engine = new Engine('en');
  const count = engine.loadFromRows([
    {
      headword: 'read',
      pos: 'verb',
      romanization: '',
      glosses: JSON.stringify([{ glosses: ['interpret text'] }]),
      forms: JSON.stringify([
        ['reads', 'third-person;singular'],
        ['reading', 'participle']
      ])
    },
    {
      headword: 'book',
      pos: 'noun',
      romanization: '',
      glosses: JSON.stringify([{ glosses: ['bound pages'] }])
    },
    { headword: 'reader', pos: 'noun', glosses: 'one who reads; reading device' }
  ]);
  const results = {};
  for (const word of ['read', 'reads', 'reading', 'book', 'reader', 'missing']) {
    results[word] = engine.lookup_all(word);
  }
  const compact = new Engine('en');
  compact.loadCompactIndex(
    { read: [[1, 0]], reader: [[2, 0]], book: [[3, 0]] },
    { reads: [[1, 0]] },
    { 0: 'fixture' }
  );
  const compactResults = ['read', 'reads', 'reed', 'boook', 'nothing'].map((word) => ({
    word,
    exact: compact.lookup_all(word),
    fuzzy: compact.fuzzyLookupKeysTiered(word, { maxTier: 1 })
  }));
  compact.injectGeminiKey('newword', 'custom-42', 'customdb', 'headword');
  const injected = compact.lookup_all('newword');
  compact.removeCompactKey('newword', 'custom-42');
  return JSON.parse(
    JSON.stringify({
      count,
      results,
      compactResults,
      injected,
      removed: compact.lookup_all('newword'),
      methods: Object.getOwnPropertyNames(Engine.prototype).sort()
    })
  );
}

export function tagsContract(host) {
  const tags = host.TRANKIT_TAGS;
  return JSON.parse(
    JSON.stringify({
      XPOS: tags.XPOS,
      DEP: tags.DEP,
      FEATS: tags.FEATS,
      lookups: [
        tags.getXpos('ancient-greek', '---------'),
        tags.getXpos('ja', 'nn'),
        tags.getDep('nsubj:pass'),
        tags.getFeat('Tense=Past'),
        tags.getXpos('unknown', '?')
      ]
    })
  );
}

export function pronunciationContract(host) {
  const api = host.GraphemePronunciationProfiles;
  const results = [];
  for (const [language, profile] of Object.entries(api.PHONOLOGY_PROFILES)) {
    const inputs = new Set([
      '',
      ' ',
      '?',
      '123',
      ...Object.keys(profile.baseMap || {}),
      ...Object.keys(profile.spanMap || {})
    ]);
    results.push([language, [...inputs].map((text) => api.analyzeCluster(language, text))]);
  }
  return { aliases: api.LANGUAGE_ALIASES, results };
}

export function clientContract(host) {
  const api = host.DictionaryClient;
  return {
    methods: Object.keys(api).sort(),
    rows: api.parseTsvText('headword\tpos\tglosses\nread\tverb\tinterpret text\nbook\tnoun\tbound pages\n'),
    alignments: [
      ['학교에서', '학교+에서', 'NNG+JKB', 'ko'],
      ['読んだ', '読む', 'VERB', 'ja'],
      ['reading', 'read', 'VERB', 'en'],
      ['a\u200bb', 'ab', 'X', 'en']
    ].map((args) => api.debugBuildLemmaAlignment(...args)),
    korean: api.debugBuildKoreanLemmaXposAlignment('학교에서', '학교+에서', 'NNG+JKB', 'ko')
  };
}
