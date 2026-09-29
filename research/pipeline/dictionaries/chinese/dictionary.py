"""
CC-CEDICT dictionary parser and lookup for Chinese.

Parses the standard CC-CEDICT format:
    Traditional Simplified [pinyin] /def1/def2/.../

Provides word-level and character-level lookup.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional


# Regex to parse a CEDICT line:
#   Traditional Simplified [pinyin] /def1/def2/
_CEDICT_LINE_RE = re.compile(
    r'^(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+/(.+)/$'
)


class ChineseDict:
    """
    In-memory CC-CEDICT dictionary keyed by simplified Chinese.

    Also supports traditional-keyed lookup as a fallback.
    """

    def __init__(self, path: str | Path):
        self._by_simplified: Dict[str, List[Dict[str, Any]]] = {}
        self._by_traditional: Dict[str, List[Dict[str, Any]]] = {}
        self._load(Path(path))

    def _load(self, path: Path) -> None:
        if not path.exists():
            print(f"[WARN] CEDICT file not found: {path}")
            return

        count = 0
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                # Skip comments and metadata
                if not line or line.startswith("#") or line.startswith("%"):
                    continue

                m = _CEDICT_LINE_RE.match(line)
                if not m:
                    continue

                traditional = m.group(1)
                simplified = m.group(2)
                pinyin_raw = m.group(3)
                defs_raw = m.group(4)

                senses = [d.strip() for d in defs_raw.split("/") if d.strip()]
                pinyin = _normalize_pinyin(pinyin_raw)

                entry = {
                    "traditional": traditional,
                    "simplified": simplified,
                    "pinyin": pinyin,
                    "senses": senses,
                }

                if simplified not in self._by_simplified:
                    self._by_simplified[simplified] = []
                self._by_simplified[simplified].append(entry)

                if traditional != simplified:
                    if traditional not in self._by_traditional:
                        self._by_traditional[traditional] = []
                    self._by_traditional[traditional].append(entry)

                count += 1

        print(f"[INFO] Loaded {count} CEDICT entries ({len(self._by_simplified)} simplified keys)")

    def lookup(self, word: str) -> Optional[Dict[str, Any]]:
        """
        Look up a word. Returns the first matching entry dict or None.

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
        """
        Return all entries for a word.

        Bucket rules:
        - If the queried surface exists as a simplified key, use that bucket.
        - If it also exists as a traditional key, include that bucket too.
        - If it exists only as traditional, use only the traditional bucket.

        Important: do NOT expand traditional entries through linked simplified
        forms. That cross-surface expansion incorrectly lumps senses that are
        unique to one written form.
        """
        def _entry_key(entry: Dict[str, Any]) -> tuple:
            return (
                str(entry.get("traditional", "") or ""),
                str(entry.get("simplified", "") or ""),
                str(entry.get("pinyin", "") or ""),
                tuple(entry.get("senses", []) or []),
            )

        def _dedupe_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            seen = set()
            for e in entries:
                k = _entry_key(e)
                if k in seen:
                    continue
                seen.add(k)
                out.append(e)
            return out

        simp_entries = list(self._by_simplified.get(word, []))
        trad_entries = list(self._by_traditional.get(word, []))

        if simp_entries and trad_entries:
            return _dedupe_entries(simp_entries + trad_entries)
        if simp_entries:
            return simp_entries
        if trad_entries:
            return trad_entries
        return []

    def fill_token(
        self,
        word: str,
        allow_exact: bool = True,
        exclude_whole: bool = False,
    ) -> Dict[str, Any]:
        """
        Build a dict_fill structure for a token.

        If the whole word is in the dictionary, return a single fill
        (unless exact matching is disabled).
        Otherwise, break it into individual characters and look each up.

        Returns:
            {
                "mode": "greedy",
                "fills": [{"text": ..., "head": ..., "roman": ..., "senses": [...], "source": ...}, ...],
                "has_known": bool,
                "has_unknown": bool,
            }
        """
        # Try whole-word lookup first
        entry = self.lookup(word)
        if allow_exact and not exclude_whole and entry:
            return {
                "mode": "exact",
                "fills": [{
                    "text": word,
                    "head": word,
                    "roman": entry["pinyin"],
                    "senses": entry["senses"],
                    "source": "CEDICT",
                }],
                "has_known": True,
                "has_unknown": False,
            }

        # Greedy forward maximum matching: at each position, try the
        # longest possible substring that exists in the dictionary,
        # then advance past it.
        fills = []
        has_known = False
        has_unknown = False
        i = 0

        while i < len(word):
            matched = False
            # Try longest substring first, down to single character
            for end in range(len(word), i, -1):
                substr = word[i:end]
                # Subword decomposition mode: don't allow the original token
                # itself to be returned as a single exact piece.
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
                    fills.append({
                        "text": substr,
                        "head": substr,
                        "roman": sub_entry["pinyin"],
                        "senses": sub_entry["senses"],
                        "source": "CEDICT",
                    })
                    i = end
                    matched = True
                    break
            if not matched:
                # Single character not in dictionary
                has_unknown = True
                fills.append({
                    "text": word[i],
                    "head": word[i],
                    "roman": "",
                    "senses": [],
                    "source": "UNKNOWN",
                })
                i += 1

        return {
            "mode": "greedy",
            "fills": fills,
            "has_known": has_known,
            "has_unknown": has_unknown,
        }


def _normalize_pinyin(raw: str) -> str:
    """
    Normalize pinyin string: lowercase, collapse whitespace.
    Keep tone numbers as-is (e.g., "bei3 jing1").
    """
    return " ".join(raw.lower().split())
