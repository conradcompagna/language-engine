"""
Japanese language hooks for the generic NLP pipeline.

Provides Japanese-specific behavior: kanji/reading form attachment,
JMdict entry selection, simple kana-based g2p, and lemma fallback
for dictionary lookup.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from language_registry import LanguageHooks
from pipeline_common import prepare_fill_entries


# ---------------------------------------------------------------------------
# Japanese-specific entry selection
# ---------------------------------------------------------------------------

def _choose_japanese_entry(
    surface: str,
    entries: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Prefer entries where the surface matches a kanji form exactly."""
    if not entries:
        return None
    if not surface:
        return entries[0]

    for entry in entries:
        kanji_forms = entry.get("kanji", []) or []
        if surface in kanji_forms:
            return entry

    # Fallback: check if surface matches a reading
    for entry in entries:
        readings = entry.get("readings", []) or []
        if surface in readings:
            return entry

    return entries[0]


# ---------------------------------------------------------------------------
# Japanese form attachment (kanji / reading)
# ---------------------------------------------------------------------------

def _is_kana(text: str) -> bool:
    """Return True if the string is entirely hiragana/katakana."""
    if not text:
        return False
    for ch in text:
        cp = ord(ch)
        # Hiragana: U+3040-U+309F, Katakana: U+30A0-U+30FF,
        # Half-width katakana: U+FF65-U+FF9F, Katakana phonetic ext: U+31F0-U+31FF
        # Also allow prolonged sound mark U+30FC and iteration marks
        if not (0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF
                or 0xFF65 <= cp <= 0xFF9F or 0x31F0 <= cp <= 0x31FF):
            return False
    return True


def _attach_japanese_forms(
    target: Dict[str, Any],
    surface: str,
    entries: List[Dict[str, Any]],
) -> None:
    """Attach kanji and reading forms to a payload dict.

    When the surface token is written in kana, do NOT replace it with a kanji
    headword — keep the kana as the primary ``kanji`` (display) form and store
    all possible kanji writings from the matched entries in ``all_kanji`` so
    the frontend can list them per sense group.
    """
    chosen = _choose_japanese_entry(surface, entries)
    surface_is_kana = _is_kana(surface)

    if chosen:
        kanji_forms = chosen.get("kanji", []) or []
        reading = chosen.get("reading", "") or ""

        if surface_is_kana:
            # Surface is kana — use it directly as the display headword.
            # Don't substitute a kanji the user never wrote.
            target["kanji"] = surface
            target["reading"] = reading or surface
        else:
            # Surface has kanji — prefer the matching kanji form
            if surface in kanji_forms:
                target["kanji"] = surface
            else:
                target["kanji"] = kanji_forms[0] if kanji_forms else surface
            target["reading"] = reading or surface

        # Collect all kanji forms across all matching entries for display
        all_kanji = []
        seen = set()
        for entry in (entries or []):
            for kf in entry.get("kanji", []) or []:
                if kf not in seen:
                    seen.add(kf)
                    all_kanji.append(kf)
        target["all_kanji"] = all_kanji
    elif surface:
        target["kanji"] = surface
        target["reading"] = surface
        target["all_kanji"] = []


# ---------------------------------------------------------------------------
# Japanese g2p (kana reading from JMdict — no decomposition)
# ---------------------------------------------------------------------------

def _build_japanese_g2p(word, dictionary, fallback_roman=""):
    """Return a simple g2p payload with the kana reading from JMdict."""
    entry = dictionary.lookup(word)
    reading = ""
    if entry:
        reading = entry.get("reading", "") or ""
    if not reading:
        reading = fallback_roman or ""

    return {
        "overall_roman": reading,
        "syllables": [],
    }


# ---------------------------------------------------------------------------
# Lemma fallback for dictionary lookup
# ---------------------------------------------------------------------------

def _japanese_lemma_fallback(word, lemma, dictionary):
    """
    Full fallback chain when exact segment match fails:
      1. Exact lemma match
      2. Greedy longest match on the lemma form
      3. Greedy longest match on the surface segment

    Returns a dict with 'entries' and 'fill' keys, or None.
    """
    if not lemma or lemma == word:
        return None

    # Step 1: Try exact lemma lookup
    entries = dictionary.lookup_all(lemma)
    if entries:
        best = entries[0]
        fill = {
            "mode": "lemma",
            "fills": [{
                "text": word,
                "head": lemma,
                "roman": best.get("reading", ""),
                "senses": best.get("flat_glosses") or best.get("senses", []),
                "source": "JMDICT",
            }],
            "has_known": True,
            "has_unknown": False,
        }
        return {"entries": entries, "fill": fill}

    # Step 2: Lemma-first greedy fallback.
    # If lemma greedy finds anything, prefer it over surface greedy.
    if lemma != word:
        lemma_fill = dictionary.fill_token(lemma)
        if lemma_fill.get("has_known"):
            lemma_fill["mode"] = "lemma_greedy"
            return {"entries": [], "fill": lemma_fill}

    # Step 3: Fallback to surface greedy.
    surface_fill = dictionary.fill_token(word)
    if surface_fill.get("has_known"):
        return {"entries": [], "fill": surface_fill}

    return None


# ---------------------------------------------------------------------------
# POS-aware entry filtering for hover definitions
# ---------------------------------------------------------------------------

def _filter_japanese_entries_for_upos(entries, upos, dictionary, **kwargs):
    """Filter JMdict candidates at the *entry* level using transformer UPOS.

    Returns ``(primary_entries, other_entries)`` so the caller can display
    matching entries prominently and offer the rest behind a toggle.
    """
    if not entries:
        return [], []
    if not upos:
        return list(entries), []
    if hasattr(dictionary, "filter_entries_by_upos"):
        return dictionary.filter_entries_by_upos(entries, upos)
    return list(entries), []


# ---------------------------------------------------------------------------
# Japanese subsegment decomposition
# ---------------------------------------------------------------------------

def build_subsegments(
    token: str,
    dictionary,
    decompose: bool = False,
) -> Dict[str, Any]:
    """Build subsegment entries for the /subsegments route (Japanese)."""
    token_text = str(token or "")
    fill = dictionary.fill_token(
        token,
        allow_exact=not decompose,
        exclude_whole=decompose,
    ) if token else {"fills": []}
    prepared = prepare_fill_entries(fill.get("fills", []), dictionary, HOOKS)
    mode = fill.get("mode", "greedy")

    if decompose and token_text:
        prepared = [
            p for p in prepared
            if str((p or {}).get("head", "") or "") != token_text
        ]

    return {
        "ok": True,
        "token": token,
        "subsegments": prepared,
        "mode": mode,
    }


# ---------------------------------------------------------------------------
# HOOKS — registered with language_registry
# ---------------------------------------------------------------------------

HOOKS = LanguageHooks(
    reading_key="reading",
    build_g2p=_build_japanese_g2p,
    attach_forms=_attach_japanese_forms,
    choose_entry=_choose_japanese_entry,
    fill_token_with_lemma=_japanese_lemma_fallback,
    filter_entries_for_upos=_filter_japanese_entries_for_upos,
    deconjugate=None,
    build_subsegments=build_subsegments,
    preload=None,
)
