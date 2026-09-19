"""
debug_panel.py â€” Debug Blueprint for inspecting raw pipeline data.

Visit /debug in the browser to see the last lookup's:
  1. Exact input text sent to the transformer
  2. Raw Trankit output (sentences, tokens, annotations)
  3. Neural tokens â†’ dictionary entry mapping

Language-agnostic: any pipeline that calls store_debug_snapshot() will
have its data displayed here.
"""

import json
import time
from flask import Blueprint, jsonify, request, Response

from debug_store import (
    clear_mwt_realign_traces,
    get_debug_json_artifact,
    get_debug_json_artifact_meta,
    get_debug_snapshot,
    get_mwt_realign_traces,
    is_debug_collection_enabled,
    is_mwt_realign_debug_enabled,
    update_debug_snapshot,
)

debug_bp = Blueprint("debug", __name__)
_SQLITE_PAYLOAD_ARTIFACT_SLUG = "sqlite_payload"


@debug_bp.route("/debug")
def debug_page():
    return Response(_DEBUG_HTML, mimetype="text/html")


@debug_bp.route("/debug/lemma_boundaries")
@debug_bp.route("/debug/korean_lemma_boundaries")
def debug_korean_lemma_boundaries_page():
    mode = str(request.args.get("mode", "") or "").strip().lower()
    if mode == "mwt_realign":
        return Response(_DEBUG_MWT_REALIGN_HTML, mimetype="text/html")
    return Response(_DEBUG_KOREAN_LEMMA_BOUNDARIES_HTML, mimetype="text/html")


@debug_bp.route("/debug/mwt_realign/data")
def debug_mwt_realign_data():
    if not is_mwt_realign_debug_enabled():
        return jsonify({"enabled": False, "traces": []})
    return jsonify({"enabled": True, "traces": get_mwt_realign_traces()})


@debug_bp.route("/debug/mwt_realign/clear", methods=["POST"])
def debug_mwt_realign_clear():
    clear_mwt_realign_traces()
    return jsonify({"ok": True})


@debug_bp.route("/debug/chatgpt_dump")
def debug_chatgpt_dump_page():
    return Response(_DEBUG_CHATGPT_DUMP_HTML, mimetype="text/html")


@debug_bp.route("/debug/scoring_information")
def debug_scoring_information_page():
    return Response(_DEBUG_SCORING_INFORMATION_HTML, mimetype="text/html")


@debug_bp.route("/debug/sqlite")
def debug_sqlite_page():
    return Response(_DEBUG_SQLITE_HTML, mimetype="text/html")


def _normalize_span(raw_span):
    if not isinstance(raw_span, (list, tuple)) or len(raw_span) < 2:
        return None
    try:
        start = int(raw_span[0])
        end = int(raw_span[1])
    except Exception:
        return None
    if end < start:
        end = start
    return [start, end]


def _extract_mwt_expanded_rows(tok):
    rows = []
    expanded = tok.get("mwt_expanded_words")
    if not isinstance(expanded, list) or not expanded:
        expanded = tok.get("expanded")
    if not isinstance(expanded, list):
        return rows
    parent_surface = str(tok.get("text", "") or "")
    # The realigner writes surface_slice + _realign_pass onto mwt_parts. We
    # surface those here too so the debug panel shows which pass anchored each
    # child and what parent-surface substring it maps to.
    for child in expanded:
        if not isinstance(child, dict):
            continue
        surface_slice = child.get("surface_slice")
        slice_text = ""
        if isinstance(surface_slice, (list, tuple)) and len(surface_slice) == 2:
            try:
                s = int(surface_slice[0])
                e = int(surface_slice[1])
                slice_text = parent_surface[s:e]
            except Exception:
                slice_text = ""
        rows.append(
            {
                "text": str(child.get("text", "") or ""),
                "lemma": str(child.get("lemma", "") or ""),
                "upos": str(child.get("upos", "") or ""),
                "xpos": str(child.get("xpos", "") or ""),
                "deprel": str(child.get("deprel", "") or ""),
                "head": child.get("head"),
                "span": _normalize_span(child.get("dspan") or child.get("span")),
                "surface_slice": surface_slice,
                "surface_slice_text": slice_text,
                "realign_pass": str(child.get("_realign_pass", "") or ""),
            }
        )
    return rows


def _build_raw_trankit_token_rows(doc):
    """Dump every token from the raw Trankit doc, including MWT expanded words."""
    rows = []
    if not isinstance(doc, dict):
        return rows
    for sent_idx, sent in enumerate(doc.get("sentences", [])):
        if not isinstance(sent, dict):
            continue
        for tok in sent.get("tokens", []):
            if not isinstance(tok, dict):
                continue
            tok_id = tok.get("id")
            expanded = tok.get("expanded")
            is_mwt = (isinstance(tok_id, (list, tuple)) and len(tok_id) == 2) or (
                isinstance(expanded, list) and len(expanded) > 0
            )
            if is_mwt:
                display_id = (
                    "{}-{}".format(tok_id[0], tok_id[1])
                    if isinstance(tok_id, (list, tuple)) and len(tok_id) == 2
                    else str(tok_id)
                )
                rows.append(
                    {
                        "sentence_index": sent_idx,
                        "id": display_id,
                        "type": "MWT_PARENT",
                        "text": str(tok.get("text", "") or ""),
                        "head": None,
                        "deprel": None,
                        "upos": None,
                        "span": tok.get("span"),
                        "dspan": tok.get("dspan"),
                    }
                )
                # mwt_expanded_words has heuristic spans assigned by _derive_child_spans;
                # fall back to raw expanded if mwt_expanded_words is not present.
                child_source = tok.get("mwt_expanded_words") or tok.get("expanded") or []
                parent_text_for_slice = str(tok.get("text", "") or "")
                for child in child_source:
                    if not isinstance(child, dict):
                        continue
                    cs = child.get("surface_slice")
                    cs_text = ""
                    if isinstance(cs, (list, tuple)) and len(cs) == 2:
                        try:
                            cs_text = parent_text_for_slice[int(cs[0]) : int(cs[1])]
                        except Exception:
                            cs_text = ""
                    rows.append(
                        {
                            "sentence_index": sent_idx,
                            "id": child.get("id"),
                            "type": "MWT_WORD",
                            "text": str(child.get("text", "") or ""),
                            "upos": str(child.get("upos", "") or ""),
                            "deprel": str(child.get("deprel", "") or ""),
                            "head": child.get("head"),
                            "lemma": str(child.get("lemma", "") or ""),
                            "span": child.get("span"),
                            "dspan": child.get("dspan"),
                            "surface_slice": cs,
                            "surface_slice_text": cs_text,
                            "realign_pass": str(child.get("_realign_pass", "") or ""),
                        }
                    )
            else:
                rows.append(
                    {
                        "sentence_index": sent_idx,
                        "id": tok_id,
                        "type": "WORD",
                        "text": str(tok.get("text", "") or ""),
                        "upos": str(tok.get("upos", "") or ""),
                        "deprel": str(tok.get("deprel", "") or ""),
                        "head": tok.get("head"),
                        "lemma": str(tok.get("lemma", "") or ""),
                    }
                )
    return rows


def _build_trankit_token_rows(doc):
    rows = []
    if not isinstance(doc, dict):
        return rows
    sentences = doc.get("sentences", [])
    if not isinstance(sentences, list):
        return rows
    for sent_idx, sent in enumerate(sentences):
        if not isinstance(sent, dict):
            continue
        tokens = sent.get("tokens", [])
        if not isinstance(tokens, list):
            continue
        for tok_idx, tok in enumerate(tokens):
            if not isinstance(tok, dict):
                continue
            rows.append(
                {
                    "sentence_index": sent_idx,
                    "token_index": tok_idx,
                    "text": str(tok.get("text", "") or ""),
                    "lemma": str(tok.get("lemma", "") or ""),
                    "upos": str(tok.get("upos", "") or ""),
                    "xpos": str(tok.get("xpos", "") or ""),
                    "deprel": str(tok.get("deprel", "") or ""),
                    "head": tok.get("head"),
                    "ner": str(tok.get("ner", "") or ""),
                    "span": _normalize_span(tok.get("dspan") or tok.get("span")),
                    "mwt_expanded_tokens": _extract_mwt_expanded_rows(tok),
                    "mwt_subword_edges": tok.get("mwt_subword_edges"),
                }
            )
    return rows


def _result_row_has_scoring_trace(row):
    if not isinstance(row, dict):
        return False
    return bool(
        isinstance(row.get("_debug_lookup_scoring"), dict)
        or isinstance(row.get("_debug_greedy_main"), dict)
        or isinstance(row.get("_debug_greedy_subwords"), dict)
    )


def _scoring_trace_available(rows):
    return any(_result_row_has_scoring_trace(row) for row in (rows or []))


def _select_effective_debug_results(payload):
    if not isinstance(payload, dict):
        return {
            "results": [],
            "results_by_seg": [],
            "source": "snapshot",
            "trace_available": False,
            "live_trace_available": False,
            "snapshot_trace_available": False,
        }

    snapshot_results = payload.get("results")
    if not isinstance(snapshot_results, list):
        snapshot_results = []
    snapshot_results_by_seg = payload.get("results_by_seg")
    if not isinstance(snapshot_results_by_seg, list):
        snapshot_results_by_seg = []

    live_results = payload.get("debug_ui_results")
    if not isinstance(live_results, list):
        live_results = []
    live_results_by_seg = payload.get("debug_ui_results_by_seg")
    if not isinstance(live_results_by_seg, list):
        live_results_by_seg = []

    live_trace_available = _scoring_trace_available(live_results_by_seg)
    snapshot_trace_available = _scoring_trace_available(snapshot_results_by_seg)

    use_live = False
    if live_results_by_seg:
        if live_trace_available or not snapshot_trace_available:
            use_live = True
    elif live_results and not snapshot_results:
        use_live = True

    effective_results = live_results if use_live else snapshot_results
    effective_results_by_seg = live_results_by_seg if use_live else snapshot_results_by_seg
    if not effective_results and effective_results_by_seg:
        effective_results = effective_results_by_seg[:1]

    return {
        "results": effective_results,
        "results_by_seg": effective_results_by_seg,
        "source": "live_client_capture" if use_live else "snapshot",
        "trace_available": _scoring_trace_available(effective_results_by_seg),
        "live_trace_available": live_trace_available,
        "snapshot_trace_available": snapshot_trace_available,
    }


def _json_safe_copy(value):
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return None


def _sqlite_query_wave_key(query_kind):
    kind = str(query_kind or "").strip().lower()
    if kind == "hydrate_winner_refs":
        return "hydrate_winner_refs"
    if kind in {"hydrate_form_rows", "hydrate_custom_form_rows"}:
        return "hydrate_form_rows"
    if kind == "hydrate_special_forms":
        return "hydrate_special_forms"
    return kind or "other"


def _sqlite_query_wave_label(wave_key):
    key = str(wave_key or "").strip().lower()
    if key == "hydrate_winner_refs":
        return "Wave 1: Hydrate Winners"
    if key == "hydrate_form_rows":
        return "Wave 2: Matched Form Rows"
    if key == "hydrate_special_forms":
        return "Wave 3: Special Forms"
    return key or "Other"


def _group_sqlite_query_waves(trace_payload):
    rows = []
    if isinstance(trace_payload, dict):
        maybe_rows = trace_payload.get("sqlite_queries")
        if isinstance(maybe_rows, list):
            rows = maybe_rows
    grouped = []
    grouped_by_key = {}
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            continue
        wave_key = _sqlite_query_wave_key(raw_row.get("query_kind"))
        bucket = grouped_by_key.get(wave_key)
        if bucket is None:
            bucket = {
                "wave_key": wave_key,
                "label": _sqlite_query_wave_label(wave_key),
                "query_count": 0,
                "total_ms": 0.0,
                "total_rows": 0,
                "queries": [],
            }
            grouped_by_key[wave_key] = bucket
            grouped.append(bucket)
        row_copy = _json_safe_copy(raw_row) if isinstance(raw_row, dict) else None
        if not isinstance(row_copy, dict):
            continue
        bucket["query_count"] += 1
        try:
            bucket["total_ms"] += float(row_copy.get("duration_ms") or 0.0)
        except Exception:
            pass
        try:
            bucket["total_rows"] += int(row_copy.get("row_count") or 0)
        except Exception:
            pass
        bucket["queries"].append(row_copy)
    for bucket in grouped:
        bucket["total_ms"] = round(float(bucket.get("total_ms") or 0.0), 3)
    return grouped


def _winner_ref_uid(ref):
    if not isinstance(ref, dict):
        return ""
    storage_kind = (
        str(ref.get("storage_kind") or ref.get("_storage_kind") or "sqlite").strip().lower()
        or "sqlite"
    )
    db_alias = str(ref.get("db_alias") or ref.get("_storage_db_alias") or "").strip()
    try:
        entry_row_id = int(ref.get("entry_row_id") or ref.get("_storage_row_id") or 0)
    except Exception:
        entry_row_id = 0
    try:
        form_row_id = int(ref.get("form_row_id") or ref.get("_storage_form_row_id") or 0)
    except Exception:
        form_row_id = 0
    if not db_alias or entry_row_id <= 0:
        return ""
    return f"{storage_kind}|{db_alias}|{entry_row_id}" + (
        f"|{form_row_id}" if form_row_id > 0 else ""
    )


def _winner_ref_base_uid(ref):
    if not isinstance(ref, dict):
        return ""
    storage_kind = (
        str(ref.get("storage_kind") or ref.get("_storage_kind") or "sqlite").strip().lower()
        or "sqlite"
    )
    db_alias = str(ref.get("db_alias") or ref.get("_storage_db_alias") or "").strip()
    try:
        entry_row_id = int(ref.get("entry_row_id") or ref.get("_storage_row_id") or 0)
    except Exception:
        entry_row_id = 0
    if not db_alias or entry_row_id <= 0:
        return ""
    return f"{storage_kind}|{db_alias}|{entry_row_id}"


def _safe_positive_int_set(values):
    out = set()
    for raw in list(values or []):
        try:
            value = int(raw)
        except Exception:
            continue
        if value > 0:
            out.add(value)
    return out


def _extract_query_param_ints(query_row):
    params = query_row.get("params") if isinstance(query_row, dict) else []
    ints = set()
    if not isinstance(params, list):
        return ints
    for raw in params:
        try:
            value = int(str(raw))
        except Exception:
            continue
        if value > 0:
            ints.add(value)
    return ints


def _extract_hydrate_query_ref_uids(query_row):
    if not isinstance(query_row, dict):
        return set(), set()
    params = query_row.get("params")
    if not isinstance(params, list) or not params:
        return set(), set()
    first = params[0]
    try:
        refs = json.loads(first)
    except Exception:
        return set(), set()
    if not isinstance(refs, list):
        return set(), set()
    full_uids = set()
    base_uids = set()
    for raw in refs:
        if not isinstance(raw, dict):
            continue
        uid = _winner_ref_uid(raw)
        base_uid = _winner_ref_base_uid(raw)
        if uid:
            full_uids.add(uid)
        if base_uid:
            base_uids.add(base_uid)
    return full_uids, base_uids


def _extract_result_entry_ids(result_row):
    if not isinstance(result_row, dict):
        return []
    out = []
    seen = set()

    def _push(raw_value):
        value = str(raw_value or "").strip()
        if not value or value in seen:
            return
        seen.add(value)
        out.append(value)

    for raw_value in list(result_row.get("entry_ids") or []):
        _push(raw_value)
    fills = list(result_row.get("fills") or result_row.get("dict_fill") or [])
    for fill in fills:
        if not isinstance(fill, dict):
            continue
        for raw_value in list(fill.get("entry_ids") or []):
            _push(raw_value)
    return out


def _extract_result_fill_rows(result_row):
    if not isinstance(result_row, dict):
        return []
    out = []
    seen = set()
    fills = list(result_row.get("fills") or result_row.get("dict_fill") or [])
    for raw_fill in fills:
        if not isinstance(raw_fill, dict):
            continue
        entry_ids = []
        seen_entry_ids = set()
        for raw_entry_id in list(raw_fill.get("entry_ids") or []):
            entry_id = str(raw_entry_id or "").strip()
            if not entry_id or entry_id in seen_entry_ids:
                continue
            seen_entry_ids.add(entry_id)
            entry_ids.append(entry_id)
        row = {
            "text": str(raw_fill.get("text") or "").strip(),
            "head": str(raw_fill.get("head") or "").strip(),
            "source": str(raw_fill.get("source") or "").strip(),
            "entry_ids": entry_ids,
        }
        row_key = (
            row["text"],
            row["head"],
            row["source"],
            tuple(entry_ids),
        )
        if row_key in seen:
            continue
        seen.add(row_key)
        out.append(row)
    return out


def _load_sqlite_payload_artifact(capture_id):
    capture = str(capture_id or "").strip()
    if not capture:
        return {}
    artifact = get_debug_json_artifact(capture, _SQLITE_PAYLOAD_ARTIFACT_SLUG)
    if not isinstance(artifact, dict):
        return {}
    try:
        payload = json.loads(str(artifact.get("text") or ""))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_debug_sense_lines(raw_senses):
    out = []
    seen = set()
    for raw in list(raw_senses or []):
        if isinstance(raw, dict):
            glosses = [
                str(item or "").strip()
                for item in list(raw.get("glosses") or [])
                if str(item or "").strip()
            ]
            text = "; ".join(glosses).strip()
        else:
            text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _extract_debug_form_rows(raw_forms):
    forms = raw_forms if isinstance(raw_forms, dict) else {}
    rows = []
    for raw_row in list(forms.get("rows") or []):
        text = ""
        tags = ""
        roman = ""
        if isinstance(raw_row, dict):
            text = str(
                raw_row.get("display_text") or raw_row.get("form_text") or raw_row.get("text") or ""
            ).strip()
            tags = str(raw_row.get("tags") or raw_row.get("morph_tags") or "").strip()
            roman = str(
                raw_row.get("form_roman")
                or raw_row.get("romanization")
                or raw_row.get("roman")
                or ""
            ).strip()
        elif isinstance(raw_row, (list, tuple)):
            if len(raw_row) > 0:
                text = str(raw_row[0] or "").strip()
            if len(raw_row) > 1:
                tags = str(raw_row[1] or "").strip()
            if len(raw_row) > 2:
                roman = str(raw_row[2] or "").strip()
        if text or tags or roman:
            rows.append({"text": text, "tags": tags, "roman": roman})
    return rows


def _extract_debug_text_value(raw_value):
    if isinstance(raw_value, str):
        return raw_value.strip()
    if isinstance(raw_value, list):
        parts = [str(item or "").strip() for item in raw_value if str(item or "").strip()]
        return " | ".join(parts)
    return ""


def _build_debug_entry_view(entry_key, entry):
    row = entry if isinstance(entry, dict) else {}
    forms = row.get("forms") if isinstance(row.get("forms"), dict) else {}
    raw_morph_info = row.get("morph_info")
    if isinstance(raw_morph_info, list):
        morph_info = [str(item or "").strip() for item in raw_morph_info if str(item or "").strip()]
    else:
        morph_text = str(raw_morph_info or "").strip()
        morph_info = [morph_text] if morph_text else []
    return {
        "entry_key": str(entry_key or "").strip(),
        "runtime_entry_id": str(
            row.get("runtime_entry_id") or row.get("entry_id") or entry_key or ""
        ).strip(),
        "display_headword": str(row.get("display_headword") or row.get("headword") or "").strip(),
        "display_reading": str(
            row.get("display_reading") or row.get("reading") or row.get("roman") or ""
        ).strip(),
        "lemma_headword": str(row.get("lemma_headword") or row.get("headword") or "").strip(),
        "source": str(row.get("source") or row.get("_source") or "").strip(),
        "pos": str(row.get("pos") or row.get("pos_raw") or "").strip(),
        "pos_raw": str(row.get("pos_raw") or row.get("pos") or "").strip(),
        "commentary": _extract_debug_text_value(row.get("commentary")),
        "lemma": str(row.get("lemma") or row.get("_lemma") or "").strip(),
        "morph_base": str(row.get("morph_base") or "").strip(),
        "morph_info": morph_info,
        "grammar": _extract_debug_text_value(row.get("grammar")),
        "etymology": _extract_debug_text_value(row.get("etymology")),
        "note": _extract_debug_text_value(row.get("note")),
        "senses": _extract_debug_sense_lines(row.get("senses_full") or row.get("senses") or []),
        "forms": {
            "rows": _extract_debug_form_rows(forms),
            "kanji": [
                str(v or "").strip() for v in list(forms.get("kanji") or []) if str(v or "").strip()
            ],
            "readings": [
                str(v or "").strip()
                for v in list(forms.get("readings") or [])
                if str(v or "").strip()
            ],
            "alt": [
                str(v or "").strip() for v in list(forms.get("alt") or []) if str(v or "").strip()
            ],
            "hanja": [
                str(v or "").strip() for v in list(forms.get("hanja") or []) if str(v or "").strip()
            ],
            "hangeul": [
                str(v or "").strip()
                for v in list(forms.get("hangeul") or [])
                if str(v or "").strip()
            ],
            "cjk": [
                str(v or "").strip() for v in list(forms.get("cjk") or []) if str(v or "").strip()
            ],
        },
        "match_kind": str(row.get("match_kind") or row.get("_match_kind") or "").strip().lower(),
        "is_alternate_match": bool(row.get("is_alternate_match")),
        "storage_kind": str(row.get("_storage_kind") or "").strip().lower(),
        "storage_db_alias": str(row.get("_storage_db_alias") or "").strip(),
        "storage_row_id": int(row.get("_storage_row_id") or 0),
    }


def _build_token_sqlite_query_waves(token_trace, grouped_waves):
    token_ref_uids = set(str(v) for v in list(token_trace.get("deduped_ref_uids") or []) if str(v))
    token_base_uids = set(
        str(v) for v in list(token_trace.get("deduped_base_uids") or []) if str(v)
    )
    token_entry_ids = _safe_positive_int_set(token_trace.get("entry_row_ids") or [])
    token_form_ids = _safe_positive_int_set(token_trace.get("form_row_ids") or [])
    out = []
    for wave in list(grouped_waves or []):
        if not isinstance(wave, dict):
            continue
        matched_queries = []
        for query in list(wave.get("queries") or []):
            if not isinstance(query, dict):
                continue
            wave_key = str(wave.get("wave_key") or "").strip().lower()
            is_match = False
            if wave_key == "hydrate_winner_refs":
                query_ref_uids, query_base_uids = _extract_hydrate_query_ref_uids(query)
                is_match = bool(
                    (token_ref_uids and query_ref_uids.intersection(token_ref_uids))
                    or (token_base_uids and query_base_uids.intersection(token_base_uids))
                )
            elif wave_key == "hydrate_form_rows":
                is_match = bool(token_form_ids.intersection(_extract_query_param_ints(query)))
            elif wave_key == "hydrate_special_forms":
                is_match = bool(token_entry_ids.intersection(_extract_query_param_ints(query)))
            else:
                is_match = False
            if is_match:
                matched_queries.append(_json_safe_copy(query))
        if not matched_queries:
            continue
        total_ms = 0.0
        total_rows = 0
        for row in matched_queries:
            try:
                total_ms += float(row.get("duration_ms") or 0.0)
            except Exception:
                pass
            try:
                total_rows += int(row.get("row_count") or 0)
            except Exception:
                pass
        out.append(
            {
                "wave_key": str(wave.get("wave_key") or ""),
                "label": str(wave.get("label") or ""),
                "query_count": len(matched_queries),
                "total_ms": round(total_ms, 3),
                "total_rows": total_rows,
                "queries": matched_queries,
            }
        )
    return out


def _build_debug_overlay_view(overlay):
    row = overlay if isinstance(overlay, dict) else {}
    matched_form = row.get("matched_form") if isinstance(row.get("matched_form"), dict) else {}
    return {
        "display_headword": str(row.get("display_headword") or "").strip(),
        "display_reading": str(row.get("display_reading") or "").strip(),
        "match_kind": str(row.get("match_kind") or row.get("_match_kind") or "").strip().lower(),
        "morph_info": [
            str(v or "").strip() for v in list(row.get("morph_info") or []) if str(v or "").strip()
        ],
        "morph_base": str(row.get("morph_base") or "").strip(),
        "is_alternate_match": bool(row.get("is_alternate_match")),
        "matched_form": {
            "text": str(
                matched_form.get("display_text") or matched_form.get("form_text") or ""
            ).strip(),
            "tags": str(matched_form.get("tags") or "").strip(),
            "roman": str(matched_form.get("form_roman") or "").strip(),
        }
        if matched_form
        else {},
    }


def _build_token_hydrated_entries(token_trace, hydrate_payload):
    token = token_trace if isinstance(token_trace, dict) else {}
    payload = hydrate_payload if isinstance(hydrate_payload, dict) else {}
    entry_store = payload.get("entry_store") if isinstance(payload.get("entry_store"), dict) else {}
    ref_to_key = payload.get("ref_to_key") if isinstance(payload.get("ref_to_key"), dict) else {}
    form_overlays = (
        payload.get("form_overlays") if isinstance(payload.get("form_overlays"), dict) else {}
    )
    buckets = {}
    order = []

    def _ensure_bucket(entry_key):
        key = str(entry_key or "").strip()
        if not key:
            return None
        bucket = buckets.get(key)
        if isinstance(bucket, dict):
            return bucket
        raw_entry = entry_store.get(key)
        bucket = {
            "entry": _build_debug_entry_view(key, raw_entry),
            "requested_match_kinds": set(),
            "requested_match_keys": set(),
            "requested_form_row_ids": set(),
            "overlays": [],
            "norm_kind_ids": set(),  # rule IDs that fired (changed the text)
            "norm_kind_details": [],  # list of {id, label, before, after} (order-preserved, deduped by id)
        }
        buckets[key] = bucket
        order.append(key)
        return bucket

    for raw_ref in list(token.get("winner_refs_after_dedupe") or []):
        if not isinstance(raw_ref, dict):
            continue
        wire_key = _winner_ref_uid(raw_ref)
        base_key = _winner_ref_base_uid(raw_ref)
        entry_key = str(
            ref_to_key.get(wire_key) or ref_to_key.get(base_key) or base_key or ""
        ).strip()
        if not entry_key:
            continue
        bucket = _ensure_bucket(entry_key)
        if not isinstance(bucket, dict):
            continue
        match_kind = str(raw_ref.get("match_kind") or "").strip().lower()
        if match_kind:
            bucket["requested_match_kinds"].add(match_kind)
        match_key = str(raw_ref.get("match_key") or "").strip()
        if match_key:
            bucket["requested_match_keys"].add(match_key)
        try:
            form_row_id = int(raw_ref.get("form_row_id") or 0)
        except Exception:
            form_row_id = 0
        if form_row_id > 0:
            bucket["requested_form_row_ids"].add(form_row_id)
        overlay = form_overlays.get(wire_key)
        if isinstance(overlay, dict):
            overlay_view = _build_debug_overlay_view(overlay)
            if overlay_view not in bucket["overlays"]:
                bucket["overlays"].append(overlay_view)
        for norm_item in list(raw_ref.get("_norm_kinds") or []):
            if not isinstance(norm_item, dict):
                continue
            nid = str(norm_item.get("id") or "").strip()
            if not nid:
                continue
            if nid not in bucket["norm_kind_ids"]:
                bucket["norm_kind_ids"].add(nid)
                bucket["norm_kind_details"].append(
                    {
                        "id": nid,
                        "label": str(norm_item.get("label") or nid).strip(),
                        "before": str(norm_item.get("before") or ""),
                        "after": str(norm_item.get("after") or ""),
                    }
                )

    for entry_id in list(token.get("result_entry_ids") or []):
        entry_key = str(entry_id or "").strip()
        if entry_key and entry_key in entry_store:
            _ensure_bucket(entry_key)

    out = []
    special_tags = ("hanja", "hangeul", "cjk", "sinitic", "hán-nôm", "han-nom", "hannom")
    for entry_key in order:
        bucket = buckets.get(entry_key)
        if not isinstance(bucket, dict):
            continue
        entry_view = bucket.get("entry") if isinstance(bucket.get("entry"), dict) else {}
        form_rows = (
            list(((entry_view.get("forms") or {}).get("rows") or []))
            if isinstance(entry_view, dict)
            else []
        )
        lemma_headword = (
            str(entry_view.get("lemma_headword") or entry_view.get("display_headword") or "")
            .strip()
            .lower()
        )
        special_rows = []
        same_headword_rows = []
        for row in form_rows:
            if not isinstance(row, dict):
                continue
            text = str(row.get("text") or "").strip()
            tags = str(row.get("tags") or "").strip()
            lower_text = text.lower()
            lower_tags = tags.lower()
            if lemma_headword and lower_text and lower_text == lemma_headword:
                same_headword_rows.append(_json_safe_copy(row))
            if any(tag in lower_tags for tag in special_tags):
                special_rows.append(_json_safe_copy(row))
        out.append(
            {
                "entry": entry_view,
                "metadata": {
                    "requested_match_kinds": sorted(bucket["requested_match_kinds"]),
                    "requested_match_keys": sorted(bucket["requested_match_keys"]),
                    "requested_form_row_ids": sorted(bucket["requested_form_row_ids"]),
                    "form_overlays": _json_safe_copy(bucket["overlays"]),
                    "form_row_count": len(form_rows),
                    "special_form_rows": special_rows,
                    "same_headword_form_rows": same_headword_rows,
                    "norm_kinds": _json_safe_copy(bucket["norm_kind_details"]),
                },
            }
        )
    return out


def _summarize_wave_stats(waves):
    out = []
    for raw_wave in list(waves or []):
        if not isinstance(raw_wave, dict):
            continue
        out.append(
            {
                "wave_key": str(raw_wave.get("wave_key") or "").strip().lower(),
                "label": str(raw_wave.get("label") or raw_wave.get("wave_key") or "").strip(),
                "query_count": int(raw_wave.get("query_count") or 0),
                "total_ms": round(float(raw_wave.get("total_ms") or 0.0), 3),
                "total_rows": int(raw_wave.get("total_rows") or 0),
            }
        )
    return out


def _build_fill_traces(token_trace):
    token = token_trace if isinstance(token_trace, dict) else {}
    hydrated_entries = list(token.get("hydrated_entries") or [])
    entry_map = {}
    for item in hydrated_entries:
        if not isinstance(item, dict):
            continue
        entry = item.get("entry") if isinstance(item.get("entry"), dict) else {}
        entry_key = str(entry.get("entry_key") or "").strip()
        if entry_key:
            entry_map[entry_key] = _json_safe_copy(item)

    fill_rows = list(token.get("fills") or [])
    if not fill_rows and token.get("result_entry_ids"):
        fill_rows = [
            {
                "text": str(token.get("segment_text") or "").strip(),
                "head": str(((token.get("result_summary") or {}).get("head") or "")).strip(),
                "source": str(((token.get("result_summary") or {}).get("source") or "")).strip(),
                "entry_ids": [
                    str(v or "").strip()
                    for v in list(token.get("result_entry_ids") or [])
                    if str(v or "").strip()
                ],
            }
        ]

    out = []
    consumed_entry_ids = set()
    for raw_fill in fill_rows:
        if not isinstance(raw_fill, dict):
            continue
        fill_entry_ids = []
        fill_entries = []
        for raw_entry_id in list(raw_fill.get("entry_ids") or []):
            entry_id = str(raw_entry_id or "").strip()
            if not entry_id:
                continue
            fill_entry_ids.append(entry_id)
            consumed_entry_ids.add(entry_id)
            entry_item = entry_map.get(entry_id)
            if isinstance(entry_item, dict):
                fill_entries.append(_json_safe_copy(entry_item))
        # Skip fills that resolved no entries — these are artifacts of a
        # ref-key mismatch between the JS fill's _winner_ref and the hydrate
        # payload's ref_to_key map.  The entries will surface correctly via the
        # unattached_entries fallback below.
        if not fill_entries:
            continue

        match_kinds = set()
        special_rows = 0
        same_headword_rows = 0
        overlay_count = 0
        fill_norm_kinds_seen = set()
        fill_norm_kinds = []
        for entry_item in fill_entries:
            meta = (
                entry_item.get("metadata") if isinstance(entry_item.get("metadata"), dict) else {}
            )
            match_kinds.update(
                str(v or "").strip()
                for v in list(meta.get("requested_match_kinds") or [])
                if str(v or "").strip()
            )
            special_rows += len(list(meta.get("special_form_rows") or []))
            same_headword_rows += len(list(meta.get("same_headword_form_rows") or []))
            overlay_count += len(list(meta.get("form_overlays") or []))
            for nk in list(meta.get("norm_kinds") or []):
                if not isinstance(nk, dict):
                    continue
                nid = str(nk.get("id") or "").strip()
                if nid and nid not in fill_norm_kinds_seen:
                    fill_norm_kinds_seen.add(nid)
                    fill_norm_kinds.append(_json_safe_copy(nk))

        out.append(
            {
                "fill_text": str(raw_fill.get("text") or "").strip(),
                "fill_head": str(raw_fill.get("head") or "").strip(),
                "fill_source": str(raw_fill.get("source") or "").strip(),
                "entry_ids": fill_entry_ids,
                "analysis": {
                    "entry_count": len(fill_entries),
                    "match_kinds": sorted(v for v in match_kinds if v),
                    "special_form_row_count": special_rows,
                    "same_headword_form_row_count": same_headword_rows,
                    "matched_form_overlay_count": overlay_count,
                    "norm_kinds": fill_norm_kinds,
                    "was_normalized": bool(fill_norm_kinds),
                },
                "entries": fill_entries,
            }
        )

    unfilled_entries = []
    for entry_item in hydrated_entries:
        if not isinstance(entry_item, dict):
            continue
        entry = entry_item.get("entry") if isinstance(entry_item.get("entry"), dict) else {}
        entry_key = str(entry.get("entry_key") or "").strip()
        if entry_key and entry_key not in consumed_entry_ids:
            unfilled_entries.append(_json_safe_copy(entry_item))
    if unfilled_entries:
        special_rows = 0
        same_headword_rows = 0
        overlay_count = 0
        match_kinds = set()
        uf_norm_kinds_seen = set()
        uf_norm_kinds = []
        for entry_item in unfilled_entries:
            meta = (
                entry_item.get("metadata") if isinstance(entry_item.get("metadata"), dict) else {}
            )
            match_kinds.update(
                str(v or "").strip()
                for v in list(meta.get("requested_match_kinds") or [])
                if str(v or "").strip()
            )
            special_rows += len(list(meta.get("special_form_rows") or []))
            same_headword_rows += len(list(meta.get("same_headword_form_rows") or []))
            overlay_count += len(list(meta.get("form_overlays") or []))
            for nk in list(meta.get("norm_kinds") or []):
                if not isinstance(nk, dict):
                    continue
                nid = str(nk.get("id") or "").strip()
                if nid and nid not in uf_norm_kinds_seen:
                    uf_norm_kinds_seen.add(nid)
                    uf_norm_kinds.append(_json_safe_copy(nk))
        # When all explicit fills were skipped (empty entry_ids), these entries
        # are the real result — label them with the token's result source instead
        # of "unattached_entries" so they don't look like leftovers.
        fill_source_label = "unattached_entries"
        if not out:
            result_source = str(((token.get("result_summary") or {}).get("source") or "")).strip()
            fill_source_label = result_source if result_source else "entries"
        out.append(
            {
                "fill_text": str(token.get("segment_text") or "").strip(),
                "fill_head": str(((token.get("result_summary") or {}).get("head") or "")).strip(),
                "fill_source": fill_source_label,
                "entry_ids": [
                    str(((item.get("entry") or {}).get("entry_key") or ""))
                    for item in unfilled_entries
                    if isinstance(item, dict)
                ],
                "analysis": {
                    "entry_count": len(unfilled_entries),
                    "match_kinds": sorted(v for v in match_kinds if v),
                    "special_form_row_count": special_rows,
                    "same_headword_form_row_count": same_headword_rows,
                    "matched_form_overlay_count": overlay_count,
                    "norm_kinds": uf_norm_kinds,
                    "was_normalized": bool(uf_norm_kinds),
                },
                "entries": unfilled_entries,
            }
        )
    return out


def _build_token_display_trace(token_trace):
    token = token_trace if isinstance(token_trace, dict) else {}
    fill_traces = _build_fill_traces(token)
    wave_stats = _summarize_wave_stats(token.get("sqlite_query_waves") or [])
    special_rows = 0
    same_headword_rows = 0
    overlay_count = 0
    unique_entry_ids = set()
    for fill in fill_traces:
        if not isinstance(fill, dict):
            continue
        analysis = fill.get("analysis") if isinstance(fill.get("analysis"), dict) else {}
        special_rows += int(analysis.get("special_form_row_count") or 0)
        same_headword_rows += int(analysis.get("same_headword_form_row_count") or 0)
        overlay_count += int(analysis.get("matched_form_overlay_count") or 0)
        for entry_id in list(fill.get("entry_ids") or []):
            entry_text = str(entry_id or "").strip()
            if entry_text:
                unique_entry_ids.add(entry_text)
    total_query_count = 0
    total_query_ms = 0.0
    total_query_rows = 0
    for wave in wave_stats:
        total_query_count += int(wave.get("query_count") or 0)
        total_query_ms += float(wave.get("total_ms") or 0.0)
        total_query_rows += int(wave.get("total_rows") or 0)
    return {
        "segment_index": int(token.get("segment_index") or 0),
        "segment_text": str(token.get("segment_text") or ""),
        "lemma": str(token.get("lemma") or ""),
        "upos": str(token.get("upos") or ""),
        "xpos": str(token.get("xpos") or ""),
        "deprel": str(token.get("deprel") or ""),
        "resolved_via": str(token.get("resolved_via") or ""),
        "fill_mode": str(token.get("fill_mode") or ""),
        "resolution_category": str(token.get("resolution_category") or ""),
        "resolution_route_code": str(token.get("resolution_route_code") or ""),
        "analysis": {
            "raw_winner_ref_count": int(token.get("winner_ref_count_raw") or 0),
            "deduped_winner_ref_count": int(token.get("winner_ref_count_after_dedupe") or 0),
            "fill_count": len(fill_traces),
            "entry_count": len(unique_entry_ids),
            "sqlite_query_count": total_query_count,
            "sqlite_total_ms": round(total_query_ms, 3),
            "sqlite_total_rows": total_query_rows,
            "wave_stats": wave_stats,
            "special_form_row_count": special_rows,
            "same_headword_form_row_count": same_headword_rows,
            "matched_form_overlay_count": overlay_count,
        },
        "fills": fill_traces,
    }


def _build_sqlite_query_analysis(
    snapshot, client_capture, grouped_waves, token_traces, artifact_meta
):
    snap = snapshot if isinstance(snapshot, dict) else {}
    client = client_capture if isinstance(client_capture, dict) else {}
    wave_stats = _summarize_wave_stats(grouped_waves)
    total_query_count = 0
    total_query_ms = 0.0
    total_query_rows = 0
    for wave in wave_stats:
        total_query_count += int(wave.get("query_count") or 0)
        total_query_ms += float(wave.get("total_ms") or 0.0)
        total_query_rows += int(wave.get("total_rows") or 0)
    fill_count = 0
    entry_ids = set()
    special_rows = 0
    same_headword_rows = 0
    for token in list(token_traces or []):
        if not isinstance(token, dict):
            continue
        analysis = token.get("analysis") if isinstance(token.get("analysis"), dict) else {}
        fill_count += int(analysis.get("fill_count") or 0)
        special_rows += int(analysis.get("special_form_row_count") or 0)
        same_headword_rows += int(analysis.get("same_headword_form_row_count") or 0)
        for fill in list(token.get("fills") or []):
            if not isinstance(fill, dict):
                continue
            for entry_id in list(fill.get("entry_ids") or []):
                entry_text = str(entry_id or "").strip()
                if entry_text:
                    entry_ids.add(entry_text)
    return {
        "q": str(snap.get("q") or ""),
        "display_text": str(snap.get("display_text") or ""),
        "language": str(snap.get("language") or "").strip().lower(),
        "segment_count": len(list(token_traces or [])),
        "raw_winner_ref_count": int(client.get("raw_winner_ref_count") or 0),
        "deduped_winner_ref_count": int(client.get("unique_winner_ref_count") or 0),
        "fill_count": fill_count,
        "entry_count": len(entry_ids),
        "sqlite_query_count": total_query_count,
        "sqlite_total_ms": round(total_query_ms, 3),
        "sqlite_total_rows": total_query_rows,
        "wave_stats": wave_stats,
        "special_form_row_count": special_rows,
        "same_headword_form_row_count": same_headword_rows,
        "lookup_path": str(((client.get("lookup_request") or {}).get("path") or "/lookup")),
        "hydrate_path": str(((client.get("hydrate_request") or {}).get("path") or "/js/hydrate")),
        "payload_filename": str(((artifact_meta or {}).get("filename") or "")),
        "payload_size_bytes": int((artifact_meta or {}).get("size_bytes") or 0),
    }


def _build_sqlite_token_traces(snapshot, client_capture, grouped_waves):
    snap = snapshot if isinstance(snapshot, dict) else {}
    client = client_capture if isinstance(client_capture, dict) else {}
    segment_rows = list(client.get("segment_winners") or [])
    dedupe_rows = list(client.get("dedupe_rows") or [])
    results_by_seg = []
    if isinstance(snap.get("debug_ui_results_by_seg"), list) and snap.get(
        "debug_ui_results_by_seg"
    ):
        results_by_seg = list(snap.get("debug_ui_results_by_seg") or [])
    elif isinstance(snap.get("results_by_seg"), list):
        results_by_seg = list(snap.get("results_by_seg") or [])
    traces = []
    for raw_row in segment_rows:
        if not isinstance(raw_row, dict):
            continue
        try:
            seg_idx = int(raw_row.get("segment_index") or 0)
        except Exception:
            seg_idx = 0
        token_dedupe_rows = []
        deduped_refs = []
        deduped_ref_uids = set()
        deduped_base_uids = set()
        entry_row_ids = set()
        form_row_ids = set()
        for raw_dedupe in dedupe_rows:
            if not isinstance(raw_dedupe, dict):
                continue
            segment_indexes = list(raw_dedupe.get("segment_indexes") or [])
            hit = False
            for raw_index in segment_indexes:
                try:
                    if int(raw_index) == seg_idx:
                        hit = True
                        break
                except Exception:
                    continue
            if not hit:
                continue
            token_dedupe_rows.append(_json_safe_copy(raw_dedupe))
            if not raw_dedupe.get("kept_after_dedupe"):
                continue
            ref = raw_dedupe.get("ref")
            if not isinstance(ref, dict):
                continue
            ref_copy = _json_safe_copy(ref)
            if isinstance(ref_copy, dict):
                deduped_refs.append(ref_copy)
                uid = _winner_ref_uid(ref_copy)
                base_uid = _winner_ref_base_uid(ref_copy)
                if uid:
                    deduped_ref_uids.add(uid)
                if base_uid:
                    deduped_base_uids.add(base_uid)
                try:
                    entry_row_id = int(ref_copy.get("entry_row_id") or 0)
                except Exception:
                    entry_row_id = 0
                if entry_row_id > 0:
                    entry_row_ids.add(entry_row_id)
                try:
                    form_row_id = int(ref_copy.get("form_row_id") or 0)
                except Exception:
                    form_row_id = 0
                if form_row_id > 0:
                    form_row_ids.add(form_row_id)
        result_row = (
            results_by_seg[seg_idx]
            if seg_idx < len(results_by_seg) and isinstance(results_by_seg[seg_idx], dict)
            else {}
        )
        trace = {
            "segment_index": seg_idx,
            "segment_text": str(raw_row.get("segment_text") or ""),
            "lemma": str(raw_row.get("lemma") or ""),
            "upos": str(raw_row.get("upos") or ""),
            "xpos": str(raw_row.get("xpos") or ""),
            "deprel": str(raw_row.get("deprel") or ""),
            "resolved_via": str(raw_row.get("resolved_via") or ""),
            "fill_mode": str(raw_row.get("fill_mode") or ""),
            "resolution_category": str(raw_row.get("resolution_category") or ""),
            "resolution_route_code": str(raw_row.get("resolution_route_code") or ""),
            "winner_refs_raw": _json_safe_copy(raw_row.get("winner_refs") or []),
            "winner_ref_count_raw": int(raw_row.get("winner_ref_count") or 0),
            "token_dedupe_rows": token_dedupe_rows,
            "winner_refs_after_dedupe": deduped_refs,
            "winner_ref_count_after_dedupe": len(deduped_refs),
            "deduped_ref_uids": sorted(deduped_ref_uids),
            "deduped_base_uids": sorted(deduped_base_uids),
            "entry_row_ids": sorted(entry_row_ids),
            "form_row_ids": sorted(form_row_ids),
            "hydrate_request": {
                "method": "POST",
                "path": "/js/hydrate",
                "payload": {
                    "lang": str(client.get("language") or snap.get("language") or "")
                    .strip()
                    .lower(),
                    "winner_refs": deduped_refs,
                },
            },
            "result_entry_ids": _extract_result_entry_ids(result_row),
            "fills": _extract_result_fill_rows(result_row),
            "result_summary": {
                "source": str(result_row.get("source") or ""),
                "head": str(result_row.get("head") or result_row.get("text") or ""),
                "lemma": str(result_row.get("lemma") or result_row.get("lemma_form") or ""),
                "entry_ids": _extract_result_entry_ids(result_row),
            },
        }
        trace["sqlite_query_waves"] = _build_token_sqlite_query_waves(trace, grouped_waves)
        trace.pop("deduped_ref_uids", None)
        trace.pop("deduped_base_uids", None)
        traces.append(trace)
    return traces


def _build_sqlite_download_url(capture_id):
    capture = str(capture_id or "").strip()
    if not capture:
        return ""
    return f"/debug/sqlite/download?capture_id={capture}"


def _build_sqlite_debug_payload(snapshot):
    snap = snapshot if isinstance(snapshot, dict) else {}
    capture_id = str(snap.get("debug_capture_id") or "").strip()
    trace_payload = (
        _json_safe_copy(snap.get("sqlite_debug_trace"))
        if isinstance(snap.get("sqlite_debug_trace"), dict)
        else {}
    )
    if not isinstance(trace_payload, dict):
        trace_payload = {}
    trace_payload.pop("final_payload", None)
    client_capture = (
        _json_safe_copy(snap.get("debug_ui_sqlite_capture"))
        if isinstance(snap.get("debug_ui_sqlite_capture"), dict)
        else {}
    )
    if not isinstance(client_capture, dict):
        client_capture = {}
    grouped_waves = _group_sqlite_query_waves(trace_payload)
    token_traces = _build_sqlite_token_traces(snap, client_capture, grouped_waves)
    hydrate_payload = _load_sqlite_payload_artifact(capture_id)
    if hydrate_payload:
        for token_trace in token_traces:
            if not isinstance(token_trace, dict):
                continue
            token_trace["hydrated_entries"] = _build_token_hydrated_entries(
                token_trace, hydrate_payload
            )
    artifact_meta = (
        get_debug_json_artifact_meta(capture_id, _SQLITE_PAYLOAD_ARTIFACT_SLUG)
        if capture_id
        else None
    )
    if not isinstance(artifact_meta, dict) and isinstance(
        trace_payload.get("final_payload_artifact"), dict
    ):
        artifact_meta = _json_safe_copy(trace_payload.get("final_payload_artifact"))
    if isinstance(artifact_meta, dict):
        artifact_meta["download_url"] = _build_sqlite_download_url(capture_id)
    display_tokens = [
        _build_token_display_trace(token_trace)
        for token_trace in token_traces
        if isinstance(token_trace, dict)
    ]
    query_analysis = _build_sqlite_query_analysis(
        snap, client_capture, grouped_waves, display_tokens, artifact_meta
    )
    return {
        "ok": True,
        "debug_capture_id": capture_id,
        "query_analysis": query_analysis,
        "token_traces": display_tokens,
        "token_trace_count": len(display_tokens),
        "payload_download": artifact_meta if isinstance(artifact_meta, dict) else None,
        "captured_at": snap.get("_timestamp"),
    }


@debug_bp.route("/debug/data")
def debug_data():
    if not is_debug_collection_enabled():
        return jsonify(
            {
                "ok": False,
                "error": "Debug collection is disabled (DEBUG_COLLECTION_ENABLED=False in debug_store.py).",
            }
        )
    snap = get_debug_snapshot()
    if snap is None:
        return jsonify(
            {"ok": False, "error": "No lookup yet. Run a lookup in the main window first."}
        )
    # Make a JSON-safe copy (Trankit doc can have odd types)
    try:
        safe = json.loads(json.dumps(snap, ensure_ascii=False, default=str))
    except Exception as e:
        return jsonify({"ok": False, "error": f"Serialization error: {e}"})
    allowed = {
        "_timestamp",
        "debug_capture_id",
        "language",
        "q",
        "display_text",
        "original_text",
        "normalized_text",
        "filtered_text",
        "preprocess_changed",
        "preprocess_language",
        "preprocess_normalization_form",
        "normalization_change_rows",
        "raw_trankit_doc",
        "pipeline_trankit_doc",
        "mwt_meta",
        "trankit_doc",
        "trankit_tokens",
        "segments",
        "segment_offsets",
        "results",
        "results_by_seg",
        "ud_overlay",
        "grammar_overlay",
        "normalized_segment_remaps",
        "segment_original_discrepancies",
        "dictionary_decision_trace",
        "korean_dictionary_trace",
        "japanese_dictionary_trace",
        "sqlite_debug_trace",
        "debug_ui_results",
        "debug_ui_results_by_seg",
        "debug_ui_capture_mode",
        "debug_ui_dict_source",
        "debug_ui_dict_meta",
        "debug_ui_lookup_timing",
        "debug_ui_render_trace",
    }
    trimmed = {k: v for k, v in safe.items() if k in allowed}
    if isinstance(trimmed.get("sqlite_debug_trace"), dict):
        trimmed["sqlite_debug_trace"].pop("final_payload", None)
    preferred_doc = trimmed.get("pipeline_trankit_doc") or trimmed.get("raw_trankit_doc")
    trimmed["trankit_doc"] = preferred_doc
    trimmed["trankit_tokens"] = _build_trankit_token_rows(preferred_doc)
    try:
        raw_doc = trimmed.get("raw_trankit_doc")
        if raw_doc and raw_doc is not preferred_doc:
            trimmed["raw_trankit_tokens"] = _build_raw_trankit_token_rows(raw_doc)
        else:
            trimmed["raw_trankit_tokens"] = []
    except Exception:
        trimmed["raw_trankit_tokens"] = []
    trimmed["snapshot_results"] = (
        list(trimmed.get("results") or []) if isinstance(trimmed.get("results"), list) else []
    )
    trimmed["snapshot_results_by_seg"] = (
        list(trimmed.get("results_by_seg") or [])
        if isinstance(trimmed.get("results_by_seg"), list)
        else []
    )
    effective = _select_effective_debug_results(trimmed)
    trimmed["results"] = effective["results"]
    trimmed["results_by_seg"] = effective["results_by_seg"]
    trimmed["debug_effective_results"] = effective["results"]
    trimmed["debug_effective_results_by_seg"] = effective["results_by_seg"]
    trimmed["debug_scoring_source"] = effective["source"]
    trimmed["debug_scoring_available"] = effective["trace_available"]
    trimmed["debug_live_scoring_available"] = effective["live_trace_available"]
    trimmed["debug_snapshot_scoring_available"] = effective["snapshot_trace_available"]
    trimmed["ok"] = True
    return jsonify(trimmed)


@debug_bp.route("/debug/sqlite/data")
def debug_sqlite_data():
    if not is_debug_collection_enabled():
        return jsonify(
            {
                "ok": False,
                "error": "Debug collection is disabled (DEBUG_COLLECTION_ENABLED=False in debug_store.py).",
            }
        )
    snap = get_debug_snapshot()
    if not isinstance(snap, dict):
        return jsonify(
            {"ok": False, "error": "No lookup yet. Run a lookup in the main window first."}
        )
    capture_id = str(snap.get("debug_capture_id") or "").strip()
    if not capture_id:
        return jsonify(
            {
                "ok": False,
                "error": "No active debug capture. Turn on Debug capture and run a fresh lookup.",
            }
        )
    payload = _build_sqlite_debug_payload(snap)
    if not payload.get("query_analysis") and not payload.get("token_traces"):
        return jsonify(
            {"ok": False, "error": "No SQLite capture is available for the current lookup."}
        )
    return jsonify(payload)


@debug_bp.route("/debug/sqlite/download")
def debug_sqlite_download():
    if not is_debug_collection_enabled():
        return jsonify({"ok": False, "error": "Debug collection disabled."}), 503
    capture_id = str(request.args.get("capture_id") or "").strip()
    if not capture_id:
        snap = get_debug_snapshot()
        if isinstance(snap, dict):
            capture_id = str(snap.get("debug_capture_id") or "").strip()
    if not capture_id:
        return jsonify({"ok": False, "error": "Missing capture id."}), 400
    artifact = get_debug_json_artifact(capture_id, _SQLITE_PAYLOAD_ARTIFACT_SLUG)
    if not isinstance(artifact, dict):
        return jsonify(
            {"ok": False, "error": "No SQLite payload artifact is available for this capture."}
        ), 404
    meta = artifact.get("meta") if isinstance(artifact.get("meta"), dict) else {}
    body = str(artifact.get("text") or "")
    filename = str(meta.get("filename") or f"{capture_id}-{_SQLITE_PAYLOAD_ARTIFACT_SLUG}.json")
    response = Response(body, mimetype="application/json")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Cache-Control"] = "no-store"
    return response


@debug_bp.route("/debug/live_lookup_capture", methods=["POST"])
def debug_live_lookup_capture():
    if not is_debug_collection_enabled():
        return jsonify({"ok": False, "error": "Debug collection disabled."}), 503

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Expected JSON object."}), 400

    capture_id = str(payload.get("debug_capture_id", "") or "").strip()
    if not capture_id:
        return jsonify({"ok": False, "error": "Missing debug_capture_id."}), 400

    snap = get_debug_snapshot()
    if not isinstance(snap, dict):
        return jsonify({"ok": False, "error": "No snapshot to attach live results to."}), 409

    current_capture_id = str(snap.get("debug_capture_id", "") or "").strip()
    if not current_capture_id or current_capture_id != capture_id:
        return jsonify({"ok": False, "error": "Stale debug capture id."}), 409

    patch = {}

    capture_mode = str(payload.get("debug_ui_capture_mode", "") or "").strip()
    if capture_mode:
        patch["debug_ui_capture_mode"] = capture_mode

    dict_source = str(payload.get("debug_ui_dict_source", "") or "").strip()
    if dict_source:
        patch["debug_ui_dict_source"] = dict_source

    results_by_seg = payload.get("debug_ui_results_by_seg")
    if isinstance(results_by_seg, list):
        patch["debug_ui_results_by_seg"] = results_by_seg

    results = payload.get("debug_ui_results")
    if isinstance(results, list):
        patch["debug_ui_results"] = results

    dict_meta = payload.get("debug_ui_dict_meta")
    if isinstance(dict_meta, dict):
        patch["debug_ui_dict_meta"] = dict_meta

    lookup_timing = payload.get("debug_ui_lookup_timing")
    if isinstance(lookup_timing, dict):
        patch["debug_ui_lookup_timing"] = lookup_timing

    render_trace = payload.get("debug_ui_render_trace")
    if isinstance(render_trace, dict):
        patch["debug_ui_render_trace"] = render_trace

    sqlite_capture = payload.get("debug_ui_sqlite_capture")
    if isinstance(sqlite_capture, dict):
        patch["debug_ui_sqlite_capture"] = sqlite_capture

    update_debug_snapshot(patch)
    return jsonify({"ok": True})


def _call_fill_token_with_debug(
    dictionary,
    word: str,
    allow_exact: bool,
    upos: str,
    debug: bool,
):
    attempts = []
    if debug:
        attempts.append(
            {
                "allow_exact": allow_exact,
                "exclude_whole": False,
                "upos": upos,
                "debug": True,
            }
        )
    attempts.append(
        {
            "allow_exact": allow_exact,
            "exclude_whole": False,
            "upos": upos,
        }
    )
    attempts.append(
        {
            "allow_exact": allow_exact,
            "exclude_whole": False,
        }
    )
    for kwargs in attempts:
        try:
            return dictionary.fill_token(word, **kwargs)
        except TypeError:
            continue
    return dictionary.fill_token(word)


@debug_bp.route("/debug/greedy_score")
def debug_greedy_score():
    token = str(request.args.get("q", "") or "").strip()
    raw_lang = str(request.args.get("lang", "vi") or "").strip().lower()
    upos = str(request.args.get("upos", "") or "").strip().upper()

    if not token:
        return jsonify({"ok": False, "error": "empty token"}), 400

    from language_registry import resolve_lang_code
    from router import _resolve_dictionary

    lang_code = resolve_lang_code(raw_lang)
    if not lang_code:
        return jsonify({"ok": False, "error": f"Unsupported language: {raw_lang}"}), 400

    dictionary = _resolve_dictionary(lang_code)
    if dictionary is None:
        return jsonify({"ok": False, "error": f"Dictionary not loaded: {lang_code}"}), 500

    try:
        exact_entries = list(dictionary.lookup_all(token) or [])
    except Exception as exc:
        return jsonify(
            {"ok": False, "error": f"lookup_all failed: {type(exc).__name__}: {exc}"}
        ), 500

    try:
        greedy_result = _call_fill_token_with_debug(
            dictionary=dictionary,
            word=token,
            allow_exact=False,
            upos=upos,
            debug=True,
        )
    except Exception as exc:
        return jsonify(
            {"ok": False, "error": f"fill_token failed: {type(exc).__name__}: {exc}"}
        ), 500

    if not isinstance(greedy_result, dict):
        greedy_result = {
            "mode": "greedy",
            "fills": [],
            "has_known": False,
            "has_unknown": True,
        }

    top_head = ""
    top_pos = ""
    if exact_entries:
        top = exact_entries[0] if isinstance(exact_entries[0], dict) else {}
        top_head = str(
            top.get("headword", "") or top.get("word", "") or top.get("head", "") or token
        )
        top_pos = str(top.get("pos_raw", "") or top.get("pos", "") or "")

    fill_preview = []
    for i, piece in enumerate(list(greedy_result.get("fills", []) or [])):
        if not isinstance(piece, dict):
            continue
        senses = list(piece.get("senses", []) or [])
        fill_preview.append(
            {
                "index": i,
                "text": str(piece.get("text", "") or ""),
                "head": str(piece.get("head", "") or ""),
                "source": str(piece.get("source", "") or ""),
                "pos": str(piece.get("pos", "") or ""),
                "xpos_hint": str(piece.get("_xpos_hint", "") or piece.get("xpos_hint", "") or ""),
                "lemma_upos_hint": str(
                    piece.get("_lemma_upos_hint", "") or piece.get("lemma_upos_hint", "") or ""
                ),
                "lemma_xpos_hint": str(
                    piece.get("_lemma_xpos_hint", "") or piece.get("lemma_xpos_hint", "") or ""
                ),
                "effective_upos": str(
                    (
                        (piece.get("_debug_trace") or {})
                        if isinstance(piece.get("_debug_trace"), dict)
                        else {}
                    ).get("effective_upos", "")
                    or ""
                ),
                "effective_xpos": str(
                    (
                        (piece.get("_debug_trace") or {})
                        if isinstance(piece.get("_debug_trace"), dict)
                        else {}
                    ).get("effective_xpos", "")
                    or ""
                ),
                "lemma_promoted": str(
                    piece.get("_lemma_promoted", "") or piece.get("lemma_promoted", "") or ""
                ),
                "sense_count": len(senses),
            }
        )

    score_breakdown = greedy_result.get("dp_debug")
    debug_supported = bool(isinstance(score_breakdown, dict) and score_breakdown.get("steps"))
    note = ""
    if not debug_supported:
        note = (
            "Detailed DP scores are unavailable for this dictionary implementation "
            "(no dp_debug payload)."
        )

    return jsonify(
        {
            "ok": True,
            "language": lang_code,
            "q": token,
            "upos": upos,
            "exact_match": {
                "found": bool(exact_entries),
                "count": len(exact_entries),
                "top_head": top_head,
                "top_pos": top_pos,
            },
            "greedy_result": greedy_result,
            "fill_preview": fill_preview,
            "score_breakdown": score_breakdown if isinstance(score_breakdown, dict) else None,
            "debug_supported": debug_supported,
            "note": note,
        }
    )


# ---------------------------------------------------------------------------
# Inline HTML â€” self-contained, no template file needed
# ---------------------------------------------------------------------------

_DEBUG_KOREAN_LEMMA_BOUNDARIES_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Lemma Boundaries Debug</title>
<style>
  :root { --bg: #1e1e2e; --fg: #cdd6f4; --surface: #313244; --border: #45475a;
          --accent: #89b4fa; --green: #a6e3a1; --red: #f38ba8; --yellow: #f9e2af;
          --peach: #fab387; --cyan: #89dceb; --mono: 'Cascadia Code', 'Fira Code', 'Consolas', monospace; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: var(--mono); font-size: 13px; background: var(--bg); color: var(--fg);
         padding: 16px; line-height: 1.6; }
  h1 { font-size: 16px; color: var(--accent); margin-bottom: 12px; display: flex;
       align-items: center; gap: 10px; }
  h1 .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--red); }
  h1 .dot.live { background: var(--green); }
  .meta { font-size: 11px; color: #6c7086; }
  .refresh-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
  .btn { background: var(--surface); color: var(--fg); border: 1px solid var(--border);
         padding: 4px 12px; border-radius: 4px; font-size: 12px; cursor: pointer;
         font-family: var(--mono); text-decoration: none; }
  .btn:hover { background: #3b3d52; }
  .btn.active { background: var(--accent); color: var(--bg); border-color: var(--accent); }
  .note { margin-bottom: 16px; padding: 10px 12px; background: #181825; border: 1px solid var(--border);
          border-radius: 6px; color: #a6adc8; }
  .empty { text-align: center; padding: 40px; color: #6c7086; border: 1px solid var(--border);
           border-radius: 6px; background: #181825; }
  .section { border: 1px solid var(--border); border-radius: 6px; overflow: hidden; background: #181825; }
  .section-head { background: var(--surface); padding: 10px 12px; font-weight: bold; font-size: 13px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; padding: 6px 8px; background: #181825; color: #a6adc8;
       font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
       position: sticky; top: 0; z-index: 1; }
  td { padding: 6px 8px; border-top: 1px solid var(--border); vertical-align: top; }
  tr:hover td { background: #2a2b3d; }
  .tok-text { font-size: 16px; font-weight: bold; }
  .lemma-text { color: #a6adc8; }
  .status { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 10px; font-weight: 700; }
  .status.aligned { background: #a6e3a133; color: var(--green); }
  .status.fallback { background: #f9e2af33; color: var(--yellow); }
  .status.failed { background: #f38ba833; color: var(--red); }
  .boundary-list { display: flex; flex-direction: column; gap: 6px; }
  .boundary-row { padding: 7px 8px; border: 1px solid var(--border); border-radius: 6px; background: #1e1e2e; }
  .surface-chip { display: inline-block; min-width: 32px; padding: 1px 8px; border-radius: 999px;
                  background: #89b4fa22; color: var(--accent); font-size: 14px; font-weight: 700; }
  .offset { color: #6c7086; margin-left: 8px; font-size: 11px; }
  .tag-row { margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap; }
  .xpos-tag { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 10px; font-weight: 700;
              background: #89dceb22; color: var(--cyan); }
  .part-tag { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 10px; font-weight: 700;
              background: #fab38722; color: var(--peach); }
  .link-tag { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 10px; font-weight: 700;
              background: #a6e3a122; color: var(--green); }
  .src-tag { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 10px; font-weight: 700;
             background: #f9e2af22; color: var(--yellow); }
  .minor { color: #6c7086; font-size: 11px; }
  .json-raw { margin-top: 4px; color: #6c7086; font-size: 11px; }
</style>
</head>
<body>

<h1><span class="dot" id="statusDot"></span> Lemma Boundaries Debug</h1>
<div class="refresh-bar">
  <button class="btn" onclick="fetchDebug()">Refresh</button>
  <button class="btn" id="autoBtn" onclick="toggleAuto()">Auto: OFF</button>
  <a class="btn" href="/debug">Main Debug</a>
  <a class="btn" href="/debug/sqlite">SQLite</a>
  <a class="btn" href="/debug/scoring_information">Scoring Info</a>
  <span class="meta" id="metaInfo"></span>
</div>

<div class="note">
  Uses the last lookup snapshot from <code>/debug/data</code> plus the captured live hybrid
  <code>results_by_seg</code> payload. This page does not recompute lemma alignment or boundary placement;
  it only renders the slices and fill rows already produced by the active lookup path.
</div>

<div id="content" class="empty">No lookup data yet. Run a lookup in the main window first.</div>

<script>
var autoInterval = null;
var lastTimestamp = null;
var currentScoringFilter = 'all';

function esc(s) {
  if (s == null) return '';
  var d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function toggleAuto() {
  if (autoInterval) {
    clearInterval(autoInterval);
    autoInterval = null;
    document.getElementById('autoBtn').textContent = 'Auto: OFF';
    document.getElementById('autoBtn').classList.remove('active');
  } else {
    autoInterval = setInterval(fetchDebug, 1500);
    document.getElementById('autoBtn').textContent = 'Auto: ON';
    document.getElementById('autoBtn').classList.add('active');
  }
}

function splitCompoundParts(raw) {
  return String(raw || '').split(/\s*[+\uFF0B]\s*/).map(function(part) {
    return String(part || '').trim();
  }).filter(Boolean);
}

function normalizeIndexList(raw) {
  var src = Array.isArray(raw) ? raw : [];
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < src.length; i++) {
    var idx = Number(src[i]);
    if (!isFinite(idx) || idx < 0) continue;
    var key = String(idx);
    if (seen[key]) continue;
    seen[key] = true;
    out.push(idx);
  }
  return out;
}

function pushUnique(out, seen, raw) {
  var value = String(raw || '').trim();
  if (!value || seen[value]) return;
  seen[value] = true;
  out.push(value);
}

function pushUniqueInt(out, seen, raw) {
  var value = Number(raw);
  if (!isFinite(value)) return;
  var key = String(value);
  if (seen[key]) return;
  seen[key] = true;
  out.push(value);
}

function collectFillXposTags(fill) {
  var out = [];
  var seen = Object.create(null);
  var trace = (fill && typeof fill._debug_trace === 'object') ? fill._debug_trace : {};
  var raw = String(trace.effective_xpos || trace.xpos || fill.pos || '').trim();
  var parts = splitCompoundParts(raw);
  if (!parts.length && raw) parts = [raw];
  for (var i = 0; i < parts.length; i++) pushUnique(out, seen, parts[i]);
  return out;
}

function collectFillPartIds(fill) {
  var out = [];
  var seen = Object.create(null);
  pushUniqueInt(out, seen, fill && fill._lemma_part_index);
  pushUniqueInt(out, seen, fill && fill.lemma_part_index);
  return out;
}

function buildSlicesFromFillOffsets(surface, fills) {
  var surfaceText = String(surface || '');
  var rows = Array.isArray(fills) ? fills : [];
  var out = [];
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var start = Number(row._surface_start);
    var end = Number(row._surface_end);
    if (!isFinite(start) || !isFinite(end) || end <= start) continue;
    if (start < 0) start = 0;
    if (end > surfaceText.length) end = surfaceText.length;
    out.push({ start: start, end: end, fill_indexes: [i] });
  }
  out.sort(function(a, b) {
    if (a.start !== b.start) return a.start - b.start;
    return a.end - b.end;
  });
  return out;
}

function getCapturedGroups(surface, result) {
  var surfaceText = String(surface || '');
  if (!surfaceText) return [];
  var fills = Array.isArray(result && result.dict_fill) ? result.dict_fill : [];
  var slices = Array.isArray(result && result.dict_fill_surface_slices)
    ? result.dict_fill_surface_slices.slice()
    : [];
  if (!slices.length) slices = buildSlicesFromFillOffsets(surfaceText, fills);
  if (!slices.length && fills.length === 1) {
    slices = [{ start: 0, end: surfaceText.length, fill_indexes: [0] }];
  }

  var out = [];
  for (var i = 0; i < slices.length; i++) {
    var slice = slices[i] || {};
    var start = Number(slice.start);
    var end = Number(slice.end);
    if (!isFinite(start) || !isFinite(end)) continue;
    if (start < 0) start = 0;
    if (end < start) end = start;
    if (end > surfaceText.length) end = surfaceText.length;
    var fillIndexes = normalizeIndexList(slice.fill_indexes);
    var xposTags = [];
    var xposSeen = Object.create(null);
    var partIds = [];
    var partSeen = Object.create(null);
    var resolutionSources = [];
    var sourceSeen = Object.create(null);
    var fillLabels = [];
    var labelSeen = Object.create(null);
    var lemmaLinked = false;

    for (var fi = 0; fi < fillIndexes.length; fi++) {
      var fill = fills[fillIndexes[fi]] || {};
      var tags = collectFillXposTags(fill);
      for (var ti = 0; ti < tags.length; ti++) pushUnique(xposTags, xposSeen, tags[ti]);
      var ids = collectFillPartIds(fill);
      for (var pi = 0; pi < ids.length; pi++) pushUniqueInt(partIds, partSeen, ids[pi]);
      if (fill.resolution_linked_to_lemma) lemmaLinked = true;
      pushUnique(resolutionSources, sourceSeen, fill.resolution_source);
      pushUnique(fillLabels, labelSeen, fill.text || fill.head);
    }

    out.push({
      start: start,
      end: end,
      surface: surfaceText.slice(start, end),
      xpos_tags: xposTags,
      part_ids: partIds,
      resolution_sources: resolutionSources,
      lemma_linked: lemmaLinked,
      fill_labels: fillLabels
    });
  }
  return out;
}

function getRuntimeAlignmentDebug(result) {
  if (result && result._debug_runtime_lemma_alignment && typeof result._debug_runtime_lemma_alignment === 'object') {
    return result._debug_runtime_lemma_alignment;
  }
  var scoring = result && result._debug_lookup_scoring;
  if (scoring && scoring.lemma_runtime_alignment && typeof scoring.lemma_runtime_alignment === 'object') {
    return scoring.lemma_runtime_alignment;
  }
  return null;
}

function getRuntimePartMap(runtimeDebug) {
  var map = Object.create(null);
  var hintParts = Array.isArray(runtimeDebug && runtimeDebug.hint_parts) ? runtimeDebug.hint_parts : [];
  for (var i = 0; i < hintParts.length; i++) {
    var part = hintParts[i] || {};
    var idx = Number(part.index);
    if (!isFinite(idx) || idx < 0) continue;
    map[String(idx)] = {
      text: String(part.text || ''),
      source_text: String(part.source_text || ''),
      exact: !!part.exact,
      upos: String(part.upos || ''),
      xpos: String(part.xpos || '')
    };
  }
  return map;
}

function renderRuntimePartTags(partIds, runtimeDebug) {
  var ids = Array.isArray(partIds) ? partIds : [];
  if (!ids.length) return '<span class="minor">No part ids</span>';
  var partMap = getRuntimePartMap(runtimeDebug);
  var html = '';
  for (var i = 0; i < ids.length; i++) {
    var idx = Number(ids[i]);
    var info = partMap[String(idx)] || null;
    var label = 'part ' + String(idx);
    if (info && info.text) label = 'p' + String(idx) + '=' + info.text;
    html += '<span class="part-tag">' + esc(label) + '</span>';
    if (info && info.xpos) html += '<span class="xpos-tag">' + esc(info.xpos) + '</span>';
  }
  return html;
}

function renderRuntimeAlignment(runtimeDebug, surface) {
  if (!runtimeDebug || typeof runtimeDebug !== 'object') {
    return '<div class="minor">No runtime alignment trace captured</div>';
  }
  var surfaceText = String(surface || runtimeDebug.surface_text || '');
  var groups = Array.isArray(runtimeDebug.groups) ? runtimeDebug.groups : [];
  var boundaries = Array.isArray(runtimeDebug.boundaries) ? runtimeDebug.boundaries : [];
  var beforeNull = Array.isArray(runtimeDebug.char_assign_before_null_fill) ? runtimeDebug.char_assign_before_null_fill : [];
  var nullSteps = Array.isArray(runtimeDebug.null_fill_steps) ? runtimeDebug.null_fill_steps : [];
  var unassigned = beforeNull.filter(function(row) {
    return !(row && Array.isArray(row.part_ids) && row.part_ids.length);
  });

  var html = '<div class="json-raw">basis=' + esc(runtimeDebug.match_basis || '');
  html += ' | boundaries=' + esc(boundaries.length ? boundaries.join(', ') : 'none') + '</div>';
  if (unassigned.length) {
    html += '<div class="json-raw">unassigned-before-null-fill=' + esc(unassigned.map(function(row) {
      return String(row.char || '') + '@' + String(row.char_index);
    }).join(' | ')) + '</div>';
  }
  if (nullSteps.length) {
    html += '<div class="json-raw">null-fill=' + esc(nullSteps.map(function(step) {
      var partText = Array.isArray(step.part_ids) ? step.part_ids.map(function(id) { return 'p' + String(id); }).join(',') : '';
      return String(step.char || '') + '@' + String(step.char_index) + ' <- ' + String(step.source || '') + '@' + String(step.from_index) + (partText ? (' [' + partText + ']') : '');
    }).join(' | ')) + '</div>';
  }
  if (!groups.length) return html + '<div class="minor">No runtime groups</div>';

  html += '<div class="boundary-list">';
  for (var i = 0; i < groups.length; i++) {
    var group = groups[i] || {};
    var start = Number(group.start);
    var end = Number(group.end);
    if (!isFinite(start)) start = 0;
    if (!isFinite(end) || end < start) end = start;
    var surfaceSlice = surfaceText.slice(start, end);
    html += '<div class="boundary-row">';
    html += '<span class="surface-chip">' + esc(surfaceSlice || group.unit_text || '') + '</span>';
    html += '<span class="offset">' + esc(String(start) + ':' + String(end)) + '</span>';
    html += '<div class="tag-row">';
    html += renderRuntimePartTags(group.part_ids, runtimeDebug);
    html += '</div>';
    if (group.unit_text) {
      html += '<div class="json-raw">units=' + esc(group.unit_text) + '</div>';
    }
    html += '</div>';
  }
  html += '</div>';
  return html;
}

function shouldShowRow(surface, lemma, result, groups) {
  var surfaceText = String(surface || '');
  var lemmaText = String(lemma || '');
  var joinedLemma = splitCompoundParts(lemmaText).join('');
  if (!(surfaceText && lemmaText && surfaceText !== lemmaText && surfaceText !== joinedLemma)) return false;

  var resolution = (result && (result.resolution_actual || result.resolution_live)) || null;
  var runtimeDebug = getRuntimeAlignmentDebug(result);
  var category = String((resolution && resolution.category) || '').trim().toLowerCase();
  var resolvedVia = String((result && result.resolved_via) || (resolution && resolution.resolved_via) || '').trim().toLowerCase();
  var exactSurfaceMatch = !!(resolution && resolution.exact_surface_match);

  if (exactSurfaceMatch) return false;
  if (runtimeDebug && Array.isArray(runtimeDebug.groups) && runtimeDebug.groups.length) return true;
  if (resolvedVia === 'lemma_override' || resolvedVia === 'lemma_partial_override' || resolvedVia === 'lemma') return true;
  if (category === 'lemma_override' || category === 'lemma_partial_override') return true;
  return false;
}

function renderBoundaryCell(groups) {
  if (!groups || !groups.length) {
    return '<span class="minor">No captured slices</span>';
  }
  var html = '<div class="boundary-list">';
  for (var i = 0; i < groups.length; i++) {
    var group = groups[i] || {};
    var tags = Array.isArray(group.xpos_tags) ? group.xpos_tags : [];
    var partIds = Array.isArray(group.part_ids) ? group.part_ids : [];
    var resolutionSources = Array.isArray(group.resolution_sources) ? group.resolution_sources : [];
    var fillLabels = Array.isArray(group.fill_labels) ? group.fill_labels : [];
    html += '<div class="boundary-row">';
    html += '<span class="surface-chip">' + esc(group.surface || '') + '</span>';
    html += '<span class="offset">' + esc(String(group.start) + ':' + String(group.end)) + '</span>';
    html += '<div class="tag-row">';
    if (tags.length) {
      for (var ti = 0; ti < tags.length; ti++) {
        html += '<span class="xpos-tag">' + esc(tags[ti]) + '</span>';
      }
    } else {
      html += '<span class="minor">No XPOS tags</span>';
    }
    if (partIds.length) {
      for (var pi = 0; pi < partIds.length; pi++) {
        html += '<span class="part-tag">part ' + esc(partIds[pi]) + '</span>';
      }
    }
    if (group.lemma_linked) {
      html += '<span class="link-tag">lemma-linked</span>';
    }
    if (resolutionSources.length) {
      for (var ri = 0; ri < resolutionSources.length; ri++) {
        html += '<span class="src-tag">' + esc(resolutionSources[ri]) + '</span>';
      }
    }
    if (fillLabels.length) {
      html += '<div class="json-raw">fills=' + esc(fillLabels.join(' | ')) + '</div>';
    }
    html += '</div></div>';
  }
  html += '</div>';
  return html;
}

function render(data) {
  var ts = data._timestamp ? new Date(data._timestamp * 1000).toLocaleTimeString() : '?';
  var source = String(data.debug_scoring_source || 'snapshot');
  document.getElementById('metaInfo').textContent = 'Lang: ' + String(data.language || '?') + ' | ' + ts + ' | source=' + source;
  var tokens = Array.isArray(data.trankit_tokens) ? data.trankit_tokens : [];
  var results = Array.isArray(data.results_by_seg) ? data.results_by_seg : [];
  if (!tokens.length && !results.length) {
    document.getElementById('content').className = 'empty';
    document.getElementById('content').innerHTML = 'No token rows were found in the last lookup snapshot.';
    return;
  }

  if (source !== 'live_client_capture') {
    document.getElementById('content').className = 'empty';
    document.getElementById('content').innerHTML = 'No captured live lookup results yet. Turn on debug capture in the reader and run a fresh lookup.';
    return;
  }

  var html = '<div class="section">';
  html += '<div class="section-head">Runtime Lemma Realignment (original lookup output)</div>';
  html += '<table><thead><tr>';
  html += '<th>#</th><th>Token</th><th>Lemma</th><th>XPOS</th><th>Resolution</th><th>Runtime Decisions</th><th>Final Output</th>';
  html += '</tr></thead><tbody>';

  var rowCount = Math.max(tokens.length, results.length);
  var shown = 0;
  for (var i = 0; i < rowCount; i++) {
    var token = tokens[i] || {};
    var result = results[i] || {};
    var surface = String((result && (result.surface_form || result.text)) || (token && token.text) || '');
    var lemma = String((result && (result.lemma || result.lemma_form)) || (token && token.lemma) || '');
    var runtimeDebug = getRuntimeAlignmentDebug(result);
    var capturedGroups = getCapturedGroups(surface, result);
    if (!shouldShowRow(surface, lemma, result, capturedGroups)) continue;
    shown += 1;
    var resolution = (result && (result.resolution_actual || result.resolution_live)) || null;
    var label = String((resolution && resolution.label) || result.resolved_via || 'surface').trim();
    var finalText = String((resolution && resolution.final_text) || '').trim();
    var boundariesText = capturedGroups.length
      ? capturedGroups.map(function(group) { return String(group.start) + ':' + String(group.end); }).join(', ')
      : 'none';
    var locationText = '';
    if (token && token.sentence_index != null && token.token_index != null) {
      locationText = 'sent ' + String(token.sentence_index) + ', tok ' + String(token.token_index);
    }
    html += '<tr>';
    html += '<td class="minor">' + i + '</td>';
    html += '<td class="tok-text">' + esc(token.text || surface || '') + (locationText ? ('<div class="minor">' + esc(locationText) + '</div>') : '') + '</td>';
    html += '<td class="lemma-text">' + esc(lemma) + '</td>';
    html += '<td class="lemma-text">' + esc(result.tag || token.xpos || '') + '</td>';
    html += '<td><span class="status aligned">runtime</span><div class="json-raw">' + esc(label || 'surface');
    if (finalText) html += ' | ' + esc(finalText);
    html += '</div><div class="json-raw">boundaries=' + esc(boundariesText) + '</div></td>';
    html += '<td>' + renderRuntimeAlignment(runtimeDebug, surface) + '</td>';
    html += '<td>' + renderBoundaryCell(capturedGroups) + '</td>';
    html += '</tr>';
  }

  html += '</tbody></table></div>';
  var content = document.getElementById('content');
  if (!shown) {
    content.className = 'empty';
    content.innerHTML = 'No non-trivial lemma realignment rows were present in the last captured lookup.';
    return;
  }
  content.className = '';
  content.innerHTML = html;
}

function fetchDebug() {
  fetch('/debug/data', { cache: 'no-store' })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.ok) {
        document.getElementById('statusDot').classList.remove('live');
        document.getElementById('content').className = 'empty';
        document.getElementById('content').innerHTML = esc(data.error || 'No data');
        var filterInfo = document.getElementById('filterInfo');
        if (filterInfo) filterInfo.textContent = '';
        return;
      }
      if (data._timestamp && data._timestamp === lastTimestamp) return;
      lastTimestamp = data._timestamp;
      document.getElementById('statusDot').classList.add('live');
      render(data);
    })
    .catch(function(_e) {
      document.getElementById('statusDot').classList.remove('live');
      document.getElementById('content').className = 'empty';
      document.getElementById('content').innerHTML = 'Failed to load debug data.';
    });
}

fetchDebug();
</script>
</body>
</html>
"""


_DEBUG_SQLITE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>SQLite Debugger</title>
<style>
  :root {
    --bg: #11111b;
    --panel: #181825;
    --panel-2: #1e1e2e;
    --border: #313244;
    --text: #cdd6f4;
    --muted: #a6adc8;
    --green: #a6e3a1;
    --yellow: #f9e2af;
    --blue: #89b4fa;
    --red: #f38ba8;
    --teal: #94e2d5;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 20px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: var(--bg);
    color: var(--text);
  }
  a { color: var(--blue); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }
  .topbar h1 {
    margin: 0;
    font-size: 22px;
    color: var(--yellow);
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .btn {
    display: inline-block;
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--panel);
    color: var(--text);
    cursor: pointer;
  }
  .btn:hover { border-color: var(--blue); }
  .status {
    margin-bottom: 14px;
    color: var(--muted);
  }
  .chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 12px;
  }
  .chip {
    padding: 6px 10px;
    border-radius: 999px;
    background: var(--panel);
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 12px;
  }
  .section {
    margin-bottom: 14px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--panel);
    overflow: hidden;
  }
  .section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 14px;
    background: var(--panel-2);
    cursor: pointer;
    user-select: none;
    font-weight: 700;
  }
  .section-body {
    padding: 14px;
  }
  .collapsed { display: none; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 12px;
  }
  .card {
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px;
    background: rgba(255,255,255,0.02);
  }
  .card h3 {
    margin: 0 0 10px 0;
    font-size: 14px;
    color: var(--teal);
  }
  .kv {
    display: grid;
    grid-template-columns: 150px 1fr;
    gap: 6px 10px;
    font-size: 12px;
  }
  .kv div:nth-child(odd) { color: var(--muted); }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  th, td {
    padding: 8px 10px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    vertical-align: top;
    text-align: left;
  }
  th {
    color: var(--yellow);
    background: rgba(255,255,255,0.03);
    position: sticky;
    top: 0;
  }
  .muted { color: var(--muted); }
  .good { color: var(--green); }
  .warn { color: var(--yellow); }
  .bad { color: var(--red); }
  .mono {
    white-space: pre-wrap;
    word-break: break-word;
    background: rgba(0,0,0,0.18);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px;
    font-size: 11px;
    line-height: 1.5;
  }
  .download-btn {
    display: inline-block;
    padding: 10px 14px;
    border-radius: 8px;
    border: 1px solid var(--blue);
    background: rgba(137,180,250,0.12);
    color: #dce7ff;
    font-weight: 700;
  }
  details {
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px;
    padding: 8px 10px;
    background: rgba(255,255,255,0.02);
    margin-top: 8px;
  }
  summary {
    cursor: pointer;
    color: var(--teal);
  }
  .token-block {
    margin-bottom: 12px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: rgba(255,255,255,0.02);
    overflow: hidden;
  }
  .token-block > summary {
    margin: -8px -10px 0 -10px;
    padding: 12px 14px;
    background: rgba(255,255,255,0.03);
    color: var(--yellow);
    font-weight: 700;
  }
  .token-body {
    padding-top: 10px;
  }
  .empty {
    color: var(--muted);
    padding: 10px 0;
  }
</style>
</head>
<body>
<div class="topbar">
    <h1>SQLite Debugger</h1>
    <div class="actions">
      <a class="btn" href="/debug">Main Debug</a>
      <a class="btn" href="/debug/lemma_boundaries">Lemma Boundaries</a>
      <a class="btn" href="/debug/scoring_information">Scoring Info</a>
      <a class="btn" href="/debug/chatgpt_dump">ChatGPT Dump</a>
      <button class="btn" onclick="fetchSQLiteDebug()">Refresh</button>
    </div>
  </div>
  <div id="status" class="status">Loading…</div>
  <div id="content"></div>
<script>
function esc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fmtMs(value) {
  var n = Number(value || 0);
  if (!isFinite(n)) return '';
  if (n >= 1000) return (n / 1000).toFixed(2) + ' s';
  return n.toFixed(2) + ' ms';
}

function fmtBytes(value) {
  var n = Number(value || 0);
  if (!isFinite(n) || n <= 0) return '0 B';
  if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(2) + ' MB';
  if (n >= 1024) return (n / 1024).toFixed(2) + ' KB';
  return n + ' B';
}

function fmtJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch (_err) {
    return String(value);
  }
}

function toggleSection(head) {
  var body = head.nextElementSibling;
  var arrow = head.querySelector('.arrow');
  if (!body) return;
  if (body.classList.contains('collapsed')) {
    body.classList.remove('collapsed');
    if (arrow) arrow.textContent = '▾';
  } else {
    body.classList.add('collapsed');
    if (arrow) arrow.textContent = '▸';
  }
}

function renderSection(title, bodyHtml, openByDefault) {
  return '<div class="section">'
    + '<div class="section-head" onclick="toggleSection(this)"><span>' + esc(title) + '</span><span class="arrow">' + (openByDefault ? '▾' : '▸') + '</span></div>'
    + '<div class="section-body' + (openByDefault ? '' : ' collapsed') + '">' + bodyHtml + '</div>'
    + '</div>';
}

function renderChipList(values, emptyText) {
  var items = Array.isArray(values) ? values : [];
  if (!items.length) return '<div class="empty">' + esc(emptyText || 'None.') + '</div>';
  var html = '<div class="chip-row">';
  for (var i = 0; i < items.length; i++) {
    html += '<span class="chip">' + esc(items[i]) + '</span>';
  }
  html += '</div>';
  return html;
}

function renderTextList(values, emptyText) {
  var items = Array.isArray(values) ? values : [];
  if (!items.length) return '<div class="empty">' + esc(emptyText || 'None.') + '</div>';
  var html = '<ol style="margin:0; padding-left:20px;">';
  for (var i = 0; i < items.length; i++) {
    html += '<li style="margin:0 0 6px 0;">' + esc(items[i]) + '</li>';
  }
  html += '</ol>';
  return html;
}

function renderObjectChipList(obj, emptyText) {
  var out = [];
  var row = (obj && typeof obj === 'object') ? obj : null;
  if (row) {
    var keys = Object.keys(row);
    for (var i = 0; i < keys.length; i++) {
      var key = String(keys[i] || '');
      var value = row[key];
      if (value == null) continue;
      if (Array.isArray(value)) {
        out.push(key + '=' + String(value.length));
        continue;
      }
      if (typeof value === 'object') continue;
      var text = String(value || '');
      if (!text) continue;
      out.push(key + '=' + text);
    }
  }
  return renderChipList(out, emptyText || 'None.');
}

function renderRequestCard(title, req, opts) {
  if (!req || typeof req !== 'object') return '<div class="card"><h3>' + esc(title) + '</h3><div class="empty">No request recorded.</div></div>';
  var html = '<div class="card"><h3>' + esc(title) + '</h3>';
  html += '<div class="kv">';
  html += '<div>Method</div><div>' + esc(req.method || '') + '</div>';
  html += '<div>Path</div><div>' + esc(req.path || '') + '</div>';
  if (req.url) html += '<div>URL</div><div>' + esc(req.url) + '</div>';
  if (req.payload && typeof req.payload === 'object') {
    html += '<div>Payload</div><div>' + esc('winner_refs=' + String((req.payload.winner_refs || []).length) + ' | lang=' + String(req.payload.lang || '')) + '</div>';
  }
  html += '</div>';
  if (req.query) {
    html += '<div style="margin-top:10px;"><div class="muted" style="margin-bottom:6px;">Query Params</div>' + renderObjectChipList(req.query, 'No query params.') + '</div>';
  }
  if (req.payload) {
    html += '<div style="margin-top:10px;"><div class="muted" style="margin-bottom:6px;">Request Body</div>' + renderObjectChipList(req.payload, 'No request body.') + '</div>';
  }
  html += '</div>';
  return html;
}

function renderWinnerRefsTable(refs) {
  var rows = Array.isArray(refs) ? refs : [];
  if (!rows.length) return '<div class="empty">No winner refs.</div>';
  var html = '<table><thead><tr><th>UID</th><th>Kind</th><th>DB</th><th>Entry</th><th>Form</th><th>Match Key</th></tr></thead><tbody>';
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    html += '<tr>';
    html += '<td><span class="muted">' + esc(row.uid || '') + '</span></td>';
    html += '<td>' + esc(row.match_kind || '') + '</td>';
    html += '<td>' + esc(row.db_alias || '') + '</td>';
    html += '<td>' + esc(row.entry_row_id != null ? row.entry_row_id : '') + '</td>';
    html += '<td>' + esc(row.form_row_id != null ? row.form_row_id : '') + '</td>';
    html += '<td>' + esc(row.match_key || '') + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

function renderSegmentWinners(rows) {
  var items = Array.isArray(rows) ? rows : [];
  if (!items.length) return '<div class="empty">No per-segment winners were captured.</div>';
  var html = '';
  for (var i = 0; i < items.length; i++) {
    var row = items[i] || {};
    var head = '#' + String(row.segment_index != null ? row.segment_index : i)
      + '  ' + String(row.segment_text || '')
      + '  |  refs=' + String(row.winner_ref_count || 0)
      + '  |  mode=' + String(row.fill_mode || '');
    html += '<details' + (i < 3 ? ' open' : '') + '>';
    html += '<summary>' + esc(head) + '</summary>';
    html += '<div class="kv" style="margin-top:10px;">';
    html += '<div>Lemma</div><div>' + esc(row.lemma || '') + '</div>';
    html += '<div>UPOS / XPOS</div><div>' + esc((row.upos || '') + ' / ' + (row.xpos || '')) + '</div>';
    html += '<div>Deprel</div><div>' + esc(row.deprel || '') + '</div>';
    html += '<div>Resolved Via</div><div>' + esc(row.resolved_via || '') + '</div>';
    html += '<div>Resolution</div><div>' + esc((row.resolution_category || '') + ' | ' + (row.resolution_route_code || '')) + '</div>';
    html += '</div>';
    html += renderWinnerRefsTable(row.winner_refs || []);
    html += '</details>';
  }
  return html;
}

function renderDedupeRows(rows) {
  var items = Array.isArray(rows) ? rows : [];
  if (!items.length) return '<div class="empty">No dedupe rows were captured.</div>';
  var html = '<table><thead><tr><th>UID</th><th>Raw Count</th><th>Kept</th><th>Segments</th><th>Texts</th><th>Match Keys</th></tr></thead><tbody>';
  for (var i = 0; i < items.length; i++) {
    var row = items[i] || {};
    html += '<tr>';
    html += '<td><span class="muted">' + esc(row.uid || '') + '</span></td>';
    html += '<td>' + esc(row.raw_count != null ? row.raw_count : '') + '</td>';
    html += '<td class="' + (row.kept_after_dedupe ? 'good' : 'bad') + '">' + esc(row.kept_after_dedupe ? 'yes' : 'no') + '</td>';
    html += '<td>' + esc((row.segment_indexes || []).join(', ')) + '</td>';
    html += '<td>' + esc((row.segment_texts || []).join(' | ')) + '</td>';
    html += '<td>' + esc((row.match_keys || []).join(', ')) + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

function renderQueryWaves(waves) {
  var groups = Array.isArray(waves) ? waves : [];
  if (!groups.length) return '<div class="empty">No SQLite queries were captured.</div>';
  var html = '';
  for (var i = 0; i < groups.length; i++) {
    var wave = groups[i] || {};
    html += '<div class="card" style="margin-bottom:12px;">';
    html += '<h3>' + esc(wave.label || wave.wave_key || ('Wave ' + (i + 1))) + '</h3>';
    html += '<div class="chip-row">';
    html += '<span class="chip">Queries: ' + esc(wave.query_count != null ? wave.query_count : 0) + '</span>';
    html += '<span class="chip">Rows: ' + esc(wave.total_rows != null ? wave.total_rows : 0) + '</span>';
    html += '<span class="chip">Total: ' + esc(fmtMs(wave.total_ms)) + '</span>';
    html += '</div>';
    var queries = Array.isArray(wave.queries) ? wave.queries : [];
    for (var qi = 0; qi < queries.length; qi++) {
      var q = queries[qi] || {};
      html += '<details' + (qi === 0 ? ' open' : '') + '>';
      html += '<summary>' + esc((q.query_kind || 'query') + ' | ' + fmtMs(q.duration_ms) + ' | rows=' + (q.row_count != null ? q.row_count : 0)) + '</summary>';
      html += '<div class="kv" style="margin-top:10px;">';
      html += '<div>Scope</div><div>' + esc(q.scope || '') + '</div>';
      html += '<div>DB</div><div>' + esc(q.db_path || '') + '</div>';
      html += '<div>Params</div><div>' + esc(q.param_count != null ? q.param_count : 0) + '</div>';
      html += '<div>Rows</div><div>' + esc(q.row_count != null ? q.row_count : 0) + '</div>';
      html += '<div>Duration</div><div>' + esc(fmtMs(q.duration_ms)) + '</div>';
      html += '<div>Pct Total</div><div>' + esc(q.pct_total != null ? q.pct_total + '%' : '') + '</div>';
      html += '</div>';
      html += '</details>';
    }
    html += '</div>';
  }
  return html;
}

function summarizeQueryWaves(waves) {
  var groups = Array.isArray(waves) ? waves : [];
  var out = { query_count: 0, total_ms: 0, total_rows: 0 };
  for (var i = 0; i < groups.length; i++) {
    var wave = groups[i] || {};
    out.query_count += Number(wave.query_count || 0);
    out.total_ms += Number(wave.total_ms || 0);
    out.total_rows += Number(wave.total_rows || 0);
  }
  out.total_ms = Number(out.total_ms.toFixed(3));
  return out;
}

function collectResultFillRows(result) {
  var rows = [];
  var seen = Object.create(null);
  if (!result || typeof result !== 'object') return rows;
  var fills = Array.isArray(result.fills) ? result.fills : (Array.isArray(result.dict_fill) ? result.dict_fill : []);
  for (var i = 0; i < fills.length; i++) {
    var fill = fills[i];
    if (!fill || typeof fill !== 'object') continue;
    var entryIds = Array.isArray(fill.entry_ids) ? fill.entry_ids : [];
    var key = String(fill.text || '') + '|' + String(fill.head || '') + '|' + entryIds.join(',');
    if (seen[key]) continue;
    seen[key] = true;
    rows.push({
      text: String(fill.text || ''),
      head: String(fill.head || ''),
      source: String(fill.source || ''),
      entry_ids: entryIds.slice()
    });
  }
  return rows;
}

function renderResultFillRows(rawRows) {
  var rows = Array.isArray(rawRows) ? rawRows : collectResultFillRows(rawRows);
  if (!rows.length) return '<div class="empty">No child entries recorded for this token.</div>';
  var html = '<table><thead><tr><th>Text</th><th>Head</th><th>Source</th><th>Entry IDs</th></tr></thead><tbody>';
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    html += '<tr>';
    html += '<td>' + esc(row.text || '') + '</td>';
    html += '<td>' + esc(row.head || '') + '</td>';
    html += '<td>' + esc(row.source || '') + '</td>';
    html += '<td>' + esc((row.entry_ids || []).join(', ')) + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

function renderFormRows(rows, emptyText) {
  var items = Array.isArray(rows) ? rows : [];
  if (!items.length) return '<div class="empty">' + esc(emptyText || 'No form rows.') + '</div>';
  var html = '<table><thead><tr><th>Form</th><th>Tags</th><th>Reading</th></tr></thead><tbody>';
  for (var i = 0; i < items.length; i++) {
    var row = items[i] || {};
    html += '<tr>';
    html += '<td>' + esc(row.text || '') + '</td>';
    html += '<td>' + esc(row.tags || '') + '</td>';
    html += '<td>' + esc(row.roman || '') + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

function renderHydratedEntries(entries) {
  var items = Array.isArray(entries) ? entries : [];
  if (!items.length) return '<div class="empty">No hydrated entries were resolved for this token.</div>';
  var html = '';
  for (var i = 0; i < items.length; i++) {
    var item = items[i] || {};
    var entry = (item.entry && typeof item.entry === 'object') ? item.entry : {};
    var meta = (item.metadata && typeof item.metadata === 'object') ? item.metadata : {};
    var title = String(entry.display_headword || entry.lemma_headword || entry.entry_key || 'entry');
    if (entry.display_reading) title += ' [' + String(entry.display_reading) + ']';
    if (entry.pos) title += ' · ' + String(entry.pos);
    html += '<details' + (i === 0 ? ' open' : '') + '>';
    html += '<summary>' + esc(title) + '</summary>';
    html += '<div class="grid" style="margin-top:10px;">';
    html += '<div class="card"><h3>Entry</h3><div class="kv">';
    html += '<div>Source</div><div>' + esc(entry.source || '') + '</div>';
    html += '<div>Lemma Headword</div><div>' + esc(entry.lemma_headword || '') + '</div>';
    html += '<div>Match Kind</div><div>' + esc(entry.match_kind || '') + '</div>';
    html += '<div>Storage</div><div>' + esc((entry.storage_db_alias || '') + (entry.storage_row_id ? ' #' + entry.storage_row_id : '')) + '</div>';
    html += '<div>Lemma</div><div>' + esc(entry.lemma || '') + '</div>';
    html += '<div>Morph Base</div><div>' + esc(entry.morph_base || '') + '</div>';
    html += '</div>';
    html += renderChipList(entry.morph_info || [], 'No morph info.');
    html += '</div>';
    var entryNormKinds = Array.isArray(meta.norm_kinds) ? meta.norm_kinds : [];
    var entryWasNormalized = entryNormKinds.length > 0;
    html += '<div class="card"><h3>Match Metadata</h3><div class="kv">';
    html += '<div>Requested Match Kinds</div><div>' + esc((meta.requested_match_kinds || []).join(', ')) + '</div>';
    html += '<div>Match Keys</div><div>' + esc((meta.requested_match_keys || []).join(', ')) + '</div>';
    html += '<div>Form Row IDs</div><div>' + esc((meta.requested_form_row_ids || []).join(', ')) + '</div>';
    html += '<div>Special Rows</div><div>' + esc((meta.special_form_rows || []).length) + '</div>';
    html += '<div>Same Headword Rows</div><div>' + esc((meta.same_headword_form_rows || []).length) + '</div>';
    html += '<div>Matched Overlays</div><div>' + esc((meta.form_overlays || []).length) + '</div>';
    html += '<div>Match via Normalization</div><div style="color:' + (entryWasNormalized ? '#94e2d5' : '#a6adc8') + ';">' + esc(entryWasNormalized ? 'YES (' + entryNormKinds.length + ' rule' + (entryNormKinds.length === 1 ? '' : 's') + ')' : 'no') + '</div>';
    html += '</div></div>';
    if (entryNormKinds.length) {
      html += '<div class="card"><h3>Normalization Rules (this entry)</h3>' + renderNormKinds(entryNormKinds) + '</div>';
    }
    html += '</div>';
    html += '<details open><summary>Senses</summary>' + renderTextList(entry.senses || [], 'No senses.') + '</details>';
    if (entry.commentary || entry.grammar || entry.etymology || entry.note) {
      html += '<details><summary>Notes</summary><div class="kv" style="margin-top:10px;">';
      html += '<div>Commentary</div><div>' + esc(entry.commentary || '') + '</div>';
      html += '<div>Grammar</div><div>' + esc(entry.grammar || '') + '</div>';
      html += '<div>Etymology</div><div>' + esc(entry.etymology || '') + '</div>';
      html += '<div>Note</div><div>' + esc(entry.note || '') + '</div>';
      html += '</div></details>';
    }
    if (Array.isArray(meta.special_form_rows) && meta.special_form_rows.length) {
      html += '<details><summary>Special Form Rows</summary>' + renderFormRows(meta.special_form_rows || [], 'No special-tag rows.') + '</details>';
    }
    if (Array.isArray(meta.same_headword_form_rows) && meta.same_headword_form_rows.length) {
      html += '<details><summary>Same Headword Form Rows</summary>' + renderFormRows(meta.same_headword_form_rows || [], 'No same-headword rows.') + '</details>';
    }
    if (Array.isArray(meta.form_overlays) && meta.form_overlays.length) {
      html += '<details><summary>Matched Form Overlays</summary>';
      for (var oi = 0; oi < meta.form_overlays.length; oi++) {
        var overlay = meta.form_overlays[oi] || {};
        var matchedForm = (overlay.matched_form && typeof overlay.matched_form === 'object') ? overlay.matched_form : {};
        html += '<div class="card" style="margin-bottom:10px;">';
        html += '<div class="kv">';
        html += '<div>Display</div><div>' + esc((overlay.display_headword || '') + ((overlay.display_reading || '') ? ' [' + overlay.display_reading + ']' : '')) + '</div>';
        html += '<div>Match Kind</div><div>' + esc(overlay.match_kind || '') + '</div>';
        html += '<div>Morph Base</div><div>' + esc(overlay.morph_base || '') + '</div>';
        html += '<div>Alternate</div><div>' + esc(overlay.is_alternate_match ? 'yes' : 'no') + '</div>';
        html += '</div>';
        html += renderChipList(overlay.morph_info || [], 'No overlay morph info.');
        if (matchedForm.text || matchedForm.tags || matchedForm.roman) {
          html += '<div style="margin-top:8px;">' + renderFormRows([matchedForm], 'No matched form.') + '</div>';
        }
        html += '</div>';
      }
      html += '</details>';
    }
    html += '</details>';
  }
  return html;
}

function renderWaveStats(waves) {
  var items = Array.isArray(waves) ? waves : [];
  if (!items.length) return '<div class="empty">No SQLite wave activity.</div>';
  var html = '<table><thead><tr><th>Wave</th><th>Queries</th><th>Rows</th><th>Time</th></tr></thead><tbody>';
  for (var i = 0; i < items.length; i++) {
    var row = items[i] || {};
    html += '<tr>';
    html += '<td>' + esc(row.label || row.wave_key || '') + '</td>';
    html += '<td>' + esc(row.query_count != null ? row.query_count : 0) + '</td>';
    html += '<td>' + esc(row.total_rows != null ? row.total_rows : 0) + '</td>';
    html += '<td>' + esc(fmtMs(row.total_ms)) + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

function renderNormKinds(normKinds) {
  var items = Array.isArray(normKinds) ? normKinds : [];
  if (!items.length) {
    return '<div style="color:#a6adc8;font-size:11px;padding:4px 0;">No normalization was applied — match key identical to surface text.</div>';
  }
  var html = '<table style="width:100%;border-collapse:collapse;font-size:11px;">';
  html += '<thead><tr style="color:#6c7086;">';
  html += '<th style="text-align:left;padding:2px 6px;">Rule ID</th>';
  html += '<th style="text-align:left;padding:2px 6px;">Description</th>';
  html += '<th style="text-align:left;padding:2px 6px;">Before</th>';
  html += '<th style="text-align:left;padding:2px 6px;">After</th>';
  html += '</tr></thead><tbody>';
  for (var i = 0; i < items.length; i++) {
    var nk = items[i] || {};
    var changed = String(nk.before || '') !== String(nk.after || '');
    var rowColor = changed ? '#94e2d5' : '#a6adc8';
    html += '<tr>';
    html += '<td style="padding:2px 6px;color:' + rowColor + ';font-family:monospace;">' + esc(nk.id || '') + '</td>';
    html += '<td style="padding:2px 6px;color:#cdd6f4;">' + esc(nk.label || '') + '</td>';
    html += '<td style="padding:2px 6px;color:#f38ba8;font-family:monospace;">' + esc(nk.before || '') + '</td>';
    html += '<td style="padding:2px 6px;color:#a6e3a1;font-family:monospace;">' + esc(nk.after || '') + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

function renderFillTrace(fill, index) {
  var row = (fill && typeof fill === 'object') ? fill : {};
  var analysis = (row.analysis && typeof row.analysis === 'object') ? row.analysis : {};
  var normKinds = Array.isArray(analysis.norm_kinds) ? analysis.norm_kinds : [];
  var wasNormalized = !!(analysis.was_normalized) || normKinds.length > 0;
  var summary = 'Fill ' + String(index + 1) + '  ' + String(row.fill_text || '');
  if (row.fill_source) summary += '  |  ' + String(row.fill_source);
  summary += '  |  entries=' + String(analysis.entry_count != null ? analysis.entry_count : 0);
  if (wasNormalized) summary += '  |  [NORM:' + normKinds.length + ' rule(s)]';
  var html = '<details' + (index === 0 ? ' open' : '') + '>';
  html += '<summary>' + esc(summary) + '</summary>';
  html += '<div class="grid" style="margin-top:10px;">';
  html += '<div class="card"><h3>Fill Analysis</h3><div class="kv">';
  html += '<div>Fill Text</div><div>' + esc(row.fill_text || '') + '</div>';
  html += '<div>Fill Head</div><div>' + esc(row.fill_head || '') + '</div>';
  html += '<div>Source</div><div>' + esc(row.fill_source || '') + '</div>';
  html += '<div>Entry Count</div><div>' + esc(analysis.entry_count != null ? analysis.entry_count : 0) + '</div>';
  html += '<div>Special Rows</div><div>' + esc(analysis.special_form_row_count != null ? analysis.special_form_row_count : 0) + '</div>';
  html += '<div>Same Headword Rows</div><div>' + esc(analysis.same_headword_form_row_count != null ? analysis.same_headword_form_row_count : 0) + '</div>';
  html += '<div>Matched Overlays</div><div>' + esc(analysis.matched_form_overlay_count != null ? analysis.matched_form_overlay_count : 0) + '</div>';
  html += '<div>Match via Normalization</div><div style="color:' + (wasNormalized ? '#94e2d5' : '#a6adc8') + ';">' + esc(wasNormalized ? 'YES (' + normKinds.length + ' rule' + (normKinds.length === 1 ? '' : 's') + ')' : 'no') + '</div>';
  html += '</div>';
  html += renderChipList(analysis.match_kinds || [], 'No match kinds.');
  html += '</div>';
  html += '<div class="card"><h3>Normalization Rules Applied</h3>';
  html += renderNormKinds(normKinds);
  html += '</div>';
  html += '<div class="card"><h3>Attached Entry IDs</h3>' + renderChipList(row.entry_ids || [], 'No entry ids.') + '</div>';
  html += '</div>';
  html += '<details open><summary>Dictionary Entries</summary>' + renderHydratedEntries(row.entries || []) + '</details>';
  html += '</details>';
  return html;
}

function renderFillTraces(fills) {
  var items = Array.isArray(fills) ? fills : [];
  if (!items.length) return '<div class="empty">No fills were produced for this token.</div>';
  var html = '';
  for (var i = 0; i < items.length; i++) {
    html += renderFillTrace(items[i] || {}, i);
  }
  return html;
}

function renderQueryAnalysis(panel, downloadMeta) {
  var row = (panel && typeof panel === 'object') ? panel : {};
  var html = '<div class="grid">';
  html += '<div class="card"><h3>Query Analysis</h3><div class="kv">';
  html += '<div>Query</div><div>' + esc(row.q || '') + '</div>';
  html += '<div>Language</div><div>' + esc(row.language || '') + '</div>';
  html += '<div>Segments</div><div>' + esc(row.segment_count != null ? row.segment_count : 0) + '</div>';
  html += '<div>Raw Winner Refs</div><div>' + esc(row.raw_winner_ref_count != null ? row.raw_winner_ref_count : 0) + '</div>';
  html += '<div>Deduped Winner Refs</div><div>' + esc(row.deduped_winner_ref_count != null ? row.deduped_winner_ref_count : 0) + '</div>';
  html += '<div>Fills</div><div>' + esc(row.fill_count != null ? row.fill_count : 0) + '</div>';
  html += '<div>Entries</div><div>' + esc(row.entry_count != null ? row.entry_count : 0) + '</div>';
  html += '<div>SQLite Queries</div><div>' + esc(row.sqlite_query_count != null ? row.sqlite_query_count : 0) + '</div>';
  html += '<div>SQLite Time</div><div>' + esc(fmtMs(row.sqlite_total_ms)) + '</div>';
  html += '<div>Special Rows</div><div>' + esc(row.special_form_row_count != null ? row.special_form_row_count : 0) + '</div>';
  html += '<div>Same Headword Rows</div><div>' + esc(row.same_headword_form_row_count != null ? row.same_headword_form_row_count : 0) + '</div>';
  html += '</div></div>';
  html += '<div class="card"><h3>Wave Breakdown</h3>' + renderWaveStats(row.wave_stats || []) + '</div>';
  html += '</div>';
  if (downloadMeta && typeof downloadMeta === 'object' && downloadMeta.download_url) {
    html += '<div class="card" style="margin-top:12px;"><h3>Frontend Payload Download</h3><div class="kv">';
    html += '<div>Filename</div><div>' + esc(downloadMeta.filename || '') + '</div>';
    html += '<div>Size</div><div>' + esc(fmtBytes(downloadMeta.size_bytes)) + '</div>';
    html += '<div>Created</div><div>' + esc(downloadMeta.created_at || '') + '</div>';
    html += '</div>';
    html += '<div style="margin-top:12px;"><a class="download-btn" href="' + esc(downloadMeta.download_url) + '">Download JSON</a></div></div>';
  }
  return html;
}

function renderTokenOverviewCards(token) {
  var analysis = (token && typeof token.analysis === 'object') ? token.analysis : {};
  var html = '<div class="grid">';
  html += '<div class="card"><h3>Token Analysis</h3><div class="kv">';
  html += '<div>Token</div><div>' + esc(token.segment_text || '') + '</div>';
  html += '<div>Lemma</div><div>' + esc(token.lemma || '') + '</div>';
  html += '<div>UPOS / XPOS</div><div>' + esc((token.upos || '') + ' / ' + (token.xpos || '')) + '</div>';
  html += '<div>Deprel</div><div>' + esc(token.deprel || '') + '</div>';
  html += '<div>Resolved Via</div><div>' + esc(token.resolved_via || '') + '</div>';
  html += '<div>Fill Mode</div><div>' + esc(token.fill_mode || '') + '</div>';
  html += '<div>Resolution</div><div>' + esc((token.resolution_category || '') + ' | ' + (token.resolution_route_code || '')) + '</div>';
  html += '<div>Raw Winner Refs</div><div>' + esc(analysis.raw_winner_ref_count != null ? analysis.raw_winner_ref_count : 0) + '</div>';
  html += '<div>Deduped Winner Refs</div><div>' + esc(analysis.deduped_winner_ref_count != null ? analysis.deduped_winner_ref_count : 0) + '</div>';
  html += '<div>Fills</div><div>' + esc(analysis.fill_count != null ? analysis.fill_count : 0) + '</div>';
  html += '<div>Entries</div><div>' + esc(analysis.entry_count != null ? analysis.entry_count : 0) + '</div>';
  html += '<div>SQLite Queries</div><div>' + esc(analysis.sqlite_query_count != null ? analysis.sqlite_query_count : 0) + '</div>';
  html += '<div>SQLite Time</div><div>' + esc(fmtMs(analysis.sqlite_total_ms)) + '</div>';
  html += '<div>Special Rows</div><div>' + esc(analysis.special_form_row_count != null ? analysis.special_form_row_count : 0) + '</div>';
  html += '<div>Same Headword Rows</div><div>' + esc(analysis.same_headword_form_row_count != null ? analysis.same_headword_form_row_count : 0) + '</div>';
  html += '<div>Matched Overlays</div><div>' + esc(analysis.matched_form_overlay_count != null ? analysis.matched_form_overlay_count : 0) + '</div>';
  html += '</div></div>';
  html += '<div class="card"><h3>Wave Breakdown</h3>' + renderWaveStats(analysis.wave_stats || []) + '</div>';
  html += '</div>';
  return html;
}

function renderTokenEntryFlow(token) {
  return renderFillTraces(token.fills || []);
}

function renderTokenTrace(token, index) {
  var analysis = (token && typeof token.analysis === 'object') ? token.analysis : {};
  var tokenLabel = token.segment_text || '(empty)';
  var header = '#'
    + String(token.segment_index != null ? token.segment_index : index)
    + '  '
    + String(tokenLabel)
    + '  | fills=' + String(analysis.fill_count != null ? analysis.fill_count : 0)
    + '  | entries=' + String(analysis.entry_count != null ? analysis.entry_count : 0)
    + '  | sqlite=' + String(fmtMs(analysis.sqlite_total_ms || 0));
  var html = '<details class="token-block"' + (index < 3 ? ' open' : '') + '>';
  html += '<summary>' + esc(header) + '</summary>';
  html += '<div class="token-body">';
  html += renderTokenOverviewCards(token);
  html += '<details open><summary>Fills</summary>' + renderTokenEntryFlow(token) + '</details>';
  html += '</div>';
  html += '</details>';
  return html;
}

function renderTokenTraces(tokens) {
  var items = Array.isArray(tokens) ? tokens : [];
  if (!items.length) return '<div class="empty">No token-keyed sqlite trace is available for this lookup.</div>';
  var html = '';
  for (var i = 0; i < items.length; i++) {
    html += renderTokenTrace(items[i] || {}, i);
  }
  return html;
}

function renderDownloadCard(meta) {
  if (!meta || typeof meta !== 'object' || !meta.download_url) {
    return '<div class="card"><h3>Frontend Payload Download</h3><div class="empty">No hydrate payload artifact is available for this capture.</div></div>';
  }
  var html = '<div class="card"><h3>Frontend Payload Download</h3>';
  html += '<div class="kv">';
  html += '<div>Filename</div><div>' + esc(meta.filename || '') + '</div>';
  html += '<div>Size</div><div>' + esc(fmtBytes(meta.size_bytes)) + '</div>';
  html += '<div>Created</div><div>' + esc(meta.created_at || '') + '</div>';
  html += '</div>';
  html += '<div style="margin-top:12px;"><a class="download-btn" href="' + esc(meta.download_url) + '">Download JSON</a></div>';
  html += '</div>';
  return html;
}

function renderPage(data) {
  var content = document.getElementById('content');
  var status = document.getElementById('status');
  if (!data || !data.ok) {
    if (status) status.textContent = (data && data.error) ? data.error : 'Failed to load sqlite debug data.';
    if (content) content.innerHTML = '';
    return;
  }
  var queryAnalysis = (data.query_analysis && typeof data.query_analysis === 'object') ? data.query_analysis : {};
  var tokenTraces = Array.isArray(data.token_traces) ? data.token_traces : [];
  if (status) {
    status.textContent = 'Capture ' + String(data.debug_capture_id || 'none')
      + ' | lang=' + String(queryAnalysis.language || '')
      + ' | q=' + String(queryAnalysis.q || '');
  }
  var html = '';
  html += renderSection('Query Analysis', renderQueryAnalysis(queryAnalysis, data.payload_download), true);
  html += renderSection('Token Walkthroughs', renderTokenTraces(tokenTraces), true);
  content.innerHTML = html;
}

function fetchSQLiteDebug() {
  var status = document.getElementById('status');
  if (status) status.textContent = 'Loading sqlite debug capture…';
  fetch('/debug/sqlite/data', { cache: 'no-store' })
    .then(function(resp) { return resp.json(); })
    .then(function(data) { renderPage(data); })
    .catch(function(err) {
      renderPage({ ok: false, error: String(err || 'Request failed') });
    });
}

fetchSQLiteDebug();
</script>
</body>
</html>
"""

_DEBUG_CHATGPT_DUMP_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ChatGPT Dump Debug</title>
<style>
  :root { --bg: #1e1e2e; --fg: #cdd6f4; --surface: #313244; --border: #45475a;
          --accent: #89b4fa; --green: #a6e3a1; --red: #f38ba8; --yellow: #f9e2af;
          --mono: 'Cascadia Code', 'Fira Code', 'Consolas', monospace; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: var(--mono); font-size: 13px; background: var(--bg); color: var(--fg);
         padding: 16px; line-height: 1.6; }
  h1 { font-size: 16px; color: var(--accent); margin-bottom: 12px; display: flex;
       align-items: center; gap: 10px; }
  h1 .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--red); }
  h1 .dot.live { background: var(--green); }
  .refresh-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
  .btn { background: var(--surface); color: var(--fg); border: 1px solid var(--border);
         padding: 4px 12px; border-radius: 4px; font-size: 12px; cursor: pointer;
         font-family: var(--mono); text-decoration: none; }
  .btn:hover { background: #3b3d52; }
  .btn.active { background: var(--accent); color: var(--bg); border-color: var(--accent); }
  .meta { font-size: 11px; color: #6c7086; }
  .note { margin-bottom: 16px; padding: 10px 12px; background: #181825; border: 1px solid var(--border);
          border-radius: 6px; color: #a6adc8; }
  .empty { text-align: center; padding: 40px; color: #6c7086; border: 1px solid var(--border);
           border-radius: 6px; background: #181825; }
  .dump-wrap { border: 1px solid var(--border); border-radius: 6px; overflow: hidden; background: #181825; }
  .dump-head { background: var(--surface); padding: 10px 12px; font-weight: bold; display: flex;
               justify-content: space-between; align-items: center; gap: 12px; }
  pre { margin: 0; padding: 12px; white-space: pre-wrap; word-break: break-word; max-height: 75vh; overflow: auto; }
</style>
</head>
<body>

<h1><span class="dot" id="statusDot"></span> ChatGPT Dump Debug</h1>
<div class="refresh-bar">
  <button class="btn" onclick="fetchDump()">Refresh</button>
  <button class="btn" id="autoBtn" onclick="toggleAuto()">Auto: OFF</button>
  <button class="btn" onclick="copyDump()">Copy Text</button>
  <a class="btn" href="/debug">Main Debug</a>
  <a class="btn" href="/debug/sqlite">SQLite</a>
  <a class="btn" href="/debug/lemma_boundaries">Lemma Boundaries</a>
  <a class="btn" href="/debug/scoring_information">Scoring Info</a>
  <span class="meta" id="metaInfo"></span>
</div>

<div class="note">
  Plain text dump for external review. Each token is followed only by the dictionary entry lines that actually survive
  filtering on the live site. This page uses the exact live browser lookup payload captured after client-side dictionary merge, including uploaded TSV overlays. Visible inflection notes and raw Hanja lists are included. Filtered-out senses, Korean Hanja-reading rows, and lines past the first 10 definition lines per entry are omitted.
</div>

<div id="content" class="empty">No lookup data yet. Run a lookup in the main window first.</div>

<script src="/static/dictionary_normalization_layer.js?v=20260311b"></script>
<script src="/static/dictionary_engine.js?v=20260311b"></script>
<script src="/static/dictionary_client.js?v=20260311f"></script>
<script>
var autoInterval = null;
var lastTimestamp = null;
var lastDumpText = '';

function esc(s) {
  if (s == null) return '';
  var d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function toggleAuto() {
  if (autoInterval) {
    clearInterval(autoInterval);
    autoInterval = null;
    document.getElementById('autoBtn').textContent = 'Auto: OFF';
    document.getElementById('autoBtn').classList.remove('active');
  } else {
    autoInterval = setInterval(fetchDump, 1500);
    document.getElementById('autoBtn').textContent = 'Auto: ON';
    document.getElementById('autoBtn').classList.add('active');
  }
}

function clonePlainObject(obj) {
  var out = {};
  var src = obj || {};
  for (var k in src) {
    if (Object.prototype.hasOwnProperty.call(src, k)) out[k] = src[k];
  }
  return out;
}

function normalizeLangCode(raw) {
  return String(raw || '').trim().toLowerCase();
}

function isMeaningfulValue(v) {
  if (v == null) return false;
  if (typeof v === 'string') return !!v.trim();
  if (Array.isArray(v)) return !!v.length;
  if (typeof v === 'object') return Object.keys(v).length > 0;
  return true;
}

function parseSenseLineForDump(rawLine) {
  var raw = String(rawLine || '');
  var cleaned = raw.replace(/\u001e/g, '').replace(/\u001f/g, ' ').trim();
  var parts = raw.split('\t');
  var gloss = cleaned;
  if (parts.length >= 4) {
    gloss = String(parts.slice(3).join('\t') || '').trim();
  } else if (parts.length >= 2) {
    gloss = String(parts[parts.length - 1] || '').trim();
  }
  if (!gloss) gloss = cleaned;
  return gloss.replace(/\s+/g, ' ').trim();
}

function collectVisibleSenseLines(lines) {
  var out = [];
  var seen = Object.create(null);
  var list = Array.isArray(lines) ? lines : [];
  for (var i = 0; i < list.length; i++) {
    var raw = String(list[i] || '');
    if (!raw || raw.charAt(0) === '\x1E') continue;
    var gloss = parseSenseLineForDump(raw);
    if (!gloss || seen[gloss]) continue;
    seen[gloss] = true;
    out.push(gloss);
  }
  return out;
}

function limitDumpSenseLines(lines) {
  var list = Array.isArray(lines) ? lines : [];
  if (list.length <= 10) return list;
  return list.slice(0, 10);
}

function normalizeDumpMorphTags(rawMorph) {
  var out = [];
  var seen = Object.create(null);
  var src = Array.isArray(rawMorph) ? rawMorph : (rawMorph ? [rawMorph] : []);
  for (var i = 0; i < src.length; i++) {
    var chunk = String(src[i] == null ? '' : src[i]).toLowerCase();
    if (!chunk) continue;
    var parts = chunk.split(/[;|,]/);
    for (var j = 0; j < parts.length; j++) {
      var tag = String(parts[j] || '').trim();
      if (!tag || seen[tag]) continue;
      seen[tag] = true;
      out.push(tag);
    }
  }
  return out;
}

function normalizeDumpTextList(raw) {
  var out = [];
  var seen = Object.create(null);
  var src = Array.isArray(raw) ? raw : (raw ? [raw] : []);
  for (var i = 0; i < src.length; i++) {
    var text = String(src[i] == null ? '' : src[i]).trim();
    if (!text || seen[text]) continue;
    seen[text] = true;
    out.push(text);
  }
  return out;
}

function isKoreanLanguageForDump(rawLang) {
  return normalizeLangCode(rawLang) === 'ko';
}

function isHanjaReadingLikeGroup(row, rawLang) {
  if (!isKoreanLanguageForDump(rawLang)) return false;
  var grp = row || {};
  var pos = String(grp.pos || '').trim().toLowerCase();
  if (pos === 'syl' || pos === 'syllable') return true;

  var morphTags = normalizeDumpMorphTags(grp.morph_info);
  for (var i = 0; i < morphTags.length; i++) {
    var tag = morphTags[i];
    if (tag === 'hangeul' || tag === 'eumhun' || tag === 'syl' || tag === 'syllable') {
      return true;
    }
  }

  var hangeulForms = Array.isArray(grp.hangeul_forms) ? grp.hangeul_forms : [];
  return hangeulForms.length > 0;
}

function extractDumpGlossesFromStructuredSense(sense) {
  var out = [];
  var s = sense || {};
  if (!s || typeof s !== 'object') return out;

  var glosses = Array.isArray(s.glosses) ? s.glosses : [];
  if (glosses.length) {
    var text = glosses.join('; ');
    var misc = Array.isArray(s.misc) ? s.misc : [];
    var field = Array.isArray(s.field) ? s.field : [];
    var stagk = Array.isArray(s.stagk) ? s.stagk : [];
    var stagr = Array.isArray(s.stagr) ? s.stagr : [];
    var xref = Array.isArray(s.xref) ? s.xref : [];
    var ant = Array.isArray(s.ant) ? s.ant : [];
    var dial = Array.isArray(s.dial) ? s.dial : [];
    var lsource = Array.isArray(s.lsource) ? s.lsource : [];
    var sInf = String(s.s_inf || '').trim();
    var annotations = [];
    for (var i = 0; i < misc.length; i++) {
      var mv = String(misc[i] || '').trim();
      if (mv) annotations.push(mv);
    }
    for (var f = 0; f < field.length; f++) {
      var fv = String(field[f] || '').trim();
      if (fv) annotations.push(fv);
    }
    for (var d = 0; d < dial.length; d++) {
      var dv = String(dial[d] || '').trim();
      if (dv) annotations.push(dv);
    }
    if (stagk.length) annotations.push('kanji: ' + stagk.join(', '));
    if (stagr.length) annotations.push('reading: ' + stagr.join(', '));
    if (lsource.length) annotations.push('source: ' + lsource.join(', '));
    if (annotations.length) text += ' [' + annotations.join('; ') + ']';
    if (xref.length) text += ' [cf. ' + xref.join(', ') + ']';
    if (ant.length) text += ' [ant. ' + ant.join(', ') + ']';
    if (sInf) text += ' (' + sInf + ')';
    if (text) out.push(text.replace(/\s+/g, ' ').trim());
    return out;
  }

  var enLemma = String(s.en_lemma || '').trim().replace(/^-+|-+$/g, '');
  var enDef = String(s.en_definition || '').trim().replace(/^-+|-+$/g, '');
  var koDef = String(s.definition_ko || '').trim();
  if (enLemma) out.push(enLemma);
  else if (enDef) out.push(enDef);
  else if (koDef) out.push(koDef);
  return out;
}

function collectVisibleSenseLinesFromGroups(groups, rawLang) {
  var out = [];
  var seen = Object.create(null);
  var src = Array.isArray(groups) ? groups : [];
  for (var gi = 0; gi < src.length; gi++) {
    var grp = src[gi] || {};
    var posGroups = Array.isArray(grp.pos_groups) ? grp.pos_groups : [];
    var rows = [];
    if (posGroups.length) {
      for (var pi = 0; pi < posGroups.length; pi++) {
        var pg = posGroups[pi] || {};
        rows.push({
          pos: pg.pos || grp.pos || '',
          senses: Array.isArray(pg.senses) ? pg.senses : (Array.isArray(grp.senses) ? grp.senses : []),
          morph_info: pg.morph_info || grp.morph_info || [],
          hangeul_forms: Array.isArray(pg.hangeul_forms) ? pg.hangeul_forms : (Array.isArray(grp.hangeul_forms) ? grp.hangeul_forms : [])
        });
      }
    } else {
      rows.push({
        pos: grp.pos || '',
        senses: Array.isArray(grp.senses) ? grp.senses : [],
        morph_info: grp.morph_info || [],
        hangeul_forms: Array.isArray(grp.hangeul_forms) ? grp.hangeul_forms : []
      });
    }

    for (var ri = 0; ri < rows.length; ri++) {
      var row = rows[ri] || {};
      if (isHanjaReadingLikeGroup(row, rawLang)) continue;
      var senses = Array.isArray(row.senses) ? row.senses : [];
      for (var si = 0; si < senses.length; si++) {
        var sense = senses[si];
        var glosses = [];
        if (sense && typeof sense === 'object') {
          glosses = extractDumpGlossesFromStructuredSense(sense);
        } else {
          glosses = collectVisibleSenseLines([sense]);
        }
        for (var gj = 0; gj < glosses.length; gj++) {
          var gloss = String(glosses[gj] || '').replace(/\s+/g, ' ').trim();
          if (!gloss || seen[gloss]) continue;
          seen[gloss] = true;
          out.push(gloss);
        }
      }
    }
  }
  return out;
}

function collectVisibleLinesForDumpEntry(entry, rawLang) {
  var row = entry || {};
  var groupedSource = [];
  if (Array.isArray(row.entry_groups_hover) && row.entry_groups_hover.length) {
    groupedSource = row.entry_groups_hover;
  } else if (Array.isArray(row.entry_groups) && row.entry_groups.length) {
    groupedSource = row.entry_groups;
  }
  if (groupedSource.length) return limitDumpSenseLines(collectVisibleSenseLinesFromGroups(groupedSource, rawLang));
  return limitDumpSenseLines(collectVisibleSenseLines(row.senses_hover || row.senses || []));
}

function collectDumpMorphNote(entry, rawLang) {
  var row = entry || {};
  var baseSeen = Object.create(null);
  var tagSeen = Object.create(null);
  var bases = [];
  var tags = [];
  var hasInflectedSurface = false;

  function pushBase(text) {
    var val = String(text || '').trim();
    if (!val || baseSeen[val]) return;
    baseSeen[val] = true;
    bases.push(val);
  }

  function pushTags(list) {
    var items = normalizeDumpTextList(list);
    for (var i = 0; i < items.length; i++) {
      var val = items[i];
      if (tagSeen[val]) continue;
      tagSeen[val] = true;
      tags.push(val);
    }
  }

  function ingestOne(meta) {
    var item = meta || {};
    var surface = String(item.surface || '').trim();
    var base = String(item.morph_base || '').trim();
    var info = normalizeDumpTextList(item.morph_info);
    var inflected = !!item.is_inflected_surface || !!(surface && base && surface !== base);
    if (!base && !info.length && !inflected) return;
    if (base) pushBase(base);
    if (info.length) pushTags(info);
    if (inflected) hasInflectedSurface = true;
  }

  var groupedSource = [];
  if (Array.isArray(row.entry_groups_hover) && row.entry_groups_hover.length) {
    groupedSource = row.entry_groups_hover;
  } else if (Array.isArray(row.entry_groups) && row.entry_groups.length) {
    groupedSource = row.entry_groups;
  }

  if (groupedSource.length) {
    for (var gi = 0; gi < groupedSource.length; gi++) {
      var grp = groupedSource[gi] || {};
      var posGroups = Array.isArray(grp.pos_groups) ? grp.pos_groups : [];
      if (!posGroups.length) {
        var singleRow = {
          pos: grp.pos || '',
          morph_info: grp.morph_info || [],
          hangeul_forms: Array.isArray(grp.hangeul_forms) ? grp.hangeul_forms : []
        };
        if (isHanjaReadingLikeGroup(singleRow, rawLang)) continue;
        ingestOne({
          surface: grp.headword || row.surface_form || row.text || row.head || '',
          morph_base: grp.morph_base || row.morph_base || '',
          morph_info: grp.morph_info || row.morph_info || [],
          is_inflected_surface: !!grp.is_inflected_surface
        });
        continue;
      }
      for (var pi = 0; pi < posGroups.length; pi++) {
        var pg = posGroups[pi] || {};
        var groupedRow = {
          pos: pg.pos || grp.pos || '',
          morph_info: pg.morph_info || grp.morph_info || [],
          hangeul_forms: Array.isArray(pg.hangeul_forms) ? pg.hangeul_forms : (Array.isArray(grp.hangeul_forms) ? grp.hangeul_forms : [])
        };
        if (isHanjaReadingLikeGroup(groupedRow, rawLang)) continue;
        ingestOne({
          surface: pg.headword || grp.headword || row.surface_form || row.text || row.head || '',
          morph_base: pg.morph_base || grp.morph_base || row.morph_base || '',
          morph_info: pg.morph_info || grp.morph_info || row.morph_info || [],
          is_inflected_surface: !!pg.is_inflected_surface
        });
      }
    }
  } else {
    ingestOne({
      surface: row.surface_form || row.text || row.head || '',
      morph_base: row.morph_base || '',
      morph_info: row.morph_info || [],
      is_inflected_surface: false
    });
  }

  if (!hasInflectedSurface && !bases.length && !tags.length) return '';
  var parts = [];
  if (bases.length) parts.push('base: ' + bases.join(', '));
  if (tags.length) parts.push('tags: ' + tags.join('; '));
  if (!parts.length && hasInflectedSurface) parts.push('inflected form');
  return parts.length ? ('Morph: ' + parts.join(' | ')) : '';
}

function extractDumpHanjaTokens(raw) {
  var text = String(raw || '').trim();
  if (!text) return [];
  var matches = text.match(/[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]+/gu);
  return Array.isArray(matches) ? matches : [];
}

function collectDumpHanjaLine(entry, rawLang) {
  if (!isKoreanLanguageForDump(rawLang)) return '';
  var row = entry || {};
  var groupedSources = [];
  if (Array.isArray(row.entry_groups_hover) && row.entry_groups_hover.length) {
    groupedSources.push(row.entry_groups_hover);
  }
  if (Array.isArray(row.entry_groups_other) && row.entry_groups_other.length) {
    groupedSources.push(row.entry_groups_other);
  }
  if (!groupedSources.length && Array.isArray(row.entry_groups) && row.entry_groups.length) {
    groupedSources.push(row.entry_groups);
  }

  var seen = Object.create(null);
  var out = [];

  function pushTokens(list) {
    var src = Array.isArray(list) ? list : (list ? [list] : []);
    for (var i = 0; i < src.length; i++) {
      var tokens = extractDumpHanjaTokens(src[i]);
      for (var j = 0; j < tokens.length; j++) {
        var token = String(tokens[j] || '').trim();
        if (!token || seen[token]) continue;
        seen[token] = true;
        out.push(token);
      }
    }
  }

  for (var gs = 0; gs < groupedSources.length; gs++) {
    var groups = groupedSources[gs] || [];
    for (var gi = 0; gi < groups.length; gi++) {
      var grp = groups[gi] || {};
      var posGroups = Array.isArray(grp.pos_groups) ? grp.pos_groups : [];
      if (!posGroups.length) {
        var singleRow = {
          pos: grp.pos || '',
          morph_info: grp.morph_info || [],
          hangeul_forms: Array.isArray(grp.hangeul_forms) ? grp.hangeul_forms : []
        };
        if (!isHanjaReadingLikeGroup(singleRow, rawLang)) continue;
        pushTokens(grp.hanja_forms);
        pushTokens(grp.base_headword);
        pushTokens(grp.headword);
        continue;
      }
      for (var pi = 0; pi < posGroups.length; pi++) {
        var pg = posGroups[pi] || {};
        var groupedRow = {
          pos: pg.pos || grp.pos || '',
          morph_info: pg.morph_info || grp.morph_info || [],
          hangeul_forms: Array.isArray(pg.hangeul_forms) ? pg.hangeul_forms : (Array.isArray(grp.hangeul_forms) ? grp.hangeul_forms : [])
        };
        if (!isHanjaReadingLikeGroup(groupedRow, rawLang)) continue;
        pushTokens(pg.hanja_forms);
        pushTokens(pg.base_headword);
        pushTokens(pg.headword);
        pushTokens(grp.headword);
      }
    }
  }

  return out.length ? ('hanja: ' + out.join(' ')) : '';
}

function buildEntryLabel(piece, result) {
  var pieceText = String((piece && piece.text) || '').trim();
  var pieceHead = String((piece && piece.head) || '').trim();
  var resultHead = String((result && result.head) || '').trim();
  if (pieceText && pieceHead && pieceText !== pieceHead) return pieceText + ' -> ' + pieceHead;
  return pieceText || pieceHead || resultHead || '';
}

function collectVisibleEntryBlocks(result, rawLang) {
  var out = [];
  var row = result || {};
  var fillRows = Array.isArray(row.inspect_fill) ? row.inspect_fill : (Array.isArray(row.dict_fill) ? row.dict_fill : []);
  var knownFillCount = 0;
  for (var i = 0; i < fillRows.length; i++) {
    var piece = fillRows[i] || {};
    if (String(piece.source || '').toUpperCase() === 'UNKNOWN') continue;
    knownFillCount += 1;
    var pieceSenses = collectVisibleLinesForDumpEntry(piece, rawLang);
    if (!pieceSenses.length) continue;
    out.push({
      label: buildEntryLabel(piece, row),
      morph_note: collectDumpMorphNote(piece, rawLang),
      hanja_line: collectDumpHanjaLine(piece, rawLang),
      senses: pieceSenses
    });
  }
  if (knownFillCount) return out;
  if (String(row.source || '').toUpperCase() === 'UNKNOWN') return [];
  var rowSenses = collectVisibleLinesForDumpEntry(row, rawLang);
  if (!rowSenses.length) return [];
  out.push({
    label: buildEntryLabel(null, row),
    morph_note: collectDumpMorphNote(row, rawLang),
    hanja_line: collectDumpHanjaLine(row, rawLang),
    senses: rowSenses
  });
  return out;
}

function resolveLookupPayload(base) {
  var payload = clonePlainObject(base || {});
  if (Array.isArray(payload.debug_ui_results_by_seg)) {
    payload.results_by_seg = payload.debug_ui_results_by_seg.slice();
    if (Array.isArray(payload.debug_ui_results)) {
      payload.results = payload.debug_ui_results.slice();
    }
  }
  return Promise.resolve(payload);
}

function buildPlainTextDump(data) {
  return resolveLookupPayload(data).then(function(resolved) {
    var lang = normalizeLangCode((resolved && resolved.language) || data.language || '');
    var tokens = Array.isArray(data.trankit_tokens) ? data.trankit_tokens : [];
    var segments = Array.isArray(resolved && resolved.segments) ? resolved.segments : [];
    var results = Array.isArray(resolved && resolved.results_by_seg) ? resolved.results_by_seg : [];
    var hasLiveCapture = Array.isArray(resolved && resolved.debug_ui_results_by_seg);
    if (!hasLiveCapture) {
      return '[no live merged dictionary capture yet]\nreload the reader page so it picks up the latest client script, then run a fresh lookup';
    }
    var rowCount = Math.max(tokens.length, segments.length, results.length);
    var lines = [];

    for (var i = 0; i < rowCount; i++) {
      var tok = tokens[i] || {};
      var res = results[i] || {};
      var tokenText = String(tok.text || (i < segments.length ? segments[i] : '') || '').trim();
      if (!tokenText) continue;
      lines.push(tokenText);
      var blocks = collectVisibleEntryBlocks(res, lang);
      for (var bi = 0; bi < blocks.length; bi++) {
        var block = blocks[bi] || {};
        var label = String(block.label || '').trim();
        if (label) lines.push('  ' + label);
        var morphNote = String(block.morph_note || '').trim();
        if (morphNote) lines.push('    ' + morphNote);
        var hanjaLine = String(block.hanja_line || '').trim();
        if (hanjaLine) lines.push('    ' + hanjaLine);
        var senses = Array.isArray(block.senses) ? block.senses : [];
        for (var si = 0; si < senses.length; si++) {
          lines.push('    ' + String(senses[si] || ''));
        }
      }
      lines.push('');
    }
    while (lines.length && !String(lines[lines.length - 1] || '').trim()) lines.pop();
    return lines.join('\n');
  });
}

function renderDump(data, dumpText) {
  var ts = data._timestamp ? new Date(data._timestamp * 1000).toLocaleTimeString() : '?';
  document.getElementById('metaInfo').textContent = 'Lang: ' + String(data.language || '?') + ' | ' + ts;
  lastDumpText = String(dumpText || '');
  var html = '<div class="dump-wrap">';
  html += '<div class="dump-head"><span>Plain Text Dump</span><span class="meta">visible live-site senses only</span></div>';
  html += '<pre id="dumpBody">' + esc(lastDumpText) + '</pre>';
  html += '</div>';
  var content = document.getElementById('content');
  content.className = '';
  content.innerHTML = html;
}

function copyDump() {
  if (!lastDumpText) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(lastDumpText).catch(function() {});
  }
}

function fetchDump() {
  fetch('/debug/data', { cache: 'no-store' })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.ok) {
        document.getElementById('statusDot').classList.remove('live');
        document.getElementById('content').className = 'empty';
        document.getElementById('content').innerHTML = esc(data.error || 'No data');
        var filterInfo = document.getElementById('filterInfo');
        if (filterInfo) filterInfo.textContent = '';
        return;
      }
      if (data._timestamp && data._timestamp === lastTimestamp) return;
      lastTimestamp = data._timestamp;
      document.getElementById('statusDot').classList.add('live');
      buildPlainTextDump(data).then(function(dumpText) {
        renderDump(data, dumpText);
      }).catch(function(err) {
        document.getElementById('content').className = 'empty';
        document.getElementById('content').innerHTML = esc(String(err || 'Failed to build dump'));
      });
    })
    .catch(function() {
      document.getElementById('statusDot').classList.remove('live');
      document.getElementById('content').className = 'empty';
      document.getElementById('content').innerHTML = 'Failed to load debug data.';
    });
}

fetchDump();
</script>
</body>
</html>
"""

_DEBUG_SCORING_INFORMATION_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Scoring Information</title>
<style>
  :root { --bg: #1e1e2e; --fg: #cdd6f4; --surface: #313244; --border: #45475a;
          --accent: #89b4fa; --green: #a6e3a1; --red: #f38ba8; --yellow: #f9e2af;
          --peach: #fab387; --cyan: #89dceb; --mono: 'Cascadia Code', 'Fira Code', 'Consolas', monospace; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: var(--mono); font-size: 13px; background: var(--bg); color: var(--fg);
         padding: 16px; line-height: 1.6; }
  h1 { font-size: 16px; color: var(--accent); margin-bottom: 12px; display: flex; align-items: center; gap: 10px; }
  h1 .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--red); }
  h1 .dot.live { background: var(--green); }
  .meta { font-size: 11px; color: #6c7086; }
  .refresh-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
  .btn { background: var(--surface); color: var(--fg); border: 1px solid var(--border);
         padding: 4px 12px; border-radius: 4px; font-size: 12px; cursor: pointer;
         font-family: var(--mono); text-decoration: none; }
  .btn:hover { background: #3b3d52; }
  .btn.active { background: var(--accent); color: var(--bg); border-color: var(--accent); }
  .note { margin-bottom: 16px; padding: 10px 12px; background: #181825; border: 1px solid var(--border);
          border-radius: 6px; color: #a6adc8; }
  .empty { text-align: center; padding: 40px; color: #6c7086; border: 1px solid var(--border);
           border-radius: 6px; background: #181825; }
  .token-list { display: flex; flex-direction: column; gap: 14px; }
  .token-card { border: 1px solid var(--border); border-radius: 8px; background: #181825; overflow: hidden; }
  .token-head { display: flex; justify-content: space-between; gap: 12px; align-items: baseline;
                padding: 10px 12px; background: var(--surface); }
  .tok-text { font-size: 18px; font-weight: 700; }
  .tok-meta { padding: 10px 12px; border-top: 1px solid var(--border); }
  .minor { color: #6c7086; font-size: 11px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
  .chip { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 10px; font-weight: 700; }
  .chip.path-surface { background: #89b4fa33; color: var(--accent); }
  .chip.path-lemma { background: #a6e3a133; color: var(--green); }
  .chip.mode { background: #89dceb22; color: var(--cyan); }
  .chip.entry { background: #fab38722; color: var(--peach); }
  .chip.entry-muted { background: #6c708633; color: #a6adc8; }
  .chip.bad { background: #f38ba833; color: var(--red); }
  .chip.warn { background: #f9e2af33; color: var(--yellow); }
  .path-block { margin-top: 10px; padding: 10px 12px; border: 1px solid var(--border); border-radius: 6px; background: #1e1e2e; }
  .path-title { font-weight: 700; margin-bottom: 6px; }
  .fill-list { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
  .fill-row { padding: 7px 8px; border: 1px solid var(--border); border-radius: 6px; background: #181825; }
  .fill-head { font-weight: 700; }
  details { margin-top: 10px; }
  details summary { cursor: pointer; color: #a6adc8; }
  .trace-wrap { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
  .trace-step { border: 1px solid var(--border); border-radius: 6px; background: #1e1e2e; padding: 8px 10px; }
  .trace-step details { margin-top: 6px; }
  .trace-label { font-size: 11px; color: #a6adc8; text-transform: uppercase; letter-spacing: 0.5px; }
  .trace-selected { margin-top: 4px; }
  .reject-list { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
  .reject-item { padding: 7px 8px; border-radius: 6px; border: 1px solid var(--border); background: #181825; }
  .reject-item.boundary { border-left: 2px solid var(--yellow); }
  .reject-item.pos { border-left: 2px solid var(--red); }
  .trace-detail { margin-top: 4px; color: #a6adc8; font-size: 11px; }
  .decision-box { margin-top: 10px; padding: 10px 12px; border: 1px solid var(--border); border-radius: 6px; background: #1e1e2e; }
  .decision-line { margin-top: 4px; }
  .decision-label { color: #6c7086; margin-right: 8px; }
  .piece-summary { font-weight: 700; color: var(--fg); }
  .path-brief { margin-top: 8px; padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; background: #181825; }
  .compact-line { margin-top: 4px; white-space: pre-wrap; word-break: break-word; }
  .summary-table { width: 100%; border-collapse: collapse; margin-top: 6px; }
  .summary-table th { width: 92px; text-align: left; vertical-align: top; padding: 6px 8px 6px 0; color: #6c7086; font-size: 11px; font-weight: 600; }
  .summary-table td { padding: 6px 0; color: var(--fg); }
  .score-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 12px; }
  .score-table th { text-align: left; padding: 7px 8px; background: #1e1e2e; color: #a6adc8;
                    font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border); }
  .score-table td { padding: 7px 8px; border-top: 1px solid var(--border); vertical-align: top; }
  .score-table tr:hover td { background: #232436; }
  .score-table td.step-col, .score-table td.path-col, .score-table td.status-col { white-space: nowrap; }
  .score-table tr.status-selected td { background: #1b2b29; }
  .score-table tr.status-considered td { background: #1c2230; }
  .score-table tr.status-rejected td { background: #2a1d25; }
  .status-pill { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 10px; font-weight: 700; }
  .status-pill.selected { background: #a6e3a133; color: var(--green); }
  .status-pill.considered { background: #89b4fa33; color: var(--accent); }
  .status-pill.rejected { background: #f38ba833; color: var(--red); }
  .path-pill { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 10px; font-weight: 700; }
  .path-pill.chosen { background: #a6e3a133; color: var(--green); }
  .path-pill.other { background: #89b4fa33; color: var(--accent); }
  .path-pill.subword { background: #f9e2af33; color: var(--yellow); }
  .candidate-cell { font-weight: 700; }
  .detail-cell { color: #a6adc8; white-space: pre-wrap; word-break: break-word; }
  .path-section { margin-top: 12px; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; background: #1e1e2e; }
  .path-section-head { padding: 9px 10px; background: #25263a; border-bottom: 1px solid var(--border); }
  .path-head-top { display: flex; align-items: center; gap: 8px; font-weight: 700; }
  .path-head-meta { margin-top: 4px; color: #a6adc8; font-size: 11px; }
  .flow-table { width: 100%; border-collapse: collapse; }
  .flow-table th { text-align: left; padding: 7px 8px; background: #181825; color: #a6adc8;
                   font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border); }
  .flow-table td { padding: 8px; border-top: 1px solid var(--border); vertical-align: top; }
  .flow-table tr:hover td { background: #232436; }
  .flow-table td.step-col { white-space: nowrap; width: 96px; color: #a6adc8; }
  .flow-table td.selected-col { background: #1b2b29; }
  .flow-table td.considered-col { background: #1c2230; }
  .flow-table td.rejected-col { background: #2a1d25; }
  .cell-item { padding: 4px 0; }
  .cell-item + .cell-item { border-top: 1px dashed #45475a; }
  .cell-head { font-weight: 700; }
  .cell-sub { color: #a6adc8; font-size: 11px; margin-top: 2px; white-space: pre-wrap; word-break: break-word; }
  .step-main { font-weight: 700; color: var(--fg); }
  .step-sub { margin-top: 2px; font-size: 11px; color: #a6adc8; }
</style>
</head>
<body>

<h1><span class="dot" id="statusDot"></span> Scoring Information</h1>
<div class="refresh-bar">
  <button class="btn" onclick="fetchDebug()">Refresh</button>
  <button class="btn" id="autoBtn" onclick="toggleAuto()">Auto: OFF</button>
  <a class="btn" href="/debug">Main Debug</a>
  <a class="btn" href="/debug/sqlite">SQLite</a>
  <a class="btn" href="/debug/lemma_boundaries">Lemma Boundaries</a>
  <a class="btn" href="/debug/chatgpt_dump">ChatGPT Dump</a>
  <span class="meta" id="metaInfo"></span>
</div>

<div class="note">
  Single-pass DP with lemma promotion. When the lemma differs from the surface, lemma hints are passed to the DP.
  Candidates whose forms tables contain a lemma hint are <strong>promoted</strong> (hard override — they auto-win
  over non-promoted candidates). Among promoted candidates, the standard metric applies: fewer unknowns, fewer
  pieces, longer span. Row <code>start 0</code> is the token-level decision; later rows show continuation choices.
</div>

<div class="refresh-bar">
  <span class="meta">Filter:</span>
  <button class="btn active" data-scoring-filter="all" onclick="setScoringFilter('all')">All</button>
  <button class="btn" data-scoring-filter="exact" onclick="setScoringFilter('exact')">Exact matches</button>
  <button class="btn" data-scoring-filter="lemma" onclick="setScoringFilter('lemma')">Lemma overrides</button>
  <button class="btn" data-scoring-filter="greedy" onclick="setScoringFilter('greedy')">Greedy segmentation</button>
  <span class="meta" id="filterInfo"></span>
</div>

<div id="content" class="empty">No live scoring trace yet. Reload the reader page so it picks up the latest client script, then run a fresh lookup.</div>

<script>
var autoInterval = null;
var lastTimestamp = null;

function esc(s) {
  if (s == null) return '';
  var d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function toggleAuto() {
  if (autoInterval) {
    clearInterval(autoInterval);
    autoInterval = null;
    document.getElementById('autoBtn').textContent = 'Auto: OFF';
    document.getElementById('autoBtn').classList.remove('active');
  } else {
    autoInterval = setInterval(fetchDebug, 1500);
    document.getElementById('autoBtn').textContent = 'Auto: ON';
    document.getElementById('autoBtn').classList.add('active');
  }
}

function formatReason(reason) {
  return String(reason || '').replace(/_/g, ' ').trim();
}

function isPosRejectReason(reason) {
  var text = String(reason || '').trim();
  return text === 'xpos_pos_mismatch' || text === 'korean_ep_ef_disallow_였다';
}

function explainRejectReason(reason) {
  var text = String(reason || '').trim();
  if (text === 'crosses_lemma_boundary') return 'crosses lemma boundary';
  if (text === 'xpos_pos_mismatch') return 'POS filter vetoed it';
  if (text === 'korean_ep_ef_disallow_였다') return 'special Korean veto: 였다 is blocked for ep+ef';
  return formatReason(text || 'rejected');
}

function formatSpan(item) {
  var start = Number(item && item.start);
  var end = Number(item && item.end);
  if (!isFinite(start) || !isFinite(end)) return '';
  return start + ':' + end;
}

function renderEntryRefs(refs, muted) {
  var list = Array.isArray(refs) ? refs : [];
  if (!list.length) return '<div class="minor">No entry refs</div>';
  var cls = muted ? 'entry-muted' : 'entry';
  return '<div class="chips">' + list.map(function(ref) {
    return '<span class="chip ' + cls + '">' + esc(entryRefLabel(ref)) + '</span>';
  }).join('') + '</div>';
}

function entryRefLabel(ref) {
  var head = String((ref && ref.headword) || '').trim() || '?';
  var pos = String((ref && ref.pos_raw) || '').trim();
  return head + (pos ? (' [' + pos + ']') : '');
}

function summarizeEntryRefsInline(refs, maxItems) {
  var list = Array.isArray(refs) ? refs : [];
  if (!list.length) return 'none';
  var max = Number(maxItems) || 5;
  var out = [];
  for (var i = 0; i < list.length && i < max; i++) out.push(entryRefLabel(list[i]));
  if (list.length > max) out.push('+' + String(list.length - max) + ' more');
  return out.join(', ');
}

function summarizeEntryRefsCompact(refs) {
  var list = Array.isArray(refs) ? refs : [];
  if (!list.length) return 'none';
  var byPos = Object.create(null);
  var posOrder = [];
  for (var i = 0; i < list.length; i++) {
    var ref = list[i] || {};
    var pos = String(ref.pos_raw || '?').trim() || '?';
    var head = String(ref.headword || '?').trim() || '?';
    if (!byPos[pos]) {
      byPos[pos] = { heads: Object.create(null), order: [] };
      posOrder.push(pos);
    }
    if (!byPos[pos].heads[head]) {
      byPos[pos].heads[head] = 0;
      byPos[pos].order.push(head);
    }
    byPos[pos].heads[head] += 1;
  }
  var chunks = [];
  for (var pi = 0; pi < posOrder.length; pi++) {
    var posKey = posOrder[pi];
    var bucket = byPos[posKey];
    var heads = [];
    for (var hi = 0; hi < bucket.order.length; hi++) {
      var headKey = bucket.order[hi];
      var count = bucket.heads[headKey] || 0;
      heads.push(headKey + (count > 1 ? ('×' + String(count)) : ''));
    }
    chunks.push(posKey + ': ' + heads.join(', '));
  }
  return chunks.join('; ');
}

function renderFillPreview(summary) {
  var fills = Array.isArray(summary && summary.fills) ? summary.fills : [];
  if (!fills.length) return '<div class="minor">No fill pieces</div>';
  return '<div class="fill-list">' + fills.map(function(fill) {
    var text = String((fill && fill.text) || '').trim();
    var head = String((fill && fill.head) || '').trim();
    var source = String((fill && fill.source) || '').trim();
    var pos = String((fill && fill.pos) || '').trim();
    var label = text;
    if (text && head && text !== head) label += ' -> ' + head;
    else if (!label) label = head || '?';
    var html = '<div class="fill-row">';
    html += '<div class="fill-head">' + esc(label) + '</div>';
    html += '<div class="chips">';
    if (source) html += '<span class="chip mode">' + esc(source) + '</span>';
    if (pos) html += '<span class="chip mode">' + esc(pos) + '</span>';
    if (fill && fill.xpos_hint) html += '<span class="chip warn">' + esc('xpos=' + fill.xpos_hint) + '</span>';
    if (fill && fill.lemma_upos_hint) html += '<span class="chip warn">' + esc('lemma_upos=' + fill.lemma_upos_hint) + '</span>';
    if (fill && fill.lemma_xpos_hint) html += '<span class="chip warn">' + esc('lemma_xpos=' + fill.lemma_xpos_hint) + '</span>';
    if (fill && fill.lemma_promoted) html += '<span class="chip path-surface">' + esc('promoted=' + fill.lemma_promoted) + '</span>';
    html += '<span class="chip mode">' + esc(String((Array.isArray(fill && fill.entry_refs) ? fill.entry_refs.length : 0)) + ' entries') + '</span>';
    html += '</div>';
    if (Array.isArray(fill && fill.entry_refs) && fill.entry_refs.length) {
      html += '<details><summary>Entry refs</summary>' + renderEntryRefs(fill && fill.entry_refs, false) + '</details>';
    }
    html += '</div>';
    return html;
  }).join('') + '</div>';
}

function summarizeFillPieces(summary) {
  var fills = Array.isArray(summary && summary.fills) ? summary.fills : [];
  var labels = [];
  for (var i = 0; i < fills.length; i++) {
    var fill = fills[i] || {};
    var text = String(fill.text || '').trim();
    var head = String(fill.head || '').trim();
    var source = String(fill.source || '').trim().toUpperCase();
    if (source === 'UNKNOWN') {
      labels.push(text || head || '?');
      continue;
    }
    labels.push(text || head || '?');
  }
  return labels.length ? labels.join(' + ') : '[none]';
}

function sameFillPreview(a, b) {
  var left = Array.isArray(a && a.fills) ? a.fills : [];
  var right = Array.isArray(b && b.fills) ? b.fills : [];
  if (left.length !== right.length) return false;
  for (var i = 0; i < left.length; i++) {
    var lf = left[i] || {};
    var rf = right[i] || {};
    if (String(lf.text || '') !== String(rf.text || '')) return false;
    if (summarizeEntryRefsInline(lf.entry_refs, 99) !== summarizeEntryRefsInline(rf.entry_refs, 99)) return false;
  }
  return true;
}

function collectXposHints(summary) {
  var fills = Array.isArray(summary && summary.fills) ? summary.fills : [];
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < fills.length; i++) {
    var hint = String((fills[i] && fills[i].xpos_hint) || '').trim();
    if (!hint || seen[hint]) continue;
    seen[hint] = true;
    out.push(hint);
  }
  return out;
}

function summarizeOtherPath(chosenSummary, otherSummary, chosenPath) {
  if (!otherSummary) return 'none';
  var otherPath = chosenPath === 'lemma' ? 'surface' : 'lemma';
  var parts = [otherPath + (otherSummary.mode ? (' ' + otherSummary.mode) : '')];
  var chosenSplit = summarizeFillPieces(chosenSummary);
  var otherSplit = summarizeFillPieces(otherSummary);
  parts.push(otherSplit === chosenSplit ? 'same split' : ('split=' + otherSplit));
  if (sameFillPreview(chosenSummary, otherSummary)) {
    parts.push('same refs');
  }
  var hints = collectXposHints(otherSummary);
  if (hints.length) parts.push('xpos=' + hints.join(', '));
  return parts.join(' | ');
}

function pathDisplayName(path) {
  var key = String(path || '').trim().toLowerCase();
  if (key === 'lemma') return 'Lemma path';
  if (key === 'surface') return 'Surface path';
  if (key === 'chosen') return 'Chosen path';
  if (key === 'other') return 'Other path';
  if (key === 'subword') return 'Subword check';
  return key || 'Path';
}

function summarizeScoreResult(item) {
  var unknown = (item && item.score_unknown != null) ? String(item.score_unknown) : '?';
  var pieces = (item && item.score_pieces != null) ? String(item.score_pieces) : '?';
  var promoted = (item && item.score_promoted != null) ? String(item.score_promoted) : '0';
  var promotedHere = Number(item && item.score_promoted_here != null ? item.score_promoted_here : 0);
  return 'current-promoted ' + (promotedHere > 0 ? 'yes' : 'no') +
    ', promoted-total ' + promoted +
    ', unknown ' + unknown +
    ', pieces ' + pieces;
}

function summarizeEntryPosList(refs) {
  var list = Array.isArray(refs) ? refs : [];
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < list.length; i++) {
    var pos = String((list[i] && list[i].pos_raw) || '').trim().toLowerCase();
    if (!pos || seen[pos]) continue;
    seen[pos] = true;
    out.push(pos);
  }
  return out.join(', ');
}

function formatDecisionReason(reason) {
  var text = formatReason(reason);
  if (!text) return '';
  if (text === 'tie prefers lemma') return 'tie, so lemma path wins';
  if (text === 'tie prefers surface exact') return 'tie, so exact surface path wins';
  if (text === 'lemma same as surface') return 'lemma and surface are the same';
  if (text === 'lemma unresolved') return 'lemma path failed, so surface path wins';
  if (text === 'surface unresolved') return 'surface path failed, so lemma path wins';
  if (text === 'surface has unknown') return 'lemma path wins because surface leaves unknown text';
  if (text === 'lemma has unknown') return 'surface path wins because lemma leaves unknown text';
  if (text === 'lemma has fewer matches') return 'lemma path wins with a smaller split';
  if (text === 'surface has fewer matches') return 'surface path wins with a smaller split';
  return text;
}

function getExactEvents(summary) {
  return Array.isArray(summary && summary.exact_events) ? summary.exact_events : [];
}

function countExactVetoes(summary) {
  var events = getExactEvents(summary);
  var count = 0;
  for (var i = 0; i < events.length; i++) {
    if (events[i] && events[i].vetoed) count += 1;
  }
  return count;
}

function summarizeExactEvents(summary) {
  var events = getExactEvents(summary);
  if (!events.length) return 'none';
  var bits = [];
  for (var i = 0; i < events.length; i++) {
    var event = events[i] || {};
    var label = String(event.display_text || event.lookup_text || '?').trim() || '?';
    if (event.vetoed) {
      bits.push(
        label + ' vetoed' +
        (Array.isArray(event.xpos_tags) && event.xpos_tags.length ? (' xpos=' + event.xpos_tags.join('+')) : '') +
        (Array.isArray(event.allowed_pos) && event.allowed_pos.length ? (' allow=' + event.allowed_pos.join('/')) : '')
      );
    } else {
      bits.push(label + ' accepted');
    }
  }
  return bits.join(' | ');
}

function summarizeExactDecision(summary) {
  var events = getExactEvents(summary);
  if (!events.length) return '';
  var vetoed = 0;
  var accepted = 0;
  for (var i = 0; i < events.length; i++) {
    if (events[i] && events[i].vetoed) vetoed += 1;
    else accepted += 1;
  }
  if (vetoed && !accepted) return ' | exact vetoed';
  if (accepted && !vetoed) return ' | exact accepted';
  return ' | exact mixed';
}

function renderCompactPieceLines(summary) {
  var fills = Array.isArray(summary && summary.fills) ? summary.fills : [];
  if (!fills.length) return '<div class="decision-line"><span class="decision-label">Pieces</span><span class="minor">none</span></div>';
  return fills.map(function(fill, idx) {
    var label = String((fill && fill.text) || (fill && fill.head) || '?').trim() || '?';
    var bits = [];
    if (fill && fill.source) bits.push(String(fill.source));
    if (fill && fill.pos) bits.push(String(fill.pos));
    if (fill && fill.xpos_hint) bits.push(String(fill.xpos_hint));
    var line = '<div class="decision-line"><span class="decision-label">' + esc(idx === 0 ? 'Pieces' : '') + '</span>';
    line += '<strong>' + esc(label) + '</strong>';
    if (bits.length) line += ' <span class="minor">(' + esc(bits.join(' | ')) + ')</span>';
    line += ' <span class="minor">| ' + esc(summarizeEntryRefsCompact(fill && fill.entry_refs)) + '</span></div>';
    return line;
  }).join('');
}

function summarizeFillGroupCompact(summary) {
  var fills = Array.isArray(summary && summary.fills) ? summary.fills : [];
  if (!fills.length) return '[none]';
  return fills.map(function(fill) {
    var label = String((fill && fill.text) || (fill && fill.head) || '?').trim() || '?';
    var meta = [];
    if (fill && fill.source) meta.push(String(fill.source));
    if (fill && fill.pos) meta.push(String(fill.pos));
    if (fill && fill.xpos_hint) meta.push(String(fill.xpos_hint));
    var refs = summarizeEntryRefsCompact(fill && fill.entry_refs);
    return label + (meta.length ? ('[' + meta.join('|') + ']') : '') + '{' + refs + '}';
  }).join(' + ');
}

function collectGreedyCompact(dpDebug, out) {
  var target = out || {
    selected: [],
    boundary: [],
    pos: [],
    selected_seen: Object.create(null),
    boundary_seen: Object.create(null),
    pos_seen: Object.create(null)
  };
  if (!dpDebug || typeof dpDebug !== 'object') return target;
  if (dpDebug.kind === 'merged') {
    var parts = Array.isArray(dpDebug.parts) ? dpDebug.parts : [];
    for (var pi = 0; pi < parts.length; pi++) collectGreedyCompact(parts[pi] && parts[pi].dp_debug, target);
    return target;
  }
  var steps = Array.isArray(dpDebug.steps) ? dpDebug.steps : [];
  for (var si = 0; si < steps.length; si++) {
    var step = steps[si] || {};
    var selected = step.selected || null;
    if (selected) {
      var skey = String(step.index != null ? step.index : si) + '|' + String(selected.piece || '');
      if (!target.selected_seen[skey]) {
        target.selected_seen[skey] = true;
        target.selected.push(String(step.index != null ? step.index : si) + ':' + String(selected.piece || '?'));
      }
    }
    var rejected = Array.isArray(step.rejected) ? step.rejected : [];
    for (var ri = 0; ri < rejected.length; ri++) {
      var item = rejected[ri] || {};
      var key = String(item.reason || '') + '|' + String(item.start || 0) + '|' + String(item.end || 0) + '|' + String(item.piece || '');
      if (String(item.reason || '') === 'crosses_lemma_boundary') {
        if (target.boundary_seen[key]) continue;
        target.boundary_seen[key] = true;
        target.boundary.push(String(item.piece || '?') + formatSpan(item));
      } else if (String(item.reason || '') === 'xpos_pos_mismatch') {
        if (target.pos_seen[key]) continue;
        target.pos_seen[key] = true;
        target.pos.push(
          String(item.piece || '?') + formatSpan(item) +
          '{x=' + String((Array.isArray(item.xpos_tags) ? item.xpos_tags.join('+') : '')) +
          ';allow=' + String((Array.isArray(item.allowed_pos) ? item.allowed_pos.join('/') : '')) +
          ';cand=' + summarizeEntryRefsCompact(item && item.entry_refs) + '}'
        );
      }
    }
  }
  return target;
}

function summarizeGreedyCompact(dpDebug) {
  var info = collectGreedyCompact(dpDebug, null);
  if (!info.selected.length && !info.boundary.length && !info.pos.length) return 'none';
  var parts = [];
  if (info.selected.length) parts.push('sel ' + info.selected.join(' '));
  parts.push('bnd ' + (info.boundary.length ? info.boundary.join(' ') : '-'));
  parts.push('pos ' + (info.pos.length ? info.pos.join(' ') : '-'));
  return parts.join(' | ');
}

function sameCandidateTrace(a, b) {
  return JSON.stringify(a || []) === JSON.stringify(b || []);
}

function sameCandidateItem(a, b) {
  var left = a || {};
  var right = b || {};
  return String(left.piece || '') === String(right.piece || '') &&
    Number(left.start || 0) === Number(right.start || 0) &&
    Number(left.end || 0) === Number(right.end || 0);
}

function compactAcceptedCandidate(item) {
  var row = item || {};
  var piece = String(row.piece || '?');
  var refs = summarizeEntryRefsCompact(row.entry_refs);
  var xpos = Array.isArray(row.xpos_tags) && row.xpos_tags.length ? (';x=' + row.xpos_tags.join('+')) : '';
  var promo = row.lemma_promoted ? (';PROMOTED=' + String(row.lemma_promoted)) : '';
  var lUpos = (row.lemma_promoted && row.lemma_promoted_upos) ? (';lu=' + String(row.lemma_promoted_upos)) : '';
  var lXpos = (row.lemma_promoted && row.lemma_promoted_xpos) ? (';lx=' + String(row.lemma_promoted_xpos)) : '';
  return piece + '{' + refs + xpos + promo + lUpos + lXpos + '}';
}

function compactRejectedCandidate(item) {
  var row = item || {};
  var piece = String(row.piece || '?');
  var reason = String(row.reason || '').trim();
  if (reason === 'crosses_lemma_boundary') {
    return piece + '{boundary}';
  }
  if (reason === 'xpos_pos_mismatch') {
    var xpos = Array.isArray(row.xpos_tags) && row.xpos_tags.length ? row.xpos_tags.join('+') : '';
    var allowed = Array.isArray(row.allowed_pos) && row.allowed_pos.length ? row.allowed_pos.join('/') : '';
    return piece + '{pos x=' + xpos + ';allow=' + allowed + ';cand=' + summarizeEntryRefsCompact(row.entry_refs) + '}';
  }
  return piece + '{' + formatReason(reason || 'rejected') + '}';
}

function buildCandidateTraceLines(dpDebug, prefix) {
  var lines = [];
  var pre = String(prefix || '');
  if (!dpDebug || typeof dpDebug !== 'object') return lines;
  if (dpDebug.kind === 'merged') {
    var parts = Array.isArray(dpDebug.parts) ? dpDebug.parts : [];
    for (var pi = 0; pi < parts.length; pi++) {
      var part = parts[pi] || {};
      var fills = Array.isArray(part.fills) ? part.fills : [];
      var label = fills.map(function(fill) {
        return String((fill && fill.text) || (fill && fill.head) || '').trim();
      }).filter(Boolean).join('+') || ('part' + String(pi + 1));
      var partLines = buildCandidateTraceLines(part.dp_debug, pre + 'p' + String(pi + 1) + '[' + label + '] ');
      for (var pli = 0; pli < partLines.length; pli++) lines.push(partLines[pli]);
    }
    return lines;
  }
  var steps = Array.isArray(dpDebug.steps) ? dpDebug.steps : [];
  for (var si = 0; si < steps.length; si++) {
    var step = steps[si] || {};
    var bits = [];
    var selected = step.selected || null;
    if (selected) {
      if (String(selected.kind || '') === 'known') {
        bits.push('sel ' + compactAcceptedCandidate(selected));
      } else {
        bits.push('sel ' + String(selected.piece || '?') + '{unknown}');
      }
    }
    var accepted = Array.isArray(step.accepted) ? step.accepted : [];
    var kept = [];
    for (var ai = 0; ai < accepted.length; ai++) {
      var acc = accepted[ai] || {};
      if (selected && sameCandidateItem(acc, selected)) continue;
      kept.push(compactAcceptedCandidate(acc));
    }
    if (kept.length) bits.push('keep ' + kept.join(' ; '));
    var rejected = Array.isArray(step.rejected) ? step.rejected : [];
    if (rejected.length) {
      var rejBits = [];
      for (var ri = 0; ri < rejected.length; ri++) rejBits.push(compactRejectedCandidate(rejected[ri]));
      bits.push('rej ' + rejBits.join(' ; '));
    }
    if (!bits.length) continue;
    lines.push(pre + 'i' + String(step.index != null ? step.index : si) + ' ' + bits.join(' | '));
  }
  return lines;
}

function summarizeChosenPieces(summary) {
  var fills = Array.isArray(summary && summary.fills) ? summary.fills : [];
  if (!fills.length) return '[none]';
  var out = [];
  for (var i = 0; i < fills.length; i++) {
    var fill = fills[i] || {};
    var label = String((fill.text) || (fill.head) || '?').trim() || '?';
    out.push(label + '{' + summarizeEntryRefsCompact(fill.entry_refs) + '}');
  }
  return out.join(' + ');
}

function candidateSpanLabel(item) {
  var piece = String((item && item.piece) || '?').trim() || '?';
  var span = formatSpan(item);
  return span ? (piece + ' (' + span + ')') : piece;
}

function candidateAcceptedDetail(item) {
  var row = item || {};
  var parts = [];
  if (String(row.kind || '') !== 'known') return 'unknown fallback';
  if (row.lemma_promoted) {
    parts.push('LEMMA PROMOTED via "' + String(row.lemma_promoted) + '"');
    if (row.lemma_promoted_headword) parts.push('hw: ' + String(row.lemma_promoted_headword));
    if (row.lemma_promoted_upos) parts.push('lemma_upos: ' + String(row.lemma_promoted_upos));
    if (row.lemma_promoted_xpos) parts.push('lemma_xpos: ' + String(row.lemma_promoted_xpos));
  }
  parts.push('score: ' + summarizeScoreResult(row));
  var posText = summarizeEntryPosList(row.entry_refs);
  if (posText) parts.push('pos: ' + posText);
  if (Array.isArray(row.xpos_tags) && row.xpos_tags.length) parts.push('xpos: ' + row.xpos_tags.join('+'));
  return parts.join('\n');
}

function candidateRejectedDetail(item) {
  var row = item || {};
  return explainRejectReason(row.reason || 'rejected');
}

function buildAcceptedLossReason(item, selected) {
  var row = item || {};
  var winner = selected || null;
  if (!winner) return 'ranked below the selected candidate';
  var winnerLabel = candidateSpanLabel(winner);
  var winnerPromotedHere = Number(winner.score_promoted_here || 0);
  var rowPromotedHere = Number(row.score_promoted_here || 0);
  if (winnerPromotedHere !== rowPromotedHere) {
    if (winnerPromotedHere > rowPromotedHere) return 'winner is lemma-promoted and this candidate is not';
    return 'is lemma-promoted but lost on other criteria to ' + winnerLabel;
  }
  var rowSpan = Number((row.end || 0) - (row.start || 0));
  var winnerSpan = Number((winner.end || 0) - (winner.start || 0));
  if (winnerPromotedHere > 0 && isFinite(rowSpan) && isFinite(winnerSpan) && rowSpan !== winnerSpan) {
    if (winnerSpan > rowSpan) return 'shorter promoted span than ' + winnerLabel;
    return 'longer promoted span but lost on other criteria to ' + winnerLabel;
  }
  var winnerPromoted = Number(winner.score_promoted || 0);
  var rowPromoted = Number(row.score_promoted || 0);
  if (winnerPromoted !== rowPromoted) {
    if (winnerPromoted > rowPromoted) return 'winner preserves more lemma-promoted continuation than this candidate';
    return 'preserves more lemma-promoted continuation but lost on other criteria to ' + winnerLabel;
  }
  var rowUnknown = Number(row.score_unknown);
  var winnerUnknown = Number(winner.score_unknown);
  if (isFinite(rowUnknown) && isFinite(winnerUnknown) && rowUnknown !== winnerUnknown) {
    return 'more unknown text than ' + winnerLabel;
  }
  var rowPieces = Number(row.score_pieces);
  var winnerPieces = Number(winner.score_pieces);
  if (isFinite(rowPieces) && isFinite(winnerPieces) && rowPieces !== winnerPieces) {
    return 'uses more pieces than ' + winnerLabel;
  }
  if (isFinite(rowSpan) && isFinite(winnerSpan) && rowSpan !== winnerSpan) {
    return 'shorter than ' + winnerLabel + ' on tie-break';
  }
  return 'ranked below ' + winnerLabel;
}

function collectFinalPathStarts(dpDebug) {
  var out = Object.create(null);
  if (!dpDebug || typeof dpDebug !== 'object' || dpDebug.kind === 'merged') return out;
  var steps = Array.isArray(dpDebug.steps) ? dpDebug.steps : [];
  var stepByIndex = Object.create(null);
  var wordLength = String(dpDebug.word || '').length;
  for (var i = 0; i < steps.length; i++) {
    var step = steps[i] || {};
    var idx = (step.index != null) ? Number(step.index) : i;
    if (isFinite(idx)) stepByIndex[idx] = step;
  }
  var cursor = 0;
  var guard = 0;
  while (guard < (wordLength + 5)) {
    guard += 1;
    var current = stepByIndex[cursor];
    if (!current || !current.selected) break;
    out[cursor] = true;
    var next = Number(current.selected.end);
    if (!isFinite(next) || next <= cursor) break;
    cursor = next;
    if (cursor >= wordLength) break;
  }
  return out;
}

function collectFinalPathSegments(dpDebug) {
  var out = [];
  if (!dpDebug || typeof dpDebug !== 'object' || dpDebug.kind === 'merged') return out;
  var steps = Array.isArray(dpDebug.steps) ? dpDebug.steps : [];
  var stepByIndex = Object.create(null);
  var wordLength = String(dpDebug.word || '').length;
  for (var i = 0; i < steps.length; i++) {
    var step = steps[i] || {};
    var idx = (step.index != null) ? Number(step.index) : i;
    if (isFinite(idx)) stepByIndex[idx] = step;
  }
  var cursor = 0;
  var guard = 0;
  while (guard < (wordLength + 5)) {
    guard += 1;
    var current = stepByIndex[cursor];
    if (!current || !current.selected) break;
    var selected = current.selected || {};
    var next = Number(selected.end);
    if (!isFinite(next) || next <= cursor) break;
    out.push({
      start: cursor,
      end: next,
      label: candidateSpanLabel(selected)
    });
    cursor = next;
    if (cursor >= wordLength) break;
  }
  return out;
}

function explainCoveredByFinalPath(startIndex, finalSegments) {
  var idx = Number(startIndex);
  var segments = Array.isArray(finalSegments) ? finalSegments : [];
  for (var i = 0; i < segments.length; i++) {
    var seg = segments[i] || {};
    var start = Number(seg.start);
    var end = Number(seg.end);
    if (!isFinite(start) || !isFinite(end)) continue;
    if (idx > start && idx < end) return 'covered by final path piece ' + String(seg.label || '?');
  }
  return 'not used by the final path';
}

function buildDisplayItem(head, detail) {
  return {
    _display_head: String(head || ''),
    _display_detail: String(detail || '')
  };
}

function collectCandidateTableRows(dpDebug, pathLabel, rows, partLabel) {
  var out = Array.isArray(rows) ? rows : [];
  var path = String(pathLabel || '');
  var part = String(partLabel || '');
  if (!dpDebug || typeof dpDebug !== 'object') return out;
  if (dpDebug.kind === 'merged') {
    var parts = Array.isArray(dpDebug.parts) ? dpDebug.parts : [];
    for (var pi = 0; pi < parts.length; pi++) {
      var partRow = parts[pi] || {};
      var fills = Array.isArray(partRow.fills) ? partRow.fills : [];
      var fillLabel = fills.map(function(fill) {
        return String((fill && fill.text) || (fill && fill.head) || '').trim();
      }).filter(Boolean).join('+') || ('part' + String(pi + 1));
      collectCandidateTableRows(partRow.dp_debug, path, out, 'p' + String(pi + 1) + ':' + fillLabel);
    }
    return out;
  }
  var steps = Array.isArray(dpDebug.steps) ? dpDebug.steps : [];
  for (var si = 0; si < steps.length; si++) {
    var step = steps[si] || {};
    var idx = String(step.index != null ? step.index : si);
    var stepLabel = part ? (part + ' / i' + idx) : ('i' + idx);
    var selected = step.selected || null;
    if (selected) {
      out.push({
        path: path,
        step: stepLabel,
        status: 'selected',
        candidate: candidateSpanLabel(selected),
        detail: (String(selected.kind || '') === 'known') ? candidateAcceptedDetail(selected) : 'unknown fallback'
      });
    }
    var accepted = Array.isArray(step.accepted) ? step.accepted : [];
    for (var ai = 0; ai < accepted.length; ai++) {
      var acc = accepted[ai] || {};
      if (selected && sameCandidateItem(acc, selected)) continue;
      out.push({
        path: path,
        step: stepLabel,
        status: 'considered',
        candidate: candidateSpanLabel(acc),
        detail: candidateAcceptedDetail(acc)
      });
    }
    var rejected = Array.isArray(step.rejected) ? step.rejected : [];
    for (var ri = 0; ri < rejected.length; ri++) {
      var rej = rejected[ri] || {};
      out.push({
        path: path,
        step: stepLabel,
        status: 'rejected',
        candidate: candidateSpanLabel(rej),
        detail: candidateRejectedDetail(rej)
      });
    }
  }
  return out;
}

function renderCandidateTable(rows) {
  var list = Array.isArray(rows) ? rows : [];
  if (!list.length) return '<div class="minor">No candidate trace.</div>';
  var html = '<table class="score-table"><thead><tr><th>Path</th><th>Step</th><th>Status</th><th>Candidate</th><th>Detail</th></tr></thead><tbody>';
  for (var i = 0; i < list.length; i++) {
    var row = list[i] || {};
    var path = String(row.path || '').trim();
    var status = String(row.status || '').trim();
    html += '<tr class="status-' + esc(status) + '">';
    html += '<td class="path-col"><span class="path-pill ' + esc(path) + '">' + esc(path || '?') + '</span></td>';
    html += '<td class="step-col">' + esc(String(row.step || '')) + '</td>';
    html += '<td class="status-col"><span class="status-pill ' + esc(status) + '">' + esc(status || '?') + '</span></td>';
    html += '<td class="candidate-cell">' + esc(String(row.candidate || '')) + '</td>';
    html += '<td class="detail-cell">' + esc(String(row.detail || '')) + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

function renderFlowCellItems(items, kind) {
  var list = Array.isArray(items) ? items : [];
  if (!list.length) return '<div class="minor">-</div>';
  var html = '';
  for (var i = 0; i < list.length; i++) {
    var item = list[i] || {};
    var head = (item._display_head != null) ? String(item._display_head) : candidateSpanLabel(item);
    var sub = (item._display_detail != null)
      ? String(item._display_detail)
      : ((kind === 'rejected') ? candidateRejectedDetail(item) : candidateAcceptedDetail(item));
    if (kind === 'selected' && item._display_detail == null && String(item.kind || '') !== 'known') sub = 'unknown fallback';
    html += '<div class="cell-item">';
    html += '<div class="cell-head">' + esc(head) + '</div>';
    html += '<div class="cell-sub">' + esc(sub) + '</div>';
    html += '</div>';
  }
  return html;
}

function renderExactEventTable(section) {
  var summary = section && section.summary ? section.summary : null;
  var events = getExactEvents(summary);
  if (!events.length) return '';
  var path = String((section && section.path) || '');
  var title = String((section && section.title) || pathDisplayName(path));
  var html = '<div class="path-section">';
  html += '<div class="path-section-head">';
  html += '<div class="path-head-top"><span class="path-pill ' + esc(path) + '">' + esc(pathDisplayName(path)) + '</span><span>' + esc(title + ' exact lookup') + '</span></div>';
  html += '<div class="path-head-meta">Exact-hit gate before greedy. Accepted exact hits continue; vetoed exact hits fall through to greedy.</div>';
  html += '</div>';
  html += '<table class="flow-table"><thead><tr><th>Exact lookup</th><th>Result</th><th>Detail</th></tr></thead><tbody>';
  for (var i = 0; i < events.length; i++) {
    var event = events[i] || {};
    var lookupLabel = String(event.display_text || event.lookup_text || '?').trim() || '?';
    var lookupText = String(event.lookup_text || '').trim();
    var detailBits = [];
    if (lookupText && lookupText !== lookupLabel) detailBits.push('lookup: ' + lookupText);
    var posText = summarizeEntryPosList(event.entry_refs);
    if (posText) detailBits.push('pos: ' + posText);
    if (Array.isArray(event.xpos_tags) && event.xpos_tags.length) detailBits.push('xpos: ' + event.xpos_tags.join('+'));
    if (Array.isArray(event.allowed_pos) && event.allowed_pos.length) detailBits.push('allowed POS: ' + event.allowed_pos.join('/'));
    if (event.vetoed && event.reason) detailBits.push('reason: ' + explainRejectReason(event.reason));
    html += '<tr>';
    html += '<td class="step-col"><div class="step-main">' + esc(lookupLabel) + '</div></td>';
    html += '<td class="' + (event.vetoed ? 'rejected-col' : 'selected-col') + '"><div class="cell-item"><div class="cell-head">' + esc(event.vetoed ? 'vetoed' : 'accepted') + '</div><div class="cell-sub">' + esc(event.vetoed ? 'rejected before greedy' : 'kept as exact candidate') + '</div></div></td>';
    html += '<td class="considered-col"><div class="cell-item"><div class="cell-sub">' + esc(detailBits.join('\n')) + '</div></div></td>';
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  return html;
}

function renderDecisionTable(dpDebug, pathLabel, partLabel) {
  var section = (pathLabel && typeof pathLabel === 'object') ? pathLabel : { path: String(pathLabel || '') };
  var path = String(section.path || '');
  var part = String(partLabel || '');
  if (!dpDebug || typeof dpDebug !== 'object') return '';
  if (dpDebug.kind === 'merged') {
    var mergedHtml = '';
    var parts = Array.isArray(dpDebug.parts) ? dpDebug.parts : [];
    for (var pi = 0; pi < parts.length; pi++) {
      var partRow = parts[pi] || {};
      var fills = Array.isArray(partRow.fills) ? partRow.fills : [];
      var fillLabel = fills.map(function(fill) {
        return String((fill && fill.text) || (fill && fill.head) || '').trim();
      }).filter(Boolean).join(' + ') || ('part ' + String(pi + 1));
      mergedHtml += renderDecisionTable(partRow.dp_debug, section, fillLabel);
    }
    return mergedHtml;
  }
  var steps = Array.isArray(dpDebug.steps) ? dpDebug.steps : [];
  if (!steps.length) return '';
  var title = String(section.title || pathDisplayName(path));
  var finalPathStarts = collectFinalPathStarts(dpDebug);
  var finalPathSegments = collectFinalPathSegments(dpDebug);
  if (part) title += ' | ' + part;
  var html = '<div class="path-section">';
  html += '<div class="path-section-head">';
  html += '<div class="path-head-top"><span class="path-pill ' + esc(path) + '">' + esc(pathDisplayName(path)) + '</span><span>' + esc(title) + '</span></div>';
  html += '</div>';
  html += '<table class="flow-table"><thead><tr><th>Start</th><th>Chosen path</th><th>Not chosen</th></tr></thead><tbody>';
  for (var si = 0; si < steps.length; si++) {
    var step = steps[si] || {};
    var selected = step.selected || null;
    var selectedInFinalPath = !!finalPathStarts[(step.index != null) ? Number(step.index) : si];
    var chosenItems = (selected && selectedInFinalPath) ? [selected] : [];
    var notChosen = [];
    var accepted = Array.isArray(step.accepted) ? step.accepted : [];
    for (var ai = 0; ai < accepted.length; ai++) {
      var acc = accepted[ai] || {};
      if (selected && sameCandidateItem(acc, selected)) continue;
      notChosen.push(buildDisplayItem(
        candidateSpanLabel(acc),
        buildAcceptedLossReason(acc, selected)
      ));
    }
    var rejected = Array.isArray(step.rejected) ? step.rejected : [];
    for (var ri = 0; ri < rejected.length; ri++) {
      var rej = rejected[ri] || {};
      notChosen.push(buildDisplayItem(candidateSpanLabel(rej), candidateRejectedDetail(rej)));
    }
    if (selected && !selectedInFinalPath) {
      notChosen.unshift(buildDisplayItem(
        candidateSpanLabel(selected),
        explainCoveredByFinalPath((step.index != null) ? Number(step.index) : si, finalPathSegments)
      ));
    }
    if (!chosenItems.length && !notChosen.length) continue;
    var stepIndex = (step.index != null ? step.index : si);
    var stepWord = String(dpDebug.word || '');
    var stepChar = (stepWord && stepIndex >= 0 && stepIndex < stepWord.length) ? stepWord.charAt(stepIndex) : '';
    html += '<tr>';
    html += '<td class="step-col"><div class="step-main">start ' + esc(String(stepIndex)) + '</div>' +
      (stepChar ? ('<div class="step-sub">' + esc(stepChar) + '</div>') : '') + '</td>';
    html += '<td class="selected-col">' + renderFlowCellItems(chosenItems, 'selected') + '</td>';
    html += '<td class="rejected-col">' + renderFlowCellItems(notChosen, 'rejected') + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  return html;
}

function collectTraceSummary(dpDebug, out) {
  var target = out || {
    boundary: [],
    pos: [],
    boundary_seen: Object.create(null),
    pos_seen: Object.create(null)
  };
  if (!dpDebug || typeof dpDebug !== 'object') return target;
  if (dpDebug.kind === 'merged') {
    var parts = Array.isArray(dpDebug.parts) ? dpDebug.parts : [];
    for (var pi = 0; pi < parts.length; pi++) {
      collectTraceSummary(parts[pi] && parts[pi].dp_debug, target);
    }
    return target;
  }
  var steps = Array.isArray(dpDebug.steps) ? dpDebug.steps : [];
  for (var si = 0; si < steps.length; si++) {
    var rejected = Array.isArray((steps[si] || {}).rejected) ? steps[si].rejected : [];
    for (var ri = 0; ri < rejected.length; ri++) {
      var item = rejected[ri] || {};
      var reason = String(item.reason || '');
      var key = reason + '|' + String(item.start || 0) + '|' + String(item.end || 0) + '|' + String(item.piece || '');
      if (reason === 'crosses_lemma_boundary') {
        if (target.boundary_seen[key]) continue;
        target.boundary_seen[key] = true;
        target.boundary.push(item);
      } else if (isPosRejectReason(reason)) {
        if (target.pos_seen[key]) continue;
        target.pos_seen[key] = true;
        target.pos.push(item);
      }
    }
  }
  return target;
}

function summarizeRejectItems(items, maxItems) {
  var list = Array.isArray(items) ? items : [];
  if (!list.length) return 'none';
  var max = Number(maxItems) || 3;
  var labels = [];
  for (var i = 0; i < list.length && i < max; i++) {
    var item = list[i] || {};
    labels.push(String(item.piece || '?') + ' (' + formatSpan(item) + ')');
  }
  if (list.length > max) labels.push('+' + String(list.length - max) + ' more');
  return labels.join(', ');
}

function renderRejectItem(item, kind) {
  var piece = String((item && item.piece) || '').trim() || '?';
  var html = '<div class="reject-item ' + esc(kind) + '">';
  html += '<div><strong>' + esc(piece) + '</strong> <span class="minor">' + esc(formatSpan(item)) + '</span></div>';
  html += '<div class="trace-detail">' + esc(explainRejectReason((item && item.reason) || kind));
  if (item && item.detail) html += ' | ' + esc(formatReason(item.detail));
  html += '</div>';
  if (kind === 'pos') {
    var allowed = Array.isArray(item && item.allowed_pos) ? item.allowed_pos : [];
    var xpos = Array.isArray(item && item.xpos_tags) ? item.xpos_tags : [];
    if (allowed.length) html += '<div class="trace-detail">allowed POS: ' + esc(allowed.join(', ')) + '</div>';
    if (xpos.length) html += '<div class="trace-detail">xpos: ' + esc(xpos.join('+')) + '</div>';
    html += renderEntryRefs(item && item.entry_refs, true);
  }
  html += '</div>';
  return html;
}

function renderDpDebug(dpDebug) {
  if (!dpDebug || typeof dpDebug !== 'object') return '<div class="minor">No greedy trace.</div>';
  if (dpDebug.kind === 'merged') {
    var parts = Array.isArray(dpDebug.parts) ? dpDebug.parts : [];
    if (!parts.length) return '<div class="minor">No greedy trace.</div>';
    return '<div class="trace-wrap">' + parts.map(function(part, idx) {
      var fills = Array.isArray(part && part.fills) ? part.fills : [];
      var fillLabel = fills.map(function(fill) {
        return String((fill && fill.text) || (fill && fill.head) || '').trim();
      }).filter(Boolean).join(' + ');
      var html = '<details class="trace-step">';
      html += '<summary>Part ' + esc(String(idx + 1)) + ' | mode=' + esc(String((part && part.mode) || '')) +
        (fillLabel ? (' | fills=' + esc(fillLabel)) : '') + '</summary>';
      html += renderDpDebug(part && part.dp_debug);
      html += '</details>';
      return html;
    }).join('') + '</div>';
  }
  var steps = Array.isArray(dpDebug.steps) ? dpDebug.steps : [];
  if (!steps.length) return '<div class="minor">No greedy trace.</div>';
  var rendered = [];
  for (var i = 0; i < steps.length; i++) {
    var step = steps[i] || {};
    var rejected = Array.isArray(step.rejected) ? step.rejected : [];
    var boundaryRejects = rejected.filter(function(item) {
      return String((item && item.reason) || '') === 'crosses_lemma_boundary';
    });
    var posRejects = rejected.filter(function(item) {
      return isPosRejectReason((item && item.reason) || '');
    });
    if (!boundaryRejects.length && !posRejects.length && !step.selected) continue;
    var selected = step.selected || null;
    var summary = 'i=' + String(step.index != null ? step.index : i);
    if (selected) {
      summary += ' | selected=' + String((selected.piece) || '?') + ' [' + String((selected.kind) || '') + ']';
    }
    if (boundaryRejects.length) summary += ' | boundary rejects=' + String(boundaryRejects.length);
    if (posRejects.length) summary += ' | pos rejects=' + String(posRejects.length);
    var html = '<div class="trace-step">';
    html += '<div class="trace-label">' + esc(summary) + '</div>';
    if (selected) {
      html += '<div class="trace-selected">';
      html += '<span class="chip ' + (selected.kind === 'known' ? 'path-surface' : 'bad') + '">' + esc(String(selected.kind || '')) + '</span>';
      html += '<span class="minor"> ' + esc(String(selected.piece || '')) + ' | unknown=' +
        esc(String(selected.score_unknown != null ? selected.score_unknown : '')) + ' | pieces=' +
        esc(String(selected.score_pieces != null ? selected.score_pieces : '')) + '</span>';
      html += '</div>';
      if (Array.isArray(selected.entry_refs) && selected.entry_refs.length) {
        html += renderEntryRefs(selected.entry_refs, false);
      }
    }
    if (boundaryRejects.length || posRejects.length) {
      html += '<div class="reject-list">';
      for (var b = 0; b < boundaryRejects.length; b++) html += renderRejectItem(boundaryRejects[b], 'boundary');
      for (var p = 0; p < posRejects.length; p++) html += renderRejectItem(posRejects[p], 'pos');
      html += '</div>';
    }
    html += '</div>';
    rendered.push(html);
  }
  if (!rendered.length) return '<div class="minor">No boundary/POS rejections for this token.</div>';
  return '<div class="trace-wrap">' + rendered.join('') + '</div>';
}

function renderPathSummary(title, summary, chosenPath) {
  if (!summary) return '<div class="minor">No data</div>';
  var html = '<div class="path-block">';
  html += '<div class="path-title">' + esc(title) + '</div>';
  html += '<div class="chips">';
  html += '<span class="chip ' + (chosenPath === 'lemma' ? 'path-lemma' : 'path-surface') + '">' + esc(chosenPath) + '</span>';
  if (summary.mode) html += '<span class="chip mode">' + esc(summary.mode) + '</span>';
  html += '<span class="chip mode">matches=' + esc(String(summary.match_count != null ? summary.match_count : 0)) + '</span>';
  html += '<span class="chip ' + (summary.has_unknown ? 'bad' : 'mode') + '">' + esc(summary.has_unknown ? 'has unknown' : 'no unknown') + '</span>';
  html += '</div>';
  html += '<div class="decision-line"><span class="decision-label">Split</span><span class="piece-summary">' + esc(summarizeFillPieces(summary)) + '</span></div>';
  html += renderCompactPieceLines(summary);
  html += '</div>';
  return html;
}

function renderScoringLemmaHints(hints) {
  var rows = Array.isArray(hints) ? hints : [];
  if (!rows.length) return '';
  var html = '';
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    if (i > 0) html += ' ';
    if (row && typeof row === 'object' && !Array.isArray(row)) {
      var text = String(row.text || row.lemma || '').trim();
      var upos = String(row.upos || '').trim();
      var xpos = String(row.xpos || '').trim();
      var variants = Array.isArray(row.variants) ? row.variants : [];
      html += '<span class="chip path-lemma">' + esc(text || '?') + '</span>';
      if (variants.length) html += ' <span class="minor">alts=' + esc(variants.join(' / ')) + '</span>';
      if (upos) html += ' <span class="chip warn">' + esc('upos=' + upos) + '</span>';
      if (xpos) html += ' <span class="chip warn">' + esc('xpos=' + xpos) + '</span>';
      continue;
    }
    var rawText = String(row || '').trim();
    if (!rawText) continue;
    html += '<span class="chip path-lemma">' + esc(rawText) + '</span>';
  }
  return html;
}

function getScoringResolutionInfo(result, scoring) {
  var actual = getActualResolutionInfo(result);
  if (actual && typeof actual === 'object') return actual;
  if (scoring && scoring.resolution && typeof scoring.resolution === 'object') return scoring.resolution;
  return null;
}

function describeScoringFilter(kind) {
  if (kind === 'exact') return 'exact matches';
  if (kind === 'lemma') return 'lemma overrides';
  if (kind === 'greedy') return 'greedy segmentation';
  return 'all tokens';
}

function getScoringFilterKind(result, scoring) {
  var resolution = getScoringResolutionInfo(result, scoring) || {};
  var bits = [
    resolution.category,
    resolution.label,
    resolution.fill_mode,
    resolution.resolved_via,
    scoring && scoring.resolved_via,
    scoring && scoring.fill_mode
  ];
  var text = bits.map(function(value) {
    return String(value || '').trim().toLowerCase();
  }).filter(Boolean).join(' | ');
  if (!text) return 'other';
  if (/override/.test(text)) return 'lemma';
  if (/exact/.test(text) || /partial_lemma_match/.test(text)) return 'exact';
  if (/greedy/.test(text) || /lemma_promotion/.test(text) || /lemma_promoted/.test(text) || /partwise/.test(text)) return 'greedy';
  return 'other';
}

function updateScoringFilterButtons() {
  var buttons = document.querySelectorAll('[data-scoring-filter]');
  for (var i = 0; i < buttons.length; i++) {
    var button = buttons[i];
    var active = String(button.getAttribute('data-scoring-filter') || '') === currentScoringFilter;
    if (active) button.classList.add('active');
    else button.classList.remove('active');
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  }
}

function updateScoringFilterStatus(visibleCount, totalCount) {
  var info = document.getElementById('filterInfo');
  if (!info) return;
  var total = Number(totalCount) || 0;
  if (!total) {
    info.textContent = '';
    return;
  }
  var label = describeScoringFilter(currentScoringFilter);
  if (currentScoringFilter === 'all') {
    info.textContent = 'Showing all ' + String(total) + ' tokens';
  } else if (visibleCount > 0) {
    info.textContent = 'Showing ' + String(visibleCount) + ' / ' + String(total) + ' ' + label;
  } else {
    info.textContent = 'No ' + label + ' in this lookup';
  }
}

function applyScoringFilter() {
  updateScoringFilterButtons();
  var cards = document.querySelectorAll('.token-card');
  var visible = 0;
  for (var i = 0; i < cards.length; i++) {
    var card = cards[i];
    var kind = String(card.getAttribute('data-scoring-kind') || 'other');
    var show = card.classList && card.classList.contains('token-error') ? true : (currentScoringFilter === 'all' || kind === currentScoringFilter);
    card.style.display = show ? '' : 'none';
    if (show) visible += 1;
  }
  updateScoringFilterStatus(visible, cards.length);
}

function setScoringFilter(mode) {
  var key = String(mode || '').trim().toLowerCase();
  if (key !== 'exact' && key !== 'lemma' && key !== 'greedy') key = 'all';
  currentScoringFilter = key;
  applyScoringFilter();
}

function renderPromotedFillRows(fills) {
  var rows = Array.isArray(fills) ? fills : [];
  var html = '';
  var count = 0;
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var lemma = String(row._lemma_promoted || row.lemma_promoted || '').trim();
    if (!lemma) continue;
    var text = String(row.text || row.head || '?').trim() || '?';
    var headword = String(row._lemma_promoted_headword || row.lemma_promoted_headword || '').trim();
    var upos = String(row._lemma_upos_hint || row.lemma_upos_hint || '').trim();
    var xpos = String(row._lemma_xpos_hint || row.lemma_xpos_hint || '').trim();
    if (count > 0) html += ' ';
    html += '<span class="chip path-surface">' + esc(text) + '</span>';
    html += ' <span class="minor">lemma=' + esc(lemma) + '</span>';
    if (headword && headword !== text) html += ' <span class="minor">headword=' + esc(headword) + '</span>';
    if (upos) html += ' <span class="chip warn">' + esc('upos=' + upos) + '</span>';
    if (xpos) html += ' <span class="chip warn">' + esc('xpos=' + xpos) + '</span>';
    count += 1;
  }
  return html;
}

function renderLemmaOverrideParts(parts) {
  var rows = Array.isArray(parts) ? parts : [];
  if (!rows.length) return '';
  var html = '';
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var text = String(row.text || '').trim();
    var sourceText = String(row.source_text || '').trim();
    var upos = String(row.upos || '').trim();
    var xpos = String(row.xpos || '').trim();
    var matched = !!row.matched;
    if (i > 0) html += ' ';
    html += '<span class="chip path-lemma">' + esc(text || '?') + '</span>';
    if (row.matched !== undefined) {
      html += ' <span class="chip ' + (matched ? 'ok' : 'warn') + '">' + esc(matched ? 'exact' : 'gap') + '</span>';
    }
    if (sourceText && sourceText !== text) html += ' <span class="minor">from ' + esc(sourceText) + '</span>';
    if (upos) html += ' <span class="chip warn">' + esc('upos=' + upos) + '</span>';
    if (xpos) html += ' <span class="chip warn">' + esc('xpos=' + xpos) + '</span>';
  }
  return html;
}

function renderRawJsonBlock(title, value) {
  if (value == null) return '';
  var text = '';
  try {
    text = JSON.stringify(value, null, 2);
  } catch (_err) {
    text = String(value);
  }
  if (!text) return '';
  return '' +
    '<div class="path-section">' +
      '<div class="path-section-head">' +
        '<div class="path-head-top"><span>' + esc(title) + '</span></div>' +
      '</div>' +
      '<pre style="margin:0;padding:12px 14px;border-top:1px solid #e5e7eb;background:#f8fafc;color:#0f172a;font-size:12px;line-height:1.45;white-space:pre-wrap;word-break:break-word;">' + esc(text) + '</pre>' +
    '</div>';
}

function rowHasScoringTrace(row) {
  if (!row || typeof row !== 'object') return false;
  return !!(
    (row._debug_lookup_scoring && typeof row._debug_lookup_scoring === 'object') ||
    (row._debug_greedy_main && typeof row._debug_greedy_main === 'object') ||
    (row._debug_greedy_subwords && typeof row._debug_greedy_subwords === 'object')
  );
}

function getEffectiveScoringResults(data) {
  if (Array.isArray(data && data.debug_effective_results_by_seg)) return data.debug_effective_results_by_seg;
  if (Array.isArray(data && data.debug_effective_results)) return data.debug_effective_results;
  if (Array.isArray(data && data.results_by_seg)) return data.results_by_seg;
  if (Array.isArray(data && data.debug_ui_results_by_seg)) return data.debug_ui_results_by_seg;
  return [];
}

function getActualResolutionInfo(result) {
  if (result && result.resolution_actual && typeof result.resolution_actual === 'object') {
    return result.resolution_actual;
  }
  if (result && result.resolution_live && typeof result.resolution_live === 'object') {
    return result.resolution_live;
  }
  return null;
}

function getScoringBucketLabel(result, scoring) {
  var actualResolution = getActualResolutionInfo(result);
  var bucketLabel = String((actualResolution && actualResolution.label) || '').trim();
  if (bucketLabel) return bucketLabel;
  if (scoring && typeof scoring === 'object') {
    var scoringLabel = String(scoring.resolved_via || scoring.chosen_path || '').trim();
    if (scoringLabel) return scoringLabel;
  }
  return String((result && result.resolved_via) || '').trim();
}

function buildScoringDecisionLine(result, scoring) {
  var parts = [];
  parts.push('bucket=' + (getScoringBucketLabel(result, scoring) || 'unresolved'));
  var actualResolution = getActualResolutionInfo(result);
  if (actualResolution && typeof actualResolution === 'object') {
    var fillMode = String(actualResolution.fill_mode || '').trim();
    if (fillMode) parts.push('mode=' + fillMode);
  } else if (scoring && typeof scoring === 'object') {
    var scoringFillMode = String(scoring.fill_mode || '').trim();
    if (scoringFillMode) parts.push('mode=' + scoringFillMode);
  }
  return parts.join(' | ');
}

function renderTokenCard(token, row, index) {
  var tok = token || {};
  var result = row || {};
  var scoring = result._debug_lookup_scoring || null;
  var actualResolution = getActualResolutionInfo(result);
  var bucketLabel = getScoringBucketLabel(result, scoring);
  var lemmaHints = (scoring && Array.isArray(scoring.lemma_hints)) ? scoring.lemma_hints : [];
  var lemmaOverrideParts = (scoring && Array.isArray(scoring.lemma_override_parts)) ? scoring.lemma_override_parts : [];
  var surfaceExactEvents = (scoring && Array.isArray(scoring.surface_exact_events)) ? scoring.surface_exact_events : [];
  var lemmaExactEvents = (scoring && Array.isArray(scoring.lemma_exact_events)) ? scoring.lemma_exact_events : [];
  var scoringKind = getScoringFilterKind(result, scoring);
  var tokenText = String(tok.text || result.surface_form || result.head || '').trim() || '?';
  var metaRight = 'sent ' + String((Number(tok.sentence_index) || 0) + 1) + ', tok ' + String((Number(tok.token_index) || 0) + 1);
  var html = '<div class="token-card" data-scoring-kind="' + esc(scoringKind) + '">';
  html += '<div class="token-head"><div class="tok-text">' + esc(tokenText) + '</div><div class="minor">' + esc(metaRight) + '</div></div>';
  html += '<div class="tok-meta">';

  var decisionLine = buildScoringDecisionLine(result, scoring);
  var fills = Array.isArray(result.dict_fill) ? result.dict_fill : [];
  var promotedRowsHtml = renderPromotedFillRows(fills);

  html += '<table class="summary-table"><tbody>';
  html += '<tr><th>Analysis</th><td>' + esc(
    'lemma=' + String((scoring && scoring.lemma_text) || tok.lemma || result.lemma || '') +
    ' | upos=' + String(tok.upos || result.upos || '') +
    ' | xpos=' + String(tok.xpos || result.tag || '')
  ) + '</td></tr>';
  html += '<tr><th>Decision</th><td>' + esc(decisionLine) + '</td></tr>';
  if (actualResolution && actualResolution.route_text) {
    html += '<tr><th>Route</th><td>' + esc(String(actualResolution.route_text || '')) + '</td></tr>';
  }
  if (actualResolution && actualResolution.final_text) {
    html += '<tr><th>Final</th><td>' + esc(String(actualResolution.final_text || '')) + '</td></tr>';
  }
  if (lemmaHints.length) {
    html += '<tr><th>Lemma hints</th><td>' + renderScoringLemmaHints(lemmaHints) + '</td></tr>';
  }
  if (lemmaOverrideParts.length) {
    html += '<tr><th>Lemma override</th><td>' + renderLemmaOverrideParts(lemmaOverrideParts) + '</td></tr>';
  }
  if (promotedRowsHtml) {
    html += '<tr><th>Promoted</th><td>' + promotedRowsHtml + '</td></tr>';
  }
  html += '</tbody></table>';

  if (surfaceExactEvents.length) {
    html += renderExactEventTable({
      path: 'surface',
      title: 'Surface path',
      summary: { exact_events: surfaceExactEvents }
    });
  }
  if (lemmaExactEvents.length) {
    html += renderExactEventTable({
      path: 'lemma',
      title: 'Lemma path',
      summary: { exact_events: lemmaExactEvents }
    });
  }

  var dpTitle = bucketLabel || 'DP';
  html += renderDecisionTable(
    result._debug_greedy_main || null,
    {
      path: 'chosen',
      title: dpTitle
    },
    ''
  );
  html += renderDecisionTable(
    result._debug_greedy_subwords || null,
    {
      path: 'subword',
      title: 'Subword DP'
    },
    ''
  );
  html += '</div></div>';
  return html;
}

function renderTokenCardError(token, index, err) {
  var tok = token || {};
  var tokenText = String(tok.text || tok.surface_form || tok.head || '').trim() || '?';
  var metaRight = 'sent ' + String((Number(tok.sentence_index) || 0) + 1) + ', tok ' + String((Number(tok.token_index) || 0) + 1);
  var message = (err && (err.stack || err.message)) ? (err.stack || err.message) : String(err || 'unknown error');
  return '' +
    '<div class="token-card token-error" data-scoring-kind="other">' +
      '<div class="token-head"><div class="tok-text">' + esc(tokenText) + '</div><div class="minor">' + esc(metaRight) + '</div></div>' +
      '<div class="tok-meta">' +
        '<div class="note" style="margin:0;border-color:#f38ba8;color:#f9e2af;background:#2a1d25;">' +
          'Render error on row ' + esc(String(index + 1)) + ': ' + esc(message) +
        '</div>' +
      '</div>' +
    '</div>';
}

function fetchDebug() {
  fetch('/debug/data', { cache: 'no-store' })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.ok) {
        document.getElementById('statusDot').classList.remove('live');
        document.getElementById('content').className = 'empty';
        document.getElementById('content').innerHTML = esc(data.error || 'No data');
        return;
      }
      if (data._timestamp && data._timestamp === lastTimestamp) return;
      lastTimestamp = data._timestamp;
      document.getElementById('statusDot').classList.add('live');
      var ts = data._timestamp ? new Date(data._timestamp * 1000).toLocaleTimeString() : '?';
      var metaParts = ['Lang: ' + String(data.language || '?'), ts];
      var scoringSource = String(data.debug_scoring_source || '').trim();
      if (scoringSource) metaParts.push('scoring=' + scoringSource);
      document.getElementById('metaInfo').textContent = metaParts.join(' | ');

      var results = getEffectiveScoringResults(data);
      var tokens = Array.isArray(data.trankit_tokens) ? data.trankit_tokens : [];
      var hasTrace = !!data.debug_scoring_available;
      if (!hasTrace) hasTrace = results.some(rowHasScoringTrace);
      if (!results.length || !hasTrace) {
        var missingTraceMessage = 'No scoring trace in the effective debug payload.';
        if (!String(data.debug_scoring_source || '').trim() || String(data.debug_scoring_source || '') === 'snapshot') {
          missingTraceMessage += ' Reload the reader page so it picks up the latest client script, then run a fresh lookup.';
        }
        document.getElementById('content').className = 'empty';
        document.getElementById('content').innerHTML = esc(missingTraceMessage);
        var filterInfo = document.getElementById('filterInfo');
        if (filterInfo) filterInfo.textContent = '';
        return;
      }

      var rowCount = Math.max(tokens.length, results.length);
      var html = '<div class="token-list">';
      var renderErrors = [];
      for (var ri = 0; ri < rowCount; ri++) {
        try {
          html += renderTokenCard(tokens[ri] || {}, results[ri] || {}, ri);
        } catch (rowErr) {
          renderErrors.push('row ' + String(ri + 1) + ': ' + String((rowErr && (rowErr.stack || rowErr.message)) || rowErr));
          html += renderTokenCardError(tokens[ri] || {}, ri, rowErr);
        }
      }
      html += '</div>';
      var content = document.getElementById('content');
      content.className = '';
      content.innerHTML = html;
      try {
        applyScoringFilter();
      } catch (filterErr) {
        var filterInfo = document.getElementById('filterInfo');
        if (filterInfo) filterInfo.textContent = 'Filter unavailable: ' + String((filterErr && filterErr.message) || filterErr);
      }
      if (renderErrors.length) {
        var metaInfo = document.getElementById('metaInfo');
        if (metaInfo) {
          metaInfo.textContent = (metaInfo.textContent ? metaInfo.textContent + ' | ' : '') + 'row errors=' + String(renderErrors.length);
        }
      }
    })
    .catch(function(err) {
      document.getElementById('statusDot').classList.remove('live');
      document.getElementById('content').className = 'empty';
      var detail = (err && (err.stack || err.message)) ? (err.stack || err.message) : String(err || '');
      var msg = 'Failed to load debug data.' + (detail ? ' ' + detail : '');
      document.getElementById('content').innerHTML = esc(msg);
      var filterInfo = document.getElementById('filterInfo');
      if (filterInfo) filterInfo.textContent = '';
    });
}

fetchDebug();
</script>
</body>
</html>
"""

_DEBUG_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Pipeline Debug</title>
<style>
  :root { --bg: #1e1e2e; --fg: #cdd6f4; --surface: #313244; --border: #45475a;
          --accent: #89b4fa; --green: #a6e3a1; --red: #f38ba8; --yellow: #f9e2af;
          --peach: #fab387; --mono: 'Cascadia Code', 'Fira Code', 'Consolas', monospace; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: var(--mono); font-size: 13px; background: var(--bg); color: var(--fg);
         padding: 16px; line-height: 1.6; }
  h1 { font-size: 16px; color: var(--accent); margin-bottom: 12px; display: flex;
       align-items: center; gap: 10px; }
  h1 .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--red); }
  h1 .dot.live { background: var(--green); }
  .meta { font-size: 11px; color: #6c7086; margin-bottom: 16px; }
  .section { margin-bottom: 20px; border: 1px solid var(--border); border-radius: 6px;
             overflow: hidden; }
  .section-head { background: var(--surface); padding: 8px 12px; font-weight: bold;
                  font-size: 13px; cursor: pointer; user-select: none;
                  display: flex; justify-content: space-between; align-items: center; }
  .section-head:hover { background: #3b3d52; }
  .section-head .tag { font-size: 10px; padding: 2px 8px; border-radius: 3px;
                       font-weight: 600; }
  .tag-input { background: #89b4fa33; color: var(--accent); }
  .tag-trankit { background: #a6e3a133; color: var(--green); }
  .tag-dict { background: #fab38733; color: var(--peach); }
  .tag-diff { background: #f38ba833; color: var(--red); }
  .tag-remap { background: #94e2d533; color: #94e2d5; }
  .tag-norm { background: #89dceb33; color: #89dceb; }
  .tag-ja { background: #f9e2af33; color: #f9e2af; }
  .diff-row td { background: #1e1017; }
  .diff-field { font-size: 10px; color: #6c7086; text-transform: uppercase; letter-spacing: 0.5px;
                margin-right: 6px; }
  .diff-expected { color: var(--green); }
  .diff-actual { color: var(--red); }
  .section-body { padding: 12px; overflow-x: auto; max-height: 70vh; overflow-y: auto; }
  .section-body.collapsed { display: none; }
  .text-block { background: #181825; padding: 12px; border-radius: 4px; white-space: pre-wrap;
                word-break: break-all; font-size: 15px; line-height: 1.8; }
  .text-block .filtered { color: var(--green); }
  .text-block .original { color: var(--fg); }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; padding: 6px 8px; background: #181825; color: #a6adc8;
       font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
       position: sticky; top: 0; z-index: 1; }
  td { padding: 5px 8px; border-top: 1px solid var(--border); vertical-align: top; }
  tr:hover td { background: #2a2b3d; }
  .tok-text { font-size: 16px; font-weight: bold; }
  .pos-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px;
               font-weight: 600; }
  .dep-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px;
               background: var(--surface); color: #a6adc8; margin-left: 4px; }
  .ner-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px;
               background: #f38ba833; color: var(--red); margin-left: 4px; }
  .dict-entry { margin-top: 4px; padding: 4px 8px; background: #181825; border-radius: 3px;
                font-size: 11px; }
  .dict-entry .head { color: var(--peach); font-weight: bold; }
  .dict-entry .roman { color: #a6adc8; font-style: italic; margin-left: 6px; }
  .dict-entry .sense { color: var(--fg); }
  .dict-unknown { color: var(--red); font-style: italic; }
  .sent-divider td { background: #1e1e2e; padding: 2px 8px; }
  .sent-label { font-size: 10px; color: #6c7086; font-weight: 600; text-transform: uppercase;
                letter-spacing: 1px; }
  .empty { text-align: center; padding: 40px; color: #6c7086; }
  .json-raw { background: #181825; padding: 12px; border-radius: 4px; white-space: pre-wrap;
              word-break: break-word; font-size: 11px; max-height: 60vh; overflow-y: auto; }
  .refresh-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
  .btn { background: var(--surface); color: var(--fg); border: 1px solid var(--border);
         padding: 4px 12px; border-radius: 4px; font-size: 12px; cursor: pointer;
         font-family: var(--mono); text-decoration: none; }
  .btn:hover { background: #3b3d52; }
  .btn.active { background: var(--accent); color: var(--bg); border-color: var(--accent); }
  .auto-tag { font-size: 10px; color: var(--green); }
  .probe-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
  .probe-input { background: #181825; color: var(--fg); border: 1px solid var(--border);
                 border-radius: 4px; padding: 6px 8px; font-size: 12px; font-family: var(--mono); }
  .probe-input.word { min-width: 220px; }
  .probe-input.lang { width: 70px; }
  .probe-input.upos { width: 120px; }
  .probe-note { font-size: 11px; color: #a6adc8; margin-bottom: 12px; }
  .probe-selected td { background: #253445 !important; }
  .probe-score { color: #89dceb; font-weight: 600; }
  .tsv-row-line { white-space: pre-wrap; word-break: break-word; font-size: 11px; line-height: 1.5; color: #cdd6f4; }
  .raw-row-summary { cursor: pointer; color: #a6adc8; }
  .match-badges { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 6px; }
  .match-badge { display: inline-block; padding: 1px 7px; border-radius: 10px; font-size: 10px; font-weight: 700; letter-spacing: 0.2px; }
  .badge-primary { background: #a6e3a133; color: #a6e3a1; }
  .badge-shown { background: #f9e2af33; color: #f9e2af; }
  .badge-filtered { background: #f38ba833; color: #f38ba8; }
  .badge-unmatched { background: #6c708633; color: #a6adc8; }
  .variant-hit-used { color: #a6e3a1; }
  .variant-hit-filtered { color: #f38ba8; }
  .variant-hit-unused { color: #89dceb; }
  details.dict-entry.primary { border-left: 2px solid #a6e3a1; }
  details.dict-entry.shown { border-left: 2px solid #f9e2af; }
  details.dict-entry.filtered { border-left: 2px solid #f38ba8; }
  details.dict-entry.unmatched { border-left: 2px solid #6c7086; }
  .ui-trace-summary { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
  .ui-trace-chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
                   border-radius: 999px; background: #181825; border: 1px solid var(--border);
                   font-size: 11px; color: #a6adc8; }
  .ui-trace-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
  .ui-trace-card { background: #181825; border: 1px solid var(--border); border-radius: 6px; padding: 10px; }
  .ui-trace-meta { display: flex; justify-content: space-between; align-items: center; gap: 8px;
                   margin-bottom: 8px; font-size: 11px; color: #a6adc8; }
  .ui-trace-kv { display: grid; grid-template-columns: 120px 1fr; gap: 4px 8px; font-size: 11px; }
  .ui-trace-kv div:nth-child(odd) { color: #6c7086; }
  .ui-trace-kv div:nth-child(even) { color: var(--fg); word-break: break-word; }
  .ui-trace-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .ui-trace-block { margin-top: 8px; padding: 8px; background: #11111b; border-radius: 4px; }
  .ui-trace-token-row { display: flex; flex-wrap: wrap; gap: 6px; }
  .ui-trace-token-pill { display: inline-block; padding: 2px 8px; border-radius: 999px;
                         background: #313244; color: var(--fg); font-size: 11px; }
  .ui-trace-table { width: 100%; border-collapse: collapse; font-size: 11px; }
  .ui-trace-table th { font-size: 10px; }
  .ui-trace-table td { padding: 6px 8px; }
  .ui-trace-type { color: #89dceb; font-weight: 700; white-space: nowrap; }
  .ui-trace-detail { color: #a6adc8; }
  .ui-trace-empty { color: #6c7086; padding: 14px 0; }
  .ui-trace-panel-details { margin-top: 12px; border: 1px solid var(--border); border-radius: 6px;
                            background: #11111b; }
  .ui-trace-panel-details > summary { cursor: pointer; padding: 10px 12px; font-weight: 700;
                                      color: var(--accent); user-select: none; }
  .ui-trace-panel-details[open] > summary { border-bottom: 1px solid var(--border); }
  .ui-trace-html { font-family: var(--mono); font-size: 10px; color: #a6adc8; white-space: pre-wrap;
                   word-break: break-word; max-height: 180px; overflow: auto; background: #0b0c10;
                   padding: 8px; border-radius: 4px; }
  .backend-trace-summary { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
  .backend-trace-chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
                        border-radius: 999px; background: #181825; border: 1px solid var(--border);
                        font-size: 11px; color: #a6adc8; }
  .backend-trace-block { margin-top: 10px; padding: 10px; background: #11111b; border: 1px solid var(--border);
                         border-radius: 6px; }
  .backend-trace-block h4 { font-size: 12px; color: var(--accent); margin-bottom: 8px; }
  .backend-trace-empty { color: #6c7086; padding: 10px 0; }
  .backend-trace-timing-row { display: grid; grid-template-columns: 180px 72px minmax(120px,1fr) 1fr; gap: 8px;
                              align-items: center; padding: 4px 0; border-top: 1px solid rgba(69,71,90,0.45); }
  .backend-trace-timing-row:first-child { border-top: none; }
  .backend-trace-scope { color: var(--fg); font-weight: 600; }
  .backend-trace-ms { color: #89dceb; white-space: nowrap; }
  .backend-trace-meta { color: #a6adc8; font-size: 11px; word-break: break-word; }
  .backend-trace-bar-wrap { height: 8px; border-radius: 999px; background: #181825; overflow: hidden; }
  .backend-trace-bar { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #89b4fa, #94e2d5); }
  .backend-trace-list { display: grid; gap: 8px; }
  .backend-trace-card { background: #181825; border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; }
  .backend-trace-card-head { display: flex; justify-content: space-between; gap: 10px; align-items: center; margin-bottom: 6px; }
  .backend-trace-card-title { color: var(--peach); font-weight: 700; }
  .backend-trace-card-meta { color: #a6adc8; font-size: 11px; }
  .backend-trace-card-body { color: var(--fg); font-size: 11px; line-height: 1.55; word-break: break-word; }
  .backend-trace-card-body code { color: #94e2d5; }
</style>
</head>
<body>

<h1><span class="dot" id="statusDot"></span> Pipeline Debug</h1>
<div class="refresh-bar">
  <button class="btn" onclick="fetchDebug()">Refresh</button>
  <button class="btn" id="autoBtn" onclick="toggleAuto()">Auto: OFF</button>
  <a class="btn" href="/debug/sqlite">SQLite</a>
  <a class="btn" href="/debug/lemma_boundaries">Lemma Boundaries</a>
  <a class="btn" href="/debug/lemma_boundaries?mode=mwt_realign">MWT Realign</a>
  <a class="btn" href="/debug/chatgpt_dump">ChatGPT Dump</a>
  <a class="btn" href="/debug/scoring_information">Scoring Info</a>
  <span class="auto-tag" id="autoTag"></span>
  <span class="meta" id="metaInfo"></span>
</div>

<div class="section" style="margin-bottom:14px;">
  <div class="section-head" onclick="toggleSection(this)">
    <span><span class="tag tag-dict">DP</span> Greedy Fill Score Probe</span>
    <span>&#9662;</span>
  </div>
  <div class="section-body">
    <div class="probe-bar">
      <input id="greedyWordInput" class="probe-input word" type="text" placeholder="Word/token to probe"
             onkeydown="handleGreedyWordKeydown(event)">
      <input id="greedyLangInput" class="probe-input lang" type="text" value="" placeholder="lang (auto)" readonly>
      <input id="greedyUposInput" class="probe-input upos" type="text" placeholder="UPOS (optional)">
      <button class="btn" onclick="runGreedyProbe()">Run Score</button>
    </div>
    <div class="probe-note" id="greedyProbeMeta">Uses the current page language (Lang: ...) and existing dictionary fill path with exact disabled to force greedy fallback.</div>
    <div id="greedyProbeBody"><span class="dict-unknown">Run a probe to see per-piece score breakdown.</span></div>
  </div>
</div>

<div id="content"><div class="empty">No lookup data yet. Run a lookup in the main window.</div></div>

<script src="/static/dictionary_normalization_layer.js?v=20260311b"></script>
<script src="/static/dictionary_engine.js?v=20260311b"></script>
<script src="/static/dictionary_client.js?v=20260311f"></script>
<script>
var autoInterval = null;
var lastTimestamp = null;
var currentProbeLang = '';
var debugDictContextByLang = Object.create(null);
var debugLookupReplayPromiseByStamp = Object.create(null);

function toggleAuto() {
  if (autoInterval) {
    clearInterval(autoInterval);
    autoInterval = null;
    document.getElementById('autoBtn').textContent = 'Auto: OFF';
    document.getElementById('autoBtn').classList.remove('active');
    document.getElementById('autoTag').textContent = '';
  } else {
    autoInterval = setInterval(fetchDebug, 1500);
    document.getElementById('autoBtn').textContent = 'Auto: ON';
    document.getElementById('autoBtn').classList.add('active');
    document.getElementById('autoTag').textContent = 'polling every 1.5s';
  }
}

function fetchDebug() {
  fetch('/debug/data')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.ok) {
        document.getElementById('statusDot').classList.remove('live');
        document.getElementById('content').innerHTML = '<div class="empty">' + esc(data.error || 'No data') + '</div>';
        return;
      }
      if (data._timestamp && data._timestamp === lastTimestamp) return;
      lastTimestamp = data._timestamp;
      document.getElementById('statusDot').classList.add('live');
      render(data);
    })
    .catch(function(e) {
      document.getElementById('statusDot').classList.remove('live');
    });
}

function esc(s) {
  if (s == null) return '';
  var d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function formatScore(v) {
  var n = Number(v);
  if (!isFinite(n)) return '';
  return n.toFixed(2);
}

function normalizeLangCode(raw) {
  return String(raw || '').trim().toLowerCase();
}

function clonePlainObject(obj) {
  var out = {};
  var src = obj || {};
  for (var k in src) {
    if (Object.prototype.hasOwnProperty.call(src, k)) out[k] = src[k];
  }
  return out;
}

function parseTsvWithHeaders(text) {
  var lines = String(text || '').split(/\r?\n/);
  if (!lines.length) return { headers: [], rows: [] };
  var headerLine = String(lines[0] || '');
  if (!headerLine.trim()) return { headers: [], rows: [] };
  var headers = headerLine.split('\t');
  var rows = [];
  for (var i = 1; i < lines.length; i++) {
    var line = lines[i];
    if (!line || !line.trim()) continue;
    var fields = line.split('\t');
    var row = { __line_no: i + 1 };
    for (var j = 0; j < headers.length; j++) {
      row[String(headers[j] || '').trim()] = (j < fields.length) ? fields[j] : '';
    }
    rows.push(row);
  }
  return { headers: headers, rows: rows };
}

function parseEtymologyNumber(raw) {
  var n = parseInt(String(raw == null ? '' : raw), 10);
  if (!isFinite(n) || n < 0) return 0;
  return n;
}

function lookupKeyForDebug(rawText) {
  var text = String(rawText || '').trim();
  if (!text) return '';
  if (window.DictionaryEngine && typeof window.DictionaryEngine.lookupKey === 'function') {
    try {
      return String(window.DictionaryEngine.lookupKey(text, currentProbeLang || '') || '');
    } catch (_e) {}
  }
  if (text.normalize) text = text.normalize('NFKC');
  text = text.trim();
  if (!text) return '';
  if (window.DictionaryNormalizationLayer && typeof window.DictionaryNormalizationLayer.normalizeLookupText === 'function') {
    try {
      text = String(window.DictionaryNormalizationLayer.normalizeLookupText(text, {
        langCode: currentProbeLang || '',
        phase: 'debug_lookup'
      }) || '');
    } catch (_e2) {}
  }
  return text.replace(/-/g, '').toLowerCase();
}

function entryIdentityKeyForDebug(entryLike) {
  if (!entryLike || typeof entryLike !== 'object') return '';
  var head = String(entryLike.headword || '').trim();
  if (!head) return '';
  var posRaw = String(entryLike.pos || entryLike.pos_raw || '').trim();
  var etymNum = parseEtymologyNumber(entryLike.etymology_number);
  var etymText = String(entryLike.etymology || '');
  return head + '\t' + posRaw + '\t' + etymNum + '\t' + etymText;
}

function buildRawRowIndex(rows, headers) {
  var byIdentity = Object.create(null);
  var byHeadword = Object.create(null);
  var byLookupKey = Object.create(null);
  var byFormKey = Object.create(null);
  var byLine = Object.create(null);
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var lineNo = Number(row.__line_no || 0);
    if (isFinite(lineNo) && lineNo > 0 && !byLine[lineNo]) {
      byLine[lineNo] = row;
    }
    var head = String(row.headword || '').trim();
    if (!head) continue;
    var key = entryIdentityKeyForDebug(row);
    if (!byIdentity[key]) byIdentity[key] = [];
    byIdentity[key].push(row);
    if (!byHeadword[head]) byHeadword[head] = [];
    byHeadword[head].push(row);

    var lookupKey = lookupKeyForDebug(head);
    if (lookupKey) {
      if (!byLookupKey[lookupKey]) byLookupKey[lookupKey] = [];
      byLookupKey[lookupKey].push(row);
    }

    var formsRaw = String(row.forms || '').trim();
    if (formsRaw) {
      try {
        var forms = JSON.parse(formsRaw);
        if (Array.isArray(forms)) {
          for (var fi = 0; fi < forms.length; fi++) {
            var formRow = forms[fi];
            if (!Array.isArray(formRow) || !formRow.length) continue;
            var formText = String(formRow[0] || '').trim();
            if (!formText) continue;
            var formKey = lookupKeyForDebug(formText);
            if (!formKey) continue;
            var tagsText = String(formRow.length > 1 ? (formRow[1] || '') : '').trim();
            var tags = tagsText ? tagsText.split(';').filter(Boolean) : [];
            if (!byFormKey[formKey]) byFormKey[formKey] = [];
            byFormKey[formKey].push({
              row: row,
              form_text: formText,
              tags: tags
            });
          }
        }
      } catch (_e) {}
    }
  }
  return {
    headers: Array.isArray(headers) ? headers.slice() : [],
    by_identity: byIdentity,
    by_headword: byHeadword,
    by_lookup_key: byLookupKey,
    by_form_key: byFormKey,
    by_line: byLine
  };
}

function decodeGzipBytesToText(gzBytes) {
  if (!gzBytes || !gzBytes.length) return Promise.resolve('');
  if (typeof DecompressionStream !== 'function') {
    return Promise.reject(new Error('DecompressionStream is not available in this browser.'));
  }
  var ds = new DecompressionStream('gzip');
  var blob = new Blob([gzBytes], { type: 'application/gzip' });
  var stream = blob.stream().pipeThrough(ds);
  return new Response(stream).text();
}

function ensureDebugDictionaryContext(langCode) {
  var code = normalizeLangCode(langCode);
  if (!code) return Promise.resolve(null);

  var cached = debugDictContextByLang[code];
  if (cached && cached.ready && cached.engine) return Promise.resolve(cached);
  if (cached && cached.promise) return cached.promise;

  var holder = {};
  var promise = fetch('/api/dict/' + encodeURIComponent(code), { cache: 'no-store' })
    .then(function(resp) {
      if (!resp.ok) throw new Error('Dictionary fetch failed for ' + code + ' (' + resp.status + ')');
      return resp.arrayBuffer();
    })
    .then(function(buf) {
      return decodeGzipBytesToText(new Uint8Array(buf));
    })
    .then(function(tsvText) {
      var parsed = parseTsvWithHeaders(tsvText);
      if (!parsed.rows.length) throw new Error('Dictionary TSV is empty for ' + code);
      if (!window.DictionaryEngine) throw new Error('DictionaryEngine is unavailable in debug page.');
      var engine = new window.DictionaryEngine(code);
      engine.load_tsv_entries(parsed.rows);
      var rowIndex = buildRawRowIndex(parsed.rows, parsed.headers);
      var ctx = {
        ready: true,
        lang: code,
        engine: engine,
        row_index: rowIndex,
        row_count: parsed.rows.length
      };
      debugDictContextByLang[code] = ctx;
      return ctx;
    })
    .catch(function(err) {
      delete debugDictContextByLang[code];
      throw err;
    });

  holder.promise = promise;
  debugDictContextByLang[code] = holder;
  return promise;
}

function buildUdOverlayFromTrankitRows(payload) {
  if (!payload || typeof payload !== 'object') return;
  var existing = payload.ud_overlay;
  if (existing && Array.isArray(existing.tokens) && existing.tokens.length) return;
  var rows = Array.isArray(payload.trankit_tokens) ? payload.trankit_tokens : [];
  if (!rows.length) return;
  var tokens = [];
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i] || {};
    tokens.push({
      i: i,
      text: String(r.text || ''),
      lemma: String(r.lemma || ''),
      upos: String(r.upos || 'X'),
      dep: String(r.deprel || 'dep'),
      tag: String(r.xpos || ''),
      feats: ''
    });
  }
  payload.ud_overlay = {
    ok: true,
    tokens: tokens,
    edges: [],
    roots: [],
    ents: [],
    sentences: [],
    doc2seg: [],
    seg2doc: []
  };
}

function resolveLookupPayloadForDebug(data) {
  var base = clonePlainObject(data || {});
  var hasSegments = Array.isArray(base.segments) && base.segments.length;
  if (hasSegments) {
    buildUdOverlayFromTrankitRows(base);
    return Promise.resolve(base);
  }

  var text = String(base.original_text || '').trim();
  var lang = normalizeLangCode(base.language || '');
  if (!text || !lang) return Promise.resolve(base);

  var stampKey = String(base._timestamp || '') + '|' + lang + '|' + text;
  if (debugLookupReplayPromiseByStamp[stampKey]) {
    return debugLookupReplayPromiseByStamp[stampKey].then(function(lookupPayload) {
      var merged = clonePlainObject(base);
      var src = lookupPayload || {};
      var passKeys = [
        'q', 'display_text', 'segments', 'segment_offsets', 'results',
        'results_by_seg', 'ud_overlay', 'grammar_overlay', 'mwt_meta', 'language'
      ];
      for (var i = 0; i < passKeys.length; i++) {
        var k = passKeys[i];
        if (Object.prototype.hasOwnProperty.call(src, k)) merged[k] = src[k];
      }
      buildUdOverlayFromTrankitRows(merged);
      return merged;
    });
  }

  var replayPromise = fetch('/lookup?q=' + encodeURIComponent(text) + '&lang=' + encodeURIComponent(lang), { cache: 'no-store' })
    .then(function(resp) {
      if (!resp.ok) throw new Error('Lookup replay failed (' + resp.status + ')');
      return resp.json();
    })
    .then(function(payload) {
      if (!payload || !payload.ok) {
        var errMsg = payload && payload.error ? payload.error : 'lookup replay returned no data';
        throw new Error(String(errMsg));
      }
      return payload;
    })
    .finally(function() {
      delete debugLookupReplayPromiseByStamp[stampKey];
    });

  debugLookupReplayPromiseByStamp[stampKey] = replayPromise;

  return replayPromise.then(function(lookupPayload) {
    var merged = clonePlainObject(base);
    var src = lookupPayload || {};
    var passKeys = [
      'q', 'display_text', 'segments', 'segment_offsets', 'results',
      'results_by_seg', 'ud_overlay', 'grammar_overlay', 'mwt_meta', 'language'
    ];
    for (var i = 0; i < passKeys.length; i++) {
      var k = passKeys[i];
      if (Object.prototype.hasOwnProperty.call(src, k)) merged[k] = src[k];
    }
    buildUdOverlayFromTrankitRows(merged);
    return merged;
  }).catch(function() {
    buildUdOverlayFromTrankitRows(base);
    return base;
  });
}

function collectCandidateEntriesForFill(fillPiece, uiEntry, engine) {
  if (!engine || typeof engine.lookup_all !== 'function') return [];
  var queries = [];
  var seenQ = Object.create(null);

  function pushQuery(raw) {
    var txt = String(raw || '').trim();
    if (!txt || seenQ[txt]) return;
    seenQ[txt] = true;
    queries.push(txt);
    if (txt.indexOf('+') >= 0) {
      var parts = txt.split('+');
      for (var pi = 0; pi < parts.length; pi++) {
        var part = String(parts[pi] || '').trim();
        if (!part || seenQ[part]) continue;
        seenQ[part] = true;
        queries.push(part);
      }
    }
  }

  function addEntries(entries, out, seenEntries) {
    var list = Array.isArray(entries) ? entries : [];
    for (var i = 0; i < list.length; i++) {
      var ent = list[i];
      if (!ent || typeof ent !== 'object') continue;
      var key = entryIdentityKeyForDebug(ent);
      if (!key) key = String(ent.headword || '') + '\t' + String(ent.pos_raw || '') + '\t' + String(i);
      if (seenEntries[key]) continue;
      seenEntries[key] = true;
      out.push(ent);
    }
  }

  var fillObj = (fillPiece && typeof fillPiece === 'object') ? fillPiece : {};
  pushQuery(fillObj.text);
  pushQuery(fillObj.head);
  pushQuery(fillObj.surface_form);
  pushQuery(fillObj.lemma_form);
  pushQuery(fillObj.lemma);

  if (uiEntry && typeof uiEntry === 'object' && !queries.length) {
    pushQuery(uiEntry.head);
    pushQuery(uiEntry.lemma_form);
    pushQuery(uiEntry.lemma);
    pushQuery(uiEntry.surface_form);
  }

  var out = [];
  var seenEntries = Object.create(null);
  addEntries(fillObj.entries, out, seenEntries);

  // Prefer exact fill-provided entry list. Only probe lookup routes when
  // fill metadata did not include entries.
  if (out.length) return out;

  for (var i = 0; i < queries.length; i++) {
    var q = queries[i];
    var entries = [];
    try {
      entries = engine.lookup_all(q) || [];
    } catch (_e) {
      entries = [];
    }
    addEntries(entries, out, seenEntries);
  }
  return out;
}

function collectUiHeadwordHints(uiEntry) {
  var hints = [];
  var seen = Object.create(null);
  if (!uiEntry || typeof uiEntry !== 'object') return hints;

  function addHint(head, reading) {
    var h = String(head || '').trim();
    if (!h || seen[h]) return;
    seen[h] = true;
    hints.push({ headword: h, reading: String(reading || '').trim() });
  }

  addHint(uiEntry.head, uiEntry.roman);

  var groupLists = [
    uiEntry.entry_groups,
    uiEntry.entry_groups_hover,
    uiEntry.entry_groups_other
  ];
  for (var gi = 0; gi < groupLists.length; gi++) {
    var groups = Array.isArray(groupLists[gi]) ? groupLists[gi] : [];
    for (var i = 0; i < groups.length; i++) {
      var g = groups[i] || {};
      addHint(g.headword, g.reading);
      var posGroups = Array.isArray(g.pos_groups) ? g.pos_groups : [];
      for (var pi = 0; pi < posGroups.length; pi++) {
        var pg = posGroups[pi] || {};
        addHint(pg.headword || g.headword, pg.reading || g.reading);
      }
    }
  }
  return hints;
}

function resolveRawRowsForUiHints(uiEntry, rowIndex) {
  var idx = rowIndex || {};
  var byHead = idx.by_headword || {};
  var hints = collectUiHeadwordHints(uiEntry);
  var out = [];
  var seenRows = Object.create(null);

  for (var i = 0; i < hints.length; i++) {
    var hint = hints[i] || {};
    var head = String(hint.headword || '').trim();
    if (!head) continue;
    var rows = byHead[head] || [];
    if (!rows.length) continue;
    var reading = String(hint.reading || '').trim();
    var subset = rows;
    if (reading) {
      var filtered = [];
      for (var ri = 0; ri < rows.length; ri++) {
        var row = rows[ri] || {};
        var rowReading = String(row.romanization || row.reading || '').trim();
        if (!rowReading || rowReading === reading) filtered.push(row);
      }
      if (filtered.length) subset = filtered;
    }
    for (var si = 0; si < subset.length; si++) {
      var rw = subset[si] || {};
      var rowKey = String(rw.__line_no || '') + '\t' + String(rw.headword || '') + '\t' + String(rw.pos || rw.pos_raw || '');
      if (seenRows[rowKey]) continue;
      seenRows[rowKey] = true;
      out.push(rw);
    }
  }
  return out;
}

function buildFillPiecesForComparison(uiEntry) {
  var out = [];
  if (!uiEntry || typeof uiEntry !== 'object') return out;
  var fill = Array.isArray(uiEntry.dict_fill) ? uiEntry.dict_fill : [];
  for (var i = 0; i < fill.length; i++) {
    var piece = fill[i];
    if (!piece || typeof piece !== 'object') continue;
    out.push(piece);
  }
  if (!out.length) {
    out.push({
      text: String(uiEntry.surface_form || uiEntry.head || ''),
      head: String(uiEntry.head || ''),
      roman: String(uiEntry.roman || ''),
      source: String(uiEntry.source || ''),
      pos: String(uiEntry.pos || uiEntry.upos || ''),
      entry_groups: uiEntry.entry_groups || [],
      entry_groups_hover: uiEntry.entry_groups_hover || [],
      entry_groups_other: uiEntry.entry_groups_other || []
    });
  }
  return out;
}

function resolveVariantFormRowsForFill(fillPiece, rowIndex, fallbackSurface) {
  var idx = rowIndex || {};
  var byForm = idx.by_form_key || {};
  var surfaces = [];
  var seenSurface = Object.create(null);

  function addSurface(raw) {
    var txt = String(raw || '').trim();
    if (!txt || seenSurface[txt]) return;
    seenSurface[txt] = true;
    surfaces.push(txt);
    if (txt.indexOf('+') >= 0) {
      var parts = txt.split('+');
      for (var i = 0; i < parts.length; i++) {
        var part = String(parts[i] || '').trim();
        if (!part || seenSurface[part]) continue;
        seenSurface[part] = true;
        surfaces.push(part);
      }
    }
  }

  var fillObj = (fillPiece && typeof fillPiece === 'object') ? fillPiece : {};
  addSurface(fillObj.text);
  addSurface(fillObj.surface_form);
  if (!surfaces.length) {
    addSurface(fallbackSurface);
  }

  var out = [];
  var hitsByRowKey = Object.create(null);
  var seenRows = Object.create(null);
  for (var si = 0; si < surfaces.length; si++) {
    var surface = surfaces[si];
    var key = lookupKeyForDebug(surface);
    if (!key) continue;
    var formHits = byForm[key] || [];
    for (var ri = 0; ri < formHits.length; ri++) {
      var hit = formHits[ri] || {};
      var row = hit.row || {};
      var rowKey = String(row.__line_no || '') + '\t' + String(row.headword || '') + '\t' + String(row.pos || row.pos_raw || '');
      if (!hitsByRowKey[rowKey]) hitsByRowKey[rowKey] = [];
      hitsByRowKey[rowKey].push({
        source_surface: surface,
        form_text: String(hit.form_text || ''),
        tags: Array.isArray(hit.tags) ? hit.tags.slice() : []
      });
      if (seenRows[rowKey]) continue;
      seenRows[rowKey] = true;
      out.push(row);
    }
  }
  return {
    rows: out,
    hits_by_row_key: hitsByRowKey
  };
}

function resolveRawRowsForEntries(entries, rowIndex, strictIdentity) {
  var idx = rowIndex || {};
  var byIdentity = idx.by_identity || {};
  var byHead = idx.by_headword || {};
  var out = [];
  var seenRows = Object.create(null);
  var strict = !!strictIdentity;

  for (var i = 0; i < (entries || []).length; i++) {
    var ent = entries[i] || {};
    var key = entryIdentityKeyForDebug(ent);
    var rows = byIdentity[key] || [];
    if (!rows.length && !strict) {
      var head = String(ent.headword || '').trim();
      if (head && byHead[head]) {
        // Fallback by headword when identity key lookup misses.
        // Keep fallback narrow by preferring same reading/POS when available.
        var pool = byHead[head] || [];
        var entReading = String(ent.reading || ent.romanization || '').trim();
        var entPos = String(ent.pos_raw || ent.pos || '').trim();
        var filtered = [];
        for (var pi = 0; pi < pool.length; pi++) {
          var prow = pool[pi] || {};
          var rowReading = String(prow.romanization || prow.reading || '').trim();
          var rowPos = String(prow.pos || prow.pos_raw || '').trim();
          if (entReading && rowReading && rowReading !== entReading) continue;
          if (entPos && rowPos && rowPos !== entPos) continue;
          filtered.push(prow);
        }
        rows = filtered.length ? filtered : pool;
      }
    }
    for (var j = 0; j < rows.length; j++) {
      var row = rows[j] || {};
      // Use stable TSV row identity so one physical row cannot be appended twice
      // when reached via multiple candidate-entry routes.
      var rowKey = String(row.__line_no || '') + '\t' + String(row.headword || '') + '\t' + String(row.pos || row.pos_raw || '');
      if (seenRows[rowKey]) continue;
      seenRows[rowKey] = true;
      out.push(row);
    }
  }
  return out;
}

function rowKeyForCompare(row) {
  return String((row && row.__line_no) || '') + '\t' + String((row && row.headword) || '') + '\t' + String((row && (row.pos || row.pos_raw)) || '');
}

function parseDebugLineNoForCompare(raw) {
  var n = parseInt(String(raw == null ? '' : raw), 10);
  if (!isFinite(n) || n <= 0) return 0;
  return n;
}

function resolveRawRowForDebugRef(ref, rowIndex) {
  var r = (ref && typeof ref === 'object') ? ref : {};
  var idx = rowIndex || {};
  var byLine = idx.by_line || {};
  var byIdentity = idx.by_identity || {};
  var byHead = idx.by_headword || {};

  var lineNo = parseDebugLineNoForCompare(r.line_no);
  if (lineNo && byLine[lineNo]) return byLine[lineNo];

  var identity = String(r.identity || '').trim();
  if (identity && Array.isArray(byIdentity[identity]) && byIdentity[identity].length) {
    var identityRows = byIdentity[identity];
    if (identityRows.length === 1) return identityRows[0];
    var refReading = String(r.reading || '').trim();
    var refPos = String(r.pos_raw || r.pos || '').trim();
    for (var i = 0; i < identityRows.length; i++) {
      var cand = identityRows[i] || {};
      var candPos = String(cand.pos || cand.pos_raw || '').trim();
      var candReading = String(cand.romanization || cand.reading || '').trim();
      if (refPos && candPos && refPos !== candPos) continue;
      if (refReading && candReading && refReading !== candReading) continue;
      return cand;
    }
    return identityRows[0];
  }

  var head = String(r.headword || '').trim();
  if (!head) return null;
  var headRows = byHead[head] || [];
  if (!headRows.length) return null;
  var pos = String(r.pos_raw || r.pos || '').trim();
  var reading = String(r.reading || '').trim();
  for (var j = 0; j < headRows.length; j++) {
    var row = headRows[j] || {};
    var rowPos = String(row.pos || row.pos_raw || '').trim();
    var rowReading = String(row.romanization || row.reading || '').trim();
    if (pos && rowPos && rowPos !== pos) continue;
    if (reading && rowReading && rowReading !== reading) continue;
    return row;
  }
  return headRows[0] || null;
}

function resolveRawRowsForDebugRefs(refs, rowIndex) {
  var out = [];
  var seen = Object.create(null);
  var list = Array.isArray(refs) ? refs : [];
  for (var i = 0; i < list.length; i++) {
    var row = resolveRawRowForDebugRef(list[i], rowIndex);
    if (!row) continue;
    var key = rowKeyForCompare(row);
    if (!key || seen[key]) continue;
    seen[key] = true;
    out.push(row);
  }
  return out;
}

function rowKeySetFromDebugRefs(refs, rowIndex) {
  var setObj = Object.create(null);
  var rows = resolveRawRowsForDebugRefs(refs, rowIndex);
  for (var i = 0; i < rows.length; i++) {
    var key = rowKeyForCompare(rows[i]);
    if (key) setObj[key] = true;
  }
  return setObj;
}

function hasOwnKeys(obj) {
  if (!obj || typeof obj !== 'object') return false;
  for (var k in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, k)) return true;
  }
  return false;
}

function addGroupIdentity(setObj, head, reading) {
  var h = String(head || '').trim();
  if (!h) return;
  var r = String(reading || '').trim();
  setObj[h + '\t' + r] = true;
  setObj[h + '\t'] = true;
}

function collectGroupIdentityKeys(groups, outSet) {
  var list = Array.isArray(groups) ? groups : [];
  for (var i = 0; i < list.length; i++) {
    var g = list[i] || {};
    addGroupIdentity(outSet, g.headword, g.reading);
    var posGroups = Array.isArray(g.pos_groups) ? g.pos_groups : [];
    for (var pi = 0; pi < posGroups.length; pi++) {
      var pg = posGroups[pi] || {};
      addGroupIdentity(outSet, pg.headword || g.headword, pg.reading || g.reading);
    }
  }
}

function buildUiGroupStatusSets(uiEntry) {
  var shown = Object.create(null);
  var filtered = Object.create(null);
  if (!uiEntry || typeof uiEntry !== 'object') {
    return { shown: shown, filtered: filtered };
  }
  collectGroupIdentityKeys(uiEntry.entry_groups_hover, shown);
  collectGroupIdentityKeys(uiEntry.entry_groups_other, filtered);
  if (!hasOwnKeys(shown)) {
    collectGroupIdentityKeys(uiEntry.entry_groups, shown);
  }
  return { shown: shown, filtered: filtered };
}

function rowMatchesIdentitySet(row, identitySet) {
  if (!row || typeof row !== 'object' || !identitySet) return false;
  var head = String(row.headword || '').trim();
  if (!head) return false;
  var roman = String(row.romanization || row.reading || '').trim();
  return !!(identitySet[head + '\t' + roman] || identitySet[head + '\t']);
}

function etymKeyForDebug(entry) {
  var e = entry || {};
  if (window.DictionaryEngine && typeof window.DictionaryEngine.etymKey === 'function') {
    try {
      return String(window.DictionaryEngine.etymKey(e) || '');
    } catch (_e) {}
  }
  return 't:' + String(e.etymology || '');
}

function hasExplicitEtymologyForDebug(entry) {
  var e = entry || {};
  var etymText = String(e.etymology || '').trim();
  var etymNum = Number(e.etymology_number || 0);
  return !!etymText || (isFinite(etymNum) && etymNum > 0);
}

function buildEntryFallbackSignatureForDebug(entry) {
  var e = entry || {};
  var head = String(e.headword || '').trim();
  var posRaw = String(e.pos_raw || e.pos || '').trim();
  var reading = String(e.reading || '').trim();
  var senses = Array.isArray(e.senses) ? e.senses : [];
  var firstSense = senses.length ? String(senses[0] || '').trim() : '';
  var sensesFull = Array.isArray(e.senses_full) ? e.senses_full : [];
  var firstSenseTags = '';
  if (sensesFull.length && sensesFull[0] && typeof sensesFull[0] === 'object') {
    var tags = Array.isArray(sensesFull[0].tags) ? sensesFull[0].tags : [];
    if (tags.length) firstSenseTags = tags.map(function(t) { return String(t || '').trim(); }).filter(Boolean).join('|');
  }
  return [head, posRaw, reading, firstSense, firstSenseTags].join('\u241f');
}

function entryGroupBucketKeyForDebug(entry) {
  var base = etymKeyForDebug(entry);
  if (base === 't:' && !hasExplicitEtymologyForDebug(entry)) {
    return base + '|' + buildEntryFallbackSignatureForDebug(entry);
  }
  return base;
}

function entryMatchesGroupForDebug(entry, group) {
  var e = entry || {};
  var g = group || {};
  var eHead = String(e.headword || '').trim();
  var eReading = String(e.reading || '').trim();
  var ePos = String(e.pos_raw || e.pos || '').trim();
  var gHead = String(g.headword || '').trim();
  var gReading = String(g.reading || '').trim();
  var gEtym = String(g.etym_key || '').trim();

  if (gHead && eHead && gHead !== eHead) return false;
  if (gReading && eReading && gReading !== eReading) return false;
  if (gEtym) {
    var eEtym = entryGroupBucketKeyForDebug(e);
    if (eEtym && eEtym !== gEtym) return false;
  }

  var posGroups = Array.isArray(g.pos_groups) ? g.pos_groups : [];
  if (!posGroups.length) return true;
  for (var i = 0; i < posGroups.length; i++) {
    var pg = posGroups[i] || {};
    var pgHead = String(pg.headword || gHead || '').trim();
    var pgReading = String(pg.reading || gReading || '').trim();
    var pgPos = String(pg.pos || '').trim();
    if (pgHead && eHead && pgHead !== eHead) continue;
    if (pgReading && eReading && pgReading !== eReading) continue;
    if (pgPos && ePos && pgPos !== ePos) continue;
    return true;
  }
  return false;
}

function splitEntriesByGroupMembership(entries, groupsShown, groupsFiltered) {
  var shownGroups = Array.isArray(groupsShown) ? groupsShown : [];
  var filteredGroups = Array.isArray(groupsFiltered) ? groupsFiltered : [];
  var shown = [];
  var filtered = [];
  var unmatched = [];

  for (var i = 0; i < (entries || []).length; i++) {
    var ent = entries[i] || {};
    var isShown = false;
    for (var si = 0; si < shownGroups.length; si++) {
      if (entryMatchesGroupForDebug(ent, shownGroups[si])) {
        isShown = true;
        break;
      }
    }
    if (isShown) {
      shown.push(ent);
      continue;
    }
    var isFiltered = false;
    for (var fi = 0; fi < filteredGroups.length; fi++) {
      if (entryMatchesGroupForDebug(ent, filteredGroups[fi])) {
        isFiltered = true;
        break;
      }
    }
    if (isFiltered) filtered.push(ent);
    else unmatched.push(ent);
  }
  return { shown: shown, filtered: filtered, unmatched: unmatched };
}

function toRowKeySet(rows) {
  var out = Object.create(null);
  var list = Array.isArray(rows) ? rows : [];
  for (var i = 0; i < list.length; i++) {
    var key = rowKeyForCompare(list[i]);
    if (key) out[key] = true;
  }
  return out;
}

function normalizeGlossForMatch(raw) {
  var txt = String(raw || '');
  if (!txt) return '';
  txt = txt.replace(/\u001e/g, '').replace(/\u001f/g, ' ');
  txt = txt.replace(/\s+/g, ' ').trim().toLowerCase();
  return txt;
}

function collectGlossSetFromSenseLines(lines) {
  var out = Object.create(null);
  var list = Array.isArray(lines) ? lines : [];
  for (var i = 0; i < list.length; i++) {
    var rawLine = String(list[i] || '');
    if (!rawLine) continue;
    if (rawLine.charAt(0) === '\x1E') continue;
    var parsed = parseDebugSenseLine(rawLine);
    var norm = normalizeGlossForMatch(parsed.gloss || parsed.raw || rawLine);
    if (norm) out[norm] = true;
  }
  return out;
}

function collectRowGlossKeys(row) {
  if (!row || typeof row !== 'object') return [];
  if (Array.isArray(row.__debug_gloss_keys)) return row.__debug_gloss_keys.slice();

  var out = [];
  var seen = Object.create(null);
  function pushGloss(raw) {
    var norm = normalizeGlossForMatch(raw);
    if (!norm || seen[norm]) return;
    seen[norm] = true;
    out.push(norm);
  }

  var rawGloss = String(row.glosses || '').trim();
  if (rawGloss) {
    try {
      var parsed = JSON.parse(rawGloss);
      var items = Array.isArray(parsed) ? parsed : [parsed];
      for (var i = 0; i < items.length; i++) {
        var item = items[i];
        if (typeof item === 'string') {
          pushGloss(item);
          continue;
        }
        if (!item || typeof item !== 'object') continue;
        if (Array.isArray(item.glosses)) {
          for (var gi = 0; gi < item.glosses.length; gi++) {
            pushGloss(item.glosses[gi]);
          }
        } else if (item.gloss != null) {
          pushGloss(item.gloss);
        }
      }
    } catch (_e) {
      pushGloss(rawGloss);
    }
  }

  row.__debug_gloss_keys = out.slice();
  return out;
}

function rowMatchesGlossSet(row, glossSet) {
  if (!glossSet || !hasOwnKeys(glossSet)) return false;
  var keys = collectRowGlossKeys(row);
  for (var i = 0; i < keys.length; i++) {
    if (glossSet[keys[i]]) return true;
  }
  return false;
}

function buildFillGlossSets(fillObj) {
  var fill = (fillObj && typeof fillObj === 'object') ? fillObj : {};
  var shownLines = Array.isArray(fill.senses_hover) && fill.senses_hover.length
    ? fill.senses_hover
    : (Array.isArray(fill.senses) ? fill.senses : []);
  var filteredLines = Array.isArray(fill.senses_hover_other) ? fill.senses_hover_other : [];
  return {
    shown: collectGlossSetFromSenseLines(shownLines),
    filtered: collectGlossSetFromSenseLines(filteredLines)
  };
}

function buildPrimaryRowSet(uiEntry, rawRows) {
  var out = Object.create(null);
  if (!uiEntry || typeof uiEntry !== 'object') return out;
  var targetHead = String(uiEntry.head || '').trim();
  var targetRoman = String(uiEntry.roman || '').trim();
  if (!targetHead) return out;

  var rows = Array.isArray(rawRows) ? rawRows : [];
  var hitCount = 0;
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var rowHead = String(row.headword || '').trim();
    if (!rowHead || rowHead !== targetHead) continue;
    var rowRoman = String(row.romanization || row.reading || '').trim();
    if (targetRoman && rowRoman && rowRoman !== targetRoman) continue;
    out[rowKeyForCompare(row)] = true;
    hitCount += 1;
  }
  return out;
}

function dedupeAndAppendRows(baseRows, extraRows) {
  var out = Array.isArray(baseRows) ? baseRows.slice() : [];
  var seen = Object.create(null);
  for (var i = 0; i < out.length; i++) {
    seen[rowKeyForCompare(out[i])] = true;
  }
  var extras = Array.isArray(extraRows) ? extraRows : [];
  for (var j = 0; j < extras.length; j++) {
    var row = extras[j] || {};
    var key = rowKeyForCompare(row);
    if (!key || seen[key]) continue;
    seen[key] = true;
    out.push(row);
  }
  return out;
}

function buildTsvComparisonRows(segments, resultsBySeg, engine, rowIndex) {
  var segs = Array.isArray(segments) ? segments : [];
  var rows = [];
  for (var i = 0; i < segs.length; i++) {
    var token = String(segs[i] || '');
    var uiEntry = (Array.isArray(resultsBySeg) && i < resultsBySeg.length) ? (resultsBySeg[i] || null) : null;
    var fillPieces = buildFillPiecesForComparison(uiEntry);
    var fillRows = [];
    var candidateTotal = 0;
    var flatRawRows = [];
    var flatSeen = Object.create(null);

    for (var fi = 0; fi < fillPieces.length; fi++) {
      var fillObj = fillPieces[fi] || {};
      var fillSurface = String(fillObj.text || fillObj.surface_form || token || '').trim();
      var rowStatusMap = Object.create(null);
      var hitMap = Object.create(null);
      var rawRows = [];
      var candidateCount = 0;

      var liveRefsAll = Array.isArray(fillObj._debug_entry_refs_all) ? fillObj._debug_entry_refs_all : [];
      var liveRefsShown = Array.isArray(fillObj._debug_entry_refs_shown) ? fillObj._debug_entry_refs_shown : [];
      var liveRefsFiltered = Array.isArray(fillObj._debug_entry_refs_filtered) ? fillObj._debug_entry_refs_filtered : [];
      var hasLiveTrace = !!(liveRefsAll.length || liveRefsShown.length || liveRefsFiltered.length);

      if (hasLiveTrace) {
        candidateCount = liveRefsAll.length;
        candidateTotal += candidateCount;

        rawRows = resolveRawRowsForDebugRefs(liveRefsAll, rowIndex);
        var shownRows = resolveRawRowsForDebugRefs(liveRefsShown, rowIndex);
        var filteredRows = resolveRawRowsForDebugRefs(liveRefsFiltered, rowIndex);
        rawRows = dedupeAndAppendRows(rawRows, shownRows);
        rawRows = dedupeAndAppendRows(rawRows, filteredRows);

        var shownSet = toRowKeySet(shownRows);
        var filteredSet = toRowKeySet(filteredRows);
        for (var lri = 0; lri < rawRows.length; lri++) {
          var lrow = rawRows[lri] || {};
          var lrk = rowKeyForCompare(lrow);
          var liveStatus = 'unmatched';
          if (shownSet[lrk]) liveStatus = 'shown';
          else if (filteredSet[lrk]) liveStatus = 'filtered_out';
          rowStatusMap[lrk] = liveStatus;
        }

        function addLiveVariantHits(refs) {
          var list = Array.isArray(refs) ? refs : [];
          for (var hri = 0; hri < list.length; hri++) {
            var href = list[hri] || {};
            var morphBase = String(href.morph_base || '').trim();
            var morphInfo = Array.isArray(href.morph_info) ? href.morph_info.slice() : [];
            var cleanedTags = [];
            for (var mti = 0; mti < morphInfo.length; mti++) {
              var mt = String(morphInfo[mti] || '').trim();
              if (mt) cleanedTags.push(mt);
            }
            if (!morphBase && !cleanedTags.length) continue;
            var hrow = resolveRawRowForDebugRef(href, rowIndex);
            if (!hrow) continue;
            var hrk = rowKeyForCompare(hrow);
            if (!hrk) continue;
            if (!hitMap[hrk]) hitMap[hrk] = [];
            hitMap[hrk].push({
              source_surface: fillSurface,
              form_text: morphBase || String(href.headword || '').trim(),
              tags: cleanedTags
            });
          }
        }

        addLiveVariantHits(liveRefsShown);
        addLiveVariantHits(liveRefsFiltered);
        addLiveVariantHits(liveRefsAll);
      } else {
        var candidateEntries = collectCandidateEntriesForFill(fillObj, uiEntry, engine);
        candidateCount = candidateEntries.length;
        candidateTotal += candidateCount;

        rawRows = resolveRawRowsForEntries(candidateEntries, rowIndex, false);
        var uiHintRows = resolveRawRowsForUiHints(fillObj, rowIndex);
        var variantFormData = resolveVariantFormRowsForFill(fillObj, rowIndex, fillSurface);
        var variantFormRows = Array.isArray(variantFormData.rows) ? variantFormData.rows : [];
        rawRows = dedupeAndAppendRows(rawRows, variantFormRows);
        rawRows = dedupeAndAppendRows(rawRows, uiHintRows);

        var shownLines = Array.isArray(fillObj.senses) ? fillObj.senses : [];
        var filteredLines = Array.isArray(fillObj.senses_hover_other) ? fillObj.senses_hover_other : [];
        var shownGlossSet = collectGlossSetFromSenseLines(shownLines);
        var filteredGlossSet = collectGlossSetFromSenseLines(filteredLines);
        for (var ri = 0; ri < rawRows.length; ri++) {
          var rr = rawRows[ri] || {};
          var rk = rowKeyForCompare(rr);
          var status = 'unmatched';
          var shownByGloss = rowMatchesGlossSet(rr, shownGlossSet);
          var filteredByGloss = rowMatchesGlossSet(rr, filteredGlossSet);
          if (shownByGloss) {
            status = 'shown';
          } else if (filteredByGloss) {
            status = 'filtered_out';
          }
          rowStatusMap[rk] = status;
        }

        hitMap = (variantFormData && variantFormData.hits_by_row_key) ? variantFormData.hits_by_row_key : {};
      }

      rawRows.sort(function(a, b) {
        var ak = rowKeyForCompare(a);
        var bk = rowKeyForCompare(b);
        var as = rowStatusMap[ak] || 'unmatched';
        var bs = rowStatusMap[bk] || 'unmatched';
        var ah = Array.isArray(hitMap[ak]) ? hitMap[ak].length : 0;
        var bh = Array.isArray(hitMap[bk]) ? hitMap[bk].length : 0;
        var ascore = (as === 'shown' || as === 'primary') ? 1 : (as === 'filtered_out') ? 2 : 3;
        var bscore = (bs === 'shown' || bs === 'primary') ? 1 : (bs === 'filtered_out') ? 2 : 3;
        if (ascore !== bscore) return ascore - bscore;
        if (!!ah !== !!bh) return ah ? -1 : 1;
        if (ah !== bh) return bh - ah;
        var aline = Number((a && a.__line_no) || 0);
        var bline = Number((b && b.__line_no) || 0);
        return aline - bline;
      });

      fillRows.push({
        fill_i: fi,
        fill_piece: fillObj,
        fill_surface: fillSurface,
        candidate_entry_count: candidateCount,
        raw_rows: rawRows,
        row_status_map: rowStatusMap,
        variant_form_hits: hitMap
      });

      for (var fr = 0; fr < rawRows.length; fr++) {
        var rawRow = rawRows[fr] || {};
        var flatKey = rowKeyForCompare(rawRow);
        if (!flatKey || flatSeen[flatKey]) continue;
        flatSeen[flatKey] = true;
        flatRawRows.push(rawRow);
      }
    }

    rows.push({
      seg_i: i,
      token: token,
      ui_entry: uiEntry,
      candidate_entry_count: candidateTotal,
      fill_row_count: fillRows.length,
      fill_rows: fillRows,
      raw_rows: flatRawRows
    });
  }
  return rows;
}

function enrichDebugPayloadWithDictionary(data) {
  var base = clonePlainObject(data || {});
  if (Array.isArray(base.debug_ui_results_by_seg) && base.debug_ui_results_by_seg.length) {
    return Promise.resolve(base);
  }
  return resolveLookupPayloadForDebug(base).then(function(payloadForMerge) {
    var lang = normalizeLangCode((payloadForMerge && payloadForMerge.language) || base.language || '');
    if (!lang) return payloadForMerge || base;

    if (!window.DictionaryClient || typeof window.DictionaryClient.buildMergedLookupPayload !== 'function') {
      return payloadForMerge || base;
    }

    return ensureDebugDictionaryContext(lang).then(function(ctx) {
      // dictionary_client helpers key some language-specific behavior off
      // ReaderDefaultLanguage when no language dropdown exists (debug page).
      window.ReaderDefaultLanguage = lang;
      var merged = window.DictionaryClient.buildMergedLookupPayload(
        payloadForMerge || base,
        ctx.engine,
        { debug_trace: true }
      );
      var out = clonePlainObject(payloadForMerge || base);
      out.debug_ui_results_by_seg = Array.isArray(merged && merged.results_by_seg) ? merged.results_by_seg : [];
      out.debug_ui_results = Array.isArray(merged && merged.results) ? merged.results : [];
      return out;
    }).catch(function(err) {
      void err;
      return payloadForMerge || base;
    });
  });
}

function handleGreedyWordKeydown(ev) {
  if (ev && ev.key === 'Enter') runGreedyProbe();
}

function runGreedyProbe() {
  var wordInput = document.getElementById('greedyWordInput');
  var langInput = document.getElementById('greedyLangInput');
  var uposInput = document.getElementById('greedyUposInput');
  var meta = document.getElementById('greedyProbeMeta');
  var body = document.getElementById('greedyProbeBody');

  var token = wordInput ? (wordInput.value || '').trim() : '';
  var lang = (currentProbeLang || '').trim().toLowerCase();
  if (!lang && langInput) {
    lang = (langInput.value || '').trim().toLowerCase();
  }
  var upos = uposInput ? (uposInput.value || '').trim().toUpperCase() : '';
  if (!lang) lang = 'vi';
  if (langInput) langInput.value = lang;

  if (!token) {
    if (meta) meta.textContent = 'Enter a word/token first.';
    if (body) body.innerHTML = '<span class="dict-unknown">No token provided.</span>';
    return;
  }

  if (meta) meta.textContent = 'Running greedy scorer...';
  if (body) body.innerHTML = '<span style="color:#a6adc8;">Loading...</span>';

  var url = '/debug/greedy_score?q=' + encodeURIComponent(token) + '&lang=' + encodeURIComponent(lang);
  if (upos) url += '&upos=' + encodeURIComponent(upos);

  fetch(url)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data || !data.ok) {
        var err = (data && data.error) ? data.error : 'Probe failed';
        if (meta) meta.textContent = 'Probe failed';
        if (body) body.innerHTML = '<span class="dict-unknown">' + esc(err) + '</span>';
        return;
      }
      currentProbeLang = data.language || lang;
      if (langInput) langInput.value = currentProbeLang;
      if (meta) {
        meta.textContent = 'lang=' + (data.language || '?') + ' | token=' + (data.q || '') + ' | mode=' + ((data.greedy_result || {}).mode || '');
      }
      if (body) body.innerHTML = renderGreedyProbe(data);
    })
    .catch(function(e) {
      if (meta) meta.textContent = 'Probe failed';
      if (body) body.innerHTML = '<span class="dict-unknown">' + esc(String(e || 'Request failed')) + '</span>';
    });
}

function renderGreedyProbe(data) {
  var html = '';
  var exact = data.exact_match || {};
  html += '<div class="dict-entry">';
  html += '<div><span class="head">' + esc(data.q || '') + '</span>';
  html += '<span class="roman">lang=' + esc(data.language || '') + '</span></div>';
  html += '<div class="sense">exact found=' + esc(exact.found ? 'yes' : 'no') + ' | count=' + esc(exact.count != null ? exact.count : 0) + '</div>';
  if (exact.top_head) {
    html += '<div class="sense">top exact: ' + esc(exact.top_head) + (exact.top_pos ? (' [' + esc(exact.top_pos) + ']') : '') + '</div>';
  }
  if (data.note) {
    html += '<div class="sense" style="color:#f9e2af;">' + esc(data.note) + '</div>';
  }
  html += '</div>';

  var preview = Array.isArray(data.fill_preview) ? data.fill_preview : [];
  if (preview.length) {
    html += '<table><thead><tr>';
    html += '<th>#</th><th>Text</th><th>Head</th><th>Source</th><th>POS</th><th>Senses</th><th>Details</th>';
    html += '</tr></thead><tbody>';
    for (var i = 0; i < preview.length; i++) {
      var row = preview[i] || {};
      var detailBits = [];
      if (row.xpos_hint) detailBits.push('x=' + String(row.xpos_hint));
      if (row.effective_upos) detailBits.push('u=' + String(row.effective_upos));
      if (row.effective_xpos) detailBits.push('x*=' + String(row.effective_xpos));
      if (row.lemma_upos_hint || row.lemma_xpos_hint) {
        detailBits.push('lemma=' + String(row.lemma_upos_hint || '') + '/' + String(row.lemma_xpos_hint || ''));
      }
      if (row.lemma_promoted) detailBits.push('picked=' + String(row.lemma_promoted));
      html += '<tr>';
      html += '<td>' + esc(row.index != null ? row.index : i) + '</td>';
      html += '<td class="tok-text">' + esc(row.text || '') + '</td>';
      html += '<td>' + esc(row.head || '') + '</td>';
      html += '<td>' + esc(row.source || '') + '</td>';
      html += '<td>' + esc(row.pos || '') + '</td>';
      html += '<td>' + esc(row.sense_count != null ? row.sense_count : 0) + '</td>';
      html += '<td>' + esc(detailBits.join(' | ')) + '</td>';
      html += '</tr>';
    }
    html += '</tbody></table>';
  } else {
    html += '<div class="dict-unknown" style="margin:8px 0;">No fill pieces returned.</div>';
  }

  var score = data.score_breakdown || null;
  if (score && Array.isArray(score.steps) && score.steps.length) {
    html += '<div class="dict-entry">';
    html += '<div class="sense">final DP score: <span class="probe-score">' + esc(formatScore(score.final_score)) + '</span></div>';
    if (Array.isArray(score.allowed_pos_raw) && score.allowed_pos_raw.length) {
      html += '<div class="sense">allowed POS: ' + esc(score.allowed_pos_raw.join(', ')) + '</div>';
    }
    html += '</div>';

    html += '<table><thead><tr>';
    html += '<th>Start</th><th>Piece</th><th>Kind</th><th>Local</th><th>Future</th><th>Total</th><th>Chosen</th><th>Reason</th><th>Details</th>';
    html += '</tr></thead><tbody>';
    for (var si = 0; si < score.steps.length; si++) {
      var step = score.steps[si] || {};
      var candidates = Array.isArray(step.candidates) ? step.candidates : [];
      if (!candidates.length) continue;
      for (var ci = 0; ci < candidates.length; ci++) {
        var cand = candidates[ci] || {};
        var breakdown = cand.score_breakdown || {};
        var details = [];
        if (Array.isArray(breakdown.pos_set) && breakdown.pos_set.length) {
          details.push('pos=' + breakdown.pos_set.join(','));
        }
        if (Array.isArray(breakdown.allowed_pos_hits) && breakdown.allowed_pos_hits.length) {
          details.push('upos_hit=' + breakdown.allowed_pos_hits.join(','));
        }
        if (Array.isArray(breakdown.affix_pos) && breakdown.affix_pos.length) {
          details.push('affix=' + breakdown.affix_pos.join(','));
        }
        if (breakdown.low_value_only_penalty) {
          details.push('low=' + formatScore(breakdown.low_value_only_penalty));
        }
        if (breakdown.affix_slot_bonus) {
          details.push('affix_bonus=' + formatScore(breakdown.affix_slot_bonus));
        }
        var rowClass = cand.selected ? ' class="probe-selected"' : '';
        html += '<tr' + rowClass + '>';
        html += '<td>' + esc(step.start != null ? step.start : '') + '</td>';
        html += '<td class="tok-text">' + esc(cand.piece || '') + '</td>';
        html += '<td>' + esc(cand.kind || '') + '</td>';
        html += '<td>' + esc(formatScore(cand.local_score)) + '</td>';
        html += '<td>' + esc(formatScore(cand.future_score)) + '</td>';
        html += '<td><span class="probe-score">' + esc(formatScore(cand.total_score)) + '</span></td>';
        html += '<td>' + esc(cand.selected ? 'yes' : 'no') + '</td>';
        html += '<td>' + esc(cand.selection_reason || '') + '</td>';
        html += '<td>' + esc(details.join(' | ')) + '</td>';
        html += '</tr>';
      }
    }
    html += '</tbody></table>';
  }

  html += '<details style="margin-top:8px;"><summary style="cursor:pointer;color:#a6adc8;">Raw JSON</summary>';
  html += '<pre class="json-raw" style="margin-top:8px;">' + esc(JSON.stringify(data, null, 2)) + '</pre>';
  html += '</details>';
  return html;
}

function getDictionaryTraceRows(data) {
  if (!data) return [];
  if (Array.isArray(data.dictionary_decision_trace) && data.dictionary_decision_trace.length) {
    return data.dictionary_decision_trace;
  }
  if (Array.isArray(data.arabic_dictionary_trace) && data.arabic_dictionary_trace.length) {
    return data.arabic_dictionary_trace;
  }
  if (Array.isArray(data.korean_dictionary_trace) && data.korean_dictionary_trace.length) {
    return data.korean_dictionary_trace;
  }
  if (Array.isArray(data.japanese_dictionary_trace) && data.japanese_dictionary_trace.length) {
    return data.japanese_dictionary_trace;
  }
  return [];
}

function dictionaryTraceLabel(lang) {
  if (lang === 'ar') return 'Arabic';
  if (lang === 'ja') return 'Japanese';
  if (lang === 'ko') return 'Korean';
  if (lang === 'vi') return 'Vietnamese';
  return 'Dictionary';
}

function formatUiTraceTime(ts) {
  var n = Number(ts);
  if (!isFinite(n) || !n) return '';
  try {
    return new Date(n * 1000).toLocaleTimeString();
  } catch (_e) {
    return String(ts);
  }
}

function renderUiTraceKvRows(obj, keys) {
  if (!obj) return '<div class="ui-trace-empty">No metadata.</div>';
  var html = '<div class="ui-trace-kv">';
  var wrote = false;
  for (var i = 0; i < keys.length; i++) {
    var key = keys[i];
    var value = obj[key];
    if (value == null || value === '') continue;
    wrote = true;
    if (typeof value === 'object') {
      try { value = JSON.stringify(value); } catch (_err) { value = String(value); }
    }
    html += '<div>' + esc(key) + '</div><div>' + esc(String(value)) + '</div>';
  }
  html += '</div>';
  return wrote ? html : '<div class="ui-trace-empty">No metadata.</div>';
}

function summarizeUiTraceEvent(type, details) {
  var d = details || {};
  if (type === 'token_map_render') {
    return (d.result || 'render') + ' | strategy=' + (d.slice_strategy || 'none') + ' | fills=' + String(d.dict_fill_count || 0);
  }
  if (type === 'panel_surface_decision') {
    return 'source=' + esc(d.source || 'unknown') + ' | exact=' + esc(String(!!d.exact_match));
  }
  if (type === 'panel_surface_upgrade') {
    return 'replaced=' + esc(String(d.replaced_count || 0));
  }
  if (type === 'resolve_token_map_lookup') {
    return 'path=' + esc(d.path || d.reason || 'unknown');
  }
  if (type === 'banner_surface_lookup' || type === 'banner_lemma_lookup') {
    return 'text=' + esc(d.surface || d.lemma || d.text || '');
  }
  if (type === 'wrapper_hover_suppressed') {
    return 'scope=' + esc(d.scope || '') + ' | reason=' + esc(d.reason || '');
  }
  if (type === 'panel_token_hover' || type === 'panel_headword_hover' || type === 'banner_token_hover' || type === 'banner_headword_hover') {
    return 'text=' + esc(d.seg || d.text || '') + ' | fill=' + esc(String(d.fill_index || d.fill_indexes || ''));
  }
  if (type === 'wikt_entry_group_row' || type === 'wikt_meta_head' || type === 'wikt_morph_block' || type === 'wikt_render_entry' || type === 'wikt_plain_headword_span') {
    return 'head=' + esc(d.head || d.headword || d.text || '') + ' | role=' + esc(d.role || d.display_mode || '');
  }
  var parts = [];
  if (d.text) parts.push('text=' + d.text);
  if (d.surface) parts.push('surface=' + d.surface);
  if (d.result) parts.push('result=' + d.result);
  if (d.path) parts.push('path=' + d.path);
  return esc(parts.join(' | '));
}

function renderUiTraceTokenList(tokens) {
  if (!tokens || !tokens.length) return '<div class="ui-trace-empty">No tokens.</div>';
  var html = '<div class="ui-trace-token-row">';
  for (var i = 0; i < tokens.length; i++) {
    var tok = tokens[i] || {};
    var label = tok.text || tok.surface || tok.fill_text || tok.fillText || '';
    if (!label) continue;
    html += '<span class="ui-trace-token-pill">' + esc(label) + '</span>';
  }
  html += '</div>';
  return html;
}

function renderUiTraceHeadlineBlocks(headlines) {
  if (!headlines || !headlines.length) return '<div class="ui-trace-empty">No headline snapshots.</div>';
  var html = '<div class="ui-trace-grid">';
  for (var i = 0; i < headlines.length; i++) {
    var item = headlines[i] || {};
    html += '<div class="ui-trace-card">';
    html += '<div class="ui-trace-meta"><strong>' + esc(item.reason || item.label || ('Snapshot ' + (i + 1))) + '</strong>';
    html += '<span>' + esc(formatUiTraceTime(item.captured_at)) + '</span></div>';
    html += renderUiTraceKvRows(item, ['surface', 'lemma', 'resolved_via', 'source', 'seg_i']);
    if (item.surface_token) {
      html += '<div class="ui-trace-block"><div style="margin-bottom:6px;color:#6c7086;">Surface token</div>';
      html += renderUiTraceTokenList(item.surface_token.fill_hits || []);
      html += '</div>';
    }
    if (item.lemma_token) {
      html += '<div class="ui-trace-block"><div style="margin-bottom:6px;color:#6c7086;">Lemma token</div>';
      html += renderUiTraceTokenList(item.lemma_token.fill_hits || []);
      html += '</div>';
    }
    if (item.html) {
      html += '<details class="ui-trace-panel-details"><summary>Raw HTML</summary><div class="section-body"><div class="ui-trace-html">' + esc(item.html) + '</div></div></details>';
    }
    html += '</div>';
  }
  html += '</div>';
  return html;
}

function renderUiTraceEvents(events, title) {
  if (!events || !events.length) return '<div class="ui-trace-empty">No ' + esc(title || 'events') + '.</div>';
  var html = '<table class="ui-trace-table"><thead><tr><th>Time</th><th>Type</th><th>Summary</th><th>Details</th></tr></thead><tbody>';
  for (var i = 0; i < events.length; i++) {
    var ev = events[i] || {};
    var details = ev.details || {};
    var rawDetails = '';
    try { rawDetails = JSON.stringify(details, null, 2); } catch (_err) { rawDetails = String(details); }
    html += '<tr>';
    html += '<td style="white-space:nowrap;">' + esc(formatUiTraceTime(ev.ts)) + '</td>';
    html += '<td class="ui-trace-type">' + esc(ev.type || '') + '</td>';
    html += '<td class="ui-trace-detail">' + summarizeUiTraceEvent(ev.type || '', details) + '</td>';
    html += '<td><details><summary class="raw-row-summary">details</summary><div class="ui-trace-html">' + esc(rawDetails) + '</div></details></td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

function renderUiRenderTrace(trace) {
  if (!trace || typeof trace !== 'object') {
    return '<div class="ui-trace-empty">No UI render trace captured yet. Turn on Debug capture, open a token, and refresh this page.</div>';
  }
  var panelSessions = Array.isArray(trace.panel_sessions) ? trace.panel_sessions : [];
  var bannerSnapshots = Array.isArray(trace.banner_snapshots) ? trace.banner_snapshots : [];
  var generalEvents = Array.isArray(trace.general_events) ? trace.general_events : [];
  var html = '';
  html += '<div class="ui-trace-summary">';
  html += '<span class="ui-trace-chip">Capture: ' + esc(trace.debug_capture_id || 'none') + '</span>';
  html += '<span class="ui-trace-chip">Lang: ' + esc(trace.current_language || '?') + '</span>';
  html += '<span class="ui-trace-chip">Panel sessions: ' + panelSessions.length + '</span>';
  html += '<span class="ui-trace-chip">Banner snapshots: ' + bannerSnapshots.length + '</span>';
  html += '<span class="ui-trace-chip">General events: ' + generalEvents.length + '</span>';
  html += '<span class="ui-trace-chip">Updated: ' + esc(formatUiTraceTime(trace.updated_at)) + '</span>';
  html += '</div>';

  html += '<div class="section" style="margin-bottom:12px;">';
  html += '<div class="section-head" onclick="toggleSection(this)"><span>Banner Snapshots</span><span>&#9662;</span></div>';
  html += '<div class="section-body">' + renderUiTraceHeadlineBlocks(bannerSnapshots) + '</div></div>';

  html += '<div class="section" style="margin-bottom:12px;">';
  html += '<div class="section-head" onclick="toggleSection(this)"><span>Panel Sessions</span><span>&#9662;</span></div>';
  html += '<div class="section-body">';
  if (!panelSessions.length) {
    html += '<div class="ui-trace-empty">No panel sessions captured yet.</div>';
  } else {
    for (var i = 0; i < panelSessions.length; i++) {
      var session = panelSessions[i] || {};
      var snapshots = Array.isArray(session.snapshots) ? session.snapshots : [];
      var events = Array.isArray(session.events) ? session.events : [];
      html += '<details class="ui-trace-panel-details"' + (i === panelSessions.length - 1 ? ' open' : '') + '>';
      html += '<summary>Session ' + esc(session.id || String(i + 1)) + ' | started ' + esc(formatUiTraceTime(session.started_at)) + ' | events ' + events.length + ' | snapshots ' + snapshots.length + '</summary>';
      html += '<div class="section-body">';
      html += '<div class="ui-trace-card" style="margin-bottom:12px;">';
      html += '<div class="ui-trace-meta"><strong>Session metadata</strong><span>' + esc(session.id || '') + '</span></div>';
      html += renderUiTraceKvRows(session.meta || {}, ['original_token', 'head', 'lookup_lang', 'manual_search', '_panelTokenSurface', '_panelTokenLemma', '_panelTokenLemmaRaw']);
      html += '</div>';
      html += '<div class="ui-trace-card" style="margin-bottom:12px;">';
      html += '<div class="ui-trace-meta"><strong>Snapshots</strong><span>' + snapshots.length + '</span></div>';
      html += renderUiTraceHeadlineBlocks(snapshots);
      html += '</div>';
      html += '<div class="ui-trace-card">';
      html += '<div class="ui-trace-meta"><strong>Events</strong><span>' + events.length + '</span></div>';
      html += renderUiTraceEvents(events, 'session events');
      html += '</div>';
      html += '</div></details>';
    }
  }
  html += '</div></div>';

  html += '<div class="section">';
  html += '<div class="section-head" onclick="toggleSection(this)"><span>General Events</span><span>&#9662;</span></div>';
  html += '<div class="section-body">' + renderUiTraceEvents(generalEvents, 'general events') + '</div></div>';
  return html;
}

function renderLookupTimingTrace(trace) {
  if (!trace || typeof trace !== 'object') {
    return '<div class="backend-trace-empty">No lookup timing trace captured yet. Turn on Debug capture and run a fresh lookup.</div>';
  }
  var totalMs = Number(trace.total_ms || 0);
  var loggedMs = Number(trace.logged_ms || 0);
  var unattributedMs = Number(trace.unattributed_ms || 0);
  var html = '<div class="backend-trace-summary">';
  html += '<span class="backend-trace-chip">Capture: ' + esc(trace.debug_capture_id || 'none') + '</span>';
  html += '<span class="backend-trace-chip">Total: ' + esc(formatMsLabel(totalMs)) + '</span>';
  html += '<span class="backend-trace-chip">Logged: ' + esc(formatMsLabel(loggedMs)) + '</span>';
  html += '<span class="backend-trace-chip">Unattributed: ' + esc(formatMsLabel(unattributedMs)) + '</span>';
  html += '</div>';
  html += renderBackendTimingTree(trace);
  return html;
}

function formatMsLabel(v) {
  var n = Number(v);
  if (!isFinite(n)) return '';
  if (n >= 1000) return (n / 1000).toFixed(2) + ' s';
  return n.toFixed(2) + ' ms';
}

function formatPctLabel(v) {
  var n = Number(v);
  if (!isFinite(n)) return '';
  return n.toFixed(1) + '%';
}

function summarizePlainMeta(meta, maxKeys) {
  if (!meta || typeof meta !== 'object') return '';
  var keys = Object.keys(meta);
  var out = [];
  var limit = Math.max(1, Number(maxKeys) || 4);
  for (var i = 0; i < keys.length; i++) {
    if (out.length >= limit) break;
    var key = keys[i];
    var value = meta[key];
    if (value == null || value === '') continue;
    if (typeof value === 'object') {
      try { value = JSON.stringify(value); } catch (_err) { value = String(value); }
    }
    out.push(key + '=' + String(value));
  }
  return out.join(' | ');
}

function flattenTimingTree(node, totalMs, depth, rows) {
  if (!node || typeof node !== 'object') return;
  var durationMs = Number(node.duration_ms || 0);
  rows.push({
    name: String(node.label || node.name || '').trim(),
    duration_ms: durationMs,
    pct_total: totalMs > 0 ? (durationMs / totalMs) * 100 : 0,
    depth: depth || 0,
    meta: node.meta || {}
  });
  var children = Array.isArray(node.children) ? node.children : [];
  for (var i = 0; i < children.length; i++) {
    flattenTimingTree(children[i], totalMs, (depth || 0) + 1, rows);
  }
}

function renderBackendTimingTree(trace) {
  if (!trace || typeof trace !== 'object' || !trace.timing_tree) {
    return '<div class="backend-trace-empty">No timing trace captured.</div>';
  }
  var totalMs = Number(trace.total_ms || 0);
  var rows = [];
  flattenTimingTree(trace.timing_tree, totalMs, 0, rows);
  if (!rows.length) return '<div class="backend-trace-empty">No timing trace captured.</div>';
  var html = '<div class="backend-trace-block"><h4>Timing Breakdown</h4>';
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var indent = Math.max(0, Number(row.depth || 0)) * 14;
    var widthPct = Math.max(0.8, Math.min(100, Number(row.pct_total || 0)));
    html += '<div class="backend-trace-timing-row">';
    html += '<div class="backend-trace-scope" style="padding-left:' + indent + 'px;">' + esc(row.name || '') + '</div>';
    html += '<div class="backend-trace-ms">' + esc(formatMsLabel(row.duration_ms)) + '</div>';
    html += '<div><div class="backend-trace-bar-wrap"><div class="backend-trace-bar" style="width:' + widthPct + '%;"></div></div></div>';
    html += '<div class="backend-trace-meta">' + esc(formatPctLabel(row.pct_total)) + (row.meta ? (' | ' + esc(summarizePlainMeta(row.meta, 4))) : '') + '</div>';
    html += '</div>';
  }
  html += '</div>';
  return html;
}

function collectBackendNormalizationRows(trace) {
  var rows = [];
  var seen = Object.create(null);
  function pushRow(kind, rawText, normalizedKey, scope, note) {
    var raw = String(rawText || '');
    var norm = String(normalizedKey || '');
    var sig = [kind || '', scope || '', raw, norm, note || ''].join('||');
    if (seen[sig]) return;
    seen[sig] = true;
    rows.push({
      kind: String(kind || ''),
      raw_text: raw,
      normalized_key: norm,
      scope: String(scope || ''),
      note: String(note || ''),
      changed: raw !== norm
    });
  }
  var direct = Array.isArray(trace && trace.normalizations) ? trace.normalizations : [];
  for (var i = 0; i < direct.length; i++) {
    var row = direct[i] || {};
    pushRow(row.kind, row.raw_text, row.normalized_key, row.scope, row.note);
  }
  var segmenterEvents = Array.isArray(trace && trace.segmenter_events) ? trace.segmenter_events : [];
  for (var j = 0; j < segmenterEvents.length; j++) {
    var ev = segmenterEvents[j] || {};
    if (String(ev.kind || '') !== 'span_key_matrix') continue;
    var pairs = Array.isArray(ev.span_pairs) ? ev.span_pairs : [];
    for (var k = 0; k < pairs.length; k++) {
      var pair = pairs[k] || {};
      pushRow('subword_span', pair.text, pair.normalized_key, ev.scope, (pair.start != null && pair.end != null) ? (String(pair.start) + ':' + String(pair.end)) : '');
    }
  }
  return rows;
}

function renderBackendNormalizations(trace) {
  var rows = collectBackendNormalizationRows(trace);
  if (!rows.length) return '<div class="backend-trace-block"><h4>Query Normalization</h4><div class="backend-trace-empty">No normalization rows captured.</div></div>';
  var html = '<div class="backend-trace-block"><h4>Query Normalization</h4><table><thead><tr><th>Kind</th><th>Raw</th><th>Normalized</th><th>Scope</th><th>Note</th></tr></thead><tbody>';
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    html += '<tr>';
    html += '<td>' + esc(row.kind || '') + '</td>';
    html += '<td class="tok-text" style="font-size:13px;">' + esc(row.raw_text || '') + '</td>';
    html += '<td style="color:' + (row.changed ? '#94e2d5' : '#a6adc8') + ';">' + esc(row.normalized_key || '') + '</td>';
    html += '<td>' + esc(row.scope || '') + '</td>';
    html += '<td>' + esc(row.note || '') + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  return html;
}

function renderBackendSqliteQueries(trace) {
  var rows = Array.isArray(trace && trace.sqlite_queries) ? trace.sqlite_queries : [];
  if (!rows.length) return '<div class="backend-trace-block"><h4>SQLite Queries</h4><div class="backend-trace-empty">No SQLite queries captured.</div></div>';
  var html = '<div class="backend-trace-block"><h4>SQLite Queries</h4><table><thead><tr><th>Kind</th><th>Time</th><th>Rows</th><th>DB</th><th>Keys</th><th>SQL</th></tr></thead><tbody>';
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var keys = Array.isArray(row.normalized_keys) ? row.normalized_keys : [];
    html += '<tr>';
    html += '<td>' + esc(row.query_kind || row.scope || '') + '</td>';
    html += '<td style="color:#89dceb;">' + esc(formatMsLabel(row.duration_ms)) + '<div style="font-size:10px;color:#6c7086;">' + esc(formatPctLabel(row.pct_total)) + '</div></td>';
    html += '<td>' + esc(row.row_count != null ? row.row_count : '') + '</td>';
    html += '<td>' + esc(row.db_path || '') + '</td>';
    html += '<td>' + esc(keys.join(', ')) + '</td>';
    html += '<td><details><summary class="raw-row-summary">SQL</summary><pre class="json-raw" style="margin-top:6px;">' + esc((row.sql || '') + '\n\nparams=' + JSON.stringify(row.params || [], null, 2)) + '</pre></details></td>';
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  return html;
}

function renderBackendRetrievals(trace) {
  var rows = Array.isArray(trace && trace.retrievals) ? trace.retrievals : [];
  if (!rows.length) return '<div class="backend-trace-block"><h4>Retrieved Entries</h4><div class="backend-trace-empty">No retrieval rows captured.</div></div>';
  var html = '<div class="backend-trace-block"><h4>Retrieved Entries</h4><div class="backend-trace-list">';
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var entries = Array.isArray(row.entries) ? row.entries : [];
    html += '<div class="backend-trace-card">';
    html += '<div class="backend-trace-card-head"><div class="backend-trace-card-title">' + esc(row.normalized_key || '') + '</div><div class="backend-trace-card-meta">entries=' + esc(row.entry_count != null ? row.entry_count : entries.length) + ' | source=' + esc(row.source || row.scope || '') + '</div></div>';
    if (!entries.length) {
      html += '<div class="backend-trace-card-body">No entries retrieved.</div>';
    } else {
      html += '<div class="backend-trace-card-body">';
      for (var j = 0; j < entries.length; j++) {
        var ent = entries[j] || {};
        var forms = Array.isArray(ent.matched_forms) ? ent.matched_forms : [];
        html += '<div><strong>' + esc(ent.headword || '') + '</strong> | pos=' + esc(ent.pos_raw || '') + ' | source=' + esc(ent.source || '') + ' | match=' + esc(ent.match_kind || '') + (forms.length ? (' | forms=' + esc(forms.map(function(f) { return String((f || {}).form_text || ''); }).join(', '))) : '') + '</div>';
      }
      html += '</div>';
    }
    html += '</div>';
  }
  html += '</div></div>';
  return html;
}

function summarizeSegmenterEventForUi(ev) {
  var kind = String((ev && ev.kind) || '');
  if (kind === 'span_key_matrix') {
    return 'unique_keys=' + String(ev.unique_key_count || 0) + ' | spans=' + String((Array.isArray(ev.span_pairs) ? ev.span_pairs.length : 0));
  }
  if (kind === 'prefetch_candidate_keys') {
    return 'requested=' + String((Array.isArray(ev.requested_keys) ? ev.requested_keys.length : 0));
  }
  if (kind === 'prefetch_candidate_results') {
    return summarizePlainMeta(ev.result_counts || {}, 6);
  }
  if (kind === 'lookup_all_result' || kind === 'lookup_all_cache_hit' || kind === 'materialized_candidates') {
    return summarizePlainMeta(ev, 6);
  }
  return summarizePlainMeta(ev, 6);
}

function summarizeDecorationEventForUi(ev) {
  var kind = String((ev && ev.kind) || '');
  if (kind === 'segment_result') {
    return 'token=' + String(ev.token || '') + ' | upos=' + String(ev.upos || '') + ' | xpos=' + String(ev.xpos || '') + ' | mode=' + String(ev.fill_mode || '') + ' | entries=' + String(ev.entry_count || 0);
  }
  if (kind === 'fill_row') {
    return 'text=' + String(ev.text || ev.head || '') + ' | upos=' + String(ev.effective_upos || '') + ' | xpos=' + String(ev.effective_xpos || '') + ' | entries=' + String(ev.entry_count || 0);
  }
  return summarizePlainMeta(ev, 6);
}

function renderBackendEventCards(title, rows, summarizer) {
  if (!rows || !rows.length) return '<div class="backend-trace-block"><h4>' + esc(title) + '</h4><div class="backend-trace-empty">No events captured.</div></div>';
  var html = '<div class="backend-trace-block"><h4>' + esc(title) + '</h4><div class="backend-trace-list">';
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var rawDetails = '';
    try { rawDetails = JSON.stringify(row, null, 2); } catch (_err) { rawDetails = String(row); }
    html += '<div class="backend-trace-card">';
    html += '<div class="backend-trace-card-head"><div class="backend-trace-card-title">' + esc(row.kind || row.scope || ('event ' + (i + 1))) + '</div><div class="backend-trace-card-meta">' + esc(String(row.scope || '')) + '</div></div>';
    html += '<div class="backend-trace-card-body">' + esc(summarizer(row) || '') + '</div>';
    html += '<details style="margin-top:6px;"><summary class="raw-row-summary">details</summary><pre class="json-raw" style="margin-top:6px;">' + esc(rawDetails) + '</pre></details>';
    html += '</div>';
  }
  html += '</div></div>';
  return html;
}

function renderBackendTrace(trace) {
  if (!trace || typeof trace !== 'object') {
    return '<div class="backend-trace-empty">No backend trace captured yet. Turn on Debug capture and run a lookup.</div>';
  }
  var queryCount = Array.isArray(trace.sqlite_queries) ? trace.sqlite_queries.length : 0;
  var retrievalCount = Array.isArray(trace.retrievals) ? trace.retrievals.length : 0;
  var segmenterCount = Array.isArray(trace.segmenter_events) ? trace.segmenter_events.length : 0;
  var decorationCount = Array.isArray(trace.decoration_events) ? trace.decoration_events.length : 0;
  var totalQueryMs = 0;
  var queries = Array.isArray(trace.sqlite_queries) ? trace.sqlite_queries : [];
  for (var i = 0; i < queries.length; i++) totalQueryMs += Number((queries[i] || {}).duration_ms || 0);
  var html = '<div class="backend-trace-summary">';
  html += '<span class="backend-trace-chip">Capture: ' + esc(trace.debug_capture_id || 'none') + '</span>';
  html += '<span class="backend-trace-chip">Total: ' + esc(formatMsLabel(trace.total_ms)) + '</span>';
  html += '<span class="backend-trace-chip">SQLite: ' + esc(formatMsLabel(totalQueryMs)) + ' across ' + esc(queryCount) + ' queries</span>';
  html += '<span class="backend-trace-chip">Retrievals: ' + esc(retrievalCount) + '</span>';
  html += '<span class="backend-trace-chip">Segmenter events: ' + esc(segmenterCount) + '</span>';
  html += '<span class="backend-trace-chip">Decoration events: ' + esc(decorationCount) + '</span>';
  html += '</div>';
  html += renderBackendTimingTree(trace);
  html += renderBackendNormalizations(trace);
  html += renderBackendSqliteQueries(trace);
  html += renderBackendRetrievals(trace);
  html += renderBackendEventCards('Segmentation Process', Array.isArray(trace.segmenter_events) ? trace.segmenter_events : [], summarizeSegmenterEventForUi);
  html += renderBackendEventCards('Decoration Process', Array.isArray(trace.decoration_events) ? trace.decoration_events : [], summarizeDecorationEventForUi);
  return html;
}

function render(data) {
  var lang = data.language || '?';
  var ts = data._timestamp ? new Date(data._timestamp * 1000).toLocaleTimeString() : '?';
  document.getElementById('metaInfo').textContent = 'Lang: ' + lang + '  |  ' + ts;
  if (lang && lang !== '?') {
    currentProbeLang = String(lang).toLowerCase();
    var langInput = document.getElementById('greedyLangInput');
    if (langInput) langInput.value = currentProbeLang;
  }

  var html = '';

  // --- Section 1: Original + Normalized Text ---
  html += '<div class="section">';
  html += '<div class="section-head" onclick="toggleSection(this)">';
  html += '<span><span class="tag tag-input">INPUT</span> Original + Normalized Text</span>';
  html += '<span>â–¾</span></div>';
  html += '<div class="section-body">';
  html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px;">';
  html += '<div>';
  html += '<div style="margin-bottom:8px;font-size:11px;color:#6c7086;">Raw input text:</div>';
  html += '<div class="text-block original">' + esc(data.original_text || '') + '</div>';
  html += '</div>';
  html += '<div>';
  html += '<div style="margin-bottom:8px;font-size:11px;color:#6c7086;">Normalized text (' + esc(data.preprocess_normalization_form || '') + '):</div>';
  html += '<div class="text-block" style="color:#94e2d5;">' + esc(data.normalized_text || data.original_text || '') + '</div>';
  html += '</div>';
  if ((data.filtered_text || '') && (data.filtered_text !== data.normalized_text)) {
    html += '<div>';
    html += '<div style="margin-bottom:8px;font-size:11px;color:#6c7086;">Model text after filtering:</div>';
    html += '<div class="text-block" style="color:#f9e2af;">' + esc(data.filtered_text || '') + '</div>';
    html += '</div>';
  }
  html += '</div>';
  html += '</div></div>';

  // --- Section 2: Normalization Changes ---
  html += '<div class="section">';
  html += '<div class="section-head" onclick="toggleSection(this)">';
  html += '<span><span class="tag tag-norm">NORM</span> Segments Removed/Changed By Normalization</span>';
  html += '<span>â–¾</span></div>';
  html += '<div class="section-body">';
  html += renderNormalizationChanges(data.normalization_change_rows || []);
  html += '</div></div>';

  // --- Section 3: Raw Trankit Output ---
  html += '<div class="section">';
  html += '<div class="section-head" onclick="toggleSection(this)">';
  html += '<span><span class="tag tag-trankit">TRANKIT</span> Raw Transformer Output</span>';
  html += '<span>â–¾</span></div>';
  html += '<div class="section-body">';
  var trankitDoc = data.pipeline_trankit_doc || data.trankit_doc || data.raw_trankit_doc;
  html += renderTrankitDoc(trankitDoc, data.mwt_meta || null);
  html += '</div></div>';

  // --- Raw Trankit Tokens (pre-MWT-collapse) ---
  var rawTrankitTokens = Array.isArray(data.raw_trankit_tokens) ? data.raw_trankit_tokens : [];
  if (rawTrankitTokens.length) {
    html += '<div class="section">';
    html += '<div class="section-head" onclick="toggleSection(this)">';
    html += '<span><span class="tag tag-trankit">TRANKIT</span> Raw Tokens (pre-MWT collapse)</span>';
    html += '<span>▾</span></div>';
    html += '<div class="section-body">';
    html += '<table><thead><tr><th>sent</th><th>id</th><th>type</th><th>text</th><th>upos</th><th>deprel</th><th>head</th><th>lemma</th><th>span</th><th>dspan</th></tr></thead><tbody>';
    var fmtSpan = function(s) {
      if (s == null) return '';
      if (Array.isArray(s) || (typeof s === 'object' && s.length != null)) {
        return '[' + (s[0] != null ? s[0] : '') + ',' + (s[1] != null ? s[1] : '') + ']';
      }
      return String(s);
    };
    for (var rti = 0; rti < rawTrankitTokens.length; rti++) {
      var rt = rawTrankitTokens[rti];
      var rowClass = rt.type === 'MWT_PARENT' ? ' style="background:#fff3cd;"' : (rt.type === 'MWT_WORD' ? ' style="background:#d1ecf1;"' : '');
      html += '<tr' + rowClass + '>';
      html += '<td>' + esc(String(rt.sentence_index != null ? rt.sentence_index : '')) + '</td>';
      html += '<td>' + esc(String(rt.id != null ? rt.id : '')) + '</td>';
      html += '<td>' + esc(String(rt.type || '')) + '</td>';
      html += '<td>' + esc(String(rt.text || '')) + '</td>';
      html += '<td>' + esc(String(rt.upos || '')) + '</td>';
      html += '<td>' + esc(String(rt.deprel || '')) + '</td>';
      html += '<td>' + esc(String(rt.head != null ? rt.head : '')) + '</td>';
      html += '<td>' + esc(String(rt.lemma || '')) + '</td>';
      html += '<td>' + esc(fmtSpan(rt.span)) + '</td>';
      html += '<td>' + esc(fmtSpan(rt.dspan)) + '</td>';
      html += '</tr>';
    }
    html += '</tbody></table>';
    html += '</div></div>';
  }

  // --- Section 4: Token â†’ Dictionary Mapping ---
  var dictResultsBySeg = Array.isArray(data.results_by_seg) ? data.results_by_seg : [];

  html += '<div class="section">';
  html += '<div class="section-head" onclick="toggleSection(this)">';
  html += '<span><span class="tag tag-dict">DICT</span> Token â†’ Dictionary Mapping</span>';
  html += '<span>â–¾</span></div>';
  html += '<div class="section-body">';
  html += renderDictMapping(data.segments, dictResultsBySeg);
  html += '</div></div>';

  if (data.debug_ui_lookup_timing && typeof data.debug_ui_lookup_timing === 'object') {
    html += '<div class="section">';
    html += '<div class="section-head" onclick="toggleSection(this)">';
    html += '<span><span class="tag tag-dict">TIME</span> End-To-End Lookup Timing</span>';
    html += '<span>&#9662;</span></div>';
    html += '<div class="section-body">';
    html += renderLookupTimingTrace(data.debug_ui_lookup_timing);
    html += '</div></div>';
  }

  if (data.sqlite_debug_trace && typeof data.sqlite_debug_trace === 'object') {
    html += '<div class="section">';
    html += '<div class="section-head" onclick="toggleSection(this)">';
    html += '<span><span class="tag tag-dict">PY</span> Python Backend Trace</span>';
    html += '<span>&#9662;</span></div>';
    html += '<div class="section-body">';
    html += renderBackendTrace(data.sqlite_debug_trace);
    html += '</div></div>';
  }

  var traceRows = getDictionaryTraceRows(data);
  if (traceRows.length > 0) {
    var traceLabel = dictionaryTraceLabel(lang);
    html += '<div class="section">';
    html += '<div class="section-head" onclick="toggleSection(this)">';
    html += '<span><span class="tag tag-ja">' + esc((lang || 'trace').toUpperCase()) + '</span> ' + esc(traceLabel) + ' Dictionary Decision Trace</span>';
    html += '<span>â–¾</span></div>';
    html += '<div class="section-body">';
    html += renderDictionaryDecisionTrace(traceRows, traceLabel);
    html += '</div></div>';
  }

  // --- Section 5: Normalization Remap (model -> original) ---
  html += '<div class="section">';
  html += '<div class="section-head" onclick="toggleSection(this)">';
  html += '<span><span class="tag tag-remap">REMAP</span> Normalized Segment Remap</span>';
  html += '<span>â–¾</span></div>';
  html += '<div class="section-body">';
  html += renderNormalizedRemaps(data.normalized_segment_remaps || []);
  html += '</div></div>';

  // --- Section 6: Returned Segments vs Original Text ---
  var retDisc = data.segment_original_discrepancies || [];
  html += '<div class="section">';
  html += '<div class="section-head" onclick="toggleSection(this)">';
  html += '<span><span class="tag tag-diff">DIFF</span> Returned Segments vs Original Text';
  if (!retDisc.length) {
    html += ' <span style="font-size:11px;font-weight:normal;color:var(--green);margin-left:8px;">â€” no discrepancies â€”</span>';
  } else {
    html += ' <span style="font-size:11px;font-weight:normal;color:var(--red);margin-left:8px;">â€” ' + retDisc.length + ' discrepanc' + (retDisc.length === 1 ? 'y' : 'ies') + ' â€”</span>';
  }
  html += '</span><span>â–¾</span></div>';
  html += '<div class="section-body">';
  html += renderSegmentOriginalDiscrepancies(retDisc);
  html += '</div></div>';

  document.getElementById('content').innerHTML = html;
}

function renderNormalizationChanges(rows) {
  if (!rows || !rows.length) {
    return '<div style="text-align:center;padding:20px;color:var(--green);">No characters were removed/changed by normalization.</div>';
  }
  var html = '<table><thead><tr>';
  html += '<th>#</th><th>Operation</th><th>Original Offset</th><th>Original Text</th><th>Normalized Offset</th><th>Normalized Text</th>';
  html += '</tr></thead><tbody>';
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i] || {};
    html += '<tr>';
    html += '<td style="color:#6c7086;">' + i + '</td>';
    html += '<td style="color:#89dceb;">' + esc(r.op || '') + '</td>';
    html += '<td style="color:#a6adc8;">' + esc(formatOffsetSpan(r.original_offset)) + '</td>';
    html += '<td class="tok-text">' + esc(r.original_text || '') + '</td>';
    html += '<td style="color:#a6adc8;">' + esc(formatOffsetSpan(r.normalized_offset)) + '</td>';
    html += '<td class="tok-text" style="color:#94e2d5;">' + esc(r.normalized_text || '') + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

function renderTrankitDoc(doc, mwtMeta) {
  if (!doc || !doc.sentences) return '<div class="empty">No Trankit data</div>';
  var html = '<table><thead><tr>';
  html += '<th>#</th><th>Text</th><th>Lemma</th><th>UPOS</th><th>XPOS</th><th>Dep</th><th>Head</th><th>NER</th><th>Span</th><th>MWT Expanded</th>';
  html += '</tr></thead><tbody>';
  var globalIdx = 0;
  for (var si = 0; si < doc.sentences.length; si++) {
    var sent = doc.sentences[si];
    var tokens = sent.tokens || [];
    html += '<tr class="sent-divider"><td colspan="10"><span class="sent-label">Sentence ' + (si + 1) + '</span></td></tr>';
    for (var ti = 0; ti < tokens.length; ti++) {
      var tok = tokens[ti];
      var upos = tok.upos || '';
      var uposColor = getUposColor(upos);
      html += '<tr>';
      html += '<td style="color:#6c7086;">' + globalIdx + '</td>';
      html += '<td class="tok-text">' + esc(tok.text || '') + '</td>';
      html += '<td style="color:#a6adc8;">' + esc(tok.lemma || '') + '</td>';
      html += '<td><span class="pos-badge" style="background:' + uposColor + '33;color:' + uposColor + ';">' + esc(upos) + '</span></td>';
      html += '<td style="color:#a6adc8;">' + esc(tok.xpos || '') + '</td>';
      html += '<td><span class="dep-badge">' + esc(tok.deprel || '') + '</span></td>';
      html += '<td style="color:#a6adc8;">' + (tok.head != null ? tok.head : '') + '</td>';
      var ner = tok.ner || '';
      if (ner && ner !== 'O') {
        html += '<td><span class="ner-badge">' + esc(ner) + '</span></td>';
      } else {
        html += '<td style="color:#45475a;">O</td>';
      }
      var span = tok.dspan || tok.span || [];
      html += '<td style="color:#6c7086;font-size:11px;">' + (span.length >= 2 ? span[0] + ':' + span[1] : '') + '</td>';
      var expandedRows = [];
      if (Array.isArray(tok.mwt_expanded_words) && tok.mwt_expanded_words.length) {
        expandedRows = tok.mwt_expanded_words;
      } else if (Array.isArray(tok.expanded) && tok.expanded.length) {
        expandedRows = tok.expanded;
      }
      if (expandedRows.length) {
        html += '<td>';
        for (var ei = 0; ei < expandedRows.length; ei++) {
          var ex = expandedRows[ei] || {};
          html += '<div style="font-size:11px;color:#f9e2af;">' + esc(ex.text || '') + '</div>';
          html += '<div style="font-size:10px;color:#a6adc8;">lemma=' + esc(ex.lemma || '') + '</div>';
          var exSlice = ex.surface_slice;
          var exSliceText = ex.surface_slice_text || '';
          var exPass = ex._realign_pass || '';
          if (exSlice && exSlice.length >= 2) {
            html += '<div style="font-size:10px;color:#94e2d5;">slice=[' + esc(String(exSlice[0])) + ',' + esc(String(exSlice[1])) + ']';
            if (exSliceText) html += ' \u201c' + esc(exSliceText) + '\u201d';
            html += '</div>';
          }
          if (exPass) {
            html += '<div style="font-size:10px;color:#89b4fa;">pass=' + esc(exPass) + '</div>';
          }
        }
        html += '</td>';
      } else {
        html += '<td style="color:#45475a;">-</td>';
      }
      html += '</tr>';
      globalIdx++;
    }
  }
  html += '</tbody></table>';
  html += '<div style="margin-top:8px;font-size:11px;color:#6c7086;">';
  html += doc.sentences.length + ' sentence(s), ' + globalIdx + ' token(s)';
  if (mwtMeta) {
    html += ', mwt_applied=' + esc(mwtMeta.applied ? 'yes' : 'no');
    html += ', mwt_expanded_words=' + esc(mwtMeta.expanded_token_count != null ? mwtMeta.expanded_token_count : 0);
  }
  html += '</div>';
  return html;
}

function renderDictMapping(segments, resultsBySeg) {
  if (!segments || !segments.length) return '<div class="empty">No segments</div>';
  if (!resultsBySeg) resultsBySeg = [];
  var html = '<table><thead><tr>';
  html += '<th>#</th><th>Token</th><th>Lemma</th><th>Source</th><th>POS</th><th>Dep</th><th>Dictionary Entries</th>';
  html += '</tr></thead><tbody>';
  for (var i = 0; i < segments.length; i++) {
    var seg = segments[i];
    var res = resultsBySeg[i] || null;
    html += '<tr>';
    html += '<td style="color:#6c7086;">' + i + '</td>';
    html += '<td class="tok-text">' + esc(seg) + '</td>';
    if (!res) {
      html += '<td style="color:#45475a;">â€”</td>';
      html += '<td colspan="4" style="color:#45475a;">â€” no data â€”</td>';
      html += '</tr>';
      continue;
    }
    html += '<td style="color:#a6adc8;">' + esc(res.lemma || res.lemma_form || '') + '</td>';
    var src = res.source || '';
    var srcColor = src === 'CEDICT' ? 'var(--green)' : src === 'UNKNOWN' ? 'var(--red)' : 'var(--yellow)';
    html += '<td style="color:' + srcColor + ';">' + esc(src) + '</td>';
    var upos = res.upos || res.pos || '';
    var uposColor = getUposColor(upos);
    html += '<td><span class="pos-badge" style="background:' + uposColor + '33;color:' + uposColor + ';">' + esc(upos) + '</span></td>';
    html += '<td><span class="dep-badge">' + esc(res.dep || '') + '</span></td>';
    // Dictionary entries
    html += '<td>';
    var fill = res.dict_fill || [];
    if (fill.length) {
      for (var fi = 0; fi < fill.length; fi++) {
        var entry = fill[fi];
        if (!entry) continue;
        html += '<div class="dict-entry">';
        html += '<span class="head">' + esc(entry.head || '') + '</span>';
        if (entry.roman) html += '<span class="roman">' + esc(entry.roman) + '</span>';
        var senses = entry.senses || [];
        if (senses.length) {
          for (var si2 = 0; si2 < senses.length; si2++) {
            var raw = senses[si2] || '';
            // Parse tab-delimited sense format
            var cleaned = raw.replace(/\t/g, '  ');
            html += '<div class="sense">' + esc(cleaned) + '</div>';
          }
        } else if (entry.source === 'UNKNOWN') {
          html += '<span class="dict-unknown"> [unknown]</span>';
        }
        html += '</div>';
      }
    } else if (res.senses && res.senses.length) {
      html += '<div class="dict-entry">';
      for (var si3 = 0; si3 < res.senses.length; si3++) {
        var cleaned2 = (res.senses[si3] || '').replace(/\t/g, '  ');
        html += '<div class="sense">' + esc(cleaned2) + '</div>';
      }
      html += '</div>';
    } else {
      html += '<span class="dict-unknown">[no entries]</span>';
    }
    html += '</td></tr>';
  }
  html += '</tbody></table>';
  return html;
}

function buildRawTsvLine(row, headers) {
  var cols = Array.isArray(headers) ? headers : [];
  if (!cols.length || !row || typeof row !== 'object') return '';
  var values = [];
  for (var i = 0; i < cols.length; i++) {
    var key = String(cols[i] || '');
    values.push(String(row[key] == null ? '' : row[key]));
  }
  return values.join('\t');
}

function renderUiFillPieceForCompare(piece, idx) {
  var fill = (piece && typeof piece === 'object') ? piece : {};
  var text = String(fill.text || '').trim();
  var head = String(fill.head || '').trim();
  var roman = String(fill.roman || '').trim();
  var source = String(fill.source || '').trim();
  var pos = String(fill.pos || '').trim();
  var senses = Array.isArray(fill.senses) ? fill.senses : [];

  var html = '<details class="dict-entry">';
  html += '<summary class="raw-row-summary">';
  html += '<span class="head">fill ' + esc(idx) + ': ' + esc(text || head || '') + '</span>';
  if (head && head !== text) html += '<span class="roman">-> ' + esc(head) + '</span>';
  if (roman) html += '<span class="roman">' + esc(roman) + '</span>';
  html += '</summary>';
  html += '<div class="sense">source=' + esc(source || '?') + ', pos=' + esc(pos || '?') + ', senses=' + esc(senses.length) + '</div>';
  if (senses.length) {
    for (var i = 0; i < senses.length; i++) {
      var parsed = parseDebugSenseLine(senses[i]);
      html += '<div class="sense">' + esc(parsed.gloss || parsed.raw || '') + '</div>';
    }
  } else {
    html += '<div class="sense dict-unknown">[no senses on this fill piece]</div>';
  }
  html += '<details style="margin-top:4px;">';
  html += '<summary style="cursor:pointer;color:#a6adc8;">fill JSON</summary>';
  html += '<pre class="json-raw" style="margin-top:6px;">' + esc(JSON.stringify(fill, null, 2)) + '</pre>';
  html += '</details>';
  html += '</details>';
  return html;
}

function renderUiEntryForCompare(entry, fillRows) {
  if (!entry) return '<span class="dict-unknown">[no UI entry]</span>';
  var html = '<div class="dict-entry">';

  var blocks = Array.isArray(fillRows) ? fillRows : [];
  if (!blocks.length && Array.isArray(entry.dict_fill)) {
    for (var di = 0; di < entry.dict_fill.length; di++) {
      blocks.push({ fill_i: di, fill_piece: entry.dict_fill[di] || {} });
    }
  }
  if (blocks.length) {
    for (var bi = 0; bi < blocks.length; bi++) {
      var block = blocks[bi] || {};
      var piece = block.fill_piece || {};
      var idx = (block.fill_i != null) ? block.fill_i : bi;
      html += renderUiFillPieceForCompare(piece, idx);
    }
  } else {
    html += '<div class="sense dict-unknown">[no dict_fill pieces]</div>';
  }

  var mergedSenses = Array.isArray(entry.senses) ? entry.senses : [];
  html += '<details style="margin-top:4px;">';
  html += '<summary style="cursor:pointer;color:#a6adc8;">token UI metadata</summary>';
  html += '<div class="sense">head=' + esc(entry.head || '') + (entry.roman ? (' [' + esc(entry.roman) + ']') : '') + '</div>';
  html += '<div class="sense">source=' + esc(entry.source || '') + ', pos=' + esc(entry.pos || entry.upos || '') + '</div>';
  if (entry.lemma || entry.lemma_form) {
    html += '<div class="sense">lemma=' + esc(entry.lemma_form || entry.lemma || '') + '</div>';
  }
  html += '</details>';

  html += '<details style="margin-top:4px;">';
  html += '<summary style="cursor:pointer;color:#a6adc8;">token-level merged senses (' + esc(mergedSenses.length) + ')</summary>';
  if (mergedSenses.length) {
    html += '<div class="tsv-row-line" style="margin-top:6px;">' + esc(mergedSenses.join('\n')) + '</div>';
  } else {
    html += '<div class="sense dict-unknown">[no merged senses]</div>';
  }
  html += '</details>';

  html += '<details style="margin-top:4px;">';
  html += '<summary style="cursor:pointer;color:#a6adc8;">full UI entry JSON</summary>';
  html += '<pre class="json-raw" style="margin-top:6px;">' + esc(JSON.stringify(entry, null, 2)) + '</pre>';
  html += '</details>';
  html += '</div>';
  return html;
}

function renderTokenInfoForCompare(row, fillRows, rawRows, variantUsed, variantFiltered, variantOther) {
  var token = String((row && row.token) || '');
  var seg = (row && row.seg_i != null) ? row.seg_i : '';
  var entry = (row && row.ui_entry && typeof row.ui_entry === 'object') ? row.ui_entry : null;
  var fillsCount = Number((row && row.fill_row_count) || (Array.isArray(fillRows) ? fillRows.length : 0) || 0);
  var entriesCount = Number((row && row.candidate_entry_count) || 0);
  var tsvCount = Array.isArray(rawRows) ? rawRows.length : 0;

  var html = '<div class="dict-entry">';
  html += '<div><span class="head">' + esc(token) + '</span>';
  html += '<span class="roman">seg=' + esc(seg) + '</span></div>';
  if (entry) {
    html += '<div class="sense">upos=' + esc(entry.upos || entry.pos || '') + ', source=' + esc(entry.source || '') + '</div>';
    if (entry.lemma || entry.lemma_form) {
      html += '<div class="sense">lemma=' + esc(entry.lemma_form || entry.lemma || '') + '</div>';
    }
  }
  html += '<div class="sense">fills=' + esc(fillsCount) + ', entries=' + esc(entriesCount) + ', tsv=' + esc(tsvCount) + '</div>';
  if ((variantUsed + variantFiltered + variantOther) > 0) {
    html += '<div class="sense">variant hits: used=' + esc(variantUsed) + ', filtered=' + esc(variantFiltered) + ', other=' + esc(variantOther) + '</div>';
  }
  html += '</div>';
  return html;
}

function statusLabelForRow(status) {
  if (status === 'primary') return 'selected';
  if (status === 'shown') return 'selected';
  if (status === 'filtered_out') return 'filtered out';
  return 'unmatched';
}

function statusBadgeClassForRow(status) {
  if (status === 'primary') return 'badge-shown';
  if (status === 'shown') return 'badge-shown';
  if (status === 'filtered_out') return 'badge-filtered';
  return 'badge-unmatched';
}

function statusCardClassForRow(status) {
  if (status === 'primary') return 'shown';
  if (status === 'shown') return 'shown';
  if (status === 'filtered_out') return 'filtered';
  return 'unmatched';
}

function renderRawRowsForCompare(rows, headers, variantHits, rowStatusMap, token) {
  var list = Array.isArray(rows) ? rows : [];
  if (!list.length) return '<span class="dict-unknown">[no matched TSV rows]</span>';
  var html = '';
  var hitMap = (variantHits && typeof variantHits === 'object') ? variantHits : {};
  var statusMap = (rowStatusMap && typeof rowStatusMap === 'object') ? rowStatusMap : {};
  var tokenText = String(token || '').trim();
  var tokenKey = lookupKeyForDebug(tokenText);
  for (var i = 0; i < list.length; i++) {
    var row = list[i] || {};
    var lineNo = row.__line_no != null ? ('line ' + String(row.__line_no)) : '';
    var rawLine = buildRawTsvLine(row, headers);
    var head = String(row.headword || '');
    var pos = String(row.pos || row.pos_raw || '');
    var roman = String(row.romanization || row.reading || '');
    var rowKey = rowKeyForCompare(row);
    var rowStatus = String(statusMap[rowKey] || 'unmatched');
    var rowHits = Array.isArray(hitMap[rowKey]) ? hitMap[rowKey] : [];
    var gloss = String(row.glosses || '');
    var statusLabel = statusLabelForRow(rowStatus);
    var badgeClass = statusBadgeClassForRow(rowStatus);
    var cardClass = statusCardClassForRow(rowStatus);
    html += '<details class="dict-entry ' + cardClass + '">';
    html += '<summary class="raw-row-summary">';
    html += '<span class="head">' + esc(head) + '</span>';
    if (roman) html += '<span class="roman">' + esc(roman) + '</span>';
    if (lineNo) html += '<span class="roman">' + esc(lineNo) + '</span>';
    html += '<span class="roman">' + esc(statusLabel) + '</span>';
    if (rowHits.length) html += '<span class="roman" style="color:#89dceb;">variant hits=' + esc(rowHits.length) + '</span>';
    html += '</summary>';
    html += '<div class="sense">pos=' + esc(pos) + '</div>';
    html += '<div class="match-badges"><span class="match-badge ' + badgeClass + '">' + esc(statusLabel) + '</span></div>';
    if (rowHits.length) {
      for (var hi = 0; hi < rowHits.length; hi++) {
        var hit = rowHits[hi] || {};
        var frm = String(hit.form_text || hit.source_surface || '').trim();
        if (!frm) continue;
        var sourceSurface = String(hit.source_surface || '').trim();
        var tags = Array.isArray(hit.tags) && hit.tags.length ? (' [' + hit.tags.join(', ') + ']') : '';
        var sourceKey = lookupKeyForDebug(sourceSurface);
        var directMatch = !!(tokenKey && sourceKey && tokenKey === sourceKey);
        var hitKind = 'unused';
        var hitLabel = 'variant form candidate';
        if (rowStatus === 'filtered_out') {
          hitKind = 'filtered';
          hitLabel = 'variant form filtered';
        } else if (directMatch) {
          hitKind = 'used';
          hitLabel = 'variant form used';
        }
        var hitClass = (hitKind === 'used') ? 'variant-hit-used' : (hitKind === 'filtered') ? 'variant-hit-filtered' : 'variant-hit-unused';
        var src = sourceSurface && sourceSurface !== frm ? (' <- ' + sourceSurface) : '';
        html += '<div class="sense ' + hitClass + '">' + esc(hitLabel + ': ' + frm + tags + src) + '</div>';
      }
      if (rowStatus === 'filtered_out') {
        html += '<div class="sense variant-hit-filtered">excluded by entry filtering (POS/classifier/etc)</div>';
      }
    }
    if (gloss) html += '<div class="sense">' + esc(gloss) + '</div>';
    var formsRaw = String(row.forms || '').trim();
    if (formsRaw) {
      html += '<details style="margin-top:4px;">';
      html += '<summary style="cursor:pointer;color:#a6adc8;">forms list (JSON)</summary>';
      html += '<div class="tsv-row-line" style="margin-top:6px;">' + esc(formsRaw) + '</div>';
      html += '</details>';
    }
    if (rawLine) {
      html += '<details style="margin-top:4px;">';
      html += '<summary style="cursor:pointer;color:#a6adc8;">raw TSV row</summary>';
      html += '<div class="tsv-row-line" style="margin-top:6px;">' + esc(rawLine.replace(/\t/g, ' [TAB] ')) + '</div>';
      html += '</details>';
    }
    html += '<details style="margin-top:4px;">';
    html += '<summary style="cursor:pointer;color:#a6adc8;">row JSON</summary>';
    html += '<pre class="json-raw" style="margin-top:6px;">' + esc(JSON.stringify(row, null, 2)) + '</pre>';
    html += '</details>';
    html += '</details>';
  }
  return html;
}

function renderFillRowsForCompare(fillRows, headers, tokenFallback) {
  var list = Array.isArray(fillRows) ? fillRows : [];
  if (!list.length) return '<span class="dict-unknown">[no dict_fill rows]</span>';
  var html = '';
  for (var i = 0; i < list.length; i++) {
    var fr = list[i] || {};
    var piece = fr.fill_piece || {};
    var fillText = String(piece.text || fr.fill_surface || tokenFallback || '').trim();
    var fillHead = String(piece.head || '').trim();
    var fillRoman = String(piece.roman || '').trim();
    var fillSource = String(piece.source || '').trim();
    var fillPos = String(piece.pos || '').trim();
    var rawRows = Array.isArray(fr.raw_rows) ? fr.raw_rows : [];
    var rowStatusMap = (fr.row_status_map && typeof fr.row_status_map === 'object') ? fr.row_status_map : {};
    var variantHits = (fr.variant_form_hits && typeof fr.variant_form_hits === 'object') ? fr.variant_form_hits : {};
    var surfaceForMatch = String(fr.fill_surface || fillText || tokenFallback || '');
    var summary = fillText || fillHead || ('fill ' + String(i));

    html += '<details class="dict-entry">';
    html += '<summary class="raw-row-summary">';
    html += '<span class="head">fill ' + esc(i) + ': ' + esc(summary) + '</span>';
    if (fillHead && fillHead !== fillText) html += '<span class="roman">-> ' + esc(fillHead) + '</span>';
    if (fillRoman) html += '<span class="roman">' + esc(fillRoman) + '</span>';
    html += '</summary>';
    html += '<div class="sense">source=' + esc(fillSource || '?') + ', pos=' + esc(fillPos || '?') + ', entries=' + esc(fr.candidate_entry_count || 0) + ', tsv=' + esc(rawRows.length) + '</div>';
    html += renderRawRowsForCompare(rawRows, headers, variantHits, rowStatusMap, surfaceForMatch);
    html += '</details>';
  }
  return html;
}

function renderUiVsRawTsvRows(data) {
  void data;
  return '';
}

function renderDictionaryDecisionTrace(rows, label) {
  if (!rows || !rows.length) {
    var lbl = label || 'Dictionary';
    return '<div class="empty">No ' + esc(lbl) + ' dictionary decisions recorded for this lookup.</div>';
  }
  var html = '<table><thead><tr>';
  html += '<th>#</th><th>Segment</th><th>Tags</th><th>Match Path</th><th>Operations</th><th>Segment → Entry Mapping</th><th>Entry Filtering</th><th>Sense-row Filtering</th>';
  html += '</tr></thead><tbody>';

  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {};
    var segOffset = formatOffsetSpan(row.segment_offset || []);
    html += '<tr>';
    html += '<td style="color:#6c7086;">' + esc(row.seg_i != null ? row.seg_i : i) + '</td>';
    html += '<td class="tok-text">' + esc(row.token || '') + '<div style="font-size:10px;color:#a6adc8;">lemma=' + esc(row.lemma || '') + '</div>';
    html += '<div style="font-size:10px;color:#6c7086;">sent=' + esc(row.sentence_index) + ', tok=' + esc(row.token_index) + (segOffset ? ', span=' + esc(segOffset) : '') + '</div></td>';
    html += '<td>';
    html += '<div><span class="pos-badge" style="background:' + getUposColor(row.upos || '') + '33;color:' + getUposColor(row.upos || '') + ';">' + esc(row.upos || '') + '</span></div>';
    html += '<div style="font-size:10px;color:#a6adc8;margin-top:2px;">xpos=' + esc(row.xpos || '') + '</div>';
    html += '</td>';
    html += '<td>';
    html += '<div style="font-weight:600;color:#f9e2af;">' + esc(row.match_path || '') + '</div>';
    html += '<div style="font-size:10px;color:#a6adc8;">';
    html += 'exact=' + esc(row.used_exact_match ? 'yes' : 'no');
    html += ' | lemma_greedy=' + esc(row.used_lemma_greedy_longest ? 'yes' : 'no');
    html += ' | surface_greedy=' + esc(row.used_surface_greedy_longest ? 'yes' : 'no');
    html += '</div>';
    html += '</td>';
    html += '<td>' + renderDictionaryTraceOps(row.operations || []) + '</td>';
    html += '<td>' + renderDictionaryTraceSegmentMapping(row) + '</td>';
    html += '<td>' + renderDictionaryTraceCandidateEntries(row.candidate_entries || [], row.entry_filter_breakdown || null) + '</td>';
    html += '<td>' + renderDictionaryTraceAppendedEntries(row.appended_dict_fill_entries || []) + '</td>';
    html += '</tr>';
  }

  html += '</tbody></table>';
  return html;
}

function renderDictionaryTraceSegmentMapping(row) {
  var mapping = row && row.segment_mapping ? row.segment_mapping : null;
  if (!mapping) return '<span class="dict-unknown">[no mapped entry]</span>';
  var html = '<div class="dict-entry">';
  html += '<div><span class="head">' + esc(mapping.resolved_head || '') + '</span>';
  html += '<span class="roman">' + esc(mapping.resolved_source || '') + '</span></div>';
  if (mapping.resolved_via) {
    html += '<div class="sense">resolved via: ' + esc(mapping.resolved_via) + '</div>';
  }
  html += '<div class="sense">dict_fill rows: ' + esc(mapping.dict_fill_count != null ? mapping.dict_fill_count : 0) + '</div>';
  html += '<div class="sense">upos=' + esc(mapping.upos || '') + ', xpos=' + esc(mapping.xpos || '') + '</div>';
  html += '</div>';
  return html;
}

function renderDictionaryTraceOps(ops) {
  if (!ops || !ops.length) return '<span class="dict-unknown">[no operations]</span>';
  var html = '';
  for (var i = 0; i < ops.length; i++) {
    var op = ops[i] || {};
    var modeText = op.mode || op.fill_mode || '';
    html += '<div class="dict-entry">';
    html += '<div><span class="head">' + esc(op.step || '') + '</span>';
    if (modeText) html += '<span class="roman">mode=' + esc(modeText) + '</span>';
    html += '</div>';
    if (op.head) html += '<div class="sense">head: ' + esc(op.head) + '</div>';
    if (op.lemma) html += '<div class="sense">lemma: ' + esc(op.lemma) + '</div>';
    if (op.entry_count != null) html += '<div class="sense">entries: ' + esc(op.entry_count) + '</div>';
    if (op.entries_found != null) html += '<div class="sense">lemma entries: ' + esc(op.entries_found) + '</div>';
    if (op.used_for_resolution != null) {
      html += '<div class="sense">used: ' + esc(op.used_for_resolution ? 'yes' : 'no') + '</div>';
    }
    if (op.has_known != null || op.has_unknown != null) {
      html += '<div class="sense">known=' + esc(op.has_known ? 'yes' : 'no') + ', unknown=' + esc(op.has_unknown ? 'yes' : 'no') + '</div>';
    }
    var pieces = op.pieces || [];
    if (pieces.length) {
      for (var pi = 0; pi < pieces.length; pi++) {
        var p = pieces[pi] || {};
        html += '<div class="sense">piece: ' + esc(p.text || '') + ' -> ' + esc(p.head || '') + ' (' + esc(p.source || '') + ')</div>';
      }
    }
    html += '</div>';
  }
  return html;
}

function renderDictionaryTraceCandidateEntries(entries, breakdown) {
  var rows = entries || [];
  if ((!rows || !rows.length) && breakdown && Array.isArray(breakdown.entries)) {
    rows = breakdown.entries;
  }
  if (!rows || !rows.length) return '<span class="dict-unknown">[no candidate entries]</span>';
  var html = '';
  if (breakdown) {
    html += '<div class="dict-entry">';
    html += '<div class="sense">mode=' + esc(breakdown.mode || '') + ', xpos=' + esc(breakdown.xpos || '') + ', upos=' + esc(breakdown.upos || '') + '</div>';
    if (breakdown.effective_upos || breakdown.effective_xpos) {
      html += '<div class="sense">effective filter: upos=' + esc(breakdown.effective_upos || '') + ', xpos=' + esc(breakdown.effective_xpos || '') + '</div>';
    }
    if (breakdown.lemma_upos_hint || breakdown.lemma_xpos_hint) {
      html += '<div class="sense">lemma hints: upos=' + esc(breakdown.lemma_upos_hint || '') + ', xpos=' + esc(breakdown.lemma_xpos_hint || '') + '</div>';
    }
    if (Array.isArray(breakdown.xpos_tags) && breakdown.xpos_tags.length) {
      html += '<div class="sense">xpos tags: ' + esc(breakdown.xpos_tags.join(', ')) + '</div>';
    }
    if (Array.isArray(breakdown.allowed_pos_raw) && breakdown.allowed_pos_raw.length) {
      html += '<div class="sense">allowed dict POS: ' + esc(breakdown.allowed_pos_raw.join(', ')) + '</div>';
    }
    html += '<div class="sense">shown=' + esc(breakdown.shown_count != null ? breakdown.shown_count : 0) + ', filtered=' + esc(breakdown.filtered_count != null ? breakdown.filtered_count : 0) + '</div>';
    html += '</div>';
  }
  for (var i = 0; i < rows.length; i++) {
    var e = rows[i] || {};
    var status = e.filter_status || '';
    var color = status === 'filtered_out' ? 'var(--red)' : 'var(--green)';
    html += '<div class="dict-entry">';
    html += '<div><span class="head">' + esc(e.label || '') + '</span>';
    html += '<span class="roman" style="color:' + color + ';">' + esc(status) + '</span></div>';
    var posRaw = e.pos_raw || '';
    var posDisp = e.pos || '';
    if (posRaw || posDisp) {
      html += '<div class="sense">pos=' + esc(posDisp || posRaw) + (posRaw && posDisp && posRaw !== posDisp ? ' [' + esc(posRaw) + ']' : '') + '</div>';
    }
    if (e.reason) {
      html += '<div class="sense">reason: ' + esc(e.reason) + '</div>';
    }
    if (e.etym_key) {
      html += '<div class="sense">etym: ' + esc(e.etym_key) + '</div>';
    }
    if (e.han_tu) {
      html += '<div class="sense">han_tu: ' + esc(e.han_tu) + '</div>';
    }
    if (e.sense_count != null) {
      html += '<div class="sense">sense rows: ' + esc(e.sense_count) + '</div>';
    }
    var preview = Array.isArray(e.sense_preview) ? e.sense_preview : [];
    for (var pi = 0; pi < preview.length; pi++) {
      html += '<div class="sense">gloss: ' + esc(preview[pi] || '') + '</div>';
    }
    if ((e.all_pos || []).length) {
      html += '<div class="sense">POS: ' + esc((e.all_pos || []).join(', ')) + '</div>';
    }
    if ((e.priority_tags || []).length) {
      html += '<div class="sense">pri: ' + esc((e.priority_tags || []).join(', ')) + '</div>';
    }
    html += '</div>';
  }
  return html;
}

function parseDebugSenseLine(rawLine) {
  var raw = String(rawLine || '');
  var cleaned = raw.replace(/\u001e/g, '').replace(/\u001f/g, ' ').trim();
  var parts = raw.split('\t');
  var pos = '';
  var gloss = cleaned;
  if (parts.length >= 4) {
    pos = String(parts[2] || '').trim();
    gloss = String(parts.slice(3).join('\t') || '').trim();
  } else if (parts.length >= 2) {
    gloss = String(parts[parts.length - 1] || '').trim();
  }
  if (!gloss) gloss = cleaned;
  return { pos: pos, gloss: gloss, raw: cleaned };
}

function renderDebugSenseRows(rows, color, prefix) {
  var list = rows || [];
  if (!list.length) return '';
  var html = '';
  for (var i = 0; i < list.length; i++) {
    var parsed = parseDebugSenseLine(list[i]);
    html += '<div class="sense"' + (color ? ' style="color:' + color + ';"' : '') + '>';
    if (prefix) html += esc(prefix) + ': ';
    if (parsed.pos) {
      html += '<span style="font-size:10px;color:#a6adc8;font-style:italic;">' + esc(parsed.pos) + '</span> ';
    }
    html += esc(parsed.gloss || parsed.raw || '');
    html += '</div>';
  }
  return html;
}

function renderDictionaryTraceAppendedEntries(entries) {
  if (!entries || !entries.length) return '<span class="dict-unknown">[no dict_fill entries appended]</span>';
  var html = '';
  for (var i = 0; i < entries.length; i++) {
    var e = entries[i] || {};
    var status = e.filter_status || '';
    var color = status.indexOf('filtered') >= 0 ? 'var(--yellow)' : 'var(--green)';
    html += '<div class="dict-entry">';
    html += '<div><span class="head">' + esc(e.head || '') + '</span>';
    if (e.roman) html += '<span class="roman">' + esc(e.roman) + '</span>';
    html += '<span class="roman" style="color:' + color + ';">' + esc(status) + '</span></div>';
    html += '<div class="sense">text=' + esc(e.text || '') + ', source=' + esc(e.source || '') + '</div>';
    html += '<div class="sense">shown senses=' + esc(e.shown_count != null ? e.shown_count : 0) + ', filtered senses=' + esc(e.filtered_count != null ? e.filtered_count : 0) + '</div>';
    html += '<div class="sense">shown defs=' + esc(e.shown_entry_group_count != null ? e.shown_entry_group_count : 0) + ', filtered defs=' + esc(e.filtered_entry_group_count != null ? e.filtered_entry_group_count : 0) + '</div>';
    var shown = e.shown_senses || [];
    html += renderDebugSenseRows(shown, '', 'show');
    var filtered = e.filtered_senses || [];
    html += renderDebugSenseRows(filtered, 'var(--red)', 'filtered');
    html += '</div>';
  }
  return html;
}

function renderDiscrepancies(doc, segments, resultsBySeg) {
  if (!doc || !doc.sentences) return { html: '<div class="empty">No Trankit data to compare</div>', count: 0 };
  if (!segments || !segments.length) return { html: '<div class="empty">No pipeline segments to compare</div>', count: 0 };
  if (!resultsBySeg) resultsBySeg = [];

  // Flatten raw Trankit tokens into a single list
  var rawTokens = [];
  for (var si = 0; si < doc.sentences.length; si++) {
    var sent = doc.sentences[si];
    var tokens = sent.tokens || [];
    for (var ti = 0; ti < tokens.length; ti++) {
      rawTokens.push({ tok: tokens[ti], sentIdx: si, tokIdx: ti });
    }
  }

  var discrepancies = [];

  // Check token count mismatch
  if (rawTokens.length !== segments.length) {
    discrepancies.push({
      idx: '-',
      token: '',
      field: 'Token count',
      raw: String(rawTokens.length),
      pipeline: String(segments.length),
      severity: 'high'
    });
  }

  // Compare each token
  var limit = Math.max(rawTokens.length, segments.length);
  for (var i = 0; i < limit; i++) {
    var raw = i < rawTokens.length ? rawTokens[i].tok : null;
    var seg = i < segments.length ? segments[i] : null;
    var res = i < resultsBySeg.length ? (resultsBySeg[i] || {}) : {};

    if (!raw && seg) {
      discrepancies.push({ idx: i, token: seg, field: 'Token', raw: '(missing)', pipeline: seg, severity: 'high' });
      continue;
    }
    if (raw && !seg) {
      discrepancies.push({ idx: i, token: raw.text || '', field: 'Token', raw: raw.text || '', pipeline: '(missing)', severity: 'high' });
      continue;
    }
    if (!raw) continue;

    var rawText = raw.text || '';
    var segText = seg || '';

    // Text mismatch
    if (rawText !== segText) {
      discrepancies.push({ idx: i, token: rawText, field: 'Text', raw: rawText, pipeline: segText, severity: 'high' });
    }

    // UPOS mismatch
    var rawUpos = raw.upos || '';
    var pipeUpos = res.upos || res.pos || '';
    if (rawUpos && pipeUpos && rawUpos !== pipeUpos) {
      discrepancies.push({ idx: i, token: segText, field: 'UPOS', raw: rawUpos, pipeline: pipeUpos, severity: 'med' });
    }

    // XPOS mismatch
    var rawXpos = raw.xpos || '';
    var pipeXpos = res.tag || '';
    if (rawXpos && pipeXpos && rawXpos !== pipeXpos) {
      discrepancies.push({ idx: i, token: segText, field: 'XPOS', raw: rawXpos, pipeline: pipeXpos, severity: 'low' });
    }

    // Dependency relation mismatch
    var rawDep = raw.deprel || '';
    var pipeDep = res.dep || '';
    if (rawDep && pipeDep && rawDep !== pipeDep) {
      discrepancies.push({ idx: i, token: segText, field: 'Dep', raw: rawDep, pipeline: pipeDep, severity: 'med' });
    }

    // Head index mismatch â€” Trankit head is 1-indexed within sentence,
    // pipeline stores it differently, so we compare what we can.
    // We convert Trankit's sentence-local head to global index for comparison.
    if (raw.head != null && res.head != null) {
      // raw.head is 1-indexed within sentence; 0 = root
      // Convert to global: find global index of head token in same sentence
      var rawEntry = rawTokens[i];
      var sentStart = 0;
      for (var si2 = 0; si2 < rawEntry.sentIdx; si2++) {
        sentStart += (doc.sentences[si2].tokens || []).length;
      }
      var rawHeadGlobal = raw.head === 0 ? -1 : (sentStart + raw.head - 1);
      var pipeHead = typeof res.head === 'number' ? res.head : -999;
      // Only flag if both are present and differ
      if (rawHeadGlobal >= 0 && pipeHead >= 0 && rawHeadGlobal !== pipeHead) {
        discrepancies.push({ idx: i, token: segText, field: 'Head', raw: String(rawHeadGlobal) + ' (sent-local: ' + raw.head + ')', pipeline: String(pipeHead), severity: 'med' });
      }
    }

    // NER mismatch
    var rawNer = raw.ner || 'O';
    // Pipeline doesn't store NER per-token in results_by_seg directly,
    // but if it did, we'd compare here. For now, just note if Trankit tagged
    // something non-O that got lost.
  }

  if (discrepancies.length === 0) {
    return { html: '<div style="text-align:center;padding:20px;color:var(--green);">All ' + rawTokens.length + ' tokens match between raw Trankit output and pipeline. No discrepancies.</div>', count: 0 };
  }

  var html = '<table><thead><tr>';
  html += '<th>#</th><th>Token</th><th>Field</th><th>Trankit (raw)</th><th>Pipeline (final)</th>';
  html += '</tr></thead><tbody>';
  for (var di = 0; di < discrepancies.length; di++) {
    var d = discrepancies[di];
    var rowColor = d.severity === 'high' ? 'var(--red)' : d.severity === 'med' ? 'var(--yellow)' : 'var(--fg)';
    html += '<tr class="diff-row">';
    html += '<td style="color:#6c7086;">' + d.idx + '</td>';
    html += '<td class="tok-text">' + esc(d.token) + '</td>';
    html += '<td><span class="diff-field" style="color:' + rowColor + ';">' + esc(d.field) + '</span></td>';
    html += '<td class="diff-expected">' + esc(d.raw) + '</td>';
    html += '<td class="diff-actual">' + esc(d.pipeline) + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return { html: html, count: discrepancies.length };
}

function formatOffsetSpan(span) {
  if (!span || span.length < 2) return '';
  var s = Number(span[0]);
  var e = Number(span[1]);
  if (!isFinite(s) || !isFinite(e)) return '';
  return s + ':' + e;
}

function renderNormalizedRemaps(rows) {
  if (!rows || !rows.length) {
    return '<div style="text-align:center;padding:20px;color:var(--green);">No segment remaps were needed for this lookup.</div>';
  }

  var html = '<table><thead><tr>';
  html += '<th>#</th><th>Model Segment</th><th>Model Offset</th><th>Remapped Segment</th><th>Original Offset</th><th>Mapped Slice</th>';
  html += '</tr></thead><tbody>';

  for (var i = 0; i < rows.length; i++) {
    var r = rows[i] || {};
    html += '<tr>';
    html += '<td style="color:#6c7086;">' + esc(r.seg_i) + '</td>';
    html += '<td class="tok-text">' + esc(r.model_segment || '') + '</td>';
    html += '<td style="color:#a6adc8;">' + esc(formatOffsetSpan(r.model_offset)) + '</td>';
    html += '<td class="tok-text" style="color:#94e2d5;">' + esc(r.remapped_segment || '') + '</td>';
    html += '<td style="color:#a6adc8;">' + esc(formatOffsetSpan(r.original_offset)) + '</td>';
    html += '<td>' + esc(r.original_slice || '') + '</td>';
    html += '</tr>';
  }

  html += '</tbody></table>';
  html += '<div style="margin-top:8px;font-size:11px;color:#6c7086;">';
  html += rows.length + ' segment(s) had normalization/filter remap adjustments.';
  html += '</div>';
  return html;
}

function renderSegmentOriginalDiscrepancies(rows) {
  if (!rows || !rows.length) {
    return '<div style="text-align:center;padding:20px;color:var(--green);">All returned segments match their mapped original-text slices.</div>';
  }

  var html = '<table><thead><tr>';
  html += '<th>#</th><th>Issue</th><th>Segment</th><th>Offset</th><th>Original Slice</th>';
  html += '</tr></thead><tbody>';
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i] || {};
    html += '<tr class="diff-row">';
    html += '<td style="color:#6c7086;">' + esc(r.seg_i) + '</td>';
    html += '<td style="color:var(--red);">' + esc(r.issue || '') + '</td>';
    html += '<td class="tok-text">' + esc(r.segment || '') + '</td>';
    html += '<td style="color:#a6adc8;">' + esc(formatOffsetSpan(r.segment_offset)) + '</td>';
    html += '<td class="diff-expected">' + esc(r.original_slice || '') + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

var UPOS_COLORS = {
  ADJ: '#fde68a', ADP: '#7dd3fc', ADV: '#fca5a5', AUX: '#a5b4fc',
  CCONJ: '#67e8f9', DET: '#94a3b8', INTJ: '#fcd34d', NOUN: '#86efac',
  NUM: '#e879f9', PART: '#c4b5fd', PRON: '#fda4af', PROPN: '#6ee7b7',
  PUNCT: '#6c7086', SCONJ: '#5eead4', SYM: '#a78bfa', VERB: '#93c5fd',
  X: '#f87171'
};
function getUposColor(upos) { return UPOS_COLORS[upos] || '#a6adc8'; }

function toggleSection(head) {
  var body = head.nextElementSibling;
  var arrow = head.querySelector('span:last-child');
  if (body.classList.contains('collapsed')) {
    body.classList.remove('collapsed');
    arrow.textContent = 'â–¾';
  } else {
    body.classList.add('collapsed');
    arrow.textContent = 'â–¸';
  }
}

// Initial fetch
fetchDebug();
</script>
</body>
</html>
"""


_DEBUG_MWT_REALIGN_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>MWT Realigner Debug</title>
<style>
  body { font-family: -apple-system, Segoe UI, sans-serif; background: #0b1020; color: #e6e8ef; padding: 16px; }
  h1 { font-size: 18px; margin: 0 0 8px 0; }
  .hint { color: #8aa0c0; font-size: 12px; margin-bottom: 12px; }
  .trace { background: #141a2e; border: 1px solid #2a3357; border-radius: 6px; padding: 10px; margin-bottom: 12px; }
  .surface { font-family: "SF Mono", Consolas, monospace; font-size: 15px; word-break: break-all; }
  table { border-collapse: collapse; margin-top: 8px; font-size: 12px; }
  th, td { border: 1px solid #2a3357; padding: 3px 6px; text-align: left; vertical-align: top; }
  th { background: #1a2140; }
  .pass-trivial    { color: #7ee787; }
  .pass-ltr_exact  { color: #79c0ff; }
  .pass-rtl_exact  { color: #79c0ff; }
  .pass-similarity { color: #f2cc60; }
  .pass-unaligned  { color: #ff7b72; }
  .pass-preassigned{ color: #c9d1d9; }
  .pass-empty      { color: #8b949e; }
  .charmap { font-family: monospace; font-size: 11px; }
  .opcodes { font-family: monospace; font-size: 11px; color: #a0b0d0; }
  button { background: #1f6feb; color: white; border: 0; padding: 6px 12px; border-radius: 4px; cursor: pointer; margin-right: 8px; }
  .toggle-links a { color: #79c0ff; margin-right: 12px; }
</style>
</head>
<body>
<h1>MWT Realigner Debug</h1>
<div class="toggle-links">
  <a href="/debug/lemma_boundaries">lemma boundaries (default)</a>
  <a href="/debug/lemma_boundaries?mode=mwt_realign">mwt realign (this view)</a>
</div>
<div class="hint">
  Shows the authoritative char-level alignment from <code>_realign_mwt_children</code>.
  Requires <code>MWT_REALIGN_DEBUG_ENABLED = True</code> in <code>debug_store.py</code>
  (off in production = zero footprint).
</div>
<div><button onclick="fetchTraces()">Refresh</button><button onclick="clearTraces()">Clear</button></div>
<div id="status" class="hint"></div>
<div id="traces"></div>
<script>
function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, function(c){
    return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c];
  });
}
function renderTrace(trace){
  var surface = trace.surface || '';
  var children = Array.isArray(trace.children) ? trace.children : [];
  var parts = [];
  parts.push('<div class="trace">');
  parts.push('<div class="surface">' + escapeHtml(surface) + ' <span class="hint">(len=' + surface.length + ')</span></div>');
  parts.push('<table><tr><th>#</th><th>probe</th><th>pass</th><th>slice</th><th>slice text</th><th>char_map</th><th>opcodes</th></tr>');
  for (var i = 0; i < children.length; i++){
    var c = children[i] || {};
    var s = Array.isArray(c.slice) ? c.slice : [0,0];
    var sliceText = surface.slice(s[0]||0, s[1]||0);
    var cm = Array.isArray(c.char_map) ? c.char_map.join(',') : '';
    var ops = Array.isArray(c.opcodes) ? c.opcodes.map(function(op){
      return op[0]+'('+op[1]+'..'+op[2]+'->'+op[3]+'..'+op[4]+')';
    }).join(' ') : '';
    parts.push('<tr>'
      + '<td>'+i+'</td>'
      + '<td>'+escapeHtml(c.probe||'')+'</td>'
      + '<td class="pass-'+escapeHtml(c.pass||'')+'">'+escapeHtml(c.pass||'')+'</td>'
      + '<td>['+s[0]+','+s[1]+']</td>'
      + '<td>'+escapeHtml(sliceText)+'</td>'
      + '<td class="charmap">'+escapeHtml(cm)+'</td>'
      + '<td class="opcodes">'+escapeHtml(ops)+'</td>'
      + '</tr>');
  }
  parts.push('</table>');
  if (trace.note) parts.push('<div class="hint">note: '+escapeHtml(trace.note)+'</div>');
  parts.push('</div>');
  return parts.join('');
}
function fetchTraces(){
  fetch('/debug/mwt_realign/data').then(function(r){ return r.json(); }).then(function(data){
    var status = document.getElementById('status');
    var container = document.getElementById('traces');
    if (!data.enabled){
      status.textContent = 'Disabled — master DEBUG_COLLECTION_ENABLED is off (debug_store.py).';
      container.innerHTML = '';
      return;
    }
    var traces = Array.isArray(data.traces) ? data.traces : [];
    status.textContent = traces.length + ' trace(s)';
    container.innerHTML = traces.map(renderTrace).join('');
  });
}
function clearTraces(){
  fetch('/debug/mwt_realign/clear', {method:'POST'}).then(fetchTraces);
}
fetchTraces();
</script>
</body>
</html>
"""
