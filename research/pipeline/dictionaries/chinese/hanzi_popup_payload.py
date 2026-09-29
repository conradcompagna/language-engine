"""
Chinese pronunciation/decomposition payload builder for hover popups.

Builds a language-specific payload that fits the existing generic
frontend pronunciation popup contract:
    {
      "overall_roman": "...",
      "syllables": [
        {
          "orth": "...",
          "roman": "...",
          "components": [{"ch": "...", "label": "...", ...}, ...],
          ...
        }
      ]
    }
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Dict, List, Optional


_HANZI_CHAR_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_WORD_RE = re.compile(r"[a-z]+")
_PINYIN_DIGIT_RE = re.compile(r"^([a-zv:]+?)([1-5])?$", re.IGNORECASE)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "or",
    "the",
    "to",
    "with",
}
_NO_GLYPH = "No glyph available"
_UNKNOWN_COMPONENT_SLOT = "□"
_MAX_DECOMP_DEPTH = 10
_HORIZONTAL_BASE_TYPES = {"a", "ra", "r3a", "wa", "ba"}
_VERTICAL_BASE_TYPES = {"d", "rd", "r3d", "wd", "bd"}
_SURROUND_BASE_TYPES = {
    "s", "st", "sb", "sl", "sr", "stl", "str", "sbl", "sbr",
    "lock", "rs", "rst", "rstl", "rsb", "rsbr", "cbl",
}


_HANZI_DECOMPOSER = None


def preload_hanzi_resources() -> bool:
    """
    Preload minimal hanzipy resources at app startup.

    Important: intentionally avoids hanzipy.HanziDictionary because it loads
    its own bundled CEDICT + frequency datasets. We only need decomposition
    + radical meaning, so we use a slim decomposer variant.
    """
    global _HANZI_DECOMPOSER
    if _HANZI_DECOMPOSER is not None:
        return True
    try:
        from hanzipy.decomposer import HanziDecomposer
    except Exception:
        _HANZI_DECOMPOSER = None
        return False

    class _SlimHanziDecomposer(HanziDecomposer):
        def __init__(self):
            self.characters = {}
            self.radicals = {}
            self.characters_with_component = {}
            self.noglyph = "No glyph available"
            # Load only decomposition/radical maps; skip compile_all_components().
            self.init_decomposition()

    try:
        _HANZI_DECOMPOSER = _SlimHanziDecomposer()
        return True
    except Exception:
        _HANZI_DECOMPOSER = None
        return False


def _get_hanzi_decomposer():
    if _HANZI_DECOMPOSER is not None:
        return _HANZI_DECOMPOSER
    preload_hanzi_resources()
    return _HANZI_DECOMPOSER


def _is_hanzi(ch: str) -> bool:
    return bool(ch and _HANZI_CHAR_RE.fullmatch(ch))


def _is_component_token(token: str) -> bool:
    if not token:
        return False
    t = str(token).strip()
    if not t or t == _NO_GLYPH:
        return False
    return len(t) == 1


def _clean_component_tokens(items: List[Any]) -> List[str]:
    out: List[str] = []
    for item in items or []:
        token = str(item or "").strip()
        if _is_component_token(token):
            out.append(token)
    return out


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _split_parts(text: str) -> List[str]:
    if not text:
        return []
    parts: List[str] = []
    raw = str(text)
    for chunk in raw.replace(";", "/").split("/"):
        c = " ".join(chunk.strip().split())
        if c and c != "...":
            parts.append(c)
    return parts


def _norm_decomp_type(decomp_type: str) -> str:
    return (decomp_type or "").strip().lower()


def _base_decomp_type(decomp_type: str) -> str:
    t = _norm_decomp_type(decomp_type)
    if "/" in t:
        t = t.split("/", 1)[0]
    return t


def _layout_child_boxes(
    decomp_type: str,
    child_count: int,
    x: float,
    y: float,
    w: float,
    h: float,
) -> List[tuple[float, float, float, float]]:
    if child_count <= 0:
        return []
    if child_count == 1:
        return [(x, y, w, h)]

    base = _base_decomp_type(decomp_type)

    if base in _HORIZONTAL_BASE_TYPES:
        step = w / child_count
        return [(x + i * step, y, step, h) for i in range(child_count)]

    if base in _VERTICAL_BASE_TYPES:
        step = h / child_count
        return [(x, y + i * step, w, step) for i in range(child_count)]

    if base in _SURROUND_BASE_TYPES:
        # Outer component first, then inner content.
        boxes: List[tuple[float, float, float, float]] = [(x, y, w, h)]
        if child_count == 1:
            return boxes

        inner_w = w * 0.64
        inner_h = h * 0.64
        inner_x = x + (w - inner_w) / 2.0
        inner_y = y + (h - inner_h) / 2.0

        # Bias inner box according to opening side.
        if base in {"st", "stl", "str", "rst", "rstl"}:
            inner_y = y + h * 0.32
        elif base in {"sb", "sbl", "sbr", "rsb", "rsbr"}:
            inner_y = y + h * 0.04

        if base in {"sl", "stl", "sbl"}:
            inner_x = x + w * 0.32
        elif base in {"sr", "str", "sbr"}:
            inner_x = x + w * 0.04

        inner_children = child_count - 1
        if inner_children == 1:
            boxes.append((inner_x, inner_y, inner_w, inner_h))
            return boxes

        step = inner_w / inner_children
        for i in range(inner_children):
            boxes.append((inner_x + i * step, inner_y, step, inner_h))
        return boxes

    # Unknown/overlaid types: keep declared order with subtle horizontal spread.
    step = w / child_count
    return [(x + i * step, y, step, h) for i in range(child_count)]


def _normalize_pinyin(pinyin: str) -> str:
    return " ".join((pinyin or "").strip().lower().replace("u:", "v").split())


def _strip_tone(pinyin: str) -> str:
    p = _normalize_pinyin(pinyin)
    m = _PINYIN_DIGIT_RE.match(p)
    if not m:
        return p
    return m.group(1) or p


def _split_pinyin(pinyin: str) -> List[str]:
    p = _normalize_pinyin(pinyin)
    if not p:
        return []
    return [tok for tok in p.split() if tok]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _sense_text_set(senses: List[str]) -> set[str]:
    words: set[str] = set()
    for sense in senses or []:
        for w in _WORD_RE.findall((sense or "").lower()):
            if len(w) > 2 and w not in _STOPWORDS:
                words.add(w)
    return words


def _best_short_gloss(senses: List[str]) -> str:
    if not senses:
        return ""
    cleaned = _dedupe_preserve_order(
        [" ".join(str(s or "").strip().split()) for s in senses if str(s or "").strip()]
    )
    return " / ".join(cleaned)


def _first_short_gloss(senses: List[str]) -> str:
    if not senses:
        return ""
    for sense in senses:
        cleaned = " ".join(str(sense or "").strip().split())
        if cleaned:
            return cleaned
    return ""


def _filter_entries_for_token_char(
    entries: List[Dict[str, Any]],
    token_char: str = "",
) -> List[Dict[str, Any]]:
    if not entries or not token_char:
        return entries

    trad_specific: List[Dict[str, Any]] = []
    simp_specific: List[Dict[str, Any]] = []
    neutral: List[Dict[str, Any]] = []

    for entry in entries:
        trad = str(entry.get("traditional", "") or "")
        simp = str(entry.get("simplified", "") or "")
        if trad == token_char and simp == token_char:
            neutral.append(entry)
        elif trad == token_char:
            trad_specific.append(entry)
        elif simp == token_char:
            simp_specific.append(entry)

    # Prefer entries that match the exact script/form from the token.
    if trad_specific and not simp_specific:
        return trad_specific + neutral
    if simp_specific and not trad_specific:
        return simp_specific + neutral
    if trad_specific and simp_specific:
        return trad_specific + simp_specific + neutral
    return entries


def _choose_cedict_entry(
    entries: List[Dict[str, Any]],
    preferred_pinyin: str,
    token_char: str = "",
) -> Optional[Dict[str, Any]]:
    entries = _filter_entries_for_token_char(entries, token_char=token_char)
    if not entries:
        return None
    preferred = _normalize_pinyin(preferred_pinyin)
    if preferred:
        for entry in entries:
            if _normalize_pinyin(entry.get("pinyin", "")) == preferred:
                return entry
        preferred_base = _strip_tone(preferred)
        for entry in entries:
            if _strip_tone(entry.get("pinyin", "")) == preferred_base:
                return entry
    return entries[0]


def _cedict_pinyins(cedict, ch: str, token_char: str = "") -> List[str]:
    if not ch:
        return []
    entries = list(cedict.lookup_all(ch) or [])
    entries = _filter_entries_for_token_char(entries, token_char=token_char)
    out: List[str] = []
    seen = set()
    for e in entries:
        p = _normalize_pinyin(e.get("pinyin", ""))
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _pinyin_initial(raw_syllable: str) -> str:
    if not raw_syllable:
        return ""
    if len(raw_syllable) >= 2 and raw_syllable[1:2] == "h":
        return raw_syllable[0:2]
    return raw_syllable[0:1]


def _pinyin_syllable_no_tone(raw_syllable: str) -> str:
    raw = _normalize_pinyin(raw_syllable)
    if not raw:
        return ""
    if raw[-1:] in {"1", "2", "3", "4", "5"}:
        return raw[:-1]
    return raw


def _pinyin_final(raw_syllable: str) -> str:
    syl = _pinyin_syllable_no_tone(raw_syllable)
    ini = _pinyin_initial(syl)
    if syl.startswith(ini):
        return syl[len(ini):]
    return syl


def _get_regularity_scale(char_pinyin: str, phonetic_pinyin: str) -> Optional[int]:
    """
    Mirror hanzipy regularity scale:
    0: no regularity
    1: exact match (with tone)
    2: syllable match (without tone)
    3: same initial
    4: same final
    """
    if not char_pinyin or not phonetic_pinyin:
        return None

    char_raw = _normalize_pinyin(char_pinyin)
    phon_raw = _normalize_pinyin(phonetic_pinyin)
    char_syl = _pinyin_syllable_no_tone(char_raw)
    phon_syl = _pinyin_syllable_no_tone(phon_raw)

    regularity = 0
    if char_syl == phon_syl:
        regularity = 2
        if char_raw == phon_raw:
            regularity = 1

    if regularity == 0:
        if _pinyin_final(char_raw) == _pinyin_final(phon_raw):
            regularity = 4
        elif _pinyin_initial(char_raw) == _pinyin_initial(phon_raw):
            regularity = 3

    return regularity


def _determine_phonetic_regularity(
    ch: str,
    decomposition: Dict[str, Any],
    cedict,
) -> Dict[str, Any]:
    """
    Local equivalent of hanzipy determine_phonetic_regularity that uses the
    app's already-loaded CEDICT source (no second dictionary load).
    """
    if not _is_hanzi(ch):
        return {}

    char_pinyins = _cedict_pinyins(cedict, ch, token_char=ch)
    if not char_pinyins:
        return {}

    # Partial fallback for pronunciation popup decomposition:
    # start from once/components, keep valid siblings, recursively resolve
    # only invalid children via radical fallback, then graphical for that
    # same child when radical does not materialize.
    components: List[str] = _select_components_with_level_fallback(ch, cedict)
    if not components:
        components = [ch]

    regularities: Dict[str, Any] = {}
    for component in components:
        comp = str(component or "")
        comp_pinyins = _cedict_pinyins(cedict, comp, token_char=comp) if _is_hanzi(comp) else []
        for pinyin in char_pinyins:
            regularities.setdefault(
                pinyin,
                {
                    "character": ch,
                    "component": [],
                    "phonetic_pinyin": [],
                    "regularity": [],
                },
            )
            if not comp_pinyins:
                regularities[pinyin]["component"].append(comp)
                regularities[pinyin]["phonetic_pinyin"].append(None)
                regularities[pinyin]["regularity"].append(None)
            else:
                for comp_pinyin in comp_pinyins:
                    regularities[pinyin]["component"].append(comp)
                    regularities[pinyin]["phonetic_pinyin"].append(comp_pinyin)
                    regularities[pinyin]["regularity"].append(
                        _get_regularity_scale(pinyin, comp_pinyin)
                    )
    return regularities


@lru_cache(maxsize=4096)
def _decomposition_for_char(ch: str) -> Dict[str, Any]:
    decomposer = _get_hanzi_decomposer()
    if decomposer is None or not _is_hanzi(ch):
        return {}
    try:
        res = decomposer.decompose(ch)
        if isinstance(res, dict):
            return res
    except Exception:
        pass
    return {}


def _select_components_with_level_fallback(ch: str, cedict) -> List[str]:
    """
    Simplified decomposition policy for pronunciation popup components.

    Rules:
    1) If `radical` contains the token itself, return [token].
    2) Try highest level (`once`, otherwise root `components`).
       If any item is unknown, discard that level and move to `radical`.
    3) Stay at `radical` level (never descend to `graphical`).
       Unknown radical slots are kept as placeholder markers.
    4) No carryover between levels, no deduplication.
    """
    if not _is_component_token(ch):
        return []

    decomposer = _get_hanzi_decomposer()
    if decomposer is None:
        return [ch]

    decomp = _decomposition_for_char(ch)
    raw_char = decomposer.characters.get(ch)
    root_components = (
        list(raw_char.get("components", []) or [])
        if isinstance(raw_char, dict)
        else []
    )
    once_raw = list(decomp.get("once", []) or [])
    radical_raw = list(decomp.get("radical", []) or [])
    # 1) Radical self short-circuit.
    for raw in radical_raw:
        tok = str(raw or "").strip()
        if tok == ch and _is_component_token(tok):
            return [ch]

    def _level_tokens(raw_items: List[Any]) -> tuple[List[str], bool]:
        tokens: List[str] = []
        has_unknown = False
        for raw in raw_items or []:
            tok = str(raw or "").strip()
            if not tok:
                continue
            tokens.append(tok)
            if not _is_component_token(tok):
                has_unknown = True
        return tokens, has_unknown

    # 2) Highest level: once, otherwise root components.
    highest_raw = once_raw if once_raw else root_components
    highest_tokens, highest_unknown = _level_tokens(highest_raw)
    if highest_tokens and not highest_unknown:
        return [tok for tok in highest_tokens if _is_component_token(tok)]

    # 3) Radical level.
    radical_out: List[str] = []
    for raw in radical_raw:
        tok = str(raw or "").strip()
        if not tok:
            continue
        if _is_component_token(tok):
            radical_out.append(tok)
        else:
            radical_out.append(_UNKNOWN_COMPONENT_SLOT)
    if radical_out:
        return radical_out

    # Final fallback.
    return [ch]


@lru_cache(maxsize=4096)
def _spatial_positions_for_char(ch: str) -> Dict[str, tuple[float, float, int]]:
    """
    Compute best (top-left-most) position for each component token found in
    the decomposition tree of `ch`.
    """
    decomposer = _get_hanzi_decomposer()
    if decomposer is None or not ch:
        return {}

    records: List[tuple[str, float, float, int]] = []

    def walk(node: str, x: float, y: float, w: float, h: float, depth: int, trail: tuple[str, ...]) -> None:
        token = str(node or "").strip()
        if _is_component_token(token):
            # Record the current node position even if decomposable.
            records.append((token, x + w / 2.0, y + h / 2.0, len(records)))

        if depth >= _MAX_DECOMP_DEPTH or token in trail:
            return

        raw = decomposer.characters.get(token)
        if not isinstance(raw, dict):
            return

        comps = list(raw.get("components", []) or [])
        if not comps:
            return

        boxes = _layout_child_boxes(raw.get("decomposition_type", ""), len(comps), x, y, w, h)
        if not boxes:
            return

        for i, comp in enumerate(comps):
            child = str(comp or "").strip()
            bx, by, bw, bh = boxes[i] if i < len(boxes) else boxes[-1]
            walk(child, bx, by, bw, bh, depth + 1, trail + (token,))

    walk(ch, 0.0, 0.0, 1.0, 1.0, 0, tuple())

    pos_by_comp: Dict[str, tuple[float, float, int]] = {}
    for comp, px, py, seq in records:
        cur = pos_by_comp.get(comp)
        cand_rank = (px, py, seq)  # column-major: left-to-right, then top-to-bottom
        if cur is None:
            pos_by_comp[comp] = (px, py, seq)
            continue
        cur_rank = (cur[0], cur[1], cur[2])
        if cand_rank < cur_rank:
            pos_by_comp[comp] = (px, py, seq)
    return pos_by_comp


@lru_cache(maxsize=4096)
def _root_horizontal_group_boxes(ch: str) -> tuple[tuple[float, float, float, float], ...]:
    """
    Return top-level child boxes when `ch` decomposes horizontally at root.

    This preserves root-level left-to-right grouping before applying
    left-to-right, then top-to-bottom ordering inside each group.
    """
    decomposer = _get_hanzi_decomposer()
    if decomposer is None or not ch:
        return tuple()
    raw = decomposer.characters.get(ch)
    if not isinstance(raw, dict):
        return tuple()

    comps = list(raw.get("components", []) or [])
    if len(comps) <= 1:
        return tuple()

    decomp_type = str(raw.get("decomposition_type", "") or "")
    if _base_decomp_type(decomp_type) not in _HORIZONTAL_BASE_TYPES:
        return tuple()

    boxes = _layout_child_boxes(decomp_type, len(comps), 0.0, 0.0, 1.0, 1.0)
    return tuple(boxes)


def _left_right_sort_key(
    pos: Optional[tuple[float, float, int]],
    original_idx: int,
) -> tuple[float, float, int, int]:
    if not pos:
        return (10**9, 10**9, 10**9, original_idx)
    px, py, seq = pos
    return (px, py, seq, original_idx)


def _group_index_for_x(
    px: float,
    boxes: List[tuple[float, float, float, float]],
) -> int:
    if not boxes:
        return 0

    eps = 1e-9
    best_idx = 0
    best_dist = float("inf")
    for i, (bx, _by, bw, _bh) in enumerate(boxes):
        left = bx - eps
        right = bx + bw + eps
        if left <= px <= right:
            return i
        cx = bx + bw / 2.0
        dist = abs(px - cx)
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx


def _order_components_spatially(ch: str, components: List[str]) -> List[str]:
    if not components:
        return []
    pos_by_comp = _spatial_positions_for_char(ch)
    if not pos_by_comp:
        return components[:]

    indexed = list(enumerate(components))
    root_boxes = list(_root_horizontal_group_boxes(ch))
    if root_boxes:
        grouped: List[List[tuple[int, str]]] = [[] for _ in root_boxes]
        ungrouped: List[tuple[int, str]] = []

        for idx, comp in indexed:
            pos = pos_by_comp.get(comp)
            if not pos:
                ungrouped.append((idx, comp))
                continue
            gidx = _group_index_for_x(pos[0], root_boxes)
            grouped[gidx].append((idx, comp))

        ordered: List[str] = []
        for g in grouped:
            for _idx, comp in sorted(
                g,
                key=lambda pair: _left_right_sort_key(pos_by_comp.get(pair[1]), pair[0]),
            ):
                ordered.append(comp)

        for _idx, comp in sorted(
            ungrouped,
            key=lambda pair: _left_right_sort_key(pos_by_comp.get(pair[1]), pair[0]),
        ):
            ordered.append(comp)

        if ordered:
            return ordered

    # Default ordering for single-glyph / non-horizontal roots:
    # left-to-right first, then top-to-bottom.
    return [
        comp
        for _idx, comp in sorted(
            indexed,
            key=lambda pair: _left_right_sort_key(pos_by_comp.get(pair[1]), pair[0]),
        )
    ]


@lru_cache(maxsize=4096)
def _radical_meaning(component: str) -> str:
    decomposer = _get_hanzi_decomposer()
    if decomposer is None or not _is_component_token(component):
        return ""
    try:
        meaning = decomposer.get_radical_meaning(component)
    except Exception:
        return ""
    if isinstance(meaning, str):
        m = meaning.strip()
        if m.lower() in {"unknown", "none", "n/a"}:
            return ""
        return m
    return ""


def _pick_pron_record(
    regularity_map: Dict[str, Any],
    char_pinyin: str,
) -> Dict[str, Any]:
    if not regularity_map:
        return {}
    preferred = _normalize_pinyin(char_pinyin)
    preferred_base = _strip_tone(preferred)

    def _score(pron: str, data: Dict[str, Any]) -> tuple:
        p = _normalize_pinyin(pron)
        p_base = _strip_tone(p)
        reg_raw = data.get("regularity", []) or []
        reg_vals = []
        for r in reg_raw:
            reg_vals.append(_safe_int(r, default=0))
        max_reg = max(reg_vals) if reg_vals else 0
        exact = 1 if preferred and p == preferred else 0
        base = 1 if preferred_base and p_base == preferred_base else 0
        return (exact, base, max_reg)

    best_key = max(
        regularity_map.keys(),
        key=lambda k: _score(k, regularity_map.get(k, {})),
    )
    best = regularity_map.get(best_key, {})
    if isinstance(best, dict):
        best = dict(best)
        best["selected_pinyin"] = _normalize_pinyin(best_key)
        return best
    return {}


def _choose_phonetic_root(
    target_char: str,
    target_pinyin: str,
    target_senses: List[str],
    components: List[Dict[str, Any]],
) -> str:
    """
    Pick the most likely phonetic root.

    Heuristic:
    - strong preference for high regularity
    - prefer pinyin base match with target character
    - demote components whose gloss words overlap dictionary senses
      (these are often semantic/radical contributors)
    """
    if not components:
        return ""
    target_base = _strip_tone(target_pinyin)
    target_words = _sense_text_set(target_senses)

    best_char = ""
    best_score = float("-inf")
    seen = set()
    for comp in components:
        c = comp.get("ch", "")
        if not c or c in seen:
            continue
        seen.add(c)
        reg = _safe_int(comp.get("regularity", 0), default=0)
        comp_pinyin = comp.get("phonetic_pinyin", "") or comp.get("roman", "")
        comp_base = _strip_tone(comp_pinyin)
        radical_gloss = (comp.get("radical_gloss") or "").lower()
        dict_gloss = (comp.get("dict_gloss") or "").lower()
        overlap = 0
        if target_words:
            overlap += len(_sense_text_set([radical_gloss]).intersection(target_words))
            overlap += len(_sense_text_set([dict_gloss]).intersection(target_words))

        score = 0.0
        score += 2.0 * reg
        if target_base and comp_base == target_base:
            score += 1.0
        if c == target_char:
            score -= 0.5
        score -= 0.6 * overlap

        if score > best_score:
            best_score = score
            best_char = c

    if best_score <= 0:
        return ""
    return best_char


def _build_component_label(
    component: Dict[str, Any],
    is_phonetic_root: bool,
) -> str:
    radical_gloss = component.get("radical_gloss", "")
    dict_gloss = component.get("dict_gloss", "")
    phonetic_pinyin = component.get("phonetic_pinyin", "")

    # Prefer radical glosses. If none exist, fall back to the first dict gloss.
    if radical_gloss:
        gloss_parts = _dedupe_preserve_order(_split_parts(radical_gloss))
    else:
        gloss_parts = _dedupe_preserve_order(_split_parts(dict_gloss))
    gloss = " / ".join(gloss_parts)
    parts = []
    if gloss:
        parts.append(gloss)
    if phonetic_pinyin:
        parts.append(phonetic_pinyin)
    return " / ".join(parts)


def _build_char_syllable(
    ch: str,
    cedict,
    fallback_pinyin: str,
) -> Dict[str, Any]:
    char_entries = list(cedict.lookup_all(ch) or [])
    entry = _choose_cedict_entry(char_entries, fallback_pinyin, token_char=ch)
    char_pinyin = _normalize_pinyin((entry or {}).get("pinyin", "") or fallback_pinyin)
    char_senses = list((entry or {}).get("senses", []) or [])

    decomposition = _decomposition_for_char(ch)
    regularity_map = _determine_phonetic_regularity(ch, decomposition, cedict)
    pron_record = _pick_pron_record(regularity_map, char_pinyin)

    raw_components = list(pron_record.get("component", []) or [])
    raw_phonetic = list(pron_record.get("phonetic_pinyin", []) or [])
    raw_regularity = list(pron_record.get("regularity", []) or [])

    # Partial fallback for pronunciation component selection.
    greedy_components = _select_components_with_level_fallback(ch, cedict)
    component_order = [c for c in greedy_components if _is_component_token(c)]
    if not component_order:
        component_order = [
            str(c or "").strip()
            for c in raw_components
            if _is_component_token(str(c or "").strip())
        ]
    # Keep HanziPy/native decomposition order. Do not re-sort spatially.

    component_slots: Dict[str, Dict[str, Any]] = {}
    component_sequence: List[str] = []

    def ensure_component_slot(comp_ch: str) -> Dict[str, Any]:
        if comp_ch in component_slots:
            return component_slots[comp_ch]
        if comp_ch == _UNKNOWN_COMPONENT_SLOT:
            slot = {
                "head": comp_ch,
                "ch": comp_ch,
                "roman": "",
                "phonetic_pinyin": "",
                "regularity": 0,
                "radical_gloss": "",
                "dict_gloss": "",
                "rad_gloss": "",
                "role": "unknown_slot",
                "_radical_gloss_parts": [],
                "_dict_gloss_parts": [],
                "_fallback_dict_gloss": "",
                "_phonetic_variants": [],
                "_entry_pinyins": [],
                "_phonetic_strength": 0,
            }
            component_slots[comp_ch] = slot
            return slot
        comp_entries = list(cedict.lookup_all(comp_ch) or [])
        comp_entry = _choose_cedict_entry(comp_entries, "", token_char=comp_ch)
        comp_senses = list((comp_entry or {}).get("senses", []) or [])
        comp_gloss = _best_short_gloss(comp_senses)
        comp_first_gloss = _first_short_gloss(comp_senses)
        all_entry_pinyins = _dedupe_preserve_order(
            [_normalize_pinyin(e.get("pinyin", "")) for e in comp_entries if _normalize_pinyin(e.get("pinyin", ""))]
        )
        all_entry_glosses = []
        for e in comp_entries:
            g = _best_short_gloss(list(e.get("senses", []) or []))
            if g:
                all_entry_glosses.append(g)
        all_entry_glosses = _dedupe_preserve_order(all_entry_glosses)
        radical = _radical_meaning(comp_ch)
        slot = {
            "head": comp_ch,
            "ch": comp_ch,
            "roman": _normalize_pinyin((comp_entry or {}).get("pinyin", "")) or (all_entry_pinyins[0] if all_entry_pinyins else ""),
            "phonetic_pinyin": " / ".join(all_entry_pinyins),
            "regularity": 0,
            "radical_gloss": radical,
            "dict_gloss": comp_gloss,
            "rad_gloss": comp_gloss,
            "role": "component",
            "_radical_gloss_parts": [radical] if radical else [],
            "_dict_gloss_parts": all_entry_glosses if all_entry_glosses else ([comp_gloss] if comp_gloss else []),
            "_fallback_dict_gloss": comp_first_gloss,
            "_phonetic_variants": all_entry_pinyins[:],
            "_entry_pinyins": all_entry_pinyins[:],
            "_phonetic_strength": 0,
        }
        component_slots[comp_ch] = slot
        return slot

    for comp in component_order:
        ensure_component_slot(comp)
        component_sequence.append(comp)

    # Merge pronunciation/regularity rows into deduped component slots.
    for i, comp in enumerate(raw_components):
        comp_ch = str(comp or "").strip()
        if not _is_component_token(comp_ch):
            continue
        slot = ensure_component_slot(comp_ch)
        if comp_ch == _UNKNOWN_COMPONENT_SLOT or slot.get("role") == "unknown_slot":
            # Unknown placeholder must never acquire dictionary/pronunciation glosses.
            continue

        comp_pinyin = _normalize_pinyin(raw_phonetic[i] if i < len(raw_phonetic) else "")
        reg_scale = _safe_int(raw_regularity[i], default=0) if i < len(raw_regularity) else 0
        # hanzipy scale is 1(best) .. 4(weaker), so invert to strength.
        reg_strength = (5 - reg_scale) if reg_scale in (1, 2, 3, 4) else 0
        if reg_strength > slot.get("regularity", 0):
            slot["regularity"] = reg_strength

        if comp_pinyin:
            variants = slot.get("_phonetic_variants", [])
            if comp_pinyin not in variants:
                variants.append(comp_pinyin)
            if (
                not slot.get("phonetic_pinyin")
                or reg_strength > slot.get("_phonetic_strength", 0)
            ):
                slot["phonetic_pinyin"] = comp_pinyin
                slot["roman"] = comp_pinyin
                slot["_phonetic_strength"] = reg_strength

        # Merge extra glosses from alternate component dictionary entries.
        comp_entry = _choose_cedict_entry(
            list(cedict.lookup_all(comp_ch) or []),
            comp_pinyin,
            token_char=comp_ch,
        )
        comp_senses = list((comp_entry or {}).get("senses", []) or [])
        comp_gloss = _best_short_gloss(comp_senses)
        comp_first_gloss = _first_short_gloss(comp_senses)
        if comp_gloss and comp_gloss not in slot["_dict_gloss_parts"]:
            slot["_dict_gloss_parts"].append(comp_gloss)
        if not slot.get("_fallback_dict_gloss") and comp_first_gloss:
            slot["_fallback_dict_gloss"] = comp_first_gloss
        radical = _radical_meaning(comp_ch)
        if radical and radical not in slot["_radical_gloss_parts"]:
            slot["_radical_gloss_parts"].append(radical)

    # If we still have nothing, keep the character itself as the single component.
    if not component_sequence and _is_component_token(ch):
        ensure_component_slot(ch)
        component_sequence.append(ch)
    # Keep selected decomposition order exactly as returned by the selector.

    components: List[Dict[str, Any]] = []
    for comp_ch in component_sequence:
        base_slot = component_slots.get(comp_ch, {})
        if not base_slot:
            continue
        slot = dict(base_slot)
        pinyin_parts = _dedupe_preserve_order(
            (base_slot.get("_entry_pinyins", []) or [])
            + (base_slot.get("_phonetic_variants", []) or [])
        )
        radical_parts = base_slot.get("_radical_gloss_parts", []) or []
        fallback_dict_gloss = str(base_slot.get("_fallback_dict_gloss", "") or "").strip()
        slot["phonetic_pinyin"] = " / ".join(pinyin_parts)
        if not slot.get("roman") and pinyin_parts:
            slot["roman"] = pinyin_parts[0]
        slot["radical_gloss"] = " / ".join(_dedupe_preserve_order(_split_parts(" / ".join(radical_parts))))
        # Keep exactly one fallback dict gloss (first definition) for no-radical cases.
        slot["dict_gloss"] = fallback_dict_gloss
        slot["rad_gloss"] = slot["radical_gloss"] or fallback_dict_gloss
        slot.pop("_radical_gloss_parts", None)
        slot.pop("_dict_gloss_parts", None)
        slot.pop("_fallback_dict_gloss", None)
        slot.pop("_entry_pinyins", None)
        slot.pop("_phonetic_variants", None)
        slot.pop("_phonetic_strength", None)
        components.append(slot)

    phonetic_root = _choose_phonetic_root(ch, char_pinyin, char_senses, components)
    if not phonetic_root:
        real_components = [
            comp for comp in components
            if comp.get("role") != "unknown_slot"
        ]
        if len(real_components) == 1 and real_components[0].get("ch") == ch:
            # When decomposition resolves to the character itself
            # (radical self short-circuit), treat that as the root.
            phonetic_root = ch
    for comp in components:
        if comp.get("role") == "unknown_slot":
            comp["roman"] = ""
            comp["phonetic_pinyin"] = ""
            comp["radical_gloss"] = ""
            comp["dict_gloss"] = ""
            comp["rad_gloss"] = ""
            comp["label"] = ""
            comp["is_phonetic_root"] = False
            continue
        is_root = bool(phonetic_root and comp.get("ch") == phonetic_root)
        comp["is_phonetic_root"] = is_root
        radical_gloss = str(comp.get("radical_gloss", "") or "").strip()
        fallback_dict_gloss = str(comp.get("dict_gloss", "") or "").strip()
        if radical_gloss:
            comp["dict_gloss"] = ""
            comp["rad_gloss"] = radical_gloss
        else:
            comp["dict_gloss"] = fallback_dict_gloss
            comp["rad_gloss"] = fallback_dict_gloss
        comp["label"] = _build_component_label(comp, is_root)

    # Greedy radical/component surface used for this character.
    radicals = [
        c for c in component_sequence
        if _is_component_token(c) and c != _UNKNOWN_COMPONENT_SLOT
    ]

    return {
        "orth": ch,
        "roman": char_pinyin,
        "components": components,
        "phonetic_root": phonetic_root or None,
        "phonetic_source_pinyin": pron_record.get("selected_pinyin") or char_pinyin or None,
        "radicals": radicals,
        "radical_glosses": {r: _radical_meaning(r) for r in radicals if _radical_meaning(r)},
        "definition_glosses": char_senses[:3],
        "decomposition": decomposition if isinstance(decomposition, dict) else {},
    }


def build_hanzi_pronunciation_payload(
    text: str,
    cedict,
    fallback_roman: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Build pronunciation/decomposition payload for Chinese text.

    Returns None if no Hanzi characters are present or hanzipy is unavailable.
    """
    if _get_hanzi_decomposer() is None:
        return None
    if not text:
        return None

    chars = [ch for ch in text if _is_hanzi(ch)]
    if not chars:
        return None

    fallback_parts = _split_pinyin(fallback_roman)
    syllables = []
    for i, ch in enumerate(chars):
        preferred = fallback_parts[i] if i < len(fallback_parts) else ""
        syllables.append(_build_char_syllable(ch, cedict, preferred))

    overall_roman = " ".join(
        s.get("roman", "") for s in syllables if s.get("roman", "")
    ).strip()
    if not overall_roman:
        overall_roman = _normalize_pinyin(fallback_roman)

    return {
        "overall_roman": overall_roman,
        "syllables": syllables,
    }
