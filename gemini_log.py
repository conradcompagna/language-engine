"""
gemini_log.py — Debug logging for all Gemini API communications.

Writes every request/response to a human-readable JSONL file:
  logs/gemini_comms.jsonl

Each line is a JSON object with:
  - timestamp, caller, model
  - request (system prompt, user prompt, config)
  - response (raw text, parsed if applicable)
  - token counts (from Gemini's usageMetadata)
"""
import json
import os
import datetime
import logging

from pathlib import Path

from config import LE_GEMINI_COMMS_LOG

log = logging.getLogger(__name__)

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "gemini_comms.jsonl"

# Ensure directory exists on import
LOG_DIR.mkdir(exist_ok=True)


def log_gemini_call(
    caller: str,
    model: str,
    request_payload: dict,
    response_data: dict | None,
    error: str | None = None,
):
    """Log a Gemini API call to the JSONL file.

    Args:
        caller: identifier like "chatbot" or "dict_generation"
        model: Gemini model name
        request_payload: the full payload sent to the API
        response_data: the parsed JSON response (or None on error)
        error: error message if the call failed
    """
    # Extract token counts from usageMetadata
    usage_meta = {}
    if response_data:
        usage_meta = response_data.get("usageMetadata", {})
    if not LE_GEMINI_COMMS_LOG:
        return usage_meta

    # Extract the text prompts sent
    sent_texts = []
    contents = request_payload.get("contents", [])
    for content in contents:
        for part in content.get("parts", []):
            if "text" in part:
                sent_texts.append(part["text"])

    system_texts = []
    sys_inst = request_payload.get("systemInstruction", {})
    for part in sys_inst.get("parts", []):
        if "text" in part:
            system_texts.append(part["text"])

    # Extract response text
    response_text = None
    if response_data:
        candidates = response_data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            response_text = "".join(p.get("text", "") for p in parts)

    entry = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "caller": caller,
        "model": model,
        "system_prompt": "\n".join(system_texts) if system_texts else None,
        "user_prompt": "\n---\n".join(sent_texts),
        "generation_config": request_payload.get("generationConfig", {}),
        "response_text": response_text,
        "token_counts": {
            "prompt_tokens": usage_meta.get("promptTokenCount", 0),
            "response_tokens": usage_meta.get("candidatesTokenCount", 0),
            "total_tokens": usage_meta.get("totalTokenCount", 0),
        },
        "error": error,
    }

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning("Failed to write Gemini log: %s", e)

    return usage_meta


def log_translation_cache_hit(caller: str, lang: str, sentences: list, source: str = "browser_session"):
    """Log when fluent sentence translations were served from the client session cache."""
    if not LE_GEMINI_COMMS_LOG:
        return
    entry = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "caller": caller,
        "event": "translation_cache_hit",
        "source": source,
        "lang": lang,
        "sentence_count": len(sentences) if sentences else 0,
        "sentences": sentences,
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning("Failed to write translation cache-hit log: %s", e)


def log_gloss_cache_hit(caller: str, lang: str, tokens: list, source: str = "browser_session"):
    """Log when per-token glosses were served from the client session cache
    instead of calling Gemini. Useful for debugging cache behavior."""
    if not LE_GEMINI_COMMS_LOG:
        return
    entry = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "caller": caller,
        "event": "gloss_cache_hit",
        "source": source,
        "lang": lang,
        "token_count": len(tokens) if tokens else 0,
        "tokens": tokens,
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning("Failed to write Gemini cache-hit log: %s", e)


def log_decomp_cache_hit(caller: str, lang: str, tokens: list, source: str = "browser_session"):
    """Log when per-token decompositions were served from the client session cache
    instead of calling Gemini."""
    if not LE_GEMINI_COMMS_LOG:
        return
    entry = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "caller": caller,
        "event": "decomp_cache_hit",
        "source": source,
        "lang": lang,
        "token_count": len(tokens) if tokens else 0,
        "tokens": tokens,
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning("Failed to write Gemini decomp cache-hit log: %s", e)
