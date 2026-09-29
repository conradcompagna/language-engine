"""Gemini transport service."""

from config import GEMINI_API_KEY
import json
import requests
import time
from .morphology import _requires_romanization, _trankit_requires_morph
from .prompts import _build_response_schema, _build_system_prompt
from .settings import GEMINI_DICT_MODEL, log


def _call_gemini(
    token: str,
    sentence: str,
    lang_code: str,
    lemma_hint: str = "",
    upos: str = "",
    xpos: str = "",
    feats: str = "",
    dep: str = "",
    surface_form: str = "",
    target_word: str = "",
) -> tuple[dict | None, dict]:
    """Call Gemini for a single token. Returns (entry_dict, usage_counts)."""
    _ = (xpos, dep, upos)
    requires_roman = _requires_romanization(lang_code)
    target_text = (
        str(target_word or "").strip()
        or str(surface_form or "").strip()
        or str(token or "").strip()
    )
    inflects = _trankit_requires_morph(target_text, lemma_hint, feats, lang_code)
    response_schema = _build_response_schema(requires_roman, inflects)
    system_prompt = _build_system_prompt(requires_roman, inflects)
    user_prompt_lines = [f"Sentence context: {sentence}"]
    user_prompt_lines.append(f"Target: {target_text}")
    user_prompt = "\n".join(user_prompt_lines)

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_DICT_MODEL}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
            "candidateCount": 1,
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "seed": 7,
            "maxOutputTokens": 1000,
        },
    }

    for _attempt in range(3):
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 503:
            log.warning("Gemini dict: 503 overloaded, retrying in 5s...")
            time.sleep(5)
            continue
        if resp.status_code != 200:
            log.warning(
                "Gemini dict: HTTP %d response body: %s",
                resp.status_code,
                resp.text[:500],
            )
        resp.raise_for_status()
        break
    else:
        resp.raise_for_status()
    data = resp.json()

    usage_meta = data.get("usageMetadata") or {}
    total_tokens = usage_meta.get("totalTokenCount", 0)
    response_tokens = usage_meta.get("candidatesTokenCount", 0) + usage_meta.get(
        "thoughtsTokenCount", 0
    )
    usage_counts = {
        "prompt_tokens": usage_meta.get(
            "promptTokenCount", max(0, total_tokens - response_tokens)
        ),
        "response_tokens": response_tokens,
        "total_tokens": total_tokens,
    }

    candidates = data.get("candidates", [])
    if not candidates:
        log.warning("Gemini dict: no candidates in response")
        return None, usage_counts

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        log.warning("Gemini dict: JSON parse error: %s\nRaw: %s", e, text[:300])
        return None, usage_counts

    if not isinstance(parsed, dict):
        log.warning("Gemini dict: expected object, got %s", type(parsed))
        return None, usage_counts

    surface_token = str(token or "").strip()

    romanization = (
        str(parsed.get("romanization", "") or "").strip() if requires_roman else ""
    )
    if inflects:
        # Schema sends "morphological properties" and "lemma"; remap to internal names
        commentary = str(parsed.get("morphological properties", "") or "").strip()
        canonical_raw = str(parsed.get("lemma", "") or "").strip()
    else:
        commentary = ""
        canonical_raw = ""

    entry = {
        "headword": surface_token,
        "pos": parsed.get("pos", ""),
        "romanization": romanization,
        "glosses": parsed.get("glosses", ""),
        "commentary": commentary,
        "canonical_form": canonical_raw,
    }

    return entry, usage_counts
