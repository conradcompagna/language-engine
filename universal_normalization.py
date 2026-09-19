"""
Universal Unicode normalization + language-profile filtering bridge.

Design goal for remapping:
- Use a simple character offset remap with one map:
  model_index -> original_index.
- Keep universal normalization + filtering at router level.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


DEFAULT_NORMALIZATION_FORM = "NFKC"
# _OLD_ENGLISH_LEMMA_STOP_RE = re.compile(r"[\s(/]")  # disabled — OE lemma post-processing commented out

# Arabic diacritical marks (tashkeel, maddah, superscript alef, Quranic marks).
# Same ranges as ARABIC_STRIP_MARKS_RE in dictionary_normalization_layer.js.
_ARABIC_DIACRITICS_RE = re.compile(
    "[\u0610-\u061a\u0640\u064b-\u065f\u0670"
    "\u06d6-\u06dc\u06df-\u06e4\u06e7-\u06e8"
    "\u06ea-\u06ed\u08ca-\u08e1\u08e3-\u08ff]"
)

_FORCED_STRIP_PUNCTUATION_LANGS = frozenset()

# ---------------------------------------------------------------------------
# Sanskrit Devanagari → IAST transliteration.
#
# Run at the very start of preprocessing so Trankit (IAST-only model) never
# sees any Devanagari. The IAST output also becomes the canonical
# original_text, so downstream output/display is IAST.
# ---------------------------------------------------------------------------

_DEVA_VOWELS = {
    "अ": "a",
    "आ": "ā",
    "इ": "i",
    "ई": "ī",
    "उ": "u",
    "ऊ": "ū",
    "ऋ": "ṛ",
    "ॠ": "ṝ",
    "ऌ": "ḷ",
    "ॡ": "ḹ",
    "ऎ": "e",
    "ए": "e",
    "ऐ": "ai",
    "ऒ": "o",
    "ओ": "o",
    "औ": "au",
    "ऍ": "e",
    "ऑ": "o",
}

_DEVA_VOWEL_SIGNS = {
    "ा": "ā",
    "ि": "i",
    "ी": "ī",
    "ु": "u",
    "ू": "ū",
    "ृ": "ṛ",
    "ॄ": "ṝ",
    "ॢ": "ḷ",
    "ॣ": "ḹ",
    "ॆ": "e",
    "े": "e",
    "ै": "ai",
    "ॊ": "o",
    "ो": "o",
    "ौ": "au",
    "ॅ": "e",
    "ॉ": "o",
}

_DEVA_CONSONANTS = {
    "क": "k",
    "ख": "kh",
    "ग": "g",
    "घ": "gh",
    "ङ": "ṅ",
    "च": "c",
    "छ": "ch",
    "ज": "j",
    "झ": "jh",
    "ञ": "ñ",
    "ट": "ṭ",
    "ठ": "ṭh",
    "ड": "ḍ",
    "ढ": "ḍh",
    "ण": "ṇ",
    "त": "t",
    "थ": "th",
    "द": "d",
    "ध": "dh",
    "न": "n",
    "प": "p",
    "फ": "ph",
    "ब": "b",
    "भ": "bh",
    "म": "m",
    "य": "y",
    "र": "r",
    "ल": "l",
    "व": "v",
    "श": "ś",
    "ष": "ṣ",
    "स": "s",
    "ह": "h",
    "ळ": "ḷ",
    # Precomposed nukta consonants (fold to base for Sanskrit lookup)
    "क़": "k",
    "ख़": "kh",
    "ग़": "g",
    "ज़": "j",
    "ड़": "ḍ",
    "ढ़": "ḍh",
    "फ़": "ph",
    "य़": "y",
}

_DEVA_SIGNS = {
    "ं": "ṃ",
    "ः": "ḥ",
    "ँ": "ṃ",
    "\u0901": "ṃ",
    "\ua8f2": "ṃ",
    "\ua8f3": "ṃ",
    "ऽ": "'",
    "ॐ": "oṃ",
    "०": "0",
    "१": "1",
    "२": "2",
    "३": "3",
    "४": "4",
    "५": "5",
    "६": "6",
    "७": "7",
    "८": "8",
    "९": "9",
    "।": "|",
    "॥": "||",
    "॰": "",
}

_DEVA_VIRAMA = "\u094d"
_DEVA_NUKTA = "\u093c"

# Vedic accents, cantillation, stress marks — strip before transliterating.
_DEVA_STRIP_RE = re.compile("[\u0951-\u0954\u0971\u1cd0-\u1cff\ua8e0-\ua8f1\ua8f4-\ua8fb]")
_DEVA_DETECT_RE = re.compile("[\u0900-\u097f\ua8e0-\ua8ff]")


def _devanagari_to_iast(text: str) -> str:
    """Transliterate Devanagari → IAST, matching devanagariToIast() in
    static/dictionary_normalization_layer.js (but Python-side, so it can run
    before Trankit)."""
    if not text:
        return text
    src = _DEVA_STRIP_RE.sub("", text).replace(_DEVA_NUKTA, "")
    out_parts: list[str] = []
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        if ch in _DEVA_CONSONANTS:
            out_parts.append(_DEVA_CONSONANTS[ch])
            nxt = src[i + 1] if i + 1 < n else ""
            if nxt == _DEVA_VIRAMA:
                i += 2
                continue
            if nxt and nxt in _DEVA_VOWEL_SIGNS:
                out_parts.append(_DEVA_VOWEL_SIGNS[nxt])
                i += 2
                continue
            out_parts.append("a")  # inherent vowel
            i += 1
            continue
        if ch in _DEVA_VOWELS:
            out_parts.append(_DEVA_VOWELS[ch])
            i += 1
            continue
        if ch in _DEVA_SIGNS:
            out_parts.append(_DEVA_SIGNS[ch])
            i += 1
            continue
        if ch == _DEVA_VIRAMA:
            i += 1
            continue
        out_parts.append(ch)
        i += 1
    return "".join(out_parts)


def _is_sanskrit_language_key(language_key: str) -> bool:
    return language_key == "sa"


_LANGUAGE_ALIASES = {
    "zh": "zh",
    "chinese": "zh",
    "ja": "ja",
    "japanese": "ja",
    "ko": "ko",
    "korean": "ko",
    "vi": "vi",
    "vietnamese": "vi",
    "lzh": "lzh",
    "classical": "lzh",
    # Wiktionary general pipeline languages
    "tr": "tr",
    "turkish": "tr",
    "ta": "ta",
    "tamil": "ta",
    "te": "te",
    "telugu": "te",
    "fa": "fa",
    "persian": "fa",
    "mr": "mr",
    "marathi": "mr",
    "id": "id",
    "indonesian": "id",
    "hi": "hi",
    "hindi": "hi",
    "ar": "ar",
    "arabic": "ar",
    "th": "th",
    "thai": "th",
    "ga": "ga",
    "irish": "ga",
    "ang": "ang",
    "oldenglish": "ang",
    "old-english": "ang",
    "old english": "ang",
    # Ancient language aliases
    "grc": "grc",
    "ancient greek": "grc",
    "ancient-greek": "grc",
    "la": "la",
    "latin": "la",
    "sa": "sa",
    "sanskrit": "sa",
}


@dataclass(frozen=True)
class PreprocessContext:
    """Context for model-space -> original-space remapping."""

    original_text: str
    normalized_text: str
    model_text: str
    # model char index -> original char index
    model_to_orig: tuple[int, ...]
    changed: bool
    language_key: str = "generic"
    normalization_form: str = DEFAULT_NORMALIZATION_FORM


def normalize_text(text: str, normalization_form: str = DEFAULT_NORMALIZATION_FORM) -> str:
    """Normalize text to a standard Unicode form."""
    return unicodedata.normalize(normalization_form, text)


def strip_non_bmp(text: str) -> str:
    """Remove characters outside the Basic Multilingual Plane (U+0000–U+FFFF).

    Cuneiform, emoji, supplementary CJK, and other astral-plane characters
    are stripped so they never reach Trankit or dictionary pipelines.
    """
    return "".join(ch for ch in text if ord(ch) <= 0xFFFF)


def preprocess_text_for_language(
    text: str,
    language: Optional[str] = None,
    normalization_form: str = DEFAULT_NORMALIZATION_FORM,
) -> str:
    """Normalize + language-profile filter text for model/dictionary use."""
    context = build_preprocess_context(text, language, normalization_form)
    return context.model_text


def run_with_universal_normalization(
    text: str,
    handler: Callable[..., Any],
    *handler_args: Any,
    language: Optional[str] = None,
    normalization_form: str = DEFAULT_NORMALIZATION_FORM,
    strip_punctuation: bool = False,
    **handler_kwargs: Any,
) -> Any:
    """
    Normalize + filter before handler call, then remap output back to original text.

    Handler must accept text as first positional argument.
    """
    context = build_preprocess_context(
        text, language, normalization_form, strip_punctuation=strip_punctuation
    )

    text_for_handler = context.model_text if context.changed else context.original_text
    response = handler(text_for_handler, *handler_args, **handler_kwargs)
    response = _postprocess_response_for_language(response, context.language_key)
    remapped = remap_response_to_original(response, context)
    return remapped


def build_preprocess_context(
    text: str,
    language: Optional[str] = None,
    normalization_form: str = DEFAULT_NORMALIZATION_FORM,
    strip_punctuation: bool = False,
) -> PreprocessContext:
    """
    Build preprocessing context:
    original -> normalized -> model(filtered), with one model->original map.
    """
    language_key = _resolve_language_key(language)

    # Save the true original BEFORE any normalization so we can remap back to it.
    true_original = text

    # Build per-char normalization map from the true original.
    # Must run before whole-string normalization so we get true_orig_i -> normalized positions.
    norm = unicodedata.normalize
    per_char_norm: List[str] = []
    norm_to_orig_fast: List[int] = []
    for orig_i, ch in enumerate(true_original):
        piece = norm(normalization_form, ch)
        if not piece:
            continue
        per_char_norm.append(piece)
        norm_to_orig_fast.extend([orig_i] * len(piece))

    rebuilt = "".join(per_char_norm)

    # NFKC first so astral chars that decompose to BMP equivalents survive.
    # Then strip anything still astral — these cause offset desync and have
    # no valid representation in the pipeline.
    normalized = strip_non_bmp(norm(normalization_form, true_original))

    if rebuilt == normalized and len(norm_to_orig_fast) == len(normalized):
        norm_to_orig = norm_to_orig_fast
    else:
        # The per-char pass gives rebuilt_pos -> true_orig_i. Whole-string
        # normalization may compose adjacent chars, so rebuilt != normalized.
        # Chain: normalized_pos -> rebuilt_pos -> true_orig_i
        norm_to_orig = _chain_via_renormalize(
            rebuilt, normalized, norm_to_orig_fast, normalization_form
        )

    # Sanskrit: Trankit model is IAST-only, so convert any Devanagari to IAST.
    # The IAST output becomes the canonical original_text — source Devanagari discarded.
    if _is_sanskrit_language_key(language_key) and _DEVA_DETECT_RE.search(normalized):
        normalized = _devanagari_to_iast(normalized)
        true_original = normalized
        norm_to_orig = list(range(len(normalized)))

    model_text, model_to_norm = filter_text_for_language(
        normalized, language_key, strip_punctuation=strip_punctuation
    )
    model_to_orig: List[int] = []
    orig_len = len(true_original)
    for norm_i in model_to_norm:
        if 0 <= norm_i < len(norm_to_orig):
            model_to_orig.append(_clamp(norm_to_orig[norm_i], 0, max(orig_len - 1, 0)))
        else:
            model_to_orig.append(0 if orig_len == 0 else orig_len - 1)

    changed = model_text != true_original
    return PreprocessContext(
        original_text=true_original,
        normalized_text=normalized,
        model_text=model_text,
        model_to_orig=tuple(model_to_orig),
        changed=changed,
        language_key=language_key,
        normalization_form=normalization_form,
    )


def filter_text_for_language(
    text: str,
    language: Optional[str] = None,
    strip_punctuation: bool = False,
) -> tuple[str, List[int]]:
    """Filter text by language profile.

    When strip_punctuation is True, punctuation and symbols are removed before
    sending to the transformer (recommended for some classical languages such as
    Sanskrit and Literary Chinese whose models were trained on unpunctuated text).
    Otherwise all BMP characters pass through unchanged (non-BMP already stripped).

    Returns (filtered_text, filtered_index -> normalized_index map).
    """
    out: List[str] = []
    model_to_norm: List[int] = []

    language_key = _resolve_language_key(language)
    strip_punctuation = strip_punctuation or language_key in _FORCED_STRIP_PUNCTUATION_LANGS
    strip_arabic = language_key == "ar"

    if strip_punctuation:
        for norm_i, ch in enumerate(text):
            if _is_ancient_keep_char(ch):
                out.append(ch)
                model_to_norm.append(norm_i)
    else:
        for norm_i, ch in enumerate(text):
            if strip_arabic and _ARABIC_DIACRITICS_RE.match(ch):
                continue
            out.append(ch)
            model_to_norm.append(norm_i)

    return "".join(out), model_to_norm


def _is_ancient_keep_char(ch: str) -> bool:
    """Keep letters, combining marks, digits, and whitespace; strip everything else."""
    if ch.isspace():
        return True
    cat = unicodedata.category(ch)
    return bool(cat) and cat[0] in ("L", "M", "N")


def remap_response_to_original(response: Any, context: PreprocessContext) -> Any:
    """
    Remap known response fields from model-space back to original input.

    Uses simple character offset mapping:
      orig_start = model_to_orig[start]
      orig_end = model_to_orig[end-1] + 1
    """
    if not isinstance(response, dict):
        return response

    payload = response

    if "q" in payload:
        payload["q"] = context.original_text
    if "display_text" in payload:
        payload["display_text"] = context.original_text

    segment_offsets = payload.get("segment_offsets")
    segments = payload.get("segments")

    if isinstance(segment_offsets, list):
        _remap_segment_offsets_in_place(
            segment_offsets, context.model_to_orig, len(context.original_text)
        )

    # MWT mismatched-child indices: token has a `surface_anchor` whose `slice`
    # is in model-space and points at the parent's surface span. The child text
    # itself (Trankit's unsandhied form) lives on segments[i] and on
    # ud_overlay.tokens[i].text — those must NOT be clobbered by the
    # rebuild-from-offsets step below, because their offsets point at the
    # parent slice, not at the child glyphs.
    mwt_mismatch_seg_indices = _collect_mwt_mismatch_seg_indices(payload)

    _remap_surface_anchors_in_place(payload, context.model_to_orig, context.original_text)

    # Always rebuild segment strings from original_text using the (possibly remapped)
    # offsets — Trankit normalizes whitespace internally (e.g. \n → space) regardless
    # of whether our own normalization pipeline changed anything.
    if isinstance(segments, list) and isinstance(segment_offsets, list):
        _rebuild_segments_from_offsets_in_place(
            context.original_text,
            segment_offsets,
            segments,
            skip_indices=mwt_mismatch_seg_indices,
        )
        _sync_results_with_segments(payload, segments, skip_indices=mwt_mismatch_seg_indices)
        _sync_ud_overlay_with_segments(payload, segments, skip_indices=mwt_mismatch_seg_indices)
    return payload


def map_model_range_to_original(
    start: int,
    end: int,
    context: PreprocessContext,
) -> List[int]:
    """Map model [start, end) offsets to original [start, end)."""
    return _map_model_range_with_single_map(
        start, end, context.model_to_orig, len(context.original_text)
    )


def _postprocess_response_for_language(
    response: Any,
    language_key: str,
) -> Any:
    if not isinstance(response, dict):
        return response

    # if language_key == "ang":
    #     _normalize_old_english_payload_lemmas(response)

    return response


# def _normalize_old_english_payload_lemmas(payload: Dict[str, Any]) -> None:
#     ud_overlay = payload.get("ud_overlay")
#     if not isinstance(ud_overlay, dict):
#         return
#
#     tokens = ud_overlay.get("tokens")
#     if not isinstance(tokens, list):
#         return
#
#     for token in tokens:
#         if not isinstance(token, dict):
#             continue
#         _normalize_old_english_lemma_entry(token)
#
#
# def _normalize_old_english_lemma_entry(entry: Dict[str, Any]) -> None:
#     raw_lemma = str(entry.get("lemma", "") or "").strip()
#     if not raw_lemma:
#         return
#
#     lemma, suffix = _normalize_old_english_lemma_text(raw_lemma)
#     if not lemma:
#         return
#
#     entry["lemma_raw"] = raw_lemma
#     entry["lemma"] = lemma
#
#     if "lemma_form" in entry and str(entry.get("lemma_form", "") or "").strip():
#         entry["lemma_form"] = lemma
#
#     if suffix:
#         entry["lemma_suffix"] = suffix
#     else:
#         entry.pop("lemma_suffix", None)
#
#
# def _normalize_old_english_lemma_text(raw_lemma: str) -> tuple[str, str]:
#     lemma_text = str(raw_lemma or "").strip()
#     if not lemma_text:
#         return "", ""
#
#     match = _OLD_ENGLISH_LEMMA_STOP_RE.search(lemma_text)
#     if not match:
#         return lemma_text, ""
#
#     stop = match.start()
#     lemma = lemma_text[:stop].strip()
#     if not lemma:
#         return lemma_text, ""
#
#     return lemma, lemma_text[stop:]


def _collect_mwt_mismatch_seg_indices(payload: Dict[str, Any]) -> set:
    """Indices of segments whose ud_overlay token carries a `surface_anchor`.

    For these segments, segments[i] / ud_overlay.tokens[i].text hold Trankit's
    unsandhied child text. The token's offset/segment_offsets[i] points at the
    parent's surface span, so rebuilding segments[i] from original_text[span]
    would clobber the child text with the parent slice.
    """
    out: set = set()
    ud_overlay = payload.get("ud_overlay")
    if not isinstance(ud_overlay, dict):
        return out
    tokens = ud_overlay.get("tokens")
    if not isinstance(tokens, list):
        return out
    for token in tokens:
        if not isinstance(token, dict):
            continue
        if not isinstance(token.get("surface_anchor"), dict):
            continue
        token_i = token.get("i")
        if isinstance(token_i, int) and token_i >= 0:
            out.add(token_i)
    return out


def _remap_surface_anchors_in_place(
    payload: Dict[str, Any],
    model_to_orig: tuple[int, ...],
    original_text: str,
) -> None:
    """Remap each surface_anchor.slice from model-space to original-text space
    and rebuild surface_anchor.text from the remapped slice. The anchor span is
    what reader.js / canonical_renderer.js use to construct the parent surface
    fill hits, so it must end up in the same coordinate system as everything
    else after normalization."""
    ud_overlay = payload.get("ud_overlay")
    if not isinstance(ud_overlay, dict):
        return
    tokens = ud_overlay.get("tokens")
    if not isinstance(tokens, list):
        return
    orig_len = len(original_text)
    for token in tokens:
        if not isinstance(token, dict):
            continue
        anchor = token.get("surface_anchor")
        if not isinstance(anchor, dict):
            continue
        norm = _normalize_offset_span(anchor.get("slice"))
        if norm is None:
            continue
        mapped = _map_model_range_with_single_map(norm[0], norm[1], model_to_orig, orig_len)
        anchor["slice"] = mapped
        s = _clamp(mapped[0], 0, orig_len)
        e = _clamp(mapped[1], s, orig_len)
        anchor["text"] = original_text[s:e]


def _remap_segment_offsets_in_place(
    segment_offsets: List[Any],
    model_to_orig: tuple[int, ...],
    original_len: int,
) -> None:
    for idx, span in enumerate(segment_offsets):
        norm = _normalize_offset_span(span)
        if norm is None:
            continue
        mapped = _map_model_range_with_single_map(norm[0], norm[1], model_to_orig, original_len)
        if (
            not isinstance(span, list)
            or len(span) < 2
            or span[0] != mapped[0]
            or span[1] != mapped[1]
        ):
            segment_offsets[idx] = mapped


def _map_model_range_with_single_map(
    start: int,
    end: int,
    model_to_orig: tuple[int, ...],
    original_len: int,
) -> List[int]:
    mlen = len(model_to_orig)
    if mlen == 0:
        return [0, 0]

    start = _clamp(start, 0, mlen)
    end = _clamp(end, start, mlen)

    if start >= mlen:
        orig_start = original_len
    else:
        orig_start = _clamp(model_to_orig[start], 0, original_len)

    if end <= 0:
        orig_end = orig_start
    elif end - 1 < mlen:
        orig_end = _clamp(model_to_orig[end - 1] + 1, 0, original_len)
    else:
        orig_end = original_len

    if orig_end < orig_start:
        orig_end = orig_start
    return [orig_start, orig_end]


def _rebuild_segments_from_offsets_in_place(
    original_text: str,
    segment_offsets: List[Any],
    segments: List[Any],
    skip_indices: Optional[set] = None,
) -> None:
    orig_len = len(original_text)
    if len(segments) < len(segment_offsets):
        segments.extend([""] * (len(segment_offsets) - len(segments)))

    for idx, span in enumerate(segment_offsets):
        if skip_indices and idx in skip_indices:
            continue
        norm = _normalize_offset_span(span)
        if norm is None or idx >= len(segments):
            continue
        start = _clamp(norm[0], 0, orig_len)
        end = _clamp(norm[1], start, orig_len)
        segments[idx] = original_text[start:end]


def _normalize_offset_span(span: Any) -> Optional[List[int]]:
    if not isinstance(span, (list, tuple)) or len(span) < 2:
        return None
    try:
        return [int(span[0]), int(span[1])]
    except (TypeError, ValueError):
        return None


def _sync_results_with_segments(
    payload: Dict[str, Any],
    segments: List[Any],
    skip_indices: Optional[set] = None,
) -> None:
    results_by_seg = payload.get("results_by_seg")
    if isinstance(results_by_seg, list):
        for idx, entry in enumerate(results_by_seg):
            if skip_indices and idx in skip_indices:
                continue
            if isinstance(entry, dict) and idx < len(segments):
                entry["head"] = segments[idx]

    results = payload.get("results")
    if isinstance(results, list):
        for entry in results:
            if not isinstance(entry, dict):
                continue
            seg_i = entry.get("seg_i")
            if skip_indices and isinstance(seg_i, int) and seg_i in skip_indices:
                continue
            if isinstance(seg_i, int) and 0 <= seg_i < len(segments):
                entry["head"] = segments[seg_i]


def _sync_ud_overlay_with_segments(
    payload: Dict[str, Any],
    segments: List[Any],
    skip_indices: Optional[set] = None,
) -> None:
    ud_overlay = payload.get("ud_overlay")
    if not isinstance(ud_overlay, dict):
        return

    tokens = ud_overlay.get("tokens")
    if isinstance(tokens, list):
        for token in tokens:
            if not isinstance(token, dict):
                continue
            token_i = token.get("i")
            if skip_indices and isinstance(token_i, int) and token_i in skip_indices:
                continue
            if isinstance(token_i, int) and 0 <= token_i < len(segments):
                token["text"] = segments[token_i]

    ents = ud_overlay.get("ents")
    if isinstance(ents, list):
        seg_count = len(segments)
        for ent in ents:
            if not isinstance(ent, dict):
                continue
            start = ent.get("start")
            end = ent.get("end")
            if not isinstance(start, int) or not isinstance(end, int):
                continue
            start = _clamp(start, 0, seg_count)
            end = _clamp(end, start, seg_count)
            ent["text"] = "".join(str(s) for s in segments[start:end])


def _chain_via_renormalize(
    rebuilt: str,
    normalized: str,
    rebuilt_to_orig: List[int],
    normalization_form: str,
) -> List[int]:
    """
    Map normalized positions back to original positions by chaining:
      normalized_pos -> rebuilt_pos -> orig_i

    `rebuilt` is the concatenation of per-char normalizations (may still have
    decomposed sequences that whole-string normalization would compose).
    `normalized` = NFKC(original) = NFKC(rebuilt).

    We walk `rebuilt` consuming characters that compose into each `normalized`
    character, inheriting the earliest original index from the consumed span.
    """
    norm_func = unicodedata.normalize
    norm_to_orig: List[int] = []
    ri = 0  # cursor into rebuilt
    rlen = len(rebuilt)

    for ni in range(len(normalized)):
        nch = normalized[ni]
        # Try increasing spans of rebuilt chars until they normalize to nch.
        # Typical case: 1 char (identical) or 2-3 chars (base + combining).
        matched = False
        for span in range(1, rlen - ri + 1):
            candidate = rebuilt[ri : ri + span]
            composed = norm_func(normalization_form, candidate)
            if composed == nch:
                # Map this normalized char to the earliest original index
                # covered by the consumed rebuilt span.
                orig_i = rebuilt_to_orig[ri] if ri < len(rebuilt_to_orig) else 0
                norm_to_orig.append(orig_i)
                ri += span
                matched = True
                break
            # If composed is already longer than 1 char we overshot.
            if len(composed) > 1:
                break
        if not matched:
            # Fallback: take one rebuilt char, map it through.
            orig_i = rebuilt_to_orig[ri] if ri < len(rebuilt_to_orig) else 0
            norm_to_orig.append(orig_i)
            ri += 1

    return norm_to_orig


def _build_normalized_to_original_map(normalized: str, original: str) -> List[int]:
    """
    Build normalized-index -> original-index map.

    This is intentionally simple and robust for remapping.
    """
    if not normalized:
        return []
    if not original:
        return [0] * len(normalized)

    max_orig_idx = len(original) - 1
    mapping = [0] * len(normalized)
    assigned = [False] * len(normalized)

    matcher = difflib.SequenceMatcher(a=normalized, b=original, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if i1 == i2:
            continue

        if tag == "equal":
            for off in range(i2 - i1):
                idx = i1 + off
                mapping[idx] = _clamp(j1 + off, 0, max_orig_idx)
                assigned[idx] = True
        elif tag == "replace":
            n_span = i2 - i1
            o_span = max(1, j2 - j1)
            for off in range(n_span):
                idx = i1 + off
                mapped = j1 + (off * o_span) // n_span
                if mapped >= j2:
                    mapped = j2 - 1
                mapping[idx] = _clamp(mapped, 0, max_orig_idx)
                assigned[idx] = True
        elif tag == "delete":
            anchor = _clamp(j1, 0, max_orig_idx)
            for idx in range(i1, i2):
                mapping[idx] = anchor
                assigned[idx] = True
        # "insert": no chars in normalized span.

    last = 0
    for i in range(len(mapping)):
        if not assigned[i]:
            mapping[i] = last
        val = _clamp(mapping[i], 0, max_orig_idx)
        if i > 0 and val < mapping[i - 1]:
            val = mapping[i - 1]
        mapping[i] = val
        last = val

    return mapping


def _resolve_language_key(language: Optional[str]) -> str:
    if not language:
        return "generic"
    key = str(language).strip().lower()
    return _LANGUAGE_ALIASES.get(key, key)


def _clamp(value: int, low: int, high: int) -> int:
    if value < low:
        return low
    if value > high:
        return high
    return value
