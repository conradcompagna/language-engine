"""
Vietnamese language hooks for the generic NLP pipeline.

Vietnamese is an analytic, whitespace-delimited language.  Trankit
handles tokenization (which may merge multi-syllable words) and
POS / dependency parsing.  Dictionary lookup is exact-match first,
then greedy forward maximum matching over space-separated tokens.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from language_registry import LanguageHooks
from pipeline_common import prepare_fill_entries
from vietnamese.dictionary import _etym_key


# ---------------------------------------------------------------------------
# Form attachment — Hán tự (CJK) characters + etymology
# ---------------------------------------------------------------------------


def _merge_word_lists(*lists: List[str]) -> List[str]:
    """Merge multiple word lists preserving order and deduping."""
    seen: set = set()
    out: List[str] = []
    for lst in lists:
        for w in lst:
            if w and w not in seen:
                seen.add(w)
                out.append(w)
    return out


def _attach_vietnamese_forms(
    target: Dict[str, Any],
    surface: str,
    entries: List[Dict[str, Any]],
) -> None:
    """Attach Hán tự, IPA variants, etymology, and relations.

    Entries are grouped by etymology — entries sharing the same
    etymology_number (or identical etymology text) are merged into
    one entry_group with multiple POS sub-categories.  This reflects
    the actual word boundaries on Wiktionary.
    """
    chosen = entries[0] if entries else None
    if not chosen:
        return

    han_tu = chosen.get("han_tu", "")
    if han_tu:
        target["han_tu"] = han_tu

    ipa_variants = chosen.get("ipa_variants", [])
    if ipa_variants:
        target["ipa_variants"] = ipa_variants

    audio_urls = chosen.get("audio_urls", [])
    if audio_urls:
        target["audio_urls"] = audio_urls

    # Group entries by etymology boundary.
    # Each etymology group becomes one entry_group containing multiple
    # POS sub-groups (pos_groups).
    from collections import OrderedDict
    etym_buckets: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    for entry in entries:
        senses_full = entry.get("senses_full", [])
        if not senses_full:
            continue
        key = _etym_key(entry)
        etym_buckets.setdefault(key, []).append(entry)

    display_headword = str(surface or "").strip()
    all_groups: List[Dict[str, Any]] = []
    for _key, bucket in etym_buckets.items():
        first = bucket[0]
        # Merge han_tu across POS sub-entries (pick first non-empty)
        group_han_tu = ""
        for e in bucket:
            ht = e.get("han_tu", "")
            if ht:
                group_han_tu = ht
                break

        # Build POS sub-groups
        pos_groups: List[Dict[str, Any]] = []
        all_clfs: List[str] = []
        all_alts: List[str] = []
        all_syns: List[str] = []
        all_ants: List[str] = []
        all_ders: List[str] = []
        all_rels: List[str] = []

        for entry in bucket:
            pg: Dict[str, Any] = {
                "pos": entry.get("pos", ""),
                "senses": entry.get("senses_full", []),
            }
            # Per-POS classifiers and alt forms
            clfs = entry.get("classifiers", [])
            if clfs:
                pg["classifiers"] = clfs
                all_clfs.extend(clfs)
            alt_forms = entry.get("alt_forms", [])
            if alt_forms:
                pg["alt_forms"] = alt_forms
                all_alts.extend(alt_forms)
            pos_groups.append(pg)

            # Accumulate relations
            all_syns = _merge_word_lists(all_syns, entry.get("synonyms", []))
            all_ants = _merge_word_lists(all_ants, entry.get("antonyms", []))
            all_ders = _merge_word_lists(all_ders, entry.get("derived", []))
            all_rels = _merge_word_lists(all_rels, entry.get("related", []))

        group: Dict[str, Any] = {
            "headword": display_headword or first.get("headword", ""),
            "han_tu": group_han_tu,
            "reading": first.get("reading", ""),
            "etym_key": _key,
            "pos_groups": pos_groups,
        }

        etym = first.get("etymology", "")
        if etym:
            group["etymology"] = etym

        # Deduplicated classifiers / alt forms at the group level
        clfs_dedup = list(dict.fromkeys(all_clfs))
        alts_dedup = list(dict.fromkeys(all_alts))
        if clfs_dedup:
            group["classifiers"] = clfs_dedup
        if alts_dedup:
            group["alt_forms"] = alts_dedup
        if all_syns:
            group["synonyms"] = all_syns
        if all_ants:
            group["antonyms"] = all_ants
        if all_ders:
            group["derived"] = all_ders
        if all_rels:
            group["related"] = all_rels

        all_groups.append(group)

    if all_groups:
        target["entry_groups"] = all_groups

    # senses_full from chosen for backward compat
    sf = chosen.get("senses_full")
    if sf:
        target["senses_full"] = sf


# ---------------------------------------------------------------------------
# G2P — IPA pronunciation from Kaikki sounds
# ---------------------------------------------------------------------------

def _build_vietnamese_g2p(word, dictionary, fallback_roman=""):
    """Return a g2p payload with IPA pronunciation."""
    entry = dictionary.lookup(word)
    ipa = ""
    ipa_variants = []
    if entry:
        ipa = entry.get("reading", "") or ""
        ipa_variants = entry.get("ipa_variants", [])
    if not ipa:
        ipa = fallback_roman or ""

    return {
        "overall_roman": ipa,
        "syllables": [],
        "ipa_variants": ipa_variants,
    }


# ---------------------------------------------------------------------------
# Entry selection — prefer entries matching the surface form exactly
# ---------------------------------------------------------------------------

def _choose_entry(
    surface: str,
    entries: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Prefer entries whose headword casing matches the surface form."""
    if not entries:
        return None
    if not surface:
        return entries[0]
    for e in entries:
        if e.get("headword") == surface:
            return e
    return entries[0]


# ---------------------------------------------------------------------------
# Lemma fallback — try lemma from trankit if surface has no match
# ---------------------------------------------------------------------------

def _vietnamese_lookup(word, lemma, dictionary, xpos=""):
    """Vietnamese dictionary lookup with lemma fallback.

    Path 1 (lemma): exact match on lemma.
    Path 2 (surface): exact match, then greedy.
    """
    if not word and not lemma:
        return None

    if lemma and lemma != word:
        entries = dictionary.lookup_all(lemma)
        if entries:
            return _build_fill_result(lemma, entries, dictionary, "lemma")

    # Surface path
    entries = dictionary.lookup_all(word)
    if entries:
        return _build_fill_result(word, entries, dictionary, "exact")

    # Greedy over surface
    fill = dictionary.fill_token(word)
    if fill.get("has_known"):
        all_entries = _collect_fill_entries(fill, dictionary)
        if all_entries:
            return {"entries": all_entries, "fill": fill}

    return None


def _build_fill_result(text, entries, dictionary, mode):
    """Build result dict for an exact-match hit."""
    best = entries[0]
    fill_entry = {
        "text": text,
        "head": text,
        "roman": best.get("reading", ""),
        "senses": best.get("senses", []),
        "pos": best.get("pos", ""),
        "source": "KAIKKI",
        "entries": list(entries),
    }
    for key in ("han_tu", "etymology", "senses_full", "ipa_variants"):
        val = best.get(key)
        if val:
            fill_entry[key] = val
    return {
        "entries": list(entries),
        "fill": {"mode": mode, "fills": [fill_entry],
                 "has_known": True, "has_unknown": False},
    }


def _collect_fill_entries(fill, dictionary):
    """Collect all entries from greedy fill pieces."""
    all_entries = []
    for f in fill.get("fills", []):
        if f.get("source") != "UNKNOWN":
            all_entries.extend(f.get("entries", []))
    return all_entries


# ---------------------------------------------------------------------------
# XPOS-based entry filtering
# ---------------------------------------------------------------------------

def _filter_vietnamese_entries_for_upos(entries, upos, dictionary, **kwargs):
    """Filter Kaikki entries at the entry level using transformer XPOS.

    Returns ``(primary_entries, other_entries)`` so the caller can display
    matching entries prominently and offer the rest behind a toggle.
    """
    if not entries:
        return [], []
    xpos = str(kwargs.get("xpos", "") or "").strip()
    if hasattr(dictionary, "filter_entries_by_xpos"):
        return dictionary.filter_entries_by_xpos(entries, xpos)
    # Backward compatibility fallback.
    if hasattr(dictionary, "filter_entries_by_upos"):
        return dictionary.filter_entries_by_upos(entries, xpos or upos)
    return list(entries), []


# ---------------------------------------------------------------------------
# Subsegment decomposition
# ---------------------------------------------------------------------------

def _build_subsegments(
    token: str,
    dictionary,
    decompose: bool = False,
) -> Dict[str, Any]:
    """Build subsegment entries for the /subsegments route."""
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
    build_g2p=_build_vietnamese_g2p,
    attach_forms=_attach_vietnamese_forms,
    choose_entry=_choose_entry,
    fill_token_with_lemma=_vietnamese_lookup,
    filter_entries_for_upos=_filter_vietnamese_entries_for_upos,
    deconjugate=None,
    build_subsegments=_build_subsegments,
    preload=None,
)
