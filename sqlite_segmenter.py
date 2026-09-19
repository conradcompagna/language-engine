from __future__ import annotations

import copy
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from dict_lookup_sqlite import (
    _filter_db_paths,
    _normalize_key,
    _resolve_all_db_paths,
    hydrate_winner_refs,
    probe_lookup_keys,
)
from debug_trace_runtime import record_normalization, record_segmenter_event, trace_scope


_COMPOUND_LEMMA_SPLIT_RE = re.compile(r"\s*[+\uFF0B]\s*")
_LOOKUP_INVISIBLE_COMPARISON_RE = re.compile(
    r"[\u061C\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFE00-\uFE0F\uFEFF]|\U000E0100-\U000E01EF"
)
_ENABLE_PARTIAL_EXACT_LEMMA_GAP_FILL = True

_LOOKUP_FORM_TAG_EXCLUDE = {
    "classifier",
    "clf",
    "counter",
    "ctr",
}


def _split_compound_tags(raw_value: Any) -> list[str]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    if "+" not in text and "＋" not in text:
        return [text]
    out: list[str] = []
    for part in _COMPOUND_LEMMA_SPLIT_RE.split(text):
        piece = str(part or "").strip()
        if piece:
            out.append(piece)
    return out


def _is_korean_language_code(lang_value: str) -> bool:
    lang = str(lang_value or "").strip().lower()
    return lang == "ko" or lang == "korean" or lang.startswith("ko-")


def _split_morph_tags(raw_morph: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    src = raw_morph if isinstance(raw_morph, list) else ([raw_morph] if raw_morph else [])
    for item in src:
        chunk = str(item or "").strip().lower()
        if not chunk:
            continue
        for part in re.split(r"[;|,]", chunk):
            tag = str(part or "").strip().lower()
            if not tag or tag in seen:
                continue
            seen.add(tag)
            out.append(tag)
    return out


def _entry_has_morph_tag(entry: dict[str, Any] | None, tag_text: str) -> bool:
    target = str(tag_text or "").strip().lower()
    if not target or not isinstance(entry, dict):
        return False
    return target in _split_morph_tags(entry.get("morph_info"))


def _clone_entry_with_morph_tag(
    entry: dict[str, Any] | None, tag_text: str
) -> dict[str, Any] | None:
    tag = str(tag_text or "").strip()
    if not isinstance(entry, dict):
        return entry
    if not tag or _entry_has_morph_tag(entry, tag):
        return dict(entry)
    clone = dict(entry)
    morph_info = _split_morph_tags(clone.get("morph_info"))
    morph_info.append(tag)
    clone["morph_info"] = morph_info
    return clone


@dataclass
class LemmaPromotion:
    index: int
    lemma: str
    lemma_key: str
    entry: dict[str, Any]
    upos: str = ""
    xpos: str = ""


def _resolution_route_step(code: str, text: str, detail: str = "") -> dict[str, str]:
    return {
        "code": str(code or "").strip(),
        "text": str(text or "").strip(),
        "detail": str(detail or "").strip(),
    }


def _build_resolution_meta(
    category: str,
    route_code: str,
    route_steps: Sequence[dict[str, Any]] | None,
    resolved_via: str,
    fill_mode: str,
    lemma_oracle_used: bool,
    lemma_oracle_outcome: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "category": str(category or "").strip().lower(),
        "route_code": str(route_code or "").strip().lower(),
        "route_steps": [
            {
                "code": str((step or {}).get("code") or "").strip(),
                "text": str((step or {}).get("text") or "").strip(),
                "detail": str((step or {}).get("detail") or "").strip(),
            }
            for step in list(route_steps or [])
            if isinstance(step, dict) and str((step or {}).get("text") or "").strip()
        ],
        "resolved_via": str(resolved_via or "").strip().lower(),
        "fill_mode": str(fill_mode or "").strip().lower(),
        "lemma_oracle_used": bool(lemma_oracle_used),
        "lemma_oracle_outcome": str(lemma_oracle_outcome or "").strip().lower(),
    }
    extras = extra if isinstance(extra, dict) else None
    if extras:
        out.update(extras)
    return out


_ACTUAL_RESOLUTION_LABELS = {
    "exact_match": "exact match",
    "exact_lemma_match": "exact lemma match",
    "greedy_segmentation": "greedy segmentation",
    "greedy_lemma_match": "greedy lemma match",
    "lemma_override": "lemma override",
    "lemma_partial_override": "lemma partial override",
}


def _build_resolution_route_text(route_steps: Sequence[dict[str, Any]] | None) -> str:
    out: list[str] = []
    for step in list(route_steps or []):
        if not isinstance(step, dict):
            continue
        text = str(step.get("text") or "").strip()
        detail = str(step.get("detail") or "").strip()
        if not text:
            continue
        out.append(f"{text} ({detail})" if detail else text)
    return " -> ".join(out)


def _summarize_actual_resolution_fills(fills: Sequence[dict[str, Any]] | None) -> dict[str, Any]:
    rows = list(fills or [])
    known_piece_count = 0
    unknown_piece_count = 0
    lemma_linked_fill_indexes: list[int] = []
    lemma_linked_keys: set[str] = set()
    for idx, row in enumerate(rows):
        item = row if isinstance(row, dict) else {}
        if str(item.get("source") or "").upper() == "UNKNOWN":
            unknown_piece_count += 1
        else:
            known_piece_count += 1
        if not item.get("resolution_linked_to_lemma"):
            continue
        lemma_linked_fill_indexes.append(idx)
        lemma_key = str(
            item.get("_lemma_override")
            or item.get("_lemma_promoted")
            or item.get("lemma_form")
            or item.get("morph_base")
            or ""
        ).strip()
        if lemma_key:
            lemma_linked_keys.add(lemma_key)
    return {
        "total_piece_count": len(rows),
        "known_piece_count": known_piece_count,
        "unknown_piece_count": unknown_piece_count,
        "lemma_linked_piece_count": len(lemma_linked_fill_indexes),
        "lemma_linked_fill_indexes": lemma_linked_fill_indexes,
        "lemma_linked_distinct_count": len(lemma_linked_keys),
    }


def _build_resolution_actual(
    resolution_meta: dict[str, Any] | None,
    fills: Sequence[dict[str, Any]] | None,
    exact_lemma_match_count: int,
    partial_gap_count: int = 0,
    partial_exact_lemma_count: int = 0,
    partial_missing_lemma_count: int = 0,
) -> dict[str, Any]:
    meta = resolution_meta if isinstance(resolution_meta, dict) else {}
    fill_summary = _summarize_actual_resolution_fills(fills)
    category_key = str(meta.get("category") or "").strip().lower()
    resolved_via = str(meta.get("resolved_via") or "").strip().lower()
    fill_mode = str(meta.get("fill_mode") or "").strip().lower()
    lemma_oracle_used = bool(meta.get("lemma_oracle_used"))
    lemma_oracle_outcome = str(meta.get("lemma_oracle_outcome") or "").strip().lower()
    lemma_exact_count = int(exact_lemma_match_count or 0)
    if lemma_exact_count < 0:
        lemma_exact_count = 0

    compare_kind = ""
    if category_key in {
        "exact_lemma_match",
        "greedy_lemma_match",
        "lemma_override",
        "lemma_partial_override",
    }:
        compare_kind = "surface"
    elif lemma_oracle_used:
        compare_kind = "lemma"

    final_text = ""
    if fill_summary["known_piece_count"] > 0:
        parts = [
            f"via={resolved_via}",
            f"mode={fill_mode}",
            f"pieces={fill_summary['total_piece_count']}",
            f"known={fill_summary['known_piece_count']}",
        ]
        if fill_summary["unknown_piece_count"] > 0:
            parts.append(f"unknown={fill_summary['unknown_piece_count']}")
        if fill_summary["lemma_linked_piece_count"] > 0:
            parts.append(f"lemma-linked={fill_summary['lemma_linked_piece_count']}")
        if lemma_exact_count > 0:
            parts.append(f"lemma-exact={lemma_exact_count}")
        final_text = " | ".join(parts)

    out: dict[str, Any] = {
        "category": category_key,
        "label": _ACTUAL_RESOLUTION_LABELS.get(category_key, "") if category_key else "",
        "route_code": str(meta.get("route_code") or "").strip().lower(),
        "route_steps": copy.deepcopy(list(meta.get("route_steps") or [])),
        "route_text": _build_resolution_route_text(meta.get("route_steps")),
        "final_text": final_text,
        "compare_kind": compare_kind,
        "resolved_via": resolved_via,
        "fill_mode": fill_mode,
        "lemma_oracle_used": lemma_oracle_used,
        "lemma_oracle_outcome": lemma_oracle_outcome,
        "exact_surface_match": category_key in {"exact_match", "exact_lemma_match"},
        "exact_matches_lemma": category_key == "exact_lemma_match",
        "exact_lemma_match_count": lemma_exact_count,
        "has_lemma_linked_fill": fill_summary["lemma_linked_piece_count"] > 0,
        "lemma_linked_fill_indexes": fill_summary["lemma_linked_fill_indexes"][:],
        "lemma_linked_distinct_count": fill_summary["lemma_linked_distinct_count"],
        "final_result": {
            "total_piece_count": fill_summary["total_piece_count"],
            "known_piece_count": fill_summary["known_piece_count"],
            "unknown_piece_count": fill_summary["unknown_piece_count"],
            "lemma_linked_piece_count": fill_summary["lemma_linked_piece_count"],
        },
    }
    if partial_exact_lemma_count > 0:
        out["partial_exact_lemma_count"] = int(partial_exact_lemma_count)
    if partial_missing_lemma_count > 0:
        out["partial_missing_lemma_count"] = int(partial_missing_lemma_count)
    if partial_gap_count > 0:
        out["partial_gap_count"] = int(partial_gap_count)
    return out


class SQLiteDictionarySegmenter:
    """
    SQLite-backed port of the JS dictionary segmenter.

    Core behavior mirrored here:
      1. whole-surface exact match wins immediately
      2. lemma hints can promote exact whole-token matches
      3. otherwise DP segmentation minimizes unknowns, then maximizes promoted
         continuation, then minimizes pieces, then prefers longer spans
      4. exact lemma parts can be aligned onto the surface and frozen in place;
         uncovered gaps are segmented greedily with the remaining lemma hints
      5. each promoted lemma hint may only be consumed once in a path
    """

    def __init__(
        self,
        lang_code: str,
        sources: Sequence[str] | None = None,
        include_custom_entries: bool = True,
        db_paths: Sequence[str | Path] | None = None,
    ) -> None:
        self.lang_code = str(lang_code or "").strip().lower()
        if db_paths is not None:
            self.db_paths = [Path(p) for p in db_paths]
        else:
            all_paths = _resolve_all_db_paths(self.lang_code)
            self.db_paths = (
                _filter_db_paths(all_paths, self.lang_code, list(sources or []))
                if sources
                else all_paths
            )
        if not self.db_paths:
            raise FileNotFoundError(f"No SQLite dictionary for language {self.lang_code!r}")
        self.include_custom_entries = include_custom_entries
        self._candidate_cache: dict[str, list[dict[str, Any]]] = {}
        self._lookup_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._entry_pool: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._normalized_text_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Exact lookup layer
    # ------------------------------------------------------------------

    def reset_caches(self) -> None:
        self._candidate_cache.clear()
        self._lookup_cache.clear()
        self._entry_pool.clear()
        self._normalized_text_cache.clear()

    def _normalize_cached(self, text: Any) -> str:
        raw_text = "" if text is None else str(text)
        cached = self._normalized_text_cache.get(raw_text)
        if cached is not None:
            return cached
        normalized = _normalize_key(raw_text, self.lang_code)
        self._normalized_text_cache[raw_text] = normalized
        return normalized

    def _entry_headword_key(self, entry: dict[str, Any]) -> str:
        if not isinstance(entry, dict):
            return ""
        cached = str(entry.get("headword_key") or "").strip()
        if cached:
            return cached
        key = self._normalize_cached(entry.get("headword"))
        if key:
            entry["headword_key"] = key
        return key

    def invalidate_lookup_texts(self, texts: Sequence[str] | str) -> None:
        keys: set[str] = set()
        source = [texts] if isinstance(texts, str) else list(texts or [])
        for text in source:
            key = self._normalize_cached(text)
            if key:
                keys.add(key)
        if not keys:
            return

        for cache_key in list(self._lookup_cache.keys()):
            if isinstance(cache_key, tuple) and cache_key and cache_key[0] in keys:
                self._lookup_cache.pop(cache_key, None)
        for key in keys:
            self._candidate_cache.pop(key, None)

        stale_idents: list[tuple[Any, ...]] = []
        for ident, entry in self._entry_pool.items():
            if self._entry_pool_entry_matches_keys(entry, keys):
                stale_idents.append(ident)
        for ident in stale_idents:
            self._entry_pool.pop(ident, None)

    def _entry_pool_entry_matches_keys(self, entry: dict[str, Any], keys: set[str]) -> bool:
        if not isinstance(entry, dict) or not keys:
            return False
        candidates = [
            entry.get("headword"),
            entry.get("headword_key"),
            entry.get("surface_form"),
            entry.get("reading"),
            entry.get("romanization"),
            entry.get("lemma"),
            entry.get("morph_base"),
        ]
        surface_forms = entry.get("surface_forms")
        if isinstance(surface_forms, list):
            candidates.extend(surface_forms)
        matched_forms = entry.get("_matched_forms")
        if isinstance(matched_forms, list):
            for rec in matched_forms:
                if not isinstance(rec, dict):
                    continue
                candidates.append(rec.get("form_text"))
                for index_key in list(rec.get("index_keys") or []):
                    candidates.append(index_key)
        forms_data = entry.get("_forms_data")
        if isinstance(forms_data, list):
            for rec in forms_data:
                if not isinstance(rec, dict):
                    continue
                candidates.append(rec.get("form_text"))
                for index_key in list(rec.get("index_keys") or []):
                    candidates.append(index_key)
        for candidate in candidates:
            key = self._normalize_cached(candidate)
            if key and key in keys:
                return True
        return False

    def lookup_all(self, text: str, *, trace: bool = False) -> list[dict[str, Any]]:
        query_text = str(text or "").strip()
        if trace:
            with trace_scope(
                "lookup_all", label="Lookup All", text=query_text, lang=self.lang_code
            ):
                key = self._normalize_cached(query_text)
                record_normalization(
                    raw_text=query_text,
                    normalized_key=key,
                    lang_code=self.lang_code,
                    kind="lookup_all",
                )
                if not key:
                    return []
                cache_key = (key, query_text)
                cached = self._lookup_cache.get(cache_key)
                if cached is not None:
                    record_segmenter_event(
                        "lookup_all_cache_hit",
                        {"text": query_text, "normalized_key": key, "entry_count": len(cached)},
                    )
                    return cached

                candidates = self._get_candidate_entries_for_key(key, trace=trace)
                entries = self._materialize_candidates_for_lookup(
                    candidates, query_text, query_key=key, trace=trace
                )
                self._lookup_cache[cache_key] = entries
                record_segmenter_event(
                    "lookup_all_result",
                    {"text": query_text, "normalized_key": key, "entry_count": len(entries)},
                )
                return entries
        key = self._normalize_cached(query_text)
        if not key:
            return []
        cache_key = (key, query_text)
        cached = self._lookup_cache.get(cache_key)
        if cached is not None:
            return cached
        candidates = self._get_candidate_entries_for_key(key, trace=False)
        entries = self._materialize_candidates_for_lookup(
            candidates, query_text, query_key=key, trace=False
        )
        self._lookup_cache[cache_key] = entries
        return entries

    def _get_candidate_entries_for_key(
        self, normalized_key: str, *, trace: bool = False
    ) -> list[dict[str, Any]]:
        key = str(normalized_key or "").strip()
        if not key:
            return []
        cached = self._candidate_cache.get(key)
        if cached is not None:
            return cached
        self._prefetch_candidate_keys([key], trace=trace)
        return list(self._candidate_cache.get(key) or [])

    def _entry_identity(self, entry: dict[str, Any]) -> tuple[Any, ...]:
        entry_id = str(entry.get("entry_id") or "").strip()
        source = str(entry.get("source") or "").strip().lower()
        storage_kind = str(entry.get("_storage_kind") or "").strip().lower()
        storage_db_alias = str(
            entry.get("_storage_db_alias") or entry.get("_storage_db_path") or ""
        ).strip()
        storage_row_id = int(entry.get("_storage_row_id") or 0)
        if storage_kind and storage_row_id:
            return ("storage", storage_kind, storage_db_alias, storage_row_id)
        if entry_id:
            return ("entry_id", source, entry_id)
        return (
            "fallback",
            source,
            str(entry.get("headword") or ""),
            str(entry.get("headword_key") or ""),
            str(entry.get("reading") or entry.get("romanization") or ""),
            str(entry.get("pos_raw") or entry.get("pos") or ""),
            str(entry.get("glosses") or ""),
            str(entry.get("lemma") or ""),
            str(entry.get("etymology") or ""),
        )

    def _intern_entry(self, row: dict[str, Any]) -> dict[str, Any]:
        prepared = self._prepare_entry_dict(row)
        ident = self._entry_identity(prepared)
        existing = self._entry_pool.get(ident)
        if existing is not None:
            # Preserve any richer fields that may appear later.
            for key, value in prepared.items():
                if key == "_hydrated" and value:
                    existing["_hydrated"] = True
                    continue
                if key not in existing or existing[key] in (None, "", [], {}):
                    existing[key] = value
                    continue
                if key == "_matched_forms" and value:
                    current = existing.setdefault("_matched_forms", [])
                    for rec in list(value or []):
                        if rec not in current:
                            current.append(rec)
            return existing
        self._entry_pool[ident] = prepared
        return prepared

    def _prepare_entry_dict(self, row: dict[str, Any]) -> dict[str, Any]:
        entry = dict(row)
        entry.pop("_match_key", None)
        entry["_hydrated"] = bool(entry.get("_hydrated"))
        if "reading" not in entry and entry.get("romanization"):
            entry["reading"] = entry.get("romanization") or ""
        if "pos_raw" not in entry and entry.get("pos"):
            entry["pos_raw"] = entry.get("pos") or ""
        commentary = str(entry.get("commentary") or "").strip()
        lemma = str(entry.get("lemma") or "").strip()
        if commentary:
            entry["_commentary"] = commentary
            if not entry.get("morph_info"):
                entry["morph_info"] = [commentary]
        if lemma:
            entry["_lemma"] = lemma
            if not entry.get("morph_base"):
                entry["morph_base"] = lemma
        raw_forms = entry.get("forms")
        if isinstance(raw_forms, str) and raw_forms.strip():
            entry["_forms_raw"] = raw_forms
        elif isinstance(raw_forms, list) and raw_forms:
            try:
                entry["_forms_raw"] = json.dumps(raw_forms, ensure_ascii=False)
            except Exception:
                entry["_forms_raw"] = ""
        # Parse the glosses JSON string (from the DB column) into senses_full
        # and a flat senses list so the rendering pipeline can consume them.
        if not entry.get("senses_full"):
            raw = entry.get("glosses")
            if isinstance(raw, str) and raw.strip():
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        for idx in range(len(parsed) - 1, -1, -1):
                            marker = parsed[idx]
                            if isinstance(marker, dict) and marker.get("_source"):
                                entry["_source"] = str(marker.get("_source") or "")
                                parsed = parsed[:idx] + parsed[idx + 1 :]
                                entry["glosses"] = json.dumps(parsed, ensure_ascii=False)
                                break
                        entry["senses_full"] = parsed
                        entry["senses"] = [
                            str(g).strip()
                            for sense in parsed
                            if isinstance(sense, dict)
                            for g in (sense.get("glosses") or [])
                            if str(g).strip()
                        ]
                except Exception:
                    pass
            elif isinstance(raw, list):
                entry["senses"] = [str(g).strip() for g in raw if str(g).strip()]
                entry["senses_full"] = [{"glosses": entry["senses"]}] if entry["senses"] else []
        return entry

    def _entry_storage_ref(self, entry: dict[str, Any]) -> tuple[str, str, int]:
        return (
            str(entry.get("_storage_kind") or "").strip().lower(),
            str(entry.get("_storage_db_alias") or entry.get("_storage_db_path") or "").strip(),
            int(entry.get("_storage_row_id") or 0),
        )

    def _capture_candidate_match_state(self, entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "match_key": str(entry.get("match_key") or entry.get("_match_key") or "").strip(),
            "_storage_kind": str(entry.get("_storage_kind") or "").strip().lower(),
            "_storage_db_alias": str(
                entry.get("_storage_db_alias") or entry.get("_storage_db_path") or ""
            ).strip(),
            "_storage_row_id": int(entry.get("_storage_row_id") or 0),
            "_match_kind": str(entry.get("_match_kind") or "").strip().lower(),
            "_form_row_id": int(entry.get("_form_row_id") or 0),
            "_matched_form_row_ids": [
                int(raw_id or 0)
                for raw_id in list(entry.get("_matched_form_row_ids") or [])
                if int(raw_id or 0) > 0
            ],
        }

    def _hydrate_candidate_entry(
        self, candidate: dict[str, Any], hydrated_row: dict[str, Any]
    ) -> None:
        if not isinstance(candidate, dict) or not isinstance(hydrated_row, dict):
            return
        match_state = self._capture_candidate_match_state(candidate)
        shared_entry = self._intern_entry(hydrated_row)
        refreshed = copy.deepcopy(shared_entry)
        refreshed.update(match_state)
        refreshed["_hydrated"] = True
        candidate.clear()
        candidate.update(refreshed)

    def _ensure_candidates_hydrated(
        self, entries: Sequence[dict[str, Any]], *, trace: bool = False
    ) -> None:
        missing: list[dict[str, Any]] = []
        seen_refs: set[tuple[str, str, int]] = set()
        for entry in list(entries or []):
            if not isinstance(entry, dict) or entry.get("_hydrated"):
                continue
            ref = self._entry_storage_ref(entry)
            if not ref[0] or not ref[2] or ref in seen_refs:
                continue
            seen_refs.add(ref)
            missing.append(entry)
        if not missing:
            return
        hydrated_rows = hydrate_winner_refs(
            missing,
            self.lang_code,
            db_paths=self.db_paths,
            include_custom_entries=self.include_custom_entries,
            trace=trace,
        )
        for entry in missing:
            hydrated_row = hydrated_rows.get(self._entry_storage_ref(entry))
            if hydrated_row is None:
                continue
            self._hydrate_candidate_entry(entry, hydrated_row)

    def _materialize_candidates_for_lookup(
        self,
        candidates: Sequence[dict[str, Any]],
        query_text: str,
        *,
        query_key: str = "",
        trace: bool = False,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []
        query = str(query_text or "").strip()
        key = str(query_key or self._normalize_cached(query) or "").strip()
        if trace:
            with trace_scope(
                "materialize_candidates",
                label="Materialize Candidates",
                text=query,
                normalized_key=key,
                candidate_count=len(list(candidates or [])),
            ):
                self._ensure_candidates_hydrated(candidates, trace=trace)
                entries: list[dict[str, Any]] = []
                seen: set[tuple[Any, ...]] = set()
                for base_entry in list(candidates or []):
                    entry = self._enrich_entry_for_lookup_text(base_entry, query, query_key=key)
                    if entry is None:
                        continue
                    ident = self._entry_identity(entry)
                    if ident in seen:
                        continue
                    seen.add(ident)
                    entries.append(entry)
                record_segmenter_event(
                    "materialized_candidates",
                    {
                        "text": query,
                        "normalized_key": key,
                        "candidate_count": len(list(candidates or [])),
                        "entry_count": len(entries),
                    },
                )
                return entries
        self._ensure_candidates_hydrated(candidates, trace=trace)
        entries: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for base_entry in list(candidates or []):
            entry = self._enrich_entry_for_lookup_text(base_entry, query, query_key=key)
            if entry is None:
                continue
            ident = self._entry_identity(entry)
            if ident in seen:
                continue
            seen.add(ident)
            entries.append(entry)
        return entries

    def _ensure_entry_forms_data(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(entry, dict):
            return []
        cached = entry.get("_forms_data")
        if isinstance(cached, list):
            return cached
        forms_data = self._parse_forms_payload(entry)
        entry["_forms_data"] = forms_data
        return forms_data

    def _get_language_form_index_texts(
        self, form_text: str, tags: Sequence[Any] | None = None
    ) -> list[str]:
        text = str(form_text or "").strip()
        if not text:
            return []
        if self.lang_code.startswith("ko"):
            lower_tags = {str(tag or "").strip().lower() for tag in (tags or [])}
            if "eumhun" in lower_tags:
                for ch in reversed(text):
                    code = ord(ch)
                    if 0xAC00 <= code <= 0xD7A3:
                        return [ch]
                for ch in reversed(text):
                    if ch.strip():
                        return [ch]
        return [text]

    def _apply_language_form_rules(
        self, entry: dict[str, Any], form_text: str, tags: Sequence[Any] | None = None
    ) -> None:
        text = str(form_text or "").strip()
        if not text or not isinstance(entry, dict):
            return
        lower_tags = {str(tag or "").strip().lower() for tag in (tags or [])}
        if self.lang_code.startswith("vi") and ({"cjk", "sinitic"} & lower_tags):
            existing = entry.get("vietnamese_cjk_variants")
            if not isinstance(existing, list):
                existing = []
                entry["vietnamese_cjk_variants"] = existing
            if text not in existing:
                existing.append(text)
            display = entry.get("hanja_forms")
            if not isinstance(display, list):
                display = []
                entry["hanja_forms"] = display
            if text not in display:
                display.append(text)
        if self.lang_code.startswith("ko"):
            if "hanja" in lower_tags:
                existing = entry.get("korean_hanja_variants")
                if not isinstance(existing, list):
                    existing = []
                    entry["korean_hanja_variants"] = existing
                if text not in existing:
                    existing.append(text)
                display = entry.get("hanja_forms")
                if not isinstance(display, list):
                    display = []
                    entry["hanja_forms"] = display
                if text not in display:
                    display.append(text)
            if "hangeul" in lower_tags:
                existing = entry.get("korean_hangeul_variants")
                if not isinstance(existing, list):
                    existing = []
                    entry["korean_hangeul_variants"] = existing
                if text not in existing:
                    existing.append(text)
                display = entry.get("hangeul_forms")
                if not isinstance(display, list):
                    display = []
                    entry["hangeul_forms"] = display
                if text not in display:
                    display.append(text)

    def _parse_forms_payload(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        raw = entry.get("_forms_raw") if entry.get("_forms_raw") is not None else entry.get("forms")
        if isinstance(raw, str):
            payload = raw.strip()
            if not payload:
                return []
            try:
                parsed = json.loads(payload)
            except Exception:
                return []
        elif isinstance(raw, list):
            parsed = raw
            payload = json.dumps(raw, ensure_ascii=False)
        else:
            return []
        if payload:
            entry["_forms_raw"] = payload
        forms_out: list[dict[str, Any]] = []
        for form in parsed if isinstance(parsed, list) else []:
            form_text = ""
            form_roman = ""
            tags: list[str] = []
            if isinstance(form, list):
                if not form:
                    continue
                form_text = str(form[0] or "").strip()
                if len(form) >= 2:
                    tags = [tag for tag in _split_morph_tags(form[1]) if tag]
                if len(form) >= 3:
                    form_roman = str(form[2] or "").strip()
            elif isinstance(form, dict):
                form_text = str(form.get("form") or form.get("text") or "").strip()
                tags = [
                    tag
                    for tag in _split_morph_tags(
                        form.get("tags") or form.get("label") or form.get("commentary")
                    )
                    if tag
                ]
                form_roman = str(
                    form.get("romanization")
                    or form.get("reading")
                    or form.get("pronunciation")
                    or ""
                ).strip()
            if not form_text:
                continue
            self._apply_language_form_rules(entry, form_text, tags)
            index_texts = self._get_language_form_index_texts(form_text, tags)
            index_keys = [
                key
                for key in (self._normalize_cached(index_text) for index_text in index_texts)
                if key
            ]
            forms_out.append(
                {
                    "form_text": form_text,
                    "display_text": form_text,
                    "form_roman": form_roman,
                    "tags": tags,
                    "index_texts": index_texts,
                    "index_keys": index_keys,
                }
            )
        return forms_out

    def _build_form_match_entry(
        self, entry: dict[str, Any], query_text: str, matching_forms: Sequence[dict[str, Any]]
    ) -> dict[str, Any]:
        surface = str(query_text or "").strip()
        clone = dict(entry)
        if not matching_forms:
            if surface:
                clone["surface_form"] = surface
            if clone.get("headword") and not clone.get("morph_base"):
                clone["morph_base"] = str(clone.get("headword") or "")
            return clone

        morph_seen: set[str] = set(_split_morph_tags(clone.get("morph_info")))
        morph_info: list[str] = list(_split_morph_tags(clone.get("morph_info")))
        surface_forms: list[str] = []
        surface_seen: set[str] = set()
        best_form_roman = str(clone.get("reading") or clone.get("romanization") or "")
        best_display_text = ""
        has_eumhun = False

        def register_surface(raw_surface: Any) -> None:
            text = str(raw_surface or "").strip()
            if not text or text in surface_seen:
                return
            surface_seen.add(text)
            surface_forms.append(text)

        for rec in matching_forms:
            display_text = str(rec.get("display_text") or rec.get("form_text") or "").strip()
            form_roman = str(rec.get("form_roman") or "").strip()
            tags = [tag for tag in _split_morph_tags(rec.get("tags")) if tag]
            is_eumhun = "eumhun" in tags
            if display_text:
                best_display_text = display_text
                register_surface(display_text)
            elif surface:
                register_surface(surface)
            if form_roman:
                if (not best_form_roman) or (
                    (has_eumhun or is_eumhun) and len(form_roman) > len(best_form_roman)
                ):
                    best_form_roman = form_roman
            if is_eumhun:
                has_eumhun = True
            for tag in tags:
                if tag in morph_seen:
                    continue
                morph_seen.add(tag)
                morph_info.append(tag)

        clone["surface_form"] = surface or best_display_text or str(clone.get("surface_form") or "")
        if surface_forms:
            if len(surface_forms) > 1:
                clone["surface_forms"] = surface_forms[:]
            if not clone.get("surface_form"):
                clone["surface_form"] = surface_forms[0]
        lemma_head = str(clone.get("headword") or "").strip()
        if lemma_head:
            clone["morph_base"] = str(clone.get("morph_base") or lemma_head)
        if morph_info:
            clone["morph_info"] = morph_info
        if best_form_roman:
            clone["reading"] = best_form_roman
        elif has_eumhun and best_display_text:
            clone["reading"] = best_display_text
        return clone

    def _enrich_entry_for_lookup_text(
        self,
        entry: dict[str, Any],
        query_text: str,
        *,
        query_key: str = "",
    ) -> dict[str, Any] | None:
        if not isinstance(entry, dict):
            return None
        query = str(query_text or "").strip()
        normalized_query_key = str(query_key or self._normalize_cached(query) or "").strip()
        if not normalized_query_key:
            return dict(entry)
        head_key = self._entry_headword_key(entry)
        if head_key and head_key == normalized_query_key:
            return dict(entry)
        direct_matches: list[dict[str, Any]] = []
        for rec in list(entry.get("_matched_forms") or []):
            tags = [tag for tag in _split_morph_tags(rec.get("tags")) if tag]
            if any(tag in _LOOKUP_FORM_TAG_EXCLUDE for tag in tags):
                continue
            index_keys = rec.get("index_keys") or []
            if normalized_query_key in index_keys:
                direct_matches.append(rec)
        if direct_matches:
            return self._build_form_match_entry(entry, query, direct_matches)
        matching_forms: list[dict[str, Any]] = []
        forms_data = self._ensure_entry_forms_data(entry)
        for rec in list(forms_data or []):
            tags = [tag for tag in _split_morph_tags(rec.get("tags")) if tag]
            if any(tag in _LOOKUP_FORM_TAG_EXCLUDE for tag in tags):
                continue
            index_keys = rec.get("index_keys") or []
            if normalized_query_key in index_keys:
                matching_forms.append(rec)
        if matching_forms:
            return self._build_form_match_entry(entry, query, matching_forms)
        return None

    def _prefetch_candidate_keys(
        self, normalized_keys: Sequence[str] | str, *, trace: bool = False
    ) -> None:
        source = (
            [normalized_keys] if isinstance(normalized_keys, str) else list(normalized_keys or [])
        )
        keys = [str(key or "").strip() for key in source if str(key or "").strip()]
        if not keys:
            return

        missing = [key for key in keys if key not in self._candidate_cache]
        if not missing:
            return
        if trace:
            with trace_scope(
                "prefetch_candidate_keys", label="Prefetch Candidate Keys", key_count=len(missing)
            ):
                record_segmenter_event(
                    "prefetch_candidate_keys",
                    {"lang": self.lang_code, "requested_keys": list(missing)},
                )
                grouped_rows = probe_lookup_keys(
                    self.lang_code,
                    missing,
                    db_paths=self.db_paths,
                    include_custom_entries=self.include_custom_entries,
                    trace=True,
                )
                for key in missing:
                    rows = list(grouped_rows.get(key) or [])
                    entries: list[dict[str, Any]] = []
                    seen: set[tuple[Any, ...]] = set()
                    for row in rows:
                        base_entry = dict(row)
                        ident = self._entry_identity(base_entry)
                        if ident in seen:
                            continue
                        seen.add(ident)
                        entries.append(base_entry)
                    self._candidate_cache[key] = entries
                record_segmenter_event(
                    "prefetch_candidate_results",
                    {
                        "lang": self.lang_code,
                        "requested_keys": list(missing),
                        "result_counts": {
                            key: len(self._candidate_cache.get(key) or []) for key in missing
                        },
                    },
                )
                return
        grouped_rows = probe_lookup_keys(
            self.lang_code,
            missing,
            db_paths=self.db_paths,
            include_custom_entries=self.include_custom_entries,
            trace=False,
        )
        for key in missing:
            rows = list(grouped_rows.get(key) or [])
            entries: list[dict[str, Any]] = []
            seen: set[tuple[Any, ...]] = set()
            for row in rows:
                base_entry = dict(row)
                ident = self._entry_identity(base_entry)
                if ident in seen:
                    continue
                seen.add(ident)
                entries.append(base_entry)
            self._candidate_cache[key] = entries

    def _prefetch_lookup_texts(self, texts: Sequence[str] | str, *, trace: bool = False) -> None:
        source = [texts] if isinstance(texts, str) else list(texts or [])
        keys: set[str] = set()
        for text in source:
            key = self._normalize_cached(str(text or "").strip())
            if key:
                keys.add(key)
        self._prefetch_candidate_keys(sorted(keys), trace=trace)

    def _build_span_key_matrix(
        self, word: str, *, trace: bool = False
    ) -> tuple[list[list[str]], list[str]]:
        if trace:
            with trace_scope(
                "build_span_key_matrix", label="Build Span Key Matrix", word=word, length=len(word)
            ):
                n = len(word)
                span_keys: list[list[str]] = [[""] * (n + 1) for _ in range(n)]
                unique_keys: set[str] = set()
                span_pairs: list[dict[str, Any]] = []
                for start in range(n):
                    for end in range(start + 1, n + 1):
                        raw_piece = word[start:end]
                        key = self._normalize_cached(raw_piece)
                        span_keys[start][end] = key
                        if key:
                            unique_keys.add(key)
                        if len(span_pairs) < 600:
                            span_pairs.append(
                                {
                                    "text": raw_piece,
                                    "normalized_key": key,
                                    "start": start,
                                    "end": end,
                                }
                            )
                record_segmenter_event(
                    "span_key_matrix",
                    {
                        "word": word,
                        "span_count": len(span_pairs),
                        "unique_key_count": len(unique_keys),
                        "span_pairs": span_pairs,
                        "all_query_keys": sorted(unique_keys),
                    },
                )
                return span_keys, sorted(unique_keys)
        n = len(word)
        span_keys: list[list[str]] = [[""] * (n + 1) for _ in range(n)]
        unique_keys: set[str] = set()
        for start in range(n):
            for end in range(start + 1, n + 1):
                raw_piece = word[start:end]
                key = self._normalize_cached(raw_piece)
                span_keys[start][end] = key
                if key:
                    unique_keys.add(key)
        return span_keys, sorted(unique_keys)

    # ------------------------------------------------------------------
    # Public high-level API
    # ------------------------------------------------------------------

    # ==========================================================================
    # DEFUNCT DO NOT TOUCH
    # DEFUNCT DO NOT TOUCH
    # DEFUNCT DO NOT TOUCH
    # Legacy alias retained only for old callers.
    # The live router paths call build_surface_lemma_aware_lookup() directly.
    # Do not add new segmentation behavior here; it will drift from the real path.
    # ==========================================================================
    def segment_token(
        self,
        surface: str,
        lemma: str | Sequence[str] | Sequence[dict[str, Any]] | None = None,
        *,
        upos: str = "",
        xpos: str = "",
        debug: bool = False,
    ) -> dict[str, Any]:
        return self.build_surface_lemma_aware_lookup(
            surface, lemma, upos=upos, xpos=xpos, debug=debug
        )

    def build_surface_lemma_aware_lookup(
        self,
        surface_text: str,
        lemma: str | Sequence[str] | Sequence[dict[str, Any]] | None,
        *,
        upos: str = "",
        xpos: str = "",
        debug: bool = False,
    ) -> dict[str, Any]:
        surface = str(surface_text or "").strip()
        hint_data = self._build_lemma_hint_data(surface, lemma, upos, xpos)
        lemma_hints = hint_data["lemma_hint_objects"]
        lemma_oracle_used = bool(hint_data["lemma_differs_from_surface"] and lemma_hints)

        exact_entries = self.lookup_all(surface, trace=debug)
        exact_match_info = (
            self._collect_entries_matching_lemma_hints(exact_entries, lemma_hints)
            if lemma_oracle_used
            else {"entries": [], "matches": []}
        )
        exact_preferred_entries = (
            exact_match_info["entries"][:] if exact_match_info["entries"] else exact_entries[:]
        )

        def _attach_resolution_compat(
            payload: dict[str, Any],
            resolution_meta: dict[str, Any] | None,
            fills: Sequence[dict[str, Any]] | None,
            exact_lemma_match_count: int,
            partial_gap_count: int = 0,
            partial_exact_lemma_count: int = 0,
            partial_missing_lemma_count: int = 0,
        ) -> dict[str, Any]:
            resolution_actual = _build_resolution_actual(
                resolution_meta,
                fills,
                exact_lemma_match_count,
                partial_gap_count=partial_gap_count,
                partial_exact_lemma_count=partial_exact_lemma_count,
                partial_missing_lemma_count=partial_missing_lemma_count,
            )
            payload["resolution_meta"] = resolution_meta
            payload["resolution_actual"] = resolution_actual
            payload["resolution_live"] = resolution_actual
            return payload

        if exact_entries:
            exact_mode = "exact_lemma_checked" if lemma_oracle_used else "exact"
            exact_result = self._build_fill_result(surface, exact_entries, exact_mode)
            exact_fill = exact_result["fill"]
            exact_outcome = "exact_kept_after_lemma_check" if lemma_oracle_used else "surface_exact"
            exact_fill_mode = str((exact_fill or {}).get("mode") or exact_mode).strip().lower()
            resolution_meta: dict[str, Any]
            if lemma_oracle_used and exact_match_info["matches"]:
                self._annotate_single_fill_lemma_promotion(
                    exact_fill,
                    exact_match_info["matches"][0],
                    mode="exact_lemma_promoted",
                    fallback_upos=upos,
                    fallback_xpos=xpos,
                )
                exact_outcome = "exact_kept_with_lemma_promotion"
                exact_fill_mode = (
                    str((exact_fill or {}).get("mode") or "exact_lemma_promoted").strip().lower()
                )
                resolution_meta = _build_resolution_meta(
                    "exact_lemma_match",
                    "surface_exact_lemma_match",
                    [
                        _resolution_route_step(
                            "surface_exact_lookup", "surface exact lookup matched"
                        ),
                        _resolution_route_step(
                            "lemma_check", "lemma check found an underlying lemma match"
                        ),
                    ],
                    "surface",
                    exact_fill_mode,
                    True,
                    exact_outcome,
                )
            else:
                exact_route_steps = [
                    _resolution_route_step("surface_exact_lookup", "surface exact lookup matched")
                ]
                if lemma_oracle_used:
                    exact_route_steps.append(
                        _resolution_route_step(
                            "lemma_check", "lemma check kept the surface exact result"
                        )
                    )
                resolution_meta = _build_resolution_meta(
                    "exact_match",
                    "surface_exact_lemma_checked" if lemma_oracle_used else "surface_exact",
                    exact_route_steps,
                    "surface",
                    exact_fill_mode,
                    lemma_oracle_used,
                    exact_outcome,
                )
            return _attach_resolution_compat(
                {
                    "exact_entries": exact_entries[:],
                    "fill": exact_fill,
                    "all_entries": exact_entries[:],
                    "preferred_entries": exact_preferred_entries[:],
                    "dict_head": surface,
                    "resolved_via": "surface",
                    "lemma_hint_data": hint_data,
                    "lemma_oracle_used": lemma_oracle_used,
                    "lemma_oracle_outcome": exact_outcome,
                    "exact_lemma_match_count": len(exact_match_info["entries"]),
                },
                resolution_meta,
                exact_fill.get("fills") if isinstance(exact_fill, dict) else None,
                len(exact_match_info["entries"]),
            )

        if lemma_oracle_used:
            aligned = self._build_aligned_lemma_override_result(
                surface,
                lemma_hints,
                upos=upos,
                xpos=xpos,
                debug=debug,
            )
            if aligned is not None:
                aligned["lemma_hint_data"] = hint_data
                partial_gap_count = int(aligned.get("partial_gap_count") or 0)
                partial_exact_count = int(aligned.get("partial_exact_lemma_count") or 0)
                partial_missing_count = int(aligned.get("partial_missing_lemma_count") or 0)
                aligned_resolved_via = str(aligned.get("resolved_via") or "").strip().lower()
                if aligned_resolved_via == "lemma_partial_override":
                    aligned["resolution_meta"] = _build_resolution_meta(
                        "lemma_partial_override",
                        "surface_no_match_then_partial_lemma_exact_then_gap_greedy",
                        [
                            _resolution_route_step(
                                "surface_exact_lookup", "surface exact lookup missed"
                            ),
                            _resolution_route_step(
                                "lemma_exact_parts",
                                "exact lemma parts were aligned onto the surface",
                            ),
                            _resolution_route_step(
                                "lemma_gap_greedy",
                                "greedy DP filled the remaining uncovered spans"
                                if partial_gap_count > 0
                                else "no uncovered spans remained after exact lemma-part alignment",
                            ),
                        ],
                        "lemma_partial_override",
                        str((aligned.get("fill") or {}).get("mode") or "lemma_partial_greedy")
                        .strip()
                        .lower(),
                        True,
                        str(
                            aligned.get("lemma_oracle_outcome")
                            or (
                                "lemma_partial_exact_gaps"
                                if partial_gap_count > 0
                                else "lemma_partial_exact_only"
                            )
                        )
                        .strip()
                        .lower(),
                        {
                            "partial_exact_lemma_count": partial_exact_count,
                            "partial_missing_lemma_count": partial_missing_count,
                            "partial_gap_count": partial_gap_count,
                        },
                    )
                else:
                    aligned["resolution_meta"] = _build_resolution_meta(
                        "lemma_override",
                        "surface_no_match_then_lemma_exact_parts",
                        [
                            _resolution_route_step(
                                "surface_exact_lookup", "surface exact lookup missed"
                            ),
                            _resolution_route_step(
                                "lemma_exact_parts", "all lemma parts resolved by exact lookup"
                            ),
                            _resolution_route_step(
                                "lemma_override", "lemma exact-part alignment selected"
                            ),
                        ],
                        "lemma_override",
                        str((aligned.get("fill") or {}).get("mode") or "lemma_override")
                        .strip()
                        .lower(),
                        True,
                        "lemma_override_exact_parts",
                    )
                return _attach_resolution_compat(
                    aligned,
                    aligned.get("resolution_meta")
                    if isinstance(aligned.get("resolution_meta"), dict)
                    else None,
                    (aligned.get("fill") or {}).get("fills")
                    if isinstance(aligned.get("fill"), dict)
                    else None,
                    int(aligned.get("exact_lemma_match_count") or 0),
                    partial_gap_count=partial_gap_count,
                    partial_exact_lemma_count=partial_exact_count,
                    partial_missing_lemma_count=partial_missing_count,
                )

        fill_opts = {"allowExact": False, "upos": upos, "debug": debug}
        if lemma_oracle_used:
            fill_opts["lemma_hints"] = lemma_hints
        fill = self.fill_token(surface, fill_opts)

        if fill and fill.get("has_known"):
            promoted = (
                self._collect_promoted_fill_entries(fill) if fill.get("has_lemma_promotion") else []
            )
            all_entries = promoted if promoted else self._collect_fill_entries(fill)
            if all_entries:
                fill_mode = str((fill or {}).get("mode") or "greedy").strip().lower()
                resolution_category = "greedy_lemma_match" if promoted else "greedy_segmentation"
                resolution_route_code = (
                    "surface_greedy_lemma_match" if promoted else "surface_greedy"
                )
                resolution_route_steps = [
                    _resolution_route_step("surface_exact_lookup", "surface exact lookup missed")
                ]
                if promoted:
                    resolution_route_steps.append(
                        _resolution_route_step(
                            "lemma_greedy", "lemma-aware greedy DP selected lemma-linked pieces"
                        )
                    )
                elif lemma_oracle_used:
                    resolution_route_steps.append(
                        _resolution_route_step(
                            "lemma_greedy", "lemma-aware greedy DP selected a surface path"
                        )
                    )
                else:
                    resolution_route_steps.append(
                        _resolution_route_step(
                            "surface_greedy", "surface greedy DP selected the final path"
                        )
                    )
                lemma_outcome = (
                    "lemma_promoted"
                    if promoted
                    else ("lemma_checked_no_promotion" if lemma_oracle_used else "surface_greedy")
                )
                resolution_meta = _build_resolution_meta(
                    resolution_category,
                    resolution_route_code,
                    resolution_route_steps,
                    "lemma_promoted" if promoted else "surface",
                    fill_mode,
                    lemma_oracle_used,
                    lemma_outcome,
                )
                return _attach_resolution_compat(
                    {
                        "exact_entries": exact_entries[:],
                        "fill": fill,
                        "all_entries": all_entries[:],
                        "preferred_entries": all_entries[:],
                        "dict_head": str(all_entries[0].get("headword") or surface)
                        if promoted
                        else surface,
                        "resolved_via": "lemma_promoted" if promoted else "surface",
                        "lemma_hint_data": hint_data,
                        "lemma_oracle_used": lemma_oracle_used,
                        "lemma_oracle_outcome": lemma_outcome,
                        "exact_lemma_match_count": 0,
                    },
                    resolution_meta,
                    (fill or {}).get("fills"),
                    0,
                )

        resolution_meta = _build_resolution_meta(
            "",
            "surface_no_match_after_lemma_check" if lemma_oracle_used else "surface_no_match",
            [
                _resolution_route_step("surface_exact_lookup", "surface exact lookup missed"),
                _resolution_route_step(
                    "lemma_greedy" if lemma_oracle_used else "surface_greedy",
                    "lemma-aware greedy DP found no known dictionary path"
                    if lemma_oracle_used
                    else "surface greedy DP found no known dictionary path",
                ),
            ],
            "surface",
            str((fill or {}).get("mode") or "greedy").strip().lower(),
            lemma_oracle_used,
            "no_lemma_match" if lemma_oracle_used else "no_match",
        )
        return _attach_resolution_compat(
            {
                "exact_entries": exact_entries[:],
                "fill": fill,
                "all_entries": [],
                "preferred_entries": [],
                "dict_head": surface,
                "resolved_via": "surface",
                "lemma_hint_data": hint_data,
                "lemma_oracle_used": lemma_oracle_used,
                "lemma_oracle_outcome": "no_lemma_match" if lemma_oracle_used else "no_match",
                "exact_lemma_match_count": 0,
            },
            resolution_meta,
            (fill or {}).get("fills"),
            0,
        )

    def wikt_lookup(
        self,
        word: str,
        lemma: str | Sequence[str] | Sequence[dict[str, Any]] | None,
        *,
        xpos: str = "",
        upos: str = "",
        debug: bool = False,
    ) -> dict[str, Any] | None:
        surface = str(word or "").strip()
        if not surface:
            return None

        surface_result = self._resolve_exact_then_greedy(
            display_text=surface,
            lookup_text=surface,
            upos=upos,
            exact_mode="exact",
            greedy_mode="greedy",
            lemma_hint=lemma,
            xpos_hint=xpos,
            debug=debug,
        )

        lemma_text = self._lemma_to_text_for_override(lemma)
        if not lemma_text or self._normalize_visible_comparison_text(
            lemma_text
        ) == self._normalize_visible_comparison_text(surface):
            if surface_result is not None:
                surface_result["resolved_via"] = "surface"
            return surface_result

        lemma_result = self._resolve_lemma_override(
            surface, lemma_text, upos=upos, xpos=xpos, debug=debug
        )
        if lemma_result is None:
            if surface_result is not None:
                surface_result["resolved_via"] = "surface"
            return surface_result
        if surface_result is None:
            lemma_result["resolved_via"] = "lemma"
            return lemma_result

        surface_has_unknown = bool(surface_result.get("fill", {}).get("has_unknown"))
        lemma_has_unknown = bool(lemma_result.get("fill", {}).get("has_unknown"))
        if surface_has_unknown != lemma_has_unknown:
            chosen = lemma_result if surface_has_unknown else surface_result
            chosen["resolved_via"] = "lemma" if surface_has_unknown else "surface"
            return chosen

        lemma_count = self._result_match_count(lemma_result)
        surface_count = self._result_match_count(surface_result)
        if lemma_count < surface_count:
            lemma_result["resolved_via"] = "lemma"
            return lemma_result
        if lemma_count == surface_count:
            surface_mode = str(surface_result.get("fill", {}).get("mode") or "").lower()
            chosen = surface_result if surface_mode == "exact" else lemma_result
            chosen["resolved_via"] = "surface" if chosen is surface_result else "lemma"
            return chosen
        surface_result["resolved_via"] = "surface"
        return surface_result

    # ------------------------------------------------------------------
    # Exact/greedy helpers
    # ------------------------------------------------------------------

    def _resolve_exact_then_greedy(
        self,
        *,
        display_text: str,
        lookup_text: str,
        upos: str,
        exact_mode: str,
        greedy_mode: str,
        lemma_hint: Any,
        xpos_hint: str,
        debug: bool,
    ) -> dict[str, Any] | None:
        del lemma_hint, xpos_hint
        query = str(lookup_text or "").strip()
        if not query:
            return None
        entries = self.lookup_all(query, trace=debug)
        if entries:
            return self._build_fill_result(display_text or query, entries[:], exact_mode)
        fill = self.fill_token(query, {"allowExact": False, "upos": upos, "debug": debug})
        if fill and fill.get("has_known"):
            all_entries = self._collect_fill_entries(fill)
            if all_entries:
                fill_out = copy.deepcopy(fill)
                fill_out["mode"] = greedy_mode
                return {"entries": all_entries, "fill": fill_out}
        return None

    def _resolve_lemma_override(
        self,
        surface: str,
        lemma_text: str,
        *,
        upos: str,
        xpos: str,
        debug: bool,
    ) -> dict[str, Any] | None:
        parts = self._split_compound_lemma(lemma_text)
        lookup_target = "".join(parts) if parts else str(lemma_text or "").strip()
        if not lookup_target:
            return None
        return self._resolve_exact_then_greedy(
            display_text=surface,
            lookup_text=lookup_target,
            upos=upos,
            exact_mode="lemma_override",
            greedy_mode="lemma_greedy",
            lemma_hint=lemma_text,
            xpos_hint=xpos,
            debug=debug,
        )

    # ------------------------------------------------------------------
    # DP segmenter port
    # ------------------------------------------------------------------

    def fill_token(
        self,
        word: str,
        allow_exact_or_opts: bool | dict[str, Any] = True,
        exclude_whole: bool = False,
        upos: str = "",
        debug: bool = False,
    ) -> dict[str, Any]:
        if isinstance(allow_exact_or_opts, dict):
            opts = dict(allow_exact_or_opts)
        else:
            opts = {
                "allowExact": allow_exact_or_opts is not False,
                "excludeWhole": bool(exclude_whole),
                "upos": upos,
                "debug": bool(debug),
            }
        allow_exact = opts.get("allowExact", True) is not False
        ex_whole = bool(opts.get("excludeWhole", False))
        upos_value = str(opts.get("upos") or "")
        debug_value = bool(opts.get("debug", False))
        boundaries = opts.get("boundaries")
        boundaries_value = list(boundaries) if isinstance(boundaries, (list, tuple)) else None
        lemma_hints = opts.get("lemma_hints")
        lemma_hints_value = list(lemma_hints) if isinstance(lemma_hints, (list, tuple)) else None

        if allow_exact and not ex_whole:
            entries = self.lookup_all(word, trace=debug_value)
            if entries:
                fill = self._entry_to_fill(entries[0], word)
                fill["entries"] = entries
                return {"mode": "exact", "fills": [fill], "has_known": True, "has_unknown": False}

        return self._greedy_fill_simple(
            word,
            exclude_whole=ex_whole,
            boundaries=boundaries_value,
            debug=debug_value,
            lemma_hints=lemma_hints_value,
            upos=upos_value,
        )

    def _greedy_fill_simple(
        self,
        word: str,
        *,
        exclude_whole: bool,
        boundaries: Sequence[int] | None,
        debug: bool,
        lemma_hints: Sequence[Any] | None,
        upos: str,
    ) -> dict[str, Any]:
        del upos
        if not word:
            return {"mode": "greedy", "fills": [], "has_known": False, "has_unknown": False}

        engine_lang = self.lang_code
        whole_word_key = self._normalize_cached(word)

        if not exclude_whole:
            exact_entries = self.lookup_all(word, trace=debug)
            if exact_entries:
                exact_fill = self._entry_to_fill(exact_entries[0], word)
                exact_fill["entries"] = exact_entries
                promoted_lemma = None
                promoted_meta = None
                for raw_hint in list(lemma_hints or []):
                    hint_texts = self._get_lemma_hint_texts(raw_hint, engine_lang)
                    for hint_text in hint_texts:
                        if not hint_text:
                            continue
                        hint_key = self._normalize_cached(hint_text)
                        if hint_key == whole_word_key:
                            promoted_lemma = hint_text
                            promoted_meta = raw_hint if isinstance(raw_hint, dict) else None
                            break
                        for entry in exact_entries:
                            if self._entry_headword_key(entry) == hint_key:
                                promoted_lemma = hint_text
                                promoted_meta = raw_hint if isinstance(raw_hint, dict) else None
                                break
                        if promoted_lemma:
                            break
                    if promoted_lemma:
                        break
                if promoted_lemma:
                    exact_fill["_lemma_promoted"] = promoted_lemma
                    exact_fill["_lemma_promoted_headword"] = str(
                        exact_entries[0].get("headword") or ""
                    )
                    if promoted_meta and promoted_meta.get("upos"):
                        exact_fill["_lemma_upos_hint"] = str(promoted_meta.get("upos") or "")
                    if promoted_meta and promoted_meta.get("xpos"):
                        exact_fill["_lemma_xpos_hint"] = str(promoted_meta.get("xpos") or "")
                return {
                    "mode": "greedy",
                    "fills": [exact_fill],
                    "has_known": True,
                    "has_unknown": False,
                    "has_lemma_promotion": bool(promoted_lemma),
                }

        n = len(word)
        inf = 10**9
        dp_unknown = [inf] * (n + 1)
        dp_pieces = [inf] * (n + 1)
        dp_promoted = [0] * (n + 1)
        dp_used_lemma_keys: list[dict[str, bool] | None] = [None] * (n + 1)
        choice: list[dict[str, Any] | None] = [None] * (n + 1)
        boundary_set: set[int] | None = None
        boundary_list: list[int] | None = None
        trace_steps: list[dict[str, Any] | None] | None = [None] * n if debug else None

        lemma_hint_list = list(lemma_hints or [])
        hint_prefetch_keys: set[str] = set()
        for raw_hint in lemma_hint_list:
            for hint_text in self._get_lemma_hint_texts(raw_hint, engine_lang):
                hint_key = self._normalize_cached(hint_text)
                if hint_key:
                    hint_prefetch_keys.add(hint_key)
        span_keys, candidate_keys = self._build_span_key_matrix(word, trace=debug)
        probe_keys = set(candidate_keys)
        probe_keys.update(hint_prefetch_keys)
        self._prefetch_candidate_keys(sorted(probe_keys), trace=debug)
        lemma_hint_meta: dict[str, dict[str, str]] = {}
        lemma_hint_labels: dict[str, str] = {}
        has_lemma_promotion = False
        lp_tag = "__promoted_lemma_keys__"
        tagged_entries: list[dict[str, Any]] = []

        def tag_promoted_entry(entry: dict[str, Any], lemma_key: str) -> None:
            if not entry or not lemma_key:
                return
            tags = entry.get(lp_tag)
            if not tags:
                entry[lp_tag] = [lemma_key]
                tagged_entries.append(entry)
                return
            if lemma_key not in tags:
                tags.append(lemma_key)

        for raw_hint in lemma_hint_list:
            if isinstance(raw_hint, dict):
                hint = str(raw_hint.get("text") or raw_hint.get("lemma") or "").strip()
                hint_upos = str(raw_hint.get("upos") or "").strip()
                hint_xpos = str(raw_hint.get("xpos") or "").strip()
            else:
                hint = str(raw_hint or "").strip()
                hint_upos = ""
                hint_xpos = ""
            if not hint:
                continue
            hint_texts = self._get_lemma_hint_texts(raw_hint, engine_lang)
            if not hint_texts:
                continue
            lemma_key = (
                self._normalize_cached(hint)
                or self._normalize_cached(hint_texts[0])
                or hint_texts[0]
            )
            if not lemma_key:
                continue
            has_lemma_promotion = True
            lemma_hint_labels.setdefault(lemma_key, hint)
            if hint_upos or hint_xpos:
                meta = lemma_hint_meta.setdefault(lemma_key, {"upos": "", "xpos": ""})
                if hint_upos and not meta["upos"]:
                    meta["upos"] = hint_upos
                if hint_xpos and not meta["xpos"]:
                    meta["xpos"] = hint_xpos
            for hint_text in hint_texts:
                if not hint_text:
                    continue
                hint_key = self._normalize_cached(hint_text)
                if not hint_key:
                    continue
                for entry in self._get_candidate_entries_for_key(hint_key, trace=debug):
                    tag_promoted_entry(entry, lemma_key)

        def get_lemma_hint_meta(lemma_key: str) -> dict[str, str] | None:
            return lemma_hint_meta.get(lemma_key)

        def get_promoted_lemma_keys(entry: dict[str, Any]) -> list[str] | None:
            if not has_lemma_promotion:
                return None
            vals = entry.get(lp_tag)
            return vals if vals else None

        def cleanup_lp_tags() -> None:
            for entry in tagged_entries:
                entry.pop(lp_tag, None)

        def filter_entries_for_lemma_reuse(
            entries: Sequence[dict[str, Any]], used_lemma_keys: dict[str, bool] | None
        ) -> list[dict[str, Any]]:
            if not entries:
                return []
            if not used_lemma_keys:
                return list(entries)
            out: list[dict[str, Any]] = []
            for entry in entries:
                lemma_keys = get_promoted_lemma_keys(entry)
                if not lemma_keys:
                    out.append(entry)
                    continue
                for key in lemma_keys:
                    if not used_lemma_keys.get(key):
                        out.append(entry)
                        break
            return out

        def check_candidates_for_promotion(
            entries: Sequence[dict[str, Any]], used_lemma_keys: dict[str, bool] | None
        ) -> LemmaPromotion | None:
            if not has_lemma_promotion or not entries:
                return None
            for idx, entry in enumerate(entries):
                matches = get_promoted_lemma_keys(entry)
                if not matches:
                    continue
                for match in matches:
                    if used_lemma_keys and used_lemma_keys.get(match):
                        continue
                    meta = get_lemma_hint_meta(match) or {}
                    return LemmaPromotion(
                        index=idx,
                        lemma=lemma_hint_labels.get(match, match),
                        lemma_key=match,
                        entry=entry,
                        upos=str(meta.get("upos") or ""),
                        xpos=str(meta.get("xpos") or ""),
                    )
            return None

        def build_boundary_data(
            raw_boundaries: Sequence[int] | None,
        ) -> tuple[list[int] | None, set[int] | None]:
            if raw_boundaries is None:
                return None, None
            values = [0, n]
            for raw in raw_boundaries:
                try:
                    b = int(raw)
                except Exception:
                    continue
                if 0 < b < n:
                    values.append(b)
            values = sorted(set(values))
            if len(values) < 2:
                return None, None
            return values, set(values)

        boundary_list, boundary_set = build_boundary_data(boundaries)

        def is_better(
            c_promoted_here: int,
            c_promoted: int,
            c_unknown: int,
            c_pieces: int,
            c_span_len: int,
            b_promoted_here: int,
            b_promoted: int,
            b_unknown: int,
            b_pieces: int,
            b_span_len: int,
        ) -> bool:
            if bool(c_promoted_here) != bool(b_promoted_here):
                return bool(c_promoted_here)
            if c_promoted_here and b_promoted_here and c_span_len != b_span_len:
                return c_span_len > b_span_len
            if c_unknown != b_unknown:
                return c_unknown < b_unknown
            if c_promoted != b_promoted:
                return c_promoted > b_promoted
            if c_pieces != b_pieces:
                return c_pieces < b_pieces
            return c_span_len > b_span_len

        def crosses_restricted_boundary(start: int, end: int) -> bool:
            if not boundary_list or len(boundary_list) <= 2:
                return False
            if start >= end:
                return False
            if boundary_set and start in boundary_set and end in boundary_set:
                return False
            for b in boundary_list:
                if b <= start:
                    continue
                if b >= end:
                    break
                return True
            return False

        dp_unknown[n] = 0
        dp_pieces[n] = 0
        dp_promoted[n] = 0
        dp_used_lemma_keys[n] = None
        choice[n] = None

        for i in range(n - 1, -1, -1):
            best_state: dict[str, Any] = {
                "promoted_here": 0,
                "promoted": 0,
                "unknown": inf,
                "pieces": inf,
                "end": -1,
                "entries": None,
                "lookup_key": "",
                "kind": "",
                "span_len": 0,
                "xpos_hint": "",
                "trace": None,
                "lemma_promotion": None,
                "used_lemma_keys": None,
            }
            step_trace = (
                {
                    "index": i,
                    "accepted": [],
                    "rejected": [],
                    "unknown_fallback": None,
                    "selected": None,
                }
                if debug
                else None
            )

            for end in range(i + 1, n + 1):
                piece = word[i:end]
                piece_key = (
                    span_keys[i][end] if i < len(span_keys) and end < len(span_keys[i]) else ""
                )
                if exclude_whole and n > 1 and i == 0 and end == n:
                    continue
                if dp_unknown[end] >= inf:
                    continue
                if not piece_key:
                    continue
                if crosses_restricted_boundary(i, end):
                    if step_trace is not None:
                        step_trace["rejected"].append(
                            {
                                "kind": "known",
                                "start": i,
                                "end": end,
                                "piece": piece,
                                "reason": "crosses_lemma_boundary",
                                "detail": "boundary_cross",
                            }
                        )
                    continue

                cached_entries = list(self._candidate_cache.get(piece_key) or [])
                if not cached_entries:
                    continue
                used_lemma_keys = dp_used_lemma_keys[end]
                available_entries = filter_entries_for_lemma_reuse(cached_entries, used_lemma_keys)
                if not available_entries:
                    if step_trace is not None:
                        step_trace["rejected"].append(
                            {
                                "kind": "known",
                                "start": i,
                                "end": end,
                                "piece": piece,
                                "reason": "lemma_already_consumed",
                                "lemma_keys": sorted((used_lemma_keys or {}).keys()),
                            }
                        )
                    continue

                c_unknown = dp_unknown[end]
                c_pieces = 1 + dp_pieces[end]
                span_len = end - i
                promotion = check_candidates_for_promotion(available_entries, used_lemma_keys)
                promoted_here = 1 if promotion else 0
                c_promoted = dp_promoted[end] + promoted_here
                next_used_lemma_keys = used_lemma_keys
                if promotion is not None:
                    next_used_lemma_keys = dict(used_lemma_keys or {})
                    next_used_lemma_keys[promotion.lemma_key] = True

                if step_trace is not None:
                    step_trace["accepted"].append(
                        {
                            "kind": "known",
                            "start": i,
                            "end": end,
                            "piece": piece,
                            "entry_count": len(available_entries),
                            "score_promoted_here": promoted_here,
                            "score_unknown": c_unknown,
                            "score_pieces": c_pieces,
                            "score_promoted": c_promoted,
                            "lemma_promoted": promotion.lemma if promotion else None,
                            "lemma_promoted_headword": str(promotion.entry.get("headword") or "")
                            if promotion
                            else None,
                            "lemma_promoted_upos": promotion.upos if promotion else "",
                            "lemma_promoted_xpos": promotion.xpos if promotion else "",
                        }
                    )

                if is_better(
                    promoted_here,
                    c_promoted,
                    c_unknown,
                    c_pieces,
                    span_len,
                    best_state["promoted_here"],
                    best_state["promoted"],
                    best_state["unknown"],
                    best_state["pieces"],
                    best_state["span_len"],
                ):
                    best_state.update(
                        {
                            "promoted_here": promoted_here,
                            "promoted": c_promoted,
                            "unknown": c_unknown,
                            "pieces": c_pieces,
                            "end": end,
                            "entries": available_entries,
                            "lookup_key": piece_key,
                            "kind": "known",
                            "span_len": span_len,
                            "xpos_hint": "",
                            "lemma_promotion": promotion,
                            "used_lemma_keys": next_used_lemma_keys,
                        }
                    )

            unknown_end = i + 1
            if unknown_end <= n and dp_unknown[unknown_end] < inf:
                unknown_span = unknown_end - i
                u_unknown = unknown_span + dp_unknown[unknown_end]
                u_pieces = 1 + dp_pieces[unknown_end]
                u_promoted = dp_promoted[unknown_end]
                unknown_trace = (
                    {
                        "kind": "unknown",
                        "start": i,
                        "end": unknown_end,
                        "piece": word[i:unknown_end],
                        "score_promoted_here": 0,
                        "score_unknown": u_unknown,
                        "score_pieces": u_pieces,
                        "score_promoted": u_promoted,
                    }
                    if debug
                    else None
                )
                if step_trace is not None:
                    step_trace["unknown_fallback"] = unknown_trace
                if is_better(
                    0,
                    u_promoted,
                    u_unknown,
                    u_pieces,
                    unknown_span,
                    best_state["promoted_here"],
                    best_state["promoted"],
                    best_state["unknown"],
                    best_state["pieces"],
                    best_state["span_len"],
                ):
                    best_state.update(
                        {
                            "promoted_here": 0,
                            "promoted": u_promoted,
                            "unknown": u_unknown,
                            "pieces": u_pieces,
                            "end": unknown_end,
                            "entries": None,
                            "lookup_key": "",
                            "kind": "unknown",
                            "span_len": unknown_span,
                            "xpos_hint": "",
                            "lemma_promotion": None,
                            "used_lemma_keys": dp_used_lemma_keys[unknown_end],
                        }
                    )

            if best_state["end"] >= 0 and best_state["kind"]:
                dp_unknown[i] = best_state["unknown"]
                dp_pieces[i] = best_state["pieces"]
                dp_promoted[i] = best_state["promoted"]
                dp_used_lemma_keys[i] = best_state["used_lemma_keys"]
                choice[i] = {
                    "end": best_state["end"],
                    "entries": best_state["entries"],
                    "lookup_key": best_state["lookup_key"],
                    "kind": best_state["kind"],
                    "xpos_hint": best_state["xpos_hint"],
                    "lemma_promotion": best_state["lemma_promotion"],
                }
                if step_trace is not None:
                    selected = {
                        "kind": best_state["kind"],
                        "start": i,
                        "end": best_state["end"],
                        "piece": word[i : best_state["end"]],
                        "score_promoted_here": best_state["promoted_here"],
                        "score_unknown": best_state["unknown"],
                        "score_pieces": best_state["pieces"],
                        "score_promoted": best_state["promoted"],
                    }
                    if best_state["lemma_promotion"] is not None:
                        selected["lemma_promoted"] = best_state["lemma_promotion"].lemma
                        selected["lemma_promoted_headword"] = str(
                            best_state["lemma_promotion"].entry.get("headword") or ""
                        )
                    step_trace["selected"] = selected
                    trace_steps[i] = step_trace

        fills: list[dict[str, Any]] = []
        has_any_promotion = False
        idx = 0
        while idx < n:
            step = choice[idx]
            if not step or step["end"] <= idx:
                cleanup_lp_tags()
                fallback = {
                    "mode": "greedy",
                    "fills": [
                        {
                            "text": word,
                            "head": word,
                            "roman": "",
                            "senses": [],
                            "pos": "",
                            "source": "UNKNOWN",
                        }
                    ],
                    "has_known": False,
                    "has_unknown": True,
                    "has_lemma_promotion": False,
                }
                if debug:
                    fallback["dp_debug"] = {
                        "word": word,
                        "exclude_whole": bool(exclude_whole),
                        "boundaries": boundary_list[:] if boundary_list else [],
                        "steps": [step for step in (trace_steps or []) if step],
                    }
                return fallback

            seg_text = word[idx : step["end"]]
            if step["kind"] == "known" and step["entries"]:
                lookup_key = str(step.get("lookup_key") or "").strip()
                resolved_entries = self._materialize_candidates_for_lookup(
                    step["entries"],
                    seg_text,
                    query_key=lookup_key,
                    trace=debug,
                )
                if not resolved_entries:
                    fills.append(
                        {
                            "text": seg_text,
                            "head": seg_text,
                            "roman": "",
                            "senses": [],
                            "pos": "",
                            "source": "UNKNOWN",
                        }
                    )
                    idx = step["end"]
                    continue
                fill = self._entry_to_fill(resolved_entries[0], seg_text)
                fill["entries"] = resolved_entries
                if step.get("xpos_hint"):
                    fill["_xpos_hint"] = step["xpos_hint"]
                promotion = step.get("lemma_promotion")
                if promotion is not None:
                    has_any_promotion = True
                    fill["_lemma_promoted"] = promotion.lemma
                    fill["_lemma_promoted_headword"] = str(promotion.entry.get("headword") or "")
                    fill["_lemma_promoted_pos"] = str(
                        promotion.entry.get("pos_raw") or promotion.entry.get("pos") or ""
                    )
                    if promotion.upos:
                        fill["_lemma_upos_hint"] = promotion.upos
                    if promotion.xpos:
                        fill["_lemma_xpos_hint"] = promotion.xpos
                fills.append(fill)
            else:
                fills.append(
                    {
                        "text": seg_text,
                        "head": seg_text,
                        "roman": "",
                        "senses": [],
                        "pos": "",
                        "source": "UNKNOWN",
                    }
                )
            idx = step["end"]

        has_known = any(f.get("source") != "UNKNOWN" for f in fills)
        has_unknown = any(f.get("source") == "UNKNOWN" for f in fills)
        result = {
            "mode": "greedy",
            "fills": fills,
            "has_known": has_known,
            "has_unknown": has_unknown,
            "has_lemma_promotion": has_any_promotion,
        }
        if has_lemma_promotion:
            result["lemma_hints"] = lemma_hint_list[:]
        if debug:
            result["dp_debug"] = {
                "word": word,
                "exclude_whole": bool(exclude_whole),
                "boundaries": boundary_list[:] if boundary_list else [],
                "steps": [step for step in (trace_steps or []) if step],
            }
        cleanup_lp_tags()
        return result

    # ------------------------------------------------------------------
    # Hybrid lemma exact-part alignment layer
    # ------------------------------------------------------------------

    def _build_aligned_lemma_override_result(
        self,
        surface_text: str,
        lemma_hint_objects: Sequence[Any],
        *,
        upos: str,
        xpos: str,
        debug: bool,
    ) -> dict[str, Any] | None:
        state = self._build_lemma_hint_alignment_state(surface_text, lemma_hint_objects)
        if state is None:
            return None
        if state["exact_part_count"] <= 0:
            return None
        if (
            state["exact_part_count"] < state["total_part_count"]
            and not _ENABLE_PARTIAL_EXACT_LEMMA_GAP_FILL
        ):
            return None

        fill_rows: list[dict[str, Any]] = []
        gap_segments: list[dict[str, Any]] = []

        for group in state["alignment_groups"]:
            start = max(0, int(group.get("start") or 0))
            end = max(start, int(group.get("end") or start))
            surface_slice = state["surface"][start:end]
            raw_ids = list(group.get("part_ids") or [])
            part_ids: list[int] = []
            seen_ids: set[int] = set()
            for raw in raw_ids:
                try:
                    pid = int(raw)
                except Exception:
                    continue
                if pid < 0 or pid >= len(state["parts"]) or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                part_ids.append(pid)
            if not part_ids:
                continue

            exact_part_ids: list[int] = []
            gap_hint_objects: list[dict[str, Any]] = []
            for pid in part_ids:
                part = state["parts"][pid]
                if part["exact"] and part["entries"]:
                    exact_part_ids.append(pid)
                else:
                    gap_hint_objects.append(
                        self._clone_lemma_hint_object(
                            part.get("hint_object")
                            or {
                                "text": part.get("text"),
                                "upos": part.get("upos"),
                                "xpos": part.get("xpos"),
                            }
                        )
                    )

            if exact_part_ids:
                exact_parts = [state["parts"][part_id] for part_id in exact_part_ids]
                exact_spans = self._split_surface_slice_for_exact_parts(
                    surface_slice,
                    [part.get("text") or surface_slice for part in exact_parts],
                    start_offset=start,
                )
                for local_idx, part_id in enumerate(exact_part_ids):
                    exact_part = state["parts"][part_id]
                    part_entries = list(exact_part.get("entries") or [])
                    if not part_entries:
                        continue
                    span_meta = (
                        exact_spans[local_idx]
                        if local_idx < len(exact_spans)
                        else {"start": start, "end": end, "text": surface_slice}
                    )
                    piece_text = str(
                        span_meta.get("text") or exact_part.get("text") or surface_slice or ""
                    )
                    piece_start = int(span_meta.get("start") or start)
                    piece_end = int(span_meta.get("end") or end)
                    best = (
                        self._choose_entry(piece_text or exact_part["text"], part_entries)
                        or part_entries[0]
                    )
                    fill_row = self._build_fill_piece_from_entry(
                        piece_text or surface_slice, best, part_entries
                    )
                    if exact_part.get("text"):
                        fill_row["head"] = exact_part["text"]
                    fill_row["_lemma_override"] = exact_part["text"]
                    fill_row["_lemma_override_part_count"] = 1
                    fill_row["_lemma_part_index"] = exact_part["index"]
                    fill_row["_surface_start"] = piece_start
                    fill_row["_surface_end"] = piece_end
                    if exact_part.get("upos"):
                        fill_row["_lemma_upos_hint"] = exact_part["upos"]
                    if exact_part.get("xpos"):
                        fill_row["_lemma_xpos_hint"] = exact_part["xpos"]
                    fill_rows.append(fill_row)
            elif surface_slice:
                gap_segments.append(
                    {
                        "start": start,
                        "end": end,
                        "text": surface_slice,
                        "part_ids": part_ids[:],
                        "hint_objects": gap_hint_objects[:],
                    }
                )

        if not fill_rows:
            return None

        gap_debug: list[dict[str, Any]] = []
        for gap in gap_segments:
            gap_text = str(gap.get("text") or "")
            if not gap_text:
                continue
            gap_fill_opts = {"allowExact": False, "upos": upos, "debug": debug}
            if gap.get("hint_objects"):
                gap_fill_opts["lemma_hints"] = list(gap["hint_objects"])
            gap_fill = self.fill_token(gap_text, gap_fill_opts)
            gap_rows_src = (
                list(gap_fill.get("fills") or [])
                if gap_fill and gap_fill.get("fills")
                else [
                    {
                        "text": gap_text,
                        "head": gap_text,
                        "roman": "",
                        "senses": [],
                        "pos": "",
                        "source": "UNKNOWN",
                    }
                ]
            )
            offset_rows = self._clone_fill_rows_with_surface_offsets(
                gap_rows_src, gap_text, int(gap["start"])
            )
            if not offset_rows:
                return None
            fill_rows.extend(offset_rows)
            if debug:
                gap_debug.append(
                    {
                        "start": int(gap["start"]),
                        "end": int(gap["end"]),
                        "text": gap_text,
                        "part_ids": list(gap.get("part_ids") or []),
                        "mode": str(gap_fill.get("mode") or "greedy") if gap_fill else "greedy",
                        "has_known": bool(gap_fill.get("has_known")) if gap_fill else False,
                        "has_unknown": bool(gap_fill.get("has_unknown")) if gap_fill else True,
                        "fills": copy.deepcopy(gap_rows_src),
                        "dp_debug": copy.deepcopy(gap_fill.get("dp_debug")) if gap_fill else None,
                    }
                )

        fill_rows.sort(
            key=lambda row: (
                int(row.get("_surface_start", 0) or 0),
                int(row.get("_surface_end", 0) or 0),
                int(row.get("_lemma_part_index", 10**9) or 10**9),
            )
        )

        is_partial = state["exact_part_count"] < state["total_part_count"]
        fill_mode = "lemma_partial_greedy" if is_partial else "lemma_override"
        merged_fill = {
            "mode": fill_mode,
            "fills": fill_rows,
            "has_known": False,
            "has_unknown": False,
            "has_lemma_override": True,
            "has_lemma_promotion": False,
        }
        for row in fill_rows:
            if str(row.get("source") or "").upper() == "UNKNOWN":
                merged_fill["has_unknown"] = True
            else:
                merged_fill["has_known"] = True
            if row.get("_lemma_promoted"):
                merged_fill["has_lemma_promotion"] = True
        if gap_debug:
            merged_fill["dp_debug"] = {
                "mode": fill_mode,
                "exact_part_count": state["exact_part_count"],
                "total_part_count": state["total_part_count"],
                "gap_count": len(gap_segments),
                "gaps": gap_debug,
            }

        all_entries = self._collect_fill_entries(merged_fill)
        if not all_entries and not merged_fill["has_unknown"]:
            return None

        result = {
            "exact_entries": [],
            "fill": merged_fill,
            "all_entries": all_entries[:],
            "preferred_entries": all_entries[:],
            "dict_head": state["surface"],
            "resolved_via": "lemma_partial_override" if is_partial else "lemma_override",
            "lemma_oracle_used": True,
            "lemma_oracle_outcome": (
                "lemma_partial_exact_gaps"
                if is_partial and gap_segments
                else ("lemma_partial_exact_only" if is_partial else "lemma_override_exact_parts")
            ),
            "exact_lemma_match_count": state["exact_part_count"],
            "lemma_override_parts": [
                {
                    "text": part["text"],
                    "source_text": part["source_text"],
                    "upos": part["upos"],
                    "xpos": part["xpos"],
                    "matched": bool(part["exact"]) if is_partial else True,
                }
                for part in state["parts"]
            ],
        }
        if is_partial:
            result["partial_exact_lemma_count"] = state["exact_part_count"]
            result["partial_missing_lemma_count"] = (
                state["total_part_count"] - state["exact_part_count"]
            )
            result["partial_gap_count"] = len(gap_segments)
        return result

    # ------------------------------------------------------------------
    # Lemma hint utilities
    # ------------------------------------------------------------------

    def _normalize_visible_comparison_text(self, text: str) -> str:
        raw = str(text or "")
        if raw:
            raw = unicodedata.normalize("NFKC", raw)
        raw = _LOOKUP_INVISIBLE_COMPARISON_RE.sub("", raw)
        return raw.strip()

    def _split_compound_lemma(self, lemma: str) -> list[str]:
        text = str(lemma or "").strip()
        if not text or ("+" not in text and "＋" not in text):
            return []
        parts = [part.strip() for part in _COMPOUND_LEMMA_SPLIT_RE.split(text) if part.strip()]
        return parts if len(parts) > 1 else []

    def _is_persian_language_code(self, lang_value: str) -> bool:
        lang = str(lang_value or "").strip().lower()
        return lang == "fa" or lang == "persian" or lang.startswith("fa-")

    def _split_persian_lemma_variants(self, text: str) -> list[str]:
        raw = str(text or "").strip()
        if not raw or "#" not in raw:
            return []
        out: list[str] = []
        seen: set[str] = set()
        for part in (part.strip() for part in raw.split("#")):
            if not part or part in seen:
                continue
            seen.add(part)
            out.append(part)
        return out if len(out) > 1 else []

    def _get_lemma_hint_texts(self, raw_hint: Any, lang_code: str | None = None) -> list[str]:
        lang = str(lang_code or self.lang_code or "").strip().lower()
        out: list[str] = []
        seen: set[str] = set()

        def push_text(raw: Any) -> None:
            txt = str(raw or "").strip()
            if not txt or txt in seen:
                return
            seen.add(txt)
            out.append(txt)

        if isinstance(raw_hint, dict):
            for variant in list(raw_hint.get("variants") or []):
                push_text(variant)
            if not out and self._is_persian_language_code(lang):
                raw_text = str(raw_hint.get("text") or raw_hint.get("lemma") or "").strip()
                if raw_text and "#" in raw_text:
                    for part in self._split_persian_lemma_variants(raw_text):
                        push_text(part)
            if not out:
                push_text(raw_hint.get("text") or raw_hint.get("lemma") or "")
            return out

        push_text(raw_hint or "")
        return out

    def _get_lemma_hint_candidate_texts(self, raw_hint: Any) -> list[str]:
        if isinstance(raw_hint, dict):
            hint = raw_hint
        else:
            hint = {"text": str(raw_hint or "").strip()}
        out: list[str] = []
        seen: set[str] = set()

        def push_text(raw: Any) -> None:
            txt = str(raw or "").strip()
            if not txt or txt in seen:
                return
            seen.add(txt)
            out.append(txt)

        for variant in list(hint.get("variants") or []):
            push_text(variant)
        if not out and self._is_persian_language_code(self.lang_code):
            for variant in self._split_persian_lemma_variants(
                str(hint.get("text") or hint.get("lemma") or "")
            ):
                push_text(variant)
        if not out:
            push_text(hint.get("text") or hint.get("lemma") or "")
        return out

    def _clone_lemma_hint_object(self, raw_hint: Any) -> dict[str, Any]:
        if isinstance(raw_hint, dict):
            out = dict(raw_hint)
            if isinstance(raw_hint.get("variants"), list):
                out["variants"] = list(raw_hint["variants"])
            return out
        text = str(raw_hint or "").strip()
        return {"text": text} if text else {}

    def _lemma_to_text_for_override(
        self, lemma: str | Sequence[str] | Sequence[dict[str, Any]] | None
    ) -> str:
        if lemma is None:
            return ""
        if isinstance(lemma, str):
            return lemma.strip()
        parts: list[str] = []
        for item in lemma:
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("lemma") or "").strip()
            else:
                text = str(item or "").strip()
            if text:
                parts.append(text)
        if not parts:
            return ""
        return " + ".join(parts) if len(parts) > 1 else parts[0]

    def _build_lemma_hint_data(
        self,
        surface_text: str,
        lemma: str | Sequence[str] | Sequence[dict[str, Any]] | None,
        upos: str,
        xpos: str,
    ) -> dict[str, Any]:
        surface_value = str(surface_text or "").strip()
        lang = str(self.lang_code or "").strip().lower()

        raw_parts: list[str] = []
        hint_objects: list[dict[str, Any]] = []

        def make_hint_objects(parts: Sequence[str]) -> list[dict[str, Any]]:
            part_list = [str(part or "").strip() for part in parts if str(part or "").strip()]
            if not part_list:
                return []
            upos_parts = _split_compound_tags(upos)
            xpos_parts = _split_compound_tags(xpos)
            has_split_upos = len(upos_parts) == len(part_list)
            has_split_xpos = len(xpos_parts) == len(part_list)
            allow_token_level_xpos_fallback = not _is_korean_language_code(lang)
            out: list[dict[str, Any]] = []
            for idx, text in enumerate(part_list):
                hint = {
                    "text": text,
                    "upos": str((upos_parts[idx] if has_split_upos else upos) or "").strip(),
                    "xpos": str(
                        (
                            xpos_parts[idx]
                            if has_split_xpos
                            else (xpos if allow_token_level_xpos_fallback else "")
                        )
                        or ""
                    ).strip(),
                }
                if self._is_persian_language_code(lang):
                    variants = self._split_persian_lemma_variants(text)
                    if variants:
                        hint["variants"] = variants[:]
                out.append(hint)
            return out

        if lemma is None:
            lemma_value = ""
        elif isinstance(lemma, str):
            lemma_value = lemma.strip()
            differs = bool(lemma_value) and (
                self._normalize_visible_comparison_text(lemma_value)
                != self._normalize_visible_comparison_text(surface_value)
            )
            raw_parts = self._split_compound_lemma(lemma_value) if differs else []
            if differs and not raw_parts:
                raw_parts = [lemma_value]
            hint_objects = make_hint_objects(raw_parts)
            return {
                "lemma_text": lemma_value,
                "lemma_differs_from_surface": differs,
                "lemma_hint_parts_raw": raw_parts[:],
                "lemma_hint_objects": hint_objects,
            }
        else:
            parts: list[dict[str, Any]] = []
            seq = list(lemma)
            upos_parts = _split_compound_tags(upos)
            xpos_parts = _split_compound_tags(xpos)
            has_split_upos = len(upos_parts) == len(seq) and len(seq) > 0
            has_split_xpos = len(xpos_parts) == len(seq) and len(seq) > 0
            allow_token_level_xpos_fallback = not _is_korean_language_code(lang)
            for idx, item in enumerate(seq):
                if isinstance(item, dict):
                    text = str(item.get("text") or item.get("lemma") or "").strip()
                    if not text:
                        continue
                    obj = self._clone_lemma_hint_object(item)
                    if not str(obj.get("upos") or "").strip():
                        obj["upos"] = str(
                            (upos_parts[idx] if has_split_upos and idx < len(upos_parts) else upos)
                            or ""
                        ).strip()
                    if not str(obj.get("xpos") or "").strip():
                        obj["xpos"] = str(
                            (
                                xpos_parts[idx]
                                if has_split_xpos and idx < len(xpos_parts)
                                else (xpos if allow_token_level_xpos_fallback else "")
                            )
                            or ""
                        ).strip()
                    if self._is_persian_language_code(lang) and not obj.get("variants"):
                        variants = self._split_persian_lemma_variants(text)
                        if variants:
                            obj["variants"] = variants[:]
                    parts.append(obj)
                else:
                    text = str(item or "").strip()
                    if not text:
                        continue
                    hint = {
                        "text": text,
                        "upos": str(
                            (upos_parts[idx] if has_split_upos and idx < len(upos_parts) else upos)
                            or ""
                        ).strip(),
                        "xpos": str(
                            (
                                xpos_parts[idx]
                                if has_split_xpos and idx < len(xpos_parts)
                                else (xpos if allow_token_level_xpos_fallback else "")
                            )
                            or ""
                        ).strip(),
                    }
                    if self._is_persian_language_code(lang):
                        variants = self._split_persian_lemma_variants(text)
                        if variants:
                            hint["variants"] = variants[:]
                    parts.append(hint)
            hint_objects = parts
            raw_parts = [
                str(obj.get("text") or obj.get("lemma") or "").strip()
                for obj in parts
                if str(obj.get("text") or obj.get("lemma") or "").strip()
            ]
            lemma_value = " + ".join(raw_parts)

        differs = bool(raw_parts) and (
            len(raw_parts) > 1
            or any(
                self._normalize_visible_comparison_text(part)
                != self._normalize_visible_comparison_text(surface_value)
                for part in raw_parts
            )
        )
        if not differs:
            raw_parts = []
            hint_objects = []

        return {
            "lemma_text": lemma_value,
            "lemma_differs_from_surface": differs,
            "lemma_hint_parts_raw": raw_parts[:],
            "lemma_hint_objects": hint_objects,
        }

    def _find_lemma_hint_match_for_entry(
        self, entry: dict[str, Any], lemma_hint_objects: Sequence[Any]
    ) -> dict[str, Any] | None:
        if not entry or not lemma_hint_objects:
            return None
        candidate_texts: list[str] = []
        seen_texts: set[str] = set()

        def push_candidate(raw: Any) -> None:
            txt = str(raw or "").strip()
            if not txt or txt in seen_texts:
                return
            seen_texts.add(txt)
            candidate_texts.append(txt)

        push_candidate(entry.get("headword"))
        push_candidate(entry.get("morph_base"))
        push_candidate(entry.get("lemma_form"))
        push_candidate(entry.get("base_headword"))

        candidate_keys: set[str] = set()
        for text in candidate_texts:
            key = self._normalize_cached(text)
            if key:
                candidate_keys.add(key)

        for raw_hint in lemma_hint_objects:
            raw_hint_text = str(
                (raw_hint.get("text") if isinstance(raw_hint, dict) else raw_hint) or ""
            ).strip()
            for hint_text in self._get_lemma_hint_candidate_texts(raw_hint):
                if hint_text in seen_texts:
                    return {
                        "text": hint_text,
                        "source_text": raw_hint_text or hint_text,
                        "upos": str(raw_hint.get("upos") or "")
                        if isinstance(raw_hint, dict)
                        else "",
                        "xpos": str(raw_hint.get("xpos") or "")
                        if isinstance(raw_hint, dict)
                        else "",
                    }
                hint_key = self._normalize_cached(hint_text)
                if hint_key and hint_key in candidate_keys:
                    return {
                        "text": hint_text,
                        "source_text": raw_hint_text or hint_text,
                        "upos": str(raw_hint.get("upos") or "")
                        if isinstance(raw_hint, dict)
                        else "",
                        "xpos": str(raw_hint.get("xpos") or "")
                        if isinstance(raw_hint, dict)
                        else "",
                    }
        return None

    def _collect_entries_matching_lemma_hints(
        self, entries: Sequence[dict[str, Any]], lemma_hint_objects: Sequence[Any]
    ) -> dict[str, Any]:
        matched_entries: list[dict[str, Any]] = []
        matches: list[dict[str, Any]] = []
        for entry in entries:
            hint_match = self._find_lemma_hint_match_for_entry(entry, lemma_hint_objects)
            if hint_match is None:
                continue
            matched_entries.append(entry)
            matches.append({"entry": entry, "hint": hint_match})
        return {"entries": matched_entries, "matches": matches}

    def _annotate_single_fill_lemma_promotion(
        self,
        fill: dict[str, Any],
        match_record: dict[str, Any],
        *,
        mode: str,
        fallback_upos: str,
        fallback_xpos: str,
    ) -> dict[str, Any]:
        rows = list(fill.get("fills") or [])
        if not rows or not match_record:
            return fill
        row = rows[0]
        entry = match_record.get("entry") or {}
        hint = match_record.get("hint") or {}
        lemma_text = str(hint.get("text") or "").strip()
        if not lemma_text:
            return fill
        row["_lemma_promoted"] = lemma_text
        row["_lemma_promoted_headword"] = str(entry.get("headword") or "")
        row["_lemma_promoted_pos"] = str(entry.get("pos_raw") or entry.get("pos") or "")
        upos_hint = str(hint.get("upos") or fallback_upos or "").strip()
        xpos_hint = str(hint.get("xpos") or fallback_xpos or "").strip()
        if upos_hint:
            row["_lemma_upos_hint"] = upos_hint
        if xpos_hint:
            row["_lemma_xpos_hint"] = xpos_hint
        fill["has_lemma_promotion"] = True
        if mode:
            fill["mode"] = str(mode)
        return fill

    # ------------------------------------------------------------------
    # Alignment helpers
    # ------------------------------------------------------------------

    def _lookup_exact_entries_for_text(self, query_text: str) -> list[dict[str, Any]]:
        query = str(query_text or "").strip()
        if not query:
            return []
        return self.lookup_all(query)

    def _build_lemma_hint_lookup_part(self, raw_hint: Any) -> dict[str, Any] | None:
        hint = self._clone_lemma_hint_object(raw_hint)
        raw_hint_text = str(hint.get("text") or hint.get("lemma") or "").strip()
        hint_texts = self._get_lemma_hint_candidate_texts(hint)
        matched_text = ""
        matched_entries: list[dict[str, Any]] = []
        for candidate_text in hint_texts:
            if not candidate_text:
                continue
            candidate_entries = self._lookup_exact_entries_for_text(candidate_text)
            if not candidate_entries:
                continue
            matched_text = candidate_text
            matched_entries = candidate_entries
            break
        part_text = matched_text or raw_hint_text
        if not part_text:
            return None
        return {
            "text": part_text,
            "source_text": raw_hint_text or part_text,
            "upos": str(hint.get("upos") or "").strip(),
            "xpos": str(hint.get("xpos") or "").strip(),
            "entries": matched_entries,
            "exact": bool(matched_text and matched_entries),
            "hint_object": hint,
        }

    def _build_lemma_hint_alignment_state(
        self, surface_text: str, lemma_hint_objects: Sequence[Any]
    ) -> dict[str, Any] | None:
        surface = str(surface_text or "").strip()
        hints = list(lemma_hint_objects or [])
        if not surface or not hints:
            return None

        parts: list[dict[str, Any]] = []
        exact_part_count = 0
        for index, hint in enumerate(hints):
            part = self._build_lemma_hint_lookup_part(hint)
            if part is None:
                return None
            part["index"] = index
            if part["exact"]:
                exact_part_count += 1
            parts.append(part)
        if not parts:
            return None

        alignment = self._build_generic_surface_part_alignment(
            surface, [part["text"] for part in parts]
        )
        if alignment is None or not alignment.get("groups"):
            return None

        alignment_groups = [
            {
                "start": int(group.get("start") or 0),
                "end": int(group.get("end") or 0),
                "part_ids": list(group.get("part_ids") or []),
            }
            for group in alignment["groups"]
        ]

        present_part_ids: set[int] = set()
        for group in alignment_groups:
            for raw in group["part_ids"]:
                try:
                    pid = int(raw)
                except Exception:
                    continue
                if 0 <= pid < len(parts):
                    present_part_ids.add(pid)

        for missing_pid in range(len(parts)):
            if missing_pid in present_part_ids:
                continue
            best_group_index = -1
            best_distance = 10**9
            for gidx, group in enumerate(alignment_groups):
                if not group["part_ids"]:
                    continue
                for raw in group["part_ids"]:
                    try:
                        candidate_id = int(raw)
                    except Exception:
                        continue
                    if candidate_id < 0:
                        continue
                    distance = abs(candidate_id - missing_pid)
                    if distance < best_distance:
                        best_distance = distance
                        best_group_index = gidx
            if best_group_index >= 0:
                alignment_groups[best_group_index]["part_ids"].append(missing_pid)
                alignment_groups[best_group_index]["part_ids"] = sorted(
                    set(alignment_groups[best_group_index]["part_ids"])
                )
                present_part_ids.add(missing_pid)

        return {
            "surface": surface,
            "parts": parts,
            "alignment_groups": alignment_groups,
            "exact_part_count": exact_part_count,
            "total_part_count": len(parts),
        }

    def _decompose_text_to_alignment_units(self, text: str) -> list[str]:
        return list(str(text or ""))

    def _build_surface_codepoint_map(self, text: str) -> dict[str, Any]:
        src = list(str(text or ""))
        chars: list[dict[str, Any]] = []
        units: list[str] = []
        unit_to_char: list[int] = []
        code_unit_offset = 0
        for index, ch in enumerate(src):
            unit_chars = self._decompose_text_to_alignment_units(ch) or [ch]
            start_unit = len(units)
            for unit in unit_chars:
                units.append(unit)
                unit_to_char.append(index)
            offset_start = code_unit_offset
            code_unit_offset += len(ch)
            chars.append(
                {
                    "index": index,
                    "offset_start": offset_start,
                    "offset_end": code_unit_offset,
                    "char": ch,
                    "unit_start": start_unit,
                    "unit_end": len(units),
                }
            )
        return {
            "chars": chars,
            "units": units,
            "unit_to_char": unit_to_char,
            "text_length": len(str(text or "")),
        }

    def _build_groups_from_unit_part_ids(
        self,
        surface_map: dict[str, Any],
        unit_part_ids: Sequence[int],
        normalized_parts: Sequence[str],
        match_basis: str,
    ) -> dict[str, Any]:
        del normalized_parts
        char_part_ids: list[list[int]] = []
        for char_row in surface_map["chars"]:
            ids: list[int] = []
            seen: set[int] = set()
            for unit_index in range(char_row["unit_start"], char_row["unit_end"]):
                pid = unit_part_ids[unit_index]
                if pid >= 0 and pid not in seen:
                    seen.add(pid)
                    ids.append(pid)
            ids.sort()
            char_part_ids.append(ids)

        groups: list[dict[str, Any]] = []
        boundaries: list[int] = []
        group_start = 0
        for gi in range(len(char_part_ids)):
            same_as_prev = False
            if gi > 0:
                same_as_prev = char_part_ids[gi - 1] == char_part_ids[gi]
            if not same_as_prev and gi > 0:
                prev_char = surface_map["chars"][gi - 1]
                start_char = surface_map["chars"][group_start]
                groups.append(
                    {
                        "start": start_char["offset_start"],
                        "end": prev_char["offset_end"],
                        "part_ids": char_part_ids[gi - 1][:],
                        "part_count": len(char_part_ids[gi - 1]),
                        "unit_start": start_char["unit_start"],
                        "unit_end": prev_char["unit_end"],
                    }
                )
                boundaries.append(prev_char["offset_end"])
                group_start = gi
        if surface_map["chars"]:
            last_char = surface_map["chars"][-1]
            first_char = surface_map["chars"][group_start]
            groups.append(
                {
                    "start": first_char["offset_start"],
                    "end": last_char["offset_end"],
                    "part_ids": char_part_ids[-1][:] if char_part_ids else [],
                    "part_count": len(char_part_ids[-1]) if char_part_ids else 0,
                    "unit_start": first_char["unit_start"],
                    "unit_end": last_char["unit_end"],
                }
            )
        return {"boundaries": boundaries, "groups": groups, "match_basis": match_basis}

    def _build_proportional_alignment(
        self, surface_map: dict[str, Any], normalized_parts: Sequence[str]
    ) -> dict[str, Any]:
        total_lemma_len = sum(len(part) for part in normalized_parts)
        num_chars = len(surface_map["chars"])
        unit_part_ids = [-1] * len(surface_map["units"])

        char_cursor = 0
        for idx, part in enumerate(normalized_parts):
            share = len(part)
            if idx == len(normalized_parts) - 1:
                char_count = num_chars - char_cursor
            else:
                char_count = max(1, round(num_chars * share / (total_lemma_len or 1)))
                if char_cursor + char_count > num_chars:
                    char_count = num_chars - char_cursor
            for char_index in range(char_cursor, min(char_cursor + char_count, num_chars)):
                char_row = surface_map["chars"][char_index]
                for unit_index in range(char_row["unit_start"], char_row["unit_end"]):
                    unit_part_ids[unit_index] = idx
            char_cursor += char_count

        last_part = max(0, len(normalized_parts) - 1)
        for unit_index, value in enumerate(unit_part_ids):
            if value < 0:
                unit_part_ids[unit_index] = last_part
        return self._build_groups_from_unit_part_ids(
            surface_map, unit_part_ids, normalized_parts, "proportional"
        )

    def _build_generic_surface_part_alignment(
        self, surface: str, part_texts: Sequence[str]
    ) -> dict[str, Any] | None:
        surface_text = str(surface or "")
        if not surface_text:
            return None
        parts = [str(part or "") for part in list(part_texts or [])]
        if not parts or any(not part for part in parts):
            return None

        if len(parts) == 1:
            return {
                "boundaries": [],
                "groups": [
                    {"start": 0, "end": len(surface_text), "part_ids": [0], "part_count": 1}
                ],
                "match_basis": "single",
            }

        joined_text = "".join(parts)
        if joined_text == surface_text:
            groups = []
            boundaries = []
            cursor = 0
            for idx, part in enumerate(parts):
                next_cursor = cursor + len(part)
                groups.append(
                    {"start": cursor, "end": next_cursor, "part_ids": [idx], "part_count": 1}
                )
                cursor = next_cursor
                if idx < len(parts) - 1:
                    boundaries.append(next_cursor)
            return {"boundaries": boundaries, "groups": groups, "match_basis": "surface"}

        surface_map = self._build_surface_codepoint_map(surface_text)
        surface_units = surface_map["units"]
        if not surface_units:
            return None
        s_len = len(surface_units)

        lemma_units: list[str] = []
        lemma_unit_part_id: list[int] = []
        for part_id, part in enumerate(parts):
            p_units = self._decompose_text_to_alignment_units(part)
            for unit in p_units:
                lemma_units.append(unit)
                lemma_unit_part_id.append(part_id)
        l_len = len(lemma_units)

        if s_len == l_len and all(surface_units[i] == lemma_units[i] for i in range(s_len)):
            return self._build_groups_from_unit_part_ids(
                surface_map, lemma_unit_part_id, parts, "codepoint"
            )

        match_score = 2
        mismatch_score = -1
        gap_score = -1
        score = [[0] * (l_len + 1) for _ in range(s_len + 1)]
        for i in range(s_len + 1):
            score[i][0] = i * gap_score
        for j in range(l_len + 1):
            score[0][j] = j * gap_score
        for i in range(1, s_len + 1):
            for j in range(1, l_len + 1):
                diag = score[i - 1][j - 1] + (
                    match_score if surface_units[i - 1] == lemma_units[j - 1] else mismatch_score
                )
                up = score[i - 1][j] + gap_score
                left = score[i][j - 1] + gap_score
                score[i][j] = max(diag, up, left)

        surface_part_id = [-1] * s_len
        ti = s_len
        tj = l_len
        match_count = 0
        while ti > 0 and tj > 0:
            current = score[ti][tj]
            diag_val = score[ti - 1][tj - 1] + (
                match_score if surface_units[ti - 1] == lemma_units[tj - 1] else mismatch_score
            )
            if current == diag_val:
                if surface_units[ti - 1] == lemma_units[tj - 1]:
                    surface_part_id[ti - 1] = lemma_unit_part_id[tj - 1]
                    match_count += 1
                ti -= 1
                tj -= 1
            elif current == score[ti - 1][tj] + gap_score:
                ti -= 1
            else:
                tj -= 1

        if match_count == 0:
            return self._build_proportional_alignment(surface_map, parts)

        part_min_unit = [s_len] * len(parts)
        part_max_unit = [-1] * len(parts)
        part_has_match = [False] * len(parts)
        for su, pid in enumerate(surface_part_id):
            if pid < 0:
                continue
            part_has_match[pid] = True
            part_min_unit[pid] = min(part_min_unit[pid], su)
            part_max_unit[pid] = max(part_max_unit[pid], su)

        final_part_id = surface_part_id[:]
        for pid in range(len(parts)):
            if not part_has_match[pid]:
                continue
            for unit_index in range(part_min_unit[pid], part_max_unit[pid] + 1):
                if final_part_id[unit_index] < 0:
                    final_part_id[unit_index] = pid

        last_assigned = -1
        for idx, pid in enumerate(final_part_id):
            if pid >= 0:
                last_assigned = pid
            elif last_assigned >= 0:
                final_part_id[idx] = last_assigned
        last_assigned = -1
        for idx in range(len(final_part_id) - 1, -1, -1):
            pid = final_part_id[idx]
            if pid >= 0:
                last_assigned = pid
            elif last_assigned >= 0:
                final_part_id[idx] = last_assigned

        unmatched_parts = [pid for pid, has_match in enumerate(part_has_match) if not has_match]
        if unmatched_parts:
            ui = 0
            while ui < len(unmatched_parts):
                u_part = unmatched_parts[ui]
                prev_matched = next((p for p in range(u_part - 1, -1, -1) if part_has_match[p]), -1)
                next_matched = next(
                    (p for p in range(u_part + 1, len(parts)) if part_has_match[p]), -1
                )
                if prev_matched >= 0 and next_matched >= 0:
                    region_start = part_max_unit[prev_matched] + 1
                    region_end = part_min_unit[next_matched]
                elif prev_matched >= 0:
                    region_start = part_max_unit[prev_matched] + 1
                    region_end = s_len
                elif next_matched >= 0:
                    region_start = 0
                    region_end = part_min_unit[next_matched]
                else:
                    region_start = 0
                    region_end = s_len
                if region_start < region_end:
                    consecutive = [u_part]
                    while ui + 1 < len(unmatched_parts) and unmatched_parts[ui + 1] < (
                        next_matched if next_matched >= 0 else len(parts)
                    ):
                        ui += 1
                        consecutive.append(unmatched_parts[ui])
                    total_len = sum(len(parts[p]) for p in consecutive)
                    r_cursor = region_start
                    for idx, pid in enumerate(consecutive):
                        share = len(parts[pid])
                        if idx == len(consecutive) - 1:
                            unit_count = region_end - r_cursor
                        else:
                            unit_count = max(
                                1, round((region_end - region_start) * share / (total_len or 1))
                            )
                        assign_end = min(r_cursor + unit_count, region_end)
                        for unit_index in range(r_cursor, assign_end):
                            final_part_id[unit_index] = pid
                        r_cursor = assign_end
                ui += 1

        return self._build_groups_from_unit_part_ids(surface_map, final_part_id, parts, "codepoint")

    # ------------------------------------------------------------------
    # Fill/entry helpers
    # ------------------------------------------------------------------

    def _entry_to_fill(self, entry: dict[str, Any], text: str) -> dict[str, Any]:
        surface_text = str(text or "")
        lemma_head = str(entry.get("headword") or "")
        display_head = surface_text or lemma_head
        fill = {
            "text": surface_text,
            "head": display_head,
            "roman": entry.get("reading") or entry.get("romanization") or "",
            "senses": entry.get("senses") or [],
            "pos": entry.get("pos") or entry.get("pos_raw") or "",
            "source": "KAIKKI",
            "etymology": entry.get("etymology") or "",
            "senses_full": entry.get("senses_full") or [],
            "ipa_variants": entry.get("ipa_variants") or [],
        }
        if entry.get("morph_info"):
            fill["morph_info"] = entry["morph_info"]
        if entry.get("morph_base"):
            fill["morph_base"] = entry["morph_base"]
        if entry.get("grammar"):
            fill["grammar"] = entry["grammar"]
        if lemma_head and lemma_head != display_head:
            fill["surface_form"] = display_head
            fill["lemma_form"] = lemma_head
            if not fill.get("morph_base"):
                fill["morph_base"] = lemma_head
        return fill

    def _build_fill_piece_from_entry(
        self, surface_text: str, entry: dict[str, Any], all_entries: Sequence[dict[str, Any]]
    ) -> dict[str, Any]:
        surface = str(surface_text or "")
        lemma_head = str(entry.get("headword") or "")
        head = surface or lemma_head
        fill = {
            "text": surface,
            "head": head,
            "headword": head,
            "roman": entry.get("reading") or entry.get("romanization") or "",
            "reading": entry.get("reading") or entry.get("romanization") or "",
            "senses": entry.get("senses") or [],
            "pos": entry.get("pos") or entry.get("pos_raw") or "",
            "pos_raw": entry.get("pos_raw") or entry.get("pos") or "",
            "source": "KAIKKI",
            "entries": list(all_entries),
        }
        for key in (
            "entry_id",
            "etymology",
            "senses_full",
            "ipa_variants",
            "grammar",
            "morph_info",
            "morph_base",
        ):
            if entry.get(key):
                fill[key] = entry[key]
        if lemma_head and lemma_head != head:
            fill["surface_form"] = surface
            fill["lemma_form"] = lemma_head
            if not fill.get("morph_base"):
                fill["morph_base"] = lemma_head
        return fill

    def _build_fill_result(
        self, text: str, entries: Sequence[dict[str, Any]], mode: str
    ) -> dict[str, Any]:
        best = entries[0]
        fill_entry = self._build_fill_piece_from_entry(text, best, list(entries))
        return {
            "entries": list(entries),
            "fill": {
                "mode": mode,
                "fills": [fill_entry],
                "has_known": True,
                "has_unknown": False,
            },
        }

    def _choose_entry(
        self, surface: str, entries: Sequence[dict[str, Any]]
    ) -> dict[str, Any] | None:
        if not entries:
            return None
        if not surface:
            return entries[0]
        target_text = str(surface or "").strip()
        target_key = self._normalize_cached(target_text)
        normalized_match = None
        for entry in entries:
            headword = str(entry.get("headword") or "").strip()
            surface_form = str(entry.get("surface_form") or "").strip()
            if headword == target_text or (surface_form and surface_form == target_text):
                return entry
            if normalized_match is None and target_key:
                if headword and self._normalize_cached(headword) == target_key:
                    normalized_match = entry
                elif surface_form and self._normalize_cached(surface_form) == target_key:
                    normalized_match = entry
        return normalized_match or entries[0]

    def _collect_fill_entries(self, fill: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in list(fill.get("fills") or []):
            if str(row.get("source") or "").upper() == "UNKNOWN":
                continue
            out.extend(list(row.get("entries") or []))
        return out

    def _collect_promoted_fill_entries(self, fill: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in list(fill.get("fills") or []):
            if not row.get("_lemma_promoted"):
                continue
            out.extend(list(row.get("entries") or []))
        return out

    def _get_fill_piece_surface_text(self, row: dict[str, Any]) -> str:
        return str(row.get("text") or row.get("head") or "")

    def _clone_fill_rows_with_surface_offsets(
        self, fills: Sequence[dict[str, Any]], expected_text: str, start_offset: int
    ) -> list[dict[str, Any]] | None:
        rows = list(fills or [])
        surface_text = str(expected_text or "")
        offset_base = int(start_offset or 0)
        cursor = 0
        out: list[dict[str, Any]] = []
        for row in rows:
            piece_text = self._get_fill_piece_surface_text(row)
            if not piece_text:
                return None
            if surface_text[cursor : cursor + len(piece_text)] != piece_text:
                return None
            clone = dict(row)
            clone["_surface_start"] = offset_base + cursor
            cursor += len(piece_text)
            clone["_surface_end"] = offset_base + cursor
            out.append(clone)
        if cursor != len(surface_text):
            return None
        return out

    def _split_surface_slice_for_exact_parts(
        self,
        surface_text: str,
        part_texts: Sequence[str],
        start_offset: int = 0,
    ) -> list[dict[str, Any]]:
        surface = str(surface_text or "")
        parts = [str(part or "") for part in list(part_texts or [])]
        if not surface or not parts:
            return []

        def proportional_ranges(
            start: int, end: int, local_parts: Sequence[str], local_ids: Sequence[int]
        ) -> dict[int, tuple[int, int]]:
            width = max(0, int(end) - int(start))
            if not local_ids:
                return {}
            if len(local_ids) == 1:
                return {int(local_ids[0]): (int(start), int(end))}
            weights = [max(1, len(str(local_parts[idx] or ""))) for idx in local_ids]
            total = sum(weights) or len(local_ids)
            cursor = int(start)
            out_ranges: dict[int, tuple[int, int]] = {}
            for pos, local_id in enumerate(local_ids):
                remaining_ids = len(local_ids) - pos - 1
                if pos == len(local_ids) - 1:
                    next_cursor = int(end)
                else:
                    share = max(1, round(width * weights[pos] / total))
                    max_cursor = int(end) - remaining_ids
                    next_cursor = min(max_cursor, cursor + share)
                out_ranges[int(local_id)] = (cursor, next_cursor)
                cursor = next_cursor
            return out_ranges

        alignment = self._build_generic_surface_part_alignment(surface, parts)
        ranges: dict[int, tuple[int, int]] = {}
        if alignment and alignment.get("groups"):
            for group in sorted(
                list(alignment.get("groups") or []),
                key=lambda row: (int(row.get("start") or 0), int(row.get("end") or 0)),
            ):
                local_ids: list[int] = []
                seen: set[int] = set()
                for raw in list(group.get("part_ids") or []):
                    try:
                        local_id = int(raw)
                    except Exception:
                        continue
                    if local_id < 0 or local_id >= len(parts) or local_id in seen:
                        continue
                    seen.add(local_id)
                    local_ids.append(local_id)
                if not local_ids:
                    continue
                local_ids.sort()
                group_start = int(group.get("start") or 0)
                group_end = int(group.get("end") or 0)
                if group_end <= group_start:
                    continue
                for local_id, local_range in proportional_ranges(
                    group_start, group_end, parts, local_ids
                ).items():
                    ranges[local_id] = local_range

        if len(ranges) != len(parts):
            ranges = proportional_ranges(0, len(surface), parts, list(range(len(parts))))

        out: list[dict[str, Any]] = []
        for local_idx in range(len(parts)):
            local_start, local_end = ranges.get(local_idx, (0, len(surface)))
            local_start = max(0, min(local_start, len(surface)))
            local_end = max(local_start, min(local_end, len(surface)))
            out.append(
                {
                    "start": int(start_offset) + local_start,
                    "end": int(start_offset) + local_end,
                    "text": surface[local_start:local_end],
                }
            )
        return out

    def _result_match_count(self, result: dict[str, Any] | None) -> int:
        if not isinstance(result, dict):
            return 0
        fills = list(result.get("fill", {}).get("fills") or [])
        if fills:
            return len(fills)
        return len(list(result.get("entries") or []))


__all__ = ["SQLiteDictionarySegmenter"]
