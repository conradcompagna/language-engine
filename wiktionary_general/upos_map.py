"""
UPOS -> Kaikki POS mapping for Wiktionary general pipeline languages.

Maps Universal POS (UPOS) tags from Trankit to the Kaikki dictionary
``pos_raw`` values that are semantically compatible. Used for entry-level
filtering so only relevant dictionary entries are shown for a given
grammatical context.

All 8 target languages use the same UPOS tagset (it's universal), but
their Kaikki dictionaries contain slightly different POS inventories.
The mapping is shared because the UPOS->Kaikki relationship is constant
across languages — what varies is which Kaikki POS values actually appear.

Standard UPOS tags (17 tags):
  ADJ, ADP, ADV, AUX, CCONJ, DET, INTJ, NOUN, NUM,
  PART, PRON, PROPN, PUNCT, SCONJ, SYM, VERB, X

Languages: Turkish (tr), Tamil (ta), Telugu (te), Persian (fa),
           Marathi (mr), Indonesian (id), Hindi (hi), Arabic (ar)
"""

from __future__ import annotations
from typing import Dict, FrozenSet, List


# ---------------------------------------------------------------------------
# Universal UPOS -> Kaikki POS mapping
# ---------------------------------------------------------------------------
# This mapping is the same for all Wiktionary general pipeline languages.
# The Kaikki POS values are drawn from the union of all 8 target language
# dictionaries.

_UPOS_TO_KAIKKI_POS: Dict[str, List[str]] = {
    # Content words
    "NOUN":  ["noun", "classifier", "name", "contraction"],
    "VERB":  ["verb"],
    "ADJ":   ["adj"],
    "ADV":   ["adv"],

    # Proper nouns
    "PROPN": ["name", "noun"],

    # Function words
    "ADP":   ["prep", "postp", "prep_phrase"],
    "AUX":   ["verb"],   # auxiliaries are verbs in Kaikki
    "CCONJ": ["conj"],
    "SCONJ": ["conj"],
    "DET":   ["det", "article"],
    "PRON":  ["pron"],
    "NUM":   ["num"],
    "PART":  ["particle"],
    "INTJ":  ["intj"],

    # Classifiers (function like nouns in many languages)
    # No direct UPOS equivalent — mapped via NOUN
    # "classifier" is also added to the NOUN mapping below

    # Structural
    "PUNCT": ["punct", "symbol"],
    "SYM":   ["symbol", "punct"],
    "X":     [],   # no filtering for unknown/foreign
}

# Language-specific additions layered on top of the shared UPOS mapping.
# Japanese Kaikki data encodes many conjugational morphemes (e.g. -て, -た)
# as suffix entries, so allow those analyses in the buckets Trankit commonly
# uses for those tokens.
_LANGUAGE_UPOS_TO_KAIKKI_POS: Dict[str, Dict[str, List[str]]] = {
    "ja": {
        "CCONJ": ["suffix"],
        "SCONJ": ["suffix"],
    },
    "lzh": {
        # Classical Chinese cnotes data includes productive affix-style rows
        # normalized to Kaikki POS tags. Treat them as particle-like analyses
        # when a syntactic hint is available.
        "PART": ["prefix", "suffix", "infix"],
    },
}


# POS values that are always filter-exempt: they bypass UPOS gating and
# always remain in the primary bucket, never filtered out.
_FILTER_EXEMPT_POS: FrozenSet[str] = frozenset({
    "proverb", "phrase", "prep_phrase",
})

# POS values that are relegated to the secondary bucket by default.
_ALWAYS_FILTERED_POS: FrozenSet[str] = frozenset({
    "character",
    "romanization",
    "root",
    "syllable",
    "punct",
    "symbol",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_upos_to_kaikki_pos(lang_code: str = "") -> Dict[str, List[str]]:
    """Return the UPOS->Kaikki POS mapping for a language.

    Most languages use the shared mapping unchanged; selected languages add
    small overrides for dictionary-specific POS inventories.
    """
    lang = str(lang_code or "").strip().lower()
    mapping = {upos: list(pos_list) for upos, pos_list in _UPOS_TO_KAIKKI_POS.items()}
    for upos, extra_pos in _LANGUAGE_UPOS_TO_KAIKKI_POS.get(lang, {}).items():
        bucket = mapping.setdefault(str(upos or "").upper(), [])
        for pos in extra_pos:
            pos_text = str(pos or "").strip()
            if pos_text and pos_text not in bucket:
                bucket.append(pos_text)
    return mapping


def get_filter_exempt_pos(lang_code: str = "") -> FrozenSet[str]:
    """Return POS values that bypass UPOS filtering."""
    return _FILTER_EXEMPT_POS


def get_always_filtered_pos(lang_code: str = "") -> FrozenSet[str]:
    """Return POS values that are always relegated to secondary."""
    return _ALWAYS_FILTERED_POS
