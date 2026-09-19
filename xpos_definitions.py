"""
Language-scoped XPOS description registry.

Keep fine-grained POS definitions outside frontend bundles so each language
can request its own set from the backend.
"""

from __future__ import annotations

from typing import Dict

from language_registry import resolve_lang_code


ZH_XPOS_DESCRIPTIONS: Dict[str, str] = {
    "ADD": "Unclear/rare miscellaneous tag",
    "AS": "Aspect marker particle",
    "BB": "Disposal/passive marker",
    "CC": "Coordinating conjunction",
    "CD": "Numeral/number",
    "DEC": "Attributive particle (de-type)",
    "DEV": "Adverbial particle (di-type)",
    "DT": "Determiner",
    "EC": "List-separator punctuation",
    "FW": "Foreign word",
    "HYPH": "Hyphen/dash",
    "IN": "Preposition/subordinator",
    "JJ": "Adjective",
    "MD": "Modal auxiliary",
    "NN": "Common noun",
    "NNB": "Unit/measure/classifier noun",
    "NNP": "Proper noun",
    "PFA": "Prefix",
    "PRD": "Demonstrative/reflexive pronoun",
    "PRP": "Personal pronoun",
    "RB": "Adverb",
    "SFA": "Adjective-forming suffix",
    "SFN": "Noun-forming suffix",
    "SFV": "Verb-forming suffix",
    "UH": "Particle/interjection",
    "VC": "Copula verb",
    "VV": "Lexical verb",
    "WP": "Wh-word",
}


JA_XPOS_DESCRIPTIONS: Dict[str, str] = {
    "NN": "Common noun / general lexical noun",
    "NNP": "Proper noun / named entity",
    "CD": "Numeral / numeric token",
    "NP": "Pronoun / pronominal demonstrative",
    "VV": "Main lexical verb (content verb)",
    "AV": "Inflectional auxiliary verb fragment (tense, aspect, voice, politeness, negation, copular elements)",
    "XV": "Verbalizer / derivational verb fragment (light-verb or verb-forming element)",
    "XA": "Existential or support verb used in auxiliary function",
    "JJ": "Inflecting adjective form (including inflected and adverbial forms)",
    "JN": "Adjectival noun stem / nominal modifier",
    "JR": "Prenominal determiner / attributive determiner",
    "RB": "Adverb",
    "CC": "Conjunction / discourse connective",
    "UH": "Interjection",
    "PS": "Simple case particle / postposition",
    "PK": "Topic, focus, or contrast particle",
    "PC": "Clause-linking or subordinating particle",
    "PA": "Adverbial, degree, or limiting particle",
    "PNB": "Nominalizer (clause-to-noun marker)",
    "PE": "Sentence-final particle (non-question)",
    "PM": "Core genitive linker particle",
    "PQ": "Quotative marker / complementizer",
    "PH": "Listing or coordination marker",
    "PP": "Compound postposition (canonical multiword postpositional expression)",
    "PN": "Possessive or genitive bound form",
    "PF": "Sentence-final question marker",
    "XP": "Bound prefix element in compound (pre-nominal prefix)",
    "XS": "Bound suffix element in compound (compound-forming nominal suffix)",
    "XSC": "Counter, unit, or classifier suffix",
    "XPC": "Number or date modifier / numeric connector element",
    "PX": "Fixed postposition-like expression or adpositional chunk",
    "SYM": "Symbol, punctuation, or non-lexical mark",
    "UNK": "Unknown, residual, or out-of-vocabulary token",
    "_": "Null or placeholder (no tag assigned)",
    "AJ": "Dependent adjectival element (derivational adjective fragment)",
    "AJN": "Adjectival-noun suffix (adjective-like nominal suffix)",
    "NR": "Temporal or sequence noun used adverbially",
    "NB": "Bound or formal noun (abstract wrapper noun)",
}


KO_XPOS_DESCRIPTIONS: Dict[str, str] = {
    # --- Nouns (n-) ---
    "NCN": "Common noun",
    "NCPA": "Action noun (하다-verb stem)",
    "NCPS": "State noun (하다-adj stem)",
    "NBN": "Bound (dependent) noun",
    "NBU": "Unit / counter noun",
    "NNC": "Cardinal number",
    "NNO": "Native / ordinal number",
    "NPD": "Demonstrative pronoun",
    "NPP": "Personal pronoun",
    "NQ": "Proper noun",
    # --- Predicates (p-) ---
    "PVG": "Verb",
    "PVD": "Verb (variant / defective)",
    "PAA": "Descriptive verb (adjective)",
    "PAD": "Adnominal adjective",
    "PX": "Auxiliary predicate",
    # --- Endings (e-) ---
    "ECC": "Coordinating connective ending",
    "ECS": "Subordinating connective ending",
    "ECX": "Auxiliary connective ending",
    "EF": "Sentence-final ending",
    "EP": "Pre-final ending (tense / honorific)",
    "ETM": "Adnominalizing ending",
    "ETN": "Nominalizing ending",
    # --- Particles / postpositions (j-) ---
    "JCA": "Adverbial case particle",
    "JCC": "Complement case particle",
    "JCJ": "Conjunctive particle",
    "JCM": "Adnominal case particle (genitive)",
    "JCO": "Object case particle",
    "JCR": "Quotative case particle",
    "JCS": "Subject case particle",
    "JCT": "Locative / directional particle",
    "JP": "Copula (이다)",
    "JCV": "Vocative case particle",
    "JXC": "Delimiter particle (까지, 부터, …)",
    "JXF": "Focus / special particle",
    "JXT": "Topic particle (은/는)",
    # --- Adverbs (ma-) ---
    "MAD": "Demonstrative adverb",
    "MAG": "General adverb",
    "MAJ": "Conjunctive adverb",
    # --- Determiners (mm-) ---
    "MMA": "Attributive determiner",
    "MMD": "Demonstrative determiner",
    # --- Derivational affixes (x-) ---
    "XP": "Prefix",
    "XSA": "Adjective-deriving suffix",
    "XSM": "Adverb-deriving suffix",
    "XSN": "Noun-deriving suffix",
    "XSV": "Verb-deriving suffix",
    # --- Punctuation / symbols (s-) ---
    "SF": "Sentence-final punctuation",
    "SL": "Left bracket / parenthesis",
    "SP": "Comma / separator",
    "SR": "Right bracket / parenthesis",
    "SU": "Symbol / unknown punctuation",
    # --- Interjection ---
    "II": "Interjection",
    # --- Other ---
    "F": "Foreign word",
    "_": "Null / no tag assigned",
}

LZH_XPOS_DESCRIPTIONS: Dict[str, str] = {
    # --- Nouns: n,名詞 ---
    "n,名詞,不可譲,属性": "Noun: inalienable attribute",
    "n,名詞,不可譲,疾病": "Noun: inalienable / disease",
    "n,名詞,不可譲,身体": "Noun: inalienable / body part",
    "n,名詞,主体,動物": "Noun: entity / animal",
    "n,名詞,主体,国名": "Noun: entity / country name",
    "n,名詞,主体,書物": "Noun: entity / book or text",
    "n,名詞,主体,機関": "Noun: entity / institution",
    "n,名詞,主体,集団": "Noun: entity / group or collective",
    "n,名詞,人,その他の人名": "Noun: person / other personal name",
    "n,名詞,人,人": "Noun: person (general)",
    "n,名詞,人,名": "Noun: person / given name",
    "n,名詞,人,姓氏": "Noun: person / surname",
    "n,名詞,人,役割": "Noun: person / role or title",
    "n,名詞,人,複合的人名": "Noun: person / compound name",
    "n,名詞,人,関係": "Noun: person / relationship",
    "n,名詞,制度,儀礼": "Noun: institution / ritual or ceremony",
    "n,名詞,制度,場": "Noun: institution / place or venue",
    "n,名詞,可搬,乗り物": "Noun: portable / vehicle",
    "n,名詞,可搬,伝達": "Noun: portable / communication tool",
    "n,名詞,可搬,成果物": "Noun: portable / product or artifact",
    "n,名詞,可搬,糧食": "Noun: portable / food or provisions",
    "n,名詞,可搬,道具": "Noun: portable / tool or implement",
    "n,名詞,固定物,地名": "Noun: fixed / place name",
    "n,名詞,固定物,地形": "Noun: fixed / terrain or landform",
    "n,名詞,固定物,建造物": "Noun: fixed / building or structure",
    "n,名詞,固定物,樹木": "Noun: fixed / tree or plant",
    "n,名詞,固定物,関係": "Noun: fixed / spatial relation",
    "n,名詞,天象,天文": "Noun: celestial / astronomy",
    "n,名詞,天象,怪異": "Noun: celestial / omen or anomaly",
    "n,名詞,天象,気象": "Noun: celestial / weather",
    "n,名詞,度量衡,*": "Noun: measurement or unit",
    "n,名詞,思考,*": "Noun: thought or concept",
    "n,名詞,描写,形質": "Noun: description / quality or form",
    "n,名詞,描写,態度": "Noun: description / attitude",
    "n,名詞,数量,*": "Noun: quantity",
    "n,名詞,時,*": "Noun: time or temporal",
    "n,名詞,行為,*": "Noun: action or conduct",
    # --- Pronouns: n,代名詞 ---
    "n,代名詞,人称,他": "Pronoun: third person",
    "n,代名詞,人称,止格": "Pronoun: objective case",
    "n,代名詞,人称,起格": "Pronoun: nominative case",
    "n,代名詞,指示,*": "Pronoun: demonstrative",
    "n,代名詞,疑問,*": "Pronoun: interrogative",
    # --- Numerals: n,数詞 ---
    "n,数詞,数,*": "Numeral (number word)",
    "n,数詞,数字,*": "Numeral (digit)",
    # --- Particles: p,助詞 ---
    "p,助詞,句末,*": "Particle: sentence-final",
    "p,助詞,句頭,*": "Particle: sentence-initial",
    "p,助詞,接続,並列": "Particle: conjunctive / coordinate",
    "p,助詞,接続,体言化": "Particle: conjunctive / nominalizer",
    "p,助詞,接続,属格": "Particle: conjunctive / genitive",
    "p,助詞,提示,*": "Particle: topic or focus marker",
    # --- Interjections ---
    "p,感嘆詞,*,*": "Interjection",
    # --- Suffixes ---
    "p,接尾辞,*,*": "Suffix",
    # --- Symbols ---
    "s,記号,一般,*": "Symbol (general)",
    # --- Prepositions: v,前置詞 ---
    "v,前置詞,基盤,*": "Preposition: basis or foundation",
    "v,前置詞,源泉,*": "Preposition: source or origin",
    "v,前置詞,経由,*": "Preposition: via or through",
    "v,前置詞,関係,*": "Preposition: relation",
    # --- Adverbs: v,副詞 ---
    "v,副詞,判断,推定": "Adverb: judgment / presumption",
    "v,副詞,判断,確定": "Adverb: judgment / certainty",
    "v,副詞,判断,逆接": "Adverb: judgment / concessive",
    "v,副詞,否定,体言否定": "Adverb: negation / nominal negation",
    "v,副詞,否定,有界": "Adverb: negation / bounded",
    "v,副詞,否定,無界": "Adverb: negation / unbounded",
    "v,副詞,否定,禁止": "Adverb: negation / prohibitive",
    "v,副詞,描写,*": "Adverb: descriptive / manner",
    "v,副詞,時相,変化": "Adverb: aspect / change",
    "v,副詞,時相,完了": "Adverb: aspect / completion",
    "v,副詞,時相,将来": "Adverb: aspect / future",
    "v,副詞,時相,恒常": "Adverb: aspect / habitual",
    "v,副詞,時相,現在": "Adverb: aspect / present",
    "v,副詞,時相,終局": "Adverb: aspect / finality",
    "v,副詞,時相,緊接": "Adverb: aspect / immediate succession",
    "v,副詞,時相,過去": "Adverb: aspect / past",
    "v,副詞,疑問,原因": "Adverb: interrogative / reason",
    "v,副詞,疑問,反語": "Adverb: interrogative / rhetorical",
    "v,副詞,疑問,所在": "Adverb: interrogative / location",
    "v,副詞,程度,やや高度": "Adverb: degree / moderately high",
    "v,副詞,程度,極度": "Adverb: degree / extreme",
    "v,副詞,範囲,共同": "Adverb: scope / collective",
    "v,副詞,範囲,総括": "Adverb: scope / comprehensive",
    "v,副詞,範囲,限定": "Adverb: scope / restrictive",
    "v,副詞,頻度,偶発": "Adverb: frequency / occasional",
    "v,副詞,頻度,重複": "Adverb: frequency / repeated",
    "v,副詞,頻度,頻繁": "Adverb: frequency / frequent",
    # --- Auxiliary verbs: v,助動詞 ---
    "v,助動詞,受動,*": "Auxiliary verb: passive",
    "v,助動詞,可能,*": "Auxiliary verb: potential or ability",
    "v,助動詞,必要,*": "Auxiliary verb: necessity",
    "v,助動詞,願望,*": "Auxiliary verb: wish or desire",
    # --- Verbs: v,動詞 ---
    "v,動詞,変化,制度": "Verb: change / institutional",
    "v,動詞,変化,性質": "Verb: change / quality or nature",
    "v,動詞,変化,生物": "Verb: change / biological",
    "v,動詞,存在,存在": "Verb: existence",
    "v,動詞,描写,境遇": "Verb: description / circumstance",
    "v,動詞,描写,形質": "Verb: description / form or quality",
    "v,動詞,描写,態度": "Verb: description / attitude",
    "v,動詞,描写,量": "Verb: description / quantity",
    "v,動詞,行為,交流": "Verb: action / exchange or interaction",
    "v,動詞,行為,伝達": "Verb: action / communication",
    "v,動詞,行為,使役": "Verb: action / causative",
    "v,動詞,行為,儀礼": "Verb: action / ritual or ceremony",
    "v,動詞,行為,分類": "Verb: action / classification",
    "v,動詞,行為,動作": "Verb: action / motion",
    "v,動詞,行為,姿勢": "Verb: action / posture",
    "v,動詞,行為,役割": "Verb: action / role or function",
    "v,動詞,行為,得失": "Verb: action / gain or loss",
    "v,動詞,行為,態度": "Verb: action / attitude or manner",
    "v,動詞,行為,生産": "Verb: action / production",
    "v,動詞,行為,移動": "Verb: action / movement",
    "v,動詞,行為,設置": "Verb: action / establishment",
    "v,動詞,行為,飲食": "Verb: action / eating and drinking",
    # --- Null ---
    "_": "Null / no tag assigned",
}


VI_XPOS_DESCRIPTIONS: Dict[str, str] = {
    # --- Nouns ---
    "N": "Common noun",
    "Np": "Proper noun",
    "Nc": "Classifier noun",
    "Nu": "Unit noun",
    "Nb": "Abbreviated noun",
    "Ny": "Nominal abbreviation",
    # --- Verbs ---
    "V": "Verb",
    # --- Adjectives ---
    "A": "Adjective",
    # --- Pronouns ---
    "P": "Pronoun",
    # --- Adverbs ---
    "R": "Adverb",
    # --- Determiners ---
    "L": "Determiner",
    # --- Numerals ---
    "M": "Numeral",
    # --- Prepositions ---
    "E": "Preposition",
    # --- Conjunctions ---
    "C": "Subordinating conjunction",
    "CC": "Coordinating conjunction",
    # --- Interjections ---
    "I": "Interjection",
    # --- Particles ---
    "T": "Particle / auxiliary word",
    # --- Affixes ---
    "S": "Affix",
    # --- Abbreviations ---
    "Y": "Abbreviation",
    # --- Punctuation ---
    "CH": "Punctuation",
    # --- Other ---
    "X": "Other / unknown",
    "_": "Null / no tag assigned",
}


_XPOS_DESCRIPTIONS_BY_LANG: Dict[str, Dict[str, str]] = {
    "zh": ZH_XPOS_DESCRIPTIONS,
    "ja": JA_XPOS_DESCRIPTIONS,
    "ko": KO_XPOS_DESCRIPTIONS,
    "vi": VI_XPOS_DESCRIPTIONS,
    "lzh": LZH_XPOS_DESCRIPTIONS,
}


def normalize_xpos_lang_code(raw_lang: str) -> str:
    """Normalize raw language input to a base code used by this registry."""
    lang = str(raw_lang or "").strip().lower()
    if not lang:
        return ""

    resolved = resolve_lang_code(lang)
    if resolved:
        return resolved

    if "-" in lang:
        base = lang.split("-", 1)[0]
        resolved_base = resolve_lang_code(base)
        return resolved_base or base

    return lang


def get_xpos_descriptions(lang: str) -> Dict[str, str]:
    """Return a copy of the XPOS description map for a language code."""
    code = normalize_xpos_lang_code(lang)
    desc = _XPOS_DESCRIPTIONS_BY_LANG.get(code)
    if not desc:
        return {}
    return dict(desc)


def get_supported_xpos_languages():
    """Return supported language codes for XPOS descriptions."""
    return sorted(_XPOS_DESCRIPTIONS_BY_LANG.keys())
