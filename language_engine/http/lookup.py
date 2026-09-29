"""Reader HTTP lookup."""

import copy
from typing import Any, Mapping

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user

from language_registry import (
    resolve_lang_code,
    run_trankit,
    run_trankit_chunk_boundaries,
)
from pipeline_common import process_lookup_nlp_only
from universal_normalization import run_with_universal_normalization

from .language_config import _normalize_trankit_upos_doc
from .quotas import (
    _attach_lookup_quota_after_success,
    _lookup_token_count_from_payload,
    _precheck_lookup_quota_response,
)
from .responses import _lookup_json_response
from .serializers import _get_requested_sources

bp = Blueprint("lookup", __name__)


def _lookup_json_body() -> dict[str, Any]:
    if request.method != "POST":
        return {}
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _lookup_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clear_trankit_ner_tags(node: Any) -> Any:
    if isinstance(node, dict):
        node.pop("ner", None)
        for value in node.values():
            _clear_trankit_ner_tags(value)
    elif isinstance(node, list):
        for value in node:
            _clear_trankit_ner_tags(value)
    return node


def _replace_lookup_ner_with_gemini(payload: dict[str, Any], lang_code: str) -> None:
    overlay = payload.get("ud_overlay")
    if not isinstance(overlay, dict):
        return
    overlay["ents"] = []
    try:
        import gemini_dict

        result = gemini_dict.recognize_ner_mwe_for_overlay(
            list(payload.get("segments") or []),
            overlay,
            current_user,
            lang_code=lang_code,
        )
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "ents": []}

    ents = result.get("ents") if isinstance(result, Mapping) else []
    if isinstance(ents, list):
        overlay["ents"] = ents
    meta = result.get("meta") if isinstance(result, Mapping) else None
    overlay["gemini_ner"] = {
        "enabled": True,
        "ok": bool(result.get("ok")) if isinstance(result, Mapping) else False,
        "error": str(result.get("error") or "")
        if isinstance(result, Mapping)
        else "Gemini NER failed.",
        "tag_count": len(overlay.get("ents") or []),
        "meta": copy.deepcopy(meta) if isinstance(meta, Mapping) else {},
    }


@bp.route("/lookup", methods=["GET", "POST"])
def lookup():
    """
    Main NLP + dictionary endpoint.
    Receives text, runs the NLP pipeline, then resolves dictionary segmentation
    fully on the server using the SQLite segmenter.
    """
    quota_response = _precheck_lookup_quota_response()
    if quota_response is not None:
        return quota_response

    json_body = _lookup_json_body()
    q = request.args.get("q", "")
    if not q and isinstance(json_body, Mapping):
        q = str(json_body.get("q") or "")
    raw_lang = (
        str(request.args.get("lang") or json_body.get("lang") or "zh").strip().lower()
    )
    strip_punctuation = False
    manual_sentence_segmentation = _lookup_bool(
        request.args.get("manual_sentence_segmentation")
    )
    gemini_ner_requested = False
    trankit_override = request.args.get("trankit", "").strip()
    selected_sources = _get_requested_sources()

    if not q:
        return jsonify({"ok": False, "error": "empty"}), 400

    if len(q) > 20000:
        return jsonify({"ok": False, "error": "Input too long (max 20000 chars)."}), 400

    lang_code = resolve_lang_code(raw_lang)
    if not lang_code:
        return jsonify({"ok": False, "error": f"Unsupported language: {raw_lang}"}), 400

    manual_sentence_segmentation_post_strip = bool(
        manual_sentence_segmentation
        and strip_punctuation
        and lang_code in {"sa", "lzh"}
    )
    effective_strip_punctuation = bool(
        strip_punctuation and not manual_sentence_segmentation_post_strip
    )
    # DISABLED: the experimental chunked Trankit lookup path used geometry chunks
    # as hard tokenizer boundaries. Canonical PDF/HTML extraction now inserts
    # synthetic paragraph breaks instead, so the normal single lookup path gives
    # Trankit natural sentence/paragraph boundaries without multiple chunk passes.
    chunked_trankit_requested = False
    prepared_trankit_chunks: list[dict[str, Any]] = []

    # NLP-only: JS client handles DP segmentation + hydration
    def _run_nlp(text, _dictionary, _hooks, trankit_lang):
        if prepared_trankit_chunks:
            trankit_doc = run_trankit_chunk_boundaries(
                text,
                prepared_trankit_chunks,
                trankit_lang,
                trankit_name_override=trankit_override,
                manual_sentence_segmentation=manual_sentence_segmentation,
                strip_punctuation_after_manual_sentence_segmentation=manual_sentence_segmentation_post_strip,
            )
        else:
            runner = current_app.extensions.get(
                "language_engine.nlp_runner", run_trankit
            )
            trankit_doc = runner(
                text,
                trankit_lang,
                trankit_name_override=trankit_override,
                manual_sentence_segmentation=manual_sentence_segmentation,
                strip_punctuation_after_manual_sentence_segmentation=manual_sentence_segmentation_post_strip,
            )
        trankit_doc = _normalize_trankit_upos_doc(trankit_doc, trankit_lang)
        if gemini_ner_requested:
            _clear_trankit_ner_tags(trankit_doc)
        payload = process_lookup_nlp_only(
            text,
            trankit_doc,
            trankit_lang=trankit_lang,
        )
        if prepared_trankit_chunks and isinstance(payload, dict):
            payload["trankit_chunked_lookup"] = {
                "enabled": True,
                "mode": "boundary_tokenized",
                "chunk_count": len(prepared_trankit_chunks),
            }
        return payload

    payload = run_with_universal_normalization(
        q,
        _run_nlp,
        None,
        None,
        lang_code,
        language=lang_code,
        strip_punctuation=effective_strip_punctuation,
    )

    if gemini_ner_requested and isinstance(payload, dict):
        _replace_lookup_ner_with_gemini(payload, lang_code)

    payload["language"] = lang_code
    payload = _attach_lookup_quota_after_success(payload)
    if bool(payload.get("ok", True)):
        try:
            from analytics import record_lookup

            record_lookup(
                lang_code, _lookup_token_count_from_payload(payload), dp_only=False
            )
        except Exception:
            pass
    return _lookup_json_response(payload)


@bp.route("/annotation", methods=["GET", "POST"])
def annotation_endpoint():
    """
    Annotations placeholder — disabled until user accounts are implemented.
    """
    if request.method == "GET":
        head = (request.args.get("head") or "").strip()
        if not head:
            return jsonify({"ok": False, "error": "missing head"}), 400
        return jsonify({"ok": True, "head": head, "note": ""})
    return jsonify({"ok": True})
