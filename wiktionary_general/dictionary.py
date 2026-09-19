"""
Universal Wiktionary dictionary — loads Yomitan zip or Kaikki JSONL exports.

Yomitan zips (preferred): contain lemma entries with structured content
(glosses, grammar, etymology) and non-lemma entries mapping inflected
forms back to their base lemmas with morphological descriptions.

Kaikki JSONL (fallback for languages without Yomitan dicts): one JSON
object per line with word, pos, senses, sounds, forms, etc.

Provides lookup, lookup_all, fill_token, and UPOS-based filtering methods
matching the interface expected by pipeline_common.py.
"""

from __future__ import annotations

import json
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from wiktionary_general.upos_map import (
    get_upos_to_kaikki_pos,
    get_filter_exempt_pos,
    get_always_filtered_pos,
)


# ── Yomitan tag -> Kaikki-style pos_raw mapping ──────────────────────────
# Yomitan tag_bank uses short codes; map them to the Kaikki POS names
# our UPOS filter system already understands.
_YOMITAN_POS_TAG_MAP: Dict[str, str] = {
    "n": "noun",
    "v": "verb",
    "vt": "verb",
    "vi": "verb",
    "vr": "verb",
    "vdt": "verb",
    "adj": "adj",
    "adv": "adv",
    "pron": "pron",
    "prep": "prep",
    "postp": "postp",
    "conj": "conj",
    "det": "det",
    "num": "num",
    "intj": "intj",
    "ptcl": "particle",
    "suf": "suffix",
    "pref": "prefix",
    "artic": "article",
    "phrase": "phrase",
    "prov": "proverb",
    "prep-phrase": "prep_phrase",
    "ptcpl": "particle",
    "name": "name",
    "prop-n": "name",
    "r": "root",
    "char": "character",
    "symb": "symbol",
    # Sub-classifications that still map to verb
    "chief-vdt": "verb",
    "chief-vi": "verb",
    "chief-vt": "verb",
    "usu-vi": "verb",
    "usu-vt": "verb",
    "oft-vi": "verb",
    "some-vdt": "verb",
}

# Kaikki POS strings -> short labels for display
_POS_LABELS: Dict[str, str] = {
    "noun": "n",
    "verb": "v",
    "adj": "adj",
    "adv": "adv",
    "pron": "pron",
    "prep": "prep",
    "postp": "postp",
    "conj": "conj",
    "det": "det",
    "num": "num",
    "intj": "intj",
    "particle": "ptcl",
    "classifier": "clf",
    "prefix": "pfx",
    "suffix": "sfx",
    "affix": "afx",
    "infix": "ifx",
    "interfix": "itfx",
    "circumfix": "circfx",
    "combining_form": "comb",
    "contraction": "contr",
    "phrase": "phr",
    "proverb": "prov",
    "prep_phrase": "prep.phr",
    "character": "char",
    "name": "name",
    "romanization": "rom",
    "root": "root",
    "article": "art",
    "punct": "punct",
    "symbol": "sym",
}

_SANSKRIT_SLP1_TO_IAST_MAP: Dict[str, str] = {
    "A": "ā",
    "I": "ī",
    "U": "ū",
    "f": "ṛ",
    "F": "ṝ",
    "x": "ḷ",
    "X": "ḹ",
    "E": "ai",
    "O": "au",
    "K": "kh",
    "G": "gh",
    "N": "ṅ",
    "C": "ch",
    "J": "jh",
    "Y": "ñ",
    "w": "ṭ",
    "W": "ṭh",
    "q": "ḍ",
    "Q": "ḍh",
    "R": "ṇ",
    "T": "th",
    "D": "dh",
    "P": "ph",
    "B": "bh",
    "S": "ś",
    "z": "ṣ",
    "M": "ṃ",
    "H": "ḥ",
}

_SANSKRIT_SLP1_TO_IAST_MAP = {
    "A": "\u0101",
    "I": "\u012b",
    "U": "\u016b",
    "f": "\u1e5b",
    "F": "\u1e5d",
    "x": "\u1e37",
    "X": "\u1e39",
    "E": "ai",
    "O": "au",
    "K": "kh",
    "G": "gh",
    "N": "\u1e45",
    "C": "ch",
    "J": "jh",
    "Y": "\u00f1",
    "w": "\u1e6d",
    "W": "\u1e6dh",
    "q": "\u1e0d",
    "Q": "\u1e0dh",
    "R": "\u1e47",
    "T": "th",
    "D": "dh",
    "P": "ph",
    "B": "bh",
    "S": "\u1e63",
    "z": "\u015b",
    "M": "\u1e43",
    "H": "\u1e25",
    "'": "\u2019",
}

# POS values that are normally always filtered, but should stay visible for
# greedy-match filtering contexts (e.g. affix decomposition rows).
_GREEDY_MATCH_ALWAYS_FILTER_BYPASS_POS: frozenset = frozenset({
    "prefix",
    "suffix",
    "affix",
    "infix",
    "interfix",
    "combining_form",
    "circumfix",
})

# POS values heavily downweighted when they are the only POS class in a
# candidate greedy segment.
_GREEDY_LOW_VALUE_ONLY_POS: frozenset = frozenset({
    "symbol",
    "character",
    "punct",
    "romanization",
    "contraction",
})

# Affix-like POS values that should be rewarded only when used in plausible
# segment slots during greedy decomposition.
_GREEDY_AFFIX_SLOT_POS: frozenset = frozenset({
    "prefix",
    "suffix",
    "affix",
    "infix",
    "interfix",
    "combining_form",
    "circumfix",
})

# DP greedy scorer weights (intentionally simple and explicit).
_GREEDY_UNKNOWN_PENALTY = -1000.0
_GREEDY_SEGMENT_PENALTY = -100.0
_GREEDY_UPOS_BONUS = 50.0
_GREEDY_LOW_VALUE_ONLY_PENALTY = -100.0
_GREEDY_AFFIX_VALID_SLOT_BONUS = 50.0


# Structural / metadata tags that should not be shown in the UI.
_HIDDEN_TAGS: frozenset = frozenset({
    "no-gloss", "empty-gloss",
    "alt-of", "form-of", "alternative",
    "abbreviation", "acronym", "initialism", "clipping",
    "romanization",
    "canonical", "variant", "synonym-of", "compound-of",
    "letter", "morpheme",
    "uppercase", "lowercase", "capitalized",
    "pronunciation-spelling", "misspelling", "misconstruction", "nonstandard",
    "ellipsis",
    "usually", "copulative",
})

# Form tags that should be excluded from building surface->lemma lookup
# mappings. Expand this set as we identify more non-variant relationship tags.
_LOOKUP_FORM_TAG_EXCLUDE: frozenset = frozenset({
    "classifier",
    "clf",
})

# Affix boundary markers observed in Wiktionary data across languages.
# These are normalized to "-" and then handled by the existing hyphen
# stripping rule in lookup-key generation.
_AFFIX_MARKER_EQUIVALENTS: frozenset = frozenset({
    "\uFEFF",  # zero width no-break space / BOM
    "\u061C",  # Arabic letter mark
    "\u200E",  # left-to-right mark
    "\u200F",  # right-to-left mark
    "\u200C",  # zero width non-joiner
    "\u202A",  # left-to-right embedding
    "\u202B",  # right-to-left embedding
    "\u202C",  # pop directional formatting
    "\u202D",  # left-to-right override
    "\u202E",  # right-to-left override
    "\u2066",  # left-to-right isolate
    "\u2067",  # right-to-left isolate
    "\u2068",  # first strong isolate
    "\u2069",  # pop directional isolate
    "\u05BE",  # Hebrew maqaf
    "\u05F3",  # Hebrew geresh
    "\u2012",  # figure dash
    "\u25CC",  # dotted circle
    "'",       # apostrophe
    ".",       # full stop
    "^",       # circumflex
    "\u3320",  # square santiimu
    "\u2810",  # braille pattern dots-5
    "\u2818",  # braille pattern dots-45
    "\u2830",  # braille pattern dots-56
    "\u211E",  # prescription take
    "\u2205",  # empty set
    "&",       # ampersand
    "(",       # left parenthesis
    ")",       # right parenthesis
    ",",       # comma
    "\u00A9",  # copyright sign
    "\u3030",  # wavy dash
})
_AFFIX_MARKER_TRANSLATION = str.maketrans({ch: "-" for ch in _AFFIX_MARKER_EQUIVALENTS})

def _normalize_dedupe_key(text: str) -> str:
    """Normalize text used for runtime dedupe keys."""
    norm = unicodedata.normalize("NFKC", str(text or ""))
    norm = " ".join(norm.split()).strip()
    return norm.casefold()


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    """Drop duplicate strings while preserving first occurrence order."""
    out: List[str] = []
    seen: set = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = _normalize_dedupe_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _dedupe_semicolon_chunks(text: str) -> str:
    """Dedupe repeated semicolon-separated chunks inside one gloss string."""
    raw = str(text or "").strip()
    if not raw or ";" not in raw:
        return raw
    chunks = [c.strip() for c in raw.split(";")]
    deduped = _dedupe_preserve_order(chunks)
    return "; ".join(deduped)


def _dedupe_gloss_list(glosses: List[str]) -> List[str]:
    """Normalize and dedupe gloss list entries."""
    cleaned = [_dedupe_semicolon_chunks(g) for g in (glosses or [])]
    return _dedupe_preserve_order(cleaned)


def _dedupe_senses_runtime(
    flat_senses: List[str],
    senses_full: List[Dict[str, Any]],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Runtime dedupe for both flat and structured sense representations."""
    out_senses_full: List[Dict[str, Any]] = []
    seen_sense_keys: set = set()

    for sense in senses_full or []:
        if not isinstance(sense, dict):
            continue
        glosses = sense.get("glosses", [])
        if isinstance(glosses, str):
            glosses = [glosses]
        elif not isinstance(glosses, list):
            continue
        deduped_glosses = _dedupe_gloss_list(glosses)
        if not deduped_glosses:
            continue
        sense_copy = dict(sense)
        sense_copy["glosses"] = deduped_glosses
        sense_key = tuple(_normalize_dedupe_key(g) for g in deduped_glosses)
        if not sense_key or sense_key in seen_sense_keys:
            continue
        seen_sense_keys.add(sense_key)
        out_senses_full.append(sense_copy)

    if out_senses_full:
        derived_flat = []
        for sf in out_senses_full:
            gs = sf.get("glosses", [])
            if isinstance(gs, list) and gs:
                derived_flat.append("; ".join(gs))
        out_flat = _dedupe_gloss_list(derived_flat)
        return out_flat, out_senses_full

    out_flat = _dedupe_gloss_list(flat_senses or [])
    out_senses_full = [{"glosses": [g]} for g in out_flat]
    return out_flat, out_senses_full

def _etym_key(entry: Dict[str, Any]) -> str:
    """Return a grouping key for entries sharing the same etymology."""
    num = entry.get("etymology_number", 0)
    if num and num > 0:
        return f"n:{num}"
    return f"t:{entry.get('etymology', '')}"


def _normalize_pos(raw: str) -> str:
    return _POS_LABELS.get(raw, raw)


def _split_upos_tags(raw_upos: str) -> List[str]:
    """Split composite UPOS strings like ``NOUN+PART`` into individual tags."""
    text = str(raw_upos or "").strip()
    if not text:
        return []
    if "+" not in text:
        return [text]
    parts = [p.strip() for p in text.split("+")]
    return [p for p in parts if p]


def _is_sanskrit_language_code(lang_code: str) -> bool:
    lang = str(lang_code or "").strip().lower()
    return (
        lang == "sa"
        or lang == "san"
        or lang == "sanskrit"
        or lang.startswith("sa-")
        or lang.startswith("san-")
        or lang.startswith("sanskrit-")
    )


def _transliterate_sanskrit_slp1_to_iast(text: str) -> str:
    src = str(text or "")
    out = "".join(_SANSKRIT_SLP1_TO_IAST_MAP.get(ch, ch) for ch in src)
    return unicodedata.normalize("NFC", out)


def _normalize_lookup_text(text: str, lang_code: str) -> str:
    """Normalize lookup/index text in a language-agnostic way."""
    value = unicodedata.normalize("NFKC", str(text or "").strip())
    if _is_sanskrit_language_code(lang_code):
        return _transliterate_sanskrit_slp1_to_iast(value)
    return value


def _normalize_affix_markers(text: str) -> str:
    """Map non-standard affix boundary symbols to ASCII hyphen."""
    return str(text or "").translate(_AFFIX_MARKER_TRANSLATION)


# =========================================================================
# Yomitan structured-content parsing helpers
# =========================================================================

def _yomitan_find_by_data_key(content: Any, data_key: str) -> str:
    """Recursively search structured-content for a node whose
    data.content == data_key and return its text content."""
    if isinstance(content, str):
        return ""
    if isinstance(content, dict):
        data = content.get("data")
        if isinstance(data, dict) and data.get("content") == data_key:
            return _yomitan_extract_text(content.get("content", ""))
        return _yomitan_find_by_data_key(content.get("content", []), data_key)
    if isinstance(content, list):
        for item in content:
            result = _yomitan_find_by_data_key(item, data_key)
            if result:
                return result
    return ""


def _yomitan_extract_text(content: Any) -> str:
    """Extract all text from a structured-content tree."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return _yomitan_extract_text(content.get("content", ""))
    if isinstance(content, list):
        return " ".join(_yomitan_extract_text(x) for x in content).strip()
    return ""


def _yomitan_extract_glosses(content: Any) -> List[str]:
    """Extract gloss texts from the 'glosses' ol element."""
    if isinstance(content, str):
        return []
    if isinstance(content, dict):
        data = content.get("data")
        if isinstance(data, dict) and data.get("content") == "glosses":
            # This is the <ol> containing <li> elements
            items = content.get("content", [])
            if isinstance(items, list):
                glosses = []
                for item in items:
                    text = _yomitan_extract_text(item).strip()
                    # Strip trailing "Wiktionary" backlink text
                    if text and text != "Wiktionary":
                        glosses.append(text)
                return glosses
            return []
        return _yomitan_extract_glosses(content.get("content", []))
    if isinstance(content, list):
        for item in content:
            result = _yomitan_extract_glosses(item)
            if result:
                return result
    return []


def _yomitan_extract_tags_from_glosses(content: Any) -> List[Dict[str, Any]]:
    """Extract structured senses with tags from the glosses ol element."""
    if isinstance(content, str):
        return []
    if isinstance(content, dict):
        data = content.get("data")
        if isinstance(data, dict) and data.get("content") == "glosses":
            items = content.get("content", [])
            if isinstance(items, list):
                senses = []
                for item in items:
                    sense = _yomitan_parse_sense_li(item)
                    if sense:
                        senses.append(sense)
                return senses
            return []
        return _yomitan_extract_tags_from_glosses(content.get("content", []))
    if isinstance(content, list):
        for item in content:
            result = _yomitan_extract_tags_from_glosses(item)
            if result:
                return result
    return []


def _yomitan_parse_sense_li(content: Any) -> Optional[Dict[str, Any]]:
    """Parse a single <li> sense item, extracting gloss text."""
    if isinstance(content, str):
        text = content.strip()
        if text and text != "Wiktionary":
            return {"glosses": [text]}
        return None
    if isinstance(content, dict):
        tag = content.get("tag", "")
        if tag == "li":
            inner = content.get("content", [])
            return _yomitan_parse_sense_inner(inner)
        return _yomitan_parse_sense_li(content.get("content", []))
    if isinstance(content, list):
        return _yomitan_parse_sense_inner(content)
    return None


def _yomitan_parse_sense_inner(content: Any) -> Optional[Dict[str, Any]]:
    """Parse the inner content of a sense <li>, preserving gloss text only."""
    text_parts: List[str] = []

    def _walk(c: Any) -> None:
        if isinstance(c, str):
            t = c.strip()
            if t and t != "Wiktionary":
                text_parts.append(t)
        elif isinstance(c, dict):
            data = c.get("data", {})
            if isinstance(data, dict):
                if data.get("content") == "tag":
                    return
                if data.get("content") in ("tags",):
                    # Skip metadata tag containers entirely.
                    return
                if data.get("content") in (
                    "details-entry-examples", "extra-info",
                    "example-sentence", "backlink",
                ):
                    return  # Skip examples and backlinks
            _walk(c.get("content", []))
        elif isinstance(c, list):
            for item in c:
                _walk(item)

    _walk(content)
    full_text = " ".join(text_parts).strip()
    if not full_text:
        return None
    return {"glosses": [full_text]}


# =========================================================================
# Main dictionary class
# =========================================================================

class WiktionaryDict:
    """In-memory Wiktionary dictionary.

    Loads from Yomitan zip (preferred) or Kaikki JSONL (fallback).
    Builds a form→lemma index from inflected forms for morphology-aware lookup.
    """

    def __init__(self, path, lang_code: str = ""):
        path = Path(path)
        self._lang_code = str(lang_code or "").strip().lower()
        self._lookup_form_tag_exclude = set(_LOOKUP_FORM_TAG_EXCLUDE)
        self._by_word: Dict[str, List[Dict[str, Any]]] = {}
        # Form index: inflected_form (casefolded) -> list of
        #   {"lemma": base_word, "morph": [morph_labels]}
        self._form_index: Dict[str, List[Dict[str, Any]]] = {}
        self._max_word_len = 1
        self._upos_to_kaikki = get_upos_to_kaikki_pos(lang_code)
        self._filter_exempt_pos = get_filter_exempt_pos(lang_code)
        self._always_filtered_pos = get_always_filtered_pos(lang_code)
        self._filterable_pos: set = set()
        for pos_list in self._upos_to_kaikki.values():
            self._filterable_pos.update(pos_list)

        if path.suffix == ".zip":
            self._load_yomitan(path)
        elif path.suffix == ".tsv":
            self._load_tsv(path)
        else:
            self._load_jsonl(path)

    def _lookup_key(self, text: str) -> str:
        """Return normalized internal lookup key for a token."""
        norm = _normalize_lookup_text(text, self._lang_code).strip()
        if not norm:
            return ""
        norm = _normalize_affix_markers(norm)
        return norm.replace("-", "").casefold() or ""

    def _ensure_runtime_state(self) -> None:
        """Backfill required attributes for compatibility with older callers."""
        if not hasattr(self, "_lookup_form_tag_exclude") or self._lookup_form_tag_exclude is None:
            self._lookup_form_tag_exclude = set(_LOOKUP_FORM_TAG_EXCLUDE)
        if not hasattr(self, "_by_word") or self._by_word is None:
            self._by_word = {}
        if not hasattr(self, "_form_index") or self._form_index is None:
            self._form_index = {}
        if not hasattr(self, "_max_word_len") or not isinstance(self._max_word_len, int):
            self._max_word_len = 1

    def _lookup_keys(self, text: str) -> List[str]:
        """Return prioritized lookup keys."""
        norm = _normalize_lookup_text(text, self._lang_code).strip()
        if not norm:
            return []
        norm = _normalize_affix_markers(norm)

        variants = [norm]

        out: List[str] = []
        seen = set()
        for v in variants:
            k = str(v or "").strip().replace("-", "").casefold()
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(k)
        return out

    def _skip_form_tags_for_lookup(self, tags: List[str]) -> bool:
        """True when form tags should not be indexed for surface->lemma lookup."""
        self._ensure_runtime_state()
        lowered = {str(t).strip().casefold() for t in tags if str(t).strip()}
        return bool(lowered & self._lookup_form_tag_exclude)

    def _collect_korean_hanja_variant(
        self,
        entry: Dict[str, Any],
        form_text: str,
        tags: List[str],
    ) -> None:
        """Capture Korean Hanja variants for display-only morphology metadata."""
        if self._lang_code != "ko":
            return
        text = str(form_text or "").strip()
        if not text:
            return
        lowered = {str(t).strip().casefold() for t in tags if str(t).strip()}
        if "hanja" not in lowered:
            return
        existing = entry.get("korean_hanja_variants")
        if not isinstance(existing, list):
            existing = []
            entry["korean_hanja_variants"] = existing
        if text not in existing:
            existing.append(text)

    def _skip_form_index_for_language(
        self,
        lemma_word: str,
        form_text: str,
        tags: List[str],
    ) -> bool:
        """Language-specific guardrails for surface->lemma form indexing."""
        _ = (lemma_word, form_text)
        _ = tags
        return False

    def add_lookup_excluded_form_tags(self, tags: List[str]) -> None:
        """Expand the form-tag denylist used by lookup indexing."""
        for tag in tags:
            t = str(tag or "").strip().casefold()
            if t:
                self._lookup_form_tag_exclude.add(t)

    # ------------------------------------------------------------------
    # Yomitan zip loader
    # ------------------------------------------------------------------

    def _load_yomitan(self, path: Path) -> None:
        lang_label = self._lang_code.upper() or "WIKT"
        if not path.exists():
            print(f"[WARN] {lang_label} dictionary zip not found: {path}")
            return

        total_lemma = 0
        total_forms = 0
        skipped = 0
        observed_pos_raw: set = set()

        with zipfile.ZipFile(path, "r") as zf:
            # Load tag bank for POS tag mapping
            tag_map: Dict[str, str] = {}
            try:
                tag_data = json.loads(zf.read("tag_bank_1.json"))
                for t in tag_data:
                    if isinstance(t, list) and len(t) >= 2:
                        tag_map[t[0]] = t[1]  # tag_name -> category
            except (KeyError, json.JSONDecodeError):
                pass

            term_banks = sorted(
                n for n in zf.namelist() if n.startswith("term_bank_")
            )
            for bank_name in term_banks:
                try:
                    entries = json.loads(zf.read(bank_name))
                except (json.JSONDecodeError, KeyError):
                    continue

                for raw in entries:
                    if not isinstance(raw, list) or len(raw) < 6:
                        skipped += 1
                        continue

                    term = str(raw[0] or "").strip()
                    tags_str = str(raw[2] or "")
                    pos_field = str(raw[3] or "")
                    defs = raw[5]

                    if not term:
                        skipped += 1
                        continue

                    if "non-lemma" in tags_str:
                        # Inflected form entry
                        self._index_nonlemma(term, defs)
                        total_forms += 1
                    else:
                        # Lemma entry
                        entry = self._parse_yomitan_lemma(
                            term, tags_str, pos_field, defs
                        )
                        if not entry:
                            skipped += 1
                            continue

                        fold_key = self._lookup_key(term)
                        if not fold_key:
                            skipped += 1
                            continue
                        self._by_word.setdefault(fold_key, []).append(entry)
                        observed_pos_raw.add(entry.get("pos_raw", ""))
                        if len(term) > self._max_word_len:
                            self._max_word_len = len(term)
                        total_lemma += 1

        print(
            f"[INFO] {lang_label} Yomitan loaded: {total_lemma:,} lemmas, "
            f"{total_forms:,} inflected forms"
            + (f", {skipped} skipped" if skipped else "")
        )
        self._report_pos_filter_coverage(observed_pos_raw)

    def _index_nonlemma(self, inflected: str, defs: Any) -> None:
        """Index a non-lemma (inflected form) entry.

        defs is a list like [["base_lemma", ["morph label 1", ...]], ...]
        """
        if not isinstance(defs, list):
            return
        fold_key = self._lookup_key(inflected)
        if not fold_key:
            return
        for d in defs:
            if not isinstance(d, list) or len(d) < 2:
                continue
            lemma = str(d[0] or "").strip()
            morph = d[1] if isinstance(d[1], list) else []
            if not lemma:
                continue
            if self._skip_form_tags_for_lookup(morph):
                continue
            lemma_key = self._lookup_key(lemma)
            if not lemma_key:
                continue
            self._form_index.setdefault(fold_key, []).append({
                "lemma": lemma,
                "lemma_key": lemma_key,
                "morph": morph,
            })

    def _parse_yomitan_lemma(
        self,
        term: str,
        tags_str: str,
        pos_field: str,
        defs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Parse a Yomitan lemma entry into the internal format."""
        # Determine POS
        pos_raw = ""
        tag_parts = tags_str.split()
        for tp in tag_parts:
            mapped = _YOMITAN_POS_TAG_MAP.get(tp)
            if mapped:
                pos_raw = mapped
                break
        if not pos_raw and pos_field:
            # pos_field is the Yomitan display POS
            mapped = _YOMITAN_POS_TAG_MAP.get(pos_field)
            if mapped:
                pos_raw = mapped
            else:
                pos_raw = pos_field
        pos = _normalize_pos(pos_raw)

        # Parse structured content
        grammar_text = ""
        etymology = ""
        flat_senses: List[str] = []
        senses_full: List[Dict[str, Any]] = []

        if isinstance(defs, list):
            for d in defs:
                if isinstance(d, dict) and d.get("type") == "structured-content":
                    content = d.get("content", [])
                    if not grammar_text:
                        grammar_text = _yomitan_find_by_data_key(
                            content, "Grammar-content"
                        )
                    if not etymology:
                        etymology = _yomitan_find_by_data_key(
                            content, "Etymology-content"
                        )
                    if not senses_full:
                        senses_full = _yomitan_extract_tags_from_glosses(content)
                    if not flat_senses:
                        flat_senses = _yomitan_extract_glosses(content)
                elif isinstance(d, str):
                    flat_senses.append(d)

        if not flat_senses and not senses_full:
            return None

        # Build senses_full from flat if needed
        if not senses_full and flat_senses:
            senses_full = [{"glosses": [g]} for g in flat_senses]

        flat_senses, senses_full = _dedupe_senses_runtime(flat_senses, senses_full)
        if not flat_senses:
            return None

        # Collect extra tags from tag string (non-POS tags)
        extra_tags: List[str] = []
        for tp in tag_parts:
            if tp in _YOMITAN_POS_TAG_MAP:
                continue
            if tp == "non-lemma":
                continue
            extra_tags.append(tp)

        return {
            "headword": term,
            "pos": pos,
            "pos_raw": pos_raw,
            "senses": flat_senses,
            "reading": "",
            "senses_full": senses_full,
            "alt_forms": [],
            "etymology": etymology,
            "etymology_number": 0,
            "grammar": grammar_text,
            "ipa_variants": [],
            "audio_urls": [],
            "extra_tags": extra_tags,
            "synonyms": [],
            "antonyms": [],
            "derived": [],
            "related": [],
        }

    # ------------------------------------------------------------------
    # Kaikki JSONL loader (fallback)
    # ------------------------------------------------------------------

    def _load_jsonl(self, path: Path) -> None:
        lang_label = self._lang_code.upper() or "WIKT"
        if not path.exists():
            print(f"[WARN] {lang_label} dictionary file not found: {path}")
            return

        total = 0
        skipped = 0
        observed_pos_raw: set = set()
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue

                entry = self._parse_jsonl_entry(raw)
                if not entry:
                    skipped += 1
                    continue

                word = entry["headword"]
                fold_key = self._lookup_key(word)
                if not fold_key:
                    skipped += 1
                    continue
                self._by_word.setdefault(fold_key, []).append(entry)
                observed_pos_raw.add(str(entry.get("pos_raw", "")).strip())
                if len(word) > self._max_word_len:
                    self._max_word_len = len(word)
                total += 1

                # Index inflected forms from the Kaikki "forms" array
                # so lookup_via_forms works the same as Yomitan non-lemma
                # entries.
                for f in raw.get("forms", []):
                    form_text = str(f.get("form", "") or "").strip()
                    if not form_text or form_text == word:
                        continue
                    tags = f.get("tags", [])
                    if not isinstance(tags, list):
                        continue
                    self._collect_korean_hanja_variant(entry, form_text, tags)
                    if self._skip_form_tags_for_lookup(tags):
                        continue
                    if self._skip_form_index_for_language(word, form_text, tags):
                        continue
                    # Skip romanization-only entries
                    if tags == ["romanization"]:
                        continue
                    form_key = self._lookup_key(form_text)
                    if not form_key or form_key == fold_key:
                        continue
                    self._form_index.setdefault(form_key, []).append({
                        "lemma": word,
                        "lemma_key": fold_key,
                        "morph": tags,
                    })

        total_forms = sum(len(v) for v in self._form_index.values())
        print(
            f"[INFO] {lang_label} JSONL loaded: {total:,} entries, "
            f"{total_forms:,} inflected forms, "
            f"max word length {self._max_word_len}"
            + (f", {skipped} skipped" if skipped else "")
        )
        self._report_pos_filter_coverage(observed_pos_raw)

    @staticmethod
    def _parse_jsonl_entry(raw: dict) -> Optional[Dict[str, Any]]:
        """Parse a single Kaikki JSONL entry into the internal format."""
        word = raw.get("word", "").strip()
        if not word:
            return None

        pos_raw = raw.get("pos", "")
        pos = _normalize_pos(pos_raw)
        raw_senses = raw.get("senses", [])
        flat_senses = _build_flat_senses_jsonl(raw_senses)
        senses_full = _build_senses_full_jsonl(raw_senses)
        flat_senses, senses_full = _dedupe_senses_runtime(flat_senses, senses_full)

        if not flat_senses and not senses_full:
            return None

        sounds = raw.get("sounds", [])
        ipa = ""
        for s in sounds:
            i = s.get("ipa", "")
            if i:
                ipa = i
                break

        forms = raw.get("forms", [])
        alt_forms = []
        for f in forms:
            ftags = f.get("tags", [])
            if "alternative" in ftags:
                w = f.get("form", "")
                if w and w not in alt_forms:
                    alt_forms.append(w)

        etymology = raw.get("etymology_text", "")
        etymology_number = raw.get("etymology_number", 0)

        ipa_variants: List[Dict[str, str]] = []
        for s in sounds:
            s_ipa = s.get("ipa", "")
            if not s_ipa:
                continue
            tags = s.get("tags", [])
            note = s.get("note", "")
            label = ", ".join(tags) if tags else note
            ipa_variants.append({"ipa": s_ipa, "label": label})

        audio_urls: List[Dict[str, str]] = []
        for s in sounds:
            mp3 = s.get("mp3_url", "")
            ogg = s.get("ogg_url", "")
            if mp3 or ogg:
                audio_urls.append({"mp3": mp3, "ogg": ogg})

        synonyms = raw.get("synonyms", [])
        antonyms = raw.get("antonyms", [])
        derived = raw.get("derived", [])
        related = raw.get("related", [])

        return {
            "headword": word,
            "pos": pos,
            "pos_raw": pos_raw,
            "senses": flat_senses,
            "reading": ipa,
            "senses_full": senses_full,
            "alt_forms": alt_forms,
            "etymology": etymology,
            "etymology_number": etymology_number,
            "ipa_variants": ipa_variants,
            "audio_urls": audio_urls,
            "synonyms": [s.get("word", "") for s in synonyms if s.get("word")],
            "antonyms": [s.get("word", "") for s in antonyms if s.get("word")],
            "derived": [d.get("word", "") for d in derived if d.get("word")],
            "related": [r.get("word", "") for r in related if r.get("word")],
        }

    # ------------------------------------------------------------------
    # TSV loader — generic tab-separated dictionary format
    # ------------------------------------------------------------------
    #
    # TSV columns (tab-separated, header row required):
    #   headword  pos_raw  reading  glosses  tags  etymology
    #   etymology_number  alt_forms  synonyms  antonyms  derived
    #   related  grammar
    #
    # Multi-value fields use semicolons within a cell.
    # glosses + tags are paired per-sense: glosses are semicolon-separated,
    # tags uses pipe | between senses and semicolons within a sense.
    # Example glosses: "to eat; to consume"
    # Example tags:    "transitive|informal; dated"
    #   -> sense 0 tags=["transitive"], sense 1 tags=["informal", "dated"]
    # Missing/blank columns are fine; only headword is required.

    _TSV_COLUMNS = [
        "headword", "pos_raw", "reading", "glosses", "tags",
        "etymology", "etymology_number", "alt_forms", "synonyms",
        "antonyms", "derived", "related", "grammar",
    ]

    def _load_tsv(self, path: Path) -> None:
        lang_label = self._lang_code.upper() or "WIKT"
        if not path.exists():
            print(f"[WARN] {lang_label} TSV file not found: {path}")
            return

        total = 0
        skipped = 0
        observed_pos_raw: set = set()
        with path.open("r", encoding="utf-8") as f:
            header_line = f.readline().strip()
            if not header_line:
                print(f"[WARN] {lang_label} TSV file is empty: {path}")
                return
            headers = header_line.split("\t")

            for line in f:
                line = line.rstrip("\n\r")
                if not line.strip():
                    continue
                fields = line.split("\t")
                row: Dict[str, str] = {}
                for i, h in enumerate(headers):
                    row[h.strip()] = fields[i] if i < len(fields) else ""

                entry = self._parse_tsv_row(row)
                if not entry:
                    skipped += 1
                    continue

                word = entry["headword"]
                fold_key = self._lookup_key(word)
                if not fold_key:
                    skipped += 1
                    continue
                self._by_word.setdefault(fold_key, []).append(entry)
                observed_pos_raw.add(str(entry.get("pos_raw", "")).strip())
                if len(word) > self._max_word_len:
                    self._max_word_len = len(word)
                total += 1

                # Index forms from compact TSV into _form_index
                self._index_tsv_forms(entry, word, fold_key)

        total_forms = sum(len(v) for v in self._form_index.values())
        print(
            f"[INFO] {lang_label} TSV loaded: {total:,} entries, "
            f"{total_forms:,} inflected forms, "
            f"max word length {self._max_word_len}"
            + (f", {skipped} skipped" if skipped else "")
        )
        self._report_pos_filter_coverage(observed_pos_raw)

    @staticmethod
    def _parse_tsv_row(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Parse a single TSV row dict into the internal entry format.

        Supports two TSV layouts:
        - **New compact format** (from convert_jsonl_to_tsv.py):
          columns: headword, pos, romanization, glosses (JSON), forms (JSON)
        - **Legacy format** (manual user uploads):
          columns: headword, pos_raw, reading, glosses (semicolon-sep), tags, ...
        """
        headword = row.get("headword", "").strip()
        if not headword:
            return None

        # Detect format: new compact has "romanization" column and JSON glosses
        glosses_raw = row.get("glosses", "").strip()
        is_new_format = "romanization" in row or glosses_raw.startswith("[")

        if is_new_format:
            return WiktionaryDict._parse_tsv_row_compact(row, headword, glosses_raw)
        else:
            return WiktionaryDict._parse_tsv_row_legacy(row, headword, glosses_raw)

    @staticmethod
    def _parse_tsv_row_compact(
        row: Dict[str, str], headword: str, glosses_raw: str,
    ) -> Optional[Dict[str, Any]]:
        """Parse a row in the new compact TSV format (JSON glosses + forms)."""
        # POS — new format uses "pos" column
        pos_raw = row.get("pos", row.get("pos_raw", "")).strip()
        pos = _normalize_pos(pos_raw)
        reading = row.get("romanization", "").strip()
        etymology = row.get("etymology", "").strip()
        etym_num_raw = row.get("etymology_number", "").strip()
        etymology_number = int(etym_num_raw) if etym_num_raw.isdigit() else 0

        # Glosses — JSON array of sense objects
        senses_full: List[Dict[str, Any]] = []
        flat_senses: List[str] = []
        if glosses_raw:
            try:
                parsed = json.loads(glosses_raw)
                if isinstance(parsed, list):
                    senses_full = parsed
                    for sf in senses_full:
                        gs = sf.get("glosses", [])
                        if gs:
                            flat_senses.append("; ".join(gs))
            except (json.JSONDecodeError, TypeError):
                pass
        flat_senses, senses_full = _dedupe_senses_runtime(flat_senses, senses_full)
        if not flat_senses:
            return None

        entry: Dict[str, Any] = {
            "headword": headword,
            "pos": pos,
            "pos_raw": pos_raw,
            "senses": flat_senses,
            "reading": reading,
            "senses_full": senses_full,
            "alt_forms": [],
            "etymology": etymology,
            "etymology_number": etymology_number,
            "ipa_variants": [],
            "audio_urls": [],
            "synonyms": [],
            "antonyms": [],
            "derived": [],
            "related": [],
        }

        # Forms column is handled separately by _load_tsv / load_tsv_entries
        # for form-index building; we store the raw JSON string on the entry
        # so the caller can access it.
        forms_raw = row.get("forms", "").strip()
        if forms_raw:
            entry["_forms_json"] = forms_raw

        return entry

    @staticmethod
    def _parse_tsv_row_legacy(
        row: Dict[str, str], headword: str, glosses_raw: str,
    ) -> Optional[Dict[str, Any]]:
        """Parse a row in the legacy semicolon-separated TSV format."""
        pos_raw = row.get("pos_raw", "").strip()
        pos = _normalize_pos(pos_raw)
        reading = row.get("reading", "").strip()

        # Parse glosses — semicolon-separated
        gloss_list = [g.strip() for g in glosses_raw.split(";") if g.strip()] if glosses_raw else []
        if not gloss_list:
            return None

        # Parse tags — pipe-separated between senses, semicolons within
        tags_raw = row.get("tags", "").strip()
        tags_per_sense: List[List[str]] = []
        if tags_raw:
            for sense_tags in tags_raw.split("|"):
                tags_per_sense.append([t.strip() for t in sense_tags.split(";") if t.strip()])

        # Build senses_full (structured) and flat senses
        flat_senses: List[str] = list(gloss_list)
        senses_full: List[Dict[str, Any]] = []
        for i, gloss in enumerate(gloss_list):
            sense: Dict[str, Any] = {"glosses": [gloss]}
            if i < len(tags_per_sense) and tags_per_sense[i]:
                sense["tags"] = tags_per_sense[i]
            senses_full.append(sense)
        flat_senses, senses_full = _dedupe_senses_runtime(flat_senses, senses_full)
        if not flat_senses:
            return None

        # Simple fields
        etymology = row.get("etymology", "").strip()
        etym_num_raw = row.get("etymology_number", "").strip()
        etymology_number = int(etym_num_raw) if etym_num_raw.isdigit() else 0
        grammar = row.get("grammar", "").strip()

        # Semicolon-separated list fields
        def _split_list(key: str) -> List[str]:
            raw = row.get(key, "").strip()
            if not raw:
                return []
            return [v.strip() for v in raw.split(";") if v.strip()]

        alt_forms = _split_list("alt_forms")
        synonyms = _split_list("synonyms")
        antonyms = _split_list("antonyms")
        derived = _split_list("derived")
        related = _split_list("related")

        # Build IPA variants from reading
        ipa_variants: List[Dict[str, str]] = []
        if reading:
            ipa_variants.append({"ipa": reading, "label": ""})

        entry: Dict[str, Any] = {
            "headword": headword,
            "pos": pos,
            "pos_raw": pos_raw,
            "senses": flat_senses,
            "reading": reading,
            "senses_full": senses_full,
            "alt_forms": alt_forms,
            "etymology": etymology,
            "etymology_number": etymology_number,
            "ipa_variants": ipa_variants,
            "audio_urls": [],
            "synonyms": synonyms,
            "antonyms": antonyms,
            "derived": derived,
            "related": related,
        }
        if grammar:
            entry["grammar"] = grammar
        return entry

    def _index_tsv_forms(
        self, entry: Dict[str, Any], word: str, fold_key: str,
    ) -> None:
        """Index inflected forms from a compact TSV entry's _forms_json."""
        forms_json = entry.pop("_forms_json", "")
        if not forms_json:
            return
        try:
            forms = json.loads(forms_json)
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(forms, list):
            return
        for f in forms:
            if not isinstance(f, list) or len(f) < 2:
                continue
            form_text = str(f[0] or "").strip()
            if not form_text or form_text == word:
                continue
            tags_str = str(f[1] or "")
            tags = [t for t in tags_str.split(";") if t] if tags_str else []
            self._collect_korean_hanja_variant(entry, form_text, tags)
            if self._skip_form_tags_for_lookup(tags):
                continue
            if self._skip_form_index_for_language(word, form_text, tags):
                continue
            form_key = self._lookup_key(form_text)
            if not form_key or form_key == fold_key:
                continue
            self._form_index.setdefault(form_key, []).append({
                "lemma": word,
                "lemma_key": fold_key,
                "morph": tags,
            })

    def load_tsv_entries(self, entries_json: List[Dict[str, str]]) -> int:
        """Load entries from a list of row dicts (for user-uploaded TSV).

        Each dict should have the same keys as TSV column headers.
        Returns the number of entries successfully loaded.
        """
        self._ensure_runtime_state()
        count = 0
        for row in entries_json:
            entry = self._parse_tsv_row(row)
            if not entry:
                continue
            word = entry["headword"]
            fold_key = self._lookup_key(word)
            if not fold_key:
                continue
            self._by_word.setdefault(fold_key, []).append(entry)
            if len(word) > self._max_word_len:
                self._max_word_len = len(word)
            # Index forms from compact TSV
            self._index_tsv_forms(entry, word, fold_key)
            count += 1
        return count

    # ------------------------------------------------------------------
    # POS coverage diagnostics
    # ------------------------------------------------------------------

    def _report_pos_filter_coverage(self, seen_pos_raw: set) -> None:
        lang_label = self._lang_code.upper() or "WIKT"
        covered_pos = (
            set(self._filterable_pos)
            | set(self._filter_exempt_pos)
            | set(self._always_filtered_pos)
        )
        observed_pos = {str(p).strip() for p in seen_pos_raw if str(p).strip()}
        missing_pos = sorted(p for p in observed_pos if p not in covered_pos)
        if missing_pos:
            print(
                f"[WARN] {lang_label} POS filter missing dictionary POS tags: "
                f"{', '.join(missing_pos)}"
            )
        else:
            print(
                f"[INFO] {lang_label} POS filter covers all observed "
                f"dictionary POS tags ({len(observed_pos)})."
            )

    # ==================================================================
    # Public API
    # ==================================================================

    def lookup(self, word: str) -> Optional[Dict[str, Any]]:
        """Return the first entry for *word*, or None."""
        entries = self.lookup_all(word)
        if not entries:
            return None
        return entries[0]

    def lookup_all(self, word: str) -> List[Dict[str, Any]]:
        """Return all entries for *word* (case-insensitive).

        Lookup order:
        1. Direct lemma/headword hits
        2. Inflected-form index hits (non-lemma -> base lemma)

        When both exist, return the union so callers can display all
        plausible analyses for the same surface form.
        """
        direct: List[Dict[str, Any]] = []
        seen_direct = set()
        for key in self._lookup_keys(word):
            for entry in self._by_word.get(key, []):
                eid = id(entry)
                if eid in seen_direct:
                    continue
                seen_direct.add(eid)
                direct.append(entry)

        form_entries = self.lookup_via_forms(word)
        if not direct:
            return form_entries
        if not form_entries:
            return direct

        merged: List[Dict[str, Any]] = list(direct)
        seen_keys = {self._entry_identity_key(e) for e in merged}
        for entry in form_entries:
            key = self._entry_identity_key(entry)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged.append(entry)
        return merged

    def lookup_via_forms(self, word: str) -> List[Dict[str, Any]]:
        """Look up *word* in the inflected-form index.

        Returns base lemma entries with ``morph_info`` attached,
        describing the morphological relationship.
        """
        form_hits: List[Dict[str, Any]] = []
        for key in self._lookup_keys(word):
            hits = self._form_index.get(key)
            if hits:
                form_hits.extend(hits)
        if not form_hits:
            return []

        results: List[Dict[str, Any]] = []
        seen_lemmas: set = set()
        for hit in form_hits:
            lemma = hit.get("lemma", "")
            morph = hit["morph"]
            lemma_key = str(hit.get("lemma_key", "") or "")
            if not lemma_key and lemma:
                lemma_key = self._lookup_key(lemma)
            base_entries = self._by_word.get(lemma_key, [])
            if not base_entries:
                continue

            for base in base_entries:
                eid = (lemma_key, base.get("pos_raw", ""))
                if eid in seen_lemmas:
                    continue
                seen_lemmas.add(eid)
                # Clone the entry and attach morph info
                enriched = dict(base)
                enriched["morph_info"] = morph
                enriched["morph_base"] = lemma
                results.append(enriched)

        return results

    @staticmethod
    def _entry_identity_key(entry: Dict[str, Any]) -> Tuple[str, str, int, str]:
        """Stable identity for deduping lookups while preserving variants."""
        head = str(entry.get("headword", "") or "")
        pos_raw = str(entry.get("pos_raw", "") or "")
        etym_num_raw = entry.get("etymology_number", 0)
        try:
            etym_num = int(etym_num_raw or 0)
        except Exception:
            etym_num = 0
        etym = str(entry.get("etymology", "") or "")
        return (head, pos_raw, etym_num, etym)

    def filter_entries_by_upos(
        self,
        entries: List[Dict[str, Any]],
        upos: str,
        **kwargs: Any,
    ) -> "tuple[List[Dict[str, Any]], List[Dict[str, Any]]]":
        """Filter entries by UPOS tag, returning (primary, other).

        Rules:
        - POS values in ``self._always_filtered_pos`` are demoted regardless
          of UPOS.
        - In greedy contexts, affix-like POS values are exempt from the
          always-filter rule and count as preferred analyses.
        - If UPOS filtering is inactive (empty/unknown/no mapped POS), only
          always-filter demotion is applied.
        """
        base_entries = list(entries or [])
        if not base_entries:
            return [], []

        greedy_match = bool(kwargs.get("greedy_match", False))
        greedy_multi_fill = bool(kwargs.get("greedy_multi_fill", False))
        greedy_mode = greedy_match or greedy_multi_fill
        active_always_filtered_pos = set(self._always_filtered_pos)
        if greedy_mode:
            active_always_filtered_pos.difference_update(
                _GREEDY_MATCH_ALWAYS_FILTER_BYPASS_POS
            )

        if len(base_entries) <= 1:
            pos_raw = str(base_entries[0].get("pos_raw", "") or "")
            if pos_raw in active_always_filtered_pos:
                return [], base_entries
            return base_entries, []

        upos_tags = _split_upos_tags(str(upos or ""))

        allowed: set = set()
        recognized = False
        for tag in upos_tags:
            mapped = self._upos_to_kaikki.get(tag)
            if mapped is None:
                continue
            recognized = True
            allowed.update(mapped)

        # No UPOS gate: still demote always-filtered POS values.
        if not upos_tags or not recognized or not allowed:
            primary = [
                e
                for e in base_entries
                if str(e.get("pos_raw", "") or "") not in active_always_filtered_pos
            ]
            other = [
                e
                for e in base_entries
                if str(e.get("pos_raw", "") or "") in active_always_filtered_pos
            ]
            return primary, other

        from collections import OrderedDict

        etym_groups: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
        for entry in base_entries:
            ekey = _etym_key(entry)
            etym_groups.setdefault(ekey, []).append(entry)

        primary: List[Dict[str, Any]] = []
        other: List[Dict[str, Any]] = []

        for _ekey, group in etym_groups.items():
            group_primary: List[Dict[str, Any]] = []
            group_other: List[Dict[str, Any]] = []
            has_allowed_match = False

            for entry in group:
                pos_raw = str(entry.get("pos_raw", "") or "")
                if greedy_mode and pos_raw in _GREEDY_MATCH_ALWAYS_FILTER_BYPASS_POS:
                    # Greedy decomposition should treat affix-like analyses as
                    # genuine preferred matches, not mere visibility bypasses.
                    has_allowed_match = True
                    group_primary.append(entry)
                    continue
                if pos_raw in active_always_filtered_pos:
                    group_other.append(entry)
                    continue
                is_exempt = pos_raw in self._filter_exempt_pos
                is_allowed = pos_raw in allowed

                if is_allowed:
                    has_allowed_match = True
                    group_primary.append(entry)
                elif is_exempt:
                    group_primary.append(entry)
                else:
                    group_other.append(entry)

            if has_allowed_match:
                primary.extend(group_primary)
                other.extend(group_other)
            else:
                if group_primary:
                    primary.extend(group_primary)
                    other.extend(group_other)
                else:
                    other.extend(group)

        if not primary:
            non_af = [
                e
                for e in base_entries
                if str(e.get("pos_raw", "") or "") not in active_always_filtered_pos
            ]
            af = [
                e
                for e in base_entries
                if str(e.get("pos_raw", "") or "") in active_always_filtered_pos
            ]
            if non_af and af:
                return non_af, af
            if af:
                return [], af
            return base_entries, []

        return primary, other

    # Alias for compatibility with pipeline_common
    def filter_entries_by_xpos(
        self,
        entries: List[Dict[str, Any]],
        xpos: str,
        **kwargs: Any,
    ) -> "tuple[List[Dict[str, Any]], List[Dict[str, Any]]]":
        return self.filter_entries_by_upos(entries, xpos, **kwargs)

    def debug_filter_entries_by_upos(
        self,
        entries: List[Dict[str, Any]],
        upos: str,
    ) -> Dict[str, Any]:
        """Return a structured explanation of UPOS entry filtering."""
        raw_entries = list(entries or [])
        primary, other = self.filter_entries_by_upos(raw_entries, upos)
        primary_ids = {id(e) for e in primary}

        upos_tags = _split_upos_tags(str(upos or ""))
        recognized_tags: List[str] = []
        allowed: set = set()
        for tag in upos_tags:
            mapped = self._upos_to_kaikki.get(tag)
            if mapped is None:
                continue
            recognized_tags.append(tag)
            allowed.update(mapped)

        single_entry_always_filtered = (
            len(raw_entries) == 1
            and str(raw_entries[0].get("pos_raw", "") or "") in self._always_filtered_pos
        )
        single_entry_passthrough = len(raw_entries) <= 1 and not single_entry_always_filtered
        no_upos_passthrough = not upos_tags
        unrecognized_passthrough = bool(upos_tags) and not recognized_tags
        nonsemantic_passthrough = bool(recognized_tags) and not allowed
        has_always_filtered = any(
            str(e.get("pos_raw", "") or "") in self._always_filtered_pos
            for e in raw_entries
        )
        filter_active = (
            has_always_filtered
            or (
                not single_entry_passthrough
                and not no_upos_passthrough
                and not unrecognized_passthrough
                and not nonsemantic_passthrough
            )
        )

        rows: List[Dict[str, Any]] = []
        for idx, entry in enumerate(raw_entries):
            pos_raw = str(entry.get("pos_raw", "") or "")
            pos_label = str(entry.get("pos", "") or "")
            status = (
                "filtered_out" if id(entry) not in primary_ids else "shown"
            )

            if pos_raw in self._always_filtered_pos:
                reason = "always_filtered_pos"
            elif single_entry_passthrough:
                reason = "single_entry_passthrough"
            elif no_upos_passthrough:
                reason = "no_upos_passthrough"
            elif unrecognized_passthrough:
                reason = "unrecognized_upos_passthrough"
            elif nonsemantic_passthrough:
                reason = "nonsemantic_upos_passthrough"
            elif pos_raw in allowed:
                reason = "upos_pos_match"
            elif pos_raw in self._filter_exempt_pos:
                reason = "filter_exempt_pos"
            else:
                reason = "upos_pos_mismatch"

            senses_full = list(entry.get("senses_full", []) or [])
            senses_flat = list(entry.get("senses", []) or [])
            preview: List[str] = []
            for sense in senses_full:
                if not isinstance(sense, dict):
                    continue
                glosses = sense.get("glosses", [])
                if not isinstance(glosses, list):
                    continue
                gloss = "; ".join(
                    str(g or "").strip()
                    for g in glosses
                    if str(g or "").strip()
                )
                if gloss:
                    preview.append(gloss)
                if len(preview) >= 2:
                    break
            if not preview:
                for gloss in senses_flat:
                    text = str(gloss or "").strip()
                    if text:
                        preview.append(text)
                    if len(preview) >= 2:
                        break

            rows.append(
                {
                    "index": idx,
                    "label": str(entry.get("headword", "") or ""),
                    "headword": str(entry.get("headword", "") or ""),
                    "pos": pos_label,
                    "pos_raw": pos_raw,
                    "etym_key": _etym_key(entry),
                    "sense_count": (
                        len(senses_full) if senses_full else len(senses_flat)
                    ),
                    "sense_preview": preview,
                    "filter_status": status,
                    "reason": reason,
                }
            )

        return {
            "mode": "upos",
            "upos": str(upos or ""),
            "upos_tags": upos_tags,
            "recognized_upos_tags": recognized_tags,
            "allowed_pos_raw": sorted(allowed),
            "filter_active": bool(filter_active),
            "entry_count": len(raw_entries),
            "shown_count": len(primary),
            "filtered_count": len(other),
            "entries": rows,
        }

    def fill_token(
        self,
        word: str,
        allow_exact: bool = True,
        exclude_whole: bool = False,
        upos: str = "",
        debug: bool = False,
    ) -> Dict[str, Any]:
        """Build a fill structure for the frontend."""
        if allow_exact and not exclude_whole:
            entries = self.lookup_all(word)
            if entries:
                best = entries[0]
                fill = self._entry_to_fill(best, word)
                fill["entries"] = entries
                return {
                    "mode": "exact",
                    "fills": [fill],
                    "has_known": True,
                    "has_unknown": False,
                }

        return self._greedy_fill(
            word,
            exclude_whole=exclude_whole,
            upos=upos,
            debug=debug,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _entry_to_fill(
        self, entry: Dict[str, Any], text: str
    ) -> Dict[str, Any]:
        """Convert an entry dict to a fill piece."""
        surface_text = str(text or "")
        lemma_head = str(entry.get("headword", "") or "")
        display_head = surface_text or lemma_head
        fill: Dict[str, Any] = {
            "text": surface_text,
            "head": display_head,
            "roman": entry.get("reading", ""),
            "senses": entry["senses"],
            "pos": entry["pos"],
            "source": "KAIKKI",
            "etymology": entry.get("etymology", ""),
            "senses_full": entry.get("senses_full", []),
            "ipa_variants": entry.get("ipa_variants", []),
        }
        if entry.get("morph_info"):
            fill["morph_info"] = entry["morph_info"]
        if entry.get("morph_base"):
            fill["morph_base"] = entry["morph_base"]
        if entry.get("grammar"):
            fill["grammar"] = entry["grammar"]
        # Keep lemma visibility while presenting the matched piece as the row head.
        if lemma_head and lemma_head != display_head:
            fill["surface_form"] = display_head
            fill["lemma_form"] = lemma_head
            if not fill.get("morph_base"):
                fill["morph_base"] = lemma_head
        return fill

    def _allowed_pos_for_upos(self, upos: str) -> set:
        """Return Kaikki POS values mapped from a token UPOS tag string."""
        out: set = set()
        for tag in _split_upos_tags(str(upos or "")):
            mapped = self._upos_to_kaikki.get(str(tag or "").upper())
            if not mapped:
                continue
            out.update(str(p or "").strip() for p in mapped if str(p or "").strip())
        return out

    @staticmethod
    def _affix_slot_is_valid(pos_raw: str, start: int, end: int, total_len: int) -> bool:
        """Return True when an affix-like POS is in a plausible slot."""
        pos = str(pos_raw or "").strip()
        if not pos:
            return True
        if pos == "prefix":
            return start == 0
        if pos == "suffix":
            return end == total_len
        if pos == "infix":
            return start > 0 and end < total_len
        if pos == "interfix":
            return start > 0 and end < total_len
        if pos == "combining_form":
            return end < total_len
        if pos == "affix":
            return start == 0 or end == total_len
        if pos == "circumfix":
            return start == 0 or end == total_len
        return True

    def _score_greedy_known_piece(
        self,
        entries: List[Dict[str, Any]],
        start: int,
        end: int,
        total_len: int,
        allowed_pos: set,
    ) -> float:
        """Score a known dictionary segment for DP greedy decomposition."""
        return float(
            self._score_greedy_known_piece_details(
                entries,
                start,
                end,
                total_len,
                allowed_pos,
            )["total"]
        )

    def _score_greedy_known_piece_details(
        self,
        entries: List[Dict[str, Any]],
        start: int,
        end: int,
        total_len: int,
        allowed_pos: set,
    ) -> Dict[str, Any]:
        """Return detailed score components for a known greedy segment."""
        score = float(_GREEDY_SEGMENT_PENALTY)
        upos_bonus = 0.0
        low_value_penalty = 0.0
        affix_slot_bonus = 0.0

        pos_set = {
            str((e or {}).get("pos_raw", "") or "").strip()
            for e in entries
            if isinstance(e, dict)
        }
        pos_set = {p for p in pos_set if p}

        allowed_hits = sorted(p for p in pos_set if p in allowed_pos) if allowed_pos else []
        if allowed_hits:
            upos_bonus = float(_GREEDY_UPOS_BONUS)
            score += upos_bonus

        if pos_set and pos_set.issubset(_GREEDY_LOW_VALUE_ONLY_POS):
            low_value_penalty = float(_GREEDY_LOW_VALUE_ONLY_PENALTY)
            score += low_value_penalty

        affix_pos = [p for p in pos_set if p in _GREEDY_AFFIX_SLOT_POS]
        if affix_pos and any(
            self._affix_slot_is_valid(p, start, end, total_len) for p in affix_pos
        ):
            affix_slot_bonus = float(_GREEDY_AFFIX_VALID_SLOT_BONUS)
            score += affix_slot_bonus

        return {
            "segment_penalty": float(_GREEDY_SEGMENT_PENALTY),
            "upos_bonus": upos_bonus,
            "low_value_only_penalty": low_value_penalty,
            "affix_slot_bonus": affix_slot_bonus,
            "pos_set": sorted(pos_set),
            "allowed_pos_hits": allowed_hits,
            "affix_pos": sorted(set(affix_pos)),
            "total": float(score),
        }

    def _score_greedy_unknown_piece(
        self,
        start: int,
        end: int,
        total_len: int,
    ) -> float:
        """Score an unknown segment for DP greedy decomposition."""
        return float(
            self._score_greedy_unknown_piece_details(
                start,
                end,
                total_len,
            )["total"]
        )

    def _score_greedy_unknown_piece_details(
        self,
        start: int,
        end: int,
        total_len: int,
    ) -> Dict[str, Any]:
        """Return detailed score components for an unknown greedy segment."""
        _ = (start, end, total_len)
        segment_penalty = float(_GREEDY_SEGMENT_PENALTY)
        unknown_penalty = float(_GREEDY_UNKNOWN_PENALTY)
        return {
            "segment_penalty": segment_penalty,
            "unknown_penalty": unknown_penalty,
            "total": float(segment_penalty + unknown_penalty),
        }

    def _choose_best_entry_for_piece(
        self,
        entries: List[Dict[str, Any]],
        start: int,
        end: int,
        total_len: int,
        allowed_pos: set,
    ) -> Dict[str, Any]:
        """Pick a representative entry for a greedy segment."""
        if not entries:
            return {}
        best_entry = entries[0]
        best_score = float("-inf")
        for e in entries:
            pos_raw = str((e or {}).get("pos_raw", "") or "").strip()
            score = 0.0
            if allowed_pos and pos_raw in allowed_pos:
                score += _GREEDY_UPOS_BONUS
            if pos_raw in _GREEDY_AFFIX_SLOT_POS:
                if self._affix_slot_is_valid(pos_raw, start, end, total_len):
                    score += _GREEDY_AFFIX_VALID_SLOT_BONUS
            if pos_raw in _GREEDY_LOW_VALUE_ONLY_POS:
                score += _GREEDY_LOW_VALUE_ONLY_PENALTY
            if score > best_score:
                best_score = score
                best_entry = e
        return best_entry

    def _greedy_fill_dp(
        self,
        word: str,
        exclude_whole: bool = False,
        upos: str = "",
        debug: bool = False,
    ) -> Dict[str, Any]:
        """DP-based greedy segmentation with lightweight POS/slot scoring."""
        if not word:
            return {
                "mode": "greedy",
                "fills": [],
                "has_known": False,
                "has_unknown": False,
            }

        n = len(word)
        allowed_pos = self._allowed_pos_for_upos(upos)
        max_len = int(getattr(self, "_max_word_len", n) or n)
        max_len = max(1, min(max_len, n))

        lookup_cache: Dict[str, List[Dict[str, Any]]] = {}
        dp: List[float] = [float("-inf")] * (n + 1)
        choice: List[Optional[Dict[str, Any]]] = [None] * (n + 1)
        debug_steps: List[Dict[str, Any]] = []
        dp[n] = 0.0

        for i in range(n - 1, -1, -1):
            best_score = float("-inf")
            best_choice: Optional[Dict[str, Any]] = None
            step_candidates: List[Dict[str, Any]] = []

            end_limit = min(n, i + max_len)
            for end in range(end_limit, i, -1):
                if (exclude_whole and n > 1 and i == 0 and end == n):
                    continue
                piece = word[i:end]
                entries = lookup_cache.get(piece)
                if entries is None:
                    entries = self.lookup_all(piece)
                    lookup_cache[piece] = entries
                if not entries:
                    continue

                known_breakdown = self._score_greedy_known_piece_details(
                    entries, i, end, n, allowed_pos
                )
                local_score = float(known_breakdown["total"])
                future_score = float(dp[end])
                total_score = local_score + dp[end]
                replace = False
                replace_reason = ""
                if total_score > best_score:
                    replace = True
                    replace_reason = "higher_total_score"
                elif total_score == best_score and best_choice is not None:
                    prev_known = bool(best_choice.get("known"))
                    prev_end = int(best_choice.get("end", i))
                    if (not prev_known) or (end > prev_end):
                        replace = True
                        replace_reason = "tie_break_longer_known_piece"
                if replace:
                    best_entry = self._choose_best_entry_for_piece(
                        entries, i, end, n, allowed_pos
                    )
                    fill = self._entry_to_fill(best_entry, piece)
                    fill["entries"] = entries
                    best_score = total_score
                    best_choice = {
                        "end": end,
                        "known": True,
                        "fill": fill,
                    }
                if debug:
                    step_candidates.append(
                        {
                            "kind": "known",
                            "piece": piece,
                            "start": i,
                            "end": end,
                            "length": end - i,
                            "entry_count": len(entries),
                            "local_score": local_score,
                            "future_score": future_score,
                            "total_score": float(total_score),
                            "selected": bool(replace),
                            "selection_reason": replace_reason,
                            "score_breakdown": known_breakdown,
                        }
                    )

            # Always keep unknown fallback for robust full coverage.
            unknown_end = i + 1
            unknown_breakdown = self._score_greedy_unknown_piece_details(i, unknown_end, n)
            unknown_local_score = float(unknown_breakdown["total"])
            unknown_future_score = float(dp[unknown_end])
            unknown_score = unknown_local_score + unknown_future_score
            replace_unknown = False
            replace_unknown_reason = ""
            if unknown_score > best_score:
                replace_unknown = True
                replace_unknown_reason = "higher_total_score"
            elif unknown_score == best_score and best_choice is None:
                replace_unknown = True
                replace_unknown_reason = "tie_break_when_no_known_choice"
            if replace_unknown:
                best_score = unknown_score
                best_choice = {
                    "end": unknown_end,
                    "known": False,
                    "fill": {
                        "text": word[i:unknown_end],
                        "head": word[i:unknown_end],
                        "roman": "",
                        "senses": [],
                        "pos": "",
                        "source": "UNKNOWN",
                    },
                }
            if debug:
                step_candidates.append(
                    {
                        "kind": "unknown",
                        "piece": word[i:unknown_end],
                        "start": i,
                        "end": unknown_end,
                        "length": 1,
                        "entry_count": 0,
                        "local_score": unknown_local_score,
                        "future_score": unknown_future_score,
                        "total_score": float(unknown_score),
                        "selected": bool(replace_unknown),
                        "selection_reason": replace_unknown_reason,
                        "score_breakdown": unknown_breakdown,
                    }
                )

            dp[i] = best_score
            choice[i] = best_choice
            if debug:
                best_piece = ""
                best_end = i
                best_known = False
                if isinstance(best_choice, dict):
                    best_end = int(best_choice.get("end", i))
                    best_known = bool(best_choice.get("known", False))
                    best_fill = best_choice.get("fill", {})
                    if isinstance(best_fill, dict):
                        best_piece = str(best_fill.get("text", "") or "")
                debug_steps.append(
                    {
                        "start": i,
                        "best_score": float(best_score),
                        "best_end": best_end,
                        "best_piece": best_piece,
                        "best_known": best_known,
                        "candidates": step_candidates,
                    }
                )

        fills: List[Dict[str, Any]] = []
        has_known = False
        has_unknown = False
        i = 0
        while i < n:
            step = choice[i]
            if not step:
                # Safety fallback; should rarely happen due unknown candidate.
                fills.append(
                    {
                        "text": word[i],
                        "head": word[i],
                        "roman": "",
                        "senses": [],
                        "pos": "",
                        "source": "UNKNOWN",
                    }
                )
                has_unknown = True
                i += 1
                continue
            fills.append(step["fill"])
            if step["known"]:
                has_known = True
            else:
                has_unknown = True
            i = int(step["end"])

        out = {
            "mode": "greedy",
            "fills": fills,
            "has_known": has_known,
            "has_unknown": has_unknown,
        }
        if debug:
            out["dp_debug"] = {
                "algorithm": "wiktionary_dp_greedy",
                "word": word,
                "upos": str(upos or ""),
                "allowed_pos_raw": sorted(allowed_pos),
                "weights": {
                    "segment_penalty": float(_GREEDY_SEGMENT_PENALTY),
                    "unknown_penalty": float(_GREEDY_UNKNOWN_PENALTY),
                    "upos_bonus": float(_GREEDY_UPOS_BONUS),
                    "low_value_only_penalty": float(_GREEDY_LOW_VALUE_ONLY_PENALTY),
                    "affix_valid_slot_bonus": float(_GREEDY_AFFIX_VALID_SLOT_BONUS),
                },
                "dp_scores": [float(v) for v in dp],
                "final_score": float(dp[0]) if dp else 0.0,
                "steps": debug_steps,
            }
        return out

    def _greedy_fill_simple(
        self,
        word: str,
        exclude_whole: bool = False,
    ) -> Dict[str, Any]:
        """Original left-to-right longest-match greedy implementation."""
        fills: List[Dict[str, Any]] = []
        has_known = False
        has_unknown = False

        if not word:
            return {
                "mode": "greedy",
                "fills": [],
                "has_known": False,
                "has_unknown": False,
            }

        i = 0
        while i < len(word):
            matched = False
            for end in range(len(word), i, -1):
                substr = word[i:end]
                if (exclude_whole and len(word) > 1
                        and i == 0 and end == len(word)):
                    continue
                entries = self.lookup_all(substr)
                if not entries:
                    continue
                fill = self._entry_to_fill(entries[0], substr)
                fill["entries"] = entries
                fills.append(fill)
                has_known = True
                i = end
                matched = True
                break
            if not matched:
                fills.append(
                    {
                        "text": word[i],
                        "head": word[i],
                        "roman": "",
                        "senses": [],
                        "pos": "",
                        "source": "UNKNOWN",
                    }
                )
                has_unknown = True
                i += 1

        return {
            "mode": "greedy",
            "fills": fills,
            "has_known": has_known,
            "has_unknown": has_unknown,
        }

    def _greedy_fill(
        self,
        word: str,
        exclude_whole: bool = False,
        upos: str = "",
        debug: bool = False,
    ) -> Dict[str, Any]:
        """Greedy decomposition entrypoint (left-to-right longest match)."""
        _ = (upos, debug)
        return self._greedy_fill_simple(word, exclude_whole=exclude_whole)


# =========================================================================
# JSONL sense-parsing helpers (identical to original)
# =========================================================================


def _build_flat_senses_jsonl(raw_senses: List[Dict[str, Any]]) -> List[str]:
    flat: List[str] = []
    seen_parents: set = set()
    for s in raw_senses:
        raw_glosses = s.get("raw_glosses", [])
        glosses = s.get("glosses", [])
        if len(glosses) > 1:
            parent = glosses[0]
            if parent and parent not in seen_parents:
                seen_parents.add(parent)
                raw_parent = raw_glosses[0] if raw_glosses else parent
                flat.append(raw_parent or parent)
            sub = (
                raw_glosses[-1]
                if (raw_glosses and len(raw_glosses) > 1 and raw_glosses[-1])
                else glosses[-1]
            )
            if sub:
                flat.append(sub)
        else:
            if raw_glosses and raw_glosses[0]:
                flat.append(raw_glosses[0])
            elif glosses:
                flat.append(glosses[0])
    return flat


def _build_senses_full_jsonl(
    raw_senses: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen_parents: set = set()
    for s in raw_senses:
        raw_glosses = s.get("raw_glosses", [])
        glosses = s.get("glosses", [])
        if len(glosses) > 1:
            parent = glosses[0]
            if parent and parent not in seen_parents:
                seen_parents.add(parent)
                raw_parent = raw_glosses[0] if raw_glosses else parent
                out.append({"glosses": [raw_parent or parent]})
            sub_raw = (
                raw_glosses[-1]
                if (raw_glosses and len(raw_glosses) > 1 and raw_glosses[-1])
                else glosses[-1]
            )
            if sub_raw:
                use_glosses = [sub_raw]
                used_raw = bool(raw_glosses and len(raw_glosses) > 1)
            else:
                continue
        else:
            used_raw = bool(raw_glosses and raw_glosses[0])
            use_glosses = raw_glosses if used_raw else glosses
            if not use_glosses:
                if s.get("form_of"):
                    use_glosses = [
                        f"form of {s['form_of'][0].get('word', '')}"
                    ]
                elif s.get("alt_of"):
                    use_glosses = [
                        f"alternative form of {s['alt_of'][0].get('word', '')}"
                    ]
                else:
                    continue

        sense: Dict[str, Any] = {"glosses": use_glosses}
        is_relation_sense = bool(s.get("form_of") or s.get("alt_of"))
        if not used_raw:
            if s.get("qualifier") and not is_relation_sense:
                sense["qualifier"] = s["qualifier"]

        for rel_key in (
            "synonyms",
            "antonyms",
            "related",
            "hypernyms",
            "hyponyms",
            "coordinate_terms",
            "derived",
            "meronyms",
            "holonyms",
        ):
            rel = s.get(rel_key)
            if rel:
                sense[rel_key] = rel

        topics = s.get("topics", [])
        if topics:
            sense["topics"] = topics

        out.append(sense)
    return out
