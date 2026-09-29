"""
Classical Chinese language hooks for the generic NLP pipeline.

Provides Classical Chinese-specific behavior: traditional/simplified form
attachment and entry selection.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from language_registry import LanguageHooks
from pipeline_common import (
    merge_all_entries,
    format_senses,
    prepare_fill_entries,
)


# ---------------------------------------------------------------------------
# Entry selection — prefer surface-matching form
# ---------------------------------------------------------------------------

def _choose_entry_for_surface(
    surface: str,
    entries: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Prefer the entry that matches the exact token surface form."""
    if not entries:
        return None
    if not surface:
        return entries[0]

    exact_neutral: List[Dict[str, Any]] = []
    trad_matches: List[Dict[str, Any]] = []
    simp_matches: List[Dict[str, Any]] = []
    for entry in entries:
        trad = str(entry.get("traditional", "") or "")
        simp = str(entry.get("simplified", "") or "")
        if trad == surface and simp == surface:
            exact_neutral.append(entry)
        elif trad == surface:
            trad_matches.append(entry)
        elif simp == surface:
            simp_matches.append(entry)

    if trad_matches and not simp_matches:
        return trad_matches[0]
    if simp_matches and not trad_matches:
        return simp_matches[0]
    if trad_matches and simp_matches:
        return trad_matches[0]
    if exact_neutral:
        return exact_neutral[0]
    return entries[0]


# ---------------------------------------------------------------------------
# Form attachment (traditional / simplified)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# UPOS-based entry filtering
# ---------------------------------------------------------------------------

def _filter_classical_entries_for_upos(entries, upos, dictionary, **kwargs):
    """Filter dictionary entries using UPOS tag and register.

    Returns ``(primary_entries, other_entries)`` so the caller can display
    matching entries prominently and offer the rest behind a toggle.
    """
    if not entries:
        return [], []
    xpos = str(kwargs.get("xpos", "") or "").strip()
    if hasattr(dictionary, "filter_entries_by_upos"):
        return dictionary.filter_entries_by_upos(entries, upos)
    return list(entries), []


def _entry_to_pos_group(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a single dictionary entry to a pos_group dict."""
    pos_label = entry.get("pos", "")
    english = entry.get("english", "")
    notes = entry.get("notes", "")
    if not english:
        return None
    sense_entry: Dict[str, Any] = {"glosses": [english]}
    if notes:
        sense_entry["notes"] = notes
    pg: Dict[str, Any] = {
        "pos": pos_label,
        "senses": [sense_entry],
    }
    register_en = entry.get("register_en", "")
    if register_en:
        pg["register"] = register_en
    topic_en = entry.get("topic_en", "")
    if topic_en:
        pg["topic"] = topic_en
    grammar_en = entry.get("grammar_en", "")
    if grammar_en:
        pg["grammar"] = grammar_en
    return pg


def _is_entry_primary(entry: Dict[str, Any], upos_allowed: Optional[set]) -> bool:
    """Return True if entry should appear in primary view.

    An entry is primary if:
    - Its register is NOT "Modern Chinese", AND
    - Its POS matches the UPOS-allowed set (or no UPOS filtering is active),
      OR its POS is filter-exempt (idioms, phrases).
    """
    from classical.dictionary import _FILTER_EXEMPT_POS
    reg = str(entry.get("register_en", "") or "").strip().lower()
    if reg == "modern chinese":
        return False
    if upos_allowed is None:
        return True
    pos_raw = str(entry.get("pos_raw", "") or "").strip().lower()
    if pos_raw in _FILTER_EXEMPT_POS:
        return True
    return pos_raw in upos_allowed


def _attach_classical_forms(
    target: Dict[str, Any],
    surface: str,
    entries: List[Dict[str, Any]],
) -> None:
    """Attach traditional/simplified forms and entry_groups to a payload dict.

    Groups entries by concept_id so that homographs with different meanings
    are rendered as separate spaced entries, each with its own headword,
    pinyin, and POS+glosses sub-groups.

    Within each concept group, senses are split into primary and filtered
    based on register (literary vs modern) and UPOS match.  Filtered senses
    are embedded as ``filtered_pos_groups`` inside the group so the frontend
    can show them behind an inline "Filtered senses" expander.
    """
    chosen = _choose_entry_for_surface(surface, entries)
    if chosen:
        trad = str(chosen.get("traditional", "") or "")
        simp = str(chosen.get("simplified", "") or "")
        target["traditional"] = trad or simp or surface
        target["simplified"] = simp or trad or surface
    elif surface:
        target["traditional"] = surface
        target["simplified"] = surface

    if not entries:
        return

    # Group entries by concept_id (senses sharing a headword).
    from collections import OrderedDict
    concept_buckets: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    for entry in entries:
        cid = str(entry.get("concept_id", "") or str(id(entry)))
        concept_buckets.setdefault(cid, []).append(entry)

    display_headword = str(surface or "").strip()
    all_groups: List[Dict[str, Any]] = []
    for _cid, bucket in concept_buckets.items():
        first = bucket[0]

        pos_groups: List[Dict[str, Any]] = []
        for entry in bucket:
            pg = _entry_to_pos_group(entry)
            if pg:
                pos_groups.append(pg)

        if not pos_groups:
            continue

        group: Dict[str, Any] = {
            "headword": display_headword or first.get("simplified", ""),
            "traditional": first.get("traditional", ""),
            "reading": first.get("pinyin", ""),
            "concept_id": _cid,
            "pos_groups": pos_groups,
        }

        all_groups.append(group)

    if all_groups:
        target["entry_groups"] = all_groups


# ---------------------------------------------------------------------------
# G2P — reuse modern Chinese Hanzi pronunciation payload
# ---------------------------------------------------------------------------

def _build_classical_g2p(word, dictionary, fallback_roman=""):
    """Hanzi decomposition/g2p is intentionally disabled to reduce memory use."""
    _ = (word, dictionary, fallback_roman)
    return None


# ---------------------------------------------------------------------------
# Subsegment decomposition — reuse modern Chinese Hanzi components
# ---------------------------------------------------------------------------

def _build_subsegments(
    token: str,
    dictionary,
    decompose: bool = False,
) -> Dict[str, Any]:
    """Build subsegment entries for the /subsegments route (Classical Chinese)."""
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
# Preloader for Hanzi decomposition resources
# ---------------------------------------------------------------------------

def _preload_classical():
    """Hanzi decomposition preload is intentionally disabled."""
    return None


# ---------------------------------------------------------------------------
# HOOKS — registered with language_registry
# ---------------------------------------------------------------------------

HOOKS = LanguageHooks(
    reading_key="pinyin",
    build_g2p=None,
    attach_forms=_attach_classical_forms,
    choose_entry=_choose_entry_for_surface,
    fill_token_with_lemma=None,
    filter_entries_for_upos=_filter_classical_entries_for_upos,
    build_subsegments=_build_subsegments,
    preload=None,
)
