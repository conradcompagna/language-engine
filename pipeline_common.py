"""NLP response construction, Unicode span alignment, and dictionary form metadata.

The browser owns lexical segmentation; this module aligns neural output with
source spans and constructs the shared dependency/entity overlay.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from trankit_mwt_expansion import (
    language_supports_mwt,
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

    if n == 0 or surface_len == 0:
        for p in parts:
            if p.get("surface_slice") is None:
                p["surface_slice"] = [0, 0]
            p.setdefault("_realign_pass", "empty")
            probe = _mwt_probe_text(p)
            p["surface_char_map"] = [0] * len(probe)
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


def _flatten_lookup_sentence_tokens(
    sent_tokens: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], bool, int]:
    flat_tokens: List[Dict[str, Any]] = []
    saw_mwt = False
    expanded_token_count = 0

    for tok in sent_tokens:
        if not isinstance(tok, dict):
            continue

        expanded = tok.get("expanded")
        is_mwt_parent = bool(
            _is_lookup_int_pair(tok.get("id")) and isinstance(expanded, list) and expanded
        )
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
        child_id_start = (
            _lookup_to_int(parent_id[0], None) if _is_lookup_int_pair(parent_id) else None
        )

        realign_parts: List[Dict[str, Any]] = []
        for ci, child_row in enumerate(expanded_rows):
            if child_row.get("id") is None and child_id_start is not None:
                child_row["id"] = child_id_start + ci
            realign_parts.append(
                {
                    "part_index": ci,
                    "text": str(child_row.get("text", "") or ""),
                    "lemma": str(child_row.get("lemma", "") or ""),
                }
            )

        if realign_parts:
            _realign_mwt_children(realign_parts, parent_text)

        for ci, child_row in enumerate(expanded_rows):
            flat_row = dict(child_row)
            flat_row.pop("expanded", None)
            flat_row.pop("mwt_subword_edges", None)
            flat_row.pop("mwt_expanded_words", None)
            flat_row.pop("mwt_expanded_texts", None)
            flat_row.pop("mwt_head_part_index", None)

            rel_slice_raw = (
                realign_parts[ci].get("surface_slice") if ci < len(realign_parts) else None
            )
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
        flat_tokens, sent_had_mwt, sent_expanded_count = _flatten_lookup_sentence_tokens(
            sent_tokens
        )
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

            raw_token_slice = _normalize_lookup_span(tok.get("dspan")) or _normalize_lookup_span(
                tok.get("span")
            )
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
                head_global = global_offset_by_sent_tok.get((sent_idx, head_tok_idx), global_idx)

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
                        collected_parts.append(
                            {
                                "part_index": int(part_idx),
                                "text": str(part.get("text", "") or ""),
                                "lemma": str(part.get("lemma", "") or ""),
                                "upos": str(part.get("upos", "X") or "X"),
                                "tag": str(part.get("xpos", "") or ""),
                                "dep": str(part.get("deprel", "dep") or "dep"),
                            }
                        )
                    # Realign MWT children onto the parent surface.
                    # Trankit supplies NO child spans — the realigner is
                    # authoritative. Run it unconditionally; the trivial-
                    # equality fast path handles non-sandhi MWT (des=de+les).
                    if collected_parts:
                        _realign_mwt_children(collected_parts, parent_surface_text)
                        for _cp in collected_parts:
                            _pi = _cp.get("part_index")
                            if isinstance(_pi, int) and 0 <= _pi < len(expanded_rows):
                                _raw = expanded_rows[_pi]
                                if isinstance(_raw, dict):
                                    _raw["surface_slice"] = _cp.get("surface_slice")
                            if "_realign_pass" in _cp:
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
                    ents_out.append(
                        {
                            "start": current_ent_start,
                            "end": global_idx,
                            "label": current_ent_label,
                            "text": "".join(current_ent_tokens),
                        }
                    )
                    current_ent_start = None
                    current_ent_label = None
                    current_ent_tokens = []
            elif ner_tag.startswith("B-"):
                if current_ent_start is not None:
                    ents_out.append(
                        {
                            "start": current_ent_start,
                            "end": global_idx,
                            "label": current_ent_label,
                            "text": "".join(current_ent_tokens),
                        }
                    )
                current_ent_label = ner_tag[2:]
                current_ent_start = global_idx
                current_ent_tokens = [tok.get("text", "")]
            elif ner_tag.startswith("I-"):
                label = ner_tag[2:]
                if current_ent_start is not None and label == current_ent_label:
                    current_ent_tokens.append(tok.get("text", ""))
                else:
                    if current_ent_start is not None:
                        ents_out.append(
                            {
                                "start": current_ent_start,
                                "end": global_idx,
                                "label": current_ent_label,
                                "text": "".join(current_ent_tokens),
                            }
                        )
                    current_ent_label = label
                    current_ent_start = global_idx
                    current_ent_tokens = [tok.get("text", "")]
            elif ner_tag.startswith("S-"):
                if current_ent_start is not None:
                    ents_out.append(
                        {
                            "start": current_ent_start,
                            "end": global_idx,
                            "label": current_ent_label,
                            "text": "".join(current_ent_tokens),
                        }
                    )
                    current_ent_start = None
                    current_ent_label = None
                    current_ent_tokens = []
                ents_out.append(
                    {
                        "start": global_idx,
                        "end": global_idx + 1,
                        "label": ner_tag[2:],
                        "text": tok.get("text", ""),
                    }
                )
            elif ner_tag.startswith("E-"):
                label = ner_tag[2:]
                if current_ent_start is not None and label == current_ent_label:
                    current_ent_tokens.append(tok.get("text", ""))
                    ents_out.append(
                        {
                            "start": current_ent_start,
                            "end": global_idx + 1,
                            "label": current_ent_label,
                            "text": "".join(current_ent_tokens),
                        }
                    )
                else:
                    if current_ent_start is not None:
                        ents_out.append(
                            {
                                "start": current_ent_start,
                                "end": global_idx,
                                "label": current_ent_label,
                                "text": "".join(current_ent_tokens),
                            }
                        )
                    ents_out.append(
                        {
                            "start": global_idx,
                            "end": global_idx + 1,
                            "label": label,
                            "text": tok.get("text", ""),
                        }
                    )
                current_ent_start = None
                current_ent_label = None
                current_ent_tokens = []

    if current_ent_start is not None:
        ents_out.append(
            {
                "start": current_ent_start,
                "end": n,
                "label": current_ent_label,
                "text": "".join(current_ent_tokens),
            }
        )

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
                        anchors.append(
                            {
                                "token_i": global_idx,
                                "text": str(surface_anchor.get("text", "") or ""),
                                "slice": [sa_start, sa_end],
                                "source": "surface_anchor",
                            }
                        )
                        continue
            raw_slice = token_surface_slice_by_global.get(global_idx)
            if isinstance(raw_slice, (list, tuple)) and len(raw_slice) >= 2:
                sa_start = _lookup_to_int(raw_slice[0], None)
                sa_end = _lookup_to_int(raw_slice[1], None)
                if sa_start is not None and sa_end is not None and sa_end >= sa_start:
                    anchors.append(
                        {
                            "token_i": global_idx,
                            "text": str(segments[global_idx] if global_idx < len(segments) else ""),
                            "slice": [sa_start, sa_end],
                            "source": "token_span",
                        }
                    )
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


# ---------------------------------------------------------------------------
# POS tag helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Debug helpers (language-agnostic; used by Japanese trace output)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# results_by_seg builder (generic)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------


def process_lookup_nlp_only(
    text: str,
    trankit_doc: dict,
    trankit_lang: str = "",
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
    ud_overlay = build_ud_overlay(sentences_data, segments, global_offset_by_sent_tok)

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

    return response
