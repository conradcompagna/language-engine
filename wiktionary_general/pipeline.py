"""
Universal Wiktionary language hooks for the generic NLP pipeline.

These hooks are shared by all Wiktionary general pipeline languages
(Turkish, Tamil, Telugu, Persian, Marathi, Indonesian, Hindi, Arabic, Thai).

Trankit handles tokenization and POS / dependency parsing. Dictionary
lookup is intentionally simple: surface exact/form -> surface greedy.
Entry filtering uses UPOS tags (not XPOS).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

from language_registry import LanguageHooks
from pipeline_common import prepare_fill_entries
from wiktionary_general.dictionary import _etym_key


# ---------------------------------------------------------------------------
# Form attachment â€” etymology grouping + IPA + relations
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


def _attach_wikt_forms(
    target: Dict[str, Any],
    surface: str,
    entries: List[Dict[str, Any]],
) -> None:
    """Attach IPA variants, etymology, and relations.

    Entries are grouped by etymology â€” entries sharing the same
    etymology_number (or identical etymology text) are merged into
    one entry_group with multiple POS sub-categories.
    """
    chosen = entries[0] if entries else None
    if not chosen:
        return

    ipa_variants = chosen.get("ipa_variants", [])
    if ipa_variants:
        target["ipa_variants"] = ipa_variants

    audio_urls = chosen.get("audio_urls", [])
    if audio_urls:
        target["audio_urls"] = audio_urls

    # Korean-only enrichment: keep Hanja variants visible in morphology UI
    # while excluding them from reverse form-index lookup.
    korean_hanja_variants: List[str] = []
    for entry in entries:
        variants = entry.get("korean_hanja_variants", [])
        if isinstance(variants, list):
            korean_hanja_variants = _merge_word_lists(
                korean_hanja_variants,
                [str(v).strip() for v in variants if str(v).strip()],
            )
    if korean_hanja_variants:
        hanja_label = "Hanja variants: " + ", ".join(korean_hanja_variants)
        existing_morph = target.get("morph_info", [])
        if isinstance(existing_morph, str):
            existing_morph_list = [existing_morph]
        elif isinstance(existing_morph, list):
            existing_morph_list = [
                str(v).strip() for v in existing_morph if str(v).strip()
            ]
        else:
            existing_morph_list = []
        target["morph_info"] = _merge_word_lists(
            existing_morph_list,
            [hanja_label],
        )

    # Group entries by etymology boundary.
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

        # Build POS sub-groups
        pos_groups: List[Dict[str, Any]] = []
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
            alt_forms = entry.get("alt_forms", [])
            if alt_forms:
                pg["alt_forms"] = alt_forms
                all_alts.extend(alt_forms)
            pos_groups.append(pg)

            all_syns = _merge_word_lists(all_syns, entry.get("synonyms", []))
            all_ants = _merge_word_lists(all_ants, entry.get("antonyms", []))
            all_ders = _merge_word_lists(all_ders, entry.get("derived", []))
            all_rels = _merge_word_lists(all_rels, entry.get("related", []))

        group: Dict[str, Any] = {
            "headword": display_headword or first.get("headword", ""),
            "reading": first.get("reading", ""),
            "etym_key": _key,
            "pos_groups": pos_groups,
        }

        etym = first.get("etymology", "")
        if etym:
            group["etymology"] = etym

        alts_dedup = list(dict.fromkeys(all_alts))
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

    sf = chosen.get("senses_full")
    if sf:
        target["senses_full"] = sf


# ---------------------------------------------------------------------------
# G2P â€” IPA pronunciation from Kaikki sounds
# ---------------------------------------------------------------------------

def _build_wikt_g2p(word, dictionary, fallback_roman=""):
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
# Entry selection â€” prefer entries matching the surface form exactly
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
# Surface-first lookup:
# surface exact/form -> surface greedy
# ---------------------------------------------------------------------------

_COMPOUND_LEMMA_SPLIT_RE = re.compile(r"\s*[+\uFF0B]\s*")

def _lookup_entries_with_forms(dictionary, text: str) -> List[Dict[str, Any]]:
    """Resolve a term via direct lookup, then inflection-index fallback."""
    query = str(text or "").strip()
    if not query:
        return []

    # New Yomitan dictionaries may already include form fallback in lookup_all.
    entries = list(dictionary.lookup_all(query) or [])
    if entries:
        return entries

    # Backward compatibility if lookup_all is exact-only.
    lookup_via_forms = getattr(dictionary, "lookup_via_forms", None)
    if callable(lookup_via_forms):
        try:
            return list(lookup_via_forms(query) or [])
        except Exception:
            return []
    return []


def _norm_lookup_key(dictionary, text: str) -> str:
    """Normalize a string for lemma/headword comparison."""
    raw = unicodedata.normalize("NFKC", str(text or "").strip())
    if not raw:
        return ""
    lookup_key = getattr(dictionary, "_lookup_key", None)
    if callable(lookup_key):
        try:
            key = str(lookup_key(raw) or "").strip()
            if key:
                return key
        except Exception:
            pass
    return raw.casefold()


def _split_compound_lemma(lemma: str) -> List[str]:
    """Split compound lemmas like 'lemma+lemma' into components."""
    text = str(lemma or "").strip()
    if not text or ("+" not in text and "\uFF0B" not in text):
        return []
    parts = [p.strip() for p in _COMPOUND_LEMMA_SPLIT_RE.split(text) if p.strip()]
    return parts if len(parts) > 1 else []


def _resolve_exact_then_greedy(
    display_text: str,
    lookup_text: str,
    dictionary,
    upos: str = "",
    exact_mode: str = "exact",
    greedy_mode: str = "greedy",
) -> Optional[Dict[str, Any]]:
    """Resolve one lookup target via exact/form first, then greedy fill."""
    query = str(lookup_text or "").strip()
    if not query:
        return None

    entries = _lookup_entries_with_forms(dictionary, query)
    if entries:
        return _build_fill_result(display_text or query, entries, dictionary, exact_mode)

    fill = dictionary.fill_token(query, allow_exact=False, upos=upos)
    if fill.get("has_known"):
        all_entries = _collect_fill_entries(fill, dictionary)
        if all_entries:
            fill_out = dict(fill)
            fill_out["mode"] = greedy_mode
            return {"entries": all_entries, "fill": fill_out}
    return None


def _merge_lookup_results(results: List[Dict[str, Any]], mode: str) -> Optional[Dict[str, Any]]:
    """Merge per-target lookup results into one payload."""
    merged_entries: List[Dict[str, Any]] = []
    merged_fills: List[Dict[str, Any]] = []
    has_known = False
    has_unknown = False

    for result in results:
        if not isinstance(result, dict):
            continue
        merged_entries.extend(list(result.get("entries", []) or []))
        fill = result.get("fill", {}) or {}
        merged_fills.extend(list(fill.get("fills", []) or []))
        has_known = has_known or bool(fill.get("has_known"))
        has_unknown = has_unknown or bool(fill.get("has_unknown"))

    if not merged_entries:
        return None

    return {
        "entries": merged_entries,
        "fill": {
            "mode": mode,
            "fills": merged_fills,
            "has_known": has_known or bool(merged_entries),
            "has_unknown": has_unknown,
        },
    }


def _resolve_lemma_override(
    surface: str,
    lemma_text: str,
    dictionary,
    upos: str = "",
    xpos: str = "",
) -> Optional[Dict[str, Any]]:
    """Resolve lemma (or lemma set) via exact-then-greedy per target."""
    _ = xpos
    lemma_value = str(lemma_text or "").strip()
    if not lemma_value:
        return None

    parts = _split_compound_lemma(lemma_value)
    targets = parts if parts else [lemma_value]
    seen = set()
    ordered_targets: List[str] = []
    for target in targets:
        key = _norm_lookup_key(dictionary, target)
        if key and key not in seen:
            seen.add(key)
            ordered_targets.append(target)

    per_target: List[Dict[str, Any]] = []
    for target in ordered_targets:
        # For a single-lemma token, keep the display head as the surface token.
        display_text = surface if len(ordered_targets) == 1 else target
        resolved = _resolve_exact_then_greedy(
            display_text=display_text,
            lookup_text=target,
            dictionary=dictionary,
            upos=upos,
            exact_mode="lemma_override",
            greedy_mode="lemma_greedy",
        )
        if resolved:
            per_target.append(resolved)

    mode = "lemma_override" if len(ordered_targets) == 1 else "lemma_multi"
    return _merge_lookup_results(per_target, mode)


def _build_fill_piece_from_entry(
    surface_text: str,
    entry: Dict[str, Any],
    all_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build one fill row from a resolved dictionary entry."""
    surface = str(surface_text or "")
    lemma_head = str(entry.get("headword", "") or "")
    head = surface or lemma_head
    fill: Dict[str, Any] = {
        "text": surface,
        "head": head,
        "roman": entry.get("reading", ""),
        "senses": entry.get("senses", []),
        "pos": entry.get("pos", ""),
        "source": "KAIKKI",
        "entries": list(all_entries or []),
    }
    for key in (
        "etymology",
        "senses_full",
        "ipa_variants",
        "grammar",
        "morph_info",
        "morph_base",
    ):
        val = entry.get(key)
        if val:
            fill[key] = val
    if lemma_head and lemma_head != head:
        fill["surface_form"] = surface
        fill["lemma_form"] = lemma_head
        if not fill.get("morph_base"):
            fill["morph_base"] = lemma_head
    return fill


def _result_match_count(result: Optional[Dict[str, Any]]) -> int:
    """Count matched fill units used for arbitration (exact=1, greedy=pieces)."""
    if not isinstance(result, dict):
        return 0
    fill = result.get("fill", {}) or {}
    fills = list(fill.get("fills", []) or [])
    if fills:
        return len(fills)
    return len(list(result.get("entries", []) or []))


def _wikt_lookup(word, lemma, dictionary, xpos="", upos=""):
    """Surface and lemma arbitration: exact->greedy, then pick fewer entries."""
    surface = str(word or "").strip()
    lemma_text = str(lemma or "").strip()
    if not surface:
        return None

    surface_result = _resolve_exact_then_greedy(
        display_text=surface,
        lookup_text=surface,
        dictionary=dictionary,
        upos=upos,
        exact_mode="exact",
        greedy_mode="greedy",
    )

    # No usable lemma (or lemma same as surface): keep surface path.
    if not lemma_text or _norm_lookup_key(dictionary, lemma_text) == _norm_lookup_key(dictionary, surface):
        return surface_result

    lemma_result = _resolve_lemma_override(
        surface,
        lemma_text,
        dictionary,
        upos=upos,
        xpos=xpos,
    )
    if lemma_result is None:
        return surface_result
    if surface_result is None:
        return lemma_result

    # Pick the less noisy path by exact/greedy match unit count; ties stay on surface.
    if _result_match_count(lemma_result) < _result_match_count(surface_result):
        return lemma_result
    return surface_result


def _build_fill_result(text, entries, dictionary, mode):
    """Build result dict for an exact-match hit."""
    _ = dictionary
    best = entries[0]
    fill_entry = _build_fill_piece_from_entry(text, best, list(entries))
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
# UPOS-based entry filtering
# ---------------------------------------------------------------------------

def _filter_wikt_entries_for_upos(entries, upos, dictionary, **kwargs):
    """Filter Kaikki entries at the entry level using UPOS tags.

    Returns ``(primary_entries, other_entries)`` so the caller can display
    matching entries prominently and offer the rest behind a toggle.
    """
    if not entries:
        return [], []
    if hasattr(dictionary, "filter_entries_by_upos"):
        try:
            return dictionary.filter_entries_by_upos(entries, upos, **kwargs)
        except TypeError:
            return dictionary.filter_entries_by_upos(entries, upos)
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
# HOOKS â€” registered with language_registry
# ---------------------------------------------------------------------------

HOOKS = LanguageHooks(
    reading_key="reading",
    build_g2p=_build_wikt_g2p,
    attach_forms=_attach_wikt_forms,
    choose_entry=_choose_entry,
    fill_token_with_lemma=_wikt_lookup,
    filter_entries_for_upos=_filter_wikt_entries_for_upos,
    deconjugate=None,
    build_subsegments=_build_subsegments,
    preload=None,
)

