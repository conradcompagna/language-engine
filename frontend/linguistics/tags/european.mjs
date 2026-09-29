import { europeanState } from './european.state.mjs';
export function initializeEuropean() {
  europeanState.XPOS_VI = {
    N: 'Common Noun',
    Np: 'Proper Noun',
    Nc: 'Classifier Noun',
    Nu: 'Unit Noun',
    Nb: 'Abbreviated Noun',
    Ny: 'Nominal Abbreviation',
    V: 'Verb',
    A: 'Adjective',
    P: 'Pronoun',
    R: 'Adverb',
    L: 'Determiner',
    M: 'Numeral',
    E: 'Preposition',
    C: 'Subordinating Conjunction',
    CC: 'Coordinating Conjunction',
    I: 'Interjection',
    T: 'Particle / Auxiliary Word',
    S: 'Affix',
    Y: 'Abbreviation',
    CH: 'Punctuation',
    X: 'Other / Unknown',
    _: 'Null / No Tag Assigned'
  };
  europeanState.XPOS_GERMAN = {
    '$(': 'Other Punctuation (Bracket, Dash, etc.)',
    '$,': 'Comma',
    '$.': 'Sentence-Final Punctuation',
    ADJA: 'Attributive Adjective',
    ADJD: 'Adverbial / Predicative Adjective',
    ADV: 'Adverb',
    APPO: 'Postposition',
    APPOS: 'Appositional Element',
    APPR: 'Preposition',
    APPRART: 'Preposition Fused With Article',
    APZR: 'Circumposition (Right Part)',
    ART: 'Article',
    CARD: 'Cardinal Number',
    FM: 'Foreign-Language Material',
    ITJ: 'Interjection',
    KOKOM: 'Comparative Conjunction',
    KON: 'Coordinating Conjunction',
    KOUI: 'Subordinating Conjunction (With zu+infinitive)',
    KOUS: 'Subordinating Conjunction (With Sentence)',
    NE: 'Proper Noun',
    NN: 'Common Noun',
    PAV: 'Pronominal Adverb',
    PDAT: 'Attributive Demonstrative Pronoun',
    PDS: 'Substituting Demonstrative Pronoun',
    PIAT: 'Attributive Indefinite Pronoun (Without Determiner)',
    PIS: 'Substituting Indefinite Pronoun',
    PPER: 'Non-Reflexive Personal Pronoun',
    PPOSAT: 'Attributive Possessive Pronoun',
    PPOSS: 'Substituting Possessive Pronoun',
    PRELAT: 'Attributive Relative Pronoun',
    PRELS: 'Substituting Relative Pronoun',
    PRF: 'Reflexive Personal Pronoun',
    PTKA: 'Particle With Adjective / Adverb',
    PTKANT: 'Answer Particle',
    PTKNEG: 'Negation Particle',
    PTKVZ: 'Separable Verb Prefix',
    PTKZU: '’Zu’ Particle (Before Infinitive)',
    PWAT: 'Attributive Interrogative Pronoun',
    PWAV: 'Adverbial Interrogative / Relative Pronoun',
    PWS: 'Substituting Interrogative Pronoun',
    TRUNC: 'Word Remnant (First Part Of Compound)',
    VAFIN: 'Finite Auxiliary Verb',
    VAINF: 'Infinitive Auxiliary Verb',
    VAPP: 'Past Participle Auxiliary Verb',
    VMFIN: 'Finite Modal Verb',
    VMINF: 'Infinitive Modal Verb',
    VVFIN: 'Finite Full Verb',
    VVIMP: 'Imperative Full Verb',
    VVINF: 'Infinitive Full Verb',
    VVIZU: 'Infinitive Full Verb With ’Zu’',
    VVPP: 'Past Participle Full Verb',
    XY: 'Non-Word (Special Symbol / Formula)'
  };
  europeanState.XPOS_DUTCH = {
    'ADJ|nom|basis|met-e|mv-n': 'Adjective, Nominalized, Base Form, Inflected (-E), Plural',
    'ADJ|nom|basis|met-e|zonder-n|bijz':
      'Adjective, Nominalized, Base Form, Inflected (-E), Singular / Uncountable, Oblique Case',
    'ADJ|nom|basis|met-e|zonder-n|stan':
      'Adjective, Nominalized, Base Form, Inflected (-E), Singular / Uncountable, Standard Case',
    'ADJ|nom|basis|zonder|mv-n': 'Adjective, Nominalized, Base Form, Uninflected, Plural',
    'ADJ|nom|basis|zonder|zonder-n': 'Adjective, Nominalized, Base Form, Uninflected, Singular / Uncountable',
    'ADJ|nom|comp|met-e|mv-n': 'Adjective, Nominalized, Comparative, Inflected (-E), Plural',
    'ADJ|nom|comp|met-e|zonder-n|stan':
      'Adjective, Nominalized, Comparative, Inflected (-E), Singular / Uncountable, Standard Case',
    'ADJ|nom|sup|met-e|mv-n': 'Adjective, Nominalized, Superlative, Inflected (-E), Plural',
    'ADJ|nom|sup|met-e|zonder-n|bijz':
      'Adjective, Nominalized, Superlative, Inflected (-E), Singular / Uncountable, Oblique Case',
    'ADJ|nom|sup|met-e|zonder-n|stan':
      'Adjective, Nominalized, Superlative, Inflected (-E), Singular / Uncountable, Standard Case',
    'ADJ|nom|sup|zonder|zonder-n': 'Adjective, Nominalized, Superlative, Uninflected, Singular / Uncountable',
    'ADJ|postnom|basis|met-s': 'Adjective, Postnominal, Base Form, Inflected (-S)',
    'ADJ|postnom|basis|zonder': 'Adjective, Postnominal, Base Form, Uninflected',
    'ADJ|postnom|comp|met-s': 'Adjective, Postnominal, Comparative, Inflected (-S)',
    'ADJ|prenom|basis|met-e|stan': 'Adjective, Prenominal, Base Form, Inflected (-E), Standard Case',
    'ADJ|prenom|basis|zonder': 'Adjective, Prenominal, Base Form, Uninflected',
    'ADJ|prenom|comp|met-e|stan': 'Adjective, Prenominal, Comparative, Inflected (-E), Standard Case',
    'ADJ|prenom|comp|zonder': 'Adjective, Prenominal, Comparative, Uninflected',
    'ADJ|prenom|sup|met-e|stan': 'Adjective, Prenominal, Superlative, Inflected (-E), Standard Case',
    'ADJ|prenom|sup|zonder': 'Adjective, Prenominal, Superlative, Uninflected',
    'ADJ|vrij|basis|zonder': 'Adjective, Free / Predicative, Base Form, Uninflected',
    'ADJ|vrij|comp|zonder': 'Adjective, Free / Predicative, Comparative, Uninflected',
    'ADJ|vrij|dim|zonder': 'Adjective, Free / Predicative, Diminutive, Uninflected',
    'ADJ|vrij|sup|zonder': 'Adjective, Free / Predicative, Superlative, Uninflected',
    BW: 'Adverb',
    LET: 'Punctuation',
    'LID|bep|dat|evmo': 'Article, Definite, Dative, Singular Masculine Oblique',
    'LID|bep|gen|evmo': 'Article, Definite, Genitive, Singular Masculine Oblique',
    'LID|bep|gen|rest3': 'Article, Definite, Genitive, Remaining Genitive Form',
    'LID|bep|stan|evon': 'Article, Definite, Standard Case, Singular Neuter',
    'LID|bep|stan|rest': 'Article, Definite, Standard Case, Remaining Forms',
    'LID|onbep|stan|agr': 'Article, Indefinite, Standard Case, Agreement Form',
    'N|eigen|ev|basis|gen': 'Noun, Proper, Singular, Base Form, Genitive',
    'N|eigen|ev|basis|genus|stan': 'Noun, Proper, Singular, Base Form, Unspecified Gender, Standard Case',
    'N|eigen|ev|basis|onz|stan': 'Noun, Proper, Singular, Base Form, Neuter, Standard Case',
    'N|eigen|ev|basis|zijd|stan': 'Noun, Proper, Singular, Base Form, Common Gender, Standard Case',
    'N|eigen|ev|dim|onz|stan': 'Noun, Proper, Singular, Diminutive, Neuter, Standard Case',
    'N|eigen|mv|basis': 'Noun, Proper, Plural, Base Form',
    'N|soort|ev|basis|dat': 'Noun, Common, Singular, Base Form, Dative',
    'N|soort|ev|basis|gen': 'Noun, Common, Singular, Base Form, Genitive',
    'N|soort|ev|basis|genus|stan': 'Noun, Common, Singular, Base Form, Unspecified Gender, Standard Case',
    'N|soort|ev|basis|onz|stan': 'Noun, Common, Singular, Base Form, Neuter, Standard Case',
    'N|soort|ev|basis|zijd|stan': 'Noun, Common, Singular, Base Form, Common Gender, Standard Case',
    'N|soort|ev|dim|onz|stan': 'Noun, Common, Singular, Diminutive, Neuter, Standard Case',
    'N|soort|mv|basis': 'Noun, Common, Plural, Base Form',
    'N|soort|mv|dim': 'Noun, Common, Plural, Diminutive',
    'SPEC|afgebr': 'Special Token, Truncated',
    'SPEC|afk': 'Special Token, Abbreviation',
    'SPEC|deeleigen': 'Special Token, Part Of Proper Noun',
    'SPEC|enof': 'Special Token, En / Of Word',
    'SPEC|meta': 'Special Token, Metalinguistic',
    'SPEC|symb': 'Special Token, Symbol',
    'SPEC|vreemd': 'Special Token, Foreign Word',
    TSW: 'Interjection',
    'TW|hoofd|nom|mv-n|basis': 'Numeral, Cardinal, Nominalized, Plural, Base Form',
    'TW|hoofd|nom|mv-n|dim': 'Numeral, Cardinal, Nominalized, Plural, Diminutive',
    'TW|hoofd|nom|zonder-n|basis': 'Numeral, Cardinal, Nominalized, Singular / Uncountable, Base Form',
    'TW|hoofd|nom|zonder-n|dim': 'Numeral, Cardinal, Nominalized, Singular / Uncountable, Diminutive',
    'TW|hoofd|prenom|stan': 'Numeral, Cardinal, Prenominal, Standard Case',
    'TW|hoofd|vrij': 'Numeral, Cardinal, Free / Predicative',
    'TW|rang|nom|mv-n': 'Numeral, Ordinal, Nominalized, Plural',
    'TW|rang|nom|zonder-n': 'Numeral, Ordinal, Nominalized, Singular / Uncountable',
    'TW|rang|prenom|stan': 'Numeral, Ordinal, Prenominal, Standard Case',
    'VG|neven': 'Conjunction, Coordinating',
    'VG|onder': 'Conjunction, Subordinating',
    'VNW|aanw|adv-pron|obl|vol|3o|getal':
      'Pronoun / Determiner, Demonstrative, Adverbial Pronoun, Oblique, Full / Stressed, 3rd Person Inanimate, Any Number',
    'VNW|aanw|adv-pron|stan|red|3|getal':
      'Pronoun / Determiner, Demonstrative, Adverbial Pronoun, Standard Case, Reduced / Unstressed, 3rd Person, Any Number',
    'VNW|aanw|det|dat|nom|met-e|zonder-n':
      'Pronoun / Determiner, Demonstrative, Determiner, Dative, Nominalized, Inflected (-E), Singular / Uncountable',
    'VNW|aanw|det|dat|prenom|met-e|evmo':
      'Pronoun / Determiner, Demonstrative, Determiner, Dative, Prenominal, Inflected (-E), Singular Masculine Oblique',
    'VNW|aanw|det|gen|prenom|met-e|rest3':
      'Pronoun / Determiner, Demonstrative, Determiner, Genitive, Prenominal, Inflected (-E), Remaining Genitive Form',
    'VNW|aanw|det|stan|nom|met-e|mv-n':
      'Pronoun / Determiner, Demonstrative, Determiner, Standard Case, Nominalized, Inflected (-E), Plural',
    'VNW|aanw|det|stan|nom|met-e|zonder-n':
      'Pronoun / Determiner, Demonstrative, Determiner, Standard Case, Nominalized, Inflected (-E), Singular / Uncountable',
    'VNW|aanw|det|stan|prenom|met-e|rest':
      'Pronoun / Determiner, Demonstrative, Determiner, Standard Case, Prenominal, Inflected (-E), Remaining Forms',
    'VNW|aanw|det|stan|prenom|zonder|agr':
      'Pronoun / Determiner, Demonstrative, Determiner, Standard Case, Prenominal, Uninflected, Agreement Form',
    'VNW|aanw|det|stan|prenom|zonder|evon':
      'Pronoun / Determiner, Demonstrative, Determiner, Standard Case, Prenominal, Uninflected, Singular Neuter',
    'VNW|aanw|det|stan|prenom|zonder|rest':
      'Pronoun / Determiner, Demonstrative, Determiner, Standard Case, Prenominal, Uninflected, Remaining Forms',
    'VNW|aanw|det|stan|vrij|zonder':
      'Pronoun / Determiner, Demonstrative, Determiner, Standard Case, Free / Predicative, Uninflected',
    'VNW|aanw|pron|gen|vol|3m|ev':
      'Pronoun / Determiner, Demonstrative, Pronoun, Genitive, Full / Stressed, 3rd Person Animate, Singular',
    'VNW|aanw|pron|stan|vol|3o|ev':
      'Pronoun / Determiner, Demonstrative, Pronoun, Standard Case, Full / Stressed, 3rd Person Inanimate, Singular',
    'VNW|aanw|pron|stan|vol|3|getal':
      'Pronoun / Determiner, Demonstrative, Pronoun, Standard Case, Full / Stressed, 3rd Person, Any Number',
    'VNW|betr|det|stan|nom|met-e|zonder-n':
      'Pronoun / Determiner, Relative, Determiner, Standard Case, Nominalized, Inflected (-E), Singular / Uncountable',
    'VNW|betr|det|stan|nom|zonder|zonder-n':
      'Pronoun / Determiner, Relative, Determiner, Standard Case, Nominalized, Uninflected, Singular / Uncountable',
    'VNW|betr|pron|stan|vol|3|ev':
      'Pronoun / Determiner, Relative, Pronoun, Standard Case, Full / Stressed, 3rd Person, Singular',
    'VNW|betr|pron|stan|vol|persoon|getal':
      'Pronoun / Determiner, Relative, Pronoun, Standard Case, Full / Stressed, Any Person, Any Number',
    'VNW|bez|det|gen|vol|3|ev|prenom|met-e|rest3':
      'Pronoun / Determiner, Possessive, Determiner, Genitive, Full / Stressed, 3rd Person, Singular, Prenominal, Inflected (-E), Remaining Genitive Form',
    'VNW|bez|det|gen|vol|3|ev|prenom|zonder|evmo':
      'Pronoun / Determiner, Possessive, Determiner, Genitive, Full / Stressed, 3rd Person, Singular, Prenominal, Uninflected, Singular Masculine Oblique',
    'VNW|bez|det|stan|nadr|2v|mv|prenom|zonder|agr':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Emphatic, 2nd Person Informal, Plural, Prenominal, Uninflected, Agreement Form',
    'VNW|bez|det|stan|red|1|ev|prenom|zonder|agr':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Reduced / Unstressed, 1st Person, Singular, Prenominal, Uninflected, Agreement Form',
    'VNW|bez|det|stan|red|2v|ev|prenom|zonder|agr':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Reduced / Unstressed, 2nd Person Informal, Singular, Prenominal, Uninflected, Agreement Form',
    'VNW|bez|det|stan|red|3|ev|prenom|zonder|agr':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Reduced / Unstressed, 3rd Person, Singular, Prenominal, Uninflected, Agreement Form',
    'VNW|bez|det|stan|vol|1|ev|prenom|met-e|rest':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Full / Stressed, 1st Person, Singular, Prenominal, Inflected (-E), Remaining Forms',
    'VNW|bez|det|stan|vol|1|ev|prenom|zonder|agr':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Full / Stressed, 1st Person, Singular, Prenominal, Uninflected, Agreement Form',
    'VNW|bez|det|stan|vol|1|mv|prenom|met-e|rest':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Full / Stressed, 1st Person, Plural, Prenominal, Inflected (-E), Remaining Forms',
    'VNW|bez|det|stan|vol|1|mv|prenom|zonder|evon':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Full / Stressed, 1st Person, Plural, Prenominal, Uninflected, Singular Neuter',
    'VNW|bez|det|stan|vol|2v|ev|prenom|zonder|agr':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Full / Stressed, 2nd Person Informal, Singular, Prenominal, Uninflected, Agreement Form',
    'VNW|bez|det|stan|vol|2|getal|prenom|zonder|agr':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Full / Stressed, 2nd Person, Any Number, Prenominal, Uninflected, Agreement Form',
    'VNW|bez|det|stan|vol|3m|ev|nom|met-e|mv-n':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Full / Stressed, 3rd Person Animate, Singular, Nominalized, Inflected (-E), Plural',
    'VNW|bez|det|stan|vol|3m|ev|nom|met-e|zonder-n':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Full / Stressed, 3rd Person Animate, Singular, Nominalized, Inflected (-E), Singular / Uncountable',
    'VNW|bez|det|stan|vol|3v|ev|nom|met-e|zonder-n':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Full / Stressed, 3rd Person Feminine / Animate, Singular, Nominalized, Inflected (-E), Singular / Uncountable',
    'VNW|bez|det|stan|vol|3|ev|prenom|zonder|agr':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Full / Stressed, 3rd Person, Singular, Prenominal, Uninflected, Agreement Form',
    'VNW|bez|det|stan|vol|3|mv|prenom|zonder|agr':
      'Pronoun / Determiner, Possessive, Determiner, Standard Case, Full / Stressed, 3rd Person, Plural, Prenominal, Uninflected, Agreement Form',
    'VNW|excl|pron|stan|vol|3|getal':
      'Pronoun / Determiner, Exclamative, Pronoun, Standard Case, Full / Stressed, 3rd Person, Any Number',
    'VNW|onbep|adv-pron|gen|red|3|getal':
      'Pronoun / Determiner, Indefinite, Adverbial Pronoun, Genitive, Reduced / Unstressed, 3rd Person, Any Number',
    'VNW|onbep|adv-pron|obl|vol|3o|getal':
      'Pronoun / Determiner, Indefinite, Adverbial Pronoun, Oblique, Full / Stressed, 3rd Person Inanimate, Any Number',
    'VNW|onbep|det|stan|nom|met-e|mv-n':
      'Pronoun / Determiner, Indefinite, Determiner, Standard Case, Nominalized, Inflected (-E), Plural',
    'VNW|onbep|det|stan|nom|met-e|zonder-n':
      'Pronoun / Determiner, Indefinite, Determiner, Standard Case, Nominalized, Inflected (-E), Singular / Uncountable',
    'VNW|onbep|det|stan|nom|zonder|zonder-n':
      'Pronoun / Determiner, Indefinite, Determiner, Standard Case, Nominalized, Uninflected, Singular / Uncountable',
    'VNW|onbep|det|stan|prenom|met-e|agr':
      'Pronoun / Determiner, Indefinite, Determiner, Standard Case, Prenominal, Inflected (-E), Agreement Form',
    'VNW|onbep|det|stan|prenom|met-e|evz':
      'Pronoun / Determiner, Indefinite, Determiner, Standard Case, Prenominal, Inflected (-E), Singular Common',
    'VNW|onbep|det|stan|prenom|met-e|mv':
      'Pronoun / Determiner, Indefinite, Determiner, Standard Case, Prenominal, Inflected (-E), Plural',
    'VNW|onbep|det|stan|prenom|met-e|rest':
      'Pronoun / Determiner, Indefinite, Determiner, Standard Case, Prenominal, Inflected (-E), Remaining Forms',
    'VNW|onbep|det|stan|prenom|zonder|agr':
      'Pronoun / Determiner, Indefinite, Determiner, Standard Case, Prenominal, Uninflected, Agreement Form',
    'VNW|onbep|det|stan|prenom|zonder|evon':
      'Pronoun / Determiner, Indefinite, Determiner, Standard Case, Prenominal, Uninflected, Singular Neuter',
    'VNW|onbep|det|stan|vrij|zonder':
      'Pronoun / Determiner, Indefinite, Determiner, Standard Case, Free / Predicative, Uninflected',
    'VNW|onbep|grad|stan|nom|met-e|mv-n|basis':
      'Pronoun / Determiner, Indefinite, Degree Word, Standard Case, Nominalized, Inflected (-E), Plural, Base Form',
    'VNW|onbep|grad|stan|nom|met-e|mv-n|sup':
      'Pronoun / Determiner, Indefinite, Degree Word, Standard Case, Nominalized, Inflected (-E), Plural, Superlative',
    'VNW|onbep|grad|stan|nom|met-e|zonder-n|basis':
      'Pronoun / Determiner, Indefinite, Degree Word, Standard Case, Nominalized, Inflected (-E), Singular / Uncountable, Base Form',
    'VNW|onbep|grad|stan|nom|met-e|zonder-n|sup':
      'Pronoun / Determiner, Indefinite, Degree Word, Standard Case, Nominalized, Inflected (-E), Singular / Uncountable, Superlative',
    'VNW|onbep|grad|stan|prenom|met-e|agr|basis':
      'Pronoun / Determiner, Indefinite, Degree Word, Standard Case, Prenominal, Inflected (-E), Agreement Form, Base Form',
    'VNW|onbep|grad|stan|prenom|met-e|agr|comp':
      'Pronoun / Determiner, Indefinite, Degree Word, Standard Case, Prenominal, Inflected (-E), Agreement Form, Comparative',
    'VNW|onbep|grad|stan|prenom|met-e|agr|sup':
      'Pronoun / Determiner, Indefinite, Degree Word, Standard Case, Prenominal, Inflected (-E), Agreement Form, Superlative',
    'VNW|onbep|grad|stan|prenom|met-e|mv|basis':
      'Pronoun / Determiner, Indefinite, Degree Word, Standard Case, Prenominal, Inflected (-E), Plural, Base Form',
    'VNW|onbep|grad|stan|prenom|zonder|agr|basis':
      'Pronoun / Determiner, Indefinite, Degree Word, Standard Case, Prenominal, Uninflected, Agreement Form, Base Form',
    'VNW|onbep|grad|stan|prenom|zonder|agr|comp':
      'Pronoun / Determiner, Indefinite, Degree Word, Standard Case, Prenominal, Uninflected, Agreement Form, Comparative',
    'VNW|onbep|grad|stan|vrij|zonder|basis':
      'Pronoun / Determiner, Indefinite, Degree Word, Standard Case, Free / Predicative, Uninflected, Base Form',
    'VNW|onbep|grad|stan|vrij|zonder|comp':
      'Pronoun / Determiner, Indefinite, Degree Word, Standard Case, Free / Predicative, Uninflected, Comparative',
    'VNW|onbep|grad|stan|vrij|zonder|sup':
      'Pronoun / Determiner, Indefinite, Degree Word, Standard Case, Free / Predicative, Uninflected, Superlative',
    'VNW|onbep|pron|gen|vol|3p|ev':
      'Pronoun / Determiner, Indefinite, Pronoun, Genitive, Full / Stressed, 3rd Person Animate, Singular',
    'VNW|onbep|pron|stan|vol|3o|ev':
      'Pronoun / Determiner, Indefinite, Pronoun, Standard Case, Full / Stressed, 3rd Person Inanimate, Singular',
    'VNW|onbep|pron|stan|vol|3p|ev':
      'Pronoun / Determiner, Indefinite, Pronoun, Standard Case, Full / Stressed, 3rd Person Animate, Singular',
    'VNW|pers|pron|gen|vol|2|getal':
      'Pronoun / Determiner, Personal, Pronoun, Genitive, Full / Stressed, 2nd Person, Any Number',
    'VNW|pers|pron|nomin|nadr|3m|ev|masc':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Emphatic, 3rd Person Animate, Singular, Masculine',
    'VNW|pers|pron|nomin|red|1|mv':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Reduced / Unstressed, 1st Person, Plural',
    'VNW|pers|pron|nomin|red|2v|ev':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Reduced / Unstressed, 2nd Person Informal, Singular',
    'VNW|pers|pron|nomin|red|2|getal':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Reduced / Unstressed, 2nd Person, Any Number',
    'VNW|pers|pron|nomin|red|3p|ev|masc':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Reduced / Unstressed, 3rd Person Animate, Singular, Masculine',
    'VNW|pers|pron|nomin|red|3|ev|masc':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Reduced / Unstressed, 3rd Person, Singular, Masculine',
    'VNW|pers|pron|nomin|vol|1|ev':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Full / Stressed, 1st Person, Singular',
    'VNW|pers|pron|nomin|vol|1|mv':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Full / Stressed, 1st Person, Plural',
    'VNW|pers|pron|nomin|vol|2b|getal':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Full / Stressed, 2nd Person Formal, Any Number',
    'VNW|pers|pron|nomin|vol|2v|ev':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Full / Stressed, 2nd Person Informal, Singular',
    'VNW|pers|pron|nomin|vol|2|getal':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Full / Stressed, 2nd Person, Any Number',
    'VNW|pers|pron|nomin|vol|3p|mv':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Full / Stressed, 3rd Person Animate, Plural',
    'VNW|pers|pron|nomin|vol|3v|ev|fem':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Full / Stressed, 3rd Person Feminine / Animate, Singular, Feminine',
    'VNW|pers|pron|nomin|vol|3|ev|masc':
      'Pronoun / Determiner, Personal, Pronoun, Nominative, Full / Stressed, 3rd Person, Singular, Masculine',
    'VNW|pers|pron|obl|nadr|3m|ev|masc':
      'Pronoun / Determiner, Personal, Pronoun, Oblique, Emphatic, 3rd Person Animate, Singular, Masculine',
    'VNW|pers|pron|obl|nadr|3v|getal|fem':
      'Pronoun / Determiner, Personal, Pronoun, Oblique, Emphatic, 3rd Person Feminine / Animate, Any Number, Feminine',
    'VNW|pers|pron|obl|red|3|ev|masc':
      'Pronoun / Determiner, Personal, Pronoun, Oblique, Reduced / Unstressed, 3rd Person, Singular, Masculine',
    'VNW|pers|pron|obl|vol|2v|ev':
      'Pronoun / Determiner, Personal, Pronoun, Oblique, Full / Stressed, 2nd Person Informal, Singular',
    'VNW|pers|pron|obl|vol|3p|mv':
      'Pronoun / Determiner, Personal, Pronoun, Oblique, Full / Stressed, 3rd Person Animate, Plural',
    'VNW|pers|pron|obl|vol|3|ev|masc':
      'Pronoun / Determiner, Personal, Pronoun, Oblique, Full / Stressed, 3rd Person, Singular, Masculine',
    'VNW|pers|pron|obl|vol|3|getal|fem':
      'Pronoun / Determiner, Personal, Pronoun, Oblique, Full / Stressed, 3rd Person, Any Number, Feminine',
    'VNW|pers|pron|stan|nadr|2v|mv':
      'Pronoun / Determiner, Personal, Pronoun, Standard Case, Emphatic, 2nd Person Informal, Plural',
    'VNW|pers|pron|stan|red|3|ev|fem':
      'Pronoun / Determiner, Personal, Pronoun, Standard Case, Reduced / Unstressed, 3rd Person, Singular, Feminine',
    'VNW|pers|pron|stan|red|3|ev|onz':
      'Pronoun / Determiner, Personal, Pronoun, Standard Case, Reduced / Unstressed, 3rd Person, Singular, Neuter',
    'VNW|pers|pron|stan|red|3|mv':
      'Pronoun / Determiner, Personal, Pronoun, Standard Case, Reduced / Unstressed, 3rd Person, Plural',
    'VNW|pr|pron|obl|nadr|1|ev':
      'Pronoun / Determiner, Prepositional Reflexive, Pronoun, Oblique, Emphatic, 1st Person, Singular',
    'VNW|pr|pron|obl|nadr|1|mv':
      'Pronoun / Determiner, Prepositional Reflexive, Pronoun, Oblique, Emphatic, 1st Person, Plural',
    'VNW|pr|pron|obl|nadr|2v|getal':
      'Pronoun / Determiner, Prepositional Reflexive, Pronoun, Oblique, Emphatic, 2nd Person Informal, Any Number',
    'VNW|pr|pron|obl|nadr|2|getal':
      'Pronoun / Determiner, Prepositional Reflexive, Pronoun, Oblique, Emphatic, 2nd Person, Any Number',
    'VNW|pr|pron|obl|red|1|ev':
      'Pronoun / Determiner, Prepositional Reflexive, Pronoun, Oblique, Reduced / Unstressed, 1st Person, Singular',
    'VNW|pr|pron|obl|red|2v|getal':
      'Pronoun / Determiner, Prepositional Reflexive, Pronoun, Oblique, Reduced / Unstressed, 2nd Person Informal, Any Number',
    'VNW|pr|pron|obl|vol|1|ev':
      'Pronoun / Determiner, Prepositional Reflexive, Pronoun, Oblique, Full / Stressed, 1st Person, Singular',
    'VNW|pr|pron|obl|vol|1|mv':
      'Pronoun / Determiner, Prepositional Reflexive, Pronoun, Oblique, Full / Stressed, 1st Person, Plural',
    'VNW|pr|pron|obl|vol|2|getal':
      'Pronoun / Determiner, Prepositional Reflexive, Pronoun, Oblique, Full / Stressed, 2nd Person, Any Number',
    'VNW|recip|pron|gen|vol|persoon|mv':
      'Pronoun / Determiner, Reciprocal, Pronoun, Genitive, Full / Stressed, Any Person, Plural',
    'VNW|recip|pron|obl|vol|persoon|mv':
      'Pronoun / Determiner, Reciprocal, Pronoun, Oblique, Full / Stressed, Any Person, Plural',
    'VNW|refl|pron|obl|nadr|3|getal':
      'Pronoun / Determiner, Reflexive, Pronoun, Oblique, Emphatic, 3rd Person, Any Number',
    'VNW|refl|pron|obl|red|3|getal':
      'Pronoun / Determiner, Reflexive, Pronoun, Oblique, Reduced / Unstressed, 3rd Person, Any Number',
    'VNW|vb|adv-pron|obl|vol|3o|getal':
      'Pronoun / Determiner, Interrogative / Exclamative, Adverbial Pronoun, Oblique, Full / Stressed, 3rd Person Inanimate, Any Number',
    'VNW|vb|det|stan|nom|met-e|zonder-n':
      'Pronoun / Determiner, Interrogative / Exclamative, Determiner, Standard Case, Nominalized, Inflected (-E), Singular / Uncountable',
    'VNW|vb|det|stan|prenom|met-e|rest':
      'Pronoun / Determiner, Interrogative / Exclamative, Determiner, Standard Case, Prenominal, Inflected (-E), Remaining Forms',
    'VNW|vb|det|stan|prenom|zonder|evon':
      'Pronoun / Determiner, Interrogative / Exclamative, Determiner, Standard Case, Prenominal, Uninflected, Singular Neuter',
    'VNW|vb|pron|gen|vol|3m|ev':
      'Pronoun / Determiner, Interrogative / Exclamative, Pronoun, Genitive, Full / Stressed, 3rd Person Animate, Singular',
    'VNW|vb|pron|gen|vol|3p|mv':
      'Pronoun / Determiner, Interrogative / Exclamative, Pronoun, Genitive, Full / Stressed, 3rd Person Animate, Plural',
    'VNW|vb|pron|gen|vol|3v|ev':
      'Pronoun / Determiner, Interrogative / Exclamative, Pronoun, Genitive, Full / Stressed, 3rd Person Feminine / Animate, Singular',
    'VNW|vb|pron|stan|vol|3o|ev':
      'Pronoun / Determiner, Interrogative / Exclamative, Pronoun, Standard Case, Full / Stressed, 3rd Person Inanimate, Singular',
    'VNW|vb|pron|stan|vol|3p|getal':
      'Pronoun / Determiner, Interrogative / Exclamative, Pronoun, Standard Case, Full / Stressed, 3rd Person Animate, Any Number',
    'VZ|fin': 'Adposition, Postposition',
    'VZ|init': 'Adposition, Preposition',
    'VZ|versm': 'Adposition, Fused Preposition',
    'WW|inf|nom|zonder|zonder-n': 'Verb, Infinitive, Nominalized, Uninflected, Singular / Uncountable',
    'WW|inf|prenom|met-e': 'Verb, Infinitive, Prenominal, Inflected (-E)',
    'WW|inf|prenom|zonder': 'Verb, Infinitive, Prenominal, Uninflected',
    'WW|inf|vrij|zonder': 'Verb, Infinitive, Free / Predicative, Uninflected',
    'WW|od|nom|met-e|mv-n': 'Verb, Present Participle, Nominalized, Inflected (-E), Plural',
    'WW|od|nom|met-e|zonder-n':
      'Verb, Present Participle, Nominalized, Inflected (-E), Singular / Uncountable',
    'WW|od|prenom|met-e': 'Verb, Present Participle, Prenominal, Inflected (-E)',
    'WW|od|prenom|zonder': 'Verb, Present Participle, Prenominal, Uninflected',
    'WW|od|vrij|zonder': 'Verb, Present Participle, Free / Predicative, Uninflected',
    'WW|pv|conj|ev': 'Verb, Finite, Subjunctive, Singular',
    'WW|pv|tgw|ev': 'Verb, Finite, Present Tense, Singular',
    'WW|pv|tgw|met-t': 'Verb, Finite, Present Tense, Formal T-Form',
    'WW|pv|tgw|mv': 'Verb, Finite, Present Tense, Plural',
    'WW|pv|verl|ev': 'Verb, Finite, Past Tense, Singular',
    'WW|pv|verl|mv': 'Verb, Finite, Past Tense, Plural',
    'WW|vd|nom|met-e|mv-n': 'Verb, Past Participle, Nominalized, Inflected (-E), Plural',
    'WW|vd|nom|met-e|zonder-n': 'Verb, Past Participle, Nominalized, Inflected (-E), Singular / Uncountable',
    'WW|vd|prenom|met-e': 'Verb, Past Participle, Prenominal, Inflected (-E)',
    'WW|vd|prenom|zonder': 'Verb, Past Participle, Prenominal, Uninflected',
    'WW|vd|vrij|zonder': 'Verb, Past Participle, Free / Predicative, Uninflected'
  };
  return true;
}
