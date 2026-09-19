"""
Build an Ancient Greek LSJ SQLite database directly from the Perseus lexica ZIP.

This bypasses the broken TSV conversion and writes the active SQLite schema that
the app already uses for hydration and compact-index generation.
"""

from __future__ import annotations

import copy
import json
import re
import sqlite3
import sys
import time
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from dict_lookup_sqlite import _normalize_keys_via_js


APP_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ZIP_PATH = (
    APP_ROOT / "wiktionary general pipeline" / "rawjsonforconversion" / "lexica-master.zip"
)
DEFAULT_DB_PATH = APP_ROOT / "dict_sqlite" / "grc-lsj.sqlite"

LANG_CODE = "grc"
SOURCE_LABEL = "lsj"

ENTRY_BATCH_SIZE = 5000
NORMALIZE_BATCH_SIZE = 50000

GREEK_BASE_MAP = {
    "a": "a",
    "b": "b",
    "g": "g",
    "d": "d",
    "e": "e",
    "z": "z",
    "h": "h",
    "q": "q",
    "i": "i",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "c": "c",
    "o": "o",
    "p": "p",
    "r": "r",
    "s": "s",
    "t": "t",
    "u": "u",
    "f": "f",
    "x": "x",
    "y": "y",
    "w": "w",
    "v": "v",
}

UNICODE_GREEK_MAP = {
    "a": "a",
    "b": "b",
    "g": "g",
    "d": "d",
    "e": "e",
    "z": "z",
    "h": "e",
    "q": "th",
    "i": "i",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "c": "x",
    "o": "o",
    "p": "p",
    "r": "r",
    "s": "s",
    "t": "t",
    "u": "u",
    "f": "ph",
    "x": "kh",
    "y": "ps",
    "w": "o",
    "v": "w",
}

GREEK_CHAR_MAP = {
    "a": "a",
    "b": "b",
    "g": "g",
    "d": "d",
    "e": "e",
    "z": "z",
    "h": "e",
    "q": "th",
    "i": "i",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "c": "x",
    "o": "o",
    "p": "p",
    "r": "r",
    "s": "s",
    "t": "t",
    "u": "u",
    "f": "ph",
    "x": "kh",
    "y": "ps",
    "w": "o",
    "v": "w",
}

BETA_TO_GREEK = {
    "a": "alpha",
    "b": "beta",
    "g": "gamma",
    "d": "delta",
    "e": "epsilon",
    "z": "zeta",
    "h": "eta",
    "q": "theta",
    "i": "iota",
    "k": "kappa",
    "l": "lambda",
    "m": "mu",
    "n": "nu",
    "c": "xi",
    "o": "omicron",
    "p": "pi",
    "r": "rho",
    "s": "sigma",
    "t": "tau",
    "u": "upsilon",
    "f": "phi",
    "x": "chi",
    "y": "psi",
    "w": "omega",
    "v": "digamma",
}

ROMAN_BASE_MAP = {
    "alpha": "a",
    "beta": "b",
    "gamma": "g",
    "delta": "d",
    "epsilon": "e",
    "zeta": "z",
    "eta": "e",
    "theta": "th",
    "iota": "i",
    "kappa": "k",
    "lambda": "l",
    "mu": "m",
    "nu": "n",
    "xi": "x",
    "omicron": "o",
    "pi": "p",
    "rho": "r",
    "sigma": "s",
    "tau": "t",
    "upsilon": "u",
    "phi": "ph",
    "chi": "kh",
    "psi": "ps",
    "omega": "o",
    "digamma": "w",
}

BETA_MODIFIERS = set("*()/=\\+|^_")
ROMANIZATION_VOWELS = set("aeiouAEIOU")
SKIP_PROSE_TAGS = {
    "orth",
    "gen",
    "itype",
    "foreign",
    "bibl",
    "author",
    "title",
    "biblScope",
    "cit",
    "quote",
    "ref",
    "xr",
    "lbl",
    "etym",
    "gramGrp",
    "gram",
    "date",
    "placeName",
    "num",
    "pb",
    "note",
    "sic",
    "corr",
}
POS_MAP = {
    "adv.": "adv",
    "adj.": "adj",
    "subst.": "noun",
}
STOP_FORM_TOKENS = {
    "",
    "indecl",
    "indecl.",
    "indeclinable",
    "contr",
    "contr.",
    "ep",
    "ep.",
    "dor",
    "dor.",
    "ion",
    "ion.",
    "att",
    "att.",
    "lacon",
    "lacon.",
    "boeot",
    "boeot.",
    "v",
}
STOP_TR_GLOSSES = {
    "n",
    "n^",
    "nˆ",
    "ne",
    "sm-",
    "sems",
}
STOP_FALLBACK_GLOSSES = {
    "cf",
    "cf.",
    "q.v",
    "q.v.",
    "etc",
    "etc.",
}

TAG_RE = re.compile(r"\s+")
ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
GREEK_LETTER_RE = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")
BAD_GLOSS_CHARS_RE = re.compile(r"[^A-Za-z '\-]")
TRAILING_PUNCT_RE = re.compile(r"[,:;.\s]+$")
LEADING_PUNCT_RE = re.compile(r"^[,:;.\s]+")


@dataclass
class ParsedEntry:
    headword: str
    romanization: str
    pos: str
    glosses_json: str
    forms_json: str
    entry_id: str
    source: str
    forms: list[tuple[str, str, str]]


def _tag_name(node: ET.Element) -> str:
    return node.tag.split("}", 1)[-1]


def _clean_whitespace(text: str) -> str:
    return TAG_RE.sub(" ", str(text or "")).strip()


def _strip_edge_punct(text: str) -> str:
    cleaned = LEADING_PUNCT_RE.sub("", str(text or ""))
    return TRAILING_PUNCT_RE.sub("", cleaned).strip()


def _has_future_base(word: str, start_index: int) -> bool:
    for idx in range(start_index, len(word)):
        ch = word[idx]
        if ch.isalpha():
            return True
        if ch in BETA_MODIFIERS or ch in "-'":
            continue
    return False


def _beta_base_to_unicode(base: str, uppercase: bool, final_sigma: bool) -> str:
    base = str(base or "").lower()
    if base == "s":
        char = "s" if not final_sigma else "s"
    else:
        char = base
    greek_name = BETA_TO_GREEK.get(char)
    if not greek_name:
        return base

    if greek_name == "alpha":
        out = "a"
    elif greek_name == "beta":
        out = "b"
    elif greek_name == "gamma":
        out = "g"
    elif greek_name == "delta":
        out = "d"
    elif greek_name == "epsilon":
        out = "e"
    elif greek_name == "zeta":
        out = "z"
    elif greek_name == "eta":
        out = "h"
    elif greek_name == "theta":
        out = "q"
    elif greek_name == "iota":
        out = "i"
    elif greek_name == "kappa":
        out = "k"
    elif greek_name == "lambda":
        out = "l"
    elif greek_name == "mu":
        out = "m"
    elif greek_name == "nu":
        out = "n"
    elif greek_name == "xi":
        out = "c"
    elif greek_name == "omicron":
        out = "o"
    elif greek_name == "pi":
        out = "p"
    elif greek_name == "rho":
        out = "r"
    elif greek_name == "sigma":
        out = "s" if not final_sigma else "j"
    elif greek_name == "tau":
        out = "t"
    elif greek_name == "upsilon":
        out = "u"
    elif greek_name == "phi":
        out = "f"
    elif greek_name == "chi":
        out = "x"
    elif greek_name == "psi":
        out = "y"
    elif greek_name == "omega":
        out = "w"
    elif greek_name == "digamma":
        out = "v"
    else:
        out = base

    greek_char = {
        "a": "a",
        "b": "b",
        "g": "g",
        "d": "d",
        "e": "e",
        "z": "z",
        "h": "h",
        "q": "q",
        "i": "i",
        "k": "k",
        "l": "l",
        "m": "m",
        "n": "n",
        "c": "c",
        "o": "o",
        "p": "p",
        "r": "r",
        "s": "s",
        "j": "j",
        "t": "t",
        "u": "u",
        "f": "f",
        "x": "x",
        "y": "y",
        "w": "w",
        "v": "v",
    }[out]

    greek_real = {
        "a": "\u03b1",
        "b": "\u03b2",
        "g": "\u03b3",
        "d": "\u03b4",
        "e": "\u03b5",
        "z": "\u03b6",
        "h": "\u03b7",
        "q": "\u03b8",
        "i": "\u03b9",
        "k": "\u03ba",
        "l": "\u03bb",
        "m": "\u03bc",
        "n": "\u03bd",
        "c": "\u03be",
        "o": "\u03bf",
        "p": "\u03c0",
        "r": "\u03c1",
        "s": "\u03c3",
        "j": "\u03c2",
        "t": "\u03c4",
        "u": "\u03c5",
        "f": "\u03c6",
        "x": "\u03c7",
        "y": "\u03c8",
        "w": "\u03c9",
        "v": "\u03dd",
    }[greek_char]
    return greek_real.upper() if uppercase else greek_real


def betacode_to_greek(text: str) -> str:
    raw = str(text or "")
    out: list[str] = []
    pending_mods: list[str] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch in "<>[]&":
            i += 1
            continue
        if ch in BETA_MODIFIERS:
            pending_mods.append(ch)
            i += 1
            continue
        if ch.isalpha():
            base = ch.lower()
            mods = list(pending_mods)
            pending_mods = []
            j = i + 1
            while j < len(raw) and raw[j] in BETA_MODIFIERS:
                mods.append(raw[j])
                j += 1
            uppercase = "*" in mods
            final_sigma = base == "s" and not _has_future_base(raw, j)
            greek = _beta_base_to_unicode(base, uppercase, final_sigma)
            combines: list[str] = []
            if "(" in mods:
                combines.append("\u0314")
            elif ")" in mods:
                combines.append("\u0313")
            if "+" in mods:
                combines.append("\u0308")
            if "|" in mods:
                combines.append("\u0345")
            if "/" in mods:
                combines.append("\u0301")
            elif "\\" in mods:
                combines.append("\u0300")
            elif "=" in mods:
                combines.append("\u0342")
            out.append(unicodedata.normalize("NFC", greek + "".join(combines)))
            i = j
            continue
        out.append(ch)
        i += 1
    return unicodedata.normalize("NFC", "".join(out))


def _apply_roman_diacritic(text: str, mark: str) -> str:
    if not text:
        return text
    chars = list(text)
    index = 1 if len(chars) > 1 and chars[0].lower() == "h" else 0
    chars[index] = unicodedata.normalize("NFC", chars[index] + mark)
    return "".join(chars)


def greek_to_romanization(text: str) -> str:
    out: list[str] = []
    for raw_char in str(text or ""):
        if not raw_char:
            continue
        decomp = unicodedata.normalize("NFD", raw_char)
        if not decomp:
            continue
        base = decomp[0]
        mods = decomp[1:]
        lower_base = base.lower()
        if lower_base == "\u03c2":
            lower_base = "\u03c3"
        if lower_base == "\u03dd":
            base_key = "digamma"
        else:
            greek_name = {
                "\u03b1": "alpha",
                "\u03b2": "beta",
                "\u03b3": "gamma",
                "\u03b4": "delta",
                "\u03b5": "epsilon",
                "\u03b6": "zeta",
                "\u03b7": "eta",
                "\u03b8": "theta",
                "\u03b9": "iota",
                "\u03ba": "kappa",
                "\u03bb": "lambda",
                "\u03bc": "mu",
                "\u03bd": "nu",
                "\u03be": "xi",
                "\u03bf": "omicron",
                "\u03c0": "pi",
                "\u03c1": "rho",
                "\u03c3": "sigma",
                "\u03c4": "tau",
                "\u03c5": "upsilon",
                "\u03c6": "phi",
                "\u03c7": "chi",
                "\u03c8": "psi",
                "\u03c9": "omega",
            }.get(lower_base)
            if not greek_name:
                out.append(raw_char)
                continue
            base_key = greek_name

        roman = ROMAN_BASE_MAP[base_key]
        if base.isupper():
            roman = roman[:1].upper() + roman[1:]
        if "\u0314" in mods:
            roman = ("H" if roman[:1].isupper() else "h") + roman
        if "\u0345" in mods:
            roman += "i"
        if "\u0301" in mods:
            roman = _apply_roman_diacritic(roman, "\u0301")
        elif "\u0300" in mods:
            roman = _apply_roman_diacritic(roman, "\u0300")
        elif "\u0342" in mods:
            roman = _apply_roman_diacritic(roman, "\u0302")
        if "\u0308" in mods:
            roman = _apply_roman_diacritic(roman, "\u0308")
        out.append(unicodedata.normalize("NFC", roman))
    return "".join(out)


def _clean_beta_surface(raw_text: str) -> str:
    text = betacode_to_greek(raw_text)
    text = text.replace("[", "").replace("]", "").replace("<", "").replace(">", "")
    text = _clean_whitespace(text)
    return _strip_edge_punct(text)


def _clean_gloss_text(raw_text: str) -> str:
    text = _clean_whitespace(raw_text)
    text = text.replace("Gr.", "Greek")
    text = text.replace("gr.", "Greek")
    text = re.sub(r"\(\s*q\.v\.\s*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    text = _strip_edge_punct(text)
    return text


def _score_headword_candidate(text: str) -> tuple[int, int]:
    alpha_count = sum(1 for ch in text if GREEK_LETTER_RE.match(ch))
    has_space = 1 if " " in text else 0
    return (alpha_count, -has_space)


def _extract_top_level_orths(entry: ET.Element) -> list[tuple[str, str, ET.Element]]:
    out: list[tuple[str, str, ET.Element]] = []
    for child in list(entry):
        if _tag_name(child) != "orth":
            continue
        raw_text = "".join(child.itertext()).strip()
        clean = _clean_beta_surface(raw_text)
        if not clean:
            continue
        out.append((raw_text, clean, child))
    return out


def _choose_primary_orth(orths: list[tuple[str, str, ET.Element]]) -> int:
    best_index = 0
    best_score = (-1, -1)
    for idx, (_, clean, _node) in enumerate(orths):
        score = _score_headword_candidate(clean)
        if score > best_score:
            best_score = score
            best_index = idx
    return best_index


def _add_text_from_node(node: ET.Element, out: list[str]) -> None:
    if _tag_name(node) not in SKIP_PROSE_TAGS and node.text:
        out.append(node.text)
    for child in list(node):
        if _tag_name(child) not in SKIP_PROSE_TAGS:
            _add_text_from_node(child, out)
        if child.tail:
            out.append(child.tail)


def _extract_explicit_glosses(entry: ET.Element, limit: int = 3) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for node in entry.iter():
        if _tag_name(node) != "tr":
            continue
        gloss = _clean_gloss_text("".join(node.itertext()))
        if not gloss:
            continue
        lower = gloss.lower()
        if lower in STOP_TR_GLOSSES:
            continue
        if BAD_GLOSS_CHARS_RE.search(gloss):
            continue
        if lower in seen:
            continue
        seen.add(lower)
        out.append(gloss)
        if len(out) >= limit:
            break
    return out


def _extract_english_fallback(entry: ET.Element) -> str:
    parts: list[str] = []
    _add_text_from_node(entry, parts)
    text = _clean_gloss_text(" ".join(parts))
    if not text:
        return ""
    if not ASCII_LETTER_RE.search(text):
        return ""
    if text.lower() in STOP_FALLBACK_GLOSSES:
        return ""
    if len(text) <= 3:
        return ""
    if len(text) > 220:
        text = text[:220].rsplit(" ", 1)[0].strip()
    return text


def _extract_greek_fallback(entry: ET.Element, limit: int = 3) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for node in entry.iter():
        if _tag_name(node) != "foreign":
            continue
        text = _clean_beta_surface("".join(node.itertext()))
        if not text or not GREEK_LETTER_RE.search(text):
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _extract_glosses(entry: ET.Element) -> list[str]:
    explicit = _extract_explicit_glosses(entry)
    if explicit:
        return explicit
    fallback = _extract_english_fallback(entry)
    if fallback:
        return [fallback]
    return _extract_greek_fallback(entry)


def _map_pos_text(raw_pos: str) -> str:
    text = _clean_whitespace(raw_pos).lower()
    return POS_MAP.get(text, text.rstrip("."))


def _extract_pos(entry: ET.Element, primary_orth: ET.Element, english_fallback: str) -> str:
    extent = str(primary_orth.attrib.get("extent", "") or "").strip().lower()
    if extent == "pref":
        return "prefix"
    if extent == "suff":
        return "suffix"

    direct_pos_values: list[str] = []
    nested_pos_values: list[str] = []
    has_gen = False
    has_itype = False

    for child in list(entry):
        tag_name = _tag_name(child)
        if tag_name == "pos":
            mapped = _map_pos_text("".join(child.itertext()))
            if mapped:
                direct_pos_values.append(mapped)
        elif tag_name == "gen":
            has_gen = True
        elif tag_name == "itype":
            has_itype = True

    for node in entry.iter():
        tag_name = _tag_name(node)
        if tag_name == "gen":
            has_gen = True
        elif tag_name == "itype":
            has_itype = True
        elif tag_name == "pos":
            mapped = _map_pos_text("".join(node.itertext()))
            if mapped:
                nested_pos_values.append(mapped)

    if direct_pos_values:
        return direct_pos_values[0]

    if has_gen:
        return "noun"

    if has_itype:
        orth_text = _clean_beta_surface("".join(primary_orth.itertext()))
        if (
            orth_text.endswith("ω")
            or orth_text.endswith("ομαι")
            or orth_text.endswith("μαι")
            or orth_text.endswith("μι")
        ):
            return "verb"
        return "adj"

    if nested_pos_values:
        return nested_pos_values[0]

    fallback = english_fallback.lower()
    if "exclamation" in fallback or "interjection" in fallback:
        return "intj"
    if "prefix" in fallback:
        return "prefix"
    if "suffix" in fallback:
        return "suffix"
    return ""


def _normalize_form_source(raw_text: str) -> str:
    text = _clean_whitespace(raw_text)
    text = text.replace(" ,", ",")
    text = text.replace(" ;", ";")
    return text


def _looks_like_full_form(token: str, source_tag: str) -> bool:
    raw = str(token or "").strip()
    if not raw:
        return False
    lowered = raw.lower().rstrip(".")
    if lowered in STOP_FORM_TOKENS:
        return False
    if " " in raw:
        return False
    if any(ch in raw for ch in "<>[]:&"):
        return False

    alpha_len = sum(1 for ch in raw if ch.isalpha())
    has_beta_marks = any(ch in raw for ch in "/\\=()|+*^_'-")
    if source_tag == "gen":
        if alpha_len >= 4:
            return True
        if alpha_len >= 3 and has_beta_marks:
            return True
        return False
    if source_tag == "itype":
        if alpha_len >= 4:
            return True
        if alpha_len >= 3 and has_beta_marks:
            return True
        return False
    return False


def _extract_forms(
    entry: ET.Element, orths: list[tuple[str, str, ET.Element]], primary_index: int
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    top_level_orth_nodes = {node for _raw, _clean, node in orths}

    def add_form(form_text: str, tag: str, raw_source: str) -> None:
        clean = _clean_beta_surface(raw_source if raw_source else form_text)
        if not clean:
            return
        key = (clean, tag)
        if key in seen:
            return
        seen.add(key)
        out.append((clean, tag, greek_to_romanization(clean)))

    for idx, (raw_text, clean, _node) in enumerate(orths):
        if idx == primary_index:
            continue
        add_form(clean, "variant=orth", raw_text)

    for node in entry.iter():
        if _tag_name(node) != "orth" or node in top_level_orth_nodes:
            continue
        raw_text = "".join(node.itertext()).strip()
        if not raw_text:
            continue
        add_form(raw_text, "variant=orth", raw_text)

    for node in entry.iter():
        tag_name = _tag_name(node)
        if tag_name not in {"gen", "itype"}:
            continue
        raw_text = _normalize_form_source("".join(node.itertext()))
        if not raw_text:
            continue
        if " " in raw_text and "," not in raw_text and ";" not in raw_text:
            continue
        for part in re.split(r"[;,]", raw_text):
            token = part.strip()
            if not _looks_like_full_form(token, tag_name):
                continue
            add_form(token, f"form_type={tag_name}", token)
    return out


def _split_gloss_entry(entry: ET.Element) -> list[ET.Element]:
    children = list(entry)
    orth_indices = [idx for idx, child in enumerate(children) if _tag_name(child) == "orth"]
    if len(orth_indices) <= 1:
        return [entry]

    out: list[ET.Element] = []
    for seg_idx, start in enumerate(orth_indices):
        end = orth_indices[seg_idx + 1] if seg_idx + 1 < len(orth_indices) else len(children)
        wrapper = ET.Element("entryFree", attrib=dict(entry.attrib))
        for child in children[start:end]:
            wrapper.append(copy.deepcopy(child))
        out.append(wrapper)
    return out or [entry]


def _build_parsed_entry(entry: ET.Element, *, entry_id: str) -> ParsedEntry | None:
    orths = _extract_top_level_orths(entry)
    if not orths:
        return None
    primary_index = _choose_primary_orth(orths)
    _raw_headword, headword, primary_node = orths[primary_index]
    if not headword:
        return None

    gloss_list = _extract_glosses(entry)
    english_fallback = _extract_english_fallback(entry)
    pos = _extract_pos(entry, primary_node, english_fallback)
    forms = _extract_forms(entry, orths, primary_index)
    glosses_json = json.dumps(
        [{"glosses": gloss_list}] if gloss_list else [], ensure_ascii=False, separators=(",", ":")
    )
    forms_json = json.dumps(
        [[form_text, tag, roman] for form_text, tag, roman in forms],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return ParsedEntry(
        headword=headword,
        romanization=greek_to_romanization(headword),
        pos=pos,
        glosses_json=glosses_json,
        forms_json=forms_json,
        entry_id=entry_id,
        source=SOURCE_LABEL,
        forms=forms,
    )


def _iter_xml_names(zf: zipfile.ZipFile) -> list[str]:
    return sorted(name for name in zf.namelist() if name.endswith(".xml") and "/grc/lsj/" in name)


def _parse_entries(zip_path: Path) -> list[ParsedEntry]:
    parsed: list[ParsedEntry] = []
    with zipfile.ZipFile(zip_path) as zf:
        xml_names = _iter_xml_names(zf)
        for xml_name in xml_names:
            print(f"  Parsing {Path(xml_name).name}...")
            with zf.open(xml_name) as fh:
                for _event, elem in ET.iterparse(fh, events=("end",)):
                    if _tag_name(elem) != "entryFree":
                        continue
                    entry_type = str(elem.attrib.get("type", "") or "").strip().lower()
                    entry_id_base = str(
                        elem.attrib.get("id", "") or elem.attrib.get("key", "") or ""
                    ).strip()
                    chunks = _split_gloss_entry(elem) if entry_type == "gloss" else [elem]
                    for chunk_index, chunk in enumerate(chunks, start=1):
                        entry_id = entry_id_base
                        if len(chunks) > 1 and entry_id:
                            entry_id = f"{entry_id}.{chunk_index}"
                        parsed_entry = _build_parsed_entry(chunk, entry_id=entry_id)
                        if parsed_entry is not None:
                            parsed.append(parsed_entry)
                    elem.clear()
    return parsed


def _batch_normalize(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    unique_pairs = list(dict.fromkeys(pairs))
    for start in range(0, len(unique_pairs), NORMALIZE_BATCH_SIZE):
        chunk = unique_pairs[start : start + NORMALIZE_BATCH_SIZE]
        out.update(_normalize_keys_via_js(chunk))
        print(
            f"  Normalized {min(start + len(chunk), len(unique_pairs)):,} / {len(unique_pairs):,} texts..."
        )
    return out


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS forms;
        DROP TABLE IF EXISTS entries;
        DROP TABLE IF EXISTS meta;

        CREATE TABLE entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            headword TEXT NOT NULL,
            headword_key TEXT NOT NULL,
            romanization TEXT NOT NULL DEFAULT '',
            pos TEXT NOT NULL DEFAULT '',
            glosses TEXT NOT NULL DEFAULT '[]',
            forms TEXT NOT NULL DEFAULT '[]',
            commentary TEXT NOT NULL DEFAULT '',
            lemma TEXT NOT NULL DEFAULT '',
            etymology TEXT NOT NULL DEFAULT '',
            etymology_number INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT '',
            entry_id TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            format TEXT NOT NULL DEFAULT 'compact'
        );

        CREATE TABLE forms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL REFERENCES entries(id),
            form_text TEXT NOT NULL,
            form_key TEXT NOT NULL,
            morph_tags TEXT NOT NULL DEFAULT '',
            romanization TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )


def _write_database(db_path: Path, zip_path: Path, entries: list[ParsedEntry]) -> tuple[int, int]:
    temp_path = db_path.with_suffix(".rebuilt.sqlite")
    if temp_path.exists():
        temp_path.unlink()

    conn = sqlite3.connect(str(temp_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    _create_schema(conn)

    all_norm_pairs: list[tuple[str, str]] = []
    for entry in entries:
        all_norm_pairs.append((entry.headword, LANG_CODE))
        for form_text, _tag, _roman in entry.forms:
            all_norm_pairs.append((form_text, LANG_CODE))

    print(f"  Normalizing {len(all_norm_pairs):,} headword/form texts...")
    norm_cache = _batch_normalize(all_norm_pairs)

    entry_batch: list[
        tuple[str, str, str, str, str, str, str, str, str, int, str, str, str, str]
    ] = []
    form_batch: list[tuple[int, str, str, str, str]] = []
    entry_count = 0
    form_count = 0
    next_id = 1

    def flush() -> None:
        nonlocal entry_count, form_count, entry_batch, form_batch
        if entry_batch:
            conn.executemany(
                "INSERT INTO entries (headword, headword_key, romanization, pos, glosses, forms, commentary, lemma, etymology, etymology_number, source, entry_id, tags, format) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                entry_batch,
            )
            entry_count += len(entry_batch)
            entry_batch = []
        if form_batch:
            conn.executemany(
                "INSERT INTO forms (entry_id, form_text, form_key, morph_tags, romanization) VALUES (?,?,?,?,?)",
                form_batch,
            )
            form_count += len(form_batch)
            form_batch = []
        conn.commit()

    for entry in entries:
        headword_key = norm_cache.get((entry.headword, LANG_CODE), "")
        if not headword_key:
            continue
        current_id = next_id
        next_id += 1
        entry_batch.append(
            (
                entry.headword,
                headword_key,
                entry.romanization,
                entry.pos,
                entry.glosses_json,
                entry.forms_json,
                "",
                "",
                "",
                0,
                entry.source,
                entry.entry_id,
                "",
                "compact",
            )
        )
        for form_text, tags, form_roman in entry.forms:
            form_key = norm_cache.get((form_text, LANG_CODE), "")
            if not form_key:
                continue
            form_batch.append((current_id, form_text, form_key, tags, form_roman))
        if current_id % ENTRY_BATCH_SIZE == 0:
            flush()

    flush()

    conn.execute("CREATE INDEX idx_entries_headword_key ON entries(headword_key)")
    conn.execute("CREATE INDEX idx_entries_lemma ON entries(lemma) WHERE lemma != ''")
    conn.execute("CREATE INDEX idx_forms_form_key ON forms(form_key)")
    conn.execute("CREATE INDEX idx_forms_entry_id ON forms(entry_id)")

    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.executemany(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        [
            ("lang_code", LANG_CODE),
            ("source_label", SOURCE_LABEL),
            ("source_zip", str(zip_path)),
            ("entry_count", str(entry_count)),
            ("form_count", str(form_count)),
            ("created_at", created_at),
        ],
    )
    conn.commit()
    conn.execute("PRAGMA optimize")
    conn.close()

    for sidecar in (
        db_path.with_name(db_path.name + "-wal"),
        db_path.with_name(db_path.name + "-shm"),
    ):
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError:
                pass
    try:
        temp_path.replace(db_path)
    except PermissionError:
        # A running Flask process can keep the live SQLite file open on Windows.
        # Fall back to SQLite's online backup API so we can refresh the file in place.
        with sqlite3.connect(str(temp_path)) as src_conn:
            with sqlite3.connect(str(db_path)) as dst_conn:
                src_conn.backup(dst_conn)
    return entry_count, form_count


def main() -> int:
    zip_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ZIP_PATH
    db_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DB_PATH

    if not zip_path.exists():
        print(f"ZIP not found: {zip_path}", file=sys.stderr)
        return 1

    started = time.time()
    print(f"Reading LSJ source from {zip_path}...")
    parsed_entries = _parse_entries(zip_path)
    print(f"Parsed {len(parsed_entries):,} candidate entries.")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    entry_count, form_count = _write_database(db_path, zip_path, parsed_entries)
    size_mb = db_path.stat().st_size / 1e6
    elapsed = time.time() - started
    print(
        f"Done: {entry_count:,} entries, {form_count:,} forms -> {db_path} ({size_mb:.1f} MB) in {elapsed:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
