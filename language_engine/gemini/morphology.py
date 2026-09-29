"""Gemini morphology service."""

LANGS_REQUIRING_ROMANIZATION: frozenset[str] = frozenset(
    {
        "zh",
        "lzh",
        "ja",
        "ko",
        "th",
        "ar",
        "fa",
        "ur",
        "hi",
        "ta",
        "bn",
        "pa",
        "he",
        "hbo",
        "hy",
        "ru",
        "el",
        "grc",
    }
)


LANGS_WITH_MORPHOLOGY: dict[str, frozenset[str]] = {
    # European / classical — full-blown inflection
    "la": frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "grc": frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "el": frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "ang": frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "ru": frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "de": frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "PROPN", "VERB"}),
    "nl": frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "PROPN", "VERB"}),
    "fr": frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "VERB"}),
    "it": frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "VERB"}),
    "es": frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "VERB"}),
    "pt": frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "VERB"}),
    # Celtic / Semitic / Indo-Iranian / Armenian / Turkic
    "ga": frozenset(
        {"ADJ", "ADP", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}
    ),
    "ar": frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "he": frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "VERB"}),
    "hbo": frozenset({"ADJ", "AUX", "NOUN", "PRON", "VERB"}),
    "fa": frozenset({"AUX", "NOUN", "PRON", "VERB"}),
    "ur": frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "PROPN", "VERB"}),
    "hi": frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "PROPN", "VERB"}),
    "sa": frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "ta": frozenset({"AUX", "NOUN", "PRON", "PROPN", "VERB"}),
    "bn": frozenset({"ADJ", "AUX", "NOUN", "PRON", "PROPN", "VERB"}),
    "pa": frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "PROPN", "VERB"}),
    "hy": frozenset({"ADJ", "ADP", "AUX", "DET", "NOUN", "PRON", "PROPN", "VERB"}),
    "tr": frozenset({"AUX", "NOUN", "PRON", "PROPN", "VERB"}),
    # East Asian / Southeast Asian / African — narrow or none
    "ko": frozenset({"ADJ", "AUX", "VERB"}),
    "ja": frozenset({"ADJ", "AUX", "VERB"}),
    "id": frozenset({"VERB"}),
    "tl": frozenset({"PRON", "VERB"}),
    "sw": frozenset({"ADJ", "DET", "NOUN", "NUM", "PRON", "VERB"}),
    # Fully isolating — no entry needed but listed for clarity (empty set)
    "zh": frozenset(),
    "lzh": frozenset(),
    "vi": frozenset(),
    "th": frozenset(),
}


def _requires_romanization(lang_code: str) -> bool:
    return (lang_code or "").strip().lower() in LANGS_REQUIRING_ROMANIZATION


def _upos_inflects(lang_code: str, upos: str) -> bool:
    """True if `upos` is in this language's inflecting UPOS set."""
    code = (lang_code or "").strip().lower()
    tag = (upos or "").strip().upper()
    if not code or not tag:
        return False
    return tag in LANGS_WITH_MORPHOLOGY.get(code, frozenset())


_INFLECTIONAL_FEATURE_KEYS: frozenset[str] = frozenset(
    {
        # User-specified core UD inflectional features
        "Gender",
        "VerbForm",
        "Animacy",
        "Mood",
        "NounClass",
        "Tense",
        "Number",
        "Aspect",
        "Case",
        "Voice",
        "Definite",
        "Evident",
        "Deixis",
        "Polarity",
        "DeixisRef",
        "Person",
        "Degree",
        "Polite",
        "Clusivity",
        # Additional inflectional features present in TRANKIT_TAGS.js FEATS
        "Clitic",
        "Connegative",
        "Form",
        "Formation",
        "HebBinyan",
        "InfForm",
        "Poss",
        "PrepCase",
        "PrepForm",
        "Reflex",
        # Agreement-target noun class/number/person/gender (e.g. ObjNumber,
        # RelPerson, ObjNounClass) — Bantu / Semitic / Celtic agreement markers
        "ObjNumber",
        "ObjPerson",
        "ObjNounClass",
        "RelNumber",
        "RelPerson",
        "RelNounClass",
    }
)


def _trankit_requires_morph(
    surface: str, lemma_hint: str, feats: str, lang_code: str = ""
) -> bool:
    """Decide whether Gemini should lemmatize / give morph analysis.

    Returns True only when Trankit reported at least one inflectional feature
    from `_INFLECTIONAL_FEATURE_KEYS`.
    Bracketed agreement variants like `Number[psor]` are normalized by
    stripping the `[...]` suffix before comparison.
    """
    feats_str = (feats or "").strip()
    is_sanskrit = (lang_code or "").strip().lower() in ("sa", "sanskrit")
    if feats_str and feats_str != "_":
        for part in feats_str.split("|"):
            key, _, val = part.partition("=")
            key = key.strip()
            # Sanskrit Case=Compound marks a bare compound stem — not an inflected form.
            if (
                is_sanskrit
                and key.lower() == "case"
                and val.strip().lower() == "compound"
            ):
                continue
            # Strip bracketed agreement suffix: Number[psor] -> Number
            bracket = key.find("[")
            if bracket > 0:
                key = key[:bracket]
            if key in _INFLECTIONAL_FEATURE_KEYS:
                return True
    return False


_POS_ENUM = [
    "noun",
    "verb",
    "adj",
    "adv",
    "pron",
    "det",
    "num",
    "conj",
    "prep",
    "postp",
    "particle",
    "intj",
    "suffix",
    "prefix",
    "name",
    "phrase",
]
