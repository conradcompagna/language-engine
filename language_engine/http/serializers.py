"""Reader HTTP serializers."""

import copy
import json
import re
import unicodedata
from typing import Any, Mapping, Sequence

from flask import request

_LOOKUP_UPOS_COLORS = {
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


_ACTUAL_RESOLUTION_LABELS = {
    "exact_match": "exact match",
    "greedy_segmentation": "greedy segmentation",
    "exact_lemma_match": "exact lemma match",
    "greedy_lemma_match": "partial lemma match + greedy segmentation",
    "lemma_override": "lemma override",
    "lemma_partial_override": "exact lemma parts + greedy gaps",
}


def _dedupe_text_list(values: Sequence[Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _normalize_selected_sources(
    raw_sources: Sequence[Any] | None, single_source: Any = ""
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in list(raw_sources or []):
        text = str(raw or "").strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    one = str(single_source or "").strip().lower()
    if one and one not in seen:
        out.append(one)
    return out


def _get_requested_sources(payload: dict[str, Any] | None = None) -> list[str]:
    data = payload or {}
    raw_sources = data.get("sources")
    query_sources = request.args.get("sources", "")
    source_list: list[str] = []
    if isinstance(raw_sources, (list, tuple)):
        source_list.extend(list(raw_sources))
    elif isinstance(raw_sources, str) and raw_sources.strip():
        source_list.extend(
            [part.strip() for part in raw_sources.split(",") if part.strip()]
        )
    if query_sources:
        source_list.extend(
            [part.strip() for part in query_sources.split(",") if part.strip()]
        )
    single_source = data.get("source") or request.args.get("source", "")
    return _normalize_selected_sources(source_list, single_source)


def _collect_lookup_texts_for_entry(entry: dict[str, Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add_text(raw: Any) -> None:
        text = str(raw or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        out.append(text)

    if not isinstance(entry, dict):
        return out

    for key in (
        "headword",
        "surface_form",
        "head",
        "text",
        "lemma",
        "lemma_form",
        "morph_base",
    ):
        add_text(entry.get(key))

    forms = entry.get("forms")
    if isinstance(forms, list):
        for form in forms:
            if isinstance(form, (list, tuple)) and form:
                add_text(form[0])
            elif isinstance(form, dict):
                add_text(form.get("word") or form.get("form") or form.get("headword"))

    return out


def _entry_source_tag(entry: dict[str, Any] | None) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("_source") or entry.get("source") or "").strip()


def _entry_reading(entry: dict[str, Any] | None) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(
        entry.get("reading") or entry.get("romanization") or entry.get("pinyin") or ""
    ).strip()


_NOUN_AFFIX_POS = (
    "suffix",
    "prefix",
    "affix",
    "infix",
    "interfix",
    "circumfix",
    "combining_form",
)


_UPOS_TO_KAIKKI_POS = {
    "NOUN": ["noun", "classifier", "name", "contraction", "counter", *_NOUN_AFFIX_POS],
    "VERB": ["verb"],
    "ADJ": ["adj", "adnominal"],
    "ADV": ["adv"],
    "PROPN": ["name", "noun"],
    "ADP": ["prep", "postp", "prep_phrase", "particle", "circumpos"],
    "AUX": ["verb"],
    "CCONJ": ["conj"],
    "SCONJ": ["conj"],
    "DET": ["det", "article", "adnominal"],
    "PRON": ["pron"],
    "NUM": ["num", "counter"],
    "PART": ["particle"],
    "INTJ": ["intj"],
    "PUNCT": ["punct", "symbol"],
    "SYM": ["symbol", "punct"],
    "X": ["syllable", "[]"],
}


_LANGUAGE_UPOS_EXTRA_POS = {
    "ja": {
        "AUX": ["suffix"],
        "CCONJ": ["suffix"],
        "SCONJ": ["suffix"],
    },
}


_FILTER_EXEMPT_POS = frozenset({"proverb", "phrase", "prep_phrase"})


_ALWAYS_FILTERED_POS = frozenset(
    {"character", "romanization", "syllable", "punct", "symbol"}
)


_GREEDY_FILTER_MODES = frozenset(
    {"greedy", "lemma_greedy", "lemma_partial_greedy", "greedy_lemma_mismatch"}
)


def _safe_json_load(raw: Any) -> Any:
    if isinstance(raw, (list, dict)):
        return copy.deepcopy(raw)
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _list_text_values(raw: Any) -> list[str]:
    out: list[str] = []
    if isinstance(raw, (list, tuple, set)):
        for item in raw:
            text = str(item or "").strip()
            if text:
                out.append(text)
    else:
        text = str(raw or "").strip()
        if text:
            out.append(text)
    return out


def _normalize_entry_form_rows(raw: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    if isinstance(raw, str):
        raw = _safe_json_load(raw)
    if not isinstance(raw, list):
        return rows
    for item in raw:
        if isinstance(item, (list, tuple)):
            word = str(item[0] or "") if len(item) > 0 else ""
            commentary = str(item[1] or "") if len(item) > 1 else ""
            romanization = str(item[2] or "") if len(item) > 2 else ""
            rows.append([word, commentary, romanization])
        elif isinstance(item, dict):
            rows.append(
                [
                    str(
                        item.get("word")
                        or item.get("form")
                        or item.get("headword")
                        or item.get("form_text")
                        or item.get("display_text")
                        or ""
                    ),
                    str(item.get("commentary") or item.get("tags") or ""),
                    str(
                        item.get("romanization")
                        or item.get("reading")
                        or item.get("form_roman")
                        or ""
                    ),
                ]
            )
        else:
            rows.append([str(item or ""), "", ""])
    return rows


_HYDRATION_KEEP_FORM_TAGS = frozenset(
    {
        "hanja",
        "hangeul",
        "cjk",
        "sinitic",
        "hán-nôm",
        "han-nom",
        "hannom",
    }
)


_SPECIAL_DISPLAY_FORM_TAG_TO_BUCKET = {
    "hanja": "hanja",
    "hangeul": "hangeul",
    "cjk": "cjk",
    "sinitic": "cjk",
    "hán-nôm": "cjk",
    "han-nom": "cjk",
    "hannom": "cjk",
}


def _split_special_display_form_tags(raw_tags: Any) -> list[str]:
    text = str(raw_tags or "").strip().lower()
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw_part in re.split(r"[;|,\s]+", text):
        part = str(raw_part or "").strip()
        if not part:
            continue
        if part not in seen:
            seen.add(part)
            out.append(part)
        folded = unicodedata.normalize("NFKD", part)
        folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
        folded = folded.replace("đ", "d")
        if folded and folded not in seen:
            seen.add(folded)
            out.append(folded)
    return out


def _merge_entry_form_rows(
    *row_groups: Sequence[Sequence[str]] | None,
) -> list[list[str]]:
    out: list[list[str]] = []
    seen: set[tuple[str, str, str]] = set()
    for group in row_groups:
        for raw_row in list(group or []):
            row = [
                str(raw_row[0] or "") if len(raw_row) > 0 else "",
                str(raw_row[1] or "") if len(raw_row) > 1 else "",
                str(raw_row[2] or "") if len(raw_row) > 2 else "",
            ]
            row_key = tuple(row)
            if row_key in seen:
                continue
            seen.add(row_key)
            out.append(row)
    return out


def _normalize_special_display_form_rows(
    form_rows: Sequence[Sequence[str]] | None,
) -> tuple[list[list[str]], dict[str, list[str]]]:
    normalized_rows: list[list[str]] = []
    seen_rows: set[tuple[str, str, str]] = set()
    bucket_values: dict[str, list[str]] = {
        "hanja": [],
        "hangeul": [],
        "cjk": [],
    }
    seen_bucket_values: dict[str, set[str]] = {
        "hanja": set(),
        "hangeul": set(),
        "cjk": set(),
    }

    for raw_row in list(form_rows or []):
        word = str(raw_row[0] or "") if len(raw_row) > 0 else ""
        commentary = str(raw_row[1] or "") if len(raw_row) > 1 else ""
        romanization = str(raw_row[2] or "") if len(raw_row) > 2 else ""
        normalized_tags = _split_special_display_form_tags(commentary)
        appended_tags: list[str] = []
        for tag in normalized_tags:
            bucket = _SPECIAL_DISPLAY_FORM_TAG_TO_BUCKET.get(tag)
            if not bucket:
                continue
            if word and word not in seen_bucket_values[bucket]:
                seen_bucket_values[bucket].add(word)
                bucket_values[bucket].append(word)
            if bucket not in normalized_tags and bucket not in appended_tags:
                appended_tags.append(bucket)
        normalized_commentary = commentary
        if appended_tags:
            normalized_commentary += (";" if normalized_commentary else "") + ";".join(
                appended_tags
            )
        row = [word, normalized_commentary, romanization]
        row_key = tuple(row)
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)
        normalized_rows.append(row)

    return normalized_rows, bucket_values


def _build_entry_forms_payload(
    entry: Mapping[str, Any] | None, *, include_matched_rows: bool
) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        return {}
    out: dict[str, Any] = {}

    form_rows = _normalize_entry_form_rows(entry.get("forms"))
    if not form_rows:
        form_rows = _normalize_entry_form_rows(
            entry.get("_forms_raw") or entry.get("_forms_json")
        )
    if include_matched_rows:
        form_rows = _merge_entry_form_rows(
            form_rows, _normalize_entry_form_rows(entry.get("_matched_forms"))
        )

    normalized_rows, special_buckets = _normalize_special_display_form_rows(form_rows)
    if normalized_rows:
        out["rows"] = normalized_rows

    form_sources = (
        ("kanji", "kanji"),
        ("readings", "readings"),
        ("alt_forms", "alt"),
        ("korean_hanja_variants", "hanja"),
        ("korean_hangeul_variants", "hangeul"),
        ("vietnamese_cjk_variants", "cjk"),
    )
    for src_key, out_key in form_sources:
        values = _list_text_values(entry.get(src_key))
        if out_key in special_buckets:
            values += list(special_buckets[out_key])
        if values:
            out[out_key] = _dedupe_text_list(values)
    return out


def _canonical_entry_senses(entry: Mapping[str, Any] | None) -> list[Any]:
    if not isinstance(entry, Mapping):
        return []

    direct = entry.get("senses_full") or entry.get("senses") or []
    if isinstance(direct, list) and direct:
        return copy.deepcopy(direct)

    raw_glosses: Any = entry.get("glosses")
    if isinstance(raw_glosses, str):
        text = raw_glosses.strip()
        if not text:
            return []
        parsed = _safe_json_load(text)
        if parsed is not None:
            raw_glosses = parsed
        else:
            return [
                {"glosses": [part]}
                for part in (chunk.strip() for chunk in text.split(";"))
                if part
            ]

    if isinstance(raw_glosses, Mapping):
        raw_glosses = [raw_glosses]
    if not isinstance(raw_glosses, list):
        return []

    out: list[Any] = []
    for raw in raw_glosses:
        if isinstance(raw, Mapping):
            glosses = [
                str(item or "").strip()
                for item in list(raw.get("glosses") or [])
                if str(item or "").strip()
            ]
            if not glosses:
                fallback = str(raw.get("gloss") or raw.get("text") or "").strip()
                if fallback:
                    glosses = [fallback]
            if not glosses:
                continue
            sense = copy.deepcopy(dict(raw))
            sense["glosses"] = glosses
            out.append(sense)
            continue
        text = str(raw or "").strip()
        if text:
            out.append({"glosses": [text]})
    return out


def _flatten_structured_senses(senses: Sequence[Any] | None) -> list[str]:
    out: list[str] = []
    for raw in senses or []:
        if isinstance(raw, Mapping):
            glosses = [
                str(item or "").strip()
                for item in list(raw.get("glosses") or [])
                if str(item or "").strip()
            ]
            if glosses:
                out.append("; ".join(glosses))
                continue
        text = str(raw or "").strip()
        if text:
            out.append(text)
    return out


_FORM_ALT_FILTER_TAGS = frozenset({"alternative", "redirect", "eumhun", "syllable"})


def _strict_entry_forms(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    return _build_entry_forms_payload(entry, include_matched_rows=True)


def _runtime_entry_id(entry: Mapping[str, Any] | None) -> str:
    if not isinstance(entry, Mapping):
        return ""
    storage_kind = str(entry.get("_storage_kind") or "").strip().lower()
    db_alias = str(entry.get("_storage_db_alias") or "").strip()
    try:
        row_id = int(entry.get("_storage_row_id") or 0)
    except Exception:
        row_id = 0
    if not storage_kind or not db_alias or row_id <= 0:
        return ""
    return f"{storage_kind}|{db_alias}|{row_id}"


def _hydrated_ref_key(entry: Mapping[str, Any] | None) -> str:
    if not isinstance(entry, Mapping):
        return ""
    storage_kind = str(entry.get("_storage_kind") or "").strip().lower()
    db_alias = str(entry.get("_storage_db_alias") or "").strip()
    try:
        row_id = int(entry.get("_storage_row_id") or 0)
    except Exception:
        row_id = 0
    try:
        form_row_id = int(entry.get("_storage_form_row_id") or 0)
    except Exception:
        form_row_id = 0
    if not storage_kind or not db_alias or row_id <= 0:
        return ""
    if form_row_id > 0:
        return f"{storage_kind}|{db_alias}|{row_id}|{form_row_id}"
    return f"{storage_kind}|{db_alias}|{row_id}"


def _split_form_tag_bundle(raw_tags: Any) -> list[str]:
    text = str(raw_tags or "").strip().lower()
    if not text:
        return []
    return [part for part in re.split(r"[;|,\s]+", text) if part]


def _has_alt_bucket_tag(raw_tags: Any) -> bool:
    for part in _split_form_tag_bundle(raw_tags):
        if part in _FORM_ALT_FILTER_TAGS:
            return True
    return False


def _select_triggering_matched_form(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        return {}
    matched_forms = entry.get("_matched_forms") or []
    if not isinstance(matched_forms, list) or not matched_forms:
        return {}
    form_match_key = str(entry.get("_form_match_key") or "").strip()
    if form_match_key:
        for raw in matched_forms:
            if not isinstance(raw, Mapping):
                continue
            if form_match_key in list(raw.get("index_keys") or []):
                return copy.deepcopy(dict(raw))
    for raw in matched_forms:
        if isinstance(raw, Mapping):
            return copy.deepcopy(dict(raw))
    return {}


def _build_hydrated_display_payload(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        return {}

    source_tag = (
        _entry_source_tag(dict(entry)) or str(entry.get("source") or "").strip()
    )
    match_kind = (
        str(entry.get("_match_kind") or "headword").strip().lower() or "headword"
    )
    runtime_entry_id = _runtime_entry_id(entry)
    ref_key = _hydrated_ref_key(entry)
    source_entry_id = str(entry.get("entry_id") or "").strip()
    lemma_headword = str(entry.get("headword") or "").strip()
    entry_reading = _entry_reading(dict(entry))
    display_headword = (
        str(entry.get("display_headword") or "").strip() or lemma_headword
    )
    display_reading = entry_reading
    raw_morph_info = entry.get("morph_info")
    morph_info = (
        raw_morph_info
        if isinstance(raw_morph_info, list)
        else ([raw_morph_info] if raw_morph_info else [])
    )
    morph_info = [
        str(item or "").strip() for item in morph_info if str(item or "").strip()
    ]
    morph_base = str(entry.get("morph_base") or "").strip()
    is_alternate_match = False
    matched_form: dict[str, Any] = {}

    if match_kind == "form":
        matched_form = _select_triggering_matched_form(entry)
        form_text = str(
            matched_form.get("display_text") or matched_form.get("form_text") or ""
        ).strip()
        form_reading = str(matched_form.get("form_roman") or "").strip()
        raw_tags = str(matched_form.get("tags") or "").strip()
        display_reading = form_reading
        if form_text:
            display_headword = form_text
        if raw_tags and not morph_info:
            morph_info = [raw_tags]
        if lemma_headword and not morph_base:
            morph_base = lemma_headword
        is_alternate_match = _has_alt_bucket_tag(raw_tags)
    elif source_tag == "gemini":
        commentary = str(
            entry.get("commentary") or entry.get("_commentary") or ""
        ).strip()
        lemma = str(entry.get("lemma") or entry.get("_lemma") or "").strip()
        if commentary and not morph_info:
            morph_info = [commentary]
        if lemma and not morph_base:
            morph_base = lemma

    senses_full = _canonical_entry_senses(entry)
    senses = _flatten_structured_senses(senses_full)
    pos = str(entry.get("pos") or "").strip()
    pos_raw = str(entry.get("pos_raw") or pos or "").strip()
    forms = _strict_entry_forms(entry)

    out: dict[str, Any] = {
        "runtime_entry_id": runtime_entry_id,
        "ref_key": ref_key,
        "match_kind": match_kind,
        "_match_kind": match_kind,
        "_match_source": match_kind,
        "display_headword": display_headword,
        "lemma_headword": lemma_headword,
        "display_reading": display_reading,
        "entry_reading": entry_reading,
        "headword": display_headword,
        "surface_form": display_headword,
        "reading": display_reading,
        "roman": display_reading,
        "source": source_tag,
        "_source": source_tag,
        "senses": senses,
        "senses_full": senses_full,
        "is_alternate_match": bool(is_alternate_match),
    }
    if source_entry_id:
        out["entry_id"] = source_entry_id
        out["_source_entry_id"] = source_entry_id
    if pos:
        out["pos"] = pos
    if pos_raw:
        out["pos_raw"] = pos_raw
    if forms:
        out["forms"] = forms
    commentary = str(entry.get("commentary") or "").strip()
    if commentary:
        out["commentary"] = commentary
        out["_commentary"] = commentary
    lemma = str(entry.get("lemma") or "").strip()
    if lemma:
        out["lemma"] = lemma
        out["_lemma"] = lemma
    if morph_info:
        out["morph_info"] = morph_info
    if morph_base:
        out["morph_base"] = morph_base
    grammar = str(entry.get("grammar") or "").strip()
    if grammar:
        out["grammar"] = grammar

    passthrough_keys = (
        "etymology",
        "etymology_number",
        "synonyms",
        "antonyms",
        "derived",
        "related",
        "note",
        "decomp",
    )
    for key in passthrough_keys:
        value = entry.get(key)
        if value:
            out[key] = copy.deepcopy(value)

    for key in (
        "_storage_kind",
        "_storage_db_alias",
        "_storage_row_id",
        "_storage_form_row_id",
    ):
        value = entry.get(key)
        if value:
            out[key] = value

    if matched_form:
        out["matched_form"] = matched_form
        out["_matched_forms"] = [copy.deepcopy(matched_form)]
    return out


def _build_shared_base_payload(
    entry: Mapping[str, Any], match_key: str, lang_code: str
) -> dict[str, Any]:
    """Build the canonical shared payload for entry_store.

    The shared base payload must stay headword-shaped even when the same entry
    also has one or more matched form refs in this hydrate batch. Per-form
    display state belongs in form_overlays only.
    """
    base_entry = dict(entry or {})
    base_entry["_match_kind"] = "headword"
    if match_key:
        base_entry["_match_key"] = match_key
    else:
        base_entry.pop("_match_key", None)
    base_entry.pop("_form_match_key", None)
    base_entry.pop("matched_form", None)
    base_entry.pop("_storage_form_row_id", None)
    base_entry["_matched_forms"] = []
    _shape_korean_synthetic_stem_entry(base_entry, match_key, lang_code)
    payload = _build_hydrated_display_payload(base_entry)
    if payload:
        payload["match_kind"] = "headword"
        payload["_match_kind"] = "headword"
        payload["_match_source"] = "headword"
    return payload


def _extract_form_overlay(
    entry: Mapping[str, Any], matched_form: dict[str, Any]
) -> dict[str, Any]:
    """Extract lightweight form-specific display fields for a matched form.

    Returns only the fields that differ per form_row_id, not the full entry.
    """
    overlay: dict[str, Any] = {}
    form_text = str(
        matched_form.get("display_text") or matched_form.get("form_text") or ""
    ).strip()
    form_reading = str(matched_form.get("form_roman") or "").strip()
    raw_tags = str(matched_form.get("tags") or "").strip()
    lemma_hw = str(entry.get("headword") or "").strip()
    if form_text:
        overlay["display_headword"] = form_text
    overlay["display_reading"] = form_reading
    if raw_tags:
        overlay["morph_info"] = [raw_tags]
    if lemma_hw:
        overlay["morph_base"] = lemma_hw
    overlay["match_kind"] = "form"
    overlay["_match_kind"] = "form"
    overlay["_match_source"] = "form"
    overlay["is_alternate_match"] = _has_alt_bucket_tag(raw_tags)
    overlay["matched_form"] = copy.deepcopy(matched_form)
    form_row_id = int(matched_form.get("_form_row_id") or 0)
    if form_row_id:
        overlay["_storage_form_row_id"] = form_row_id
    return overlay


def _shape_korean_synthetic_stem_entry(
    entry: dict[str, Any], match_key: str, lang_code: str
) -> None:
    if not isinstance(entry, dict):
        return
    lang = str(lang_code or "").strip().lower()
    if not (lang == "ko" or lang == "korean" or lang.startswith("ko-")):
        return
    if str(entry.get("_match_kind") or "").strip().lower() != "headword":
        return
    headword = str(entry.get("headword") or "").strip()
    pos = str(entry.get("pos") or "").strip().lower()
    if pos not in {"verb", "adj"}:
        return
    if not headword.endswith("다") or len(headword) <= 1:
        return
    stem_text = headword[:-1].strip()
    if not stem_text:
        return
    key = str(match_key or "").strip()
    if not key or key != stem_text:
        return
    entry["display_headword"] = stem_text
    entry["morph_info"] = ["stem"]
    entry["morph_base"] = headword
