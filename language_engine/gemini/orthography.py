"""Gemini orthography service."""

from config import GEMINI_API_KEY
import json
import requests
import time
from .gloss import _token_to_key_suffix
from .settings import GEMINI_DICT_MODEL, log

_ORTH_BREAKDOWN_SYSTEM_PROMPT = (
    "You are a romanization tool. For each token provided, output its pronunciation "
    "written in plain English letters (romanized). Use ONLY English letters, "
    "no IPA, no original script, no explanations. One romanization per token."
)


def call_orth_chunk(
    chunk: list[dict],
    lang_code: str,
    slot_counts: list[int] | None = None,
) -> tuple[list | None, dict]:
    """Call Gemini to romanize each token.

    chunk: list of {text, ...} — one per sub-part (flattened for MWT/compound lemmas).
    slot_counts: how many sub-parts per original token (for + joining).

    Returns (list_of_results | None, usage_counts).
    Each entry is {"rom": "..."} or None, one per original segment.
    MWT/compound sub-parts are joined with " + ".
    """
    # One schema slot per sub-part token
    props = {}
    required = []
    ordering = []
    slot_keys: list[str] = []
    for i, tok in enumerate(chunk):
        suffix = _token_to_key_suffix(tok.get("text", "") or str(i))
        key = f"{i}_{suffix}"
        props[key] = {"type": "string"}
        required.append(key)
        ordering.append(key)
        slot_keys.append(key)

    # Group sub-part tokens into original segments via slot_counts
    if slot_counts:
        slot_groups: list[list[int]] = []
        ti = 0
        for count in slot_counts:
            slot_groups.append(list(range(ti, ti + count)))
            ti += count
    else:
        slot_groups = [[i] for i in range(len(chunk))]

    schema = {
        "type": "object",
        "properties": props,
        "required": required,
        "propertyOrdering": ordering,
    }

    # User prompt lists each token inline next to its schema key name
    lines = [f"Language: {lang_code}.", "Romanize each token into English letters:"]
    for i, tok in enumerate(chunk):
        lines.append(f"  {slot_keys[i]}: {tok.get('text', '')}")
    user_prompt = "\n".join(lines)

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_DICT_MODEL}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": _ORTH_BREAKDOWN_SYSTEM_PROMPT}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "candidateCount": 1,
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "seed": 7,
            "maxOutputTokens": max(200, len(chunk) * 40),
        },
    }

    try:
        resp = None
        for _attempt in range(3):
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 503:
                log.warning("Orth breakdown chunk: 503 overloaded, retrying in 5s...")
                time.sleep(5)
                continue
            if resp.status_code != 200:
                log.warning(
                    "Orth breakdown chunk: HTTP %d: %s",
                    resp.status_code,
                    resp.text[:500],
                )
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("Orth breakdown chunk failed: %s", e)
        return None, {}

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
        log.warning("Orth breakdown chunk: no candidates")
        return None, usage_counts

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        log.warning(
            "Orth breakdown chunk: JSON parse error: %s\nRaw: %s", e, text[:300]
        )
        return None, usage_counts

    expected_keys = set(required)
    if not isinstance(parsed, dict) or set(parsed.keys()) != expected_keys:
        log.warning(
            "Orth breakdown chunk: key mismatch. Expected %d keys, got %d",
            len(expected_keys),
            len(parsed) if isinstance(parsed, dict) else -1,
        )
        return None, usage_counts

    # Collapse sub-parts with " + " for MWT/compound tokens
    result = []
    for seg_token_indices in slot_groups:
        sub_parts = []
        for tok_idx in seg_token_indices:
            val = parsed.get(slot_keys[tok_idx], "")
            if not isinstance(val, str):
                val = str(val)
            sub_parts.append(val.strip())
        combined = " + ".join(p for p in sub_parts if p)
        result.append({"rom": combined} if combined else None)

    return result, usage_counts
