"""
Vietnamese dictionary â€” parses Kaikki Wiktionary JSONL export.

Each line is a JSON object with fields:
  word, pos, senses[{glosses, tags, raw_tags, ...}],
  sounds[{ipa, tags, ...}], forms[{form, tags}],
  etymology_text, derived, synonyms, antonyms, related, ...

Provides lookup, lookup_all, and fill_token methods matching the
interface expected by pipeline_common.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


# Kaikki POS strings â†’ short labels for display
_POS_LABELS: Dict[str, str] = {
    "noun": "n",
    "verb": "v",
    "adj": "adj",
    "adv": "adv",
    "pron": "pron",
    "prep": "prep",
    "conj": "conj",
    "det": "det",
    "num": "num",
    "intj": "intj",
    "particle": "ptcl",
    "classifier": "clf",
    "prefix": "pfx",
    "suffix": "sfx",
    "affix": "afx",
    "combining_form": "comb",
    "phrase": "phr",
    "proverb": "prov",
    "character": "char",
    "name": "name",
    "romanization": "rom",
    "punct": "punct",
    "symbol": "sym",
}


# Structural / metadata tags that should not be shown in the UI —
# the gloss text already describes these relationships.
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


def _etym_key(entry: Dict[str, Any]) -> str:
    """Return a grouping key for entries sharing the same etymology.

    Entries with the same ``etymology_number`` (>0) belong together.
    When there is no numbering (0), fall back to the etymology text.
    """
    num = entry.get("etymology_number", 0)
    if num and num > 0:
        return f"n:{num}"
    return f"t:{entry.get('etymology', '')}"


def _normalize_pos(raw: str) -> str:
    return _POS_LABELS.get(raw, raw)


def _extract_ipa(sounds: List[Dict[str, Any]]) -> str:
    """Pick the best IPA string from the sounds list.

    Preference: HÃ  Ná»™i (standard Northern) > any tagged > first available.
    """
    if not sounds:
        return ""
    best = ""
    for s in sounds:
        ipa = s.get("ipa", "")
        if not ipa:
            continue
        tags = s.get("tags", [])
        note = s.get("note", "")
        tag_str = " ".join(tags).lower() + " " + note.lower()
        if "hÃ " in tag_str or "hanoi" in tag_str or "ná»™i" in tag_str:
            return ipa
        if not best:
            best = ipa
    return best


def _extract_han_tu(forms: List[Dict[str, Any]]) -> str:
    """Extract HÃ¡n tá»± (CJK) forms from the forms list."""
    chars = []
    for f in forms:
        tags = f.get("tags", [])
        if "CJK" in tags or "Sinitic" in tags:
            chars.append(f.get("form", ""))
    return ", ".join(c for c in chars if c)


def _extract_classifiers(forms: List[Dict[str, Any]]) -> List[str]:
    """Extract classifier words from the forms list."""
    clfs = []
    for f in forms:
        tags = f.get("tags", [])
        if "classifier" in tags:
            w = f.get("form", "")
            if w and w not in clfs:
                clfs.append(w)
    return clfs


def _extract_alt_forms(forms: List[Dict[str, Any]]) -> List[str]:
    """Extract alternative forms from the forms list."""
    alts = []
    for f in forms:
        tags = f.get("tags", [])
        if "alternative" in tags:
            w = f.get("form", "")
            if w and w not in alts:
                alts.append(w)
    return alts


def _build_flat_senses(raw_senses: List[Dict[str, Any]]) -> List[str]:
    """Build a flat list of English glosses for pipeline compatibility.

    Prefers raw_glosses which preserve bracketed context like
    "(anatomy) eye" over the cleaned glosses "eye".

    In Kaikki format, multi-element glosses have a shared parent
    (glosses[0]) and a specific sub-sense (glosses[-1]).  We emit the
    parent once, then each sub-sense separately.
    """
    flat: List[str] = []
    seen_parents: set = set()
    for s in raw_senses:
        raw_glosses = s.get("raw_glosses", [])
        glosses = s.get("glosses", [])

        if len(glosses) > 1:
            # Multi-element: parent + sub-sense
            parent = glosses[0]
            if parent and parent not in seen_parents:
                seen_parents.add(parent)
                # Use raw_glosses[0] if available for parent
                raw_parent = raw_glosses[0] if raw_glosses else parent
                flat.append(raw_parent or parent)
            # Sub-sense: use raw_glosses[-1] if available
            sub = (raw_glosses[-1] if (raw_glosses and len(raw_glosses) > 1
                                       and raw_glosses[-1])
                   else glosses[-1])
            if sub:
                flat.append(sub)
        else:
            # Single element
            if raw_glosses and raw_glosses[0]:
                flat.append(raw_glosses[0])
            elif glosses:
                flat.append(glosses[0])
    return flat


def _build_senses_full(raw_senses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build structured sense data preserving all Kaikki fields.

    In Kaikki format, multi-element glosses have a shared parent
    (glosses[0]) and a specific sub-sense (glosses[-1]).  We emit the
    parent once, then each sub-sense with its raw_glosses context.
    """
    out: List[Dict[str, Any]] = []
    seen_parents: set = set()
    for s in raw_senses:
        raw_glosses = s.get("raw_glosses", [])
        glosses = s.get("glosses", [])

        if len(glosses) > 1:
            # Multi-element: emit parent once, then sub-sense
            parent = glosses[0]
            if parent and parent not in seen_parents:
                seen_parents.add(parent)
                raw_parent = raw_glosses[0] if raw_glosses else parent
                out.append({"glosses": [raw_parent or parent]})
            # Sub-sense uses raw_glosses[-1] for context
            sub_raw = (raw_glosses[-1]
                       if (raw_glosses and len(raw_glosses) > 1
                           and raw_glosses[-1])
                       else glosses[-1])
            if sub_raw:
                use_glosses = [sub_raw]
                used_raw = bool(raw_glosses and len(raw_glosses) > 1)
            else:
                continue
        else:
            # Single element
            used_raw = bool(raw_glosses and raw_glosses[0])
            use_glosses = raw_glosses if used_raw else glosses
            if not use_glosses:
                if s.get("form_of"):
                    use_glosses = [f"form of {s['form_of'][0].get('word', '')}"]
                elif s.get("alt_of"):
                    use_glosses = [f"alternative form of {s['alt_of'][0].get('word', '')}"]
                else:
                    continue

        sense: Dict[str, Any] = {
            "glosses": use_glosses,
        }
        is_relation_sense = bool(s.get("form_of") or s.get("alt_of"))
        # Tags (regional, register, etc.)
        # When raw_glosses is used, tags are already embedded in the
        # gloss text as bracketed annotations — skip them to avoid
        # doubling like "(colloquial) (colloquial) ...".
        # Also filter out structural metadata tags that aren't useful
        # for display (alt-of, form-of, etc.) — the gloss text already
        # describes these relationships.
        if not used_raw:
            tags = s.get("tags", [])
            raw_tags = s.get("raw_tags", [])
            all_tags: List[str] = []
            seen_tags: set = set()
            for t in (tags + raw_tags):
                txt = str(t or "").strip()
                if not txt:
                    continue
                norm = txt.lower()
                if norm in _HIDDEN_TAGS:
                    continue
                # Structural relation senses already encode relation in the
                # gloss itself ("alternative form of ...", "form of ...").
                if is_relation_sense and norm in {"alternative"}:
                    continue
                if norm in seen_tags:
                    continue
                seen_tags.add(norm)
                all_tags.append(txt)
            if all_tags:
                sense["tags"] = all_tags

            # Qualifier
            if s.get("qualifier") and not is_relation_sense:
                sense["qualifier"] = s["qualifier"]

        # Synonyms, antonyms, related
        for rel_key in ("synonyms", "antonyms", "related",
                        "hypernyms", "hyponyms", "coordinate_terms",
                        "derived", "meronyms", "holonyms"):
            rel = s.get(rel_key)
            if rel:
                sense[rel_key] = rel

        # Topics / categories for context
        topics = s.get("topics", [])
        if topics:
            sense["topics"] = topics

        out.append(sense)
    return out


# ---------------------------------------------------------------------------
# XPOS -> Kaikki POS mapping for entry-level filtering
# ---------------------------------------------------------------------------
# Maps Vietnamese XPOS tags to the set of Kaikki dictionary ``pos_raw``
# values that are semantically compatible.
#
# POS tags deliberately EXCLUDED from all XPOS buckets (always relegated
# to "Other definitions" when a matching entry exists):
#   character   â€” single-letter / HÃ¡n tá»± glyph descriptions
#   romanization â€” HÃ¡n-Viá»‡t reading cross-references
#   proverb     â€” fixed multi-word proverbs (tá»¥c ngá»¯)
#   phrase      â€” fixed multi-word phrases / idioms
#   punct       â€” punctuation marks
#   symbol      â€” typographic symbols
#
# These are excluded from XPOS matching but always shown â€” they bypass
# the filter entirely and remain in the primary bucket.

_XPOS_TO_KAIKKI_POS: Dict[str, List[str]] = {
    "N":  ["noun"],
    "Np": ["name"],
    "Nc": ["classifier"],
    "Nu": ["classifier", "noun"],
    "Nb": ["noun"],
    "Ny": ["name", "noun"],
    "V":  ["verb"],
    "A":  ["adj"],
    "P":  ["pron"],
    "R":  ["adv"],
    "L":  ["det"],
    "M":  ["num"],
    "E":  ["prep"],
    "C":  ["conj"],
    "CC": ["conj"],
    "I":  ["intj"],
    "T":  ["particle"],
    "S":  ["affix", "prefix", "suffix", "combining_form"],
    "Y":  ["name", "noun"],
    "CH": ["punct", "symbol"],
    "X":  [],
    "_":  [],
}

_ALL_XPOS_TAGS: frozenset = frozenset({
    "N", "Np", "Nc", "Nu", "Nb", "Ny",
    "V", "A", "P", "R", "L", "M", "E", "C", "CC",
    "I", "T", "S", "Y", "CH", "X", "_",
})


def _split_xpos_tags(raw_xpos: str) -> List[str]:
    """Split composite XPOS strings like ``N+T`` into individual tags."""
    text = str(raw_xpos or "").strip()
    if not text:
        return []
    if "+" not in text:
        return [text]
    parts = [p.strip() for p in text.split("+")]
    return [p for p in parts if p]

# Flat set of all Kaikki POS values that participate in filtering.
# Entries whose pos_raw is NOT in this set are always filter-exempt
# (shown in primary when no other entries match, otherwise in "other").
_FILTERABLE_POS: set = set()
for _pos_list in _XPOS_TO_KAIKKI_POS.values():
    _FILTERABLE_POS.update(_pos_list)

# POS values that are always filter-exempt: they bypass XPOS gating and
# always remain in the primary bucket, never filtered out.
_FILTER_EXEMPT_POS: frozenset = frozenset({
    "proverb", "phrase",
    "punct", "symbol",
})

# POS values that should never be promoted to primary when alternatives exist.
_ALWAYS_FILTERED_POS: frozenset = frozenset({
    "character",
    "romanization",
})


def _report_pos_filter_coverage(seen_pos_raw: set) -> None:
    """Emit startup diagnostics for XPOS/POS filter coverage."""
    mapping_xpos = set(_XPOS_TO_KAIKKI_POS.keys())
    missing_xpos = sorted(_ALL_XPOS_TAGS - mapping_xpos)
    extra_xpos = sorted(mapping_xpos - _ALL_XPOS_TAGS)
    if missing_xpos:
        print(f"[WARN] Vietnamese POS filter missing XPOS tags: {', '.join(missing_xpos)}")
    if extra_xpos:
        print(f"[WARN] Vietnamese POS filter has unknown XPOS tags: {', '.join(extra_xpos)}")
    if not missing_xpos and not extra_xpos:
        print(f"[INFO] Vietnamese POS filter covers all {len(_ALL_XPOS_TAGS)} configured VI XPOS tags.")

    covered_pos = set(_FILTERABLE_POS) | set(_FILTER_EXEMPT_POS) | set(_ALWAYS_FILTERED_POS)
    observed_pos = {str(p).strip() for p in seen_pos_raw if str(p).strip()}
    missing_pos = sorted(p for p in observed_pos if p not in covered_pos)
    if missing_pos:
        print(f"[WARN] Vietnamese POS filter missing dictionary POS tags: {', '.join(missing_pos)}")
    else:
        print(f"[INFO] Vietnamese POS filter covers all observed dictionary POS tags ({len(observed_pos)}).")


class VietnameseDict:
    """In-memory Vietnamese dictionary built from Kaikki JSONL."""

    def __init__(self, path):
        path = Path(path)
        self._by_word: Dict[str, List[Dict[str, Any]]] = {}
        self._max_word_len = 1
        self._load(path)

    def _load(self, path: Path) -> None:
        if not path.exists():
            print(f"[WARN] Vietnamese dictionary file not found: {path}")
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

                entry = self._parse_entry(raw)
                if not entry:
                    skipped += 1
                    continue

                word = entry["headword"]
                # Index case-insensitively so capitalization in running text
                # does not affect dictionary retrieval.
                fold_key = word.casefold()
                self._by_word.setdefault(fold_key, []).append(entry)
                observed_pos_raw.add(str(entry.get("pos_raw", "")).strip())
                if len(word) > self._max_word_len:
                    self._max_word_len = len(word)
                total += 1

        print(f"[INFO] Vietnamese dictionary loaded: {total:,} entries, "
              f"max word length {self._max_word_len}"
              + (f", {skipped} skipped" if skipped else ""))
        _report_pos_filter_coverage(observed_pos_raw)

    @staticmethod
    def _parse_entry(raw: dict) -> Optional[Dict[str, Any]]:
        """Parse a single Kaikki JSONL entry into the internal format."""
        word = raw.get("word", "").strip()
        if not word:
            return None

        pos_raw = raw.get("pos", "")
        pos = _normalize_pos(pos_raw)
        raw_senses = raw.get("senses", [])
        flat_senses = _build_flat_senses(raw_senses)
        senses_full = _build_senses_full(raw_senses)

        # Skip entries with no usable definitions
        if not flat_senses and not senses_full:
            return None

        sounds = raw.get("sounds", [])
        ipa = _extract_ipa(sounds)
        forms = raw.get("forms", [])
        han_tu = _extract_han_tu(forms)
        classifiers = _extract_classifiers(forms)
        alt_forms = _extract_alt_forms(forms)
        etymology = raw.get("etymology_text", "")
        etymology_number = raw.get("etymology_number", 0)

        # Collect all IPA variants for g2p
        ipa_variants: List[Dict[str, str]] = []
        for s in sounds:
            s_ipa = s.get("ipa", "")
            if not s_ipa:
                continue
            tags = s.get("tags", [])
            note = s.get("note", "")
            label = ", ".join(tags) if tags else note
            ipa_variants.append({"ipa": s_ipa, "label": label})

        # Audio URLs
        audio_urls: List[Dict[str, str]] = []
        for s in sounds:
            mp3 = s.get("mp3_url", "")
            ogg = s.get("ogg_url", "")
            if mp3 or ogg:
                audio_urls.append({
                    "mp3": mp3,
                    "ogg": ogg,
                })

        # Top-level synonyms, antonyms, derived, related
        synonyms = raw.get("synonyms", [])
        antonyms = raw.get("antonyms", [])
        derived = raw.get("derived", [])
        related = raw.get("related", [])

        return {
            # --- pipeline-required fields ---
            "headword": word,
            "pos": pos,
            "pos_raw": pos_raw,
            "senses": flat_senses,
            "reading": ipa,
            # --- rich fields ---
            "senses_full": senses_full,
            "han_tu": han_tu,
            "classifiers": classifiers,
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
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, word: str) -> Optional[Dict[str, Any]]:
        """Return the first entry for *word*, or None."""
        entries = self._by_word.get(word.casefold())
        if not entries:
            return None
        return entries[0]

    def lookup_all(self, word: str) -> List[Dict[str, Any]]:
        """Return all entries for *word* (case-insensitive)."""
        return list(self._by_word.get(word.casefold(), []))

    def filter_entries_by_xpos(
        self,
        entries: List[Dict[str, Any]],
        xpos: str,
    ) -> "tuple[List[Dict[str, Any]], List[Dict[str, Any]]]":
        """Filter entries by XPOS tag, returning (primary, other).

        Entries are split at the entry level (within each etymology
        group): matching/exempt entries stay in ``primary`` and
        non-matching entries go to ``other``.  This lets the UI show
        irrelevant senses under per-entry "more" while keeping the
        main view focused.

        Single-entry words are never filtered.
        If no entries match, everything is returned as primary.
        """
        if not entries:
            return [], []
        if len(entries) <= 1:
            return list(entries), []

        xpos_tags = _split_xpos_tags(str(xpos or ""))
        if not xpos_tags:
            return list(entries), []

        allowed: set = set()
        recognized = False
        for tag in xpos_tags:
            mapped = _XPOS_TO_KAIKKI_POS.get(tag)
            if mapped is None:
                continue
            recognized = True
            allowed.update(mapped)
        # Unknown / non-semantic XPOS like X or _ -> no filtering.
        if not recognized or not allowed:
            return list(entries), []

        # Group entries by etymology key
        from collections import OrderedDict
        etym_groups: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
        for entry in entries:
            ekey = _etym_key(entry)
            etym_groups.setdefault(ekey, []).append(entry)

        primary: List[Dict[str, Any]] = []
        other: List[Dict[str, Any]] = []

        for _ekey, group in etym_groups.items():
            group_primary: List[Dict[str, Any]] = []
            group_other: List[Dict[str, Any]] = []
            has_allowed_match = False

            for entry in group:
                pos_raw = entry.get("pos_raw", "")
                if pos_raw in _ALWAYS_FILTERED_POS:
                    group_other.append(entry)
                    continue
                is_exempt = pos_raw in _FILTER_EXEMPT_POS
                is_allowed = pos_raw in allowed

                if is_allowed:
                    has_allowed_match = True
                    group_primary.append(entry)
                elif is_exempt:
                    # Exempt POS always remain visible in primary.
                    group_primary.append(entry)
                else:
                    group_other.append(entry)

            if has_allowed_match:
                primary.extend(group_primary)
                other.extend(group_other)
            else:
                # No semantic match for this etymology group:
                # keep only exempt entries in primary, and move the rest.
                if group_primary:
                    primary.extend(group_primary)
                    other.extend(group_other)
                else:
                    other.extend(group)

        if not primary:
            non_always_filtered = [e for e in entries if e.get("pos_raw", "") not in _ALWAYS_FILTERED_POS]
            always_filtered = [e for e in entries if e.get("pos_raw", "") in _ALWAYS_FILTERED_POS]
            if non_always_filtered and always_filtered:
                return non_always_filtered, always_filtered
            return list(entries), []

        return primary, other

    def debug_filter_entries_by_xpos(
        self,
        entries: List[Dict[str, Any]],
        xpos: str,
    ) -> Dict[str, Any]:
        """Return a structured explanation of XPOS entry filtering.

        Used by the shared /debug endpoint to show why entries were kept
        in the primary set vs moved to filtered/other definitions.
        """
        raw_entries = list(entries or [])
        primary, other = self.filter_entries_by_xpos(raw_entries, xpos)
        primary_ids = {id(e) for e in primary}
        other_ids = {id(e) for e in other}

        xpos_tags = _split_xpos_tags(str(xpos or ""))
        recognized_tags: List[str] = []
        allowed: set = set()
        for tag in xpos_tags:
            mapped = _XPOS_TO_KAIKKI_POS.get(tag)
            if mapped is None:
                continue
            recognized_tags.append(tag)
            allowed.update(mapped)

        single_entry_passthrough = len(raw_entries) <= 1
        no_xpos_passthrough = not xpos_tags
        unrecognized_passthrough = bool(xpos_tags) and not recognized_tags
        nonsemantic_passthrough = bool(recognized_tags) and not allowed
        filter_active = (
            not single_entry_passthrough
            and not no_xpos_passthrough
            and not unrecognized_passthrough
            and not nonsemantic_passthrough
        )

        rows: List[Dict[str, Any]] = []
        for idx, entry in enumerate(raw_entries):
            pos_raw = str(entry.get("pos_raw", "") or "")
            pos_label = str(entry.get("pos", "") or "")
            status = "shown"
            if id(entry) in other_ids:
                status = "filtered_out"
            elif id(entry) in primary_ids:
                status = "shown"

            if single_entry_passthrough:
                reason = "single_entry_passthrough"
            elif no_xpos_passthrough:
                reason = "no_xpos_passthrough"
            elif unrecognized_passthrough:
                reason = "unrecognized_xpos_passthrough"
            elif nonsemantic_passthrough:
                reason = "nonsemantic_xpos_passthrough"
            elif pos_raw in _ALWAYS_FILTERED_POS:
                reason = "always_filtered_pos"
            elif pos_raw in allowed:
                reason = "xpos_pos_match"
            elif pos_raw in _FILTER_EXEMPT_POS:
                reason = "filter_exempt_pos"
            else:
                reason = "xpos_pos_mismatch"

            senses_full = list(entry.get("senses_full", []) or [])
            senses_flat = list(entry.get("senses", []) or [])
            preview: List[str] = []
            for sense in senses_full:
                if not isinstance(sense, dict):
                    continue
                glosses = sense.get("glosses", [])
                if not isinstance(glosses, list):
                    continue
                gloss = "; ".join(str(g or "").strip() for g in glosses if str(g or "").strip())
                if gloss:
                    preview.append(gloss)
                if len(preview) >= 2:
                    break
            if not preview:
                for gloss in senses_flat:
                    text = str(gloss or "").strip()
                    if not text:
                        continue
                    preview.append(text)
                    if len(preview) >= 2:
                        break

            rows.append({
                "index": idx,
                "label": str(
                    entry.get("headword", "")
                    or entry.get("word", "")
                    or entry.get("head", "")
                    or ""
                ),
                "headword": str(entry.get("headword", "") or ""),
                "han_tu": str(entry.get("han_tu", "") or ""),
                "pos": pos_label,
                "pos_raw": pos_raw,
                "etym_key": _etym_key(entry),
                "sense_count": len(senses_full) if senses_full else len(senses_flat),
                "sense_preview": preview,
                "filter_status": status,
                "reason": reason,
            })

        return {
            "mode": "xpos",
            "xpos": str(xpos or ""),
            "xpos_tags": xpos_tags,
            "recognized_xpos_tags": recognized_tags,
            "allowed_pos_raw": sorted(allowed),
            "filter_active": bool(filter_active),
            "entry_count": len(raw_entries),
            "shown_count": len(primary),
            "filtered_count": len(other),
            "entries": rows,
        }

    # Backward-compatible alias (legacy call sites).
    def filter_entries_by_upos(
        self,
        entries: List[Dict[str, Any]],
        upos: str,
    ) -> "tuple[List[Dict[str, Any]], List[Dict[str, Any]]]":
        return self.filter_entries_by_xpos(entries, upos)

    def fill_token(
        self,
        word: str,
        allow_exact: bool = True,
        exclude_whole: bool = False,
    ) -> Dict[str, Any]:
        """Build a fill structure for the frontend.

        Vietnamese is a whitespace-delimited language so fill_token
        primarily does exact match.  Falls back to greedy forward
        maximum matching for compound words that trankit may have
        merged or for subsegment decomposition.
        """
        # Try whole-word exact match
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

        # Greedy forward maximum matching (space-aware for Vietnamese)
        return self._greedy_fill(word, exclude_whole=exclude_whole)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _entry_to_fill(self, entry: Dict[str, Any], text: str) -> Dict[str, Any]:
        """Convert an entry dict to a fill piece."""
        return {
            "text": text,
            "head": entry["headword"],
            "roman": entry.get("reading", ""),
            "senses": entry["senses"],
            "pos": entry["pos"],
            "source": "KAIKKI",
            # Rich fields
            "han_tu": entry.get("han_tu", ""),
            "etymology": entry.get("etymology", ""),
            "senses_full": entry.get("senses_full", []),
            "ipa_variants": entry.get("ipa_variants", []),
        }

    def _greedy_fill(
        self,
        word: str,
        exclude_whole: bool = False,
    ) -> Dict[str, Any]:
        """Greedy forward maximum matching.

        For Vietnamese, try space-delimited multi-word chunks first
        (e.g. "ThÃ nh phá»‘" as one unit), then fall back to single tokens.
        """
        fills: List[Dict[str, Any]] = []
        has_known = False
        has_unknown = False

        # Split into space-separated tokens, then try combining
        # adjacent tokens for multi-word lookups
        tokens = word.split()
        if not tokens:
            return {"mode": "greedy", "fills": [], "has_known": False, "has_unknown": False}

        i = 0
        while i < len(tokens):
            best_len = 0
            best_entries = None

            # Try combining tokens from longest to single across full
            # whitespace-delimited span.
            max_try = (len(tokens) - i)
            for length in range(max_try, 0, -1):
                if exclude_whole and i == 0 and length == len(tokens):
                    continue
                candidate = " ".join(tokens[i:i + length])
                entries = self.lookup_all(candidate)
                if entries:
                    best_len = length
                    best_entries = entries
                    break

            if best_entries is not None:
                text = " ".join(tokens[i:i + best_len])
                fill = self._entry_to_fill(best_entries[0], text)
                fill["entries"] = best_entries
                fills.append(fill)
                has_known = True
                i += best_len
            else:
                # Single token not found
                tok = tokens[i]
                fills.append({
                    "text": tok,
                    "head": tok,
                    "roman": "",
                    "senses": [],
                    "pos": "",
                    "source": "UNKNOWN",
                })
                has_unknown = True
                i += 1

        return {
            "mode": "greedy",
            "fills": fills,
            "has_known": has_known,
            "has_unknown": has_unknown,
        }
