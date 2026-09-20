#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jp_inflection_table_analyzer.py

Standalone, rules-based Japanese inflection analyzer for (surface, lemma) pairs.

Goal: given a token where surface != lemma, identify WHICH inflection/derivation
the surface is, relative to the lemma, using a fixed comprehensive rule table.
Routes tokens through specific pipelines based on JMDict POS tags to ensure accuracy.

Coverage (modern Japanese):
- Verbs: godan / ichidan / irregular (する/来る)
  base inflections + negative + past + te + conditional + imperative + volitional
  polite (ます/ません/ました/ませんでした/ましょう)
  aspect/conditional (たら/たり)
  passive / causative / potential (including ra-nuki) / causative-passive
  desiderative (たい) linked to i-adj inflections
  classical negatives: ず / ぬ
- i-adjectives, na-adjectives, copula (だ/です)
- Common special-cases: ある negative = ない, 行く te/ta = って/った

CLI usage examples:
  python jp_inflection_table_analyzer.py --surface 行って --lemma 行く --pos v5k-s
  python jp_inflection_table_analyzer.py --surface 食べたくなかった --lemma 食べる --pos v1 --json
  python jp_inflection_table_analyzer.py --tokens-json tokens.json --json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple, Iterable, Any


# ------------------------------
# Data structures
# ------------------------------

@dataclass(frozen=True)
class Analysis:
    surface: str
    lemma: str
    category: str              # verb / i-adj / na-adj / copula / unknown
    derivation: Tuple[str, ...]  # e.g., ("Passive", "TeIru", "Past") or ("Conjunctive",)
    features: Dict[str, Any]   # normalized features
    description: str           # short English description


# ------------------------------
# Kana row maps for Godan
# ------------------------------

_GODAN_ROW: Dict[str, Dict[str, str]] = {
    "う": {"a": "わ", "i": "い", "u": "う", "e": "え", "o": "お"},
    "く": {"a": "か", "i": "き", "u": "く", "e": "け", "o": "こ"},
    "ぐ": {"a": "が", "i": "ぎ", "u": "ぐ", "e": "げ", "o": "ご"},
    "す": {"a": "さ", "i": "し", "u": "す", "e": "せ", "o": "そ"},
    "つ": {"a": "た", "i": "ち", "u": "つ", "e": "て", "o": "と"},
    "ぬ": {"a": "な", "i": "に", "u": "ぬ", "e": "ね", "o": "の"},
    "ぶ": {"a": "ば", "i": "び", "u": "ぶ", "e": "べ", "o": "ぼ"},
    "む": {"a": "ま", "i": "み", "u": "む", "e": "め", "o": "も"},
    "る": {"a": "ら", "i": "り", "u": "る", "e": "れ", "o": "ろ"},
}

_GODAN_TE_TA: Dict[str, Tuple[str, str]] = {
    "う": ("って", "った"), "つ": ("って", "った"), "る": ("って", "った"),
    "む": ("んで", "んだ"), "ぶ": ("んで", "んだ"), "ぬ": ("んで", "んだ"),
    "く": ("いて", "いた"), "ぐ": ("いで", "いだ"), "す": ("して", "した"),
}

# ------------------------------
# Helpers
# ------------------------------

def _safe_strip(s: Optional[str]) -> str:
    return (s or "").strip()

def _parse_jmdict_pos(pos: Optional[str]) -> Tuple[str, str]:
    """
    Routes JMDict (or generic) POS tags to (category, sub_class).
    """
    if not pos:
        return "unknown", "unknown"
    p = pos.lower()

    # Normalized internal labels from adapter
    if p in {"verb", "i-adj", "na-adj", "copula"}:
        return p, "unknown"
    
    # JMDict Verb POS
    if p.startswith("v1"): return "verb", "ichidan"
    if p.startswith("v5"): return "verb", "godan"
    if p.startswith("vk"): return "verb", "kuru"
    if p.startswith("vs") or p == "vz": return "verb", "suru"
    
    # Generic Verb Fallbacks
    if "verb" in p or "動詞" in p: return "verb", "unknown"
    
    # Adjectives
    if "adj-i" in p or p == "形容詞": return "i-adj", ""
    if "adj-na" in p or "形容動詞" in p: return "na-adj", ""
    if "adj" in p: return "unknown", "unknown" # Could be either, let analyzer try both
    
    # Copula
    if "cop" in p: return "copula", ""
    
    return "unknown", "unknown"

def _guess_verb_class(lemma: str) -> str:
    """Fallback if JMDict POS does not specify verb class."""
    if lemma in ("する",): return "suru"
    if lemma in ("来る", "くる"): return "kuru"
    if lemma.endswith("る") and len(lemma) >= 2:
        prev = lemma[-2]
        if prev in set("いきしちにひみりぎじぢびぴえけせてねへめれげぜでべぺ"):
            return "ichidan"
    return "godan"


def _first_form_for_primary_tag(lemma: str, verb_class: str, primary_tag: str) -> str:
    for s, tags, _feats, _desc in _gen_verb_base_forms(lemma, verb_class):
        if tags and tags[0] == primary_tag:
            return s
    return ""


# ------------------------------
# Generators
# ------------------------------

def _gen_verb_base_forms(lemma: str, verb_class: str) -> Iterable[Tuple[str, Tuple[str, ...], Dict[str, Any], str]]:
    lemma = _safe_strip(lemma)
    if not lemma: return

    if verb_class == "suru":
        yield ("し", ("Conjunctive",), {"form": "conjunctive"}, "Conjunctive stem (連用形)")
        yield ("せ", ("Irrealis",), {"form": "irrealis"}, "Irrealis stem (未然形)")
        yield ("すれ", ("Conditional",), {"form": "conditional"}, "Conditional stem (仮定形)")
        yield ("しろ", ("Imperative",), {"form": "imperative"}, "Imperative")
        yield ("せよ", ("Imperative", "Alt"), {"form": "imperative", "variant": "seyo"}, "Imperative (せよ)")
        yield ("しよう", ("Volitional",), {"form": "volitional"}, "Volitional")
        yield ("して", ("Te",), {"form": "te"}, "Te-form")
        yield ("した", ("Past",), {"form": "ta", "tense": "past"}, "Past")
        yield ("したら", ("Tara",), {"form": "tara", "tense": "conditional"}, "Tara conditional")
        yield ("したり", ("Tari",), {"form": "tari"}, "Tari representative")
        yield ("しない", ("Negative",), {"polarity": "negative"}, "Negative")
        yield ("しなかった", ("Negative", "Past"), {"polarity": "negative", "tense": "past"}, "Negative past")
        yield ("するな", ("Imperative", "Negative"), {"polarity": "negative", "form": "imperative"}, "Negative imperative")
        # Polite
        yield ("します", ("Polite", "NonPast"), {"polite": True}, "Polite non-past")
        yield ("しません", ("Polite", "Negative"), {"polite": True, "polarity": "negative"}, "Polite negative")
        yield ("しました", ("Polite", "Past"), {"polite": True, "tense": "past"}, "Polite past")
        yield ("しませんでした", ("Polite", "Negative", "Past"), {"polite": True, "polarity": "negative", "tense": "past"}, "Polite negative past")
        yield ("しましょう", ("Polite", "Volitional"), {"polite": True, "form": "volitional"}, "Polite volitional")
        # Classical
        yield ("せず", ("ClassicalNegative", "Zu"), {"polarity": "negative", "register": "classical"}, "Classical negative (ず)")
        yield ("せぬ", ("ClassicalNegative", "Nu"), {"polarity": "negative", "register": "classical"}, "Classical negative (ぬ)")
        return

    if verb_class == "kuru":
        is_kanji = lemma == "来る"
        stem = "来" if is_kanji else "く"
        renyou = "来" if is_kanji else "き"
        mizen = "来" if is_kanji else "こ"
        
        yield (renyou, ("Conjunctive",), {"form": "conjunctive"}, "Conjunctive stem (連用形)")
        yield (mizen, ("Irrealis",), {"form": "irrealis"}, "Irrealis stem (未然形)")
        yield (f"{stem}れ", ("Conditional",), {"form": "conditional"}, "Conditional stem (仮定形)")
        yield (f"{stem}い", ("Imperative",), {"form": "imperative"}, "Imperative")
        yield (f"{mizen}よう", ("Volitional",), {"form": "volitional"}, "Volitional")
        yield (f"{renyou}て", ("Te",), {"form": "te"}, "Te-form")
        yield (f"{renyou}た", ("Past",), {"form": "ta", "tense": "past"}, "Past")
        yield (f"{renyou}たら", ("Tara",), {"form": "tara", "tense": "conditional"}, "Tara conditional")
        yield (f"{renyou}たり", ("Tari",), {"form": "tari"}, "Tari representative")
        yield (f"{mizen}ない", ("Negative",), {"polarity": "negative"}, "Negative")
        yield (f"{mizen}なかった", ("Negative", "Past"), {"polarity": "negative", "tense": "past"}, "Negative past")
        yield (f"{lemma}な", ("Imperative", "Negative"), {"polarity": "negative", "form": "imperative"}, "Negative imperative")
        # Polite
        yield (f"{renyou}ます", ("Polite", "NonPast"), {"polite": True}, "Polite non-past")
        yield (f"{renyou}ません", ("Polite", "Negative"), {"polite": True, "polarity": "negative"}, "Polite negative")
        yield (f"{renyou}ました", ("Polite", "Past"), {"polite": True, "tense": "past"}, "Polite past")
        yield (f"{renyou}ませんでした", ("Polite", "Negative", "Past"), {"polite": True, "polarity": "negative", "tense": "past"}, "Polite negative past")
        yield (f"{renyou}ましょう", ("Polite", "Volitional"), {"polite": True, "form": "volitional"}, "Polite volitional")
        # Classical
        yield (f"{mizen}ず", ("ClassicalNegative", "Zu"), {"polarity": "negative", "register": "classical"}, "Classical negative (ず)")
        yield (f"{mizen}ぬ", ("ClassicalNegative", "Nu"), {"polarity": "negative", "register": "classical"}, "Classical negative (ぬ)")
        return

    if lemma == "ある":
        yield ("あり", ("Conjunctive",), {"form": "conjunctive"}, "Conjunctive stem (連用形)")
        yield ("あっ", ("TeTaStem",), {"form": "te_ta_stem"}, "Te/ta stem")
        yield ("あって", ("Te",), {"form": "te"}, "Te-form")
        yield ("あった", ("Past",), {"form": "ta", "tense": "past"}, "Past")
        yield ("あったら", ("Tara",), {"form": "tara", "tense": "conditional"}, "Tara conditional")
        yield ("あったり", ("Tari",), {"form": "tari"}, "Tari representative")
        yield ("あれ", ("Conditional",), {"form": "conditional"}, "Conditional stem (仮定形)")
        yield ("あれば", ("Conditional",), {"form": "conditional"}, "Conditional")
        yield ("あろう", ("Volitional",), {"form": "volitional"}, "Volitional")
        yield ("ない", ("Negative", "Suppletive"), {"polarity": "negative"}, "Negative (ない)")
        yield ("なかった", ("Negative", "Past", "Suppletive"), {"polarity": "negative", "tense": "past"}, "Negative past (なかった)")
        yield ("あるな", ("Imperative", "Negative"), {"polarity": "negative", "form": "imperative"}, "Negative imperative")
        # Polite
        yield ("あります", ("Polite", "NonPast"), {"polite": True}, "Polite non-past")
        yield ("ありません", ("Polite", "Negative"), {"polite": True, "polarity": "negative"}, "Polite negative")
        yield ("ありました", ("Polite", "Past"), {"polite": True, "tense": "past"}, "Polite past")
        yield ("ありませんでした", ("Polite", "Negative", "Past"), {"polite": True, "polarity": "negative", "tense": "past"}, "Polite negative past")
        yield ("ありましょう", ("Polite", "Volitional"), {"polite": True, "form": "volitional"}, "Polite volitional")
        return

    stem, end = lemma[:-1], lemma[-1]

    if verb_class == "ichidan" and lemma.endswith("る"):
        base = lemma[:-1]
        yield (base, ("Conjunctive",), {"form": "conjunctive"}, "Conjunctive stem (連用形)")
        yield (base + "て", ("Te",), {"form": "te"}, "Te-form")
        yield (base + "た", ("Past",), {"form": "ta", "tense": "past"}, "Past")
        yield (base + "たら", ("Tara",), {"form": "tara", "tense": "conditional"}, "Tara conditional")
        yield (base + "たり", ("Tari",), {"form": "tari"}, "Tari representative")
        yield (base + "ない", ("Negative",), {"polarity": "negative"}, "Negative")
        yield (base + "なかった", ("Negative", "Past"), {"polarity": "negative", "tense": "past"}, "Negative past")
        yield (base + "れば", ("Conditional",), {"form": "conditional"}, "Conditional")
        yield (base + "ろ", ("Imperative",), {"form": "imperative"}, "Imperative (ろ)")
        yield (base + "よ", ("Imperative", "Alt"), {"form": "imperative", "variant": "yo"}, "Imperative (よ)")
        yield (lemma + "な", ("Imperative", "Negative"), {"polarity": "negative", "form": "imperative"}, "Negative imperative")
        yield (base + "よう", ("Volitional",), {"form": "volitional"}, "Volitional")
        # Polite
        yield (base + "ます", ("Polite", "NonPast"), {"polite": True}, "Polite non-past")
        yield (base + "ません", ("Polite", "Negative"), {"polite": True, "polarity": "negative"}, "Polite negative")
        yield (base + "ました", ("Polite", "Past"), {"polite": True, "tense": "past"}, "Polite past")
        yield (base + "ませんでした", ("Polite", "Negative", "Past"), {"polite": True, "polarity": "negative", "tense": "past"}, "Polite negative past")
        yield (base + "ましょう", ("Polite", "Volitional"), {"polite": True, "form": "volitional"}, "Polite volitional")
        # Classical
        yield (base + "ず", ("ClassicalNegative", "Zu"), {"polarity": "negative", "register": "classical"}, "Classical negative (ず)")
        yield (base + "ぬ", ("ClassicalNegative", "Nu"), {"polarity": "negative", "register": "classical"}, "Classical negative (ぬ)")
        return

    # Godan
    if end in _GODAN_ROW:
        row = _GODAN_ROW[end]
        mizen = stem + row["a"]
        renyou = stem + row["i"]
        katei = stem + row["e"]
        vol = stem + row["o"] + "う"
        
        # Exception for Iku
        if lemma in ("行く", "いく"):
            te, ta = "って", "った"
        else:
            te, ta = _GODAN_TE_TA.get(end, (None, None))
            
        if te and ta:
            yield (stem + te, ("Te",), {"form": "te"}, "Te-form")
            yield (stem + ta, ("Past",), {"form": "ta", "tense": "past"}, "Past")
            yield (stem + ta + "ら", ("Tara",), {"form": "tara", "tense": "conditional"}, "Tara conditional")
            yield (stem + ta + "り", ("Tari",), {"form": "tari"}, "Tari representative")
            yield (stem + te[:-1], ("TeTaStem",), {"form": "te_ta_stem"}, "Te/ta stem")
            
        yield (mizen, ("Irrealis",), {"form": "irrealis"}, "Irrealis stem (未然形)")
        yield (renyou, ("Conjunctive",), {"form": "conjunctive"}, "Conjunctive stem (連用形)")
        yield (katei, ("ConditionalStem",), {"form": "conditional_stem"}, "Conditional stem (仮定形)")
        yield (katei + "ば", ("Conditional",), {"form": "conditional"}, "Conditional (〜ば)")
        yield (katei, ("Imperative",), {"form": "imperative"}, "Imperative")
        yield (lemma + "な", ("Imperative", "Negative"), {"polarity": "negative", "form": "imperative"}, "Negative imperative")
        yield (vol, ("Volitional",), {"form": "volitional"}, "Volitional")
        # Negative
        yield (mizen + "ない", ("Negative",), {"polarity": "negative"}, "Negative")
        yield (mizen + "なかった", ("Negative", "Past"), {"polarity": "negative", "tense": "past"}, "Negative past")
        # Polite
        yield (renyou + "ます", ("Polite", "NonPast"), {"polite": True}, "Polite non-past")
        yield (renyou + "ません", ("Polite", "Negative"), {"polite": True, "polarity": "negative"}, "Polite negative")
        yield (renyou + "ました", ("Polite", "Past"), {"polite": True, "tense": "past"}, "Polite past")
        yield (renyou + "ませんでした", ("Polite", "Negative", "Past"), {"polite": True, "polarity": "negative", "tense": "past"}, "Polite negative past")
        yield (renyou + "ましょう", ("Polite", "Volitional"), {"polite": True, "form": "volitional"}, "Polite volitional")
        # Classical
        yield (mizen + "ず", ("ClassicalNegative", "Zu"), {"polarity": "negative", "register": "classical"}, "Classical negative (ず)")
        yield (mizen + "ぬ", ("ClassicalNegative", "Nu"), {"polarity": "negative", "register": "classical"}, "Classical negative (ぬ)")

def _gen_verb_derivations(lemma: str, verb_class: str) -> Iterable[Tuple[str, str, str]]:
    lemma = _safe_strip(lemma)
    if not lemma or lemma == "ある": return

    if verb_class == "suru":
        yield ("される", "Passive", "Passive")
        yield ("させる", "Causative", "Causative")
        yield ("できる", "Potential", "Potential (suppletive)")
        yield ("させられる", "CausativePassive", "Causative-passive")
        yield ("したい", "Desiderative", "Desiderative (Tai)")
        return

    if verb_class == "kuru":
        is_kanji = lemma == "来る"
        yield ("来られる" if is_kanji else "こられる", "Passive/Potential", "Passive/Potential")
        yield ("来れる" if is_kanji else "これる", "Potential (Ra-nuki)", "Colloquial Potential (Ra-nuki)")
        yield ("来させる" if is_kanji else "こさせる", "Causative", "Causative")
        yield ("来させられる" if is_kanji else "こさせられる", "CausativePassive", "Causative-passive")
        yield ("来たい" if is_kanji else "きたい", "Desiderative", "Desiderative (Tai)")
        return

    stem, end = lemma[:-1], lemma[-1]

    if verb_class == "ichidan" and lemma.endswith("る"):
        base = lemma[:-1]
        yield (base + "られる", "Passive/Potential", "Passive/Potential")
        yield (base + "れる", "Potential (Ra-nuki)", "Colloquial Potential (Ra-nuki)")
        yield (base + "させる", "Causative", "Causative")
        yield (base + "させられる", "CausativePassive", "Causative-passive")
        yield (base + "たい", "Desiderative", "Desiderative (Tai)")
        return

    if verb_class == "godan" and end in _GODAN_ROW:
        row = _GODAN_ROW[end]
        mizen = stem + row["a"]
        renyou = stem + row["i"]
        yield (mizen + "れる", "Passive", "Passive")
        yield (mizen + "せる", "Causative", "Causative")
        yield (stem + row["e"] + "る", "Potential", "Potential")
        yield (mizen + "せられる", "CausativePassive", "Causative-passive (standard)")
        yield (mizen + "される", "CausativePassive", "Causative-passive (shortened)")
        yield (renyou + "たい", "Desiderative", "Desiderative (Tai)")

def _gen_i_adj_forms(lemma: str) -> Iterable[Tuple[str, Tuple[str, ...], Dict[str, Any], str]]:
    lemma = _safe_strip(lemma)
    if not lemma or not lemma.endswith("い"): return
    base = lemma[:-1]
    yield (base + "く", ("Adverbial",), {"form": "adverbial"}, "Adverbial (〜く)")
    yield (base + "かった", ("Past",), {"tense": "past"}, "Past (〜かった)")
    yield (base + "くない", ("Negative",), {"polarity": "negative"}, "Negative (〜くない)")
    yield (base + "くなかった", ("Negative", "Past"), {"polarity": "negative", "tense": "past"}, "Negative past (〜くなかった)")
    yield (base + "くて", ("Te",), {"form": "te"}, "Te-form (〜くて)")
    yield (base + "ければ", ("Conditional",), {"form": "conditional"}, "Conditional (〜ければ)")
    yield (lemma + "です", ("Polite",), {"polite": True}, "Polite predicative (〜です)")

def _gen_na_adj_forms(lemma: str) -> Iterable[Tuple[str, Tuple[str, ...], Dict[str, Any], str]]:
    lemma = _safe_strip(lemma)
    if not lemma: return
    yield (lemma + "だ", ("Copula", "NonPast"), {"copula": "da"}, "Plain copula predicative (〜だ)")
    yield (lemma + "な", ("Attributive",), {"form": "attributive"}, "Attributive (〜な)")
    yield (lemma + "に", ("Adverbial",), {"form": "adverbial"}, "Adverbial (〜に)")
    yield (lemma + "で", ("Te",), {"form": "te"}, "Te-form (〜で)")
    yield (lemma + "だった", ("Past",), {"tense": "past"}, "Past (〜だった)")
    yield (lemma + "ではない", ("Negative",), {"polarity": "negative"}, "Negative (〜ではない)")
    yield (lemma + "じゃない", ("Negative", "Alt"), {"polarity": "negative", "variant": "ja"}, "Negative (〜じゃない)")
    yield (lemma + "ではなかった", ("Negative", "Past"), {"polarity": "negative", "tense": "past"}, "Negative past (〜ではなかった)")
    yield (lemma + "じゃなかった", ("Negative", "Past", "Alt"), {"polarity": "negative", "tense": "past", "variant": "ja"}, "Negative past (〜じゃなかった)")
    yield (lemma + "なら", ("Conditional",), {"form": "conditional"}, "Conditional (〜なら)")
    # polite
    yield (lemma + "です", ("Polite", "NonPast"), {"polite": True}, "Polite predicative (〜です)")
    yield (lemma + "でした", ("Polite", "Past"), {"polite": True, "tense": "past"}, "Polite past (〜でした)")
    yield (lemma + "ではありません", ("Polite", "Negative"), {"polite": True, "polarity": "negative"}, "Polite negative (〜ではありません)")
    yield (lemma + "ではありませんでした", ("Polite", "Negative", "Past"), {"polite": True, "polarity": "negative", "tense": "past"}, "Polite negative past")

def _gen_copula_forms(lemma: str) -> Iterable[Tuple[str, Tuple[str, ...], Dict[str, Any], str]]:
    lemma = _safe_strip(lemma)
    if lemma not in ("だ", "です"): return
    if lemma == "だ":
        yield ("だ", ("Dictionary",), {"form": "dictionary"}, "Plain copula (だ)")
        yield ("で", ("Te",), {"form": "te"}, "Te-form of copula (で)")
        yield ("だった", ("Past",), {"tense": "past"}, "Past of copula (だった)")
        yield ("ではない", ("Negative",), {"polarity": "negative"}, "Negative of copula (ではない)")
        yield ("じゃない", ("Negative", "Alt"), {"polarity": "negative", "variant": "ja"}, "Negative of copula (じゃない)")
        yield ("ではなかった", ("Negative", "Past"), {"polarity": "negative", "tense": "past"}, "Negative past of copula (ではなかった)")
        yield ("じゃなかった", ("Negative", "Past", "Alt"), {"polarity": "negative", "tense": "past", "variant": "ja"}, "Negative past of copula (じゃなかった)")
        yield ("なら", ("Conditional",), {"form": "conditional"}, "Conditional (なら) of copula")
    else:
        yield ("です", ("Dictionary",), {"polite": True}, "Polite copula (です)")
        yield ("で", ("Te",), {"form": "te"}, "Te-form used with です (で)")
        yield ("でした", ("Past",), {"polite": True, "tense": "past"}, "Past polite copula (でした)")
        yield ("ではありません", ("Negative",), {"polite": True, "polarity": "negative"}, "Polite negative copula (ではありません)")
        yield ("ではありませんでした", ("Negative", "Past"), {"polite": True, "polarity": "negative", "tense": "past"}, "Polite negative past copula")
        yield ("でしょう", ("Volitional",), {"polite": True, "form": "volitional"}, "Polite conjectural (でしょう)")


# ------------------------------
# Main analyzer
# ------------------------------

class JapaneseInflectionTableAnalyzer:
    def analyze(
        self,
        surface: str,
        lemma: str,
        pos: Optional[str] = None,
        verb_class: Optional[str] = None,
        jmdict_pos: Optional[str] = None,
    ) -> List[Analysis]:
        surface = _safe_strip(surface)
        lemma = _safe_strip(lemma)
        if not surface or not lemma or surface == lemma:
            return []

        analyses: List[Analysis] = []
        pos_for_routing = jmdict_pos if jmdict_pos is not None else pos
        cat, sub_class = _parse_jmdict_pos(pos_for_routing)
        if verb_class:
            sub_class = str(verb_class or "").strip().lower()
        
        candidates: List[str]
        if cat == "unknown":
            candidates = ["copula", "i-adj", "verb", "na-adj"]
        else:
            candidates = [cat]

        for c in candidates:
            if c == "copula":
                for s, tags, feats, desc in _gen_copula_forms(lemma):
                    if s == surface:
                        analyses.append(Analysis(surface, lemma, "copula", tags, feats, desc))

            elif c == "i-adj":
                for s, tags, feats, desc in _gen_i_adj_forms(lemma):
                    if s == surface:
                        analyses.append(Analysis(surface, lemma, "i-adj", tags, feats, desc))

            elif c == "na-adj":
                for s, tags, feats, desc in _gen_na_adj_forms(lemma):
                    if s == surface:
                        analyses.append(Analysis(surface, lemma, "na-adj", tags, feats, desc))

            elif c == "verb":
                vc = sub_class if sub_class != "unknown" else _guess_verb_class(lemma)

                # Base inflections
                for s, tags, feats, desc in _gen_verb_base_forms(lemma, vc):
                    if s == surface:
                        analyses.append(Analysis(surface, lemma, "verb", tags, feats, desc))

                # Te-based auxiliaries directly on the base lemma (e.g., 進んでいた).
                te_base = _first_form_for_primary_tag(lemma, vc, "Te")
                if te_base:
                    te_aux_rules = (
                        ("TeIru", "いる", "progressive/resultative (te-iru)"),
                        ("TeOru", "おる", "humble progressive (te-oru)"),
                        ("TeAru", "ある", "resultative (te-aru)"),
                        ("Shimau", "しまう", "completion/regret (te-shimau)"),
                        ("Oku", "おく", "in advance (te-oku)"),
                        ("Miru", "みる", "trial (te-miru)"),
                        ("Iku", "いく", "continuative/future direction (te-iku)"),
                        ("Kuru", "くる", "change-toward-speaker (te-kuru)"),
                    )
                    for aux_tag, aux_lemma, aux_desc in te_aux_rules:
                        aux_derived = te_base + aux_lemma
                        avc = _guess_verb_class(aux_derived)
                        for s3, tags3, feats3, desc3 in _gen_verb_base_forms(aux_derived, avc):
                            if s3 == surface:
                                chain3 = (aux_tag,) + tags3
                                feats3_out = dict(feats3)
                                feats3_out["derivation"] = aux_tag
                                analyses.append(Analysis(surface, lemma, "verb", chain3, feats3_out, f"{aux_desc}; then {desc3}"))

                # Derivations
                for derived_lemma, dtag, ddesc in _gen_verb_derivations(lemma, vc):
                    
                    # Desiderative pipeline handles forms via i-adj
                    if dtag == "Desiderative":
                        for s2, tags2, feats2, desc2 in _gen_i_adj_forms(derived_lemma):
                            if s2 == surface:
                                chain = (dtag,) + tags2
                                feats = dict(feats2)
                                feats["derivation"] = dtag
                                analyses.append(Analysis(surface, lemma, "verb", chain, feats, f"{ddesc} -> {desc2}"))
                        # Match the plain derived string
                        if derived_lemma == surface:
                            analyses.append(Analysis(surface, lemma, "verb", (dtag, "Dictionary"), {"form": "dictionary", "derivation": dtag}, f"{ddesc} (dictionary form)"))
                        continue

                    # Standard verb derivations
                    dvc = "ichidan" if derived_lemma.endswith("る") and derived_lemma != "できる" else _guess_verb_class(derived_lemma)
                    for s2, tags2, feats2, desc2 in _gen_verb_base_forms(derived_lemma, dvc):
                        if s2 == surface:
                            chain = (dtag,) + tags2
                            feats = dict(feats2)
                            feats["derivation"] = dtag
                            analyses.append(Analysis(surface, lemma, "verb", chain, feats, f"{ddesc}; then {desc2}"))
                            
                    if derived_lemma == surface:
                        analyses.append(Analysis(surface, lemma, "verb", (dtag, "Dictionary"), {"form": "dictionary", "derivation": dtag}, f"{ddesc} (dictionary form)"))

                    # Te-based auxiliaries chained after derivations
                    te_chain_base = _first_form_for_primary_tag(derived_lemma, dvc, "Te")
                    if te_chain_base:
                        te_aux_rules = (
                            ("TeIru", "いる", "progressive/resultative (te-iru)"),
                            ("TeOru", "おる", "humble progressive (te-oru)"),
                            ("TeAru", "ある", "resultative (te-aru)"),
                            ("Shimau", "しまう", "completion/regret (te-shimau)"),
                            ("Oku", "おく", "in advance (te-oku)"),
                            ("Miru", "みる", "trial (te-miru)"),
                            ("Iku", "いく", "continuative/future direction (te-iku)"),
                            ("Kuru", "くる", "change-toward-speaker (te-kuru)"),
                        )
                        for aux_tag, aux_lemma, aux_desc in te_aux_rules:
                            aux_derived = te_chain_base + aux_lemma
                            avc = _guess_verb_class(aux_derived)
                            for s3, tags3, feats3, desc3 in _gen_verb_base_forms(aux_derived, avc):
                                if s3 == surface:
                                    chain3 = (dtag, aux_tag) + tags3
                                    feats3_out = dict(feats3)
                                    feats3_out["derivation"] = dtag
                                    feats3_out["auxiliary"] = aux_tag
                                    analyses.append(Analysis(surface, lemma, "verb", chain3, feats3_out, f"{ddesc}; {aux_desc}; then {desc3}"))

        # Deduplicate identical analyses
        uniq: Dict[Tuple[str, str, str, Tuple[str, ...], Tuple[Tuple[str, Any], ...], str], Analysis] = {}
        for a in analyses:
            # Need to freeze dict items for hashing
            frozen_feats = tuple(sorted(a.features.items()))
            key = (a.surface, a.lemma, a.category, a.derivation, frozen_feats, a.description)
            uniq[key] = a
        return list(uniq.values())


# ------------------------------
# CLI
# ------------------------------

def _pretty(a: Analysis) -> str:
    d = " + ".join(a.derivation) if a.derivation else "(none)"
    feats = ", ".join(f"{k}={v}" for k, v in sorted(a.features.items()))
    return f"{a.surface}  <=  {a.lemma} | {a.category} | {d} | {a.description}" + (f" | {feats}" if feats else "")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--surface", type=str, default=None)
    ap.add_argument("--lemma", type=str, default=None)
    ap.add_argument("--pos", type=str, default=None, help="JMDict pos tag e.g., v5k, v1, adj-i")
    ap.add_argument("--tokens-json", type=str, default=None, help="Path to JSON list of tokens")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    args = ap.parse_args()

    ana = JapaneseInflectionTableAnalyzer()
    out: List[Analysis] = []

    if args.tokens_json:
        with open(args.tokens_json, "r", encoding="utf-8") as f:
            items = json.load(f)
        if not isinstance(items, list):
            raise SystemExit("--tokens-json must be a JSON list")
        for it in items:
            if not isinstance(it, dict):
                continue
            surface = _safe_strip(it.get("surface"))
            lemma = _safe_strip(it.get("lemma"))
            pos = it.get("pos") or it.get("jmdict_pos")
            out.extend(ana.analyze(surface, lemma, jmdict_pos=pos))
    else:
        if not args.surface or not args.lemma:
            raise SystemExit("Provide --surface and --lemma OR --tokens-json")
        out = ana.analyze(args.surface, args.lemma, jmdict_pos=args.pos)

    if args.json:
        print(json.dumps([asdict(a) for a in out], ensure_ascii=False, indent=2))
    else:
        if not out:
            print("(no match)")
        else:
            for a in sorted(out, key=lambda x: (x.category, x.derivation, x.description)):
                print(_pretty(a))

if __name__ == "__main__":
    main()
