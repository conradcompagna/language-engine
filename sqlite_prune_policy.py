#!/usr/bin/env python3
"""
Shared read-only pruning policy for SQLite dictionary postprocessing.

This module is intended to be reused by both dry-run audit scripts and the
future compact-index runtime filter.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from typing import Iterable


ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
ENGLISH_PROSE_HINT_RE = re.compile(
    r"\b(?:form|forms|formed|using|present|past|future|perfect|imperfect|simple|"
    r"particle|appendix|information|note|marks|case|instead|other|desiderative|"
    r"imperative|indicative|subjunctive|conditional|participle|voice|aspect|"
    r"declension|conjugation|dialect|modern|standard|swahili|absent|table)\b",
    re.IGNORECASE,
)
ALTERNATION_LABEL_RE = re.compile(
    r"^[A-Za-z][A-Za-z-]*-[A-Za-z][A-Za-z-]*\s+alternation$", re.IGNORECASE
)
ROMAN_NUMERAL_RE = re.compile(
    r"^(?=.+)(?:M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3}))\.?$"
)
HEBREW_MISHKAL_RE = re.compile(r"^[\u0590-\u05FF\uFB1D-\uFB4F\u05BE\u05C0\u05C3\u05F3\u05F4]+$")
CLASS_CODE_RE = re.compile(
    r"""
    ^
    (?:
        \d+(?:[a-z]|\+[1-9])?
        (?:\s+Anglian)?
        |
        \d+\s+(?:strong|weak)
        |
        [IVXLCDM]+\s+[a-z]\.?
        |
        [IVXLCDM]+\.
        |
        [IVXLCDM]+
        |
        [A-Za-z]\.
        |
        a\*\d?
        |
        a\*\[[^\]]+\]
        |
        b\*\d?
        |
        c(?:ʹ)?\*
        |
        [1-9]\d*(?:[a-z])?\s+(?:perfective|imperfective).+
        |
        accent-[a-z]
        |
        .+-stem
    )
    $
    """,
    re.VERBOSE,
)
BROKEN_TEMPLATE_RE = re.compile(r"(?:\{\{\{.+\}\}\}|[{}]|[()]{0,1}.+\([^-)]*$)")

HARD_DROP_TAGS = frozenset(
    {
        "class",
        "classifier",
        "counter",
        "table-tags",
        "inflection-template",
        "multiword-construction",
        "includes-article",
        "auxiliary",
    }
)

RULE_A_EXEMPT_DBS = frozenset(
    {
        "ja",
        "ja-jmdict",
        "ko",
        "ko-krdict",
        "grc",
        "zh",
        "zh-cc-cedict",
        "zh-hant",
        "zh-hant-cc-cedict",
        "lzh",
        "lzh-wiktionary",
        "vi",
    }
)

NON_KAIKKI_DBS = frozenset(
    {
        "ja-jmdict",
        "ko-krdict",
        "zh-cc-cedict",
        "zh-hant-cc-cedict",
        "grc-lsj",
        "ang-bt",
        "sa",
    }
)

SYNTHETIC_COLLAPSE_TRIGGERS = frozenset(
    {
        # Pure inflectional morphology only.
        # Number
        "singular",
        "plural",
        "dual",
        # Case
        "nominative",
        "accusative",
        "dative",
        "genitive",
        "vocative",
        "ablative",
        "locative",
        "instrumental",
        "prepositional",
        "partitive",
        "oblique",
        # Gender
        "masculine",
        "feminine",
        "neuter",
        # Person
        "first-person",
        "second-person",
        "third-person",
        # Tense
        "present",
        "past",
        "future",
        "imperfect",
        "perfect",
        "pluperfect",
        "preterite",
        "aorist",
        # Aspect
        "perfective",
        "imperfective",
        "progressive",
        "continuative",
        "habitual",
        "contemplative",
        "prospective",
        # Mood
        "indicative",
        "subjunctive",
        "conditional",
        "imperative",
        "optative",
        # Non-finite forms
        "infinitive",
        "gerund",
        "participle",
        "supine",
        "conjunctive",
        # Voice
        "active",
        "passive",
        "mediopassive",
        "reflexive",
        "causative",
        "agentive",
        # Definiteness / polarity
        "definite",
        "indefinite",
        "negative",
        # Possession / comparison / size
        "possessive",
        "comparative",
        "superlative",
        "augmentative",
        "diminutive",
        # Generic morphology markers
        "inflection",
        "inflected",
    }
)

# Targets that are never valid collapse destinations even if they happen to
# exist as headwords in a dictionary (English/Romance/Germanic articles,
# determiners, prepositions, copulas, generic English connectives). The donor's
# gloss is almost always an English-prose definition when the target is one of
# these; collapsing in that case produces nonsense.
TARGET_BLACKLIST = frozenset(
    {
        # English articles, prepositions, copulas, conjunctions, demonstratives
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "at",
        "to",
        "by",
        "for",
        "with",
        "and",
        "or",
        "but",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "their",
        "his",
        "her",
        "my",
        "your",
        "our",
        "him",
        "she",
        "we",
        "you",
        "they",
        "them",
        "from",
        "into",
        "such",
        "any",
        "all",
        "each",
        "no",
        "not",
        "than",
        "so",
        # Romance articles / common particles
        "el",
        "la",
        "lo",
        "los",
        "las",
        "le",
        "les",
        "il",
        "i",
        "gli",
        "de",
        "da",
        "del",
        "della",
        "delle",
        "dei",
        "degli",
        "des",
        "du",
        "au",
        "aux",
        "un",
        "una",
        "uno",
        "ein",
        "eine",
        "einer",
        "einem",
        "einen",
        # Germanic articles
        "der",
        "den",
        "dem",
        "das",
        "die",
        "des",
        # Dutch
        "uw",
        "het",
        # Irish
        "an",
        # English/Latin-script trigger words that are themselves headwords (avoid
        # pointing to a literal trigger word as the target)
        "instrumental",
        "verbal",
        "adverbial",
        "pronominal",
        "adjectival",
        "predicative",
        "attributive",
    }
)


def is_kaikki_db(db_name: str) -> bool:
    return normalize_db_name(db_name) not in NON_KAIKKI_DBS


_OF_HEADWORD_RE = re.compile(r"\bof\s+(\S+)")
_TRAILING_PUNCT_RE = re.compile(r"[\s\.,;:!\?\)\]\}\"'`]+$")
_WORD_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-]*")


def _nfkc_fold(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).casefold()


def compute_synthetic_collapses(conn, alias: str, db_name: str) -> dict:
    """DISABLED. The "X of Y" gloss-pattern collapse heuristic produced too many
    edge-case false positives across dictionaries to ever be made fully safe.
    Returns an empty result so the build pipeline keeps every entry as-is.

    The original implementation is kept commented-out below for reference.
    """
    return {
        "donor_to_target": {},
        "synthetic_tags_by_donor": {},
        "donor_surface_by_donor": {},
        "donor_romanization_by_donor": {},
        "donor_gloss_by_donor": {},
        "target_headword_by_donor": {},
    }


# def _compute_synthetic_collapses_disabled(conn, alias: str, db_name: str) -> dict:
#     """Original collapse logic. Disabled — see compute_synthetic_collapses above."""
#     out: dict[str, dict] = {
#         "donor_to_target": {},
#         "synthetic_tags_by_donor": {},
#         "donor_surface_by_donor": {},
#         "donor_romanization_by_donor": {},
#         "donor_gloss_by_donor": {},
#         "target_headword_by_donor": {},
#     }
#     if not is_kaikki_db(db_name):
#         return out
#
#     qa = '"' + str(alias).replace('"', '""') + '"'
#     headword_to_entry_id: dict[str, int] = {}
#     rows = list(conn.execute(
#         f"SELECT id, TRIM(COALESCE(headword, '')) AS headword, "
#         f"       TRIM(COALESCE(romanization, '')) AS romanization, "
#         f"       TRIM(COALESCE(glosses, '')) AS glosses "
#         f"FROM {qa}.entries"
#     ))
#     for row in rows:
#         hw = str(row["headword"] or "").strip()
#         if not hw:
#             continue
#         folded = _nfkc_fold(hw)
#         if folded and folded not in headword_to_entry_id:
#             headword_to_entry_id[folded] = int(row["id"])
#
#     for row in rows:
#         donor_id = int(row["id"] or 0)
#         donor_hw = str(row["headword"] or "").strip()
#         if donor_id <= 0 or not donor_hw:
#             continue
#         glosses_raw = str(row["glosses"] or "")
#         glosses, _err = parse_glosses(glosses_raw)
#         if not glosses:
#             continue
#
#         best_target_id = 0
#         best_target_hw = ""
#         best_gloss_len = -1
#         best_gloss = ""
#         triggers_union: set[str] = set()
#
#         for gloss in glosses:
#             gloss_str = str(gloss or "")
#             if not gloss_str:
#                 continue
#             words_lower = {m.group(0).lower() for m in _WORD_TOKEN_RE.finditer(gloss_str)}
#             gloss_triggers = words_lower & SYNTHETIC_COLLAPSE_TRIGGERS
#             if not gloss_triggers:
#                 continue
#             for m in _OF_HEADWORD_RE.finditer(gloss_str):
#                 tok = _TRAILING_PUNCT_RE.sub("", m.group(1))
#                 if not tok:
#                     continue
#                 tok_folded = _nfkc_fold(tok)
#                 if tok_folded in TARGET_BLACKLIST:
#                     continue
#                 target_id = headword_to_entry_id.get(tok_folded, 0)
#                 if not target_id or target_id == donor_id:
#                     continue
#                 triggers_union |= gloss_triggers
#                 if len(gloss_str) > best_gloss_len:
#                     best_gloss_len = len(gloss_str)
#                     best_target_id = target_id
#                     best_target_hw = tok
#                     best_gloss = gloss_str
#                 break
#
#         if best_target_id and triggers_union:
#             out["donor_to_target"][donor_id] = best_target_id
#             out["synthetic_tags_by_donor"][donor_id] = sorted(triggers_union)
#             out["donor_surface_by_donor"][donor_id] = donor_hw
#             out["donor_romanization_by_donor"][donor_id] = str(row["romanization"] or "").strip()
#             out["donor_gloss_by_donor"][donor_id] = best_gloss
#             out["target_headword_by_donor"][donor_id] = best_target_hw
#
#     return out


CODELIKE_TEXT_EXEMPT_DBS = frozenset(
    {
        "ja",
        "ja-jmdict",
        "ko",
        "ko-krdict",
        "zh",
        "zh-cc-cedict",
        "zh-hant",
        "zh-hant-cc-cedict",
        "lzh",
        "lzh-wiktionary",
        "vi",
    }
)

RULE_A_EXEMPT_TAGS = frozenset(
    {
        "baybayin",
        "hanja",
        "hangeul",
        "cjk",
        "hán-nôm",
        "han-nom",
        "hannom",
    }
)

ALWAYS_KEEP_TAGS = frozenset(
    {
        "reading",
        "romanization",
        "romanisation",
        "transliteration",
        "baybayin",
        "hanja",
        "hangeul",
        "hangul",
        "cjk",
        "hán-nôm",
        "han-nom",
        "hannom",
        "hiragana",
        "katakana",
        "romaji",
        "pinyin",
        "bopomofo",
        "jyutping",
        "kana",
        "revised",
    }
)

ALWAYS_KEEP_TAG_SUBSTRINGS = (
    "romanization",
    "romanisation",
    "transliteration",
    "reading",
    "romaji",
    "pinyin",
    "bopomofo",
    "jyutping",
    "mccune",
    "revised romanization",
    "yale",
)

FANOUT_EXEMPT_DBS = frozenset(
    {
        "ja",
        "ja-jmdict",
        "ko",
        "ko-krdict",
        "grc",
        "lzh",
        "lzh-wiktionary",
        "zh",
        "zh-cc-cedict",
        "zh-hant",
        "zh-hant-cc-cedict",
    }
)

FORM_EXACT_BLACKLISTS: dict[str, frozenset[str]] = {
    "ja": frozenset(
        {
            "For other desiderative forms",
            "intransitive godan",
            "intransitive ichidan",
        }
    ),
    "ko": frozenset(
        {
            "no hanja",
            "—時計",
        }
    ),
    "ko-krdict": frozenset(
        {
            "no hanja",
            "—時計",
        }
    ),
    "grc": frozenset(
        {
            "Second declension",
            "Third declension",
            "First declension",
            "First and second declension",
            "first",
            "third declension",
            "declension",
            "εἶμεν",
            "εἶτε",
            "εἶτον",
            "εἴτην",
            "tēîsĭnĭ",
            "tēîsĭnĭn",
            "toîs",
            "τῷ",
            "τοῖς",
            "τοῦ",
            "οἱ",
            "ὁ",
            "τὸν",
            "τοῖσῐ",
            "τοῖσῐν",
            "τοὺς",
            "-σῐν",
            "τᾱ́ν",
        }
    ),
}

FORM_EXACT_WHITELISTS: dict[str, frozenset[str]] = {
    "ar": frozenset(
        {
            "إِنْجْلِيزِيَّة",
            "إِنْقْلِيزِيَّة",
            "إِنْكْلِيزِيَّة",
        }
    ),
    "hi": frozenset(
        {
            "انتظار",
        }
    ),
    "it": frozenset(
        {
            "guard rail",
            "guard-rail",
            "guardaraglio",
            "guardarai",
            "guardarail",
            "guardaraile",
            "guardaraille",
            "guardarailo",
            "guardarrai",
            "guardarrail",
            "guardarraile",
            "guardarraille",
            "guardrail",
        }
    ),
    "pt": frozenset(
        {
            "meya",
        }
    ),
    "ta": frozenset(
        {
            "ஆகுவது",
        }
    ),
    "tl": frozenset(
        {
            "ᜋᜄ᜔",
            "ᜒᜈ᜔",
            "ᜓᜋ᜔",
            "ᜋᜅ᜔",
            "ᜂᜋ᜔",
            "ᜁ",
            "ᜈᜅ᜔",
            "ᜐᜎ",
            "ᜂ",
            "ᜉᜒᜉᜒ",
            "ᜇᜒ",
            "ᜉᜉ",
            "ᜋᜓᜎᜒ",
            "ᜐᜒ",
        }
    ),
    "vi": frozenset(
        {
            "折",
        }
    ),
}


def _flatten_gloss_node(node: object, out: list[str]) -> None:
    if isinstance(node, str):
        text = node.strip()
        if text:
            out.append(text)
        return
    if isinstance(node, dict):
        glosses = node.get("glosses")
        if isinstance(glosses, list):
            for item in glosses:
                _flatten_gloss_node(item, out)
        for key in ("gloss", "text", "definition", "def"):
            value = node.get(key)
            if isinstance(value, str):
                text = value.strip()
                if text:
                    out.append(text)
        return
    if isinstance(node, list):
        for item in node:
            _flatten_gloss_node(item, out)


def parse_glosses(raw_glosses: str) -> tuple[list[str], bool]:
    text = str(raw_glosses or "").strip()
    if not text:
        return [], False
    parse_error = False
    parsed: object = text
    if text[:1] in "[{":
        try:
            parsed = json.loads(text)
        except Exception:
            parse_error = True
            parsed = text
    out: list[str] = []
    _flatten_gloss_node(parsed, out)
    if out:
        return out, parse_error
    if isinstance(parsed, str):
        parts = [part.strip() for part in parsed.split(";") if part.strip()]
        return parts, parse_error
    return out, parse_error


@lru_cache(maxsize=250000)
def _has_any_letter(text: str) -> bool:
    for ch in str(text or ""):
        if unicodedata.category(ch).startswith("L"):
            return True
    return False


@lru_cache(maxsize=250000)
def _char_script(ch: str) -> str:
    code = ord(ch)
    if (
        0x0041 <= code <= 0x024F
        or 0x1E00 <= code <= 0x1EFF
        or 0x2C60 <= code <= 0x2C7F
        or 0xA720 <= code <= 0xA7FF
    ):
        return "Latin"
    if 0x0370 <= code <= 0x03FF or 0x1F00 <= code <= 0x1FFF:
        return "Greek"
    if (
        0x0400 <= code <= 0x052F
        or 0x2DE0 <= code <= 0x2DFF
        or 0xA640 <= code <= 0xA69F
        or 0x1C80 <= code <= 0x1C8F
    ):
        return "Cyrillic"
    if 0x0590 <= code <= 0x05FF or 0xFB1D <= code <= 0xFB4F:
        return "Hebrew"
    if (
        0x0600 <= code <= 0x06FF
        or 0x0750 <= code <= 0x077F
        or 0x0870 <= code <= 0x089F
        or 0x08A0 <= code <= 0x08FF
        or 0xFB50 <= code <= 0xFDFF
        or 0xFE70 <= code <= 0xFEFF
    ):
        return "Arabic"
    if (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2A6DF
        or 0x2A700 <= code <= 0x2B73F
        or 0x2B740 <= code <= 0x2B81F
        or 0x2B820 <= code <= 0x2CEAF
        or 0x2CEB0 <= code <= 0x2EBEF
        or 0x30000 <= code <= 0x3134F
    ):
        return "Han"
    return "Other"


@lru_cache(maxsize=250000)
def _has_latin_letter(text: str) -> bool:
    s = str(text or "")
    if ASCII_LETTER_RE.search(s):
        return True
    for ch in s:
        if not unicodedata.category(ch).startswith("L"):
            continue
        if _char_script(ch) == "Latin":
            return True
    return False


def gloss_bucket(raw_glosses: str) -> str:
    glosses, _parse_error = parse_glosses(raw_glosses)
    if not glosses:
        return "missing"
    has_letter = any(_has_any_letter(gloss) for gloss in glosses)
    has_latin = any(_has_latin_letter(gloss) for gloss in glosses)
    if not has_letter:
        return "symbol_only"
    if not has_latin:
        return "non_latin_only"
    return "ok"


def entry_cut_reason(raw_glosses: str) -> str:
    bucket = gloss_bucket(raw_glosses)
    if bucket == "missing":
        return "gloss_missing"
    if bucket == "symbol_only":
        return "gloss_symbol_only"
    if bucket == "non_latin_only":
        return "gloss_non_latin_only"
    return ""


def normalize_db_name(db_name: str) -> str:
    return str(db_name or "").strip().casefold()


def normalize_text(text: str) -> str:
    return str(text or "").strip()


def split_tags(raw_tags: str | Iterable[str]) -> list[str]:
    if isinstance(raw_tags, str):
        src = raw_tags.split(";")
    else:
        src = list(raw_tags or [])
    out: list[str] = []
    seen: set[str] = set()
    for tag in src:
        text = str(tag or "").strip()
        if not text:
            continue
        folded = unicodedata.normalize("NFKC", text).casefold()
        if folded in seen:
            continue
        seen.add(folded)
        out.append(text)
    return out


def split_tags_casefold(raw_tags: str | Iterable[str]) -> set[str]:
    out: set[str] = set()
    for tag in split_tags(raw_tags):
        out.add(unicodedata.normalize("NFKC", tag).casefold())
    return out


def has_always_keep_tag(raw_tags: str | Iterable[str]) -> bool:
    for tag in split_tags_casefold(raw_tags):
        if tag in ALWAYS_KEEP_TAGS:
            return True
        for needle in ALWAYS_KEEP_TAG_SUBSTRINGS:
            if needle in tag:
                return True
    return False


def word_count(text: str) -> int:
    return len([part for part in re.split(r"\s+", normalize_text(text)) if part])


def is_fanout_exempt_db(db_name: str) -> bool:
    return normalize_db_name(db_name) in FANOUT_EXEMPT_DBS


def is_exact_whitelist(db_name: str, form_text: str) -> bool:
    return normalize_text(form_text) in FORM_EXACT_WHITELISTS.get(
        normalize_db_name(db_name), frozenset()
    )


def is_exact_blacklist(db_name: str, form_text: str) -> bool:
    return normalize_text(form_text) in FORM_EXACT_BLACKLISTS.get(
        normalize_db_name(db_name), frozenset()
    )


def occurrence_tag_cut_reason(raw_tags: str | Iterable[str]) -> str:
    tags_folded = split_tags_casefold(raw_tags)
    for tag in sorted(tags_folded):
        if tag in HARD_DROP_TAGS:
            return f"hard_tag:{tag}"
    return ""


def _looks_broken_template(text: str) -> bool:
    s = normalize_text(text)
    if not s:
        return False
    if BROKEN_TEMPLATE_RE.search(s):
        return True
    if s.count("(") != s.count(")"):
        return True
    return False


def _looks_english_prose(text: str) -> bool:
    s = normalize_text(text)
    if word_count(s) < 4:
        return False
    if not ASCII_LETTER_RE.search(s):
        return False
    if ENGLISH_PROSE_HINT_RE.search(s):
        return True
    if "." in s or ":" in s:
        return True
    return False


def _looks_hebrew_mishkal_placeholder(text: str) -> bool:
    s = normalize_text(text)
    if not s:
        return False
    if not HEBREW_MISHKAL_RE.match(s):
        return False
    base = "".join(
        ch for ch in unicodedata.normalize("NFKD", s) if unicodedata.category(ch).startswith("L")
    )
    if not base:
        return False
    return "קטל" in base or "קטר" in base


def occurrence_text_cut_reason(db_name: str, form_text: str) -> str:
    s = normalize_text(form_text)
    if not s:
        return "hard_text:blank"
    if ALTERNATION_LABEL_RE.match(s):
        return "hard_text:alternation_label"
    db_name_folded = normalize_db_name(db_name)
    if db_name_folded not in CODELIKE_TEXT_EXEMPT_DBS:
        if ROMAN_NUMERAL_RE.match(s):
            return "hard_text:roman_numeral"
        if CLASS_CODE_RE.match(s):
            return "hard_text:class_code"
    if _looks_broken_template(s):
        return "hard_text:template_leak"
    if _looks_english_prose(s):
        return "hard_text:english_prose"
    if _looks_hebrew_mishkal_placeholder(s):
        return "hard_text:hebrew_placeholder"
    return ""


def rule_a_exempt(db_name: str, raw_tags: str | Iterable[str]) -> bool:
    if normalize_db_name(db_name) in RULE_A_EXEMPT_DBS:
        return True
    if has_always_keep_tag(raw_tags):
        return True
    return bool(split_tags_casefold(raw_tags) & RULE_A_EXEMPT_TAGS)


def occurrence_rule_a_cut_reason(
    db_name: str, form_text: str, headword: str, raw_tags: str | Iterable[str]
) -> str:
    if rule_a_exempt(db_name, raw_tags):
        return ""
    if word_count(form_text) != word_count(headword):
        return "rule_a_word_count"
    return ""


def _hyphen_affix_mismatch(form_text: str, headword: str) -> bool:
    f = str(form_text or "")
    h = str(headword or "")
    f_aff = f.startswith("-") or f.endswith("-")
    h_aff = h.startswith("-") or h.endswith("-")
    return f_aff and not h_aff


def _zero_overlap_cross_script(form_text: str, headword: str) -> bool:
    f = str(form_text or "")
    h = str(headword or "")
    if not f or not h:
        return False
    f_scripts = {_char_script(ch) for ch in f if unicodedata.category(ch).startswith("L")}
    h_scripts = {_char_script(ch) for ch in h if unicodedata.category(ch).startswith("L")}
    if not f_scripts or not h_scripts:
        return False
    if f_scripts & h_scripts:
        return False
    if set(f) & set(h):
        return False
    return True


def occurrence_cut_reason(
    db_name: str, form_text: str, headword: str, raw_tags: str | Iterable[str]
) -> str:
    if str(form_text or "") == str(headword or "") and form_text:
        return "hard_text:identical_to_headword"
    if _hyphen_affix_mismatch(form_text, headword):
        return "hard_text:hyphen_affix_mismatch"
    if is_exact_whitelist(db_name, form_text) or has_always_keep_tag(raw_tags):
        return ""
    if is_exact_blacklist(db_name, form_text):
        return "exact_blacklist"
    tag_reason = occurrence_tag_cut_reason(raw_tags)
    if tag_reason:
        return tag_reason
    text_reason = occurrence_text_cut_reason(db_name, form_text)
    if text_reason:
        return text_reason
    if normalize_db_name(db_name) not in CODELIKE_TEXT_EXEMPT_DBS:
        if _zero_overlap_cross_script(form_text, headword):
            return "hard_text:zero_overlap_cross_script"
    rule_a_reason = occurrence_rule_a_cut_reason(db_name, form_text, headword, raw_tags)
    if rule_a_reason:
        return rule_a_reason
    return ""


def surface_fanout_cut_reason(db_name: str, form_text: str, entry_fanout_count: int) -> str:
    if is_exact_whitelist(db_name, form_text):
        return ""
    if is_exact_blacklist(db_name, form_text):
        return "exact_blacklist"
    if is_fanout_exempt_db(db_name):
        return ""
    if int(entry_fanout_count or 0) > 10:
        return "fanout_gt_10"
    return ""


def choose_bucket_cut_reason(cut_reasons: Iterable[str]) -> str:
    reasons = list(cut_reasons or [])
    if not reasons:
        return ""
    if "exact_blacklist" in reasons:
        return "exact_blacklist"
    for prefix in ("hard_tag:", "hard_text:", "rule_a_word_count", "fanout_gt_10"):
        for reason in reasons:
            if reason == prefix or reason.startswith(prefix):
                return reason
    return reasons[0]
