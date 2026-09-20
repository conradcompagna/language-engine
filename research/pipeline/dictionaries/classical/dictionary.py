"""
Classical Chinese dictionary — parses the cnotes_zh_en_dict.tsv (Fo Guang Shan)
tab-separated export.

TSV columns (1-indexed):
  1  id
  2  simplified
  3  traditional  (\\N if same as simplified)
  4  pinyin
  5  english
  6  pos
  7  grammar_category_zh  (\\N if empty)
  8  grammar_category_en  (\\N if empty)
  9  register_zh          (文言文 / 现代汉语 / 成语 / ...)
 10  register_en          (Literary Chinese / Modern Chinese / Idiom / ...)
 11  topic_zh             (\\N if empty)
 12  topic_en             (\\N if empty)
 13  subtopic_zh          (\\N if empty)
 14  subtopic_en          (\\N if empty)
 15  notes
 16  concept_id           (groups senses sharing the same headword)

Provides lookup, lookup_all, and fill_token methods matching the interface
expected by pipeline_common.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


# Dictionary POS strings → short labels (standard abbreviation scheme)
_POS_LABELS: Dict[str, str] = {
    "noun": "n",
    "verb": "v",
    "adjective": "adj",
    "adverb": "adv",
    "pronoun": "pron",
    "preposition": "prep",
    "conjunction": "conj",
    "particle": "ptcl",
    "interjection": "intj",
    "proper noun": "prop",
    "measure word": "mw",
    "number": "num",
    "ordinal": "ord",
    "onomatopoeia": "onom",
    "phonetic": "phon",
    "prefix": "pfx",
    "suffix": "sfx",
    "infix": "ifx",
    "bound form": "bound",
    "auxiliary verb": "aux",
    "radical": "rad",
    "foreign": "for",
    "set phrase": "idm",
    "phrase": "phr",
    "expression": "expr",
    "pattern": "pat",
}


def _normalize_pos(raw: str) -> str:
    """Return abbreviated POS label for display."""
    return _POS_LABELS.get(raw.strip().lower(), raw.strip())


# ---------------------------------------------------------------------------
# UPOS → dictionary POS mapping for entry-level filtering
# ---------------------------------------------------------------------------
# Maps UD UPOS tags to the set of dictionary ``pos_raw`` values (lowercased)
# that are semantically compatible.

_UPOS_TO_DICT_POS: Dict[str, set] = {
    "NOUN":  {"noun", "measure word", "bound form"},
    "VERB":  {"verb", "auxiliary verb"},
    "ADJ":   {"adjective"},
    "ADV":   {"adverb"},
    "PRON":  {"pronoun"},
    "PROPN": {"proper noun"},
    "NUM":   {"number", "ordinal"},
    "ADP":   {"preposition"},
    "CCONJ": {"conjunction"},
    "SCONJ": {"conjunction"},
    "PART":  {"particle"},
    "AUX":   {"auxiliary verb", "verb"},
    "INTJ":  {"interjection", "onomatopoeia"},
    "SYM":   {"radical", "phonetic"},
}

# POS values that bypass UPOS filtering — always stay in primary.
_FILTER_EXEMPT_POS: frozenset = frozenset({
    "set phrase", "phrase", "expression", "pattern",
})


def _tsv_field(raw: str) -> str:
    """Return empty string for SQL-style NULL markers."""
    if raw == "\\N" or raw == "NULL":
        return ""
    return raw.strip()


class ClassicalChineseDict:
    """In-memory dictionary for Classical Chinese keyed by simplified form."""

    def __init__(self, path: str | Path):
        self._by_simplified: Dict[str, List[Dict[str, Any]]] = {}
        self._by_traditional: Dict[str, List[Dict[str, Any]]] = {}
        self._max_word_len = 1
        self._load(Path(path))

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self, path: Path) -> None:
        if not path.exists():
            print(f"[WARN] Classical Chinese dictionary file not found: {path}")
            return

        count = 0
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue

                cols = line.split("\t")
                if len(cols) < 16:
                    continue

                # Skip non-numeric id column (header or comment lines)
                try:
                    int(cols[0])
                except ValueError:
                    continue

                entry = self._parse_row(cols)
                if not entry:
                    continue

                simplified = entry["simplified"]
                traditional = entry["traditional"]

                self._by_simplified.setdefault(simplified, []).append(entry)
                if len(simplified) > self._max_word_len:
                    self._max_word_len = len(simplified)

                if traditional and traditional != simplified:
                    self._by_traditional.setdefault(traditional, []).append(entry)
                    if len(traditional) > self._max_word_len:
                        self._max_word_len = len(traditional)

                count += 1

        print(
            f"[INFO] Classical Chinese dictionary loaded: {count:,} entries, "
            f"{len(self._by_simplified)} simplified keys, "
            f"max word length {self._max_word_len}"
        )

    @staticmethod
    def _parse_row(cols: List[str]) -> Optional[Dict[str, Any]]:
        """Parse a single TSV row into the internal entry format."""
        entry_id = cols[0].strip()
        simplified = cols[1].strip()
        traditional = _tsv_field(cols[2]) or simplified
        pinyin = _tsv_field(cols[3])
        english = _tsv_field(cols[4])
        pos = _tsv_field(cols[5])
        grammar_zh = _tsv_field(cols[6])
        grammar_en = _tsv_field(cols[7])
        register_zh = _tsv_field(cols[8])
        register_en = _tsv_field(cols[9])
        topic_zh = _tsv_field(cols[10])
        topic_en = _tsv_field(cols[11])
        subtopic_zh = _tsv_field(cols[12])
        subtopic_en = _tsv_field(cols[13])
        notes = _tsv_field(cols[14])
        concept_id = _tsv_field(cols[15])

        if not simplified or not english:
            return None

        return {
            "entry_id": entry_id,
            "simplified": simplified,
            "traditional": traditional,
            "pinyin": pinyin,
            "english": english,
            "pos": _normalize_pos(pos),
            "pos_raw": pos,
            "grammar_zh": grammar_zh,
            "grammar_en": grammar_en,
            "register_zh": register_zh,
            "register_en": register_en,
            "topic_zh": topic_zh,
            "topic_en": topic_en,
            "subtopic_zh": subtopic_zh,
            "subtopic_en": subtopic_en,
            "notes": notes,
            "concept_id": concept_id,
            # Pipeline-compatible fields
            "headword": simplified,
            "reading": pinyin,
            "senses": [english],
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, word: str) -> Optional[Dict[str, Any]]:
        """Return the first entry for *word*, or None.

        Tries simplified first, then traditional.
        """
        entries = self._by_simplified.get(word)
        if entries:
            return entries[0]
        entries = self._by_traditional.get(word)
        if entries:
            return entries[0]
        return None

    def lookup_all(self, word: str) -> List[Dict[str, Any]]:
        """Return all entries for *word*.

        Merges simplified and traditional buckets, deduplicating by entry_id.
        """
        seen: set = set()
        out: List[Dict[str, Any]] = []

        for entries in (
            self._by_simplified.get(word, []),
            self._by_traditional.get(word, []),
        ):
            for e in entries:
                eid = e.get("entry_id", id(e))
                if eid in seen:
                    continue
                seen.add(eid)
                out.append(e)
        return out

    def fill_token(
        self,
        word: str,
        allow_exact: bool = True,
        exclude_whole: bool = False,
    ) -> Dict[str, Any]:
        """Build a dict_fill structure for a token.

        If the whole word is in the dictionary, return a single fill
        (unless exact matching is disabled).
        Otherwise, greedy forward maximum matching on characters.
        """
        # Try whole-word lookup first
        if allow_exact and not exclude_whole:
            entry = self.lookup(word)
            if entry:
                return {
                    "mode": "exact",
                    "fills": [self._entry_to_fill(entry, word)],
                    "has_known": True,
                    "has_unknown": False,
                }

        # Greedy forward maximum matching
        fills: List[Dict[str, Any]] = []
        has_known = False
        has_unknown = False
        i = 0

        while i < len(word):
            matched = False
            max_end = min(i + self._max_word_len, len(word))
            for end in range(max_end, i, -1):
                substr = word[i:end]
                if (
                    exclude_whole
                    and len(word) > 1
                    and i == 0
                    and end == len(word)
                    and substr == word
                ):
                    continue
                sub_entry = self.lookup(substr)
                if sub_entry:
                    has_known = True
                    fills.append(self._entry_to_fill(sub_entry, substr))
                    i = end
                    matched = True
                    break
            if not matched:
                has_unknown = True
                fills.append({
                    "text": word[i],
                    "head": word[i],
                    "roman": "",
                    "senses": [],
                    "pos": "",
                    "source": "UNKNOWN",
                })
                i += 1

        return {
            "mode": "greedy",
            "fills": fills,
            "has_known": has_known,
            "has_unknown": has_unknown,
        }

    # ------------------------------------------------------------------
    # UPOS → dictionary POS filtering
    # ------------------------------------------------------------------

    def filter_entries_by_upos(
        self,
        entries: List[Dict[str, Any]],
        upos: str,
    ) -> "tuple[List[Dict[str, Any]], List[Dict[str, Any]]]":
        """Filter entries by UPOS tag, returning (primary, other).

        Filtering is POS-based only: entries whose ``pos_raw`` does not
        match the allowed set for the token's UPOS tag are demoted.

        Register (Literary Chinese / Modern Chinese / Idiom / Proverb) is
        not used for filtering, so both literary and modern senses remain
        eligible for primary display when POS matches.

        Exempt POS values (set phrase, phrase, idiom, proverb) always
        stay in primary. Single-entry words are never filtered.
        """
        if not entries:
            return [], []
        if len(entries) <= 1:
            return list(entries), []

        base_entries = list(entries)
        upos_tag = str(upos or "").strip().upper()
        if not upos_tag:
            return base_entries, []

        allowed = _UPOS_TO_DICT_POS.get(upos_tag)
        if not allowed:
            return base_entries, []

        primary: List[Dict[str, Any]] = []
        other: List[Dict[str, Any]] = []
        for e in base_entries:
            pos_raw = str(e.get("pos_raw", "") or "").strip().lower()
            if pos_raw in _FILTER_EXEMPT_POS or pos_raw in allowed:
                primary.append(e)
            else:
                other.append(e)

        if not primary:
            # No UPOS match � keep all entries visible.
            return base_entries, []

        return primary, other
    # Alias for compatibility with pipeline_common
    def filter_entries_by_xpos(
        self,
        entries: List[Dict[str, Any]],
        xpos: str,
    ) -> "tuple[List[Dict[str, Any]], List[Dict[str, Any]]]":
        return self.filter_entries_by_upos(entries, xpos)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entry_to_fill(entry: Dict[str, Any], text: str) -> Dict[str, Any]:
        """Convert an entry dict to a fill piece."""
        return {
            "text": text,
            "head": entry["simplified"],
            "roman": entry["pinyin"],
            "senses": entry["senses"],
            "pos": entry["pos"],
            "source": "CNOTESDICT",
        }
