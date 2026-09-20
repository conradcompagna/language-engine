"""
Korean dictionary — parses official KRDICT JSON term banks (format 4).

Each term bank entry is a dict with all fields from the NIKL XML export,
with only English equivalents retained.

Provides lookup, lookup_all, and fill_token methods matching the
interface expected by pipeline_common.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


# POS values whose first sense is the canonical/citation form
_VERB_ADJ_POS = {"동사", "형용사", "보조 동사", "보조 형용사"}

# Matches conjugation redirect senses like "(매운데, 매우니, ...)→ 맵다"
_REDIRECT_RE = re.compile(r"^\(.*\)→\s*(.+)$")

# Vocabulary level -> sort tier (lower = more common, shown first)
_LEVEL_TIER = {
    "초급": 0,   # beginner — most common
    "중급": 1,   # intermediate
    "고급": 2,   # advanced
    "없음": 3,   # unlabelled — least common
}

# Some KRDICT origin strings contain unresolved refs like
# "<hanja>13233_1</hanja>". Resolve those IDs to visible glyphs.
_HANJA_ID_TO_CHAR: Dict[str, str] = {
    "4076_1": "\u4e39",   # 丹
    "10512_1": "\u7530",  # 田
    "5858_1": "\u5927",   # 大
    "14773_1": "\u8c46",  # 豆
    "6304_1": "\u4ee3",   # 代
    "11210_1": "\u99ac",  # 馬
    "13233_1": "\u842c",  # 萬
    "9761_1": "\u7121",   # 無
    "15837_1": "\u914c",  # 酌
    "6227_1": "\u5b9a",   # 定
    "10782_1": "\u767e",  # 百
}

_HANJA_REF_RE = re.compile(r"<\s*hanja\s*>([^<]+?)<\s*/\s*hanja\s*>", re.IGNORECASE)
_XML_TAG_RE = re.compile(r"<[^>]+>")


def _normalize_origin_hanja(raw_origin: Any) -> str:
    """Resolve KRDICT origin refs like <hanja>13233_1</hanja> to glyphs."""
    text = str(raw_origin or "")
    if not text:
        return ""

    # Defensive decode for escaped XML snippets if any survive upstream.
    text = text.replace("&lt;", "<").replace("&gt;", ">")

    def _replace_ref(match: re.Match) -> str:
        ref_id = str(match.group(1) or "").strip()
        if not ref_id:
            return ""
        return _HANJA_ID_TO_CHAR.get(ref_id, ref_id)

    text = _HANJA_REF_RE.sub(_replace_ref, text)
    # Remove any leftover tags so origin renders as plain text.
    text = _XML_TAG_RE.sub("", text)
    return text.strip()

# KAIST XPOS tag → allowed KRDICT part_of_speech values.
# Used for both hover-panel filtering (union of all tags) and XPOS-aware
# greedy matching (concatenated candidates must match ALL covered tags).
_XPOS_TO_KRDICT_POS: Dict[str, List[str]] = {
    # --- Nouns ---
    "ncn":  ["명사", "접사"],
    "ncpa": ["명사", "동사"],              # action noun (하다-verb stem) → also verb
    "ncps": ["명사", "형용사", "부사"],    # state noun (하다-adj stem) → also adjective/adverb
    "nbn":  ["의존 명사"],                 # bound noun → dependent noun only
    "nbu":  ["의존 명사"],                 # unit/counter noun → dependent noun only
    "nnc":  ["수사"],                      # cardinal number → numeral only
    "nno":  ["수사"],                      # ordinal number → numeral only
    "npd":  ["대명사"],
    "npp":  ["대명사"],
    "nq":   ["명사"],
    # --- Predicates ---
    "pvg":  ["동사"],
    "pvd":  ["동사"],
    "paa":  ["형용사"],
    "pad":  ["관형사"],
    "px":   ["보조 동사", "보조 형용사"],  # auxiliary → aux categories only
    # --- Endings ---
    "ecc":  ["어미"],
    "ecs":  ["어미"],
    "ecx":  ["어미"],
    "ef":   ["어미"],
    "ep":   ["어미"],
    "etm":  ["어미"],
    "etn":  ["어미"],
    # --- Particles / postpositions ---
    "jca":  ["조사"],
    "jcc":  ["조사"],
    "jcj":  ["조사"],
    "jcm":  ["조사"],
    "jco":  ["조사"],
    "jcr":  ["조사"],
    "jcs":  ["조사"],
    "jct":  ["조사"],
    "jp":   ["조사"],
    "jcv":  ["조사"],
    "jxc":  ["조사"],
    "jxf":  ["조사"],
    "jxt":  ["조사"],
    # --- Adverbs ---
    "mad":  ["부사"],
    "mag":  ["부사"],
    "maj":  ["부사"],
    # --- Determiners ---
    "mma":  ["관형사"],
    "mmd":  ["관형사"],
    # --- Derivational affixes ---
    "xp":   ["접사"],
    "xsa":  ["접사"],
    "xsm":  ["접사"],
    "xsn":  ["접사"],
    "xsv":  ["접사"],
    # --- Interjection ---
    "ii":   ["감탄사"],
    # --- Punctuation / other (no filtering) ---
    "sf":   [],
    "sl":   [],
    "sp":   [],
    "sr":   [],
    "su":   [],
    "f":    [],
    "_":    [],
}


_POS_FILTER_EXEMPT_LEXICAL_UNITS = {
    "\uad00\uc6a9\uad6c",        # \uad00\uc6a9\uad6c (idiom)
    "\uad6c",                    # \uad6c (phrase)
    "\uc18d\ub2f4",             # \uc18d\ub2f4 (proverb)
    "\ubb38\ubc95\u2027\ud45c\ud604",  # \ubb38\ubc95\u2027\ud45c\ud604 (grammar expression)
}


_XPOS_MATCH_IGNORE_TAGS = {"xp", "xsa", "xsm", "xsn", "xsv"}


def _normalize_lexical_unit(raw_unit: Any) -> str:
    """Normalize lexical_unit text for stable comparisons."""
    unit = str(raw_unit or "").strip()
    if not unit:
        return ""
    # Normalize middle-dot variants (e.g. \u00b7 vs \u2027).
    return unit.replace("\u00b7", "\u2027")


def _entry_is_pos_filter_exempt(entry: Dict[str, Any]) -> bool:
    """Return True for lexical-unit categories exempt from POS/XPOS filtering."""
    if not entry:
        return False
    return _normalize_lexical_unit(entry.get("lexical_unit", "")) in _POS_FILTER_EXEMPT_LEXICAL_UNITS


def entries_match_xpos(entries: List[Dict[str, Any]], xpos_tags: List[str]) -> bool:
    """Return True if at least one entry's pos_raw is allowed by ALL XPOS tags.

    A concatenated dictionary entry (one that spans multiple morphemes)
    must be consistent with *every* covered morpheme's XPOS tag, not
    just one.  For each tag, we build its allowed POS set; a candidate
    entry passes only if its ``pos_raw`` appears in every tag's set.

    Used by the Korean lookup to validate that an exact/greedy candidate
    spanning multiple morphemes is consistent with the morphological analysis.

    Idiom / phrase / proverb / grammar-expression entries bypass POS/XPOS
    gating so rare fixed expressions can still match even when POS tags
    do not align cleanly with KRDICT POS buckets.
    """
    if not entries or not xpos_tags:
        return True  # no constraint — allow

    # Special lexical-unit entries bypass POS filtering.
    if any(_entry_is_pos_filter_exempt(e) for e in entries):
        return True

    # Ignore derivational affix tags for match gating so a lexical base to the
    # left can still be accepted as a combined span in greedy/exact validation.
    normalized_tags = []
    for tag in xpos_tags:
        norm = str(tag or "").strip().lower()
        if not norm:
            continue
        if norm in _XPOS_MATCH_IGNORE_TAGS:
            continue
        normalized_tags.append(norm)

    if not normalized_tags:
        return True

    # Build per-tag allowed sets
    per_tag_sets: List[set] = []
    for tag in normalized_tags:
        pos_list = _XPOS_TO_KRDICT_POS.get(tag, [])
        if pos_list:
            per_tag_sets.append(set(pos_list))

    if not per_tag_sets:
        return True  # unknown tags — don't reject

    # Intersect: an entry must be allowed by ALL tags
    allowed = per_tag_sets[0]
    for s in per_tag_sets[1:]:
        allowed = allowed & s
    if not allowed:
        return False  # no POS satisfies all tags simultaneously

    return any(e.get("pos_raw", "") in allowed for e in entries)


def _entry_tier_key(entry: Dict[str, Any]) -> int:
    """Sort key: vocabulary-level tier (0 = most common, 3 = unlabelled)."""
    return entry.get("tier", 3)


class KoreanDict:
    """In-memory Korean dictionary built from official KRDICT term banks."""

    def __init__(self, path):
        path = Path(path)
        self._by_headword: Dict[str, List[Dict[str, Any]]] = {}
        self._max_word_len = 1
        self._load(path)

    def _load(self, dict_dir: Path) -> None:
        """Load all term_bank_*.json files from the directory."""
        bank_files = sorted(dict_dir.glob("term_bank_*.json"))
        if not bank_files:
            raise FileNotFoundError(f"No term_bank_*.json files found in {dict_dir}")

        total = 0
        for bank_path in bank_files:
            with bank_path.open("r", encoding="utf-8") as f:
                entries = json.load(f)

            for raw in entries:
                entry = self._parse_entry(raw)
                hw = entry["headword"]
                # Strip affix/suffix dashes to get bare form
                bare = hw.lstrip("-").rstrip("-")

                # Index under bare form only (no synthetic 다 expansion)
                keys = set()
                if bare:
                    keys.add(bare)

                for key in keys:
                    self._by_headword.setdefault(key, []).append(entry)
                    if len(key) > self._max_word_len:
                        self._max_word_len = len(key)
                total += 1

        # Sort each headword's entries by vocabulary-level tier (most common first)
        for entries_list in self._by_headword.values():
            entries_list.sort(key=_entry_tier_key)

        redirects_resolved = self._resolve_redirects()
        print(f"[INFO] Korean dictionary loaded: {total:,} entries, "
              f"max word length {self._max_word_len}, "
              f"{redirects_resolved} redirects resolved")

    def _resolve_redirects(self) -> int:
        """Annotate redirect entries with their Korean target words.

        Redirect entries have senses like "(매운데, 매우니, ...)→ 맵다" and no
        real definitions.  Instead of replacing them, rewrite their senses to
        show the target word(s) so users can look those up directly.
        """
        resolved = 0
        seen_ids: set = set()
        for entries in self._by_headword.values():
            for entry in entries:
                eid = id(entry)
                if eid in seen_ids:
                    continue
                seen_ids.add(eid)
                senses = entry.get("senses", [])
                if not senses:
                    continue
                targets = []
                all_redirect = True
                for s in senses:
                    m = _REDIRECT_RE.match(s.strip())
                    if m:
                        raw_target = m.group(1).strip()
                        raw_target = raw_target.replace("\u2018", "").replace("\u2019", "")
                        raw_target = raw_target.replace("'", "")
                        for part in raw_target.split(","):
                            word = re.sub(r"\s*\d+$", "", part.strip())
                            if word:
                                targets.append(word)
                    else:
                        all_redirect = False
                        break
                if all_redirect and targets:
                    # Rewrite senses to show target words as clickable references
                    entry["senses"] = [f"→ {t}" for t in targets]
                    entry["redirect_targets"] = targets
                    resolved += 1

        return resolved

    @staticmethod
    def _parse_entry(raw: dict) -> Dict[str, Any]:
        """Parse a single rich JSON entry into the internal format.

        Preserves ALL fields from the official KRDICT export.
        The ``senses`` key is a flat list of English definition strings
        for pipeline compatibility; the full structured data lives in
        ``senses_full``.
        """
        headword = raw["headword"]
        part_of_speech = raw.get("part_of_speech", "")
        vocabulary_level = raw.get("vocabulary_level", "없음")
        pronunciation = raw.get("pronunciation", "")
        origin = _normalize_origin_hanja(raw.get("origin", ""))
        raw_senses = raw.get("senses", [])

        # --- flat English senses for pipeline compat ---
        flat_senses: List[str] = []
        canonical_form = ""

        is_verb_adj = part_of_speech in _VERB_ADJ_POS
        is_grammar = raw.get("lexical_unit") == "문법‧표현"

        for i, s in enumerate(raw_senses):
            en_lemma = s.get("en_lemma", "")
            en_def = s.get("en_definition", "")
            # Build a combined English gloss: "lemma; definition"
            # or whichever is available
            if en_lemma and en_def:
                gloss = f"{en_lemma}; {en_def}"
            elif en_lemma:
                gloss = en_lemma
            elif en_def:
                gloss = en_def
            else:
                # Fall back to Korean definition if no English
                gloss = s.get("definition_ko", "")

            if i == 0 and (is_verb_adj or is_grammar):
                # First sense of verb/adj: canonical citation form
                canonical_form = en_lemma or s.get("definition_ko", "")
                # Still include it as a sense
            flat_senses.append(gloss)

        # Tier: derive from vocabulary level (lower = more common)
        tier = _LEVEL_TIER.get(vocabulary_level, 3)

        # Normalize POS with underscores to spaces
        pos = part_of_speech.replace("_", " ")

        return {
            # --- pipeline-required fields ---
            "headword": headword,
            "reading": pronunciation,
            "pos": pos,
            "pos_raw": part_of_speech,
            "level": vocabulary_level if vocabulary_level != "없음" else "",
            "tier": tier,
            "senses": flat_senses,
            "canonical_form": canonical_form,
            # --- rich fields from official KRDICT ---
            "entry_id": raw.get("entry_id", ""),
            "homonym_number": raw.get("homonym_number", ""),
            "lexical_unit": raw.get("lexical_unit", ""),
            "origin": origin,
            "pronunciation_url": raw.get("pronunciation_url", ""),
            "conjugations": raw.get("conjugations", []),
            "related_forms": raw.get("related_forms", []),
            "vocabulary_level": vocabulary_level,
            "senses_full": raw_senses,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, word: str) -> Optional[Dict[str, Any]]:
        """Return the first entry for *word*, or None."""
        entries = self._by_headword.get(word)
        if not entries:
            return None
        return entries[0]

    def lookup_all(self, word: str) -> List[Dict[str, Any]]:
        """Return all entries for *word*, deduplicated, in insertion order.

        Runtime normalization: also tries *word* + 다 (infinitive expansion)
        so that verb stems like 없 → 없다, 광범하 → 광범하다 resolve.
        """
        seen: set = set()
        out: List[Dict[str, Any]] = []
        # Try the word as-is, then with 다 appended
        candidates = [word]
        if word and not word.endswith("다"):
            candidates.append(word + "다")
        for candidate in candidates:
            for e in (self._by_headword.get(candidate) or []):
                eid = id(e)
                if eid not in seen:
                    seen.add(eid)
                    out.append(e)
        # Sort by vocabulary-level tier (most common first)
        out.sort(key=_entry_tier_key)
        return out

    def filter_entries_by_xpos(
        self,
        entries: List[Dict[str, Any]],
        xpos_tags: List[str],
    ) -> "tuple[List[Dict[str, Any]], List[Dict[str, Any]]]":
        """Filter entries by KAIST XPOS tags, returning (primary, other).

        Builds the set of allowed KRDICT POS values from the XPOS tags,
        then splits entries into those whose ``pos_raw`` matches any
        allowed value (primary) and the rest (other).

        Single-entry words are never filtered.  If no entries match,
        everything is returned as primary.
        """
        if not entries or len(entries) <= 1:
            return list(entries), []
        if not xpos_tags:
            return list(entries), []

        normalized_tags = [str(tag or "").strip().lower() for tag in xpos_tags if str(tag or "").strip()]
        if not normalized_tags:
            return list(entries), []

        def _split_by_allowed(allowed: set) -> "tuple[List[Dict[str, Any]], List[Dict[str, Any]]]":
            if not allowed:
                return [], list(entries)
            primary_local: List[Dict[str, Any]] = []
            other_local: List[Dict[str, Any]] = []
            for entry in entries:
                # Special lexical-unit entries bypass POS filtering and
                # always remain in the primary bucket.
                if _entry_is_pos_filter_exempt(entry):
                    primary_local.append(entry)
                    continue
                pos_raw = entry.get("pos_raw", "")
                if pos_raw in allowed:
                    primary_local.append(entry)
                else:
                    other_local.append(entry)
            return primary_local, other_local

        # Prefer the rightmost morpheme tag when multiple XPOS tags are present.
        # For Korean eojeol analyses (e.g. ncn+jxt, pvg+ef), the final tag often
        # captures the surface syntactic function shown in context.
        if len(normalized_tags) > 1:
            tail_allowed = set(_XPOS_TO_KRDICT_POS.get(normalized_tags[-1], []))
            tail_primary, tail_other = _split_by_allowed(tail_allowed)
            if tail_primary:
                return tail_primary, tail_other

        allowed_pos: set = set()
        for tag in normalized_tags:
            for pos in _XPOS_TO_KRDICT_POS.get(tag, []):
                allowed_pos.add(pos)

        if not allowed_pos:
            return list(entries), []

        primary, other = _split_by_allowed(allowed_pos)

        if not primary:
            return list(entries), []
        return primary, other

    def fill_token(
        self,
        word: str,
        allow_exact: bool = True,
        exclude_whole: bool = False,
        boundaries: "List[int] | None" = None,
        xpos_tags: "List[str] | None" = None,
        morphemes: "List[str] | None" = None,
    ) -> Dict[str, Any]:
        """
        Build a fill structure for the frontend.

        Tries exact match first; falls back to greedy forward maximum matching.
        *boundaries* is an optional list of character offsets where morpheme
        splits occur (e.g. for "중력장이" with morphemes ["중력장","이"],
        boundaries=[3]).  The greedy matcher will not match across these.

        *xpos_tags* and *morphemes* enable XPOS-aware validation: when a
        greedy candidate spans multiple morphemes, its entries are checked
        against the XPOS tags of those morphemes and rejected if no entry
        matches any allowed POS.
        """
        if allow_exact and not exclude_whole:
            entries = self.lookup_all(word)
            if entries:
                # When XPOS tags are provided and the word spans multiple
                # morphemes, validate the exact match.  Reject if no entry
                # has a POS allowed by the morpheme XPOS tags.
                xpos_reject = (
                    xpos_tags and morphemes and len(morphemes) > 1
                    and not entries_match_xpos(entries, xpos_tags)
                )
                if not xpos_reject:
                    fill = self._entry_to_fill(entries[0], word)
                    fill["entries"] = entries
                    return {
                        "mode": "exact",
                        "fills": [fill],
                        "has_known": True,
                        "has_unknown": False,
                    }

        return self._greedy_fill(
            word, exclude_whole=exclude_whole, boundaries=boundaries,
            xpos_tags=xpos_tags, morphemes=morphemes,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _entry_to_fill(self, entry: Dict, text: str) -> Dict[str, Any]:
        """Convert an entry dict to a fill piece.

        Passes ALL rich fields so the frontend Korean template can
        render origin, examples, conjugations, etc.
        """
        return {
            "text": text,
            "head": text,
            "roman": entry["reading"],
            "senses": entry["senses"],
            "pos": entry["pos"],
            "level": entry["level"],
            "canonical_form": entry["canonical_form"],
            "source": "KRDICT",
            # --- rich KRDICT fields for the frontend ---
            "entry_id": entry.get("entry_id", ""),
            "homonym_number": entry.get("homonym_number", ""),
            "lexical_unit": entry.get("lexical_unit", ""),
            "origin": entry.get("origin", ""),
            "conjugations": entry.get("conjugations", []),
            "related_forms": entry.get("related_forms", []),
            "senses_full": entry.get("senses_full", []),
        }

    def _greedy_fill(
        self, word: str, exclude_whole: bool = False,
        boundaries: "List[int] | None" = None,
        xpos_tags: "List[str] | None" = None,
        morphemes: "List[str] | None" = None,
    ) -> Dict[str, Any]:
        """Greedy forward maximum matching over the dictionary.

        When *boundaries* are provided, matches must start and end at
        boundary positions (morpheme edges).  This allows combining
        adjacent morphemes (e.g. "광범"+"하" → "광범하" matches "광범하다")
        while preventing splits within a morpheme.

        When *xpos_tags* and *morphemes* are provided, a candidate that
        spans two or more morphemes is validated: at least one dictionary
        entry must have a ``pos_raw`` allowed by the XPOS tags of the
        covered morphemes.  Otherwise the candidate is rejected and the
        algorithm tries a shorter span.
        """
        fills: List[Dict[str, Any]] = []
        i = 0
        has_known = False
        has_unknown = False

        # Build sorted list of valid split points (boundaries + string edges)
        if boundaries:
            split_pts = sorted(set(boundaries) | {0, len(word)})
        else:
            split_pts = None

        # Build morpheme-index-by-offset map for XPOS validation.
        # morpheme_at_offset[char_offset] → morpheme index
        morpheme_at_offset: "Dict[int, int] | None" = None
        if morphemes and xpos_tags and boundaries:
            morpheme_at_offset = {}
            offset = 0
            for m_idx, m in enumerate(morphemes):
                for c in range(len(m)):
                    morpheme_at_offset[offset + c] = m_idx
                offset += len(m)

        def _xpos_ok(entries: List[Dict[str, Any]], start: int, end: int) -> bool:
            """Check if entries are consistent with the XPOS of covered morphemes."""
            if not morpheme_at_offset or not xpos_tags:
                return True
            # Find which morpheme indices this span covers
            covered = set()
            for off in range(start, end):
                m_idx = morpheme_at_offset.get(off)
                if m_idx is not None:
                    covered.add(m_idx)
            if len(covered) <= 1:
                return True  # single morpheme — no cross-morpheme check needed
            # Collect the XPOS tags of the covered morphemes
            covered_tags = []
            for m_idx in covered:
                if m_idx < len(xpos_tags):
                    covered_tags.append(xpos_tags[m_idx])
            if not covered_tags:
                return True
            return entries_match_xpos(entries, covered_tags)

        while i < len(word):
            best_len = 0
            best_entries = None

            if split_pts:
                # Try all valid end positions (must land on a split point),
                # longest first.
                valid_ends = [p for p in split_pts if p > i]
                for end in reversed(valid_ends):
                    length = end - i
                    if length > self._max_word_len:
                        continue
                    if exclude_whole and i == 0 and length == len(word):
                        continue
                    candidate = word[i:end]
                    entries = self.lookup_all(candidate)
                    if entries and _xpos_ok(entries, i, end):
                        best_len = length
                        best_entries = entries
                        break
            else:
                # No boundaries: try all lengths, longest first
                max_try = min(self._max_word_len, len(word) - i)
                for length in range(max_try, 0, -1):
                    if exclude_whole and i == 0 and length == len(word):
                        continue
                    candidate = word[i : i + length]
                    entries = self.lookup_all(candidate)
                    if entries:
                        best_len = length
                        best_entries = entries
                        break

            if best_entries is not None:
                text = word[i : i + best_len]
                fill = self._entry_to_fill(best_entries[0], text)
                fill["entries"] = best_entries
                fills.append(fill)
                has_known = True
                i += best_len
            else:
                # No boundary-aligned match found.  Fall back to
                # character-level greedy within the next morpheme.
                if split_pts:
                    next_pt = len(word)
                    for p in split_pts:
                        if p > i:
                            next_pt = p
                            break
                    morpheme = word[i:next_pt]
                else:
                    morpheme = word[i:]
                    next_pt = len(word)

                # Character-level greedy within this morpheme
                j = 0
                while j < len(morpheme):
                    sub_len = 0
                    sub_entries = None
                    max_try = min(self._max_word_len, len(morpheme) - j)
                    for length in range(max_try, 0, -1):
                        candidate = morpheme[j : j + length]
                        entries = self.lookup_all(candidate)
                        if entries:
                            sub_len = length
                            sub_entries = entries
                            break
                    if sub_entries is not None:
                        text = morpheme[j : j + sub_len]
                        fill = self._entry_to_fill(sub_entries[0], text)
                        fill["entries"] = sub_entries
                        fills.append(fill)
                        has_known = True
                        j += sub_len
                    else:
                        ch = morpheme[j]
                        fills.append({
                            "text": ch,
                            "head": ch,
                            "roman": "",
                            "senses": [],
                            "pos": "",
                            "level": "",
                            "canonical_form": "",
                            "source": "UNKNOWN",
                        })
                        has_unknown = True
                        j += 1
                i = next_pt

        return {
            "mode": "greedy",
            "fills": fills,
            "has_known": has_known,
            "has_unknown": has_unknown,
        }
