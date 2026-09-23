"""Gemini translation service."""

from config import GEMINI_API_KEY
import json
import requests
import time
from .settings import log


def translate_sentences(
    sentences: list,
    user,
    *,
    lang_code: str = "",
    sentence_requests=None,
) -> dict:
    """Batch translate per-sentence token lists into fluent idiomatic English via Gemini.

    Uses responseSchema=OBJECT<STRING> for minimal token overhead. Returns
    {"ok": True, "translations": [...]} aligned 1:1 with input, or
    {"ok": False, "error": "..."}.
    """
    from db import ApiUsage, db as _db
    from config import TIER_CAPS
    from api_services import _record_gemini_usage

    if not GEMINI_API_KEY:
        return {"ok": False, "error": "LLM service is not configured."}
    if getattr(user, "tier", "free") == "free":
        return {"ok": False, "error": "upgrade_required", "upgrade": True}

    structured = []
    if isinstance(sentence_requests, list):
        for item in sentence_requests:
            if not isinstance(item, dict):
                continue
            tokens = [
                str(t or "").strip()
                for t in (item.get("tokens") or [])
                if str(t or "").strip()
            ]
            if not tokens:
                continue
            structured.append({"tokens": tokens})

    if not structured:
        return {"ok": True, "translations": []}

    usage = ApiUsage.query.filter_by(user_id=user.id).first()
    if not usage:
        usage = ApiUsage(user_id=user.id)
        _db.session.add(usage)
    usage._maybe_reset(user)
    if not usage.can_use_llm(user):
        return {"ok": False, "error": "Monthly LLM budget reached."}

    model = TIER_CAPS.get(user.tier, {}).get("gemini_model", "gemini-3.1-flash-lite")
    lang_hint = f" from {lang_code}" if lang_code else ""
    system_instruction = (
        "Translate each input token list" + lang_hint + " into fluent English. "
        "Each JSON value is an array of source tokens from one sentence. "
        "You must explicitly use all of the lexical content in the source tokens. "
        "Do not add anything that is not there. "
        "Do not invent subjects, objects, connectives, modality, aspect, discourse material, or explanatory content not supported by the source tokens. "
        "Do not omit lexical material unless English truly requires it to be absorbed into another word or construction. "
        "Keep the result clean, accurate, and natural, but maximally faithful. "
        "Input is JSON with keys s0, s1, s2, ... . "
        "Output MUST be a JSON object with EXACTLY the same keys (s0, s1, ...), "
        "each mapped to its English translation as a string. "
        "Do not merge, split, skip, reorder, or rename keys. "
        "If a token list is untranslatable, return an empty string for that key. "
        "No commentary, no numbering in values, no explanations."
    )
    src_obj = {f"s{i}": item["tokens"] for i, item in enumerate(structured)}
    joined = json.dumps(src_obj, ensure_ascii=False)
    item_count = len(structured)
    keys = [f"s{i}" for i in range(item_count)]
    schema_props = {k: {"type": "STRING"} for k in keys}

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": joined}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {
            "maxOutputTokens": max(256, min(8192, 80 * item_count + 128)),
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": schema_props,
                "required": keys,
                "propertyOrdering": keys,
            },
        },
    }

    try:
        resp = None
        for _attempt in range(3):
            resp = requests.post(url, json=payload, timeout=45)
            if resp.status_code == 503:
                time.sleep(5)
                continue
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
        usage_meta = data.get("usageMetadata", {})
        candidates = data.get("candidates", [])
        if not candidates:
            return {"ok": False, "error": "No response from model."}
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("not an object")
            translations = [
                str(parsed.get(f"s{i}", "") or "") for i in range(item_count)
            ]
        except Exception:
            return {"ok": False, "error": "Malformed translation response."}

        _record_gemini_usage(usage, usage_meta)
        _db.session.commit()
        return {"ok": True, "translations": translations}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "LLM request timed out."}
    except Exception as e:
        log.warning("translate_sentences error: %s", e)
        return {"ok": False, "error": "LLM service error."}
