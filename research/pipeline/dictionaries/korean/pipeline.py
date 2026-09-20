"""
Korean language hooks for the generic NLP pipeline.

Matching strategy:
- For each token from Trankit, use the lemma if it exists and differs
  from the surface form.
- Prefer exact dictionary match.  If no exact match, fall back to greedy
  forward maximum matching.
- Try lemma first, then surface form.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from language_registry import LanguageHooks
from pipeline_common import prepare_fill_entries


# ---------------------------------------------------------------------------
# Entry selection
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Form attachment
# ---------------------------------------------------------------------------

def _attach_korean_forms(
    target: Dict[str, Any],
    surface: str,
    entries: List[Dict[str, Any]],
) -> None:
    """Attach reading, canonical_form, and all rich KRDICT fields.

    Merges data from ALL entries (not just the chosen one) so every
    homonym / POS variant is represented in the frontend.
    """
    chosen = entries[0] if entries else None
    if chosen:
        target["reading"] = chosen.get("reading", "") or ""
        target["pos_kr"] = chosen.get("pos", "") or ""
        target["level"] = chosen.get("level", "") or ""
        canonical = chosen.get("canonical_form", "") or ""
        if canonical:
            target["canonical_form"] = canonical
        # Scalar fields from chosen entry
        for key in ("entry_id", "homonym_number", "lexical_unit", "origin"):
            val = chosen.get(key)
            if val:
                target[key] = val

        # Merge list fields from ALL entries so every definition appears.
        # Each entry_group bundles its POS / origin / senses together so
        # the frontend can render grouped headings.
        all_groups = []
        all_conjugations = []
        all_related = []
        seen_related = set()
        for entry in (entries or []):
            senses = entry.get("senses_full", [])
            if senses:
                hw = entry.get("headword", "")
                is_affix = hw.startswith("-") or hw.endswith("-")
                all_groups.append({
                    "headword": hw,
                    "pos": entry.get("pos", ""),
                    "origin": entry.get("origin", ""),
                    "lexical_unit": entry.get("lexical_unit", ""),
                    "reading": entry.get("reading", ""),
                    "conjugations": entry.get("conjugations", []),
                    "senses": senses,
                    "_is_affix": is_affix,
                })
            for conj in entry.get("conjugations", []):
                all_conjugations.append(conj)
            for rf in entry.get("related_forms", []):
                key = (rf.get("type", ""), rf.get("written", ""))
                if key not in seen_related:
                    seen_related.add(key)
                    all_related.append(rf)

        if all_groups:
            # Sort: non-affix entries first, then affixes
            all_groups.sort(key=lambda g: (g.pop("_is_affix", False),))
            target["entry_groups"] = all_groups
        if all_conjugations:
            target["conjugations"] = all_conjugations
        if all_related:
            target["related_forms"] = all_related
        # Keep senses_full from chosen for backward compat
        sf = chosen.get("senses_full")
        if sf:
            target["senses_full"] = sf
    elif surface:
        target["reading"] = ""


# ---------------------------------------------------------------------------
# G2P — pronunciation from dictionary reading field
# ---------------------------------------------------------------------------

def _build_korean_g2p(word, dictionary, fallback_roman=""):
    """Return a g2p payload with the pronunciation reading from KRDICT."""
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
# Lemma fallback — the core matching logic
# ---------------------------------------------------------------------------

def _korean_lookup(word, lemma, dictionary, xpos=""):
    """
    Korean dictionary lookup — two paths, same normalization.

    Path 1 (lemma exists): exact match on joined lemma → greedy over
    joined lemma respecting morpheme boundaries.  Never touches surface.

    Path 2 (no lemma): exact match on surface → unrestricted greedy
    over surface.

    Both paths go through the normalized index (pass 1: strip dashes,
    pass 2: expand/strip 다).  All entries appended without scoring.

    When *xpos* is provided (e.g. ``"ncn+jca"``), candidates that span
    multiple morphemes are validated: at least one dictionary entry must
    have a ``pos_raw`` allowed by the XPOS tags of the underlying
    morphemes.  This prevents spurious whole-token matches like 글로
    (adverb "that way") when the analysis is 글 (noun) + 로 (particle).
    """
    from korean.dictionary import entries_match_xpos

    if not word and not lemma:
        return None

    xpos_tags = [t.strip().lower() for t in xpos.split("+") if t.strip()] if xpos else []

    if lemma:
        # --- LEMMA PATH ---
        morphemes = lemma.split("+") if "+" in lemma else [lemma]
        joined = "".join(morphemes)
        is_compound = len(morphemes) > 1

        # 1a. Exact match on whole joined string
        entries = dictionary.lookup_all(joined)
        if entries:
            # When the lemma spans multiple morphemes, validate the match
            # against the XPOS tags.  If no entry matches the allowed POS,
            # skip and fall through to the greedy path which will split
            # at morpheme boundaries.
            if is_compound and xpos_tags and not entries_match_xpos(entries, xpos_tags):
                pass  # fall through to greedy
            else:
                return _build_fill_result(joined, entries, dictionary, "lemma")

        # 1b. Greedy over joined string, respecting morpheme boundaries
        boundaries = []
        offset = 0
        for m in morphemes[:-1]:
            offset += len(m)
            boundaries.append(offset)
        fill = dictionary.fill_token(
            joined, boundaries=boundaries if boundaries else None,
            xpos_tags=xpos_tags if is_compound else None,
            morphemes=morphemes if is_compound else None,
        )
        if fill.get("has_known"):
            fill["mode"] = "lemma"
            all_entries = _collect_fill_entries(fill, dictionary)
            if all_entries:
                return {"entries": all_entries, "fill": fill}

        return None

    else:
        # --- SURFACE PATH (no lemma) ---
        # 2a. Exact match on whole surface
        entries = dictionary.lookup_all(word)
        if entries:
            return _build_fill_result(word, entries, dictionary, "exact")

        # 2b. Unrestricted greedy over surface
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
        "level": best.get("level", ""),
        "canonical_form": best.get("canonical_form", ""),
        "source": "KRDICT",
        "entries": list(entries),
    }
    for key in ("entry_id", "homonym_number", "lexical_unit", "origin",
                "conjugations", "related_forms", "senses_full"):
        val = best.get(key)
        if val:
            fill_entry[key] = val
    return {
        "entries": list(entries),
        "fill": {"mode": mode, "fills": [fill_entry],
                 "has_known": True, "has_unknown": False},
    }


def _collect_fill_entries(fill, dictionary):
    """Collect all entries from greedy fill pieces, no dedup, no scoring.

    Entries are already stored on each fill piece by the greedy matcher,
    so no re-lookup is needed.  All entries are appended as-is.
    """
    all_entries = []
    for f in fill.get("fills", []):
        if f.get("source") != "UNKNOWN":
            all_entries.extend(f.get("entries", []))
    return all_entries


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
# XPOS-based entry filtering
# ---------------------------------------------------------------------------

def _filter_korean_entries_for_xpos(entries, upos, dictionary, xpos=""):
    """Filter KRDICT entries using KAIST XPOS tags.

    Splits the compound xpos string (e.g. ``"ncn+jcs"``) into individual
    tags and delegates to ``dictionary.filter_entries_by_xpos``.
    Falls back to no filtering when xpos is unavailable.
    """
    if not entries:
        return [], []
    if not xpos:
        return list(entries), []
    tags = [t.strip() for t in xpos.split("+") if t.strip()]
    if not tags:
        return list(entries), []
    if hasattr(dictionary, "filter_entries_by_xpos"):
        return dictionary.filter_entries_by_xpos(entries, tags)
    return list(entries), []


# ---------------------------------------------------------------------------
# HOOKS — registered with language_registry
# ---------------------------------------------------------------------------

HOOKS = LanguageHooks(
    reading_key="reading",
    build_g2p=_build_korean_g2p,
    attach_forms=_attach_korean_forms,
    choose_entry=None,
    fill_token_with_lemma=_korean_lookup,
    filter_entries_for_upos=_filter_korean_entries_for_xpos,
    deconjugate=None,
    build_subsegments=_build_subsegments,
    preload=None,
)
