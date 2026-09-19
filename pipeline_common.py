"""
Generic NLP pipeline — shared across all languages.

Receives preprocessed text, Trankit output, a dictionary, and language hooks,
then builds the standard response dict the frontend expects.

Language-specific behavior (g2p, form attachment, entry selection) is
injected through LanguageHooks from language_registry.py.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from debug_store import (
    is_mwt_realign_debug_enabled,
    push_mwt_realign_trace,
)
from debug_trace_runtime import is_trace_active, trace_scope
from language_registry import LanguageHooks
from trankit_mwt_expansion import (
    language_supports_mwt,
    maybe_expand_mwt_doc,
)

# ---------------------------------------------------------------------------
# UPOS color map (universal across all languages)
# ---------------------------------------------------------------------------
UPOS_COLORS = {
    "ADJ": "#fde68a",
    "ADP": "#e0f2fe",
    "ADV": "#fee2e2",
    "AUX": "#e0e7ff",
    "CCONJ": "#cffafe",
    "DET": "#f1f5f9",
    "INTJ": "#fcd34d",
    "NOUN": "#bbf7d0",
    "NUM": "#f5d0fe",
    "PART": "#f4f4f5",
    "PRON": "#e2e8f0",
    "PROPN": "#c7d2fe",
    "PUNCT": "#e5e7eb",
    "SCONJ": "#bae6fd",
    "SYM": "#f3e8ff",
    "VERB": "#fda4af",
    "X": "#d1d5db",
}


# ---------------------------------------------------------------------------
# MWT child realignment
# ---------------------------------------------------------------------------

def _mwt_probe_text(part: dict) -> str:
    """Return the best probe string for a child: text if real, else lemma."""
    t = str(part.get("text", "") or "").strip()
    if t and t != "_":
        return t
    return str(part.get("lemma", "") or "").strip()


def _compress_alignment_steps(
    steps: List[Tuple[str, int, int, int, int]],
    region_offset: int,
) -> List[Tuple[str, int, int, int, int]]:
    out: List[Tuple[str, int, int, int, int]] = []
    for tag, i1, i2, j1, j2 in steps:
        b1 = region_offset + j1
        b2 = region_offset + j2
        if out and out[-1][0] == tag and out[-1][2] == i1 and out[-1][4] == b1:
            prev = out[-1]
            out[-1] = (tag, prev[1], i2, prev[3], b2)
        else:
            out.append((tag, i1, i2, b1, b2))
    return out


def _align_probe_to_slice_dp(
    probe: str,
    surface_region: str,
    region_offset: int,
) -> Dict[str, Any]:
    """
    Character-level alignment between one child probe and one candidate parent
    surface slice, solved by DP.

    Returns a dict with:
      - exact: True when probe == surface_region exactly
      - matched_chars: count of exact character matches in the chosen alignment
      - edit_count: count of non-match edits in the chosen alignment
      - char_map: parent-relative surface offset for every probe char
      - opcodes: compressed opcode tuples in the existing debug-panel shape
    """
    probe_len = len(probe)
    surface_len = len(surface_region)
    scores: List[List[Optional[Tuple[int, int]]]] = [
        [None] * (surface_len + 1) for _ in range(probe_len + 1)
    ]
    back: List[List[Optional[Tuple[int, int, str]]]] = [
        [None] * (surface_len + 1) for _ in range(probe_len + 1)
    ]
    scores[0][0] = (0, 0)  # (matched_chars, negative_edit_count)

    for i in range(probe_len + 1):
        for j in range(surface_len + 1):
            base = scores[i][j]
            if base is None:
                continue

            if i < probe_len and j < surface_len:
                is_equal = probe[i] == surface_region[j]
                cand = (
                    base[0] + (1 if is_equal else 0),
                    base[1] - (0 if is_equal else 1),
                )
                incumbent = scores[i + 1][j + 1]
                if incumbent is None or cand > incumbent:
                    scores[i + 1][j + 1] = cand
                    back[i + 1][j + 1] = (i, j, "equal" if is_equal else "replace")

            if i < probe_len:
                cand = (base[0], base[1] - 1)
                incumbent = scores[i + 1][j]
                if incumbent is None or cand > incumbent:
                    scores[i + 1][j] = cand
                    back[i + 1][j] = (i, j, "delete")

            if j < surface_len:
                cand = (base[0], base[1] - 1)
                incumbent = scores[i][j + 1]
                if incumbent is None or cand > incumbent:
                    scores[i][j + 1] = cand
                    back[i][j + 1] = (i, j, "insert")

    best_score = scores[probe_len][surface_len] or (0, 0)
    steps_rev: List[Tuple[str, int, int, int, int]] = []
    i = probe_len
    j = surface_len
    while i > 0 or j > 0:
        prev = back[i][j]
        if prev is None:
            break
        pi, pj, tag = prev
        steps_rev.append((tag, pi, i, pj, j))
        i = pi
        j = pj
    steps = list(reversed(steps_rev))

    char_map: List[int] = [region_offset] * probe_len
    last_anchor = region_offset
    for tag, i1, _i2, j1, j2 in steps:
        if tag in ("equal", "replace"):
            char_map[i1] = region_offset + j1
            if j2 > j1:
                last_anchor = region_offset + j2 - 1
        elif tag == "delete":
            char_map[i1] = last_anchor
        elif tag == "insert":
            if j2 > j1:
                last_anchor = region_offset + j2 - 1

    return {
        "exact": probe == surface_region,
        "matched_chars": best_score[0],
        "edit_count": -best_score[1],
        "char_map": char_map,
        "opcodes": _compress_alignment_steps(steps, region_offset),
    }


def _solve_mwt_partition_dp(probes: List[str], surface: str) -> Optional[List[Dict[str, Any]]]:
    """
    Solve the full child sequence against the full parent surface in one DP.

    Score order is lexicographic:
      1. maximize number of exact child matches
      2. maximize matched characters
      3. minimize edits
    """
    child_count = len(probes)
    surface_len = len(surface)
    suffix_nonempty = [0] * (child_count + 1)
    for i in range(child_count - 1, -1, -1):
        suffix_nonempty[i] = suffix_nonempty[i + 1] + (1 if probes[i] else 0)

    scores: List[List[Optional[Tuple[int, int, int]]]] = [
        [None] * (surface_len + 1) for _ in range(child_count + 1)
    ]
    parents: List[List[Optional[Tuple[int, Tuple[int, int, int]]]]] = [
        [None] * (surface_len + 1) for _ in range(child_count + 1)
    ]
    scores[0][0] = (0, 0, 0)  # (exact_child_count, matched_chars, negative_edit_count)
    local_cache: Dict[Tuple[int, int, int], Dict[str, Any]] = {}

    for child_idx, probe in enumerate(probes):
        remaining_nonempty = suffix_nonempty[child_idx + 1]
        require_width = 1 if probe else 0
        for start in range(surface_len + 1):
            prev_score = scores[child_idx][start]
            if prev_score is None:
                continue
            max_end = surface_len - remaining_nonempty
            if start > max_end:
                continue
            if require_width:
                min_end = start + 1
                if min_end > max_end:
                    continue
                end_iter = range(min_end, max_end + 1)
            else:
                end_iter = (start,)

            for end in end_iter:
                cache_key = (child_idx, start, end)
                local = local_cache.get(cache_key)
                if local is None:
                    local = _align_probe_to_slice_dp(probe, surface[start:end], start)
                    local_cache[cache_key] = local
                cand = (
                    prev_score[0] + (1 if local["exact"] else 0),
                    prev_score[1] + int(local["matched_chars"]),
                    prev_score[2] - int(local["edit_count"]),
                )
                incumbent = scores[child_idx + 1][end]
                if incumbent is None or cand > incumbent:
                    scores[child_idx + 1][end] = cand
                    parents[child_idx + 1][end] = (start, cache_key)

    final_score = scores[child_count][surface_len]
    if final_score is None:
        return None

    out: List[Optional[Dict[str, Any]]] = [None] * child_count
    end = surface_len
    for child_idx in range(child_count, 0, -1):
        parent = parents[child_idx][end]
        if parent is None:
            return None
        start, cache_key = parent
        local = local_cache[cache_key]
        out[child_idx - 1] = {
            "surface_slice": [start, end],
            "surface_char_map": list(local["char_map"]),
            "opcodes": list(local["opcodes"]),
        }
        end = start

    if end != 0:
        return None
    return [row for row in out if row is not None]


def _realign_mwt_children(parts: list, surface: str) -> None:
    """
    Assign a parent-relative surface_slice AND a per-character lattice
    (surface_char_map) to every child in `parts`.

    Trankit supplies NO spans for MWT children — only child text and lemma.
    This function is authoritative: slices are *derived* from the lattice,
    not the other way around, so the whole alignment is character-level.

    Strategy (in-place):
      Pass A — trivial equality: concat(probes) == surface.
      Pass B — one global DP solve across the entire child sequence. The DP
               chooses an ordered, contiguous partition of the full parent
               surface and scores it lexicographically by:
                 1. exact child slice matches
                 2. matched characters
                 3. fewer edits

    Each part gets:
      part["surface_slice"] = [start, end]        (parent-relative)
      part["surface_char_map"] = [o0, o1, ...]    (len == len(probe))
      part["_realign_pass"] = "trivial" | "dp" | "empty"
    """
    n = len(parts)
    surface_len = len(surface)
    debug_on = is_mwt_realign_debug_enabled()

    if n == 0 or surface_len == 0:
        for p in parts:
            if p.get("surface_slice") is None:
                p["surface_slice"] = [0, 0]
            p.setdefault("_realign_pass", "empty")
            probe = _mwt_probe_text(p)
            p["surface_char_map"] = [0] * len(probe)
        if debug_on:
            push_mwt_realign_trace({
                "surface": surface, "children": [], "note": "empty",
            })
        return

    probes = [_mwt_probe_text(p) for p in parts]

    # Clear proportional preassignments from _derive_child_spans — this
    # function is authoritative and recomputes slices from scratch.
    for p in parts:
        p.pop("surface_slice", None)

    # --- Pass A: trivial equality ----------------------------------------
    if "".join(probes) == surface:
        cursor = 0
        for i, p in enumerate(parts):
            plen = len(probes[i])
            p["surface_slice"] = [cursor, cursor + plen]
            p["surface_char_map"] = [cursor + k for k in range(plen)]
            p["_realign_pass"] = "trivial"
            cursor += plen
        if debug_on:
            push_mwt_realign_trace({
                "surface": surface,
                "children": [
                    {
                        "probe": probes[i],
                        "slice": parts[i]["surface_slice"],
                        "char_map": parts[i]["surface_char_map"],
                        "pass": "trivial",
                        "opcodes": [],
                    }
                    for i in range(n)
                ],
                "note": "trivial_equality",
            })
        return

    solved = _solve_mwt_partition_dp(probes, surface)
    if solved is None:
        raise RuntimeError(f"MWT DP realignment failed for surface {surface!r}")

    for i, p in enumerate(parts):
        probe = probes[i]
        if not probe:
            if i < len(solved):
                p["surface_slice"] = list(solved[i]["surface_slice"])
                p["surface_char_map"] = []
            p["_realign_pass"] = "empty"
            continue
        p["surface_slice"] = list(solved[i]["surface_slice"])
        p["surface_char_map"] = list(solved[i]["surface_char_map"])
        p["_realign_pass"] = "dp"

    if debug_on:
        push_mwt_realign_trace({
            "surface": surface,
            "children": [
                {
                    "probe": probes[i],
                    "slice": list(parts[i]["surface_slice"]),
                    "char_map": list(parts[i]["surface_char_map"]),
                    "pass": parts[i]["_realign_pass"],
                    "opcodes": list(solved[i]["opcodes"] if i < len(solved) else []),
                }
                for i in range(n)
            ],
            "note": "dp",
        })


def _lookup_to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_lookup_int_pair(value: Any) -> bool:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return False
    return _lookup_to_int(value[0], None) is not None and _lookup_to_int(value[1], None) is not None


def _normalize_lookup_span(raw_span: Any) -> Optional[List[int]]:
    if not isinstance(raw_span, (tuple, list)) or len(raw_span) < 2:
        return None
    start = _lookup_to_int(raw_span[0], None)
    end = _lookup_to_int(raw_span[1], None)
    if start is None or end is None:
        return None
    if end < start:
        end = start
    return [start, end]


def _absolute_span_from_parent_slice(
    parent_span: Optional[List[int]],
    surface_slice: Optional[List[int]],
) -> Optional[List[int]]:
    if parent_span is None or surface_slice is None:
        return None
    parent_start = _lookup_to_int(parent_span[0], None)
    parent_end = _lookup_to_int(parent_span[1], None)
    rel_start = _lookup_to_int(surface_slice[0], None)
    rel_end = _lookup_to_int(surface_slice[1], None)
    if None in (parent_start, parent_end, rel_start, rel_end):
        return None
    if parent_end < parent_start:
        parent_end = parent_start
    width = max(0, parent_end - parent_start)
    if rel_start < 0:
        rel_start = 0
    if rel_end < rel_start:
        rel_end = rel_start
    if rel_start > width:
        rel_start = width
    if rel_end > width:
        rel_end = width
    return [parent_start + rel_start, parent_start + rel_end]


def _build_surface_anchor_payload(
    child_row: Dict[str, Any],
    surface_text: str,
    absolute_slice: Optional[List[int]],
) -> Optional[Dict[str, Any]]:
    if not surface_text or absolute_slice is None:
        return None
    probe = _mwt_probe_text(child_row)
    if not probe or probe == surface_text:
        return None
    return {
        "text": surface_text,
        "slice": [int(absolute_slice[0]), int(absolute_slice[1])],
    }


def _flatten_lookup_sentence_tokens(sent_tokens: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool, int]:
    flat_tokens: List[Dict[str, Any]] = []
    saw_mwt = False
    expanded_token_count = 0

    for tok in sent_tokens:
        if not isinstance(tok, dict):
            continue

        expanded = tok.get("expanded")
        is_mwt_parent = bool(_is_lookup_int_pair(tok.get("id")) and isinstance(expanded, list) and expanded)
        if not is_mwt_parent:
            flat_row = dict(tok)
            flat_row.pop("expanded", None)
            flat_row.pop("mwt_subword_edges", None)
            flat_row.pop("mwt_expanded_words", None)
            flat_row.pop("mwt_expanded_texts", None)
            flat_row.pop("mwt_head_part_index", None)
            flat_tokens.append(flat_row)
            continue

        saw_mwt = True
        expanded_rows = [dict(child or {}) for child in (expanded or [])]
        expanded_token_count += len(expanded_rows)

        parent_text = str(tok.get("text", "") or "")
        parent_span = _normalize_lookup_span(tok.get("span"))
        parent_dspan = _normalize_lookup_span(tok.get("dspan"))
        parent_id = tok.get("id")
        child_id_start = _lookup_to_int(parent_id[0], None) if _is_lookup_int_pair(parent_id) else None

        realign_parts: List[Dict[str, Any]] = []
        for ci, child_row in enumerate(expanded_rows):
            if child_row.get("id") is None and child_id_start is not None:
                child_row["id"] = child_id_start + ci
            realign_parts.append({
                "part_index": ci,
                "text": str(child_row.get("text", "") or ""),
                "lemma": str(child_row.get("lemma", "") or ""),
            })

        if realign_parts:
            _realign_mwt_children(realign_parts, parent_text)

        for ci, child_row in enumerate(expanded_rows):
            flat_row = dict(child_row)
            flat_row.pop("expanded", None)
            flat_row.pop("mwt_subword_edges", None)
            flat_row.pop("mwt_expanded_words", None)
            flat_row.pop("mwt_expanded_texts", None)
            flat_row.pop("mwt_head_part_index", None)

            rel_slice_raw = realign_parts[ci].get("surface_slice") if ci < len(realign_parts) else None
            rel_slice = _normalize_lookup_span(rel_slice_raw) or [0, 0]
            rel_start = max(0, rel_slice[0])
            rel_end = max(rel_start, rel_slice[1])
            if rel_end > len(parent_text):
                rel_end = len(parent_text)
            if rel_start > len(parent_text):
                rel_start = len(parent_text)
            surface_text = parent_text[rel_start:rel_end]

            abs_span = _absolute_span_from_parent_slice(parent_span, [rel_start, rel_end])
            abs_dspan = _absolute_span_from_parent_slice(parent_dspan, [rel_start, rel_end])

            if abs_span is not None:
                flat_row["span"] = abs_span
            else:
                existing_span = _normalize_lookup_span(flat_row.get("span"))
                if existing_span is not None:
                    flat_row["span"] = existing_span

            if abs_dspan is not None:
                flat_row["dspan"] = abs_dspan
            else:
                existing_dspan = _normalize_lookup_span(flat_row.get("dspan"))
                if existing_dspan is not None:
                    flat_row["dspan"] = existing_dspan

            surface_anchor = _build_surface_anchor_payload(
                flat_row,
                surface_text,
                abs_dspan or abs_span,
            )
            if surface_anchor is not None:
                flat_row["surface_anchor"] = surface_anchor
            else:
                flat_row.pop("surface_anchor", None)

            flat_tokens.append(flat_row)

    return flat_tokens, saw_mwt, expanded_token_count


def _flatten_lookup_trankit_doc(
    doc: Dict[str, Any],
    trankit_lang: str = "",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    lang_key = str(trankit_lang or "").strip().lower().replace("_", "-")
    meta = {
        "applied": False,
        "supports_mwt": bool(language_supports_mwt(lang_key)),
        "language": lang_key,
        "expanded_token_count": 0,
        "surface_token_count": 0,
    }

    if not isinstance(doc, dict):
        return doc, meta

    sentences = doc.get("sentences")
    if not isinstance(sentences, list) or not sentences:
        return doc, meta

    out_doc = dict(doc)
    out_sentences = []
    saw_mwt = False
    expanded_token_count = 0
    surface_token_count = 0

    for sent in sentences:
        if not isinstance(sent, dict):
            out_sentences.append(sent)
            continue
        sent_tokens = sent.get("tokens", [])
        if not isinstance(sent_tokens, list):
            sent_tokens = []
        surface_token_count += len(sent_tokens)
        flat_tokens, sent_had_mwt, sent_expanded_count = _flatten_lookup_sentence_tokens(sent_tokens)
        saw_mwt = saw_mwt or sent_had_mwt
        expanded_token_count += sent_expanded_count
        sent_out = dict(sent)
        sent_out["tokens"] = flat_tokens
        out_sentences.append(sent_out)

    out_doc["sentences"] = out_sentences
    meta["applied"] = saw_mwt
    meta["expanded_token_count"] = expanded_token_count
    meta["surface_token_count"] = surface_token_count
    return out_doc, meta


# ---------------------------------------------------------------------------
# Sense formatting helpers
# ---------------------------------------------------------------------------

def _stringify_ud_feats(raw_feats: Any) -> str:
    """Normalize Trankit feats payload to a compact display string."""
    if raw_feats is None:
        return ""
    if isinstance(raw_feats, str):
        return raw_feats.strip()
    if isinstance(raw_feats, dict):
        parts = []
        for k, v in raw_feats.items():
            key = str(k).strip()
            val = str(v).strip()
            if not key and not val:
                continue
            parts.append(f"{key}={val}" if key else val)
        return "|".join(parts)
    if isinstance(raw_feats, (list, tuple, set)):
        parts = [str(x).strip() for x in raw_feats if str(x).strip()]
        return "|".join(parts)
    return str(raw_feats).strip()


def merge_all_entries(
    head: str,
    entries: list,
    surface_form: Optional[str] = None,
    lemma_form: Optional[str] = None,
) -> list:
    """Merge senses from multiple dictionary entries sharing a headword.

    Handles two formats:
      - Flat senses (Chinese/CEDICT): entry["senses"] is a list of strings.
      - Structured senses (Japanese/JMdict): entry["senses"] is a list of dicts
        with keys: glosses, pos, misc, s_inf, field, stagk, stagr, xref, ant,
        dial, lsource.
    """
    formatted: list = []
    for entry in entries:
        roman = entry.get("pinyin", "") or entry.get("reading", "") or ""
        pos = entry.get("pos", "")
        senses = entry.get("senses", [])
        # Detect structured senses (list of dicts vs list of strings)
        if senses and isinstance(senses[0], dict):
            # Keep per-entry orthography header for merged JMdict entries.
            entry_head = _build_entry_spellings_head(entry)
            if entry_head:
                formatted.append(f"\x1E{entry_head}")
            # Senses follow without head/roman (header is separate)
            formatted.extend(_format_structured_senses(senses))
        else:
            # For flat sense dictionaries, show each entry under its own
            # headword so surface-form + inflection-derived lemma entries
            # remain distinguishable in merged output.
            entry_head = str(entry.get("headword", "") or head)
            formatted.extend(format_senses(entry_head, roman, senses, pos=pos))
    return _dedupe_merged_sense_lines(formatted)


def _dedupe_merged_sense_lines(lines: List[str]) -> List[str]:
    """Drop repeated sense lines while preserving order and section headers."""
    out: List[str] = []
    seen_lines: set = set()
    for raw in lines:
        line = str(raw or "")
        if not line:
            continue
        # Keep explicit section headers so grouped displays remain intact.
        if line.startswith("\x1E"):
            out.append(line)
            continue
        if line in seen_lines:
            continue
        seen_lines.add(line)
        out.append(line)
    return out


def _split_entries_for_hover(
    entries: List[Dict[str, Any]],
    upos: str,
    dictionary,
    hooks: LanguageHooks,
    xpos: str = "",
    **filter_kwargs: Any,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (primary_entries, alternate_entries) for hover display.

    The hook may return either:
      - A tuple ``(primary, other)`` (sense-level filtering), or
      - A flat list of matching entries (legacy entry-level filtering).

    When a hook returns no split signal (both buckets empty), the full entry
    list is kept in primary so the user still sees fallback content.
    """
    base_entries = list(entries or [])
    if not base_entries or not hooks.filter_entries_for_upos:
        return base_entries, []

    call_kwargs: Dict[str, Any] = dict(filter_kwargs or {})
    if xpos and "xpos" not in call_kwargs:
        call_kwargs["xpos"] = xpos

    try:
        result = hooks.filter_entries_for_upos(
            base_entries, upos, dictionary, **call_kwargs
        )
    except TypeError:
        # Hook may not accept extra kwargs/xpos — degrade gracefully.
        try:
            minimal_kwargs = dict(call_kwargs)
            minimal_kwargs.pop("xpos", None)
            if minimal_kwargs:
                result = hooks.filter_entries_for_upos(
                    base_entries, upos, dictionary, **minimal_kwargs
                )
            else:
                raise TypeError()
        except TypeError:
            try:
                result = hooks.filter_entries_for_upos(base_entries, upos, dictionary)
            except Exception:
                return base_entries, []
        except Exception:
            return base_entries, []
    except Exception:
        return base_entries, []

    # Tuple return — sense-level split already done by the hook.
    if isinstance(result, tuple) and len(result) == 2:
        primary, alternate = result
        if not primary and not alternate:
            # No signal from hook — keep everything visible.
            return base_entries, []
        return primary, alternate

    # Legacy: flat list of matching entries.
    filtered = list(result or [])
    if not filtered:
        return base_entries, []

    filtered_ids = {id(e) for e in filtered}
    if len(filtered_ids) >= len(base_entries):
        return filtered, []

    alternate = [e for e in base_entries if id(e) not in filtered_ids]
    return filtered, alternate


def _build_entry_spellings_head(entry: dict) -> str:
    """Build a headword string listing all kanji and kana spellings.

    Format: kanji1・kanji2【reading1・reading2】
    If no kanji forms: reading1・reading2
    """
    kanji_forms = entry.get("kanji", []) or []
    readings = entry.get("readings", []) or []

    if kanji_forms:
        header = "・".join(kanji_forms)
        if readings:
            header += "【" + "・".join(readings) + "】"
        return header
    return "・".join(readings) if readings else ""


_META_NF_RE = re.compile(r"^nf(\d+)$")
_META_PRI_TAG_PERCENT = {
    "ichi1": 80.0,
    "news1": 70.0,
    "ichi2": 50.0,
    "gai1": 50.0,
    "news2": 40.0,
    "gai2": 25.0,
}


def _compute_meta_spec_tag(tags: Any) -> str:
    raw_tags: List[str] = []
    if isinstance(tags, (list, tuple, set)):
        for tag in tags:
            txt = str(tag or "").strip()
            if txt:
                raw_tags.append(txt)
    else:
        txt = str(tags or "").strip()
        if txt:
            raw_tags.append(txt)
    tag_set = set(raw_tags)
    if "spec1" in tag_set:
        return "spec1"
    if "spec2" in tag_set:
        return "spec2"
    return ""


def _meta_nf_percent(nf_band: int) -> float:
    band = max(1, min(48, int(nf_band)))
    pct = ((49 - band) / 48.0) * 100.0
    if pct < 0.0:
        return 0.0
    if pct > 100.0:
        return 100.0
    return pct


def _compute_meta_pri_score_details(tags: Any) -> Tuple[float, str]:
    """Return (score_pct, basis_tag) using form-only frequency rules."""
    raw_tags: List[str] = []
    if isinstance(tags, (list, tuple, set)):
        for tag in tags:
            txt = str(tag or "").strip()
            if txt:
                raw_tags.append(txt)
    else:
        txt = str(tags or "").strip()
        if txt:
            raw_tags.append(txt)

    best_nf: Optional[int] = None
    for tag in raw_tags:
        m = _META_NF_RE.match(tag)
        if not m:
            continue
        try:
            nf_band = int(m.group(1))
        except Exception:
            continue
        if best_nf is None or nf_band < best_nf:
            best_nf = nf_band
    if best_nf is not None:
        return _meta_nf_percent(best_nf), f"nf{best_nf:02d}"

    best_score = 0.0
    best_tag = ""
    for tag in raw_tags:
        pct = _META_PRI_TAG_PERCENT.get(tag)
        if pct is None:
            continue
        if pct > best_score:
            best_score = pct
            best_tag = tag
    if best_score < 0.0:
        best_score = 0.0
    if best_score > 100.0:
        best_score = 100.0
    return best_score, best_tag


def _compute_meta_pri_score(tags: Any) -> float:
    return _compute_meta_pri_score_details(tags)[0]


def _list_texts(raw: Any) -> List[str]:
    out: List[str] = []
    if isinstance(raw, (list, tuple, set)):
        for item in raw:
            txt = str(item or "").strip()
            if txt:
                out.append(txt)
    else:
        txt = str(raw or "").strip()
        if txt:
            out.append(txt)
    return out


def _build_jmdict_forms_meta_bundle(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Build per-form JMdict metadata for kanji/reading hover chips."""
    if not isinstance(entry, dict):
        return {}

    kanji_info = entry.get("kanji_info", {}) or {}
    kanji_pri = entry.get("kanji_pri", {}) or {}
    reading_info = entry.get("reading_info", {}) or {}
    reading_pri = entry.get("reading_pri", {}) or {}
    reading_restr = entry.get("reading_restr", {}) or {}
    reading_nokanji = entry.get("reading_nokanji", {}) or {}

    kanji_rows: List[Dict[str, Any]] = []
    kanji_by_form: Dict[str, Dict[str, Any]] = {}
    for form in _list_texts(entry.get("kanji", [])):
        pri_tags = _list_texts(kanji_pri.get(form, []))
        info_tags = _list_texts(kanji_info.get(form, []))
        pri_score, pri_basis_tag = _compute_meta_pri_score_details(pri_tags)
        spec_tag = _compute_meta_spec_tag(pri_tags)
        row = {
            "form": form,
            "kind": "kanji",
            "info_tags": info_tags,
            "priority_tags": pri_tags,
            "priority_score": pri_score,
            "priority_basis_tag": pri_basis_tag,
            "spec_priority_tag": spec_tag,
        }
        kanji_rows.append(row)
        kanji_by_form[form] = dict(row)

    reading_rows: List[Dict[str, Any]] = []
    reading_by_form: Dict[str, Dict[str, Any]] = {}
    for form in _list_texts(entry.get("readings", [])):
        pri_tags = _list_texts(reading_pri.get(form, []))
        info_tags = _list_texts(reading_info.get(form, []))
        restricted = _list_texts(reading_restr.get(form, []))
        no_kanji = bool(reading_nokanji.get(form, False))
        pri_score, pri_basis_tag = _compute_meta_pri_score_details(pri_tags)
        spec_tag = _compute_meta_spec_tag(pri_tags)
        row = {
            "form": form,
            "kind": "reading",
            "info_tags": info_tags,
            "priority_tags": pri_tags,
            "priority_score": pri_score,
            "priority_basis_tag": pri_basis_tag,
            "spec_priority_tag": spec_tag,
            "no_kanji": no_kanji,
            "restricted_to_kanji": restricted,
            "is_restricted": bool(restricted),
        }
        reading_rows.append(row)
        reading_by_form[form] = dict(row)

    return {
        "kanji": kanji_rows,
        "readings": reading_rows,
        "kanji_by_form": kanji_by_form,
        "readings_by_form": reading_by_form,
    }


def _build_jmdict_forms_meta_by_header(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map 'kanji【reading】' headers -> per-form metadata bundle."""
    out: Dict[str, Dict[str, Any]] = {}
    for entry in list(entries or []):
        if not isinstance(entry, dict):
            continue
        header = _build_entry_spellings_head(entry)
        if not header or header in out:
            continue
        bundle = _build_jmdict_forms_meta_bundle(entry)
        if not bundle:
            continue
        bundle["header"] = header
        out[header] = bundle
    return out


def format_senses(head: str, roman: str, raw_senses: list, pos: str = "") -> list:
    """
    Format raw definition strings into tab-delimited format for the frontend.

    First line:  headword\\troman\\tpos\\tsense_text
    Subsequent:  \\t\\t\\tsense_text
    """
    if not raw_senses:
        return []
    formatted = []
    for i, sense in enumerate(raw_senses):
        if i == 0:
            formatted.append(f"{head}\t{roman}\t{pos}\t{sense}")
        else:
            formatted.append(f"\t\t\t{sense}")
    return formatted


def _format_structured_senses(senses: list) -> list:
    """Format structured JMdict senses into tab-delimited lines.

    The forms header is emitted separately by the caller as a ``\\x1E``
    prefixed line.  This function only produces the sense lines:

      - ``\\t\\tpos\\tsense_line``   (first sense or new POS group)
      - ``\\tsense_line``            (continuation sense, same POS)

    s_inf notes are appended inline using ``\\x1F`` as a delimiter so the
    frontend can style them with a different colour.

    Misc tags shared by ALL senses appear once at the end.
    """
    if not senses:
        return []

    # ---- Pre-pass: find misc notes shared by every sense ----
    dict_senses = [s for s in senses if isinstance(s, dict) and s.get("glosses")]
    if dict_senses:
        common_misc = set(dict_senses[0].get("misc", []))
        for s in dict_senses[1:]:
            common_misc &= set(s.get("misc", []))
    else:
        common_misc = set()

    formatted: list = []
    prev_pos_key = ""

    for sense in senses:
        if not isinstance(sense, dict):
            formatted.append(f"\t{sense}")
            continue

        glosses = sense.get("glosses", [])
        if not glosses:
            continue

        pos_list = sense.get("pos", [])
        misc = sense.get("misc", [])
        s_inf = sense.get("s_inf", "")
        field = sense.get("field", [])
        stagk = sense.get("stagk", [])
        stagr = sense.get("stagr", [])
        xref = sense.get("xref", [])
        ant = sense.get("ant", [])
        dial = sense.get("dial", [])
        lsource = sense.get("lsource", [])

        # Build POS label — join all POS tags for this sense
        if pos_list:
            pos_parts = []
            for p in pos_list:
                if not p:
                    continue
                part = _abbreviate_pos(p)
                part = " ".join(str(part).split()).strip().strip(",")
                if part:
                    pos_parts.append(part)
            pos_label = ", ".join(pos_parts)
        else:
            pos_label = ""
        pos_key = "|".join(pos_list)

        # --- Build the single sense line ---
        # Join all glosses from this sense block with "; "
        sense_text = "; ".join(glosses)

        # Annotations: only show misc tags unique to this sense
        annotations = []
        unique_misc = [m for m in misc if m not in common_misc]
        if unique_misc:
            annotations.extend(unique_misc)
        if field:
            annotations.extend(field)
        if dial:
            annotations.extend(dial)
        if stagk:
            annotations.append("kanji: " + ", ".join(stagk))
        if stagr:
            annotations.append("reading: " + ", ".join(stagr))
        if lsource:
            annotations.append("source: " + ", ".join(lsource))
        if annotations:
            sense_text += " [" + "; ".join(annotations) + "]"

        # Cross-references
        if xref:
            sense_text += " [cf. " + ", ".join(xref) + "]"
        if ant:
            sense_text += " [ant. " + ", ".join(ant) + "]"

        # s_inf inline with \x1F delimiter for frontend colour styling
        if s_inf:
            sense_text += f"\x1F({s_inf})"

        # Emit the line — first sense or new POS group gets POS label
        if not formatted or (pos_key != prev_pos_key and pos_label):
            formatted.append(f"\t\t{pos_label}\t{sense_text}")
        else:
            formatted.append(f"\t{sense_text}")

        if pos_key:
            prev_pos_key = pos_key

    # ---- Append shared misc notes once at the end ----
    if common_misc:
        misc_text = "; ".join(sorted(common_misc))
        formatted.append(f"\t[{misc_text}]")

    return formatted


# Abbreviation map for common JMdict POS labels
_POS_ABBREV = {
    "noun (common) (futsuumeishi)": "n",
    "noun or verb acting prenominally": "adj-f",
    "nouns which may take the genitive case particle `no'": "n-no",
    "adverbial noun (fukushitekimeishi)": "n-adv",
    "noun, used as a suffix": "n-suf",
    "noun, used as a prefix": "n-pref",
    "noun (temporal) (jisoumeishi)": "n-t",
    "Ichidan verb": "v1",
    "Godan verb with `u' ending": "v5u",
    "Godan verb with `ku' ending": "v5k",
    "Godan verb with `su' ending": "v5s",
    "Godan verb with `tsu' ending": "v5t",
    "Godan verb with `nu' ending": "v5n",
    "Godan verb with `bu' ending": "v5b",
    "Godan verb with `mu' ending": "v5m",
    "Godan verb with `ru' ending": "v5r",
    "Godan verb with `gu' ending": "v5g",
    "Godan verb - Iku/Yuku special class": "v5k-s",
    "Kuru verb - special class": "vk",
    "suru verb - included": "vs-i",
    "suru verb - special class": "vs-s",
    "su verb - precursor to the modern suru": "vs-c",
    "intransitive verb": "vi",
    "transitive verb": "vt",
    "adjective (keiyoushi)": "adj-i",
    "adjectival nouns or quasi-adjectives (keiyodoshi)": "adj-na",
    "pre-noun adjectival (rentaishi)": "adj-pn",
    "`taru' adjective": "adj-t",
    "noun or participle which takes the aux. verb suru": "vs",
    "adverb (fukushi)": "adv",
    "adverb taking the `to' particle": "adv-to",
    "auxiliary verb": "aux-v",
    "auxiliary adjective": "aux-adj",
    "conjunction": "conj",
    "counter": "ctr",
    "expressions (phrases, clauses, etc.)": "exp",
    "interjection (kandoushi)": "int",
    "pronoun": "pn",
    "prefix": "pref",
    "suffix": "suf",
    "particle": "prt",
    "numeric": "num",
    "copula": "cop",
    "auxiliary": "aux",
    "unclassified": "unc",
}


def _abbreviate_pos(pos_text: str) -> str:
    """Abbreviate a JMdict POS string to a short label."""
    if not pos_text:
        return ""
    lower = pos_text.lower().strip()
    # Check exact match first
    if lower in _POS_ABBREV:
        return _POS_ABBREV[lower]
    # Check case-insensitive match
    for full, abbr in _POS_ABBREV.items():
        if full.lower() == lower:
            return abbr
    # Fallback: use first 6 chars, normalized
    fallback = pos_text.strip()
    if len(fallback) > 6:
        fallback = fallback[:6]
    return fallback.strip().strip(",")


def is_unknown_fill_entry(obj: Dict[str, Any]) -> bool:
    if not isinstance(obj, dict):
        return True
    pos = str(obj.get("pos", "") or "").lower()
    if "unknown" in pos:
        return True
    senses = list(obj.get("senses", []) or [])
    if not senses:
        return True
    if len(senses) == 1:
        first = str(senses[0] or "").lower()
        if "no dictionary entry" in first:
            return True
    return False


# ---------------------------------------------------------------------------
# UD overlay builder (fully generic)
# ---------------------------------------------------------------------------

def build_ud_overlay(
    sentences_data: List[Dict],
    segments: List[str],
    global_offset_by_sent_tok: Dict,
) -> Dict[str, Any]:
    """Convert Trankit sentence/token output into ud_overlay format."""
    tokens_out = []
    edges_out = []
    roots = []
    ents_out = []
    sentences_out = []
    n = len(segments)
    doc2seg = list(range(n))
    seg2doc = list(range(n))
    token_entry_by_global: Dict[int, Dict[str, Any]] = {}
    token_surface_slice_by_global: Dict[int, List[int]] = {}

    for sent_idx, sent in enumerate(sentences_data):
        sent_tokens = sent.get("tokens", [])
        if not sent_tokens:
            continue

        first_global = global_offset_by_sent_tok.get((sent_idx, 0))
        last_global = global_offset_by_sent_tok.get((sent_idx, len(sent_tokens) - 1))
        if first_global is not None and last_global is not None:
            sentences_out.append([first_global, last_global + 1])

        for tok_idx, tok in enumerate(sent_tokens):
            global_idx = global_offset_by_sent_tok.get((sent_idx, tok_idx))
            if global_idx is None:
                continue

            raw_token_slice = _normalize_lookup_span(tok.get("dspan")) or _normalize_lookup_span(tok.get("span"))
            if raw_token_slice is not None:
                token_surface_slice_by_global[global_idx] = raw_token_slice

            upos = tok.get("upos", "X")
            xpos = tok.get("xpos", "")
            deprel = tok.get("deprel", "dep")
            lemma = str(tok.get("lemma", "") or "")
            feats = _stringify_ud_feats(tok.get("feats"))
            head_in_sent = tok.get("head", 0)

            is_mwt = bool(tok.get("mwt_subword_edges"))
            if head_in_sent == 0 or deprel.upper() == "ROOT":
                head_global = global_idx
                roots.append(global_idx)
                if not is_mwt:
                    deprel = "ROOT"
            else:
                head_tok_idx = head_in_sent - 1
                head_global = global_offset_by_sent_tok.get(
                    (sent_idx, head_tok_idx), global_idx
                )

            subword_edges = tok.get("mwt_subword_edges")
            if subword_edges:
                # MWT token: preserve ordered part metadata and emit every
                # subword edge, including same-surface part-to-part links.
                mwt_heads = []
                mwt_parts = []
                expanded_rows = tok.get("mwt_expanded_words")
                if isinstance(expanded_rows, list):
                    parent_surface_text = str(tok.get("text", "") or "")
                    collected_parts = []
                    for part_idx, part_row in enumerate(expanded_rows):
                        part = part_row if isinstance(part_row, dict) else {}
                        collected_parts.append({
                            "part_index": int(part_idx),
                            "text": str(part.get("text", "") or ""),
                            "lemma": str(part.get("lemma", "") or ""),
                            "upos": str(part.get("upos", "X") or "X"),
                            "tag": str(part.get("xpos", "") or ""),
                            "dep": str(part.get("deprel", "dep") or "dep"),
                        })
                    # Realign MWT children onto the parent surface.
                    # Trankit supplies NO child spans — the realigner is
                    # authoritative. Run it unconditionally; the trivial-
                    # equality fast path handles non-sandhi MWT (des=de+les).
                    if collected_parts:
                        _realign_mwt_children(collected_parts, parent_surface_text)
                        # Propagate realigner output back onto the original
                        # mwt_expanded_words rows. surface_slice is always
                        # written (authoritative anchor). _realign_pass is
                        # debug-only and only attached when debug collection
                        # is enabled, so the payload stays clean in prod.
                        _debug_on = False
                        try:
                            from debug_store import is_debug_collection_enabled as _is_dbg
                            _debug_on = bool(_is_dbg())
                        except Exception:
                            _debug_on = False
                        for _cp in collected_parts:
                            _pi = _cp.get("part_index")
                            if isinstance(_pi, int) and 0 <= _pi < len(expanded_rows):
                                _raw = expanded_rows[_pi]
                                if isinstance(_raw, dict):
                                    _raw["surface_slice"] = _cp.get("surface_slice")
                                    if _debug_on:
                                        _raw["_realign_pass"] = _cp.get("_realign_pass")
                            if not _debug_on and "_realign_pass" in _cp:
                                _cp.pop("_realign_pass", None)
                    mwt_parts.extend(collected_parts)
                for sw_edge in subword_edges:
                    sw_head_sent = sw_edge.get("head", 0)
                    sw_part_idx = sw_edge.get("part_index")
                    sw_head_part_idx = sw_edge.get("head_part_index")
                    try:
                        sw_part_idx = int(sw_part_idx)
                    except (TypeError, ValueError):
                        sw_part_idx = None
                    try:
                        sw_head_part_idx = int(sw_head_part_idx)
                    except (TypeError, ValueError):
                        sw_head_part_idx = None
                    if sw_head_sent == 0:
                        continue
                    sw_head_global = global_offset_by_sent_tok.get(
                        (sent_idx, sw_head_sent - 1), None
                    )
                    if sw_head_global is None:
                        continue
                    if sw_head_global == global_idx and (
                        sw_head_part_idx is None or sw_head_part_idx == sw_part_idx
                    ):
                        continue
                    if sw_head_global != global_idx and sw_head_global not in mwt_heads:
                        mwt_heads.append(sw_head_global)
                    edge_entry = {
                        "from": sw_head_global,
                        "to": global_idx,
                        "dep": sw_edge.get("deprel", "dep"),
                        "upos": sw_edge.get("upos", upos),
                    }
                    if sw_head_part_idx is not None:
                        edge_entry["from_part"] = sw_head_part_idx
                    if sw_part_idx is not None:
                        edge_entry["to_part"] = sw_part_idx
                    edges_out.append(edge_entry)

                token_entry = {
                    "i": global_idx,
                    "doc_i": global_idx,
                    "text": tok.get("text", segments[global_idx] if global_idx < n else ""),
                    "upos": upos,
                    "tag": xpos,
                    "dep": deprel,
                    "lemma": lemma,
                    "feats": feats,
                    "heads": mwt_heads,
                }
                if mwt_parts:
                    token_entry["mwt_parts"] = mwt_parts
            else:
                token_entry = {
                    "i": global_idx,
                    "doc_i": global_idx,
                    "text": tok.get("text", segments[global_idx] if global_idx < n else ""),
                    "upos": upos,
                    "tag": xpos,
                    "dep": deprel,
                    "lemma": lemma,
                    "feats": feats,
                    "head": head_global,
                }
                # Normal (non-MWT) token: single edge
                if deprel != "ROOT" and head_global != global_idx:
                    edge_entry = {
                        "from": head_global,
                        "to": global_idx,
                        "dep": deprel,
                        "upos": upos,
                    }
                    head_part_idx = tok.get("mwt_head_part_index")
                    try:
                        head_part_idx = int(head_part_idx)
                    except (TypeError, ValueError):
                        head_part_idx = None
                    if head_part_idx is not None:
                        edge_entry["from_part"] = head_part_idx
                    edges_out.append(edge_entry)
                surface_anchor = tok.get("surface_anchor")
                if isinstance(surface_anchor, dict):
                    raw_slice = surface_anchor.get("slice")
                    if isinstance(raw_slice, (list, tuple)) and len(raw_slice) >= 2:
                        sa_start = _lookup_to_int(raw_slice[0], None)
                        sa_end = _lookup_to_int(raw_slice[1], None)
                        if sa_start is not None and sa_end is not None and sa_end >= sa_start:
                            token_entry["surface_anchor"] = {
                                "text": str(surface_anchor.get("text", "") or ""),
                                "slice": [sa_start, sa_end],
                            }
            tokens_out.append(token_entry)
            token_entry_by_global[global_idx] = token_entry

    # NER: consolidate token-level BIO/BILOU tags into spans
    current_ent_start = None
    current_ent_label = None
    current_ent_tokens = []

    for sent_idx, sent in enumerate(sentences_data):
        sent_tokens = sent.get("tokens", [])
        for tok_idx, tok in enumerate(sent_tokens):
            global_idx = global_offset_by_sent_tok.get((sent_idx, tok_idx))
            if global_idx is None:
                continue

            ner_tag = tok.get("ner", "O")
            if ner_tag == "O":
                if current_ent_start is not None:
                    ents_out.append({
                        "start": current_ent_start,
                        "end": global_idx,
                        "label": current_ent_label,
                        "text": "".join(current_ent_tokens),
                    })
                    current_ent_start = None
                    current_ent_label = None
                    current_ent_tokens = []
            elif ner_tag.startswith("B-"):
                if current_ent_start is not None:
                    ents_out.append({
                        "start": current_ent_start,
                        "end": global_idx,
                        "label": current_ent_label,
                        "text": "".join(current_ent_tokens),
                    })
                current_ent_label = ner_tag[2:]
                current_ent_start = global_idx
                current_ent_tokens = [tok.get("text", "")]
            elif ner_tag.startswith("I-"):
                label = ner_tag[2:]
                if current_ent_start is not None and label == current_ent_label:
                    current_ent_tokens.append(tok.get("text", ""))
                else:
                    if current_ent_start is not None:
                        ents_out.append({
                            "start": current_ent_start,
                            "end": global_idx,
                            "label": current_ent_label,
                            "text": "".join(current_ent_tokens),
                        })
                    current_ent_label = label
                    current_ent_start = global_idx
                    current_ent_tokens = [tok.get("text", "")]
            elif ner_tag.startswith("S-"):
                if current_ent_start is not None:
                    ents_out.append({
                        "start": current_ent_start,
                        "end": global_idx,
                        "label": current_ent_label,
                        "text": "".join(current_ent_tokens),
                    })
                    current_ent_start = None
                    current_ent_label = None
                    current_ent_tokens = []
                ents_out.append({
                    "start": global_idx,
                    "end": global_idx + 1,
                    "label": ner_tag[2:],
                    "text": tok.get("text", ""),
                })
            elif ner_tag.startswith("E-"):
                label = ner_tag[2:]
                if current_ent_start is not None and label == current_ent_label:
                    current_ent_tokens.append(tok.get("text", ""))
                    ents_out.append({
                        "start": current_ent_start,
                        "end": global_idx + 1,
                        "label": current_ent_label,
                        "text": "".join(current_ent_tokens),
                    })
                else:
                    if current_ent_start is not None:
                        ents_out.append({
                            "start": current_ent_start,
                            "end": global_idx,
                            "label": current_ent_label,
                            "text": "".join(current_ent_tokens),
                        })
                    ents_out.append({
                        "start": global_idx,
                        "end": global_idx + 1,
                        "label": label,
                        "text": tok.get("text", ""),
                    })
                current_ent_start = None
                current_ent_label = None
                current_ent_tokens = []

    if current_ent_start is not None:
        ents_out.append({
            "start": current_ent_start,
            "end": n,
            "label": current_ent_label,
            "text": "".join(current_ent_tokens),
        })

    for ent in ents_out:
        if not isinstance(ent, dict):
            continue
        start = _lookup_to_int(ent.get("start"), None)
        end = _lookup_to_int(ent.get("end"), None)
        if start is None or end is None or end <= start:
            continue
        anchors = []
        for global_idx in range(start, end):
            token_entry = token_entry_by_global.get(global_idx) or {}
            surface_anchor = token_entry.get("surface_anchor")
            if isinstance(surface_anchor, dict):
                raw_slice = surface_anchor.get("slice")
                if isinstance(raw_slice, (list, tuple)) and len(raw_slice) >= 2:
                    sa_start = _lookup_to_int(raw_slice[0], None)
                    sa_end = _lookup_to_int(raw_slice[1], None)
                    if sa_start is not None and sa_end is not None and sa_end >= sa_start:
                        anchors.append({
                            "token_i": global_idx,
                            "text": str(surface_anchor.get("text", "") or ""),
                            "slice": [sa_start, sa_end],
                            "source": "surface_anchor",
                        })
                        continue
            raw_slice = token_surface_slice_by_global.get(global_idx)
            if isinstance(raw_slice, (list, tuple)) and len(raw_slice) >= 2:
                sa_start = _lookup_to_int(raw_slice[0], None)
                sa_end = _lookup_to_int(raw_slice[1], None)
                if sa_start is not None and sa_end is not None and sa_end >= sa_start:
                    anchors.append({
                        "token_i": global_idx,
                        "text": str(segments[global_idx] if global_idx < len(segments) else ""),
                        "slice": [sa_start, sa_end],
                        "source": "token_span",
                    })
        if anchors:
            ent["surface_anchors"] = anchors

    return {
        "ok": True,
        "tokens": tokens_out,
        "edges": edges_out,
        "roots": roots,
        "ents": ents_out,
        "sentences": sentences_out,
        "doc2seg": doc2seg,
        "seg2doc": seg2doc,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Generic fill entry preparation
# ---------------------------------------------------------------------------

def prepare_fill_entries(
    fills: List[Dict[str, Any]],
    dictionary,
    hooks: LanguageHooks,
    upos: str = "",
    xpos: str = "",
    fill_mode: str = "",
) -> List[Dict[str, Any]]:
    """Normalize dict_fill entries for hover + side panel display."""
    reading_key = hooks.reading_key
    out = list(fills or [])
    mode = str(fill_mode or "").strip().lower()
    greedy_match_mode = mode in {"greedy", "lemma_greedy", "greedy_lemma_mismatch"}
    known_fill_piece_count = sum(
        1
        for piece in out
        if str((piece or {}).get("source", "") or "").upper() != "UNKNOWN"
    )
    greedy_multi_fill = (
        mode in {"greedy", "lemma_greedy"}
        and known_fill_piece_count > 1
    )
    for f in out:
        fill_head = str(f.get("head", "") or "")
        fill_text = str(f.get("text", "") or "")
        display_head = fill_text or fill_head
        lookup_head = fill_head or display_head
        if display_head:
            f["head"] = display_head
        fill_xpos_hint = str(f.get("_xpos_hint", "") or "")
        # Use pre-stored entries if available (Korean greedy/exact match),
        # otherwise fall back to lookup by headword.
        fill_entries = f.get("entries") or dictionary.lookup_all(lookup_head)

        def _entries_with_display_head(
            rows: List[Dict[str, Any]],
        ) -> List[Dict[str, Any]]:
            if not display_head:
                return list(rows or [])
            shown: List[Dict[str, Any]] = []
            for row in list(rows or []):
                if not isinstance(row, dict):
                    continue
                headword = str(row.get("headword", "") or "")
                if headword == display_head:
                    shown.append(row)
                    continue
                row_copy = dict(row)
                row_copy["headword"] = display_head
                shown.append(row_copy)
            return shown

        full_forms_meta_by_header: Dict[str, Dict[str, Any]] = {}
        hover_forms_meta_by_header: Dict[str, Dict[str, Any]] = {}
        other_forms_meta_by_header: Dict[str, Dict[str, Any]] = {}

        full_senses: List[str] = []
        if fill_entries:
            # Always route through merge_all_entries so structured senses
            # (Japanese/JMdict) get the \x1E header format.
            full_senses = merge_all_entries(
                display_head or lookup_head,
                _entries_with_display_head(fill_entries),
            )
            full_forms_meta_by_header = _build_jmdict_forms_meta_by_header(fill_entries)
        elif f.get("senses"):
            full_senses = format_senses(
                display_head or lookup_head, f.get("roman", ""), f["senses"]
            )
        f["senses"] = full_senses

        if hooks.filter_entries_for_upos:
            hover_senses = list(full_senses)
            other_senses: List[str] = []
            if fill_entries:
                split_kwargs: Dict[str, Any] = {}
                if greedy_match_mode:
                    split_kwargs["greedy_match"] = True
                if greedy_multi_fill:
                    split_kwargs["greedy_multi_fill"] = True
                hover_entries, other_entries = _split_entries_for_hover(
                    fill_entries,
                    upos,
                    dictionary,
                    hooks,
                    xpos=fill_xpos_hint or xpos,
                    **split_kwargs,
                )
                hover_senses = merge_all_entries(
                    display_head or lookup_head,
                    _entries_with_display_head(hover_entries),
                )
                if other_entries:
                    other_senses = merge_all_entries(
                        display_head or lookup_head,
                        _entries_with_display_head(other_entries),
                    )
                hover_forms_meta_by_header = _build_jmdict_forms_meta_by_header(hover_entries)
                if other_entries:
                    other_forms_meta_by_header = _build_jmdict_forms_meta_by_header(other_entries)
                # Build entry_groups_hover / entry_groups_other for structured rendering
                if hooks.attach_forms and hover_entries:
                    hover_tmp: Dict[str, Any] = {}
                    hooks.attach_forms(hover_tmp, display_head or lookup_head, hover_entries)
                    if hover_tmp.get("entry_groups"):
                        f["entry_groups_hover"] = hover_tmp["entry_groups"]
                if hooks.attach_forms and other_entries:
                    other_tmp: Dict[str, Any] = {}
                    hooks.attach_forms(other_tmp, display_head or lookup_head, other_entries)
                    if other_tmp.get("entry_groups"):
                        f["entry_groups_other"] = other_tmp["entry_groups"]
            f["senses_hover"] = hover_senses
            f["senses_hover_other"] = other_senses
            f["hover_has_alt_senses"] = bool(other_senses)
        # Internal hint used only during filtering; don't expose in payload.
        if "_xpos_hint" in f:
            try:
                del f["_xpos_hint"]
            except Exception:
                pass

        if full_forms_meta_by_header:
            f["senses_form_meta_by_header"] = full_forms_meta_by_header
        if hover_forms_meta_by_header:
            f["senses_hover_form_meta_by_header"] = hover_forms_meta_by_header
        if other_forms_meta_by_header:
            f["senses_hover_other_form_meta_by_header"] = other_forms_meta_by_header

        # Pick best entry and extract romanization
        chosen_fill = None
        if hooks.choose_entry:
            chosen_fill = hooks.choose_entry(lookup_head, fill_entries)
        elif fill_entries:
            chosen_fill = fill_entries[0]

        if chosen_fill and not f.get("roman"):
            f["roman"] = chosen_fill.get(reading_key, "") or chosen_fill.get("pinyin", "") or chosen_fill.get("reading", "") or ""

        # Attach language-specific forms
        if hooks.attach_forms:
            hooks.attach_forms(f, display_head or lookup_head, fill_entries)

        # Attach g2p if language supports it
        if hooks.build_g2p:
            f["g2p"] = hooks.build_g2p(
                display_head or lookup_head,
                dictionary,
                fallback_roman=f.get("roman", ""),
            )
        else:
            f["g2p"] = None
    return out


# ---------------------------------------------------------------------------
# POS tag helpers
# ---------------------------------------------------------------------------

def _collect_entry_all_pos(
    preferred_entry: Optional[Dict[str, Any]],
    entries: List[Dict[str, Any]],
) -> List[str]:
    """Collect unique JMdict POS tags from a preferred entry then all entries."""
    out: List[str] = []
    seen = set()

    def _add_one(raw: Any) -> None:
        text = str(raw or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        out.append(text)

    def _add_many(raw: Any) -> None:
        if isinstance(raw, (list, tuple, set)):
            for item in raw:
                _add_one(item)
        else:
            _add_one(raw)

    if preferred_entry:
        _add_many(preferred_entry.get("all_pos", []))
        _add_many(preferred_entry.get("pos", ""))

    for entry in list(entries or []):
        _add_many(entry.get("all_pos", []))

    return out


def _build_sentence_child_index(sent_tokens: List[Dict[str, Any]]) -> Dict[int, List[int]]:
    """Map sentence token index -> list of direct child token indices."""
    children: Dict[int, List[int]] = {}
    for child_idx, child_tok in enumerate(list(sent_tokens or [])):
        head_raw = child_tok.get("head", 0)
        try:
            head_in_sent = int(head_raw or 0)
        except Exception:
            head_in_sent = 0
        if head_in_sent <= 0:
            continue
        head_idx = head_in_sent - 1
        if head_idx < 0:
            continue
        children.setdefault(head_idx, []).append(child_idx)
    return children


def _build_deconjugation_surface_candidates(
    word: str,
    sent_idx: int,
    tok_idx: int,
    segments: List[str],
    global_offset_by_sent_tok: Dict[Any, Any],
    child_index: Dict[int, List[int]],
) -> List[Dict[str, Any]]:
    """Return only the current token as the deconjugation surface candidate."""
    _ = (sent_idx, segments, global_offset_by_sent_tok, child_index)
    base = str(word or "")
    if not base:
        return []
    return [{
        "surface": base,
        "tokens": [base],
        "token_indices": [tok_idx],
    }]


# ---------------------------------------------------------------------------
# Debug helpers (language-agnostic; used by Japanese trace output)
# ---------------------------------------------------------------------------

def _debug_entry_label(entry: Dict[str, Any]) -> str:
    """Build a compact, human-readable label for a dictionary entry."""
    if not isinstance(entry, dict):
        return ""

    kanji = [str(x) for x in (entry.get("kanji", []) or []) if str(x)]
    readings = [str(x) for x in (entry.get("readings", []) or []) if str(x)]

    if kanji and readings:
        return f"{'/'.join(kanji)} [{'/'.join(readings)}]"
    if kanji:
        return "/".join(kanji)
    if readings:
        return "/".join(readings)

    head = str(
        entry.get("headword", "")
        or entry.get("head", "")
        or entry.get("reading", "")
        or ""
    )
    if head:
        return head
    return str(entry.get("text", "") or "")


def _debug_entry_sense_preview(
    entry: Dict[str, Any],
    max_rows: Optional[int] = None,
) -> List[str]:
    """Return gloss rows for a dictionary entry.

    When ``max_rows`` is a positive int, output is capped to that many rows.
    Otherwise all available rows are returned.
    """
    out: List[str] = []
    if not isinstance(entry, dict):
        return out

    limit = int(max_rows) if isinstance(max_rows, int) else None
    if limit is not None and limit <= 0:
        limit = None

    senses_full = list(entry.get("senses_full", []) or [])
    for sense in senses_full:
        if not isinstance(sense, dict):
            continue
        glosses = sense.get("glosses", [])
        if not isinstance(glosses, list):
            continue
        text = "; ".join(str(g or "").strip() for g in glosses if str(g or "").strip())
        if not text:
            continue
        out.append(text)
        if limit is not None and len(out) >= limit:
            return out

    for raw in list(entry.get("senses", []) or []):
        text = str(raw or "").strip()
        if not text:
            continue
        out.append(text)
        if limit is not None and len(out) >= limit:
            break
    return out


def _debug_fill_pieces(fill_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return compact fill-piece rows for debug display."""
    out: List[Dict[str, Any]] = []
    for part in list((fill_obj or {}).get("fills", []) or []):
        if not isinstance(part, dict):
            continue
        src = str(part.get("source", "") or "")
        out.append({
            "text": str(part.get("text", "") or ""),
            "head": str(part.get("head", "") or ""),
            "source": src,
            "known": src.upper() != "UNKNOWN",
        })
    return out


def _build_debug_candidate_rows(
    entries: List[Dict[str, Any]],
    shown_entries: List[Dict[str, Any]],
    filtered_entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Label candidate dictionary entries as shown vs filtered by POS logic."""
    shown_ids = {id(e) for e in list(shown_entries or [])}
    filtered_ids = {id(e) for e in list(filtered_entries or [])}

    rows: List[Dict[str, Any]] = []
    for idx, entry in enumerate(list(entries or [])):
        eid = id(entry)
        if eid in filtered_ids:
            status = "filtered_out"
        elif eid in shown_ids or not shown_ids:
            status = "shown"
        else:
            status = "shown"
        senses_full = list(entry.get("senses_full", []) or [])
        senses_flat = list(entry.get("senses", []) or [])
        rows.append({
            "index": idx,
            "label": _debug_entry_label(entry),
            "headword": str(entry.get("headword", "") or ""),
            "pos": str(entry.get("pos", "") or ""),
            "pos_raw": str(entry.get("pos_raw", "") or ""),
            "han_tu": str(entry.get("han_tu", "") or ""),
            "etym_key": str(entry.get("etym_key", "") or ""),
            "all_pos": list(entry.get("all_pos", []) or []),
            "priority_tags": list(entry.get("pri", []) or []),
            "sense_count": len(senses_full) if senses_full else len(senses_flat),
            "sense_preview": _debug_entry_sense_preview(entry),
            "filter_status": status,
        })
    return rows


def _build_debug_entry_filter_breakdown(
    entries: List[Dict[str, Any]],
    shown_entries: List[Dict[str, Any]],
    filtered_entries: List[Dict[str, Any]],
    dictionary: Any,
    xpos: str,
    upos: str,
) -> Dict[str, Any]:
    """Build a structured per-token entry-filter breakdown for debug UI."""
    base_rows = _build_debug_candidate_rows(entries, shown_entries, filtered_entries)
    payload: Dict[str, Any] = {
        "mode": "xpos" if str(xpos or "").strip() else ("upos" if str(upos or "").strip() else "none"),
        "xpos": str(xpos or ""),
        "upos": str(upos or ""),
        "entry_count": len(list(entries or [])),
        "shown_count": len(list(shown_entries or [])),
        "filtered_count": len(list(filtered_entries or [])),
        "entries": base_rows,
    }

    debug_method = getattr(dictionary, "debug_filter_entries_by_xpos", None)
    if not callable(debug_method):
        return payload

    try:
        custom = debug_method(entries, xpos)
    except Exception as exc:
        payload["debug_error"] = f"{type(exc).__name__}: {exc}"
        return payload

    if not isinstance(custom, dict):
        return payload

    merged = dict(custom)
    merged.setdefault("mode", payload["mode"])
    merged.setdefault("xpos", payload["xpos"])
    merged.setdefault("upos", payload["upos"])
    merged.setdefault("entry_count", payload["entry_count"])
    merged.setdefault("shown_count", payload["shown_count"])
    merged.setdefault("filtered_count", payload["filtered_count"])
    if not isinstance(merged.get("entries"), list):
        merged["entries"] = base_rows
    return merged


def _classify_fill_strategy(fill_mode: str) -> str:
    """Normalize low-level fill mode into user-facing match path labels."""
    mode = str(fill_mode or "").strip().lower()
    if mode == "exact":
        return "exact_surface"
    if mode == "lemma":
        return "exact_lemma"
    if mode == "lemma_greedy":
        return "greedy_longest_lemma"
    if mode == "greedy":
        return "greedy_longest_surface"
    if mode == "mwt_expanded":
        return "mwt_expanded"
    return mode or "unknown"


def _normalize_component_text(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    # Keep normalization conservative so we don't over-match unrelated forms.
    text = text.replace(" ", "")
    text = text.lstrip("-").rstrip("-")
    return text


def _split_compound_tags(raw: Any) -> List[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split("+") if part.strip()]


def _derive_fill_piece_xpos_hints(
    fills: List[Dict[str, Any]],
    lemma: str,
    xpos: str,
) -> List[Dict[str, Any]]:
    """Attach per-fill ``_xpos_hint`` values when lemma/XPOS are compound.

    For agglutinative analyses (e.g. ``lemma='그것+은'``, ``xpos='npd+jxt'``),
    each fill piece should be filtered with the XPOS tags of the lemma
    component(s) that generated that piece. This prevents token-level XPOS
    unions from leaking unrelated POS entries into a fill row.
    """
    out: List[Dict[str, Any]] = []
    for row in list(fills or []):
        if isinstance(row, dict):
            out.append(dict(row))
        else:
            out.append(row)

    if not out:
        return out

    xpos_parts = [p.lower() for p in _split_compound_tags(xpos)]
    if len(xpos_parts) <= 1:
        return out

    lemma_parts = _split_compound_tags(lemma)
    lemma_xpos: List[Tuple[str, str]] = []
    if len(lemma_parts) == len(xpos_parts):
        for idx, lemma_piece in enumerate(lemma_parts):
            lemma_xpos.append((_normalize_component_text(lemma_piece), xpos_parts[idx]))

    # 1) Lexical matching pass: map each known fill piece to lemma piece(s).
    if lemma_xpos:
        for row in out:
            if not isinstance(row, dict):
                continue
            src = str(row.get("source", "") or "").upper()
            if src == "UNKNOWN":
                continue
            piece_norm = _normalize_component_text(row.get("head") or row.get("text") or "")
            if not piece_norm:
                continue

            matched_tags: List[str] = []
            seen = set()
            for lemma_norm, xtag in lemma_xpos:
                if not lemma_norm:
                    continue
                is_match = (
                    piece_norm == lemma_norm
                    or piece_norm == (lemma_norm + "다")
                    or lemma_norm == (piece_norm + "다")
                    or piece_norm in lemma_norm
                    or lemma_norm in piece_norm
                )
                if not is_match:
                    continue
                if xtag not in seen:
                    seen.add(xtag)
                    matched_tags.append(xtag)
            if matched_tags:
                row["_xpos_hint"] = "+".join(matched_tags)

    # 2) Positional fallback for unresolved known rows.
    unresolved_known_idx: List[int] = []
    for idx, row in enumerate(out):
        if not isinstance(row, dict):
            continue
        if row.get("_xpos_hint"):
            continue
        src = str(row.get("source", "") or "").upper()
        if src == "UNKNOWN":
            continue
        unresolved_known_idx.append(idx)

    if unresolved_known_idx and len(unresolved_known_idx) == len(xpos_parts):
        for ord_idx, row_idx in enumerate(unresolved_known_idx):
            out[row_idx]["_xpos_hint"] = xpos_parts[ord_idx]

    return out


# ---------------------------------------------------------------------------
# results_by_seg builder (generic)
# ---------------------------------------------------------------------------

def build_results_by_seg(
    segments: List[str],
    sentences_data: List[Dict],
    global_offset_by_sent_tok: Dict,
    dictionary,
    hooks: LanguageHooks,
    debug_trace_out: Optional[List[Dict[str, Any]]] = None,
) -> List[Optional[Dict[str, Any]]]:
    """Build results_by_seg: one dict per segment with dictionary + POS data."""
    reading_key = hooks.reading_key
    n = len(segments)
    results_by_seg: List[Optional[Dict[str, Any]]] = [None] * n

    for sent_idx, sent in enumerate(sentences_data):
        sent_tokens = sent.get("tokens", [])
        child_index = _build_sentence_child_index(sent_tokens)
        for tok_idx, tok in enumerate(sent_tokens):
            global_idx = global_offset_by_sent_tok.get((sent_idx, tok_idx))
            if global_idx is None or global_idx >= n:
                continue

            word = segments[global_idx]
            upos = tok.get("upos", "X")
            deprel = tok.get("deprel", "dep")
            xpos = tok.get("xpos", "")
            lemma = str(tok.get("lemma", "") or "")
            feats = _stringify_ud_feats(tok.get("feats"))

            head_in_sent = tok.get("head", 0)
            if head_in_sent == 0:
                head_global = global_idx
            else:
                head_global = global_offset_by_sent_tok.get(
                    (sent_idx, head_in_sent - 1), global_idx
                )

            # Dictionary lookup (surface-first baseline)
            all_entries = dictionary.lookup_all(word)
            fill = dictionary.fill_token(word)
            fill_subwords = dictionary.fill_token(word, allow_exact=False, exclude_whole=True)
            dict_head = word
            surface_entries = list(all_entries or [])
            surface_fill = fill
            surface_fill_subwords = fill_subwords
            lemma_attempted = bool(lemma and lemma != word and hooks.fill_token_with_lemma)
            lemma_entries: List[Dict[str, Any]] = []
            lemma_fill: Optional[Dict[str, Any]] = None
            lemma_result_used = False

            # Lemma-first override for languages that provide hook behavior.
            # If a lemma exists and resolves, prefer lemma entries/head.
            if lemma and hooks.fill_token_with_lemma:
                try:
                    lemma_result = hooks.fill_token_with_lemma(
                        word, lemma, dictionary, xpos=xpos, upos=upos
                    )
                except TypeError:
                    try:
                        lemma_result = hooks.fill_token_with_lemma(
                            word, lemma, dictionary, xpos=xpos
                        )
                    except TypeError:
                        lemma_result = hooks.fill_token_with_lemma(word, lemma, dictionary)
                if lemma_result:
                    lemma_entries = lemma_result.get("entries", []) or []
                    lemma_fill = lemma_result.get("fill")
                    if lemma_entries:
                        all_entries = lemma_entries
                        dict_head = lemma
                        lemma_result_used = True
                    # If lemma resolved entries, or surface had no entries, use hook fill.
                    if lemma_fill and (lemma_entries or not all_entries):
                        fill = lemma_fill
                        lemma_result_used = True
            resolved_via_lemma = bool(lemma and dict_head == lemma and dict_head != word)

            # Pick best entry
            chosen_main = None
            if hooks.choose_entry:
                chosen_main = hooks.choose_entry(dict_head, all_entries)
            elif all_entries:
                chosen_main = all_entries[0]

            hover_entries: List[Dict[str, Any]] = list(all_entries or [])
            other_entries: List[Dict[str, Any]] = []

            # Build main entry dict
            if all_entries:
                hover_senses = []
                hover_other_senses = []
                forms_meta_by_header = _build_jmdict_forms_meta_by_header(all_entries)
                hover_forms_meta_by_header: Dict[str, Dict[str, Any]] = {}
                other_forms_meta_by_header: Dict[str, Dict[str, Any]] = {}
                if hooks.filter_entries_for_upos:
                    entry_filter_mode = str((fill or {}).get("mode", "") or "").strip().lower()
                    entry_filter_kwargs: Dict[str, Any] = {}
                    if entry_filter_mode in {"greedy", "lemma_greedy", "greedy_lemma_mismatch"}:
                        entry_filter_kwargs["greedy_match"] = True
                    hover_entries, other_entries = _split_entries_for_hover(
                        all_entries,
                        upos,
                        dictionary,
                        hooks,
                        xpos=xpos,
                        **entry_filter_kwargs,
                    )
                    hover_senses = merge_all_entries(
                        dict_head,
                        hover_entries,
                        surface_form=word,
                        lemma_form=lemma,
                    )
                    if other_entries:
                        hover_other_senses = merge_all_entries(
                            dict_head,
                            other_entries,
                            surface_form=word,
                            lemma_form=lemma,
                        )
                    hover_forms_meta_by_header = _build_jmdict_forms_meta_by_header(hover_entries)
                    if other_entries:
                        other_forms_meta_by_header = _build_jmdict_forms_meta_by_header(other_entries)
                else:
                    hover_forms_meta_by_header = forms_meta_by_header

                merged_senses = merge_all_entries(
                    dict_head,
                    all_entries,
                    surface_form=word,
                    lemma_form=lemma,
                )
                roman = (chosen_main or all_entries[0]).get(reading_key, "") or \
                        (chosen_main or all_entries[0]).get("pinyin", "") or \
                        (chosen_main or all_entries[0]).get("reading", "") or ""
                entry = {
                    "head": dict_head,
                    "roman": roman,
                    "pos": upos,
                    "meta_pos": upos,
                    "senses": merged_senses,
                    "source": "DICT",
                }
                if hooks.filter_entries_for_upos:
                    entry["senses_hover"] = hover_senses
                    entry["senses_hover_other"] = hover_other_senses
                    entry["hover_has_alt_senses"] = bool(hover_other_senses)
                if forms_meta_by_header:
                    entry["senses_form_meta_by_header"] = forms_meta_by_header
                if hover_forms_meta_by_header:
                    entry["senses_hover_form_meta_by_header"] = hover_forms_meta_by_header
                if other_forms_meta_by_header:
                    entry["senses_hover_other_form_meta_by_header"] = other_forms_meta_by_header
            elif fill["has_known"] and not fill["has_unknown"]:
                entry = {
                    "head": word,
                    "roman": "",
                    "pos": upos,
                    "meta_pos": "composite",
                    "senses": [],
                    "source": "COMPOSITE",
                }
            else:
                entry = {
                    "head": word,
                    "roman": "",
                    "pos": upos,
                    "meta_pos": "unknown" if not all_entries else upos,
                    "senses": [],
                    "source": "UNKNOWN",
                }

            if hooks.filter_entries_for_upos and "senses_hover" not in entry:
                entry["senses_hover"] = list(entry.get("senses", []) or [])
                entry["senses_hover_other"] = []
                entry["hover_has_alt_senses"] = False

            # Preserve dictionary morphology metadata (inflected form -> base lemma)
            # so the grammar popup can explain why a token resolved to this entry.
            primary_entry = chosen_main or (all_entries[0] if all_entries else None)
            if isinstance(primary_entry, dict):
                morph_info = primary_entry.get("morph_info")
                morph_base = primary_entry.get("morph_base")
                grammar_text = primary_entry.get("grammar")
                if morph_info:
                    entry["morph_info"] = list(morph_info) if isinstance(morph_info, list) else [str(morph_info)]
                if morph_base:
                    entry["morph_base"] = str(morph_base)
                if grammar_text:
                    entry["grammar"] = str(grammar_text)

            # Keep both surface and lemma forms so the UI can show conversion clearly.
            entry["surface_form"] = word
            if lemma:
                entry["lemma_form"] = lemma
            if resolved_via_lemma:
                entry["resolved_via"] = "lemma"

            # Attach language-specific forms
            if hooks.attach_forms:
                hooks.attach_forms(entry, dict_head, all_entries)
                # If filtering is active, also build entry_groups for
                # primary (hover) and other entries separately.
                if hooks.filter_entries_for_upos and other_entries:
                    hover_entry_tmp: Dict[str, Any] = {}
                    hooks.attach_forms(hover_entry_tmp, dict_head, hover_entries)
                    if hover_entry_tmp.get("entry_groups"):
                        entry["entry_groups_hover"] = hover_entry_tmp["entry_groups"]
                    other_entry_tmp: Dict[str, Any] = {}
                    hooks.attach_forms(other_entry_tmp, dict_head, other_entries)
                    if other_entry_tmp.get("entry_groups"):
                        entry["entry_groups_other"] = other_entry_tmp["entry_groups"]

            # Format dict_fill senses
            fill_rows = _derive_fill_piece_xpos_hints(
                fill.get("fills", []),
                lemma,
                xpos,
            )
            fill_subword_rows = _derive_fill_piece_xpos_hints(
                fill_subwords.get("fills", []),
                lemma,
                xpos,
            )
            fill_mode = str(fill.get("mode", "greedy") or "greedy")
            raw_fills = prepare_fill_entries(
                fill_rows,
                dictionary,
                hooks,
                upos=upos,
                xpos=xpos,
                fill_mode=fill_mode,
            )
            raw_fill_subwords = prepare_fill_entries(
                fill_subword_rows,
                dictionary,
                hooks,
                upos=upos,
                xpos=xpos,
                fill_mode=fill_mode,
            )
            fill_has_known = fill.get("has_known", False)
            fill_has_unknown = fill.get("has_unknown", True)

            entry["dict_fill"] = raw_fills
            entry["dict_fill_subwords"] = raw_fill_subwords
            entry["inspect_fill"] = raw_fills
            entry["dict_fill_mode"] = fill_mode
            entry["dict_fill_has_known"] = fill_has_known
            entry["dict_fill_has_unknown"] = fill_has_unknown
            entry["seg_i"] = global_idx

            # Optional per-token debug trace.
            if debug_trace_out is not None:
                fill_mode_value = str(fill_mode or "")
                lemma_fill_mode = str((lemma_fill or {}).get("mode", "") or "")
                operations = [
                    {
                        "step": "surface_exact_lookup",
                        "head": word,
                        "matched": bool(surface_entries),
                        "entry_count": len(surface_entries),
                    },
                    {
                        "step": "surface_fill",
                        "mode": str(surface_fill.get("mode", "") or ""),
                        "has_known": bool(surface_fill.get("has_known", False)),
                        "has_unknown": bool(surface_fill.get("has_unknown", True)),
                        "pieces": _debug_fill_pieces(surface_fill),
                    },
                    {
                        "step": "surface_fill_subwords",
                        "mode": str(surface_fill_subwords.get("mode", "") or ""),
                        "has_known": bool(surface_fill_subwords.get("has_known", False)),
                        "has_unknown": bool(surface_fill_subwords.get("has_unknown", True)),
                        "pieces": _debug_fill_pieces(surface_fill_subwords),
                    },
                ]
                if lemma_attempted:
                    operations.append({
                        "step": "lemma_fallback",
                        "lemma": lemma,
                        "entries_found": len(lemma_entries),
                        "fill_mode": lemma_fill_mode,
                        "used_for_resolution": bool(lemma_result_used),
                    })

                appended_rows: List[Dict[str, Any]] = []
                for fill_entry in list(raw_fills or []):
                    shown_senses = list(
                        fill_entry.get("senses_hover", fill_entry.get("senses", [])) or []
                    )
                    filtered_senses = list(fill_entry.get("senses_hover_other", []) or [])
                    shown_groups = list(
                        fill_entry.get("entry_groups_hover", fill_entry.get("entry_groups", [])) or []
                    )
                    filtered_groups = list(fill_entry.get("entry_groups_other", []) or [])
                    if shown_senses and filtered_senses:
                        filter_status = "shown_with_filtered_alternates"
                    elif shown_senses:
                        filter_status = "shown"
                    elif filtered_senses:
                        filter_status = "filtered_out"
                    else:
                        filter_status = "shown"
                    appended_rows.append({
                        "text": str(fill_entry.get("text", "") or ""),
                        "head": str(fill_entry.get("head", "") or ""),
                        "roman": str(fill_entry.get("roman", "") or ""),
                        "source": str(fill_entry.get("source", "") or ""),
                        "filter_status": filter_status,
                        "shown_senses": shown_senses,
                        "filtered_senses": filtered_senses,
                        "shown_count": len(shown_senses),
                        "filtered_count": len(filtered_senses),
                        "shown_entry_group_count": len(shown_groups),
                        "filtered_entry_group_count": len(filtered_groups),
                    })

                entry_filter_breakdown = _build_debug_entry_filter_breakdown(
                    all_entries,
                    hover_entries,
                    other_entries,
                    dictionary,
                    xpos=xpos,
                    upos=upos,
                )
                candidate_rows = list(
                    (entry_filter_breakdown or {}).get("entries")
                    or _build_debug_candidate_rows(
                        all_entries,
                        hover_entries,
                        other_entries,
                    )
                )

                debug_trace_out.append({
                    "seg_i": global_idx,
                    "sentence_index": sent_idx,
                    "token_index": tok_idx,
                    "token": word,
                    "lemma": lemma,
                    "upos": upos,
                    "xpos": xpos,
                    "head_global": head_global,
                    "resolved_head": dict_head,
                    "resolved_via_lemma": resolved_via_lemma,
                    "dict_source": entry.get("source", ""),
                    "dict_fill_mode": fill_mode_value,
                    "match_path": _classify_fill_strategy(fill_mode_value),
                    "used_exact_match": fill_mode_value in {"exact", "lemma"},
                    "used_lemma_greedy_longest": fill_mode_value == "lemma_greedy",
                    "used_surface_greedy_longest": fill_mode_value == "greedy",
                    "operations": operations,
                    "entry_filter_breakdown": entry_filter_breakdown,
                    "candidate_entries": candidate_rows,
                    "appended_dict_fill_entries": appended_rows,
                })

            # Attach g2p if language supports it
            if hooks.build_g2p:
                entry["g2p"] = hooks.build_g2p(dict_head, dictionary, fallback_roman=entry.get("roman", ""))
            else:
                entry["g2p"] = None

            # POS/dep data
            entry["upos"] = upos
            entry["upos_label"] = upos
            entry["upos_color"] = UPOS_COLORS.get(upos, "#d1d5db")
            entry["dep"] = deprel
            entry["dep_label"] = deprel
            entry["tag"] = xpos
            entry["lemma"] = lemma
            entry["feats"] = feats
            token_surface = str(word or "").strip()
            token_lemma = str(lemma or "").strip()
            should_try_deconj = bool(token_surface and token_lemma and token_surface != token_lemma)
            if hooks.deconjugate and should_try_deconj:
                try:
                    entry_pos = _collect_entry_all_pos(chosen_main, all_entries)
                    candidates = _build_deconjugation_surface_candidates(
                        word,
                        sent_idx,
                        tok_idx,
                        segments,
                        global_offset_by_sent_tok,
                        child_index,
                    )
                    best_hit = None
                    for cand_idx, cand_meta in enumerate(candidates):
                        if isinstance(cand_meta, dict):
                            cand_surface = str(cand_meta.get("surface", "") or "").strip()
                            cand_tokens = [
                                str(piece or "").strip()
                                for piece in list(cand_meta.get("tokens", []) or [])
                                if str(piece or "").strip()
                            ]
                            raw_indices = list(cand_meta.get("token_indices", []) or [])
                        else:
                            cand_surface = str(cand_meta or "").strip()
                            cand_tokens = [cand_surface] if cand_surface else []
                            raw_indices = []
                        if not cand_surface:
                            continue
                        hit = hooks.deconjugate(cand_surface, lemma, entry_pos)
                        if not hit:
                            continue
                        if isinstance(hit, dict):
                            hit = dict(hit)
                            hit["surface_used"] = cand_surface
                            hit["analysis_tokens"] = list(cand_tokens or [cand_surface])
                            token_indices: List[int] = []
                            for idx in raw_indices:
                                try:
                                    token_indices.append(int(idx))
                                except Exception:
                                    continue
                            if token_indices:
                                hit["analysis_token_indices"] = token_indices
                            if len(candidates) > 1:
                                hit["surface_candidates"] = [
                                    str((c.get("surface", "") if isinstance(c, dict) else c) or "").strip()
                                    for c in candidates
                                    if str((c.get("surface", "") if isinstance(c, dict) else c) or "").strip()
                                ]
                                hit["surface_candidate_index"] = cand_idx
                                hit["used_dependency_context"] = (cand_surface != word)
                        best_hit = hit
                        break
                    if best_hit is not None:
                        entry["conjugation"] = best_hit
                except Exception:
                    pass

            results_by_seg[global_idx] = entry

    return results_by_seg


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

def process_lookup(
    text: str,
    trankit_doc: dict,
    dictionary,
    hooks: LanguageHooks,
    trankit_lang: str = "",
) -> Dict[str, Any]:
    """
    Full NLP lookup: Trankit doc + dict mapping -> response.

    `trankit_doc` is the already-computed Trankit output (called via
    language_registry.run_trankit with the lock held).
    """
    if not text or not text.strip():
        return {"ok": False, "error": "no text found"}

    model_text = text
    original_text = model_text

    doc = trankit_doc

    # Optional MWT adapter
    try:
        doc_for_pipeline, mwt_meta = maybe_expand_mwt_doc(doc, trankit_lang)
    except Exception as e:
        doc_for_pipeline = doc
        mwt_meta = {
            "applied": False,
            "supports_mwt": False,
            "language": str(trankit_lang or ""),
            "expanded_token_count": 0,
            "error": f"{type(e).__name__}: {e}",
        }

    # Flatten tokens across sentences
    sentences_data = doc_for_pipeline.get("sentences", [])
    segments: List[str] = []
    segment_offsets: List[List[int]] = []
    global_offset_by_sent_tok: Dict = {}

    for sent_idx, sent in enumerate(sentences_data):
        sent_tokens = sent.get("tokens", [])
        for tok_idx, tok in enumerate(sent_tokens):
            global_idx = len(segments)
            global_offset_by_sent_tok[(sent_idx, tok_idx)] = global_idx

            tok_text = tok.get("text", "")
            segments.append(tok_text)

            dspan = tok.get("dspan")
            span = tok.get("span")
            if dspan and isinstance(dspan, (list, tuple)) and len(dspan) >= 2:
                model_start, model_end = int(dspan[0]), int(dspan[1])
            elif span and isinstance(span, (list, tuple)) and len(span) >= 2:
                model_start, model_end = int(span[0]), int(span[1])
            else:
                model_start, model_end = 0, len(tok_text)

            if model_end < model_start:
                model_end = model_start

            segment_offsets.append([model_start, model_end])

    if not segments:
        return {"ok": False, "error": "no tokens produced"}

    # Build results_by_seg with dictionary data.
    # Gate expensive per-token debug traces behind debug collection flag.
    trace_lang = str(trankit_lang or "").strip().lower()
    debug_collection_enabled = False
    store_debug_snapshot_fn = None
    try:
        from debug_store import is_debug_collection_enabled, store_debug_snapshot
        debug_collection_enabled = bool(is_debug_collection_enabled())
        store_debug_snapshot_fn = store_debug_snapshot
    except Exception:
        debug_collection_enabled = False
        store_debug_snapshot_fn = None

    dictionary_decision_trace: Optional[List[Dict[str, Any]]] = (
        [] if (debug_collection_enabled and trace_lang in {"ja", "ko", "vi", "ar"}) else None
    )
    results_by_seg = build_results_by_seg(
        segments,
        sentences_data,
        global_offset_by_sent_tok,
        dictionary,
        hooks,
        debug_trace_out=dictionary_decision_trace,
    )

    if dictionary_decision_trace is not None:
        for row in dictionary_decision_trace:
            if not isinstance(row, dict):
                continue
            try:
                seg_i = int(row.get("seg_i"))
            except Exception:
                continue
            if seg_i < 0:
                continue
            if seg_i < len(segment_offsets):
                row["segment_offset"] = list(segment_offsets[seg_i])
            if seg_i < len(results_by_seg):
                mapped = results_by_seg[seg_i]
                if isinstance(mapped, dict):
                    row["segment_mapping"] = {
                        "segment": str(segments[seg_i] if seg_i < len(segments) else ""),
                        "resolved_head": str(mapped.get("head", "") or ""),
                        "resolved_source": str(mapped.get("source", "") or ""),
                        "resolved_via": str(mapped.get("resolved_via", "") or ""),
                        "upos": str(mapped.get("upos", "") or ""),
                        "xpos": str(mapped.get("tag", "") or ""),
                        "dict_fill_count": len(list(mapped.get("dict_fill", []) or [])),
                    }

    # Build ud_overlay from Trankit parse
    ud_overlay = build_ud_overlay(
        sentences_data, segments, global_offset_by_sent_tok
    )

    # Build results list (first non-punct entry for panel display)
    results = []
    for entry in results_by_seg:
        if entry and entry.get("source") != "PUNCT":
            results.append(entry)
            break

    debug_capture_id = uuid.uuid4().hex

    # Debug snapshot
    if debug_collection_enabled and callable(store_debug_snapshot_fn):
        try:
            snapshot = {
                "debug_capture_id": debug_capture_id,
                "language": trankit_lang,
                "original_text": original_text,
                "filtered_text": model_text,
                "raw_trankit_doc": doc,
                "pipeline_trankit_doc": doc_for_pipeline,
                "mwt_meta": mwt_meta,
                "segments": segments,
                "segment_offsets": segment_offsets,
                "results_by_seg": results_by_seg,
            }
            if dictionary_decision_trace is not None:
                # Preferred language-agnostic key.
                snapshot["dictionary_decision_trace"] = dictionary_decision_trace
                # Backward-compatible aliases for existing debug UI consumers.
                if trace_lang == "ja":
                    snapshot["japanese_dictionary_trace"] = dictionary_decision_trace
                if trace_lang == "ko":
                    snapshot["korean_dictionary_trace"] = dictionary_decision_trace
                if trace_lang == "ar":
                    snapshot["arabic_dictionary_trace"] = dictionary_decision_trace
            store_debug_snapshot_fn(snapshot)
        except Exception:
            pass

    return {
        "ok": True,
        "debug_capture_id": debug_capture_id,
        "display_text": original_text,
        "q": original_text,
        "segments": segments,
        "segment_offsets": segment_offsets,
        "results": results,
        "results_by_seg": results_by_seg,
        "grammar_overlay": {"tokens": [], "links": []},
        "ud_overlay": ud_overlay,
        "mwt_meta": mwt_meta,
    }


def process_lookup_nlp_only(
    text: str,
    trankit_doc: dict,
    trankit_lang: str = "",
    enable_debug_capture: bool = True,
    debug_capture_id: str = "",
) -> Dict[str, Any]:
    """
    NLP-only lookup response: tokenization + UD annotations, no dictionary calls.

    Used by the browser-side dictionary engine, which merges dictionary data
    into ``results_by_seg`` client-side.
    """
    if not text or not text.strip():
        return {"ok": False, "error": "no text found"}

    model_text = text
    original_text = model_text
    doc = trankit_doc
    trace_active = bool(enable_debug_capture and is_trace_active())

    if trace_active:
        with trace_scope("flatten_mwt_doc", label="Flatten MWT Doc", language=trankit_lang):
            try:
                doc_for_pipeline, mwt_meta = _flatten_lookup_trankit_doc(doc, trankit_lang)
            except Exception as e:
                doc_for_pipeline = doc
                mwt_meta = {
                    "applied": False,
                    "supports_mwt": bool(language_supports_mwt(trankit_lang)),
                    "language": str(trankit_lang or ""),
                    "expanded_token_count": 0,
                    "surface_token_count": 0,
                    "error": f"{type(e).__name__}: {e}",
                }
    else:
        try:
            doc_for_pipeline, mwt_meta = _flatten_lookup_trankit_doc(doc, trankit_lang)
        except Exception as e:
            doc_for_pipeline = doc
            mwt_meta = {
                "applied": False,
                "supports_mwt": bool(language_supports_mwt(trankit_lang)),
                "language": str(trankit_lang or ""),
                "expanded_token_count": 0,
                "surface_token_count": 0,
                "error": f"{type(e).__name__}: {e}",
            }

    sentences_data = doc_for_pipeline.get("sentences", [])
    segments: List[str] = []
    segment_offsets: List[List[int]] = []
    global_offset_by_sent_tok: Dict = {}

    if trace_active:
        with trace_scope("collect_segments", label="Collect Segments", sentence_count=len(sentences_data)):
            for sent_idx, sent in enumerate(sentences_data):
                sent_tokens = sent.get("tokens", [])
                for tok_idx, tok in enumerate(sent_tokens):
                    global_idx = len(segments)
                    global_offset_by_sent_tok[(sent_idx, tok_idx)] = global_idx

                    tok_text = tok.get("text", "")
                    segments.append(tok_text)

                    dspan = tok.get("dspan")
                    span = tok.get("span")
                    if dspan and isinstance(dspan, (list, tuple)) and len(dspan) >= 2:
                        model_start, model_end = int(dspan[0]), int(dspan[1])
                    elif span and isinstance(span, (list, tuple)) and len(span) >= 2:
                        model_start, model_end = int(span[0]), int(span[1])
                    else:
                        model_start, model_end = 0, len(tok_text)

                    if model_end < model_start:
                        model_end = model_start

                    segment_offsets.append([model_start, model_end])
    else:
        for sent_idx, sent in enumerate(sentences_data):
            sent_tokens = sent.get("tokens", [])
            for tok_idx, tok in enumerate(sent_tokens):
                global_idx = len(segments)
                global_offset_by_sent_tok[(sent_idx, tok_idx)] = global_idx

                tok_text = tok.get("text", "")
                segments.append(tok_text)

                dspan = tok.get("dspan")
                span = tok.get("span")
                if dspan and isinstance(dspan, (list, tuple)) and len(dspan) >= 2:
                    model_start, model_end = int(dspan[0]), int(dspan[1])
                elif span and isinstance(span, (list, tuple)) and len(span) >= 2:
                    model_start, model_end = int(span[0]), int(span[1])
                else:
                    model_start, model_end = 0, len(tok_text)

                if model_end < model_start:
                    model_end = model_start

                segment_offsets.append([model_start, model_end])

    if not segments:
        return {"ok": False, "error": "no tokens produced"}

    if trace_active:
        with trace_scope("build_ud_overlay", label="Build UD Overlay", segment_count=len(segments)):
            ud_overlay = build_ud_overlay(
                sentences_data, segments, global_offset_by_sent_tok
            )
    else:
        ud_overlay = build_ud_overlay(
            sentences_data, segments, global_offset_by_sent_tok
        )

    response = {
        "ok": True,
        "display_text": original_text,
        "q": original_text,
        "segments": segments,
        "segment_offsets": segment_offsets,
        "results": [],
        "results_by_seg": [],
        "grammar_overlay": {"tokens": [], "links": []},
        "ud_overlay": ud_overlay,
        "mwt_meta": mwt_meta,
    }

    if not enable_debug_capture:
        return response

    capture_id = str(debug_capture_id or "").strip() or uuid.uuid4().hex

    # Debug snapshot: NLP-only path still needs a full snapshot so /debug/data
    # has token + segment context even when dictionary merge is client-side.
    debug_collection_enabled = False
    store_debug_snapshot_fn = None
    try:
        from debug_store import is_debug_collection_enabled, store_debug_snapshot

        debug_collection_enabled = bool(is_debug_collection_enabled())
        store_debug_snapshot_fn = store_debug_snapshot
    except Exception:
        debug_collection_enabled = False
        store_debug_snapshot_fn = None

    if debug_collection_enabled and callable(store_debug_snapshot_fn):
        try:
            if trace_active:
                with trace_scope("store_debug_snapshot", label="Store Debug Snapshot"):
                    store_debug_snapshot_fn(
                        {
                            "debug_capture_id": capture_id,
                            "language": trankit_lang,
                            "original_text": original_text,
                            "filtered_text": model_text,
                            "raw_trankit_doc": doc,
                            "pipeline_trankit_doc": doc_for_pipeline,
                            "mwt_meta": mwt_meta,
                            "segments": segments,
                            "segment_offsets": segment_offsets,
                            "results": [],
                            "results_by_seg": [],
                            "grammar_overlay": {"tokens": [], "links": []},
                            "ud_overlay": ud_overlay,
                        }
                    )
            else:
                store_debug_snapshot_fn(
                    {
                        "debug_capture_id": capture_id,
                        "language": trankit_lang,
                        "original_text": original_text,
                        "filtered_text": model_text,
                        "raw_trankit_doc": doc,
                        "pipeline_trankit_doc": doc_for_pipeline,
                        "mwt_meta": mwt_meta,
                        "segments": segments,
                        "segment_offsets": segment_offsets,
                        "results": [],
                        "results_by_seg": [],
                        "grammar_overlay": {"tokens": [], "links": []},
                        "ud_overlay": ud_overlay,
                    }
                )
        except Exception:
            pass

    response["debug_capture_id"] = capture_id
    return response


def process_lookup_dp_only(
    text: str,
    dictionary,
    hooks: LanguageHooks,
    lemma_hint: str = None,
    upos_hint: str = None,
    xpos_hint: str = None,
) -> Dict[str, Any]:
    """Dictionary-only lookup (no Trankit). For lightweight side-panel queries.

    If `lemma_hint` is provided (from the initial segmentation), it will be
    tried as a fallback when the surface form has no exact dictionary match.

    If `upos_hint` is provided (from the initial Trankit run), it is used
    to split definitions into POS-matching (``senses_hover``) and other
    (``senses_hover_other``) so the side panel can replicate the hover
    popup's filtered view with an expander for the rest.
    """
    if not text or not text.strip():
        return {"ok": False, "error": "empty"}

    reading_key = hooks.reading_key
    word = text

    all_entries = dictionary.lookup_all(word)
    dict_head = word

    # Lemma-first: if a lemma hint is provided, try lemma resolution first.
    used_lemma = False
    lemma_fill_override = None
    if lemma_hint and hooks.fill_token_with_lemma:
        try:
            lemma_result = hooks.fill_token_with_lemma(
                word,
                lemma_hint,
                dictionary,
                xpos=str(xpos_hint or ""),
                upos=str(upos_hint or ""),
            )
        except TypeError:
            try:
                lemma_result = hooks.fill_token_with_lemma(
                    word,
                    lemma_hint,
                    dictionary,
                    xpos=str(xpos_hint or ""),
                )
            except TypeError:
                lemma_result = hooks.fill_token_with_lemma(word, lemma_hint, dictionary)
        if lemma_result:
            lemma_entries = lemma_result.get("entries", []) or []
            lemma_fill = lemma_result.get("fill")
            if lemma_entries:
                all_entries = lemma_entries
                used_lemma = True
                dict_head = lemma_hint
            if lemma_fill and (lemma_entries or not all_entries):
                lemma_fill_override = lemma_fill
        # Direct lemma lookup fallback if hook did not resolve entries
        if not all_entries:
            lemma_entries = dictionary.lookup_all(lemma_hint)
            if lemma_entries:
                all_entries = lemma_entries
                used_lemma = True
                dict_head = lemma_hint

    fill = lemma_fill_override if lemma_fill_override else dictionary.fill_token(word)
    fill_subwords = dictionary.fill_token(word, allow_exact=False, exclude_whole=True)

    # Pick best entry
    chosen_main = None
    if hooks.choose_entry:
        chosen_main = hooks.choose_entry(dict_head, all_entries)
    elif all_entries:
        chosen_main = all_entries[0]

    upos = str(upos_hint or "").strip().upper() or ""
    xpos = str(xpos_hint or "").strip() or ""
    fill_rows = _derive_fill_piece_xpos_hints(
        fill.get("fills", []),
        str(lemma_hint or ""),
        xpos,
    )
    fill_subword_rows = _derive_fill_piece_xpos_hints(
        fill_subwords.get("fills", []),
        str(lemma_hint or ""),
        xpos,
    )
    fill_mode = str(fill.get("mode", "greedy") or "greedy")
    raw_fills = prepare_fill_entries(
        fill_rows, dictionary, hooks, upos=upos, xpos=xpos, fill_mode=fill_mode,
    )
    raw_fill_subwords = prepare_fill_entries(
        fill_subword_rows, dictionary, hooks, upos=upos, xpos=xpos, fill_mode=fill_mode,
    )

    if all_entries:
        best = chosen_main or all_entries[0]
        roman = best.get(reading_key, "") or best.get("pinyin", "") or best.get("reading", "") or ""
        merged_senses = merge_all_entries(
            dict_head,
            all_entries,
            surface_form=word,
            lemma_form=lemma_hint,
        )
        forms_meta_by_header = _build_jmdict_forms_meta_by_header(all_entries)

        # POS filtering: split entries into primary (matching UPOS) vs other
        hover_senses = list(merged_senses)
        hover_other_senses: list = []
        hover_forms_meta_by_header: Dict[str, Dict[str, Any]] = forms_meta_by_header
        other_forms_meta_by_header: Dict[str, Dict[str, Any]] = {}
        entry_filter_kwargs: Dict[str, Any] = {}
        if fill_mode in {"greedy", "lemma_greedy", "greedy_lemma_mismatch"}:
            entry_filter_kwargs["greedy_match"] = True
        if upos and hooks.filter_entries_for_upos:
            hover_entries, other_entries = _split_entries_for_hover(
                all_entries, upos, dictionary, hooks, xpos=xpos, **entry_filter_kwargs,
            )
            hover_senses = merge_all_entries(
                dict_head, hover_entries,
                surface_form=word, lemma_form=lemma_hint,
            )
            hover_forms_meta_by_header = _build_jmdict_forms_meta_by_header(hover_entries)
            if other_entries:
                hover_other_senses = merge_all_entries(
                    dict_head, other_entries,
                    surface_form=word, lemma_form=lemma_hint,
                )
                other_forms_meta_by_header = _build_jmdict_forms_meta_by_header(other_entries)

        result = {
            "head": dict_head,
            "roman": roman,
            "pos": upos or "",
            "meta_pos": upos or "",
            "lemma": lemma_hint or "",
            "feats": "",
            "senses": merged_senses,
            "source": "DICT",
            "dict_fill": raw_fills,
            "dict_fill_subwords": raw_fill_subwords,
            "inspect_fill": raw_fills,
            "dict_fill_mode": fill_mode,
            "dict_fill_has_known": fill.get("has_known", False),
            "dict_fill_has_unknown": fill.get("has_unknown", True),
            "seg_i": 0,
            "surface_form": word,
        }
        if isinstance(best, dict):
            morph_info = best.get("morph_info")
            morph_base = best.get("morph_base")
            grammar_text = best.get("grammar")
            if morph_info:
                result["morph_info"] = list(morph_info) if isinstance(morph_info, list) else [str(morph_info)]
            if morph_base:
                result["morph_base"] = str(morph_base)
            if grammar_text:
                result["grammar"] = str(grammar_text)
        if hooks.filter_entries_for_upos:
            result["senses_hover"] = hover_senses
            result["senses_hover_other"] = hover_other_senses
            result["hover_has_alt_senses"] = bool(hover_other_senses)
            if hover_forms_meta_by_header:
                result["senses_hover_form_meta_by_header"] = hover_forms_meta_by_header
            if other_forms_meta_by_header:
                result["senses_hover_other_form_meta_by_header"] = other_forms_meta_by_header
        if forms_meta_by_header:
            result["senses_form_meta_by_header"] = forms_meta_by_header
        if used_lemma:
            result["resolved_via"] = "lemma"
            result["lemma_form"] = lemma_hint
        # Attach g2p
        if hooks.build_g2p:
            result["g2p"] = hooks.build_g2p(dict_head, dictionary, fallback_roman=roman)
        else:
            result["g2p"] = None
        # Attach forms
        if hooks.attach_forms:
            hooks.attach_forms(result, dict_head, all_entries)
            # Build separate entry_groups for filtered view
            if upos and hooks.filter_entries_for_upos:
                hover_ent, other_ent = _split_entries_for_hover(
                    all_entries, upos, dictionary, hooks, xpos=xpos, **entry_filter_kwargs,
                )
                if other_ent:
                    hover_tmp: Dict[str, Any] = {}
                    hooks.attach_forms(hover_tmp, dict_head, hover_ent)
                    if hover_tmp.get("entry_groups"):
                        result["entry_groups_hover"] = hover_tmp["entry_groups"]
                    other_tmp: Dict[str, Any] = {}
                    hooks.attach_forms(other_tmp, dict_head, other_ent)
                    if other_tmp.get("entry_groups"):
                        result["entry_groups_other"] = other_tmp["entry_groups"]
        token_surface = str(word or "").strip()
        token_lemma = str(result.get("lemma", "") or "").strip()
        should_try_deconj = bool(token_surface and token_lemma and token_surface != token_lemma)
        if hooks.deconjugate and should_try_deconj:
            try:
                result_pos = _collect_entry_all_pos(chosen_main, all_entries)
                hit = hooks.deconjugate(word, result.get("lemma", ""), result_pos)
                if isinstance(hit, dict):
                    hit = dict(hit)
                    hit.setdefault("surface_used", word)
                    hit.setdefault("analysis_tokens", [str(word or "")])
                if hit is not None:
                    result["conjugation"] = hit
            except Exception:
                pass
    else:
        result = {
            "head": word,
            "roman": "",
            "pos": "unknown",
            "meta_pos": "unknown",
            "lemma": lemma_hint or "",
            "feats": "",
            "senses": [],
            "source": "UNKNOWN",
            "dict_fill": raw_fills,
            "dict_fill_subwords": raw_fill_subwords,
            "inspect_fill": raw_fills,
            "dict_fill_mode": fill_mode,
            "dict_fill_has_known": fill.get("has_known", False),
            "dict_fill_has_unknown": fill.get("has_unknown", True),
            "seg_i": 0,
            "surface_form": word,
        }
        if hooks.build_g2p:
            result["g2p"] = hooks.build_g2p(word, dictionary, fallback_roman="")
        else:
            result["g2p"] = None
        if hooks.attach_forms:
            hooks.attach_forms(result, word, all_entries)

    return {
        "ok": True,
        "display_text": word,
        "q": word,
        "segments": [word],
        "segment_offsets": [[0, len(word)]],
        "results": [result],
        "results_by_seg": [result],
        "grammar_overlay": {"tokens": [], "links": []},
        "ud_overlay": {
            "ok": False,
            "tokens": [],
            "edges": [],
            "roots": [],
            "ents": [],
            "sentences": [],
            "doc2seg": [],
            "seg2doc": [-1],
            "error": "dp_only",
        },
    }
