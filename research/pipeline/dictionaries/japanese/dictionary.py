"""
JMdict dictionary parser and lookup for Japanese.

Parses the standard JMdict XML format (with inline DTD entity definitions)
and provides word-level lookup by kanji or kana reading.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class JapaneseDict:
    """
    In-memory JMdict dictionary keyed by kanji forms and kana readings.
    """

    def __init__(self, path: str | Path):
        self._by_kanji: Dict[str, List[Dict[str, Any]]] = {}
        self._by_reading: Dict[str, List[Dict[str, Any]]] = {}
        self._all_pos_tags: List[str] = []
        self._upos_to_pos_tags: Dict[str, List[str]] = {}
        self._load(Path(path))

    def _load(self, path: Path) -> None:
        if not path.exists():
            print(f"[WARN] JMdict file not found: {path}")
            return

        # JMdict uses XML entity references for POS tags etc.
        # Python's ET parser can't resolve them from inline DTD,
        # so we extract the entity map and pre-substitute before parsing.
        print(f"[INFO] Parsing JMdict from {path} (this may take a moment)...")

        entity_map = _extract_entities(path)
        xml_text = _read_and_resolve_entities(path, entity_map)

        count = 0
        root = ET.fromstring(xml_text)
        pos_inventory_seen: Set[str] = set()
        pos_inventory: List[str] = []

        for entry_el in root.iter("entry"):
            # Kanji forms with per-form info (ke_inf)
            kanji_forms = []
            kanji_info: Dict[str, List[str]] = {}
            for k_ele in entry_el.iter("k_ele"):
                keb = k_ele.find("keb")
                if keb is not None and keb.text:
                    kanji_forms.append(keb.text)
                    ke_infs = [ki.text for ki in k_ele.iter("ke_inf") if ki.text]
                    if ke_infs:
                        kanji_info[keb.text] = ke_infs

            # Reading forms with per-form info (re_inf) and restrictions (re_restr)
            readings = []
            reading_info: Dict[str, List[str]] = {}
            reading_restr: Dict[str, List[str]] = {}
            reading_nokanji: Dict[str, bool] = {}
            for r_ele in entry_el.iter("r_ele"):
                reb = r_ele.find("reb")
                if reb is not None and reb.text:
                    readings.append(reb.text)
                    re_infs = [ri.text for ri in r_ele.iter("re_inf") if ri.text]
                    if re_infs:
                        reading_info[reb.text] = re_infs
                    re_restrs = [rr.text for rr in r_ele.iter("re_restr") if rr.text]
                    if re_restrs:
                        reading_restr[reb.text] = re_restrs
                    if r_ele.find("re_nokanji") is not None:
                        reading_nokanji[reb.text] = True
            if not readings:
                continue

            # Priority / commonness tags from k_ele and r_ele
            pri_tags: List[str] = []
            # Per-form priority tags: { "擦る": ["ichi1","news2","nf36"], ... }
            kanji_pri: Dict[str, List[str]] = {}
            reading_pri: Dict[str, List[str]] = {}
            for k_ele in entry_el.iter("k_ele"):
                keb_el = k_ele.find("keb")
                keb_text = keb_el.text if keb_el is not None else None
                for kp in k_ele.iter("ke_pri"):
                    if kp.text and kp.text not in pri_tags:
                        pri_tags.append(kp.text)
                    if kp.text and keb_text:
                        kanji_pri.setdefault(keb_text, []).append(kp.text)
            for r_ele in entry_el.iter("r_ele"):
                reb_el = r_ele.find("reb")
                reb_text = reb_el.text if reb_el is not None else None
                for rp in r_ele.iter("re_pri"):
                    if rp.text and rp.text not in pri_tags:
                        pri_tags.append(rp.text)
                    if rp.text and reb_text:
                        reading_pri.setdefault(reb_text, []).append(rp.text)

            # Senses: collect structured per-sense data
            structured_senses: List[Dict[str, Any]] = []
            flat_glosses: List[str] = []
            all_pos_tags: List[str] = []
            # JMdict convention: POS carries forward from earlier senses
            # if a later sense omits it.
            inherited_pos: List[str] = []

            for sense_el in entry_el.iter("sense"):
                glosses = [g.text for g in sense_el.iter("gloss") if g.text]
                if not glosses:
                    continue

                # POS tags for this sense (if present, they replace inherited)
                sense_pos = [p.text for p in sense_el.iter("pos") if p.text]
                if sense_pos:
                    inherited_pos = list(sense_pos)
                for p in inherited_pos:
                    if p not in all_pos_tags:
                        all_pos_tags.append(p)

                # Misc tags (e.g. "usually written using kana alone")
                misc = [m.text for m in sense_el.iter("misc") if m.text]
                # Sense info / notes
                s_inf = "; ".join(
                    si.text for si in sense_el.iter("s_inf") if si.text
                )
                # Field of application
                field = [f.text for f in sense_el.iter("field") if f.text]
                # Kanji/reading restrictions for this sense
                stagk = [sk.text for sk in sense_el.iter("stagk") if sk.text]
                stagr = [sr.text for sr in sense_el.iter("stagr") if sr.text]
                # Cross-references and antonyms
                xref = [x.text for x in sense_el.iter("xref") if x.text]
                ant = [a.text for a in sense_el.iter("ant") if a.text]
                # Dialect
                dial = [d.text for d in sense_el.iter("dial") if d.text]
                # Loan source language
                lsource = []
                for ls in sense_el.iter("lsource"):
                    ls_text = ls.text or ""
                    ls_lang = ls.get("{http://www.w3.org/XML/1998/namespace}lang", "eng")
                    if ls_text:
                        lsource.append(f"{ls_text} ({ls_lang})")

                structured_senses.append({
                    "glosses": glosses,
                    "pos": list(inherited_pos),
                    "misc": misc,
                    "s_inf": s_inf,
                    "field": field,
                    "stagk": stagk,
                    "stagr": stagr,
                    "xref": xref,
                    "ant": ant,
                    "dial": dial,
                    "lsource": lsource,
                })
                flat_glosses.extend(glosses)

            if not flat_glosses:
                continue

            entry = {
                "kanji": kanji_forms,
                "kanji_info": kanji_info,
                "reading": readings[0],
                "readings": readings,
                "reading_info": reading_info,
                "reading_restr": reading_restr,
                "reading_nokanji": reading_nokanji,
                "senses": structured_senses,
                "flat_glosses": flat_glosses,
                "pos": all_pos_tags[0] if all_pos_tags else "",
                "all_pos": all_pos_tags,
                "pri": pri_tags,
                "pri_score": _compute_pri_score(pri_tags),
                "kanji_pri": kanji_pri,
                "reading_pri": reading_pri,
                "sense_count": len(structured_senses),
            }

            for p in all_pos_tags:
                if p and p not in pos_inventory_seen:
                    pos_inventory_seen.add(p)
                    pos_inventory.append(p)

            # Index by kanji forms
            for kf in kanji_forms:
                if kf not in self._by_kanji:
                    self._by_kanji[kf] = []
                self._by_kanji[kf].append(entry)

            # Index by reading forms
            for rf in readings:
                if rf not in self._by_reading:
                    self._by_reading[rf] = []
                self._by_reading[rf].append(entry)

            count += 1

        print(f"[INFO] Loaded {count} JMdict entries "
              f"({len(self._by_kanji)} kanji keys, {len(self._by_reading)} reading keys)")
        self._all_pos_tags = pos_inventory
        self._upos_to_pos_tags = _build_upos_to_pos_map(self._all_pos_tags)

    def get_all_pos_tags(self) -> List[str]:
        """Return all unique JMdict POS tags discovered in this dictionary."""
        return list(self._all_pos_tags)

    def get_pos_tags_for_upos(self, upos: str) -> List[str]:
        """Return JMdict POS tags that map to a given UD UPOS tag."""
        key = str(upos or "").strip().upper()
        if not key:
            return []
        return list(self._upos_to_pos_tags.get(key, []))

    def filter_entries_by_upos(
        self,
        entries: List[Dict[str, Any]],
        upos: str,
    ) -> tuple:
        """Filter at the *entry* level by UPOS, returning (primary, other).

        An entry passes the filter if its ``all_pos`` (aggregated across all
        senses) overlaps the allowed JMdict tags for the given UPOS.  When an
        entry passes, ALL of its senses are kept — no sense-level splitting.

        Single-entry words are never filtered (nothing to choose between).

        If no entries match, everything is returned as primary so the user
        always sees definitions.

        Returns ``(primary_entries, other_entries)``.
        """
        if not entries:
            return [], []
        # Single entry — nothing to filter between, skip.
        if len(entries) <= 1:
            return list(entries), []

        key = str(upos or "").strip().upper()
        if not key:
            return list(entries), []

        allowed = set(self.get_pos_tags_for_upos(key))
        if not allowed:
            return list(entries), []

        primary: List[Dict[str, Any]] = []
        other: List[Dict[str, Any]] = []

        for entry in entries:
            entry_pos = entry.get("all_pos", []) or []
            if any(p in allowed for p in entry_pos):
                primary.append(entry)
            else:
                other.append(entry)

        if not primary:
            # Nothing matched — show everything as primary.
            return list(entries), []

        return primary, other

    def lookup(self, word: str) -> Optional[Dict[str, Any]]:
        """Look up a word. Returns the highest-priority matching entry or None.
        Tries kanji index first, then reading index.  Uses form-aware scoring
        so that priority tags scoped to the matched form are preferred."""
        entries = self._by_kanji.get(word)
        if entries:
            return max(entries, key=lambda e: _form_sort_key(e, word))
        entries = self._by_reading.get(word)
        if entries:
            return max(entries, key=lambda e: _form_sort_key(e, word))
        return None

    def lookup_all(self, word: str) -> List[Dict[str, Any]]:
        """Return all entries for a word (kanji + reading, deduped),
        sorted by matched-form frequency (highest score first)."""
        kanji_entries = list(self._by_kanji.get(word, []))
        reading_entries = list(self._by_reading.get(word, []))

        if kanji_entries and reading_entries:
            # Dedupe by identity (same dict object)
            seen = set(id(e) for e in kanji_entries)
            for e in reading_entries:
                if id(e) not in seen:
                    kanji_entries.append(e)
                    seen.add(id(e))
            combined = kanji_entries
        else:
            combined = kanji_entries or reading_entries

        # Sort by form-aware score descending (most common first)
        if len(combined) > 1:
            combined.sort(key=lambda e: _form_sort_key(e, word), reverse=True)
        return combined

    def fill_token(
        self,
        word: str,
        allow_exact: bool = True,
        exclude_whole: bool = False,
    ) -> Dict[str, Any]:
        """
        Build a dict_fill structure for a token.

        If exact match found and allowed, returns that.
        Otherwise falls back to greedy forward longest matching.
        """
        entry = self.lookup(word)
        if allow_exact and not exclude_whole and entry:
            return {
                "mode": "exact",
                "fills": [{
                    "text": word,
                    "head": word,
                    "roman": entry["reading"],
                    "senses": entry.get("flat_glosses") or entry.get("senses", []),
                    "source": "JMDICT",
                }],
                "has_known": True,
                "has_unknown": False,
            }

        # Greedy forward longest matching
        return self._greedy_fill(word, exclude_whole=exclude_whole)

    def _greedy_fill(
        self,
        word: str,
        exclude_whole: bool = False,
    ) -> Dict[str, Any]:
        """Greedy forward longest matching, like Chinese fill_token."""
        fills = []
        has_known = False
        has_unknown = False
        i = 0

        while i < len(word):
            matched = False
            for end in range(len(word), i, -1):
                substr = word[i:end]
                # Don't return the whole word as a single piece in subword mode
                if (exclude_whole and len(word) > 1
                        and i == 0 and end == len(word) and substr == word):
                    continue
                sub_entry = self.lookup(substr)
                if not sub_entry:
                    continue
                fills.append({
                    "text": substr,
                    "head": substr,
                    "roman": sub_entry["reading"],
                    "senses": sub_entry.get("flat_glosses") or sub_entry.get("senses", []),
                    "source": "JMDICT",
                })
                has_known = True
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
                    "source": "UNKNOWN",
                })
                i += 1

        return {
            "mode": "greedy",
            "fills": fills,
            "has_known": has_known,
            "has_unknown": has_unknown,
        }


# ---------------------------------------------------------------------------
# Priority / commonness scoring
# ---------------------------------------------------------------------------

_NF_RE = re.compile(r"^nf(\d+)$")

_PRI_TAG_PERCENT = {
    "ichi1": 80.0,
    "news1": 70.0,
    "ichi2": 50.0,
    "gai1": 50.0,
    "news2": 40.0,
    "gai2": 25.0,
}


def _compute_spec_priority(pri_tags: List[str]) -> int:
    """Return spec rank for ordering: spec1 > spec2 > non-spec."""
    tags = set(pri_tags or [])
    if "spec1" in tags:
        return 2
    if "spec2" in tags:
        return 1
    return 0


def _extract_nf_band(pri_tags: List[str]) -> Optional[int]:
    """Return the best (lowest) nf band if present, else None."""
    best: Optional[int] = None
    for raw in list(pri_tags or []):
        tag = str(raw or "").strip()
        if not tag:
            continue
        m = _NF_RE.match(tag)
        if not m:
            continue
        try:
            band = int(m.group(1))
        except Exception:
            continue
        if best is None or band < best:
            best = band
    return best


def _nf_percent(band: int) -> float:
    """Map nf01..nf48 to percentage via ((49-XX)/48)*100."""
    b = max(1, min(48, int(band)))
    pct = ((49 - b) / 48.0) * 100.0
    if pct < 0.0:
        return 0.0
    if pct > 100.0:
        return 100.0
    return pct


def _compute_pri_score(pri_tags: List[str]) -> float:
    """Compute frequency score (0..100) from one form's JMdict priority tags.

    Rules:
      - If any nfXX tag exists, score uses nf only.
      - Else use the highest single non-nf tag bucket.
      - Missing or unknown tags score 0.
    """
    tags = [str(t or "").strip() for t in list(pri_tags or []) if str(t or "").strip()]
    nf_band = _extract_nf_band(tags)
    if nf_band is not None:
        return _nf_percent(nf_band)

    best = 0.0
    for tag in tags:
        pct = _PRI_TAG_PERCENT.get(tag)
        if pct is not None and pct > best:
            best = pct
    if best < 0.0:
        return 0.0
    if best > 100.0:
        return 100.0
    return best


def _get_form_priority_tags(entry: Dict[str, Any], lookup_word: str) -> List[str]:
    """Return pri tags only for the specific matched surface form."""
    reading_pri = entry.get("reading_pri") or {}
    kanji_pri = entry.get("kanji_pri") or {}
    raw = reading_pri.get(lookup_word) or kanji_pri.get(lookup_word) or []
    return [str(t or "").strip() for t in list(raw or []) if str(t or "").strip()]


def _form_sort_key(entry: Dict[str, Any], lookup_word: str):
    """Sort by spec priority, then form-only frequency score, then sense count."""
    form_tags = _get_form_priority_tags(entry, lookup_word)
    spec_rank = _compute_spec_priority(form_tags)
    form_score = _compute_pri_score(form_tags)
    sense_count = int(entry.get("sense_count", 0))
    return (spec_rank, form_score, sense_count)


def _compute_form_pri_score(entry: Dict[str, Any], lookup_word: str) -> float:
    """Compute score for the exact matched form only (no entry fallback)."""
    return _compute_pri_score(_get_form_priority_tags(entry, lookup_word))

# ---------------------------------------------------------------------------
# UPOS -> JMdict POS mapping (built from mined dictionary POS inventory)
# ---------------------------------------------------------------------------

_UPOS_ORDER = (
    "ADJ", "ADP", "ADV", "AUX", "CCONJ", "DET", "INTJ",
    "NOUN", "NUM", "PART", "PRON", "PROPN", "PUNCT",
    "SCONJ", "SYM", "VERB", "X",
)


def _normalize_pos_text(pos_tag: str) -> str:
    return " ".join(str(pos_tag or "").strip().lower().split())


def _classify_pos_tag_to_upos(pos_tag: str) -> Set[str]:
    """Map a JMdict POS label → the set of UPOS tags whose bucket it belongs to.

    The mapping is designed *inclusively*: for each UPOS that Trankit may
    assign to a token, we want to keep any JMdict sense whose POS could
    plausibly be that UPOS.  A single JMdict tag can belong to multiple
    UPOS buckets (e.g. na-adjectives are both ADJ and NOUN; particles
    are both PART and ADP).
    """
    t = _normalize_pos_text(pos_tag)
    out: Set[str] = set()
    if not t:
        return {"X"}

    # ---- Proper nouns ----
    if "proper noun" in t:
        out.add("PROPN")
        out.add("NOUN")          # proper nouns are still nouns

    # ---- Pronouns ----
    if "pronoun" in t:
        out.add("PRON")
        out.add("NOUN")          # Trankit sometimes tags pronouns NOUN

    # ---- Interjections ----
    if "interjection" in t:
        out.add("INTJ")

    # ---- Particles → PART *and* ADP ----
    # Trankit uses ADP for case/binding particles (は が を に で へ)
    # and PART for sentence-final / focus particles.  JMdict only has
    # "particle" so we must map it to both.
    # Guard: startswith to avoid matching "…genitive case particle 'no'"
    if t.startswith("particle"):
        out.add("PART")
        out.add("ADP")

    # ---- Conjunctions ----
    if "conjunction" in t:
        out.add("CCONJ")
        out.add("SCONJ")

    # ---- Auxiliary / copula ----
    # Broadened: suru verbs commonly function as auxiliaries (する → AUX).
    # Ichidan/Kuru can too (e.g. られる、させる、くる as auxiliaries).
    if t == "auxiliary" or "auxiliary verb" in t or "copula" in t:
        out.add("AUX")
    if "suru" in t and "verb" in t:
        out.add("AUX")
    if "auxiliary adjective" in t:
        out.add("AUX")
        out.add("ADJ")

    # ---- Adverbs ----
    if "adverb" in t:
        out.add("ADV")

    # ---- Adjectives ----
    if (
        "adjective" in t
        or "adjectival" in t
        or "keiyoushi" in t
        or "keiyodoshi" in t
        or "'taru'" in t
        or "'shiku'" in t
        or "'ku' adjective" in t
    ):
        out.add("ADJ")
        # na-adjectives (keiyodoshi / quasi-adjective) also function as nouns
        if ("keiyodoshi" in t or "quasi-adjective" in t
                or "adjectival noun" in t or "na-adjective" in t):
            out.add("NOUN")

    # ---- Determiners / pre-noun adjectivals ----
    if "pre-noun" in t or "prenominally" in t or "rentaishi" in t:
        out.add("DET")
        out.add("ADJ")

    # ---- Numerics / counters ----
    if "numeric" in t or "counter" in t:
        out.add("NUM")
        out.add("NOUN")

    # ---- Prefix / suffix ----
    # Prefixes and suffixes are noun-like; map to NOUN always.
    if "prefix" in t or "suffix" in t:
        out.add("NOUN")

    # ---- Nouns ----
    if "noun" in t:
        out.add("NOUN")
        # suru-nouns are verb-like (勉強する, 運動する)
        if "suru" in t:
            out.add("VERB")
        # nouns acting prenominally are adjective-like / determiner-like
        if "prenominally" in t:
            out.add("ADJ")
            out.add("DET")

    # ---- Verbs (excluding auxiliary verbs and adverbs) ----
    if "verb" in t and "auxiliary verb" not in t and "adverb" not in t:
        out.add("VERB")

    # ---- Adpositions (JMdict rarely uses these labels, particles cover it) ----
    if "adposition" in t or "preposition" in t or "postposition" in t:
        out.add("ADP")

    # ---- Symbols ----
    if "symbol" in t:
        out.add("SYM")

    # ---- Expressions / unclassified → catch-all ----
    if "expression" in t or "phrases" in t or "clauses" in t or "unclassified" in t:
        out.add("X")

    if not out:
        out.add("X")
    return out


def _build_upos_to_pos_map(all_pos_tags: List[str]) -> Dict[str, List[str]]:
    """Build UPOS → JMdict POS map from the full discovered POS tag set.

    After the initial classification pass, applies cross-mappings so that
    UPOS tags which should be supersets of others inherit those tags:
      - PROPN inherits everything in NOUN (proper nouns are nouns)
    """
    out: Dict[str, List[str]] = {k: [] for k in _UPOS_ORDER}
    for pos_tag in all_pos_tags or []:
        upos_tags = _classify_pos_tag_to_upos(pos_tag)
        for upos in _UPOS_ORDER:
            if upos in upos_tags and pos_tag not in out[upos]:
                out[upos].append(pos_tag)

    # ---- Cross-mappings ----
    # PROPN: when Trankit says PROPN the dictionary entry is almost always
    # tagged as a regular noun.  Inherit all NOUN tags so we never blank out.
    for tag in out.get("NOUN", []):
        if tag not in out["PROPN"]:
            out["PROPN"].append(tag)

    return out


# ---------------------------------------------------------------------------
# JMdict XML parsing helpers
# ---------------------------------------------------------------------------

_ENTITY_RE = re.compile(r'<!ENTITY\s+(\S+)\s+"([^"]*)">')
_ENTITY_REF_RE = re.compile(r'&([a-zA-Z0-9_.-]+);')


def _extract_entities(path: Path) -> Dict[str, str]:
    """Read the inline DTD from JMdict and extract entity definitions."""
    entities: Dict[str, str] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip() == "]>":
                break
            m = _ENTITY_RE.search(line)
            if m:
                entities[m.group(1)] = m.group(2)
    return entities


def _read_and_resolve_entities(path: Path, entity_map: Dict[str, str]) -> str:
    """Read JMdict, strip the DOCTYPE, and resolve entity references."""
    lines: List[str] = []
    past_dtd = False

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not past_dtd:
                if line.strip() == "]>":
                    past_dtd = True
                continue
            lines.append(line)

    text = "".join(lines)

    # Resolve entity references: &n; -> "noun (common) (futsuumeishi)", etc.
    def _replace(m):
        name = m.group(1)
        # Keep standard XML entities
        if name in ("amp", "lt", "gt", "quot", "apos"):
            return m.group(0)
        return entity_map.get(name, m.group(0))

    text = _ENTITY_REF_RE.sub(_replace, text)

    # Wrap in XML declaration + root if needed
    if not text.strip().startswith("<?xml"):
        text = '<?xml version="1.0" encoding="UTF-8"?>\n' + text

    return text

