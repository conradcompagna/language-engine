"""Reader HTTP llm."""

import json

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
    stream_with_context,
)
from flask_login import current_user

from db import db as le_db

bp = Blueprint("llm", __name__)


@bp.route("/api/mt_gloss", methods=["POST"])
def mt_gloss():
    """Generate a synthetic dictionary entry for one unknown token via Gemini.

    Writes result to gemini_generated_tsvs/{lang}.tsv (server copy).
    """
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    surface_form = (data.get("surface_form") or "").strip()
    target_word = (data.get("target_word") or "").strip()
    lang = (data.get("language") or "").strip()
    sentence = (data.get("sentence") or "").strip()
    lemma = (data.get("lemma") or "").strip()
    upos = (data.get("upos") or "").strip()
    xpos = (data.get("xpos") or "").strip()
    feats = (data.get("feats") or "").strip()
    dep = (data.get("dep") or "").strip()
    if not token or not lang:
        return jsonify({"ok": False, "error": "Missing token or language."}), 400

    import gemini_dict

    if not gemini_dict.is_enabled():
        return jsonify({"ok": False, "error": "Gemini dict not configured."}), 503

    entry = gemini_dict.generate_entry(
        token,
        sentence or token,
        lang,
        lemma_hint=lemma,
        upos=upos,
        xpos=xpos,
        feats=feats,
        dep=dep,
        surface_form=surface_form,
        target_word=target_word,
        user=current_user,
    )

    if not entry:
        return jsonify({"ok": False, "error": "Generation failed or budget exhausted."})

    return jsonify({"ok": True, "entry": entry})


@bp.route("/api/llm_query", methods=["POST"])
def llm_query():
    """Send a user query + reader context to Gemini. Paid users only."""
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401

    from api_services import query_gemini

    data = request.get_json(silent=True) or {}
    context_text = (data.get("context") or "").strip()
    conversation_history = (data.get("history") or "").strip()
    last_exchange = (data.get("last_exchange") or "").strip()
    user_query = (data.get("query") or "").strip()
    lang_code = (data.get("lang") or "").strip()
    include_reader_context = bool(data.get("include_reader_context"))

    if not user_query:
        return jsonify({"ok": False, "error": "Empty query."}), 400

    result = query_gemini(
        context_text,
        user_query,
        current_user,
        lang_code=lang_code,
        include_reader_context=include_reader_context,
        conversation_history=conversation_history,
        last_exchange=last_exchange,
    )
    status = 200 if result.get("ok") else (403 if result.get("upgrade") else 429)
    return jsonify(result), status


@bp.route("/api/llm_translate_sentences", methods=["POST"])
def llm_translate_sentences():
    """Batch translate per-sentence token lists to fluent English. Paid users only."""
    from gemini_dict import translate_sentences

    data = request.get_json(silent=True) or {}
    sentence_requests = data.get("requests") or []
    lang_code = (data.get("lang") or "").strip()
    if not isinstance(sentence_requests, list):
        return jsonify({"ok": False, "error": "requests must be a list."}), 400
    result = translate_sentences(
        [],
        current_user,
        lang_code=lang_code,
        sentence_requests=sentence_requests,
    )
    status = 200 if result.get("ok") else (403 if result.get("upgrade") else 429)
    return jsonify(result), status


@bp.route("/api/llm_usage", methods=["GET"])
def llm_usage():
    """Return current LLM usage stats for the logged-in user."""
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Not logged in."}), 401

    from config import TIER_CAPS
    from db import ApiUsage

    usage = ApiUsage.query.filter_by(user_id=current_user.id).first()
    tier = current_user.tier
    caps = TIER_CAPS.get(tier, {})

    if usage:
        usage._maybe_reset(current_user)
        le_db.session.commit()

    llm_budget_usd = (
        usage.llm_budget_usd(current_user)
        if usage
        else float(caps.get("llm_budget_usd_per_month", 0.0) or 0.0)
    )
    llm_cost_usd = usage.llm_cost_usd(current_user) if usage else 0.0
    llm_usage_pct = usage.llm_usage_percent(current_user) if usage else 0.0

    return jsonify(
        {
            "ok": True,
            "tier": tier,
            "mt_chars_used": usage.mt_chars_used if usage else 0,
            "mt_chars_cap": caps.get("mt_chars_per_month", 0),
            "llm_prompt_tokens_used": usage.llm_prompt_tokens_used if usage else 0,
            "llm_output_tokens_used": usage.llm_output_tokens_used if usage else 0,
            "llm_tokens_used": usage.llm_tokens_used if usage else 0,
            "llm_budget_usd": llm_budget_usd,
            "llm_cost_usd": llm_cost_usd,
            "llm_usage_pct": llm_usage_pct,
        }
    )


@bp.route("/api/llm_glosses", methods=["POST"])
def llm_glosses():
    """Generate short contextual LLM glosses for each Trankit token, streamed as SSE.

    Expects JSON body:
        tokens: list of {text, lemmas} — one per Trankit token
        lang: str — language code

    Streams SSE lines:
        data: {"indices": [...], "glosses": [...]}   — one per chunk as it completes
        data: {"done": true}                          — final message
        data: {"error": "..."}                        — on failure
    """
    # Auth + tier gated centrally via _enforce_paid_feature_gate

    data = request.get_json(silent=True) or {}
    chunks = data.get("chunks") or []
    lang = (data.get("lang") or "").strip()

    if not chunks or not lang:
        return jsonify({"ok": False, "error": "Missing chunks or lang."}), 400

    import gemini_dict
    from db import ApiUsage

    if not gemini_dict.is_enabled():
        return jsonify({"ok": False, "error": "LLM glosses not available."}), 503

    # Budget check
    usage = ApiUsage.query.filter_by(user_id=current_user.id).first()
    if not usage:
        usage = ApiUsage(user_id=current_user.id)
        le_db.session.add(usage)

    usage._maybe_reset(current_user)
    if not usage.can_use_llm(current_user):
        return jsonify({"ok": False, "error": "Monthly LLM budget reached."})

    user_id = current_user.id

    def generate():
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from db import ApiUsage as _ApiUsage

        _usage = _ApiUsage.query.filter_by(user_id=user_id).first()
        try:
            valid_chunks = [c for c in chunks if c.get("tokens")]

            def _run_chunk(chunk_data):
                tokens = chunk_data.get("tokens") or []
                indices = chunk_data.get("indices") or []
                context = chunk_data.get("context") or ""
                sentences = chunk_data.get("sentences") or None
                # Convert client sentence payload (list of {tokens, indices})
                # into [start, end) spans over the flat chunk token list.
                sentence_spans = None
                if sentences:
                    sentence_spans = []
                    cursor = 0
                    for s in sentences:
                        n = len(s.get("tokens") or [])
                        if n > 0:
                            sentence_spans.append([cursor, cursor + n])
                            cursor += n
                g_chunk, usage_chunk = gemini_dict.call_gloss_chunk(
                    tokens,
                    lang,
                    context,
                    sentences=sentence_spans,
                )
                return indices, g_chunk, usage_chunk

            with ThreadPoolExecutor(max_workers=len(valid_chunks) or 1) as executor:
                futures = {executor.submit(_run_chunk, c): c for c in valid_chunks}
                for future in as_completed(futures):
                    try:
                        indices, g_chunk, usage_chunk = future.result()
                    except Exception as e:
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                        continue
                    if g_chunk is not None:
                        out_indices = []
                        out_glosses = []
                        for j, gi in enumerate(indices):
                            if j < len(g_chunk) and g_chunk[j] is not None:
                                out_indices.append(gi)
                                out_glosses.append(g_chunk[j])
                        if out_indices:
                            line = json.dumps(
                                {"indices": out_indices, "glosses": out_glosses},
                                ensure_ascii=False,
                            )
                            yield f"data: {line}\n\n"
                    if (
                        _usage
                        and usage_chunk
                        and (
                            usage_chunk.get("prompt_tokens")
                            or usage_chunk.get("response_tokens")
                        )
                    ):
                        _usage.record_llm(
                            usage_chunk.get("prompt_tokens", 0),
                            usage_chunk.get("response_tokens", 0),
                        )
                        le_db.session.commit()
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield 'data: {"done": true}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/api/llm_decomps", methods=["POST"])
def llm_decomps():
    """Generate inflectional morpheme decompositions for selected tokens, streamed as SSE."""

    data = request.get_json(silent=True) or {}
    chunks = data.get("chunks") or []
    lang = (data.get("lang") or "").strip()

    if not chunks or not lang:
        return jsonify({"ok": False, "error": "Missing chunks or lang."}), 400

    import gemini_dict
    from db import ApiUsage

    if not gemini_dict.is_enabled():
        return jsonify({"ok": False, "error": "LLM decompositions not available."}), 503

    usage = ApiUsage.query.filter_by(user_id=current_user.id).first()
    if not usage:
        usage = ApiUsage(user_id=current_user.id)
        le_db.session.add(usage)

    usage._maybe_reset(current_user)
    if not usage.can_use_llm(current_user):
        return jsonify({"ok": False, "error": "Monthly LLM budget reached."})

    user_id = current_user.id

    def generate():
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from db import ApiUsage as _ApiUsage

        _usage = _ApiUsage.query.filter_by(user_id=user_id).first()
        try:
            valid_chunks = [c for c in chunks if c.get("tokens")]

            def _run_chunk(chunk_data):
                chunk_id = chunk_data.get("chunk_id")
                tokens = chunk_data.get("tokens") or []
                indices = chunk_data.get("indices") or []
                target_positions = chunk_data.get("target_positions") or []
                target_tokens = chunk_data.get("target_tokens") or []
                targets = []
                for i, token_text in enumerate(target_tokens):
                    sentence_index = (
                        target_positions[i] if i < len(target_positions) else i
                    )
                    targets.append(
                        {
                            "sentence_index": sentence_index,
                            "text": token_text,
                        }
                    )
                d_chunk, usage_chunk = gemini_dict.call_decomp_chunk(
                    tokens, targets, lang
                )
                return chunk_id, indices, d_chunk, usage_chunk

            with ThreadPoolExecutor(max_workers=len(valid_chunks) or 1) as executor:
                futures = {executor.submit(_run_chunk, c): c for c in valid_chunks}
                for future in as_completed(futures):
                    try:
                        chunk_id, indices, d_chunk, usage_chunk = future.result()
                    except Exception as e:
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                        continue
                    if d_chunk is not None:
                        line = json.dumps(
                            {
                                "chunk_id": chunk_id,
                                "indices": indices,
                                "decomps": d_chunk,
                            },
                            ensure_ascii=False,
                        )
                        yield f"data: {line}\n\n"
                    if (
                        _usage
                        and usage_chunk
                        and (
                            usage_chunk.get("prompt_tokens")
                            or usage_chunk.get("response_tokens")
                        )
                    ):
                        _usage.record_llm(
                            usage_chunk.get("prompt_tokens", 0),
                            usage_chunk.get("response_tokens", 0),
                        )
                        le_db.session.commit()
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield 'data: {"done": true}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/api/orth_breakdowns", methods=["POST"])
def orth_breakdowns():
    """Generate orthographic/pronunciation breakdowns for each token, streamed as SSE."""

    data = request.get_json(silent=True) or {}
    chunks = data.get("chunks") or []
    lang = (data.get("lang") or "").strip()

    if not chunks or not lang:
        return jsonify({"ok": False, "error": "Missing chunks or lang."}), 400

    import gemini_dict
    from db import ApiUsage

    if not gemini_dict.is_enabled():
        return jsonify({"ok": False, "error": "Orth breakdowns not available."}), 503

    usage = ApiUsage.query.filter_by(user_id=current_user.id).first()
    if not usage:
        usage = ApiUsage(user_id=current_user.id)
        le_db.session.add(usage)

    usage._maybe_reset(current_user)
    if not usage.can_use_llm(current_user):
        return jsonify({"ok": False, "error": "Monthly LLM budget reached."})

    user_id = current_user.id

    def generate():
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from db import ApiUsage as _ApiUsage

        _usage = _ApiUsage.query.filter_by(user_id=user_id).first()
        try:
            valid_chunks = [c for c in chunks if c.get("tokens")]

            def _run_chunk(chunk_data):
                tokens = chunk_data.get("tokens") or []
                indices = chunk_data.get("indices") or []
                slot_counts = chunk_data.get("slot_counts") or None
                o_chunk, usage_chunk = gemini_dict.call_orth_chunk(
                    tokens, lang, slot_counts=slot_counts
                )
                return indices, o_chunk, usage_chunk

            with ThreadPoolExecutor(max_workers=len(valid_chunks) or 1) as executor:
                futures = {executor.submit(_run_chunk, c): c for c in valid_chunks}
                for future in as_completed(futures):
                    try:
                        indices, o_chunk, usage_chunk = future.result()
                    except Exception as e:
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                        continue
                    if o_chunk is not None:
                        out_indices = []
                        out_roms = []
                        for j, gi in enumerate(indices):
                            if j < len(o_chunk) and o_chunk[j] is not None:
                                out_indices.append(gi)
                                out_roms.append(o_chunk[j])
                        if out_indices:
                            line = json.dumps(
                                {"indices": out_indices, "roms": out_roms},
                                ensure_ascii=False,
                            )
                            yield f"data: {line}\n\n"
                    if (
                        _usage
                        and usage_chunk
                        and (
                            usage_chunk.get("prompt_tokens")
                            or usage_chunk.get("response_tokens")
                        )
                    ):
                        _usage.record_llm(
                            usage_chunk.get("prompt_tokens", 0),
                            usage_chunk.get("response_tokens", 0),
                        )
                        le_db.session.commit()
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield 'data: {"done": true}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
