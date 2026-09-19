"""
api_services.py — Google Translate and Gemini API integration for Language Engine.

Provides:
  - query_gemini(): LLM query with piped context text
  - Budget enforcement via ApiUsage model (hard monthly caps)
  - legacy Google Translate MT helpers kept disabled as stubs
"""
import logging
import time

import requests

from db import db, ApiUsage, SyntheticEntry
from config import (
    GOOGLE_TRANSLATE_API_KEY,
    GEMINI_API_KEY,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_MAX_USER_QUERY_CHARS,
    TIER_CAPS,
)

log = logging.getLogger(__name__)
APPROX_CHARS_PER_TOKEN = 4
GEMINI_MAX_HISTORY_TOKENS = 1000
GEMINI_MAX_READER_CONTEXT_TOKENS = 1000

# ---------------------------------------------------------------------------
# Google Translate
# ---------------------------------------------------------------------------

# Map our internal lang codes to Google Translate BCP-47 codes where they differ
_LANG_TO_GOOGLE = {
    "zh": "zh-CN",
    "zh-Hant": "zh-TW",
    "lzh": "zh-CN",   # classical Chinese → simplified as best effort
    "grc": "el",       # ancient Greek → modern Greek fallback
    "ang": "en",       # Old English → English
    "hbo": "he",       # ancient Hebrew → modern Hebrew
    "sa": "hi",        # Sanskrit → Hindi as fallback
}


def _google_lang(lang_code: str) -> str:
    return _LANG_TO_GOOGLE.get(lang_code, lang_code)


def translate_token(token: str, lang_code: str) -> str | None:
    """Translate a single unknown token via Google Translate v2.

    Returns English gloss text, or None on failure.
    Does NOT check budget — caller must check first.
    """
    # Legacy Google Translate MT path disabled.
    return None


def get_or_create_synthetic(token: str, lang_code: str, user) -> dict | None:
    """Look up or create a synthetic entry for an unknown token.

    Returns a dict with entry data (for frontend), or None if:
      - user is free tier (returns special upgrade flag instead — handled by caller)
      - API budget exhausted
      - translation failed

    Side effects: may insert SyntheticEntry + update ApiUsage.
    """
    # Legacy Google Translate synthetic-entry path disabled.
    return None


def _synthetic_to_dict(entry: SyntheticEntry) -> dict:
    """Convert a SyntheticEntry to a frontend-compatible dict."""
    return {
        "head": entry.headword,
        "pos": "",
        "senses": [entry.mt_gloss],
        "synthetic": True,
        "source": entry.source,
        "synthetic_id": entry.id,
    }


# ---------------------------------------------------------------------------
# Gemini LLM
# ---------------------------------------------------------------------------

def _truncate_approx_tokens(text: str, limit: int) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    max_chars = max(0, int(limit)) * APPROX_CHARS_PER_TOKEN
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars].strip()


def _record_gemini_usage(usage: ApiUsage, usage_meta: dict) -> int:
    total_tokens = usage_meta.get("totalTokenCount", 0)
    output_tokens = usage_meta.get("candidatesTokenCount", 0) + usage_meta.get("thoughtsTokenCount", 0)
    prompt_tokens = usage_meta.get("promptTokenCount", max(0, total_tokens - output_tokens))
    usage.record_llm(prompt_tokens, output_tokens)
    return total_tokens


def _call_gemini(
    model: str,
    prompt_parts: list[dict],
    *,
    caller: str = "chatbot",
    max_output_tokens: int = GEMINI_MAX_OUTPUT_TOKENS,
    system_prompt: str | None = None,
) -> dict:
    from gemini_log import log_gemini_call

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    payload: dict = {
        "contents": [{"parts": prompt_parts}],
        "generationConfig": {
            "maxOutputTokens": max_output_tokens,
            "thinkingConfig": {"thinkingLevel": "minimal"},
        },
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    try:
        resp = None
        for _attempt in range(3):
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 503:
                log.warning("Gemini API: 503 overloaded, retrying in 5s...")
                time.sleep(5)
                continue
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()

        usage_meta = log_gemini_call(caller, model, payload, data)
        candidates = data.get("candidates", [])
        if not candidates:
            return {"ok": False, "error": "No response from model."}

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        return {
            "ok": True,
            "text": text,
            "usage_meta": usage_meta,
        }

    except requests.exceptions.Timeout:
        log_gemini_call(caller, model, payload, None, error="timeout")
        return {"ok": False, "error": "LLM request timed out."}
    except requests.exceptions.HTTPError as e:
        log.warning("Gemini API error: %s", e)
        log_gemini_call(caller, model, payload, None, error=str(e))
        return {"ok": False, "error": "LLM service error."}
    except Exception as e:
        log.warning("Gemini unexpected error: %s", e)
        return {"ok": False, "error": "LLM service error."}


def query_gemini(
    context_text: str,
    user_query: str,
    user,
    *,
    lang_code: str = "",
    include_reader_context: bool = False,
    conversation_history: str = "",
    last_exchange: str = "",
) -> dict:
    """Send a query to Gemini with optional reader context.

    Returns {"ok": True, "response": "..."} or {"ok": False, "error": "..."}.
    Enforces budget, input caps, and output token limit.
    """
    if not GEMINI_API_KEY:
        return {"ok": False, "error": "LLM service is not configured."}

    if user.tier == "free":
        return {"ok": False, "error": "upgrade_required", "upgrade": True}

    # Budget check
    usage = ApiUsage.query.filter_by(user_id=user.id).first()
    if not usage:
        usage = ApiUsage(user_id=user.id)
        db.session.add(usage)

    usage._maybe_reset(user)
    if not usage.can_use_llm(user):
        caps = TIER_CAPS.get(user.tier, {})
        current_cost = usage.llm_cost_usd(user)
        current_budget = usage.llm_budget_usd(user)
        current_pct = usage.llm_usage_percent(user)
        return {
            "ok": False,
            "error": "Monthly LLM budget reached ($%.2f / $%.2f, %.1f%%)." % (
                current_cost,
                current_budget,
                current_pct,
            ),
        }

    # Truncate user query
    if len(user_query) > GEMINI_MAX_USER_QUERY_CHARS:
        user_query = user_query[:GEMINI_MAX_USER_QUERY_CHARS]
    conversation_history = _truncate_approx_tokens(conversation_history, GEMINI_MAX_HISTORY_TOKENS)
    context_text = _truncate_approx_tokens(context_text, GEMINI_MAX_READER_CONTEXT_TOKENS)

    # Select model based on tier
    model = TIER_CAPS.get(user.tier, {}).get("gemini_model", "gemini-3.1-flash-lite")

    # Build prompt
    lang_hint = f"The language being studied is: {lang_code}. " if lang_code else ""
    system_instruction = (
        "You are a helpful language learning assistant. "
        + lang_hint
        + "The user is reading foreign-language text and may ask about grammar, vocabulary, meaning, or cultural context. "
        "Always respond in English. "
        "Use earlier conversation history and the reader context if given as context. "
        "Answer the latest question while keeping in mind earlier exchanges. "
        "Answer concisely (under 300 words)."
    )

    prompt_parts = [{"text": system_instruction}]
    history_text = (conversation_history or "").strip()
    if history_text:
        prompt_parts.append({"text": history_text})
    last_exchange_text = (last_exchange or "").strip()
    if last_exchange_text:
        prompt_parts.append({"text": last_exchange_text})
    prompt_parts.append({"text": "User question: " + user_query})
    if include_reader_context and context_text:
        prompt_parts.append({"text": "Reader context:\n" + context_text})
    result = _call_gemini(model, prompt_parts, caller="chatbot")
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "LLM service error.")}

    total_tokens_used = _record_gemini_usage(usage, result.get("usage_meta", {}))
    db.session.commit()

    return {
        "ok": True,
        "response": result.get("text", ""),
        "tokens_used": total_tokens_used,
    }
