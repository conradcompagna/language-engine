"""
Chinese language hooks for the generic NLP pipeline.

Provides Chinese-specific behavior: traditional/simplified form attachment,
CEDICT entry selection, and subsegment decomposition.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from chinese.dictionary import ChineseDict
from language_registry import LanguageHooks
from pipeline_common import (
    merge_all_entries,
    format_senses,
    prepare_fill_entries,
)


# ---------------------------------------------------------------------------
# Chinese-specific entry selection
# ---------------------------------------------------------------------------

def _choose_entry_for_surface(
    surface: str,
    entries: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Prefer the CEDICT row that matches the exact token surface form
    (traditional vs simplified) when available.
    """
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
# Chinese-specific form attachment (traditional / simplified)
# ---------------------------------------------------------------------------

def _attach_chinese_forms(
    target: Dict[str, Any],
    surface: str,
    entries: List[Dict[str, Any]],
) -> None:
    """Attach traditional/simplified forms to a payload dict."""
    chosen = _choose_entry_for_surface(surface, entries)
    if chosen:
        trad = str(chosen.get("traditional", "") or "")
        simp = str(chosen.get("simplified", "") or "")
        target["traditional"] = trad or simp or surface
        target["simplified"] = simp or trad or surface
    elif surface:
        target["traditional"] = surface
        target["simplified"] = surface


# ---------------------------------------------------------------------------
# Chinese g2p (Hanzi pronunciation + decomposition)
# ---------------------------------------------------------------------------

def _build_chinese_g2p(word, dictionary, fallback_roman=""):
    """Hanzi decomposition/g2p is intentionally disabled to reduce memory use."""
    _ = (word, dictionary, fallback_roman)
    return None


# ---------------------------------------------------------------------------
# Chinese-specific subsegment decomposition
# ---------------------------------------------------------------------------

def _build_hanzi_component_subsegments(
    token: str,
    cedict: ChineseDict,
) -> List[Dict[str, Any]]:
    """Hanzi decomposition mode is disabled."""
    _ = (token, cedict)
    return []


def build_subsegments(
    token: str,
    cedict: ChineseDict,
    decompose: bool = False,
) -> Dict[str, Any]:
    """Build subsegment entries for the /subsegments route (Chinese)."""
    token_text = str(token or "")
    fill = cedict.fill_token(
        token,
        allow_exact=not decompose,
        exclude_whole=decompose,
    ) if token else {"fills": []}
    prepared = prepare_fill_entries(fill.get("fills", []), cedict, HOOKS)
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

def _preload_chinese():
    """Hanzi decomposition preload is intentionally disabled."""
    return None


# ---------------------------------------------------------------------------
# HOOKS — registered with language_registry
# ---------------------------------------------------------------------------

HOOKS = LanguageHooks(
    reading_key="pinyin",
    build_g2p=None,
    attach_forms=_attach_chinese_forms,
    choose_entry=_choose_entry_for_surface,
    fill_token_with_lemma=None,
    build_subsegments=build_subsegments,
    preload=None,
)
